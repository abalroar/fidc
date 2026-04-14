from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from services.fundonet_dashboard import FundonetDashboardData


ORANGE = "#ff5a00"
BLACK = "#111111"
DARK_GRAY = "#353535"
MID_GRAY = "#666666"
GRID_GRAY = "#d7dce3"
SOFT_GRAY = "#f5f6f8"
WHITE = "#ffffff"
SERIES_COLORS = [BLACK, ORANGE, DARK_GRAY, "#8a8a8a", "#b24f19"]
OVER_PPT_COLORS = ["#2f7d4a", "#8abc4a", "#f0c340", "#ea8c2d", "#c8562c", "#7b241c"]
AGING_PPT_COLORS = [
    "#27ae60",
    "#82ca3f",
    "#f9ca24",
    "#f0932b",
    "#ef7c1a",
    "#e55039",
    "#c0392b",
    "#943126",
    "#7b241c",
    "#4a1310",
]
COVERAGE_LINE_COLOR = "#0f172a"

SLIDE_WIDTH_IN = 13.333
SLIDE_HEIGHT_IN = 7.5
MARGIN_LEFT_IN = 0.45
MARGIN_RIGHT_IN = 0.45
CONTENT_WIDTH_IN = SLIDE_WIDTH_IN - MARGIN_LEFT_IN - MARGIN_RIGHT_IN

TITLE_SIZE = 24
SECTION_SIZE = 13
BODY_SIZE = 9
LABEL_SIZE = 9
AXIS_SIZE = 9
FOOTER_SIZE = 8
CARD_VALUE_SIZE = 17


@dataclass(frozen=True)
class MoneyScale:
    divisor: float
    suffix: str
    label: str


