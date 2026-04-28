from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Sequence


def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def networkdays(start: date, end: date, feriados: Iterable[date | datetime]) -> int:
    if start > end:
        start, end = end, start
    feriados_set = {_as_date(holiday) for holiday in feriados}
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


def easter_date(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def b3_market_holidays_for_year(year: int) -> set[date]:
    easter = easter_date(year)
    holidays = {
        date(year, 1, 1),
        date(year, 4, 21),
        date(year, 5, 1),
        date(year, 9, 7),
        date(year, 10, 12),
        date(year, 11, 2),
        date(year, 11, 15),
        date(year, 12, 24),
        date(year, 12, 25),
        date(year, 12, 31),
        easter - timedelta(days=48),  # Carnival Monday
        easter - timedelta(days=47),  # Carnival Tuesday
        easter - timedelta(days=2),  # Good Friday
        easter + timedelta(days=60),  # Corpus Christi
    }
    if year >= 2024:
        holidays.add(date(year, 11, 20))
    return holidays


def b3_market_holidays_for_dates(datas: Sequence[datetime | date]) -> set[date]:
    if not datas:
        return set()
    years = range(min(_as_date(value).year for value in datas), max(_as_date(value).year for value in datas) + 1)
    holidays: set[date] = set()
    for year in years:
        holidays.update(b3_market_holidays_for_year(year))
    return holidays


def merge_with_b3_market_holidays(
    feriados: Iterable[date | datetime],
    datas: Sequence[datetime | date],
) -> list[date]:
    merged = {_as_date(holiday) for holiday in feriados}
    merged.update(b3_market_holidays_for_dates(datas))
    return sorted(merged)


def build_day_counts(datas: Sequence[datetime], feriados: Iterable[date | datetime]) -> tuple[list[int], list[int]]:
    if not datas:
        return [], []

    start_date = datas[0].date()
    holiday_dates = [_as_date(holiday) for holiday in feriados]
    dc = [(dt.date() - start_date).days for dt in datas]
    du = [0]
    for dt in datas[1:]:
        du.append(networkdays(start_date, dt.date(), holiday_dates) - 1)
    return dc, du
