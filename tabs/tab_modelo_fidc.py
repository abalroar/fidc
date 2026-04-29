from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from html import escape
from io import BytesIO

import altair as alt
import pandas as pd
import streamlit as st

from data_loader import load_model_inputs
from services.fidc_model import (
    AMORTIZATION_MODE_BULLET,
    AMORTIZATION_MODE_LINEAR,
    AMORTIZATION_MODE_NONE,
    AMORTIZATION_MODE_WORKBOOK,
    INTEREST_PAYMENT_MODE_AFTER_GRACE,
    INTEREST_PAYMENT_MODE_BULLET,
    INTEREST_PAYMENT_MODE_PERIODIC,
    INTERPOLATION_METHOD_FLAT_FORWARD_252,
    INTERPOLATION_METHOD_SPLINE,
    RATE_MODE_POST_CDI,
    RATE_MODE_PRE,
    Premissas,
    build_flow,
    build_kpis,
    cession_discount_to_monthly_rate,
    monthly_to_annual_252_rate,
    monthly_rate_to_cession_discount,
)
from services.fidc_model.b3_curves import (
    B3CurveError,
    B3CurveSnapshot,
    DEFAULT_TAXASWAP_CURVE_CODE,
    fetch_latest_taxaswap_curve,
    fetch_taxaswap_curve,
)
from services.fidc_model.calendar import (
    B3CalendarError,
    B3CalendarSnapshot,
    build_b3_calendar_snapshot,
    fetch_b3_trading_calendar_html,
    merge_with_b3_market_holidays,
)


SNAPSHOT_CURVE_DATE = date(2025, 2, 25)
CURVE_SOURCE_B3_LATEST = "B3 - último pregão disponível"
CURVE_SOURCE_B3_DATE = "B3 - data escolhida"
CURVE_SOURCE_SNAPSHOT = "Snapshot local da planilha"
CURVE_SOURCE_OPTIONS = [CURVE_SOURCE_B3_LATEST, CURVE_SOURCE_B3_DATE, CURVE_SOURCE_SNAPSHOT]
INTERPOLATION_LABEL_B3 = "Flat Forward 252 (metodologia B3)"
INTERPOLATION_LABEL_SPLINE = "Spline (compatibilidade com a planilha)"
INTERPOLATION_OPTIONS = [INTERPOLATION_LABEL_B3, INTERPOLATION_LABEL_SPLINE]
CALENDAR_SOURCE_B3_OFFICIAL = "B3 oficial + projeção explícita"
CALENDAR_SOURCE_B3_PROJECTED = "Calendário B3 projetado"
CALENDAR_SOURCE_SNAPSHOT = "Feriados do snapshot da planilha"
CALENDAR_SOURCE_OPTIONS = [CALENDAR_SOURCE_B3_OFFICIAL, CALENDAR_SOURCE_B3_PROJECTED, CALENDAR_SOURCE_SNAPSHOT]
DATE_SCHEDULE_WORKBOOK = "Compatível com a planilha"
DATE_SCHEDULE_MONTHLY = "Mensal pelo prazo informado"
PORTFOLIO_MODE_REVOLVING = "Revolvente"
PORTFOLIO_MODE_STATIC = "Carteira estática"
CESSION_INPUT_DISCOUNT = "Taxa de Cessão"
CESSION_INPUT_MONTHLY = "Taxa Mensal (%)"
DEFAULT_VOLUME_CARTEIRA = 750_000_000.0
DEFAULT_TX_CESSAO_AM = 0.04
DEFAULT_CUSTO_ADM_AA = 0.0035
DEFAULT_CUSTO_MIN_MENSAL = 20_000.0
DEFAULT_INADIMPLENCIA = 0.0
DEFAULT_PROP_SENIOR = 0.75
DEFAULT_PROP_MEZZ = 0.15
DEFAULT_PROP_SUB = 0.10
DEFAULT_TAXA_SENIOR = 0.0135
DEFAULT_TAXA_MEZZ = 0.05
DEFAULT_PRAZO_ANOS = 3.0
DEFAULT_PRAZO_RECEBIVEIS_MESES = 6.0
DEFAULT_CARENCIA_PRINCIPAL_MESES = 30.0
AMORTIZATION_LABELS = {
    "Compatível com a planilha": AMORTIZATION_MODE_WORKBOOK,
    "Linear após carência": AMORTIZATION_MODE_LINEAR,
    "Bullet no vencimento": AMORTIZATION_MODE_BULLET,
    "Sem amortização programada": AMORTIZATION_MODE_NONE,
}
INTEREST_LABELS = {
    "Pago em todo período": INTEREST_PAYMENT_MODE_PERIODIC,
    "Pago após carência": INTEREST_PAYMENT_MODE_AFTER_GRACE,
    "Bullet no vencimento": INTEREST_PAYMENT_MODE_BULLET,
}


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


@dataclass(frozen=True)
class _SelectedCurve:
    source_label: str
    curve_code: str
    base_date: date
    curva_du: tuple[float, ...]
    curva_taxa_aa: tuple[float, ...]
    source_url: str
    retrieved_label: str
    content_sha256: str
    point_count: int
    first_du: int | None
    last_du: int | None
    raw_line_count: int | None = None

    @property
    def cache_key(self) -> tuple[str, str, str, str]:
        return (
            self.source_label,
            self.curve_code,
            self.base_date.isoformat(),
            self.content_sha256[:16],
        )


@dataclass(frozen=True)
class _SelectedCalendar:
    source_label: str
    feriados: tuple[date, ...]
    holiday_count: int
    first_holiday: date | None
    last_holiday: date | None
    official_years: tuple[int, ...] = ()
    projected_years: tuple[int, ...] = ()
    source_url: str = ""
    retrieved_label: str = ""
    content_sha256: str = ""

    @property
    def cache_key(self) -> tuple[str, int, str, str, str, str]:
        return (
            self.source_label,
            self.holiday_count,
            self.first_holiday.isoformat() if self.first_holiday else "",
            self.last_holiday.isoformat() if self.last_holiday else "",
            ",".join(str(year) for year in self.official_years),
            ",".join(str(year) for year in self.projected_years),
        )


@dataclass(frozen=True)
class _RevolvencyMetrics:
    portfolio_mode: str
    prazo_total_anos: float
    prazo_medio_recebiveis_meses: float
    giro_estimado: float
    carteira_total_originada: float
    sub_final_sem_inadimplencia: float
    perda_maxima_sobre_originacao: float | None


@st.cache_data(show_spinner=False, ttl=6 * 60 * 60)
def _load_b3_curve_for_date(date_iso: str, curve_code: str) -> B3CurveSnapshot:
    return fetch_taxaswap_curve(date.fromisoformat(date_iso), curve_code=curve_code)


@st.cache_data(show_spinner=False, ttl=6 * 60 * 60)
def _load_latest_b3_curve(start_date_iso: str, curve_code: str) -> B3CurveSnapshot:
    return fetch_latest_taxaswap_curve(start_date=date.fromisoformat(start_date_iso), curve_code=curve_code)


@st.cache_data(show_spinner=False, ttl=24 * 60 * 60)
def _load_b3_calendar_snapshot(start_year: int, end_year: int) -> B3CalendarSnapshot:
    html_text, content_hash = fetch_b3_trading_calendar_html()
    datas = [date(start_year, 1, 1), date(end_year, 12, 31)]
    return build_b3_calendar_snapshot(datas, html_text, content_hash=content_hash)


def _selected_curve_from_snapshot(inputs) -> _SelectedCurve:
    return _SelectedCurve(
        source_label=CURVE_SOURCE_SNAPSHOT,
        curve_code="PRE",
        base_date=SNAPSHOT_CURVE_DATE,
        curva_du=tuple(float(value) for value in inputs.curva_du),
        curva_taxa_aa=tuple(float(value) for value in inputs.curva_cdi),
        source_url="Modelo_Publico.xlsm / model_data.json",
        retrieved_label="snapshot local sem consulta externa",
        content_sha256="local-snapshot",
        point_count=len(inputs.curva_du),
        first_du=int(inputs.curva_du[0]) if inputs.curva_du else None,
        last_du=int(inputs.curva_du[-1]) if inputs.curva_du else None,
        raw_line_count=None,
    )


def _selected_curve_from_b3(snapshot: B3CurveSnapshot, source_label: str) -> _SelectedCurve:
    return _SelectedCurve(
        source_label=source_label,
        curve_code=snapshot.curve_code,
        base_date=snapshot.generated_at,
        curva_du=tuple(snapshot.curva_du),
        curva_taxa_aa=tuple(snapshot.curva_taxa_aa),
        source_url=snapshot.source_url,
        retrieved_label=snapshot.retrieved_at.strftime("%d/%m/%Y %H:%M:%S UTC"),
        content_sha256=snapshot.content_sha256,
        point_count=len(snapshot.points),
        first_du=snapshot.first_du,
        last_du=snapshot.last_du,
        raw_line_count=snapshot.raw_line_count,
    )


