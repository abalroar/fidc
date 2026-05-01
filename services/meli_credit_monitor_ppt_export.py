from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd

from services.mercado_livre_dashboard import PT_MONTH_ABBR


MELI_BLACK = "000000"
MELI_ORANGE = "E47811"
MELI_DARK_GRAY = "3F3F3F"
MELI_MEDIUM_GRAY = "8C8C8C"


def build_dashboard_meli_pptx_bytes(monitor_outputs: Any) -> bytes:
    try:
        from pptx import Presentation
        from pptx.chart.data import CategoryChartData
        from pptx.dml.color import RGBColor
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_MARKER_STYLE
        from pptx.util import Inches, Pt
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("Dependência python-pptx não instalada.") from exc

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    layout = prs.slide_layouts[6]

    _add_consolidated_slide(
        prs=prs,
        layout=layout,
        monitor_outputs=monitor_outputs,
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
    )
    _add_consolidated_detail_slide(
        prs=prs,
        layout=layout,
        monitor_outputs=monitor_outputs,
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
    )
    for cnpj, monitor in getattr(monitor_outputs, "fund_monitor", {}).items():
        fund_name = _fund_name(monitor, fallback=str(cnpj))
        _add_fund_slide(
            prs=prs,
            layout=layout,
            title=fund_name,
            monitor_df=monitor,
            cohort_df=getattr(monitor_outputs, "fund_cohorts", {}).get(cnpj, pd.DataFrame()),
            CategoryChartData=CategoryChartData,
            RGBColor=RGBColor,
            XL_CHART_TYPE=XL_CHART_TYPE,
            XL_LEGEND_POSITION=XL_LEGEND_POSITION,
            XL_MARKER_STYLE=XL_MARKER_STYLE,
            Inches=Inches,
            Pt=Pt,
        )

    buffer = BytesIO()
    prs.save(buffer)
    return buffer.getvalue()


def _add_consolidated_slide(
    *,
    prs,
    layout,
    monitor_outputs: Any,
    CategoryChartData,
    RGBColor,
    XL_CHART_TYPE,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
    Inches,
    Pt,
) -> None:
    slide = prs.slides.add_slide(layout)
    _style_slide(slide, RGBColor)
    _add_header(slide, "Dashboard MELI - Consolidado", RGBColor, Inches, Pt)
    slots = _grid_2x2_slots()
    df = _chart_monthly(getattr(monitor_outputs, "consolidated_monitor", pd.DataFrame()))
    categories = _category_labels(df)
    _add_multi_line_chart(
        slide=slide,
        slot=slots[0],
        title="Roll rates",
        df=df,
        categories=categories,
        series_specs=[
            ("Roll 61-90 M-3", "roll_61_90_m3_pct", MELI_BLACK),
            ("Roll 151-180 M-6", "roll_151_180_m6_pct", MELI_ORANGE),
        ],
        y_axis_title="%",
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
    )
    _add_stacked_npl_chart(
        slide=slide,
        slot=slots[1],
        df=df,
        categories=categories,
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        Inches=Inches,
        Pt=Pt,
    )
    _add_money_bar_chart(
        slide=slide,
        slot=slots[2],
        title="Carteira ex-360",
        df=df,
        categories=categories,
        column="carteira_ex360",
        series_name="Carteira ex-360",
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        Inches=Inches,
        Pt=Pt,
    )
    _add_multi_line_chart(
        slide=slide,
        slot=slots[3],
        title="Crescimento a/a carteira ex-360",
        df=df,
        categories=categories,
        series_specs=[("Crescimento a/a", "carteira_ex360_yoy_pct", MELI_ORANGE)],
        y_axis_title="%",
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
    )


