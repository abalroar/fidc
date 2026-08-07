"""Os slides do Top 100 para revisão do universo Middle.

Cem linhas não cabem em um slide legível, e condensá-las produziria uma tabela
que ninguém lê nem edita.  Elas entram em blocos de
:data:`ROWS_PER_SLIDE`, cada bloco em **uma tabela nativa do Office** — o
revisor ordena, filtra, corrige um nome e preenche a coluna ``MIDDLE``
diretamente no PowerPoint, ou cola o bloco no Excel.

A ordenação é por patrimônio líquido, do maior para o menor: é ele que diz a
materialidade de cada veículo na revisão.  Oito dos cem não reportaram PL em
competência alguma e fecham a lista, identificados como tal em vez de
receberem um número inventado.
"""

from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

from services.carteira_subordinacao import short_fund_name

#: Sufixos societários que não identificam ninguém e comem a largura da célula.
#: A âncora no fim é essencial: sem ela, "CLOUDWALK INSTITUICAO DE PAGAMENTO E
#: SERVICOS LTDA" perde o miolo e vira "Cloudwalk E Servicos".
_SUFIXO = re.compile(
    r"(?:\s*[,-]?\s*(?:S[/.]?\s?A\.?|LTDA\.?|EIRELI|\bME\b|\bEPP\b|"
    r"SOCIEDADE DE CREDITO DIRETO|SOCIEDADE DE CREDITO, FINANCIAMENTO E INVESTIMENTO"
    r"))+\s*\.?$",
    re.IGNORECASE,
)


def short_company(nome: str, limite: int) -> str:
    """Razão social legível: sem o sufixo societário final, em caixa de título."""

    bruto = _text(nome, 10_000)
    if bruto == "—":
        return bruto
    texto = re.sub(r"\s+", " ", _SUFIXO.sub("", bruto)).strip(" -,.")
    if not texto:
        texto = bruto
    if texto.isupper():
        texto = texto.title()
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"
REVIEW_NAME = "top100_fidcs_middle_review.csv"
#: Vinte linhas cabem com fonte legível e ainda deixam respiro no rodapé.
ROWS_PER_SLIDE = 20
KICKER = "TOP 100 FIDCs · REVISÃO DO UNIVERSO MIDDLE"
SOURCE = (
    "CVM: Informe Mensal FIDC (PL, competência mais recente de cada fundo) e "
    "Sistema de Registro de Ofertas (volume emitido em 2026). Cedente conforme "
    "declarado no Informe. Preencher a coluna MIDDLE com Sim ou Não."
)

#: Colunas do slide, na ordem: o que identifica o veículo, o que mede a
#: materialidade e o que sustenta a decisão de Middle.
#: A soma tem de fechar em ``CONTENT_WIDTH_IN``; passando disso, a última
#: coluna sai pela borda da lâmina — e a última é justamente a que o revisor
#: preenche.
COLUMNS: tuple[tuple[str, str, float, str], ...] = (
    ("rank_pl", "#", 0.38, "r"),
    ("FIDC", "FIDC", 3.10, "l"),
    ("cnpj", "CNPJ", 1.22, "l"),
    ("pl_mm", "PL (R$ mm)", 0.92, "r"),
    ("Volume 2026 (R$ mi)", "Emissão 26 (R$ mi)", 1.00, "r"),
    ("Coordenador líder", "Coordenador líder", 1.28, "l"),
    ("Razão social cedente", "Cedente", 2.00, "l"),
    ("Setor cedente", "Setor do cedente", 1.40, "l"),
    ("MIDDLE (preencher)", "MIDDLE", 0.75, "l"),
)


def load_review(data_dir: Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    """A base de revisão, ordenada por PL do maior para o menor."""

    frame = pd.read_csv(Path(data_dir) / REVIEW_NAME, dtype=str)
    frame["pl_num"] = pd.to_numeric(frame["pl_mm"], errors="coerce")
    return frame.sort_values(
        "pl_num", ascending=False, na_position="last"
    ).reset_index(drop=True)


def _number(value: object, decimals: int = 1) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "n/d"
    try:
        number = float(str(value))
    except ValueError:
        return "n/d"
    return f"{number:,.{decimals}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _text(value: object, limite: int) -> str:
    texto = "" if value is None or pd.isna(value) else str(value).strip()
    if not texto:
        return "—"
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def _cnpj(value: object) -> str:
    digits = "" if value is None or pd.isna(value) else str(value).zfill(14)
    if len(digits) != 14:
        return "—"
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


#: Quantos caracteres cabem por coluna antes de a célula quebrar em duas
#: linhas e desalinhar a tabela.  Calibrado para Arial 8,6 pt na largura de
#: cada coluna.
_LIMITES = {
    "FIDC": 46,
    "Coordenador líder": 19,
    "Razão social cedente": 28,
    "Setor cedente": 21,
    "MIDDLE (preencher)": 10,
}


def table_rows(bloco: pd.DataFrame) -> list[list[str]]:
    rows: list[list[str]] = [[titulo for _key, titulo, _w, _a in COLUMNS]]
    for registro in bloco.to_dict("records"):
        linha: list[str] = []
        for key, _titulo, _largura, _alinhamento in COLUMNS:
            valor = registro.get(key)
            if key == "cnpj":
                linha.append(_cnpj(valor))
            elif key == "rank_pl":
                linha.append(_text(valor, 4))
            elif key == "Razão social cedente":
                linha.append(short_company(valor, _LIMITES[key]))
            elif key == "FIDC":
                # No slide vale o nome próprio: a razão social completa enche a
                # célula com boilerplate registral e esconde o que identifica o
                # fundo.  A planilha guarda a denominação inteira.
                linha.append(short_fund_name(str(valor or ""), limite=_LIMITES["FIDC"]))
            elif key in {"pl_mm", "Volume 2026 (R$ mi)"}:
                linha.append(_number(valor))
            else:
                linha.append(_text(valor, _LIMITES.get(key, 40)))
        rows.append(linha)
    return rows


def append_top100_slides(presentation, data_dir: Path = DEFAULT_DATA_DIR) -> int:
    """Acrescenta os slides do Top 100 ao fim do deck e devolve quantos."""

    from services.bba_deck import Deck

    frame = load_review(data_dir)
    if frame.empty:
        return 0

    deck = Deck(KICKER, presentation)
    blocos = max(1, -(-len(frame) // ROWS_PER_SLIDE))
    for indice in range(blocos):
        bloco = frame.iloc[indice * ROWS_PER_SLIDE : (indice + 1) * ROWS_PER_SLIDE]
        primeiro = int(indice * ROWS_PER_SLIDE) + 1
        ultimo = primeiro + len(bloco) - 1
        slide = deck.slide(
            f"Top 100 por PL | {primeiro}º a {ultimo}º", KICKER
        )
        deck.native_table(
            slide,
            table_rows(bloco),
            0.62,
            1.40,
            [largura for _k, _t, largura, _a in COLUMNS],
            row_height=0.245,
            header_height=0.30,
            size=8.6,
            aligns="".join(alinhamento for _k, _t, _w, alinhamento in COLUMNS),
        )
        deck.footer(slide, SOURCE)
    return blocos


__all__ = [
    "COLUMNS",
    "KICKER",
    "REVIEW_NAME",
    "ROWS_PER_SLIDE",
    "append_top100_slides",
    "load_review",
    "table_rows",
]
