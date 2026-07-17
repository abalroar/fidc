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
import shutil
from typing import Callable, Iterable
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data" / "industry_study"
PAYLOAD_NAME = "artifact_payload.json"
BUNDLE_MANIFEST_NAME = "industry_export_bundle.json"
MATERIALIZED_PPTX_NAME = "industry_executive_revised.pptx"
MATERIALIZED_XLSX_NAME = "industry_data_revised.xlsx"
BUNDLE_SCHEMA = "fidc_revision_export_bundle_v1"
PAYLOAD_SCHEMA = "fidc_revision_artifact_payload_v3"
EXPECTED_SLIDES = 44
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
    "Comparativos históricos",
    "Ranking prestadores",
    "Taxonomia adquirência",
    "Curadoria Atlântico",
    "Série Atlântico",
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
        office_xml = b"".join(
            archive.read(name)
            for name in archive.namelist()
            if name.endswith(".xml") and (
                name.startswith("ppt/slides/")
                or name.startswith("ppt/theme/")
                or "/charts/chart" in name
            )
        )
        if b"172A3A" in office_xml.upper():
            raise RevisionExportUnavailable("PPTX revisado contém a cor navy bloqueada")
        chart_xml = b"".join(archive.read(name) for name in _chart_members(archive))
        if b'<c:smooth val="1"' in chart_xml or b'<c:smooth val="true"' in chart_xml:
            raise RevisionExportUnavailable("PPTX revisado contém linha suavizada")
        marker_tokens = chart_xml.replace(b" />", b"/>").split(b"<c:marker>")[1:]
        for token in marker_tokens:
            marker = token.split(b"</c:marker>", 1)[0]
            if b'<c:symbol val="none"' not in marker:
                raise RevisionExportUnavailable("PPTX revisado contém marker ativo")


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
    return _ValidatedBundle(
        manifest=manifest,
        pptx_path=pptx_path,
        pptx_bytes=pptx_bytes,
        xlsx_path=xlsx_path,
        xlsx_bytes=xlsx_bytes,
    )


def revision_export_signature(data_dir: Path = DEFAULT_DATA_DIR) -> str:
    """Cache key that changes whenever the published bundle manifest changes."""

    path = revision_bundle_manifest_path(data_dir)
    if not path.exists():
        return f"missing:{path}"
    return _sha256(path.read_bytes())


def get_revision_export_status(data_dir: Path = DEFAULT_DATA_DIR) -> RevisionExportStatus:
    data_dir = Path(data_dir).resolve()
    payload_path = revision_payload_path(data_dir)
    manifest_path = revision_bundle_manifest_path(data_dir)
    schema, latest = _payload_metadata(payload_path)
    bundle_id = ""
    pptx_path = revision_pptx_candidates(data_dir)[0]
    xlsx_path = revision_xlsx_candidates(data_dir)[0]
    error = ""
    valid = False
    try:
        bundle = _load_validated_bundle(data_dir)
        bundle_id = str(bundle.manifest.get("bundle_id") or "")
        pptx_path = bundle.pptx_path
        xlsx_path = bundle.xlsx_path
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
        artifact_runtime_available=artifact_runtime_available(),
    )


def build_revision_pptx_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    return _load_validated_bundle(data_dir).pptx_bytes


def build_revision_xlsx_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    return _load_validated_bundle(data_dir).xlsx_bytes


__all__ = [
    "BUNDLE_SCHEMA",
    "RevisionExportStatus",
    "RevisionExportUnavailable",
    "artifact_runtime_available",
    "build_revision_pptx_bytes",
    "build_revision_xlsx_bytes",
    "get_revision_export_status",
    "revision_bundle_manifest_path",
    "revision_export_signature",
    "revision_payload_path",
    "validate_revision_pptx",
    "validate_revision_xlsx",
]
