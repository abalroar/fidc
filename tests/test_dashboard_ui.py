from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import tomllib

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
from tabs import tab_industry_study
from tabs.tab_dashboard_meli import _normalise_audit_identifier_columns
from tabs.tab_cloudwalk_financial_cost import CLOUDWALK_VIEW_TABS
from tabs.tab_estimativas_modelagem import ESTIMATES_MODELING_VIEWS
from tabs.tab_industry_study import (
    INDUSTRY_EXECUTIVE_CHARTS,
    INDUSTRY_HOLDER_PL_CUTS_MM,
    INDUSTRY_STRUCTURE_CHARTS,
    INDUSTRY_VIEW_TABS,
    _CEDENTE_COMPETENCES,
    _INDUSTRY_EXECUTIVE_PACK_INPUTS,
    _INDUSTRY_EXPORT_INPUTS,
    _industry_anbima_coverage_note,
    _industry_executive_trend_frames,
    _industry_files_signature,
    _load_csv,
    _industry_holder_histogram_frames,
    _industry_monostructure_frames,
    _revision_holder_distribution_frame,
    _revision_history_frame,
    _revision_offer_comparable_frame,
    _revision_offer_current_row,
    _revision_offers_cutoff,
    _revision_period_encoding,
    _render_industry_tab4_conflict_notice,
    _taxonomy_review_action_choice,
    _industry_tab4_conflict_notice,
)
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("clicked_label", "expected_status"),
    [
        ("Aprovar e próximo", "approve"),
        ("Salvar e permanecer", "save"),
        ("Pular", "skip"),
    ],
)
def test_taxonomy_review_actions_remain_clickable_without_authorization(
    monkeypatch: pytest.MonkeyPatch,
    clicked_label: str,
    expected_status: str,
) -> None:
    rendered: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        tab_industry_study.st,
        "columns",
        lambda widths: [nullcontext() for _ in widths],
    )

    def click_selected(label: str, **kwargs: object) -> bool:
        rendered.append((label, kwargs))
        return label == clicked_label

    monkeypatch.setattr(tab_industry_study.st, "button", click_selected)

    assert _taxonomy_review_action_choice("12345678000199") == expected_status
    assert [label for label, _ in rendered] == [
        "Aprovar e próximo",
        "Salvar e permanecer",
        "Pular",
    ]
    assert all("disabled" not in kwargs for _, kwargs in rendered)


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
    # "Breakdown FIDCs Cartão", "Top 20" e "Reclassificação Manual - Tipo
    # ANBIMA" saíram da navegação; os dados e a classificação de adquirência
    # continuam no backend, cobertos pelos testes de taxonomia.
    assert INDUSTRY_VIEW_TABS == (
        "Principais conclusões",
        "Escala e taxonomia",
        "Base investidora",
        "Carteira e inadimplência",
        "Prestadores",
        "Ofertas e originação",
        "Dados e exportações",
    )
    for removed in (
        "Breakdown FIDCs Cartão",
        "Top 20",
        "Reclassificação Manual - Tipo ANBIMA",
    ):
        assert removed not in INDUSTRY_VIEW_TABS
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
        "tabs/tab_industry_study.py": ("PPTX", "XLSX", "HTML interativo", "Baixar CSV"),
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


def test_app_brand_is_centered_and_uses_the_shared_orange() -> None:
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert '<h1 class="fidc-app-title">toma.conta fidcs</h1>' in app_source
    assert '<p class="fidc-app-author">por matheus prates, cfa</p>' in app_source
    assert ".fidc-app-header {" in app_source
    assert "text-align: center;" in app_source
    assert "flex-direction: column;" in app_source
    assert "color: #ff5a00 !important;" in app_source
    assert "font-family: 'IBM Plex Sans', sans-serif !important;" in app_source


