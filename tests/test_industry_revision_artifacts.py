from __future__ import annotations

from services.industry_comparative_period import ComparisonCut

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
    EXPECTED_SLIDE_IDS,
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
SLIDE_OFFERS_VOLUME = _contract_slide_number("volume e ticket")
SLIDE_OFFER_TICKETS = _contract_slide_number("concentracao das ofertas")
SLIDE_OFFER_REGIME = _contract_slide_number("garantia firme")
SLIDES_TOP15_CURRENT = _sequence_slide_numbers(CURRENT_TOP15_SLIDE_SEQUENCE)
SLIDES_TOP15_HISTORY = _sequence_slide_numbers(HISTORICAL_TOP15_SLIDE_SEQUENCE)
SLIDE_CONCLUSIONS = _contract_slide_number("principais conclusoes")
SLIDE_PROVIDER_HISTORY = _contract_slide_number("ranking de prestadores")
SLIDE_PROVIDER_RANKING = _contract_slide_number("prestadores", "ranking e concentracao")
SLIDE_INVESTOR_BASE = _contract_slide_number("publico-alvo e base investidora")
SLIDE_HOLDER_DISTRIBUTION = _contract_slide_number("distribuicao por numero")


def _latest_label(payload: dict[str, object]) -> str:
    months = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")
    value = str(payload["latest_complete"])
    return f"{months[int(value[-2:]) - 1]}/{value[2:4]}"


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


def test_cedente_sheets_replace_stale_rows_and_preserve_cnae_as_text() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    specs = (
        ("Cedentes · Top 500", "cedente_top500_detail", "S"),
        ("Cedentes · competência", "cedente_registry_by_competence", "M"),
        ("Cedentes · cadastro", "cedente_registry_master", "H"),
    )

    with ZipFile(XLSX) as archive:
        sheets = _workbook_sheets(archive)
        shared = _shared_strings(archive)
        for sheet_name, payload_key, column in specs:
            expected_rows = len(payload[payload_key])
            root = ET.fromstring(archive.read(sheets[sheet_name]))
            values_by_row = {
                int(re.search(r"\d+", cell.attrib["r"]).group()): _cell_value(
                    cell, shared
                )
                for cell in root.findall(f".//{{{SHEET}}}c")
                if cell.attrib.get("r", "").startswith(column)
            }
            assert all(
                not value
                for row, value in values_by_row.items()
                if row > expected_rows + 4
            ), sheet_name
            cnae_codes = [
                value
                for row, value in values_by_row.items()
                if 5 <= row <= expected_rows + 4 and value not in {"", "N/D"}
            ]
            assert cnae_codes
            assert all(len(code) == 7 and code.isdigit() for code in cnae_codes)
            assert any(code.startswith("0") for code in cnae_codes)


def test_deck_order_and_compact_appendix_contract() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slides = _slide_texts(archive)

    assert len(slides) == EXPECTED_SLIDES == len(EXPECTED_SLIDE_SEQUENCE)
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    assert "Indústria de FIDCs" in slides[0]
    assert f"Dados de referência: {_latest_label(payload).lower()}" in slides[0]
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
    assert "Ranking de prestadores" in slides[
        SLIDE_PROVIDER_HISTORY - 1
    ]
    assert "PRESTADORES · RANKING E CONCENTRAÇÃO" in slides[
        SLIDE_PROVIDER_RANKING - 1
    ]
    assert all("PRESTADORES · EVIDÊNCIAS DE MIGRAÇÃO" not in text for text in slides)
    assert "Público-alvo e base investidora" in slides[
        SLIDE_INVESTOR_BASE - 1
    ]
    assert "DISTRIBUIÇÃO POR NÚMERO DE COTISTAS" in slides[
        SLIDE_HOLDER_DISTRIBUTION - 1
    ].upper()
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


