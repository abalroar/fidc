from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd

from services.mercado_livre_dashboard import PT_MONTH_ABBR


MELI_BLACK = "000000"
MELI_ORANGE = "E47811"
MELI_DARK_GRAY = "3F3F3F"
MELI_MEDIUM_GRAY = "8C8C8C"


def build_pptx_export_bytes(outputs: Any) -> bytes:
    try:
        from pptx import Presentation
        from pptx.chart.data import CategoryChartData
        from pptx.dml.color import RGBColor
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_MARKER_STYLE
        from pptx.enum.text import PP_ALIGN
        from pptx.util import Inches, Pt
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("Dependência python-pptx não instalada.") from exc

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    scopes: list[tuple[str, pd.DataFrame]] = [("Carteira consolidada", outputs.consolidated_monthly)]
    for cnpj, frame in outputs.fund_monthly.items():
        fund_name = str(frame["fund_name"].iloc[0]) if isinstance(frame, pd.DataFrame) and not frame.empty and "fund_name" in frame.columns else str(cnpj)
        scopes.append((fund_name, frame))

    for scope_name, monthly_df in scopes:
        if not isinstance(monthly_df, pd.DataFrame) or monthly_df.empty:
            continue
        _add_pl_slide(
            prs=prs,
            layout=blank_layout,
            scope_name=scope_name,
            monthly_df=monthly_df,
            CategoryChartData=CategoryChartData,
            RGBColor=RGBColor,
            XL_CHART_TYPE=XL_CHART_TYPE,
            XL_LEGEND_POSITION=XL_LEGEND_POSITION,
            XL_MARKER_STYLE=XL_MARKER_STYLE,
            PP_ALIGN=PP_ALIGN,
            Inches=Inches,
            Pt=Pt,
        )
        _add_npl_slide(
            prs=prs,
            layout=blank_layout,
            scope_name=scope_name,
            monthly_df=monthly_df,
            CategoryChartData=CategoryChartData,
            RGBColor=RGBColor,
            XL_CHART_TYPE=XL_CHART_TYPE,
            XL_LEGEND_POSITION=XL_LEGEND_POSITION,
            XL_MARKER_STYLE=XL_MARKER_STYLE,
            PP_ALIGN=PP_ALIGN,
            Inches=Inches,
            Pt=Pt,
        )

    if len(prs.slides) == 0:
        slide = prs.slides.add_slide(blank_layout)
        _add_textbox(slide, "Mercado Livre", 0.55, 0.4, 11.8, 0.4, Pt(20), bold=True, RGBColor=RGBColor)
        _add_textbox(slide, "Sem dados carregados para gerar gráficos.", 0.55, 1.1, 11.8, 0.4, Pt(13), RGBColor=RGBColor)

    buffer = BytesIO()
    prs.save(buffer)
    return buffer.getvalue()


def _add_pl_slide(
    *,
    prs,
    layout,
    scope_name: str,
    monthly_df: pd.DataFrame,
    CategoryChartData,
    RGBColor,
    XL_CHART_TYPE,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
    PP_ALIGN,
    Inches,
    Pt,
) -> None:
    df = _chart_monthly(monthly_df)
    categories = _category_labels(df)
    scale_divisor, scale_label = _money_scale(
        pd.concat(
            [
                pd.to_numeric(df.get("pl_senior"), errors="coerce"),
                pd.to_numeric(df.get("pl_subordinada_mezz_ex360"), errors="coerce"),
            ],
            ignore_index=True,
        )
    )
    slide = prs.slides.add_slide(layout)
    _style_slide_background(slide, RGBColor)
    _add_title(slide, f"{scope_name} | Evolução de PL e Subordinação", "Valores em escala consistente; subordinação ex-360 em gráfico auxiliar.", RGBColor, Inches, Pt)

    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series("Sênior", [_scaled_value(value, scale_divisor) for value in df.get("pl_senior", pd.Series(dtype="float"))])
    chart_data.add_series(
        "Subordinada + Mezanino ex-360",
        [_scaled_value(value, scale_divisor) for value in df.get("pl_subordinada_mezz_ex360", pd.Series(dtype="float"))],
    )
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_STACKED,
        Inches(0.55),
        Inches(1.15),
        Inches(7.6),
        Inches(5.45),
        chart_data,
    ).chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    chart.value_axis.has_major_gridlines = True
    chart.value_axis.tick_labels.number_format = "#,##0.0"
    _set_series_fill(chart.series[0], _rgb(MELI_BLACK, RGBColor))
    if len(chart.series) > 1:
        _set_series_fill(chart.series[1], _rgb(MELI_ORANGE, RGBColor))

    line_data = CategoryChartData()
    line_data.categories = categories
    line_data.add_series("% Subordinação Total ex-360", [_percent_value(value) for value in df.get("subordinacao_total_ex360_pct", pd.Series(dtype="float"))])
    line_chart = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE_MARKERS,
        Inches(8.55),
        Inches(1.45),
        Inches(4.15),
        Inches(4.9),
        line_data,
    ).chart
    line_chart.has_legend = True
    line_chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    line_chart.legend.include_in_layout = False
    line_chart.value_axis.tick_labels.number_format = "0.0%"
    if line_chart.series:
        _set_series_line(line_chart.series[0], _rgb(MELI_DARK_GRAY, RGBColor), XL_MARKER_STYLE.CIRCLE)


