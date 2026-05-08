from __future__ import annotations

import unittest

from tabs.tab_fidc_monitoring import _portfolio_reference_competencia


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


if __name__ == "__main__":
    unittest.main()
