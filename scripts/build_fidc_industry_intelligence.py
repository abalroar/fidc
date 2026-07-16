"""Build the executive intelligence layer for the FIDC Industry tab."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
import urllib.request

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_intelligence import (  # noqa: E402
    build_competence_status,
    build_competitive_position,
    build_investor_distribution,
    build_investor_types,
    build_offer_annual,
    build_offer_rankings,
    build_originator_annual,
    build_stock_ranking_deltas,
    intelligence_manifest,
    latest_complete_competence,
    load_cvm_offers_zip,
)


OFFERS_URL = "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/oferta_distribuicao.zip"
DEFAULT_INDUSTRY_DIR = Path("data/industry_study")
DEFAULT_CACHE_PATH = Path(".cache/cvm-industry-study/oferta_distribuicao.zip")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--offers-zip", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--skip-download", action="store_true")
    return parser.parse_args()


def download_offers(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        OFFERS_URL,
        headers={"User-Agent": "fidc-industry-intelligence/1.0 (dados.cvm.gov.br open data)"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        path.write_bytes(response.read())


def save(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression="gzip" if path.suffix == ".gz" else None)


def main() -> None:
    args = parse_args()
    as_of = date.fromisoformat(args.as_of)
    if not args.skip_download:
        download_offers(args.offers_zip)
    if not args.offers_zip.exists():
        raise SystemExit(f"Arquivo de ofertas não encontrado: {args.offers_zip}")

    industry = pd.read_csv(args.industry_dir / "industry_monthly.csv")
    audit_path = args.industry_dir / "update_audit_monthly.csv"
    audit = pd.read_csv(audit_path) if audit_path.exists() else pd.DataFrame()
    status = build_competence_status(industry, audit)
    latest_complete = latest_complete_competence(status, fallback=str(industry.iloc[-1]["competencia"]))

    offers = load_cvm_offers_zip(args.offers_zip, as_of=as_of)
    annual = build_offer_annual(offers)
    offer_rankings = build_offer_rankings(offers)
    originators = build_originator_annual(offers)
    investor_distribution = build_investor_distribution(offers)
    investor_types = build_investor_types(offers)
    competitive_position = build_competitive_position(offers)

    vehicle = pd.read_csv(args.industry_dir / "vehicle_monthly.csv.gz", low_memory=False)
    stock_rankings = build_stock_ranking_deltas(vehicle, latest_competence=latest_complete)

    save(status, args.industry_dir / "industry_competence_status.csv")
    save(offers, args.industry_dir / "industry_offers.csv.gz")
    save(annual, args.industry_dir / "industry_offers_annual.csv")
    save(offer_rankings, args.industry_dir / "industry_offer_rankings.csv.gz")
    save(originators, args.industry_dir / "industry_originators_annual.csv")
    save(investor_distribution, args.industry_dir / "industry_investor_distribution.csv")
    save(investor_types, args.industry_dir / "industry_investor_types.csv")
    save(competitive_position, args.industry_dir / "industry_competitive_position.csv")
    save(stock_rankings, args.industry_dir / "industry_stock_ranking_deltas.csv.gz")

    manifest = intelligence_manifest(
        offers=offers,
        annual=annual,
        rankings=offer_rankings,
        originators=originators,
        investor_distribution=investor_distribution,
        investor_types=investor_types,
        stock_rankings=stock_rankings,
        source_path=args.offers_zip,
        as_of=as_of,
    )
    manifest["latest_complete_competence"] = latest_complete
    manifest["latest_available_competence"] = str(status.iloc[-1]["competencia"])
    (args.industry_dir / "industry_intelligence_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        "[ok] inteligência executiva: "
        f"{len(offers):,} ofertas, {len(stock_rankings):,} linhas de ranking; "
        f"competência publicável {latest_complete}"
    )


if __name__ == "__main__":
    main()
