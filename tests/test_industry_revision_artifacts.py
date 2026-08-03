from __future__ import annotations

import json
import os
import posixpath
import re
from pathlib import Path
import unicodedata
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from services.industry_revision_export import (
    CURRENT_TOP15_SLIDE_SEQUENCE,
    EXPECTED_SLIDE_SEQUENCE,
    EXPECTED_SLIDES,
    HISTORICAL_TOP15_SLIDE_SEQUENCE,
    STRUCTURAL_MVP_SLIDE_SEQUENCE,
    _contains_blocked_rgb_color,
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
FLOW_HTML = Path(
    os.environ.get(
        "FIDC_TEST_HTML",
        ROOT
        / "data"
        / "industry_study"
        / "generated_revision"
        / "provider_flows_explorer.html",
    )
)
PAYLOAD = Path(
    os.environ.get(
        "FIDC_TEST_PAYLOAD",
        ROOT
        / "data"
        / "industry_study"
        / "generated_revision"
        / "artifact_payload.json",
    )
)

PML = "http://schemas.openxmlformats.org/presentationml/2006/main"
DML = "http://schemas.openxmlformats.org/drawingml/2006/main"
CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"
SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _fold(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(
        "".join(char for char in normalized if not unicodedata.combining(char))
        .lower()
        .split()
    )


def _contract_slide_numbers(*needles: str) -> tuple[int, ...]:
    folded_needles = tuple(_fold(needle) for needle in needles)
    return tuple(
        index
        for index, tokens in enumerate(EXPECTED_SLIDE_SEQUENCE, start=1)
        if all(
            any(needle in _fold(token) for token in tokens)
            for needle in folded_needles
        )
    )


def _contract_slide_number(*needles: str) -> int:
    matches = _contract_slide_numbers(*needles)
    assert len(matches) == 1, (needles, matches)
    return matches[0]


def _sequence_slide_numbers(
    sequence: tuple[tuple[str, ...], ...],
) -> tuple[int, ...]:
    return tuple(
        EXPECTED_SLIDE_SEQUENCE.index(tokens) + 1 for tokens in sequence
    )


STRUCTURAL_MVP_SLIDES = _sequence_slide_numbers(STRUCTURAL_MVP_SLIDE_SEQUENCE)
SLIDE_OFFERS_VOLUME = _contract_slide_number("emissoes crescem 15%")
SLIDE_OFFER_TICKETS = _contract_slide_number("22 ofertas concentram")
SLIDE_OFFER_REGIME = _contract_slide_number("garantia firme", "yoy ytd")
SLIDES_TOP15_CURRENT = _sequence_slide_numbers(CURRENT_TOP15_SLIDE_SEQUENCE)
SLIDES_TOP15_HISTORY = _sequence_slide_numbers(HISTORICAL_TOP15_SLIDE_SEQUENCE)
SLIDE_CONCLUSIONS = _contract_slide_number("o que muda")
SLIDE_PROVIDER_HISTORY = _contract_slide_number("qi lidera administracao")
SLIDE_PROVIDER_RANKING = _contract_slide_number("prestadores", "ranking e concentracao")
SLIDE_INVESTOR_BASE = _contract_slide_number("quase todo o volume")
SLIDE_HOLDER_DISTRIBUTION = _contract_slide_number("distribuicao por numero")


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


def _slide_image_paths(archive: ZipFile, slide_number: int) -> list[str]:
    rels_path = f"ppt/slides/_rels/slide{slide_number}.xml.rels"
    rels = ET.fromstring(archive.read(rels_path))
    paths: list[str] = []
    for rel in rels.findall(f"{{{PACKAGE_REL}}}Relationship"):
        if not rel.attrib.get("Type", "").endswith("/image"):
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


def _cell_text(cell: ET.Element) -> str:
    return "".join(node.text or "" for node in cell.iter(f"{{{DML}}}t")).strip()


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


def test_deck_order_and_compact_appendix_contract() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slides = _slide_texts(archive)

    assert len(slides) == EXPECTED_SLIDES == len(EXPECTED_SLIDE_SEQUENCE)
    assert "Indústria de FIDCs — ago-26" in slides[0]
    assert "Dados de referência: jun-26" in slides[0]
    for slide_number, (slide_text, required_tokens) in enumerate(
        zip(slides, EXPECTED_SLIDE_SEQUENCE, strict=True),
        start=1,
    ):
        folded_text = _fold(slide_text)
        for token in required_tokens:
            assert _fold(token) in folded_text, (
                f"slide {slide_number} deveria conter {token!r}; "
                f"texto observado: {slide_text[:240]!r}"
            )
    assert all("APÊNDICE · CURADORIA TOP 20" not in text for text in slides)
    assert all("INADIMPLÊNCIA ·" not in text for text in slides)
    assert "QI lidera administração; BTG lidera gestão e custódia" in slides[
        SLIDE_PROVIDER_HISTORY - 1
    ]
    assert "PRESTADORES · RANKING E CONCENTRAÇÃO" in slides[
        SLIDE_PROVIDER_RANKING - 1
    ]
    assert all("PRESTADORES · EVIDÊNCIAS DE MIGRAÇÃO" not in text for text in slides)
    assert "Quase todo o volume vai para o investidor profissional" in slides[
        SLIDE_INVESTOR_BASE - 1
    ]
    assert "DISTRIBUIÇÃO POR NÚMERO DE COTISTAS" in slides[
        SLIDE_HOLDER_DISTRIBUTION - 1
    ]
    for removed_title in (
        "CONCENTRAÇÃO DAS MONOESTRUTURAS",
        "MARKET SHARE · ADMINISTRAÇÃO",
        "MARKET SHARE · GESTÃO",
        "MARKET SHARE · CUSTÓDIA",
        "Administração por subtipo",
        "Gestão por subtipo",
        "Custódia por subtipo",
    ):
        assert all(removed_title not in text for text in slides)
    assert all("APÊNDICE · CASO ATLÂNTICO" not in text for text in slides)
    deck_text = "\n".join(slides)
    assert deck_text.count("R$ 16,69 bi") == 0
    assert "Visão ex-360 bloqueada" not in deck_text


def test_structural_audit_corrections_are_materialized_in_the_deck() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slides = _slide_texts(archive)

    assert "58,4%" in slides[SLIDE_CONCLUSIONS - 1]
    assert "PL ≥ R$ 200 mi" in slides[SLIDE_HOLDER_DISTRIBUTION - 1]
    assert "Financeiro explicou 70% do crescimento da carteira" in slides[7]
    assert "Emissões crescem 15% no semestre" in slides[SLIDE_OFFERS_VOLUME - 1]
    assert re.search(r"2022 FY.*N/D N/D", slides[SLIDE_OFFERS_VOLUME - 1])
    assert "66,0% dos R$ 77,7 bi" in slides[SLIDE_CONCLUSIONS - 1]
    assert all("PRESTADORES · EVIDÊNCIAS DE MIGRAÇÃO" not in text for text in slides)
    assert all("APÊNDICE · CASO ATLÂNTICO" not in text for text in slides)

    deck_text = "\n".join(slides)
    assert "FICs excluídos pelo portão único" not in deck_text
    assert "Kanastra permanece separada do Itaú" not in deck_text
    for stale in (
        "R$ 5.500 bi",
        "R$ 4.200 bi",
        "R$ 2.500 bi",
        "R$ 1.000 bi",
        "R$ 11.000 bi",
        "explicou 67%",
        "1 pendentes",
        "O 99% é coerente",
    ):
        assert stale not in deck_text
    assert "Factoring→Fomento" not in deck_text
    assert all(len(slide_text.strip()) > 80 for slide_text in slides)


def test_structural_mvp_contract_has_six_contiguous_taxonomy_slides() -> None:
    assert EXPECTED_SLIDES == 37
    assert STRUCTURAL_MVP_SLIDE_SEQUENCE == (
        ("risco estrutural", "financeiro", "carteira i"),
        ("risco estrutural", "adquirencia", "carteira i"),
        ("risco estrutural", "agro / revenda", "carteira i"),
        ("risco estrutural", "risco corporativo", "carteira i"),
        ("risco estrutural", "consignado inss e fgts", "carteira i"),
        ("risco estrutural", "factoring", "carteira i"),
    )
    assert STRUCTURAL_MVP_SLIDES == tuple(
        range(STRUCTURAL_MVP_SLIDES[0], STRUCTURAL_MVP_SLIDES[0] + 6)
    )
    assert ("risco estrutural", "cobertura por taxonomia") not in (
        EXPECTED_SLIDE_SEQUENCE
    )
    assert ("risco estrutural", "ativos") not in EXPECTED_SLIDE_SEQUENCE


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


def test_scale_slide_uses_two_native_office_charts_with_ex_fic_pl_and_total() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, 2)
        slide = ET.fromstring(archive.read("ppt/slides/slide2.xml"))
        text = " ".join(
            node.text or "" for node in slide.iter(f"{{{DML}}}t")
        )
        charts = [
            ET.fromstring(archive.read(path)) for path in chart_paths
        ]

    charts = [
        chart for chart in charts if chart.find(f".//{{{CHART}}}barChart") is not None
    ]
    assert len(charts) == 2
    assert "FIDCs ex-FIC" in text
    assert "R$ 821,0 bi" in text
    assert "R$ 13,780 tri" in text
    assert "SALDO FIC" not in text.upper()
    assert "Carteira de crédito privada ampliada · R$ bi" in text
    assert "excluídos títulos públicos" in text
    assert "demais securitizações (CRIs e CRAs)" in text
    assert "PL direto e carteira privada têm perímetros contábeis distintos" in text
    assert "Mai/26" not in text

    left_bar = charts[0].find(f".//{{{CHART}}}barChart")
    right_bar = charts[1].find(f".//{{{CHART}}}barChart")
    assert left_bar is not None and right_bar is not None
    assert len(left_bar.findall(f"{{{CHART}}}ser")) == 1
    assert (
        left_bar.find(f"{{{CHART}}}grouping").attrib.get("val")
        == "clustered"
    )
    assert len(right_bar.findall(f"{{{CHART}}}ser")) == 5
    assert (
        right_bar.find(f"{{{CHART}}}grouping").attrib.get("val")
        == "stacked"
    )


def test_taxonomy_slide_has_two_native_office_charts_for_anbima_evolution() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, 6)
        chart_xml = [
            archive.read(name)
            for name in chart_paths
            if ET.fromstring(archive.read(name)).find(f".//{{{CHART}}}barChart") is not None
        ]
        assert len(chart_xml) == 2

    groupings: set[str] = set()
    for raw in chart_xml:
        root = ET.fromstring(raw)
        bar_direction = root.find(f".//{{{CHART}}}barDir")
        grouping = root.find(f".//{{{CHART}}}grouping")
        assert bar_direction is not None
        assert bar_direction.attrib.get("val") == "col"
        assert grouping is not None
        groupings.add(str(grouping.attrib.get("val")))
        visible = raw.decode("utf-8", errors="ignore")
        for label in ("dez/23", "dez/24", "dez/25", "jun/26"):
            assert label in visible
        for label in (
            "Precatórios e/ou Ações Judiciais",
            "Multicedente/Multisacado",
            "Recuperação / FIDCs NP",
            "N/D",
        ):
            assert f">{label}<" in visible
    assert groupings == {"stacked", "percentStacked"}


