"""B3/Cetip DI Over loader and monthly compounding helpers."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.fidc_model.calendar import b3_market_holidays_for_dates


B3_MEDIA_CDI_URL = "ftp://ftp.cetip.com.br/MediaCDI/{yyyymmdd}.txt"
B3_BDI_DI_OVER_URL = (
    "https://arquivos.b3.com.br/bdi/table/DIover/"
    "{start_date}/{end_date}/{page}/{page_size}"
)
DEFAULT_CDI_CACHE_DIR = Path(".cache/b3-cdi/MediaCDI")
B3_BDI_SOURCE = "B3 BDI DI Over via HTTPS (fator diário oficial)"
B3_MEDIA_CDI_SOURCE = "B3/Cetip MediaCDI via FTP"


class B3CdiError(RuntimeError):
    """Raised when a B3 DI Over file cannot be parsed."""


@dataclass(frozen=True)
class B3CdiDailyRate:
    data: date
    taxa_aa: float
    source_url: str
    retrieved_at: datetime
    daily_factor: float | None = None

    @property
    def fator_diario(self) -> float:
        if self.daily_factor is not None:
            return self.daily_factor - 1.0
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


def b3_bdi_di_over_url(
    start_date: date,
    end_date: date,
    *,
    page: int = 1,
    page_size: int = 1000,
) -> str:
    return B3_BDI_DI_OVER_URL.format(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        page=max(1, int(page)),
        page_size=max(1, int(page_size)),
    )


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


def fetch_b3_bdi_cdi_daily_rates(
    start_date: date,
    end_date: date,
    *,
    timeout: float = 30.0,
    opener: Callable[..., object] | None = None,
    page_size: int = 1000,
) -> tuple[B3CdiDailyRate, ...]:
    """Fetch realized DI Over daily factors from the official B3 BDI HTTPS API."""
    if end_date < start_date:
        return ()

    open_func = opener or urlopen
    rates_by_date: dict[date, B3CdiDailyRate] = {}
    retrieved_at = datetime.now(timezone.utc)
    page = 1
    page_count = 1
    while page <= page_count:
        url = b3_bdi_di_over_url(
            start_date,
            end_date,
            page=page,
            page_size=page_size,
        )
        request = Request(
            url,
            data=b"{}",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "fidc-streamlit-model/1.0",
            },
            method="POST",
        )
        try:
            with open_func(request, timeout=timeout) as response:  # type: ignore[misc]
                raw_payload = response.read()
        except HTTPError as exc:
            raise B3CdiError(f"B3 BDI retornou HTTP {exc.code} ao consultar CDI realizado.") from exc
        except URLError as exc:
            raise B3CdiError(f"Falha de rede ao consultar CDI no B3 BDI: {exc.reason}.") from exc
        except OSError as exc:
            raise B3CdiError(f"Falha ao consultar CDI no B3 BDI: {exc}.") from exc
        if not raw_payload:
            raise B3CdiError("B3 BDI retornou resposta vazia para o CDI realizado.")
        try:
            payload = json.loads(raw_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise B3CdiError("B3 BDI retornou JSON inválido para o CDI realizado.") from exc

        table = payload.get("table") if isinstance(payload, dict) else None
        if not isinstance(table, dict):
            raise B3CdiError("B3 BDI não retornou a tabela DIover esperada.")
        columns = table.get("columns")
        values = table.get("values")
        if not isinstance(columns, list) or not isinstance(values, list):
            raise B3CdiError("B3 BDI retornou uma tabela DIover sem colunas ou valores.")
        column_index = {
            str(column.get("name")): index
            for index, column in enumerate(columns)
            if isinstance(column, dict) and column.get("name")
        }
        if "RptDt" not in column_index or not ({"DailyFactor", "Average"} & set(column_index)):
            raise B3CdiError("B3 BDI alterou o layout esperado da tabela DIover.")

        for raw_row in values:
            rate = _parse_b3_bdi_daily_row(
                raw_row,
                column_index=column_index,
                source_url=url,
                retrieved_at=retrieved_at,
            )
            if rate is not None and start_date <= rate.data <= end_date:
                rates_by_date[rate.data] = rate
        try:
            parsed_page_count = max(1, int(table.get("pageCount") or 1))
        except (TypeError, ValueError, OverflowError):
            parsed_page_count = 1
        page_count = max(page_count, parsed_page_count)
        page += 1

    return tuple(rates_by_date[item_date] for item_date in sorted(rates_by_date))


def fetch_b3_cdi_monthly_rates(
    start_date: date,
    end_date: date,
    *,
    cache_dir: str | Path = DEFAULT_CDI_CACHE_DIR,
    fetcher: Callable[..., B3CdiDailyRate] = fetch_media_cdi_daily_rate,
    bdi_fetcher: Callable[..., Iterable[B3CdiDailyRate]] | None = fetch_b3_bdi_cdi_daily_rates,
    max_workers: int = 12,
) -> tuple[B3CdiMonthlyRate, ...]:
    if end_date < start_date:
        return ()

    expected_dates = _expected_cdi_business_dates(start_date, end_date)
    if not expected_dates:
        return ()
    expected_date_set = set(expected_dates)

    rates_by_date: dict[date, B3CdiDailyRate] = {}
    errors: list[str] = []
    if bdi_fetcher is not None:
        try:
            for rate in bdi_fetcher(start_date, end_date):
                if rate.data in expected_date_set:
                    rates_by_date[rate.data] = rate
        except B3CdiError as exc:
            errors.append(str(exc))

    missing_primary_dates = [item_date for item_date in expected_dates if item_date not in rates_by_date]
    workers = max(1, int(max_workers or 1))
    if missing_primary_dates:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(fetcher, item_date, cache_dir=cache_dir): item_date
                for item_date in missing_primary_dates
            }
            for future in as_completed(future_map):
                expected_date = future_map[future]
                try:
                    rate = future.result()
                except B3CdiError as exc:
                    if len(errors) < 3:
                        errors.append(str(exc))
                    continue
                if rate.data == expected_date:
                    rates_by_date[rate.data] = rate

    if not rates_by_date:
        detail = f" Detalhe: {errors[0]}" if errors else ""
        raise B3CdiError(
            "Nenhuma taxa CDI realizada foi obtida pelo B3 BDI/HTTPS nem pelo MediaCDI/FTP."
            + detail
        )

    rates = list(rates_by_date.values())

    grouped: dict[str, list[B3CdiDailyRate]] = {}
    for rate in rates:
        grouped.setdefault(f"{rate.data.year:04d}-{rate.data.month:02d}", []).append(rate)
    expected_dates_by_month: dict[str, set[date]] = {}
    for item_date in expected_dates:
        expected_dates_by_month.setdefault(f"{item_date.year:04d}-{item_date.month:02d}", set()).add(item_date)

    rows: list[B3CdiMonthlyRate] = []
    for mes, month_rates in sorted(grouped.items()):
        factor = 1.0
        for rate in sorted(month_rates, key=lambda item: item.data):
            factor *= 1.0 + rate.fator_diario
        dates = [rate.data for rate in month_rates]
        month_expected_dates = expected_dates_by_month.get(mes, set())
        missing_dates = tuple(sorted(month_expected_dates - set(dates)))
        rows.append(
            B3CdiMonthlyRate(
                mes=mes,
                cdi_mensal=factor - 1.0,
                dias_uteis=len(month_rates),
                data_inicio=min(dates),
                data_fim=max(dates),
                source=_monthly_cdi_source(month_rates),
                expected_dias_uteis=len(month_expected_dates),
                missing_dates=missing_dates,
            )
        )
    return tuple(rows)


def _parse_b3_bdi_daily_row(
    raw_row: object,
    *,
    column_index: dict[str, int],
    source_url: str,
    retrieved_at: datetime,
) -> B3CdiDailyRate | None:
    if not isinstance(raw_row, list):
        return None
    try:
        raw_date = str(raw_row[column_index["RptDt"]])[:10]
        item_date = date.fromisoformat(raw_date)
    except (IndexError, KeyError, TypeError, ValueError):
        return None

    daily_factor: float | None = None
    if "DailyFactor" in column_index:
        try:
            candidate = float(raw_row[column_index["DailyFactor"]])
        except (IndexError, TypeError, ValueError):
            candidate = float("nan")
        if math.isfinite(candidate) and candidate > 0.0:
            daily_factor = candidate

    taxa_aa: float | None = None
    if daily_factor is not None:
        taxa_aa = daily_factor**252.0 - 1.0
    elif "Average" in column_index:
        try:
            candidate = float(raw_row[column_index["Average"]]) / 100.0
        except (IndexError, TypeError, ValueError):
            candidate = float("nan")
        if math.isfinite(candidate) and candidate > -1.0:
            taxa_aa = candidate
    if taxa_aa is None:
        return None
    return B3CdiDailyRate(
        data=item_date,
        taxa_aa=taxa_aa,
        source_url=source_url,
        retrieved_at=retrieved_at,
        daily_factor=daily_factor,
    )


def _monthly_cdi_source(rates: Iterable[B3CdiDailyRate]) -> str:
    source_urls = {str(rate.source_url) for rate in rates}
    uses_bdi = any("arquivos.b3.com.br/bdi/" in url for url in source_urls)
    uses_ftp = any(url.startswith("ftp://ftp.cetip.com.br/") for url in source_urls)
    if uses_bdi and uses_ftp:
        return f"{B3_BDI_SOURCE}; contingência parcial {B3_MEDIA_CDI_SOURCE}"
    if uses_bdi:
        return B3_BDI_SOURCE
    if uses_ftp:
        return B3_MEDIA_CDI_SOURCE
    return "CDI diário realizado composto por mês"


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