def test_industry_revision_uses_itau_bba_orange_in_css_and_chart_specs() -> None:
    source = (ROOT / "tabs/tab_industry_study.py").read_text(encoding="utf-8")
    revision_source = source[source.index("def _render_revision_overview") :]

    assert '_ORANGE = "#EC7000"' in source
    assert '_ORANGE_SOFT = "rgba(236, 112, 0, 0.14)"' in source
    assert "border-left: 4px solid #EC7000;" in source
    assert ".industry-thesis b { color: #EC7000; }" in source
    assert "#ff5a00" not in revision_source.lower()
    period_order, period_colors = _revision_period_encoding(
        pd.DataFrame(
            {
                "competencia": ["2023-12", "2026-05"],
                "Período": ["Dez/23", "Mai/26"],
            }
        )
    )
    assert period_order == ["Dez/23", "Mai/26"]
    assert period_colors == ["#8D9399", "#EC7000"]
    assert "alt.value(_ORANGE)" in revision_source
    assert "range=[_ORANGE, _BLACK]" in revision_source
    assert "industry-revision-type-mix-volume" in revision_source
    assert "industry-revision-type-mix-share" in revision_source
    assert "N/D foi incorporado em Outros nesta visualização" in revision_source


def test_revision_history_frame_adds_period_label_to_acquiring_mix() -> None:
    frame = _revision_history_frame(
        {
            "acquiring_reclassified_mix": [
                {
                    "competencia": "2026-05",
                    "categoria_analitica": "Adquirência",
                    "pl_brl": 1.0,
                }
            ]
        },
        "acquiring_reclassified_mix",
    )

    assert frame.loc[0, "Período"] == "Mai/26"


def test_industry_revision_holder_distributions_add_normalized_percentage_charts() -> None:
    frame = pd.DataFrame(
        {
            "bucket": ["1", "2–10", ">10"],
            "fundos": [50, 30, 20],
            "pl": [100.0, 100.0, 300.0],
            "share_fundos": [0.9, 0.05, 0.05],
            "share_pl": [0.1, 0.1, 0.1],
        }
    )

    normalized = _revision_holder_distribution_frame(frame)

    assert normalized["share_fundos"].sum() == pytest.approx(1.0)
    assert normalized["share_pl"].sum() == pytest.approx(1.0)
    assert normalized["share_fundos"].tolist() == pytest.approx([0.5, 0.3, 0.2])
    assert normalized["share_pl"].tolist() == pytest.approx([0.2, 0.2, 0.6])

    historical = _revision_holder_distribution_frame(
        pd.DataFrame(
            {
                "competencia": ["2023-12", "2023-12", "2026-05", "2026-05"],
                "bucket": ["1", ">1", "1", ">1"],
                "fundos": [3, 1, 1, 3],
                "pl": [75.0, 25.0, 20.0, 80.0],
            }
        )
    )
    assert historical.groupby("competencia")["share_fundos"].sum().tolist() == pytest.approx([1.0, 1.0])
    assert historical.groupby("competencia")["share_pl"].sum().tolist() == pytest.approx([1.0, 1.0])

    source = (ROOT / "tabs/tab_industry_study.py").read_text(encoding="utf-8")
    revision_source = source[source.index("def _render_revision_investors") :]
    assert 'title="Fundos por faixa: % do total"' in revision_source
    assert 'title="PL por faixa: % do total"' in revision_source
    assert 'key="industry-revision-holder-funds-share-history"' in revision_source
    assert 'key="industry-revision-holder-pl-share-history"' in revision_source
    assert revision_source.count('xOffset=alt.XOffset("Período:N"') >= 4
    assert revision_source.count('format=".0%"') >= 2
    assert 'key="industry-revision-receivables-share-history"' in revision_source
    assert '"industry-revision-provider-top10-history"' in revision_source
    assert 'payload.get("atlantico_profile")' in source
    assert "_render_revision_atlantico(payload)" not in revision_source
    assert "Atlântico FIDC" in revision_source

    with pytest.raises(ValueError, match="fundos negativo"):
        _revision_holder_distribution_frame(
            pd.DataFrame({"bucket": ["1"], "fundos": [-1], "pl": [100.0]})
        )


