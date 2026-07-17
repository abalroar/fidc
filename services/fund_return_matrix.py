from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import date
from typing import Any, Mapping

import pandas as pd

from services.fundonet_dashboard import sort_class_display_frame


RETURN_SERIES_COLUMN = "Série"
RETURN_TRAILING_12M_COLUMN = "Ac. Últ. 12m (%)"
RETURN_TRAILING_12M_CDI_COLUMN = "CDI Ac. Últ. 12m (%)"
RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN = "Spread CDI Impl. Últ. 12m (% a.a.)"
RETURN_YTD_COLUMN = "Acumulado YTD (%)"
RETURN_YTD_CDI_COLUMN = "CDI Acumulado YTD (%)"
RETURN_YTD_IMPLIED_SPREAD_COLUMN = "Spread CDI Impl. YTD (% a.a.)"
RETURN_ISSUANCE_SPREAD_COLUMN = "CDI+ Emissão (% a.a.)"
RETURN_TRAILING_12M_SPREAD_GAP_COLUMN = "Gap 12m vs Emissão (bps)"
RETURN_YTD_SPREAD_GAP_COLUMN = "Gap YTD vs Emissão (bps)"

_BPS_COLUMNS = {
    RETURN_TRAILING_12M_SPREAD_GAP_COLUMN,
    RETURN_YTD_SPREAD_GAP_COLUMN,
}

_PT_MONTH_ABBR = {
    1: "jan",
    2: "fev",
    3: "mar",
    4: "abr",
    5: "mai",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "set",
    10: "out",
    11: "nov",
    12: "dez",
}


