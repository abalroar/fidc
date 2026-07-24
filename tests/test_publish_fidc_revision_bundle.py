from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

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
    validate_source_presence_coverage,
    validate_user_facing_workbook_snapshot,
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


def _snapshot_workbook_bytes(latest: str, *, stale_sheet: str = "") -> bytes:
    from scripts.publish_fidc_revision_bundle import USER_FACING_SNAPSHOT_SHEETS

    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name in USER_FACING_SNAPSHOT_SHEETS:
        sheet = workbook.create_sheet(sheet_name)
        sheet.append(["competencia", "valor"])
        sheet.append(["2026-05", 1])
        if sheet_name != stale_sheet:
            sheet.append([latest, 2])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_user_facing_workbook_snapshot_accepts_all_tabs_at_latest() -> None:
    validate_user_facing_workbook_snapshot(
        _snapshot_workbook_bytes("2026-06"),
        "2026-06",
    )


def test_user_facing_workbook_snapshot_blocks_one_stale_inherited_tab() -> None:
    with pytest.raises(
        RevisionBundlePublishError,
        match=r"Mix ANBIMA \(2026-05\)",
    ):
        validate_user_facing_workbook_snapshot(
            _snapshot_workbook_bytes("2026-06", stale_sheet="Mix ANBIMA"),
            "2026-06",
        )


def _write_gzip_csv(path: Path, text: str) -> None:
    import gzip

    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write(text)


def test_source_presence_validation_blocks_degraded_latest_snapshot(
    tmp_path: Path,
) -> None:
    _write_gzip_csv(
        tmp_path / "base_competencia_cnpj.csv.gz",
        "competencia,field_presence_exact\n2026-06,False\n",
    )
    _write_gzip_csv(
        tmp_path / "source_presence_overlay.csv.gz",
        "competencia\n",
    )

    with pytest.raises(RevisionBundlePublishError, match="vazio-versus-zero"):
        validate_source_presence_coverage(tmp_path, "2026-06")


def test_source_presence_validation_accepts_complete_latest_snapshot(
    tmp_path: Path,
) -> None:
    _write_gzip_csv(
        tmp_path / "base_competencia_cnpj.csv.gz",
        "competencia,field_presence_exact\n2026-06,True\n",
    )
    _write_gzip_csv(
        tmp_path / "source_presence_overlay.csv.gz",
        "competencia\n2026-06\n",
    )

    validate_source_presence_coverage(tmp_path, "2026-06")


def test_source_presence_validation_blocks_historical_overlay_reduction(
    tmp_path: Path,
) -> None:
    _write_gzip_csv(
        tmp_path / "base_competencia_cnpj.csv.gz",
        "competencia,field_presence_exact\n"
        "2026-05,True\n"
        "2026-06,True\n",
    )
    _write_gzip_csv(
        tmp_path / "source_presence_overlay.csv.gz",
        "competencia\n2026-06\n",
    )

    with pytest.raises(
        RevisionBundlePublishError,
        match="não cobre o histórico completo",
    ):
        validate_source_presence_coverage(tmp_path, "2026-06")


def test_discover_artifact_node_modules_uses_explicit_offline_runtime(
    tmp_path: Path,
) -> None:
    node_modules = tmp_path / "node_modules"
    package = node_modules / "@oai" / "artifact-tool" / "package.json"
    package.parent.mkdir(parents=True)
    package.write_text('{"version":"1.2.3"}', encoding="utf-8")

    assert discover_artifact_node_modules(node_modules) == node_modules.resolve()


def _format_test_cnpj(value: int) -> str:
    digits = f"{value:014d}"
    return (
        f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/"
        f"{digits[8:12]}-{digits[12:]}"
    )


