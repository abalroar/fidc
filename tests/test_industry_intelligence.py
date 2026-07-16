from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pandas as pd

from scripts.classify_large_fidcs_from_documents import (
    classify_large_fund_precise,
    extract_anbima_labels,
)
from services.industry_intelligence import (
    build_competence_status,
    build_competitive_position,
    build_offer_annual,
)
from services.industry_ppt_export import build_industry_pptx_bytes, build_industry_xlsx_bytes


def test_competence_status_keeps_partial_tail_out_of_consolidated_snapshot() -> None:
    industry = pd.DataFrame(
        {
            "competencia": ["2026-04", "2026-05", "2026-06"],
            "n_veiculos": [4_200, 4_224, 1_990],
            "pl_total": [950e9, 958e9, 337e9],
        }
    )

    status = build_competence_status(industry)

    assert status.iloc[-1]["publication_status"] == "preliminar"
    assert status.iloc[-2]["publication_status"] == "completa"
    assert status.iloc[-1]["vehicle_ratio_vs_previous"] < 0.5


def test_offer_annual_separates_total_initial_and_relevant_ticket_scopes() -> None:
    offers = pd.DataFrame(
        {
            "year": [2026, 2026, 2026],
            "period": ["2026YTD"] * 3,
            "offer_id": ["a", "b", "c"],
            "issuer_cnpj": ["1", "1", "2"],
            "registered_volume_brl": [500e6, 200e6, 400e6],
            "valid_offer": [True, True, False],
            "closed_offer": [True, True, False],
            "initial_offer": [True, False, True],
            "ticket_relevant": [True, False, True],
            "investor_data_available": [True, True, False],
            "single_investor": [True, False, False],
            "investor_count": [1, 4, 0],
            "placed_volume_proxy_brl": [500e6, 180e6, 0],
        }
    )

    annual = build_offer_annual(offers).iloc[0]

    assert annual["valid_offers"] == 2
    assert annual["initial_offers"] == 1
    assert annual["relevant_ticket_offers"] == 1
    assert annual["valid_registered_volume_brl"] == 700e6


def test_competitive_position_exposes_structuring_to_servicing_conversion_gap() -> None:
    offers = pd.DataFrame(
        {
            "year": [2026, 2026, 2026],
            "period": ["2026YTD"] * 3,
            "offer_id": ["a", "b", "c"],
            "registered_volume_brl": [600e6, 500e6, 400e6],
            "valid_offer": [True] * 3,
            "ticket_relevant": [True] * 3,
            "leader_group": ["Itaú", "Itaú", "Bradesco"],
            "administrator_group": ["Oliveira Trust", "Itaú", "Bradesco"],
            "manager_group": ["Oliveira Trust", "Tercon", "Bradesco"],
            "custodian_group": ["Oliveira Trust", "Itaú", "Bradesco"],
            "same_platform_admin_manager_custodian": [True, False, True],
            "closed_offer": [True, True, True],
            "investor_data_available": [True, True, True],
            "single_investor": [True, False, False],
            "investor_count": [1, 8, 5],
            "fund_investor_present": [False, True, True],
            "bank_investor_present": [True, True, False],
        }
    )

    row = build_competitive_position(offers).iloc[0]

    assert row["itau_coordinator_rank"] == 1
    assert row["itau_coordinator_volume_brl"] == 1.1e9
    assert row["itau_administrator_volume_brl"] == 500e6
    assert row["itau_coordinator_share"] > row["itau_administrator_share"]


def test_large_fund_classifier_prioritizes_specific_lastro_over_generic_terms() -> None:
    text = (
        "Índice de preços ao consumidor. Os direitos creditórios são oriundos de litígios "
        "contra pessoas jurídicas de direito público e podem estar representados por precatórios."
    )
    result = classify_large_fund_precise("Alternative Assets III", text, "Financeiro")

    assert result["n1"] == "Judicial/Precatórios/NPL"
    assert result["confidence"] == "alta"


def test_anbima_labels_remain_separate_from_economic_classification() -> None:
    text = (
        'O fundo é classificado como FIDC, tipo "Agro, Indústria e Comércio" e '
        'foco de atuação em "Crédito Corporativo", conforme diretriz ANBIMA.'
    )

    anbima_type, focus, evidence = extract_anbima_labels(text)

    assert "AGRO" in anbima_type
    assert "CREDITO CORPORATIVO" in focus
    assert evidence


def test_industry_exports_are_valid_office_files() -> None:
    from openpyxl import load_workbook
    from pptx import Presentation

    pptx = build_industry_pptx_bytes()
    xlsx = build_industry_xlsx_bytes()

    assert len(Presentation(BytesIO(pptx)).slides) == 16
    with ZipFile(BytesIO(pptx)) as archive:
        chart_xml = b"".join(
            archive.read(name)
            for name in archive.namelist()
            if name.startswith("ppt/charts/chart") and name.endswith(".xml")
        )
    assert b'<c:axId val="-' not in chart_xml
    assert b'<c:crossAx val="-' not in chart_xml
    workbook = load_workbook(BytesIO(xlsx), read_only=True)
    assert "Indústria mensal" in workbook.sheetnames
    assert "FIDCs >5bi" in workbook.sheetnames
