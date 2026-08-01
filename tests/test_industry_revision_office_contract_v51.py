"""Acceptance contract for the compact FIDC industry revision.

This module intentionally lives beside the legacy 47-slide assertions while
the renderer, validators and generated artifacts are migrated together.  It
tests the exported OOXML rather than presentation-library abstractions so an
image or a collection of text boxes cannot satisfy a native Office contract.
"""

from __future__ import annotations

from io import BytesIO
import json
import os
import posixpath
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import load_workbook

from services.industry_revision_export import (
    RevisionExportUnavailable,
    _contains_blocked_rgb_color,
    validate_revision_pptx,
)


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
XLSX = Path(
    os.environ.get(
        "FIDC_TEST_XLSX",
        ROOT
        / "data"
        / "industry_study"
        / "generated_revision"
        / "industry_data_revised.xlsx",
    )
)


def test_blocked_palette_detector_only_reads_color_elements() -> None:
    metadata = b'<p:cNvPr xmlns:p="p" id="1" descr="random token 172A3A"/>'
    blocked = b'<a:srgbClr xmlns:a="a" val="172a3a"/>'
    system_fallback = b'<a:sysClr xmlns:a="a" val="window" lastClr="172A3A"/>'

    assert not _contains_blocked_rgb_color([metadata], "172A3A")
    assert _contains_blocked_rgb_color([blocked], "172A3A")
    assert _contains_blocked_rgb_color([system_fallback], "172A3A")


PAYLOAD = (
    ROOT
    / "data"
    / "industry_study"
    / "generated_revision"
    / "artifact_payload.json"
)

TARGET_SLIDES = 26

DML = "http://schemas.openxmlformats.org/drawingml/2006/main"
CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"
PML = "http://schemas.openxmlformats.org/presentationml/2006/main"
SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

