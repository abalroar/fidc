"""Published Office bundle for the audited FIDC industry revision.

The Streamlit request path only reads an immutable, prebuilt bundle.  It never
starts Node or silently serves a stale/legacy deck.  The bundle is produced by
``scripts/build_fidc_revision_artifacts.mjs`` from the same editorial payload
used by the Industry Data page and is accepted only when payload and file
hashes match its manifest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import posixpath
import re
import shutil
from threading import RLock
from typing import Callable, Iterable, Mapping
import unicodedata
import zipfile
from xml.etree import ElementTree

from scripts.patch_industry_workbook_operational_cache import validate_workbook_caches
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
MATERIALIZED_PORTFOLIO_XLSX_NAME = "carteira_101_flagships.xlsx"
MATERIALIZED_TOP100_XLSX_NAME = "top100_fidcs_middle_market.xlsx"
MATERIALIZED_HTML_NAME = "provider_flows_explorer.html"
BUNDLE_SCHEMA = "fidc_revision_export_bundle_v5"
PAYLOAD_SCHEMA = "fidc_revision_artifact_payload_v11"
TOP100_PLUS2_ADDITIONAL_CNPJS = {"44302112000172", "61669748000176"}
# The executive deck carries a stable topic order. Documentary rankings and
# structural detail remain in the audited workbooks, outside this contract.
ISSUANCE_TAXONOMY_TABLE_DIMENSIONS: tuple[tuple[int, int], ...] = ()
STRUCTURAL_MVP_SLIDE_SEQUENCE: tuple[tuple[str, ...], ...] = ()
TYPE_RANKING_SLIDE_SEQUENCE: tuple[tuple[str, ...], ...] = ()
CURRENT_TOP15_SLIDE_SEQUENCE: tuple[tuple[str, ...], ...] = ()
HISTORICAL_TOP15_SLIDE_SEQUENCE: tuple[tuple[str, ...], ...] = ()
HISTORICAL_TOP15_TABLE_DIMENSIONS: tuple[tuple[int, int], ...] = ()
CURRENT_TOP15_SLIDE_NUMBERS: tuple[int, ...] = ()
HISTORICAL_TOP15_SLIDE_NUMBERS: tuple[int, ...] = ()
EXPECTED_SLIDE_IDS: tuple[str, ...] = (
    "cover", "industry_scale", "annual_issuance", "issuance_taxonomy_summary",
    "analytical_taxonomy", "acquiring", "receivables", "offers_volume_ticket",
    "offers_ticket_distribution", "offers_placement_regime", "conclusions",
    "provider_history", "provider_ranking", "investor_base", "holder_distribution",
)
EXPECTED_SLIDE_SEQUENCE: tuple[tuple[str, ...], ...] = (
    ("industria de fidcs", "dados de referencia"),
    ("escala da industria",),
    ("emissoes de fidcs e outros instrumentos", "yoy"),
    ("emissoes por setor",),
    ("composicao da industria", "pl ex-fic"),
    ("adquirencia na industria de fidcs",),
    ("evolucao dos recebiveis", "tabela ii"),
    ("volume e ticket das ofertas",),
    ("concentracao das ofertas por ticket",),
    ("garantia firme", "melhores esforcos"),
    ("principais conclusoes",),
    ("ranking de prestadores", "ranking geral"),
    ("prestadores", "ranking e concentracao"),
    ("publico-alvo e base investidora",),
    ("distribuicao por numero de cotistas",),
)
EXPECTED_SLIDES = len(EXPECTED_SLIDE_SEQUENCE)
if len(EXPECTED_SLIDE_IDS) != EXPECTED_SLIDES:
    raise RuntimeError("contrato compacto de slides inconsistente")

BLOCKED_PPTX_AUDIENCE_COPY: tuple[str, ...] = (
    "clique para inserir",
    "click to add",
    "atualizar para",
    "copilot",
    "claude code",
    "prompt antigo",
)
BLOCKED_PUBLISHED_TEXT_MARKERS: tuple[str, ...] = (
    "√",
    "\ufffd",
)
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
    "Risco estrutural ativos",
    "Risco estrutural taxonomia",
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
    "Auditoria emissões",
    "Remuneração-alvo",
    "Cobertura emissões",
    "Curadoria perfis",
    "Validação emissões",
    "Emissões por categoria",
    "Público-alvo ofertas",
    "Principais conclusões",
    "Curadoria Atlântico",
    "Série Atlântico",
    "Cedentes · Leia-me",
    "Cedentes · Top 500",
    "Cedentes · competência",
    "Cedentes · sem cedente",
    "Cedentes · evolução",
    "Cedentes · presença",
    "Cedentes · cobertura",
    "Cedentes · PL segmento",
    "Cedentes · cadastro",
    "Cedentes · exclusões",
    "Cedentes · reparos fonte",
    "Taxonomia · de-para",
    "Taxonomia · Outros",
    "Taxonomia · impacto",
    "Universo elegível",
    "FICs excluídos",
    "Decisões do ledger",
}
REVISION_EMISSION_AUDIT_REQUIRED_HEADERS = frozenset(
    {
        "Preço unitário por tipo de cota",
        "Fonte preço",
        "Remuneração-alvo por tipo de cota",
        "Fonte remuneração",
    }
)
REVISION_EMISSION_COVERAGE_TARGET_LABEL = "Remuneração-alvo"
CEDENTE_TOP500_COMPETENCES = frozenset({"202312", "202412", "202512", "202606"})
CEDENTE_TOP500_WORKBOOK_SHEETS = {
    "Cedentes · Top 500": {
        "required_headers": {
            "CNPJ do fundo",
            "CNPJ/CPF do cedente",
            "Competência",
            "Rank PL",
            "Cedente dominante?",
        },
        "identifier_headers": {
            "CNPJ do fundo": r"\d{14}",
            "CNPJ/CPF do cedente": r"\d{1,14}",
        },
        "competence_header": "Competência",
    },
    "Cedentes · competência": {
        "required_headers": {
            "CNPJ/CPF",
            "Competência",
            "Natureza do cedente",
            "Segmento",
            "Critério do segmento",
        },
        "identifier_headers": {"CNPJ/CPF": r"\d{1,14}"},
        "competence_header": "Competência",
    },
    "Cedentes · sem cedente": {
        "required_headers": {
            "CNPJ do fundo",
            "Competência",
            "Rank PL",
            "Motivo",
        },
        "identifier_headers": {"CNPJ do fundo": r"\d{14}"},
        "competence_header": "Competência",
    },
    "Cedentes · evolução": {
        "required_headers": {
            "Competência",
            "Segmento",
            "PL alcançado (R$)",
        },
        "identifier_headers": {},
        "competence_header": "Competência",
    },
    "Cedentes · presença": {
        "required_headers": {
            "CNPJ/CPF",
            "Competências",
            "Natureza do cedente",
            "Segmento",
        },
        "identifier_headers": {"CNPJ/CPF": r"\d{1,14}"},
        "competence_header": None,
    },
    "Cedentes · cobertura": {
        "required_headers": {
            "Competência",
            "Fundos que identificam cedente",
            "Fundos sem cedente",
            "PL do Top 500 (R$)",
        },
        "identifier_headers": {},
        "competence_header": "Competência",
        "expected_rows": 4,
    },
    "Cedentes · PL segmento": {
        "required_headers": {
            "Competência",
            "Segmento",
            "PL dominante (R$)",
            "PL identificado · denominador (R$)",
        },
        "identifier_headers": {},
        "competence_header": "Competência",
    },
    "Cedentes · cadastro": {
        "required_headers": {
            "CNPJ/CPF",
            "Natureza do cedente",
            "Segmento",
            "Critério do segmento",
        },
        "identifier_headers": {"CNPJ/CPF": r"\d{1,14}"},
        "competence_header": None,
    },
    "Cedentes · exclusões": {
        "required_headers": {
            "competencia",
            "cnpj_fundo",
            "motivo_exclusao",
        },
        "identifier_headers": {"cnpj_fundo": r"\d{14}"},
        "competence_header": "competencia",
        # 202606 não tem documento fictício/irregular no Top 500; a ausência
        # de linhas é um resultado válido, não uma competência perdida.
        "expected_competences": frozenset({"202312", "202412", "202512"}),
    },
    "Cedentes · reparos fonte": {
        "required_headers": {
            "competencia",
            "tabela",
            "fonte",
            "linha_fisica",
            "acao",
            "documento_fundo",
            "denominacao_reparada",
            "data_referencia",
        },
        "identifier_headers": {"documento_fundo": r"\d{14}"},
        "competence_header": "competencia",
        "expected_competences": frozenset({"202312", "202412"}),
        "expected_rows": 10,
    },
}
REQUIRED_PORTFOLIO_WORKBOOK_SHEETS = {
    "Leia-me",
    "Carteira 101",
    "Casos 99",
    "Nomes editáveis",
    "Flagships",
    "Cobertura e lacunas",
    "Dicionário",
    "Fontes manuais",
    "Preços por cota",
    "Auditoria documental",
    "Evidências documentais",
    "Cobertura varredura",
    "Dicionário de campos",
}
PORTFOLIO_WORKBOOK_MINIMUM_HEADERS = frozenset(
    {
        "CNPJ",
        "Nome completo do fundo (CVM)",
        "PL atual",
        "Sub / PL atual",
        "Mínimo Jr literal",
        "Mínimo Jr calculado*",
        "Mínimo Jr ajustado*",
        "Suporte total*",
        "Suporte Jr + Mezanino*",
        "Índice estrutural usado",
        "Folga / falta",
        "Preço por cota · leitura",
        "Originador*",
        "Cedente*",
        "Sacado / devedor*",
        "Tipo de recebível*",
        "Categoria de risco atual",
        "Categoria de risco proposta",
        "Subtipo de risco diagnosticado",
        "Middle Market · status",
        "Fonte documental",
        "Status do preenchimento",
    }
)
PORTFOLIO_WORKBOOK_EXPECTED_ROWS = {
    "Carteira 101": 101,
    "Casos 99": 99,
    "Flagships": 47,
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
    portfolio_xlsx_path: str
    portfolio_xlsx_exists: bool
    top100_xlsx_path: str
    top100_xlsx_exists: bool
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
    portfolio_xlsx_path: Path
    portfolio_xlsx_bytes: bytes
    top100_xlsx_path: Path
    top100_xlsx_bytes: bytes
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


def _validate_no_mojibake_text(value: str, artifact_label: str) -> None:
    marker = next(
        (
            candidate
            for candidate in BLOCKED_PUBLISHED_TEXT_MARKERS
            if candidate in value
        ),
        None,
    )
    if marker is None:
        match = re.search(r"(?:Ã|Â)[\u0080-\u00bf]", value)
        marker = match.group(0) if match is not None else None
    if marker is not None:
        raise RevisionExportUnavailable(
            f"{artifact_label} contém texto corrompido ou ilegível: {marker}"
        )


def _validate_no_mojibake_office_archive(
    archive: zipfile.ZipFile,
    artifact_label: str,
) -> None:
    for name in archive.namelist():
        if not name.endswith((".xml", ".rels")):
            continue
        raw = archive.read(name)
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RevisionExportUnavailable(
                f"{artifact_label} contém parte OOXML fora de UTF-8: {name}"
            ) from exc
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError as exc:
            raise RevisionExportUnavailable(
                f"{artifact_label} contém parte OOXML inválida: {name}"
            ) from exc
        values: list[str] = []
        for element in root.iter():
            values.extend(
                value
                for value in (
                    element.text,
                    element.tail,
                    *element.attrib.values(),
                )
                if value
            )
        try:
            _validate_no_mojibake_text(" ".join(values), artifact_label)
        except RevisionExportUnavailable as exc:
            raise RevisionExportUnavailable(f"{exc} em {name}") from exc


def _normalize_office_text(value: str) -> str:
    """Return case- and accent-insensitive Office text with compact spacing."""

    normalized = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        ).split()
    )


def _normalized_slide_text(payload: bytes) -> str:
    """Return normalized text from one slide or notes XML part."""

    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return ""
    visible = " ".join(
        node.text or ""
        for node in root.iter()
        if node.tag.endswith("}t")
    )
    return _normalize_office_text(visible)


def _slide_xml_containing(
    archive: zipfile.ZipFile,
    *tokens: str,
) -> bytes:
    expected = [_normalize_office_text(token) for token in tokens]
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


def _validate_no_blocked_audience_copy(archive: zipfile.ZipFile) -> None:
    """Reject production placeholders and stale instructions in slides or notes."""

    blocked = tuple(_normalize_office_text(value) for value in BLOCKED_PPTX_AUDIENCE_COPY)
    audience_parts = sorted(
        name
        for name in archive.namelist()
        if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        or re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", name)
    )
    for name in audience_parts:
        text = _normalized_slide_text(archive.read(name))
        for phrase in blocked:
            if phrase in text:
                raise RevisionExportUnavailable(
                    "PPTX revisado contém placeholder ou instrução antiga "
                    f"em {name}: {phrase}"
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


def _native_table_text_rows(
    archive: zipfile.ZipFile,
    slide_number: int,
) -> tuple[tuple[str, ...], ...]:
    """Return the first native Office table as normalized cell text rows."""

    root = ElementTree.fromstring(
        archive.read(f"ppt/slides/slide{slide_number}.xml")
    )
    table = root.find(f".//{{{_DML}}}tbl")
    if table is None:
        return ()
    rows: list[tuple[str, ...]] = []
    for row in table.findall(f"{{{_DML}}}tr"):
        cells: list[str] = []
        for cell in row.findall(f"{{{_DML}}}tc"):
            text = " ".join(
                part.text or ""
                for part in cell.findall(f".//{{{_DML}}}t")
            )
            cells.append(" ".join(text.split()))
        rows.append(tuple(cells))
    return tuple(rows)


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


def _slide_contract_metadata(
    archive: zipfile.ZipFile, slide_path: str
) -> dict[str, object]:
    rels_path = posixpath.join(
        posixpath.dirname(slide_path), "_rels", posixpath.basename(slide_path) + ".rels"
    )
    try:
        rels = ElementTree.fromstring(archive.read(rels_path))
    except (KeyError, ElementTree.ParseError) as exc:
        raise RevisionExportUnavailable("slide sem relações Office válidas") from exc
    notes = []
    for relationship in rels:
        if not relationship.attrib.get("Type", "").endswith("/notesSlide"):
            continue
        target = relationship.attrib.get("Target", "")
        notes_path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(
            posixpath.join(posixpath.dirname(slide_path), target)
        )
        try:
            root = ElementTree.fromstring(archive.read(notes_path))
        except (KeyError, ElementTree.ParseError) as exc:
            raise RevisionExportUnavailable("PPTX sem notas válidas para o contrato editorial") from exc
        notes.append(" ".join(node.text or "" for node in root.iter(f"{{{_DML}}}t")))
    matches = re.findall(r"\[Industry contract\]\s*(\{[^{}]+\})", " ".join(notes))
    if len(matches) != 1:
        raise RevisionExportUnavailable("slide sem contrato editorial único nas notas")
    try:
        metadata = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise RevisionExportUnavailable("contrato editorial do slide inválido") from exc
    if not isinstance(metadata, dict):
        raise RevisionExportUnavailable("contrato editorial do slide inválido")
    return metadata


def validate_revision_pptx(
    payload: bytes, *, expected_payload: dict[str, object] | None = None,
    expected_signature: str | None = None,
) -> None:
    """Validate compact order, periods, native evidence and Office integrity."""

    if not _valid_zip(payload, "ppt/presentation.xml"):
        raise RevisionExportUnavailable("PPTX revisado inválido ou corrompido")
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        _validate_no_mojibake_office_archive(archive, "PPTX revisado")
        ordered_slides = _ordered_slide_parts(archive)
        if len(ordered_slides) != EXPECTED_SLIDES:
            raise RevisionExportUnavailable(
                f"PPTX revisado deveria conter {EXPECTED_SLIDES} slides; contém {len(ordered_slides)}"
            )
        _validate_no_blocked_audience_copy(archive)
        metadata_rows = []
        for slide_number, (slide_path, expected_id, expected_tokens) in enumerate(
            zip(ordered_slides, EXPECTED_SLIDE_IDS, EXPECTED_SLIDE_SEQUENCE, strict=True), start=1
        ):
            slide_text = _normalized_slide_text(archive.read(slide_path))
            missing = [token for token in expected_tokens if token not in slide_text]
            if missing:
                raise RevisionExportUnavailable(
                    f"slide {slide_number} viola o contrato ordinal: " + ", ".join(missing)
                )
            metadata = _slide_contract_metadata(archive, slide_path)
            if metadata.get("id") != expected_id:
                raise RevisionExportUnavailable(f"slide {slide_number} tem identidade editorial incorreta")
            if metadata.get("executive_conclusions") != 5:
                raise RevisionExportUnavailable("deck sem cinco conclusões atualizadas")
            metadata_rows.append(metadata)
        signatures = {str(row.get("source_signature", "")) for row in metadata_rows}
        if len(signatures) != 1 or not re.fullmatch(r"[0-9a-f]{64}", next(iter(signatures))):
            raise RevisionExportUnavailable("PPTX sem assinatura única do payload")
        if expected_signature is not None and signatures != {expected_signature}:
            raise RevisionExportUnavailable("PPTX desatualizado em relação à assinatura do payload")
        period_pairs = {
            (str(row.get("latest_complete", "")), str(row.get("offers_as_of", "")))
            for row in metadata_rows
        }
        if len(period_pairs) != 1:
            raise RevisionExportUnavailable("PPTX contém competências divergentes entre slides")
        competence, offers_as_of = next(iter(period_pairs))
        if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", competence) or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", offers_as_of):
            raise RevisionExportUnavailable("PPTX sem períodos de referência válidos")
        if expected_payload is not None and (
            competence != expected_payload.get("latest_complete")
            or offers_as_of != expected_payload.get("offers_as_of")
        ):
            raise RevisionExportUnavailable("PPTX desatualizado em relação ao payload")
        from services.industry_comparative_period import ComparisonCut

        try:
            offer_cut = ComparisonCut.from_competence(offers_as_of[:7])
        except ValueError as exc:
            raise RevisionExportUnavailable("PPTX sem corte mensal válido para ofertas") from exc
        if offers_as_of != offer_cut.period_end.isoformat():
            raise RevisionExportUnavailable("PPTX sem fechamento mensal para ofertas")
        if expected_payload is not None and expected_payload.get("offers_comparison_meta") is not None:
            metadata = expected_payload["offers_comparison_meta"]
            if (
                not isinstance(metadata, Mapping)
                or any(metadata.get(key) != value for key, value in offer_cut.to_meta().items())
                or offer_cut.competence != competence
            ):
                raise RevisionExportUnavailable("corte comparativo não acompanha a competência consolidada")
        for number in (1, 3, 4, 8, 9, 10, 11, 14):
            if offer_cut.period_label() not in _normalized_slide_text(archive.read(ordered_slides[number - 1])):
                raise RevisionExportUnavailable(f"slide {number} sem corte atual de ofertas")
        months = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
        stock_label = f"{months[int(competence[-2:]) - 1]}/{competence[2:4]}"
        for number in (1, 2, 5, 6, 7, 12, 13, 14, 15):
            if stock_label not in _normalized_slide_text(archive.read(ordered_slides[number - 1])):
                raise RevisionExportUnavailable(f"slide {number} sem competência atual do estoque")
        presentation = ElementTree.fromstring(archive.read("ppt/presentation.xml"))
        size = presentation.find(f"{{{_PML}}}sldSz")
        if size is None:
            raise RevisionExportUnavailable("PPTX revisado sem dimensão de slide")
        canvas = (int(size.attrib["cx"]), int(size.attrib["cy"]))
        _validate_native_table_slide(archive, 3, expected_dimensions=((7, 3),), canvas=canvas)
        # Preserve editable native charts on every retained evidence slide.
        chart_minimums = {2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2, 9: 3, 10: 1, 12: 6, 13: 2, 14: 2, 15: 4}
        for number, minimum in chart_minimums.items():
            root = ElementTree.fromstring(archive.read(ordered_slides[number - 1]))
            count = len(root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/chart}chart"))
            if count < minimum:
                raise RevisionExportUnavailable(f"slide {number} sem os gráficos nativos esperados")
        for number in (1, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15):
            if b"<a:tbl>" in archive.read(ordered_slides[number - 1]):
                raise RevisionExportUnavailable(f"slide {number} contém tabela fora do contrato compacto")
        scale_text = _normalized_slide_text(archive.read(ordered_slides[1]))
        if "saldo fic" in scale_text:
            raise RevisionExportUnavailable("slide de escala voltou a exibir FIC no gráfico de PL")
        office_xml = [archive.read(name) for name in archive.namelist() if name.endswith(".xml") and (name.startswith("ppt/slides/") or name.startswith("ppt/theme/") or "/charts/chart" in name)]
        if _contains_blocked_rgb_color(office_xml, "172A3A"):
            raise RevisionExportUnavailable("PPTX revisado contém a cor navy bloqueada")
        chart_xml = b"".join(archive.read(name) for name in _chart_members(archive))
        chart_namespace = "http://schemas.openxmlformats.org/drawingml/2006/chart"
        for name in _chart_members(archive):
            root = ElementTree.fromstring(archive.read(name))
            for labels in root.findall(f".//{{{chart_namespace}}}dLbls"):
                for scope in [labels, *labels.findall(f"{{{chart_namespace}}}dLbl")]:
                    for flag in ("showLegendKey", "showCatName", "showSerName", "showPercent", "showBubbleSize"):
                        value = scope.find(f"{{{chart_namespace}}}{flag}")
                        if value is None or value.attrib.get("val") not in {"0", "false"}:
                            raise RevisionExportUnavailable("PPTX revisado contém rótulos nativos ambíguos")
            for value in root.findall(f".//{{{chart_namespace}}}val//{{{chart_namespace}}}pt/{{{chart_namespace}}}v"):
                if value.text in {None, ""}:
                    continue
                try:
                    finite = math.isfinite(float(value.text))
                except ValueError:
                    finite = False
                if not finite:
                    raise RevisionExportUnavailable("PPTX revisado contém valor não finito em gráfico nativo")
        if b'<c:smooth val="1"' in chart_xml or b'<c:smooth val="true"' in chart_xml:
            raise RevisionExportUnavailable("PPTX revisado contém linha suavizada")
        for token in chart_xml.replace(b" />", b"/>").split(b"<c:marker>")[1:]:
            if b'<c:symbol val="none"' not in token.split(b"</c:marker>", 1)[0]:
                raise RevisionExportUnavailable("PPTX revisado contém marker ativo")


def _validate_workbook_offer_periods(workbook, expected_payload: Mapping[str, object]) -> None:
    """Validate the authored data blocks, separately from captions and summaries."""
    from services.industry_comparative_period import ComparisonCut

    try:
        offer_cut = ComparisonCut.from_competence(str(expected_payload["latest_complete"]))
    except (KeyError, ValueError) as exc:
        raise RevisionExportUnavailable("XLSX sem competência comparativa válida") from exc
    metadata = expected_payload.get("offers_comparison_meta") or {}
    if any(metadata.get(key) != value for key, value in offer_cut.to_meta().items()):
        raise RevisionExportUnavailable("XLSX usa metadados comparativos desatualizados")
    specs = (
        ("Comparativo renda fixa", "fixed_income_offer_comparison"),
        ("Regime de colocação", "closed_offer_placement_regime"),
        ("Histograma ofertas", "closed_offer_ticket_distribution"),
        ("Top 15 ofertas", "closed_offer_top15"),
        ("Validação emissões", "market_offer_reconciliation"),
        ("Público-alvo ofertas", "offer_target_public_shares"),
    )
    for sheet_name, source_key in specs:
        sheet = workbook[sheet_name]
        headers = [str(cell.value or "").strip() for cell in next(sheet.iter_rows(min_row=4, max_row=4), ())]
        if "Período" not in headers:
            raise RevisionExportUnavailable(f"{sheet_name} sem período comparativo")
        column = headers.index("Período")
        source_rows = expected_payload.get(source_key) or []
        if not source_rows:
            raise RevisionExportUnavailable(f"{sheet_name} sem linhas comparativas")
        last_data_row = 4 + len(source_rows)
        periods = [str(row[column].value or "") for row in sheet.iter_rows(min_row=5, max_row=last_data_row, max_col=len(headers))]
        source_periods = [str(row.get("period_label") or "") for row in source_rows]
        source_cut = offer_cut
        if source_key == "market_offer_reconciliation":
            secondary = (expected_payload.get("anbima_market_offers_manifest") or {}).get("comparison_meta") or {}
            try:
                source_cut = ComparisonCut.from_competence(str(secondary.get("current_period_end") or "")[:7])
            except ValueError as exc:
                raise RevisionExportUnavailable("Validação emissões sem corte ANBIMA válido") from exc
        if periods != source_periods or source_cut.period_id() not in periods:
            raise RevisionExportUnavailable(f"{sheet_name} usa período divergente do payload")
        if source_key != "closed_offer_top15":
            for row in sheet.iter_rows(min_row=last_data_row + 1, max_col=len(headers)):
                if re.match(r"^\d{4}\s+(?:FY|jan-)", str(row[column].value or "")):
                    raise RevisionExportUnavailable(f"{sheet_name} contém linhas comparativas extras")

    sheet = workbook["Top 15 ofertas"]
    summary = sorted(expected_payload.get("closed_offer_top15_summary") or [], key=lambda row: int(row.get("period_order") or 0))
    if len(summary) != 5 or len({row.get("period_label") for row in summary}) != 5:
        raise RevisionExportUnavailable("Top 15 ofertas deve conter cinco períodos de resumo")
    summary_specs = (
        ("Período", "period_label"),
        ("Ofertas no período", "period_closed_offers"),
        ("Volume do período", "period_registered_volume_brl"),
        ("Subtotal Top 15", "top15_registered_volume_brl"),
        ("% do total", "top15_share_of_period_volume"),
        ("IBBA líder · ofertas", "ibba_lead_offers_top15"),
        ("IBBA líder · volume", "ibba_lead_volume_top15_brl"),
        ("Garantia firme · ofertas", "firm_commitment_offers_top15"),
        ("Garantia firme · volume", "firm_commitment_volume_top15_brl"),
        ("% rito automático · volume", "automatic_rite_registered_volume_share"),
        ("Comparabilidade", "comparability_status"),
    )
    summary_row = len(expected_payload["closed_offer_top15"]) + 7
    headers = [cell.value for cell in next(sheet.iter_rows(min_row=summary_row, max_row=summary_row, max_col=len(summary_specs)))]
    if headers != [header for header, _ in summary_specs]:
        raise RevisionExportUnavailable("Top 15 ofertas sem cabeçalhos do resumo")
    for index, source_row in enumerate(summary, start=summary_row + 1):
        actual = next(sheet.iter_rows(min_row=index, max_row=index, max_col=len(summary_specs), values_only=True))
        for value, (header, key) in zip(actual, summary_specs):
            expected = source_row.get(key)
            if isinstance(expected, (int, float)) and not isinstance(expected, bool):
                tolerance = 0.01 if key.endswith("_brl") else 1e-12
                valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and math.isclose(value, expected, rel_tol=1e-13, abs_tol=tolerance)
            else:
                valid = value == expected
            if not valid:
                raise RevisionExportUnavailable(f"Top 15 ofertas: resumo divergente em {header}, linha {index}")
    expected_periods = {row["period_label"] for row in summary}
    for row in sheet.iter_rows(min_row=summary_row + len(summary) + 1, max_col=1, values_only=True):
        if row[0] in expected_periods:
            raise RevisionExportUnavailable("Top 15 ofertas contém períodos de resumo extras")

    taxonomy = workbook["Emissões por categoria"]
    taxonomy_headers = {str(cell.value or "").strip() for cell in next(taxonomy.iter_rows(min_row=4, max_row=4), ())}
    expected_headers = set((expected_payload.get("issuance_taxonomy_table") or [{}])[0])
    if not expected_headers.issubset(taxonomy_headers):
        raise RevisionExportUnavailable("Emissões por categoria usa cabeçalhos desatualizados")
    presence_headers = {str(cell.value or "").strip() for cell in next(workbook["Cedentes · presença"].iter_rows(min_row=4, max_row=4), ())}
    current_pl_header = f"PL {offer_cut.period_key()[:-2]}/{str(offer_cut.year)[-2:]} (R$)"
    if current_pl_header not in presence_headers:
        raise RevisionExportUnavailable("Cedentes · presença sem PL na competência atual")


def validate_revision_xlsx(payload: bytes, *, expected_payload: Mapping[str, object] | None = None) -> None:
    if not _valid_zip(payload, "xl/workbook.xml"):
        raise RevisionExportUnavailable("XLSX revisado inválido ou corrompido")
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            _validate_no_mojibake_office_archive(archive, "XLSX revisado")
        from openpyxl import load_workbook

        workbook = load_workbook(BytesIO(payload), read_only=True, data_only=False)
    except RevisionExportUnavailable:
        raise
    except Exception as exc:
        raise RevisionExportUnavailable("XLSX revisado não pôde ser lido") from exc
    try:
        missing = sorted(REQUIRED_WORKBOOK_SHEETS.difference(workbook.sheetnames))
        if missing:
            raise RevisionExportUnavailable(
                "XLSX revisado sem abas obrigatórias: " + ", ".join(missing)
            )

        audit_sheet = workbook["Auditoria emissões"]
        audit_headers = {
            str(cell.value or "").strip()
            for cell in next(audit_sheet.iter_rows(min_row=4, max_row=4), ())
        }
        missing_headers = sorted(
            REVISION_EMISSION_AUDIT_REQUIRED_HEADERS.difference(audit_headers)
        )
        if missing_headers:
            raise RevisionExportUnavailable(
                "Auditoria emissões não separa VNU de remuneração-alvo; faltam: "
                + ", ".join(missing_headers)
            )

        coverage_sheet = workbook["Cobertura emissões"]
        coverage_labels = [
            str(row[0].value or "").strip()
            for row in coverage_sheet.iter_rows(
                min_row=5,
                min_col=4,
                max_col=4,
            )
            if str(row[0].value or "").strip()
        ]
        target_count = coverage_labels.count(
            REVISION_EMISSION_COVERAGE_TARGET_LABEL
        )
        if target_count != 8:
            raise RevisionExportUnavailable(
                "Cobertura emissões deveria conter oito linhas de "
                f"{REVISION_EMISSION_COVERAGE_TARGET_LABEL}; contém {target_count}"
            )
        if "Preço por cota" in coverage_labels:
            raise RevisionExportUnavailable(
                "Cobertura emissões ainda trata VNU como rentabilidade-alvo"
            )

        from services.industry_comparative_period import ComparisonCut
        coverage = workbook["Cedentes · cobertura"]
        coverage_headers = [str(cell.value or "").strip() for cell in next(coverage.iter_rows(min_row=4, max_row=4), ())]
        if "Competência" not in coverage_headers:
            raise RevisionExportUnavailable("Cedentes · cobertura sem competência")
        coverage_column = coverage_headers.index("Competência")
        coverage_competences = {
            re.sub(r"\D", "", str(row[coverage_column].value or ""))
            for row in coverage.iter_rows(min_row=5, max_col=len(coverage_headers))
            if row[coverage_column].value not in (None, "")
        }
        try:
            cut = ComparisonCut.from_competence(max(coverage_competences))
        except (ValueError, TypeError) as exc:
            raise RevisionExportUnavailable("Cedentes · cobertura sem corte mensal válido") from exc
        expected_competences = {*(f"{year}12" for year in range(cut.year - 3, cut.year)), cut.competence.replace("-", "")}
        if expected_payload and expected_payload.get("offers_comparison_meta"):
            published_cut = ComparisonCut.from_competence(str(expected_payload.get("latest_complete") or ""))
            if cut != published_cut:
                raise RevisionExportUnavailable("corte de cedentes diverge da competência consolidada")
        if coverage_competences != expected_competences:
            raise RevisionExportUnavailable("cedentes devem cobrir três encerramentos anuais e a competência atual")
        sparse_keys = {"Cedentes · exclusões": "cedente_exclusions", "Cedentes · reparos fonte": "cedente_source_repairs"}
        for sheet_name, contract in CEDENTE_TOP500_WORKBOOK_SHEETS.items():
            sheet = workbook[sheet_name]
            header_cells = tuple(
                next(sheet.iter_rows(min_row=4, max_row=4), ())
            )
            headers = [str(cell.value or "").strip() for cell in header_cells]
            header_index = {
                header: index for index, header in enumerate(headers) if header
            }
            missing_cedent_headers = sorted(
                contract["required_headers"].difference(header_index)
            )
            if missing_cedent_headers:
                raise RevisionExportUnavailable(
                    f"{sheet_name} sem cabeçalhos obrigatórios: "
                    + ", ".join(missing_cedent_headers)
                )

            rows = [
                row
                for row in sheet.iter_rows(min_row=5, max_col=len(headers))
                if any(cell.value not in (None, "") for cell in row)
            ]
            empty_repairs = sheet_name == "Cedentes · reparos fonte" and str(sheet["A2"].value or "").startswith("0 reparos estruturais")
            if not rows and not empty_repairs:
                raise RevisionExportUnavailable(f"{sheet_name} está vazia")
            if empty_repairs and expected_payload:
                summary = (expected_payload.get("cedente_triage_manifest") or {}).get("source_repairs_summary")
                if not isinstance(summary, Mapping) or any(value != 0 for value in summary.values()) or expected_payload.get("cedente_source_repairs") != []:
                    raise RevisionExportUnavailable("zero reparos não reconcilia com o manifesto publicado")

            competence_header = contract["competence_header"]
            if competence_header:
                competence_column = header_index[competence_header]
                competences = {
                    re.sub(r"\D", "", str(row[competence_column].value or ""))
                    for row in rows
                }
                required_competences = expected_competences
                if sheet_name in sparse_keys:
                    if expected_payload:
                        source_rows = expected_payload.get(sparse_keys[sheet_name]) or []
                        required_competences = {
                            re.sub(r"\D", "", str(row.get("competencia") or "")) for row in source_rows
                        }
                    else:
                        required_competences = competences
                    if not competences.issubset(expected_competences):
                        raise RevisionExportUnavailable(f"{sheet_name} contém competência fora do corte")
                if competences != required_competences:
                    raise RevisionExportUnavailable(
                        f"{sheet_name} contém competências divergentes do contrato; contém {sorted(competences)}"
                    )

            expected_rows = 0 if empty_repairs else contract.get("expected_rows")
            if sheet_name in sparse_keys and expected_payload:
                expected_rows = len(expected_payload.get(sparse_keys[sheet_name]) or [])
            if expected_rows is not None and len(rows) != expected_rows:
                raise RevisionExportUnavailable(
                    f"{sheet_name} deveria conter {expected_rows} linhas; contém {len(rows)}"
                )

            for identifier_header, identifier_pattern in contract[
                "identifier_headers"
            ].items():
                identifier_column = header_index[identifier_header]
                invalid_identifiers: list[str] = []
                for row in rows:
                    cell = row[identifier_column]
                    value = cell.value
                    if not isinstance(value, str) or not re.fullmatch(
                        identifier_pattern, value.strip()
                    ):
                        invalid_identifiers.append(str(value or ""))
                        if len(invalid_identifiers) >= 3:
                            break
                if invalid_identifiers:
                    raise RevisionExportUnavailable(
                        f"{sheet_name} deve preservar {identifier_header} como texto "
                        "de 14 dígitos; exemplos inválidos: "
                        + ", ".join(invalid_identifiers)
                    )

        if expected_payload and expected_payload.get("offers_comparison_meta") is not None:
            _validate_workbook_offer_periods(workbook, expected_payload)
        try:
            validate_workbook_caches(payload)
        except (ValueError, KeyError, IndexError, ElementTree.ParseError) as exc:
            raise RevisionExportUnavailable(
                "XLSX revisado com cache operacional inválido: " + str(exc)
            ) from exc
    finally:
        workbook.close()


def _validated_numeric_cnpj(value: object) -> str | None:
    """Return a checksum-valid 14-digit CNPJ stored as an Excel number."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        digits = str(value)
    elif isinstance(value, float) and value.is_integer():
        digits = str(int(value))
    else:
        return None
    if not digits or len(digits) > 14:
        return None
    digits = digits.zfill(14)
    if len(set(digits)) == 1:
        return None

    def check_digit(base: str, weights: tuple[int, ...]) -> str:
        remainder = sum(
            int(character) * weight
            for character, weight in zip(base, weights, strict=True)
        ) % 11
        return "0" if remainder < 2 else str(11 - remainder)

    first = check_digit(
        digits[:12],
        (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2),
    )
    second = check_digit(
        digits[:12] + first,
        (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2),
    )
    return digits if digits[-2:] == first + second else None