def _card_taxonomy_rows() -> list[dict[str, object]]:
    statuses = (
        ["Incluído em Adquirência"] * 26
        + ["Fora de Adquirência"] * 17
        + ["Pendente"]
    )
    rows: list[dict[str, object]] = []
    for rank, status in enumerate(statuses, start=1):
        included = status == "Incluído em Adquirência"
        rows.append(
            {
                "ordem_materialidade": rank,
                "cnpj_fundo_formatado": _format_test_cnpj(rank),
                "cnpj_fundo_identificado": True,
                "denominacao": f"FIDC Cartão {rank}",
                "criterio_inclusao": "Cartão de crédito é o segmento principal da Tabela II",
                "categoria_tabela_ii": "Cartão de crédito",
                "valor_cartao_tabela_ii_brl": float(45 - rank),
                "pl_jun25_brl": float(45 - rank),
                "pl_jun25_observavel": True,
                "pl_referencia_brl": float(45 - rank),
                "pl_referencia_competencia": "2026-06",
                "status_curadoria": status,
                "decisao_curadoria": (
                    "Reclassificar como Adquirência"
                    if included
                    else "Manter fora da abertura de Adquirência"
                ),
                "cedente_originador": f"Originador {rank}",
                "devedor_sacado": f"Devedor {rank}",
                "instrumento": "CCB",
                "natureza_economica": "Recebíveis de pagamento",
                "evidencia_curta": "Evidência documental reconciliada.",
                "fonte_url": f"https://example.com/regulamento/{rank}",
                "anbima_tipo": "Outros",
                "anbima_foco": "N/D",
                "anbima_cartao_explicito": False,
                "ja_curado_como_adquirencia": included,
                "consistencia_decisao_reclassificacao": "OK",
            }
        )
    return rows


def _card_taxonomy_summary(
    rows: list[dict[str, object]],
) -> dict[str, object]:
    statuses = {
        "Incluído em Adquirência": (
            "fundos_incluidos_adquirencia",
            "pl_incluido_adquirencia_brl",
        ),
        "Fora de Adquirência": (
            "fundos_fora_adquirencia",
            "pl_fora_adquirencia_brl",
        ),
        "Pendente": (
            "fundos_pendentes_curadoria",
            "pl_pendente_curadoria_brl",
        ),
    }
    summary: dict[str, object] = {
        "fundos_total": len(rows),
        "pl_referencia_observado_brl": sum(
            float(row["pl_referencia_brl"]) for row in rows
        ),
        "divergencias_decisao_reclassificacao": 0,
    }
    for status, (count_field, pl_field) in statuses.items():
        status_rows = [row for row in rows if row["status_curadoria"] == status]
        summary[count_field] = len(status_rows)
        summary[pl_field] = sum(
            float(row["pl_referencia_brl"]) for row in status_rows
        )
    return summary


def _fixed_income_offer_comparison_fixture() -> list[dict[str, object]]:
    periods = ("2023 FY", "2024 FY", "2025 FY", "2026 jan-jun")
    rows: list[dict[str, object]] = []
    for period in periods:
        comparable = period != "2023 FY"
        for view, labels in (
            ("FIDCs vs demais elegíveis", ("FIDCs", "Demais elegíveis")),
            (
                "FIDCs vs instrumentos materiais de 2025",
                ("FIDCs", "Debêntures", "CRI", "Notas comerciais", "CRA"),
            ),
        ):
            universe = 2.0 if len(labels) == 2 else 5.0
            for series_order, label in enumerate(labels, start=1):
                rows.append(
                    {
                        "view": view,
                        "series_order": series_order,
                        "series_label": label,
                        "period_label": period,
                        "registered_volume_brl": 1.0,
                        "previous_registered_volume_brl": (
                            1.0 if comparable else None
                        ),
                        "yoy_growth": 0.0 if comparable else None,
                        "yoy_comparable": comparable,
                        "universe_registered_volume_brl": universe,
                        "source_url": "https://dados.cvm.gov.br/",
                        "scope": "Oferta Encerrada",
                        "excluded_instruments": "Cotas de FII",
                    }
                )
    return rows


def _closed_offer_placement_regime_fixture() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for period_order, period in enumerate(
        ("2024 FY", "2025 FY", "2026 jan-jun"),
        start=1,
    ):
        for regime_order, regime in enumerate(
            (
                "Melhores esforços",
                "Garantia firme",
                "Misto",
                "Não informado",
            ),
            start=1,
        ):
            observed = 1.0 if regime_order == 1 else 0.0
            rows.append(
                {
                    "period_order": period_order,
                    "period_label": period,
                    "regime_order": regime_order,
                    "placement_regime": regime,
                    "closed_offers": observed,
                    "closed_offers_share": observed,
                    "registered_volume_brl": observed,
                    "registered_volume_share": observed,
                    "period_closed_offers": 1,
                    "period_registered_volume_brl": 1.0,
                    "source_url": "https://dados.cvm.gov.br/",
                    "scope": "Oferta Encerrada",
                    "methodology": "Regime_distribuicao",
                }
            )
    return rows


