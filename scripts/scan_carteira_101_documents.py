from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime
import gzip
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from typing import Any, Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.carteira_101_document_audit import (  # noqa: E402
    AUDITED_FIELDS,
    SCHEMA_VERSION,
    DocumentSource,
    Evidence,
    PriceEvidence,
    build_audit_table,
    classify_source_kind,
    compact_text,
    coverage_table,
    deduplicate_evidence,
    deduplicate_prices,
    evidence_frame,
    evidence_from_checkpoint,
    extract_document_evidence,
    fold_text,
    fundonet_download_url,
    is_missing,
    normalize_cnpj,
    payload_evidence,
    price_frame,
    price_rows_from_sqlite,
    read_checkpoint,
    serialize_evidence,
    serialize_prices,
    source_priority,
    utc_now_iso,
    write_checkpoint,
)
from services.fundonet_client import FundosNetClient  # noqa: E402
from services.regulatory_knowledge import classify_document  # noqa: E402


DEFAULT_OUTPUT_DIR = Path("data/industry_study/carteira_101_document_audit")
DEFAULT_PAYLOAD = Path("data/industry_study/generated_revision/artifact_payload.json")
DEFAULT_INVENTORY = Path("data/industry_study/document_inventory.csv.gz")
DEFAULT_TEXT_CACHE = Path("data/industry_study/document_text_cache")
DEFAULT_DIRECTOR_CACHE = Path(
    "outputs/fidc_director_deep_diagnostic_20260609/pdf_text_cache"
)
DEFAULT_STRUCTURED_PARTIES = Path("data/industry_study/cedentes_structured.csv.gz")
DEFAULT_DB = Path("data/fidc_credit_strategy/fidc_credit_strategy.sqlite")
PARTY_LABEL_PARSER_VERSION = 2
PRICE_PARSER_VERSION = 2
REMUNERATION_PARSER_VERSION = 1
ONLINE_SUCCESS_STATUSES = {"consultado", "sem_documentos"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Varre os 101 CNPJs da Carteira 1 e materializa evidência "
            "documental com checkpoint por CNPJ."
        )
    )
    parser.add_argument("--payload", type=Path, default=DEFAULT_PAYLOAD)
    parser.add_argument(
        "--top15-ranking-scope",
        action="store_true",
        help=(
            "Deriva a coorte diretamente de top20_taxonomy_review no payload: "
            "Top 15 por Tipo nos fechamentos 2025-12 e mais recente."
        ),
    )
    parser.add_argument(
        "--scope-csv",
        type=Path,
        help=(
            "CSV alternativo para uma varredura por CNPJ. Quando informado, "
            "substitui a coorte Carteira 101 do payload."
        ),
    )
    parser.add_argument("--scope-cnpj-column", default="cnpj")
    parser.add_argument("--scope-name-column", default="fundo")
    parser.add_argument(
        "--scope-filter-column",
        help="Coluna opcional usada para restringir as linhas do CSV alternativo.",
    )
    parser.add_argument(
        "--scope-filter-value",
        help="Valor exato exigido na coluna informada por --scope-filter-column.",
    )
    parser.add_argument("--scope-name", default="Carteira 101")
    parser.add_argument(
        "--output-prefix",
        default="carteira_101_document",
        help="Prefixo dos seis arquivos materializados no diretório de saída.",
    )
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--text-cache", type=Path, default=DEFAULT_TEXT_CACHE)
    parser.add_argument("--director-cache", type=Path, default=DEFAULT_DIRECTOR_CACHE)
    parser.add_argument("--structured-parties", type=Path, default=DEFAULT_STRUCTURED_PARTIES)
    parser.add_argument("--credit-strategy-db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--runtime-cache", type=Path, default=Path(".cache/carteira_101_document_scan"))
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-cnpjs", type=int, default=0)
    parser.add_argument("--max-pages", type=int, default=180)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--max-docs-per-kind", type=int, default=2)
    return parser.parse_args()


