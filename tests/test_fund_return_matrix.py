from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from services.fidc_model.b3_cdi import B3CdiMonthlyRate
from services.fund_return_matrix import (
    RETURN_ISSUANCE_SPREAD_COLUMN,
    RETURN_SERIES_COLUMN,
    RETURN_TRAILING_12M_CDI_COLUMN,
    RETURN_TRAILING_12M_COLUMN,
    RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN,
    RETURN_TRAILING_12M_SPREAD_GAP_COLUMN,
    RETURN_YTD_CDI_COLUMN,
    RETURN_YTD_COLUMN,
    RETURN_YTD_IMPLIED_SPREAD_COLUMN,
    RETURN_YTD_SPREAD_GAP_COLUMN,
    build_fund_return_matrix,
    format_fund_return_matrix,
)


def _monthly_cdi_rate(
    month: str,
    *,
    rate: float = 0.01,
    complete: bool = True,
) -> B3CdiMonthlyRate:
    month_start = pd.Timestamp(f"{month}-01")
    month_end = month_start + pd.offsets.MonthEnd(1)
    return B3CdiMonthlyRate(
        mes=month,
        cdi_mensal=rate,
        dias_uteis=20 if complete else 19,
        data_inicio=month_start.date(),
        data_fim=month_end.date(),
        source="fixture",
        expected_dias_uteis=20,
        missing_dates=() if complete else (month_end.date(),),
    )


def test_build_fund_return_matrix_has_continuous_12_months_and_numeric_accumulated_returns() -> None:
    competencias = pd.date_range("2025-07-01", "2026-06-01", freq="MS")
    history = pd.DataFrame(
        {
            "competencia": [value.strftime("%m/%Y") for value in competencias],
            "competencia_dt": competencias,
            "class_kind": ["senior"] * len(competencias),
            "class_key": ["senior:2"] * len(competencias),
            "class_label": ["Sênior · Série 2"] * len(competencias),
            "retorno_mensal_pct": [float(index) for index in range(1, 13)],
        }
    )
    summary = pd.DataFrame(
        {
            "class_kind": ["senior", "senior", "subordinada"],
            "class_key": ["senior:10", "senior:2", "sub:1"],
            "class_label": ["Sênior · Série 10", "Sênior · Série 2", "Subordinada"],
            "latest_competencia": ["06/2026"] * 3,
            "retorno_12m_pct": [10.5, 20.5, 30.5],
            "retorno_ano_pct": [4.5, 5.5, 6.5],
        }
    )
    outputs = SimpleNamespace(
        fund_return_history={"fund": history},
        fund_return_summary={"fund": summary},
    )

    matrix = build_fund_return_matrix(outputs, "fund")

    assert matrix.columns.tolist() == [
        RETURN_SERIES_COLUMN,
        "jul/25",
        "ago/25",
        "set/25",
        "out/25",
        "nov/25",
        "dez/25",
        "jan/26",
        "fev/26",
        "mar/26",
        "abr/26",
        "mai/26",
        "jun/26",
        RETURN_TRAILING_12M_COLUMN,
        RETURN_YTD_COLUMN,
    ]
    assert matrix[RETURN_SERIES_COLUMN].tolist() == [
        "Sênior · Série 2",
        "Sênior · Série 10",
        "Subordinada",
    ]
    senior_2 = matrix.iloc[0]
    assert senior_2["jul/25"] == 1.0
    assert senior_2["jun/26"] == 12.0
    assert senior_2[RETURN_TRAILING_12M_COLUMN] == 20.5
    assert senior_2[RETURN_YTD_COLUMN] == 5.5
    assert matrix.iloc[1]["jul/25"] != matrix.iloc[1]["jul/25"]
    assert matrix.iloc[2][RETURN_TRAILING_12M_COLUMN] == 30.5


def test_build_fund_return_matrix_uses_class_key_even_when_labels_match() -> None:
    history = pd.DataFrame(
        {
            "competencia": ["06/2026", "06/2026"],
            "class_kind": ["subordinada", "subordinada"],
            "class_key": ["sub:1", "sub:2"],
            "class_label": ["Mezanino", "Mezanino"],
            "retorno_mensal_pct": [1.0, 2.0],
        }
    )
    summary = pd.DataFrame(
        {
            "class_kind": ["subordinada", "subordinada"],
            "class_key": ["sub:1", "sub:2"],
            "class_label": ["Mezanino", "Mezanino"],
            "latest_competencia": ["06/2026", "06/2026"],
            "retorno_12m_pct": [3.0, 4.0],
            "retorno_ano_pct": [5.0, 6.0],
        }
    )
    outputs = SimpleNamespace(
        fund_return_history={"fund": history},
        fund_return_summary={"fund": summary},
    )

    matrix = build_fund_return_matrix(outputs, "fund")

    assert len(matrix) == 2
    assert matrix[RETURN_SERIES_COLUMN].tolist() == ["Mezanino", "Mezanino"]
    assert matrix["jun/26"].tolist() == [1.0, 2.0]


