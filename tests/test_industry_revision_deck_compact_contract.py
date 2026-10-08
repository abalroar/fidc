"""Contrato editorial do PPTX compacto da revisão setorial."""

from __future__ import annotations

import posixpath
import json
import os
from pathlib import Path
import unicodedata
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from services.industry_comparative_period import ComparisonCut
from services.industry_revision_export import (
    EXPECTED_SLIDE_SEQUENCE,
    EXPECTED_SLIDE_IDS,
    EXPECTED_SLIDES,
    ISSUANCE_TAXONOMY_TABLE_DIMENSIONS,
    TYPE_RANKING_SLIDE_SEQUENCE,
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

PAYLOAD_PATH = Path(os.environ.get("FIDC_TEST_PAYLOAD", PPTX.parent / "artifact_payload.json"))

def _payload() -> dict:
    return json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))

def _cut() -> ComparisonCut:
    return ComparisonCut.from_competence(_payload()["offers_as_of"][:7])


DML = "http://schemas.openxmlformats.org/drawingml/2006/main"
CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"
PML = "http://schemas.openxmlformats.org/presentationml/2006/main"
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


SLIDE_INSTRUMENTS = _contract_slide_number("emissoes de fidcs")
SLIDE_STOCK_AND_TYPES = _contract_slide_number("emissoes por setor")
SLIDE_ISSUANCE_TAXONOMY = _contract_slide_number("emissoes por setor")
SLIDE_ANALYTICAL_TAXONOMY = _contract_slide_number("composicao da industria")
SLIDE_OFFER_REGIME = _contract_slide_number("garantia firme", "melhores esforcos")
SLIDES_TOP_TYPE = tuple(
    EXPECTED_SLIDE_SEQUENCE.index(tokens) + 1
    for tokens in TYPE_RANKING_SLIDE_SEQUENCE
)


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


def _series_name(series: ET.Element) -> str:
    return "".join(
        node.text or ""
        for node in series.findall(f".//{{{CHART}}}tx//{{{CHART}}}v")
    )


def _series_color(series: ET.Element) -> str | None:
    for path in (
        f"{{{CHART}}}spPr/{{{DML}}}solidFill/{{{DML}}}srgbClr",
        f"{{{CHART}}}spPr/{{{DML}}}ln/{{{DML}}}solidFill/{{{DML}}}srgbClr",
    ):
        node = series.find(path)
        if node is not None and node.attrib.get("val"):
            return node.attrib["val"].upper()
    return None


def _series_values(series: ET.Element) -> list[float]:
    points = series.findall(
        f".//{{{CHART}}}val/{{{CHART}}}numLit/{{{CHART}}}pt"
    )
    if not points:
        points = series.findall(
            f".//{{{CHART}}}val/{{{CHART}}}numRef/"
            f"{{{CHART}}}numCache/{{{CHART}}}pt"
        )
    return [
        float(value.text)
        for point in points
        if (value := point.find(f"{{{CHART}}}v")) is not None
        and value.text not in {None, ""}
    ]


def _chart_categories(series: ET.Element) -> list[str]:
    points = series.findall(
        f".//{{{CHART}}}cat/{{{CHART}}}strLit/{{{CHART}}}pt"
    )
    if not points:
        points = series.findall(
            f".//{{{CHART}}}cat/{{{CHART}}}strRef/"
            f"{{{CHART}}}strCache/{{{CHART}}}pt"
        )
    return [
        value.text or ""
        for point in points
        if (value := point.find(f"{{{CHART}}}v")) is not None
    ]


def _slide_shape_fill_colors(archive: ZipFile, slide_number: int) -> set[str]:
    root = ET.fromstring(archive.read(f"ppt/slides/slide{slide_number}.xml"))
    return {
        node.attrib["val"].upper()
        for shape in root.findall(f".//{{{PML}}}sp")
        for node in shape.findall(
            f"{{{PML}}}spPr/{{{DML}}}solidFill/{{{DML}}}srgbClr"
        )
        if node.attrib.get("val")
    }


