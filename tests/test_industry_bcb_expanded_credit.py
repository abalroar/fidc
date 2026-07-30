from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.industry_bcb_expanded_credit import (
    BCB_SERIES,
    ExpandedCreditError,
    build_expanded_credit_history,
    load_materialized_expanded_credit_history,
)


def _frames() -> dict[str, pd.DataFrame]:
    rows = {
        "expanded_credit_total": [1_000.0, 1_100.0],
        "loans": [400.0, 450.0],
        "loans_sfn": [300.0, 340.0],
        "loans_other_finance": [60.0, 65.0],
        "loans_government_funds": [40.0, 45.0],
        "debt_securities": [400.0, 420.0],
        "public_debt": [200.0, 210.0],
        "private_debt": [100.0, 100.0],
        "securitization": [100.0, 110.0],
        "external_debt": [200.0, 230.0],
    }
    return {
        name: pd.DataFrame(
            {
                "competencia": ["2025-12", "2026-05"],
                "value_brl": values,
            }
        )
        for name, values in rows.items()
    }


def test_bcb_stack_closes_and_separates_fidc_receivables() -> None:
    monthly = pd.DataFrame(
        {
            "competencia": ["2025-12", "2026-05"],
            "carteira_dc": [70.0, 80.0],
        }
    )
    result = build_expanded_credit_history(monthly, series_frames=_frames())

    assert result["period_label"].tolist() == ["2025", "05/26"]
    latest = result.iloc[-1]
    assert latest["fidc_receivables_brl"] == 80.0
    assert latest["other_securitization_brl"] == 30.0
    assert latest["expanded_credit_total_brl"] == 1_100.0


def test_bcb_bridge_rejects_fidc_book_above_securitization() -> None:
    monthly = pd.DataFrame(
        {
            "competencia": ["2025-12", "2026-05"],
            "carteira_dc": [70.0, 120.0],
        }
    )
    with pytest.raises(ExpandedCreditError, match="supera securitização"):
        build_expanded_credit_history(monthly, series_frames=_frames())


def test_materialized_bcb_history_has_all_required_series() -> None:
    frame = load_materialized_expanded_credit_history(
        Path("data/industry_study")
    )
    assert set(BCB_SERIES) == {
        "expanded_credit_total",
        "loans",
        "loans_sfn",
        "loans_other_finance",
        "loans_government_funds",
        "debt_securities",
        "public_debt",
        "private_debt",
        "securitization",
        "external_debt",
    }
    # O último ponto acompanha o que BCB e CVM têm em comum e avança quando o
    # BCB publica. Fixar o mês literal quebraria o teste a cada divulgação, sem
    # dizer nada sobre a série; o que importa é que a ponta seja a mais recente
    # e que a identidade do crédito ampliado feche nela.
    latest = frame.iloc[-1]
    assert latest["competencia"] == frame["competencia"].max()
    assert bool(latest["is_latest"])
    assert latest["competencia"] >= "2026-06"
    assert latest["expanded_credit_total_brl"] > 20_000_000_000_000
