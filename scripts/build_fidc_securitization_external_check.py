"""Cross-check the FIDC scale against the CRI+CRA stock published by ANBIMA.

The panel states that FIDCs hold roughly R$ 820 bi of net assets and a credit
book near R$ 677 bi.  Both come from the same CVM monthly filing, so they
corroborate each other only as far as that filing is trustworthy.  This script
brings a source the CVM does not touch: the outstanding stock of the two other
securitization instruments, CRI and CRA.

The BCB expanded-credit series already carries a securitization block that
splits into "FIDCs · carteira" — the CVM book, ex-FIC — and a residual for
everything else.  If the residual sat far from what ANBIMA reports for CRI+CRA,
either the split or the FIDC number would be suspect.  Residual above CRI+CRA
is the expected direction and the size of that excess is the finding: the BCB
block also carries certificates of receivables and securitization debentures
that ANBIMA counts elsewhere.

The ANBIMA stock series is an input, not a derivation — it lives in
``industry_anbima_securitization_stock.csv`` with its source, and this script
only compares.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

ANBIMA_STOCK_FILENAME = "industry_anbima_securitization_stock.csv"
BCB_FILENAME = "industry_bcb_expanded_credit.csv"
OUTPUT_FILENAME = "checagem_externa_securitizacao.csv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/analysis"))
    return parser.parse_args(argv)


def build_external_check(data_dir: Path) -> pd.DataFrame:
    """Return one row per competence comparing the residual with CRI+CRA."""

    anbima = pd.read_csv(data_dir / ANBIMA_STOCK_FILENAME)
    anbima["stock_brl"] = pd.to_numeric(anbima["stock_brl"], errors="coerce")
    cri_cra = (
        anbima[anbima["instrument_label"].isin(["CRI", "CRA"])]
        .groupby(["competencia", "period_label"], as_index=False)["stock_brl"]
        .sum()
        .rename(columns={"stock_brl": "anbima_cri_cra_stock_brl"})
    )

    bcb = pd.read_csv(data_dir / BCB_FILENAME)
    bcb["competencia"] = bcb["competencia"].astype(str).str[:7]
    columns = [
        "competencia",
        "fidc_receivables_brl",
        "other_securitization_brl",
        "securitization_brl",
        "private_expanded_credit_total_brl",
    ]
    scoped = bcb.loc[bcb["competencia"].isin(set(cri_cra["competencia"])), columns]
    for column in columns[1:]:
        scoped[column] = pd.to_numeric(scoped[column], errors="coerce")

    merged = cri_cra.merge(scoped, on="competencia", how="inner", validate="one_to_one")
    if len(merged) != len(cri_cra):
        missing = sorted(set(cri_cra["competencia"]) - set(merged["competencia"]))
        raise SystemExit(
            "competências sem correspondência na série do BCB: " + ", ".join(missing)
        )

    merged["gap_brl"] = (
        merged["other_securitization_brl"] - merged["anbima_cri_cra_stock_brl"]
    )
    merged["gap_share_of_securitization"] = (
        merged["gap_brl"] / merged["securitization_brl"]
    )
    merged["gap_share_of_private_credit"] = (
        merged["gap_brl"] / merged["private_expanded_credit_total_brl"]
    )
    merged["gap_share_of_anbima_cri_cra"] = (
        merged["gap_brl"] / merged["anbima_cri_cra_stock_brl"]
    )
    merged["fidc_over_cri_cra"] = (
        merged["fidc_receivables_brl"] / merged["anbima_cri_cra_stock_brl"]
    )
    # Um resíduo abaixo do estoque CRI+CRA significaria que a série do BCB não
    # comporta nem os dois instrumentos que a ANBIMA mede — sinal de que a
    # carteira de FIDC estaria absorvendo volume alheio.  É a leitura que
    # invalidaria o número, e por isso é verificada em vez de assumida.
    inverted = merged[merged["gap_brl"] < 0]
    if not inverted.empty:
        raise SystemExit(
            "resíduo de securitização abaixo do estoque CRI+CRA em "
            + ", ".join(inverted["competencia"])
            + "; a carteira de FIDC precisa ser revista antes de publicar"
        )
    return merged.sort_values("competencia").reset_index(drop=True)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    check = build_external_check(args.data_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / OUTPUT_FILENAME
    check.to_csv(output, index=False)
    print(f"[ok] checagem externa materializada: {output}")
    for row in check.itertuples(index=False):
        print(
            f"  {row.period_label}: outras securitizações (BCB) "
            f"R$ {row.other_securitization_brl / 1e9:,.0f} bi vs CRI+CRA (ANBIMA) "
            f"R$ {row.anbima_cri_cra_stock_brl / 1e9:,.0f} bi | gap "
            f"R$ {row.gap_brl / 1e9:,.0f} bi "
            f"({row.gap_share_of_anbima_cri_cra:.1%} sobre CRI+CRA, "
            f"{row.gap_share_of_private_credit:.2%} do crédito privado ampliado) | "
            f"carteira FIDC {row.fidc_over_cri_cra:.2f}× CRI+CRA"
        )


if __name__ == "__main__":
    main()
