"""Materialize the auditable closed-FIDC-offer tables through June 2026."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.industry_closed_offers_source import (
    SOURCE_ARCHIVE_SHA256,
    SOURCE_AS_OF_DATE,
    build_closed_offer_tables_from_archive,
    write_closed_offer_tables,
)


from services.industry_comparative_period import ComparisonCut

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, help="oferta_distribuicao.zip da CVM")
    parser.add_argument("--output-dir", default="data/industry_study")
    parser.add_argument("--source-as-of-date", default=SOURCE_AS_OF_DATE)
    parser.add_argument(
        "--expected-sha256",
        default=None,
        help="vazio desabilita a trava de hash",
    )
    parser.add_argument("--latest-complete", help="Competência consolidada AAAA-MM; omitida, lê a base de saída")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    cut = ComparisonCut.from_competence(args.latest_complete) if args.latest_complete else ComparisonCut.from_data_dir(getattr(args, "data_dir", args.output_dir))
    tables = build_closed_offer_tables_from_archive(
        args.archive,
        source_as_of_date=args.source_as_of_date,
        expected_archive_sha256=args.expected_sha256 or None,
        comparison_cut=cut,
    )
    manifest = write_closed_offer_tables(tables, args.output_dir)
    print(
        "[ok] ofertas encerradas materializadas: "
        f"{manifest['annual_rows']} anos, {manifest['monthly_rows']} meses, "
        f"{manifest['originator_rows']} originadores, "
        f"SHA-256 {manifest['source_archive_sha256']}"
    )


if __name__ == "__main__":
    main()
