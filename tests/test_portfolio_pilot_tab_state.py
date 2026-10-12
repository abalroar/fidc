from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from services.portfolio_store import PortfolioFund, PortfolioRecord
from services.portfolio_structure_ui import _PILOT_CNPJS
from tabs import portfolio_page


PILOT_ID = "7681d350f2994945ada0590b0e3703c2"
MELI_ID = "47b0eb1b7bea42ef85233f9b1186129c"


def _portfolio() -> PortfolioRecord:
    return PortfolioRecord(
        id=PILOT_ID, name="Cloudwalk", created_at="2026-10-11", updated_at="2026-10-11",
        funds=tuple(PortfolioFund(cnpj=cnpj, display_name=cnpj) for cnpj in sorted(_PILOT_CNPJS)),
    )


APP = '''
import streamlit as st
from services.portfolio_store import PortfolioFund, PortfolioRecord
from tabs.portfolio_page import _render_portfolio_view_tabs, _render_scoped_views, _structure_scope_labels, PortfolioAnalysisScope, PORTFOLIO_VIEW_TABS

portfolio = PortfolioRecord.from_dict(PORTFOLIO_DATA)
root_key = f"portfolio_analysis_view::{portfolio.id}"
scope_key = f"portfolio_structure_scope::{portfolio.id}"
def choose(key, label):
    st.session_state[key] = label
st.button("Abrir fundo B", key="select_b", on_click=choose, args=(scope_key,"Fundo B"))
st.button("Abrir Rentabilidade", key="select_returns", on_click=choose, args=(root_key,"Rentabilidade"))
page = st.radio("Página", ("análise", "outra"), key="page")
selection = st.radio("Escopos", ("ambos", "somente A", "somente B"), key="selection")
st.session_state["rendered_scopes"] = []
st.session_state["rendered_views"] = []
if page == "análise":
    scopes = tuple(PortfolioAnalysisScope(value=x, label=f"Fundo {x}", kind="fund", cnpj=x, dashboard=None)
        for x in ("A", "B") if selection=="ambos" or selection==f"somente {x}")
    def render(scope):
        st.session_state["rendered_scopes"].append(scope.value)
        st.radio(f"Visão {scope.value}", ("R$", "%"), key=f"pl_view_{scope.value}")
    for label, container in zip(PORTFOLIO_VIEW_TABS, _render_portfolio_view_tabs(portfolio)):
        with container:
            st.session_state["rendered_views"].append(label)
            if label=="Estrutura":
                _render_scoped_views(scopes,render,key=scope_key)
            else:
                st.write(label)
'''


def _app_source(portfolio_id: str) -> str:
    if portfolio_id == PILOT_ID:
        portfolio = _portfolio()
    else:
        portfolio = PortfolioRecord(
            id=MELI_ID, name="MELI (FIDC Sellers I, II e III)",
            created_at="2026-04-22", updated_at="2026-04-22",
            funds=tuple(PortfolioFund(cnpj=cnpj, display_name=name) for cnpj, name in (
                ("50473039000102", "SELLER FIDC SEGMENTO MEIOS DE PAGAMENTO DE RESPONSABILIDADE LIMITADA"),
                ("55471753000177", "SELLER II FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS SEGMENTO MEIOS DE PAGAMENTO RESP LTDA"),
                ("63572282000111", "SELLER 3 FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS SEGMENTO MEIOS DE PAGAMENTO DE RESP LIMITADA"),
            )),
        )
    return APP.replace("PORTFOLIO_DATA", repr(portfolio.to_dict()))


def _assert_ok(app: AppTest) -> None:
    assert not app.exception, [exception.message for exception in app.exception]