def _add_npl_slide(
    *,
    prs,
    layout,
    scope_name: str,
    monthly_df: pd.DataFrame,
    CategoryChartData,
    RGBColor,
    XL_CHART_TYPE,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
    PP_ALIGN,
    Inches,
    Pt,
) -> None:
    df = _chart_monthly(monthly_df)
    categories = _category_labels(df)
    slide = prs.slides.add_slide(layout)
    _style_slide_background(slide, RGBColor)
    _add_title(slide, f"{scope_name} | NPL e Cobertura Ex-Vencidos > 360d", "Percentuais recalculados a partir dos numeradores e denominadores da base mensal.", RGBColor, Inches, Pt)

    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series("NPL Over 90d ex-360 / Carteira", [_percent_value(value) for value in df.get("npl_over90_ex360_pct", pd.Series(dtype="float"))])
    chart_data.add_series("PDD Ex / NPL Over 90d ex-360", [_percent_value(value) for value in df.get("pdd_npl_over90_ex360_pct", pd.Series(dtype="float"))])
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE_MARKERS,
        Inches(0.75),
        Inches(1.25),
        Inches(11.85),
        Inches(5.3),
        chart_data,
    ).chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    chart.value_axis.tick_labels.number_format = "0.0%"
    chart.value_axis.has_major_gridlines = True
    if chart.series:
        _set_series_line(chart.series[0], _rgb(MELI_BLACK, RGBColor), XL_MARKER_STYLE.CIRCLE)
    if len(chart.series) > 1:
        _set_series_line(chart.series[1], _rgb(MELI_ORANGE, RGBColor), XL_MARKER_STYLE.CIRCLE)


def _style_slide_background(slide, RGBColor) -> None:  # noqa: ANN001
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(255, 255, 255)


def _add_title(slide, title: str, subtitle: str, RGBColor, Inches, Pt) -> None:  # noqa: ANN001
    _add_textbox(slide, title, 0.55, 0.28, 12.25, 0.38, Pt(19), bold=True, RGBColor=RGBColor)
    _add_textbox(slide, subtitle, 0.55, 0.72, 12.25, 0.28, Pt(10.5), color=MELI_MEDIUM_GRAY, RGBColor=RGBColor)


def _add_textbox(slide, text: str, left: float, top: float, width: float, height: float, font_size, *, bold: bool = False, color: str = MELI_BLACK, RGBColor) -> None:  # noqa: ANN001
    from pptx.util import Inches

    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.clear()
    paragraph = frame.paragraphs[0]
    run = paragraph.add_run()
    run.text = text
    run.font.size = font_size
    run.font.bold = bold
    run.font.color.rgb = _rgb(color, RGBColor)


def _rgb(hex_color: str, RGBColor):  # noqa: ANN001
    clean = str(hex_color).strip().lstrip("#")
    return RGBColor(int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))


def _chart_monthly(monthly_df: pd.DataFrame) -> pd.DataFrame:
    df = monthly_df.copy()
    if "competencia_dt" not in df.columns:
        df["competencia_dt"] = pd.to_datetime(df.get("competencia"), errors="coerce")
    else:
        df["competencia_dt"] = pd.to_datetime(df["competencia_dt"], errors="coerce")
    return df.sort_values("competencia_dt").reset_index(drop=True)


def _category_labels(df: pd.DataFrame) -> list[str]:
    labels: list[str] = []
    for _, row in df.iterrows():
        ts = pd.to_datetime(row.get("competencia_dt"), errors="coerce")
        if pd.notna(ts):
            labels.append(f"{PT_MONTH_ABBR[int(ts.month)]}/{str(int(ts.year))[-2:]}")
        else:
            labels.append(str(row.get("competencia") or ""))
    return labels


def _money_scale(values: pd.Series) -> tuple[float, str]:
    max_value = pd.to_numeric(values, errors="coerce").abs().max()
    if pd.isna(max_value):
        max_value = 0.0
    if max_value >= 1_000_000_000:
        return 1_000_000_000.0, "R$ bi"
    if max_value >= 1_000_000:
        return 1_000_000.0, "R$ mm"
    if max_value >= 1_000:
        return 1_000.0, "R$ mil"
    return 1.0, "R$"


def _scaled_value(value: object, divisor: float) -> float | None:
    numeric = _num(value)
    return None if numeric is None else numeric / divisor


def _percent_value(value: object) -> float | None:
    numeric = _num(value)
    return None if numeric is None else numeric / 100.0


def _num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return None
    return float(parsed)


def _set_series_fill(series, color) -> None:  # noqa: ANN001
    series.format.fill.solid()
    series.format.fill.fore_color.rgb = color
    series.format.line.color.rgb = color


def _set_series_line(series, color, marker_style) -> None:  # noqa: ANN001
    series.format.line.color.rgb = color
    series.format.line.width = 19050
    series.marker.style = marker_style
    series.marker.size = 5
    series.marker.format.fill.solid()
    series.marker.format.fill.fore_color.rgb = color
    series.marker.format.line.color.rgb = color
