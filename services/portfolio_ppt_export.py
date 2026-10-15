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
from pptx.enum.chart import XL_CHART_TYPE, XL_DATA_LABEL_POSITION, XL_LEGEND_POSITION, XL_TICK_LABEL_POSITION, XL_MARKER_STYLE, XL_TICK_MARK
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.text import MSO_AUTO_SIZE, MSO_ANCHOR, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Pt

from services.portfolio_ppt_style import DEFAULT_STYLE, SNAPSHOT_SERIES_KEYS, PortfolioPptStyle, series_color


def build_portfolio_pptx_bytes(*, style: PortfolioPptStyle = DEFAULT_STYLE,
                               presentation_context=None, export_warnings=(),
                               table_placement: str = "inline", section_dividers: str = "auto",
                               **inputs: Any) -> bytes:
    """Compose the portfolio deck.

    ``table_placement``: ``"inline"`` puts each theme's series right after its
    charts (pre-read); ``"appendix"`` moves every series table to an appendix
    in the same theme order (live presentation).
    ``section_dividers``: ``"auto"`` adds dividers only to long decks,
    ``"always"`` or ``"never"`` force the choice.
    ``fund_annex`` (in ``inputs``): ``"auto"`` keeps the per-fund annex up to
    ``FUND_ANNEX_MAX_FUNDS`` funds and summarizes it (one row per fund) above;
    ``"full"`` or ``"summary"`` force the choice.
    """
    from services.portfolio_ppt_content import build_portfolio_deck_spec

    reference_lines = ()
    if presentation_context is not None:
        inputs.setdefault("dashboard_summary_competencia", presentation_context.common_position)
        reference_lines = tuple(presentation_context.reference_lines())
    spec = build_portfolio_deck_spec(**inputs, table_placement=table_placement,
                                     reference_lines=reference_lines, export_warnings=tuple(export_warnings))
    if presentation_context is not None:
        spec = replace(spec, metadata=(*spec.metadata,
            f"Posição comum: {presentation_context.common_position}. Última observada: {presentation_context.latest_observed}."))
    if export_warnings:
        spec = replace(spec, metadata=(*spec.metadata, "Cobertura parcial. Partes indisponíveis identificadas em Referências e cobertura."))
    return render_portfolio_deck(spec, style=style, section_dividers=section_dividers)


