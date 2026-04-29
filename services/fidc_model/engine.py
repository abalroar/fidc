from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable, Sequence

from .calendar import build_day_counts, build_period_indexes
from .contracts import ModelKpis, PeriodResult, Premissas
from .curves import INTERPOLATION_METHOD_SPLINE, interpolate_curve
from .metrics import calculate_duration_years, lookup_pre_di_duration, xirr


RATE_MODE_POST_CDI = "pos_cdi"
RATE_MODE_PRE = "pre"
AMORTIZATION_MODE_WORKBOOK = "workbook"
AMORTIZATION_MODE_LINEAR = "linear"
AMORTIZATION_MODE_BULLET = "bullet"
AMORTIZATION_MODE_NONE = "none"
INTEREST_PAYMENT_MODE_PERIODIC = "periodic"
INTEREST_PAYMENT_MODE_AFTER_GRACE = "after_grace"
INTEREST_PAYMENT_MODE_BULLET = "bullet"


def annual_252_to_monthly_rate(rate_aa: float) -> float:
    """Convert an annual effective rate on a 252-business-day basis to 21 DU/month."""

    return (1.0 + rate_aa) ** (21.0 / 252.0) - 1.0


def monthly_to_annual_252_rate(rate_am: float) -> float:
    """Convert an effective monthly rate, using 21 DU/month, to annual 252 DU."""

    return (1.0 + rate_am) ** (252.0 / 21.0) - 1.0


def _class_annual_rate(base_rate: float, class_rate: float, mode: str) -> float:
    if mode == RATE_MODE_PRE:
        return class_rate
    if mode == RATE_MODE_POST_CDI:
        return (1.0 + base_rate) * (1.0 + class_rate) - 1.0
    raise ValueError(f"Tipo de taxa de cota inválido: {mode}")


def _months_between(start: datetime, current: datetime) -> int:
    return (current.year - start.year) * 12 + (current.month - start.month)


def _term_months(term_years: float | None, fallback_months: int) -> int:
    if term_years is None:
        return fallback_months
    return max(1, round(float(term_years) * 12.0))


def _principal_schedule(
    datas: Sequence[datetime],
    initial_pl: float,
    *,
    mode: str = AMORTIZATION_MODE_WORKBOOK,
    start_month: int = 25,
    term_months: int | None = None,
) -> list[float]:
    period_count = len(datas)
    schedule = [0.0] * period_count
    if period_count:
        schedule[0] = -initial_pl
    if period_count <= 1 or initial_pl <= 0:
        return schedule

    if mode == AMORTIZATION_MODE_NONE:
        return schedule

    month_deltas = [_months_between(datas[0], dt) for dt in datas]
    last_month = month_deltas[-1]
    final_month = term_months if term_months is not None else last_month

    if mode == AMORTIZATION_MODE_WORKBOOK:
        remaining = initial_pl
        for index in range(5, period_count):
            amount = min(initial_pl / 12.0, remaining)
            schedule[index] = amount
            remaining -= amount
            if remaining <= 1e-9:
                break
        return schedule

    if mode == AMORTIZATION_MODE_BULLET:
        payment_index = _first_index_at_or_after(month_deltas, final_month)
        schedule[payment_index] = initial_pl
        return schedule

    if mode == AMORTIZATION_MODE_LINEAR:
        eligible_indexes = [
            index
            for index, month_delta in enumerate(month_deltas)
            if index > 0 and month_delta >= start_month and month_delta <= final_month
        ]
        if not eligible_indexes:
            eligible_indexes = [_first_index_at_or_after(month_deltas, min(start_month, final_month))]
        amount = initial_pl / len(eligible_indexes)
        for index in eligible_indexes:
            schedule[index] = amount
        return schedule

    raise ValueError(f"Modo de amortização inválido: {mode}")


def _first_index_at_or_after(month_deltas: Sequence[int], target_month: int) -> int:
    for index, month_delta in enumerate(month_deltas):
        if index > 0 and month_delta >= target_month:
            return index
    return len(month_deltas) - 1


