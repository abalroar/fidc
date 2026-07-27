#!/usr/bin/env python3
"""Ajusta data labels sem converter os gráficos de market share em shapes.

O renderer cria gráficos OOXML nativos e data labels editáveis. Este pós-processo
mantém o chart intacto, fixa Arial 10 pt e distribui somente os rótulos de
segmentos curtos em três faixas internas do próprio gráfico.
"""

from __future__ import annotations

import os
import posixpath
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"
DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

ET.register_namespace("a", DRAWING)
ET.register_namespace("c", CHART)

EXPECTED_MARKET_SHARE_SLIDES = 6
SHORT_SEGMENT = 0.025


def _c(tag: str) -> str:
    return f"{{{CHART}}}{tag}"


def _a(tag: str) -> str:
    return f"{{{DRAWING}}}{tag}"


def _chart_targets(archive: ZipFile) -> dict[str, str]:
    targets: dict[str, str] = {}
    slide_names = sorted(
        (
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide")
            and name.endswith(".xml")
            and "/_rels/" not in name
        ),
        key=lambda name: int(Path(name).stem.replace("slide", "")),
    )
    for slide_name in slide_names:
        slide_number = int(Path(slide_name).stem.replace("slide", ""))
        slide_root = ET.fromstring(archive.read(slide_name))
        slide_text = " ".join(
            node.text or "" for node in slide_root.findall(f".//{_a('t')}")
        )
        normalized_text = slide_text.upper().strip()
        is_market_share = (
            normalized_text.startswith("MARKET SHARE ·")
            or normalized_text.startswith("APÊNDICE · MARKET SHARE")
        )
        is_scale = normalized_text.startswith("ESCALA DA INDÚSTRIA")
        if not (is_market_share or is_scale):
            continue
        appendix = is_market_share and normalized_text.startswith("APÊNDICE")
        rels_name = f"ppt/slides/_rels/slide{slide_number}.xml.rels"
        root = ET.fromstring(archive.read(rels_name))
        chart_paths = []
        for relationship in root.findall(f"{{{PACKAGE_REL}}}Relationship"):
            if str(relationship.get("Type") or "").endswith("/chart"):
                chart_paths.append(str(relationship.get("Target") or "").lstrip("/"))
        if is_market_share and len(chart_paths) != 1:
            raise RuntimeError(
                f"slide {slide_number} deveria conter exatamente um gráfico nativo; "
                f"encontrados {len(chart_paths)}"
            )
        for target in chart_paths:
            resolved = (
                target.lstrip("/")
                if target.startswith("/") or target.startswith("ppt/")
                else posixpath.normpath(posixpath.join("ppt/slides", target))
            )
            targets[resolved] = (
                "scale"
                if is_scale
                else "market_appendix"
                if appendix
                else "market_body"
            )
    market_count = sum(mode.startswith("market_") for mode in targets.values())
    if market_count != EXPECTED_MARKET_SHARE_SLIDES:
        raise RuntimeError(
            "deveriam existir seis slides de market share nativo; "
            f"foram encontrados {market_count}"
        )
    return targets


def _series_values(series: ET.Element) -> dict[int, float]:
    points = series.findall(f".//{_c('val')}/{_c('numLit')}/{_c('pt')}")
    if not points:
        points = series.findall(
            f".//{_c('val')}/{_c('numRef')}/{_c('numCache')}/{_c('pt')}"
        )
    values: dict[int, float] = {}
    for point in points:
        value = point.find(_c("v"))
        if value is None or value.text in {None, ""}:
            continue
        values[int(point.get("idx") or 0)] = float(value.text)
    return values


def _distribute(items: list[dict[str, float]], gap: float) -> None:
    if not items:
        return
    items.sort(key=lambda item: item["desired"])
    low, high = 0.02, 0.98
    centers = [max(low, min(high, item["desired"])) for item in items]
    for index in range(1, len(centers)):
        centers[index] = max(centers[index], centers[index - 1] + gap)
    if centers[-1] > high:
        shift = centers[-1] - high
        centers = [center - shift for center in centers]
    for index in range(len(centers) - 2, -1, -1):
        centers[index] = min(centers[index], centers[index + 1] - gap)
    if centers[0] < low:
        shift = low - centers[0]
        centers = [center + shift for center in centers]
    for item, center in zip(items, centers, strict=True):
        item["assigned"] = center


def _label_for_index(series: ET.Element, category_index: int) -> ET.Element:
    labels = series.find(_c("dLbls"))
    if labels is None:
        raise RuntimeError("série nativa sem dLbls")
    for label in labels.findall(_c("dLbl")):
        index = label.find(_c("idx"))
        if index is not None and int(index.get("val") or -1) == category_index:
            return label
    raise RuntimeError(f"data label ausente para categoria {category_index}")


