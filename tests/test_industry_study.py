import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_fidc_industry_study import (  # noqa: E402
    FIC_FIDC_PATTERN,
    _norm_name,
    _strip_digits,
    month_range,
)
from services.industry_study import (  # noqa: E402
    CEDENTE_REVIEW_COLUMNS,
    CRITERIA_REVIEW_COLUMNS,
    MONTHLY_DELTA_ACTION_COLUMNS,
    REVIEW_AUDIT_COLUMNS,
    append_review_audit_events,
    apply_monthly_delta_actions,
    assign_document_chunks,
    build_review_audit_events,
    build_criteria_pipeline_manifest,
    build_criteria_structured,
    build_dimension_catalog_pipeline_manifest,
    build_dimension_monthly_pipeline_manifest,
    build_dimension_profile_pipeline_manifest,
    build_document_inventory,
    build_document_pipeline_manifest,
    build_industry_dimension_catalog,
    build_industry_dimension_monthly,
    build_industry_dimension_profiles,
    build_industry_fund_snapshot,
    build_industry_monthly_delta,
    build_industry_market_share,
    build_industry_pipeline_index,
    build_issuance_annual,
    build_issuance_pipeline_manifest,
    build_issuance_sector_year,
    build_issuance_tranches,
    build_market_share_pipeline_manifest,
    build_monthly_delta_pipeline_manifest,
    build_cedente_structured,
    build_cedente_pipeline_manifest,
    cedente_quality_summary,
    criteria_quality_summary,
    document_quality_summary,
    fund_snapshot_quality_summary,
    industry_dimension_catalog_quality_summary,
    industry_dimension_monthly_quality_summary,
    industry_dimension_profile_quality_summary,
    industry_market_share_quality_summary,
    industry_monthly_delta_quality_summary,
    load_cedente_structured,
    load_monthly_delta_actions,
    load_review_audit,
    normalize_cnpj,
    save_monthly_delta_actions,
    save_pipeline_manifest,
    save_cedente_structured,
    scan_regulatory_extraction_files,
)
from tabs.tab_industry_study import (  # noqa: E402
    _apply_document_chunk_actions,
    _apply_snapshot_gap_actions,
    _build_fund_dossier_tables,
    _build_snapshot_market_share,
    _apply_catalog_gap_actions,
    _catalog_heatmap_cell_frame,
    _catalog_gap_actions_for_audit,
    _dimension_catalog_gap_frame,
    _dimension_catalog_quality_frame,
    _dimension_profile_coverage_frame,
    _dimension_radar_frame,
    _dimension_value_snapshot_frame,
    _document_chunk_actions_for_audit,
    _document_chunk_plan_frame,
    _format_document_chunk_plan,
    _format_dimension_catalog_gaps,
    _format_dimension_catalog_quality,
    _format_dimension_value_snapshot,
    _format_dimension_radar,
    _format_monthly_readiness,
    _heatmap_base_frame,
    _heatmap_preset_options,
    _monthly_delta_actions_for_audit,
    _monthly_readiness_frame,
    _pl_fic_impact_frame,
    _profile_heatmap_frame,
    _snapshot_gap_actions_for_audit,
    _snapshot_gap_frame,
)


def test_month_range_spans_years():
    months = month_range("2013-01", "2014-03")
    assert months[0] == "201301"
    assert months[-1] == "201403"
    assert len(months) == 15


def test_month_range_single_month():
    assert month_range("2026-05", "2026-05") == ["202605"]


def test_strip_digits():
    assert _strip_digits("05.753.599/0001-58") == "05753599000158"
    assert _strip_digits(None) == ""


def test_norm_name_collapses_spaces_and_uppercases():
    assert _norm_name("  BTG  Pactual   Servicos ") == "BTG PACTUAL SERVICOS"


def test_fic_fidc_pattern():
    assert FIC_FIDC_PATTERN.search("XPTO FIC FIDC MULTIMERCADO")
    assert FIC_FIDC_PATTERN.search(
        "FUNDO DE INVESTIMENTO EM COTAS DE FUNDOS DE INVESTIMENTO EM DIREITOS CREDITORIOS ABC"
    )
    assert not FIC_FIDC_PATTERN.search("FUNDO DE INVESTIMENTO EM DIREITOS CREDITORIOS ABC")


def test_versioned_granular_industry_outputs_have_expected_schema():
    data_dir = Path(__file__).resolve().parents[1] / "data" / "industry_study"
    vehicle_cols = set(pd.read_csv(data_dir / "vehicle_monthly.csv.gz", nrows=0).columns)
    audit_cols = set(pd.read_csv(data_dir / "update_audit_monthly.csv", nrows=0).columns)

    assert {
        "competencia",
        "cnpj",
        "denominacao",
        "pl",
        "captacao_liquida",
        "inad_pct_ajustada",
        "subordinacao_pct",
        "cnpj_fundo",
    }.issubset(vehicle_cols)
    assert {
        "competencia",
        "n_veiculos_usados",
        "tab1_coverage",
        "tab2_coverage",
        "x4_coverage",
        "x4_valor_descartado",
    }.issubset(audit_cols)


def test_granular_vehicle_panel_reconciles_to_monthly_aggregates():
    data_dir = Path(__file__).resolve().parents[1] / "data" / "industry_study"
    industry = pd.read_csv(data_dir / "industry_monthly.csv", usecols=["competencia", "pl_total", "captacao_liquida"])
    vehicle = pd.read_csv(
        data_dir / "vehicle_monthly.csv.gz",
        usecols=["competencia", "pl", "captacao_liquida"],
    )
    granular = vehicle.groupby("competencia", as_index=False).agg(
        pl=("pl", "sum"),
        captacao_liquida_granular=("captacao_liquida", "sum"),
    )
    reconciled = industry.merge(granular, on="competencia", how="inner")

    assert (reconciled["pl_total"] - reconciled["pl"]).abs().max() < 1.0
    assert (
        reconciled["captacao_liquida"] - reconciled["captacao_liquida_granular"]
    ).abs().max() < 1.0


def test_cedente_review_schema_keeps_manual_fields():
    assert "nome_fantasia_revisado" in CEDENTE_REVIEW_COLUMNS
    assert "confianca_manual" in CEDENTE_REVIEW_COLUMNS


def test_review_audit_events_track_material_review_changes():
    updated = pd.DataFrame(
        [
            {
                "review_id": "r1",
                "status": "aprovado",
                "nome_revisado": "CEDENTE ABC S.A.",
                "nome_fantasia_revisado": "",
                "cnpj_revisado": "",
                "grupo_economico": "",
                "setor_revisado": "",
                "segmento_revisado": "",
                "confianca_manual": "0.90",
                "notas": "",
            },
            {
                "review_id": "r2",
                "status": "pendente",
                "nome_revisado": "",
                "nome_fantasia_revisado": "",
                "cnpj_revisado": "",
                "grupo_economico": "",
                "setor_revisado": "",
                "segmento_revisado": "",
                "confianca_manual": "",
                "notas": "",
            },
        ],
        columns=CEDENTE_REVIEW_COLUMNS,
    )
    events = build_review_audit_events(
        previous=pd.DataFrame(columns=CEDENTE_REVIEW_COLUMNS),
        updated=updated,
        key_column="review_id",
        review_domain="cedente",
        saved_at_utc="2026-07-08T00:00:00+00:00",
        source="test",
    )

    assert list(events.columns) == REVIEW_AUDIT_COLUMNS
    assert set(events["record_id"]) == {"r1"}
    assert {"status", "nome_revisado", "confianca_manual"}.issubset(set(events["field"]))

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.csv"
        audit = append_review_audit_events(events, path)
        audit_again = append_review_audit_events(events, path)
        loaded = load_review_audit(path)

    assert len(audit) == len(events)
    assert len(audit_again) == len(events)
    assert loaded["event_id"].tolist() == audit["event_id"].tolist()

    candidates = pd.DataFrame(
        [
            {
                "review_id": "r1",
                "cnpj_fundo": "12345678000190",
                "fund_name": "FIDC TESTE",
                "participant_type": "cedente_originador",
                "participant_cnpj_candidate": "",
                "participant_name_candidate": "CEDENTE AUTO S.A.",
                "participante_extraido": "CEDENTE AUTO S.A.",
                "setor_n1": "Crédito PJ",
                "setor_n2": "Recebíveis comerciais",
                "evidence_context": "Cedente CEDENTE AUTO S.A.",
                "source_cache": "doc.txt",
                "documento_origem": "doc.txt",
                "pagina": "",
                "metodo_extracao": "teste",
                "score_confianca": 0.6,
                "evidencias_agrupadas": 1,
            }
        ]
    )
    structured = build_cedente_structured(candidates, updated, review_audit=events)

    assert structured.loc[0, "review_event_count"] == len(events)
    assert structured.loc[0, "last_review_at_utc"] == "2026-07-08T00:00:00+00:00"
    assert structured.loc[0, "last_review_source"] == "test"


def test_cedente_structured_applies_manual_review():
    candidates = pd.DataFrame(
        [
            {
                "review_id": "abc123",
                "cnpj_fundo": "12345678000190",
                "fund_name": "FIDC TESTE",
                "participant_type": "cedente_originador",
                "participant_cnpj_candidate": "00.000.000/0001-91",
                "participant_name_candidate": "NOME AUTOMATICO S.A.",
                "participante_extraido": "NOME AUTOMATICO S.A.",
                "setor_n1": "Crédito PJ",
                "setor_n2": "Recebíveis comerciais",
                "evidence_context": "Cedente NOME AUTOMATICO S.A. página 12",
                "source_cache": "doc.txt",
                "documento_origem": "doc.txt",
                "pagina": "12",
                "metodo_extracao": "teste",
                "score_confianca": 0.6,
                "evidencias_agrupadas": 2,
            }
        ]
    )
    reviews = pd.DataFrame(
        [
            {
                "review_id": "abc123",
                "status": "corrigido",
                "nome_revisado": "CEDENTE REVISADO S.A.",
                "nome_fantasia_revisado": "Cedente Rev",
                "cnpj_revisado": "05.753.599/0001-58",
                "grupo_economico": "Grupo Teste",
                "setor_revisado": "Crédito PF",
                "segmento_revisado": "Consignado",
                "confianca_manual": "0.9",
                "notas": "ok",
            }
        ]
    )

    structured = build_cedente_structured(candidates, reviews)
    row = structured.iloc[0]

    assert row["razao_social"] == "CEDENTE REVISADO S.A."
    assert row["nome_fantasia"] == "Cedente Rev"
    assert row["cnpj_participante"] == "05753599000158"
    assert row["grupo_economico"] == "Grupo Teste"
    assert row["setor"] == "Crédito PF"
    assert row["segmento"] == "Consignado"
    assert row["fonte_nome"] == "revisao_manual"
    assert row["score_confianca_final"] == 0.9


