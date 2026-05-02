from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from services.ime_period import ImePeriodSelection, build_custom_period, current_default_end_month, month_options, shift_month
from services.meli_credit_monitor import (
    build_meli_chart_axis_table,
    build_meli_methodology_table,
    build_meli_monitor_outputs,
    latest_row,
)
from services.meli_credit_monitor_ppt_export import build_dashboard_meli_pptx_bytes
from services.meli_credit_monitor_visuals import (
    cohort_chart,
    duration_chart,
    npl_severity_chart,
    portfolio_growth_chart,
    roll_rates_chart,
)
from services.mercado_livre_dashboard import (
    build_mercado_livre_outputs,
    extract_official_pl_history_from_wide_csv,
    load_outputs_from_cache,
    portfolio_identity_key,
    save_outputs_to_cache,
)
from services.portfolio_store import PortfolioRecord
from tabs import tab_fidc_ime as ime_tab
from tabs.ime_portfolio_support import (
    enrich_portfolio_funds_with_catalog,
    get_portfolio_status_caption,
    list_saved_portfolios,
    load_fidc_catalog_cached,
)
from tabs.tab_fidc_ime_carteira import (
    _build_loaded_dashboards_by_cnpj,
    _execute_portfolio_load_for_funds,
    _get_portfolio_runtime_state,
)


_DASHBOARD_MELI_CSS = """
<style>
.meli-kpi-grid {
    display: grid;
    grid-template-columns: repeat(6, minmax(120px, 1fr));
    gap: 8px;
    margin: 0.35rem 0 1rem 0;
}
.meli-kpi-card {
    border: 1px solid #E5E5E5;
    border-radius: 8px;
    padding: 9px 10px;
    background: #FFFFFF;
}
.meli-kpi-label {
    color: #6f7a87;
    font-size: 0.72rem;
    line-height: 1.2;
    margin-bottom: 4px;
}
.meli-kpi-value {
    color: #000000;
    font-size: 1.02rem;
    font-weight: 700;
    line-height: 1.2;
}
.meli-period-bar {
    display: flex;
    flex-wrap: nowrap;
    gap: 6px;
    overflow-x: auto;
    padding-bottom: 4px;
    margin: 0 0 0.6rem 0;
    scrollbar-width: thin;
}
.meli-period-bar span {
    align-items: center;
    background: #f8f9fa;
    border: 1px solid #eceff3;
    border-radius: 999px;
    color: #5a5a5a;
    display: inline-flex;
    flex: 0 0 auto;
    font-size: 0.72rem;
    gap: 4px;
    line-height: 1.2;
    padding: 4px 7px;
    white-space: nowrap;
}
.meli-period-bar strong {
    color: #212529;
    font-weight: 500;
}
.meli-chart-title {
    color: #000000;
    font-size: clamp(16px, 1.45vw, 18px);
    font-weight: 600;
    line-height: 1.25;
    margin: 8px 0 3px 0;
}
.meli-chart-subtitle {
    color: #8C8C8C;
    font-size: 12px;
    line-height: 1.35;
    margin: 0 0 8px 0;
}
@media (max-width: 1180px) {
    .meli-kpi-grid {
        grid-template-columns: repeat(3, minmax(120px, 1fr));
    }
}
@media (max-width: 760px) {
    .meli-kpi-grid {
        grid-template-columns: repeat(2, minmax(120px, 1fr));
    }
}
</style>
"""


