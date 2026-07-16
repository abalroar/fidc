"""Native PowerPoint and Excel exports for the FIDC Industry intelligence pack."""

from __future__ import annotations

import json
import re
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data" / "industry_study"

NAVY = "11263D"
ORANGE = "E86A1A"
TEAL = "168AAD"
GREEN = "2B7A55"
RED = "B5463C"
GRAY_900 = "26323D"
GRAY_700 = "52606D"
GRAY_500 = "87929C"
GRAY_300 = "CDD3D8"
GRAY_100 = "F3F5F6"
WHITE = "FFFFFF"
_CHART_AXIS_ID_RE = re.compile(rb'(<c:(?:axId|crossAx)\b[^>]*\bval=")(-\d+)(")')


def _read(data_dir: Path, name: str) -> pd.DataFrame:
    path = data_dir / name
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def _read_manifest(data_dir: Path) -> dict:
    path = data_dir / "industry_intelligence_manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _competence_label(value: object, *, short: bool = False, lower: bool = False) -> str:
    full_names = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")
    short_names = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")
    try:
        period = pd.Period(str(value), freq="M")
    except (TypeError, ValueError):
        return str(value)
    label = f"{(short_names if short else full_names)[period.month - 1]}/{str(period.year)[-2:]}"
    return label.lower() if lower else label


def _date_label(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return str(value) if pd.isna(parsed) else parsed.strftime("%d/%m/%Y")


def _normalize_chart_axis_ids(payload: bytes) -> bytes:
    """Convert signed chart-axis IDs to their OpenXML unsigned representation."""

    def replace_axis_id(match: re.Match[bytes]) -> bytes:
        unsigned_value = int(match.group(2)) % (2**32)
        return match.group(1) + str(unsigned_value).encode("ascii") + match.group(3)

    output = BytesIO()
    with zipfile.ZipFile(BytesIO(payload), "r") as source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for member in source.infolist():
            data = source.read(member.filename)
            if member.filename.startswith("ppt/charts/chart") and member.filename.endswith(".xml"):
                data = _CHART_AXIS_ID_RE.sub(replace_axis_id, data)
            target.writestr(member, data)
    return output.getvalue()


def _fmt_bi(value: object, decimals: int = 1) -> str:
    return f"R$ {float(value or 0) / 1e9:.{decimals}f} bi".replace(".", ",")


def _fmt_pct(value: object, decimals: int = 1) -> str:
    return f"{float(value or 0) * 100:.{decimals}f}%".replace(".", ",")


def _fmt_pp(value: object, decimals: int = 1) -> str:
    number = float(value or 0)
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.{decimals}f} p.p.".replace(".", ",")


def _yearly_industry(industry: pd.DataFrame, latest_complete: str) -> pd.DataFrame:
    frame = industry[industry["competencia"].astype(str).le(latest_complete)].copy()
    frame["year"] = frame["competencia"].astype(str).str[:4].astype(int)
    rows = []
    for year, group in frame.groupby("year"):
        december = group[group["competencia"].astype(str).str.endswith("-12")]
        row = december.iloc[-1] if not december.empty else group.sort_values("competencia").iloc[-1]
        rows.append(row)
    output = pd.DataFrame(rows).sort_values("year")
    output["pl_ex_fic"] = output["pl_total"] - output["pl_fic_fidc"].fillna(0)
    output["growth"] = output["pl_ex_fic"].pct_change()
    return output


def _annual_segment_mix(segments: pd.DataFrame, yearly: pd.DataFrame) -> pd.DataFrame:
    selected = yearly[["year", "competencia"]].copy()
    frame = segments[segments["nivel"].eq("top")].merge(selected, on="competencia", how="inner")
    pivot = frame.pivot_table(index="year", columns="segmento", values="valor", aggfunc="sum", fill_value=0)
    keep = list(pivot.sum().sort_values(ascending=False).head(7).index)
    output = pivot[keep].copy()
    remaining = pivot.drop(columns=keep).sum(axis=1)
    if remaining.gt(0).any():
        output["Outros"] = remaining
    return output.div(output.sum(axis=1).replace(0, 1), axis=0)


