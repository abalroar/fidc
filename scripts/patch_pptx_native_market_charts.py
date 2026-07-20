#!/usr/bin/env python3
"""Ajusta data labels sem converter os gráficos de market share em shapes.

O renderer cria gráficos OOXML nativos e data labels editáveis. Este pós-processo
mantém o chart intacto, fixa Arial 10 pt e distribui somente os rótulos de
segmentos curtos em três faixas internas do próprio gráfico.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"
DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

ET.register_namespace("a", DRAWING)
ET.register_namespace("c", CHART)

MARKET_SHARE_SLIDES = {
    12: False,
    13: False,
    14: False,
    28: True,
    29: True,
    30: True,
}
SHORT_SEGMENT = 0.025


def _c(tag: str) -> str:
    return f"{{{CHART}}}{tag}"


def _a(tag: str) -> str:
    return f"{{{DRAWING}}}{tag}"


def _chart_targets(archive: ZipFile) -> dict[str, bool]:
    targets: dict[str, bool] = {}
    for slide_number, appendix in MARKET_SHARE_SLIDES.items():
        rels_name = f"ppt/slides/_rels/slide{slide_number}.xml.rels"
        root = ET.fromstring(archive.read(rels_name))
        chart_paths = []
        for relationship in root.findall(f"{{{PACKAGE_REL}}}Relationship"):
            if str(relationship.get("Type") or "").endswith("/chart"):
                chart_paths.append(str(relationship.get("Target") or "").lstrip("/"))
        if len(chart_paths) != 1:
            raise RuntimeError(
                f"slide {slide_number} deveria conter exatamente um gráfico nativo; "
                f"encontrados {len(chart_paths)}"
            )
        targets[chart_paths[0]] = appendix
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


def patch_pptx(path: Path) -> None:
    path = path.resolve()
    with ZipFile(path) as archive:
        targets = _chart_targets(archive)
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
        try:
            with ZipFile(temporary, "w", ZIP_DEFLATED) as output:
                for info in archive.infolist():
                    data = archive.read(info.filename)
                    if info.filename in targets:
                        data = _patch_chart(data, appendix=targets[info.filename])
                    output.writestr(info, data)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("uso: patch_pptx_native_market_charts.py arquivo.pptx")
    patch_pptx(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