def test_offer_slides_use_native_charts_and_editable_native_tables() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        ticket_charts = _slide_chart_paths(archive, SLIDE_OFFER_TICKETS)
        ticket_charts = [
            path for path in ticket_charts
            if ET.fromstring(archive.read(path)).find(f".//{{{CHART}}}barChart") is not None
        ]
        assert len(ticket_charts) == 3
        ticket_slide = ET.fromstring(
            archive.read(f"ppt/slides/slide{SLIDE_OFFER_TICKETS}.xml")
        )
        assert ticket_slide.findall(f".//{{{DML}}}tbl") == []
        for chart_path in ticket_charts:
            chart = ET.fromstring(archive.read(chart_path))
            bar_chart = chart.find(f".//{{{CHART}}}barChart")
            assert bar_chart is not None
            grouping = bar_chart.find(f"{{{CHART}}}grouping")
            assert grouping is not None
            assert grouping.attrib.get("val") == "clustered"
            assert len(bar_chart.findall(f"{{{CHART}}}ser")) == 3

        regime_charts = _slide_chart_paths(archive, SLIDE_OFFER_REGIME)
        regime_charts = [
            path for path in regime_charts
            if ET.fromstring(archive.read(path)).find(f".//{{{CHART}}}barChart") is not None
        ]
        assert len(regime_charts) == 4
        regime_slide = ET.fromstring(
            archive.read(f"ppt/slides/slide{SLIDE_OFFER_REGIME}.xml")
        )
        assert regime_slide.findall(f".//{{{DML}}}tbl") == []

        current_slides = [
            ET.fromstring(archive.read(f"ppt/slides/slide{slide_number}.xml"))
            for slide_number in SLIDES_TOP15_CURRENT
        ]
        assert all(
            _slide_chart_paths(archive, slide_number) == []
            for slide_number in SLIDES_TOP15_CURRENT
        )
        assert all(
            len(slide.findall(f".//{{{DML}}}tbl")) == 1
            for slide in current_slides
        )
        text = " ".join(
            node.text or ""
            for slide in current_slides
            for node in slide.iter(f"{{{DML}}}t")
        )
        for token in (
            "IBBA esteve em 8 das 15 maiores ofertas do semestre",
            "Liderou 5 delas",
            "As 15 maiores ofertas de 2025 mantêm a base anual de comparação",
            "jan–jun/26 · Top 15",
            "2025 FY · Top 15",
            "IBBA",
            "Originador",
            "Cedente",
            "Sub. mín.",
            "Preço por cota",
            "Sacado",
        ):
            assert token in text

        history_slides = [
            ET.fromstring(archive.read(f"ppt/slides/slide{slide_number}.xml"))
            for slide_number in SLIDES_TOP15_HISTORY
        ]
        assert all(
            len(slide.findall(f".//{{{DML}}}tbl")) == 1
            for slide in history_slides
        )


