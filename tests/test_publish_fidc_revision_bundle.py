from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import pandas as pd
from openpyxl import Workbook

import scripts.publish_fidc_revision_bundle as revision_publisher
from scripts.build_fidc_industry_study import parse_args as parse_study_args
from scripts.build_fidc_revision_analysis import (
    parse_args as parse_revision_args,
    require_previous_table_ii,
)
from scripts.publish_fidc_revision_bundle import (
    ANALYSIS_MANIFEST_NAME,
    BUNDLE_MANIFEST_NAME,
    MATERIALIZED_PORTFOLIO_XLSX_NAME,
    MATERIALIZED_PPTX_NAME,
    MATERIALIZED_XLSX_NAME,
    EXPECTED_SLIDES,
    PAYLOAD_SCHEMA,
    REQUIRED_ANALYSIS_FILES,
    REQUIRED_NONEMPTY_ANALYSIS_FILES,
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
    validate_fic_detection_audit_provenance,
    validate_renderer_manifest,
    validate_source_presence_coverage,
    validate_user_facing_workbook_snapshot,
)


def test_fic_detection_audit_provenance_rejects_legacy_labels(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "industry_fic_detection_audit.csv"
    audit.write_text(
        "cnpj_fundo,fic_detection_method,fic_detection_evidence\n"
        "12345678000199,flag_cadastral,descrição antiga\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RevisionBundlePublishError,
        match="rótulos de proveniência legados",
    ):
        validate_fic_detection_audit_provenance(tmp_path)


def test_fic_detection_audit_provenance_accepts_declared_sources(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "industry_fic_detection_audit.csv"
    audit.write_text(
        "cnpj_fundo,fic_detection_method,fic_detection_evidence\n"
        "12345678000199,sinal_nominal_legado,Sinal nominal legado\n"
        "98765432000199,informe_mensal,Informe Mensal Estruturado\n",
        encoding="utf-8",
    )

    validate_fic_detection_audit_provenance(tmp_path)


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


def _market_offer_reconciliation_fixture() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for period_order, period in enumerate(
        ("2023 FY", "2024 FY", "2025 FY", "2026 jan-jun"),
        start=1,
    ):
        for instrument_order, instrument in enumerate(
            ("Debêntures", "FIDCs", "CRI", "Notas comerciais", "CRA"),
            start=1,
        ):
            rows.append(
                {
                    "period_order": period_order,
                    "period_label": period,
                    "instrument_order": instrument_order,
                    "instrument_label": instrument,
                    "cvm_registered_volume_brl": 1.0,
                    "cvm_harmonization_volume_brl": 0.5 if instrument == "Debêntures" else 0.0,
                    "cvm_harmonized_volume_brl": 1.5 if instrument == "Debêntures" else 1.0,
                    "anbima_closed_volume_brl": 1.0,
                    "raw_gap_brl": 0.0,
                    "raw_gap_pct": 0.0,
                    "harmonized_gap_brl": 0.5 if instrument == "Debêntures" else 0.0,
                    "harmonized_gap_pct": 0.5 if instrument == "Debêntures" else 0.0,
                    "primary_explanation": "Reconciliação por instrumento.",
                    "cvm_source_url": "https://dados.cvm.gov.br/",
                    "cvm_source_as_of_date": "2026-07-24",
                    "cvm_metric": "Valor registrado",
                    "cvm_scope": "Ofertas públicas primárias encerradas.",
                    "anbima_source_url": "https://data.anbima.com.br/",
                    "anbima_source_snapshot": "jun/26",
                    "anbima_source_sheet": "02-02-Vlr",
                    "anbima_metric": "Valor Encerrado",
                    "anbima_scope": "Ofertas públicas encerradas.",
                    "limitation": "Série sujeita a retificações.",
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


def _issuance_taxonomy_fixture() -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    periods = (
        ("2023", "2023"),
        ("2024", "2024"),
        ("2025", "2025"),
        ("jun25", "jan–jun/25"),
        ("jun26", "jan–jun/26"),
    )
    categories = (
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    )
    long_rows = [
        {
            "period_key": key,
            "period_label": label,
            "categoria": category,
            "volume_brl": 0.2,
            "share": 0.25,
        }
        for key, label in periods
        for category in categories
    ]
    wide_rows = [
        {
            "Categoria": category,
            "2023 (R$ bi)": 0.2 / 1e9,
            "2023 (%)": 0.25,
        }
        for category in categories
    ]
    reconciliation = [
        {
            "period_key": key,
            "period_label": label,
            "total_brl": 0.8,
            "fic_excluded_brl": 0.2,
            "emitted_volume_brl": 1.0,
        }
        for key, label in periods
    ]
    return long_rows, wide_rows, reconciliation


def _emission_field_coverage_fixture() -> list[dict[str, object]]:
    floors = {
        "originador": 0.01,
        "cedente": 0.15,
        "subordinacao_minima": 0.01,
        "remuneracao_por_tipo_cota": 0.0,
        "sacado": 0.01,
    }
    rows: list[dict[str, object]] = []
    for type_name in (
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    ):
        for period in ("2025-12", "2026-05"):
            table = f"{type_name} · {period}"
            for field, floor in floors.items():
                filled = 3 if field == "cedente" else 1
                rows.append(
                    {
                        "tabela": table,
                        "tipo": type_name,
                        "competencia": period,
                        "campo": field,
                        "linhas_total": 15,
                        "depois_com_dado": filled,
                        "depois_cobertura_pct": filled / 15,
                        "nd_depois": 15 - filled,
                        "piso_publicacao_pct": floor,
                        "piso_atendido": True,
                    }
                )
    return rows


def _emission_field_audit_fixture() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    serial = 1
    for type_name in (
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    ):
        for period in ("2025-12", "2026-05"):
            for rank in range(1, 16):
                cnpj = f"41{serial:012d}"
                serial += 1
                rows.append(
                    {
                        "bloco": "slides 10–17",
                        "tabela": f"{type_name} · {period}",
                        "cnpj": cnpj,
                        "originador": (
                            "Originador documentado" if rank == 1 else "N/D"
                        ),
                        "cedente": (
                            "Cedente legal declarado" if rank <= 3 else "N/D"
                        ),
                        "subordinacao_minima": (
                            "Jr. 10,0%" if rank == 1 else "N/D"
                        ),
                        "preco_por_tipo_cota": (
                            "Cota sênior: R$ 1.000,00" if rank == 1 else "N/D"
                        ),
                        "remuneracao_por_tipo_cota": (
                            "Cota sênior: CDI + 1,00% a.a."
                            if rank == 1
                            else "N/D"
                        ),
                        "sacado": "Sacado documentado" if rank == 1 else "N/D",
                        "fonte_remuneracao": (
                            f"regulamento DOC-{cnpj} · p. 10"
                            if rank == 1
                            else "N/D"
                        ),
                    }
                )
    rows.extend(
        {
            "bloco": "slides 21–22",
            "tabela": "Ofertas",
            "cnpj": f"42{index:012d}",
            "remuneracao_por_tipo_cota": "N/D",
            "fonte_remuneracao": "N/D",
        }
        for index in range(1, 61)
    )
    return rows


def _emission_field_remuneration_evidence_fixture() -> list[dict[str, object]]:
    return [
        {
            "cnpj": row["cnpj"],
            "field": "remuneracao_alvo",
            "value": row["remuneracao_por_tipo_cota"],
            "source_kind": "regulamento",
            "source_id": f"DOC-{row['cnpj']}",
            "document_class": "regulamento",
            "document_date": "2025-12-01",
            "page": "10",
            "status": "encontrado_explicito",
            "nature": "rentabilidade-alvo documentada · Cota sênior",
        }
        for row in _emission_field_audit_fixture()
        if row.get("bloco") == "slides 10–17"
        and row.get("remuneracao_por_tipo_cota") != "N/D"
    ]


def _payload() -> dict[str, object]:
    card_rows = _card_taxonomy_rows()
    type_names = (
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    )
    top20_by_type = [
        {
            "tipo_exibicao": type_name,
            "rank_tipo": rank,
            "cnpj_fundo": f"{type_index + 1:02d}{rank:012d}",
            "denominacao": f"FIDC {type_name} {rank}",
            "pl": float(21 - rank),
            "competencia_pl": "2026-05",
            "pl_anterior_positivo": True,
            "administrador": "Administrador",
            "gestor": "Gestor",
            "custodiante": "Custodiante",
            "cedente_originador": "N/D",
            "cedente_status": "regulamento_nao_localizado_no_corpus_versionado",
            "regulamento_id": "",
            "regulamento_data": "",
            "regulamento_url": "https://example.com/fundosnet",
            "pagina_clausula": "N/D",
            "evidencia_cedente": "",
            "limitacao_cedente": "documento não localizado",
        }
        for type_index, type_name in enumerate(type_names)
        for rank in range(1, 21)
    ]
    historical_periods = ("2023-12", "2024-12", "2025-12", "2026-05")
    historical_top20 = []
    for period_index, period in enumerate(historical_periods, start=1):
        for type_index, type_name in enumerate(type_names, start=1):
            for rank in range(1, 21):
                cnpj = f"{period_index:02d}{type_index:02d}{rank:010d}"
                historical_top20.append(
                    {
                        "competencia": period,
                        "tipo_exibicao": type_name,
                        "rank_tipo": rank,
                        "cnpj_fundo": cnpj,
                        "review_id": cnpj,
                    }
                )
    top100_outros = [
        {
            "competencia_pl": "2026-05",
            "rank_outros_slide": rank,
            "cnpj_fundo": f"99{rank:012d}",
            "denominacao": f"FIDC Outros {rank}",
            "pl": float(101 - rank),
            "bucket_slide_atual": "Outros",
            "anbima_tipo_oficial": "Outros",
            "anbima_foco_oficial": "Multicarteira Outros",
            "tabela_ii_reportada": "N/D",
            "tabela_ii_dominante": "N/D",
            "tabela_ii_multisegmento": False,
            "documento_id_base": "",
            "documento_data_base": "",
            "documento_url_base": "https://example.com/fundosnet",
            "evidencia_documental": "",
            "cedente_originador_expresso": "N/D",
            "tipo_anbima_sugerido": "",
            "foco_anbima_sugerido": "",
            "tabela_ii_sugerida": "N/D",
            "perimeter_proposal": "",
            "is_fic_fidc_sugerido": False,
            "pl_correcao_perimetro_candidata_brl": 0.0,
            "confianca_base": "baixa",
            "status_revisao_base": "sem_regulamento_versionado",
            "motivo_validacao_manual_base": "documento não localizado",
            "acao_status": "pendente",
            "anbima_tipo_curado": "Outros",
            "anbima_foco_curado": "Multicarteira Outros",
            "tabela_ii_curada": "N/D",
            "taxonomy_review_applied": False,
        }
        for rank in range(1, 101)
    ]
    issuance_taxonomy, issuance_taxonomy_table, issuance_reconciliation = (
        _issuance_taxonomy_fixture()
    )
    return {
        "schema_version": PAYLOAD_SCHEMA,
        "latest_complete": "2026-05",
        "offers_as_of": "2026-07-15",
        "top20_fidcs": [{}] * 20,
        "top20_outros": [{}] * 20,
        "profiles": [{}] * 20,
        "emission_field_audit": _emission_field_audit_fixture(),
        "emission_field_coverage": _emission_field_coverage_fixture(),
        "emission_field_remuneration_evidence": (
            _emission_field_remuneration_evidence_fixture()
        ),
        "portfolio_export_carteira_101": [
            {"cnpj": f"10{index:012d}"} for index in range(1, 102)
        ],
        "portfolio_export_cases_99": [
            {"cnpj": f"10{index:012d}"} for index in range(1, 100)
        ],
        "portfolio_export_flagships": [
            {"cnpj": f"20{index:012d}"} for index in range(1, 48)
        ],
        "top100_fidcs_middle_market": [
            *[
                {
                    "ordem_exportacao": index,
                    "rank_geral": index,
                    "inclusao_criterio": "Top 100 por PL ex-FIC",
                    "cnpj": f"30{index:012d}",
                    "nome_fundo": f"FIDC Top 100 {index}",
                    "pl_brl": float(101 - index),
                    "middle_market_status": "dados_insuficientes",
                }
                for index in range(1, 101)
            ],
            {
                "ordem_exportacao": 101,
                "rank_geral": 101,
                "inclusao_criterio": "Inclusão 2026 documentada",
                "cnpj": "44302112000172",
                "nome_fundo": "Citi-Bayer",
                "pl_brl": 1.0,
                "subordinacao_atual_pl": 0.20,
                "minimo_subordinacao_junior": 0.10,
                "minimo_subordinacao_estrutural": 0.15,
                "natureza_minimo": "Suporte combinado júnior + mezanino",
                "preco_cota_emissao_brl": 1_000.0,
                "oferta_id": "CVM-OFERTA-CITI-BAYER",
                "processo_cvm": "SRE/2026/CITI-BAYER",
                "data_registro": "2026-06-01",
                "data_encerramento": "2026-06-30",
                "cedente_originador": "Bayer",
                "sacado_devedor": "Produtores rurais",
                "tipo_recebivel": "Crédito corporativo agrícola",
                "middle_market_status": "Indício de crédito corporativo; porte N/D",
                "documento_id": "REG-CITI-BAYER",
                "documento_emissao_id": "EMIS-CITI-BAYER",
                "fonte_regulamento": "FundosNet/B3",
                "fonte_emissao": "CVM Ofertas",
            },
            {
                "ordem_exportacao": 102,
                "rank_geral": 102,
                "inclusao_criterio": "Inclusão 2026 documentada",
                "cnpj": "61669748000176",
                "nome_fundo": "Lavoro",
                "pl_brl": 1.0,
                "subordinacao_atual_pl": 0.20,
                "minimo_subordinacao_junior": 0.10,
                "minimo_subordinacao_estrutural": 0.15,
                "natureza_minimo": "Suporte combinado júnior + mezanino",
                "preco_cota_emissao_brl": 1_000.0,
                "oferta_id": "CVM-OFERTA-LAVORO",
                "processo_cvm": "SRE/2026/LAVORO",
                "data_registro": "2026-06-01",
                "data_encerramento": "2026-06-30",
                "cedente_originador": "Lavoro",
                "sacado_devedor": "Produtores rurais",
                "tipo_recebivel": "Crédito corporativo agrícola",
                "middle_market_status": "Indício de crédito corporativo; porte N/D",
                "documento_id": "REG-LAVORO",
                "documento_emissao_id": "EMIS-LAVORO",
                "fonte_regulamento": "FundosNet/B3",
                "fonte_emissao": "CVM Ofertas",
            },
        ],
        "top100_fidcs_middle_market_summary": {
            "fundos": 102,
            "top100_fundos": 100,
            "adicionais_2026_fundos": 2,
            "top100_pl_brl": 5050.0,
            "top100_share_pl_ex_fic": 0.5,
        },
        "portfolio_export_coverage": [
            {"coorte": "Carteira 101", "campo": "sub_pl_atual"}
        ],
        "portfolio_export_gaps": [
            {"coorte": "Carteira 101", "cnpj": "10000000000001"}
        ],
        "portfolio_export_manual_audit": [
            {
                "raiz_cnpj_foto": "10000000",
                "cnpj": "10000000000001",
                "status_resolucao_cnpj": "correspondencia_unica",
                "quantidade_candidatos_cnpj": 1,
            }
        ],
        "portfolio_export_dictionary": [
            {
                "campo": "preco_cota_display",
                "descricao": "Preço unitário da cota por classe ou série",
            }
        ],
        "portfolio_export_price_evidence": [
            {
                "cnpj": "10000000000001",
                "class_series": "Cota Sênior",
                "price_display": "R$ 1.000,00",
                "price_nature": "valor unitário de emissão",
            }
        ],
        "carteira_101_document_audit": [
            {
                "cnpj": f"10{index:012d}",
                "status": "concluído",
            }
            for index in range(1, 102)
        ],
        "carteira_101_document_coverage": [
            {"campo": "minimo_junior", "depois_com_dado": 83}
        ],
        "carteira_101_document_evidence": [
            {
                "cnpj": "10000000000001",
                "field": "minimo_junior",
                "status": "encontrado",
            }
        ],
        "carteira_101_document_prices": [
            {
                "cnpj": "10000000000001",
                "class_series": "Cota Sênior",
                "price_display": "R$ 1.000,00",
                "price_nature": "valor unitário de emissão",
            }
        ],
        "carteira_101_document_checkpoint": [
            {
                "cnpj": f"10{index:012d}",
                "status": "concluído",
                "online_status": "consultado",
            }
            for index in range(1, 102)
        ],
        "carteira_101_document_manifest": {
            "schema_version": "carteira-101-document-audit/v2",
            "online_requested": True,
            "online_consulted_cnpjs": 101,
            "online_error_cnpjs": 0,
            "rules": {
                "price_definition": (
                    "VNU/preço unitário por classe ou série; "
                    "remuneração e quantidade excluídas"
                )
            },
        },
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
        "carteira_1_taxonomy_history": [
            {
                "competencia": competencia,
                "period_label": period_label,
                "period_order": period_order,
                "category_order": category_order,
                "anbima_tipo": anbima_tipo,
                "portfolio_pl_brl": 0.25,
                "portfolio_share": 0.25,
                "portfolio_funds": 1,
                "portfolio_total_brl": 1.0,
                "scope_cnpjs": 4,
                "observed_cnpjs": 4,
                "coverage_scope_share": 1.0,
                "market_pl_brl": 0.25,
                "market_share": 0.25,
                "market_total_brl": 1.0,
                "portfolio_growth_since_start": 0.0,
                "market_growth_since_start": 0.0,
                "portfolio_share_delta_pp": 0.0,
                "market_share_delta_pp": 0.0,
            }
            for period_order, (competencia, period_label) in enumerate(
                (
                    ("2023-12", "dez/23"),
                    ("2024-12", "dez/24"),
                    ("2025-12", "dez/25"),
                    ("2026-05", "mai/26"),
                )
            )
            for category_order, anbima_tipo in enumerate(type_names)
        ],
        "carteira_1_taxonomy_summary": {
            "portfolio": "Carteira 1",
            "scope_cnpjs": 4,
            "latest_observed_cnpjs": 4,
            "latest_total_brl": 1.0,
            "source": "fixture",
            "methodology": "ausente permanece ausente",
        },
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
        "delinquency_dispersion": [
            {
                "competencia": "2026-05",
                "tipo_recebivel_tabela_ii": "Financeiro",
                "fundos_reportantes_inadimplencia": 1,
                "inadimplencia_total_subcategoria_brl": 1.0,
                "top1_inadimplencia_brl": 1.0,
                "top1_share": 1.0,
                "top3_inadimplencia_brl": 1.0,
                "top3_share": 1.0,
                "top5_inadimplencia_brl": 1.0,
                "top5_share": 1.0,
                "hhi": 1.0,
                "gini": 0.0,
                "leitura_concentracao": "Concentrada em poucos fundos",
                "fonte": "CVM",
            }
        ],
        "delinquency_dispersion_summary": {
            "fundos_reportantes_inadimplencia_positiva": 1,
            "pl_reportantes_inadimplencia_positiva_brl": 1.0,
        },
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
        "acquiring_anbima_review": [
            {
                "cnpj_fundo_formatado": "10.000.000/0000-01",
                "denominacao": "FIDC A",
                "tipo_anbima_atual": "Outros",
                "foco_anbima_atual": "N/D",
                "categoria_referencia_sugerida": "Outros",
                "base_alterada": "Não",
                "criterio_sugestao": "correspondência literal",
            }
        ],
        "acquiring_anbima_review_summary": {"fundos_filtrados": 1},
        "taxonomy_top15": [
            {
                "visao": "Tipo ANBIMA",
                "rank": 1,
                "cnpj_fundo": "10000000000001",
                "denominacao": "FIDC A",
                "taxonomia_atual": "Outros",
                "pl_brl": 1.0,
                "competencia": "2026-05",
                "fonte": "ANBIMA",
                "metodologia": "classificação atual preservada",
            }
        ],
        "top20_by_anbima_type": top20_by_type,
        "top20_by_anbima_type_coverage": [
            {
                "tipo_exibicao": type_name,
                "fundos": 20,
                "administrador_preenchido": 20,
                "gestor_preenchido": 20,
                "custodiante_preenchido": 20,
                "cedente_curadoria_concluida": 0,
                "regulamento_local_sem_curadoria": 0,
                "sem_regulamento_local": 20,
                "competencia_pl": "2026-05",
                "competencia_anterior_verificada": "2026-04",
                "fundos_pl_anterior_positivo": 20,
            }
            for type_name in type_names
        ],
        "top20_taxonomy_review": historical_top20,
        "top100_outros_review": top100_outros,
        "top100_outros_summary": {
            "outros_oficial_brl": 1000.0,
            "outros_curado_brl": 1000.0,
            "reducao_aprovada_brl": 0.0,
            "top100_outros_brl": 5050.0,
            "candidatos_documentais_brl": 0.0,
            "candidatos_reclassificacao_tipo_brl": 0.0,
            "candidatos_correcao_perimetro_brl": 0.0,
            "outros_pos_candidatos_brl": 1000.0,
            "residual_minimo_top100_brl": -4050.0,
            "gap_meta_minimo_top100_brl": 0.0,
            "meta_atingivel_top100": True,
        },
        "taxonomy_review_meta": {
            "ledger_sha256": "0" * 64,
            "audit_sha256": "1" * 64,
            "ledger_path": "data/industry_study/taxonomy_review_actions.csv",
            "audit_path": "data/industry_study/taxonomy_review_audit.csv",
        },
        "numeric_locale_audit": [
            {"artefato": "PPTX", "ponto": "tabelas", "padrao": "pt-BR"}
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
            for year in (2022, 2023, 2024, 2025, 2026)
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
        "market_offer_reconciliation": (
            _market_offer_reconciliation_fixture()
        ),
        "issuance_taxonomy": issuance_taxonomy,
        "issuance_taxonomy_table": issuance_taxonomy_table,
        "issuance_taxonomy_reconciliation": issuance_reconciliation,
        "bcb_expanded_credit": [
            {
                "competencia": "2026-05",
                "period_label": "05/26",
                "expanded_credit_total_brl": 100.0,
                "private_expanded_credit_total_brl": 80.0,
                "loans_brl": 40.0,
                "public_debt_brl": 20.0,
                "private_debt_brl": 10.0,
                "fidc_receivables_brl": 5.0,
                "other_securitization_brl": 5.0,
                "external_debt_brl": 20.0,
                "source_bcb": "BCB SGS 28183-28192",
                "source_cvm": "CVM Informe Mensal",
                "methodology": "Pilha reconciliada",
            }
        ],
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
                "ibba_participant": rank in {1, 2},
                "ibba_participant_label": (
                    "Sim" if rank in {1, 2} else "Não"
                ),
                "ibba_participant_entities": (
                    "ITAÚ BBA ASSESSORIA FINANCEIRA S.A."
                    if rank in {1, 2}
                    else ""
                ),
                "ibba_participant_roles": (
                    "Coordenador" if rank in {1, 2} else ""
                ),
                "ibba_participation_source": "participantes oficiais SRE",
                "participants_source_url": (
                    f"https://web.cvm.gov.br/sre-publico-cvm/"
                    f"rest/sitePublico/pesquisar/participantes/{period_order}{rank:02d}"
                ),
                "closing_document_url": "",
                "distribution_regime": (
                    "Garantia Firme de Colocação"
                    if rank == 1
                    else "Melhores Esforços"
                ),
                "firm_commitment": rank == 1,
                "firm_commitment_label": "Sim" if rank == 1 else "Não",
                "publico": "Profissional",
                "investor_count": rank,
                "investor_categories": f"Pessoa física: {rank}",
                "coordinator_entities": "COORDENADOR A",
                "firm_commitment_coordinators": (
                    "COORDENADOR A" if rank == 1 else "Não aplicável"
                ),
                "firm_commitment_amount_by_coordinator": "N/D",
                "firm_commitment_source_limitation": "API SRE sem rateio.",
                "rating_agency": "N/D",
                "rating_assigned": "N/D",
                "rating_scope": "N/D",
                "rating_source_type": "N/D",
                "rating_source_url": "N/D",
                "rating_match_status": "sem documento público verificável",
                "rating_evidence": "Nenhum documento conciliável localizado.",
                "rating_availability_status": "sem documento público localizado",
                "rating_limitation": "Nenhum documento localizado.",
                "metadata_matched": True,
                "status": "Oferta Encerrada",
                "offer_type": "PRIMARIA",
                "security": "Cotas de FIDC",
                "source_url": "https://dados.cvm.gov.br/",
                "scope": "Cotas de FIDC | oferta primária | Oferta Encerrada",
            }
            for period_order, period, row_count in (
                (0, "2022 FY parcial", 7),
                (1, "2023 FY", 15),
                (2, "2024 FY", 15),
                (3, "2025 FY", 15),
                (4, "2026 jan-jun", 15),
            )
            for rank in range(1, row_count + 1)
        ],
        "closed_offer_top15_summary": [
            {
                "period_label": period,
                "period_closed_offers": 100,
                "period_registered_volume_brl": 200.0,
                "top15_offers": row_count,
                "top15_registered_volume_brl": 84.0 if row_count == 7 else 120.0,
                "top15_share_of_period_volume": 0.42 if row_count == 7 else 0.6,
                "ibba_lead_offers_top15": 1,
                "ibba_lead_volume_top15_brl": 15.0,
                "ibba_lead_share_top15_volume": 0.125,
                "ibba_participation_offers_top15": 2,
                "ibba_participation_volume_top15_brl": 29.0,
                "ibba_participation_share_top15_volume": 29.0 / 120.0,
                "firm_commitment_offers_top15": 1,
                "firm_commitment_volume_top15_brl": 15.0,
                "ibba_firm_commitment_offers_top15": 1,
                "ibba_firm_commitment_volume_top15_brl": 15.0,
                "investor_count_methodology": "soma dos campos Num_Invest_*",
                "ranking_methodology": "volume desc; offer_id asc",
                "automatic_rite_registered_volume_share": 0.0 if row_count == 7 else 1.0,
                "comparability_status": "parcial_não_comparável" if row_count == 7 else "comparável_todos_os_ritos",
                "coverage_note": "2022 parcial" if row_count == 7 else "comparável",
            }
            for period, row_count in (
                ("2022 FY parcial", 7),
                ("2023 FY", 15),
                ("2024 FY", 15),
                ("2025 FY", 15),
                ("2026 jan-jun", 15),
            )
        ],
        "top20_outros_regulation_review": [{} for _ in range(20)],
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
    assert PAYLOAD_SCHEMA == "fidc_revision_artifact_payload_v10"
    payload = _payload()
    validate_artifact_payload(payload, "2026-05")
    assert len(payload["portfolio_export_cases_99"]) == 99
    top100_plus2 = payload["top100_fidcs_middle_market"]
    assert len(top100_plus2) == 102
    assert {row["cnpj"] for row in top100_plus2[-2:]} == {
        "44302112000172",
        "61669748000176",
    }


def test_payload_rejects_incomplete_emission_field_coverage_matrix() -> None:
    payload = deepcopy(_payload())
    payload["emission_field_coverage"].pop()

    with pytest.raises(
        RevisionBundlePublishError,
        match=r"40 linhas \(8 tabelas x 5 campos\); recebeu 39",
    ):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_duplicate_emission_field_coverage_key() -> None:
    payload = deepcopy(_payload())
    payload["emission_field_coverage"][1] = deepcopy(
        payload["emission_field_coverage"][0]
    )

    with pytest.raises(RevisionBundlePublishError, match="duplica"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_all_nd_emission_field_column_even_with_waiver_text() -> None:
    payload = deepcopy(_payload())
    row = payload["emission_field_coverage"][0]
    for audit_row in payload["emission_field_audit"]:
        if audit_row.get("tabela") == row["tabela"]:
            audit_row[row["campo"]] = "N/D"
    row.update(
        {
            "depois_com_dado": 0,
            "depois_cobertura_pct": 0.0,
            "nd_depois": 15,
            "piso_publicacao_pct": 0.01,
            "piso_atendido": False,
            "waiver": "texto sem configuração de waiver aprovada",
        }
    )

    with pytest.raises(RevisionBundlePublishError, match="coluna toda N/D"):
        validate_artifact_payload(payload, "2026-05")


def _payload_with_approved_outros_originator_exceptions() -> dict[str, object]:
    payload = deepcopy(_payload())
    for audit_row in payload["emission_field_audit"]:
        if audit_row.get("tabela") == "Outros · 2026-05":
            audit_row["tabela"] = "Outros · 2026-06"
        if audit_row.get("tabela") in {"Outros · 2025-12", "Outros · 2026-06"}:
            audit_row["originador"] = "N/D"
    reason = (
        "documentos identificados não individualizam originador econômico; "
        "cedentes legais permanecem em coluna separada"
    )
    for row in payload["emission_field_coverage"]:
        if row.get("tabela") == "Outros · 2026-05":
            row["tabela"] = "Outros · 2026-06"
            row["competencia"] = "2026-06"
        if row.get("tabela") in {"Outros · 2025-12", "Outros · 2026-06"} and row.get(
            "campo"
        ) == "originador":
            row.update(
                {
                    "depois_com_dado": 0,
                    "depois_cobertura_pct": 0.0,
                    "nd_depois": 15,
                    "piso_publicacao_pct": 0.0,
                    "piso_atendido": True,
                    "excecao_publicacao": reason,
                }
            )
    return payload


def test_payload_accepts_only_the_two_documented_outros_originator_exceptions() -> None:
    payload = _payload_with_approved_outros_originator_exceptions()

    validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_outros_originator_exception_with_different_reason() -> None:
    payload = _payload_with_approved_outros_originator_exceptions()
    row = next(
        item
        for item in payload["emission_field_coverage"]
        if item["tabela"] == "Outros · 2025-12" and item["campo"] == "originador"
    )
    row["excecao_publicacao"] = "waiver genérico"

    with pytest.raises(RevisionBundlePublishError, match="piso inválido"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_emission_field_coverage_below_declared_floor() -> None:
    payload = deepcopy(_payload())
    row = next(
        item
        for item in payload["emission_field_coverage"]
        if item["campo"] == "cedente"
    )
    row.update(
        {
            "depois_com_dado": 2,
            "depois_cobertura_pct": 2 / 15,
            "nd_depois": 13,
            "piso_atendido": False,
        }
    )
    changed = False
    for audit_row in payload["emission_field_audit"]:
        if (
            audit_row.get("tabela") == row["tabela"]
            and audit_row.get("cedente") != "N/D"
            and not changed
        ):
            audit_row["cedente"] = "N/D"
            changed = True

    with pytest.raises(RevisionBundlePublishError, match="abaixo do piso"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_keeps_nominal_unit_price_separate_from_target_remuneration() -> None:
    payload = deepcopy(_payload())

    validate_artifact_payload(payload, "2026-05")

    first = next(
        row
        for row in payload["emission_field_audit"]
        if row.get("bloco") == "slides 10–17"
        and row.get("remuneracao_por_tipo_cota") != "N/D"
    )
    assert first["preco_por_tipo_cota"] == "Cota sênior: R$ 1.000,00"
    assert first["remuneracao_por_tipo_cota"] == "Cota sênior: CDI + 1,00% a.a."


def test_payload_allows_a_target_remuneration_page_with_documented_zero_coverage() -> None:
    payload = deepcopy(_payload())
    table = "Fomento Mercantil · 2025-12"
    coverage = next(
        row
        for row in payload["emission_field_coverage"]
        if row["tabela"] == table
        and row["campo"] == "remuneracao_por_tipo_cota"
    )
    coverage.update(
        {
            "depois_com_dado": 0,
            "depois_cobertura_pct": 0.0,
            "nd_depois": 15,
            "piso_publicacao_pct": 0.0,
            "piso_atendido": True,
        }
    )
    for audit_row in payload["emission_field_audit"]:
        if audit_row.get("tabela") == table:
            audit_row["remuneracao_por_tipo_cota"] = "N/D"
            audit_row["fonte_remuneracao"] = "N/D"

    validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_target_remuneration_column_entirely_nd() -> None:
    payload = deepcopy(_payload())
    for coverage in payload["emission_field_coverage"]:
        if coverage.get("campo") == "remuneracao_por_tipo_cota":
            coverage.update(
                {
                    "depois_com_dado": 0,
                    "depois_cobertura_pct": 0.0,
                    "nd_depois": 15,
                    "piso_publicacao_pct": 0.0,
                    "piso_atendido": True,
                }
            )
    for audit_row in payload["emission_field_audit"]:
        if audit_row.get("bloco") == "slides 10–17":
            audit_row["remuneracao_por_tipo_cota"] = "N/D"
            audit_row["fonte_remuneracao"] = "N/D"

    with pytest.raises(
        RevisionBundlePublishError,
        match="coluna inteira de remuneração-alvo",
    ):
        validate_artifact_payload(payload, "2026-05")


@pytest.mark.parametrize(
    "invalid_value",
    (
        "Cota sênior: R$ 1.000,00",
        "Cota sênior · VNU: CDI + 1,00%",
        "Taxa média da carteira: CDI + 7,00%",
    ),
)
def test_payload_rejects_nominal_or_portfolio_values_as_target_remuneration(
    invalid_value: str,
) -> None:
    payload = deepcopy(_payload())
    row = next(
        item
        for item in payload["emission_field_audit"]
        if item.get("bloco") == "slides 10–17"
        and item.get("remuneracao_por_tipo_cota") != "N/D"
    )
    row["remuneracao_por_tipo_cota"] = invalid_value

    with pytest.raises(RevisionBundlePublishError, match="mistura remuneração-alvo"):
        validate_artifact_payload(payload, "2026-05")


@pytest.mark.parametrize(
    "invalid_source",
    (
        "N/D — sem documento identificado",
        "FundosNet/B3",
    ),
)
def test_payload_rejects_target_remuneration_without_identified_document(
    invalid_source: str,
) -> None:
    payload = deepcopy(_payload())
    row = next(
        item
        for item in payload["emission_field_audit"]
        if item.get("bloco") == "slides 10–17"
        and item.get("remuneracao_por_tipo_cota") != "N/D"
    )
    row["fonte_remuneracao"] = invalid_source

    with pytest.raises(RevisionBundlePublishError, match="documento identificado"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_candidate_target_remuneration_evidence() -> None:
    payload = deepcopy(_payload())
    evidence = payload["emission_field_remuneration_evidence"][0]
    evidence["status"] = "candidate_extraction"
    evidence["source_kind"] = "candidate_extraction"

    with pytest.raises(RevisionBundlePublishError, match="extração não aprovada"):
        validate_artifact_payload(payload, "2026-05")


@pytest.mark.parametrize(
    "field",
    (
        "subordinacao_atual_pl",
        "minimo_subordinacao_estrutural",
        "preco_cota_emissao_brl",
        "cedente_originador",
        "sacado_devedor",
        "tipo_recebivel",
        "documento_id",
        "documento_emissao_id",
        "fonte_regulamento",
        "fonte_emissao",
    ),
)
def test_payload_rejects_top100_plus2_addition_without_documentary_field(
    field: str,
) -> None:
    payload = deepcopy(_payload())
    citi_bayer = next(
        row
        for row in payload["top100_fidcs_middle_market"]
        if row["cnpj"] == "44302112000172"
    )
    citi_bayer[field] = "N/D"

    with pytest.raises(
        RevisionBundlePublishError,
        match=rf"inclusão 2026 44302112000172 sem campos documentais: {field}",
    ):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_unapproved_top100_plus2_addition() -> None:
    payload = deepcopy(_payload())
    payload["top100_fidcs_middle_market"][-1]["cnpj"] = "99999999000199"

    with pytest.raises(
        RevisionBundlePublishError,
        match="deve acrescentar somente Citi-Bayer e Lavoro",
    ):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_incomplete_portfolio_export_cohorts() -> None:
    payload = deepcopy(_payload())
    payload["portfolio_export_carteira_101"].pop()

    with pytest.raises(RevisionBundlePublishError, match="101 linhas"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_duplicate_portfolio_export_cnpj() -> None:
    payload = deepcopy(_payload())
    payload["portfolio_export_flagships"][1]["cnpj"] = payload[
        "portfolio_export_flagships"
    ][0]["cnpj"]

    with pytest.raises(RevisionBundlePublishError, match="47 CNPJs únicos"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_document_audit_cnpj_set_divergence() -> None:
    payload = deepcopy(_payload())
    payload["carteira_101_document_audit"][0]["cnpj"] = "99000000000000"

    with pytest.raises(
        RevisionBundlePublishError,
        match="diverge dos CNPJs da Carteira 101",
    ):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_duplicate_document_checkpoint_cnpj() -> None:
    payload = deepcopy(_payload())
    payload["carteira_101_document_checkpoint"][1]["cnpj"] = payload[
        "carteira_101_document_checkpoint"
    ][0]["cnpj"]

    with pytest.raises(
        RevisionBundlePublishError,
        match="checkpoint documental não preserva 101 CNPJs únicos",
    ):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_ambiguous_manual_cnpj_resolution() -> None:
    payload = deepcopy(_payload())
    payload["portfolio_export_manual_audit"][0][
        "status_resolucao_cnpj"
    ] = "ambigua"
    payload["portfolio_export_manual_audit"][0][
        "quantidade_candidatos_cnpj"
    ] = 2

    with pytest.raises(RevisionBundlePublishError, match="ambígua"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_spread_or_quantity_as_quota_price() -> None:
    payload = _payload()
    payload["carteira_101_document_prices"][0]["price_nature"] = (
        "spread de remuneração"
    )

    with pytest.raises(
        RevisionBundlePublishError,
        match="spread, remuneração ou quantidade",
    ):
        validate_artifact_payload(payload, "2026-05")


@pytest.mark.parametrize(
    "price_display",
    (
        "Quantidade de cotas: 1.000 · R$ 1.000,00",
        "Spread DI + 2,0% · R$ 1.000,00",
        "Remuneração da cota · R$ 1.000,00",
        "Taxa da série · R$ 1.000,00",
    ),
)
@pytest.mark.parametrize(
    "collection_key",
    ("carteira_101_document_prices", "portfolio_export_price_evidence"),
)
def test_payload_rejects_forbidden_terms_in_quota_price_display(
    price_display: str,
    collection_key: str,
) -> None:
    payload = _payload()
    payload[collection_key][0]["price_display"] = price_display

    with pytest.raises(
        RevisionBundlePublishError,
        match="spread, remuneração ou quantidade/taxa",
    ):
        validate_artifact_payload(payload, "2026-05")


def test_payload_requires_monetary_value_in_quota_price_display() -> None:
    payload = _payload()
    payload["carteira_101_document_prices"][0]["price_display"] = "1.000 cotas"

    with pytest.raises(
        RevisionBundlePublishError,
        match="valor monetário unitário em price_display",
    ):
        validate_artifact_payload(payload, "2026-05")


def test_payload_requires_unitary_quota_price_nature() -> None:
    payload = _payload()
    payload["carteira_101_document_prices"][0]["price_nature"] = (
        "montante total da oferta"
    )

    with pytest.raises(
        RevisionBundlePublishError,
        match="price_nature sem natureza unitária",
    ):
        validate_artifact_payload(payload, "2026-05")


def test_payload_allows_unknown_quota_class_only_with_asterisk() -> None:
    payload = _payload()
    row = payload["carteira_101_document_prices"][0]
    row["class_series"] = "N/D"
    row["exception_flag"] = "*"
    evidence = payload["portfolio_export_price_evidence"][0]
    evidence["class_series"] = "N/D"
    evidence["excecao_asterisco_flag"] = True

    validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_unknown_quota_class_without_asterisk() -> None:
    payload = _payload()
    payload["carteira_101_document_prices"][0]["class_series"] = "N/D"

    with pytest.raises(
        RevisionBundlePublishError,
        match="deve trazer asterisco de exceção",
    ):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_quota_price_from_outside_carteira_101() -> None:
    payload = deepcopy(_payload())
    payload["carteira_101_document_prices"][0]["cnpj"] = "99000000000000"

    with pytest.raises(
        RevisionBundlePublishError,
        match="CNPJ fora da Carteira 101",
    ):
        validate_artifact_payload(payload, "2026-05")


def test_payload_requires_online_attempt_for_all_101_cnpjs() -> None:
    payload = _payload()
    payload["carteira_101_document_checkpoint"][0]["online_status"] = (
        "não solicitado"
    )

    with pytest.raises(
        RevisionBundlePublishError,
        match="não foi tentada para todos",
    ):
        validate_artifact_payload(payload, "2026-05")


def test_payload_accepts_manual_root_without_cohort_match_when_audited() -> None:
    payload = deepcopy(_payload())
    payload["portfolio_export_manual_audit"][0].update(
        {
            "cnpj": "",
            "status_resolucao_cnpj": "sem_correspondencia",
            "quantidade_candidatos_cnpj": 0,
        }
    )

    validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_issuance_taxonomy_that_does_not_reconcile() -> None:
    payload = deepcopy(_payload())
    payload["issuance_taxonomy_reconciliation"][0]["emitted_volume_brl"] += 0.02

    with pytest.raises(
        RevisionBundlePublishError,
        match=r"quatro tipos ANBIMA \+ FIC-FIDC",
    ):
        validate_artifact_payload(payload, "2026-05")

    payload = _payload()
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
        "market_offer_reconciliation",
        "provider_history_cvm_coverage",
        "provider_history_cvm_links",
        "provider_history_cvm_detail",
        "conclusion_metrics",
    ):
        broken = dict(payload)
        broken.pop(key)
        with pytest.raises(RevisionBundlePublishError, match=key):
            validate_artifact_payload(broken, "2026-05")


def test_payload_rejects_card_taxonomy_count_divergent_from_summary() -> None:
    payload = deepcopy(_payload())
    payload["card_taxonomy_audit"].pop()

    with pytest.raises(RevisionBundlePublishError, match="fundos_total diverge"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_duplicate_card_taxonomy_cnpj() -> None:
    payload = deepcopy(_payload())
    rows = payload["card_taxonomy_audit"]
    rows[1]["cnpj_fundo_formatado"] = rows[0]["cnpj_fundo_formatado"]

    with pytest.raises(RevisionBundlePublishError, match="CNPJs únicos"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_non_continuous_card_taxonomy_rank() -> None:
    payload = deepcopy(_payload())
    payload["card_taxonomy_audit"][1]["ordem_materialidade"] = 1

    with pytest.raises(RevisionBundlePublishError, match="contínua de 1 a N"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_card_taxonomy_enum_count_drift() -> None:
    payload = deepcopy(_payload())
    payload["card_taxonomy_audit"][0]["status_curadoria"] = "Fora de Adquirência"

    with pytest.raises(
        RevisionBundlePublishError,
        match="fundos_incluidos_adquirencia não reconcilia",
    ):
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


def test_payload_accepts_pending_card_taxonomy_from_official_classification() -> None:
    payload = deepcopy(_payload())
    pending = next(
        row
        for row in payload["card_taxonomy_audit"]
        if row["status_curadoria"] == "Pendente"
    )
    pending["fonte_url"] = "N/D"
    pending["anbima_cartao_explicito"] = True
    pending["classification_source"] = "ANBIMA Data — Fundos 175"

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


def test_payload_accepts_anbima_2023_fidc_level() -> None:
    payload = deepcopy(_payload())
    corrected_volume = 3.0
    for row in payload["market_offer_reconciliation"]:
        if (
            row["period_label"] == "2023 FY"
            and row["instrument_label"] == "FIDCs"
        ):
            row["anbima_closed_volume_brl"] = corrected_volume
    for row in payload["fixed_income_offer_comparison"]:
        if row["period_label"] != "2023 FY":
            continue
        if row["series_label"] == "FIDCs":
            row["registered_volume_brl"] = corrected_volume
        if row["view"] == "FIDCs vs demais elegíveis":
            row["universe_registered_volume_brl"] = corrected_volume + 1.0

    validate_artifact_payload(payload, "2026-05")


def test_payload_rejects_2023_fidc_level_divergent_from_anbima() -> None:
    payload = deepcopy(_payload())
    for row in payload["fixed_income_offer_comparison"]:
        if row["period_label"] != "2023 FY":
            continue
        if row["series_label"] == "FIDCs":
            row["registered_volume_brl"] = 3.0
        if row["view"] == "FIDCs vs demais elegíveis":
            row["universe_registered_volume_brl"] = 4.0

    with pytest.raises(RevisionBundlePublishError, match="2023 FY"):
        validate_artifact_payload(payload, "2026-05")


def test_payload_still_reconciles_2024_fidc_level_to_cvm() -> None:
    payload = deepcopy(_payload())
    for row in payload["fixed_income_offer_comparison"]:
        if row["period_label"] != "2024 FY":
            continue
        if row["series_label"] == "FIDCs":
            row["registered_volume_brl"] = 3.0
        if row["view"] == "FIDCs vs demais elegíveis":
            row["universe_registered_volume_brl"] = 4.0

    with pytest.raises(RevisionBundlePublishError, match="2024 FY"):
        validate_artifact_payload(payload, "2026-05")


def _minimal_live_input_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, str], dict[str, Path]]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    required = data_dir / "required.csv"
    required.write_text("value\ninitial\n", encoding="utf-8")
    optional = data_dir / "optional.csv"
    curation = tmp_path / "curation.csv"
    curation.write_text("value\ninitial\n", encoding="utf-8")
    workbook = tmp_path / "input.xlsx"
    workbook.write_bytes(b"initial workbook")
    builder = tmp_path / "builder.py"
    builder.write_text("VALUE = 'initial'\n", encoding="utf-8")

    monkeypatch.setattr(revision_publisher, "REQUIRED_DATA_INPUTS", ("required.csv",))
    monkeypatch.setattr(revision_publisher, "OPTIONAL_DATA_INPUTS", ("optional.csv",))
    monkeypatch.setattr(revision_publisher, "BUILDER_SOURCES", (builder,))
    captured = revision_publisher.collect_input_hashes(
        data_dir=data_dir,
        curation_path=curation,
        input_workbook=workbook,
        artifact_script=builder,
    )
    return captured, {
        "data_dir": data_dir,
        "required": required,
        "optional": optional,
        "curation": curation,
        "workbook": workbook,
        "builder": builder,
    }


def test_input_hashes_include_top20_curation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, _ = _minimal_live_input_snapshot(tmp_path, monkeypatch)

    assert "curation/top20.csv" in captured


@pytest.mark.parametrize(
    ("target", "expected_label"),
    (
        ("required", "data/required.csv"),
        ("curation", "curation/top20.csv"),
        ("workbook", "workbook/input.xlsx"),
        ("builder", "builder/builder.py"),
    ),
)
def test_live_input_revalidation_rejects_mutation_before_commit_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    expected_label: str,
) -> None:
    captured, paths = _minimal_live_input_snapshot(tmp_path, monkeypatch)
    revision_publisher.validate_live_input_hashes_unchanged(
        captured,
        data_dir=paths["data_dir"],
        curation_path=paths["curation"],
        input_workbook=paths["workbook"],
        artifact_script=paths["builder"],
    )
    paths[target].write_text("changed\n", encoding="utf-8")

    with pytest.raises(
        RevisionBundlePublishError,
        match=expected_label,
    ):
        revision_publisher.validate_live_input_hashes_unchanged(
            captured,
            data_dir=paths["data_dir"],
            curation_path=paths["curation"],
            input_workbook=paths["workbook"],
            artifact_script=paths["builder"],
        )


def test_live_input_revalidation_rejects_new_optional_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, paths = _minimal_live_input_snapshot(tmp_path, monkeypatch)
    paths["optional"].write_text("value\nlate\n", encoding="utf-8")

    with pytest.raises(
        RevisionBundlePublishError,
        match=r"data/optional\.csv \(adicionado\)",
    ):
        revision_publisher.validate_live_input_hashes_unchanged(
            captured,
            data_dir=paths["data_dir"],
            curation_path=paths["curation"],
            input_workbook=paths["workbook"],
            artifact_script=paths["builder"],
        )


def test_bundle_manifest_is_content_addressed_and_validated() -> None:
    payload = _payload()
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    kwargs = {
        "payload_bytes": payload_bytes,
        "payload": payload,
        "analysis_manifest_bytes": b"analysis",
        "pptx_bytes": b"pptx",
        "xlsx_bytes": b"xlsx",
        "portfolio_xlsx_bytes": b"portfolio",
        "top100_xlsx_bytes": b"top100",
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
    assert first["schema_version"] == "fidc_revision_export_bundle_v5"
    assert first["checks"]["slides"] == EXPECTED_SLIDES
    assert first["top100_xlsx"]["name"] == "top100_fidcs_middle_market.xlsx"
    assert first["checks"]["portfolio_export_cases_99"] == 99
    assert first["checks"]["top100_fidcs_middle_market"] == 102
    validate_bundle_manifest(
        first,
        payload_bytes=payload_bytes,
        payload=payload,
        analysis_manifest_bytes=b"analysis",
        pptx_bytes=b"pptx",
        xlsx_bytes=b"xlsx",
        portfolio_xlsx_bytes=b"portfolio",
        top100_xlsx_bytes=b"top100",
        html_bytes=b"html",
    )
    validate_renderer_manifest(
        first,
        payload_bytes=payload_bytes,
        payload=payload,
        pptx_bytes=b"pptx",
        xlsx_bytes=b"xlsx",
        portfolio_xlsx_bytes=b"portfolio",
        top100_xlsx_bytes=b"top100",
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
            portfolio_xlsx_bytes=b"portfolio",
            top100_xlsx_bytes=b"top100",
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
            portfolio_xlsx_bytes=b"portfolio",
            top100_xlsx_bytes=b"top100",
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
            portfolio_xlsx_bytes=b"portfolio",
            top100_xlsx_bytes=b"top100",
            html_bytes=b"html",
        )

    broken_inputs = deepcopy(first)
    broken_inputs["inputs"]["data/a.csv"] = "0" * 64
    with pytest.raises(RevisionBundlePublishError, match="input_signature"):
        validate_bundle_manifest(
            broken_inputs,
            payload_bytes=payload_bytes,
            payload=payload,
            analysis_manifest_bytes=b"analysis",
            pptx_bytes=b"pptx",
            xlsx_bytes=b"xlsx",
            portfolio_xlsx_bytes=b"portfolio",
            top100_xlsx_bytes=b"top100",
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
    staged_portfolio_xlsx = tmp_path / "stage" / "portfolio.xlsx"
    staged_manifest = tmp_path / "stage" / "bundle.json"
    staged_pptx.write_bytes(b"pptx")
    staged_xlsx.write_bytes(b"xlsx")
    staged_portfolio_xlsx.write_bytes(b"portfolio")
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
        staged_portfolio_xlsx=staged_portfolio_xlsx,
        staged_bundle_manifest=staged_manifest,
        publish_dir=publish_dir,
        replace=recording_replace,
    )

    assert destinations[-1] == publish_dir / BUNDLE_MANIFEST_NAME
    assert destinations.count(publish_dir / BUNDLE_MANIFEST_NAME) == 1
    assert destinations[-4:-1] == [
        publish_dir / MATERIALIZED_PPTX_NAME,
        publish_dir / MATERIALIZED_XLSX_NAME,
        publish_dir / MATERIALIZED_PORTFOLIO_XLSX_NAME,
    ]
    assert (publish_dir / MATERIALIZED_PORTFOLIO_XLSX_NAME).read_bytes() == b"portfolio"
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
        "files": {
            name: {"rows": 1 if name in REQUIRED_NONEMPTY_ANALYSIS_FILES else 0}
            for name in REQUIRED_ANALYSIS_FILES
        },
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


def test_analysis_manifest_rejects_empty_cohort_revision_tables(tmp_path: Path) -> None:
    from scripts.publish_fidc_revision_bundle import validate_analysis_manifest

    for filename in REQUIRED_ANALYSIS_FILES:
        (tmp_path / filename).write_bytes(b"")
    manifest = {
        "latest_complete": "2026-06",
        "files": {name: {"rows": 1} for name in REQUIRED_ANALYSIS_FILES},
        "checks": {
            "top20_fidcs_rows": 20,
            "top20_outros_rows": 20,
            "latest_funds": 4222,
        },
    }
    manifest["files"]["inadimplencia_coorte_revisao_transicoes.csv"]["rows"] = 0

    with pytest.raises(
        RevisionBundlePublishError,
        match=r"competência anterior 2026-05 no --raw-dir",
    ):
        validate_analysis_manifest(
            manifest,
            revision_dir=tmp_path,
            latest_complete="2026-06",
        )


def test_previous_table_ii_is_required_for_cohort_revision() -> None:
    current = pd.DataFrame(
        {"competencia": ["2026-06"], "cnpj": ["12345678000190"]}
    )

    with pytest.raises(SystemExit, match=r"inf_mensal_fidc_202605\.zip"):
        require_previous_table_ii(
            [current],
            previous_competence="2026-05",
            raw_dir=Path("missing-cache"),
        )

    previous = pd.DataFrame(
        {"competencia": ["2026-05"], "cnpj": ["12345678000190"]}
    )
    require_previous_table_ii(
        [current, previous],
        previous_competence="2026-05",
        raw_dir=Path("available-cache"),
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
    assert "document_inventory.csv.gz" in REQUIRED_DATA_INPUTS
    assert "taxonomy_review_actions.csv" in REQUIRED_DATA_INPUTS
    assert "taxonomy_user_comment_overrides.csv" in REQUIRED_DATA_INPUTS
    assert "taxonomy_review_audit.csv" in REQUIRED_DATA_INPUTS
    assert "industry_taxonomy_document_review.csv" in REQUIRED_DATA_INPUTS
    assert "industry_top20_taxonomy_document_review.csv" in REQUIRED_DATA_INPUTS
    assert "industry_top20_taxonomy_document_conclusions.csv" in REQUIRED_DATA_INPUTS
    assert (
        "carteira_101_document_audit/carteira_101_document_manifest.json"
        in REQUIRED_DATA_INPUTS
    )
    assert (
        "carteira_101_document_audit/carteira_101_document_prices.csv.gz"
        in REQUIRED_DATA_INPUTS
    )
    assert {
        "industry_taxonomy_audited_decisions_202606.csv",
        "industry_taxonomy_audit_top200_202606.csv.gz",
        "industry_taxonomy_outros_three_buckets_202606.csv",
        "industry_taxonomy_acquiring_202606.csv",
        "industry_taxonomy_audit_manifest_202606.json",
        "industry_taxonomy_impact_summary_202606.csv",
        "industry_taxonomy_impact_flows_202606.csv",
        "industry_taxonomy_issuance_impact_202606.csv",
        "industry_taxonomy_market_share_denominator_impact_202606.csv",
        "cedente_triage/202606/fidc_cedentes_top437_202606.csv.gz",
        "cedente_triage/202606/fidc_cedentes_curva_cobertura_202606.csv",
        "cedente_triage/202606/fidc_cedentes_triagem_manifest_202606.json",
        "emission_field_document_audit/emission_field_document_audit.csv",
        "emission_field_document_audit/emission_field_document_coverage.csv",
        "emission_field_document_audit/emission_field_document_evidence.csv.gz",
        "emission_field_document_audit/emission_field_document_prices.csv.gz",
        "emission_field_document_audit/emission_field_document_checkpoint.jsonl",
        "emission_field_document_audit/emission_field_document_manifest.json",
    }.issubset(REQUIRED_DATA_INPUTS)


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


def test_revision_analysis_accepts_validated_presence_overlay_reuse() -> None:
    args = parse_revision_args(
        ["--source-presence-overlay", "source_presence_overlay.csv.gz"]
    )

    assert args.refresh_source_presence is False
    assert args.source_presence_overlay == "source_presence_overlay.csv.gz"
