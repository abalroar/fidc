"""Materializa o onboarding incremental de FIDCs novos/reativados.

Este modulo consolida, por CNPJ, as tres etapas do PRD para novos fundos:
descoberta, processamento e incorporacao. Ele nao reprocessa documentos nem
cria decisoes de curadoria; apenas cruza delta mensal, fila unica e plano de
chunks ja materializados.

Uso:
    python scripts/build_fidc_industry_incremental_onboarding.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_incremental_onboarding_pipeline_manifest,
    build_incremental_onboarding_plan,
    load_dataframe,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build incremental onboarding checklist for new/reactivated FIDCs.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = args.output or args.industry_dir / "industry_incremental_onboarding.csv"
    manifest_path = args.manifest or args.industry_dir / "industry_incremental_onboarding_manifest.json"

    monthly_delta = load_dataframe(args.industry_dir / "industry_monthly_delta.csv.gz")
    curation_queue = load_dataframe(args.industry_dir / "industry_curation_queue.csv.gz")
    document_chunk_plan = load_dataframe(args.industry_dir / "document_chunk_plan.csv")
    plan = build_incremental_onboarding_plan(
        monthly_delta=monthly_delta,
        curation_queue=curation_queue,
        document_chunk_plan=document_chunk_plan,
    )
    save_dataframe(plan, output_path)
    manifest = build_incremental_onboarding_pipeline_manifest(
        industry_dir=args.industry_dir,
        output_path=output_path,
        manifest_path=manifest_path,
        monthly_delta=monthly_delta,
        curation_queue=curation_queue,
        document_chunk_plan=document_chunk_plan,
        plan=plan,
    )
    save_pipeline_manifest(manifest, manifest_path)
    quality = manifest.get("quality", {})
    print(
        f"[ok] onboarding incremental gravado em {output_path} "
        f"({quality.get('rows', 0):,} FIDCs; {quality.get('blocked_rows', 0):,} bloqueados; "
        f"{quality.get('attention_rows', 0):,} atenção; {quality.get('ok_rows', 0):,} ok)"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
