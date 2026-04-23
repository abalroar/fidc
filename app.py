from __future__ import annotations

import streamlit as st

from tabs.tab_fidc_book import render_tab_fidc_book
from tabs import tab_fidc_ime as ime_tab
from tabs.tab_fidc_ime_carteira import render_tab_fidc_ime_carteira
from tabs.tab_modelo_fidc import render_tab_modelo_fidc


_APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');

html, body, .stApp, .stMarkdown, .stDataFrame, .stTextInput, .stSelectbox, .stRadio, .stTabs, div, p, label, input, button, h1, h2, h3, h4, h5, h6, li, table, th, td {
    font-family: 'IBM Plex Sans', sans-serif !important;
}

.stApp {
    background: #ffffff;
    color: #2f3a48;
}

.block-container {
    padding-top: 1.25rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
}

.fidc-app-header {
    margin: 0 0 1.1rem 0;
    max-width: 64rem;
}

.fidc-app-kicker {
    color: #1f77b4;
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    line-height: 1.2;
    margin-bottom: 0.3rem;
    text-transform: uppercase;
}

.fidc-app-title {
    color: #283241;
    font-size: 2.45rem;
    font-weight: 700;
    letter-spacing: 0;
    line-height: 1.08;
    margin: 0;
}

.fidc-app-subtitle {
    color: #6f7a87;
    font-size: 0.98rem;
    line-height: 1.55;
    margin-top: 0.65rem;
    max-width: 48rem;
}

.fidc-control-kicker {
    color: #ff5a00;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    line-height: 1.2;
    margin: 0.7rem 0 0.3rem 0;
    text-transform: uppercase;
}

[data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1px solid #dde3ea;
    gap: 0.35rem;
    overflow-x: auto;
    scrollbar-width: thin;
}

[data-testid="stTabs"] [role="tab"] {
    min-height: 2.55rem;
    white-space: nowrap;
}

[data-testid="stTabs"] [role="tab"] p {
    color: #2f3a48;
    font-size: 0.95rem;
}

[data-testid="stTabs"] [aria-selected="true"] p {
    color: #1f77b4;
    font-weight: 600;
}

[data-testid="stForm"] {
    border: 1px solid #dde3ea;
    border-radius: 8px;
    padding: 1rem 1rem 0.85rem 1rem;
}

[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"] > div[data-baseweb="select"] > div,
[data-testid="stMultiSelect"] > div[data-baseweb="select"] > div {
    border-color: #dde3ea;
    border-radius: 8px;
}

@media (max-width: 760px) {
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    .fidc-app-title {
        font-size: 2rem;
    }

    .fidc-app-subtitle {
        font-size: 0.94rem;
    }
}
</style>
"""


st.set_page_config(page_title="tomaconta FIDCs", page_icon="📊", layout="wide")

st.markdown(_APP_CSS, unsafe_allow_html=True)
st.markdown(
    """
    <div class="fidc-app-header">
      <div class="fidc-app-kicker">Plataforma de análise FIDC</div>
      <h1 class="fidc-app-title">tomaconta FIDCs</h1>
      <div class="fidc-app-subtitle">
        Monitoramento de risco por Informe Mensal, modelo econômico e base de conhecimento regulatória em uma única plataforma.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Global period selector — shared across Informe Mensal tabs to keep single-fund and portfolio views in sync.
_render_period_selector = getattr(ime_tab, "render_period_selector", None) or getattr(ime_tab, "_render_period_selector")
st.markdown('<div class="fidc-control-kicker">Período dos Informes Mensais</div>', unsafe_allow_html=True)
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
