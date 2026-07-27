"""Build the documentary table for the current Top 20 funds in Outros."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.industry_top20_outros_regulations import (
    CURATION_FILENAME,
    build_top20_outros_regulation_review,
    write_top20_outros_regulation_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/industry_study")
    parser.add_argument(
        "--top20",
        default="data/industry_study/generated_revision/top20_outros.csv",
    )
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    top20 = pd.read_csv(args.top20, dtype={"cnpj_fundo": str})
    curation = pd.read_csv(
        data_dir / CURATION_FILENAME, dtype={"cnpj_fundo": str}
    )
    output = build_top20_outros_regulation_review(top20, curation)
    path = write_top20_outros_regulation_review(output, data_dir)
    print(f"[ok] {len(output)} fundos documentados em {path}")


if __name__ == "__main__":
    main()
