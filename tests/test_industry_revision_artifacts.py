from __future__ import annotations

import posixpath
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest


ROOT = Path(__file__).resolve().parents[1]
PPTX = ROOT / "outputs" / "Industria_FIDC_Executivo_202607_revisado.pptx"
XLSX = ROOT / "outputs" / "Industria_FIDC_Dados_202607_revisado.xlsx"

PML = "http://schemas.openxmlformats.org/presentationml/2006/main"
DML = "http://schemas.openxmlformats.org/drawingml/2006/main"
CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"
SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _require(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"artefato ainda não gerado: {path}")


def _numeric_suffix(name: str) -> int:
    match = re.search(r"(\d+)\.xml$", name)
    assert match is not None
    return int(match.group(1))


def _slide_texts(archive: ZipFile) -> list[str]:
    names = sorted(
        (
            name
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        ),
        key=_numeric_suffix,
    )
    texts: list[str] = []
    for name in names:
        root = ET.fromstring(archive.read(name))
        texts.append(" ".join(node.text or "" for node in root.iter(f"{{{DML}}}t")))
    return texts


def _slide_chart_paths(archive: ZipFile, slide_number: int) -> list[str]:
    rels_path = f"ppt/slides/_rels/slide{slide_number}.xml.rels"
    rels = ET.fromstring(archive.read(rels_path))
    paths: list[str] = []
    for rel in rels.findall(f"{{{PACKAGE_REL}}}Relationship"):
        if not rel.attrib.get("Type", "").endswith("/chart"):
            continue
        target = rel.attrib["Target"]
        paths.append(
            target.lstrip("/")
            if target.startswith("/")
            else posixpath.normpath(posixpath.join("ppt/slides", target))
        )
    return paths


def _chart_series_values(root: ET.Element) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for series in root.findall(f".//{{{CHART}}}ser"):
        name = "".join(
            node.text or ""
            for node in series.findall(f".//{{{CHART}}}tx//{{{CHART}}}v")
        )
        values = [
            float(node.text)
            for node in series.findall(
                f".//{{{CHART}}}val//{{{CHART}}}pt/{{{CHART}}}v"
            )
            if node.text is not None
        ]
        result[name] = values
    return result


def _series_values_by_index(series: ET.Element) -> dict[int, float]:
    points = series.findall(
        f".//{{{CHART}}}val/{{{CHART}}}numLit/{{{CHART}}}pt"
    )
    if not points:
        points = series.findall(
            f".//{{{CHART}}}val/{{{CHART}}}numRef/"
            f"{{{CHART}}}numCache/{{{CHART}}}pt"
        )
    result: dict[int, float] = {}
    for point in points:
        value = point.find(f"{{{CHART}}}v")
        if value is None or value.text in {None, ""}:
            continue
        result[int(point.attrib.get("idx", "0"))] = float(value.text)
    return result


def _series_name(series: ET.Element) -> str:
    return "".join(
        node.text or ""
        for node in series.findall(f".//{{{CHART}}}tx//{{{CHART}}}v")
    )


def _shape_texts(slide: ET.Element) -> list[str]:
    return [
        "".join(node.text or "" for node in shape.iter(f"{{{DML}}}t")).strip()
        for shape in slide.findall(f".//{{{PML}}}sp")
    ]


def _shape_fill_colors(slide: ET.Element) -> list[str]:
    colors: list[str] = []
    for shape in slide.findall(f".//{{{PML}}}sp"):
        color = shape.find(
            f"{{{PML}}}spPr/{{{DML}}}solidFill/{{{DML}}}srgbClr"
        )
        if color is not None and color.attrib.get("val"):
            colors.append(color.attrib["val"].upper())
    return colors


def _shared_strings(archive: ZipFile) -> list[str]:
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(f"{{{SHEET}}}t"))
        for item in root.findall(f"{{{SHEET}}}si")
    ]


