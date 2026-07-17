from __future__ import annotations

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

    assert len(slides) == 42
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
        "RANKING · TOP 20 FIDCS",
        "RANKING · TOP 20 OUTROS",
        "MODELO DE PRESTAÇÃO",
        "CONCENTRAÇÃO DAS MONOESTRUTURAS",
        "OFERTAS, CAPTAÇÃO E ORIGINAÇÃO",
    ]
    assert "INDÚSTRIA DE FIDCs" in slides[0]
    for slide_text, expected in zip(slides[1:18], expected_body, strict=True):
        assert expected in slide_text
    assert "Escopo, fontes e limitações" in slides[18]
    assert "Administração por subtipo" in slides[19]
    assert "Gestão por subtipo" in slides[20]
    assert "Custódia por subtipo" in slides[21]
    profiles = slides[22:]
    assert len(profiles) == 20
    assert sum("APÊNDICE · CURADORIA TOP 20" in text for text in slides) == 20
    for rank, slide_text in enumerate(profiles, start=1):
        assert "APÊNDICE · CURADORIA TOP 20" in slide_text
        assert f"#{rank} " in slide_text
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
        "Base competência/CNPJ",
        "Base por fundo/CNPJ",
        "Concentração de monoestruturas",
        "Market share por subtipo",
        "Top 20 FIDCs",
        "Top 20 Outros",
        "Curadoria Top 20",
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
