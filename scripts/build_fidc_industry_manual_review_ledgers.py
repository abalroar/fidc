"""Inicializa ledgers de revisao manual da aba Industria.

Cria arquivos CSV ausentes com os cabecalhos oficiais para que a UI consiga
persistir acoes e auditoria sem exigir edicao manual de arquivos internos.
Nao cria decisoes, aprovacoes ou eventos artificiais.

Uso:
    python scripts/build_fidc_industry_manual_review_ledgers.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_manual_review_pipeline_manifest,
    initialize_manual_review_ledgers,
    manual_review_ledgers_quality_summary,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize in-app manual review ledgers for the FIDC Industry tab.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_path = args.manifest or args.industry_dir / "industry_manual_review_manifest.json"

    ledger_files = initialize_manual_review_ledgers(industry_dir=args.industry_dir)
    manifest = build_manual_review_pipeline_manifest(
        industry_dir=args.industry_dir,
        manifest_path=manifest_path,
        ledger_files=ledger_files,
    )
    save_pipeline_manifest(manifest, manifest_path)
    quality = manual_review_ledgers_quality_summary(ledger_files)
    print(
        f"[ok] ledgers de revisao manual verificados em {args.industry_dir} "
        f"({quality.get('files_present', 0)}/{quality.get('files', 0)} arquivos; "
        f"{quality.get('schema_ok_files', 0)} schemas ok; {quality.get('files_created', 0)} criados)"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
