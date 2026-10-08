from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.industry_closed_offer_placement_regime import (
    ClosedOfferPlacementRegimeError,
    load_materialized_closed_offer_placement_regime,
    validate_closed_offer_placement_regime,
)


DATA_DIR = Path("data/industry_study")


def test_materialized_placement_regime_reconciles_offer_cohort() -> None:
    frame = load_materialized_closed_offer_placement_regime(DATA_DIR)
    totals = (
        frame.groupby("period_label", sort=False)
        .agg(
            offers=("closed_offers", "sum"),
            volume=("registered_volume_brl", "sum"),
        )
    )
    assert totals.loc["2024 FY", "offers"] == 1009
    assert totals.loc["2025 FY", "offers"] == 1476
    assert totals.loc["2026 jan-ago", "offers"] == 1034
    assert totals.loc["2024 FY", "volume"] == pytest.approx(
        95_416_726_133.75
    )
    assert totals.loc["2025 FY", "volume"] == pytest.approx(
        116_941_319_054.77
    )
    assert totals.loc["2026 jan-ago", "volume"] == pytest.approx(
        91_917_778_632.26
    )


def test_materialized_placement_regime_preserves_official_breakdown() -> None:
    frame = load_materialized_closed_offer_placement_regime(DATA_DIR)
    count = frame.pivot(
        index="period_label",
        columns="placement_regime",
        values="closed_offers",
    )
    assert count.loc["2024 FY", "Melhores esforços"] == 945
    assert count.loc["2024 FY", "Garantia firme"] == 38
    assert count.loc["2024 FY", "Misto"] == 26
    assert count.loc["2024 FY", "Não informado"] == 0
    assert count.loc["2026 jan-ago", "Melhores esforços"] == 981
    assert count.loc["2026 jan-ago", "Garantia firme"] == 34
    assert count.loc["2026 jan-ago", "Misto"] == 19


def test_placement_regime_exposes_true_prior_ytd_comparison() -> None:
    frame = load_materialized_closed_offer_placement_regime(DATA_DIR)
    guarantee = frame[
        frame["period_label"].eq("2026 jan-ago")
        & frame["placement_regime"].eq("Garantia firme")
    ].iloc[0]
    assert guarantee["comparison_period_label"] == "2025 jan-ago"
    assert guarantee["comparison_closed_offers"] == 29
    assert guarantee["comparison_registered_volume_brl"] == pytest.approx(
        13_382_592_653.59
    )
    assert guarantee["registered_volume_brl"] == pytest.approx(18_313_675_000.0)
    assert guarantee["registered_volume_yoy_ytd"] == pytest.approx(
        0.3684698827836767
    )


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
