from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from scripts.build_fidc_industry_study import parse_args as parse_study_args
from scripts.publish_fidc_revision_bundle import (
    ANALYSIS_MANIFEST_NAME,
    BUNDLE_MANIFEST_NAME,
    MATERIALIZED_PPTX_NAME,
    MATERIALIZED_XLSX_NAME,
    PAYLOAD_SCHEMA,
    REQUIRED_ANALYSIS_FILES,
    REQUIRED_DATA_INPUTS,
    RevisionBundlePublishError,
    build_bundle_manifest,
    discover_artifact_node_modules,
    discover_latest_complete,
    publish_staged_bundle,
    serialize_analysis_manifest,
    validate_artifact_payload,
    validate_bundle_manifest,
    validate_deck_snapshot,
    validate_renderer_manifest,
)


def test_discover_latest_complete_ignores_newer_preliminary_month(tmp_path: Path) -> None:
    (tmp_path / "industry_competence_status.csv").write_text(
        "competencia,publication_status\n"
        "2026-04,completa\n"
        "2026-05,completa\n"
        "2026-06,preliminar\n",
        encoding="utf-8",
    )

    assert discover_latest_complete(tmp_path) == "2026-05"


def test_discover_artifact_node_modules_uses_explicit_offline_runtime(
    tmp_path: Path,
) -> None:
    node_modules = tmp_path / "node_modules"
    package = node_modules / "@oai" / "artifact-tool" / "package.json"
    package.parent.mkdir(parents=True)
    package.write_text('{"version":"1.2.3"}', encoding="utf-8")

    assert discover_artifact_node_modules(node_modules) == node_modules.resolve()


