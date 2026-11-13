from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from services.industry_anbima_analysis import build_anbima_analysis
from services.industry_intelligence import canonical_provider
from services.industry_revision_additions import build_independent_provider_historical_ranking

DATA = Path(__file__).resolve().parents[1] / "data/industry_study"


@pytest.fixture(scope="module")
def analysis():
    return build_anbima_analysis(DATA)


def test_annex_top15_uses_one_role_and_distinct_registrations(analysis):
    annex = pd.read_csv(DATA / "anbima_rf_ranking_annex.csv.gz", dtype={"block_code": str, "classe": str})
    fidc = annex[annex.role.eq("originacao") & annex.block_code.eq("1") & annex.classe.eq("1.3.1")]
    truth = fidc.groupby("registro_cvm").valor_brl.sum().sort_values(ascending=False, kind="stable")
    deals = pd.DataFrame(analysis["fidc_deals"])
    top = pd.DataFrame(analysis["fidc_top15"])
    assert deals.registro_cvm.is_unique
    assert len(deals) == len(truth) == analysis["fidc_summary"]["registrations"]
    assert deals.volume_brl.sum() == pytest.approx(truth.sum(), abs=0.01)
    assert top.registro_cvm.tolist() == truth.head(15).index.tolist()
    assert top.volume_brl.sum() == pytest.approx(truth.head(15).sum(), abs=0.01)
    assert analysis["fidc_summary"]["top15_share"] == pytest.approx(truth.head(15).sum()/truth.sum())
    ibba = fidc[fidc.participante.eq("ITAU BBA")].groupby("registro_cvm").valor_brl.sum()
    assert top.ibba_volume_brl.sum() == pytest.approx(ibba.reindex(top.registro_cvm).sum(), abs=0.01)


def test_sector_denominator_includes_unclassified_volume(analysis):
    sectors = pd.DataFrame(analysis["fidc_sectors"])
    deals = pd.DataFrame(analysis["fidc_deals"])
    total = analysis["fidc_summary"]["volume_brl"]
    assert sectors.volume_brl.sum() == pytest.approx(total, abs=0.01)
    assert sectors.share.sum() == pytest.approx(1)
    assert sectors.set_index("category").loc["N/D", "volume_brl"] == pytest.approx(deals.loc[deals.category.eq("N/D"), "volume_brl"].sum())
    assert analysis["fidc_summary"]["classification_volume_coverage"] == pytest.approx(1-sectors.loc[sectors.category.eq("N/D"), "share"].sum())
    assert all(len(row["cnpj_emissor"]) == 14 for row in analysis["fidc_deals"])


def test_official_ranking_preserves_source_names_and_unpublished_is_null(analysis):
    ranking = pd.DataFrame(analysis["ranking"])
    assert ranking.participant_source.str.endswith("*").any()
    assert not ranking.participant.str.endswith("*").any()
    related_distribution = next(row for row in analysis["ibba_positions"] if row["ranking_code"] == "3" and row["role"] == "Distribuição")
    assert related_distribution["status"] == "sem ranking publicado"
    assert related_distribution["rank"] is related_distribution["volume_brl"] is related_distribution["share"] is None
    json.dumps(analysis, allow_nan=False)


def test_products_exclude_related_companies_and_distribution(analysis):
    annex = pd.read_csv(DATA / "anbima_rf_ranking_annex.csv.gz", dtype={"block_code": str})
    truth = annex[annex.role.eq("originacao") & annex.block_code.isin(["1", "2"])].valor_brl.sum()
    assert sum(row["volume_brl"] for row in analysis["products"]) == pytest.approx(truth, abs=0.01)


def test_market_operations_and_top15_retain_all_originated_credit(analysis):
    annex = pd.read_csv(DATA / "anbima_rf_ranking_annex.csv.gz", dtype={"block_code": str})
    origin = annex[annex.role.eq("originacao") & annex.block_code.isin(["1", "2"])]
    operations = pd.DataFrame(analysis["market_operations"])
    top15 = pd.DataFrame(analysis["market_top15"])
    assert operations.operation_id.is_unique
    assert operations.volume_brl.sum() == pytest.approx(origin.valor_brl.sum(), abs=0.01)
    assert top15.volume_brl.sum() == pytest.approx(operations.volume_brl.nlargest(15).sum(), abs=0.01)
    assert operations.ibba_volume_brl.sum() == pytest.approx(origin.loc[origin.participante.eq("ITAU BBA"), "valor_brl"].sum(), abs=0.01)
    assert analysis["market_summary"]["top15_share"] == pytest.approx(top15.volume_brl.sum()/operations.volume_brl.sum())


def test_twelve_month_positions_use_official_window_not_current_annex(analysis):
    official = pd.read_csv(DATA / "anbima_rf_ranking_official.csv", dtype={"ranking_code": str})
    official["participant"] = official.participant.str.replace(r"\*+$", "", regex=True)
    for row in analysis["ibba_positions_all"]:
        source = official[official.window.eq(row["window"]) & official.ranking_code.eq(row["ranking_code"]) & official.participant.eq("ITAU BBA") & official.measure.eq({"Originação":"originacao_valor", "Distribuição":"distribuicao_valor"}[row["role"]])]
        if source.empty:
            assert row["volume_brl"] is None
        else:
            assert row["volume_brl"] == pytest.approx(source.iloc[0].value_brl_or_count)
            assert row["share"] == pytest.approx(source.iloc[0]["share"])
    assert analysis["windows"]["ultimos_12_meses"]["start"] == "2025-10-01"
    assert analysis["windows"]["ultimos_12_meses"]["end"] == "2026-09-30"


def test_itau_and_kanastra_are_separate_in_normalization_and_independents():
    assert canonical_provider("KANASTRA ADMINISTRACAO DE RECURSOS LTDA") == "Kanastra"
    assert canonical_provider("LIMINE TRUST DTVM LTDA") == "Kanastra"
    assert canonical_provider("ITAU UNIBANCO SA") == "Itaú"
    source = pd.DataFrame([
        {"competencia": "2026-09", "papel": "administrador", "participante": name,
         "pl_brl": amount, "fundos": 1, "denominador_pl_brl": 171, "fundos_universo": 3,
         "rank_periodo": rank, "share_pl": amount/171, "fonte_prestador": "Informe Mensal"}
        for rank, (name, amount) in enumerate([("KANASTRA",101), ("ITAU UNIBANCO",50), ("LIMINE TRUST",20)], start=1)
    ])
    curated = pd.read_csv(DATA / "provider_ownership_curation.csv")
    result = build_independent_provider_historical_ranking(source, curated, latest_period="2026-09")
    assert result.participante.tolist() == ["Kanastra"]
    assert result.iloc[0].pl_brl == 121
    assert result.iloc[0].denominador_pl_brl == 171