def test_updated_conclusions_are_materialized_without_legacy_numeric_copy() -> None:
    _require(PPTX)
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    with ZipFile(PPTX) as archive:
        slides = _slide_texts(archive)
    conclusion_text = slides[SLIDE_CONCLUSIONS - 1]
    for row in payload["executive_conclusions"]:
        assert row["title"] in conclusion_text
        assert all(bullet in conclusion_text for bullet in row["bullets"])
    assert "PL ex-FIC ≥ R$ 200 mi" in slides[SLIDE_HOLDER_DISTRIBUTION - 1]
    assert "Evolução dos recebíveis" in slides[6]
    assert "Volume e ticket das ofertas" in slides[SLIDE_OFFERS_VOLUME - 1]
    assert ComparisonCut.from_competence(payload["offers_as_of"][:7]).period_label() in slides[SLIDE_OFFERS_VOLUME - 1]
    for text in slides:
        assert len(text.strip()) > 80
        assert "PRESTADORES · EVIDÊNCIAS DE MIGRAÇÃO" not in text
        assert "APÊNDICE · CASO ATLÂNTICO" not in text
        assert 'Abrir "Outros" revela que 63%' not in text
        assert "Financeiro explicou 70%" not in text
        assert "Adquirência é R$ 99 bi" not in text


def test_structural_detail_is_preserved_in_workbook_and_payload() -> None:
    _require(XLSX)
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    assert EXPECTED_SLIDES == len(EXPECTED_SLIDE_IDS) == 15
    assert STRUCTURAL_MVP_SLIDE_SEQUENCE == ()
    assert STRUCTURAL_MVP_SLIDES == ()
    assert payload["carteira_1_structural_taxonomy"]
    assert payload["carteira_1_structural_summary"]
    with ZipFile(XLSX) as archive:
        assert {"Risco estrutural ativos", "Risco estrutural taxonomia"}.issubset(_workbook_sheets(archive))


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
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    latest = next(row for row in payload["pl_history"] if row["competencia"] == payload["latest_complete"])
    assert _latest_label(payload).lower() in text
    left_series = _chart_series_values(charts[0])["FIDCs ex-FIC"]
    assert left_series[-1] == pytest.approx(round(latest["pl_ex_fic"] / 1e9))
    assert "SALDO FIC" not in text.upper()
    assert "Carteira de crédito privada ampliada · R$ bi" in text
    assert "excluídos títulos públicos" in text
    assert "demais securitizações (CRIs e CRAs)" in text
    assert "PL direto e carteira privada têm perímetros contábeis distintos" in text

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
        chart_paths = _slide_chart_paths(archive, 5)
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
        for label in ("dez/23", "dez/24", "dez/25", _latest_label(json.loads(PAYLOAD.read_text(encoding="utf-8"))).lower()):
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
        assert len(regime_charts) == 1
        regime_slide = ET.fromstring(
            archive.read(f"ppt/slides/slide{SLIDE_OFFER_REGIME}.xml")
        )
        assert regime_slide.findall(f".//{{{DML}}}tbl") == []
        regime_text = " ".join(
            node.text or "" for node in regime_slide.iter(f"{{{DML}}}t")
        )
        assert "Número de ofertas" not in regime_text
        assert "Volume registrado · R$ bi" not in regime_text

        assert SLIDES_TOP15_CURRENT == ()
        assert SLIDES_TOP15_HISTORY == ()
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    assert len([row for row in payload["closed_offer_top15"] if row["period_label"] == ComparisonCut.from_competence(payload["offers_as_of"][:7]).period_id()]) == 15
    cut = ComparisonCut.from_competence(payload["offers_as_of"][:7])
    assert len([row for row in payload["closed_offer_top15"] if row["period_label"] in {f"{year} FY" for year in range(cut.year - 3, cut.year)}]) == 45
    with ZipFile(XLSX) as archive:
        assert "Top 15 ofertas" in _workbook_sheets(archive)


