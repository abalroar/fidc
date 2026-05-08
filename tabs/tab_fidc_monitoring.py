from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from services.ime_loader import load_or_extract_informe
from services.ime_period import (
    ImePeriodSelection,
    build_custom_period,
    build_preset_period,
    current_default_end_month,
    display_month_count_for_period,
    parse_competencia_label,
    select_competencia_labels_for_period,
    shift_month,
)
from services.monitoring_metrics import (
    MonitoringTables,
    build_monitoring_tables,
    load_manual_overrides,
    read_wide_csv,
    save_manual_overrides,
)
from services.portfolio_store import PortfolioRecord
from services.variaveis_fnet import VARIAVEIS_FNET, competencia_columns, resolve_tag_path
from tabs.ime_portfolio_support import (
    build_portfolio_record_label_lookup,
    format_portfolio_cnpj,
    list_saved_portfolios,
    normalize_portfolio_fund_name,
)


_CACHE_MONTH_OPTIONS = (12, 15, 18, 24, 36, 48, 60, 72)
_CORE_AVAILABILITY_IDS = (
    "PATRLIQ/VL_SOM_PATRLIQ",
    "PATRLIQ/VL_PATRIM_LIQ",
    "APLIC_ATIVO/VL_SOM_APLIC_ATIVO",
    "APLIC_ATIVO/VL_CARTEIRA",
)


@dataclass(frozen=True)
class CockpitMetric:
    section: str
    label: str
    indicator: str
    unit: str
    aggregate: str


_COCKPIT_METRICS: tuple[CockpitMetric, ...] = (
    CockpitMetric("Tamanho e alocação", "PL", "PL (R$)", "R$ bruto", "sum"),
    CockpitMetric("Tamanho e alocação", "Direitos creditórios", "Dir Cred (R$ MM)", "R$ MM", "sum"),
    CockpitMetric("Tamanho e alocação", "Direitos creditórios / PL", "Dir Cred / PL", "ratio", "dircred_pl"),
    CockpitMetric("Inadimplência", "Over 30d / Crédito", "Vencidos Over 30 d / Crédito", "ratio", "over30_credito"),
    CockpitMetric("Inadimplência", "Over 60d / Crédito", "Vencidos Over 60 d / Crédito", "ratio", "over60_credito"),
    CockpitMetric("Inadimplência", "Over 90d / Crédito", "Vencidos Over 90 d / Crédito", "ratio", "over90_credito"),
    CockpitMetric("Inadimplência", "Over 180d / Crédito", "Vencidos Over 180 d / Crédito", "ratio", "over180_credito"),
    CockpitMetric("Inadimplência", "Over 360d / Crédito", "Vencidos Over 360 d / Crédito", "ratio", "over360_credito"),
    CockpitMetric("PDD e recompras", "PDD", "PDD (R$ MM)", "R$ MM", "sum"),
    CockpitMetric("PDD e recompras", "PDD / Crédito", "PDD / Crédito", "ratio", "pdd_credito"),
    CockpitMetric("PDD e recompras", "PDD / Over 90d", "PDD / Venc > 90 d", "ratio", "pdd_over90"),
    CockpitMetric("PDD e recompras", "Recompras / Crédito", "Recompras / Crédito", "ratio", "recompras_credito"),
    CockpitMetric("Cotas e retorno", "Cotas SR / PL", "Cotas SR / PL %", "%", "weighted_pl"),
    CockpitMetric("Cotas e retorno", "Cotas MZ / PL", "Cotas MZ / PL %", "%", "weighted_pl"),
    CockpitMetric("Cotas e retorno", "Cotas Sub / PL", "Cotas Sub / PL %", "%", "weighted_pl"),
    CockpitMetric("Cotas e retorno", "Rentabilidade SR a.m.", "Rentabilidade SR % a.m.", "%", "none"),
    CockpitMetric("Cotas e retorno", "Rentabilidade MZ a.m.", "Rentabilidade MZ % a.m.", "%", "none"),
    CockpitMetric("Cotas e retorno", "Rentabilidade Sub a.m.", "Rentabilidade Sub % a.m.", "%", "none"),
)