def _number(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _br(value: float, decimals: int) -> str:
    if round(value, decimals) == 0:
        value = 0.0  # never "-0,0"
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
        scaled = number / 1_000_000 if kind in {"money", "money_value"} else number
        if abs(round(scaled, decimals)) >= 1000:
            # Four or more integer digits: decimals add width, not information,
            # and push a 13-month table onto two slides.
            decimals = 0
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


def _lines(text: object, width: float, size: float, *, bold: bool = False) -> list[str]:
    # Conservative fit, including legal names and long documentary clauses.
    # Bold labels (first column, headers) are wider, often in capitals.
    capacity = max(5, int((width - 12) / (size * (0.56 if bold else 0.49))))
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


_NUMERIC_TOKENS = {"number", "money", "money_value", "percent", "integer"}


def _is_numeric_column(block, column) -> bool:
    token = block.formats.get(column, "text").split(":")[0]
    return (column in set(getattr(block, "numeric_columns", ())) or token in _NUMERIC_TOKENS
            or bool(re.fullmatch(r"[a-z]{3}/\d{2}", str(column))))


def _table_widths(block, width: float, style) -> list[float]:
    """Natural widths: about 56–110pt per numeric column and the label column
    sized by its text. Narrow tables are not stretched to the slide width;
    only wrapping text columns absorb free space."""
    columns = list(block.frame.columns)
    if len(columns) == 1:
        return [width]
    if getattr(block, "snapshot_history", None):
        fractions = {5: (.31, .18, .16, .16, .19), 4: (.36, .20, .20, .24), 3: (.44, .26, .30)}.get(len(columns))
        if fractions:
            return [width * fraction for fraction in fractions]
    size = style.table_min_size if getattr(block, "compact", False) else style.table_size
    weights, wants = [], []
    for index, column in enumerate(columns):
        values = [str(column), *[format_cell(v, block.formats.get(column, "text")) for v in block.frame[column]]]
        length = max((len(value) for value in values), default=10)
        if index == 0:
            # Bold label column: same character width as the line estimate.
            natural = length * size * .56 + 14
            weights.append(min(225, max(110, natural)))
        elif _is_numeric_column(block, column):
            natural = length * size * .56 + 14
            weights.append(min(110, max(56, natural)))
        else:
            natural = length * size * .49 + 14
            weights.append(min(450, max(115, natural)))
        wants.append(max(0.0, natural - weights[-1]))
    total = sum(weights)
    if total > width:
        if all(_is_numeric_column(block, column) for column in columns[1:]):
            first = min(weights[0], width * .30)
            others = weights[1:]
            return [first, *[(width - first) * value / sum(others) for value in others]]
        return [width * value / total for value in weights]
    spare = width - total
    hungry = [index for index, want in enumerate(wants) if want > 0 and (index == 0 or not _is_numeric_column(block, columns[index]))]
    if hungry:
        need = sum(wants[index] for index in hungry)
        for index in hungry:
            weights[index] += spare * min(1.0, need / spare) * wants[index] / need
    return weights


def _table_layout(block, width: float, style, *, compact=False):
    compact = compact or getattr(block, "compact", False)
    size = style.table_min_size if compact or len(block.frame.columns) > 11 else style.table_size
    widths = _table_widths(block, width, style)
    header_height = max(24, max(len(_lines(col, w, size, bold=True)) for col, w in zip(block.frame.columns, widths)) * size * 1.2 + 8)
    heights = []
    for _, row in block.frame.iterrows():
        lines = max(len(_lines(format_cell(value, block.formats.get(col, "text")), w, size, bold=index == 0))
                    for index, (col, value, w) in enumerate(zip(block.frame.columns, row, widths)))
        # Line height ≈ 1.2 × size plus the 2pt cell margins, as rendered; a
        # lower estimate lets a long table run into the footer.
        height = max(16.5 if size <= 10 else 21, lines * size * 1.2 + 4.5)
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
    width = sum(widths)
    if block.title:
        _text(slide, block.title, x, y, width, 19, size=style.section_size, bold=True, style=style)
        y += 22
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
            cell.margin_top = cell.margin_bottom = Pt(2)
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
    return header_h + sum(heights) + (22 if block.title else 0)


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


def _axis_cap(values):
    """Cap the axis when one or two spikes flatten the rest of the series
    (e.g. a coverage ratio over a near-zero denominator). Outliers lie beyond
    the Tukey far-out fence (3×IQR) of the remaining values and are at least
    1.5× the highest of them. The fence is measured without the candidates,
    so two spikes in a short series cannot hide each other."""
    finite = sorted(v for v in values if v is not None)
    if len(finite) < 8:
        return None
    for count in (2, 1):
        regular, outliers = finite[:-count], finite[-count:]
        q1, q3 = regular[len(regular) // 4], regular[(3 * len(regular)) // 4]
        fence = q3 + 3 * (q3 - q1)
        if regular[-1] > 0 and outliers[0] > fence and outliers[0] >= 1.5 * regular[-1]:
            _, upper, _, _ = _axis_bounds([regular[0], regular[-1] * 1.1])
            return upper
    return None


def _chart_notes(block):
    """Sentences printed above the plot: constant series, empty series and a
    capped axis. They are computed before drawing so paired panels can share
    one band and start their plots at the same height."""
    series = [(s, [_number(v) for v in s.values]) for s in block.series]
    variable = [(s, vals) for s, vals in series
                if s.reference or len({_br(v, s.decimals) for v in vals if v is not None}) > 1
                or (block.kind == "bar" and any(v is not None for v in vals))]
    lines = []
    for spec, vals in series:
        if spec.reference or (spec, vals) in variable:
            continue
        valid = [v for v in vals if v is not None]
        suffix = "%" if spec.unit == "%" else " " + spec.unit
        if not valid:
            lines.append(f"Sem dados: {spec.label}.")
        else:
            qualifier = ("1 observação válida" if len(valid) == 1 else
                         "constante nas observações disponíveis" if any(v is None for v in vals) else "constante no período")
            lines.append(f"{spec.label}: {_br(valid[0], spec.decimals)}{suffix}, {qualifier}.")
    cap = None
    if block.kind == "line":
        drawn = [v for s, vals in variable if not s.reference for v in vals if v is not None]
        cap = _axis_cap(drawn)
        if cap is not None:
            peaks = [(v, block.categories[i], s) for s, vals in variable if not s.reference
                     for i, v in enumerate(vals) if v is not None and v > cap]
            text = "; ".join(f"{_br(v, s.decimals)}{'%' if s.unit == '%' else ''} em {month}" for v, month, s in peaks)
            lines.append(f"Eixo limitado a {_br(cap, 0)}{'%' if block.unit == '%' else ''} para legibilidade; pico de {text}.")
    return variable, lines, cap


def _band_height(lines, width):
    return len(_lines("\n".join(lines), width, 10)) * 13 + 4 if lines else 0


def _kpi(slide, block, x, y, width, height, style):
    _text(slide, block.title, x, y, width, 22, size=style.section_size, bold=True, style=style)
    lines = _lines(block.text, width, 13)
    _text(slide, "\n".join(lines), x, y + 30, width, min(height - 30, len(lines) * 18),
          size=13, color=style.muted, style=style)


def _chart(slide, block, x, y, width, height, style, *, band=None):
    _text(slide, block.title, x, y, width, 22, size=style.section_size, bold=True, style=style)
    variable, lines, cap = _chart_notes(block)
    own_band = _band_height(lines, width)
    if lines:
        _text(slide, "\n".join(_lines("\n".join(lines), width, 10)), x, y + 24, width, own_band,
              size=10, color=style.muted, style=style)
    band = own_band if band is None else max(band, own_band)
    if not [s for s, _ in variable if not s.reference]:
        return
    chart_y = y + 26 + band
    chart_h = height - 26 - band
    if block.kind == "bar":
        _bar_chart(slide, block, variable, x, chart_y, width, chart_h, style)
        return
    data = CategoryChartData()
    # Hierarchical native categories keep month positions tied to the data and
    # show each year once on the second axis row.
    parsed_categories = [str(label).split("/") for label in block.categories]
    hierarchical = bool(parsed_categories) and all(len(parts) == 2 for parts in parsed_categories)
    if hierarchical:
        previous_year = None
        year_category = None
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
    # The plot fills the column; only a narrow lane on the right is kept for
    # the end values.
    chart = slide.shapes.add_chart(XL_CHART_TYPE.LINE, Pt(x), Pt(chart_y), Pt(width), Pt(chart_h), data).chart
    chart.has_title = False
    drawn = [s for s, _ in variable]
    chart.has_legend = len(drawn) > 1
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(10)
        chart.legend.font.name = style.font
        chart.legend.font.color.rgb = _rgb(style.muted)
    chart.font.name, chart.font.size = style.font, Pt(style.chart_size)
    values = [v for s, vals in variable if not s.reference for v in vals if v is not None]
    references = [v for s, vals in variable if s.reference for v in vals if v is not None]
    if cap is not None:
        values = [v for v in values if v <= cap]
    if references and cap is None:
        values = [*values, *references]
    lo, hi, major_unit, tick_decimals = _axis_bounds(values)
    if cap is not None:
        hi = max(hi, cap)
    axis = chart.value_axis
    axis.minimum_scale, axis.maximum_scale = lo, hi
    axis.major_unit = major_unit
    axis.tick_labels.font.name = style.font
    axis.tick_labels.font.size = Pt(style.chart_size)
    axis.tick_labels.font.color.rgb = _rgb(style.muted)
    number_format = "[$-416]#,##0" + ("." + "0" * tick_decimals if tick_decimals else "")
    axis.tick_labels.number_format = number_format + ('"%"' if block.unit == "%" else "")
    axis.tick_labels.number_format_is_linked = False
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
    label_lane = 52.0
    top = 30.0 if chart.has_legend else 6.0
    _chart_layout(chart, 42 / width, top / chart_h, max(.3, 1 - (42 + label_lane) / width), max(.3, 1 - (top + 34) / chart_h))
    for native, (spec, _) in zip(chart.series, variable):
        native.format.line.color.rgb = _rgb(style.muted if spec.reference else series_color(spec.key, style))
        native.format.line.width = Pt(1.0 if spec.reference else style.line_width)
        if spec.reference:
            native.format.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        native.marker.style = XL_MARKER_STYLE.NONE
        native.smooth = False
    endpoints = [(index, next(v for v in reversed(vals) if v is not None))
                 for index, (spec, vals) in enumerate(variable)
                 if not spec.reference and any(v is not None for v in vals)]
    span = (hi - lo) or 1
    for index, endpoint in endpoints:
        spec, vals = variable[index]
        if cap is not None and endpoint > cap:
            continue
        # Value and short unit only; the legend names the series.
        label = _br(endpoint, spec.decimals) + ("%" if spec.unit == "%" else "")
        last_index = max(i for i, v in enumerate(vals) if v is not None)
        if last_index < len(vals) - 1:
            label += f" ({block.categories[last_index]})"
        native_label = chart.series[index].points[last_index].data_label
        native_label.position = XL_DATA_LABEL_POSITION.RIGHT
        close = [other_index for other_index, other in endpoints
                 if other_index != index and abs(other - endpoint) / span < .08]
        if close:
            # Close final values: the higher one above, the lower one below.
            others = [dict(endpoints)[other] for other in close]
            higher = endpoint > max(others) or (endpoint == max(others) and index < min(close))
            native_label.position = XL_DATA_LABEL_POSITION.ABOVE if higher else XL_DATA_LABEL_POSITION.BELOW
        native_label.has_text_frame = True
        frame = native_label.text_frame
        frame.clear()
        frame.word_wrap = False
        paragraph = frame.paragraphs[0]
        run = paragraph.add_run()
        run.text = label
        run.font.name, run.font.size, run.font.bold = style.font, Pt(style.chart_size), True
        run.font.color.rgb = _rgb(series_color(spec.key, style))
    # Native hierarchical labels remain horizontal, including narrow plots.
    for body in chart._chartSpace.xpath(".//c:catAx/c:txPr/a:bodyPr"):
        body.set("rot", "0")


def _bar_chart(slide, block, variable, x, y, width, height, style):
    data = CategoryChartData()
    data.categories = list(block.categories)
    for spec, vals in variable:
        data.add_series(spec.label, vals)
    chart = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Pt(x), Pt(y), Pt(width), Pt(height), data).chart
    chart.has_title = False
    chart.has_legend = len(variable) > 1
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(10)
        chart.legend.font.name = style.font
    chart.font.name, chart.font.size = style.font, Pt(style.chart_size)
    plot = chart.plots[0]
    plot.gap_width = 60
    plot.overlap = -10
    plot.has_data_labels = True
    labels = plot.data_labels
    labels.number_format = '[$-416]0.0"%"'
    labels.number_format_is_linked = False
    labels.position = XL_DATA_LABEL_POSITION.OUTSIDE_END
    labels.font.size = Pt(10)
    labels.font.name = style.font
    values = [v for _, vals in variable for v in vals if v is not None]
    lo, hi, major_unit, _ = _axis_bounds([min(0, *values), max(0, *values) * 1.18 or 1])
    axis = chart.value_axis
    axis.minimum_scale, axis.maximum_scale, axis.major_unit = lo, hi, major_unit
    axis.visible = False
    axis.has_major_gridlines = False
    category = chart.category_axis
    category.reverse_order = True  # first series on top, as in the table
    category.tick_labels.font.size = Pt(10)
    category.tick_labels.font.name = style.font
    category.format.line.color.rgb = _rgb(style.grid)
    category.major_tick_mark = XL_TICK_MARK.NONE
    colors = {"return_12m": style.orange, "cdi_12m": "8B9199"}
    for native, (spec, _) in zip(chart.series, variable):
        native.format.fill.solid()
        native.format.fill.fore_color.rgb = _rgb(colors.get(spec.key, style.muted))
        for index, category in enumerate(block.categories):
            if str(category).startswith("CDI"):
                point = native.points[index]
                point.format.fill.solid()
                point.format.fill.fore_color.rgb = _rgb("8B9199")


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
    """Pieces of a table that fit one slide each. A continuation of one or
    two rows is avoided by trying the compact font first."""
    chunks = list(_split_table(block, style, width, height))
    if (len(chunks) >= 2 and len(chunks[-1].frame) <= 2 and not getattr(block, "compact", False)
            and list(chunks[-1].frame.columns) == list(block.frame.columns)):
        compact = list(_split_table(replace(block, compact=True), style, width, height))
        if len(compact) < len(chunks):
            return compact
    return chunks


def _split_table(block, style, width=None, height=None):
    width = width or style.content_width
    height = height or style.content_bottom - style.content_top
    columns = list(block.frame.columns)
    # Repeat the identity column when a dense matrix needs another page.
    # One short text column (e.g. a position month) does not make a table textual.
    textual = [column for column in columns[1:] if not (column in block.numeric_columns or block.formats.get(column, "text").split(":")[0] in {"number", "money", "money_value", "percent", "integer"})]
    mostly_numeric = not textual or (len(textual) == 1 and block.frame[textual[0]].map(lambda value: len(str(value))).max() <= 16)
    max_columns = style.month_columns + 1 if len(columns) > 10 or mostly_numeric else 7
    while max_columns > 2 and not _fits_horizontally(replace(block, frame=block.frame.loc[:, columns[:max_columns]]), width, style):
        max_columns -= 1
    if len(columns) <= max_columns:
        groups = [columns]
    else:
        # Even groups (7 + 6, never 12 + 1); the identity column repeats.
        body = columns[1:]
        count = math.ceil(len(body) / (max_columns - 1))
        size = math.ceil(len(body) / count)
        groups = [[columns[0], *body[i:i + size]] for i in range(0, len(body), size)]
    yielded = 0

    def continued(segment):
        # A table that goes on in another place says so; two pieces of the
        # same table never repeat the same subtitle.
        nonlocal yielded
        yielded += 1
        if yielded > 1 and segment.title and not segment.title.endswith("(cont.)"):
            return replace(segment, title=f"{segment.title} (cont.)")
        return segment

    for cols in groups:
        selected = replace(block, frame=block.frame.loc[:, cols])
        start = 0
        while start < len(selected.frame):
            end = start
            for candidate_end in range(start + 1, len(selected.frame) + 1):
                candidate = replace(selected, frame=selected.frame.iloc[start:candidate_end])
                widths, header_h, heights, _ = _table_layout(candidate, width, style)
                if header_h + sum(heights) + (22 if block.title else 0) <= height:
                    end = candidate_end
                else:
                    break
            if end > start:
                yield continued(replace(selected, frame=selected.frame.iloc[start:end]))
                start = end
            else:
                # Split clauses too long for one page using that page's actual
                # column widths. Re-measuring a segment avoids height drift.
                single = replace(selected, frame=selected.frame.iloc[start:start + 1])
                widths, header_h, _, _ = _table_layout(single, width, style)
                available = height - header_h - (22 if block.title else 0)
                row = selected.frame.iloc[start]
                chunks = [textwrap.wrap(format_cell(value, selected.formats.get(col, "text")),
                                       max(12, int((w - 12) / (style.table_size * .49) * max(1, int(available / 15) - 3))),
                                       break_long_words=True, break_on_hyphens=False) or [""]
                          for col, value, w in zip(cols, row, widths)]
                for part in range(max(map(len, chunks))):
                    values = [pieces[part] if part < len(pieces) else "" for pieces in chunks]
                    values[0] = str(row.iloc[0]) if part else values[0]
                    yield continued(replace(selected, frame=pd.DataFrame([values], columns=cols), formats={}))
                start += 1
        if selected.frame.empty:
            yield continued(selected)


#: Decks longer than this get section dividers in ``section_dividers="auto"``.
DIVIDER_MIN_SLIDES = 24
#: ...and only before sections with at least this many slides.
DIVIDER_MIN_SECTION = 3
SECTION_DIVIDER_MODES = ("auto", "always", "never")


def _divider(prs, label, size, style):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(style.white)
    _text(slide, label, style.margin, 228, style.content_width, 40, size=30, bold=True, style=style)
    _text(slide, f"{size} slides", style.margin, 276, style.content_width, 20, size=13, color=style.muted, style=style)
    slide.notes_slide.notes_text_frame.text = f"Divisória de seção: {label}."


def _draw_panels(prs, page, blocks, style, footer=None):
    from services.portfolio_ppt_content import ChartBlock, TableBlock

    slide = _header(prs, page, style)
    width = style.content_width if len(blocks) == 1 else (style.content_width - style.gap) / 2
    height = style.content_bottom - style.content_top
    if footer is not None:
        # A small table of the same theme sits under the panels instead of
        # taking a slide of its own; it never repeats a panel's subtitle.
        if footer.title in {getattr(block, "title", None) for block in blocks}:
            footer = replace(footer, title=f"{footer.title} (tabela)")
        footer_height = _table_height(footer, style) + 12
        height -= footer_height
        notes = slide.notes_slide.notes_text_frame
        notes.text = "\n".join(dict.fromkeys([*notes.text.split("\n"), *map(str, footer.notes)]))
        _table(slide, footer, style.margin, style.content_bottom - footer_height + 12, style.content_width, style=style)
    # Paired plots share the note band, so both start at the same height and
    # have the same plot height.
    band = max([_band_height(_chart_notes(block)[1], width) for block in blocks if isinstance(block, ChartBlock)], default=0)
    for index, block in enumerate(blocks):
        x = style.margin + index * (width + style.gap)
        if isinstance(block, ChartBlock):
            _chart(slide, block, x, style.content_top, width, height, style, band=band)
        elif isinstance(block, TableBlock):
            _table(slide, block, x, style.content_top, width, style=style, compact=True)
        else:
            _kpi(slide, block, x, style.content_top, width, height, style)


#: A lone table up to this share of the content height joins the panels above it.
FOOTER_TABLE_SHARE = .35


def _table_height(block, style):
    _, header_h, rows, _ = _table_layout(block, style.content_width, style)
    return header_h + sum(rows) + (22 if block.title else 0)


def _footer_table(page, following, style):
    """The single small table of the next page, when it can close this
    panels page: same section, one block, one piece, short enough."""
    from services.portfolio_ppt_content import TableBlock

    if (page.layout != "panels" or len(page.blocks) > 2 or following is None or following.layout != "flow" or following.section != page.section
            or len(following.blocks) != 1 or not isinstance(following.blocks[0], TableBlock)):
        return None
    block = following.blocks[0]
    if len(list(_table_chunks(block, style))) != 1:
        return None
    limit = FOOTER_TABLE_SHARE * (style.content_bottom - style.content_top)
    return block if _table_height(block, style) <= limit else None


def _draw_flow(prs, page, blocks, style):
    """Stack the blocks of one theme in reading order; a new slide only when
    the next piece does not fit, and continuations say "(cont.)"."""
    from services.portfolio_ppt_content import ChartBlock, TableBlock

    slide = None
    y = style.content_top
    columns = None  # [left y, right y, current side] while tables share columns
    placed = None  # (slide, title, column) of the last table drawn
    for block in blocks:
        if isinstance(block, ChartBlock):
            _draw_panels(prs, page, (block,), style)
            slide, columns = None, None
            continue
        if isinstance(block, TableBlock):
            half = (style.content_width - style.gap) / 2
            for segment in _table_chunks(block, style):
                widths, header_h, rows, _ = _table_layout(segment, style.content_width, style)
                height = header_h + sum(rows) + (22 if segment.title else 0)
                if sum(widths) <= half:
                    # Narrow tables fill two columns (left, then right)
                    # instead of leaving half of each slide empty.
                    if slide is not None and columns is None:
                        columns = [y, y, 0]
                    if slide is not None and columns[columns[2]] + height > style.content_bottom and columns[2] == 0:
                        columns[2] = 1
                    if slide is None or columns[columns[2]] + height > style.content_bottom:
                        slide = _header(prs, page, style)
                        y = style.content_top
                        columns = [y, y, 0]
                    side = columns[2]
                    base = segment.title.removesuffix(" (cont.)")
                    if base and placed is not None and placed[:2] == (slide, base):
                        # Continued on the same slide: one title is enough;
                        # beside itself, the rows stay aligned with the first piece.
                        segment = replace(segment, title="")
                        if placed[2] == side:
                            height -= 22
                        else:
                            columns[side] += 22
                    placed = (slide, base, side)
                    _table(slide, segment, style.margin + side * (half + style.gap), columns[side], half, style=style)
                    columns[side] += height + 8
                    y = max(columns[0], columns[1])
                    continue
                if columns is not None:
                    y, columns = max(columns[0], columns[1]), None
                if slide is None or y + height > style.content_bottom:
                    slide = _header(prs, page, style)
                    y = style.content_top
                base = segment.title.removesuffix(" (cont.)")
                if base and placed is not None and placed[:2] == (slide, base):
                    # The same table goes on right below: one title is enough.
                    segment = replace(segment, title="")
                    height -= 22
                placed = (slide, base, 0)
                _table(slide, segment, style.margin, y, style.content_width, style=style)
                y += height + 8
            continue
        if columns is not None:
            y, columns = max(columns[0], columns[1]), None
        lines = _lines(block.text, style.content_width, style.table_size)
        for start in range(0, len(lines), 22):
            visible = lines[start:start + 22]
            height = len(visible) * 14 + (22 if block.title else 0)
            if slide is None or y + height > style.content_bottom:
                slide = _header(prs, page, style)
                y = style.content_top
            if block.title:
                title = block.title if start == 0 else f"{block.title} (cont.)"
                _text(slide, title, style.margin, y, style.content_width, 22, size=style.section_size, bold=True, style=style)
                y += 22
            _text(slide, "\n".join(visible), style.margin, y, style.content_width, len(visible) * 14,
                  size=style.table_size, color=style.muted if page.kind == "appendix" else style.text, style=style)
            y += len(visible) * 14 + 12


def _render(spec, style, dividers=None):
    from services.portfolio_ppt_content import TextBlock

    prs = Presentation()
    prs.slide_width, prs.slide_height = Pt(style.width), Pt(style.height)
    prs.core_properties.title = spec.title
    prs.core_properties.author = "Toma Conta"
    _cover(prs, spec, style)
    counts = []
    absorbed = set()
    for index, page in enumerate(spec.slides):
        if index in absorbed:
            counts.append(0)
            continue
        if dividers and index in dividers:
            _divider(prs, *dividers[index], style)
        before = len(prs.slides._sldIdLst)
        footer = _footer_table(page, spec.slides[index + 1] if index + 1 < len(spec.slides) else None, style)
        if footer is not None:
            absorbed.add(index + 1)
        blocks = []
        for block in page.blocks:
            if (blocks and isinstance(block, TextBlock) and isinstance(blocks[-1], TextBlock)
                    and block.title == blocks[-1].title):
                blocks[-1] = replace(blocks[-1], text=f"{blocks[-1].text}\n{block.text}")
            else:
                blocks.append(block)
        if page.layout == "panels" and len(blocks) <= 2:
            _draw_panels(prs, page, blocks, style, footer=footer)
        else:
            _draw_flow(prs, page, blocks, style)
        counts.append(len(prs.slides._sldIdLst) - before)
    return prs, counts


def _section_dividers(spec, counts, mode):
    if mode == "never" or (mode == "auto" and 1 + sum(counts) <= DIVIDER_MIN_SLIDES):
        return {}
    groups = []
    for index, (page, count) in enumerate(zip(spec.slides, counts)):
        label = getattr(page, "section", "")
        if groups and groups[-1][0] == label:
            groups[-1][2] += count
        else:
            groups.append([label, index, count])
    # Short sections do not need a divider.
    return {index: (label, size) for label, index, size in groups if label and size >= DIVIDER_MIN_SECTION}


def render_portfolio_deck(spec, *, style=DEFAULT_STYLE, section_dividers="auto") -> bytes:
    if section_dividers not in SECTION_DIVIDER_MODES:
        raise ValueError(f"section_dividers deve ser um de {SECTION_DIVIDER_MODES}.")
    prs, counts = _render(spec, style)
    dividers = _section_dividers(spec, counts, section_dividers)
    if dividers:
        prs, _ = _render(spec, style, dividers)
    stream = BytesIO()
    prs.save(stream)
    return stream.getvalue()