def _stock_table(stock: pd.DataFrame, role: str, *, limit: int = 9) -> pd.DataFrame:
    frame = stock[(stock["role"].eq(role)) & stock["segment"].eq("Todos") & stock["metric"].eq("PL")].copy()
    current = frame[frame["period"].eq("2026YTD")].sort_values("rank").head(limit)
    rows = []
    for participant in current["participant"]:
        row = {"Participante": participant}
        for period in ("2024", "2025", "2026YTD"):
            match = frame[(frame["participant"].eq(participant)) & frame["period"].eq(period)]
            row[f"Rank {period}"] = int(match.iloc[0]["rank"]) if not match.empty else "-"
            row[f"Share {period}"] = _fmt_pct(match.iloc[0]["share"]) if not match.empty else "-"
        first = frame[(frame["participant"].eq(participant)) & frame["period"].eq("2024")]
        last = frame[(frame["participant"].eq(participant)) & frame["period"].eq("2026YTD")]
        row["Δ share"] = _fmt_pp((float(last.iloc[0]["share"]) - float(first.iloc[0]["share"])) * 100) if not first.empty and not last.empty else "-"
        rows.append(row)
    return pd.DataFrame(rows)


def _segment_dance(stock: pd.DataFrame) -> pd.DataFrame:
    frame = stock[(stock["role"].eq("administrador")) & stock["metric"].eq("PL") & stock["segment"].ne("Todos")].copy()
    current = frame[frame["period"].eq("2026YTD")]
    segment_sizes = current.groupby("segment")["value"].sum().sort_values(ascending=False).head(8)
    rows = []
    for segment in segment_sizes.index:
        part = frame[frame["segment"].eq(segment)]
        now = part[part["period"].eq("2026YTD")].sort_values("rank")
        changes = []
        for participant in set(part["participant"]):
            p24 = part[(part["participant"].eq(participant)) & part["period"].eq("2024")]
            p26 = part[(part["participant"].eq(participant)) & part["period"].eq("2026YTD")]
            if p24.empty or p26.empty:
                continue
            changes.append((participant, (float(p26.iloc[0]["share"]) - float(p24.iloc[0]["share"])) * 100))
        changes.sort(key=lambda item: item[1], reverse=True)
        rows.append(
            {
                "Segmento CVM": segment,
                "Líder 2026": now.iloc[0]["participant"] if not now.empty else "-",
                "Share líder": _fmt_pct(now.iloc[0]["share"]) if not now.empty else "-",
                "Maior ganho 24-26": changes[0][0] if changes else "-",
                "Δ ganho": _fmt_pp(changes[0][1]) if changes else "-",
                "Maior perda 24-26": changes[-1][0] if changes else "-",
                "Δ perda": _fmt_pp(changes[-1][1]) if changes else "-",
            }
        )
    return pd.DataFrame(rows)


def build_industry_xlsx_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    names = {
        "Competências": "industry_competence_status.csv",
        "Indústria mensal": "industry_monthly.csv",
        "Segmentos": "segments_monthly.csv",
        "Ofertas anual": "industry_offers_annual.csv",
        "Posição Itaú": "industry_competitive_position.csv",
        "Ranking ofertas": "industry_offer_rankings.csv.gz",
        "Ranking estoque": "industry_stock_ranking_deltas.csv.gz",
        "Cedentes": "industry_originators_annual.csv",
        "Investidores hist": "industry_investor_distribution.csv",
        "Tipos investidor": "industry_investor_types.csv",
        "FIDCs >5bi": "industry_large_fund_classification.csv",
        "Docs >5bi": "industry_large_fund_documents.csv.gz",
    }
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet, filename in names.items():
            frame = _read(data_dir, filename)
            frame.to_excel(writer, sheet_name=sheet[:31], index=False)
            ws = writer.book[sheet[:31]]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for column_cells in ws.columns:
                width = min(max(len(str(cell.value or "")) for cell in list(column_cells)[:250]) + 2, 10, 42)
                ws.column_dimensions[column_cells[0].column_letter].width = width
    return output.getvalue()


