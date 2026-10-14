from streamlit.testing.v1 import AppTest


def _app():
    import streamlit as st
    from tabs import tab_fidc_ime

    period, _, _ = tab_fidc_ime.render_period_toolbar(state_prefix="probe")
    st.session_state["probe_result"] = (period.mode, period.start_month.isoformat(), period.end_month.isoformat())


def test_presets_custom_interval_and_return_keep_one_active_period():
    app = AppTest.from_function(_app, default_timeout=30).run()
    assert not app.exception
    mode, start, end = app.session_state["probe_result"]
    assert mode == "preset" and app.session_state["probe_period_preset"] == "12M"

    # A custom interval from the popover replaces the preset and clears its highlight.
    app.button(key="probe_btn_apply_custom").click().run()
    assert not app.exception
    assert app.session_state["probe_result"][0] == "custom"
    assert app.session_state["probe_period_preset"] is None

    # Choosing a preset again returns to the moving window.
    app.button_group(key="probe_period_preset").set_value("24M").run()
    assert not app.exception
    assert app.session_state["probe_result"][0] == "preset"
    assert app.session_state["probe_period_preset"] == "24M"
