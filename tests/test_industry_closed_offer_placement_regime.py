from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.industry_comparative_period import ComparisonCut
from services.industry_closed_offer_placement_regime import (
    ClosedOfferPlacementRegimeError,
    load_materialized_closed_offer_placement_regime,
    validate_closed_offer_placement_regime,
)


DATA_DIR = Path("data/industry_study")
REGIMES = ("Melhores esforços", "Garantia firme", "Misto", "Não informado")


def _official_cohort() -> pd.DataFrame:
    cohort = pd.read_csv(
        DATA_DIR / "industry_closed_offer_ticket_cohort.csv.gz",
        dtype={"numero_requerimento": str},
        keep_default_na=False,
    )
    assert not cohort["numero_requerimento"].duplicated().any()
    cohort["registered_volume_brl"] = pd.to_numeric(cohort["registered_volume_brl"], errors="raise")
    cohort["data_encerramento"] = pd.to_datetime(cohort["data_encerramento"], errors="raise")
    # These are literal official regimes retained on each source offer. Unknown
    # labels must fail rather than silently enter the missing-data bucket.
    labels = {
        "Melhores Esforços": "Melhores esforços",
        "Garantia Firme de Colocação": "Garantia firme",
        "Garantia Firme de Liquidação": "Garantia firme",
        "Misto": "Misto",
        "": "Não informado",
    }
    cohort["placement_regime"] = cohort["distribution_regime"].map(labels)
    assert cohort["placement_regime"].notna().all()
    return cohort


def _reconciliation_cohort() -> pd.DataFrame:
    # Placement publishes the three full preceding years and current YTD;
    # the granular input additionally retains an older partial legacy year.
    cut = ComparisonCut.from_data_dir(DATA_DIR)
    periods = {f"{year} FY" for year in range(cut.year - 3, cut.year)} | {cut.period_id()}
    cohort = _official_cohort()
    selected = cohort[cohort["period_label"].isin(periods)]
    assert set(selected["period_label"]) == periods
    return selected


def test_materialized_placement_regime_reconciles_offer_cohort() -> None:
    frame = load_materialized_closed_offer_placement_regime(DATA_DIR)
    cohort = _reconciliation_cohort()
    totals = frame.groupby("period_label", sort=False).agg(
        offers=("closed_offers", "sum"),
        volume=("registered_volume_brl", "sum"),
    )
    source = cohort.groupby("period_label", sort=False).agg(
        offers=("numero_requerimento", "nunique"),
        volume=("registered_volume_brl", "sum"),
    )
    assert set(totals.index) == set(source.index)
    for period, row in source.iterrows():
        assert totals.loc[period, "offers"] == row["offers"]
        assert totals.loc[period, "volume"] == pytest.approx(row["volume"], abs=0.01, rel=0)
    assert set(frame["source_archive_sha256"]) == set(cohort["source_archive_sha256"])
    assert set(frame["source_as_of_date"]) == set(cohort["source_as_of_date"])


def test_materialized_placement_regime_preserves_official_breakdown() -> None:
    frame = load_materialized_closed_offer_placement_regime(DATA_DIR)
    cohort = _reconciliation_cohort()
    source = cohort.groupby(["period_label", "placement_regime"]).agg(
        offers=("numero_requerimento", "nunique"),
        volume=("registered_volume_brl", "sum"),
    )
    expected_keys = pd.MultiIndex.from_product(
        [cohort["period_label"].unique(), REGIMES],
        names=["period_label", "placement_regime"],
    )
    source = source.reindex(expected_keys, fill_value=0)
    indexed = frame.set_index(["period_label", "placement_regime"])
    assert indexed.index.is_unique and set(indexed.index) == set(source.index)
    for key, row in source.iterrows():
        assert indexed.loc[key, "closed_offers"] == row["offers"]
        assert indexed.loc[key, "registered_volume_brl"] == pytest.approx(row["volume"], abs=0.01, rel=0)


def test_placement_regime_exposes_true_prior_ytd_comparison() -> None:
    frame = load_materialized_closed_offer_placement_regime(DATA_DIR)
    cut = ComparisonCut.from_data_dir(DATA_DIR)
    cohort = _official_cohort()
    current = frame[frame["period_label"].eq(cut.period_id())]
    previous = cohort[
        cohort["data_encerramento"].between(
            pd.Timestamp(f"{cut.year - 1}-01-01"),
            pd.Timestamp(cut.previous_period_end),
        )
    ]
    assert set(current["placement_regime"]) == set(REGIMES)
    assert current["period_end"].eq(cut.period_end.isoformat()).all()
    for _, row in current.iterrows():
        source = previous[previous["placement_regime"].eq(row["placement_regime"])]
        volume = float(source["registered_volume_brl"].sum())
        assert row["comparison_period_label"] == cut.period_id(cut.year - 1)
        assert row["comparison_period_start"] == f"{cut.year - 1}-01-01"
        assert row["comparison_period_end"] == cut.previous_period_end.isoformat()
        assert row["comparison_closed_offers"] == source["numero_requerimento"].nunique()
        assert row["comparison_registered_volume_brl"] == pytest.approx(volume, abs=0.01, rel=0)
        if volume:
            assert row["registered_volume_yoy_ytd"] == pytest.approx(row["registered_volume_brl"] / volume - 1)
        else:
            assert pd.isna(row["registered_volume_yoy_ytd"])


def test_placement_regime_validation_rejects_broken_share() -> None:
    frame = load_materialized_closed_offer_placement_regime(DATA_DIR)
    broken = frame.copy()
    broken.loc[0, "closed_offers_share"] = 0.0
    with pytest.raises(
        ClosedOfferPlacementRegimeError,
        match="participação da quantidade",
    ):
        validate_closed_offer_placement_regime(broken)


def test_placement_regime_validation_rejects_missing_regime() -> None:
    frame = load_materialized_closed_offer_placement_regime(DATA_DIR)
    broken = frame.iloc[:-1].copy()
    with pytest.raises(
        ClosedOfferPlacementRegimeError,
        match="deveria conter",
    ):
        validate_closed_offer_placement_regime(broken)
