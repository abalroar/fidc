"""Revalida, contra o regulamento, o mínimo de subordinação de cada FIDC.

O registro guarda o mínimo com documento e página. Este módulo faz o caminho
inverso: relê o documento, procura de forma independente a cláusula que fixa o
piso e diz se o número em uso se sustenta.

Três armadilhas moldaram o extrator, e todas apareceram nos documentos reais:

**O regulamento diz a mesma coisa de duas formas.** Uns fixam a subordinação
diretamente ("as Cotas Subordinadas representarão no mínimo 20% do Patrimônio
Líquido"); outros fixam a cobertura da sênior ("relação mínima de 125% entre o
Patrimônio Líquido e as Cotas Seniores").  São equivalentes — 125% de cobertura
é 20% de subordinação —, e ignorar a segunda forma produziria divergência onde
há acordo.  A conversão é ``sub = 1 − 1/cobertura``.

**Há outros índices no mesmo documento.** O *Índice de Resolução de Cessão*, o
de liquidez e o de cobertura de despesas moram nas mesmas páginas e têm
percentuais próprios.  Capturar qualquer percentual perto da palavra
"subordinação" traz esses números junto.

**Limites de concentração se parecem com pisos.** "Endossante cujos Direitos
Creditórios representem pelo menos 50% da carteira" tem piso e percentual, e não
é subordinação nenhuma.

O que o módulo **não** faz é inventar o número quando o documento não o traz.
Muitos regulamentos definem o índice no glossário e remetem o percentual a um
**Suplemento** ou **Anexo da Classe** que não acompanha o regulamento na
FundosNET; a saída é ``remete a suplemento``, não uma estimativa.  Um "não
localizei" vale mais do que um número plausível sem lastro.
"""

from __future__ import annotations

import re
from typing import Iterable

import pandas as pd


CONFIRMA = "confirma"
DIVERGE = "diverge"
REMETE_SUPLEMENTO = "remete a suplemento"
SEM_CLAUSULA = "sem cláusula localizada"
SEM_DOCUMENTO = "sem documento"

#: Tolerância em pontos percentuais para considerar que dois valores batem.
#: Um pouco larga de propósito: a conversão de cobertura arredondada — 117,64%
#: em vez de 117,647% — desloca o resultado em centésimos.
TOLERANCIA_PP = 0.55

#: Quanto texto entra na janela em torno do nome do índice.
JANELA_ANTES = 260
JANELA_DEPOIS = 760

#: O índice que fixa a subordinação diretamente.
_INDICE_SUB = re.compile(
    r"(?:[ÍI]ndice\s+de\s+Subordina\w*"
    r"|Raz[ãa]o\s+de\s+Subordina\w*"
    r"|Aloca[çc][ãa]o\s+M[íi]nima\s+de\s+Cotas\s+Subordinada\w*"
    r"|Cotas\s+Subordinadas?\s+(?:\w+\s+){0,3}representar[ãa]o"
    r"|percentual\s+m[íi]nimo\s+de\s+Cotas\s+Subordinada\w*)",
    re.I,
)
#: O índice que fixa a mesma coisa pelo avesso: cobertura da classe sênior.
_INDICE_COB = re.compile(
    r"(?:[ÍI]ndice\s+de\s+Cobertura\s+S[êe]nior"
    r"|Raz[ãa]o\s+de\s+Garantia"
    r"|rela[çc][ãa]o\s+m[íi]nima(?:\s+\w+){0,6}\s+Cotas\s+S[êe]nior)",
    re.I,
)
#: A frase que fixa um piso.
_PISO = re.compile(
    r"(?:no\s+m[íi]nimo|m[íi]nimo\s+de|m[íi]nima\s+(?:de|equivalente)"
    r"|n[ãa]o\s+inferior\s+a|ao\s+menos|igual\s+ou\s+superior\s+a"
    r"|pelo\s+menos|dever[áa]\s+ser\s+(?:superior|igual)"
    r"|Subordina[çc][ãa]o\s+M[íi]nima(?:\s+admitida)?(?:\s+no\s+FUNDO)?\s+[ée]\s+de)",
    re.I,
)