def build_dashboard_pptx_bytes(
    dashboard: FundonetDashboardData,
    *,
    generated_at: datetime | None = None,
    requested_period_label: str | None = None,
) -> bytes:
    try:
        from pptx import Presentation
        from pptx.chart.data import CategoryChartData
        from pptx.dml.color import RGBColor
        from pptx.enum.chart import XL_CHART_TYPE, XL_DATA_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE
        from pptx.enum.dml import MSO_LINE_DASH_STYLE
        from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
        from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
        from pptx.util import Inches, Pt
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Dependência python-pptx não instalada.") from exc

    sao_paulo_tz = ZoneInfo("America/Sao_Paulo")
    if generated_at is None:
        generated_at = datetime.now(sao_paulo_tz)
    elif generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=sao_paulo_tz)
    else:
        generated_at = generated_at.astimezone(sao_paulo_tz)
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_WIDTH_IN)
    prs.slide_height = Inches(SLIDE_HEIGHT_IN)
    blank = prs.slide_layouts[6]

    def rgb(hex_color: str) -> RGBColor:
        value = str(hex_color or BLACK).strip().lstrip("#")
        return RGBColor(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))

    def add_textbox(  # noqa: ANN202
        slide,
        left: float,
        top: float,
        width: float,
        height: float,
        text: str,
        *,
        size: int,
        bold: bool = False,
        color: str = BLACK,
        align=PP_ALIGN.LEFT,
    ):
        box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        frame = box.text_frame
        frame.clear()
        frame.word_wrap = True
        frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        paragraph = frame.paragraphs[0]
        paragraph.alignment = align
        run = paragraph.add_run()
        run.text = text
        run.font.name = "IBM Plex Sans"
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = rgb(color)
        return box

    def style_shape_border(shape, *, line_color: str = GRID_GRAY, line_width_pt: float = 0.8) -> None:  # noqa: ANN001
        shape.line.color.rgb = rgb(line_color)
        shape.line.width = Pt(line_width_pt)

    def add_panel(slide, left: float, top: float, width: float, height: float):  # noqa: ANN001
        shape = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
            Inches(left),
            Inches(top),
            Inches(width),
            Inches(height),
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = rgb(WHITE)
        style_shape_border(shape)
        return shape

    def add_card(slide, left: float, top: float, width: float, height: float, label: str, value: str, note: str = "") -> None:
        panel = add_panel(slide, left, top, width, height)
        style_shape_border(panel, line_color=GRID_GRAY, line_width_pt=0.7)
        accent = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.RECTANGLE,
            Inches(left),
            Inches(top),
            Inches(width),
            Inches(0.04),
        )
        accent.fill.solid()
        accent.fill.fore_color.rgb = rgb(ORANGE)
        accent.line.fill.background()
        add_textbox(slide, left + 0.10, top + 0.08, width - 0.20, 0.20, label, size=BODY_SIZE, bold=True, color=MID_GRAY)
        add_textbox(slide, left + 0.10, top + 0.30, width - 0.20, 0.28, value, size=CARD_VALUE_SIZE, bold=True, color=BLACK)
        if note:
            add_textbox(slide, left + 0.10, top + 0.67, width - 0.20, 0.18, note, size=LABEL_SIZE, color=MID_GRAY)

    def add_footer(slide, timestamp_text: str) -> None:  # noqa: ANN001
        add_textbox(
            slide,
            MARGIN_LEFT_IN,
            7.08,
            CONTENT_WIDTH_IN,
            0.18,
            f"Fonte: Informe Mensal - CVM    |    Gerado em: {timestamp_text}",
            size=FOOTER_SIZE,
            color=MID_GRAY,
        )

    def set_table_style(table, *, header_fill: str = BLACK) -> None:  # noqa: ANN001
        for row_idx in range(len(table.rows)):
            for col_idx in range(len(table.columns)):
                cell = table.cell(row_idx, col_idx)
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(header_fill if row_idx == 0 else WHITE)
                cell.text_frame.word_wrap = True
                for paragraph in cell.text_frame.paragraphs:
                    paragraph.alignment = PP_ALIGN.LEFT
                    for run in paragraph.runs:
                        run.font.name = "IBM Plex Sans"
                        run.font.size = Pt(LABEL_SIZE if row_idx == 0 else BODY_SIZE)
                        run.font.bold = row_idx == 0
                        run.font.color.rgb = rgb(WHITE if row_idx == 0 else BLACK)
                cell.margin_left = Inches(0.05)
                cell.margin_right = Inches(0.05)
                cell.margin_top = Inches(0.02)
                cell.margin_bottom = Inches(0.02)

    def add_table(  # noqa: ANN202
        slide,
        df: pd.DataFrame,
        *,
        title: str | None,
        left: float,
        top: float,
        width: float,
        height: float,
        col_widths: Sequence[float] | None = None,
    ):
        if title:
            add_textbox(slide, left, top - 0.22, width, 0.18, title, size=SECTION_SIZE, bold=True, color=BLACK)
        frame = df.copy()
        rows = max(len(frame.index), 1)
        cols = max(len(frame.columns), 1)
        table = slide.shapes.add_table(rows + 1, cols, Inches(left), Inches(top), Inches(width), Inches(height)).table
        if col_widths and len(col_widths) == cols:
            for idx, col_width in enumerate(col_widths):
                table.columns[idx].width = Inches(col_width)
        if frame.empty:
            table.cell(0, 0).text = "Sem dados"
            table.cell(1, 0).text = "-"
            set_table_style(table)
            return table
        for col_idx, column in enumerate(frame.columns):
            table.cell(0, col_idx).text = str(column)
        for row_idx, (_, row) in enumerate(frame.iterrows(), start=1):
            for col_idx, value in enumerate(row):
                table.cell(row_idx, col_idx).text = str(value)
        set_table_style(table)
        return table

    def add_manual_legend(
        slide,
        items: Sequence[tuple[str, str]],
        *,
        left: float,
        top: float,
        max_width: float,
    ) -> None:
        cursor_left = left
        for label, color in items:
            label_width = max(0.55, min(1.8, 0.10 + (len(label) * 0.06)))
            if cursor_left + label_width + 0.35 > left + max_width:
                top += 0.18
                cursor_left = left
            marker = slide.shapes.add_shape(
                MSO_AUTO_SHAPE_TYPE.RECTANGLE,
                Inches(cursor_left),
                Inches(top + 0.02),
                Inches(0.18),
                Inches(0.05),
            )
            marker.fill.solid()
            marker.fill.fore_color.rgb = rgb(color)
            marker.line.fill.background()
            add_textbox(slide, cursor_left + 0.22, top - 0.02, label_width, 0.14, label, size=LABEL_SIZE, color=DARK_GRAY)
            cursor_left += label_width + 0.45

    def _data_label_position(position_name: str):  # noqa: ANN202
        mapping = {
            "above": XL_DATA_LABEL_POSITION.ABOVE,
            "outside_end": XL_DATA_LABEL_POSITION.OUTSIDE_END,
            "center": XL_DATA_LABEL_POSITION.CENTER,
            "inside_end": XL_DATA_LABEL_POSITION.INSIDE_END,
        }
        return mapping[position_name]

    def add_chart(  # noqa: ANN202
        slide,
        *,
        title: str | None,
        chart_type,
        categories: Sequence[str],
        series_map: Sequence[tuple[str, Sequence[float]]],
        left: float,
        top: float,
        width: float,
        height: float,
        number_format: str,
        percent_axis: bool = False,
        money_axis: bool = False,
        gap_width: int | None = None,
        overlap: int | None = None,
        label_position: str = "above",
        label_color: str = BLACK,
        label_font_size: int = LABEL_SIZE,
        series_colors: Sequence[str] | None = None,
        title_suffix: str = "",
        value_max: float | None = None,
        value_min: float | None = None,
        show_data_labels: bool = True,
        show_legend: bool = False,
    ):
        if title:
            add_textbox(slide, left, top - 0.22, width, 0.18, f"{title}{title_suffix}", size=SECTION_SIZE, bold=True, color=BLACK)
        chart_data = CategoryChartData()
        chart_data.categories = list(categories)
        for series_name, values in series_map:
            chart_data.add_series(series_name, tuple(values))
        chart_shape = slide.shapes.add_chart(chart_type, Inches(left), Inches(top), Inches(width), Inches(height), chart_data)
        chart = chart_shape.chart
        chart.has_legend = show_legend
        if show_legend and chart.legend is not None:
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            if hasattr(chart.legend, "include_in_layout"):
                chart.legend.include_in_layout = True

        plot = chart.plots[0]
        if gap_width is not None and hasattr(plot, "gap_width"):
            plot.gap_width = gap_width
        if overlap is not None and hasattr(plot, "overlap"):
            plot.overlap = overlap
        plot.has_data_labels = show_data_labels
        if show_data_labels:
            labels = plot.data_labels
            labels.show_value = True
            labels.number_format = number_format
            labels.position = _data_label_position(label_position)
            labels.font.name = "IBM Plex Sans"
            labels.font.size = Pt(label_font_size)
            labels.font.bold = True
            labels.font.color.rgb = rgb(label_color)

        if hasattr(chart, "category_axis"):
            chart.category_axis.tick_labels.font.name = "IBM Plex Sans"
            chart.category_axis.tick_labels.font.size = Pt(AXIS_SIZE)
            chart.category_axis.format.line.color.rgb = rgb(GRID_GRAY)
        if hasattr(chart, "value_axis"):
            chart.value_axis.tick_labels.font.name = "IBM Plex Sans"
            chart.value_axis.tick_labels.font.size = Pt(AXIS_SIZE)
            chart.value_axis.has_major_gridlines = True
            chart.value_axis.major_gridlines.format.line.color.rgb = rgb(GRID_GRAY)
            chart.value_axis.format.line.color.rgb = rgb(GRID_GRAY)
            if value_min is not None:
                chart.value_axis.minimum_scale = value_min
            if value_max is not None:
                chart.value_axis.maximum_scale = value_max
            if percent_axis:
                if value_min is None:
                    chart.value_axis.minimum_scale = 0.0
                if value_max is None:
                    chart.value_axis.maximum_scale = 110.0
            if money_axis:
                if value_min is None:
                    chart.value_axis.minimum_scale = 0.0

        applied_colors = list(series_colors or SERIES_COLORS)
        for idx, series in enumerate(chart.series):
            fill = series.format.fill
            fill.solid()
            fill.fore_color.rgb = rgb(applied_colors[idx % len(applied_colors)])
            series.format.line.color.rgb = rgb(applied_colors[idx % len(applied_colors)])
            if show_data_labels and hasattr(series, "data_labels"):
                series.data_labels.show_value = True
                series.data_labels.number_format = number_format
                series.data_labels.position = _data_label_position(label_position)
                series.data_labels.font.name = "IBM Plex Sans"
                series.data_labels.font.size = Pt(label_font_size)
                series.data_labels.font.bold = True
                series.data_labels.font.color.rgb = rgb(label_color)

        return chart

    def _first_axis_element(chart, axis_name: str):  # noqa: ANN202
        plot_area = chart._chartSpace.xpath("./c:chart/c:plotArea")
        if not plot_area:
            return None
        matches = plot_area[0].xpath(f"./c:{axis_name}")
        return matches[0] if matches else None

    def _set_axis_hidden(chart, axis_name: str, hidden: bool) -> None:  # noqa: ANN001
        axis = _first_axis_element(chart, axis_name)
        if axis is None:
            return
        delete_nodes = axis.xpath("./c:delete")
        if delete_nodes:
            delete_nodes[0].set("val", "1" if hidden else "0")

    def _set_value_axis_right(chart) -> None:  # noqa: ANN001
        val_axis = _first_axis_element(chart, "valAx")
        cat_axis = _first_axis_element(chart, "catAx")
        if val_axis is not None:
            ax_pos = val_axis.xpath("./c:axPos")
            if ax_pos:
                ax_pos[0].set("val", "r")
        if cat_axis is not None:
            crosses = cat_axis.xpath("./c:crosses")
            if crosses:
                crosses[0].set("val", "max")

    def _style_line_series(
        series,  # noqa: ANN001
        *,
        color: str,
        width_pt: float = 2.5,
        marker_size: int | None = None,
        dashed: bool = False,
        hide_marker: bool = False,
    ) -> None:
        series.format.line.color.rgb = rgb(color)
        series.format.line.width = Pt(width_pt)
        if dashed:
            series.format.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        if hide_marker:
            series.marker.style = XL_MARKER_STYLE.NONE
        else:
            series.marker.style = XL_MARKER_STYLE.CIRCLE
            if marker_size is not None:
                series.marker.size = marker_size
            series.marker.format.fill.solid()
            series.marker.format.fill.fore_color.rgb = rgb(color)
            series.marker.format.line.color.rgb = rgb(color)

    def _repel_label_positions(values: Sequence[float], min_gap: float) -> list[float]:
        indexed = sorted(enumerate(values), key=lambda item: item[1])
        if not indexed:
            return []
        adjusted: dict[int, float] = {}
        previous: float | None = None
        for idx, value in indexed:
            candidate = value if previous is None else max(value, previous + min_gap)
            adjusted[idx] = candidate
            previous = candidate
        return [adjusted[idx] for idx in range(len(values))]

    def add_line_end_labels(
        slide,
        *,
        labels: Sequence[str],
        values: Sequence[float],
        colors: Sequence[str],
        left: float,
        top: float,
        width: float,
        height: float,
        axis_max: float,
        axis_min: float = 0.0,
        font_size: int = 11,
        fill_colors: Sequence[str] | None = None,
        text_colors: Sequence[str] | None = None,
    ) -> None:
        numeric_values = [float(value) for value in values]
        plot_top = top + 0.22
        plot_height = max(height - 0.58, 0.1)
        plot_right = left + width - 0.38
        value_span = max(axis_max - axis_min, 1.0)
        raw_positions = [
            plot_top + plot_height * (1.0 - ((value - axis_min) / value_span))
            for value in numeric_values
        ]
        adjusted_positions = _repel_label_positions(raw_positions, min_gap=0.18)
        for idx, label in enumerate(labels):
            label_width = max(0.92, min(1.90, 0.34 + len(str(label)) * 0.10))
            label_left = min(plot_right, left + width - label_width - 0.10)
            label_top = max(top + 0.02, adjusted_positions[idx] - 0.10)
            fill_color = fill_colors[idx % len(fill_colors)] if fill_colors else None
            if fill_color:
                badge = slide.shapes.add_shape(
                    MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
                    Inches(label_left),
                    Inches(label_top - 0.02),
                    Inches(label_width),
                    Inches(0.26),
                )
                badge.fill.solid()
                badge.fill.fore_color.rgb = rgb(fill_color)
                badge.line.fill.background()
            add_textbox(
                slide,
                label_left,
                label_top,
                label_width,
                0.20,
                label,
                size=font_size,
                bold=True,
                color=(text_colors[idx % len(text_colors)] if text_colors else colors[idx % len(colors)]),
                align=PP_ALIGN.CENTER,
            )

    def add_overlay_combo_credit_chart(
        slide,
        *,
        categories: Sequence[str],
        bar_series_map: Sequence[tuple[str, Sequence[float]]],
        line_series_map: Sequence[tuple[str, Sequence[float]]],
        left: float,
        top: float,
        width: float,
        height: float,
    ) -> None:
        bar_axis_max = _percent_axis_max(bar_series_map, cap=120.0)
        line_axis_max = _percent_axis_max(
            line_series_map,
            cap=max(
                650.0,
                max([max([float(v) for v in values if v is not None], default=0.0) for _, values in line_series_map]) * 1.18
                if line_series_map
                else 120.0,
            ),
        )
        bar_chart = add_chart(
            slide,
            title=None,
            chart_type=XL_CHART_TYPE.COLUMN_CLUSTERED,
            categories=categories,
            series_map=bar_series_map,
            left=left,
            top=top,
            width=width,
            height=height,
            number_format='0.0"%"',
            percent_axis=True,
            gap_width=42,
            label_position="outside_end",
            label_font_size=10,
            show_legend=True,
            value_max=bar_axis_max,
        )
        line_chart = add_chart(
            slide,
            title=None,
            chart_type=XL_CHART_TYPE.LINE_MARKERS,
            categories=categories,
            series_map=line_series_map,
            left=left,
            top=top,
            width=width,
            height=height,
            number_format='0.0"%"',
            percent_axis=True,
            label_position="above",
            label_font_size=9,
            value_max=line_axis_max,
            show_data_labels=False,
            show_legend=False,
        )
        _set_axis_hidden(line_chart, "catAx", True)
        _set_value_axis_right(line_chart)
        _set_axis_hidden(bar_chart, "valAx", False)
        if hasattr(line_chart, "value_axis"):
            line_chart.value_axis.tick_labels.font.name = "IBM Plex Sans"
            line_chart.value_axis.tick_labels.font.size = Pt(AXIS_SIZE)
            line_chart.value_axis.has_major_gridlines = False
            line_chart.value_axis.format.line.color.rgb = rgb(GRID_GRAY)
        if len(line_chart.series) >= 1:
            _style_line_series(
                line_chart.series[0],
                color=COVERAGE_LINE_COLOR,
                width_pt=3.0,
                marker_size=12,
            )
        if len(line_chart.series) >= 2:
            _style_line_series(
                line_chart.series[1],
                color=MID_GRAY,
                width_pt=1.8,
                dashed=True,
                hide_marker=True,
            )
        coverage_values = [float(value) for value in line_series_map[0][1] if value is not None] if line_series_map else []
        if coverage_values:
            add_line_end_labels(
                slide,
                labels=[_format_percent(coverage_values[-1])],
                values=[coverage_values[-1]],
                colors=[COVERAGE_LINE_COLOR],
                fill_colors=[COVERAGE_LINE_COLOR],
                text_colors=[WHITE],
                left=left,
                top=top,
                width=width,
                height=height,
                axis_max=line_axis_max,
            )

    def add_compounding_waterfall_chart(
        slide,
        *,
        categories: Sequence[str],
        step_values: Sequence[float],
        total_value: float,
        left: float,
        top: float,
        width: float,
        height: float,
        number_format: str,
        value_max: float | None,
        title_suffix: str = "",
        label_font_size: int = 9,
    ) -> None:
        base_values: list[float] = []
        flow_values: list[float] = []
        total_series_values: list[float] = []
        cumulative = 0.0
        for idx, step_value in enumerate(step_values):
            numeric_value = float(step_value)
            base_values.append(cumulative)
            flow_values.append(numeric_value)
            total_series_values.append(0.0)
            cumulative += numeric_value
        base_values.append(0.0)
        flow_values.append(0.0)
        total_series_values.append(float(total_value))
        chart = add_chart(
            slide,
            title=f"Waterfall de vencimento da carteira{title_suffix}",
            chart_type=XL_CHART_TYPE.COLUMN_STACKED,
            categories=list(categories) + ["Total"],
            series_map=[
                ("Base", base_values),
                ("Fluxo", flow_values),
                ("Total", total_series_values),
            ],
            left=left,
            top=top,
            width=width,
            height=height,
            number_format=number_format,
            money_axis=True,
            gap_width=36,
            overlap=100,
            label_position="outside_end",
            label_font_size=label_font_size,
            value_max=value_max,
            show_data_labels=True,
            show_legend=False,
            series_colors=[WHITE, ORANGE, BLACK],
        )
        base_series = chart.series[0]
        base_series.format.fill.background()
        base_series.format.line.fill.background()
        if hasattr(base_series, "data_labels"):
            base_series.data_labels.show_value = False
        for idx in range(1, len(chart.series)):
            series = chart.series[idx]
            series.data_labels.font.bold = True
            series.data_labels.font.size = Pt(label_font_size)
            series.data_labels.font.color.rgb = rgb(BLACK if idx == 2 else DARK_GRAY)

    timestamp_text = f"{generated_at.strftime('%d/%m/%Y %H:%M')} GMT-3"
    title_fund = _fund_title(dashboard)

    # Slide 1 — overview + structural protection
    slide = prs.slides.add_slide(blank)
    add_textbox(slide, 0.45, 0.18, 6.2, 0.28, "Informe Mensal Estruturado", size=TITLE_SIZE, bold=True, color=BLACK)
    add_textbox(slide, 0.45, 0.48, 10.8, 0.22, title_fund, size=13, bold=True, color=ORANGE)
    requested_period_text = (
        f"  |  Janela solicitada: {requested_period_label}"
        if requested_period_label and requested_period_label != dashboard.fund_info.get("periodo_analisado")
        else ""
    )
    subtitle = (
        f"Última competência: {_format_competencia(dashboard.latest_competencia)}"
        f"  |  Janela carregada: {dashboard.fund_info.get('periodo_analisado', 'N/D')}"
        f"{requested_period_text}"
        f"  |  Cotistas: {dashboard.fund_info.get('total_cotistas') or 'N/D'}"
    )
    add_textbox(slide, 0.45, 0.72, 10.8, 0.16, subtitle, size=BODY_SIZE, color=MID_GRAY)
    cards = [
        ("PL total", _format_brl_compact(dashboard.summary.get("pl_total")), ""),
        ("Direitos creditórios", _format_brl_compact(dashboard.summary.get("inadimplencia_denominador") or dashboard.summary.get("direitos_creditorios")), ""),
        ("Inadimplência", _format_percent(dashboard.summary.get("inadimplencia_pct")), "vencidos / DC total"),
        ("Cobertura de provisão", _format_percent(dashboard.summary.get("cobertura_pct")), "provisão / inadimplência"),
        ("Subordinação", _format_percent(dashboard.summary.get("subordinacao_pct")), ""),
        ("Créditos vencidos", _format_brl_compact(dashboard.summary.get("direitos_creditorios_vencidos")), ""),
    ]
    for idx, (label, value, note) in enumerate(cards):
        add_card(slide, 0.45 + idx * 2.08, 1.02, 2.0, 0.95, label, value, note)
    sub_df = dashboard.subordination_history_df.sort_values("competencia_dt").copy()
    if not sub_df.empty:
        sub_series = [("Subordinação", _series_numeric(sub_df, "subordinacao_pct").fillna(0.0).tolist())]
        sub_chart = add_chart(
            slide,
            title="Índice de subordinação",
            chart_type=XL_CHART_TYPE.LINE_MARKERS,
            categories=_competencia_labels(sub_df["competencia"].tolist()),
            series_map=sub_series,
            left=MARGIN_LEFT_IN,
            top=2.35,
            width=CONTENT_WIDTH_IN,
            height=2.55,
            number_format='0.0"%"',
            percent_axis=True,
            label_position="above",
            show_data_labels=True,
            label_font_size=16,
            value_max=_percent_axis_max(sub_series, cap=80.0),
        )
        _style_line_series(sub_chart.series[0], color=ORANGE, width_pt=2.8, marker_size=12)
    structural_table = _risk_metrics_table_frame(dashboard.risk_metrics_df, "Risco estrutural")
    add_table(
        slide,
        structural_table,
        title="Métricas exibidas no bloco estrutural",
        left=MARGIN_LEFT_IN,
        top=5.28,
        width=CONTENT_WIDTH_IN,
        height=1.38,
        col_widths=[3.3, 1.5, 7.1],
    )
    add_footer(slide, timestamp_text)

    # Slide 2 — PL por classe
    slide = prs.slides.add_slide(blank)
    add_textbox(slide, 0.45, 0.18, 8.5, 0.28, "PL por tipo de cota", size=TITLE_SIZE, bold=True, color=BLACK)
    add_textbox(slide, 0.45, 0.46, 10.0, 0.16, "Visão padrão da aba: valores absolutos (R$) por competência, mantendo a mesma decomposição por classe.", size=BODY_SIZE, color=MID_GRAY)
    quota_values = _quota_pl_value_pivot(dashboard.quota_pl_history_df)
    if not quota_values.empty:
        quota_scale = _money_scale(quota_values.drop(columns=["competencia"]).stack())
        quota_series = [
            (column, _scale_values(quota_values[column], quota_scale).tolist())
            for column in quota_values.columns
            if column != "competencia"
        ]
        quota_chart = add_chart(
            slide,
            title=None,
            chart_type=XL_CHART_TYPE.COLUMN_STACKED,
            categories=_competencia_labels(quota_values["competencia"].tolist()),
            series_map=quota_series,
            left=MARGIN_LEFT_IN,
            top=0.82,
            width=CONTENT_WIDTH_IN,
            height=4.20,
            number_format=_money_label_number_format(quota_scale),
            money_axis=True,
            gap_width=48,
            overlap=100,
            label_position="center",
            label_color=WHITE,
            label_font_size=13,
            series_colors=SERIES_COLORS,
            value_min=0.0,
            value_max=_money_axis_max([value for _, values in quota_series for value in values]),
            show_legend=True,
        )
        for series in quota_chart.series:
            series.data_labels.font.color.rgb = rgb(WHITE)
    add_table(
        slide,
        _latest_quota_table_frame(dashboard.quota_pl_history_df, dashboard.latest_competencia),
        title=f"Quadro de cotas em {_format_competencia(dashboard.latest_competencia)}",
        left=MARGIN_LEFT_IN,
        top=5.38,
        width=CONTENT_WIDTH_IN,
        height=1.22,
        col_widths=[4.0, 3.4, 5.0],
    )
    add_footer(slide, timestamp_text)

    # Slide 3 — default, provision and coverage
    slide = prs.slides.add_slide(blank)
    add_textbox(slide, 0.45, 0.18, 10.0, 0.28, "Inadimplência, Provisão e Cobertura", size=TITLE_SIZE, bold=True, color=BLACK)
    add_textbox(
        slide,
        0.45,
        0.46,
        11.2,
        0.20,
        "Barras no eixo esquerdo: % dos DCs. Linha grossa no eixo direito: cobertura = provisão / inadimplência, com referência em 100%.",
        size=BODY_SIZE,
        color=MID_GRAY,
    )
    default_df = dashboard.default_history_df.sort_values("competencia_dt").copy()
    if not default_df.empty:
        categories = _competencia_labels(default_df["competencia"].tolist())
        add_overlay_combo_credit_chart(
            slide,
            categories=categories,
            bar_series_map=[
                ("Inadimplência", _series_numeric(default_df, "inadimplencia_pct").fillna(0.0).tolist()),
                ("Provisão", _series_numeric(default_df, "provisao_pct_direitos").fillna(0.0).tolist()),
            ],
            line_series_map=[
                ("Cobertura", _series_numeric(default_df, "cobertura_pct").fillna(0.0).tolist()),
                ("100% (paridade)", [100.0] * len(categories)),
            ],
            left=MARGIN_LEFT_IN,
            top=0.82,
            width=CONTENT_WIDTH_IN,
            height=4.18,
        )
    add_table(
        slide,
        _risk_metrics_table_frame(dashboard.risk_metrics_df, "Risco de crédito"),
        title="Métricas exibidas no bloco de crédito",
        left=MARGIN_LEFT_IN,
        top=5.40,
        width=CONTENT_WIDTH_IN,
        height=1.18,
        col_widths=[3.0, 1.6, 7.3],
    )
    add_footer(slide, timestamp_text)

    # Slide 4 — cumulative over curves
    slide = prs.slides.add_slide(blank)
    add_textbox(slide, 0.45, 0.18, 10.5, 0.28, "Inadimplência Over (somatório do aging)", size=TITLE_SIZE, bold=True, color=BLACK)
    add_textbox(
        slide,
        0.45,
        0.46,
        11.8,
        0.18,
        "Curvas cumulativas sobre a base canônica de direitos creditórios. Os rótulos finais usam a mesma cor da série e ficam à direita do último marker.",
        size=BODY_SIZE,
        color=MID_GRAY,
    )
    over_history = _build_over_aging_history_for_ppt(dashboard)
    if not over_history.empty:
        over_columns = [column for column in over_history.columns if column != "competencia"]
        over_series_map = [(column, over_history[column].tolist()) for column in over_columns]
        over_axis_max = _percent_axis_max(over_series_map, cap=120.0)
        over_chart = add_chart(
            slide,
            title=None,
            chart_type=XL_CHART_TYPE.LINE_MARKERS,
            categories=_competencia_labels(over_history["competencia"].tolist()),
            series_map=over_series_map,
            left=MARGIN_LEFT_IN,
            top=0.84,
            width=11.15,
            height=5.15,
            number_format='0.0"%"',
            percent_axis=True,
            label_position="above",
            label_font_size=8,
            series_colors=OVER_PPT_COLORS,
            value_max=over_axis_max,
            show_data_labels=False,
            show_legend=True,
        )
        for idx, series in enumerate(over_chart.series):
            _style_line_series(
                series,
                color=OVER_PPT_COLORS[idx % len(OVER_PPT_COLORS)],
                width_pt=2.5,
                marker_size=11,
            )
        latest_row = over_history.iloc[-1]
        add_line_end_labels(
            slide,
            labels=[_format_percent(latest_row[column]) for column in over_columns],
            values=[float(latest_row[column]) for column in over_columns],
            colors=[OVER_PPT_COLORS[idx % len(OVER_PPT_COLORS)] for idx in range(len(over_columns))],
            left=MARGIN_LEFT_IN,
            top=0.84,
            width=11.15,
            height=5.15,
            axis_max=over_axis_max,
        )
    add_textbox(
        slide,
        0.45,
        6.20,
        12.0,
        0.30,
        "Definição CVM: o somatório usa parcelas vencidas por faixa de atraso. Não é métrica de arrasto.",
        size=LABEL_SIZE,
        color=MID_GRAY,
    )
    add_footer(slide, timestamp_text)

    # Slide 5 — default aging
    slide = prs.slides.add_slide(blank)
    add_textbox(slide, 0.45, 0.18, 10.0, 0.28, "Aging da inadimplência (% dos direitos creditórios totais)", size=TITLE_SIZE, bold=True, color=BLACK)
    add_textbox(
        slide,
        0.45,
        0.46,
        11.7,
        0.18,
        "Distribuição não cumulativa por faixa de atraso. Os rótulos ficam centralizados em cada segmento quando há espaço útil suficiente.",
        size=BODY_SIZE,
        color=MID_GRAY,
    )
    aging_history = _build_aging_history_for_ppt(dashboard)
    if not aging_history.empty:
        aging_columns = [column for column in aging_history.columns if column != "competencia"]
        aging_series_map = [(column, aging_history[column].tolist()) for column in aging_columns]
        aging_chart = add_chart(
            slide,
            title=None,
            chart_type=XL_CHART_TYPE.COLUMN_STACKED,
            categories=_competencia_labels(aging_history["competencia"].tolist()),
            series_map=aging_series_map,
            left=MARGIN_LEFT_IN,
            top=0.82,
            width=CONTENT_WIDTH_IN,
            height=5.48,
            number_format='0%',
            percent_axis=True,
            gap_width=36,
            overlap=100,
            label_position="center",
            label_color=WHITE,
            label_font_size=12,
            series_colors=AGING_PPT_COLORS,
            value_max=_percent_axis_max(aging_series_map, cap=120.0),
            show_legend=True,
        )
        for idx, series in enumerate(aging_chart.series):
            series.data_labels.font.color.rgb = rgb(WHITE)
    add_footer(slide, timestamp_text)

    # Slide 6 — maturity and duration
    slide = prs.slides.add_slide(blank)
    add_textbox(slide, 0.45, 0.18, 9.5, 0.28, "Vencimento e duration estimada dos recebíveis", size=TITLE_SIZE, bold=True, color=BLACK)
    add_textbox(
        slide,
        0.45,
        0.46,
        11.6,
        0.18,
        "O waterfall mostra apenas os direitos creditórios a vencer; os vencidos ficam fora do total do gráfico. A duration continua usando a malha completa.",
        size=BODY_SIZE,
        color=MID_GRAY,
    )
    maturity_df = _latest_maturity_chart_frame(dashboard.maturity_latest_df)
    if not maturity_df.empty:
        maturity_scale = _money_scale(pd.to_numeric(maturity_df["valor"], errors="coerce"))
        maturity_values = _scale_values(maturity_df["valor"], maturity_scale).tolist()
        add_compounding_waterfall_chart(
            slide,
            categories=maturity_df["faixa"].astype(str).tolist(),
            step_values=maturity_values,
            total_value=float(sum(maturity_values)),
            left=MARGIN_LEFT_IN,
            top=0.86,
            width=CONTENT_WIDTH_IN,
            height=3.05,
            number_format=_money_number_format(maturity_scale),
            value_max=_money_axis_max(list(maturity_values) + [sum(maturity_values)]),
            title_suffix=f" ({maturity_scale.label})" if maturity_scale.label else "",
            label_font_size=11,
        )
    duration_df = dashboard.duration_history_df.sort_values("competencia_dt").copy()
    if not duration_df.empty:
        duration_series = [("Duration", _series_numeric(duration_df, "duration_days").fillna(0.0).tolist())]
        duration_chart = add_chart(
            slide,
            title="Duration estimada dos recebíveis",
            chart_type=XL_CHART_TYPE.LINE_MARKERS,
            categories=_competencia_labels(duration_df["competencia"].tolist()),
            series_map=duration_series,
            left=MARGIN_LEFT_IN,
            top=4.35,
            width=CONTENT_WIDTH_IN,
            height=2.05,
            number_format='0',
            label_position="above",
            label_font_size=12,
            show_data_labels=True,
        )
        _style_line_series(duration_chart.series[0], color=ORANGE, width_pt=2.4, marker_size=15)
    add_footer(slide, timestamp_text)

    buffer = BytesIO()
    prs.save(buffer)
    return buffer.getvalue()