def _add_fund_slide(
    *,
    prs,
    layout,
    title: str,
    monitor_df: pd.DataFrame,
    cohort_df: pd.DataFrame,
    CategoryChartData,
    RGBColor,
    XL_CHART_TYPE,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
    Inches,
    Pt,
) -> None:
    slide = prs.slides.add_slide(layout)
    _style_slide(slide, RGBColor)
    _add_header(slide, title, RGBColor, Inches, Pt)
    slots = _grid_2x2_slots()
    df = _chart_monthly(monitor_df)
    categories = _category_labels(df)
    _add_multi_line_chart(
        slide=slide,
        slot=slots[0],
        title="Roll rates",
        df=df,
        categories=categories,
        series_specs=[
            ("Roll 61-90 M-3", "roll_61_90_m3_pct", MELI_BLACK),
            ("Roll 151-180 M-6", "roll_151_180_m6_pct", MELI_ORANGE),
        ],
        y_axis_title="%",
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
    )
    _add_stacked_npl_chart(
        slide=slide,
        slot=slots[1],
        df=df,
        categories=categories,
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        Inches=Inches,
        Pt=Pt,
    )
    _add_money_bar_chart(
        slide=slide,
        slot=slots[2],
        title="Carteira ex-360",
        df=df,
        categories=categories,
        column="carteira_ex360",
        series_name="Carteira ex-360",
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        Inches=Inches,
        Pt=Pt,
    )
    _add_cohort_chart(
        slide=slide,
        slot=slots[3],
        title="Cohorts recentes",
        cohort_df=cohort_df,
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
    )


def _add_consolidated_detail_slide(
    *,
    prs,
    layout,
    monitor_outputs: Any,
    CategoryChartData,
    RGBColor,
    XL_CHART_TYPE,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
    Inches,
    Pt,
) -> None:
    slide = prs.slides.add_slide(layout)
    _style_slide(slide, RGBColor)
    _add_header(slide, "Dashboard MELI - Duration e cohorts consolidadas", RGBColor, Inches, Pt)
    slots = _grid_2x2_slots()
    duration_df = _duration_frame(getattr(monitor_outputs, "consolidated_monitor", pd.DataFrame()), getattr(monitor_outputs, "fund_monitor", {}))
    duration_series = [column for column in duration_df.columns if column not in {"competencia_dt", "competencia"}]
    _add_multi_line_chart(
        slide=slide,
        slot=slots[0],
        title="Duration por FIDC",
        df=duration_df,
        categories=_category_labels(duration_df),
        series_specs=[(serie, serie, color) for serie, color in _series_colors(duration_series)],
        y_axis_title="meses",
        value_is_percent=False,
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
    )
    _add_cohort_chart(
        slide=slide,
        slot=slots[1],
        title="Cohorts recentes",
        cohort_df=getattr(monitor_outputs, "consolidated_cohorts", pd.DataFrame()),
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
    )


def _add_multi_line_chart(
    *,
    slide,
    slot: tuple[float, float, float, float],
    title: str,
    df: pd.DataFrame,
    categories: list[str],
    series_specs: list[tuple[str, str, str]],
    y_axis_title: str,
    CategoryChartData,
    RGBColor,
    XL_CHART_TYPE,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
    Inches,
    Pt,
    value_is_percent: bool = True,
) -> None:
    valid_specs = [(name, column, color) for name, column, color in series_specs if column in df.columns or name in set(df.get("serie", pd.Series(dtype="object")))]
    if df.empty or not categories or not valid_specs:
        _add_empty(slide, slot, title, "Sem dados calculáveis.", RGBColor, Inches, Pt)
        return
    chart_data = CategoryChartData()
    chart_data.categories = categories
    final_labels: list[tuple[str, object, str]] = []
    for name, column, color in valid_specs:
        if column in df.columns:
            values = [_chart_value(value, percent=value_is_percent) for value in df[column]]
        else:
            series_df = df[df["serie"].eq(name)].copy()
            values = [_chart_value(value, percent=value_is_percent) for value in series_df.get("valor", pd.Series(dtype="float"))]
        chart_data.add_series(name, values)
        final_labels.append((name, _last_non_null(values), color))
    chart = _add_chart(slide, slot, XL_CHART_TYPE.LINE_MARKERS, chart_data, Inches)
    _style_common_chart(chart, title, "Competência", y_axis_title, "0.0%" if value_is_percent else "#,##0.0", RGBColor, Pt)
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    for series, (_, _, color) in zip(chart.series, valid_specs, strict=False):
        _set_series_line(series, _rgb(color, RGBColor), XL_MARKER_STYLE.CIRCLE)
    _add_final_label_stack(slide, slot, final_labels, value_is_percent=value_is_percent, RGBColor=RGBColor, Inches=Inches, Pt=Pt)


