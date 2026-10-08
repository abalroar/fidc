from __future__ import annotations

import pandas as pd
import pytest

from scripts.build_fidc_revision_artifact_payload import (
    _executive_conclusions,
    _holder_distribution,
    _holder_vehicle_perimeter,
    _offer_ticket_concentration_2026,
)


def conclusions(**overrides):
    arguments = {
        "latest": "2026-08",
        "conclusion_metrics": {
            "holder_ge_200m_share_fundos_ate_10_contas": 0.873,
            "admin_custodia_juntas_share_pl": 0.914,
        },
        "offer_concentration": {
            "period_label": "jan–jun/26",
            "large_offer_registered_volume_share": 0.422,
        },
        "closed_annual": [],
        "closed_jan_june": [],
        "provider_concentration_history": [],
        "provider_historical_ranking": pd.DataFrame(),
        "qi_legacy_attribution": pd.DataFrame(),
        "reag_admin_summary": pd.DataFrame(),
        "stock_snapshot": {"pl_ex_fic": 851_361_559_284.45},
        "receivables_snapshot": [{"segmento": "Financeiro", "share_reported": 0.443}],
    }
    arguments.update(overrides)
    return _executive_conclusions(**arguments)


def test_holder_cohort_excludes_audited_fics_and_aggregates_classes_to_legal_fund():
    vehicles = pd.DataFrame([
        {"competencia": "2026-08", "cnpj": "11", "cnpj_fundo": "1", "pl": 200e6, "cotistas": 3, "is_fic_fidc": False},
        {"competencia": "2026-08", "cnpj": "12", "cnpj_fundo": "1", "pl": 100e6, "cotistas": 2, "is_fic_fidc": False},
        {"competencia": "2026-08", "cnpj": "2", "cnpj_fundo": "2", "pl": 500e6, "cotistas": 100, "is_fic_fidc": False},
    ])
    funds = pd.DataFrame([
        {"competencia": "2026-08", "cnpj_fundo": "1", "is_fic": False},
        {"competencia": "2026-08", "cnpj_fundo": "2", "is_fic": True},
    ])
    scoped = _holder_vehicle_perimeter(vehicles, funds, ["2026-08"])
    distribution = _holder_distribution(scoped, "2026-08")
    assert distribution["fundos"].sum() == 1
    assert distribution["pl"].sum() == 300e6
    assert distribution.loc[distribution["bucket"].eq("4–10"), "fundos"].iloc[0] == 1
    assert not vehicles["is_fic_fidc"].any()
    with pytest.raises(ValueError, match="sem perímetro FIC auditado"):
        _holder_vehicle_perimeter(vehicles, funds.iloc[:1], ["2026-08"])


def test_conclusions_round_display_values_and_keep_the_correct_cuts():
    rows, notes = conclusions()
    assert [row["order"] for row in rows] == list(range(1, 6))
    assert all(len(row["bullets"]) == 1 for row in rows)
    texts = [row["bullets"][0] for row in rows]
    assert "R$ 850 bi" in texts[0] and "ago/26" in texts[0]
    assert "45%" in texts[1] and "Tabela II" in texts[1]
    assert "85%" in texts[2] and "R$ 200 mi" in texts[2]
    assert "90%" in texts[3] and "PL ex-FIC" in texts[3]
    assert "40%" in texts[4] and "jan–jun/26" in texts[4]
    assert all(len(text) < 170 for text in texts)
    assert any("soma dos segmentos" in note for note in notes)
    assert any("mais de uma conta" in note for note in notes)
    assert any("R$ 500 mi" in note for note in notes)


def test_missing_data_remains_unavailable_instead_of_zero():
    rows, _ = conclusions(
        stock_snapshot={}, receivables_snapshot=[],
        conclusion_metrics={}, offer_concentration={"period_label": "1S26"},
    )
    texts = [row["bullets"][0] for row in rows]
    assert all("indisponível" in text for text in texts)
    assert all("0%" not in text and "R$ 0" not in text for text in texts)


def test_holder_message_preserves_a_majority_across_the_rounding_boundary():
    for share in (0.57472826, 0.57551):
        rows, notes = conclusions(conclusion_metrics={
            "holder_ge_200m_share_fundos_ate_10_contas": share,
        })
        text = rows[2]["bullets"][0]
        assert "Mais da metade" in text and "dez contas" in text
        assert "%" not in text
        assert any("R$ 200 mi" in note for note in notes)
    rows, _ = conclusions(conclusion_metrics={
        "holder_ge_200m_share_fundos_ate_10_contas": 0.5,
    })
    assert "Mais da metade" not in rows[2]["bullets"][0]
    assert "50%" in rows[2]["bullets"][0]


def test_stock_date_changes_without_relabelling_the_offer_cohort():
    rows, _ = conclusions(latest="2026-12")
    assert all("dez/26" in row["bullets"][0] for row in rows[:4])
    assert "jan–jun/26" in rows[4]["bullets"][0]


def test_invalid_shares_do_not_create_a_conclusion_above_one_hundred_percent():
    rows, _ = conclusions(
        receivables_snapshot=[{"segmento": "Financeiro", "share_reported": 1.4}],
        conclusion_metrics={"admin_custodia_juntas_share_pl": -0.1},
    )
    assert "indisponível" in rows[1]["bullets"][0]
    assert "indisponível" in rows[3]["bullets"][0]


def test_offer_concentration_selects_the_explicit_new_cut_and_year():
    cohort = pd.DataFrame([
        {"period_label": "2026 jan-jun", "period_start": "2026-01-01", "period_end": "2026-06-30", "numero_requerimento": "june", "registered_volume_brl": 1e9},
        {"period_label": "2026 jan-ago", "period_start": "2026-01-01", "period_end": "2026-08-31", "numero_requerimento": "aug1", "registered_volume_brl": 500e6},
        {"period_label": "2026 jan-ago", "period_start": "2026-01-01", "period_end": "2026-08-31", "numero_requerimento": "aug2", "registered_volume_brl": 500e6},
        {"period_label": "2027 jan-fev", "period_start": "2027-01-01", "period_end": "2027-02-28", "numero_requerimento": "feb", "registered_volume_brl": 600e6},
    ])
    metric = _offer_ticket_concentration_2026(cohort, period_end="2026-08-31")
    assert metric["universe_closed_offers"] == 2
    assert set(metric["large_offer_requirement_numbers"]) == {"aug1", "aug2"}
    rows, _ = conclusions(offer_concentration={**metric, "large_offer_registered_volume_share": 0.44526})
    assert "45%" in rows[4]["bullets"][0] and "jan–ago/26" in rows[4]["bullets"][0]
    current = _offer_ticket_concentration_2026(cohort)
    assert current["period_end"] == "2027-02-28"
    rows, _ = conclusions(offer_concentration=current)
    assert "jan–fev/27" in rows[4]["bullets"][0]
    with pytest.raises(ValueError, match="ausente"):
        _offer_ticket_concentration_2026(cohort, period_end="2027-03-31")