def build_dashboard_pptx_file(
    dashboard: FundonetDashboardData,
    output_path: Path,
    *,
    generated_at: datetime | None = None,
) -> Path:
    output_path.write_bytes(build_dashboard_pptx_bytes(dashboard, generated_at=generated_at))
    return output_path


def _fund_title(dashboard: FundonetDashboardData) -> str:
    return str(dashboard.fund_info.get("nome_fundo") or dashboard.fund_info.get("nome_classe") or "FIDC selecionado")


def _to_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_decimal(value: object, *, decimals: int = 2) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/D"
    return f"{numeric:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_percent(value: object) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/D"
    return f"{_format_decimal(numeric, decimals=1)}%"


def _format_metric_value(value: object, unit: str) -> str:
    if unit == "R$":
        return _format_brl_compact(value)
    if unit == "%":
        return _format_percent(value)
    return _format_decimal(value)


def _format_brl_compact(value: object) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/D"
    scale = _money_scale(pd.Series([numeric]))
    if scale.divisor == 1.0:
        return f"R$ {_format_decimal(numeric, decimals=2)}"
    decimals = 2 if scale.divisor >= 1_000_000_000 else 1
    return f"R$ {_format_decimal(numeric / scale.divisor, decimals=decimals)} {scale.suffix}"


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