def test_provider_flow_explorer_is_self_contained_specific_and_office_ready() -> None:
    _require(FLOW_HTML)
    html = FLOW_HTML.read_text(encoding="utf-8")

    assert len(html.encode("utf-8")) < 2_000_000
    assert "fetch(" not in html
    for expected in (
        "Movimentação de prestadores da indústria de FIDCs",
        "Top 25",
        "≥ R$ 250 mi",
        "Copiar para Office",
        "data-export-svg",
        "data-export-png",
        "data-export-csv",
        "26.286.939/0001-58",
        "Sem reporte",
        "Ativa Investimentos",
        "Finvest",
        "BRL Trust",
        "FundosNet",
        "CVM origem",
        "CVM destino",
        "DEZ/24 → JUN/26 · ADMINISTRAÇÃO",
        "DEZ/24 → MAI/26 · GESTÃO · AMOSTRA ICVM 555",
        "DEZ/24 → MAI/26 · CUSTÓDIA · AMOSTRA ICVM 555",
        "CBSF / REAG · DEZ/25 → JUN/26",
        '"fileStem":"fluxos_admin_dez24_jun26"',
        '"fileStem":"fluxos_gestor_dez24_mai26"',
        '"fileStem":"fluxos_custodiante_dez24_mai26"',
        '"fileStem":"fluxos_cbsf_reag_dez25_jun26"',
        "Taxonomia reclassificada por nível",
        "Curadoria comparável dos fundos flagship",
        "Carteira 1 · risco estrutural por CNPJ",
        "Carteira 1 · evolução pela taxonomia reclassificada",
        "taxonomy_levels_compact_v1",
        "flagship_curation_compact_v2",
        "carteira_1_curation_compact_v4",
        "carteira_1_taxonomy_compact_v1",
        "Cloudwalk Bela",
        "N/D",
    ):
        assert expected in html


