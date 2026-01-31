from __future__ import annotations

import io
from dataclasses import asdict
from typing import Dict, Optional

import numpy as np
import pandas as pd
import streamlit as st

from fidc.excel import ExcelInputs, infer_curve, load_excel_inputs
from fidc.model import ModelInputs, run_model


DEFAULTS: Dict[str, float] = {
    "volume": 100_000_000.0,
    "asset_rate_aa": 0.15,
    "admin_rate_aa": 0.02,
    "admin_min_period": 50_000.0,
    "loss_rate_aa": 0.02,
    "senior_share": 0.7,
    "mezz_share": 0.2,
    "junior_share": 0.1,
    "senior_rate_aa": 0.11,
    "mezz_rate_aa": 0.14,
    "periods": 24,
    "frequency_months": 3,
}


def _safe_float(value: object, default: float) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, float) and np.isnan(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_rate(value: object, default: float) -> float:
    rate = _safe_float(value, default)
    if rate > 1:
        return rate / 100
    return rate


def _select_frequency_index(value: object, default: int) -> int:
    options = [1, 3, 6]
    frequency = int(_safe_float(value, default))
    if frequency not in options:
        frequency = default
    return options.index(frequency)


@st.cache_data(show_spinner=False)
def _load_excel(file_bytes: bytes) -> ExcelInputs:
    return load_excel_inputs(io.BytesIO(file_bytes))


def _sidebar_premissas(excel_inputs: Optional[ExcelInputs]) -> Dict[str, object]:
    premissas = excel_inputs.premissas if excel_inputs else {}

    st.header("Premissas")
    volume = st.number_input(
        "Volume (R$)",
        min_value=0.0,
        value=_safe_float(premissas.get("Volume"), DEFAULTS["volume"]),
    )
    asset_rate_aa = st.slider(
        "Taxa da carteira (a.a.)",
        min_value=0.0,
        max_value=0.5,
        value=_normalize_rate(premissas.get("Taxa de cessão"), DEFAULTS["asset_rate_aa"]),
        step=0.005,
        format="%.3f",
    )
    admin_rate_aa = st.slider(
        "Custo de administração (a.a.)",
        min_value=0.0,
        max_value=0.1,
        value=_normalize_rate(premissas.get("Custo de administração"), DEFAULTS["admin_rate_aa"]),
        step=0.001,
        format="%.3f",
    )
    admin_min_period = st.number_input(
        "Custo mínimo por período",
        min_value=0.0,
        value=_safe_float(premissas.get("Custo mínimo"), DEFAULTS["admin_min_period"]),
    )
    loss_rate_aa = st.slider(
        "Perdas/Inadimplência (a.a.)",
        min_value=0.0,
        max_value=0.2,
        value=_normalize_rate(premissas.get("Perdas"), DEFAULTS["loss_rate_aa"]),
        step=0.001,
        format="%.3f",
    )

    st.subheader("Estrutura de cotas")
    senior_share = st.slider(
        "Senior (% do PL)",
        min_value=0.0,
        max_value=1.0,
        value=_normalize_rate(premissas.get("Senior %"), DEFAULTS["senior_share"]),
        step=0.01,
    )
    mezz_share = st.slider(
        "Mezz (% do PL)",
        min_value=0.0,
        max_value=1.0,
        value=_normalize_rate(premissas.get("Mezz %"), DEFAULTS["mezz_share"]),
        step=0.01,
    )
    junior_share = st.slider(
        "Junior (% do PL)",
        min_value=0.0,
        max_value=1.0,
        value=_normalize_rate(premissas.get("Junior %"), DEFAULTS["junior_share"]),
        step=0.01,
    )

    if abs((senior_share + mezz_share + junior_share) - 1.0) > 1e-3:
        st.warning("As porcentagens das cotas devem somar 100%.")

    senior_rate_aa = st.slider(
        "Cupom Senior (a.a.)",
        min_value=0.0,
        max_value=0.3,
        value=_normalize_rate(premissas.get("Cupom Senior"), DEFAULTS["senior_rate_aa"]),
        step=0.001,
        format="%.3f",
    )
    mezz_rate_aa = st.slider(
        "Cupom Mezz (a.a.)",
        min_value=0.0,
        max_value=0.3,
        value=_normalize_rate(premissas.get("Cupom Mezz"), DEFAULTS["mezz_rate_aa"]),
        step=0.001,
        format="%.3f",
    )

    st.subheader("Linha do tempo")
    start_date = st.date_input("Data inicial", value=pd.Timestamp.today().date())
    periods = st.number_input(
        "Número de períodos",
        min_value=1,
        value=int(_safe_float(premissas.get("Prazo"), DEFAULTS["periods"])),
    )
    frequency_months = st.selectbox(
        "Periodicidade (meses)",
        options=[1, 3, 6],
        index=_select_frequency_index(premissas.get("Periodicidade"), DEFAULTS["frequency_months"]),
    )

    return {
        "volume": volume,
        "asset_rate_aa": asset_rate_aa,
        "admin_rate_aa": admin_rate_aa,
        "admin_min_period": admin_min_period,
        "loss_rate_aa": loss_rate_aa,
        "senior_share": senior_share,
        "mezz_share": mezz_share,
        "junior_share": junior_share,
        "senior_rate_aa": senior_rate_aa,
        "mezz_rate_aa": mezz_rate_aa,
        "start_date": start_date,
        "periods": periods,
        "frequency_months": frequency_months,
    }


st.set_page_config(page_title="FIDC Amortização", layout="wide")
st.title("Modelo de Amortização FIDC")

with st.sidebar:
    excel_file = st.file_uploader("Carregar planilha Excel", type=["xlsx", "xls"])

    excel_inputs: Optional[ExcelInputs] = None
    curve = None
    holiday_calendar = None

    if excel_file:
        with st.spinner("Lendo planilha..."):
            excel_inputs = _load_excel(excel_file.getvalue())
            curve = infer_curve(excel_inputs.bmf)
            holiday_calendar = excel_inputs.holidays

        if excel_inputs.missing_sheets:
            st.warning(
                "Planilha sem abas esperadas: "
                + ", ".join(excel_inputs.missing_sheets)
                + ". O app vai rodar com defaults."
            )

        if excel_inputs.premissas:
            st.caption("Premissas identificadas na planilha")
            st.json(excel_inputs.premissas)

        if excel_inputs.outputs:
            st.caption("Outputs listados na planilha")
            st.write(excel_inputs.outputs)

    premissas_ui = _sidebar_premissas(excel_inputs)

inputs = ModelInputs(
    volume=float(premissas_ui["volume"]),
    start_date=pd.Timestamp(premissas_ui["start_date"]),
    periods=int(premissas_ui["periods"]),
    frequency_months=int(premissas_ui["frequency_months"]),
    asset_rate_aa=float(premissas_ui["asset_rate_aa"]),
    admin_rate_aa=float(premissas_ui["admin_rate_aa"]),
    admin_min_period=float(premissas_ui["admin_min_period"]),
    loss_rate_aa=float(premissas_ui["loss_rate_aa"]),
    senior_share=float(premissas_ui["senior_share"]),
    mezz_share=float(premissas_ui["mezz_share"]),
    junior_share=float(premissas_ui["junior_share"]),
    senior_rate_aa=float(premissas_ui["senior_rate_aa"]),
    mezz_rate_aa=float(premissas_ui["mezz_rate_aa"]),
    holiday_calendar=holiday_calendar,
    curve=curve,
)

results = run_model(inputs)

kpi_cols = st.columns(4)

kpi_cols[0].metric("IRR Senior (per.)", f"{results.kpis['irr_senior']:.2%}")
kpi_cols[1].metric("IRR Mezz (per.)", f"{results.kpis['irr_mezz']:.2%}")
kpi_cols[2].metric("IRR Junior (per.)", f"{results.kpis['irr_junior']:.2%}")
kpi_cols[3].metric("Equity Multiple", f"{results.kpis['equity_multiple']:.2f}x")

st.subheader("Saldos por classe")
st.line_chart(
    results.timeline.set_index("data")[["saldo_senior", "saldo_mezz", "saldo_junior", "saldo_ativo"]]
)

st.subheader("Fluxos por período")
flow_chart = results.timeline.set_index("data")[["pagamento_senior", "pagamento_mezz", "pagamento_junior"]]
st.bar_chart(flow_chart)

st.subheader("Timeline")
st.dataframe(results.timeline, use_container_width=True)

st.subheader("Exportar resultados")

csv_buffer = io.StringIO()
results.timeline.to_csv(csv_buffer, index=False)

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    results.timeline.to_excel(writer, index=False, sheet_name="timeline")
    kpi_df = pd.DataFrame([results.kpis])
    kpi_df.to_excel(writer, index=False, sheet_name="kpis")
    premissas_df = pd.DataFrame([asdict(inputs)])
    premissas_df.to_excel(writer, index=False, sheet_name="premissas")

st.download_button("Exportar CSV", data=csv_buffer.getvalue(), file_name="fidc_timeline.csv", mime="text/csv")
st.download_button(
    "Exportar Excel",
    data=excel_buffer.getvalue(),
    file_name="fidc_resultados.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
