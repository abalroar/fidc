"""A triagem: quem vai à mesa, quem sai, e por qual motivo."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.carteira_provisao import COM_COBERTURA, SEM_INADIMPLENCIA as ESTADO_SEM_INAD  # noqa: E402
from services.carteira_triagem import (  # noqa: E402
    DECIDIR,
    DESCARTAR,
    DESENQUADRA,
    IMPACTO_IRRELEVANTE,
    INAD_IMATERIAL,
    OBSERVAR,
    SEM_INADIMPLENCIA,
    VEICULO_PEQUENO,
    pauta,
    resumo,
    triar,
)


def fundo(**campos):
    base = {
        "cnpj": "11111111000191",
        "rotulo": "FIDC Teste",
        "categoria_estrutural": "Financeiro",
        "cobertura_estado": COM_COBERTURA,
        "carteira_dc": 400e6,
        "dc_inadimplentes": 80e6,
        "vl_cotas_total": 500e6,
        "deficit_brl": 40e6,
        "folga_pos_pp": -3.0,
        "aporte_brl": 25e6,
        "referencia_pct": 20.0,
    }
    base.update(campos)
    return base


def test_adquirencia_sem_inadimplencia_sai_do_teste() -> None:
    """Chargeback e cancelamento com recompra não são inadimplência de crédito."""

    linha = triar(
        pd.DataFrame(
            [fundo(cobertura_estado=ESTADO_SEM_INAD, dc_inadimplentes=0.0)]
        )
    ).iloc[0]

    assert linha["triagem_status"] == DESCARTAR
    assert linha["triagem_motivo"] == SEM_INADIMPLENCIA


def test_inadimplencia_imaterial_e_ruido() -> None:
    """R$ 121 de inadimplência produz cobertura de 24.884% e não informa nada."""

    por_valor = triar(pd.DataFrame([fundo(dc_inadimplentes=1e6)])).iloc[0]
    por_proporcao = triar(pd.DataFrame([fundo(dc_inadimplentes=6e6)])).iloc[0]

    assert por_valor["triagem_motivo"] == INAD_IMATERIAL
    assert por_proporcao["triagem_motivo"] == INAD_IMATERIAL


def test_veiculo_pequeno_nao_move_a_conversa() -> None:
    linha = triar(
        pd.DataFrame([fundo(carteira_dc=20e6, dc_inadimplentes=10e6)])
    ).iloc[0]

    assert linha["triagem_motivo"] == VEICULO_PEQUENO


def test_buraco_que_nao_mexe_na_subordinacao_sai() -> None:
    linha = triar(pd.DataFrame([fundo(deficit_brl=1e6)])).iloc[0]

    assert linha["triagem_motivo"] == IMPACTO_IRRELEVANTE


def test_quem_desenquadra_vai_decidir_e_folga_fina_vai_observar() -> None:
    frame = pd.DataFrame(
        [
            fundo(cnpj="11111111000191", folga_pos_pp=-3.0),
            fundo(cnpj="22222222000172", folga_pos_pp=2.0, aporte_brl=0.0),
            fundo(cnpj="33333333000153", folga_pos_pp=30.0, aporte_brl=0.0),
        ]
    )

    triado = triar(frame).set_index("cnpj")

    assert triado.at["11111111000191", "triagem_status"] == DECIDIR
    assert triado.at["11111111000191", "triagem_motivo"] == DESENQUADRA
    assert triado.at["22222222000172", "triagem_status"] == OBSERVAR
    assert triado.at["33333333000153", "triagem_status"] == DESCARTAR


def test_a_pauta_traz_so_o_que_vai_a_mesa_do_pior_para_o_melhor() -> None:
    frame = pd.DataFrame(
        [
            fundo(cnpj="11111111000191", folga_pos_pp=2.0, aporte_brl=0.0),
            fundo(cnpj="22222222000172", folga_pos_pp=-9.0),
            fundo(cnpj="33333333000153", folga_pos_pp=40.0, aporte_brl=0.0),
        ]
    )

    mesa = pauta(frame)

    assert list(mesa["cnpj"]) == ["22222222000172", "11111111000191"]


def test_o_resumo_fecha_com_o_universo() -> None:
    frame = pd.DataFrame(
        [
            fundo(cnpj="11111111000191", folga_pos_pp=-3.0, aporte_brl=25e6),
            fundo(cnpj="22222222000172", cobertura_estado=ESTADO_SEM_INAD),
            fundo(cnpj="33333333000153", folga_pos_pp=40.0, aporte_brl=0.0),
        ]
    )

    numeros = resumo(frame)

    assert numeros["universo"] == 3
    assert numeros["decidir"] + numeros["observar"] + numeros["descartar"] == 3
    assert numeros["aporte_decidir_brl"] == pytest.approx(25e6)
    assert sum(numeros["motivos_descarte"].values()) == numeros["descartar"]


def test_a_carteira_publicada_cabe_numa_pauta_curta() -> None:
    """O ponto do módulo: 37 linhas não são uma decisão."""

    from services.carteira_estresse import estressar
    from services.carteira_provisao import attach_provisao
    from services.carteira_subordinacao import resolve_portfolio

    dados = ROOT / "data" / "industry_study"
    carteira = estressar(attach_provisao(resolve_portfolio(dados).frame, dados))
    numeros = resumo(carteira)

    assert numeros["decidir"] + numeros["observar"] <= 15
    # E o que fica concentra o aporte: descartar não é esconder custo.
    assert numeros["aporte_decidir_brl"] >= numeros["aporte_total_brl"] * 0.95
