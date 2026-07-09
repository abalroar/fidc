"""Materializa criterios monitoraveis e subordinação mínima da aba Industria.

Consolida a curadoria documental all FIDCs em uma base estruturada, auditavel e
reutilizavel para medianas, heatmaps, deep dives e revisao manual pela UI.

Uso:
    python scripts/build_fidc_industry_criteria.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_criteria_pipeline_manifest,
    build_criteria_structured,
    load_criteria_reviews,
    load_criteria_source,
    load_document_criteria_candidates,
    load_fund_universe,
    load_regulatory_feature_criteria,
    load_review_audit,
    save_dataframe,
    save_criteria_reviews,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")
DEFAULT_STRATEGY_DB = Path("data/fidc_credit_strategy/fidc_credit_strategy.sqlite")
DEFAULT_CRITERIA_SOURCE = Path("data/regulatory_profiles/all_fidcs_criteria_monitoraveis_ime.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build structured regulatory criteria for the FIDC industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--strategy-db", type=Path, default=DEFAULT_STRATEGY_DB)
    parser.add_argument("--criteria-source", type=Path, default=DEFAULT_CRITERIA_SOURCE)
    parser.add_argument("--reviews", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reviews_path = args.reviews or args.industry_dir / "criteria_reviews.csv"
    output_path = args.output or args.industry_dir / "criteria_structured.csv.gz"
    manifest_path = args.manifest or args.industry_dir / "industry_criteria_manifest.json"
    review_audit_path = args.industry_dir / "criteria_review_audit.csv"

    documentary_criteria = load_criteria_source(args.criteria_source)
    document_candidates_path = args.industry_dir / "document_criteria_candidates.csv.gz"
    document_candidates = load_document_criteria_candidates(document_candidates_path)
    regulatory_features = load_regulatory_feature_criteria(args.strategy_db)
    criteria = pd.concat(
        [documentary_criteria, document_candidates, regulatory_features],
        ignore_index=True,
        sort=False,
    )
    if not criteria.empty and "rule_id" in criteria.columns:
        criteria = criteria.drop_duplicates("rule_id", keep="first")
    reviews = load_criteria_reviews(reviews_path)
    if not reviews_path.exists():
        save_criteria_reviews(reviews, reviews_path)
    fund_universe = load_fund_universe(args.strategy_db)
    structured = build_criteria_structured(
        criteria,
        reviews,
        fund_universe=fund_universe,
        review_audit=load_review_audit(review_audit_path),
    )
    save_dataframe(structured, output_path)
    manifest = build_criteria_pipeline_manifest(
        industry_dir=args.industry_dir,
        strategy_db=args.strategy_db,
        criteria_source_path=args.criteria_source,
        document_candidates_path=document_candidates_path,
        reviews_path=reviews_path,
        output_path=output_path,
        manifest_path=manifest_path,
        criteria=criteria,
        reviews=reviews,
        fund_universe=fund_universe,
        structured=structured,
    )
    save_pipeline_manifest(manifest, manifest_path)

    sub = structured[structured["chave"].eq("subordination_ratio_min")] if "chave" in structured else structured.iloc[0:0]
    print(
        f"[ok] criterios estruturados gravados em {output_path} "
        f"({len(structured):,} regras; {structured['cnpj_fundo'].nunique() if 'cnpj_fundo' in structured else 0:,} FIDCs)"
    )
    print(
        f"[ok] matriz regulatória Estratégia: {len(regulatory_features):,} sinais positivos "
        f"em {regulatory_features['CNPJ'].nunique() if 'CNPJ' in regulatory_features else 0:,} FIDCs"
    )
    print(f"[ok] subordinação mínima: {len(sub):,} regras em {sub['cnpj_fundo'].nunique() if 'cnpj_fundo' in sub else 0:,} FIDCs")
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
