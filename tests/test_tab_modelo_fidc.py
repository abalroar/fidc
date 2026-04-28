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
        self.assertIn("Diferença intencional documentada", audit_df["Status"].tolist())

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


if __name__ == "__main__":
    unittest.main()
