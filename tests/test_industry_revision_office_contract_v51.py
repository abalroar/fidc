"""Acceptance contract for the 64-slide FIDC industry revision.

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
PPTX = (
    ROOT
    / "data"
    / "industry_study"
    / "generated_revision"
    / "industry_executive_revised.pptx"
)
XLSX = (
    ROOT
    / "data"
    / "industry_study"
    / "generated_revision"
    / "industry_data_revised.xlsx"
)

TARGET_SLIDES = 64

DML = "http://schemas.openxmlformats.org/drawingml/2006/main"
CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"
SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

MARKET_SHARE_SLIDES = (57, 58, 59, 61, 62, 63)

SLIDE_TOKENS = {
    1: ("INDÚSTRIA DE FIDCs",),
    2: ("GRANDES NÚMEROS",),
    3: (
        "ESCALA DA INDÚSTRIA",
        "CAGR 2015–18",
        "2020/19",
        "2022/21",
        "2026 YTD",
    ),
    4: (
        "OFERTAS ENCERRADAS · SÉRIE CVM",
        "FIDCS E DEMAIS INSTRUMENTOS ELEGÍVEIS",
        "INSTRUMENTOS MAIS EMITIDOS EM 2025",
    ),
    5: ("OFERTAS ENCERRADAS · SÉRIE ANBIMA", "VALOR ENCERRADO POR INSTRUMENTO"),
    6: ("BASE INVESTIDORA",),
    7: ("DISTRIBUIÇÃO POR NÚMERO DE COTISTAS",),
    8: ("TAXONOMIA VIGENTE",),
    9: ("TAXONOMIA CVM", "ADQUIRÊNCIA", "33 CNPJs"),
    10: ("CARTEIRA POR TIPO DE RECEBÍVEL",),
    11: ("OBSERVABILIDADE DA INADIMPLÊNCIA",),
    12: (
        "INADIMPLÊNCIA · BASE ORIGINAL",
        "TIPO NA TABELA II",
        "4,4% DA CARTEIRA",
    ),
    13: ("INADIMPLÊNCIA · EX-ZEROS", "13,5%", "9,1 P.P."),
    14: ("INADIMPLÊNCIA · COORTE ATUAL POR RECEBÍVEL",),
    15: ("INADIMPLÊNCIA · DISPERSÃO ENTRE REPORTANTES",),
    16: ("INADIMPLÊNCIA · SÍNTESE EXECUTIVA",),
    17: ("PRESTADORES · RANKING E CONCENTRAÇÃO",),
    18: ("RANKING · TOP 20 FIDCs",),
    19: ("RANKING · TOP 20 OUTROS",),
    20: ("TIPO ANBIMA · MAIORES FIDCS POR PL",),
    21: ("FOCO ANBIMA · MAIORES FIDCS POR PL",),
    22: ("TABELA II REPORTADA · MAIORES FIDCS POR PL",),
    23: ("TABELA II RECLASSIFICADA · MAIORES FIDCS POR PL",),
    24: ("MODELO DE PRESTAÇÃO",),
    25: ("CONCENTRAÇÃO DAS MONOESTRUTURAS",),
    26: ("OFERTAS ENCERRADAS · VOLUME E TICKET", "JAN–DEZ", "14,6%"),
    27: ("OFERTAS ENCERRADAS · DISTRIBUIÇÃO DO TICKET", "> R$ 100 MI"),
    28: (
        "OFERTAS · VOLUME E REGIME",
        "NÚMERO DE OFERTAS",
        "REGIME DE COLOCAÇÃO · VOLUME",
    ),
    29: (
        "TOP 15 · OFERTAS ENCERRADAS",
        "IBBA PARTICIPOU DE 8 DAS 15 MAIORES",
        "JAN–JUN/26 · TOP 15",
        "2025FY · TOP 15",
    ),
    30: ("TOP 15 · HISTÓRICO", "2024FY · TOP 15", "2023FY · TOP 15"),
    31: ("TOP 15 · 2022 PARCIAL", "7 OFERTAS LEGADAS"),
    32: (
        "PRINCIPAIS CONCLUSÕES",
        "RCVM 175",
        "771 OFERTAS",
        "R$ 65,5 BI",
        "R$ 33,0 BI",
        "DOIS FIDCS CIELO",
    ),
    33: ("ESCOPO, FONTES E LIMITAÇÕES",),
    54: ("PRESTADORES · EVOLUÇÃO E RANKING",),
    55: ("FIDCS DOS CINCO BANCOS · COORTE ATUAL",),
    56: ("PRESTADORES · LIDERANÇA EXPLICADA",),
    57: ("MARKET SHARE · ADMINISTRAÇÃO",),
    58: ("MARKET SHARE · GESTÃO",),
    59: ("MARKET SHARE · CUSTÓDIA",),
    60: ("PRESTADORES · EVIDÊNCIAS DE MIGRAÇÃO", "7,2%", "35,0%"),
    61: ("ADMINISTRAÇÃO POR SUBTIPO",),
    62: ("GESTÃO POR SUBTIPO",),
    63: ("CUSTÓDIA POR SUBTIPO",),
    64: (
        "APÊNDICE · CASO ATLÂNTICO",
        "09.194.841/0001-51",
        "A QUEBRA NO BRUTO COINCIDE",
    ),
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
    "Reconciliação Tabelas I-II",
    "Comparativos históricos",
    "Ranking prestadores",
    "Taxonomia adquirência",
    "Curadoria Cartão",
    "Reclass. adquirência",
    "Top 15 taxonomias",
    "Dispersão inadimplência",
    "Auditoria numérica",
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
    "Comparativo renda fixa",
    "Regime de colocação",
    "Histograma ofertas",
    "Originadores 2026",
    "Top 15 ofertas",
    "Validação emissões",
    "Público-alvo ofertas",
    "Reclass. ANBIMA",
    "Reclass. CVM",
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


def test_export_and_renderer_declare_64_slide_contract() -> None:
    export_source = (ROOT / "services" / "industry_revision_export.py").read_text(
        encoding="utf-8"
    )
    renderer_source = (
        ROOT / "scripts" / "build_fidc_revision_artifacts.mjs"
    ).read_text(encoding="utf-8")

    assert re.search(r"^EXPECTED_SLIDES\s*=\s*64\s*$", export_source, re.MULTILINE)
    assert re.search(
        r"^const EXPECTED_SLIDES\s*=\s*64;\s*$", renderer_source, re.MULTILINE
    )
    for sheet_name in REQUIRED_WORKBOOK_SHEETS_V51:
        assert f'"{sheet_name}"' in export_source


def test_deck_has_64_slides_in_the_reviewed_narrative_order() -> None:
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

        profiles = [_slide_text(archive, number) for number in range(34, 54)]

    assert len(profiles) == 20
    for rank, profile in enumerate(profiles, start=1):
        assert "APÊNDICE · CURADORIA TOP 20" in profile
        assert f"#{rank} " in profile


def test_standard_deck_omits_transition_slides_and_local_file_references() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        all_text = "\n".join(
            _slide_text(archive, number) for number in range(1, TARGET_SLIDES + 1)
        )

    for removed_title in (
        "CBSF / REAG · DESTINO DOS FUNDOS",
        "PRESTADORES · MIGRAÇÃO EM ADMINISTRAÇÃO",
        "PRESTADORES · MIGRAÇÃO EM GESTÃO",
        "PRESTADORES · MIGRAÇÃO EM CUSTÓDIA",
    ):
        assert removed_title not in all_text
    assert ".csv" not in all_text.lower()
    assert ".xml" not in all_text.lower()
    assert "/users/" not in all_text.lower()


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


def test_scale_slide_keeps_two_native_bar_charts() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, 3)
        charts = [ET.fromstring(archive.read(path)) for path in chart_paths]

    bar_charts = [
        chart for chart in charts if chart.find(f".//{{{CHART}}}barChart") is not None
    ]
    assert len(bar_charts) == 2

    groupings = [
        chart.find(f".//{{{CHART}}}barChart/{{{CHART}}}grouping")
        for chart in bar_charts
    ]
    assert {group.attrib.get("val") for group in groupings if group is not None} == {
        "clustered",
        "stacked",
    }

    total_series = []
    for chart in charts:
        for series in chart.findall(f".//{{{CHART}}}lineChart/{{{CHART}}}ser"):
            name = " ".join(
                node.text or "" for node in series.findall(f".//{{{CHART}}}v")
            )
            if "Total" in name:
                total_series.append(series)
    assert len(total_series) == 2
    for series in total_series:
        labels = series.find(f"{{{CHART}}}dLbls")
        assert labels is not None
        number_format = labels.find(f"{{{CHART}}}numFmt")
        assert number_format is not None
        assert number_format.attrib.get("formatCode") == "[>=1000]#\\.##0;0"


def test_native_charts_are_bound_to_ptbr_without_currency_locale_prefix() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = [
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/charts/chart") and name.endswith(".xml")
        ]
        assert chart_paths
        for chart_path in chart_paths:
            root = ET.fromstring(archive.read(chart_path))
            language = root.find(f"{{{CHART}}}lang")
            assert language is not None
            assert language.attrib.get("val") == "pt-BR"
            codes = [
                str(node.attrib.get("formatCode") or "")
                for node in root.iter(f"{{{CHART}}}numFmt")
            ]
            codes.extend(
                str(node.text or "")
                for node in root.iter(f"{{{CHART}}}formatCode")
            )
            for code in codes:
                assert "[$-416]" not in code


def test_combined_provider_ranking_uses_six_native_charts_and_no_tables() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        assert len(_slide_chart_paths(archive, 54)) >= 6
        assert _native_table_count(archive, 54) == 0


@pytest.mark.parametrize(
    ("slide_number", "minimum_charts", "minimum_tables"),
    [
        (4, 2, 0),  # série CVM por instrumento
        (5, 1, 0),  # série ANBIMA por instrumento
        (12, 1, 1),  # inadimplência por recebível único da Tabela II
        (13, 1, 1),  # sensibilidade ex-zeros
        (14, 1, 1),  # histórico da coorte atual por subtipo
        (15, 0, 1),  # dispersão por subcategoria
        (16, 0, 1),  # síntese executiva da dispersão
        (18, 0, 2),  # Top 20 FIDCs em tabelas nativas
        (19, 0, 2),  # Top 20 Outros em tabelas nativas
        (20, 0, 1),  # Top 15 Tipo ANBIMA
        (21, 0, 1),  # Top 15 Foco ANBIMA
        (22, 0, 1),  # Top 15 Tabela II reportada
        (23, 0, 1),  # Top 15 Tabela II reclassificada
        (55, 1, 1),  # evolução dos FIDCs dos cinco bancos
        (26, 2, 1),  # volume/ticket FY/YTD e acumulado mensal
    ],
)
def test_new_analytical_slides_use_native_office_structures(
    slide_number: int, minimum_charts: int, minimum_tables: int
) -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        assert len(_slide_chart_paths(archive, slide_number)) >= minimum_charts
        assert _native_table_count(archive, slide_number) >= minimum_tables


def test_offer_ticket_distribution_uses_three_native_clustered_charts() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, 27)
        assert _native_table_count(archive, 27) == 0
        charts = [ET.fromstring(archive.read(path)) for path in chart_paths]
        bar_charts = [
            chart for chart in charts if chart.find(f".//{{{CHART}}}barChart") is not None
        ]
        assert len(bar_charts) == 3
        for chart in bar_charts:
            bar_chart = chart.find(f".//{{{CHART}}}barChart")
            assert bar_chart is not None
            grouping = bar_chart.find(f"{{{CHART}}}grouping")
            assert grouping is not None
            assert grouping.attrib.get("val") == "clustered"
            assert len(bar_chart.findall(f"{{{CHART}}}ser")) == 3


def test_offer_placement_slide_uses_four_native_bar_charts() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, 28)
        assert _native_table_count(archive, 28) == 0
        charts = [ET.fromstring(archive.read(path)) for path in chart_paths]
        assert sum(
            chart.find(f".//{{{CHART}}}barChart") is not None for chart in charts
        ) == 4


def test_top15_offer_slide_uses_two_native_tables_and_no_chart_images() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        assert _native_table_count(archive, 29) == 2
        assert _slide_chart_paths(archive, 29) == []


def test_june_offer_slide_uses_straight_markerless_native_line_chart() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        charts = [
            ET.fromstring(archive.read(path))
            for path in _slide_chart_paths(archive, 26)
        ]
    line_charts = [
        chart
        for chart in charts
        if any(
            len(series.findall(f".//{{{CHART}}}pt")) > 2
            for series in chart.findall(
                f".//{{{CHART}}}lineChart/{{{CHART}}}ser"
            )
        )
    ]
    assert len(line_charts) == 1
    series = line_charts[0].findall(f".//{{{CHART}}}lineChart/{{{CHART}}}ser")
    assert len(series) == 3
    for item in series:
        symbol = item.find(f".//{{{CHART}}}marker/{{{CHART}}}symbol")
        assert symbol is not None and symbol.attrib.get("val") == "none"
        smooth = item.find(f"{{{CHART}}}smooth")
        assert smooth is None or smooth.attrib.get("val") in {"0", "false"}


def test_workbook_exposes_the_v63_analysis_tabs() -> None:
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

    top15 = workbook["Top 15 ofertas"]
    assert '"bi"' in top15["I5"].number_format
    assert top15["K4"].value == "IBBA Coord-Líder?"
    assert top15["L4"].value == "IBBA Coord?"
    assert top15["S4"].value == "Garantia Firme?"
    assert top15["T4"].value == "Público"
    assert top15["U4"].value == "Nº de Inv."

    banks = workbook["FIDCs por banco"]
    assert banks["J4"].value == "Raízes de CNPJ listadas"
    assert banks["M4"].value == "Referências"
