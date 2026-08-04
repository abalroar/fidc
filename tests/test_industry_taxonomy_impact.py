from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from services.industry_taxonomy_impact import (
    FLOWS_FILENAME,
    ISSUANCE_FILENAME,
    MARKET_SHARE_FILENAME,
    SUMMARY_FILENAME,
    TaxonomyImpactReport,
    build_gross_source_impact,
    build_incremental_current_impact,
    build_issuance_impact,
    build_market_share_denominator_impact,
    materialize_taxonomy_impact,
)
from services.industry_taxonomy_review import TAXONOMY_REVIEW_COLUMNS


def _cnpj(index: int) -> str:
    return str(90_000_000_000_000 + index)


def _closed_decisions() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index in range(19):
        rows.append(
            {
                "cnpj_fundo": _cnpj(index),
                "denominacao_referencia": f"Migração {index}",
                "pl_brl": 10.0 if index == 0 else 0.0,
                "tipo_atual": "Outros",
                "foco_atual": "Multicarteira Outros",
                "tipo_proposto": "Financeiro",
                "foco_proposto": "Multicarteira Financeiro",
                "efeito": "Migra de Tipo",
            }
        )
    for index in range(19, 37):
        rows.append(
            {
                "cnpj_fundo": _cnpj(index),
                "denominacao_referencia": f"Foco {index}",
                "pl_brl": 5.0 if index == 19 else 0.0,
                "tipo_atual": "Financeiro",
                "foco_atual": "Crédito Pessoal",
                "tipo_proposto": "Financeiro",
                "foco_proposto": "Crédito Consignado",
                "efeito": "Só Foco",
            }
        )
    return pd.DataFrame(rows)


def _source_mix() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"anbima_tipo": "Fomento Mercantil", "pl_brl": 100.0, "funds": 1},
            {
                "anbima_tipo": "Agro, Indústria e Comércio",
                "pl_brl": 200.0,
                "funds": 1,
            },
            {"anbima_tipo": "Financeiro", "pl_brl": 300.0, "funds": 1},
            {"anbima_tipo": "Outros", "pl_brl": 400.0, "funds": 1},
            {"anbima_tipo": "N/D", "pl_brl": 20.0, "funds": 1},
        ]
    )


def _action(cnpj: str) -> pd.DataFrame:
    row = {column: "" for column in TAXONOMY_REVIEW_COLUMNS}
    row.update(
        {
            "review_id": cnpj,
            "competencia_referencia": "2026-06",
            "cnpj_fundo": cnpj,
            "denominacao_referencia": "Fundo Agro",
            "status": "aprovado",
            "tipo_analitico": "Financeiro",
            "foco_analitico": "Adquirência",
            "tabela_ii_analitica": "N/D",
            "taxonomia_funcional_n1": "Meios de Pagamento e Cartões",
            "taxonomia_funcional_n2": "Arranjos de pagamento/adquirência",
            "confianca": "alta",
            "documento_id": "doc-1",
            "fonte_documental": "teste",
            "competencia_inicio": "2026-06",
            "updated_at_utc": "2026-08-04T00:00:00+00:00",
        }
    )
    return pd.DataFrame([row], columns=list(TAXONOMY_REVIEW_COLUMNS))


def _fund_base() -> pd.DataFrame:
    specifications = (
        ("Fomento Mercantil", "Fomento Mercantil", 100.0),
        ("Agro, Indústria e Comércio", "Recebíveis Comerciais", 200.0),
        ("Financeiro", "Crédito Pessoal", 300.0),
        ("Outros", "Multicarteira Outros", 400.0),
    )
    rows = []
    for index, (anbima_type, focus, pl) in enumerate(specifications, start=1):
        rows.append(
            {
                "competencia": "2026-06",
                "cnpj_fundo": _cnpj(index),
                "denominacao": f"Fundo {index}",
                "pl": pl,
                "is_fic": False,
                "is_fic_fidc": False,
                "anbima_tipo": anbima_type,
                "anbima_foco": focus,
                "anbima_tipo_oficial": anbima_type,
                "anbima_foco_oficial": focus,
                "admin_nome": "Administrador A",
                "admin_cnpj": _cnpj(100),
                "gestor_nome": "Gestor A",
                "gestor_cnpj": _cnpj(101),
                "custodiante_nome": "Custodiante A",
                "custodiante_cnpj": _cnpj(102),
            }
        )
    return pd.DataFrame(rows)


