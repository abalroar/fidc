#!/usr/bin/env python3
"""Run the taxonomy cross-check and materialize the findings for review."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.taxonomy_crosscheck import (  # noqa: E402
    crosscheck_taxonomy,
    load_ledger_for_crosscheck,
    summarize,
)


OUTPUT_FILENAME = "industry_taxonomy_crosscheck.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = args.data_dir
    ledger = load_ledger_for_crosscheck(data_dir)
    if ledger.empty:
        print("ledger vazio; nada a conferir")
        return

    published = None
    published_path = data_dir / "industry_outros_reclassification_conclusions.csv"
    if published_path.exists():
        published = pd.read_csv(published_path, dtype=str, keep_default_na=False)
        published = published.rename(
            columns={
                "tipo_anbima_sugerido": "tipo_analitico",
                "foco_anbima_sugerido": "foco_analitico",
            }
        )
        published = published[published["decision_status"].eq("aprovado")]

    findings = crosscheck_taxonomy(ledger, published=published)
    output = data_dir / OUTPUT_FILENAME
    findings.to_csv(output, index=False)
    report = summarize(findings)

    print(f"{report.findings} inconsistências gravadas em {output}")
    print(f"PL envolvido: R$ {report.pl_involved_brl / 1e9:.2f} bi")
    print("\npor regra:")
    for rule, count in sorted(report.by_rule.items(), key=lambda item: -item[1]):
        print(f"  {count:>5}  {rule}")
    if not findings.empty:
        print("\n15 maiores por PL:")
        for _, row in findings.nlargest(15, "pl_max").iterrows():
            print(
                f"  R$ {row['pl_max'] / 1e9:6.2f} bi  {row['regra']:<42} "
                f"{row['nome_fidc'][:48]}"
            )


if __name__ == "__main__":
    main()
