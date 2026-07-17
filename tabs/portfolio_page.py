from __future__ import annotations

from dataclasses import dataclass, replace
from html import escape
from typing import Any, Callable

import pandas as pd
import streamlit as st

from services.dashboard_ui import diagnostics_enabled
from services.fund_name_display import short_fund_name
from services.fundonet_dashboard import filter_dashboard_to_competencias
from services.fundonet_portfolio_dashboard import PortfolioDashboardBundle, build_portfolio_dashboard_bundle
from services.ime_period import ImePeriodSelection
from services.meli_credit_monitor import MeliMonitorOutputs, build_meli_monitor_outputs
from services.meli_credit_research import MeliResearchOutputs, build_meli_research_outputs
from services.meli_credit_research_verification import verify_meli_research_outputs
from services.meli_credit_monitor_visuals import (
    cohort_chart,
    duration_chart,
    npl_severity_chart,
    portfolio_growth_chart,
    roll_rates_chart,
)
from services.mercado_livre_dashboard import (
    build_consolidated_snapshot_excel_bytes,
    build_full_variable_csv_zip_bytes,
    build_full_variable_excel_export_bytes,
)
from services.portfolio_store import PortfolioRecord, portfolio_basket_signature
from tabs import tab_deep_dive as deep_dive_tab
from tabs import tab_dashboard_meli as credit_tab
from tabs import tab_fidc_ime as ime_tab
from tabs import tab_fidc_ime_carteira as carteira_tab
from tabs import tab_fidc_monitoring as monitoring_tab
from tabs import tab_mercado_livre as somatorio_tab


SECTION_AGING = "Aging e visão executiva"
SECTION_RETURNS = "Retornos e análise de crédito"
SECTION_MONITORING = "Monitoramento e base regulatória"
SECTION_DEEP_DIVE = "Curadoria de Leitura (Documentos)"
DEFAULT_SECTIONS = (SECTION_AGING, SECTION_RETURNS, SECTION_DEEP_DIVE)

PORTFOLIO_VIEW_TABS = (
    "Estrutura",
    "Crédito e prazo",
    "Inadimplência",
    "Rentabilidade",
    SECTION_DEEP_DIVE,
)


@dataclass(frozen=True)
class PortfolioPageBlock:
    section_id: str
    title: str
    group: str
    position: int


@dataclass(frozen=True)
class PortfolioAnalysisScope:
    value: str
    label: str
    kind: str
    cnpj: str
    dashboard: Any


@dataclass(frozen=True)
class PortfolioAnalysisData:
    scopes: tuple[PortfolioAnalysisScope, ...]
    aggregate_bundle: PortfolioDashboardBundle | None
    outputs: Any
    monitor_outputs: MeliMonitorOutputs | None
    research_outputs: MeliResearchOutputs | None
    verification_report: pd.DataFrame | None
    dashboard_errors: dict[str, str]
    load_errors: dict[str, str]