def build_industry_pptx_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.util import Inches, Pt

    industry = _read(data_dir, "industry_monthly.csv")
    status = _read(data_dir, "industry_competence_status.csv")
    segments = _read(data_dir, "segments_monthly.csv")
    annual = _read(data_dir, "industry_offers_annual.csv")
    competitive = _read(data_dir, "industry_competitive_position.csv")
    rankings = _read(data_dir, "industry_offer_rankings.csv.gz")
    stock = _read(data_dir, "industry_stock_ranking_deltas.csv.gz")
    originators = _read(data_dir, "industry_originators_annual.csv")
    investor_distribution = _read(data_dir, "industry_investor_distribution.csv")
    investor_types = _read(data_dir, "industry_investor_types.csv")
    large_funds = _read(data_dir, "industry_large_fund_classification.csv")
    manifest = _read_manifest(data_dir)

    complete = status[status["publication_status"].eq("completa")].sort_values("competencia")
    latest_complete = str(complete.iloc[-1]["competencia"])
    latest_available = str(status.sort_values("competencia").iloc[-1]["competencia"])
    preliminary = status[status["publication_status"].ne("completa")].sort_values("competencia").tail(1)
    preliminary_row = preliminary.iloc[0] if not preliminary.empty else None
    offers_as_of = str(manifest.get("as_of_date") or "n/d")
    yearly = _yearly_industry(industry, latest_complete)
    mix = _annual_segment_mix(segments, yearly)
    latest_comp = competitive.sort_values("year").iloc[-1]

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    def rgb(hex_color: str) -> RGBColor:
        return RGBColor.from_string(hex_color)

    def add_text(slide, text, x, y, w, h, *, size=12, color=GRAY_900, bold=False, align=PP_ALIGN.LEFT, font="Aptos", valign=MSO_ANCHOR.TOP):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        frame = box.text_frame
        frame.clear()
        frame.word_wrap = True
        frame.vertical_anchor = valign
        paragraph = frame.paragraphs[0]
        paragraph.text = str(text)
        paragraph.alignment = align
        paragraph.font.name = font
        paragraph.font.size = Pt(size)
        paragraph.font.bold = bold
        paragraph.font.color.rgb = rgb(color)
        return box

    def base_slide(title: str, kicker: str = "INDÚSTRIA FIDC"):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        background = slide.background.fill
        background.solid()
        background.fore_color.rgb = rgb(WHITE)
        add_text(slide, kicker, 0.55, 0.28, 3.0, 0.25, size=8, color=ORANGE, bold=True)
        add_text(slide, title, 0.55, 0.58, 12.1, 0.48, size=22, color=NAVY, bold=True)
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.55), Inches(1.13), Inches(12.15), Inches(0.035))
        line.fill.solid(); line.fill.fore_color.rgb = rgb(ORANGE); line.line.fill.background()
        return slide

    def footer(slide, source: str, page: int):
        add_text(slide, source, 0.58, 7.12, 11.8, 0.2, size=6.8, color=GRAY_500)
        add_text(slide, str(page), 12.45, 7.10, 0.3, 0.2, size=7, color=GRAY_500, align=PP_ALIGN.RIGHT)

    def add_table(slide, frame: pd.DataFrame, x, y, w, h, *, font_size=8.5, widths=None, highlight="Itaú"):
        if frame.empty:
            add_text(slide, "Sem dados", x, y, w, h, size=11, color=GRAY_500)
            return None
        table_shape = slide.shapes.add_table(len(frame) + 1, len(frame.columns), Inches(x), Inches(y), Inches(w), Inches(h))
        table = table_shape.table
        if widths:
            total = sum(widths)
            for index, share in enumerate(widths):
                table.columns[index].width = Inches(w * share / total)
        for col, name in enumerate(frame.columns):
            cell = table.cell(0, col)
            cell.text = str(name)
            cell.fill.solid(); cell.fill.fore_color.rgb = rgb(NAVY)
        for row_index, row in enumerate(frame.itertuples(index=False), start=1):
            is_highlight = any(highlight.lower() in str(value).lower() for value in row) if highlight else False
            for col_index, value in enumerate(row):
                cell = table.cell(row_index, col_index)
                cell.text = str(value)
                cell.fill.solid(); cell.fill.fore_color.rgb = rgb("FFF2E9" if is_highlight else (WHITE if row_index % 2 else GRAY_100))
        for row in table.rows:
            for cell in row.cells:
                cell.margin_left = Inches(0.05); cell.margin_right = Inches(0.05)
                cell.margin_top = Inches(0.025); cell.margin_bottom = Inches(0.025)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                for paragraph in cell.text_frame.paragraphs:
                    paragraph.font.name = "Aptos"
                    paragraph.font.size = Pt(font_size)
                    paragraph.font.color.rgb = rgb(WHITE if row is table.rows[0] else GRAY_900)
                    paragraph.font.bold = row is table.rows[0]
        return table

    def add_chart(slide, categories, series, x, y, w, h, *, chart_type, colors=None, legend=True, value_format="0.0"):
        data = CategoryChartData()
        data.categories = [str(value) for value in categories]
        for name, values in series:
            data.add_series(str(name), [float(value) for value in values])
        chart = slide.shapes.add_chart(chart_type, Inches(x), Inches(y), Inches(w), Inches(h), data).chart
        chart.has_legend = legend
        if legend:
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            chart.legend.font.size = Pt(8)
        chart.has_title = False
        chart.value_axis.tick_labels.font.size = Pt(8)
        chart.category_axis.tick_labels.font.size = Pt(8)
        chart.value_axis.tick_labels.number_format = value_format
        chart.value_axis.major_gridlines.format.line.color.rgb = rgb(GRAY_300)
        for index, chart_series in enumerate(chart.series):
            chart_series.format.fill.solid()
            chart_series.format.fill.fore_color.rgb = rgb((colors or [ORANGE, NAVY, TEAL, GREEN, GRAY_500])[index % len(colors or [ORANGE, NAVY, TEAL, GREEN, GRAY_500])])
            chart_series.format.line.color.rgb = chart_series.format.fill.fore_color.rgb
        return chart

    # 1. Cover
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid(); slide.background.fill.fore_color.rgb = rgb(NAVY)
    accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.18), Inches(7.5))
    accent.fill.solid(); accent.fill.fore_color.rgb = rgb(ORANGE); accent.line.fill.background()
    add_text(slide, "INDÚSTRIA DE FIDCs", 0.8, 1.35, 11.5, 0.7, size=34, color=WHITE, bold=True)
    add_text(slide, "Crescimento, originação, prestadores e base investidora", 0.82, 2.2, 10.8, 0.42, size=17, color="D9E1E8")
    load_status = f"prévia {latest_available} monitorada" if preliminary_row is not None else f"carga {latest_available} consolidada"
    add_text(
        slide,
        f"Competência consolidada {latest_complete} | {load_status} | ofertas até {_date_label(offers_as_of)}",
        0.82,
        3.05,
        10.8,
        0.32,
        size=12,
        color=ORANGE,
        bold=True,
    )
    add_text(slide, "CVM Informe Mensal + Ofertas Públicas + leitura documental CVM/FundosNet", 0.82, 6.55, 10.8, 0.3, size=9, color="B9C5CF")

    # 2. Executive answer
    slide = base_slide("A resposta em uma página", "LEITURA EXECUTIVA")
    add_text(slide, "Originação forte. Conversão em servicing recorrente ainda muito abaixo do potencial.", 0.65, 1.35, 12.0, 0.45, size=17, color=NAVY, bold=True)
    rows = [
        ("Coordenação > R$ 300 mi", f"#{int(latest_comp['itau_coordinator_rank'])} em 2026YTD", f"{_fmt_bi(latest_comp['itau_coordinator_volume_brl'])} · {_fmt_pct(latest_comp['itau_coordinator_share'])} do mercado", ORANGE),
        ("Administração nas mesmas ofertas", _fmt_pct(latest_comp["itau_administrator_share"]), f"{_fmt_bi(latest_comp['itau_administrator_volume_brl'])} · rank #{int(latest_comp['itau_administrator_rank']) or '-'}", NAVY),
        ("Custódia nas mesmas ofertas", _fmt_pct(latest_comp["itau_custodian_share"]), f"{_fmt_bi(latest_comp['itau_custodian_volume_brl'])} · rank #{int(latest_comp['itau_custodian_rank']) or '-'}", TEAL),
        ("Ponto de decisão", "Capturar o pós-originação", "Mandato de administração/custódia e distribuição institucional são o gap econômico", GREEN),
    ]
    for index, (label, value, note, color) in enumerate(rows):
        y = 2.05 + index * 1.08
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.65), Inches(y), Inches(0.08), Inches(0.78))
        bar.fill.solid(); bar.fill.fore_color.rgb = rgb(color); bar.line.fill.background()
        add_text(slide, label, 0.9, y, 3.2, 0.25, size=9, color=GRAY_700, bold=True)
        add_text(slide, value, 4.0, y - 0.03, 2.4, 0.38, size=19, color=color, bold=True)
        add_text(slide, note, 6.25, y, 6.1, 0.45, size=10.5, color=GRAY_900)
    footer(slide, "Fonte: CVM Ofertas Públicas de Distribuição; volumes registrados. Não identifica o beneficiário nominal do encarteiramento.", 2)

    # 3. Industry growth
    growth_title = (
        f"O mercado segue crescendo; {_competence_label(preliminary_row['competencia'], lower=True)} ainda não é uma fotografia publicável"
        if preliminary_row is not None
        else "O mercado segue crescendo com a última competência consolidada"
    )
    slide = base_slide(growth_title, "TAMANHO E FLUXO")
    growth_frame = yearly[yearly["year"].ge(2018)]
    add_chart(slide, growth_frame["year"], [("PL ex-FIC", growth_frame["pl_ex_fic"] / 1e9)], 0.65, 1.45, 8.0, 4.8, chart_type=XL_CHART_TYPE.LINE_MARKERS, colors=[ORANGE], legend=False, value_format="0")
    table = pd.DataFrame({
        "Ano": growth_frame["year"].astype(str),
        "PL ex-FIC": growth_frame["pl_ex_fic"].map(lambda v: _fmt_bi(v, 0)),
        "Crescimento": growth_frame["growth"].map(lambda v: "-" if pd.isna(v) else _fmt_pct(v)),
    }).tail(7)
    add_table(slide, table, 8.9, 1.48, 3.8, 3.9, font_size=8.5, widths=[1, 1.5, 1.2], highlight="")
    if preliminary_row is not None:
        add_text(
            slide,
            f"{_competence_label(preliminary_row['competencia'], short=True)}: {_fmt_pct(preliminary_row['vehicle_ratio_vs_previous'])} dos veículos e {_fmt_pct(preliminary_row['pl_ratio_vs_previous'])} do PL da competência anterior.",
            8.95,
            5.65,
            3.6,
            0.6,
            size=10,
            color=RED,
            bold=True,
        )
    footer(slide, f"Fonte: Informe Mensal FIDC/CVM. PL ex-FIC reduz dupla contagem econômica; fotografia consolidada em {latest_complete}.", 3)

    # 4. 100% segment mix
    slide = base_slide("A composição mudou junto com a expansão do crédito estruturado", "COMPOSIÇÃO DO PL")
    add_chart(slide, mix.index, [(column, mix[column] * 100) for column in mix.columns], 0.65, 1.42, 12.0, 4.95, chart_type=XL_CHART_TYPE.COLUMN_STACKED_100, colors=[ORANGE, NAVY, TEAL, GREEN, "6C5B7B", "C49A00", GRAY_700, GRAY_300], legend=True, value_format="0%")
    add_text(slide, "Leitura pela Tabela II da CVM. A classificação econômica documental pode divergir do rótulo ANBIMA.", 0.8, 6.48, 11.5, 0.3, size=9, color=GRAY_700)
    footer(slide, f"Fonte: Informe Mensal FIDC/CVM, Tabela II; dezembro de cada ano e {latest_complete}.", 4)

    # 5. ANBIMA definitions
    slide = base_slide("Classes ANBIMA: o rótulo formal não substitui a leitura do lastro", "REFERENCIAL ANBIMA")
    definitions = [
        ("Fomento Mercantil", "Recebíveis pulverizados de vários cedentes que antecipam recursos; duplicatas, cheques e operações típicas de factoring."),
        ("Financeiro", "Recebíveis originados por instituições financeiras: consignado, crédito pessoal, veículos, imobiliário e multicarteira financeiro."),
        ("Agro, Indústria e Comércio", "Recebíveis do setor real: infraestrutura, energia, comércio, agronegócio e determinados fluxos de cartão."),
        ("Outros", "Recuperação/NPL, ações judiciais, precatórios e focos que não se enquadram nas classes anteriores."),
    ]
    for index, (label, description) in enumerate(definitions):
        y = 1.45 + index * 1.18
        add_text(slide, label, 0.75, y, 3.1, 0.32, size=13, color=ORANGE if index == 2 else NAVY, bold=True)
        add_text(slide, description, 3.5, y, 8.8, 0.68, size=11, color=GRAY_900)
    add_text(slide, "Achado documental: CloudWalk aparece como Agro, Indústria e Comércio / Crédito Corporativo no regulamento, mas o lastro é meios de pagamento. Por isso o estudo mantém taxonomia formal e econômica em colunas separadas.", 0.75, 6.15, 11.9, 0.65, size=10, color=RED, bold=True)
    footer(slide, "Fonte: ANBIMA, Deliberação nº 72; leitura dos regulamentos CVM/FundosNet dos FIDCs > R$ 5 bi.", 5)

    # 6. Relevant tickets
    slide = base_slide("Itaú liderou tickets relevantes em 2024-25 e segue competitivo em 2026", "OFERTAS > R$ 300 MI")
    add_chart(slide, competitive["period"], [("Mercado", competitive["market_relevant_volume_brl"] / 1e9), ("Itaú coordenador", competitive["itau_coordinator_volume_brl"] / 1e9)], 0.65, 1.48, 7.2, 4.9, chart_type=XL_CHART_TYPE.COLUMN_CLUSTERED, colors=[NAVY, ORANGE], legend=True, value_format="0")
    relevant_table = pd.DataFrame({
        "Período": competitive["period"],
        "Mercado": competitive["market_relevant_volume_brl"].map(_fmt_bi),
        "Ofertas": competitive["market_relevant_offers"].astype(int),
        "Itaú": competitive["itau_coordinator_volume_brl"].map(_fmt_bi),
        "Share": competitive["itau_coordinator_share"].map(_fmt_pct),
        "Rank": competitive["itau_coordinator_rank"].map(lambda value: f"#{int(value)}"),
    })
    add_table(slide, relevant_table, 8.1, 1.5, 4.55, 2.7, font_size=8, widths=[1.1, 1.5, .8, 1.4, 1, .7])
    add_text(slide, "Volume registrado CVM", 8.2, 4.55, 2.5, 0.25, size=9, color=GRAY_700, bold=True)
    add_text(slide, "Inclui ofertas subsequentes e reaberturas. O deck separa também ofertas iniciais, evitando confundir atividade total de DCM com nascimento de novos veículos.", 8.2, 4.9, 4.15, 1.0, size=10.5, color=GRAY_900)
    footer(slide, "Fonte: CVM Ofertas Públicas de Distribuição, registros válidos. Ticket = valor total registrado ≥ R$ 300 mi.", 6)

    # 7. Role capture
    slide = base_slide("O gap está na captura de mandatos recorrentes depois da coordenação", "CONVERSÃO DA ORIGINAÇÃO")
    role_labels = ["Coordenação", "Administração", "Gestão", "Custódia"]
    role_values = [latest_comp["itau_coordinator_share"], latest_comp["itau_administrator_share"], latest_comp["itau_manager_share"], latest_comp["itau_custodian_share"]]
    add_chart(slide, role_labels, [("Share Itaú", [value * 100 for value in role_values])], 0.7, 1.45, 6.5, 4.8, chart_type=XL_CHART_TYPE.BAR_CLUSTERED, colors=[ORANGE], legend=False, value_format="0.0")
    conversion = pd.DataFrame({
        "Período": competitive["period"],
        "Coord.": competitive["itau_coordinator_share"].map(_fmt_pct),
        "Adm.": competitive["itau_administrator_share"].map(_fmt_pct),
        "Gestão": competitive["itau_manager_share"].map(_fmt_pct),
        "Custódia": competitive["itau_custodian_share"].map(_fmt_pct),
        "Monoestrutura mercado": competitive["market_monostructure_volume_share"].map(_fmt_pct),
    })
    add_table(slide, conversion, 7.5, 1.5, 5.15, 2.75, font_size=8, widths=[1.1, .9, .9, .9, .9, 1.8])
    add_text(slide, f"Em 2026YTD, {_fmt_pct(latest_comp['market_monostructure_volume_share'])} do volume relevante usa o mesmo grupo em administração, gestão e custódia. A integração vertical existe, mas não é universal.", 7.6, 4.65, 4.7, 0.9, size=11, color=NAVY, bold=True)
    footer(slide, "Fonte: CVM Ofertas Públicas de Distribuição. Participantes canônicos por conglomerado; papéis não são somáveis.", 7)

    # 8-10. Stock roles
    for page, role, title, note in [
        (8, "administrador", "Administração: BTG assumiu a liderança; Itaú permanece #9", "Histórico mensal do Informe Mensal CVM; mudança de share é publicável."),
        (9, "gestor", "Gestão: foto econômica útil, mas troca de mandato não é observável no histórico", "Gestor vigente foi aplicado ao painel histórico; serve para exposição atual, não para afirmar troca passada."),
        (10, "custodiante", "Custódia: BTG e QI lideram; Itaú está fora do top 10 de estoque", "Custodiante vigente foi aplicado ao painel histórico; deltas são reconstrução, não trilha cadastral completa."),
    ]:
        slide = base_slide(title, role.upper())
        table = _stock_table(stock, role, limit=9)
        add_table(slide, table, 0.65, 1.45, 12.0, 4.8, font_size=7.3, widths=[2.6, .7, 1, .7, 1, .8, 1, 1])
        add_text(slide, note, 0.75, 6.42, 11.5, 0.38, size=9.5, color=RED if role != "administrador" else GRAY_700, bold=role != "administrador")
        footer(slide, "Fonte: Informe Mensal FIDC/CVM + cadastro vigente de prestadores. Share sobre PL do papel em cada competência.", page)

    # 11. Segment dance
    slide = base_slide("Dança das cadeiras por subsegmento: administração é a trilha histórica defensável", "DELTA 2024 → 2026YTD")
    dance = _segment_dance(stock)
    add_table(slide, dance, 0.6, 1.4, 12.1, 4.95, font_size=7.4, widths=[1.6, 1.5, .8, 1.5, .8, 1.5, .8], highlight="")
    add_text(slide, "Filtro do dashboard permite trocar papel, métrica, segmento CVM e top N. Para gestor e custodiante, o histórico permanece marcado como reconstruído.", 0.75, 6.45, 11.5, 0.35, size=9.5, color=GRAY_700)
    footer(slide, "Fonte: Informe Mensal FIDC/CVM, Tabela I e IV. Segmento = principal exposição da Tabela II.", 11)

    # 12. Originators
    slide = base_slide("Cedentes/originadores nomináveis mostram a nova fronteira comercial", "CEDENTES 2024–2026YTD")
    for index, period in enumerate(["2024", "2025", "2026YTD"]):
        frame = originators[originators["period"].astype(str).eq(period)].sort_values("rank").head(8)
        display = pd.DataFrame({"Cedente/originador": frame["originator_group"], "Volume": frame["volume_brl"].map(_fmt_bi)})
        add_text(slide, period, 0.65 + index * 4.13, 1.35, 3.8, 0.3, size=13, color=ORANGE, bold=True)
        add_table(slide, display, 0.65 + index * 4.13, 1.75, 3.85, 4.35, font_size=8, widths=[2.1, 1], highlight="")
        coverage = float(frame["identified_volume_coverage"].max()) if not frame.empty else 0.0
        add_text(slide, f"Cobertura nominal: {_fmt_pct(coverage)} do volume", 0.72 + index * 4.13, 6.2, 3.6, 0.3, size=8.5, color=GRAY_700, bold=True)
    footer(slide, "Fonte: CVM Ofertas Públicas. Somente regras nominais auditáveis; volume não identificado é excluído do ranking e cobertura é exibida.", 12)

    # 13. Investor structure
    slide = base_slide("A colocação é concentrada, mas fundos e bancos aparecem com frequência", "BASE INVESTIDORA")
    bucket_order = ["1 investidor", "2 investidores", "3-5 investidores", "6-20 investidores", "21+ investidores"]
    inv_pivot = investor_distribution.pivot_table(index="period", columns="investor_bucket", values="offer_share", fill_value=0)
    inv_pivot = inv_pivot.reindex(columns=[col for col in bucket_order if col in inv_pivot], fill_value=0)
    add_chart(slide, inv_pivot.index, [(column, inv_pivot[column] * 100) for column in inv_pivot.columns], 0.65, 1.45, 7.0, 4.85, chart_type=XL_CHART_TYPE.COLUMN_STACKED_100, colors=[ORANGE, NAVY, TEAL, GREEN, GRAY_500], legend=True, value_format="0%")
    annual_display = pd.DataFrame({
        "Período": annual["period"],
        "Encerradas c/ dado": annual["offers_with_investor_data"].astype(int),
        "1 investidor": annual["single_investor_share"].map(_fmt_pct),
        "Mediana": annual["median_investors"].map(lambda value: f"{int(value)}"),
    })
    add_table(slide, annual_display, 7.95, 1.55, 4.6, 2.65, font_size=8.3, widths=[1.1, 1.8, 1.2, .9])
    latest_types = investor_types[investor_types["period"].astype(str).eq("2026YTD")].sort_values("placed_volume_proxy_brl", ascending=False).head(5)
    type_display = pd.DataFrame({"Tipo": latest_types["investor_type"], "% valor proxy": latest_types["value_share"].map(_fmt_pct)})
    add_table(slide, type_display, 7.95, 4.45, 4.6, 1.65, font_size=7.8, widths=[2, 1], highlight="")
    footer(slide, "Fonte: CVM Ofertas Públicas encerradas. Quantidades por categoria; não há identificação nominal do cotista.", 13)

    # 14. Large funds
    slide = base_slide(f"Os {len(large_funds)} FIDCs acima de R$ 5 bi foram classificados com leitura documental", "COBERTURA DOCUMENTAL")
    large_display = large_funds.copy()
    large_display["Fundo"] = large_display["fund_name"].astype(str).str.replace("FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS", "FIDC", regex=False).str.slice(0, 44)
    large_display["PL"] = large_display["pl_brl"].map(lambda value: _fmt_bi(value, 1))
    large_display["Segmento econômico"] = large_display["document_segment_n2"]
    large_display["ANBIMA doc."] = large_display["anbima_type_document"].fillna("-")
    large_display["Leitura"] = large_display.apply(lambda row: f"{int(row['documents_read'])}/{int(row['documents_relevant'])}", axis=1)
    add_table(slide, large_display[["Fundo", "PL", "Segmento econômico", "ANBIMA doc.", "Leitura"]], 0.55, 1.35, 12.25, 5.55, font_size=6.6, widths=[2.8, .8, 1.9, 1.6, .7], highlight="Itaú")
    listed_documents = int(large_funds["documents_listed"].sum()) if not large_funds.empty else 0
    read_documents = int(large_funds["documents_read"].sum()) if not large_funds.empty else 0
    coverage_source = (
        f"Fonte: CVM/FundosNet. {listed_documents:,} documentos listados; {read_documents:,} classificatórios lidos; fotografia de PL {latest_complete}."
        .replace(",", ".")
    )
    footer(slide, coverage_source, 14)

    # 15. Methodology
    slide = base_slide("O que é publicável, reconstruído e ainda não observável", "DEFENSABILIDADE")
    methodology = pd.DataFrame(
        [
            [
                "PL, fluxos, cotistas, inadimplência",
                "Publicável",
                (
                    f"Informe Mensal CVM; {_competence_label(preliminary_row['competencia'], lower=True)} marcado preliminar enquanto cobertura <85%."
                    if preliminary_row is not None
                    else f"Informe Mensal CVM consolidado até {_competence_label(latest_complete, lower=True)}."
                ),
            ],
            ["Administração histórica", "Publicável", "Administrador consta mensalmente no informe; delta 2024-26 é observável."],
            ["Gestão e custódia históricas", "Reconstrução", "Cadastro vigente aplicado ao PL passado; não prova troca de mandato."],
            ["Ofertas e tickets >R$300 mi", "Publicável", "Volume registrado CVM; separar oferta válida, encerrada e inicial."],
            ["Cedentes/originadores", "Parcial auditável", "Só nomes com regra/evidência explícita; cobertura nominal exibida por ano."],
            ["Investidor nominal", "Não observável", "CVM divulga categorias e contagens, não beneficiário final."],
            ["Mercado secundário", "Não observável gratuitamente", "Campo de mercado indica infraestrutura/elegibilidade, não turnover nem velocidade."],
        ],
        columns=["Dimensão", "Status", "Leitura"],
    )
    add_table(slide, methodology, 0.65, 1.42, 12.0, 4.95, font_size=9, widths=[1.8, 1.2, 4.6], highlight="Publicável")
    add_text(slide, "Fontes primárias: dados.cvm.gov.br/dataset/fidc-doc-inf_mensal e dados.cvm.gov.br/dataset/oferta-distrib. Taxonomia ANBIMA conforme Deliberação nº 72.", 0.75, 6.5, 11.4, 0.35, size=9, color=GRAY_700)
    footer(slide, "Elaboração: dashboard FIDC | metodologia versionada em data/industry_study.", 15)

    # 16. Decision agenda
    slide = base_slide("Quatro movimentos para converter originação em receita recorrente", "AGENDA DE DECISÃO")
    latest_period = str(latest_comp["period"])
    latest_annual = annual.sort_values("year").iloc[-1]
    originator_names = ", ".join(
        originators[originators["period"].astype(str).eq(latest_period)]
        .sort_values("rank")
        .head(5)["originator_group"]
        .astype(str)
    )
    actions = [
        (
            "1  Tornar o mandato completo",
            f"{_fmt_pct(latest_comp['itau_coordinator_share'])} em coordenação vs. {_fmt_pct(latest_comp['itau_administrator_share'])} em administração",
            "Vincular proposta de administração, custódia e distribuição a cada ticket acima de R$ 300 mi.",
            ORANGE,
        ),
        (
            "2  Priorizar cedentes atacáveis",
            originator_names or "Cobertura nominal ainda insuficiente",
            "Transformar o ranking conservador em pipeline comercial com dono, relação atual e próxima emissão.",
            NAVY,
        ),
        (
            "3  Ampliar o reencarteiramento",
            f"{_fmt_pct(latest_annual['single_investor_share'])} das ofertas com composição têm um único investidor",
            "Usar a leitura por categoria para separar estruturas cativas de ofertas distribuíveis a fundos e bancos.",
            TEAL,
        ),
        (
            "4  Medir o secundário de verdade",
            "Base transacional B3/ANBIMA",
            "Contratar ou integrar negócios por ativo; o registro público de mercado não mede giro nem velocidade de venda.",
            GREEN,
        ),
    ]
    for index, (label, evidence, implication, color) in enumerate(actions):
        y = 1.42 + index * 1.3
        marker = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.68), Inches(y), Inches(0.09), Inches(0.92))
        marker.fill.solid(); marker.fill.fore_color.rgb = rgb(color); marker.line.fill.background()
        add_text(slide, label, 0.95, y, 3.0, 0.34, size=12, color=color, bold=True)
        add_text(slide, evidence, 3.8, y, 4.0, 0.62, size=13, color=NAVY, bold=True)
        add_text(slide, implication, 7.85, y, 4.45, 0.72, size=10.5, color=GRAY_900)
    footer(slide, f"Base de decisão: CVM Informe Mensal até {latest_complete}; ofertas públicas até {_date_label(offers_as_of)}; cobertura nominal explicitada no deck.", 16)

    output = BytesIO()
    prs.save(output)
    return _normalize_chart_axis_ids(output.getvalue())
