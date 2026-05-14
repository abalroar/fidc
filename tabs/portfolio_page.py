from __future__ import annotations

import streamlit as st

from services.ime_period import ImePeriodSelection
from tabs import tab_deep_dive as deep_dive_tab
from tabs import tab_fidc_ime_carteira as carteira_tab
from tabs import tab_fidc_monitoring as monitoring_tab
from tabs import tab_mercado_livre as somatorio_tab


SECTION_AGING = "Aging e visão executiva"
SECTION_RETURNS = "Retornos e análise de crédito"
SECTION_MONITORING = "Monitoramento e base regulatória"
SECTION_DEEP_DIVE = "Waterfall e Deep Dives"
DEFAULT_SECTIONS = (SECTION_AGING, SECTION_RETURNS, SECTION_MONITORING)
ALL_SECTIONS = (*DEFAULT_SECTIONS, SECTION_DEEP_DIVE)


def render_portfolio_center_page(period: ImePeriodSelection) -> None:
    selected_portfolio, _ = carteira_tab.render_portfolio_control_panel(
        load_button_label="Carregar IME",
        load_button_key="portfolio_center_load_ime",
        show_load_button=False,
    )
    if selected_portfolio is None:
        st.info("Crie ou selecione uma carteira para iniciar as análises.")
        return

    selected_sections = st.multiselect(
        "Blocos exibidos",
        options=list(ALL_SECTIONS),
        default=list(DEFAULT_SECTIONS),
        key="portfolio_center_sections",
    )

    if SECTION_AGING in selected_sections:
        carteira_tab.render_portfolio_aging_analysis(
            selected_portfolio=selected_portfolio,
            period=period,
            section_mode="stacked",
        )

    if SECTION_RETURNS in selected_sections:
        somatorio_tab.render_tab_somatorio_fidcs(
            period=period,
            selected_portfolio=selected_portfolio,
            show_portfolio_controls=False,
            use_tabs=False,
            show_guide=False,
        )

    if SECTION_MONITORING in selected_sections:
        monitoring_tab.render_tab_fidc_monitoring(
            period=period,
            selected_portfolio=selected_portfolio,
            show_portfolio_selector=False,
            use_tabs=False,
        )

    if SECTION_DEEP_DIVE in selected_sections:
        deep_dive_tab.render_tab_deep_dive(
            selected_portfolio=selected_portfolio,
            show_portfolio_selector=False,
            show_curation_tools=False,
            compact=True,
        )
