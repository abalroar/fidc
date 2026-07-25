"""Curate originators and Itaú participation in the 30 largest FIDC offers."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.industry_offer_document_curation import (
    build_offer_document_curation,
    write_offer_document_curation,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/industry_study")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    cohort = pd.read_csv(data_dir / "industry_closed_offer_ticket_cohort.csv.gz")
    offers = pd.read_csv(data_dir / "industry_offers.csv.gz", dtype=str)
    output = write_offer_document_curation(
        build_offer_document_curation(cohort, offers),
        data_dir,
    )
    print(f"[ok] curadoria documental de ofertas materializada: {output}")


if __name__ == "__main__":
    main()