def _interest_payment(
    interest: float,
    accrued_interest: float,
    *,
    mode: str,
    month_delta: int,
    start_month: int,
    term_month: int,
    is_last_period: bool,
) -> tuple[float, float]:
    if mode == INTEREST_PAYMENT_MODE_PERIODIC:
        return interest, accrued_interest
    if mode == INTEREST_PAYMENT_MODE_AFTER_GRACE:
        if month_delta < start_month and not is_last_period:
            return 0.0, accrued_interest + interest
        return accrued_interest + interest, 0.0
    if mode == INTEREST_PAYMENT_MODE_BULLET:
        if month_delta >= term_month or is_last_period:
            return accrued_interest + interest, 0.0
        return 0.0, accrued_interest + interest
    raise ValueError(f"Modo de pagamento de juros inválido: {mode}")


def _period_indexes_for_dates(datas: Sequence[datetime]) -> list[int]:
    month_deltas = [_months_between(datas[0], dt) for dt in datas]
    workbook_prefix = [0, 6, 12, 18, 24]
    if len(month_deltas) >= len(workbook_prefix) and month_deltas[: len(workbook_prefix)] == workbook_prefix:
        return build_period_indexes(len(datas))
    return month_deltas


def build_flow(
    datas: Sequence[datetime],
    feriados: Iterable[datetime],
    curva_du: Sequence[float],
    curva_cdi: Sequence[float],
    premissas: Premissas,
    interpolation_method: str = INTERPOLATION_METHOD_SPLINE,
) -> list[PeriodResult]:
    if not datas:
        return []
    if not curva_du or not curva_cdi:
        raise ValueError("Curva DI/Pre vazia: o modelo exige uma curva válida da fonte selecionada.")

    period_indexes = _period_indexes_for_dates(datas)
    dc, du = build_day_counts(datas, feriados)
    month_deltas = [_months_between(datas[0], dt) for dt in datas]

    zero_pre_di: list[float | None] = [None]
    for du_value in du[1:]:
        zero_pre_di.append(interpolate_curve(float(du_value), curva_du, curva_cdi, method=interpolation_method))

    taxa_senior: list[float | None] = [None]
    taxa_mezz: list[float | None] = [None]
    for index in range(1, len(datas)):
        base_rate = zero_pre_di[index]
        assert base_rate is not None
        taxa_senior.append(_class_annual_rate(base_rate, premissas.taxa_senior, premissas.tipo_taxa_senior))
        taxa_mezz.append(_class_annual_rate(base_rate, premissas.taxa_mezz, premissas.tipo_taxa_mezz))

    fra_senior: list[float | None] = [None]
    fra_mezz: list[float | None] = [None]
    for index in range(1, len(datas)):
        if index == 1:
            fra_senior.append(taxa_senior[index])
            fra_mezz.append(taxa_mezz[index])
            continue
        if du[index] == du[index - 1]:
            fra_senior.append(taxa_senior[index])
            fra_mezz.append(taxa_mezz[index])
            continue
        current_senior = taxa_senior[index]
        previous_senior = taxa_senior[index - 1]
        current_mezz = taxa_mezz[index]
        previous_mezz = taxa_mezz[index - 1]
        if previous_senior is None or previous_mezz is None or current_senior is None or current_mezz is None:
            fra_senior.append(None)
            fra_mezz.append(None)
            continue
        fra_senior.append(
            ((1.0 + current_senior) ** (du[index] / 252.0) / (1.0 + previous_senior) ** (du[index - 1] / 252.0))
            ** (252.0 / (du[index] - du[index - 1]))
            - 1.0
        )
        fra_mezz.append(
            ((1.0 + current_mezz) ** (du[index] / 252.0) / (1.0 + previous_mezz) ** (du[index - 1] / 252.0))
            ** (252.0 / (du[index] - du[index - 1]))
            - 1.0
        )

    pl_senior_initial = premissas.volume * premissas.proporcao_senior
    pl_mezz_initial = premissas.volume * premissas.proporcao_mezz
    if premissas.proporcao_subordinada is None:
        pl_sub_initial = premissas.volume - pl_senior_initial - pl_mezz_initial
    else:
        pl_sub_initial = premissas.volume * premissas.proporcao_subordinada

    fallback_term_months = month_deltas[-1] if month_deltas else 0
    senior_term_months = _term_months(premissas.prazo_senior_anos or premissas.prazo_fidc_anos, fallback_term_months)
    mezz_term_months = _term_months(premissas.prazo_mezz_anos or premissas.prazo_fidc_anos, fallback_term_months)
    principal_senior = _principal_schedule(
        datas,
        pl_senior_initial,
        mode=premissas.amortizacao_senior,
        start_month=premissas.inicio_amortizacao_senior_meses,
        term_months=senior_term_months,
    )
    principal_mezz = _principal_schedule(
        datas,
        pl_mezz_initial,
        mode=premissas.amortizacao_mezz,
        start_month=premissas.inicio_amortizacao_mezz_meses,
        term_months=mezz_term_months,
    )

    periods: list[PeriodResult] = []
    pl_senior_atual = pl_senior_initial
    pl_mezz_atual = pl_mezz_initial
    pl_fidc_atual = premissas.volume
    accrued_interest_senior = 0.0
    accrued_interest_mezz = 0.0

    for index, dt in enumerate(datas):
        if index == 0:
            periods.append(
                PeriodResult(
                    indice=period_indexes[index],
                    data=dt,
                    dc=dc[index],
                    du=du[index],
                    delta_dc=0,
                    delta_du=0,
                    pre_di=None,
                    taxa_senior=None,
                    fra_senior=None,
                    taxa_mezz=None,
                    fra_mezz=None,
                    carteira=premissas.volume,
                    fluxo_carteira=0.0,
                    pl_fidc=premissas.volume,
                    custos_adm=0.0,
                    inadimplencia_despesa=0.0,
                    principal_senior=principal_senior[index],
                    juros_senior=0.0,
                    pmt_senior=principal_senior[index],
                    vp_pmt_senior=0.0,
                    pl_senior=pl_senior_atual,
                    fluxo_remanescente=0.0,
                    principal_mezz=principal_mezz[index],
                    juros_mezz=0.0,
                    pmt_mezz=principal_mezz[index],
                    pl_mezz=pl_mezz_atual,
                    fluxo_remanescente_mezz=0.0,
                    principal_sub_jr=0.0,
                    juros_sub_jr=0.0,
                    pmt_sub_jr=0.0,
                    pl_sub_jr=pl_sub_initial,
                    subordinacao_pct=pl_sub_initial / premissas.volume if premissas.volume else None,
                    pl_sub_jr_modelo=None,
                    subordinacao_pct_modelo=None,
                )
            )
            continue

        delta_du = du[index] - du[index - 1]
        delta_dc = dc[index] - dc[index - 1]
        carteira = pl_fidc_atual
        fluxo_carteira = carteira * ((1.0 + premissas.tx_cessao_am) ** (delta_du / 21.0) - 1.0)
        custos_adm = max(carteira * premissas.custo_adm_aa / 12.0, premissas.custo_min)
        inadimplencia_despesa = carteira * (premissas.inadimplencia * (delta_dc / 100.0))

        fra_senior_period = fra_senior[index] or 0.0
        fra_mezz_period = fra_mezz[index] or 0.0
        juros_senior_bruto = pl_senior_atual * ((1.0 + fra_senior_period) ** (delta_du / 252.0) - 1.0)
        juros_mezz_bruto = pl_mezz_atual * ((1.0 + fra_mezz_period) ** (delta_du / 252.0) - 1.0)
        juros_senior, accrued_interest_senior = _interest_payment(
            juros_senior_bruto,
            accrued_interest_senior,
            mode=premissas.juros_senior,
            month_delta=month_deltas[index],
            start_month=premissas.inicio_amortizacao_senior_meses,
            term_month=senior_term_months,
            is_last_period=index == len(datas) - 1,
        )
        juros_mezz, accrued_interest_mezz = _interest_payment(
            juros_mezz_bruto,
            accrued_interest_mezz,
            mode=premissas.juros_mezz,
            month_delta=month_deltas[index],
            start_month=premissas.inicio_amortizacao_mezz_meses,
            term_month=mezz_term_months,
            is_last_period=index == len(datas) - 1,
        )

        principal_senior_period = max(principal_senior[index], 0.0)
        principal_mezz_period = max(principal_mezz[index], 0.0)
        pmt_senior = juros_senior + principal_senior_period
        pmt_mezz = juros_mezz + principal_mezz_period

        pl_senior_atual -= principal_senior_period
        pl_mezz_atual -= principal_mezz_period

        fluxo_remanescente = fluxo_carteira - custos_adm - inadimplencia_despesa - pmt_senior
        fluxo_remanescente_mezz = fluxo_remanescente - pmt_mezz
        pl_fidc_atual = carteira + fluxo_carteira - custos_adm - inadimplencia_despesa - pmt_senior - pmt_mezz
        pl_sub_jr = pl_fidc_atual - pl_senior_atual - pl_mezz_atual

        taxa_senior_period = taxa_senior[index]
        vp_pmt_senior = 0.0
        if taxa_senior_period is not None:
            vp_pmt_senior = pmt_senior / ((1.0 + taxa_senior_period) ** (du[index] / 252.0))

        periods.append(
            PeriodResult(
                indice=period_indexes[index],
                data=dt,
                dc=dc[index],
                du=du[index],
                delta_dc=delta_dc,
                delta_du=delta_du,
                pre_di=zero_pre_di[index],
                taxa_senior=taxa_senior[index],
                fra_senior=fra_senior[index],
                taxa_mezz=taxa_mezz[index],
                fra_mezz=fra_mezz[index],
                carteira=carteira,
                fluxo_carteira=fluxo_carteira,
                pl_fidc=pl_fidc_atual,
                custos_adm=custos_adm,
                inadimplencia_despesa=inadimplencia_despesa,
                principal_senior=principal_senior_period,
                juros_senior=juros_senior,
                pmt_senior=pmt_senior,
                vp_pmt_senior=vp_pmt_senior,
                pl_senior=pl_senior_atual,
                fluxo_remanescente=fluxo_remanescente,
                principal_mezz=principal_mezz_period,
                juros_mezz=juros_mezz,
                pmt_mezz=pmt_mezz,
                pl_mezz=pl_mezz_atual,
                fluxo_remanescente_mezz=fluxo_remanescente_mezz,
                principal_sub_jr=0.0,
                juros_sub_jr=0.0,
                pmt_sub_jr=0.0,
                pl_sub_jr=pl_sub_jr,
                subordinacao_pct=(pl_sub_jr / pl_fidc_atual) if pl_fidc_atual else None,
                pl_sub_jr_modelo=None,
                subordinacao_pct_modelo=None,
            )
        )

    residual_modelo: list[float | None] = [None] * len(periods)
    for index, period in enumerate(periods):
        if index == 0:
            residual_modelo[index] = None
            continue
        if index == 1:
            residual_modelo[index] = period.pl_sub_jr
            continue
        if index == len(periods) - 1:
            residual_modelo[index] = 0.0
            continue
        residual_modelo[index] = periods[index + 1].pl_sub_jr

    periodos_ajustados: list[PeriodResult] = []
    for index, period in enumerate(periods):
        residual_exibido = residual_modelo[index]
        subordinacao_modelo = None
        if residual_exibido is not None and period.pl_fidc:
            subordinacao_modelo = residual_exibido / period.pl_fidc
        periodos_ajustados.append(
            replace(
                period,
                pl_sub_jr_modelo=residual_exibido,
                subordinacao_pct_modelo=subordinacao_modelo,
            )
        )

    return periodos_ajustados


