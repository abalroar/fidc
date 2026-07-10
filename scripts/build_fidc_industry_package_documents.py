"""Descobre e baixa documentos FNET para pacotes prioritários da aba Indústria."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.fundonet_client import FundosNetClient  # noqa: E402
from services.fundonet_documents import build_document_filename  # noqa: E402
from services.industry_package_documents import (  # noqa: E402
    PACKAGE_DOCUMENT_DISCOVERY_COLUMNS,
    PACKAGE_DOCUMENT_DISCOVERY_STATUS_COLUMNS,
    build_package_document_discovery_manifest,
    merge_package_document_discovery,
    select_package_document_targets,
)
from services.industry_study import load_dataframe, save_dataframe, save_pipeline_manifest  # noqa: E402
from services.regulatory_knowledge import classify_document  # noqa: E402


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")
DEFAULT_RAW_DIR = Path("data/raw")
DOCUMENT_PRIORITY = {"regulamento": 4, "emissao": 3, "assembleia": 2, "evento": 1}
RECENT_DOCUMENT_START = pd.Timestamp("2024-01-01")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover FNET documents for prioritized Industry packages.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--tier", action="append", default=None)
    parser.add_argument("--batch-id", action="append", default=None)
    parser.add_argument("--package-id", action="append", default=None)
    parser.add_argument("--max-funds", type=int, default=25)
    parser.add_argument("--max-docs-per-fund", type=int, default=12)
    parser.add_argument("--timeout-seconds", type=int, default=25)
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--retry-completed", action="store_true")
    parser.add_argument("--documents-output", type=Path, default=None)
    parser.add_argument("--status-output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def _safe_storage_name(document: object, classification: str) -> str:
    name = build_document_filename(document, default_stem=f"{classification}_{document.id}")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem).strip("._") or f"{classification}_{document.id}"
    suffix = Path(name).suffix.lower() or ".pdf"
    return f"{document.id}_{classification}_{stem}{suffix}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    evidence_path = args.industry_dir / "industry_curation_package_evidence.csv.gz"
    documents_path = args.documents_output or args.industry_dir / "industry_package_document_discovery.csv.gz"
    status_path = args.status_output or args.industry_dir / "industry_package_document_discovery_status.csv.gz"
    manifest_path = args.manifest or args.industry_dir / "industry_package_document_discovery_manifest.json"
    evidence = load_dataframe(evidence_path)
    existing_documents = load_dataframe(documents_path)
    existing_status = load_dataframe(status_path)
    targets = select_package_document_targets(
        evidence,
        existing_status=existing_status,
        work_tiers=tuple(args.tier or ["P0 competência"]),
        batch_ids=tuple(args.batch_id or []),
        package_ids=tuple(args.package_id or []),
        max_funds=args.max_funds,
        retry_completed=args.retry_completed,
    )
    client = FundosNetClient(timeout_seconds=max(args.timeout_seconds, 5), max_retries=1)
    document_rows: list[dict[str, object]] = []
    status_rows: list[dict[str, object]] = []
    download_enabled = not args.no_download

    for index, target in targets.iterrows():
        cnpj = str(target["cnpj_fundo"])
        attempted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        print(f"[{index + 1}/{len(targets)}] {cnpj} {target['nome_exibicao']}", flush=True)
        try:
            listed = client.listar_documentos(cnpj, error_stage="industry_package_discovery")
        except Exception as exc:  # noqa: BLE001
            status_rows.append(
                {
                    **target.to_dict(),
                    "listing_status": "erro_listagem",
                    "documents_listed": 0,
                    "documents_relevant": 0,
                    "documents_downloaded": 0,
                    "documents_reused": 0,
                    "document_errors": 1,
                    "error_message": f"{type(exc).__name__}: {exc}",
                    "attempted_at_utc": attempted_at,
                }
            )
            print(f"  erro de listagem: {type(exc).__name__}: {exc}", flush=True)
            continue

        relevant: list[tuple[object, str, pd.Timestamp | pd.NaT]] = []
        for document in listed:
            classification = classify_document(
                categoria=document.categoria,
                tipo=document.tipo,
                especie=document.especie,
                nome_arquivo=document.nome_arquivo or "",
            )
            if classification not in DOCUMENT_PRIORITY:
                continue
            reference_date = pd.Timestamp(document.data_referencia_dt) if document.data_referencia_dt else pd.NaT
            if classification == "regulamento" or pd.isna(reference_date) or reference_date >= RECENT_DOCUMENT_START:
                relevant.append((document, classification, reference_date))
        relevant = sorted(
            relevant,
            key=lambda item: (
                DOCUMENT_PRIORITY.get(item[1], 0),
                item[2] if not pd.isna(item[2]) else pd.Timestamp.min,
                str(item[0].id),
            ),
            reverse=True,
        )
        if args.max_docs_per_fund > 0:
            relevant = relevant[: args.max_docs_per_fund]

        downloaded = 0
        reused = 0
        errors = 0
        error_messages: list[str] = []
        fund_dir = args.raw_dir / cnpj
        for document, classification, reference_date in relevant:
            local_path = fund_dir / _safe_storage_name(document, classification)
            download_status = "listado"
            error_message = ""
            if download_enabled:
                fund_dir.mkdir(parents=True, exist_ok=True)
                if local_path.exists() and local_path.stat().st_size > 0:
                    download_status = "reutilizado"
                    reused += 1
                else:
                    try:
                        local_path.write_bytes(client.download_documento(document.id))
                        download_status = "baixado"
                        downloaded += 1
                    except Exception as exc:  # noqa: BLE001
                        download_status = "erro_download"
                        error_message = f"{type(exc).__name__}: {exc}"
                        errors += 1
                        error_messages.append(f"{document.id}:{type(exc).__name__}")
            local_exists = local_path.exists() and local_path.stat().st_size > 0
            document_rows.append(
                {
                    "discovery_id": f"fnet:{cnpj}:{document.id}",
                    "cnpj_fundo": cnpj,
                    "package_ids": target["package_ids"],
                    "work_tier": target["work_tier"],
                    "batch_id": target["batch_id"],
                    "nome_exibicao": target["nome_exibicao"],
                    "document_id": str(document.id),
                    "document_class": classification,
                    "category": document.categoria or "",
                    "document_type": document.tipo or "",
                    "species": document.especie or "",
                    "reference_date": "" if pd.isna(reference_date) else reference_date.date().isoformat(),
                    "source_filename": document.nome_arquivo or "",
                    "download_status": download_status,
                    "local_path": str(local_path) if local_exists else "",
                    "bytes": int(local_path.stat().st_size) if local_exists else 0,
                    "sha256": _sha256(local_path) if local_exists else "",
                    "error_message": error_message,
                    "discovered_at_utc": attempted_at,
                }
            )
            print(f"  {classification}: {download_status} {document.id}", flush=True)

        listing_status = "sem_documento_relevante" if not relevant else ("parcial" if errors else "ok")
        status_rows.append(
            {
                **target.to_dict(),
                "listing_status": listing_status,
                "documents_listed": len(listed),
                "documents_relevant": len(relevant),
                "documents_downloaded": downloaded,
                "documents_reused": reused,
                "document_errors": errors,
                "error_message": " | ".join(error_messages),
                "attempted_at_utc": attempted_at,
            }
        )
        print(f"  status: {listing_status}; listados {len(listed)}; relevantes {len(relevant)}", flush=True)

    documents = merge_package_document_discovery(
        existing_documents,
        pd.DataFrame(document_rows),
        key_column="discovery_id",
        columns=PACKAGE_DOCUMENT_DISCOVERY_COLUMNS,
    )
    status = merge_package_document_discovery(
        existing_status,
        pd.DataFrame(status_rows),
        key_column="cnpj_fundo",
        columns=PACKAGE_DOCUMENT_DISCOVERY_STATUS_COLUMNS,
    )
    save_dataframe(documents, documents_path)
    save_dataframe(status, status_path)
    manifest = build_package_document_discovery_manifest(
        industry_dir=args.industry_dir,
        raw_dir=args.raw_dir,
        evidence_path=evidence_path,
        documents_path=documents_path,
        status_path=status_path,
        manifest_path=manifest_path,
        documents=documents,
        status=status,
        target_funds=len(targets),
        download_enabled=download_enabled,
    )
    save_pipeline_manifest(manifest, manifest_path)
    quality = manifest.get("quality", {})
    print(
        f"[ok] descoberta FNET: {quality.get('attempted_funds', 0)} CNPJs acumulados; "
        f"{quality.get('relevant_documents', 0)} documentos relevantes; "
        f"{quality.get('downloaded_documents', 0)} baixados; "
        f"{quality.get('no_relevant_document_funds', 0)} sem documento relevante"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
