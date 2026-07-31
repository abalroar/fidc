#!/usr/bin/env python3
"""Materialize the FIC audit with the provenance of each perimeter decision.

The audit separates the legacy nominal signal, quantitative confirmations from
the structured monthly report, and cases raised only by the stricter secondary
nominal cross-check.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.fic_detection import (  # noqa: E402
    METHOD_NAME,
    annotate_fic_detection,
    build_fic_audit,
    exclude_fics_from_fidc_universe,
    name_says_fic,
)
from services.fic_perimeter import load_fic_perimeter_overrides  # noqa: E402


AUDIT_FILENAME = "industry_fic_detection_audit.csv"
BASE_RELATIVE = Path("generated_revision") / "base_fundo_cnpj.csv.gz"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = args.data_dir
    base = pd.read_csv(
        data_dir / BASE_RELATIVE,
        dtype=str,
        keep_default_na=False,
        usecols=["competencia", "cnpj_fundo", "denominacao", "is_fic_fidc", "pl"],
    )
    base["pl"] = pd.to_numeric(base["pl"], errors="coerce").fillna(0.0)

    overrides = load_fic_perimeter_overrides(data_dir)
    annotated = annotate_fic_detection(
        base,
        curated_cnpjs=overrides["cnpj_fundo"].tolist(),
        curated_evidence=dict(zip(overrides["cnpj_fundo"], overrides["evidencia"])),
    )

    audit = build_fic_audit(annotated)
    audit_path = data_dir / AUDIT_FILENAME
    audit.to_csv(audit_path, index=False)

    _kept, report = exclude_fics_from_fidc_universe(annotated)

    by_cnpj = annotated.drop_duplicates("cnpj_fundo")
    excluded = by_cnpj[by_cnpj["is_fic"]]
    name_says = by_cnpj["denominacao"].map(lambda text: bool(name_says_fic(text)))
    nominal_review = by_cnpj[by_cnpj["fic_detection_method"].eq(METHOD_NAME)]
    silent_names = excluded[~excluded["cnpj_fundo"].isin(set(by_cnpj[name_says]["cnpj_fundo"]))]

    print(f"auditoria gravada em {audit_path} ({len(audit)} linhas)")
    print(f"CNPJs excluídos como FIC: {excluded['cnpj_fundo'].nunique()}")
    print(
        "PL excluído na competência mais recente "
        f"({report.last_competence}): R$ {report.pl_excluded_last_competence_brl / 1e9:.2f} bi"
    )
    print(f"linhas-mês removidas: {report.rows_excluded} de {report.rows_in}")

    print("\nmétodo de detecção (por CNPJ):")
    print(excluded["fic_detection_method"].value_counts().to_string())

    print(
        "\ncandidatos levantados apenas pelo cross-check nominal secundário: "
        f"{len(nominal_review)}"
    )
    if len(nominal_review):
        top = nominal_review.nlargest(min(15, len(nominal_review)), "pl")
        for _, row in top.iterrows():
            print(f"  R$ {row['pl'] / 1e9:6.2f} bi  {row['denominacao'][:72]}")

    print(
        f"\nexcluídos sem correspondência no cross-check nominal secundário: "
        f"{len(silent_names)} "
        f"({len(silent_names) / max(len(excluded), 1) * 100:.0f}% dos excluídos) — "
        "proveniência quantitativa registrada separadamente"
    )

    print("\nPL excluído por competência de referência:")
    for competence in ("2023-12", "2024-12", "2025-12", "2026-06"):
        window = annotated[annotated["competencia"].eq(competence)]
        gone = window[window["is_fic"]]
        if window.empty:
            continue
        print(
            f"  {competence}: {len(gone):>3} fundos, R$ {gone['pl'].sum() / 1e9:7.2f} bi "
            f"de R$ {window['pl'].sum() / 1e9:7.2f} bi "
            f"({gone['pl'].sum() / max(window['pl'].sum(), 1) * 100:4.1f}%)"
        )


if __name__ == "__main__":
    main()
