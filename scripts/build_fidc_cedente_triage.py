"""Materializa a fila auditável de cedentes da competência jun/26.

Exemplo:
    python scripts/build_fidc_cedente_triage.py \
      --input-workbook /caminho/FIDC_Cedentes_202606.xlsx
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_cedente_triage import (  # noqa: E402
    DEFAULT_COMPETENCE,
    DEFAULT_CUTOFF_RANK,
    materialize_cedente_triage,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Valida FIDC_Cedentes_202606.xlsx e materializa a fila Top N, "
            "a curva de cobertura e o manifesto de qualidade."
        )
    )
    parser.add_argument(
        "--input-workbook",
        type=Path,
        required=True,
        help="Workbook fonte FIDC_Cedentes_202606.xlsx",
    )
    parser.add_argument(
        "--competence",
        default=DEFAULT_COMPETENCE,
        help="Competência no formato YYYYMM (padrão: 202606)",
    )
    parser.add_argument(
        "--cutoff-rank",
        type=int,
        default=DEFAULT_CUTOFF_RANK,
        help="Rank máximo da fila priorizada (padrão: 500)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Diretório de saída; padrão: "
            "data/industry_study/cedente_triage/<competência>"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.cutoff_rank <= 0:
        raise SystemExit("--cutoff-rank deve ser positivo")
    output_dir = args.output_dir or (
        ROOT / "data" / "industry_study" / "cedente_triage" / args.competence
    )
    manifest = materialize_cedente_triage(
        args.input_workbook,
        output_dir,
        competence=args.competence,
        cutoff_rank=args.cutoff_rank,
    )
    coverage = manifest["coverage"]
    top = manifest["cutoff"]["top_queue"]
    print(
        "[ok] "
        f"{coverage['fundos_total']:,} fundos; "
        f"{coverage['fundos_com_cedente']:,} com cedente; "
        f"{coverage['fundos_sem_cedente']:,} sem cedente"
    )
    print(
        "[ok] "
        f"Top {args.cutoff_rank}: {top['fundos']:,} fundos, "
        f"{top['pares_fundo_cedente']:,} pares fundo--cedente e "
        f"{top['fundos_sem_cedente']:,} lacunas da Tabela I"
    )
    print(f"[ok] fila: {manifest['queue_path']}")
    print(f"[ok] curva: {manifest['curve_path']}")
    print(f"[ok] manifesto: {manifest['manifest_path']}")


if __name__ == "__main__":
    main()
