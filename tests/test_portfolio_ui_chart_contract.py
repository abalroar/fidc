from __future__ import annotations

import pandas as pd
import pytest

from services import meli_credit_monitor_visuals as visuals
from tabs import tab_fidc_ime as ime


def _monitor(yoy=(None, None, None)) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=3, freq="MS")
    return pd.DataFrame({
        "competencia": dates.strftime("%m/%Y"), "competencia_dt": dates,
        "fund_name": ["FIDC Exemplo"] * 3,
        "carteira_ex360": [100_000_000.0, 0.0, 120_000_000.0],
        "carteira_ex360_yoy_pct": list(yoy),
        "duration_days": [82.0, None, 84.0],
        "duration_months": [2.69, None, 2.76],
        "roll_61_90_m3_pct": [0.0, None, 1.25],
        "roll_91_120_m4_pct": [None] * 3,
        "roll_121_150_m5_pct": [None] * 3,
        "roll_151_180_m6_pct": [None] * 3,
    })


def _rows(spec: dict, layer: dict) -> list[dict]:
    return spec["datasets"][layer.get("data", spec.get("data"))["name"]]


def test_missing_yoy_omits_only_optional_panel_and_keeps_cash_zero_and_months():
    frame = _monitor()
    before = frame.copy(deep=True)
    spec = visuals.portfolio_growth_chart(frame, portfolio_mode=True).to_dict(validate=True)
    assert "vconcat" not in spec
    data = _rows(spec, spec["layer"][0])
    assert [row["carteira_ex360"] for row in data] == [100_000_000.0, 0.0, 120_000_000.0]
    assert [row["competencia_label"] for row in data] == ["jan/26", "fev/26", "mar/26"]
    assert spec["layer"][0]["encoding"]["y"]["title"] == "R$ mm"
    assert len(_rows(spec, spec["layer"][1])) == 1
    pd.testing.assert_frame_equal(frame, before)
    # The caller must opt in; the legacy composition keeps its two panels.
    assert "vconcat" in visuals.portfolio_growth_chart(frame).to_dict(validate=True)


@pytest.mark.parametrize("yoy", [(0.0, None, 0.0), (4.0, None, -2.0)])
def test_yoy_keeps_valid_zero_supplied_rates_and_visual_gap(yoy):
    frame = _monitor(yoy)
    before = frame.copy(deep=True)
    spec = visuals.portfolio_growth_chart(frame, portfolio_mode=True).to_dict(validate=True)
    assert len(spec["vconcat"]) == 2
    line = spec["vconcat"][1]["layer"][0]
    data = _rows(spec, line)
    assert [row["carteira_ex360_yoy_pct"] for row in data] == list(yoy)
    assert [row["_path_segment"] for row in data] == [0, 1, 1]
    assert line["encoding"]["detail"]["field"] == "_path_segment"
    pd.testing.assert_frame_equal(frame, before)


def test_yoy_in_ineligible_universe_does_not_make_a_comparison_valid():
    frame = _monitor((None, 0.0, None))
    frame["universe_complete"] = [True, False, True]
    before = frame.copy(deep=True)
    spec = visuals.portfolio_growth_chart(frame, portfolio_mode=True).to_dict(validate=True)
    assert "vconcat" not in spec
    assert [row["competencia_label"] for row in _rows(spec, spec["layer"][0])] == ["jan/26", "mar/26"]
    pd.testing.assert_frame_equal(frame, before)