def _set_arial_10(root: ET.Element) -> None:
    for label_scope in root.findall(f".//{_c('dLbls')}"):
        for default_run in label_scope.findall(f".//{_a('defRPr')}"):
            default_run.set("sz", "1000")
            default_run.set("b", "0")
            for tag in ("latin", "ea", "cs"):
                font = default_run.find(_a(tag))
                if font is None:
                    font = ET.SubElement(default_run, _a(tag))
                font.set("typeface", "Arial")


def _set_chart_language_ptbr(payload: bytes) -> bytes:
    """Bind native chart formatting to Brazilian Portuguese without currency tags."""

    root = ET.fromstring(payload)
    changed = False
    language = root.find(_c("lang"))
    if language is not None and language.get("val") != "pt-BR":
        language.set("val", "pt-BR")
        changed = True
    for node in root.iter():
        if node.tag == _c("numFmt"):
            code = str(node.get("formatCode") or "")
            clean_code = code.removeprefix("[$-416]")
            if clean_code != code:
                node.set("formatCode", clean_code)
                changed = True
        elif node.tag == _c("formatCode"):
            code = str(node.text or "")
            clean_code = code.removeprefix("[$-416]")
            if clean_code != code:
                node.text = clean_code
                changed = True
    if not changed:
        return payload
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def _patch_chart(payload: bytes, *, appendix: bool) -> bytes:
    root = ET.fromstring(payload)
    bar_chart = root.find(f".//{_c('barChart')}")
    if bar_chart is None:
        raise RuntimeError("market share deixou de ser um gráfico de barras nativo")
    grouping = bar_chart.find(_c("grouping"))
    if grouping is None or grouping.get("val") != "percentStacked":
        raise RuntimeError("market share nativo deixou de ser 100% empilhado")

    series = bar_chart.findall(_c("ser"))
    if len(series) != 12:
        raise RuntimeError(f"market share deveria conter 12 séries; contém {len(series)}")
    values = [_series_values(item) for item in series]
    category_count = max((max(item, default=-1) for item in values), default=-1) + 1
    lane_offsets = (-0.018, 0.0, 0.018) if appendix else (-0.05, 0.0, 0.05)
    lane_gap = 0.035

    for category_index in range(category_count):
        cumulative = 0.0
        short_labels: list[dict[str, float]] = []
        for series_index, series_values in enumerate(values):
            value = max(0.0, float(series_values.get(category_index, 0.0)))
            desired = cumulative + value / 2.0
            if 0.0 < value < SHORT_SEGMENT:
                short_labels.append(
                    {
                        "series": float(series_index),
                        "desired": desired,
                    }
                )
            cumulative += value

        lanes: list[list[dict[str, float]]] = [[], [], []]
        for index, item in enumerate(short_labels):
            lanes[index % len(lanes)].append(item)
        for lane in lanes:
            _distribute(lane, lane_gap)

        for lane_index, lane in enumerate(lanes):
            for item in lane:
                label = _label_for_index(
                    series[int(item["series"])], category_index
                )
                position = label.find(_c("dLblPos"))
                if position is not None:
                    position.set("val", "ctr")
                old_layout = label.find(_c("layout"))
                if old_layout is not None:
                    label.remove(old_layout)
                layout = ET.Element(_c("layout"))
                manual = ET.SubElement(layout, _c("manualLayout"))
                ET.SubElement(manual, _c("x"), {"val": f"{lane_offsets[lane_index]:.12g}"})
                ET.SubElement(
                    manual,
                    _c("y"),
                    {"val": f"{item['assigned'] - item['desired']:.12g}"},
                )
                label.insert(1, layout)

    _set_arial_10(root)
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def _text_properties(font_size: int = 850, *, bold: bool = True) -> ET.Element:
    tx_pr = ET.Element(_c("txPr"))
    ET.SubElement(tx_pr, _a("bodyPr"))
    ET.SubElement(tx_pr, _a("lstStyle"))
    paragraph = ET.SubElement(tx_pr, _a("p"))
    paragraph_props = ET.SubElement(paragraph, _a("pPr"))
    default_props = ET.SubElement(
        paragraph_props,
        _a("defRPr"),
        {"sz": str(font_size), "b": "1" if bold else "0"},
    )
    for tag in ("latin", "ea", "cs"):
        ET.SubElement(default_props, _a(tag), {"typeface": "Arial"})
    ET.SubElement(paragraph, _a("endParaRPr"), {"lang": "pt-BR"})
    return tx_pr


