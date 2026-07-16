from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

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
from tabs.tab_estimativas_modelagem import ESTIMATES_MODELING_VIEWS
from tabs.tab_industry_study import (
    INDUSTRY_EXECUTIVE_CHARTS,
    INDUSTRY_HOLDER_PL_CUTS_MM,
    INDUSTRY_STRUCTURE_CHARTS,
    INDUSTRY_VIEW_TABS,
    _INDUSTRY_EXECUTIVE_PACK_INPUTS,
    _INDUSTRY_EXPORT_INPUTS,
    _industry_anbima_coverage_note,
    _industry_executive_trend_frames,
    _industry_files_signature,
    _industry_holder_histogram_frames,
    _industry_monostructure_frames,
    _render_industry_tab4_conflict_notice,
    _industry_tab4_conflict_notice,
)
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
    assert ESTIMATES_MODELING_VIEWS == (
        ("custo_cedente", "Custo Financeiro do Cedente"),
        ("vencimentario_premissas", "Vencimentário e Premissas"),
    )
    assert INDUSTRY_EXECUTIVE_CHARTS == (
        "industry-executive-pl",
        "industry-executive-relevant-offers",
        "industry-executive-net-flow",
        "industry-executive-holders",
        "industry-executive-delinquency",
    )
    assert INDUSTRY_STRUCTURE_CHARTS == (
        "industry-provider-monostructure-history",
        "industry-provider-structure-current",
        "industry-holder-histogram-funds",
        "industry-holder-histogram-pl",
    )
    assert INDUSTRY_HOLDER_PL_CUTS_MM == (0, 100, 300, 1000)
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
    for route in ("sobre", "industria", "carteira", "estimativas", "glossario"):
        assert f'("{route}",' in app_source
    assert '("cloudwalk",' not in app_source
    assert '("modelagem",' not in app_source
    assert '"cloudwalk": "estimativas"' in app_source
    assert '"modelagem": "estimativas"' in app_source
    assert '"cloudwalk": VIEW_CEDENT_COST' in app_source
    assert '"modelagem": VIEW_MATURITY_ASSUMPTIONS' in app_source
    assert '("secundario",' not in app_source
    assert '("regulamentos",' not in app_source
    assert '("industria", "Dados da Indústria")' in app_source
    assert '("carteira", "Dados de Carteira")' in app_source
    assert '("estimativas", "Estimativas e Modelagem")' in app_source

    source_expectations = {
        "tabs/tab_industry_study.py": ("PPTX", "XLSX", "Baixar CSV"),
        "tabs/tab_cloudwalk_financial_cost.py": ("Baixar memória XLSX", "Baixar PPTX", "Baixar pacote CSV"),
        "tabs/tab_estimativas_modelagem.py": ("Custo Financeiro do Cedente", "Vencimentário e Premissas"),
        "tabs/tab_deep_dive.py": (
            "Curadoria de Leitura (Documentos)",
            "Prompt usado para atualizar este artefato",
        ),
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
    assert 'st.query_params.get("book_page")' in source
    assert "load_page_body_for_app" in source
    assert 'key="fidc_book_section_tab"' in source
    assert 'on_change="rerun"' in source


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


def test_industry_cache_signatures_track_every_declared_input(tmp_path: Path) -> None:
    names = ("one.csv", "two.csv.gz", "manifest.json")
    for name in names:
        (tmp_path / name).write_text(name, encoding="utf-8")
    first = _industry_files_signature(names, data_dir=tmp_path)

    (tmp_path / "two.csv.gz").write_text("changed payload", encoding="utf-8")
    second = _industry_files_signature(names, data_dir=tmp_path)

    assert first != second
    assert set(_INDUSTRY_EXECUTIVE_PACK_INPUTS).issubset(_INDUSTRY_EXPORT_INPUTS)
    assert {
        "industry_competence_status.csv",
        "industry_monthly.csv",
        "segments_monthly.csv",
        "concentration_monthly.csv",
        "industry_offers_annual.csv",
        "industry_competitive_position.csv",
        "industry_offer_rankings.csv.gz",
        "industry_stock_ranking_deltas.csv.gz",
        "industry_originators_annual.csv",
        "industry_investor_distribution.csv",
        "industry_investor_types.csv",
        "industry_large_fund_documents.csv.gz",
        "industry_intelligence_manifest.json",
    }.issubset(_INDUSTRY_EXPORT_INPUTS)


def test_industry_tab4_conflict_notice_is_concise_and_explicit_about_precedence() -> None:
    pack = SimpleNamespace(
        source_conflicts=pd.DataFrame(
            {
                "competencia": ["2025-12", "2025-12", "2026-05"],
                "cnpj_fundo": ["11111111000111", "11111111000111", "22222222000122"],
                "tab4_type_conflict": [True, True, False],
            }
        )
    )

    notice = _industry_tab4_conflict_notice(pack)

    assert notice == (
        "Integridade CVM: 1 CNPJ com registros Classe/Fundo duplicados em Dezembro/25. "
        "Para evitar dupla contagem, foi aplicada a regra Classe > Fundo."
    )
    assert _industry_tab4_conflict_notice(
        SimpleNamespace(source_conflicts=pd.DataFrame())
    ) == ""


def test_industry_tab4_conflict_notice_is_rendered_only_when_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[str] = []
    monkeypatch.setattr(
        "tabs.tab_industry_study.st.warning",
        lambda message, *args, **kwargs: warnings.append(str(message)),
    )
    _render_industry_tab4_conflict_notice(
        SimpleNamespace(
            source_conflicts=pd.DataFrame(
                {
                    "competencia": ["2025-12"],
                    "cnpj_fundo": ["11111111000111"],
                    "tab4_type_conflict": [True],
                }
            )
        )
    )
    _render_industry_tab4_conflict_notice(
        SimpleNamespace(source_conflicts=pd.DataFrame())
    )

    assert warnings == [
        "Integridade CVM: 1 CNPJ com registros Classe/Fundo duplicados em Dezembro/25. "
        "Para evitar dupla contagem, foi aplicada a regra Classe > Fundo."
    ]


def test_industry_monostructure_frames_preserve_history_and_six_current_models() -> None:
    models = (
        "Monoestrutura",
        "Administração + Gestão",
        "Administração + Custódia",
        "Gestão + Custódia",
        "Três prestadores distintos",
        "Dados incompletos",
    )
    rows: list[dict[str, object]] = []
    for competence, mono_share in (("2024-12", 0.20), ("2025-12", 0.25), ("2026-05", 0.30)):
        remaining = (1.0 - mono_share) / 5.0
        for order, model in enumerate(models):
            share = mono_share if model == "Monoestrutura" else remaining
            rows.append(
                {
                    "competencia": competence,
                    "structure_model": model,
                    "model_order": order,
                    "funds": 100 - order,
                    "pl_brl": 1e9 * (6 - order),
                    "fund_share_total": share,
                    "pl_share_total": share,
                    "provider_fund_coverage": 0.95,
                    "provider_pl_coverage": 0.98,
                }
            )
    pack = SimpleNamespace(
        monostructure_history=pd.DataFrame(rows),
        competences=SimpleNamespace(
            ordered=("2024-12", "2025-12", "2026-05"), latest_complete="2026-05"
        ),
    )

    history, current = _industry_monostructure_frames(pack)

    assert history["metric"].value_counts().to_dict() == {"% dos fundos": 3, "% do PL": 3}
    assert history.sort_values("_period_order")["competencia"].drop_duplicates().tolist() == [
        "2024-12",
        "2025-12",
        "2026-05",
    ]
    assert history.loc[history["competencia"].ne("2026-05"), "period_label"].str.endswith("*").all()
    assert not history.loc[history["competencia"].eq("2026-05"), "period_label"].str.endswith("*").any()
    assert current["structure_model"].astype(str).tolist() == list(models)
    assert current["fund_share_total"].sum() == pytest.approx(1.0)
    assert current["pl_share_total"].sum() == pytest.approx(1.0)


def test_industry_holder_histogram_frames_apply_same_cut_and_anbima_filters() -> None:
    funds = pd.DataFrame(
        [
            ["2026-05", "a", "Financeiro", "Crédito Consignado", 150e6, 1],
            ["2026-05", "b", "Financeiro", "Crédito Consignado", 90e6, 2],
            ["2026-05", "c", "Financeiro", "Crédito Pessoal", 300e6, 3],
            ["2026-05", "d", "Outros", "Recuperação", 500e6, 51],
        ],
        columns=["competencia", "fund_key", "anbima_tipo", "anbima_foco", "pl", "cotistas"],
    )
    pack = SimpleNamespace(
        fund_monthly=funds,
        competences=SimpleNamespace(latest_complete="2026-05"),
        coverage=pd.DataFrame(
            {
                "competencia": ["2026-05"],
                "official_anbima_ex_fic_pl_coverage": [0.915],
            }
        ),
    )

    histogram, coverage = _industry_holder_histogram_frames(
        pack,
        min_pl_brl=100e6,
        anbima_type="Financeiro",
        anbima_focus="Crédito Consignado",
    )

    assert histogram["fund_count"].sum() == 1
    assert histogram.loc[histogram["cotistas_bucket"].eq("1"), "fund_count"].item() == 1
    assert histogram["pl_brl"].sum() == pytest.approx(150e6)
    assert coverage.loc[0, "eligible_funds"] == 1
    assert coverage.loc[0, "included_funds"] == 1
    assert "91,5% do PL ex-FIC" in _industry_anbima_coverage_note(pack)
    assert "proxy CVM ou N/D" in _industry_anbima_coverage_note(pack)
