import json
from unittest.mock import patch

from scripts.report_documentary_diligence import acquisition_row, before_answers, build_report, coverage_row, reported_criteria, supported_not_applicable
from services.documentary_diligence import public_document_payload


def source():
    return {"document_id": "123456", "title": "Regulamento", "reference_date": "2026-01-01", "page": 3}


def item(key="allocation", **updates):
    return {"criterion_id": key, "label": "Alocação mínima", "theme": "Alocação", "applicability": "applicable", "status": "confirmed", "value": "50% do PL depois de 180 dias", "sources": [source()], "provenance": "primary_passage", **updates}


def test_missing_legacy_question_stays_in_paired_denominator():
    fund = {"cnpj": "1", "name": "A", "criteria": [item()]}
    row, criteria, excluded, answered, synthetic = coverage_row(fund, {"allocation": {}}, {}, registered=True)
    assert row["paired_denominator"] == 27
    assert row["paired_before_answered"] == 1 and row["paired_after_answered"] == 1
    assert "quota_grace" in synthetic
    assert row["pending"] == row["denominator"] - 1
    assert row["applicability_unresolved"] == row["denominator"] - 1


def test_not_applicable_without_source_is_never_excluded():
    unsupported = item("subordination", applicability="not_applicable", status="not_applicable", value=None, sources=[], reason="Cota única")
    assert not supported_not_applicable(unsupported)
    row, _criteria, excluded, _answered, _synthetic = coverage_row({"cnpj": "1", "criteria": [unsupported]}, {}, {}, registered=True)
    assert excluded == set() and row["documented_not_applicable"] == 0
    assert row["paired_denominator"] == 27
    supported = {**unsupported, "sources": [source()]}
    assert supported_not_applicable(supported)
    row, *_ = coverage_row({"cnpj": "1", "criteria": [supported]}, {}, {}, registered=True)
    assert row["paired_denominator"] == 26


def test_before_requires_substantive_value_and_same_primary_document():
    review = {"facts": {"comparison_mechanics": {"Alocação mínima": {"value": "50% do PL depois de 180 dias", "source": "Fundos.NET ID 123456 · 01/01/2026 · p. 3"}}}}
    docs = [{"id": 123456, "title": "Regulamento", "reference_date": "2026-01-01", "text_path": "data/text.txt",
             "url": "https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id=123456&cvm=true", "sha256": "a" * 64, "parse_status": "complete"}]
    assert set(before_answers(review, docs)) == {"allocation"}
    assert before_answers(review, []) == {}
    review["facts"]["comparison_mechanics"]["Alocação mínima"]["value"] = "Não localizado no corpus acessível"
    assert before_answers(review, docs) == {}


def test_before_coverage_is_identical_for_local_and_public_inventory():
    review = {"facts": {"comparison_mechanics": {"Alocação mínima": {"value": "50% do PL depois de 180 dias", "source": "Fundos.NET ID 123456 · 01/01/2026 · p. 3"}}}}
    document = {"id": 123456, "title": "Regulamento", "reference_date": "2026-01-01", "url": "https://example.org/regulamento.pdf",
                "sha256": "b" * 64, "parse_status": "complete", "local_path": "/Users/analista/regulamento.pdf", "text_path": "/Users/analista/texto.txt"}
    private_before = before_answers(review, [document])
    public_before = before_answers(review, public_document_payload([document]))
    assert set(private_before) == set(public_before) == {"allocation"}
    fund = {"cnpj": "1", "criteria": [item()]}
    assert coverage_row(fund, private_before, {}, registered=True)[0] == coverage_row(fund, public_before, {}, registered=True)[0]
    assert public_before["allocation"]["sources"][0]["verification"] == "historical_citation_reconstructed_current_collection"
    for missing in ("url", "sha256", "parse_status"):
        incomplete = {key: value for key, value in document.items() if key != missing}
        assert before_answers(review, [incomplete]) == {}
    assert before_answers(review, [{**document, "pages_total": 2}]) == {}
    assert set(before_answers(review, [{**document, "pages_total": 3}])) == {"allocation"}


def test_complete_physical_pages_do_not_count_as_readable_text():
    document = {"id": 123456, "download_status": "downloaded", "parse_status": "unreadable_text", "pages_total": 53, "pages_extracted": 53,
                "error": "text_character_map_corruption"}
    row = acquisition_row({"cnpj": "1"}, {"documents": [document]}, True)
    assert row["local_or_downloaded"] == 1
    assert row["complete_texts"] == 0 and row["parse_failed"] == 1 and row["unreadable_text"] == 1
    assert row["unreadable_text_label"] == "Texto ilegível por codificação do PDF"


def test_acquisition_csv_references_full_inventory_without_oversized_cells():
    documents = [{"id": number, "classification": "regulamento", "download_status": "downloaded", "parse_status": "complete", "excerpt": "evidência " * 1000} for number in range(400)]
    row = acquisition_row({"cnpj": "54871427000194"}, {"documents": documents}, True)
    assert row["documents_inventoried"] == row["local_or_downloaded"] == row["complete_texts"] == 400
    assert json.loads(row["document_counts_by_classification"]) == {"regulamento": 400}
    assert row["corpus_reference"] == "data/documentary_diligence/audit_corpus/54871427000194.json"
    assert "documents" not in row and max(len(str(value)) for value in row.values()) < 1000


def test_acceptance_report_includes_investee_ime_without_promoting_historical_position(tmp_path):
    parent, target = "54871427000194", "41970012000126"
    (tmp_path / "portfolios.json").write_text(json.dumps({"portfolios": [{"id": "p", "name": "FIC", "funds": [{"cnpj": parent, "display_name": "FIC"}]}]}))
    directory = tmp_path / "data/documentary_diligence/funds"
    directory.mkdir(parents=True)
    relation = {"cnpj": target, "label": "Investido", "status": "verified_position", "position_date": "2025-12-31", "current_position_confirmed": False}
    for cnpj in (parent, target):
        directory.joinpath(f"{cnpj}.json").write_text(json.dumps({"schema_version": 2, "cnpj": cnpj, "name": cnpj, "criteria": [item()], "lookthrough": [relation] if cnpj == parent else []}))
    reference = {"competence": "08/2026", "declared_count": 1, "available_count": 1, "missing_cnpjs": [], "warnings": []}
    def observations(fund, *, competence, cache_root):
        assert competence == "08/2026" and cache_root == tmp_path
        return [{"criterion_id": "allocation", "comparison_required": True, "status": "not_comparable", "competence": competence,
                 "context_value": 75, "context_unit": "percent", "source": {"cnpj": fund["cnpj"]}}]
    with patch("scripts.report_documentary_diligence.resolve_documentary_reference", return_value=reference), patch("scripts.report_documentary_diligence.build_documentary_observations", side_effect=observations):
        tables, summary = build_report(tmp_path)
    rows = tables["ime_comparisons.csv"]
    assert len(rows) == 2
    linked = next(row for row in rows if row["cnpj"] == target)
    assert linked["layer"] == "Vínculo de investimento" and linked["parent_cnpj"] == parent
    assert linked["position_date"] == "2025-12-31" and linked["current_position_confirmed"] is False
    assert summary["scope"]["registered_cnpjs"] == 1 and summary["scope"]["active_cnpjs_including_lookthrough"] == 2