def _selected_calendar(
    inputs,
    source_label: str,
    b3_snapshot: B3CalendarSnapshot | None = None,
    datas: list[datetime] | None = None,
) -> _SelectedCalendar:
    flow_dates = datas or inputs.datas
    if source_label == CALENDAR_SOURCE_B3_OFFICIAL:
        if b3_snapshot is None:
            raise B3CalendarError("Snapshot de calendário B3 não foi carregado.")
        holidays = tuple(b3_snapshot.holidays)
        return _SelectedCalendar(
            source_label=source_label,
            feriados=holidays,
            holiday_count=len(holidays),
            first_holiday=holidays[0] if holidays else None,
            last_holiday=holidays[-1] if holidays else None,
            official_years=b3_snapshot.official_years,
            projected_years=b3_snapshot.projected_years,
            source_url=b3_snapshot.source_url,
            retrieved_label=b3_snapshot.retrieved_at.strftime("%d/%m/%Y %H:%M:%S UTC"),
            content_sha256=b3_snapshot.content_sha256,
        )
    if source_label == CALENDAR_SOURCE_B3_PROJECTED:
        holidays = tuple(merge_with_b3_market_holidays(inputs.feriados, flow_dates))
        projected_years = tuple(range(flow_dates[0].year, flow_dates[-1].year + 1)) if flow_dates else ()
    else:
        holidays = tuple(holiday.date() for holiday in inputs.feriados)
        projected_years = ()
    return _SelectedCalendar(
        source_label=source_label,
        feriados=holidays,
        holiday_count=len(holidays),
        first_holiday=holidays[0] if holidays else None,
        last_holiday=holidays[-1] if holidays else None,
        projected_years=projected_years,
    )


def _interpolation_method_from_label(label: str) -> str:
    return INTERPOLATION_METHOD_FLAT_FORWARD_252 if label == INTERPOLATION_LABEL_B3 else INTERPOLATION_METHOD_SPLINE


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


def _format_brl_input_value(value: float, decimals: int = 2) -> str:
    return f"R$ {_format_input_value(value, decimals)}"


def _format_percent_input_value(value: float, decimals: int = 2) -> str:
    return f"{_format_input_value(value, decimals)}%"


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


def _format_raw_input_text(value: str, *, decimals: int, kind: str) -> str:
    parsed = _parse_br_number(value, field_name="valor")
    if kind == "brl":
        return _format_brl_input_value(parsed, decimals)
    if kind == "percent":
        return _format_percent_input_value(parsed, decimals)
    if kind == "number":
        return _format_input_value(parsed, decimals)
    raise ValueError(f"Tipo de input inválido: {kind}")


_INPUT_NORMALIZATION_SPECS = {
    "modelo_volume": (2, "brl"),
    "modelo_tx_cessao_desagio": (2, "percent"),
    "modelo_tx_cessao_mensal": (2, "percent"),
    "modelo_custo_adm_pct": (2, "percent"),
    "modelo_custo_min": (2, "brl"),
    "modelo_inadimplencia_pct": (2, "percent"),
    "modelo_prop_senior": (1, "percent"),
    "modelo_prop_mezz": (1, "percent"),
    "modelo_prop_sub": (1, "percent"),
    "modelo_taxa_senior": (2, "percent"),
    "modelo_taxa_mezz": (2, "percent"),
    "modelo_taxa_sub": (2, "percent"),
    "modelo_prazo_fidc_anos": (1, "number"),
    "modelo_prazo_recebiveis_meses": (1, "number"),
    "modelo_prazo_senior_anos": (1, "number"),
    "modelo_prazo_mezz_anos": (1, "number"),
    "modelo_prazo_sub_anos": (1, "number"),
    "modelo_inicio_amort_senior": (0, "number"),
    "modelo_inicio_amort_mezz": (0, "number"),
}


def _normalize_model_input_values() -> None:
    for key, (decimals, kind) in _INPUT_NORMALIZATION_SPECS.items():
        if key not in st.session_state:
            continue
        try:
            st.session_state[key] = _format_raw_input_text(st.session_state[key], decimals=decimals, kind=kind)
        except ValueError:
            continue


def _add_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    month_lengths = (31, 29 if _is_leap_year(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    day = min(dt.day, month_lengths[month - 1])
    return dt.replace(year=year, month=month, day=day)


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _build_monthly_dates(start: datetime, prazo_total_anos: float) -> list[datetime]:
    total_months = max(1, round(prazo_total_anos * 12.0))
    return [_add_months(start, month) for month in range(total_months + 1)]


def _build_simulation_dates(inputs, schedule_label: str, prazo_total_anos: float) -> list[datetime]:
    if schedule_label == DATE_SCHEDULE_MONTHLY:
        return _build_monthly_dates(inputs.datas[0], prazo_total_anos)
    return list(inputs.datas)


def _label_for_value(mapping: dict[str, str], value: str) -> str:
    for label, mapped_value in mapping.items():
        if mapped_value == value:
            return label
    return next(iter(mapping))


def _ensure_session_option(key: str, options: list[str], default_index: int = 0) -> str:
    value = st.session_state.get(key)
    if value not in options:
        value = options[default_index]
        st.session_state[key] = value
    return value


def _ensure_session_date(key: str, default_value: date) -> date:
    value = st.session_state.get(key)
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        value = default_value
        st.session_state[key] = value
    return value


def _build_revolvency_metrics(
    *,
    premissas: Premissas,
    zero_default_results,
    portfolio_mode: str,
) -> _RevolvencyMetrics:
    prazo_total_anos = float(premissas.prazo_fidc_anos or 0.0)
    prazo_medio_meses = max(float(premissas.prazo_medio_recebiveis_meses), 0.01)
    giro_estimado = prazo_total_anos * 12.0 / prazo_medio_meses
    if portfolio_mode == PORTFOLIO_MODE_STATIC:
        giro_para_originacao = 1.0
    else:
        giro_para_originacao = giro_estimado
    carteira_total_originada = premissas.volume * max(giro_para_originacao, 0.0)
    sub_final = max(float(zero_default_results[-1].pl_sub_jr), 0.0) if zero_default_results else 0.0
    perda_maxima = sub_final / carteira_total_originada if carteira_total_originada > 0 else None
    return _RevolvencyMetrics(
        portfolio_mode=portfolio_mode,
        prazo_total_anos=prazo_total_anos,
        prazo_medio_recebiveis_meses=prazo_medio_meses,
        giro_estimado=giro_estimado,
        carteira_total_originada=carteira_total_originada,
        sub_final_sem_inadimplencia=sub_final,
        perda_maxima_sobre_originacao=perda_maxima,
    )


def _text_number_input(
    label: str,
    *,
    default: float,
    key: str,
    decimals: int = 2,
    help_text: str | None = None,
) -> str:
    return st.text_input(label, value=_format_input_value(default, decimals), key=key, help=help_text)


def _text_brl_input(
    label: str,
    *,
    default: float,
    key: str,
    decimals: int = 2,
    help_text: str | None = None,
) -> str:
    return st.text_input(label, value=_format_brl_input_value(default, decimals), key=key, help=help_text)


def _text_percent_input(
    label: str,
    *,
    default: float,
    key: str,
    decimals: int = 2,
    help_text: str | None = None,
) -> str:
    return st.text_input(label, value=_format_percent_input_value(default, decimals), key=key, help=help_text)


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
            "taxa_mezz": "Taxa MEZZ",
            "fra_mezz": "FRA MEZZ",
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
            "principal_mezz": "Principal MEZZ",
            "juros_mezz": "Juros MEZZ",
            "pmt_mezz": "PMT MEZZ",
            "pl_mezz": "PL MEZZ",
            "fluxo_remanescente_mezz": "Fluxo remanescente após MEZZ",
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
                "Indicador": "Retorno anualizado da classe MEZZ (econômico)",
                "Valor": kpis.xirr_mezz,
                "Definicao": "Taxa interna anual de retorno dos pagamentos projetados da classe MEZZ.",
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


def _build_curve_source_dataframe(
    selected_curve: _SelectedCurve,
    selected_calendar: _SelectedCalendar,
    interpolation_label: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Campo": "Fonte", "Valor": selected_curve.source_label},
            {"Campo": "Curva", "Valor": selected_curve.curve_code},
            {"Campo": "Interpolação", "Valor": interpolation_label},
            {"Campo": "Data-base", "Valor": selected_curve.base_date.strftime("%d/%m/%Y")},
            {"Campo": "Pontos", "Valor": _format_number_br(selected_curve.point_count, 0)},
            {"Campo": "DU inicial", "Valor": selected_curve.first_du if selected_curve.first_du is not None else "N/D"},
            {"Campo": "DU final", "Valor": selected_curve.last_du if selected_curve.last_du is not None else "N/D"},
            {"Campo": "Calendário de dias úteis", "Valor": selected_calendar.source_label},
            {"Campo": "Feriados considerados", "Valor": _format_number_br(selected_calendar.holiday_count, 0)},
            {
                "Campo": "Anos oficiais B3",
                "Valor": ", ".join(str(year) for year in selected_calendar.official_years) or "N/D",
            },
            {
                "Campo": "Anos projetados",
                "Valor": ", ".join(str(year) for year in selected_calendar.projected_years) or "N/D",
            },
            {
                "Campo": "Primeiro feriado",
                "Valor": selected_calendar.first_holiday.strftime("%d/%m/%Y") if selected_calendar.first_holiday else "N/D",
            },
            {
                "Campo": "Último feriado",
                "Valor": selected_calendar.last_holiday.strftime("%d/%m/%Y") if selected_calendar.last_holiday else "N/D",
            },
            {"Campo": "URL calendário", "Valor": selected_calendar.source_url or "N/D"},
            {"Campo": "Calendário baixado em", "Valor": selected_calendar.retrieved_label or "N/D"},
            {"Campo": "SHA-256 calendário", "Valor": selected_calendar.content_sha256 or "N/D"},
            {"Campo": "URL/Origem", "Valor": selected_curve.source_url},
            {"Campo": "Baixado em", "Valor": selected_curve.retrieved_label},
            {"Campo": "SHA-256", "Valor": selected_curve.content_sha256},
        ]
    )


def _build_revolvency_export_dataframe(metrics: _RevolvencyMetrics) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Indicador": "Modo da carteira", "Valor": metrics.portfolio_mode},
            {"Indicador": "Prazo total do FIDC (anos)", "Valor": metrics.prazo_total_anos},
            {"Indicador": "Prazo médio dos recebíveis (meses)", "Valor": metrics.prazo_medio_recebiveis_meses},
            {"Indicador": "Giro estimado da carteira", "Valor": metrics.giro_estimado},
            {"Indicador": "Carteira total originada estimada", "Valor": metrics.carteira_total_originada},
            {"Indicador": "SUB final sem inadimplência", "Valor": metrics.sub_final_sem_inadimplencia},
            {"Indicador": "Perda máxima sobre carteira originada", "Valor": metrics.perda_maxima_sobre_originacao},
        ]
    )


