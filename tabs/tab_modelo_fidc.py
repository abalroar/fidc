from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from data_loader import load_model_inputs
from services.fidc_model import Premissas, build_flow, build_kpis


@st.cache_data
def _load_inputs(path: str):
    return load_model_inputs(path)


def _format_percent(value: float | None) -> str:
    if value is None:
        return "N/D"
    return f"{value:.2%}"


def _format_brl(value: float | None) -> str:
    if value is None:
        return "N/D"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _build_dataframe(results) -> pd.DataFrame:
    frame = pd.DataFrame([result.__dict__ for result in results])
    frame["data"] = pd.to_datetime(frame["data"])
    return frame


def _build_export_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    export = frame.copy()
    export["data"] = export["data"].dt.strftime("%d/%m/%Y")
    return export.rename(
        columns={
            "indice": "Indice",
            "data": "Data",
            "dc": "Dias corridos",
            "du": "Dias uteis",
            "delta_dc": "Delta dias corridos",
            "delta_du": "Delta dias uteis",
            "pre_di": "Pre DI",
            "taxa_senior": "Taxa senior",
            "fra_senior": "FRA senior",
            "taxa_mezz": "Taxa mezz",
            "fra_mezz": "FRA mezz",
            "carteira": "Carteira de recebiveis (saldo economico)",
            "fluxo_carteira": "Fluxo economico da carteira",
            "pl_fidc": "PL economico do veiculo",
            "custos_adm": "Custos administrativos",
            "inadimplencia_despesa": "Perda economica por inadimplencia",
            "principal_senior": "Principal senior",
            "juros_senior": "Juros senior",
            "pmt_senior": "PMT senior",
            "vp_pmt_senior": "VP PMT senior",
            "pl_senior": "PL senior",
            "fluxo_remanescente": "Fluxo remanescente apos senior",
            "principal_mezz": "Principal mezz",
            "juros_mezz": "Juros mezz",
            "pmt_mezz": "PMT mezz",
            "pl_mezz": "PL mezz",
            "fluxo_remanescente_mezz": "Fluxo remanescente apos mezz",
            "principal_sub_jr": "Principal subordinada",
            "juros_sub_jr": "Juros subordinada",
            "pmt_sub_jr": "PMT subordinada",
            "pl_sub_jr": "Saldo residual junior economico",
            "subordinacao_pct": "Subordinacao economica",
            "pl_sub_jr_modelo": "Saldo junior exibido (workbook)",
            "subordinacao_pct_modelo": "Subordinacao exibida (workbook)",
        }
    )


def _build_kpi_export_dataframe(kpis) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Indicador": "Retorno anualizado da classe senior (economico)",
                "Valor": kpis.xirr_senior,
                "Definicao": "Taxa interna anual de retorno dos pagamentos projetados da classe senior.",
            },
            {
                "Indicador": "Retorno anualizado da classe mezz (economico)",
                "Valor": kpis.xirr_mezz,
                "Definicao": "Taxa interna anual de retorno dos pagamentos projetados da classe mezzanino.",
            },
            {
                "Indicador": "Retorno anualizado da junior residual (economico)",
                "Valor": kpis.xirr_sub_jr,
                "Definicao": "Nao aplicavel quando a serie de pagamentos da subordinada nao tem sinais validos para calcular retorno interno.",
            },
            {
                "Indicador": "Duration economica da senior",
                "Valor": kpis.duration_senior_anos,
                "Definicao": "Prazo medio ponderado, em anos, dos pagamentos descontados da classe senior.",
            },
            {
                "Indicador": "Pre DI equivalente na duration",
                "Valor": kpis.pre_di_duration,
                "Definicao": "Taxa Pre DI da curva interpolada no ponto correspondente ao duration da senior.",
            },
            {
                "Indicador": "Excesso de retorno da junior sobre o Pre DI",
                "Valor": kpis.taxa_retorno_sub_jr_cdi,
                "Definicao": "Excesso de retorno da subordinada sobre a taxa Pre DI no duration, quando a serie permite o calculo.",
            },
        ]
    )


