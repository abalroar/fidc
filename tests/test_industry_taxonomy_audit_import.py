from pathlib import Path

import pandas as pd
import pytest

import services.industry_taxonomy_audit_import as audit_import
from services.industry_taxonomy_audit_import import (
    AETOS_CNPJ,
    ACQUIRING_SHEET,
    DECISIONS_SHEET,
    EXPECTED_ACQUIRING_ROWS,
    EXPECTED_F8_PL_BRL,
    EXPECTED_F8_ROWS,
    EXPECTED_FOCUS_ONLY_PL_BRL,
    EXPECTED_OUTROS_ROWS,
    EXPECTED_TOP200_ROWS,
    EXPECTED_TYPE_MIGRATION_PL_BRL,
    OUTROS_SHEET,
    SELLER3_CNPJ,
    SUMMARY_SHEET,
    TOP200_SHEET,
    TaxonomyAuditImportError,
    import_taxonomy_audit,
    prepare_audited_actions,
)
from services.industry_taxonomy_review import TAXONOMY_REVIEW_COLUMNS
from services.industry_taxonomy_review import valid_analytical_type_focus_pair


def _generated_cnpj(index: int) -> str:
    return str(90_000_000_000_000 + index)


def _source_contract_frames() -> dict[str, pd.DataFrame]:
    migration_cnpjs = [SELLER3_CNPJ] + [_generated_cnpj(i) for i in range(1, 19)]
    focus_cnpjs = [AETOS_CNPJ] + [_generated_cnpj(i) for i in range(19, 36)]
    decisions: list[dict[str, object]] = []
    for index, cnpj in enumerate(migration_cnpjs):
        decisions.append(
            {
                "CNPJ": cnpj,
                "FIDC": f"Migra {index}",
                "PL (R$)": EXPECTED_TYPE_MIGRATION_PL_BRL if index == 0 else 0.0,
                "Tipo atual": "Agro, Indústria e Comércio",
                "Foco atual": "Recebíveis Comerciais",
                "Tipo proposto": "Financeiro",
                "Foco proposto": "Adquirência" if index == 0 else "Multicarteira Financeiro",
                "Efeito": "Migra de Tipo",
            }
        )
    for index, cnpj in enumerate(focus_cnpjs):
        is_aetos = cnpj == AETOS_CNPJ
        decisions.append(
            {
                "CNPJ": cnpj,
                "FIDC": f"Foco {index}",
                "PL (R$)": EXPECTED_FOCUS_ONLY_PL_BRL if index == 0 else 0.0,
                "Tipo atual": (
                    "Agro, Indústria e Comércio" if is_aetos else "Financeiro"
                ),
                "Foco atual": (
                    "Recebíveis Comerciais" if is_aetos else "Crédito Pessoal"
                ),
                "Tipo proposto": (
                    "Agro, Indústria e Comércio" if is_aetos else "Financeiro"
                ),
                "Foco proposto": (
                    "Infraestrutura" if is_aetos else "Multicarteira Financeiro"
                ),
                "Efeito": "Só Foco",
            }
        )

    top200_rows: list[dict[str, object]] = []
    for decision in decisions:
        cnpj = str(decision["CNPJ"])
        recommendation = "Aplicar o de-para auditado."
        verdict = "Reclassificar" if decision["Efeito"] == "Migra de Tipo" else "Revisar Foco"
        if cnpj == SELLER3_CNPJ:
            recommendation = (
                'Manter o Tipo "Financeiro" e revisar o Foco de "Crédito Pessoal".'
            )
        if cnpj == AETOS_CNPJ:
            verdict = "Tabela II mal reportada"
        top200_rows.append(
            {
                "CNPJ": cnpj,
                "FIDC": decision["FIDC"],
                "PL (R$)": decision["PL (R$)"],
                "Tipo ANBIMA atual": decision["Tipo atual"],
                "Foco ANBIMA atual": decision["Foco atual"],
                "Confiabilidade da Tabela II": "Alta — subsegmento específico",
                "Veredito documental": verdict,
                "Evidência no regulamento": f"Evidência documental {cnpj}",
                "Documento FundosNET (id)": f"Regulamento id {100000 + len(top200_rows)}",
                "Recomendação": recommendation,
            }
        )

    filler_count = EXPECTED_TOP200_ROWS - len(top200_rows)
    for index in range(filler_count):
        is_f8 = index < EXPECTED_F8_ROWS
        is_outros = index < 75
        top200_rows.append(
            {
                "CNPJ": _generated_cnpj(1_000 + index),
                "FIDC": f"Filler {index}",
                "PL (R$)": EXPECTED_F8_PL_BRL if index == 0 else 0.0,
                "Tipo ANBIMA atual": "Outros" if is_outros else "Financeiro",
                "Foco ANBIMA atual": (
                    "Multicarteira Outros" if is_outros else "Multicarteira Financeiro"
                ),
                "Confiabilidade da Tabela II": (
                    'Baixa — dominância vem do campo residual F8 "Financeiro/Outro"'
                    if is_f8
                    else "Alta — subsegmento específico"
                ),
                "Veredito documental": "Ler documento" if index < 9 else "",
                "Evidência no regulamento": "",
                "Documento FundosNET (id)": "",
                "Recomendação": "",
            }
        )

    top200 = pd.DataFrame(top200_rows)
    current_outros = top200[top200["Tipo ANBIMA atual"].eq("Outros")]
    top200_total = float(pd.to_numeric(top200["PL (R$)"], errors="coerce").sum())
    outros_total = float(
        pd.to_numeric(current_outros["PL (R$)"], errors="coerce").sum()
    )
    summary = pd.DataFrame(
        [
            [None, "Balde Outros no Top 200", "75 fundos.", outros_total],
            [
                None,
                "Agro, Indústria e Comércio → Financeiro",
                "19 fundos.",
                EXPECTED_TYPE_MIGRATION_PL_BRL,
            ],
            [None, "Financeiro", None, EXPECTED_TYPE_MIGRATION_PL_BRL],
            [
                None,
                "Agro, Indústria e Comércio",
                None,
                -EXPECTED_TYPE_MIGRATION_PL_BRL,
            ],
            [
                None,
                "Campo residual F8",
                f"{EXPECTED_F8_ROWS} fundos do Top 200.",
                EXPECTED_F8_PL_BRL,
            ],
            [
                None,
                'Vereditos "Ler documento"',
                "9 fundos ficaram sem decisão.",
                None,
            ],
            [
                None,
                "Fundos auditados nas três camadas",
                f"{EXPECTED_TOP200_ROWS} maiores por PL de jun/26.",
                top200_total,
            ],
        ]
    )
    outros = pd.DataFrame(
        {"CNPJ": [_generated_cnpj(2_000 + i) for i in range(EXPECTED_OUTROS_ROWS)]}
    )
    acquiring = pd.DataFrame(
        {
            "CNPJ": [
                _generated_cnpj(3_000 + i) for i in range(EXPECTED_ACQUIRING_ROWS)
            ]
        }
    )
    return {
        DECISIONS_SHEET: pd.DataFrame(decisions),
        TOP200_SHEET: top200,
        OUTROS_SHEET: outros,
        ACQUIRING_SHEET: acquiring,
        SUMMARY_SHEET: summary,
    }