def _build_workbook_mechanics_markdown(
    *,
    selected_curve: _SelectedCurve,
    selected_calendar: _SelectedCalendar,
    interpolation_label: str,
    taxa_cessao_input_mode: str,
) -> str:
    return "\n".join(
        [
            "Esta seção descreve a mecânica completa da aba e a base de cálculo herdada da planilha de referência.",
            "",
            "### 1. Datas, dias corridos e dias úteis",
            "",
            "- A simulação roda em uma grade de competências carregada do `model_data.json`, extraída da planilha original.",
            "- `DC` é a quantidade de dias corridos desde a data inicial do fluxo.",
            "- `DU` é a quantidade de dias úteis desde a data inicial, descontando fins de semana e feriados.",
            f"- Calendário usado nesta simulação: `{selected_calendar.source_label}`.",
            f"- Curva usada nesta simulação: `{selected_curve.source_label}`, data-base `{selected_curve.base_date:%d/%m/%Y}`, interpolação `{interpolation_label}`.",
            "",
            "### 2. Taxa da carteira",
            "",
            "- O usuário pode informar a taxa de duas formas:",
            "- `Taxa de Cessão`: deságio sobre o valor futuro. Ex.: comprar R$ 100 por R$ 95 significa taxa de cessão de `5,00%`.",
            "- `Taxa Mensal (%)`: taxa efetiva cobrada ao mês, que é a base usada diretamente pelo motor.",
            "",
            "```text",
            "taxa_mensal = 1 / (1 - taxa_cessao) - 1",
            "taxa_cessao = taxa_mensal / (1 + taxa_mensal)",
            "```",
            "",
            "- A carteira gera retorno econômico pela fórmula da planilha:",
            "",
            "```text",
            "fluxo_carteira = carteira * ((1 + taxa_cessao_am) ^ (delta_DU / 21) - 1)",
            "```",
            "",
            f"- Entrada informada pelo usuário nesta simulação: `{taxa_cessao_input_mode}`.",
            "- Em ambos os casos, a aba também calcula o de-para anual em base 252 dias úteis:",
            "",
            "```text",
            "taxa_cessao_aa_252 = (1 + taxa_cessao_am) ^ (252 / 21) - 1",
            "```",
            "",
            "### 3. Custos de administração e gestão",
            "",
            "- O custo percentual é anual, mas a planilha cobra uma parcela mensal com piso mínimo:",
            "",
            "```text",
            "custos_adm = max(carteira * custo_adm_aa / 12, custo_minimo_mensal)",
            "```",
            "",
            "- Exemplo: `0,35` na interface significa `0,35% a.a.`; internamente vira `0,0035`.",
            "",
            "### 4. Inadimplência",
            "",
            "- A fórmula histórica da planilha não trata a inadimplência como perda total da vida do fundo. Ela aplica a perda proporcionalmente aos dias corridos do período:",
            "",
            "```text",
            "inadimplencia_periodo = carteira * (inadimplencia * delta_DC / 100)",
            "```",
            "",
            "- Consequência prática: se a inadimplência informada for `10,00%` e o período tiver `184` dias corridos, a perda do período será `18,40%` da carteira inicial daquele período.",
            "- Isso é compatível com a planilha, mas é uma premissa forte. Um modo alternativo de perda total da vida ainda precisaria ser implementado.",
            "",
            "### 5. Taxas SEN e MEZZ",
            "",
            "- Para cotas pós-fixadas, a planilha soma economicamente a curva DI/Pré ao spread da classe:",
            "",
            "```text",
            "taxa_classe_aa = (1 + pre_di_interpolado) * (1 + spread_classe_aa) - 1",
            "```",
            "",
            "- Para cotas pré-fixadas, o app usa diretamente a taxa anual informada.",
            "- A taxa de cada período é transformada em FRA pela composição entre o ponto atual e o ponto anterior da curva, em base 252 dias úteis.",
            "- Os juros de cada classe são calculados sobre o PL da classe no início do período:",
            "",
            "```text",
            "juros_classe = pl_classe_inicial * ((1 + fra_classe) ^ (delta_DU / 252) - 1)",
            "```",
            "",
            "### 6. Principal, PMT e waterfall atual",
            "",
            "- A planilha tem pagamentos programados de SEN e MEZZ. No motor atual, o pagamento de cada classe é:",
            "",
            "```text",
            "PMT SEN = juros SEN + principal SEN programado",
            "PMT MEZZ = juros MEZZ + principal MEZZ programado",
            "```",
            "",
            "- A SUB é residual: não há principal nem juros programados para SUB na planilha.",
            "- A lógica atual é compatível com a planilha: os PMTs programados de SEN/MEZZ são calculados mesmo quando o fluxo líquido da carteira fica insuficiente.",
            "- Portanto, a trava de caixa está desligada por compatibilidade com o Excel.",
            "",
            "### 7. O que seria a trava de caixa",
            "",
            "- Com trava de caixa ligada, o modelo não pagaria mais aos cotistas do que o caixa disponível no período.",
            "- A ordem econômica esperada seria:",
            "",
            "```text",
            "1. custos e despesas",
            "2. juros SEN",
            "3. principal SEN",
            "4. juros MEZZ",
            "5. principal MEZZ",
            "6. residual SUB",
            "```",
            "",
            "- Se o caixa acabasse no item 3, por exemplo, MEZZ e SUB não receberiam naquele período.",
            "- Essa trava ainda não está implementada; quando for implementada, deve ficar em premissas avançadas e desligada por padrão para preservar a comparação com `Modelo_Publico.xlsm`.",
            "",
            "### 8. PL econômico e SUB residual",
            "",
            "- Depois de retorno da carteira, custos, perdas e PMTs, o PL econômico do veículo é:",
            "",
            "```text",
            "PL FIDC = carteira + fluxo_carteira - custos - inadimplencia - PMT SEN - PMT MEZZ",
            "```",
            "",
            "- O saldo econômico de SEN e MEZZ cai conforme o principal programado é amortizado.",
            "- A SUB residual corrente é:",
            "",
            "```text",
            "SUB residual = PL FIDC - PL SEN - PL MEZZ",
            "```",
            "",
            "- Se a SUB residual fica positiva, ela representa colchão subordinado disponível.",
            "- Se fica negativa, ela não é um saldo de cota para receber; é déficit econômico depois de consumir toda a SUB.",
            "- A timeline detalhada preserva também a coluna deslocada do workbook, porque a planilha passa a referenciar o residual da linha seguinte em `AO`. Os gráficos usam o residual corrente para evitar distorções como percentuais extremos.",
            "",
            "### 9. Revolvência e perda máxima sobre carteira originada",
            "",
            "- Quando a carteira é revolvente, o modelo estima quantas vezes o volume inicial gira dentro do prazo do FIDC:",
            "",
            "```text",
            "giro_estimado = prazo_total_fidc_anos * 12 / prazo_medio_recebiveis_meses",
            "carteira_originada = volume_inicial * giro_estimado",
            "```",
            "",
            "- Quando a carteira é estática, a carteira originada é apenas a compra inicial:",
            "",
            "```text",
            "carteira_originada = volume_inicial",
            "```",
            "",
            "- A perda máxima suportada roda uma simulação paralela com inadimplência igual a `0%` e compara o colchão final positivo da SUB com a carteira total originada:",
            "",
            "```text",
            "perda_maxima = max(SUB_final_sem_inadimplencia, 0) / carteira_originada",
            "```",
            "",
            "- Exemplo: prazo total de `3 anos`, prazo médio de recebíveis de `6 meses` e volume inicial de `R$ 750MM` geram giro de `6x` e carteira originada estimada de `R$ 4,5 bi`.",
            "",
            "### 10. Indicadores do resumo econômico",
            "",
            "- Retorno anualizado SEN: XIRR dos PMTs SEN contra a data de cada fluxo.",
            "- Retorno anualizado MEZZ: XIRR dos PMTs MEZZ contra a data de cada fluxo.",
            "- Retorno anualizado SUB: fica `N/D` quando a SUB não tem série de caixa válida; na planilha isso aparece como `#NUM!`.",
            "- Duration SEN: média ponderada dos pagamentos SEN descontados, usando `DU / 252`.",
            "- Pre DI na duration: taxa da curva no ponto correspondente ao duration arredondado para baixo em meses, como a planilha faz com `VLOOKUP`.",
            "- SUB inicial: volume inicial multiplicado pela proporção subordinada.",
            "",
            "### 11. Como interpretar os gráficos",
            "",
            "- `Evolução de Saldo das Cotas`: mostra SEN, MEZZ, SUB disponível e, quando existir, déficit econômico separado.",
            "- `Evolução Subordinação x Inadimplência Acumulada`: compara inadimplência acumulada, inadimplência do período e subordinação disponível.",
            "- Se a inadimplência acumulada sobe enquanto a subordinação disponível cai para zero, a estrutura está consumindo o colchão subordinado.",
            "- Se aparece déficit econômico, o cenário já ultrapassou a proteção da SUB dentro da mecânica atual.",
            "",
            "### 12. Limitações atuais",
            "",
            "- Ainda não há trava de caixa ligada no waterfall.",
            "- Ainda não há atraso acumulado, capitalização de juros em atraso ou gatilhos de liquidação.",
            "- Ainda não há amortização customizada por classe via interface avançada.",
            "- Ainda não há modo alternativo para inadimplência como perda total da vida da carteira.",
            "- Ainda não há fluxo programado para SUB; ela permanece residual para manter compatibilidade com a planilha.",
        ]
    )


