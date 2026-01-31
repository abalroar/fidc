from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st

from data_loader import load_model_inputs
from model import Premissas, build_flow, build_kpis


st.set_page_config(page_title="Modelo FIDC", page_icon="📊", layout="wide")

st.title("Modelo FIDC (Streamlit)")
st.caption("Reimplementação do fluxo econômico sem VBA, com inputs interativos.")


@st.cache_data
def load_inputs(path: str):
    return load_model_inputs(path)


inputs = load_inputs("model_data.json")

with st.sidebar:
    st.header("Premissas")
    volume = st.number_input("Volume", value=inputs.premissas.get("Volume", 1_000_000.0), step=10000.0)
    tx_cessao_am = st.number_input("Tx Cessão (%am)", value=inputs.premissas.get("Tx Cessão (%am)", 0.1))
    tx_cessao_cdi = st.number_input("Tx Cessão (CDI+ %aa)", value=inputs.premissas.get("Tx Cessão (CDI+ %aa)", 0.1))
    custo_adm = st.number_input("Custo Adm/Gestão (a.a.)", value=inputs.premissas.get("Custo Adm/Gestão (a.a.)", 0.0035))
    custo_min = st.number_input("Custo Adm/Gestão (mín)", value=inputs.premissas.get("Custo Adm/Gestão (mín)", 20000.0))
    inadimplencia = st.number_input("Inadimplência", value=inputs.premissas.get("Inadimplência", 0.1))
    prop_senior = st.slider("Proporção PL Sr.", 0.0, 1.0, value=inputs.premissas.get("Proporção PL Sr.", 0.9))
    taxa_senior = st.number_input("Taxa Sênior", value=inputs.premissas.get("Taxa Sênior", 0.02))
    prop_mezz = st.slider("Proporção PL Mezz", 0.0, 1.0, value=inputs.premissas.get("Proporção PL Mezz", 0.05))
    taxa_mezz = st.number_input("Taxa Mezz", value=inputs.premissas.get("Taxa Mezz", 0.05))

    total_prop = prop_senior + prop_mezz
    if total_prop > 1.0:
        st.warning("A soma das proporções Sr + Mezz excede 100%. Ajuste para continuar.")

    divider = getattr(st, "divider", None)
    if callable(divider):
        divider()
    else:
        st.markdown("---")
    st.caption("Dados base")
    if st.button("Recarregar model_data.json"):
        load_inputs.clear()
        inputs = load_inputs("model_data.json")


premissas = Premissas(
    volume=volume,
    tx_cessao_am=tx_cessao_am,
    tx_cessao_cdi_aa=tx_cessao_cdi,
    custo_adm_aa=custo_adm,
    custo_min=custo_min,
    inadimplencia=inadimplencia,
    proporcao_senior=prop_senior,
    taxa_senior=taxa_senior,
    proporcao_mezz=prop_mezz,
    taxa_mezz=taxa_mezz,
)

if total_prop <= 1.0:
    results = build_flow(inputs.datas, inputs.feriados, inputs.curva_du, inputs.curva_cdi, premissas)
    kpis = build_kpis(results)
else:
    results = []
    kpis = {}

if results:
    df = pd.DataFrame([r.__dict__ for r in results])
    df["data"] = pd.to_datetime(df["data"])
    df["sub_jr"] = df["pl_sub_jr"]

    st.subheader("KPIs")
    cols = st.columns(3)
    cols[0].metric("XIRR Sênior", f"{kpis.get('xirr_senior', 0.0):.2%}")
    cols[1].metric("XIRR Mezz", f"{kpis.get('xirr_mezz', 0.0):.2%}")
    cols[2].metric("XIRR Sub Jr", f"{kpis.get('xirr_sub_jr', 0.0):.2%}")

    st.subheader("Saldos por classe")
    balance_df = df[["data", "pl_senior", "pl_mezz", "pl_sub_jr"]].set_index("data")
    st.line_chart(balance_df.rename(columns={"pl_senior": "Senior", "pl_mezz": "Mezz", "pl_sub_jr": "Sub Jr"}))

    st.subheader("Fluxos por período")
    fluxo_df = df[["data", "pmt_senior", "pmt_mezz", "pmt_sub_jr"]].set_index("data")
    st.area_chart(fluxo_df.rename(columns={"pmt_senior": "Senior", "pmt_mezz": "Mezz", "pmt_sub_jr": "Sub Jr"}))

    st.subheader("Timeline detalhada")
    st.dataframe(df)

    st.subheader("Exportar resultados")
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Baixar CSV", data=csv, file_name="timeline.csv", mime="text/csv")

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="timeline")
        pd.DataFrame([kpis]).to_excel(writer, index=False, sheet_name="kpis")
    st.download_button(
        "Baixar Excel",
        data=output.getvalue(),
        file_name="resultados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Ajuste as premissas para gerar resultados.")
