"""Materializa o catalogo de dimensoes da aba Industria.

O catalogo grava uma linha por CNPJ x dimensao x valor, com pesos e metadados
de fonte. Heatmaps e Deep Dives passam a reutilizar esta camada em vez de
codificar regras especificas para cada combinacao.

Uso:
    python scripts/build_fidc_industry_dimensions.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_dimension_catalog_pipeline_manifest,
    build_industry_dimension_catalog,
    industry_dimension_catalog_quality_summary,
    load_dataframe,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build reusable dimension catalog for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--snapshot", type=Path, default=None)
    parser.add_argument("--cedentes", type=Path, default=None)
    parser.add_argument("--criteria", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot_path = args.snapshot or args.industry_dir / "industry_fund_snapshot.csv.gz"
    cedentes_path = args.cedentes or args.industry_dir / "cedentes_structured.csv.gz"
    criteria_path = args.criteria or args.industry_dir / "criteria_structured.csv.gz"
    output_path = args.output or args.industry_dir / "industry_dimension_catalog.csv.gz"
    manifest_path = args.manifest or args.industry_dir / "industry_dimension_catalog_manifest.json"

    snapshot = load_dataframe(snapshot_path)
    cedentes = load_dataframe(cedentes_path)
    criteria = load_dataframe(criteria_path)
    catalog = build_industry_dimension_catalog(snapshot=snapshot, cedentes=cedentes, criteria=criteria)
    save_dataframe(catalog, output_path)
    manifest = build_dimension_catalog_pipeline_manifest(
        industry_dir=args.industry_dir,
        snapshot_path=snapshot_path,
        cedentes_path=cedentes_path,
        criteria_path=criteria_path,
        output_path=output_path,
        manifest_path=manifest_path,
        snapshot=snapshot,
        cedentes=cedentes,
        criteria=criteria,
        catalog=catalog,
    )
    save_pipeline_manifest(manifest, manifest_path)
    quality = industry_dimension_catalog_quality_summary(catalog)
    print(
        f"[ok] catalogo gravado em {output_path} "
        f"({quality.get('rows', 0):,} linhas; {quality.get('funds', 0):,} FIDCs; "
        f"{quality.get('dimensions', 0)} dimensoes)"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