@pytest.mark.parametrize("portfolio_id", (PILOT_ID, MELI_ID))
def test_portfolios_retain_view_fund_and_radio_after_reruns_and_navigation(portfolio_id: str) -> None:
    root_key = f"portfolio_analysis_view::{portfolio_id}"
    scope_key = f"portfolio_structure_scope::{portfolio_id}"
    app = AppTest.from_string(_app_source(portfolio_id)).run()
    _assert_ok(app)
    app.button(key="select_b").click().run()
    _assert_ok(app)
    assert app.session_state[scope_key] == "Fundo B"
    app.radio(key="pl_view_B").set_value("%").run()
    _assert_ok(app)
    assert app.session_state[scope_key] == "Fundo B"
    assert app.session_state["pl_view_B"] == "%"
    app.button(key="select_returns").click().run()
    _assert_ok(app)
    assert app.session_state[root_key] == "Rentabilidade"
    assert app.session_state[scope_key] == "Fundo B"
    assert app.session_state["rendered_scopes"] == ["A", "B"]
    assert app.session_state["rendered_views"] == list(portfolio_page.PORTFOLIO_VIEW_TABS)
    app.run()
    _assert_ok(app)
    assert app.session_state[root_key] == "Rentabilidade"
    assert app.session_state[scope_key] == "Fundo B"
    app.radio(key="page").set_value("outra").run()
    _assert_ok(app)
    assert root_key not in app.session_state.filtered_state
    app.radio(key="page").set_value("análise").run()
    _assert_ok(app)
    assert app.session_state[root_key] == "Rentabilidade"
    assert app.session_state[scope_key] == "Fundo B"


@pytest.mark.parametrize("portfolio_id", (PILOT_ID, MELI_ID))
def test_removed_scope_is_sanitized_without_reinstating_the_removed_selection(portfolio_id: str) -> None:
    scope_key = f"portfolio_structure_scope::{portfolio_id}"
    app = AppTest.from_string(_app_source(portfolio_id)).run()
    app.button(key="select_b").click().run()
    _assert_ok(app)
    assert app.session_state[scope_key] == "Fundo B"
    app.radio(key="selection").set_value("somente A").run()
    _assert_ok(app)
    assert app.session_state[f"{scope_key}::selection"] == "Fundo A"
    assert app.session_state["rendered_scopes"] == ["A"]
    app.radio(key="selection").set_value("ambos").run()
    _assert_ok(app)
    assert app.session_state[scope_key] == "Fundo A"
    assert app.session_state["rendered_scopes"] == ["A", "B"]


def test_all_portfolios_use_stable_tabs_and_unkeyed_scope_tabs_keep_the_existing_api(monkeypatch) -> None:
    tabs = Mock(return_value=(nullcontext(), nullcontext()))
    monkeypatch.setattr(portfolio_page.st, "tabs", tabs)
    monkeypatch.setattr(portfolio_page.st, "session_state", {})
    portfolio_page._render_portfolio_view_tabs(replace(_portfolio(), id="other"))
    tabs.assert_called_once_with(
        portfolio_page.PORTFOLIO_VIEW_TABS,
        key="portfolio_analysis_view::other", on_change="rerun",
    )
    tabs.reset_mock()
    scopes = tuple(SimpleNamespace(label=label) for label in ("Fundo A", "Fundo B"))
    renderer = Mock()
    portfolio_page._render_scoped_views(scopes, renderer)
    tabs.assert_called_once_with(["Fundo A", "Fundo B"])
    assert [call.args[0] for call in renderer.call_args_list] == list(scopes)


