from __future__ import annotations

import unittest
from unittest.mock import patch

from services.portfolio_store import PortfolioFund, PortfolioRecord
from tabs.tab_fidc_ime_carteira import _sync_portfolio_fund_names_from_results


class TabFidcImeCarteiraTests(unittest.TestCase):
    def test_sync_portfolio_fund_names_from_results_persists_resolved_name(self) -> None:
        portfolio = PortfolioRecord(
            id="portfolio-1",
            name="Carteira Teste",
            funds=(PortfolioFund(cnpj="12345678000199", display_name="12345678000199"),),
            created_at="2026-04-15T00:00:00Z",
            updated_at="2026-04-15T00:00:00Z",
        )
        results = {
            "12345678000199": {
                "context": {
                    "portfolio_fund_name_resolved": "FIDC Resolvido",
                }
            }
        }

        with patch("tabs.tab_fidc_ime_carteira.save_portfolio_record", side_effect=lambda record: record) as mocked_save:
            updated = _sync_portfolio_fund_names_from_results(
                selected_portfolio=portfolio,
                results=results,
            )

        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual("FIDC Resolvido", updated.funds[0].display_name)
        mocked_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