def _competencia_labels(values: Sequence[object]) -> list[str]:
    return [_format_competencia(value) for value in values]


def _safe_pct(numerator: object, denominator: object) -> float | None:
    num = _to_float(numerator)
    den = _to_float(denominator)
    if num is None or den is None or den <= 0:
        return None
    return num / den * 100.0


def _series_numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _percent_axis_max(series_map: Sequence[tuple[str, Sequence[float]]], *, cap: float = 110.0) -> float:
    values: list[float] = []
    for _, series_values in series_map:
        values.extend([float(value) for value in series_values if value is not None])
    if not values:
        return cap
    max_value = max(values)
    if max_value <= 0:
        return cap
    return min(cap, max(max_value * 1.18, max_value + 4.0))


def _money_axis_max(values: Sequence[object]) -> float | None:
    numeric = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if numeric.empty:
        return None
    max_value = float(numeric.max())
    if max_value <= 0:
        return None
    return max_value * 1.16


def _money_scale(values: pd.Series) -> MoneyScale:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    max_abs = float(numeric.abs().max()) if not numeric.empty else 0.0
    if max_abs >= 1_000_000_000_000:
        return MoneyScale(1_000_000_000_000.0, "tri", "R$ tri")
    if max_abs >= 1_000_000_000:
        return MoneyScale(1_000_000_000.0, "bi", "R$ bi")
    if max_abs >= 1_000_000:
        return MoneyScale(1_000_000.0, "mm", "R$ mm")
    return MoneyScale(1.0, "", "R$")