def test_compact_pptx_matches_dynamic_contract_and_omits_requested_sections() -> None:
    with ZipFile(PPTX) as archive:
        slides = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide")
            and name.endswith(".xml")
            and "/_rels/" not in name
        )
        assert len(slides) == EXPECTED_SLIDES
        text = "\n".join(
            _slide_text(archive, number)
            for number in range(1, EXPECTED_SLIDES + 1)
        )

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
        raw_text = _slide_text(archive, SLIDE_INSTRUMENTS)
        text = raw_text.upper()
        charts = [
            root
            for root in _chart_roots(archive, SLIDE_INSTRUMENTS)
            if root.find(f".//{{{CHART}}}barChart") is not None
        ]
        tables = _tables(archive, SLIDE_INSTRUMENTS)

    assert len(charts) == 2
    assert len(tables) == 1
    assert "FIDCS E DEMAIS INSTRUMENTOS ELEGÍVEIS" in text
    assert "VALOR ENCERRADO POR INSTRUMENTO" in text
    assert "FIDCs e demais instrumentos elegíveis · R$ bi" in raw_text
    assert "Valor encerrado por instrumento · R$ bi" in raw_text
    assert _cut().period_label() in raw_text.casefold()
    assert any(
        f"{_cut().year} {_cut().period_label().split('/')[0]}"
        in " ".join(node.text or "" for node in chart.iter())
        for chart in charts
    )
    if _payload().get("offers_comparison_meta"):
        assert f"ANBIMA, {_payload()['anbima_market_offers_manifest']['comparison_meta']['period_label']}" in raw_text
    else:
        assert f"ANBIMA ({_cut().period_key()[:-2]}/{str(_cut().year)[-2:]})" in raw_text
    rows = tables[0].findall(f"{{{DML}}}tr")
    assert [_cell_text(cell) for cell in rows[0].findall(f"{{{DML}}}tc")] == [
        "Emissões por instrumento",
        f"{_cut().year - 1} YoY %",
        f"{_cut().period_label()} YoY" if _payload().get("offers_comparison_meta") else "1S26 YTD YoY",
    ]
    body = [row.findall(f"{{{DML}}}tc") for row in rows[1:]]
    assert [_cell_text(cells[0]) for cells in body] == [
        "FIDC",
        "Demais Instr.",
        "Debêntures",
        "CRI",
        "Notas comerciais",
        "CRA",
    ]
    assert "007A3D" in _cell_rgb(body[0][1])
    assert "007A3D" in _cell_rgb(body[0][2])
    assert "7A1F3D" in _cell_rgb(body[1][2])
    assert "7A1F3D" in _cell_rgb(body[5][2])
    assert all(_cell_is_bold(cell) for cell in (body[0][1], body[0][2], body[1][2], body[5][2]))


def test_slide_4_has_only_sector_issuance_to_avoid_duplicate_stock() -> None:
    with ZipFile(PPTX) as archive:
        raw_text = _slide_text(archive, SLIDE_STOCK_AND_TYPES)
        text = raw_text.upper()
        charts = [
            root
            for root in _chart_roots(archive, SLIDE_STOCK_AND_TYPES)
            if root.find(f".//{{{CHART}}}barChart") is not None
        ]
        tables = _tables(archive, SLIDE_STOCK_AND_TYPES)

    assert len(charts) == 2
    assert [
        root.find(f".//{{{CHART}}}grouping").attrib["val"] for root in charts
    ].count("stacked") == 1
    assert [
        root.find(f".//{{{CHART}}}grouping").attrib["val"] for root in charts
    ].count("percentStacked") == 1
    assert tables == []
    assert "EMISSÕES POR SETOR" in text
    assert _cut().period_label().upper() in text
    assert "SALDO EX-FIC" not in text
    assert "PARTICIPAÇÃO NO SALDO" not in text
    for title in (
        "Volume emitido · R$ bi",
        "Participação no volume emitido · %",
    ):
        assert title in raw_text


