"""Materializa o inventario documental incremental da aba Industria.

O script nao baixa documentos nem interpreta conteudo. Ele consolida referencias
da aba Estrategia, artefatos de extracao e todos os documentos publicos ja
baixados em data/raw. Os chunks sao append-only: documentos conhecidos preservam
o lote anterior e apenas arquivos novos recebem novos IDs.

Uso:
    python scripts/build_fidc_industry_documents.py
    python scripts/build_fidc_industry_documents.py --chunk-id doc-0001
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    assign_document_chunks,
    build_document_chunk_plan,
    build_document_inventory,
    build_document_pipeline_manifest,
    load_dataframe,
    load_document_source_rows,
    load_fund_universe,
    merge_document_source_rows,
    save_dataframe,
    save_pipeline_manifest,
    scan_raw_document_files,
    scan_regulatory_extraction_files,
)
from services.industry_alternative_documents import alternative_documents_to_inventory_sources  # noqa: E402


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")
DEFAULT_STRATEGY_DB = Path("data/fidc_credit_strategy/fidc_credit_strategy.sqlite")
DEFAULT_EXTRACTIONS_DIR = Path("data/regulatory_extractions")
DEFAULT_RAW_DIR = Path("data/raw")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build document inventory and processing chunks for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--strategy-db", type=Path, default=DEFAULT_STRATEGY_DB)
    parser.add_argument("--extractions-dir", type=Path, default=DEFAULT_EXTRACTIONS_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--inventory-output", type=Path, default=None)
    parser.add_argument("--chunks-output", type=Path, default=None)
    parser.add_argument("--plan-output", type=Path, default=None)
    parser.add_argument("--chunk-actions", type=Path, default=None)
    parser.add_argument("--diagnostics-summary", type=Path, default=None)
    parser.add_argument("--text-summary", type=Path, default=None)
    parser.add_argument("--field-summary", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--chunk-id", type=str, default="")
    parser.add_argument("--max-cnpjs", type=int, default=20)
    parser.add_argument("--max-documents", type=int, default=100)
    parser.add_argument("--max-bytes", type=int, default=128 * 1024 * 1024)
    parser.add_argument("--max-hash-bytes", type=int, default=25 * 1024 * 1024)
    parser.add_argument("--repartition", action="store_true", help="Ignora IDs de chunks existentes e reparte todo o inventário.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    default_inventory_name = "document_inventory.csv.gz" if not args.chunk_id else f"document_inventory_{args.chunk_id}.csv.gz"
    default_manifest_name = "industry_document_manifest.json" if not args.chunk_id else f"industry_document_manifest_{args.chunk_id}.json"
    inventory_path = args.inventory_output or args.industry_dir / default_inventory_name
    chunks_path = args.chunks_output or args.industry_dir / "document_processing_chunks.csv"
    plan_path = args.plan_output or args.industry_dir / "document_chunk_plan.csv"
    actions_path = args.chunk_actions or args.industry_dir / "document_chunk_actions.csv"
    diagnostics_summary_path = args.diagnostics_summary or args.industry_dir / "document_chunk_run_summary.csv"
    text_summary_path = args.text_summary or args.industry_dir / "document_text_run_summary.csv"
    field_summary_path = args.field_summary or args.industry_dir / "document_field_run_summary.csv"
    manifest_path = args.manifest or args.industry_dir / default_manifest_name

    source_rows = load_document_source_rows(args.strategy_db)
    raw_rows = scan_raw_document_files(args.raw_dir)
    alternative_rows = alternative_documents_to_inventory_sources(
        load_dataframe(args.industry_dir / "industry_alternative_documents.csv.gz")
    )
    document_sources = merge_document_source_rows(source_rows, raw_rows, alternative_rows)
    extraction_rows = scan_regulatory_extraction_files(args.extractions_dir)
    fund_universe = load_fund_universe(args.strategy_db)
    inventory = build_document_inventory(
        document_sources,
        fund_universe=fund_universe,
        extraction_rows=extraction_rows,
        root=ROOT,
        max_hash_bytes=args.max_hash_bytes,
    )
    existing_inventory = None if args.repartition else load_dataframe(args.industry_dir / "document_inventory.csv.gz")
    inventory, chunks = assign_document_chunks(
        inventory,
        max_cnpjs=args.max_cnpjs,
        max_documents=args.max_documents,
        max_bytes=args.max_bytes,
        existing_inventory=existing_inventory,
    )
    selected_inventory = inventory
    if args.chunk_id:
        selected_inventory = inventory[inventory["chunk_id"].astype(str).eq(args.chunk_id)].copy()
        if selected_inventory.empty:
            available = ", ".join(chunks["chunk_id"].astype(str).head(8).tolist()) if not chunks.empty else "nenhum"
            raise SystemExit(f"Chunk {args.chunk_id!r} nao encontrado. Exemplos disponiveis: {available}")

    chunk_actions = load_dataframe(actions_path)
    chunk_plan = build_document_chunk_plan(
        chunks,
        inventory,
        actions=chunk_actions,
        diagnostics_summary=load_dataframe(diagnostics_summary_path),
        text_summary=load_dataframe(text_summary_path),
        field_summary=load_dataframe(field_summary_path),
    )
    save_dataframe(selected_inventory, inventory_path)
    save_dataframe(chunks, chunks_path)
    save_dataframe(chunk_plan, plan_path)
    manifest = build_document_pipeline_manifest(
        industry_dir=args.industry_dir,
        strategy_db=args.strategy_db,
        extractions_dir=args.extractions_dir,
        inventory_path=inventory_path,
        chunks_path=chunks_path,
        plan_path=plan_path,
        manifest_path=manifest_path,
        source_rows=source_rows,
        extraction_rows=extraction_rows,
        inventory=selected_inventory,
        chunks=chunks,
        chunk_plan=chunk_plan,
        max_hash_bytes=args.max_hash_bytes,
        raw_dir=args.raw_dir,
        raw_rows=raw_rows,
        alternative_rows=alternative_rows,
    )
    save_pipeline_manifest(manifest, manifest_path)

    print(
        f"[ok] inventario gravado em {inventory_path} "
        f"({len(selected_inventory):,} documentos; {selected_inventory['cnpj_fundo'].nunique() if not selected_inventory.empty else 0:,} FIDCs)"
    )
    print(f"[ok] chunks gravados em {chunks_path} ({len(chunks):,} lotes)")
    print(f"[ok] plano de chunks gravado em {plan_path} ({len(chunk_plan):,} lotes)")
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
