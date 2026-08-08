"""A apuração documental: cláusulas, contraprova e o mínimo de subordinação."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.carteira_apuracao_documental import (  # noqa: E402
    CONFIRMA_ZERO,
    REFUTA,
    SEM_MEDICAO,
    load_apuracao,
    medir_terceiro,
    varrer_clausulas,
    varrer_contraprova,
)
from services.carteira_validacao_subordinacao import (  # noqa: E402
    CONFIRMA,
    DIVERGE,
    REMETE_SUPLEMENTO,
    SEM_CLAUSULA,
    avaliar,
    candidatos,
    cobertura_para_subordinacao,
)

DADOS = ROOT / "data" / "industry_study"


def documento(categoria: str, paginas: list[str], tipo: str = "", identificador: int = 1):
    return {
        "id": identificador,
        "categoria": categoria,
        "tipo": tipo,
        "data_referencia": "06/2026",
        "data_entrega": "01/07/2026 10:00",
        "pages": paginas,
        "erro": None,
    }


# ---------------------------------------------------------------------------
# Cláusulas
# ---------------------------------------------------------------------------

def test_a_cessao_sem_regresso_nao_conta_como_coobrigacao() -> None:
    """É a redação mais comum, e ela diz o oposto do que a família procura."""

    achados = varrer_clausulas(
        [
            documento(
                "Regulamento",
                [
                    "A cessão é feita em caráter definitivo, sem direito de "
                    "regresso contra a Cedente, nos termos deste Regulamento."
                ],
            )
        ]
    )

    assert achados["coobrigacao"]["achou"]
    assert achados["coobrigacao"]["sinal"] == "negativa"


def test_a_coobrigacao_afirmativa_e_marcada_como_tal() -> None:
    achados = varrer_clausulas(
        [
            documento(
                "Regulamento",
                ["A Cedente permanece solidariamente responsável pelo pagamento."],
            )
        ]
    )

    assert achados["coobrigacao"]["sinal"] == "afirmativa"


def test_a_resolucao_da_cessao_e_localizada_com_pagina_e_trecho() -> None:
    achados = varrer_clausulas(
        [
            documento(
                "Regulamento",
                [
                    "página sem nada",
                    "Ocorrida a hipótese, a cessão será resolvida de pleno "
                    "direito e o Direito Creditório retornará à Cedente.",
                ],
            )
        ]
    )

    resolucao = achados["resolucao_cessao"]
    assert resolucao["achou"]
    assert resolucao["pagina"] == 2
    assert "resolvida de pleno direito" in resolucao["trecho"]


def test_a_clausula_e_procurada_so_no_normativo() -> None:
    """Rating e demonstração financeira falam de recompra sem serem a norma."""

    achados = varrer_clausulas(
        [
            documento(
                "Relatórios",
                ["A Cedente obriga-se a recomprar os créditos vencidos."],
                tipo="Relatório de Agência de Rating",
            )
        ]
    )

    assert not achados["recompra_substituicao"]["achou"]


# ---------------------------------------------------------------------------
# Contraprova
# ---------------------------------------------------------------------------

def test_o_informe_trimestral_confirma_o_zero() -> None:
    medicao = medir_terceiro(
        [
            documento(
                "Informes Periódicos",
                [
                    "1.a) Direitos Creditórios a Vencer 468.991.948,32 74,43% "
                    "1.b) Direitos Creditórios Vencidos 0,00 0,00% "
                    "1.c) PDD 0,00 0,00%"
                ],
                tipo="Informe Trimestral",
            )
        ]
    )

    assert medicao["veredito"] == CONFIRMA_ZERO
    assert medicao["vencidos_brl"] == pytest.approx(0.0)
    assert medicao["pdd_brl"] == pytest.approx(0.0)


def test_o_informe_trimestral_refuta_quando_mede_valor() -> None:
    medicao = medir_terceiro(
        [
            documento(
                "Informes Periódicos",
                [
                    "1.b) Direitos Creditórios Vencidos 23.674.466,71 6,95% "
                    "1.c) PDD 1.200.000,00 0,35%"
                ],
                tipo="Informe Trimestral",
            )
        ]
    )

    assert medicao["veredito"] == REFUTA
    assert medicao["vencidos_brl"] == pytest.approx(23_674_466.71)


def test_sem_informe_trimestral_nao_ha_medicao() -> None:
    assert medir_terceiro([documento("Regulamento", ["texto"])])["veredito"] == SEM_MEDICAO


def test_a_contraprova_so_conta_com_numero_ao_lado() -> None:
    """A palavra "inadimplência" solta não mede nada."""

    sem_numero = varrer_contraprova(
        [
            documento(
                "Relatórios",
                ["O comitê discutiu a inadimplência da carteira."],
                tipo="Relatório de Agência de Rating",
            )
        ]
    )
    com_numero = varrer_contraprova(
        [
            documento(
                "Relatórios",
                ["A inadimplência acima de 90 dias encerrou o mês em 3,4%."],
                tipo="Relatório de Agência de Rating",
            )
        ]
    )

    assert sem_numero["fontes"] == []
    assert com_numero["fontes"] == ["rating"]


# ---------------------------------------------------------------------------
# Subordinação mínima
# ---------------------------------------------------------------------------

def test_cobertura_de_cento_e_vinte_e_cinco_e_vinte_de_subordinacao() -> None:
    assert cobertura_para_subordinacao(125.0) == pytest.approx(20.0)
    assert cobertura_para_subordinacao(133.33) == pytest.approx(25.0, abs=0.01)
    # Abaixo de 100% não há subordinação a extrair.
    assert cobertura_para_subordinacao(90.0) is None


def test_a_clausula_direta_confirma_o_minimo_em_uso() -> None:
    paginas = [
        "14.4 Índice de Subordinação. O Fundo deverá observar que, no mínimo, "
        "20% (vinte por cento) do Patrimônio Líquido seja representado por "
        "Cotas Subordinadas."
    ]

    resultado = avaliar(20.0, candidatos(paginas))

    assert resultado["veredito"] == CONFIRMA
    assert resultado["valor_documental_pct"] == pytest.approx(20.0)


def test_um_limite_de_concentracao_nao_vira_piso_de_subordinacao() -> None:
    """"Endossante cujos créditos representem pelo menos 50%" não é subordinação."""

    paginas = [
        "(viii) desenquadramento do Índice de Subordinação Mínimo por 15 dias; "
        "(ix) substituição de qualquer Endossante cujos Direitos Creditórios "
        "representem pelo menos 50% (cinquenta por cento) da carteira do Fundo;"
    ]

    assert avaliar(67.0, candidatos(paginas))["veredito"] != DIVERGE


def test_o_indice_vizinho_nao_empresta_o_percentual() -> None:
    """O Índice de Resolução de Cessão mora ao lado e tem número próprio."""

    paginas = [
        "“Índice de Resolução de Cessão” não deverá ultrapassar, no mínimo, "
        "1,50% (um inteiro e cinquenta centésimos por cento) do Patrimônio "
        "Líquido. “Índice de Subordinação” O Índice de Subordinação Sênior e o "
        "Índice de Subordinação Mezanino, quando referidos em conjunto."
    ]

    assert avaliar(0.5, candidatos(paginas))["veredito"] != DIVERGE


def test_a_remissao_a_suplemento_e_dita_e_nao_estimada() -> None:
    paginas = [
        "A relação mínima entre as Cotas Subordinadas e as Cotas Seniores, "
        "conforme definido em seu respectivo Suplemento, será verificada "
        "diariamente pela Gestora."
    ]

    assert avaliar(15.0, candidatos(paginas))["veredito"] == REMETE_SUPLEMENTO


def test_sem_clausula_o_veredito_nao_inventa_valor() -> None:
    resultado = avaliar(15.0, candidatos(["Texto sem índice nem percentual."]))

    assert resultado["veredito"] == SEM_CLAUSULA
    assert resultado["valor_documental_pct"] is None


# ---------------------------------------------------------------------------
# As bases publicadas
# ---------------------------------------------------------------------------

def test_a_apuracao_publicada_cobre_todos_os_pendentes() -> None:
    from services.carteira_estresse import nao_reportantes
    from services.carteira_provisao import attach_provisao
    from services.carteira_subordinacao import resolve_portfolio

    pendentes = nao_reportantes(attach_provisao(resolve_portfolio(DADOS).frame, DADOS))
    apuracao = load_apuracao(DADOS)

    assert set(pendentes["cnpj"]) <= set(apuracao["cnpj"])
    # Toda linha diz alguma coisa: diagnóstico vazio seria pior que ausência.
    assert apuracao["diagnostico"].str.strip().ne("").all()


def test_a_validacao_publicada_cobre_o_registro() -> None:
    from services.carteira_subordinacao import load_registry

    validacao = pd.read_csv(
        DADOS / "carteira_subordinacao_validacao.csv", dtype={"cnpj": str}
    )
    registro = load_registry(DADOS)

    assert set(registro["cnpj"]) == set(validacao["cnpj"])
    # Onde o veredito confirma, o trecho literal tem de estar junto.
    confirmados = validacao[validacao["veredito"] == CONFIRMA]
    assert confirmados["trecho"].str.strip().ne("").all()
    assert confirmados["pagina"].notna().all()
