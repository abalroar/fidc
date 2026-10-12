from streamlit.testing.v1 import AppTest


def _history_controls():
    from types import SimpleNamespace
    from unittest.mock import patch
    import pandas as pd
    import streamlit as st
    from tabs import tab_mercado_livre

    portfolio = st.selectbox("Carteira", ["A", "B"])
    show = st.checkbox("Mostrar controle", value=True)
    st.session_state.setdefault("somatorio_fidcs_display_window", "24M")
    outputs = SimpleNamespace(
        consolidated_monthly=pd.DataFrame({"competencia": [f"{month:02}/2026" for month in range(1, 9)]}),
        metadata={"requested_window_option": "12M"},
    )
    if show:
        with patch.object(tab_mercado_livre, "_filter_outputs_by_competencia_months", side_effect=lambda outputs, **kwargs: kwargs):
            result = tab_mercado_livre._render_loaded_period_window(outputs, state_namespace=portfolio)
        st.session_state["result"] = result


def test_visual_window_survives_basket_switch_and_widget_cleanup_without_affecting_other_pages():
    app = AppTest.from_function(_history_controls).run()
    assert not app.exception
    app.radio[0].set_value("6M").run()
    assert app.session_state["result"]["mode"] == "6M"
    app.selectbox[0].set_value("B").run()
    assert app.session_state["result"]["mode"] == "12M"
    app.selectbox[0].set_value("A").run()
    assert app.radio[0].value == "6M"
    app.checkbox[0].uncheck().run()
    app.checkbox[0].check().run()
    assert app.radio[0].value == "6M"
    assert app.session_state["somatorio_fidcs_display_window"] == "24M"
    assert not app.exception
