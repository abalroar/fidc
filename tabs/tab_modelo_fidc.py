from __future__ import annotations

from html import escape
from io import BytesIO

import altair as alt
import pandas as pd
import streamlit as st

from data_loader import load_model_inputs
from services.fidc_model import (
    RATE_MODE_POST_CDI,
    RATE_MODE_PRE,
    Premissas,
    annual_252_to_monthly_rate,
    build_flow,
    build_kpis,
    monthly_to_annual_252_rate,
)


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


def _format_number_br(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "N/D"
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_percent(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "N/D"
    return f"{_format_number_br(value * 100.0, decimals)}%"


def _format_brl(value: float | None) -> str:
    if value is None:
        return "N/D"
    return f"R$ {_format_number_br(value, 2)}"


def _format_input_value(value: float, decimals: int = 2) -> str:
    return _format_number_br(value, decimals)


def _parse_br_number(value: str, *, field_name: str) -> float:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Informe {field_name}.")
    normalized = text.replace("R$", "").replace("%", "").replace(" ", "")
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError as exc:
        raise ValueError(f"Valor inválido em {field_name}: {value}") from exc


def _text_number_input(
    label: str,
    *,
    default: float,
    key: str,
    decimals: int = 2,
    help_text: str | None = None,
) -> str:
    return st.text_input(label, value=_format_input_value(default, decimals), key=key, help=help_text)


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


def _build_display_dataframe(export_frame: pd.DataFrame) -> pd.DataFrame:
    display = export_frame.copy()
    money_tokens = (
        "Carteira",
        "Fluxo",
        "PL",
        "Custos",
        "Perda",
        "Principal",
        "Juros",
        "PMT",
        "VP",
        "Saldo",
    )
    percent_tokens = ("Pre DI", "Taxa", "FRA", "Subordinação")
    for column in display.columns:
        if column in {"Índice", "Dias corridos", "Dias úteis", "Delta dias corridos", "Delta dias úteis"}:
            display[column] = display[column].map(lambda value: _format_number_br(float(value), 0) if pd.notna(value) else "N/D")
        elif any(token in column for token in percent_tokens):
            display[column] = display[column].map(lambda value: _format_percent(float(value)) if pd.notna(value) else "N/D")
        elif any(token in column for token in money_tokens):
            display[column] = display[column].map(lambda value: _format_brl(float(value)) if pd.notna(value) else "N/D")
    return display


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


def _validate_model_inputs(inputs) -> list[str]:
    errors: list[str] = []
    if not inputs.datas:
        errors.append("datas do fluxo ausentes em model_data.json")
    if not inputs.curva_du or not inputs.curva_cdi:
        errors.append("curva DI/Pre ausente em model_data.json")
    if len(inputs.curva_du) != len(inputs.curva_cdi):
        errors.append("curva_du e curva_cdi têm tamanhos diferentes")
    if not inputs.feriados:
        errors.append("lista de feriados vazia em model_data.json")
    return errors


def _rate_mode_from_label(label: str) -> str:
    return RATE_MODE_PRE if label.startswith("Pré") else RATE_MODE_POST_CDI


def _build_balance_area_frame(frame: pd.DataFrame) -> pd.DataFrame:
    chart_frame = frame[["data", "pl_senior", "pl_mezz", "pl_sub_jr", "pl_sub_jr_modelo"]].copy()
    chart_frame["pl_sub_display"] = chart_frame["pl_sub_jr_modelo"].fillna(chart_frame["pl_sub_jr"])
    long_df = chart_frame.melt(
        id_vars=["data"],
        value_vars=["pl_senior", "pl_mezz", "pl_sub_display"],
        var_name="classe",
        value_name="valor",
    )
    label_map = {
        "pl_senior": "Sênior",
        "pl_mezz": "Mezzanino",
        "pl_sub_display": "Subordinada/SUB",
    }
    long_df["classe"] = long_df["classe"].map(label_map)
    long_df["valor_milhoes"] = long_df["valor"] / 1_000_000.0
    long_df["valor_formatado"] = long_df["valor"].map(_format_brl)
    long_df["periodo"] = long_df["data"].dt.strftime("%d/%m/%Y")
    return long_df


def _build_loss_area_frame(frame: pd.DataFrame, volume: float) -> pd.DataFrame:
    chart_frame = frame[["data", "carteira", "inadimplencia_despesa", "subordinacao_pct_modelo", "subordinacao_pct"]].copy()
    chart_frame["subordinacao_display"] = chart_frame["subordinacao_pct_modelo"].fillna(chart_frame["subordinacao_pct"])
    chart_frame["inadimplencia_acumulada"] = chart_frame["inadimplencia_despesa"].fillna(0.0).cumsum()
    chart_frame["perda_periodo_pct"] = chart_frame.apply(
        lambda row: row["inadimplencia_despesa"] / row["carteira"] if row["carteira"] else None,
        axis=1,
    )
    denominator = volume if volume else 1.0
    chart_frame["perda_acumulada_pct"] = chart_frame["inadimplencia_acumulada"] / denominator
    long_df = chart_frame.melt(
        id_vars=["data"],
        value_vars=["subordinacao_display", "perda_acumulada_pct", "perda_periodo_pct"],
        var_name="serie",
        value_name="valor",
    ).dropna(subset=["valor"])
    label_map = {
        "subordinacao_display": "Subordinação econômica (SUB/PL)",
        "perda_acumulada_pct": "Inadimplência acumulada (% do volume)",
        "perda_periodo_pct": "Inadimplência do período (% da carteira)",
    }
    long_df["serie"] = long_df["serie"].map(label_map)
    long_df["valor_pct"] = long_df["valor"] * 100.0
    long_df["valor_formatado"] = long_df["valor"].map(_format_percent)
    long_df["periodo"] = long_df["data"].dt.strftime("%d/%m/%Y")
    return long_df


def _area_money_chart(chart_df: pd.DataFrame) -> alt.Chart:
    base = alt.Chart(chart_df).encode(
        x=alt.X("data:T", title="Período", axis=alt.Axis(format="%m/%Y", labelAngle=-35)),
        y=alt.Y(
            "valor_milhoes:Q",
            title="R$ milhões",
            stack="zero",
            axis=alt.Axis(labelExpr="replace(format(datum.value, '.1f'), '.', ',')"),
        ),
        color=alt.Color(
            "classe:N",
            title="Classe",
            scale=alt.Scale(range=["#2f6f9f", "#f28e2b", "#59a14f"]),
        ),
        order=alt.Order("classe:N", sort="ascending"),
        tooltip=[
            alt.Tooltip("periodo:N", title="Período"),
            alt.Tooltip("classe:N", title="Classe"),
            alt.Tooltip("valor_formatado:N", title="Valor"),
        ],
    )
    return (base.mark_area(opacity=0.72, interpolate="monotone") + base.mark_line(size=1.1, interpolate="monotone")).properties(height=320)


def _area_percent_chart(chart_df: pd.DataFrame) -> alt.Chart:
    base = alt.Chart(chart_df).encode(
        x=alt.X("data:T", title="Período", axis=alt.Axis(format="%m/%Y", labelAngle=-35)),
        y=alt.Y(
            "valor_pct:Q",
            title="%",
            axis=alt.Axis(labelExpr="replace(format(datum.value, '.1f'), '.', ',') + '%'"),
        ),
        color=alt.Color(
            "serie:N",
            title="Série",
            scale=alt.Scale(range=["#2f6f9f", "#d62728", "#f28e2b"]),
        ),
        tooltip=[
            alt.Tooltip("periodo:N", title="Período"),
            alt.Tooltip("serie:N", title="Série"),
            alt.Tooltip("valor_formatado:N", title="Valor"),
        ],
    )
    return (base.mark_area(opacity=0.28, interpolate="monotone") + base.mark_line(size=2, interpolate="monotone")).properties(height=320)


def _render_model_header() -> None:
    st.markdown(_MODEL_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="fidc-model-header">
          <div class="fidc-model-kicker">Simulação econômica</div>
          <h2 class="fidc-model-title">Modelo FIDC</h2>
          <div class="fidc-model-copy">
            Este é um modelo econômico-financeiro para simular cenários de perda máxima em uma
            carteira de FIDC, considerando diferentes níveis de rentabilidade, subordinação e
            inadimplência.
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
            f"{_format_number_br(kpis.duration_senior_anos, 2)} anos" if kpis.duration_senior_anos is not None else "N/D",
            "Classe sênior",
        ),
        ("Pre DI na duration", _format_percent(kpis.pre_di_duration), "Curva interpolada"),
        ("SUB inicial", _format_brl(results[0].pl_sub_jr), "Colchão subordinado"),
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
    source_errors = _validate_model_inputs(inputs)
    if source_errors:
        st.error("Fonte local do modelo incompleta: " + "; ".join(source_errors) + ".")
        return

    default_tx_cessao_am = inputs.premissas.get("Tx Cessão (%am)", 0.1)
    default_tx_cessao_aa = monthly_to_annual_252_rate(default_tx_cessao_am)
    default_senior_pct = inputs.premissas.get("Proporção PL Sr.", 0.9) * 100.0
    default_mezz_pct = inputs.premissas.get("Proporção PL Mezz", 0.05) * 100.0
    default_sub_pct = inputs.premissas.get(
        "Proporção PL Jr.",
        1.0 - default_senior_pct / 100.0 - default_mezz_pct / 100.0,
    ) * 100.0

    left, right = st.columns([1.2, 0.8])
    with left:
        with st.form("modelo-fidc-premissas"):
            st.markdown("##### Premissas da carteira")
            volume_text = _text_number_input(
                "Volume da carteira (R$)",
                default=inputs.premissas.get("Volume", 1_000_000.0),
                key="modelo_volume",
                decimals=2,
                help_text="Valor total da carteira em reais. Não há escala implícita em milhões ou bilhões.",
            )
            taxa_cessao_base = st.radio(
                "Base da taxa de cessão",
                ["% a.m.", "% a.a. base 252 dias úteis"],
                horizontal=True,
                help="A base anual usa 252 dias úteis por ano e 21 dias úteis por mês.",
            )
            if taxa_cessao_base == "% a.m.":
                tx_cessao_text = _text_number_input(
                    "Taxa de cessão (% a.m.)",
                    default=default_tx_cessao_am * 100.0,
                    key="modelo_tx_cessao_am",
                    decimals=4,
                )
                tx_cessao_aa_text = ""
            else:
                tx_cessao_aa_text = _text_number_input(
                    "Taxa de cessão (% a.a., base 252 dias úteis)",
                    default=default_tx_cessao_aa * 100.0,
                    key="modelo_tx_cessao_aa",
                    decimals=4,
                    help_text="O app converte esta taxa para uma taxa mensal equivalente antes de rodar o motor.",
                )
                tx_cessao_text = ""

            costs_a, costs_b = st.columns(2)
            with costs_a:
                custo_adm_text = _text_number_input(
                    "Custo de administração e gestão (% a.a.)",
                    default=inputs.premissas.get("Custo Adm/Gestão (a.a.)", 0.0035) * 100.0,
                    key="modelo_custo_adm_pct",
                    decimals=4,
                    help_text="Digite 0,35 para representar 0,35% ao ano. O motor converte internamente para 0,0035.",
                )
            with costs_b:
                custo_min_text = _text_number_input(
                    "Custo mínimo de administração e gestão (R$/mês)",
                    default=inputs.premissas.get("Custo Adm/Gestão (mín)", 20000.0),
                    key="modelo_custo_min",
                    decimals=2,
                    help_text="Piso mensal aplicado pela fórmula max(carteira * custo % a.a. / 12, custo mínimo).",
                )
            inadimplencia_text = _text_number_input(
                "Inadimplência (% da carteira total)",
                default=inputs.premissas.get("Inadimplência", 0.1) * 100.0,
                key="modelo_inadimplencia_pct",
                decimals=4,
                help_text="Na planilha de referência, a perda é proporcional aos dias corridos do período.",
            )

            st.markdown("##### Estrutura de PL")
            prop_a, prop_b, prop_c = st.columns(3)
            with prop_a:
                senior_pct_text = _text_number_input(
                    "PL sênior (%)",
                    default=default_senior_pct,
                    key="modelo_prop_senior",
                    decimals=2,
                )
            with prop_b:
                mezz_pct_text = _text_number_input(
                    "PL mezzanino/MES (%)",
                    default=default_mezz_pct,
                    key="modelo_prop_mezz",
                    decimals=2,
                )
            with prop_c:
                sub_pct_text = _text_number_input(
                    "PL subordinado/SUB (%)",
                    default=default_sub_pct,
                    key="modelo_prop_sub",
                    decimals=2,
                )

            st.markdown("##### Remuneração das cotas")
            senior_mode_label = st.selectbox(
                "Remuneração cota sênior",
                ["Pós-fixada: spread sobre CDI", "Pré-fixada: taxa % a.a."],
                help="Pós-fixada replica a planilha: (1 + curva DI/Pré) * (1 + spread) - 1. Pré-fixada usa diretamente a taxa anual informada.",
            )
            senior_rate_label = (
                "Spread cota sênior sobre CDI (% a.a.)"
                if _rate_mode_from_label(senior_mode_label) == RATE_MODE_POST_CDI
                else "Taxa pré-fixada cota sênior (% a.a.)"
            )
            senior_rate_text = _text_number_input(
                senior_rate_label,
                default=inputs.premissas.get("Taxa Sênior", 0.02) * 100.0,
                key="modelo_taxa_senior",
                decimals=2,
            )

            mezz_mode_label = st.selectbox(
                "Remuneração cota mezzanino/MES",
                ["Pós-fixada: spread sobre CDI", "Pré-fixada: taxa % a.a."],
                help="Pós-fixada replica a planilha para a cota mezzanino; pré-fixada usa taxa anual efetiva.",
            )
            mezz_rate_label = (
                "Spread cota mezzanino sobre CDI (% a.a.)"
                if _rate_mode_from_label(mezz_mode_label) == RATE_MODE_POST_CDI
                else "Taxa pré-fixada cota mezzanino (% a.a.)"
            )
            mezz_rate_text = _text_number_input(
                mezz_rate_label,
                default=inputs.premissas.get("Taxa Mezz", 0.05) * 100.0,
                key="modelo_taxa_mezz",
                decimals=2,
            )

            sub_mode_label = st.selectbox(
                "Remuneração cota subordinada/SUB",
                [
                    "Residual (compatível com a planilha)",
                    "Pós-fixada: spread sobre CDI (taxa-alvo)",
                    "Pré-fixada: taxa % a.a. (taxa-alvo)",
                ],
                help="A planilha não tem pagamento programado da SUB: a SUB absorve o residual. As taxas-alvo ficam explícitas, sem alterar a paridade.",
            )
            sub_rate_text = "0,00"
            if not sub_mode_label.startswith("Residual"):
                sub_rate_text = _text_number_input(
                    "Taxa-alvo cota subordinada/SUB (% a.a.)",
                    default=0.0,
                    key="modelo_taxa_sub",
                    decimals=2,
                )
            submitted = st.form_submit_button("Rodar simulação", width="stretch")

    try:
        volume = _parse_br_number(volume_text, field_name="Volume da carteira (R$)")
        if taxa_cessao_base == "% a.m.":
            tx_cessao_am = _parse_br_number(tx_cessao_text, field_name="Taxa de cessão (% a.m.)") / 100.0
            tx_cessao_aa_equivalente = monthly_to_annual_252_rate(tx_cessao_am)
        else:
            tx_cessao_aa_equivalente = _parse_br_number(
                tx_cessao_aa_text,
                field_name="Taxa de cessão (% a.a., base 252 dias úteis)",
            ) / 100.0
            tx_cessao_am = annual_252_to_monthly_rate(tx_cessao_aa_equivalente)
        custo_adm_aa = _parse_br_number(custo_adm_text, field_name="Custo de administração e gestão (% a.a.)") / 100.0
        custo_min = _parse_br_number(custo_min_text, field_name="Custo mínimo de administração e gestão (R$/mês)")
        inadimplencia = _parse_br_number(inadimplencia_text, field_name="Inadimplência (% da carteira total)") / 100.0
        proporcao_senior = _parse_br_number(senior_pct_text, field_name="PL sênior (%)") / 100.0
        proporcao_mezz = _parse_br_number(mezz_pct_text, field_name="PL mezzanino/MES (%)") / 100.0
        proporcao_sub = _parse_br_number(sub_pct_text, field_name="PL subordinado/SUB (%)") / 100.0
        taxa_senior = _parse_br_number(senior_rate_text, field_name=senior_rate_label) / 100.0
        taxa_mezz = _parse_br_number(mezz_rate_text, field_name=mezz_rate_label) / 100.0
        taxa_sub = _parse_br_number(sub_rate_text, field_name="Taxa-alvo cota subordinada/SUB (% a.a.)") / 100.0
    except ValueError as exc:
        st.error(str(exc))
        return

    if volume <= 0:
        st.error("O volume da carteira deve ser maior que zero.")
        return

    prop_total = proporcao_senior + proporcao_mezz + proporcao_sub
    if abs(prop_total - 1.0) > 0.0001:
        st.error(f"As proporções de PL precisam somar 100,00%. Soma atual: {_format_percent(prop_total)}.")
        return

    premissas = Premissas(
        volume=volume,
        tx_cessao_am=tx_cessao_am,
        tx_cessao_cdi_aa=inputs.premissas.get("Tx Cessão (CDI+ %aa)"),
        custo_adm_aa=custo_adm_aa,
        custo_min=custo_min,
        inadimplencia=inadimplencia,
        proporcao_senior=proporcao_senior,
        taxa_senior=taxa_senior,
        proporcao_mezz=proporcao_mezz,
        taxa_mezz=taxa_mezz,
        proporcao_subordinada=proporcao_sub,
        taxa_sub_jr=taxa_sub,
        tipo_taxa_senior=_rate_mode_from_label(senior_mode_label),
        tipo_taxa_mezz=_rate_mode_from_label(mezz_mode_label),
        tipo_taxa_sub_jr=(
            "residual"
            if sub_mode_label.startswith("Residual")
            else RATE_MODE_PRE
            if sub_mode_label.startswith("Pré")
            else RATE_MODE_POST_CDI
        ),
    )

    with right:
        st.info(
            "Fonte da curva: snapshot local da aba `BMF` do `Modelo_Publico.xlsm`, com curva DI/Pré da B3/BM&F. "
            "O app não consulta B3/CDI em tempo de execução; se `model_data.json` estiver incompleto, a aba falha explicitamente."
        )
        st.markdown(
            "\n".join(
                [
                    f"- Taxa de cessão usada no motor: {_format_percent(tx_cessao_am, 4)} a.m.; equivalente anual 252 DU: {_format_percent(tx_cessao_aa_equivalente, 4)} a.a.",
                    "- O calendário útil usa base brasileira de 252 dias com feriados explícitos da planilha.",
                    "- Sênior e mezz podem ser pós-fixadas sobre CDI/DI ou pré-fixadas em taxa anual.",
                    "- A SUB é residual na planilha: ela absorve o excedente ou a perda após sênior e mezz.",
                    "- Inadimplência segue a fórmula histórica do arquivo: perda proporcional ao delta de dias corridos dividido por 100.",
                    "- `Tx Cessão (CDI+ %aa)` existe no JSON histórico, mas não entra nas fórmulas ativas da planilha.",
                ]
            )
        )
        if not sub_mode_label.startswith("Residual"):
            st.warning(
                "A taxa da SUB está registrada como taxa-alvo informativa. O workbook de referência não possui pagamento "
                "programado da SUB; por isso, a paridade do waterfall mantém a SUB como residual."
            )
        st.warning(
            "Não confundir esta aba com o IME: aqui `inadimplência` é perda econômica premissada, "
            "`subordinação` é econômica/residual, e `PL` representa saldo econômico do veículo."
        )

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
    display_frame = _build_display_dataframe(export_frame)

    st.markdown('<div class="fidc-model-section-title">KPIs de saída</div>', unsafe_allow_html=True)
    _render_model_kpi_cards(kpis, results)

    st.caption(
        "Retorno anualizado = taxa interna anual de retorno dos pagamentos projetados de cada classe. "
        "Se a série não tiver fluxo válido, o app mostra `N/D` em vez de inventar um número. "
        "Esses KPIs são econômicos e não equivalem automaticamente aos indicadores observados no IME."
    )

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.markdown('<div class="fidc-model-section-title">Saldos econômicos das cotas</div>', unsafe_allow_html=True)
        st.altair_chart(_area_money_chart(_build_balance_area_frame(frame)), width="stretch")
    with chart_right:
        st.markdown('<div class="fidc-model-section-title">Perda máxima e subordinação</div>', unsafe_allow_html=True)
        st.altair_chart(_area_percent_chart(_build_loss_area_frame(frame, premissas.volume)), width="stretch")

    st.markdown('<div class="fidc-model-section-title">Memória de cálculo</div>', unsafe_allow_html=True)
    memory_df = pd.DataFrame(
        [
            {
                "Indicador": "Fluxo econômico da carteira",
                "Fórmula": "carteira * ((1 + tx_cessao_am) ^ (delta_du / 21) - 1)",
                "Observação": "Replica Qx no Fluxo Base. Se o usuário informar taxa a.a. base 252, o app converte antes para taxa mensal equivalente.",
            },
            {
                "Indicador": "Conversão de taxa de cessão anual",
                "Fórmula": "tx_cessao_am = (1 + tx_cessao_aa_252) ^ (21 / 252) - 1",
                "Observação": "Conversão financeira efetiva, com 21 dias úteis médios por mês e 252 dias úteis por ano.",
            },
            {
                "Indicador": "Custo adm/gestão",
                "Fórmula": "max(carteira * custo_adm_aa / 12, custo_min)",
                "Observação": "O usuário informa percentual em base 100. Ex.: 0,35 significa 0,35% a.a.; custo mínimo é R$/mês.",
            },
            {
                "Indicador": "Perda econômica por inadimplência",
                "Fórmula": "carteira * (inadimplencia * delta_dc / 100)",
                "Observação": "Inadimplência é informada como % da carteira total, mas a planilha distribui a perda pelo delta de dias corridos.",
            },
            {
                "Indicador": "Juros sênior/mezz",
                "Fórmula": "pós: (1 + curva DI/Pré) * (1 + spread) - 1; pré: taxa anual informada",
                "Observação": "O FRA de cada período usa base 252 DU para acumular juros da classe.",
            },
            {
                "Indicador": "Proporções de PL",
                "Fórmula": "PL sênior + PL mezzanino + PL SUB = 100%",
                "Observação": "A SUB agora é uma premissa explícita na interface; o motor bloqueia soma diferente de 100%.",
            },
            {
                "Indicador": "Júnior residual / subordinação econômica",
                "Fórmula": "Residual econômico = PL econômico do veículo - PL sênior - PL mezz; série exibida replica o deslocamento da planilha",
                "Observação": "A planilha não remunera a SUB programaticamente; taxas da SUB ficam como premissa-alvo informativa até decisão de modelagem.",
            },
        ]
    )
    st.dataframe(memory_df, width="stretch", hide_index=True)

    with st.expander("Passo a Passo", expanded=False):
        st.markdown(
            "\n".join(
                [
                    "Este modelo simula uma carteira de FIDC e mostra como juros, custos, inadimplência e estrutura de cotas afetam o colchão de proteção.",
                    "",
                    "- Volume da carteira é o valor em reais dos recebíveis comprados pelo fundo.",
                    "- Taxa de cessão é a rentabilidade esperada desses recebíveis. Ela pode ser informada ao mês ou ao ano, com conversão por 252 dias úteis.",
                    "- Cotas sênior têm prioridade de pagamento; mezzanino fica no meio; subordinada/SUB absorve perdas primeiro e recebe o residual.",
                    "- Subordinação é o tamanho desse colchão de SUB em relação ao PL econômico do fundo.",
                    "- Inadimplência é a perda premissada como percentual da carteira total, aplicada no tempo pela regra da planilha.",
                    "- Perda máxima indica quanto do colchão econômico vai sendo consumido antes de afetar as classes acima.",
                    "- No gráfico de saldos, a área da SUB mostra o colchão disponível; quanto menor ela fica, menor a proteção.",
                    "- No gráfico de perda e subordinação, maior inadimplência acumulada com menor subordinação indica cenário mais pressionado.",
                    "- Rentabilidade maior da carteira aumenta o excesso de spread; custos, taxas das cotas e inadimplência reduzem o residual disponível.",
                ]
            )
        )

    st.markdown('<div class="fidc-model-section-title">Timeline detalhada</div>', unsafe_allow_html=True)
    st.dataframe(display_frame, width="stretch", hide_index=True)

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
