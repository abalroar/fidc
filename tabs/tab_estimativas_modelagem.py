from __future__ import annotations

import streamlit as st

from services.dashboard_ui import render_page_header
from tabs.tab_cloudwalk_financial_cost import render_tab_cloudwalk_financial_cost
from tabs.tab_modelo_fidc import render_tab_modelo_fidc


VIEW_CEDENT_COST = "custo_cedente"
VIEW_MATURITY_ASSUMPTIONS = "vencimentario_premissas"
ESTIMATES_MODELING_VIEWS = (
    (VIEW_CEDENT_COST, "Custo Financeiro do Cedente"),
    (VIEW_MATURITY_ASSUMPTIONS, "Vencimentário e Premissas"),
)
_VIEW_LABELS = dict(ESTIMATES_MODELING_VIEWS)
_VIEW_OPTIONS = tuple(slug for slug, _label in ESTIMATES_MODELING_VIEWS)
_VIEW_STATE_KEY = "estimativas_modelagem_view"

_ESTIMATES_MODELING_CSS = """
<style>
.st-key-fidc_page_estimativas .st-key-estimativas_modelagem_nav {
    border-bottom: 1px solid #dde3ea;
    margin: 0 0 0.75rem;
    padding: 0;
}
.st-key-fidc_page_estimativas .st-key-estimativas_modelagem_nav [data-testid="stButtonGroup"] {
    overflow-x: visible;
}
.st-key-fidc_page_estimativas .st-key-estimativas_modelagem_nav [data-baseweb="button-group"] {
    display: grid !important;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: 100%;
}
.st-key-fidc_page_estimativas .st-key-estimativas_modelagem_nav [data-testid^="stBaseButton-segmented_control"] {
    background: transparent !important;
    border: 0 !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    color: #5a6470 !important;
    font-size: 0.88rem !important;
    font-weight: 550 !important;
    min-height: 2.55rem !important;
    padding: 0.45rem 0.8rem !important;
    width: 100% !important;
}
.st-key-fidc_page_estimativas .st-key-estimativas_modelagem_nav [data-testid^="stBaseButton-segmented_control"]:hover {
    background: #fff7f2 !important;
    color: #d9530b !important;
}
.st-key-fidc_page_estimativas .st-key-estimativas_modelagem_nav [data-testid="stBaseButton-segmented_controlActive"] {
    background: transparent !important;
    border-bottom-color: #ff5a00 !important;
    color: #20262d !important;
    font-weight: 650 !important;
}
.st-key-fidc_page_estimativas .estimates-view-purpose {
    color: #64707c;
    font-size: 0.86rem;
    line-height: 1.45;
    margin: 0 0 0.8rem;
    max-width: 72rem;
}
@media (max-width: 520px) {
    .st-key-fidc_page_estimativas .st-key-estimativas_modelagem_nav [data-testid^="stBaseButton-segmented_control"] {
        font-size: 0.78rem !important;
        line-height: 1.2 !important;
        min-height: 3.2rem !important;
        padding: 0.4rem 0.35rem !important;
        white-space: normal !important;
    }
    .st-key-fidc_page_estimativas .st-key-estimativas_modelagem_nav [data-testid^="stBaseButton-segmented_control"] p {
        line-height: 1.2 !important;
        white-space: normal !important;
    }
}
</style>
"""


def normalize_estimates_modeling_view(value: object) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in _VIEW_LABELS else VIEW_CEDENT_COST


def render_tab_estimativas_modelagem() -> None:
    st.markdown(_ESTIMATES_MODELING_CSS, unsafe_allow_html=True)
    render_page_header(
        "Estimativas e Modelagem",
        "Estime o custo de funding do cedente ou projete vencimentos, premissas e proteção de uma estrutura FIDC.",
    )

    selected_view = normalize_estimates_modeling_view(st.session_state.get(_VIEW_STATE_KEY))
    st.session_state[_VIEW_STATE_KEY] = selected_view
    with st.container(key="estimativas_modelagem_nav"):
        selected_view = st.segmented_control(
            "Sub-aba",
            options=_VIEW_OPTIONS,
            format_func=_VIEW_LABELS.get,
            selection_mode="single",
            required=True,
            key=_VIEW_STATE_KEY,
            label_visibility="collapsed",
            width="stretch",
        )
    selected_view = normalize_estimates_modeling_view(selected_view)

    if selected_view == VIEW_MATURITY_ASSUMPTIONS:
        render_tab_modelo_fidc(embedded=True)
        return
    render_tab_cloudwalk_financial_cost(embedded=True)