def _payload() -> dict[str, object]:
    card_rows = _card_taxonomy_rows()
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
            {
                "competencia": competencia,
                "period_label": period_label,
                "period_order": period_order,
                "anbima_tipo": anbima_tipo,
                "category_order": category_order,
                "pl": 0.25,
                "share": 0.25,
            }
            for period_order, (competencia, period_label) in enumerate(
                (
                    ("2023-12", "dez/23"),
                    ("2024-12", "dez/24"),
                    ("2025-12", "dez/25"),
                    ("2026-05", "mai/26"),
                )
            )
            for category_order, anbima_tipo in enumerate(
                (
                    "Fomento Mercantil",
                    "Agro, Indústria e Comércio",
                    "Financeiro",
                    "Outros",
                )
            )
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
        "delinquency_cohort_revision_summary": {
            "competencia_anterior": "2026-04",
            "competencia_atual": "2026-05",
            "fundos_coorte_anterior": 1,
            "fundos_coorte_atual": 1,
            "fundos_reclassificados": 1,
            "fundos_entraram": 0,
            "fundos_sairam": 0,
        },
        "delinquency_cohort_revision_transitions": [
            {
                "subtipo_anterior": "Serviços",
                "subtipo_atual": "Financeiro",
                "fundos": 1,
                "pl_atual_brl": 1.0,
                "principais_fundos": "FIDC A",
                "competencia_anterior": "2026-04",
                "competencia_atual": "2026-05",
            }
        ],
        "delinquency_cohort_revision_sensitivity": [
            {
                "competencia": "2025-12",
                "tipo_recebivel_tabela_ii": "Financeiro",
                "inadimplencia_sobre_carteira_coorte_anterior": 0.01,
                "inadimplencia_sobre_carteira_coorte_atual": 0.02,
                "delta_inadimplencia_pp": 0.01,
                "competencia_coorte_anterior": "2026-04",
                "competencia_coorte_atual": "2026-05",
            }
        ],
        "acquiring_curation_detail": [
            {
                "ordem_materialidade": 1,
                "cnpj_fundo_formatado": "10.000.000/0000-01",
                "denominacao": "FIDC A",
                "pl_referencia_brl": 2.0,
                "pl_referencia_competencia": "2026-06",
                "natureza_economica": "Recebíveis de pagamento",
                "categoria_tabela_ii": "Cartão de crédito",
                "anbima_tipo": "Outros",
                "anbima_foco": "N/D",
                "fonte_url": "https://example.com/regulamento",
            }
        ],
        "card_taxonomy_audit": card_rows,
        "card_taxonomy_summary": _card_taxonomy_summary(card_rows),
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
                "pl_brl_raw": 1.0,
                "pl_recovered_official": False,
                "pl_display_suffix": "",
                "pl_source_references": "N/D",
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
                "pl_brl_raw": 1.0,
                "pl_recovered_official": False,
                "pl_display_suffix": "",
                "pl_source_reference": "N/D",
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
                "period_label": (
                    f"{year} FY" if year < 2026 else "2026 jan-jun"
                ),
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
        "closed_offers_jan_june": [
            {
                "year": 2026,
                "closed_offers": 1,
                "registered_volume_brl": 1.0,
                "mean_registered_ticket_brl": 1.0,
            }
        ],
        "closed_offer_ticket_distribution": [
            {
                "period_label": "2026 jan–jun",
                "period_start": "2026-01-01",
                "period_end": "2026-06-30",
                "ticket_bucket": "R$ 10–25 mi",
                "closed_offers": 1,
                "offer_share": 1.0,
                "registered_volume_brl": 1.0,
                "registered_volume_share": 1.0,
                "period_mean_ticket_brl": 1.0,
                "period_median_ticket_brl": 1.0,
            }
        ],
        "closed_offer_placement_regime": (
            _closed_offer_placement_regime_fixture()
        ),
        "fixed_income_offer_comparison": (
            _fixed_income_offer_comparison_fixture()
        ),
        "closed_offer_originators_2026": [
            {
                "rank": rank,
                "originator_group": f"Originador {rank}",
                "closed_offers": rank,
                "registered_volume_brl": float(4 - rank),
                "mean_registered_ticket_brl": 1.0,
                "identified_registered_volume_coverage": 0.5,
                "identified_registered_volume_brl": 0.5,
                "confidence": "high",
                "share_of_total_registered_volume": 0.1,
            }
            for rank in range(1, 4)
        ],
        "closed_offer_top15": [
            {
                "period_label": period,
                "rank": rank,
                "offer_id": f"{period_order}{rank:02d}",
                "data_encerramento": (
                    "2025-12-31" if period == "2025 FY" else "2026-06-30"
                ),
                "cnpj_emissor": f"{period_order}{rank:013d}",
                "nome_emissor": f"FIDC {period} {rank}",
                "fund_name_short": f"FIDC {rank}",
                "originator_group": (
                    "Não identificado" if rank == 1 else f"Originador {rank}"
                ),
                "registered_volume_brl": float(16 - rank),
                "leader_name": (
                    "ITAU BBA ASSESSORIA FINANCEIRA S.A."
                    if rank == 1
                    else "OUTRO COORDENADOR"
                ),
                "ibba_coord_lead": rank == 1,
                "ibba_coord_lead_label": "Sim" if rank == 1 else "Não",
                "distribution_regime": (
                    "Garantia Firme de Colocação"
                    if rank == 1
                    else "Melhores Esforços"
                ),
                "firm_commitment": rank == 1,
                "firm_commitment_label": "Sim" if rank == 1 else "Não",
                "publico": "Profissional",
                "investor_count": rank,
                "metadata_matched": True,
                "status": "Oferta Encerrada",
                "offer_type": "PRIMARIA",
                "security": "Cotas de FIDC",
                "source_url": "https://dados.cvm.gov.br/",
                "scope": "Cotas de FIDC | oferta primária | Oferta Encerrada",
            }
            for period_order, period in (
                (2, "2025 FY"),
                (3, "2026 jan-jun"),
            )
            for rank in range(1, 16)
        ],
        "closed_offer_top15_summary": [
            {
                "period_label": period,
                "period_closed_offers": 100,
                "period_registered_volume_brl": 200.0,
                "top15_offers": 15,
                "top15_registered_volume_brl": 120.0,
                "top15_share_of_period_volume": 0.6,
                "ibba_lead_offers_top15": 1,
                "ibba_lead_volume_top15_brl": 15.0,
                "ibba_lead_share_top15_volume": 0.125,
                "firm_commitment_offers_top15": 1,
                "firm_commitment_volume_top15_brl": 15.0,
                "ibba_firm_commitment_offers_top15": 1,
                "ibba_firm_commitment_volume_top15_brl": 15.0,
                "investor_count_methodology": "soma dos campos Num_Invest_*",
                "ranking_methodology": "volume desc; offer_id asc",
            }
            for period in ("2025 FY", "2026 jan-jun")
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
        "conclusion_metrics": {
            "competencia": "2026-05",
            "btg_bank_cohort_listed_roots": 1,
            "btg_bank_cohort_observed_funds": 1,
            "btg_bank_cohort_pl_brl": 1.0,
            "btg_bank_cohort_combo_funds": 1,
            "btg_bank_cohort_combo_pl_brl": 1.0,
        },
    }