def render_tab_dashboard_meli(period: ImePeriodSelection | None = None) -> None:
    st.markdown(ime_tab._FIDC_REPORT_CSS, unsafe_allow_html=True)
    st.markdown(_DASHBOARD_MELI_CSS, unsafe_allow_html=True)

    portfolios = list_saved_portfolios()
    catalog_df = load_fidc_catalog_cached()
    selected_period = _render_period_panel(period)
    selected_portfolio = _render_portfolio_controls(portfolios)
    if selected_portfolio is None:
        st.info("Salve uma carteira no Somatório FIDCs para usar o Dashboard MELI.")
        return
    selected_portfolio = _enrich_portfolio_record(selected_portfolio=selected_portfolio, catalog_df=catalog_df)
    runtime_state = _get_portfolio_runtime_state(selected_portfolio=selected_portfolio, period=selected_period)
    results = runtime_state.get("results") or {}
    session_key = _outputs_session_key(selected_portfolio=selected_portfolio, period=selected_period)

    if st.session_state.pop("_dashboard_meli_load_requested", False):
        cached_outputs = load_outputs_from_cache(
            portfolio_id=selected_portfolio.id,
            period_key=selected_period.cache_key,
            portfolio_funds=selected_portfolio.funds,
        )
        if cached_outputs is not None:
            st.session_state[session_key] = cached_outputs
            st.session_state[f"{session_key}::source"] = "cache"
            st.toast("Base do Dashboard MELI reutilizada do storage.")
            st.rerun()
        _execute_portfolio_load_for_funds(
            selected_portfolio=selected_portfolio,
            period=selected_period,
            funds=tuple(selected_portfolio.funds),
            existing_results=None,
        )
        st.rerun()

    session_outputs = st.session_state.get(session_key)
    if session_outputs is not None:
        _render_outputs(
            outputs=session_outputs,
            selected_portfolio=selected_portfolio,
            period=selected_period,
            storage_source=str(st.session_state.get(f"{session_key}::source") or "cache"),
        )
        return

    if not results:
        _render_status_bar(selected_portfolio=selected_portfolio, period=selected_period, outputs=None, storage_source="não carregado")
        st.info("Clique em **Carregar dashboard** para montar as visões MELI.")
        return

    dashboards_by_cnpj, dashboard_errors = _build_loaded_dashboards_by_cnpj(
        selected_portfolio=selected_portfolio,
        results=results,
    )
    if dashboard_errors:
        with st.expander("Fundos sem dashboard base", expanded=False):
            for cnpj, message in dashboard_errors.items():
                st.caption(f"**{cnpj}** - {message}")
    if not dashboards_by_cnpj:
        _render_status_bar(selected_portfolio=selected_portfolio, period=selected_period, outputs=None, storage_source="não carregado")
        st.warning("Nenhum fundo carregado com sucesso para montar o Dashboard MELI.")
        return

    outputs = build_mercado_livre_outputs(
        portfolio_id=selected_portfolio.id,
        portfolio_name=selected_portfolio.name,
        dashboards_by_cnpj=dashboards_by_cnpj,
        period_label=selected_period.label,
        official_pl_by_cnpj=_build_official_pl_by_cnpj(results=results, cnpjs=list(dashboards_by_cnpj)),
    )
    save_outputs_to_cache(
        outputs,
        portfolio_id=selected_portfolio.id,
        period_key=selected_period.cache_key,
        portfolio_funds=selected_portfolio.funds,
    )
    st.session_state[session_key] = outputs
    st.session_state[f"{session_key}::source"] = "recalculado"
    _render_outputs(outputs=outputs, selected_portfolio=selected_portfolio, period=selected_period, storage_source="recalculado")


