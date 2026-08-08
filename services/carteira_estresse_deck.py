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
from services.carteira_estresse import estressar, nao_reportantes
from services.carteira_triagem import DECIDIR, pauta, resumo
from services.carteira_apuracao_documental import load_apuracao
from services.carteira_provisao import (
    attach_provisao,
    cobertura_figure,
    figure_png_bytes,
)
from services.carteira_deck import REPLACED_SLIDE_RANGE
from services.carteira_subordinacao import resolve_portfolio, short_fund_name

KICKER = "CARTEIRA 101 · PROVISÃO NÃO RECONHECIDA"

#: A lâmina fecha o bloco de subordinação, logo após os índices de sub v. mínimo.
_, ULTIMO_SLIDE_ESTRUTURAL = REPLACED_SLIDE_RANGE

CHART_TOP_IN = 1.24
CHART_HEIGHT_IN = 2.24
TABLE_TOP_IN = 3.78
TRANCHE_GAP_IN = 0.05
#: Onde o número de página mora no rodapé padrão do deck.
PAGINA_X_IN = 12.25
#: FIDC · seção · PL · cobertura · sub antes · sub pós · mínimo · folga · aporte.
PAUTA_COLUMNS = (2.80, 1.70, 0.95, 0.72, 1.00, 0.92, 0.82, 0.86, 1.10, 1.18)
TABLE_HEADER = (
    "FIDC",
    "Seção",
    "PL R$ mm",
    "Cob.",
    "Sub antes",
    "Sub pós",
    "Mínimo",
    "Folga",
    "Aporte R$ mm",
    "Ação",
)

#: Vermelho de desenquadramento e verde de folga, os mesmos do resto do deck.
FILL_ABAIXO = "F7D5DA"
FILL_ATENCAO = "FCEFCF"

