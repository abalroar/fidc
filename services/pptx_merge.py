"""Concatenate compatible PPTX packages without rasterizing native objects.

The merger works at the Office Open XML package level. Appended slide XML is
kept intact and every reachable relationship part (charts, images, embedded
workbooks, and chart styles) is copied with a collision-free part name. This is
deliberately stricter than shape-by-shape copying, which commonly leaves charts
pointing at the source package and produces a presentation PowerPoint repairs.

Only presentations that use the same slide size and the same blank
layout/master/theme chain are accepted. The decks generated for the Carteira
page satisfy that contract. Speaker notes and their source citations are kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import posixpath
import re
import tempfile
from typing import Iterable
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from lxml import etree
from services.presentation_text import public_pptx_bytes


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
_NOTES_MASTER_REL_TYPE = f"{_R_NS}/notesMaster"

_SLIDE_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
_NOTES_MASTER_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"


class PptxMergeError(ValueError):
    """Raised when PPTX packages cannot be concatenated without fidelity loss."""


_SERIAL_TEMP_BUDGET = 512 * 1024 * 1024
_SERIAL_XML_LIMIT = 32 * 1024 * 1024
_SERIAL_BATCH_SLIDES = 32


class _SerialPackage(Mapping[str, bytes]):
    """A member index, with no cache of decompressed package contents."""

    def __init__(self, archive: ZipFile):
        self.archive = archive
        names = archive.namelist()
        self.names = set(names)
        if len(names) != len(self.names):
            raise PptxMergeError("PPTX contém partes duplicadas.")
        if any(name.startswith("/") or posixpath.normpath(name).startswith("../") for name in names):
            raise PptxMergeError("PPTX contém caminho de parte inválido.")

    def __getitem__(self, name: str) -> bytes:
        if name not in self.names:
            raise KeyError(name)
        if self.archive.getinfo(name).file_size > _SERIAL_XML_LIMIT:
            raise PptxMergeError(f"Parte excede o limite de leitura individual: {name!r}.")
        return self.archive.read(name)

    def __iter__(self):
        return iter(self.names)

    def __len__(self):
        return len(self.names)

    def __contains__(self, name):
        return name in self.names


def merge_pptx_files_serial(input_paths: Iterable[str | Path], output_path: str | Path) -> Path:
    """Merge compatible, already-sanitized batches without loading a final deck.

    At most one ZIP member is copied at a time. Only presentation/content-type
    metadata and part-name maps survive between batches; neither all package
    XML nor a ``Presentation`` for the result is created. Slide and notes XML
    stay byte-for-byte intact. Inputs must contain at most 32 slides each.
    """
    paths = tuple(Path(path).resolve() for path in input_paths)
    output = Path(output_path).resolve()
    if not paths or output in paths:
        raise PptxMergeError("Informe lotes de entrada e uma saída distinta.")
    try:
        input_bytes = sum(path.stat().st_size for path in paths)
    except OSError as exc:
        raise PptxMergeError("Lote PPTX ausente ou inacessível.") from exc
    if input_bytes >= _SERIAL_TEMP_BUDGET:
        raise PptxMergeError("Lotes excedem o orçamento temporário de 512 MiB.")

    batches = []
    size = layout_signature = notes_signature = table_styles_signature = None
    canonical_layout = canonical_notes = None
    # This pass holds only a single batch's structural metadata, never slides.
    for batch_index, path in enumerate(paths):
        try:
            with ZipFile(path) as archive:
                source = _SerialPackage(archive)
                _validate_core_parts(source, label=f"lote {batch_index + 1}")
                slides = _presentation_slide_paths(source)
                if len(slides) > _SERIAL_BATCH_SLIDES:
                    raise PptxMergeError("Lote serial excede 32 slides.")
                current_size = _slide_size(source)
                if size is not None and current_size != size:
                    raise PptxMergeError("Lote usa tamanho de slide diferente.")
                size = current_size
                layout = _find_compatible_blank_layout(source)
                signature = _layout_chain_signature(source, layout)
                if layout_signature is not None and signature != layout_signature:
                    raise PptxMergeError("Lote usa layout/master/tema incompatível.")
                layout_signature = signature
                canonical_layout = canonical_layout or layout
                layouts = {}
                signatures = {layout: signature}
                for slide in slides:
                    slide_layout = _slide_layout_path(source, slide)
                    if slide_layout not in signatures:
                        signatures[slide_layout] = _layout_chain_signature(source, slide_layout)
                    if signatures[slide_layout] != layout_signature:
                        raise PptxMergeError("Slide usa layout/master/tema incompatível.")
                    layouts[slide] = slide_layout
                styles = sha256(source["ppt/tableStyles.xml"]).hexdigest() if "ppt/tableStyles.xml" in source else ""
                if table_styles_signature is not None and styles != table_styles_signature:
                    raise PptxMergeError("Lotes usam tableStyles incompatíveis.")
                table_styles_signature = styles
                types = _ContentTypes.from_files(source)
                masters = _notes_master_paths(types)
                for master in masters:
                    signature = _notes_chain_signature(source, master)
                    if notes_signature is not None and signature != notes_signature:
                        raise PptxMergeError("Notes masters incompatíveis entre lotes.")
                    notes_signature = signature
                if masters and canonical_notes is None:
                    canonical_notes = masters[0]
                batches.append((slides, layouts, masters))
        except (BadZipFile, OSError, etree.XMLSyntaxError) as exc:
            raise PptxMergeError(f"Lote {batch_index + 1} não é um PPTX válido.") from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=output.name + ".", suffix=".partial", delete=False) as stream:
            temporary = Path(stream.name)
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as target:
            written: set[str] = set()
            planned: set[str] = set()
            with ZipFile(paths[0]) as archive:
                first = _SerialPackage(archive)
                content_types = _ContentTypes.from_files(first)
                presentation = _xml(first, _PRESENTATION_PATH)
                presentation_rels = _xml(first, _PRESENTATION_RELS_PATH)
                app_properties = first.get("docProps/app.xml")
                slide_ids = presentation.find(f"{{{_P_NS}}}sldIdLst")
                if slide_ids is None:
                    slide_ids = etree.SubElement(presentation, f"{{{_P_NS}}}sldIdLst")
                next_id = _next_presentation_slide_id(slide_ids)
                used_rel_ids = {node.get("Id") for node in presentation_rels}
                next_rel = _next_relationship_number(used_rel_ids)
                duplicate_masters = set(batches[0][2]) - {canonical_notes}
                skipped = duplicate_masters | {_relationships_path(name) for name in duplicate_masters}
                for name in duplicate_masters:
                    content_types.remove_override(name)
                used_names = first.names - skipped
                next_slide = _next_slide_part_number(first)
                deferred = {_CONTENT_TYPES_PATH, _PRESENTATION_PATH, _PRESENTATION_RELS_PATH, "docProps/app.xml"}

                def budget():
                    if input_bytes + target.fp.tell() > _SERIAL_TEMP_BUDGET:
                        raise PptxMergeError("Lotes e saída excedem o orçamento temporário de 512 MiB.")

                def write_bytes(name, data):
                    if name in written:
                        raise PptxMergeError(f"Parte duplicada na saída: {name!r}.")
                    target.writestr(name, data)
                    written.add(name)
                    budget()

                def copy_member(source, source_name, destination_name):
                    if destination_name in written:
                        raise PptxMergeError(f"Parte duplicada na saída: {destination_name!r}.")
                    with source.archive.open(source_name) as incoming, target.open(destination_name, "w") as outgoing:
                        for block in iter(lambda: incoming.read(1024 * 1024), b""):
                            outgoing.write(block)
                    written.add(destination_name)
                    budget()

                for name in archive.namelist():
                    if name in skipped or name in deferred:
                        continue
                    if name.endswith(".rels") and duplicate_masters:
                        owner = "" if name == "_rels/.rels" else posixpath.join(posixpath.dirname(posixpath.dirname(name)), posixpath.basename(name).removesuffix(".rels"))
                        relations = _xml(first, name)
                        for relation in relations:
                            if str(relation.get("TargetMode") or "").lower() != "external":
                                referred = _resolve_relationship_target(owner_part=owner, target=relation.get("Target", ""))
                                if referred in duplicate_masters:
                                    relation.set("Target", posixpath.relpath(canonical_notes, posixpath.dirname(owner)))
                        write_bytes(name, _serialize_xml(relations))
                    else:
                        copy_member(first, name, name)

            total_slides = len(batches[0][0])
            for batch_index, path in enumerate(paths[1:], start=2):
                with ZipFile(path) as archive:
                    source = _SerialPackage(archive)
                    source_types = _ContentTypes.from_files(source)
                    slides, layouts, masters = batches[batch_index - 1]
                    mapping = {layout: canonical_layout for layout in layouts.values()}
                    mapping.update({master: canonical_notes for master in masters})
                    for slide in slides:
                        mapping[slide] = f"ppt/slides/slide{next_slide}.xml"
                        used_names.add(mapping[slide]); next_slide += 1

                    def copy_part(part, destination):
                        if destination in written or destination in planned:
                            return
                        if part not in source:
                            raise PptxMergeError(f"Parte relacionada ausente: {part!r}.")
                        planned.add(destination)
                        used_names.add(destination)
                        content_types.add_override(destination, source_types.content_type_for(part))
                        rels_path = _relationships_path(part)
                        rewritten = None
                        if rels_path in source:
                            rewritten = _xml(source, rels_path)
                            for relation in rewritten:
                                if str(relation.get("TargetMode") or "").lower() == "external":
                                    continue
                                referred = _resolve_relationship_target(owner_part=part, target=relation.get("Target", ""))
                                if referred not in source:
                                    raise PptxMergeError(f"Parte relacionada ausente: {referred!r}.")
                                mapped = mapping.get(referred)
                                if not mapped:
                                    mapped = _allocate_part_name(referred, used_names, deck_index=batch_index)
                                    mapping[referred] = mapped
                                # Preallocated slide targets include notes backlinks
                                # and internal hyperlinks to a later slide.
                                if referred not in slides:
                                    copy_part(referred, mapped)
                                relation.set("Target", posixpath.relpath(mapped, posixpath.dirname(destination)))
                        copy_member(source, part, destination)
                        if rewritten is not None:
                            write_bytes(_relationships_path(destination), _serialize_xml(rewritten))

                    for slide in slides:
                        destination = mapping[slide]
                        copy_part(slide, destination)
                        rel_id = _allocate_relationship_id(used_rel_ids, start=next_rel)
                        next_rel = int(rel_id.removeprefix("rId")) + 1
                        relation = etree.SubElement(presentation_rels, f"{{{_REL_NS}}}Relationship", Id=rel_id, Type=_SLIDE_REL_TYPE, Target=posixpath.relpath(destination, "ppt"))
                        slide_id = etree.SubElement(slide_ids, f"{{{_P_NS}}}sldId", id=str(next_id))
                        slide_id.set(f"{{{_R_NS}}}id", rel_id)
                        next_id += 1; total_slides += 1

            if canonical_notes:
                for node in list(presentation_rels):
                    if node.get("Type") == _NOTES_MASTER_REL_TYPE:
                        presentation_rels.remove(node)
                rel_id = _allocate_relationship_id(used_rel_ids, start=next_rel)
                etree.SubElement(presentation_rels, f"{{{_REL_NS}}}Relationship", Id=rel_id, Type=_NOTES_MASTER_REL_TYPE, Target=posixpath.relpath(canonical_notes, "ppt"))
                notes_ids = presentation.find(f"{{{_P_NS}}}notesMasterIdLst")
                if notes_ids is None:
                    notes_ids = etree.Element(f"{{{_P_NS}}}notesMasterIdLst")
                    masters = presentation.find(f"{{{_P_NS}}}sldMasterIdLst")
                    presentation.insert(presentation.index(masters) + 1 if masters is not None else 0, notes_ids)
                notes_ids.clear()
                node = etree.SubElement(notes_ids, f"{{{_P_NS}}}notesMasterId")
                node.set(f"{{{_R_NS}}}id", rel_id)
            if app_properties:
                app = etree.fromstring(app_properties)
                namespace = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
                for label, count in (("Slides", total_slides), ("Notes", sum(name.startswith("ppt/notesSlides/") and name.endswith(".xml") for name in written))):
                    node = app.find(f"{{{namespace}}}{label}")
                    if node is not None:
                        node.text = str(count)
                write_bytes("docProps/app.xml", _serialize_xml(app))
            write_bytes(_PRESENTATION_PATH, _serialize_xml(presentation))
            write_bytes(_PRESENTATION_RELS_PATH, _serialize_xml(presentation_rels))
            write_bytes(_CONTENT_TYPES_PATH, content_types.to_bytes())
        if input_bytes + temporary.stat().st_size > _SERIAL_TEMP_BUDGET:
            raise PptxMergeError("Lotes e saída excedem o orçamento temporário de 512 MiB.")
        _validate_serial_package(temporary)
        temporary.replace(output)
        return output
    except (BadZipFile, OSError, etree.XMLSyntaxError) as exc:
        raise PptxMergeError("Falha ao reunir os lotes PPTX por arquivos.") from exc
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _validate_serial_package(path: Path) -> None:
    """Validate CRCs, XML and OPC targets one member at a time, no final DOM."""
    with ZipFile(path) as archive:
        package = _SerialPackage(archive)
        _validate_core_parts(package, label="saída serial")
        for name in archive.namelist():
            if name.endswith((".xml", ".rels")):
                root = _xml(package, name)
                if name.endswith(".rels"):
                    owner = "" if name == "_rels/.rels" else posixpath.join(posixpath.dirname(posixpath.dirname(name)), posixpath.basename(name).removesuffix(".rels"))
                    ids = set()
                    for relation in root:
                        identifier = relation.get("Id")
                        if not identifier or identifier in ids:
                            raise PptxMergeError("ID de relacionamento ausente ou duplicado.")
                        ids.add(identifier)
                        if str(relation.get("TargetMode") or "").lower() != "external":
                            target = _resolve_relationship_target(owner_part=owner, target=relation.get("Target", ""))
                            if target not in package:
                                raise PptxMergeError(f"Relacionamento sem parte de destino: {target!r}.")
            else:
                with archive.open(name) as stream:
                    for _block in iter(lambda: stream.read(1024 * 1024), b""):
                        pass
        types = _ContentTypes.from_files(package)
        if any(part.lstrip("/") not in package for part in types.overrides):
            raise PptxMergeError("Tipo de conteúdo aponta para parte ausente.")


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

    def remove_override(self, part_path: str) -> None:
        part_name = f"/{part_path}"
        for node in list(self.root.findall(f"{{{_CT_NS}}}Override")):
            if node.get("PartName") == part_name:
                self.root.remove(node)
        self.overrides.pop(part_name, None)


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
    destination_content_types = _ContentTypes.from_files(destination)
    if not additional_pptx:
        if len(_notes_master_paths(destination_content_types)) <= 1:
            return public_pptx_bytes(bytes(primary_pptx))
        _register_notes_masters(destination, content_types=destination_content_types)
        destination[_CONTENT_TYPES_PATH] = destination_content_types.to_bytes()
        return public_pptx_bytes(_write_package(destination))
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

    _register_notes_masters(destination, content_types=destination_content_types)
    destination[_CONTENT_TYPES_PATH] = destination_content_types.to_bytes()
    merged = _write_package(destination)
    _validate_openable_presentation(merged)
    return public_pptx_bytes(merged)


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


def _notes_master_paths(content_types: _ContentTypes) -> list[str]:
    return sorted(path.lstrip("/") for path, kind in content_types.overrides.items() if kind == _NOTES_MASTER_CONTENT_TYPE)


def _notes_chain_signature(files: dict[str, bytes], part_path: str, *, active: frozenset[str] = frozenset()) -> str:
    """Compare the complete notes-master design, including related content.

    Part names and relationship IDs are package-local. Resolve them to their
    content before comparing; distinct themes, media or URLs remain distinct.
    Cyclic/custom incompatible chains stop instead of silently converting.
    """
    if part_path in active:
        raise PptxMergeError(f"Cadeia cíclica de notesMaster não suportada: {part_path!r}.")
    if part_path not in files:
        raise PptxMergeError(f"Parte da cadeia de notesMaster ausente: {part_path!r}.")
    active = active | {part_path}
    relationships = []
    ids = {}
    rels_path = _relationships_path(part_path)
    if rels_path in files:
        for relation in _xml(files, rels_path).findall(f"{{{_REL_NS}}}Relationship"):
            attributes = {key: value for key, value in relation.attrib.items() if key not in {"Id", "Target"}}
            external = str(relation.get("TargetMode") or "").lower() == "external"
            attributes["TargetMode"] = "External" if external else "Internal"
            if external:
                target = str(relation.get("Target") or "")
            else:
                target = _notes_chain_signature(
                    files,
                    _resolve_relationship_target(owner_part=part_path, target=str(relation.get("Target") or "")),
                    active=active,
                )
            item = json.dumps([attributes, target], sort_keys=True, ensure_ascii=False)
            relationship_id = str(relation.get("Id") or "")
            if not relationship_id or relationship_id in ids:
                raise PptxMergeError(f"ID de relacionamento inválido/duplicado na cadeia de notesMaster: {part_path!r}.")
            ids[relationship_id] = sha256(item.encode()).hexdigest()
            relationships.append(item)
    payload = files[part_path]
    if part_path.endswith(".xml"):
        root = _xml(files, part_path)
        for node in root.iter():
            for attribute, value in list(node.attrib.items()):
                if attribute.startswith(f"{{{_R_NS}}}"):
                    if value not in ids:
                        raise PptxMergeError(f"Referência sem relacionamento na cadeia de notesMaster: {part_path!r}, {value!r}.")
                    node.set(attribute, ids[value])
        payload = etree.tostring(root, method="c14n")
    return sha256(payload + json.dumps(sorted(relationships), ensure_ascii=False).encode()).hexdigest()


def _register_notes_masters(files: dict[str, bytes], *, content_types: _ContentTypes) -> None:
    """Share one compatible Notes Master, as required by PresentationML.

    This corrects an objective packaging bug for every concatenated export;
    the notes content and all slide/chart data retain their source behavior.
    """
    masters = _notes_master_paths(content_types)
    if not masters:
        return
    root = _xml(files, _PRESENTATION_PATH)
    rels = _xml(files, _PRESENTATION_RELS_PATH)
    relationships = rels.findall(f"{{{_REL_NS}}}Relationship")
    master_relationships = [node for node in relationships if node.get("Type") == _NOTES_MASTER_REL_TYPE]
    referenced = [_resolve_relationship_target(owner_part=_PRESENTATION_PATH, target=str(node.get("Target") or "")) for node in master_relationships]
    canonical = next((path for path in referenced if path in masters), masters[0])
    for master in masters:
        if _xml(files, master).tag != f"{{{_P_NS}}}notesMaster":
            raise PptxMergeError(f"Root XML inválido no notesMaster: {master!r}.")
    if len(masters) > 1:
        signature = _notes_chain_signature(files, canonical)
        for master in masters:
            if _notes_chain_signature(files, master) != signature:
                raise PptxMergeError(
                    f"Notes masters incompatíveis: {canonical!r} e {master!r}; conteúdo e cadeias de fonte/tema precisam de revisão antes da concatenação."
                )
    duplicates = set(masters) - {canonical}
    candidate_themes = set()
    for master in duplicates:
        rels_path = _relationships_path(master)
        if rels_path in files:
            for relation in _xml(files, rels_path).findall(f"{{{_REL_NS}}}Relationship"):
                if relation.get("Type") == _THEME_REL_TYPE:
                    candidate_themes.add(_resolve_relationship_target(owner_part=master, target=str(relation.get("Target") or "")))
    for rels_path in list(files):
        if not rels_path.endswith(".rels") or rels_path == _PRESENTATION_RELS_PATH:
            continue
        if not duplicates:
            break
        owner = posixpath.join(posixpath.dirname(posixpath.dirname(rels_path)), posixpath.basename(rels_path).removesuffix(".rels"))
        rel_root = _xml(files, rels_path)
        changed = False
        for relation in rel_root.findall(f"{{{_REL_NS}}}Relationship"):
            if relation.get("Type") != _NOTES_MASTER_REL_TYPE:
                continue
            target = _resolve_relationship_target(owner_part=owner, target=str(relation.get("Target") or ""))
            if target not in masters:
                raise PptxMergeError(f"Relacionamento de notesMaster sem part registrado: {target!r}.")
            if target in duplicates:
                relation.set("Target", posixpath.relpath(canonical, posixpath.dirname(owner)))
                changed = True
        if changed:
            files[rels_path] = _serialize_xml(rel_root)
    for master in duplicates:
        files.pop(master)
        files.pop(_relationships_path(master), None)
        content_types.remove_override(master)
    # Remove only themes used exclusively by removed notes masters. Preserve
    # all chart/workbook/media parts and the visual slide master/layout chain.
    referenced_parts = set()
    for rels_path in files:
        if not rels_path.endswith(".rels"):
            continue
        owner = "" if rels_path == "_rels/.rels" else posixpath.join(posixpath.dirname(posixpath.dirname(rels_path)), posixpath.basename(rels_path).removesuffix(".rels"))
        for relation in _xml(files, rels_path).findall(f"{{{_REL_NS}}}Relationship"):
            if str(relation.get("TargetMode") or "").lower() != "external":
                referenced_parts.add(_resolve_relationship_target(owner_part=owner, target=str(relation.get("Target") or "")))
    for theme in candidate_themes - referenced_parts:
        files.pop(theme, None)
        files.pop(_relationships_path(theme), None)
        content_types.remove_override(theme)
    used_ids = {str(node.get("Id") or "") for node in relationships}
    canonical_relationship = next((node for node in master_relationships if _resolve_relationship_target(owner_part=_PRESENTATION_PATH, target=str(node.get("Target") or "")) == canonical), None)
    for node in master_relationships:
        if node is not canonical_relationship:
            rels.remove(node)
    if canonical_relationship is None:
        canonical_relationship = etree.SubElement(rels, f"{{{_REL_NS}}}Relationship")
        canonical_relationship.set("Id", _allocate_relationship_id(used_ids, start=_next_relationship_number(used_ids)))
        canonical_relationship.set("Type", _NOTES_MASTER_REL_TYPE)
        canonical_relationship.set("Target", posixpath.relpath(canonical, posixpath.dirname(_PRESENTATION_PATH)))
    relationship_id = str(canonical_relationship.get("Id"))
    id_list = root.find(f"{{{_P_NS}}}notesMasterIdLst")
    if id_list is None:
        id_list = etree.Element(f"{{{_P_NS}}}notesMasterIdLst")
        slide_masters = root.find(f"{{{_P_NS}}}sldMasterIdLst")
        root.insert(root.index(slide_masters) + 1 if slide_masters is not None else 0, id_list)
    master_id = next((node for node in id_list if node.get(f"{{{_R_NS}}}id") == relationship_id), None)
    for node in list(id_list):
        if node is not master_id:
            id_list.remove(node)
    if master_id is None:
        master_id = etree.SubElement(id_list, f"{{{_P_NS}}}notesMasterId")
        master_id.set(f"{{{_R_NS}}}id", relationship_id)
    files[_PRESENTATION_PATH] = _serialize_xml(root)
    files[_PRESENTATION_RELS_PATH] = _serialize_xml(rels)


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
        if (
            str(root.get("type") or "").lower() == "blank"
            or not root.xpath('.//*[local-name()="ph"]')
        ):
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
    if (
        str(layout_root.get("type") or "").lower() != "blank"
        and layout_root.xpath('.//*[local-name()="ph"]')
    ):
        raise PptxMergeError(f"Layout não vazio não suportado: {layout_path!r}.")
    master_path = _related_part_by_type(files, layout_path, _SLIDE_MASTER_REL_TYPE)
    theme_path = _related_part_by_type(files, master_path, _THEME_REL_TYPE)
    roots = [_xml(files, path) for path in (layout_path, master_path, theme_path)]
    # PowerPoint and python-pptx freely regenerate relationship IDs. They are
    # package-local pointers and do not change the layout/master/theme design.
    # Normalizing them prevents a false incompatibility after a valid Office
    # round trip while all visual XML remains part of the signature.
    for root in roots:
        for node in root.xpath('.//*[@r:id]', namespaces={"r": _R_NS}):
            node.set(f"{{{_R_NS}}}id", "rId")
    return tuple(
        sha256(etree.tostring(root, method="c14n")).hexdigest()
        for root in roots
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
