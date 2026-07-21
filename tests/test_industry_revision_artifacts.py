from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest


ROOT = Path(__file__).resolve().parents[1]
PPTX = ROOT / "outputs" / "Industria_FIDC_Executivo_202607_revisado.pptx"
XLSX = ROOT / "outputs" / "Industria_FIDC_Dados_202607_revisado.xlsx"
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

    assert len(slides) == 56
    expected_body = [
        "GRANDES NÚMEROS",
        "ESCALA DA INDÚSTRIA",
        "BASE INVESTIDORA",
        "DISTRIBUIÇÃO POR NÚMERO DE COTISTAS",
        "TIPO ANBIMA",
        "TAXONOMIA CVM · RECLASSIFICAÇÃO DE ADQUIRÊNCIA",
        "CARTEIRA POR TIPO DE RECEBÍVEL",
        "OBSERVABILIDADE DA INADIMPLÊNCIA",
        "INADIMPLÊNCIA · EVOLUÇÃO E QUEBRA",
        "INADIMPLÊNCIA · COORTE ATUAL POR RECEBÍVEL",
        "PRESTADORES · RANKING E CONCENTRAÇÃO",
        "MARKET SHARE · ADMINISTRAÇÃO",
        "MARKET SHARE · GESTÃO",
        "MARKET SHARE · CUSTÓDIA",
        "PRESTADORES · EVOLUÇÃO DO RANKING",
        "PRESTADORES INDEPENDENTES · EVOLUÇÃO",
        "FIDCs DOS CINCO BANCOS · COORTE ATUAL",
        "PRESTADORES · LIDERANÇA EXPLICADA",
        "CBSF / REAG · DESTINO DOS FUNDOS",
        "PRESTADORES · MIGRAÇÃO EM ADMINISTRAÇÃO",
        "PRESTADORES · MIGRAÇÃO EM GESTÃO",
        "PRESTADORES · MIGRAÇÃO EM CUSTÓDIA",
        "RANKING · TOP 20 FIDCs",
        "RANKING · TOP 20 OUTROS",
        "MODELO DE PRESTAÇÃO",
        "CONCENTRAÇÃO DAS MONOESTRUTURAS",
        "OFERTAS ENCERRADAS · VOLUME E TICKET",
        "OFERTAS ENCERRADAS · DISTRIBUIÇÃO DO TICKET",
        "OFERTAS ENCERRADAS · ORIGINADORES NOMINÁVEIS",
        "PRINCIPAIS CONCLUSÕES",
    ]
    assert "INDÚSTRIA DE FIDCs" in slides[0]
    for slide_text, expected in zip(slides[1:31], expected_body, strict=True):
        assert expected in slide_text
    assert "Escopo, fontes e limitações" in slides[31]
    assert "Administração por subtipo" in slides[32]
    assert "Gestão por subtipo" in slides[33]
    assert "Custódia por subtipo" in slides[34]
    profiles = slides[35:55]
    assert len(profiles) == 20
    assert sum("APÊNDICE · CURADORIA TOP 20" in text for text in slides) == 20
    for rank, slide_text in enumerate(profiles, start=1):
        assert "APÊNDICE · CURADORIA TOP 20" in slide_text
        assert f"#{rank} " in slide_text
    assert "APÊNDICE · CASO ATLÂNTICO" in slides[55]
    assert "09.194.841/0001-51" in slides[55]
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


@pytest.mark.parametrize("slide_number", [13, 14, 15, 33, 34, 35])
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
        slide = ET.fromstring(archive.read("ppt/slides/slide16.xml"))
        text = " ".join(node.text or "" for node in slide.iter(f"{{{DML}}}t"))
        chart_paths = _slide_chart_paths(archive, 16)

    assert len(chart_paths) == 3
    assert len(slide.findall(f".//{{{DML}}}tbl")) == 3
    assert text.count("Participante") == 3
    for expected in (
        "ADMINISTRAÇÃO",
        "GESTÃO",
        "CUSTÓDIA",
        "Dez/24",
        "Dez/25",
            "Jun/26",
        "Sistema Petrobras e TAPSO excluídos",
        "Itaú",
    ):
        assert expected in text


