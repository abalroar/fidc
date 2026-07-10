from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from services.industry_study import file_fingerprint, normalize_cnpj
from services.regulatory_knowledge import classify_document


ALTERNATIVE_DOCUMENT_COLUMNS = [
    "discovery_id",
    "source_dataset",
    "source_dataset_url",
    "source_year",
    "cnpj_fundo",
    "package_ids",
    "work_tier",
    "batch_id",
    "nome_exibicao",
    "document_id",
    "document_class",
    "document_type",
    "fund_type",
    "reference_date",
    "received_date",
    "source_filename",
    "source_url",
    "download_status",
    "local_path",
    "bytes",
    "sha256",
    "error_message",
    "discovered_at_utc",
]

ALTERNATIVE_DOCUMENT_STATUS_COLUMNS = [
    "cnpj_fundo",
    "package_ids",
    "work_tier",
    "batch_id",
    "nome_exibicao",
    "listing_status",
    "source_years",
    "documents_listed",
    "documents_relevant",
    "documents_downloaded",
    "documents_reused",
    "document_errors",
    "document_types",
    "latest_reference_date",
    "error_message",
    "attempted_at_utc",
]

_CONSTITUTIVE_TYPES = {"REGUL FDO", "SGF ANEXO", "SGF APENDICE"}


def _join_unique(values: pd.Series, *, separator: str = " | ") -> str:
    seen: list[str] = []
    for value in values.fillna("").astype(str):
        for part in value.split("|"):
            text = part.strip()
            if text and text not in seen:
                seen.append(text)
    return separator.join(seen)


def _source_year(value: object) -> str:
    match = re.search(r"\b(20\d{2})\b", str(value or ""))
    return match.group(1) if match else ""


def select_alternative_document_targets(
    evidence: pd.DataFrame,
    *,
    work_tiers: tuple[str, ...] = ("P0 competência",),
    technical_stages: tuple[str, ...] = ("fontes alternativas",),
    max_funds: int = 25,
) -> pd.DataFrame:
    columns = [
        "cnpj_fundo",
        "package_ids",
        "work_tier",
        "batch_id",
        "nome_exibicao",
        "source_years",
    ]
    if evidence is None or evidence.empty:
        return pd.DataFrame(columns=columns)
    frame = evidence.copy()
    for col in [
        "package_id",
        "cnpj_fundo",
        "work_tier",
        "batch_id",
        "nome_exibicao",
        "competencia",
        "technical_stage",
        "scope_status",
    ]:
        if col not in frame.columns:
            frame[col] = ""
        frame[col] = frame[col].fillna("").astype(str)
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame = frame[
        frame["cnpj_fundo"].str.len().eq(14)
        & ~frame["scope_status"].isin({"revisar universo", "excluído por revisão"})
    ].copy()
    if technical_stages:
        frame = frame[frame["technical_stage"].isin(technical_stages)].copy()
    if work_tiers:
        frame = frame[frame["work_tier"].isin(work_tiers)].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["_source_year"] = frame["competencia"].map(_source_year)
    records: list[dict[str, object]] = []
    for cnpj, group in frame.groupby("cnpj_fundo", sort=False):
        first = group.iloc[0]
        records.append(
            {
                "cnpj_fundo": cnpj,
                "package_ids": _join_unique(group["package_id"]),
                "work_tier": first["work_tier"],
                "batch_id": first["batch_id"],
                "nome_exibicao": first["nome_exibicao"],
                "source_years": _join_unique(group["_source_year"], separator=","),
            }
        )
    targets = pd.DataFrame(records).sort_values(["work_tier", "batch_id", "cnpj_fundo"])
    if max_funds > 0:
        targets = targets.head(int(max_funds))
    return targets[columns].reset_index(drop=True)


def classify_cvm_eventual_document(document_type: object, filename: object = "") -> str:
    normalized_type = str(document_type or "").strip().upper()
    if normalized_type in _CONSTITUTIVE_TYPES:
        return "regulamento"
    return classify_document(tipo=str(document_type or ""), nome_arquivo=str(filename or ""))


