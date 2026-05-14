from __future__ import annotations

import streamlit as st

from services.ime_period import ImePeriodSelection
from tabs import tab_deep_dive as deep_dive_tab
from tabs import tab_fidc_ime_carteira as carteira_tab
from tabs import tab_fidc_monitoring as monitoring_tab
from tabs import tab_mercado_livre as somatorio_tab


def render_portfolio_center_page(period: ImePeriodSelection) -> None:
    selected_portfolio, load_clicked = carteira_tab.render_portfolio_control_panel(
        load_button_label="Carregar IME",
        load_button_key="portfolio_center_load_ime",
    )
    if selected_portfolio is None:
        st.info("Crie ou selecione uma carteira para iniciar as análises.")
        return

    if load_clicked:
        carteira_tab.load_portfolio_ime_data(selected_portfolio=selected_portfolio, period=period)

    _render_section_toggle(
        title="Aging e visão executiva",
        key="portfolio_center_section_aging",
        default=True,
    )
    if st.session_state.get("portfolio_center_section_aging", True):
        carteira_tab.render_portfolio_aging_analysis(
            selected_portfolio=selected_portfolio,
            period=period,
            section_mode="stacked",
        )

    _render_section_toggle(
        title="Retornos e análise de crédito",
        key="portfolio_center_section_returns",
        default=True,
    )
    if st.session_state.get("portfolio_center_section_returns", True):
        somatorio_tab.render_tab_somatorio_fidcs(
            period=period,
            selected_portfolio=selected_portfolio,
            show_portfolio_controls=False,
            use_tabs=False,
        )

    _render_section_toggle(
        title="Monitoramento e base regulatória",
        key="portfolio_center_section_monitoring",
        default=True,
    )
    if st.session_state.get("portfolio_center_section_monitoring", True):
        monitoring_tab.render_tab_fidc_monitoring(
            period=period,
            selected_portfolio=selected_portfolio,
            show_portfolio_selector=False,
            use_tabs=False,
        )

    _render_section_toggle(
        title="Waterfall e Deep Dives",
        key="portfolio_center_section_deep_dive",
        default=True,
    )
    if st.session_state.get("portfolio_center_section_deep_dive", True):
        deep_dive_tab.render_tab_deep_dive(
            selected_portfolio=selected_portfolio,
            show_portfolio_selector=False,
        )


def _render_section_toggle(*, title: str, key: str, default: bool) -> None:
    st.markdown("<div class='portfolio-section-spacer'></div>", unsafe_allow_html=True)
    st.toggle(title, value=default, key=key)
