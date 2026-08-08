"""Teste de estresse: e se o fundo provisionasse toda a inadimplência?

A carteira que o Informe reporta **já é líquida de PDD** — no Investcred, por
exemplo, ``a vencer 731,4 + vencido não pago 36,4 + inadimplentes 1.668,9 −
PDD 1.443,8 = 992,9``.  O que ainda não foi reconhecido, portanto, é a parte da
inadimplência que a provisão não cobre:

.. math::

    \\Delta = \\max(\\text{inadimplência} - \\text{PDD},\\; 0)

Esse é o buraco.  Ele é equivalente a ``(1 − cobertura) × inadimplência``, e
**não** a ``(1 − cobertura) × carteira``: a carteira é outro montante, e nos
fundos em run-off a inadimplência chega a superá-la.

Reconhecer Δ derruba o ativo em Δ.  O sênior está protegido pela estrutura, de
modo que a perda inteira consome a classe subordinada primeiro:

.. math::

    \\text{Sub}_{pós} = \\text{Sub}_{antes} - \\Delta \\qquad
    \\text{Total}_{pós} = \\text{Total}_{antes} - \\Delta

O denominador é o **total de cotas**, que é a base do índice de subordinação que
o regulamento cobra — não o PL, que difere dele em alguns fundos.

Desenquadrando, o aporte que reenquadra sai de exigir
``(Sub + A) / (Total + A) ≥ m``:

.. math::

    A = \\frac{m \\cdot \\text{Total}_{pós} - \\text{Sub}_{pós}}{1 - m}

Uma premissa fica registrada porque o Informe não permite verificá-la: a PDD é
tratada como se estivesse toda alocada contra os créditos inadimplentes.  A CVM
não abre a provisão por faixa, e qualquer parcela provisionada contra créditos a
vencer tornaria a cobertura aqui medida otimista.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


#: Cobertura a partir da qual não há o que estressar.
COBERTURA_PLENA_PCT = 100.0

ENQUADRADO = "enquadrado"
DESENQUADRADO = "desenquadrado"
CAPITAL_CONSUMIDO = "capital consumido"
SEM_MINIMO = "sem mínimo documentado"

#: Colunas que o teste precisa encontrar na carteira resolvida.
ENTRADAS = (
    "vl_cotas_subordinadas",
    "vl_cotas_total",
    "referencia_pct",
    "dc_inadimplentes",
    "pdd_brl",
)


def estressar(frame: pd.DataFrame) -> pd.DataFrame:
    """Aplica o estresse a cada linha e devolve as colunas do resultado."""

    saida = frame.copy()
    for coluna in ENTRADAS:
        saida[coluna] = pd.to_numeric(saida.get(coluna), errors="coerce")

    inad = saida["dc_inadimplentes"]
    pdd = saida["pdd_brl"]
    saida["deficit_brl"] = (inad - pdd).clip(lower=0.0).where(inad.gt(0))

    sub_antes = saida["vl_cotas_subordinadas"]
    total_antes = saida["vl_cotas_total"]
    saida["sub_antes_pct"] = sub_antes / total_antes.where(total_antes.gt(0)) * 100.0

    sub_pos = sub_antes - saida["deficit_brl"]
    total_pos = total_antes - saida["deficit_brl"]
    saida["sub_pos_brl"] = sub_pos
    saida["total_pos_brl"] = total_pos
    saida["sub_pos_pct"] = sub_pos / total_pos.where(total_pos.gt(0)) * 100.0
    saida["folga_pos_pp"] = saida["sub_pos_pct"] - saida["referencia_pct"]

    # O aporte que reenquadra: (m·Total + A) resolvido para A.  Com o mínimo em
    # 100% não existe A finito — a classe sênior teria de desaparecer.
    m = saida["referencia_pct"] / 100.0
    viavel = m.notna() & m.lt(1.0)
    aporte = (m * total_pos - sub_pos) / (1.0 - m)
    saida["aporte_brl"] = aporte.where(viavel).clip(lower=0.0)

    saida["estresse_status"] = np.select(
        [
            saida["referencia_pct"].isna(),
            total_pos.le(0),
            saida["folga_pos_pp"].ge(0),
        ],
        [SEM_MINIMO, CAPITAL_CONSUMIDO, ENQUADRADO],
        default=DESENQUADRADO,
    )
    # Sem inadimplência não há estresse a aplicar; a linha fica fora do teste.
    saida.loc[saida["deficit_brl"].isna(), "estresse_status"] = pd.NA
    return saida


def sob_estresse(frame: pd.DataFrame) -> pd.DataFrame:
    """Os fundos que o teste alcança: cobertura abaixo de 100% e mínimo conhecido.

    Cobertura plena não muda nada — Δ é zero e a subordinação fica onde estava —,
    então esses fundos ficariam na tabela só ocupando linha.
    """

    dados = estressar(frame)
    alvo = (
        dados["cobertura_pct"].notna()
        & dados["cobertura_pct"].lt(COBERTURA_PLENA_PCT)
        & dados["referencia_pct"].notna()
        & dados["vl_cotas_total"].gt(0)
    )
    return dados[alvo].sort_values("folga_pos_pp").reset_index(drop=True)


def nao_reportantes(frame: pd.DataFrame) -> pd.DataFrame:
    """Quem não deu PDD, inadimplência ou ambas — a lista para apurar.

    Há dois casos por trás do mesmo silêncio, e a coluna ``caso`` os separa:
    fundo sem nada em atraso (e aí zero é a resposta certa) e fundo com carteira
    parada, provisionada, mas sem inadimplência declarada — onde o zero é
    improvável e o administrador provavelmente deveria estar reportando.
    """

    dados = frame.copy()
    inad = pd.to_numeric(dados.get("dc_inadimplentes"), errors="coerce").fillna(0.0)
    pdd = pd.to_numeric(dados.get("pdd_brl"), errors="coerce").fillna(0.0)
    carteira = pd.to_numeric(dados.get("carteira_dc"), errors="coerce").fillna(0.0)

    faltantes = dados[inad.le(0) | pdd.le(0)].copy()
    f_inad = inad[faltantes.index]
    f_pdd = pdd[faltantes.index]
    f_cart = carteira[faltantes.index]

    faltantes["caso"] = np.select(
        [
            f_cart.le(0),
            f_inad.le(0) & f_pdd.gt(0),
            f_inad.le(0) & f_pdd.le(0),
        ],
        [
            "sem carteira de direitos creditórios",
            "provisiona mas não declara inadimplência — apurar",
            "nem PDD nem inadimplência declaradas — apurar",
        ],
        default="declara inadimplência sem provisionar — apurar",
    )
    return faltantes.sort_values(
        ["caso", "carteira_dc"], ascending=[True, False]
    ).reset_index(drop=True)


__all__ = [
    "CAPITAL_CONSUMIDO",
    "COBERTURA_PLENA_PCT",
    "DESENQUADRADO",
    "ENQUADRADO",
    "ENTRADAS",
    "SEM_MINIMO",
    "estressar",
    "nao_reportantes",
    "sob_estresse",
]
