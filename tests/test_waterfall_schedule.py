from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from services.waterfall_schedule import (
    FidcAmortizationSchedule,
    build_waterfall_schedule,
    detect_amortization_convention,
    export_waterfall,
    load_cloudwalk_emissions,
    parse_amortization_schedule,
    percentages_to_incremental,
)


class WaterfallScheduleTest(unittest.TestCase):
    def test_detect_convention_incremental(self):
        dates = [date(2025, 6, 30), date(2025, 12, 31), date(2026, 6, 30), date(2026, 12, 31)]

        self.assertEqual("incremental", detect_amortization_convention(dates, [16, 34, 30, 20]))

    def test_detect_convention_cumulative(self):
        dates = [date(2025, 6, 30), date(2025, 12, 31), date(2026, 6, 30), date(2026, 12, 31)]

        self.assertEqual("cumulative", detect_amortization_convention(dates, [16, 50, 80, 100]))

    def test_detect_convention_ambiguous(self):
        dates = [date(2025, 6, 30), date(2025, 12, 31), date(2026, 6, 30), date(2026, 12, 31)]

        with self.assertRaises(ValueError):
            detect_amortization_convention(dates, [16, 50, 80, 110])

    def test_cumulative_to_incremental(self):
        deltas = percentages_to_incremental([16, 50, 80, 100], "cumulative")

        self.assertEqual([16, 34, 30, 20], deltas)
        self.assertEqual([160_000, 340_000, 300_000, 200_000], [1_000_000 * value / 100 for value in deltas])

    def test_incremental_sum_validation_keeps_near_100_with_warning(self):
        convention, schedule, warnings = parse_amortization_schedule(
            "30% em jan/27, 30% em fev/27, 37% em mar/27",
            1_000_000,
        )

        self.assertEqual("incremental", convention)
        self.assertAlmostEqual(970_000, sum(amount for _, amount in schedule))
        self.assertTrue(warnings)

    def test_document_rounding_near_100_is_adjusted_to_principal(self):
        _, schedule, warnings = parse_amortization_schedule(
            "23/05/2029 11,67%; 23/06/2029 11,67%; 23/07/2029 11,67%; "
            "23/08/2029 11,67%; 23/09/2029 11,67%; 23/10/2029 11,67%; "
            "23/11/2029 5,00%; 23/12/2029 5,00%; 23/01/2030 5,00%; "
            "23/02/2030 5,00%; 23/03/2030 5,00%; 23/04/2030 5,00%",
            1_000_000,
        )

        self.assertAlmostEqual(1_000_000, sum(amount for _, amount in schedule))
        self.assertEqual((), warnings)

    def test_incremental_sum_invalid(self):
        with self.assertRaises(ValueError):
            parse_amortization_schedule("50% em jan/27, 50% em fev/27, 50% em mar/27", 1_000_000)

    def test_bullet_parsing(self):
        convention, schedule, warnings = parse_amortization_schedule("Bullet em 15/06/2027", 1_000_000)

        self.assertEqual("incremental", convention)
        self.assertEqual([(date(2027, 6, 15), 1_000_000)], schedule)
        self.assertEqual((), warnings)

    def test_empty_schedule_excluded(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cloudwalk.csv"
            pd.DataFrame(
                [
                    {
                        "Fundo": "CLOUDWALK TEST",
                        "CNPJ": "42.085.816/0001-05",
                        "Cota/Classe": "1ª série sênior",
                        "Tipo": "Sênior",
                        "Volume": "R$ 1.000.000,00",
                        "Amortização principal": "",
                    }
                ]
            ).to_csv(path, index=False)

            schedules = load_cloudwalk_emissions(path)

        self.assertFalse(schedules[0].included)
        self.assertIn("Amortização não mapeada", schedules[0].exclusion_reason)

    def test_curated_cloudwalk_file_includes_mapped_senior_series(self):
        schedules = load_cloudwalk_emissions("data/regulatory_profiles/cloudwalk_cotas_emissoes_pagamentos.csv")
        included = [schedule for schedule in schedules if schedule.included]
        included_cnpjs = {schedule.cnpj for schedule in included}
        conventions = {(schedule.cnpj, schedule.classe): schedule.convention for schedule in included}

        self.assertGreaterEqual(len(included), 5)
        self.assertIn("57.609.282/0001-46", included_cnpjs)
        self.assertIn("60.356.171/0001-80", included_cnpjs)
        self.assertIn("62.393.679/0001-83", included_cnpjs)
        self.assertEqual("cumulative", conventions[("57.609.282/0001-46", "1ª série sênior")])

    def test_waterfall_consolidation(self):
        schedules = [
            FidcAmortizationSchedule(
                fund_name="FIDC A",
                cnpj="1",
                classe="Sênior",
                volume_emitido=1_000.0,
                saldo_atual=1_000.0,
                convention="incremental",
                schedule=[(date(2027, 1, 31), 300.0), (date(2027, 2, 28), 700.0)],
                included=True,
                exclusion_reason=None,
            ),
            FidcAmortizationSchedule(
                fund_name="FIDC B",
                cnpj="2",
                classe="Sênior",
                volume_emitido=500.0,
                saldo_atual=500.0,
                convention="incremental",
                schedule=[(date(2027, 2, 28), 500.0)],
                included=True,
                exclusion_reason=None,
            ),
        ]

        rows = build_waterfall_schedule(schedules, 100.0, {}, reference_date=date(2026, 5, 14))

        self.assertEqual([date(2027, 1, 31), date(2027, 2, 28)], [row.data for row in rows])
        self.assertEqual(1_200.0, rows[0].saldo_devedor_total)
        self.assertEqual(0.0, rows[1].saldo_devedor_total)
        self.assertEqual(1_200.0, rows[1].amortizacao_total)
        self.assertEqual(100.0, rows[1].posicao_liquida)

    def test_export_creates_files(self):
        schedule = FidcAmortizationSchedule(
            fund_name="FIDC A",
            cnpj="1",
            classe="Sênior",
            volume_emitido=1_000.0,
            saldo_atual=1_000.0,
            convention="incremental",
            schedule=[(date(2027, 1, 31), 1_000.0)],
            included=True,
            exclusion_reason=None,
        )
        rows = build_waterfall_schedule([schedule], 0.0, {}, reference_date=date(2026, 5, 14))

        with TemporaryDirectory() as tmp:
            paths = export_waterfall(rows, [schedule], tmp)

            for path in paths.values():
                self.assertTrue(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