def _scale_values(values: Sequence[object], scale: MoneyScale) -> pd.Series:
    numeric = pd.to_numeric(pd.Series(values), errors="coerce").fillna(0.0)
    if scale.divisor <= 0:
        return numeric
    return numeric / scale.divisor


def _money_number_format(scale: MoneyScale) -> str:
    if scale.divisor == 1.0:
        return '#,##0.00'
    return '0.0'


def _money_label_number_format(scale: MoneyScale) -> str:
    if scale.divisor == 1.0:
        return '#,##0'
    if scale.suffix:
        return f'0" {scale.suffix}"'
    return '0'


def _latest_aging_table_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame({"Faixa": ["Sem dados"], "Valor": ["-"], "%": ["-"]})
    output = frame.copy()
    percent_column = "percentual_direitos_creditorios" if "percentual_direitos_creditorios" in output.columns else "percentual"
    output["Faixa"] = output["faixa"]
    output["Valor"] = output["valor"].map(_format_brl_compact)
    output["%"] = output[percent_column].map(_format_percent)
    return output[["Faixa", "Valor", "%"]]


def _build_over_aging_history_for_ppt(dashboard: FundonetDashboardData) -> pd.DataFrame:
    over_history_df = dashboard.default_over_history_df.sort_values("competencia_dt").copy()
    if over_history_df.empty:
        return pd.DataFrame(columns=["competencia"])
    pivot = (
        over_history_df[over_history_df["calculo_status"] == "calculado"]
        .pivot(index="competencia", columns="serie", values="percentual")
        .reset_index()
    )
    ordered_columns = ["competencia", "Over 30", "Over 60", "Over 90", "Over 180", "Over 360"]
    for column in ordered_columns:
        if column not in pivot.columns:
            pivot[column] = 0.0 if column != "competencia" else pivot.get(column)
    pivot = pivot[ordered_columns].copy()
    pivot = pivot.fillna(0.0)
    return pivot