def test_cedente_structured_roundtrip_preserves_cnpj_text():
    frame = pd.DataFrame(
        [
            {
                "cnpj_fundo": "01234567000189",
                "cnpj_participante": normalize_cnpj("05.753.599/0001-58"),
                "razao_social": "ABC S.A.",
            }
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cedentes.csv.gz"
        save_cedente_structured(frame, path)
        loaded = load_cedente_structured(path)

    assert loaded.loc[0, "cnpj_fundo"] == "01234567000189"
    assert loaded.loc[0, "cnpj_participante"] == "05753599000158"


def test_cedente_quality_summary_tracks_coverage_and_priority():
    structured = pd.DataFrame(
        [
            {
                "cnpj_fundo": "11111111000111",
                "participant_type": "cedente_originador",
                "razao_social": "ABC S.A.",
                "cnpj_participante": "05753599000158",
                "setor": "Crédito PJ",
                "segmento": "Recebíveis",
                "documento_origem": "doc.txt",
                "pagina": "12",
                "metodo_extracao": "teste",
                "score_confianca_final": 0.9,
                "periodo_prioritario": "2025-2026 YTD",
                "ativo_curadoria": True,
            },
            {
                "cnpj_fundo": "22222222000122",
                "participant_type": "sacado_devedor",
                "razao_social": "",
                "cnpj_participante": "",
                "setor": "Crédito PF",
                "segmento": "Consignado",
                "documento_origem": "doc2.txt",
                "pagina": "",
                "metodo_extracao": "teste",
                "score_confianca_final": 0.5,
                "periodo_prioritario": "histórico",
                "ativo_curadoria": True,
            },
        ]
    )
    summary = cedente_quality_summary(
        pd.DataFrame({"cnpj_fundo": ["11111111000111", "22222222000122"]}),
        pd.DataFrame({"review_id": ["a"], "status": ["aprovado"]}),
        structured,
    )

    assert summary["structured_rows"] == 2
    assert summary["priority_2025_2026_rows"] == 1
    assert summary["coverage"]["razao_social"] == 0.5
    assert summary["coverage"]["documento_origem"] == 1.0
    assert summary["score"]["median"] == 0.7


def test_cedente_pipeline_manifest_lists_rerunnable_stages():
    candidates = pd.DataFrame({"cnpj_fundo": ["11111111000111"], "review_id": ["r1"]})
    reviews = pd.DataFrame({"review_id": ["r1"], "status": ["pendente"]})
    fund_universe = pd.DataFrame({"cnpj": ["11111111000111"]})
    vehicle_latest = pd.DataFrame({"cnpj_fundo": ["11111111000111"]})
    structured = pd.DataFrame(
        [
            {
                "cnpj_fundo": "11111111000111",
                "participant_type": "cedente_originador",
                "razao_social": "ABC S.A.",
                "cnpj_participante": "05753599000158",
                "periodo_prioritario": "2025-2026 YTD",
                "score_confianca_final": 0.9,
                "ativo_curadoria": True,
            }
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "strategy.sqlite"
        reviews_path = tmp_path / "reviews.csv"
        output_path = tmp_path / "cedentes.csv.gz"
        db_path.write_text("db")
        reviews_path.write_text("review")
        save_cedente_structured(structured, output_path)
        manifest = build_cedente_pipeline_manifest(
            industry_dir=tmp_path,
            strategy_db=db_path,
            reviews_path=reviews_path,
            output_path=output_path,
            candidates=candidates,
            reviews=reviews,
            fund_universe=fund_universe,
            vehicle_latest=vehicle_latest,
            structured=structured,
        )
        manifest_path = tmp_path / "manifest.json"
        save_pipeline_manifest(manifest, manifest_path)

    assert manifest["schema_version"] == "industry-pipeline-manifest/v1"
    assert {stage["id"] for stage in manifest["stages"]} == {
        "extract_candidates",
        "apply_manual_review",
        "enrich_funds",
        "enrich_ime_snapshot",
        "consolidate_structured_base",
    }
    assert all(stage["rerun"] for stage in manifest["stages"])
    assert manifest["outputs"]["cedentes_structured"]["sha256"]


def test_issuance_annual_and_sector_year_from_fund_universe():
    funds = pd.DataFrame(
        [
            {
                "cnpj": "11111111000111",
                "setor_n1": "Crédito PJ",
                "setor_n2": "Recebíveis",
                "volume_2024_brl": 100.0,
                "valid_volume_2024_brl": 80.0,
                "offers_2024": 1,
                "pl_atual_brl": 1000.0,
                "has_regulatory_matrix": 1,
            },
            {
                "cnpj": "22222222000122",
                "setor_n1": "Crédito PF",
                "setor_n2": "Consignado",
                "volume_2025_brl": 200.0,
                "valid_volume_2025_brl": 150.0,
                "offers_2025": 2,
                "pl_atual_brl": 2000.0,
                "has_regulatory_matrix": 0,
            },
        ]
    )

    annual = build_issuance_annual(funds)
    sector = build_issuance_sector_year(funds)

    assert annual.loc[annual["ano"].eq(2024), "volume_conservador_brl"].iloc[0] == 80.0
    assert annual.loc[annual["ano"].eq(2025), "emissores_cnpj"].iloc[0] == 1
    assert set(sector["setor_n1"]) == {"Crédito PJ", "Crédito PF"}


def test_issuance_tranches_normalizes_indexer_and_source():
    pricing = pd.DataFrame(
        [
            {
                "cnpj_emissor": "05.753.599/0001-58",
                "fund_name_final": "FIDC ABC",
                "pricing_year": 2026,
                "pricing_period": "2026YTD",
                "data_deliberacao_dt": "2026-01-10",
                "cota_classe": "Série A",
                "tipo_cota_normalizado": "Sênior",
                "pricing_basis": "cdi_spread",
                "spread_cdi_aa_num": 1.5,
                "pct_cdi_num": 0,
                "spread_ipca_aa_num": 0,
                "volume_brl_num": 123.0,
                "setor_n1": "Crédito PJ",
                "setor_n2": "Recebíveis",
                "emission_cohort": "2026YTD",
                "status_curadoria": "ok",
                "fonte": "doc.pdf · ID 1",
                "confidence": "alta",
                "pricing_evidence": "CDI+1,5%",
            }
        ]
    )

    tranches = build_issuance_tranches(pricing)
    row = tranches.iloc[0]

    assert row["cnpj_fundo"] == "05753599000158"
    assert row["indexador"] == "CDI+"
    assert row["documento_origem"] == "doc.pdf"
    assert row["score_confianca"] == 0.9


def test_issuance_pipeline_manifest_lists_outputs():
    funds = pd.DataFrame({"cnpj": ["11111111000111"]})
    pricing = pd.DataFrame({"cnpj_fundo": ["11111111000111"]})
    annual = pd.DataFrame({"ano": [2026], "volume_conservador_brl": [10.0], "emissores_cnpj": [1]})
    sector = pd.DataFrame({"ano": [2026], "setor_n1": ["Crédito PJ"], "volume_conservador_brl": [10.0]})
    tranches = pd.DataFrame(
        {
            "cnpj_fundo": ["11111111000111"],
            "volume_brl": [10.0],
            "indexador": ["CDI+"],
            "documento_origem": ["doc.pdf"],
            "data_deliberacao": ["2026-01-01"],
            "setor_n1": ["Crédito PJ"],
            "score_confianca": [0.9],
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "strategy.sqlite"
        annual_path = tmp_path / "annual.csv"
        sector_path = tmp_path / "sector.csv"
        tranches_path = tmp_path / "tranches.csv.gz"
        db_path.write_text("db")
        annual.to_csv(annual_path, index=False)
        sector.to_csv(sector_path, index=False)
        save_cedente_structured(tranches, tranches_path)
        manifest = build_issuance_pipeline_manifest(
            industry_dir=tmp_path,
            strategy_db=db_path,
            annual_path=annual_path,
            sector_year_path=sector_path,
            tranches_path=tranches_path,
            fund_universe=funds,
            pricing=pricing,
            annual=annual,
            sector_year=sector,
            tranches=tranches,
        )

    assert manifest["schema_version"] == "industry-issuance-manifest/v1"
    assert manifest["outputs"]["issuance_tranches"]["sha256"]
    assert {stage["id"] for stage in manifest["stages"]} >= {"aggregate_annual_issuance", "normalize_tranches"}


def test_document_inventory_fingerprints_and_classifies_local_sources():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pdf_dir = root / "data" / "raw" / "05753599000158"
        pdf_dir.mkdir(parents=True)
        pdf_path = pdf_dir / "123456_regulamento_regulamento_123456_2026-05-10.pdf"
        pdf_path.write_bytes(b"%PDF local")
        sources = pd.DataFrame(
            [
                {
                    "cnpj_fundo": "05.753.599/0001-58",
                    "fundo": "FIDC TESTE",
                    "setor_n1": "Crédito PJ",
                    "setor_n2": "Recebíveis",
                    "source_table": "manual_review_queue",
                    "source_field": "latest_regulamento_file",
                    "source_value": "data/raw/05753599000158/123456_regulamento_regulamento_123456_2026-05-10.pdf",
                    "document_date_hint": "2026-05-10",
                    "priority_hint": "Onda 1",
                }
            ]
        )

        inventory = build_document_inventory(sources, root=root, max_hash_bytes=1024)
        row = inventory.iloc[0]

    assert row["cnpj_fundo"] == "05753599000158"
    assert row["document_class"] == "regulamento"
    assert row["content_kind"] == "pdf"
    assert row["document_date"] == "2026-05-10"
    assert bool(row["local_exists"]) is True
    assert row["hash_status"] == "hashed"
    assert len(row["sha256"]) == 64


def test_document_chunks_keep_small_rerunnable_batches():
    inventory = pd.DataFrame(
        [
            {
                "document_key": f"k{i}",
                "cnpj_fundo": f"{i:014d}",
                "fundo": f"FIDC {i}",
                "setor_n1": "Crédito PJ",
                "setor_n2": "Recebíveis",
                "documento_origem": f"doc_{i}.pdf",
                "documento_id": str(1000 + i),
                "document_class": "regulamento",
                "content_kind": "pdf",
                "document_date": "2026-01-01",
                "local_path": f"data/raw/{i:014d}/doc.pdf",
                "local_exists": True,
                "bytes": 10,
                "sha256": "a" * 64,
                "hash_status": "hashed",
                "source_table": "manual_review_queue",
                "source_field": "latest_regulamento_file",
                "source_value": "doc.pdf",
                "source_rows": 1,
                "priority_2025_2026": True,
                "first_offer_year": 2026,
                "emission_cohort": "2026YTD",
                "suggested_stage": "ocr_parse_extract",
                "processing_status": "local_ready",
            }
            for i in range(5)
        ]
    )

    assigned, chunks = assign_document_chunks(inventory, max_cnpjs=2, max_documents=2, max_bytes=100)

    assert assigned["chunk_id"].nunique() == 3
    assert chunks["document_count"].max() == 2
    assert chunks["cnpj_count"].max() == 2
    assert chunks["rerun_command"].str.contains("--chunk-id doc-0001").any()


def test_document_chunk_plan_prioritizes_download_hash_and_processing_actions():
    chunks = pd.DataFrame(
        [
            {
                "chunk_id": "doc-0001",
                "document_count": 2,
                "cnpj_count": 2,
                "priority_2025_2026_docs": 2,
                "local_ready_docs": 1,
                "hashed_docs": 1,
                "total_bytes": 1024,
                "document_classes": "regulamento",
                "rerun_command": "python scripts/build_fidc_industry_documents.py --chunk-id doc-0001",
            },
            {
                "chunk_id": "doc-0002",
                "document_count": 1,
                "cnpj_count": 1,
                "priority_2025_2026_docs": 1,
                "local_ready_docs": 1,
                "hashed_docs": 1,
                "total_bytes": 2048,
                "document_classes": "emissao",
                "rerun_command": "python scripts/build_fidc_industry_documents.py --chunk-id doc-0002",
            },
            {
                "chunk_id": "doc-0003",
                "document_count": 1,
                "cnpj_count": 1,
                "priority_2025_2026_docs": 0,
                "local_ready_docs": 1,
                "hashed_docs": 1,
                "total_bytes": 512,
                "document_classes": "assembleia",
                "rerun_command": "python scripts/build_fidc_industry_documents.py --chunk-id doc-0003",
            },
        ]
    )
    inventory = pd.DataFrame(
        [
            {
                "chunk_id": "doc-0001",
                "cnpj_fundo": "05753599000158",
                "fundo": "FIDC BAIXAR",
                "document_class": "regulamento",
                "local_exists": False,
                "sha256": "",
                "bytes": 0,
                "priority_2025_2026": True,
                "suggested_stage": "discover_download",
                "processing_status": "missing_local",
            },
            {
                "chunk_id": "doc-0001",
                "cnpj_fundo": "11111111000111",
                "fundo": "FIDC LOCAL",
                "document_class": "regulamento",
                "local_exists": True,
                "sha256": "a" * 64,
                "bytes": 1024,
                "priority_2025_2026": True,
                "suggested_stage": "ocr_parse_extract",
                "processing_status": "local_ready",
            },
            {
                "chunk_id": "doc-0002",
                "cnpj_fundo": "22222222000122",
                "fundo": "FIDC PROCESSAR",
                "document_class": "emissao",
                "local_exists": True,
                "sha256": "b" * 64,
                "bytes": 2048,
                "priority_2025_2026": True,
                "suggested_stage": "ocr_parse_extract",
                "processing_status": "local_ready",
            },
            {
                "chunk_id": "doc-0003",
                "cnpj_fundo": "33333333000133",
                "fundo": "FIDC PRONTO",
                "document_class": "assembleia",
                "local_exists": True,
                "sha256": "c" * 64,
                "bytes": 512,
                "priority_2025_2026": False,
                "suggested_stage": "",
                "processing_status": "complete",
            },
        ]
    )

    plan = _document_chunk_plan_frame(chunks, inventory)
    by_chunk = plan.set_index("chunk_id")
    actions = pd.DataFrame(
        [
            {
                "chunk_id": "doc-0002",
                "status_lote": "em andamento",
                "acao_revisada": "Rodar OCR e parsing",
                "responsavel": "Research",
                "prazo": "2026-07-20",
                "notas": "prioridade emissões",
                "updated_at_utc": "2026-07-08T12:00:00+00:00",
            }
        ]
    )
    tracked = _apply_document_chunk_actions(plan, actions)
    tracked_by_chunk = tracked.set_index("chunk_id")
    events = build_review_audit_events(
        previous=_document_chunk_actions_for_audit(pd.DataFrame(columns=actions.columns)),
        updated=_document_chunk_actions_for_audit(actions),
        key_column="chunk_id",
        review_domain="document_chunk_action",
        saved_at_utc="2026-07-08T12:00:00+00:00",
        source="test",
    )

    assert list(plan["chunk_id"])[:3] == ["doc-0001", "doc-0002", "doc-0003"]
    assert by_chunk.loc["doc-0001", "chunk_status"] == "baixar"
    assert by_chunk.loc["doc-0001", "missing_local_docs"] == 1
    assert by_chunk.loc["doc-0002", "chunk_status"] == "processar"
    assert by_chunk.loc["doc-0002", "next_action"] == "ocr parse extract"
    assert by_chunk.loc["doc-0003", "chunk_status"] == "pronto"
    assert tracked_by_chunk.loc["doc-0002", "status_lote"] == "em andamento"
    assert tracked_by_chunk.loc["doc-0002", "acao_revisada"] == "Rodar OCR e parsing"
    assert set(events["field"]) == {"status", "acao_revisada", "responsavel", "prazo", "notas"}
    assert set(events["record_id"]) == {"doc-0002"}

    formatted = _format_document_chunk_plan(tracked)

    assert formatted.loc[formatted["Chunk"].eq("doc-0001"), "Status"].iloc[0] == "baixar"
    assert formatted.loc[formatted["Chunk"].eq("doc-0002"), "Próxima ação"].iloc[0] == "ocr parse extract"
    assert formatted.loc[formatted["Chunk"].eq("doc-0002"), "Status acomp."].iloc[0] == "em andamento"
    assert "Comando" in formatted.columns


def test_document_manifest_and_quality_describe_pipeline_outputs():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "strategy.sqlite"
        extraction_dir = tmp_path / "data" / "regulatory_extractions"
        cnpj_dir = extraction_dir / "05753599000158"
        cnpj_dir.mkdir(parents=True)
        local_json = cnpj_dir / "123456.local.json"
        local_json.write_text("{}", encoding="utf-8")
        db_path.write_text("db")

        extraction_rows = scan_regulatory_extraction_files(extraction_dir)
        inventory = build_document_inventory(pd.DataFrame(), extraction_rows=extraction_rows, root=tmp_path)
        inventory, chunks = assign_document_chunks(inventory, max_cnpjs=10, max_documents=10)
        inventory_path = tmp_path / "document_inventory.csv.gz"
        chunks_path = tmp_path / "document_processing_chunks.csv"
        save_cedente_structured(inventory, inventory_path)
        chunks.to_csv(chunks_path, index=False)
        manifest = build_document_pipeline_manifest(
            industry_dir=tmp_path,
            strategy_db=db_path,
            extractions_dir=extraction_dir,
            inventory_path=inventory_path,
            chunks_path=chunks_path,
            manifest_path=tmp_path / "industry_document_manifest.json",
            source_rows=pd.DataFrame(),
            extraction_rows=extraction_rows,
            inventory=inventory,
            chunks=chunks,
            max_hash_bytes=1024,
        )
        quality = document_quality_summary(inventory, chunks)

    assert manifest["schema_version"] == "industry-document-manifest/v1"
    assert {stage["id"] for stage in manifest["stages"]} >= {"scan_local_extraction_artifacts", "assign_processing_chunks"}
    assert manifest["outputs"]["document_inventory"]["sha256"]
    assert quality["document_rows"] == 1
    assert quality["content_kind_counts"]["extraction_json"] == 1


def test_criteria_structured_applies_review_and_tracks_subordination():
    criteria = pd.DataFrame(
        [
            {
                "Fundo": "FIDC ABC",
                "CNPJ": "05.753.599/0001-58",
                "Critério": "Subordinação mínima",
                "Chave": "subordination_ratio_min",
                "Limite/regra": "Relação mínima de 12,5%",
                "Monitorabilidade IME": "monitoravel",
                "Métrica IME / proxy": "Subordinadas / PL",
                "Condição de alerta sugerida": "Abaixo de 12,5%",
                "Observação técnica": "pagina 10",
                "Fonte": "123456_regulamento_regulamento_123456_2026-05-10.pdf · ID 123456 · 10/05/2026",
                "Status curadoria": "triagem estruturada por evidência documental offline",
            }
        ]
    )
    criteria["rule_id"] = ["r1"]
    reviews = pd.DataFrame(
        [
            {
                "rule_id": "r1",
                "status": "corrigido",
                "criterio_revisado": "Subordinação mínima revisada",
                "chave_revisada": "",
                "limite_revisado": "",
                "pct_min_revisado": "10",
                "monitorabilidade_revisada": "parcial",
                "confianca_manual": "0.85",
                "notas": "ok",
            }
        ],
        columns=CRITERIA_REVIEW_COLUMNS,
    )
    funds = pd.DataFrame(
        [
            {
                "cnpj": "05753599000158",
                "fund_name_final": "FIDC ABC FINAL",
                "setor_n1": "Crédito PJ",
                "setor_n2": "Recebíveis",
                "first_offer_year": 2026,
                "emission_cohort": "2026YTD",
                "pl_atual_brl": 100.0,
                "has_regulatory_matrix": 1,
            }
        ]
    )

    structured = build_criteria_structured(criteria, reviews, fund_universe=funds)
    row = structured.iloc[0]
    quality = criteria_quality_summary(criteria, reviews, structured)

    assert row["cnpj_fundo"] == "05753599000158"
    assert row["criterio"] == "Subordinação mínima revisada"
    assert row["pct_min"] == 10
    assert row["monitorabilidade_ime"] == "parcial"
    assert row["documento_id"] == "123456"
    assert row["document_date"] == "2026-05-10"
    assert row["score_confianca_final"] == 0.85
    assert quality["subordination"]["median"] == 10.0
    assert quality["coverage"]["documento_origem"] == 1.0


def test_criteria_pipeline_manifest_lists_rerunnable_stages():
    criteria = pd.DataFrame(
        {
            "rule_id": ["r1"],
            "CNPJ": ["05753599000158"],
            "Chave": ["subordination_ratio_min"],
            "Critério": ["Sub"],
            "Limite/regra": ["10%"],
            "Monitorabilidade IME": ["monitoravel"],
            "Fonte": ["doc.pdf · ID 1 · 01/01/2026"],
        }
    )
    reviews = pd.DataFrame(columns=CRITERIA_REVIEW_COLUMNS)
    funds = pd.DataFrame({"cnpj": ["05753599000158"]})
    structured = build_criteria_structured(criteria, reviews, fund_universe=funds)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "strategy.sqlite"
        source_path = tmp_path / "criteria.csv"
        reviews_path = tmp_path / "criteria_reviews.csv"
        output_path = tmp_path / "criteria_structured.csv.gz"
        db_path.write_text("db")
        criteria.to_csv(source_path, index=False)
        reviews.to_csv(reviews_path, index=False)
        save_cedente_structured(structured, output_path)
        manifest = build_criteria_pipeline_manifest(
            industry_dir=tmp_path,
            strategy_db=db_path,
            criteria_source_path=source_path,
            reviews_path=reviews_path,
            output_path=output_path,
            manifest_path=tmp_path / "industry_criteria_manifest.json",
            criteria=criteria,
            reviews=reviews,
            fund_universe=funds,
            structured=structured,
        )

    assert manifest["schema_version"] == "industry-criteria-manifest/v1"
    assert {stage["id"] for stage in manifest["stages"]} >= {"load_documentary_criteria", "normalize_structured_criteria"}
    assert manifest["outputs"]["criteria_structured"]["sha256"]
    assert manifest["quality"]["subordination_rows"] == 1


def test_industry_fund_snapshot_unifies_layers_per_fund():
    vehicle = pd.DataFrame(
        [
            {
                "cnpj": "05.753.599/0001-58",
                "cnpj_fundo": "05.753.599/0001-58",
                "competencia": "2026-05",
                "denominacao": "FIDC ABC",
                "pl": 1000.0,
                "is_fic_fidc": False,
                "admin_nome": "Admin",
                "gestor_nome": "Gestor",
                "segmento_principal": "Comercial",
                "carteira_dc": 800.0,
                "dc_inadimplentes": 10.0,
                "cotistas": 3,
            },
            {
                "cnpj": "11.111.111/0001-11",
                "cnpj_fundo": "11.111.111/0001-11",
                "competencia": "2026-05",
                "denominacao": "FIDC DEF",
                "pl": 500.0,
                "is_fic_fidc": True,
                "admin_nome": "Admin",
                "gestor_nome": "Gestor",
                "segmento_principal": "Financeiro",
            },
        ]
    )
    funds = pd.DataFrame(
        {
            "cnpj": ["05753599000158"],
            "fund_name_final": ["FIDC ABC"],
            "setor_n1": ["Crédito PJ"],
            "setor_n2": ["Recebíveis"],
            "valid_volume_2025_brl": [100.0],
            "valid_volume_2026_brl": [50.0],
            "has_regulatory_matrix": [1],
        }
    )
    tranches = pd.DataFrame(
        {
            "cnpj_fundo": ["05753599000158"],
            "ano": [2026],
            "volume_brl": [25.0],
            "indexador": ["CDI+"],
            "tipo_cota": ["Sênior"],
            "documento_origem": ["emissao.pdf"],
            "score_confianca": [0.9],
        }
    )
    cedentes = pd.DataFrame(
        {
            "cnpj_fundo": ["05753599000158"],
            "razao_social": ["Cedente ABC S.A."],
            "participant_type": ["cedente_originador"],
            "tipo_participante": ["cedente/originador"],
            "ativo_curadoria": [True],
            "status_revisao": ["aprovado"],
            "score_confianca_final": [0.95],
            "documento_origem": ["reg.pdf"],
            "periodo_prioritario": ["2025-2026 YTD"],
        }
    )
    criteria = pd.DataFrame(
        {
            "cnpj_fundo": ["05753599000158"],
            "chave": ["subordination_ratio_min"],
            "pct_min": [10.0],
            "monitorabilidade_ime": ["monitoravel"],
            "ativo_curadoria": [True],
            "documento_origem": ["reg.pdf"],
            "score_confianca_final": [0.9],
        }
    )
    docs = pd.DataFrame(
        {
            "cnpj_fundo": ["05753599000158"],
            "document_class": ["regulamento"],
            "content_kind": ["pdf"],
            "document_date": ["2026-01-01"],
            "local_exists": [True],
            "priority_2025_2026": [True],
            "chunk_id": ["doc-0001"],
        }
    )

    snapshot = build_industry_fund_snapshot(
        vehicle_latest=vehicle,
        fund_universe=funds,
        issuance_tranches=tranches,
        cedentes=cedentes,
        criteria=criteria,
        documents=docs,
    )
    quality = fund_snapshot_quality_summary(snapshot)
    abc = snapshot[snapshot["cnpj_fundo"].eq("05753599000158")].iloc[0]
    defe = snapshot[snapshot["cnpj_fundo"].eq("11111111000111")].iloc[0]

    assert len(snapshot) == 2
    assert abc["camadas_com_evidencia"] == 5
    assert abc["snapshot_status"] == "completo"
    assert abc["participantes_count"] == 1
    assert abc["sub_min_pct_median"] == 10.0
    assert abc["document_chunk_ids"] == "doc-0001"
    assert defe["snapshot_status"] == "basico"
    assert quality["with_subordination_min"] == 1


def test_industry_heatmap_base_uses_snapshot_multivalue_dimensions():
    vehicle = pd.DataFrame(
        [
            {
                "competencia": "2026-05",
                "cnpj": "05753599000158",
                "cnpj_fundo": "05753599000158",
                "pl": 100.0,
                "captacao_liquida": 20.0,
            }
        ]
    )
    snapshot = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05.753.599/0001-58",
                "indexadores": "CDI+ | IPCA+",
                "criteria_keys": "subordination_ratio_min | concentration_limits",
                "sub_min_pct_median": 10.0,
                "snapshot_status": "completo",
            }
        ]
    )

    frame = _heatmap_base_frame(vehicle, pd.DataFrame(), snapshot, "indexadores", "criteria_keys")

    assert len(frame) == 4
    assert set(frame["indexadores"]) == {"CDI+", "IPCA+"}
    assert set(frame["criteria_keys"]) == {"subordination_ratio_min", "concentration_limits"}
    assert frame["_metric_weight"].sum() == 1.0
    assert set(frame["sub_min_bucket"]) == {"10%-15%"}


def test_industry_heatmap_presets_follow_available_dimensions():
    options = _heatmap_preset_options(
        [
            "Administrador",
            "Gestor",
            "Cedente/sacado",
            "Segmento",
            "Setor cedente",
            "Ano 1ª oferta",
            "Safra emissão",
            "Indexador",
            "Tipo de cota",
        ]
    )

    assert options["Personalizado"] is None
    assert options["Administrador × Segmento"] == ("Administrador", "Segmento")
    assert options["Gestor × Segmento"] == ("Gestor", "Segmento")
    assert options["Cedente/sacado × Administrador"] == ("Cedente/sacado", "Administrador")
    assert options["Setor cedente × Ano 1ª oferta"] == ("Setor cedente", "Ano 1ª oferta")
    assert options["Segmento × Safra emissão"] == ("Segmento", "Safra emissão")
    assert options["Setor cedente × Indexador"] == ("Setor cedente", "Indexador")
    assert options["Administrador × Tipo de cota"] == ("Administrador", "Tipo de cota")
    assert "Critério × Segmento" not in options


def test_industry_heatmap_cell_drilldown_preserves_catalog_evidence():
    catalog = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05.753.599/0001-58",
                "nome_exibicao": "FIDC ABC",
                "dimension_id": "admin",
                "dimension_label": "Administrador",
                "dimension_value": "Admin A",
                "value_weight": 1.0,
                "source_layer": "snapshot",
                "source_field": "admin_nome",
                "source_value": "Admin A",
                "is_multivalue": False,
                "is_curated": False,
                "source_document": "",
                "source_page": "",
                "source_method": "informe_mensal",
                "confidence_score": 1.0,
                "review_status": "",
            },
            {
                "cnpj_fundo": "05.753.599/0001-58",
                "nome_exibicao": "FIDC ABC",
                "dimension_id": "segmento",
                "dimension_label": "Segmento",
                "dimension_value": "Financeiro",
                "value_weight": 1.0,
                "source_layer": "cedente",
                "source_field": "segmento",
                "source_value": "Financeiro",
                "is_multivalue": False,
                "is_curated": True,
                "participant_type": "cedente",
                "participant_cnpj": "12345678000190",
                "source_document": "regulamento.pdf",
                "source_page": "12",
                "source_method": "manual_review",
                "confidence_score": 0.85,
                "review_status": "aprovado",
            },
            {
                "cnpj_fundo": "11.111.111/0001-11",
                "nome_exibicao": "FIDC DEF",
                "dimension_id": "admin",
                "dimension_label": "Administrador",
                "dimension_value": "Admin B",
                "value_weight": 1.0,
                "source_layer": "snapshot",
                "source_field": "admin_nome",
                "source_value": "Admin B",
                "source_method": "informe_mensal",
                "confidence_score": 1.0,
            },
        ]
    )
    snapshot = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05753599000158",
                "nome_exibicao": "FIDC ABC",
                "competencia": "2026-05",
                "pl": 100.0,
                "valid_volume_2024_2026_brl": 20.0,
                "admin_nome": "Admin A",
                "gestor_nome": "Gestor A",
                "segmento_principal": "Financeiro",
                "document_rows": 2,
                "cedente_rows": 1,
                "criteria_rows": 1,
                "snapshot_status": "completo",
            }
        ]
    )

    drilldown = _catalog_heatmap_cell_frame(catalog, snapshot, "admin", "Admin A", "segmento", "Financeiro")

    assert len(drilldown) == 1
    row = drilldown.iloc[0]
    assert row["cnpj_fundo_norm"] == "05753599000158"
    assert row["pl"] == 100.0
    assert row["row_source_method"] == "informe_mensal"
    assert row["col_source_document"] == "regulamento.pdf"
    assert row["col_source_page"] == "12"
    assert row["col_confidence_score"] == 0.85
    assert _catalog_heatmap_cell_frame(catalog, snapshot, "admin", "Admin A", "admin", "Admin B").empty


