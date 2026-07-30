"""Materialize the BCB expanded-credit bridge used by the industry deck."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fic_detection import exclude_fics_from_fidc_universe
from services.industry_bcb_expanded_credit import (
    build_expanded_credit_history,
    write_expanded_credit_history,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/industry_study")
    return parser.parse_args(argv)


def _eligible_receivables(data_dir: Path) -> pd.DataFrame | None:
    """Recompute ``carteira_dc`` over the FIDCs that survive the FIC gate.

    ``industry_monthly`` aggregates every vehicle, FICs included.  A FIC holds
    quotas and normally books no receivables, so the two totals nearly agree —
    but a handful of funds the CVM flags as FIC still report a book, and the
    chart has to stand on the eligible universe rather than nearly.
    """

    base_path = data_dir / "generated_revision" / "base_fundo_cnpj.csv.gz"
    if not base_path.exists():
        return None
    base = pd.read_csv(
        base_path,
        dtype=str,
        keep_default_na=False,
        usecols=["competencia", "cnpj_fundo", "carteira_dc", "is_fic_fidc", "pl"],
    )
    base["carteira_dc"] = pd.to_numeric(base["carteira_dc"], errors="coerce").fillna(0.0)
    eligible, report = exclude_fics_from_fidc_universe(base)
    print(
        f"carteira reconstruída sobre o universo elegível: "
        f"{report.cnpj_excluded} CNPJs FIC fora"
    )
    return (
        eligible.groupby("competencia", as_index=False)["carteira_dc"]
        .sum()
        .sort_values("competencia")
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    monthly = _eligible_receivables(data_dir)
    if monthly is None:
        print(
            "AVISO: base revisada ausente; usando industry_monthly, que inclui FICs "
            "na carteira. Rode scripts/build_fidc_revision_analysis.py antes."
        )
        monthly = pd.read_csv(data_dir / "industry_monthly.csv")
    output = write_expanded_credit_history(
        build_expanded_credit_history(monthly),
        data_dir,
    )
    print(f"[ok] Carteira de Crédito Ampliada materializada: {output}")


if __name__ == "__main__":
    main()
