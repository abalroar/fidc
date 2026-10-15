"""Native Office charts of the portfolio deck: lines, columns and stacked columns.

Every chart carries its title and legend inside the chart object, shows the
value of every point as a data label (Calibri) and highlights the latest
period: bold, larger, on a fill of the series colour. The value axis is
hidden when the labels already carry the values. No shapes are drawn.
"""

from __future__ import annotations

import math

from lxml import etree
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_MARKER_STYLE, XL_TICK_LABEL_POSITION, XL_TICK_MARK
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.oxml.ns import qn
from pptx.util import Pt

INK = "1F1F1F"
ORANGE = "EC7000"
GREY_DARK = "626970"
GREY = "8B9199"
GREY_LIGHT = "C4C8CD"
WHITE = "FFFFFF"

#: Labels above this many series are reduced to the latest period.
FULL_LABEL_SERIES = 2
#: A stacked segment smaller than this share of the tallest column has no label.
SEGMENT_LABEL_SHARE = .08
LABEL_SIZE = 8.0
LAST_LABEL_SIZE = 9.5
TITLE_ROW = 20.0

_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _el(tag, **attributes):
    prefix, name = tag.split(":")
    element = etree.Element(f"{{{_C if prefix == 'c' else _A}}}{name}")
    for key, value in attributes.items():
        element.set(key, str(value))
    return element


def _sub(parent, tag, **attributes):
    element = _el(tag, **attributes)
    parent.append(element)
    return element


def _rgb(value):
    return RGBColor.from_string(value)


def _light(color):
    return color in {GREY_LIGHT, GREY}


def number_format(unit, decimals):
    places = "." + "0" * decimals if decimals else ""
    return f'[$-416]#,##0{places}' + ('"%"' if unit == "%" else "")


def _text_properties(parent, *, size, bold, color, font, rotate=False):
    tx = _sub(parent, "c:txPr")
    body = _sub(tx, "a:bodyPr")
    if rotate:
        body.set("rot", "-5400000")
        body.set("vert", "horz")
    _sub(tx, "a:lstStyle")
    paragraph = _sub(tx, "a:p")
    properties = _sub(_sub(paragraph, "a:pPr"), "a:defRPr", sz=int(size * 100), b=int(bold))
    _sub(_sub(properties, "a:solidFill"), "a:srgbClr", val=color)
    _sub(properties, "a:latin", typeface=font)
    _sub(paragraph, "a:endParaRPr", lang="pt-BR")


def _shape(parent, fill):
    sp = _sub(parent, "c:spPr")
    if fill:
        _sub(_sub(sp, "a:solidFill"), "a:srgbClr", val=fill)
    else:
        _sub(sp, "a:noFill")
    _sub(_sub(sp, "a:ln"), "a:noFill")


def _flags(parent):
    for name, value in (("showLegendKey", 0), ("showVal", 1), ("showCatName", 0), ("showSerName", 0),
                        ("showPercent", 0), ("showBubbleSize", 0)):
        _sub(parent, f"c:{name}", val=value)


def label_series(ser, count, *, fmt, position, color, font, highlight=None, hidden=(), last=None,
                 rotate=False, size=LABEL_SIZE, only_last=False):
    """Write the ``c:dLbls`` of one series. ``highlight`` is the fill of the
    latest label (None keeps it plain but bold); ``hidden`` points carry no
    label; ``only_last`` labels the latest point alone."""
    for existing in ser.findall(qn("c:dLbls")):
        ser.remove(existing)
    labels = _el("c:dLbls")
    last = count - 1 if last is None else last
    for index in range(count):
        if index == last and last not in hidden:
            label = _sub(labels, "c:dLbl")
            _sub(label, "c:idx", val=index)
            _sub(label, "c:numFmt", formatCode=fmt, sourceLinked=0)
            _shape(label, highlight)
            _text_properties(label, size=LAST_LABEL_SIZE, bold=True, color=WHITE if highlight else color, font=font)
            _sub(label, "c:dLblPos", val=position)
            _flags(label)
        elif index in hidden or only_last:
            label = _sub(labels, "c:dLbl")
            _sub(label, "c:idx", val=index)
            _sub(label, "c:delete", val=1)
    _sub(labels, "c:numFmt", formatCode=fmt, sourceLinked=0)
    _shape(labels, None)
    _text_properties(labels, size=size, bold=False, color=color, font=font, rotate=rotate)
    _sub(labels, "c:dLblPos", val=position)
    _flags(labels)
    # Schema order: dLbls sits right before the categories.
    ser.find(qn("c:cat")).addprevious(labels)