def validate_revision_portfolio_xlsx(payload: bytes) -> None:
    """Validate the standalone Carteira 101 and flagship workbook."""

    if not _valid_zip(payload, "xl/workbook.xml"):
        raise RevisionExportUnavailable(
            "XLSX de Carteira 101 e Flagships inválido ou corrompido"
        )
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            _validate_no_mojibake_office_archive(
                archive,
                "XLSX de Carteira 101 e Flagships",
            )
            workbook_root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    except (KeyError, OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise RevisionExportUnavailable(
            "XLSX de Carteira 101 e Flagships inválido ou corrompido"
        ) from exc
    sheet_names = {
        str(node.attrib.get("name") or "")
        for node in workbook_root.iter()
        if node.tag.endswith("}sheet")
    }
    missing = sorted(REQUIRED_PORTFOLIO_WORKBOOK_SHEETS - sheet_names)
    if missing:
        raise RevisionExportUnavailable(
            "XLSX de Carteira 101 e Flagships sem abas obrigatórias: "
            + ", ".join(missing)
        )
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            chart_parts = _chart_members(archive)
            if not chart_parts:
                raise RevisionExportUnavailable(
                    "XLSX de Carteira 101 sem gráficos nativos do Office"
                )
            chart_xml = "\n".join(
                archive.read(name).decode("utf-8", errors="ignore")
                for name in chart_parts
            )
            if "Nomes editáveis" not in chart_xml:
                raise RevisionExportUnavailable(
                    "rótulos dos gráficos não referenciam a aba Nomes editáveis"
                )
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise RevisionExportUnavailable(
            "gráficos do XLSX de Carteira 101 não puderam ser validados"
        ) from exc

    try:
        from openpyxl import load_workbook

        workbook = load_workbook(
            BytesIO(payload),
            read_only=True,
            data_only=True,
        )
    except Exception as exc:
        raise RevisionExportUnavailable(
            "XLSX de Carteira 101 e Flagships não pôde ser lido"
        ) from exc

    try:
        for sheet_name, expected_rows in PORTFOLIO_WORKBOOK_EXPECTED_ROWS.items():
            sheet = workbook[sheet_name]
            header_cells = next(
                sheet.iter_rows(min_row=4, max_row=4),
                (),
            )
            headers = tuple(
                str(cell.value or "").strip() for cell in header_cells
            )
            missing_headers = sorted(
                PORTFOLIO_WORKBOOK_MINIMUM_HEADERS - set(headers)
            )
            if missing_headers:
                raise RevisionExportUnavailable(
                    f"aba {sheet_name} sem cabeçalhos obrigatórios: "
                    + ", ".join(missing_headers)
                )

            cnpj_column = headers.index("CNPJ")
            data_rows = [
                row
                for row in sheet.iter_rows(
                    min_row=5,
                    max_col=len(headers),
                )
                if any(cell.value not in (None, "") for cell in row)
            ]
            if len(data_rows) != expected_rows:
                raise RevisionExportUnavailable(
                    f"aba {sheet_name} deveria conter {expected_rows} linhas; "
                    f"contém {len(data_rows)}"
                )

            cnpjs: list[str] = []
            for row_number, row in enumerate(data_rows, start=5):
                cell = row[cnpj_column]
                cnpj = _validated_numeric_cnpj(cell.value)
                if cnpj is None:
                    raise RevisionExportUnavailable(
                        f"aba {sheet_name} contém CNPJ numérico inválido "
                        f"na linha {row_number}"
                    )
                cnpjs.append(cnpj)
            duplicated = sorted(
                {
                    cnpj
                    for cnpj in cnpjs
                    if cnpjs.count(cnpj) > 1
                }
            )
            if duplicated:
                raise RevisionExportUnavailable(
                    f"aba {sheet_name} contém CNPJ duplicado: "
                    + ", ".join(duplicated)
                )
    finally:
        workbook.close()


def validate_revision_top100_xlsx(payload: bytes) -> None:
    """Validate the standalone global Top 100 plus two 2026 issuances."""

    if not _valid_zip(payload, "xl/workbook.xml"):
        raise RevisionExportUnavailable("XLSX Top 100 inválido ou corrompido")
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            _validate_no_mojibake_office_archive(archive, "XLSX Top 100 + 2")
        from openpyxl import load_workbook

        workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
    except RevisionExportUnavailable:
        raise
    except Exception as exc:
        raise RevisionExportUnavailable("XLSX Top 100 não pôde ser lido") from exc
    try:
        required = {"Leia-me", "Top 100 FIDCs"}
        missing = required.difference(workbook.sheetnames)
        if missing:
            raise RevisionExportUnavailable(
                "XLSX Top 100 sem abas obrigatórias: " + ", ".join(sorted(missing))
            )
        sheet = workbook["Top 100 FIDCs"]
        headers = tuple(
            str(cell.value or "").strip()
            for cell in next(sheet.iter_rows(min_row=4, max_row=4), ())
        )
        required_headers = {
            "Ordem do export",
            "Rank geral por PL",
            "Critério de inclusão",
            "CNPJ",
            "Nome completo do fundo (CVM)",
            "PL",
            "Sub / PL atual",
            "Mínimo de Sub Jr",
            "Mínimo estrutural",
            "Preço inicial por cota",
            "Cedente / originador",
            "Sacado / devedor",
            "Tipo de recebível",
            "Tipo ANBIMA oficial",
            "Taxonomia funcional N1",
            "Middle Market · status",
            "Fonte",
        }
        missing_headers = required_headers.difference(headers)
        if missing_headers:
            raise RevisionExportUnavailable(
                "XLSX Top 100 sem cabeçalhos obrigatórios: "
                + ", ".join(sorted(missing_headers))
            )
        rows = [
            row
            for row in sheet.iter_rows(min_row=5, max_col=len(headers))
            if any(cell.value not in (None, "") for cell in row)
        ]
        if len(rows) != 102:
            raise RevisionExportUnavailable(
                f"XLSX Top 100 + 2 deveria conter 102 linhas; contém {len(rows)}"
            )
        cnpj_column = headers.index("CNPJ")
        cnpjs = [_validated_numeric_cnpj(row[cnpj_column].value) for row in rows]
        if any(value is None for value in cnpjs) or len(set(cnpjs)) != 102:
            raise RevisionExportUnavailable(
                "XLSX Top 100 + 2 deve conter 102 CNPJs numéricos válidos e únicos"
            )
        if not TOP100_PLUS2_ADDITIONAL_CNPJS.issubset(set(cnpjs)):
            raise RevisionExportUnavailable(
                "XLSX Top 100 + 2 não contém Citi-Bayer e Lavoro"
            )
        cnpj_formats = {
            str(row[cnpj_column].number_format or "") for row in rows
        }
        if cnpj_formats != {"00000000000000"}:
            raise RevisionExportUnavailable(
                "XLSX Top 100 + 2 deve exibir CNPJ com máscara de 14 dígitos"
            )
    finally:
        workbook.close()


def validate_revision_html(payload: bytes, *, expected_payload: Mapping[str, object] | None = None) -> None:
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
    _validate_no_mojibake_text(document, "HTML interativo de fluxos")
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
        "flagship_curation_compact_v2",
        "carteira_1_curation_compact_v4",
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
    if expected_payload and expected_payload.get("offers_comparison_meta") is not None:
        try:
            match = re.search(r'<script type="application/json" id="provider-flow-data">(.*?)</script>', document, flags=re.DOTALL)
            data = json.loads(match.group(1)) if match else {}
            taxonomy = data.get("issuanceTaxonomy") or {}
            if taxonomy.get("comparisonMeta") != expected_payload["offers_comparison_meta"]:
                raise ValueError("metadados divergentes")
            for row in expected_payload.get("issuance_taxonomy_table") or []:
                if row not in taxonomy.get("rows", []):
                    raise ValueError("tabela difere do payload publicado")
        except (ValueError, TypeError, AttributeError) as exc:
            raise RevisionExportUnavailable("HTML de emissões não acompanha o corte comparativo publicado") from exc
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


def revision_portfolio_xlsx_candidates(
    data_dir: Path = DEFAULT_DATA_DIR,
) -> tuple[Path, ...]:
    return _candidate_paths(
        Path(data_dir),
        materialized_name=MATERIALIZED_PORTFOLIO_XLSX_NAME,
        output_name=MATERIALIZED_PORTFOLIO_XLSX_NAME,
        env_name="FIDC_REVISION_PORTFOLIO_XLSX",
    )


def revision_top100_xlsx_candidates(
    data_dir: Path = DEFAULT_DATA_DIR,
) -> tuple[Path, ...]:
    return _candidate_paths(
        Path(data_dir),
        materialized_name=MATERIALIZED_TOP100_XLSX_NAME,
        output_name=MATERIALIZED_TOP100_XLSX_NAME,
        env_name="FIDC_REVISION_TOP100_XLSX",
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


def _read_cache_metadata(path: Path) -> tuple[str, dict[str, object]]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return "missing", {}
    except OSError as exc:
        raise RevisionExportUnavailable(f"bundle revisado ilegível: {exc}") from exc
    try:
        metadata = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        metadata = {}
    return _sha256(raw), metadata if isinstance(metadata, dict) else {}


def _signed_cache_input_paths(data_dir: Path, manifest: dict[str, object]) -> set[Path]:
    """Track published inputs available on this host, including missing paths.

    The manifest uses logical labels rather than absolute workstation paths.
    Data and analysis labels resolve directly; source ZIPs and builders retain
    both project-local and configured-runtime candidates. Staging-only inputs
    remain covered by the manifest digest and their materialized artifacts.
    """
    paths: set[Path] = set()
    roots = {ROOT.resolve(), data_dir.parent.parent.resolve()}
    inputs = manifest.get("inputs")
    for label in inputs if isinstance(inputs, dict) else ():
        kind, separator, name = str(label).partition("/")
        relative = Path(name)
        if not separator or not name or relative.is_absolute() or ".." in relative.parts:
            continue
        if kind == "data":
            paths.add(data_dir / relative)
        elif kind == "analysis":
            paths.add(revision_dir(data_dir) / relative)
        elif kind == "builder":
            for root in roots:
                paths.update((root / "scripts" / relative, root / "services" / relative))
        elif kind == "source":
            for root in roots:
                paths.update((root / ".cache" / "cvm-industry-study" / relative,
                              root / ".cache" / "cvm-cadastro" / relative))
        elif kind == "curation" and name == "top20.csv":
            for root in roots:
                paths.add(root / "outputs" / "analysis" / "top20_fidcs_curadoria.csv")
        elif kind == "workbook" and name == "input.xlsx":
            configured = os.environ.get("FIDC_INPUT_WORKBOOK", "").strip()
            if configured:
                paths.add(Path(configured).expanduser())
    # A manifest may also preserve the exact locations of custom source files.
    locations = manifest.get("input_paths")
    if isinstance(locations, dict):
        for label, location in locations.items():
            if isinstance(inputs, dict) and label in inputs and isinstance(location, str) and location.strip():
                path = Path(location).expanduser()
                paths.add(path if path.is_absolute() else data_dir / path)
    return paths


def _bundle_cache_fingerprint(data_dir: Path) -> tuple[object, ...]:
    manifest_path = revision_bundle_manifest_path(data_dir)
    payload_path = revision_payload_path(data_dir)
    manifest_digest, manifest = _read_cache_metadata(manifest_path)
    payload_digest, payload = _read_cache_metadata(payload_path)
    ledger_path = _taxonomy_review_ledger_path(data_dir, payload)
    audit_path = _taxonomy_review_audit_path(data_dir, payload)
    ledger_digest, _ = _read_cache_metadata(ledger_path)
    audit_digest, _ = _read_cache_metadata(audit_path)
    paths = {
        manifest_path, payload_path, ledger_path, audit_path,
        revision_dir(data_dir) / "revision_manifest.json",
        *_signed_cache_input_paths(data_dir, manifest),
    }
    candidate_groups = (
        revision_pptx_candidates(data_dir), revision_xlsx_candidates(data_dir),
        revision_portfolio_xlsx_candidates(data_dir), revision_top100_xlsx_candidates(data_dir),
        revision_html_candidates(data_dir),
    )
    records: list[tuple[object, ...]] = []
    for group in candidate_groups:
        # Candidate order is part of the key, including environment overrides.
        records.append(("candidate_order", *(str(path) for path in group)))
        paths.update(group)
    for path in sorted(paths, key=str):
        resolved = path.resolve()
        try:
            stat = resolved.stat()
        except FileNotFoundError:
            records.append((str(path), str(resolved), "missing"))
            continue
        except OSError as exc:
            raise RevisionExportUnavailable(f"assinatura do bundle indisponível: {exc}") from exc
        records.append((str(path), str(resolved), stat.st_size, stat.st_mtime_ns,
                        stat.st_ctime_ns, stat.st_ino, stat.st_mode))
    return (manifest_digest, payload_digest, ledger_digest, audit_digest, tuple(records))


_BUNDLE_CACHE_LOCK = RLock()


@lru_cache(maxsize=2)
def _cached_validated_bundle(data_dir: str, fingerprint: tuple[object, ...]) -> _ValidatedBundle:
    path = Path(data_dir)
    bundle = _validate_bundle_uncached(path)
    if _bundle_cache_fingerprint(path) != fingerprint:
        raise RevisionExportUnavailable("arquivos ou fontes do bundle mudaram durante a validação")
    return bundle


def _load_validated_bundle(data_dir: Path = DEFAULT_DATA_DIR) -> _ValidatedBundle:
    data_dir = Path(data_dir).resolve()
    # Coalesce simultaneous cold requests; exceptions never enter the LRU.
    with _BUNDLE_CACHE_LOCK:
        fingerprint = _bundle_cache_fingerprint(data_dir)
        bundle = _cached_validated_bundle(str(data_dir), fingerprint)
        if _bundle_cache_fingerprint(data_dir) != fingerprint:
            _cached_validated_bundle.cache_clear()
            raise RevisionExportUnavailable("arquivos ou fontes do bundle mudaram durante a leitura")
        return bundle


def _validate_bundle_uncached(data_dir: Path = DEFAULT_DATA_DIR) -> _ValidatedBundle:
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
    renderer_version = str(manifest.get("renderer_version") or "")
    renderer_match = re.fullmatch(r"industry_revision_artifacts_v(\d+)", renderer_version)
    if renderer_match and int(renderer_match.group(1)) >= 50 and payload.get("offers_comparison_meta") is None:
        raise RevisionExportUnavailable("bundle atual sem corte comparativo dinâmico")
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
        lambda data: validate_revision_pptx(data, expected_payload=payload, expected_signature=payload_hash),
    )
    xlsx_path, xlsx_bytes = _matching_candidate(
        revision_xlsx_candidates(data_dir),
        dict(manifest.get("xlsx") or {}),
        lambda data: validate_revision_xlsx(data, expected_payload=payload),
    )
    portfolio_xlsx_path, portfolio_xlsx_bytes = _matching_candidate(
        revision_portfolio_xlsx_candidates(data_dir),
        dict(manifest.get("portfolio_xlsx") or {}),
        validate_revision_portfolio_xlsx,
    )
    top100_xlsx_path, top100_xlsx_bytes = _matching_candidate(
        revision_top100_xlsx_candidates(data_dir),
        dict(manifest.get("top100_xlsx") or {}),
        validate_revision_top100_xlsx,
    )
    html_path, html_bytes = _matching_candidate(
        revision_html_candidates(data_dir),
        dict(manifest.get("html") or {}),
        lambda data: validate_revision_html(data, expected_payload=payload),
    )
    return _ValidatedBundle(
        manifest=manifest,
        pptx_path=pptx_path,
        pptx_bytes=pptx_bytes,
        xlsx_path=xlsx_path,
        xlsx_bytes=xlsx_bytes,
        portfolio_xlsx_path=portfolio_xlsx_path,
        portfolio_xlsx_bytes=portfolio_xlsx_bytes,
        top100_xlsx_path=top100_xlsx_path,
        top100_xlsx_bytes=top100_xlsx_bytes,
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
    portfolio_xlsx_path = revision_portfolio_xlsx_candidates(data_dir)[0]
    top100_xlsx_path = revision_top100_xlsx_candidates(data_dir)[0]
    html_path = revision_html_candidates(data_dir)[0]
    error = ""
    valid = False
    try:
        bundle = _load_validated_bundle(data_dir)
        bundle_id = str(bundle.manifest.get("bundle_id") or "")
        pptx_path = bundle.pptx_path
        xlsx_path = bundle.xlsx_path
        portfolio_xlsx_path = bundle.portfolio_xlsx_path
        top100_xlsx_path = bundle.top100_xlsx_path
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
        portfolio_xlsx_path=str(portfolio_xlsx_path),
        portfolio_xlsx_exists=portfolio_xlsx_path.exists(),
        top100_xlsx_path=str(top100_xlsx_path),
        top100_xlsx_exists=top100_xlsx_path.exists(),
        html_path=str(html_path),
        html_exists=html_path.exists(),
        artifact_runtime_available=artifact_runtime_available(),
    )


def build_revision_pptx_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    return _load_validated_bundle(data_dir).pptx_bytes


def build_revision_xlsx_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    return _load_validated_bundle(data_dir).xlsx_bytes


def build_revision_portfolio_xlsx_bytes(
    data_dir: Path = DEFAULT_DATA_DIR,
) -> bytes:
    return _load_validated_bundle(data_dir).portfolio_xlsx_bytes


def build_revision_top100_xlsx_bytes(
    data_dir: Path = DEFAULT_DATA_DIR,
) -> bytes:
    return _load_validated_bundle(data_dir).top100_xlsx_bytes


def build_revision_html_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    return _load_validated_bundle(data_dir).html_bytes


__all__ = [
    "BUNDLE_SCHEMA",
    "CURRENT_TOP15_SLIDE_SEQUENCE",
    "EXPECTED_SLIDE_SEQUENCE",
    "EXPECTED_SLIDE_IDS",
    "EXPECTED_SLIDES",
    "HISTORICAL_TOP15_SLIDE_SEQUENCE",
    "HISTORICAL_TOP15_TABLE_DIMENSIONS",
    "ISSUANCE_TAXONOMY_TABLE_DIMENSIONS",
    "MATERIALIZED_HTML_NAME",
    "MATERIALIZED_PORTFOLIO_XLSX_NAME",
    "MATERIALIZED_TOP100_XLSX_NAME",
    "REQUIRED_WORKBOOK_SHEETS",
    "REQUIRED_PORTFOLIO_WORKBOOK_SHEETS",
    "REVISION_EMISSION_AUDIT_REQUIRED_HEADERS",
    "REVISION_EMISSION_COVERAGE_TARGET_LABEL",
    "STRUCTURAL_MVP_SLIDE_SEQUENCE",
    "TYPE_RANKING_SLIDE_SEQUENCE",
    "RevisionExportStatus",
    "RevisionExportUnavailable",
    "artifact_runtime_available",
    "build_revision_pptx_bytes",
    "build_revision_portfolio_xlsx_bytes",
    "build_revision_top100_xlsx_bytes",
    "build_revision_xlsx_bytes",
    "build_revision_html_bytes",
    "get_revision_export_status",
    "revision_bundle_manifest_path",
    "revision_export_signature",
    "revision_payload_path",
    "revision_html_candidates",
    "revision_portfolio_xlsx_candidates",
    "revision_top100_xlsx_candidates",
    "validate_revision_html",
    "validate_revision_portfolio_xlsx",
    "validate_revision_top100_xlsx",
    "validate_revision_pptx",
    "validate_revision_xlsx",
]
