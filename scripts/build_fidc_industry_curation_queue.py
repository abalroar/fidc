"""Materializa a fila única de curadoria mensal da aba Industria.

A fila consolida, em um CSV operacional, as pendencias que hoje vivem em
frentes separadas: delta mensal, lacunas all-FIDCs do snapshot, chunks
documentais e rastreabilidade do catálogo de dimensões.

Uso:
    python scripts/build_fidc_industry_curation_queue.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    apply_monthly_delta_actions,
    build_curation_queue_pipeline_manifest,
    build_document_chunk_plan,
    build_industry_curation_queue,
    load_dataframe,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the unified monthly curation queue for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = args.output or args.industry_dir / "industry_curation_queue.csv.gz"
    manifest_path = args.manifest or args.industry_dir / "industry_curation_queue_manifest.json"

    snapshot = load_dataframe(args.industry_dir / "industry_fund_snapshot.csv.gz")
    monthly_delta = load_dataframe(args.industry_dir / "industry_monthly_delta.csv.gz")
    monthly_delta_actions = load_dataframe(args.industry_dir / "monthly_delta_actions.csv")
    if not monthly_delta.empty:
        monthly_delta = apply_monthly_delta_actions(monthly_delta, monthly_delta_actions)

    inventory = load_dataframe(args.industry_dir / "document_inventory.csv.gz")
    chunks = load_dataframe(args.industry_dir / "document_processing_chunks.csv")
    document_chunk_actions = load_dataframe(args.industry_dir / "document_chunk_actions.csv")
    document_chunk_plan = build_document_chunk_plan(chunks, inventory, actions=document_chunk_actions)
    if document_chunk_plan.empty:
        document_chunk_plan = load_dataframe(args.industry_dir / "document_chunk_plan.csv")

    dimension_catalog = load_dataframe(args.industry_dir / "industry_dimension_catalog.csv.gz")
    snapshot_gap_actions = load_dataframe(args.industry_dir / "snapshot_gap_actions.csv")
    catalog_gap_actions = load_dataframe(args.industry_dir / "dimension_catalog_gap_actions.csv")

    queue = build_industry_curation_queue(
        snapshot=snapshot,
        monthly_delta=monthly_delta,
        document_chunk_plan=document_chunk_plan,
        dimension_catalog=dimension_catalog,
        snapshot_gap_actions=snapshot_gap_actions,
        catalog_gap_actions=catalog_gap_actions,
    )
    save_dataframe(queue, output_path)
    manifest = build_curation_queue_pipeline_manifest(
        industry_dir=args.industry_dir,
        output_path=output_path,
        manifest_path=manifest_path,
        snapshot=snapshot,
        monthly_delta=monthly_delta,
        document_chunk_plan=document_chunk_plan,
        dimension_catalog=dimension_catalog,
        queue=queue,
    )
    save_pipeline_manifest(manifest, manifest_path)

    quality = manifest.get("quality", {})
    print(
        f"[ok] fila de curadoria gravada em {output_path} "
        f"({quality.get('rows', 0):,} linhas; {quality.get('open_rows', 0):,} abertas)"
    )
    print(f"[ok] dominios: {quality.get('domain_counts', {})}")
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
