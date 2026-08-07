from __future__ import annotations

import streamlit as st

# Deployment marker: unified exports and industry payload v5 (2026-07-20).

from services.dashboard_ui import dashboard_page, diagnostics_enabled, render_page_header
from tabs.tab_fidc_book import render_tab_fidc_book
from tabs import tab_fidc_ime as ime_tab
from tabs import tab_deep_dive as deep_dive_tab
from tabs import tab_fidc_monitoring as monitoring_tab
from tabs import tab_mercado_livre as somatorio_tab
from tabs.portfolio_page import render_portfolio_center_page
from tabs.tab_estimativas_modelagem import (
    VIEW_CEDENT_COST,
    VIEW_MATURITY_ASSUMPTIONS,
    render_tab_estimativas_modelagem,
)
from tabs.tab_industry_study import render_tab_industry_study


_APP_BASE_CSS = """
@font-face {
    font-family: 'IBM Plex Sans';
    src: url('app/static/fonts/IBMPlexSans-Light-Latin1.woff2') format('woff2');
    font-display: swap;
    font-style: normal;
    font-weight: 300;
}

@font-face {
    font-family: 'IBM Plex Sans';
    src: url('app/static/fonts/IBMPlexSans-Regular-Latin1.woff2') format('woff2');
    font-display: swap;
    font-style: normal;
    font-weight: 400;
}

@font-face {
    font-family: 'IBM Plex Sans';
    src: url('app/static/fonts/IBMPlexSans-Medium-Latin1.woff2') format('woff2');
    font-display: swap;
    font-style: normal;
    font-weight: 500;
}

@font-face {
    font-family: 'IBM Plex Sans';
    src: url('app/static/fonts/IBMPlexSans-SemiBold-Latin1.woff2') format('woff2');
    font-display: swap;
    font-style: normal;
    font-weight: 600;
}

@font-face {
    font-family: 'IBM Plex Sans';
    src: url('app/static/fonts/IBMPlexSans-Bold-Latin1.woff2') format('woff2');
    font-display: swap;
    font-style: normal;
    font-weight: 700;
}

html, body, .stApp, .stMarkdown, .stDataFrame, .stTextInput, .stSelectbox, .stRadio, .stTabs, div, p, label, input, button, h1, h2, h3, h4, h5, h6, li, table, th, td {
    font-family: 'IBM Plex Sans', sans-serif !important;
}

.stApp {
    background: #ffffff;
    color: #2f3a48;
}

.block-container {
    max-width: 1500px;
    padding-top: 0.8rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
}

.fidc-app-header {
    align-items: center;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    justify-content: center;
    margin: 0.35rem auto 1rem;
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
    color: #ff5a00 !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: 2.25rem !important;
    font-weight: 500 !important;
    letter-spacing: 0 !important;
    line-height: 1.08 !important;
    margin: 0 !important;
}

.fidc-app-author {
    color: #7b8590 !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: 0.82rem !important;
    font-weight: 400 !important;
    letter-spacing: 0 !important;
    line-height: 1.3 !important;
    margin: 0 !important;
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

.st-key-fidc_main_section {
    border-bottom: 1px solid #dde3ea;
    margin-bottom: 1rem;
    padding-bottom: 0.3rem;
}

.st-key-fidc_main_section [data-testid="stButtonGroup"] {
    overflow-x: auto;
    padding-bottom: 0.2rem;
    scrollbar-width: thin;
}

.st-key-fidc_main_section [data-baseweb="button-group"] {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    min-width: max-content;
    width: 100%;
}

.st-key-fidc_main_section [data-testid^="stBaseButton-segmented_control"] {
    border-color: transparent !important;
    border-radius: 7px !important;
    color: #2f3a48 !important;
    flex: 1 1 0 !important;
    font-size: 0.93rem !important;
    font-weight: 500 !important;
    min-width: max-content !important;
    min-height: 2.35rem !important;
    padding-inline: 0.85rem !important;
    white-space: nowrap !important;
    width: auto !important;
}

.st-key-fidc_main_section [data-testid^="stBaseButton-segmented_control"] p {
    color: inherit !important;
    font-size: inherit !important;
    font-weight: inherit !important;
}

.st-key-fidc_main_section [data-testid^="stBaseButton-segmented_control"]:hover {
    background: #fff4ed !important;
    color: #ff5a00 !important;
}

.st-key-fidc_main_section [data-testid="stBaseButton-segmented_controlActive"],
.st-key-fidc_main_section [data-testid="stBaseButton-segmented_controlActive"]:hover {
    background: #ff5a00 !important;
    border-color: #ff5a00 !important;
    color: #ffffff !important;
    font-weight: 650 !important;
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

.st-key-ime_global_period_preset [data-testid^="stBaseButton-segmented_control"] {
    min-height: 2.5rem !important;
}

@media (max-width: 760px) {
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    .st-key-fidc_main_section [data-testid^="stBaseButton-segmented_control"] {
        font-size: 0.86rem !important;
        min-height: 2.1rem !important;
        padding-inline: 0.55rem !important;
    }

    .fidc-app-title {
        font-size: 1.8rem !important;
    }

    .fidc-app-subtitle {
        font-size: 0.94rem;
    }
}

@media (min-width: 521px) and (max-width: 850px) {
    .st-key-ime_global_btn_custom [data-testid="stIconMaterial"],
    .st-key-ime_global_btn_preset [data-testid="stIconMaterial"] {
        display: none !important;
    }

    .st-key-ime_global_btn_custom p,
    .st-key-ime_global_btn_preset p {
        white-space: nowrap !important;
    }
}

@media (max-width: 460px) {
    .st-key-ime_global_period_preset [data-baseweb="button-group"] {
        flex-wrap: wrap !important;
    }

    .st-key-ime_global_period_preset [data-testid^="stBaseButton-segmented_control"] {
        flex: 1 1 33.333% !important;
        width: 33.333% !important;
    }

    .st-key-fidc_main_section [data-testid="stButtonGroup"] {
        overflow-x: visible;
    }

    .st-key-fidc_main_section [data-baseweb="button-group"] {
        flex-wrap: wrap !important;
        gap: 0.25rem !important;
        min-width: 0 !important;
    }

    .st-key-fidc_main_section [data-testid^="stBaseButton-segmented_control"] {
        flex: 1 1 calc(50% - 0.25rem) !important;
        min-height: 3rem !important;
        min-width: 0 !important;
        padding: 0.35rem 0.45rem !important;
        width: calc(50% - 0.25rem) !important;
    }

    .st-key-fidc_main_section [data-testid^="stBaseButton-segmented_control"] p {
        line-height: 1.2 !important;
        overflow: visible !important;
        text-overflow: clip !important;
        white-space: normal !important;
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
      <h1 class="fidc-app-title">toma.conta fidcs</h1>
      <p class="fidc-app-author">por matheus prates, cfa</p>
    </div>
    """,
    unsafe_allow_html=True,
)

