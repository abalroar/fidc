"""A revalidação documental das seções da carteira."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.carteira_revalidacao import (  # noqa: E402
    MULTI_AMBOS,
    MULTICEDENTE,
    MULTISSACADO,
    SEM_EVIDENCIA,
    classify,
    drop_risk_chapter,
    fold,
)


def test_o_sacado_decide_a_secao_e_nao_o_nome_do_fundo() -> None:
    """Um fundo chamado "Agro" cujo devedor é credenciadora é Adquirência."""

    regulamento = """
    FIDC AGRO PAGAMENTOS. Os Direitos Creditórios são créditos detidos pela
    Cedente, na qualidade de subcredenciadora, contra credenciadoras
    participantes dos arranjos de pagamento. As transações de pagamento são
    liquidadas pelas credenciadoras. Os instrumentos de pagamento envolvidos
    nos arranjos de pagamento observam a regulamentação do Banco Central.
    """

    veredito = classify("1", regulamento)

    assert veredito.categoria == "Adquirência"
    assert veredito.conclusivo


def test_consignado_e_reconhecido_pelo_devedor() -> None:
    regulamento = """
    Os Direitos Creditórios decorrem de empréstimo consignado em folha, com
    desconto na margem consignável de aposentados e pensionistas do INSS.
    O consignado INSS é originado pelo Cedente. Benefícios do INSS respondem
    pelo pagamento. Consignado.
    """

    assert classify("2", regulamento).categoria == "Consignado INSS e FGTS"


def test_um_regulamento_mudo_nao_produz_categoria() -> None:
    """Sem termo que descreva lastro ou devedor, a vigente permanece."""

    regulamento = """
    O Fundo é constituído sob a forma de condomínio fechado. A Administradora
    prestará os serviços previstos na regulamentação. A Assembleia Geral
    deliberará sobre as matérias de sua competência.
    """

    veredito = classify("3", regulamento)

    assert veredito.categoria == SEM_EVIDENCIA
    assert not veredito.conclusivo


def test_a_secao_de_recebiveis_comerciais_se_chama_fomento_mercantil() -> None:
    """Nenhum destes veículos é factoring no sentido regulatório.

    "Fomento Mercantil" é o termo da ANBIMA e o que os próprios regulamentos
    usam ao se autoclassificarem — o do Pneucash II diz isso com todas as
    letras.
    """

    from services.carteira_revalidacao import CATEGORIAS, FOMENTO_MERCANTIL

    assert FOMENTO_MERCANTIL in CATEGORIAS
    assert "Factoring" not in CATEGORIAS

    regulamento = (
        "Para fins do Código ANBIMA, o Fundo é classificado como Fomento "
        "Mercantil. Os Direitos Creditórios são duplicatas mercantis oriundas "
        "de operações a prazo. Fomento mercantil. Fomento mercantil."
    )

    assert classify("13", regulamento).categoria == FOMENTO_MERCANTIL


def test_a_taxonomia_materializada_nao_carrega_o_rotulo_herdado() -> None:
    """O payload publicado diz "Factoring"; a carteira traduz ao materializar."""

    import pandas as pd

    caminho = ROOT / "data" / "industry_study" / "carteira_taxonomia_estrutural.csv"
    categorias = set(pd.read_csv(caminho, dtype=str)["categoria_estrutural"])

    assert "Factoring" not in categorias
    assert "Fomento Mercantil" in categorias


def test_empate_tecnico_e_ausencia_de_evidencia() -> None:
    """Duas operações citadas com força parecida não escolhem uma delas."""

    regulamento = """
    Os Direitos Creditórios podem ser cédulas de crédito bancário emitidas por
    sociedades, notas comerciais e debêntures, bem como créditos de fomento
    mercantil e factoring.
    """

    assert classify("4", regulamento).categoria == SEM_EVIDENCIA


def test_o_capitulo_de_fatores_de_risco_nao_classifica() -> None:
    """O sumário cita "Fatores de Risco" logo no início; o corte é no corpo.

    Sem essa distinção o guard descartaria sempre o corte, e o vocabulário do
    capítulo de risco — que menciona produtores rurais em fundo nenhum agro —
    passaria a decidir a seção.
    """

    corpo = "SUMARIO FATORES DE RISCO ... " + ("CLAUSULA GERAL. " * 400)
    risco = "FATORES DE RISCO " + ("PRODUTORES RURAIS E AGRONEGOCIO E INSUMOS AGRICOLAS. " * 40)
    texto = fold(corpo + risco)

    cortado = drop_risk_chapter(texto)

    assert len(cortado) < len(texto)
    assert "PRODUTORES RURAIS" not in cortado
    assert classify("5", corpo + risco).categoria == SEM_EVIDENCIA


def test_multicedente_e_multissacado_sao_marcados() -> None:
    base = "Os Direitos Creditórios decorrem de fomento mercantil e factoring. "

    assert classify("6", base + "Carteira multicedente.").multi == MULTICEDENTE
    assert classify("7", base + "Carteira multissacado.").multi == MULTISSACADO
    assert classify("8", base + "Fundo multicedente e multissacado.").multi == MULTI_AMBOS
    assert classify("9", base).multi == ""


def test_o_veredito_carrega_a_evidencia_literal() -> None:
    """Sem trecho não há como um analista conferir a decisão."""

    regulamento = (
        "Os Direitos Creditórios são Cédulas de Produto Rural emitidas por "
        "produtores rurais para aquisição de insumos agrícolas. CPR. "
        "Agronegócio. Produtores rurais. Insumos agrícolas."
    )

    veredito = classify("10", regulamento)

    assert veredito.categoria == "Agro / Revenda"
    assert veredito.evidencia
    assert veredito.termos


def test_consignado_na_ata_nao_e_credito_consignado() -> None:
    """Todo regulamento diz que o voto é "consignado na ata".

    O termo solto colocava um FIDC de crédito pessoal em Consignado INSS e
    FGTS; ele só conta em contexto de crédito.
    """

    ata = """
    O voto poderá ser proferido por cada cotista durante a Assembleia Geral e
    será obrigatoriamente consignado na respectiva ata por meio da assinatura
    da lista de presença.
    """

    assert classify("11", ata).categoria == SEM_EVIDENCIA

    credito = """
    Os Direitos Creditórios decorrem de empréstimos consignados em folha de
    pagamento, com desconto na margem consignável. Crédito consignado INSS.
    Consignado FGTS. Aposentados e pensionistas.
    """

    assert classify("12", credito).categoria == "Consignado INSS e FGTS"