_CSS = """
<style>
.monitor-card-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0.35rem 0 0.7rem 0;
}
.monitor-chip {
    align-items: center;
    background: #f8f9fa;
    border: 1px solid #eceff3;
    border-radius: 999px;
    color: #5a5a5a;
    display: inline-flex;
    font-size: 0.74rem;
    gap: 5px;
    line-height: 1.2;
    padding: 5px 9px;
}
.monitor-chip strong {
    color: #212529;
    font-weight: 600;
}
.monitor-card-grid {
    display: grid;
    gap: 8px;
    grid-template-columns: repeat(6, minmax(110px, 1fr));
    margin: 0.55rem 0 0.75rem 0;
}
.monitor-kpi-card {
    background: #F7F7F7;
    border: 1px solid #E5E5E5;
    border-radius: 6px;
    min-height: 64px;
    padding: 8px 10px;
}
.monitor-kpi-label {
    color: #6B6B6B;
    font-size: 0.67rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    line-height: 1.15;
    text-transform: uppercase;
}
.monitor-kpi-value {
    color: #1F1F1F;
    font-size: 1.05rem;
    font-weight: 700;
    line-height: 1.25;
    margin-top: 6px;
}
.monitor-kpi-note {
    color: #8C8C8C;
    font-size: 0.68rem;
    line-height: 1.2;
    margin-top: 2px;
}
.monitor-wide-wrapper {
    overflow-x: auto;
    overflow-y: visible;
    max-width: 100%;
    padding-bottom: 5px;
    margin-bottom: 12px;
}
.monitor-wide-section {
    margin: 0 0 8px 0;
}
.monitor-wide-section summary {
    background: #000000;
    color: #FFFFFF;
    cursor: pointer;
    font-size: 13px;
    font-weight: 700;
    line-height: 1.25;
    list-style-position: inside;
    padding: 7px 9px;
    white-space: normal;
}
.monitor-wide-table {
    border-collapse: collapse;
    font-family: inherit;
    font-size: 12px;
    table-layout: fixed;
    width: 100%;
}
.monitor-wide-table th {
    background: #FFFFFF;
    border-bottom: 1px solid #3F3F3F;
    color: #000000;
    font-weight: 600;
    padding: 6px 8px;
    position: sticky;
    text-align: right;
    top: 0;
    white-space: normal;
    z-index: 2;
}
.monitor-wide-table th.label-col,
.monitor-wide-table td.label {
    text-align: left;
}
.monitor-wide-table td {
    border-bottom: 1px solid #E5E5E5;
    color: #3F3F3F;
    line-height: 1.22;
    overflow-wrap: anywhere;
    padding: 4px 8px;
    text-align: right;
    vertical-align: top;
    white-space: normal;
    word-break: normal;
}
.monitor-wide-table td.label {
    color: #000000;
    font-weight: 500;
    padding-left: 14px;
}
.monitor-wide-table tr.destaque td {
    color: #000000;
    font-weight: 700;
}
.monitor-wide-table tr:hover td {
    background: #F4F1EA;
}
.monitor-fund-title {
    color: #1f1f1f;
    font-size: 1.02rem;
    font-weight: 700;
    line-height: 1.25;
    margin: 0.35rem 0 0.1rem 0;
}
.monitor-caption {
    color: #6f7a87;
    font-size: 0.78rem;
    line-height: 1.35;
    margin-bottom: 0.45rem;
}
@media (max-width: 1100px) {
    .monitor-card-grid {
        grid-template-columns: repeat(3, minmax(110px, 1fr));
    }
}
</style>
"""

_PT_MONTH_ABBR = {
    "01": "jan",
    "02": "fev",
    "03": "mar",
    "04": "abr",
    "05": "mai",
    "06": "jun",
    "07": "jul",
    "08": "ago",
    "09": "set",
    "10": "out",
    "11": "nov",
    "12": "dez",
}


def render_tab_fidc_monitoring(period: ImePeriodSelection | None = None) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown("## Monitoramento FIDCs")
    st.caption(
        "Cockpit comparativo de carteiras salvas. A carga usa o mesmo cache IME/FNET; "
        "a janela exibida ancora automaticamente na última competência realmente disponível."
    )

    if period is None:
        period = build_preset_period(end_month=current_default_end_month(), months=12)

    portfolios = list_saved_portfolios()
    if not portfolios:
        st.info("Crie uma carteira salva nas abas de carteira/Soma de FIDCs para usar o monitoramento.")
        return

    selected_portfolio = _render_portfolio_selector(portfolios)
    if selected_portfolio is None:
        return

    cache_months = _render_cache_horizon_control(selected_portfolio=selected_portfolio, period=period)
    load_period = _build_cache_load_period(period=period, cache_months=cache_months)

    _render_requested_load_chips(period=period, load_period=load_period, cache_months=cache_months, fund_count=len(selected_portfolio.funds))

    session_key = _session_key(selected_portfolio, period, cache_months)
    if st.button("Carregar / atualizar monitoramento", type="primary", key=f"{session_key}::load"):
        st.session_state[session_key] = _load_portfolio_monitoring(selected_portfolio, period, cache_months)
        st.rerun()

    outputs = st.session_state.get(session_key)
    if not outputs:
        st.info("Clique em **Carregar / atualizar monitoramento** para montar o cockpit com a carteira selecionada.")
        return

    success_outputs = [item for item in outputs if item.get("tables") is not None]
    error_outputs = [item for item in outputs if item.get("error")]
    if error_outputs:
        with st.expander("Fundos com falha de carga", expanded=False):
            for item in error_outputs:
                st.caption(f"**{item['display_name']}** · {item['cnpj']} — {item['error']}")
    if not success_outputs:
        st.warning("Nenhum fundo carregou dados suficientes para montar o monitoramento.")
        return

    _render_loaded_period_status(success_outputs, requested_period=period, load_period=load_period, cache_months=cache_months)

    cockpit_tab, trend_tab, fund_tab, raw_tab, overrides_tab = st.tabs(
        ["Cockpit", "Tendências", "Tabela por Fundo", "Dados brutos", "Overrides de Mezanino"]
    )
    with cockpit_tab:
        _render_cockpit_tab(success_outputs)
    with trend_tab:
        _render_comparison_tab(success_outputs)
    with fund_tab:
        _render_fund_boards_tab(success_outputs)
    with raw_tab:
        _render_raw_data_tab(success_outputs)
    with overrides_tab:
        _render_overrides_tab(success_outputs)


def _render_portfolio_selector(portfolios: list[PortfolioRecord]) -> PortfolioRecord | None:
    labels = build_portfolio_record_label_lookup(portfolios)
    portfolio_id = st.selectbox(
        "Carteira",
        options=[portfolio.id for portfolio in portfolios],
        format_func=lambda value: labels.get(value, value),
        key="monitoring_portfolio_id",
    )
    return next((portfolio for portfolio in portfolios if portfolio.id == portfolio_id), None)


