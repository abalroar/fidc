"""Finalize the reviewed comparison/PPTX contract for one saved portfolio."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.document_curation_contract import DocumentCurationContractError, finalize_document_curation, find_document_curation_package
from services.portfolio_store import LocalPortfolioStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida os sete comparativos curados e publica seu PPTX no pacote da carteira existente.")
    parser.add_argument("--portfolio-id", required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/deep_dives")
    parser.add_argument("--check", action="store_true", help="Validação somente leitura; um export ainda inexistente é informado.")
    parser.add_argument("--reading-at", help="Data efetiva da leitura, ISO 8601 com fuso. Sem este argumento, preserva a data existente.")
    args = parser.parse_args()
    try:
        matches = [portfolio for portfolio in LocalPortfolioStore(ROOT / "portfolios.json").list_portfolios() if portfolio.id == args.portfolio_id]
        if len(matches) != 1:
            raise DocumentCurationContractError(f"ID deve identificar exatamente uma carteira salva: {args.portfolio_id}.")
        portfolio = matches[0]
        package_dir = find_document_curation_package(portfolio, args.output_root)
        result = finalize_document_curation(package_dir, portfolio, output_root=args.output_root, reading_at=args.reading_at, check_only=args.check)
    except (DocumentCurationContractError, OSError, ValueError) as exc:
        parser.exit(1, f"Curadoria não finalizada: {exc}\n")
    action = "Finalizado"
    if args.check:
        action = "Validado (somente leitura)" if result.export_exists else "Preparação validada (somente leitura; PPTX ainda não persistido)"
    print(f"{action}: {portfolio.name} ({portfolio.id})")
    print(f"Pacote: {result.package_dir}")
    print(f"Leitura: {result.generated_at}; comparativos: {result.table_count}; células com evidência: {result.cell_count}; slides: {result.slide_count}")
    if result.export_exists:
        print(f"PPTX: exports/documentary_comparison.pptx; SHA-256: {result.pptx_sha256}")
    else:
        print("PPTX ainda não persistido; execute sem --check para disponibilizá-lo no pacote.")


if __name__ == "__main__":
    main()
