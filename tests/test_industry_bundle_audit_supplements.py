from __future__ import annotations

from pathlib import Path
import re

import pytest

from scripts.build_fidc_revision_artifact_payload import (
    _load_bundle_audit_supplements,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "industry_study"
RENDERER = ROOT / "scripts" / "build_fidc_revision_artifacts.mjs"


def test_normalized_cedent_and_taxonomy_blocks_enter_the_payload() -> None:
    blocks = _load_bundle_audit_supplements(DATA_DIR)

    top = blocks["cedente_top500_detail"]
    coverage = blocks["cedente_top500_coverage_history"]
    registry = blocks["cedente_registry_master"]
    gaps = blocks["cedente_funds_without_cedent"]
    repairs = blocks["cedente_source_repairs"]
    manifest = blocks["cedente_triage_manifest"]
    decisions = blocks["taxonomy_audit_decisions"]
    outros = blocks["taxonomy_audit_outros_three_buckets"]

    assert top
    assert len(coverage) == 4
    assert [row["Fundos que identificam cedente"] for row in coverage] == [
        181,
        148,
        205,
        172,
    ]
    assert [row["Fundos na indústria"] for row in coverage] == [
        2_404,
        3_140,
        4_008,
        4_311,
    ]
    assert [row["% do PL total"] for row in coverage] == pytest.approx(
        [
            0.8395464326020662,
            0.7946176676596972,
            0.7349500587764943,
            0.7255622598775591,
        ]
    )
    assert registry
    assert len(gaps) == 1_294
    assert len(repairs) == 10
    assert {
        competence: sum(str(row["competencia"]) == competence for row in repairs)
        for competence in ("202312", "202412", "202512", "202606")
    } == {"202312": 6, "202412": 4, "202512": 0, "202606": 0}
    assert manifest["schema_version"] == "fidc-cedente-top500/v2"
    assert manifest["source_repairs_summary"] == {
        "202312": 6,
        "202412": 4,
        "202512": 0,
        "202606": 0,
    }
    assert "fidc_cedentes_receita_targets.csv" in manifest["outputs"]
    assert {
        "CNPJ/CPF do cedente",
        "Razão social do cedente",
        "Cedente dominante?",
    }.issubset(top[0])
    assert len(decisions) == 37
    assert len(outros) == 76
    assert all(len(row["CNPJ do fundo"]) == 14 for row in top)
    for rows in (
        top,
        blocks["cedente_registry_by_competence"],
        registry,
    ):
        cnae_codes = [
            str(row["CNAE (cód.)"])
            for row in rows
            if str(row.get("CNAE (cód.)") or "").strip()
        ]
        assert all(len(code) == 7 and code.isdigit() for code in cnae_codes)
    assert any(
        str(row.get("CNAE (cód.)") or "").startswith("0") for row in top
    )

    assert len(blocks["taxonomy_audit_impact_summary"]) == 11
    assert len(blocks["taxonomy_audit_issuance_impact"]) == 20
    assert len(blocks["taxonomy_audit_market_share_impact"]) == 22
    assert {
        row["view"] for row in blocks["taxonomy_audit_impact_summary"]
    } == {
        "source_decision_summary",
        "source_gross_stock_type",
        "current_bundle_incremental_stock_type",
    }


def test_stock_impact_keeps_gross_and_incremental_perimeters_separate() -> None:
    blocks = _load_bundle_audit_supplements(DATA_DIR)
    stock_rows = [
        row
        for row in blocks["taxonomy_audit_impact_summary"]
        if row["dimension"] == "tipo_anbima_exibido"
    ]
    denominators = {round(float(row["denominator_brl"]), 2) for row in stock_rows}

    assert denominators == {821_361_559_284.45, 880_375_346_502.31}
    assert all(row["source"] and row["note"] for row in stock_rows)


def test_renderer_materializes_all_audit_sheets_and_limitations() -> None:
    source = RENDERER.read_text(encoding="utf-8")

    for sheet_name in (
        "Cedentes · Leia-me",
        "Cedentes · Top 500",
        "Cedentes · competência",
        "Cedentes · sem cedente",
        "Cedentes · evolução",
        "Cedentes · presença",
        "Cedentes · cobertura",
        "Cedentes · PL segmento",
        "Cedentes · cadastro",
        "Cedentes · exclusões",
        "Cedentes · reparos fonte",
        "Taxonomia · de-para",
        "Taxonomia · Outros",
        "Taxonomia · impacto",
        "Cobertura emissões",
        "Curadoria perfis",
    ):
        assert sheet_name in source

    assert "await addCedenteAuditSheets(workbook, payload);" in source
    assert "await addTaxonomyAuditSheets(workbook, payload);" in source
    assert "await addTaxonomyImpactSheet(workbook, payload);" in source
    assert "await addEmissionFieldCoverageSheets(workbook, payload);" in source
    assert "Fonte originador" in source
    assert "Fonte cedente" in source
    assert "Natureza do mínimo" in source
    assert "Motivo N/D" in source
    assert "O Informe Mensal da CVM não identifica sacado/devedor nomeado." in source
    assert "cedenteColumns(rows)" not in source
    for schema_name in (
        "CEDENTE_TOP500_DETAIL_COLUMNS",
        "CEDENTE_REGISTRY_BY_COMPETENCE_COLUMNS",
        "CEDENTE_FUNDS_WITHOUT_CEDENT_COLUMNS",
        "CEDENTE_EVOLUTION_BY_SEGMENT_COLUMNS",
        "CEDENTE_PRESENCE_HISTORY_COLUMNS",
        "CEDENTE_TOP500_COVERAGE_HISTORY_COLUMNS",
        "CEDENTE_SEGMENT_MIX_HISTORY_COLUMNS",
        "CEDENTE_REGISTRY_MASTER_COLUMNS",
        "CEDENTE_EXCLUSIONS_COLUMNS",
        "CEDENTE_SOURCE_REPAIRS_COLUMNS",
    ):
        assert schema_name in source
    assert (
        "A Tabela I identifica cedente; não identifica sacado ou devedor nomeado."
        in source
    )
    assert (
        "Potencial Middle é resíduo de triagem; porte e capital social não "
        "confirmam faturamento entre R$ 30 mi e R$ 500 mi."
        in source
    )
    assert "Variações em R$ bi e p.p. não são somadas entre perímetros." in source


def test_cedent_sheet_schemas_are_explicit_complete_and_keep_identifiers_as_text() -> None:
    source = RENDERER.read_text(encoding="utf-8")
    blocks = _load_bundle_audit_supplements(DATA_DIR)
    schema_by_payload = {
        "cedente_top500_detail": "CEDENTE_TOP500_DETAIL_COLUMNS",
        "cedente_registry_by_competence": (
            "CEDENTE_REGISTRY_BY_COMPETENCE_COLUMNS"
        ),
        "cedente_funds_without_cedent": (
            "CEDENTE_FUNDS_WITHOUT_CEDENT_COLUMNS"
        ),
        "cedente_evolution_by_segment": (
            "CEDENTE_EVOLUTION_BY_SEGMENT_COLUMNS"
        ),
        "cedente_presence_history": "CEDENTE_PRESENCE_HISTORY_COLUMNS",
        "cedente_top500_coverage_history": (
            "CEDENTE_TOP500_COVERAGE_HISTORY_COLUMNS"
        ),
        "cedente_segment_mix_history": (
            "CEDENTE_SEGMENT_MIX_HISTORY_COLUMNS"
        ),
        "cedente_registry_master": "CEDENTE_REGISTRY_MASTER_COLUMNS",
        "cedente_exclusions": "CEDENTE_EXCLUSIONS_COLUMNS",
        "cedente_source_repairs": "CEDENTE_SOURCE_REPAIRS_COLUMNS",
    }

    for payload_key, schema_name in schema_by_payload.items():
        match = re.search(
            rf"const {schema_name} = Object\.freeze\(\[(.*?)\]\);",
            source,
            flags=re.DOTALL,
        )
        assert match is not None, schema_name
        schema_keys = re.findall(r'cedenteColumn\("([^"]+)"', match.group(1))
        assert len(schema_keys) == len(set(schema_keys)), schema_name
        assert set(schema_keys) == set(blocks[payload_key][0]), schema_name

    text_branch = source.index('if (column.format === "@")')
    numeric_branch = source.index(
        'if (column.key === "cnpj_numerico" || column.format === "00000000000000")'
    )
    assert text_branch < numeric_branch
    assert 'return String(value);' in source[text_branch:numeric_branch]
    assert 'cedenteColumn("CNPJ do fundo", 140, "@")' in source
    assert 'cedenteColumn("CNPJ/CPF", 150, "@")' in source
    assert 'cedenteColumn("CNAE (cód.)", 95, "@")' in source
    assert 'cedenteColumn("cnae_codigo", 95, "@")' in source
    assert 'cedenteColumn("documento_fundo", 150, "@")' in source
    assert '["Cedentes · reparos fonte", "A1:H20"]' in source
    assert "Cedentes · reparos estruturais da fonte" in source
    assert "Gate estrutural aplicado antes do ranking" in source


def test_renderer_aggregates_legacy_and_audited_multicedente_focus() -> None:
    source = RENDERER.read_text(encoding="utf-8")

    alias_contract = (
        '"Multicedente/Multissacado": '
        '["Multicarteira Outros", "Multicedente/Multissacado"]'
    )
    assert source.count(alias_contract) >= 2