def test_build_fund_return_matrix_falls_back_to_history_for_latest_month() -> None:
    history = pd.DataFrame(
        {
            "competencia": ["04/2026"],
            "class_kind": ["senior"],
            "class_key": ["senior:1"],
            "class_label": ["Sênior"],
            "retorno_mensal_pct": [1.25],
        }
    )
    outputs = SimpleNamespace(
        fund_return_history={"fund": history},
        fund_return_summary={"fund": pd.DataFrame()},
    )

    matrix = build_fund_return_matrix(outputs, "fund", months=2)

    assert matrix.columns.tolist() == [
        RETURN_SERIES_COLUMN,
        "mar/26",
        "abr/26",
        RETURN_TRAILING_12M_COLUMN,
        RETURN_YTD_COLUMN,
    ]
    assert matrix.iloc[0]["abr/26"] == 1.25
    assert pd.isna(matrix.iloc[0][RETURN_TRAILING_12M_COLUMN])


def test_format_fund_return_matrix_uses_pt_br_two_decimals_and_preserves_source() -> None:
    source = pd.DataFrame(
        {
            RETURN_SERIES_COLUMN: ["Série A", "Série B"],
            "mai/26": [0.0, -1.234],
            "jun/26": [1234.5, float("nan")],
            RETURN_TRAILING_12M_COLUMN: [10.0, None],
            RETURN_YTD_COLUMN: [5.678, -0.0],
        }
    )

    formatted = format_fund_return_matrix(source)

    assert formatted.iloc[0].to_dict() == {
        RETURN_SERIES_COLUMN: "Série A",
        "mai/26": "0,00%",
        "jun/26": "1.234,50%",
        RETURN_TRAILING_12M_COLUMN: "10,00%",
        RETURN_YTD_COLUMN: "5,68%",
    }
    assert formatted.iloc[1]["mai/26"] == "-1,23%"
    assert formatted.iloc[1]["jun/26"] == "N/D"
    assert formatted.iloc[1][RETURN_YTD_COLUMN] == "0,00%"
    assert source.iloc[0]["mai/26"] == 0.0


def test_build_fund_return_matrix_handles_empty_maps_and_rejects_invalid_months() -> None:
    outputs = SimpleNamespace(fund_return_history={}, fund_return_summary={})

    empty = build_fund_return_matrix(outputs, "missing")

    assert empty.empty
    assert empty.columns.tolist() == [
        RETURN_SERIES_COLUMN,
        RETURN_TRAILING_12M_COLUMN,
        RETURN_YTD_COLUMN,
    ]
    with pytest.raises(ValueError):
        build_fund_return_matrix(outputs, "missing", months=0)