def test_industry_dimension_value_snapshot_combines_evidence_gaps_and_actions():
    catalog = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05.753.599/0001-58",
                "nome_exibicao": "FIDC ABC",
                "dimension_id": "admin",
                "dimension_label": "Administrador",
                "dimension_value": "Admin A",
                "value_weight": 1.0,
                "source_layer": "snapshot",
                "source_document": "",
                "source_page": "",
                "source_method": "informe_mensal",
                "confidence_score": 1.0,
                "review_status": "",
                "is_curated": False,
                "is_multivalue": False,
            },
            {
                "cnpj_fundo": "22.222.222/0001-22",
                "nome_exibicao": "FIDC CEDENTE",
                "dimension_id": "admin",
                "dimension_label": "Administrador",
                "dimension_value": "Admin A",
                "value_weight": 1.0,
                "source_layer": "cedente",
                "source_document": "regulamento.pdf",
                "source_page": "12",
                "source_method": "manual_review",
                "confidence_score": 0.85,
                "review_status": "aprovado",
                "participant_cnpj": "12345678000190",
                "is_curated": True,
                "is_multivalue": False,
            },
        ]
    )
    snapshot = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05753599000158",
                "nome_exibicao": "FIDC ABC",
                "competencia": "2026-05",
                "pl": 100.0,
                "valid_volume_2024_2026_brl": 50.0,
                "tem_emissao_2025_2026": True,
                "document_rows": 0,
                "document_local_ready": 0,
                "cedente_rows": 0,
                "criteria_rows": 1,
                "criteria_subordination_rows": 0,
                "admin_nome": "Admin A",
                "segmento_principal": "Financeiro",
            },
            {
                "cnpj_fundo": "22222222000122",
                "nome_exibicao": "FIDC CEDENTE",
                "competencia": "2026-05",
                "pl": 80.0,
                "valid_volume_2024_2026_brl": 10.0,
                "tem_emissao_2025_2026": False,
                "document_rows": 1,
                "document_local_ready": 1,
                "cedente_rows": 1,
                "criteria_rows": 1,
                "criteria_subordination_rows": 1,
                "sub_min_pct_median": 12.5,
                "admin_nome": "Admin A",
                "segmento_principal": "Comercial",
            },
        ]
    )

    value_snapshot = _dimension_value_snapshot_frame(catalog, snapshot, "admin", "Admin A")
    value_snapshot = _apply_snapshot_gap_actions(
        value_snapshot,
        pd.DataFrame(
            [
                {
                    "gap_id": "2026-05_05753599000158",
                    "status_lacuna": "em andamento",
                    "acao_revisada": "Baixar regulamento",
                    "responsavel": "Research",
                    "prazo": "2026-07-15",
                    "notas": "",
                    "updated_at_utc": "2026-07-08T12:00:00+00:00",
                }
            ]
        ),
    )
    by_cnpj = value_snapshot.set_index("cnpj_fundo_norm")

    assert list(value_snapshot["cnpj_fundo_norm"])[0] == "05753599000158"
    assert by_cnpj.loc["05753599000158", "gap_count"] == 4
    assert by_cnpj.loc["05753599000158", "status_lacuna"] == "em andamento"
    assert by_cnpj.loc["22222222000122", "dimension_documents"] == "regulamento.pdf"
    assert bool(by_cnpj.loc["22222222000122", "dimension_curated"]) is True

    formatted = _format_dimension_value_snapshot(value_snapshot)

    assert "Camadas faltantes" in formatted.columns
    assert formatted.loc[formatted["CNPJ"].eq("05753599000158"), "Status lacuna"].iloc[0] == "em andamento"
    assert formatted.loc[formatted["CNPJ"].eq("22222222000122"), "Docs dimensão"].iloc[0] == "regulamento.pdf"


