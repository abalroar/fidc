from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import altair as alt
import pandas as pd
import streamlit as st

from services.cloudwalk_financial_cost import (
    CostRunConfig,
    FinancialCostOutputs,
    build_financial_cost_outputs,
    load_amortization_convention_overrides,
    load_cash_yield_factor,
    load_funding_lines,
    load_ime_financial_snapshots,
    load_spread_overrides,
)
from services.cloudwalk_financial_cost_exports import (
    build_cloudwalk_financial_cost_pptx_bytes,
    build_cloudwalk_financial_cost_xlsx_bytes,
)
from services.cloudwalk_pl_waterfall import CloudwalkPlWaterfall, build_cloudwalk_pl_waterfall
from services.fidc_model.b3_cdi import B3CdiMonthlyRate, fetch_b3_cdi_monthly_rates
from services.fidc_model.b3_curves import fetch_latest_taxaswap_curve
from services.fidc_model.curves import INTERPOLATION_METHOD_FLAT_FORWARD_252, interpolate_curve
from services.waterfall_schedule import DEFAULT_REFERENCE_DATE, only_digits


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EMISSIONS_CSV = ROOT / "data/regulatory_profiles/cloudwalk_cotas_emissoes_pagamentos.csv"
DEFAULT_CONFIG_JSON = ROOT / "config/cloudwalk_financial_cost_inputs.json"
DEFAULT_RUNTIME_CACHE_ROOT = ROOT / ".cache/fundonet-ime"
DEFAULT_PORTABLE_CACHE_ROOT = ROOT / "data/ime_cache/fundonet-ime"

_CSS = """
<style>
.cloudwalk-header {
    border-bottom: 1px solid #dde3ea;
    margin: 0.15rem 0 1rem 0;
    padding-bottom: 0.85rem;
}
.cloudwalk-kicker {
    color: #d35714;
    font-size: 0.74rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    line-height: 1.2;
    margin-bottom: 0.25rem;
    text-transform: uppercase;
}
.cloudwalk-title {
    color: #12171d;
    font-size: 2rem;
    font-weight: 650;
    letter-spacing: 0;
    line-height: 1.08;
    margin: 0;
}
.cloudwalk-subtitle {
    color: #68727d;
    font-size: 0.96rem;
    line-height: 1.48;
    margin-top: 0.45rem;
    max-width: 56rem;
}
.cloudwalk-note {
    background: #f7f8fa;
    border: 1px solid #e5e9ef;
    border-radius: 8px;
    color: #4f5c69;
    font-size: 0.86rem;
    line-height: 1.48;
    margin: 0.25rem 0 0.85rem 0;
    padding: 0.75rem 0.85rem;
}
.cloudwalk-section-title {
    color: #161c23;
    font-size: 1.05rem;
    font-weight: 650;
    letter-spacing: 0;
    margin: 1rem 0 0.45rem 0;
}
</style>
"""


def render_tab_cloudwalk_financial_cost() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="cloudwalk-header">
          <div class="cloudwalk-kicker">Cloudwalk</div>
          <h2 class="cloudwalk-title">Custo financeiro dos FIDCs</h2>
          <div class="cloudwalk-subtitle">
            Estimativa anual com gross-up gerencial da receita de antecipação, amortizações,
            captações intraperíodo e carry de caixa/LFT.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    controls = _render_controls()
    if controls is None:
        return

    try:
        outputs, pl_waterfall = _run_cost_engine(**controls)
    except Exception as exc:  # noqa: BLE001
        st.error("Não foi possível rodar a estimativa Cloudwalk.")
        st.caption(f"{type(exc).__name__}: {exc}")
        return

    _render_headline(outputs)
    tabs = st.tabs(["Resumo", "Preço por série", "Custo mensal", "Waterfall PL", "Caixa/LFT", "Downloads"])
    with tabs[0]:
        _render_summary(outputs, controls)
    with tabs[1]:
        _render_lines(outputs)
    with tabs[2]:
        _render_monthly(outputs)
    with tabs[3]:
        _render_pl_waterfall(pl_waterfall)
    with tabs[4]:
        _render_cash(outputs)
    with tabs[5]:
        _render_downloads(outputs, pl_waterfall, controls)