def _build_aging_history_for_ppt(dashboard: FundonetDashboardData) -> pd.DataFrame:
    aging_history_df = dashboard.default_aging_history_df.sort_values("competencia_dt").copy()
    if aging_history_df.empty:
        return pd.DataFrame(columns=["competencia"])
    pivot = (
        aging_history_df.pivot_table(
            index="competencia",
            columns="faixa",
            values="percentual_direitos_creditorios",
            aggfunc="sum",
        )
        .fillna(0.0)
        .reset_index()
    )
    ordered_columns = [
        "competencia",
        "Até 30 dias",
        "31 a 60 dias",
        "61 a 90 dias",
        "91 a 120 dias",
        "121 a 150 dias",
        "151 a 180 dias",
        "181 a 360 dias",
        "361 a 720 dias",
        "721 a 1080 dias",
        "Acima de 1080 dias",
    ]
    for column in ordered_columns:
        if column not in pivot.columns:
            pivot[column] = 0.0 if column != "competencia" else pivot.get(column)
    return pivot[ordered_columns].copy()


def _latest_over_table_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame({"Faixa": ["Sem dados"], "% DCs": ["-"], "Status": ["-"]})
    latest_row = frame.iloc[-1]
    rows = []
    for column in frame.columns:
        if column == "competencia":
            continue
        rows.append(
            {
                "Faixa": column,
                "% DCs": _format_percent(latest_row[column]),
                "Status": "Acumulado",
            }
        )
    return pd.DataFrame(rows)