def build_cvm_eventual_candidates(
    eventual: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    source_year: int,
    dataset_url: str,
    discovered_at_utc: str | None = None,
) -> pd.DataFrame:
    if eventual is None or eventual.empty or targets is None or targets.empty:
        return pd.DataFrame(columns=ALTERNATIVE_DOCUMENT_COLUMNS)
    frame = eventual.copy()
    for col in [
        "CNPJ_FUNDO_CLASSE",
        "DENOM_SOCIAL",
        "DT_COMPTC",
        "DT_RECEB",
        "ID_DOC",
        "TP_DOC",
        "TP_FUNDO_CLASSE",
        "NM_ARQ",
        "LINK_ARQ",
    ]:
        if col not in frame.columns:
            frame[col] = ""
        frame[col] = frame[col].fillna("").astype(str)
    frame["cnpj_fundo"] = frame["CNPJ_FUNDO_CLASSE"].map(normalize_cnpj)
    target_frame = targets.copy()
    target_frame["cnpj_fundo"] = target_frame["cnpj_fundo"].map(normalize_cnpj)
    target_columns = ["cnpj_fundo", "package_ids", "work_tier", "batch_id", "nome_exibicao"]
    frame = frame.merge(target_frame[target_columns].drop_duplicates("cnpj_fundo"), on="cnpj_fundo", how="inner")
    if frame.empty:
        return pd.DataFrame(columns=ALTERNATIVE_DOCUMENT_COLUMNS)
    frame["document_class"] = [
        classify_cvm_eventual_document(doc_type, filename)
        for doc_type, filename in zip(frame["TP_DOC"], frame["NM_ARQ"])
    ]
    frame = frame[frame["document_class"].isin({"regulamento", "emissao", "assembleia", "evento"})].copy()
    frame = frame[frame["LINK_ARQ"].str.strip().ne("")].copy()
    direct_keys = {
        (row["cnpj_fundo"], row["TP_DOC"], row["DT_COMPTC"])
        for _, row in frame[frame["NM_ARQ"].str.strip().ne("")].iterrows()
    }
    duplicate_fnet = frame.apply(
        lambda row: (
            not str(row["NM_ARQ"]).strip()
            and (row["cnpj_fundo"], row["TP_DOC"], row["DT_COMPTC"]) in direct_keys
        ),
        axis=1,
    )
    frame = frame[~duplicate_fnet].copy()
    if frame.empty:
        return pd.DataFrame(columns=ALTERNATIVE_DOCUMENT_COLUMNS)
    discovered_at = discovered_at_utc or datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        source_url = str(row["LINK_ARQ"]).strip()
        source_filename = str(row["NM_ARQ"]).strip() or Path(source_url).name
        document_id = str(row["ID_DOC"]).strip()
        if not document_id:
            document_id = hashlib.sha1(source_url.encode("utf-8", errors="ignore")).hexdigest()[:16]
        rows.append(
            {
                "discovery_id": f"cvm_eventual:{source_year}:{row['cnpj_fundo']}:{document_id}",
                "source_dataset": "CVM FI Documentos Eventuais",
                "source_dataset_url": dataset_url,
                "source_year": int(source_year),
                "cnpj_fundo": row["cnpj_fundo"],
                "package_ids": row["package_ids"],
                "work_tier": row["work_tier"],
                "batch_id": row["batch_id"],
                "nome_exibicao": row["nome_exibicao"] or row["DENOM_SOCIAL"],
                "document_id": document_id,
                "document_class": row["document_class"],
                "document_type": row["TP_DOC"],
                "fund_type": row["TP_FUNDO_CLASSE"],
                "reference_date": row["DT_COMPTC"],
                "received_date": row["DT_RECEB"],
                "source_filename": source_filename,
                "source_url": source_url,
                "download_status": "listado",
                "local_path": "",
                "bytes": 0,
                "sha256": "",
                "error_message": "",
                "discovered_at_utc": discovered_at,
            }
        )
    out = pd.DataFrame(rows)
    return out.drop_duplicates("discovery_id", keep="last")[ALTERNATIVE_DOCUMENT_COLUMNS].reset_index(drop=True)


