"""B3/Cetip DI Over loader and monthly compounding helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from services.fidc_model.calendar import b3_market_holidays_for_dates


B3_MEDIA_CDI_URL = "ftp://ftp.cetip.com.br/MediaCDI/{yyyymmdd}.txt"
DEFAULT_CDI_CACHE_DIR = Path(".cache/b3-cdi/MediaCDI")


class B3CdiError(RuntimeError):
    """Raised when a B3 DI Over file cannot be parsed."""


@dataclass(frozen=True)
class B3CdiDailyRate:
    data: date
    taxa_aa: float
    source_url: str
    retrieved_at: datetime

    @property
    def fator_diario(self) -> float:
        return (1.0 + self.taxa_aa) ** (1.0 / 252.0) - 1.0


@dataclass(frozen=True)
class B3CdiMonthlyRate:
    mes: str
    cdi_mensal: float
    dias_uteis: int
    data_inicio: date
    data_fim: date
    source: str
    expected_dias_uteis: int | None = None
    missing_dates: tuple[date, ...] = ()

    @property
    def cdi_aa_equivalente(self) -> float:
        if self.dias_uteis <= 0:
            return 0.0
        return (1.0 + self.cdi_mensal) ** (252.0 / self.dias_uteis) - 1.0

    @property
    def is_complete(self) -> bool:
        if self.missing_dates:
            return False
        if self.expected_dias_uteis is None:
            return True
        return self.dias_uteis >= self.expected_dias_uteis


def media_cdi_url(item_date: date) -> str:
    return B3_MEDIA_CDI_URL.format(yyyymmdd=f"{item_date:%Y%m%d}")


def parse_media_cdi_text(text: str) -> float:
    cleaned = "".join(char for char in str(text or "") if char.isdigit())
    if not cleaned:
        raise B3CdiError("Arquivo MediaCDI sem campo numérico.")
    return int(cleaned) / 10_000.0


def fetch_media_cdi_daily_rate(
    item_date: date,
    *,
    cache_dir: str | Path = DEFAULT_CDI_CACHE_DIR,
    timeout: float = 8.0,
    opener: Callable[..., object] | None = None,
) -> B3CdiDailyRate:
    cache_path = Path(cache_dir) / f"{item_date:%Y%m%d}.txt"
    url = media_cdi_url(item_date)
    if cache_path.exists():
        text = cache_path.read_text(encoding="latin-1")
    else:
        open_func = opener or urlopen
        try:
            with open_func(url, timeout=timeout) as response:  # type: ignore[misc]
                payload = response.read()
        except HTTPError as exc:
            raise B3CdiError(f"B3 retornou HTTP {exc.code} para CDI de {item_date:%d/%m/%Y}.") from exc
        except URLError as exc:
            raise B3CdiError(f"Falha de rede ao consultar CDI B3 de {item_date:%d/%m/%Y}: {exc.reason}.") from exc
        except OSError as exc:
            raise B3CdiError(f"Falha ao consultar CDI B3 de {item_date:%d/%m/%Y}: {exc}.") from exc
        if not payload:
            raise B3CdiError(f"B3 retornou arquivo CDI vazio para {item_date:%d/%m/%Y}.")
        text = payload.decode("latin-1", errors="replace")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="latin-1")
    return B3CdiDailyRate(
        data=item_date,
        taxa_aa=parse_media_cdi_text(text),
        source_url=url,
        retrieved_at=datetime.now(timezone.utc),
    )


def fetch_b3_cdi_monthly_rates(
    start_date: date,
    end_date: date,
    *,
    cache_dir: str | Path = DEFAULT_CDI_CACHE_DIR,
    fetcher: Callable[..., B3CdiDailyRate] = fetch_media_cdi_daily_rate,
    max_workers: int = 12,
) -> tuple[B3CdiMonthlyRate, ...]:
    if end_date < start_date:
        return ()

    business_dates = [item_date for item_date in _calendar_days(start_date, end_date) if item_date.weekday() < 5]
    rates: list[B3CdiDailyRate] = []
    workers = max(1, int(max_workers or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(fetcher, item_date, cache_dir=cache_dir): item_date for item_date in business_dates}
        for future in as_completed(future_map):
            try:
                rates.append(future.result())
            except B3CdiError:
                continue

    grouped: dict[str, list[B3CdiDailyRate]] = {}
    for rate in rates:
        grouped.setdefault(f"{rate.data.year:04d}-{rate.data.month:02d}", []).append(rate)
    expected_dates_by_month: dict[str, set[date]] = {}
    for item_date in _expected_cdi_business_dates(start_date, end_date):
        expected_dates_by_month.setdefault(f"{item_date.year:04d}-{item_date.month:02d}", set()).add(item_date)

    rows: list[B3CdiMonthlyRate] = []
    for mes, rates in sorted(grouped.items()):
        factor = 1.0
        for rate in sorted(rates, key=lambda item: item.data):
            factor *= 1.0 + rate.fator_diario
        dates = [rate.data for rate in rates]
        expected_dates = expected_dates_by_month.get(mes, set())
        missing_dates = tuple(sorted(expected_dates - set(dates)))
        rows.append(
            B3CdiMonthlyRate(
                mes=mes,
                cdi_mensal=factor - 1.0,
                dias_uteis=len(rates),
                data_inicio=min(dates),
                data_fim=max(dates),
                source="B3/Cetip MediaCDI diário composto por mês",
                expected_dias_uteis=len(expected_dates),
                missing_dates=missing_dates,
            )
        )
    return tuple(rows)


def compound_monthly_cdi(
    monthly_rates: Iterable[B3CdiMonthlyRate],
    *,
    factor: float = 1.0,
) -> float:
    output = 1.0
    for rate in monthly_rates:
        output *= (1.0 + rate.cdi_mensal) ** factor
    return output - 1.0


def _calendar_days(start_date: date, end_date: date) -> Iterable[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _expected_cdi_business_dates(start_date: date, end_date: date) -> tuple[date, ...]:
    """Expected MediaCDI publication dates (Brazil business days, including 24/31 Dec)."""
    holidays = b3_market_holidays_for_dates([start_date, end_date])
    for year in range(start_date.year, end_date.year + 1):
        holidays.discard(date(year, 12, 24))
        holidays.discard(date(year, 12, 31))
    return tuple(
        item_date
        for item_date in _calendar_days(start_date, end_date)
        if item_date.weekday() < 5 and item_date not in holidays
    )
