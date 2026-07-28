from __future__ import annotations

from datetime import date

from services.portfolio_competence import assess_portfolio_competence


def test_competence_excludes_cancelled_fund_but_keeps_liquidating_fund_eligible() -> None:
    assessment = assess_portfolio_competence(
        {
            "11111111000111": ("FIDC ativo", ["02/2026", "05/2026", "06/2026"]),
            "22222222000122": ("FIDC em liquidação", ["02/2026"]),
            "33333333000133": ("FIDC cancelado", ["09/2024", "10/2024"]),
        },
        reporting_status_by_cnpj={
            "11111111000111": {"situacao": "Em Funcionamento Normal"},
            "22222222000122": {"situacao": "Em Liquidação", "data_inicio_situacao": "2026-03-27"},
            "33333333000133": {"situacao": "Cancelado", "data_cancelamento": "2024-10-31"},
        },
        as_of=date(2026, 7, 28),
    )

    assert assessment.reference_competence == "02/2026"
    assert assessment.latest_observed_competence == "06/2026"
    assert assessment.eligible_cnpjs == ("11111111000111", "22222222000122")
    assert assessment.excluded_cnpjs == ("33333333000133",)
    assert "FIDC em liquidação" in assessment.note
    assert "prazo regulatório encerrado em 15/07/2026" in assessment.note
    assert "FIDC cancelado" in assessment.note
    latest = assessment.coverage_df.iloc[-1]
    assert latest["fundos_elegiveis"] == 2
    assert latest["fundos_reportantes"] == 1
    assert latest["status"] == "Incompleta"


def test_competence_marks_missing_report_as_pending_during_regulatory_deadline() -> None:
    assessment = assess_portfolio_competence(
        {
            "11111111000111": ("FIDC A", ["05/2026", "06/2026"]),
            "22222222000122": ("FIDC B", ["05/2026"]),
        },
        as_of=date(2026, 7, 10),
    )

    assert assessment.reference_competence == "05/2026"
    assert "prazo regulatório até 15/07/2026" in assessment.note


def test_competence_keeps_cancelled_fund_without_cancellation_date_eligible() -> None:
    assessment = assess_portfolio_competence(
        {
            "11111111000111": ("FIDC A", ["05/2026"]),
            "22222222000122": ("FIDC cancelado sem data", ["04/2026"]),
        },
        reporting_status_by_cnpj={
            "11111111000111": {"situacao": "Em Funcionamento Normal"},
            "22222222000122": {"situacao": "Cancelado"},
        },
        as_of=date(2026, 7, 28),
    )

    assert assessment.reference_competence is None
    assert assessment.eligible_cnpjs == ("11111111000111", "22222222000122")
    assert assessment.excluded_cnpjs == ()


def test_competence_excludes_fund_registered_after_latest_observed_month() -> None:
    assessment = assess_portfolio_competence(
        {
            "11111111000111": ("FIDC A", ["05/2026"]),
            "22222222000122": ("FIDC ainda sem obrigação", []),
        },
        reporting_status_by_cnpj={
            "11111111000111": {"situacao": "Em Funcionamento Normal", "data_registro": "2025-01-10"},
            "22222222000122": {"situacao": "Fase Pré-Operacional", "data_registro": "2026-06-03"},
        },
        as_of=date(2026, 7, 28),
    )

    assert assessment.reference_competence == "05/2026"
    assert assessment.eligible_cnpjs == ("11111111000111",)
    assert assessment.excluded_cnpjs == ("22222222000122",)
    assert "Registro em 03/06/2026 posterior à competência" in assessment.note
