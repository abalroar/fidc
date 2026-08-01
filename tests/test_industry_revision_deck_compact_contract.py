"""Contrato editorial do PPTX compacto da revisão setorial."""

from __future__ import annotations

import posixpath
import os
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
PPTX = Path(
    os.environ.get(
        "FIDC_TEST_PPTX",
        ROOT
        / "data"
        / "industry_study"
        / "generated_revision"
        / "industry_executive_revised.pptx",
    )
)

DML = "http://schemas.openxmlformats.org/drawingml/2006/main"
CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _slide_text(archive: ZipFile, slide_number: int) -> str:
    root = ET.fromstring(archive.read(f"ppt/slides/slide{slide_number}.xml"))
    return " ".join(node.text or "" for node in root.iter(f"{{{DML}}}t"))


def _chart_paths(archive: ZipFile, slide_number: int) -> list[str]:
    rels = ET.fromstring(
        archive.read(f"ppt/slides/_rels/slide{slide_number}.xml.rels")
    )
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


def _chart_roots(archive: ZipFile, slide_number: int) -> list[ET.Element]:
    roots: list[ET.Element] = []
    for path in _chart_paths(archive, slide_number):
        roots.append(ET.fromstring(archive.read(path)))
    return roots


def _tables(archive: ZipFile, slide_number: int) -> list[ET.Element]:
    root = ET.fromstring(archive.read(f"ppt/slides/slide{slide_number}.xml"))
    return root.findall(f".//{{{DML}}}tbl")


def _cell_text(cell: ET.Element) -> str:
    return "".join(node.text or "" for node in cell.iter(f"{{{DML}}}t"))


def _cell_rgb(cell: ET.Element) -> set[str]:
    return {
        node.attrib["val"].upper()
        for node in cell.iter(f"{{{DML}}}srgbClr")
        if node.attrib.get("val")
    }


def _cell_is_bold(cell: ET.Element) -> bool:
    return any(
        node.attrib.get("b", "0").lower() in {"1", "true"}
        for tag in ("rPr", "defRPr", "endParaRPr")
        for node in cell.iter(f"{{{DML}}}{tag}")
    )


def test_compact_pptx_has_26_slides_and_omits_requested_sections() -> None:
    with ZipFile(PPTX) as archive:
        slides = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide")
            and name.endswith(".xml")
            and "/_rels/" not in name
        )
        assert len(slides) == 26
        text = "\n".join(_slide_text(archive, number) for number in range(1, 27))

    for removed in (
        "OBSERVABILIDADE DA INADIMPLÊNCIA",
        "INADIMPLÊNCIA · BASE ORIGINAL",
        "INADIMPLÊNCIA · EX-ZEROS",
        "INADIMPLÊNCIA · COORTE ATUAL POR RECEBÍVEL",
        "INADIMPLÊNCIA · DISPERSÃO ENTRE REPORTANTES",
        "INADIMPLÊNCIA · SÍNTESE EXECUTIVA",
        "APÊNDICE · CURADORIA TOP 20",
        "APÊNDICE · CASO ATLÂNTICO",
        "OUTROS · ABERTURA ANALÍTICA",
        "CONCENTRAÇÃO DAS MONOESTRUTURAS",
        "MARKET SHARE · ADMINISTRAÇÃO",
        "MARKET SHARE · GESTÃO",
        "MARKET SHARE · CUSTÓDIA",
        "ADMINISTRAÇÃO POR SUBTIPO",
        "GESTÃO POR SUBTIPO",
        "CUSTÓDIA POR SUBTIPO",
    ):
        assert removed not in text


def test_slide_3_combines_cvm_and_anbima_instrument_charts() -> None:
    with ZipFile(PPTX) as archive:
        text = _slide_text(archive, 3).upper()
        charts = [
            root
            for root in _chart_roots(archive, 3)
            if root.find(f".//{{{CHART}}}barChart") is not None
        ]

    assert len(charts) == 2
    assert "FIDCS E DEMAIS INSTRUMENTOS ELEGÍVEIS" in text
    assert "VALOR ENCERRADO POR INSTRUMENTO" in text


def test_slide_4_has_two_stacked_sector_charts_and_native_table_without_deltas() -> None:
    with ZipFile(PPTX) as archive:
        text = _slide_text(archive, 4).upper()
        charts = [
            root
            for root in _chart_roots(archive, 4)
            if root.find(f".//{{{CHART}}}barChart") is not None
        ]
        tables = _tables(archive, 4)

    assert len(charts) == 2
    assert {root.find(f".//{{{CHART}}}grouping").attrib["val"] for root in charts} == {
        "stacked",
        "percentStacked",
    }
    assert len(tables) == 1
    assert "EMISSÕES POR SETOR · R$ BI" in text
    assert "EMISSÕES POR SETOR · % DO TOTAL" in text
    assert "EMISSÕES POR CATEGORIA ANBIMA" in text
    assert "DELTA" not in text
    assert "Δ" not in text


def test_slide_4_share_highlights_follow_relative_two_percent_rule() -> None:
    green = "007A3D"
    wine = "7A1F3D"
    with ZipFile(PPTX) as archive:
        table = _tables(archive, 4)[0]
        rows = table.findall(f"{{{DML}}}tr")

    headers = [_cell_text(cell) for cell in rows[0].findall(f"{{{DML}}}tc")]
    assert headers == [
        "Categoria",
        "2023R$ bi",
        "2023%",
        "2024R$ bi",
        "2024%",
        "2025R$ bi",
        "2025%",
        "jan–jun/25R$ bi",
        "jan–jun/25%",
        "jan–jun/26R$ bi",
        "jan–jun/26%",
    ]
    body = {
        _cell_text(cells[0]): cells
        for row in rows[1:5]
        if (cells := row.findall(f"{{{DML}}}tc"))
    }
    expected = {
        "Fomento Mercantil": {4: green, 6: wine, 10: green},
        "Agro, Indústria e Comércio": {4: wine, 6: green, 10: wine},
        "Financeiro": {4: green, 6: wine, 10: green},
        "Outros": {4: wine, 6: green, 10: wine},
    }
    for category, cells in body.items():
        for column in (2, 4, 6, 8, 10):
            colors = _cell_rgb(cells[column])
            highlight = expected[category].get(column)
            if highlight:
                assert highlight in colors
                assert _cell_is_bold(cells[column])
            else:
                assert not ({green, wine} & colors)


def test_analytical_taxonomy_expands_outros_with_the_requested_display_names() -> None:
    with ZipFile(PPTX) as archive:
        text = _slide_text(archive, 5).upper()
        charts = [
            root
            for root in _chart_roots(archive, 5)
            if root.find(f".//{{{CHART}}}barChart") is not None
        ]

    assert len(charts) == 2
    for label in (
        "PRECATÓRIOS E/OU AÇÕES JUDICIAIS",
        "MULTICEDENTE/MULTISACADO",
        "RECUPERAÇÃO / FIDCS NP",
    ):
        assert label in text


def test_taxonomy_rankings_use_two_period_tables_with_originators() -> None:
    with ZipFile(PPTX) as archive:
        for slide_number in range(10, 14):
            text = _slide_text(archive, slide_number).upper()
            assert len(_tables(archive, slide_number)) == 2
            assert "JUN/26 · TOP 15" in text
            assert "DEZ/25 · TOP 15" in text
            assert "ORIGINADOR" in text
