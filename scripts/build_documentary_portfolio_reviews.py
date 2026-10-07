"""Finalize reviewed comparisons for an explicit list of existing portfolio IDs."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.documentary_portfolio_reviews import REVIEW_DIR, enrich_cached_ime, publish_portfolio, publish_profiles, read_review
from services.portfolio_store import LocalPortfolioStore

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portfolio-id', action='append', required=True)
    parser.add_argument('--review-dir', type=Path, default=REVIEW_DIR)
    parser.add_argument('--output-root', type=Path, default=Path('data/deep_dives'))
    args=parser.parse_args()
    ids=set(args.portfolio_id)
    portfolios=[p for p in LocalPortfolioStore(Path('portfolios.json')).list_portfolios() if p.id in ids]
    if len(portfolios)!=len(ids): raise SystemExit('ID inexistente ou duplicado; nenhuma carteira criada.')
    unique={f.cnpj:f for p in portfolios for f in p.funds}
    reviews={cnpj:read_review(cnpj,args.review_dir) for cnpj in unique}
    reviews,cached_ime=enrich_cached_ime(reviews)
    # All identities and fact sources are checked before shared profiles are changed.
    publish_profiles(reviews,list(unique.values()))
    for portfolio in portfolios:
        result=publish_portfolio(portfolio,reviews,args.output_root,cached_ime)
        print(f'{portfolio.name}: {result.cell_count} células, {result.slide_count} slides, {result.package_dir}',flush=True)

if __name__=='__main__': main()
