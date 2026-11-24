"""Expose nominal groups consistently in the site and native current-offer tables."""
from __future__ import annotations

import ast
from copy import deepcopy
import json
import os
import posixpath
from pathlib import Path
import re
import shutil
import subprocess
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from services.industry_comparative_period import ComparisonCut
from services.industry_revision_export import EXPECTED_SLIDE_IDS

ROOT = Path(os.environ.get("FIDC_QUALIFICATION_ROOT", Path(__file__).resolve().parents[1]))
DATA = Path(os.environ.get("FIDC_QUALIFICATION_DATA_DIR", ROOT / "data/industry_study"))
PPTX = Path(os.environ.get("FIDC_TEST_PPTX", DATA / "generated_revision/industry_executive_revised.pptx"))
PAYLOAD = Path(os.environ.get("FIDC_TEST_PAYLOAD", DATA / "generated_revision/artifact_payload.json"))
NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


def _python_label(row):
    # Exercise the real small UI helper without importing a second full tab module.
    tree = ast.parse((ROOT / "tabs/tab_industry_study.py").read_text())
    helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_revision_offer_originator_label")
    scope = {"pd": pd}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "real-ui-helper", "exec"), scope)
    return scope[helper.name](row)


def _js_labels(rows):
    source = (ROOT / "scripts/build_fidc_revision_artifacts.mjs").read_text()
    helper = re.search(r"function offerOriginatorDisplay\(row\) \{.*?\n\}", source, re.S)
    assert helper is not None
    node = shutil.which("node")
    assert node, "The normal artifact build requires Node.js"
    result = subprocess.run([node, "-e", helper.group(0) + "\nprocess.stdout.write(JSON.stringify(JSON.parse(process.argv[1]).map(offerOriginatorDisplay)));", json.dumps(rows)],
                            capture_output=True, text=True, check=True, timeout=15)
    return json.loads(result.stdout)


def test_nominal_group_is_qualified_even_when_an_unrelated_closing_document_exists():
    rows = [
        {"originator_group": "Banco Santander", "originator_source": "campo_1",
         "originator_evidence": r"campo_1: \\bSANTANDER\\s+AUTO\\b",
         "closing_document_url": "https://web.cvm.gov.br/sre-publico-cvm/rest/download/example",
         "originator_evidence_document": "Classificação nominal preexistente; não revisada nesta rodada documental.",
         "review_status": "revisado"},
        {"originator_group": "Mercado Pago / Mercado Crédito", "originator_source": "campo_2"},
        {"originator_group": "Grupo nominal", "originator_source": "nome_emissor"},
        {"originator_group": "Grupo em curadoria", "originator_evidence_document": "Vínculo nominal requer leitura conjunta da oferta."},
        {"originator_group": "Grupo por regex", "originator_evidence": r"\\bGRUPO\\b"},
    ]
    before = deepcopy(rows)
    expected = [f"{row['originator_group']} (inferido)" for row in rows]
    assert [_python_label(row) for row in rows] == _js_labels(rows) == expected
    assert rows == before


def test_missing_and_documentary_values_are_preserved_without_reassigning_legal_entities():
    rows = [
        {"originator_group": value, "originator_source": "campo_1"}
        for value in ("N/D", "Não identificado", "Não identificado · crédito consignado")
    ] + [{"originator_group": "Originador documental S.A. (CNPJ 00.000.000/0001-00)",
          "originator_source": "curadoria_documental",
          "originator_evidence_document": "Documento da oferta, 01/09/2026, p.5: entidade que concede os créditos."}]
    expected = [row["originator_group"] for row in rows]
    assert [_python_label(row) for row in rows] == _js_labels(rows) == expected
    assert _python_label({"originator_group": pd.NA}) == "N/D"
    assert _js_labels([{"originator_group": None}]) == ["N/D"]


def test_real_santander_offer_is_an_inferred_group_and_october_stock_evidence_is_not_backdated():
    payload = json.loads(PAYLOAD.read_text())
    candidates = [row for row in payload["closed_offer_top15"] if str(row["offer_id"]) == "27585"]
    if candidates:
        row = candidates[0]
    else:
        # The historical offer need not remain among the current Top 15.
        offers = pd.read_csv(DATA / "industry_offers.csv.gz", dtype=str, keep_default_na=False)
        source = offers[offers["offer_id"].eq("27585")]
        assert len(source) == 1
        row = source.iloc[0].to_dict()
        row["data_encerramento"] = row["closing_date"]
    before = deepcopy(row)
    assert row["data_encerramento"] == "2026-09-08"
    assert row["originator_source"] == "campo_1"
    assert _python_label(row) == _js_labels([row])[0] == "Banco Santander (inferido)"
    assert row == before
    assert not row.get("originator_evidence_document")
    assert "07.707.650/0001-10" not in _python_label(row)