def _workbook_sheets(archive: ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target_by_id = {
        rel.attrib["Id"]: rel.attrib["Target"].lstrip("/")
        for rel in rels.findall(f"{{{PACKAGE_REL}}}Relationship")
        if rel.attrib.get("Type", "").endswith("/worksheet")
    }
    return {
        sheet.attrib["name"]: target_by_id[sheet.attrib[f"{{{OFFICE_REL}}}id"]]
        for sheet in workbook.findall(f".//{{{SHEET}}}sheet")
    }


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.attrib.get("t")
    value = cell.find(f"{{{SHEET}}}v")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{SHEET}}}t"))
    if value is None or value.text is None:
        return ""
    if kind == "s":
        return shared[int(value.text)]
    return value.text


def _column_values(
    archive: ZipFile,
    sheet_path: str,
    column: str,
    first_row: int,
    last_row: int,
    shared: list[str],
) -> list[str]:
    root = ET.fromstring(archive.read(sheet_path))
    by_ref = {
        cell.attrib["r"]: _cell_value(cell, shared)
        for cell in root.findall(f".//{{{SHEET}}}c")
        if "r" in cell.attrib
    }
    return [by_ref.get(f"{column}{row}", "") for row in range(first_row, last_row + 1)]


def test_deck_order_and_profile_count() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slides = _slide_texts(archive)

    assert len(slides) == 44
    expected_body = [
        "SÍNTESE EXECUTIVA",
        "ESCALA DA INDÚSTRIA",
        "BASE INVESTIDORA",
        "DISTRIBUIÇÃO POR NÚMERO DE COTISTAS",
        "TIPO ANBIMA",
        "CARTEIRA POR TIPO DE RECEBÍVEL",
        "OBSERVABILIDADE DA INADIMPLÊNCIA",
        "INADIMPLÊNCIA · EVOLUÇÃO E QUEBRA",
        "PRESTADORES · RANKING E CONCENTRAÇÃO",
        "MARKET SHARE · ADMINISTRAÇÃO",
        "MARKET SHARE · GESTÃO",
        "MARKET SHARE · CUSTÓDIA",
        "PRESTADORES · EVOLUÇÃO DO RANKING",
        "RANKING · TOP 20 FIDCS",
        "RANKING · TOP 20 OUTROS",
        "MODELO DE PRESTAÇÃO",
        "CONCENTRAÇÃO DAS MONOESTRUTURAS",
        "OFERTAS, CAPTAÇÃO E ORIGINAÇÃO",
    ]
    assert "INDÚSTRIA DE FIDCs" in slides[0]
    for slide_text, expected in zip(slides[1:19], expected_body, strict=True):
        assert expected in slide_text
    assert "Escopo, fontes e limitações" in slides[19]
    assert "Administração por subtipo" in slides[20]
    assert "Gestão por subtipo" in slides[21]
    assert "Custódia por subtipo" in slides[22]
    profiles = slides[23:43]
    assert len(profiles) == 20
    assert sum("APÊNDICE · CURADORIA TOP 20" in text for text in slides) == 20
    for rank, slide_text in enumerate(profiles, start=1):
        assert "APÊNDICE · CURADORIA TOP 20" in slide_text
        assert f"#{rank} " in slide_text
    assert "APÊNDICE · CASO ATLÂNTICO" in slides[43]
    assert "09.194.841/0001-51" in slides[43]
    assert all(len(slide_text.strip()) > 80 for slide_text in slides)


def test_ppt_charts_have_no_active_markers_or_smoothing() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_names = [
            name
            for name in archive.namelist()
            if "/charts/chart" in name and name.endswith(".xml")
        ]
        assert chart_names
        for name in chart_names:
            root = ET.fromstring(archive.read(name))
            for smooth in root.iter(f"{{{CHART}}}smooth"):
                assert smooth.attrib.get("val", "0").lower() not in {"1", "true"}
            for marker in root.iter(f"{{{CHART}}}marker"):
                symbol = marker.find(f"{{{CHART}}}symbol")
                assert symbol is not None
                assert symbol.attrib.get("val") == "none"