def load_portfolio(
    payload_path: Path,
    *,
    scope_csv: Path | None = None,
    scope_cnpj_column: str = "cnpj",
    scope_name_column: str = "fundo",
    scope_filter_column: str | None = None,
    scope_filter_value: str | None = None,
    top15_ranking_scope: bool = False,
) -> pd.DataFrame:
    if top15_ranking_scope:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        source = pd.DataFrame(payload.get("top20_taxonomy_review") or [])
        required = {"cnpj_fundo", "denominacao", "competencia", "rank_tipo"}
        missing = required.difference(source.columns)
        if missing:
            raise ValueError(
                f"ranking documental sem colunas obrigatórias: {sorted(missing)}"
            )
        competences = sorted(source["competencia"].astype(str).unique())
        if not competences:
            raise ValueError("ranking documental sem competências")
        reference_periods = {"2025-12", competences[-1]}
        source = source[
            source["competencia"].astype(str).isin(reference_periods)
            & pd.to_numeric(source["rank_tipo"], errors="coerce").le(15)
        ].copy()
        rows = pd.DataFrame(
            {
                "cnpj": source["cnpj_fundo"].map(normalize_cnpj),
                "nome_oficial_cvm": source["denominacao"],
            }
        )
        rows = rows[rows["cnpj"].ne("")].drop_duplicates("cnpj", keep="first")
        rows = rows.reset_index(drop=True)
        rows.insert(0, "ordem", range(1, len(rows) + 1))
        rows["nome_referencia"] = rows["nome_oficial_cvm"]
        if len(rows) != 72:
            raise ValueError(
                "coorte Top 15 por tipo deveria conter 72 CNPJs distintos; "
                f"contém {len(rows)}"
            )
        return rows

    if scope_csv is not None:
        source = pd.read_csv(scope_csv, dtype=str, keep_default_na=False)
        if scope_filter_column:
            if scope_filter_column not in source.columns:
                raise ValueError(
                    f"escopo documental sem coluna de filtro: {scope_filter_column}"
                )
            source = source[
                source[scope_filter_column].astype(str).eq(str(scope_filter_value or ""))
            ].copy()
        if scope_cnpj_column not in source.columns:
            raise ValueError(
                f"escopo documental sem coluna CNPJ: {scope_cnpj_column}"
            )
        rows = pd.DataFrame(
            {
                "cnpj": source[scope_cnpj_column].map(normalize_cnpj),
                "nome_oficial_cvm": (
                    source[scope_name_column]
                    if scope_name_column in source.columns
                    else "N/D"
                ),
            }
        )
        rows = rows[rows["cnpj"].ne("")].drop_duplicates("cnpj", keep="first")
        rows = rows.reset_index(drop=True)
        rows.insert(0, "ordem", range(1, len(rows) + 1))
        rows["nome_referencia"] = rows["nome_oficial_cvm"]
        if rows.empty:
            raise ValueError("escopo documental alternativo não contém CNPJ válido")
        if rows["cnpj"].duplicated().any():
            raise ValueError("escopo documental alternativo contém CNPJ duplicado")
        return rows

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    rows = pd.DataFrame(payload.get("portfolio_export_carteira_101") or [])
    if len(rows) != 101:
        raise ValueError(f"payload precisa conter 101 CNPJs; contém {len(rows)}")
    rows["cnpj"] = rows["cnpj"].map(normalize_cnpj)
    if rows["cnpj"].eq("").any() or rows["cnpj"].duplicated().any():
        raise ValueError("payload contém CNPJ vazio ou duplicado")
    return rows.sort_values("ordem", kind="stable").reset_index(drop=True)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _cache_by_document_key(cache_dir: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in cache_dir.glob("*/*.json.gz"):
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        key = str(payload.get("document_key") or "")
        if key:
            result[key] = path
    return result


def _date_key(value: object) -> tuple[int, int, int]:
    text = str(value or "")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%Y %H:%M", "%m/%Y"):
        try:
            parsed = datetime.strptime(text[:19], fmt)
            return parsed.year, parsed.month, parsed.day
        except ValueError:
            continue
    match = re.search(r"(20\d{2})[-_](\d{2})[-_](\d{2})", text)
    return tuple(map(int, match.groups())) if match else (0, 0, 0)


def _source_from_cached_json(path: Path, row: pd.Series) -> DocumentSource | None:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    pages = tuple(
        (int(item.get("page_number") or index), str(item.get("text") or ""))
        for index, item in enumerate(payload.get("pages") or [], start=1)
        if isinstance(item, dict)
    )
    text = "\n".join(page_text for _, page_text in pages)
    description = " ".join(
        str(value or "")
        for value in (
            row.get("document_class"),
            row.get("documento_origem"),
            row.get("source_value"),
        )
    )
    source_id = str(row.get("documento_id") or "")
    return DocumentSource(
        cnpj=normalize_cnpj(row.get("cnpj_fundo")),
        source_kind=classify_source_kind(
            document_class=row.get("document_class"), description=description
        ),
        source_id=source_id or str(row.get("document_key") or ""),
        document_class=str(row.get("document_class") or ""),
        document_date=str(row.get("document_date") or ""),
        source_path=str(row.get("local_path") or payload.get("source_path") or path),
        source_url=fundonet_download_url(source_id),
        text=text,
        pages=pages,
    )


def load_local_inventory_sources(
    inventory_path: Path,
    cache_dir: Path,
    cnpjs: set[str],
    *,
    max_docs_per_kind: int,
) -> dict[str, list[DocumentSource]]:
    if not inventory_path.exists() or not cache_dir.exists():
        return {}
    inventory = pd.read_csv(inventory_path, dtype={"cnpj_fundo": str}, low_memory=False)
    inventory["cnpj"] = inventory["cnpj_fundo"].map(normalize_cnpj)
    inventory = inventory[inventory["cnpj"].isin(cnpjs)].copy()
    key_to_cache = _cache_by_document_key(cache_dir)
    inventory["_cache_path"] = inventory["document_key"].astype(str).map(key_to_cache)
    inventory = inventory[inventory["_cache_path"].notna()].copy()
    inventory["_kind"] = inventory.apply(
        lambda row: classify_source_kind(
            document_class=row.get("document_class"),
            description=" ".join(
                str(value or "")
                for value in (row.get("documento_origem"), row.get("source_value"))
            ),
        ),
        axis=1,
    )
    inventory["_date_key"] = inventory["document_date"].map(_date_key)
    selected: list[pd.Series] = []
    for (_, _), group in inventory.groupby(["cnpj", "_kind"], dropna=False):
        group = group.sort_values("_date_key", ascending=False, kind="stable")
        selected.extend(row for _, row in group.head(max_docs_per_kind).iterrows())
    output: dict[str, list[DocumentSource]] = {}
    for row in selected:
        source = _source_from_cached_json(Path(row["_cache_path"]), row)
        if source and source.text.strip():
            output.setdefault(source.cnpj, []).append(source)
    return output


_DIRECTOR_FILE_RE = re.compile(
    r"^(?P<cnpj>\d{14})_(?P<doc_id>\d+)_(?P<description>.+?)\.txt$"
)


def load_director_cache_sources(
    cache_dir: Path,
    cnpjs: set[str],
    *,
    max_docs_per_kind: int,
) -> dict[str, list[DocumentSource]]:
    if not cache_dir.exists():
        return {}
    candidates: dict[tuple[str, str], list[tuple[tuple[int, int, int], Path, re.Match[str]]]] = {}
    for path in cache_dir.glob("*.txt"):
        match = _DIRECTOR_FILE_RE.match(path.name)
        if not match or match.group("cnpj") not in cnpjs:
            continue
        description = match.group("description")
        kind = classify_source_kind(document_class="", description=description)
        candidates.setdefault((match.group("cnpj"), kind), []).append(
            (_date_key(description), path, match)
        )
    output: dict[str, list[DocumentSource]] = {}
    for (cnpj, kind), rows in candidates.items():
        for _, path, match in sorted(rows, reverse=True)[:max_docs_per_kind]:
            text = path.read_text(encoding="utf-8", errors="replace")
            source_id = match.group("doc_id")
            date_match = re.findall(r"20\d{2}-\d{2}-\d{2}", match.group("description"))
            output.setdefault(cnpj, []).append(
                DocumentSource(
                    cnpj=cnpj,
                    source_kind=kind,
                    source_id=source_id,
                    document_class=kind,
                    document_date=date_match[-1] if date_match else "",
                    source_path=str(path),
                    source_url=fundonet_download_url(source_id),
                    text=text,
                )
            )
    return output


def load_structured_candidates(path: Path, cnpjs: set[str]) -> list[Evidence]:
    """Keep heuristically extracted parties in the log without promoting them."""

    if not path.exists():
        return []
    frame = pd.read_csv(path, dtype={"cnpj_fundo": str}, low_memory=False)
    frame["cnpj"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame = frame[frame["cnpj"].isin(cnpjs)]
    results: list[Evidence] = []
    field_map = {
        "cedente_originador": "cedente",
        "originador": "originador",
        "cedente": "cedente",
        "sacado_devedor": "sacado_devedor",
    }
    for _, row in frame.iterrows():
        field = field_map.get(str(row.get("participant_type") or ""))
        if not field:
            continue
        value = row.get("nome_fantasia")
        if is_missing(value):
            value = row.get("razao_social")
        if is_missing(value):
            value = row.get("cnpj_participante")
        if is_missing(value):
            continue
        document = compact_text(row.get("documento_origem"), limit=500)
        doc_id_match = re.search(r"(?:^|_)(\d{5,})(?:_|$)", document)
        doc_id = doc_id_match.group(1) if doc_id_match else document
        results.append(
            Evidence(
                cnpj=row["cnpj"],
                field=field,
                value=compact_text(value, limit=500),
                source_kind="candidate_extraction",
                source_id=doc_id,
                document_class="extração heurística",
                document_date="",
                source_path=compact_text(row.get("source_cache"), limit=600),
                source_url=fundonet_download_url(doc_id),
                page=compact_text(row.get("pagina"), limit=60),
                status="candidato_revisao",
                confidence=float(pd.to_numeric(row.get("score_confianca_final"), errors="coerce") or 0),
                excerpt=compact_text(row.get("evidencia"), limit=1200),
            )
        )
    return deduplicate_evidence(results)


def _document_descriptor(document: Any) -> str:
    return " ".join(
        str(value or "")
        for value in (
            document.categoria,
            document.tipo,
            document.especie,
            document.nome_arquivo,
        )
    )


def _online_documents_to_scan(documents: list[Any], max_per_kind: int) -> list[Any]:
    grouped: dict[str, list[Any]] = {}
    for document in documents:
        kind = classify_source_kind(description=_document_descriptor(document))
        if kind not in {"rating_report", "regulamento", "emissao", "assembleia", "informe_mensal"}:
            continue
        if kind == "informe_mensal":
            # The IME is retained as an inventory fallback; downloading every
            # monthly XML/PDF would add volume without contractual clauses.
            continue
        grouped.setdefault(kind, []).append(document)
    selected: list[Any] = []
    for kind in sorted(grouped, key=source_priority):
        selected.extend(
            sorted(
                grouped[kind],
                key=lambda doc: (
                    _date_key(doc.data_referencia or doc.data_entrega),
                    int(doc.versao or 0),
                    int(doc.id),
                ),
                reverse=True,
            )[:max_per_kind]
        )
    return selected


def _cached_online_source(
    cache_dir: Path,
    cnpj: str,
    document: Any,
) -> DocumentSource | None:
    path = cache_dir / cnpj / f"{document.id}.json.gz"
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    pages = tuple(
        (int(row["page"]), str(row["text"]))
        for row in payload.get("pages") or []
        if isinstance(row, dict)
    )
    return DocumentSource(
        cnpj=cnpj,
        source_kind=payload["source_kind"],
        source_id=str(document.id),
        document_class=payload["document_class"],
        document_date=payload["document_date"],
        source_path=str(path),
        source_url=fundonet_download_url(document.id),
        text="\n".join(text for _, text in pages),
        pages=pages,
    )


def load_runtime_cache_sources(
    cache_dir: Path,
    cnpjs: set[str],
    *,
    max_docs_per_kind: int,
) -> dict[str, list[DocumentSource]]:
    """Load downloaded FundosNet documents without making a network request."""

    grouped: dict[str, dict[str, list[DocumentSource]]] = {}
    for cnpj in sorted(cnpjs):
        for path in (cache_dir / cnpj).glob("*.json.gz"):
            try:
                with gzip.open(path, "rt", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                continue
            pages = tuple(
                (int(row["page"]), str(row["text"]))
                for row in payload.get("pages") or []
                if isinstance(row, dict) and "page" in row and "text" in row
            )
            source_id = str(payload.get("document_id") or path.name.split(".", 1)[0])
            source = DocumentSource(
                cnpj=cnpj,
                source_kind=str(payload.get("source_kind") or "outro"),
                source_id=source_id,
                document_class=str(payload.get("document_class") or ""),
                document_date=str(payload.get("document_date") or ""),
                source_path=str(path),
                source_url=str(
                    payload.get("source_url") or fundonet_download_url(source_id)
                ),
                text="\n".join(text for _, text in pages),
                pages=pages,
            )
            grouped.setdefault(cnpj, {}).setdefault(source.source_kind, []).append(source)

    result: dict[str, list[DocumentSource]] = {}
    for cnpj, by_kind in grouped.items():
        selected: list[DocumentSource] = []
        for kind in sorted(by_kind, key=source_priority):
            selected.extend(
                sorted(
                    by_kind[kind],
                    key=lambda item: (
                        _date_key(item.document_date),
                        int(item.source_id) if item.source_id.isdigit() else 0,
                    ),
                    reverse=True,
                )[:max_docs_per_kind]
            )
        result[cnpj] = selected
    return result


def _download_online_source(
    client: FundosNetClient,
    cache_dir: Path,
    cnpj: str,
    document: Any,
    *,
    max_pages: int,
) -> DocumentSource:
    cached = _cached_online_source(cache_dir, cnpj, document)
    if cached is not None:
        return cached
    from pypdf import PdfReader

    content = client.download_documento(document.id)
    reader = PdfReader(BytesIO(content))
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages[:max_pages], start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        pages.append((index, text))
    kind = classify_source_kind(description=_document_descriptor(document))
    document_date = str(document.data_referencia or document.data_entrega or "")
    path = cache_dir / cnpj / f"{document.id}.json.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "cnpj": cnpj,
        "source_kind": kind,
        "document_class": compact_text(_document_descriptor(document), limit=600),
        "document_date": document_date,
        "document_id": document.id,
        "source_url": fundonet_download_url(document.id),
        "downloaded_at_utc": utc_now_iso(),
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "pages": [{"page": page, "text": text} for page, text in pages],
    }
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    return DocumentSource(
        cnpj=cnpj,
        source_kind=kind,
        source_id=str(document.id),
        document_class=payload["document_class"],
        document_date=document_date,
        source_path=str(path),
        source_url=payload["source_url"],
        text="\n".join(text for _, text in pages),
        pages=tuple(pages),
    )


def scan_online(
    cnpj: str,
    *,
    runtime_cache: Path,
    timeout_seconds: int,
    max_docs_per_kind: int,
    max_pages: int,
    known_document_ids: set[str] | None = None,
) -> tuple[list[DocumentSource], str, list[str], int]:
    client = FundosNetClient(timeout_seconds=timeout_seconds, max_retries=2)
    errors: list[str] = []
    try:
        documents = client.listar_documentos(
            cnpj, page_size=200, error_stage="listar_documentos_fast"
        )
    except Exception as exc:  # noqa: BLE001
        return [], f"erro: {type(exc).__name__}", [str(exc)], 0
    selected = _online_documents_to_scan(documents, max_docs_per_kind)
    known = {str(value) for value in (known_document_ids or set()) if str(value)}
    sources: list[DocumentSource] = []
    for document in selected:
        if str(document.id) in known:
            continue
        try:
            sources.append(
                _download_online_source(
                    client,
                    runtime_cache,
                    cnpj,
                    document,
                    max_pages=max_pages,
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"doc {document.id}: {type(exc).__name__}: {exc}")
    status = "consultado" if documents else "sem_documentos"
    return sources, status, errors, len(documents)


def load_prices(db_path: Path, cnpjs: set[str]) -> list[PriceEvidence]:
    resolved = _resolve_credit_strategy_db(db_path)
    if not resolved.exists():
        return []
    with sqlite3.connect(resolved) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table'"
            )
        }
        if "pricing_tranche_enriched" not in tables:
            return []
        frame = pd.read_sql_query("select * from pricing_tranche_enriched", connection)
    return price_rows_from_sqlite(frame, cnpjs)


def _resolve_credit_strategy_db(requested: Path) -> Path:
    """Resolve the local analytical DB without embedding a user-specific path."""

    candidates = [requested]
    configured = os.environ.get("FIDC_CREDIT_STRATEGY_DB", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--git-common-dir"],
            check=True,
            capture_output=True,
            text=True,
        )
        common_dir = Path(result.stdout.strip())
        if not common_dir.is_absolute():
            common_dir = (ROOT / common_dir).resolve()
        primary_root = common_dir.parent if common_dir.name == ".git" else ROOT
        candidates.append(
            primary_root / "data/fidc_credit_strategy/fidc_credit_strategy.sqlite"
        )
    except (OSError, subprocess.CalledProcessError):
        pass
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return requested


def _serialize_status(checkpoint: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    return {
        cnpj: {
            "status": row.get("status"),
            "sources_consulted": row.get("sources_consulted"),
            "online_status": row.get("online_status"),
            "errors": row.get("errors") or [],
        }
        for cnpj, row in checkpoint.items()
    }


def _unique_strings(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _online_history(previous: dict[str, object] | None) -> list[dict[str, object]]:
    """Return an append-only attempt log, migrating pre-v2 checkpoints."""

    history = [
        dict(item)
        for item in ((previous or {}).get("online_attempts") or [])
        if isinstance(item, dict)
    ]
    previous_status = str((previous or {}).get("online_status") or "").strip()
    if previous_status and not history:
        history.append(
            {
                "attempted_at_utc": (previous or {}).get("completed_at_utc"),
                "status": previous_status,
                "errors": list((previous or {}).get("errors") or []),
                "mode": "checkpoint_migration",
            }
        )
    return history


def _best_online_status(
    history: Iterable[dict[str, object]],
    *,
    runtime_cache_present: bool,
) -> str:
    """Preserve the best completed query when a later retry is transiently down."""

    statuses = [str(item.get("status") or "") for item in history]
    if "consultado" in statuses:
        return "consultado"
    if "sem_documentos" in statuses:
        return "sem_documentos"
    # A populated per-CNPJ download cache proves that an earlier inventory query
    # completed even when a later interrupted replay overwrote its status.
    if runtime_cache_present:
        return "consultado"
    for status in reversed(statuses):
        if status:
            return status
    return "não solicitado"


def write_outputs(
    *,
    args: argparse.Namespace,
    portfolio: pd.DataFrame,
    before: list[Evidence],
    after: list[Evidence],
    prices: list[PriceEvidence],
    checkpoint: dict[str, dict[str, object]],
    started_at: str,
) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cnpjs = portfolio["cnpj"].tolist()
    audit = build_audit_table(
        portfolio, after, scan_status=_serialize_status(checkpoint)
    )
    coverage = coverage_table(before, after, cnpjs)
    evidence = evidence_frame(after)
    price_table = price_frame(prices)

    prefix = str(args.output_prefix).strip()
    if not re.fullmatch(r"[a-z0-9_]+", prefix):
        raise ValueError(f"prefixo de saída inválido: {prefix!r}")
    audit_path = args.output_dir / f"{prefix}_audit.csv"
    coverage_path = args.output_dir / f"{prefix}_coverage.csv"
    evidence_path = args.output_dir / f"{prefix}_evidence.csv.gz"
    prices_path = args.output_dir / f"{prefix}_prices.csv.gz"
    audit.to_csv(audit_path, index=False)
    coverage.to_csv(coverage_path, index=False)
    evidence.to_csv(evidence_path, index=False, compression="gzip")
    price_table.to_csv(prices_path, index=False, compression="gzip")

    scan_rows = list(checkpoint.values())
    online_was_requested = bool(args.online) or any(
        str(row.get("online_status") or "") not in {"", "não solicitado"}
        for row in scan_rows
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "scope_name": args.scope_name,
        "generated_at_utc": utc_now_iso(),
        "started_at_utc": started_at,
        "portfolio_cnpjs": len(cnpjs),
        "checkpoint_cnpjs": len(checkpoint),
        "completed_cnpjs": sum(row.get("status") == "concluído" for row in scan_rows),
        "online_requested": online_was_requested,
        "materialization_mode": "online" if args.online else "cache_only_reextract",
        "online_scan_parameters": {
            "max_documents_per_source_kind": args.max_docs_per_kind,
            "max_pages_per_document": args.max_pages,
            "timeout_seconds": args.timeout_seconds,
            "party_label_parser_version": PARTY_LABEL_PARSER_VERSION,
            "price_parser_version": PRICE_PARSER_VERSION,
            "remuneration_parser_version": REMUNERATION_PARSER_VERSION,
        },
        "online_consulted_cnpjs": sum(
            row.get("online_status") in {"consultado", "sem_documentos"}
            for row in scan_rows
        ),
        "online_error_cnpjs": sum(
            str(row.get("online_status") or "").startswith("erro")
            for row in scan_rows
        ),
        "online_retry_error_cnpjs": sum(
            any(
                str(attempt.get("status") or "").startswith("erro")
                for attempt in (row.get("online_attempts") or [])
                if isinstance(attempt, dict)
            )
            for row in scan_rows
        ),
        "source_order": [
            "rating_report",
            "regulamento/suplemento/emissao",
            "assembleia",
            "informe_mensal",
        ],
        "rules": {
            "missing_is_zero": False,
            "fund_name_inference": False,
            "candidate_extraction_improves_coverage": False,
            "price_definition": "VNU/preço unitário por classe ou série; remuneração e quantidade excluídas",
            "remuneration_definition": (
                "rentabilidade-alvo/benchmark da cota ou série; CDI/DI, % CDI, "
                "IPCA e demais indexadores preservados sem conversão"
            ),
        },
        "audited_fields": list(AUDITED_FIELDS),
        "coverage": coverage.to_dict(orient="records"),
        "prices": {
            "rows": len(price_table),
            "cnpjs": int(price_table["cnpj"].nunique()) if not price_table.empty else 0,
            "fields": [
                "cnpj",
                "class_series",
                "price_display",
                "price_nature",
                "document_date",
                "source_id",
                "source_url",
                "exception_flag",
                "exception_reason",
            ],
        },
        "inputs": {
            str(path): {
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in (
                args.scope_csv or args.payload,
                args.inventory,
                args.structured_parties,
            )
            if path.exists()
        },
        "outputs": {
            path.name: {
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in (audit_path, coverage_path, evidence_path, prices_path)
        },
        "checkpoint": str(args.output_dir / f"{prefix}_checkpoint.jsonl"),
    }
    manifest_path = args.output_dir / f"{prefix}_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Cobertura antes/depois:")
    print(coverage.to_string(index=False))
    print(f"Preços unitários: {len(price_table)} linhas / {manifest['prices']['cnpjs']} CNPJs")
    print(f"Manifesto: {manifest_path}")


def main() -> None:
    args = parse_args()
    started_at = utc_now_iso()
    portfolio = load_portfolio(
        args.payload,
        scope_csv=args.scope_csv,
        scope_cnpj_column=args.scope_cnpj_column,
        scope_name_column=args.scope_name_column,
        scope_filter_column=args.scope_filter_column,
        scope_filter_value=args.scope_filter_value,
        top15_ranking_scope=args.top15_ranking_scope,
    )
    if args.max_cnpjs > 0:
        portfolio = portfolio.head(args.max_cnpjs).copy()
    cnpjs = set(portfolio["cnpj"])
    before = payload_evidence(portfolio)
    candidates = load_structured_candidates(args.structured_parties, cnpjs)
    prices = load_prices(args.credit_strategy_db, cnpjs)

    local_sources = load_local_inventory_sources(
        args.inventory,
        args.text_cache,
        cnpjs,
        max_docs_per_kind=args.max_docs_per_kind,
    )
    director_sources = load_director_cache_sources(
        args.director_cache,
        cnpjs,
        max_docs_per_kind=args.max_docs_per_kind,
    )
    runtime_sources = load_runtime_cache_sources(
        args.runtime_cache,
        cnpjs,
        max_docs_per_kind=args.max_docs_per_kind,
    )

    checkpoint_path = (
        args.output_dir / f"{args.output_prefix}_checkpoint.jsonl"
    )
    checkpoint = {} if args.force else read_checkpoint(checkpoint_path)
    checkpoint = {
        cnpj: row for cnpj, row in checkpoint.items() if cnpj in cnpjs
    }
    for index, row in portfolio.iterrows():
        cnpj = row["cnpj"]
        previous = checkpoint.get(cnpj)
        if previous:
            previous_attempts = _online_history(previous)
            previous_runtime_cache_present = bool(runtime_sources.get(cnpj))
            if (
                previous_runtime_cache_present
                and not any(
                    str(item.get("status") or "") in ONLINE_SUCCESS_STATUSES
                    for item in previous_attempts
                )
            ):
                previous_attempts.append(
                    {
                        "attempted_at_utc": utc_now_iso(),
                        "status": "consultado",
                        "errors": [],
                        "mode": "recovered_from_runtime_cache",
                    }
                )
            previous["online_attempts"] = previous_attempts
            previous["online_status"] = _best_online_status(
                previous_attempts,
                runtime_cache_present=previous_runtime_cache_present,
            )
        previous_online_ok = previous and previous.get("online_status") in {
            "consultado",
            "sem_documentos",
        }
        previous_depth_ok = (
            int((previous or {}).get("max_documents_per_source_kind") or 0)
            >= args.max_docs_per_kind
        )
        previous_parser_ok = (
            int((previous or {}).get("party_label_parser_version") or 0)
            >= PARTY_LABEL_PARSER_VERSION
        )
        previous_price_parser_ok = (
            int((previous or {}).get("price_parser_version") or 0)
            >= PRICE_PARSER_VERSION
        )
        previous_remuneration_parser_ok = (
            int((previous or {}).get("remuneration_parser_version") or 0)
            >= REMUNERATION_PARSER_VERSION
        )
        if previous and previous.get("status") == "concluído" and (
            (
                not args.online
                and previous_parser_ok
                and previous_price_parser_ok
                and previous_remuneration_parser_ok
            )
            or (
                args.online
                and previous_online_ok
                and previous_depth_ok
                and previous_parser_ok
                and previous_price_parser_ok
                and previous_remuneration_parser_ok
            )
        ):
            print(f"[{index + 1}/{len(portfolio)}] {cnpj} · checkpoint")
            continue

        errors: list[str] = list((previous or {}).get("errors") or [])
        sources_by_identity: dict[tuple[str, str], DocumentSource] = {}
        for source in [
            *(local_sources.get(cnpj) or []),
            *(director_sources.get(cnpj) or []),
            *(runtime_sources.get(cnpj) or []),
        ]:
            key = (source.source_kind, source.source_id)
            current = sources_by_identity.get(key)
            if current is None or bool(source.pages) > bool(current.pages):
                sources_by_identity[key] = source

        online_attempts = _online_history(previous)
        runtime_cache_present = bool(runtime_sources.get(cnpj))
        online_status = _best_online_status(
            online_attempts,
            runtime_cache_present=runtime_cache_present,
        )
        if (
            runtime_cache_present
            and not any(
                str(item.get("status") or "") in ONLINE_SUCCESS_STATUSES
                for item in online_attempts
            )
        ):
            online_attempts.append(
                {
                    "attempted_at_utc": utc_now_iso(),
                    "status": "consultado",
                    "errors": [],
                    "mode": "recovered_from_runtime_cache",
                }
            )
            online_status = "consultado"
        online_inventory_count = (
            0
            if args.online or not previous
            else int(previous.get("online_inventory_documents") or 0)
        )
        if args.online:
            print(f"[{index + 1}/{len(portfolio)}] {cnpj} · FundosNet")
            online_sources, attempt_status, online_errors, online_inventory_count = scan_online(
                cnpj,
                runtime_cache=args.runtime_cache,
                timeout_seconds=args.timeout_seconds,
                max_docs_per_kind=args.max_docs_per_kind,
                max_pages=args.max_pages,
                known_document_ids={source_id for _, source_id in sources_by_identity},
            )
            errors.extend(online_errors)
            online_attempts.append(
                {
                    "attempted_at_utc": utc_now_iso(),
                    "status": attempt_status,
                    "errors": online_errors,
                    "mode": "online",
                }
            )
            online_status = _best_online_status(
                online_attempts,
                runtime_cache_present=runtime_cache_present or bool(online_sources),
            )
            for source in online_sources:
                sources_by_identity[(source.source_kind, source.source_id)] = source
        else:
            print(f"[{index + 1}/{len(portfolio)}] {cnpj} · fontes locais")

        # A deeper follow-up scan is a monotonic enrichment.  Preserve evidence
        # already checkpointed so a transient provider timeout cannot erase a
        # document downloaded in an earlier pass.
        previous_evidence: list[Evidence] = []
        previous_prices: list[PriceEvidence] = []
        if previous:
            previous_evidence, previous_prices = evidence_from_checkpoint(
                {cnpj: previous}
            )
            # Participant-table parsing is intentionally versioned by replay:
            # remove older automatic table-label rows and regenerate them from
            # the currently selected rating reports.  Accepted payload evidence
            # and contractual definitions remain monotonic.
            previous_evidence = [
                item
                for item in previous_evidence
                if not item.nature.startswith("rótulo explícito de participante")
            ]
            if int(previous.get("price_parser_version") or 0) < PRICE_PARSER_VERSION:
                previous_prices = []
            if (
                int(previous.get("remuneration_parser_version") or 0)
                < REMUNERATION_PARSER_VERSION
            ):
                previous_evidence = [
                    item
                    for item in previous_evidence
                    if item.field != "remuneracao_alvo"
                ]
        found: list[Evidence] = list(previous_evidence)
        found_prices: list[PriceEvidence] = list(previous_prices)
        for source in sorted(
            sources_by_identity.values(),
            key=lambda item: (
                source_priority(item.source_kind),
                item.document_date,
                item.source_id,
            ),
        ):
            try:
                source_evidence, source_prices = extract_document_evidence(source)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"extração {source.source_id}: {type(exc).__name__}: {exc}"
                )
                continue
            found.extend(source_evidence)
            found_prices.extend(source_prices)

        checkpoint[cnpj] = {
            "schema_version": SCHEMA_VERSION,
            "cnpj": cnpj,
            "nome_fundo": row.get("nome_oficial_cvm") or row.get("nome_referencia"),
            "status": "concluído",
            "completed_at_utc": utc_now_iso(),
            "sources_consulted": len(sources_by_identity),
            "local_inventory_sources": len(local_sources.get(cnpj) or []),
            "director_cache_sources": len(director_sources.get(cnpj) or []),
            "runtime_cache_sources": len(runtime_sources.get(cnpj) or []),
            "online_status": online_status,
            "online_attempts": online_attempts,
            "online_inventory_documents": online_inventory_count,
            "max_documents_per_source_kind": args.max_docs_per_kind,
            "max_pages_per_document": args.max_pages,
            "party_label_parser_version": PARTY_LABEL_PARSER_VERSION,
            "price_parser_version": PRICE_PARSER_VERSION,
            "remuneration_parser_version": REMUNERATION_PARSER_VERSION,
            "errors": _unique_strings(errors),
            "evidence": serialize_evidence(found),
            "prices": serialize_prices(found_prices),
        }
        write_checkpoint(checkpoint_path, checkpoint)

    # Rewrite the complete checkpoint with the current schema version even when
    # every CNPJ was resumed from a prior run.
    for checkpoint_row in checkpoint.values():
        checkpoint_row["schema_version"] = SCHEMA_VERSION
    write_checkpoint(checkpoint_path, checkpoint)

    checkpoint_evidence, checkpoint_prices = evidence_from_checkpoint(checkpoint)
    after = deduplicate_evidence([*before, *candidates, *checkpoint_evidence])
    prices = deduplicate_prices([*prices, *checkpoint_prices])
    write_outputs(
        args=args,
        portfolio=portfolio,
        before=before,
        after=after,
        prices=prices,
        checkpoint=checkpoint,
        started_at=started_at,
    )


if __name__ == "__main__":
    main()
