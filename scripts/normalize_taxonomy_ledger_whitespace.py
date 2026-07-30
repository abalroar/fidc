#!/usr/bin/env python3
"""Re-commit ledger rows whose text fields are not whitespace-normalized.

``assert_taxonomy_review_ledger_matches_audit`` replays the audit trail through
the module's own normalization, which collapses runs of whitespace.  A decision
stored with a double space in the evidence therefore stops being reproducible
from its own trail even though nothing about the decision changed.

This script rewrites only whitespace: the status, the five taxonomies and every
other value stay byte-identical once normalized.  Each rewrite is recorded in
the audit trail like any other commit.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_taxonomy_review import (  # noqa: E402
    TAXONOMY_REVIEW_COLUMNS,
    commit_taxonomy_review_action,
    load_taxonomy_review_actions,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument("--saved-at-utc", default="")
    parser.add_argument(
        "--source", default="whitespace_normalization_taxonomy_ledger"
    )
    return parser.parse_args()


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def main() -> None:
    args = parse_args()
    saved_at_utc = args.saved_at_utc or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()
    ledger_path = args.data_dir / "taxonomy_review_actions.csv"
    audit_path = args.data_dir / "taxonomy_review_audit.csv"
    ledger = load_taxonomy_review_actions(ledger_path)

    rewritten = 0
    for record in ledger.to_dict(orient="records"):
        normalized = {
            column: normalize(record.get(column, "")) for column in TAXONOMY_REVIEW_COLUMNS
        }
        if all(
            str(record.get(column, "")) == normalized[column]
            for column in TAXONOMY_REVIEW_COLUMNS
        ):
            continue
        commit_taxonomy_review_action(
            normalized,
            ledger_path,
            audit_path,
            saved_at_utc=saved_at_utc,
            source=args.source,
        )
        rewritten += 1

    print(f"{rewritten} decisões normalizadas de {len(ledger)}")


if __name__ == "__main__":
    main()
