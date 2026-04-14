from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from services.cvm_cadastro import list_fidc_catalog
from services.portfolio_store import (
    PortfolioRecord,
    build_portfolio_store,
    resolve_portfolio_store_config,
)

_cache_data = getattr(st, "cache_data", None)
if callable(_cache_data):
    _cache_data_decorator = _cache_data(show_spinner=False)
else:
    def _cache_data_decorator(func):  # type: ignore[misc]
        return func


def _secrets_to_dict() -> dict[str, Any]:
    try:
        return dict(st.secrets)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return {}


def get_portfolio_store_config():
    return resolve_portfolio_store_config(secrets_mapping=_secrets_to_dict())


def _portfolio_store_signature() -> str:
    config = get_portfolio_store_config()
    return json.dumps(
        {
            "backend": config.backend,
            "repo": config.repo,
            "branch": config.branch,
            "path": config.path,
            "local_path": config.local_path,
            "api_base_url": config.api_base_url,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


@_cache_data_decorator
def list_saved_portfolios_cached(signature: str) -> list[dict[str, Any]]:
    _ = signature
    store = build_portfolio_store(get_portfolio_store_config())
    return [portfolio.to_dict() for portfolio in store.list_portfolios()]


def list_saved_portfolios() -> list[PortfolioRecord]:
    signature = _portfolio_store_signature()
    return [PortfolioRecord.from_dict(item) for item in list_saved_portfolios_cached(signature)]


def save_portfolio_record(portfolio: PortfolioRecord) -> PortfolioRecord:
    store = build_portfolio_store(get_portfolio_store_config())
    stored = store.save_portfolio(portfolio)
    list_saved_portfolios_cached.clear()
    return stored


def delete_portfolio_record(portfolio_id: str) -> None:
    store = build_portfolio_store(get_portfolio_store_config())
    store.delete_portfolio(portfolio_id)
    list_saved_portfolios_cached.clear()


@_cache_data_decorator
def load_fidc_catalog_cached() -> pd.DataFrame:
    return list_fidc_catalog()


def get_portfolio_status_caption() -> str:
    config = get_portfolio_store_config()
    if config.backend == "github" and config.repo:
        return f"Carteiras persistidas via GitHub: `{config.repo}` · branch `{config.branch}`."
    return "Carteiras persistidas localmente neste ambiente."
