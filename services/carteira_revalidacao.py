"""Revalida a seção de cada FIDC da carteira a partir do regulamento.

A pergunta é sempre a mesma: **quem é o sacado e qual é o recebível
encarteirado**.  É isso que decide se um veículo é de Adquirência, Consignado
INSS e FGTS, Risco Corporativo, Agro / Revenda, Financeiro ou Factoring — e não
o nome do fundo nem o setor do cedente.

O módulo lê o regulamento, procura os termos que descrevem lastro e devedor, e
devolve, para cada CNPJ, a categoria sustentada pelo documento **com o trecho
literal que a sustenta**.  Quando o documento não distingue, a saída é
``sem evidência``: a categoria vigente permanece, marcada como não revalidada.
Nada é decidido por semelhança de nome.

A marca de multicedente/multissacado sai do mesmo texto e acompanha o nome do
fundo na tabela do slide, porque muda a natureza do risco: pulverizado entre
muitos sacados não é o mesmo que concentrado em um.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


CATEGORIAS = (
    "Adquirência",
    "Consignado INSS e FGTS",
    "Risco Corporativo",
    "Agro / Revenda",
    "Financeiro",
    "Factoring",
)
SEM_EVIDENCIA = "sem evidência"

MULTICEDENTE = "multicedente"
MULTISSACADO = "multissacado"
MULTI_AMBOS = "multicedente/multissacado"


#: O capítulo de fatores de risco repete todo o vocabulário do fundo em frases
#: que não descrevem a operação — "podem afetar adversamente os produtores
#: rurais" aparece em regulamento que não tem nada de agro.  Ele sai antes da
#: pontuação.
_RISCO = re.compile(
    r"(?:FATORES DE RISCO|RISCOS? (?:RELACIONADOS?|ASSOCIADOS?|INERENTES?)\b)"
)


def drop_risk_chapter(texto: str, inicio_minimo: float = 0.2) -> str:
    """Corta o capítulo de fatores de risco, se houver um depois do começo.

    O título aparece antes no sumário, quase no primeiro caractere; usar a
    primeira ocorrência faria o corte ser sempre descartado pelo próprio guard.
    O que interessa é a **primeira ocorrência já dentro do corpo**.
    """

    piso = len(texto) * inicio_minimo
    for achado in _RISCO.finditer(texto):
        if achado.start() >= piso:
            return texto[: achado.start()]
    return texto


def fold(text: str) -> str:
    """Sem acentos, caixa alta, espaços colapsados — a forma em que buscamos."""

    norma = unicodedata.normalize("NFKD", text or "")
    limpo = "".join(ch for ch in norma if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", limpo).upper()


#: Cada categoria é descrita pelos termos que o regulamento usa para o lastro e
#: para o devedor.  O peso separa o que identifica a operação (peso alto) do que
#: só a acompanha — "duplicata" aparece em quase todo FIDC comercial, mas
#: "arranjo de pagamento" só aparece onde o devedor é uma credenciadora.
SINAIS: dict[str, tuple[tuple[str, int], ...]] = {
    "Adquirência": (
        (r"ARRANJOS? DE PAGAMENTO", 5),
        (r"SUBCREDENCIADORA", 5),
        (r"CREDENCIADORAS?\b", 4),
        (r"INSTRUMENTOS? DE PAGAMENTO", 3),
        (r"AGENDA FINANCEIRA", 4),
        (r"UNIDADES? DE RECEBIVEIS", 4),
        (r"TRANSACOES? DE PAGAMENTO", 3),
        (r"\bADQUIRENTES?\b", 3),
    ),
    "Consignado INSS e FGTS": (
        # "Consignado" solto não serve: todo regulamento diz que o voto é
        # "consignado na ata".  O termo só conta em contexto de crédito.
        (r"(?:CREDITOS?|EMPRESTIMOS?|OPERAC(?:AO|OES)|CARTAO|CARTEIRA)\s+"
         r"CONSIGNAD[OA]S?", 5),
        (r"CONSIGNAD[OA]S?\s+(?:EM FOLHA|INSS|FGTS|PRIVAD|PUBLIC)", 5),
        (r"\bINSS\b", 4),
        (r"\bFGTS\b", 4),
        (r"SAQUE[- ]ANIVERSARIO", 5),
        (r"MARGEM CONSIGNAVEL", 4),
        (r"BENEFICIOS? (?:DO )?INSS", 4),
        (r"APOSENTADOS E PENSIONISTAS", 3),
    ),
    "Risco Corporativo": (
        (r"NOTAS? COMERCIAIS", 4),
        (r"\bDEBENTURES?\b", 4),
        (r"RISCO CORPORATIVO", 5),
        (r"CEDULAS? DE CREDITO BANCARIO.{0,80}?EMITIDAS? POR SOCIEDADES?", 3),
        (r"UNICO DEVEDOR", 3),
        (r"DEVEDOR UNICO", 3),
    ),
    "Agro / Revenda": (
        (r"\bCPR\b|CEDULA DE PRODUTO RURAL", 5),
        (r"PRODUTORES? RURA(?:L|IS)", 4),
        (r"AGRONEGOCIO", 4),
        (r"INSUMOS? AGRICOLAS?|INSUMOS? AGROPECUARIOS?", 4),
        (r"\bCDCA\b|\bCRA\b", 3),
        (r"REVENDAS? AGRICOLAS?", 4),
        (r"\bFIAGRO\b", 3),
    ),
    "Financeiro": (
        (r"CARTAO DE CREDITO", 4),
        (r"CREDITO PESSOAL", 4),
        (r"FINANCIAMENTO DE VEICULOS?", 4),
        (r"EMPRESTIMO PESSOAL", 4),
        (r"INSTITUICAO FINANCEIRA.{0,60}?ORIGINAD", 3),
        (r"CEDULAS? DE CREDITO BANCARIO", 2),
        (r"\bCCB\b", 2),
    ),
    "Factoring": (
        (r"FOMENTO MERCANTIL", 5),
        (r"\bFACTORING\b", 5),
        (r"DUPLICATAS? (?:MERCANTIS|DE SERVICO)", 3),
        (r"CHEQUES?\b", 2),
        (r"MULTISSETORIAL", 2),
    ),
}

SINAIS_MULTI = {
    MULTICEDENTE: (r"MULTICEDENTE", r"DIVERSOS CEDENTES", r"PLURALIDADE DE CEDENTES"),
    MULTISSACADO: (
        r"MULTISSACADO",
        r"MULTI[- ]SACADO",
        r"DIVERSOS SACADOS",
        r"EXPRESSIVA DIVERSIFICACAO DE DEVEDORES",
        r"PULVERIZAD[OA]",
    ),
}

#: Abaixo desta pontuação o documento não distingue a operação, e a categoria
#: vigente permanece.  Dois sinais fracos não fazem uma conclusão.
PONTUACAO_MINIMA = 5
#: E a vantagem sobre a segunda colocada precisa ser real.  Margem de dois
#: pontos é um sinal fraco a mais, não uma conclusão: veículos de lastro misto
#: — recebíveis de cartão *e* duplicatas na mesma carteira — caem exatamente
#: aí, e reclassificá-los por isso seria cara ou coroa.
MARGEM_MINIMA = 4


@dataclass(frozen=True)
class Veredito:
    """O que o regulamento sustenta sobre um CNPJ."""

    cnpj: str
    categoria: str
    pontuacao: int
    margem: int
    evidencia: str
    termos: tuple[str, ...]
    multi: str

    @property
    def conclusivo(self) -> bool:
        return self.categoria != SEM_EVIDENCIA


def _pontuar(texto: str) -> dict[str, tuple[int, list[str], str]]:
    resultado: dict[str, tuple[int, list[str], str]] = {}
    for categoria, sinais in SINAIS.items():
        pontos = 0
        achados: list[str] = []
        trecho = ""
        for padrao, peso in sinais:
            ocorrencias = list(re.finditer(padrao, texto))
            if not ocorrencias:
                continue
            # Uma menção isolada pode ser ruído de um anexo; a partir da
            # terceira o termo descreve a operação.
            multiplicador = 2 if len(ocorrencias) >= 3 else 1
            pontos += peso * multiplicador
            achados.append(padrao)
            if not trecho:
                inicio = ocorrencias[0].start()
                trecho = texto[max(0, inicio - 140) : inicio + 260].strip()
        resultado[categoria] = (pontos, achados, trecho)
    return resultado


def _multi(texto: str) -> str:
    marcas = {
        rotulo
        for rotulo, padroes in SINAIS_MULTI.items()
        if any(re.search(padrao, texto) for padrao in padroes)
    }
    if marcas == {MULTICEDENTE, MULTISSACADO}:
        return MULTI_AMBOS
    return next(iter(marcas), "")


def classify(cnpj: str, regulamento: str) -> Veredito:
    """A categoria que o regulamento sustenta, ou ``sem evidência``."""

    texto = drop_risk_chapter(fold(regulamento))
    if not texto:
        return Veredito(cnpj, SEM_EVIDENCIA, 0, 0, "", (), "")

    pontuado = _pontuar(texto)
    ordenado = sorted(pontuado.items(), key=lambda item: item[1][0], reverse=True)
    (melhor, (pontos, achados, trecho)) = ordenado[0]
    segunda = ordenado[1][1][0] if len(ordenado) > 1 else 0
    margem = pontos - segunda
    multi = _multi(texto)

    if pontos < PONTUACAO_MINIMA or margem < MARGEM_MINIMA:
        return Veredito(cnpj, SEM_EVIDENCIA, pontos, margem, trecho, tuple(achados), multi)
    return Veredito(cnpj, melhor, pontos, margem, trecho, tuple(achados), multi)


__all__ = [
    "CATEGORIAS",
    "MARGEM_MINIMA",
    "MULTI_AMBOS",
    "MULTICEDENTE",
    "MULTISSACADO",
    "PONTUACAO_MINIMA",
    "SEM_EVIDENCIA",
    "SINAIS",
    "Veredito",
    "classify",
    "drop_risk_chapter",
    "fold",
]
