"""A lâmina do teste de estresse: gráfico, tabela dos vermelhos e apuração.

Uma lâmina só. Em cima, a mesma leitura de PDD sobre inadimplência que o painel
mostra; embaixo, o que acontece com a subordinação de cada fundo abaixo de 100%
quando o buraco de provisão é reconhecido, e o aporte que reenquadra os que
desenquadram.

Fora da área visível — à direita do limite da lâmina, no mesmo arquivo — vai a
tabela de apuração: quem não declarou PDD, inadimplência ou as duas.  Ela não
compete com a leitura da lâmina, mas viaja com o arquivo e é editável como
qualquer tabela do Office.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from pptx.util import Inches

from services.bba_deck import (
    CONTENT_WIDTH_IN,
    GRAY_100,
    GRAY_500,
    GRAY_700,
    GRAY_900,
    MARGIN_IN,
    ORANGE,
    SLIDE_WIDTH_IN,
    WHITE,
    Deck,
    fmt_mm,
)
from services.carteira_estresse import (
    CAPITAL_CONSUMIDO,
    DESENQUADRADO,
    nao_reportantes,
    sob_estresse,
)
from services.carteira_provisao import (
    attach_provisao,
    cobertura_figure,
    figure_png_bytes,
)
from services.carteira_subordinacao import resolve_portfolio, short_fund_name

KICKER = "CARTEIRA 101 · PROVISÃO NÃO RECONHECIDA"

CHART_TOP_IN = 1.24
CHART_HEIGHT_IN = 2.24
TABLE_TOP_IN = 3.78
TRANCHE_GAP_IN = 0.05
#: FIDC · cobertura · déficit · subordinação pós · folga pós · aporte.
TRANCHE_COLUMNS = (2.02, 0.70, 0.82, 0.82, 0.80, 0.84)
TABLE_HEADER = (
    "FIDC",
    "Cob.",
    "Δ R$ mm",
    "Sub pós",
    "Folga",
    "Aporte",
)

#: Vermelho de desenquadramento e verde de folga, os mesmos do resto do deck.
FILL_ABAIXO = "F7D5DA"
FILL_ACIMA = "DCEFE9"

#: A tabela acessória mora à direita da lâmina — presente no arquivo, ausente
#: da projeção.
OFFSLIDE_LEFT_IN = SLIDE_WIDTH_IN + 0.60
APURACAO_COLUMNS = (3.30, 1.55, 1.05, 1.05, 1.05, 3.05)
APURACAO_HEADER = (
    "FIDC",
    "Seção",
    "Carteira R$ mm",
    "Inad. R$ mm",
    "PDD R$ mm",
    "Caso a apurar",
)


def _pp(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    return f"{float(valor):+.1f}".replace(".", ",")


def _pct(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    return f"{float(valor):.0f}%"


def _brl_mm(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    return fmt_mm(float(valor) / 1e6, 1)


def _brl_mm_fino(valor: object) -> str:
    """Como ``_brl_mm``, mas sem transformar centavos de milhão em zero.

    Na tabela de apuração convivem R$ 2.966 mm e R$ 0,0002 mm, e arredondar o
    segundo para ``0,0`` faria parecer que o fundo não declarou nada — que é
    exatamente a distinção que a tabela existe para fazer.
    """

    if valor is None or pd.isna(valor):
        return "—"
    numero = float(valor) / 1e6
    if numero == 0:
        return "0"
    if abs(numero) < 0.01:
        return "< 0,01"
    return fmt_mm(numero, 2)


def _dados(data_dir: Path) -> pd.DataFrame:
    frame = attach_provisao(resolve_portfolio(data_dir).frame, data_dir)
    return frame.assign(rotulo=frame["fundo"].map(short_fund_name))


def _linhas_estresse(teste: pd.DataFrame) -> list[list[str]]:
    return [
        [
            str(linha.rotulo)[:30],
            _pct(linha.cobertura_pct),
            _brl_mm(linha.deficit_brl),
            _pct(linha.sub_pos_pct),
            _pp(linha.folga_pos_pp),
            _brl_mm(linha.aporte_brl) if linha.aporte_brl and linha.aporte_brl > 0 else "—",
        ]
        for linha in teste.itertuples()
    ]


def _pinta(teste: pd.DataFrame) -> dict[tuple[int, int], str]:
    """Vermelho onde a folga pós-estresse é negativa; verde onde sobra."""

    fills: dict[tuple[int, int], str] = {}
    for posicao, linha in enumerate(teste.itertuples(), start=1):
        if pd.isna(linha.folga_pos_pp):
            continue
        cor = FILL_ABAIXO if linha.folga_pos_pp < 0 else FILL_ACIMA
        fills[(posicao, 4)] = cor
        if linha.folga_pos_pp < 0:
            fills[(posicao, 5)] = FILL_ABAIXO
    return fills


def _tranche(deck: Deck, slide, teste: pd.DataFrame, x: float, altura_linha: float):
    linhas = [list(TABLE_HEADER)] + _linhas_estresse(teste)
    deck.native_table(
        slide,
        linhas,
        x,
        TABLE_TOP_IN,
        list(TRANCHE_COLUMNS),
        aligns="lrrrrr",
        size=6.5,
        row_height=altura_linha,
        header_height=0.20,
        header_fill=GRAY_100,
        header_color=GRAY_500,
        cell_fills=_pinta(teste),
    )


def _tabela_apuracao(deck: Deck, slide, pendentes: pd.DataFrame) -> None:
    """A lista de quem não reportou, fora da área projetada."""

    deck.text(
        slide,
        "Fora da lâmina — apuração: fundos sem PDD e/ou sem inadimplência declarada",
        OFFSLIDE_LEFT_IN,
        0.30,
        sum(APURACAO_COLUMNS),
        0.26,
        size=11,
        color=ORANGE,
        bold=True,
    )
    linhas = [list(APURACAO_HEADER)] + [
        [
            str(linha.rotulo)[:44],
            str(linha.categoria_estrutural),
            _brl_mm_fino(linha.carteira_dc),
            _brl_mm_fino(linha.dc_inadimplentes),
            _brl_mm_fino(linha.pdd_brl),
            str(linha.caso),
        ]
        for linha in pendentes.itertuples()
    ]
    deck.native_table(
        slide,
        linhas,
        OFFSLIDE_LEFT_IN,
        0.62,
        list(APURACAO_COLUMNS),
        aligns="llrrrl",
        size=7,
        row_height=0.19,
        header_height=0.24,
        header_fill=GRAY_100,
        header_color=GRAY_500,
    )


def append_stress_slide(presentation, data_dir: Path):
    """Acrescenta a lâmina do teste de estresse ao fim da apresentação."""

    dados = _dados(data_dir)
    teste = sob_estresse(dados)
    pendentes = nao_reportantes(dados)
    if teste.empty:
        return presentation

    quebram = teste[teste["estresse_status"].isin({DESENQUADRADO, CAPITAL_CONSUMIDO})]
    aporte_total = float(teste["aporte_brl"].fillna(0).sum())

    deck = Deck(KICKER, presentation)
    slide = deck.slide(
        f"Teste de estresse | {len(quebram)} de {len(teste)} desenquadram"
    )

    imagem = figure_png_bytes(
        cobertura_figure(dados, figsize=(12.0, 2.24), dpi=220)
    )
    slide.shapes.add_picture(
        BytesIO(imagem),
        Inches(MARGIN_IN),
        Inches(CHART_TOP_IN),
        Inches(CONTENT_WIDTH_IN),
        Inches(CHART_HEIGHT_IN),
    )

    deck.text(
        slide,
        "Δ = inadimplência − PDD é abatido da classe subordinada e do total de cotas. "
        f"Aporte somado para reenquadrar os {len(quebram)}: R$ {_brl_mm(aporte_total)} mm.",
        MARGIN_IN,
        CHART_TOP_IN + CHART_HEIGHT_IN + 0.06,
        CONTENT_WIDTH_IN,
        0.24,
        size=8.5,
        color=GRAY_700,
    )

    metade = (len(teste) + 1) // 2
    largura_tranche = sum(TRANCHE_COLUMNS)
    # O rodapé começa por volta de 7,05"; a última linha não pode encostar nele.
    altura_linha = min(
        0.165, (6.94 - TABLE_TOP_IN - 0.20) / max(metade, 1)
    )
    _tranche(deck, slide, teste.iloc[:metade], MARGIN_IN, altura_linha)
    _tranche(
        deck,
        slide,
        teste.iloc[metade:],
        MARGIN_IN + largura_tranche + TRANCHE_GAP_IN,
        altura_linha,
    )

    _tabela_apuracao(deck, slide, pendentes)
    deck.footer(
        slide,
        "CVM, Informe Mensal FIDC — Tabela I (competência mais recente de cada fundo) "
        "e regulamentos na FundosNet/B3. A carteira reportada já é líquida de PDD; a "
        "provisão é tratada como integralmente alocada aos créditos inadimplentes.",
    )
    return presentation


__all__ = ["append_stress_slide"]
