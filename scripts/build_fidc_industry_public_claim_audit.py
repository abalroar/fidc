"""Materializa auditoria de claims publicos para a aba Industria.

Compara numeros citados em noticias/boletins publicos com metricas locais ja
materializadas no estudo da industria. O modulo nao baixa dados externos: os
claims ficam declarados no codigo com URL, data, valor e ressalva metodologica.

Uso:
    python scripts/build_fidc_industry_public_claim_audit.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_public_claim_audit,
    build_public_claim_audit_pipeline_manifest,
    load_dataframe,
    public_claim_audit_quality_summary,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build public claim audit for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--industry-monthly", type=Path, default=None)
    parser.add_argument("--issuance-tranches", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    industry_monthly_path = args.industry_monthly or args.industry_dir / "industry_monthly.csv"
    issuance_tranches_path = args.issuance_tranches or args.industry_dir / "issuance_tranches.csv.gz"
    output_path = args.output or args.industry_dir / "industry_public_claim_audit.csv"
    manifest_path = args.manifest or args.industry_dir / "industry_public_claim_audit_manifest.json"

    industry_monthly = load_dataframe(industry_monthly_path)
    issuance_tranches = load_dataframe(issuance_tranches_path)
    audit = build_public_claim_audit(
        industry_monthly=industry_monthly,
        issuance_tranches=issuance_tranches,
    )
    save_dataframe(audit, output_path)
    manifest = build_public_claim_audit_pipeline_manifest(
        industry_dir=args.industry_dir,
        output_path=output_path,
        manifest_path=manifest_path,
        industry_monthly_path=industry_monthly_path,
        issuance_tranches_path=issuance_tranches_path,
        industry_monthly=industry_monthly,
        issuance_tranches=issuance_tranches,
        audit=audit,
    )
    save_pipeline_manifest(manifest, manifest_path)
    quality = public_claim_audit_quality_summary(audit)
    print(
        f"[ok] auditoria publica gravada em {output_path} "
        f"({quality.get('rows', 0):,} claims; {quality.get('claims_with_local_metric', 0):,} com metrica local)"
    )
    print(f"[ok] status: {quality.get('status_counts', {})}")
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