def _patch_scale_chart(payload: bytes) -> tuple[bytes, bool]:
    """Add an invisible auxiliary line series with native total labels."""

    root = ET.fromstring(payload)
    plot_area = root.find(f".//{_c('plotArea')}")
    bar_chart = root.find(f".//{_c('barChart')}")
    if plot_area is None or bar_chart is None:
        return payload, False
    series = bar_chart.findall(_c("ser"))
    if len(series) not in {1, 5}:
        return payload, False
    values_by_series = [_series_values(item) for item in series]
    category_count = max(
        (max(values, default=-1) for values in values_by_series), default=-1
    ) + 1
    if category_count <= 0:
        raise RuntimeError("gráfico de escala sem valores em cache")
    totals = [
        sum(values.get(index, 0.0) for values in values_by_series)
        for index in range(category_count)
    ]

    all_indices = [
        int(node.get("val") or 0)
        for node in root.findall(f".//{_c('ser')}/{_c('idx')}")
    ]
    series_index = max(all_indices, default=-1) + 1
    line_chart = ET.Element(_c("lineChart"))
    ET.SubElement(line_chart, _c("grouping"), {"val": "standard"})
    ET.SubElement(line_chart, _c("varyColors"), {"val": "0"})
    aux = ET.SubElement(line_chart, _c("ser"))
    ET.SubElement(aux, _c("idx"), {"val": str(series_index)})
    ET.SubElement(aux, _c("order"), {"val": str(series_index)})
    tx = ET.SubElement(aux, _c("tx"))
    str_lit = ET.SubElement(tx, _c("strLit"))
    ET.SubElement(str_lit, _c("ptCount"), {"val": "1"})
    point = ET.SubElement(str_lit, _c("pt"), {"idx": "0"})
    ET.SubElement(point, _c("v")).text = "Total"
    shape_props = ET.SubElement(aux, _c("spPr"))
    line = ET.SubElement(shape_props, _a("ln"))
    ET.SubElement(line, _a("noFill"))
    marker = ET.SubElement(aux, _c("marker"))
    ET.SubElement(marker, _c("symbol"), {"val": "none"})
    ET.SubElement(marker, _c("size"), {"val": "2"})
    category = series[0].find(_c("cat"))
    if category is None:
        raise RuntimeError("gráfico de escala sem categorias nativas")
    aux.append(deepcopy(category))
    values = ET.SubElement(aux, _c("val"))
    literal = ET.SubElement(values, _c("numLit"))
    ET.SubElement(literal, _c("formatCode")).text = "0"
    ET.SubElement(literal, _c("ptCount"), {"val": str(category_count)})
    for index, value in enumerate(totals):
        point = ET.SubElement(literal, _c("pt"), {"idx": str(index)})
        ET.SubElement(point, _c("v")).text = f"{value:.12g}"
    labels = ET.SubElement(aux, _c("dLbls"))
    ET.SubElement(labels, _c("dLblPos"), {"val": "inEnd"})
    ET.SubElement(
        labels,
        _c("numFmt"),
        {"formatCode": "[>=1000]#\\.##0;0", "sourceLinked": "0"},
    )
    for tag, value in (
        ("showLegendKey", "0"),
        ("showVal", "1"),
        ("showCatName", "0"),
        ("showSerName", "0"),
        ("showPercent", "0"),
        ("showBubbleSize", "0"),
        ("showLeaderLines", "0"),
    ):
        ET.SubElement(labels, _c(tag), {"val": value})
    labels.append(_text_properties())
    ET.SubElement(aux, _c("smooth"), {"val": "0"})
    for axis_id in bar_chart.findall(_c("axId")):
        line_chart.append(deepcopy(axis_id))
    insert_at = list(plot_area).index(bar_chart) + 1
    plot_area.insert(insert_at, line_chart)
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True), True


def patch_pptx(path: Path) -> None:
    path = path.resolve()
    with ZipFile(path) as archive:
        targets = _chart_targets(archive)
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
        try:
            scale_charts_patched = 0
            with ZipFile(temporary, "w", ZIP_DEFLATED) as output:
                for info in archive.infolist():
                    data = archive.read(info.filename)
                    if info.filename in targets:
                        mode = targets[info.filename]
                        if mode == "scale":
                            data, patched = _patch_scale_chart(data)
                            scale_charts_patched += int(patched)
                        else:
                            data = _patch_chart(
                                data,
                                appendix=mode == "market_appendix",
                            )
                    if (
                        info.filename.startswith("ppt/slides/charts/chart")
                        and info.filename.endswith(".xml")
                    ):
                        data = _set_chart_language_ptbr(data)
                    output.writestr(info, data)
            if scale_charts_patched != 2:
                raise RuntimeError(
                    "slide Escala da Indústria deveria ter dois gráficos de barras "
                    f"com série auxiliar; foram ajustados {scale_charts_patched}"
                )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("uso: patch_pptx_native_market_charts.py arquivo.pptx")
    patch_pptx(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