def test_build_fund_return_matrix_compounds_cdi_for_each_series_used_competencias() -> None:
    full_trailing = pd.date_range("2025-07-01", "2026-06-01", freq="MS")
    full_ytd = pd.date_range("2026-01-01", "2026-06-01", freq="MS")
    new_series_window = pd.date_range("2026-03-01", "2026-06-01", freq="MS")
    summary = pd.DataFrame(
        {
            "class_kind": ["senior", "senior"],
            "class_key": ["senior:1", "senior:2"],
            "class_label": ["Sênior · Série 1", "Sênior · Série 2"],
            "latest_competencia": ["06/2026", "06/2026"],
            "retorno_12m_pct": [15.0, 5.0],
            "retorno_ano_pct": [7.0, 5.0],
            "trailing_12m_status": ["completo", "completo"],
            "ytd_status": ["completo", "completo"],
            "trailing_12m_competencias_utilizadas": [
                ", ".join(value.strftime("%m/%Y") for value in full_trailing),
                ", ".join(value.strftime("%m/%Y") for value in new_series_window),
            ],
            "ytd_competencias_utilizadas": [
                ", ".join(value.strftime("%m/%Y") for value in full_ytd),
                ", ".join(value.strftime("%m/%Y") for value in new_series_window),
            ],
        }
    )
    outputs = SimpleNamespace(
        fund_return_history={"fund": pd.DataFrame()},
        fund_return_summary={"fund": summary},
    )
    monthly_cdi_rates = tuple(
        _monthly_cdi_rate(value.strftime("%Y-%m"))
        for value in full_trailing
    )

    matrix = build_fund_return_matrix(
        outputs,
        "fund",
        monthly_cdi_rates=monthly_cdi_rates,
    )

    assert matrix.columns.tolist()[-6:] == [
        RETURN_TRAILING_12M_COLUMN,
        RETURN_TRAILING_12M_CDI_COLUMN,
        RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN,
        RETURN_YTD_COLUMN,
        RETURN_YTD_CDI_COLUMN,
        RETURN_YTD_IMPLIED_SPREAD_COLUMN,
    ]
    full_series = matrix[matrix[RETURN_SERIES_COLUMN] == "Sênior · Série 1"].iloc[0]
    new_series = matrix[matrix[RETURN_SERIES_COLUMN] == "Sênior · Série 2"].iloc[0]
    assert full_series[RETURN_TRAILING_12M_CDI_COLUMN] == pytest.approx(((1.01**12) - 1.0) * 100.0)
    assert full_series[RETURN_YTD_CDI_COLUMN] == pytest.approx(((1.01**6) - 1.0) * 100.0)
    assert new_series[RETURN_TRAILING_12M_CDI_COLUMN] == pytest.approx(((1.01**4) - 1.0) * 100.0)
    assert new_series[RETURN_YTD_CDI_COLUMN] == pytest.approx(((1.01**4) - 1.0) * 100.0)
    assert full_series[RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN] == pytest.approx(
        (((1.15 / (1.01**12)) ** (252 / 240)) - 1.0) * 100.0
    )
    assert full_series[RETURN_YTD_IMPLIED_SPREAD_COLUMN] == pytest.approx(
        (((1.07 / (1.01**6)) ** (252 / 120)) - 1.0) * 100.0
    )
    assert new_series[RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN] == pytest.approx(
        (((1.05 / (1.01**4)) ** (252 / 80)) - 1.0) * 100.0
    )
    assert matrix.attrs["cdi_source"] == "B3/Cetip MediaCDI diário composto por mês"
    assert matrix.attrs["cdi_missing_competencias"] == ()


@pytest.mark.parametrize(
    ("monthly_cdi_rates", "expected_missing"),
    [
        pytest.param((), ("01/2026", "02/2026"), id="no-rates"),
        pytest.param(
            (
                _monthly_cdi_rate("2026-01"),
                _monthly_cdi_rate("2026-02", complete=False),
            ),
            ("02/2026",),
            id="incomplete-month",
        ),
    ],
)
def test_build_fund_return_matrix_marks_missing_or_incomplete_cdi_as_nd(
    monthly_cdi_rates: tuple[B3CdiMonthlyRate, ...],
    expected_missing: tuple[str, ...],
) -> None:
    summary = pd.DataFrame(
        {
            "class_kind": ["senior"],
            "class_key": ["senior:1"],
            "class_label": ["Sênior"],
            "latest_competencia": ["02/2026"],
            "retorno_12m_pct": [2.0],
            "retorno_ano_pct": [2.0],
            "trailing_12m_status": ["completo"],
            "ytd_status": ["completo"],
            "trailing_12m_competencias_utilizadas": ["01/2026, 02/2026"],
            "ytd_competencias_utilizadas": ["01/2026, 02/2026"],
        }
    )
    outputs = SimpleNamespace(
        fund_return_history={"fund": pd.DataFrame()},
        fund_return_summary={"fund": summary},
    )

    matrix = build_fund_return_matrix(
        outputs,
        "fund",
        months=2,
        monthly_cdi_rates=monthly_cdi_rates,
    )
    formatted = format_fund_return_matrix(matrix)

    assert pd.isna(matrix.iloc[0][RETURN_TRAILING_12M_CDI_COLUMN])
    assert pd.isna(matrix.iloc[0][RETURN_YTD_CDI_COLUMN])
    assert pd.isna(matrix.iloc[0][RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN])
    assert pd.isna(matrix.iloc[0][RETURN_YTD_IMPLIED_SPREAD_COLUMN])
    assert formatted.iloc[0][RETURN_TRAILING_12M_CDI_COLUMN] == "N/D"
    assert formatted.iloc[0][RETURN_YTD_CDI_COLUMN] == "N/D"
    assert formatted.iloc[0][RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN] == "N/D"
    assert formatted.iloc[0][RETURN_YTD_IMPLIED_SPREAD_COLUMN] == "N/D"
    assert matrix.attrs["cdi_missing_competencias"] == expected_missing
    assert formatted.attrs["cdi_missing_competencias"] == expected_missing


