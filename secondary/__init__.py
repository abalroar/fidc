"""Módulo de mercado secundário de FIDCs (ANBIMA Feed - Preços & Índices).

Camadas:
- auth / anbima_client: acesso autenticado à API ANBIMA.
- universe: universo de ISINs de cotas de FIDC.
- backfill: coleta diária -> parquet particionado (data/raw).
- aggregate: cruzamento negociações x preços -> agregado mensal (data/curated).
"""
from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

RAW_PRECOS_DIR = DATA_DIR / "raw" / "precos_fidc"
RAW_NEGOCIACOES_DIR = DATA_DIR / "raw" / "negociacoes"

CURATED_DIR = DATA_DIR / "curated"
CURATED_MENSAL = CURATED_DIR / "mensal_fidc.parquet"
CURATED_NEGOCIACOES = CURATED_DIR / "negociacoes_fidc.parquet"
