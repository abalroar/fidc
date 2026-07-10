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
    build_public_claim_methodology_bridge,
    build_public_claim_audit_pipeline_manifest,
    load_dataframe,
    public_claim_audit_quality_summary,
    public_claim_methodology_bridge_quality_summary,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build public claim audit for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--industry-monthly", type=Path, default=None)
    parser.add_argument("--issuance-tranches", type=Path, default=None)
    parser.add_argument("--issuance-offers", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--bridge", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    industry_monthly_path = args.industry_monthly or args.industry_dir / "industry_monthly.csv"
    issuance_tranches_path = args.issuance_tranches or args.industry_dir / "issuance_tranches.csv.gz"
    issuance_offers_path = args.issuance_offers or args.industry_dir / "issuance_offers.csv.gz"
    output_path = args.output or args.industry_dir / "industry_public_claim_audit.csv"
    bridge_path = args.bridge or args.industry_dir / "industry_public_claim_methodology_bridge.csv"
    manifest_path = args.manifest or args.industry_dir / "industry_public_claim_audit_manifest.json"

    industry_monthly = load_dataframe(industry_monthly_path)
    issuance_tranches = load_dataframe(issuance_tranches_path)
    issuance_offers = load_dataframe(issuance_offers_path)
    audit = build_public_claim_audit(
        industry_monthly=industry_monthly,
        issuance_tranches=issuance_tranches,
        issuance_offers=issuance_offers,
    )
    bridge = build_public_claim_methodology_bridge(audit)
    save_dataframe(audit, output_path)
    save_dataframe(bridge, bridge_path)
    manifest = build_public_claim_audit_pipeline_manifest(
        industry_dir=args.industry_dir,
        output_path=output_path,
        bridge_path=bridge_path,
        manifest_path=manifest_path,
        industry_monthly_path=industry_monthly_path,
        issuance_tranches_path=issuance_tranches_path,
        industry_monthly=industry_monthly,
        issuance_tranches=issuance_tranches,
        issuance_offers_path=issuance_offers_path,
        issuance_offers=issuance_offers,
        audit=audit,
        bridge=bridge,
    )
    save_pipeline_manifest(manifest, manifest_path)
    quality = public_claim_audit_quality_summary(audit)
    bridge_quality = public_claim_methodology_bridge_quality_summary(bridge)
    print(
        f"[ok] auditoria publica gravada em {output_path} "
        f"({quality.get('rows', 0):,} claims; {quality.get('claims_with_local_metric', 0):,} com metrica local)"
    )
    print(
        f"[ok] ponte metodologica gravada em {bridge_path} "
        f"({bridge_quality.get('rows', 0):,} linhas; {bridge_quality.get('high_or_blocking_rows', 0):,} alta/bloqueante)"
    )
    print(f"[ok] status: {quality.get('status_counts', {})}")
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
