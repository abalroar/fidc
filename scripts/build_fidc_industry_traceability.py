"""Materializa matriz de rastreabilidade do catálogo dimensional da Indústria.

A matriz resume, por dimensão e camada de fonte, a cobertura de documento,
página, data, método, score e status de revisão. Ela é leve e pode ser
reexecutada sempre que o catálogo de dimensões ou ações de curadoria mudarem.

Uso:
    python scripts/build_fidc_industry_traceability.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_dimension_traceability_matrix,
    build_dimension_traceability_pipeline_manifest,
    load_dataframe,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build dimension traceability matrix for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--catalog", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog_path = args.catalog or args.industry_dir / "industry_dimension_catalog.csv.gz"
    output_path = args.output or args.industry_dir / "industry_dimension_traceability_matrix.csv"
    manifest_path = args.manifest or args.industry_dir / "industry_dimension_traceability_manifest.json"

    catalog = load_dataframe(catalog_path)
    matrix = build_dimension_traceability_matrix(catalog)
    save_dataframe(matrix, output_path)
    manifest = build_dimension_traceability_pipeline_manifest(
        industry_dir=args.industry_dir,
        catalog_path=catalog_path,
        output_path=output_path,
        manifest_path=manifest_path,
        catalog=catalog,
        matrix=matrix,
    )
    save_pipeline_manifest(manifest, manifest_path)
    quality = manifest.get("quality", {})
    print(
        f"[ok] matriz de rastreabilidade gravada em {output_path} "
        f"({quality.get('rows', 0):,} linhas; {quality.get('dimensions', 0):,} dimensões; "
        f"{quality.get('low_quality_rows', 0):,} baixa qualidade)"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