def _import_from_frames(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    frames: dict[str, pd.DataFrame],
):
    workbook = tmp_path / "auditoria.xlsx"
    workbook.touch()

    class _Excel:
        sheet_names = list(frames)

    monkeypatch.setattr(audit_import.pd, "ExcelFile", lambda _: _Excel())
    monkeypatch.setattr(
        audit_import,
        "_read_sheet",
        lambda _path, sheet, header=3: frames[sheet].copy(),
    )
    monkeypatch.setattr(audit_import, "_sha256", lambda _: "0" * 64)
    return import_taxonomy_audit(workbook)


def test_import_validates_closed_workbook_contract_and_manifest_issues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _import_from_frames(tmp_path, monkeypatch, _source_contract_frames())
    assert imported.manifest["sheets"][TOP200_SHEET] == EXPECTED_TOP200_ROWS
    assert imported.manifest["sheets"][OUTROS_SHEET] == EXPECTED_OUTROS_ROWS
    assert imported.manifest["sheets"][ACQUIRING_SHEET] == EXPECTED_ACQUIRING_ROWS
    assert imported.manifest["checks"]["decision_top200_join_count"] == 37
    assert imported.manifest["checks"]["summary_validated"] is True
    assert imported.manifest["checks"]["f8_count"] == EXPECTED_F8_ROWS
    assert imported.manifest["checks"]["f8_pl_brl"] == EXPECTED_F8_PL_BRL
    assert {issue["code"] for issue in imported.manifest["issues"]} == {
        "seller3_recommendation_text_inconsistent",
        "aetos_table_ii_misreport_focus_exception",
        "f8_exact_value_differs_from_rounded_brief",
    }
    assert imported.decisions.columns.tolist() == [
        "denominacao_referencia",
        "pl_brl",
        "tipo_atual",
        "foco_atual",
        "tipo_proposto",
        "foco_proposto",
        "efeito",
        "cnpj_fundo",
    ]


