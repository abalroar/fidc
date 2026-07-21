"""Materialize the auditable ticket distribution of closed FIDC offerings."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.industry_offer_ticket_distribution import (
    EXPECTED_SOURCE_ARCHIVE_SHA256,
    SOURCE_AS_OF_DATE,
    build_offer_ticket_outputs,
    write_offer_ticket_outputs,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        required=True,
        help="oferta_distribuicao.zip publicado pela CVM",
    )
    parser.add_argument("--output-dir", default="data/industry_study")
    parser.add_argument("--source-as-of-date", default=SOURCE_AS_OF_DATE)
    parser.add_argument(
        "--expected-sha256",
        default=EXPECTED_SOURCE_ARCHIVE_SHA256,
        help="vazio desabilita a trava de hash",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    outputs = build_offer_ticket_outputs(
        args.archive,
        source_as_of_date=args.source_as_of_date,
        expected_archive_sha256=args.expected_sha256 or None,
    )
    manifest = write_offer_ticket_outputs(outputs, args.output_dir)
    print(
        "[ok] distribuição de tickets materializada: "
        f"{manifest['cohort_rows']} ofertas, "
        f"{manifest['distribution_rows']} linhas agregadas, "
        f"SHA-256 {manifest['source_archive_sha256']}"
    )


if __name__ == "__main__":
    main()
