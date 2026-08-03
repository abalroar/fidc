"""Semantic contract for the compact, self-contained provider-flow HTML."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

from services.industry_revision_export import validate_revision_html


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_PATH = Path(
    os.environ.get(
        "FIDC_TEST_PAYLOAD",
        ROOT / "data" / "industry_study" / "generated_revision" / "artifact_payload.json",
    )
)
BUILDER_PATH = ROOT / "scripts" / "build_provider_flow_explorer.mjs"
MAX_COMPACT_HTML_BYTES = 480_000
EXPECTED_PAYLOAD_KEYS = {
    "carteira_1_flagship_comparison",
    "carteira_1_flagship_comparison_summary",
    "carteira_1_curation",
    "carteira_1_curation_ranges",
    "carteira_1_curation_summary",
    "carteira_1_structural_summary",
    "carteira_1_taxonomy_history",
    "carteira_1_taxonomy_summary",
    "flagship_curation",
    "flagship_curation_summary",
    "flagship_families",
    "issuance_taxonomy_reconciliation",
    "issuance_taxonomy_table",
    "latest_complete",
    "portfolio_export_carteira_101",
    "portfolio_export_flagships",
    "provider_history_cvm_coverage",
    "provider_history_cvm_detail",
    "provider_history_cvm_links",
    "provider_transition_detail",
    "provider_transition_links",
    "provider_transition_summary",
    "reag_admin_detail",
    "reag_admin_summary",
    "taxonomy_level_history",
}


def _embedded_data(document: str) -> dict[str, object]:
    match = re.search(
        r'<script type="application/json" id="provider-flow-data">'
        r"(.*?)</script>",
        document,
        flags=re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_provider_flow_builder_keeps_the_declared_payload_contract() -> None:
    source = BUILDER_PATH.read_text(encoding="utf-8")
    payload_keys = set(
        re.findall(
            r"\bpayload\.([A-Za-z_$][A-Za-z0-9_$]*)",
            source,
        )
    )
    assert payload_keys == EXPECTED_PAYLOAD_KEYS


def test_compact_provider_flow_html_preserves_values_and_absence(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "provider_flows_explorer.html"
    completed = subprocess.run(
        [
            "node",
            str(BUILDER_PATH),
            "--payload",
            str(PAYLOAD_PATH),
            "--html",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

    payload = output_path.read_bytes()
    validate_revision_html(payload)
    assert len(payload) < MAX_COMPACT_HTML_BYTES
    document = payload.decode("utf-8")
    assert "fetch(" not in document
    assert "provider_flow_compact_v1" in document
    assert "JSON.stringify(expanded) não preservou o view-model" not in document

    compact = _embedded_data(document)
    assert compact["schemaVersion"] == "provider_flow_compact_v1"
    assert compact["taxonomy"]["schemaVersion"] == "taxonomy_levels_compact_v1"
    assert compact["flagships"]["schemaVersion"] == "flagship_curation_compact_v2"
    assert compact["carteira1"]["schemaVersion"] == "carteira_1_curation_compact_v4"
    assert compact["carteira1Taxonomy"]["schemaVersion"] == "carteira_1_taxonomy_compact_v1"
    assert len(compact["carteira1Taxonomy"]["rows"]) == 16
    assert compact["issuanceTaxonomy"]["schemaVersion"] == "issuance_taxonomy_table_v1"
    assert len(compact["issuanceTaxonomy"]["rows"]) == 7
    source_payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
    assert len(compact["taxonomy"]["rows"]) == len(
        source_payload["taxonomy_level_history"]
    )
    assert len(compact["flagships"]["families"]) == 26
    assert len(compact["flagships"]["details"]) == 47
    flagship_fields = compact["flagships"]["fields"]["detail"]
    assert {
        "originator",
        "cedente",
        "cedenteOriginator",
        "partyRole",
        "debtor",
        "receivable",
        "partiesSource",
        "minJuniorLiteral",
        "minJuniorCalculated",
        "minJuniorAdjusted",
        "supportTotal",
        "supportCombined",
        "structuralMinimum",
        "structuralDisplay",
        "structuralNature",
        "structuralFormula",
        "structuralComparable",
        "structuralComparableReason",
        "exceptionAsterisk",
        "structuralHeadroom",
        "lossAbsorption",
        "regulatoryStatus",
        "priceBrl",
        "priceDisplay",
        "priceNature",
        "priceClassSeries",
        "priceDocumentDate",
        "priceDocumentId",
        "priceSource",
        "priceStatus",
        "priceExceptionAsterisk",
        "completionStatus",
        "gaps",
        "documentId",
        "documentDate",
        "page",
        "curationStatus",
        "documentarySource",
        "minimumText",
    } <= set(flagship_fields)
    assert {
        "quantidade_cotas",
        "quantidade",
        "spread",
        "remuneracao",
    }.isdisjoint(flagship_fields)
    flagship_cnpj_index = flagship_fields.index("cnpj")
    flagship_pl_index = flagship_fields.index("pl")
    flagship_ratio_index = flagship_fields.index("ratio")
    flagship_originator_index = flagship_fields.index("originator")
    compact_flagship_rows = {
        row[flagship_cnpj_index]: row for row in compact["flagships"]["details"]
    }
    canonical_flagship_rows = {
        row["cnpj_formatado"]: row
        for row in source_payload["portfolio_export_flagships"]
    }
    legacy_flagship_cnpjs = {
        row["cnpj_fundo_formatado"]
        for row in source_payload["flagship_curation"]
    }
    family_flagship_cnpjs = {
        cnpj.strip()
        for row in source_payload["flagship_families"]
        for cnpj in row["cnpjs"].split(";")
    }
    assert len(canonical_flagship_rows) == 47
    assert set(compact_flagship_rows) == set(canonical_flagship_rows)
    assert set(compact_flagship_rows) == legacy_flagship_cnpjs
    assert set(compact_flagship_rows) == family_flagship_cnpjs
    for cnpj, source_row in canonical_flagship_rows.items():
        compact_row = compact_flagship_rows[cnpj]
        assert compact_row[flagship_pl_index] == source_row["pl_atual_brl"]
        assert compact_row[flagship_ratio_index] == source_row["sub_pl_atual"]
        assert compact_row[flagship_originator_index] == source_row["originador"]
    assert len(compact["carteira1"]["ranges"]) == 7
    assert len(compact["carteira1"]["details"]) == 101
    assert compact["carteira1"]["summary"]["minJunior"] == 83
    assert compact["carteira1"]["summary"]["minStructural"] == 99
    assert len(compact["carteira1"]["comparison"]) == 7
    assert compact["carteira1"]["comparisonSummary"]["flagshipFunds"] == 47
    assert compact["carteira1"]["comparisonSummary"]["classified"] == 100
    carteira_fields = compact["carteira1"]["fields"]["detail"]
    assert {
        "originator",
        "cedente",
        "cedenteOriginator",
        "debtor",
        "receivable",
        "partiesSource",
        "minJuniorLiteral",
        "minJuniorCalculated",
        "minJuniorAdjusted",
        "supportTotal",
        "supportCombined",
        "structuralMinimum",
        "structuralNature",
        "structuralHeadroom",
        "lossAbsorption",
        "marketPosition",
        "marketExcess",
        "benchmarkReliable",
        "marketPeers",
        "mvpCategory",
        "mvpRange",
        "mvpEligible",
        "mvpFloorStatus",
        "priceBrl",
        "priceDisplay",
        "priceNature",
        "priceClassSeries",
        "priceDocumentDate",
        "priceDocumentId",
        "priceSource",
        "priceStatus",
        "priceExceptionAsterisk",
        "completionStatus",
        "gaps",
    } <= set(carteira_fields)
    assert {
        "quantidade_cotas",
        "quantidade",
        "spread",
        "remuneracao",
    }.isdisjoint(carteira_fields)
    carteira_cnpj_index = carteira_fields.index("cnpj")
    carteira_pl_index = carteira_fields.index("pl")
    carteira_ratio_index = carteira_fields.index("ratio")
    canaa = next(
        row
        for row in compact["carteira1"]["details"]
        if row[carteira_cnpj_index] == "45.123.558/0001-00"
    )
    assert canaa[carteira_pl_index] is None
    assert canaa[carteira_ratio_index] is None
    fields = compact["fields"]
    views = compact["views"]
    assert set(views) == {"admin", "gestor", "custodiante", "reag"}
    assert {
        view: (len(data["links"]), len(data["details"]))
        for view, data in views.items()
    } == {
        "admin": (135, 348),
        "gestor": (2, 3),
        "custodiante": (0, 0),
        "reag": (9, 126),
    }

    # Custody is an observed zero under limited coverage.  It remains numeric.
    assert views["custodiante"]["summary"]["primary"] == 0
    assert views["custodiante"]["summary"]["secondary"] == 0

    cohort_fields = fields["cohortDetail"]
    current_pl_index = cohort_fields.index("pl1")
    current_values = [
        row[current_pl_index]
        for row in views["reag"]["details"]
    ]
    assert current_values.count(None) == 36
    assert current_values.count(0) == 0
    cohort_link_fields = fields["cohortLink"]
    target_index = cohort_link_fields.index("target")
    link_current_index = cohort_link_fields.index("current")
    missing_report_link = next(
        row
        for row in views["reag"]["links"]
        if row[target_index] == "Sem reporte"
    )
    assert missing_report_link[link_current_index] is None

    # The browser renders missing destination PL as a dash and CSV serialization
    # receives null, which the existing quote function emits as an empty cell.
    assert 'r.pl1==null?"—":money(r.pl1)' in document
    assert 'l.current==null?"sem PL reportado em "' in document
    assert 'String(v??"")' in document
    assert 'value == null || value === ""' in document
    assert '${money(row.pl)}' in document
    assert '${pct(row.ratio)}' in document
    assert "Preço unitário por cota" in document
    assert "Originador / cedente / sacado / recebível" in document
    assert "preco_cota_display" in document
    assert "preco_cota_classe_serie" in document
    assert "preco_cota_excecao_asterisco" in document
    assert "mvp_slide_categoria" in document
    assert "mvp_faixa_sub_atual" in document
    assert "mvp_elegivel_flag" in document
    assert "mvp_situacao_piso" in document
    assert "data-c1-mvp-category" in document
    assert "data-c1-eligibility" in document
    assert "quantidade_cotas" not in document


def test_flagship_detail_prefers_the_canonical_export_by_cnpj(
    tmp_path: Path,
) -> None:
    source_payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
    canonical = source_payload["portfolio_export_flagships"][0]
    cnpj = canonical["cnpj_formatado"]
    canonical.update(
        {
            "originador": "Originador canônico",
            "cedente": "Cedente canônico",
            "sacado_devedor": "Sacado canônico",
            "tipo_recebivel_literal": "Recebível canônico",
            "minimo_junior_literal": 0.1234,
            "minimo_estrutural_usado": 0.1234,
            "minimo_estrutural_display": "12,34% do PL",
            "folga_pp": 0.0456,
            "situacao_regulatoria": "acima do mínimo",
            "preco_cota_brl": 1_234.56,
            "preco_cota_display": "R$ 1.234,56",
            "preco_cota_natureza": "valor unitário de emissão",
            "preco_cota_classe_serie": "2ª série sênior",
            "preco_cota_documento_data": "2026-06-30",
            "preco_cota_documento_id": "DOC-CANONICO",
            "preco_cota_fonte": "https://example.test/preco-canonico",
            "preco_cota_status": "localizado documentalmente",
            "preco_cota_excecao_asterisco_flag": True,
        }
    )
    legacy = next(
        row
        for row in source_payload["flagship_curation"]
        if row["cnpj_fundo_formatado"] == cnpj
    )
    legacy["preco_emissao_display"] = "VALOR LEGADO"
    legacy["preco_emissao_classe"] = "CLASSE LEGADA"
    payload_path = tmp_path / "artifact_payload.json"
    output_path = tmp_path / "provider_flows_explorer.html"
    payload_path.write_text(
        json.dumps(source_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "node",
            str(BUILDER_PATH),
            "--payload",
            str(payload_path),
            "--html",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

    compact = _embedded_data(output_path.read_text(encoding="utf-8"))["flagships"]
    fields = compact["fields"]["detail"]
    detail = next(
        dict(zip(fields, row, strict=True))
        for row in compact["details"]
        if row[fields.index("cnpj")] == cnpj
    )
    assert detail["originator"] == "Originador canônico"
    assert detail["cedente"] == "Cedente canônico"
    assert detail["debtor"] == "Sacado canônico"
    assert detail["receivable"] == "Recebível canônico"
    assert detail["minJuniorLiteral"] == 0.1234
    assert detail["structuralMinimum"] == 0.1234
    assert detail["structuralHeadroom"] == 0.0456
    assert detail["regulatoryStatus"] == "acima do mínimo"
    assert detail["priceBrl"] == 1_234.56
    assert detail["priceDisplay"] == "R$ 1.234,56"
    assert detail["priceNature"] == "valor unitário de emissão"
    assert detail["priceClassSeries"] == "2ª série sênior"
    assert detail["priceDocumentDate"] == "2026-06-30"
    assert detail["priceDocumentId"] == "DOC-CANONICO"
    assert detail["priceSource"] == "https://example.test/preco-canonico"
    assert detail["priceExceptionAsterisk"] is True
    assert "VALOR LEGADO" not in detail.values()
    assert "CLASSE LEGADA" not in detail.values()


def test_carteira1_mvp_fields_flow_to_model_filters_and_csv(
    tmp_path: Path,
) -> None:
    source_payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
    canonical = source_payload["portfolio_export_carteira_101"][0]
    cnpj = canonical["cnpj_formatado"]
    canonical.update(
        {
            "mvp_slide_categoria": "Financeiro",
            "mvp_faixa_sub_atual": "20%–35%",
            "mvp_elegivel_flag": True,
            "mvp_situacao_piso": "acima do piso",
        }
    )
    payload_path = tmp_path / "artifact_payload.json"
    output_path = tmp_path / "provider_flows_explorer.html"
    payload_path.write_text(
        json.dumps(source_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "node",
            str(BUILDER_PATH),
            "--payload",
            str(payload_path),
            "--html",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

    document = output_path.read_text(encoding="utf-8")
    compact = _embedded_data(document)["carteira1"]
    fields = compact["fields"]["detail"]
    details = [dict(zip(fields, row, strict=True)) for row in compact["details"]]
    detail = next(row for row in details if row["cnpj"] == cnpj)
    assert len(details) == 101
    assert detail["mvpCategory"] == "Financeiro"
    assert detail["mvpRange"] == "20%–35%"
    assert detail["mvpEligible"] is True
    assert detail["mvpFloorStatus"] == "acima do piso"
    assert 'state.eligibility === "eligible" && !row.mvpEligible' in document
    assert 'row.mvpCategory !== state.mvpCategory' in document
    assert "Taxonomia / MVP" in document
