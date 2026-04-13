from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

import pandas as pd

from services.fundonet_dashboard import FundonetDashboardData


ORANGE = "#ff5a00"
BLACK = "#111111"
GRAY = "#6e6e6e"
LIGHT_GRAY = "#eef2f6"
SERIES_COLORS = [ORANGE, BLACK, "#6e6e6e", "#c9864a", "#b8b8b8"]


def build_dashboard_pptx_bytes(
    dashboard: FundonetDashboardData,
    *,
    generated_at: datetime | None = None,
) -> bytes:
    try:
        from pptx import Presentation
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_DATA_LABEL_POSITION, XL_LEGEND_POSITION
        from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
        from pptx.enum.text import PP_ALIGN
        from pptx.util import Inches, Pt
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Dependência python-pptx não instalada.") from exc

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    now = generated_at or datetime.now()

    def rgb(hex_color: str):  # noqa: ANN202
        value = hex_color.lstrip("#")
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))

    def add_textbox(slide, left, top, width, height, text: str, *, size: int, bold: bool = False, color: str = BLACK, align=PP_ALIGN.LEFT):  # noqa: ANN001
        box = slide.shapes.add_textbox(left, top, width, height)
        frame = box.text_frame
        frame.clear()
        p = frame.paragraphs[0]
        p.text = text
        p.alignment = align
        run = p.runs[0]
        run.font.name = "IBM Plex Sans"
        run.font.size = Pt(size)
        run.font.bold = bold
        r, g, b = rgb(color)
        run.font.color.rgb = __import__("pptx.dml.color", fromlist=["RGBColor"]).RGBColor(r, g, b)
        return box

    def add_card(slide, left, top, width, height, label: str, value: str, note: str = ""):  # noqa: ANN001
        shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, left, top, width, height)
        fill = shape.fill
        fill.solid()
        r, g, b = rgb("#ffffff")
        fill.fore_color.rgb = __import__("pptx.dml.color", fromlist=["RGBColor"]).RGBColor(r, g, b)
        shape.line.color.rgb = __import__("pptx.dml.color", fromlist=["RGBColor"]).RGBColor(*rgb(LIGHT_GRAY))
        add_textbox(slide, left + Inches(0.10), top + Inches(0.05), width - Inches(0.2), Inches(0.25), label, size=10, bold=True, color=GRAY)
        add_textbox(slide, left + Inches(0.10), top + Inches(0.30), width - Inches(0.2), Inches(0.35), value, size=20, bold=True, color=BLACK)
        if note:
            add_textbox(slide, left + Inches(0.10), top + Inches(0.70), width - Inches(0.2), Inches(0.25), note, size=8, color=GRAY)

    def add_table(slide, df: pd.DataFrame, left, top, width, height, *, title: str):  # noqa: ANN001
        add_textbox(slide, left, top - Inches(0.22), width, Inches(0.2), title, size=14, bold=True, color=BLACK)
        frame = df.copy()
        rows, cols = frame.shape
        table = slide.shapes.add_table(rows + 1, cols, left, top, width, height).table
        for index, column in enumerate(frame.columns):
            cell = table.cell(0, index)
            cell.text = str(column)
            cell.fill.solid()
            cell.fill.fore_color.rgb = __import__("pptx.dml.color", fromlist=["RGBColor"]).RGBColor(*rgb(LIGHT_GRAY))
        for row_index, (_, row) in enumerate(frame.iterrows(), start=1):
            for col_index, value in enumerate(row):
                table.cell(row_index, col_index).text = str(value)
        for row_index in range(rows + 1):
            for col_index in range(cols):
                cell = table.cell(row_index, col_index)
                for paragraph in cell.text_frame.paragraphs:
                    for run in paragraph.runs:
                        run.font.name = "IBM Plex Sans"
                        run.font.size = Pt(8 if row_index else 9)
                        run.font.bold = row_index == 0
        return table

    def add_chart(  # noqa: ANN001
        slide,
        *,
        title: str,
        chart_type,
        categories: list[str],
        series_map: list[tuple[str, list[float]]],
        left,
        top,
        width,
        height,
        number_format: str,
        stacked: bool = False,
        percent_axis: bool = False,
        label_position=None,
    ):
        add_textbox(slide, left, top - Inches(0.22), width, Inches(0.2), title, size=14, bold=True, color=BLACK)
        data = CategoryChartData()
        data.categories = categories
        for name, values in series_map:
            data.add_series(name, tuple(values))
        frame = slide.shapes.add_chart(chart_type, left, top, width, height, data)
        chart = frame.chart
        chart.has_legend = len(series_map) > 1
        if chart.has_legend:
            chart.legend.include_in_layout = False
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        plot = chart.plots[0]
        plot.has_data_labels = True
        labels = plot.data_labels
        labels.number_format = number_format
        labels.show_value = True
        labels.font.name = "IBM Plex Sans"
        labels.font.size = Pt(8)
        if label_position is not None:
            labels.position = label_position
        if hasattr(chart, "value_axis"):
            chart.value_axis.has_major_gridlines = True
            chart.value_axis.format.line.color.rgb = __import__("pptx.dml.color", fromlist=["RGBColor"]).RGBColor(*rgb(LIGHT_GRAY))
            chart.value_axis.tick_labels.font.name = "IBM Plex Sans"
            chart.value_axis.tick_labels.font.size = Pt(9)
            if percent_axis:
                chart.value_axis.maximum_scale = 110.0
                chart.value_axis.minimum_scale = 0.0
        if hasattr(chart, "category_axis"):
            chart.category_axis.tick_labels.font.name = "IBM Plex Sans"
            chart.category_axis.tick_labels.font.size = Pt(9)
        for index, series in enumerate(chart.series):
            fill = series.format.fill
            fill.solid()
            fill.fore_color.rgb = __import__("pptx.dml.color", fromlist=["RGBColor"]).RGBColor(*rgb(SERIES_COLORS[index % len(SERIES_COLORS)]))
            line = series.format.line
            line.color.rgb = __import__("pptx.dml.color", fromlist=["RGBColor"]).RGBColor(*rgb(SERIES_COLORS[index % len(SERIES_COLORS)]))
        return chart

    def competencia_labels(df: pd.DataFrame) -> list[str]:
        labels = []
        for competencia in df["competencia"].tolist():
            text = str(competencia or "")
            if "/" in text:
                month, year = text.split("/", 1)
                month_map = {
                    "01": "jan", "02": "fev", "03": "mar", "04": "abr", "05": "mai", "06": "jun",
                    "07": "jul", "08": "ago", "09": "set", "10": "out", "11": "nov", "12": "dez",
                }
                labels.append(f"{month_map.get(month, month)}-{year[-2:]}")
            else:
                labels.append(text)
        return labels

    def pct_series(df: pd.DataFrame, value_column: str) -> list[float]:
        return [float(value) if pd.notna(value) else 0.0 for value in pd.to_numeric(df[value_column], errors="coerce").fillna(0.0)]

    def latest_aging_table() -> pd.DataFrame:
        frame = dashboard.default_buckets_latest_df.copy()
        if frame.empty:
            return pd.DataFrame({"Faixa": ["Sem dados"], "Valor": [""], "%": [""]})
        frame = frame[frame["ordem"] <= 7].copy()
        frame["Valor"] = frame["valor"].map(_format_brl_compact)
        frame["%"] = frame["percentual"].map(_format_percent)
        return frame[["faixa", "Valor", "%"]].rename(columns={"faixa": "Faixa"})

    def latest_events_table() -> pd.DataFrame:
        frame = dashboard.event_summary_latest_df.copy()
        if frame.empty:
            return pd.DataFrame({"Evento": ["Sem dados"], "Valor bruto": [""], "% PL": [""]})
        frame["Evento"] = frame["evento"]
        frame["Valor bruto"] = frame["valor_total"].map(_format_brl_compact)
        frame["% PL"] = frame["valor_total_pct_pl"].map(_format_percent)
        return frame[["Evento", "Valor bruto", "% PL"]]

    def latest_maturity_frame() -> pd.DataFrame:
        frame = dashboard.maturity_latest_df.copy()
        if frame.empty:
            return pd.DataFrame(columns=["faixa", "valor"])
        frame["valor"] = pd.to_numeric(frame["valor"], errors="coerce").fillna(0.0)
        return frame[frame["valor"] > 0].copy()

    # Slide 1
    slide = prs.slides.add_slide(blank)
    add_textbox(slide, Inches(0.55), Inches(0.40), Inches(8.8), Inches(0.5), "Informe Mensal Estruturado", size=24, bold=True)
    add_textbox(slide, Inches(0.55), Inches(0.95), Inches(11.8), Inches(0.35), _fund_title(dashboard), size=18, bold=True, color=ORANGE)
    subtitle = (
        f"Última competência: {_format_competencia(dashboard.latest_competencia)}"
        f"  |  Janela: {dashboard.fund_info.get('periodo_analisado', 'N/D')}"
        f"  |  Gerado em {now.strftime('%d/%m/%Y %H:%M')}"
    )
    add_textbox(slide, Inches(0.55), Inches(1.35), Inches(11.8), Inches(0.3), subtitle, size=10, color=GRAY)

    metrics = [
        ("PL total", _format_brl_compact(dashboard.summary.get("pl_total")), ""),
        ("Direitos creditórios", _format_brl_compact(dashboard.summary.get("inadimplencia_denominador") or dashboard.summary.get("direitos_creditorios")), ""),
        ("Inadimplência", _format_percent(dashboard.summary.get("inadimplencia_pct")), "créditos vencidos / base observável"),
        ("Cobertura de provisão", _format_percent(_safe_pct(dashboard.summary.get("provisao_total"), dashboard.summary.get("inadimplencia_total"))), "provisão / vencidos"),
        ("Subordinação", _format_percent(dashboard.summary.get("subordinacao_pct")), ""),
        ("Cotistas", str(dashboard.fund_info.get("total_cotistas") or "N/D"), ""),
    ]
    for index, (label, value, note) in enumerate(metrics):
        row = index // 3
        col = index % 3
        add_card(
            slide,
            Inches(0.55 + (col * 4.15)),
            Inches(1.9 + (row * 1.35)),
            Inches(3.75),
            Inches(1.0),
            label,
            value,
            note,
        )
    add_textbox(
        slide,
        Inches(0.55),
        Inches(5.2),
        Inches(12.0),
        Inches(1.0),
        "Deck executivo gerado a partir do dashboard carregado. Métricas de crédito priorizam a malha de vencimento dos direitos creditórios; cobertura, gatilhos e covenants exigem documentação complementar.",
        size=10,
        color=GRAY,
    )

    # Slide 2
    slide = prs.slides.add_slide(blank)
    add_textbox(slide, Inches(0.55), Inches(0.35), Inches(12.0), Inches(0.35), "Crédito", size=22, bold=True)
    default_df = dashboard.default_history_df.sort_values("competencia_dt").copy()
    if not default_df.empty:
        labels = competencia_labels(default_df)
        direitos = pd.to_numeric(default_df["direitos_creditorios"], errors="coerce")
        provisao = pd.to_numeric(default_df["provisao_total"], errors="coerce")
        provisao_pct_direitos = (provisao / direitos).where(direitos > 0).mul(100.0).fillna(0.0)
        add_chart(
            slide,
            title="Crédito problemático (% dos direitos creditórios)",
            chart_type=XL_CHART_TYPE.LINE_MARKERS,
            categories=labels,
            series_map=[
                ("Inadimplência", pct_series(default_df, "inadimplencia_pct")),
                ("Provisão", [float(value) for value in provisao_pct_direitos.tolist()]),
            ],
            left=Inches(0.55),
            top=Inches(0.95),
            width=Inches(7.3),
            height=Inches(2.55),
            number_format='0.0"%"',
            percent_axis=True,
            label_position=XL_DATA_LABEL_POSITION.ABOVE,
        )
    add_table(
        slide,
        latest_aging_table().head(7),
        Inches(8.15),
        Inches(1.0),
        Inches(4.55),
        Inches(2.65),
        title="Aging da inadimplência",
    )

    # Slide 3
    slide = prs.slides.add_slide(blank)
    add_textbox(slide, Inches(0.55), Inches(0.35), Inches(12.0), Inches(0.35), "Estrutura e cotas", size=22, bold=True)
    sub_df = dashboard.subordination_history_df.sort_values("competencia_dt").copy()
    if not sub_df.empty:
        add_chart(
            slide,
            title="Índice de subordinação",
            chart_type=XL_CHART_TYPE.COLUMN_CLUSTERED,
            categories=competencia_labels(sub_df),
            series_map=[("Subordinação", pct_series(sub_df, "subordinacao_pct"))],
            left=Inches(0.55),
            top=Inches(0.95),
            width=Inches(5.8),
            height=Inches(2.55),
            number_format='0.0"%"',
            percent_axis=True,
            label_position=XL_DATA_LABEL_POSITION.OUTSIDE_END,
        )
    share_df = dashboard.quota_pl_history_df.copy()
    if not share_df.empty:
        share_df["pl"] = pd.to_numeric(share_df["pl"], errors="coerce").fillna(0.0)
        totals = share_df.groupby("competencia", dropna=False)["pl"].transform("sum")
        share_df["share_pct"] = (share_df["pl"] / totals).where(totals > 0).mul(100.0).fillna(0.0)
        pivot = share_df.pivot_table(index="competencia", columns="label", values="share_pct", aggfunc="sum").fillna(0.0)
        add_chart(
            slide,
            title="PL por tipo de cota (% do total)",
            chart_type=XL_CHART_TYPE.COLUMN_STACKED_100,
            categories=competencia_labels(pivot.reset_index()),
            series_map=[(str(column), [float(v) for v in pivot[column].tolist()]) for column in pivot.columns],
            left=Inches(6.65),
            top=Inches(0.95),
            width=Inches(6.0),
            height=Inches(2.55),
            number_format='0.0"%"',
            percent_axis=True,
            label_position=XL_DATA_LABEL_POSITION.CENTER,
        )
    latest_quota = dashboard.quota_pl_history_df[dashboard.quota_pl_history_df["competencia"] == dashboard.latest_competencia].copy()
    if latest_quota.empty:
        latest_quota_table = pd.DataFrame({"Classe": ["Sem dados"], "PL": [""]})
    else:
        latest_quota["Classe"] = latest_quota["label"]
        latest_quota["PL"] = latest_quota["pl"].map(_format_brl_compact)
        latest_quota["Qt. cotas"] = latest_quota["qt_cotas"].map(_format_decimal_0_or_2)
        latest_quota_table = latest_quota[["Classe", "Qt. cotas", "PL"]]
    add_table(
        slide,
        latest_quota_table.head(8),
        Inches(0.55),
        Inches(3.9),
        Inches(5.8),
        Inches(2.35),
        title="Quadro de cotas na última competência",
    )

    # Slide 4
    slide = prs.slides.add_slide(blank)
    add_textbox(slide, Inches(0.55), Inches(0.35), Inches(12.0), Inches(0.35), "Eventos e vencimento", size=22, bold=True)
    maturity_df = latest_maturity_frame()
    if not maturity_df.empty:
        add_chart(
            slide,
            title=f"Vencimento dos direitos creditórios em {_format_competencia(dashboard.latest_competencia)}",
            chart_type=XL_CHART_TYPE.COLUMN_CLUSTERED,
            categories=[str(value) for value in maturity_df["faixa"].tolist()],
            series_map=[("Valor", [float(value) for value in maturity_df["valor"].tolist()])],
            left=Inches(0.55),
            top=Inches(0.95),
            width=Inches(7.2),
            height=Inches(2.65),
            number_format='#,##0',
            label_position=XL_DATA_LABEL_POSITION.OUTSIDE_END,
        )
    add_table(
        slide,
        latest_events_table().head(8),
        Inches(8.0),
        Inches(1.0),
        Inches(4.7),
        Inches(2.6),
        title="Eventos de cotas",
    )
    vencidos = _to_float(dashboard.summary.get("direitos_creditorios_vencidos"))
    base = _to_float(dashboard.summary.get("inadimplencia_denominador"))
    add_textbox(
        slide,
        Inches(0.55),
        Inches(4.0),
        Inches(12.0),
        Inches(0.6),
        f"Vencidos observáveis: {_format_brl_compact(vencidos)}  |  Base observável: {_format_brl_compact(base)}  |  Razão: {_format_percent(_safe_pct(vencidos, base))}",
        size=11,
        color=GRAY,
    )

    buffer = BytesIO()
    prs.save(buffer)
    return buffer.getvalue()


