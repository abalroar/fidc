from __future__ import annotations

import unittest
from datetime import date, datetime

from services.fidc_model.calendar import (
    b3_market_holidays_for_dates,
    b3_market_holidays_for_year,
    build_day_counts,
    merge_with_b3_market_holidays,
    networkdays,
)


class B3CalendarTest(unittest.TestCase):
    def test_projected_2026_market_holidays_include_b3_non_trading_days(self):
        holidays = b3_market_holidays_for_year(2026)

        self.assertIn(date(2026, 2, 16), holidays)
        self.assertIn(date(2026, 2, 17), holidays)
        self.assertIn(date(2026, 4, 3), holidays)
        self.assertIn(date(2026, 6, 4), holidays)
        self.assertIn(date(2026, 11, 20), holidays)
        self.assertIn(date(2026, 12, 24), holidays)
        self.assertIn(date(2026, 12, 31), holidays)
        self.assertNotIn(date(2026, 7, 9), holidays)

    def test_market_holidays_are_generated_for_flow_years(self):
        holidays = b3_market_holidays_for_dates([datetime(2025, 3, 1), datetime(2028, 11, 1)])

        self.assertIn(date(2025, 4, 18), holidays)
        self.assertIn(date(2028, 2, 28), holidays)

    def test_merge_with_b3_market_holidays_keeps_static_and_projects_future(self):
        merged = merge_with_b3_market_holidays([datetime(2018, 12, 31)], [datetime(2026, 1, 1)])

        self.assertIn(date(2018, 12, 31), merged)
        self.assertIn(date(2026, 1, 1), merged)

    def test_build_day_counts_accepts_date_holidays(self):
        datas = [datetime(2026, 4, 1), datetime(2026, 4, 6)]
        _, du = build_day_counts(datas, [date(2026, 4, 3)])

        self.assertEqual([0, 2], du)
        self.assertEqual(3, networkdays(date(2026, 4, 1), date(2026, 4, 6), [date(2026, 4, 3)]))


if __name__ == "__main__":
    unittest.main()
