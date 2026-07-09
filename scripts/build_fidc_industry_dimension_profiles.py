"""Materializa perfis cruzados por dimensão da aba Industria.

O módulo lê o snapshot unificado e o catálogo de dimensões para gravar uma
matriz agregada dimensão-origem x dimensão-alvo. Deep Dives e heatmaps podem
usar essa camada para explicar qualquer valor selecionado sem recomputar joins
pesados na UI.

Uso:
    python scripts/build_fidc_industry_dimension_profiles.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_dimension_profile_pipeline_manifest,
    build_industry_heatmap_registry,
    build_industry_dimension_profiles,
    industry_dimension_profile_quality_summary,
    load_dataframe,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build cross-dimension profiles for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--snapshot", type=Path, default=None)
    parser.add_argument("--dimension-catalog", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--heatmap-registry-output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot_path = args.snapshot or args.industry_dir / "industry_fund_snapshot.csv.gz"
    catalog_path = args.dimension_catalog or args.industry_dir / "industry_dimension_catalog.csv.gz"
    output_path = args.output or args.industry_dir / "industry_dimension_profiles.csv.gz"
    heatmap_registry_path = args.heatmap_registry_output or args.industry_dir / "industry_heatmap_registry.csv"
    manifest_path = args.manifest or args.industry_dir / "industry_dimension_profile_manifest.json"

    snapshot = load_dataframe(snapshot_path)
    catalog = load_dataframe(catalog_path)
    profiles = build_industry_dimension_profiles(snapshot=snapshot, dimension_catalog=catalog)
    save_dataframe(profiles, output_path)
    heatmap_registry = build_industry_heatmap_registry(dimension_catalog=catalog, profiles=profiles)
    save_dataframe(heatmap_registry, heatmap_registry_path)
    manifest = build_dimension_profile_pipeline_manifest(
        industry_dir=args.industry_dir,
        snapshot_path=snapshot_path,
        dimension_catalog_path=catalog_path,
        output_path=output_path,
        manifest_path=manifest_path,
        heatmap_registry_path=heatmap_registry_path,
        snapshot=snapshot,
        dimension_catalog=catalog,
        profiles=profiles,
        heatmap_registry=heatmap_registry,
    )
    save_pipeline_manifest(manifest, manifest_path)
    quality = industry_dimension_profile_quality_summary(profiles)
    print(
        f"[ok] perfis gravados em {output_path} "
        f"({quality.get('rows', 0):,} linhas; {quality.get('source_dimensions', 0)} dimensões-origem; "
        f"{quality.get('target_dimensions', 0)} dimensões-alvo)"
    )
    print(
        f"[ok] registry de heatmaps gravado em {heatmap_registry_path} "
        f"({int(heatmap_registry.get('profile_available', []).sum()) if not heatmap_registry.empty else 0}/"
        f"{len(heatmap_registry)} com perfil materializado)"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