def _render_period_panel(global_period: ImePeriodSelection | None = None) -> ImePeriodSelection:
    end_month = current_default_end_month()
    options = ("12M", "24M", "36M", "YTD", "Customizado")
    selected = st.radio(
        "Janela do Dashboard MELI",
        options=options,
        index=options.index("24M"),
        horizontal=True,
        key="dashboard_meli_load_window",
        help="Use 24M ou 36M para ler variação anual, roll rates e cohorts com mais contexto.",
    )
    if selected == "Customizado":
        max_options = month_options(end_month, months_back=119)
        default_start = global_period.start_month if global_period is not None else shift_month(end_month, -23)
        default_end = global_period.end_month if global_period is not None else end_month
        if default_start not in max_options:
            default_start = shift_month(end_month, -23)
        if default_end not in max_options:
            default_end = end_month
        left, right = st.columns(2)
        with left:
            start_month = st.selectbox(
                "Competência inicial",
                options=max_options,
                index=max_options.index(default_start),
                key="dashboard_meli_period_start",
                format_func=_format_month_label,
            )
        end_candidates = [value for value in max_options if value >= start_month]
        if default_end not in end_candidates:
            default_end = end_candidates[-1]
        with right:
            end_month_selected = st.selectbox(
                "Competência final",
                options=end_candidates,
                index=end_candidates.index(default_end),
                key="dashboard_meli_period_end",
                format_func=_format_month_label,
            )
        selected_period = build_custom_period(start_month=start_month, end_month=end_month_selected)
    elif selected == "YTD":
        selected_period = build_custom_period(start_month=date(end_month.year, 1, 1), end_month=end_month)
    else:
        months = int(selected.removesuffix("M"))
        selected_period = build_custom_period(start_month=shift_month(end_month, -(months - 1)), end_month=end_month)
    st.caption(f"Período de carga: {_format_month_label(selected_period.start_month)} -> {_format_month_label(selected_period.end_month)} · {selected_period.month_count} competências")
    return selected_period


def _render_portfolio_controls(portfolios: list[PortfolioRecord]) -> PortfolioRecord | None:
    if not portfolios:
        return None
    try:
        left, right = st.columns([5.0, 1.6], vertical_alignment="bottom")
    except TypeError:
        left, right = st.columns([5.0, 1.6])
    options = [portfolio.id for portfolio in portfolios]
    labels = {portfolio.id: f"{portfolio.name} · {len(portfolio.funds)} fundo(s)" for portfolio in portfolios}
    default_id = st.session_state.get("dashboard_meli_portfolio_active_id")
    if default_id not in options:
        preferred = next(
            (
                portfolio.id
                for portfolio in portfolios
                if "mercado" in portfolio.name.strip().lower() or "meli" in portfolio.name.strip().lower()
            ),
            None,
        )
        default_id = preferred or options[0]
        st.session_state["dashboard_meli_portfolio_active_id"] = default_id
    with left:
        selected_id = st.selectbox(
            "Carteira salva",
            options=options,
            index=options.index(default_id),
            key="dashboard_meli_portfolio_active_id",
            format_func=lambda value: labels.get(value, value),
        )
    with right:
        if st.button("Carregar dashboard", key="dashboard_meli_load_button", type="secondary", use_container_width=True):
            st.session_state["_dashboard_meli_load_requested"] = True
            st.rerun()
    st.caption(get_portfolio_status_caption())
    return next((portfolio for portfolio in portfolios if portfolio.id == selected_id), None)


def _render_outputs(*, outputs, selected_portfolio: PortfolioRecord, period: ImePeriodSelection, storage_source: str) -> None:  # noqa: ANN001
    _render_status_bar(selected_portfolio=selected_portfolio, period=period, outputs=outputs, storage_source=storage_source)
    monitor_outputs = build_meli_monitor_outputs(outputs)
    _render_guide()
    pptx_bytes = build_dashboard_meli_pptx_bytes(monitor_outputs)
    st.download_button(
        "Baixar gráficos PPTX",
        data=pptx_bytes,
        file_name=f"dashboard_meli_graficos_{_safe_file_token(selected_portfolio.name)}.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        key=f"dashboard_meli_pptx_download::{selected_portfolio.id}",
        use_container_width=True,
    )
    _render_kpis(monitor_outputs.consolidated_monitor)
    main_tab, funds_tab, audit_tab = st.tabs(["Consolidado", "Fundos individuais", "Auditoria"])
    with main_tab:
        _render_consolidated_dashboard(monitor_outputs)
    with funds_tab:
        _render_fund_dashboards(monitor_outputs)
    with audit_tab:
        _render_audit(monitor_outputs)
    _render_methodology()


