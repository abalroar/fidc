from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from services.industry_flagship_curation import build_portfolio_curation
from services.industry_taxonomy_review import load_taxonomy_review_actions


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "industry_study"
REVISION = DATA / "generated_revision"
LATEST = "2026-06"


def _curation():
    return build_portfolio_curation(
        scope_path=DATA / "industry_carteira_1_scope.csv",
        documentary_path=DATA / "industry_carteira_1_document_curation.csv",
        funds=pd.read_csv(REVISION / "base_fundo_cnpj.csv.gz", low_memory=False),
        vehicle=pd.read_csv(
            REVISION / "base_competencia_cnpj.csv.gz", low_memory=False
        ),
        taxonomy_actions=load_taxonomy_review_actions(
            DATA / "taxonomy_review_actions.csv"
        ),
        latest=LATEST,
    )


def test_carteira_1_saved_scope_matches_the_three_images() -> None:
    scope = pd.read_csv(
        DATA / "industry_carteira_1_scope.csv", dtype=str, keep_default_na=False
    )
    assert len(scope) == 101
    assert scope["ordem"].astype(int).tolist() == list(range(1, 102))
    assert scope["raiz_cnpj_foto"].str.fullmatch(r"\d{8}").all()
    assert scope["cnpj_fundo"].str.fullmatch(r"\d{14}").all()
    assert scope["cnpj_fundo"].nunique() == 101
    assert scope["nome_foto"].str.strip().ne("").all()
    canaa = scope.loc[scope["raiz_cnpj_foto"].eq("45123558")].iloc[0]
    assert canaa["status_identidade"] == "fora_base_fidc"
    assert "FIAGRO Imobiliário" in canaa["observacao_identidade"]

    saved = json.loads((ROOT / "portfolios.json").read_text(encoding="utf-8"))
    portfolio = next(
        row for row in saved["portfolios"] if row["name"] == "Carteira 1"
    )
    assert len(portfolio["funds"]) == 101
    assert len({row["cnpj"] for row in portfolio["funds"]}) == 101


def test_carteira_1_current_metrics_preserve_absence() -> None:
    result = _curation()
    detail = result.detail
    assert result.summary["cnpjs"] == 101
    assert result.summary["cnpjs_localizados_base_fidc"] == 78
    assert result.summary["cnpjs_fora_base_fidc"] == 1
    assert result.summary["cnpjs_com_subordinacao_atual"] == 68
    assert detail["pl_atual_brl"].notna().sum() == 78
    assert detail["subordinacao_atual_pct"].notna().sum() == 68
    assert detail["pl_atual_brl"].dropna().gt(0).all()
    assert detail["subordinacao_atual_pct"].dropna().between(0, 1.01).all()
    absent = detail["subordinacao_atual_status"].str.contains("ausente|N/D")
    assert detail.loc[absent, "subordinacao_atual_pct"].isna().all()
    assert result.ranges["fundos"].sum() == 101
    assert result.ranges.loc[
        result.ranges["faixa_subordinacao_atual"].eq("N/D"), "fundos"
    ].item() == 33


def test_carteira_1_documentary_contract_is_complete_and_traceable() -> None:
    result = _curation()
    detail = result.detail
    located = detail["subordinacao_minima_junior_pct"].notna()
    assert located.sum() == 50
    assert result.summary["cnpjs_com_minimo_junior"] == 50
    assert result.summary["cnpjs_com_data_emissao"] == 97
    assert detail.loc[located, "subordinacao_minima_junior_pct"].gt(0).all()
    assert detail.loc[located, "subordinacao_minima_fonte"].ne("N/D").all()
    assert detail.loc[located, "pagina_clausula"].ne("N/D").all()
    assert detail.loc[~located, "subordinacao_minima_junior_display"].eq("N/D").all()
    assert detail["paginas_lidas"].astype(int).sum() == 11_089
    assert detail["tipo_exibicao"].ne("N/D").sum() == 100

    canaa = detail.loc[detail["cnpj_fundo"].eq("45123558000100")].iloc[0]
    assert pd.isna(canaa["pl_atual_brl"])
    assert pd.isna(canaa["subordinacao_atual_pct"])
    assert pd.isna(canaa["subordinacao_minima_junior_pct"])
    assert canaa["emissao_data_display"] == "N/D"
    assert canaa["tipo_exibicao"] == "N/D"
    assert canaa["status_curadoria_documental"].startswith(
        "fora do perímetro FIDC"
    )
