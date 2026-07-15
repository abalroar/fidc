"""Concatenate compatible PPTX packages without rasterizing native objects.

The merger works at the Office Open XML package level. Appended slide XML is
kept intact and every reachable relationship part (charts, images, embedded
workbooks, and chart styles) is copied with a collision-free part name. This is
deliberately stricter than shape-by-shape copying, which commonly leaves charts
pointing at the source package and produces a presentation PowerPoint repairs.

Only presentations that use the same slide size and the same blank
layout/master/theme chain are accepted. The decks generated for the Carteira
page satisfy that contract. Speaker notes are intentionally omitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import posixpath
import re
from typing import Iterable
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from lxml import etree


_CONTENT_TYPES_PATH = "[Content_Types].xml"
_PRESENTATION_PATH = "ppt/presentation.xml"
_PRESENTATION_RELS_PATH = "ppt/_rels/presentation.xml.rels"

_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

_SLIDE_REL_TYPE = f"{_R_NS}/slide"
_SLIDE_LAYOUT_REL_TYPE = f"{_R_NS}/slideLayout"
_SLIDE_MASTER_REL_TYPE = f"{_R_NS}/slideMaster"
_THEME_REL_TYPE = f"{_R_NS}/theme"
_NOTES_SLIDE_REL_TYPE = f"{_R_NS}/notesSlide"

_SLIDE_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"


class PptxMergeError(ValueError):
    """Raised when PPTX packages cannot be concatenated without fidelity loss."""


@dataclass
class _ContentTypes:
    root: etree._Element
    defaults: dict[str, str]
    overrides: dict[str, str]

    @classmethod
    def from_files(cls, files: dict[str, bytes]) -> "_ContentTypes":
        try:
            root = etree.fromstring(files[_CONTENT_TYPES_PATH])
        except (KeyError, etree.XMLSyntaxError) as exc:
            raise PptxMergeError("PPTX sem [Content_Types].xml válido.") from exc
        defaults = {
            str(node.get("Extension") or "").lower(): str(node.get("ContentType") or "")
            for node in root.findall(f"{{{_CT_NS}}}Default")
        }
        overrides = {
            str(node.get("PartName") or ""): str(node.get("ContentType") or "")
            for node in root.findall(f"{{{_CT_NS}}}Override")
        }
        return cls(root=root, defaults=defaults, overrides=overrides)

    def content_type_for(self, part_path: str) -> str:
        override = self.overrides.get(f"/{part_path}")
        if override:
            return override
        extension = posixpath.splitext(part_path)[1].lstrip(".").lower()
        default = self.defaults.get(extension)
        if default:
            return default
        raise PptxMergeError(f"Tipo de conteúdo ausente para a parte {part_path!r}.")

    def add_override(self, part_path: str, content_type: str) -> None:
        part_name = f"/{part_path}"
        if self.overrides.get(part_name) == content_type:
            return
        if part_name in self.overrides:
            raise PptxMergeError(f"Conflito de tipo de conteúdo em {part_path!r}.")
        node = etree.SubElement(self.root, f"{{{_CT_NS}}}Override")
        node.set("PartName", part_name)
        node.set("ContentType", content_type)
        self.overrides[part_name] = content_type

    def to_bytes(self) -> bytes:
        return _serialize_xml(self.root)


def merge_pptx_bytes(primary_pptx: bytes, *additional_pptx: bytes) -> bytes:
    """Append slides from ``additional_pptx`` to ``primary_pptx`` in order.

    Native tables and charts remain native. Chart workbooks, chart styles,
    images, hyperlinks, and other slide-level dependencies are copied by their
    OPC relationships. The first presentation supplies the slide master/theme.

    Args:
        primary_pptx: Presentation whose slides, theme, and document properties
            remain first and authoritative.
        *additional_pptx: Presentations appended in the given order.

    Returns:
        A complete PPTX package as bytes.

    Raises:
        PptxMergeError: If an input is invalid, uses a different slide size, or
            does not share the same blank layout/master/theme contract.
    """
    destination = _read_package(primary_pptx, label="deck principal")
    _validate_core_parts(destination, label="deck principal")
    if not additional_pptx:
        return bytes(primary_pptx)

    destination_content_types = _ContentTypes.from_files(destination)
    destination_layout = _find_compatible_blank_layout(destination)
    destination_layout_signature = _layout_chain_signature(destination, destination_layout)
    destination_size = _slide_size(destination)

    for deck_index, payload in enumerate(additional_pptx, start=2):
        source = _read_package(payload, label=f"deck {deck_index}")
        _validate_core_parts(source, label=f"deck {deck_index}")
        if _slide_size(source) != destination_size:
            raise PptxMergeError(
                f"Deck {deck_index} usa tamanho de slide diferente do deck principal."
            )
        source_content_types = _ContentTypes.from_files(source)
        _append_package_slides(
            destination=destination,
            source=source,
            destination_content_types=destination_content_types,
            source_content_types=source_content_types,
            destination_layout=destination_layout,
            destination_layout_signature=destination_layout_signature,
            deck_index=deck_index,
        )

    destination[_CONTENT_TYPES_PATH] = destination_content_types.to_bytes()
    merged = _write_package(destination)
    _validate_openable_presentation(merged)
    return merged


def _append_package_slides(
    *,
    destination: dict[str, bytes],
    source: dict[str, bytes],
    destination_content_types: _ContentTypes,
    source_content_types: _ContentTypes,
    destination_layout: str,
    destination_layout_signature: tuple[str, str, str],
    deck_index: int,
) -> None:
    presentation_root = _xml(destination, _PRESENTATION_PATH)
    presentation_rels_root = _xml(destination, _PRESENTATION_RELS_PATH)
    slide_id_list = presentation_root.find(f"{{{_P_NS}}}sldIdLst")
    if slide_id_list is None:
        slide_id_list = etree.SubElement(presentation_root, f"{{{_P_NS}}}sldIdLst")

    next_slide_number = _next_slide_part_number(destination)
    next_slide_id = _next_presentation_slide_id(slide_id_list)
    used_relationship_ids = {
        str(node.get("Id") or "")
        for node in presentation_rels_root.findall(f"{{{_REL_NS}}}Relationship")
    }
    next_relationship_number = _next_relationship_number(used_relationship_ids)
    used_part_names = set(destination)
    source_to_destination: dict[str, str] = {}

    source_slides = _presentation_slide_paths(source)
    destination_slides: list[str] = []
    for source_slide in source_slides:
        destination_slide = f"ppt/slides/slide{next_slide_number}.xml"
        next_slide_number += 1
        source_to_destination[source_slide] = destination_slide
        destination_slides.append(destination_slide)

    # Preallocating every slide mapping keeps internal slide hyperlinks valid,
    # including links to a slide that has not been copied yet.
    for source_slide, destination_slide in zip(source_slides, destination_slides, strict=True):
        source_layout = _slide_layout_path(source, source_slide)
        if _layout_chain_signature(source, source_layout) != destination_layout_signature:
            raise PptxMergeError(
                f"Deck {deck_index} usa layout/master/tema incompatível no slide "
                f"{posixpath.basename(source_slide)}."
            )
        source_to_destination[source_layout] = destination_layout
        _copy_part_with_relationships(
            source_part=source_slide,
            destination_part=destination_slide,
            source=source,
            destination=destination,
            source_content_types=source_content_types,
            destination_content_types=destination_content_types,
            source_to_destination=source_to_destination,
            used_part_names=used_part_names,
            destination_layout=destination_layout,
            deck_index=deck_index,
            is_slide=True,
        )

        relationship_id = _allocate_relationship_id(
            used_relationship_ids,
            start=next_relationship_number,
        )
        next_relationship_number = int(relationship_id.removeprefix("rId")) + 1
        relationship = etree.SubElement(
            presentation_rels_root,
            f"{{{_REL_NS}}}Relationship",
        )
        relationship.set("Id", relationship_id)
        relationship.set("Type", _SLIDE_REL_TYPE)
        relationship.set(
            "Target",
            posixpath.relpath(destination_slide, posixpath.dirname(_PRESENTATION_PATH)),
        )

        slide_id = etree.SubElement(slide_id_list, f"{{{_P_NS}}}sldId")
        slide_id.set("id", str(next_slide_id))
        slide_id.set(f"{{{_R_NS}}}id", relationship_id)
        next_slide_id += 1

    destination[_PRESENTATION_PATH] = _serialize_xml(presentation_root)
    destination[_PRESENTATION_RELS_PATH] = _serialize_xml(presentation_rels_root)


def _copy_part_with_relationships(
    *,
    source_part: str,
    destination_part: str,
    source: dict[str, bytes],
    destination: dict[str, bytes],
    source_content_types: _ContentTypes,
    destination_content_types: _ContentTypes,
    source_to_destination: dict[str, str],
    used_part_names: set[str],
    destination_layout: str,
    deck_index: int,
    is_slide: bool = False,
) -> str:
    existing = source_to_destination.get(source_part)
    if existing and existing != destination_part:
        return existing
    if source_part not in source:
        raise PptxMergeError(f"Parte relacionada ausente no PPTX: {source_part!r}.")

    source_to_destination[source_part] = destination_part
    used_part_names.add(destination_part)
    destination[destination_part] = source[source_part]
    destination_content_types.add_override(
        destination_part,
        source_content_types.content_type_for(source_part),
    )

    source_rels_path = _relationships_path(source_part)
    if source_rels_path not in source:
        return destination_part

    rels_root = _xml(source, source_rels_path)
    for relationship in list(rels_root.findall(f"{{{_REL_NS}}}Relationship")):
        if str(relationship.get("TargetMode") or "").lower() == "external":
            continue
        relationship_type = str(relationship.get("Type") or "")
        source_target = _resolve_relationship_target(
            owner_part=source_part,
            target=str(relationship.get("Target") or ""),
        )
        if is_slide and relationship_type == _NOTES_SLIDE_REL_TYPE:
            rels_root.remove(relationship)
            continue
        if is_slide and relationship_type == _SLIDE_LAYOUT_REL_TYPE:
            destination_target = destination_layout
        else:
            destination_target = source_to_destination.get(source_target, "")
            if not destination_target:
                destination_target = _allocate_part_name(
                    source_target,
                    used_part_names,
                    deck_index=deck_index,
                )
                _copy_part_with_relationships(
                    source_part=source_target,
                    destination_part=destination_target,
                    source=source,
                    destination=destination,
                    source_content_types=source_content_types,
                    destination_content_types=destination_content_types,
                    source_to_destination=source_to_destination,
                    used_part_names=used_part_names,
                    destination_layout=destination_layout,
                    deck_index=deck_index,
                )
        relationship.set(
            "Target",
            posixpath.relpath(destination_target, posixpath.dirname(destination_part)),
        )

    destination[_relationships_path(destination_part)] = _serialize_xml(rels_root)
    used_part_names.add(_relationships_path(destination_part))
    return destination_part


def _presentation_slide_paths(files: dict[str, bytes]) -> list[str]:
    presentation_root = _xml(files, _PRESENTATION_PATH)
    rels_root = _xml(files, _PRESENTATION_RELS_PATH)
    relationships = {
        str(node.get("Id") or ""): node
        for node in rels_root.findall(f"{{{_REL_NS}}}Relationship")
    }
    slide_id_list = presentation_root.find(f"{{{_P_NS}}}sldIdLst")
    if slide_id_list is None:
        return []
    paths: list[str] = []
    for slide_id in slide_id_list.findall(f"{{{_P_NS}}}sldId"):
        relationship_id = str(slide_id.get(f"{{{_R_NS}}}id") or "")
        relationship = relationships.get(relationship_id)
        if relationship is None or relationship.get("Type") != _SLIDE_REL_TYPE:
            raise PptxMergeError("Relacionamento de slide ausente no presentation.xml.rels.")
        paths.append(
            _resolve_relationship_target(
                owner_part=_PRESENTATION_PATH,
                target=str(relationship.get("Target") or ""),
            )
        )
    return paths


def _find_compatible_blank_layout(files: dict[str, bytes]) -> str:
    candidates = sorted(
        name
        for name in files
        if name.startswith("ppt/slideLayouts/") and name.endswith(".xml")
    )
    for candidate in candidates:
        root = _xml(files, candidate)
        if str(root.get("type") or "").lower() == "blank":
            _layout_chain_signature(files, candidate)
            return candidate
    raise PptxMergeError("Deck principal não contém um slide layout vazio compatível.")


def _slide_layout_path(files: dict[str, bytes], slide_path: str) -> str:
    rels_path = _relationships_path(slide_path)
    if rels_path not in files:
        raise PptxMergeError(f"Slide sem relacionamentos: {slide_path!r}.")
    rels_root = _xml(files, rels_path)
    for relationship in rels_root.findall(f"{{{_REL_NS}}}Relationship"):
        if relationship.get("Type") == _SLIDE_LAYOUT_REL_TYPE:
            return _resolve_relationship_target(
                owner_part=slide_path,
                target=str(relationship.get("Target") or ""),
            )
    raise PptxMergeError(f"Slide sem slide layout: {slide_path!r}.")


def _layout_chain_signature(files: dict[str, bytes], layout_path: str) -> tuple[str, str, str]:
    layout_root = _xml(files, layout_path)
    if str(layout_root.get("type") or "").lower() != "blank":
        raise PptxMergeError(f"Layout não vazio não suportado: {layout_path!r}.")
    master_path = _related_part_by_type(files, layout_path, _SLIDE_MASTER_REL_TYPE)
    theme_path = _related_part_by_type(files, master_path, _THEME_REL_TYPE)
    return tuple(
        sha256(files[path]).hexdigest()
        for path in (layout_path, master_path, theme_path)
    )  # type: ignore[return-value]


def _related_part_by_type(files: dict[str, bytes], owner_path: str, relationship_type: str) -> str:
    rels_path = _relationships_path(owner_path)
    if rels_path not in files:
        raise PptxMergeError(f"Relacionamentos ausentes para {owner_path!r}.")
    rels_root = _xml(files, rels_path)
    for relationship in rels_root.findall(f"{{{_REL_NS}}}Relationship"):
        if relationship.get("Type") == relationship_type:
            target = _resolve_relationship_target(
                owner_part=owner_path,
                target=str(relationship.get("Target") or ""),
            )
            if target not in files:
                raise PptxMergeError(f"Parte relacionada ausente: {target!r}.")
            return target
    raise PptxMergeError(f"Relacionamento {relationship_type!r} ausente em {owner_path!r}.")


def _slide_size(files: dict[str, bytes]) -> tuple[int, int]:
    root = _xml(files, _PRESENTATION_PATH)
    slide_size = root.find(f"{{{_P_NS}}}sldSz")
    if slide_size is None:
        raise PptxMergeError("presentation.xml sem dimensão de slide.")
    try:
        return int(slide_size.get("cx")), int(slide_size.get("cy"))
    except (TypeError, ValueError) as exc:
        raise PptxMergeError("Dimensão de slide inválida.") from exc


def _allocate_part_name(source_path: str, used_names: set[str], *, deck_index: int) -> str:
    directory = posixpath.dirname(source_path)
    filename = posixpath.basename(source_path)
    stem, extension = posixpath.splitext(filename)
    match = re.match(r"^(.*?)(\d+)$", stem)
    prefix = match.group(1) if match else f"{stem}_deck{deck_index}_"
    number = 1
    while True:
        candidate = posixpath.join(directory, f"{prefix}{number}{extension}")
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        number += 1


def _next_slide_part_number(files: dict[str, bytes]) -> int:
    numbers = [
        int(match.group(1))
        for name in files
        if (match := re.fullmatch(r"ppt/slides/slide(\d+)\.xml", name))
    ]
    return max(numbers, default=0) + 1


def _next_presentation_slide_id(slide_id_list: etree._Element) -> int:
    values = []
    for node in slide_id_list.findall(f"{{{_P_NS}}}sldId"):
        try:
            values.append(int(node.get("id")))
        except (TypeError, ValueError):
            continue
    return max(values, default=255) + 1


def _next_relationship_number(relationship_ids: Iterable[str]) -> int:
    numbers = [
        int(match.group(1))
        for value in relationship_ids
        if (match := re.fullmatch(r"rId(\d+)", value))
    ]
    return max(numbers, default=0) + 1


def _allocate_relationship_id(used_ids: set[str], *, start: int) -> str:
    number = max(start, 1)
    while f"rId{number}" in used_ids:
        number += 1
    relationship_id = f"rId{number}"
    used_ids.add(relationship_id)
    return relationship_id


def _relationships_path(part_path: str) -> str:
    return posixpath.join(
        posixpath.dirname(part_path),
        "_rels",
        f"{posixpath.basename(part_path)}.rels",
    )


def _resolve_relationship_target(*, owner_part: str, target: str) -> str:
    if not target:
        raise PptxMergeError(f"Relacionamento interno sem Target em {owner_part!r}.")
    if target.startswith("/"):
        resolved = posixpath.normpath(target).lstrip("/")
    else:
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(owner_part), target))
    if resolved.startswith("../") or resolved == "..":
        raise PptxMergeError(f"Relacionamento escapa do pacote: {target!r}.")
    return resolved


def _read_package(payload: bytes, *, label: str) -> dict[str, bytes]:
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        raise PptxMergeError(f"{label.capitalize()} vazio ou inválido.")
    try:
        with ZipFile(BytesIO(bytes(payload)), "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise PptxMergeError(f"{label.capitalize()} contém partes duplicadas.")
            bad_member = archive.testzip()
            if bad_member:
                raise PptxMergeError(f"{label.capitalize()} contém parte corrompida: {bad_member}.")
            return {name: archive.read(name) for name in names}
    except (BadZipFile, OSError) as exc:
        raise PptxMergeError(f"{label.capitalize()} não é um PPTX válido.") from exc


def _write_package(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return output.getvalue()


def _validate_core_parts(files: dict[str, bytes], *, label: str) -> None:
    missing = [
        path
        for path in (_CONTENT_TYPES_PATH, _PRESENTATION_PATH, _PRESENTATION_RELS_PATH)
        if path not in files
    ]
    if missing:
        raise PptxMergeError(
            f"{label.capitalize()} não é uma apresentação PPTX completa: {', '.join(missing)}."
        )
    _presentation_slide_paths(files)


def _validate_openable_presentation(payload: bytes) -> None:
    try:
        from pptx import Presentation

        Presentation(BytesIO(payload))
    except Exception as exc:  # noqa: BLE001
        raise PptxMergeError("O PPTX concatenado não pôde ser reaberto pelo python-pptx.") from exc


def _xml(files: dict[str, bytes], path: str) -> etree._Element:
    try:
        return etree.fromstring(files[path])
    except KeyError as exc:
        raise PptxMergeError(f"Parte XML ausente: {path!r}.") from exc
    except etree.XMLSyntaxError as exc:
        raise PptxMergeError(f"Parte XML inválida: {path!r}.") from exc


def _serialize_xml(root: etree._Element) -> bytes:
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )
