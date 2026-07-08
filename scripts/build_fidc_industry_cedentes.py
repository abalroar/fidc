"""Materializa a base estruturada de cedentes/sacados da aba Industria.

Este modulo e incremental: ele nao reprocessa documentos. Ele consolida os
candidatos ja extraidos no SQLite regulatorio, aplica as revisoes manuais feitas
pela UI e grava uma tabela versionavel para heatmaps, deep dives e QA mensal.

Uso:
    python scripts/build_fidc_industry_cedentes.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_cedente_pipeline_manifest,
    build_cedente_structured,
    load_cedente_candidates,
    load_cedente_reviews,
    load_fund_universe,
    load_vehicle_latest,
    save_pipeline_manifest,
    save_cedente_structured,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")
DEFAULT_STRATEGY_DB = Path("data/fidc_credit_strategy/fidc_credit_strategy.sqlite")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build structured cedente/sacado base for the FIDC industry study.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--strategy-db", type=Path, default=DEFAULT_STRATEGY_DB)
    parser.add_argument("--reviews", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reviews_path = args.reviews or args.industry_dir / "cedente_reviews.csv"
    output_path = args.output or args.industry_dir / "cedentes_structured.csv.gz"
    manifest_path = args.manifest or args.industry_dir / "industry_pipeline_manifest.json"

    candidates = load_cedente_candidates(args.strategy_db)
    reviews = load_cedente_reviews(reviews_path)
    fund_universe = load_fund_universe(args.strategy_db)
    vehicle_latest = load_vehicle_latest(args.industry_dir)
    structured = build_cedente_structured(
        candidates,
        reviews,
        fund_universe=fund_universe,
        vehicle_latest=vehicle_latest,
    )
    save_cedente_structured(structured, output_path)
    manifest = build_cedente_pipeline_manifest(
        industry_dir=args.industry_dir,
        strategy_db=args.strategy_db,
        reviews_path=reviews_path,
        output_path=output_path,
        candidates=candidates,
        reviews=reviews,
        fund_universe=fund_universe,
        vehicle_latest=vehicle_latest,
        structured=structured,
    )
    save_pipeline_manifest(manifest, manifest_path)
    print(
        f"[ok] {len(structured):,} linhas estruturadas gravadas em {output_path} "
        f"({structured['cnpj_fundo'].nunique() if 'cnpj_fundo' in structured else 0:,} FIDCs)"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
