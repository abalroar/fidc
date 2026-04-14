"""CVM Dados Abertos — cadastro de FIDCs.

Fetches fund registration data (Administrador, Gestor, Custodiante) from the
CVM open-data CSV at dados.cvm.gov.br.  The full CSV (~400 KB) is downloaded
once per process and cached in-memory via lru_cache, so subsequent lookups
within the same Streamlit session are instant.

The Informe Mensal Estruturado (Fundos.NET) does NOT carry Gestor or
Custodiante fields — only NR_CNPJ_ADM (administrator CNPJ).  This module
fills that gap using the fund registration dataset, which is updated daily
by the CVM.

URL: https://dados.cvm.gov.br/dados/FIDC/CAD/DADOS/cad_fidc.csv
Encoding: latin-1   Separator: ;
"""

from __future__ import annotations

import io
import re
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any

import pandas as pd


_CAD_FIDC_URL = "https://dados.cvm.gov.br/dados/FIDC/CAD/DADOS/cad_fidc.csv"
_REQUEST_TIMEOUT = 15  # seconds


def _strip_digits(value: Any) -> str:
    """Return only the digit characters of a string (normalises CNPJ/CPF)."""
    return re.sub(r"\D", "", str(value or ""))


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.upper() in {"", "N/A", "NAO", "NÃO", "NÃO INFORMADO", "NAO INFORMADO"}:
        return ""
    return text


@lru_cache(maxsize=1)
def _load_cad_fidc() -> pd.DataFrame | None:
    """Download and parse the CVM FIDC registration CSV.

    Cached for the lifetime of the Python process (one download per session).
    Returns None if the download fails for any reason.
    """
    try:
        req = urllib.request.Request(
            _CAD_FIDC_URL,
            headers={"User-Agent": "fidc-dashboard/1.0 (dados.cvm.gov.br open data)"},
        )
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            raw: bytes = resp.read()
        df = pd.read_csv(
            io.BytesIO(raw),
            sep=";",
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
        )
        # Normalise column names: strip whitespace
        df.columns = [c.strip() for c in df.columns]
        return df
    except urllib.error.HTTPError as exc:
        try:
            exc.close()
        except Exception:  # noqa: BLE001
            pass
        return None
    except Exception:  # noqa: BLE001
        return None


def fetch_fidc_participantes(cnpj_fundo: str) -> dict[str, str]:
    """Look up Administrador, Gestor and Custodiante for a given fund CNPJ.

    Args:
        cnpj_fundo: Fund CNPJ — formatted (XX.XXX.XXX/XXXX-XX) or raw digits.

    Returns:
        Dict with keys:
            nm_admin        — Administrador name  (empty str if unavailable)
            nm_gestor       — Gestor name
            nm_custodiante  — Custodiante name
            cnpj_gestor     — Gestor CNPJ (raw digits)
            cnpj_custodiante— Custodiante CNPJ (raw digits)
        All values are empty strings on failure / unavailability.
    """
    empty: dict[str, str] = {
        "nm_admin": "",
        "nm_gestor": "",
        "nm_custodiante": "",
        "cnpj_gestor": "",
        "cnpj_custodiante": "",
    }

    cnpj_digits = _strip_digits(cnpj_fundo)
    if len(cnpj_digits) != 14:
        return empty

    df = _load_cad_fidc()
    if df is None or df.empty:
        return empty

    # Identify the CNPJ column (CVM uses CNPJ_FUNDO)
    cnpj_col = next(
        (c for c in df.columns if re.fullmatch(r"CNPJ_FUNDO", c, re.IGNORECASE)),
        None,
    )
    if cnpj_col is None:
        return empty

    df = df.copy()
    df["_cnpj_norm"] = df[cnpj_col].map(_strip_digits)
    match = df[df["_cnpj_norm"] == cnpj_digits]
    if match.empty:
        return empty

    # Prefer the most recent active record; fall back to any record
    if "SIT" in df.columns:
        active = match[match["SIT"].str.strip().str.upper() == "EM FUNCIONAMENTO NORMAL"]
        row = active.iloc[-1] if not active.empty else match.iloc[-1]
    else:
        row = match.iloc[-1]

    def _col(*candidates: str) -> str:
        for c in candidates:
            if c in df.columns:
                return _clean(row.get(c, ""))
        return ""

    return {
        "nm_admin": _col("NM_ADMIN"),
        "nm_gestor": _col("NM_GESTOR"),
        "nm_custodiante": _col("NM_CUSTODIANTE"),
        "cnpj_gestor": _strip_digits(_col("CPF_CNPJ_GESTOR", "CNPJ_GESTOR")),
        "cnpj_custodiante": _strip_digits(_col("CNPJ_CUSTODIANTE")),
    }


def list_fidc_catalog() -> pd.DataFrame:
    """Return a lightweight searchable catalog of FIDCs from CVM registration data."""
    df = _load_cad_fidc()
    if df is None or df.empty:
        return pd.DataFrame(columns=["cnpj_fundo", "nome_fundo", "situacao"])

    cnpj_col = next(
        (c for c in df.columns if re.fullmatch(r"CNPJ_FUNDO", c, re.IGNORECASE)),
        None,
    )
    if cnpj_col is None:
        return pd.DataFrame(columns=["cnpj_fundo", "nome_fundo", "situacao"])

    name_candidates = [
        "DENOM_SOCIAL",
        "DENOM_COMERC",
        "NM_FUNDO",
        "NOME_FUNDO",
    ]
    name_col = next((column for column in name_candidates if column in df.columns), None)
    situacao_col = next((column for column in ("SIT", "SITUACAO") if column in df.columns), None)

    catalog = pd.DataFrame(
        {
            "cnpj_fundo": df[cnpj_col].map(_strip_digits),
            "nome_fundo": df[name_col].map(_clean) if name_col else "",
            "situacao": df[situacao_col].map(_clean) if situacao_col else "",
        }
    )
    catalog = catalog[catalog["cnpj_fundo"].str.len() == 14].copy()
    if name_col:
        catalog["nome_fundo"] = catalog["nome_fundo"].replace("", pd.NA)
    catalog["nome_fundo"] = catalog["nome_fundo"].fillna(catalog["cnpj_fundo"])
    catalog = catalog.drop_duplicates(subset=["cnpj_fundo"], keep="last")
    return catalog.sort_values(["nome_fundo", "cnpj_fundo"]).reset_index(drop=True)
