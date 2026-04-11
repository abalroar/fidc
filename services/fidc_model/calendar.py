from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Sequence


def networkdays(start: date, end: date, feriados: Iterable[date]) -> int:
    if start > end:
        start, end = end, start
    feriados_set = set(feriados)
    day = start
    total = 0
    while day <= end:
        if day.weekday() < 5 and day not in feriados_set:
            total += 1
        day = day.fromordinal(day.toordinal() + 1)
    return total


def build_period_indexes(length: int) -> list[int]:
    indices = [0]
    for i in range(1, length):
        if i <= 4:
            indices.append(6 * i)
        else:
            indices.append(24 + (i - 4))
    return indices


def build_day_counts(datas: Sequence[datetime], feriados: Iterable[datetime]) -> tuple[list[int], list[int]]:
    if not datas:
        return [], []

    start_date = datas[0].date()
    holiday_dates = [holiday.date() for holiday in feriados]
    dc = [(dt.date() - start_date).days for dt in datas]
    du = [0]
    for dt in datas[1:]:
        du.append(networkdays(start_date, dt.date(), holiday_dates) - 1)
    return dc, du