def _add_stacked_npl_chart(
    *,
    slide,
    slot: tuple[float, float, float, float],
    df: pd.DataFrame,
    categories: list[str],
    CategoryChartData,
    RGBColor,
    XL_CHART_TYPE,
    XL_LEGEND_POSITION,
    Inches,
    Pt,
) -> None:
    if df.empty or not categories:
        _add_empty(slide, slot, "NPL por severidade", "Sem dados calculáveis.", RGBColor, Inches, Pt)
        return
    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series("NPL 1-90d", [_chart_value(value, percent=True) for value in df.get("npl_1_90_pct", pd.Series(dtype="float"))])
    chart_data.add_series("NPL 91-360d", [_chart_value(value, percent=True) for value in df.get("npl_91_360_pct", pd.Series(dtype="float"))])
    chart = _add_chart(slide, slot, XL_CHART_TYPE.COLUMN_STACKED, chart_data, Inches)
    _style_common_chart(chart, "NPL por severidade", "Competência", "% da carteira ex-360", "0.0%", RGBColor, Pt)
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    for series, color in zip(chart.series, [MELI_BLACK, MELI_ORANGE], strict=False):
        _set_series_fill(series, _rgb(color, RGBColor))
    _add_final_label_stack(
        slide,
        slot,
        [
            ("NPL 1-90d", _last_non_null([_chart_value(value, percent=True) for value in df.get("npl_1_90_pct", pd.Series(dtype="float"))]), MELI_BLACK),
            ("NPL 91-360d", _last_non_null([_chart_value(value, percent=True) for value in df.get("npl_91_360_pct", pd.Series(dtype="float"))]), MELI_ORANGE),
        ],
        value_is_percent=True,
        RGBColor=RGBColor,
        Inches=Inches,
        Pt=Pt,
    )


def _add_money_bar_chart(
    *,
    slide,
    slot: tuple[float, float, float, float],
    title: str,
    df: pd.DataFrame,
    categories: list[str],
    column: str,
    series_name: str,
    CategoryChartData,
    RGBColor,
    XL_CHART_TYPE,
    Inches,
    Pt,
) -> None:
    if df.empty or not categories or column not in df.columns:
        _add_empty(slide, slot, title, "Sem dados calculáveis.", RGBColor, Inches, Pt)
        return
    scale, scale_label = _money_scale(df[column])
    values = [_scaled_value(value, scale) for value in df[column]]
    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series(series_name, values)
    chart = _add_chart(slide, slot, XL_CHART_TYPE.COLUMN_CLUSTERED, chart_data, Inches)
    _style_common_chart(chart, title, "Competência", scale_label, "#,##0.0", RGBColor, Pt)
    chart.has_legend = False
    if chart.series:
        _set_series_fill(chart.series[0], _rgb(MELI_BLACK, RGBColor))
    _add_final_label_stack(
        slide,
        slot,
        [(series_name, _last_non_null(values), MELI_BLACK)],
        value_is_percent=False,
        RGBColor=RGBColor,
        Inches=Inches,
        Pt=Pt,
    )


def _add_cohort_chart(
    *,
    slide,
    slot: tuple[float, float, float, float],
    title: str,
    cohort_df: pd.DataFrame,
    CategoryChartData,
    RGBColor,
    XL_CHART_TYPE,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
    Inches,
    Pt,
) -> None:
    if cohort_df is None or cohort_df.empty:
        _add_empty(slide, slot, title, "Sem dados calculáveis.", RGBColor, Inches, Pt)
        return
    df = cohort_df.copy()
    recent = df[["cohort", "cohort_dt"]].drop_duplicates().sort_values("cohort_dt").tail(6)["cohort"].tolist()
    df = df[df["cohort"].isin(recent)].copy()
    categories = ["M1", "M2", "M3", "M4", "M5", "M6"]
    colors = [MELI_BLACK, MELI_ORANGE, MELI_DARK_GRAY, MELI_MEDIUM_GRAY]
    chart_data = CategoryChartData()
    chart_data.categories = categories
    final_labels: list[tuple[str, object, str]] = []
    for idx, cohort in enumerate(recent):
        group = df[df["cohort"].eq(cohort)].set_index("mes_ciclo")
        values = [_chart_value(group.loc[label, "valor_pct"], percent=True) if label in group.index else None for label in categories]
        chart_data.add_series(cohort, values)
        final_labels.append((cohort, _last_non_null(values), colors[idx % len(colors)]))
    chart = _add_chart(slide, slot, XL_CHART_TYPE.LINE_MARKERS, chart_data, Inches)
    _style_common_chart(chart, title, "Mês de maturação", "% do saldo a vencer em 30d", "0.0%", RGBColor, Pt)
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    for series, color in zip(chart.series, colors, strict=False):
        _set_series_line(series, _rgb(color, RGBColor), XL_MARKER_STYLE.CIRCLE)
    _add_final_label_stack(slide, slot, final_labels, value_is_percent=True, RGBColor=RGBColor, Inches=Inches, Pt=Pt)