def test_provider_ranking_slide_has_six_native_charts_and_method_note() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slide = ET.fromstring(
            archive.read(f"ppt/slides/slide{SLIDE_PROVIDER_HISTORY}.xml")
        )
        text = " ".join(node.text or "" for node in slide.iter(f"{{{DML}}}t"))
        chart_paths = _slide_chart_paths(archive, SLIDE_PROVIDER_HISTORY)

    assert len(chart_paths) >= 6
    assert slide.findall(f".//{{{DML}}}tbl") == []
    for expected in (
        "Administração · ranking geral",
        "Gestão · ranking geral",
        "Custódia · ranking geral",
        "Todos os prestadores",
        "Independentes",
        "Exclui Sistema Petrobras e TAPSO",
        "Singulare consolidada em QI Tech",
        "Itaú",
    ):
        assert expected in text


def test_holder_distribution_slide_has_four_charts_and_normalized_histograms() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slide = ET.fromstring(
            archive.read(f"ppt/slides/slide{SLIDE_HOLDER_DISTRIBUTION}.xml")
        )
        chart_frames = slide.findall(f".//{{{PML}}}graphicFrame")
        assert len(chart_frames) >= 4
        chart_frames = sorted(
            chart_frames,
            key=lambda frame: (
                int(frame.find(f"{{{PML}}}xfrm/{{{DML}}}ext").attrib["cx"])
                * int(frame.find(f"{{{PML}}}xfrm/{{{DML}}}ext").attrib["cy"])
            ),
            reverse=True,
        )[:4]

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

        chart_series = []
        for chart_path in _slide_chart_paths(
            archive, SLIDE_HOLDER_DISTRIBUTION
        ):
            chart = ET.fromstring(archive.read(chart_path))
            if chart.find(f".//{{{CHART}}}barChart") is not None:
                chart_series.append(_chart_series_values(chart))

    assert len(chart_series) == 4
    for series in chart_series:
        assert set(series) == {"Dez/23", "Jun/26"}
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
        (7, {"Dez/23", "Jun/26"}),
        (8, {"Dez/23", "Jun/26"}),
        (SLIDE_PROVIDER_RANKING, {"Dez/25", "Jun/26"}),
    ],
)
def test_before_after_slides_have_two_clustered_charts(
    slide_number: int, periods: set[str]
) -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, slide_number)
        chart_series = []
        for chart_path in chart_paths:
            chart = ET.fromstring(archive.read(chart_path))
            if chart.find(f".//{{{CHART}}}barChart") is not None:
                chart_series.append(_chart_series_values(chart))

    assert len(chart_series) == 2
    assert all(set(series) == periods for series in chart_series)
    if slide_number in {5, 10}:
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
        office_xml_parts = [
            archive.read(name)
            for name in archive.namelist()
            if name.endswith(".xml")
            and (
                name.startswith("ppt/slides/")
                or name.startswith("ppt/theme/")
                or "/charts/chart" in name
            )
        ]
        office_xml = b"".join(office_xml_parts)
        assert b"EC7000" in office_xml.upper()
        assert not _contains_blocked_rgb_color(office_xml_parts, "172A3A")
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
        "Inadimplência por recebível",
        "Histórico inad. coorte",
        "Ranking independentes",
        "FIDCs por banco",
        "Detalhe coorte bancos",
        "Taxonomia adquirência",
        "Adquirência reclass.",
        "Curadoria Cartão",
        "Top 20 por Tipo ANBIMA",
        "Auditoria Top 20 Tipo",
        "Curadoria Outros Top 100",
        "Dispersão inadimplência",
        "Ofertas encerradas",
        "Regime de colocação",
        "Histograma ofertas",
        "Crédito Privado Ampliado",
        "Originadores 2026",
        "Top 15 ofertas",
        "Auditoria emissões",
        "Emissões por categoria",
        "Principais conclusões",
        "Atribuição prestadores",
        "Fluxos prestadores",
        "Migração CBSF",
        "Checks revisão",
        "Universo elegível",
        "FICs excluídos",
        "Decisões do ledger",
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
        top15_periods = _column_values(
            archive, sheets["Top 15 ofertas"], "A", 5, 71, shared
        )
        top15_ranks = _column_values(
            archive, sheets["Top 15 ofertas"], "B", 5, 71, shared
        )
        assert top15_periods == (
            ["2022 FY parcial"] * 7
            + ["2023 FY"] * 15
            + ["2024 FY"] * 15
            + ["2025 FY"] * 15
            + ["2026 jan-jun"] * 15
        )
        assert [int(float(value)) for value in top15_ranks] == (
            list(range(1, 8))
            + list(range(1, 16)) * 4
        )
        assert _column_values(
            archive,
            sheets["Emissões por categoria"],
            "A",
            5,
            11,
            shared,
        ) == [
            "Fomento Mercantil",
            "Agro, Indústria e Comércio",
            "Financeiro",
            "Outros",
            "Total (quatro tipos ANBIMA)",
            "FIC-FIDC (fora dos quatro tipos)",
            "Total emitido",
        ]
        for column, header in {
            "K": "IBBA Coord-Líder?",
            "L": "IBBA Coord?",
            "S": "Garantia Firme?",
            "T": "Público",
            "U": "Nº de Inv.",
            "AI": "Agência de rating",
            "AJ": "Rating",
        }.items():
            assert _column_values(
                archive, sheets["Top 15 ofertas"], column, 4, 4, shared
            ) == [header]
        card_ranks = _column_values(
            archive,
            sheets["Curadoria Cartão"],
            "A",
            5,
            48,
            shared,
        )
        assert [int(float(value)) for value in card_ranks] == list(range(1, 45))