_MAIN_SECTIONS = (
    ("sobre", "Sobre"),
    ("industria", "Dados da Indústria"),
    ("carteira", "Dados de Carteira"),
    ("estimativas", "Estimativas e Modelagem"),
    ("glossario", "Glossário"),
)
_MAIN_SECTION_LABELS = dict(_MAIN_SECTIONS)
_MAIN_SECTION_SLUGS = tuple(slug for slug, _label in _MAIN_SECTIONS)
_LEGACY_MAIN_SECTION_ALIASES = {
    "cloudwalk": "estimativas",
    "modelagem": "estimativas",
}
_LEGACY_ESTIMATES_VIEW_BY_SECTION = {
    "cloudwalk": VIEW_CEDENT_COST,
    "modelagem": VIEW_MATURITY_ASSUMPTIONS,
}
_DEFAULT_SECTION = "sobre"


def _requested_main_section_slug() -> str:
    raw_value = st.query_params.get("section", _DEFAULT_SECTION)
    if isinstance(raw_value, list):
        raw_value = raw_value[-1] if raw_value else _DEFAULT_SECTION
    return str(raw_value).strip().lower()


def _current_main_section() -> str:
    section = _requested_main_section_slug()
    if section == "regulamentos":
        return "carteira"
    section = _LEGACY_MAIN_SECTION_ALIASES.get(section, section)
    return section if section in _MAIN_SECTION_LABELS else _DEFAULT_SECTION


def _render_main_nav() -> str:
    selected = st.segmented_control(
        "Seção",
        options=_MAIN_SECTION_SLUGS,
        selection_mode="single",
        format_func=_MAIN_SECTION_LABELS.get,
        key="fidc_main_section",
        label_visibility="collapsed",
        required=True,
        width="stretch",
    )
    return selected or _DEFAULT_SECTION


selected_section = st.session_state.get("fidc_main_section")
if selected_section in _LEGACY_MAIN_SECTION_ALIASES:
    st.session_state["estimativas_modelagem_view"] = _LEGACY_ESTIMATES_VIEW_BY_SECTION[selected_section]
    selected_section = _LEGACY_MAIN_SECTION_ALIASES[selected_section]
    st.session_state["fidc_main_section"] = selected_section
requested_section = _current_main_section() if "section" in st.query_params else None
if requested_section is not None:
    requested_slug = _requested_main_section_slug()
    if requested_slug in _LEGACY_ESTIMATES_VIEW_BY_SECTION:
        st.session_state["estimativas_modelagem_view"] = _LEGACY_ESTIMATES_VIEW_BY_SECTION[requested_slug]
    st.session_state["fidc_main_section"] = requested_section
elif selected_section not in _MAIN_SECTION_LABELS:
    st.session_state["fidc_main_section"] = _DEFAULT_SECTION

if "section" in st.query_params:
    st.query_params.pop("section", None)

selected_section = _render_main_nav()

with dashboard_page(selected_section):
    if selected_section == "industria":
        render_tab_industry_study()
    elif selected_section == "carteira":
        render_page_header("Dados de Carteira", "Analise carteiras salvas ou consulte um FIDC diretamente pelo CNPJ.")
        _render_period_selector = getattr(ime_tab, "render_period_selector", None) or getattr(ime_tab, "_render_period_selector")
        period = _render_period_selector(state_prefix="ime_global")
        render_portfolio_center_page(period=period)
    elif selected_section == "estimativas":
        render_tab_estimativas_modelagem()
    elif selected_section == "glossario":
        render_tab_fidc_book()
    elif selected_section == "sobre":
        try:
            from tabs.tab_about import render_tab_about

            render_tab_about()
        except ModuleNotFoundError as exc:
            st.error("A tela Sobre ainda não foi carregada corretamente neste deploy.")
            if diagnostics_enabled():
                st.caption(f"Módulo ausente: {exc.name}.")
        except Exception as exc:  # noqa: BLE001
            st.error("A tela Sobre encontrou um erro, mas as demais abas continuam disponíveis.")
            if diagnostics_enabled():
                st.caption(f"Detalhe técnico: {type(exc).__name__}: {exc}")