@pytest.mark.parametrize(
    ("sheet", "expected"),
    [
        (TOP200_SHEET, EXPECTED_TOP200_ROWS),
        (OUTROS_SHEET, EXPECTED_OUTROS_ROWS),
        (ACQUIRING_SHEET, EXPECTED_ACQUIRING_ROWS),
    ],
)
def test_import_fails_closed_on_sheet_cardinality(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sheet: str,
    expected: int,
) -> None:
    frames = _source_contract_frames()
    frames[sheet] = frames[sheet].iloc[:-1].copy()
    with pytest.raises(
        TaxonomyAuditImportError,
        match=rf"deveria conter {expected} CNPJs válidos",
    ):
        _import_from_frames(tmp_path, monkeypatch, frames)


def test_import_fails_closed_on_duplicate_cnpj(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = _source_contract_frames()
    frames[ACQUIRING_SHEET].loc[1, "CNPJ"] = frames[ACQUIRING_SHEET].loc[0, "CNPJ"]
    with pytest.raises(TaxonomyAuditImportError, match="CNPJ duplicado"):
        _import_from_frames(tmp_path, monkeypatch, frames)


@pytest.mark.parametrize(
    ("column", "replacement", "message"),
    [
        ("PL (R$)", -1.0, "PL do de-para diverge do Top200"),
        ("Tipo ANBIMA atual", "Outros", "Tipo atual.*diverge"),
        ("Foco ANBIMA atual", "Poder Público", "Foco atual.*diverge"),
    ],
)
def test_import_fails_closed_when_current_decision_fields_do_not_match_top200(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    column: str,
    replacement: object,
    message: str,
) -> None:
    frames = _source_contract_frames()
    frames[TOP200_SHEET].loc[0, column] = replacement
    with pytest.raises(TaxonomyAuditImportError, match=message):
        _import_from_frames(tmp_path, monkeypatch, frames)


def test_import_fails_closed_when_summary_f8_value_drifts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = _source_contract_frames()
    summary = frames[SUMMARY_SHEET]
    row = summary.index[summary[1].eq("Campo residual F8")][0]
    summary.loc[row, 3] = EXPECTED_F8_PL_BRL - 1.0
    with pytest.raises(TaxonomyAuditImportError, match="sumário diverge em Campo residual F8"):
        _import_from_frames(tmp_path, monkeypatch, frames)


class _Imported:
    decisions = pd.DataFrame(
        [
            {
                "cnpj_fundo": "50168890000113",
                "denominacao_referencia": "CEA PAY",
                "tipo_atual": "Agro, Indústria e Comércio",
                "foco_atual": "Recebíveis Comerciais",
                "tipo_proposto": "Financeiro",
                "foco_proposto": "Multicarteira Financeiro",
                "efeito": "Migra de Tipo",
                "pl_brl": 1.0,
            }
        ]
    )
    top200 = pd.DataFrame(
        [
            {
                "cnpj_fundo": "50168890000113",
                "Evidência no regulamento": "Titulares do Cartão C&A",
                "Documento FundosNET (id)": "Regulamento id 123456",
                "Recomendação": "Aplicar Financeiro/Multicarteira Financeiro.",
            }
        ]
    )


def test_missing_action_is_prepared_with_documentary_defaults(tmp_path: Path) -> None:
    ledger = tmp_path / "taxonomy_review_actions.csv"
    pd.DataFrame(columns=TAXONOMY_REVIEW_COLUMNS).to_csv(ledger, index=False)
    actions = prepare_audited_actions(
        _Imported(),
        ledger,
        updated_at_utc="2026-08-04T12:00:00+00:00",
    )
    row = actions.iloc[0]
    assert row["cnpj_fundo"] == "50168890000113"
    assert row["tipo_analitico"] == "Financeiro"
    assert row["foco_analitico"] == "Multicarteira Financeiro"
    assert row["tabela_ii_analitica"] == "Cartão de crédito"
    assert row["taxonomia_funcional_n2"] == "Banco emissor/cartão de crédito"
    assert row["evidencia"] == "Titulares do Cartão C&A"
    assert row["documento_id"] == "Regulamento id 123456"
    assert row["competencia_inicio"] == ""
    assert "aplicado retroativamente" in row["notas"]
    assert "recomendação" in row["notas"]


def test_existing_stronger_documentary_evidence_is_preserved(tmp_path: Path) -> None:
    ledger = tmp_path / "taxonomy_review_actions.csv"
    existing = {column: "" for column in TAXONOMY_REVIEW_COLUMNS}
    existing.update(
        {
            "review_id": "50168890000113",
            "competencia_referencia": "2026-05",
            "cnpj_fundo": "50168890000113",
            "denominacao_referencia": "CEA PAY",
            "status": "aprovado",
            "tipo_analitico": "Financeiro",
            "foco_analitico": "Multicarteira Financeiro",
            "tabela_ii_analitica": "Cartão de crédito",
            "taxonomia_funcional_n1": "Meios de Pagamento e Cartões",
            "taxonomia_funcional_n2": "Banco emissor/cartão de crédito",
            "confianca": "alta",
            "documento_id": "https://fnet.example/regulamento/999999",
            "fonte_documental": "https://fnet.example/regulamento/999999",
            "evidencia": "Cláusula primária lida integralmente, p. 42.",
            "updated_at_utc": "2026-08-01T12:00:00+00:00",
        }
    )
    pd.DataFrame([existing], columns=TAXONOMY_REVIEW_COLUMNS).to_csv(
        ledger, index=False
    )
    row = prepare_audited_actions(
        _Imported(),
        ledger,
        updated_at_utc="2026-08-04T12:00:00+00:00",
    ).iloc[0]
    assert row["documento_id"] == "https://fnet.example/regulamento/999999"
    assert row["fonte_documental"] == "https://fnet.example/regulamento/999999"
    assert row["evidencia"] == "Cláusula primária lida integralmente, p. 42."
    assert "Titulares do Cartão C&A" in row["notas"]
    assert "Regulamento id 123456" in row["notas"]


def test_pan_auto_audited_other_bucket_is_a_valid_analytical_focus() -> None:
    assert valid_analytical_type_focus_pair(
        "Outros",
        "Multicedente/Multissacado",
    )
