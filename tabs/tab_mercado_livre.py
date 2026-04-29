from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import uuid
from typing import Any

import pandas as pd
import streamlit as st

from services.ime_period import ImePeriodSelection
from services.mercado_livre_dashboard import (
    build_consolidated_snapshot_excel_bytes,
    build_excel_export_bytes,
    build_mercado_livre_outputs,
    build_validation_table,
    cache_dir_for_outputs,
    extract_official_pl_history_from_wide_csv,
    load_outputs_from_cache,
    order_period_columns_desc,
    portfolio_identity_key,
    save_outputs_to_cache,
)
from services.mercado_livre_ppt_export import build_pptx_export_bytes
from services.mercado_livre_visuals import npl_coverage_chart, pl_subordination_chart
from services.portfolio_store import PortfolioFund, PortfolioRecord, portfolio_basket_signature, portfolio_name_key
from tabs import tab_fidc_ime as ime_tab
from tabs.ime_portfolio_support import (
    build_catalog_option_lookup,
    build_portfolio_funds_from_cnpjs,
    delete_portfolio_record,
    enrich_portfolio_funds_with_catalog,
    get_portfolio_status_caption,
    list_saved_portfolios,
    load_fidc_catalog_cached,
    save_portfolio_record,
)
from tabs.tab_fidc_ime_carteira import (
    _build_loaded_dashboards_by_cnpj,
    _execute_portfolio_load_for_funds,
    _get_portfolio_runtime_state,
)


_MERCADO_LIVRE_UI_CSS = """
<style>
.chart-title {
    color: #000000;
    font-size: clamp(16px, 1.45vw, 18px);
    font-weight: 600;
    line-height: 1.25;
    margin: 8px 0 4px 0;
}
.chart-subtitle {
    color: #8C8C8C;
    font-size: 12px;
    line-height: 1.25;
    margin: 0 0 8px 0;
}
.wide-table-wrapper {
    overflow-x: auto;
    overflow-y: visible;
    max-width: 100%;
    padding-bottom: 4px;
    margin-bottom: 10px;
}
.wide-section {
    margin: 0 0 8px 0;
}
.wide-section summary {
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
.wide-section summary::marker {
    color: #FFFFFF;
}
.wide-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    font-family: inherit;
    table-layout: fixed;
}
.wide-table th {
    text-align: right;
    padding: 6px 8px;
    border-bottom: 1px solid #3F3F3F;
    font-weight: 600;
    color: #000000;
    background: #FFFFFF;
    position: sticky;
    top: 0;
    z-index: 2;
    white-space: nowrap;
}
.wide-table th.label-col {
    text-align: left;
}
.wide-table th.formula-col {
    text-align: left;
    color: #8C8C8C;
}
.wide-table td {
    padding: 4px 8px;
    text-align: right;
    border-bottom: 1px solid #E5E5E5;
    color: #3F3F3F;
    line-height: 1.25;
    overflow-wrap: anywhere;
    vertical-align: top;
    white-space: normal;
    word-break: normal;
}
.wide-table td.label,
.wide-table td.formula {
    text-align: left;
}
.wide-table td.label {
    color: #000000;
    padding-left: 18px;
}
.wide-table td.formula {
    color: #8C8C8C;
    font-size: 11px;
}
.wide-table tr.destaque td {
    font-weight: 700;
    color: #000000;
}
.wide-table tr.variacao td {
    font-style: italic;
    color: #8C8C8C;
    font-size: 11px;
}
.wide-table tr:hover td {
    background: #F4F1EA;
}
</style>
"""


