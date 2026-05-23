from __future__ import annotations

from datetime import date
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import altair as alt
import pandas as pd
import streamlit as st

from services.cloudwalk_financial_cost import (
    CostRunConfig,
    FinancialCostOutputs,
    build_financial_cost_outputs,
    load_cash_yield_factor,
    load_funding_lines,
    load_ime_financial_snapshots,
    load_spread_overrides,
)
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
        outputs = _run_cost_engine(**controls)
    except Exception as exc:  # noqa: BLE001
        st.error("Não foi possível rodar a estimativa Cloudwalk.")
        st.caption(f"{type(exc).__name__}: {exc}")
        return

    _render_headline(outputs)
    tabs = st.tabs(["Resumo", "FIDCs e cotas", "Mensal", "Caixa/LFT", "Premissas"])
    with tabs[0]:
        _render_summary(outputs)
    with tabs[1]:
        _render_lines(outputs)
    with tabs[2]:
        _render_monthly(outputs)
    with tabs[3]:
        _render_cash(outputs)
    with tabs[4]:
        _render_assumptions(outputs, controls)


def _render_controls() -> dict[str, object] | None:
    base_config = _load_base_config()
    current_year = date.today().year
    with st.form("cloudwalk_financial_cost_controls", border=False):
        col1, col2, col3, col4 = st.columns([0.8, 1.1, 1.1, 1.1])
        year = col1.number_input("Ano", min_value=2020, max_value=2035, value=current_year, step=1)
        default_start = date(int(year), 1, 1)
        default_end = date(int(year), 12, 31)
        start_date = col2.date_input("Início", value=default_start, format="YYYY-MM-DD")
        end_date = col3.date_input("Fim", value=default_end, format="YYYY-MM-DD")
        snapshot_default = _default_snapshot_date(start_date, end_date)
        snapshot_date = col4.date_input("Snapshot", value=snapshot_default, format="YYYY-MM-DD")

        col5, col6, col7 = st.columns([1.1, 1.1, 1.1])
        cdi_mode = col5.selectbox("CDI", ["B3 TaxaSwap PRE DU252", "Manual"], index=0)
        curve_date = col6.date_input("Data curva B3", value=date.today(), format="YYYY-MM-DD")
        manual_cdi_pct = col7.number_input("CDI manual (% a.a.)", value=13.99364, min_value=0.0, max_value=100.0, step=0.05)

        col8, col9 = st.columns([1.1, 2.2])
        cash_yield_factor = col8.number_input(
            "Fator CDI caixa/LFT",
            value=float(base_config["cash_yield_factor"]),
            min_value=0.0,
            max_value=2.0,
            step=0.05,
        )
        additional_overrides = col9.text_area(
            "Overrides CDI+ adicionais (JSON)",
            value="{}",
            height=86,
            placeholder='{"54218673000141|1ª série sênior": 0.012}',
        )

        submitted = st.form_submit_button("Atualizar estimativa", width="stretch")

    if not submitted and "cloudwalk_cost_has_run" not in st.session_state:
        st.session_state["cloudwalk_cost_has_run"] = True
    elif submitted:
        st.session_state["cloudwalk_cost_has_run"] = True

    if end_date < start_date:
        st.warning("A data final precisa ser maior ou igual à data inicial.")
        return None

    try:
        parsed_overrides = _parse_overrides(additional_overrides)
    except ValueError as exc:
        st.warning(str(exc))
        return None

    if cdi_mode == "B3 TaxaSwap PRE DU252":
        cdi_aa, cdi_source = _resolve_b3_cdi(curve_date, manual_cdi_pct / 100.0)
    else:
        cdi_aa, cdi_source = manual_cdi_pct / 100.0, "manual no Streamlit"

    merged_overrides = dict(base_config["spread_overrides"])
    merged_overrides.update(parsed_overrides)
    return {
        "start_date": start_date,
        "end_date": end_date,
        "snapshot_date": snapshot_date,
        "cdi_aa": cdi_aa,
        "cdi_source": cdi_source,
        "cash_yield_factor": cash_yield_factor,
        "spread_overrides": merged_overrides,
    }


@st.cache_data(show_spinner=False)
def _load_base_config() -> dict[str, object]:
    return {
        "spread_overrides": load_spread_overrides(DEFAULT_CONFIG_JSON),
        "cash_yield_factor": load_cash_yield_factor(DEFAULT_CONFIG_JSON),
    }


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
    cash_yield_factor: float,
    spread_overrides: dict[str, float],
) -> FinancialCostOutputs:
    lines = load_funding_lines(DEFAULT_EMISSIONS_CSV, spread_overrides=spread_overrides)
    fund_names = {only_digits(line.cnpj): line.fund_name for line in lines if line.fund_name}
    snapshots = load_ime_financial_snapshots(
        [line.cnpj for line in lines if line.included],
        fund_names=fund_names,
        cache_root=DEFAULT_RUNTIME_CACHE_ROOT,
        portable_cache_root=DEFAULT_PORTABLE_CACHE_ROOT,
    )
    return build_financial_cost_outputs(
        lines=lines,
        snapshots=snapshots,
        config=CostRunConfig(
            start_date=start_date,
            end_date=end_date,
            snapshot_date=snapshot_date,
            cdi_aa=float(cdi_aa),
            cdi_source=cdi_source,
            cash_yield_cdi_factor=float(cash_yield_factor),
        ),
    )