def test_compact_deck_keeps_editable_evidence_and_omits_sector_detail_table() -> None:
    with ZipFile(PPTX) as archive:
        assert len(_chart_roots(archive, SLIDE_STOCK_AND_TYPES)) == 2
        assert len(_chart_roots(archive, SLIDE_ANALYTICAL_TAXONOMY)) == 2
        assert _tables(archive, SLIDE_STOCK_AND_TYPES) == []
        assert _tables(archive, SLIDE_ANALYTICAL_TAXONOMY) == []
    assert ISSUANCE_TAXONOMY_TABLE_DIMENSIONS == ()


def test_renderer_contract_matches_15_topics_and_uses_payload_periods() -> None:
    import re
    source = (ROOT / "scripts" / "build_fidc_revision_artifacts.mjs").read_text(encoding="utf-8")
    declaration = source.split("const SLIDE_CONTRACT_V1 = Object.freeze([", 1)[1].split("]);", 1)[0]
    assert tuple(re.findall(r'"([^"\n]+)"', declaration)) == EXPECTED_SLIDE_IDS
    assert len(EXPECTED_SLIDE_IDS) == 15
    assert "fallbackExecutiveConclusions" not in source
    assert 'rows.length !== 5' in source


def test_analytical_taxonomy_expands_outros_with_the_requested_display_names() -> None:
    with ZipFile(PPTX) as archive:
        text = _slide_text(archive, SLIDE_ANALYTICAL_TAXONOMY).upper()
        charts = [
            root
            for root in _chart_roots(archive, SLIDE_ANALYTICAL_TAXONOMY)
            if root.find(f".//{{{CHART}}}barChart") is not None
        ]

    assert len(charts) == 2
    for label in (
        "PRECATÓRIOS E/OU AÇÕES JUDICIAIS",
        "MULTICEDENTE/MULTISACADO",
        "RECUPERAÇÃO / FIDCS NP",
    ):
        assert label in text


def test_slides_4_to_6_use_exact_taxonomy_colors_without_changing_other_series() -> None:
    expected_colors = {
        "Fomento Mercantil": "73787D",
        "Agro, Indústria e Comércio": "0A3B00",
        "Financeiro": "EC7000",
        "Precatórios / ações": "151515",
        "Precatórios e/ou Ações Judiciais": "151515",
        "Multicedente / multisacado": "7030A0",
        "Multicedente/Multisacado": "7030A0",
        "Recuperação / NP": "E7E9EB",
        "Recuperação / FIDCs NP": "E7E9EB",
        "N/D": "D7DADD",
        "Outros": "D7DADD",
    }
    with ZipFile(PPTX) as archive:
        for slide_number in (
            SLIDE_STOCK_AND_TYPES,
            SLIDE_ISSUANCE_TAXONOMY,
            SLIDE_ANALYTICAL_TAXONOMY,
        ):
            seen: set[str] = set()
            for root in _chart_roots(archive, slide_number):
                for series in root.findall(f".//{{{CHART}}}ser"):
                    name = _series_name(series)
                    if name not in expected_colors:
                        continue
                    seen.add(name)
                    assert _series_color(series) == expected_colors[name]
            assert "Agro, Indústria e Comércio" in seen

        slide_4_fills = _slide_shape_fill_colors(archive, SLIDE_STOCK_AND_TYPES)
        assert {"0A3B00", "EC7000", "73787D", "D7DADD"} <= slide_4_fills

        slide_6_roots = _chart_roots(archive, SLIDE_ANALYTICAL_TAXONOMY)
        assert all(root.find(f".//{{{CHART}}}lineChart") is None for root in slide_6_roots)
        legend_fills = _slide_shape_fill_colors(archive, SLIDE_ANALYTICAL_TAXONOMY)
        assert {"0A3B00", "7030A0"} <= legend_fills