def _render_consolidated_dashboard(monitor_outputs) -> None:  # noqa: ANN001
    _chart_title(
        "Roll rates",
        "Eixo esquerdo: roll rate em %. Sem eixo direito. 61-90 usa carteira a vencer de três meses antes; 151-180 usa seis meses antes.",
    )
    _chart_note("O gráfico responde: de cada R$ 100 expostos no passado, quanto apareceu em atraso mais severo depois?")
    st.altair_chart(roll_rates_chart(monitor_outputs.consolidated_monitor), use_container_width=True)

    _chart_title("NPL ex-360 por severidade", "Eixo esquerdo: NPL 1-90d e 91-360d como % da carteira ex-360. Sem eixo direito.")
    _chart_note(
        "A carteira ex-360 remove vencidos acima de 360 dias do denominador; as barras separam o NPL remanescente entre atraso inicial (1-90d) e atraso maduro (91-360d)."
    )
    st.altair_chart(npl_severity_chart(monitor_outputs.consolidated_monitor), use_container_width=True)

    _chart_title("Carteira ex-360 e crescimento YoY", "Painéis empilhados com títulos e eixos próprios, ambos ajustados à largura da página.")
    _chart_note("Carteira ex-360 exclui créditos vencidos acima de 360 dias; YoY compara o mês atual com o mesmo mês do ano anterior.")
    st.altair_chart(portfolio_growth_chart(monitor_outputs.consolidated_monitor), use_container_width=True)

    _chart_title("Duration por FIDC", "Eixo esquerdo: duration em meses. Sem eixo direito; consolidado ponderado por saldo.")
    _duration_notes()
    st.altair_chart(duration_chart(monitor_outputs.consolidated_monitor, monitor_outputs.fund_monitor), use_container_width=True)

    _chart_title("Cohorts recentes", "Eixo esquerdo: % do saldo a vencer em 30 dias. Sem eixo direito.")
    _cohort_notes()
    st.altair_chart(cohort_chart(monitor_outputs.consolidated_cohorts), use_container_width=True)


def _render_fund_dashboards(monitor_outputs) -> None:  # noqa: ANN001
    if not monitor_outputs.fund_monitor:
        st.info("Sem fundos individuais carregados.")
        return
    for cnpj, monitor in monitor_outputs.fund_monitor.items():
        name = str(monitor["fund_name"].dropna().iloc[0]) if not monitor.empty and "fund_name" in monitor.columns and monitor["fund_name"].notna().any() else cnpj
        with st.expander(name, expanded=False):
            _chart_title("Roll rates", "Eixo esquerdo: roll rate em %. Sem eixo direito; denominador é carteira a vencer defasada.")
            _chart_note("O gráfico responde: de cada R$ 100 expostos no passado, quanto apareceu em atraso mais severo depois?")
            st.altair_chart(roll_rates_chart(monitor), use_container_width=True)

            _chart_title("NPL ex-360 por severidade", "Eixo esquerdo: NPL 1-90d e 91-360d como % da carteira ex-360. Sem eixo direito.")
            _chart_note(
                "A carteira ex-360 remove vencidos acima de 360 dias do denominador; as barras separam o NPL remanescente entre atraso inicial (1-90d) e atraso maduro (91-360d)."
            )
            st.altair_chart(npl_severity_chart(monitor), use_container_width=True)

            _chart_title("Carteira ex-360 e crescimento YoY", "Painéis empilhados com títulos e eixos próprios, ambos ajustados à largura da página.")
            _chart_note("Carteira ex-360 exclui créditos vencidos acima de 360 dias; YoY compara o mês atual com o mesmo mês do ano anterior.")
            st.altair_chart(portfolio_growth_chart(monitor), use_container_width=True)

            _chart_title("Duration", "Eixo esquerdo: duration em meses. Sem eixo direito.")
            _duration_notes()
            st.altair_chart(duration_chart(pd.DataFrame(), {cnpj: monitor}), use_container_width=True)

            _chart_title("Cohorts recentes", "Eixo esquerdo: % do saldo a vencer em 30 dias. Sem eixo direito.")
            _cohort_notes()
            st.altair_chart(cohort_chart(monitor_outputs.fund_cohorts.get(cnpj, pd.DataFrame())), use_container_width=True)