def _render_controls() -> dict[str, object] | None:
    base_config = _load_base_config()
    current_year = date.today().year
    with st.form("cloudwalk_financial_cost_controls", border=False):
        col1, col2, col3 = st.columns([0.8, 1.1, 1.1])
        year = col1.number_input(
            "Ano-base",
            min_value=2020,
            max_value=2035,
            value=current_year,
            step=1,
            help="Preenche automaticamente o período de 01/jan a 31/dez. Ajuste as datas ao lado para simular outro intervalo.",
        )
        default_start = date(int(year), 1, 1)
        default_end = date(int(year), 12, 31)
        start_date = col2.date_input(
            "Data inicial",
            value=default_start,
            format="YYYY-MM-DD",
            help="Primeiro dia considerado para captações, amortizações, CDI e saldo médio das cotas.",
        )
        end_date = col3.date_input(
            "Data final",
            value=default_end,
            format="YYYY-MM-DD",
            help="Último dia considerado. O motor corta emissões futuras e amortizações fora do período.",
        )

        col4, col5 = st.columns([1.1, 2.2])
        cash_yield_factor = col4.number_input(
            "Caixa/LFT (x CDI)",
            value=float(base_config["cash_yield_factor"]),
            min_value=0.0,
            max_value=2.0,
            step=0.05,
            help="Multiplicador aplicado à rentabilidade do caixa/LFT. Use 1,00 para 100% do CDI; use 0,00 para não abater carry de caixa.",
        )
        curve_date = col5.date_input(
            "CDI fallback B3",
            value=date.today(),
            format="YYYY-MM-DD",
            help="Só é usado se o CDI mensal B3/Cetip não estiver disponível para o período.",
        )

        spread_table = _spread_input_table(base_config["spread_overrides"], base_config["amortization_conventions"])
        edited_spreads = pd.DataFrame()
        with st.expander("CDI+ manual por série", expanded=False):
            st.caption(
                "Preencha apenas quando quiser substituir ou completar o CDI+ lido dos documentos. "
                "Valor em % a.a.; exemplo: 1,20 significa CDI+1,20% a.a."
            )
            if spread_table.empty:
                st.success("Nenhuma série ativa remunerada para editar.")
            else:
                edited_spreads = st.data_editor(
                    spread_table,
                    hide_index=True,
                    width="stretch",
                    disabled=["FIDC", "Série", "CDI+ atual (% a.a.)", "Fonte atual", "Chave"],
                    column_config={
                        "CDI+ manual (% a.a.)": st.column_config.NumberColumn(
                            "CDI+ manual (% a.a.)",
                            help="Opcional. Preencha em pontos percentuais: 0,95 para CDI+0,95% a.a.",
                            format="%.2f",
                            min_value=-10.0,
                            max_value=30.0,
                        ),
                        "Chave": st.column_config.TextColumn(
                            "Chave",
                            help="Identificador técnico da série: CNPJ|nome da cota. Mantido visível para conciliar com a memória.",
                        ),
                    },
                )

        submitted = st.form_submit_button("Atualizar estimativa", width="stretch")

    if not submitted and "cloudwalk_cost_has_run" not in st.session_state:
        st.session_state["cloudwalk_cost_has_run"] = True
    elif submitted:
        st.session_state["cloudwalk_cost_has_run"] = True

    if end_date < start_date:
        st.warning("A data final precisa ser maior ou igual à data inicial.")
        return None

    monthly_cdi_rates = _resolve_monthly_cdi(start_date, end_date)
    monthly_cdi_aa = _annualize_monthly_cdi(monthly_cdi_rates)
    if monthly_cdi_aa is not None:
        cdi_aa, cdi_source = monthly_cdi_aa, "B3/Cetip MediaCDI diário composto por mês"
    else:
        cdi_aa, cdi_source = _resolve_b3_cdi(curve_date, 0.1399364)
    if monthly_cdi_rates:
        cdi_source = "B3/Cetip MediaCDI diário composto por mês"

    merged_overrides = dict(base_config["spread_overrides"])
    merged_overrides.update(_parse_spread_editor(edited_spreads))
    return {
        "start_date": start_date,
        "end_date": end_date,
        "snapshot_date": _default_snapshot_date(start_date, end_date),
        "cdi_aa": cdi_aa,
        "cdi_source": cdi_source,
        "monthly_cdi_rates": monthly_cdi_rates,
        "cash_yield_factor": cash_yield_factor,
        "spread_overrides": merged_overrides,
        "amortization_conventions": dict(base_config["amortization_conventions"]),
    }


@st.cache_data(show_spinner=False)
def _load_base_config() -> dict[str, object]:
    return {
        "spread_overrides": load_spread_overrides(DEFAULT_CONFIG_JSON),
        "amortization_conventions": load_amortization_convention_overrides(DEFAULT_CONFIG_JSON),
        "cash_yield_factor": load_cash_yield_factor(DEFAULT_CONFIG_JSON),
    }


@st.cache_data(show_spinner="Buscando e compondo CDI B3 mês a mês...")
def _resolve_monthly_cdi(start_date: date, end_date: date) -> tuple[B3CdiMonthlyRate, ...]:
    return fetch_b3_cdi_monthly_rates(start_date, end_date)


@st.cache_data(show_spinner="Buscando CDI na B3...")
def _fetch_b3_cdi(curve_date_iso: str) -> tuple[float, str]:
    snapshot = fetch_latest_taxaswap_curve(start_date=date.fromisoformat(curve_date_iso), curve_code="PRE")
    cdi_aa = interpolate_curve(
        252.0,
        snapshot.curva_du,
        snapshot.curva_taxa_aa,
        method=INTERPOLATION_METHOD_FLAT_FORWARD_252,
    )
    return float(cdi_aa), f"B3 TaxaSwap PRE {snapshot.generated_at.isoformat()} DU252"


def _resolve_b3_cdi(curve_date: date, fallback_cdi_aa: float) -> tuple[float, str]:
    try:
        return _fetch_b3_cdi(curve_date.isoformat())
    except Exception as exc:  # noqa: BLE001
        st.warning("A consulta à B3 falhou; usando o CDI manual como fallback.")
        st.caption(f"{type(exc).__name__}: {exc}")
        return fallback_cdi_aa, "manual fallback após falha B3"


