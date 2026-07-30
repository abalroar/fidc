#!/usr/bin/env python3
"""Commit documentary taxonomy decisions to the analytical ledger, by CNPJ.

The script reads any conclusions CSV produced by the documentary pipelines
(``industry_outros_reclassification_conclusions.csv`` or
``industry_top20_pending_curation.csv``) and writes one auditable action per
CNPJ through ``commit_taxonomy_review_action``.

Continuity rules
----------------
* an approved decision already in the ledger is never overwritten unless
  ``--allow-override`` is passed with an explicit ``--override-reason``;
* the audit trail records every field-level change;
* official ANBIMA and CVM columns are not touched.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_taxonomy_review import (  # noqa: E402
    TAXONOMY_REVIEW_COLUMNS,
    commit_taxonomy_review_actions,
    load_taxonomy_review_actions,
    normalize_cnpj,
    taxonomy_review_id,
    validate_taxonomy_review_action,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument("--responsavel", default="curadoria_documental_outros")
    parser.add_argument("--audit-source", default="documentary_outros_expansion")
    parser.add_argument(
        "--statuses",
        default="aprovado,em_revisao,rejeitado,pendente",
        help="decision_status values that should reach the ledger",
    )
    parser.add_argument("--allow-override", action="store_true")
    parser.add_argument("--override-reason", default="")
    parser.add_argument("--saved-at-utc", default="")
    return parser.parse_args()


def _text(value: object) -> str:
    """Normalize exactly like the ledger reader does.

    ``assert_taxonomy_review_ledger_matches_audit`` replays the audit through
    the module's own whitespace normalization, so a value stored with double
    spaces in the ledger would no longer be reproducible from its trail.
    """

    if value is None:
        return ""
    text = str(value)
    if text.lower() == "nan":
        return ""
    return re.sub(r"\s+", " ", text).strip()


def build_action(row: pd.Series, *, responsavel: str, saved_at_utc: str) -> dict[str, object]:
    cnpj = normalize_cnpj(row["cnpj_fundo"])
    document_date = _text(row.get("document_reference_date"))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", document_date):
        document_date = ""
    notes = " ".join(
        part
        for part in (
            _text(row.get("justificativa_curta")),
            _text(row.get("manual_validation_reason")),
            _text(row.get("perimeter_proposal")),
            _text(row.get("source_limitations")),
            f"Escores documentais: {_text(row.get('family_scores'))}."
            if _text(row.get("family_scores"))
            else "",
            f"Documentos lidos: {_text(row.get('documentos_lidos'))}."
            if _text(row.get("documentos_lidos"))
            else "",
        )
        if part
    )
    competence = _text(row.get("competencia_pl_max")) or "2026-06"
    action = {
        "review_id": taxonomy_review_id(cnpj),
        "competencia_referencia": competence,
        "cnpj_fundo": cnpj,
        "denominacao_referencia": _text(row.get("nome_fidc")),
        "status": _text(row.get("decision_status")) or "pendente",
        "tipo_analitico": _text(row.get("tipo_anbima_sugerido")),
        "foco_analitico": _text(row.get("foco_anbima_sugerido")),
        "tabela_ii_analitica": _text(row.get("tabela_ii_sugerida_documental")),
        "taxonomia_funcional_n1": _text(row.get("taxonomia_funcional_n1_sugerida")),
        "taxonomia_funcional_n2": _text(row.get("taxonomia_funcional_n2_sugerida")),
        "confianca": _text(row.get("confianca_documental")),
        "documento_id": _text(row.get("document_id")),
        "fonte_documental": _text(row.get("document_url")),
        "documento_data": document_date,
        "pagina_clausula": _text(row.get("pagina_clausula")),
        "evidencia": _text(row.get("evidence_summary"))[:6000],
        "cedente_originador_expresso": _text(row.get("cedent_originator_explicit")),
        "notas": notes[:6000],
        "responsavel": responsavel,
        "competencia_inicio": "",
        "updated_at_utc": saved_at_utc,
    }
    return {column: action.get(column, "") for column in TAXONOMY_REVIEW_COLUMNS}


def main() -> None:
    args = parse_args()
    saved_at_utc = args.saved_at_utc or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()
    if args.allow_override and not args.override_reason.strip():
        raise SystemExit("--allow-override exige --override-reason")

    ledger_path = args.data_dir / "taxonomy_review_actions.csv"
    audit_path = args.data_dir / "taxonomy_review_audit.csv"
    conclusions = pd.read_csv(args.source, dtype=str, keep_default_na=False)
    conclusions["cnpj_fundo"] = conclusions["cnpj_fundo"].map(normalize_cnpj)
    wanted = {part.strip() for part in args.statuses.split(",") if part.strip()}
    selected = conclusions[conclusions["decision_status"].isin(wanted)].copy()
    if selected["cnpj_fundo"].duplicated().any():
        raise SystemExit("as conclusões devem conter um registro por CNPJ")

    previous = load_taxonomy_review_actions(ledger_path)
    approved_before = set(
        previous.loc[previous["status"].eq("aprovado"), "cnpj_fundo"].map(normalize_cnpj)
    )
    #: A ``pendente`` conclusion carries no information: it must never erase a
    #: decision that some earlier reading already recorded for the same CNPJ.
    decided_before = set(
        previous.loc[previous["status"].ne("pendente"), "cnpj_fundo"].map(normalize_cnpj)
    )

    committed = 0
    preserved = 0
    staged: list[dict[str, object]] = []
    invalid: list[tuple[str, str]] = []
    for record in selected.sort_values("cnpj_fundo").to_dict(orient="records"):
        row = pd.Series(record)
        cnpj = str(row["cnpj_fundo"])
        if cnpj in approved_before and not args.allow_override:
            preserved += 1
            continue
        if str(row.get("decision_status")) == "pendente" and cnpj in decided_before:
            preserved += 1
            continue
        action = build_action(row, responsavel=args.responsavel, saved_at_utc=saved_at_utc)
        if cnpj in approved_before:
            action["notas"] = (
                f"Sobrescreve aprovação anterior. Motivo: {args.override_reason.strip()} "
                + str(action["notas"])
            )[:6000]
        try:
            validate_taxonomy_review_action(action)
        except ValueError as error:
            invalid.append((cnpj, str(error)))
            continue
        staged.append(action)

    if staged:
        commit_taxonomy_review_actions(
            pd.DataFrame(staged, columns=list(TAXONOMY_REVIEW_COLUMNS)),
            ledger_path,
            audit_path,
            saved_at_utc=saved_at_utc,
            source=args.audit_source,
        )
        committed = len(staged)

    updated = load_taxonomy_review_actions(ledger_path)
    print(
        f"{committed} decisões gravadas, {preserved} aprovações preservadas, "
        f"{len(invalid)} rejeitadas pela validação"
    )
    for cnpj, reason in invalid[:20]:
        print(f"  inválida {cnpj}: {reason}")
    print(
        "ledger: "
        + ", ".join(
            f"{status}={count}"
            for status, count in updated["status"].value_counts().items()
        )
    )


if __name__ == "__main__":
    main()
