from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from services.portfolio_store import PortfolioFund, PortfolioRecord
from services.portfolio_structure_ui import _PILOT_CNPJS
from tabs import portfolio_page


PILOT_ID = "7681d350f2994945ada0590b0e3703c2"
ROOT_KEY = f"portfolio_analysis_view::{PILOT_ID}"
SCOPE_KEY = f"portfolio_structure_scope::{PILOT_ID}"


def _portfolio() -> PortfolioRecord:
    return PortfolioRecord(
        id=PILOT_ID, name="Cloudwalk", created_at="2026-10-11", updated_at="2026-10-11",
        funds=tuple(PortfolioFund(cnpj=cnpj, display_name=cnpj) for cnpj in sorted(_PILOT_CNPJS)),
    )


APP = '''
import streamlit as st
from services.portfolio_store import PortfolioFund, PortfolioRecord
from services.portfolio_structure_ui import _PILOT_CNPJS
from tabs.portfolio_page import _render_portfolio_view_tabs, _render_scoped_views, PortfolioAnalysisScope, PORTFOLIO_VIEW_TABS

pilot_id = "7681d350f2994945ada0590b0e3703c2"
root_key = f"portfolio_analysis_view::{pilot_id}"
scope_key = f"portfolio_structure_scope::{pilot_id}"
portfolio = PortfolioRecord(id=pilot_id, name="Cloudwalk", created_at="2026-10-11", updated_at="2026-10-11",
    funds=tuple(PortfolioFund(cnpj=c, display_name=c) for c in sorted(_PILOT_CNPJS)))
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


def _assert_ok(app: AppTest) -> None:
    assert not app.exception, [exception.message for exception in app.exception]


def test_pilot_retains_view_fund_and_radio_after_reruns_and_navigation() -> None:
    app = AppTest.from_string(APP).run()
    _assert_ok(app)
    app.button(key="select_b").click().run()
    _assert_ok(app)
    assert app.session_state[SCOPE_KEY] == "Fundo B"
    app.radio(key="pl_view_B").set_value("%").run()
    _assert_ok(app)
    assert app.session_state[SCOPE_KEY] == "Fundo B"
    assert app.session_state["pl_view_B"] == "%"
    app.button(key="select_returns").click().run()
    _assert_ok(app)
    assert app.session_state[ROOT_KEY] == "Rentabilidade"
    assert app.session_state[SCOPE_KEY] == "Fundo B"
    assert app.session_state["rendered_scopes"] == ["A", "B"]
    assert app.session_state["rendered_views"] == list(portfolio_page.PORTFOLIO_VIEW_TABS)
    app.run()
    _assert_ok(app)
    assert app.session_state[ROOT_KEY] == "Rentabilidade"
    assert app.session_state[SCOPE_KEY] == "Fundo B"
    app.radio(key="page").set_value("outra").run()
    _assert_ok(app)
    assert ROOT_KEY not in app.session_state.filtered_state
    app.radio(key="page").set_value("análise").run()
    _assert_ok(app)
    assert app.session_state[ROOT_KEY] == "Rentabilidade"
    assert app.session_state[SCOPE_KEY] == "Fundo B"


def test_removed_scope_is_sanitized_without_reinstating_the_removed_selection() -> None:
    app = AppTest.from_string(APP).run()
    app.button(key="select_b").click().run()
    _assert_ok(app)
    assert app.session_state[SCOPE_KEY] == "Fundo B"
    app.radio(key="selection").set_value("somente A").run()
    _assert_ok(app)
    assert app.session_state[f"{SCOPE_KEY}::selection"] == "Fundo A"
    assert app.session_state["rendered_scopes"] == ["A"]
    app.radio(key="selection").set_value("ambos").run()
    _assert_ok(app)
    assert app.session_state[SCOPE_KEY] == "Fundo A"
    assert app.session_state["rendered_scopes"] == ["A", "B"]


def test_other_portfolios_and_unkeyed_scope_tabs_keep_the_existing_api(monkeypatch) -> None:
    tabs = Mock(return_value=(nullcontext(), nullcontext()))
    monkeypatch.setattr(portfolio_page.st, "tabs", tabs)
    portfolio_page._render_portfolio_view_tabs(replace(_portfolio(), id="other"))
    tabs.assert_called_once_with(portfolio_page.PORTFOLIO_VIEW_TABS)
    tabs.reset_mock()
    scopes = tuple(SimpleNamespace(label=label) for label in ("Fundo A", "Fundo B"))
    renderer = Mock()
    portfolio_page._render_scoped_views(scopes, renderer)
    tabs.assert_called_once_with(["Fundo A", "Fundo B"])
    assert [call.args[0] for call in renderer.call_args_list] == list(scopes)