def _build_step_by_step_markdown() -> str:
    return "\n".join(
        [
            "Este modelo simula uma carteira de FIDC e mostra como juros, custos, inadimplência, estrutura de cotas e revolvência afetam o colchão de proteção.",
            "",
            "- Volume da carteira é o valor em reais dos recebíveis comprados pelo fundo no início da simulação.",
            "- Taxa de Cessão é o deságio sobre o valor futuro do recebível; Taxa Mensal é a taxa efetiva usada pelo motor. A aba mostra a equivalência mensal e anual em base 252.",
            "- Prazo total do FIDC define até qual mês a simulação vai quando o cronograma mensal está selecionado.",
            "- Prazo médio dos recebíveis define o giro estimado da carteira. Com carteira revolvente, um FIDC de 36 meses e recebíveis de 6 meses gera giro estimado de 6x.",
            "- Cotas sênior têm prioridade de pagamento; MEZZ fica no meio; subordinada/SUB absorve perdas primeiro e recebe o residual econômico.",
            "- As regras de amortização indicam quando o principal de SEN/MEZZ começa a ser repago e se o pagamento é linear, bullet, inexistente ou compatível com a planilha.",
            "- As regras de juros indicam se os juros são pagos em cada período, após carência ou apenas no vencimento.",
            "- Subordinação é o tamanho do colchão de SUB disponível em relação ao PL econômico do fundo.",
            "- Perda máxima sobre carteira originada compara a SUB final sem inadimplência com o total estimado de recebíveis originados no período.",
            "- No gráfico de saldos, o eixo X mostra o mês desde o início do FIDC; isso deixa claro quando terminam carências e começam amortizações.",
            "- No gráfico de perda e subordinação, maior inadimplência acumulada com menor subordinação indica cenário mais pressionado.",
        ]
    )


def _validate_model_inputs(inputs) -> list[str]:
    errors: list[str] = []
    if not inputs.datas:
        errors.append("datas do fluxo ausentes em model_data.json")
    if not inputs.feriados:
        errors.append("lista de feriados vazia em model_data.json")
    return errors


def _validate_snapshot_curve(inputs) -> list[str]:
    errors: list[str] = []
    if not inputs.curva_du or not inputs.curva_cdi:
        errors.append("curva DI/Pre ausente em model_data.json")
    if len(inputs.curva_du) != len(inputs.curva_cdi):
        errors.append("curva_du e curva_cdi têm tamanhos diferentes")
    return errors


def _curve_comparison_metrics(inputs, selected_curve: _SelectedCurve) -> dict[str, float] | None:
    if selected_curve.source_label == CURVE_SOURCE_SNAPSHOT:
        return None
    if selected_curve.base_date != SNAPSHOT_CURVE_DATE:
        return None

    snapshot_by_du = {int(du): float(rate) for du, rate in zip(inputs.curva_du, inputs.curva_cdi)}
    b3_by_du = {int(du): float(rate) for du, rate in zip(selected_curve.curva_du, selected_curve.curva_taxa_aa)}
    common_du = sorted(set(snapshot_by_du) & set(b3_by_du))
    if not common_du:
        return None

    diffs = [b3_by_du[du] - snapshot_by_du[du] for du in common_du]
    abs_diffs = [abs(value) for value in diffs]
    return {
        "pontos_comuns": float(len(common_du)),
        "diferenca_media_bps": sum(abs_diffs) / len(abs_diffs) * 10_000.0,
        "diferenca_max_bps": max(abs_diffs) * 10_000.0,
    }


def _render_curve_source_info(inputs, selected_curve: _SelectedCurve) -> None:
    st.info(
        "\n".join(
            [
                f"Fonte da curva: {selected_curve.source_label}.",
                f"Curva {selected_curve.curve_code} em % a.a., base 252 dias úteis.",
                f"Data-base: {selected_curve.base_date:%d/%m/%Y}; pontos: {_format_number_br(selected_curve.point_count, 0)}; "
                f"DU inicial/final: {selected_curve.first_du or 'N/D'} / {selected_curve.last_du or 'N/D'}.",
            ]
        )
    )
    if selected_curve.source_label != CURVE_SOURCE_SNAPSHOT:
        st.caption(
            f"Arquivo B3: `{selected_curve.source_url}` | baixado em {selected_curve.retrieved_label} | "
            f"SHA-256: `{selected_curve.content_sha256[:12]}`"
        )
    else:
        st.caption(
            "Snapshot usado apenas como referência histórica: dados extraídos da aba `BMF` do `Modelo_Publico.xlsm` "
            f"com data-base {SNAPSHOT_CURVE_DATE:%d/%m/%Y}."
        )

    metrics = _curve_comparison_metrics(inputs, selected_curve)
    if metrics is not None:
        st.caption(
            "Comparação B3 x snapshot local na mesma data: "
            f"{_format_number_br(metrics['pontos_comuns'], 0)} DUs comuns; "
            f"diferença média absoluta {_format_number_br(metrics['diferenca_media_bps'], 2)} bps; "
            f"diferença máxima absoluta {_format_number_br(metrics['diferenca_max_bps'], 2)} bps."
        )
    elif selected_curve.source_label != CURVE_SOURCE_SNAPSHOT:
        st.caption(
            f"O snapshot local é de {SNAPSHOT_CURVE_DATE:%d/%m/%Y}; por isso a comparação ponto a ponto só é exibida "
            "quando a data B3 selecionada é a mesma."
        )


