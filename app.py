from __future__ import annotations

import io
from typing import Dict

import numpy as np
import pandas as pd
import streamlit as st

from src.excel_reader import infer_curve, load_excel_inputs
from src.model import ModelInputs, run_model


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


st.set_page_config(page_title="FIDC Amortização", layout="wide")

st.title("Modelo de Amortização FIDC")

with st.sidebar:
    st.header("Premissas")
    excel_file = st.file_uploader("Carregar planilha Excel", type=["xlsx", "xls", "xlsm"])

    premissas = {}
    curve = None
    holiday_calendar = None
    outputs = []

    if excel_file:
        try:
            with st.spinner("Lendo planilha..."):
                excel_inputs = load_excel_inputs(excel_file)
                premissas = excel_inputs.premissas
                outputs = excel_inputs.outputs
                curve = infer_curve(excel_inputs.bmf)
                holiday_calendar = excel_inputs.holidays

            # Show what was found
            found_items = []
            if excel_inputs.fluxo_base is not None:
                found_items.append("Fluxo Base")
            if excel_inputs.bmf is not None:
                found_items.append("BMF/Curva")
            if excel_inputs.holidays is not None:
                found_items.append("Feriados")
            if excel_inputs.vencimentario is not None:
                found_items.append("Vencimentário")

            if found_items:
                st.success(f"Abas encontradas: {', '.join(found_items)}")

            if premissas:
                st.caption("Premissas identificadas na planilha")
                st.json(premissas)

            if outputs:
                st.caption("Outputs listados na planilha")
                st.write(outputs)
        except Exception as e:
            st.error(f"Erro ao ler planilha: {e}")

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

inputs = ModelInputs(
    volume=volume,
    start_date=pd.Timestamp(start_date),
    periods=int(periods),
    frequency_months=int(frequency_months),
    asset_rate_aa=float(asset_rate_aa),
    admin_rate_aa=float(admin_rate_aa),
    admin_min_period=float(admin_min_period),
    loss_rate_aa=float(loss_rate_aa),
    senior_share=float(senior_share),
    mezz_share=float(mezz_share),
    junior_share=float(junior_share),
    senior_rate_aa=float(senior_rate_aa),
    mezz_rate_aa=float(mezz_rate_aa),
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

csv_buffer = io.StringIO()
results.timeline.to_csv(csv_buffer, index=False)

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    results.timeline.to_excel(writer, index=False, sheet_name="timeline")
    kpi_df = pd.DataFrame([results.kpis])
    kpi_df.to_excel(writer, index=False, sheet_name="kpis")

st.download_button("Exportar CSV", data=csv_buffer.getvalue(), file_name="fidc_timeline.csv", mime="text/csv")
st.download_button(
    "Exportar Excel",
    data=excel_buffer.getvalue(),
    file_name="fidc_resultados.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
