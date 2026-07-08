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
    load_dataframe,
    load_monthly_delta_actions,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build monthly delta queue for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
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
    action_reviews = load_monthly_delta_actions(actions_path)
    if not actions_path.exists():
        save_dataframe(action_reviews, actions_path)
    delta = build_industry_monthly_delta(
        vehicle_monthly=vehicle_monthly,
        snapshot=snapshot,
        metadata=metadata,
        action_reviews=action_reviews,
    )
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
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