def test_provider_flow_explorer_is_self_contained_specific_and_office_ready() -> None:
    _require(FLOW_HTML)
    html = FLOW_HTML.read_text(encoding="utf-8")

    assert len(html.encode("utf-8")) < 2_000_000
    assert "fetch(" not in html
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    latest_upper = _latest_label(payload).upper()
    latest_stem = _latest_label(payload).lower().replace("/", "")
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
        "FundosNet",
        "CVM origem",
        "CVM destino",
        f"DEZ/24 → {latest_upper} · ADMINISTRAÇÃO",
        f"DEZ/24 → {latest_upper} · GESTÃO · AMOSTRA ICVM 555",
        f"DEZ/24 → {latest_upper} · CUSTÓDIA · AMOSTRA ICVM 555",
        f"CBSF / REAG · DEZ/25 → {latest_upper}",
        f'"fileStem":"fluxos_admin_dez24_{latest_stem}"',
        f'"fileStem":"fluxos_gestor_dez24_{latest_stem}"',
        f'"fileStem":"fluxos_custodiante_dez24_{latest_stem}"',
        f'"fileStem":"fluxos_cbsf_reag_dez25_{latest_stem}"',
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
    embedded = re.search(r'<script type="application/json" id="provider-flow-data">(.*?)</script>', html, re.DOTALL)
    assert embedded is not None
    compact = json.loads(embedded.group(1))
    admin_links = compact["views"]["admin"]["links"]
    source_links = payload["provider_transition_links"]
    assert len(admin_links) == len(source_links)
    fields = compact["fields"]["marketLink"]
    for compact_row, source_row in zip(admin_links, source_links):
        observed = dict(zip(fields, compact_row))
        assert observed["funds"] == source_row["fundos"]
        assert observed["value"] == source_row["pl_comparavel_brl"]


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
        "Exclui Petrobras/TAPSO",
        "Gestão/custódia reconstruídas; método no XLSX",
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
        assert set(series) == {"Dez/23", _latest_label(json.loads(PAYLOAD.read_text(encoding="utf-8")))}
        assert all(len(values) == 6 for values in series.values())
    normalized = [
        series
        for series in chart_series
        if all(sum(values) == pytest.approx(1.0, abs=1e-9) for values in series.values())
    ]
    assert len(normalized) == 2