def _render_calendar_source_info(selected_calendar: _SelectedCalendar) -> None:
    official_years = ", ".join(str(year) for year in selected_calendar.official_years) or "N/D"
    projected_years = ", ".join(str(year) for year in selected_calendar.projected_years) or "N/D"
    st.info(
        "\n".join(
            [
                f"Calendário de dias úteis: {selected_calendar.source_label}.",
                f"Feriados considerados: {_format_number_br(selected_calendar.holiday_count, 0)}.",
                f"Anos oficiais B3: {official_years}; anos projetados: {projected_years}.",
                "Os DUs dos fluxos mensais são recalculados com esse calendário antes da interpolação da curva.",
            ]
        )
    )
    if selected_calendar.source_label == CALENDAR_SOURCE_B3_OFFICIAL:
        st.caption(
            f"Calendário B3 consultado em {selected_calendar.retrieved_label}; "
            f"SHA-256 `{selected_calendar.content_sha256[:12]}`. "
            "Anos ainda não publicados pela B3 são preenchidos por projeção explícita."
        )
    elif selected_calendar.source_label == CALENDAR_SOURCE_B3_PROJECTED:
        st.caption(
            "O calendário projetado combina os feriados originais da planilha com regras de mercado para anos futuros "
            "do fluxo, incluindo feriados nacionais, Carnaval, Sexta-feira Santa, Corpus Christi e datas sem pregão "
            "como 24/12 e 31/12."
        )
    else:
        last_holiday = selected_calendar.last_holiday.strftime("%d/%m/%Y") if selected_calendar.last_holiday else "N/D"
        st.warning(
            "O snapshot da planilha é útil para comparação histórica, mas a lista local termina em "
            f"{last_holiday}."
        )


def _render_curve_source_controls(
    inputs,
    selected_curve: _SelectedCurve | None = None,
    selected_calendar: _SelectedCalendar | None = None,
) -> None:
    with st.expander("Fonte da curva DI/Pré", expanded=False):
        st.selectbox(
            "Origem da curva de juros",
            CURVE_SOURCE_OPTIONS,
            key="modelo_curve_source",
            help=(
                "A fonte B3 usa o arquivo público TaxaSwap da Pesquisa por pregão. "
                "O snapshot local fica disponível apenas para comparação histórica com a planilha."
            ),
        )
        if st.session_state.get("modelo_curve_source") == CURVE_SOURCE_B3_DATE:
            st.date_input(
                "Data-base B3",
                key="modelo_b3_date",
                min_value=date(2000, 1, 1),
                max_value=date.today(),
                help="A data escolhida é exata. Se a B3 não tiver arquivo para essa data, o app mostra erro em vez de usar fallback.",
            )
        st.selectbox(
            "Metodologia de interpolação",
            INTERPOLATION_OPTIONS,
            key="modelo_interpolation_label",
            help=(
                "Flat Forward 252 preserva a composição financeira em dias úteis entre vértices. "
                "Spline fica disponível para comparar com a planilha original."
            ),
        )
        st.selectbox(
            "Calendário de dias úteis",
            CALENDAR_SOURCE_OPTIONS,
            key="modelo_calendar_source",
            help=(
                "O calendário oficial usa a página pública da B3 para anos publicados e projeção explícita para anos futuros. "
                "O snapshot fica disponível para comparação histórica."
            ),
        )
        if selected_curve is not None and selected_calendar is not None:
            st.markdown("##### Detalhes da fonte selecionada")
            _render_curve_source_info(inputs, selected_curve)
            _render_calendar_source_info(selected_calendar)


def _rate_mode_from_label(label: str) -> str:
    return RATE_MODE_PRE if label.startswith("Pré") else RATE_MODE_POST_CDI


def _build_balance_area_frame(frame: pd.DataFrame) -> pd.DataFrame:
    chart_frame = frame[["indice", "data", "pl_senior", "pl_mezz", "pl_sub_jr"]].copy()
    chart_frame["pl_sub_available"] = chart_frame["pl_sub_jr"].clip(lower=0.0)
    chart_frame["deficit_economico"] = chart_frame["pl_sub_jr"].where(chart_frame["pl_sub_jr"] < 0.0, 0.0)
    long_df = chart_frame.melt(
        id_vars=["indice", "data"],
        value_vars=["pl_senior", "pl_mezz", "pl_sub_available", "deficit_economico"],
        var_name="classe",
        value_name="valor",
    )
    label_map = {
        "pl_senior": "Sênior",
        "pl_mezz": "MEZZ",
        "pl_sub_available": "Subordinada/SUB disponível",
        "deficit_economico": "Déficit econômico",
    }
    long_df["classe"] = long_df["classe"].map(label_map)
    long_df["valor_milhoes"] = long_df["valor"] / 1_000_000.0
    long_df["valor_formatado"] = long_df["valor"].map(_format_brl)
    long_df["periodo"] = long_df["data"].dt.strftime("%d/%m/%Y")
    long_df["mes_fidc"] = long_df["indice"].map(lambda value: f"Mês {int(value)}")
    return long_df


def _available_subordination_pct(row: pd.Series) -> float | None:
    pl_fidc = row.get("pl_fidc")
    pl_sub_jr = row.get("pl_sub_jr")
    if pd.isna(pl_fidc) or pd.isna(pl_sub_jr) or pl_fidc <= 0:
        return None
    return max(float(pl_sub_jr), 0.0) / float(pl_fidc)


def _build_loss_area_frame(frame: pd.DataFrame, volume: float) -> pd.DataFrame:
    chart_frame = frame[["indice", "data", "carteira", "pl_fidc", "pl_sub_jr", "inadimplencia_despesa"]].copy()
    chart_frame["subordinacao_display"] = chart_frame.apply(_available_subordination_pct, axis=1)
    chart_frame["inadimplencia_acumulada"] = chart_frame["inadimplencia_despesa"].fillna(0.0).cumsum()
    chart_frame["perda_periodo_pct"] = chart_frame.apply(
        lambda row: row["inadimplencia_despesa"] / row["carteira"] if row["carteira"] else None,
        axis=1,
    )
    denominator = volume if volume else 1.0
    chart_frame["perda_acumulada_pct"] = chart_frame["inadimplencia_acumulada"] / denominator
    long_df = chart_frame.melt(
        id_vars=["indice", "data"],
        value_vars=["subordinacao_display", "perda_acumulada_pct", "perda_periodo_pct"],
        var_name="serie",
        value_name="valor",
    ).dropna(subset=["valor"])
    label_map = {
        "subordinacao_display": "Subordinação econômica disponível (SUB positiva/PL)",
        "perda_acumulada_pct": "Inadimplência acumulada (% do volume)",
        "perda_periodo_pct": "Inadimplência do período (% da carteira)",
    }
    long_df["serie"] = long_df["serie"].map(label_map)
    long_df["valor_pct"] = long_df["valor"] * 100.0
    long_df["valor_formatado"] = long_df["valor"].map(_format_percent)
    long_df["periodo"] = long_df["data"].dt.strftime("%d/%m/%Y")
    long_df["mes_fidc"] = long_df["indice"].map(lambda value: f"Mês {int(value)}")
    return long_df


def _area_money_chart(chart_df: pd.DataFrame) -> alt.Chart:
    base = alt.Chart(chart_df).encode(
        x=alt.X("indice:Q", title="Mês do FIDC", axis=alt.Axis(tickMinStep=1)),
        y=alt.Y(
            "valor_milhoes:Q",
            title="R$ milhões",
            stack="zero",
            axis=alt.Axis(labelExpr="replace(format(datum.value, '.1f'), '.', ',')"),
        ),
        color=alt.Color(
            "classe:N",
            title="Classe",
            scale=alt.Scale(range=["#2f6f9f", "#f28e2b", "#59a14f", "#b23b3b"]),
        ),
        order=alt.Order("classe:N", sort="ascending"),
        tooltip=[
            alt.Tooltip("mes_fidc:N", title="Mês"),
            alt.Tooltip("periodo:N", title="Período"),
            alt.Tooltip("classe:N", title="Classe"),
            alt.Tooltip("valor_formatado:N", title="Valor"),
        ],
    )
    return (base.mark_area(opacity=0.72, interpolate="monotone") + base.mark_line(size=1.1, interpolate="monotone")).properties(height=320)