def merge_alternative_documents(
    existing: pd.DataFrame | None,
    updates: pd.DataFrame | None,
    *,
    key_column: str,
    columns: list[str],
) -> pd.DataFrame:
    frames = [frame.copy() for frame in [existing, updates] if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame(columns=columns)
    combined = pd.concat(frames, ignore_index=True, sort=False)
    for col in columns:
        if col not in combined.columns:
            combined[col] = ""
    combined[key_column] = combined[key_column].fillna("").astype(str)
    combined = combined[combined[key_column].str.strip().ne("")]
    return combined.drop_duplicates(key_column, keep="last")[columns].reset_index(drop=True)


def alternative_documents_to_inventory_sources(documents: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "cnpj_fundo",
        "fundo",
        "setor_n1",
        "setor_n2",
        "source_table",
        "source_field",
        "source_value",
        "document_date_hint",
        "priority_hint",
    ]
    if documents is None or documents.empty:
        return pd.DataFrame(columns=columns)
    frame = documents.copy()
    for col in [
        "cnpj_fundo",
        "nome_exibicao",
        "local_path",
        "reference_date",
        "document_class",
        "document_type",
        "source_url",
        "download_status",
    ]:
        if col not in frame.columns:
            frame[col] = ""
        frame[col] = frame[col].fillna("").astype(str)
    frame = frame[
        frame["download_status"].isin({"baixado", "reutilizado"})
        & frame["local_path"].str.strip().ne("")
    ].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(
        {
            "cnpj_fundo": frame["cnpj_fundo"].map(normalize_cnpj),
            "fundo": frame["nome_exibicao"],
            "setor_n1": "",
            "setor_n2": "",
            "source_table": "cvm_eventual_documents",
            "source_field": "local_path",
            "source_value": frame["local_path"],
            "document_date_hint": frame["reference_date"],
            "priority_hint": (
                frame["document_class"]
                + " | "
                + frame["document_type"]
                + " | "
                + frame["source_url"]
            ),
        },
        columns=columns,
    ).drop_duplicates(["cnpj_fundo", "source_value", "source_table"], keep="last")


def build_alternative_document_status(
    targets: pd.DataFrame,
    documents: pd.DataFrame,
    *,
    attempted_at_utc: str,
) -> pd.DataFrame:
    if targets is None or targets.empty:
        return pd.DataFrame(columns=ALTERNATIVE_DOCUMENT_STATUS_COLUMNS)
    docs = pd.DataFrame() if documents is None else documents.copy()
    rows: list[dict[str, object]] = []
    for _, target in targets.iterrows():
        cnpj = normalize_cnpj(target.get("cnpj_fundo", ""))
        group = docs[docs.get("cnpj_fundo", pd.Series("", index=docs.index)).map(normalize_cnpj).eq(cnpj)].copy()
        download = group.get("download_status", pd.Series("", index=group.index)).fillna("").astype(str)
        errors = group.get("error_message", pd.Series("", index=group.index)).fillna("").astype(str)
        error_values = [value.strip() for value in errors if value.strip()]
        relevant = int(len(group))
        downloaded = int(download.eq("baixado").sum())
        reused = int(download.eq("reutilizado").sum())
        error_count = int(download.eq("erro_download").sum())
        if not relevant:
            listing_status = "sem_documento_alternativo"
        elif error_count:
            listing_status = "parcial"
        elif downloaded or reused:
            listing_status = "ok"
        else:
            listing_status = "listado"
        rows.append(
            {
                "cnpj_fundo": cnpj,
                "package_ids": target.get("package_ids", ""),
                "work_tier": target.get("work_tier", ""),
                "batch_id": target.get("batch_id", ""),
                "nome_exibicao": target.get("nome_exibicao", ""),
                "listing_status": listing_status,
                "source_years": target.get("source_years", ""),
                "documents_listed": relevant,
                "documents_relevant": relevant,
                "documents_downloaded": downloaded,
                "documents_reused": reused,
                "document_errors": error_count,
                "document_types": _join_unique(group.get("document_type", pd.Series(dtype=str))),
                "latest_reference_date": max(group.get("reference_date", pd.Series(dtype=str)), default=""),
                "error_message": " | ".join(dict.fromkeys(error_values)),
                "attempted_at_utc": attempted_at_utc,
            }
        )
    return pd.DataFrame(rows, columns=ALTERNATIVE_DOCUMENT_STATUS_COLUMNS)


def alternative_document_quality_summary(
    documents: pd.DataFrame,
    status: pd.DataFrame,
    *,
    target_funds: int = 0,
) -> dict[str, object]:
    docs = pd.DataFrame() if documents is None else documents.copy()
    states = pd.DataFrame() if status is None else status.copy()
    listing = states.get("listing_status", pd.Series("", index=states.index)).fillna("").astype(str)
    download = docs.get("download_status", pd.Series("", index=docs.index)).fillna("").astype(str)
    return {
        "target_funds": int(target_funds),
        "attempted_funds": int(len(states)),
        "covered_funds": int(listing.eq("ok").sum()),
        "no_document_funds": int(listing.eq("sem_documento_alternativo").sum()),
        "partial_funds": int(listing.eq("parcial").sum()),
        "document_rows": int(len(docs)),
        "relevant_documents": int(len(docs)),
        "downloaded_documents": int(download.eq("baixado").sum()),
        "reused_documents": int(download.eq("reutilizado").sum()),
        "download_error_documents": int(download.eq("erro_download").sum()),
        "regulation_documents": int(docs.get("document_class", pd.Series("", index=docs.index)).eq("regulamento").sum()),
        "document_type_counts": {
            str(key): int(value)
            for key, value in docs.get("document_type", pd.Series(dtype=str)).fillna("").astype(str).value_counts().to_dict().items()
        },
        "listing_status_counts": {str(key): int(value) for key, value in listing.value_counts().to_dict().items()},
        "download_status_counts": {str(key): int(value) for key, value in download.value_counts().to_dict().items()},
    }


def alternative_download_stage_status(quality: dict[str, object]) -> str:
    """Keep historical download errors visible without blocking an empty current queue."""

    if int(quality.get("target_funds", 0) or 0) == 0:
        return "ok"
    return "warning" if int(quality.get("download_error_documents", 0) or 0) else "ok"


def build_alternative_document_manifest(
    *,
    industry_dir: Path,
    raw_dir: Path,
    cache_paths: dict[int, Path],
    evidence_path: Path,
    documents_path: Path,
    status_path: Path,
    manifest_path: Path,
    documents: pd.DataFrame,
    status: pd.DataFrame,
    target_funds: int,
    download_enabled: bool,
) -> dict[str, object]:
    quality = alternative_document_quality_summary(documents, status, target_funds=target_funds)
    return {
        "schema_version": "industry-alternative-document-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_alternative_document_discovery",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "official_sources_only": True,
            "download_enabled": bool(download_enabled),
            "notes": [
                "A fonte é o dataset semanal de Documentos Eventuais da CVM, independente da listagem FNET.",
                "Cada registro preserva URL do dataset, URL do PDF, datas CVM, arquivo local e SHA-256.",
                "A seleção parte exclusivamente de pacotes no estágio fontes alternativas.",
            ],
        },
        "inputs": {
            "package_evidence": file_fingerprint(evidence_path),
            **{f"cvm_eventual_{year}": file_fingerprint(path) for year, path in sorted(cache_paths.items())},
            "raw_dir": {"path": str(raw_dir), "exists": raw_dir.exists()},
        },
        "outputs": {
            "alternative_documents": file_fingerprint(documents_path),
            "alternative_document_status": file_fingerprint(status_path),
            "manifest": {"path": str(manifest_path)},
        },
        "stages": [
            {
                "id": "select_alternative_targets",
                "label": "Selecionar pacotes sem documento FNET",
                "status": "ok",
                "rows": int(target_funds),
                "rerun": "python scripts/build_fidc_industry_alternative_documents.py --max-funds 25",
            },
            {
                "id": "discover_cvm_eventual",
                "label": "Cruzar Documentos Eventuais CVM",
                "status": "ok" if status is not None and not status.empty else "empty",
                "rows": int(len(documents)) if documents is not None else 0,
                "rerun": "python scripts/build_fidc_industry_alternative_documents.py --max-funds 25",
            },
            {
                "id": "download_alternative_documents",
                "label": "Baixar e hashear documentos alternativos",
                "status": alternative_download_stage_status(quality),
                "rows": int(quality.get("downloaded_documents", 0)) + int(quality.get("reused_documents", 0)),
                "rerun": "python scripts/build_fidc_industry_alternative_documents.py --max-funds 25",
            },
        ],
        "quality": quality,
    }