def _render_cache_horizon_control(*, selected_portfolio: PortfolioRecord, period: ImePeriodSelection) -> int:
    target_months = display_month_count_for_period(period)
    recommended = max(target_months + 3, 15)
    options = sorted({*_CACHE_MONTH_OPTIONS, recommended, target_months})
    default_index = options.index(recommended)
    key = f"monitoring_cache_months::{selected_portfolio.id}"
    return int(
        st.selectbox(
            "Histórico a carregar no cache para esta carteira",
            options=options,
            index=default_index,
            format_func=lambda value: f"{value} meses",
            key=key,
            help=(
                "Não muda a janela exibida. Só aumenta a janela baixada/lida do cache para permitir "
                "ancorar a exibição no último mês realmente disponível e manter histórico adicional."
            ),
        )
    )


def _build_cache_load_period(*, period: ImePeriodSelection, cache_months: int) -> ImePeriodSelection:
    cache_months = max(int(cache_months), display_month_count_for_period(period))
    return build_custom_period(
        start_month=shift_month(period.end_month, -(cache_months - 1)),
        end_month=period.end_month,
    )


def _render_requested_load_chips(*, period: ImePeriodSelection, load_period: ImePeriodSelection, cache_months: int, fund_count: int) -> None:
    st.markdown(
        f"""
<div class="monitor-card-row">
  <span class="monitor-chip"><strong>Janela solicitada:</strong> {escape(_format_period_label(period))}</span>
  <span class="monitor-chip"><strong>Cache a carregar:</strong> {escape(_format_period_label(load_period))}</span>
  <span class="monitor-chip"><strong>Horizonte cache:</strong> {cache_months} meses</span>
  <span class="monitor-chip"><strong>Fundos:</strong> {fund_count}</span>
</div>
""",
        unsafe_allow_html=True,
    )


