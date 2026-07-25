"""Materialize the BCB expanded-credit bridge used by the industry deck."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.industry_bcb_expanded_credit import (
    build_expanded_credit_history,
    write_expanded_credit_history,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/industry_study")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    monthly = pd.read_csv(data_dir / "industry_monthly.csv")
    output = write_expanded_credit_history(
        build_expanded_credit_history(monthly),
        data_dir,
    )
    print(f"[ok] Carteira de Crédito Ampliada materializada: {output}")


if __name__ == "__main__":
    main()
