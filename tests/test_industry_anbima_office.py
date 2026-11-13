from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import posixpath
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import openpyxl
import pytest

from services.industry_revision_export import EXPECTED_SLIDE_IDS

DATA = Path(__file__).resolve().parents[1] / "data/industry_study/generated_revision"
PPTX = Path(os.environ.get("FIDC_TEST_PPTX", DATA / "industry_executive_revised.pptx"))
XLSX = Path(os.environ.get("FIDC_TEST_XLSX", DATA / "industry_data_revised.xlsx"))
PAYLOAD = Path(os.environ.get("FIDC_TEST_PAYLOAD", DATA / "artifact_payload.json"))
NS = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


def charts(archive, topic):
    number = EXPECTED_SLIDE_IDS.index(topic) + 1
    relationships = ET.fromstring(archive.read(f"ppt/slides/_rels/slide{number}.xml.rels"))
    result = []
    for rel in relationships:
        if rel.attrib["Type"].endswith("/chart"):
            target = rel.attrib["Target"]
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("ppt/slides", target))
            result.append(ET.fromstring(archive.read(path)))
    return result


def chart_values(chart):
    series = chart.find(".//c:ser", NS)
    labels = series.findall("c:cat//c:pt/c:v", NS)
    values = series.findall("c:val//c:pt/c:v", NS)
    return {label.text: float(value.text) for label, value in zip(labels, values, strict=True)}


def table_rows(archive, topic):
    number = EXPECTED_SLIDE_IDS.index(topic) + 1
    root = ET.fromstring(archive.read(f"ppt/slides/slide{number}.xml"))
    return [[" ".join(node.text or "" for node in cell.findall(".//a:t", NS))
             for cell in row.findall("a:tc", NS)] for row in root.findall(".//a:tbl/a:tr", NS)]


def br_number(text):
    return float(text.replace("R$", "").replace("bi", "").replace("%", "").strip().replace(".", "").replace(",", "."))


def test_native_anbima_sector_charts_match_annex_volume_and_denominator():
    payload = json.loads(PAYLOAD.read_text())["anbima_analysis"]
    with ZipFile(PPTX) as archive:
        amount, share = charts(archive, "anbima_sectors")
        amounts, shares = chart_values(amount), chart_values(share)
    for row in payload["fidc_sectors"]:
        assert amounts[row["category"]] == pytest.approx(row["volume_brl"]/1e9)
        assert shares[row["category"]] == pytest.approx(row["share"])
    assert sum(shares.values()) == pytest.approx(1)


def test_top15_anbima_native_tables_keep_all_registrations_and_credited_volumes():
    payload = json.loads(PAYLOAD.read_text())["anbima_analysis"]
    with ZipFile(PPTX) as archive:
        rows = table_rows(archive, "top15_anbima_1")[1:] + table_rows(archive, "top15_anbima_2")[1:]
    assert len(rows) == 15
    for actual, expected in zip(rows, payload["fidc_top15"], strict=True):
        assert int(actual[0]) == expected["rank"]
        assert actual[2] == expected["registro_cvm"]
        assert br_number(actual[3]) == pytest.approx(expected["volume_brl"]/1e9, abs=0.0051)
        assert br_number(actual[5]) == pytest.approx(expected["ibba_volume_brl"]/1e9, abs=0.0051)


def test_native_anbima_rankings_preserve_both_official_windows():
    payload = json.loads(PAYLOAD.read_text())["anbima_analysis"]
    with ZipFile(PPTX) as archive:
        for topic, scope in [("anbima_ranking", "Renda fixa"), ("anbima_fidc_ranking", "FIDC")]:
            native = charts(archive, topic)
            assert len(native) == 4
            for index, (window, role) in enumerate([(window, role) for window in ["acumulado_ano", "ultimos_12_meses"] for role in ["Originação", "Distribuição"]]):
                expected = next(row for row in payload["ranking_all"] if row["scope"] == scope and row["window"] == window and row["role"] == role and row["participant"] == "ITAU BBA")
                assert chart_values(native[index])["ITAU BBA"] == pytest.approx(expected["volume_brl"]/1e9)