def test_offer_ui_discloses_nominal_source_at_the_cell_and_caption():
    cut = ComparisonCut(2026, 10)
    row = {field: "N/D" for field in ("leader_name", "ibba_participant_label", "firm_commitment_label", "publico", "investor_categories", "coordinator_entities", "rating_agency", "rating_assigned")}
    row.update(fund_name_short="Santander Auto Loans II", originator_group="Banco Santander", originator_source="campo_1",
               period_label=cut.period_id(), rank=1, registered_volume_brl=1e9, investor_count=0)
    payload = {"latest_complete": cut.competence, "offers_comparison_meta": cut.to_meta(),
               "closed_offer_top15": [row], "closed_offer_top15_summary": [{
                   "period_label": cut.period_id(), "period_order": 5, "period_end": cut.period_end.isoformat(),
                   "top15_offers": 1, "top15_registered_volume_brl": 1e9, "top15_share_of_period_volume": 1,
                   "ibba_lead_offers_top15": 0, "ibba_participation_offers_top15": 0}]}
    program = f'''import importlib.util
spec = importlib.util.spec_from_file_location("candidate_offer_tab", {str(ROOT / "tabs/tab_industry_study.py")!r})
tab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tab)
tab._render_revision_issuance_taxonomy = lambda *_: None
tab._render_revision_offers({payload!r})
'''
    app = AppTest.from_string(program, default_timeout=60).run()
    assert not app.exception and not app.error
    table = next(item.value for item in app.dataframe if "Originador / grupo" in item.value.columns)
    assert table.iloc[0]["Originador / grupo"] == "Banco Santander (inferido)"
    assert table.iloc[0]["Rating"] == "N/D" and table.iloc[0]["Nº de Inv."] == "0"
    assert any("Grupos por nome são inferidos" in item.value for item in app.caption)


def test_native_ppt_offer_cells_and_source_note_match_their_source_nature():
    payload = json.loads(PAYLOAD.read_text())
    current = payload["offers_comparison_meta"]["current_period_id"]
    expected = sorted((row for row in payload["closed_offer_top15"] if row["period_label"] == current), key=lambda row: int(row["rank"]))
    native_rows = []
    with ZipFile(PPTX) as archive:
        for topic in ("top15_cvm_1", "top15_cvm_2"):
            number = EXPECTED_SLIDE_IDS.index(topic) + 1
            slide_part = f"ppt/slides/slide{number}.xml"
            root = ET.fromstring(archive.read(slide_part))
            rows = [[" ".join(node.text or "" for node in cell.findall(".//a:t", NS))
                     for cell in row.findall("a:tc", NS)] for row in root.findall(".//a:tbl/a:tr", NS)]
            assert rows[0][2] == "Originador / grupo"
            native_rows.extend(rows[1:])
            visible = " ".join(node.text or "" for node in root.findall(".//a:t", NS))
            # addSourceNotes stores source provenance in the real speaker-note
            # part; the inference qualifier remains visible in every table cell.
            relationships = ET.fromstring(archive.read(
                f"ppt/slides/_rels/slide{number}.xml.rels"
            ))
            note_relation = next(item for item in relationships if
                item.attrib.get("Type", "").endswith("/notesSlide"))
            note_part = posixpath.normpath(posixpath.join(
                posixpath.dirname(slide_part), note_relation.attrib["Target"],
            )).lstrip("/")
            notes = ET.fromstring(archive.read(note_part))
            source_note = " ".join(node.text or "" for node in notes.findall(".//a:t", NS))
            assert "Grupos por nome são inferidos" in source_note
            assert "Rating e originador seguem a evidência documental datada" not in f"{visible} {source_note}"
    assert len(native_rows) == len(expected) == 15
    for actual, row in zip(native_rows, expected, strict=True):
        assert int(actual[0]) == row["rank"]
        assert actual[2] == _python_label(row)
