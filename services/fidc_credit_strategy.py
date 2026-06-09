from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


DEFAULT_DB_PATH = Path("data/fidc_credit_strategy/fidc_credit_strategy.sqlite")


def database_path(path: Path | None = None) -> Path:
    return path or DEFAULT_DB_PATH


def database_exists(path: Path | None = None) -> bool:
    return database_path(path).exists()


def list_tables(path: Path | None = None) -> list[str]:
    db = database_path(path)
    if not db.exists():
        return []
    with sqlite3.connect(db) as conn:
        rows = conn.execute("select name from sqlite_master where type='table' order by name").fetchall()
    return [row[0] for row in rows]


def load_table(table_name: str, path: Path | None = None) -> pd.DataFrame:
    db = database_path(path)
    if not db.exists():
        return pd.DataFrame()
    safe_tables = set(list_tables(db))
    if table_name not in safe_tables:
        return pd.DataFrame()
    with sqlite3.connect(db) as conn:
        return pd.read_sql_query(f"select * from {table_name}", conn)


def load_metadata(path: Path | None = None) -> dict[str, str]:
    frame = load_table("study_metadata", path)
    if frame.empty or not {"key", "value"}.issubset(frame.columns):
        return {}
    return dict(zip(frame["key"].astype(str), frame["value"].astype(str), strict=False))


def load_strategy_tables(path: Path | None = None) -> dict[str, pd.DataFrame]:
    names = [
        "fund_universe",
        "regulatory_feature_heatmap_year",
        "regulatory_feature_heatmap_current",
        "subordination_by_sector_year",
        "subordination_fund_detail",
        "pricing_senior_by_sector_year",
        "pricing_quota_by_sector_year",
        "pricing_tranche_enriched",
        "market_opportunities",
        "ime_cache_summary",
        "ime_current_snapshot",
        "ime_current_subordination_by_sector_year",
        "ime_cota_price_by_sector_year",
        "manual_review_queue",
    ]
    return {name: load_table(name, path) for name in names}