def test_payload_schema_and_required_historical_comparisons_are_versioned() -> None:
    assert PAYLOAD_SCHEMA == "fidc_revision_artifact_payload_v6"
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
        "delinquency_cohort_revision_summary",
        "delinquency_cohort_revision_transitions",
        "delinquency_cohort_revision_sensitivity",
        "acquiring_curation_detail",
        "card_taxonomy_audit",
        "card_taxonomy_summary",
        "provider_independent_ranking",
        "bank_fidc_evolution",
        "bank_fidc_detail",
        "btg_provider_ex_controlled_scenario",
        "acquiring_reclassified_mix",
        "closed_offers_annual",
        "closed_offers_monthly",
        "closed_offers_jan_june",
        "closed_offers_jan_may",
        "closed_offer_ticket_distribution",
        "closed_offer_placement_regime",
        "closed_offer_originators_2026",
        "closed_offer_top15",
        "closed_offer_top15_summary",
        "fixed_income_offer_comparison",
        "provider_history_cvm_coverage",
        "provider_history_cvm_links",
        "provider_history_cvm_detail",
        "conclusion_metrics",
    ):
        broken = dict(payload)
        broken.pop(key)
        with pytest.raises(RevisionBundlePublishError, match=key):
            validate_artifact_payload(broken, "2026-05")


