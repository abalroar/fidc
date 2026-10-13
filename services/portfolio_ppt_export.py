"""Native portfolio deck compositor. Inputs and financial rules belong to producers.

The renderer builds one presentation from a content plan. It does not restyle or
concatenate the old presentations. Tables, lines and sparklines remain editable.
"""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import math
import re
import textwrap
from typing import Any

import pandas as pd
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_DATA_LABEL_POSITION, XL_TICK_LABEL_POSITION, XL_MARKER_STYLE, XL_TICK_MARK
from pptx.enum.text import MSO_AUTO_SIZE, MSO_ANCHOR, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Pt

from services.portfolio_ppt_style import DEFAULT_STYLE, SNAPSHOT_SERIES_KEYS, PortfolioPptStyle, series_color


def build_portfolio_pptx_bytes(*, style: PortfolioPptStyle = DEFAULT_STYLE,
                               presentation_context=None, export_warnings=(), **inputs: Any) -> bytes:
    from services.portfolio_ppt_content import SlideSpec, TableBlock, build_portfolio_deck_spec
    from services.presentation_text import public_document_text

    if presentation_context is not None:
        inputs.setdefault("dashboard_summary_competencia", presentation_context.common_position)
    spec = build_portfolio_deck_spec(**inputs)
    reference_rows = []
    if presentation_context is not None:
        reference_rows.extend({"Referência": line.partition(": ")[0], "Contexto": line.partition(": ")[2] or line}
                              for line in presentation_context.reference_lines())
        spec = replace(spec, metadata=(*spec.metadata,
            f"Posição comum: {presentation_context.common_position}. Última observada: {presentation_context.latest_observed}."))
    reference_rows.extend({"Referência": "Parte indisponível", "Contexto": public_document_text(warning)}
                          for warning in export_warnings)
    if reference_rows:
        slide = SlideSpec("Referências", spec.context,
                          (TableBlock("Escopo, cortes e cobertura", pd.DataFrame(reference_rows)),),
                          "CVM · Informe Mensal · Fundos.NET/B3", kind="appendix")
        spec = replace(spec, slides=(*spec.slides, slide))
    if export_warnings:
        spec = replace(spec, metadata=(*spec.metadata, "Cobertura parcial. Partes indisponíveis identificadas no anexo."))
    return render_portfolio_deck(spec, style=style)