def test_industry_snapshot_gap_frame_prioritizes_missing_structured_layers():
    snapshot = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05753599000158",
                "nome_exibicao": "FIDC RECENTE",
                "pl": 100.0,
                "valid_volume_2024_2026_brl": 50.0,
                "tem_emissao_2025_2026": True,
                "document_rows": 0,
                "document_local_ready": 0,
                "cedente_rows": 0,
                "criteria_rows": 1,
                "criteria_subordination_rows": 0,
            },
            {
                "cnpj_fundo": "11111111000111",
                "nome_exibicao": "FIDC ANTIGO",
                "pl": 300.0,
                "valid_volume_2024_2026_brl": 0.0,
                "tem_emissao_2025_2026": False,
                "document_rows": 1,
                "document_local_ready": 1,
                "cedente_rows": 1,
                "criteria_rows": 1,
                "criteria_subordination_rows": 0,
            },
            {
                "cnpj_fundo": "22222222000122",
                "nome_exibicao": "FIDC COMPLETO",
                "pl": 50.0,
                "valid_volume_2024_2026_brl": 10.0,
                "tem_emissao_2025_2026": True,
                "document_rows": 1,
                "document_local_ready": 1,
                "cedente_rows": 1,
                "criteria_rows": 1,
                "criteria_subordination_rows": 1,
            },
        ]
    )

    gaps = _snapshot_gap_frame(snapshot)

    assert list(gaps["cnpj_fundo"]) == ["05753599000158", "11111111000111"]
    recent = gaps[gaps["cnpj_fundo"].eq("05753599000158")].iloc[0]
    assert bool(recent["priority_2025_2026"]) is True
    assert recent["gap_id"] == "snapshot_05753599000158"
    assert recent["gap_count"] == 4
    assert set(recent["missing_layers"].split(" | ")) == {
        "sem documento",
        "sem documento local",
        "sem cedente/sacado",
        "sem sub mínima",
    }
    overlayed = _apply_snapshot_gap_actions(
        gaps,
        pd.DataFrame(
            [
                {
                    "gap_id": recent["gap_id"],
                    "status_lacuna": "em andamento",
                    "acao_revisada": "Baixar regulamento e revisar cedente",
                    "responsavel": "Research",
                    "prazo": "2026-07-15",
                    "notas": "priorizar emissão recente",
                    "updated_at_utc": "2026-07-08T12:00:00+00:00",
                }
            ]
        ),
    )
    reviewed = overlayed[overlayed["gap_id"].eq(recent["gap_id"])].iloc[0]
    assert reviewed["status_lacuna"] == "em andamento"
    assert reviewed["acao_revisada"] == "Baixar regulamento e revisar cedente"
    assert reviewed["responsavel"] == "Research"


def test_industry_snapshot_gap_actions_for_audit_tracks_field_changes():
    previous = pd.DataFrame(
        [
            {
                "gap_id": "2026-05_05753599000158",
                "status_lacuna": "pendente",
                "acao_revisada": "",
                "responsavel": "",
                "prazo": "",
                "notas": "",
                "updated_at_utc": "",
            }
        ]
    )
    updated = pd.DataFrame(
        [
            {
                "gap_id": "2026-05_05753599000158",
                "status_lacuna": "em andamento",
                "acao_revisada": "Baixar regulamento",
                "responsavel": "Research",
                "prazo": "2026-07-15",
                "notas": "prioridade alta",
                "updated_at_utc": "2026-07-08T12:00:00+00:00",
            }
        ]
    )

    events = build_review_audit_events(
        previous=_snapshot_gap_actions_for_audit(previous),
        updated=_snapshot_gap_actions_for_audit(updated),
        key_column="gap_id",
        review_domain="snapshot_gap",
        saved_at_utc="2026-07-08T12:00:00+00:00",
        source="test",
    )

    assert set(events["field"]) == {"status", "acao_revisada", "responsavel", "prazo", "notas"}
    assert set(events["record_id"]) == {"2026-05_05753599000158"}
    assert set(events["status_after"]) == {"em andamento"}


def test_industry_pl_fic_impact_frame_quantifies_double_count_proxy():
    industry = pd.DataFrame(
        [
            {"competencia": "2026-04", "pl_total": 900.0, "pl_fic_fidc": 90.0},
            {"competencia": "2026-05", "pl_total": 1000.0, "pl_fic_fidc": 125.0},
        ]
    )

    impact = _pl_fic_impact_frame(industry)

    latest = impact.set_index("competencia").loc["2026-05"]
    assert latest["pl_ex_fic_fidc"] == 875.0
    assert latest["fic_share"] == 0.125

    no_fic_col = _pl_fic_impact_frame(pd.DataFrame([{"competencia": "2026-05", "pl_total": 1000.0}]))
    assert no_fic_col.iloc[0]["pl_fic_fidc"] == 0.0
    assert no_fic_col.iloc[0]["pl_ex_fic_fidc"] == 1000.0