def test_provider_flow_slides_use_clean_raster_snapshots_and_disclose_limits() -> None:
    _require(PPTX)
    with ZipFile(PPTX) as archive:
        attribution = ET.fromstring(archive.read("ppt/slides/slide19.xml"))
        reag = ET.fromstring(archive.read("ppt/slides/slide20.xml"))
        transitions = ET.fromstring(archive.read("ppt/slides/slide21.xml"))
        manager = ET.fromstring(archive.read("ppt/slides/slide22.xml"))
        custodian = ET.fromstring(archive.read("ppt/slides/slide23.xml"))
        attribution_text = " ".join(node.text or "" for node in attribution.iter(f"{{{DML}}}t"))
        reag_text = " ".join(node.text or "" for node in reag.iter(f"{{{DML}}}t"))
        transition_text = " ".join(node.text or "" for node in transitions.iter(f"{{{DML}}}t"))

        assert len(_slide_chart_paths(archive, 19)) == 2
        assert not _slide_chart_paths(archive, 20)
        assert not _slide_chart_paths(archive, 21)
        assert not _slide_chart_paths(archive, 22)
        assert not _slide_chart_paths(archive, 23)
        reag_images = _slide_image_paths(archive, 20)
        transition_images = _slide_image_paths(archive, 21)
        manager_images = _slide_image_paths(archive, 22)
        custodian_images = _slide_image_paths(archive, 23)
        assert len(reag_images) == 1
        assert len(transition_images) == 1
        assert len(manager_images) == 1
        assert len(custodian_images) == 1
        assert len(archive.read(reag_images[0])) > 50_000
        assert len(archive.read(transition_images[0])) > 50_000
        assert len(archive.read(manager_images[0])) > 50_000
        assert len(archive.read(custodian_images[0])) > 50_000

    assert "95,9%" in attribution_text
    assert "R$ 28,0 bi" in attribution_text
    assert "Master e Planner receberam R$ 9,9 bi" in reag_text
    assert "destino em jun/26" in reag_text
    assert len(reag.findall(f".//{{{PML}}}pic")) == 1
    assert len(transitions.findall(f".//{{{PML}}}pic")) == 1
    assert not reag.findall(f".//{{{PML}}}cxnSp")
    assert not transitions.findall(f".//{{{PML}}}cxnSp")
    assert "largura = PL jun/26" in transition_text
    assert "Cobertura: 73,1%" in transition_text


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
        (6, {"Dez/23", "Jun/26"}),
        (7, {"Dez/23", "Jun/26"}),
        (8, {"Dez/23", "Jun/26"}),
        (12, {"Dez/25", "Jun/26"}),
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
    if slide_number in {6, 7, 8}:
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
        "Inadimplência por recebível",
        "Histórico inad. coorte",
        "Ranking independentes",
        "FIDCs por banco",
        "Detalhe coorte bancos",
        "Taxonomia adquirência",
        "Adquirência reclass.",
        "Ofertas encerradas",
        "Histograma ofertas",
        "Originadores 2026",
        "Principais conclusões",
        "Atribuição prestadores",
        "Fluxos prestadores",
        "Migração CBSF",
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