def _payload() -> dict[str, object]:
    return {
        "schema_version": PAYLOAD_SCHEMA,
        "latest_complete": "2026-05",
        "offers_as_of": "2026-07-15",
        "top20_fidcs": [{}] * 20,
        "top20_outros": [{}] * 20,
        "profiles": [{}] * 20,
        "holder_distribution_history": [
            {"competencia": "2023-12"},
            {"competencia": "2026-05"},
        ],
        "type_mix_history": [
            {"competencia": "2023-12"},
            {"competencia": "2026-05"},
        ],
        "receivables_history": [
            {"competencia": "2023-12"},
            {"competencia": "2026-05"},
        ],
        "provider_concentration_history": [
            {"competencia": "2025-12"},
            {"competencia": "2026-05"},
        ],
        "provider_historical_ranking": [
            {"competencia": "2024-12", "papel": "administrador"},
            {"competencia": "2025-12", "papel": "administrador"},
            {"competencia": "2026-05", "papel": "administrador"},
        ],
        "market_share_scope_summary": [
            {"competencia": "2026-05", "papel": "administrador"}
        ],
        "market_share_exclusions": [
            {"cnpj": "09195235000150", "fund": "FIDC Sistema Petrobras"},
            {"cnpj": "26287464000114", "fund": "FIDC TAPSO"},
        ],
        "acquiring_taxonomy": {
            "summary": {"table_ii_category": "Cartão"},
            "funds": [{"fund_name": "TAPSO FIDC"}],
            "sources": [],
        },
        "atlantico_profile": {"cnpj": "09.194.841/0001-51"},
        "atlantico_history": [{"competencia": "2026-05"}],
        "provider_transition_summary": {"changed_funds": 257},
        "provider_transition_links": [{"grupo_origem": "A", "grupo_destino": "B"}],
        "provider_transition_detail": [{"cnpj_fundo": "1"}],
        "provider_transition_role_availability": [{"papel": "administrador"}],
        "reag_admin_summary": {"funds_origin": 131},
        "reag_admin_links": [{"destino_grupo": "Planner"}],
        "reag_admin_detail": [{"cnpj_fundo": "1"}],
        "provider_leadership_attribution": {"btg": {}, "qi": {}},
        "btg_controlled_reconciliation": [{"cnpj_veiculo": "1"}],
        "qi_legacy_attribution": [{"provider_cnpj": "1"}],
        "delinquency_single_receivable": [
            {
                "tipo_recebivel_tabela_ii": "Financeiro",
                "fundos_incluidos": 1,
                "pl_incluido_brl": 1.0,
                "inadimplencia_sobre_pl": 0.01,
            }
        ],
        "delinquency_single_receivable_summary": {
            "fundos_universo_ex_fic_pl_positivo": 2,
            "pl_universo_ex_fic_positivo_brl": 2.0,
            "fundos_incluidos": 1,
            "pl_incluido_brl": 1.0,
            "cobertura_pl": 0.5,
            "fundos_multitipo_excluidos": 0,
            "pl_multitipo_excluido_brl": 0.0,
            "fundos_sem_tipo_excluidos": 0,
            "pl_sem_tipo_excluido_brl": 0.0,
            "fundos_inad_supera_carteira_excluidos": 0,
            "pl_inad_supera_carteira_excluido_brl": 0.0,
            "fundos_fic_excluidos": 1,
            "pl_fic_excluido_brl": 1.0,
        },
        "delinquency_frozen_cohort_history": [
            {
                "competencia": "2026-05",
                "tipo_recebivel_tabela_ii": "Financeiro",
                "fundos_incluidos": 1,
                "pl_incluido_brl": 1.0,
                "inadimplencia_sobre_carteira": 0.01,
                "fundos_coorte": 1,
                "pl_coorte_referencia_brl": 1.0,
            }
        ],
        "delinquency_frozen_cohort_summary": [
            {
                "competencia": "2026-05",
                "fundos_incluidos": 1,
                "pl_incluido_brl": 1.0,
                "inadimplencia_sobre_carteira": 0.01,
                "fundos_coorte": 1,
                "pl_coorte_referencia_brl": 1.0,
                "regra": "coorte fixa",
                "fonte": "CVM",
            }
        ],
        "provider_independent_ranking": [
            {
                "competencia": "2026-05",
                "papel": "administrador",
                "participante": "QI Tech",
                "rank_independente": 1,
                "rank_geral": 1,
                "pl_brl": 1.0,
                "selected_latest_top_n": True,
            }
        ],
        "bank_fidc_evolution": [
            {
                "competencia": "2026-05",
                "grupo_bancario": "BTG Pactual",
                "pl_bruto_brl": 1.0,
                "is_total_5_banks": False,
                "observado": True,
            }
        ],
        "bank_fidc_detail": [
            {
                "competencia": "2026-05",
                "grupo_bancario": "BTG Pactual",
                "cnpj_fundo": "1",
                "denominacao": "FIDC A",
                "pl_brl": 1.0,
                "observado": True,
            }
        ],
        "btg_provider_ex_controlled_scenario": [
            {
                "competencia": "2026-05",
                "papel": "administrador",
                "btg_pl_brl": 1.0,
                "btg_rank": 2,
                "fidcs_controlados_excluidos": 6,
                "pl_controlado_excluido_brl": 0.2,
                "btg_pl_ex_controlados_brl": 0.8,
                "btg_rank_ex_controlados": 2,
                "regra": "seis fundos confirmados",
                "fonte": "DFs",
            }
        ],
        "acquiring_reclassified_mix": [
            {
                "competencia": "2026-05",
                "categoria_analitica": "Adquirência",
                "pl_brl": 1.0,
                "share_pl": 0.01,
            }
        ],
        "closed_offers_annual": [
            {
                "year": year,
                "closed_offers": 1,
                "registered_volume_brl": 1.0,
                "mean_registered_ticket_brl": 1.0,
                "median_registered_ticket_brl": 1.0,
                "natural_person_placed_volume_share": 0.01,
                "placed_quantity_registered_volume_coverage": 0.99,
                "professional_target_registered_volume_share": 0.95,
            }
            for year in (2023, 2024, 2025, 2026)
        ],
        "closed_offers_monthly": [
            {"year": 2026, "month": 1, "registered_volume_brl": 1.0}
        ],
        "closed_offers_jan_may": [
            {
                "year": 2026,
                "closed_offers": 1,
                "registered_volume_brl": 1.0,
                "mean_registered_ticket_brl": 1.0,
            }
        ],
        "closed_offer_ticket_distribution": [
            {
                "period_label": "2026 jan–mai",
                "period_start": "2026-01-01",
                "period_end": "2026-05-31",
                "ticket_bucket": "R$ 10–25 mi",
                "closed_offers": 1,
                "offer_share": 1.0,
                "registered_volume_brl": 1.0,
                "registered_volume_share": 1.0,
                "period_mean_ticket_brl": 1.0,
                "period_median_ticket_brl": 1.0,
            }
        ],
        "closed_offer_originators_2026": [
            {
                "rank": 1,
                "originator_group": "Originador A",
                "closed_offers": 1,
                "registered_volume_brl": 1.0,
                "mean_registered_ticket_brl": 1.0,
                "identified_registered_volume_coverage": 0.5,
                "identified_registered_volume_brl": 0.5,
                "confidence": "high",
                "share_of_total_registered_volume": 0.1,
            }
        ],
        "provider_history_cvm_coverage": [
            {
                "papel": "gestor",
                "data_referencia": "2024-12-31→2026-05-31",
                "fundos_coorte": 1,
                "pl_coorte_mai26_brl": 1.0,
                "fundos_resolvidos_unicos": 1,
                "pl_resolvido_unico_brl": 1.0,
                "cobertura_fundos_resolvida": 1.0,
                "cobertura_pl_resolvida": 1.0,
                "escopo_fonte": "ICVM 555",
            }
        ],
        "provider_history_cvm_links": [
            {
                "papel": "gestor",
                "data_origem": "2024-12-31",
                "data_destino": "2026-05-31",
                "origem_prestador_grupo": "A",
                "destino_prestador_grupo": "B",
                "fundos": 1,
                "pl_mai26_brl": 1.0,
                "share_pl_comparavel": 1.0,
                "escopo_fonte": "ICVM 555",
            }
        ],
        "provider_history_cvm_detail": [
            {
                "papel": "gestor",
                "data_origem": "2024-12-31",
                "data_destino": "2026-05-31",
                "cnpj_fundo": "1",
                "denominacao": "FIDC A",
                "pl_mai26_brl": 1.0,
                "origem_prestador_grupo": "A",
                "destino_prestador_grupo": "B",
            }
        ],
        "conclusion_metrics": {"competencia": "2026-05"},
    }


