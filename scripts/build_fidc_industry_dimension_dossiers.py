"""Materializa dossies por dimensao da aba Industria.

O modulo resume atlas, perfis cruzados e registry de heatmaps em uma linha por
dimensao estruturada. A UI usa esse artefato para Deep Dives e auditoria sem
recalcular joins pesados.

Uso:
    python scripts/build_fidc_industry_dimension_dossiers.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_dimension_dossier_pipeline_manifest,
    build_industry_dimension_dossiers,
    industry_dimension_dossier_quality_summary,
    load_dataframe,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build reusable dimension dossiers for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--atlas", type=Path, default=None)
    parser.add_argument("--profiles", type=Path, default=None)
    parser.add_argument("--heatmap-registry", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    atlas_path = args.atlas or args.industry_dir / "industry_dimension_value_atlas.csv.gz"
    profiles_path = args.profiles or args.industry_dir / "industry_dimension_profiles.csv.gz"
    heatmap_registry_path = args.heatmap_registry or args.industry_dir / "industry_heatmap_registry.csv"
    output_path = args.output or args.industry_dir / "industry_dimension_dossiers.csv"
    manifest_path = args.manifest or args.industry_dir / "industry_dimension_dossier_manifest.json"

    atlas = load_dataframe(atlas_path)
    profiles = load_dataframe(profiles_path)
    heatmap_registry = load_dataframe(heatmap_registry_path)
    dossiers = build_industry_dimension_dossiers(
        atlas=atlas,
        profiles=profiles,
        heatmap_registry=heatmap_registry,
    )
    save_dataframe(dossiers, output_path)
    manifest = build_dimension_dossier_pipeline_manifest(
        industry_dir=args.industry_dir,
        atlas_path=atlas_path,
        profiles_path=profiles_path,
        heatmap_registry_path=heatmap_registry_path,
        output_path=output_path,
        manifest_path=manifest_path,
        atlas=atlas,
        profiles=profiles,
        heatmap_registry=heatmap_registry,
        dossiers=dossiers,
    )
    save_pipeline_manifest(manifest, manifest_path)
    quality = industry_dimension_dossier_quality_summary(dossiers)
    print(
        f"[ok] dossies dimensionais gravados em {output_path} "
        f"({quality.get('rows', 0):,} dimensoes; {quality.get('ok_rows', 0)} ok; "
        f"{quality.get('attention_rows', 0)} atencao)"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
