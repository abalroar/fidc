from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

import altair as alt
import pandas as pd
import pytest

from services.dashboard_ui import (
    PLOTLY_CHART_CONFIG,
    diagnostic_mode_from_params,
    enable_chart_theme,
    normalize_single_selection,
    reconcile_context_selection,
    scoped_page_css,
    style_plotly_figure,
)
from tabs import tab_about, tab_modelo_fidc
from tabs.tab_dashboard_meli import _normalise_audit_identifier_columns
from tabs.tab_cloudwalk_financial_cost import CLOUDWALK_VIEW_TABS
from tabs.tab_industry_study import (
    INDUSTRY_EXECUTIVE_CHARTS,
    INDUSTRY_VIEW_TABS,
    _industry_executive_trend_frames,
)
from tabs.tab_secondary_market import SECONDARY_CHART_KEYS


ROOT = Path(__file__).resolve().parents[1]


def test_diagnostic_mode_is_opt_in() -> None:
    assert diagnostic_mode_from_params({}) is False
    assert diagnostic_mode_from_params({"diagnostic": "0"}) is False
    assert diagnostic_mode_from_params({"diagnostic": "true"}) is True
    assert diagnostic_mode_from_params({"diagnostic": ["0", "1"]}) is True


def test_about_hides_operational_telemetry_outside_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called() -> None:
        raise AssertionError("telemetria operacional não pode ser renderizada no modo normal")

    monkeypatch.setattr(tab_about, "diagnostics_enabled", lambda: False)
    monkeypatch.setattr(tab_about, "render_development_investment_section", fail_if_called)
    monkeypatch.setattr(tab_about.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(tab_about.st, "html", lambda *args, **kwargs: None)
    monkeypatch.setattr(tab_about.st, "expander", lambda *args, **kwargs: nullcontext())

    tab_about.render_tab_about()


def test_about_keeps_operational_telemetry_in_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(tab_about, "diagnostics_enabled", lambda: True)
    monkeypatch.setattr(tab_about, "render_development_investment_section", lambda: calls.append("telemetry"))
    monkeypatch.setattr(tab_about.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(tab_about.st, "html", lambda *args, **kwargs: None)
    monkeypatch.setattr(tab_about.st, "expander", lambda *args, **kwargs: nullcontext())

    tab_about.render_tab_about()

    assert calls == ["telemetry"]


def test_single_selection_normalizes_none_and_stale_values() -> None:
    options = ("3M", "6M", "12M")
    assert normalize_single_selection(None, options, default="12M") == "12M"
    assert normalize_single_selection("24M", options, default="12M") == "12M"
    assert normalize_single_selection("6M", options, default="12M") == "6M"


def test_dependent_selection_resets_only_when_context_changes() -> None:
    state: dict[str, object] = {}
    selected = reconcile_context_selection(
        state,
        signature_key="entity_context",
        value_key="entities",
        signature="segment-a|2025",
        options=("A", "B", "C"),
        default=("B",),
    )
    assert selected == ("B",)

    state["entities"] = ["A", "C"]
    selected = reconcile_context_selection(
        state,
        signature_key="entity_context",
        value_key="entities",
        signature="segment-a|2025",
        options=("A", "B", "C"),
        default=("B",),
    )
    assert selected == ("A", "C")

    selected = reconcile_context_selection(
        state,
        signature_key="entity_context",
        value_key="entities",
        signature="segment-b|2026",
        options=("C", "D"),
        default=("D",),
    )
    assert selected == ("D",)
    assert state["entities"] == ["D"]


def test_shared_altair_finish_is_transparent_and_value_axis_only() -> None:
    enable_chart_theme()
    spec = (
        alt.Chart(pd.DataFrame({"x": [1, 2], "y": [2, 3]}))
        .mark_line(point=True)
        .encode(x="x:Q", y="y:Q")
        .to_dict()
    )
    config = spec["config"]
    assert config["background"] == "transparent"
    assert config["axisX"]["grid"] is False
    assert config["axisY"]["grid"] is True
    assert config["legend"]["orient"] == "bottom"
    assert config["point"]["size"] <= 30


def test_shared_plotly_finish_and_toolbar_contract() -> None:
    go = pytest.importorskip("plotly.graph_objects")
    figure = style_plotly_figure(go.Figure(go.Scatter(x=[1, 2], y=[2, 3])))

    assert PLOTLY_CHART_CONFIG["displayModeBar"] == "hover"
    assert PLOTLY_CHART_CONFIG["displaylogo"] is False
    assert figure.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert figure.layout.plot_bgcolor == "rgba(0,0,0,0)"
    assert figure.layout.uirevision is None
    assert figure.layout.xaxis.showgrid is False
    assert figure.layout.yaxis.showgrid is True


def test_scoped_css_includes_mobile_and_hover_chart_rules() -> None:
    css = scoped_page_css("fidc_page_industria")
    assert ".st-key-fidc_page_industria" in css
    assert "overflow-x: clip" in css
    assert "@media (max-width: 520px)" in css
    assert '[data-testid="stPlotlyChart"]:hover' in css


def test_all_primary_views_and_chart_series_are_preserved() -> None:
    assert INDUSTRY_VIEW_TABS == (
        "Executivo",
        "Ofertas",
        "Prestadores",
        "Cedentes",
        "Investidores",
        "> R$5 bi",
        "Dados e exportações",
    )
    assert CLOUDWALK_VIEW_TABS == (
        "Resumo",
        "Séries",
        "Mensal",
        "Waterfall",
        "Caixa",
        "Dados e exportações",
    )
    assert SECONDARY_CHART_KEYS == (
        "secondary_market_volume_monthly",
        "secondary_market_rate_monthly",
        "secondary_market_top_funds",
        "secondary_market_premium_discount",
    )
    assert INDUSTRY_EXECUTIVE_CHARTS == (
        "industry-executive-pl",
        "industry-executive-relevant-offers",
        "industry-executive-net-flow",
        "industry-executive-holders",
        "industry-executive-delinquency",
    )
    assert {tab_modelo_fidc.MODEL_VIEW_GERAL, tab_modelo_fidc.MODEL_VIEW_MC3} == {
        "Modelo FIDC (geral)",
        "FIDC MC3 Cartões",
    }
    assert {tab_modelo_fidc.CESSION_INPUT_DISCOUNT, tab_modelo_fidc.CESSION_INPUT_MONTHLY} == {
        "Taxa de Cessão",
        "Taxa Mensal (%)",
    }


def test_routes_and_exports_remain_available() -> None:
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    for route in ("sobre", "industria", "secundario", "carteira", "regulamentos", "cloudwalk", "glossario", "modelagem"):
        assert f'("{route}",' in app_source

    source_expectations = {
        "tabs/tab_industry_study.py": ("PPTX", "XLSX", "Baixar CSV"),
        "tabs/tab_secondary_market.py": ("Dados e exportações", "st.dataframe"),
        "tabs/tab_cloudwalk_financial_cost.py": ("Baixar memória XLSX", "Baixar PPTX", "Baixar pacote CSV"),
        "tabs/tab_deep_dive.py": ("Exportar deck de comitê (PPTX)", "Baixar CSV da tabela selecionada"),
        "tabs/tab_modelo_fidc.py": ("Exportar deck de comitê (PPTX)", "Baixar timeline CSV", "Baixar dashboard Excel"),
        "tabs/tab_mercado_livre.py": ("Resumo (Excel)", "Base completa (Excel)", "Base completa (CSV)"),
    }
    for relative_path, expected_labels in source_expectations.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        for label in expected_labels:
            assert label in source


def test_portfolio_context_switch_hides_stale_results_until_refresh_finishes() -> None:
    source = (ROOT / "tabs/portfolio_page.py").read_text(encoding="utf-8")

    assert "portfolio_page_context_signature" in source
    assert "portfolio-context-overlay" in source
    assert "loading_surface.empty()" in source


def test_glossary_page_navigation_uses_compact_selector() -> None:
    source = (ROOT / "tabs/tab_fidc_book.py").read_text(encoding="utf-8")

    assert 'st.selectbox(\n                    "Páginas"' in source


def test_meli_audit_identifiers_are_arrow_safe() -> None:
    frame = pd.DataFrame({"cnpj": ["123", 456, None], "valor": [1, 2, 3]})

    output = _normalise_audit_identifier_columns(frame)

    assert output["cnpj"].tolist() == ["123", "456", ""]


def test_industry_executive_trends_restore_comparative_series() -> None:
    frame = pd.DataFrame(
        {
            "competencia": ["2026-04", "2026-05"],
            "pl_total": [100.0, 120.0],
            "pl_fic_fidc": [10.0, 15.0],
            "captacao_liquida": [-5.0, 8.0],
            "cotistas_total": [1_000.0, 1_200.0],
            "inad_pct_ajustada": [0.05, 0.06],
            "inad_pct": [0.07, 0.08],
        }
    )

    trends = _industry_executive_trend_frames(frame)

    assert set(trends["pl"]["Série"]) == {"FIDCs + FIC-FIDCs", "Somente FIDCs (ex-FIC-FIDCs)"}
    assert set(trends["flow"]["Sinal"]) == {"entrada líquida", "saída líquida"}
    assert trends["holders"]["contas_mil"].tolist() == [1.0, 1.2]
    assert set(trends["delinquency"]["Série"]) == {"Ajustada", "Bruta"}
