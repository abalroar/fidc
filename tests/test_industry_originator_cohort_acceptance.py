"""Acceptance checks for the documentary cohort actually exported in Sep/26.

The source guard is competence-specific.  These checks additionally detect a
later official retification that changes the members within the same month.
"""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from services.emission_field_enrichment import is_missing


DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"
REVIEW_NAME = "industry_top15_originator_cohort_review_202609.json"
TABLE = "Outros · 2026-09"


@pytest.fixture(scope="module")
def september_export() -> tuple[dict, dict]:
    payload = json.loads((DATA_DIR / "generated_revision" / "artifact_payload.json").read_text())
    if payload["latest_complete"] != "2026-09":
        pytest.skip("A página atual não usa a exceção documental de set/26.")
    review = json.loads((DATA_DIR / REVIEW_NAME).read_text())
    return payload, review


def _assert_frozen_outros_membership(payload: dict, review: dict) -> None:
    cohort = next(row for row in review["cohorts"] if row["tipo"] == "Outros")
    audited = {row["cnpj"] for row in cohort["cohorts"]["2026-09"]}
    assert len(audited) == 15
    rankings = [
        row for row in payload["top20_taxonomy_review"]
        if row["competencia"] == "2026-09"
        and row["tipo_exibicao"] == "Outros"
        and int(row["rank_tipo"]) <= 15
    ]
    actual_ranked = {str(row["cnpj_fundo"]) for row in rankings}
    assert len(rankings) == 15
    assert actual_ranked == audited, (
        "Coorte Outros set/26 mudou; exige nova revisão documental: "
        f"entraram={sorted(actual_ranked - audited)}, saíram={sorted(audited - actual_ranked)}"
    )
    exported = [
        row for row in payload["emission_field_audit"]
        if row["bloco"] == "slides 10–17" and row["tabela"] == TABLE
    ]
    assert len(exported) == 15
    assert {str(row["cnpj"]) for row in exported} == audited
    assert all(is_missing(row["originador"]) for row in exported)
    coverage = next(
        row for row in payload["emission_field_coverage"]
        if row["tabela"] == TABLE and row["campo"] == "originador"
    )
    assert coverage["depois_com_dado"] == 0
    assert coverage["nd_depois"] == 15
    assert coverage["depois_cobertura_pct"] == 0.0
    assert coverage["depois_pl_coberto_brl"] == 0.0
    assert coverage["excecao_publicacao"] == review["specific_waiver"]["reason"]


def test_exported_outros_september_members_match_the_documentary_review(september_export) -> None:
    payload, review = september_export
    _assert_frozen_outros_membership(payload, review)


def test_same_month_membership_retification_requires_another_review(september_export) -> None:
    payload, review = september_export
    changed = deepcopy(payload)
    row = next(
        row for row in changed["top20_taxonomy_review"]
        if row["competencia"] == "2026-09"
        and row["tipo_exibicao"] == "Outros"
        and int(row["rank_tipo"]) == 15
    )
    row["cnpj_fundo"] = "00000000000001"
    with pytest.raises(AssertionError, match="exige nova revisão documental"):
        _assert_frozen_outros_membership(changed, review)


def test_opi_gooroo_export_uses_its_explicit_originator_document_only_for_that_role(
    september_export,
) -> None:
    payload, review = september_export
    source = next(row for row in review["primary_document_reviews"]
                  if row["cnpj"] == "51295720000162")
    evidence = [
        row for row in payload["emission_field_taxonomy_party_evidence"]
        if str(row["cnpj"]) == "51295720000162" and str(row["source_id"]) == source["document_id"]
    ]
    assert len(evidence) == 1
    assert evidence[0]["field"] == "originador"
    assert evidence[0]["status"] == "encontrado_explicito"
    assert evidence[0]["source_url"] == source["source_url"]
    assert evidence[0]["document_date"] == source["reference_date"]
    assert "GOOROO CRÉDITO E COBRANÇA LTDA." in evidence[0]["value"]
    assert "43.732.242/0001-82" in evidence[0]["value"]
    exported = [
        row for row in payload["emission_field_audit"]
        if row["bloco"] == "slides 10–17"
        and row["tabela"] == "Fomento Mercantil · 2026-09"
        and str(row["cnpj"]) == "51295720000162"
    ]
    assert len(exported) == 1
    row = exported[0]
    assert row["originador"] == evidence[0]["value"]
    assert source["document_id"] in row["fonte_originador"]
    assert source["reference_date"] in row["fonte_originador"]
    assert "GOOROO" not in str(row["cedente"]).upper()
    assert source["document_id"] not in row["fonte_cedente"]
