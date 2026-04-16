from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.portfolio_store import PortfolioFund, PortfolioRecord
from tabs.tab_fidc_ime_carteira import (
    _execute_portfolio_load_for_funds,
    _sync_portfolio_fund_names_from_results,
)


class _DummyProgress:
    def progress(self, *_args, **_kwargs) -> None:
        return None

    def empty(self) -> None:
        return None


class _DummyStatus:
    def caption(self, *_args, **_kwargs) -> None:
        return None

    def empty(self) -> None:
        return None


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

    def test_execute_portfolio_load_for_funds_does_not_require_retry_results_when_no_retry(self) -> None:
        portfolio = PortfolioRecord(
            id="portfolio-1",
            name="Carteira Teste",
            funds=(PortfolioFund(cnpj="12345678000199", display_name="FIDC A"),),
            created_at="2026-04-15T00:00:00Z",
            updated_at="2026-04-15T00:00:00Z",
        )
        period = SimpleNamespace(
            month_count=12,
            cache_key="period-1",
            label="12 meses",
            mode="preset",
            start_month=SimpleNamespace(isoformat=lambda: "2026-01-01"),
            end_month=SimpleNamespace(isoformat=lambda: "2026-12-01"),
            preset_months=12,
        )
        initial_results = {
            "12345678000199": {
                "result": object(),
                "context": {"portfolio_fund_name_resolved": "FIDC A"},
            }
        }

        with (
            patch("tabs.tab_fidc_ime_carteira.st.progress", return_value=_DummyProgress()),
            patch("tabs.tab_fidc_ime_carteira.st.empty", return_value=_DummyStatus()),
            patch("tabs.tab_fidc_ime_carteira._portfolio_worker_count", return_value=1),
            patch("tabs.tab_fidc_ime_carteira._load_portfolio_funds_batch", return_value=initial_results),
            patch("tabs.tab_fidc_ime_carteira._sync_portfolio_fund_names_from_results", return_value=None),
            patch("tabs.tab_fidc_ime_carteira._get_portfolio_runtime_state", return_value={}),
            patch("tabs.tab_fidc_ime_carteira._save_portfolio_runtime_state"),
        ):
            _execute_portfolio_load_for_funds(
                selected_portfolio=portfolio,
                period=period,
                funds=portfolio.funds,
                existing_results=None,
            )


if __name__ == "__main__":
    unittest.main()