@st.cache_data(show_spinner="Calculando custo financeiro Cloudwalk...")
def _run_cost_engine(
    *,
    start_date: date,
    end_date: date,
    snapshot_date: date,
    cdi_aa: float,
    cdi_source: str,
    monthly_cdi_rates: tuple[B3CdiMonthlyRate, ...],
    cash_yield_factor: float,
    spread_overrides: dict[str, float],
    amortization_conventions: dict[str, str],
) -> tuple[FinancialCostOutputs, CloudwalkPlWaterfall]:
    lines = load_funding_lines(
        DEFAULT_EMISSIONS_CSV,
        spread_overrides=spread_overrides,
        amortization_convention_overrides=amortization_conventions,
    )
    fund_names = {only_digits(line.cnpj): line.fund_name for line in lines if line.fund_name}
    snapshots = load_ime_financial_snapshots(
        [line.cnpj for line in lines if line.included],
        fund_names=fund_names,
        cache_root=DEFAULT_RUNTIME_CACHE_ROOT,
        portable_cache_root=DEFAULT_PORTABLE_CACHE_ROOT,
    )
    outputs = build_financial_cost_outputs(
        lines=lines,
        snapshots=snapshots,
        config=CostRunConfig(
            start_date=start_date,
            end_date=end_date,
            snapshot_date=snapshot_date,
            cdi_aa=float(cdi_aa),
            cdi_source=cdi_source,
            cash_yield_cdi_factor=float(cash_yield_factor),
            monthly_cdi_rates=monthly_cdi_rates,
        ),
    )
    pl_waterfall = build_cloudwalk_pl_waterfall(
        [line.cnpj for line in lines if line.included],
        fund_names=fund_names,
        year=start_date.year,
        end_date=end_date,
        cache_root=DEFAULT_RUNTIME_CACHE_ROOT,
        portable_cache_root=DEFAULT_PORTABLE_CACHE_ROOT,
    )
    return outputs, pl_waterfall


def _render_headline(outputs: FinancialCostOutputs) -> None:
    summary = outputs.summary_df
    recommended = _summary_row(summary, "2_programado_bruto_com_amortizacao")
    net = _summary_row(summary, "3_programado_liquido_caixa_lft")
    cash_base, cash_yield = _cash_totals(outputs)
    cdi_aa = float(recommended["cdi_aa"])
    implied_spread = _solve_implied_spread(outputs.monthly_df, float(recommended["despesa_financeira_bruta"]), cdi_aa)
    weighted_spread = _weighted_average_spread(outputs.line_df)

    cols = st.columns(6)
    cols[0].metric("Despesa bruta", _format_money(float(recommended["despesa_financeira_bruta"])))
    cols[1].metric("Custo líquido", _format_money(float(net["despesa_financeira_liquida"])))
    cols[2].metric("Aplicação caixa/LFT", _format_money(cash_base))
    cols[3].metric("Rendimento caixa/LFT", _format_money(cash_yield))
    cols[4].metric("Saldo médio", _format_money(float(recommended["saldo_base"])))
    cols[5].metric("CDI+ implícito", _format_cdi_plus(implied_spread))

    note = (
        f"CDI usado: {_format_percent(cdi_aa)} a.a. equivalente ({recommended['cdi_source']}). "
        f"Spread ponderado por saldo médio: {_format_cdi_plus(weighted_spread)}."
    )
    st.markdown(f"<div class='cloudwalk-note'>{note}</div>", unsafe_allow_html=True)


def _render_summary(outputs: FinancialCostOutputs, controls: dict[str, object]) -> None:
    st.markdown("<div class='cloudwalk-section-title'>Estimativas principais</div>", unsafe_allow_html=True)
    display = outputs.summary_df.copy()
    display = display[display["estimativa"].isin(["2_programado_bruto_com_amortizacao", "3_programado_liquido_caixa_lft"])].copy()
    display["estimativa"] = display["estimativa"].map(
        {
            "2_programado_bruto_com_amortizacao": "Bruto programado",
            "3_programado_liquido_caixa_lft": "Líquido após caixa/LFT",
        }
    )
    display["descricao"] = display["descricao"].map(_short_description)
    money_columns = [
        "despesa_financeira_bruta",
        "receita_antecipacao_gross_up_sugerida",
        "rendimento_caixa_lft",
        "despesa_financeira_liquida",
        "saldo_base",
        "saldo_snapshot_sem_spread",
    ]
    for column in money_columns:
        display[column] = display[column].map(_format_money)
    display["cdi_aa"] = display["cdi_aa"].map(_format_percent)
    display = display.rename(
        columns={
            "estimativa": "Estimativa",
            "descricao": "Como ler",
            "despesa_financeira_bruta": "Despesa bruta",
            "receita_antecipacao_gross_up_sugerida": "Gross-up receita",
            "rendimento_caixa_lft": "Rendimento caixa/LFT",
            "despesa_financeira_liquida": "Despesa líquida",
            "saldo_base": "Saldo médio",
            "linhas_incluidas": "Séries incluídas",
            "linhas_sem_spread": "Séries sem CDI+",
            "periodo_inicio": "Início",
            "periodo_fim": "Fim",
            "cdi_aa": "CDI a.a.",
            "cdi_source": "Fonte CDI",
        }
    )
    summary_columns = [
        "Estimativa",
        "Como ler",
        "Despesa bruta",
        "Gross-up receita",
        "Rendimento caixa/LFT",
        "Despesa líquida",
        "Saldo médio",
        "Séries incluídas",
        "Séries sem CDI+",
        "Início",
        "Fim",
        "CDI a.a.",
        "Fonte CDI",
    ]
    display = display[[column for column in summary_columns if column in display.columns]]
    st.dataframe(display, hide_index=True, width="stretch")
    cdi_frame = _cdi_rates_frame(controls.get("monthly_cdi_rates") or ())
    if not cdi_frame.empty:
        st.markdown("<div class='cloudwalk-section-title'>CDI B3 composto mês a mês</div>", unsafe_allow_html=True)
        cdi_display = cdi_frame.copy()
        cdi_display["cdi_mensal"] = pd.to_numeric(cdi_display["cdi_mensal"], errors="coerce").map(_format_percent)
        cdi_display["cdi_aa_equivalente"] = pd.to_numeric(cdi_display["cdi_aa_equivalente"], errors="coerce").map(_format_percent)
        cdi_display = cdi_display.rename(
            columns={
                "mes": "Mês",
                "cdi_mensal": "CDI mensal",
                "cdi_aa_equivalente": "CDI a.a. equivalente",
                "dias_uteis": "Dias úteis",
            }
        )
        st.dataframe(cdi_display, hide_index=True, width="stretch")


