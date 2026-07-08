from __future__ import annotations

from html import escape

import streamlit as st

from tabs.tab_fidc_book import render_tab_fidc_book
from tabs.tab_cloudwalk_financial_cost import render_tab_cloudwalk_financial_cost
from tabs.tab_fidc_credit_strategy import render_tab_fidc_credit_strategy
from tabs import tab_fidc_ime as ime_tab
from tabs import tab_deep_dive as deep_dive_tab
from tabs import tab_fidc_monitoring as monitoring_tab
from tabs import tab_mercado_livre as somatorio_tab
from tabs.portfolio_page import render_portfolio_center_page
from tabs.tab_industry_study import render_tab_industry_study
from tabs.tab_modelo_fidc import render_tab_modelo_fidc


_APP_BASE_CSS = """
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
    margin: 1.15rem auto 1.75rem auto;
    max-width: 64rem;
    text-align: center;
}

.fidc-app-kicker {
    color: #ff5a00;
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    line-height: 1.2;
    margin-bottom: 0.3rem;
    text-transform: uppercase;
}

.fidc-app-title {
    color: #12171d !important;
    font-size: clamp(3.1rem, 6.2vw, 4.45rem) !important;
    font-weight: 300 !important;
    letter-spacing: -0.045em !important;
    line-height: 0.98 !important;
    margin: 0 !important;
}

.fidc-app-author {
    color: #9aa3ad !important;
    font-size: 1.02rem !important;
    font-weight: 300 !important;
    letter-spacing: 0 !important;
    line-height: 1.3 !important;
    margin-top: 0.7rem !important;
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
    gap: 2rem;
    overflow-x: auto;
    scrollbar-width: thin;
}

/* Radio buttons → compact chips (period selector & portfolio view toggle) */
[data-testid="stRadio"] [role="radiogroup"],
[data-testid="stRadio"] [data-baseweb="radio-group"] {
    display: flex !important;
    gap: 0.45rem !important;
    flex-wrap: wrap;
    align-items: center;
}

[data-testid="stRadio"] [role="radiogroup"] > label,
[data-testid="stRadio"] [data-baseweb="radio-group"] > label {
    display: inline-flex !important;
    align-items: center !important;
    background: transparent !important;
    border: 0 !important;
    cursor: pointer !important;
    margin: 0 !important;
    padding: 0 !important;
    white-space: nowrap !important;
}

/* Hide the native radio circle and style the text node as the visible chip. */
[data-testid="stRadio"] [role="radiogroup"] > label > div:first-child,
[data-testid="stRadio"] [data-baseweb="radio-group"] > label > div:first-child {
    display: none !important;
}

[data-testid="stRadio"] [role="radiogroup"] > label > input[type="radio"],
[data-testid="stRadio"] [data-baseweb="radio-group"] > label > input[type="radio"] {
    height: 0 !important;
    opacity: 0 !important;
    pointer-events: none !important;
    position: absolute !important;
    width: 0 !important;
}

[data-testid="stRadio"] [role="radiogroup"] > label > input[type="radio"] + div,
[data-testid="stRadio"] [data-baseweb="radio-group"] > label > input[type="radio"] + div {
    align-items: center !important;
    background: #f7f8fa !important;
    border: 1.5px solid #dde3ea !important;
    border-radius: 999px !important;
    color: #5a6478 !important;
    display: inline-flex !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    line-height: 1.6 !important;
    padding: 0.2rem 0.9rem !important;
    transition: background 0.12s, border-color 0.12s, color 0.12s !important;
}

[data-testid="stRadio"] [role="radiogroup"] > label:hover > input[type="radio"] + div,
[data-testid="stRadio"] [data-baseweb="radio-group"] > label:hover > input[type="radio"] + div {
    border-color: #ff5a00 !important;
    color: #ff5a00 !important;
    background: #fff4ed !important;
}

/* Selected chip */
[data-testid="stRadio"] [role="radiogroup"] > label > input[type="radio"]:checked + div,
[data-testid="stRadio"] [data-baseweb="radio-group"] > label > input[type="radio"]:checked + div {
    background: #ff5a00 !important;
    border-color: #ff5a00 !important;
    color: #ffffff !important;
    font-weight: 600 !important;
}

[data-testid="stRadio"] [role="radiogroup"] > label > input[type="radio"]:checked + div *,
[data-testid="stRadio"] [data-baseweb="radio-group"] > label > input[type="radio"]:checked + div * {
    color: #ffffff !important;
}

.fidc-main-nav {
    border-bottom: 1px solid #dde3ea;
    display: flex;
    gap: 0;
    margin: 0.25rem 0 1rem 0;
    overflow-x: auto;
    scrollbar-width: thin;
}

.fidc-main-nav a,
.fidc-main-nav a:visited {
    border-bottom: 2px solid transparent;
    color: #2f3a48;
    display: inline-flex;
    font-size: 0.95rem;
    font-weight: 500;
    line-height: 2.45rem;
    padding: 0 1.05rem;
    text-decoration: none !important;
    white-space: nowrap;
}

.fidc-main-nav a:hover,
.fidc-main-nav a:focus {
    border-bottom-color: #ffb180;
    color: #ff5a00;
    outline: none;
}

.fidc-main-nav a.fidc-main-nav-active,
.fidc-main-nav a.fidc-main-nav-active:visited {
    border-bottom-color: #ff5a00;
    color: #ff5a00;
    font-weight: 650;
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
    color: #ff5a00;
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

    .fidc-main-nav {
        flex-wrap: wrap;
        overflow-x: visible;
    }

    .fidc-main-nav a,
    .fidc-main-nav a:visited {
        font-size: 0.88rem;
        line-height: 2.15rem;
        padding: 0 0.55rem;
    }

    .fidc-app-title {
        font-size: 2.65rem !important;
    }

    .fidc-app-subtitle {
        font-size: 0.94rem;
    }
}
"""