def _area_percent_chart(chart_df: pd.DataFrame) -> alt.Chart:
    base = alt.Chart(chart_df).encode(
        x=alt.X("indice:Q", title="Mês do FIDC", axis=alt.Axis(tickMinStep=1)),
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
            alt.Tooltip("mes_fidc:N", title="Mês"),
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
        ("Retorno anualizado", _format_percent(kpis.xirr_mezz), "Classe MEZZ"),
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


def _render_revolvency_cards(metrics: _RevolvencyMetrics) -> None:
    cards = [
        ("Modo da carteira", metrics.portfolio_mode, "Originação"),
        ("Prazo médio recebíveis", f"{_format_number_br(metrics.prazo_medio_recebiveis_meses, 1)} meses", "Prazo de giro"),
        ("Giro estimado", f"{_format_number_br(metrics.giro_estimado, 2)}x", "Prazo FIDC / prazo médio"),
        ("Carteira originada", _format_brl(metrics.carteira_total_originada), "Base de comparação"),
        ("SUB final sem inadimplência", _format_brl(metrics.sub_final_sem_inadimplencia), "Colchão acumulado"),
        ("Perda máxima suportada", _format_percent(metrics.perda_maxima_sobre_originacao), "SUB final / carteira originada"),
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

    default_tx_cessao_am = DEFAULT_TX_CESSAO_AM
    default_tx_cessao_desagio = monthly_rate_to_cession_discount(default_tx_cessao_am)
    default_senior_pct = DEFAULT_PROP_SENIOR * 100.0
    default_mezz_pct = DEFAULT_PROP_MEZZ * 100.0
    default_sub_pct = DEFAULT_PROP_SUB * 100.0

    left = st.container()
    with left:
        with st.form("modelo-fidc-premissas"):
            st.markdown("##### Premissas da carteira")
            volume_text = _text_brl_input(
                "Volume da carteira (R$)",
                default=DEFAULT_VOLUME_CARTEIRA,
                key="modelo_volume",
                decimals=2,
                help_text="Valor total da carteira em reais. Não há escala implícita em milhões ou bilhões.",
            )
            taxa_cessao_input_mode = st.radio(
                "Entrada da taxa da carteira",
                [CESSION_INPUT_DISCOUNT, CESSION_INPUT_MONTHLY],
                index=1,
                horizontal=True,
                help=(
                    "Taxa de Cessão é o deságio sobre o valor futuro do recebível. "
                    "Taxa Mensal é a taxa efetiva cobrada ao mês, como no motor da planilha."
                ),
            )
            if taxa_cessao_input_mode == CESSION_INPUT_DISCOUNT:
                tx_cessao_desagio_text = _text_percent_input(
                    "Taxa de Cessão (%)",
                    default=default_tx_cessao_desagio * 100.0,
                    key="modelo_tx_cessao_desagio",
                    decimals=2,
                    help_text=(
                        "Deságio sobre o valor futuro. Ex.: comprar R$ 100 por R$ 95 equivale a 5,00% "
                        "de taxa de cessão e 5,26% de taxa mensal."
                    ),
                )
                tx_cessao_mensal_text = ""
            else:
                tx_cessao_mensal_text = _text_percent_input(
                    "Taxa Mensal (%)",
                    default=default_tx_cessao_am * 100.0,
                    key="modelo_tx_cessao_mensal",
                    decimals=2,
                    help_text="Taxa efetiva cobrada ao mês, exatamente a base usada pelo motor da planilha.",
                )
                tx_cessao_desagio_text = ""

            costs_a, costs_b = st.columns(2)
            with costs_a:
                custo_adm_text = _text_percent_input(
                    "Custo de administração e gestão (% a.a.)",
                    default=DEFAULT_CUSTO_ADM_AA * 100.0,
                    key="modelo_custo_adm_pct",
                    decimals=2,
                    help_text="Digite 0,35 para representar 0,35% ao ano. O motor converte internamente para 0,0035.",
                )
            with costs_b:
                custo_min_text = _text_brl_input(
                    "Custo mínimo de administração e gestão (R$/mês)",
                    default=DEFAULT_CUSTO_MIN_MENSAL,
                    key="modelo_custo_min",
                    decimals=2,
                    help_text="Piso mensal aplicado pela fórmula max(carteira * custo % a.a. / 12, custo mínimo).",
                )
            inadimplencia_text = _text_percent_input(
                "Inadimplência (% da carteira total)",
                default=DEFAULT_INADIMPLENCIA * 100.0,
                key="modelo_inadimplencia_pct",
                decimals=2,
                help_text="Na planilha de referência, a perda é proporcional aos dias corridos do período.",
            )

            st.markdown("##### Estrutura de PL")
            prop_a, prop_b, prop_c = st.columns(3)
            with prop_a:
                senior_pct_text = _text_percent_input(
                    "PL sênior/SEN (%)",
                    default=default_senior_pct,
                    key="modelo_prop_senior",
                    decimals=1,
                )
            with prop_b:
                mezz_pct_text = _text_percent_input(
                    "PL mezanino/MEZZ (%)",
                    default=default_mezz_pct,
                    key="modelo_prop_mezz",
                    decimals=1,
                )
            with prop_c:
                sub_pct_text = _text_percent_input(
                    "PL subordinado/SUB (%)",
                    default=default_sub_pct,
                    key="modelo_prop_sub",
                    decimals=1,
                )
            st.caption("As proporções SEN, MEZZ e SUB devem somar 100,00%.")

            st.markdown("##### Remuneração das cotas")
            senior_mode_label = st.selectbox(
                "Remuneração cota sênior/SEN",
                ["Pós-fixada: spread sobre CDI", "Pré-fixada: taxa % a.a."],
                help="Pós-fixada replica a planilha: (1 + curva DI/Pré) * (1 + spread) - 1. Pré-fixada usa diretamente a taxa anual informada.",
            )
            senior_rate_label = (
                "Spread cota SEN sobre CDI (% a.a.)"
                if _rate_mode_from_label(senior_mode_label) == RATE_MODE_POST_CDI
                else "Taxa pré-fixada cota SEN (% a.a.)"
            )
            senior_rate_text = _text_percent_input(
                senior_rate_label,
                default=DEFAULT_TAXA_SENIOR * 100.0,
                key="modelo_taxa_senior",
                decimals=2,
            )

            mezz_mode_label = st.selectbox(
                "Remuneração cota mezanino/MEZZ",
                ["Pós-fixada: spread sobre CDI", "Pré-fixada: taxa % a.a."],
                help="Pós-fixada replica a planilha para a cota mezanino; pré-fixada usa taxa anual efetiva.",
            )
            mezz_rate_label = (
                "Spread cota MEZZ sobre CDI (% a.a.)"
                if _rate_mode_from_label(mezz_mode_label) == RATE_MODE_POST_CDI
                else "Taxa pré-fixada cota MEZZ (% a.a.)"
            )
            mezz_rate_text = _text_percent_input(
                mezz_rate_label,
                default=DEFAULT_TAXA_MEZZ * 100.0,
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
                sub_rate_text = _text_percent_input(
                    (
                        "Spread-alvo cota SUB sobre CDI (% a.a.)"
                        if sub_mode_label.startswith("Pós")
                        else "Taxa-alvo pré-fixada cota SUB (% a.a.)"
                    ),
                    default=0.0,
                    key="modelo_taxa_sub",
                    decimals=2,
                )

            with st.expander("Premissas avançadas de prazo, revolvência e waterfall", expanded=False):
                st.markdown("##### Prazo e originação")
                date_schedule_label = st.selectbox(
                    "Cronograma do fluxo",
                    [DATE_SCHEDULE_WORKBOOK, DATE_SCHEDULE_MONTHLY],
                    index=1,
                    help=(
                        "O modo compatível mantém a grade de datas extraída da planilha. "
                        "O modo mensal gera novas competências até o prazo total informado."
                    ),
                )
                term_a, term_b, term_c = st.columns(3)
                with term_a:
                    prazo_fidc_text = _text_number_input(
                        "Prazo total do FIDC (anos)",
                        default=DEFAULT_PRAZO_ANOS,
                        key="modelo_prazo_fidc_anos",
                        decimals=1,
                    )
                with term_b:
                    prazo_recebiveis_text = _text_number_input(
                        "Prazo médio dos recebíveis (meses)",
                        default=DEFAULT_PRAZO_RECEBIVEIS_MESES,
                        key="modelo_prazo_recebiveis_meses",
                        decimals=1,
                    )
                with term_c:
                    portfolio_mode_label = st.selectbox(
                        "Originação da carteira",
                        [PORTFOLIO_MODE_REVOLVING, PORTFOLIO_MODE_STATIC],
                        help=(
                            "No modo revolvente, o caixa reciclado recompra recebíveis e a carteira total originada "
                            "é estimada pelo giro do prazo médio."
                        ),
                    )

                st.markdown("##### Cotas SEN e MEZZ")
                st.caption(
                    "O modo compatível com a planilha preserva o cronograma original. "
                    "Os demais modos alteram os pagamentos programados no motor."
                )
                senior_cfg_a, senior_cfg_b = st.columns(2)
                with senior_cfg_a:
                    prazo_senior_text = _text_number_input(
                        "Prazo cota SEN (anos)",
                        default=DEFAULT_PRAZO_ANOS,
                        key="modelo_prazo_senior_anos",
                        decimals=1,
                    )
                    senior_amort_label = st.selectbox(
                        "Amortização principal SEN",
                        list(AMORTIZATION_LABELS),
                        index=1,
                        key="modelo_amort_senior",
                    )
                    senior_start_text = _text_number_input(
                        "Carência principal SEN (meses)",
                        default=DEFAULT_CARENCIA_PRINCIPAL_MESES,
                        key="modelo_inicio_amort_senior",
                        decimals=0,
                    )
                with senior_cfg_b:
                    prazo_mezz_text = _text_number_input(
                        "Prazo cota MEZZ (anos)",
                        default=DEFAULT_PRAZO_ANOS,
                        key="modelo_prazo_mezz_anos",
                        decimals=1,
                    )
                    mezz_amort_label = st.selectbox(
                        "Amortização principal MEZZ",
                        list(AMORTIZATION_LABELS),
                        index=1,
                        key="modelo_amort_mezz",
                    )
                    mezz_start_text = _text_number_input(
                        "Carência principal MEZZ (meses)",
                        default=DEFAULT_CARENCIA_PRINCIPAL_MESES,
                        key="modelo_inicio_amort_mezz",
                        decimals=0,
                    )

                interest_a, interest_b, interest_c = st.columns(3)
                with interest_a:
                    senior_interest_label = st.selectbox(
                        "Pagamento de juros SEN",
                        list(INTEREST_LABELS),
                        key="modelo_juros_senior",
                    )
                with interest_b:
                    mezz_interest_label = st.selectbox(
                        "Pagamento de juros MEZZ",
                        list(INTEREST_LABELS),
                        key="modelo_juros_mezz",
                    )
                with interest_c:
                    prazo_sub_text = _text_number_input(
                        "Prazo cota SUB (anos)",
                        default=DEFAULT_PRAZO_ANOS,
                        key="modelo_prazo_sub_anos",
                        decimals=1,
                    )
                st.caption("A SUB segue residual nesta etapa; o prazo da SUB entra na documentação e na análise econômica.")
            submitted = st.form_submit_button(
                "Rodar simulação",
                width="stretch",
                on_click=_normalize_model_input_values,
            )

    try:
        volume = _parse_br_number(volume_text, field_name="Volume da carteira (R$)")
        if taxa_cessao_input_mode == CESSION_INPUT_DISCOUNT:
            tx_cessao_desagio = _parse_br_number(tx_cessao_desagio_text, field_name="Taxa de Cessão (%)") / 100.0
            tx_cessao_am = cession_discount_to_monthly_rate(tx_cessao_desagio)
        else:
            tx_cessao_am = _parse_br_number(tx_cessao_mensal_text, field_name="Taxa Mensal (%)") / 100.0
            tx_cessao_desagio = monthly_rate_to_cession_discount(tx_cessao_am)
        tx_cessao_aa_equivalente = monthly_to_annual_252_rate(tx_cessao_am)
        custo_adm_aa = _parse_br_number(custo_adm_text, field_name="Custo de administração e gestão (% a.a.)") / 100.0
        custo_min = _parse_br_number(custo_min_text, field_name="Custo mínimo de administração e gestão (R$/mês)")
        inadimplencia = _parse_br_number(inadimplencia_text, field_name="Inadimplência (% da carteira total)") / 100.0
        proporcao_senior = _parse_br_number(senior_pct_text, field_name="PL sênior/SEN (%)") / 100.0
        proporcao_mezz = _parse_br_number(mezz_pct_text, field_name="PL mezanino/MEZZ (%)") / 100.0
        proporcao_sub = _parse_br_number(sub_pct_text, field_name="PL subordinado/SUB (%)") / 100.0
        taxa_senior = _parse_br_number(senior_rate_text, field_name=senior_rate_label) / 100.0
        taxa_mezz = _parse_br_number(mezz_rate_text, field_name=mezz_rate_label) / 100.0
        taxa_sub = _parse_br_number(sub_rate_text, field_name="Taxa-alvo cota SUB (% a.a.)") / 100.0
        prazo_fidc_anos = _parse_br_number(prazo_fidc_text, field_name="Prazo total do FIDC (anos)")
        prazo_medio_recebiveis_meses = _parse_br_number(
            prazo_recebiveis_text,
            field_name="Prazo médio dos recebíveis (meses)",
        )
        prazo_senior_anos = _parse_br_number(prazo_senior_text, field_name="Prazo cota SEN (anos)")
        prazo_mezz_anos = _parse_br_number(prazo_mezz_text, field_name="Prazo cota MEZZ (anos)")
        prazo_sub_anos = _parse_br_number(prazo_sub_text, field_name="Prazo cota SUB (anos)")
        inicio_amortizacao_senior_meses = int(
            round(_parse_br_number(senior_start_text, field_name="Carência principal SEN (meses)"))
        )
        inicio_amortizacao_mezz_meses = int(
            round(_parse_br_number(mezz_start_text, field_name="Carência principal MEZZ (meses)"))
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    if volume <= 0:
        st.error("O volume da carteira deve ser maior que zero.")
        return
    if prazo_fidc_anos <= 0 or prazo_medio_recebiveis_meses <= 0:
        st.error("O prazo total do FIDC e o prazo médio dos recebíveis devem ser maiores que zero.")
        return
    if min(prazo_senior_anos, prazo_mezz_anos, prazo_sub_anos) <= 0:
        st.error("Os prazos das cotas devem ser maiores que zero.")
        return
    if min(inicio_amortizacao_senior_meses, inicio_amortizacao_mezz_meses) < 0:
        st.error("A carência de principal não pode ser negativa.")
        return

    prop_total = proporcao_senior + proporcao_mezz + proporcao_sub
    if abs(prop_total - 1.0) > 0.0001:
        st.error(f"As proporções de PL precisam somar 100,00%. Soma atual: {_format_percent(prop_total)}.")
        return

    simulation_dates = _build_simulation_dates(inputs, date_schedule_label, prazo_fidc_anos)

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
        prazo_fidc_anos=prazo_fidc_anos,
        prazo_medio_recebiveis_meses=prazo_medio_recebiveis_meses,
        carteira_revolvente=portfolio_mode_label == PORTFOLIO_MODE_REVOLVING,
        prazo_senior_anos=prazo_senior_anos,
        prazo_mezz_anos=prazo_mezz_anos,
        prazo_sub_jr_anos=prazo_sub_anos,
        amortizacao_senior=AMORTIZATION_LABELS[senior_amort_label],
        amortizacao_mezz=AMORTIZATION_LABELS[mezz_amort_label],
        juros_senior=INTEREST_LABELS[senior_interest_label],
        juros_mezz=INTEREST_LABELS[mezz_interest_label],
        inicio_amortizacao_senior_meses=inicio_amortizacao_senior_meses,
        inicio_amortizacao_mezz_meses=inicio_amortizacao_mezz_meses,
    )

    st.caption(
        "Equivalência da taxa da carteira: "
        f"Taxa de Cessão {_format_percent(tx_cessao_desagio)} | "
        f"Taxa Mensal {_format_percent(tx_cessao_am)} | "
        f"Taxa anual base 252 {_format_percent(tx_cessao_aa_equivalente)}."
    )

    curve_source_label = _ensure_session_option("modelo_curve_source", CURVE_SOURCE_OPTIONS)
    selected_b3_date = _ensure_session_date("modelo_b3_date", date.today() - timedelta(days=1))
    interpolation_label = _ensure_session_option("modelo_interpolation_label", INTERPOLATION_OPTIONS)
    interpolation_method = _interpolation_method_from_label(interpolation_label)
    calendar_source_label = _ensure_session_option("modelo_calendar_source", CALENDAR_SOURCE_OPTIONS)

    try:
        if curve_source_label == CURVE_SOURCE_SNAPSHOT:
            snapshot_errors = _validate_snapshot_curve(inputs)
            if snapshot_errors:
                st.error("Snapshot local da curva incompleto: " + "; ".join(snapshot_errors) + ".")
                _render_curve_source_controls(inputs)
                return
            selected_curve = _selected_curve_from_snapshot(inputs)
        elif curve_source_label == CURVE_SOURCE_B3_DATE:
            with st.spinner("Consultando curva TaxaSwap na B3..."):
                b3_snapshot = _load_b3_curve_for_date(selected_b3_date.isoformat(), DEFAULT_TAXASWAP_CURVE_CODE)
            selected_curve = _selected_curve_from_b3(b3_snapshot, curve_source_label)
        else:
            with st.spinner("Localizando último pregão TaxaSwap disponível na B3..."):
                b3_snapshot = _load_latest_b3_curve(date.today().isoformat(), DEFAULT_TAXASWAP_CURVE_CODE)
            selected_curve = _selected_curve_from_b3(b3_snapshot, curve_source_label)
    except B3CurveError as exc:
        st.error(f"Não foi possível carregar a curva B3: {exc}")
        st.warning("Selecione o snapshot local da planilha apenas se quiser rodar uma comparação histórica sem fonte externa.")
        _render_curve_source_controls(inputs)
        return

    try:
        if calendar_source_label == CALENDAR_SOURCE_B3_OFFICIAL:
            with st.spinner("Consultando calendário de negociação da B3..."):
                b3_calendar_snapshot = _load_b3_calendar_snapshot(simulation_dates[0].year, simulation_dates[-1].year)
            selected_calendar = _selected_calendar(
                inputs,
                calendar_source_label,
                b3_calendar_snapshot,
                datas=simulation_dates,
            )
        else:
            selected_calendar = _selected_calendar(inputs, calendar_source_label, datas=simulation_dates)
    except B3CalendarError as exc:
        st.error(f"Não foi possível carregar o calendário B3: {exc}")
        st.warning("Selecione o calendário projetado se quiser rodar a simulação sem consultar a página pública da B3.")
        _render_curve_source_controls(inputs, selected_curve)
        return

    if not sub_mode_label.startswith("Residual"):
        st.warning(
            "A taxa da SUB está registrada como taxa-alvo informativa. O workbook de referência não possui pagamento "
            "programado da SUB; por isso, a paridade do waterfall mantém a SUB como residual."
        )

    simulation_signature = (
        selected_curve.cache_key,
        selected_calendar.cache_key,
        interpolation_method,
        tuple(dt.isoformat() for dt in simulation_dates),
        premissas,
    )
    if (
        not submitted
        and st.session_state.get("modelo_fidc_signature") == simulation_signature
        and "modelo_fidc_periods" in st.session_state
    ):
        results = st.session_state["modelo_fidc_periods"]
        kpis = st.session_state["modelo_fidc_kpis"]
    else:
        results = build_flow(
            simulation_dates,
            selected_calendar.feriados,
            selected_curve.curva_du,
            selected_curve.curva_taxa_aa,
            premissas,
            interpolation_method=interpolation_method,
        )
        kpis = build_kpis(results)
        st.session_state["modelo_fidc_signature"] = simulation_signature
        st.session_state["modelo_fidc_periods"] = results
        st.session_state["modelo_fidc_kpis"] = kpis

    if not results:
        st.info("Sem datas suficientes para montar o fluxo.")
        return

    zero_default_results = build_flow(
        simulation_dates,
        selected_calendar.feriados,
        selected_curve.curva_du,
        selected_curve.curva_taxa_aa,
        replace(premissas, inadimplencia=0.0),
        interpolation_method=interpolation_method,
    )
    revolvency_metrics = _build_revolvency_metrics(
        premissas=premissas,
        zero_default_results=zero_default_results,
        portfolio_mode=portfolio_mode_label,
    )

    frame = _build_dataframe(results)
    export_frame = _build_export_dataframe(frame)
    display_frame = _build_display_dataframe(export_frame)

    st.markdown('<div class="fidc-model-section-title">Resumo econômico</div>', unsafe_allow_html=True)
    _render_model_kpi_cards(kpis, results)

    st.markdown('<div class="fidc-model-section-title">Perda máxima sobre carteira originada</div>', unsafe_allow_html=True)
    _render_revolvency_cards(revolvency_metrics)

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.markdown('<div class="fidc-model-section-title">Evolução de Saldo das Cotas</div>', unsafe_allow_html=True)
        st.altair_chart(_area_money_chart(_build_balance_area_frame(frame)), width="stretch")
    with chart_right:
        st.markdown(
            '<div class="fidc-model-section-title">Evolução Subordinação x Inadimplência Acumulada</div>',
            unsafe_allow_html=True,
        )
        st.altair_chart(_area_percent_chart(_build_loss_area_frame(frame, premissas.volume)), width="stretch")

    memory_df = pd.DataFrame(
        [
            {
                "Indicador": "Fluxo econômico da carteira",
                "Fórmula": "carteira * ((1 + tx_cessao_am) ^ (delta_du / 21) - 1)",
                "Observação": "Replica Qx no Fluxo Base. A Taxa de Cessão é convertida para Taxa Mensal antes do cálculo.",
            },
            {
                "Indicador": "De-para da Taxa de Cessão",
                "Fórmula": "tx_cessao_am = 1 / (1 - taxa_cessao) - 1",
                "Observação": "Ex.: comprar R$ 100 de valor futuro por R$ 95 implica taxa de cessão de 5,00% e taxa mensal de 5,26%.",
            },
            {
                "Indicador": "Conversão anual base 252",
                "Fórmula": "tx_cessao_aa_252 = (1 + tx_cessao_am) ^ (252 / 21) - 1",
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
                "Indicador": "Juros sênior/MEZZ",
                "Fórmula": "pós: (1 + curva DI/Pré) * (1 + spread) - 1; pré: taxa anual informada",
                "Observação": (
                    f"O FRA de cada período usa base 252 DU. Fonte selecionada: {selected_curve.source_label} "
                    f"({selected_curve.base_date:%d/%m/%Y}); interpolação: {interpolation_label}."
                ),
            },
            {
                "Indicador": "Dias úteis do fluxo",
                "Fórmula": "DU = dias úteis entre a data inicial e a data do fluxo, descontando fins de semana e feriados",
                "Observação": f"Calendário selecionado: {selected_calendar.source_label}.",
            },
            {
                "Indicador": "Proporções de PL",
                "Fórmula": "PL sênior + PL MEZZ + PL SUB = 100%",
                "Observação": "A SUB agora é uma premissa explícita na interface; o motor bloqueia soma diferente de 100%.",
            },
            {
                "Indicador": "Carteira originada estimada",
                "Fórmula": "revolvente: volume * (prazo_total_anos * 12 / prazo_medio_recebiveis_meses); estática: volume",
                "Observação": "Usada para comparar o colchão final da SUB contra o total de recebíveis originados no período do FIDC.",
            },
            {
                "Indicador": "Perda máxima suportada",
                "Fórmula": "max(SUB final com inadimplência 0%, 0) / carteira total originada estimada",
                "Observação": "Esta é uma simulação paralela sem inadimplência para medir quanto colchão econômico seria acumulado antes das perdas.",
            },
            {
                "Indicador": "Júnior residual / subordinação econômica",
                "Fórmula": "Residual econômico = PL econômico do veículo - PL sênior - PL MEZZ; subordinação disponível = max(residual, 0) / PL positivo",
                "Observação": (
                    "A planilha não remunera a SUB programaticamente; taxas da SUB ficam como premissa-alvo informativa. "
                    "A timeline preserva a coluna deslocada do workbook para conferência, mas os gráficos usam o residual corrente."
                ),
            },
        ]
    )
    with st.expander("Memória de cálculo", expanded=False):
        st.dataframe(memory_df, width="stretch", hide_index=True)

    st.markdown('<div class="fidc-model-section-title">Timeline detalhada</div>', unsafe_allow_html=True)
    st.dataframe(display_frame, width="stretch", hide_index=True)

    csv = export_frame.to_csv(index=False).encode("utf-8")
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_frame.to_excel(writer, index=False, sheet_name="timeline")
        _build_kpi_export_dataframe(kpis).to_excel(writer, index=False, sheet_name="kpis")
        _build_curve_source_dataframe(selected_curve, selected_calendar, interpolation_label).to_excel(
            writer,
            index=False,
            sheet_name="fonte_curva",
        )
        _build_revolvency_export_dataframe(revolvency_metrics).to_excel(
            writer,
            index=False,
            sheet_name="perda_maxima",
        )
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

    st.markdown('<div class="fidc-model-section-title">Fonte da curva DI/Pré</div>', unsafe_allow_html=True)
    _render_curve_source_controls(inputs, selected_curve, selected_calendar)

    guide_left, guide_right = st.columns(2)
    with guide_left:
        with st.expander("Passo a passo", expanded=False):
            st.markdown(_build_step_by_step_markdown())
    with guide_right:
        with st.expander("Mecânica completa da aba", expanded=False):
            st.markdown(
                _build_workbook_mechanics_markdown(
                    selected_curve=selected_curve,
                    selected_calendar=selected_calendar,
                    interpolation_label=interpolation_label,
                    taxa_cessao_input_mode=taxa_cessao_input_mode,
                )
            )
