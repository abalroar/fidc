"""Validate reviewed documentary comparisons before publishing a package.

The finalizer consumes the curator's seven CSVs. It does not derive legal rules
from legacy tables, fill gaps or update the reading date implicitly.
"""
from __future__ import annotations

from copy import deepcopy
import csv
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
import unicodedata

import pandas as pd

from services.deep_dive_models import DeepDiveManifest
from services.deep_dive_ppt_export import build_document_comparison_pptx_bytes
from services.document_curation_comparison import DocumentComparisonPage, build_document_comparison_pages
from services.portfolio_store import PortfolioRecord, portfolio_basket_signature


COMPARISON_TITLES = {
    "comparison_eligibility": "Recebíveis e elegibilidade",
    "comparison_protection": "Subordinação, gatilhos e proteção",
    "comparison_mechanics": "Alocação e mecânica contratual",
    "comparison_emissions": "Emissões e remuneração",
    "comparison_payments": "Amortização e calendário de pagamentos",
    "comparison_costs": "Custos estruturais",
    "comparison_monitoring": "Monitoramento IME e controles documentais",
}
REQUIRED_COMPARISON_IDS = tuple(COMPARISON_TITLES)
EVIDENCE_COLUMNS = ("Tabela", "Critério", "CNPJ", "Valor", "Fonte", "Nota")
EXPORT_SOURCE_FILE = "exports/documentary_comparison.pptx"
_PLACEHOLDERS = {"", "-", "—", "–", "n/d", "n.d.", "nd", "nan", "none", "null", "na", "n/a"}


class DocumentCurationContractError(ValueError):
    """A reviewed package cannot be finalized without fixing this finding."""


@dataclass(frozen=True)
class ValidatedDocumentCuration:
    payload: dict[str, Any]
    manifest: DeepDiveManifest
    pages: tuple[DocumentComparisonPage, ...]
    cell_count: int


@dataclass(frozen=True)
class DocumentCurationResult:
    package_dir: Path
    generated_at: str
    table_count: int
    cell_count: int
    pptx_sha256: str
    slide_count: int
    export_exists: bool
    check_only: bool


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value))


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).casefold().split())


def _require_text(value: object, location: str) -> str:
    text = str(value)
    if text.strip().casefold() in _PLACEHOLDERS:
        raise DocumentCurationContractError(f"{location}: lacuna implícita; descreva a ausência em texto.")
    return text


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DocumentCurationContractError(f"Não foi possível ler {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DocumentCurationContractError(f"{path}: objeto JSON esperado.")
    return payload


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle), [])
        if len(header) != len(set(header)):
            raise DocumentCurationContractError(f"{path}: cabeçalhos duplicados.")
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise DocumentCurationContractError(f"Não foi possível ler {path}: {exc}") from exc
    if frame.empty:
        raise DocumentCurationContractError(f"{path}: tabela vazia.")
    return frame


