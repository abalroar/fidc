from __future__ import annotations

from datetime import date, datetime, timezone
import json
import unittest

from services.fidc_model.b3_cdi import (
    B3_BDI_SOURCE,
    B3_MEDIA_CDI_SOURCE,
    B3CdiDailyRate,
    B3CdiError,
    b3_bdi_di_over_url,
    fetch_b3_bdi_cdi_daily_rates,
    fetch_b3_cdi_monthly_rates,
    parse_media_cdi_text,
)


class _BytesResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self) -> _BytesResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


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
            bdi_fetcher=None,
        )

        self.assertEqual(1, len(rates))
        self.assertEqual("2025-01", rates[0].mes)
        self.assertEqual(2, rates[0].dias_uteis)
        expected = (1.0 + 0.252) ** (2 / 252.0) - 1.0
        self.assertAlmostEqual(expected, rates[0].cdi_mensal)

    def test_fetch_b3_cdi_monthly_rates_marks_missing_december_24_and_31_as_incomplete(self):
        unavailable = {
            date(2025, 12, 24),
            date(2025, 12, 25),
            date(2025, 12, 31),
        }

        def fake_fetcher(item_date: date, **_: object) -> B3CdiDailyRate:
            if item_date in unavailable:
                raise B3CdiError("fixture sem arquivo")
            return B3CdiDailyRate(
                data=item_date,
                taxa_aa=0.149,
                source_url="fixture",
                retrieved_at=datetime.now(timezone.utc),
            )

        rates = fetch_b3_cdi_monthly_rates(
            date(2025, 12, 24),
            date(2025, 12, 31),
            fetcher=fake_fetcher,
            bdi_fetcher=None,
        )

        self.assertEqual(1, len(rates))
        december = rates[0]
        self.assertEqual("2025-12", december.mes)
        self.assertEqual(5, december.expected_dias_uteis)
        self.assertEqual(3, december.dias_uteis)
        self.assertEqual(
            (date(2025, 12, 24), date(2025, 12, 31)),
            december.missing_dates,
        )
        self.assertFalse(december.is_complete)

    def test_fetch_b3_bdi_daily_rates_uses_official_factor_and_paginates(self):
        urls: list[str] = []

        def fake_opener(request: object, **_: object) -> _BytesResponse:
            url = str(getattr(request, "full_url"))
            urls.append(url)
            self.assertEqual("POST", request.get_method())  # type: ignore[attr-defined]
            self.assertEqual(b"{}", request.data)  # type: ignore[attr-defined]
            page = 1 if "/1/1" in url else 2
            factor = 1.00055131 if page == 1 else 1.00055200
            payload = {
                "table": {
                    "columns": [
                        {"name": "DailyFactor"},
                        {"name": "RptDt"},
                        {"name": "Average"},
                    ],
                    "values": [
                        [factor, f"2025-09-0{page}T00:00:00", 99.0],
                    ],
                    "pageCount": 2,
                }
            }
            return _BytesResponse(json.dumps(payload).encode("utf-8"))

        rates = fetch_b3_bdi_cdi_daily_rates(
            date(2025, 9, 1),
            date(2025, 9, 2),
            opener=fake_opener,
            page_size=1,
        )

        self.assertEqual(
            [
                b3_bdi_di_over_url(date(2025, 9, 1), date(2025, 9, 2), page=1, page_size=1),
                b3_bdi_di_over_url(date(2025, 9, 1), date(2025, 9, 2), page=2, page_size=1),
            ],
            urls,
        )
        self.assertEqual((date(2025, 9, 1), date(2025, 9, 2)), tuple(rate.data for rate in rates))
        self.assertAlmostEqual(0.00055131, rates[0].fator_diario)
        self.assertAlmostEqual(1.00055131**252 - 1.0, rates[0].taxa_aa)

    def test_fetch_b3_cdi_monthly_rates_prefers_complete_bdi_https_data(self):
        def fake_bdi_fetcher(*_: object) -> tuple[B3CdiDailyRate, ...]:
            return tuple(
                B3CdiDailyRate(
                    data=item_date,
                    taxa_aa=0.149,
                    source_url=b3_bdi_di_over_url(date(2025, 1, 1), date(2025, 1, 3)),
                    retrieved_at=datetime.now(timezone.utc),
                    daily_factor=1.0005,
                )
                for item_date in (date(2025, 1, 2), date(2025, 1, 3))
            )

        def forbidden_ftp_fetcher(*_: object, **__: object) -> B3CdiDailyRate:
            raise AssertionError("FTP não deve ser consultado quando o BDI está completo")

        rates = fetch_b3_cdi_monthly_rates(
            date(2025, 1, 1),
            date(2025, 1, 3),
            fetcher=forbidden_ftp_fetcher,
            bdi_fetcher=fake_bdi_fetcher,
        )

        self.assertEqual(1, len(rates))
        self.assertEqual(2, rates[0].dias_uteis)
        self.assertAlmostEqual(1.0005**2 - 1.0, rates[0].cdi_mensal)
        self.assertEqual(B3_BDI_SOURCE, rates[0].source)
        self.assertTrue(rates[0].is_complete)

    def test_fetch_b3_cdi_monthly_rates_falls_back_only_for_missing_bdi_dates(self):
        def fake_bdi_fetcher(*_: object) -> tuple[B3CdiDailyRate, ...]:
            return (
                B3CdiDailyRate(
                    data=date(2025, 1, 2),
                    taxa_aa=0.149,
                    source_url=b3_bdi_di_over_url(date(2025, 1, 2), date(2025, 1, 3)),
                    retrieved_at=datetime.now(timezone.utc),
                    daily_factor=1.0005,
                ),
            )

        ftp_dates: list[date] = []

        def fake_ftp_fetcher(item_date: date, **_: object) -> B3CdiDailyRate:
            ftp_dates.append(item_date)
            return B3CdiDailyRate(
                data=item_date,
                taxa_aa=0.149,
                source_url=f"ftp://ftp.cetip.com.br/MediaCDI/{item_date:%Y%m%d}.txt",
                retrieved_at=datetime.now(timezone.utc),
            )

        rates = fetch_b3_cdi_monthly_rates(
            date(2025, 1, 2),
            date(2025, 1, 3),
            fetcher=fake_ftp_fetcher,
            bdi_fetcher=fake_bdi_fetcher,
        )

        self.assertEqual([date(2025, 1, 3)], ftp_dates)
        self.assertTrue(rates[0].is_complete)
        self.assertIn(B3_BDI_SOURCE, rates[0].source)
        self.assertIn(B3_MEDIA_CDI_SOURCE, rates[0].source)

    def test_fetch_b3_cdi_monthly_rates_raises_when_https_and_ftp_both_fail(self):
        def failed_bdi_fetcher(*_: object) -> tuple[B3CdiDailyRate, ...]:
            raise B3CdiError("HTTPS indisponível")

        def failed_ftp_fetcher(*_: object, **__: object) -> B3CdiDailyRate:
            raise B3CdiError("FTP indisponível")

        with self.assertRaisesRegex(B3CdiError, "Nenhuma taxa CDI realizada"):
            fetch_b3_cdi_monthly_rates(
                date(2025, 1, 2),
                date(2025, 1, 2),
                fetcher=failed_ftp_fetcher,
                bdi_fetcher=failed_bdi_fetcher,
                max_workers=1,
            )


if __name__ == "__main__":
    unittest.main()
