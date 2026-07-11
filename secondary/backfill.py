"""Backfill diário dos endpoints ANBIMA -> parquet particionado Hive-style.

Layout:
    data/raw/precos_fidc/ano=YYYY/mes=MM/parte.parquet
    data/raw/negociacoes/ano=YYYY/mes=MM/parte.parquet

Idempotente por mês: partição existente é pulada (use --force para reprocessar).

Modo de trabalho recomendado (ver README):
    1. python -m secondary.backfill --mes 2026-06          # valida auth/campos
    2. python -m secondary.backfill --dia 2023-01-16       # sonda o histórico (não grava)
    3. python -m secondary.backfill --inicio 2023-01-01 --fim 2026-12-31

AVISO: o backfill completo (3+ anos x 2 endpoints x ~250 dias úteis/ano, com o
REUNE paginado) gera milhares de chamadas. Alinhe previamente com a ANBIMA e
ajuste ANBIMA_SLEEP_SECONDS antes de rodar.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path
from typing import Iterable

import pandas as pd

from secondary import RAW_NEGOCIACOES_DIR, RAW_PRECOS_DIR
from secondary.anbima_client import negociacoes_reune, precos_fidc

logger = logging.getLogger(__name__)

# TODO: preencher com feriados nacionais/B3 (ex.: gerar via pacote `holidays`
# com holidays.Brazil() + feriados específicos da B3) para não consultar dias
# sem pregão. Com a tupla vazia, usa-se apenas seg-sex (pandas bdate_range).
FERIADOS_B3: tuple[str, ...] = ()

PRECOS_COLS = [
    "codigo_b3", "isin", "emissor", "nome", "serie", "tipo_remuneracao",
    "data_referencia", "data_vencimento", "pu", "percent_pu_par", "duration",
    "desvio_padrao", "referencia_ntnb", "taxa_compra", "taxa_venda",
    "taxa_indicativa", "taxa_correcao",
]
NEGOCIACOES_COLS = [
    "data_atualizacao", "data_operacao", "hora_operacao", "tipo_ativo",
    "codigo_ativo", "isin", "cnpj_emissor", "emissor", "qtd_negociada",
    "vl_pu_negociado", "vl_volume_negociado", "taxa_negociada",
    "tipo_liquidacao", "emissao", "serie_emissao", "data_emissao",
    "data_vencimento", "data_liquidacao", "situacao_negociacao",
]

_DATASETS = {
    "precos": (RAW_PRECOS_DIR, PRECOS_COLS, precos_fidc),
    "negociacoes": (RAW_NEGOCIACOES_DIR, NEGOCIACOES_COLS, negociacoes_reune),
}


def dias_uteis(inicio: dt.date, fim: dt.date) -> list[dt.date]:
    """Dias úteis BR entre inicio e fim (ponto de extensão: FERIADOS_B3)."""
    index = pd.bdate_range(inicio, fim, freq="C", holidays=list(FERIADOS_B3))
    return [ts.date() for ts in index]


def _particao(raw_dir: Path, ano: int, mes: int) -> Path:
    return raw_dir / f"ano={ano:04d}" / f"mes={mes:02d}" / "parte.parquet"


def _para_frame(rows: list[dict], colunas: list[str], dia: dt.date) -> pd.DataFrame:
    frame = pd.DataFrame(rows).reindex(columns=colunas)
    frame["data_coleta"] = dia.isoformat()
    return frame


def backfill_mes(
    ano: int,
    mes: int,
    datasets: Iterable[str] = ("precos", "negociacoes"),
    force: bool = False,
) -> None:
    """Baixa e grava um mês de um ou mais datasets, pulando partições existentes."""
    primeiro = dt.date(ano, mes, 1)
    ultimo = (pd.Timestamp(primeiro) + pd.offsets.MonthEnd(0)).date()
    ultimo = min(ultimo, dt.date.today())
    if primeiro > dt.date.today():
        logger.info("Mês %04d-%02d está no futuro; nada a fazer.", ano, mes)
        return
    dias = dias_uteis(primeiro, ultimo)

    for nome in datasets:
        raw_dir, colunas, fetch = _DATASETS[nome]
        destino = _particao(raw_dir, ano, mes)
        if destino.exists() and not force:
            logger.info("[%s] %04d-%02d já existe; pulando (use --force).", nome, ano, mes)
            continue
        frames: list[pd.DataFrame] = []
        for dia in dias:
            rows = fetch(dia)
            if rows:
                frames.append(_para_frame(rows, colunas, dia))
            logger.info("[%s] %s: %s registros", nome, dia, len(rows))
        if frames:
            frame = pd.concat(frames, ignore_index=True)
        else:
            # Mês sem dado é normal (liquidez baixa / histórico indisponível):
            # grava partição vazia para manter a idempotência.
            frame = pd.DataFrame(columns=[*colunas, "data_coleta"]).astype("object")
        destino.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(destino, index=False)
        logger.info("[%s] %04d-%02d gravado: %s linhas -> %s", nome, ano, mes, len(frame), destino)


def backfill_intervalo(
    inicio: dt.date,
    fim: dt.date,
    datasets: Iterable[str] = ("precos", "negociacoes"),
    force: bool = False,
) -> None:
    """Backfill mês a mês em [inicio, fim]."""
    cursor = dt.date(inicio.year, inicio.month, 1)
    fim = min(fim, dt.date.today())
    while cursor <= fim:
        backfill_mes(cursor.year, cursor.month, datasets=datasets, force=force)
        cursor = (pd.Timestamp(cursor) + pd.offsets.MonthBegin(1)).date()


def sondar_dia(dia: dt.date) -> None:
    """Modo de teste: consulta um dia e imprime um diagnóstico, sem gravar nada.

    Útil para verificar se o histórico existe (ex.: 2023-01) e se o cruzamento
    por ISIN captura FIDCs no REUNE.
    """
    precos = precos_fidc(dia)
    negociacoes = negociacoes_reune(dia)
    isins_fidc = {str(r.get("isin") or "").strip() for r in precos} - {""}
    cff = [r for r in negociacoes if str(r.get("tipo_ativo", "")).strip().upper() == "CFF"]
    casadas = [r for r in negociacoes if str(r.get("isin") or "").strip() in isins_fidc]
    print(f"Diagnóstico {dia.isoformat()}")
    print(f"  precos_fidc:            {len(precos)} cotas ({len(isins_fidc)} ISINs)")
    print(f"  reune (todos os ativos): {len(negociacoes)} negociações")
    print(f"  reune tipo_ativo=CFF:    {len(cff)}")
    print(f"  reune com ISIN de FIDC:  {len(casadas)}")
    if not precos and not negociacoes:
        print("  -> Dia sem dado (feriado, sem pregão ou histórico indisponível).")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--mes", help="Backfill de um único mês (YYYY-MM).")
    grupo.add_argument("--dia", help="Sonda um único dia sem gravar (YYYY-MM-DD).")
    grupo.add_argument("--inicio", help="Início do backfill completo (YYYY-MM-DD).")
    parser.add_argument("--fim", help="Fim do backfill completo (YYYY-MM-DD).")
    parser.add_argument(
        "--dataset",
        choices=["precos", "negociacoes", "ambos"],
        default="ambos",
    )
    parser.add_argument("--force", action="store_true", help="Reprocessa partições existentes.")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    datasets = ("precos", "negociacoes") if args.dataset == "ambos" else (args.dataset,)
    if args.dia:
        sondar_dia(dt.date.fromisoformat(args.dia))
    elif args.mes:
        ano, mes = (int(parte) for parte in args.mes.split("-"))
        backfill_mes(ano, mes, datasets=datasets, force=args.force)
    else:
        if not args.fim:
            raise SystemExit("--inicio exige --fim (ex.: --inicio 2023-01-01 --fim 2026-12-31).")
        backfill_intervalo(
            dt.date.fromisoformat(args.inicio),
            dt.date.fromisoformat(args.fim),
            datasets=datasets,
            force=args.force,
        )


if __name__ == "__main__":
    main()