@pytest.mark.parametrize("slide_number", [11, 12, 13, 21, 22, 23])
def test_market_share_slides_use_one_native_percent_stacked_chart(
    slide_number: int,
) -> None:
    _require(PPTX)
    short_threshold = 0.025
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, slide_number)
        assert len(chart_paths) == 1
        chart = ET.fromstring(archive.read(chart_paths[0]))
        slide = ET.fromstring(archive.read(f"ppt/slides/slide{slide_number}.xml"))

    bar_charts = chart.findall(f".//{{{CHART}}}barChart")
    assert len(bar_charts) == 1
    bar_chart = bar_charts[0]
    grouping = bar_chart.find(f"{{{CHART}}}grouping")
    assert grouping is not None
    assert grouping.attrib.get("val") == "percentStacked"

    series = bar_chart.findall(f"{{{CHART}}}ser")
    assert len(series) == 12
    expected_manual: set[tuple[int, int]] = set()
    actual_manual: set[tuple[int, int]] = set()
    for series_index, item in enumerate(series):
        values = _series_values_by_index(item)
        expected_manual.update(
            (series_index, point_index)
            for point_index, value in values.items()
            if 0.0 < value < short_threshold
        )

        labels = item.find(f"{{{CHART}}}dLbls")
        assert labels is not None
        labels_by_index = {
            int(index.attrib["val"]): label
            for label in labels.findall(f"{{{CHART}}}dLbl")
            if (index := label.find(f"{{{CHART}}}idx")) is not None
        }
        for point_index, value in values.items():
            if value <= 0:
                continue
            assert point_index in labels_by_index
            label = labels_by_index[point_index]
            show_value = label.find(f"{{{CHART}}}showVal")
            assert show_value is not None
            assert show_value.attrib.get("val", "1").lower() in {"1", "true"}
            default_runs = label.findall(f".//{{{DML}}}defRPr")
            assert default_runs
            for default_run in default_runs:
                assert default_run.attrib.get("sz") == "1000"
                for font_tag in ("latin", "ea", "cs"):
                    font = default_run.find(f"{{{DML}}}{font_tag}")
                    assert font is not None
                    assert font.attrib.get("typeface") == "Arial"

        for label in labels.findall(f"{{{CHART}}}dLbl"):
            index = label.find(f"{{{CHART}}}idx")
            manual = label.find(
                f"{{{CHART}}}layout/{{{CHART}}}manualLayout"
            )
            if index is not None and manual is not None:
                actual_manual.add((series_index, int(index.attrib["val"])))

    assert expected_manual
    assert actual_manual == expected_manual

    legends = chart.findall(f".//{{{CHART}}}legend")
    assert len(legends) == 1
    deleted = legends[0].find(f"{{{CHART}}}delete")
    assert deleted is None or deleted.attrib.get("val", "0").lower() not in {
        "1",
        "true",
    }

    # Series names and point values must live in the native chart part, not in
    # PowerPoint text boxes that imitate a legend or data labels.
    series_names = {_series_name(item) for item in series}
    slide_shape_texts = _shape_texts(slide)
    assert not series_names.intersection(slide_shape_texts)
    assert not any(
        re.fullmatch(r"<?\d+(?:[,.]\d+)?%", text)
        for text in slide_shape_texts
    )
    # The only filled slide shapes are the two neutral header rules. Provider
    # colors must occur inside the chart part, never as simulated bar shapes.
    assert _shape_fill_colors(slide) == ["D7DADD", "D7DADD"]


def test_provider_historical_slide_has_three_table_chart_pairs_and_method_note() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slide = ET.fromstring(archive.read("ppt/slides/slide14.xml"))
        text = " ".join(node.text or "" for node in slide.iter(f"{{{DML}}}t"))
        chart_paths = _slide_chart_paths(archive, 14)

    assert len(chart_paths) == 3
    assert text.count("Participante") == 3
    for expected in (
        "ADMINISTRAÇÃO",
        "GESTÃO",
        "CUSTÓDIA",
        "Dez/24",
        "Dez/25",
        "Mai/26",
        "Sistema Petrobras e TAPSO excluídos",
    ):
        assert expected in text


