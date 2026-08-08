"""Por que um FIDC não reporta inadimplência e/ou PDD — o que os documentos dizem.

Zero de inadimplência num fundo com carteira viva tem explicações legítimas, e
todas moram no regulamento:

``recompra_substituicao``
    o cedente é obrigado a recomprar ou substituir o direito creditório vencido,
    de modo que o atraso sai da carteira antes de virar inadimplência;

``resolucao_cessao``
    a cessão se resolve de pleno direito quando o crédito não é pago, com o
    mesmo efeito;

``coobrigacao``
    o cedente responde pelo crédito — atenção ao oposto, "sem coobrigação", que
    é a redação mais comum e **não** justifica coisa alguma;

``liquidacao_curta``
    recebível de adquirência liquida em poucos dias, e a janela para inadimplir
    é estreita;

``politica_pdd``
    o critério de provisionamento que o próprio regulamento fixa.

E há a contraprova: relatórios de agência de rating, demonstrações financeiras e
relatórios de verificação de lastro trazem inadimplência e provisão medidas por
terceiros.  Quando o número existe ali e não no Informe, o silêncio na CVM passa
a ser lacuna de reporte, não característica da estrutura.

O módulo **não conclui além do texto**.  Cada achado carrega o trecho literal, o
documento e a página; o que não foi achado sai como lacuna nomeada, para o
analista ir ler.  Nenhuma família é inferida do tipo do fundo, do nome ou do
setor.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable

import pandas as pd


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"
APURACAO_NAME = "carteira_apuracao_documental.csv"


#: Uma família de cláusula: nome, o que ela justifica e como se reconhece.
FAMILIAS: dict[str, dict[str, object]] = {
    "recompra_substituicao": {
        "rotulo": "recompra/substituição pelo cedente",
        "padrao": re.compile(
            r"(?:obriga\w*\s+a\s+(?:substituir|recomprar)"
            r"|dever[áa]\s+(?:substituir|recomprar)"
            r"|substitui[çc][ãa]o\s+(?:obrigat[óo]ria|de\s+Direitos\s+Credit[óo]rios\s+"
            r"(?:inadimplid|vencid))"
            r"|recompra\s+(?:obrigat[óo]ria|dos?\s+Direitos\s+Credit[óo]rios))",
            re.I,
        ),
    },
    "resolucao_cessao": {
        "rotulo": "resolução da cessão",
        "padrao": re.compile(
            r"(?:resolu[çc][ãa]o\s+d[ao]\s+[Cc]ess[ãa]o"
            r"|cess[ãa]o\s+(?:ser[áa]|fica)\s+resolvida"
            r"|resolvid[ao]\s+de\s+pleno\s+direito"
            r"|condi[çc][ãa]o\s+resolutiva)",
            re.I,
        ),
    },
    "coobrigacao": {
        "rotulo": "coobrigação do cedente",
        "padrao": re.compile(
            r"(?:com\s+coobriga[çc][ãa]o|coobriga[çc][ãa]o\s+d[oa]s?\s+[Cc]edente"
            r"|direito\s+de\s+regresso|solidariamente\s+respons[áa]vel)",
            re.I,
        ),
        # A cessão sem coobrigação é a redação mais comum, e ela diz o oposto.
        # A negativa vem em várias roupagens, então em vez de tentar esgotá-las
        # o achado sai com o sinal marcado e o trecho literal ao lado.
        "negacao": re.compile(
            r"(?:sem\s+(?:qualquer\s+)?(?:coobriga[çc][ãa]o|direito\s+de\s+regresso"
            r"|direito\s+de\s+recompra|solidariedade)"
            r"|n[ãa]o\s+(?:dar[áa]|haver[áa]|ter[áa]|assume|assumir[áa])"
            r"(?:\s+\w+){0,8}\s+(?:regresso|coobriga[çc][ãa]o)"
            r"|inexist[êe]ncia\s+de\s+(?:direito\s+de\s+)?(?:regresso|coobriga))",
            re.I,
        ),
    },
    "liquidacao_curta": {
        "rotulo": "liquidação em poucos dias",
        "padrao": re.compile(
            r"(?:arranjo\s+de\s+pagamento|credenciador\w*|subcredenciador\w*"
            r"|Unidades?\s+de\s+Receb[íi]veis|agenda\s+de\s+receb[íi]veis"
            r"|liquida[çc][ãa]o\s+em\s+D\s*\+\s*\d{1,2})",
            re.I,
        ),
    },
    "politica_pdd": {
        "rotulo": "política de provisionamento",
        "padrao": re.compile(
            r"(?:provis[ãa]o\s+para\s+(?:cr[ée]ditos\s+de\s+liquida[çc][ãa]o\s+duvidosa"
            r"|perdas|devedores\s+duvidosos)"
            r"|redu[çc][ãa]o\s+ao\s+valor\s+recuper[áa]vel"
            r"|crit[ée]rios?\s+de\s+provisionamento)",
            re.I,
        ),
    },
}

#: Onde a contraprova de terceiro costuma estar.
CATEGORIAS_CONTRAPROVA = {
    "Relatório de Agência de Rating": "rating",
    "Outros Relatórios": "outros relatórios",
    "Demonstrações Financeiras": "demonstrações financeiras",
    "Informe Trimestral": "informe trimestral",
}

#: O que uma contraprova precisa mencionar para valer como medição de terceiro.
_MEDIDA_TERCEIRO = re.compile(
    r"(?:inadimpl\w+|atraso\w*|vencid\w+\s+e\s+n[ãa]o\s+pag\w+|PDD"
    r"|provis[ãa]o|NPL|over\s*\d{1,3})",
    re.I,
)
_COM_NUMERO = re.compile(r"\d{1,3}(?:[.,]\d+)?\s*%|R\$\s*[\d.]+")

#: Documentos onde a cláusula é procurada.
CATEGORIAS_CLAUSULA = {"Regulamento", "Atos de Deliberação do Administrador"}


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "")


def _trecho(texto: str, marca: re.Match, antes: int = 180, depois: int = 320) -> str:
    return texto[max(0, marca.start() - antes) : marca.end() + depois].strip()


def varrer_clausulas(documentos: Iterable[dict]) -> dict[str, dict[str, object]]:
    """Procura cada família de cláusula nos documentos normativos do fundo."""

    resultado: dict[str, dict[str, object]] = {}
    for chave, familia in FAMILIAS.items():
        resultado[chave] = {
            "achou": False,
            "sinal": "",
            "trecho": "",
            "documento": "",
            "pagina": None,
        }

    for documento in documentos:
        if documento.get("categoria") not in CATEGORIAS_CLAUSULA:
            continue
        identificador = f"{documento.get('categoria')} {documento.get('id')}"
        for numero_pagina, pagina in enumerate(documento.get("pages") or [], start=1):
            texto = _normalizar(pagina)
            for chave, familia in FAMILIAS.items():
                if resultado[chave]["achou"]:
                    continue
                marca = familia["padrao"].search(texto)
                if not marca:
                    continue
                trecho = _trecho(texto, marca)
                negacao = familia.get("negacao")
                sinal = "afirmativa"
                if negacao is not None and negacao.search(trecho):
                    sinal = "negativa"
                resultado[chave] = {
                    "achou": True,
                    "sinal": sinal,
                    "trecho": trecho[:500],
                    "documento": identificador,
                    "pagina": numero_pagina,
                }
    return resultado


#: As duas linhas estruturadas do Informe Trimestral, que medem o mesmo que o
#: Informe Mensal e servem de contraprova direta.
_LINHA_TRIMESTRAL = re.compile(
    r"1\.?\s*([bc])\)\s*(?:Direitos\s+Credit[óo]rios\s+Vencidos|PDD)\s*"
    r"(-?[\d.]+,\d{2}|-?\d+)\s*(?:(-?[\d.,]+)\s*%)?",
    re.I,
)

CONFIRMA_ZERO = "terceiro também mede zero"
REFUTA = "terceiro mede valor positivo"
SEM_MEDICAO = "sem medição estruturada de terceiro"


def _valor(bruto: str) -> float:
    limpo = bruto.strip()
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    return float(limpo)


def medir_terceiro(documentos: Iterable[dict]) -> dict[str, object]:
    """Vencidos e PDD como o Informe Trimestral os declara.

    É a contraprova mais dura disponível: mede exatamente as duas grandezas que
    o Informe Mensal traz zeradas, e vem do mesmo administrador.  O Informe
    Trimestral saiu de uso, então a competência costuma ser antiga — ela vai na
    saída para que ninguém a leia como contemporânea.
    """

    melhor: dict[str, object] | None = None
    for documento in documentos:
        if (documento.get("tipo") or "").strip() != "Informe Trimestral":
            continue
        referencia = documento.get("data_referencia") or ""
        for numero_pagina, pagina in enumerate(documento.get("pages") or [], start=1):
            texto = _normalizar(pagina)
            achados = _LINHA_TRIMESTRAL.findall(texto)
            valores = {letra.lower(): _valor(valor) for letra, valor, _pct in achados}
            if "b" not in valores or "c" not in valores:
                continue
            candidato = {
                "referencia": referencia,
                "pagina": numero_pagina,
                "vencidos_brl": valores["b"],
                "pdd_brl": valores["c"],
                "documento": f"Informe Trimestral {documento.get('id')}",
            }
            if melhor is None or referencia > str(melhor["referencia"]):
                melhor = candidato
            break
    if melhor is None:
        return {"veredito": SEM_MEDICAO}
    positivo = melhor["vencidos_brl"] > 0 or melhor["pdd_brl"] > 0
    melhor["veredito"] = REFUTA if positivo else CONFIRMA_ZERO
    return melhor

def varrer_contraprova(documentos: Iterable[dict]) -> dict[str, object]:
    """Inadimplência ou provisão medidas por terceiro, com o trecho literal."""

    achados: list[dict[str, object]] = []
    for documento in documentos:
        tipo = (documento.get("tipo") or "").strip()
        categoria = documento.get("categoria")
        rotulo = CATEGORIAS_CONTRAPROVA.get(tipo) or CATEGORIAS_CONTRAPROVA.get(categoria)
        if rotulo is None:
            continue
        for numero_pagina, pagina in enumerate(documento.get("pages") or [], start=1):
            texto = _normalizar(pagina)
            for marca in _MEDIDA_TERCEIRO.finditer(texto):
                janela = _trecho(texto, marca, 140, 260)
                if not _COM_NUMERO.search(janela):
                    continue
                achados.append(
                    {
                        "fonte": rotulo,
                        "documento": f"{tipo or categoria} {documento.get('id')}",
                        "pagina": numero_pagina,
                        "trecho": janela[:420],
                    }
                )
                break
    vistos: set[str] = set()
    unicos = []
    for achado in achados:
        if achado["fonte"] in vistos:
            continue
        vistos.add(achado["fonte"])
        unicos.append(achado)
    return {"fontes": sorted(vistos), "achados": unicos[:4]}


def load_apuracao(data_dir: Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    """O diagnóstico documental por CNPJ, se materializado.

    Ausente o arquivo, a tabela de apuração continua de pé sem a coluna — o
    painel não depende da varredura para listar quem não reportou.
    """

    caminho = Path(data_dir) / APURACAO_NAME
    if not caminho.is_file():
        return pd.DataFrame(columns=["cnpj", "diagnostico", "lacunas"])
    frame = pd.read_csv(caminho, dtype={"cnpj": str}).fillna("")
    frame["cnpj"] = frame["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14)
    return frame.drop_duplicates("cnpj", keep="last")


__all__ = [
    "APURACAO_NAME",
    "CONFIRMA_ZERO",
    "REFUTA",
    "SEM_MEDICAO",
    "medir_terceiro",
    "CATEGORIAS_CLAUSULA",
    "CATEGORIAS_CONTRAPROVA",
    "FAMILIAS",
    "load_apuracao",
    "varrer_clausulas",
    "varrer_contraprova",
]
