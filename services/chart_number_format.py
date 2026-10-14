"""Brazilian number labels for chart axes, with precision set by the data span."""
from __future__ import annotations

import math

import pandas as pd


def pt_br_number_expr(decimals: int, suffix: str = "") -> str:
    """Vega labelExpr: thousands with '.', decimals with ','."""
    expr = (
        f"replace(replace(replace(format(datum.value, ',.{int(decimals)}f'), "
        "regexp(',', 'g'), '_'), '.', ','), regexp('_', 'g'), '.')"
    )
    return f"{expr} + '{suffix}'" if suffix else expr


def span_decimals(values: object, *, ticks: int = 6, minimum: int = 0, maximum: int = 3) -> int:
    """Fewest decimals that keep neighbouring axis ticks distinct."""
    numeric = pd.to_numeric(pd.Series(values, dtype="object"), errors="coerce").dropna()
    numeric = numeric[numeric.map(lambda value: math.isfinite(float(value)))]
    if numeric.empty:
        return minimum
    span = float(numeric.max() - numeric.min()) or abs(float(numeric.max()))
    if span <= 0:
        return minimum
    step = span / max(ticks - 1, 1)
    decimals = max(0, -math.floor(math.log10(step)))
    return int(min(max(decimals, minimum), maximum))