def _render_headline(outputs: FinancialCostOutputs) -> None:
    summary = outputs.summary_df
    recommended = _summary_row(summary, "2_programado_bruto_com_amortizacao")
    net = _summary_row(summary, "3_programado_liquido_caixa_lft")
    cdi_aa = float(recommended["cdi_aa"])
    implied_spread = _solve_implied_spread(outputs.monthly_df, float(recommended["despesa_financeira_bruta"]), cdi_aa)
    weighted_spread = _weighted_average_spread(outputs.line_df)

    cols = st.columns(5)
    cols[0].metric("Despesa bruta", _format_money(float(recommended["despesa_financeira_bruta"])))
    cols[1].metric("Gross-up receita", _format_money(float(recommended["receita_antecipacao_gross_up_sugerida"])))
    cols[2].metric("Custo líquido", _format_money(float(net["despesa_financeira_liquida"])))
    cols[3].metric("Saldo médio", _format_money(float(recommended["saldo_base"])))
    cols[4].metric("CDI+ implícito", _format_cdi_plus(implied_spread))

    note = (
        f"CDI usado: {_format_percent(cdi_aa)} ({recommended['cdi_source']}). "
        f"Spread ponderado por saldo médio: {_format_cdi_plus(weighted_spread)}."
    )
    st.markdown(f"<div class='cloudwalk-note'>{note}</div>", unsafe_allow_html=True)


def _render_summary(outputs: FinancialCostOutputs) -> None:
    display = outputs.summary_df.copy()
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
    st.dataframe(display, hide_index=True, width="stretch")


def _render_lines(outputs: FinancialCostOutputs) -> None:
    frame = outputs.line_df.copy()
    active = frame[frame["included_in_cost"].fillna(False).astype(bool)].copy()
    if active.empty:
        st.info("Nenhuma linha incluída no custo.")
        return

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

    cols = [
        "fund_name",
        "classe",
        "class_macro",
        "issue_date",
        "spread_cdi_plus_aa",
        "saldo_snapshot",
        "saldo_inicio_periodo",
        "saldo_medio_programado",
        "custo_programado_bruto",
        "amortizacao_no_periodo",
        "spread_source",
    ]
    st.dataframe(_format_line_table(active[cols]), hide_index=True, width="stretch")


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
        .mark_line(point=True, color="#d35714")
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
    st.dataframe(_format_line_table(monthly), hide_index=True, width="stretch")


def _render_cash(outputs: FinancialCostOutputs) -> None:
    frame = outputs.ime_snapshot_df.copy()
    if frame.empty:
        st.info("Sem snapshots IME para caixa/LFT.")
        return
    total_cash = pd.to_numeric(frame["cash_like_caixa_lft"], errors="coerce").fillna(0.0).sum()
    total_yield = pd.to_numeric(frame["rendimento_estimado_caixa_lft"], errors="coerce").fillna(0.0).sum()
    cols = st.columns(2)
    cols[0].metric("Base caixa/LFT", _format_money(total_cash))
    cols[1].metric("Rendimento estimado", _format_money(total_yield))
    st.dataframe(_format_line_table(frame), hide_index=True, width="stretch")


def _render_assumptions(outputs: FinancialCostOutputs, controls: dict[str, object]) -> None:
    recommended = _summary_row(outputs.summary_df, "2_programado_bruto_com_amortizacao")
    st.markdown("<div class='cloudwalk-section-title'>Premissas da rodada</div>", unsafe_allow_html=True)
    assumptions = pd.DataFrame(
        [
            ("Período", f"{recommended['periodo_inicio']} a {recommended['periodo_fim']}"),
            ("Snapshot", str(recommended["snapshot_date"])),
            ("CDI", f"{_format_percent(float(recommended['cdi_aa']))} - {recommended['cdi_source']}"),
            ("Fator caixa/LFT", f"{float(recommended['cash_yield_cdi_factor']):.2f}x CDI"),
            ("CSV emissões", str(DEFAULT_EMISSIONS_CSV.relative_to(ROOT))),
            ("Config spreads", str(DEFAULT_CONFIG_JSON.relative_to(ROOT))),
            ("Cache IME local", str(DEFAULT_RUNTIME_CACHE_ROOT.relative_to(ROOT))),
            ("Cache IME GitHub", str(DEFAULT_PORTABLE_CACHE_ROOT.relative_to(ROOT))),
        ],
        columns=["Premissa", "Valor"],
    )
    st.dataframe(assumptions, hide_index=True, width="stretch")

    if outputs.missing_inputs_df.empty:
        st.success("Todas as linhas ativas incluídas têm spread CDI+ definido ou parseável.")
    else:
        st.warning("Há linhas ativas sem spread CDI+.")
        st.dataframe(outputs.missing_inputs_df, hide_index=True, width="stretch")

    with st.expander("Metodologia"):
        st.markdown(outputs.methodology_md)

    st.download_button(
        "Baixar pacote CSV/MD",
        data=_zip_outputs(outputs),
        file_name=f"cloudwalk_financial_cost_{controls['start_date']}_{controls['end_date']}.zip",
        mime="application/zip",
        width="stretch",
    )


def _summary_row(summary: pd.DataFrame, estimativa: str) -> pd.Series:
    return summary.loc[summary["estimativa"].eq(estimativa)].iloc[0]


def _parse_overrides(raw: str) -> dict[str, float]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON de overrides inválido: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Overrides adicionais precisam ser um objeto JSON.")
    parsed: dict[str, float] = {}
    for key, value in payload.items():
        try:
            parsed[str(key)] = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Spread inválido para {key!r}: use decimal, ex. 0.012 para CDI+1,20%.") from exc
    return parsed


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
    frame = frame[(frame["saldo_base"] > 0.0) & (frame["dias_uteis"] > 0.0)]
    if frame.empty:
        return None

    def cost_for_spread(spread: float) -> float:
        rate = max(cdi_aa + spread, -0.999999)
        return float((frame["saldo_base"] * ((1.0 + rate) ** (frame["dias_uteis"] / 252.0) - 1.0)).sum())

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
