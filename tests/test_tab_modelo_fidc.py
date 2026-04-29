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

    def test_raw_inputs_are_formatted_after_submit_callback(self) -> None:
        self.assertEqual("4,00%", tab_modelo_fidc._format_raw_input_text("4", decimals=2, kind="percent"))
        self.assertEqual("R$ 4,00", tab_modelo_fidc._format_raw_input_text("4", decimals=2, kind="brl"))
        self.assertEqual("30", tab_modelo_fidc._format_raw_input_text("30", decimals=0, kind="number"))

    def test_requested_page_defaults_are_encoded(self) -> None:
        self.assertEqual(750_000_000.0, tab_modelo_fidc.DEFAULT_VOLUME_CARTEIRA)
        self.assertEqual(0.04, tab_modelo_fidc.DEFAULT_TX_CESSAO_AM)
        self.assertEqual(0.0, tab_modelo_fidc.DEFAULT_PERDA_ESPERADA_AM)
        self.assertEqual(0.0, tab_modelo_fidc.DEFAULT_PERDA_INESPERADA_AM)
        self.assertEqual(0.0, tab_modelo_fidc.DEFAULT_AGIO_AQUISICAO)
        self.assertEqual(0.0, tab_modelo_fidc.DEFAULT_EXCESSO_SPREAD_SENIOR_AM)
        self.assertEqual(0.75, tab_modelo_fidc.DEFAULT_PROP_SENIOR)
        self.assertEqual(0.15, tab_modelo_fidc.DEFAULT_PROP_MEZZ)
        self.assertEqual(0.10, tab_modelo_fidc.DEFAULT_PROP_SUB)
        self.assertEqual(0.0135, tab_modelo_fidc.DEFAULT_TAXA_SENIOR)
        self.assertEqual(0.05, tab_modelo_fidc.DEFAULT_TAXA_MEZZ)
        self.assertEqual(30.0, tab_modelo_fidc.DEFAULT_CARENCIA_PRINCIPAL_MESES)

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
            taxa_cessao_input_mode=tab_modelo_fidc.CESSION_INPUT_MONTHLY,
        )

        self.assertIn("trava de caixa está desligada", markdown)
        self.assertIn("perda_carteira = perda_esperada + perda_inesperada", markdown)
        self.assertIn("PMT SEN = juros SEN + principal SEN programado", markdown)
        self.assertIn("SUB residual = PL FIDC - PL SEN - PL MEZZ", markdown)

    def test_revolvency_metrics_compare_sub_final_to_originated_portfolio(self) -> None:
        class Result:
            pl_sub_jr = 2_400_000_000.0

        premissas = tab_modelo_fidc.Premissas(
            volume=750_000_000.0,
            tx_cessao_am=0.0,
            tx_cessao_cdi_aa=None,
            custo_adm_aa=0.0,
            custo_min=0.0,
            inadimplencia=0.0,
            proporcao_senior=0.75,
            taxa_senior=0.0,
            proporcao_mezz=0.15,
            taxa_mezz=0.0,
            proporcao_subordinada=0.10,
            prazo_fidc_anos=3.0,
            prazo_medio_recebiveis_meses=6.0,
        )

        metrics = tab_modelo_fidc._build_revolvency_metrics(
            premissas=premissas,
            zero_default_results=[Result()],
            portfolio_mode=tab_modelo_fidc.PORTFOLIO_MODE_REVOLVING,
        )

        self.assertEqual(6.0, metrics.giro_estimado)
        self.assertEqual(4_500_000_000.0, metrics.carteira_total_originada)
        self.assertAlmostEqual(2_400_000_000.0 / 4_500_000_000.0, metrics.perda_maxima_sobre_originacao)

    def test_time_protection_uses_monthly_revolving_origination(self) -> None:
        premissas = tab_modelo_fidc.Premissas(
            volume=750_000_000.0,
            tx_cessao_am=0.0,
            tx_cessao_cdi_aa=None,
            custo_adm_aa=0.0,
            custo_min=0.0,
            inadimplencia=0.0,
            proporcao_senior=0.75,
            taxa_senior=0.0,
            proporcao_mezz=0.15,
            taxa_mezz=0.0,
            proporcao_subordinada=0.10,
            prazo_fidc_anos=3.0,
            prazo_medio_recebiveis_meses=6.0,
        )
        frame = pd.DataFrame(
            {
                "indice": [0, 1, 6, 36],
                "data": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-07-01", "2029-01-01"]),
                "pl_sub_jr": [75_000_000.0, 75_000_000.0, 75_000_000.0, 75_000_000.0],
                "fluxo_remanescente_mezz": [0.0, 10_000_000.0, 20_000_000.0, 30_000_000.0],
            }
        )

        protection = tab_modelo_fidc._build_time_protection_frame(
            frame,
            premissas=premissas,
            portfolio_mode=tab_modelo_fidc.PORTFOLIO_MODE_REVOLVING,
            scenario_label="Cenário",
        )

        self.assertEqual([1, 6, 36], protection["indice"].tolist())
        self.assertAlmostEqual(750_000_000.0, protection.iloc[0]["carteira_inicial_considerada"])
        self.assertAlmostEqual(125_000_000.0, protection.iloc[0]["nova_originacao_estimada"])
        self.assertAlmostEqual(875_000_000.0, protection.iloc[0]["carteira_originada_acumulada"])
        self.assertAlmostEqual(1_500_000_000.0, protection.iloc[1]["carteira_originada_acumulada"])
        self.assertAlmostEqual(4_500_000_000.0, protection.iloc[2]["carteira_originada_acumulada"])
        self.assertAlmostEqual(10_000_000.0, protection.iloc[0]["residual_economico_fluxo"])
        self.assertAlmostEqual(75_000_000.0 / 875_000_000.0, protection.iloc[0]["perda_maxima_suportada"])
        self.assertAlmostEqual(0.05, protection.iloc[1]["perda_maxima_suportada"])

    def test_time_protection_denominator_includes_initial_portfolio_in_first_month(self) -> None:
        premissas = tab_modelo_fidc.Premissas(
            volume=1_000_000_000.0,
            tx_cessao_am=0.0,
            tx_cessao_cdi_aa=None,
            custo_adm_aa=0.0,
            custo_min=0.0,
            inadimplencia=0.0,
            proporcao_senior=0.90,
            taxa_senior=0.0,
            proporcao_mezz=0.0,
            taxa_mezz=0.0,
            proporcao_subordinada=0.10,
            prazo_fidc_anos=3.0,
            prazo_medio_recebiveis_meses=6.0,
        )
        frame = pd.DataFrame(
            {
                "indice": [1],
                "data": pd.to_datetime(["2026-02-01"]),
                "pl_sub_jr": [100_000_000.0],
                "fluxo_remanescente_mezz": [0.0],
            }
        )

        protection = tab_modelo_fidc._build_time_protection_frame(
            frame,
            premissas=premissas,
            portfolio_mode=tab_modelo_fidc.PORTFOLIO_MODE_REVOLVING,
            scenario_label="Cenário",
        )

        self.assertAlmostEqual(1_000_000_000.0, protection.iloc[0]["carteira_inicial_considerada"])
        self.assertAlmostEqual(166_666_666.66666666, protection.iloc[0]["nova_originacao_estimada"])
        self.assertAlmostEqual(1_166_666_666.6666667, protection.iloc[0]["carteira_originada_acumulada"])
        self.assertAlmostEqual(100_000_000.0 / 1_166_666_666.6666667, protection.iloc[0]["perda_maxima_suportada"])

    def test_time_protection_uses_actual_reinvested_origination_when_available(self) -> None:
        premissas = tab_modelo_fidc.Premissas(
            volume=1_000.0,
            tx_cessao_am=0.0,
            tx_cessao_cdi_aa=None,
            custo_adm_aa=0.0,
            custo_min=0.0,
            inadimplencia=0.0,
            proporcao_senior=0.90,
            taxa_senior=0.0,
            proporcao_mezz=0.0,
            taxa_mezz=0.0,
            proporcao_subordinada=0.10,
            prazo_fidc_anos=3.0,
            prazo_medio_recebiveis_meses=6.0,
        )
        frame = pd.DataFrame(
            {
                "indice": [0, 1, 2],
                "data": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]),
                "pl_sub_jr": [100.0, 120.0, 150.0],
                "nova_originacao": [0.0, 220.0, 330.0],
                "fluxo_remanescente_mezz": [0.0, 20.0, 30.0],
            }
        )

        protection = tab_modelo_fidc._build_time_protection_frame(
            frame,
            premissas=premissas,
            portfolio_mode=tab_modelo_fidc.PORTFOLIO_MODE_REVOLVING,
            scenario_label="Cenário",
        )

        self.assertEqual([1, 2], protection["indice"].tolist())
        self.assertAlmostEqual(220.0, protection.iloc[0]["nova_originacao_estimada"])
        self.assertAlmostEqual(220.0, protection.iloc[0]["nova_originacao_acumulada"])
        self.assertAlmostEqual(1_220.0, protection.iloc[0]["carteira_originada_acumulada"])
        self.assertAlmostEqual(550.0, protection.iloc[1]["nova_originacao_acumulada"])
        self.assertAlmostEqual(1_550.0, protection.iloc[1]["carteira_originada_acumulada"])

    def test_model_charts_are_filled_area_charts(self) -> None:
        chart_df = pd.DataFrame(
            {
                "indice": [0, 1],
                "data": pd.to_datetime(["2026-01-01", "2026-02-01"]),
                "classe": ["Sênior", "Sênior"],
                "valor_milhoes": [1.0, 0.9],
                "valor_formatado": ["R$ 1.000.000,00", "R$ 900.000,00"],
                "periodo": ["01/01/2026", "01/02/2026"],
                "mes_fidc": ["Mês 0", "Mês 1"],
            }
        )

        chart = tab_modelo_fidc._area_money_chart(chart_df)
        spec = chart.to_dict()

        self.assertEqual("area", spec["layer"][0]["mark"]["type"])
        self.assertEqual("line", spec["layer"][1]["mark"]["type"])
        self.assertEqual("Mês do FIDC", spec["layer"][0]["encoding"]["x"]["title"])

    def test_balance_chart_uses_current_sub_residual_and_separates_deficit(self) -> None:
        frame = pd.DataFrame(
            {
                "indice": [0],
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
                "indice": [0, 1],
                "data": pd.to_datetime(["2026-01-01", "2026-02-01"]),
                "carteira": [100.0, 100.0],
                "pl_fidc": [100.0, 1.0],
                "pl_sub_jr": [10.0, -80.0],
                "perda_carteira_despesa": [0.0, 10.0],
                "subordinacao_pct": [0.1, -80.0],
                "subordinacao_pct_modelo": [0.1, -8000.0],
            }
        )

        chart_df = tab_modelo_fidc._build_loss_area_frame(frame, volume=100.0)
        sub_series = chart_df[chart_df["serie"] == "Subordinação econômica disponível (SUB positiva/PL)"]

        self.assertEqual([10.0, 0.0], sub_series["valor_pct"].tolist())
        self.assertGreaterEqual(sub_series["valor_pct"].min(), 0.0)

    def test_loss_chart_can_include_time_protection_series(self) -> None:
        frame = pd.DataFrame(
            {
                "indice": [0, 1],
                "data": pd.to_datetime(["2026-01-01", "2026-02-01"]),
                "carteira": [100.0, 100.0],
                "pl_fidc": [100.0, 100.0],
                "pl_sub_jr": [10.0, 10.0],
                "perda_carteira_despesa": [0.0, 1.0],
            }
        )
        protection = pd.DataFrame(
            {
                "indice": [1],
                "data": pd.to_datetime(["2026-02-01"]),
                "perda_maxima_suportada": [0.2],
                "valor_pct": [20.0],
                "valor_formatado": ["20,00%"],
                "periodo": ["01/02/2026"],
                "mes_fidc": ["Mês 1"],
            }
        )

        chart_df = tab_modelo_fidc._build_loss_area_frame(frame, volume=100.0, protection_frame=protection)

        self.assertIn("Perda máxima suportada (% carteira originada)", chart_df["serie"].tolist())

    def test_time_protection_chart_is_line_chart(self) -> None:
        chart_df = pd.DataFrame(
            {
                "indice": [1],
                "data": pd.to_datetime(["2026-02-01"]),
                "serie": ["Cenário"],
                "valor_pct": [20.0],
                "valor_formatado": ["20,00%"],
                "carteira_inicial_formatada": ["R$ 40,00"],
                "nova_originacao_formatada": ["R$ 10,00"],
                "nova_originacao_acumulada_formatada": ["R$ 10,00"],
                "sub_formatada": ["R$ 10,00"],
                "originada_formatada": ["R$ 50,00"],
                "residual_fluxo_formatado": ["R$ 1,00"],
                "periodo": ["01/02/2026"],
                "mes_fidc": ["Mês 1"],
            }
        )

        spec = tab_modelo_fidc._protection_ratio_chart(chart_df).to_dict()

        self.assertEqual("line", spec["layer"][0]["mark"]["type"])


if __name__ == "__main__":
    unittest.main()
