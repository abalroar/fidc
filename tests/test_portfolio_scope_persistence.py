from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
from streamlit.testing.v1 import AppTest

from tabs import portfolio_page


FUND_A = "33254370000104"
FUND_B = "37511828000114"


def _scope_persistence_app():
    from types import SimpleNamespace
    from unittest.mock import patch

    import pandas as pd
    import streamlit as st

    from tabs import portfolio_page, tab_fidc_ime

    portfolio_id = st.selectbox("Carteira de teste", ["A", "B"], key="test_portfolio")
    show = st.checkbox("Mostrar página", value=True, key="test_show")
    remove_class = st.checkbox("Retirar classe antiga", key="test_remove_class")
    root_key = f"portfolio_analysis_view::{portfolio_id}"

    def choose(label):
        st.session_state[root_key] = label

    st.button("Abrir Estrutura", key="test_structure", on_click=choose, args=("Estrutura",))
    st.button("Abrir Rentabilidade", key="test_returns", on_click=choose, args=("Rentabilidade",))
    if not show:
        return
    portfolio_page._restore_portfolio_widget_choices(portfolio_id)
    cnpjs = ("33254370000104", "37511828000114")
    labels = ["Sênior 1", "Mezzanino 1", "Subordinada 1"]
    if remove_class:
        labels = labels[:2]
    dates = pd.date_range("2026-01-01", periods=2, freq="MS")

    def dashboard(name):
        history = pd.DataFrame([
            {"competencia": date.strftime("%m/%Y"), "competencia_dt": date,
             "class_label": label, "retorno_mensal_pct": 1.0}
            for date in dates for label in labels
        ])
        quota = pd.DataFrame({
            "competencia": ["02/2026"] * 3,
            "competencia_dt": [dates[-1]] * 3,
            "class_macro_label": ["Sênior", "Mezzanino", "Subordinada"],
            "pl": [88.0, 10.0, 2.0],
        })
        return SimpleNamespace(
            fund_info={"nome_fundo": name}, latest_competencia="02/2026",
            quota_pl_history_df=quota,
            subordination_history_df=pd.DataFrame({"competencia": ["02/2026"], "subordinacao_pct": [12.0]}),
            return_history_df=history, return_summary_df=pd.DataFrame(),
        )

    scopes = (
        portfolio_page.PortfolioAnalysisScope("consolidado", "Consolidado", "consolidated", "", dashboard("Consolidado")),
        *(portfolio_page.PortfolioAnalysisScope(f"fund::{cnpj}", f"Fundo {index}", "fund", cnpj, dashboard(f"Fundo {index}"))
          for index, cnpj in enumerate(cnpjs, start=1)),
    )
    with st.expander("Fundos da comparação"):
        compared = portfolio_page._render_scope_selector(scopes=scopes, portfolio_id=portfolio_id)
    active = portfolio_page._render_active_portfolio_scope(compared, portfolio_id)
    st.session_state["test_comparison_values"] = tuple(scope.value for scope in compared)
    st.session_state["test_visible_values"] = (active.value,)
    outputs = SimpleNamespace(fund_monthly={
        cnpj: pd.DataFrame({"fund_name": [f"Fundo {index}"]})
        for index, cnpj in enumerate(cnpjs, start=1)
    })
    analysis = SimpleNamespace(scopes=scopes, outputs=outputs, monitor_outputs=None)
    portfolio = SimpleNamespace(id=portfolio_id)
    tabs = portfolio_page._render_portfolio_view_tabs(portfolio)
    if tabs[0].open:
        with tabs[0]:
            tab_fidc_ime._render_structural_risk_section(
                active.dashboard, slot_key=f"portfolio_structure::{portfolio_id}::{active.value}",
                portfolio_mode=True, show_return_section=False,
            )
    if tabs[3].open:
        with tabs[3], patch.object(portfolio_page.credit_tab, "_render_fund_return_table"):
            portfolio_page._render_returns_tab(
                analysis=analysis, selected_scopes=(active,), selected_portfolio=portfolio,
            )
    portfolio_page._remember_portfolio_widget_choices(portfolio_id)


def _ok(app):
    assert not app.exception, [error.message for error in app.exception]


def _scale_scope_app():
    import json
    from pathlib import Path

    import streamlit as st

    from services.fund_name_display import short_fund_name
    from services.portfolio_store import PortfolioRecord
    from tabs import portfolio_page

    catalog_path = Path(portfolio_page.__file__).resolve().parents[1] / "portfolios.json"
    catalog = json.loads(catalog_path.read_text())
    data = next(row for row in catalog["portfolios"] if row["id"] == "carteira1_fidc_industry_20260731")
    portfolio = PortfolioRecord.from_dict(data)
    # Only identities enter this UI fixture; no financial dataset is constructed.
    scopes = (
        portfolio_page.PortfolioAnalysisScope("consolidado", "Consolidado", "consolidated", "", None),
        *(portfolio_page.PortfolioAnalysisScope(
            f"fund::{fund.cnpj}", short_fund_name(fund.display_name), "fund", fund.cnpj, None,
        ) for fund in portfolio.funds),
    )
    selected = portfolio_page._render_scope_selector(scopes=scopes, portfolio_id=portfolio.id)
    active = portfolio_page._render_active_portfolio_scope(selected, portfolio.id)
    portfolio_page._render_portfolio_view_tabs(portfolio)
    st.session_state["test_catalog_cnpjs"] = tuple(fund.cnpj for fund in portfolio.funds)
    st.session_state["test_scale_options"] = tuple(scope.value for scope in selected)
    st.session_state["test_scale_active"] = active.value


