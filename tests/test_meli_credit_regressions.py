from __future__ import annotations

import json
import unittest

import pandas as pd

from services.meli_credit_monitor import (
    MeliMonitorOutputs,
    build_cohort_matrix,
    build_monitor_base,
)
from services.meli_credit_monitor_visuals import portfolio_growth_chart
from services.meli_credit_research import build_meli_research_outputs
from services.mercado_livre_dashboard import build_consolidated_monthly_base


class MeliCreditRegressionTest(unittest.TestCase):
    def test_calendar_lags_and_cohorts_do_not_jump_over_missing_months(self) -> None:
        monthly = pd.DataFrame(
            [
                _monitor_row("2026-01-01", carteira_ex360=1_000.0, carteira_a_vencer=100.0, atraso_61_90=1.0),
                _monitor_row("2026-02-01", carteira_ex360=1_100.0, carteira_a_vencer=200.0, atraso_61_90=2.0),
                _monitor_row("2026-04-01", carteira_ex360=1_200.0, carteira_a_vencer=400.0, atraso_61_90=30.0),
                _monitor_row("2026-05-01", carteira_ex360=1_300.0, carteira_a_vencer=500.0, atraso_61_90=20.0),
            ]
        )

        monitor = build_monitor_base(monthly)
        april = monitor.loc[monitor["competencia"].eq("04/2026")].iloc[0]
        may = monitor.loc[monitor["competencia"].eq("05/2026")].iloc[0]

        self.assertAlmostEqual(100.0, april["roll_61_90_m3_den"])
        self.assertAlmostEqual(200.0, may["roll_61_90_m3_den"])
        self.assertAlmostEqual(10.0, may["roll_61_90_m3_pct"])
        self.assertTrue(pd.isna(april["carteira_ex360_mom_pct"]))

        january_cohort = build_cohort_matrix(monitor)
        january_cohort = january_cohort[january_cohort["cohort"].eq("Jan-26")].set_index("mes_ciclo")
        self.assertAlmostEqual(30.0, january_cohort.loc["M3", "valor_pct"])
        self.assertNotIn("M2", january_cohort.index)

    def test_incomplete_universe_is_excluded_from_cohorts_research_and_charts(self) -> None:
        complete = _monitor_row(
            "2026-01-01",
            carteira_ex360=1_111.0,
            carteira_a_vencer=200.0,
            atraso_61_90=3.0,
        )
        incomplete = _monitor_row(
            "2026-02-01",
            carteira_ex360=987_654_321.0,
            carteira_a_vencer=200.0,
            atraso_61_90=3.0,
        )
        complete.update({"funds_expected_count": 2, "funds_present_count": 2})
        incomplete.update({"funds_expected_count": 2, "funds_present_count": 1})
        monitor = build_monitor_base(pd.DataFrame([complete, incomplete]))

        self.assertEqual([True, False], monitor["universe_complete"].tolist())
        cohorts = build_cohort_matrix(monitor)
        self.assertTrue(cohorts.empty)

        outputs = MeliMonitorOutputs(
            consolidated_monitor=monitor,
            fund_monitor={},
            consolidated_cohorts=cohorts,
            fund_cohorts={},
            audit_table=pd.DataFrame(),
            pdf_reconciliation=pd.DataFrame(),
            warnings=[],
        )
        research = build_meli_research_outputs(outputs)
        for frame in (
            research.roll_seasonality,
            research.npl_research_table,
            research.portfolio_duration_table,
        ):
            self.assertEqual({"01/2026"}, set(frame["competencia"].dropna()))

        chart_payload = json.dumps(portfolio_growth_chart(monitor).to_dict(), ensure_ascii=False)
        self.assertIn("jan/26", chart_payload)
        self.assertNotIn("fev/26", chart_payload)
        self.assertNotIn("987654321", chart_payload)

    def test_consolidated_duration_is_invalid_when_positive_balance_has_no_numerator(self) -> None:
        fund_a = _consolidation_row(
            cnpj="1",
            carteira_bruta=100.0,
            pdd_total=10.0,
            duration_total_saldo=100.0,
            duration_weighted_days=600.0,
        )
        fund_b = _consolidation_row(
            cnpj="2",
            carteira_bruta=300.0,
            pdd_total=20.0,
            duration_total_saldo=300.0,
            duration_weighted_days=None,
        )

        consolidated = build_consolidated_monthly_base(
            portfolio_name="Carteira",
            fund_monthly_frames={"1": fund_a, "2": fund_b},
        )
        row = consolidated.iloc[0]

        self.assertFalse(bool(row["duration_universe_complete"]))
        for column in (
            "duration_total_saldo",
            "duration_weighted_days",
            "duration_days",
            "duration_months",
        ):
            self.assertTrue(pd.isna(row[column]), column)

    def test_consolidated_ratio_uses_sum_of_numerators_over_sum_of_denominators(self) -> None:
        fund_a = _consolidation_row(
            cnpj="1",
            carteira_bruta=100.0,
            pdd_total=90.0,
            duration_total_saldo=100.0,
            duration_weighted_days=600.0,
        )
        fund_b = _consolidation_row(
            cnpj="2",
            carteira_bruta=900.0,
            pdd_total=0.0,
            duration_total_saldo=900.0,
            duration_weighted_days=10_800.0,
        )

        consolidated = build_consolidated_monthly_base(
            portfolio_name="Carteira",
            fund_monthly_frames={"1": fund_a, "2": fund_b},
        )
        row = consolidated.iloc[0]

        self.assertAlmostEqual(90.0, row["pdd_total"])
        self.assertAlmostEqual(1_000.0, row["carteira_bruta"])
        self.assertAlmostEqual(9.0, row["pdd_carteira_bruta_pct"])
        self.assertNotAlmostEqual((90.0 + 0.0) / 2.0, row["pdd_carteira_bruta_pct"])