def render_tab_mercado_livre(period: ImePeriodSelection | None = None) -> None:
    st.markdown(ime_tab._FIDC_REPORT_CSS, unsafe_allow_html=True)
    st.markdown(_MERCADO_LIVRE_UI_CSS, unsafe_allow_html=True)
    _apply_pending_selection()

    portfolios = list_saved_portfolios()
    catalog_df = load_fidc_catalog_cached()
    if period is None:
        period = ime_tab._render_period_selector(state_prefix="mercado_livre", title="Período")

    selected_portfolio = _render_selection_controls(portfolios=portfolios, catalog_df=catalog_df)
    if selected_portfolio is None:
        st.info("Crie ou selecione uma carteira para iniciar a auditoria Mercado Livre.")
        return
    selected_portfolio = _enrich_portfolio_record(selected_portfolio=selected_portfolio, catalog_df=catalog_df)
    runtime_state = _get_portfolio_runtime_state(selected_portfolio=selected_portfolio, period=period)
    results = runtime_state.get("results") or {}
    cache_session_key = _outputs_session_key(selected_portfolio=selected_portfolio, period=period)

    if st.session_state.pop("_ml_load_requested", False):
        cached_outputs = load_outputs_from_cache(
            portfolio_id=selected_portfolio.id,
            period_key=period.cache_key,
            portfolio_funds=selected_portfolio.funds,
        )
        if cached_outputs is not None:
            st.session_state[cache_session_key] = cached_outputs
            st.session_state[f"{cache_session_key}::source"] = "cache"
            st.toast("Base Mercado Livre reutilizada do storage calculado.")
            st.rerun()
        _execute_portfolio_load_for_funds(
            selected_portfolio=selected_portfolio,
            period=period,
            funds=tuple(selected_portfolio.funds),
            existing_results=None,
        )
        st.rerun()

    _render_status_bar(selected_portfolio=selected_portfolio, period=period, results=results)
    cached_session_outputs = st.session_state.get(cache_session_key)
    if cached_session_outputs is not None:
        cache_dir = cache_dir_for_outputs(
            portfolio_id=selected_portfolio.id,
            period_key=period.cache_key,
            portfolio_funds=selected_portfolio.funds,
        )
        _render_outputs(
            outputs=cached_session_outputs,
            selected_portfolio=selected_portfolio,
            cache_dir=cache_dir,
            storage_source=str(st.session_state.get(f"{cache_session_key}::source") or "cache"),
        )
        return
    if not results:
        st.info("Clique em **Carregar carteira** para montar a base auditável e os gráficos.")
        return

    dashboards_by_cnpj, dashboard_errors = _build_loaded_dashboards_by_cnpj(
        selected_portfolio=selected_portfolio,
        results=results,
    )
    if dashboard_errors:
        with st.expander("Fundos sem dashboard base", expanded=False):
            for cnpj, message in dashboard_errors.items():
                st.caption(f"**{cnpj}** — {message}")
    if not dashboards_by_cnpj:
        st.warning("Nenhum fundo carregado com sucesso para montar a aba Mercado Livre.")
        return
    official_pl_by_cnpj = _build_official_pl_by_cnpj(results=results, cnpjs=list(dashboards_by_cnpj))

    outputs = build_mercado_livre_outputs(
        portfolio_id=selected_portfolio.id,
        portfolio_name=selected_portfolio.name,
        dashboards_by_cnpj=dashboards_by_cnpj,
        period_label=period.label,
        official_pl_by_cnpj=official_pl_by_cnpj,
    )
    cache_dir = save_outputs_to_cache(
        outputs,
        portfolio_id=selected_portfolio.id,
        period_key=period.cache_key,
        portfolio_funds=selected_portfolio.funds,
    )
    st.session_state[cache_session_key] = outputs
    st.session_state[f"{cache_session_key}::source"] = "recalculado"
    _render_outputs(
        outputs=outputs,
        selected_portfolio=selected_portfolio,
        cache_dir=cache_dir,
        storage_source="recalculado",
    )