#: A tabela acessória mora à direita da lâmina — presente no arquivo, ausente
#: da projeção.
OFFSLIDE_LEFT_IN = SLIDE_WIDTH_IN + 0.60
APURACAO_COLUMNS = (2.60, 1.45, 0.95, 0.95, 0.95, 9.60)
APURACAO_HEADER = (
    "FIDC",
    "Seção",
    "Carteira R$ mm",
    "Inad. R$ mm",
    "PDD R$ mm",
    "Caso e apuração documental",
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


def _linhas_pauta(mesa: pd.DataFrame) -> list[list[str]]:
    return [
        [
            str(linha.rotulo)[:40],
            str(linha.categoria_estrutural)[:24],
            _brl_mm(linha.vl_cotas_total),
            _pct(linha.cobertura_pct),
            _pct(linha.sub_antes_pct),
            _pct(linha.sub_pos_pct),
            _pct(linha.referencia_pct),
            _pp(linha.folga_pos_pp),
            _brl_mm(linha.aporte_brl) if linha.aporte_brl and linha.aporte_brl > 0 else "—",
            "Aportar" if linha.triagem_status == DECIDIR else "Acompanhar",
        ]
        for linha in mesa.itertuples()
    ]


def _pinta(mesa: pd.DataFrame) -> dict[tuple[int, int], str]:
    """Vermelho em quem desenquadra; amarelo em quem fica com folga fina."""

    fills: dict[tuple[int, int], str] = {}
    for posicao, linha in enumerate(mesa.itertuples(), start=1):
        cor = FILL_ABAIXO if linha.triagem_status == DECIDIR else FILL_ATENCAO
        for coluna in (7, 8, 9):
            fills[(posicao, coluna)] = cor
    return fills


def _tabela_pauta(deck: Deck, slide, mesa: pd.DataFrame) -> None:
    linhas = [list(TABLE_HEADER)] + _linhas_pauta(mesa)
    deck.native_table(
        slide,
        linhas,
        MARGIN_IN,
        TABLE_TOP_IN,
        list(PAUTA_COLUMNS),
        aligns="llrrrrrrrl",
        size=8,
        row_height=0.205,
        header_height=0.24,
        header_fill=GRAY_100,
        header_color=GRAY_500,
        cell_fills=_pinta(mesa),
    )


def _tabela_apuracao(deck: Deck, slide, pendentes: pd.DataFrame, data_dir: Path) -> None:
    """A lista de quem não reportou, fora da área projetada.

    A última coluna carrega, além do caso, o que a varredura dos documentos do
    próprio fundo encontrou — e o que não encontrou.
    """

    diagnosticos = load_apuracao(data_dir).set_index("cnpj")

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
            _caso_com_apuracao(linha, diagnosticos),
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


def _caso_com_apuracao(linha, diagnosticos: pd.DataFrame) -> str:
    caso = str(linha.caso).replace(" — apurar", "")
    if linha.cnpj not in diagnosticos.index:
        return caso
    registro = diagnosticos.loc[linha.cnpj]
    partes = [caso, str(registro.get("diagnostico", "") or "")]
    falta = str(registro.get("lacunas", "") or "")
    if falta:
        partes.append(f"falta: {falta}")
    return " · ".join(p for p in partes if p)


def _caixa_de_pagina(slide):
    """A caixinha do número de página, achada pela geometria do rodapé."""

    for forma in slide.shapes:
        if not forma.has_text_frame:
            continue
        texto = forma.text_frame.text.strip()
        if (
            texto.isdigit()
            and forma.top > Inches(6.8)
            and abs(forma.left - Inches(PAGINA_X_IN)) < Inches(0.3)
        ):
            return forma, int(texto)
    return None, None


def _mover_para(presentation, depois_do_slide: int) -> None:
    """Leva a última lâmina para logo depois de ``depois_do_slide`` (1-based).

    A lâmina é **acrescentada** e só então reposicionada, porque o
    ``next_partname`` do python-pptx devolve nomes de parte já ocupados quando a
    numeração deixa de ser contígua — inserir no meio abriria esse buraco.  Aqui
    o que muda é apenas a ordem dos ``sldId`` no XML: as partes ficam onde estão,
    e o pacote continua íntegro.

    Depois da mudança de ordem, os números de página de tudo que vem adiante
    andam um.  Eles não são campos do PowerPoint, e sim caixas de texto escritas
    na montagem, então quem insere no meio tem de corrigi-los.
    """

    ids = presentation.slides._sldIdLst
    elementos = list(ids)
    if len(elementos) <= depois_do_slide:
        return
    ids.remove(elementos[-1])
    ids.insert(depois_do_slide, elementos[-1])

    # O número da lâmina anterior manda; a numeração publicada não é igual à
    # posição (há lâminas sem número), então o que se preserva é a sequência.
    _, anterior = _caixa_de_pagina(presentation.slides[depois_do_slide - 1])
    for posicao, slide in enumerate(presentation.slides):
        if posicao < depois_do_slide:
            continue
        caixa, numero = _caixa_de_pagina(slide)
        if caixa is None:
            continue
        if posicao == depois_do_slide:
            novo = (anterior or depois_do_slide) + 1
        else:
            novo = numero + 1
        caixa.text_frame.paragraphs[0].runs[0].text = str(novo)


def append_stress_slide(presentation, data_dir: Path):
    """Acrescenta a lâmina do teste de estresse ao fim e a reposiciona."""

    dados = estressar(_dados(data_dir))
    mesa = pauta(dados)
    numeros = resumo(dados)
    pendentes = nao_reportantes(dados)
    if mesa.empty:
        return presentation

    deck = Deck(KICKER, presentation)
    slide = deck.slide(
        f"{numeros['decidir']} FIDCs concentram R$ "
        f"{_brl_mm(numeros['aporte_decidir_brl'])} mm de aporte"
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

    # O racional em uma linha, e só ele.
    deck.text(
        slide,
        "Δ = Inadimplência − PDD (o que falta provisionar). Reconhecido, sai da "
        "subordinada e do total de cotas: Sub pós = (Sub − Δ) ÷ (Total − Δ).",
        MARGIN_IN,
        CHART_TOP_IN + CHART_HEIGHT_IN + 0.06,
        CONTENT_WIDTH_IN,
        0.22,
        size=9,
        color=GRAY_900,
    )

    _tabela_pauta(deck, slide, mesa)

    # Por que os outros saíram — o descarte fica explícito, não invisível.
    motivos = "; ".join(
        f"{quantos} {motivo}" for motivo, quantos in numeros["motivos_descarte"].items()
    )
    altura_tabela = 0.24 + 0.205 * len(mesa)
    deck.text(
        slide,
        f"Fora da pauta, {numeros['descartar']} dos {numeros['universo']} da "
        f"carteira — {motivos}.",
        MARGIN_IN,
        TABLE_TOP_IN + altura_tabela + 0.10,
        CONTENT_WIDTH_IN,
        0.22,
        size=8,
        color=GRAY_700,
    )

    _tabela_apuracao(deck, slide, pendentes, data_dir)
    deck.footer(
        slide,
        "CVM, Informe Mensal FIDC — Tabela I (competência mais recente de cada fundo) "
        "e regulamentos na FundosNet/B3. A carteira reportada já é líquida de PDD; a "
        "provisão é tratada como integralmente alocada aos créditos inadimplentes.",
    )
    _mover_para(presentation, ULTIMO_SLIDE_ESTRUTURAL)
    return presentation


__all__ = ["append_stress_slide"]
