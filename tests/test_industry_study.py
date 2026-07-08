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
    build_issuance_annual,
    build_issuance_pipeline_manifest,
    build_issuance_sector_year,
    build_issuance_tranches,
    build_cedente_structured,
    build_cedente_pipeline_manifest,
    cedente_quality_summary,
    load_cedente_structured,
    normalize_cnpj,
    save_pipeline_manifest,
    save_cedente_structured,
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
