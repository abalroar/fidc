"""Universo de ISINs de cotas de FIDC.

O REUNE não tem rótulo literal "FIDC" (cotas entram como "CFF"); o isolamento
é feito cruzando o ISIN da negociação contra o universo de ISINs retornado
pelo endpoint de preços indicativos de FIDC.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Iterable

from secondary import RAW_PRECOS_DIR
from secondary.anbima_client import precos_fidc

logger = logging.getLogger(__name__)


def universo_fidc_isins(datas_amostra: Iterable[str | dt.date]) -> set[str]:
    """Coleta ISINs de FIDC consultando o endpoint de preços nas datas dadas.

    Datas sem dado são ignoradas silenciosamente (liquidez baixa é normal).
    """
    isins: set[str] = set()
    for data in datas_amostra:
        for row in precos_fidc(data):
            isin = str(row.get("isin") or "").strip()
            if isin:
                isins.add(isin)
    logger.info("Universo FIDC: %s ISINs a partir da amostra de datas.", len(isins))
    return isins


def universo_fidc_isins_de_raw() -> set[str]:
    """Universo de ISINs a partir do parquet cru já baixado (offline, sem API)."""
    import pandas as pd

    if not RAW_PRECOS_DIR.exists():
        return set()
    frames = pd.read_parquet(RAW_PRECOS_DIR, columns=["isin"])
    return {str(v).strip() for v in frames["isin"].dropna().unique() if str(v).strip()}
