"""Materialize CVM provider-history transitions for the May-2026 FIDC cohort."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from services.industry_provider_history import (
    CAD_FI_HISTORY_URL,
    DEFAULT_FROM_DATE,
    DEFAULT_LATEST_COMPETENCE,
    DEFAULT_TO_DATE,
    build_current_fund_cohort,
    build_provider_history_outputs,
    download_provider_history_zip,
    read_provider_history_zip,
    write_provider_history_outputs,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fund-base",
        default="data/industry_study/generated_revision/base_fundo_cnpj.csv.gz",
    )
    parser.add_argument(
        "--ownership-curation",
        default="data/industry_study/provider_ownership_curation.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="data/industry_study/generated_revision",
    )
    parser.add_argument(
        "--source-zip",
        default="",
        help="ZIP local já obtido; se vazio, usa o cache ou baixa da CVM",
    )
    parser.add_argument(
        "--cache-zip",
        default=".cache/cvm-industry-study/cad_fi_hist.zip",
    )
    parser.add_argument("--source-url", default=CAD_FI_HISTORY_URL)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--latest-competence", default=DEFAULT_LATEST_COMPETENCE)
    parser.add_argument("--from-date", default=DEFAULT_FROM_DATE)
    parser.add_argument("--to-date", default=DEFAULT_TO_DATE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    fund_base_path = Path(args.fund_base)
    if not fund_base_path.exists():
        raise SystemExit(f"base por fundo ausente: {fund_base_path}")
    fund_base = pd.read_csv(fund_base_path, low_memory=False)
    ownership_path = Path(args.ownership_curation)
    ownership = (
        pd.read_csv(ownership_path, low_memory=False)
        if ownership_path.exists()
        else None
    )

    if args.source_zip:
        archive_path = Path(args.source_zip)
        if not archive_path.exists():
            raise SystemExit(f"ZIP cadastral ausente: {archive_path}")
    else:
        archive_path = Path(args.cache_zip)
        if not archive_path.exists():
            if args.skip_download:
                raise SystemExit(
                    f"ZIP cadastral ausente e download bloqueado: {archive_path}"
                )
            download_provider_history_zip(
                archive_path, source_url=str(args.source_url)
            )

    cohort = build_current_fund_cohort(
        fund_base, latest_competence=args.latest_competence
    )
    histories = read_provider_history_zip(
        archive_path, cohort_cnpjs=cohort["cnpj_fundo"]
    )
    outputs = build_provider_history_outputs(
        fund_base,
        histories,
        ownership_curation=ownership,
        latest_competence=args.latest_competence,
        from_date=args.from_date,
        to_date=args.to_date,
    )
    manifest = write_provider_history_outputs(
        outputs, Path(args.output_dir), source_archive=archive_path
    )
    transition_coverage = outputs.coverage.loc[
        outputs.coverage["data_referencia"].astype(str).str.contains("→", regex=False),
        ["papel", "fundos_resolvidos_unicos", "cobertura_pl_resolvida"],
    ]
    coverage_text = ", ".join(
        f"{row.papel} {row.cobertura_pl_resolvida:.1%} do PL"
        for row in transition_coverage.itertuples(index=False)
    )
    print(
        "[ok] cadastro histórico CVM materializado: "
        f"{manifest['checks']['cohort_funds']} fundos na coorte; {coverage_text}"
    )


if __name__ == "__main__":
    main()
