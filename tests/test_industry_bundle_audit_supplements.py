from __future__ import annotations

from pathlib import Path

from scripts.build_fidc_revision_artifact_payload import (
    _load_bundle_audit_supplements,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "industry_study"
RENDERER = ROOT / "scripts" / "build_fidc_revision_artifacts.mjs"


def test_normalized_cedent_and_taxonomy_blocks_enter_the_payload() -> None:
    blocks = _load_bundle_audit_supplements(DATA_DIR)

    top = blocks["cedente_middle_market_top437"]
    curve = blocks["cedente_middle_market_coverage_curve"]
    decisions = blocks["taxonomy_audit_decisions"]
    outros = blocks["taxonomy_audit_outros_three_buckets"]

    assert len(top) == 510
    assert len({row["cnpj_fundo"] for row in top}) == 437
    assert len(curve) == 4_311
    assert len(decisions) == 37
    assert len(outros) == 76
    assert all(len(row["cnpj_fundo"]) == 14 for row in top)
    assert sum(
        row["middle_market_triage_status"] == "sem_cedente_tabela_i"
        for row in top
    ) == 296

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
        "Cedentes · Top 437",
        "Cedentes · Cobertura",
        "Taxonomia · de-para",
        "Taxonomia · Outros",
        "Taxonomia · impacto",
    ):
        assert sheet_name in source

    assert "await addCedenteAuditSheets(workbook, payload);" in source
    assert "await addTaxonomyAuditSheets(workbook, payload);" in source
    assert "await addTaxonomyImpactSheet(workbook, payload);" in source
    assert "Documento do cedente · coluna H" in source
    assert "Razão social · coluna K" in source
    assert "Razão social consolidada" in source
    assert "a chave da coluna A reconcilia razão social" in source
    assert (
        "A Tabela I identifica cedente; não identifica sacado ou devedor nomeado."
        in source
    )
    assert (
        "Porte da Receita e capital social não confirmam faturamento entre "
        "R$ 30 mi e R$ 500 mi."
        in source
    )
    assert "Variações em R$ bi e p.p. não são somadas entre perímetros." in source


def test_renderer_aggregates_legacy_and_audited_multicedente_focus() -> None:
    source = RENDERER.read_text(encoding="utf-8")

    alias_contract = (
        '"Multicedente/Multissacado": '
        '["Multicarteira Outros", "Multicedente/Multissacado"]'
    )
    assert source.count(alias_contract) >= 2
