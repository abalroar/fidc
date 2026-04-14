from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Sequence

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
) -> bytes:
    try:
        from pptx import Presentation
        from pptx.chart.data import CategoryChartData
        from pptx.dml.color import RGBColor
        from pptx.enum.chart import XL_CHART_TYPE, XL_DATA_LABEL_POSITION
        from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
        from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
        from pptx.util import Inches, Pt
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Dependência python-pptx não instalada.") from exc

    generated_at = generated_at or datetime.now()
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
        title: str,
        left: float,
        top: float,
        width: float,
        height: float,
        col_widths: Sequence[float] | None = None,
    ):
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
        title: str,
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
        legend_items: Sequence[tuple[str, str]] | None = None,
        title_suffix: str = "",
        value_max: float | None = None,
        value_min: float | None = None,
    ):
        add_textbox(slide, left, top - 0.22, width, 0.18, f"{title}{title_suffix}", size=SECTION_SIZE, bold=True, color=BLACK)
        chart_data = CategoryChartData()
        chart_data.categories = list(categories)
        for series_name, values in series_map:
            chart_data.add_series(series_name, tuple(values))
        chart_shape = slide.shapes.add_chart(chart_type, Inches(left), Inches(top), Inches(width), Inches(height), chart_data)
        chart = chart_shape.chart
        chart.has_legend = False

        plot = chart.plots[0]
        if gap_width is not None and hasattr(plot, "gap_width"):
            plot.gap_width = gap_width
        if overlap is not None and hasattr(plot, "overlap"):
            plot.overlap = overlap
        plot.has_data_labels = True
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

        for idx, series in enumerate(chart.series):
            fill = series.format.fill
            fill.solid()
            fill.fore_color.rgb = rgb(SERIES_COLORS[idx % len(SERIES_COLORS)])
            series.format.line.color.rgb = rgb(SERIES_COLORS[idx % len(SERIES_COLORS)])

        if legend_items:
            add_manual_legend(slide, legend_items, left=left, top=top + height + 0.02, max_width=width)

        return chart

    timestamp_text = generated_at.strftime("%d/%m/%Y %H:%M")
    title_fund = _fund_title(dashboard)

    # Slide 1: visão geral + crédito
    slide = prs.slides.add_slide(blank)
    add_textbox(slide, MARGIN_LEFT_IN, 0.18, 6.2, 0.28, "Informe Mensal Estruturado", size=TITLE_SIZE, bold=True, color=BLACK)
    add_textbox(slide, MARGIN_LEFT_IN, 0.48, 9.6, 0.22, title_fund, size=13, bold=True, color=ORANGE)
    subtitle = (
        f"Última competência: {_format_competencia(dashboard.latest_competencia)}"
        f"  |  Janela: {dashboard.fund_info.get('periodo_analisado', 'N/D')}"
        f"  |  Cotistas: {dashboard.fund_info.get('total_cotistas') or 'N/D'}"
    )
    add_textbox(slide, MARGIN_LEFT_IN, 0.72, 10.5, 0.16, subtitle, size=BODY_SIZE, color=MID_GRAY)

    cards = [
        ("PL total", _format_brl_compact(dashboard.summary.get("pl_total")), ""),
        ("Direitos creditórios", _format_brl_compact(dashboard.summary.get("inadimplencia_denominador") or dashboard.summary.get("direitos_creditorios")), ""),
        ("Inadimplência", _format_percent(dashboard.summary.get("inadimplencia_pct")), "vencidos / base observável"),
        ("Cobertura de provisão", _format_percent(_safe_pct(dashboard.summary.get("provisao_total"), dashboard.summary.get("inadimplencia_total"))), "provisão / vencidos"),
        ("Subordinação", _format_percent(dashboard.summary.get("subordinacao_pct")), ""),
        ("Créditos vencidos", _format_brl_compact(dashboard.summary.get("direitos_creditorios_vencidos")), ""),
    ]
    card_width = 2.0
    card_gap = 0.08
    for idx, (label, value, note) in enumerate(cards):
        add_card(
            slide,
            MARGIN_LEFT_IN + idx * (card_width + card_gap),
            1.02,
            card_width,
            0.95,
            label,
            value,
            note,
        )

    default_df = dashboard.default_history_df.sort_values("competencia_dt").copy()
    if not default_df.empty:
        direitos_base = _series_numeric(default_df, "direitos_creditorios_vencimento_total")
        if direitos_base.dropna().empty:
            direitos_base = _series_numeric(default_df, "direitos_creditorios")
        provisao_pct = (
            _series_numeric(default_df, "provisao_total") / direitos_base
        ).where(direitos_base > 0).mul(100.0).fillna(0.0)
        credit_series = [
            ("Inadimplência", _series_numeric(default_df, "inadimplencia_pct").fillna(0.0).tolist()),
            ("Provisão", provisao_pct.tolist()),
        ]
        add_chart(
            slide,
            title="Inad vs. Provisão (% dos DCs)",
            chart_type=XL_CHART_TYPE.COLUMN_CLUSTERED,
            categories=_competencia_labels(default_df["competencia"].tolist()),
            series_map=credit_series,
            left=MARGIN_LEFT_IN,
            top=2.35,
            width=7.55,
            height=3.85,
            number_format='0.0"%"',
            percent_axis=True,
            gap_width=42,
            label_position="outside_end",
            label_font_size=10,
            legend_items=[("Inadimplência", SERIES_COLORS[0]), ("Provisão", SERIES_COLORS[1])],
            value_max=_percent_axis_max(credit_series, cap=60.0),
        )
        add_textbox(
            slide,
            MARGIN_LEFT_IN,
            6.25,
            7.55,
            0.20,
            "Leitura: barras justapostas para comparar vencidos e provisão sobre a mesma base observável de direitos creditórios.",
            size=LABEL_SIZE,
            color=MID_GRAY,
        )

    aging_df = _latest_aging_table_frame(dashboard.default_buckets_latest_df)
    add_table(
        slide,
        aging_df,
        title="Aging da inadimplência - última competência",
        left=8.20,
        top=2.35,
        width=4.70,
        height=3.45,
        col_widths=[2.10, 1.35, 1.05],
    )
    add_textbox(
        slide,
        8.20,
        5.98,
        4.70,
        0.30,
        "Faixas curtas devem concentrar maior peso quando a carteira está só tensionada; faixas longas indicam deterioração mais séria.",
        size=LABEL_SIZE,
        color=MID_GRAY,
    )
    add_footer(slide, timestamp_text)

    # Slide 2: estrutura + eventos + vencimento
    slide = prs.slides.add_slide(blank)
    add_textbox(slide, MARGIN_LEFT_IN, 0.18, 7.0, 0.28, "Estrutura, cotas, eventos e vencimento", size=TITLE_SIZE, bold=True, color=BLACK)
    add_textbox(slide, MARGIN_LEFT_IN, 0.50, 8.5, 0.18, title_fund, size=12, bold=True, color=ORANGE)

    sub_df = dashboard.subordination_history_df.sort_values("competencia_dt").copy()
    if not sub_df.empty:
        sub_series = [("Subordinação", _series_numeric(sub_df, "subordinacao_pct").fillna(0.0).tolist())]
        add_chart(
            slide,
            title="Índice de subordinação",
            chart_type=XL_CHART_TYPE.COLUMN_CLUSTERED,
            categories=_competencia_labels(sub_df["competencia"].tolist()),
            series_map=sub_series,
            left=MARGIN_LEFT_IN,
            top=1.00,
            width=6.00,
            height=2.25,
            number_format='0.0"%"',
            percent_axis=True,
            gap_width=32,
            label_position="outside_end",
            label_font_size=10,
            value_max=_percent_axis_max(sub_series, cap=60.0),
        )

    quota_share = _quota_pl_share_pivot(dashboard.quota_pl_history_df)
    if not quota_share.empty:
        add_chart(
            slide,
            title="PL por tipo de cota (% do total)",
            chart_type=XL_CHART_TYPE.COLUMN_STACKED_100,
            categories=_competencia_labels(quota_share["competencia"].tolist()),
            series_map=[
                (column, quota_share[column].tolist())
                for column in quota_share.columns
                if column != "competencia"
            ],
            left=6.40,
            top=1.00,
            width=6.45,
            height=2.25,
            number_format='0.0"%"',
            percent_axis=True,
            gap_width=32,
            overlap=100,
            label_position="center",
            label_color=WHITE,
            label_font_size=9,
            legend_items=[
                (column, SERIES_COLORS[idx % len(SERIES_COLORS)])
                for idx, column in enumerate([column for column in quota_share.columns if column != "competencia"])
            ],
            value_max=100.0,
        )
        add_textbox(
            slide,
            6.40,
            3.42,
            6.45,
            0.18,
            "Leitura: a composição mostra quanto do PL é proteção subordinada versus tranches mais seniores.",
            size=LABEL_SIZE,
            color=MID_GRAY,
        )

    latest_quota = _latest_quota_table_frame(dashboard.quota_pl_history_df, dashboard.latest_competencia)
    add_table(
        slide,
        latest_quota,
        title="Estrutura de cotas - última competência",
        left=MARGIN_LEFT_IN,
        top=3.95,
        width=3.85,
        height=2.55,
        col_widths=[1.55, 0.95, 1.35],
    )

    latest_events = _latest_events_table_frame(dashboard.event_summary_latest_df)
    add_table(
        slide,
        latest_events,
        title="Eventos de cotas",
        left=4.50,
        top=3.95,
        width=3.35,
        height=2.55,
        col_widths=[1.35, 1.00, 1.00],
    )

    maturity_df = _latest_maturity_chart_frame(dashboard.maturity_latest_df)
    if not maturity_df.empty:
        maturity_scale = _money_scale(pd.to_numeric(maturity_df["valor"], errors="coerce"))
        maturity_values = _scale_values(maturity_df["valor"], maturity_scale).tolist()
        add_chart(
            slide,
            title="Vencimento dos direitos creditórios",
            title_suffix=f" ({maturity_scale.label})" if maturity_scale.label else "",
            chart_type=XL_CHART_TYPE.COLUMN_CLUSTERED,
            categories=maturity_df["faixa"].astype(str).tolist(),
            series_map=[("Valor", maturity_values)],
            left=8.10,
            top=3.95,
            width=4.75,
            height=2.55,
            number_format=_money_number_format(maturity_scale),
            money_axis=True,
            gap_width=28,
            label_position="outside_end",
            label_font_size=10,
            value_max=_money_axis_max(maturity_values),
        )
    vencidos = _to_float(dashboard.summary.get("direitos_creditorios_vencidos"))
    base = _to_float(dashboard.summary.get("inadimplencia_denominador"))
    add_textbox(
        slide,
        8.10,
        6.55,
        4.75,
        0.22,
        f"Vencidos observáveis: {_format_brl_compact(vencidos)}  |  Base: {_format_brl_compact(base)}  |  Razão: {_format_percent(_safe_pct(vencidos, base))}",
        size=LABEL_SIZE,
        color=MID_GRAY,
    )
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


