"""Executive package on the ANBIMA June/2026 fixed-income and hybrid ranking.

Builds two deliverables from the two official workbooks and nothing else:

* an XLSX working file with every table — league tables for origination and
  distribution in both windows, the per-product view, the full operation
  participation matrix and the largest operations of the period; and
* a PPTX executive presentation for the Itaú BBA president.

    python scripts/build_anbima_executive_package.py \
        --ranking-xlsx <ranking.xlsx> --annex-xlsx <anexo.xlsx>
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_TICK_MARK
from openpyxl.styles import Font
from pptx.util import Inches, Pt


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.anbima_fixed_income_ranking import (  # noqa: E402
    parse_annex_workbook,
    parse_ranking_totals,
    parse_ranking_workbook,
    workbook_sha256,
)
from services.anbima_executive_package import (  # noqa: E402
    HOUSE,
    SEGMENT_CRITERIA,
    display_name,
    MEASURES,
    PEERS,
    WINDOWS,
    largest_operations,
    league_table,
    operation_matrix,
    peer_chart_frame,
    product_view,
)
from services.bba_deck import (  # noqa: E402
    BLACK,
    CONTENT_WIDTH_IN,
    Deck,
    FONT,
    GRAY_100,
    GRAY_300,
    GRAY_500,
    GRAY_700,
    GRAY_900,
    HOUSE_BLUE,
    MARGIN_IN,
    NEUTRAL,
    ORANGE,
    WHITE,
    fmt_mm,
    fmt_pct,
    fmt_pp,
    fmt_rank,
)

DEFAULT_OUTPUT_DIR = Path("outputs/anbima_executivo_1s26")
KICKER = "RANKING ANBIMA · JUNHO/2026"

SOURCE_RANKING = (
    "Fonte: ANBIMA, Ranking de Renda Fixa e Híbridos — Junho/2026"
)
SOURCE_ANNEX = (
    "Fonte: ANBIMA, Anexo ao Ranking — Tabela de Encerramento, Junho/2026"
)
SOURCE_ANNEX_SHORT = "Anexo ao Ranking — Tabela de Encerramento, Junho/2026"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ranking-xlsx", type=Path, required=True)
    parser.add_argument("--annex-xlsx", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


# --------------------------------------------------------------------------- #
# Narrative
# --------------------------------------------------------------------------- #
def executive_messages(official: pd.DataFrame, matrix: pd.DataFrame) -> list[str]:
    """Committee-language findings, with every number read from the source."""

    def cell(measure: str, window: str, code: str = "1") -> tuple:
        table = league_table(official, measure=measure, window=window, ranking_code=code)
        if table.empty:
            return (None, None, None, None)
        house = table[table["participante"].eq(HOUSE)]
        if house.empty:
            return (None, None, table.iloc[0]["instituicao"], table.iloc[0]["market_share"])
        row = house.iloc[0]
        return (
            int(row["posicao"]),
            float(row["market_share"]),
            table.iloc[0]["instituicao"],
            float(table.iloc[0]["market_share"]),
        )

    o_ytd = cell("originacao_valor", "acumulado_ano")
    o_12m = cell("originacao_valor", "ultimos_12_meses")
    d_ytd = cell("distribuicao_valor", "acumulado_ano")
    d_12m = cell("distribuicao_valor", "ultimos_12_meses")
    sec = cell("originacao_valor", "acumulado_ano", "1.3")
    fidc = cell("originacao_valor", "acumulado_ano", "1.3.1")
    hyb = cell("originacao_valor", "acumulado_ano", "2")
    infra = cell("originacao_valor", "acumulado_ano", "2.4")
    cra = cell("originacao_valor", "acumulado_ano", "1.3.3")
    curto = cell("originacao_valor", "acumulado_ano", "1.1")

    house_ops = matrix[matrix["itau_participa"].eq("Sim")]
    led = house_ops[house_ops[HOUSE].eq("Líder")]

    return [
        "Na distribuição de renda fixa — o esforço efetivo de colocação junto ao "
        f"investidor — o Itaú BBA é líder nas duas janelas: {fmt_pct(d_ytd[1])} no "
        f"acumulado de 2026 e {fmt_pct(d_12m[1])} nos últimos 12 meses.",

        "Na originação de renda fixa o banco é "
        f"{fmt_rank(o_12m[0])} nos últimos 12 meses, com {fmt_pct(o_12m[1])}, e "
        f"{fmt_rank(o_ytd[0])} no acumulado de 2026, com {fmt_pct(o_ytd[1])}. "
        "A troca de posição no semestre não se reproduz na janela de doze meses.",

        f"A desvantagem para o líder no acumulado de 2026 é de {fmt_mm(abs((o_ytd[3] - o_ytd[1]) * 100))} p.p. "
        f"({o_ytd[2]}, {fmt_pct(o_ytd[3])}), enquanto a vantagem sobre o 3º colocado "
        "supera 12 p.p. — o bloco de liderança segue restrito a duas casas.",

        "Em securitização o Itaú BBA lidera a originação com "
        f"{fmt_pct(sec[1])}, puxado por FIDC, onde a participação é de {fmt_pct(fidc[1])} — "
        "mais que o dobro do segundo colocado.",

        "Em operações híbridas o banco também lidera a originação, com "
        f"{fmt_pct(hyb[1])}, incluindo {fmt_pct(infra[1])} em FI-Infra (FIP-IE).",

        f"O Itaú BBA participou de {len(house_ops)} das {len(matrix)} operações encerradas no "
        f"período e foi o maior coordenador em {len(led)} delas, o que sustenta a posição "
        "por presença recorrente, não por concentração em poucas transações.",

        "Pontos de atenção específicos, e não sistêmicos: CRA na originação "
        f"({fmt_rank(cra[0])}, {fmt_pct(cra[1])}) e renda fixa de curto prazo "
        f"({fmt_rank(curto[0])}, {fmt_pct(curto[1])}), ambos segmentos de menor peso no "
        "consolidado e com espaço claro de recuperação.",
    ]


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def add_share_chart(
    deck: Deck,
    slide,
    frame: pd.DataFrame,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
) -> None:
    """Horizontal bars, house in dark blue, peers neutral, labels on the marks."""

    deck.text(slide, title, x, y, w, 0.26, size=11, color=GRAY_700, bold=True)
    plot_top = y + 0.34

    # PowerPoint plots the first category at the bottom of a bar chart, so the
    # ranking is reversed to read top-down.
    ordered = frame.iloc[::-1]
    categories = [
        f"{int(row.posicao)}º  {row.instituicao}" for row in ordered.itertuples()
    ]
    values = [float(row.market_share) for row in ordered.itertuples()]

    data = CategoryChartData()
    data.categories = categories
    data.add_series("Market share", values)

    graphic = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_CLUSTERED,
        Inches(x),
        Inches(plot_top),
        Inches(w),
        Inches(h - 0.34),
        data,
    )
    chart = graphic.chart
    chart.has_title = False
    chart.has_legend = False  # one series; the slide title names it

    plot = chart.plots[0]
    plot.gap_width = 60
    plot.vary_by_categories = False
    series = plot.series[0]
    for index, point in enumerate(series.points):
        participant = ordered.iloc[index]["participante"]
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = deck.rgb(
            HOUSE_BLUE if participant == HOUSE else NEUTRAL
        )
        point.format.line.fill.background()

    plot.has_data_labels = True
    labels = plot.data_labels
    labels.number_format = "0.0%"
    labels.number_format_is_linked = False
    labels.position = XL_LABEL_POSITION.OUTSIDE_END
    labels.font.size = Pt(10)
    labels.font.name = FONT
    labels.font.bold = True
    labels.font.color.rgb = deck.rgb(GRAY_900)

    category_axis = chart.category_axis
    category_axis.has_major_gridlines = False
    category_axis.major_tick_mark = XL_TICK_MARK.NONE
    category_axis.format.line.color.rgb = deck.rgb(GRAY_300)
    category_axis.tick_labels.font.size = Pt(10)
    category_axis.tick_labels.font.name = FONT
    category_axis.tick_labels.font.color.rgb = deck.rgb(GRAY_900)

    value_axis = chart.value_axis
    value_axis.has_major_gridlines = False
    value_axis.visible = False
    value_axis.maximum_scale = max(values) * 1.28
    value_axis.minimum_scale = 0.0


# --------------------------------------------------------------------------- #
# Slides
# --------------------------------------------------------------------------- #
def _league_rows(table: pd.DataFrame, limit: int = 8) -> tuple[list[list[str]], int | None]:
    rows = [["#", "Instituição", "Volume (R$ mi)", "Share", "vs. líder", "vs. Itaú"]]
    highlight = None
    for position, row in enumerate(table.head(limit).itertuples()):
        if row.participante == HOUSE:
            highlight = position
        rows.append(
            [
                fmt_rank(row.posicao),
                row.instituicao,
                fmt_mm(row.volume_brl_mm),
                fmt_pct(row.market_share),
                fmt_pp(row.gap_lider_pp),
                fmt_pp(row.gap_itau_pp),
            ]
        )
    return rows, highlight


def ranking_slide(deck: Deck, official: pd.DataFrame, measure: str) -> None:
    label = MEASURES[measure]
    ytd = league_table(official, measure=measure, window="acumulado_ano")
    m12 = league_table(official, measure=measure, window="ultimos_12_meses")
    house_ytd = ytd[ytd["participante"].eq(HOUSE)].iloc[0]
    house_12m = m12[m12["participante"].eq(HOUSE)].iloc[0]

    if int(house_ytd["posicao"]) == int(house_12m["posicao"]):
        headline = (
            f"{label} de renda fixa: Itaú BBA em {fmt_rank(house_ytd['posicao'])} "
            "nas duas janelas"
        )
    else:
        headline = (
            f"{label} de renda fixa: {fmt_rank(house_ytd['posicao'])} no acumulado de 2026 "
            f"e {fmt_rank(house_12m['posicao'])} nos últimos 12 meses"
        )
    slide = deck.slide(headline)

    deck.stat_cards(
        slide,
        [
            (
                f"Volume {label.lower()}",
                f"R$ {fmt_mm(float(house_ytd['volume_brl_mm']) / 1e3)} bi",
                "acumulado 2026",
            ),
            ("Participação", fmt_pct(float(house_ytd["market_share"])), "do mercado apurado"),
            (
                "Posição 2026",
                fmt_rank(house_ytd["posicao"]),
                f"entre {len(ytd)} instituições",
            ),
            (
                "Posição 12 meses",
                fmt_rank(house_12m["posicao"]),
                fmt_pct(float(house_12m["market_share"])) + " de participação",
            ),
        ],
        y=1.4,
    )

    for column, (table, window) in enumerate(
        ((ytd, "acumulado_ano"), (m12, "ultimos_12_meses"))
    ):
        x = MARGIN_IN + column * 6.15
        deck.text(slide, WINDOWS[window], x, 2.78, 5.7, 0.26, size=11, color=ORANGE, bold=True)
        rows, highlight = _league_rows(table)
        deck.native_table(
            slide,
            rows,
            x,
            3.12,
            [0.5, 1.9, 1.3, 0.82, 0.78, 0.6],
            highlight=highlight,
            aligns="llrrrr",
            size=10,
        )
    deck.footer(
        slide,
        f"{SOURCE_RANKING} — {label} (Valor), Tipo 1: Renda Fixa Consolidado · "
        "diferenças em pontos percentuais de market share",
    )


def chart_slide(deck: Deck, official: pd.DataFrame, measure: str) -> None:
    label = MEASURES[measure]
    slide = deck.slide(f"{label} — market share das seis principais casas")
    for column, window in enumerate(("acumulado_ano", "ultimos_12_meses")):
        frame = peer_chart_frame(official, measure=measure, window=window)
        add_share_chart(
            deck,
            slide,
            frame,
            x=MARGIN_IN + column * 6.15,
            y=1.42,
            w=5.7,
            h=4.9,
            title=WINDOWS[window],
        )
    deck.text(
        slide,
        "Itaú BBA em azul; demais casas em cinza. Percentuais referem-se ao total do "
        "ranking Tipo 1, que soma 100% em cada janela.",
        MARGIN_IN,
        6.52,
        CONTENT_WIDTH_IN,
        0.3,
        size=10,
        color=GRAY_500,
    )
    deck.footer(slide, f"{SOURCE_RANKING} — {label} (Valor), Tipo 1: Renda Fixa Consolidado")


def product_slide(deck: Deck, products: pd.DataFrame) -> None:
    slide = deck.slide("Visão por produto: mercado, posição e participação do Itaú BBA")
    view = products[products["visao"].eq("Originação")]

    rows = [
        [
            "Segmento",
            "Operações (#)",
            "Mercado (R$ bi)",
            "Rank 1S26",
            "Share 1S26",
            "Rank 12m",
            "Share 12m",
        ]
    ]
    for row in view.itertuples():
        label = row.segmento + ("*" if row.nota_criterio else "")
        rows.append(
            [
                label,
                fmt_mm(row.operacoes_1s26, 0),
                fmt_mm(row.volume_1s26_brl / 1e9),
                fmt_rank(row.ranking_1s26),
                fmt_pct(row.share_1s26) if row.share_1s26 is not None else "—",
                fmt_rank(row.ranking_12m),
                fmt_pct(row.share_12m) if row.share_12m is not None else "—",
            ]
        )
    deck.native_table(
        slide,
        rows,
        MARGIN_IN,
        1.42,
        [3.15, 1.45, 1.65, 1.35, 1.4, 1.35, 1.4],
        aligns="lrrrrrr",
        size=10,
        row_height=0.29,
    )

    note_top = 1.42 + 0.32 + len(view) * 0.29 + 0.22
    deck.text(
        slide,
        "* Composição dos agregados",
        MARGIN_IN,
        note_top,
        CONTENT_WIDTH_IN,
        0.24,
        size=10,
        color=ORANGE,
        bold=True,
    )
    deck.text(
        slide,
        " ".join(SEGMENT_CRITERIA),
        MARGIN_IN,
        note_top + 0.26,
        CONTENT_WIDTH_IN,
        0.8,
        size=9,
        color=GRAY_700,
    )
    deck.footer(
        slide,
        f"{SOURCE_RANKING} — Originação (Valor e Nº de Operações), acumulado 2026 e "
        "últimos 12 meses · operações do total publicado por tipo",
    )


def fidc_slide(deck: Deck, official: pd.DataFrame, totals: pd.DataFrame) -> None:
    fidc = league_table(
        official, measure="originacao_valor", window="acumulado_ano", ranking_code="1.3.1"
    )
    if fidc.empty:
        return
    counts = official[
        official["measure"].eq("originacao_numero_operacoes")
        & official["window"].eq("acumulado_ano")
        & official["ranking_code"].eq("1.3.1")
    ].set_index("participant")["value_brl_or_count"]
    distribution = league_table(
        official, measure="distribuicao_valor", window="acumulado_ano", ranking_code="1.3.1"
    )
    total_ops = totals[
        totals["measure"].eq("originacao_numero_operacoes")
        & totals["window"].eq("acumulado_ano")
        & totals["ranking_code"].eq("1.3.1")
    ]
    operations = int(total_ops["total"].iloc[0]) if not total_ops.empty else 0

    house = fidc[fidc["participante"].eq(HOUSE)].iloc[0]
    house_ops = int(counts.get(HOUSE, 0))
    universe = float(fidc["volume_brl_mm"].sum())

    slide = deck.slide(
        "Em FIDC o Itaú BBA lidera com "
        f"{fmt_pct(float(house['market_share']))}, mais que o dobro do segundo colocado"
    )
    deck.stat_cards(
        slide,
        [
            ("Volume originado", f"R$ {fmt_mm(float(house['volume_brl_mm']) / 1e3)} bi", "1S26"),
            ("Participação", fmt_pct(float(house["market_share"])), "do mercado apurado"),
            ("Posição", fmt_rank(house["posicao"]), f"entre {len(fidc)} coordenadores"),
            ("Operações", f"{house_ops} de {operations}", "originadas no semestre"),
        ],
        y=1.4,
    )

    rows = [["#", "Coordenador", "Volume (R$ mi)", "Share", "Operações (#)"]]
    highlight = None
    for position, row in enumerate(fidc.head(9).itertuples()):
        if row.participante == HOUSE:
            highlight = position
        rows.append(
            [
                fmt_rank(row.posicao),
                row.instituicao,
                fmt_mm(row.volume_brl_mm),
                fmt_pct(row.market_share),
                fmt_mm(float(counts.get(row.participante, 0)), 0),
            ]
        )
    bottom = deck.native_table(
        slide,
        rows,
        MARGIN_IN,
        2.78,
        [0.7, 5.35, 2.2, 1.7, 2.1],
        highlight=highlight,
        aligns="llrrr",
        size=10,
    )

    house_distribution = distribution[distribution["participante"].eq(HOUSE)]
    share_text = (
        fmt_pct(float(house_distribution["market_share"].iloc[0]))
        if not house_distribution.empty
        else "—"
    )
    deck.text(
        slide,
        f"Na distribuição de FIDC o Itaú BBA também é 1º, com {share_text}. O mercado "
        f"apurado no ranking é de R$ {fmt_mm(universe / 1e3)} bi, contra R$ 65,5 bi de cotas "
        "de FIDC registradas na CVM no mesmo período: o ranking cobre a parcela disputada, "
        "sem as operações de empresas ligadas e sem as ofertas não reportadas à ANBIMA.",
        MARGIN_IN,
        bottom + 0.26,
        CONTENT_WIDTH_IN,
        0.62,
        size=11,
        color=GRAY_700,
    )
    deck.footer(
        slide,
        f"{SOURCE_RANKING} — Originação e Distribuição (Valor), Tipo 1.3.1 · "
        "CVM, ofertas públicas de distribuição",
    )


def operations_slide(deck: Deck, matrix: pd.DataFrame) -> None:
    top = largest_operations(matrix, 12)
    slide = deck.slide("As maiores operações do período e a presença do Itaú BBA")
    rows = [["Operação", "Instrumento", "Data", "R$ mi", "Líder(es)", "Itaú BBA"]]
    for row in top.itertuples():
        name = row.operacao
        if len(name) > 44:
            name = name[:43].rstrip() + "…"
        rows.append(
            [
                name,
                row.instrumento,
                row.data_encerramento.strftime("%d/%m/%y"),
                fmt_mm(row.valor_total_brl_mm),
                row.lideres if len(row.lideres) <= 28 else row.lideres[:27] + "…",
                row.participacao_itau,
            ]
        )
    bottom = deck.native_table(
        slide,
        rows,
        MARGIN_IN,
        1.42,
        [4.3, 1.55, 0.95, 1.2, 2.7, 1.35],
        aligns="llrrlr",
        size=10,
        row_height=0.3,
    )
    participated = int((top["itau_participa"] == "Sim").sum())
    deck.text(
        slide,
        f"O Itaú BBA participou de {participated} das 12 maiores operações do período. "
        "A lista das 20 maiores e a matriz completa de participação, operação a operação, "
        "estão no arquivo Excel.",
        MARGIN_IN,
        bottom + 0.24,
        CONTENT_WIDTH_IN,
        0.36,
        size=10,
        color=GRAY_500,
    )
    deck.footer(slide, f"{SOURCE_ANNEX} — originação, ordenado por valor total da operação")


def methodology_slide(deck: Deck) -> None:
    slide = deck.slide("Como interpretar o ranking ANBIMA")
    items = (
        (
            "Originação × Distribuição",
            "Originação mede a estruturação e a coordenação da oferta. Distribuição mede "
            "o esforço de colocação junto ao investidor. Uma casa pode liderar um e não o outro.",
        ),
        (
            "O ranking mede valor",
            "A posição vem do volume das operações encerradas no período. Há um ranking "
            "separado por número de operações, em que cada coordenador recebe uma unidade.",
        ),
        (
            "As duas janelas",
            "“Acumulado 2026” cobre jan–jun/26. “Últimos 12 meses” cobre jul/25–jun/26 e "
            "suaviza o efeito de operações grandes concentradas em um trimestre.",
        ),
        (
            "Uma operação, vários coordenadores",
            "O crédito segue os percentuais informados à ANBIMA: proporção da garantia "
            "firme, ou proporção do fee em melhores esforços. Não é rateio igualitário.",
        ),
        (
            "O “Percentual Coordenado” define a liderança",
            "Na matriz de operações, “Líder” marca a casa com o maior percentual "
            "coordenado; “X” marca participação sem liderança; “–” marca ausência.",
        ),
        (
            "Participação formal sem valor",
            "Alguns registros trazem participantes com percentual e valor zerados. Eles "
            "constam como participantes, mas não elevam market share por valor.",
        ),
        (
            "É um ranking declaratório",
            "Operação cujo formulário-padrão não foi enviado à ANBIMA não entra. Parte do "
            "mercado liderado por administradores e DTVMs fica de fora.",
        ),
        (
            "Empresas ligadas saem do Tipo 1",
            "Coordenador com 10% ou mais do capital da emissora, cedente ou originadora "
            "vai para o Tipo 3, apurado à parte.",
        ),
    )
    cursor = 1.42
    for index, (title, body) in enumerate(items):
        column = index % 2
        if column == 0 and index:
            cursor += 1.36
        x = MARGIN_IN + column * 6.2
        deck.block(slide, x, cursor, 0.045, 1.02, ORANGE)
        deck.text(slide, title, x + 0.26, cursor, 5.5, 0.46, size=11.5, color=BLACK, bold=True)
        deck.text(slide, body, x + 0.26, cursor + 0.4, 5.5, 0.92, size=9.5, color=GRAY_700)
    deck.footer(
        slide,
        "Fonte: ANBIMA, Metodologia do Ranking de Renda Fixa e Híbridos, capítulos II a VII",
    )


def caveats_slide(
    deck: Deck,
    matrix: pd.DataFrame,
    sources: dict[str, str],
    consistency: dict[str, int],
) -> None:
    slide = deck.slide("Premissas, limitações e fontes")
    zero = int((matrix["sem_valor_economico"] == "Sim").sum())
    items = (
        (
            "Escopo",
            "Toda a análise vem exclusivamente das duas planilhas oficiais da ANBIMA de "
            "junho/2026. Nenhum dado externo foi acrescentado.",
        ),
        (
            "Chave de operação",
            "A matriz usa o registro CVM como chave. Séries da mesma emissão com registros "
            "distintos permanecem em linhas separadas.",
        ),
        (
            "Consistência verificada",
            "Os market shares somam 100,0% em cada ranking. Em "
            f"{consistency['exatos']} dos {consistency['registros']} registros o percentual "
            "coordenado soma exatamente 100%.",
        ),
        (
            "Registros sem valor econômico",
            f"{zero} operações têm valor total zero, com participantes formais e sem crédito "
            "de valor. Estão sinalizadas na matriz e não elevam market share.",
        ),
        (
            "Consolidação de entidades",
            "A ANBIMA consolida cada conglomerado sob um rótulo único e não segrega as "
            "entidades jurídicas do grupo.",
        ),
        (
            "Cobertura do ranking",
            "O ranking é declaratório e exclui operações de empresas ligadas do Tipo 1. "
            "Ele não equivale ao total emitido no mercado.",
        ),
    )
    cursor = 1.45
    for index, (title, body) in enumerate(items):
        column = index % 2
        if column == 0 and index:
            cursor += 1.5
        x = MARGIN_IN + column * 6.2
        deck.text(slide, title, x, cursor, 5.7, 0.28, size=11, color=ORANGE, bold=True)
        deck.text(slide, body, x, cursor + 0.3, 5.7, 0.95, size=10, color=GRAY_700)

    deck.text(
        slide,
        "Arquivos-fonte (SHA-256): "
        + " · ".join(f"{name} {digest[:12]}" for name, digest in sources.items()),
        MARGIN_IN,
        6.5,
        CONTENT_WIDTH_IN,
        0.3,
        size=9,
        color=GRAY_500,
    )
    deck.footer(slide, "ANBIMA Data — Ranking de Renda Fixa e Híbridos, referência Junho/2026")


def build_deck(
    official: pd.DataFrame,
    totals: pd.DataFrame,
    matrix: pd.DataFrame,
    products: pd.DataFrame,
    sources: dict[str, str],
    consistency: dict[str, int],
    output: Path,
) -> Path:
    """Assemble the single combined deck."""

    deck = Deck(KICKER)

    cover = deck.blank()
    deck.block(cover, 0.0, 0.0, 0.22, 7.5, ORANGE)
    deck.text(cover, KICKER, 0.92, 2.24, 8.0, 0.26, size=11, color=ORANGE, bold=True)
    deck.text(
        cover,
        "Posição competitiva do Itaú BBA em renda fixa e híbridos",
        0.92,
        2.68,
        11.4,
        0.8,
        size=30,
        color=BLACK,
        bold=True,
    )
    deck.text(
        cover,
        "Originação e distribuição · acumulado de 2026 e últimos 12 meses",
        0.92,
        3.56,
        11.4,
        0.34,
        size=14,
        color=GRAY_700,
    )
    deck.rule(cover, 0.92, 4.12, 3.2, color=GRAY_300, height=0.018)
    deck.text(
        cover,
        "Ranking ANBIMA de Renda Fixa e Híbridos — referência Junho/2026",
        0.92,
        4.36,
        11.4,
        0.3,
        size=11,
        color=GRAY_500,
    )
    deck.text(
        cover,
        "Análise Setorial de Crédito — Itaú BBA",
        0.92,
        6.62,
        6.0,
        0.28,
        size=10,
        color=GRAY_500,
    )

    slide = deck.slide("Sumário executivo")
    cursor = 1.42
    for message in executive_messages(official, matrix):
        deck.block(slide, MARGIN_IN, cursor + 0.05, 0.045, 0.5, ORANGE)
        deck.text(
            slide, message, MARGIN_IN + 0.28, cursor, 11.6, 0.72, size=12, color=GRAY_900
        )
        cursor += 0.76
    deck.footer(slide, f"{SOURCE_RANKING} · {SOURCE_ANNEX_SHORT}")

    ranking_slide(deck, official, "originacao_valor")
    chart_slide(deck, official, "originacao_valor")
    ranking_slide(deck, official, "distribuicao_valor")
    chart_slide(deck, official, "distribuicao_valor")
    product_slide(deck, products)
    fidc_slide(deck, official, totals)
    operations_slide(deck, matrix)
    methodology_slide(deck)
    caveats_slide(deck, matrix, sources, consistency)

    output.parent.mkdir(parents=True, exist_ok=True)
    deck.save(output)
    return output


# --------------------------------------------------------------------------- #
# Workbook
# --------------------------------------------------------------------------- #
def build_workbook(
    official: pd.DataFrame,
    matrix: pd.DataFrame,
    products: pd.DataFrame,
    output: Path,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    peers = list(PEERS)

    league_sheets: dict[str, pd.DataFrame] = {}
    for measure, measure_label in MEASURES.items():
        for window, window_label in WINDOWS.items():
            table = league_table(official, measure=measure, window=window)
            table = table.drop(columns=["participante"])
            table.columns = [
                "Posição",
                "Instituição",
                "Volume (R$ milhões)",
                "Market share",
                "Dif. para o líder (p.p.)",
                "Dif. vs. Itaú BBA (p.p.)",
            ]
            tag = "1S26" if window == "acumulado_ano" else "12m"
            league_sheets[f"{measure_label} {tag}"] = table

    product_sheet = products.copy()
    product_sheet["volume_1s26_brl"] = product_sheet["volume_1s26_brl"] / 1e9
    product_sheet["volume_12m_brl"] = product_sheet["volume_12m_brl"] / 1e9
    product_sheet = product_sheet.rename(
        columns={
            "segmento": "Segmento",
            "codigo_anbima": "Código ANBIMA",
            "nota_criterio": "Agregado com nota de critério",
            "visao": "Visão",
            "ranking_1s26": "Ranking 1S26",
            "share_1s26": "Market share 1S26",
            "ranking_12m": "Ranking 12 meses",
            "share_12m": "Market share 12 meses",
            "variacao_posicao": "Variação de posição",
            "concorrentes_1s26": "Concorrentes no segmento",
            "operacoes_1s26": "Operações 1S26 (#)",
            "operacoes_12m": "Operações 12 meses (#)",
            "volume_1s26_brl": "Mercado 1S26 (R$ bi)",
            "volume_12m_brl": "Mercado 12 meses (R$ bi)",
        }
    )

    matrix_sheet = matrix.copy()
    ordered_columns = (
        [
            "operacao",
            "registro_cvm",
            "instrumento",
            "classe_anbima",
            "classe_descricao",
            "bloco_anbima",
            "originador_risco",
            "regime_colocacao",
            "data_encerramento",
            "valor_total_brl_mil",
            "valor_total_brl_mm",
        ]
        + peers
        + [
            "participacao_itau_pct",
            "valor_itau_brl_mm",
            "itau_participa",
            "lideres",
            "demais_participantes",
            "participantes_completos",
            "n_participantes",
            "sem_valor_economico",
        ]
    )
    matrix_sheet = matrix_sheet[ordered_columns]
    matrix_sheet.columns = (
        [
            "Operação / emissão",
            "Registro CVM",
            "Instrumento",
            "Classe ANBIMA",
            "Descrição da classe",
            "Bloco ANBIMA",
            "Originador do risco (cedente)",
            "Regime de colocação",
            "Data de encerramento",
            "Valor total (R$ mil)",
            "Valor total (R$ milhões)",
        ]
        + [display_name(name) for name in peers]
        + [
            "Participação Itaú BBA (%)",
            "Valor Itaú BBA (R$ milhões)",
            "Itaú BBA participa",
            "Banco(s) líder(es)",
            "Demais participantes",
            "Participantes completos",
            "Nº de participantes",
            "Sem valor econômico",
        ]
    )

    top20 = largest_operations(matrix, 20)[
        [
            "operacao",
            "instrumento",
            "data_encerramento",
            "valor_total_brl_mm",
            "lideres",
            "participacao_itau",
            "participantes_completos",
        ]
    ]
    top20.columns = [
        "Operação",
        "Instrumento",
        "Data",
        "Valor total (R$ milhões)",
        "Banco(s) líder(es)",
        "Participação do Itaú BBA",
        "Participantes",
    ]

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, frame in league_sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
        product_sheet.to_excel(writer, sheet_name="Visão por produto", index=False)
        top20.to_excel(writer, sheet_name="Top 20 operações", index=False)
        matrix_sheet.to_excel(writer, sheet_name="Matriz de operações", index=False)
        matrix_sheet[matrix_sheet["Itaú BBA participa"].eq("Sim")].to_excel(
            writer, sheet_name="Matriz — só Itaú BBA", index=False
        )

        workbook = writer.book
        # Values stay numeric so the file remains analysable; only the display
        # format follows the one-decimal convention asked for.
        formats = {
            "Volume (R$ milhões)": "#,##0.0",
            "Valor total (R$ milhões)": "#,##0.0",
            "Valor total (R$ mil)": "#,##0.0",
            "Valor Itaú BBA (R$ milhões)": "#,##0.0",
            "Market share": "0.0%",
            "Market share 1S26": "0.0%",
            "Market share 12 meses": "0.0%",
            "Mercado 1S26 (R$ bi)": "#,##0.0",
            "Mercado 12 meses (R$ bi)": "#,##0.0",
            "Participação Itaú BBA (%)": "0.0%",
            "Dif. para o líder (p.p.)": "+0.0;-0.0;0.0",
            "Dif. vs. Itaú BBA (p.p.)": "+0.0;-0.0;0.0",
        }
        for sheet in workbook.worksheets:
            sheet.freeze_panes = "A2"
            headers = {
                str(cell.value): cell.column_letter for cell in sheet[1] if cell.value
            }
            for name, number_format in formats.items():
                letter = headers.get(name)
                if not letter:
                    continue
                for (cell,) in sheet[f"{letter}2:{letter}{sheet.max_row}"]:
                    cell.number_format = number_format
            for column_cells in sheet.columns:
                longest = max(
                    (len(str(cell.value)) for cell in column_cells[:200] if cell.value),
                    default=10,
                )
                letter = column_cells[0].column_letter
                sheet.column_dimensions[letter].width = min(max(longest + 2, 10), 52)
            for cell in sheet[1]:
                cell.font = Font(bold=True)
    return output


def main() -> None:
    args = parse_args()
    official = parse_ranking_workbook(args.ranking_xlsx)
    totals = parse_ranking_totals(args.ranking_xlsx)
    annex = parse_annex_workbook(args.annex_xlsx)

    matrix = operation_matrix(annex)
    products = product_view(official, totals)

    origination = annex[annex["role"].eq("originacao")]
    per_registration = origination.groupby("registro_cvm")["percentual_participacao"].sum()
    consistency = {
        "registros": int(len(per_registration)),
        "exatos": int((per_registration.round(4) == 1.0).sum()),
    }
    sources = {
        "Ranking": workbook_sha256(args.ranking_xlsx),
        "Anexo": workbook_sha256(args.annex_xlsx),
    }

    workbook_path = build_workbook(
        official, matrix, products, args.output_dir / "ANBIMA_Analise_Itau_BBA_1S26.xlsx"
    )
    deck_path = build_deck(
        official,
        totals,
        matrix,
        products,
        sources,
        consistency,
        args.output_dir / "ANBIMA_Itau_BBA_Renda_Fixa_1S26.pptx",
    )
    print(f"workbook: {workbook_path}")
    print(f"deck: {deck_path}")


if __name__ == "__main__":
    main()
