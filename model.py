from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class Premissas:
    volume: float
    tx_cessao_am: float
    tx_cessao_cdi_aa: float
    custo_adm_aa: float
    custo_min: float
    inadimplencia: float
    proporcao_senior: float
    taxa_senior: float
    proporcao_mezz: float
    taxa_mezz: float


@dataclass(frozen=True)
class PeriodResult:
    indice: int
    data: datetime
    dc: int
    du: int
    pre_di: float
    taxa_senior: float
    fra_senior: float
    taxa_mezz: float
    fra_mezz: float
    carteira: float
    fluxo: float
    pl_fidc: float
    custos_adm: float
    inadimplencia: float
    principal_senior: float
    juros_senior: float
    pmt_senior: float
    pl_senior: float
    fluxo_remanescente: float
    principal_mezz: float
    juros_mezz: float
    pmt_mezz: float
    pl_mezz: float
    fluxo_remanescente_mezz: float
    principal_sub_jr: float
    juros_sub_jr: float
    pmt_sub_jr: float
    pl_sub_jr: float


def networkdays(start: date, end: date, feriados: Iterable[date]) -> int:
    if start > end:
        start, end = end, start
    feriados_set = {f for f in feriados}
    day = start
    total = 0
    while day <= end:
        if day.weekday() < 5 and day not in feriados_set:
            total += 1
        day = day.fromordinal(day.toordinal() + 1)
    return total


def _months_index(length: int) -> List[int]:
    indices = [0]
    for i in range(1, length):
        if i <= 4:
            indices.append(6 * i)
        else:
            indices.append(24 + (i - 4))
    return indices


def _spline_coefficients(xs: Sequence[float], ys: Sequence[float]) -> Tuple[List[float], List[float], List[float], List[float]]:
    n = len(xs)
    if n < 2:
        raise ValueError("Need at least two points for spline interpolation.")
    a = list(ys)
    b = [0.0] * (n - 1)
    d = [0.0] * (n - 1)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    alpha = [0.0] * n
    for i in range(1, n - 1):
        alpha[i] = (3 / h[i]) * (a[i + 1] - a[i]) - (3 / h[i - 1]) * (a[i] - a[i - 1])

    c = [0.0] * n
    l = [1.0] * n
    mu = [0.0] * n
    z = [0.0] * n
    for i in range(1, n - 1):
        l[i] = 2 * (xs[i + 1] - xs[i - 1]) - h[i - 1] * mu[i - 1]
        mu[i] = h[i] / l[i]
        z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / l[i]

    for j in range(n - 2, -1, -1):
        c[j] = z[j] - mu[j] * c[j + 1]
        b[j] = (a[j + 1] - a[j]) / h[j] - h[j] * (c[j + 1] + 2 * c[j]) / 3
        d[j] = (c[j + 1] - c[j]) / (3 * h[j])

    return a, b, c, d


def cubic_spline(x: float, xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) < 2:
        return float(ys[0]) if ys else 0.0
    a, b, c, d = _spline_coefficients(xs, ys)
    if x <= xs[0]:
        slope = b[0]
        return a[0] + slope * (x - xs[0])
    if x >= xs[-1]:
        slope = b[-1] + 2 * c[-1] * (xs[-1] - xs[-2]) + 3 * d[-1] * (xs[-1] - xs[-2]) ** 2
        return a[-1] + slope * (x - xs[-1])
    i = 0
    while i < len(xs) - 1 and xs[i + 1] < x:
        i += 1
    dx = x - xs[i]
    return a[i] + b[i] * dx + c[i] * dx ** 2 + d[i] * dx ** 3