def build_fund_return_matrix(
    outputs: Any,
    cnpj: str,
    months: int = 12,
    *,
    monthly_cdi_rates: Iterable[Any] | None = None,
    benchmark_spreads: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Build returns and CDI-equivalent spreads using percentage-point values.

    ``benchmark_spreads`` is keyed by the return series ``class_key`` and uses
    annual decimal rates (for example, ``0.035`` for CDI + 3.50% a.a.).
    """
    if isinstance(months, bool) or not isinstance(months, int) or months <= 0:
        raise ValueError("months must be a positive integer")

    history_by_cnpj = getattr(outputs, "fund_return_history", {}) or {}
    summary_by_cnpj = getattr(outputs, "fund_return_summary", {}) or {}
    history_df = _normalize_identity_frame(history_by_cnpj.get(cnpj, pd.DataFrame()))
    summary_df = _normalize_identity_frame(summary_by_cnpj.get(cnpj, pd.DataFrame()))
    latest_month = _latest_available_month(summary_df, history_df)
    include_cdi = monthly_cdi_rates is not None
    include_benchmark = benchmark_spreads is not None
    cdi_rates = tuple(monthly_cdi_rates or ()) if include_cdi else ()
    if latest_month is None:
        return _empty_return_matrix(
            [],
            include_cdi=include_cdi,
            include_benchmark=include_benchmark,
        )

    month_starts = list(pd.date_range(end=latest_month, periods=months, freq="MS"))
    competencias = [value.strftime("%m/%Y") for value in month_starts]
    month_columns = [_format_month_column(value) for value in month_starts]
    identities = _series_identities(summary_df, history_df)
    if identities.empty:
        return _empty_return_matrix(
            month_columns,
            include_cdi=include_cdi,
            include_benchmark=include_benchmark,
        )

    output = pd.DataFrame({RETURN_SERIES_COLUMN: identities["class_label"].astype(str)})
    output.index = identities["__series_key"].astype(str)

    if history_df.empty or "competencia" not in history_df.columns:
        monthly_pivot = pd.DataFrame(index=output.index, columns=competencias, dtype="float64")
    else:
        selected_history = history_df[history_df["competencia"].astype(str).isin(competencias)].copy()
        selected_history["retorno_mensal_pct"] = pd.to_numeric(
            selected_history.get("retorno_mensal_pct"),
            errors="coerce",
        )
        selected_history = selected_history.drop_duplicates(
            subset=["__series_key", "competencia"],
            keep="last",
        )
        monthly_pivot = selected_history.pivot(
            index="__series_key",
            columns="competencia",
            values="retorno_mensal_pct",
        ).reindex(index=output.index, columns=competencias)

    for competencia, column in zip(competencias, month_columns, strict=True):
        output[column] = pd.to_numeric(monthly_pivot[competencia], errors="coerce").to_numpy()

    summary_lookup = (
        summary_df.drop_duplicates(subset=["__series_key"], keep="last").set_index("__series_key")
        if not summary_df.empty
        else pd.DataFrame()
    )
    output[RETURN_TRAILING_12M_COLUMN] = _summary_values(
        summary_lookup,
        output.index,
        "retorno_12m_pct",
    )
    cdi_missing_competencias: set[str] = set()
    trailing_implied_values = pd.Series(float("nan"), index=output.index, dtype="float64").to_numpy()
    if include_cdi:
        trailing_values, trailing_implied_values, trailing_missing = _cdi_summary_values(
            summary_lookup=summary_lookup,
            history_df=history_df,
            index=output.index,
            latest_month=latest_month,
            period_start=latest_month - pd.DateOffset(months=11),
            return_column="retorno_12m_pct",
            status_column="trailing_12m_status",
            used_competencias_column="trailing_12m_competencias_utilizadas",
            monthly_cdi_rates=cdi_rates,
        )
        output[RETURN_TRAILING_12M_CDI_COLUMN] = trailing_values
        output[RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN] = trailing_implied_values
        cdi_missing_competencias.update(trailing_missing)
    output[RETURN_YTD_COLUMN] = _summary_values(
        summary_lookup,
        output.index,
        "retorno_ano_pct",
    )
    ytd_implied_values = pd.Series(float("nan"), index=output.index, dtype="float64").to_numpy()
    if include_cdi:
        ytd_values, ytd_implied_values, ytd_missing = _cdi_summary_values(
            summary_lookup=summary_lookup,
            history_df=history_df,
            index=output.index,
            latest_month=latest_month,
            period_start=pd.Timestamp(year=latest_month.year, month=1, day=1),
            return_column="retorno_ano_pct",
            status_column="ytd_status",
            used_competencias_column="ytd_competencias_utilizadas",
            monthly_cdi_rates=cdi_rates,
        )
        output[RETURN_YTD_CDI_COLUMN] = ytd_values
        output[RETURN_YTD_IMPLIED_SPREAD_COLUMN] = ytd_implied_values
        cdi_missing_competencias.update(ytd_missing)

    if include_benchmark:
        benchmark_lookup = _valid_benchmark_spreads(benchmark_spreads or {})
        benchmark_values = pd.Series(
            [benchmark_lookup.get(str(series_key), float("nan")) * 100.0 for series_key in output.index],
            index=output.index,
            dtype="float64",
        ).to_numpy()
        output[RETURN_ISSUANCE_SPREAD_COLUMN] = benchmark_values
        output[RETURN_TRAILING_12M_SPREAD_GAP_COLUMN] = (
            trailing_implied_values - benchmark_values
        ) * 100.0
        output[RETURN_YTD_SPREAD_GAP_COLUMN] = (
            ytd_implied_values - benchmark_values
        ) * 100.0

    result = output.reset_index(drop=True)
    if include_cdi:
        result.attrs["cdi_source"] = _cdi_source_label(cdi_rates)
        result.attrs["cdi_missing_competencias"] = tuple(
            sorted(cdi_missing_competencias, key=_competencia_sort_key)
        )
    return result


def _cdi_source_label(monthly_cdi_rates: Iterable[Any]) -> str:
    sources = tuple(
        dict.fromkeys(
            source
            for rate in monthly_cdi_rates
            if (source := str(getattr(rate, "source", "") or "").strip())
        )
    )
    if sources:
        return "; ".join(sources)
    return "B3 CDI realizado"


def fund_return_cdi_date_range(outputs: Any, cnpj: str) -> tuple[date, date] | None:
    """Return the B3 query window that covers both trailing-12-month and YTD returns."""
    history_by_cnpj = getattr(outputs, "fund_return_history", {}) or {}
    summary_by_cnpj = getattr(outputs, "fund_return_summary", {}) or {}
    history_df = _normalize_identity_frame(history_by_cnpj.get(cnpj, pd.DataFrame()))
    summary_df = _normalize_identity_frame(summary_by_cnpj.get(cnpj, pd.DataFrame()))
    latest_month = _latest_available_month(summary_df, history_df)
    if latest_month is None:
        return None
    start = latest_month - pd.DateOffset(months=11)
    end = latest_month + pd.offsets.MonthEnd(1)
    return start.date(), end.date()


def format_fund_return_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """Format a numeric return matrix for display without mutating the source."""
    output = frame.copy()
    output.attrs.update(frame.attrs)
    for column in output.columns:
        if column == RETURN_SERIES_COLUMN:
            continue
        formatter = _format_bps_pt_br if column in _BPS_COLUMNS else _format_percent_pt_br
        output[column] = output[column].map(formatter)
    return output


def _normalize_identity_frame(value: object) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame) or value.empty:
        return pd.DataFrame()
    frame = value.copy()
    if "class_label" not in frame.columns:
        frame["class_label"] = frame.get("label", "")
    if "class_kind" not in frame.columns:
        frame["class_kind"] = ""
    if "class_key" not in frame.columns:
        frame["class_key"] = ""
    labels = frame["class_label"].fillna("").astype(str).str.strip()
    keys = frame["class_key"].fillna("").astype(str).str.strip()
    kinds = frame["class_kind"].fillna("").astype(str).str.strip()
    fallback_keys = "label:" + kinds + ":" + labels
    frame["__series_key"] = keys.where(keys.ne(""), fallback_keys)
    frame["class_label"] = labels.where(labels.ne(""), keys).replace("", "Cota")
    if "competencia_dt" in frame.columns:
        frame["competencia_dt"] = pd.to_datetime(frame["competencia_dt"], errors="coerce")
        frame = frame.sort_values("competencia_dt", kind="stable")
    return frame


def _latest_available_month(summary_df: pd.DataFrame, history_df: pd.DataFrame) -> pd.Timestamp | None:
    candidates = pd.Series(dtype="datetime64[ns]")
    if not summary_df.empty and "latest_competencia" in summary_df.columns:
        candidates = pd.to_datetime(
            summary_df["latest_competencia"].astype(str),
            format="%m/%Y",
            errors="coerce",
        ).dropna()
    if candidates.empty and not history_df.empty:
        if "competencia_dt" in history_df.columns:
            candidates = pd.to_datetime(history_df["competencia_dt"], errors="coerce").dropna()
        elif "competencia" in history_df.columns:
            candidates = pd.to_datetime(
                history_df["competencia"].astype(str),
                format="%m/%Y",
                errors="coerce",
            ).dropna()
    if candidates.empty:
        return None
    latest = pd.Timestamp(candidates.max())
    return pd.Timestamp(year=latest.year, month=latest.month, day=1)


def _series_identities(summary_df: pd.DataFrame, history_df: pd.DataFrame) -> pd.DataFrame:
    identity_columns = ["__series_key", "class_kind", "class_label"]
    frames: list[pd.DataFrame] = []
    if not history_df.empty:
        frames.append(history_df[identity_columns].drop_duplicates(subset=["__series_key"], keep="last"))
    if not summary_df.empty:
        frames.append(summary_df[identity_columns].drop_duplicates(subset=["__series_key"], keep="last"))
    if not frames:
        return pd.DataFrame(columns=identity_columns)
    identities = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["__series_key"], keep="last")
    return sort_class_display_frame(identities, label_column="class_label")


def _summary_values(summary_lookup: pd.DataFrame, index: pd.Index, column: str) -> pd.Series:
    if summary_lookup.empty or column not in summary_lookup.columns:
        return pd.Series(float("nan"), index=index, dtype="float64").to_numpy()
    values = pd.to_numeric(summary_lookup[column], errors="coerce")
    return values.reindex(index).to_numpy()


def _cdi_summary_values(
    *,
    summary_lookup: pd.DataFrame,
    history_df: pd.DataFrame,
    index: pd.Index,
    latest_month: pd.Timestamp,
    period_start: pd.Timestamp,
    return_column: str,
    status_column: str,
    used_competencias_column: str,
    monthly_cdi_rates: Iterable[Any],
) -> tuple[pd.Series, pd.Series, set[str]]:
    rate_by_month: dict[str, tuple[float, int]] = {}
    for rate in monthly_cdi_rates:
        raw_month_key = getattr(rate, "mes", "")
        month_key = "" if pd.isna(raw_month_key) else str(raw_month_key).strip()
        try:
            monthly_rate = float(getattr(rate, "cdi_mensal"))
            business_days = int(getattr(rate, "dias_uteis"))
        except (TypeError, ValueError, OverflowError):
            continue
        if getattr(rate, "is_complete", True) is False:
            continue
        if month_key and math.isfinite(monthly_rate) and monthly_rate > -1.0 and business_days > 0:
            rate_by_month[month_key] = (monthly_rate, business_days)

    cdi_values: list[float] = []
    implied_spread_values: list[float] = []
    missing_competencias: set[str] = set()
    for series_key in index.astype(str):
        if summary_lookup.empty or series_key not in summary_lookup.index:
            cdi_values.append(float("nan"))
            implied_spread_values.append(float("nan"))
            continue
        row = summary_lookup.loc[series_key]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        return_value = pd.to_numeric(pd.Series([row.get(return_column)]), errors="coerce").iloc[0]
        raw_status = row.get(status_column)
        status = "" if pd.isna(raw_status) else str(raw_status).strip().lower()
        if pd.isna(return_value) or status == "incompleto":
            cdi_values.append(float("nan"))
            implied_spread_values.append(float("nan"))
            continue

        competencias = _used_competencias(
            row=row,
            history_df=history_df,
            series_key=series_key,
            period_start=period_start,
            latest_month=latest_month,
            used_competencias_column=used_competencias_column,
        )
        if not competencias:
            cdi_values.append(float("nan"))
            implied_spread_values.append(float("nan"))
            continue

        log_cdi_factor = 0.0
        total_business_days = 0
        missing_for_row: list[str] = []
        for competencia in competencias:
            month_key = _competencia_to_rate_key(competencia)
            rate_info = rate_by_month.get(month_key)
            if rate_info is None:
                missing_for_row.append(competencia)
                continue
            monthly_rate, business_days = rate_info
            log_cdi_factor += math.log1p(monthly_rate)
            total_business_days += business_days
        if missing_for_row:
            missing_competencias.update(missing_for_row)
            cdi_values.append(float("nan"))
            implied_spread_values.append(float("nan"))
            continue
        cdi_values.append(math.expm1(log_cdi_factor) * 100.0)

        return_decimal = float(return_value) / 100.0
        if (
            not math.isfinite(return_decimal)
            or return_decimal <= -1.0
            or total_business_days <= 0
        ):
            implied_spread_values.append(float("nan"))
            continue
        try:
            implied_spread = math.expm1(
                (252.0 / total_business_days) * (math.log1p(return_decimal) - log_cdi_factor)
            )
        except (OverflowError, ValueError):
            implied_spread_values.append(float("nan"))
            continue
        implied_spread_values.append(implied_spread * 100.0)
    return (
        pd.Series(cdi_values, index=index, dtype="float64").to_numpy(),
        pd.Series(implied_spread_values, index=index, dtype="float64").to_numpy(),
        missing_competencias,
    )


def _valid_benchmark_spreads(values: Mapping[str, float]) -> dict[str, float]:
    output: dict[str, float] = {}
    for raw_key, raw_value in values.items():
        try:
            spread = float(raw_value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(spread) and spread > -1.0:
            output[str(raw_key)] = spread
    return output


def _used_competencias(
    *,
    row: pd.Series,
    history_df: pd.DataFrame,
    series_key: str,
    period_start: pd.Timestamp,
    latest_month: pd.Timestamp,
    used_competencias_column: str,
) -> list[str]:
    raw_used = row.get(used_competencias_column)
    if raw_used is not None and not pd.isna(raw_used):
        explicit = [value.strip() for value in str(raw_used).split(",") if value.strip()]
        if explicit:
            return sorted(set(explicit), key=_competencia_sort_key)

    if history_df.empty or "__series_key" not in history_df.columns:
        history = pd.DataFrame()
    else:
        history = history_df[history_df["__series_key"].astype(str) == series_key].copy()
    if not history.empty and "competencia" in history.columns:
        if "competencia_dt" not in history.columns:
            history["competencia_dt"] = pd.to_datetime(
                history["competencia"].astype(str),
                format="%m/%Y",
                errors="coerce",
            )
        history["retorno_mensal_pct"] = pd.to_numeric(
            history.get("retorno_mensal_pct"),
            errors="coerce",
        )
        history = history[
            history["competencia_dt"].between(period_start, latest_month, inclusive="both")
            & history["retorno_mensal_pct"].notna()
        ]
        competencias = history["competencia"].astype(str).drop_duplicates().tolist()
        if competencias:
            return sorted(competencias, key=_competencia_sort_key)

    return [
        value.strftime("%m/%Y")
        for value in pd.date_range(period_start, latest_month, freq="MS")
    ]


def _competencia_to_rate_key(value: object) -> str:
    parsed = pd.to_datetime(str(value), format="%m/%Y", errors="coerce")
    return "" if pd.isna(parsed) else pd.Timestamp(parsed).strftime("%Y-%m")


def _competencia_sort_key(value: object) -> tuple[int, int]:
    parsed = pd.to_datetime(str(value), format="%m/%Y", errors="coerce")
    if pd.isna(parsed):
        return (0, 0)
    timestamp = pd.Timestamp(parsed)
    return (timestamp.year, timestamp.month)


def _empty_return_matrix(
    month_columns: list[str],
    *,
    include_cdi: bool = False,
    include_benchmark: bool = False,
) -> pd.DataFrame:
    columns = [
        RETURN_SERIES_COLUMN,
        *month_columns,
        RETURN_TRAILING_12M_COLUMN,
        *([RETURN_TRAILING_12M_CDI_COLUMN] if include_cdi else []),
        *([RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN] if include_cdi else []),
        RETURN_YTD_COLUMN,
        *([RETURN_YTD_CDI_COLUMN] if include_cdi else []),
        *([RETURN_YTD_IMPLIED_SPREAD_COLUMN] if include_cdi else []),
        *(
            [
                RETURN_ISSUANCE_SPREAD_COLUMN,
                RETURN_TRAILING_12M_SPREAD_GAP_COLUMN,
                RETURN_YTD_SPREAD_GAP_COLUMN,
            ]
            if include_benchmark
            else []
        ),
    ]
    return pd.DataFrame(columns=columns)


def _format_month_column(value: pd.Timestamp) -> str:
    return f"{_PT_MONTH_ABBR[value.month]}/{str(value.year)[-2:]}"


def _format_percent_pt_br(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/D"
    if not math.isfinite(numeric):
        return "N/D"
    if numeric == 0:
        numeric = 0.0
    formatted = f"{numeric:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{formatted}%"


def _format_bps_pt_br(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/D"
    if not math.isfinite(numeric):
        return "N/D"
    rounded = round(numeric)
    if rounded == 0:
        return "0"
    formatted = f"{abs(rounded):,}".replace(",", ".")
    return f"{'+' if rounded > 0 else '-'}{formatted}"
