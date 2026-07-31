from __future__ import annotations

import json
import os
import posixpath
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from services.industry_revision_export import _contains_blocked_rgb_color


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
XLSX = (
    ROOT
    / "data"
    / "industry_study"
    / "generated_revision"
    / "industry_data_revised.xlsx"
)
FLOW_HTML = (
    ROOT
    / "data"
    / "industry_study"
    / "generated_revision"
    / "provider_flows_explorer.html"
)
PAYLOAD = (
    ROOT
    / "data"
    / "industry_study"
    / "generated_revision"
    / "artifact_payload.json"
)

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

    assert len(slides) == 64
    expected_body = [
        "GRANDES NÚMEROS",
        "ESCALA DA INDÚSTRIA",
        "OFERTAS ENCERRADAS · SÉRIE CVM",
        "OFERTAS ENCERRADAS · SÉRIE ANBIMA",
        "BASE INVESTIDORA",
        "DISTRIBUIÇÃO POR NÚMERO DE COTISTAS",
        "TAXONOMIA ANALÍTICA · DECISÕES APROVADAS",
        "TAXONOMIA CVM · RECLASSIFICAÇÃO DE ADQUIRÊNCIA",
        "CARTEIRA POR TIPO DE RECEBÍVEL",
        "OBSERVABILIDADE DA INADIMPLÊNCIA",
        "INADIMPLÊNCIA · BASE ORIGINAL",
        "INADIMPLÊNCIA · EX-ZEROS",
        "INADIMPLÊNCIA · COORTE ATUAL POR RECEBÍVEL",
        "INADIMPLÊNCIA · DISPERSÃO ENTRE REPORTANTES",
        "INADIMPLÊNCIA · SÍNTESE EXECUTIVA",
        "PRESTADORES · RANKING E CONCENTRAÇÃO",
        "RANKING · TOP 20 FIDCs",
        "RANKING · TOP 20 OUTROS",
        "Fomento Mercantil · R$",
        "Agro, Indústria e Comércio · R$",
        "Financeiro · R$",
        "Outros · R$",
        "MODELO DE PRESTAÇÃO",
        "CONCENTRAÇÃO DAS MONOESTRUTURAS",
        "OFERTAS ENCERRADAS · VOLUME E TICKET",
        "OFERTAS ENCERRADAS · DISTRIBUIÇÃO DO TICKET",
        "OFERTAS · VOLUME E REGIME",
        "TOP 15 · OFERTAS ENCERRADAS",
        "TOP 15 · HISTÓRICO",
        "TOP 15 · 2022 PARCIAL",
        "PRINCIPAIS CONCLUSÕES",
    ]
    assert "INDÚSTRIA DE FIDCs" in slides[0]
    for slide_text, expected in zip(slides[1:32], expected_body, strict=True):
        assert expected in slide_text
    assert "Escopo, fontes e limitações" in slides[32]
    profiles = slides[33:53]
    assert len(profiles) == 20
    assert sum("APÊNDICE · CURADORIA TOP 20" in text for text in slides) == 20
    for rank, slide_text in enumerate(profiles, start=1):
        assert "APÊNDICE · CURADORIA TOP 20" in slide_text
        assert f"#{rank} " in slide_text
    assert "Ex-360 publicável" in slides[10]
    assert "R$ 6,89 bi" in slides[10]
    assert "4,4% da carteira" in slides[11]
    assert "13,5%" in slides[12]
    assert "9,1 p.p." in slides[12]
    assert "PRESTADORES · EVOLUÇÃO E RANKING" in slides[53]
    assert "FIDCs DOS CINCO BANCOS · COORTE ATUAL" in slides[54]
    assert "PRESTADORES · LIDERANÇA EXPLICADA" in slides[55]
    assert "MARKET SHARE · ADMINISTRAÇÃO" in slides[56]
    assert "MARKET SHARE · GESTÃO" in slides[57]
    assert "MARKET SHARE · CUSTÓDIA" in slides[58]
    assert "PRESTADORES · EVIDÊNCIAS DE MIGRAÇÃO" in slides[59]
    assert "Administração por subtipo" in slides[60]
    assert "Gestão por subtipo" in slides[61]
    assert "Custódia por subtipo" in slides[62]
    assert "APÊNDICE · CASO ATLÂNTICO" in slides[63]
    assert "09.194.841/0001-51" in slides[63]
    assert "A quebra no bruto coincide" in slides[63]
    deck_text = "\n".join(slides)
    assert deck_text.count("R$ 16,69 bi") == 0
    assert "Visão ex-360 bloqueada" not in deck_text


def test_structural_audit_corrections_are_materialized_in_the_deck() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slides = _slide_texts(archive)

    assert all(token in slides[1] for token in ("58,4%", "59,5%", "R$ 733,1 bi", "PL ≥ R$ 200 mi"))
    assert "70,1% do aumento líquido" in slides[9]
    assert "11,5% do Tipo literal Outros" in slides[18]
    assert "19,6% do bucket do slide 8" in slides[18]
    assert "FICs excluídos pelo portão único" in slides[23]
    assert "Kanastra permanece separada do Itaú" in slides[23]
    assert "sobre jan–jun/25" in slides[25]
    assert re.search(r"2022 FY.*N/D N/D", slides[25])
    assert slides[12].index("Setor público") < slides[12].index("Agronegócio")
    assert "66,0% dos R$ 77,7 bi" in slides[31]
    assert "PRESTADORES · EVIDÊNCIAS DE MIGRAÇÃO" in slides[59]
    assert "100,0% é coerente com a estratégia NPL" in slides[63]

    deck_text = "\n".join(slides)
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


