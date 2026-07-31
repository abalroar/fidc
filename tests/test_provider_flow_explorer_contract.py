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
MAX_COMPACT_HTML_BYTES = 400_000
EXPECTED_PAYLOAD_KEYS = {
    "carteira_1_curation",
    "carteira_1_curation_ranges",
    "carteira_1_curation_summary",
    "carteira_1_taxonomy_history",
    "carteira_1_taxonomy_summary",
    "flagship_curation",
    "flagship_curation_summary",
    "flagship_families",
    "issuance_taxonomy_reconciliation",
    "issuance_taxonomy_table",
    "latest_complete",
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
    assert compact["flagships"]["schemaVersion"] == "flagship_curation_compact_v1"
    assert compact["carteira1"]["schemaVersion"] == "carteira_1_curation_compact_v1"
    assert compact["carteira1Taxonomy"]["schemaVersion"] == "carteira_1_taxonomy_compact_v1"
    assert len(compact["carteira1Taxonomy"]["rows"]) == 16
    assert compact["issuanceTaxonomy"]["schemaVersion"] == "issuance_taxonomy_table_v1"
    assert len(compact["issuanceTaxonomy"]["rows"]) == 7
    assert len(compact["taxonomy"]["rows"]) == 358
    assert len(compact["flagships"]["families"]) == 26
    assert len(compact["flagships"]["details"]) == 47
    flagship_fields = compact["flagships"]["fields"]["detail"]
    assert {
        "documentId",
        "documentDate",
        "page",
        "pagesRead",
        "curationStatus",
        "documentaryNote",
    } <= set(flagship_fields)
    assert len(compact["carteira1"]["ranges"]) == 7
    assert len(compact["carteira1"]["details"]) == 101
    carteira_fields = compact["carteira1"]["fields"]["detail"]
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
