from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from services.fidc_model.b3_cdi import B3CdiDailyRate, fetch_b3_cdi_monthly_rates, parse_media_cdi_text


class B3CdiTest(unittest.TestCase):
    def test_parse_media_cdi_text(self):
        self.assertAlmostEqual(0.1215, parse_media_cdi_text("000001215"))
        self.assertAlmostEqual(0.1490, parse_media_cdi_text("000001490   \r\n"))

    def test_fetch_b3_cdi_monthly_rates_compounds_daily_files(self):
        def fake_fetcher(item_date: date, **_: object) -> B3CdiDailyRate:
            return B3CdiDailyRate(
                data=item_date,
                taxa_aa=0.252,
                source_url="fixture",
                retrieved_at=datetime.now(timezone.utc),
            )

        rates = fetch_b3_cdi_monthly_rates(
            date(2025, 1, 1),
            date(2025, 1, 3),
            fetcher=fake_fetcher,
        )

        self.assertEqual(1, len(rates))
        self.assertEqual("2025-01", rates[0].mes)
        self.assertEqual(3, rates[0].dias_uteis)
        expected = (1.0 + 0.252) ** (3 / 252.0) - 1.0
        self.assertAlmostEqual(expected, rates[0].cdi_mensal)


if __name__ == "__main__":
    unittest.main()
