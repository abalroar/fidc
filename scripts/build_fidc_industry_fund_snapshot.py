"""Materializa a base unificada por FIDC da aba Industria.

O snapshot consolida uma linha por CNPJ de fundo/classe, juntando a foto IME
mais recente, emissões/ofertas, documentos, cedentes/sacados e critérios. Ele
nao substitui as bases detalhe: serve como camada de navegação, filtros,
heatmaps e Deep Dives.

Uso:
    python scripts/build_fidc_industry_fund_snapshot.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_fund_snapshot_pipeline_manifest,
    build_industry_fund_snapshot,
    load_dataframe,
    load_fund_universe,
    load_vehicle_latest,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")
DEFAULT_STRATEGY_DB = Path("data/fidc_credit_strategy/fidc_credit_strategy.sqlite")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the unified one-row-per-FIDC industry snapshot.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--strategy-db", type=Path, default=DEFAULT_STRATEGY_DB)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = args.output or args.industry_dir / "industry_fund_snapshot.csv.gz"
    manifest_path = args.manifest or args.industry_dir / "industry_fund_snapshot_manifest.json"

    vehicle_latest = load_vehicle_latest(args.industry_dir)
    fund_universe = load_fund_universe(args.strategy_db)
    issuance_tranches = load_dataframe(args.industry_dir / "issuance_tranches.csv.gz")
    cedentes = load_dataframe(args.industry_dir / "cedentes_structured.csv.gz")
    criteria = load_dataframe(args.industry_dir / "criteria_structured.csv.gz")
    documents = load_dataframe(args.industry_dir / "document_inventory.csv.gz")

    snapshot = build_industry_fund_snapshot(
        vehicle_latest=vehicle_latest,
        fund_universe=fund_universe,
        issuance_tranches=issuance_tranches,
        cedentes=cedentes,
        criteria=criteria,
        documents=documents,
    )
    save_dataframe(snapshot, output_path)
    manifest = build_fund_snapshot_pipeline_manifest(
        industry_dir=args.industry_dir,
        strategy_db=args.strategy_db,
        output_path=output_path,
        manifest_path=manifest_path,
        vehicle_latest=vehicle_latest,
        fund_universe=fund_universe,
        issuance_tranches=issuance_tranches,
        cedentes=cedentes,
        criteria=criteria,
        documents=documents,
        snapshot=snapshot,
    )
    save_pipeline_manifest(manifest, manifest_path)
    print(
        f"[ok] snapshot gravado em {output_path} "
        f"({len(snapshot):,} FIDCs; {snapshot['camadas_com_evidencia'].median() if not snapshot.empty else 0:.1f} camadas medianas)"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
