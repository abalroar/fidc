from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

import pandas as pd

from services.ime_period import build_custom_period
from services.monitoring_metrics import MonitoringTables
from services.portfolio_store import PortfolioFund, PortfolioRecord
from tabs.tab_fidc_monitoring import (
    _build_regulatory_monitoring_checks,
    render_portfolio_cockpit_snapshot,
    render_tab_fidc_monitoring,
)


class MonitoringTabReferenceCompetenciaTests(unittest.TestCase):
    def test_regulatory_monitoring_checks_use_loaded_ime_metrics(self) -> None:
        item = {
            "competencias": ["03/2026"],
            "tables": MonitoringTables(
                raw_variables_df=pd.DataFrame(
                    [
                        {
                            "id_cvm": "MERC_DERIVATIVO/VL_SOM_MERC_DERIVATIVO",
                            "03/2026": "0",
                        }
                    ]
                ),
                indicators_df=pd.DataFrame(
                    [
                        {"indicador": "Cotas Sub / PL %", "03/2026": "12.0"},
                        {"indicador": "Cotas SR / PL %", "03/2026": "80.0"},
                        {"indicador": "Dir Cred / PL", "03/2026": "0.72"},
                        {"indicador": "Vencidos Over 90 d / Crédito", "03/2026": "0.082"},
                        {"indicador": "PL (R$)", "03/2026": "1500000"},
                    ]
                ),
                aging_df=pd.DataFrame(),
                audit_df=pd.DataFrame(),
            ),
        }
        criteria_df = pd.DataFrame(
            [
                {"Critério": "Índice de Subordinação", "Limite/regra": "Cotas Subordinadas Juniores / PL >= 10%", "Monitorabilidade IME": "direto com validação"},
                {"Critério": "Alocação mínima regulatória", "Limite/regra": "Direitos Creditórios Elegíveis / PL >= 50%", "Monitorabilidade IME": "direto com ressalva"},
                {"Critério": "Derivativos", "Limite/regra": "Operações com derivativos vedadas", "Monitorabilidade IME": "direto agregado"},
                {"Critério": "PL mínimo operacional", "Limite/regra": "PL diário não inferior a R$ 1.000.000", "Monitorabilidade IME": "direto com ressalva"},
                {"Critério": "Relação Mínima", "Limite/regra": "PL / Cotas Sênior >= 105%", "Monitorabilidade IME": "direto com ressalva"},
                {"Critério": "Índice de Atraso Over 90", "Chave": "default_rate_evaluation_event", "Limite/regra": "Over 90 > 10,5%", "Monitorabilidade IME": "direto com ressalva"},
            ]
        )

        checks = _build_regulatory_monitoring_checks(item, criteria_df)

        self.assertEqual(["Proxy com ressalva — validação documental"] * 6, checks["Status"].tolist())
        self.assertEqual("12,00%", checks.loc[0, "Valor IME"])
        self.assertEqual("72,00%", checks.loc[1, "Valor IME"])
        self.assertEqual("R$ 0", checks.loc[2, "Valor IME"])
        self.assertEqual("R$ 1,5 MM", checks.loc[3, "Valor IME"])
        self.assertEqual("125,00%", checks.loc[4, "Valor IME"])
        self.assertEqual("8,20%", checks.loc[5, "Valor IME"])

    def test_partial_default_proxy_displays_value_without_contractual_status(self) -> None:
        item = {"competencias": ["03/2026"]}
        criteria = pd.DataFrame([{
            "Critério": "Índice de Perdas 90",
            "Chave": "default_rate_evaluation_event",
            "Limite/regra": "CCBs com parcela superior a 90 dias: máximo de 5% do face adquirido",
            "Métrica IME / proxy": "Over 90 / Crédito, somente como alerta preliminar",
            "Monitorabilidade IME": "parcial",
        }])
        for value, formatted in [(0.02, "2,00%"), (0.08, "8,00%")]:
            with self.subTest(value=value), patch("tabs.tab_fidc_monitoring._metric_numeric", return_value=value) as metric:
                checks = _build_regulatory_monitoring_checks(item, criteria)
            metric.assert_called_once_with(item, "Vencidos Over 90 d / Crédito", "03/2026")
            self.assertEqual(formatted, checks.loc[0, "Valor IME"])
            self.assertEqual("Proxy parcial — validação documental", checks.loc[0, "Status"])

    def test_documentary_criteria_do_not_read_ime_metrics(self) -> None:
        item = {"competencias": ["03/2026"]}
        criteria = pd.DataFrame([
            {"Critério": "Concentração", "Monitorabilidade IME": "nao_monitoravel"},
            {"Critério": "Subordinação sênior", "Chave": "subordination_ratio_min", "Monitorabilidade IME": "não usar via IME"},
        ])
        with (
            patch("tabs.tab_fidc_monitoring._metric_numeric") as metric,
            patch("tabs.tab_fidc_monitoring._raw_variable_numeric") as raw_metric,
        ):
            checks = _build_regulatory_monitoring_checks(item, criteria)
        metric.assert_not_called()
        raw_metric.assert_not_called()
        self.assertEqual(["Qualitativo — controle documental"] * 2, checks["Status"].tolist())
        self.assertEqual(["não comparável à regra via IME"] * 2, checks["Valor IME"].tolist())

    def test_validated_direct_criterion_keeps_contractual_status(self) -> None:
        item = {"competencias": ["03/2026"]}
        criteria = pd.DataFrame([{
            "Critério": "Alocação mínima",
            "Chave": "credit_rights_allocation_min",
            "Limite/regra": "Direitos creditórios / PL >= 50%",
            "Monitorabilidade IME": "direto validado",
        }])
        with patch("tabs.tab_fidc_monitoring._metric_numeric", return_value=0.72):
            checks = _build_regulatory_monitoring_checks(item, criteria)
        self.assertEqual("72,00%", checks.loc[0, "Valor IME"])
        self.assertEqual("OK", checks.loc[0, "Status"])

    def test_partial_subordination_does_not_use_junior_as_total_protection(self) -> None:
        item = {"competencias": ["03/2026"]}
        criteria = pd.DataFrame([{
            "Critério": "Subordinação sênior",
            "Chave": "subordination_ratio_min",
            "Limite/regra": "Mezanino + Júnior / PL >= 15%",
            "Monitorabilidade IME": "parcial",
        }])
        with patch("tabs.tab_fidc_monitoring._metric_numeric") as metric:
            checks = _build_regulatory_monitoring_checks(item, criteria)
        metric.assert_not_called()
        self.assertEqual("não comparável à regra via IME", checks.loc[0, "Valor IME"])
        self.assertEqual("Proxy parcial — validação documental", checks.loc[0, "Status"])

    def test_partial_reserve_displays_absolute_cash_without_pl_ratio(self) -> None:
        item = {"competencias": ["03/2026"]}
        criteria = pd.DataFrame([{
            "Critério": "Reserva de caixa",
            "Chave": "minimum_cash_ratio",
            "Limite/regra": "Três meses de despesas futuras estimadas",
            "Monitorabilidade IME": "parcial",
        }])
        with (
            patch("tabs.tab_fidc_monitoring._metric_numeric") as metric,
            patch("tabs.tab_fidc_monitoring._raw_variable_numeric", return_value=200000) as raw_metric,
        ):
            checks = _build_regulatory_monitoring_checks(item, criteria)
        metric.assert_not_called()
        raw_metric.assert_called_once_with(item, "APLIC_ATIVO/VL_DISPONIB", "03/2026")
        self.assertEqual("R$ 200,0 mil", checks.loc[0, "Valor IME"])
        self.assertEqual("Proxy parcial — validação documental", checks.loc[0, "Status"])

    def test_main_page_monitoring_mode_does_not_render_duplicate_cockpit(self) -> None:
        portfolio = PortfolioRecord(
            id="portfolio-1",
            name="Carteira Teste",
            funds=(PortfolioFund(cnpj="11111111000111", display_name="FIDC A"),),
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        period = build_custom_period(start_month=date(2026, 3, 1), end_month=date(2026, 3, 1))
        outputs = [
            {
                "cnpj": "11111111000111",
                "display_name": "FIDC A",
                "competencias": ["03/2026"],
                "tables": object(),
            }
        ]

        with (
            patch("tabs.tab_fidc_monitoring.st") as st_mock,
            patch("tabs.tab_fidc_monitoring._load_portfolio_monitoring", return_value=outputs),
            patch("tabs.tab_fidc_monitoring._render_cockpit_tab") as cockpit,
            patch("tabs.tab_fidc_monitoring._render_regulatory_base_tab") as regulatory,
        ):
            st_mock.session_state = {}

            render_tab_fidc_monitoring(
                period=period,
                selected_portfolio=portfolio,
                show_portfolio_selector=False,
                use_tabs=False,
            )

        cockpit.assert_not_called()
        regulatory.assert_called_once()
        markdown_values = [call.args[0] for call in st_mock.markdown.call_args_list if call.args]
        self.assertIn("### Base regulatória", markdown_values)
        self.assertNotIn("### Cockpit", markdown_values)

    def test_cockpit_snapshot_helper_preserves_standalone_cockpit_table(self) -> None:
        portfolio = PortfolioRecord(
            id="portfolio-1",
            name="Carteira Teste",
            funds=(PortfolioFund(cnpj="11111111000111", display_name="FIDC A"),),
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        period = build_custom_period(start_month=date(2026, 3, 1), end_month=date(2026, 3, 1))
        outputs = [
            {
                "cnpj": "11111111000111",
                "display_name": "FIDC A",
                "competencias": ["03/2026"],
                "tables": object(),
            }
        ]

        with (
            patch("tabs.tab_fidc_monitoring.st") as st_mock,
            patch("tabs.tab_fidc_monitoring._load_portfolio_monitoring", return_value=outputs),
            patch("tabs.tab_fidc_monitoring._render_cockpit_tab") as cockpit,
        ):
            st_mock.session_state = {}

            rendered = render_portfolio_cockpit_snapshot(period=period, selected_portfolio=portfolio)

        self.assertTrue(rendered)
        cockpit.assert_called_once_with(outputs)


if __name__ == "__main__":
    unittest.main()