def _manual_layout(target, x, y, w=None, h=None, *, inner=False):
    layout = target.find(qn("c:layout"))
    if layout is None:
        layout = _el("c:layout")
        # Schema position: first in plotArea; after c:tx in a title; after
        # c:legendPos and any c:legendEntry in a legend.
        anchors = [child for child in target if child.tag in {qn("c:tx"), qn("c:legendPos"), qn("c:legendEntry")}]
        if anchors:
            anchors[-1].addnext(layout)
        else:
            target.insert(0, layout)
    for child in list(layout):
        layout.remove(child)
    manual = _sub(layout, "c:manualLayout")
    if inner:
        _sub(manual, "c:layoutTarget", val="inner")
    items = [("xMode", "edge"), ("yMode", "edge")]
    if w is not None:
        items += [("wMode", "factor"), ("hMode", "factor")]
    items += [("x", round(x, 4)), ("y", round(y, 4))]
    if w is not None:
        items += [("w", round(w, 4)), ("h", round(h, 4))]
    for name, value in items:
        _sub(manual, f"c:{name}", val=value)


def title_and_legend(chart, title, *, width, height, legend, font, size=11.0):
    """Title at the top left and, when there are several series, the legend
    on the same row at the right: one band, no text box."""
    chart.has_title = True
    frame = chart.chart_title.text_frame
    frame.text = title
    for paragraph in frame.paragraphs:
        for run in paragraph.runs:
            run.font.name, run.font.size, run.font.bold = font, Pt(size), True
            run.font.color.rgb = _rgb(INK)
    title_element = chart._chartSpace.find(qn("c:chart")).find(qn("c:title"))
    overlay = title_element.find(qn("c:overlay"))
    if overlay is None:
        overlay = _sub(title_element, "c:overlay")
    overlay.set("val", "0")
    _manual_layout(title_element, 0.0, 0.0)
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(9)
        chart.legend.font.name = font
        chart.legend.font.color.rgb = _rgb(GREY_DARK)
        legend_element = chart._chartSpace.find(qn("c:chart")).find(qn("c:legend"))
        # Right half of the title row.
        _manual_layout(legend_element, .42, 0.0, .58, min(.12, (TITLE_ROW + 2) / height))


def category_axis(chart, categories, *, font, size=9, width=440.0):
    axis = chart.category_axis
    axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
    axis.tick_labels.font.name = font
    axis.tick_labels.font.size = Pt(size)
    axis.tick_labels.font.color.rgb = _rgb(GREY_DARK)
    axis.format.line.color.rgb = _rgb(GREY_LIGHT)
    axis.major_tick_mark = axis.minor_tick_mark = XL_TICK_MARK.NONE
    axis.tick_label_spacing = max(1, math.ceil(len(categories) / (18 if width > 600 else 13 if width > 320 else 5)))
    for body in chart._chartSpace.xpath(".//c:catAx/c:txPr/a:bodyPr"):
        body.set("rot", "0")


def hide_value_axis(chart, lo, hi):
    axis = chart.value_axis
    axis.minimum_scale, axis.maximum_scale = lo, hi
    axis.visible = False
    axis.has_major_gridlines = False
    axis.major_tick_mark = axis.minor_tick_mark = XL_TICK_MARK.NONE


def hierarchical_categories(data, categories):
    """Month on the first row, the year once on the second."""
    parsed = [str(label).split("/") for label in categories]
    if parsed and all(len(parts) == 2 for parts in parsed):
        previous, year_category = None, None
        for month, year in parsed:
            year = "20" + year if len(year) == 2 else year
            if year != previous:
                year_category = data.categories.add_category(year)
                previous = year
            year_category.add_sub_category(month)
    else:
        data.categories = list(categories)


def plot_layout(chart, *, width, height, top, left=6.0, right=6.0, bottom=38.0):
    area = chart._chartSpace.xpath(".//c:plotArea")[0]
    _manual_layout(area, left / width, top / height, max(.3, 1 - (left + right) / width),
                   max(.25, 1 - (top + bottom) / height), inner=True)


def _gaps(chart):
    main = chart._chartSpace.xpath("./c:chart")[0]
    elements = main.xpath("./c:dispBlanksAs")
    gaps = elements[0] if elements else _el("c:dispBlanksAs")
    gaps.set("val", "gap")
    if not elements:
        main.append(gaps)


def label_color(color):
    return GREY_DARK if _light(color) else color


def _last_index(values):
    return max((index for index, value in enumerate(values) if value is not None), default=None)