def _add_chart(slide, slot, chart_type, chart_data, Inches):  # noqa: ANN001
    left, top, width, height = slot
    return slide.shapes.add_chart(chart_type, Inches(left), Inches(top), Inches(width), Inches(height), chart_data).chart


def _grid_2x2_slots() -> list[tuple[float, float, float, float]]:
    margin_x = 0.48
    top = 0.72
    gap_x = 0.26
    gap_y = 0.28
    width = (13.333 - margin_x * 2 - gap_x) / 2
    height = (7.5 - top - 0.24 - gap_y) / 2
    return [
        (margin_x, top, width, height),
        (margin_x + width + gap_x, top, width, height),
        (margin_x, top + height + gap_y, width, height),
        (margin_x + width + gap_x, top + height + gap_y, width, height),
    ]


def _style_common_chart(chart, title: str, x_title: str, y_title: str, number_format: str, RGBColor, Pt) -> None:  # noqa: ANN001
    chart.has_title = True
    _set_text(chart.chart_title.text_frame, title, Pt(10.5), True, MELI_BLACK, RGBColor)
    chart.category_axis.has_title = True
    _set_text(chart.category_axis.axis_title.text_frame, x_title, Pt(9), False, MELI_DARK_GRAY, RGBColor)
    chart.value_axis.has_title = True
    _set_text(chart.value_axis.axis_title.text_frame, y_title, Pt(9), False, MELI_DARK_GRAY, RGBColor)
    chart.category_axis.tick_labels.font.size = Pt(8)
    chart.category_axis.tick_labels.font.color.rgb = _rgb(MELI_DARK_GRAY, RGBColor)
    chart.value_axis.tick_labels.font.size = Pt(8)
    chart.value_axis.tick_labels.font.color.rgb = _rgb(MELI_DARK_GRAY, RGBColor)
    chart.value_axis.tick_labels.number_format = number_format
    chart.value_axis.has_major_gridlines = True


def _set_text(text_frame, text: str, font_size, bold: bool, color: str, RGBColor) -> None:  # noqa: ANN001
    text_frame.clear()
    paragraph = text_frame.paragraphs[0]
    run = paragraph.add_run()
    run.text = text
    run.font.size = font_size
    run.font.bold = bold
    run.font.color.rgb = _rgb(color, RGBColor)


def _add_header(slide, title: str, RGBColor, Inches, Pt) -> None:  # noqa: ANN001
    box = slide.shapes.add_textbox(Inches(0.48), Inches(0.18), Inches(12.35), Inches(0.32))
    _set_text(box.text_frame, title, Pt(16), True, MELI_BLACK, RGBColor)


def _add_empty(slide, slot, title: str, message: str, RGBColor, Inches, Pt) -> None:  # noqa: ANN001
    left, top, width, height = slot
    title_box = slide.shapes.add_textbox(Inches(left), Inches(top + 0.04), Inches(width), Inches(0.24))
    _set_text(title_box.text_frame, title, Pt(10.5), True, MELI_BLACK, RGBColor)
    msg_box = slide.shapes.add_textbox(Inches(left), Inches(top + height / 2 - 0.1), Inches(width), Inches(0.28))
    _set_text(msg_box.text_frame, message, Pt(10), False, MELI_MEDIUM_GRAY, RGBColor)


def _add_final_label_stack(
    slide,
    slot: tuple[float, float, float, float],
    labels: list[tuple[str, object, str]],
    *,
    value_is_percent: bool,
    RGBColor,
    Inches,
    Pt,
) -> None:
    left, top, width, _height = slot
    clean = [(name, value, color) for name, value, color in labels if value is not None]
    for idx, (name, value, color) in enumerate(clean[:6]):
        text = f"{name}: {_format_ppt_value(value, percent=value_is_percent)}"
        box = slide.shapes.add_textbox(Inches(left + width - 2.15), Inches(top + 0.32 + 0.19 * idx), Inches(2.1), Inches(0.18))
        _set_text(box.text_frame, text, Pt(7.2), True, color, RGBColor)


