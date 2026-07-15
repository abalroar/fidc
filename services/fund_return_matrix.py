from __future__ import annotations

import math
from typing import Any

import pandas as pd

from services.fundonet_dashboard import sort_class_display_frame


RETURN_SERIES_COLUMN = "Série"
RETURN_TRAILING_12M_COLUMN = "Ac. Últ. 12m (%)"
RETURN_YTD_COLUMN = "Acumulado YTD (%)"

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


def build_fund_return_matrix(outputs: Any, cnpj: str, months: int = 12) -> pd.DataFrame:
    """Build the shared per-series return table using percentage-point values."""
    if isinstance(months, bool) or not isinstance(months, int) or months <= 0:
        raise ValueError("months must be a positive integer")

    history_by_cnpj = getattr(outputs, "fund_return_history", {}) or {}
    summary_by_cnpj = getattr(outputs, "fund_return_summary", {}) or {}
    history_df = _normalize_identity_frame(history_by_cnpj.get(cnpj, pd.DataFrame()))
    summary_df = _normalize_identity_frame(summary_by_cnpj.get(cnpj, pd.DataFrame()))
    latest_month = _latest_available_month(summary_df, history_df)
    if latest_month is None:
        return _empty_return_matrix([])

    month_starts = list(pd.date_range(end=latest_month, periods=months, freq="MS"))
    competencias = [value.strftime("%m/%Y") for value in month_starts]
    month_columns = [_format_month_column(value) for value in month_starts]
    identities = _series_identities(summary_df, history_df)
    if identities.empty:
        return _empty_return_matrix(month_columns)

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
    output[RETURN_YTD_COLUMN] = _summary_values(
        summary_lookup,
        output.index,
        "retorno_ano_pct",
    )
    return output.reset_index(drop=True)


def format_fund_return_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """Format a numeric return matrix for display without mutating the source."""
    output = frame.copy()
    for column in output.columns:
        if column == RETURN_SERIES_COLUMN:
            continue
        output[column] = output[column].map(_format_percent_pt_br)
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


def _empty_return_matrix(month_columns: list[str]) -> pd.DataFrame:
    columns = [
        RETURN_SERIES_COLUMN,
        *month_columns,
        RETURN_TRAILING_12M_COLUMN,
        RETURN_YTD_COLUMN,
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
