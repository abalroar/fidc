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
    assert totals.loc["2025 FY", "offers"] == 1470
    assert totals.loc["2026 jan-jun", "offers"] == 771
    assert totals.loc["2024 FY", "volume"] == pytest.approx(
        95_416_726_133.75
    )
    assert totals.loc["2025 FY", "volume"] == pytest.approx(
        116_348_319_054.77
    )
    assert totals.loc["2026 jan-jun", "volume"] == pytest.approx(
        65_488_118_983.56
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
    assert count.loc["2026 jan-jun", "Melhores esforços"] == 737
    assert count.loc["2026 jan-jun", "Garantia firme"] == 22
    assert count.loc["2026 jan-jun", "Misto"] == 12


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