def _reading_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DocumentCurationContractError("Data de leitura inválida; use ISO 8601 com fuso horário.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DocumentCurationContractError("Data de leitura exige fuso horário, por exemplo 2026-10-07T11:56:39-03:00.")
    return value


def _validate_portfolio(payload: dict[str, Any], portfolio: PortfolioRecord) -> set[str]:
    if payload.get("portfolio_id") != portfolio.id:
        raise DocumentCurationContractError("portfolio_id do pacote difere da carteira salva.")
    if payload.get("portfolio_signature") != portfolio_basket_signature(portfolio.funds):
        raise DocumentCurationContractError("Assinatura do pacote difere dos CNPJs da carteira salva.")
    funds = payload.get("funds")
    if not isinstance(funds, list) or any(not isinstance(fund, dict) for fund in funds):
        raise DocumentCurationContractError("manifest.funds deve listar os fundos da carteira salva.")
    observed = [_digits(fund.get("cnpj", "")) for fund in funds]
    expected = {fund.cnpj for fund in portfolio.funds}
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise DocumentCurationContractError("CNPJs do manifest diferem da carteira salva ou estão duplicados.")
    return expected


def _column_mapping(payload: dict[str, Any], portfolio: PortfolioRecord, labels: list[str]) -> dict[str, str]:
    explicit = payload.get("comparison_columns")
    expected = {fund.cnpj for fund in portfolio.funds}
    if explicit is not None:
        if not isinstance(explicit, dict):
            raise DocumentCurationContractError("comparison_columns deve ser um mapa de cabeçalho para CNPJ.")
        if set(explicit) != set(labels):
            raise DocumentCurationContractError("comparison_columns exige as chaves exatas dos cabeçalhos, sem omissões ou colunas extras.")
        mapping = {label: _digits(explicit.get(label, "")) for label in labels}
        unknown = [label for label, cnpj in mapping.items() if cnpj not in expected]
        if unknown:
            raise DocumentCurationContractError(f"Cabeçalho sem CNPJ inequívoco em comparison_columns: {', '.join(unknown)}.")
    else:
        aliases: dict[str, set[str]] = {}
        for fund in payload["funds"]:
            cnpj = _digits(fund["cnpj"])
            for value in (fund.get("name"), fund.get("short_name"), fund.get("cnpj"), cnpj):
                if value:
                    aliases.setdefault(_fold(value), set()).add(cnpj)
        for fund in portfolio.funds:
            aliases.setdefault(_fold(fund.display_name), set()).add(fund.cnpj)
        mapping = {}
        for label in labels:
            candidates = aliases.get(_fold(label), set()).copy()
            if _digits(label) in expected:
                candidates.add(_digits(label))
            if len(candidates) != 1:
                raise DocumentCurationContractError(
                    f"Cabeçalho '{label}' sem CNPJ inequívoco; informe manifest.comparison_columns."
                )
            mapping[label] = next(iter(candidates))
    if len(mapping) != len(expected) or set(mapping.values()) != expected:
        raise DocumentCurationContractError("Cada comparativo deve conter exatamente uma coluna por CNPJ da carteira salva.")
    return mapping


def _register_specs(payload: dict[str, Any]) -> None:
    raw_specs = payload.get("tables") or []
    if not isinstance(raw_specs, list) or any(not isinstance(spec, dict) for spec in raw_specs):
        raise DocumentCurationContractError("manifest.tables deve ser uma lista de especificações.")
    ids = [spec.get("id") for spec in raw_specs]
    if len(ids) != len(set(ids)):
        raise DocumentCurationContractError("IDs duplicados em manifest.tables.")
    unknown = [spec.get("id") for spec in raw_specs if spec.get("kind") == "document_comparison" and spec.get("id") not in COMPARISON_TITLES]
    if unknown:
        raise DocumentCurationContractError(f"Comparativos fora do contrato: {', '.join(map(str, unknown))}.")
    existing = {spec.get("id"): spec for spec in raw_specs}
    kept = [spec for spec in raw_specs if spec.get("id") not in {*REQUIRED_COMPARISON_IDS, "comparison_evidence", "key_findings"}]
    kept.append({**existing.get("key_findings", {}), "id": "key_findings", "title": "Destaques da carteira", "source_file": "tables/key_findings.csv", "first_column": "Tema", "kind": "source_table"})
    for table_id, title in COMPARISON_TITLES.items():
        kept.append({**existing.get(table_id, {}), "id": table_id, "title": existing.get(table_id, {}).get("title") or title, "source_file": f"tables/{table_id}.csv", "first_column": "Critério", "kind": "document_comparison"})
    kept.append({**existing.get("comparison_evidence", {}), "id": "comparison_evidence", "title": "Fontes e notas dos comparativos", "source_file": "evidence/comparison_sources.csv", "first_column": "Tabela", "kind": "source_table"})
    payload["tables"] = kept


def validate_document_curation_contract(
    package_dir: str | Path,
    portfolio: PortfolioRecord,
    *,
    reading_at: str | None = None,
) -> ValidatedDocumentCuration:
    """Read and validate all reviewed inputs without changing any file."""
    package_dir = Path(package_dir)
    payload = deepcopy(_read_json(package_dir / "manifest.json"))
    expected = _validate_portfolio(payload, portfolio)
    payload["generated_at"] = _reading_at(reading_at if reading_at is not None else str(payload.get("generated_at", "")))
    findings = _read_csv(package_dir / "tables/key_findings.csv")
    if tuple(findings.columns) != ("Tema", "Conclusão") or not 3 <= len(findings) <= 5:
        raise DocumentCurationContractError("key_findings.csv exige colunas Tema/Conclusão e 3 a 5 conclusões.")
    for index, row in findings.iterrows():
        for column in findings:
            _require_text(row[column], f"key_findings.csv, linha {index + 2}, {column}")

    cells: dict[tuple[str, str, str], str] = {}
    canonical_columns: list[str] | None = None
    for table_id in REQUIRED_COMPARISON_IDS:
        frame = _read_csv(package_dir / f"tables/{table_id}.csv")
        if frame.columns[0] != "Critério":
            raise DocumentCurationContractError(f"{table_id}: primeira coluna deve ser Critério.")
        labels = list(frame.columns[1:])
        if canonical_columns is None:
            canonical_columns = labels
        elif labels != canonical_columns:
            raise DocumentCurationContractError(f"{table_id}: os sete comparativos devem manter os mesmos cabeçalhos e a mesma ordem de fundos.")
        mapping = _column_mapping(payload, portfolio, labels)
        if frame["Critério"].duplicated().any():
            raise DocumentCurationContractError(f"{table_id}: critérios duplicados.")
        for index, row in frame.iterrows():
            criterion = _require_text(row["Critério"], f"{table_id}, linha {index + 2}, Critério")
            for label, cnpj in mapping.items():
                cells[(table_id, criterion, cnpj)] = _require_text(row[label], f"{table_id}, {criterion}, {label}")

    evidence = _read_csv(package_dir / "evidence/comparison_sources.csv")
    if tuple(evidence.columns) != EVIDENCE_COLUMNS:
        raise DocumentCurationContractError("comparison_sources.csv exige as colunas exatas Tabela, Critério, CNPJ, Valor, Fonte, Nota.")
    covered = set()
    for index, row in evidence.iterrows():
        location = f"comparison_sources.csv, linha {index + 2}"
        if row["Tabela"] not in COMPARISON_TITLES:
            raise DocumentCurationContractError(f"{location}: Tabela desconhecida '{row['Tabela']}'.")
        if row["CNPJ"] == "Carteira":
            if row["Critério"] != "Nota":
                raise DocumentCurationContractError(f"{location}: Carteira só pode qualificar uma nota comum (Critério=Nota).")
            _require_text(row["Nota"], f"{location}, Nota")
            continue
        cnpj = _digits(row["CNPJ"])
        if cnpj not in expected:
            raise DocumentCurationContractError(f"{location}: CNPJ fora da carteira salva.")
        key = (row["Tabela"], row["Critério"], cnpj)
        if key not in cells:
            raise DocumentCurationContractError(f"{location}: evidência sem célula correspondente ({key}).")
        if row["Valor"] != cells[key]:
            raise DocumentCurationContractError(f"{location}: Valor diverge da célula {key}.")
        _require_text(row["Fonte"], f"{location}, Fonte")
        covered.add(key)
    missing = set(cells) - covered
    if missing:
        table_id, criterion, cnpj = sorted(missing)[0]
        raise DocumentCurationContractError(f"Célula sem evidência: {table_id}, {criterion}, CNPJ {cnpj} ({len(missing)} pendente(s)).")

    _register_specs(payload)
    manifest = DeepDiveManifest.from_dict(payload, package_dir=package_dir)
    pages = tuple(build_document_comparison_pages(manifest))
    if len(pages) != len(REQUIRED_COMPARISON_IDS):
        raise DocumentCurationContractError("O renderizador não carregou os sete comparativos revisados.")
    return ValidatedDocumentCuration(payload, manifest, pages, len(cells))


def _presentation_fingerprint(payload: bytes) -> tuple[str, int]:
    """Compare rendered native data without ZIP timestamps or core metadata."""
    from pptx import Presentation

    try:
        presentation = Presentation(BytesIO(payload))
        slides = []
        for slide in presentation.slides:
            shapes = []
            for shape in slide.shapes:
                record: dict[str, Any] = {"position": [shape.left, shape.top, shape.width, shape.height]}
                if shape.has_table:
                    record["table"] = [[cell.text for cell in row.cells] for row in shape.table.rows]
                elif shape.has_text_frame:
                    record["text"] = shape.text
                else:
                    raise DocumentCurationContractError("PPTX documental contém objeto sem texto/tabela nativa.")
                shapes.append(record)
            if not any("table" in shape for shape in shapes):
                raise DocumentCurationContractError("PPTX documental contém slide sem tabela nativa.")
            slides.append({"shapes": shapes, "notes": slide.notes_slide.notes_text_frame.text})
        data = {"size": [presentation.slide_width, presentation.slide_height], "slides": slides}
        return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), len(slides)
    except DocumentCurationContractError:
        raise
    except Exception as exc:
        raise DocumentCurationContractError(f"PPTX documental inválido: {exc}") from exc


