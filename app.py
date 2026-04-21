from __future__ import annotations

import streamlit as st

from tabs.tab_fidc_book import render_tab_fidc_book
from tabs import tab_fidc_ime as ime_tab
from tabs.tab_fidc_ime_carteira import render_tab_fidc_ime_carteira
from tabs.tab_modelo_fidc import render_tab_modelo_fidc


st.set_page_config(page_title="tomaconta FIDCs", page_icon="📊", layout="wide")

st.title("tomaconta FIDCs")
st.caption("Monitoramento de risco por Informe Mensal, modelo econômico e base de conhecimento regulatória em uma única plataforma.")

# Global period selector — shared across Informe Mensal tabs to keep single-fund and portfolio views in sync.
_render_period_selector = getattr(ime_tab, "render_period_selector", None) or getattr(ime_tab, "_render_period_selector")
period = _render_period_selector(state_prefix="ime_global")


tab_informes, tab_carteira, tab_modelo, tab_book = st.tabs(
    [
        "Informe Mensal Estruturado",
        "Visão Carteira",
        "Modelo FIDC",
        "Glossário FIDC",
    ]
)

with tab_informes:
    ime_tab.render_tab_fidc_ime(period=period)

with tab_carteira:
    render_tab_fidc_ime_carteira(period=period)

with tab_modelo:
    render_tab_modelo_fidc()

with tab_book:
    render_tab_fidc_book()