def _render_selection_controls(
    *,
    portfolios: list[PortfolioRecord],
    catalog_df: pd.DataFrame,
) -> PortfolioRecord | None:
    if not portfolios:
        st.session_state["ml_editor_open"] = True
        st.session_state["ml_editor_mode"] = "create"
        selected_portfolio = None
    else:
        try:
            sel_col, new_col, edit_col, load_col = st.columns([4.0, 1.45, 1.45, 1.35], vertical_alignment="bottom")
        except TypeError:
            sel_col, new_col, edit_col, load_col = st.columns([4.0, 1.45, 1.45, 1.35])
        with sel_col:
            selected_portfolio = _render_portfolio_selector(portfolios)
        with new_col:
            if st.button("Criar nova seleção", key="ml_portfolio_new_button", use_container_width=True):
                _reset_editor_state()
                st.session_state["ml_editor_mode"] = "create"
                st.session_state["ml_editor_open"] = True
                st.rerun()
        with edit_col:
            if st.button("Editar seleção atual", key="ml_portfolio_edit_button", use_container_width=True):
                st.session_state["ml_editor_mode"] = "edit"
                st.session_state["ml_editor_open"] = True
                st.rerun()
        with load_col:
            if st.button("Carregar carteira", key="ml_portfolio_load_button", type="secondary", use_container_width=True):
                st.session_state["_ml_load_requested"] = True
                st.rerun()

    st.caption(get_portfolio_status_caption())
    if st.session_state.get("ml_editor_open", False):
        _render_portfolio_editor(
            portfolios=portfolios,
            catalog_df=catalog_df,
            selected_portfolio=selected_portfolio,
            editor_mode=str(st.session_state.get("ml_editor_mode") or "edit"),
        )
    return selected_portfolio


def _render_portfolio_selector(portfolios: list[PortfolioRecord]) -> PortfolioRecord | None:
    if not portfolios:
        return None
    options = [portfolio.id for portfolio in portfolios]
    labels = {portfolio.id: f"{portfolio.name} · {len(portfolio.funds)} fundo(s)" for portfolio in portfolios}
    default_id = st.session_state.get("ml_portfolio_active_id")
    if default_id not in options:
        mercado = next((portfolio.id for portfolio in portfolios if portfolio.name.strip().lower() == "mercado livre"), None)
        default_id = mercado or options[0]
        st.session_state["ml_portfolio_active_id"] = default_id
    selected_id = st.selectbox(
        "Carteira salva",
        options=options,
        index=options.index(default_id),
        key="ml_portfolio_active_id",
        label_visibility="collapsed",
        format_func=lambda value: labels.get(value, value),
    )
    return next((portfolio for portfolio in portfolios if portfolio.id == selected_id), None)


