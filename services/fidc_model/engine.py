from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable, Sequence

from .calendar import build_day_counts, build_period_indexes
from .contracts import ModelKpis, PeriodResult, Premissas
from .curves import cubic_spline
from .metrics import calculate_duration_years, lookup_pre_di_duration, xirr


RATE_MODE_POST_CDI = "pos_cdi"
RATE_MODE_PRE = "pre"


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


def _principal_schedule(period_count: int, initial_pl: float) -> list[float]:
    schedule = [0.0] * period_count
    if period_count:
        schedule[0] = -initial_pl
    for index in range(5, period_count):
        schedule[index] = initial_pl / 12.0
    return schedule


def build_flow(
    datas: Sequence[datetime],
    feriados: Iterable[datetime],
    curva_du: Sequence[float],
    curva_cdi: Sequence[float],
    premissas: Premissas,
) -> list[PeriodResult]:
    if not datas:
        return []
    if not curva_du or not curva_cdi:
        raise ValueError("Curva DI/Pre vazia: o modelo exige curva local extraída da planilha de referência.")

    period_indexes = build_period_indexes(len(datas))
    dc, du = build_day_counts(datas, feriados)

    zero_pre_di: list[float | None] = [None]
    for du_value in du[1:]:
        zero_pre_di.append(cubic_spline(float(du_value), curva_du, curva_cdi))

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

    principal_senior = _principal_schedule(len(datas), pl_senior_initial)
    principal_mezz = _principal_schedule(len(datas), pl_mezz_initial)

    periods: list[PeriodResult] = []
    pl_senior_atual = pl_senior_initial
    pl_mezz_atual = pl_mezz_initial
    pl_fidc_atual = premissas.volume

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
        juros_senior = pl_senior_atual * ((1.0 + fra_senior_period) ** (delta_du / 252.0) - 1.0)
        juros_mezz = pl_mezz_atual * ((1.0 + fra_mezz_period) ** (delta_du / 252.0) - 1.0)

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