@pytest.mark.parametrize(
    ("slide_number", "before_label"),
    [(6, "Dez/23"), (7, "Dez/23"), (SLIDE_PROVIDER_RANKING, "Dez/25")],
)
def test_before_after_slides_have_two_clustered_charts(
    slide_number: int, before_label: str
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
    periods = {before_label, _latest_label(json.loads(PAYLOAD.read_text(encoding="utf-8")))}
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
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
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
            archive, sheets["Top 15 ofertas"], "A", 5, len(payload["closed_offer_top15"]) + 4, shared
        )
        top15_ranks = _column_values(
            archive, sheets["Top 15 ofertas"], "B", 5, len(payload["closed_offer_top15"]) + 4, shared
        )
        cut = ComparisonCut.from_competence(payload["offers_as_of"][:7])
        ranking_periods = [("2022 FY parcial" if year == 2022 else f"{year} FY", 7 if year == 2022 else 15) for year in range(cut.year - 4, cut.year)] + [(cut.period_id(), 15)]
        assert top15_periods == [period for period, count in ranking_periods for _ in range(count)]
        assert [int(float(value)) for value in top15_ranks] == [rank for _, count in ranking_periods for rank in range(1, count + 1)]
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
            4 + len(json.loads(PAYLOAD.read_text(encoding="utf-8"))["card_taxonomy_audit"]),
            shared,
        )
        assert [int(float(value)) for value in card_ranks] == list(range(1, 1 + len(json.loads(PAYLOAD.read_text(encoding="utf-8"))["card_taxonomy_audit"])))


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
    assert 'const RENDERER_VERSION = "industry_revision_artifacts_v50";' in source
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
    assert source.count("_set_arial_12(root)") >= 3


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
    latest = payload["latest_complete"]
    metrics = payload["conclusion_metrics"]
    assert metrics["competencia"] == latest
    service = {row["modelo_prestacao"]: row for row in payload["service_model"]}
    service_pl = sum(row["pl"] for row in service.values())
    assert metrics["service_model_universe_funds"] == sum(row["fundos"] for row in service.values())
    assert metrics["service_model_universe_pl_brl"] == pytest.approx(service_pl, abs=0.01)
    together = [service[name] for name in ("Monoestrutura", "Administração + Custódia")]
    assert metrics["admin_custodia_juntas_fundos"] == sum(row["fundos"] for row in together)
    assert metrics["admin_custodia_juntas_share_pl"] == pytest.approx(sum(row["pl"] for row in together) / service_pl)
    assert metrics["monoestrutura_fundos"] == service["Monoestrutura"]["fundos"]
    assert metrics["monoestrutura_share_pl"] == pytest.approx(service["Monoestrutura"]["pl"] / service_pl)
    holders = [row for row in payload["holder_distribution_history"] if row["competencia"] == latest]
    holder_count = sum(row["fundos"] for row in holders)
    assert metrics["holder_ge_200m_fundos"] == holder_count
    assert metrics["holder_ge_200m_share_fundos_ate_10_contas"] == pytest.approx(
        sum(row["fundos"] for row in holders if row["bucket"] in {"0", "1", "2–3", "4–10"}) / holder_count)
    current_btg = [row for row in payload["bank_fidc_detail"] if row["competencia"] == latest and row["grupo_bancario"] == "BTG Pactual"]
    observed_btg = [row for row in current_btg if row["observado"] and row["pl_brl"] > 0]
    assert len({row["cnpj_root8"] for row in current_btg}) == metrics["btg_bank_cohort_listed_roots"]
    assert len({row["cnpj_fundo"] for row in observed_btg}) == metrics["btg_bank_cohort_observed_funds"]
    assert sum(row["pl_brl"] for row in observed_btg) == pytest.approx(metrics["btg_bank_cohort_pl_brl"], abs=0.01)
    assert metrics["btg_bank_cohort_combo_share_pl"] == pytest.approx(metrics["btg_bank_cohort_combo_pl_brl"] / metrics["btg_bank_cohort_pl_brl"])
    assert metrics["admin_transition_2024_2025_changed_share_pl"] == pytest.approx(metrics["admin_transition_2024_2025_changed_pl_brl"] / metrics["admin_transition_2024_2025_comparable_pl_brl"])
    offer_concentration = payload["offer_ticket_concentration_2026"]
    assert offer_concentration["threshold_registered_volume_brl"] == 500_000_000
    assert offer_concentration["large_offer_share"] == pytest.approx(offer_concentration["large_offer_closed_offers"] / offer_concentration["universe_closed_offers"])
    assert 0 < offer_concentration["large_offer_registered_volume_share"] < 1
    conclusions = payload["executive_conclusions"]
    assert [row["order"] for row in conclusions] == list(range(1, 6))
    assert all(1 <= len(row["bullets"]) <= 2 for row in conclusions)
    assert all(row["title"] and all(row["bullets"]) for row in conclusions)
    assert len(payload["executive_conclusion_notes"]) >= 5
    management_scenario = next(row for row in payload["btg_provider_ex_controlled_scenario"] if row["papel"] == "gestor")
    assert management_scenario["fidcs_coorte_bancaria_excluidos"] == metrics["btg_bank_cohort_combo_funds"]
    assert management_scenario["pl_coorte_bancaria_excluido_brl"] == pytest.approx(metrics["btg_bank_cohort_combo_pl_brl"])


def test_materialized_ex_fic_pl_annual_growth_matches_the_chart_totals() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    histories = [
        (payload["pl_total_cagr_periods"], {row["competencia"]: row["pl_ex_fic"] for row in payload["pl_history"]}, "start_pl_total_brl", "end_pl_total_brl"),
        (payload["bcb_total_growth_periods"], {row["competencia"]: row["private_expanded_credit_total_brl"] for row in payload["bcb_expanded_credit"]}, "start_total_brl", "end_total_brl"),
    ]
    for periods, history, start_field, end_field in histories:
        assert len(periods) == 7
        assert periods[-1]["end_competencia"] == payload["latest_complete"]
        for period in periods:
            start = history[period["start_competencia"]]
            end = history[period["end_competencia"]]
            assert period[start_field] == pytest.approx(start, abs=0.01)
            assert period[end_field] == pytest.approx(end, abs=0.01)
            intervals = period["end_year"] - period["start_year"]
            assert period["annual_intervals"] == intervals > 0
            expected = (end / start) ** (1 / intervals) - 1 if period["growth_kind"] == "cagr" else end / start - 1
            assert period["cagr"] == pytest.approx(expected)