def _render_portfolio_editor(
    *,
    portfolios: list[PortfolioRecord],
    catalog_df: pd.DataFrame,
    selected_portfolio: PortfolioRecord | None,
    editor_mode: str,
) -> None:
    target = selected_portfolio if editor_mode == "edit" and selected_portfolio is not None else None
    suffix = target.id if target is not None else "new"
    option_labels, option_lookup = build_catalog_option_lookup(catalog_df)
    catalog_cnpjs = {fund.cnpj for fund in option_lookup.values()}
    default_labels = [
        next((label for label, fund in option_lookup.items() if fund.cnpj == portfolio_fund.cnpj), portfolio_fund.display_name)
        for portfolio_fund in (target.funds if target is not None else ())
    ]
    st.markdown(f"**{'Criar nova seleção' if target is None else 'Editar seleção atual'}**")
    with st.form(f"ml_portfolio_editor_form::{suffix}", clear_on_submit=False):
        name = st.text_input(
            "Nome da seleção",
            value=target.name if target is not None else "",
            placeholder="Ex.: Mercado Livre",
            key=f"ml_portfolio_name::{suffix}",
        ).strip()
        selected_labels = st.multiselect(
            "Fundos",
            options=option_labels,
            default=default_labels,
            help="Até 20 FIDCs. Busca usa o cadastro público da CVM.",
            key=f"ml_portfolio_funds::{suffix}",
        ) if option_labels else []
        manual_cnpjs = st.text_area(
            "CNPJs adicionais",
            value="\n".join(
                fund.cnpj
                for fund in (target.funds if target is not None else ())
                if fund.cnpj not in catalog_cnpjs
            )
            if target is not None
            else "",
            placeholder="00.000.000/0000-00 (um por linha)",
            height=90,
            key=f"ml_portfolio_cnpjs::{suffix}",
        )
        cols = st.columns([1.2, 1.2, 3])
        save_clicked = cols[0].form_submit_button("Atualizar seleção" if target is not None else "Salvar nova seleção", type="primary")
        cancel_clicked = cols[1].form_submit_button("Cancelar")

    if cancel_clicked:
        st.session_state["ml_editor_open"] = False if portfolios else True
        _reset_editor_state()
        st.rerun()

    if save_clicked:
        if not name:
            st.warning("Informe um nome para a seleção.")
            return
        funds = [option_lookup[label] for label in selected_labels]
        funds.extend(build_portfolio_funds_from_cnpjs(manual_cnpjs.splitlines(), catalog_df))
        funds = enrich_portfolio_funds_with_catalog(funds, catalog_df)
        if not funds:
            st.warning("Selecione ao menos um fundo.")
            return
        existing = _resolve_existing_portfolio_for_save(
            portfolios=portfolios,
            target=target,
            name=name,
            funds=funds,
        )
        if existing.get("action") == "reuse":
            reused = existing["portfolio"]
            _queue_selection(reused.id)
            st.session_state["ml_editor_open"] = False
            _reset_editor_state()
            st.toast(f"A seleção '{reused.name}' já estava salva com a mesma composição. Reaproveitei a carteira existente.")
            st.rerun()
            return
        if existing.get("action") == "rename":
            conflict = existing["portfolio"]
            st.warning(
                f"Já existe uma seleção chamada '{conflict.name}', mas com outra composição. "
                "Use outro nome antes de salvar."
            )
            return
        try:
            stored = save_portfolio_record(
                PortfolioRecord(
                    id=target.id if target is not None else uuid.uuid4().hex,
                    name=name,
                    funds=tuple(funds),
                    created_at=target.created_at if target is not None else _utc_now_iso(),
                    updated_at=target.updated_at if target is not None else _utc_now_iso(),
                    notes=target.notes if target is not None else "",
                )
            )
        except ValueError as exc:
            st.warning(str(exc))
            return
        _queue_selection(stored.id)
        st.session_state["ml_editor_open"] = False
        _reset_editor_state()
        st.toast(f"Seleção '{stored.name}' salva ({len(stored.funds)} fundo(s)).")
        st.rerun()

    if target is not None:
        if st.button("Excluir seleção", key=f"ml_portfolio_delete_button::{target.id}"):
            delete_portfolio_record(target.id)
            st.session_state.pop("ml_portfolio_active_id", None)
            st.session_state["ml_editor_open"] = False if len(portfolios) > 1 else True
            _reset_editor_state()
            st.rerun()