def test_scope_detail_preserves_the_complete_comparison_and_each_funds_pl_mode():
    app = AppTest.from_function(_scope_persistence_app).run()
    _ok(app)
    expected = ("consolidado", f"fund::{FUND_A}", f"fund::{FUND_B}")
    app.selectbox(key="portfolio_active_scope::A").set_value(f"fund::{FUND_A}").run()
    key_a = f"pl_view_portfolio_structure::A::fund::{FUND_A}"
    app.radio(key=key_a).set_value("% do total por competência").run()
    app.selectbox(key="portfolio_active_scope::A").set_value(f"fund::{FUND_B}").run()
    _ok(app)
    assert app.session_state["test_comparison_values"] == expected
    assert app.session_state["test_visible_values"] == (f"fund::{FUND_B}",)
    key_b = f"pl_view_portfolio_structure::A::fund::{FUND_B}"
    assert app.radio(key=key_b).value == "Valores absolutos (R$)"
    app.selectbox(key="portfolio_active_scope::A").set_value(f"fund::{FUND_A}").run()
    _ok(app)
    assert app.radio(key=key_a).value == "% do total por competência"
    assert app.session_state["test_comparison_values"] == expected


def test_return_classes_scope_and_theme_survive_lazy_tabs_basket_switch_and_page_cleanup():
    app = AppTest.from_function(_scope_persistence_app).run()
    app.selectbox(key="portfolio_active_scope::A").set_value(f"fund::{FUND_A}").run()
    app.button(key="test_returns").click().run()
    _ok(app)
    class_key = f"return_labels_portfolio_returns::A::{FUND_A}"
    app.multiselect(key=class_key).set_value(["Sênior 1"]).run()
    # A single active fund no longer produces the second rentability selector.
    assert not any(widget.label == "Fundo da rentabilidade" for widget in app.selectbox)
    app.button(key="test_structure").click().run()
    assert not any(widget.key == class_key for widget in app.multiselect)
    app.button(key="test_returns").click().run()
    _ok(app)
    assert app.multiselect(key=class_key).value == ["Sênior 1"]
    app.selectbox(key="test_portfolio").set_value("B").run()
    _ok(app)
    assert app.session_state["portfolio_active_scope::B"] == "consolidado"
    app.selectbox(key="test_portfolio").set_value("A").run()
    _ok(app)
    assert app.session_state["portfolio_active_scope::A"] == f"fund::{FUND_A}"
    assert app.session_state["portfolio_analysis_view::A"] == "Rentabilidade"
    assert app.multiselect(key=class_key).value == ["Sênior 1"]
    app.checkbox(key="test_show").uncheck().run()
    app.checkbox(key="test_show").check().run()
    _ok(app)
    assert app.session_state["portfolio_active_scope::A"] == f"fund::{FUND_A}"
    assert app.session_state["portfolio_analysis_view::A"] == "Rentabilidade"
    assert app.multiselect(key=class_key).value == ["Sênior 1"]


def test_return_class_removed_from_current_data_is_reconciled_without_resurrecting_it():
    app = AppTest.from_function(_scope_persistence_app).run()
    app.selectbox(key="portfolio_active_scope::A").set_value(f"fund::{FUND_A}").run()
    app.button(key="test_returns").click().run()
    class_key = f"return_labels_portfolio_returns::A::{FUND_A}"
    app.multiselect(key=class_key).set_value(["Sênior 1", "Subordinada 1"]).run()
    app.button(key="test_structure").click().run()
    app.checkbox(key="test_remove_class").check().run()
    app.button(key="test_returns").click().run()
    _ok(app)
    assert app.multiselect(key=class_key).value == ["Sênior 1"]
    assert "Subordinada 1" not in app.multiselect(key=class_key).options


def test_removed_active_fund_stays_sanitized_when_comparison_is_expanded_again():
    app = AppTest.from_function(_scope_persistence_app).run()
    app.selectbox(key="portfolio_active_scope::A").set_value(f"fund::{FUND_B}").run()
    app.toggle(key="portfolio_analysis_show_all::A").set_value(False).run()
    app.multiselect(key="portfolio_analysis_scopes::A").set_value([f"fund::{FUND_A}"]).run()
    _ok(app)
    assert app.session_state["test_visible_values"] == (f"fund::{FUND_A}",)