def _render_kpis(monitor_df: pd.DataFrame) -> None:
    row = latest_row(monitor_df)
    cards = [
        ("Carteira ex-360", _format_brl_compact(row.get("carteira_ex360"))),
        ("NPL 1-90 / carteira", _format_percent(row.get("npl_1_90_pct"))),
        ("NPL 91-360 / carteira", _format_percent(row.get("npl_91_360_pct"))),
        ("Roll 61-90 M-3", _format_percent(row.get("roll_61_90_m3_pct"))),
        ("Roll 151-180 M-6", _format_percent(row.get("roll_151_180_m6_pct"))),
        ("Duration", f"{_format_decimal(row.get('duration_months'), 1)} meses"),
    ]
    html = ["<div class='meli-kpi-grid'>"]
    for label, value in cards:
        html.append(
            f"<div class='meli-kpi-card'><div class='meli-kpi-label'>{escape(label)}</div><div class='meli-kpi-value'>{escape(value)}</div></div>"
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _render_audit(monitor_outputs) -> None:  # noqa: ANN001
    if monitor_outputs.warnings:
        with st.expander("Warnings do monitor", expanded=False):
            for warning in monitor_outputs.warnings:
                st.caption(warning)
    audit = monitor_outputs.audit_table.copy()
    if audit.empty:
        st.info("Sem tabela de auditoria.")
        return
    display = audit.copy()
    for column in [col for col in display.columns if col.endswith("_pct")]:
        display[column] = display[column].map(_format_percent)
    for column in ["carteira_ex360", "carteira_a_vencer", "npl_1_90", "npl_91_360", "roll_61_90_m3_den", "roll_151_180_m6_den"]:
        if column in display.columns:
            display[column] = display[column].map(_format_brl_compact)
    if "duration_months" in display.columns:
        display["duration_months"] = display["duration_months"].map(lambda value: f"{_format_decimal(value, 1)} meses")
    st.dataframe(display, use_container_width=True)


def _render_methodology() -> None:
    with st.expander("Metodologia, fórmulas e fontes dos indicadores", expanded=False):
        st.markdown(
            """
O painel usa dados mensais já compilados no Somatório FIDCs. No consolidado, valores absolutos são somados primeiro e percentuais são recalculados depois.

**Leitura dos gráficos:** cada gráfico informa explicitamente o eixo usado, a unidade e se há eixo direito. Os rótulos finais mostram o último ponto calculável de cada série.

**Roll rates:** mostram migração de risco. A pergunta é: quanto de uma base que estava exposta em um mês anterior apareceu em um bucket de atraso específico depois? Exemplo: `Roll 61-90 M-3 = atraso 61-90 no mês t / carteira a vencer no mês t-3`.

**NPL ex-360 por severidade:** primeiro o modelo baixa conceitualmente da carteira os vencidos acima de 360 dias. Depois, sobre a carteira remanescente, separa o NPL em `1-90d` (atraso inicial) e `91-360d` (atraso maduro). Fórmulas: `NPL 1-90d / carteira ex-360` e `NPL 91-360d / carteira ex-360`.

**Carteira ex-360 e YoY:** a carteira ex-360 remove vencidos acima de 360 dias. O YoY mostra crescimento contra a mesma competência do ano anterior, não contra o mês imediatamente anterior.

**Duration:** é prazo médio ponderado por saldo na malha de vencimentos. Fórmula: `duration_dias = Σ(saldo_bucket × prazo_proxy_bucket) / Σ(saldo_bucket)`. O gráfico exibe `duration_meses = duration_dias / 30,4375`. Exemplo: saldo a vencer entre 61 e 90 dias usa `75,5 dias`, o ponto médio da faixa.

**Cohorts recentes:** cada linha acompanha uma safra proxy. Como o Informe Mensal não traz originação contrato a contrato, a safra é definida pelo saldo que estava a vencer em até 30 dias no mês-base. Esse saldo vira o denominador fixo da linha.

**Exemplo de cohort:** se em jul/25 havia R$ 100 milhões a vencer em até 30 dias, a linha `Jul-25` usa R$ 100 milhões como base em todos os pontos. Se em ago/25 aparecem R$ 4 milhões em atraso até 30 dias, `M1 = 4 / 100 = 4,0%`. Se em set/25 aparecem R$ 6 milhões em atraso 31-60 dias, `M2 = 6 / 100 = 6,0%`. Se em out/25 aparecem R$ 5 milhões em atraso 61-90 dias, `M3 = 5 / 100 = 5,0%`.

**Como ler cohorts:** M1, M2, M3... são meses de maturação depois da safra, não competências calendário. Compare `M3` de uma safra com `M3` de outra safra. Linha mais alta no mesmo M indica que uma parcela maior daquela safra migrou para atraso.
            """
        )
        st.markdown("**Eixos dos gráficos**")
        st.dataframe(build_meli_chart_axis_table(), use_container_width=True, hide_index=True)
        st.markdown("**Fórmulas e fontes das métricas**")
        st.dataframe(build_meli_methodology_table(), use_container_width=True, hide_index=True)


def _render_status_bar(*, selected_portfolio: PortfolioRecord, period: ImePeriodSelection, outputs, storage_source: str) -> None:  # noqa: ANN001
    if outputs is not None and getattr(outputs, "consolidated_monthly", pd.DataFrame()).empty is False:
        loaded = _loaded_period_label(outputs)
        ok = len(outputs.fund_monthly)
    else:
        loaded = "N/D"
        ok = 0
    total = len(selected_portfolio.funds)
    identity = portfolio_identity_key(selected_portfolio.funds, fallback=selected_portfolio.id)
    st.markdown(
        f"""
<div class="meli-period-bar">
  <span><strong>Carteira:</strong> {escape(selected_portfolio.name)}</span>
  <span><strong>Período solicitado:</strong> {escape(period.label)}</span>
  <span><strong>Fundos carregados:</strong> {ok}/{total}</span>
  <span><strong>Período carregado:</strong> {escape(loaded)}</span>
  <span><strong>Storage:</strong> {escape(storage_source)}</span>
  <span><strong>Identidade:</strong> {escape(identity)}</span>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_guide() -> None:
    with st.expander("Como usar e interpretar o Dashboard MELI", expanded=False):
        st.markdown(
            """
1. Selecione a carteira salva de FIDCs de crédito do Mercado Livre e carregue uma janela longa, preferencialmente 24M ou 36M.
2. Comece pelos roll rates: eles mostram a velocidade de deterioração sobre a carteira a vencer defasada, não apenas o estoque vencido.
3. Use NPL ex-360 por severidade para separar atraso inicial (1-90d) de atraso mais maduro (91-360d), sempre depois da baixa conceitual dos vencidos acima de 360 dias.
4. Confira carteira ex-360 e crescimento para saber se melhora de NPL vem de qualidade ou de efeito denominador.
5. Use cohorts para comparar safras recentes contra a própria curva de maturação M1-M6.

O painel usa os dados já compilados no Somatório FIDCs. Percentuais consolidados são sempre recalculados a partir da soma dos numeradores e denominadores.
            """
        )


def _chart_title(title: str, subtitle: str) -> None:
    st.markdown(f"<div class='meli-chart-title'>{escape(title)}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='meli-chart-subtitle'>{escape(subtitle)}</div>", unsafe_allow_html=True)


def _chart_note(text: str) -> None:
    st.markdown(f"<div class='meli-chart-subtitle'>{escape(text)}</div>", unsafe_allow_html=True)


def _cohort_notes() -> None:
    notes = [
        "Cada linha acompanha uma safra proxy: o saldo que estava a vencer em até 30 dias no mês-base.",
        "Exemplo: se a safra Jul-25 tinha R$ 100 milhões a vencer em até 30 dias, esse R$ 100 milhões vira a base fixa da linha.",
        "Se em Ago-25 surgem R$ 4 milhões em atraso até 30d, M1 = 4 / 100 = 4,0%; se em Set-25 surgem R$ 6 milhões em atraso 31-60d, M2 = 6 / 100 = 6,0%.",
        "M1, M2, M3... são meses de maturação depois da safra, não competências calendário; compare sempre o mesmo M entre safras.",
        "Linha mais alta no mesmo M indica pior deterioração relativa daquela safra.",
    ]
    for note in notes:
        _chart_note(note)


def _duration_notes() -> None:
    notes = [
        "Fórmula: duration_dias = Σ(saldo de cada faixa de vencimento × prazo proxy da faixa) ÷ Σ(saldos das faixas).",
        "O gráfico mostra duration_meses = duration_dias ÷ 30,4375; não é mediana nem prazo contratual simples.",
        "Exemplo: um crédito a vencer entre 61 e 90 dias usa 75,5 dias como prazo proxy, que é o ponto médio (61 + 90) ÷ 2.",
    ]
    for note in notes:
        _chart_note(note)


def _outputs_session_key(*, selected_portfolio: PortfolioRecord, period: ImePeriodSelection) -> str:
    identity = portfolio_identity_key(selected_portfolio.funds, fallback=selected_portfolio.id)
    return f"dashboard_meli_outputs::{identity}::{period.cache_key}"


def _build_official_pl_by_cnpj(*, results: dict[str, dict[str, Any]], cnpjs: list[str]) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for cnpj in cnpjs:
        payload = results.get(cnpj) or {}
        result = payload.get("result")
        wide_csv_path = getattr(result, "wide_csv_path", None)
        if wide_csv_path is None:
            continue
        frames[cnpj] = extract_official_pl_history_from_wide_csv(wide_csv_path)
    return frames


def _enrich_portfolio_record(*, selected_portfolio: PortfolioRecord, catalog_df: pd.DataFrame) -> PortfolioRecord:
    return PortfolioRecord(
        id=selected_portfolio.id,
        name=selected_portfolio.name,
        funds=tuple(enrich_portfolio_funds_with_catalog(selected_portfolio.funds, catalog_df)),
        created_at=selected_portfolio.created_at,
        updated_at=selected_portfolio.updated_at,
        notes=selected_portfolio.notes,
    )


def _loaded_period_label(outputs) -> str:  # noqa: ANN001
    frame = outputs.consolidated_monthly
    if frame is None or frame.empty or "competencia" not in frame.columns:
        return "N/D"
    competencias = frame["competencia"].astype(str).tolist()
    return f"{ime_tab._format_competencia_label(competencias[0])} a {ime_tab._format_competencia_label(competencias[-1])}"


def _format_month_label(value: date) -> str:
    return ime_tab._format_competencia_label(f"{value.month:02d}/{value.year}")


def _format_brl_compact(value: object) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "N/D"
    number = float(numeric)
    if abs(number) >= 1_000_000_000_000:
        return f"R$ {_format_decimal(number / 1_000_000_000, 1)} bi"
    if abs(number) >= 1_000_000:
        return f"R$ {_format_decimal(number / 1_000_000, 1)} mm"
    if abs(number) >= 1_000:
        return f"R$ {_format_decimal(number / 1_000, 1)} mil"
    return f"R$ {_format_decimal(number, 2)}"


def _format_percent(value: object) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "N/D"
    return f"{_format_decimal(float(numeric), 1)}%"


def _safe_file_token(value: object) -> str:
    text = str(value or "dashboard_meli").strip().lower()
    token = "".join(char if char.isalnum() else "_" for char in text)
    token = "_".join(part for part in token.split("_") if part)
    return token or "dashboard_meli"


def _format_decimal(value: object, decimals: int) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "N/D"
    return f"{float(numeric):,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")