def test_materialized_payload_uses_latest_complete_stock() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    data_dir = Path(os.environ.get("FIDC_TEST_DATA_DIR", ROOT / "data" / "industry_study"))
    status = __import__("pandas").read_csv(data_dir / "industry_competence_status.csv", dtype={"competencia": str})
    complete = status[status["publication_status"].eq("completa")]
    latest = str(complete["competencia"].max())
    assert payload["latest_complete"] == latest
    current = status[status["competencia"].eq(latest)].iloc[0]
    assert payload["qa_latest"]["competencia"] == latest
    assert payload["qa_latest"]["veiculos_total"] == int(current["n_veiculos"])
    assert 0 < payload["qa_latest"]["fundos_total"] <= payload["qa_latest"]["veiculos_total"]
    preliminary = status[status["competencia"].gt(latest) & ~status["publication_status"].eq("completa")]
    if preliminary.empty:
        assert payload["stock_preliminary_status"] == {}
    else:
        assert payload["stock_preliminary_status"]["competencia"] == str(preliminary["competencia"].max())
        assert payload["stock_preliminary_status"]["publication_status"] != "completa"


def test_provider_history_reaches_end_of_latest_complete_stock() -> None:
    import calendar
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    manifest_path = PAYLOAD.parent / "prestadores_historico_cvm_manifest.json"
    assert manifest_path.is_file(), "histórico de prestadores sem manifesto do corte atualizado"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    year, month = map(int, payload["latest_complete"].split("-"))
    expected_date = f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
    assert manifest["checks"]["to_date"] == expected_date
    assert len(manifest["source"]["archive_sha256"]) == 64


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
    observable = [row for row in rows if row["pl_comparavel_anterior_observavel"]]
    current_observable = [
        row for row in rows if row["pl_referencia_competencia"] == payload["latest_complete"]
    ]
    included = [row for row in rows if row["status_curadoria"] == "Incluído em Adquirência"]
    outside = [row for row in rows if row["status_curadoria"] == "Fora de Adquirência"]
    pending = [row for row in rows if row["status_curadoria"] == "Pendente"]

    assert summary["competencia_tabela_ii"] == payload["latest_complete"]
    cut = ComparisonCut.from_competence(payload["latest_complete"])
    assert summary["competencia_pl"] == f"{cut.year - 1}-{cut.month:02d}"
    assert len(rows) == summary["fundos_total"]
    assert len(acquiring_detail) == 33
    assert [row["ordem_materialidade"] for row in acquiring_detail] == list(
        range(1, 34)
    )
    assert len(principal) == summary["fundos_cartao_segmento_principal"]
    assert len(secondary) == summary["fundos_exposicao_secundaria"]
    assert summary["fundos_anbima_cartao_explicito"] == sum(
        bool(row["anbima_cartao_explicito"]) for row in rows
    )
    assert sum(row["ja_curado_como_adquirencia"] for row in rows) == summary[
        "fundos_curados_adquirencia"
    ]
    assert all(row["cnpj_fundo_identificado"] for row in rows)
    assert len({row["cnpj_fundo_formatado"] for row in rows}) == len(rows)
    assert len(observable) == summary["fundos_pl_observavel"]
    assert sum(row["pl_comparavel_anterior_brl"] for row in observable) == pytest.approx(
        summary["pl_comparavel_anterior_observado_brl"]
    )
    assert len(current_observable) == summary["fundos_pl_atual_observavel"]
    assert summary["fundos_pl_fallback_usado"] == 0
    assert len(included) == summary["fundos_incluidos_adquirencia"]
    assert len(outside) == summary["fundos_fora_adquirencia"]
    assert len(pending) == summary["fundos_pendentes_curadoria"]
    assert summary["pl_referencia_observado_brl"] == pytest.approx(
        sum(row["pl_referencia_brl"] for row in rows)
    )
    assert summary["pl_incluido_adquirencia_brl"] == pytest.approx(
        sum(row["pl_referencia_brl"] for row in included)
    )
    assert summary["pl_fora_adquirencia_brl"] == pytest.approx(
        sum(row["pl_referencia_brl"] for row in outside)
    )
    assert summary["pl_pendente_curadoria_brl"] == pytest.approx(
        sum(row["pl_referencia_brl"] for row in pending)
    )
    assert sum(row["valor_cartao_tabela_ii_brl"] for row in rows) == pytest.approx(
        summary["valor_cartao_tabela_ii_atual_brl"]
    )


