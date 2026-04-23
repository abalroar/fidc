from __future__ import annotations

from html import escape
from io import BytesIO

import pandas as pd
import streamlit as st

from data_loader import load_model_inputs
from services.fidc_model import Premissas, build_flow, build_kpis


_MODEL_CSS = """
<style>
.fidc-model-header {
    border-bottom: 1px solid #dde3ea;
    margin: 0.15rem 0 1.05rem 0;
    padding-bottom: 1rem;
}

.fidc-model-kicker {
    color: #ff5a00;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    line-height: 1.2;
    margin-bottom: 0.35rem;
    text-transform: uppercase;
}

.fidc-model-title {
    color: #283241;
    font-size: 1.65rem;
    font-weight: 700;
    letter-spacing: 0;
    line-height: 1.16;
    margin: 0;
}

.fidc-model-copy {
    color: #6f7a87;
    font-size: 0.96rem;
    line-height: 1.58;
    margin-top: 0.55rem;
    max-width: 58rem;
}

.fidc-model-section-title {
    color: #283241;
    font-size: 1.02rem;
    font-weight: 700;
    margin: 1.15rem 0 0.55rem 0;
}

.fidc-model-kpi-grid {
    display: grid;
    gap: 0.65rem;
    grid-template-columns: repeat(auto-fit, minmax(168px, 1fr));
    margin: 0.4rem 0 0.55rem 0;
}

.fidc-model-kpi-card {
    background: #ffffff;
    border: 1px solid #dde3ea;
    border-radius: 8px;
    border-top: 3px solid #1f77b4;
    min-height: 6.1rem;
    padding: 0.75rem 0.8rem;
}

.fidc-model-kpi-card:nth-child(2n) {
    border-top-color: #ff5a00;
}

.fidc-model-kpi-label {
    color: #6f7a87;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    line-height: 1.25;
    margin-bottom: 0.35rem;
    text-transform: uppercase;
}

.fidc-model-kpi-value {
    color: #202a36;
    font-size: 1.18rem;
    font-weight: 700;
    line-height: 1.18;
}

.fidc-model-kpi-context {
    color: #6f7a87;
    font-size: 0.78rem;
    line-height: 1.35;
    margin-top: 0.35rem;
}

@media (max-width: 760px) {
    .fidc-model-title {
        font-size: 1.4rem;
    }
}
</style>
"""


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
            "indice": "Índice",
            "data": "Data",
            "dc": "Dias corridos",
            "du": "Dias úteis",
            "delta_dc": "Delta dias corridos",
            "delta_du": "Delta dias úteis",
            "pre_di": "Pre DI",
            "taxa_senior": "Taxa sênior",
            "fra_senior": "FRA sênior",
            "taxa_mezz": "Taxa mezz",
            "fra_mezz": "FRA mezz",
            "carteira": "Carteira de recebíveis (saldo econômico)",
            "fluxo_carteira": "Fluxo econômico da carteira",
            "pl_fidc": "PL econômico do veículo",
            "custos_adm": "Custos administrativos",
            "inadimplencia_despesa": "Perda econômica por inadimplência",
            "principal_senior": "Principal sênior",
            "juros_senior": "Juros sênior",
            "pmt_senior": "PMT sênior",
            "vp_pmt_senior": "VP PMT sênior",
            "pl_senior": "PL sênior",
            "fluxo_remanescente": "Fluxo remanescente após sênior",
            "principal_mezz": "Principal mezz",
            "juros_mezz": "Juros mezz",
            "pmt_mezz": "PMT mezz",
            "pl_mezz": "PL mezz",
            "fluxo_remanescente_mezz": "Fluxo remanescente após mezz",
            "principal_sub_jr": "Principal subordinada",
            "juros_sub_jr": "Juros subordinada",
            "pmt_sub_jr": "PMT subordinada",
            "pl_sub_jr": "Saldo residual júnior econômico",
            "subordinacao_pct": "Subordinação econômica",
            "pl_sub_jr_modelo": "Saldo júnior exibido (workbook)",
            "subordinacao_pct_modelo": "Subordinação exibida (workbook)",
        }
    )


def _build_kpi_export_dataframe(kpis) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Indicador": "Retorno anualizado da classe sênior (econômico)",
                "Valor": kpis.xirr_senior,
                "Definicao": "Taxa interna anual de retorno dos pagamentos projetados da classe sênior.",
            },
            {
                "Indicador": "Retorno anualizado da classe mezz (econômico)",
                "Valor": kpis.xirr_mezz,
                "Definicao": "Taxa interna anual de retorno dos pagamentos projetados da classe mezzanino.",
            },
            {
                "Indicador": "Retorno anualizado da júnior residual (econômico)",
                "Valor": kpis.xirr_sub_jr,
                "Definicao": "Não aplicável quando a série de pagamentos da subordinada não tem sinais válidos para calcular retorno interno.",
            },
            {
                "Indicador": "Duration econômica da sênior",
                "Valor": kpis.duration_senior_anos,
                "Definicao": "Prazo médio ponderado, em anos, dos pagamentos descontados da classe sênior.",
            },
            {
                "Indicador": "Pre DI equivalente na duration",
                "Valor": kpis.pre_di_duration,
                "Definicao": "Taxa Pre DI da curva interpolada no ponto correspondente ao duration da sênior.",
            },
            {
                "Indicador": "Excesso de retorno da júnior sobre o Pre DI",
                "Valor": kpis.taxa_retorno_sub_jr_cdi,
                "Definicao": "Excesso de retorno da subordinada sobre a taxa Pre DI no duration, quando a série permite o cálculo.",
            },
        ]
    )


