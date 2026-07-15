from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from services.fund_return_matrix import (
    RETURN_SERIES_COLUMN,
    RETURN_TRAILING_12M_COLUMN,
    RETURN_YTD_COLUMN,
    build_fund_return_matrix,
    format_fund_return_matrix,
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