def _market_side(agro: float, financeiro: float) -> pd.DataFrame:
    rows = []
    for role in ("administrador", "gestor", "custodiante"):
        for anbima_type, focus, denominator, funds in (
            ("Agro, Indústria e Comércio", "Recebíveis Comerciais", agro, 2),
            ("Financeiro", "Adquirência", financeiro, 1),
        ):
            for participant in ("Top", "Outros identificados"):
                rows.append(
                    {
                        "papel": role,
                        "tipo_anbima": anbima_type,
                        "foco_anbima": focus,
                        "denominador_pl_subtipo_brl": denominator,
                        "denominador_publicacao_pl_positivo_brl": denominator,
                        "fundos_subtipo": funds,
                        "participante_bucket": participant,
                    }
                )
    return pd.DataFrame(rows)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_gross_source_impact_reconciles_19_type_and_18_focus_decisions() -> None:
    summary, flows = build_gross_source_impact(
        _closed_decisions(), _source_mix(), source_label="fonte"
    )
    decision_summary = summary[summary["view"].eq("source_decision_summary")]
    assert decision_summary.set_index("category")["decision_count"].to_dict() == {
        "Migra de Tipo": 19,
        "Só Foco": 18,
    }
    stock = summary[summary["view"].eq("source_gross_stock_type")].set_index(
        "category"
    )
    assert stock.at["Financeiro", "delta_brl"] == 10.0
    assert stock.at["Outros", "delta_brl"] == -10.0
    assert stock["delta_brl"].sum() == 0.0
    assert stock["denominator_brl"].nunique() == 1
    assert stock["denominator_brl"].iloc[0] == 1_020.0
    assert flows.groupby("effect")["decision_count"].sum().to_dict() == {
        "Migra de Tipo": 19,
        "Só Foco": 18,
    }


def test_incremental_current_impact_holds_universe_fixed_and_changes_one_fund() -> None:
    fund_base = _fund_base()
    current_actions = _action(_cnpj(2))
    summary, flows, market = build_incremental_current_impact(
        fund_base,
        pd.DataFrame(columns=list(TAXONOMY_REVIEW_COLUMNS)),
        current_actions,
        baseline_label="origin/main",
        current_label="current",
    )
    stock = summary.set_index("category")
    assert stock.at["Agro, Indústria e Comércio", "delta_brl"] == -200.0
    assert stock.at["Financeiro", "delta_brl"] == 200.0
    assert stock["before_brl"].sum() == stock["after_brl"].sum() == 1_000.0
    assert flows["decision_count"].sum() == 1
    assert flows.iloc[0]["effect"] == "Migra de Tipo"
    changed = market[market["delta_denominator_brl"].ne(0)].set_index(
        ["tipo_anbima", "foco_anbima"]
    )
    assert changed.at[
        ("Agro, Indústria e Comércio", "Recebíveis Comerciais"),
        "delta_denominator_brl",
    ] == -200.0
    assert changed.at[("Financeiro", "Adquirência"), "delta_denominator_brl"] == 200.0


def test_market_share_denominators_require_and_reconcile_three_roles() -> None:
    impact = build_market_share_denominator_impact(
        _market_side(200.0, 100.0),
        _market_side(150.0, 150.0),
        baseline_label="before",
        current_label="after",
    )
    assert impact["roles_reconciled"].eq(3).all()
    assert impact["scope_total_before_brl"].eq(300.0).all()
    assert impact["scope_total_after_brl"].eq(300.0).all()
    assert impact["delta_denominator_brl"].sum() == 0.0


def test_issuance_impact_preserves_every_period_total() -> None:
    baseline = pd.DataFrame(
        [
            {
                "period_key": "jun26",
                "period_label": "jan–jun/26",
                "categoria": "Fomento Mercantil",
                "volume_brl": 40.0,
                "share": 0.4,
            },
            {
                "period_key": "jun26",
                "period_label": "jan–jun/26",
                "categoria": "Financeiro",
                "volume_brl": 60.0,
                "share": 0.6,
            },
        ]
    )
    current = baseline.copy()
    current.loc[current["categoria"].eq("Fomento Mercantil"), ["volume_brl", "share"]] = [
        30.0,
        0.3,
    ]
    current.loc[current["categoria"].eq("Financeiro"), ["volume_brl", "share"]] = [
        70.0,
        0.7,
    ]
    impact = build_issuance_impact(
        baseline,
        current,
        baseline_label="before",
        current_label="after",
    )
    assert impact["delta_brl"].sum() == 0.0
    assert impact["period_total_before_brl"].eq(100.0).all()
    assert impact["period_total_after_brl"].eq(100.0).all()
    assert impact.set_index("categoria").at[
        "Financeiro", "delta_pp"
    ] == pytest.approx(10.0)


def test_materialized_csvs_are_byte_deterministic(tmp_path: Path) -> None:
    report = TaxonomyImpactReport(
        summary=pd.DataFrame([{"view": "summary", "value": 1.25}]),
        flows=pd.DataFrame([{"view": "flow", "value": -2.5}]),
        issuance=pd.DataFrame([{"period": "2026", "value": 3.75}]),
        market_share_denominators=pd.DataFrame(
            [{"tipo": "Financeiro", "value": 4.0}]
        ),
    )
    first = materialize_taxonomy_impact(report, tmp_path)
    hashes_before = {key: _sha(path) for key, path in first.items()}
    second = materialize_taxonomy_impact(report, tmp_path)
    hashes_after = {key: _sha(path) for key, path in second.items()}
    assert hashes_before == hashes_after
    assert {path.name for path in second.values()} == {
        SUMMARY_FILENAME,
        FLOWS_FILENAME,
        ISSUANCE_FILENAME,
        MARKET_SHARE_FILENAME,
    }
