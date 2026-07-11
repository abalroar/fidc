import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_fidc_definitive_market_intelligence import (  # noqa: E402
    build_fidc_type_share_delta,
    clean_document_participant_name,
    cnpj14,
    deduplicate_closing_profiles,
)


def test_cnpj14_restores_leading_zero_from_numeric_csv_representation():
    assert cnpj14("1425787000104") == "01425787000104"
    assert cnpj14("01.425.787/0001-04") == "01425787000104"


def test_document_participant_cleaner_removes_list_marker_without_eating_company_name():
    assert clean_document_participant_name("(ii) Redecard Instituicao de Pagamento S.A") == (
        "Redecard Instituicao de Pagamento S.A"
    )
    assert clean_document_participant_name("CLUBE LEVE ADMINISTRACAO") == (
        "CLUBE LEVE ADMINISTRACAO"
    )


def test_semantic_closing_dedup_keeps_one_observation_and_matching_categories():
    profiles = pd.DataFrame(
        [
            {
                "document_key": "a",
                "cnpj_fundo": "1",
                "document_date": "2025-01-10",
                "parse_status": "parsed_high",
                "total_subscribers": 4,
                "total_quotas": 100,
                "closing_amount_brl": 1000,
                "total_row_validated": True,
            },
            {
                "document_key": "b",
                "cnpj_fundo": "1",
                "document_date": "2025-01-10",
                "parse_status": "parsed_high",
                "total_subscribers": 4,
                "total_quotas": 100,
                "closing_amount_brl": 1000,
                "total_row_validated": True,
            },
        ]
    )
    categories = pd.DataFrame(
        [
            {"document_key": "a", "investor_family": "Fundos", "subscribers": 4},
            {"document_key": "b", "investor_family": "Fundos", "subscribers": 4},
        ]
    )

    deduped, deduped_categories, diagnostics = deduplicate_closing_profiles(
        profiles,
        categories,
        pd.Timestamp("2024-07-01"),
        pd.Timestamp("2026-06-30"),
    )

    assert len(deduped) == 1
    assert len(deduped_categories) == 1
    assert diagnostics["semantic_duplicates_removed"] == 1


def test_fidc_type_delta_is_exhaustive_and_retains_unknown_type():
    vehicle = pd.DataFrame(
        [
            {
                "competencia": "2025-05",
                "cnpj": "1",
                "cnpj_fundo": "1",
                "segmento_principal": "Financeiro",
                "pl": 60.0,
            },
            {
                "competencia": "2025-05",
                "cnpj": "2",
                "cnpj_fundo": "2",
                "segmento_principal": None,
                "pl": 40.0,
            },
            {
                "competencia": "2026-05",
                "cnpj": "1",
                "cnpj_fundo": "1",
                "segmento_principal": "Financeiro",
                "pl": 80.0,
            },
            {
                "competencia": "2026-05",
                "cnpj": "2",
                "cnpj_fundo": "2",
                "segmento_principal": None,
                "pl": 20.0,
            },
        ]
    )

    delta, _, diagnostics = build_fidc_type_share_delta(
        vehicle,
        pd.Period("2026-05", freq="M"),
        pd.Period("2025-05", freq="M"),
    )

    assert round(delta["share_current"].sum(), 12) == 1.0
    assert "Nao classificado" in set(delta["fidc_type"])
    assert diagnostics["classified_pl_share_current"] == 0.8