def test_maturity_horizontal_preserves_all_a_vencer_values_and_existing_total():
    frame = pd.DataFrame({
        "faixa": ["Vencidos", "Em 30 dias", "31 a 60 dias", "61 a 90 dias", "Acima de 1080 dias"],
        "valor": [5_000.0, 0.0, None, 10_000.0, 100_000_000.0],
        "ordem": [0, 1, 2, 3, 10],
        "source_status": ["reported_value", "reported_zero", "not_reported", "reported_value", "reported_value"],
    })
    before = frame.copy(deep=True)
    view = ime._maturity_horizontal_chart_frame(frame)
    assert view.faixa.tolist() == ["Em 30 dias", "31 a 60 dias", "61 a 90 dias", "Acima de 1080 dias", "Total informado (parcial)"]
    assert view.loc[0, "valor"] == 0.0 and pd.isna(view.loc[1, "valor"])
    assert view.loc[0, "valor_fmt"] == "0,0" and view.loc[1, "valor_fmt"] == "N/D"
    assert view.loc[2, "valor_fmt"] == "0,01" and view.loc[3, "valor_fmt"] == "100,0"
    assert view.iloc[-1].valor == ime._maturity_waterfall_chart_frame(frame).iloc[-1].valor_etapa
    spec = ime._maturity_waterfall_chart(frame, title=None, portfolio_mode=True).to_dict(validate=True)
    bar = spec["layer"][0]
    assert bar["encoding"]["x"]["title"] == "R$ mm"
    assert bar["encoding"]["y"]["field"] == "faixa"
    assert "y2" not in bar["encoding"] and bar["encoding"]["color"]["legend"] is None
    assert len(_rows(spec, bar)) == 5
    pd.testing.assert_frame_equal(frame, before)


def test_maturity_all_missing_total_is_missing_and_small_positive_is_not_zero():
    absent = pd.DataFrame({"faixa": ["Em 30 dias", "31 a 60 dias"], "valor": [None, None]})
    result = ime._maturity_horizontal_chart_frame(absent)
    assert result.valor.isna().all() and result.valor_fmt.eq("N/D").all()
    assert ime._portfolio_millions_label(0.0) == "0,0"
    assert ime._portfolio_millions_label(100.0) == "<0,01"
    assert ime._portfolio_millions_label(50_000.0) == "0,05"


def test_portfolio_duration_uses_supplied_days_and_keeps_quality_gap():
    frame = pd.DataFrame({
        "competencia": ["01/2026", "02/2026", "03/2026"],
        "competencia_dt": pd.date_range("2026-01-01", periods=3, freq="MS"),
        "duration_days": [82.0, 999.0, 84.0],
        "data_quality": ["ok", "nao_calculavel_bucket_aberto_dominante", "ok"],
    })
    before = frame.copy(deep=True)
    spec = ime._duration_line_chart(frame, portfolio_mode=True).to_dict(validate=True)
    line = spec["layer"][0]
    data = _rows(spec, line)
    assert line["encoding"]["y"]["title"] == "Dias"
    assert [row["duration_days"] for row in data] == [82.0, 999.0, 84.0]
    assert [row["_plot_duration_days"] for row in data] == [82.0, None, 84.0]
    assert [row["competencia"] for row in data] == ["jan/26", "fev/26", "mar/26"]
    assert line["encoding"]["detail"]["field"] == "_path_segment"
    assert len(_rows(spec, spec["layer"][2])) == 1
    pd.testing.assert_frame_equal(frame, before)


def test_duration_comparison_changes_unit_without_recomputing_days_from_months():
    frame = _monitor()
    frame["duration_months"] = [999.0, None, 888.0]
    spec = visuals.duration_chart(pd.DataFrame(), {"123": frame}, portfolio_mode=True).to_dict(validate=True)
    line = spec["layer"][0]
    assert line["encoding"]["y"]["field"] == "duration_days"
    assert line["encoding"]["y"]["title"] == "Dias"
    assert line["encoding"]["color"]["legend"] is None
    assert [row["duration_days"] for row in _rows(spec, line)] == [82.0, None, 84.0]
    legacy = visuals.duration_chart(pd.DataFrame(), {"123": frame}).to_dict(validate=True)
    assert legacy["layer"][0]["encoding"]["y"]["field"] == "duration_months"


