from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from services.ime_loader import load_or_extract_informe
from services.ime_period import (
    ImePeriodSelection,
    build_preset_period,
    current_default_end_month,
    load_period_for_available_data,
    select_competencia_labels_for_period,
)
from services.monitoring_metrics import (
    MonitoringTables,
    build_monitoring_tables,
    load_manual_overrides,
    read_wide_csv,
    save_manual_overrides,
)
from services.portfolio_store import PortfolioRecord
from services.variaveis_fnet import VARIAVEIS_FNET, competencia_columns
from tabs.ime_portfolio_support import (
    build_portfolio_record_label_lookup,
    format_portfolio_cnpj,
    list_saved_portfolios,
    normalize_portfolio_fund_name,
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
    st.caption("Painel comparativo baseado nos Informes Mensais Estruturados já baixados via cache FNET/CVM.")

    if period is None:
        period = build_preset_period(end_month=current_default_end_month(), months=12)

    portfolios = list_saved_portfolios()
    if not portfolios:
        st.info("Crie uma carteira salva nas abas de carteira/Soma de FIDCs para usar o monitoramento.")
        return

    labels = build_portfolio_record_label_lookup(portfolios)
    portfolio_id = st.selectbox(
        "Carteira",
        options=[portfolio.id for portfolio in portfolios],
        format_func=lambda value: labels.get(value, value),
        key="monitoring_portfolio_id",
    )
    selected_portfolio = next((portfolio for portfolio in portfolios if portfolio.id == portfolio_id), None)
    if selected_portfolio is None:
        return

    st.markdown(
        f"""
<div class="monitor-card-row">
  <span class="monitor-chip"><strong>Período:</strong> {escape(period.label)}</span>
  <span class="monitor-chip"><strong>Fundos:</strong> {len(selected_portfolio.funds)}</span>
</div>
""",
        unsafe_allow_html=True,
    )

    session_key = _session_key(selected_portfolio, period)
    if st.button("Carregar Monitoramento", type="primary", key=f"{session_key}::load"):
        st.session_state[session_key] = _load_portfolio_monitoring(selected_portfolio, period)
        st.rerun()

    outputs = st.session_state.get(session_key)
    if not outputs:
        st.info("Clique em **Carregar Monitoramento** para montar os quadros usando o cache IME/FNET.")
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

    comparison_tab, fund_tab, raw_tab, overrides_tab = st.tabs(
        ["Comparativo", "Quadros por fundo", "Dados brutos", "Overrides de Mezanino"]
    )
    with comparison_tab:
        _render_comparison_tab(success_outputs)
    with fund_tab:
        _render_fund_boards_tab(success_outputs)
    with raw_tab:
        _render_raw_data_tab(success_outputs)
    with overrides_tab:
        _render_overrides_tab(success_outputs)


def _load_portfolio_monitoring(portfolio: PortfolioRecord, period: ImePeriodSelection) -> list[dict[str, Any]]:
    progress = st.progress(0.0, text="Preparando monitoramento...")
    outputs: list[dict[str, Any]] = []
    total = len(portfolio.funds)
    load_period = load_period_for_available_data(period)
    for index, fund in enumerate(portfolio.funds, start=1):
        progress.progress(index / max(total, 1), text=f"{index}/{total} · {fund.display_name}")
        try:
            cached = load_or_extract_informe(
                cnpj_fundo=fund.cnpj,
                data_inicial=load_period.start_month,
                data_final=load_period.end_month,
            )
            wide_df = read_wide_csv(cached.result.wide_csv_path)
            all_competencias = competencia_columns(wide_df)
            competencias = select_competencia_labels_for_period(all_competencias, period) or all_competencias
            overrides = load_manual_overrides(fund.cnpj)
            tables = build_monitoring_tables(wide_df, competencias, cnpj=fund.cnpj, overrides=overrides)
            outputs.append(
                {
                    "cnpj": fund.cnpj,
                    "display_name": normalize_portfolio_fund_name(fund.display_name, fund.cnpj),
                    "competencias": competencias,
                    "tables": tables,
                    "cache_status": cached.cache_status,
                    "cache_dir": str(cached.cache_dir),
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
        .properties(height=360)
        .configure_axis(labelFontSize=11, titleFontSize=12)
        .configure_legend(labelFontSize=11, titleFontSize=11, orient="bottom")
    )
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(_comparison_table(outputs, selected_id), hide_index=True, use_container_width=True)


def _render_fund_boards_tab(outputs: list[dict[str, Any]]) -> None:
    for item in outputs:
        tables: MonitoringTables = item["tables"]
        cnpj = str(item["cnpj"])
        display_name = str(item["display_name"])
        fnet_url = f"https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM?cnpjFundo={cnpj}"
        with st.expander(f"{display_name} · {format_portfolio_cnpj(cnpj)}", expanded=False):
            st.markdown(f'<div class="monitor-fund-title">{escape(display_name)}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="monitor-caption">{escape(format_portfolio_cnpj(cnpj))} · <a href="{escape(fnet_url)}" target="_blank">Abrir FNET</a></div>',
                unsafe_allow_html=True,
            )
            spark_left, spark_right = st.columns(2)
            with spark_left:
                st.altair_chart(_sparkline_from_indicator(tables.indicators_df, "PL (R$ MM)", "PL (R$ MM)"), use_container_width=True)
            with spark_right:
                st.altair_chart(_sparkline_from_indicator(tables.indicators_df, "Dir Cred / PL", "Dir Cred / PL"), use_container_width=True)
            st.markdown("**Tabela de Indicadores**")
            st.dataframe(_format_metric_frame(tables.indicators_df, label_column="indicador"), hide_index=True, use_container_width=True)
            st.markdown("**Tabela Aging**")
            st.dataframe(_format_metric_frame(tables.aging_df, label_column="bucket"), hide_index=True, use_container_width=True)
            with st.expander("Auditoria de fórmulas", expanded=False):
                st.dataframe(tables.audit_df, hide_index=True, use_container_width=True)


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


def _format_metric_frame(frame: pd.DataFrame, *, label_column: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    competencias = [column for column in frame.columns if isinstance(column, str) and column[:2].isdigit() and "/" in column]
    rows = []
    for _, source in frame.iterrows():
        unit = str(source.get("unidade") or "")
        row = {"Indicador": source.get(label_column)}
        for competencia in competencias:
            row[_format_competencia_label(competencia)] = _format_metric_value(source.get(competencia), unit)
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
        return alt.Chart(pd.DataFrame({"x": [], "y": []})).mark_line().properties(title=title, height=120)
    row = match.iloc[0]
    competencias = [column for column in frame.columns if isinstance(column, str) and column[:2].isdigit() and "/" in column]
    data = pd.DataFrame(
        {
            "competencia": [_format_competencia_label(competencia) for competencia in competencias],
            "valor": [pd.to_numeric(pd.Series([row.get(competencia)]), errors="coerce").iloc[0] for competencia in competencias],
        }
    ).dropna()
    if data.empty:
        return alt.Chart(pd.DataFrame({"competencia": [], "valor": []})).mark_line().properties(title=title, height=120)
    return (
        alt.Chart(data)
        .mark_line(point=True, color="#EC7000")
        .encode(
            x=alt.X("competencia:N", title=None, sort=data["competencia"].tolist()),
            y=alt.Y("valor:Q", title=None),
            tooltip=["competencia:N", alt.Tooltip("valor:Q", title="Valor", format=",.2f")],
        )
        .properties(title=title, height=120)
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
    return f"R$ {_format_decimal(value, 2)}"


def _format_decimal(value: float, decimals: int) -> str:
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _format_competencia_label(value: object) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text[2] == "/":
        return f"{_PT_MONTH_ABBR.get(text[:2], text[:2])}/{text[-2:]}"
    return text


def _session_key(portfolio: PortfolioRecord, period: ImePeriodSelection) -> str:
    return f"fidc_monitoring::{portfolio.id}::{period.cache_key}"