def test_legacy_industry_export_no_longer_requests_line_markers() -> None:
    source = (ROOT / "services" / "industry_ppt_export.py").read_text(
        encoding="utf-8"
    )
    assert "LINE_MARKERS" not in source
    assert 'NAVY = "172A3A"' not in source
    assert 'font.name = "Calibri"' not in source


def test_revision_renderer_version_tracks_export_simplification() -> None:
    source = (ROOT / "scripts" / "build_fidc_revision_artifacts.mjs").read_text(
        encoding="utf-8"
    )
    assert 'const RENDERER_VERSION = "industry_revision_artifacts_v43";' in source
    assert "payload.executive_conclusions" in source
    assert "payload.executive_conclusion_notes" in source


def test_native_chart_patcher_preserves_twelve_point_data_label_floor() -> None:
    source = (ROOT / "scripts" / "patch_pptx_native_market_charts.py").read_text(
        encoding="utf-8"
    )
    assert 'default_run.set("sz", "1200")' in source
    assert "def _text_properties(font_size: int = 1200" in source
    assert 'default_run.set("sz", "1000")' not in source
    assert "font_size: int = 850" not in source


def test_taxonomy_top15_preserves_reported_table_when_no_override_exists() -> None:
    _require(PAYLOAD)
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    rows = payload["taxonomy_top15"]
    by_rank_and_view = {
        (int(row["rank"]), str(row["visao"])): str(row["taxonomia_atual"])
        for row in rows
    }
    for rank in range(1, 16):
        reported = by_rank_and_view[(rank, "Tabela II reportada")]
        reclassified = by_rank_and_view[(rank, "Tabela II reclassificada")]
        assert reported.lower() != "nan"
        assert reclassified.lower() != "nan"
        if reported != "N/D":
            assert reclassified != "N/D"


