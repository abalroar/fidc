#!/usr/bin/env python3
"""Record the FIC perimeter correction as a decision in the analytical ledger.

A vehicle that only holds quotas of other FIDCs has no receivables family of its
own to classify: its assets are already counted, with their own taxonomy, inside
the funds it invests in.  The honest decision is therefore ``rejeitado`` — the
hypothesis of classifying it as a direct FIDC is incorrect — with the perimeter
correction recorded as the reason.

The taxonomy overlay only applies approved decisions, so this both removes any
previous classification from the analytical mix and leaves an auditable trail of
why the vehicle left it.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.fic_perimeter import load_fic_perimeter_overrides  # noqa: E402
from services.industry_taxonomy_review import (  # noqa: E402
    TAXONOMY_REVIEW_COLUMNS,
    commit_taxonomy_review_actions,
    load_taxonomy_review_actions,
    normalize_cnpj,
    taxonomy_review_id,
    validate_taxonomy_review_action,
)


RESPONSIBLE = "curadoria_perimetro_fic"
REVIEW_FILENAME = "industry_fic_perimeter_review.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument("--competencia", default="2026-06")
    parser.add_argument("--saved-at-utc", default="")
    parser.add_argument("--audit-source", default="fic_perimeter_correction")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    saved_at_utc = args.saved_at_utc or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()
    data_dir = args.data_dir
    overrides = load_fic_perimeter_overrides(data_dir)
    if overrides.empty:
        print("nenhuma correção de perímetro registrada")
        return

    review_path = data_dir / REVIEW_FILENAME
    evidence_by_cnpj: dict[str, str] = {}
    if review_path.exists():
        review = pd.read_csv(review_path, dtype=str, keep_default_na=False)
        review["cnpj_fundo"] = review["cnpj_fundo"].map(normalize_cnpj)
        evidence_by_cnpj = dict(zip(review["cnpj_fundo"], review["evidencia"]))

    ledger = load_taxonomy_review_actions(data_dir / "taxonomy_review_actions.csv")
    previous_status = {}
    previous_owner = {}
    if not ledger.empty:
        ledger = ledger.copy()
        ledger["cnpj_fundo"] = ledger["cnpj_fundo"].map(normalize_cnpj)
        previous_status = dict(zip(ledger["cnpj_fundo"], ledger["status"]))
        previous_owner = dict(zip(ledger["cnpj_fundo"], ledger["responsavel"]))

    actions: list[dict[str, object]] = []
    overrode_manual: list[str] = []
    for record in overrides.to_dict(orient="records"):
        cnpj = normalize_cnpj(record["cnpj_fundo"])
        owner = str(previous_owner.get(cnpj, ""))
        if previous_status.get(cnpj) == "aprovado" and "usuario" in owner:
            overrode_manual.append(f"{cnpj} {record['denominacao']}")
        action = {
            "review_id": taxonomy_review_id(cnpj),
            "competencia_referencia": args.competencia,
            "cnpj_fundo": cnpj,
            "denominacao_referencia": str(record.get("denominacao") or ""),
            "status": "rejeitado",
            "tipo_analitico": "",
            "foco_analitico": "",
            "tabela_ii_analitica": "",
            "taxonomia_funcional_n1": "",
            "taxonomia_funcional_n2": "",
            "confianca": "alta",
            "documento_id": "",
            "fonte_documental": str(record.get("fonte") or ""),
            "documento_data": "",
            "pagina_clausula": "Informe Mensal Estruturado, bloco APLIC_ATIVO",
            "evidencia": evidence_by_cnpj.get(cnpj, str(record.get("evidencia") or ""))[:6000],
            "cedente_originador_expresso": "",
            "notas": (
                "Correção de perímetro: o veículo não adquire direitos creditórios, "
                "detém cotas de outros FIDCs. O patrimônio passa a alimentar o saldo "
                "de FIC-FIDC e sai dos quatro tipos ANBIMA, evitando dupla contagem "
                "do mesmo patrimônio já classificado nos fundos investidos."
            ),
            "responsavel": RESPONSIBLE,
            "competencia_inicio": "",
            "updated_at_utc": saved_at_utc,
        }
        action = {column: action.get(column, "") for column in TAXONOMY_REVIEW_COLUMNS}
        validate_taxonomy_review_action(action)
        actions.append(action)

    commit_taxonomy_review_actions(
        pd.DataFrame(actions, columns=list(TAXONOMY_REVIEW_COLUMNS)),
        data_dir / "taxonomy_review_actions.csv",
        data_dir / "taxonomy_review_audit.csv",
        saved_at_utc=saved_at_utc,
        source=args.audit_source,
    )
    updated = load_taxonomy_review_actions(data_dir / "taxonomy_review_actions.csv")
    print(f"{len(actions)} correções de perímetro gravadas no ledger")
    print("ledger: " + ", ".join(
        f"{status}={count}" for status, count in updated["status"].value_counts().items()
    ))
    if overrode_manual:
        print(
            f"\nATENÇÃO: {len(overrode_manual)} decisões manuais do usuário foram "
            "substituídas pela correção de perímetro:"
        )
        for entry in overrode_manual:
            print(f"  {entry}")


if __name__ == "__main__":
    main()
