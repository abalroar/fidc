from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


COHORT_STEPS: tuple[tuple[str, str, int], ...] = (
    ("M1", "atraso_ate30", 1),
    ("M2", "atraso_31_60", 2),
    ("M3", "atraso_61_90", 3),
    ("M4", "atraso_91_120", 4),
    ("M5", "atraso_121_150", 5),
    ("M6", "atraso_151_180", 6),
)


@dataclass(frozen=True)
class MeliMonitorOutputs:
    consolidated_monitor: pd.DataFrame
    fund_monitor: dict[str, pd.DataFrame]
    consolidated_cohorts: pd.DataFrame
    fund_cohorts: dict[str, pd.DataFrame]
    audit_table: pd.DataFrame
    warnings: list[str]


def build_meli_monitor_outputs(outputs) -> MeliMonitorOutputs:  # noqa: ANN001
    fund_monitor: dict[str, pd.DataFrame] = {}
    fund_cohorts: dict[str, pd.DataFrame] = {}
    warnings: list[str] = []
    for cnpj, monthly in getattr(outputs, "fund_monthly", {}).items():
        monitor = build_monitor_base(monthly)
        fund_monitor[cnpj] = monitor
        fund_cohorts[cnpj] = build_cohort_matrix(monitor)
        warnings.extend(_monitor_warnings(monitor, scope=cnpj))

    consolidated_monitor = build_monitor_base(getattr(outputs, "consolidated_monthly", pd.DataFrame()))
    consolidated_cohorts = build_cohort_matrix(consolidated_monitor)
    warnings.extend(_monitor_warnings(consolidated_monitor, scope="CONSOLIDADO"))
    audit_table = build_monitor_audit_table(consolidated_monitor=consolidated_monitor, fund_monitor=fund_monitor)
    return MeliMonitorOutputs(
        consolidated_monitor=consolidated_monitor,
        fund_monitor=fund_monitor,
        consolidated_cohorts=consolidated_cohorts,
        fund_cohorts=fund_cohorts,
        audit_table=audit_table,
        warnings=warnings,
    )


def build_monitor_base(monthly_df: pd.DataFrame) -> pd.DataFrame:
    if monthly_df is None or monthly_df.empty:
        return _empty_monitor_base()
    df = monthly_df.copy()
    if "competencia_dt" not in df.columns:
        df["competencia_dt"] = pd.to_datetime(df.get("competencia"), errors="coerce")
    else:
        df["competencia_dt"] = pd.to_datetime(df["competencia_dt"], errors="coerce")
    df = df.sort_values("competencia_dt").reset_index(drop=True)
    _ensure_numeric_columns(
        df,
        [
            "carteira_ex360",
            "carteira_bruta",
            "carteira_em_dia",
            "atraso_ate30",
            "atraso_31_60",
            "atraso_61_90",
            "atraso_91_120",
            "atraso_121_150",
            "atraso_151_180",
            "atraso_181_360",
            "prazo_venc_30",
            "pdd_ex360",
            "npl_over90_ex360",
            "duration_months",
        ],
    )
    df["npl_1_90"] = df[["atraso_ate30", "atraso_31_60", "atraso_61_90"]].sum(axis=1, min_count=1)
    df["npl_91_360"] = df[["atraso_91_120", "atraso_121_150", "atraso_151_180", "atraso_181_360"]].sum(axis=1, min_count=1)
    df["npl_1_90_pct"] = _safe_div_pct(df["npl_1_90"], df["carteira_ex360"])
    df["npl_91_360_pct"] = _safe_div_pct(df["npl_91_360"], df["carteira_ex360"])
    df["npl_1_360_pct"] = _safe_div_pct(df["npl_1_90"] + df["npl_91_360"], df["carteira_ex360"])
    df["roll_61_90_m3_den"] = df["carteira_em_dia"].shift(3)
    df["roll_151_180_m6_den"] = df["carteira_em_dia"].shift(6)
    df["roll_61_90_m3_pct"] = _safe_div_pct(df["atraso_61_90"], df["roll_61_90_m3_den"])
    df["roll_151_180_m6_pct"] = _safe_div_pct(df["atraso_151_180"], df["roll_151_180_m6_den"])
    df["carteira_ex360_mom_pct"] = df["carteira_ex360"].pct_change(fill_method=None) * 100.0
    df["carteira_ex360_yoy_pct"] = (df["carteira_ex360"] / df["carteira_ex360"].shift(12) - 1.0) * 100.0
    df["pdd_npl90_ex360_pct"] = _safe_div_pct(df["pdd_ex360"], df["npl_over90_ex360"])
    return df