def test_duplicate_short_names_keep_distinct_cnpj_labels_after_scope_filter_changes() -> None:
    source = _app_source(MELI_ID)
    source = source.replace('args=(scope_key,"Fundo B")', 'args=(scope_key,"Seller · B")')
    source = source.replace('label=f"Fundo {x}"', 'label="Seller"')
    source = source.replace(
        '_render_scoped_views(scopes,render,key=scope_key)',
        '_render_scoped_views(scopes,render,key=scope_key, labels_by_value=_structure_scope_labels('
        'tuple(PortfolioAnalysisScope(value=x, label="Seller", kind="fund", cnpj=x, dashboard=None) for x in ("A", "B"))))',
    )
    scope_key = f"portfolio_structure_scope::{MELI_ID}"
    app = AppTest.from_string(source).run()
    _assert_ok(app)
    app.button(key="select_b").click().run()
    _assert_ok(app)
    assert app.session_state[scope_key] == "Seller · B"
    app.radio(key="selection").set_value("somente B").run()
    _assert_ok(app)
    assert app.session_state[f"{scope_key}::selection"] == "Seller · B"
    app.radio(key="selection").set_value("ambos").run()
    _assert_ok(app)
    assert app.session_state[scope_key] == "Seller · B"
    assert app.session_state["rendered_scopes"] == ["A", "B"]


@pytest.mark.parametrize("portfolio_id", (PILOT_ID, MELI_ID))
def test_structure_reuses_approved_components_and_order_for_each_portfolio(monkeypatch, portfolio_id: str) -> None:
    portfolio = replace(_portfolio(), id=portfolio_id)
    dashboard = SimpleNamespace(latest_competencia="2026-08")
    scope = portfolio_page.PortfolioAnalysisScope(
        value="fund::50473039000102", label="Seller", kind="fund", cnpj="50473039000102", dashboard=dashboard,
    )
    analysis = SimpleNamespace(
        scopes=(scope,), outputs=SimpleNamespace(metadata={"display_period_label": "Set/25 – Ago/26"}),
        dashboard_errors={},
    )
    period = SimpleNamespace(label="Out/25 – Set/26")
    monkeypatch.setattr(portfolio_page.st, "container", Mock(side_effect=lambda **kwargs: nullcontext()))
    monkeypatch.setattr(portfolio_page.st, "expander", Mock(side_effect=lambda *args, **kwargs: nullcontext()))
    monkeypatch.setattr(portfolio_page.st, "html", Mock())
    monkeypatch.setattr(portfolio_page.st, "markdown", Mock())
    monkeypatch.setattr(portfolio_page.st, "caption", Mock())
    monkeypatch.setattr(portfolio_page.st, "session_state", {})
    components = Mock()
    for owner, name, label in (
        (portfolio_page.monitoring_tab, "render_portfolio_cockpit_snapshot", "cockpit"),
        (portfolio_page.ime_tab, "_render_financial_snapshot_cards", "cards"),
        (portfolio_page.ime_tab, "_render_structural_risk_section", "chart"),
        (portfolio_page.somatorio_tab, "_render_wide_table_html", "table"),
        (portfolio_page.ime_tab, "_render_calculation_memory_section", "memory"),
    ):
        component = Mock(return_value="<table></table>")
        monkeypatch.setattr(owner, name, component)
        components.attach_mock(component, label)
    base = object()
    monkeypatch.setattr(portfolio_page, "_base_scope_lookup", Mock(return_value={scope.value: SimpleNamespace(wide_df=base)}))
    monkeypatch.setattr(portfolio_page.somatorio_tab, "_display_wide_table", Mock(return_value=base))

    portfolio_page._render_structure_tab(
        analysis=analysis, selected_scopes=(scope,), selected_portfolio=portfolio, period=period,
    )

    assert [call[0] for call in components.mock_calls] == ["cockpit", "cards", "chart", "table", "memory"]
    components.cockpit.assert_called_once_with(
        period=period, selected_portfolio=portfolio, selected_cnpjs={scope.cnpj},
        context_items=(), portfolio_mode=True,
    )
    components.cards.assert_called_once_with(dashboard, interactive_help=True, portfolio_mode=True, slot_key=scope.value)
    components.chart.assert_called_once_with(
        dashboard, slot_key=f"portfolio_structure::{portfolio_id}::{scope.value}",
        show_return_section=False, responsive_labels=True, portfolio_mode=True,
    )
    components.table.assert_called_once_with(base, accessible=True)
    assert portfolio_page.st.session_state[f"portfolio_structure_scope::{portfolio_id}::selection"] == "Seller"
