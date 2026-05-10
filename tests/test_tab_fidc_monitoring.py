from __future__ import annotations

import unittest

import pandas as pd

from services.monitoring_metrics import MonitoringTables
from tabs.tab_fidc_monitoring import _build_regulatory_monitoring_checks, _portfolio_reference_competencia


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
                        {"indicador": "Dir Cred / PL", "03/2026": "0.72"},
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
            ]
        )

        checks = _build_regulatory_monitoring_checks(item, criteria_df)

        self.assertEqual(["OK", "OK", "OK", "OK"], checks["Status"].tolist())
        self.assertEqual("12,00%", checks.loc[0, "Valor IME"])
        self.assertEqual("72,00%", checks.loc[1, "Valor IME"])


if __name__ == "__main__":
    unittest.main()
