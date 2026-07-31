"""Acceptance contract for the 64-slide FIDC industry revision.

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

TARGET_SLIDES = 64

DML = "http://schemas.openxmlformats.org/drawingml/2006/main"
CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"
PML = "http://schemas.openxmlformats.org/presentationml/2006/main"
SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

MARKET_SHARE_SLIDES = (58, 59, 60, 61, 62, 63)

SLIDE_TOKENS = {
    1: ("INDÚSTRIA DE FIDCs",),
    2: ("GRANDES NÚMEROS",),
    3: (
        "ESCALA DA INDÚSTRIA",
        "R$ 821,0 BI",
        "R$ 13,780 TRI",
        "CAGR 2015–18",
        "2020/19",
        "2022/21",
        "2026 YTD",
    ),
    4: (
        "OFERTAS ENCERRADAS · SÉRIE CVM",
        "FIDCS E DEMAIS INSTRUMENTOS ELEGÍVEIS",
        "EMISSÕES POR CATEGORIA ANBIMA",
        "TOTAL EMITIDO",
    ),
    5: ("OFERTAS ENCERRADAS · SÉRIE ANBIMA", "VALOR ENCERRADO POR INSTRUMENTO"),
    6: ("BASE INVESTIDORA",),
    7: ("DISTRIBUIÇÃO POR NÚMERO DE COTISTAS",),
    8: ("TAXONOMIA ANALÍTICA · DECISÕES APROVADAS",),
    9: ("OUTROS · ABERTURA ANALÍTICA", "PODER PÚBLICO", "RECUPERAÇÃO", "AÇÕES JUDICIAIS"),
    10: ("TAXONOMIA CVM", "ADQUIRÊNCIA"),
    11: ("CARTEIRA POR TIPO DE RECEBÍVEL",),
    12: ("OBSERVABILIDADE DA INADIMPLÊNCIA",),
    13: (
        "INADIMPLÊNCIA · BASE ORIGINAL",
        "TIPO NA TABELA II",
        "4,4% DA CARTEIRA",
    ),
    14: ("INADIMPLÊNCIA · EX-ZEROS", "13,5%", "9,1 P.P."),
    15: ("INADIMPLÊNCIA · COORTE ATUAL POR RECEBÍVEL",),
    16: ("INADIMPLÊNCIA · DISPERSÃO ENTRE REPORTANTES",),
    17: ("INADIMPLÊNCIA · SÍNTESE EXECUTIVA",),
    18: ("PRESTADORES · RANKING E CONCENTRAÇÃO",),
    19: ("RANKING · TOP 20 FIDCs",),
    20: ("TOP 20 POR TIPO ANALÍTICO", "FOMENTO MERCANTIL"),
    21: ("TOP 20 POR TIPO ANALÍTICO", "AGRO, INDÚSTRIA E COMÉRCIO"),
    22: ("TOP 20 POR TIPO ANALÍTICO", "FINANCEIRO"),
    23: ("TOP 20 POR TIPO ANALÍTICO", "OUTROS"),
    24: ("CURADORIA · FUNDOS FLAGSHIP", "FAIXAS DESCRITIVAS"),
    25: ("CURADORIA · CARTEIRA 1", "CAIXAS INDIVIDUAIS"),
    26: ("CARTEIRA 1 · TAXONOMIA ANALÍTICA", "EVOLUÇÃO DO PL", "PARTICIPAÇÃO NO PL OBSERVADO"),
    27: ("MODELO DE PRESTAÇÃO",),
    28: ("CONCENTRAÇÃO DAS MONOESTRUTURAS",),
    29: ("OFERTAS ENCERRADAS · VOLUME E TICKET", "JAN–DEZ", "14,6%"),
    30: ("OFERTAS ENCERRADAS · DISTRIBUIÇÃO DO TICKET", "> R$ 100 MI"),
    31: (
        "OFERTAS · VOLUME E REGIME",
        "NÚMERO DE OFERTAS",
        "REGIME DE COLOCAÇÃO · VOLUME",
    ),
    32: (
        "TOP 15 · OFERTAS ENCERRADAS",
        "IBBA PARTICIPOU DE 8 DAS 15 MAIORES",
        "JAN–JUN/26 · TOP 15",
        "2025FY · TOP 15",
    ),
    33: ("TOP 15 · HISTÓRICO", "2024FY · TOP 15", "2023FY · TOP 15"),
    34: (
        "PRINCIPAIS CONCLUSÕES",
        "RCVM 175",
        "771 OFERTAS",
        "R$ 65,5 BI",
        "R$ 32,4 BI",
        "DOIS FIDCS CIELO",
    ),
    55: ("PRESTADORES · EVOLUÇÃO E RANKING",),
    56: ("FIDCS DOS CINCO BANCOS · COORTE ATUAL",),
    57: ("PRESTADORES · LIDERANÇA EXPLICADA",),
    58: ("MARKET SHARE · ADMINISTRAÇÃO",),
    59: ("MARKET SHARE · GESTÃO",),
    60: ("MARKET SHARE · CUSTÓDIA",),
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
    "Top 20 por Tipo ANBIMA",
    "Auditoria Top 20 Tipo",
    "Taxonomia por nível",
    "Curadoria flagship",
    "Carteira 1 curadoria",
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


def test_export_and_renderer_declare_fixed_64_slide_contract() -> None:
    export_source = (ROOT / "services" / "industry_revision_export.py").read_text(
        encoding="utf-8"
    )
    renderer_source = (
        ROOT / "scripts" / "build_fidc_revision_artifacts.mjs"
    ).read_text(encoding="utf-8")

    assert re.search(r"^EXPECTED_SLIDES\s*=\s*64\s*$", export_source, re.MULTILINE)
    assert "const SLIDE_CONTRACT_V1 = Object.freeze([" in renderer_source
    assert "const EXPECTED_SLIDES = SLIDE_CONTRACT_V1.length;" in renderer_source
    assert "if (EXPECTED_SLIDES !== 64)" in renderer_source
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

        profiles = [_slide_text(archive, number) for number in range(35, 55)]

    assert len(profiles) == 20
    for rank, profile in enumerate(profiles, start=1):
        assert "APÊNDICE · CURADORIA TOP 20" in profile
        assert f"#{rank} " in profile


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
        text = _slide_text(archive, 3)

    assert "FIDCs ex-FIC" in text
    assert "R$ 821,0 bi" in text
    assert "TOTAL · R$ 13,780 tri" in text
    assert "saldo FIC" not in text


def test_annual_issuance_slide_contains_the_complete_anbima_taxonomy_table() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slide = ET.fromstring(archive.read("ppt/slides/slide4.xml"))
        text = _slide_text(archive, 4)
    tables = slide.findall(f".//{{{DML}}}tbl")
    assert len(tables) == 1
    assert len(tables[0].findall(f"{{{DML}}}tr")) == 8
    assert len(tables[0].findall(f"{{{DML}}}tblGrid/{{{DML}}}gridCol")) == 14
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


def test_flagship_and_portfolio_slides_keep_individual_filled_cards_and_shared_type_colors() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        flagship_text = _slide_text(archive, 24)
        portfolio_text = _slide_text(archive, 25)
        portfolio = ET.fromstring(archive.read("ppt/slides/slide25.xml"))

    assert "12 mínimos júnior localizados em 24 regulamentos revistos" in flagship_text
    assert "101 FUNDOS · CAIXAS INDIVIDUAIS" in portfolio_text
    for token in ("SELLER", "GAZIN", "CLOUDWALK", "PNEUCASH"):
        assert token in portfolio_text.upper()
    filled_shapes = [
        shape
        for shape in portfolio.findall(f".//{{{PML}}}sp")
        if shape.find(f"{{{PML}}}spPr/{{{DML}}}solidFill") is not None
    ]
    assert len(filled_shapes) >= 101
    renderer_source = (
        ROOT / "scripts" / "build_fidc_revision_artifacts.mjs"
    ).read_text(encoding="utf-8")
    assert renderer_source.count("const style = flagshipTypeStyle(row);") >= 2
    carteira_function = renderer_source.split(
        "function addCarteira1CurationSlide", 1
    )[1].split("function addDelinquencyDispersionSlides", 1)[0]
    assert "payload.carteira_1_curation || []" in carteira_function
    assert "payload.carteira_1_curation_ranges" not in carteira_function


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
        assert len(_slide_chart_paths(archive, 55)) >= 6
        assert _native_table_count(archive, 55) == 0


@pytest.mark.parametrize(
    ("slide_number", "minimum_charts", "minimum_tables"),
    [
        (4, 1, 1),  # série anual e tabela de emissões por categoria
        (5, 1, 0),  # série ANBIMA por instrumento
        (13, 1, 1),  # inadimplência por recebível único da Tabela II
        (14, 1, 1),  # sensibilidade ex-zeros
        (15, 1, 1),  # histórico da coorte atual por subtipo
        (16, 0, 1),  # dispersão por subcategoria
        (17, 0, 1),  # síntese executiva da dispersão
        (19, 0, 2),  # Top 20 FIDCs em tabelas nativas
        (20, 0, 1),  # Top 20 Fomento Mercantil
        (21, 0, 1),  # Top 20 Agro, Indústria e Comércio
        (22, 0, 1),  # Top 20 Financeiro
        (23, 0, 1),  # Top 20 Outros
        (56, 1, 1),  # evolução dos FIDCs dos cinco bancos
        (29, 2, 1),  # volume/ticket FY/YTD e acumulado mensal
    ],
)
def test_new_analytical_slides_use_native_office_structures(
    slide_number: int, minimum_charts: int, minimum_tables: int
) -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        assert len(_slide_chart_paths(archive, slide_number)) >= minimum_charts
        assert _native_table_count(archive, slide_number) >= minimum_tables


def test_top20_type_slides_keep_complete_curated_originator_text() -> None:
    _require(PPTX)
    _require(PAYLOAD)
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    slides_by_type = {
        "Fomento Mercantil": 20,
        "Agro, Indústria e Comércio": 21,
        "Financeiro": 22,
        "Outros": 23,
    }
    with ZipFile(PPTX) as archive:
        slide_text = {
            type_name: _slide_text(archive, slide_number)
            for type_name, slide_number in slides_by_type.items()
        }
    curated = [
        row
        for row in payload["top20_by_anbima_type"]
        if row.get("cedente_status") == "curadoria_documental_concluida"
    ]
    assert curated
    for row in curated:
        assert row["cedente_originador"] in slide_text[row["tipo_exibicao"]]


def test_offer_ticket_distribution_uses_three_native_clustered_charts() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, 30)
        assert _native_table_count(archive, 30) == 0
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
        chart_paths = _slide_chart_paths(archive, 31)
        assert _native_table_count(archive, 31) == 0
        charts = [ET.fromstring(archive.read(path)) for path in chart_paths]
        assert sum(
            chart.find(f".//{{{CHART}}}barChart") is not None for chart in charts
        ) == 4


@pytest.mark.parametrize(
    ("slide_number", "expected_tables"),
    [(32, 2), (33, 2)],
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
            for path in _slide_chart_paths(archive, 29)
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


def test_workbook_preserves_taxonomy_levels_and_flagship_documentary_gaps() -> None:
    _require(XLSX)
    workbook = load_workbook(XLSX, read_only=True, data_only=False)

    taxonomy = workbook["Taxonomia por nível"]
    assert taxonomy["A4"].value == "Nível"
    taxonomy_rows = list(taxonomy.iter_rows(min_row=5, values_only=True))
    taxonomy_rows = [row for row in taxonomy_rows if row[0] not in {None, ""}]
    assert len(taxonomy_rows) == 358
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
