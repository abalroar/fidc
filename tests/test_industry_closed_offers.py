from __future__ import annotations

import json
from pathlib import Path
import shutil

import math
import pandas as pd
import pytest

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


def test_loads_and_reconciles_materialized_closed_offer_tables() -> None:
    tables = load_closed_offers_tables()

    assert tables.annual["year"].tolist() == [2023, 2024, 2025, 2026]
    assert len(tables.monthly) == 41
    assert tables.monthly.iloc[-1]["competence"] == "2026-06"
    assert bool(tables.monthly.iloc[-1]["is_complete_month"])
    assert len(tables.originators) == 17
    assert tables.originators.iloc[0]["originator_group"] == "CloudWalk"


def test_full_payload_is_json_serializable_and_has_stable_blocks() -> None:
    payload = build_closed_offers_payload()

    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    assert encoded
    assert payload["schema"] == "industry_closed_offers.v1"
    assert payload["annual"]["row_count"] == 4
    assert payload["monthly"]["row_count"] == 41
    assert payload["jan_june_2024_2026"]["row_count"] == 3
    assert payload["jan_may_2024_2026"]["row_count"] == 3
    assert payload["originators_2026_ytd"]["row_count"] == 17
    assert payload["annual"]["source"]["archive_sha256"] == (
        "ff53d4406953411a3153a2701669c6d06ebad56f5d849c7e0190406ac7bfa0f3"
    )


def test_jan_june_view_recalculates_comparable_ticket_and_volume() -> None:
    tables = load_closed_offers_tables()
    rows = build_jan_june_closed_offers_payload(tables.monthly)["rows"]
    by_year = {row["year"]: row for row in rows}

    expected = {
        2024: (413, 40_869_510_061.91, 98_957_651.48162228),
        2025: (700, 57_158_706_968.36, 81_655_295.66908571),
        2026: (771, 65_488_118_983.56, 84_939_194.53120622),
    }
    assert set(by_year) == set(expected)
    for year, (offers, volume, ticket) in expected.items():
        assert by_year[year]["closed_offers"] == offers
        assert math.isclose(by_year[year]["registered_volume_brl"], volume, abs_tol=0.01)
        assert math.isclose(by_year[year]["mean_registered_ticket_brl"], ticket, abs_tol=0.01)
        assert by_year[year]["period_start"] == f"{year}-01-01"
        assert by_year[year]["period_end"] == f"{year}-06-30"


def test_nominable_originator_list_is_complete_sorted_and_reconciled() -> None:
    tables = load_closed_offers_tables()
    rows = list_nominable_originators_2026_ytd(tables.originators)

    assert [row["rank"] for row in rows] == list(range(1, 18))
    assert rows[0]["originator_group"] == "CloudWalk"
    assert rows[-1]["originator_group"] == "Pravaler"
    assert all(row["confidence"] == "alta - regra nominal auditável" for row in rows)
    assert all(
        left["registered_volume_brl"] >= right["registered_volume_brl"]
        for left, right in zip(rows, rows[1:])
    )
    identified = sum(row["registered_volume_brl"] for row in rows)
    assert math.isclose(identified, 21_099_788_000.0, abs_tol=0.01)
    assert math.isclose(rows[0]["identified_registered_volume_coverage"], 0.3221926103160307)


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

    with pytest.raises(ClosedOffersDataError, match="natural_person_accounts não reconcilia em 2023"):
        load_closed_offers_tables(tmp_path)
