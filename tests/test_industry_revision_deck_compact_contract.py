"""Contrato editorial do PPTX compacto da revisão setorial."""

from __future__ import annotations

import posixpath
import os
from pathlib import Path
import unicodedata
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from services.industry_revision_export import (
    EXPECTED_SLIDE_SEQUENCE,
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


SLIDE_INSTRUMENTS = _contract_slide_number("fidcs seguem ganhando escala")
SLIDE_STOCK_AND_TYPES = _contract_slide_number("saldo e tipos")
SLIDE_ISSUANCE_TAXONOMY = _contract_slide_number("emissoes por categoria anbima")
SLIDE_ANALYTICAL_TAXONOMY = _contract_slide_number("revela que 63%")
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
    assert "jan–jun/26" in raw_text
    assert any(
        "2026 jan–jun"
        in " ".join(node.text or "" for node in chart.iter())
        for chart in charts
    )
    assert "snapshot jun/26" in raw_text
    rows = tables[0].findall(f"{{{DML}}}tr")
    assert [_cell_text(cell) for cell in rows[0].findall(f"{{{DML}}}tc")] == [
        "Emissões por instrumento",
        "2025 YoY %",
        "1S26 YTD YoY",
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


def test_slide_4_combines_opened_stock_and_sector_issuance_without_table() -> None:
    with ZipFile(PPTX) as archive:
        raw_text = _slide_text(archive, SLIDE_STOCK_AND_TYPES)
        text = raw_text.upper()
        charts = [
            root
            for root in _chart_roots(archive, SLIDE_STOCK_AND_TYPES)
            if root.find(f".//{{{CHART}}}barChart") is not None
        ]
        tables = _tables(archive, SLIDE_STOCK_AND_TYPES)

    assert len(charts) == 4
    assert [
        root.find(f".//{{{CHART}}}grouping").attrib["val"] for root in charts
    ].count("stacked") == 2
    assert [
        root.find(f".//{{{CHART}}}grouping").attrib["val"] for root in charts
    ].count("percentStacked") == 2
    assert tables == []
    assert "SALDO E TIPOS DE FIDCS" in text
    assert "FINANCEIROS DOMINAM SALDO E NOVAS EMISSÕES" in text
    assert "SALDO EX-FIC · R$ BI" in text
    assert "PARTICIPAÇÃO NO SALDO" in text
    assert "NOVAS EMISSÕES POR SETOR · R$ BI" in text
    assert "NOVAS EMISSÕES POR SETOR · %" in text
    for title in (
        "Saldo ex-FIC · R$ bi",
        "Participação no saldo",
        "Novas emissões por setor · R$ bi",
        "Novas emissões por setor · %",
    ):
        assert title in raw_text


def test_slide_5_has_two_stacked_sector_charts_and_native_table_without_deltas() -> None:
    with ZipFile(PPTX) as archive:
        raw_text = _slide_text(archive, SLIDE_ISSUANCE_TAXONOMY)
        text = raw_text.upper()
        charts = [
            root
            for root in _chart_roots(archive, SLIDE_ISSUANCE_TAXONOMY)
            if root.find(f".//{{{CHART}}}barChart") is not None
        ]
        tables = _tables(archive, SLIDE_ISSUANCE_TAXONOMY)

    assert len(charts) == 2
    assert {root.find(f".//{{{CHART}}}grouping").attrib["val"] for root in charts} == {
        "stacked",
        "percentStacked",
    }
    assert len(tables) == 1
    assert "EMISSÕES POR SETOR · R$ BI" in text
    assert "EMISSÕES POR SETOR · % DO TOTAL" in text
    assert "EMISSÕES POR CATEGORIA ANBIMA" in text
    assert "Emissões por setor · R$ bi" in raw_text
    assert "Emissões por setor · % do total" in raw_text
    assert "DELTA" not in text
    assert "Δ" not in text


def test_slide_5_yoy_highlights_follow_growth_direction() -> None:
    green = "007A3D"
    wine = "7A1F3D"
    with ZipFile(PPTX) as archive:
        table = _tables(archive, SLIDE_ISSUANCE_TAXONOMY)[0]
        rows = table.findall(f"{{{DML}}}tr")

    assert (
        len(rows),
        len(table.findall(f"{{{DML}}}tblGrid/{{{DML}}}gridCol")),
    ) == ISSUANCE_TAXONOMY_TABLE_DIMENSIONS[0]
    headers = [_cell_text(cell) for cell in rows[0].findall(f"{{{DML}}}tc")]
    assert headers == [
        "Categoria",
        "2023R$ bi",
        "2024R$ bi",
        "2025R$ bi",
        "1S25R$ bi",
        "1S26R$ bi",
        "1S26%",
        "1S26 YoY",
    ]
    body = {
        _cell_text(cells[0]): cells
        for row in rows[1:5]
        if (cells := row.findall(f"{{{DML}}}tc"))
    }
    expected = {
        "Fomento Mercantil": green,
        "Agro, Indústria e Comércio": wine,
        "Financeiro": green,
        "Outros": wine,
    }
    for category, cells in body.items():
        for column in range(1, 7):
            assert not ({green, wine} & _cell_rgb(cells[column]))
        assert expected[category] in _cell_rgb(cells[7])
        assert _cell_is_bold(cells[7])


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
        assert {"0A3B00", "7030A0"} <= slide_4_fills

        slide_6_roots = _chart_roots(archive, SLIDE_ANALYTICAL_TAXONOMY)
        legend_series = [
            series
            for root in slide_6_roots
            if root.find(f".//{{{CHART}}}lineChart") is not None
            for series in root.findall(f".//{{{CHART}}}ser")
        ]
        legend_colors = {
            _series_name(series): _series_color(series)
            for series in legend_series
        }
        assert legend_colors["Agro, Indústria e Comércio"] == "0A3B00"
        assert legend_colors["Multicedente/Multisacado"] == "7030A0"


def test_offer_regime_uses_full_width_volume_shares_that_close_to_one() -> None:
    with ZipFile(PPTX) as archive:
        raw_text = _slide_text(archive, SLIDE_OFFER_REGIME)
        roots = _chart_roots(archive, SLIDE_OFFER_REGIME)
        bar_roots = [
            root
            for root in roots
            if root.find(f".//{{{CHART}}}barChart") is not None
        ]

    assert len(bar_roots) == 3
    assert "Regime de colocação · número de ofertas" not in raw_text
    assert "Regime de colocação · participação no volume · % do total" in raw_text
    assert "Melhores esforços repr. 69,2% do volume em 2026" in raw_text

    regime_chart = next(
        root
        for root in bar_roots
        if len(root.findall(f".//{{{CHART}}}barChart/{{{CHART}}}ser")) == 3
    )
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

    assert any(
        node.text == "0.0%"
        for node in regime_chart.iter(f"{{{CHART}}}formatCode")
    )
    assert any(
        node.attrib.get("formatCode") == "0%"
        for node in regime_chart.iter(f"{{{CHART}}}numFmt")
    )


def test_taxonomy_rankings_use_one_legible_table_per_type_and_period() -> None:
    with ZipFile(PPTX) as archive:
        for slide_number in SLIDES_TOP_TYPE:
            text = _slide_text(archive, slide_number)
            assert len(_tables(archive, slide_number)) == 1
            assert "Top 15" in text
            assert any(period in text for period in ("jun/26", "dez/25"))
            assert "Cedente / originador" in text