def test_offer_regime_uses_full_width_volume_shares_that_close_to_one() -> None:
    with ZipFile(PPTX) as archive:
        raw_text = _slide_text(archive, SLIDE_OFFER_REGIME)
        roots = _chart_roots(archive, SLIDE_OFFER_REGIME)
        bar_roots = [
            root
            for root in roots
            if root.find(f".//{{{CHART}}}barChart") is not None
        ]

    assert len(bar_roots) == 1
    assert "Regime de colocação · número de ofertas" not in raw_text
    assert "Número de ofertas" not in raw_text
    assert "Volume registrado · R$ bi" not in raw_text
    assert "Regime de colocação · participação no volume · % do total" in raw_text
    assert "Regime de colocação das ofertas" in raw_text
    assert _cut().period_label() in raw_text

    regime_chart = bar_roots[0]
    series = regime_chart.findall(f".//{{{CHART}}}barChart/{{{CHART}}}ser")
    assert _chart_categories(series[0]) == [
        "Não informado",
        "Misto",
        "Garantia firme",
        "Melhores esforços",
    ]
    for item in series:
        values = _series_values(item)
        assert len(values) == 4
        assert abs(sum(values) - 1.0) < 1e-9

    import json
    payload_path = Path(os.environ.get("FIDC_TEST_PAYLOAD", PPTX.parent / "artifact_payload.json"))
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    rows = payload["closed_offer_placement_regime"]
    for item in series:
        period = _series_name(item).replace("–", "-").replace("FY", " FY")
        matching = [row for row in rows if row["period_label"] == period]
        assert matching, period
        expected = {row["placement_regime"]: float(row["registered_volume_share"]) for row in matching}
        assert _series_values(item) == [expected[label] for label in _chart_categories(item)]

    assert any(
        node.text == "0.0%"
        for node in regime_chart.iter(f"{{{CHART}}}formatCode")
    )
    assert any(
        node.attrib.get("formatCode") == "0%"
        for node in regime_chart.iter(f"{{{CHART}}}numFmt")
    )


def test_taxonomy_rankings_are_outside_the_15_slide_executive_contract() -> None:
    assert TYPE_RANKING_SLIDE_SEQUENCE == ()
    with ZipFile(PPTX) as archive:
        text = " ".join(_slide_text(archive, number) for number in range(1, EXPECTED_SLIDES + 1))
    assert "RANKING · TOP FUNDOS E ORIGINADORES" not in text
    assert "RISCO ESTRUTURAL · CARTEIRA I" not in text
    assert "TOP 15 · OFERTAS ENCERRADAS" not in text


def test_ytd_offer_curve_has_twelve_month_positions_and_no_future_zeroes() -> None:
    import json
    import pytest

    payload_path = Path(os.environ.get("FIDC_TEST_PAYLOAD", PPTX.parent / "artifact_payload.json"))
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    with ZipFile(PPTX) as archive:
        curve = next(
            root for root in _chart_roots(archive, 8)
            if root.find(f".//{{{CHART}}}lineChart") is not None
        )
    assert curve.find(f".//{{{CHART}}}dispBlanksAs").attrib["val"] == "gap"
    series = curve.findall(f".//{{{CHART}}}lineChart/{{{CHART}}}ser")
    assert {_series_name(item) for item in series} == {str(year) for year in range(_cut().year - 2, _cut().year + 1)}
    for item in series:
        year = int(_series_name(item))
        assert len(_chart_categories(item)) == 12
        container = item.find(f"{{{CHART}}}val/{{{CHART}}}numLit")
        assert container is not None
        assert int(container.find(f"{{{CHART}}}ptCount").attrib["val"]) == 12
        points = {int(point.attrib["idx"]): point.find(f"{{{CHART}}}v") for point in container.findall(f"{{{CHART}}}pt")}
        values = [float(points[index].text) if index in points and points[index] is not None and points[index].text else None for index in range(12)]
        observed_months = _cut().month if year == _cut().year else 12
        monthly = {int(row["month"]): float(row["registered_volume_brl"]) for row in payload["closed_offers_monthly"] if int(row["year"]) == year}
        expected = [sum(monthly[month] for month in range(1, index + 2)) / 1e9 for index in range(observed_months)]
        assert values[:observed_months] == pytest.approx(expected)
        assert values[observed_months:] == [None] * (12 - observed_months)