def _latest_events_table_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame({"Evento": ["Sem dados"], "Valor": ["-"], "% PL": ["-"]})
    output = frame.copy()
    output["Evento"] = output["evento"]
    output["Valor"] = output["valor_total"].map(_format_brl_compact)
    output["% PL"] = output["valor_total_pct_pl"].map(_format_percent)
    return output[["Evento", "Valor", "% PL"]]


def _latest_quota_table_frame(frame: pd.DataFrame, latest_competencia: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame({"Classe": ["Sem dados"], "Qt. cotas": ["-"], "PL": ["-"]})
    output = frame[frame["competencia"] == latest_competencia].copy()
    if output.empty:
        return pd.DataFrame({"Classe": ["Sem dados"], "Qt. cotas": ["-"], "PL": ["-"]})
    output["Classe"] = output["label"]
    output["Qt. cotas"] = output["qt_cotas"].map(_format_decimal_0_or_2)
    output["PL"] = output["pl"].map(_format_brl_compact)
    return output[["Classe", "Qt. cotas", "PL"]]


def _latest_maturity_chart_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["faixa", "valor", "ordem"])
    output = frame.copy()
    output["valor"] = pd.to_numeric(output["valor"], errors="coerce").fillna(0.0)
    output = output[output["faixa"] != "Vencidos"].copy()
    if output.empty:
        return pd.DataFrame(columns=["faixa", "valor", "ordem"])
    if "ordem" in output.columns:
        output = output.sort_values("ordem")
        return output[["faixa", "valor", "ordem"]]
    return output[["faixa", "valor"]]