def test_market_top15_native_tables_preserve_all_fifteen_operations():
    payload = json.loads(PAYLOAD.read_text())["anbima_analysis"]
    with ZipFile(PPTX) as archive:
        rows = table_rows(archive, "top15_anbima_market_1")[1:] + table_rows(archive, "top15_anbima_market_2")[1:]
    assert len(rows) == 15
    for actual, expected in zip(rows, payload["market_top15"], strict=True):
        assert int(actual[0]) == expected["rank"]
        assert actual[1] == expected["emissor"]
        assert br_number(actual[4]) == pytest.approx(expected["volume_brl"]/1e9, abs=0.0051)
        assert br_number(actual[6]) == pytest.approx(expected["ibba_volume_brl"]/1e9, abs=0.0051)


def test_general_and_independent_provider_charts_keep_kanastra_and_itau_separate():
    payload = json.loads(PAYLOAD.read_text())
    with ZipFile(PPTX) as archive:
        native = charts(archive, "provider_history")
    assert len(native) == 6
    for index, role in enumerate(["administrador", "gestor", "custodiante"]):
        general, independent = chart_values(native[index*2]), chart_values(native[index*2+1])
        for name in ["Itaú", "Kanastra"]:
            row = next(row for row in payload["provider_historical_ranking"] if row["competencia"] == payload["latest_complete"] and row["papel"] == role and row["participante"] == name)
            assert general[name] == pytest.approx(row["pl_brl"]/1e9)
        assert "Kanastra" in independent
        assert "Itaú" not in independent


def test_anbima_workbook_reconciles_and_keeps_share_formulas_and_missing_data():
    payload = json.loads(PAYLOAD.read_text())["anbima_analysis"]
    source = XLSX.read_bytes()
    book = openpyxl.load_workbook(BytesIO(source), read_only=True, data_only=True)
    formulas = openpyxl.load_workbook(BytesIO(source), read_only=True, data_only=False)
    sectors = list(book["ANBIMA Setores"].iter_rows(min_row=5, values_only=True))
    assert sum(row[1] for row in sectors) == pytest.approx(payload["fidc_summary"]["volume_brl"], abs=0.01)
    assert sum(row[2] for row in sectors) == pytest.approx(1)
    assert formulas["ANBIMA Setores"]["C5"].data_type == "f"
    assert formulas["ANBIMA Produtos"]["E5"].data_type == "f"
    deals = list(book["ANBIMA Emissões FIDC"].iter_rows(min_row=5, values_only=True))
    assert len(deals) == payload["fidc_summary"]["registrations"]
    assert len({row[0] for row in deals}) == len(deals)
    assert all(isinstance(row[1], str) and len(row[1]) == 14 for row in deals)
    assert sum(row[5] for row in deals) == pytest.approx(payload["fidc_summary"]["volume_brl"], abs=0.01)
    missing = [row for row in book["ANBIMA IBBA"].iter_rows(min_row=5, values_only=True) if row[0] == "Empresas ligadas" and row[1] == "Distribuição"]
    assert len(missing) == 2
    assert all(value in (None, "N/D") for row in missing for value in row[2:6])
    market = list(book["ANBIMA Operações"].iter_rows(min_row=5, values_only=True))
    assert len(market) == payload["market_summary"]["operations"]
    assert sum(row[5] for row in market) == pytest.approx(payload["market_summary"]["volume_brl"], abs=0.01)
    ranking = list(book["ANBIMA Ranking"].iter_rows(min_row=5, values_only=True))
    assert len(ranking) == len(payload["ranking_all"])
    assert {row[7] for row in ranking} == {"Acumulado no ano", "Últimos 12 meses"}
    book.close()
    formulas.close()