def test_industry_revision_exposes_selected_deck_views_with_labels_and_notes() -> None:
    source = (ROOT / "tabs/tab_industry_study.py").read_text(encoding="utf-8")
    revision_source = source[source.index("def _render_revision_conclusions") :]

    assert "python scripts/publish_fidc_revision_bundle.py" in source
    assert "python scripts/build_fidc_revision_analysis.py &&" not in source

    required_text = (
        "Principais conclusões",
        'payload.get("executive_conclusions")',
        'payload.get("executive_conclusion_notes")',
        "Grandes números",
        "growth_multiple_label",
        "holder_ge_200m_share_pl_ate_10_contas",
        "btg_bank_cohort_observed_funds",
        "btg_bank_cohort_combo_funds",
        "FIDCs e Carteira de Crédito Privada Ampliada",
        "Contas e veículos reportantes",
        "Distribuição por número de contas: dez/23 e {stock_label_lower}",
        "Taxonomia CVM com abertura analítica de adquirência",
        "Cartão de crédito: lista completa e decisão de curadoria",
        "industry-revision-card-taxonomy-download",
        "Fotografia da coorte",
        "Revisão da série",
        "delinquency_cohort_revision_transitions",
        "Ranking e concentração dos prestadores",
        "Evolução do ranking dos prestadores",
        "btg_provider_ex_controlled_scenario",
        "BTG ex-coorte bancária curada",
        "PL observado",
        "Prestadores independentes",
        "cedent_originator_explicit",
        "document_reference_date",
        "Modelo de prestação e monoestruturas",
        "Distribuição do valor das emissões",
        "Participação no volume registrado",
        "Volume registrado por faixa",
        "Volume e regime de colocação",
        "Regime de colocação · número de ofertas",
        "Regime de colocação · volume",
        "Top 15 ofertas encerradas e originadores",
        "Coord. líder = coordenador informado no requerimento",
        "IBBA Coord = ",
        "propostas, fees",
    )
    for text in required_text:
        assert text in revision_source

    required_chart_keys = (
        "industry-revision-pl",
        "industry-revision-bcb-credit",
        "industry-revision-accounts",
        "industry-revision-vehicles",
        "industry-revision-investor-composition",
        "industry-revision-holder-funds-history",
        "industry-revision-holder-pl-history",
        "industry-revision-holder-funds-share-history",
        "industry-revision-holder-pl-share-history",
        "industry-revision-acquiring-pl",
        "industry-revision-acquiring-share",
        "industry-revision-delinquency-frozen-cohort-history",
        "industry-revision-provider-top10-history",
        "industry-revision-provider-top5-history",
        "industry-revision-provider-ranking-",
        "industry-revision-independent-",
        "industry-revision-service-model-shares",
        "industry-revision-closed-offer-ticket-histogram",
        'f"{chart_key}-volume-share"',
        'f"{chart_key}-volume-absolute"',
        "industry-revision-placement-total-offers",
        "industry-revision-placement-total-volume",
        "industry-revision-placement-regime-offers",
        "industry-revision-placement-regime-volume",
        "industry-revision-closed-offers-jan-june",
    )
    for key in required_chart_keys:
        assert key in revision_source

    assert revision_source.count(".mark_text(") >= 18
    assert 'range=[_GRAY_LIGHT, _ORANGE]' in revision_source
    assert 'color="white"' in revision_source
    assert "Síntese executiva" not in revision_source
    assert "\nex-6 " not in revision_source
    assert revision_source.index("industry-revision-closed-offers-cumulative") < revision_source.index(
        "industry-revision-closed-offer-ticket-histogram"
    )


def test_industry_revision_preserves_slide_specific_sources_and_caveats() -> None:
    source = (ROOT / "tabs/tab_industry_study.py").read_text(encoding="utf-8")
    revision_source = source[source.index("def _render_revision_conclusions") :]

    required_notes = (
        "Fontes: CVM, ANBIMA, FundosNet e BCB",
        "Fonte: CVM, Informe Mensal de FIDC. Variações dezembro contra dezembro",
        "Crescimento do PL ex-FIC",
        "Fonte: Banco Central do Brasil. Série de carteira de crédito ampliada",
        "Fonte: CVM, Informe Mensal de FIDC, {stock_label_lower}",
        "Fonte: CVM, dez/23 e {stock_label_lower}",
        "Fonte: CVM, Informe Mensal e documentos primários",
        "fallback mai/26",
        "transações do arranjo e da cadeia de pagamentos entram em Adquirência",
        "crédito a PF/PJ ou CCB permanece fora",
        "Fonte: CVM, dez/25 e {stock_label_lower}",
            "A lista delimita a coorte bancária atual",
        "Singulare é consolidada em QI Tech",
        "Fonte: CVM, cadastro vigente em {stock_label_lower}",
        "Fonte: ANBIMA, regulamentos e documentos das ofertas; ranking em {stock_label_lower}",
        "CVM — Sistema de Registro de Ofertas (SRE)",
        "ofertas primárias encerradas",
        "todos os ritos",
        "data de encerramento preenchida",
        "Encerramento regulatório não comprova colocação integral",
        "FIDCs versus demais emissões de renda fixa",
        "A linha laranja mostra o consolidado ajustado de mercado",
        "Nos meses legados, presença de reporte é inferida por registro",
    )
    for note in required_notes:
        assert note in revision_source


