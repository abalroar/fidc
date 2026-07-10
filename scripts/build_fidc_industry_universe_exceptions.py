"""Materializa divergências de universo CVM e o overlay de decisão manual."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (  # noqa: E402
    REVIEW_AUDIT_COLUMNS,
    build_industry_universe_exceptions,
    build_universe_exception_pipeline_manifest,
    load_dataframe,
    load_industry_universe_reviews,
    load_review_audit,
    save_dataframe,
    save_industry_universe_reviews,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CVM universe exceptions for the Industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--reviews", type=Path, default=None)
    parser.add_argument("--audit", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = args.output or args.industry_dir / "industry_universe_exceptions.csv.gz"
    reviews_path = args.reviews or args.industry_dir / "universe_scope_reviews.csv"
    audit_path = args.audit or args.industry_dir / "universe_scope_review_audit.csv"
    manifest_path = args.manifest or args.industry_dir / "industry_universe_exception_manifest.json"
    reviews = load_industry_universe_reviews(reviews_path)
    if not reviews_path.exists():
        reviews = save_industry_universe_reviews(reviews, reviews_path)
    audit = load_review_audit(audit_path)
    if not audit_path.exists():
        save_dataframe(pd.DataFrame(columns=REVIEW_AUDIT_COLUMNS), audit_path)
    exceptions = build_industry_universe_exceptions(
        load_dataframe(args.industry_dir / "industry_curation_package_evidence.csv.gz"),
        reviews=reviews,
        review_audit=audit,
    )
    save_dataframe(exceptions, output_path)
    manifest = build_universe_exception_pipeline_manifest(
        industry_dir=args.industry_dir,
        output_path=output_path,
        reviews_path=reviews_path,
        audit_path=audit_path,
        manifest_path=manifest_path,
        exceptions=exceptions,
    )
    save_pipeline_manifest(manifest, manifest_path)
    quality = manifest.get("quality", {})
    print(
        f"[ok] exceções de universo gravadas em {output_path} "
        f"({quality.get('rows', 0)} CNPJs; {quality.get('pending_rows', 0)} pendentes; "
        f"{quality.get('maintained_rows', 0)} mantidos; {quality.get('excluded_rows', 0)} excluídos)"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