def _render_status_bar(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
    results: dict[str, dict[str, Any]],
) -> None:
    ok = sum(1 for payload in results.values() if payload.get("result") is not None)
    total = len(selected_portfolio.funds)
    st.markdown(
        f"""
<div class="fidc-period-bar">
  <span><strong>Carteira:</strong> {escape(selected_portfolio.name)}</span>
  <span><strong>Período solicitado:</strong> {escape(period.label)}</span>
  <span><strong>Fundos carregados:</strong> {ok}/{total}</span>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_outputs(
    *,
    outputs,
    selected_portfolio: PortfolioRecord,
    cache_dir,
    storage_source: str,
) -> None:
    validation_df = build_validation_table(outputs)
    st.markdown(
        f"""
<div class="fidc-period-bar">
  <span><strong>Período carregado:</strong> {escape(_loaded_period_label(outputs))}</span>
  <span><strong>Storage:</strong> {escape(storage_source)}</span>
  <span><strong>Identidade da carteira:</strong> {escape(str(outputs.metadata.get("storage_identity_key") or portfolio_identity_key(selected_portfolio.funds, fallback=selected_portfolio.id)))}</span>
</div>
""",
        unsafe_allow_html=True,
    )

    excel_bytes = build_excel_export_bytes(outputs)
    snapshot_bytes = build_consolidated_snapshot_excel_bytes(outputs)
    pptx_bytes = build_pptx_export_bytes(outputs)
    main_tab, audit_tab = st.tabs(["Tabelas wide e gráficos", "Tabela de auditoria"])

    with main_tab:
        btn_left, btn_mid, btn_right = st.columns([1.15, 1.65, 1.45])
        with btn_left:
            st.download_button(
                "Baixar wide completo",
                data=excel_bytes,
                file_name=f"mercado_livre_{_safe_file_token(selected_portfolio.name)}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"ml_excel_download::{selected_portfolio.id}",
                use_container_width=True,
            )
        with btn_mid:
            st.download_button(
                "Baixar resumo 6m + gráficos consolidados",
                data=snapshot_bytes,
                file_name=f"mercado_livre_resumo_6m_{_safe_file_token(selected_portfolio.name)}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"ml_snapshot_excel_download::{selected_portfolio.id}",
                use_container_width=True,
            )
        with btn_right:
            st.download_button(
                "Baixar slides PPTX",
                data=pptx_bytes,
                file_name=f"mercado_livre_graficos_{_safe_file_token(selected_portfolio.name)}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                key=f"ml_pptx_download::{selected_portfolio.id}",
                use_container_width=True,
            )

        st.markdown("### Wide consolidada")
        st.markdown(_render_wide_table_html(outputs.consolidated_wide), unsafe_allow_html=True)

        st.markdown("### Wide individuais")
        for cnpj, monthly_df in outputs.fund_monthly.items():
            fund_name = str(monthly_df["fund_name"].iloc[0]) if not monthly_df.empty and "fund_name" in monthly_df.columns else cnpj
            with st.expander(f"{fund_name} · {cnpj}", expanded=False):
                st.markdown(_render_wide_table_html(outputs.fund_wide[cnpj]), unsafe_allow_html=True)

        st.markdown("### Gráficos consolidados")
        _render_graph_definitions()
        left, right = st.columns(2)
        with left:
            _render_chart(
                "Evolução de PL e Subordinação",
                "PL consolidado em escala dinâmica; subordinação ex-360 no eixo direito.",
                pl_subordination_chart(outputs.consolidated_monthly),
            )
        with right:
            _render_chart(
                "NPL e Cobertura Ex-Vencidos > 360d",
                "Índices consolidados recalculados a partir das somas absolutas.",
                npl_coverage_chart(outputs.consolidated_monthly),
            )

        st.markdown("### Gráficos individuais")
        for cnpj, monthly_df in outputs.fund_monthly.items():
            fund_name = str(monthly_df["fund_name"].iloc[0]) if not monthly_df.empty and "fund_name" in monthly_df.columns else cnpj
            with st.expander(f"{fund_name} · {cnpj}", expanded=False):
                left, right = st.columns(2)
                with left:
                    _render_chart(
                        "Evolução de PL e Subordinação",
                        "PL em escala dinâmica; subordinação ex-360 no eixo direito.",
                        pl_subordination_chart(monthly_df),
                    )
                with right:
                    _render_chart(
                        "NPL e Cobertura Ex-Vencidos > 360d",
                        "NPL Over 90d ex-360 e cobertura PDD ex-360 / NPL Over 90d ex-360.",
                        npl_coverage_chart(monthly_df),
                    )

    with audit_tab:
        st.caption("Base auxiliar para conferência: valores absolutos são calculados primeiro; percentuais são derivados depois.")
        st.dataframe(_format_validation_for_display(validation_df), width="stretch", hide_index=True)
        st.caption(f"Base calculada persistida em `{cache_dir}`.")
        if not outputs.warnings_df.empty:
            with st.expander("Warnings da base", expanded=False):
                st.dataframe(outputs.warnings_df, width="stretch", hide_index=True)


def _render_chart(title: str, subtitle: str, chart) -> None:
    st.markdown(f"<h4 class='chart-title'>{escape(title)}</h4>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<p class='chart-subtitle'>{escape(subtitle)}</p>", unsafe_allow_html=True)
    st.altair_chart(chart, width="stretch")


def _render_wide_table_html(df_wide: pd.DataFrame) -> str:
    if df_wide.empty:
        return "<p class='chart-subtitle'>Sem dados para a tabela wide consolidada.</p>"
    period_columns = order_period_columns_desc(df_wide.columns)
    table_min_width = max(620 + 96 * len(period_columns), 920)
    colgroup = _wide_table_colgroup(period_columns)
    html: list[str] = []
    html.append(f"<div class='wide-table-wrapper' style='min-width: 100%; --wide-table-min-width: {table_min_width}px;'>")
    current_block = ""
    section_rows: list[pd.Series] = []

    def flush_section() -> None:
        if not current_block:
            return
        html.append(f"<details class='wide-section' open style='min-width: {table_min_width}px;'>")
        html.append(f"<summary>{escape(_section_label(current_block))}</summary>")
        html.append(f"<table class='wide-table' style='min-width: {table_min_width}px;'>")
        html.append(colgroup)
        html.append("<thead><tr>")
        html.append("<th class='label-col'>Métrica</th>")
        for column in period_columns:
            html.append(f"<th>{escape(column)}</th>")
        html.append("<th class='formula-col'>Memória / fórmula</th>")
        html.append("</tr></thead><tbody>")
        for item in section_rows:
            metric = str(item.get("Métrica") or "").strip()
            formula = str(item.get("Memória / fórmula") or "").strip()
            row_class = _wide_table_metric_class(metric)
            html.append(f"<tr class='{row_class}'>")
            html.append(f"<td class='label'>{escape(metric)}</td>")
            for column in period_columns:
                html.append(f"<td>{escape(_dense_wide_value(item.get(column)))}</td>")
            html.append(f"<td class='formula'>{escape(_dense_wide_value(formula))}</td>")
            html.append("</tr>")
        html.append("</tbody></table></details>")

    for _, row in df_wide.iterrows():
        block = str(row.get("Bloco") or "").strip()
        if block and block != current_block:
            flush_section()
            current_block = block
            section_rows = []
        section_rows.append(row)
    flush_section()
    html.append("</div>")
    return "\n".join(html)


def _wide_table_colgroup(period_columns: list[str]) -> str:
    columns = ["<colgroup>", "<col class='label-col-width' style='width: 280px;'>"]
    columns.extend("<col class='period-col-width' style='width: 96px;'>" for _ in period_columns)
    columns.append("<col class='formula-col-width' style='width: 340px;'>")
    columns.append("</colgroup>")
    return "".join(columns)


def _section_label(block: str) -> str:
    parts = block.split(".", 1)
    if len(parts) == 2 and parts[0].strip().isdigit():
        return parts[1].strip()
    return block


def _wide_table_metric_class(metric: str) -> str:
    normalized = metric.lower()
    destaque_terms = (
        "pl fidc total",
        "carteira bruta total",
        "carteira líquida",
        "npl over 90d / carteira",
        "pdd / npl over 90d",
        "% subordinação total",
        "carteira ex over 360d",
        "pl ex over 360d",
        "pdd ex over 360d",
    )
    if any(term in normalized for term in destaque_terms):
        return "destaque"
    if "(%)" in metric or " / " in metric or metric.startswith("%") or "reconciliação" in normalized:
        return "variacao"
    return "normal"


def _dense_wide_value(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text or text.upper() == "N/D":
        return ""
    for prefix, suffix, decimals in (
        ("R$ bi ", " bi", 1),
        ("R$ mm ", " MM", 1),
        ("R$ mil ", " mil", 1),
    ):
        if text.startswith(prefix):
            parsed = _parse_br_number(text.removeprefix(prefix))
            return _format_br_number(parsed, decimals=decimals) + suffix if parsed is not None else text
    if text.startswith("R$ "):
        parsed = _parse_br_number(text.removeprefix("R$ "))
        if parsed is None:
            return text
        decimals = 0 if float(parsed).is_integer() else 1
        return _format_br_number(parsed, decimals=decimals)
    if text.endswith("%"):
        parsed = _parse_br_number(text[:-1])
        return f"{_format_br_number(parsed, decimals=1)}%" if parsed is not None else text
    return text


def _parse_br_number(value: str) -> float | None:
    try:
        normalized = value.strip().replace(".", "").replace(",", ".")
        return float(normalized)
    except (TypeError, ValueError):
        return None


def _format_br_number(value: float, *, decimals: int) -> str:
    formatted = f"{float(value):,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _render_graph_definitions() -> None:
    st.caption(
        "**Evolução de PL e Subordinação:** barras empilhadas mostram PL Sênior e Subordinada + Mez ex-360 em R$; "
        "a linha mostra a subordinação ex-360, após eventual baixa residual de Over 360 não coberta por PDD. "
        "**NPL e Cobertura Ex-Vencidos > 360d:** a linha de NPL usa NPL Over 90d sem vencidos acima de 360 dias; "
        "a cobertura usa PDD Ex Over 360d / NPL Over 90d Ex 360, em que PDD Ex Over 360d = PDD total menos a baixa Over 360d na PDD."
    )


def _resolve_existing_portfolio_for_save(
    *,
    portfolios: list[PortfolioRecord],
    target: PortfolioRecord | None,
    name: str,
    funds: list[PortfolioFund],
) -> dict[str, Any]:
    target_id = target.id if target is not None else None
    requested_name_key = portfolio_name_key(name)
    requested_basket = portfolio_basket_signature(funds)
    same_basket = next(
        (
            portfolio
            for portfolio in portfolios
            if portfolio.id != target_id and portfolio_basket_signature(portfolio.funds) == requested_basket
        ),
        None,
    )
    if same_basket is not None:
        return {"action": "reuse", "portfolio": same_basket}
    same_name = next(
        (
            portfolio
            for portfolio in portfolios
            if portfolio.id != target_id and portfolio_name_key(portfolio.name) == requested_name_key
        ),
        None,
    )
    if same_name is not None:
        return {"action": "rename", "portfolio": same_name}
    return {"action": "save"}


def _outputs_session_key(*, selected_portfolio: PortfolioRecord, period: ImePeriodSelection) -> str:
    identity = portfolio_identity_key(selected_portfolio.funds, fallback=selected_portfolio.id)
    return f"ml_outputs::{identity}::{period.cache_key}"


def _build_official_pl_by_cnpj(
    *,
    results: dict[str, dict[str, Any]],
    cnpjs: list[str],
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for cnpj in cnpjs:
        payload = results.get(cnpj) or {}
        result = payload.get("result")
        wide_csv_path = getattr(result, "wide_csv_path", None)
        if wide_csv_path is None:
            continue
        frames[cnpj] = extract_official_pl_history_from_wide_csv(wide_csv_path)
    return frames


def _loaded_period_label(outputs) -> str:
    frame = outputs.consolidated_monthly
    if frame is None or frame.empty or "competencia" not in frame.columns:
        return "N/D"
    competencias = frame["competencia"].astype(str).tolist()
    return f"{ime_tab._format_competencia_label(competencias[0])} a {ime_tab._format_competencia_label(competencias[-1])}"


def _format_validation_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    output = df.copy()
    rename = {
        "fund_name": "Fundo",
        "cnpj": "CNPJ",
        "competencia": "Competência",
        "pl_total": "PL total",
        "pl_total_oficial": "PL oficial",
        "pl_total_classes": "PL soma classes",
        "pl_reconciliacao_delta": "Delta PL",
        "pl_senior": "PL sênior",
        "pl_subordinada_mezz": "Subordinada + Mez",
        "subordinacao_total_pct": "% Subordinação",
        "carteira_bruta": "Carteira",
        "pdd_total": "PDD",
        "npl_over90": "NPL Over 90d",
        "npl_over360": "Over 360d",
        "baixa_over360_carteira": "Baixa carteira >360",
        "baixa_over360_pdd": "Baixa PDD >360",
        "baixa_over360_pl": "Baixa PL >360",
        "npl_over90_ex360": "NPL 90 ex-360",
        "carteira_ex360": "Carteira ex-360",
        "pdd_ex360": "PDD ex-360",
        "pl_total_ex360": "PL ex-360",
        "pl_subordinada_mezz_ex360": "Sub+Mez ex-360",
        "subordinacao_total_ex360_pct": "% Subordinação ex-360",
        "pdd_npl_over90_pct": "PDD/NPL90",
        "pdd_npl_over90_ex360_pct": "PDD/NPL90 ex-360",
        "warnings": "Warnings",
    }
    for column in [
        "pl_total",
        "pl_total_oficial",
        "pl_total_classes",
        "pl_reconciliacao_delta",
        "pl_senior",
        "pl_subordinada_mezz",
        "carteira_bruta",
        "pdd_total",
        "npl_over90",
        "npl_over360",
        "baixa_over360_carteira",
        "baixa_over360_pdd",
        "baixa_over360_pl",
        "npl_over90_ex360",
        "carteira_ex360",
        "pdd_ex360",
        "pl_total_ex360",
        "pl_subordinada_mezz_ex360",
    ]:
        if column in output.columns:
            output[column] = output[column].map(_format_brl_compact)
    for column in [
        "subordinacao_total_pct",
        "subordinacao_total_ex360_pct",
        "pdd_npl_over90_pct",
        "pdd_npl_over90_ex360_pct",
    ]:
        if column in output.columns:
            output[column] = output[column].map(_format_percent)
    return output.rename(columns=rename)


def _format_brl_compact(value: object) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "N/D"
    if abs(float(numeric)) >= 1_000_000_000:
        return f"R$ {_format_decimal(float(numeric) / 1_000_000_000, 2)} bi"
    if abs(float(numeric)) >= 1_000_000:
        return f"R$ {_format_decimal(float(numeric) / 1_000_000, 1)} mm"
    if abs(float(numeric)) >= 1_000:
        return f"R$ {_format_decimal(float(numeric) / 1_000, 1)} mil"
    return f"R$ {_format_decimal(float(numeric), 2)}"


def _format_percent(value: object) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "N/D"
    return f"{_format_decimal(float(numeric), 2)}%"


def _format_decimal(value: float, decimals: int) -> str:
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _enrich_portfolio_record(*, selected_portfolio: PortfolioRecord, catalog_df: pd.DataFrame) -> PortfolioRecord:
    return PortfolioRecord(
        id=selected_portfolio.id,
        name=selected_portfolio.name,
        funds=tuple(enrich_portfolio_funds_with_catalog(selected_portfolio.funds, catalog_df)),
        created_at=selected_portfolio.created_at,
        updated_at=selected_portfolio.updated_at,
        notes=selected_portfolio.notes,
    )


def _apply_pending_selection() -> None:
    pending = st.session_state.pop("_ml_portfolio_active_id_pending", None)
    if pending:
        st.session_state["ml_portfolio_active_id"] = pending


def _queue_selection(portfolio_id: str) -> None:
    st.session_state["_ml_portfolio_active_id_pending"] = portfolio_id


def _reset_editor_state() -> None:
    for key in ("ml_portfolio_name::new", "ml_portfolio_funds::new", "ml_portfolio_cnpjs::new"):
        st.session_state.pop(key, None)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_file_token(value: object) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value or "").strip().lower()).strip("_") or "carteira"