def test_materialized_delinquency_cohort_revision_reconciles_all_blocks() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    summary = payload["delinquency_cohort_revision_summary"]
    transitions = payload["delinquency_cohort_revision_transitions"]
    sensitivity = payload["delinquency_cohort_revision_sensitivity"]
    assert summary["competencia_anterior"] < summary["competencia_atual"] <= payload["latest_complete"]
    assert summary["fundos_coorte_atual"] == summary["fundos_mesmo_subtipo"] + summary["fundos_reclassificados"] + summary["fundos_entraram"]
    assert summary["fundos_coorte_anterior"] == summary["fundos_mesmo_subtipo"] + summary["fundos_reclassificados"] + summary["fundos_sairam"]
    assert sum(row["fundos"] for row in transitions) == summary["fundos_reclassificados"]
    assert sum(row["pl_atual_brl"] for row in transitions) == pytest.approx(summary["pl_atual_reclassificado_brl"], abs=0.01)
    assert summary["pl_coorte_atual_brl"] == pytest.approx(summary["pl_atual_mesmo_subtipo_brl"] + summary["pl_atual_reclassificado_brl"] + summary["pl_atual_entradas_brl"], abs=0.01)
    assert sensitivity
    assert {row["competencia_coorte_anterior"] for row in sensitivity} == {summary["competencia_anterior"]}
    assert {row["competencia_coorte_atual"] for row in sensitivity} == {summary["competencia_atual"]}
    for row in sensitivity:
        before = row["inadimplencia_sobre_carteira_coorte_anterior"]
        after = row["inadimplencia_sobre_carteira_coorte_atual"]
        if before is not None and after is not None:
            assert row["delta_inadimplencia_pp"] == pytest.approx(after - before)


def test_materialized_acquiring_mix_includes_the_documented_card_curations() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    current_rows = {row["categoria_analitica"]: row for row in payload["acquiring_reclassified_mix"] if row["competencia"] == payload["latest_complete"]}
    current = current_rows["Adquirência"]
    curated = payload["acquiring_curation_detail"]
    assert current["fundos_adquirencia_curados"] == len(curated)
    assert current["fundos_adquirencia_observados"] <= len(curated)
    assert current["pl_brl"] == pytest.approx(sum(row["pl_referencia_brl"] or 0 for row in curated), abs=0.01)
    assert current["share_pl"] == pytest.approx(current["pl_brl"] / current["denominador_pl_brl"])
    latest_history = next(row for row in payload["pl_history"] if row["competencia"] == payload["latest_complete"])
    assert current["denominador_pl_brl"] == pytest.approx(latest_history["pl_ex_fic"], abs=0.01)
    moved = set(current["cnpjs_movidos_para_adquirencia"].split(";"))
    assert {"50473039000102", "55471753000177", "63572282000111"}.issubset(moved)
    assert sum(row["fundos_movidos_da_categoria"] for name, row in current_rows.items() if name != "Adquirência") == current["fundos_movidos_para_adquirencia"]