def _input_digest(validated: ValidatedDocumentCuration) -> str:
    files = [*(f"tables/{table_id}.csv" for table_id in REQUIRED_COMPARISON_IDS), "tables/key_findings.csv", "evidence/comparison_sources.csv"]
    data = {
        "manifest": {key: validated.payload.get(key) for key in ("deep_dive_id", "title", "generated_at", "source", "portfolio_id", "portfolio_signature", "funds", "comparison_columns", "tables")},
        "files": {source_file: sha256((validated.manifest.package_dir / source_file).read_bytes()).hexdigest() for source_file in files},
    }
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _validate_registered_specs(raw: dict[str, Any], registered: dict[str, Any]) -> None:
    """The actual screen reads raw specs, so a finalized check requires them."""
    required = {*REQUIRED_COMPARISON_IDS, "comparison_evidence", "key_findings"}
    expected = {spec["id"]: spec for spec in registered["tables"] if spec["id"] in required}
    observed = {spec.get("id"): spec for spec in raw.get("tables") or []}
    for table_id, spec in expected.items():
        if any(observed.get(table_id, {}).get(key) != spec[key] for key in ("id", "source_file", "first_column", "kind")):
            raise DocumentCurationContractError(f"manifest.tables não registra corretamente {table_id}; a tela carregaria um contrato diferente. Execute a finalização.")


