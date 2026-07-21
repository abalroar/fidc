"""Acceptance contract for the 55-slide FIDC industry revision.

This module intentionally lives beside the legacy 47-slide assertions while
the renderer, validators and generated artifacts are migrated together.  It
tests the exported OOXML rather than presentation-library abstractions so an
image or a collection of text boxes cannot satisfy a native Office contract.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
PPTX = ROOT / "outputs" / "Industria_FIDC_Executivo_202607_revisado.pptx"
XLSX = ROOT / "outputs" / "Industria_FIDC_Dados_202607_revisado.xlsx"

TARGET_SLIDES = 55

DML = "http://schemas.openxmlformats.org/drawingml/2006/main"
CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"
SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

MARKET_SHARE_SLIDES = (13, 14, 15, 32, 33, 34)

SLIDE_TOKENS = {
    1: ("INDÚSTRIA DE FIDCs",),
    2: ("SÍNTESE EXECUTIVA",),
    3: (
        "ESCALA DA INDÚSTRIA",
        "CAGR 2015–2018",
        "18,7% A.A.",
        "CAGR 2018–2023",
        "27,9% A.A.",
        "CAGR 2024–2025",
        "25,6% A.A.",
    ),
    4: ("BASE INVESTIDORA",),
    5: ("DISTRIBUIÇÃO POR NÚMERO DE COTISTAS",),
    6: ("TIPO ANBIMA",),
    7: ("TAXONOMIA CVM", "ADQUIRÊNCIA", "16 CNPJs"),
    8: ("CARTEIRA POR TIPO DE RECEBÍVEL",),
    9: ("OBSERVABILIDADE DA INADIMPLÊNCIA",),
    10: ("INADIMPLÊNCIA · EVOLUÇÃO E QUEBRA", "TIPO NA TABELA II"),
    11: ("INADIMPLÊNCIA · COORTE ATUAL POR RECEBÍVEL",),
    12: ("PRESTADORES · RANKING E CONCENTRAÇÃO",),
    13: ("MARKET SHARE · ADMINISTRAÇÃO",),
    14: ("MARKET SHARE · GESTÃO",),
    15: ("MARKET SHARE · CUSTÓDIA",),
    16: ("PRESTADORES · EVOLUÇÃO DO RANKING",),
    17: ("PRESTADORES", "INDEPENDENTES"),
    18: ("BANCOS", "FIDC"),
    19: ("PRESTADORES · LIDERANÇA EXPLICADA",),
    20: ("CBSF / REAG · DESTINO DOS FUNDOS",),
    21: ("PRESTADORES · MIGRAÇÃO EM ADMINISTRAÇÃO",),
    22: ("PRESTADORES · MIGRAÇÃO EM GESTÃO",),
    23: ("PRESTADORES · MIGRAÇÃO EM CUSTÓDIA",),
    24: ("RANKING · TOP 20 FIDCs",),
    25: ("RANKING · TOP 20 OUTROS",),
    26: ("MODELO DE PRESTAÇÃO",),
    27: ("CONCENTRAÇÃO DAS MONOESTRUTURAS",),
    28: ("OFERTAS ENCERRADAS · DISTRIBUIÇÃO DO TICKET",),
    29: ("ORIGINADORES",),
    30: (
        "PRINCIPAIS CONCLUSÕES",
        "RCVM 175",
        "R$ 65,0 BI",
        "R$ 33,0 BI",
        "DOIS FIDCS CIELO",
    ),
    31: ("ESCOPO, FONTES E LIMITAÇÕES",),
    32: ("ADMINISTRAÇÃO POR SUBTIPO",),
    33: ("GESTÃO POR SUBTIPO",),
    34: ("CUSTÓDIA POR SUBTIPO",),
    55: ("APÊNDICE · CASO ATLÂNTICO", "09.194.841/0001-51"),
}

REQUIRED_WORKBOOK_SHEETS_V51 = {
    "QA Inadimplência",
    "Base competência-CNPJ",
    "Base por fundo-CNPJ",
    "Concentração de monoestruturas",
    "Market share por subtipo",
    "Top 20 FIDCs",
    "Top 20 Outros",
    "Curadoria Top 20",
    "Comparativos históricos",
    "Ranking prestadores",
    "Taxonomia adquirência",
    "Atribuição prestadores",
    "Fluxos prestadores",
    "Migração CBSF",
    "Checks revisão",
    "Inadimplência por recebível",
    "Histórico inad. coorte",
    "Ranking independentes",
    "FIDCs por banco",
    "Detalhe coorte bancos",
    "Ofertas encerradas",
    "Histograma ofertas",
    "Originadores 2026",
    "Principais conclusões",
}


def _require(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"artefato ainda não gerado: {path}")


def _slide_text(archive: ZipFile, slide_number: int) -> str:
    root = ET.fromstring(archive.read(f"ppt/slides/slide{slide_number}.xml"))
    return " ".join(node.text or "" for node in root.iter(f"{{{DML}}}t"))


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


def _native_table_count(archive: ZipFile, slide_number: int) -> int:
    slide = ET.fromstring(archive.read(f"ppt/slides/slide{slide_number}.xml"))
    return len(slide.findall(f".//{{{DML}}}tbl"))


def _sheet_names(archive: ZipFile) -> set[str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    return {
        sheet.attrib["name"]
        for sheet in workbook.findall(f".//{{{SHEET}}}sheet")
    }


def test_export_and_renderer_declare_55_slide_contract() -> None:
    export_source = (ROOT / "services" / "industry_revision_export.py").read_text(
        encoding="utf-8"
    )
    renderer_source = (
        ROOT / "scripts" / "build_fidc_revision_artifacts.mjs"
    ).read_text(encoding="utf-8")

    assert re.search(r"^EXPECTED_SLIDES\s*=\s*55\s*$", export_source, re.MULTILINE)
    assert re.search(
        r"^const EXPECTED_SLIDES\s*=\s*55;\s*$", renderer_source, re.MULTILINE
    )
    for sheet_name in REQUIRED_WORKBOOK_SHEETS_V51:
        assert f'"{sheet_name}"' in export_source


def test_deck_has_55_slides_in_the_reviewed_narrative_order() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slide_members = {
            name
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        }
        assert len(slide_members) == TARGET_SLIDES

        for slide_number, tokens in SLIDE_TOKENS.items():
            text = _slide_text(archive, slide_number).upper()
            for token in tokens:
                assert token.upper() in text, (
                    f"slide {slide_number} deveria conter {token!r}; "
                    f"texto observado: {text[:240]!r}"
                )

        profiles = [_slide_text(archive, number) for number in range(35, 55)]

    assert len(profiles) == 20
    for rank, profile in enumerate(profiles, start=1):
        assert "APÊNDICE · CURADORIA TOP 20" in profile
        assert f"#{rank} " in profile


@pytest.mark.parametrize("slide_number", MARKET_SHARE_SLIDES)
def test_market_share_slides_remain_native_percent_stacked_charts(
    slide_number: int,
) -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, slide_number)
        assert len(chart_paths) == 1
        chart = ET.fromstring(archive.read(chart_paths[0]))

    bar_charts = chart.findall(f".//{{{CHART}}}barChart")
    assert len(bar_charts) == 1
    grouping = bar_charts[0].find(f"{{{CHART}}}grouping")
    assert grouping is not None
    assert grouping.attrib.get("val") == "percentStacked"


def test_gross_pl_evolution_remains_one_native_stacked_chart() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, 3)
        assert len(chart_paths) == 1
        chart = ET.fromstring(archive.read(chart_paths[0]))

    bar_charts = chart.findall(f".//{{{CHART}}}barChart")
    assert len(bar_charts) == 1
    grouping = bar_charts[0].find(f"{{{CHART}}}grouping")
    assert grouping is not None
    assert grouping.attrib.get("val") == "stacked"


@pytest.mark.parametrize(
    ("slide_number", "charts", "tables"),
    [
        (16, 3, 3),  # ranking histórico: Administração, Gestão e Custódia
        (17, 3, 3),  # ranking dos prestadores independentes
    ],
)
def test_provider_rankings_use_three_native_table_chart_pairs(
    slide_number: int, charts: int, tables: int
) -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        assert len(_slide_chart_paths(archive, slide_number)) == charts
        assert _native_table_count(archive, slide_number) == tables


@pytest.mark.parametrize(
    ("slide_number", "minimum_charts", "minimum_tables"),
    [
        (10, 1, 1),  # inadimplência por recebível único da Tabela II
        (11, 1, 1),  # histórico da coorte atual por subtipo
        (18, 1, 1),  # evolução dos FIDCs dos cinco bancos
        (28, 1, 1),  # histograma de ofertas encerradas
        (29, 1, 1),  # originadores nomináveis e tickets de emissão
    ],
)
def test_new_analytical_slides_use_native_office_structures(
    slide_number: int, minimum_charts: int, minimum_tables: int
) -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        assert len(_slide_chart_paths(archive, slide_number)) >= minimum_charts
        assert _native_table_count(archive, slide_number) >= minimum_tables


def test_workbook_exposes_the_v55_analysis_tabs() -> None:
    _require(XLSX)
    with ZipFile(XLSX) as archive:
        sheet_names = _sheet_names(archive)

    assert REQUIRED_WORKBOOK_SHEETS_V51.issubset(sheet_names), (
        "abas ausentes: "
        + ", ".join(sorted(REQUIRED_WORKBOOK_SHEETS_V51 - sheet_names))
    )


def test_offer_workbook_uses_counts_billions_and_millions_consistently() -> None:
    _require(XLSX)
    workbook = load_workbook(XLSX, read_only=False, data_only=False)

    offers = workbook["Ofertas encerradas"]
    assert '"bi"' in offers["I5"].number_format
    assert '"mi"' in offers["J5"].number_format
    assert '"mi"' in offers["K5"].number_format
    assert '"bi"' in offers["L5"].number_format

    originators = workbook["Originadores 2026"]
    assert "R$" not in originators["D5"].number_format
    assert '"bi"' in originators["E5"].number_format
    assert '"mi"' in originators["F5"].number_format
    assert '"mi"' in originators["G5"].number_format
    assert '"bi"' in originators["H5"].number_format

    banks = workbook["FIDCs por banco"]
    assert banks["G4"].value == "Raízes de CNPJ listadas"
    assert banks["J4"].value == "Referências"
