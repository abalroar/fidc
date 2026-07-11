"""Agregação: cruza negociações REUNE x preços indicativos FIDC -> curated.

Saídas:
    data/curated/negociacoes_fidc.parquet  (nível negociação, enriquecido)
    data/curated/mensal_fidc.parquet       (agregado mês x emissor x cnpj x isin)

Métrica-chave:
    agio_desagio_impl_pct = (vl_pu_negociado / pu_indicativo - 1) * 100
comparando o preço praticado (REUNE) com o PU indicativo ANBIMA do mesmo
isin+data. percent_pu_par (marcação oficial sobre o par) também é exposto.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from secondary import (
    CURATED_DIR,
    CURATED_MENSAL,
    CURATED_NEGOCIACOES,
    RAW_NEGOCIACOES_DIR,
    RAW_PRECOS_DIR,
)

logger = logging.getLogger(__name__)

_NUM_NEG = ["qtd_negociada", "vl_pu_negociado", "vl_volume_negociado", "taxa_negociada"]
_NUM_PRECOS = ["pu", "percent_pu_par", "taxa_indicativa", "duration"]


def _ler_raw(raw_dir, colunas: list[str] | None = None) -> pd.DataFrame:
    if not raw_dir.exists():
        raise FileNotFoundError(
            f"{raw_dir} não existe. Rode antes: python -m secondary.backfill --mes YYYY-MM"
        )
    return pd.read_parquet(raw_dir, columns=colunas)


def cruzar_negociacoes_precos(
    negociacoes: pd.DataFrame, precos: pd.DataFrame
) -> pd.DataFrame:
    """Filtra o REUNE ao universo FIDC (por ISIN) e anexa o PU indicativo.

    Join por (isin, data): data_operacao da negociação x data_referencia do
    preço indicativo. Negociação sem preço indicativo no dia fica com
    agio_desagio_impl_pct nulo (não é descartada).
    """
    neg = negociacoes.copy()
    prc = precos.copy()

    neg["isin"] = neg["isin"].astype(str).str.strip()
    prc["isin"] = prc["isin"].astype(str).str.strip()
    neg["data_operacao"] = pd.to_datetime(neg["data_operacao"], errors="coerce")
    prc["data_referencia"] = pd.to_datetime(prc["data_referencia"], errors="coerce")
    for col in _NUM_NEG:
        neg[col] = pd.to_numeric(neg[col], errors="coerce")
    for col in _NUM_PRECOS:
        prc[col] = pd.to_numeric(prc[col], errors="coerce")

    universo = set(prc.loc[prc["isin"] != "", "isin"].unique())
    fidc = neg[neg["isin"].isin(universo)].copy()
    logger.info(
        "REUNE: %s negociações no total; %s casadas com ISINs de FIDC (%s ISINs no universo).",
        len(neg), len(fidc), len(universo),
    )

    ref = (
        prc.sort_values("data_referencia")
        .drop_duplicates(subset=["isin", "data_referencia"], keep="last")
        .loc[:, ["isin", "data_referencia", "nome", "pu", "percent_pu_par", "taxa_indicativa"]]
        .rename(columns={"pu": "pu_indicativo", "taxa_indicativa": "taxa_indicativa_anbima"})
    )
    fidc = fidc.merge(
        ref,
        left_on=["isin", "data_operacao"],
        right_on=["isin", "data_referencia"],
        how="left",
    ).drop(columns=["data_referencia"])

    pu = fidc["pu_indicativo"]
    fidc["agio_desagio_impl_pct"] = np.where(
        pu > 0, (fidc["vl_pu_negociado"] / pu - 1.0) * 100.0, np.nan
    )
    fidc["mes"] = fidc["data_operacao"].dt.to_period("M").astype(str)
    return fidc


def agregar_mensal(negociacoes_fidc: pd.DataFrame) -> pd.DataFrame:
    """Agrega mês a mês por emissor/cnpj/isin.

    taxa_media é ponderada pelo volume negociado (fallback: média simples
    quando o volume do grupo é nulo/zero).
    """
    df = negociacoes_fidc.copy()
    df["_vol_taxa"] = df["taxa_negociada"] * df["vl_volume_negociado"]
    df["_vol_com_taxa"] = df["vl_volume_negociado"].where(df["taxa_negociada"].notna())

    grupos = df.groupby(["mes", "emissor", "cnpj_emissor", "isin"], dropna=False)
    mensal = grupos.agg(
        volume=("vl_volume_negociado", "sum"),
        n_operacoes=("vl_volume_negociado", "size"),
        qtd_negociada=("qtd_negociada", "sum"),
        taxa_media_simples=("taxa_negociada", "mean"),
        soma_vol_taxa=("_vol_taxa", "sum"),
        soma_vol_com_taxa=("_vol_com_taxa", "sum"),
        agio_desagio_medio=("agio_desagio_impl_pct", "mean"),
        percent_pu_par_medio=("percent_pu_par", "mean"),
    ).reset_index()

    ponderada = mensal["soma_vol_taxa"] / mensal["soma_vol_com_taxa"]
    mensal["taxa_media"] = ponderada.where(
        mensal["soma_vol_com_taxa"] > 0, mensal["taxa_media_simples"]
    )
    mensal = mensal.drop(columns=["soma_vol_taxa", "soma_vol_com_taxa", "taxa_media_simples"])
    return mensal.rename(columns={"cnpj_emissor": "cnpj"}).sort_values(
        ["mes", "volume"], ascending=[True, False], ignore_index=True
    )


def executar() -> None:
    """Lê data/raw, cruza, agrega e grava data/curated."""
    precos = _ler_raw(RAW_PRECOS_DIR)
    negociacoes = _ler_raw(RAW_NEGOCIACOES_DIR)
    trades = cruzar_negociacoes_precos(negociacoes, precos)
    if trades.empty:
        logger.warning(
            "Nenhuma negociação de FIDC encontrada no raw atual "
            "(liquidez baixa é normal; confira também a cobertura do backfill)."
        )
    mensal = agregar_mensal(trades)

    CURATED_DIR.mkdir(parents=True, exist_ok=True)
    # A partição Hive "ano" vira coluna categórica na leitura; normaliza p/ parquet.
    # (A coluna "mes" da partição é sobrescrita pelo período YYYY-MM no cruzamento.)
    if "ano" in trades.columns:
        trades["ano"] = trades["ano"].astype(str)
    trades.to_parquet(CURATED_NEGOCIACOES, index=False)
    mensal.to_parquet(CURATED_MENSAL, index=False)
    logger.info(
        "Curated gravado: %s negociações -> %s | %s linhas mensais -> %s",
        len(trades), CURATED_NEGOCIACOES, len(mensal), CURATED_MENSAL,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    executar()