def test_industry_profile_heatmap_reuses_materialized_profiles():
    profiles = pd.DataFrame(
        [
            {
                "competencia": "2026-05",
                "source_dimension_id": "admin",
                "source_dimension_label": "Administrador",
                "source_dimension_value": "Admin A",
                "target_dimension_id": "segmento",
                "target_dimension_label": "Segmento",
                "target_dimension_value": "Financeiro",
                "pl_brl": 100_000_000_000.0,
                "funds_unique": 2,
                "vehicles_unique": 3,
                "catalog_links": 4,
                "source_document_links": 1,
                "curated_links": 1,
                "weighted_links": 0,
                "avg_confidence_score": 0.8,
            },
            {
                "competencia": "2026-05",
                "source_dimension_id": "admin",
                "source_dimension_label": "Administrador",
                "source_dimension_value": "Admin A",
                "target_dimension_id": "segmento",
                "target_dimension_label": "Segmento",
                "target_dimension_value": "Industrial",
                "pl_brl": 50_000_000_000.0,
                "funds_unique": 1,
                "vehicles_unique": 1,
                "catalog_links": 2,
                "source_document_links": 0,
                "curated_links": 0,
                "weighted_links": 1,
                "avg_confidence_score": 0.6,
            },
            {
                "competencia": "2026-05",
                "source_dimension_id": "admin",
                "source_dimension_label": "Administrador",
                "source_dimension_value": "Admin A",
                "target_dimension_id": "admin",
                "target_dimension_label": "Administrador",
                "target_dimension_value": "Admin A",
                "pl_brl": 100_000_000_000.0,
                "funds_unique": 2,
                "vehicles_unique": 3,
                "catalog_links": 4,
                "source_document_links": 1,
                "curated_links": 1,
                "weighted_links": 0,
                "avg_confidence_score": 0.8,
            },
            {
                "competencia": "2026-05",
                "source_dimension_id": "admin",
                "source_dimension_label": "Administrador",
                "source_dimension_value": "Admin A",
                "target_dimension_id": "admin",
                "target_dimension_label": "Administrador",
                "target_dimension_value": "Admin B",
                "pl_brl": 10_000_000_000.0,
                "funds_unique": 1,
                "vehicles_unique": 1,
                "catalog_links": 1,
                "source_document_links": 0,
                "curated_links": 0,
                "weighted_links": 0,
                "avg_confidence_score": 0.7,
            },
        ]
    )

    heatmap = _profile_heatmap_frame(profiles, "admin", "segmento", "PL médio")
    by_segment = heatmap.set_index("coluna")

    assert by_segment.loc["Financeiro", "valor"] == 100.0
    assert by_segment.loc["Industrial", "valor"] == 50.0
    assert by_segment.loc["Financeiro", "catalog_links"] == 4
    assert by_segment.loc["Industrial", "weighted_links"] == 1

    funds = _profile_heatmap_frame(profiles, "admin", "segmento", "Fundos")
    assert funds.set_index("coluna").loc["Financeiro", "valor"] == 2

    diagonal = _profile_heatmap_frame(profiles, "admin", "admin", "Veículos")
    assert set(diagonal["coluna"]) == {"Admin A"}
    assert _profile_heatmap_frame(profiles, "admin", "segmento", "Captação líquida").empty


def test_industry_dimension_profile_coverage_summarizes_source_dimensions():
    profiles = pd.DataFrame(
        [
            {
                "source_dimension_id": "admin",
                "source_dimension_label": "Administrador",
                "source_dimension_value": "Admin A",
                "target_dimension_id": "segmento",
                "target_dimension_value": "Financeiro",
                "catalog_links": 4,
                "source_document_links": 1,
                "curated_links": 1,
                "weighted_links": 0,
                "avg_confidence_score": 0.8,
            },
            {
                "source_dimension_id": "admin",
                "source_dimension_label": "Administrador",
                "source_dimension_value": "Admin A",
                "target_dimension_id": "indexador",
                "target_dimension_value": "CDI+",
                "catalog_links": 2,
                "source_document_links": 1,
                "curated_links": 0,
                "weighted_links": 1,
                "avg_confidence_score": 0.6,
            },
            {
                "source_dimension_id": "segmento",
                "source_dimension_label": "Segmento",
                "source_dimension_value": "Financeiro",
                "target_dimension_id": "admin",
                "target_dimension_value": "Admin A",
                "catalog_links": 3,
                "source_document_links": 0,
                "curated_links": 0,
                "weighted_links": 0,
                "avg_confidence_score": 0.9,
            },
        ]
    )

    coverage = _dimension_profile_coverage_frame(profiles)
    by_dimension = coverage.set_index("source_dimension_id")

    assert by_dimension.loc["admin", "source_values"] == 1
    assert by_dimension.loc["admin", "target_dimensions"] == 2
    assert by_dimension.loc["admin", "profile_links"] == 6
    assert by_dimension.loc["admin", "source_document_ratio"] == 2 / 6
    assert by_dimension.loc["admin", "weighted_ratio"] == 1 / 6
    assert by_dimension.loc["segmento", "profile_links"] == 3


def test_industry_fund_dossier_collects_all_structured_layers():
    snapshot = pd.DataFrame(
        [
            {"cnpj_fundo": "05.753.599/0001-58", "nome_exibicao": "FIDC ABC", "snapshot_status": "completo"},
            {"cnpj_fundo": "11.111.111/0001-11", "nome_exibicao": "FIDC DEF", "snapshot_status": "basico"},
        ]
    )
    tranches = pd.DataFrame(
        [
            {"cnpj_fundo": "05753599000158", "volume_brl": "10", "ano": "2026", "indexador": "CDI+"},
            {"cnpj_fundo": "11111111000111", "volume_brl": "20", "ano": "2026", "indexador": "IPCA+"},
        ]
    )
    documents = pd.DataFrame(
        [
            {"cnpj_fundo": "05753599000158", "document_class": "regulamento", "local_exists": "true", "chunk_id": "doc-1"},
            {"cnpj_fundo": "11111111000111", "document_class": "assembleia", "local_exists": "true", "chunk_id": "doc-2"},
        ]
    )
    cedentes = pd.DataFrame(
        [
            {"cnpj_fundo": "05753599000158", "razao_social": "CEDENTE ABC", "score_confianca_final": "0.9"},
            {"cnpj_fundo": "11111111000111", "razao_social": "CEDENTE DEF", "score_confianca_final": "0.8"},
        ]
    )
    criteria = pd.DataFrame(
        [
            {"cnpj_fundo": "05753599000158", "chave": "subordination_ratio_min", "pct_min": "10"},
            {"cnpj_fundo": "11111111000111", "chave": "concentration_limits", "pct_min": "30"},
        ]
    )

    dossier = _build_fund_dossier_tables(
        cnpj="05.753.599/0001-58",
        snapshot=snapshot,
        tranches=tranches,
        documents=documents,
        cedentes=cedentes,
        criteria=criteria,
    )

    assert dossier["snapshot"]["nome_exibicao"].tolist() == ["FIDC ABC"]
    assert dossier["tranches"]["indexador"].tolist() == ["CDI+"]
    assert dossier["documents"]["document_class"].tolist() == ["regulamento"]
    assert dossier["cedentes"]["razao_social"].tolist() == ["CEDENTE ABC"]
    assert dossier["criteria"]["chave"].tolist() == ["subordination_ratio_min"]


def test_industry_snapshot_market_share_weights_multivalue_dimensions():
    snapshot = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05753599000158",
                "pl": 100.0,
                "valid_volume_2024_2026_brl": 40.0,
                "indexadores": "CDI+ | IPCA+",
                "document_rows": 2,
                "cedente_rows": 1,
                "criteria_rows": 1,
                "tem_sub_minima": True,
                "tem_emissao_2025_2026": True,
                "camadas_com_evidencia": 5,
            },
            {
                "cnpj_fundo": "11111111000111",
                "pl": 50.0,
                "valid_volume_2024_2026_brl": 10.0,
                "indexadores": "CDI+",
                "document_rows": 0,
                "cedente_rows": 0,
                "criteria_rows": 0,
                "tem_sub_minima": False,
                "tem_emissao_2025_2026": False,
                "camadas_com_evidencia": 1,
            },
        ]
    )

    market, summary = _build_snapshot_market_share(snapshot, "indexadores", "pl")

    by_dim = market.set_index("Dimensão")
    assert by_dim.loc["CDI+", "PL"] == 100.0
    assert by_dim.loc["IPCA+", "PL"] == 50.0
    assert market["PL"].sum() == 150.0
    assert summary["total_metric"] == 150.0
    assert round(float(by_dim.loc["CDI+", "Share"]), 6) == round(100 / 150, 6)


def test_industry_market_share_materializes_weighted_dimensions_and_manifest():
    snapshot = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05753599000158",
                "nome_exibicao": "FIDC ABC",
                "pl": 100.0,
                "valid_volume_2024_2026_brl": 40.0,
                "admin_nome": "Admin A",
                "indexadores": "CDI+ | IPCA+",
                "document_rows": 2,
                "cedente_rows": 1,
                "criteria_rows": 1,
                "tem_sub_minima": True,
                "tem_emissao_2025_2026": True,
                "camadas_com_evidencia": 5,
            },
            {
                "cnpj_fundo": "11111111000111",
                "nome_exibicao": "FIDC DEF",
                "pl": 50.0,
                "valid_volume_2024_2026_brl": 10.0,
                "admin_nome": "Admin B",
                "indexadores": "CDI+",
                "document_rows": 0,
                "cedente_rows": 0,
                "criteria_rows": 0,
                "tem_sub_minima": False,
                "tem_emissao_2025_2026": False,
                "camadas_com_evidencia": 1,
            },
        ]
    )

    market = build_industry_market_share(snapshot)
    indexer_pl = market[(market["dimension_id"] == "indexador") & (market["metric_id"] == "pl")].set_index("dimension_value")
    quality = industry_market_share_quality_summary(market)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        snapshot_path = tmp_path / "industry_fund_snapshot.csv.gz"
        output_path = tmp_path / "industry_market_share.csv.gz"
        manifest_path = tmp_path / "industry_market_share_manifest.json"
        snapshot.to_csv(snapshot_path, index=False, compression="gzip")
        market.to_csv(output_path, index=False, compression="gzip")
        manifest = build_market_share_pipeline_manifest(
            industry_dir=tmp_path,
            snapshot_path=snapshot_path,
            output_path=output_path,
            manifest_path=manifest_path,
            snapshot=snapshot,
            market_share=market,
        )

    assert round(float(indexer_pl.loc["CDI+", "metric_value"]), 6) == 100.0
    assert round(float(indexer_pl.loc["IPCA+", "metric_value"]), 6) == 50.0
    assert round(float(indexer_pl["metric_value"].sum()), 6) == 150.0
    assert bool(indexer_pl.loc["CDI+", "weighted_multivalue"]) is True
    assert quality["dimensions"] >= 3
    assert quality["metrics"] == 6
    assert manifest["schema_version"] == "industry-market-share-manifest/v1"
    assert manifest["quality"]["rows"] == len(market)