def test_all_native_charts_have_observed_data_and_legends_use_editable_shapes() -> None:
    with ZipFile(PPTX) as archive:
        for slide_number in range(1, EXPECTED_SLIDES + 1):
            for chart in _chart_roots(archive, slide_number):
                all_series = chart.findall(f".//{{{CHART}}}ser")
                assert all_series
                assert all(_series_values(series) for series in all_series), slide_number


def test_native_horizontal_charts_keep_categories_visible() -> None:
    with ZipFile(PPTX) as archive:
        for slide_number in range(1, EXPECTED_SLIDES + 1):
            charts = _chart_roots(archive, slide_number)
            visible_category_sets = {
                tuple(_chart_categories(chart.find(f".//{{{CHART}}}ser")))
                for chart in charts
                if chart.find(f".//{{{CHART}}}catAx/{{{CHART}}}delete") is not None
                and chart.find(f".//{{{CHART}}}catAx/{{{CHART}}}delete").attrib.get("val") == "0"
            }
            for chart in charts:
                direction = chart.find(f".//{{{CHART}}}barChart/{{{CHART}}}barDir")
                if direction is None or direction.attrib.get("val") != "bar":
                    continue
                axes = chart.findall(f".//{{{CHART}}}catAx")
                assert axes
                if slide_number == 13:
                    assert chart.find(f".//{{{CHART}}}valAx/{{{CHART}}}scaling/{{{CHART}}}min").attrib["val"] == "0"
                    assert chart.find(f".//{{{CHART}}}valAx/{{{CHART}}}scaling/{{{CHART}}}max").attrib["val"] == "1"
                if all(axis.find(f"{{{CHART}}}delete").attrib.get("val") == "0" for axis in axes):
                    continue
                # Paired amount/share charts reuse the visible categories on the left.
                assert slide_number in {6, 7}
                assert tuple(_chart_categories(chart.find(f".//{{{CHART}}}ser"))) in visible_category_sets


def test_native_data_labels_disable_extra_content_in_every_point_override() -> None:
    with ZipFile(PPTX) as archive:
        for slide_number in range(1, EXPECTED_SLIDES + 1):
            for chart in _chart_roots(archive, slide_number):
                for labels in chart.findall(f".//{{{CHART}}}dLbls"):
                    for scope in [labels, *labels.findall(f"{{{CHART}}}dLbl")]:
                        assert scope.find(f"{{{CHART}}}showVal") is not None
                        for flag in ("showLegendKey", "showCatName", "showSerName", "showPercent", "showBubbleSize"):
                            assert scope.find(f"{{{CHART}}}{flag}").attrib["val"] == "0", (slide_number, flag)


def test_stacked_labels_hide_small_segments_and_use_legible_emission_contrast() -> None:
    with ZipFile(PPTX) as archive:
        for slide_number in (4, 5):
            for chart in _chart_roots(archive, slide_number):
                maximum = float(chart.find(f".//{{{CHART}}}valAx/{{{CHART}}}scaling/{{{CHART}}}max").attrib["val"])
                for series in chart.findall(f".//{{{CHART}}}barChart/{{{CHART}}}ser"):
                    values = _series_values(series)
                    points = series.findall(f"{{{CHART}}}dLbls/{{{CHART}}}dLbl")
                    assert len(points) == len(values)
                    for point in points:
                        index = int(point.find(f"{{{CHART}}}idx").attrib["val"])
                        visible = point.find(f"{{{CHART}}}showVal").attrib["val"] in {"1", "true"}
                        assert visible == (values[index] >= 0.08 * maximum)
                        if slide_number == 4 and len(_chart_categories(series)) == 5:
                            color = point.find(f"{{{CHART}}}txPr/{{{DML}}}p/{{{DML}}}pPr/{{{DML}}}defRPr/{{{DML}}}solidFill/{{{DML}}}srgbClr")
                            assert color is not None
                            expected = "FFFFFF" if _series_name(series) in {"Fomento Mercantil", "Agro, Indústria e Comércio"} else "151515"
                            assert color.attrib["val"].upper() == expected


