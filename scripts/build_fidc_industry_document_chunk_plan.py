"""Materializa o plano operacional dos chunks documentais da aba Industria.

Este script nao reinventa inventario nem chunks. Ele le os artefatos ja
persistidos por `build_fidc_industry_documents.py`, aplica o acompanhamento
manual salvo pela UI e grava um CSV unico para o refresh mensal.

Uso:
    python scripts/build_fidc_industry_document_chunk_plan.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_document_chunk_plan,
    initialize_document_chunk_actions,
    load_dataframe,
    save_dataframe,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the document chunk execution plan for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--inventory", type=Path, default=None)
    parser.add_argument("--chunks", type=Path, default=None)
    parser.add_argument("--actions", type=Path, default=None)
    parser.add_argument("--diagnostics-summary", type=Path, default=None)
    parser.add_argument("--text-summary", type=Path, default=None)
    parser.add_argument("--field-summary", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--no-initialize-actions",
        action="store_true",
        help="Nao criar linhas pendentes para chunks sem acompanhamento persistido.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inventory_path = args.inventory or args.industry_dir / "document_inventory.csv.gz"
    chunks_path = args.chunks or args.industry_dir / "document_processing_chunks.csv"
    actions_path = args.actions or args.industry_dir / "document_chunk_actions.csv"
    diagnostics_summary_path = args.diagnostics_summary or args.industry_dir / "document_chunk_run_summary.csv"
    text_summary_path = args.text_summary or args.industry_dir / "document_text_run_summary.csv"
    field_summary_path = args.field_summary or args.industry_dir / "document_field_run_summary.csv"
    output_path = args.output or args.industry_dir / "document_chunk_plan.csv"

    inventory = load_dataframe(inventory_path)
    chunks = load_dataframe(chunks_path)
    actions = load_dataframe(actions_path)
    diagnostics_summary = load_dataframe(diagnostics_summary_path)
    text_summary = load_dataframe(text_summary_path)
    field_summary = load_dataframe(field_summary_path)
    plan = build_document_chunk_plan(
        chunks,
        inventory,
        actions=actions,
        diagnostics_summary=diagnostics_summary,
        text_summary=text_summary,
        field_summary=field_summary,
    )
    created_actions = 0
    if not args.no_initialize_actions:
        initialized_actions = initialize_document_chunk_actions(plan, actions)
        created_actions = max(len(initialized_actions) - len(actions), 0)
        save_dataframe(initialized_actions, actions_path)
        actions = initialized_actions
        plan = build_document_chunk_plan(
            chunks,
            inventory,
            actions=actions,
            diagnostics_summary=diagnostics_summary,
            text_summary=text_summary,
            field_summary=field_summary,
        )
    save_dataframe(plan, output_path)

    status_counts = plan["chunk_status"].value_counts().to_dict() if "chunk_status" in plan else {}
    action_counts = (
        plan["status_lote"].fillna("").astype(str).replace("", "pendente").value_counts().to_dict()
        if "status_lote" in plan
        else {}
    )
    open_rows = int(plan["chunk_status"].fillna("").astype(str).ne("pronto").sum()) if "chunk_status" in plan else 0
    print(f"[ok] plano de chunks gravado em {output_path} ({len(plan):,} chunks; {open_rows:,} abertos)")
    print(f"[ok] acompanhamento salvo em {actions_path} ({len(actions):,} linhas; {created_actions:,} criadas)")
    print(f"[ok] status operacional: {status_counts}")
    print(f"[ok] acompanhamento: {action_counts}")


if __name__ == "__main__":
    main()
