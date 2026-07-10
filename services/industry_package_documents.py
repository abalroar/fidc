from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from services.industry_study import file_fingerprint, normalize_cnpj


PACKAGE_DOCUMENT_DISCOVERY_COLUMNS = [
    "discovery_id",
    "cnpj_fundo",
    "package_ids",
    "work_tier",
    "batch_id",
    "nome_exibicao",
    "document_id",
    "document_class",
    "category",
    "document_type",
    "species",
    "reference_date",
    "source_filename",
    "download_status",
    "local_path",
    "bytes",
    "sha256",
    "error_message",
    "discovered_at_utc",
]

PACKAGE_DOCUMENT_DISCOVERY_STATUS_COLUMNS = [
    "cnpj_fundo",
    "package_ids",
    "work_tier",
    "batch_id",
    "nome_exibicao",
    "listing_status",
    "documents_listed",
    "documents_relevant",
    "documents_downloaded",
    "documents_reused",
    "document_errors",
    "error_message",
    "attempted_at_utc",
]


def _join_unique(values: pd.Series) -> str:
    seen: list[str] = []
    for value in values.fillna("").astype(str):
        for part in value.split("|"):
            text = part.strip()
            if text and text not in seen:
                seen.append(text)
    return " | ".join(seen)


def select_package_document_targets(
    evidence: pd.DataFrame,
    *,
    existing_status: pd.DataFrame | None = None,
    work_tiers: tuple[str, ...] = ("P0 competência",),
    batch_ids: tuple[str, ...] = (),
    package_ids: tuple[str, ...] = (),
    max_funds: int = 25,
    retry_completed: bool = False,
) -> pd.DataFrame:
    """Select one deterministic FNET target per CNPJ from package evidence."""

    columns = ["cnpj_fundo", "package_ids", "work_tier", "batch_id", "nome_exibicao", "technical_stage"]
    if evidence is None or evidence.empty:
        return pd.DataFrame(columns=columns)
    frame = evidence.copy()
    for col in ["package_id", "cnpj_fundo", "work_tier", "batch_id", "nome_exibicao", "technical_stage", "scope_status"]:
        if col not in frame.columns:
            frame[col] = ""
        frame[col] = frame[col].fillna("").astype(str)
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame = frame[
        frame["cnpj_fundo"].astype(str).str.len().eq(14)
        & frame["technical_stage"].isin({"descoberta", "download"})
        & ~frame["scope_status"].eq("revisar universo")
    ].copy()
    if work_tiers:
        frame = frame[frame["work_tier"].isin(work_tiers)].copy()
    if batch_ids:
        frame = frame[frame["batch_id"].isin(batch_ids)].copy()
    if package_ids:
        frame = frame[frame["package_id"].isin(package_ids)].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)

    tier_order = {"P0 competência": 0, "P1 material 25-26": 1, "P2 cobertura": 2, "P3 backlog": 3}
    frame["_tier_order"] = frame["work_tier"].map(tier_order).fillna(9)
    frame = frame.sort_values(["_tier_order", "batch_id", "package_id"])
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
                "technical_stage": first["technical_stage"],
            }
        )
    targets = pd.DataFrame(records)
    if not retry_completed and existing_status is not None and not existing_status.empty:
        status = existing_status.copy()
        if "cnpj_fundo" not in status.columns:
            status["cnpj_fundo"] = ""
        if "listing_status" not in status.columns:
            status["listing_status"] = ""
        status["cnpj_fundo"] = status["cnpj_fundo"].map(normalize_cnpj)
        completed = set(
            status[
                status["listing_status"].fillna("").astype(str).isin({"ok", "sem_documento_relevante"})
            ]["cnpj_fundo"]
        )
        targets = targets[~targets["cnpj_fundo"].isin(completed)].copy()
    normalized_limit = max(int(max_funds), 0)
    if normalized_limit:
        targets = targets.head(normalized_limit)
    return targets[columns].reset_index(drop=True)


def merge_package_document_discovery(
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


def package_document_discovery_quality_summary(
    documents: pd.DataFrame,
    status: pd.DataFrame,
    *,
    target_funds: int = 0,
) -> dict[str, object]:
    document_frame = pd.DataFrame() if documents is None else documents.copy()
    status_frame = pd.DataFrame() if status is None else status.copy()
    listing = status_frame.get("listing_status", pd.Series("", index=status_frame.index)).fillna("").astype(str)
    download = document_frame.get("download_status", pd.Series("", index=document_frame.index)).fillna("").astype(str)
    return {
        "target_funds": int(target_funds),
        "attempted_funds": int(len(status_frame)),
        "successful_funds": int(listing.isin({"ok", "sem_documento_relevante"}).sum()),
        "no_relevant_document_funds": int(listing.eq("sem_documento_relevante").sum()),
        "listing_error_funds": int(listing.eq("erro_listagem").sum()),
        "document_rows": int(len(document_frame)),
        "relevant_documents": int(pd.to_numeric(status_frame.get("documents_relevant"), errors="coerce").fillna(0).sum()),
        "downloaded_documents": int(download.eq("baixado").sum()),
        "reused_documents": int(download.eq("reutilizado").sum()),
        "listed_only_documents": int(download.eq("listado").sum()),
        "download_error_documents": int(download.eq("erro_download").sum()),
        "listing_status_counts": {str(k): int(v) for k, v in listing.value_counts().to_dict().items()},
        "download_status_counts": {str(k): int(v) for k, v in download.value_counts().to_dict().items()},
    }


def build_package_document_discovery_manifest(
    *,
    industry_dir: Path,
    raw_dir: Path,
    evidence_path: Path,
    documents_path: Path,
    status_path: Path,
    manifest_path: Path,
    documents: pd.DataFrame,
    status: pd.DataFrame,
    target_funds: int,
    download_enabled: bool,
) -> dict[str, object]:
    return {
        "schema_version": "industry-package-document-discovery-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_package_document_discovery",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "download_enabled": bool(download_enabled),
            "notes": [
                "A seleção parte dos estágios descoberta/download da evidência por pacote.",
                "Resultados são cumulativos por CNPJ e documento; tentativas concluídas não são repetidas sem opção explícita.",
            ],
        },
        "inputs": {
            "package_evidence": file_fingerprint(evidence_path),
            "raw_dir": {"path": str(raw_dir), "exists": raw_dir.exists()},
        },
        "outputs": {
            "package_document_discovery": file_fingerprint(documents_path),
            "package_document_discovery_status": file_fingerprint(status_path),
            "manifest": {"path": str(manifest_path)},
        },
        "stages": [
            {
                "id": "select_targets",
                "label": "Selecionar CNPJs prioritários",
                "status": "ok",
                "rows": int(target_funds),
                "rerun": "python scripts/build_fidc_industry_package_documents.py --max-funds 25",
            },
            {
                "id": "discover_fnet",
                "label": "Consultar documentos no FNET",
                "status": "ok" if status is not None and not status.empty else "empty",
                "rows": int(len(status)) if status is not None else 0,
                "rerun": "python scripts/build_fidc_industry_package_documents.py --max-funds 25",
            },
            {
                "id": "persist_discovery",
                "label": "Persistir descoberta e downloads",
                "status": "ok" if documents_path.exists() and status_path.exists() else "empty",
                "rows": int(len(documents)) if documents is not None else 0,
                "rerun": "python scripts/build_fidc_industry_package_documents.py --max-funds 25",
            },
        ],
        "quality": package_document_discovery_quality_summary(
            documents,
            status,
            target_funds=target_funds,
        ),
    }