def _index_payload(root: Path, validated: ValidatedDocumentCuration) -> dict[str, Any]:
    path = root / "index.json"
    payload = deepcopy(_read_json(path)) if path.exists() else {"deep_dives": []}
    entries = payload.get("deep_dives")
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise DocumentCurationContractError("index.json exige lista deep_dives.")
    manifest = validated.manifest
    target = [index for index, entry in enumerate(entries) if entry.get("deep_dive_id") == manifest.deep_dive_id]
    if len(target) > 1:
        raise DocumentCurationContractError("Pacote alvo duplicado no índice.")
    try:
        manifest_path = (manifest.package_dir / "manifest.json").resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise DocumentCurationContractError("Pacote alvo está fora do output-root.") from exc
    entry = {"deep_dive_id": manifest.deep_dive_id, "title": manifest.title, "subtitle": manifest.subtitle, "generated_at": manifest.generated_at, "portfolio_id": manifest.portfolio_id, "portfolio_signature": manifest.portfolio_signature, "manifest_path": manifest_path}
    if target:
        entries[target[0]] = {**entries[target[0]], **entry}
    else:
        entries.append(entry)
    return payload


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def finalize_document_curation(
    package_dir: str | Path,
    portfolio: PortfolioRecord,
    *,
    output_root: str | Path | None = None,
    reading_at: str | None = None,
    check_only: bool = False,
) -> DocumentCurationResult:
    """Finalize one saved portfolio, or check it without mutating its artifacts."""
    validated = validate_document_curation_contract(package_dir, portfolio, reading_at=reading_at)
    payload = build_document_comparison_pptx_bytes(validated.manifest, validated.pages)
    rendered_hash, slide_count = _presentation_fingerprint(payload)
    input_hash = _input_digest(validated)
    export_path = validated.manifest.package_dir / EXPORT_SOURCE_FILE
    export_exists = export_path.exists()
    export_hash = sha256(payload).hexdigest()
    metadata = validated.payload.get("documentary_export")
    if check_only:
        if metadata is not None or export_exists:
            _validate_registered_specs(_read_json(validated.manifest.package_dir / "manifest.json"), validated.payload)
        if metadata is not None:
            if not isinstance(metadata, dict) or metadata.get("source_file") != EXPORT_SOURCE_FILE:
                raise DocumentCurationContractError("documentary_export deve apontar para exports/documentary_comparison.pptx.")
            if not export_exists:
                raise DocumentCurationContractError("PPTX registrado no manifest não está disponível no pacote.")
        if export_exists:
            existing = export_path.read_bytes()
            export_hash = sha256(existing).hexdigest()
            if not isinstance(metadata, dict) or metadata.get("sha256") != export_hash:
                raise DocumentCurationContractError("Hash do PPTX diverge de documentary_export.sha256 ou não foi registrado.")
            existing_rendered_hash, _ = _presentation_fingerprint(existing)
            if existing_rendered_hash != rendered_hash:
                raise DocumentCurationContractError("PPTX diverge dos comparativos, notas ou fontes atualmente carregados pelo site.")
            if metadata.get("input_sha256") != input_hash:
                raise DocumentCurationContractError("Digest dos inputs diverge de documentary_export.input_sha256; finalize novamente após revisar os arquivos.")
    else:
        root = Path(output_root) if output_root is not None else validated.manifest.package_dir.parent
        index = _index_payload(root, validated)
        validated.payload["documentary_export"] = {"source_file": EXPORT_SOURCE_FILE, "sha256": export_hash, "rendering_sha256": rendered_hash, "input_sha256": input_hash}
        manifest_bytes = (json.dumps(validated.payload, ensure_ascii=False, indent=2) + "\n").encode()
        index_bytes = (json.dumps(index, ensure_ascii=False, indent=2) + "\n").encode()
        # All inputs, index and generated PPTX are ready before the first write.
        _atomic_write(export_path, payload)
        _atomic_write(validated.manifest.package_dir / "manifest.json", manifest_bytes)
        _atomic_write(root / "index.json", index_bytes)
        export_exists = True
    return DocumentCurationResult(validated.manifest.package_dir, validated.manifest.generated_at, len(validated.pages), validated.cell_count, export_hash, slide_count, export_exists, check_only)


def find_document_curation_package(portfolio: PortfolioRecord, output_root: str | Path) -> Path:
    """Find the newest package whose saved portfolio ID is exact."""
    candidates = []
    for path in Path(output_root).glob("*/manifest.json"):
        try:
            payload = _read_json(path)
        except DocumentCurationContractError:
            # Unrelated malformed packages must not prevent the target lookup.
            continue
        if payload.get("portfolio_id") == portfolio.id:
            candidates.append((str(payload.get("generated_at", "")), path.parent))
    if not candidates:
        raise DocumentCurationContractError(f"Nenhum pacote encontrado para a carteira existente {portfolio.id}.")
    candidates.sort(key=lambda item: item[0], reverse=True)
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        raise DocumentCurationContractError("Mais de um pacote da carteira tem a mesma data; resolva a duplicidade antes de finalizar.")
    return candidates[0][1]
