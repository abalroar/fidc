from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


MELI_PDF_TARGET_COMPETENCIA = "11/2025"
MELI_PDF_TARGETS: tuple[dict[str, object], ...] = (
    {
        "metric": "Carteira ex-360",
        "column": "carteira_ex360",
        "target": 7_141_000_000.0,
        "unit": "R$",
    },
    {
        "metric": "NPL 1-90d",
        "column": "npl_1_90",
        "target": 600_000_000.0,
        "unit": "R$",
    },
    {
        "metric": "NPL 91-360d",
        "column": "npl_91_360",
        "target": 1_012_000_000.0,
        "unit": "R$",
    },
    {
        "metric": "NPL 1-90d / carteira ex-360",
        "column": "npl_1_90_pct",
        "target": 8.4,
        "unit": "%",
    },
    {
        "metric": "NPL 91-360d / carteira ex-360",
        "column": "npl_91_360_pct",
        "target": 14.2,
        "unit": "%",
    },
    {
        "metric": "NPL 1-360d / carteira ex-360",
        "column": "npl_1_360_pct",
        "target": 22.6,
        "unit": "%",
    },
    {
        "metric": "Crescimento m/m carteira ex-360",
        "column": "carteira_ex360_mom_pct",
        "target": 1.0,
        "unit": "%",
    },
    {
        "metric": "Crescimento a/a carteira ex-360",
        "column": "carteira_ex360_yoy_pct",
        "target": 0.0,
        "unit": "%",
    },
    {
        "metric": "Roll 61-90 / carteira a vencer M-3",
        "column": "roll_61_90_m3_pct",
        "target": 3.0,
        "unit": "%",
    },
    {
        "metric": "Roll 151-180 / carteira a vencer M-6",
        "column": "roll_151_180_m6_pct",
        "target": 2.7,
        "unit": "%",
    },
    {
        "metric": "Duration",
        "column": "duration_months",
        "target": 7.9,
        "unit": "meses",
    },
)

MATURITY_CURRENT_COLUMNS: tuple[str, ...] = (
    "prazo_venc_30",
    "prazo_venc_31_60",
    "prazo_venc_61_90",
    "prazo_venc_91_120",
    "prazo_venc_121_150",
    "prazo_venc_151_180",
    "prazo_venc_181_360",
    "prazo_venc_361_720",
    "prazo_venc_721_1080",
    "prazo_venc_1080",
)

EXPECTED_MELI_CREDIT_FUND_TYPES: tuple[str, ...] = (
    "Mercado Crédito",
    "Mercado Crédito I",
    "Mercado Crédito II",
)

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
    pdf_reconciliation: pd.DataFrame
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
    warnings.extend(_universe_warnings(fund_monitor))
    audit_table = build_monitor_audit_table(consolidated_monitor=consolidated_monitor, fund_monitor=fund_monitor)
    pdf_reconciliation = build_pdf_reconciliation_table(consolidated_monitor)
    return MeliMonitorOutputs(
        consolidated_monitor=consolidated_monitor,
        fund_monitor=fund_monitor,
        consolidated_cohorts=consolidated_cohorts,
        fund_cohorts=fund_cohorts,
        audit_table=audit_table,
        pdf_reconciliation=pdf_reconciliation,
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
            "carteira_a_vencer",
            "atraso_ate30",
            "atraso_31_60",
            "atraso_61_90",
            "atraso_91_120",
            "atraso_121_150",
            "atraso_151_180",
            "atraso_181_360",
            *MATURITY_CURRENT_COLUMNS,
            "pdd_ex360",
            "npl_over90_ex360",
            "duration_months",
        ],
    )
    derived_current = df[list(MATURITY_CURRENT_COLUMNS)].sum(axis=1, min_count=1)
    df["carteira_a_vencer"] = df["carteira_a_vencer"].where(df["carteira_a_vencer"].notna(), derived_current)
    df["npl_1_90"] = df[["atraso_ate30", "atraso_31_60", "atraso_61_90"]].sum(axis=1, min_count=1)
    df["npl_91_360"] = df[["atraso_91_120", "atraso_121_150", "atraso_151_180", "atraso_181_360"]].sum(axis=1, min_count=1)
    df["npl_1_90_pct"] = _safe_div_pct(df["npl_1_90"], df["carteira_ex360"])
    df["npl_91_360_pct"] = _safe_div_pct(df["npl_91_360"], df["carteira_ex360"])
    df["npl_1_360_pct"] = _safe_div_pct(df["npl_1_90"] + df["npl_91_360"], df["carteira_ex360"])
    df["roll_61_90_m3_den"] = df["carteira_a_vencer"].shift(3)
    df["roll_151_180_m6_den"] = df["carteira_a_vencer"].shift(6)
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
            "carteira_a_vencer",
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