def test_payload_rejects_card_taxonomy_with_fewer_than_44_funds() -> None:
    payload = deepcopy(_payload())
    payload["card_taxonomy_audit"].pop()

    with pytest.raises(RevisionBundlePublishError, match="exatamente 44 fundos"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_duplicate_card_taxonomy_cnpj() -> None:
    payload = deepcopy(_payload())
    rows = payload["card_taxonomy_audit"]
    rows[1]["cnpj_fundo_formatado"] = rows[0]["cnpj_fundo_formatado"]

    with pytest.raises(RevisionBundlePublishError, match="44 CNPJs únicos"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_non_continuous_card_taxonomy_rank() -> None:
    payload = deepcopy(_payload())
    payload["card_taxonomy_audit"][1]["ordem_materialidade"] = 1

    with pytest.raises(RevisionBundlePublishError, match="contínua de 1 a 44"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_card_taxonomy_enum_count_drift() -> None:
    payload = deepcopy(_payload())
    payload["card_taxonomy_audit"][0]["status_curadoria"] = "Fora de Adquirência"

    with pytest.raises(RevisionBundlePublishError, match="26 incluídos, 17 fora e 1"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_card_taxonomy_summary_count_drift() -> None:
    payload = deepcopy(_payload())
    payload["card_taxonomy_summary"]["fundos_incluidos_adquirencia"] = 25

    with pytest.raises(
        RevisionBundlePublishError,
        match="fundos_incluidos_adquirencia não reconcilia",
    ):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_card_taxonomy_summary_pl_drift() -> None:
    payload = deepcopy(_payload())
    payload["card_taxonomy_summary"]["pl_incluido_adquirencia_brl"] += 1.0

    with pytest.raises(
        RevisionBundlePublishError,
        match="pl_incluido_adquirencia_brl não reconcilia",
    ):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_card_taxonomy_without_document_url() -> None:
    payload = deepcopy(_payload())
    payload["card_taxonomy_audit"][0]["fonte_url"] = "N/D"

    with pytest.raises(RevisionBundlePublishError, match="fonte_url inválida"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_card_taxonomy_decision_divergence() -> None:
    payload = deepcopy(_payload())
    payload["card_taxonomy_audit"][0][
        "consistencia_decisao_reclassificacao"
    ] = "Divergente"

    with pytest.raises(RevisionBundlePublishError, match="divergência de decisão"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_non_continuous_originator_rank() -> None:
    payload = deepcopy(_payload())
    payload["closed_offer_originators_2026"][1]["rank"] = 1

    with pytest.raises(RevisionBundlePublishError, match="ranks contínuos e únicos"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_originators_out_of_volume_order() -> None:
    payload = deepcopy(_payload())
    payload["closed_offer_originators_2026"][1]["registered_volume_brl"] = 4.0

    with pytest.raises(RevisionBundlePublishError, match="volume decrescente"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_non_closed_offer_in_top15() -> None:
    payload = deepcopy(_payload())
    payload["closed_offer_top15"][0]["status"] = "Em análise"

    with pytest.raises(RevisionBundlePublishError, match="oferta não encerrada"):
        validate_artifact_payload(payload, "2026-05")


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
    assert first["checks"]["slides"] == 57
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
        "inadimplencia_coorte_revisao_resumo.csv",
        "inadimplencia_coorte_revisao_transicoes.csv",
        "inadimplencia_coorte_revisao_sensibilidade.csv",
    }.issubset(REQUIRED_ANALYSIS_FILES)
    assert "acquiring_taxonomy_curation.json" in REQUIRED_DATA_INPUTS
    assert "industry_closed_offer_ticket_distribution.csv" in REQUIRED_DATA_INPUTS
    assert "industry_closed_offer_ticket_cohort.csv.gz" in REQUIRED_DATA_INPUTS
    assert "industry_closed_offer_placement_regime.csv" in REQUIRED_DATA_INPUTS


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
