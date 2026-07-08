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
    assign_document_chunks,
    build_criteria_pipeline_manifest,
    build_criteria_structured,
    build_dimension_catalog_pipeline_manifest,
    build_dimension_monthly_pipeline_manifest,
    build_document_inventory,
    build_document_pipeline_manifest,
    build_industry_dimension_catalog,
    build_industry_dimension_monthly,
    build_industry_fund_snapshot,
    build_industry_market_share,
    build_industry_pipeline_index,
    build_issuance_annual,
    build_issuance_pipeline_manifest,
    build_issuance_sector_year,
    build_issuance_tranches,
    build_market_share_pipeline_manifest,
    build_cedente_structured,
    build_cedente_pipeline_manifest,
    cedente_quality_summary,
    criteria_quality_summary,
    document_quality_summary,
    fund_snapshot_quality_summary,
    industry_dimension_catalog_quality_summary,
    industry_dimension_monthly_quality_summary,
    industry_market_share_quality_summary,
    load_cedente_structured,
    normalize_cnpj,
    save_pipeline_manifest,
    save_cedente_structured,
    scan_regulatory_extraction_files,
)
from tabs.tab_industry_study import (  # noqa: E402
    _build_fund_dossier_tables,
    _build_snapshot_market_share,
    _heatmap_base_frame,
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
    assert round(float(cedente_rows.loc["CEDENTE ABC S.A.", "value_weight"]), 6) == 0.5
    assert cedente_rows.loc["CEDENTE ABC S.A.", "source_document"] == "regulamento.pdf"
    assert cedente_rows.loc["CEDENTE ABC S.A.", "source_page"] == "12"
    assert quality["dimensions"] >= 8
    assert quality["with_source_document"] >= 2
    assert manifest["schema_version"] == "industry-dimension-catalog-manifest/v1"
    assert manifest["quality"]["rows"] == len(catalog)


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
    assert index["quality_rollup"]["modules_total"] == 9
    assert index["quality_rollup"]["module_status_counts"]["ok"] == 9
    assert index["quality_rollup"]["competencia_snapshot"] == "202605"
    assert index["quality_rollup"]["document_chunks"] == 1
    assert index["quality_rollup"]["subordination_median_pct"] == 10.0
    assert index["quality_rollup"]["fund_snapshot_rows"] == 2
    assert index["quality_rollup"]["dimension_catalog_rows"] == 80
    assert index["quality_rollup"]["dimension_catalog_dimensions"] == 10
    assert index["quality_rollup"]["dimension_monthly_rows"] == 120
    assert index["quality_rollup"]["dimension_monthly_latest_competencia"] == "202605"
    assert index["quality_rollup"]["market_share_rows"] == 30
    assert index["quality_rollup"]["market_share_dimensions"] == 5
    assert {stage["module_id"] for stage in index["refresh_plan"]} >= {
        "base_monthly",
        "fund_snapshot",
        "dimension_catalog",
        "dimension_monthly",
        "market_share",
        "pipeline_index",
    }
    assert any(row["artifact"] == "manifest" for row in index["artifact_index"])