def test_payload_schema_and_required_historical_comparisons_are_versioned() -> None:
    assert PAYLOAD_SCHEMA == "fidc_revision_artifact_payload_v5"
    payload = _payload()
    validate_artifact_payload(payload, "2026-05")

    for key in (
        "holder_distribution_history",
        "type_mix_history",
        "receivables_history",
        "provider_concentration_history",
        "provider_historical_ranking",
        "market_share_scope_summary",
        "market_share_exclusions",
        "acquiring_taxonomy",
        "atlantico_profile",
        "atlantico_history",
        "provider_transition_summary",
        "provider_transition_links",
        "provider_transition_detail",
        "provider_transition_role_availability",
        "reag_admin_summary",
        "reag_admin_links",
        "reag_admin_detail",
        "provider_leadership_attribution",
        "btg_controlled_reconciliation",
        "qi_legacy_attribution",
        "delinquency_single_receivable",
        "delinquency_single_receivable_summary",
        "delinquency_frozen_cohort_history",
        "delinquency_frozen_cohort_summary",
        "provider_independent_ranking",
        "bank_fidc_evolution",
        "bank_fidc_detail",
        "btg_provider_ex_controlled_scenario",
        "acquiring_reclassified_mix",
        "closed_offers_annual",
        "closed_offers_monthly",
        "closed_offers_jan_may",
        "closed_offer_ticket_distribution",
        "closed_offer_originators_2026",
        "provider_history_cvm_coverage",
        "provider_history_cvm_links",
        "provider_history_cvm_detail",
        "conclusion_metrics",
    ):
        broken = dict(payload)
        broken.pop(key)
        with pytest.raises(RevisionBundlePublishError, match=key):
            validate_artifact_payload(broken, "2026-05")