#: O piso da estrutura é sempre medido contra o patrimônio.  Quando a janela
#: traz um percentual assim ancorado, ele manda: os outros costumam ser a fatia
#: de uma classe dentro da própria subordinação ("10% desta relação").
_ANCORA_PL = re.compile(
    r"\s*\([^)]*\)\s*(?:do|de)\s+Patrim[ôo]nio\s+L[íi]quido|\s*(?:do|de)\s+Patrim[ôo]nio\s+L[íi]quido",
    re.I,
)
_PCT = re.compile(r"(\d{1,3}(?:[.,]\d{1,4})?)\s*%")
_REMISSAO = re.compile(
    r"(?:respectivo\s+Suplemento|no\s+Suplemento|Anexo\s+da\s+Classe"
    r"|Suplemento\s+da\s+(?:S[ée]rie|Subclasse|Classe)|definido\s+em\s+Suplemento"
    r"|conforme\s+definido\s+no\s+(?:respectivo\s+)?Ap[êe]ndice)",
    re.I,
)
#: Outros índices do mesmo regulamento, com percentuais próprios.
_OUTRO_INDICE = re.compile(
    r"(?:[ÍI]ndice\s+de\s+Resolu[çc][ãa]o|[ÍI]ndice\s+de\s+Liquidez"
    r"|[ÍI]ndice\s+de\s+Cobertura\s+de\s+Despesas|[ÍI]ndice\s+de\s+Inadimpl"
    r"|[ÍI]ndice\s+de\s+Atraso|[ÍI]ndice\s+de\s+Perda|Taxa\s+de\s+Performance)",
    re.I,
)
#: Limite de concentração — tem piso e percentual, e não é subordinação.
_CONCENTRACAO = re.compile(
    r"(?:Endossante|Cedente|Devedor|Sacado)\w*\s+(?:\w+\s+){0,8}"
    r"(?:representem|represente|corresponda|superior\s+a)",
    re.I,
)
#: Deliberação, quórum e remuneração usam "subordinada" noutro sentido.
_RUIDO = re.compile(
    r"(?:est[ãa]o\s+subordinad|subordinadas?\s+[àa]\s+aprova"
    r"|remunera[çc][ãa]o\s+das?\s+Cotas?\s+Subordinada"
    r"|Cotas\s+em\s+circula[çc][ãa]o|Cotistas\s+presentes|Assembleia\s+Geral"
    r"|Valor\s+Unit[áa]rio\s+de\s+Emiss[ãa]o|Per[íi]odo\s+de\s+Car[êe]ncia"
    r"|monitorar|Taxa\s+de\s+Administra)",
    re.I,
)

#: O percentual só prova o piso quando está colado nele.  Solto na janela, ele
#: pode ser de qualquer outra frase que a janela alcançou.
DISTANCIA_PISO = 120


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "")


def _numero(bruto: str) -> float:
    return float(bruto.replace(".", "").replace(",", ".")) if "," in bruto else float(bruto)


def cobertura_para_subordinacao(cobertura_pct: float) -> float | None:
    """125% de cobertura da sênior é 20% de subordinação."""

    if cobertura_pct <= 100:
        return None
    return (1.0 - 1.0 / (cobertura_pct / 100.0)) * 100.0


def candidatos(paginas: Iterable[str]) -> list[dict[str, object]]:
    """Os trechos que fixam um piso de subordinação, em qualquer das duas formas."""

    achados: list[dict[str, object]] = []
    for numero_pagina, pagina in enumerate(paginas, start=1):
        texto = _normalizar(pagina)
        for familia, padrao in (("subordinacao", _INDICE_SUB), ("cobertura", _INDICE_COB)):
            for marca in padrao.finditer(texto):
                inicio = max(0, marca.start() - JANELA_ANTES)
                fim = min(len(texto), marca.end() + JANELA_DEPOIS)
                janela = texto[inicio:fim]
                if _RUIDO.search(janela) or _CONCENTRACAO.search(janela):
                    continue
                # A janela pode alcançar o índice vizinho; nesse caso o
                # percentual pode ser dele, e o trecho não serve de prova.
                if _OUTRO_INDICE.search(janela):
                    continue
                # Só valem os percentuais que aparecem logo depois de uma
                # expressão de piso — é isso que separa a cláusula do resto.
                brutos: list[float] = []
                ancorados: list[float] = []
                for piso in _PISO.finditer(janela):
                    vizinho = _PCT.search(janela, piso.end(), piso.end() + DISTANCIA_PISO)
                    if not vizinho:
                        continue
                    valor = _numero(vizinho.group(1))
                    brutos.append(valor)
                    if _ANCORA_PL.match(janela, vizinho.end()):
                        ancorados.append(valor)
                if ancorados:
                    brutos = ancorados
                remete = bool(_REMISSAO.search(janela))
                if not brutos and not remete:
                    continue
                if familia == "cobertura":
                    valores = [
                        convertido
                        for bruto in brutos
                        if (convertido := cobertura_para_subordinacao(bruto)) is not None
                    ]
                else:
                    valores = [b for b in brutos if 0 < b <= 100]
                achados.append(
                    {
                        "pagina": numero_pagina,
                        "familia": familia,
                        "trecho": janela.strip()[:700],
                        "percentuais": valores,
                        "percentuais_brutos": brutos,
                        "tem_piso": bool(brutos),
                        "remete_suplemento": remete,
                    }
                )
    return achados