def test_many_duration_series_keep_identities_and_values_without_endpoint_crowding():
    frames = {str(index): _monitor() for index in range(12)}
    spec = visuals.duration_chart(pd.DataFrame(), frames, portfolio_mode=True).to_dict(validate=True)
    assert len(spec["layer"]) == 1
    data = _rows(spec, spec["layer"][0])
    assert len(data) == 36 and len({row["serie"] for row in data}) == 12
    assert {row["serie"].split(" · ")[-1] for row in data} == set(frames)


def test_one_observed_roll_has_no_legend_and_does_not_drop_missing_rows():
    frame = _monitor()
    before = frame.copy(deep=True)
    spec = visuals.roll_rates_chart(frame, portfolio_mode=True).to_dict(validate=True)
    line = spec["layer"][0]
    assert line["encoding"]["color"]["legend"] is None
    data = _rows(spec, line)
    assert len(data) == 12
    one = [row for row in data if row["serie"].startswith("Roll 61-90")]
    assert [row["valor"] for row in one] == [0.0, None, 1.25]
    pd.testing.assert_frame_equal(frame, before)


def test_one_seasonal_series_keeps_original_identity_and_numeric_zero():
    frame = pd.DataFrame({
        "metric_id": ["roll_61_90_m3"] * 3, "year": [2026] * 3,
        "month": [1, 2, 3], "month_label": ["Jan", "Fev", "Mar"],
        "series_name": ["2026 / CNPJ 123 / Roll 61-90"] * 3,
        "value_pct": [0.0, None, 2.0], "formula": ["numerador / denominador"] * 3,
    })
    before = frame.copy(deep=True)
    spec = visuals.research_roll_seasonality_chart(frame, metric_id="roll_61_90_m3", portfolio_mode=True).to_dict(validate=True)
    line = spec["layer"][0]
    assert line["encoding"]["color"]["legend"] is None
    rows = _rows(spec, line)
    assert [row["value_pct"] for row in rows] == [0.0, None, 2.0]
    assert {row["source_series_name"] for row in rows} == {"2026 / CNPJ 123 / Roll 61-90"}
    assert {row["series_name"] for row in rows} == {"2026"}
    pd.testing.assert_frame_equal(frame, before)


def test_dense_pl_window_keeps_latest_total_visible_on_desktop_with_same_categories():
    dates = pd.date_range("2025-06-01", periods=13, freq="MS")
    frame = pd.DataFrame({
        "competencia": dates.strftime("%m/%Y"), "competencia_dt": dates,
        "serie": ["Subordinada"] * 13, "valor": [100_000_000.0] * 13, "ordem": [1] * 13,
    })
    spec = ime._stacked_history_bar_chart(
        frame, title=None, y_title="R$", value_column="valor",
        responsive_labels=True, show_total_labels=False, show_segment_labels=False,
        portfolio_mode=True, x_label_angle=0,
    ).to_dict(validate=True)
    total = spec["layer"][-1]
    expression = total["mark"]["opacity"]["expr"]
    assert 'datum.competencia === "jun/26"' in expression
    assert "width < 520" not in expression
    assert total["encoding"]["x"]["sort"] == spec["layer"][0]["encoding"]["x"]["sort"]
    assert {row["competencia"] for row in _rows(spec, total)} == set(total["encoding"]["x"]["sort"])
    assert all(row["valor_total"] == 100_000_000.0 for row in _rows(spec, total))


@pytest.mark.parametrize("factory", [visuals.npl_severity_chart, visuals.roll_rates_chart, visuals.portfolio_growth_chart])
def test_no_eligible_observation_has_safe_factory_without_fabricated_zero(factory):
    frame = _monitor()
    frame["universe_complete"] = False
    frame["npl_1_90_pct"] = [None] * 3
    frame["npl_91_360_pct"] = [None] * 3
    before = frame.copy(deep=True)
    spec = factory(frame, portfolio_mode=True).to_dict(validate=True)
    assert spec["mark"]["type"] == "text"
    assert list(spec["datasets"].values()) == [[{"x": 0, "text": "Sem dados"}]]
    pd.testing.assert_frame_equal(frame, before)


