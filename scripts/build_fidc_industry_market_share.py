"""Materializa market share e concentracao da aba Industria.

O modulo le o snapshot unificado por FIDC e grava rankings reutilizaveis por
dimensao e metrica. Ele nao reprocessa documentos, informes ou curadoria; serve
como camada analitica incremental para a UI, heatmaps e deep dives.

Uso:
    python scripts/build_fidc_industry_market_share.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_industry_market_share,
    build_market_share_pipeline_manifest,
    industry_market_share_quality_summary,
    load_dataframe,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build reusable market-share tables for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--snapshot", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot_path = args.snapshot or args.industry_dir / "industry_fund_snapshot.csv.gz"
    output_path = args.output or args.industry_dir / "industry_market_share.csv.gz"
    manifest_path = args.manifest or args.industry_dir / "industry_market_share_manifest.json"

    snapshot = load_dataframe(snapshot_path)
    market_share = build_industry_market_share(snapshot)
    save_dataframe(market_share, output_path)
    manifest = build_market_share_pipeline_manifest(
        industry_dir=args.industry_dir,
        snapshot_path=snapshot_path,
        output_path=output_path,
        manifest_path=manifest_path,
        snapshot=snapshot,
        market_share=market_share,
    )
    save_pipeline_manifest(manifest, manifest_path)
    quality = industry_market_share_quality_summary(market_share)
    print(
        f"[ok] market share gravado em {output_path} "
        f"({quality.get('rows', 0):,} linhas; {quality.get('dimensions', 0)} dimensoes; "
        f"{quality.get('metrics', 0)} metricas)"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