def test_provider_transition_slide_has_no_stale_editorial_fallback() -> None:
    source = (ROOT / "scripts" / "build_fidc_revision_artifacts.mjs").read_text(
        encoding="utf-8"
    )
    assert "provider_transition_summary ausente ou incompleto" in source
    assert "continuing_funds: 2477" not in source
    assert "changed_funds: 257" not in source
    assert "summary.changed_funds || 257" not in source


def test_materialized_conclusions_reconcile_their_declared_universes() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    metrics = payload["conclusion_metrics"]

    assert metrics["holder_ge_200m_fundos"] == 784
    assert metrics["holder_ge_200m_share_fundos_ate_10_contas"] == pytest.approx(
        0.5841836735
    )
    assert metrics["service_model_universe_funds"] == 3474
    assert metrics["service_model_universe_pl_brl"] == pytest.approx(
        821_361_559_284.45
    )
    assert metrics["admin_custodia_juntas_fundos"] == 3076
    assert metrics["admin_custodia_juntas_share_pl"] == pytest.approx(0.9072333490)
    assert metrics["monoestrutura_fundos"] == 304
    assert metrics["monoestrutura_share_pl"] == pytest.approx(0.4037434723)
    assert metrics["btg_combo_tres_funcoes_fundos"] == 67
    assert metrics["btg_combo_tres_funcoes_pl_brl"] == pytest.approx(
        77_692_063_823.57
    )
    assert metrics["btg_bank_cohort_listed_roots"] == 32
    assert metrics["btg_bank_cohort_observed_funds"] == 30
    assert metrics["btg_bank_cohort_pl_brl"] == pytest.approx(
        52_201_104_080.03
    )
    assert metrics["btg_bank_cohort_combo_funds"] == 22
    assert metrics["btg_bank_cohort_combo_pl_brl"] == pytest.approx(
        51_277_027_287.65
    )
    assert metrics["btg_bank_cohort_combo_share_pl"] == pytest.approx(
        0.9822977539
    )
    assert metrics["admin_transition_2024_2025_continuing_funds"] == 2323
    assert metrics["admin_transition_2024_2025_changed_funds"] == 243
    assert metrics["admin_transition_2024_2025_changed_pl_brl"] == pytest.approx(
        32_410_254_665.61
    )
    assert metrics["admin_transition_2024_2025_changed_share_pl"] == pytest.approx(
        0.07591989563
    )
    assert metrics["admin_transition_2024_2025_cielo_funds"] == 2
    assert metrics["admin_transition_2024_2025_cielo_pl_brl"] == pytest.approx(
        8_922_506_388.74
    )

    offer_concentration = payload["offer_ticket_concentration_2026"]
    assert offer_concentration["threshold_registered_volume_brl"] == pytest.approx(
        500_000_000
    )
    assert offer_concentration["large_offer_closed_offers"] == 22
    assert offer_concentration["universe_closed_offers"] == 771
    assert offer_concentration["large_offer_share"] == pytest.approx(0.02853437095)
    assert offer_concentration["large_offer_registered_volume_share"] == pytest.approx(
        0.4222944319
    )

    conclusions = payload["executive_conclusions"]
    assert [row["order"] for row in conclusions] == list(range(1, 8))
    assert all(len(row["bullets"]) == 2 for row in conclusions)
    conclusion_text = " ".join(
        [row["title"] for row in conclusions]
        + [bullet for row in conclusions for bullet in row["bullets"]]
    )
    assert "RCVM 175" in conclusion_text
    assert "42,2%" in conclusion_text
    assert "empate técnico" in conclusion_text and "BTG" in conclusion_text
    assert "QI Tech lidera administração e custódia" not in conclusion_text
    assert len(payload["executive_conclusion_notes"]) >= 5

    current_btg = [
        row
        for row in payload["bank_fidc_detail"]
        if row["competencia"] == "2026-06"
        and row["grupo_bancario"] == "BTG Pactual"
    ]
    observed_btg = [
        row for row in current_btg if row["observado"] and row["pl_brl"] > 0
    ]
    assert len({row["cnpj_root8"] for row in current_btg}) == 32
    assert len({row["cnpj_fundo"] for row in observed_btg}) == 30
    assert sum(row["pl_brl"] for row in observed_btg) == pytest.approx(
        metrics["btg_bank_cohort_pl_brl"]
    )

    management_scenario = next(
        row
        for row in payload["btg_provider_ex_controlled_scenario"]
        if row["papel"] == "gestor"
    )
    assert management_scenario["fidcs_coorte_bancaria_excluidos"] == 22
    assert management_scenario["pl_coorte_bancaria_excluido_brl"] == pytest.approx(
        metrics["btg_bank_cohort_combo_pl_brl"]
    )
    assert management_scenario["btg_rank"] == 1
    assert management_scenario["btg_rank_ex_controlados"] == 3