def test_industry_dimension_catalog_preserves_sources_and_weights():
    snapshot = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05.753.599/0001-58",
                "nome_exibicao": "FIDC ABC",
                "admin_nome": "Admin A",
                "segmento_principal": "Comercial",
                "is_fic_fidc": False,
                "indexadores": "CDI+ | IPCA+",
                "criteria_keys": "subordination_ratio_min | concentration_limits",
                "criteria_documentos": "reg.pdf",
                "criteria_score_mediana": 0.9,
                "sub_min_pct_median": 10.0,
                "tem_sub_minima": True,
                "camadas_com_evidencia": 5,
                "snapshot_status": "completo",
                "first_offer_year": 2026,
                "emission_cohort": "2026YTD",
            }
        ]
    )
    cedentes = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05753599000158",
                "fundo": "FIDC ABC",
                "razao_social": "CEDENTE ABC S.A.",
                "grupo_economico": "Grupo ABC",
                "participant_type": "cedente_originador",
                "tipo_participante": "cedente/originador",
                "cnpj_participante": "12.345.678/0001-99",
                "status_revisao": "aprovado",
                "ativo_curadoria": True,
                "periodo_prioritario": "2025-2026 YTD",
                "score_confianca_final": 0.95,
                "metodo_extracao": "manual",
                "documento_origem": "regulamento.pdf",
                "pagina": "12",
            },
            {
                "cnpj_fundo": "05753599000158",
                "fundo": "FIDC ABC",
                "razao_social": "CEDENTE DEF S.A.",
                "grupo_economico": "Grupo DEF",
                "participant_type": "cedente_originador",
                "tipo_participante": "cedente/originador",
                "cnpj_participante": "98.765.432/0001-10",
                "status_revisao": "aprovado",
                "ativo_curadoria": True,
                "periodo_prioritario": "2025-2026 YTD",
                "score_confianca_final": 0.85,
                "metodo_extracao": "manual",
                "documento_origem": "regulamento.pdf",
                "pagina": "13",
            },
        ]
    )

    catalog = build_industry_dimension_catalog(snapshot=snapshot, cedentes=cedentes)
    quality = industry_dimension_catalog_quality_summary(catalog)
    indexers = catalog[catalog["dimension_id"].eq("indexador")].set_index("dimension_value")
    first_offer_year = catalog[catalog["dimension_id"].eq("ano_primeira_oferta")].set_index("dimension_value")
    emission_cohort = catalog[catalog["dimension_id"].eq("safra_emissao")].set_index("dimension_value")
    cedente_rows = catalog[catalog["dimension_id"].eq("cedente_sacado")].set_index("dimension_value")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        snapshot_path = tmp_path / "industry_fund_snapshot.csv.gz"
        cedentes_path = tmp_path / "cedentes_structured.csv.gz"
        output_path = tmp_path / "industry_dimension_catalog.csv.gz"
        manifest_path = tmp_path / "industry_dimension_catalog_manifest.json"
        snapshot.to_csv(snapshot_path, index=False, compression="gzip")
        cedentes.to_csv(cedentes_path, index=False, compression="gzip")
        catalog.to_csv(output_path, index=False, compression="gzip")
        manifest = build_dimension_catalog_pipeline_manifest(
            industry_dir=tmp_path,
            snapshot_path=snapshot_path,
            cedentes_path=cedentes_path,
            output_path=output_path,
            manifest_path=manifest_path,
            snapshot=snapshot,
            cedentes=cedentes,
            catalog=catalog,
        )

    assert round(float(indexers.loc["CDI+", "value_weight"]), 6) == 0.5
    assert round(float(indexers.loc["IPCA+", "value_weight"]), 6) == 0.5
    assert "2026" in first_offer_year.index
    assert "2026YTD" in emission_cohort.index
    assert round(float(cedente_rows.loc["CEDENTE ABC S.A.", "value_weight"]), 6) == 0.5
    assert cedente_rows.loc["CEDENTE ABC S.A.", "source_document"] == "regulamento.pdf"
    assert cedente_rows.loc["CEDENTE ABC S.A.", "source_page"] == "12"
    assert quality["dimensions"] >= 8
    assert quality["with_source_document"] >= 2
    assert manifest["schema_version"] == "industry-dimension-catalog-manifest/v1"
    assert manifest["quality"]["rows"] == len(catalog)


def test_industry_dimension_catalog_quality_flags_traceability_gaps():
    catalog = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05753599000158",
                "nome_exibicao": "FIDC ABC",
                "dimension_id": "admin",
                "dimension_label": "Administrador",
                "dimension_value": "Admin A",
                "source_layer": "snapshot",
                "source_method": "informe_mensal",
                "confidence_score": 1.0,
                "source_document": "",
                "source_page": "",
                "review_status": "",
                "is_curated": False,
                "is_multivalue": False,
            },
            {
                "cnpj_fundo": "11111111000111",
                "nome_exibicao": "FIDC DEF",
                "dimension_id": "cedente_sacado",
                "dimension_label": "Cedente/sacado",
                "dimension_value": "CEDENTE DEF",
                "source_layer": "cedente",
                "source_method": "manual_review",
                "confidence_score": 0.8,
                "source_document": "regulamento.pdf",
                "source_page": "",
                "review_status": "",
                "participant_cnpj": "12345678000190",
                "is_curated": True,
                "is_multivalue": False,
                "priority_2025_2026": True,
            },
        ]
    )

    quality = _dimension_catalog_quality_frame(catalog)
    gaps = _dimension_catalog_gap_frame(catalog)
    by_dimension = quality.set_index("dimension_id")

    assert by_dimension.loc["admin", "source_method_ratio"] == 1.0
    assert pd.isna(by_dimension.loc["admin", "source_document_ratio"])
    assert by_dimension.loc["cedente_sacado", "source_document_ratio"] == 1.0
    assert by_dimension.loc["cedente_sacado", "source_page_ratio"] == 0.0
    assert by_dimension.loc["cedente_sacado", "review_status_ratio"] == 0.0
    assert len(gaps) == 1
    assert gaps.iloc[0]["missing_traceability_fields"] == "página | status revisão"

    formatted_quality = _format_dimension_catalog_quality(quality)
    formatted_gaps = _format_dimension_catalog_gaps(gaps)

    assert "Score qualidade" in formatted_quality.columns
    assert formatted_gaps.iloc[0]["Campos faltantes"] == "página | status revisão"


def test_industry_dimension_catalog_gap_actions_overlay_and_audit():
    catalog = pd.DataFrame(
        [
            {
                "cnpj_fundo": "11111111000111",
                "nome_exibicao": "FIDC DEF",
                "dimension_id": "cedente_sacado",
                "dimension_label": "Cedente/sacado",
                "dimension_value": "CEDENTE DEF",
                "source_layer": "cedente",
                "source_method": "manual_review",
                "confidence_score": 0.8,
                "source_document": "regulamento.pdf",
                "source_page": "",
                "review_status": "",
                "participant_cnpj": "12345678000190",
                "is_curated": True,
                "priority_2025_2026": True,
            }
        ]
    )
    gaps = _dimension_catalog_gap_frame(catalog)
    gap_id = gaps.iloc[0]["traceability_gap_id"]
    actions = pd.DataFrame(
        [
            {
                "traceability_gap_id": gap_id,
                "status_lacuna": "em andamento",
                "acao_revisada": "Localizar página no regulamento",
                "responsavel": "Research",
                "prazo": "2026-07-20",
                "notas": "prioridade cedente",
                "updated_at_utc": "2026-07-08T12:00:00+00:00",
            }
        ]
    )

    overlayed = _apply_catalog_gap_actions(gaps, actions)
    events = build_review_audit_events(
        previous=_catalog_gap_actions_for_audit(pd.DataFrame(columns=actions.columns)),
        updated=_catalog_gap_actions_for_audit(actions),
        key_column="traceability_gap_id",
        review_domain="dimension_catalog_gap",
        saved_at_utc="2026-07-08T12:00:00+00:00",
        source="test",
    )

    assert overlayed.iloc[0]["status_lacuna"] == "em andamento"
    assert overlayed.iloc[0]["acao_revisada"] == "Localizar página no regulamento"
    assert set(events["field"]) == {"status", "acao_revisada", "responsavel", "prazo", "notas"}
    assert set(events["record_id"]) == {gap_id}


def test_industry_dimension_monthly_aggregates_weighted_series_and_manifest():
    vehicle = pd.DataFrame(
        [
            {
                "competencia": "2026-04",
                "cnpj": "05753599000158",
                "cnpj_fundo": "05753599000158",
                "pl": 100.0,
                "captacao_liquida": 10.0,
                "carteira_dc": 80.0,
                "dc_inadimplentes_ajustado": 4.0,
                "cotistas": 2,
            },
            {
                "competencia": "2026-04",
                "cnpj": "11111111000111",
                "cnpj_fundo": "11111111000111",
                "pl": 50.0,
                "captacao_liquida": -5.0,
                "carteira_dc": 20.0,
                "dc_inadimplentes_ajustado": 1.0,
                "cotistas": 1,
            },
            {
                "competencia": "2026-05",
                "cnpj": "05753599000158",
                "cnpj_fundo": "05753599000158",
                "pl": 120.0,
                "captacao_liquida": 20.0,
                "carteira_dc": 90.0,
                "dc_inadimplentes_ajustado": 9.0,
                "cotistas": 3,
            },
        ]
    )
    catalog = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05753599000158",
                "dimension_id": "indexador",
                "dimension_label": "Indexador",
                "dimension_value": "CDI+",
                "value_weight": 0.5,
                "source_document": "reg.pdf",
                "is_curated": False,
                "is_multivalue": True,
            },
            {
                "cnpj_fundo": "05753599000158",
                "dimension_id": "indexador",
                "dimension_label": "Indexador",
                "dimension_value": "IPCA+",
                "value_weight": 0.5,
                "source_document": "reg.pdf",
                "is_curated": False,
                "is_multivalue": True,
            },
            {
                "cnpj_fundo": "11111111000111",
                "dimension_id": "indexador",
                "dimension_label": "Indexador",
                "dimension_value": "CDI+",
                "value_weight": 1.0,
                "source_document": "",
                "is_curated": False,
                "is_multivalue": False,
            },
        ]
    )

    monthly = build_industry_dimension_monthly(vehicle_monthly=vehicle, dimension_catalog=catalog)
    quality = industry_dimension_monthly_quality_summary(monthly)
    april = monthly[monthly["competencia"].eq("2026-04")].set_index("dimension_value")
    may = monthly[monthly["competencia"].eq("2026-05")].set_index("dimension_value")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        vehicle_path = tmp_path / "vehicle_monthly.csv.gz"
        catalog_path = tmp_path / "industry_dimension_catalog.csv.gz"
        output_path = tmp_path / "industry_dimension_monthly.csv.gz"
        manifest_path = tmp_path / "industry_dimension_monthly_manifest.json"
        vehicle.to_csv(vehicle_path, index=False, compression="gzip")
        catalog.to_csv(catalog_path, index=False, compression="gzip")
        monthly.to_csv(output_path, index=False, compression="gzip")
        manifest = build_dimension_monthly_pipeline_manifest(
            industry_dir=tmp_path,
            vehicle_monthly_path=vehicle_path,
            dimension_catalog_path=catalog_path,
            output_path=output_path,
            manifest_path=manifest_path,
            vehicle_monthly=vehicle,
            dimension_catalog=catalog,
            monthly=monthly,
        )

    assert april.loc["CDI+", "pl_brl"] == 100.0
    assert april.loc["IPCA+", "pl_brl"] == 50.0
    assert may.loc["CDI+", "pl_brl"] == 60.0
    assert round(float(may.loc["CDI+", "inad_pct_ajustada"]), 6) == 0.1
    assert quality["months"] == 2
    assert quality["dimensions"] == 1
    assert manifest["schema_version"] == "industry-dimension-monthly-manifest/v1"
    assert manifest["quality"]["rows"] == len(monthly)


def test_industry_dimension_radar_tracks_window_and_12m_growth():
    months = pd.period_range("2025-06", "2026-06", freq="M").astype(str)
    rows = []
    for idx, competencia in enumerate(months):
        rows.append(
            {
                "competencia": competencia,
                "dimension_id": "admin",
                "dimension_value": "Admin A",
                "pl_brl": 100.0 + idx * 10.0,
                "captacao_liquida_brl": 10.0,
                "carteira_dc_brl": 500.0,
                "dc_inadimplentes_ajustado_brl": 25.0,
                "funds_unique": 2,
                "vehicles_unique": 3,
                "catalog_links": 4,
                "source_document_links": 2,
                "curated_links": 1,
                "weighted_links": 0,
            }
        )
        rows.append(
            {
                "competencia": competencia,
                "dimension_id": "admin",
                "dimension_value": "Admin B",
                "pl_brl": 50.0,
                "captacao_liquida_brl": -1.0,
                "carteira_dc_brl": 100.0,
                "dc_inadimplentes_ajustado_brl": 0.0,
                "funds_unique": 1,
                "vehicles_unique": 1,
                "catalog_links": 1,
                "source_document_links": 0,
                "curated_links": 0,
                "weighted_links": 0,
            }
        )
    monthly = pd.DataFrame(rows)

    radar = _dimension_radar_frame(monthly, dimension_id="admin", comp="2026-06", period="Últimos 12 meses")
    by_value = radar.set_index("dimension_value")
    admin_a = by_value.loc["Admin A"]

    assert admin_a["competencia_atual"] == "2026-06"
    assert admin_a["competencia_12m_antes"] == "2025-06"
    assert admin_a["pl_atual_brl"] == 220.0
    assert admin_a["captacao_janela_brl"] == 120.0
    assert admin_a["pl_delta_12m_brl"] == 120.0
    assert round(float(admin_a["pl_growth_12m_pct"]), 6) == 1.2
    assert admin_a["evidence_coverage"] == 0.5

    formatted = _format_dimension_radar(radar.head(1))

    assert list(formatted.columns)[:5] == ["Valor", "Competência", "PL atual", "Captação janela", "Delta PL 12m"]
    assert formatted.iloc[0]["Cresc. PL 12m"] == "120,0%"


