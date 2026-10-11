from __future__ import annotations

import pandas as pd

from tabs.tab_fidc_ime import _stacked_history_bar_chart


def _frame(months: int = 5) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "competencia": month.strftime("%m/%Y"), "competencia_dt": month,
            "serie": series, "ordem": order, "valor": value,
        }
        for month in pd.date_range("2026-01-01", periods=months, freq="MS")
        for order, (series, value) in enumerate(
            (("Sênior", 12_000_000_000.0), ("Mezzanino", 400_000_000.0), ("Subordinada", 100_000_000.0)), 1,
        )
    ])


def _spec(frame: pd.DataFrame, *, responsive: bool, total_labels: bool = True) -> dict:
    return _stacked_history_bar_chart(
        frame, title=None, y_title="R$", value_column="valor", bar_size=50,
        show_total_labels=total_labels, allow_outside_labels=not responsive,
        responsive_labels=responsive,
    ).to_dict(validate=True)


def _bar_data(spec: dict) -> list[dict]:
    bar = spec["layer"][0]
    return spec["datasets"][bar["data"]["name"]]


def test_responsive_labels_preserve_bar_values_series_colors_and_totals() -> None:
    frame = _frame()
    original = frame.copy(deep=True)
    desktop = _spec(frame, responsive=False)
    pilot = _spec(frame, responsive=True)
    assert _bar_data(desktop) == _bar_data(pilot)
    assert desktop["layer"][0]["encoding"] == pilot["layer"][0]["encoding"]
    assert desktop["padding"]["right"] == 180
    assert pilot["padding"]["right"] == 18
    assert pilot["layer"][0]["mark"]["size"] == {"expr": "min(50, bandwidth('x') * 0.8)"}
    assert pilot["layer"][1]["mark"]["opacity"] == {"expr": "width >= 520 ? 1 : 0"}
    assert 'datum.competencia === "mai-26"' in pilot["layer"][-1]["mark"]["opacity"]["expr"]
    old_totals = desktop["datasets"][desktop["layer"][-1]["data"]["name"]]
    new_totals = pilot["datasets"][pilot["layer"][-1]["data"]["name"]]
    assert [{k: v for k, v in row.items() if k != "_total_has_value"} for row in new_totals] == old_totals
    pd.testing.assert_frame_equal(frame, original)


def test_zero_and_missing_bar_values_remain_distinct() -> None:
    frame = _frame()
    frame.loc[frame["competencia"].eq("04/2026"), "valor"] = 0.0
    frame.loc[frame["competencia"].eq("05/2026"), "valor"] = float("nan")
    desktop = _spec(frame, responsive=False)
    pilot = _spec(frame, responsive=True)
    assert _bar_data(desktop) == _bar_data(pilot)
    bars = _bar_data(pilot)
    assert {row["valor"] for row in bars if row["competencia"] == "abr-26"} == {0.0}
    assert {row["valor"] for row in bars if row["competencia"] == "mai-26"} == {None}
    totals = pilot["datasets"][pilot["layer"][-1]["data"]["name"]]
    assert next(row for row in totals if row["competencia"] == "abr-26")["_total_has_value"] is True
    assert next(row for row in totals if row["competencia"] == "mai-26")["_total_has_value"] is False


def test_dense_window_keeps_desktop_totals_hidden_and_mobile_latest_visible() -> None:
    spec = _spec(_frame(months=13), responsive=True, total_labels=False)
    expression = spec["layer"][-1]["mark"]["opacity"]["expr"]
    assert 'width < 520 && datum.competencia === "jan-27"' in expression
    assert "width >= 520" not in expression


def test_percent_chart_schema_and_tooltip_values_are_unchanged() -> None:
    frame = _frame()
    frame["percentual"] = frame["valor"] / frame.groupby("competencia")["valor"].transform("sum") * 100.0
    specs = []
    for responsive in (False, True):
        specs.append(_stacked_history_bar_chart(
            frame, title=None, y_title="% do total", value_column="percentual", bar_size=50,
            round_percent_labels=True, allow_outside_labels=not responsive,
            responsive_labels=responsive,
        ).to_dict(validate=True))
    assert _bar_data(specs[0]) == _bar_data(specs[1])
    assert specs[0]["layer"][0]["encoding"] == specs[1]["layer"][0]["encoding"]
