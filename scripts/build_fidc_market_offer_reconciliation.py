#!/usr/bin/env python3
"""Build the frozen CVM/ANBIMA market-offer reconciliation table."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.industry_market_offer_reconciliation import (
    CVM_ARCHIVE_SHA256,
    CVM_SOURCE_AS_OF_DATE,
    build_market_offer_reconciliation,
    load_anbima_market_offers,
    write_market_offer_reconciliation,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--archive",
        default=str(ROOT / ".cache/cvm-offers/oferta_distribuicao.zip"),
    )
    parser.add_argument(
        "--data-dir", default=str(ROOT / "data/industry_study")
    )
    parser.add_argument("--source-as-of-date", default=CVM_SOURCE_AS_OF_DATE)
    parser.add_argument("--expected-archive-sha256", default=CVM_ARCHIVE_SHA256)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    anbima = load_anbima_market_offers(data_dir)
    output = build_market_offer_reconciliation(
        args.archive,
        anbima,
        cvm_source_as_of_date=args.source_as_of_date,
        expected_cvm_archive_sha256=(
            args.expected_archive_sha256 or None
        ),
    )
    path = write_market_offer_reconciliation(output, data_dir)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
