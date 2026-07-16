from __future__ import annotations

from dataclasses import dataclass
from html import escape

import streamlit as st

from services.ime_period import ImePeriodSelection
from services.portfolio_store import PortfolioRecord, portfolio_basket_signature
from tabs import tab_deep_dive as deep_dive_tab
from tabs import tab_fidc_ime_carteira as carteira_tab
from tabs import tab_fidc_monitoring as monitoring_tab
from tabs import tab_mercado_livre as somatorio_tab


SECTION_AGING = "Aging e visão executiva"
SECTION_RETURNS = "Retornos e análise de crédito"
SECTION_MONITORING = "Monitoramento e base regulatória"
SECTION_DEEP_DIVE = "Regulamentos"
DEFAULT_SECTIONS = (SECTION_AGING, SECTION_RETURNS, SECTION_DEEP_DIVE)


@dataclass(frozen=True)
class PortfolioPageBlock:
    section_id: str
    title: str
    group: str
    position: int


_PORTFOLIO_PAGE_CSS = """
<style>
.portfolio-center-header {
    border-bottom: 2px solid #1F1F1F;
    margin: 0.2rem 0 0.55rem 0;
    padding-bottom: 0.6rem;
}
.portfolio-center-title {
    color: #1F1F1F;
    font-size: 1.18rem;
    font-weight: 700;
    line-height: 1.25;
    margin: 0;
}
.portfolio-center-meta {
    color: #6B6B6B;
    display: flex;
    flex-wrap: wrap;
    font-size: 0.74rem;
    gap: 0.45rem;
    line-height: 1.35;
    margin-top: 0.3rem;
}
.portfolio-center-meta span {
    border-left: 3px solid #FF6200;
    padding: 0.08rem 0.45rem;
}
.portfolio-block-header {
    align-items: baseline;
    border-top: 1px solid #BFBFBF;
    display: flex;
    gap: 0.55rem;
    margin: 1.35rem 0 0.65rem 0;
    padding-top: 0.65rem;
}
.portfolio-block-title {
    color: #1F1F1F;
    font-size: 1.04rem;
    font-weight: 700;
    line-height: 1.25;
    margin: 0 !important;
}
.st-key-fidc_page_carteira .portfolio-context-overlay {
    align-items: center;
    background: #FFFFFF;
    color: #1F1F1F;
    display: flex;
    inset: 0;
    justify-content: center;
    position: fixed;
    text-align: center;
    z-index: 999999;
}
.st-key-fidc_page_carteira .portfolio-context-overlay strong {
    display: block;
    font-size: 1rem;
    font-weight: 650;
}
.st-key-fidc_page_carteira .portfolio-context-overlay span {
    color: #6B6B6B;
    display: block;
    font-size: 0.78rem;
    margin-top: 0.25rem;
}
.fidc-section {
    font-size: 1rem !important;
    margin: 1rem 0 0.45rem 0 !important;
}
.fidc-chart-title {
    font-size: 0.88rem !important;
    line-height: 1.3 !important;
}
div[data-testid="stExpander"] details {
    background: #FFFFFF;
    border: 1px solid #D9D9D9;
    border-radius: 4px;
    box-shadow: none;
}
div[data-testid="stExpander"] summary {
    min-height: 2.3rem;
    padding: 0.42rem 0.65rem;
}
div[data-testid="stExpander"] summary p {
    color: #2F2F2F;
    font-size: 0.78rem;
    font-weight: 600;
    line-height: 1.3;
}
div[data-testid="stDownloadButton"] button,
div[data-testid="stButton"] button {
    border-radius: 4px;
    font-size: 0.78rem;
    min-height: 2.25rem;
}
div[data-testid="stCaptionContainer"] p {
    font-size: 0.72rem;
    line-height: 1.4;
}
@media (max-width: 700px) {
    div[data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 0.65rem !important;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
        flex: 1 1 100% !important;
        min-width: 0 !important;
        width: 100% !important;
    }
    .portfolio-block-header { margin-top: 1.05rem; }
}
</style>
"""

_BLOCKS = (
    PortfolioPageBlock(SECTION_AGING, "Diagnóstico da carteira", "Contexto e risco", 10),
    PortfolioPageBlock(SECTION_RETURNS, "Retorno e crédito", "Contexto e risco", 20),
    PortfolioPageBlock(SECTION_MONITORING, "Monitoramento recorrente", "Monitoramento e governança", 30),
    PortfolioPageBlock(SECTION_DEEP_DIVE, "Regulamentos", "Monitoramento e governança", 40),
)
_BLOCK_BY_ID = {block.section_id: block for block in _BLOCKS}
_SECTION_DEPENDENCIES: dict[str, tuple[str, ...]] = {}
_GROUP_ORDER = ("Contexto e risco", "Monitoramento e governança")