def build_kpis(periods: Sequence[PeriodResult]) -> ModelKpis:
    if not periods:
        return ModelKpis(
            xirr_senior=None,
            xirr_mezz=None,
            xirr_sub_jr=None,
            taxa_retorno_sub_jr_cdi=None,
            duration_senior_anos=None,
            pre_di_duration=None,
        )

    xirr_senior = xirr([(period.data, period.pmt_senior) for period in periods])
    xirr_mezz = xirr([(period.data, period.pmt_mezz) for period in periods])
    xirr_sub_jr = xirr([(period.data, period.pmt_sub_jr) for period in periods])
    duration_senior_anos = calculate_duration_years(periods)
    pre_di_duration = lookup_pre_di_duration(periods, duration_senior_anos)
    taxa_retorno_sub_jr_cdi = None
    if xirr_sub_jr is not None and pre_di_duration is not None:
        taxa_retorno_sub_jr_cdi = ((1.0 + xirr_sub_jr) / (1.0 + pre_di_duration)) - 1.0

    return ModelKpis(
        xirr_senior=xirr_senior,
        xirr_mezz=xirr_mezz,
        xirr_sub_jr=xirr_sub_jr,
        taxa_retorno_sub_jr_cdi=taxa_retorno_sub_jr_cdi,
        duration_senior_anos=duration_senior_anos,
        pre_di_duration=pre_di_duration,
    )
