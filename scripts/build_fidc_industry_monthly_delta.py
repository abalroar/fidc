"""Materializa a fila incremental mensal da aba Industria.

Compara a competência snapshot com a anterior, identifica FIDCs novos,
reativados, recorrentes ou ausentes e prioriza ações de descoberta documental
e curadoria sem reprocessar a indústria inteira.

Uso:
    python scripts/build_fidc_industry_monthly_delta.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_industry_monthly_delta,
    build_monthly_delta_pipeline_manifest,
    apply_industry_universe_reviews,
    initialize_monthly_delta_actions,
    load_dataframe,
    load_monthly_delta_actions,
    load_industry_universe_reviews,
    save_dataframe,
    save_monthly_delta_actions,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build monthly delta queue for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument(
        "--no-initialize-actions",
        action="store_true",
        help="Nao criar linhas pendentes para deltas de alta prioridade sem acompanhamento.",
    )
    parser.add_argument(
        "--initialize-all-actions",
        action="store_true",
        help="Criar linhas pendentes para todos os deltas sem acompanhamento, nao apenas alta prioridade.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = args.output or args.industry_dir / "industry_monthly_delta.csv.gz"
    manifest_path = args.manifest or args.industry_dir / "industry_monthly_delta_manifest.json"
    actions_path = args.industry_dir / "monthly_delta_actions.csv"
    metadata_path = args.industry_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}

    vehicle_monthly = load_dataframe(args.industry_dir / "vehicle_monthly.csv.gz")
    snapshot = load_dataframe(args.industry_dir / "industry_fund_snapshot.csv.gz")
    universe_reviews = load_industry_universe_reviews(args.industry_dir / "universe_scope_reviews.csv")
    vehicle_monthly = apply_industry_universe_reviews(
        vehicle_monthly,
        universe_reviews,
        cnpj_column="cnpj" if "cnpj" in vehicle_monthly.columns else "cnpj_fundo",
    )
    snapshot = apply_industry_universe_reviews(snapshot, universe_reviews)
    action_reviews = load_monthly_delta_actions(actions_path)
    delta = build_industry_monthly_delta(
        vehicle_monthly=vehicle_monthly,
        snapshot=snapshot,
        metadata=metadata,
        action_reviews=action_reviews,
    )
    created_actions = 0
    if not args.no_initialize_actions:
        priority_bands = tuple() if args.initialize_all_actions else ("alta",)
        initialized_actions = initialize_monthly_delta_actions(
            delta,
            action_reviews,
            priority_bands=priority_bands,
        )
        created_actions = max(len(initialized_actions) - len(action_reviews), 0)
        action_reviews = save_monthly_delta_actions(initialized_actions, actions_path)
        delta = build_industry_monthly_delta(
            vehicle_monthly=vehicle_monthly,
            snapshot=snapshot,
            metadata=metadata,
            action_reviews=action_reviews,
        )
    elif not actions_path.exists():
        save_monthly_delta_actions(action_reviews, actions_path)
    save_dataframe(delta, output_path)
    manifest = build_monthly_delta_pipeline_manifest(
        industry_dir=args.industry_dir,
        output_path=output_path,
        manifest_path=manifest_path,
        vehicle_monthly=vehicle_monthly,
        snapshot=snapshot,
        delta=delta,
    )
    save_pipeline_manifest(manifest, manifest_path)

    quality = manifest.get("quality", {})
    print(
        f"[ok] delta mensal gravado em {output_path} "
        f"({quality.get('rows', 0):,} linhas; {quality.get('new_funds', 0):,} novos; "
        f"{quality.get('reactivated_funds', 0):,} reativados)"
    )
    print(f"[ok] acompanhamento salvo em {actions_path} ({len(action_reviews):,} linhas; {created_actions:,} criadas)")
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
