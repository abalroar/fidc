#!/usr/bin/env python3
"""Publish definitive documentary taxonomy decisions once per FIDC CNPJ."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_taxonomy_review import (
    TAXONOMY_REVIEW_COLUMNS,
    commit_taxonomy_review_action,
    normalize_cnpj,
    taxonomy_review_id,
)


DEFAULT_SAVED_AT = "2026-07-29T20:21:37+00:00"
MANUAL_OVERRIDE_FILENAME = "taxonomy_user_comment_overrides.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument("--saved-at-utc", default=DEFAULT_SAVED_AT)
    return parser.parse_args()


def build_action(row: pd.Series, *, saved_at_utc: str) -> dict[str, object]:
    cnpj = normalize_cnpj(row["cnpj_fundo"])
    notes = " ".join(
        part.strip()
        for part in (
            str(row.get("manual_validation_reason") or ""),
            str(row.get("source_limitations") or ""),
        )
        if part.strip()
    )
    document_date = str(row.get("document_reference_date") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", document_date):
        document_date = ""
    action = {
        "review_id": taxonomy_review_id(cnpj),
        "competencia_referencia": "2026-06",
        "cnpj_fundo": cnpj,
        "denominacao_referencia": str(row.get("nome_fidc") or "").strip(),
        "status": "aprovado",
        "tipo_analitico": str(row.get("tipo_anbima_sugerido") or "").strip(),
        "foco_analitico": str(row.get("foco_anbima_sugerido") or "").strip(),
        "tabela_ii_analitica": str(
            row.get("tabela_ii_sugerida_documental") or "N/D"
        ).strip(),
        "taxonomia_funcional_n1": str(
            row.get("taxonomia_funcional_n1_sugerida") or ""
        ).strip(),
        "taxonomia_funcional_n2": str(
            row.get("taxonomia_funcional_n2_sugerida") or ""
        ).strip(),
        "confianca": str(row.get("confianca_documental") or "").strip(),
        "documento_id": str(row.get("document_id") or "").strip(),
        "fonte_documental": str(row.get("document_url") or "").strip(),
        "documento_data": document_date,
        "pagina_clausula": str(row.get("pagina_clausula") or "").strip(),
        "evidencia": str(row.get("evidence_summary") or "").strip(),
        "cedente_originador_expresso": str(
            row.get("cedent_originator_explicit") or ""
        ).strip(),
        "notas": notes,
        "responsavel": "curadoria_documental_consolidada",
        "competencia_inicio": "",
        "updated_at_utc": saved_at_utc,
    }
    return {column: action.get(column, "") for column in TAXONOMY_REVIEW_COLUMNS}


def build_manual_override_action(
    row: pd.Series, *, saved_at_utc: str
) -> dict[str, object]:
    """Build an approved CNPJ-level action from an explicit user decision."""
    cnpj = normalize_cnpj(row["cnpj_fundo"])
    rationale = str(row.get("justificativa_curta") or "").strip()
    limitation = str(row.get("limitacao_documental") or "").strip()
    notes = " ".join(part for part in (rationale, limitation) if part)
    action = {
        "review_id": taxonomy_review_id(cnpj),
        "competencia_referencia": "2026-06",
        "cnpj_fundo": cnpj,
        "denominacao_referencia": str(
            row.get("denominacao_referencia") or ""
        ).strip(),
        "status": "aprovado",
        "tipo_analitico": str(row.get("tipo_analitico") or "").strip(),
        "foco_analitico": str(row.get("foco_analitico") or "").strip(),
        "tabela_ii_analitica": str(
            row.get("tabela_ii_analitica") or "N/D"
        ).strip(),
        "taxonomia_funcional_n1": str(
            row.get("taxonomia_funcional_n1") or ""
        ).strip(),
        "taxonomia_funcional_n2": str(
            row.get("taxonomia_funcional_n2") or ""
        ).strip(),
        "confianca": str(row.get("confianca") or "media").strip(),
        "documento_id": "IMG_8592",
        "fonte_documental": "Comentário manual do usuário — IMG_8592.jpg",
        "documento_data": "2026-07-29",
        "pagina_clausula": "Linha do FIDC na imagem",
        "evidencia": str(row.get("comentario_usuario") or "").strip(),
        "cedente_originador_expresso": str(
            row.get("cedente_originador_expresso") or ""
        ).strip(),
        "notas": notes,
        "responsavel": "usuario_curadoria_manual",
        "competencia_inicio": "",
        "updated_at_utc": saved_at_utc,
    }
    return {column: action.get(column, "") for column in TAXONOMY_REVIEW_COLUMNS}


def load_manual_override_actions(
    path: Path, *, saved_at_utc: str
) -> list[dict[str, object]]:
    if not path.exists():
        return []
    overrides = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {
        "cnpj_fundo",
        "denominacao_referencia",
        "comentario_usuario",
        "tipo_analitico",
        "foco_analitico",
        "tabela_ii_analitica",
        "taxonomia_funcional_n1",
        "taxonomia_funcional_n2",
    }
    missing = sorted(required.difference(overrides.columns))
    if missing:
        raise ValueError(
            "campos ausentes nas decisões manuais: " + ", ".join(missing)
        )
    overrides["cnpj_fundo"] = overrides["cnpj_fundo"].map(normalize_cnpj)
    if overrides["cnpj_fundo"].duplicated().any():
        raise ValueError("decisões manuais devem conter um registro por CNPJ")
    return [
        build_manual_override_action(pd.Series(row), saved_at_utc=saved_at_utc)
        for row in overrides.sort_values("cnpj_fundo").to_dict(orient="records")
    ]


def main() -> None:
    args = parse_args()
    source_path = args.data_dir / "industry_top20_taxonomy_document_conclusions.csv"
    ledger_path = args.data_dir / "taxonomy_review_actions.csv"
    audit_path = args.data_dir / "taxonomy_review_audit.csv"
    manual_override_path = args.data_dir / MANUAL_OVERRIDE_FILENAME
    conclusions = pd.read_csv(source_path, dtype=str, keep_default_na=False)
    conclusions["cnpj_fundo"] = conclusions["cnpj_fundo"].map(normalize_cnpj)
    definitive = conclusions[
        conclusions["reclassification_status"].isin(
            {
                "manter_classificacao_oficial",
                "propor_reclassificacao_documental",
            }
        )
    ].copy()
    if definitive["cnpj_fundo"].duplicated().any():
        raise ValueError("conclusões definitivas devem conter um registro por CNPJ")
    for row in definitive.sort_values("cnpj_fundo").to_dict(orient="records"):
        commit_taxonomy_review_action(
            build_action(pd.Series(row), saved_at_utc=args.saved_at_utc),
            ledger_path,
            audit_path,
            saved_at_utc=args.saved_at_utc,
            source="consolidated_documentary_taxonomy_2026_07_29",
        )
    manual_actions = load_manual_override_actions(
        manual_override_path, saved_at_utc=args.saved_at_utc
    )
    for action in manual_actions:
        commit_taxonomy_review_action(
            action,
            ledger_path,
            audit_path,
            saved_at_utc=args.saved_at_utc,
            source="user_comment_IMG_8592_2026_07_29",
        )
    print(
        f"{len(definitive)} decisões documentais e "
        f"{len(manual_actions)} decisões manuais consolidadas por CNPJ"
    )


if __name__ == "__main__":
    main()
