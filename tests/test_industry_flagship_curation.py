from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.industry_flagship_curation import build_flagship_curation


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "industry_study"
REVISION = DATA / "generated_revision"
DEEP_DIVES = ROOT / "data" / "deep_dives"
LATEST = "2026-06"


@pytest.fixture(scope="module")
def flagship():
    return build_flagship_curation(
        scope_path=DATA / "industry_flagship_scope.csv",
        funds=pd.read_csv(
            REVISION / "base_fundo_cnpj.csv.gz",
            low_memory=False,
        ),
        vehicle=pd.read_csv(
            REVISION / "base_competencia_cnpj.csv.gz",
            low_memory=False,
        ),
        latest=LATEST,
        deep_dives_dir=DEEP_DIVES,
    )


def test_flagship_scope_is_complete_unique_and_current(flagship) -> None:
    detail = flagship.detail
    families = flagship.families
    assert len(detail) == 47
    assert detail["cnpj_fundo"].nunique() == 47
    assert len(families) == 26
    assert families["ordem_familia"].tolist() == list(range(1, 27))
    assert detail["pl_atual_brl"].notna().all()
    assert detail["subordinacao_atual_pct"].notna().all()
    assert detail["subordinacao_atual_pct"].between(0, 1).all()
    assert detail["subordinacao_atual_status"].eq(
        "Calculado com classes reportadas e PL oficial reconciliado"
    ).all()


def test_flagship_documentary_coverage_preserves_gaps(flagship) -> None:
    detail = flagship.detail.set_index("cnpj_fundo")
    assert flagship.summary["cnpjs_com_pacote_documental"] == 15
    assert flagship.summary["cnpjs_com_minimo_junior"] == 6
    assert flagship.summary["cnpjs_com_preco_vnu"] == 13
    assert flagship.summary["cnpjs_com_mezanino_comprovado"] == 8

    paketa = detail.loc["53841740000117"]
    assert pd.isna(paketa["subordinacao_minima_junior_pct"])
    assert paketa["subordinacao_minima_junior_display"] == "N/D"
    assert pd.isna(paketa["preco_emissao_brl"])
    assert paketa["preco_emissao_display"] == "N/D"
    assert paketa["cota_mezanino"] == "N/D"
    assert paketa["vencimento_antecipado"].startswith("N/D")


def test_flagship_known_documentary_fields_are_source_faithful(flagship) -> None:
    detail = flagship.detail.set_index("cnpj_fundo")

    bela = detail.loc["62393679000183"]
    assert pd.isna(bela["subordinacao_minima_junior_pct"])
    assert bela["subordinacao_minima_junior_display"] == "1% / 2,5%"
    assert bela["preco_emissao_brl"] == pytest.approx(1_000.0)
    assert bela["cota_mezanino"] == "Sim"
    assert "1117954" in bela["subordinacao_minima_fonte"]

    seller_iii = detail.loc["63572282000111"]
    assert seller_iii["subordinacao_minima_junior_pct"] == pytest.approx(10.0)
    assert seller_iii["preco_emissao_brl"] == pytest.approx(1_000.0)
    assert seller_iii["cota_mezanino"] == "Sim"

    mercado_ii = detail.loc["41970012000126"]
    assert mercado_ii["subordinacao_minima_junior_pct"] == pytest.approx(10.0)
    assert mercado_ii["preco_emissao_brl"] == pytest.approx(1_000.0)
    assert "1077334" in mercado_ii["subordinacao_minima_fonte"]


def test_flagship_family_ranges_cover_every_family(flagship) -> None:
    observed = flagship.families["faixa_subordinacao_atual"].value_counts().to_dict()
    assert observed == {
        "< 10%": 5,
        "10%–15%": 4,
        "15%–20%": 6,
        "20%–35%": 3,
        "35%–60%": 4,
        "≥ 60%": 4,
    }
    assert flagship.families["subordinacao_atual_pct"].notna().all()


def test_flagship_divergent_quota_pl_is_not_materialized_as_zero(tmp_path: Path) -> None:
    scope = pd.DataFrame(
        [
            {
                "ordem_categoria": 1,
                "categoria": "Teste",
                "ordem_familia": 1,
                "familia_flagship": "Fundo teste",
                "cnpj_fundo": "00.000.000/0001-91",
                "representante_familia": 1,
                "pacote_documental": "",
            }
        ]
    )
    scope_path = tmp_path / "scope.csv"
    scope.to_csv(scope_path, index=False)
    funds = pd.DataFrame(
        [
            {
                "competencia": LATEST,
                "cnpj_fundo": "00000000000191",
                "denominacao": "Fundo teste",
                "pl": 100.0,
            }
        ]
    )
    vehicle = pd.DataFrame(
        [
            {
                "competencia": LATEST,
                "cnpj_fundo": "00000000000191",
                "cnpj": "00000000000191",
                "vl_cotas_total": 50.0,
                "vl_cotas_subordinadas": 10.0,
            }
        ]
    )
    result = build_flagship_curation(
        scope_path=scope_path,
        funds=funds,
        vehicle=vehicle,
        latest=LATEST,
        deep_dives_dir=tmp_path,
    )
    row = result.detail.iloc[0]
    assert pd.isna(row["subordinacao_atual_pct"])
    assert "diverge" in row["subordinacao_atual_status"]
    assert result.families.iloc[0]["faixa_subordinacao_atual"] == "N/D"