def test_industry_revision_offers_use_jan_june_cutoff_with_legacy_fallback() -> None:
    annual = [
        {
            "year": 2026,
            "closed_offers": 841,
            "registered_volume_brl": 69_600_000_000.0,
            "mean_registered_ticket_brl": 82_700_000.0,
            "median_registered_ticket_brl": 22_500_000.0,
            "natural_person_placed_volume_share": 0.04,
            "placed_quantity_registered_volume_coverage": 0.973,
            "professional_target_registered_volume_share": 0.938,
        }
    ]
    jan_june = [
        {
            "year": 2026,
            "period_end": "2026-06-30",
            "closed_offers": 771,
            "registered_volume_brl": 65_488_118_983.56,
            "mean_registered_ticket_brl": 84_939_194.53,
        }
    ]
    payload = {
        "closed_offers_annual": annual,
        "closed_offers_jan_june": jan_june,
        "closed_offers_jan_may": [
            {
                "year": 2026,
                "closed_offers": 554,
                "registered_volume_brl": 51_475_000_000.0,
                "mean_registered_ticket_brl": 92_900_000.0,
            }
        ],
    }

    comparable = _revision_offer_comparable_frame(payload)
    current = _revision_offer_current_row(payload)

    assert int(comparable.iloc[0]["closed_offers"]) == 771
    assert int(current["closed_offers"]) == 771
    assert float(current["registered_volume_brl"]) == pytest.approx(
        65_488_118_983.56
    )
    assert float(current["median_registered_ticket_brl"]) == 22_500_000.0
    assert _revision_offers_cutoff(payload) == "2026-06-30"

    legacy = {"closed_offers_jan_may": payload["closed_offers_jan_may"]}
    assert int(_revision_offer_comparable_frame(legacy).iloc[0]["closed_offers"]) == 554
    assert _revision_offers_cutoff(legacy) == "2026-06-30"


def test_industry_revision_offers_show_full_year_history_and_stop_2026_at_june() -> None:
    source = (ROOT / "tabs/tab_industry_study.py").read_text(encoding="utf-8")
    offers_source = source[
        source.index("def _render_revision_offers") : source.index(
            "def _render_revision_data_exports"
        )
    ]

    assert 'key="industry-revision-closed-offers-jan-june"' in offers_source
    assert 'title="Volume registrado e ticket · FY / YTD"' in offers_source
    assert 'title="Volume acumulado · janeiro a dezembro"' in offers_source
    assert 'monthly["month"].le(6)' in offers_source
    assert "ofertas primárias encerradas até" in offers_source
    assert "as curvas de 2024 e 2025 seguem até dezembro" in offers_source
    assert "Jan–mai" not in offers_source
    assert "jan–mai" not in offers_source
    assert "17/jul/26" not in offers_source


def test_ibm_plex_sans_is_self_hosted_by_streamlit() -> None:
    config = tomllib.loads((ROOT / ".streamlit/config.toml").read_text(encoding="utf-8"))
    expected_fonts = (
        "IBMPlexSans-Light-Latin1.woff2",
        "IBMPlexSans-Regular-Latin1.woff2",
        "IBMPlexSans-Medium-Latin1.woff2",
        "IBMPlexSans-SemiBold-Latin1.woff2",
        "IBMPlexSans-Bold-Latin1.woff2",
    )

    assert config["server"]["enableStaticServing"] is True
    for filename in expected_fonts:
        assert (ROOT / "static/fonts" / filename).is_file()
    assert (ROOT / "static/fonts/IBM-Plex-OFL.txt").is_file()

    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert app_source.count("@font-face {") == len(expected_fonts)
    for filename in expected_fonts:
        assert f"app/static/fonts/{filename}" in app_source
    assert "fonts.googleapis.com" not in app_source