def _load_portfolio_monitoring(portfolio: PortfolioRecord, period: ImePeriodSelection, cache_months: int) -> list[dict[str, Any]]:
    progress = st.progress(0.0, text="Preparando monitoramento...")
    outputs: list[dict[str, Any]] = []
    total = len(portfolio.funds)
    load_period = _build_cache_load_period(period=period, cache_months=cache_months)
    for index, fund in enumerate(portfolio.funds, start=1):
        progress.progress(index / max(total, 1), text=f"{index}/{total} · {fund.display_name}")
        try:
            cached = load_or_extract_informe(
                cnpj_fundo=fund.cnpj,
                data_inicial=load_period.start_month,
                data_final=load_period.end_month,
            )
            wide_df = read_wide_csv(cached.result.wide_csv_path)
            all_competencias = _available_competencias_from_wide(wide_df)
            competencias = select_competencia_labels_for_period(all_competencias, period) or all_competencias
            overrides = load_manual_overrides(fund.cnpj)
            tables = build_monitoring_tables(wide_df, competencias, cnpj=fund.cnpj, overrides=overrides)
            outputs.append(
                {
                    "cnpj": fund.cnpj,
                    "display_name": normalize_portfolio_fund_name(fund.display_name, fund.cnpj),
                    "competencias": competencias,
                    "all_competencias": all_competencias,
                    "tables": tables,
                    "cache_status": cached.cache_status,
                    "cache_dir": str(cached.cache_dir),
                    "load_period_label": _format_period_label(load_period),
                }
            )
        except Exception as exc:  # noqa: BLE001
            outputs.append(
                {
                    "cnpj": fund.cnpj,
                    "display_name": normalize_portfolio_fund_name(fund.display_name, fund.cnpj),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    progress.empty()
    return outputs


def _available_competencias_from_wide(wide_df: pd.DataFrame) -> list[str]:
    competencias = competencia_columns(wide_df)
    if not competencias:
        return []
    core_paths = [resolve_tag_path(short_id, wide_df) for short_id in _CORE_AVAILABILITY_IDS]
    core_paths = [path for path in core_paths if path and path in wide_df.index]
    if not core_paths:
        return competencias

    available: list[str] = []
    for competencia in competencias:
        values = []
        for path in core_paths:
            row = wide_df.loc[path]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            values.append(row.get(competencia))
        numeric = pd.to_numeric(pd.Series(values), errors="coerce")
        if numeric.notna().any():
            available.append(competencia)
    return available or competencias


def _render_loaded_period_status(
    outputs: list[dict[str, Any]],
    *,
    requested_period: ImePeriodSelection,
    load_period: ImePeriodSelection,
    cache_months: int,
) -> None:
    latest = _portfolio_latest_competencia(outputs)
    display_span = _portfolio_display_span(outputs)
    latest_label = _format_competencia_label(latest) if latest else "-"
    display_label = display_span or "-"
    if latest:
        latest_date = parse_competencia_label(latest)
        if requested_period.end_month > latest_date:
            st.info(
                f"A competência solicitada {_format_month_date_label(requested_period.end_month)} ainda não está disponível nos dados carregados. "
                f"A janela exibida foi ancorada em {_format_competencia_label(latest)}."
            )
    st.markdown(
        f"""
<div class="monitor-card-row">
  <span class="monitor-chip"><strong>Janela exibida:</strong> {escape(display_label)}</span>
  <span class="monitor-chip"><strong>Última competência disponível:</strong> {escape(latest_label)}</span>
  <span class="monitor-chip"><strong>Cache carregado:</strong> {escape(_format_period_label(load_period))}</span>
  <span class="monitor-chip"><strong>Horizonte:</strong> {cache_months} meses</span>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_cockpit_tab(outputs: list[dict[str, Any]]) -> None:
    latest = _portfolio_latest_competencia(outputs)
    if not latest:
        st.info("Não há competência disponível para montar o cockpit.")
        return
    st.markdown("### Cockpit da carteira")
    st.caption("Valores por FIDC na última competência disponível. Percentuais consolidados são recalculados a partir de somas absolutas.")
    _render_cockpit_cards(outputs, latest)
    st.markdown(_render_cockpit_table_html(outputs, latest), unsafe_allow_html=True)
    with st.expander("Diagnóstico de carga e cache", expanded=False):
        st.dataframe(_build_cache_diagnostics_df(outputs), hide_index=True, use_container_width=True)


def _render_cockpit_cards(outputs: list[dict[str, Any]], latest: str) -> None:
    cards = [
        ("Competência", _format_competencia_label(latest), "último dado disponível"),
        ("Fundos com dados", f"{len(outputs)}", "carga concluída"),
        ("PL total", _format_metric_value(_aggregate_metric(CockpitMetric("", "", "PL (R$)", "R$ bruto", "sum"), outputs, latest), "R$ bruto"), "soma dos fundos"),
        ("DC / PL", _format_metric_value(_aggregate_metric(CockpitMetric("", "", "Dir Cred / PL", "ratio", "dircred_pl"), outputs, latest), "ratio"), "recalculado"),
        ("Over 90d", _format_metric_value(_aggregate_metric(CockpitMetric("", "", "Vencidos Over 90 d / Crédito", "ratio", "over90_credito"), outputs, latest), "ratio"), "sobre crédito"),
        ("PDD / Over 90d", _format_metric_value(_aggregate_metric(CockpitMetric("", "", "PDD / Venc > 90 d", "ratio", "pdd_over90"), outputs, latest), "ratio"), "cobertura"),
    ]
    html = ["<div class='monitor-card-grid'>"]
    for label, value, note in cards:
        html.append(
            "<div class='monitor-kpi-card'>"
            f"<div class='monitor-kpi-label'>{escape(label)}</div>"
            f"<div class='monitor-kpi-value'>{escape(value)}</div>"
            f"<div class='monitor-kpi-note'>{escape(note)}</div>"
            "</div>"
        )
    html.append("</div>")
    st.markdown("\n".join(html), unsafe_allow_html=True)


def _render_cockpit_table_html(outputs: list[dict[str, Any]], latest: str) -> str:
    fund_width = 128
    min_width = max(460 + fund_width * (len(outputs) + 1), 980)
    html = [f"<div class='monitor-wide-wrapper' style='min-width: 100%; --monitor-table-min-width: {min_width}px;'>"]
    by_section: dict[str, list[CockpitMetric]] = {}
    for metric in _COCKPIT_METRICS:
        by_section.setdefault(metric.section, []).append(metric)

    for section, metrics in by_section.items():
        html.append(f"<details class='monitor-wide-section' open style='min-width: {min_width}px;'>")
        html.append(f"<summary>{escape(section)}</summary>")
        html.append(f"<table class='monitor-wide-table' style='min-width: {min_width}px;'>")
        html.append("<colgroup><col style='width: 230px;'><col style='width: 120px;'>")
        html.extend(f"<col style='width: {fund_width}px;'>" for _ in outputs)
        html.append("</colgroup><thead><tr><th class='label-col'>Métrica</th><th>Consolidado</th>")
        for item in outputs:
            html.append(f"<th>{escape(_short_fund_label(str(item['display_name'])))}<br>{escape(format_portfolio_cnpj(str(item['cnpj']))[-8:])}</th>")
        html.append("</tr></thead><tbody>")
        for metric in metrics:
            row_class = "destaque" if metric.indicator in {"PL (R$)", "Vencidos Over 90 d / Crédito", "PDD / Venc > 90 d"} else ""
            html.append(f"<tr class='{row_class}'>")
            html.append(f"<td class='label'>{escape(metric.label)}</td>")
            html.append(f"<td>{escape(_format_metric_value(_aggregate_metric(metric, outputs, latest), metric.unit))}</td>")
            for item in outputs:
                value = _metric_numeric(item, metric.indicator, latest)
                html.append(f"<td>{escape(_format_metric_value(value, metric.unit))}</td>")
            html.append("</tr>")
        html.append("</tbody></table></details>")
    html.append("</div>")
    return "\n".join(html)


def _render_comparison_tab(outputs: list[dict[str, Any]]) -> None:
    options = [item[0] for item in VARIAVEIS_FNET]
    labels = {item[0]: item[1] for item in VARIAVEIS_FNET}
    default_id = "PATRLIQ/VL_SOM_PATRLIQ"
    selected_id = st.selectbox(
        "Variável a comparar",
        options=options,
        index=options.index(default_id) if default_id in options else 0,
        format_func=lambda value: f"{labels.get(value, value)} · {value}",
        key="monitoring_compare_variable",
    )
    chart_df = _comparison_long_df(outputs, selected_id)
    if chart_df.empty:
        st.info("A variável selecionada não está disponível nos fundos carregados.")
        return
    unit = _unit_for_raw_variable(selected_id)
    y_title = "R$ MM" if unit == "money" else ("%" if unit == "percent" else "Valor")
    chart = (
        alt.Chart(chart_df)
        .mark_line(point=True, strokeWidth=2)
        .encode(
            x=alt.X("competencia_label:N", title="Competência", sort=chart_df["competencia_label"].drop_duplicates().tolist()),
            y=alt.Y("valor_plot:Q", title=y_title),
            color=alt.Color("fundo:N", title="FIDC"),
            tooltip=[
                alt.Tooltip("fundo:N", title="FIDC"),
                alt.Tooltip("competencia_label:N", title="Competência"),
                alt.Tooltip("valor_fmt:N", title="Valor"),
            ],
        )
        .properties(height=380)
        .configure_axis(labelFontSize=11, titleFontSize=12)
        .configure_legend(labelFontSize=11, titleFontSize=11, orient="bottom")
    )
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(_comparison_table(outputs, selected_id), hide_index=True, use_container_width=True)


def _render_fund_boards_tab(outputs: list[dict[str, Any]]) -> None:
    selected = _select_output(outputs, key="monitoring_fund_table")
    if selected is None:
        return
    tables: MonitoringTables = selected["tables"]
    cnpj = str(selected["cnpj"])
    display_name = str(selected["display_name"])
    fnet_url = f"https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM?cnpjFundo={cnpj}"
    st.markdown(f'<div class="monitor-fund-title">{escape(display_name)}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="monitor-caption">{escape(format_portfolio_cnpj(cnpj))} · <a href="{escape(fnet_url)}" target="_blank">Abrir FNET</a></div>',
        unsafe_allow_html=True,
    )
    latest = _latest_competencia(selected)
    _render_single_fund_cards(selected, latest)
    spark_left, spark_right = st.columns(2)
    with spark_left:
        st.altair_chart(_sparkline_from_indicator(tables.indicators_df, "PL (R$ MM)", "PL (R$ MM)"), use_container_width=True)
    with spark_right:
        st.altair_chart(_sparkline_from_indicator(tables.indicators_df, "Vencidos Over 90 d / Crédito", "Over 90d / Crédito"), use_container_width=True)
    st.markdown("### Tabela Completa do fundo")
    st.markdown(_render_fund_time_table_html(selected), unsafe_allow_html=True)
    with st.expander("Auditoria de fórmulas", expanded=False):
        st.dataframe(tables.audit_df, hide_index=True, use_container_width=True)


def _render_single_fund_cards(item: dict[str, Any], latest: str | None) -> None:
    if not latest:
        return
    cards = [
        ("Última competência", _format_competencia_label(latest), "fundo selecionado"),
        ("PL", _format_metric_value(_metric_numeric(item, "PL (R$)", latest), "R$ bruto"), "Informe Mensal"),
        ("DC / PL", _format_metric_value(_metric_numeric(item, "Dir Cred / PL", latest), "ratio"), "alocação"),
        ("Over 90d", _format_metric_value(_metric_numeric(item, "Vencidos Over 90 d / Crédito", latest), "ratio"), "sobre crédito"),
        ("PDD / Over 90d", _format_metric_value(_metric_numeric(item, "PDD / Venc > 90 d", latest), "ratio"), "cobertura"),
        ("Cache", str(item.get("cache_status") or "-"), "status"),
    ]
    html = ["<div class='monitor-card-grid'>"]
    for label, value, note in cards:
        html.append(
            "<div class='monitor-kpi-card'>"
            f"<div class='monitor-kpi-label'>{escape(label)}</div>"
            f"<div class='monitor-kpi-value'>{escape(value)}</div>"
            f"<div class='monitor-kpi-note'>{escape(note)}</div>"
            "</div>"
        )
    html.append("</div>")
    st.markdown("\n".join(html), unsafe_allow_html=True)


def _render_fund_time_table_html(item: dict[str, Any]) -> str:
    tables: MonitoringTables = item["tables"]
    competencias = _competencias_desc(item.get("competencias") or [])
    if not competencias:
        return "<p class='monitor-caption'>Sem competências disponíveis.</p>"
    min_width = max(620 + 104 * len(competencias), 980)
    sections = _fund_time_table_sections(tables)
    html = [f"<div class='monitor-wide-wrapper' style='min-width: 100%; --monitor-table-min-width: {min_width}px;'>"]
    for section, rows in sections.items():
        html.append(f"<details class='monitor-wide-section' open style='min-width: {min_width}px;'>")
        html.append(f"<summary>{escape(section)}</summary>")
        html.append(f"<table class='monitor-wide-table' style='min-width: {min_width}px;'>")
        html.append("<colgroup><col style='width: 280px;'>")
        html.extend("<col style='width: 104px;'>" for _ in competencias)
        html.append("</colgroup><thead><tr><th class='label-col'>Métrica</th>")
        for competencia in competencias:
            html.append(f"<th>{escape(_format_competencia_label(competencia))}</th>")
        html.append("</tr></thead><tbody>")
        for row in rows:
            row_class = "destaque" if row["metric"] in {"PL (R$)", "Vencidos Over 90 d / Crédito", "PDD / Venc > 90 d"} else ""
            html.append(f"<tr class='{row_class}'>")
            html.append(f"<td class='label'>{escape(str(row['label']))}</td>")
            for competencia in competencias:
                html.append(f"<td>{escape(_format_metric_value(row.get(competencia), str(row.get('unit') or '')))}</td>")
            html.append("</tr>")
        html.append("</tbody></table></details>")
    html.append("</div>")
    return "\n".join(html)


def _fund_time_table_sections(tables: MonitoringTables) -> dict[str, list[dict[str, object]]]:
    wanted = {
        "Tamanho e alocação": ["PL (R$)", "Dir Cred (R$ MM)", "Dir Cred / PL"],
        "Inadimplência": [
            "Vencidos <= 90 d (R$ MM)",
            "Vencidos > 90 d (R$ MM)",
            "Vencidos Total (R$ MM)",
            "Vencidos Over 30 d / Crédito",
            "Vencidos Over 60 d / Crédito",
            "Vencidos Over 90 d / Crédito",
            "Vencidos Over 180 d / Crédito",
            "Vencidos Over 360 d / Crédito",
        ],
        "PDD e recompras": ["PDD (R$ MM)", "PDD / Crédito", "PDD / Venc > 90 d", "PDD / Venc Total", "Recompras (R$ MM)", "Recompras / Crédito"],
        "Cotas e retorno": ["Cotas SR / PL %", "Cotas MZ / PL %", "Cotas Sub / PL %", "Rentabilidade SR % a.m.", "Rentabilidade MZ % a.m.", "Rentabilidade Sub % a.m."],
    }
    sections: dict[str, list[dict[str, object]]] = {}
    for section, labels in wanted.items():
        rows = []
        for label in labels:
            match = tables.indicators_df[tables.indicators_df["indicador"] == label]
            if match.empty:
                continue
            source = match.iloc[0].to_dict()
            source["label"] = _friendly_indicator_label(label)
            source["metric"] = label
            source["unit"] = source.get("unidade")
            rows.append(source)
        if rows:
            sections[section] = rows
    aging_rows = []
    for _, row in tables.aging_df.iterrows():
        payload = row.to_dict()
        payload["label"] = payload.get("bucket")
        payload["metric"] = payload.get("bucket")
        payload["unit"] = payload.get("unidade")
        aging_rows.append(payload)
    if aging_rows:
        sections["Aging"] = aging_rows
    return sections


def _render_raw_data_tab(outputs: list[dict[str, Any]]) -> None:
    selected = _select_output(outputs, key="monitoring_raw_fund")
    if selected is None:
        return
    raw_df = selected["tables"].raw_variables_df.copy()
    sections = raw_df["secao"].dropna().astype(str).drop_duplicates().tolist()
    selected_sections = st.multiselect(
        "Seções",
        options=sections,
        default=sections,
        key="monitoring_raw_sections",
    )
    if selected_sections:
        raw_df = raw_df[raw_df["secao"].isin(selected_sections)].copy()
    st.dataframe(_format_raw_frame(raw_df), hide_index=True, use_container_width=True)


def _render_overrides_tab(outputs: list[dict[str, Any]]) -> None:
    selected = _select_output(outputs, key="monitoring_override_fund")
    if selected is None:
        return
    cnpj = str(selected["cnpj"])
    competencias = list(selected.get("competencias") or [])
    payload = load_manual_overrides(cnpj)
    editor_df = pd.DataFrame(
        [
            {
                "competencia": competencia,
                "vl_total_mz": (payload.get("competencias") or {}).get(competencia, {}).get("vl_total_mz"),
                "rent_mz": (payload.get("competencias") or {}).get(competencia, {}).get("rent_mz"),
            }
            for competencia in competencias
        ]
    )
    st.caption("Preencha apenas fundos/competências com classe mezanino não capturada diretamente pelo IME.")
    edited = st.data_editor(
        editor_df,
        key=f"monitoring_overrides_editor::{cnpj}",
        hide_index=True,
        use_container_width=True,
        column_config={
            "competencia": st.column_config.TextColumn("Competência", disabled=True),
            "vl_total_mz": st.column_config.NumberColumn("Valor total MZ (R$)", format="%.2f"),
            "rent_mz": st.column_config.NumberColumn("Rentabilidade MZ (% a.m.)", format="%.2f"),
        },
    )
    if st.button("Salvar overrides", key=f"monitoring_save_overrides::{cnpj}"):
        save_manual_overrides(cnpj, {"competencias": _editor_to_override_payload(edited)})
        st.success("Overrides salvos. Recarregue o monitoramento para recalcular os quadros.")


def _comparison_long_df(outputs: list[dict[str, Any]], selected_id: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    unit = _unit_for_raw_variable(selected_id)
    for item in outputs:
        raw_df = item["tables"].raw_variables_df
        match = raw_df[raw_df["id_cvm"] == selected_id]
        if match.empty:
            continue
        row = match.iloc[0]
        for competencia in item.get("competencias") or []:
            value = pd.to_numeric(pd.Series([row.get(competencia)]), errors="coerce").iloc[0]
            if pd.isna(value):
                continue
            value_plot = float(value) / 1_000_000.0 if unit == "money" else float(value)
            rows.append(
                {
                    "fundo": item["display_name"],
                    "competencia": competencia,
                    "competencia_label": _format_competencia_label(competencia),
                    "valor_plot": value_plot,
                    "valor_fmt": _format_raw_value(value, selected_id),
                }
            )
    return pd.DataFrame(rows)


def _comparison_table(outputs: list[dict[str, Any]], selected_id: str) -> pd.DataFrame:
    rows = []
    for item in outputs:
        raw_df = item["tables"].raw_variables_df
        match = raw_df[raw_df["id_cvm"] == selected_id]
        if match.empty:
            continue
        source = match.iloc[0]
        row = {"Fundo": item["display_name"]}
        for competencia in item.get("competencias") or []:
            row[_format_competencia_label(competencia)] = _format_raw_value(source.get(competencia), selected_id)
        rows.append(row)
    return pd.DataFrame(rows)


def _format_raw_frame(frame: pd.DataFrame) -> pd.DataFrame:
    competencias = [column for column in frame.columns if isinstance(column, str) and column[:2].isdigit() and "/" in column]
    output = frame[["secao", "label", "id_cvm", "status"]].rename(
        columns={"secao": "Seção", "label": "Variável", "id_cvm": "ID CVM", "status": "Status"}
    ).copy()
    for competencia in competencias:
        output[_format_competencia_label(competencia)] = [
            _format_raw_value(value, id_cvm)
            for value, id_cvm in zip(frame[competencia].tolist(), frame["id_cvm"].tolist(), strict=False)
        ]
    return output


def _sparkline_from_indicator(frame: pd.DataFrame, indicator: str, title: str) -> alt.Chart:
    match = frame[frame["indicador"] == indicator]
    if match.empty:
        return alt.Chart(pd.DataFrame({"x": [], "y": []})).mark_line().properties(title=title, height=140)
    row = match.iloc[0]
    competencias = [column for column in frame.columns if isinstance(column, str) and column[:2].isdigit() and "/" in column]
    data = pd.DataFrame(
        {
            "competencia": [_format_competencia_label(competencia) for competencia in competencias],
            "valor": [pd.to_numeric(pd.Series([row.get(competencia)]), errors="coerce").iloc[0] for competencia in competencias],
        }
    ).dropna()
    if data.empty:
        return alt.Chart(pd.DataFrame({"competencia": [], "valor": []})).mark_line().properties(title=title, height=140)
    return (
        alt.Chart(data)
        .mark_line(point=True, color="#EC7000", strokeWidth=2.2)
        .encode(
            x=alt.X("competencia:N", title=None, sort=data["competencia"].tolist()),
            y=alt.Y("valor:Q", title=None),
            tooltip=["competencia:N", alt.Tooltip("valor:Q", title="Valor", format=",.2f")],
        )
        .properties(title=title, height=140)
    )


def _select_output(outputs: list[dict[str, Any]], *, key: str) -> dict[str, Any] | None:
    options = [item["cnpj"] for item in outputs]
    labels = {item["cnpj"]: f"{item['display_name']} · {format_portfolio_cnpj(item['cnpj'])}" for item in outputs}
    selected = st.selectbox("Fundo", options=options, key=key, format_func=lambda value: labels.get(value, value))
    return next((item for item in outputs if item["cnpj"] == selected), None)


def _editor_to_override_payload(frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    payload: dict[str, dict[str, float]] = {}
    for _, row in frame.iterrows():
        competencia = str(row.get("competencia") or "").strip()
        if not competencia:
            continue
        values = {}
        for key in ("vl_total_mz", "rent_mz"):
            parsed = pd.to_numeric(pd.Series([row.get(key)]), errors="coerce").iloc[0]
            if pd.notna(parsed):
                values[key] = float(parsed)
        if values:
            payload[competencia] = values
    return payload


def _build_cache_diagnostics_df(outputs: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in outputs:
        all_competencias = list(item.get("all_competencias") or [])
        display_competencias = list(item.get("competencias") or [])
        rows.append(
            {
                "Fundo": item.get("display_name"),
                "CNPJ": format_portfolio_cnpj(str(item.get("cnpj") or "")),
                "Status cache": item.get("cache_status"),
                "Primeira no cache": _format_competencia_label(all_competencias[0]) if all_competencias else "-",
                "Última no cache": _format_competencia_label(all_competencias[-1]) if all_competencias else "-",
                "Janela exibida": _format_competencia_span(display_competencias),
                "Competências exibidas": len(display_competencias),
                "Diretório cache": item.get("cache_dir"),
            }
        )
    return pd.DataFrame(rows)


def _aggregate_metric(metric: CockpitMetric, outputs: list[dict[str, Any]], competencia: str) -> object:
    if metric.aggregate == "none":
        return pd.NA
    if metric.aggregate == "sum":
        values = [_metric_numeric(item, metric.indicator, competencia) for item in outputs]
        total = _sum_numbers(values)
        return pd.NA if total is None else total
    if metric.aggregate == "dircred_pl":
        dircred = _sum_numbers([_metric_numeric(item, "Dir Cred (R$ MM)", competencia) for item in outputs])
        pl = _sum_numbers([_metric_numeric(item, "PL (R$)", competencia) for item in outputs])
        return _safe_ratio(dircred, (pl / 1_000_000.0) if pl is not None else None)
    if metric.aggregate.startswith("over") and metric.aggregate.endswith("_credito"):
        prefix = metric.aggregate.removesuffix("_credito").replace("over", "Vencidos Over ") + " d (R$ MM)"
        vencidos = _sum_numbers([_metric_numeric(item, prefix, competencia) for item in outputs])
        dircred = _sum_numbers([_metric_numeric(item, "Dir Cred (R$ MM)", competencia) for item in outputs])
        return _safe_ratio(vencidos, dircred)
    if metric.aggregate == "pdd_credito":
        pdd = _sum_numbers([_metric_numeric(item, "PDD (R$ MM)", competencia) for item in outputs])
        dircred = _sum_numbers([_metric_numeric(item, "Dir Cred (R$ MM)", competencia) for item in outputs])
        return _safe_ratio(pdd, dircred)
    if metric.aggregate == "pdd_over90":
        pdd = _sum_numbers([_metric_numeric(item, "PDD (R$ MM)", competencia) for item in outputs])
        over90 = _sum_numbers([_metric_numeric(item, "Vencidos Over 90 d (R$ MM)", competencia) for item in outputs])
        return _safe_ratio(pdd, over90)
    if metric.aggregate == "recompras_credito":
        recomp = _sum_numbers([_metric_numeric(item, "Recompras (R$ MM)", competencia) for item in outputs])
        dircred = _sum_numbers([_metric_numeric(item, "Dir Cred (R$ MM)", competencia) for item in outputs])
        return _safe_ratio(recomp, dircred)
    if metric.aggregate == "weighted_pl":
        weighted = 0.0
        weight_sum = 0.0
        for item in outputs:
            value = _metric_numeric(item, metric.indicator, competencia)
            pl = _metric_numeric(item, "PL (R$)", competencia)
            if value is None or pl is None:
                continue
            weighted += value * pl
            weight_sum += pl
        return pd.NA if weight_sum <= 0 else weighted / weight_sum
    return pd.NA


def _metric_numeric(item: dict[str, Any], indicator: str, competencia: str | None) -> float | None:
    if not competencia:
        return None
    tables: MonitoringTables = item["tables"]
    frame = tables.indicators_df
    if competencia not in frame.columns:
        return None
    match = frame[frame["indicador"] == indicator]
    if match.empty:
        return None
    value = pd.to_numeric(pd.Series([match.iloc[0].get(competencia)]), errors="coerce").iloc[0]
    if pd.isna(value):
        return None
    return float(value)


def _sum_numbers(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None and pd.notna(value)]
    if not clean:
        return None
    return float(sum(clean))


def _safe_ratio(numerator: float | None, denominator: float | None) -> object:
    if numerator is None or denominator is None or denominator <= 0:
        return pd.NA
    return float(numerator) / float(denominator)


def _format_metric_value(value: object, unit: str) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "-"
    if unit == "R$ bruto":
        return _format_brl(float(numeric))
    if unit == "R$ MM":
        return f"R$ {_format_decimal(float(numeric), 1)} MM"
    if unit == "ratio":
        return f"{_format_decimal(float(numeric) * 100.0, 2)}%"
    if unit == "%":
        return f"{_format_decimal(float(numeric), 2)}%"
    return _format_decimal(float(numeric), 2)


def _format_raw_value(value: object, id_cvm: str) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "-"
    unit = _unit_for_raw_variable(id_cvm)
    if unit == "money":
        return f"R$ {_format_decimal(float(numeric) / 1_000_000.0, 1)} MM"
    if unit == "percent":
        return f"{_format_decimal(float(numeric), 2)}%"
    if unit == "count":
        return _format_decimal(float(numeric), 0)
    return _format_decimal(float(numeric), 2)


def _unit_for_raw_variable(id_cvm: str) -> str:
    if "/QT_" in id_cvm or id_cvm.startswith("QT_"):
        return "count"
    if "PR_" in id_cvm or "%" in id_cvm:
        return "percent"
    if "/VL_" in id_cvm or id_cvm.startswith("VL_"):
        return "money"
    return "number"


def _format_brl(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"R$ {_format_decimal(value / 1_000_000_000_000, 1)} bi"
    if abs_value >= 1_000_000:
        return f"R$ {_format_decimal(value / 1_000_000, 1)} MM"
    if abs_value >= 1_000:
        return f"R$ {_format_decimal(value / 1_000, 1)} mil"
    return f"R$ {_format_decimal(value, 0)}"


def _format_decimal(value: float, decimals: int) -> str:
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _format_competencia_label(value: object) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text[2] == "/":
        return f"{_PT_MONTH_ABBR.get(text[:2], text[:2])}/{text[-2:]}"
    return text


def _format_month_date_label(value: date) -> str:
    return f"{_PT_MONTH_ABBR.get(f'{value.month:02d}', f'{value.month:02d}')}/{str(value.year)[-2:]}"


def _format_period_label(period: ImePeriodSelection) -> str:
    return f"{_format_month_date_label(period.start_month)} → {_format_month_date_label(period.end_month)}"


def _format_competencia_span(competencias: list[str]) -> str:
    if not competencias:
        return "-"
    return f"{_format_competencia_label(competencias[0])} → {_format_competencia_label(competencias[-1])}"


def _portfolio_display_span(outputs: list[dict[str, Any]]) -> str:
    starts = []
    ends = []
    for item in outputs:
        competencias = list(item.get("competencias") or [])
        if not competencias:
            continue
        starts.append(parse_competencia_label(competencias[0]))
        ends.append(parse_competencia_label(competencias[-1]))
    if not starts or not ends:
        return "-"
    return f"{_format_month_date_label(min(starts))} → {_format_month_date_label(max(ends))}"


def _portfolio_latest_competencia(outputs: list[dict[str, Any]]) -> str | None:
    latest: tuple[date, str] | None = None
    for item in outputs:
        for competencia in item.get("competencias") or []:
            try:
                parsed = parse_competencia_label(competencia)
            except Exception:  # noqa: BLE001
                continue
            if latest is None or parsed > latest[0]:
                latest = (parsed, competencia)
    return latest[1] if latest else None


def _latest_competencia(item: dict[str, Any]) -> str | None:
    competencias = list(item.get("competencias") or [])
    return competencias[-1] if competencias else None


def _competencias_desc(competencias: list[str]) -> list[str]:
    return sorted(competencias, key=lambda value: parse_competencia_label(value), reverse=True)


def _short_fund_label(value: str) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= 30:
        return text
    return f"{text[:27].rstrip()}..."


def _friendly_indicator_label(value: str) -> str:
    return {
        "Dir Cred (R$ MM)": "Direitos creditórios",
        "Dir Cred / PL": "Direitos creditórios / PL",
        "Vencidos <= 90 d / Crédito": "Vencidos <=90d / Crédito",
        "Vencidos > 90 d / Crédito": "Vencidos >90d / Crédito",
        "Vencidos Over 30 d / Crédito": "Over 30d / Crédito",
        "Vencidos Over 60 d / Crédito": "Over 60d / Crédito",
        "Vencidos Over 90 d / Crédito": "Over 90d / Crédito",
        "Vencidos Over 180 d / Crédito": "Over 180d / Crédito",
        "Vencidos Over 360 d / Crédito": "Over 360d / Crédito",
        "PDD / Venc > 90 d": "PDD / Over 90d",
        "PDD / Venc Total": "PDD / vencidos totais",
    }.get(value, value)


def _session_key(portfolio: PortfolioRecord, period: ImePeriodSelection, cache_months: int) -> str:
    return f"fidc_monitoring::{portfolio.id}::{period.cache_key}::{cache_months}"