def test_real_carteira_101_uses_exact_saved_ids_and_one_scope_selector_without_fund_tabs():
    import json
    from pathlib import Path

    catalog_path = Path(portfolio_page.__file__).resolve().parents[1] / "portfolios.json"
    original = catalog_path.read_bytes()
    catalog = json.loads(original)
    portfolio = next(row for row in catalog["portfolios"] if row["id"] == "carteira1_fidc_industry_20260731")
    cnpjs = tuple(fund["cnpj"] for fund in portfolio["funds"])
    assert len(cnpjs) == 101
    app = AppTest.from_function(_scale_scope_app).run()
    _ok(app)
    assert app.session_state["test_catalog_cnpjs"] == cnpjs
    assert app.session_state["test_scale_options"] == ("consolidado", *(f"fund::{cnpj}" for cnpj in cnpjs))
    selector = app.selectbox(key="portfolio_active_scope::carteira1_fidc_industry_20260731")
    assert len(selector.options) == 102
    assert len(app.tabs) == len(portfolio_page.PORTFOLIO_VIEW_TABS)
    assert tuple(tab.label for tab in app.tabs) == portfolio_page.PORTFOLIO_VIEW_TABS
    selector.set_value(f"fund::{cnpjs[-1]}").run()
    _ok(app)
    assert app.session_state["test_scale_active"] == f"fund::{cnpjs[-1]}"
    assert len(app.tabs) == len(portfolio_page.PORTFOLIO_VIEW_TABS)
    assert catalog_path.read_bytes() == original
    app.toggle(key="portfolio_analysis_show_all::A").set_value(True).run()
    _ok(app)
    assert app.session_state["test_visible_values"] == (f"fund::{FUND_A}",)


def test_one_scope_detail_keeps_every_compared_fund_in_duration(monkeypatch):
    scopes = (
        portfolio_page.PortfolioAnalysisScope("consolidado", "Consolidado", "consolidated", "", None),
        portfolio_page.PortfolioAnalysisScope(f"fund::{FUND_A}", "Fundo A", "fund", FUND_A, None),
        portfolio_page.PortfolioAnalysisScope(f"fund::{FUND_B}", "Fundo B", "fund", FUND_B, None),
    )
    a, b, consolidated = (pd.DataFrame({"value": [value]}) for value in (1.0, 2.0, 3.0))
    analysis = SimpleNamespace(monitor_outputs=SimpleNamespace(
        fund_monitor={FUND_A: a, FUND_B: b}, consolidated_monitor=consolidated,
    ))
    monkeypatch.setattr(portfolio_page, "_render_scoped_views", Mock())
    monkeypatch.setattr(portfolio_page.st, "markdown", Mock())
    monkeypatch.setattr(portfolio_page.st, "caption", Mock())
    monkeypatch.setattr(portfolio_page.st, "altair_chart", Mock())
    duration = Mock(return_value="chart")
    monkeypatch.setattr(portfolio_page, "duration_chart", duration)
    portfolio_page._render_credit_term_tab(
        analysis=analysis, selected_scopes=(scopes[1],),
        selected_portfolio=SimpleNamespace(id="A"), comparison_scopes=scopes,
    )
    assert duration.call_args.args[0] is consolidated
    assert set(duration.call_args.args[1]) == {FUND_A, FUND_B}


def test_one_scope_detail_keeps_the_complete_cockpit_basket(monkeypatch):
    scopes = (
        portfolio_page.PortfolioAnalysisScope("consolidado", "Consolidado", "consolidated", "", None),
        portfolio_page.PortfolioAnalysisScope(f"fund::{FUND_A}", "Fundo A", "fund", FUND_A, None),
        portfolio_page.PortfolioAnalysisScope(f"fund::{FUND_B}", "Fundo B", "fund", FUND_B, None),
    )
    monkeypatch.setattr(portfolio_page.st, "container", lambda **kwargs: nullcontext())
    monkeypatch.setattr(portfolio_page.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(portfolio_page.st, "html", Mock())
    monkeypatch.setattr(portfolio_page.st, "markdown", Mock())
    monkeypatch.setattr(portfolio_page, "_render_scoped_views", Mock())
    monkeypatch.setattr(portfolio_page, "_base_scope_lookup", lambda **kwargs: {})
    cockpit = Mock()
    monkeypatch.setattr(portfolio_page.monitoring_tab, "render_portfolio_cockpit_snapshot", cockpit)
    analysis = SimpleNamespace(scopes=scopes, outputs=SimpleNamespace(metadata={}), dashboard_errors={})
    portfolio_page._render_structure_tab(
        analysis=analysis, selected_scopes=(scopes[1],), selected_portfolio=SimpleNamespace(id="A"),
        period=SimpleNamespace(label="12M"), comparison_scopes=scopes,
    )
    assert cockpit.call_args.kwargs["selected_cnpjs"] is None
