from __future__ import annotations

import streamlit as st

from services.ime_period import ImePeriodSelection
from tabs import tab_fidc_ime_carteira as carteira_tab


def render_portfolio_center_page(period: ImePeriodSelection) -> None:
    selected_portfolio, _ = carteira_tab.render_portfolio_control_panel(
        load_button_label="Carregar IME",
        load_button_key="portfolio_center_load_ime",
        show_load_button=False,
    )
    if selected_portfolio is None:
        st.info("Selecione uma carteira.")
        return

    carteira_tab.render_portfolio_aging_analysis(
        selected_portfolio=selected_portfolio,
        period=period,
        section_mode="stacked",
    )
