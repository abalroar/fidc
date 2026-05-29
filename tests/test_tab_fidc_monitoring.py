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
    _portfolio_reference_competencia,
)


class MonitoringTabReferenceCompetenciaTests(unittest.TestCase):
    def test_reference_competencia_uses_latest_month_with_adequate_coverage(self) -> None:
        outputs = [
            {"tables": object(), "competencias": ["03/2026", "04/2026"]},
            {"tables": object(), "competencias": ["03/2026", "04/2026"]},
            {"tables": object(), "competencias": ["03/2026"]},
            {"tables": object(), "competencias": ["03/2026"]},
            {"tables": object(), "competencias": ["02/2026"]},
        ]

        competencia, eligible_count, total_count = _portfolio_reference_competencia(outputs)

        self.assertEqual("03/2026", competencia)
        self.assertEqual(4, eligible_count)
        self.assertEqual(5, total_count)

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

        self.assertEqual(["OK", "OK", "OK", "OK", "OK", "OK"], checks["Status"].tolist())
        self.assertEqual("12,00%", checks.loc[0, "Valor IME"])
        self.assertEqual("72,00%", checks.loc[1, "Valor IME"])
        self.assertEqual("125,00%", checks.loc[4, "Valor IME"])
        self.assertEqual("8,20%", checks.loc[5, "Valor IME"])

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
