from __future__ import annotations

import json

import pytest

from services.industry_comparative_period import ComparisonCut


def test_reporting_cut_selects_august_and_preserves_partial_september(tmp_path):
    (tmp_path / "industry_competence_status.csv").write_text(
        "competencia,publication_status\n2026-06,completa\n2026-09,preliminar\n2026-08,completa\n",
    )
    (tmp_path / "metadata.json").write_text(json.dumps({"competencia_snapshot": "202606"}))
    meta = ComparisonCut.from_data_dir(tmp_path).to_meta()
    assert meta["current_period_end"] == "2026-08-31"
    assert meta["previous_period_end"] == "2025-08-31"
    assert meta["current_period_id"] == "2026 jan-ago"
    assert meta["previous_period_id"] == "2025 jan-ago"
    assert meta["period_label"] == "jan–ago/26"
    assert meta["current_period_key"] == "ago26"


def test_leap_year_windows_include_each_year_actual_february_end():
    meta = ComparisonCut.from_competence("2024-02").to_meta()
    assert meta["current_period_end"] == "2024-02-29"
    assert meta["previous_period_end"] == "2023-02-28"


def test_new_year_moves_all_comparison_labels_and_dates_without_fixed_year():
    meta = ComparisonCut.from_competence("202701").to_meta()
    assert meta["current_year"] == 2027
    assert meta["period_label"] == "jan/27"
    assert meta["previous_period_label"] == "jan/26"
    assert meta["current_period_key"] == "jan27"
    assert meta["previous_period_key"] == "jan26"
    assert meta["current_period_start"] == "2027-01-01"
    assert meta["month_count"] == 1


def test_partial_only_status_never_falls_back_to_a_stale_snapshot(tmp_path):
    (tmp_path / "industry_competence_status.csv").write_text(
        "competencia,publication_status\n2026-09,preliminar\n",
    )
    (tmp_path / "metadata.json").write_text(json.dumps({"competencia_snapshot": "202606"}))
    with pytest.raises(ValueError, match="Nenhuma competência consolidada"):
        ComparisonCut.from_data_dir(tmp_path)


def test_legacy_snapshot_requires_an_explicit_validated_month(tmp_path):
    with pytest.raises(ValueError, match="não identificada"):
        ComparisonCut.from_data_dir(tmp_path)
    (tmp_path / "metadata.json").write_text(json.dumps({"competencia_snapshot": "202608"}))
    assert ComparisonCut.from_data_dir(tmp_path).competence == "2026-08"


@pytest.mark.parametrize("value", ["2026-00", "2026-13", "ago/26", "2026-08-31", "", "0000-06"])
def test_invalid_competence_is_rejected(value):
    with pytest.raises(ValueError):
        ComparisonCut.from_competence(value)
