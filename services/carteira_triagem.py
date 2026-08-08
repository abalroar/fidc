"""Quais FIDCs merecem a conversa de PDD / inadimplência — e quais não merecem.

O teste de estresse roda em 37 fundos, e 37 linhas não são uma decisão. Este
módulo aplica os cortes que separam o dado que presta do dado que não sustenta
conclusão, e entrega três grupos: **decidir**, **observar** e **descartar**.

Os cortes, na ordem em que eliminam:

``sem inadimplência de crédito``
    Adquirência não tem inadimplência: o lastro é agenda de arranjo de
    pagamento, e o que ocorre é chargeback ou cancelamento — casos em que o
    cedente recompra e substitui o direito creditório.  Zero ali é a estrutura
    funcionando, não silêncio de reporte, e o quociente PDD/inadimplência não
    tem denominador.

``inadimplência imaterial``
    Abaixo de ``INAD_MINIMA_MM`` ou de ``INAD_MINIMA_PCT`` da carteira, o
    quociente é ruído aritmético: há fundo com R$ 121 de inadimplência cuja
    cobertura dá 24.884%.  O número existe e não informa nada.

``veículo pequeno``
    Carteira abaixo de ``CARTEIRA_MINIMA_MM``.  Mesmo um rombo integral não
    move a conversa, e são justamente esses que produzem os extremos do
    gráfico.

``impacto irrelevante``
    O buraco de provisão vale menos de ``DEFICIT_MINIMO_PCT`` do total de
    cotas.  Reconhecê-lo não mexe na subordinação.

O que sobra é classificado pelo que o estresse faz: quem **desenquadra** vai
para *decidir*; quem fica com folga abaixo de ``FOLGA_OBSERVACAO_PP`` vai para
*observar*; o resto tem folga suficiente para não ocupar a pauta.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.carteira_provisao import COM_COBERTURA


#: Abaixo disto o quociente é ruído aritmético, não informação.
INAD_MINIMA_MM = 5.0
INAD_MINIMA_PCT = 2.0
#: Veículo pequeno demais para mover a conversa, ainda que quebre por inteiro.
CARTEIRA_MINIMA_MM = 50.0
#: Buraco pequeno demais para mexer na subordinação.
DEFICIT_MINIMO_PCT = 1.0
#: Folga que ainda merece acompanhamento, embora não decisão.
FOLGA_OBSERVACAO_PP = 5.0

DECIDIR = "decidir"
OBSERVAR = "observar"
DESCARTAR = "descartar"

SEM_INADIMPLENCIA = "sem inadimplência de crédito (adquirência: chargeback/cancelamento com recompra)"
INAD_IMATERIAL = "inadimplência imaterial — quociente é ruído"
VEICULO_PEQUENO = "veículo pequeno — não move a conversa"
IMPACTO_IRRELEVANTE = "buraco não mexe na subordinação"
FOLGA_CONFORTAVEL = "folga confortável após o estresse"
DESENQUADRA = "desenquadra sob estresse"
FOLGA_FINA = "folga fina após o estresse"


def triar(frame: pd.DataFrame) -> pd.DataFrame:
    """Classifica cada fundo em decidir / observar / descartar, com o motivo.

    ``frame`` é a carteira já com provisão e estresse aplicados.  A função não
    descarta linha nenhuma — marca cada uma, para que o descarte seja auditável
    em vez de invisível.
    """

    saida = frame.copy()
    carteira_mm = saida["carteira_dc"] / 1e6
    inad_mm = saida["dc_inadimplentes"] / 1e6
    inad_pct = saida["dc_inadimplentes"] / saida["carteira_dc"].where(
        saida["carteira_dc"].gt(0)
    ) * 100.0
    deficit_pct = saida.get("deficit_brl", pd.Series(0.0, index=saida.index)) / saida[
        "vl_cotas_total"
    ].where(saida["vl_cotas_total"].gt(0)) * 100.0
    folga = saida.get("folga_pos_pp", pd.Series(np.nan, index=saida.index))

    saida["inad_sobre_carteira_pct"] = inad_pct
    saida["deficit_sobre_pl_pct"] = deficit_pct

    sem_denominador = saida["cobertura_estado"].ne(COM_COBERTURA)
    imaterial = inad_mm.lt(INAD_MINIMA_MM) | inad_pct.lt(INAD_MINIMA_PCT)
    pequeno = carteira_mm.lt(CARTEIRA_MINIMA_MM)
    irrelevante = deficit_pct.lt(DEFICIT_MINIMO_PCT)

    saida["triagem_motivo"] = np.select(
        [sem_denominador, pequeno, imaterial, irrelevante, folga.lt(0), folga.lt(FOLGA_OBSERVACAO_PP)],
        [SEM_INADIMPLENCIA, VEICULO_PEQUENO, INAD_IMATERIAL, IMPACTO_IRRELEVANTE, DESENQUADRA, FOLGA_FINA],
        default=FOLGA_CONFORTAVEL,
    )
    saida["triagem_status"] = np.select(
        [saida["triagem_motivo"].eq(DESENQUADRA), saida["triagem_motivo"].eq(FOLGA_FINA)],
        [DECIDIR, OBSERVAR],
        default=DESCARTAR,
    )
    return saida


def pauta(frame: pd.DataFrame) -> pd.DataFrame:
    """Só o que vai à mesa, do pior para o melhor."""

    triado = triar(frame)
    alvo = triado["triagem_status"].isin({DECIDIR, OBSERVAR})
    return triado[alvo].sort_values("folga_pos_pp").reset_index(drop=True)


def resumo(frame: pd.DataFrame) -> dict[str, object]:
    """Os números da capa: quantos ficam, quanto custa, quantos saem e por quê."""

    triado = triar(frame)
    decidir = triado[triado["triagem_status"].eq(DECIDIR)]
    observar = triado[triado["triagem_status"].eq(OBSERVAR)]
    descartados = triado[triado["triagem_status"].eq(DESCARTAR)]
    return {
        "universo": int(len(triado)),
        "decidir": int(len(decidir)),
        "observar": int(len(observar)),
        "descartar": int(len(descartados)),
        "aporte_decidir_brl": float(decidir["aporte_brl"].fillna(0).sum()),
        "aporte_total_brl": float(triado["aporte_brl"].fillna(0).sum()),
        "motivos_descarte": descartados["triagem_motivo"].value_counts().to_dict(),
    }


__all__ = [
    "CARTEIRA_MINIMA_MM",
    "DECIDIR",
    "DEFICIT_MINIMO_PCT",
    "DESCARTAR",
    "DESENQUADRA",
    "FOLGA_CONFORTAVEL",
    "FOLGA_FINA",
    "FOLGA_OBSERVACAO_PP",
    "IMPACTO_IRRELEVANTE",
    "INAD_IMATERIAL",
    "INAD_MINIMA_MM",
    "INAD_MINIMA_PCT",
    "OBSERVAR",
    "SEM_INADIMPLENCIA",
    "VEICULO_PEQUENO",
    "pauta",
    "resumo",
    "triar",
]