def test_industry_dimension_profiles_crosses_catalog_dimensions_and_manifest():
    snapshot = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05753599000158",
                "cnpj": "05753599000158",
                "competencia": "2026-05",
                "pl": 100.0,
                "valid_volume_2024_2026_brl": 40.0,
                "document_rows": 2,
                "cedente_rows": 1,
                "criteria_rows": 1,
                "camadas_com_evidencia": 4,
                "tem_sub_minima": True,
            },
            {
                "cnpj_fundo": "11111111000111",
                "cnpj": "11111111000111",
                "competencia": "2026-05",
                "pl": 50.0,
                "valid_volume_2024_2026_brl": 10.0,
                "document_rows": 1,
                "cedente_rows": 0,
                "criteria_rows": 0,
                "camadas_com_evidencia": 2,
                "tem_sub_minima": False,
            },
        ]
    )
    catalog = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05753599000158",
                "dimension_id": "admin",
                "dimension_label": "Administrador",
                "dimension_value": "ADMIN A",
                "value_weight": 1.0,
            },
            {
                "cnpj_fundo": "11111111000111",
                "dimension_id": "admin",
                "dimension_label": "Administrador",
                "dimension_value": "ADMIN A",
                "value_weight": 1.0,
            },
            {
                "cnpj_fundo": "05753599000158",
                "dimension_id": "segmento",
                "dimension_label": "Segmento",
                "dimension_value": "Financeiro",
                "value_weight": 1.0,
            },
            {
                "cnpj_fundo": "11111111000111",
                "dimension_id": "segmento",
                "dimension_label": "Segmento",
                "dimension_value": "Industrial",
                "value_weight": 1.0,
            },
            {
                "cnpj_fundo": "05753599000158",
                "dimension_id": "indexador",
                "dimension_label": "Indexador",
                "dimension_value": "CDI+",
                "value_weight": 0.5,
                "source_document": "reg.pdf",
                "is_multivalue": True,
                "confidence_score": 0.8,
            },
            {
                "cnpj_fundo": "05753599000158",
                "dimension_id": "indexador",
                "dimension_label": "Indexador",
                "dimension_value": "IPCA+",
                "value_weight": 0.5,
                "source_document": "reg.pdf",
                "is_multivalue": True,
                "confidence_score": 0.8,
            },
        ]
    )

    profiles = build_industry_dimension_profiles(snapshot=snapshot, dimension_catalog=catalog)
    quality = industry_dimension_profile_quality_summary(profiles)
    admin_segments = profiles[
        profiles["source_dimension_id"].eq("admin")
        & profiles["source_dimension_value"].eq("ADMIN A")
        & profiles["target_dimension_id"].eq("segmento")
    ].set_index("target_dimension_value")
    admin_indexers = profiles[
        profiles["source_dimension_id"].eq("admin")
        & profiles["source_dimension_value"].eq("ADMIN A")
        & profiles["target_dimension_id"].eq("indexador")
    ].set_index("target_dimension_value")

    assert admin_segments.loc["Financeiro", "pl_brl"] == 100.0
    assert admin_segments.loc["Industrial", "pl_brl"] == 50.0
    assert admin_indexers.loc["CDI+", "pl_brl"] == 50.0
    assert admin_indexers.loc["IPCA+", "pl_brl"] == 50.0
    assert admin_indexers.loc["CDI+", "source_document_links"] == 1
    assert quality["source_dimensions"] == 3
    assert quality["target_dimensions"] == 3

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        snapshot_path = tmp_path / "industry_fund_snapshot.csv.gz"
        catalog_path = tmp_path / "industry_dimension_catalog.csv.gz"
        output_path = tmp_path / "industry_dimension_profiles.csv.gz"
        manifest_path = tmp_path / "industry_dimension_profile_manifest.json"
        snapshot.to_csv(snapshot_path, index=False, compression="gzip")
        catalog.to_csv(catalog_path, index=False, compression="gzip")
        profiles.to_csv(output_path, index=False, compression="gzip")
        manifest = build_dimension_profile_pipeline_manifest(
            industry_dir=tmp_path,
            snapshot_path=snapshot_path,
            dimension_catalog_path=catalog_path,
            output_path=output_path,
            manifest_path=manifest_path,
            snapshot=snapshot,
            dimension_catalog=catalog,
            profiles=profiles,
        )

    assert manifest["schema_version"] == "industry-dimension-profile-manifest/v1"
    assert manifest["quality"]["rows"] == len(profiles)


def test_industry_monthly_readiness_flags_release_blockers_and_normalizes_competencia():
    index = {
        "quality_rollup": {
            "competencia_snapshot": "202605",
            "dimension_monthly_latest_competencia": "2026-05",
        },
        "modules": [
            {"label": "Base granular mensal", "status": "ok", "command": "python base.py"},
            {"label": "Inventário documental", "status": "missing_artifact", "command": "python docs.py"},
        ],
        "artifact_index": [
            {"module_id": "documents", "artifact": "manifest", "required": True, "exists": False},
            {"module_id": "fund_snapshot", "artifact": "snapshot_gap_action_audit", "required": False, "exists": False},
        ],
    }
    monthly_delta = pd.DataFrame(
        [
            {
                "competencia_atual": "2026-05",
                "cnpj_fundo": "05753599000158",
                "fundo": "FIDC NOVO",
                "priority_band": "alta",
                "priority_score": 95,
                "status_acao": "pendente",
                "next_actions": "descobrir documentos",
            },
            {
                "competencia_atual": "2026-05",
                "cnpj_fundo": "11111111000111",
                "fundo": "FIDC BAIXO",
                "priority_band": "baixa",
                "priority_score": 5,
                "status_acao": "concluído",
                "next_actions": "",
            },
        ]
    )
    snapshot = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05753599000158",
                "nome_exibicao": "FIDC NOVO",
                "pl": 100.0,
                "valid_volume_2024_2026_brl": 50.0,
                "tem_emissao_2025_2026": True,
                "document_rows": 0,
                "document_local_ready": 0,
                "cedente_rows": 0,
                "criteria_rows": 0,
                "criteria_subordination_rows": 0,
            }
        ]
    )
    catalog = pd.DataFrame(
        [
            {
                "cnpj_fundo": "05753599000158",
                "nome_exibicao": "FIDC NOVO",
                "dimension_id": "cedente_sacado",
                "dimension_label": "Cedente/sacado",
                "dimension_value": "CEDENTE ABC",
                "source_layer": "cedente",
                "source_method": "manual_review",
                "confidence_score": 0.8,
                "source_document": "regulamento.pdf",
                "source_page": "",
                "review_status": "",
                "participant_cnpj": "12345678000190",
                "is_curated": True,
                "is_multivalue": False,
                "priority_2025_2026": True,
            }
        ]
    )

    readiness = _monthly_readiness_frame(
        index=index,
        monthly_delta=monthly_delta,
        snapshot=snapshot,
        dimension_catalog=catalog,
        snapshot_gap_actions=pd.DataFrame(),
        catalog_gap_actions=pd.DataFrame(),
    )
    by_check = readiness.set_index("check_id")

    assert by_check.loc["competencia_alignment", "status_prontidao"] == "ok"
    assert by_check.loc["module_status", "status_prontidao"] == "bloqueado"
    assert by_check.loc["artifact_presence", "pendencias"] == 1
    assert by_check.loc["monthly_delta_queue", "status_prontidao"] == "bloqueado"
    assert by_check.loc["snapshot_structural_gaps", "pendencias"] == 1
    assert by_check.loc["catalog_traceability_gaps", "status_prontidao"] == "bloqueado"

    formatted = _format_monthly_readiness(readiness)

    assert "Ação sugerida" in formatted.columns
    assert formatted.loc[formatted["ID"].eq("competencia_alignment"), "Status"].iloc[0] == "ok"
    assert formatted.loc[formatted["ID"].eq("artifact_presence"), "Pendências"].iloc[0] == "1"


def test_industry_monthly_delta_prioritizes_incremental_review_queue():
    vehicle = pd.DataFrame(
        [
            {
                "competencia": "2026-04",
                "cnpj_fundo": "11111111000111",
                "denominacao": "FIDC RECORRENTE",
                "admin_nome": "ADMIN A",
                "segmento_principal": "Comercial",
                "pl": 900.0,
                "captacao_liquida": 10.0,
                "carteira_dc": 700.0,
                "cotistas": 10,
            },
            {
                "competencia": "2026-05",
                "cnpj_fundo": "11111111000111",
                "denominacao": "FIDC RECORRENTE",
                "admin_nome": "ADMIN A",
                "segmento_principal": "Comercial",
                "pl": 1000.0,
                "captacao_liquida": 20.0,
                "carteira_dc": 800.0,
                "cotistas": 12,
            },
            {
                "competencia": "2026-05",
                "cnpj_fundo": "22222222000122",
                "denominacao": "FIDC NOVO",
                "admin_nome": "ADMIN B",
                "segmento_principal": "Serviços",
                "pl": 2000.0,
                "captacao_liquida": 150_000_000.0,
                "carteira_dc": 1200.0,
                "cotistas": 8,
            },
            {
                "competencia": "2026-04",
                "cnpj_fundo": "33333333000133",
                "denominacao": "FIDC SAIU",
                "admin_nome": "ADMIN C",
                "segmento_principal": "Industrial",
                "pl": 500.0,
                "captacao_liquida": -5.0,
                "carteira_dc": 300.0,
                "cotistas": 5,
            },
            {
                "competencia": "2026-03",
                "cnpj_fundo": "44444444000144",
                "denominacao": "FIDC REATIVADO",
                "admin_nome": "ADMIN D",
                "segmento_principal": "Financeiro",
                "pl": 100.0,
                "captacao_liquida": 0.0,
                "carteira_dc": 80.0,
                "cotistas": 3,
            },
            {
                "competencia": "2026-05",
                "cnpj_fundo": "44444444000144",
                "denominacao": "FIDC REATIVADO",
                "admin_nome": "ADMIN D",
                "segmento_principal": "Financeiro",
                "pl": 700.0,
                "captacao_liquida": 30.0,
                "carteira_dc": 500.0,
                "cotistas": 4,
            },
        ]
    )
    snapshot = pd.DataFrame(
        [
            {
                "cnpj_fundo": "11111111000111",
                "nome_exibicao": "FIDC RECORRENTE",
                "document_rows": 2,
                "cedente_rows": 1,
                "criteria_rows": 1,
                "tem_sub_minima": True,
                "camadas_com_evidencia": 4,
            },
            {
                "cnpj_fundo": "22222222000122",
                "nome_exibicao": "FIDC NOVO",
                "document_rows": 0,
                "cedente_rows": 0,
                "criteria_rows": 0,
                "tem_sub_minima": False,
                "camadas_com_evidencia": 1,
            },
        ]
    )

    delta = build_industry_monthly_delta(
        vehicle_monthly=vehicle,
        snapshot=snapshot,
        metadata={"competencia_snapshot": "202605"},
    )
    quality = industry_monthly_delta_quality_summary(delta)

    statuses = delta.set_index("cnpj_fundo")["status_delta"].to_dict()
    novo = delta[delta["cnpj_fundo"].eq("22222222000122")].iloc[0]

    assert statuses["11111111000111"] == "recorrente"
    assert statuses["22222222000122"] == "novo_no_ime"
    assert statuses["33333333000133"] == "saiu_do_ime"
    assert statuses["44444444000144"] == "reativado"
    assert bool(novo["needs_document_discovery"]) is True
    assert bool(novo["needs_cedente_review"]) is True
    assert "curar critérios" in novo["next_actions"]
    assert str(novo["delta_id"]) == "202605_22222222000122"
    assert quality["new_funds"] == 1
    assert quality["reactivated_funds"] == 1
    assert quality["exited_funds"] == 1

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        output_path = tmp_path / "industry_monthly_delta.csv.gz"
        manifest_path = tmp_path / "industry_monthly_delta_manifest.json"
        actions_path = tmp_path / "monthly_delta_actions.csv"
        actions = pd.DataFrame(
            [
                {
                    "delta_id": novo["delta_id"],
                    "status_acao": "em andamento",
                    "acao_revisada": "Priorizar regulamento e suplemento",
                    "responsavel": "mesa",
                    "prazo": "2026-06-10",
                    "notas": "FIDC novo no IME",
                    "updated_at_utc": "2026-06-01T12:00:00+00:00",
                }
            ]
        )
        saved_actions = save_monthly_delta_actions(actions, actions_path)
        loaded_actions = load_monthly_delta_actions(actions_path)
        overlayed = apply_monthly_delta_actions(delta, loaded_actions)
        novo_overlayed = overlayed[overlayed["delta_id"].eq(novo["delta_id"])].iloc[0]
        audit_events = build_review_audit_events(
            previous=_monthly_delta_actions_for_audit(pd.DataFrame(columns=MONTHLY_DELTA_ACTION_COLUMNS)),
            updated=_monthly_delta_actions_for_audit(loaded_actions),
            key_column="delta_id",
            review_domain="monthly_delta_action",
            saved_at_utc="2026-06-01T12:00:00+00:00",
            source="test",
        )

        assert saved_actions.columns.tolist() == MONTHLY_DELTA_ACTION_COLUMNS
        assert loaded_actions.to_dict("records") == saved_actions.to_dict("records")
        assert novo_overlayed["status_acao"] == "em andamento"
        assert novo_overlayed["responsavel"] == "mesa"
        assert industry_monthly_delta_quality_summary(overlayed)["action_status_counts"]["em andamento"] == 1
        assert set(audit_events["field"]) == {"status", "acao_revisada", "responsavel", "prazo", "notas"}
        assert set(audit_events["record_id"]) == {novo["delta_id"]}
        assert set(audit_events["status_after"]) == {"em andamento"}

        save_cedente_structured(delta, output_path)
        manifest = build_monthly_delta_pipeline_manifest(
            industry_dir=tmp_path,
            output_path=output_path,
            manifest_path=manifest_path,
            vehicle_monthly=vehicle,
            snapshot=snapshot,
            delta=delta,
        )

    assert manifest["schema_version"] == "industry-monthly-delta-manifest/v1"
    assert manifest["quality"]["rows"] == len(delta)
    assert manifest["outputs"]["monthly_delta"]["sha256"]


