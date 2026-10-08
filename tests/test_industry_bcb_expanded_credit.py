from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services import industry_bcb_expanded_credit as bcb
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


def _frames_for_months(months: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    """Declared mocks preserve the BCB identities; source values are not inferred."""
    return {
        name: pd.DataFrame(
            {"competencia": months, "value_brl": frame["value_brl"].iloc[-1]}
        )
        for name, frame in _frames().items()
    }


def _monthly_for_months(months: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame({"competencia": months, "carteira_dc": 80.0})


def test_august_cut_preserves_values_schema_and_labels() -> None:
    months = ("2025-12", "2026-08")
    result = build_expanded_credit_history(
        _monthly_for_months(months),
        series_frames=_frames_for_months(months),
        latest_complete="2026-08",
    )
    assert result["competencia"].tolist() == list(months)
    assert result["period_label"].tolist() == ["2025", "08/26"]
    assert result["is_latest"].tolist() == [False, True]
    assert result["private_expanded_credit_total_brl"].tolist() == [890.0, 890.0]
    assert result["fidc_receivables_brl"].tolist() == [80.0, 80.0]
    assert result["other_securitization_brl"].tolist() == [30.0, 30.0]
    assert tuple(result.columns) == bcb.OUTPUT_COLUMNS


def test_rollover_selects_current_month_and_previous_decembers() -> None:
    months = ("2025-12", "2026-08", "2026-12", "2027-02", "2027-03")
    result = build_expanded_credit_history(
        _monthly_for_months(months),
        series_frames=_frames_for_months(months),
        latest_complete="2027-03",
    )
    assert result["competencia"].tolist() == ["2025-12", "2026-12", "2027-03"]
    assert result["period_label"].tolist() == ["2025", "2026", "03/27"]
    assert result["is_latest"].tolist() == [False, False, True]


def test_secondary_lag_keeps_last_common_month_explicit() -> None:
    months = ("2025-12", "2026-12", "2027-02", "2027-03")
    frames = _frames_for_months(months)
    frames["external_debt"] = frames["external_debt"].iloc[:-1].copy()
    result = build_expanded_credit_history(
        _monthly_for_months(months), series_frames=frames, latest_complete="2027-03"
    )
    assert result.iloc[-1]["competencia"] == "2027-02"
    assert result.iloc[-1]["period_label"] == "02/27"
    assert bool(result.iloc[-1]["is_latest"])


def test_later_preliminary_month_does_not_enter_comparison() -> None:
    months = ("2025-12", "2026-12", "2027-03", "2027-04")
    result = build_expanded_credit_history(
        _monthly_for_months(months),
        series_frames=_frames_for_months(months),
        latest_complete="2027-03",
    )
    assert result.iloc[-1]["competencia"] == "2027-03"
    assert not result["competencia"].eq("2027-04").any()


def test_download_end_uses_explicit_consolidated_cut(monkeypatch) -> None:
    months = ("2026-12", "2027-03")
    frames = _frames_for_months(months)
    requested_ends: list[str] = []

    def fetch(code: int, **kwargs) -> pd.DataFrame:
        requested_ends.append(kwargs["end"])
        name = next(name for name, value in BCB_SERIES.items() if value == code)
        return frames[name]

    monkeypatch.setattr(bcb, "_download_series", fetch)
    build_expanded_credit_history(_monthly_for_months(months), latest_complete="2027-03")
    assert requested_ends == ["31/03/2027"] * len(BCB_SERIES)


def test_standalone_download_default_end_uses_current_date(monkeypatch) -> None:
    requested_params: list[dict] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> list[dict[str, str]]:
            return [{"data": "31/08/2026", "valor": "1,23"}]

    def fetch(*args, **kwargs) -> Response:
        requested_params.append(kwargs["params"])
        return Response()

    monkeypatch.setattr(bcb.requests, "get", fetch)
    result = bcb._download_series(28183)
    assert requested_params[0]["dataFinal"] == pd.Timestamp.today().strftime("%d/%m/%Y")
    assert result["value_brl"].iloc[0] == 1_230_000.0


def test_no_common_month_within_cut_fails() -> None:
    months = ("2027-03",)
    with pytest.raises(ExpandedCreditError, match="competência comum"):
        build_expanded_credit_history(
            _monthly_for_months(months),
            series_frames=_frames_for_months(months),
            latest_complete="2026-12",
        )