def _quota_pl_share_pivot(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["competencia"])
    output = frame.copy()
    output["percentual"] = pd.to_numeric(output["pl_share_pct"], errors="coerce").fillna(0.0)
    pivot = (
        output.pivot_table(index="competencia", columns="label", values="percentual", aggfunc="sum")
        .fillna(0.0)
        .reset_index()
    )
    return pivot


def _quota_pl_value_pivot(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["competencia"])
    output = frame.copy()
    output["valor"] = pd.to_numeric(output["pl"], errors="coerce").fillna(0.0)
    pivot = (
        output.pivot_table(index="competencia", columns="label", values="valor", aggfunc="sum")
        .fillna(0.0)
        .reset_index()
    )
    return pivot


def _risk_metrics_table_frame(metrics_df: pd.DataFrame, risk_block: str) -> pd.DataFrame:
    if metrics_df.empty:
        return pd.DataFrame(columns=["Métrica", "Valor", "Leitura"])
    output = metrics_df[metrics_df["risk_block"] == risk_block].copy()
    if output.empty:
        return pd.DataFrame(columns=["Métrica", "Valor", "Leitura"])
    output["Métrica"] = output["label"]
    output["Valor"] = output.apply(
        lambda row: _format_metric_value(row.get("value"), str(row.get("unit") or "")),
        axis=1,
    )
    output["Leitura"] = output["interpretation"].fillna("N/D")
    return output[["Métrica", "Valor", "Leitura"]]


def _format_decimal_0_or_2(value: object) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/D"
    decimals = 0 if float(numeric).is_integer() else 2
    return _format_decimal(numeric, decimals=decimals)