def line_chart(slide, block, variable, x, y, width, height, *, colors, font, top, bounds, cap=None, compact=False):
    """Lines with every point labelled (one or two series: the first above
    its points, the second below); with more series, the latest only."""
    drawn = [spec for spec, _ in variable if not spec.reference]
    full = len(drawn) <= FULL_LABEL_SERIES and not compact
    data = CategoryChartData()
    hierarchical_categories(data, block.categories)
    for spec, values in variable:
        last = _last_index(values)
        name = spec.label
        if not full and not compact and not spec.reference and last is not None:
            # Several lines: each legend entry carries its latest value, so
            # end labels never sit on top of one another.
            name = f"{spec.label}: {format_value(values[last], spec, places(spec, values))}"
        data.add_series(name, values)
    chart = slide.shapes.add_chart(XL_CHART_TYPE.LINE, Pt(x), Pt(y), Pt(width), Pt(height), data).chart
    title_and_legend(chart, block.title, width=width, height=height, legend=len(variable) > 1, font=font,
                     size=10 if compact else 11)
    chart.font.name, chart.font.size = font, Pt(9)
    lo, hi, step, decimals = bounds
    if full:
        # Room above (and, with a second series labelled below, under) the lines.
        span = (hi - lo) or 1
        hide_value_axis(chart, lo - span * .15 if len(drawn) == 2 or lo < 0 else lo, hi + span * .15)
    else:
        axis = chart.value_axis
        axis.minimum_scale, axis.maximum_scale, axis.major_unit = lo, hi, step
        axis.tick_labels.font.name, axis.tick_labels.font.size = font, Pt(8)
        axis.tick_labels.font.color.rgb = _rgb(GREY_DARK)
        axis.tick_labels.number_format = number_format(block.unit if block.unit == "%" else "", decimals)
        axis.tick_labels.number_format_is_linked = False
        axis.has_major_gridlines = True
        axis.major_gridlines.format.line.color.rgb = _rgb("E8EAED")
        axis.format.line.fill.background()
        axis.major_tick_mark = axis.minor_tick_mark = XL_TICK_MARK.NONE
    category_axis(chart, block.categories, font=font, size=8 if compact else 9, width=width)
    _gaps(chart)
    plot_layout(chart, width=width, height=height, top=top, left=6.0 if full else 34.0, right=30.0)
    order = 0
    for native, (spec, values) in zip(chart.series, variable):
        color = GREY_DARK if spec.reference else colors(spec)
        native.format.line.color.rgb = _rgb(color)
        native.format.line.width = Pt(1.0 if spec.reference else 1.75)
        if spec.reference:
            native.format.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        native.marker.style = XL_MARKER_STYLE.CIRCLE if not spec.reference and not compact else XL_MARKER_STYLE.NONE
        if native.marker.style == XL_MARKER_STYLE.CIRCLE:
            native.marker.size = 4
            native.marker.format.fill.solid()
            native.marker.format.fill.fore_color.rgb = _rgb(color)
            native.marker.format.line.fill.background()
        native.smooth = False
        if spec.reference:
            continue
        last = _last_index(values)
        if last is None:
            continue
        hidden = {index for index, value in enumerate(values) if value is not None and cap is not None and value > cap}
        if full or compact:
            label_series(native._element, len(values), fmt=number_format(spec.unit if spec.unit == "%" else "", places(spec, values)),
                         position="b" if full and order == 1 else "t", color=label_color(color), font=font,
                         highlight=color, hidden=hidden, last=last, only_last=not full)
        order += 1
    return chart


