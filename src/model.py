from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import numpy_financial as npf
import pandas as pd


@dataclass
class ModelInputs:
    volume: float
    start_date: pd.Timestamp
    periods: int
    frequency_months: int
    asset_rate_aa: float
    admin_rate_aa: float
    admin_min_period: float
    loss_rate_aa: float
    senior_share: float
    mezz_share: float
    junior_share: float
    senior_rate_aa: float
    mezz_rate_aa: float
    holiday_calendar: Optional[List[pd.Timestamp]] = None
    curve: Optional[pd.DataFrame] = None


@dataclass
class ModelOutputs:
    timeline: pd.DataFrame
    kpis: Dict[str, float]


def _period_rate(rate_aa: float, periods_per_year: int) -> float:
    return (1 + rate_aa) ** (1 / periods_per_year) - 1


def _interpolate_curve(curve: pd.DataFrame, dates: List[pd.Timestamp]) -> List[float]:
    curve = curve.sort_values("date").dropna()
    curve["timestamp"] = curve["date"].astype("int64")
    rates = []
    for date in dates:
        ts = pd.Timestamp(date).value
        interp_rate = np.interp(ts, curve["timestamp"], curve["rate"])
        rates.append(interp_rate)
    return rates


def _business_days(start: pd.Timestamp, end: pd.Timestamp, holidays: Optional[List[pd.Timestamp]]) -> int:
    holiday_list = None
    if holidays:
        holiday_list = [pd.Timestamp(day).date() for day in holidays]
    return np.busday_count(start.date(), end.date(), holidays=holiday_list)


def generate_timeline(start_date: pd.Timestamp, periods: int, frequency_months: int) -> List[pd.Timestamp]:
    return [start_date + pd.DateOffset(months=frequency_months * idx) for idx in range(periods + 1)]


def run_model(inputs: ModelInputs) -> ModelOutputs:
    periods_per_year = int(round(12 / inputs.frequency_months))
    dates = generate_timeline(inputs.start_date, inputs.periods, inputs.frequency_months)
    period_dates = dates[1:]

    if inputs.curve is not None:
        curve_rates = _interpolate_curve(inputs.curve, period_dates)
        asset_rates = [_period_rate(rate, periods_per_year) for rate in curve_rates]
    else:
        asset_rates = [_period_rate(inputs.asset_rate_aa, periods_per_year)] * inputs.periods

    senior_rates = _period_rate(inputs.senior_rate_aa, periods_per_year)
    mezz_rates = _period_rate(inputs.mezz_rate_aa, periods_per_year)
    admin_rates = _period_rate(inputs.admin_rate_aa, periods_per_year)
    loss_rates = _period_rate(inputs.loss_rate_aa, periods_per_year)

    asset_balance = inputs.volume
    senior_balance = inputs.volume * inputs.senior_share
    mezz_balance = inputs.volume * inputs.mezz_share
    junior_balance = inputs.volume * inputs.junior_share

    rows = []
    asset_amort = inputs.volume / inputs.periods

    senior_flows = [-senior_balance]
    mezz_flows = [-mezz_balance]
    junior_flows = [-junior_balance]

    for idx, date in enumerate(period_dates):
        prev_date = dates[idx]
        business_days = _business_days(prev_date, date, inputs.holiday_calendar)

        asset_interest = asset_balance * asset_rates[idx]
        asset_amortization = min(asset_amort, asset_balance)

        loss = asset_balance * loss_rates
        asset_balance = max(asset_balance - asset_amortization - loss, 0)

        admin_cost = max(inputs.admin_min_period, inputs.volume * admin_rates)
        gross_cash = asset_interest + asset_amortization
        net_cash = gross_cash - admin_cost - loss

        senior_interest = senior_balance * senior_rates
        senior_payment = min(net_cash, senior_interest)
        net_cash -= senior_payment

        senior_amort = min(net_cash, senior_balance)
        net_cash -= senior_amort
        senior_balance -= senior_amort

        mezz_interest = mezz_balance * mezz_rates
        mezz_payment = min(net_cash, mezz_interest)
        net_cash -= mezz_payment

        mezz_amort = min(net_cash, mezz_balance)
        net_cash -= mezz_amort
        mezz_balance -= mezz_amort

        junior_payment = max(net_cash, 0)
        junior_balance = max(junior_balance - junior_payment, 0)

        senior_flows.append(senior_payment + senior_amort)
        mezz_flows.append(mezz_payment + mezz_amort)
        junior_flows.append(junior_payment)

        rows.append(
            {
                "data": date,
                "dias_uteis": business_days,
                "caixa_bruto": gross_cash,
                "custo_admin": admin_cost,
                "perdas": loss,
                "caixa_liquido": gross_cash - admin_cost - loss,
                "pagamento_senior": senior_payment,
                "amort_senior": senior_amort,
                "pagamento_mezz": mezz_payment,
                "amort_mezz": mezz_amort,
                "pagamento_junior": junior_payment,
                "saldo_ativo": asset_balance,
                "saldo_senior": senior_balance,
                "saldo_mezz": mezz_balance,
                "saldo_junior": junior_balance,
            }
        )

    timeline = pd.DataFrame(rows)
    kpis = {
        "irr_senior": _safe_irr(senior_flows),
        "irr_mezz": _safe_irr(mezz_flows),
        "irr_junior": _safe_irr(junior_flows),
        "duration_senior": _duration(senior_flows, periods_per_year),
        "duration_mezz": _duration(mezz_flows, periods_per_year),
        "duration_junior": _duration(junior_flows, periods_per_year),
        "equity_multiple": _equity_multiple(junior_flows),
    }

    return ModelOutputs(timeline=timeline, kpis=kpis)


def _safe_irr(flows: List[float]) -> float:
    try:
        irr = float(npf.irr(flows))
        if np.isnan(irr):
            return 0.0
        return irr
    except Exception:
        return 0.0


def _duration(flows: List[float], periods_per_year: int) -> float:
    irr = _safe_irr(flows)
    if irr == 0:
        return 0.0
    discounted = []
    weighted = []
    for idx, flow in enumerate(flows[1:], start=1):
        df = (1 + irr) ** idx
        discounted.append(flow / df)
        weighted.append(idx * flow / df)
    total = sum(discounted)
    if total == 0:
        return 0.0
    macaulay = sum(weighted) / total
    return macaulay / periods_per_year


def _equity_multiple(flows: List[float]) -> float:
    if not flows:
        return 0.0
    invested = -flows[0]
    if invested <= 0:
        return 0.0
    return sum(flows[1:]) / invested