def _strip_style_tags(css: str) -> str:
    return css.replace("<style>", "").replace("</style>", "").strip()


_APP_CSS = (
    "<style>\n"
    + "\n\n".join(
        _strip_style_tags(block)
        for block in (
            _APP_BASE_CSS,
            ime_tab._FIDC_REPORT_CSS,
            somatorio_tab._MERCADO_LIVRE_UI_CSS,
            monitoring_tab._CSS,
            deep_dive_tab._CSS,
        )
    )
    + "\n</style>"
)


st.set_page_config(page_title="tomaconta FIDCs", page_icon="📊", layout="wide")

st.markdown(_APP_CSS, unsafe_allow_html=True)
st.markdown(
    """
    <div class="fidc-app-header">
      <div class="fidc-app-title" role="heading" aria-level="1">tomaconta fidcs</div>
      <div class="fidc-app-author">por matheus prates, cfa</div>
    </div>
    """,
    unsafe_allow_html=True,
)

_MAIN_SECTIONS = (
    ("sobre", "Sobre"),
    ("industria", "Indústria"),
    ("carteira", "Carteira"),
    ("regulamentos", "Regulamentos"),
    ("estrategia", "Estratégia"),
    ("cloudwalk", "Cloudwalk"),
    ("glossario", "Glossário"),
    ("modelagem", "Modelagem"),
)
_MAIN_SECTION_LABELS = dict(_MAIN_SECTIONS)
_DEFAULT_SECTION = "sobre"


def _current_main_section() -> str:
    raw_value = st.query_params.get("section", _DEFAULT_SECTION)
    if isinstance(raw_value, list):
        raw_value = raw_value[-1] if raw_value else _DEFAULT_SECTION
    section = str(raw_value).strip().lower()
    return section if section in _MAIN_SECTION_LABELS else _DEFAULT_SECTION


def _render_main_nav(selected_section: str) -> None:
    links = []
    for slug, label in _MAIN_SECTIONS:
        active_class = " fidc-main-nav-active" if slug == selected_section else ""
        current_attr = ' aria-current="page"' if slug == selected_section else ""
        links.append(
            f'<a class="fidc-main-nav-link{active_class}" href="?section={escape(slug, quote=True)}"{current_attr}>'
            f"{escape(label)}</a>"
        )
    st.markdown(f"<nav class='fidc-main-nav' aria-label='Seções principais'>{''.join(links)}</nav>", unsafe_allow_html=True)


selected_section = _current_main_section()
_render_main_nav(selected_section)

if selected_section == "industria":
    render_tab_industry_study()
elif selected_section == "carteira":
    _render_period_selector = getattr(ime_tab, "render_period_selector", None) or getattr(ime_tab, "_render_period_selector")
    period = _render_period_selector(state_prefix="ime_global")
    render_portfolio_center_page(period=period)
elif selected_section == "regulamentos":
    deep_dive_tab.render_tab_deep_dive()
elif selected_section == "estrategia":
    render_tab_fidc_credit_strategy()
elif selected_section == "cloudwalk":
    render_tab_cloudwalk_financial_cost()
elif selected_section == "modelagem":
    render_tab_modelo_fidc()
elif selected_section == "glossario":
    render_tab_fidc_book()
elif selected_section == "sobre":
    try:
        from tabs.tab_about import render_tab_about

        render_tab_about()
    except ModuleNotFoundError as exc:
        st.error("A tela Sobre ainda não foi carregada corretamente neste deploy.")
        st.caption(f"Módulo ausente: {exc.name}. As demais abas continuam disponíveis.")
    except Exception as exc:  # noqa: BLE001
        st.error("A tela Sobre encontrou um erro, mas as demais abas continuam disponíveis.")
        st.caption(f"Detalhe técnico: {type(exc).__name__}: {exc}")