class PortfolioAnalysisUnavailable(RuntimeError):
    def __init__(
        self,
        *,
        message: str,
        details: tuple[str, ...] = (),
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        self.retryable = retryable


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
.portfolio-scope-current {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-left: 4px solid #ff5a00;
    border-radius: 8px;
    margin: 0.35rem 0 0.8rem 0;
    padding: 9px 11px;
}
.portfolio-scope-current span {
    color: #6f7a87;
    display: block;
    font-size: 0.72rem;
    margin-bottom: 2px;
}
.portfolio-scope-current strong {
    color: #111827;
    display: block;
    font-size: 0.95rem;
}
.st-key-fidc_page_carteira .portfolio-loading-state {
    align-items: start;
    background: #f7f8fa;
    border: 1px solid var(--dashboard-grid, #e5e8ec);
    border-radius: 8px;
    color: var(--dashboard-ink, #202832);
    display: grid;
    gap: 0.7rem;
    grid-template-columns: 1rem minmax(0, 1fr);
    margin: 0.75rem 0 1rem;
    padding: 0.85rem 1rem;
    width: 100%;
}
.st-key-fidc_page_carteira .portfolio-loading-indicator {
    animation: portfolio-loading-spin 800ms linear infinite;
    border: 2px solid #cfd4da;
    border-radius: 50%;
    border-top-color: var(--dashboard-accent, #ff5a00);
    height: 1rem;
    margin-top: 0.16rem;
    width: 1rem;
}
.st-key-fidc_page_carteira .portfolio-loading-copy {
    min-width: 0;
}
.st-key-fidc_page_carteira .portfolio-loading-copy strong {
    color: var(--dashboard-ink, #202832);
    display: block;
    font-size: 0.92rem;
    font-weight: 600;
    line-height: 1.35;
    overflow-wrap: anywhere;
}
.st-key-fidc_page_carteira .portfolio-loading-meta {
    color: var(--dashboard-muted, #66717d);
    display: flex;
    flex-wrap: wrap;
    font-size: 0.78rem;
    gap: 0.2rem 0.75rem;
    line-height: 1.4;
    margin-top: 0.12rem;
}
.st-key-fidc_page_carteira .portfolio-loading-copy p {
    color: #4d5864;
    font-size: 0.84rem;
    line-height: 1.45;
    margin: 0.32rem 0 0;
    max-width: 65ch;
}
.st-key-fidc_page_carteira .portfolio-error-state {
    background: #f7f8fa;
    border: 1px solid var(--dashboard-grid, #e5e8ec);
    border-left: 3px solid var(--dashboard-accent, #ff5a00);
    border-radius: 8px;
    color: var(--dashboard-ink, #202832);
    margin: 0.75rem 0 0.65rem;
    padding: 0.85rem 1rem;
}
.st-key-fidc_page_carteira .portfolio-error-state strong {
    display: block;
    font-size: 0.92rem;
    font-weight: 600;
    line-height: 1.35;
}
.st-key-fidc_page_carteira .portfolio-error-state p {
    color: #4d5864;
    font-size: 0.84rem;
    line-height: 1.45;
    margin: 0.3rem 0 0;
    max-width: 72ch;
}
.st-key-fidc_page_carteira .portfolio-unavailable-note {
    color: var(--dashboard-muted, #66717d);
    font-size: 0.82rem;
    margin: 0.75rem 0;
}
.st-key-fidc_page_carteira .st-key-ime_portfolio_entry_mode [data-baseweb="button-group"] {
    display: flex !important;
    width: 100%;
}
.st-key-fidc_page_carteira .st-key-ime_portfolio_entry_mode [data-testid^="stBaseButton-segmented_control"] {
    flex: 1 1 0 !important;
    white-space: nowrap !important;
}
@keyframes portfolio-loading-spin {
    to { transform: rotate(360deg); }
}
@media (max-width: 640px) {
    .st-key-fidc_page_carteira .portfolio-loading-state,
    .st-key-fidc_page_carteira .portfolio-error-state {
        padding: 0.75rem;
    }
    .st-key-fidc_page_carteira .st-key-ime_portfolio_entry_mode [data-baseweb="button-group"] {
        flex-wrap: wrap !important;
    }
    .st-key-fidc_page_carteira .st-key-ime_portfolio_entry_mode [data-testid^="stBaseButton-segmented_control"] {
        flex: 1 1 100% !important;
        width: 100% !important;
    }
}
@media (prefers-reduced-motion: reduce) {
    .st-key-fidc_page_carteira .portfolio-loading-indicator {
        animation: none;
    }
}
</style>
"""

_BLOCKS = (
    PortfolioPageBlock(SECTION_AGING, "Diagnóstico da carteira", "Contexto e risco", 10),
    PortfolioPageBlock(SECTION_RETURNS, "Retorno e crédito", "Contexto e risco", 20),
    PortfolioPageBlock(SECTION_MONITORING, "Monitoramento recorrente", "Monitoramento e governança", 30),
    PortfolioPageBlock(SECTION_DEEP_DIVE, SECTION_DEEP_DIVE, "Monitoramento e governança", 40),
)
_BLOCK_BY_ID = {block.section_id: block for block in _BLOCKS}
_SECTION_DEPENDENCIES: dict[str, tuple[str, ...]] = {}
_GROUP_ORDER = ("Contexto e risco", "Monitoramento e governança")


def render_portfolio_center_page(period: ImePeriodSelection) -> None:
    st.html(
        "\n".join(
            (
                _PORTFOLIO_PAGE_CSS,
                ime_tab._FIDC_REPORT_CSS,
                credit_tab._DASHBOARD_MELI_CSS,
                somatorio_tab._SOMATORIO_FIDCS_UI_CSS,
            )
        )
    )
    selected_portfolio, _ = carteira_tab.render_portfolio_control_panel(
        load_button_label="Carregar IME",
        load_button_key="portfolio_center_load_ime",
        show_load_button=False,
    )
    if selected_portfolio is None:
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

    context_signature = "|".join(
        (
            selected_portfolio.id,
            portfolio_basket_signature(selected_portfolio.funds),
            period.cache_key,
            *selected_sections,
        )
    )
    previous_signature = st.session_state.get("portfolio_page_context_signature")
    analysis_surface = st.empty()
    analysis_surface.empty()
    analysis_ready = False
    try:
        with analysis_surface.container():
            loading_surface = st.empty()
            if previous_signature != context_signature:
                with loading_surface.container():
                    st.markdown(
                        _portfolio_loading_state_html(
                            selected_portfolio=selected_portfolio,
                            period=period,
                        ),
                        unsafe_allow_html=True,
                    )
            try:
                analysis_ready = _render_portfolio_analysis_surface(
                    selected_portfolio=selected_portfolio,
                    period=period,
                    selected_sections=selected_sections,
                )
            finally:
                loading_surface.empty()
    except Exception:
        _restore_portfolio_context_signature(previous_signature)
        raise
    else:
        if analysis_ready:
            st.session_state["portfolio_page_context_signature"] = context_signature
        else:
            _restore_portfolio_context_signature(previous_signature)


def _restore_portfolio_context_signature(previous_signature: object) -> None:
    if previous_signature is None:
        st.session_state.pop("portfolio_page_context_signature", None)
    else:
        st.session_state["portfolio_page_context_signature"] = previous_signature


def _portfolio_loading_state_html(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
) -> str:
    fund_count = len(selected_portfolio.funds)
    fund_label = f"{fund_count} fundo{'s' if fund_count != 1 else ''}"
    return f"""
<div class="portfolio-loading-state" role="status" aria-live="polite" aria-atomic="true">
  <span class="portfolio-loading-indicator" aria-hidden="true"></span>
  <div class="portfolio-loading-copy">
    <strong>Carregando {escape(selected_portfolio.name)}</strong>
    <span class="portfolio-loading-meta">
      <span>{escape(period.label)}</span>
      <span>{escape(fund_label)}</span>
    </span>
    <p>Buscando informes mensais e calculando os indicadores. A primeira consulta pode levar alguns instantes.</p>
  </div>
</div>
"""


def _render_portfolio_analysis_surface(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
    selected_sections: tuple[str, ...],
) -> bool:
    try:
        _preload_portfolio_data(
            selected_portfolio=selected_portfolio,
            period=period,
            selected_sections=selected_sections,
        )
        analysis = _load_portfolio_analysis_data(
            selected_portfolio=selected_portfolio,
            period=period,
        )
    except PortfolioAnalysisUnavailable as exc:
        _render_unavailable_portfolio_views(
            selected_portfolio=selected_portfolio,
            period=period,
            failure=exc,
        )
        return False
    except Exception as exc:  # noqa: BLE001
        _render_unavailable_portfolio_views(
            selected_portfolio=selected_portfolio,
            period=period,
            failure=PortfolioAnalysisUnavailable(
                message="Ocorreu uma falha inesperada ao montar os indicadores. Tente novamente.",
                details=(f"{exc.__class__.__name__}: {exc}",),
            ),
        )
        return False

    display_outputs = somatorio_tab._render_loaded_period_window(
        analysis.outputs,
        show_caption=True,
        control_label="Filtro visual de toda a análise",
    )
    analysis = _filter_analysis_dashboards_to_outputs(analysis, display_outputs)
    monitor_outputs = somatorio_tab._build_credit_monitor_for_display(
        outputs=analysis.outputs,
        display_outputs=display_outputs,
    )
    research_outputs = build_meli_research_outputs(monitor_outputs)
    verification_report = verify_meli_research_outputs(monitor_outputs, research_outputs)
    analysis = PortfolioAnalysisData(
        scopes=analysis.scopes,
        aggregate_bundle=analysis.aggregate_bundle,
        outputs=display_outputs,
        monitor_outputs=monitor_outputs,
        research_outputs=research_outputs,
        verification_report=verification_report,
        dashboard_errors=analysis.dashboard_errors,
        load_errors=analysis.load_errors,
    )

    _render_analysis_coverage_alert(analysis=analysis, selected_portfolio=selected_portfolio)

    _render_unified_portfolio_download(
        analysis=analysis,
        selected_portfolio=selected_portfolio,
        period=period,
    )
    selected_scopes = _render_scope_selector(
        scopes=analysis.scopes,
        portfolio_id=selected_portfolio.id,
    )
    if not selected_scopes:
        _render_unavailable_portfolio_views(
            selected_portfolio=selected_portfolio,
            period=period,
            failure=PortfolioAnalysisUnavailable(
                message="Selecione ao menos um fundo ou o consolidado para exibir a análise.",
                retryable=False,
            ),
        )
        return False

    structure_tab, credit_term_tab, delinquency_tab, returns_tab, curation_tab = st.tabs(PORTFOLIO_VIEW_TABS)
    with curation_tab:
        deep_dive_tab.render_tab_deep_dive(
            selected_portfolio=selected_portfolio,
            show_portfolio_selector=False,
            show_curation_tools=False,
            compact=True,
        )
    with structure_tab:
        _render_structure_tab(
            analysis=analysis,
            selected_scopes=selected_scopes,
            selected_portfolio=selected_portfolio,
            period=period,
        )
    with credit_term_tab:
        _render_credit_term_tab(
            analysis=analysis,
            selected_scopes=selected_scopes,
            selected_portfolio=selected_portfolio,
        )
    with delinquency_tab:
        _render_delinquency_tab(
            analysis=analysis,
            selected_scopes=selected_scopes,
            selected_portfolio=selected_portfolio,
        )
    with returns_tab:
        _render_returns_tab(
            analysis=analysis,
            selected_scopes=selected_scopes,
            selected_portfolio=selected_portfolio,
        )
    return True


def _render_unavailable_portfolio_views(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
    failure: PortfolioAnalysisUnavailable,
) -> None:
    st.markdown(
        f"""
<div class="portfolio-error-state" role="alert">
  <strong>Não foi possível concluir a análise</strong>
  <p>{escape(failure.message)}</p>
</div>
""",
        unsafe_allow_html=True,
    )
    if failure.retryable and st.button(
        "Tentar novamente",
        key=f"portfolio_analysis_retry::{selected_portfolio.id}::{period.cache_key}",
        type="primary",
    ):
        carteira_tab.load_portfolio_ime_data(
            selected_portfolio=selected_portfolio,
            period=period,
        )
        st.session_state.pop("portfolio_page_context_signature", None)
        st.rerun()
    if diagnostics_enabled() and failure.details:
        with st.expander("Detalhes técnicos", expanded=False):
            st.code("\n".join(failure.details), language=None)

    tabs = st.tabs(PORTFOLIO_VIEW_TABS)
    for tab in tabs[:-1]:
        with tab:
            st.markdown(
                '<p class="portfolio-unavailable-note">Esta seção será exibida após uma carga bem-sucedida.</p>',
                unsafe_allow_html=True,
            )
    with tabs[-1]:
        deep_dive_tab.render_tab_deep_dive(
            selected_portfolio=selected_portfolio,
            show_portfolio_selector=False,
            show_curation_tools=False,
            compact=True,
        )


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


def _load_portfolio_analysis_data(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
) -> PortfolioAnalysisData:
    runtime_state = carteira_tab.ensure_portfolio_ime_data(
        selected_portfolio=selected_portfolio,
        period=period,
    )
    results = runtime_state.get("results") or {}
    load_errors = {
        fund.cnpj: str((results.get(fund.cnpj) or {}).get("error") or "Fundo não carregado")
        for fund in selected_portfolio.funds
        if (results.get(fund.cnpj) or {}).get("result") is None
    }
    dashboards_by_cnpj, dashboard_errors = carteira_tab._build_loaded_dashboards_by_cnpj(
        selected_portfolio=selected_portfolio,
        results=results,
    )
    if not dashboards_by_cnpj:
        retryable = any(
            carteira_tab._is_retryable_portfolio_failure(results.get(fund.cnpj) or {})
            for fund in selected_portfolio.funds
        )
        if retryable:
            message = (
                "A fonte regulatória demorou mais que o esperado. "
                "Tente novamente; os dados já carregados serão reaproveitados."
            )
        elif dashboard_errors:
            message = (
                "Os arquivos foram recebidos, mas não foi possível montar os indicadores. "
                "Tente novamente ou selecione outro período."
            )
        else:
            message = (
                "Não encontramos informes utilizáveis para o período selecionado. "
                "Tente outro período ou faça uma nova tentativa."
            )
        details = tuple(
            f"{fund.display_name} ({fund.cnpj}): {load_errors[fund.cnpj]}"
            for fund in selected_portfolio.funds
            if fund.cnpj in load_errors
        ) + tuple(
            f"Dashboard {cnpj}: {error}"
            for cnpj, error in dashboard_errors.items()
        )
        raise PortfolioAnalysisUnavailable(
            message=message,
            details=details,
        )

    try:
        aggregate_bundle = build_portfolio_dashboard_bundle(
            portfolio_name=selected_portfolio.name,
            dashboards_by_cnpj=dashboards_by_cnpj,
        )
    except Exception as exc:  # noqa: BLE001
        aggregate_bundle = None
        dashboard_errors["CONSOLIDADO"] = f"{exc.__class__.__name__}: {exc}"

    scopes: list[PortfolioAnalysisScope] = []
    if aggregate_bundle is not None and len(dashboards_by_cnpj) > 1:
        scopes.append(
            PortfolioAnalysisScope(
                value=somatorio_tab.CONSOLIDATED_SCOPE_VALUE,
                label="Consolidado",
                kind="consolidated",
                cnpj="",
                dashboard=aggregate_bundle.dashboard,
            )
        )
    for fund in selected_portfolio.funds:
        loaded = dashboards_by_cnpj.get(fund.cnpj)
        if loaded is None:
            continue
        fund_name, dashboard = loaded
        scopes.append(
            PortfolioAnalysisScope(
                value=f"fund::{fund.cnpj}",
                label=short_fund_name(fund_name),
                kind="fund",
                cnpj=fund.cnpj,
                dashboard=dashboard,
            )
        )

    outputs = somatorio_tab.resolve_somatorio_outputs(
        period=period,
        selected_portfolio=selected_portfolio,
    )
    if outputs is None:
        raise PortfolioAnalysisUnavailable(
            message=(
                "Os informes foram carregados, mas a consolidação não foi concluída. "
                "Tente novamente para recalcular os indicadores."
            ),
            details=tuple(
                f"{fund.display_name} ({fund.cnpj}): {load_errors[fund.cnpj]}"
                for fund in selected_portfolio.funds
                if fund.cnpj in load_errors
            ),
        )
    return PortfolioAnalysisData(
        scopes=tuple(scopes),
        aggregate_bundle=aggregate_bundle,
        outputs=outputs,
        monitor_outputs=None,
        research_outputs=None,
        verification_report=None,
        dashboard_errors=dashboard_errors,
        load_errors=load_errors,
    )


def _filter_analysis_dashboards_to_outputs(
    analysis: PortfolioAnalysisData,
    display_outputs: Any,
) -> PortfolioAnalysisData:
    monthly = getattr(display_outputs, "consolidated_monthly", pd.DataFrame())
    if monthly is None or monthly.empty or "competencia" not in monthly.columns:
        return replace(analysis, outputs=display_outputs)
    competencias = [
        str(value)
        for value in monthly["competencia"].dropna().astype(str).drop_duplicates().tolist()
    ]
    if not competencias:
        return replace(analysis, outputs=display_outputs)

    filtered_scopes = tuple(
        replace(
            scope,
            dashboard=filter_dashboard_to_competencias(scope.dashboard, competencias),
        )
        for scope in analysis.scopes
    )
    filtered_bundle = analysis.aggregate_bundle
    if filtered_bundle is not None:
        filtered_bundle = replace(
            filtered_bundle,
            dashboard=filter_dashboard_to_competencias(filtered_bundle.dashboard, competencias),
        )
    return replace(
        analysis,
        scopes=filtered_scopes,
        aggregate_bundle=filtered_bundle,
        outputs=display_outputs,
    )


def _render_analysis_coverage_alert(
    *,
    analysis: PortfolioAnalysisData,
    selected_portfolio: PortfolioRecord,
) -> None:
    if analysis.load_errors:
        st.warning(
            "A análise está parcial: um ou mais fundos da seleção não foram carregados. "
            "Os fundos ausentes não são tratados como zero."
        )
        with st.expander("Fundos não carregados", expanded=True):
            for fund in selected_portfolio.funds:
                message = analysis.load_errors.get(fund.cnpj)
                if message is not None:
                    st.caption(f"{fund.display_name} · {fund.cnpj} — {message}")

    dashboard_cnpjs = {scope.cnpj for scope in analysis.scopes if scope.kind == "fund"}
    output_cnpjs = set(getattr(analysis.outputs, "fund_monthly", {}) or {})
    if dashboard_cnpjs != output_cnpjs:
        st.warning(
            "As fontes carregadas não cobrem o mesmo conjunto de fundos. "
            "O PPT completo fica bloqueado para evitar combinar escopos diferentes."
        )


def _render_unified_portfolio_download(
    *,
    analysis: PortfolioAnalysisData,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
) -> None:
    from services.fundonet_ppt_export import build_dashboard_pptx_bytes
    from services.pptx_merge import merge_pptx_bytes
    from services.somatorio_fidcs_ppt_export import build_somatorio_fidcs_pptx_bytes

    if analysis.monitor_outputs is None or analysis.research_outputs is None:
        st.warning("Os dados avançados ainda não estão prontos para a exportação completa.")
        return

    dashboard_cnpjs = {scope.cnpj for scope in analysis.scopes if scope.kind == "fund"}
    output_cnpjs = set(getattr(analysis.outputs, "fund_monthly", {}) or {})
    ppt_scope_consistent = dashboard_cnpjs == output_cnpjs and not analysis.load_errors
    decks: list[bytes] = []
    export_warnings: list[str] = []
    if analysis.aggregate_bundle is not None and ppt_scope_consistent:
        try:
            decks.append(
                build_dashboard_pptx_bytes(
                    analysis.aggregate_bundle.dashboard,
                    requested_period_label=period.label,
                )
            )
        except Exception as exc:  # noqa: BLE001
            export_warnings.append(f"Visão Fundos.NET: {exc}")
    if ppt_scope_consistent:
        try:
            decks.append(
                build_somatorio_fidcs_pptx_bytes(
                    outputs=analysis.outputs,
                    monitor_outputs=analysis.monitor_outputs,
                    research_outputs=analysis.research_outputs,
                )
            )
        except Exception as exc:  # noqa: BLE001
            export_warnings.append(f"Base analítica: {exc}")

    file_token = _safe_file_token(selected_portfolio.name)
    if decks:
        try:
            pptx_bytes = decks[0] if len(decks) == 1 else merge_pptx_bytes(decks[0], *decks[1:])
        except Exception as exc:  # noqa: BLE001
            export_warnings.append(f"Concatenação dos decks: {exc}")
        else:
            st.download_button(
                "Exportar apresentação completa da carteira (PPTX)",
                data=pptx_bytes,
                file_name=f"carteira_completa_{file_token}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                key=f"portfolio_unified_pptx::{selected_portfolio.id}",
                type="primary",
                use_container_width=True,
                help="Um único arquivo com os slides dos dois relatórios existentes, preservados como objetos editáveis.",
            )
    elif not ppt_scope_consistent:
        st.warning("O PPT completo será habilitado quando todos os fundos estiverem consistentes nas duas fontes.")
    else:
        st.warning("A apresentação completa não pôde ser gerada nesta execução.")

    with st.expander("Downloads de dados editáveis", expanded=False):
        snapshot_bytes = build_consolidated_snapshot_excel_bytes(analysis.outputs)
        full_excel_bytes = build_full_variable_excel_export_bytes(
            analysis.outputs,
            monitor_outputs=analysis.monitor_outputs,
        )
        csv_zip_bytes = build_full_variable_csv_zip_bytes(analysis.outputs)
        st.download_button(
            "Resumo exibido (Excel)",
            data=snapshot_bytes,
            file_name=f"carteira_resumo_{file_token}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"portfolio_snapshot_excel::{selected_portfolio.id}",
            use_container_width=True,
        )
        st.download_button(
            "Base completa e rentabilidade por série (Excel)",
            data=full_excel_bytes,
            file_name=f"carteira_base_completa_{file_token}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"portfolio_full_excel::{selected_portfolio.id}",
            use_container_width=True,
        )
        st.download_button(
            "Base completa (CSV)",
            data=csv_zip_bytes,
            file_name=f"carteira_base_completa_{file_token}.zip",
            mime="application/zip",
            key=f"portfolio_full_csv::{selected_portfolio.id}",
            use_container_width=True,
        )
        for warning in export_warnings:
            st.caption(f"Parte não incluída no PPT: {warning}")


def _safe_file_token(value: object) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value or "").strip().lower()).strip("_") or "carteira"


def _render_scope_selector(
    *,
    scopes: tuple[PortfolioAnalysisScope, ...],
    portfolio_id: str,
) -> tuple[PortfolioAnalysisScope, ...]:
    if len(scopes) <= 1:
        return scopes

    show_all = st.toggle(
        "Mostrar consolidado e todos os fundos",
        value=True,
        key=f"portfolio_analysis_show_all::{portfolio_id}",
        help="Desative para escolher somente os escopos que deseja consultar.",
    )
    if show_all:
        return scopes

    values = [scope.value for scope in scopes]
    labels = {
        scope.value: (
            "Consolidado da carteira"
            if scope.kind == "consolidated"
            else f"{scope.label} · CNPJ {scope.cnpj}"
        )
        for scope in scopes
    }
    key = f"portfolio_analysis_scopes::{portfolio_id}"
    current = [value for value in st.session_state.get(key, values) if value in values]
    if not current:
        current = values
    st.session_state[key] = current
    selected_values = st.multiselect(
        "Escopos exibidos",
        options=values,
        key=key,
        format_func=lambda value: labels.get(value, str(value)),
        placeholder="Selecione o consolidado e/ou fundos individuais",
    )
    selected = set(selected_values)
    return tuple(scope for scope in scopes if scope.value in selected)


def _render_scoped_views(
    selected_scopes: tuple[PortfolioAnalysisScope, ...],
    renderer: Callable[[PortfolioAnalysisScope], None],
) -> None:
    if len(selected_scopes) == 1:
        renderer(selected_scopes[0])
        return
    scope_tabs = st.tabs([scope.label for scope in selected_scopes])
    for scope_tab, scope in zip(scope_tabs, selected_scopes, strict=False):
        with scope_tab:
            renderer(scope)


def _render_scope_header(scope: PortfolioAnalysisScope) -> None:
    if scope.kind == "consolidated":
        detail = "Soma de todos os fundos carregados na seleção"
    else:
        detail = f"Fundo individual · CNPJ {scope.cnpj}"
    st.markdown(
        f"""
<div class="portfolio-scope-current">
  <span>{escape(detail)}</span>
  <strong>{escape(scope.label)}</strong>
</div>
""",
        unsafe_allow_html=True,
    )


def _base_scope_lookup(
    *,
    analysis: PortfolioAnalysisData,
    selected_portfolio: PortfolioRecord,
) -> dict[str, Any]:
    return {
        option.value: option
        for option in somatorio_tab._build_base_scope_options(
            display_outputs=analysis.outputs,
            selected_portfolio=selected_portfolio,
        )
    }


def _scope_monitor(analysis: PortfolioAnalysisData, scope: PortfolioAnalysisScope) -> pd.DataFrame:
    if analysis.monitor_outputs is None:
        return pd.DataFrame()
    if scope.kind == "consolidated":
        return analysis.monitor_outputs.consolidated_monitor
    return analysis.monitor_outputs.fund_monitor.get(scope.cnpj, pd.DataFrame())


def _scope_cohorts(analysis: PortfolioAnalysisData, scope: PortfolioAnalysisScope) -> pd.DataFrame:
    if analysis.monitor_outputs is None:
        return pd.DataFrame()
    if scope.kind == "consolidated":
        return analysis.monitor_outputs.consolidated_cohorts
    return analysis.monitor_outputs.fund_cohorts.get(scope.cnpj, pd.DataFrame())


def _render_structure_tab(
    *,
    analysis: PortfolioAnalysisData,
    selected_scopes: tuple[PortfolioAnalysisScope, ...],
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
) -> None:
    st.markdown("### Estrutura da carteira")
    st.caption(
        "Posição mais recente, PL por tipo de cota e base analítica histórica. "
        "Use as abas abaixo para alternar entre o consolidado e cada fundo."
    )
    cockpit_cnpjs = None
    if not any(scope.kind == "consolidated" for scope in selected_scopes):
        cockpit_cnpjs = {scope.cnpj for scope in selected_scopes if scope.kind == "fund"}
    monitoring_tab.render_portfolio_cockpit_snapshot(
        period=period,
        selected_portfolio=selected_portfolio,
        selected_cnpjs=cockpit_cnpjs,
    )
    base_scope_by_value = _base_scope_lookup(
        analysis=analysis,
        selected_portfolio=selected_portfolio,
    )

    def render_scope(scope: PortfolioAnalysisScope) -> None:
        _render_scope_header(scope)
        ime_tab._render_financial_snapshot_cards(scope.dashboard)
        ime_tab._render_structural_risk_section(
            scope.dashboard,
            slot_key=f"portfolio_structure::{selected_portfolio.id}::{scope.value}",
            show_return_section=False,
        )
        base_scope = base_scope_by_value.get(scope.value)
        st.markdown("#### Base analítica")
        if base_scope is None:
            st.caption("Base analítica não disponível para este escopo.")
        else:
            st.markdown(
                somatorio_tab._render_wide_table_html(
                    somatorio_tab._display_wide_table(base_scope.wide_df, compact=True)
                ),
                unsafe_allow_html=True,
            )
        with st.expander("Memória de cálculo e auditoria da estrutura", expanded=False):
            ime_tab._render_calculation_memory_section(
                scope.dashboard,
                slot_key=f"portfolio_structure_memory::{selected_portfolio.id}::{scope.value}",
            )

    _render_scoped_views(selected_scopes, render_scope)
    if analysis.dashboard_errors:
        with st.expander("Fundos não incluídos por falha no dashboard base", expanded=False):
            for cnpj, message in analysis.dashboard_errors.items():
                st.caption(f"{cnpj} — {message}")


def _render_credit_term_tab(
    *,
    analysis: PortfolioAnalysisData,
    selected_scopes: tuple[PortfolioAnalysisScope, ...],
    selected_portfolio: PortfolioRecord,
) -> None:
    st.markdown("### Crédito e prazo")
    st.caption(
        "A visão começa pelo vencimento dos direitos creditórios na competência mais recente; "
        "o prazo médio proxy permanece logo abaixo do gráfico."
    )

    def render_scope(scope: PortfolioAnalysisScope) -> None:
        _render_scope_header(scope)
        ime_tab._render_liquidity_risk_section(
            scope.dashboard,
            show_duration_history_chart=True,
        )
        monitor = _scope_monitor(analysis, scope)
        if monitor.empty:
            st.caption("Histórico de carteira bruta ex-360 indisponível para este escopo.")
            return
        credit_tab._chart_title(
            "Carteira Bruta ex-360 e crescimento YoY",
            credit_tab.PORTFOLIO_GROWTH_NOTES,
        )
        st.altair_chart(portfolio_growth_chart(monitor), use_container_width=True)

    _render_scoped_views(selected_scopes, render_scope)

    selected_fund_cnpjs = {
        scope.cnpj for scope in selected_scopes if scope.kind == "fund" and scope.cnpj
    }
    comparison_funds = {
        cnpj: monitor
        for cnpj, monitor in (analysis.monitor_outputs.fund_monitor if analysis.monitor_outputs else {}).items()
        if cnpj in selected_fund_cnpjs
    }
    if len(comparison_funds) > 1:
        st.markdown("#### Comparação de duration")
        include_consolidated = any(scope.kind == "consolidated" for scope in selected_scopes)
        st.caption(
            "Uma linha por fundo selecionado"
            + (" e a linha do consolidado integral da carteira." if include_consolidated else ".")
        )
        st.altair_chart(
            duration_chart(
                analysis.monitor_outputs.consolidated_monitor if include_consolidated else pd.DataFrame(),
                comparison_funds,
            ),
            use_container_width=True,
        )


def _render_delinquency_tab(
    *,
    analysis: PortfolioAnalysisData,
    selected_scopes: tuple[PortfolioAnalysisScope, ...],
    selected_portfolio: PortfolioRecord,
) -> None:
    st.markdown("### Inadimplência")
    st.caption(
        "PDD, cobertura, aging, inadimplência over, NPL, roll rates e cohorts no mesmo escopo selecionado."
    )

    def render_scope(scope: PortfolioAnalysisScope) -> None:
        _render_scope_header(scope)
        ime_tab._render_credit_risk_section(scope.dashboard)
        monitor = _scope_monitor(analysis, scope)
        if monitor.empty:
            st.caption("Monitor de inadimplência indisponível para este escopo.")
            return

        credit_tab._chart_title("NPL ex-360 por severidade", credit_tab.NPL_SEVERITY_NOTES)
        st.altair_chart(npl_severity_chart(monitor), use_container_width=True)
        credit_tab._chart_title("Roll rates", credit_tab.ROLL_RATES_NOTES)
        st.altair_chart(roll_rates_chart(monitor), use_container_width=True)

        research_key = (
            "consolidado::"
            if scope.kind == "consolidated"
            else credit_tab._research_scope_key("fundo", scope.cnpj)
        )
        roll_df = credit_tab._filter_research_scope(
            getattr(analysis.research_outputs, "roll_seasonality", pd.DataFrame()),
            research_key,
        )
        if not roll_df.empty:
            credit_tab._render_research_roll_charts(
                roll_df,
                key=f"portfolio_delinquency_roll::{selected_portfolio.id}::{scope.value}",
            )

        credit_tab._chart_title("Cohorts recentes", credit_tab._cohort_notes())
        st.altair_chart(cohort_chart(_scope_cohorts(analysis, scope)), use_container_width=True)

    _render_scoped_views(selected_scopes, render_scope)
    with st.expander("Auditoria e conciliações de inadimplência", expanded=False):
        credit_tab._render_audit(
            analysis.outputs,
            analysis.monitor_outputs,
            analysis.research_outputs,
            analysis.verification_report,
            compact=True,
        )
    credit_tab._render_methodology(analysis.research_outputs)


def _render_returns_tab(
    *,
    analysis: PortfolioAnalysisData,
    selected_scopes: tuple[PortfolioAnalysisScope, ...],
    selected_portfolio: PortfolioRecord,
) -> None:
    st.markdown("### Rentabilidade")
    fund_monthly = getattr(analysis.outputs, "fund_monthly", {}) or {}
    available_cnpjs = list(fund_monthly)
    selected_cnpjs = [
        scope.cnpj
        for scope in selected_scopes
        if scope.kind == "fund" and scope.cnpj in fund_monthly
    ]
    fund_options = selected_cnpjs or available_cnpjs
    if not fund_options:
        st.info("Sem fundos individuais carregados para a rentabilidade por série.")
        return

    labels = {
        cnpj: (
            f"{short_fund_name(somatorio_tab._fund_name_from_frame(fund_monthly[cnpj], fallback=cnpj))} "
            f"· CNPJ {cnpj}"
        )
        for cnpj in fund_options
    }
    selected_cnpj = st.selectbox(
        "Fundo da rentabilidade",
        options=fund_options,
        key=f"portfolio_returns_fund::{selected_portfolio.id}",
        format_func=lambda value: labels.get(value, str(value)),
        help="A rentabilidade por série é exibida por fundo; não há média entre séries de CNPJs diferentes.",
    )
    selected_scope = next(
        (scope for scope in analysis.scopes if scope.kind == "fund" and scope.cnpj == selected_cnpj),
        None,
    )
    monitor = (
        analysis.monitor_outputs.fund_monitor.get(selected_cnpj, pd.DataFrame())
        if analysis.monitor_outputs is not None
        else pd.DataFrame()
    )
    if not monitor.empty:
        credit_tab._render_selected_fund_context(monitor, cnpj=selected_cnpj)
    elif selected_scope is not None:
        _render_scope_header(selected_scope)
    else:
        st.markdown(f"**{escape(labels[selected_cnpj])}**")

    credit_tab._render_fund_return_table(outputs=analysis.outputs, cnpj=selected_cnpj)
    if selected_scope is not None:
        ime_tab._render_quota_return_section(
            selected_scope.dashboard,
            slot_key=f"portfolio_returns::{selected_portfolio.id}::{selected_cnpj}",
            return_months=12,
            show_table=False,
            selector_label="Classes no histórico acumulado base 100",
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