def test_revision_renderer_version_tracks_provider_flow_assets() -> None:
    source = (ROOT / "scripts" / "build_fidc_revision_artifacts.mjs").read_text(
        encoding="utf-8"
    )
    assert 'const RENDERER_VERSION = "industry_revision_artifacts_v13";' in source


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
    assert metrics["service_model_universe_funds"] == 4247
    assert metrics["admin_custodia_juntas_fundos"] == 3782
    assert metrics["admin_custodia_juntas_share_pl"] == pytest.approx(0.9028615536)
    assert metrics["monoestrutura_share_pl"] == pytest.approx(0.3566815953)
    assert metrics["btg_combo_tres_funcoes_fundos"] == 70
    assert metrics["btg_combo_tres_funcoes_pl_brl"] == pytest.approx(
        78_061_458_101.28
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
    assert metrics["admin_transition_2024_2025_continuing_funds"] == 2477
    assert metrics["admin_transition_2024_2025_changed_funds"] == 257
    assert metrics["admin_transition_2024_2025_changed_pl_brl"] == pytest.approx(
        33_020_408_763.18
    )
    assert metrics["admin_transition_2024_2025_changed_share_pl"] == pytest.approx(
        0.07243504065
    )
    assert metrics["admin_transition_2024_2025_cielo_funds"] == 2
    assert metrics["admin_transition_2024_2025_cielo_pl_brl"] == pytest.approx(
        8_922_506_388.74
    )

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


def test_materialized_gross_pl_cagrs_match_the_chart_totals() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    periods = {
        (int(row["start_year"]), int(row["end_year"])): row
        for row in payload["pl_total_cagr_periods"]
    }

    assert set(periods) == {(2015, 2018), (2018, 2023), (2024, 2025)}
    assert periods[(2015, 2018)]["annual_intervals"] == 3
    assert periods[(2015, 2018)]["cagr"] == pytest.approx(0.1868018650)
    assert periods[(2018, 2023)]["annual_intervals"] == 5
    assert periods[(2018, 2023)]["cagr"] == pytest.approx(0.2794351323)
    assert periods[(2024, 2025)]["annual_intervals"] == 1
    assert periods[(2024, 2025)]["cagr"] == pytest.approx(0.2559047631)


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

    assert summary["competencia_tabela_ii"] == "2026-06"
    assert summary["competencia_pl"] == "2025-06"
    assert len(rows) == summary["fundos_total"] == 44
    assert len(principal) == summary["fundos_cartao_segmento_principal"] == 43
    assert len(secondary) == summary["fundos_exposicao_secundaria"] == 1
    assert summary["fundos_anbima_cartao_explicito"] == 0
    assert sum(row["ja_curado_como_adquirencia"] for row in rows) == 9
    assert summary["fundos_curados_adquirencia"] == 9
    assert all(row["cnpj_fundo_identificado"] for row in rows)
    assert len({row["cnpj_fundo_formatado"] for row in rows}) == 44
    assert len(observable) == summary["fundos_pl_observavel"] == 37
    assert sum(row["pl_jun25_brl"] for row in observable) == pytest.approx(
        summary["pl_jun25_observado_brl"]
    )
    assert summary["pl_jun25_observado_brl"] == pytest.approx(
        76_063_154_829.65
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


def test_materialized_acquiring_mix_includes_the_three_seller_fidcs() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    current = next(
        row
        for row in payload["acquiring_reclassified_mix"]
        if row["competencia"] == "2026-06"
        and row["categoria_analitica"] == "Adquirência"
    )

    assert current["fundos_adquirencia_curados"] == 16
    assert current["fundos_adquirencia_observados"] == 14
    assert current["fundos_movidos_para_adquirencia"] == 14
    assert current["pl_brl"] == pytest.approx(80_565_524_077.66)
    assert current["share_pl"] == pytest.approx(0.0915126990)
    assert current["denominador_pl_brl"] == pytest.approx(880_375_346_502.31)
    assert current["rank_reclassificado"] == 5
    moved = set(current["cnpjs_movidos_para_adquirencia"].split(";"))
    assert {"50473039000102", "55471753000177", "63572282000111"}.issubset(moved)
    current_rows = {
        row["categoria_analitica"]: row
        for row in payload["acquiring_reclassified_mix"]
        if row["competencia"] == "2026-06"
    }
    assert current_rows["Cartão"]["fundos_movidos_da_categoria"] == 9
    assert current_rows["Comercial"]["fundos_movidos_da_categoria"] == 2
    assert current_rows["Serviços"]["fundos_movidos_da_categoria"] == 2
    assert current_rows["Financeiro"]["fundos_movidos_da_categoria"] == 1
