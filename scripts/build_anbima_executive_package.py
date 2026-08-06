"""Write the ANBIMA executive package to disk.

Both artefacts are rendered by ``services.anbima_executive_export``; this is a
thin CLI around it so the same bytes reach the Streamlit download buttons and
the files on disk.

    python scripts/build_anbima_executive_package.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.anbima_executive_export import (  # noqa: E402
    DEFAULT_DATA_DIR,
    build_anbima_deck_bytes,
    build_anbima_workbook_bytes,
    resolve_source_workbooks,
)

DEFAULT_OUTPUT_DIR = Path("outputs/anbima_executivo_1s26")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Diretório com as planilhas oficiais em sources/.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ranking_path, annex_path = resolve_source_workbooks(args.data_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    deck_path = args.output_dir / "ANBIMA_Itau_BBA_Renda_Fixa_1S26.pptx"
    workbook_path = args.output_dir / "ANBIMA_Analise_Itau_BBA_1S26.xlsx"
    deck_path.write_bytes(build_anbima_deck_bytes(args.data_dir))
    workbook_path.write_bytes(build_anbima_workbook_bytes(args.data_dir))

    print(f"ranking: {ranking_path}")
    print(f"anexo:   {annex_path}")
    print(f"deck:     {deck_path}")
    print(f"workbook: {workbook_path}")


if __name__ == "__main__":
    main()
