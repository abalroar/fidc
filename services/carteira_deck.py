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

No lugar deles entra um slide consolidado mais um por tipo ANBIMA com fundos
suficientes, cada um com o gráfico de hastes: subordinação atual contra o
mínimo que o regulamento exige.
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
#: pontos soltos.  O tipo continua representado no slide consolidado.
MIN_FUNDS_PER_TYPE = 6

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
    """Os slides a desenhar: o consolidado e depois os maiores tipos ANBIMA."""

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
    counts = comparable["tipo_anbima"].value_counts()
    for tipo in counts[counts.ge(MIN_FUNDS_PER_TYPE)].index:
        subset = comparable[comparable["tipo_anbima"].eq(tipo)]
        breaches = int(subset["abaixo_do_minimo"].fillna(False).sum())
        titulo = (
            f"{tipo} | {breaches} de {len(subset)} veículos abaixo do mínimo"
            if breaches
            else f"{tipo} | os {len(subset)} veículos estão acima do mínimo"
        )
        plans.append(
            (
                titulo,
                f"{tipo} · FIDCs ativos · base até {rotulo} · % do patrimônio líquido",
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

    Se houver menos gráficos do que slots, os slots restantes recebem o
    consolidado filtrado pelos fundos abaixo do mínimo — nenhum slide é
    removido, porque remover é o que quebra a numeração das partes.
    """

    from services.bba_deck import Deck

    first, _ = REPLACED_SLIDE_RANGE
    slots = slot_count()
    plans = slide_plans(data_dir, limite=slots)
    if not plans:
        return 0
    while len(plans) < slots:
        # Sem tipos suficientes para preencher, o slot extra repete o
        # consolidado restrito a quem está abaixo do mínimo: é o recorte que
        # um leitor procuraria em seguida, e não inventa dado nenhum.
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
    slides = list(presentation.slides)
    if len(slides) < first - 1 + len(plans):
        raise IndexError(
            f"O deck tem {len(slides)} slides; a carteira precisa dos slots "
            f"{first}–{first + len(plans) - 1}. O deck publicado mudou de tamanho."
        )
    deck.page = first - 1
    for offset, (titulo, subtitulo, frame) in enumerate(plans):
        slide = slides[first - 1 + offset]
        clear_slide(slide)
        draw_carteira_slide(deck, slide, titulo, subtitulo, frame)
    return len(plans)


__all__ = [
    "KICKER",
    "MIN_FUNDS_PER_TYPE",
    "REPLACED_SLIDE_RANGE",
    "clear_slide",
    "draw_carteira_slide",
    "replace_structural_slides",
    "slide_plans",
    "slot_count",
]