def _monitor_row(
    date: str,
    *,
    carteira_ex360: float,
    carteira_a_vencer: float,
    atraso_61_90: float,
) -> dict[str, object]:
    competencia_dt = pd.Timestamp(date)
    return {
        "fund_name": "FIDC teste",
        "cnpj": "00000000000000",
        "competencia": competencia_dt.strftime("%m/%Y"),
        "competencia_dt": competencia_dt,
        "carteira_ex360": carteira_ex360,
        "carteira_bruta": carteira_ex360,
        "carteira_em_dia": 100.0,
        "carteira_a_vencer": carteira_a_vencer,
        "atraso_ate30": 10.0,
        "atraso_31_60": 20.0,
        "atraso_61_90": atraso_61_90,
        "atraso_91_120": 4.0,
        "atraso_121_150": 5.0,
        "atraso_151_180": 6.0,
        "atraso_181_360": 7.0,
        "prazo_venc_30": 100.0,
        "prazo_venc_31_60": 100.0,
        "prazo_venc_61_90": 0.0,
        "prazo_venc_91_120": 0.0,
        "prazo_venc_121_150": 0.0,
        "prazo_venc_151_180": 0.0,
        "prazo_venc_181_360": 0.0,
        "prazo_venc_361_720": 0.0,
        "prazo_venc_721_1080": 0.0,
        "prazo_venc_1080": 0.0,
        "pdd_ex360": 50.0,
        "npl_over90_ex360": 25.0,
        "duration_months": 6.0,
        "duration_total_saldo": 100.0,
        "duration_weighted_days": 18_262.5,
    }


def _consolidation_row(
    *,
    cnpj: str,
    carteira_bruta: float,
    pdd_total: float,
    duration_total_saldo: float,
    duration_weighted_days: float | None,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "fund_name": f"FIDC {cnpj}",
                "cnpj": cnpj,
                "competencia": "01/2026",
                "competencia_dt": pd.Timestamp("2026-01-01"),
                "carteira_bruta": carteira_bruta,
                "pdd_total": pdd_total,
                "duration_total_saldo": duration_total_saldo,
                "duration_weighted_days": duration_weighted_days,
            }
        ]
    )


if __name__ == "__main__":
    unittest.main()
