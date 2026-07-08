"""Materializa o cockpit mensal da aba Industria.

O script nao reprocessa informes, documentos ou curadoria. Ele agrega manifests,
fingerprints e comandos de reexecucao dos modulos ja materializados para que a
aba Pipeline mostre um checklist mensal unico e auditavel.

Uso:
    python scripts/build_fidc_industry_pipeline_index.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import build_industry_pipeline_index, save_pipeline_manifest


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the monthly refresh cockpit for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = args.output or args.industry_dir / "industry_pipeline_index.json"
    index = build_industry_pipeline_index(industry_dir=args.industry_dir, output_path=output_path)
    save_pipeline_manifest(index, output_path)
    rollup = index.get("quality_rollup", {})
    status_counts = rollup.get("module_status_counts", {}) if isinstance(rollup, dict) else {}
    print(
        f"[ok] cockpit gravado em {output_path} "
        f"({rollup.get('modules_total', 0)} módulos; status {status_counts})"
    )
    print(
        f"[ok] artefatos: {rollup.get('artifacts_present', 0)}/"
        f"{rollup.get('artifacts_total', 0)} presentes"
    )


if __name__ == "__main__":
    main()
