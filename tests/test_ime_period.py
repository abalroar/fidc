from __future__ import annotations

from datetime import date
import unittest

from services.ime_period import (
    DEFAULT_PRESET_MONTHS,
    build_custom_period,
    build_preset_period,
    current_default_end_month,
    month_options,
)


class ImePeriodTests(unittest.TestCase):
    def test_build_preset_period_is_inclusive(self) -> None:
        period = build_preset_period(end_month=date(2026, 4, 1), months=DEFAULT_PRESET_MONTHS)

        self.assertEqual(date(2025, 5, 1), period.start_month)
        self.assertEqual(date(2026, 4, 1), period.end_month)
        self.assertEqual(12, period.month_count)
        self.assertEqual("05/2025 a 04/2026", period.label)

    def test_build_custom_period_rejects_inverted_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "Competência inicial"):
            build_custom_period(start_month=date(2026, 5, 1), end_month=date(2026, 4, 1))

    def test_month_options_returns_contiguous_months(self) -> None:
        options = month_options(date(2026, 4, 1), months_back=5)

        self.assertEqual(
            [
                date(2025, 11, 1),
                date(2025, 12, 1),
                date(2026, 1, 1),
                date(2026, 2, 1),
                date(2026, 3, 1),
                date(2026, 4, 1),
            ],
            options,
        )

    def test_current_default_end_month_normalizes_to_first_day(self) -> None:
        self.assertEqual(date(2026, 4, 1), current_default_end_month(date(2026, 4, 14)))


if __name__ == "__main__":
    unittest.main()
