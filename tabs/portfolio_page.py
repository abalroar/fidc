from __future__ import annotations

from dataclasses import dataclass
from html import escape

import streamlit as st

from services.ime_period import ImePeriodSelection
from services.portfolio_store import PortfolioRecord
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
PRESET_OVERVIEW = "Panorama executivo"
PRESET_CREDIT = "Crédito e retorno"
PRESET_REGULATORY = "Monitoramento regulatório"
PRESET_DILIGENCE = "Due diligence completa"


@dataclass(frozen=True)
class PortfolioPageBlock:
    section_id: str
    title: str
    group: str
    position: int


_PORTFOLIO_PAGE_CSS = """
<style>
.portfolio-center-header {
    border-bottom: 1px solid #dde3ea;
    margin: 0.25rem 0 0.85rem 0;
    padding-bottom: 0.7rem;
}
.portfolio-center-title {
    color: #283241;
    font-size: 1.22rem;
    font-weight: 700;
    line-height: 1.25;
    margin: 0;
}
.portfolio-center-meta {
    color: #6f7a87;
    display: flex;
    flex-wrap: wrap;
    font-size: 0.78rem;
    gap: 0.45rem;
    line-height: 1.35;
    margin-top: 0.35rem;
}
.portfolio-center-meta span {
    background: #f8f9fa;
    border: 1px solid #eceff3;
    border-radius: 999px;
    padding: 0.18rem 0.55rem;
}
.portfolio-center-group {
    border-top: 1px solid #dde3ea;
    margin: 1.1rem 0 0.55rem 0;
    padding-top: 0.75rem;
}
.portfolio-center-group-title {
    color: #283241;
    font-size: 0.94rem;
    font-weight: 700;
    line-height: 1.25;
    margin: 0;
}
.portfolio-center-group-flow {
    color: #6f7a87;
    font-size: 0.76rem;
    line-height: 1.35;
    margin-top: 0.22rem;
}
</style>
"""

_BLOCKS = (
    PortfolioPageBlock(SECTION_AGING, "Diagnóstico da carteira", "Contexto e risco", 10),
    PortfolioPageBlock(SECTION_RETURNS, "Retorno e crédito", "Contexto e risco", 20),
    PortfolioPageBlock(SECTION_MONITORING, "Monitoramento recorrente", "Monitoramento e governança", 30),
    PortfolioPageBlock(SECTION_DEEP_DIVE, "Waterfall e deep dives", "Monitoramento e governança", 40),
)
_BLOCK_BY_ID = {block.section_id: block for block in _BLOCKS}
_PRESET_SECTIONS = {
    PRESET_OVERVIEW: DEFAULT_SECTIONS,
    PRESET_CREDIT: (SECTION_AGING, SECTION_RETURNS),
    PRESET_REGULATORY: (SECTION_MONITORING,),
    PRESET_DILIGENCE: ALL_SECTIONS,
}
_SECTION_DEPENDENCIES = {
    SECTION_DEEP_DIVE: (SECTION_MONITORING,),
}
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
    for group_name, group_sections in _sections_grouped_for_render(selected_sections):
        _render_group_header(group_name=group_name, group_sections=group_sections)
        for section in group_sections:
            _render_section(
                section=section,
                selected_portfolio=selected_portfolio,
                period=period,
            )


def _render_workflow_selector() -> tuple[str, ...]:
    preset = st.radio(
        "Roteiro",
        options=list(_PRESET_SECTIONS),
        index=list(_PRESET_SECTIONS).index(PRESET_OVERVIEW),
        horizontal=True,
        key="portfolio_center_preset",
    )
    multiselect_key = f"portfolio_center_sections::{_slug_widget_value(preset)}"
    selected_sections = st.multiselect(
        "Blocos da página",
        options=list(ALL_SECTIONS),
        default=list(_PRESET_SECTIONS[preset]),
        key=multiselect_key,
        format_func=_format_section_option,
    )
    return _resolve_workflow_sections(selected_sections)


def _render_portfolio_context_header(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
    selected_sections: tuple[str, ...],
) -> None:
    flow = " / ".join(_BLOCK_BY_ID[section].title for section in selected_sections if section in _BLOCK_BY_ID)
    st.markdown(
        f"""
<div class="portfolio-center-header">
  <div class="portfolio-center-title">{escape(selected_portfolio.name)}</div>
  <div class="portfolio-center-meta">
    <span>{len(selected_portfolio.funds)} fundo(s)</span>
    <span>{escape(period.label)}</span>
    <span>{escape(flow)}</span>
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


def _render_group_header(*, group_name: str, group_sections: tuple[str, ...]) -> None:
    flow = " / ".join(_BLOCK_BY_ID[section].title for section in group_sections if section in _BLOCK_BY_ID)
    st.markdown(
        f"""
<div class="portfolio-center-group">
  <div class="portfolio-center-group-title">{escape(group_name)}</div>
  <div class="portfolio-center-group-flow">{escape(flow)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_section(
    *,
    section: str,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
) -> None:
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


def _format_section_option(section: str) -> str:
    block = _BLOCK_BY_ID.get(section)
    if block is None:
        return section
    return f"{block.group} · {block.title}"


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


def _slug_widget_value(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