def _render_lines(outputs: FinancialCostOutputs) -> None:
    frame = outputs.line_df.copy()
    active = frame[frame["included_in_cost"].fillna(False).astype(bool)].copy()
    if active.empty:
        st.info("Nenhuma linha incluída no custo.")
        return

    st.markdown("<div class='cloudwalk-section-title'>Preço por série</div>", unsafe_allow_html=True)
    fund_cost = (
        active.groupby("fund_name", as_index=False)
        .agg(saldo_medio_programado=("saldo_medio_programado", "sum"), custo_programado_bruto=("custo_programado_bruto", "sum"))
        .sort_values("custo_programado_bruto", ascending=False)
    )
    chart = (
        alt.Chart(fund_cost)
        .mark_bar(color="#1f77b4")
        .encode(
            x=alt.X("custo_programado_bruto:Q", title="Custo bruto estimado"),
            y=alt.Y("fund_name:N", sort="-x", title="FIDC"),
            tooltip=[
                alt.Tooltip("fund_name:N", title="FIDC"),
                alt.Tooltip("custo_programado_bruto:Q", title="Custo", format=",.0f"),
                alt.Tooltip("saldo_medio_programado:Q", title="Saldo médio", format=",.0f"),
            ],
        )
        .properties(height=max(260, 26 * len(fund_cost)))
    )
    st.altair_chart(chart, width="stretch")

    st.dataframe(_series_price_frame(frame), hide_index=True, width="stretch")