def test_holder_distribution_slide_has_four_charts_and_normalized_histograms() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slide = ET.fromstring(archive.read("ppt/slides/slide5.xml"))
        chart_frames = slide.findall(f".//{{{PML}}}graphicFrame")
        assert len(chart_frames) == 4

        x_positions: list[int] = []
        y_positions: list[int] = []
        for frame in chart_frames:
            offset = frame.find(f"{{{PML}}}xfrm/{{{DML}}}off")
            assert offset is not None
            x_positions.append(int(offset.attrib["x"]))
            y_positions.append(int(offset.attrib["y"]))
        assert sorted(x_positions).count(min(x_positions)) == 2
        assert sorted(x_positions).count(max(x_positions)) == 2
        assert len(set(x_positions)) == 2
        assert sorted(y_positions).count(min(y_positions)) == 2
        assert sorted(y_positions).count(max(y_positions)) == 2
        assert len(set(y_positions)) == 2

        chart_series = [
            _chart_series_values(ET.fromstring(archive.read(chart_path)))
            for chart_path in _slide_chart_paths(archive, 5)
        ]

    assert len(chart_series) == 4
    for series in chart_series:
        assert set(series) == {"Dez/23", "Mai/26"}
        assert all(len(values) == 6 for values in series.values())
    normalized = [
        series
        for series in chart_series
        if all(sum(values) == pytest.approx(1.0, abs=1e-9) for values in series.values())
    ]
    assert len(normalized) == 2


@pytest.mark.parametrize(
    ("slide_number", "periods"),
    [
        (6, {"Dez/23", "Mai/26"}),
        (7, {"Dez/23", "Mai/26"}),
        (10, {"Dez/25", "Mai/26"}),
    ],
)
def test_before_after_slides_have_two_clustered_charts(
    slide_number: int, periods: set[str]
) -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, slide_number)
        chart_series = [
            _chart_series_values(ET.fromstring(archive.read(chart_path)))
            for chart_path in chart_paths
        ]

    assert len(chart_series) == 2
    assert all(set(series) == periods for series in chart_series)
    if slide_number in {6, 7}:
        normalized = [
            series
            for series in chart_series
            if all(
                sum(values) == pytest.approx(1.0, abs=1e-9)
                for values in series.values()
            )
        ]
        assert len(normalized) == 1


def test_deck_palette_and_explicit_slide_font() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slide_xml = b"".join(
            archive.read(name)
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        )
        office_xml = b"".join(
            archive.read(name)
            for name in archive.namelist()
            if name.endswith(".xml")
            and (
                name.startswith("ppt/slides/")
                or name.startswith("ppt/theme/")
                or "/charts/chart" in name
            )
        )
        assert b"EC7000" in office_xml.upper()
        assert b"172A3A" not in office_xml.upper()
        assert b'COLOR="172A3A"' not in office_xml.upper()
        assert b'typeface="Calibri"' not in slide_xml
        assert b'typeface="Arial"' in slide_xml


def test_workbook_has_required_tabs_and_exact_top20_counts() -> None:
    _require(XLSX)
    required = {
        "QA Inadimplência",
        "Base competência-CNPJ",
        "Base por fundo-CNPJ",
        "Concentração de monoestruturas",
        "Market share por subtipo",
        "Top 20 FIDCs",
        "Top 20 Outros",
        "Curadoria Top 20",
        "Comparativos históricos",
        "Curadoria Atlântico",
        "Série Atlântico",
        "Ranking prestadores",
        "Taxonomia adquirência",
        "Checks revisão",
    }
    with ZipFile(XLSX) as archive:
        sheets = _workbook_sheets(archive)
        shared = _shared_strings(archive)
        assert required.issubset(sheets)
        for sheet_name in ("Top 20 FIDCs", "Top 20 Outros", "Curadoria Top 20"):
            ranks = _column_values(
                archive,
                sheets[sheet_name],
                "A",
                5,
                24,
                shared,
            )
            assert [int(float(value)) for value in ranks] == list(range(1, 21))
            assert _column_values(
                archive,
                sheets[sheet_name],
                "A",
                25,
                25,
                shared,
            ) == [""]


def test_legacy_industry_export_no_longer_requests_line_markers() -> None:
    source = (ROOT / "services" / "industry_ppt_export.py").read_text(
        encoding="utf-8"
    )
    assert "LINE_MARKERS" not in source
    assert 'NAVY = "172A3A"' not in source
    assert 'font.name = "Calibri"' not in source


def test_revision_renderer_version_tracks_holder_distribution_layout() -> None:
    source = (ROOT / "scripts" / "build_fidc_revision_artifacts.mjs").read_text(
        encoding="utf-8"
    )
    assert 'const RENDERER_VERSION = "industry_revision_artifacts_v5";' in source