_ORDEM = {CONFIRMA: 0, DIVERGE: 1, REMETE_SUPLEMENTO: 2, SEM_CLAUSULA: 3}


def avaliar(
    minimo_em_uso: float | None, achados: list[dict[str, object]]
) -> dict[str, object]:
    """O veredito e o trecho literal que o sustenta."""

    vazio = {
        "veredito": SEM_CLAUSULA,
        "valor_documental_pct": None,
        "familia": "",
        "pagina": None,
        "trecho": "",
    }
    if not achados:
        return vazio

    com_piso = [a for a in achados if a["tem_piso"] and a["percentuais"]]
    if minimo_em_uso is not None:
        for achado in com_piso:
            for valor in achado["percentuais"]:
                if abs(valor - minimo_em_uso) <= TOLERANCIA_PP:
                    return {
                        "veredito": CONFIRMA,
                        "valor_documental_pct": round(valor, 4),
                        "familia": achado["familia"],
                        "pagina": achado["pagina"],
                        "trecho": achado["trecho"],
                    }

    remissivos = [a for a in achados if a["remete_suplemento"]]
    if remissivos:
        # O piso existe, mas mora fora do documento: nada a confrontar.
        return {
            "veredito": REMETE_SUPLEMENTO,
            "valor_documental_pct": None,
            "familia": remissivos[0]["familia"],
            "pagina": remissivos[0]["pagina"],
            "trecho": remissivos[0]["trecho"],
        }
    if com_piso and minimo_em_uso is not None:
        escolhido = com_piso[0]
        return {
            "veredito": DIVERGE,
            "valor_documental_pct": round(escolhido["percentuais"][0], 4),
            "familia": escolhido["familia"],
            "pagina": escolhido["pagina"],
            "trecho": escolhido["trecho"],
        }
    return {**vazio, "pagina": achados[0]["pagina"], "trecho": achados[0]["trecho"]}


def validar(
    registro: pd.DataFrame, documentos: dict[str, list[tuple[str, list[str]]]]
) -> pd.DataFrame:
    """Uma linha por CNPJ do registro, com veredito, valor e trecho literal.

    ``documentos`` mapeia CNPJ para uma lista de ``(identificador, páginas)``,
    já na ordem em que devem ser tentados — regulamento vigente primeiro.
    """

    linhas: list[dict[str, object]] = []
    for fundo in registro.itertuples():
        minimo = fundo.subordinacao_estrutural_pct
        if pd.isna(minimo):
            minimo = fundo.subordinacao_minima_pct
        minimo = None if pd.isna(minimo) else float(minimo)

        acervo = documentos.get(fundo.cnpj) or []
        if not acervo:
            linhas.append(
                {
                    "cnpj": fundo.cnpj,
                    "minimo_em_uso_pct": minimo,
                    "veredito": SEM_DOCUMENTO,
                    "valor_documental_pct": None,
                    "familia": "",
                    "documento": "",
                    "pagina": None,
                    "trecho": "",
                }
            )
            continue

        melhor: dict[str, object] | None = None
        for identificador, paginas in acervo:
            resultado = avaliar(minimo, candidatos(paginas))
            resultado["documento"] = identificador
            if melhor is None or _ORDEM[resultado["veredito"]] < _ORDEM[melhor["veredito"]]:
                melhor = resultado
            if melhor["veredito"] == CONFIRMA:
                break

        linhas.append({"cnpj": fundo.cnpj, "minimo_em_uso_pct": minimo, **melhor})
    return pd.DataFrame(linhas)


__all__ = [
    "CONFIRMA",
    "DIVERGE",
    "JANELA_ANTES",
    "JANELA_DEPOIS",
    "REMETE_SUPLEMENTO",
    "SEM_CLAUSULA",
    "SEM_DOCUMENTO",
    "TOLERANCIA_PP",
    "avaliar",
    "candidatos",
    "cobertura_para_subordinacao",
    "validar",
]