def test_materialized_ex_fic_pl_annual_growth_matches_the_chart_totals() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    periods = {
        (int(row["start_year"]), int(row["end_year"])): row
        for row in payload["pl_total_cagr_periods"]
    }

    assert set(periods) == {
        (2015, 2018),
        (2019, 2020),
        (2021, 2022),
        (2022, 2023),
        (2023, 2024),
        (2024, 2025),
        (2025, 2026),
    }
    assert periods[(2015, 2018)]["annual_intervals"] == 3
    assert periods[(2015, 2018)]["cagr"] == pytest.approx(0.1672417821)
    assert periods[(2019, 2020)]["cagr"] == pytest.approx(-0.0900760950)
    assert periods[(2021, 2022)]["cagr"] == pytest.approx(0.2211881031)
    assert periods[(2022, 2023)]["cagr"] == pytest.approx(0.2513602654)
    assert periods[(2023, 2024)]["cagr"] == pytest.approx(0.4401995990)
    assert periods[(2024, 2025)]["cagr"] == pytest.approx(0.1852101948)
    assert periods[(2025, 2026)]["cagr"] == pytest.approx(0.0637904277)

    bcb_periods = {
        (int(row["start_year"]), int(row["end_year"])): row
        for row in payload["bcb_total_growth_periods"]
    }
    assert set(bcb_periods) == set(periods)
    assert bcb_periods[(2015, 2018)]["cagr"] == pytest.approx(0.0155136903)
    assert bcb_periods[(2019, 2020)]["cagr"] == pytest.approx(0.1604784933)
    assert bcb_periods[(2025, 2026)]["cagr"] == pytest.approx(0.0308222993)


def test_materialized_payload_uses_complete_june_stock() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))

    assert payload["latest_complete"] == "2026-06"
    assert payload["stock_preliminary_status"] == {}
    assert payload["qa_latest"]["veiculos_total"] == 4252
    assert payload["qa_latest"]["fundos_total"] == 4247


def test_materialized_card_taxonomy_audit_reconciles_its_summary() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    rows = payload["card_taxonomy_audit"]
    summary = payload["card_taxonomy_summary"]
    acquiring_detail = payload["acquiring_curation_detail"]

    principal = [
        row
        for row in rows
        if row["criterio_inclusao"].startswith("Cartão de crédito")
    ]
    secondary = [
        row
        for row in rows
        if row["criterio_inclusao"].startswith("Exposição")
    ]
    observable = [row for row in rows if row["pl_jun25_observavel"]]
    current_observable = [
        row for row in rows if row["pl_referencia_competencia"] == "2026-06"
    ]
    included = [row for row in rows if row["status_curadoria"] == "Incluído em Adquirência"]
    outside = [row for row in rows if row["status_curadoria"] == "Fora de Adquirência"]
    pending = [row for row in rows if row["status_curadoria"] == "Pendente"]

    assert summary["competencia_tabela_ii"] == "2026-06"
    assert summary["competencia_pl"] == "2025-06"
    assert len(rows) == summary["fundos_total"] == 44
    assert len(acquiring_detail) == 33
    assert [row["ordem_materialidade"] for row in acquiring_detail] == list(
        range(1, 34)
    )
    assert len(principal) == summary["fundos_cartao_segmento_principal"] == 43
    assert len(secondary) == summary["fundos_exposicao_secundaria"] == 1
    assert summary["fundos_anbima_cartao_explicito"] == 0
    assert sum(row["ja_curado_como_adquirencia"] for row in rows) == 26
    assert summary["fundos_curados_adquirencia"] == 26
    assert all(row["cnpj_fundo_identificado"] for row in rows)
    assert len({row["cnpj_fundo_formatado"] for row in rows}) == 44
    assert len(observable) == summary["fundos_pl_observavel"] == 37
    assert sum(row["pl_jun25_brl"] for row in observable) == pytest.approx(
        summary["pl_jun25_observado_brl"]
    )
    assert summary["pl_jun25_observado_brl"] == pytest.approx(
        76_063_154_829.65
    )
    assert len(current_observable) == summary["fundos_pl_atual_observavel"] == 44
    assert summary["fundos_pl_fallback_usado"] == 0
    assert len(included) == summary["fundos_incluidos_adquirencia"] == 26
    assert len(outside) == summary["fundos_fora_adquirencia"] == 17
    assert len(pending) == summary["fundos_pendentes_curadoria"] == 1
    assert summary["pl_referencia_observado_brl"] == pytest.approx(
        97_480_792_502.62
    )
    assert summary["pl_incluido_adquirencia_brl"] == pytest.approx(
        86_447_199_744.79
    )
    assert summary["pl_fora_adquirencia_brl"] == pytest.approx(
        11_006_443_530.36
    )
    assert summary["pl_pendente_curadoria_brl"] == pytest.approx(
        27_149_227.47
    )
    assert sum(row["valor_cartao_tabela_ii_brl"] for row in rows) == pytest.approx(
        summary["valor_cartao_tabela_ii_jun26_brl"]
    )
    assert summary["valor_cartao_tabela_ii_jun26_brl"] == pytest.approx(
        78_589_843_711.39
    )