def test_scale_slide_uses_two_native_office_charts_with_direct_pl_and_fic_balance() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, 3)
        slide = ET.fromstring(archive.read("ppt/slides/slide3.xml"))
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
    assert "PL DIRETO + SALDO FIC" in text
    assert "CARTEIRA DE CRÉDITO PRIVADA AMPLIADA" in text
    assert "excluídos títulos públicos" in text
    assert "demais securitizações (CRIs e CRAs)" in text
    assert "PL direto e carteira privada têm perímetros contábeis distintos" in text
    assert "Mai/26" not in text

    left_bar = charts[0].find(f".//{{{CHART}}}barChart")
    right_bar = charts[1].find(f".//{{{CHART}}}barChart")
    assert left_bar is not None and right_bar is not None
    assert len(left_bar.findall(f"{{{CHART}}}ser")) == 2
    assert (
        left_bar.find(f"{{{CHART}}}grouping").attrib.get("val")
        == "stacked"
    )
    assert len(right_bar.findall(f"{{{CHART}}}ser")) == 5
    assert (
        right_bar.find(f"{{{CHART}}}grouping").attrib.get("val")
        == "stacked"
    )


def test_taxonomy_slide_has_two_native_office_charts_for_anbima_evolution() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        chart_paths = _slide_chart_paths(archive, 8)
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
        assert ">N/D<" not in visible
    assert groupings == {"stacked", "percentStacked"}


def test_offer_slides_use_native_charts_and_editable_native_tables() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        ticket_charts = _slide_chart_paths(archive, 27)
        ticket_charts = [
            path for path in ticket_charts
            if ET.fromstring(archive.read(path)).find(f".//{{{CHART}}}barChart") is not None
        ]
        assert len(ticket_charts) == 3
        slide25 = ET.fromstring(archive.read("ppt/slides/slide27.xml"))
        assert slide25.findall(f".//{{{DML}}}tbl") == []
        for chart_path in ticket_charts:
            chart = ET.fromstring(archive.read(chart_path))
            bar_chart = chart.find(f".//{{{CHART}}}barChart")
            assert bar_chart is not None
            grouping = bar_chart.find(f"{{{CHART}}}grouping")
            assert grouping is not None
            assert grouping.attrib.get("val") == "clustered"
            assert len(bar_chart.findall(f"{{{CHART}}}ser")) == 3

        regime_charts = _slide_chart_paths(archive, 28)
        regime_charts = [
            path for path in regime_charts
            if ET.fromstring(archive.read(path)).find(f".//{{{CHART}}}barChart") is not None
        ]
        assert len(regime_charts) == 4
        slide26 = ET.fromstring(archive.read("ppt/slides/slide28.xml"))
        assert slide26.findall(f".//{{{DML}}}tbl") == []

        assert _slide_chart_paths(archive, 29) == []
        slide27 = ET.fromstring(archive.read("ppt/slides/slide29.xml"))
        assert len(slide27.findall(f".//{{{DML}}}tbl")) == 2
        text = " ".join(node.text or "" for node in slide27.iter(f"{{{DML}}}t"))
        for token in (
            "TOP 15 · OFERTAS ENCERRADAS",
            "JAN–JUN/26 · TOP 15",
            "2025FY · TOP 15",
            "IBBA",
            "GF",
            "Público",
            "Agência",
            "Rating",
        ):
            assert token in text

        slide28 = ET.fromstring(archive.read("ppt/slides/slide30.xml"))
        assert len(slide28.findall(f".//{{{DML}}}tbl")) == 2
        slide29 = ET.fromstring(archive.read("ppt/slides/slide31.xml"))
        assert len(slide29.findall(f".//{{{DML}}}tbl")) == 1


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
    ):
        assert expected in html


@pytest.mark.parametrize("slide_number", [57, 58, 59, 61, 62, 63])
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


def test_provider_ranking_slide_has_six_native_charts_and_method_note() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slide = ET.fromstring(archive.read("ppt/slides/slide54.xml"))
        text = " ".join(node.text or "" for node in slide.iter(f"{{{DML}}}t"))
        chart_paths = _slide_chart_paths(archive, 54)

    assert len(chart_paths) >= 6
    assert slide.findall(f".//{{{DML}}}tbl") == []
    for expected in (
        "ADMINISTRAÇÃO",
        "GESTÃO",
        "CUSTÓDIA",
        "TODOS OS PRESTADORES",
        "INDEPENDENTES",
        "Exclui Sistema Petrobras e TAPSO",
        "Singulare consolidada em QI Tech",
        "Itaú",
    ):
        assert expected in text


def test_holder_distribution_slide_has_four_charts_and_normalized_histograms() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        slide = ET.fromstring(archive.read("ppt/slides/slide7.xml"))
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
        for chart_path in _slide_chart_paths(archive, 7):
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
        (9, {"Dez/23", "Jun/26"}),
        (10, {"Dez/23", "Jun/26"}),
        (17, {"Dez/25", "Jun/26"}),
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
    if slide_number in {8, 9}:
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
        "Auditoria numérica",
        "Ofertas encerradas",
        "Regime de colocação",
        "Histograma ofertas",
        "Crédito Privado Ampliado",
        "Originadores 2026",
        "Top 15 ofertas",
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


def test_revision_renderer_version_tracks_provider_flow_assets() -> None:
    source = (ROOT / "scripts" / "build_fidc_revision_artifacts.mjs").read_text(
        encoding="utf-8"
    )
    assert 'const RENDERER_VERSION = "industry_revision_artifacts_v25";' in source
    assert "payload.executive_conclusions" in source
    assert "payload.executive_conclusion_notes" in source


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
