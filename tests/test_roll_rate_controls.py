from __future__ import annotations

import unittest

import pandas as pd

from services.roll_rate_controls import (
    available_roll_seasonality_specs,
    default_roll_seasonality_metric_ids,
)


class RollRateControlsTest(unittest.TestCase):
    def test_roll_seasonality_selector_defaults_to_one_available_bucket(self) -> None:
        roll_df = pd.DataFrame({"metric_id": ["roll_91_120_m4", "roll_151_180_m6"]})

        specs = available_roll_seasonality_specs(roll_df)

        self.assertEqual(["roll_91_120_m4", "roll_151_180_m6"], [spec["metric_id"] for spec in specs])
        self.assertEqual(["roll_91_120_m4"], default_roll_seasonality_metric_ids(specs))


if __name__ == "__main__":
    unittest.main()