SLIDE_TOKENS = {
    1: ("INDÚSTRIA DE FIDCs",),
    2: (
        "ESCALA DA INDÚSTRIA",
        "R$ 821,0 BI",
        "R$ 13,780 TRI",
        "CAGR 2015–18",
        "2020/19",
        "2022/21",
        "2026 YTD",
    ),
    3: (
        "OFERTAS ENCERRADAS · CVM E ANBIMA",
        "FIDCS E DEMAIS INSTRUMENTOS ELEGÍVEIS",
        "VALOR ENCERRADO POR INSTRUMENTO",
    ),
    4: ("EMISSÕES POR CATEGORIA ANBIMA", "EMISSÕES POR SETOR", "TOTAL EMITIDO"),
    5: ("TAXONOMIA ANALÍTICA · OUTROS ABERTO", "PRECATÓRIOS E/OU AÇÕES JUDICIAIS", "MULTICEDENTE/MULTISACADO", "RECUPERAÇÃO / FIDCS NP"),
    6: ("TAXONOMIA CVM", "ADQUIRÊNCIA"),
    7: ("CARTEIRA POR TIPO DE RECEBÍVEL",),
    8: ("PRESTADORES · RANKING E CONCENTRAÇÃO",),
    9: ("RANKING · TOP 20 FIDCs",),
    10: ("TOP FUNDOS E ORIGINADORES", "FOMENTO MERCANTIL"),
    11: ("TOP FUNDOS E ORIGINADORES", "AGRO, INDÚSTRIA E COMÉRCIO"),
    12: ("TOP FUNDOS E ORIGINADORES", "FINANCEIRO"),
    13: ("TOP FUNDOS E ORIGINADORES", "OUTROS"),
    14: ("CURADORIA · FUNDOS FLAGSHIP", "FAIXAS DESCRITIVAS"),
    15: ("CARTEIRA 1 VS. 47 CNPJS FLAGSHIP", "RISCO ACEITO"),
    16: ("CARTEIRA 1 · TAXONOMIA ANALÍTICA", "EVOLUÇÃO DO PL", "PARTICIPAÇÃO NO PL OBSERVADO"),
    17: ("OFERTAS ENCERRADAS · VOLUME E TICKET", "JAN–DEZ", "14,6%"),
    18: ("OFERTAS ENCERRADAS · DISTRIBUIÇÃO DO TICKET", "> R$ 100 MI"),
    19: (
        "OFERTAS · VOLUME E REGIME",
        "NÚMERO DE OFERTAS",
        "REGIME DE COLOCAÇÃO · VOLUME",
    ),
    20: (
        "TOP 15 · OFERTAS ENCERRADAS",
        "IBBA PARTICIPOU DE 8 DAS 15 MAIORES",
        "JAN–JUN/26 · TOP 15",
        "2025FY · TOP 15",
    ),
    21: ("TOP 15 · HISTÓRICO", "2024FY · TOP 15", "2023FY · TOP 15"),
    22: (
        "PRINCIPAIS CONCLUSÕES",
        "RCVM 175",
        "771 OFERTAS",
        "R$ 65,5 BI",
        "R$ 32,4 BI",
        "DOIS FIDCS CIELO",
    ),
    23: ("PRESTADORES · EVOLUÇÃO E RANKING",),
    24: ("PRESTADORES · LIDERANÇA EXPLICADA",),
    25: ("BASE INVESTIDORA",),
    26: ("DISTRIBUIÇÃO POR NÚMERO DE COTISTAS",),
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
    "Top 20 por Tipo ANBIMA",
    "Auditoria Top 20 Tipo",
    "Taxonomia por nível",
    "Curadoria flagship",
    "Carteira 1 curadoria",
    "Carteira 1 vs flagships",
    "Carteira 1 evolução",
    "Curadoria Outros Top 100",
    "Dispersão inadimplência",
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
    "Auditoria emissões",
    "Validação emissões",
    "Emissões por categoria",
    "Público-alvo ofertas",
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


def _xfrm_bbox(xfrm: ET.Element | None) -> tuple[int, int, int, int] | None:
    if xfrm is None:
        return None
    offset = xfrm.find(f"{{{DML}}}off")
    extent = xfrm.find(f"{{{DML}}}ext")
    if offset is None or extent is None:
        return None
    return (
        int(offset.attrib["x"]),
        int(offset.attrib["y"]),
        int(extent.attrib["cx"]),
        int(extent.attrib["cy"]),
    )


def _native_table_bboxes(
    archive: ZipFile, slide_number: int
) -> list[tuple[int, int, int, int]]:
    slide = ET.fromstring(archive.read(f"ppt/slides/slide{slide_number}.xml"))
    bboxes: list[tuple[int, int, int, int]] = []
    for frame in slide.findall(f".//{{{PML}}}graphicFrame"):
        if frame.find(f".//{{{DML}}}tbl") is None:
            continue
        bbox = _xfrm_bbox(frame.find(f"{{{PML}}}xfrm"))
        assert bbox is not None
        bboxes.append(bbox)
    return bboxes


def _shape_bboxes(
    archive: ZipFile, slide_number: int
) -> list[tuple[tuple[int, int, int, int], str]]:
    slide = ET.fromstring(archive.read(f"ppt/slides/slide{slide_number}.xml"))
    bboxes: list[tuple[tuple[int, int, int, int], str]] = []
    for shape in slide.findall(f".//{{{PML}}}sp"):
        bbox = _xfrm_bbox(shape.find(f"{{{PML}}}spPr/{{{DML}}}xfrm"))
        if bbox is None:
            continue
        text = " ".join(node.text or "" for node in shape.iter(f"{{{DML}}}t"))
        bboxes.append((bbox, text))
    return bboxes


def _overlap(
    left: tuple[int, int, int, int], right: tuple[int, int, int, int]
) -> bool:
    left_x, left_y, left_w, left_h = left
    right_x, right_y, right_w, right_h = right
    return (
        max(left_x, right_x) < min(left_x + left_w, right_x + right_w)
        and max(left_y, right_y) < min(left_y + left_h, right_y + right_h)
    )


def _sheet_names(archive: ZipFile) -> set[str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    return {
        sheet.attrib["name"]
        for sheet in workbook.findall(f".//{{{SHEET}}}sheet")
    }


def test_export_and_renderer_declare_fixed_26_slide_contract() -> None:
    export_source = (ROOT / "services" / "industry_revision_export.py").read_text(
        encoding="utf-8"
    )
    renderer_source = (
        ROOT / "scripts" / "build_fidc_revision_artifacts.mjs"
    ).read_text(encoding="utf-8")

    assert re.search(r"^EXPECTED_SLIDES\s*=\s*26\s*$", export_source, re.MULTILINE)
    assert "const SLIDE_CONTRACT_V1 = Object.freeze([" in renderer_source
    assert "const EXPECTED_SLIDES = SLIDE_CONTRACT_V1.length;" in renderer_source
    assert "if (EXPECTED_SLIDES !== 26)" in renderer_source
    for sheet_name in REQUIRED_WORKBOOK_SHEETS_V51:
        assert f'"{sheet_name}"' in export_source


def test_deck_has_26_slides_in_the_reviewed_narrative_order() -> None:
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

        full_text = "\n".join(
            _slide_text(archive, number) for number in range(1, TARGET_SLIDES + 1)
        )

    assert "APÊNDICE · CURADORIA TOP 20" not in full_text
    assert "APÊNDICE · CASO ATLÂNTICO" not in full_text
    assert "OBSERVABILIDADE DA INADIMPLÊNCIA" not in full_text


def test_validator_rejects_a_hidden_slide_outside_slide_three() -> None:
    _require(PPTX)
    mutated = BytesIO()
    with ZipFile(PPTX) as source, ZipFile(mutated, "w", ZIP_DEFLATED) as target:
        for member in source.infolist():
            content = source.read(member.filename)
            if member.filename == "ppt/slides/slide4.xml":
                root = ET.fromstring(content)
                root.set("show", "0")
                content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(member, content)

    with pytest.raises(RevisionExportUnavailable, match="slide oculto"):
        validate_revision_pptx(mutated.getvalue())


def test_standard_deck_omits_transition_slides_and_local_file_references() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        all_text = "\n".join(
            _slide_text(archive, number) for number in range(1, TARGET_SLIDES + 1)
        )

    for removed_title in (
        "OUTROS · FOCO ANALÍTICO",
        "OUTROS · TABELA II ANALÍTICA",
        "OUTROS · TAXONOMIA FUNCIONAL N1",
        "OUTROS · TAXONOMIA FUNCIONAL N2",
        "RANKING · TOP 20 OUTROS",
        "CBSF / REAG · DESTINO DOS FUNDOS",
        "PRESTADORES · MIGRAÇÃO EM ADMINISTRAÇÃO",
        "PRESTADORES · MIGRAÇÃO EM GESTÃO",
        "PRESTADORES · MIGRAÇÃO EM CUSTÓDIA",
        "CONCENTRAÇÃO DAS MONOESTRUTURAS",
        "MARKET SHARE · ADMINISTRAÇÃO",
        "MARKET SHARE · GESTÃO",
        "MARKET SHARE · CUSTÓDIA",
        "ADMINISTRAÇÃO POR SUBTIPO",
        "GESTÃO POR SUBTIPO",
        "CUSTÓDIA POR SUBTIPO",
    ):
        assert removed_title not in all_text
    assert ".csv" not in all_text.lower()
    assert ".xml" not in all_text.lower()
    assert "/users/" not in all_text.lower()

def test_scale_slide_keeps_two_native_bar_charts() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, 2)
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
    assert len(total_series) == 1
    for series in total_series:
        title = series.find(f"{{{CHART}}}tx")
        assert title is not None
        assert title.find(f"{{{CHART}}}v") is not None
        assert title.find(f"{{{CHART}}}strLit") is None
        labels = series.find(f"{{{CHART}}}dLbls")
        assert labels is not None
        children = [node.tag for node in series]
        assert children.index(f"{{{CHART}}}dLbls") < children.index(
            f"{{{CHART}}}cat"
        ) < children.index(f"{{{CHART}}}val")
        position = labels.find(f"{{{CHART}}}dLblPos")
        assert position is not None
        assert position.attrib.get("val") == "t"
        number_format = labels.find(f"{{{CHART}}}numFmt")
        assert number_format is not None
        assert number_format.attrib.get("formatCode") == "[>=1000]#\\.##0;0"


def test_scale_slide_uses_only_ex_fic_pl_and_explicit_brazilian_labels() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        text = _slide_text(archive, 2)

    assert "FIDCs ex-FIC" in text
    assert "R$ 821,0 bi" in text
    assert "TOTAL · R$ 13,780 tri" in text
    assert "saldo FIC" not in text


def test_ex_fic_pl_chart_has_native_value_labels_for_every_data_point() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        bar_charts = []
        for path in _slide_chart_paths(archive, 2):
            root = ET.fromstring(archive.read(path))
            bar = root.find(f".//{{{CHART}}}barChart")
            if bar is not None:
                bar_charts.append(bar)

    ex_fic = next(
        bar
        for bar in bar_charts
        if len(bar.findall(f"{{{CHART}}}ser")) == 1
    )
    labels = ex_fic.find(f"{{{CHART}}}dLbls")
    assert labels is not None
    show_value = labels.find(f"{{{CHART}}}showVal")
    assert show_value is not None and show_value.attrib.get("val") == "1"
    series = ex_fic.find(f"{{{CHART}}}ser")
    assert series is not None
    points = series.findall(
        f"{{{CHART}}}val/{{{CHART}}}numLit/{{{CHART}}}pt"
    )
    assert len(points) == 12


def test_analytical_taxonomy_uses_only_bba_colors_and_labels_all_periods() -> None:
    _require(PPTX)
    allowed = {
        "151515",
        "30353A",
        "73787D",
        "8D9399",
        "D7DADD",
        "E7E9EB",
        "EC7000",
        "FFFFFF",
    }
    with ZipFile(PPTX) as archive:
        charts = []
        for path in _slide_chart_paths(archive, 5):
            root = ET.fromstring(archive.read(path))
            bar = root.find(f".//{{{CHART}}}barChart")
            if bar is not None:
                charts.append(bar)

    assert len(charts) == 2
    for bar in charts:
        labels = bar.find(f"{{{CHART}}}dLbls")
        assert labels is not None
        show_value = labels.find(f"{{{CHART}}}showVal")
        assert show_value is not None and show_value.attrib.get("val") == "1"
        series = bar.findall(f"{{{CHART}}}ser")
        assert len(series) == 7
        for item in series:
            colors = {
                str(node.attrib.get("val") or "").upper()
                for node in item.iter(f"{{{DML}}}srgbClr")
            }
            assert colors <= allowed
            values = item.findall(
                f"{{{CHART}}}val/{{{CHART}}}numLit/{{{CHART}}}pt"
            )
            item_labels = item.find(f"{{{CHART}}}dLbls")
            assert item_labels is not None
            assert len(item_labels.findall(f"{{{CHART}}}dLbl")) == len(values) == 4


def test_annual_issuance_slide_contains_the_complete_anbima_taxonomy_table() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slide = ET.fromstring(archive.read("ppt/slides/slide4.xml"))
        text = _slide_text(archive, 4)
    tables = slide.findall(f".//{{{DML}}}tbl")
    assert len(tables) == 1
    assert len(tables[0].findall(f"{{{DML}}}tr")) == 8
    assert len(tables[0].findall(f"{{{DML}}}tblGrid/{{{DML}}}gridCol")) == 11
    for token in (
        "EMISSÕES POR CATEGORIA ANBIMA",
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
        "FIC-FIDC · reconciliação",
        "Total emitido",
    ):
        assert token in text


def test_flagship_and_portfolio_slides_keep_traceable_comparison_tables() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        flagship_text = _slide_text(archive, 14)
        portfolio_text = _slide_text(archive, 15)
        portfolio = ET.fromstring(archive.read("ppt/slides/slide15.xml"))
        portfolio_table_count = _native_table_count(archive, 15)

    assert "12 mínimos júnior localizados em 24 regulamentos revistos" in flagship_text
    assert "47 CNPJS FLAGSHIP" in portfolio_text.upper()
    for token in (
        "ADQUIRÊNCIA",
        "AGRO / REVENDA",
        "CONSIGNADO INSS",
        "CONSIGNADO FGTS",
        "VEÍCULOS",
        "FACTORING",
        "FINANCEIRO",
        "RISCO ACEITO",
    ):
        assert token in portfolio_text.upper()
    assert portfolio_table_count == 7
    filled_shapes = [
        shape
        for shape in portfolio.findall(f".//{{{PML}}}sp")
        if shape.find(f"{{{PML}}}spPr/{{{DML}}}solidFill") is not None
    ]
    assert len(filled_shapes) >= 7
    renderer_source = (
        ROOT / "scripts" / "build_fidc_revision_artifacts.mjs"
    ).read_text(encoding="utf-8")
    carteira_function = renderer_source.split(
        "function addCarteira1CurationSlide", 1
    )[1].split("function addDelinquencyDispersionSlides", 1)[0]
    assert "payload.carteira_1_flagship_comparison || []" in carteira_function
    assert "rows.length !== 7" in carteira_function
    assert "num(summary.flagship_cnpjs) !== 47" in carteira_function


def test_native_chart_series_titles_use_schema_supported_forms() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = [
            name
            for name in archive.namelist()
            if "/charts/chart" in name and name.endswith(".xml")
        ]
        assert chart_paths
        for chart_path in chart_paths:
            chart = ET.fromstring(archive.read(chart_path))
            invalid_titles = chart.findall(
                f".//{{{CHART}}}ser/{{{CHART}}}tx/{{{CHART}}}strLit"
            )
            assert invalid_titles == []


def test_native_charts_are_bound_to_ptbr_without_currency_locale_prefix() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = [
            name
            for name in archive.namelist()
            if (
                name.endswith(".xml")
                and (
                    name.startswith("ppt/charts/chart")
                    or name.startswith("ppt/slides/charts/chart")
                )
            )
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


def test_visible_slide_text_uses_brazilian_decimal_separators() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        for slide_number in range(1, TARGET_SLIDES + 1):
            raw = archive.read(f"ppt/slides/slide{slide_number}.xml")
            text = _slide_text(archive, slide_number)
            assert b'lang="en-US"' not in raw
            assert re.search(r"R\$\s*\d+\.\d{1,2}(?:\s|$)", text) is None
            assert re.search(r"\d+\.\d+%", text) is None


def test_combined_provider_ranking_uses_six_native_charts_and_no_tables() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        assert len(_slide_chart_paths(archive, 23)) >= 6
        assert _native_table_count(archive, 23) == 0


@pytest.mark.parametrize(
    ("slide_number", "minimum_charts", "minimum_tables"),
    [
        (3, 2, 0),  # séries CVM e ANBIMA no mesmo slide
        (4, 2, 1),  # taxonomia em R$ bi, % e tabela
        (9, 0, 2),  # Top 20 FIDCs em tabelas nativas
        (10, 0, 2),  # Fomento: jun/26 e dez/25
        (11, 0, 2),  # Agro: jun/26 e dez/25
        (12, 0, 2),  # Financeiro: jun/26 e dez/25
        (13, 0, 2),  # Outros: jun/26 e dez/25
        (15, 0, 7),  # Carteira 1 versus os sete tipos flagship
        (17, 2, 1),  # volume/ticket FY/YTD e acumulado mensal
    ],
)
def test_new_analytical_slides_use_native_office_structures(
    slide_number: int, minimum_charts: int, minimum_tables: int
) -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        assert len(_slide_chart_paths(archive, slide_number)) >= minimum_charts
        assert _native_table_count(archive, slide_number) >= minimum_tables


def test_top_type_slides_compare_two_periods_and_show_originator_column() -> None:
    _require(PPTX)
    _require(PAYLOAD)
    slides_by_type = {
        "Fomento Mercantil": 10,
        "Agro, Indústria e Comércio": 11,
        "Financeiro": 12,
        "Outros": 13,
    }
    with ZipFile(PPTX) as archive:
        slide_text = {
            type_name: _slide_text(archive, slide_number)
            for type_name, slide_number in slides_by_type.items()
        }
    for type_name, text in slide_text.items():
        assert type_name in text
        assert "JUN/26 · TOP 15" in text
        assert "DEZ/25 · TOP 15" in text
        assert text.count("Originador") >= 2


def test_offer_ticket_distribution_uses_three_native_clustered_charts() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, 18)
        assert _native_table_count(archive, 18) == 0
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
        chart_paths = _slide_chart_paths(archive, 19)
        assert _native_table_count(archive, 19) == 0
        charts = [ET.fromstring(archive.read(path)) for path in chart_paths]
        assert sum(
            chart.find(f".//{{{CHART}}}barChart") is not None for chart in charts
        ) == 4


@pytest.mark.parametrize(
    ("slide_number", "expected_tables"),
    [(20, 2), (21, 2)],
)
def test_top15_offer_slides_use_only_on_canvas_native_tables(
    slide_number: int, expected_tables: int
) -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
        slide_size = presentation.find(f"{{{PML}}}sldSz")
        assert slide_size is not None
        canvas_width = int(slide_size.attrib["cx"])
        canvas_height = int(slide_size.attrib["cy"])

        tables = _native_table_bboxes(archive, slide_number)
        assert len(tables) == expected_tables
        assert _native_table_count(archive, slide_number) == expected_tables
        assert _slide_chart_paths(archive, slide_number) == []
        for left, top, width, height in tables:
            assert left >= 0
            assert top >= 0
            assert width > 0
            assert height > 0
            assert left + width <= canvas_width
            assert top + height <= canvas_height

        overlapping_shapes = [
            text or "<shape sem texto>"
            for shape_bbox, text in _shape_bboxes(archive, slide_number)
            if any(_overlap(shape_bbox, table_bbox) for table_bbox in tables)
        ]
        assert overlapping_shapes == []


def test_june_offer_slide_uses_straight_markerless_native_line_chart() -> None:
    _require(PPTX)
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    with ZipFile(PPTX) as archive:
        charts = [
            ET.fromstring(archive.read(path))
            for path in _slide_chart_paths(archive, 17)
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
    line_chart = line_charts[0]
    blanks = line_chart.find(f".//{{{CHART}}}dispBlanksAs")
    assert blanks is not None and blanks.attrib.get("val") == "gap"
    series = line_chart.findall(f".//{{{CHART}}}lineChart/{{{CHART}}}ser")
    assert len(series) == 3
    series_by_name = {
        str(item.findtext(f"{{{CHART}}}tx/{{{CHART}}}v") or ""): item
        for item in series
    }
    assert set(series_by_name) == {"2024", "2025", "2026"}
    for item in series:
        symbol = item.find(f".//{{{CHART}}}marker/{{{CHART}}}symbol")
        assert symbol is not None and symbol.attrib.get("val") == "none"
        smooth = item.find(f"{{{CHART}}}smooth")
        assert smooth is None or smooth.attrib.get("val") in {"0", "false"}

    point_indices: dict[str, list[int]] = {}
    point_values: dict[str, dict[int, float]] = {}
    for name, item in series_by_name.items():
        points = item.findall(
            f"{{{CHART}}}val/{{{CHART}}}numLit/{{{CHART}}}pt"
        )
        point_indices[name] = [int(point.attrib["idx"]) for point in points]
        point_values[name] = {
            int(point.attrib["idx"]): float(
                point.findtext(f"{{{CHART}}}v") or "nan"
            )
            for point in points
        }

    assert point_indices["2024"] == list(range(12))
    assert point_indices["2025"] == list(range(12))
    assert point_indices["2026"] == list(range(6))
    expected_june_2026 = sum(
        float(row["registered_volume_brl"])
        for row in payload["closed_offers_monthly"]
        if int(row["year"]) == 2026 and int(row["month"]) <= 6
    ) / 1e9
    assert point_values["2026"][5] == pytest.approx(expected_june_2026)


def test_workbook_exposes_the_v63_analysis_tabs() -> None:
    _require(XLSX)
    with ZipFile(XLSX) as archive:
        sheet_names = _sheet_names(archive)

    assert REQUIRED_WORKBOOK_SHEETS_V51.issubset(sheet_names), (
        "abas ausentes: "
        + ", ".join(sorted(REQUIRED_WORKBOOK_SHEETS_V51 - sheet_names))
    )


def test_emission_audit_sheet_materializes_180_sourced_rows_and_preserves_nd() -> None:
    _require(XLSX)
    workbook = load_workbook(XLSX, read_only=True, data_only=False)
    sheet = workbook["Auditoria emissões"]
    headers = [sheet.cell(4, column).value for column in range(1, 16)]
    assert headers == [
        "Bloco do deck",
        "Tabela / período",
        "CNPJ",
        "ID da emissão",
        "Fundo",
        "Originador",
        "Subordinação mínima",
        "Preço por tipo de cota",
        "Cedente",
        "Sacado",
        "Fonte originador / cedente",
        "Fonte subordinação",
        "Fonte preço",
        "Fonte sacado",
        "Status",
    ]
    rows = list(
        sheet.iter_rows(min_row=5, max_row=184, min_col=1, max_col=15, values_only=True)
    )
    assert len(rows) == 180
    assert sum(row[0] == "slides 10–13" for row in rows) == 120
    assert sum(row[0] == "slides 21–22" for row in rows) == 60
    assert all(value not in {None, ""} for row in rows for value in row)
    assert all(
        re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", str(row[2]))
        for row in rows
    )
    assert all(str(row[3]).startswith(("E ", "N/D")) for row in rows)
    assert [sum(row[column] != "N/D" for row in rows) for column in range(5, 10)] == [
        41,
        15,
        14,
        5,
        0,
    ]


def test_workbook_preserves_taxonomy_levels_and_flagship_documentary_gaps() -> None:
    _require(XLSX)
    workbook = load_workbook(XLSX, read_only=True, data_only=False)

    taxonomy = workbook["Taxonomia por nível"]
    assert taxonomy["A4"].value == "Nível"
    taxonomy_rows = list(taxonomy.iter_rows(min_row=5, values_only=True))
    taxonomy_rows = [row for row in taxonomy_rows if row[0] not in {None, ""}]
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    assert len(taxonomy_rows) == len(payload["taxonomy_level_history"])
    assert {row[0] for row in taxonomy_rows} == {
        "Foco analítico",
        "Tabela II analítica",
        "Taxonomia funcional N1",
        "Taxonomia funcional N2",
    }
    assert any(row[3] == "Judicial/Precatórios/NPL" for row in taxonomy_rows)
    assert all(isinstance(row[4], (int, float)) and row[4] >= 0 for row in taxonomy_rows)

    flagship = workbook["Curadoria flagship"]
    assert flagship["E4"].value == "CNPJ"
    assert flagship["G4"].value == "PL atual"
    assert flagship["I4"].value == "Subordinação atual / PL"
    assert flagship["N4"].value == "Mínimo júnior"
    assert flagship["R4"].value == "Preço/VNU numérico"
    assert flagship["AE4"].value == "Documento do regulamento revisto"
    assert flagship["AI4"].value == "Status da curadoria documental"
    rows = list(flagship.iter_rows(min_row=5, max_col=38, values_only=True))
    rows = [row for row in rows if row[4] not in {None, ""}]
    assert len(rows) == 47
    assert len({row[4] for row in rows}) == 47
    assert all(isinstance(row[6], (int, float)) and row[6] > 0 for row in rows)
    assert all(isinstance(row[8], (int, float)) and 0 <= row[8] <= 1 for row in rows)
    assert all(row[13] is None or row[13] > 0 for row in rows)
    assert all(row[17] is None or row[17] > 0 for row in rows)
    assert any(row[13] is None and row[14] == "N/D" for row in rows)
    assert any(row[17] is None and row[18] == "N/D" for row in rows)
    assert sum(str(row[34]).startswith("revisto") for row in rows) == 24
    assert sum(row[14] != "N/D" for row in rows) == 12

    carteira_1 = workbook["Carteira 1 curadoria"]
    assert carteira_1["C4"].value == "Raiz CNPJ · foto"
    assert carteira_1["D4"].value == "Nome · foto"
    assert carteira_1["J4"].value == "PL atual"
    assert carteira_1["L4"].value == "Subordinação atual / PL"
    assert carteira_1["O4"].value == "Mínimo júnior"
    assert carteira_1["T4"].value == "Emissão · mês/ano"
    carteira_rows = list(
        carteira_1.iter_rows(min_row=5, max_col=35, values_only=True)
    )
    carteira_rows = [row for row in carteira_rows if row[0] not in {None, ""}]
    assert len(carteira_rows) == 101
    assert len({row[7] for row in carteira_rows}) == 101
    assert sum(row[9] is not None for row in carteira_rows) == 78
    assert sum(row[11] is not None for row in carteira_rows) == 68
    assert sum(row[14] is not None for row in carteira_rows) == 50
    assert sum(row[19] != "N/D" for row in carteira_rows) == 97
    assert sum(str(row[31]).startswith("fora do perímetro FIDC") for row in carteira_rows) == 1
    assert all(row[9] is None or row[9] > 0 for row in carteira_rows)
    assert all(row[14] is None or row[14] > 0 for row in carteira_rows)


def test_top20_type_workbook_keeps_rank_share_date_and_coverage_typed() -> None:
    _require(XLSX)
    workbook = load_workbook(XLSX, read_only=False, data_only=False)
    sheet = workbook["Top 20 por Tipo ANBIMA"]

    assert sheet["B4"].value == "Rank"
    assert isinstance(sheet["B5"].value, (int, float))
    assert sheet["F4"].value == "% do bucket"
    assert isinstance(sheet["F5"].value, (int, float))
    assert sheet["F5"].number_format == "0.0%"
    assert sheet["G4"].value == "Competência"
    assert sheet["G5"].value == "2026-06"
    assert "R$" not in sheet["G5"].number_format
    assert sheet["H4"].value == "Mai/26 disponível"
    assert isinstance(sheet["H5"].value, bool)
    assert "R$" not in sheet["H5"].number_format


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