def _latest_aging_table_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame({"Faixa": ["Sem dados"], "Valor": ["-"], "%": ["-"]})
    output = frame.copy()
    output = output[output["ordem"] <= 7].copy()
    if output.empty:
        return pd.DataFrame({"Faixa": ["Sem dados"], "Valor": ["-"], "%": ["-"]})
    output["Faixa"] = output["faixa"]
    output["Valor"] = output["valor"].map(_format_brl_compact)
    output["%"] = output["percentual"].map(_format_percent)
    return output[["Faixa", "Valor", "%"]]


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
        return pd.DataFrame(columns=["faixa", "valor"])
    output = frame.copy()
    output["valor"] = pd.to_numeric(output["valor"], errors="coerce").fillna(0.0)
    output = output[output["valor"] > 0].copy()
    return output[["faixa", "valor"]]


def _quota_pl_share_pivot(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["competencia"])
    output = frame.copy()
    output["pl"] = pd.to_numeric(output["pl"], errors="coerce").fillna(0.0)
    totals = output.groupby("competencia", dropna=False)["pl"].transform("sum")
    output["percentual"] = (output["pl"] / totals).where(totals > 0).mul(100.0).fillna(0.0)
    pivot = (
        output.pivot_table(index="competencia", columns="label", values="percentual", aggfunc="sum")
        .fillna(0.0)
        .reset_index()
    )
    return pivot


def _format_decimal_0_or_2(value: object) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/D"
    decimals = 0 if float(numeric).is_integer() else 2
    return _format_decimal(numeric, decimals=decimals)
