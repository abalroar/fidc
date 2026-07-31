"""Materialize FIDC versus eligible fixed-income closed offerings."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.industry_fixed_income_offer_comparison import (
    SOURCE_ARCHIVE_SHA256,
    SOURCE_AS_OF_DATE,
    apply_anbima_2023_fidc_issuance_correction,
    build_fixed_income_offer_comparison,
    write_fixed_income_offer_comparison,
)
from services.industry_market_offer_reconciliation import (
    load_anbima_market_offers,
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
        default=SOURCE_ARCHIVE_SHA256,
        help="vazio desabilita a trava de hash",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    frame = build_fixed_income_offer_comparison(
        args.archive,
        source_as_of_date=args.source_as_of_date,
        expected_archive_sha256=args.expected_sha256 or None,
    )
    # A série CVM só captura o universo de FIDC integralmente a partir de 2024;
    # o nível de 2023 sai do Boletim ANBIMA antes de o artefato ser gravado,
    # para que nenhum consumidor leia o valor subestimado.
    frame = apply_anbima_2023_fidc_issuance_correction(
        frame, load_anbima_market_offers(args.output_dir)
    )
    output = write_fixed_income_offer_comparison(frame, args.output_dir)
    print(
        "[ok] comparativo de ofertas encerradas materializado: "
        f"{len(frame)} linhas em {output}"
    )


if __name__ == "__main__":
    main()