def _fund_title(dashboard: FundonetDashboardData) -> str:
    return str(dashboard.fund_info.get("nome_fundo") or dashboard.fund_info.get("nome_classe") or "FIDC selecionado")


def _format_competencia(value: object) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and "/" in text:
        month, year = text.split("/", 1)
        month_map = {
            "01": "jan", "02": "fev", "03": "mar", "04": "abr", "05": "mai", "06": "jun",
            "07": "jul", "08": "ago", "09": "set", "10": "out", "11": "nov", "12": "dez",
        }
        return f"{month_map.get(month, month)}-{year[-2:]}"
    return text or "N/D"


def _to_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_pct(numerator: object, denominator: object) -> float | None:
    num = _to_float(numerator)
    den = _to_float(denominator)
    if num is None or den is None or den <= 0:
        return None
    return num / den * 100.0


def _format_decimal(value: object, *, decimals: int = 2) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/D"
    return f"{numeric:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_decimal_0_or_2(value: object) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/D"
    decimals = 0 if float(numeric).is_integer() else 2
    return _format_decimal(numeric, decimals=decimals)


def _format_percent(value: object) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/D"
    return f"{_format_decimal(numeric, decimals=1)}%"


def _format_brl_compact(value: object) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/D"
    magnitude = abs(numeric)
    if magnitude >= 1_000_000_000:
        return f"R$ {_format_decimal(numeric / 1_000_000_000, decimals=2)} bi"
    if magnitude >= 1_000_000:
        return f"R$ {_format_decimal(numeric / 1_000_000, decimals=1)} mm"
    return f"R$ {_format_decimal(numeric, decimals=2)}"
