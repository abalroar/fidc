from __future__ import annotations

from io import BytesIO
import json
import unittest
import zipfile

import pandas as pd

from services.meli_credit_monitor import (
    MeliMonitorOutputs,
    build_cohort_matrix,
    build_meli_methodology_table,
    build_monitor_base,
    build_pdf_reconciliation_table,
)
from services.meli_credit_monitor_ppt_export import build_dashboard_meli_pptx_bytes
from services.meli_credit_monitor_visuals import cohort_chart, portfolio_growth_chart, roll_rates_chart
from services.mercado_livre_dashboard import build_consolidated_monthly_base


class MeliCreditMonitorTest(unittest.TestCase):
    def test_roll_rates_use_lagged_current_maturity_denominators(self) -> None:
        monthly = _sample_monthly(month_count=7)
        monitor = build_monitor_base(monthly)

        self.assertAlmostEqual(2.5, monitor.loc[3, "roll_61_90_m3_pct"])
        self.assertAlmostEqual(3.0, monitor.loc[6, "roll_151_180_m6_pct"])
        self.assertAlmostEqual(200.0, monitor.loc[3, "roll_61_90_m3_den"])
        self.assertAlmostEqual(200.0, monitor.loc[6, "roll_151_180_m6_den"])

    def test_roll_rates_derive_current_maturity_when_missing(self) -> None:
        monthly = _sample_monthly(month_count=7).drop(columns=["carteira_a_vencer"])
        monitor = build_monitor_base(monthly)

        self.assertAlmostEqual(200.0, monitor.loc[0, "carteira_a_vencer"])
        self.assertAlmostEqual(2.5, monitor.loc[3, "roll_61_90_m3_pct"])

    def test_cohort_matrix_uses_due_30_base_and_future_buckets(self) -> None:
        monthly = _sample_monthly(month_count=7)
        cohort = build_cohort_matrix(build_monitor_base(monthly))
        jan = cohort[cohort["cohort"] == "Jan-26"].set_index("mes_ciclo")

        self.assertAlmostEqual(1.0, jan.loc["M1", "valor_pct"])
        self.assertAlmostEqual(2.0, jan.loc["M2", "valor_pct"])
        self.assertAlmostEqual(5.0, jan.loc["M3", "valor_pct"])
        self.assertAlmostEqual(6.0, jan.loc["M6", "valor_pct"])
        self.assertNotIn("01/2026", set(cohort["cohort"]))
        jul_cohort = build_cohort_matrix(build_monitor_base(_sample_monthly(month_count=2, start="2025-07-01")))
        self.assertIn("Jul-25", set(jul_cohort["cohort"]))

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

    def test_pdf_reconciliation_uses_november_2025_targets(self) -> None:
        monthly = _sample_monthly(month_count=1, start="2025-11-01")
        monthly.loc[0, "carteira_ex360"] = 7_141_000_000.0
        monthly.loc[0, "atraso_ate30"] = 266_000_000.0
        monthly.loc[0, "atraso_31_60"] = 184_000_000.0
        monthly.loc[0, "atraso_61_90"] = 150_000_000.0
        monthly.loc[0, "atraso_91_120"] = 370_000_000.0
        monthly.loc[0, "atraso_121_150"] = 0.0
        monthly.loc[0, "atraso_151_180"] = 0.0
        monthly.loc[0, "atraso_181_360"] = 642_000_000.0
        monthly.loc[0, "duration_months"] = 7.9
        monitor = build_monitor_base(monthly)

        reconciliation = build_pdf_reconciliation_table(monitor)
        npl_1_90 = reconciliation[reconciliation["Métrica"].eq("NPL 1-90d")].iloc[0]
        npl_1_360_pct = reconciliation[reconciliation["Métrica"].eq("NPL 1-360d / carteira ex-360")].iloc[0]
        no_pdf_target = reconciliation[reconciliation["Métrica"].eq("PL total")].iloc[0]

        self.assertAlmostEqual(600_000_000.0, npl_1_90["Valor app"])
        self.assertAlmostEqual(22.6, npl_1_360_pct["Valor PDF"])
        self.assertEqual("Sem alvo no PDF.", no_pdf_target["Status"])

    def test_methodology_table_documents_formula_sources(self) -> None:
        methodology = build_meli_methodology_table()

        roll = methodology[methodology["Indicador"].eq("Roll 61-90 / carteira a vencer M-3")].iloc[0]

        self.assertIn("carteira_a_vencer_t-3", roll["Fórmula"])
        self.assertIn("Fonte / coluna", methodology.columns)

    def test_dashboard_meli_charts_include_final_labels(self) -> None:
        monitor = build_monitor_base(_sample_monthly(month_count=7))

        roll_payload = json.dumps(roll_rates_chart(monitor).to_dict(), ensure_ascii=False)
        growth_payload = json.dumps(portfolio_growth_chart(monitor).to_dict(), ensure_ascii=False)

        self.assertIn("mark", roll_payload)
        self.assertIn("text", roll_payload)
        self.assertIn("3,0%", roll_payload)
        self.assertIn("Carteira ex-360", growth_payload)
        self.assertIn("text", growth_payload)

    def test_dashboard_meli_cohort_chart_uses_chronological_labels_and_gray_dashes(self) -> None:
        monitor = build_monitor_base(_sample_monthly(month_count=9))
        cohorts = build_cohort_matrix(monitor)

        payload = json.dumps(cohort_chart(cohorts).to_dict(), ensure_ascii=False)

        self.assertIn("Jan-26", payload)
        self.assertNotIn("01/2026", payload)
        self.assertIn("strokeDash", payload)
        self.assertIn("#000000", payload)

    def test_dashboard_meli_pptx_export_is_valid_zip(self) -> None:
        monitor = build_monitor_base(_sample_monthly(month_count=7))
        cohorts = build_cohort_matrix(monitor)
        outputs = MeliMonitorOutputs(
            consolidated_monitor=monitor,
            fund_monitor={"00000000000000": monitor},
            consolidated_cohorts=cohorts,
            fund_cohorts={"00000000000000": cohorts},
            audit_table=pd.DataFrame(),
            pdf_reconciliation=pd.DataFrame(),
            warnings=[],
        )

        pptx_bytes = build_dashboard_meli_pptx_bytes(outputs)

        self.assertTrue(pptx_bytes.startswith(b"PK"))
        self.assertTrue(zipfile.is_zipfile(BytesIO(pptx_bytes)))
        with zipfile.ZipFile(BytesIO(pptx_bytes)) as archive:
            names = archive.namelist()
        self.assertTrue(any(name.startswith("ppt/charts/chart") for name in names))


def _sample_monthly(*, month_count: int, start: str = "2026-01-01") -> pd.DataFrame:
    rows = []
    start_ts = pd.Timestamp(start)
    for idx in range(month_count):
        ts = start_ts + pd.DateOffset(months=idx)
        rows.append(
            {
                "fund_name": "Mercado Crédito",
                "cnpj": "00000000000000",
                "competencia": f"{int(ts.month):02d}/{int(ts.year)}",
                "competencia_dt": ts,
                "carteira_ex360": 1_000.0,
                "carteira_bruta": 1_000.0,
                "carteira_em_dia": 100.0,
                "carteira_a_vencer": 200.0,
                "atraso_ate30": 1.0,
                "atraso_31_60": 2.0,
                "atraso_61_90": 5.0 if idx == 3 else 3.0,
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
            }
        )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    unittest.main()
