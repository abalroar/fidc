from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from services import cvm_cadastro
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
    direct_loader = getattr(cvm_cadastro, "list_fidc_catalog", None)
    if callable(direct_loader):
        return direct_loader()

    raw_loader = getattr(cvm_cadastro, "_load_cad_fidc", None)
    if not callable(raw_loader):
        return pd.DataFrame(columns=["cnpj_fundo", "nome_fundo", "situacao"])

    df = raw_loader()
    if df is None or df.empty:
        return pd.DataFrame(columns=["cnpj_fundo", "nome_fundo", "situacao"])

    strip_digits = getattr(cvm_cadastro, "_strip_digits", lambda value: "".join(ch for ch in str(value or "") if ch.isdigit()))
    clean = getattr(cvm_cadastro, "_clean", lambda value: str(value or "").strip())

    cnpj_col = next(
        (column for column in df.columns if str(column).strip().upper() == "CNPJ_FUNDO"),
        None,
    )
    if cnpj_col is None:
        return pd.DataFrame(columns=["cnpj_fundo", "nome_fundo", "situacao"])

    name_candidates = ["DENOM_SOCIAL", "DENOM_COMERC", "NM_FUNDO", "NOME_FUNDO"]
    name_col = next((column for column in name_candidates if column in df.columns), None)
    situacao_col = next((column for column in ("SIT", "SITUACAO") if column in df.columns), None)

    catalog = pd.DataFrame(
        {
            "cnpj_fundo": df[cnpj_col].map(strip_digits),
            "nome_fundo": df[name_col].map(clean) if name_col else "",
            "situacao": df[situacao_col].map(clean) if situacao_col else "",
        }
    )
    catalog = catalog[catalog["cnpj_fundo"].astype(str).str.len() == 14].copy()
    if name_col:
        catalog["nome_fundo"] = catalog["nome_fundo"].replace("", pd.NA)
    catalog["nome_fundo"] = catalog["nome_fundo"].fillna(catalog["cnpj_fundo"])
    return catalog.drop_duplicates(subset=["cnpj_fundo"], keep="last").sort_values(["nome_fundo", "cnpj_fundo"]).reset_index(drop=True)


def get_portfolio_status_caption() -> str:
    config = get_portfolio_store_config()
    if config.backend == "github" and config.repo:
        return f"Carteiras persistidas via GitHub: `{config.repo}` · branch `{config.branch}`."
    return "Carteiras persistidas localmente neste ambiente."
