from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from tabs import tab_modelo_fidc


class TabModeloFidcTests(unittest.TestCase):
    def test_brl_input_value_uses_brazilian_currency_format(self) -> None:
        self.assertEqual("R$ 125.000.000,00", tab_modelo_fidc._format_brl_input_value(125_000_000.0))

    def test_percent_input_value_uses_visible_percent_suffix(self) -> None:
        self.assertEqual("70,0%", tab_modelo_fidc._format_percent_input_value(70.0, decimals=1))
        self.assertEqual("15,22%", tab_modelo_fidc._format_percent_input_value(15.22, decimals=2))

    def test_parse_br_number_accepts_currency_and_percent_suffixes(self) -> None:
        self.assertEqual(1_234_567.89, tab_modelo_fidc._parse_br_number("R$ 1.234.567,89", field_name="x"))
        self.assertEqual(15.22, tab_modelo_fidc._parse_br_number("15,22%", field_name="x"))

    def test_reference_audit_documents_key_workbook_differences(self) -> None:
        selected_curve = tab_modelo_fidc._SelectedCurve(
            source_label=tab_modelo_fidc.CURVE_SOURCE_B3_LATEST,
            curve_code="PRE",
            base_date=date(2026, 4, 27),
            curva_du=(1.0, 21.0),
            curva_taxa_aa=(0.13, 0.14),
            source_url="https://example.test/TS260427.ex_",
            retrieved_label="28/04/2026 19:00:00 UTC",
            content_sha256="abc123",
            point_count=2,
            first_du=1,
            last_du=21,
        )
        selected_calendar = tab_modelo_fidc._SelectedCalendar(
            source_label=tab_modelo_fidc.CALENDAR_SOURCE_B3_OFFICIAL,
            feriados=(date(2026, 1, 1),),
            holiday_count=1,
            first_holiday=date(2026, 1, 1),
            last_holiday=date(2026, 1, 1),
            official_years=(2026,),
            projected_years=(2027,),
        )

        audit_df = tab_modelo_fidc._build_reference_audit_dataframe(
            selected_curve=selected_curve,
            selected_calendar=selected_calendar,
            interpolation_label=tab_modelo_fidc.INTERPOLATION_LABEL_B3,
            taxa_cessao_base="% a.a. base 252 dias úteis",
        )

        temas = set(audit_df["Tema"].tolist())
        self.assertIn("Taxa de cessão", temas)
        self.assertIn("Cota SUB", temas)
        self.assertIn("Curva de juros", temas)
        self.assertIn("Paridade preservada na tabela; visualização corrigida", audit_df["Status"].tolist())

    def test_workbook_mechanics_expander_explains_cash_lock_and_sheet_formulas(self) -> None:
        selected_curve = tab_modelo_fidc._SelectedCurve(
            source_label=tab_modelo_fidc.CURVE_SOURCE_B3_LATEST,
            curve_code="PRE",
            base_date=date(2026, 4, 27),
            curva_du=(1.0, 21.0),
            curva_taxa_aa=(0.13, 0.14),
            source_url="https://example.test/TS260427.ex_",
            retrieved_label="28/04/2026 19:00:00 UTC",
            content_sha256="abc123",
            point_count=2,
            first_du=1,
            last_du=21,
        )
        selected_calendar = tab_modelo_fidc._SelectedCalendar(
            source_label=tab_modelo_fidc.CALENDAR_SOURCE_B3_OFFICIAL,
            feriados=(date(2026, 1, 1),),
            holiday_count=1,
            first_holiday=date(2026, 1, 1),
            last_holiday=date(2026, 1, 1),
            official_years=(2026,),
            projected_years=(2027,),
        )

        markdown = tab_modelo_fidc._build_workbook_mechanics_markdown(
            selected_curve=selected_curve,
            selected_calendar=selected_calendar,
            interpolation_label=tab_modelo_fidc.INTERPOLATION_LABEL_B3,
            taxa_cessao_base="% a.m.",
        )

        self.assertIn("trava de caixa está desligada", markdown)
        self.assertIn("inadimplencia_periodo = carteira * (inadimplencia * delta_DC / 100)", markdown)
        self.assertIn("PMT SEN = juros SEN + principal SEN programado", markdown)
        self.assertIn("SUB residual = PL FIDC - PL SEN - PL MES", markdown)

    def test_model_charts_are_filled_area_charts(self) -> None:
        chart_df = pd.DataFrame(
            {
                "data": pd.to_datetime(["2026-01-01", "2026-02-01"]),
                "classe": ["Sênior", "Sênior"],
                "valor_milhoes": [1.0, 0.9],
                "valor_formatado": ["R$ 1.000.000,00", "R$ 900.000,00"],
                "periodo": ["01/01/2026", "01/02/2026"],
            }
        )

        chart = tab_modelo_fidc._area_money_chart(chart_df)
        spec = chart.to_dict()

        self.assertEqual("area", spec["layer"][0]["mark"]["type"])
        self.assertEqual("line", spec["layer"][1]["mark"]["type"])

    def test_balance_chart_uses_current_sub_residual_and_separates_deficit(self) -> None:
        frame = pd.DataFrame(
            {
                "data": pd.to_datetime(["2026-01-01"]),
                "pl_senior": [75.0],
                "pl_mezz": [15.0],
                "pl_sub_jr": [-12.0],
                "pl_sub_jr_modelo": [-80.0],
            }
        )

        chart_df = tab_modelo_fidc._build_balance_area_frame(frame)
        values = dict(zip(chart_df["classe"], chart_df["valor"]))

        self.assertEqual(0.0, values["Subordinada/SUB disponível"])
        self.assertEqual(-12.0, values["Déficit econômico"])
        self.assertNotIn(-80.0, values.values())

    def test_loss_chart_uses_available_subordination_not_shifted_workbook_ratio(self) -> None:
        frame = pd.DataFrame(
            {
                "data": pd.to_datetime(["2026-01-01", "2026-02-01"]),
                "carteira": [100.0, 100.0],
                "pl_fidc": [100.0, 1.0],
                "pl_sub_jr": [10.0, -80.0],
                "inadimplencia_despesa": [0.0, 10.0],
                "subordinacao_pct": [0.1, -80.0],
                "subordinacao_pct_modelo": [0.1, -8000.0],
            }
        )

        chart_df = tab_modelo_fidc._build_loss_area_frame(frame, volume=100.0)
        sub_series = chart_df[chart_df["serie"] == "Subordinação econômica disponível (SUB positiva/PL)"]

        self.assertEqual([10.0, 0.0], sub_series["valor_pct"].tolist())
        self.assertGreaterEqual(sub_series["valor_pct"].min(), 0.0)


if __name__ == "__main__":
    unittest.main()
