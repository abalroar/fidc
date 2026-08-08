"""Cobertura de PDD sobre inadimplência: o que tem denominador e o que não tem."""

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
    COM_COBERTURA,
    LIMIAR_PCT,
    PROVISAO_NAME,
    SEM_CARTEIRA,
    SEM_INADIMPLENCIA,
    TETO_PCT,
    altair_cobertura,
    attach_provisao,
    chart_frame,
    formatar_pct,
)

COBERTO = "11111111000191"
DESCOBERTO = "22222222000172"
SEM_ATRASO = "33333333000153"
SEM_DC = "44444444000134"
MARCO = "55555555000115"


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    pd.DataFrame(
        [
            {"competencia": "2026-06", "cnpj": COBERTO, "pdd_brl": 12e6},
            {"competencia": "2026-06", "cnpj": DESCOBERTO, "pdd_brl": 1e6},
            {"competencia": "2026-06", "cnpj": SEM_ATRASO, "pdd_brl": 0.0},
            {"competencia": "2026-06", "cnpj": SEM_DC, "pdd_brl": 0.0},
            # O fundo que ficou em março tem PDD nas duas competências; só a
            # dele pode ser usada.
            {"competencia": "2026-03", "cnpj": MARCO, "pdd_brl": 2e6},
            {"competencia": "2026-06", "cnpj": MARCO, "pdd_brl": 900e6},
        ]
    ).to_csv(tmp_path / PROVISAO_NAME, index=False, compression="gzip")
    return tmp_path


@pytest.fixture()
def carteira() -> pd.DataFrame:
    def linha(cnpj, nome, competencia, categoria, carteira, inad):
        return {
            "cnpj": cnpj, "fundo": nome, "competencia": competencia,
            "categoria_estrutural": categoria,
            "carteira_dc": carteira, "dc_inadimplentes": inad,
        }

    return pd.DataFrame(
        [
            linha(COBERTO, "FIDC Coberto", "2026-06", "Financeiro", 100e6, 8e6),
            linha(DESCOBERTO, "FIDC Descoberto", "2026-06", "Financeiro", 90e6, 5e6),
            linha(SEM_ATRASO, "FIDC Sem Atraso", "2026-06", "Adquirência", 50e6, 0.0),
            linha(SEM_DC, "FIDC Sem Carteira", "2026-06", "Adquirência", 0.0, 0.0),
            linha(MARCO, "FIDC Março", "2026-03", "Agro / Revenda", 40e6, 4e6),
        ]
    )


def test_a_cobertura_e_pdd_sobre_inadimplencia(
    carteira: pd.DataFrame, data_dir: Path
) -> None:
    frame = attach_provisao(carteira, data_dir).set_index("cnpj")

    assert frame.at[COBERTO, "cobertura_pct"] == pytest.approx(150.0)
    assert frame.at[DESCOBERTO, "cobertura_pct"] == pytest.approx(20.0)


def test_sem_inadimplencia_nao_e_cobertura_zero(
    carteira: pd.DataFrame, data_dir: Path
) -> None:
    """Um fundo sem atraso não é um fundo sem cobertura — falta denominador."""

    frame = attach_provisao(carteira, data_dir).set_index("cnpj")

    assert frame.at[SEM_ATRASO, "cobertura_estado"] == SEM_INADIMPLENCIA
    assert np.isnan(frame.at[SEM_ATRASO, "cobertura_pct"])
    assert frame.at[SEM_DC, "cobertura_estado"] == SEM_CARTEIRA
    assert frame.at[COBERTO, "cobertura_estado"] == COM_COBERTURA


def test_a_pdd_vem_da_competencia_do_proprio_fundo(
    carteira: pd.DataFrame, data_dir: Path
) -> None:
    """Casar junho com a inadimplência de março inventaria um quociente."""

    frame = attach_provisao(carteira, data_dir).set_index("cnpj")

    assert frame.at[MARCO, "pdd_mm"] == pytest.approx(2.0)
    assert frame.at[MARCO, "cobertura_pct"] == pytest.approx(50.0)


def test_so_entra_no_grafico_quem_tem_denominador(
    carteira: pd.DataFrame, data_dir: Path
) -> None:
    frame = attach_provisao(carteira, data_dir)
    dados = chart_frame(frame.assign(rotulo=frame["fundo"]))

    assert set(dados["cnpj"]) == {COBERTO, DESCOBERTO, MARCO}
    # Da maior cobertura para a menor.
    assert dados["cobertura_pct"].is_monotonic_decreasing


