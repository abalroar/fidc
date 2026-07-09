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
    readiness = index.get("readiness_checks", [])
    if isinstance(readiness, list) and readiness:
        status_counts: dict[str, int] = {}
        for row in readiness:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status_prontidao") or "n/d")
            status_counts[status] = status_counts.get(status, 0) + 1
        print(f"[ok] prontidão: {status_counts}")
        for row in readiness:
            if not isinstance(row, dict) or row.get("status_prontidao") == "ok":
                continue
            print(
                "[check] "
                f"{row.get('status_prontidao')}: {row.get('frente')} · "
                f"{row.get('pendencias', 0)} pendência(s) · {row.get('acao_sugerida')}"
            )


if __name__ == "__main__":
    main()
