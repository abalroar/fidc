from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from services.industry_flagship_curation import (
    PORTFOLIO_FLAGSHIP_GROUPS,
    PortfolioCurationResult,
    PortfolioFlagshipComparisonResult,
)
from services.industry_structural_risk import (
    MVP_SLIDE_CATEGORIES,
    _apply_financeiro_agro_risk_review,
    _load_financeiro_agro_risk_review,
    _load_mvp_slide_overrides,
    _validate_financeiro_agro_risk_review,
    build_portfolio_structural_risk,
)


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "scripts" / "build_fidc_revision_artifacts.mjs"


def _portfolio_with_isolated_junior() -> PortfolioCurationResult:
    detail = pd.DataFrame(
        [
            {
                "ordem": 1,
                "denominacao": "FIDC COM MINIMO JR ISOLADO",
                "cnpj_fundo": "00000000000001",
                "cnpj_fundo_formatado": "00.000.000/0000-01",
                "familia_flagship_referencia": "",
                "tipo_exibicao": "Financeiro",
                "foco_exibicao": "Credito pessoal",
                "subordinacao_atual_pct": 0.20,
                "subordinacao_minima_junior_pct": 5.0,
                "suporte_estrutural_minimo_pct": np.nan,
                "subordinacao_minima_natureza": "junior_pl",
                "subordinacao_minima_junior_display": "5,0% do PL",
                "suporte_estrutural_minimo_display": "N/D",
                "subordinacao_minima_texto": "cotas junior >= 5,0% do PL",
                "suporte_estrutural_minimo_texto": "N/D",
                "subordinacao_minima_formula": "junior / PL",
                "comparabilidade_tranche_flag": "false",
                "comparabilidade_tranche_motivo": (
                    "Sub/PL atual total nao e comparavel ao minimo junior isolado"
                ),
                "pl_atual_brl": 1_000_000_000.0,
                "subordinacao_minima_fonte": "regulamento",
                "documento_id_regulamento": "DOC-1",
                "pagina_clausula": "p. 10",
                "status_curadoria_documental": "revisto",
            }
        ]
    )
    return PortfolioCurationResult(
        detail=detail,
        ranges=pd.DataFrame(),
        summary={
            "competencia": "2026-06",
            "fonte": "fixture documental",
        },
    )


def _comparison_for_all_groups() -> PortfolioFlagshipComparisonResult:
    rows = []
    for _, group, _, _ in PORTFOLIO_FLAGSHIP_GROUPS:
        rows.append(
            {
                "tipo_comparacao": group,
                "flagship_cnpjs": 5,
                "flagship_cnpjs_com_subordinacao": 5,
                "flagship_pl_brl": 5_000_000_000.0,
                "flagship_subordinacao_mediana_pct": 0.18,
            }
        )
    return PortfolioFlagshipComparisonResult(
        detail=pd.DataFrame(rows),
        summary={},
    )


def test_isolated_junior_minimum_stays_eligible_but_has_neutral_status() -> None:
    result = build_portfolio_structural_risk(
        portfolio=_portfolio_with_isolated_junior(),
        comparison=_comparison_for_all_groups(),
    )
    row = result.assets.iloc[0]

    assert row["sub_jr_min_documental"] == 0.05
    assert pd.isna(row["suporte_total_min_documental"])
    assert row["minimo_estrutural_display"] == "N/D"
    assert not bool(row["comparacao_estrutural_completa_flag"])
    assert bool(row["mvp_elegivel_flag"])
    assert row["mvp_situacao_piso"] == "incomparável"
    assert result.summary["mvp_cnpjs_elegiveis"] == 1


def test_renderer_uses_dynamic_eligible_count_and_guards_cnpj_uniqueness() -> None:
    source = RENDERER.read_text(encoding="utf-8")
    function = source.split("function addStructuralMvpSlides", 1)[1].split(
        "function addFlagshipCurationSlide", 1
    )[0]

    assert re.search(r"eligible\.length\s*!==\s*\d+", function) is None
    assert "mvp_cnpjs_elegiveis" in function
    assert "mvp_slide_categoria" in function
    assert re.search(r"\.has\(cnpj\).*?throw new Error", function, re.DOTALL)
    assert "duplic" in function.lower()
    assert "shown.size !== eligible.length" in function


def test_renderer_does_not_promote_isolated_junior_to_structural_minimum() -> None:
    source = RENDERER.read_text(encoding="utf-8")
    minima = source.split("function structuralMvpMinima", 1)[1].split(
        "function structuralMvpCardStyle", 1
    )[0]

    for field in (
        "minimo_junior_literal",
        "minimo_junior_calculado",
        "minimo_junior_ajustado",
        "suporte_total",
        "suporte_combinado_junior_mezanino",
    ):
        assert field in minima
    assert "minimo_estrutural_usado" not in minima
    assert "Jr " in minima
    assert "Estr. " in minima


def test_structural_mvp_card_metric_whitelist_is_basic() -> None:
    source = RENDERER.read_text(encoding="utf-8")
    match = re.search(
        r"addText\(\s*slide,\s*(`\$\{structuralFundName\(row,.*?`),\s*\{\s*left,",
        source,
        re.DOTALL,
    )
    assert match is not None
    card = match.group(1)

    for expected in (
        "pl_atual_brl",
        "sub_pl_atual",
        "structuralMvpMinima(row)",
    ):
        assert expected in card
    for forbidden in (
        "folga",
        "capacidade",
        "perda_ate_gatilho",
        "percentil",
        "z_score",
        "excesso_vs_mercado",
        "preco",
        "quantidade",
    ):
        assert forbidden not in card.lower()


