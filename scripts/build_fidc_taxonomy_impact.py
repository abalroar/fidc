#!/usr/bin/env python3
"""Build the reconciled June/2026 taxonomy-impact CSVs.

The script reads ``origin/main`` through ``git show`` and never checks out or
rewrites baseline files.  The audited workbook is required because its
``Mix ANBIMA`` sheet carries the historical R$ 880.4 bi perimeter; the current
fund base carries the separate revision-bundle perimeter.
"""

from __future__ import annotations

import argparse
from io import StringIO
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from services.industry_taxonomy_impact import (
    build_taxonomy_impact_report,
    file_sha256,
    git_blob_text,
    git_ref_commit,
    load_source_mix,
    materialize_taxonomy_impact,
    taxonomy_actions_from_csv_text,
)
from services.industry_taxonomy_review import load_taxonomy_review_actions


DECISIONS_RELATIVE = Path(
    "data/industry_study/industry_taxonomy_audited_decisions_202606.csv"
)
FUND_BASE_RELATIVE = Path(
    "data/industry_study/generated_revision/base_fundo_cnpj.csv.gz"
)
LEDGER_RELATIVE = Path("data/industry_study/taxonomy_review_actions.csv")
ISSUANCE_RELATIVE = Path(
    "data/industry_study/industry_issuance_taxonomy_delta.csv"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", type=Path, default=Path.cwd())
    parser.add_argument(
        "--audit-workbook",
        type=Path,
        required=True,
        help="Industria_FIDC_202606_auditada.xlsx used as source of truth",
    )
    parser.add_argument("--baseline-ref", default="origin/main")
    parser.add_argument(
        "--data-dir", type=Path, default=Path("data/industry_study")
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_dir = args.repo_dir.resolve()
    data_dir = (
        args.data_dir
        if args.data_dir.is_absolute()
        else repo_dir / args.data_dir
    )
    workbook = args.audit_workbook.resolve()
    baseline_commit = git_ref_commit(repo_dir, args.baseline_ref)

    decisions = pd.read_csv(repo_dir / DECISIONS_RELATIVE, dtype=str)
    decisions["pl_brl"] = pd.to_numeric(decisions["pl_brl"], errors="coerce")
    source_mix = load_source_mix(workbook)
    fund_base = pd.read_csv(repo_dir / FUND_BASE_RELATIVE, low_memory=False)
    baseline_actions = taxonomy_actions_from_csv_text(
        git_blob_text(repo_dir, args.baseline_ref, LEDGER_RELATIVE)
    )
    current_actions = load_taxonomy_review_actions(repo_dir / LEDGER_RELATIVE)
    baseline_issuance = pd.read_csv(
        StringIO(git_blob_text(repo_dir, args.baseline_ref, ISSUANCE_RELATIVE))
    )
    current_issuance = pd.read_csv(repo_dir / ISSUANCE_RELATIVE)

    current_ledger_hash = file_sha256(repo_dir / LEDGER_RELATIVE)
    source_label = (
        f"{workbook.name}; sha256={file_sha256(workbook)}; "
        f"aba=Mix ANBIMA"
    )
    baseline_label = f"git {args.baseline_ref}@{baseline_commit}"
    current_label = (
        f"ledger atual sha256={current_ledger_hash}; base corrente de 2026-06"
    )
    report = build_taxonomy_impact_report(
        decisions=decisions,
        source_mix=source_mix,
        fund_base=fund_base,
        baseline_actions=baseline_actions,
        current_actions=current_actions,
        baseline_issuance=baseline_issuance,
        current_issuance=current_issuance,
        source_label=source_label,
        baseline_label=baseline_label,
        current_label=current_label,
    )
    paths = materialize_taxonomy_impact(report, data_dir)
    for name, path in paths.items():
        print(f"[ok] {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
