"""Materializa o inventario documental incremental da aba Industria.

O script nao baixa documentos nem interpreta conteudo. Ele consolida referencias
ja descobertas pela aba Estrategia, cruza com artefatos locais, calcula status de
arquivo/fingerprint leve e divide o trabalho em chunks pequenos para OCR,
parsing e extracao em etapas futuras.

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
    save_dataframe,
    save_pipeline_manifest,
    scan_regulatory_extraction_files,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")
DEFAULT_STRATEGY_DB = Path("data/fidc_credit_strategy/fidc_credit_strategy.sqlite")
DEFAULT_EXTRACTIONS_DIR = Path("data/regulatory_extractions")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build document inventory and processing chunks for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--strategy-db", type=Path, default=DEFAULT_STRATEGY_DB)
    parser.add_argument("--extractions-dir", type=Path, default=DEFAULT_EXTRACTIONS_DIR)
    parser.add_argument("--inventory-output", type=Path, default=None)
    parser.add_argument("--chunks-output", type=Path, default=None)
    parser.add_argument("--plan-output", type=Path, default=None)
    parser.add_argument("--chunk-actions", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--chunk-id", type=str, default="")
    parser.add_argument("--max-cnpjs", type=int, default=40)
    parser.add_argument("--max-documents", type=int, default=250)
    parser.add_argument("--max-bytes", type=int, default=256 * 1024 * 1024)
    parser.add_argument("--max-hash-bytes", type=int, default=25 * 1024 * 1024)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    default_inventory_name = "document_inventory.csv.gz" if not args.chunk_id else f"document_inventory_{args.chunk_id}.csv.gz"
    default_manifest_name = "industry_document_manifest.json" if not args.chunk_id else f"industry_document_manifest_{args.chunk_id}.json"
    inventory_path = args.inventory_output or args.industry_dir / default_inventory_name
    chunks_path = args.chunks_output or args.industry_dir / "document_processing_chunks.csv"
    plan_path = args.plan_output or args.industry_dir / "document_chunk_plan.csv"
    actions_path = args.chunk_actions or args.industry_dir / "document_chunk_actions.csv"
    manifest_path = args.manifest or args.industry_dir / default_manifest_name

    source_rows = load_document_source_rows(args.strategy_db)
    extraction_rows = scan_regulatory_extraction_files(args.extractions_dir)
    fund_universe = load_fund_universe(args.strategy_db)
    inventory = build_document_inventory(
        source_rows,
        fund_universe=fund_universe,
        extraction_rows=extraction_rows,
        root=ROOT,
        max_hash_bytes=args.max_hash_bytes,
    )
    inventory, chunks = assign_document_chunks(
        inventory,
        max_cnpjs=args.max_cnpjs,
        max_documents=args.max_documents,
        max_bytes=args.max_bytes,
    )
    selected_inventory = inventory
    if args.chunk_id:
        selected_inventory = inventory[inventory["chunk_id"].astype(str).eq(args.chunk_id)].copy()
        if selected_inventory.empty:
            available = ", ".join(chunks["chunk_id"].astype(str).head(8).tolist()) if not chunks.empty else "nenhum"
            raise SystemExit(f"Chunk {args.chunk_id!r} nao encontrado. Exemplos disponiveis: {available}")

    chunk_actions = load_dataframe(actions_path)
    chunk_plan = build_document_chunk_plan(chunks, inventory, actions=chunk_actions)
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
