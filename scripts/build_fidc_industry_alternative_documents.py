"""Descobre documentos oficiais CVM para pacotes sem material relevante no FNET."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_alternative_documents import (  # noqa: E402
    ALTERNATIVE_DOCUMENT_COLUMNS,
    ALTERNATIVE_DOCUMENT_STATUS_COLUMNS,
    build_alternative_document_manifest,
    build_alternative_document_status,
    build_cvm_eventual_candidates,
    merge_alternative_documents,
    select_alternative_document_targets,
)
from services.industry_study import load_dataframe, save_dataframe, save_pipeline_manifest  # noqa: E402


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")
DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_CACHE_DIR = Path(".cache/cvm-industry-alternative")
DATASET_URL = "https://dados.cvm.gov.br/dados/FI/DOC/EVENTUAL/DADOS/eventual_fi_{year}.csv"
USER_AGENT = "fidc-industry-alternative-documents/1.0 (dados.cvm.gov.br)"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover official CVM documents for no-FNET Industry packages.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--tier", action="append", default=None)
    parser.add_argument("--technical-stage", action="append", default=None)
    parser.add_argument("--year", action="append", type=int, default=None)
    parser.add_argument("--max-funds", type=int, default=25)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--documents-output", type=Path, default=None)
    parser.add_argument("--status-output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def _download(url: str, destination: Path, *, timeout_seconds: int) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            temporary.write_bytes(response.read())
        if destination.suffix.lower() == ".pdf" and not temporary.read_bytes()[:5].startswith(b"%PDF-"):
            raise ValueError("resposta não contém PDF válido")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_document_path(raw_dir: Path, row: pd.Series) -> Path:
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", str(row.get("source_filename", ""))).strip("._")
    filename = filename or f"documento_{row.get('document_id', '')}.pdf"
    if not Path(filename).suffix:
        filename = f"{filename}.pdf"
    prefix = f"cvm_eventual_{row.get('document_id', '')}_{row.get('document_class', 'outro')}"
    return raw_dir / str(row["cnpj_fundo"]) / f"{prefix}_{filename}"


def main() -> None:
    args = parse_args()
    evidence_path = args.industry_dir / "industry_curation_package_evidence.csv.gz"
    documents_path = args.documents_output or args.industry_dir / "industry_alternative_documents.csv.gz"
    status_path = args.status_output or args.industry_dir / "industry_alternative_document_status.csv.gz"
    manifest_path = args.manifest or args.industry_dir / "industry_alternative_document_manifest.json"
    evidence = load_dataframe(evidence_path)
    targets = select_alternative_document_targets(
        evidence,
        work_tiers=tuple(args.tier or ["P0 competência"]),
        technical_stages=tuple(args.technical_stage or ["fontes alternativas"]),
        max_funds=args.max_funds,
    )
    explicit_years = sorted(set(args.year or []))
    target_years = sorted(
        {
            int(value)
            for values in targets.get("source_years", pd.Series(dtype=str)).fillna("").astype(str)
            for value in values.split(",")
            if value.strip().isdigit()
        }
    )
    years = explicit_years or target_years
    attempted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cache_paths: dict[int, Path] = {}
    candidate_frames: list[pd.DataFrame] = []
    for year in years:
        dataset_url = DATASET_URL.format(year=year)
        cache_path = args.cache_dir / f"eventual_fi_{year}.csv"
        if args.refresh_cache or not cache_path.exists() or cache_path.stat().st_size == 0:
            print(f"[info] baixando metadados CVM Eventuais {year}", flush=True)
            _download(dataset_url, cache_path, timeout_seconds=max(args.timeout_seconds, 10))
        cache_paths[year] = cache_path
        eventual = pd.read_csv(cache_path, sep=";", encoding="latin-1", dtype=str, keep_default_na=False)
        candidate_frames.append(
            build_cvm_eventual_candidates(
                eventual,
                targets,
                source_year=year,
                dataset_url=dataset_url,
                discovered_at_utc=attempted_at,
            )
        )
    candidates = (
        pd.concat(candidate_frames, ignore_index=True, sort=False)
        if candidate_frames
        else pd.DataFrame(columns=ALTERNATIVE_DOCUMENT_COLUMNS)
    )
    download_enabled = not args.no_download
    processed_rows: list[dict[str, object]] = []
    for _, row in candidates.iterrows():
        record = row.to_dict()
        local_path = _safe_document_path(args.raw_dir, row)
        try:
            if local_path.exists() and local_path.stat().st_size > 0:
                record["download_status"] = "reutilizado"
            elif download_enabled:
                _download(str(row["source_url"]), local_path, timeout_seconds=max(args.timeout_seconds, 10))
                record["download_status"] = "baixado"
            else:
                record["download_status"] = "listado"
            if local_path.exists() and local_path.stat().st_size > 0:
                record["local_path"] = str(local_path)
                record["bytes"] = int(local_path.stat().st_size)
                record["sha256"] = _sha256(local_path)
        except Exception as exc:  # noqa: BLE001
            record["download_status"] = "erro_download"
            record["error_message"] = f"{type(exc).__name__}: {exc}"
        processed_rows.append(record)
        print(
            f"[{row['cnpj_fundo']}] {row['document_type']} {record['download_status']} "
            f"{row['source_filename']}",
            flush=True,
        )
    existing_documents = load_dataframe(documents_path)
    documents = merge_alternative_documents(
        existing_documents,
        pd.DataFrame(processed_rows),
        key_column="discovery_id",
        columns=ALTERNATIVE_DOCUMENT_COLUMNS,
    )
    current_status = build_alternative_document_status(targets, documents, attempted_at_utc=attempted_at)
    status = merge_alternative_documents(
        load_dataframe(status_path),
        current_status,
        key_column="cnpj_fundo",
        columns=ALTERNATIVE_DOCUMENT_STATUS_COLUMNS,
    )
    save_dataframe(documents, documents_path)
    save_dataframe(status, status_path)
    manifest = build_alternative_document_manifest(
        industry_dir=args.industry_dir,
        raw_dir=args.raw_dir,
        cache_paths=cache_paths,
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
        f"[ok] fontes alternativas CVM: {quality.get('covered_funds', 0)}/{quality.get('attempted_funds', 0)} CNPJs; "
        f"{quality.get('relevant_documents', 0)} documentos; "
        f"{quality.get('downloaded_documents', 0)} baixados; {quality.get('download_error_documents', 0)} erros"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
