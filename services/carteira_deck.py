"""Os slides de subordinação da carteira, e a troca deles no deck padrão.

O deck padrão é um binário publicado: ele chega pronto do bundle e é validado
contra um manifesto.  Editá-lo na origem exigiria republicar o bundle inteiro,
então a substituição acontece no caminho de exportação — sobre a apresentação
já carregada em memória, do mesmo modo que o ranking ANBIMA é acoplado.  O
bundle no disco permanece intacto e continua validando.

Os seis slides antigos (um por categoria de risco estrutural) são **reescritos
no lugar**, e não removidos e recriados.  A diferença não é estética: o
``next_partname`` do python-pptx devolve nomes já ocupados quando a numeração
das partes deixa de ser contígua, e remover slides do meio do deck é
exatamente o que abre esse buraco — o pacote sairia com duas partes
``ppt/slides/slideN.xml``.  Reescrevendo, nenhuma parte nasce ou morre, e os
slides do ranking podem ser acrescentados depois com segurança.

No lugar deles entra um slide consolidado mais um por categoria estrutural —
a mesma taxonomia que dava nome aos slides originais: Financeiro, Adquirência,
Agro / Revenda, Risco Corporativo, Consignado INSS e FGTS, Factoring.  Cada um
traz o gráfico de hastes: subordinação atual contra o mínimo que o regulamento
exige.  São sete gráficos para seis slots, e o excedente é acrescentado.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

from services.carteira_subordinacao import (
    DEFAULT_DATA_DIR,
    dumbbell_figure,
    figure_png_bytes,
    resolve_portfolio,
)


#: Faixa de slides que a carteira substitui, 1-indexada e inclusiva — é a
#: sequência "RISCO ESTRUTURAL · CARTEIRA I · <categoria>" do deck publicado.
REPLACED_SLIDE_RANGE = (18, 23)
#: Abaixo disso um gráfico de hastes não comunica nada: vira um punhado de
#: pontos soltos.  A categoria continua representada no slide consolidado.
MIN_FUNDS_PER_CATEGORY = 3

KICKER = "RISCO ESTRUTURAL · CARTEIRA 101"
FOOTNOTE = (
    "*Cotas subordinadas / PL no Informe Mensal mais recente de cada fundo. "
    "†Mínimo estrutural (subordinada + mezanino) quando o regulamento o define; "
    "mínimo júnior nos demais."
)
SOURCE = (
    "Fontes: CVM, Informe Mensal FIDC (competência mais recente de cada fundo); "
    "regulamentos na FundosNet/B3. Mínimos conforme curadoria documental."
)


def slot_count() -> int:
    first, last = REPLACED_SLIDE_RANGE
    return last - first + 1


def clear_slide(slide) -> None:
    """Esvazia um slide, preservando a parte e a posição dele no deck."""

    tree = slide.shapes._spTree
    for shape in list(slide.shapes):
        tree.remove(shape._element)


def _competence_label(competencia: str) -> str:
    return (
        f"{competencia[5:]}/{competencia[2:4]}"
        if len(competencia) == 7 and competencia[4] == "-"
        else competencia
    )


def slide_plans(
    data_dir: Path = DEFAULT_DATA_DIR, *, limite: int | None = None
) -> list[tuple[str, str, pd.DataFrame]]:
    """Os slides a desenhar: o consolidado e depois cada categoria estrutural."""

    position = resolve_portfolio(data_dir, somente_ativos=True)
    comparable = position.frame[position.frame["comparavel"]]
    rotulo = _competence_label(position.competencia_base)

    plans: list[tuple[str, str, pd.DataFrame]] = [
        (
            "Carteira 101 | subordinação atual contra o mínimo do regulamento",
            f"Carteira 101 · FIDCs ativos · base até {rotulo} · % do patrimônio líquido",
            comparable,
        )
    ]
    # O corte é o dos slides estruturais originais — Financeiro, Adquirência,
    # Agro / Revenda, Risco Corporativo, Consignado INSS e FGTS, Factoring —
    # ordenado pelo tamanho, para que os slots existentes fiquem com as
    # categorias que mais pesam.
    counts = comparable["categoria_estrutural"].value_counts()
    for categoria in counts[counts.ge(MIN_FUNDS_PER_CATEGORY)].index:
        subset = comparable[comparable["categoria_estrutural"].eq(categoria)]
        breaches = int(subset["abaixo_do_minimo"].fillna(False).sum())
        titulo = (
            f"{categoria} | {breaches} de {len(subset)} veículos abaixo do mínimo"
            if breaches
            else f"{categoria} | os {len(subset)} veículos estão acima do mínimo"
        )
        plans.append(
            (
                titulo,
                f"{categoria} · FIDCs ativos · base até {rotulo} · % do patrimônio líquido",
                subset,
            )
        )
    return plans if limite is None else plans[:limite]


def draw_carteira_slide(deck, slide, titulo: str, subtitulo: str, frame: pd.DataFrame) -> None:
    """Desenha um slide da carteira sobre um slide já existente e vazio."""

    from pptx.util import Inches

    deck.compose(slide, titulo, KICKER)
    figure = dumbbell_figure(
        frame, subtitulo=subtitulo, rodape=FOOTNOTE, fonte="", figsize=(12.1, 5.1)
    )
    slide.shapes.add_picture(
        BytesIO(figure_png_bytes(figure)), Inches(0.62), Inches(1.30), width=Inches(12.1)
    )
    deck.footer(slide, SOURCE)


def replace_structural_slides(
    presentation, data_dir: Path = DEFAULT_DATA_DIR
) -> int:
    """Reescreve os slides estruturais com os da carteira e devolve quantos.

    Os seis slots existentes são reescritos no lugar.  Havendo mais gráficos do
    que slots — o consolidado mais as seis categorias estruturais dão sete —, o
    excedente **nasce no fim do deck e é movido** para depois dos slots.
    Acrescentar é seguro; remover é que abriria buraco na numeração das partes.

    Sobrando slot, ele recebe o consolidado restrito a quem está abaixo do
    mínimo: o recorte que um leitor procuraria em seguida, sem inventar dado.
    """

    from services.bba_deck import Deck

    first, _ = REPLACED_SLIDE_RANGE
    slots = slot_count()
    plans = slide_plans(data_dir)
    if not plans:
        return 0
    while len(plans) < slots:
        titulo, subtitulo, frame = plans[0]
        breached = frame[frame["abaixo_do_minimo"].fillna(False)]
        plans.append(
            (
                f"Abaixo do mínimo | {len(breached)} veículos",
                subtitulo.replace("Carteira 101", "Carteira 101 · abaixo do mínimo"),
                breached,
            )
        )

    deck = Deck(KICKER, presentation)
    if len(presentation.slides) < first - 1 + slots:
        raise IndexError(
            f"O deck tem {len(presentation.slides)} slides; a carteira precisa "
            f"dos slots {first}–{first + slots - 1}. O deck publicado mudou de "
            "tamanho."
        )

    extras = len(plans) - slots
    if extras > 0:
        total = len(presentation.slides)
        for _ in range(extras):
            deck.blank()
        move_slides(presentation, total + 1, extras, first + slots)

    deck.page = first - 1
    slides = list(presentation.slides)
    for offset, (titulo, subtitulo, frame) in enumerate(plans):
        slide = slides[first - 1 + offset]
        clear_slide(slide)
        draw_carteira_slide(deck, slide, titulo, subtitulo, frame)
    return len(plans)


def move_slides(presentation, first: int, count: int, destination: int) -> None:
    """Move ``count`` slides a partir de ``first`` para a posição ``destination``.

    Índices 1-indexados, medidos na lista antes do movimento.  Mexe apenas na
    ordem declarada em ``sldIdLst``: nenhuma parte é criada ou destruída, então
    a numeração do pacote fica intacta.
    """

    id_list = presentation.slides._sldIdLst
    entries = list(id_list)
    moving = entries[first - 1 : first - 1 + count]
    for entry in moving:
        id_list.remove(entry)
    for offset, entry in enumerate(moving):
        id_list.insert(destination - 1 + offset, entry)


__all__ = [
    "KICKER",
    "MIN_FUNDS_PER_CATEGORY",
    "REPLACED_SLIDE_RANGE",
    "clear_slide",
    "draw_carteira_slide",
    "move_slides",
    "replace_structural_slides",
    "slide_plans",
    "slot_count",
]