def _render_model_header() -> None:
    st.markdown(_MODEL_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="fidc-model-header">
          <div class="fidc-model-kicker">Simulação econômica</div>
          <h2 class="fidc-model-title">Modelo FIDC</h2>
          <div class="fidc-model-copy">
            Replica o motor econômico do arquivo Modelo_Publico (.xlsm) como benchmark funcional:
            calendário útil brasileiro, curva Pre DI por dias úteis, waterfall sênior/mezz/júnior
            e fluxo econômico da carteira. Esta aba não usa IME.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_model_kpi_cards(kpis, results) -> None:
    cards = [
        ("Retorno anualizado", _format_percent(kpis.xirr_senior), "Classe sênior"),
        ("Retorno anualizado", _format_percent(kpis.xirr_mezz), "Classe mezzanino"),
        ("Retorno anualizado", _format_percent(kpis.xirr_sub_jr), "Júnior residual"),
        (
            "Duration econômica",
            f"{kpis.duration_senior_anos:.2f} anos" if kpis.duration_senior_anos is not None else "N/D",
            "Classe sênior",
        ),
        ("Pre DI na duration", _format_percent(kpis.pre_di_duration), "Curva interpolada"),
        ("Saldo júnior inicial", _format_brl(results[0].pl_sub_jr), "Residual econômico"),
    ]
    cards_html = "".join(
        (
            '<div class="fidc-model-kpi-card">'
            f'<div class="fidc-model-kpi-label">{escape(label)}</div>'
            f'<div class="fidc-model-kpi-value">{escape(value)}</div>'
            f'<div class="fidc-model-kpi-context">{escape(context)}</div>'
            "</div>"
        )
        for label, value, context in cards
    )
    st.markdown(f'<div class="fidc-model-kpi-grid">{cards_html}</div>', unsafe_allow_html=True)


def render_tab_modelo_fidc() -> None:
    inputs = _load_inputs("model_data.json")

    _render_model_header()

    left, right = st.columns([1.2, 0.8])
    with left:
        with st.form("modelo-fidc-premissas"):
            premissas = Premissas(
                volume=st.number_input("Volume", value=inputs.premissas.get("Volume", 1_000_000.0), step=10000.0),
                tx_cessao_am=st.number_input(
                    "Tx Cessão (% a.m.)",
                    value=inputs.premissas.get("Tx Cessão (%am)", 0.1),
                    format="%.6f",
                ),
                tx_cessao_cdi_aa=inputs.premissas.get("Tx Cessão (CDI+ %aa)"),
                custo_adm_aa=st.number_input(
                    "Custo Adm/Gestão (a.a.)",
                    value=inputs.premissas.get("Custo Adm/Gestão (a.a.)", 0.0035),
                    format="%.6f",
                ),
                custo_min=st.number_input(
                    "Custo Adm/Gestão (mín.)",
                    value=inputs.premissas.get("Custo Adm/Gestão (mín)", 20000.0),
                    step=1000.0,
                ),
                inadimplencia=st.number_input(
                    "Inadimplência",
                    value=inputs.premissas.get("Inadimplência", 0.1),
                    format="%.6f",
                ),
                proporcao_senior=st.slider(
                    "Proporção PL sênior",
                    0.0,
                    1.0,
                    value=inputs.premissas.get("Proporção PL Sr.", 0.9),
                ),
                taxa_senior=st.number_input(
                    "Taxa sênior",
                    value=inputs.premissas.get("Taxa Sênior", 0.02),
                    format="%.6f",
                ),
                proporcao_mezz=st.slider(
                    "Proporção PL mezz",
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
            submitted = st.form_submit_button("Rodar simulação", width="stretch")

    with right:
        st.info(
            "Contrato ativo do .xlsm: a planilha usa apenas `Tx Cessão (%am)` para fluxo da carteira. "
            "`Tx Cessão (CDI+ %aa)` existe no arquivo e no JSON histórico, mas não entra nas fórmulas ativas."
        )
        st.markdown(
            "\n".join(
                [
                    "- A verdade temporal do modelo está nas datas, nos dias corridos e nos dias úteis; o índice do período é apenas auxiliar.",
                    "- O calendário útil usa base brasileira de 252 dias com lista explícita de feriados.",
                    "- Sênior e mezz recebem juros pela curva Pre DI interpolada mais spread da classe.",
                    "- O retorno anualizado mostrado nos cards é a taxa interna anual dos pagamentos projetados da classe.",
                    "- A júnior fica como residual econômico do veículo; o workbook não gera uma série válida de retorno interno para ela.",
                    "- Duration e Pre DI no duration replicam as fórmulas da planilha para os PMTs sênior.",
                ]
            )
        )
        st.warning(
            "Não confundir esta aba com o IME: aqui `inadimplência` é perda econômica premissada, "
            "`subordinação` é econômica/residual, e `PL` representa saldo econômico do veículo."
        )

    total_prop = premissas.proporcao_senior + premissas.proporcao_mezz
    if total_prop > 1.0:
        st.error("A soma de sênior + mezz excede 100%. O modelo exige subordinada residual não negativa.")
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

    st.markdown('<div class="fidc-model-section-title">KPIs de saída</div>', unsafe_allow_html=True)
    _render_model_kpi_cards(kpis, results)

    st.caption(
        "Retorno anualizado = taxa interna anual de retorno dos pagamentos projetados de cada classe. "
        "Se a série não tiver fluxo válido, o app mostra `N/D` em vez de inventar um número. "
        "Esses KPIs são econômicos e não equivalem automaticamente aos indicadores observados no IME."
    )

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.markdown('<div class="fidc-model-section-title">Saldos econômicos das classes</div>', unsafe_allow_html=True)
        balance_df = frame[["data", "pl_senior", "pl_mezz", "pl_sub_jr_modelo"]].set_index("data")
        st.line_chart(
            balance_df.rename(
                columns={"pl_senior": "Sênior", "pl_mezz": "Mezz", "pl_sub_jr_modelo": "Júnior (exibição workbook)"}
            )
        )
    with chart_right:
        st.markdown('<div class="fidc-model-section-title">Curva Pre DI e subordinação econômica</div>', unsafe_allow_html=True)
        curve_df = frame[["data", "pre_di", "taxa_senior", "subordinacao_pct_modelo"]].set_index("data")
        st.line_chart(
            curve_df.rename(
                columns={
                    "pre_di": "Pre DI",
                    "taxa_senior": "Taxa sênior",
                    "subordinacao_pct_modelo": "Subordinação econômica",
                }
            )
        )

    st.markdown('<div class="fidc-model-section-title">Memória de cálculo</div>', unsafe_allow_html=True)
    memory_df = pd.DataFrame(
        [
            {
                "Indicador": "Fluxo econômico da carteira",
                "Fórmula": "carteira * ((1 + tx_cessao_am) ^ (delta_du / 21) - 1)",
                "Observação": "Replica Qx no Fluxo Base. A taxa de cessão mensal é o driver efetivo da remuneração da carteira.",
            },
            {
                "Indicador": "Custo adm/gestão",
                "Fórmula": "max(carteira * custo_adm_aa / 12, custo_min)",
                "Observação": "Maior entre percentual anualizado sobre o saldo e o piso mensal.",
            },
            {
                "Indicador": "Perda econômica por inadimplência",
                "Fórmula": "carteira * (inadimplencia * delta_dc / 100)",
                "Observação": "Despesa determinística por passagem do tempo; não equivale ao aging regulatório do IME.",
            },
            {
                "Indicador": "Juros sênior/mezz",
                "Fórmula": "pl_classe * ((1 + FRA) ^ (delta_du / 252) - 1)",
                "Observação": "FRA derivado da curva Pre DI interpolada.",
            },
            {
                "Indicador": "Júnior residual / subordinação econômica",
                "Fórmula": "Residual econômico = PL econômico do veículo - PL sênior - PL mezz; série exibida replica o deslocamento da planilha",
                "Observação": "O gráfico usa a série exibida do workbook; a tabela exporta a visão econômica e a visão exibida.",
            },
        ]
    )
    st.dataframe(memory_df, width="stretch", hide_index=True)

    with st.expander("O que este modelo é e o que ele não é", expanded=False):
        st.markdown(
            "\n".join(
                [
                    "- Esta aba é uma **simulação econômica** de estrutura, waterfall e curva; não é leitura contábil/regulatória do IME.",
                    "- `PL econômico do veículo` não equivale automaticamente ao PL contábil reportado no Informe Mensal da CVM.",
                    "- `Inadimplência` aqui é perda econômica premissada; não é `aging`, `over 30` ou saldo vencido observado do IME.",
                    "- `Subordinação econômica` aqui é residual da júnior sobre o PL econômico; não substitui a subordinação reportada no IME nem covenants contratuais.",
                    "- `Duration econômica da sênior` aqui é cash flow duration por VP em DU/252; não é o prazo médio proxy da carteira usado no painel IME.",
                ]
            )
        )

    st.markdown('<div class="fidc-model-section-title">Timeline detalhada</div>', unsafe_allow_html=True)
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
