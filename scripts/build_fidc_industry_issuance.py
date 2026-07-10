"""Materializa a camada de emissoes/ofertas da aba Industria.

Consolida o SQLite da aba Estrategia em artefatos reutilizaveis pela aba
Industria. O objetivo e separar claramente volume de emissoes/ofertas de
captacao liquida do Informe Mensal.

Uso:
    python scripts/build_fidc_industry_issuance.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_issuance_annual,
    build_issuance_offers,
    build_issuance_pipeline_manifest,
    build_issuance_sector_year,
    build_issuance_tranches,
    load_fund_universe,
    load_dataframe,
    load_pricing_tranches,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")
DEFAULT_STRATEGY_DB = Path("data/fidc_credit_strategy/fidc_credit_strategy.sqlite")


def latest_strategy_offers_source() -> Path | None:
    candidates = list(
        Path("outputs").glob(
            "fidc_credit_strategy_study_*/issuance/fidc_public_offers_2024_2026ytd.csv"
        )
    )
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, str(path)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build structured issuance/offers data for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--strategy-db", type=Path, default=DEFAULT_STRATEGY_DB)
    parser.add_argument("--annual-output", type=Path, default=None)
    parser.add_argument("--sector-year-output", type=Path, default=None)
    parser.add_argument("--offers-source", type=Path, default=None)
    parser.add_argument("--offers-output", type=Path, default=None)
    parser.add_argument("--tranches-output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    annual_path = args.annual_output or args.industry_dir / "issuance_annual.csv"
    sector_year_path = args.sector_year_output or args.industry_dir / "issuance_sector_year.csv"
    offers_path = args.offers_output or args.industry_dir / "issuance_offers.csv.gz"
    tranches_path = args.tranches_output or args.industry_dir / "issuance_tranches.csv.gz"
    manifest_path = args.manifest or args.industry_dir / "industry_issuance_manifest.json"

    fund_universe = load_fund_universe(args.strategy_db)
    pricing = load_pricing_tranches(args.strategy_db)
    offers_source_path = args.offers_source or latest_strategy_offers_source()
    if offers_source_path is not None and offers_source_path.exists():
        offers = build_issuance_offers(load_dataframe(offers_source_path))
    else:
        offers = load_dataframe(offers_path)
    annual = build_issuance_annual(fund_universe, offers)
    sector_year = build_issuance_sector_year(fund_universe, offers)
    tranches = build_issuance_tranches(pricing)

    save_dataframe(annual, annual_path)
    save_dataframe(sector_year, sector_year_path)
    save_dataframe(offers, offers_path)
    save_dataframe(tranches, tranches_path)
    manifest = build_issuance_pipeline_manifest(
        industry_dir=args.industry_dir,
        strategy_db=args.strategy_db,
        annual_path=annual_path,
        sector_year_path=sector_year_path,
        tranches_path=tranches_path,
        offers_path=offers_path,
        offers_source_path=offers_source_path,
        fund_universe=fund_universe,
        pricing=pricing,
        annual=annual,
        sector_year=sector_year,
        tranches=tranches,
        offers=offers,
    )
    save_pipeline_manifest(manifest, manifest_path)

    print(
        f"[ok] emissoes anuais gravadas em {annual_path} "
        f"({len(annual):,} anos; R$ {annual['volume_conservador_brl'].sum() / 1e9:,.1f} bi conservador)"
    )
    print(f"[ok] setor x ano gravado em {sector_year_path} ({len(sector_year):,} linhas)")
    print(f"[ok] ofertas CVM gravadas em {offers_path} ({len(offers):,} linhas)")
    print(f"[ok] tranches gravadas em {tranches_path} ({len(tranches):,} linhas)")
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