def test_industry_pipeline_index_rolls_up_modules_and_refresh_plan():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for name in [
            "industry_monthly.csv",
            "vehicle_monthly.csv.gz",
            "update_audit_monthly.csv",
            "admin_monthly.csv",
            "flows_monthly.csv",
            "segments_monthly.csv",
            "prestadores_latest.csv",
            "universe_latest.csv",
        ]:
            (tmp_path / name).write_text("col\n1\n", encoding="utf-8")
        (tmp_path / "metadata.json").write_text(
            json.dumps(
                {
                    "gerado_em_utc": "2026-07-08T00:00:00+00:00",
                    "competencia_inicial": "201301",
                    "competencia_final": "202606",
                    "competencia_snapshot": "202605",
                    "n_competencias": 162,
                }
            ),
            encoding="utf-8",
        )

        def write_module_manifest(name: str, pipeline: str, output_name: str, quality: dict[str, object]) -> None:
            output_path = tmp_path / output_name
            output_path.write_text("col\n1\n", encoding="utf-8")
            manifest = {
                "schema_version": f"{pipeline}/v1",
                "generated_at_utc": "2026-07-08T01:00:00+00:00",
                "pipeline": pipeline,
                "inputs": {},
                "outputs": {output_name.replace(".", "_"): {"path": str(output_path)}},
                "stages": [{"id": "stage", "label": "Stage", "status": "ok", "rerun": "python x.py"}],
                "quality": quality,
            }
            (tmp_path / name).write_text(json.dumps(manifest), encoding="utf-8")

        write_module_manifest(
            "industry_monthly_delta_manifest.json",
            "industry_monthly_delta",
            "industry_monthly_delta.csv.gz",
            {
                "rows": 6,
                "competencia_atual": "2026-05",
                "competencia_anterior": "2026-04",
                "new_funds": 1,
                "reactivated_funds": 1,
                "exited_funds": 1,
                "high_priority_rows": 2,
                "needs_document_discovery": 2,
            },
        )
        (tmp_path / "monthly_delta_actions.csv").write_text(
            "delta_id,status_acao,acao_revisada,responsavel,prazo,notas,updated_at_utc\n"
            "202605_22222222000122,em andamento,baixar regulamento,research,2026-07-15,,2026-07-08T12:00:00+00:00\n"
        )
        (tmp_path / "monthly_delta_action_audit.csv").write_text(
            "event_id,saved_at_utc,review_domain,record_id,field,old_value,new_value,status_after,source\n"
            "delta1,2026-07-08T12:00:00+00:00,monthly_delta_action,202605_22222222000122,status,pendente,em andamento,em andamento,test\n"
        )
        write_module_manifest(
            "industry_issuance_manifest.json",
            "industry_issuance_structured",
            "issuance_annual.csv",
            {"annual_volume_conservador_brl": 100.0, "tranche_rows": 1},
        )
        write_module_manifest(
            "industry_document_manifest.json",
            "industry_document_inventory",
            "document_inventory.csv.gz",
            {"document_rows": 2, "chunks": 1, "max_documents_per_chunk": 2},
        )
        (tmp_path / "document_chunk_actions.csv").write_text(
            "chunk_id,status_lote,acao_revisada,responsavel,prazo,notas,updated_at_utc\n"
            "doc-0001,em andamento,rodar OCR,research,2026-07-20,,2026-07-08T12:00:00+00:00\n"
        )
        (tmp_path / "document_chunk_action_audit.csv").write_text(
            "event_id,saved_at_utc,review_domain,record_id,field,old_value,new_value,status_after,source\n"
            "doc1,2026-07-08T12:00:00+00:00,document_chunk_action,doc-0001,status,pendente,em andamento,em andamento,test\n"
        )
        write_module_manifest(
            "industry_pipeline_manifest.json",
            "industry_cedentes_structured",
            "cedentes_structured.csv.gz",
            {"structured_rows": 3, "structured_funds": 2},
        )
        write_module_manifest(
            "industry_criteria_manifest.json",
            "industry_criteria_structured",
            "criteria_structured.csv.gz",
            {
                "structured_rows": 4,
                "subordination_funds": 2,
                "subordination": {"median": 10.0},
            },
        )
        write_module_manifest(
            "industry_fund_snapshot_manifest.json",
            "industry_fund_snapshot",
            "industry_fund_snapshot.csv.gz",
            {
                "fund_rows": 2,
                "with_cedentes": 1,
                "with_criteria": 1,
                "with_subordination_min": 1,
            },
        )
        (tmp_path / "snapshot_gap_actions.csv").write_text(
            "gap_id,status_lacuna,acao_revisada,responsavel,prazo,notas,updated_at_utc\n"
            "2026-05_05753599000158,em andamento,baixar documento,research,2026-07-15,,2026-07-08T12:00:00+00:00\n"
        )
        (tmp_path / "snapshot_gap_action_audit.csv").write_text(
            "event_id,saved_at_utc,review_domain,record_id,field,old_value,new_value,status_after,source\n"
            "abc,2026-07-08T12:00:00+00:00,snapshot_gap,2026-05_05753599000158,status,pendente,em andamento,em andamento,test\n"
        )
        write_module_manifest(
            "industry_dimension_catalog_manifest.json",
            "industry_dimension_catalog",
            "industry_dimension_catalog.csv.gz",
            {
                "rows": 80,
                "funds": 2,
                "dimensions": 10,
                "curated_rows": 12,
                "weighted_dimensions": 3,
                "with_source_document": 20,
                "with_confidence": 18,
            },
        )
        write_module_manifest(
            "industry_dimension_monthly_manifest.json",
            "industry_dimension_monthly",
            "industry_dimension_monthly.csv.gz",
            {
                "rows": 120,
                "months": 12,
                "dimensions": 10,
                "dimension_values": 20,
                "latest_competencia": "202605",
                "latest_rows": 10,
                "with_source_document_links": 8,
                "curated_rows": 4,
            },
        )
        write_module_manifest(
            "industry_dimension_profile_manifest.json",
            "industry_dimension_profiles",
            "industry_dimension_profiles.csv.gz",
            {
                "rows": 240,
                "competencia": "2026-05",
                "source_dimensions": 10,
                "target_dimensions": 10,
                "source_values": 20,
                "target_values": 20,
                "with_source_document_links": 8,
                "curated_links": 4,
            },
        )
        write_module_manifest(
            "industry_market_share_manifest.json",
            "industry_market_share",
            "industry_market_share.csv.gz",
            {
                "rows": 30,
                "dimensions": 5,
                "metrics": 6,
                "weighted_dimensions": 2,
                "top5_pl_share_admin": 0.7,
                "hhi_pl_admin": 1800.0,
                "source_snapshot_rows": 2,
            },
        )

        index = build_industry_pipeline_index(industry_dir=tmp_path)

    assert index["schema_version"] == "industry-pipeline-index/v1"
    assert index["quality_rollup"]["modules_total"] == 11
    assert index["quality_rollup"]["module_status_counts"]["ok"] == 11
    assert index["quality_rollup"]["artifacts_missing"] == 0
    assert index["quality_rollup"]["manual_review_artifacts_total"] == 6
    assert index["quality_rollup"]["manual_review_artifacts_present"] == 6
    assert index["quality_rollup"]["competencia_snapshot"] == "202605"
    assert index["quality_rollup"]["monthly_delta_competencia_atual"] == "2026-05"
    assert index["quality_rollup"]["monthly_delta_new_funds"] == 1
    assert index["quality_rollup"]["monthly_delta_high_priority"] == 2
    assert index["quality_rollup"]["document_chunks"] == 1
    assert index["quality_rollup"]["document_chunk_actions_rows"] == 1
    assert index["quality_rollup"]["document_chunks_in_progress"] == 1
    assert index["quality_rollup"]["document_chunks_without_action"] == 0
    assert index["quality_rollup"]["subordination_median_pct"] == 10.0
    assert index["quality_rollup"]["fund_snapshot_rows"] == 2
    assert index["quality_rollup"]["dimension_catalog_rows"] == 80
    assert index["quality_rollup"]["dimension_catalog_dimensions"] == 10
    assert index["quality_rollup"]["dimension_monthly_rows"] == 120
    assert index["quality_rollup"]["dimension_monthly_latest_competencia"] == "202605"
    assert index["quality_rollup"]["dimension_profile_rows"] == 240
    assert index["quality_rollup"]["dimension_profile_source_dimensions"] == 10
    assert index["quality_rollup"]["market_share_rows"] == 30
    assert index["quality_rollup"]["market_share_dimensions"] == 5
    assert {stage["module_id"] for stage in index["refresh_plan"]} >= {
        "base_monthly",
        "fund_snapshot",
        "dimension_catalog",
        "dimension_profiles",
        "dimension_monthly",
        "market_share",
        "monthly_delta",
        "pipeline_index",
    }
    assert any(row["artifact"] == "manifest" for row in index["artifact_index"])
    readiness = {row["check_id"]: row for row in index["readiness_checks"]}
    assert readiness["competencia_alignment"]["status_prontidao"] == "ok"
    assert readiness["monthly_delta_queue"]["status_prontidao"] == "bloqueado"
    assert readiness["monthly_delta_queue"]["pendencias"] == 2
    assert readiness["document_chunk_processing"]["status_prontidao"] == "atenção"
    assert readiness["document_chunk_processing"]["pendencias"] == 1
    assert readiness["structured_coverage"]["status_prontidao"] == "atenção"
    manual_artifacts = {
        row["artifact"]: row
        for row in index["artifact_index"]
        if row["group"] == "manual_review"
    }
    assert manual_artifacts["monthly_delta_actions"]["module_id"] == "monthly_delta"
    assert manual_artifacts["monthly_delta_action_audit"]["exists"] is True
    assert manual_artifacts["document_chunk_actions"]["module_id"] == "documents"
    assert manual_artifacts["document_chunk_action_audit"]["exists"] is True
    assert manual_artifacts["snapshot_gap_actions"]["required"] is False
    assert manual_artifacts["snapshot_gap_actions"]["exists"] is True
    assert manual_artifacts["snapshot_gap_action_audit"]["exists"] is True