def test_build_fund_return_matrix_compares_implied_spread_with_issuance_benchmark() -> None:
    summary = pd.DataFrame(
        {
            "class_kind": ["senior", "senior"],
            "class_key": ["senior:1", "senior:2"],
            "class_label": ["Sênior · Série 1", "Sênior · Série 2"],
            "latest_competencia": ["02/2026", "02/2026"],
            "retorno_12m_pct": [3.0604, 1.0],
            "retorno_ano_pct": [3.0604, 1.0],
            "trailing_12m_status": ["completo", "completo"],
            "ytd_status": ["completo", "completo"],
            "trailing_12m_competencias_utilizadas": ["01/2026, 02/2026"] * 2,
            "ytd_competencias_utilizadas": ["01/2026, 02/2026"] * 2,
        }
    )
    outputs = SimpleNamespace(
        fund_return_history={"fund": pd.DataFrame()},
        fund_return_summary={"fund": summary},
    )
    rates = (_monthly_cdi_rate("2026-01"), _monthly_cdi_rate("2026-02"))

    matrix = build_fund_return_matrix(
        outputs,
        "fund",
        months=2,
        monthly_cdi_rates=rates,
        benchmark_spreads={"senior:1": 0.05},
    )
    formatted = format_fund_return_matrix(matrix)
    first = matrix.iloc[0]
    second = matrix.iloc[1]
    expected_implied = (((1.030604 / (1.01**2)) ** (252 / 40)) - 1.0) * 100.0

    assert first[RETURN_ISSUANCE_SPREAD_COLUMN] == pytest.approx(5.0)
    assert first[RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN] == pytest.approx(expected_implied)
    assert first[RETURN_YTD_IMPLIED_SPREAD_COLUMN] == pytest.approx(expected_implied)
    assert first[RETURN_TRAILING_12M_SPREAD_GAP_COLUMN] == pytest.approx(
        (expected_implied - 5.0) * 100.0
    )
    assert first[RETURN_YTD_SPREAD_GAP_COLUMN] == pytest.approx((expected_implied - 5.0) * 100.0)
    assert formatted.iloc[0][RETURN_ISSUANCE_SPREAD_COLUMN] == "5,00%"
    assert formatted.iloc[0][RETURN_TRAILING_12M_SPREAD_GAP_COLUMN].startswith("+")
    assert pd.isna(second[RETURN_ISSUANCE_SPREAD_COLUMN])
    assert pd.isna(second[RETURN_TRAILING_12M_SPREAD_GAP_COLUMN])
    assert formatted.iloc[1][RETURN_ISSUANCE_SPREAD_COLUMN] == "N/D"
    assert formatted.iloc[1][RETURN_YTD_SPREAD_GAP_COLUMN] == "N/D"


def test_implied_spread_can_be_negative_and_rejects_return_at_or_below_minus_one_hundred_percent() -> None:
    summary = pd.DataFrame(
        {
            "class_kind": ["senior", "senior"],
            "class_key": ["senior:1", "senior:2"],
            "class_label": ["A", "B"],
            "latest_competencia": ["01/2026", "01/2026"],
            "retorno_12m_pct": [0.0, -100.0],
            "retorno_ano_pct": [0.0, -101.0],
            "trailing_12m_status": ["completo", "completo"],
            "ytd_status": ["completo", "completo"],
            "trailing_12m_competencias_utilizadas": ["01/2026", "01/2026"],
            "ytd_competencias_utilizadas": ["01/2026", "01/2026"],
        }
    )
    outputs = SimpleNamespace(
        fund_return_history={"fund": pd.DataFrame()},
        fund_return_summary={"fund": summary},
    )

    matrix = build_fund_return_matrix(
        outputs,
        "fund",
        months=1,
        monthly_cdi_rates=(_monthly_cdi_rate("2026-01"),),
    )

    assert matrix.iloc[0][RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN] < 0.0
    assert matrix.iloc[0][RETURN_YTD_IMPLIED_SPREAD_COLUMN] < 0.0
    assert pd.isna(matrix.iloc[1][RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN])
    assert pd.isna(matrix.iloc[1][RETURN_YTD_IMPLIED_SPREAD_COLUMN])
