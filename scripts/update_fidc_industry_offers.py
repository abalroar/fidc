"""Refresh every public-offer and BCB input used by Dados da Indústria.

This is the analyst-facing refresh entrypoint.  It downloads the current CVM
archive, normalizes every public-primary rite, rebuilds all offer views,
refreshes the BCB bridge and re-runs the official SRE document curation for the
Top 15 from 2022 through 2026 YTD. The seven legacy observations available for
2022 are retained as a partial, non-comparable period.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

import pandas as pd
import requests

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.industry_bcb_expanded_credit import (
    build_expanded_credit_history,
    write_expanded_credit_history,
)
from services.industry_closed_offer_placement_regime import (
    build_closed_offer_placement_regime,
    write_closed_offer_placement_regime,
)
from services.industry_closed_offers_source import (
    build_closed_offer_tables_from_archive,
    write_closed_offer_tables,
)
from services.industry_fixed_income_offer_comparison import (
    build_fixed_income_offer_comparison,
    write_fixed_income_offer_comparison,
)
from services.industry_offer_document_curation import (
    build_offer_document_curation,
    write_offer_document_curation,
)
from services.industry_offer_ticket_distribution import (
    build_offer_ticket_outputs,
    write_offer_ticket_outputs,
)
from services.industry_public_offers import SOURCE_URL, archive_sha256


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/industry_study")
    parser.add_argument(
        "--archive",
        default=".cache/cvm-offers/oferta_distribuicao.zip",
    )
    parser.add_argument("--source-as-of-date", default="")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-document-curation", action="store_true")
    return parser.parse_args(argv)


def _download_archive(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(SOURCE_URL, timeout=180)
    response.raise_for_status()
    with NamedTemporaryFile(
        dir=target.parent, prefix=target.name + ".", delete=False
    ) as handle:
        handle.write(response.content)
        temporary = Path(handle.name)
    temporary.replace(target)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    archive = Path(args.archive)
    if not args.skip_download:
        _download_archive(archive)
    if not archive.is_file():
        raise SystemExit(f"Arquivo CVM ausente: {archive}")
    source_as_of = (
        args.source_as_of_date
        or pd.Timestamp.now(tz="America/Sao_Paulo").date().isoformat()
    )
    digest = archive_sha256(archive)

    tickets = build_offer_ticket_outputs(
        archive,
        source_as_of_date=source_as_of,
        expected_archive_sha256=digest,
    )
    write_offer_ticket_outputs(tickets, data_dir)
    closed = build_closed_offer_tables_from_archive(
        archive,
        source_as_of_date=source_as_of,
        expected_archive_sha256=digest,
    )
    write_closed_offer_tables(closed, data_dir)
    write_closed_offer_placement_regime(
        build_closed_offer_placement_regime(
            data_dir,
            archive,
            source_as_of_date=source_as_of,
            expected_archive_sha256=digest,
        ),
        data_dir,
    )
    write_fixed_income_offer_comparison(
        build_fixed_income_offer_comparison(
            archive,
            source_as_of_date=source_as_of,
            expected_archive_sha256=digest,
        ),
        data_dir,
    )
    monthly = pd.read_csv(data_dir / "industry_monthly.csv")
    write_expanded_credit_history(
        build_expanded_credit_history(monthly),
        data_dir,
    )
    if not args.skip_document_curation:
        offers = pd.read_csv(
            data_dir / "industry_offers.csv.gz", dtype=str
        )
        write_offer_document_curation(
            build_offer_document_curation(tickets.cohort, offers),
            data_dir,
        )
    print(
        "[ok] ofertas públicas e Carteira de Crédito Privada Ampliada atualizadas; "
        f"SHA-256 CVM {digest}"
    )


if __name__ == "__main__":
    main()
