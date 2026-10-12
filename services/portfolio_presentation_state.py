"""Read-only presence checks for optional portfolio presentation components.

These checks describe the supplied observations. They do not infer whether an
indicator applies to a fund, fill gaps, aggregate values, or use a materiality
threshold. Callers remain responsible for explaining any omitted component.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable, Literal

import pandas as pd


ComponentStatus = Literal["absent", "zero", "observed"]


@dataclass(frozen=True)
class ComponentState:
    """Presence of numeric observations in the requested columns.

    Counts refer to cells, including each missing requested column once per
    row. ``zero`` can therefore coexist with ``has_gaps``; it describes only
    the finite observations and never means complete coverage.
    """

    status: ComponentStatus
    finite_count: int
    missing_count: int
    row_count: int
    columns: tuple[str, ...]

    @property
    def has_gaps(self) -> bool:
        return self.missing_count > 0


def _is_finite_numeric(value: object) -> bool:
    if value is None or value is pd.NA or value is pd.NaT:
        return False
    try:
        # Decimal supplies this method and can retain nonzero values below
        # the float range. Keep its exact zero comparison in the caller.
        decimal_check = getattr(value, "is_finite", None)
        if callable(decimal_check):
            return bool(decimal_check())
        return isfinite(value)
    except (TypeError, ValueError, OverflowError):
        return False


def classify_component(
    frame: pd.DataFrame | None, columns: Iterable[str] | str
) -> ComponentState:
    """Classify supplied numeric cells without changing ``frame``.

    ``absent`` means no finite numeric observation; ``zero`` means every
    finite observation is exactly zero; ``observed`` means at least one is
    nonzero, including negative and arbitrarily small values. Missing
    columns, nulls, infinities and nonnumeric cells count as missing. Column
    names are deduplicated in their original order. Numeric strings are not
    parsed, because this helper does not reinterpret the input data.
    """

    requested = (columns,) if isinstance(columns, str) else tuple(columns)
    requested = tuple(dict.fromkeys(requested))
    row_count = 0 if frame is None else len(frame)
    finite_count = 0
    observed = False

    if frame is not None:
        for column in requested:
            if column not in frame.columns:
                continue
            for value in frame[column].array:
                if _is_finite_numeric(value):
                    finite_count += 1
                    if value != 0:
                        observed = True

    status: ComponentStatus = (
        "observed" if observed else "zero" if finite_count else "absent"
    )
    return ComponentState(
        status=status,
        finite_count=finite_count,
        missing_count=row_count * len(requested) - finite_count,
        row_count=row_count,
        columns=requested,
    )