def test_portfolio_context_switch_clears_stale_results_without_fullscreen_overlay() -> None:
    source = (ROOT / "tabs/portfolio_page.py").read_text(encoding="utf-8")

    assert "portfolio_page_context_signature" in source
    assert "analysis_surface.empty()" in source
    assert "portfolio-loading-state" in source
    assert "portfolio-context-overlay" not in source
    assert "position: fixed" not in source
    assert "visibility: hidden" not in source
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
        "industry_cnpj_manual_enrichment.csv",
        "industry_intelligence_manifest.json",
        "generated_revision/artifact_payload.json",
        "generated_revision/revision_manifest.json",
        "generated_revision/industry_export_bundle.json",
        "generated_revision/industry_executive_revised.pptx",
        "generated_revision/industry_data_revised.xlsx",
        "generated_revision/carteira_101_flagships.xlsx",
        "generated_revision/top100_fidcs_middle_market.xlsx",
        "generated_revision/provider_flows_explorer.html",
    }.issubset(_INDUSTRY_EXPORT_INPUTS)


def test_industry_exports_expose_the_top100_plus2_workbook_download() -> None:
    source = (ROOT / "tabs/tab_industry_study.py").read_text(encoding="utf-8")
    payload_source = source[
        source.index("def _industry_export_payloads") : source.index(
            "def _industry_provider_flow_html"
        )
    ]
    download_source = source[
        source.index("_INDUSTRY_EXPORT_BUTTONS") : source.index(
            "def _stock_delta_display"
        )
    ]
    data_export_source = source[
        source.index("def _render_revision_data_exports") : source.index(
            "def _render_industry_data_audit"
        )
    ]

    assert "tuple[dict[str, bytes], dict[str, str]]" in payload_source
    assert "build_revision_top100_xlsx_bytes" in payload_source
    assert "Top 100 + 2 FIDCs" in download_source
    assert "Top100_Plus2_FIDCs_Middle_Market_" in download_source
    assert "industry-top100-xlsx" in download_source
    assert "Excel — Top 100 + 2 FIDCs e Middle Market" in data_export_source
    assert "top100_fidcs_middle_market.xlsx" in data_export_source


def test_industry_exports_expose_taxonomy_audit_and_cedente_triage() -> None:
    source = (ROOT / "tabs/tab_industry_study.py").read_text(encoding="utf-8")
    data_export_source = source[
        source.index("def _render_revision_data_exports") : source.index(
            "def _render_industry_data_audit"
        )
    ]

    assert "Excel — estudo, taxonomia e triagem de cedentes" in data_export_source
    assert "industry_taxonomy_audited_decisions_202606.csv" in data_export_source
    assert "industry_taxonomy_impact_summary_202606.csv" in data_export_source
    assert "fidc_cedentes_top500_2023_2026.csv.gz" in data_export_source
    assert "fidc_cedentes_cobertura_top500_2023_2026.csv" in data_export_source
    assert "fidc_cedentes_pl_segmento_2023_2026.csv" in data_export_source
    assert "fidc_cedentes_exclusoes_2023_2026.csv.gz" in data_export_source
    assert "fidc_cedentes_receita_targets.csv" in data_export_source
    assert "fidc_cedentes_reparos_fonte_2023_2026.csv" in data_export_source
    assert "top437" not in data_export_source.casefold()
    assert '".gz": "application/gzip"' in data_export_source
    assert "CVM — Informe Mensal FIDC, Tabela I" in data_export_source
    assert "o campo não identifica sacado" in data_export_source
    assert {
        "industry_taxonomy_audited_decisions_202606.csv",
        "industry_taxonomy_impact_summary_202606.csv",
        "cedente_triage/fidc_cedentes_top500_2023_2026.csv.gz",
        "cedente_triage/fidc_cedentes_por_competencia_2023_2026.csv.gz",
        "cedente_triage/fidc_cedentes_fundos_sem_cedente_2023_2026.csv.gz",
        "cedente_triage/fidc_cedentes_evolucao_segmento_2023_2026.csv",
        "cedente_triage/fidc_cedentes_presenca_tempo_2023_2026.csv.gz",
        "cedente_triage/fidc_cedentes_cobertura_top500_2023_2026.csv",
        "cedente_triage/fidc_cedentes_pl_segmento_2023_2026.csv",
        "cedente_triage/fidc_cedentes_cadastro_master.csv.gz",
        "cedente_triage/fidc_cedentes_exclusoes_2023_2026.csv.gz",
        "cedente_triage/fidc_cedentes_receita_targets.csv",
        "cedente_triage/fidc_cedentes_reparos_fonte_2023_2026.csv",
        "cedente_triage/fidc_cedentes_triagem_index.json",
    }.issubset(_INDUSTRY_EXPORT_INPUTS)


