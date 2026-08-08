"""Carteira de crédito, PDD e inadimplência: o que é zero e o que é ausência."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.carteira_provisao import (  # noqa: E402
    PROVISAO_NAME,
    REPORTADO,
    SEM_DADO,
    ZERO_DECLARADO,
    altair_carteira_pdd,
    attach_provisao,
    chart_frame,
    cobertura,
    limite_do_eixo,
    por_categoria,
)

COM_PDD = "11111111000191"
SEM_PDD = "22222222000172"
SEM_CARTEIRA = "33333333000153"
OUTRA_COMPETENCIA = "44444444000134"


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    pd.DataFrame(
        [
            {"competencia": "2026-06", "cnpj": COM_PDD, "pdd_brl": 20e6},
            {"competencia": "2026-06", "cnpj": SEM_PDD, "pdd_brl": 0.0},
            {"competencia": "2026-06", "cnpj": SEM_CARTEIRA, "pdd_brl": 0.0},
            # O fundo que ficou em março tem PDD nas duas competências; só a
            # dele pode ser usada.
            {"competencia": "2026-03", "cnpj": OUTRA_COMPETENCIA, "pdd_brl": 5e6},
            {"competencia": "2026-06", "cnpj": OUTRA_COMPETENCIA, "pdd_brl": 900e6},
        ]
    ).to_csv(tmp_path / PROVISAO_NAME, index=False, compression="gzip")
    return tmp_path


@pytest.fixture()
def carteira() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cnpj": COM_PDD, "fundo": "FIDC Com PDD", "competencia": "2026-06",
                "categoria_estrutural": "Financeiro",
                "carteira_dc": 100e6, "dc_inadimplentes": 4e6,
            },
            {
                "cnpj": SEM_PDD, "fundo": "FIDC Sem PDD", "competencia": "2026-06",
                "categoria_estrutural": "Financeiro",
                "carteira_dc": 50e6, "dc_inadimplentes": 0.0,
            },
            {
                "cnpj": SEM_CARTEIRA, "fundo": "FIDC Sem Carteira",
                "competencia": "2026-06", "categoria_estrutural": "Adquirência",
                "carteira_dc": 0.0, "dc_inadimplentes": 0.0,
            },
            {
                "cnpj": OUTRA_COMPETENCIA, "fundo": "FIDC Março",
                "competencia": "2026-03", "categoria_estrutural": "Adquirência",
                "carteira_dc": 25e6, "dc_inadimplentes": 1e6,
            },
        ]
    )


def test_zero_declarado_nao_e_a_mesma_coisa_que_ausencia(
    carteira: pd.DataFrame, data_dir: Path
) -> None:
    """O campo nunca vem em branco na Tabela I: zero é declaração do fundo."""

    frame = attach_provisao(carteira, data_dir).set_index("cnpj")

    assert frame.at[COM_PDD, "pdd_estado"] == REPORTADO
    assert frame.at[SEM_PDD, "pdd_estado"] == ZERO_DECLARADO
    assert frame.at[SEM_PDD, "pdd_sobre_carteira_pct"] == pytest.approx(0.0)
    # Sem carteira o quociente não existe — e não vale zero.
    assert frame.at[SEM_CARTEIRA, "pdd_estado"] == SEM_DADO
    assert np.isnan(frame.at[SEM_CARTEIRA, "pdd_sobre_carteira_pct"])


def test_a_pdd_vem_da_competencia_do_proprio_fundo(
    carteira: pd.DataFrame, data_dir: Path
) -> None:
    """Casar junho com a carteira de março inventaria um quociente."""

    frame = attach_provisao(carteira, data_dir).set_index("cnpj")

    assert frame.at[OUTRA_COMPETENCIA, "pdd_mm"] == pytest.approx(5.0)
    assert frame.at[OUTRA_COMPETENCIA, "pdd_sobre_carteira_pct"] == pytest.approx(20.0)


def test_a_cobertura_conta_os_tres_estados(
    carteira: pd.DataFrame, data_dir: Path
) -> None:
    conta = cobertura(attach_provisao(carteira, data_dir))

    assert conta["fundos"] == 4
    assert conta["pdd_reportada"] == 2
    assert conta["pdd_zero"] == 1
    assert conta["pdd_sem_dado"] == 1
    assert conta["inad_reportada"] == 2
    assert conta["inad_zero"] == 1
    assert conta["inad_sem_dado"] == 1


def test_a_seção_usa_o_quociente_da_soma(
    carteira: pd.DataFrame, data_dir: Path
) -> None:
    """A média dos quocientes daria o mesmo peso a R$ 25 mm e a R$ 100 mm."""

    grupos = por_categoria(attach_provisao(carteira, data_dir)).set_index(
        "categoria_estrutural"
    )

    # Financeiro: (20 + 0) / (100 + 50).
    assert grupos.at["Financeiro", "pdd_sobre_carteira_pct"] == pytest.approx(
        20.0 / 150.0 * 100
    )
    # Adquirência: só o fundo de março tem carteira.
    assert grupos.at["Adquirência", "pdd_sobre_carteira_pct"] == pytest.approx(20.0)


def test_quem_nao_tem_carteira_sai_do_grafico(
    carteira: pd.DataFrame, data_dir: Path
) -> None:
    """Uma barra de altura zero com ponto em zero mentiria duas vezes."""

    frame = attach_provisao(carteira, data_dir)
    dados = chart_frame(frame.assign(rotulo=frame["fundo"]))

    assert SEM_CARTEIRA not in set(dados["cnpj"])
    # E a ordem é a da carteira, do maior para o menor.
    assert dados["carteira_mm"].is_monotonic_decreasing


def test_o_teto_do_eixo_so_entra_quando_ha_extremo() -> None:
    """Sem outlier o eixo fica inteiro; com outlier o resto não pode achatar."""

    parelho = pd.Series([10.0, 12.0, 9.0, 11.0, 13.0, 10.5])
    assert limite_do_eixo(parelho) is None

    com_extremo = pd.Series([1.0, 2.0, 3.0, 2.5, 1.5, 276.0])
    teto = limite_do_eixo(com_extremo)
    assert teto is not None and teto < 276.0


def test_o_grafico_marca_o_que_passa_do_teto(
    carteira: pd.DataFrame, data_dir: Path
) -> None:
    """O ponto sai da escala, não do gráfico: vira triângulo com o valor."""

    frame = attach_provisao(carteira, data_dir)
    grafico = altair_carteira_pdd(frame.assign(rotulo=frame["fundo"]))
    spec = grafico.to_dict()

    # Barra, ponto, triângulo, rótulo do triângulo e a marca de sem informe.
    assert len(spec["layer"]) == 5
    assert spec["resolve"]["scale"]["y"] == "independent"
    # As duas escalas ancoradas em zero — é o que torna o eixo duplo defensável.
    for camada in spec["layer"][:2]:
        assert camada["encoding"]["y"]["scale"].get("domainMin") == 0 or camada[
            "encoding"
        ]["y"]["scale"].get("domain", [None])[0] == 0


def test_sem_base_de_pdd_o_grafico_ainda_sobe(carteira: pd.DataFrame, tmp_path: Path) -> None:
    """A base é opcional: sem ela a carteira aparece e a PDD fica sem informe."""

    frame = attach_provisao(carteira, tmp_path)

    assert frame["pdd_brl"].isna().all()
    assert set(frame["pdd_estado"]) == {SEM_DADO}
    # A inadimplência não depende da base de PDD e continua lida.
    assert frame.set_index("cnpj").at[COM_PDD, "inad_estado"] == REPORTADO


def test_a_base_publicada_cobre_a_carteira_ativa() -> None:
    """Um fundo da carteira sem PDD materializada apareceria como lacuna falsa."""

    from services.carteira_subordinacao import resolve_portfolio

    dados = ROOT / "data" / "industry_study"
    frame = attach_provisao(resolve_portfolio(dados).frame, dados)
    com_carteira = frame[frame["carteira_dc"].fillna(0).gt(0)]

    assert len(com_carteira) >= 80
    assert com_carteira["pdd_brl"].notna().all()