def test_materialized_delinquency_cohort_revision_reconciles_all_blocks() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    summary = payload["delinquency_cohort_revision_summary"]
    transitions = payload["delinquency_cohort_revision_transitions"]
    sensitivity = payload["delinquency_cohort_revision_sensitivity"]

    assert summary["competencia_anterior"] == "2026-05"
    assert summary["competencia_atual"] == "2026-06"
    assert summary["fundos_coorte_anterior"] == 2050
    assert summary["fundos_coorte_atual"] == 2066
    assert summary["fundos_mesmo_subtipo"] == 1856
    assert summary["fundos_reclassificados"] == 86
    assert summary["fundos_entraram"] == 124
    assert summary["fundos_sairam"] == 108
    assert summary["pl_coorte_anterior_brl"] == pytest.approx(
        603_516_406_097.59
    )
    assert summary["pl_coorte_atual_brl"] == pytest.approx(
        608_713_543_906.14
    )
    assert sum(row["fundos"] for row in transitions) == 86
    assert sum(row["pl_atual_brl"] for row in transitions) == pytest.approx(
        summary["pl_atual_reclassificado_brl"]
    )

    services_to_financial = next(
        row
        for row in transitions
        if row["subtipo_anterior"] == "Serviços"
        and row["subtipo_atual"] == "Financeiro"
    )
    assert services_to_financial["fundos"] == 16
    assert services_to_financial["pl_atual_brl"] == pytest.approx(
        17_393_401_256.48
    )
    assert services_to_financial["maior_fundo_pl_brl"] == pytest.approx(
        8_032_044_361.07
    )
    assert "BTG PACTUAL CONSIGNADOS II" in services_to_financial["principais_fundos"]

    assert sensitivity
    assert {
        row["competencia_coorte_anterior"] for row in sensitivity
    } == {"2026-05"}
    assert {
        row["competencia_coorte_atual"] for row in sensitivity
    } == {"2026-06"}
    assert {row["tipo_recebivel_tabela_ii"] for row in sensitivity} == {
        "Agronegócio",
        "Ações judiciais",
        "Cartão de crédito",
        "Comercial",
        "Factoring",
        "Financeiro",
        "Imobiliário",
        "Industrial",
        "Serviços",
        "Setor público",
    }
    december_financial = next(
        row
        for row in sensitivity
        if row["competencia"] == "2025-12"
        and row["tipo_recebivel_tabela_ii"] == "Financeiro"
    )
    assert december_financial[
        "inadimplencia_sobre_carteira_coorte_anterior"
    ] == pytest.approx(0.0473844554)
    assert december_financial[
        "inadimplencia_sobre_carteira_coorte_atual"
    ] == pytest.approx(0.0468319400)
    assert december_financial["delta_inadimplencia_pp"] == pytest.approx(
        -0.0005525154
    )


def test_materialized_acquiring_mix_includes_the_documented_card_curations() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    current = next(
        row
        for row in payload["acquiring_reclassified_mix"]
        if row["competencia"] == "2026-06"
        and row["categoria_analitica"] == "Adquirência"
    )

    assert current["fundos_adquirencia_curados"] == 33
    assert current["fundos_adquirencia_observados"] == 31
    assert current["fundos_movidos_para_adquirencia"] == 31
    assert current["pl_brl"] == pytest.approx(99_246_541_247.99)
    assert current["share_pl"] == pytest.approx(0.1208317338)
    assert current["denominador_pl_brl"] == pytest.approx(821_361_559_284.45)
    assert current["rank_reclassificado"] == 3
    moved = set(current["cnpjs_movidos_para_adquirencia"].split(";"))
    assert {"50473039000102", "55471753000177", "63572282000111"}.issubset(moved)
    current_rows = {
        row["categoria_analitica"]: row
        for row in payload["acquiring_reclassified_mix"]
        if row["competencia"] == "2026-06"
    }
    assert current_rows["Cartão"]["fundos_movidos_da_categoria"] == 26
    assert current_rows["Comercial"]["fundos_movidos_da_categoria"] == 2
    assert current_rows["Serviços"]["fundos_movidos_da_categoria"] == 2
    assert current_rows["Financeiro"]["fundos_movidos_da_categoria"] == 1