def test_industry_overview_exposes_top500_cedente_segment_block() -> None:
    source = (ROOT / "tabs/tab_industry_study.py").read_text(encoding="utf-8")
    block_source = source[
        source.index("def _render_revision_cedente_segments") : source.index(
            "def _revision_offer_comparable_frame"
        )
    ]
    overview_source = source[
        source.index("def _render_revision_overview") : source.index(
            "def _render_revision_card_breakdown"
        )
    ]

    assert _CEDENTE_COMPETENCES == ("202312", "202412", "202512", "202606")
    for payload_key in (
        "cedente_top500_detail",
        "cedente_segment_mix_history",
        "cedente_top500_coverage_history",
        "cedente_registry_by_competence",
        "cedente_triage_manifest",
    ):
        assert payload_key in source
    for label in (
        "Cedentes do Top 500 · segmento e cobertura",
        "Mix de PL por segmento do cedente dominante",
        "Cobertura do Top 500 sobre o PL da indústria",
        "Denominador: PL dos fundos do Top 500",
        "Denominador: PL total da indústria",
        "Potencial Middle",
        "classificação residual",
        "não comprovam",
        "faturamento entre R$ 30 milhões e R$ 500 milhões",
        "Natureza do cedente",
        "Seção CNAE",
    ):
        assert label in block_source
    for filter_key in (
        "industry-revision-cedente-filter-competence",
        "industry-revision-cedente-filter-segment",
        "industry-revision-cedente-filter-nature",
        "industry-revision-cedente-filter-uf",
        "industry-revision-cedente-filter-cnae-section",
    ):
        assert filter_key in block_source
    assert block_source.count("st.multiselect(") == 5
    assert "_render_revision_cedente_segments(payload)" in overview_source


def test_industry_csv_cache_reloads_when_the_source_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "industry_competence_status.csv"
    source.write_text("competencia,publication_status\n2026-05,completa\n", encoding="utf-8")
    monkeypatch.setattr(tab_industry_study, "_DATA_DIR", tmp_path)
    _load_csv.clear()

    first_signature = _industry_files_signature((source.name,), data_dir=tmp_path)
    first = _load_csv(source.name, first_signature)

    source.write_text(
        "competencia,publication_status\n2026-05,completa\n2026-06,completa\n",
        encoding="utf-8",
    )
    second_signature = _industry_files_signature((source.name,), data_dir=tmp_path)
    second = _load_csv(source.name, second_signature)
    _load_csv.clear()

    assert first is not None and first["competencia"].tolist() == ["2026-05"]
    assert second is not None and second["competencia"].tolist() == [
        "2026-05",
        "2026-06",
    ]


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


def test_one_failing_export_keeps_the_other_downloads(monkeypatch) -> None:
    """A broken builder must not empty the whole export section."""

    import services.industry_ppt_export as ppt_export
    import services.industry_revision_export as revision_export
    from tabs.tab_industry_study import _industry_export_payloads

    monkeypatch.setattr(ppt_export, "build_industry_pptx_bytes", lambda *_: b"pptx")
    monkeypatch.setattr(ppt_export, "build_industry_xlsx_bytes", lambda *_: b"xlsx")
    monkeypatch.setattr(
        revision_export, "build_revision_portfolio_xlsx_bytes", lambda *_: b"portfolio"
    )
    monkeypatch.setattr(
        revision_export, "build_revision_html_bytes", lambda *_: b"html"
    )

    def explode(*_args, **_kwargs):
        raise RuntimeError("openpyxl ausente")

    monkeypatch.setattr(
        revision_export, "build_revision_top100_xlsx_bytes", explode
    )

    payloads, failures = _industry_export_payloads.__wrapped__("assinatura")

    assert set(payloads) == {"pptx", "xlsx", "portfolio", "html"}
    assert set(failures) == {"top100"}
    assert "openpyxl ausente" in failures["top100"]


def test_every_export_button_is_declared_with_a_payload_key() -> None:
    from tabs.tab_industry_study import _INDUSTRY_EXPORT_BUTTONS

    keys = [spec["key"] for spec in _INDUSTRY_EXPORT_BUTTONS]

    assert keys == ["pptx", "xlsx", "portfolio", "top100", "html"]
    for spec in _INDUSTRY_EXPORT_BUTTONS:
        assert spec["label"] and spec["mime"] and spec["widget"]
        assert "{period}" in spec["file_name"]