def _number(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _br(value: float, decimals: int) -> str:
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def format_cell(value: object, token: str = "text") -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return "N/D"
    if not isinstance(value, str):
        try:
            if pd.isna(value):
                return "N/D"
        except (ValueError, TypeError):
            pass
    kind, _, places = token.partition(":")
    if kind in {"money", "money_value", "number", "percent", "integer"}:
        number = _number(value)
        if number is None:
            return "N/D" if str(value).strip() in {"", "nan", "None"} else str(value)
        decimals = int(places or ("0" if kind == "integer" else "2"))
        if kind == "money":
            return f"R$ {_br(number / 1_000_000, decimals)} mm"
        if kind == "money_value":
            return _br(number / 1_000_000, decimals)
        return _br(number, decimals) + ("%" if kind == "percent" else "")
    text = str(value).strip()
    return text if text and text not in {"nan", "None", "<NA>", "NaT"} else "N/D"


def _rgb(value: str) -> RGBColor:
    return RGBColor.from_string(value.lstrip("#"))


def _text(slide, text: str, x: float, y: float, w: float, h: float, *, size: float,
          style: PortfolioPptStyle, bold: bool = False, color: str | None = None,
          align=PP_ALIGN.LEFT, wrap: bool = True):
    shape = slide.shapes.add_textbox(Pt(x), Pt(y), Pt(w), Pt(h))
    shape.name = "Texto" if not bold else "Título"
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = wrap
    frame.auto_size = MSO_AUTO_SIZE.NONE
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    for index, line in enumerate(str(text).split("\n")):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = align
        paragraph.space_after = paragraph.space_before = Pt(0)
        paragraph.line_spacing = 1.05
        run = paragraph.add_run()
        run.text = line
        run.font.name = style.font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = _rgb(color or style.text)
    return shape


def _lines(text: object, width: float, size: float) -> list[str]:
    # Conservative fit, including legal names and long documentary clauses.
    capacity = max(5, int((width - 12) / (size * 0.49)))
    return [line for paragraph in str(text).split("\n")
            for line in (textwrap.wrap(paragraph, capacity, break_long_words=True,
                                      break_on_hyphens=False) or [""])]


def _header(prs, spec, style: PortfolioPptStyle):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(style.white)
    _text(slide, spec.title, style.margin, style.title_top, style.content_width, 34,
          size=style.title_size, bold=True, style=style)
    _text(slide, spec.context, style.margin, style.context_top, style.content_width, 34,
          size=style.context_size, color=style.muted, style=style)
    source = str(spec.source or "CVM · Informe Mensal · Fundos.NET/B3")
    # The full source is retained in references and notes; this line is a reader aid.
    footer = source if len(source) <= 168 else "CVM · Informe Mensal · Fundos.NET/B3. Referências completas no anexo."
    _text(slide, footer.replace("\n", " "), style.margin, style.footer_top,
          style.content_width, 14, size=style.footer_size, color=style.muted, style=style, wrap=False)
    notes = [spec.context, source, *spec.notes]
    notes.extend(note for block in spec.blocks for note in getattr(block, "notes", ()))
    slide.notes_slide.notes_text_frame.text = "\n".join(dict.fromkeys(str(note) for note in notes if note))
    return slide


def _cover(prs, spec, style):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(style.white)
    title_lines = _lines(spec.title, style.content_width, 34)
    title_height = len(title_lines) * 39
    top = min(215, 300 - title_height)
    _text(slide, "\n".join(title_lines), style.margin, top, style.content_width,
          title_height, size=34, bold=True, style=style)
    _text(slide, spec.context, style.margin, top + title_height + 12, style.content_width,
          60, size=16, color=style.muted, style=style)
    metadata = spec.metadata if isinstance(spec.metadata, (tuple, list)) else (spec.metadata,)
    # No masthead, decorative shape or page counter.
    content = "\n".join(str(item) for item in metadata if item)
    lines = _lines(content, style.content_width, style.footer_size)
    height = len(lines) * 12
    _text(slide, "\n".join(lines), style.margin, style.footer_top - height + 12,
          style.content_width, height, size=style.footer_size, color=style.muted, style=style)
    slide.notes_slide.notes_text_frame.text = content


def _table_widths(block, width: float, style) -> list[float]:
    columns = list(block.frame.columns)
    if len(columns) == 1:
        return [width]
    numeric = set(getattr(block, "numeric_columns", ()))
    numeric.update(column for column, fmt in block.formats.items()
                   if fmt.split(":")[0] in {"number", "money", "money_value", "percent", "integer"})
    if getattr(block, "snapshot_history", None):
        # Snapshot: labels, value, comparisons, history.
        if len(columns) == 5:
            return [width * fraction for fraction in (.31, .18, .16, .16, .19)]
    weights = []
    for index, column in enumerate(columns):
        values = [str(column), *[format_cell(v, block.formats.get(column, "text")) for v in block.frame[column]]]
        length = max((len(value) for value in values), default=10)
        if index == 0:
            weights.append(min(225, max(120, length * 4.7)))
        elif column in numeric or re.search(r"[a-z]{3}/\d{2}$", str(column)):
            weights.append(min(125, max(49, length * 5.0)))
        else:
            weights.append(min(450, max(115, length * 4.8)))
    if all(column in numeric or re.search(r"[a-z]{3}/\d{2}$", str(column)) for column in columns[1:]):
        first = min(weights[0], width * .30)
        others = weights[1:]
        return [first, *[(width - first) * value / sum(others) for value in others]]
    return [width * value / sum(weights) for value in weights]


def _table_layout(block, width: float, style, *, compact=False):
    size = style.table_min_size if compact or len(block.frame.columns) > 11 else style.table_size
    widths = _table_widths(block, width, style)
    header_height = max(26, max(len(_lines(col, w, size)) for col, w in zip(block.frame.columns, widths)) * (size + 3) + 10)
    heights = []
    for _, row in block.frame.iterrows():
        lines = max(len(_lines(format_cell(value, block.formats.get(col, "text")), w, size))
                    for col, value, w in zip(block.frame.columns, row, widths))
        height = max(22 if not compact else 18, lines * (size + 3) + 7)
        if getattr(block, "snapshot_history", None):
            height = max(39, height)
        heights.append(height)
    return widths, header_height, heights, size


def _borders(cell, style, *, header=False):
    tcpr = cell._tc.get_or_add_tcPr()
    for name in ("lnL", "lnR", "lnT", "lnB"):
        for element in list(tcpr.findall("{http://schemas.openxmlformats.org/drawingml/2006/main}" + name)):
            tcpr.remove(element)
        line = OxmlElement("a:" + name)
        line.set("w", "6350")  # 0.5pt, horizontal rule only.
        if name == "lnB" and not header:
            fill = OxmlElement("a:solidFill")
            rgb = OxmlElement("a:srgbClr")
            rgb.set("val", style.grid)
            fill.append(rgb)
        else:
            fill = OxmlElement("a:noFill")
        line.append(fill)
        tcpr.append(line)


def _table(slide, block, x, y, width, *, style, compact=False):
    widths, header_h, heights, size = _table_layout(block, width, style, compact=compact)
    if block.title:
        _text(slide, block.title, x, y, width, 19, size=style.section_size, bold=True, style=style)
        y += 25
    table = slide.shapes.add_table(len(block.frame) + 1, len(block.frame.columns),
                                   Pt(x), Pt(y), Pt(width), Pt(header_h + sum(heights))).table
    table.first_row = table.horz_banding = table.vert_banding = False
    for column, column_width in zip(table.columns, widths):
        column.width = Pt(column_width)
    for row, height in zip(table.rows, [header_h, *heights]):
        row.height = Pt(height)
    numeric = set(getattr(block, "numeric_columns", ()))
    history = getattr(block, "snapshot_history", {}) or {}
    colors = getattr(block, "cell_colors", {}) or {}
    values = [list(block.frame.columns), *block.frame.values.tolist()]
    for row_index, row_values in enumerate(values):
        for column_index, (column, value) in enumerate(zip(block.frame.columns, row_values)):
            cell = table.cell(row_index, column_index)
            token = block.formats.get(column, "text")
            cell.text = str(value) if row_index == 0 else format_cell(value, token)
            cell.fill.solid()
            cell.fill.fore_color.rgb = _rgb(style.orange if row_index == 0 else style.white)
            cell.margin_left = cell.margin_right = Pt(6)
            cell.margin_top = cell.margin_bottom = Pt(3)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.text_frame.word_wrap = True
            cell.text_frame.auto_size = MSO_AUTO_SIZE.NONE
            is_numeric = column in numeric or token.split(":")[0] in {"money", "money_value", "number", "percent", "integer"}
            if row_index and is_numeric:
                cell.text_frame.word_wrap = False
            for paragraph in cell.text_frame.paragraphs:
                paragraph.alignment = PP_ALIGN.RIGHT if column_index > 0 and is_numeric else PP_ALIGN.LEFT
                paragraph.space_before = paragraph.space_after = Pt(0)
                paragraph.line_spacing = 1.02
                for run in paragraph.runs:
                    run.font.name = style.font
                    run.font.size = Pt(size if not history or row_index == 0 else 13 if column_index == 1 else 11)
                    run.font.bold = row_index == 0 or column_index == 0 or bool(history and column_index == 1)
                    color = colors.get((row_index - 1, column), style.text)
                    color = {"good": style.good, "bad": style.bad, "neutral": style.muted}.get(color, color)
                    run.font.color.rgb = _rgb(style.white if row_index == 0 else color)
            _borders(cell, style, header=row_index == 0)
    if history:
        offset_y = y + header_h
        for row_index, height in enumerate(heights):
            label = str(block.frame.iloc[row_index, 0])
            series = history.get(label)
            if series:
                table.cell(row_index + 1, len(widths) - 1).text = ""
                data = [_number(value) for value in series]
                finite = [value for value in data if value is not None]
                hx, hw = x + sum(widths[:-1]) + 7, widths[-1] - 14
                if finite and len(finite) == len(data) and len({_br(v, 1) for v in finite}) == 1:
                    caption = "1 observação" if len(data) == 1 else "Constante no período"
                    _text(slide, caption, hx, offset_y + (height - 15) / 2,
                          hw, 17, size=9.5, color=style.muted, style=style)
                elif finite:
                    table.cell(row_index + 1, len(widths) - 1).text = ""
                    _sparkline(slide, data, hx, offset_y + 6, hw, height - 12, style,
                               key=SNAPSHOT_SERIES_KEYS.get(label, label))
            offset_y += height
    return header_h + sum(heights) + (25 if block.title else 0)


def _sparkline(slide, values, x, y, w, h, style, *, key=""):
    data = CategoryChartData()
    data.categories = [str(i) for i in range(len(values))]
    data.add_series("Evolução", values)
    chart = slide.shapes.add_chart(XL_CHART_TYPE.LINE, Pt(x), Pt(y), Pt(w), Pt(h), data).chart
    chart.has_legend = chart.has_title = False
    chart.category_axis.visible = chart.value_axis.visible = False
    chart.category_axis.major_tick_mark = chart.value_axis.major_tick_mark = XL_TICK_MARK.NONE
    chart.value_axis.has_major_gridlines = False
    finite = [v for v in values if v is not None]
    lo, hi = _bounds(finite)
    chart.value_axis.minimum_scale, chart.value_axis.maximum_scale = lo, hi
    chart.series[0].format.line.color.rgb = _rgb(series_color(key, style) if key else style.muted)
    chart.series[0].format.line.width = Pt(1.4)
    chart.series[0].marker.style = XL_MARKER_STYLE.NONE
    _chart_layout(chart, .02, .02, .95, .94)
    _chart_gaps(chart)


def _bounds(values):
    lo, hi = min(values), max(values)
    span = hi - lo
    padding = span * .14 if span else max(abs(hi) * .06, .1)
    return max(0, lo - padding) if lo >= 0 else lo - padding, hi + padding


def _axis_bounds(values):
    lo, hi = min(values), max(values)
    raw = (hi - lo) / 5
    power = 10 ** math.floor(math.log10(raw))
    step = next(factor * power for factor in (1, 2, 2.5, 5, 10) if factor * power >= raw)
    lower, upper = math.floor(lo / step) * step, math.ceil(hi / step) * step
    if math.isclose(upper, hi):
        upper += step
    if math.isclose(lower, lo) and lo != 0:
        lower -= step
    if lo >= 0:
        lower = max(0, lower)
    decimals = max(0, -math.floor(math.log10(step)))
    if not math.isclose(step * 10 ** decimals, round(step * 10 ** decimals)):
        decimals += 1
    return lower, upper, step, decimals


def _chart_layout(chart, x, y, w, h):
    area = chart._chartSpace.xpath(".//c:plotArea")[0]
    layouts = area.xpath("./c:layout")
    layout = layouts[0] if layouts else OxmlElement("c:layout")
    if not layouts:
        area.insert(0, layout)
    manual = OxmlElement("c:manualLayout")
    for name, value in (("layoutTarget", "inner"), ("xMode", "edge"), ("yMode", "edge"),
                        ("wMode", "factor"), ("hMode", "factor"),
                        ("x", x), ("y", y), ("w", w), ("h", h)):
        element = OxmlElement("c:" + name)
        element.set("val", str(value))
        manual.append(element)
    layout.append(manual)


def _chart_gaps(chart):
    main = chart._chartSpace.xpath("./c:chart")[0]
    elements = main.xpath("./c:dispBlanksAs")
    gaps = elements[0] if elements else OxmlElement("c:dispBlanksAs")
    gaps.set("val", "gap")
    if not elements:
        main.append(gaps)


def _endpoint_positions(endpoints, lo, hi, plot_y, plot_h, label_h=27):
    """Repel labels in a dedicated right lane; retain their series identity."""
    ordered = sorted(((index, plot_y + plot_h * (hi - value) / (hi - lo))
                      for index, value in endpoints), key=lambda item: item[1])
    output = {}
    last = plot_y - label_h
    for index, natural in ordered:
        y = max(natural - label_h / 2, last + label_h)
        output[index] = y
        last = y
    if ordered:
        excess = max(0, last + label_h - (plot_y + plot_h))
        for index in output:
            output[index] -= excess
    return output


def _chart(slide, block, x, y, width, height, style):
    _text(slide, block.title, x, y, width, 22, size=style.section_size, bold=True, style=style)
    series = [(s, [_number(v) for v in s.values]) for s in block.series]
    variable = [(s, vals) for s, vals in series if len({_br(v, s.decimals) for v in vals if v is not None}) > 1]
    constant = [(s, vals) for s, vals in series if vals and any(v is not None for v in vals)
                and len({_br(v, s.decimals) for v in vals if v is not None}) == 1]
    missing = [s for s, vals in series if not any(v is not None for v in vals)]
    subtitle_lines = []
    for spec, vals in constant:
        valid = [v for v in vals if v is not None]
        value = _br(valid[0], spec.decimals) + ("%" if spec.unit == "%" else " " + spec.unit)
        qualifier = ("1 observação válida" if len(valid) == 1 else
                     "Constante nas observações disponíveis" if any(v is None for v in vals) else
                     "Constante à precisão exibida")
        subtitle_lines.append(f"{spec.label}: {value}. {qualifier}.")
    if missing:
        subtitle_lines.append("Sem dados: " + ", ".join(s.label for s in missing) + ".")
    if subtitle_lines:
        text_height = len(_lines("\n".join(subtitle_lines), width, 10)) * 13
        _text(slide, "\n".join(subtitle_lines), x, y + 26, width, text_height,
              size=10, color=style.muted, style=style)
        y += text_height + 6
        height -= text_height + 6
    if not variable:
        return
    chart_y = y + 27
    chart_h = height - 60
    label_w = min(120, width * .27)
    plot_chart_w = width - label_w
    data = CategoryChartData()
    # Hierarchical native categories keep month positions tied to the data and
    # show each year once on the second axis row.
    parsed_categories = [str(label).split("/") for label in block.categories]
    hierarchical = bool(parsed_categories) and all(len(parts) == 2 for parts in parsed_categories)
    if hierarchical:
        year_category = None
        previous_year = None
        for month, year in parsed_categories:
            year = "20" + year if len(year) == 2 else year
            if year != previous_year:
                year_category = data.categories.add_category(year)
                previous_year = year
            year_category.add_sub_category(month)
    else:
        data.categories = list(block.categories)
    for spec, vals in variable:
        data.add_series(spec.label, vals)
    chart = slide.shapes.add_chart(XL_CHART_TYPE.LINE, Pt(x), Pt(chart_y), Pt(plot_chart_w), Pt(chart_h), data).chart
    chart.has_legend = chart.has_title = False
    chart.font.name, chart.font.size = style.font, Pt(style.chart_size)
    values = [v for _, vals in variable for v in vals if v is not None]
    lo, hi, major_unit, tick_decimals = _axis_bounds(values)
    axis = chart.value_axis
    axis.minimum_scale, axis.maximum_scale = lo, hi
    axis.major_unit = major_unit
    axis.tick_labels.font.name = style.font
    axis.tick_labels.font.size = Pt(style.chart_size)
    axis.tick_labels.font.color.rgb = _rgb(style.muted)
    number_format = "[$-416]0" + ("." + "0" * tick_decimals if tick_decimals else "")
    axis.tick_labels.number_format = number_format + ('"%"' if block.unit == "%" else "")
    axis.has_major_gridlines = True
    axis.major_gridlines.format.line.color.rgb = _rgb(style.grid)
    axis.major_gridlines.format.line.width = Pt(.5)
    axis.format.line.fill.background()
    axis.major_tick_mark = axis.minor_tick_mark = XL_TICK_MARK.NONE
    chart.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
    chart.category_axis.tick_labels.font.name = style.font
    chart.category_axis.tick_labels.font.size = Pt(10)
    chart.category_axis.tick_labels.font.color.rgb = _rgb(style.muted)
    chart.category_axis.tick_label_spacing = max(1, math.ceil(len(block.categories) / (18 if width > 600 else 13)))
    chart.category_axis.format.line.fill.background()
    chart.category_axis.major_tick_mark = chart.category_axis.minor_tick_mark = XL_TICK_MARK.NONE
    _chart_gaps(chart)
    for native, (spec, _) in zip(chart.series, variable):
        native.format.line.color.rgb = _rgb(series_color(spec.key, style))
        native.format.line.width = Pt(style.line_width)
        native.marker.style = XL_MARKER_STYLE.NONE
        native.smooth = False
    plot_y, plot_h = chart_y + chart_h * .04, chart_h * .90
    endpoints = [(index, next(v for v in reversed(vals) if v is not None))
                 for index, (_, vals) in enumerate(variable)]
    for index, endpoint in endpoints:
        spec, vals = variable[index]
        suffix = "%" if spec.unit == "%" else (" " + spec.unit if spec.unit else "")
        short_label = _short_series_label(spec.label)
        label = _br(endpoint, spec.decimals) + suffix + "\n" + short_label
        last_index = max(i for i, v in enumerate(vals) if v is not None)
        if last_index < len(vals) - 1:
            label += " (" + str(block.categories[last_index]) + ")"
        # A native point label stays part of the editable chart. Close final
        # values use opposite sides of the points to retain both names.
        native_label = chart.series[index].points[last_index].data_label
        native_label.position = XL_DATA_LABEL_POSITION.RIGHT
        close = [other_index for other_index, other in endpoints
                 if other_index != index and abs(other - endpoint) / (hi - lo) < .10]
        if close:
            native_label.position = XL_DATA_LABEL_POSITION.ABOVE if index < min(close) else XL_DATA_LABEL_POSITION.BELOW
        native_label.has_text_frame = True
        frame = native_label.text_frame
        frame.clear()
        frame.word_wrap = False
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
        for line_index, line in enumerate(label.split("\n")):
            paragraph = frame.paragraphs[0] if not line_index else frame.add_paragraph()
            paragraph.space_before = paragraph.space_after = Pt(0)
            run = paragraph.add_run()
            run.text = line
            run.font.name, run.font.size, run.font.bold = style.font, Pt(style.chart_size), True
            run.font.color.rgb = _rgb(series_color(spec.key, style))
    # Native hierarchical labels remain horizontal, including narrow plots.
    for body in chart._chartSpace.xpath(".//c:catAx/c:txPr/a:bodyPr"):
        body.set("rot", "0")


def _short_series_label(label):
    return {
        "Inadimplência / direitos creditórios": "Vencidos",
        "Provisão / direitos creditórios": "Provisão",
        "Cobertura provisão / vencidos": "PDD / vencidos",
        "Cobertura PDD / NPL > 90d ex-360": "PDD / NPL >90d",
        "NPL > 1d ex-360": ">1d", "NPL > 30d ex-360": ">30d",
        "NPL > 60d ex-360": ">60d", "NPL > 90d ex-360": ">90d",
        "PL total": "PL", "Carteira bruta ex-360": "Carteira ex-360",
    }.get(label, label)


def _fits_horizontally(block, width, style):
    widths, _, _, size = _table_layout(block, width, style)
    for index, (column, allotted) in enumerate(zip(block.frame.columns, widths)):
        token = block.formats.get(column, "text").split(":")[0]
        numeric = column in block.numeric_columns or token in {"number", "money", "money_value", "percent", "integer"}
        month = bool(re.fullmatch(r"[a-z]{3}/\d{2}", str(column)))
        if numeric or month:
            font_size = 13 if block.snapshot_history and index == 1 else size
            length = max((len(format_cell(value, block.formats.get(column, "text"))) for value in block.frame[column]), default=0)
            required = max(48 if month else 0, length * font_size * .56 + 12)
            if allotted + .01 < required:
                return False
    return True


def _table_chunks(block, style, width=None, height=None):
    width = width or style.content_width
    height = height or style.content_bottom - style.content_top
    columns = list(block.frame.columns)
    # Repeat the identity column when a dense matrix needs another page.
    mostly_numeric = all(column in block.numeric_columns or block.formats.get(column, "text").split(":")[0] in {"number", "money", "money_value", "percent", "integer"}
                         for column in columns[1:])
    max_columns = style.month_columns + 1 if len(columns) > 10 or mostly_numeric else 5
    while max_columns > 2 and not _fits_horizontally(replace(block, frame=block.frame.loc[:, columns[:max_columns]]), width, style):
        max_columns -= 1
    groups = [columns] if len(columns) <= max_columns else [[columns[0], *columns[i:i + max_columns - 1]]
              for i in range(1, len(columns), max_columns - 1)]
    for cols in groups:
        selected = replace(block, frame=block.frame.loc[:, cols])
        start = 0
        while start < len(selected.frame):
            end = start
            for candidate_end in range(start + 1, len(selected.frame) + 1):
                candidate = replace(selected, frame=selected.frame.iloc[start:candidate_end])
                widths, header_h, heights, _ = _table_layout(candidate, width, style)
                if header_h + sum(heights) + (25 if block.title else 0) <= height:
                    end = candidate_end
                else:
                    break
            if end > start:
                yield replace(selected, frame=selected.frame.iloc[start:end])
                start = end
            else:
                # Split clauses too long for one page using that page's actual
                # column widths. Re-measuring a segment avoids height drift.
                single = replace(selected, frame=selected.frame.iloc[start:start + 1])
                widths, header_h, _, _ = _table_layout(single, width, style)
                available = height - header_h - (25 if block.title else 0)
                row = selected.frame.iloc[start]
                chunks = [textwrap.wrap(format_cell(value, selected.formats.get(col, "text")),
                                       max(12, int((w - 12) / (style.table_size * .49) * max(1, int(available / 15) - 3))),
                                       break_long_words=True, break_on_hyphens=False) or [""]
                          for col, value, w in zip(cols, row, widths)]
                for part in range(max(map(len, chunks))):
                    values = [pieces[part] if part < len(pieces) else "" for pieces in chunks]
                    values[0] = str(row.iloc[0]) if part else values[0]
                    yield replace(selected, frame=pd.DataFrame([values], columns=cols), formats={})
                start += 1
        if selected.frame.empty:
            yield selected


def render_portfolio_deck(spec, *, style=DEFAULT_STYLE) -> bytes:
    from services.portfolio_ppt_content import ChartBlock, TableBlock, TextBlock

    prs = Presentation()
    prs.slide_width, prs.slide_height = Pt(style.width), Pt(style.height)
    prs.core_properties.title = spec.title
    prs.core_properties.author = "Toma Conta"
    _cover(prs, spec, style)
    pages = []
    for page in spec.slides:
        if pages and page.kind == "appendix" and (page.title, page.context, page.source) == (pages[-1].title, pages[-1].context, pages[-1].source):
            pages[-1] = replace(pages[-1], blocks=(*pages[-1].blocks, *page.blocks), notes=(*pages[-1].notes, *page.notes))
        elif pages and page.kind == "content" and page.title == "Rentabilidade" == pages[-1].title:
            previous = pages[-1]
            if not previous.context.startswith(spec.context):
                entity = previous.context.split(" · ")[0]
                previous = replace(previous, context=spec.context,
                                   blocks=tuple(replace(block, title=f"{entity} · {block.title}") if isinstance(block, TableBlock) else block for block in previous.blocks))
            entity = page.context.split(" · ")[0]
            pages[-1] = replace(previous, blocks=(*previous.blocks, *(replace(block, title=f"{entity} · {block.title}") if isinstance(block, TableBlock) else block for block in page.blocks)), notes=(*previous.notes, *page.notes))
        else:
            pages.append(page)
    for page in pages:
        blocks = []
        for block in page.blocks:
            if (blocks and isinstance(block, TextBlock) and isinstance(blocks[-1], TextBlock)
                    and block.title == blocks[-1].title):
                blocks[-1] = replace(blocks[-1], text=f"{blocks[-1].text}\n{block.text}")
            else:
                blocks.append(block)
        charts = [block for block in blocks if isinstance(block, ChartBlock)]
        tables = [block for block in blocks if isinstance(block, TableBlock)]
        texts = [block for block in blocks if isinstance(block, TextBlock)]
        if page.title == "Ficha documental" and len(tables) == 2 and len(tables[0].frame) == 1:
            position = tables[0]
            values = position.frame.iloc[0]
            position = replace(position, frame=pd.DataFrame({"Posição documental": list(position.frame.columns), "Informação": list(values)}), formats={}, numeric_columns=())
            clauses = tables[1]
            left_w = style.content_width * .66
            right_w = style.content_width - left_w - style.gap
            _, lh, lr, _ = _table_layout(clauses, left_w, style)
            _, rh, rr, _ = _table_layout(position, right_w, style)
            table_h = max(lh + sum(lr) + 25, rh + sum(rr) + 25)
            text_h = sum(len(_lines(block.text, style.content_width, 10)) * 13 + 12 for block in texts)
            if table_h + text_h <= style.content_bottom - style.content_top:
                slide = _header(prs, page, style)
                _table(slide, clauses, style.margin, style.content_top, left_w, style=style)
                _table(slide, position, style.margin + left_w + style.gap, style.content_top, right_w, style=style)
                y = style.content_top + table_h + 10
                for block in texts:
                    height = len(_lines(block.text, style.content_width, 10)) * 13
                    _text(slide, block.text, style.margin, y, style.content_width, height,
                          size=10, color=style.muted, style=style)
                    y += height + 12
                continue
        if not charts and (tables or texts):
            # Pack compatible blocks in reading order. Horizontal validation
            # precedes packing, so financial digits and month names stay whole.
            slide = None
            y = style.content_top
            for block in blocks:
                if isinstance(block, TableBlock):
                    segments = list(_table_chunks(block, style))
                    for segment in segments:
                        _, header_h, rows, _ = _table_layout(segment, style.content_width, style)
                        height = header_h + sum(rows) + (25 if segment.title else 0)
                        if slide is None or y + height > style.content_bottom:
                            slide = _header(prs, page, style)
                            y = style.content_top
                        _table(slide, segment, style.margin, y, style.content_width, style=style)
                        y += height + 12
                else:
                    lines = _lines(block.text, style.content_width, style.table_size)
                    for start in range(0, len(lines), 22):
                        visible = lines[start:start + 22]
                        height = len(visible) * 14 + (25 if block.title else 0)
                        if slide is None or y + height > style.content_bottom:
                            slide = _header(prs, page, style)
                            y = style.content_top
                        if block.title:
                            _text(slide, block.title, style.margin, y, style.content_width, 22,
                                  size=style.section_size, bold=True, style=style)
                            y += 25
                        _text(slide, "\n".join(visible), style.margin, y, style.content_width, len(visible) * 14,
                              size=style.table_size, color=style.muted if page.kind == "appendix" else style.text, style=style)
                        y += len(visible) * 14 + 12
            continue
        # A short constant observation or documentary absence shares its slide
        # with the table/plot it qualifies.
        if len(tables) == 1 and texts and not charts:
            _, head, row_heights, _ = _table_layout(tables[0], style.content_width, style)
            table_h = head + sum(row_heights) + (25 if tables[0].title else 0)
            text_heights = [len(_lines(t.text, style.content_width, style.table_size)) * 14 + (25 if t.title else 0) for t in texts]
            if table_h + sum(text_heights) + 12 * len(texts) <= style.content_bottom - style.content_top:
                slide = _header(prs, page, style)
                _table(slide, tables[0], style.margin, style.content_top, style.content_width, style=style)
                y = style.content_top + table_h + 12
                for block, text_h in zip(texts, text_heights):
                    if block.title:
                        _text(slide, block.title, style.margin, y, style.content_width, 22,
                              size=style.section_size, bold=True, style=style)
                        y += 25
                    _text(slide, block.text, style.margin, y, style.content_width, text_h,
                          size=style.table_size, color=style.muted, style=style)
                    y += text_h + 12
                continue
        if len(charts) == 1 and texts and not tables:
            text_h = sum(len(_lines(t.text, style.content_width, 11)) * 14 + 25 for t in texts)
            if text_h <= 90:
                slide = _header(prs, page, style)
                plot_h = style.content_bottom - style.content_top - text_h - 12
                _chart(slide, charts[0], style.margin, style.content_top, style.content_width, plot_h, style)
                y = style.content_top + plot_h + 12
                for block in texts:
                    _text(slide, block.title, style.margin, y, style.content_width, 20,
                          size=style.section_size, bold=True, style=style)
                    y += 25
                    height = len(_lines(block.text, style.content_width, 11)) * 14
                    _text(slide, block.text, style.margin, y, style.content_width, height,
                          size=11, color=style.muted, style=style)
                    y += height + 6
                continue
        # Common thematic composition: two aligned plots and a compact matrix.
        can_pair = len(charts) == 2 and len(tables) <= 1 and not texts and all(len(c.series) <= style.chart_series_limit for c in charts)
        if can_pair and tables:
            _, head, rows, _ = _table_layout(tables[0], style.content_width, style, compact=True)
            can_pair = head + sum(rows) + (25 if tables[0].title else 0) <= 192
        if can_pair:
            slide = _header(prs, page, style)
            half = (style.content_width - style.gap) / 2
            chart_height = 173 if tables else 330
            for index, chart in enumerate(charts):
                _chart(slide, chart, style.margin + index * (half + style.gap), style.content_top,
                       half, chart_height, style)
            if tables:
                _table(slide, tables[0], style.margin, style.content_top + chart_height + 8,
                       style.content_width, style=style, compact=True)
            continue
        # Combine thin compatible tables vertically before allocating another slide.
        if tables and not charts and not texts:
            heights = []
            for block in tables:
                _, header_h, rows, _ = _table_layout(block, style.content_width, style)
                heights.append(header_h + sum(rows) + (25 if block.title else 0))
            if sum(heights) + style.gap * (len(tables) - 1) <= style.content_bottom - style.content_top:
                slide = _header(prs, page, style)
                y = style.content_top
                for block, height in zip(tables, heights):
                    _table(slide, block, style.margin, y, style.content_width, style=style)
                    y += height + style.gap
                continue
        for block in blocks:
            if isinstance(block, TableBlock):
                for segment in _table_chunks(block, style):
                    slide = _header(prs, replace(page, blocks=(segment,)), style)
                    _table(slide, segment, style.margin, style.content_top, style.content_width, style=style)
            elif isinstance(block, ChartBlock):
                for start in range(0, len(block.series), style.chart_series_limit):
                    selected = replace(block, series=block.series[start:start + style.chart_series_limit])
                    slide = _header(prs, replace(page, blocks=(selected,)), style)
                    _chart(slide, selected, style.margin, style.content_top, style.content_width,
                           style.content_bottom - style.content_top, style)
            elif isinstance(block, TextBlock):
                lines = _lines(block.text, style.content_width, style.table_size)
                max_lines = 24
                for start in range(0, len(lines), max_lines):
                    slide = _header(prs, replace(page, blocks=(block,)), style)
                    top = style.content_top
                    if block.title:
                        _text(slide, block.title, style.margin, top, style.content_width, 24,
                              size=style.section_size, bold=True, style=style)
                        top += 32
                    _text(slide, "\n".join(lines[start:start + max_lines]), style.margin, top,
                          style.content_width, style.content_bottom - top, size=style.table_size, style=style)
    stream = BytesIO()
    prs.save(stream)
    return stream.getvalue()
