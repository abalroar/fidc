from __future__ import annotations

import json
from pathlib import Path
import shutil

import math
import pandas as pd
import pytest

from services.industry_comparative_period import ComparisonCut
from services.industry_closed_offers import (
    ANNUAL_FILENAME,
    ClosedOffersDataError,
    INDUSTRY_STUDY_DIR,
    MONTHLY_FILENAME,
    ORIGINATORS_FILENAME,
    build_closed_offers_payload,
    build_jan_june_closed_offers_payload,
    list_nominable_originators_2026_ytd,
    load_closed_offers_tables,
    validate_closed_offers_annual,
)


def _published_offer_cohort() -> pd.DataFrame:
    """Granular input retained independently of the aggregate payload blocks."""
    frame = pd.read_csv(
        INDUSTRY_STUDY_DIR / "industry_closed_offer_ticket_cohort.csv.gz",
        dtype={"numero_requerimento": str},
        keep_default_na=False,
    )
    assert not frame["numero_requerimento"].duplicated().any()
    frame["data_encerramento"] = pd.to_datetime(frame["data_encerramento"], errors="raise")
    frame["registered_volume_brl"] = pd.to_numeric(frame["registered_volume_brl"], errors="raise")
    return frame


def test_loads_and_reconciles_materialized_closed_offer_tables() -> None:
    tables = load_closed_offers_tables()
    cut = ComparisonCut.from_data_dir(INDUSTRY_STUDY_DIR)

    assert tables.annual["year"].tolist() == list(range(int(tables.annual["year"].min()), cut.year + 1))
    assert tables.annual.iloc[-1]["period_end"] == cut.period_end.isoformat()
    assert tables.monthly["competence"].max() == cut.competence
    assert not tables.monthly["competence"].duplicated().any()
    current = tables.monthly[tables.monthly["year"].eq(cut.year)]
    assert current["month"].tolist() == list(range(1, cut.month + 1))
    assert current["is_complete_month"].all()
    assert not tables.originators.empty
    assert tables.originators["originator_group"].is_unique
    assert tables.originators["period_end"].eq(cut.period_end.isoformat()).all()


def test_full_payload_is_json_serializable_and_has_stable_blocks() -> None:
    payload = build_closed_offers_payload()
    tables = load_closed_offers_tables()
    cohort = _published_offer_cohort()

    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    assert encoded
    assert payload["schema"] == "industry_closed_offers.v1"
    assert payload["annual"]["row_count"] == len(tables.annual)
    assert payload["monthly"]["row_count"] == len(tables.monthly)
    assert payload["jan_june_2024_2026"]["row_count"] == 3
    assert payload["jan_may_2024_2026"]["row_count"] == 3
    assert payload["originators_2026_ytd"]["row_count"] == len(tables.originators)
    assert cohort["source_archive_sha256"].nunique() == 1
    assert payload["annual"]["source"]["archive_sha256"] == cohort["source_archive_sha256"].iloc[0]
    assert payload["monthly"]["source"]["archive_sha256"] == cohort["source_archive_sha256"].iloc[0]
    assert payload["comparison_meta"] == ComparisonCut.from_data_dir(INDUSTRY_STUDY_DIR).to_meta()


def test_legacy_alias_recalculates_the_current_comparable_ticket_and_volume() -> None:
    tables = load_closed_offers_tables()
    rows = build_jan_june_closed_offers_payload(tables.monthly)["rows"]
    by_year = {row["year"]: row for row in rows}
    cut = ComparisonCut.from_data_dir(INDUSTRY_STUDY_DIR)
    cohort = _published_offer_cohort()

    assert set(by_year) == set(range(cut.year - 2, cut.year + 1))
    for year, row in by_year.items():
        period = cohort[
            cohort["data_encerramento"].dt.year.eq(year)
            & cohort["data_encerramento"].dt.month.le(cut.month)
        ]
        offers = period["numero_requerimento"].nunique()
        volume = period["registered_volume_brl"].sum()
        assert offers > 0
        assert row["closed_offers"] == offers
        assert math.isclose(row["registered_volume_brl"], volume, abs_tol=0.01, rel_tol=0)
        assert math.isclose(row["mean_registered_ticket_brl"], volume / offers, abs_tol=0.01, rel_tol=0)
        assert row["period_start"] == f"{year}-01-01"
        assert row["period_end"] == ComparisonCut(year, cut.month).period_end.isoformat()


def test_nominable_originator_list_is_complete_sorted_and_reconciled() -> None:
    tables = load_closed_offers_tables()
    rows = list_nominable_originators_2026_ytd(tables.originators)
    cut = ComparisonCut.from_data_dir(INDUSTRY_STUDY_DIR)
    cohort = _published_offer_cohort()
    current = cohort[cohort["data_encerramento"].dt.year.eq(cut.year)]
    universe_volume = float(current["registered_volume_brl"].sum())

    assert [row["rank"] for row in rows] == list(range(1, len(tables.originators) + 1))
    assert len({row["originator_group"] for row in rows}) == len(rows)
    assert all(row["confidence"] == "alta - regra nominal auditável" for row in rows)
    assert all(
        left["registered_volume_brl"] >= right["registered_volume_brl"]
        for left, right in zip(rows, rows[1:])
    )
    identified = sum(row["registered_volume_brl"] for row in rows)
    assert 0 < identified <= universe_volume
    for row in rows:
        assert row["universe_closed_offers"] == current["numero_requerimento"].nunique()
        assert row["universe_registered_volume_brl"] == pytest.approx(universe_volume, abs=0.01, rel=0)
        assert row["identified_registered_volume_brl"] == pytest.approx(identified, abs=0.01, rel=0)
        assert row["unidentified_registered_volume_brl"] == pytest.approx(universe_volume - identified, abs=0.01, rel=0)
        assert row["identified_registered_volume_coverage"] == pytest.approx(identified / universe_volume)
        assert row["share_of_total_registered_volume"] == pytest.approx(row["registered_volume_brl"] / universe_volume)
        assert row["share_of_identified_registered_volume"] == pytest.approx(row["registered_volume_brl"] / identified)


def test_schema_validation_rejects_missing_required_column() -> None:
    frame = pd.read_csv(INDUSTRY_STUDY_DIR / ANNUAL_FILENAME).drop(
        columns="source_archive_sha256"
    )

    with pytest.raises(ClosedOffersDataError, match="source_archive_sha256"):
        validate_closed_offers_annual(frame)


def test_cross_table_validation_rejects_non_reconciling_monthly_value(tmp_path: Path) -> None:
    for filename in (ANNUAL_FILENAME, MONTHLY_FILENAME, ORIGINATORS_FILENAME):
        shutil.copy2(INDUSTRY_STUDY_DIR / filename, tmp_path / filename)

    monthly_path = tmp_path / MONTHLY_FILENAME
    monthly = pd.read_csv(monthly_path)
    monthly.loc[0, "natural_person_accounts"] += 1
    monthly.to_csv(monthly_path, index=False)

    with pytest.raises(ClosedOffersDataError, match="natural_person_accounts não reconcilia em 2022"):
        load_closed_offers_tables(tmp_path)