def build_pdf_reconciliation_table(monitor_df: pd.DataFrame) -> pd.DataFrame:
    columns = ["Métrica", "Competência", "Valor app", "Valor PDF", "Diferença", "Unidade", "Status"]
    if monitor_df is None or monitor_df.empty:
        return pd.DataFrame(
            [
                {
                    "Métrica": "PDF MELI",
                    "Competência": MELI_PDF_TARGET_COMPETENCIA,
                    "Valor app": pd.NA,
                    "Valor PDF": pd.NA,
                    "Diferença": pd.NA,
                    "Unidade": "",
                    "Status": "Base consolidada vazia.",
                }
            ],
            columns=columns,
        )
    df = monitor_df.copy()
    competencia_text = df.get("competencia", pd.Series(index=df.index, dtype="object")).astype(str)
    target_rows = df[competencia_text.eq(MELI_PDF_TARGET_COMPETENCIA)]
    if target_rows.empty:
        return pd.DataFrame(
            [
                {
                    "Métrica": "PDF MELI",
                    "Competência": MELI_PDF_TARGET_COMPETENCIA,
                    "Valor app": pd.NA,
                    "Valor PDF": pd.NA,
                    "Diferença": pd.NA,
                    "Unidade": "",
                    "Status": "Competência 11/2025 ausente na janela carregada.",
                }
            ],
            columns=columns,
        )
    row = target_rows.iloc[-1]
    rows: list[dict[str, object]] = []
    for target in MELI_PDF_TARGETS:
        app_value = _num(row.get(str(target["column"])))
        pdf_value = float(target["target"])
        diff = app_value - pdf_value if app_value is not None else pd.NA
        rows.append(
            {
                "Métrica": target["metric"],
                "Competência": MELI_PDF_TARGET_COMPETENCIA,
                "Valor app": app_value,
                "Valor PDF": pdf_value,
                "Diferença": diff,
                "Unidade": target["unit"],
                "Status": _reconciliation_status(diff, unit=str(target["unit"])),
            }
        )
    return pd.DataFrame(rows, columns=columns)


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
    if "carteira_a_vencer" not in df.columns or pd.to_numeric(df["carteira_a_vencer"], errors="coerce").fillna(0).le(0).all():
        warnings.append(f"{scope}: roll rates não calculáveis porque a carteira a vencer total está ausente ou zerada.")
    if "duration_months" not in df.columns or pd.to_numeric(df["duration_months"], errors="coerce").isna().all():
        warnings.append(f"{scope}: duration não calculável pela malha de vencimentos.")
    return warnings


def _universe_warnings(fund_monitor: dict[str, pd.DataFrame]) -> list[str]:
    if not fund_monitor:
        return []
    fund_types: set[str] = set()
    unexpected: list[str] = []
    for cnpj, frame in fund_monitor.items():
        name = str(frame["fund_name"].dropna().iloc[0]) if frame is not None and not frame.empty and "fund_name" in frame.columns and frame["fund_name"].notna().any() else cnpj
        normalized = _normalize_text(name)
        fund_type = _classify_meli_credit_fund(normalized)
        if fund_type:
            fund_types.add(fund_type)
        if any(token in normalized for token in ("seller", "factoring", "antecip", "vendedor", "fornecedor")):
            unexpected.append(name)
    warnings: list[str] = []
    missing = [fund_type for fund_type in EXPECTED_MELI_CREDIT_FUND_TYPES if fund_type not in fund_types]
    if missing:
        warnings.append("Universo MELI: fundos de crédito esperados ausentes ou sem nome reconhecido: " + ", ".join(missing) + ".")
    if unexpected:
        warnings.append("Universo MELI: a carteira contém fundos com perfil possivelmente fora do PDF de crédito: " + ", ".join(unexpected) + ".")
    return warnings


def _classify_meli_credit_fund(normalized_name: str) -> str | None:
    if "mercado credito ii" in normalized_name or "mercado credito 2" in normalized_name:
        return "Mercado Crédito II"
    if "mercado credito i" in normalized_name or "mercado credito 1" in normalized_name:
        return "Mercado Crédito I"
    if "mercado credito" in normalized_name:
        return "Mercado Crédito"
    return None


def _ensure_numeric_columns(df: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column not in df.columns:
            df[column] = pd.NA
        df[column] = pd.to_numeric(df[column], errors="coerce")


def _safe_div_pct(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    return (num / den).where(den > 0).mul(100.0)


def _reconciliation_status(diff: object, *, unit: str) -> str:
    numeric = _num(diff)
    if numeric is None:
        return "Não calculável no app."
    tolerance = 0.15 if unit in {"%", "meses"} else 1_000_000.0
    if abs(numeric) <= tolerance:
        return "OK dentro da tolerância."
    return "Divergente."


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


def _normalize_text(value: object) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.lower().replace("-", " ").replace("_", " ").split())


def _empty_monitor_base() -> pd.DataFrame:
    return pd.DataFrame(columns=["fund_name", "cnpj", "competencia", "competencia_dt"])
