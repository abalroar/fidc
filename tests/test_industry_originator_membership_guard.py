"""Publication guard for an audited documentary gap within one competence."""

from copy import deepcopy
import json

import pytest

from scripts import publish_fidc_revision_bundle as publisher


TABLE = "Outros · 2026-09"
KEY = ("Outros", "originador", "2026-09")
REVIEW_NAME = "industry_top15_originator_cohort_review_202609.json"


@pytest.fixture
def audited_cohort(tmp_path):
    identities = [f"{value:014d}" for value in range(1, 16)]
    reason = publisher.COHORT_COVERAGE_WAIVERS[KEY]
    payload = {
        "latest_complete": "2026-09",
        "emission_field_coverage": [{
            "tabela": TABLE, "campo": "originador", "excecao_publicacao": reason,
        }],
        "top20_taxonomy_review": [
            {"competencia": "2026-09", "tipo_exibicao": "Outros", "rank_tipo": rank,
             "cnpj_fundo": cnpj, "pl": 1000 - rank}
            for rank, cnpj in enumerate(identities, 1)
        ],
        "emission_field_audit": [
            {"bloco": "slides 10–17", "tabela": TABLE, "cnpj": cnpj, "originador": "N/D"}
            for cnpj in identities
        ],
    }
    review = {
        "schema_version": 1,
        "specific_waiver": {
            "tipo": KEY[0], "campo": KEY[1], "competencia": KEY[2],
            "reason": reason, "prospective": False,
        },
        "cohorts": [{"tipo": "Outros", "cohorts": {
            "2026-09": [{"cnpj": cnpj} for cnpj in identities],
        }}],
    }
    path = tmp_path / REVIEW_NAME
    path.write_text(json.dumps(review))
    return payload, review, path


def test_exact_documentary_cohort_is_accepted_without_changing_payload(audited_cohort):
    payload, _, path = audited_cohort
    before = deepcopy(payload)
    publisher.validate_originator_cohort_membership(payload, data_dir=path.parent)
    assert payload == before


def test_same_month_retification_changing_a_member_requires_new_review(audited_cohort):
    payload, _, path = audited_cohort
    payload["top20_taxonomy_review"][-1]["cnpj_fundo"] = "99999999999999"
    payload["emission_field_audit"][-1]["cnpj"] = "99999999999999"
    with pytest.raises(publisher.RevisionBundlePublishError, match="coorte .* mudou; exige nova revisão documental"):
        publisher.validate_originator_cohort_membership(payload, data_dir=path.parent)


@pytest.mark.parametrize("surface", ["top20_taxonomy_review", "emission_field_audit"])
def test_rank_and_export_must_both_match_the_review(audited_cohort, surface):
    payload, _, path = audited_cohort
    key = "cnpj_fundo" if surface == "top20_taxonomy_review" else "cnpj"
    payload[surface][0][key] = "99999999999999"
    with pytest.raises(publisher.RevisionBundlePublishError, match="exige nova revisão documental"):
        publisher.validate_originator_cohort_membership(payload, data_dir=path.parent)


def test_value_and_rank_order_retifications_keep_the_reviewed_membership(audited_cohort):
    payload, _, path = audited_cohort
    payload["top20_taxonomy_review"].reverse()
    payload["emission_field_audit"].reverse()
    payload["top20_taxonomy_review"][0]["pl"] = 500000
    publisher.validate_originator_cohort_membership(payload, data_dir=path.parent)


def test_missing_review_blocks_only_the_documented_exception(audited_cohort):
    payload, _, path = audited_cohort
    path.unlink()
    with pytest.raises(publisher.RevisionBundlePublishError, match="ausente ou inválida"):
        publisher.validate_originator_cohort_membership(payload, data_dir=path.parent)
    payload["emission_field_coverage"][0]["excecao_publicacao"] = ""
    publisher.validate_originator_cohort_membership(payload, data_dir=path.parent)


@pytest.mark.parametrize("malformation", ["json", "schema", "waiver_period", "waiver_reason", "prospective"])
def test_invalid_or_mismatched_documentary_review_blocks_publication(audited_cohort, malformation):
    payload, review, path = audited_cohort
    if malformation == "json":
        path.write_text("{invalid json")
    else:
        if malformation == "schema":
            review["schema_version"] = 2
        elif malformation == "waiver_period":
            review["specific_waiver"]["competencia"] = "2026-08"
        elif malformation == "waiver_reason":
            review["specific_waiver"]["reason"] = "outro motivo"
        elif malformation == "prospective":
            review["specific_waiver"]["prospective"] = True
        path.write_text(json.dumps(review))
    with pytest.raises(publisher.RevisionBundlePublishError, match="ausente ou inválida"):
        publisher.validate_originator_cohort_membership(payload, data_dir=path.parent)


@pytest.mark.parametrize("malformation", ["duplicate", "missing", "invalid_cnpj"])
def test_review_requires_fifteen_unique_canonical_cnpjs(audited_cohort, malformation):
    payload, review, path = audited_cohort
    rows = review["cohorts"][0]["cohorts"]["2026-09"]
    if malformation == "duplicate":
        rows[-1] = deepcopy(rows[0])
    elif malformation == "missing":
        rows.pop()
    else:
        rows[-1]["cnpj"] = "14.000.000/0001-00"
    path.write_text(json.dumps(review))
    with pytest.raises(publisher.RevisionBundlePublishError, match="15 fundos|CNPJs inválidos ou repetidos"):
        publisher.validate_originator_cohort_membership(payload, data_dir=path.parent)


def test_reviewed_historical_table_is_checked_in_later_payloads(audited_cohort):
    payload, _, path = audited_cohort
    payload["latest_complete"] = "2026-10"
    publisher.validate_originator_cohort_membership(payload, data_dir=path.parent)
    payload["emission_field_audit"][0]["cnpj"] = "99999999999999"
    with pytest.raises(publisher.RevisionBundlePublishError, match="exige nova revisão documental"):
        publisher.validate_originator_cohort_membership(payload, data_dir=path.parent)


def test_other_competences_do_not_inherit_the_review(audited_cohort):
    payload, _, path = audited_cohort
    payload["emission_field_coverage"][0]["tabela"] = "Outros · 2026-10"
    path.unlink()
    # The normal coverage validator continues to reject an October zero floor.
    publisher.validate_originator_cohort_membership(payload, data_dir=path.parent)