def render_tab_modelo_fidc() -> None:
    inputs = _load_inputs("model_data.json")

    st.subheader("Modelo FIDC — Simulacao economica")
    st.caption(
        "Replica o motor economico do arquivo Modelo_Publico (.xlsm) como benchmark funcional: calendario util brasileiro, "
        "curva Pre DI por dias uteis, waterfall senior/mezz/junior e fluxo economico da carteira. Esta aba nao usa IME."
    )

    left, right = st.columns([1.2, 0.8])
    with left:
        with st.form("modelo-fidc-premissas"):
            premissas = Premissas(
                volume=st.number_input("Volume", value=inputs.premissas.get("Volume", 1_000_000.0), step=10000.0),
                tx_cessao_am=st.number_input(
                    "Tx Cessao (%am)",
                    value=inputs.premissas.get("Tx Cessão (%am)", 0.1),
                    format="%.6f",
                ),
                tx_cessao_cdi_aa=inputs.premissas.get("Tx Cessão (CDI+ %aa)"),
                custo_adm_aa=st.number_input(
                    "Custo Adm/Gestao (a.a.)",
                    value=inputs.premissas.get("Custo Adm/Gestão (a.a.)", 0.0035),
                    format="%.6f",
                ),
                custo_min=st.number_input(
                    "Custo Adm/Gestao (min)",
                    value=inputs.premissas.get("Custo Adm/Gestão (mín)", 20000.0),
                    step=1000.0,
                ),
                inadimplencia=st.number_input(
                    "Inadimplencia",
                    value=inputs.premissas.get("Inadimplência", 0.1),
                    format="%.6f",
                ),
                proporcao_senior=st.slider(
                    "Proporcao PL Sr.",
                    0.0,
                    1.0,
                    value=inputs.premissas.get("Proporção PL Sr.", 0.9),
                ),
                taxa_senior=st.number_input(
                    "Taxa Senior",
                    value=inputs.premissas.get("Taxa Sênior", 0.02),
                    format="%.6f",
                ),
                proporcao_mezz=st.slider(
                    "Proporcao PL Mezz",
                    0.0,
                    1.0,
                    value=inputs.premissas.get("Proporção PL Mezz", 0.05),
                ),
                taxa_mezz=st.number_input(
                    "Taxa Mezz",
                    value=inputs.premissas.get("Taxa Mezz", 0.05),
                    format="%.6f",
                ),
            )
            submitted = st.form_submit_button("Rodar simulacao", width="stretch")

    with right:
        st.info(
            "Contrato ativo do .xlsm: a planilha usa apenas `Tx Cessao (%am)` para fluxo da carteira. "
            "`Tx Cessao (CDI+ %aa)` existe no arquivo e no JSON historico, mas nao entra nas formulas ativas."
        )
        st.markdown(
            "\n".join(
                [
                    "- A verdade temporal do modelo esta nas datas, nos dias corridos e nos dias uteis; o indice do periodo e apenas auxiliar.",
                    "- O calendario util usa base brasileira de 252 dias com lista explicita de feriados.",
                    "- Senior e mezz recebem juros pela curva Pre DI interpolada mais spread da classe.",
                    "- O retorno anualizado mostrado nos cards e a taxa interna anual dos pagamentos projetados da classe.",
                    "- A junior fica como residual economico do veiculo; o workbook nao gera uma serie valida de retorno interno para ela.",
                    "- Duration e Pre DI no duration replicam as formulas da planilha para os PMTs senior.",
                ]
            )
        )
        st.warning(
            "Nao confundir esta aba com o IME: aqui `inadimplencia` e perda economica premissada, "
            "`subordinacao` e economica/residual, e `PL` representa saldo economico do veiculo."
        )

    total_prop = premissas.proporcao_senior + premissas.proporcao_mezz
    if total_prop > 1.0:
        st.error("A soma de Senior + Mezz excede 100%. O modelo exige subordinada residual nao negativa.")
        return

    if not submitted and "modelo_fidc_periods" in st.session_state:
        results = st.session_state["modelo_fidc_periods"]
        kpis = st.session_state["modelo_fidc_kpis"]
    else:
        results = build_flow(inputs.datas, inputs.feriados, inputs.curva_du, inputs.curva_cdi, premissas)
        kpis = build_kpis(results)
        st.session_state["modelo_fidc_periods"] = results
        st.session_state["modelo_fidc_kpis"] = kpis

    if not results:
        st.info("Sem datas suficientes para montar o fluxo.")
        return

    frame = _build_dataframe(results)
    export_frame = _build_export_dataframe(frame)

    st.markdown("**KPIs**")
    cols = st.columns(6)
    cols[0].metric("Retorno anualizado Senior", _format_percent(kpis.xirr_senior))
    cols[1].metric("Retorno anualizado Mezz", _format_percent(kpis.xirr_mezz))
    cols[2].metric("Retorno anualizado Junior residual", _format_percent(kpis.xirr_sub_jr))
    cols[3].metric("Duration economica da Senior", f"{kpis.duration_senior_anos:.2f} anos" if kpis.duration_senior_anos is not None else "N/D")
    cols[4].metric("Pre DI equivalente na duration", _format_percent(kpis.pre_di_duration))
    cols[5].metric("Saldo junior inicial", _format_brl(results[0].pl_sub_jr))

    st.caption(
        "Retorno anualizado = taxa interna anual de retorno dos pagamentos projetados de cada classe. "
        "Se a serie nao tiver fluxo valido, o app mostra `N/D` em vez de inventar um numero. "
        "Esses KPIs sao economicos e nao equivalem automaticamente aos indicadores observados no IME."
    )

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.markdown("**Saldos economicos das classes**")
        balance_df = frame[["data", "pl_senior", "pl_mezz", "pl_sub_jr_modelo"]].set_index("data")
        st.line_chart(
            balance_df.rename(
                columns={"pl_senior": "Senior", "pl_mezz": "Mezz", "pl_sub_jr_modelo": "Junior (exibicao workbook)"}
            )
        )
    with chart_right:
        st.markdown("**Curva Pre DI e subordinacao economica**")
        curve_df = frame[["data", "pre_di", "taxa_senior", "subordinacao_pct_modelo"]].set_index("data")
        st.line_chart(
            curve_df.rename(
                columns={
                    "pre_di": "Pre DI",
                    "taxa_senior": "Taxa Senior",
                    "subordinacao_pct_modelo": "Subordinacao economica",
                }
            )
        )

    st.markdown("**Memoria de calculo**")
    memory_df = pd.DataFrame(
        [
            {
                "Indicador": "Fluxo economico da carteira",
                "Formula": "carteira * ((1 + tx_cessao_am) ^ (delta_du / 21) - 1)",
                "Observacao": "Replica Qx no Fluxo Base. A taxa de cessao mensal e o driver efetivo da remuneracao da carteira.",
            },
            {
                "Indicador": "Custo adm/gestao",
                "Formula": "max(carteira * custo_adm_aa / 12, custo_min)",
                "Observacao": "Maior entre percentual anualizado sobre o saldo e o piso mensal.",
            },
            {
                "Indicador": "Perda economica por inadimplencia",
                "Formula": "carteira * (inadimplencia * delta_dc / 100)",
                "Observacao": "Despesa deterministica por passagem do tempo; nao equivale ao aging regulatorio do IME.",
            },
            {
                "Indicador": "Juros Senior/Mezz",
                "Formula": "pl_classe * ((1 + FRA) ^ (delta_du / 252) - 1)",
                "Observacao": "FRA derivado da curva Pre DI interpolada.",
            },
            {
                "Indicador": "Junior residual / subordinacao economica",
                "Formula": "Residual economico = PL economico do veiculo - PL Senior - PL Mezz; serie exibida replica o deslocamento da planilha",
                "Observacao": "O grafico usa a serie exibida do workbook; a tabela exporta a visao economica e a visao exibida.",
            },
        ]
    )
    st.dataframe(memory_df, width="stretch", hide_index=True)

    with st.expander("O que este modelo e o que ele nao e", expanded=False):
        st.markdown(
            "\n".join(
                [
                    "- Esta aba e uma **simulacao economica** de estrutura, waterfall e curva; nao e leitura contabil/regulatoria do IME.",
                    "- `PL economico do veiculo` nao equivale automaticamente ao PL contabil reportado no Informe Mensal da CVM.",
                    "- `Inadimplencia` aqui e perda economica premissada; nao e `aging`, `over 30` ou saldo vencido observado do IME.",
                    "- `Subordinacao economica` aqui e residual da junior sobre o PL economico; nao substitui a subordinação reportada no IME nem covenants contratuais.",
                    "- `Duration economica da senior` aqui e cash flow duration por VP em DU/252; nao e o prazo medio proxy da carteira usado no painel IME.",
                ]
            )
        )

    st.markdown("**Timeline detalhada**")
    st.dataframe(export_frame, width="stretch")

    csv = export_frame.to_csv(index=False).encode("utf-8")
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_frame.to_excel(writer, index=False, sheet_name="timeline")
        _build_kpi_export_dataframe(kpis).to_excel(writer, index=False, sheet_name="kpis")
    download_left, download_right = st.columns(2)
    download_left.download_button(
        "Baixar CSV",
        data=csv,
        file_name="modelo_fidc_timeline.csv",
        mime="text/csv",
        width="stretch",
    )
    download_right.download_button(
        "Baixar Excel",
        data=output.getvalue(),
        file_name="modelo_fidc_resultados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