def test_bundle_manifest_is_content_addressed_and_validated() -> None:
    payload = _payload()
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    kwargs = {
        "payload_bytes": payload_bytes,
        "payload": payload,
        "analysis_manifest_bytes": b"analysis",
        "pptx_bytes": b"pptx",
        "xlsx_bytes": b"xlsx",
        "html_bytes": b"html",
        "input_hashes": {"data/a.csv": "a" * 64},
        "renderer": {
            "artifact_tool_version": "1",
            "node_version": "v22",
            "renderer_sha256": "f" * 64,
        },
    }
    first = build_bundle_manifest(
        **kwargs,
        generated_at_utc="2026-07-16T12:00:00+00:00",
    )
    second = build_bundle_manifest(
        **kwargs,
        generated_at_utc="2026-07-17T12:00:00+00:00",
    )

    assert first["bundle_id"] == second["bundle_id"]
    assert first["schema_version"] == "fidc_revision_export_bundle_v2"
    assert first["checks"]["slides"] == 55
    validate_bundle_manifest(
        first,
        payload_bytes=payload_bytes,
        payload=payload,
        analysis_manifest_bytes=b"analysis",
        pptx_bytes=b"pptx",
        xlsx_bytes=b"xlsx",
        html_bytes=b"html",
    )
    validate_renderer_manifest(
        first,
        payload_bytes=payload_bytes,
        payload=payload,
        pptx_bytes=b"pptx",
        xlsx_bytes=b"xlsx",
        html_bytes=b"html",
        renderer_sha256="f" * 64,
    )

    with pytest.raises(RevisionBundlePublishError, match="snapshot"):
        validate_renderer_manifest(
            first,
            payload_bytes=payload_bytes,
            payload=payload,
            pptx_bytes=b"pptx",
            xlsx_bytes=b"xlsx",
            html_bytes=b"html",
            renderer_sha256="0" * 64,
        )

    broken = dict(first)
    broken["pptx"] = {**dict(first["pptx"]), "sha256": "0" * 64}
    with pytest.raises(RevisionBundlePublishError, match="pptx"):
        validate_bundle_manifest(
            broken,
            payload_bytes=payload_bytes,
            payload=payload,
            analysis_manifest_bytes=b"analysis",
            pptx_bytes=b"pptx",
            xlsx_bytes=b"xlsx",
            html_bytes=b"html",
        )

    broken_html = dict(first)
    broken_html["html"] = {**dict(first["html"]), "sha256": "0" * 64}
    with pytest.raises(RevisionBundlePublishError, match="html"):
        validate_bundle_manifest(
            broken_html,
            payload_bytes=payload_bytes,
            payload=payload,
            analysis_manifest_bytes=b"analysis",
            pptx_bytes=b"pptx",
            xlsx_bytes=b"xlsx",
            html_bytes=b"html",
        )


def test_analysis_manifest_uses_publisher_clock_for_reproducibility() -> None:
    first, first_bytes = serialize_analysis_manifest(
        {"generated_at_utc": "wall-clock-a", "latest_complete": "2026-05"},
        "2026-07-17T00:00:00+00:00",
    )
    second, second_bytes = serialize_analysis_manifest(
        {"generated_at_utc": "wall-clock-b", "latest_complete": "2026-05"},
        "2026-07-17T00:00:00+00:00",
    )

    assert first == second
    assert first_bytes == second_bytes
    assert first["generated_at_utc"] == "2026-07-17T00:00:00+00:00"