def test_dense_column_charts_keep_spaced_representative_labels_and_all_data() -> None:
    def visible_indices(series: ET.Element) -> set[int]:
        labels = series.find(f"{{{CHART}}}dLbls")
        default = labels.find(f"{{{CHART}}}showVal").attrib["val"] in {"1", "true"}
        visibility = {index: default for index in range(len(_series_values(series)))}
        for point in labels.findall(f"{{{CHART}}}dLbl"):
            index = int(point.find(f"{{{CHART}}}idx").attrib["val"])
            visibility[index] = point.find(f"{{{CHART}}}showVal").attrib["val"] in {"1", "true"}
        return {index for index, shown in visibility.items() if shown}

    with ZipFile(PPTX) as archive:
        scale = _chart_roots(archive, 2)[1]
        total = scale.find(f".//{{{CHART}}}lineChart/{{{CHART}}}ser")
        count = len(_series_values(total))
        assert count == len(_chart_categories(total))
        assert visible_indices(total) == set(range(0, count - 2, 2)) | {count - 1}

        instruments = _chart_roots(archive, 3)[1]
        for series in instruments.findall(f".//{{{CHART}}}barChart/{{{CHART}}}ser"):
            assert len(_series_values(series)) == len(_chart_categories(series)) == 4
            assert visible_indices(series) == (set(range(4)) if _series_name(series) == "Debêntures" else set())

        charts = _chart_roots(archive, 9)
        for chart_number, chart in enumerate(charts):
            series = chart.findall(f".//{{{CHART}}}barChart/{{{CHART}}}ser")
            count = len(_series_values(series[-1]))
            assert all(len(_series_values(item)) == len(_chart_categories(item)) == count for item in series)
            assert visible_indices(series[-1]) == (set(range(count)) if chart_number == 0 else {count - 1} if chart_number == 1 else set())


def test_compact_footers_and_investor_copy_preserve_separate_dates() -> None:
    with ZipFile(PPTX) as archive:
        for slide_number in range(2, EXPECTED_SLIDES + 1):
            root = ET.fromstring(archive.read(f"ppt/slides/slide{slide_number}.xml"))
            for shape in root.findall(f".//{{{PML}}}sp"):
                top = shape.find(f"{{{PML}}}spPr/{{{DML}}}xfrm/{{{DML}}}off")
                if top is None or int(top.attrib["y"]) < 674 * 9525:
                    continue
                text = "".join(node.text or "" for node in shape.iter(f"{{{DML}}}t"))
                if len(text) > 3:
                    assert len(text) <= 112, (slide_number, text)
        providers = _slide_text(archive, 12)
        assert "PL ex-FIC (R$ bi)" in providers
        investor = _slide_text(archive, 14)
        assert f"Ofertas até {_cut().period_key()[:-2]}/{str(_cut().year)[-2:]}; contas em" in investor
        assert "demanda institucional" not in investor
        assert "Público-alvo mede elegibilidade; contas podem repetir investidores." in investor




def _rewrite_pptx_part(part_name: str, transform) -> bytes:
    from io import BytesIO
    from zipfile import ZIP_DEFLATED

    output = BytesIO()
    with ZipFile(PPTX) as source, ZipFile(output, "w", ZIP_DEFLATED) as target:
        for member in source.infolist():
            content = source.read(member.filename)
            if member.filename == part_name:
                content = transform(content)
            target.writestr(member, content)
    return output.getvalue()


def test_compact_validator_rejects_ambiguous_native_point_labels() -> None:
    import pytest
    from services.industry_revision_export import RevisionExportUnavailable, validate_revision_pptx

    with ZipFile(PPTX) as archive:
        part = _chart_paths(archive, 8)[0]
    def change_label(content: bytes) -> bytes:
        root = ET.fromstring(content)
        root.find(f".//{{{CHART}}}dLbl/{{{CHART}}}showSerName").set("val", "1")
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with pytest.raises(RevisionExportUnavailable, match="rótulos nativos"):
        validate_revision_pptx(_rewrite_pptx_part(part, change_label))


