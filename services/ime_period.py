from __future__ import annotations

from dataclasses import dataclass
from datetime import date


DEFAULT_PRESET_MONTHS = 12
PERIOD_PRESET_OPTIONS = (3, 6, 9, 12)


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def shift_month(base: date, offset_months: int) -> date:
    month_index = (base.year * 12 + (base.month - 1)) + offset_months
    year = month_index // 12
    month = (month_index % 12) + 1
    return date(year, month, 1)


def current_default_end_month(today: date | None = None) -> date:
    reference = today or date.today()
    # Informes mensais do mês corrente normalmente ainda não estão disponíveis.
    # Use o último mês fechado como fim padrão da janela móvel.
    return shift_month(month_start(reference), -1)


def month_options(end_month: date, *, months_back: int) -> list[date]:
    start_month = shift_month(end_month, -months_back)
    values: list[date] = []
    current = start_month
    while current <= end_month:
        values.append(current)
        current = shift_month(current, 1)
    return values


def parse_competencia_label(value: str) -> date:
    month, year = str(value).strip().split("/", 1)
    return date(int(year), int(month), 1)


@dataclass(frozen=True)
class ImePeriodSelection:
    mode: str
    start_month: date
    end_month: date
    preset_months: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "start_month", month_start(self.start_month))
        object.__setattr__(self, "end_month", month_start(self.end_month))
        if self.start_month > self.end_month:
            raise ValueError("Competência inicial deve ser menor ou igual à competência final.")
        if self.mode not in {"preset", "custom"}:
            raise ValueError("Modo de período inválido.")
        if self.mode == "preset" and self.preset_months not in PERIOD_PRESET_OPTIONS:
            raise ValueError("Preset inválido para o período.")

    @property
    def label(self) -> str:
        return f"{self.start_month.strftime('%m/%Y')} a {self.end_month.strftime('%m/%Y')}"

    @property
    def cache_key(self) -> str:
        return f"{self.start_month.isoformat()}::{self.end_month.isoformat()}"

    @property
    def month_count(self) -> int:
        return ((self.end_month.year - self.start_month.year) * 12) + (self.end_month.month - self.start_month.month) + 1


def build_preset_period(*, end_month: date, months: int) -> ImePeriodSelection:
    if months not in PERIOD_PRESET_OPTIONS:
        raise ValueError("Preset inválido.")
    normalized_end = month_start(end_month)
    start_month = shift_month(normalized_end, -(months - 1))
    return ImePeriodSelection(
        mode="preset",
        start_month=start_month,
        end_month=normalized_end,
        preset_months=months,
    )


def build_custom_period(*, start_month: date, end_month: date) -> ImePeriodSelection:
    return ImePeriodSelection(
        mode="custom",
        start_month=month_start(start_month),
        end_month=month_start(end_month),
        preset_months=None,
    )
