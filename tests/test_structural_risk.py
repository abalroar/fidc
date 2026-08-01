from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.structural_risk import (
    BAND_BREACH,
    BAND_NO_BENCHMARK,
    BAND_THIN,
    MIN_COMPARABLES,
    automatic_insights,
    coverage_report,
    enrich_assets,
    loss_until_trigger,
    percentile_from_quartiles,
    portfolio_metrics,
    summarize_by_category,
)


def _book(**overrides: object) -> pd.DataFrame:
    base = {
        "ativo": ["A", "B", "C"],
        "categoria": ["Consignado INSS", "Consignado INSS", "Factoring"],
        "sub_pl_atual": [0.25, 0.13, 0.40],
        "sub_jr_min_regulamento": [0.20, 0.12, 0.30],
        "pl_atual": [1_000e6, 500e6, 200e6],
        "mercado_categoria_mediana_sub": [0.15, 0.15, 0.35],
        "mercado_categoria_q25_sub": [0.12, 0.12, 0.30],
        "mercado_categoria_q75_sub": [0.20, 0.20, 0.42],
        "mercado_categoria_media_ponderada_pl_sub": [0.14, 0.14, 0.34],
        "n_comparaveis_categoria": [12, 12, 8],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_loss_absorption_is_not_the_arithmetic_difference() -> None:
    """25% over a 20% floor absorbs 6.25% of the book, not 5 points."""

    result = loss_until_trigger(pd.Series([0.25]), pd.Series([0.20]))

    assert result.iloc[0] == pytest.approx(0.0625)


def test_the_gap_between_the_two_readings_grows_with_the_floor() -> None:
    """Same 5pp headroom, very different absorption — this is why it matters."""

    low = loss_until_trigger(pd.Series([0.15]), pd.Series([0.10])).iloc[0]
    high = loss_until_trigger(pd.Series([0.55]), pd.Series([0.50])).iloc[0]

    assert low == pytest.approx(0.05556, rel=1e-3)
    assert high == pytest.approx(0.10, rel=1e-3)
    assert high > low


def test_a_breach_stays_negative_rather_than_clipped() -> None:
    """Clipping to zero would erase how deep the breach is."""

    assert loss_until_trigger(pd.Series([0.10]), pd.Series([0.20])).iloc[0] < 0


def test_the_percentile_saturates_instead_of_extrapolating() -> None:
    q25, median, q75 = (pd.Series([0.12]), pd.Series([0.15]), pd.Series([0.20]))

    far_above = percentile_from_quartiles(pd.Series([0.90]), q25, median, q75).iloc[0]
    far_below = percentile_from_quartiles(pd.Series([0.01]), q25, median, q75).iloc[0]
    at_median = percentile_from_quartiles(pd.Series([0.15]), q25, median, q75).iloc[0]

    assert far_above == 0.75
    assert far_below == 0.25
    assert at_median == pytest.approx(0.50)


def test_a_missing_floor_produces_a_missing_cushion_never_a_zero() -> None:
    """Zero reads as 'no protection'; the truth is 'not measured'."""

    book = _book(sub_jr_min_regulamento=[0.20, np.nan, 0.30])

    assets = enrich_assets(book)

    assert pd.isna(assets.loc[1, "folga_pp"])
    assert pd.isna(assets.loc[1, "perda_ate_gatilho"])


def test_a_thin_category_gets_no_benchmark_rather_than_a_fake_one() -> None:
    book = _book(n_comparaveis_categoria=[12, 12, MIN_COMPARABLES - 1])

    assets = enrich_assets(book)

    assert not bool(assets.loc[2, "benchmark_confiavel"])
    assert pd.isna(assets.loc[2, "excesso_vs_mercado"])
    assert assets.loc[2, "posicao_mercado"] == BAND_NO_BENCHMARK


def test_non_comparable_tranches_do_not_produce_headroom() -> None:
    book = _book(comparacao_estrutural_completa_flag=[True, False, True])

    assets = enrich_assets(book)

    assert pd.isna(assets.loc[1, "folga_pp"])
    assert pd.isna(assets.loc[1, "perda_ate_gatilho"])
    assert assets.loc[1, "situacao_regulatoria"] == "não medido"


def test_missing_pl_remains_missing_in_weights() -> None:
    book = _book(pl_atual=[1_000e6, np.nan, 200e6])

    assets = enrich_assets(book)

    assert pd.isna(assets.loc[1, "peso_pl"])


def test_a_breach_outranks_every_other_band() -> None:
    book = _book(sub_pl_atual=[0.18, 0.13, 0.40])

    assets = enrich_assets(book)

    assert assets.loc[0, "banda"] == BAND_BREACH


def test_a_thin_cushion_is_flagged_even_when_in_line_with_the_market() -> None:
    book = _book(sub_pl_atual=[0.205, 0.13, 0.40])

    assets = enrich_assets(book)

    assert assets.loc[0, "banda"] == BAND_THIN
    assert "folga estreita" in assets.loc[0, "watchlist"]


def test_the_weighted_reading_differs_from_the_median_and_both_are_kept() -> None:
    """When protection sits in the small positions, only the weighted view shows it."""

    # A posição maior é a de colchão mais fino: a mediana simples esconde isso,
    # a ponderada revela.
    book = _book(sub_pl_atual=[0.13, 0.21, 0.60], pl_atual=[5_000e6, 4_000e6, 10e6])

    by_category = summarize_by_category(enrich_assets(book))
    inss = by_category[by_category["categoria"].eq("Consignado INSS")].iloc[0]

    assert inss["sub_mediana_carteira"] == pytest.approx(0.17)
    assert inss["sub_ponderada_carteira"] == pytest.approx(0.16556, rel=1e-4)
    assert inss["sub_ponderada_carteira"] < inss["sub_mediana_carteira"]


def test_coverage_is_measured_in_money_not_in_count() -> None:
    """Missing on the biggest position is not the same blind spot as on the smallest."""

    book = _book(sub_jr_min_regulamento=[np.nan, 0.12, 0.30])

    coverage = coverage_report(enrich_assets(book))
    row = coverage[coverage["campo"].eq("sub_jr_min_regulamento")].iloc[0]

    assert row["ativos_com_dado"] == 2
    # 700 de 1.700 milhões cobertos: a contagem diria 67%, o dinheiro diz 41%.
    assert row["cobertura_pl"] == pytest.approx(700 / 1700, rel=1e-6)


def test_portfolio_metrics_report_the_unmeasured_slice() -> None:
    book = _book(sub_jr_min_regulamento=[np.nan, 0.12, 0.30])

    metrics = portfolio_metrics(enrich_assets(book))

    assert metrics["pl_sem_minimo"] == pytest.approx(1_000e6)


def test_insights_state_facts_without_recommending() -> None:
    assets = enrich_assets(_book())
    lines = automatic_insights(assets, summarize_by_category(assets))

    assert lines
    joined = " ".join(lines).casefold()
    for verb in ("recomendamos", "sugerimos", "deveria", "é preciso"):
        assert verb not in joined


def test_missing_required_columns_fail_loudly() -> None:
    with pytest.raises(KeyError, match="obrigatórias"):
        enrich_assets(pd.DataFrame({"ativo": ["A"]}))


def test_the_demo_book_exercises_every_failure_mode() -> None:
    from scripts.build_structural_risk_deck import build_demo

    assets = enrich_assets(build_demo(seed=7))
    bands = set(assets["banda"])
    market_positions = set(assets["posicao_mercado"])

    assert len(assets) == 101
    assert BAND_BREACH in bands
    assert BAND_NO_BENCHMARK in market_positions
    assert assets["sub_jr_min_regulamento"].isna().any()