def build_cohort_matrix(monitor_df: pd.DataFrame) -> pd.DataFrame:
    if monitor_df is None or monitor_df.empty:
        return pd.DataFrame(columns=["cohort", "cohort_dt", "mes_ciclo", "ordem", "valor_pct", "numerador", "denominador"])
    df = monitor_df.sort_values("competencia_dt").reset_index(drop=True).copy()
    rows: list[dict[str, object]] = []
    for idx, row in df.iterrows():
        denominator = _num(row.get("prazo_venc_30"))
        if denominator is None or denominator <= 0:
            continue
        cohort = _format_competencia(row.get("competencia_dt"), row.get("competencia"))
        for order, (label, bucket_col, lag_months) in enumerate(COHORT_STEPS, start=1):
            future_idx = idx + lag_months
            if future_idx >= len(df):
                continue
            numerator = _num(df.iloc[future_idx].get(bucket_col))
            if numerator is None:
                continue
            rows.append(
                {
                    "cohort": cohort,
                    "cohort_dt": row.get("competencia_dt"),
                    "mes_ciclo": label,
                    "ordem": order,
                    "valor_pct": numerator / denominator * 100.0,
                    "numerador": numerator,
                    "denominador": denominator,
                }
            )
    return pd.DataFrame(rows)


def build_monitor_audit_table(*, consolidated_monitor: pd.DataFrame, fund_monitor: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for frame in [consolidated_monitor, *fund_monitor.values()]:
        if frame is None or frame.empty:
            continue
        cols = [
            "fund_name",
            "cnpj",
            "competencia",
            "carteira_ex360",
            "npl_1_90",
            "npl_91_360",
            "npl_1_90_pct",
            "npl_91_360_pct",
            "roll_61_90_m3_pct",
            "roll_61_90_m3_den",
            "roll_151_180_m6_pct",
            "roll_151_180_m6_den",
            "duration_months",
            "carteira_ex360_mom_pct",
            "carteira_ex360_yoy_pct",
            "pdd_npl90_ex360_pct",
        ]
        available = [col for col in cols if col in frame.columns]
        frames.append(frame[available].copy())
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def latest_row(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype="object")
    return df.sort_values("competencia_dt").iloc[-1]


def _monitor_warnings(df: pd.DataFrame, *, scope: str) -> list[str]:
    if df is None or df.empty:
        return [f"{scope}: base vazia."]
    warnings: list[str] = []
    if "prazo_venc_30" not in df.columns or pd.to_numeric(df["prazo_venc_30"], errors="coerce").fillna(0).le(0).all():
        warnings.append(f"{scope}: cohorts não calculáveis porque a carteira a vencer em 30 dias está ausente ou zerada.")
    if "duration_months" not in df.columns or pd.to_numeric(df["duration_months"], errors="coerce").isna().all():
        warnings.append(f"{scope}: duration não calculável pela malha de vencimentos.")
    return warnings


def _ensure_numeric_columns(df: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column not in df.columns:
            df[column] = pd.NA
        df[column] = pd.to_numeric(df[column], errors="coerce")


def _safe_div_pct(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    return (num / den).where(den > 0).mul(100.0)


def _num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return None
    return float(parsed)


def _format_competencia(competencia_dt: object, fallback: object) -> str:
    ts = pd.to_datetime(competencia_dt, errors="coerce")
    if pd.isna(ts):
        return str(fallback or "N/D")
    return f"{int(ts.month):02d}/{int(ts.year)}"


def _empty_monitor_base() -> pd.DataFrame:
    return pd.DataFrame(columns=["fund_name", "cnpj", "competencia", "competencia_dt"])
