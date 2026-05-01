from __future__ import annotations

import unittest

import pandas as pd

from services.meli_credit_monitor import build_cohort_matrix, build_monitor_base
from services.mercado_livre_dashboard import build_consolidated_monthly_base


class MeliCreditMonitorTest(unittest.TestCase):
    def test_roll_rates_use_lagged_current_portfolio_denominators(self) -> None:
        monthly = _sample_monthly(month_count=7)
        monitor = build_monitor_base(monthly)

        self.assertAlmostEqual(5.0, monitor.loc[3, "roll_61_90_m3_pct"])
        self.assertAlmostEqual(6.0, monitor.loc[6, "roll_151_180_m6_pct"])

    def test_cohort_matrix_uses_due_30_base_and_future_buckets(self) -> None:
        monthly = _sample_monthly(month_count=7)
        cohort = build_cohort_matrix(build_monitor_base(monthly))
        jan = cohort[cohort["cohort"] == "01/2026"].set_index("mes_ciclo")

        self.assertAlmostEqual(1.0, jan.loc["M1", "valor_pct"])
        self.assertAlmostEqual(2.0, jan.loc["M2", "valor_pct"])
        self.assertAlmostEqual(5.0, jan.loc["M3", "valor_pct"])
        self.assertAlmostEqual(6.0, jan.loc["M6", "valor_pct"])

    def test_consolidated_duration_is_weighted_by_maturity_balance(self) -> None:
        frame_a = pd.DataFrame(
            [
                {
                    "fund_name": "A",
                    "cnpj": "1",
                    "competencia": "01/2026",
                    "competencia_dt": pd.Timestamp("2026-01-01"),
                    "duration_total_saldo": 100.0,
                    "duration_weighted_days": 600.0,
                }
            ]
        )
        frame_b = pd.DataFrame(
            [
                {
                    "fund_name": "B",
                    "cnpj": "2",
                    "competencia": "01/2026",
                    "competencia_dt": pd.Timestamp("2026-01-01"),
                    "duration_total_saldo": 300.0,
                    "duration_weighted_days": 3600.0,
                }
            ]
        )

        consolidated = build_consolidated_monthly_base(
            portfolio_name="Carteira",
            fund_monthly_frames={"1": frame_a, "2": frame_b},
        )

        self.assertAlmostEqual(10.5, consolidated.loc[0, "duration_days"])
        self.assertAlmostEqual(10.5 / 30.4375, consolidated.loc[0, "duration_months"])


def _sample_monthly(*, month_count: int) -> pd.DataFrame:
    rows = []
    for idx in range(month_count):
        ts = pd.Timestamp(year=2026, month=idx + 1, day=1)
        rows.append(
            {
                "fund_name": "Mercado Crédito",
                "cnpj": "00000000000000",
                "competencia": f"{idx + 1:02d}/2026",
                "competencia_dt": ts,
                "carteira_ex360": 1_000.0,
                "carteira_bruta": 1_000.0,
                "carteira_em_dia": 100.0,
                "atraso_ate30": 1.0,
                "atraso_31_60": 2.0,
                "atraso_61_90": 5.0 if idx == 3 else 3.0,
                "atraso_91_120": 4.0,
                "atraso_121_150": 5.0,
                "atraso_151_180": 6.0,
                "atraso_181_360": 7.0,
                "prazo_venc_30": 100.0,
                "pdd_ex360": 50.0,
                "npl_over90_ex360": 25.0,
                "duration_months": 6.0,
            }
        )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    unittest.main()
