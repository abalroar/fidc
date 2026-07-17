from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from services.cloudwalk_financial_cost import (
    CostRunConfig,
    FundingLine,
    _balance_at,
    _find_latest_cached_ime,
    _parse_line_amortizations,
    _parse_programmed_range_schedule,
    _period_funding_factor,
    _scheduled_cost,
    parse_cdi_plus_spread,
)
from services.fidc_model.b3_cdi import B3CdiMonthlyRate
from services.fidc_model.calendar import b3_market_holidays_for_dates


class CloudwalkFinancialCostTest(unittest.TestCase):
    def test_parse_cdi_plus_spread_from_curated_text(self):
        self.assertAlmostEqual(0.0135, parse_cdi_plus_spread("Taxa DI + 1,35% a.a."))
        self.assertAlmostEqual(0.0075, parse_cdi_plus_spread("CDI + 0,75% a.a."))
        self.assertIsNone(parse_cdi_plus_spread("Benchmark em apêndice; spread não localizado"))

    def test_programmed_range_schedule_uses_monthly_linear_dates(self):
        parsed = _parse_programmed_range_schedule(
            "Remuneração mensal; amortização programada de 08/06/2027 a 08/11/2027",
            600.0,
        )
        self.assertIsNotNone(parsed)
        convention, schedule, warnings = parsed or ("", [], ())

        self.assertEqual("linear_de_intervalo_documentado", convention)
        self.assertEqual(6, len(schedule))
        self.assertEqual(date(2027, 6, 8), schedule[0][0])
        self.assertEqual(date(2027, 11, 8), schedule[-1][0])
        self.assertAlmostEqual(100.0, schedule[0][1])
        self.assertTrue(warnings)

    def test_balance_and_scheduled_cost_reflect_amortization(self):
        line = FundingLine(
            fund_name="FIDC Teste",
            cnpj="00.000.000/0001-00",
            classe="1ª série sênior",
            tipo="Sênior",
            class_macro="senior",
            issue_date=date(2026, 1, 1),
            volume=1_000_000.0,
            spread_aa=0.01,
            spread_source="teste",
            remuneration="CDI + 1,00% a.a.",
            amortization_text="",
            amortization_convention="incremental",
            amortizations=((date(2026, 7, 1), 500_000.0),),
            source="teste",
            included=True,
        )
        config = CostRunConfig(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            snapshot_date=date(2026, 5, 14),
            cdi_aa=0.13,
            cdi_source="teste",
        )
        holidays = b3_market_holidays_for_dates([config.start_date, config.end_date])
        scheduled = _scheduled_cost(line, config, holidays)

        self.assertAlmostEqual(1_000_000.0, _balance_at(line, date(2026, 6, 30)))
        self.assertAlmostEqual(500_000.0, _balance_at(line, date(2026, 7, 1)))
        self.assertGreater(scheduled["gross_cost"], 0.0)
        self.assertLess(scheduled["average_balance"], 1_000_000.0)

    def test_amortization_convention_override_wins_over_text_hint(self):
        convention, schedule, warnings = _parse_line_amortizations(
            "Percentual do saldo de Cotas Sêniores a serem amortizadas: "
            "01/01/2025 50,00%; 01/02/2025 50,00%",
            1_000_000.0,
            amortization_convention="incremental",
        )

        self.assertEqual("incremental", convention)
        self.assertEqual((), warnings)
        self.assertAlmostEqual(1_000_000.0, sum(amount for _, amount in schedule))

    def test_period_funding_factor_uses_monthly_cdi_when_available(self):
        config = CostRunConfig(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            snapshot_date=date(2025, 1, 31),
            cdi_aa=0.50,
            cdi_source="fallback",
            monthly_cdi_rates=(
                B3CdiMonthlyRate(
                    mes="2025-01",
                    cdi_mensal=0.01,
                    dias_uteis=20,
                    data_inicio=date(2025, 1, 2),
                    data_fim=date(2025, 1, 31),
                    source="fixture",
                ),
            ),
        )

        factor = _period_funding_factor(
            config=config,
            spread_aa=0.0,
            current=date(2025, 1, 10),
            du=20,
            monthly_cdi={config.monthly_cdi_rates[0].mes: config.monthly_cdi_rates[0]},
        )

        self.assertAlmostEqual(0.01, factor)

    def test_ime_snapshot_cache_respects_as_of_month(self):
        with TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir) / "fixture"
            cache_dir.mkdir()
            (cache_dir / "informes_wide.csv").write_text("tag_path,05/2025,06/2026\nPL,1,2\n", encoding="utf-8")
            (cache_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "cnpj_fundo": "08.417.544/0001-65",
                        "competencias": ["05/2025", "06/2026"],
                        "files": {"wide_csv_path": "informes_wide.csv"},
                    }
                ),
                encoding="utf-8",
            )

            cached = _find_latest_cached_ime(
                "08417544000165",
                Path(tmp_dir),
                as_of_date=date(2025, 12, 31),
            )

        self.assertIsNotNone(cached)
        self.assertEqual("05/2025", cached["competencia"])


if __name__ == "__main__":
    unittest.main()
