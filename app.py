from __future__ import annotations

import streamlit as st

from tabs.tab_fidc_book import render_tab_fidc_book
from tabs.tab_fidc_ime import render_tab_fidc_ime
from tabs.tab_modelo_fidc import render_tab_modelo_fidc


st.set_page_config(page_title="tomaconta FIDCs", page_icon="📊", layout="wide")

st.title("tomaconta FIDCs")
st.caption("Monitoramento de risco por IME, modelo econômico e base de conhecimento regulatória em uma única plataforma.")


tab_informes, tab_modelo, tab_book = st.tabs(
    ["tomaconta FIDCs", "Modelo FIDC", "Glossário / Book FIDC"]
)

with tab_informes:
    render_tab_fidc_ime()

with tab_modelo:
    render_tab_modelo_fidc()

with tab_book:
    render_tab_fidc_book()
