"""Materializa series mensais por dimensao da aba Industria.

O modulo cruza a base granular mensal com o catalogo de dimensoes e grava uma
serie competencia x dimensao x valor. Isso permite Deep Dives historicos sem
recalcular joins pesados na interface.

Uso:
    python scripts/build_fidc_industry_dimension_monthly.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_dimension_monthly_pipeline_manifest,
    build_industry_dimension_monthly,
    industry_dimension_monthly_quality_summary,
    load_dataframe,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build monthly reusable dimension metrics for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--vehicle-monthly", type=Path, default=None)
    parser.add_argument("--dimension-catalog", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    vehicle_path = args.vehicle_monthly or args.industry_dir / "vehicle_monthly.csv.gz"
    catalog_path = args.dimension_catalog or args.industry_dir / "industry_dimension_catalog.csv.gz"
    output_path = args.output or args.industry_dir / "industry_dimension_monthly.csv.gz"
    manifest_path = args.manifest or args.industry_dir / "industry_dimension_monthly_manifest.json"

    vehicle_monthly = load_dataframe(vehicle_path)
    dimension_catalog = load_dataframe(catalog_path)
    monthly = build_industry_dimension_monthly(
        vehicle_monthly=vehicle_monthly,
        dimension_catalog=dimension_catalog,
    )
    save_dataframe(monthly, output_path)
    manifest = build_dimension_monthly_pipeline_manifest(
        industry_dir=args.industry_dir,
        vehicle_monthly_path=vehicle_path,
        dimension_catalog_path=catalog_path,
        output_path=output_path,
        manifest_path=manifest_path,
        vehicle_monthly=vehicle_monthly,
        dimension_catalog=dimension_catalog,
        monthly=monthly,
    )
    save_pipeline_manifest(manifest, manifest_path)
    quality = industry_dimension_monthly_quality_summary(monthly)
    print(
        f"[ok] series mensais gravadas em {output_path} "
        f"({quality.get('rows', 0):,} linhas; {quality.get('months', 0)} meses; "
        f"{quality.get('dimensions', 0)} dimensoes)"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