def render_portfolio_center_page(period: ImePeriodSelection) -> None:
    st.markdown(_PORTFOLIO_PAGE_CSS, unsafe_allow_html=True)
    selected_portfolio, _ = carteira_tab.render_portfolio_control_panel(
        load_button_label="Carregar IME",
        load_button_key="portfolio_center_load_ime",
        show_load_button=False,
    )
    if selected_portfolio is None:
        st.info("Crie ou selecione uma carteira para iniciar as análises.")
        return

    selected_sections = _render_workflow_selector()
    if not selected_sections:
        st.info("Selecione ao menos um bloco para montar a página da carteira.")
        return

    context_signature = "|".join(
        (
            selected_portfolio.id,
            portfolio_basket_signature(selected_portfolio.funds),
            period.cache_key,
            *selected_sections,
        )
    )
    previous_signature = st.session_state.get("portfolio_page_context_signature")
    st.session_state["portfolio_page_context_signature"] = context_signature
    loading_surface = st.empty()
    if previous_signature != context_signature:
        with loading_surface.container():
            st.markdown(
                '<div class="portfolio-context-overlay" role="status">'
                f'<div><strong>Atualizando carteira</strong><span>{escape(selected_portfolio.name)} · {escape(period.label)}</span></div>'
                "</div>",
                unsafe_allow_html=True,
            )

    analysis_surface = st.empty()
    analysis_surface.empty()
    try:
        with analysis_surface.container():
            _render_portfolio_context_header(
                selected_portfolio=selected_portfolio,
                period=period,
                selected_sections=selected_sections,
            )
            _preload_portfolio_data(
                selected_portfolio=selected_portfolio,
                period=period,
                selected_sections=selected_sections,
            )
            for _, group_sections in _sections_grouped_for_render(selected_sections):
                for section in group_sections:
                    _render_section(
                        section=section,
                        selected_portfolio=selected_portfolio,
                        period=period,
                    )
    finally:
        loading_surface.empty()


def _render_workflow_selector() -> tuple[str, ...]:
    return DEFAULT_SECTIONS


def _render_portfolio_context_header(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
    selected_sections: tuple[str, ...],
) -> None:
    _ = selected_sections
    st.markdown(
        f"""
<div class="portfolio-center-header">
  <div class="portfolio-center-title">{escape(selected_portfolio.name)}</div>
  <div class="portfolio-center-meta">
    <span>{escape(period.label)}</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def _preload_portfolio_data(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
    selected_sections: tuple[str, ...],
) -> None:
    if SECTION_RETURNS in selected_sections:
        calculation_period = somatorio_tab._period_with_yoy_lookback(period)
        if not _returns_outputs_cached(selected_portfolio=selected_portfolio, period=calculation_period):
            carteira_tab.ensure_portfolio_ime_data(selected_portfolio=selected_portfolio, period=calculation_period)
    if SECTION_AGING in selected_sections:
        carteira_tab.ensure_portfolio_ime_data(selected_portfolio=selected_portfolio, period=period)


def _returns_outputs_cached(*, selected_portfolio: PortfolioRecord, period: ImePeriodSelection) -> bool:
    cache_session_key = somatorio_tab._outputs_session_key(selected_portfolio=selected_portfolio, period=period)
    if st.session_state.get(cache_session_key) is not None:
        return True
    return (
        somatorio_tab.load_outputs_from_cache(
            portfolio_id=selected_portfolio.id,
            period_key=period.cache_key,
            portfolio_funds=selected_portfolio.funds,
        )
        is not None
    )

def _render_section(
    *,
    section: str,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
) -> None:
    _render_portfolio_block_header(section)
    if section == SECTION_AGING:
        carteira_tab.render_portfolio_aging_analysis(
            selected_portfolio=selected_portfolio,
            period=period,
            section_mode="stacked",
        )
        return

    if section == SECTION_RETURNS:
        somatorio_tab.render_tab_somatorio_fidcs(
            period=period,
            selected_portfolio=selected_portfolio,
            show_portfolio_controls=False,
            use_tabs=False,
            show_guide=False,
        )
        return

    if section == SECTION_MONITORING:
        monitoring_tab.render_tab_fidc_monitoring(
            period=period,
            selected_portfolio=selected_portfolio,
            show_portfolio_selector=False,
            use_tabs=False,
        )
        return

    if section == SECTION_DEEP_DIVE:
        deep_dive_tab.render_tab_deep_dive(
            selected_portfolio=selected_portfolio,
            show_portfolio_selector=False,
            show_curation_tools=False,
            compact=True,
        )


def _render_portfolio_block_header(section: str) -> None:
    block = _BLOCK_BY_ID.get(section)
    if block is None:
        return
    st.markdown(
        f"""
<div class="portfolio-block-header">
  <h2 class="portfolio-block-title">{escape(block.title)}</h2>
</div>
""",
        unsafe_allow_html=True,
    )


def _format_section_option(section: str) -> str:
    block = _BLOCK_BY_ID.get(section)
    if block is None:
        return section
    return block.title


def _resolve_workflow_sections(selected_sections: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    resolved: list[str] = []
    for section in selected_sections:
        if section not in _BLOCK_BY_ID:
            continue
        for dependency in _SECTION_DEPENDENCIES.get(section, ()):
            if dependency not in resolved:
                resolved.append(dependency)
        if section not in resolved:
            resolved.append(section)
    return tuple(sorted(resolved, key=lambda section: _BLOCK_BY_ID[section].position))


def _sections_grouped_for_render(selected_sections: tuple[str, ...]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    groups: list[tuple[str, tuple[str, ...]]] = []
    selected_lookup = set(selected_sections)
    for group_name in _GROUP_ORDER:
        group_sections = tuple(
            block.section_id
            for block in _BLOCKS
            if block.group == group_name and block.section_id in selected_lookup
        )
        if group_sections:
            groups.append((group_name, group_sections))
    return tuple(groups)
