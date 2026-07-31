"""Published Office bundle for the audited FIDC industry revision.

The Streamlit request path only reads an immutable, prebuilt bundle.  It never
starts Node or silently serves a stale/legacy deck.  The bundle is produced by
``scripts/build_fidc_revision_artifacts.mjs`` from the same editorial payload
used by the Industry Data page and is accepted only when payload and file
hashes match its manifest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
from typing import Callable, Iterable
import unicodedata
import zipfile
from xml.etree import ElementTree

from services.industry_taxonomy_review import (
    assert_taxonomy_review_ledger_matches_audit,
    taxonomy_review_audit_digest,
    taxonomy_review_ledger_digest,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data" / "industry_study"
PAYLOAD_NAME = "artifact_payload.json"
BUNDLE_MANIFEST_NAME = "industry_export_bundle.json"
MATERIALIZED_PPTX_NAME = "industry_executive_revised.pptx"
MATERIALIZED_XLSX_NAME = "industry_data_revised.xlsx"
MATERIALIZED_HTML_NAME = "provider_flows_explorer.html"
BUNDLE_SCHEMA = "fidc_revision_export_bundle_v2"
PAYLOAD_SCHEMA = "fidc_revision_artifact_payload_v7"
EXPECTED_SLIDES = 33
EXPECTED_SLIDE_SEQUENCE: tuple[tuple[str, ...], ...] = (
    ("industria de fidcs",),
    ("escala da industria", "r$ 821,0 bi", "r$ 13,780 tri"),
    ("ofertas encerradas", "cvm e anbima", "valor encerrado por instrumento"),
    ("emissoes por categoria anbima", "emissoes por setor"),
    ("taxonomia analitica", "precatorios e/ou acoes judiciais", "multicedente/multisacado"),
    ("reclassificacao de adquirencia",),
    ("carteira por tipo de recebivel",),
    ("prestadores", "ranking e concentracao"),
    ("ranking", "top 20 fidcs"),
    ("top fundos e originadores", "fomento mercantil"),
    ("top fundos e originadores", "agro, industria e comercio"),
    ("top fundos e originadores", "financeiro"),
    ("top fundos e originadores", "outros"),
    ("curadoria", "fundos flagship"),
    ("carteira 1", "47 cnpjs flagship"),
    ("carteira 1", "taxonomia analitica"),
    ("concentracao das monoestruturas",),
    ("ofertas encerradas", "volume e ticket"),
    ("distribuicao do ticket",),
    ("ofertas", "volume e regime"),
    ("top 15", "ofertas encerradas"),
    ("top 15", "historico"),
    ("principais conclusoes",),
    ("prestadores", "evolucao e ranking"),
    ("prestadores", "lideranca explicada"),
    ("market share", "administracao"),
    ("market share", "gestao"),
    ("market share", "custodia"),
    ("apendice", "market share", "administracao"),
    ("apendice", "market share", "gestao"),
    ("apendice", "market share", "custodia"),
    ("base investidora",),
    ("distribuicao por numero de cotistas",),
)
if len(EXPECTED_SLIDE_SEQUENCE) != EXPECTED_SLIDES:  # pragma: no cover
    raise RuntimeError("contrato ordinal do PPTX não fecha 33 slides")
REQUIRED_WORKBOOK_SHEETS = {
    "QA Inadimplência",
    "Base por fundo-CNPJ",
    "Base competência-CNPJ",
    "Checks revisão",
    "Concentração de monoestruturas",
    "Market share por subtipo",
    "Top 20 FIDCs",
    "Top 20 Outros",
    "Curadoria Top 20",
    "Curadoria flagship",
    "Carteira 1 curadoria",
    "Carteira 1 vs flagships",
    "Carteira 1 evolução",
    "Taxonomia por nível",
    "Comparativos históricos",
    "Ranking prestadores",
    "Inadimplência por recebível",
    "Histórico inad. coorte",
    "Reconciliação Tabelas I-II",
    "Ranking independentes",
    "FIDCs por banco",
    "Detalhe coorte bancos",
    "Atribuição prestadores",
    "Fluxos prestadores",
    "Migração CBSF",
    "Taxonomia adquirência",
    "Adquirência reclass.",
    "Curadoria Cartão",
    "Top 20 por Tipo ANBIMA",
    "Auditoria Top 20 Tipo",
    "Curadoria Outros Top 100",
    "Dispersão inadimplência",
    "Ofertas encerradas",
    "Comparativo renda fixa",
    "Regime de colocação",
    "Histograma ofertas",
    "Crédito Privado Ampliado",
    "Originadores 2026",
    "Top 15 ofertas",
    "Validação emissões",
    "Emissões por categoria",
    "Público-alvo ofertas",
    "Principais conclusões",
    "Curadoria Atlântico",
    "Série Atlântico",
    "Universo elegível",
    "FICs excluídos",
    "Decisões do ledger",
}


class RevisionExportUnavailable(RuntimeError):
    """Raised when the published revision bundle is missing or inconsistent."""


@dataclass(frozen=True)
class RevisionExportStatus:
    payload_path: str
    payload_exists: bool
    payload_schema: str
    latest_complete: str
    bundle_manifest_path: str
    bundle_exists: bool
    bundle_id: str
    bundle_valid: bool
    validation_error: str
    pptx_path: str
    pptx_exists: bool
    xlsx_path: str
    xlsx_exists: bool
    html_path: str
    html_exists: bool
    artifact_runtime_available: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _ValidatedBundle:
    manifest: dict[str, object]
    pptx_path: Path
    pptx_bytes: bytes
    xlsx_path: Path
    xlsx_bytes: bytes
    html_path: Path
    html_bytes: bytes


def revision_dir(data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    return Path(data_dir).resolve() / "generated_revision"


def revision_payload_path(data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    return revision_dir(data_dir) / PAYLOAD_NAME


def revision_bundle_manifest_path(data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    configured = os.environ.get("FIDC_EXPORT_MANIFEST", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return revision_dir(data_dir) / BUNDLE_MANIFEST_NAME


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _valid_zip(payload: bytes, required_member: str) -> bool:
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            return required_member in archive.namelist()
    except (OSError, zipfile.BadZipFile):
        return False


def _chart_members(archive: zipfile.ZipFile) -> list[str]:
    return [
        name
        for name in archive.namelist()
        if "/charts/chart" in name and name.endswith(".xml")
    ]


def _normalized_slide_text(payload: bytes) -> str:
    """Return accent-insensitive visible text from one slide XML part."""

    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return ""
    visible = " ".join(
        node.text or ""
        for node in root.iter()
        if node.tag.endswith("}t")
    )
    normalized = unicodedata.normalize("NFKD", visible.casefold())
    return " ".join(
        "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        ).split()
    )


def _slide_xml_containing(
    archive: zipfile.ZipFile,
    *tokens: str,
) -> bytes:
    expected = [
        "".join(
            character
            for character in unicodedata.normalize("NFKD", token.casefold())
            if not unicodedata.combining(character)
        )
        for token in tokens
    ]
    for name in sorted(
        (
            item
            for item in archive.namelist()
            if item.startswith("ppt/slides/slide")
            and item.endswith(".xml")
            and "/_rels/" not in item
        ),
        key=lambda item: int(Path(item).stem.removeprefix("slide")),
    ):
        payload = archive.read(name)
        visible = _normalized_slide_text(payload)
        if all(token in visible for token in expected):
            return payload
    raise RevisionExportUnavailable(
        "PPTX revisado sem slide esperado: " + " / ".join(tokens)
    )


_PML = "http://schemas.openxmlformats.org/presentationml/2006/main"
_DML = "http://schemas.openxmlformats.org/drawingml/2006/main"
_DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _ordered_slide_parts(archive: zipfile.ZipFile) -> list[str]:
    presentation = ElementTree.fromstring(archive.read("ppt/presentation.xml"))
    relationships = ElementTree.fromstring(
        archive.read("ppt/_rels/presentation.xml.rels")
    )
    targets = {
        node.attrib.get("Id", ""): node.attrib.get("Target", "")
        for node in relationships.findall(f"{{{_PKG_REL}}}Relationship")
        if node.attrib.get("Type", "").endswith("/slide")
    }
    ordered: list[str] = []
    slide_ids = presentation.findall(f".//{{{_PML}}}sldId")
    if len({node.attrib.get("id") for node in slide_ids}) != len(slide_ids):
        raise RevisionExportUnavailable("PPTX revisado contém sldId duplicado")
    for node in slide_ids:
        relation_id = node.attrib.get(f"{{{_DOC_REL}}}id", "")
        target = targets.get(relation_id, "")
        if not target:
            raise RevisionExportUnavailable(
                "PPTX revisado contém relação de slide ausente"
            )
        part = (
            target.lstrip("/")
            if target.startswith("/")
            else posixpath.normpath(posixpath.join("ppt", target))
        )
        slide_root = ElementTree.fromstring(archive.read(part))
        if str(slide_root.attrib.get("show", "1")).casefold() in {"0", "false"}:
            raise RevisionExportUnavailable("PPTX revisado contém slide oculto")
        ordered.append(part)
    if len(set(ordered)) != len(ordered):
        raise RevisionExportUnavailable("PPTX revisado contém relação de slide duplicada")
    physical = {
        name
        for name in archive.namelist()
        if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
    }
    if set(ordered) != physical:
        raise RevisionExportUnavailable(
            "PPTX revisado contém slide órfão ou fora da sequência"
        )
    return ordered


def _xfrm_bbox(node: ElementTree.Element | None) -> tuple[int, int, int, int] | None:
    if node is None:
        return None
    offset = node.find(f"{{{_DML}}}off")
    extent = node.find(f"{{{_DML}}}ext")
    if offset is None or extent is None:
        return None
    return (
        int(offset.attrib["x"]),
        int(offset.attrib["y"]),
        int(extent.attrib["cx"]),
        int(extent.attrib["cy"]),
    )


def _overlap(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
) -> bool:
    left_x, left_y, left_w, left_h = left
    right_x, right_y, right_w, right_h = right
    return (
        max(left_x, right_x) < min(left_x + left_w, right_x + right_w)
        and max(left_y, right_y) < min(left_y + left_h, right_y + right_h)
    )


def _validate_native_table_slide(
    archive: zipfile.ZipFile,
    slide_number: int,
    *,
    expected_dimensions: tuple[tuple[int, int], ...],
    canvas: tuple[int, int],
) -> None:
    root = ElementTree.fromstring(
        archive.read(f"ppt/slides/slide{slide_number}.xml")
    )
    tables: list[tuple[tuple[int, int, int, int], tuple[int, int]]] = []
    for frame in root.findall(f".//{{{_PML}}}graphicFrame"):
        table = frame.find(f".//{{{_DML}}}tbl")
        if table is None:
            continue
        bbox = _xfrm_bbox(frame.find(f"{{{_PML}}}xfrm"))
        if bbox is None:
            raise RevisionExportUnavailable(
                f"slide {slide_number} contém tabela nativa sem posição"
            )
        rows = len(table.findall(f"{{{_DML}}}tr"))
        columns = len(table.findall(f"{{{_DML}}}tblGrid/{{{_DML}}}gridCol"))
        tables.append((bbox, (rows, columns)))
    if tuple(dimensions for _, dimensions in tables) != expected_dimensions:
        raise RevisionExportUnavailable(
            f"slide {slide_number} não contém as tabelas Office esperadas"
        )
    canvas_width, canvas_height = canvas
    for bbox, _ in tables:
        left, top, width, height = bbox
        if (
            left < 0
            or top < 0
            or width <= 0
            or height <= 0
            or left + width > canvas_width
            or top + height > canvas_height
        ):
            raise RevisionExportUnavailable(
                f"slide {slide_number} contém tabela fora do canvas"
            )
    shape_bboxes: list[tuple[int, int, int, int]] = []
    for shape in root.findall(f".//{{{_PML}}}sp"):
        bbox = _xfrm_bbox(shape.find(f"{{{_PML}}}spPr/{{{_DML}}}xfrm"))
        if bbox is not None:
            shape_bboxes.append(bbox)
    if any(
        _overlap(shape_bbox, table_bbox)
        for shape_bbox in shape_bboxes
        for table_bbox, _ in tables
    ):
        raise RevisionExportUnavailable(
            f"slide {slide_number} contém shape sobreposto à tabela nativa"
        )


def _contains_blocked_rgb_color(
    xml_parts: Iterable[bytes],
    blocked_color: str,
) -> bool:
    """Match a blocked RGB value only in DrawingML color elements."""

    blocked = str(blocked_color).strip().removeprefix("#").upper()
    for xml in xml_parts:
        root = ElementTree.fromstring(xml)
        for element in root.iter():
            local_name = str(element.tag).rsplit("}", 1)[-1]
            if local_name not in {"srgbClr", "sysClr"}:
                continue
            values = (
                str(element.attrib.get("val") or "").removeprefix("#").upper(),
                str(element.attrib.get("lastClr") or "").removeprefix("#").upper(),
            )
            if blocked in values:
                return True
    return False


def validate_revision_pptx(payload: bytes) -> None:
    """Validate the visual contract directly in the exported OOXML."""

    if not _valid_zip(payload, "ppt/presentation.xml"):
        raise RevisionExportUnavailable("PPTX revisado inválido ou corrompido")
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        slides = [
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide")
            and name.endswith(".xml")
            and "/_rels/" not in name
        ]
        if len(slides) != EXPECTED_SLIDES:
            raise RevisionExportUnavailable(
                f"PPTX revisado deveria conter {EXPECTED_SLIDES} slides; contém {len(slides)}"
            )
        ordered_slides = _ordered_slide_parts(archive)
        if len(ordered_slides) != EXPECTED_SLIDES:
            raise RevisionExportUnavailable(
                f"sequência do PPTX deveria conter {EXPECTED_SLIDES} slides; contém {len(ordered_slides)}"
            )
        for slide_number, (slide_path, expected_tokens) in enumerate(
            zip(ordered_slides, EXPECTED_SLIDE_SEQUENCE, strict=True),
            start=1,
        ):
            slide_text = _normalized_slide_text(archive.read(slide_path))
            missing_tokens = [
                token for token in expected_tokens if token not in slide_text
            ]
            if missing_tokens:
                raise RevisionExportUnavailable(
                    f"slide {slide_number} viola o contrato ordinal: "
                    + ", ".join(missing_tokens)
                )
        scale_slide = _slide_xml_containing(archive, "ESCALA DA INDÚSTRIA")
        if scale_slide.count(b"<c:chart") < 2:
            raise RevisionExportUnavailable(
                "slide de escala deve conter dois gráficos nativos do Office"
            )
        if "saldo fic" in _normalized_slide_text(scale_slide):
            raise RevisionExportUnavailable(
                "slide de escala voltou a exibir FIC no gráfico de PL"
            )
        scale_slide_root = ElementTree.fromstring(scale_slide)
        if str(scale_slide_root.attrib.get("show", "1")).casefold() in {"0", "false"}:
            raise RevisionExportUnavailable("slide de escala está oculto")
        presentation = ElementTree.fromstring(archive.read("ppt/presentation.xml"))
        slide_size = presentation.find(f"{{{_PML}}}sldSz")
        if slide_size is None:
            raise RevisionExportUnavailable("PPTX revisado sem dimensão de slide")
        canvas = (int(slide_size.attrib["cx"]), int(slide_size.attrib["cy"]))
        _validate_native_table_slide(
            archive,
            4,
            expected_dimensions=((8, 11),),
            canvas=canvas,
        )
        for ranking_slide_number in range(10, 14):
            _validate_native_table_slide(
                archive,
                ranking_slide_number,
                expected_dimensions=((16, 4), (16, 4)),
                canvas=canvas,
            )
        _validate_native_table_slide(
            archive,
            21,
            expected_dimensions=((16, 10), (16, 10)),
            canvas=canvas,
        )
        _validate_native_table_slide(
            archive,
            22,
            expected_dimensions=((16, 9), (16, 9)),
            canvas=canvas,
        )
        office_xml_parts = [
            archive.read(name)
            for name in archive.namelist()
            if name.endswith(".xml") and (
                name.startswith("ppt/slides/")
                or name.startswith("ppt/theme/")
                or "/charts/chart" in name
            )
        ]
        if _contains_blocked_rgb_color(office_xml_parts, "172A3A"):
            raise RevisionExportUnavailable("PPTX revisado contém a cor navy bloqueada")
        chart_xml = b"".join(archive.read(name) for name in _chart_members(archive))
        if b'<c:smooth val="1"' in chart_xml or b'<c:smooth val="true"' in chart_xml:
            raise RevisionExportUnavailable("PPTX revisado contém linha suavizada")
        marker_tokens = chart_xml.replace(b" />", b"/>").split(b"<c:marker>")[1:]
        for token in marker_tokens:
            marker = token.split(b"</c:marker>", 1)[0]
            if b'<c:symbol val="none"' not in marker:
                raise RevisionExportUnavailable("PPTX revisado contém marker ativo")
        ranking_slide = _slide_xml_containing(
            archive, "PRESTADORES", "EVOLUÇÃO E RANKING"
        )
        if ranking_slide.count(b"<a:tbl>") != 0:
            raise RevisionExportUnavailable(
                "slide combinado de prestadores deve conter apenas gráficos"
            )
        if ranking_slide.count(b"<c:chart") < 6:
            raise RevisionExportUnavailable(
                "slide combinado de prestadores deve conter ao menos seis gráficos nativos do Office"
            )
        offers_slide = _slide_xml_containing(
            archive, "OFERTAS ENCERRADAS", "DISTRIBUIÇÃO DO TICKET"
        )
        if offers_slide.count(b"<c:chart") < 3:
            raise RevisionExportUnavailable(
                "slide de distribuição de ofertas deve conter três gráficos nativos do Office"
            )
        placement_slide = _slide_xml_containing(archive, "OFERTAS", "VOLUME E REGIME")
        if placement_slide.count(b"<c:chart") < 4:
            raise RevisionExportUnavailable(
                "slide de volume e regime deve conter quatro gráficos nativos do Office"
            )
        combined_market_slide = _slide_xml_containing(
            archive, "OFERTAS ENCERRADAS", "CVM E ANBIMA"
        )
        if combined_market_slide.count(b"<c:chart") != 2:
            raise RevisionExportUnavailable(
                "slide conjunto CVM e ANBIMA deve conter dois gráficos nativos do Office"
            )
        if combined_market_slide.count(b"<a:tbl>") != 0:
            raise RevisionExportUnavailable(
                "slide conjunto CVM e ANBIMA não deve conter tabela nativa"
            )
        taxonomy_market_slide = _slide_xml_containing(
            archive, "EMISSÕES POR CATEGORIA ANBIMA"
        )
        if taxonomy_market_slide.count(b"<c:chart") != 2:
            raise RevisionExportUnavailable(
                "slide de emissões por categoria deve conter dois gráficos nativos do Office"
            )
        if taxonomy_market_slide.count(b"<a:tbl>") != 1:
            raise RevisionExportUnavailable(
                "slide de emissões por categoria deve conter uma tabela nativa"
            )
        top15_offers_slide = _slide_xml_containing(
            archive, "TOP 15", "IBBA PARTICIPOU", "JAN–JUN/26"
        )
        if top15_offers_slide.count(b"<a:tbl>") != 2:
            raise RevisionExportUnavailable(
                "slide de maiores ofertas deve conter duas tabelas nativas do Office"
            )
        _slide_xml_containing(archive, "PRINCIPAIS CONCLUSÕES")


def validate_revision_xlsx(payload: bytes) -> None:
    if not _valid_zip(payload, "xl/workbook.xml"):
        raise RevisionExportUnavailable("XLSX revisado inválido ou corrompido")
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8", errors="ignore")
    missing = sorted(sheet for sheet in REQUIRED_WORKBOOK_SHEETS if sheet not in workbook_xml)
    if missing:
        raise RevisionExportUnavailable(
            "XLSX revisado sem abas obrigatórias: " + ", ".join(missing)
        )


def validate_revision_html(payload: bytes) -> None:
    """Validate the self-contained provider-flow explorer served by the app."""

    if not payload:
        raise RevisionExportUnavailable("HTML interativo de fluxos está vazio")
    if len(payload) > 2 * 1024 * 1024:
        raise RevisionExportUnavailable("HTML interativo de fluxos excede 2 MB")
    try:
        document = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RevisionExportUnavailable(
            "HTML interativo de fluxos não está em UTF-8"
        ) from exc
    required_tokens = (
        "<!doctype html",
        'id="provider-flow-explorer"',
        "data-chart",
        "<script",
        "Dez/24",
        "Administração",
        "Gestão",
        "Custódia",
        "CBSF / REAG",
        "Carteira 1 · evolução pela taxonomia reclassificada",
        "Carteira 1 vs. 47 CNPJs flagship",
        "carteira_1_taxonomy_compact_v1",
    )
    missing = [
        token
        for token in required_tokens
        if token.casefold() not in document.casefold()
    ]
    if missing:
        raise RevisionExportUnavailable(
            "HTML interativo de fluxos incompleto: " + ", ".join(missing)
        )
    if "fetch(" in document:
        raise RevisionExportUnavailable(
            "HTML interativo de fluxos depende de carregamento externo"
        )


def _candidate_paths(
    data_dir: Path,
    *,
    materialized_name: str,
    output_name: str,
    env_name: str,
) -> tuple[Path, ...]:
    explicit = os.environ.get(env_name, "").strip()
    candidates = [
        revision_dir(data_dir) / materialized_name,
        ROOT / "outputs" / output_name,
    ]
    if explicit:
        candidates.insert(0, Path(explicit).expanduser().resolve())
    return tuple(dict.fromkeys(path.resolve() for path in candidates))


def revision_pptx_candidates(data_dir: Path = DEFAULT_DATA_DIR) -> tuple[Path, ...]:
    return _candidate_paths(
        Path(data_dir),
        materialized_name=MATERIALIZED_PPTX_NAME,
        output_name="Industria_FIDC_Executivo_202607_revisado.pptx",
        env_name="FIDC_REVISION_PPTX",
    )


def revision_xlsx_candidates(data_dir: Path = DEFAULT_DATA_DIR) -> tuple[Path, ...]:
    return _candidate_paths(
        Path(data_dir),
        materialized_name=MATERIALIZED_XLSX_NAME,
        output_name="Industria_FIDC_Dados_202607_revisado.xlsx",
        env_name="FIDC_REVISION_XLSX",
    )


def revision_html_candidates(data_dir: Path = DEFAULT_DATA_DIR) -> tuple[Path, ...]:
    return _candidate_paths(
        Path(data_dir),
        materialized_name=MATERIALIZED_HTML_NAME,
        output_name="Industria_FIDC_Fluxos_Prestadores_202607.html",
        env_name="FIDC_REVISION_HTML",
    )


def _artifact_node_modules() -> Path | None:
    candidates: list[Path] = []
    configured = os.environ.get("CODEX_NODE_MODULES", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            ROOT / "node_modules",
            Path.home()
            / ".cache"
            / "codex-runtimes"
            / "codex-primary-runtime"
            / "dependencies"
            / "node"
            / "node_modules",
        ]
    )
    for candidate in candidates:
        if (candidate / "@oai" / "artifact-tool" / "package.json").exists():
            return candidate.resolve()
    return None


def artifact_runtime_available() -> bool:
    """Diagnostic only; the application request path never invokes the runtime."""

    return bool(shutil.which("node") and _artifact_node_modules())


def _payload_metadata(path: Path) -> tuple[str, str]:
    if not path.exists():
        return "", ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", ""
    return str(payload.get("schema_version") or ""), str(payload.get("latest_complete") or "")


def _taxonomy_review_ledger_path(
    data_dir: Path,
    payload: dict[str, object] | None,
) -> Path:
    """Resolve the payload-declared ledger inside the selected industry data dir."""

    meta = dict((payload or {}).get("taxonomy_review_meta") or {})
    configured = str(
        meta.get("ledger_path") or "taxonomy_review_actions.csv"
    ).strip()
    raw_path = Path(configured).expanduser()
    if raw_path.is_absolute():
        return raw_path.resolve()

    parts = raw_path.parts
    if "industry_study" in parts:
        anchor = parts.index("industry_study")
        suffix = parts[anchor + 1 :]
        raw_path = Path(*suffix) if suffix else Path("taxonomy_review_actions.csv")

    resolved_data_dir = Path(data_dir).resolve()
    resolved = (resolved_data_dir / raw_path).resolve()
    try:
        resolved.relative_to(resolved_data_dir)
    except ValueError as exc:
        raise RevisionExportUnavailable(
            "caminho do ledger de taxonomia está fora do diretório de dados"
        ) from exc
    return resolved


def _taxonomy_review_audit_path(
    data_dir: Path,
    payload: dict[str, object] | None,
) -> Path:
    """Resolve the payload-declared audit inside the selected industry data dir."""

    meta = dict((payload or {}).get("taxonomy_review_meta") or {})
    configured = str(
        meta.get("audit_path") or "taxonomy_review_audit.csv"
    ).strip()
    raw_path = Path(configured).expanduser()
    if raw_path.is_absolute():
        return raw_path.resolve()
    parts = raw_path.parts
    if "industry_study" in parts:
        anchor = parts.index("industry_study")
        suffix = parts[anchor + 1 :]
        raw_path = Path(*suffix) if suffix else Path("taxonomy_review_audit.csv")
    resolved_data_dir = Path(data_dir).resolve()
    resolved = (resolved_data_dir / raw_path).resolve()
    try:
        resolved.relative_to(resolved_data_dir)
    except ValueError as exc:
        raise RevisionExportUnavailable(
            "caminho da auditoria de taxonomia está fora do diretório de dados"
        ) from exc
    return resolved


def _taxonomy_review_signature(data_dir: Path, payload: dict[str, object] | None) -> str:
    ledger_path = _taxonomy_review_ledger_path(data_dir, payload)
    audit_path = _taxonomy_review_audit_path(data_dir, payload)
    return (
        f"{taxonomy_review_ledger_digest(ledger_path)}:"
        f"{taxonomy_review_audit_digest(audit_path)}"
    )


def _matching_candidate(
    paths: Iterable[Path],
    expected: dict[str, object],
    validator: Callable[[bytes], None],
) -> tuple[Path, bytes]:
    expected_hash = str(expected.get("sha256") or "")
    expected_size = int(expected.get("bytes") or 0)
    for path in paths:
        if not path.exists():
            continue
        payload = path.read_bytes()
        if expected_size and len(payload) != expected_size:
            continue
        if not expected_hash or _sha256(payload) != expected_hash:
            continue
        validator(payload)
        return path, payload
    raise RevisionExportUnavailable("arquivo publicado não corresponde ao hash do bundle")


def _load_validated_bundle(data_dir: Path = DEFAULT_DATA_DIR) -> _ValidatedBundle:
    data_dir = Path(data_dir).resolve()
    payload_path = revision_payload_path(data_dir)
    manifest_path = revision_bundle_manifest_path(data_dir)
    if not payload_path.exists():
        raise RevisionExportUnavailable(f"payload revisado ausente: {payload_path}")
    if not manifest_path.exists():
        raise RevisionExportUnavailable(f"manifest do bundle ausente: {manifest_path}")
    payload_raw = payload_path.read_bytes()
    try:
        payload = json.loads(payload_raw)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RevisionExportUnavailable(f"bundle revisado ilegível: {exc}") from exc
    if manifest.get("schema_version") != BUNDLE_SCHEMA:
        raise RevisionExportUnavailable("schema do bundle revisado incompatível")
    payload_hash = _sha256(payload_raw)
    if manifest.get("payload_sha256") != payload_hash:
        raise RevisionExportUnavailable("payload mudou após a publicação do bundle")
    if manifest.get("source_signature") != payload_hash:
        raise RevisionExportUnavailable("assinatura de fontes do bundle não reconcilia")
    if manifest.get("payload_schema") != payload.get("schema_version"):
        raise RevisionExportUnavailable("schema do payload diverge do bundle")
    if payload.get("schema_version") != PAYLOAD_SCHEMA:
        raise RevisionExportUnavailable("schema do payload revisado incompatível")
    if manifest.get("latest_complete") != payload.get("latest_complete"):
        raise RevisionExportUnavailable("competência do bundle diverge do payload")
    taxonomy_meta = dict(payload.get("taxonomy_review_meta") or {})
    if taxonomy_meta:
        published_taxonomy_digest = str(
            taxonomy_meta.get("ledger_sha256") or ""
        ).strip()
        published_audit_digest = str(
            taxonomy_meta.get("audit_sha256") or ""
        ).strip()
        if not published_taxonomy_digest or not published_audit_digest:
            raise RevisionExportUnavailable(
                "payload revisado não registra os hashes da curadoria de taxonomia"
            )
        ledger_path = _taxonomy_review_ledger_path(data_dir, payload)
        audit_path = _taxonomy_review_audit_path(data_dir, payload)
        try:
            assert_taxonomy_review_ledger_matches_audit(
                ledger_path,
                audit_path,
            )
        except ValueError as exc:
            raise RevisionExportUnavailable(
                "curadoria ou auditoria de Outros mudou após a publicação; "
                "ledger e auditoria são inconsistentes: "
                f"{exc}"
            ) from exc
        if (
            taxonomy_review_ledger_digest(ledger_path)
            != published_taxonomy_digest
            or taxonomy_review_audit_digest(audit_path)
            != published_audit_digest
        ):
            raise RevisionExportUnavailable(
                "curadoria ou auditoria de Outros mudou após a publicação; regenere o bundle"
            )
    pptx_path, pptx_bytes = _matching_candidate(
        revision_pptx_candidates(data_dir),
        dict(manifest.get("pptx") or {}),
        validate_revision_pptx,
    )
    xlsx_path, xlsx_bytes = _matching_candidate(
        revision_xlsx_candidates(data_dir),
        dict(manifest.get("xlsx") or {}),
        validate_revision_xlsx,
    )
    html_path, html_bytes = _matching_candidate(
        revision_html_candidates(data_dir),
        dict(manifest.get("html") or {}),
        validate_revision_html,
    )
    return _ValidatedBundle(
        manifest=manifest,
        pptx_path=pptx_path,
        pptx_bytes=pptx_bytes,
        xlsx_path=xlsx_path,
        xlsx_bytes=xlsx_bytes,
        html_path=html_path,
        html_bytes=html_bytes,
    )


def revision_export_signature(data_dir: Path = DEFAULT_DATA_DIR) -> str:
    """Cache key for the immutable bundle and its live taxonomy ledger."""

    data_dir = Path(data_dir).resolve()
    manifest_path = revision_bundle_manifest_path(data_dir)
    manifest_digest = (
        _sha256(manifest_path.read_bytes())
        if manifest_path.exists()
        else f"missing:{manifest_path}"
    )
    payload: dict[str, object] = {}
    payload_path = revision_payload_path(data_dir)
    if payload_path.exists():
        try:
            loaded = json.loads(payload_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, json.JSONDecodeError):
            payload = {}
    taxonomy_digest = _taxonomy_review_signature(data_dir, payload)
    return f"{manifest_digest}:{taxonomy_digest}"


def get_revision_export_status(data_dir: Path = DEFAULT_DATA_DIR) -> RevisionExportStatus:
    data_dir = Path(data_dir).resolve()
    payload_path = revision_payload_path(data_dir)
    manifest_path = revision_bundle_manifest_path(data_dir)
    schema, latest = _payload_metadata(payload_path)
    bundle_id = ""
    pptx_path = revision_pptx_candidates(data_dir)[0]
    xlsx_path = revision_xlsx_candidates(data_dir)[0]
    html_path = revision_html_candidates(data_dir)[0]
    error = ""
    valid = False
    try:
        bundle = _load_validated_bundle(data_dir)
        bundle_id = str(bundle.manifest.get("bundle_id") or "")
        pptx_path = bundle.pptx_path
        xlsx_path = bundle.xlsx_path
        html_path = bundle.html_path
        valid = True
    except RevisionExportUnavailable as exc:
        error = str(exc)
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                bundle_id = str(manifest.get("bundle_id") or "")
            except (OSError, json.JSONDecodeError):
                pass
    return RevisionExportStatus(
        payload_path=str(payload_path),
        payload_exists=payload_path.exists(),
        payload_schema=schema,
        latest_complete=latest,
        bundle_manifest_path=str(manifest_path),
        bundle_exists=manifest_path.exists(),
        bundle_id=bundle_id,
        bundle_valid=valid,
        validation_error=error,
        pptx_path=str(pptx_path),
        pptx_exists=pptx_path.exists(),
        xlsx_path=str(xlsx_path),
        xlsx_exists=xlsx_path.exists(),
        html_path=str(html_path),
        html_exists=html_path.exists(),
        artifact_runtime_available=artifact_runtime_available(),
    )


def build_revision_pptx_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    return _load_validated_bundle(data_dir).pptx_bytes


def build_revision_xlsx_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    return _load_validated_bundle(data_dir).xlsx_bytes


def build_revision_html_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    return _load_validated_bundle(data_dir).html_bytes


__all__ = [
    "BUNDLE_SCHEMA",
    "MATERIALIZED_HTML_NAME",
    "RevisionExportStatus",
    "RevisionExportUnavailable",
    "artifact_runtime_available",
    "build_revision_pptx_bytes",
    "build_revision_xlsx_bytes",
    "build_revision_html_bytes",
    "get_revision_export_status",
    "revision_bundle_manifest_path",
    "revision_export_signature",
    "revision_payload_path",
    "revision_html_candidates",
    "validate_revision_html",
    "validate_revision_pptx",
    "validate_revision_xlsx",
]