def test_compact_validator_rejects_missing_notes_part_without_keyerror() -> None:
    from io import BytesIO
    from zipfile import ZIP_DEFLATED
    import pytest
    from services.industry_revision_export import RevisionExportUnavailable, validate_revision_pptx

    output = BytesIO()
    with ZipFile(PPTX) as source, ZipFile(output, "w", ZIP_DEFLATED) as target:
        notes = next(name for name in source.namelist() if name.startswith("ppt/notesSlides/") and name.endswith(".xml") and "/_rels/" not in name)
        for member in source.infolist():
            if member.filename != notes:
                target.writestr(member, source.read(member.filename))
    with pytest.raises(RevisionExportUnavailable, match="notas válidas"):
        validate_revision_pptx(output.getvalue())


def test_compact_validator_rejects_invalid_notes_xml_without_parseerror() -> None:
    import pytest
    from services.industry_revision_export import RevisionExportUnavailable, validate_revision_pptx
    with ZipFile(PPTX) as source:
        notes = next(name for name in source.namelist() if name.startswith("ppt/notesSlides/") and name.endswith(".xml") and "/_rels/" not in name)
    with pytest.raises(RevisionExportUnavailable, match="parte OOXML inválida|notas válidas"):
        validate_revision_pptx(_rewrite_pptx_part(notes, lambda _content: b"<invalid"))


def test_compact_validator_rejects_stale_payload_period() -> None:
    import json
    import pytest
    from services.industry_revision_export import RevisionExportUnavailable, validate_revision_pptx

    payload_path = Path(os.environ.get("FIDC_TEST_PAYLOAD", PPTX.parent / "artifact_payload.json"))
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    stale = dict(payload, latest_complete="2020-12")
    with pytest.raises(RevisionExportUnavailable, match="desatualizado"):
        validate_revision_pptx(PPTX.read_bytes(), expected_payload=stale)


def test_compact_validator_rejects_missing_slide() -> None:
    import pytest
    from services.industry_revision_export import RevisionExportUnavailable, validate_revision_pptx

    def remove_last_slide(content: bytes) -> bytes:
        root = ET.fromstring(content)
        ids = root.find(f"{{{PML}}}sldIdLst")
        assert ids is not None
        ids.remove(list(ids)[-1])
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    with pytest.raises(RevisionExportUnavailable, match="órfão|sequência|15 slides"):
        validate_revision_pptx(_rewrite_pptx_part("ppt/presentation.xml", remove_last_slide))


def test_compact_validator_rejects_duplicate_slide_identity() -> None:
    import pytest
    from services.industry_revision_export import RevisionExportUnavailable, validate_revision_pptx

    def duplicate_slide_id(content: bytes) -> bytes:
        root = ET.fromstring(content)
        ids = root.find(f"{{{PML}}}sldIdLst")
        assert ids is not None
        list(ids)[1].set("id", list(ids)[0].attrib["id"])
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    with pytest.raises(RevisionExportUnavailable, match="sldId duplicado"):
        validate_revision_pptx(_rewrite_pptx_part("ppt/presentation.xml", duplicate_slide_id))


def test_compact_validator_rejects_missing_editorial_metadata() -> None:
    import pytest
    from services.industry_revision_export import RevisionExportUnavailable, validate_revision_pptx

    with ZipFile(PPTX) as archive:
        notes = next(name for name in archive.namelist() if name.startswith("ppt/notesSlides/") and name.endswith(".xml") and "/_rels/" not in name)
    with pytest.raises(RevisionExportUnavailable, match="contrato editorial único"):
        validate_revision_pptx(_rewrite_pptx_part(notes, lambda raw: raw.replace(b"[Industry contract]", b"[Removed metadata]")))


def test_compact_validator_rejects_other_payload_with_same_period() -> None:
    import pytest
    from services.industry_revision_export import RevisionExportUnavailable, validate_revision_pptx

    with pytest.raises(RevisionExportUnavailable, match="assinatura do payload"):
        validate_revision_pptx(PPTX.read_bytes(), expected_signature="0" * 64)