def xirr(cashflows: Sequence[Tuple[datetime, float]], guess: float = 0.1) -> float:
    if not cashflows:
        return 0.0
    dates = [cf[0] for cf in cashflows]
    values = [cf[1] for cf in cashflows]
    start = dates[0]

    def npv(rate: float) -> float:
        return sum(
            val / (1 + rate) ** ((dt - start).days / 365.0)
            for dt, val in zip(dates, values)
        )

    rate = guess
    for _ in range(100):
        f = npv(rate)
        if abs(f) < 1e-7:
            break
        derivative = sum(
            -(dt - start).days / 365.0 * val / (1 + rate) ** (((dt - start).days / 365.0) + 1)
            for dt, val in zip(dates, values)
        )
        if derivative == 0:
            break
        rate -= f / derivative
    return rate


def build_flow(
    datas: Sequence[datetime],
    feriados: Iterable[datetime],
    curva_du: Sequence[float],
    curva_cdi: Sequence[float],
    premissas: Premissas,
) -> List[PeriodResult]:
    if not datas:
        return []

    start_date = datas[0].date()
    feriados_dates = [f.date() for f in feriados]
    months_index = _months_index(len(datas))

    du = [
        networkdays(start_date, d.date(), feriados_dates) - 1
        for d in datas
    ]
    dc = [(d.date() - start_date).days for d in datas]

    pre_di = [cubic_spline(float(du_i), curva_du, curva_cdi) for du_i in du]
    taxa_senior = [(1 + pre_di[i]) * (1 + premissas.taxa_senior) - 1 for i in range(len(datas))]
    taxa_mezz = [(1 + pre_di[i]) * (1 + premissas.taxa_mezz) - 1 for i in range(len(datas))]

    fra_senior = [taxa_senior[0]]
    fra_mezz = [taxa_mezz[0]]
    for i in range(1, len(datas)):
        if du[i] == du[i - 1]:
            fra_senior.append(taxa_senior[i])
            fra_mezz.append(taxa_mezz[i])
            continue
        fra_s = ((1 + taxa_senior[i]) ** (du[i] / 252) / (1 + taxa_senior[i - 1]) ** (du[i - 1] / 252)) ** (
            252 / (du[i] - du[i - 1])
        ) - 1
        fra_m = ((1 + taxa_mezz[i]) ** (du[i] / 252) / (1 + taxa_mezz[i - 1]) ** (du[i - 1] / 252)) ** (
            252 / (du[i] - du[i - 1])
        ) - 1
        fra_senior.append(fra_s)
        fra_mezz.append(fra_m)

    pl_senior_initial = premissas.volume * premissas.proporcao_senior
    pl_mezz_initial = premissas.volume * premissas.proporcao_mezz

    principal_senior = []
    principal_mezz = []
    for i, months in enumerate(months_index):
        if i <= 4:
            principal_senior.append(0.0)
            principal_mezz.append(0.0)
        else:
            principal_senior.append(pl_senior_initial / 12)
            principal_mezz.append(pl_mezz_initial / 12)

    carteira = []
    fluxo = []
    pl_fidc = []
    custos_adm = []
    inad = []
    juros_senior = []
    pmt_senior = []
    pl_senior = []
    fluxo_remanescente = []
    juros_mezz = []
    pmt_mezz = []
    pl_mezz = []
    fluxo_remanescente_mezz = []
    principal_sub_jr = []
    juros_sub_jr = []
    pmt_sub_jr = []
    pl_sub_jr = []

    for i in range(len(datas)):
        if i == 0:
            carteira.append(premissas.volume)
            fluxo.append(0.0)
            custos_adm.append(0.0)
            inad.append(0.0)
            pl_senior.append(pl_senior_initial)
            pl_mezz.append(pl_mezz_initial)
            juros_senior.append(0.0)
            juros_mezz.append(0.0)
            pmt_senior.append(-pl_senior_initial)
            pmt_mezz.append(-pl_mezz_initial)
            pl_fidc.append(premissas.volume)
            fluxo_remanescente.append(0.0)
            fluxo_remanescente_mezz.append(0.0)
            principal_sub_jr.append(0.0)
            juros_sub_jr.append(0.0)
            pmt_sub_jr.append(0.0)
            pl_sub_jr.append(premissas.volume - pl_senior_initial - pl_mezz_initial)
            continue

        carteira.append(pl_fidc[i - 1])
        fluxo_periodo = carteira[i] * ((1 + premissas.tx_cessao_am) ** ((du[i] - du[i - 1]) / 21) - 1)
        fluxo.append(fluxo_periodo)
        custo = max(carteira[i] * premissas.custo_adm_aa / 12, premissas.custo_min)
        custos_adm.append(custo)
        inad_val = carteira[i] * (premissas.inadimplencia * ((dc[i] - dc[i - 1]) / 100))
        inad.append(inad_val)

        juros_s = pl_senior[i - 1] * ((1 + fra_senior[i]) ** ((du[i] - du[i - 1]) / 252) - 1)
        juros_senior.append(juros_s)
        pmt_s = juros_s + principal_senior[i]
        pmt_senior.append(pmt_s)
        pl_s = pl_senior[i - 1] - principal_senior[i]
        pl_senior.append(pl_s)

        juros_m = pl_mezz[i - 1] * ((1 + fra_mezz[i]) ** ((du[i] - du[i - 1]) / 252) - 1)
        juros_mezz.append(juros_m)
        pmt_m = juros_m + principal_mezz[i]
        pmt_mezz.append(pmt_m)
        pl_m = pl_mezz[i - 1] - principal_mezz[i]
        pl_mezz.append(pl_m)

        fluxo_rem = fluxo_periodo - custo - inad_val - pmt_s
        fluxo_remanescente.append(fluxo_rem)
        fluxo_rem_mezz = fluxo_rem - pmt_m
        fluxo_remanescente_mezz.append(fluxo_rem_mezz)

        pl_f = carteira[i] + fluxo_periodo - custo - inad_val - pmt_s - pmt_m
        pl_fidc.append(pl_f)
        pl_sub = pl_f - pl_s - pl_m
        pl_sub_jr.append(pl_sub)
        principal_sub_jr.append(0.0)
        juros_sub_jr.append(0.0)
        pmt_sub_jr.append(0.0)

    results = []
    for i in range(len(datas)):
        results.append(
            PeriodResult(
                indice=months_index[i],
                data=datas[i],
                dc=dc[i],
                du=du[i],
                pre_di=pre_di[i],
                taxa_senior=taxa_senior[i],
                fra_senior=fra_senior[i],
                taxa_mezz=taxa_mezz[i],
                fra_mezz=fra_mezz[i],
                carteira=carteira[i],
                fluxo=fluxo[i],
                pl_fidc=pl_fidc[i],
                custos_adm=custos_adm[i],
                inadimplencia=inad[i],
                principal_senior=principal_senior[i],
                juros_senior=juros_senior[i],
                pmt_senior=pmt_senior[i],
                pl_senior=pl_senior[i],
                fluxo_remanescente=fluxo_remanescente[i],
                principal_mezz=principal_mezz[i],
                juros_mezz=juros_mezz[i],
                pmt_mezz=pmt_mezz[i],
                pl_mezz=pl_mezz[i],
                fluxo_remanescente_mezz=fluxo_remanescente_mezz[i],
                principal_sub_jr=principal_sub_jr[i],
                juros_sub_jr=juros_sub_jr[i],
                pmt_sub_jr=pmt_sub_jr[i],
                pl_sub_jr=pl_sub_jr[i],
            )
        )
    return results


def build_kpis(results: Sequence[PeriodResult]) -> dict:
    if not results:
        return {}
    cashflows_senior = [(r.data, r.pmt_senior) for r in results]
    cashflows_mezz = [(r.data, r.pmt_mezz) for r in results]
    cashflows_sub = [(r.data, r.pmt_sub_jr) for r in results]
    return {
        "xirr_senior": xirr(cashflows_senior),
        "xirr_mezz": xirr(cashflows_mezz),
        "xirr_sub_jr": xirr(cashflows_sub),
    }