def column_chart(slide, block, variable, x, y, width, height, *, colors, font, top, cap=None):
    """Columns. One series: history in grey, the latest month in orange.
    Several: side by side. ``stacked``: parts with their total on top."""
    stacked = block.kind == "stacked"
    data = CategoryChartData()
    hierarchical_categories(data, block.categories)
    for spec, values in variable:
        data.add_series(spec.label, values)
    totals = [sum(v for v in column if v is not None) if any(v is not None for v in column) else None
              for column in zip(*(values for _, values in variable))]
    shares = all(t is None or abs(t - 100) < .5 for t in totals)
    show_total = stacked and len(variable) > 1 and not shares
    if show_total:
        data.add_series("Total", totals)
    kind = XL_CHART_TYPE.COLUMN_STACKED if stacked else XL_CHART_TYPE.COLUMN_CLUSTERED
    chart = slide.shapes.add_chart(kind, Pt(x), Pt(y), Pt(width), Pt(height), data).chart
    title_and_legend(chart, block.title, width=width, height=height, legend=len(variable) > 1, font=font)
    chart.font.name, chart.font.size = font, Pt(9)
    plot = chart.plots[0]
    plot.gap_width = 45 if stacked or len(variable) == 1 else 35
    plot.overlap = 100 if stacked else 0
    values_all = [v for _, values in variable for v in values if v is not None]
    peak = max([*(t for t in totals if t is not None), *values_all, 0.0]) if stacked else max([*values_all, 0.0])
    if cap is not None:
        peak = min(peak, cap)
    low = min(0.0, *values_all) if values_all else 0.0
    hide_value_axis(chart, low * 1.15 if low < 0 else 0.0, (peak or 1) * (1.22 if not stacked or show_total else 1.08))
    category_axis(chart, block.categories, font=font, width=width)
    _gaps(chart)
    plot_layout(chart, width=width, height=height, top=top, right=8.0)
    bar_width = (width - 14) / max(1, len(block.categories)) * (1 if stacked else 1 / (len(variable) + .3)) * .7
    for index, (native, (spec, values)) in enumerate(zip(chart.series, variable)):
        color = colors(spec)
        native.format.fill.solid()
        native.format.fill.fore_color.rgb = _rgb(color)
        native.invert_if_negative = False
        last = _last_index(values)
        if last is None:
            continue
        fmt = number_format(spec.unit if spec.unit == "%" else "", places(spec, values))
        widest = max(len(format_value(v, spec, places(spec, values))) for v in values if v is not None)
        # Labels stay horizontal; a crowded chart uses smaller type instead.
        size = LABEL_SIZE if stacked or widest * LABEL_SIZE * .5 <= bar_width + 6 else 7.0
        if stacked:
            # No label for slivers, nor for a part that is the whole column
            # (the total above already says it).
            hidden = {i for i, v in enumerate(values) if v is None or (peak and abs(v) < SEGMENT_LABEL_SHARE * peak)
                      or (show_total and totals[i] and abs(v - totals[i]) < 1e-9 * max(1.0, abs(totals[i])))}
            text = INK if _light(color) else WHITE
            label_series(native._element, len(values), fmt=fmt, position="ctr", color=text, font=font,
                         highlight=None, hidden=hidden, last=last)
        elif len(variable) == 1:
            # History in grey, the latest month in the accent colour.
            native.format.fill.fore_color.rgb = _rgb(GREY)
            point = native.points[last]
            point.format.fill.solid()
            point.format.fill.fore_color.rgb = _rgb(ORANGE)
            # A column cut by the capped axis has its value in the note under
            # the title; its label would land on the title.
            hidden = {i for i, v in enumerate(values) if cap is not None and v is not None and v > cap}
            label_series(native._element, len(values), fmt=fmt, position="outEnd", color=GREY_DARK, font=font,
                         highlight=ORANGE, hidden=hidden, last=last, size=size)
        else:
            label_series(native._element, len(values), fmt=fmt, position="outEnd", color=label_color(color), font=font,
                         highlight=color, last=last, size=size)
    if show_total:
        unit = variable[0][0].unit
        _total_as_line(chart, totals, fmt=number_format(unit if unit == "%" else "", places(variable[0][0], totals)), font=font)
    return chart


def places(spec, values):
    """Decimals a label needs: none for volumes of a hundred or more (R$ mm)
    or for any value of four integer digits."""
    peak = max((abs(v) for v in values if v is not None), default=0.0)
    if peak >= 1000 or (spec.unit != "%" and peak >= 100):
        return 0
    if 0 < peak < 1:
        # Small values keep two significant digits (0,018%, not 0,02%).
        return max(spec.decimals, 1 - math.floor(math.log10(peak)))
    return spec.decimals


def format_value(value, spec, decimals):
    text = f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return text + ("%" if spec.unit == "%" else "")


def _total_as_line(chart, totals, *, fmt, font):
    """The last series ("Total") leaves the stack for an invisible line on
    the same axes: its labels sit on top of each column."""
    plot_area = chart._chartSpace.xpath(".//c:plotArea")[0]
    bar = plot_area.find(qn("c:barChart"))
    total = bar.findall(qn("c:ser"))[-1]
    bar.remove(total)
    line = _el("c:lineChart")
    _sub(line, "c:grouping", val="standard")
    _sub(line, "c:varyColors", val=0)
    line.append(total)
    for child in list(total):
        if child.tag in {qn("c:invertIfNegative"), qn("c:spPr")}:
            total.remove(child)
    sp = _el("c:spPr")
    _sub(_sub(sp, "a:ln"), "a:noFill")
    total.find(qn("c:tx")).addnext(sp)
    marker = _el("c:marker")
    _sub(marker, "c:symbol", val="none")
    sp.addnext(marker)
    _sub(line, "c:marker", val=1)
    for axis in bar.findall(qn("c:axId")):
        _sub(line, "c:axId", val=axis.get("val"))
    bar.addnext(line)
    last = _last_index(totals)
    if last is not None:
        label_series(total, len(totals), fmt=fmt, position="t", color=INK, font=font, highlight=INK, last=last)
    # The legend names the parts, not the helper series.
    legend = chart._chartSpace.find(qn("c:chart")).find(qn("c:legend"))
    if legend is not None:
        entry = _el("c:legendEntry")
        _sub(entry, "c:idx", val=total.find(qn("c:idx")).get("val"))
        _sub(entry, "c:delete", val=1)
        anchors = [child for child in legend if child.tag in {qn("c:legendPos"), qn("c:legendEntry")}]
        anchors[-1].addnext(entry)