def test_publish_staged_bundle_replaces_commit_manifest_last(tmp_path: Path) -> None:
    stage_revision = tmp_path / "stage" / "revision"
    stage_revision.mkdir(parents=True)
    (stage_revision / "artifact_payload.json").write_text("payload", encoding="utf-8")
    (stage_revision / ANALYSIS_MANIFEST_NAME).write_text("analysis", encoding="utf-8")
    (stage_revision / BUNDLE_MANIFEST_NAME).write_text(
        "provisional renderer manifest", encoding="utf-8"
    )
    staged_pptx = tmp_path / "stage" / "deck.pptx"
    staged_xlsx = tmp_path / "stage" / "book.xlsx"
    staged_manifest = tmp_path / "stage" / "bundle.json"
    staged_pptx.write_bytes(b"pptx")
    staged_xlsx.write_bytes(b"xlsx")
    staged_manifest.write_text("manifest", encoding="utf-8")
    publish_dir = tmp_path / "published"
    destinations: list[Path] = []

    def recording_replace(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        destinations.append(Path(target))
        os.replace(source, target)

    publish_staged_bundle(
        staged_revision_dir=stage_revision,
        staged_pptx=staged_pptx,
        staged_xlsx=staged_xlsx,
        staged_bundle_manifest=staged_manifest,
        publish_dir=publish_dir,
        replace=recording_replace,
    )

    assert destinations[-1] == publish_dir / BUNDLE_MANIFEST_NAME
    assert destinations.count(publish_dir / BUNDLE_MANIFEST_NAME) == 1
    assert destinations[-3:-1] == [
        publish_dir / MATERIALIZED_PPTX_NAME,
        publish_dir / MATERIALIZED_XLSX_NAME,
    ]
    assert (publish_dir / BUNDLE_MANIFEST_NAME).read_text() == "manifest"


def _minimal_pptx(text: str) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            f'<p:sld xmlns:p="p" xmlns:a="a"><a:t>{text}</a:t></p:sld>',
        )
    return output.getvalue()


def test_validate_deck_snapshot_rejects_hardcoded_wrong_competence() -> None:
    validate_deck_snapshot(_minimal_pptx("Base consolidada Mai/26"), "2026-05")

    with pytest.raises(RevisionBundlePublishError, match="jun/26"):
        validate_deck_snapshot(_minimal_pptx("Base consolidada Mai/26"), "2026-06")


def test_analysis_manifest_requires_materialized_tables(tmp_path: Path) -> None:
    from scripts.publish_fidc_revision_bundle import validate_analysis_manifest

    for filename in REQUIRED_ANALYSIS_FILES:
        (tmp_path / filename).write_bytes(b"")
    manifest = {
        "latest_complete": "2026-05",
        "files": {name: {} for name in REQUIRED_ANALYSIS_FILES},
        "checks": {
            "top20_fidcs_rows": 20,
            "top20_outros_rows": 20,
            "latest_funds": 4222,
        },
    }

    validate_analysis_manifest(
        manifest,
        revision_dir=tmp_path,
        latest_complete="2026-05",
    )


def test_revision_bundle_requires_new_market_share_and_taxonomy_inputs() -> None:
    assert {
        "market_share_escopo_resumo.csv",
        "prestadores_ranking_historico.csv",
    }.issubset(REQUIRED_ANALYSIS_FILES)
    assert "acquiring_taxonomy_curation.json" in REQUIRED_DATA_INPUTS
    assert "industry_closed_offer_ticket_distribution.csv" in REQUIRED_DATA_INPUTS
    assert "industry_closed_offer_ticket_cohort.csv.gz" in REQUIRED_DATA_INPUTS


def test_main_pipeline_exposes_explicit_offline_publish_switch() -> None:
    args = parse_study_args(
        [
            "--publish-revision-bundle",
            "--revision-input-workbook",
            "base.xlsx",
        ]
    )

    assert args.publish_revision_bundle is True
    assert args.revision_input_workbook == "base.xlsx"
