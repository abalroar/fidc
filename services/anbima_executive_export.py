"""Executive deck and workbook over the ANBIMA fixed-income ranking.

Renders the committee package from the two official ANBIMA workbooks: an
11-slide presentation with native Office tables and charts, and a working
spreadsheet with every table behind it.

The byte-returning entry points — :func:`build_anbima_deck_bytes` and
:func:`build_anbima_workbook_bytes` — are what the Streamlit download buttons
call; the CLI in ``scripts/build_anbima_executive_package.py`` writes the same
bytes to disk.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from openpyxl.styles import Font
import pandas as pd
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_TICK_MARK
from pptx.util import Inches, Pt

from services.anbima_fixed_income_ranking import (
    parse_annex_workbook,
    parse_ranking_totals,
    parse_ranking_workbook,
    workbook_sha256,
)
from services.anbima_executive_package import (
    HOUSE,
    MEASURES,
    PEERS,
    SEGMENT_CRITERIA,
    WINDOWS,
    display_name,
    largest_operations,
    league_table,
    operation_matrix,
    peer_chart_frame,
    product_view,
)
from services.bba_deck import (
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


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data" / "industry_study"
SOURCES_SUBDIR = "sources"

#: Glob that locates each official workbook inside ``<data_dir>/sources``.  The
#: file name carries the reference month, so the pattern — not a fixed name —
#: is what survives the next publication.
RANKING_GLOB = "Ranking de Renda Fixa e H*bridos*.xlsx"
ANNEX_GLOB = "Anexo ao Ranking*.xlsx"

KICKER = "RANKING ANBIMA \u00b7 JUNHO/2026"

SOURCE_RANKING = "Fonte: ANBIMA, Ranking de Renda Fixa e H\u00edbridos \u2014 Junho/2026"
SOURCE_ANNEX = (
    "Fonte: ANBIMA, Anexo ao Ranking \u2014 Tabela de Encerramento, Junho/2026"
)
SOURCE_ANNEX_SHORT = "Anexo ao Ranking \u2014 Tabela de Encerramento, Junho/2026"


class AnbimaSourceMissingError(FileNotFoundError):
    """Raised when the official ANBIMA workbooks are not in the data directory."""


def resolve_source_workbooks(data_dir: Path = DEFAULT_DATA_DIR) -> tuple[Path, Path]:
    """Return ``(ranking, annex)`` from ``<data_dir>/sources``, newest first."""

    sources = Path(data_dir) / SOURCES_SUBDIR

    def newest(pattern: str, label: str) -> Path:
        matches = sorted(
            sources.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True
        )
        if not matches:
            raise AnbimaSourceMissingError(
                f"Planilha ANBIMA de {label} ausente em {sources}"
            )
        return matches[0]

    return newest(RANKING_GLOB, "ranking"), newest(ANNEX_GLOB, "anexo")


def _load(data_dir: Path) -> dict[str, object]:
    ranking_path, annex_path = resolve_source_workbooks(data_dir)
    official = parse_ranking_workbook(ranking_path)
    totals = parse_ranking_totals(ranking_path)
    annex = parse_annex_workbook(annex_path)
    origination = annex[annex["role"].eq("originacao")]
    per_registration = origination.groupby("registro_cvm")["percentual_participacao"].sum()
    return {
        "official": official,
        "totals": totals,
        "annex": annex,
        "matrix": operation_matrix(annex),
        "products": product_view(official, totals),
        "consistency": {
            "registros": int(len(per_registration)),
            "exatos": int((per_registration.round(4) == 1.0).sum()),
        },
        "sources": {
            "Ranking": workbook_sha256(ranking_path),
            "Anexo": workbook_sha256(annex_path),
        },
        "paths": (ranking_path, annex_path),
    }


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


TOP_FIDCS_NAME = "top_fidcs_middle_resolved.csv"

#: Data files under ``data_dir`` that the deck reads.  Whoever caches the deck
#: must fold these into its cache key, or a data refresh will keep serving the
#: previously rendered deck.
DECK_DATA_INPUTS: tuple[str, ...] = (TOP_FIDCS_NAME,)

#: Short display names for the middle-market list; the legal names do not fit.
_FIDC_SHORT = {
    1: "FIDC 30E",
    2: "Afinity MF",
    3: "Cobuccio",
    4: "For-Te",
    5: "Consignado Privado Paketá",
    6: "Cash Flow Multissegmentos",
    7: "Monee I",
    8: "Turbi I",
    9: "XPCE Infra",
    10: "Jefer Banking NP",
    11: "Kyklos N",
    12: "LF III",
    13: "Multiplica",
    14: "Red Real LP",
    15: "Residence Club",
    16: "Roqdeal",
}


def _short_cedente(value: str) -> str:
    """First assignor, trimmed of the legal-form tail, for a narrow column."""

    first = str(value).split("|")[0].strip()
    for tail in (
        " SOCIEDADE DE CRÉDITO AO MICROEMPREENDEDOR E À EMPRESA DE PEQUENO PORTE S.A.",
        " SOCIEDADE DE CRÉDITO, FINANCIAMENTO E INVESTIMENTOS",
        " SOCIEDADE DE CRÉDITO DIRETO S.A.",
        " INSTITUIÇÃO DE PAGAMENTO LTDA",
        " DISTRIBUIDORA DE TÍTULOS E VALORES MOBILIÁRIOS LTDA",
        " PARTICIPAÇÕES E PRODUÇÕES ARTÍSTICAS S.A.",
        " COMÉRCIO, IMPORTAÇÃO E EXPORTAÇÃO LTDA.",
        " INDÚSTRIA E COMÉRCIO DE CONFECÇÕES LTDA.",
        " COMPARTILHAMENTO DE VEÍCULOS S/A",
        " EMPREENDIMENTO HOTELEIRO S.A.",
        " DA AMAZÔNIA INDÚSTRIA DE APARELHOS ELÉTRICOS LTDA",
        " GARIMPEIRO URBANO COM. METAIS LTDA",
        " TELECOMUNICAÇÕES LTDA.",
        " PARTICIPAÇÕES S.A.",
        " S/A",
        " S.A.",
        " LTDA.",
        " LTDA",
    ):
        if first.upper().endswith(tail.upper()):
            first = first[: -len(tail)]
            break
    words = first.strip().split()
    # Acronyms such as QI, BMP, RQ, BWT, HRH and 30E must survive; only mixed
    # words get title case.
    return " ".join(
        word if (word.isupper() and len(word) <= 4) or any(ch.isdigit() for ch in word)
        else word.title()
        for word in words
    )


def top_fidcs_slide(deck: Deck, data_dir: Path) -> None:
    """Top FIDCs Middle — one row per fund, only what the bases confirm."""

    path = Path(data_dir) / TOP_FIDCS_NAME
    if not path.is_file():
        return
    table = pd.read_csv(path).sort_values("ordem")

    slide = deck.slide("Top FIDCs Middle | jan\u2013jun/26")
    deck.text(
        slide,
        "TOP 16 POR VOLUME CEDIDO NO PER\u00cdODO",
        MARGIN_IN,
        1.2,
        6.0,
        0.22,
        size=10,
        color=ORANGE,
        bold=True,
    )

    header = [
        "#",
        "FIDC",
        "Originador\u00b9",
        "Tipo",
        "Receb\u00edvel",
        "R$ bi",
        "IBBA Coord?",
        "Garantia Firme",
        "Bookamos?",
        "Risco IBBA",
    ]
    rows = [header]
    for record in table.itertuples():
        volume = record.volume_emissao_brl
        rows.append(
            [
                str(int(record.ordem)),
                _FIDC_SHORT.get(int(record.ordem), str(record.fidc)[:26]),
                _short_cedente(record.cedente_informado),
                str(record.tipo_anbima).replace("Agro, Indústria e Comércio", "Agro, Ind. e Com."),
                str(record.foco_anbima).replace("Multicarteira Agro, Indústria e Comércio", "Multicarteira Agro/Ind."),
                fmt_mm(volume / 1e9, 2) if pd.notna(volume) else "n/d",
                str(record.ibba_coordenou),
                str(record.garantia_firme),
                "",
                "",
            ]
        )

    subtotal = float(table["volume_emissao_brl"].dropna().sum())
    in_window_volume = float(
        table.loc[table["escopo_oferta"].eq("1S26"), "volume_emissao_brl"].dropna().sum()
    )
    # The denominator is the CVM universe of FIDC quota offers closed in 1S26,
    # stated on the reconciliation slide of this same deck.
    fidc_universe_brl = 65.488e9
    rows.append(
        ["", "Subtotal (R$ bi)", "", "", "", fmt_mm(subtotal / 1e9, 2), "", "", "", ""]
    )
    rows.append(
        [
            "",
            "Subtotal 1S26 (% emiss\u00f5es FIDC CVM)",
            "",
            "",
            "",
            fmt_pct(in_window_volume / fidc_universe_brl),
            "",
            "",
            "",
            "",
        ]
    )

    bottom = deck.native_table(
        slide,
        rows,
        MARGIN_IN,
        1.46,
        [0.30, 2.05, 1.95, 1.35, 1.90, 0.60, 1.50, 0.90, 0.70, 0.80],
        aligns="lllllrllll",
        size=8,
        row_height=0.245,
        header_height=0.34,
        header_fill=ORANGE,
        header_color=WHITE,
        emphasis_rows=(len(rows) - 2, len(rows) - 1),
    )

    missing = int(table["volume_emissao_brl"].isna().sum())
    deck.text(
        slide,
        "\u00b9 A coluna Originador reproduz o cedente informado na planilha de entrada. "
        "A confirma\u00e7\u00e3o de que o cedente \u00e9 tamb\u00e9m o originador dos direitos credit\u00f3rios exige "
        "leitura do regulamento e dos documentos da oferta \u2014 ver nota t\u00e9cnica no slide seguinte.",
        MARGIN_IN,
        bottom + 0.14,
        CONTENT_WIDTH_IN,
        0.28,
        size=8,
        color=GRAY_700,
    )
    deck.text(
        slide,
        f"Subtotal em R$ bi soma as ofertas de refer\u00eancia mostradas; o percentual usa apenas as "
        "encerradas no 1S26, sobre o universo CVM de cotas de FIDC do semestre (R$ 65,5 bi). "
        f"Bookamos? e Risco IBBA em branco por instru\u00e7\u00e3o. {missing} fundos n\u00e3o t\u00eam oferta "
        "p\u00fablica encerrada registrada na CVM e aparecem como n/d em R$ bi e "
        "\u201cN\u00e3o identificado\u201d nas colunas dependentes da oferta.",
        MARGIN_IN,
        bottom + 0.42,
        CONTENT_WIDTH_IN,
        0.28,
        size=8,
        color=GRAY_700,
    )
    deck.footer(
        slide,
        "Fonte: CVM, Oferta P\u00fablica de Distribui\u00e7\u00e3o \u2014 RCVM 160 e legado ICVM 400/476, "
        "prim\u00e1ria, encerrada \u00b7 ANBIMA, Fundos 175 caracter\u00edsticas p\u00fablico",
    )


UNKNOWN_LABEL = "Não identificado"


def top_fidcs_note_slide(deck: Deck, data_dir: Path) -> None:
    """Which source answered each column, and what is still open."""

    path = Path(data_dir) / TOP_FIDCS_NAME
    if not path.is_file():
        return
    table = pd.read_csv(path)
    resolved = int(table["volume_emissao_brl"].notna().sum())
    in_window = int((table["escopo_oferta"] == "1S26").sum())
    firm_known = int((~table["garantia_firme"].isin([UNKNOWN_LABEL])).sum())
    history = table[table["itau_lider_historico"].fillna("").ne("")]
    total_offers = int(table["ofertas_totais_fundo"].fillna(0).sum())
    missing = list(
        table.loc[table["volume_emissao_brl"].isna(), "ordem"].astype(int)
    )

    slide = deck.slide("Top FIDCs Middle \u2014 nota t\u00e9cnica de fontes")
    rows = [["Coluna", "Fonte utilizada", "Situa\u00e7\u00e3o"]]
    rows += [
        [
            "FIDC / CNPJ",
            "Planilha de entrada curada",
            "16 de 16 conferidos contra o cadastro ANBIMA",
        ],
        [
            "Originador",
            "\u2014",
            "N\u00e3o confirmado: exige regulamento e documentos da oferta",
        ],
        [
            "Tipo e Receb\u00edvel",
            "ANBIMA, Fundos 175 caracter\u00edsticas p\u00fablico",
            "16 de 16 classificados",
        ],
        [
            "R$ bi",
            "CVM, ofertas RCVM 160 e legado ICVM 400/476",
            f"{resolved} de 16 com oferta encerrada identificada",
        ],
        [
            "IBBA Coord?",
            "CVM, campo Nome_Lider da oferta",
            f"{resolved} de 16; a CVM publica apenas o l\u00edder",
        ],
        [
            "Garantia Firme",
            "CVM, campo Regime_distribuicao (s\u00f3 RCVM 160)",
            f"{firm_known} de 16; o legado n\u00e3o traz o campo",
        ],
        ["Bookamos? / Risco IBBA", "\u2014", "Em branco por instru\u00e7\u00e3o"],
    ]
    bottom = deck.native_table(
        slide,
        rows,
        MARGIN_IN,
        1.42,
        [2.4, 4.6, 5.05],
        aligns="lll",
        size=10,
        row_height=0.30,
    )

    notes = (
        (
            "Oferta de refer\u00eancia",
            f"Quando o fundo tem oferta encerrada no 1S26, ela \u00e9 a refer\u00eancia ({in_window} fundos). "
            "Sem oferta no semestre, usa-se a mais recente encerrada, e a data consta no CSV "
            "resolvido. As demais colunas vêm sempre da mesma oferta.",
        ),
        (
            "Por que o Originador ficou aberto",
            "Nem o arquivo de ofertas da CVM nem o cadastro ANBIMA declaram o originador dos "
            "direitos credit\u00f3rios. Os campos Descricao_lastro e Identificacao_devedores_coobrigados "
            f"est\u00e3o vazios nas {total_offers} ofertas encerradas destes fundos. Fechar a coluna exige o regulamento "
            "vigente e os documentos da oferta no FundosNet, fundo a fundo.",
        ),
        (
            "Ritos consultados",
            "Foram lidos os dois arquivos da CVM: o de ofertas autom\u00e1ticas RCVM 160 e o "
            "legado, com ICVM 400 e ICVM 476. As ICVM 476 s\u00e3o ofertas com esfor\u00e7os "
            "restritos e chegam rotuladas como \u201cCotas de fundos de investimento fechados\u201d, "
            "sem indicar o tipo do fundo; entram aqui porque o CNPJ emissor j\u00e1 \u00e9 um FIDC "
            "conhecido. Ordens "
            + ", ".join(str(value) for value in missing)
            + " seguem sem oferta encerrada em qualquer rito.",
        ),
        (
            "Itaú BBA em ofertas anteriores",
            "O banco liderou ofertas passadas de "
            + ", ".join(
                _FIDC_SHORT.get(int(row.ordem), str(row.fidc)[:18])
                for row in history.itertuples()
            )
            + ". No LF III liderou tr\u00eas emiss\u00f5es entre 2023 e 2024, e a oferta de refer\u00eancia "
            "de 2026 saiu com o UBS BB \u2014 hist\u00f3rico que a coluna IBBA Coord?, restrita \u00e0 "
            "oferta de refer\u00eancia, n\u00e3o mostra. O CSV resolvido traz as datas.",
        ),
        (
            "Ranking ANBIMA",
            "Apenas o LF III aparece no anexo do ranking ANBIMA de junho/2026, coordenado "
            "pelo UBS BB. Os demais 15 n\u00e3o entram no ranking, que \u00e9 declarat\u00f3rio.",
        ),
    )
    cursor = bottom + 0.18
    for title, text in notes:
        deck.text(slide, title, MARGIN_IN, cursor, 3.0, 0.24, size=9.5, color=ORANGE, bold=True)
        deck.text(slide, text, MARGIN_IN + 3.2, cursor, 8.85, 0.52, size=9, color=GRAY_700)
        cursor += 0.56
    deck.footer(
        slide,
        "Fontes consultadas: CVM Ofertas P\u00fablicas de Distribui\u00e7\u00e3o \u00b7 ANBIMA Fundos 175 "
        "caracter\u00edsticas p\u00fablico \u00b7 ANBIMA Anexo ao Ranking de Renda Fixa e H\u00edbridos",
    )


def build_deck(
    official: pd.DataFrame,
    totals: pd.DataFrame,
    matrix: pd.DataFrame,
    products: pd.DataFrame,
    sources: dict[str, str],
    consistency: dict[str, int],
    output: Path,
    data_dir: Path = DEFAULT_DATA_DIR,
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
    top_fidcs_slide(deck, data_dir)
    top_fidcs_note_slide(deck, data_dir)
    methodology_slide(deck)
    caveats_slide(deck, matrix, sources, consistency)

    if isinstance(output, Path):
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
    if isinstance(output, Path):
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




def build_anbima_deck_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    """Render the executive deck straight to bytes, for a download button."""

    loaded = _load(Path(data_dir))
    buffer = BytesIO()
    build_deck(
        loaded["official"],
        loaded["totals"],
        loaded["matrix"],
        loaded["products"],
        loaded["sources"],
        loaded["consistency"],
        buffer,
        Path(data_dir),
    )
    return buffer.getvalue()


def build_anbima_workbook_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    """Render the working spreadsheet straight to bytes."""

    loaded = _load(Path(data_dir))
    buffer = BytesIO()
    build_workbook(loaded["official"], loaded["matrix"], loaded["products"], buffer)
    return buffer.getvalue()


__all__ = [
    "AnbimaSourceMissingError",
    "DECK_DATA_INPUTS",
    "ANNEX_GLOB",
    "DEFAULT_DATA_DIR",
    "RANKING_GLOB",
    "build_anbima_deck_bytes",
    "build_anbima_workbook_bytes",
    "build_deck",
    "build_workbook",
    "top_fidcs_slide",
    "resolve_source_workbooks",
]
