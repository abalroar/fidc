from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pandas as pd
import pytest

from services.portfolio_presentation_state import classify_component


def test_absence_does_not_become_valid_zero() -> None:
    state = classify_component(
        pd.DataFrame({"npl": [None, float("nan"), float("inf"), -float("inf")]}),
        ["npl"],
    )

    assert state.status == "absent"
    assert (state.finite_count, state.missing_count, state.row_count) == (0, 4, 4)
    assert state.has_gaps


def test_complete_zero_series_remains_valid_zero() -> None:
    state = classify_component(pd.DataFrame({"npl": [0.0, -0.0, 0]}), ["npl"])

    assert state.status == "zero"
    assert (state.finite_count, state.missing_count) == (3, 0)
    assert not state.has_gaps


def test_zero_with_gaps_reports_partial_coverage() -> None:
    frame = pd.DataFrame({"npl": pd.Series([0, pd.NA, 0], dtype="Float64")})
    state = classify_component(frame, ["npl"])

    assert state.status == "zero"
    assert (state.finite_count, state.missing_count) == (2, 1)
    assert state.has_gaps


@pytest.mark.parametrize("value", [1e-15, 5e-324, -0.01, Decimal("1e-1000")])
def test_every_nonzero_observation_is_retained(value: object) -> None:
    state = classify_component(pd.DataFrame({"npl": [0, value]}), ["npl"])

    assert state.status == "observed"
    assert (state.finite_count, state.missing_count) == (2, 0)
    assert not state.has_gaps


def test_missing_requested_column_counts_as_gap_for_each_row() -> None:
    state = classify_component(pd.DataFrame({"pl": [1, 2]}), ["npl"])

    assert state.status == "absent"
    assert state.columns == ("npl",)
    assert (state.finite_count, state.missing_count, state.row_count) == (0, 2, 2)
    assert state.has_gaps


def test_multiple_series_preserve_nonzero_and_missing_observations() -> None:
    state = classify_component(
        pd.DataFrame({"npl": [0, 0], "pdd": [0, 1e-12]}),
        ["npl", "pdd", "missing"],
    )

    assert state.status == "observed"
    assert state.columns == ("npl", "pdd", "missing")
    assert (state.finite_count, state.missing_count, state.row_count) == (4, 2, 2)
    assert state.has_gaps


@pytest.mark.parametrize("frame", [None, pd.DataFrame(columns=["npl"])])
def test_empty_input_has_no_observations_or_coverage_claim(frame: pd.DataFrame | None) -> None:
    state = classify_component(frame, ["npl"])

    assert state.status == "absent"
    assert (state.finite_count, state.missing_count, state.row_count) == (0, 0, 0)
    assert not state.has_gaps


def test_classification_does_not_mutate_values_index_or_nullable_dtypes() -> None:
    frame = pd.DataFrame(
        {
            "npl": pd.Series([0, pd.NA, 1e-15], dtype="Float64"),
            "name": ["Fundo A", "Fundo B", "Fundo C"],
        }
    )
    frame.index = pd.Index([10, 20, 30], name="observation")
    before = frame.copy(deep=True)

    state = classify_component(frame, ["npl"])

    pd.testing.assert_frame_equal(frame, before)
    assert state.status == "observed"
    assert state.has_gaps
    with pytest.raises(FrozenInstanceError):
        state.status = "zero"  # type: ignore[misc]


def test_nonnumeric_values_are_missing_without_parsing_or_filling() -> None:
    state = classify_component(
        pd.DataFrame({"npl": ["0", "N/D", pd.NA, Decimal("NaN"), 0]}), "npl"
    )

    assert state.status == "zero"
    assert (state.finite_count, state.missing_count) == (1, 4)
    assert state.has_gaps


def test_duplicate_column_requests_do_not_inflate_coverage_counts() -> None:
    state = classify_component(pd.DataFrame({"npl": [0, None]}), ["npl", "npl"])

    assert state.columns == ("npl",)
    assert (state.finite_count, state.missing_count) == (1, 1)
