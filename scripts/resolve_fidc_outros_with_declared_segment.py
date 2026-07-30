#!/usr/bin/env python3
"""Close open ``Outros`` conclusions with the Tabela II the fund itself declared.

The documentary reading describes the mandate the regulation permits.  The
structured monthly report (IME) filed with the CVM describes the portfolio the
fund actually holds.  When the reading left families disputing the mandate, or
produced nothing usable because no document was legible, the declared segment
resolves the case — and it is a regulatory filing of the vehicle, not an
inference.

The script only touches conclusions in ``em_revisao`` or ``pendente``; anything
already approved or rejected is left untouched.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_outros_reclassification import (  # noqa: E402
    resolve_with_declared_segment,
)
from services.industry_taxonomy_review import normalize_cnpj  # noqa: E402


DEFAULT_PERIODS = ("2023-12", "2024-12", "2025-12", "2026-06")
CONCLUSIONS_FILENAME = "industry_outros_reclassification_conclusions.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument("--periods", default=",".join(DEFAULT_PERIODS))
    return parser.parse_args()


def load_declared_segments(data_dir: Path, periods: tuple[str, ...]) -> pd.DataFrame:
    frame = pd.read_csv(
        data_dir / "vehicle_monthly.csv.gz",
        dtype=str,
        keep_default_na=False,
        usecols=[
            "competencia",
            "cnpj",
            "segmento_principal",
            "segmento_principal_valor",
            "segmento_reportado_total",
        ],
    )
    frame["cnpj_fundo"] = frame["cnpj"].map(normalize_cnpj)
    frame = frame[frame["competencia"].isin(periods)].copy()
    for column in ("segmento_principal_valor", "segmento_reportado_total"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    frame["share"] = 0.0
    reported = frame["segmento_reportado_total"] > 0
    frame.loc[reported, "share"] = (
        frame.loc[reported, "segmento_principal_valor"]
        / frame.loc[reported, "segmento_reportado_total"]
    )
    frame = frame[frame["segmento_principal"].str.strip().ne("")]
    return (
        frame.sort_values(["cnpj_fundo", "competencia"])
        .drop_duplicates("cnpj_fundo", keep="last")
        .set_index("cnpj_fundo")[["competencia", "segmento_principal", "share"]]
    )


def main() -> None:
    args = parse_args()
    periods = tuple(part.strip() for part in args.periods.split(",") if part.strip())
    path = args.data_dir / CONCLUSIONS_FILENAME
    conclusions = pd.read_csv(path, dtype=str, keep_default_na=False)
    conclusions["cnpj_fundo"] = conclusions["cnpj_fundo"].map(normalize_cnpj)
    segments = load_declared_segments(args.data_dir, periods)

    resolved = 0
    by_reason: dict[str, int] = {}
    for index, row in conclusions.iterrows():
        cnpj = str(row["cnpj_fundo"])
        if cnpj not in segments.index:
            continue
        declared = segments.loc[cnpj]
        outcome = resolve_with_declared_segment(
            decision_status=str(row["decision_status"]),
            family_scores=row.get("family_scores"),
            declared_segment=declared["segmento_principal"],
            declared_share=float(declared["share"]),
            competence=str(declared["competencia"]),
        )
        if not outcome.resolved:
            continue
        citation = (
            f"Informe Mensal Estruturado {declared['competencia']}: segmento "
            f"{declared['segmento_principal']} = {float(declared['share']):.0%} da "
            "carteira de direitos creditórios reportada à CVM."
        )
        conclusions.at[index, "tipo_anbima_sugerido"] = outcome.tipo
        conclusions.at[index, "foco_anbima_sugerido"] = outcome.foco
        conclusions.at[index, "tabela_ii_sugerida_documental"] = outcome.tabela_ii
        conclusions.at[index, "taxonomia_funcional_n1_sugerida"] = outcome.n1
        conclusions.at[index, "taxonomia_funcional_n2_sugerida"] = outcome.n2
        conclusions.at[index, "decision_status"] = "aprovado"
        conclusions.at[index, "confianca_documental"] = outcome.confidence
        conclusions.at[index, "justificativa_curta"] = outcome.rationale
        conclusions.at[index, "manual_validation_reason"] = ""
        conclusions.at[index, "evidence_summary"] = (
            f"{citation} {str(row.get('evidence_summary') or '')}".strip()[:4600]
        )
        conclusions.at[index, "reading_method"] = (
            str(row.get("reading_method") or "")
            + "; informe_mensal_estruturado_tabela_ii"
        ).strip("; ")
        conclusions.at[index, "source_limitations"] = (
            "O segmento da Tabela II fixa o setor econômico do lastro, mas não "
            "individualiza o produto de crédito dentro do setor."
        )
        resolved += 1
        by_reason[outcome.reason] = by_reason.get(outcome.reason, 0) + 1

    conclusions.to_csv(path, index=False)
    print(f"{resolved} conclusões fechadas pelo segmento declarado")
    for reason, count in sorted(by_reason.items()):
        print(f"  {reason}: {count}")
    print(conclusions["decision_status"].value_counts().to_dict())


if __name__ == "__main__":
    main()