def _style_slide(slide, RGBColor) -> None:  # noqa: ANN001
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(255, 255, 255)


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


def _duration_frame(consolidated_monitor: pd.DataFrame, fund_monitor: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    if consolidated_monitor is not None and not consolidated_monitor.empty:
        rows.extend(_duration_rows(consolidated_monitor, "Consolidado"))
    for cnpj, frame in fund_monitor.items():
        rows.extend(_duration_rows(frame, _fund_name(frame, fallback=str(cnpj))))
    if not rows:
        return pd.DataFrame()
    long = pd.DataFrame(rows)
    wide = long.pivot_table(index=["competencia_dt", "competencia"], columns="serie", values="duration_months", aggfunc="last").reset_index()
    wide.columns.name = None
    return wide.sort_values("competencia_dt").reset_index(drop=True)


def _duration_rows(frame: pd.DataFrame, label: str) -> list[dict[str, object]]:
    if frame is None or frame.empty:
        return []
    df = _chart_monthly(frame)
    values = pd.to_numeric(df.get("duration_months"), errors="coerce")
    return [
        {
            "competencia_dt": row.get("competencia_dt"),
            "competencia": row.get("competencia"),
            "serie": label,
            "duration_months": values.iloc[idx],
        }
        for idx, row in df.iterrows()
    ]


def _series_colors(series: pd.Series | list[str] | None) -> list[tuple[str, str]]:
    if series is None:
        return []
    colors = [MELI_BLACK, MELI_ORANGE, MELI_DARK_GRAY, MELI_MEDIUM_GRAY]
    names = pd.Series(series).dropna().drop_duplicates().astype(str).tolist()
    return [(name, colors[idx % len(colors)]) for idx, name in enumerate(names)]


def _chart_monthly(monthly_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(monthly_df, pd.DataFrame) or monthly_df.empty:
        return pd.DataFrame()
    df = monthly_df.copy()
    df["competencia_dt"] = pd.to_datetime(df.get("competencia_dt", df.get("competencia")), errors="coerce")
    return df.sort_values("competencia_dt").reset_index(drop=True)


def _category_labels(df: pd.DataFrame) -> list[str]:
    labels = []
    for _, row in df.iterrows():
        ts = pd.to_datetime(row.get("competencia_dt"), errors="coerce")
        labels.append(f"{PT_MONTH_ABBR[int(ts.month)]}/{str(int(ts.year))[-2:]}" if pd.notna(ts) else str(row.get("competencia") or ""))
    return labels


def _money_scale(values: pd.Series) -> tuple[float, str]:
    max_value = pd.to_numeric(values, errors="coerce").abs().max()
    if pd.isna(max_value):
        max_value = 0.0
    if max_value >= 1_000_000_000_000:
        return 1_000_000_000.0, "R$ bi"
    if max_value >= 1_000_000:
        return 1_000_000.0, "R$ mm"
    if max_value >= 1_000:
        return 1_000.0, "R$ mil"
    return 1.0, "R$"


def _chart_value(value: object, *, percent: bool) -> float | None:
    numeric = _num(value)
    if numeric is None:
        return None
    return numeric / 100.0 if percent else numeric


def _scaled_value(value: object, divisor: float) -> float | None:
    numeric = _num(value)
    return None if numeric is None else numeric / divisor


def _last_non_null(values: list[object]) -> object:
    for value in reversed(values):
        if value is not None and not pd.isna(value):
            return value
    return None


def _format_ppt_value(value: object, *, percent: bool) -> str:
    numeric = _num(value)
    if numeric is None:
        return "N/D"
    if percent:
        return f"{numeric * 100.0:.1f}%".replace(".", ",")
    return f"{numeric:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return None
    return float(parsed)


def _fund_name(frame: pd.DataFrame, *, fallback: str) -> str:
    if frame is not None and not frame.empty and "fund_name" in frame.columns and frame["fund_name"].notna().any():
        return str(frame["fund_name"].dropna().iloc[0])
    return fallback


def _rgb(hex_color: str, RGBColor):  # noqa: ANN001
    clean = str(hex_color).strip().lstrip("#")
    return RGBColor(int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))
