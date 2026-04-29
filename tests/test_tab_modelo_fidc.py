from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from data_loader import load_model_inputs
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

    def test_model_tooltip_html_exposes_explanation_for_css_and_accessibility(self) -> None:
        html = tab_modelo_fidc._model_tooltip_html('Duration "econômica" da SEN')

        self.assertIn('data-tooltip="Duration &quot;econômica&quot; da SEN"', html)
        self.assertIn('title="Duration &quot;econômica&quot; da SEN"', html)
        self.assertIn('aria-label="Duration &quot;econômica&quot; da SEN"', html)
        self.assertIn('tabindex="0"', html)

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
        self.assertIn("Metodologias de crédito, NPL e provisão", markdown)
        self.assertIn("provisao_minima = estoque_npl90_t", markdown)
        self.assertIn("Migração por faixas de atraso", markdown)
        self.assertIn("ECL forward-looking", markdown)
        self.assertIn("perda_calibrada_anual_equivalente", markdown)
        self.assertIn("Backlog Fase 2", markdown)
        self.assertIn("PMT SEN = juros SEN + principal SEN programado", markdown)
        self.assertIn("SUB residual = PL FIDC - PL SEN - PL MEZZ", markdown)
        self.assertIn("taxa_selic_periodo = (1 + selic_aa_do_ano)", markdown)
        self.assertIn("rendimento_caixa_selic", markdown)

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
            lgd=0.8,
        )

        metrics = tab_modelo_fidc._build_revolvency_metrics(
            premissas=premissas,
            zero_default_results=[Result()],
            portfolio_mode=tab_modelo_fidc.PORTFOLIO_MODE_REVOLVING,
            calibrated_loss_cycle=0.05,
        )

        self.assertEqual(6.0, metrics.giro_estimado)
        self.assertEqual(4_500_000_000.0, metrics.carteira_total_originada)
        self.assertAlmostEqual(2_400_000_000.0 / 4_500_000_000.0, metrics.colchao_sem_perdas_sobre_originacao)
        self.assertEqual(750_000_000.0, metrics.ead_maximo)
        self.assertEqual(750_000_000.0, metrics.ead_medio_ponderado)
        self.assertAlmostEqual((1.05**2) - 1.0, metrics.perda_ciclo_calibrada_anual_equivalente)
        self.assertAlmostEqual(0.04, metrics.perda_ciclo_calibrada_pos_lgd)

    def test_calibrated_loss_cycle_solver_finds_loss_that_exhausts_sub(self) -> None:
        dates = [pd.Timestamp(2026, 1, 1) + pd.DateOffset(months=month) for month in range(13)]
        datas = [date.to_pydatetime() for date in dates]
        premissas = tab_modelo_fidc.Premissas(
            volume=1_000.0,
            tx_cessao_am=0.0,
            tx_cessao_cdi_aa=None,
            custo_adm_aa=0.0,
            custo_min=0.0,
            inadimplencia=0.0,
            proporcao_senior=0.0,
            taxa_senior=0.0,
            proporcao_mezz=0.0,
            taxa_mezz=0.0,
            proporcao_subordinada=1.0,
            tipo_taxa_senior=tab_modelo_fidc.RATE_MODE_PRE,
            tipo_taxa_mezz=tab_modelo_fidc.RATE_MODE_PRE,
            prazo_fidc_anos=1.0,
            prazo_medio_recebiveis_meses=6.0,
            carteira_revolvente=True,
            modelo_credito=tab_modelo_fidc.CREDIT_MODEL_NPL90,
            npl90_lag_meses=0,
            cobertura_minima_npl90=1.0,
            lgd=1.0,
        )

        perda_ciclo, exceeded = tab_modelo_fidc._solve_calibrated_loss_cycle(
            datas=datas,
            feriados=[],
            curva_du=[1.0, 2000.0],
            curva_taxa_aa=[0.0, 0.0],
            premissas=premissas,
            interpolation_method=tab_modelo_fidc.INTERPOLATION_METHOD_FLAT_FORWARD_252,
        )

        self.assertFalse(exceeded)
        self.assertIsNotNone(perda_ciclo)
        self.assertGreater(perda_ciclo, 0.0)
        self.assertLess(perda_ciclo, 1.0)
        final_sub = tab_modelo_fidc._final_sub_for_loss_cycle(
            datas=datas,
            feriados=[],
            curva_du=[1.0, 2000.0],
            curva_taxa_aa=[0.0, 0.0],
            premissas=premissas,
            interpolation_method=tab_modelo_fidc.INTERPOLATION_METHOD_FLAT_FORWARD_252,
            perda_ciclo=perda_ciclo,
        )
        self.assertAlmostEqual(0.0, final_sub, delta=1.0)

    def test_reference_monthly_scenario_uses_additive_cdi_spread_outputs(self) -> None:
        inputs = load_model_inputs("model_data.json")
        datas = tab_modelo_fidc._build_monthly_dates(inputs.datas[0], 3.0)
        selected_calendar = tab_modelo_fidc._selected_calendar(
            inputs,
            tab_modelo_fidc.CALENDAR_SOURCE_B3_PROJECTED,
            datas=datas,
        )
        selected_curve = tab_modelo_fidc._selected_curve_from_snapshot(inputs)
        premissas = tab_modelo_fidc.Premissas(
            volume=750_000_000.0,
            tx_cessao_am=0.04,
            tx_cessao_cdi_aa=None,
            custo_adm_aa=0.0035,
            custo_min=20_000.0,
            inadimplencia=0.0,
            proporcao_senior=0.75,
            taxa_senior=0.0135,
            proporcao_mezz=0.15,
            taxa_mezz=0.05,
            proporcao_subordinada=0.10,
            tipo_taxa_senior=tab_modelo_fidc.RATE_MODE_POST_CDI,
            tipo_taxa_mezz=tab_modelo_fidc.RATE_MODE_POST_CDI,
            carteira_revolvente=True,
            prazo_fidc_anos=3.0,
            prazo_medio_recebiveis_meses=6.0,
            prazo_senior_anos=3.0,
            prazo_mezz_anos=3.0,
            amortizacao_senior=tab_modelo_fidc.AMORTIZATION_MODE_LINEAR,
            amortizacao_mezz=tab_modelo_fidc.AMORTIZATION_MODE_LINEAR,
            juros_senior=tab_modelo_fidc.INTEREST_PAYMENT_MODE_PERIODIC,
            juros_mezz=tab_modelo_fidc.INTEREST_PAYMENT_MODE_PERIODIC,
            inicio_amortizacao_senior_meses=30,
            inicio_amortizacao_mezz_meses=30,
            modelo_credito=tab_modelo_fidc.CREDIT_MODEL_NPL90,
            perda_ciclo=0.0,
            npl90_lag_meses=3,
            cobertura_minima_npl90=1.0,
            lgd=1.0,
        )

        periods = tab_modelo_fidc.build_flow(
            datas,
            selected_calendar.feriados,
            selected_curve.curva_du,
            selected_curve.curva_taxa_aa,
            premissas,
            interpolation_method=tab_modelo_fidc.INTERPOLATION_METHOD_FLAT_FORWARD_252,
        )
        kpis = tab_modelo_fidc.build_kpis(periods)
        loss_cycle, exceeded = tab_modelo_fidc._solve_calibrated_loss_cycle(
            datas=datas,
            feriados=selected_calendar.feriados,
            curva_du=selected_curve.curva_du,
            curva_taxa_aa=selected_curve.curva_taxa_aa,
            premissas=premissas,
            interpolation_method=tab_modelo_fidc.INTERPOLATION_METHOD_FLAT_FORWARD_252,
        )

        self.assertAlmostEqual(0.1481403471878306, periods[1].taxa_senior)
        self.assertAlmostEqual(0.18464034718783057, periods[1].taxa_mezz)
        self.assertAlmostEqual(0.15463403302424067, kpis.xirr_senior)
        self.assertAlmostEqual(0.19047218455885997, kpis.xirr_mezz)
        self.assertAlmostEqual(1_496_273_586.821506, periods[-1].pl_sub_jr, delta=1.0)
        self.assertFalse(exceeded)
        self.assertAlmostEqual(0.18585968017578125, loss_cycle)

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

    def test_time_protection_keeps_programmatic_denominator_when_actual_reinvestment_exists(self) -> None:
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
        self.assertAlmostEqual(166.66666666666666, protection.iloc[0]["nova_originacao_estimada"])
        self.assertAlmostEqual(166.66666666666666, protection.iloc[0]["nova_originacao_acumulada"])
        self.assertAlmostEqual(1_166.6666666666667, protection.iloc[0]["carteira_originada_acumulada"])
        self.assertAlmostEqual(220.0, protection.iloc[0]["nova_originacao_motor"])
        self.assertAlmostEqual(333.3333333333333, protection.iloc[1]["nova_originacao_acumulada"])
        self.assertAlmostEqual(1_333.3333333333333, protection.iloc[1]["carteira_originada_acumulada"])
        self.assertAlmostEqual(330.0, protection.iloc[1]["nova_originacao_motor"])

    def test_model_charts_are_filled_area_charts(self) -> None:
        frame = pd.DataFrame(
            {
                "indice": [0, 1],
                "data": pd.to_datetime(["2026-01-01", "2026-02-01"]),
                "pl_senior": [75.0, 65.0],
                "pl_mezz": [15.0, 10.0],
                "pl_sub_jr": [10.0, 25.0],
            }
        )
        chart_df = tab_modelo_fidc._build_balance_area_frame(frame)

        chart = tab_modelo_fidc._area_money_chart(chart_df)
        spec = chart.to_dict()

        self.assertEqual("area", spec["layer"][0]["mark"]["type"])
        self.assertEqual("line", spec["layer"][1]["mark"]["type"])
        self.assertEqual("Mês do FIDC", spec["layer"][0]["encoding"]["x"]["title"])
        self.assertEqual("stack_top_milhoes", spec["layer"][0]["encoding"]["y"]["field"])
        self.assertEqual("stack_base_milhoes", spec["layer"][0]["encoding"]["y2"]["field"])

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

    def test_balance_chart_uses_explicit_stacked_area_coordinates(self) -> None:
        frame = pd.DataFrame(
            {
                "indice": [0],
                "data": pd.to_datetime(["2026-01-01"]),
                "pl_senior": [75.0],
                "pl_mezz": [15.0],
                "pl_sub_jr": [10.0],
            }
        )

        chart_df = tab_modelo_fidc._build_balance_area_frame(frame)
        stacks = {
            row["classe"]: (row["stack_base"], row["stack_top"])
            for _, row in chart_df.iterrows()
        }

        self.assertEqual((0.0, 75.0), stacks["Sênior"])
        self.assertEqual((75.0, 90.0), stacks["MEZZ"])
        self.assertEqual((90.0, 100.0), stacks["Subordinada/SUB disponível"])

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

        self.assertIn("Proteção disponível (% carteira originada)", chart_df["serie"].tolist())
        self.assertIn("Proteção / subordinação", chart_df["eixo"].tolist())

    def test_loss_chart_uses_right_axis_for_protection_series(self) -> None:
        frame = pd.DataFrame(
            {
                "indice": [0, 1],
                "data": pd.to_datetime(["2026-01-01", "2026-02-01"]),
                "carteira": [100.0, 100.0],
                "pl_fidc": [100.0, 100.0],
                "pl_sub_jr": [20.0, 18.0],
                "perda_carteira_despesa": [0.0, 2.0],
            }
        )
        chart_df = tab_modelo_fidc._build_loss_area_frame(frame, volume=100.0)

        spec = tab_modelo_fidc._area_percent_chart(chart_df).to_dict()

        def has_right_axis(node) -> bool:
            if isinstance(node, dict):
                axis = node.get("axis")
                if isinstance(axis, dict) and axis.get("orient") == "right":
                    return True
                return any(has_right_axis(value) for value in node.values())
            if isinstance(node, list):
                return any(has_right_axis(value) for value in node)
            return False

        self.assertEqual("independent", spec["resolve"]["scale"]["y"])
        self.assertTrue(has_right_axis(spec))

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
                "nova_originacao_motor_formatada": ["R$ 11,00"],
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