def test_all_missing_npl_is_safe_and_observed_zero_stays_numeric_zero():
    frame = _monitor()
    frame["npl_1_90_pct"] = None
    frame["npl_91_360_pct"] = None
    before = frame.copy(deep=True)
    absent = visuals.npl_severity_chart(frame, portfolio_mode=True).to_dict(validate=True)
    assert absent["mark"]["type"] == "text"
    pd.testing.assert_frame_equal(frame, before)
    frame["npl_1_90_pct"] = 0.0
    zero = visuals.npl_severity_chart(frame, portfolio_mode=True).to_dict(validate=True)
    bars = _rows(zero, zero["layer"][0])
    assert [row["valor"] for row in bars if row["serie"] == "NPL 1-90d"] == [0.0] * 3
    assert [row["valor"] for row in bars if row["serie"] == "NPL 91-360d"] == [None] * 3


def test_endpoint_readability_bounds_text_without_changing_roll_data_scale_or_legend():
    frame = _monitor()
    columns = ("roll_61_90_m3_pct", "roll_91_120_m4_pct", "roll_121_150_m5_pct", "roll_151_180_m6_pct")
    for column, value in zip(columns, (3.1, 0.8, 0.4, 0.2), strict=True):
        frame[column] = [None, None, value]
    before = frame.copy(deep=True)
    spec = visuals.roll_rates_chart(frame, portfolio_mode=True).to_dict(validate=True)
    line = spec["layer"][0]
    data = _rows(spec, line)
    assert [row["valor"] for row in data if row["competencia"] == "mar/26"] == [3.1, 0.8, 0.4, 0.2]
    expected_scale = visuals._tight_percent_scale(pd.Series([3.1, 0.8, 0.4, 0.2])).to_dict()
    assert line["encoding"]["y"]["scale"] == expected_scale
    assert len(line["encoding"]["color"]["scale"]["domain"]) == 4
    assert len(spec["layer"]) == 5
    for label in spec["layer"][1:]:
        assert "max(8, min(height - 8" in label["mark"]["dy"]["expr"]
        assert "scale" not in label["encoding"]["y"]
    assert ">= 15" in spec["layer"][-1]["mark"]["opacity"]["expr"]
    pd.testing.assert_frame_equal(frame, before)
    legacy = visuals.roll_rates_chart(frame).to_dict(validate=True)
    assert isinstance(legacy["layer"][1]["mark"]["dy"], int)


def test_portfolio_duration_domain_tracks_robbin_range_and_keeps_valid_zero():
    dates = pd.date_range('2025-12-01', periods=9, freq='MS')
    values = [46.,47.,51.,52.,57.,60.,59.,66.,69.]
    frame = pd.DataFrame({'competencia': dates.strftime('%m/%Y'), 'competencia_dt': dates,
                          'duration_days': values, 'data_quality': ['ok']*9})
    before = frame.copy(deep=True)
    spec = ime._duration_line_chart(frame, portfolio_mode=True).to_dict(validate=True)
    line = spec['layer'][0]
    domain = line['encoding']['y']['scale']['domain']
    assert 0 < domain[0] < min(values) and max(values) < domain[1] < 80
    assert [r['duration_days'] for r in _rows(spec,line)] == values
    pd.testing.assert_frame_equal(frame,before)
    legacy = ime._duration_line_chart(frame).to_dict(validate=True)
    assert legacy['layer'][0]['encoding']['y']['scale']['zero'] is True
    frame.loc[0,'duration_days'] = 0.
    zero_spec = ime._duration_line_chart(frame,portfolio_mode=True).to_dict(validate=True)
    assert zero_spec['layer'][0]['encoding']['y']['scale']['domain'][0] == 0.
    assert _rows(zero_spec,zero_spec['layer'][0])[0]['duration_days'] == 0.