def test_a_barra_para_no_teto_mas_o_rotulo_nao(data_dir: Path) -> None:
    """Coberturas de 300% e de 24.000% dizem a mesma coisa; o número não some."""

    extremo = pd.DataFrame(
        [
            {
                "cnpj": COBERTO, "fundo": "FIDC Extremo", "competencia": "2026-06",
                "categoria_estrutural": "Financeiro",
                "carteira_dc": 100e6, "dc_inadimplentes": 1e3,
            }
        ]
    )
    frame = attach_provisao(extremo, data_dir)
    linha = chart_frame(frame.assign(rotulo=frame["fundo"])).iloc[0]

    assert linha["cobertura_pct"] > TETO_PCT
    assert linha["altura_pct"] == pytest.approx(TETO_PCT)
    assert linha["etiqueta"] == formatar_pct(linha["cobertura_pct"])
    assert "1.200.000" in linha["etiqueta"]


def test_a_faixa_muda_no_limiar_de_cem(
    carteira: pd.DataFrame, data_dir: Path
) -> None:
    frame = attach_provisao(carteira, data_dir)
    dados = chart_frame(frame.assign(rotulo=frame["fundo"])).set_index("cnpj")

    assert dados.at[COBERTO, "faixa"] != dados.at[DESCOBERTO, "faixa"]
    assert dados.at[COBERTO, "cobertura_pct"] >= LIMIAR_PCT
    assert dados.at[DESCOBERTO, "cobertura_pct"] < LIMIAR_PCT


def test_o_rotulo_cabe_sobre_a_barra() -> None:
    """Separador de milhar brasileiro, e decimal só onde ele informa."""

    assert formatar_pct(0.0) == "0,0%"
    assert formatar_pct(3.14) == "3,1%"
    assert formatar_pct(150.0) == "150%"
    assert formatar_pct(24883.86) == "24.884%"


def test_todo_fundo_do_grafico_tem_nome_e_rotulo(
    carteira: pd.DataFrame, data_dir: Path
) -> None:
    """Nada de rotular só os notáveis: era o pedido, e é o que o teto exige."""

    frame = attach_provisao(carteira, data_dir)
    dados = frame.assign(rotulo=frame["fundo"])
    grafico = altair_cobertura(dados)
    spec = grafico.to_dict()

    # Limiar, barras e etiquetas — uma camada de texto para todas as barras.
    assert len(spec["layer"]) == 3
    texto = spec["layer"][2]
    assert texto["mark"]["type"] == "text"
    assert texto["encoding"]["text"]["field"] == "etiqueta"
    # A etiqueta lê o mesmo dado que a barra: uma por barra, e não uma seleção
    # de notáveis.
    barras = spec["layer"][1]
    assert texto["data"] == barras["data"]
    nome = barras["data"]["name"]
    assert len(spec["datasets"][nome]) == len(chart_frame(dados))
    # E o eixo categórico não esconde nome nenhum: sem labels=False e sem
    # truncar em poucos caracteres.
    eixo = barras["encoding"]["x"]["axis"]
    assert eixo.get("labels", True) is not False
    assert eixo["labelLimit"] >= 200


def test_sem_base_de_pdd_a_cobertura_fica_em_zero(
    carteira: pd.DataFrame, tmp_path: Path
) -> None:
    """A base é opcional: sem ela o gráfico sobe, com cobertura zerada."""

    frame = attach_provisao(carteira, tmp_path)

    assert frame["pdd_brl"].isna().all()
    assert frame.set_index("cnpj").at[COBERTO, "cobertura_pct"] == pytest.approx(0.0)
    assert frame.set_index("cnpj").at[SEM_ATRASO, "cobertura_estado"] == SEM_INADIMPLENCIA


def test_a_base_publicada_cobre_a_carteira_ativa() -> None:
    """Um fundo sem PDD materializada apareceria como cobertura zero falsa."""

    from services.carteira_subordinacao import resolve_portfolio

    dados = ROOT / "data" / "industry_study"
    frame = attach_provisao(resolve_portfolio(dados).frame, dados)
    com_carteira = frame[frame["carteira_dc"].fillna(0).gt(0)]

    assert len(com_carteira) >= 80
    assert com_carteira["pdd_brl"].notna().all()