def _render_monthly(outputs: FinancialCostOutputs) -> None:
    frame = outputs.monthly_df.copy()
    if frame.empty:
        st.info("Sem custo mensal calculado.")
        return
    monthly = frame.groupby("mes", as_index=False).agg(
        saldo_base=("saldo_base", "sum"),
        custo_programado_bruto=("custo_programado_bruto", "sum"),
    )
    chart = (
        alt.Chart(monthly)
        .mark_bar(color="#d35714")
        .encode(
            x=alt.X("mes:N", title="Mês"),
            y=alt.Y("custo_programado_bruto:Q", title="Custo bruto"),
            tooltip=[
                alt.Tooltip("mes:N", title="Mês"),
                alt.Tooltip("custo_programado_bruto:Q", title="Custo", format=",.0f"),
                alt.Tooltip("saldo_base:Q", title="Saldo base", format=",.0f"),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, width="stretch")
    monthly_display = monthly.copy()
    monthly_display["saldo_base"] = monthly_display["saldo_base"].map(_format_money)
    monthly_display["custo_programado_bruto"] = monthly_display["custo_programado_bruto"].map(_format_money)
    monthly_display = monthly_display.rename(
        columns={
            "mes": "Mês",
            "saldo_base": "Saldo base",
            "custo_programado_bruto": "Custo bruto",
        }
    )
    st.dataframe(monthly_display, hide_index=True, width="stretch")


def _render_pl_waterfall(pl_waterfall: CloudwalkPlWaterfall) -> None:
    if pl_waterfall.steps_df.empty:
        st.info("Sem dados de PL para montar o waterfall.")
        return
    chart_df = _waterfall_chart_frame(pl_waterfall.steps_df)
    color_scale = alt.Scale(domain=["total", "up", "down"], range=["#111111", "#0f9d58", "#d93025"])
    bars = (
        alt.Chart(chart_df)
        .mark_bar(size=42)
        .encode(
            x=alt.X("etapa:N", title=None, sort=None),
            y=alt.Y("bar_start:Q", title="PL / variação"),
            y2="bar_end:Q",
            color=alt.Color("tipo:N", scale=color_scale, legend=None),
            tooltip=[
                alt.Tooltip("etapa:N", title="Etapa"),
                alt.Tooltip("valor:Q", title="Valor", format=",.0f"),
                alt.Tooltip("acumulado:Q", title="Acumulado", format=",.0f"),
            ],
        )
    )
    labels = (
        alt.Chart(chart_df)
        .mark_text(dy=-8, fontSize=11, color="#111111")
        .encode(x=alt.X("etapa:N", sort=None), y=alt.Y("label_y:Q"), text="label:N")
    )
    st.altair_chart((bars + labels).properties(height=360), width="stretch")
    st.dataframe(_pl_waterfall_frame(pl_waterfall.by_fund_df), hide_index=True, width="stretch")


def _render_cash(outputs: FinancialCostOutputs) -> None:
    frame = outputs.ime_snapshot_df.copy()
    if frame.empty:
        st.info("Sem informe mensal em cache para caixa/LFT.")
        return
    total_cash, total_yield = _cash_totals(outputs)
    reported_cash = pd.to_numeric(frame["cash_like_reported"], errors="coerce").fillna(0.0).sum()
    residual_proxy = pd.to_numeric(frame["cash_like_residual_proxy"], errors="coerce").fillna(0.0).sum()
    cols = st.columns(4)
    cols[0].metric("Aplicação caixa/LFT", _format_money(total_cash))
    cols[1].metric("Rendimento estimado", _format_money(total_yield))
    cols[2].metric("Caixa + títulos", _format_money(reported_cash))
    cols[3].metric("Proxy PL - recebíveis", _format_money(residual_proxy))
    st.dataframe(_cash_frame(frame), hide_index=True, width="stretch")


def _render_downloads(outputs: FinancialCostOutputs, pl_waterfall: CloudwalkPlWaterfall, controls: dict[str, object]) -> None:
    recommended = _summary_row(outputs.summary_df, "2_programado_bruto_com_amortizacao")
    st.markdown("<div class='cloudwalk-section-title'>Premissas e downloads</div>", unsafe_allow_html=True)
    assumptions = pd.DataFrame(
        [
            ("Período calculado", f"{recommended['periodo_inicio']} a {recommended['periodo_fim']}"),
            ("CDI", f"Mensal composto - {recommended['cdi_source']}"),
            ("Caixa/LFT", f"IME mais recente por fundo; rendimento a {float(recommended['cash_yield_cdi_factor']):.2f}x CDI"),
            ("CDI+ manual", "Editável na seção 'CDI+ manual por série'; valores em % a.a."),
            ("Base de cotas", str(DEFAULT_EMISSIONS_CSV.relative_to(ROOT))),
            ("Cache IME", "Cache local e portátil do Toma Conta FIDCs."),
        ],
        columns=["Premissa", "Valor"],
    )
    st.dataframe(assumptions, hide_index=True, width="stretch")

    if outputs.missing_inputs_df.empty:
        st.success("Todas as linhas ativas incluídas têm spread CDI+ definido ou parseável.")
    else:
        st.warning("Há linhas ativas sem spread CDI+.")
        st.dataframe(outputs.missing_inputs_df, hide_index=True, width="stretch")

    with st.expander("Memória metodológica"):
        st.markdown(outputs.methodology_md)

    xlsx_bytes = build_cloudwalk_financial_cost_xlsx_bytes(
        outputs,
        pl_waterfall=pl_waterfall,
        monthly_cdi_rates=controls.get("monthly_cdi_rates") or (),
    )
    pptx_bytes = build_cloudwalk_financial_cost_pptx_bytes(outputs, pl_waterfall=pl_waterfall)
    col1, col2, col3 = st.columns(3)
    col1.download_button(
        "Baixar memória XLSX",
        data=xlsx_bytes,
        file_name=f"cloudwalk_memoria_custo_fidcs_{controls['start_date']}_{controls['end_date']}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
    col2.download_button(
        "Baixar PPTX",
        data=pptx_bytes,
        file_name=f"cloudwalk_custo_fidcs_{controls['start_date']}_{controls['end_date']}.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        width="stretch",
    )
    col3.download_button(
        "Baixar pacote CSV",
        data=_zip_outputs(outputs),
        file_name=f"cloudwalk_financial_cost_{controls['start_date']}_{controls['end_date']}.zip",
        mime="application/zip",
        width="stretch",
    )


def _summary_row(summary: pd.DataFrame, estimativa: str) -> pd.Series:
    return summary.loc[summary["estimativa"].eq(estimativa)].iloc[0]


def _spread_input_table(spread_overrides: dict[str, float], amortization_conventions: dict[str, str]) -> pd.DataFrame:
    lines = load_funding_lines(
        DEFAULT_EMISSIONS_CSV,
        spread_overrides=spread_overrides,
        amortization_convention_overrides=amortization_conventions,
    )
    rows = []
    for line in lines:
        if not line.included or not _is_priced_class(line.class_macro):
            continue
        manual = spread_overrides.get(line.line_key)
        rows.append(
            {
                "FIDC": _short_fund_name(line.fund_name),
                "Série": line.classe,
                "CDI+ atual (% a.a.)": None if line.spread_aa is None else round(line.spread_aa * 100.0, 4),
                "CDI+ manual (% a.a.)": None if manual is None else round(manual * 100.0, 4),
                "Fonte atual": _spread_source_label(line.spread_source),
                "Chave": line.line_key,
            }
        )
    return pd.DataFrame(rows)


def _parse_spread_editor(frame: pd.DataFrame) -> dict[str, float]:
    if frame is None or frame.empty:
        return {}
    parsed: dict[str, float] = {}
    for _, row in frame.iterrows():
        key = str(row.get("Chave") or "").strip()
        value = pd.to_numeric(pd.Series([row.get("CDI+ manual (% a.a.)")]), errors="coerce").iloc[0]
        if key and pd.notna(value):
            parsed[key] = float(value) / 100.0
    return parsed


def _is_priced_class(class_macro: str) -> bool:
    return str(class_macro).strip().lower() in {"senior", "mezzanino"}


def _cash_totals(outputs: FinancialCostOutputs) -> tuple[float, float]:
    frame = outputs.ime_snapshot_df
    if frame.empty:
        return 0.0, 0.0
    cash_base = pd.to_numeric(frame.get("cash_like_caixa_lft", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()
    cash_yield = pd.to_numeric(frame.get("rendimento_estimado_caixa_lft", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()
    return float(cash_base), float(cash_yield)


def _short_description(value: object) -> str:
    text = str(value or "")
    if "Custo bruto por linha" in text:
        return "Saldo por série, mês a mês, com CDI B3 composto, captações e amortizações."
    if "Custo bruto programado menos rendimento" in text:
        return "Mesma despesa bruta, abatendo o rendimento estimado da aplicação em caixa/LFT."
    return text


def _series_price_frame(line_df: pd.DataFrame) -> pd.DataFrame:
    frame = line_df[line_df["included"].fillna(False).astype(bool)].copy()
    if frame.empty:
        return pd.DataFrame()
    frame["FIDC"] = frame["fund_name"].map(_short_fund_name)
    frame["Série"] = frame["classe"]
    frame["Classe"] = frame["class_macro"].map(_class_label)
    frame["Data emissão"] = frame["issue_date"].replace("", "N/D")
    frame["Volume emitido"] = pd.to_numeric(frame["volume_emitido"], errors="coerce").map(_format_money)
    frame["CDI+ a.a."] = pd.to_numeric(frame["spread_cdi_plus_aa"], errors="coerce").map(_format_percent)
    frame["Fonte CDI+"] = frame["spread_source"].map(_spread_source_label)
    frame["Saldo médio"] = pd.to_numeric(frame["saldo_medio_programado"], errors="coerce").map(_format_money)
    frame["Custo bruto"] = pd.to_numeric(frame["custo_programado_bruto"], errors="coerce").map(_format_money)
    frame["Amortização"] = pd.to_numeric(frame["amortizacao_no_periodo"], errors="coerce").map(_format_money)
    frame["Convenção amort."] = frame["amortization_convention"].map(_amortization_label)
    frame["Observação"] = frame["warnings"].fillna("").replace("", "OK")
    frame["Chave"] = frame["line_key"]
    return frame[
        [
            "FIDC",
            "Série",
            "Classe",
            "Data emissão",
            "Volume emitido",
            "CDI+ a.a.",
            "Fonte CDI+",
            "Saldo médio",
            "Custo bruto",
            "Amortização",
            "Convenção amort.",
            "Observação",
            "Chave",
        ]
    ].sort_values(["FIDC", "Série"])


def _cash_frame(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    if output.empty:
        return output
    output["FIDC"] = output["fund_name"].map(_short_fund_name)
    output["Competência IME"] = output["competencia"]
    output["PL"] = pd.to_numeric(output["pl_total"], errors="coerce").map(_format_money)
    output["Caixa"] = pd.to_numeric(output["caixa"], errors="coerce").map(_format_money)
    output["Títulos públicos"] = pd.to_numeric(output["titulos_publicos"], errors="coerce").map(_format_money)
    output["Recebíveis"] = pd.to_numeric(output["recebiveis"], errors="coerce").map(_format_money)
    output["Caixa + títulos"] = pd.to_numeric(output["cash_like_reported"], errors="coerce").map(_format_money)
    output["Proxy PL - recebíveis"] = pd.to_numeric(output["cash_like_residual_proxy"], errors="coerce").map(_format_money)
    output["Aplicação caixa/LFT"] = pd.to_numeric(output["cash_like_caixa_lft"], errors="coerce").map(_format_money)
    output["Critério usado"] = output["cash_like_method"].map(_cash_method_label)
    output["Rendimento estimado"] = pd.to_numeric(output["rendimento_estimado_caixa_lft"], errors="coerce").map(_format_money)
    return output[
        [
            "FIDC",
            "Competência IME",
            "PL",
            "Caixa",
            "Títulos públicos",
            "Recebíveis",
            "Caixa + títulos",
            "Proxy PL - recebíveis",
            "Aplicação caixa/LFT",
            "Critério usado",
            "Rendimento estimado",
        ]
    ]


def _pl_waterfall_frame(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    if output.empty:
        return output
    output["FIDC"] = output.get("short_name", output.get("fund_name", pd.Series(dtype=str))).map(_short_fund_name)
    output["PL inicial"] = pd.to_numeric(output["pl_inicial"], errors="coerce").map(_format_money)
    output["Captações"] = pd.to_numeric(output["captacoes"], errors="coerce").map(_format_money)
    output["Resgates"] = pd.to_numeric(output["resgates"], errors="coerce").map(_format_money)
    output["Amortizações"] = pd.to_numeric(output["amortizacoes"], errors="coerce").map(_format_money)
    output["Accrual / residual"] = pd.to_numeric(output["accrual_rentabilidade_residual"], errors="coerce").map(_format_money)
    output["PL final"] = pd.to_numeric(output["pl_final"], errors="coerce").map(_format_money)
    output["Início"] = output["start_comp"]
    output["Fim"] = output["end_comp"]
    output["Status"] = output["status"]
    return output[["FIDC", "Início", "Fim", "PL inicial", "Captações", "Resgates", "Amortizações", "Accrual / residual", "PL final", "Status"]]


def _short_fund_name(name: object) -> str:
    text = str(name or "").upper()
    if "BELA" in text:
        return "Bela"
    if "PI FUNDO" in text:
        return "PI"
    if "A.I." in text:
        return "A.I."
    if "AKIRA II" in text:
        return "Akira II"
    if "AKIRA I" in text:
        return "Akira I"
    if "KICK ASS I" in text:
        return "Kick Ass I"
    if "KICK ASS II" in text:
        return "Kick Ass II"
    if "BIG PICTURE IV" in text:
        return "Big Picture IV"
    if "BIG PICTURE III" in text:
        return "Big Picture III"
    if "BIG PICTURE II" in text:
        return "Big Picture II"
    if "BIG PICTURE I" in text:
        return "Big Picture I"
    return str(name or "")


def _class_label(value: object) -> str:
    mapping = {"senior": "Sênior", "mezzanino": "Mezanino", "subordinada": "Subordinada"}
    return mapping.get(str(value or "").strip().lower(), str(value or ""))


def _spread_source_label(value: object) -> str:
    text = str(value or "")
    if text.startswith("override:"):
        return "Manual"
    if text == "curadoria:remuneracao":
        return "Documento/curadoria"
    if text == "pendente":
        return "Pendente"
    return text


def _amortization_label(value: object) -> str:
    mapping = {
        "incremental": "%/valor sobre principal original",
        "cumulative": "% acumulado",
        "current_balance": "% sobre saldo remanescente",
        "linear_de_intervalo_documentado": "Linear por intervalo",
        "nao_aplicavel": "Não aplicável",
        "sem_cronograma_parseavel": "Saldo constante",
    }
    return mapping.get(str(value or ""), str(value or ""))


def _cash_method_label(value: object) -> str:
    mapping = {
        "reportado_caixa_titpub": "Caixa + títulos públicos",
        "proxy_pl_menos_recebiveis": "Proxy PL - recebíveis",
        "sem_cache": "Sem IME em cache",
        "erro": "Erro de leitura",
    }
    return mapping.get(str(value or ""), str(value or ""))


def _annualize_monthly_cdi(monthly_cdi_rates: tuple[B3CdiMonthlyRate, ...]) -> float | None:
    if not monthly_cdi_rates:
        return None
    total_du = sum(item.dias_uteis for item in monthly_cdi_rates)
    if total_du <= 0:
        return None
    compounded = 1.0
    for item in monthly_cdi_rates:
        compounded *= 1.0 + item.cdi_mensal
    return compounded ** (252.0 / total_du) - 1.0


def _cdi_rates_frame(monthly_cdi_rates: tuple[B3CdiMonthlyRate, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "mes": item.mes,
                "cdi_mensal": item.cdi_mensal,
                "cdi_aa_equivalente": item.cdi_aa_equivalente,
                "dias_uteis": item.dias_uteis,
            }
            for item in monthly_cdi_rates
        ]
    )


def _waterfall_chart_frame(steps_df: pd.DataFrame) -> pd.DataFrame:
    running = 0.0
    rows = []
    for index, row in steps_df.reset_index(drop=True).iterrows():
        value = float(row["valor"])
        measure = str(row["measure"])
        if measure == "total":
            bar_start, bar_end = 0.0, value
            running = value
            tipo = "total"
        else:
            previous = running
            running += value
            bar_start, bar_end = min(previous, running), max(previous, running)
            tipo = "up" if value >= 0 else "down"
        rows.append(
            {
                "etapa": row["etapa"],
                "valor": value,
                "bar_start": bar_start,
                "bar_end": bar_end,
                "label_y": bar_end,
                "acumulado": running,
                "tipo": tipo,
                "label": _format_money(value),
            }
        )
    return pd.DataFrame(rows)


def _default_snapshot_date(start_date: date, end_date: date) -> date:
    if start_date <= DEFAULT_REFERENCE_DATE <= end_date:
        return DEFAULT_REFERENCE_DATE
    if DEFAULT_REFERENCE_DATE > end_date:
        return end_date
    return start_date


def _solve_implied_spread(monthly_df: pd.DataFrame, target_cost: float, cdi_aa: float) -> float | None:
    if monthly_df.empty or target_cost <= 0.0:
        return None
    frame = monthly_df.copy()
    frame["saldo_base"] = pd.to_numeric(frame["saldo_base"], errors="coerce").fillna(0.0)
    frame["dias_uteis"] = pd.to_numeric(frame["dias_uteis"], errors="coerce").fillna(0.0)
    frame["cdi_mensal"] = pd.to_numeric(frame.get("cdi_mensal", pd.Series(dtype=float)), errors="coerce")
    frame["dias_uteis_cdi_mes"] = pd.to_numeric(frame.get("dias_uteis_cdi_mes", pd.Series(dtype=float)), errors="coerce")
    frame = frame[(frame["saldo_base"] > 0.0) & (frame["dias_uteis"] > 0.0)]
    if frame.empty:
        return None

    def cost_for_spread(spread: float) -> float:
        monthly_mask = frame["cdi_mensal"].notna() & frame["dias_uteis_cdi_mes"].gt(0)
        cost = 0.0
        if monthly_mask.any():
            subset = frame[monthly_mask]
            cdi_factor = (1.0 + subset["cdi_mensal"]) ** (subset["dias_uteis"] / subset["dias_uteis_cdi_mes"]) - 1.0
            spread_factor = (1.0 + spread) ** (subset["dias_uteis"] / 252.0) - 1.0
            cost += float((subset["saldo_base"] * ((1.0 + cdi_factor) * (1.0 + spread_factor) - 1.0)).sum())
        if (~monthly_mask).any():
            subset = frame[~monthly_mask]
            rate = max(cdi_aa + spread, -0.999999)
            cost += float((subset["saldo_base"] * ((1.0 + rate) ** (subset["dias_uteis"] / 252.0) - 1.0)).sum())
        return cost

    lo, hi = -0.5, 0.5
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if cost_for_spread(mid) < target_cost:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _weighted_average_spread(line_df: pd.DataFrame) -> float | None:
    if line_df.empty:
        return None
    frame = line_df[line_df["included_in_cost"].fillna(False).astype(bool)].copy()
    frame["spread_cdi_plus_aa"] = pd.to_numeric(frame["spread_cdi_plus_aa"], errors="coerce")
    frame["saldo_medio_programado"] = pd.to_numeric(frame["saldo_medio_programado"], errors="coerce").fillna(0.0)
    frame = frame[(frame["spread_cdi_plus_aa"].notna()) & (frame["saldo_medio_programado"] > 0.0)]
    denominator = frame["saldo_medio_programado"].sum()
    if denominator <= 0.0:
        return None
    return float((frame["spread_cdi_plus_aa"] * frame["saldo_medio_programado"]).sum() / denominator)


def _format_line_table(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in output.columns:
        if column in {
            "volume_emitido",
            "saldo_snapshot",
            "saldo_inicio_periodo",
            "saldo_medio_programado",
            "custo_snapshot_sem_amortizacao",
            "custo_programado_bruto",
            "amortizacao_no_periodo",
            "saldo_base",
            "rendimento_estimado_caixa_lft",
            "pl_total",
            "caixa",
            "titulos_publicos",
            "recebiveis",
            "cash_like_reported",
            "cash_like_residual_proxy",
            "cash_like_caixa_lft",
        }:
            output[column] = pd.to_numeric(output[column], errors="coerce").map(_format_money)
        elif column in {"spread_cdi_plus_aa", "taxa_total_aa", "cdi_aa"}:
            output[column] = pd.to_numeric(output[column], errors="coerce").map(_format_percent)
        elif column in {"cdi_mensal", "cdi_aa_equivalente"}:
            output[column] = pd.to_numeric(output[column], errors="coerce").map(_format_percent)
    return output


def _zip_outputs(outputs: FinancialCostOutputs) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("cloudwalk_financial_cost_summary.csv", outputs.summary_df.to_csv(index=False))
        archive.writestr("cloudwalk_financial_cost_by_line.csv", outputs.line_df.to_csv(index=False))
        archive.writestr("cloudwalk_financial_cost_monthly.csv", outputs.monthly_df.to_csv(index=False))
        archive.writestr("cloudwalk_financial_cost_ime_snapshot.csv", outputs.ime_snapshot_df.to_csv(index=False))
        archive.writestr("cloudwalk_financial_cost_missing_inputs.csv", outputs.missing_inputs_df.to_csv(index=False))
        archive.writestr("cloudwalk_financial_cost_methodology.md", outputs.methodology_md)
    return buffer.getvalue()


def _format_money(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(number):
        return ""
    sign = "-" if number < 0 else ""
    number = abs(number)
    if number >= 1_000_000_000:
        return f"{sign}R$ {number / 1_000_000_000:,.2f} bi"
    if number >= 1_000_000:
        return f"{sign}R$ {number / 1_000_000:,.1f} mi"
    return f"{sign}R$ {number:,.0f}"


def _format_percent(value: object, decimals: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(number):
        return ""
    return f"{number * 100:.{decimals}f}%"


def _format_cdi_plus(value: float | None) -> str:
    if value is None or pd.isna(value):
        return ""
    sign = "+" if value >= 0.0 else "-"
    return f"CDI{sign}{abs(value) * 100:.2f}% a.a."