def test_financeiro_agro_review_contract_is_complete_and_fail_closed() -> None:
    review = _load_financeiro_agro_risk_review()

    assert len(review) == 72
    assert review["cnpj"].nunique() == 72
    assert review["categoria_atual"].value_counts().to_dict() == {
        "Agro / Revenda": 49,
        "Financeiro": 23,
    }
    assert review["subtipo_risco"].str.strip().ne("").all()
    assert review["status"].str.strip().ne("").all()
    assert review["evidencia"].str.strip().ne("").all()
    applied = review["applied_flag"].eq("SIM")
    assert int(applied.sum()) == 20
    assert review.loc[applied, "categoria_atual"].ne(
        review.loc[applied, "categoria_proposta"]
    ).all()
    assert review.loc[~applied, "categoria_atual"].eq(
        review.loc[~applied, "categoria_proposta"]
    ).all()
    assert "Risco Corporativo" in MVP_SLIDE_CATEGORIES
    assert "Risco Corporativo" in set(review["categoria_proposta"])

    scope = pd.read_csv(
        ROOT / "data" / "industry_study" / "industry_carteira_1_scope.csv",
        dtype=str,
        keep_default_na=False,
    )
    assert set(review["cnpj"]).issubset(set(scope["cnpj_fundo"]))

    invalid = review.iloc[[0]].copy()
    invalid.loc[:, "applied_flag"] = "NAO"
    invalid.loc[:, "categoria_proposta"] = "Risco Corporativo"
    with pytest.raises(ValueError, match="mantém categoria atual"):
        _validate_financeiro_agro_risk_review(invalid)


def test_review_application_reconciles_99_cases_and_two_exclusions() -> None:
    review = _load_financeiro_agro_risk_review()
    reviewed_rows = review[["cnpj", "categoria_atual"]].rename(
        columns={"categoria_atual": "mvp_slide_categoria"}
    )
    reviewed_rows["mvp_slide_categoria_original"] = reviewed_rows[
        "mvp_slide_categoria"
    ]
    additional_rows = pd.DataFrame(
        {
            "cnpj": [f"{90_000_000_000_000 + index:014d}" for index in range(29)],
            "mvp_slide_categoria": ["Factoring"] * 27 + ["Veículos", "N/D"],
            "mvp_slide_categoria_original": ["Factoring"] * 27
            + ["Veículos", "N/D"],
        }
    )
    rows = pd.concat([reviewed_rows, additional_rows], ignore_index=True)

    applied_rows = _apply_financeiro_agro_risk_review(rows, review)
    included = applied_rows[
        applied_rows["categoria_risco_proposta"].isin(MVP_SLIDE_CATEGORIES)
    ]
    changed = applied_rows["categoria_risco_atual"].ne(
        applied_rows["categoria_risco_proposta"]
    )

    assert len(applied_rows) == 101
    assert len(included) == 99
    excluded = applied_rows.loc[
        ~applied_rows.index.isin(included.index), "categoria_risco_proposta"
    ]
    assert set(excluded) == {"Veículos", "N/D"}
    assert int(changed.sum()) == 20
    assert changed.equals(
        applied_rows["reclassificacao_proposta_flag"].astype(bool)
    )


def test_slide_only_taxonomy_overlay_preserves_all_audited_decisions() -> None:
    overrides = _load_mvp_slide_overrides().set_index("cnpj")
    review = _load_financeiro_agro_risk_review().set_index("cnpj")
    applied = review[review["applied_flag"].eq("SIM")]

    assert len(overrides) == 26
    assert overrides["categoria_mvp"].value_counts().to_dict() == {
        "Risco Corporativo": 13,
        "Adquirência": 11,
        "Agro / Revenda": 1,
        "Consignado INSS e FGTS": 1,
    }
    assert overrides["fonte"].astype(str).str.strip().ne("").all()
    assert overrides["motivo"].astype(str).str.strip().ne("").all()
    assert set(applied.index).issubset(set(overrides.index))
    assert overrides.loc[applied.index, "categoria_mvp"].to_dict() == (
        applied["categoria_proposta"].to_dict()
    )
    for cnpj in (
        "45598747000121",  # SumUp Solo
        "62626887000185",  # SumUp Smart IV
        "52271464000136",  # Kiwify
        "48967719000122",  # Soulpay
        "40919667000107",  # RecargaPay I
        "31739396000117",  # LF III
    ):
        assert overrides.loc[cnpj, "categoria_mvp"] == "Adquirência"
        assert overrides.loc[cnpj, "fonte"]
        assert overrides.loc[cnpj, "motivo"]

    assert overrides.loc["52968533000165", "categoria_mvp"] == "Agro / Revenda"
    for cnpj in (
        "52100879000147",
        "38658727000133",
        "63622842000103",
        "65873297000145",
    ):
        assert overrides.loc[cnpj, "categoria_mvp"] == "Risco Corporativo"

    assert overrides.loc["62393829000159", "categoria_mvp"] == "Risco Corporativo"
    medici = review.loc["62393829000159"]
    assert medici["categoria_proposta"] == "Risco Corporativo"
    assert medici["categoria_atual"] == "Agro / Revenda"
    assert medici["applied_flag"] == "SIM"
