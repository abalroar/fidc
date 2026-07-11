"""Testes do módulo de mercado secundário (cruzamento e agregação)."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from secondary import aggregate, backfill


def _precos() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # FIDC A: PU indicativo 100 no dia 02/06
            {"isin": "BRFIDCA0001", "nome": "FIDC A SR1", "data_referencia": "2026-06-02",
             "pu": 100.0, "percent_pu_par": 98.5, "taxa_indicativa": 14.0, "duration": 1.2},
            # FIDC B: sem preço no dia da negociação (só 03/06)
            {"isin": "BRFIDCB0001", "nome": "FIDC B SR1", "data_referencia": "2026-06-03",
             "pu": 200.0, "percent_pu_par": 101.0, "taxa_indicativa": 13.0, "duration": 2.0},
        ]
    )


def _negociacoes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # casa com o PU de A: ágio implícito de +2%
            {"isin": "BRFIDCA0001", "tipo_ativo": "CFF", "emissor": "FIDC A",
             "cnpj_emissor": "11.111.111/0001-11", "data_operacao": "2026-06-02",
             "qtd_negociada": 10, "vl_pu_negociado": 102.0,
             "vl_volume_negociado": 1020.0, "taxa_negociada": 15.0},
            # mesma cota, segunda operação no mês, deságio de -2%
            {"isin": "BRFIDCA0001", "tipo_ativo": "CFF", "emissor": "FIDC A",
             "cnpj_emissor": "11.111.111/0001-11", "data_operacao": "2026-06-02",
             "qtd_negociada": 30, "vl_pu_negociado": 98.0,
             "vl_volume_negociado": 2940.0, "taxa_negociada": 16.0},
            # FIDC B negocia em dia sem PU indicativo -> ágio nulo, mas mantida
            {"isin": "BRFIDCB0001", "tipo_ativo": "CFF", "emissor": "FIDC B",
             "cnpj_emissor": "22.222.222/0001-22", "data_operacao": "2026-06-04",
             "qtd_negociada": 5, "vl_pu_negociado": 199.0,
             "vl_volume_negociado": 995.0, "taxa_negociada": None},
            # debênture: ISIN fora do universo FIDC -> descartada
            {"isin": "BRDEBENT001", "tipo_ativo": "DEB", "emissor": "Empresa X",
             "cnpj_emissor": "33.333.333/0001-33", "data_operacao": "2026-06-02",
             "qtd_negociada": 100, "vl_pu_negociado": 1000.0,
             "vl_volume_negociado": 100000.0, "taxa_negociada": 12.0},
        ]
    )


def test_cruzamento_filtra_por_isin_e_calcula_agio() -> None:
    trades = aggregate.cruzar_negociacoes_precos(_negociacoes(), _precos())
    assert len(trades) == 3  # debênture fora
    assert set(trades["isin"]) == {"BRFIDCA0001", "BRFIDCB0001"}

    a = trades[trades["isin"] == "BRFIDCA0001"].sort_values("vl_pu_negociado")
    assert a["agio_desagio_impl_pct"].round(6).tolist() == [-2.0, 2.0]

    b = trades[trades["isin"] == "BRFIDCB0001"].iloc[0]
    assert pd.isna(b["agio_desagio_impl_pct"])  # sem PU indicativo no dia
    assert trades["mes"].unique().tolist() == ["2026-06"]


def test_agregacao_mensal_pondera_taxa_por_volume() -> None:
    trades = aggregate.cruzar_negociacoes_precos(_negociacoes(), _precos())
    mensal = aggregate.agregar_mensal(trades)

    assert len(mensal) == 2
    a = mensal[mensal["isin"] == "BRFIDCA0001"].iloc[0]
    assert a["volume"] == pytest.approx(3960.0)
    assert a["n_operacoes"] == 2
    # (15*1020 + 16*2940) / 3960 = 15.742...
    assert a["taxa_media"] == pytest.approx((15 * 1020 + 16 * 2940) / 3960)
    assert a["agio_desagio_medio"] == pytest.approx(0.0)
    assert a["cnpj"] == "11.111.111/0001-11"

    b = mensal[mensal["isin"] == "BRFIDCB0001"].iloc[0]
    assert pd.isna(b["taxa_media"])  # nenhuma taxa disponível no grupo


def test_backfill_mes_e_idempotente(tmp_path, monkeypatch) -> None:
    chamadas: list[dt.date] = []

    def fake_fetch(dia: dt.date) -> list[dict]:
        chamadas.append(dia)
        return [{"isin": "BRFIDCA0001", "pu": 100.0}] if dia.day == 2 else []

    monkeypatch.setitem(
        backfill._DATASETS, "precos", (tmp_path, ["isin", "pu"], fake_fetch)
    )
    backfill.backfill_mes(2026, 6, datasets=("precos",))
    particao = tmp_path / "ano=2026" / "mes=06" / "parte.parquet"
    assert particao.exists()
    frame = pd.read_parquet(particao)
    assert frame["isin"].tolist() == ["BRFIDCA0001"]
    assert frame["data_coleta"].tolist() == ["2026-06-02"]

    # segunda rodada sem --force não refaz chamadas
    n = len(chamadas)
    backfill.backfill_mes(2026, 6, datasets=("precos",))
    assert len(chamadas) == n


def test_dias_uteis_ignora_fim_de_semana() -> None:
    dias = backfill.dias_uteis(dt.date(2026, 6, 1), dt.date(2026, 6, 7))
    assert dias == [dt.date(2026, 6, d) for d in (1, 2, 3, 4, 5)]
