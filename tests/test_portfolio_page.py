from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tabs import portfolio_page


class PortfolioPageTests(unittest.TestCase):
    def test_render_portfolio_center_page_goes_straight_to_portfolio_analysis(self) -> None:
        portfolio = Mock()
        period = SimpleNamespace(cache_key="current", label="05/2023 a 04/2026")

        with (
            patch("tabs.portfolio_page.carteira_tab.render_portfolio_control_panel", return_value=(portfolio, False)),
            patch("tabs.portfolio_page.carteira_tab.render_portfolio_aging_analysis") as aging,
        ):
            portfolio_page.render_portfolio_center_page(period)

        aging.assert_called_once_with(
            selected_portfolio=portfolio,
            period=period,
            section_mode="stacked",
        )

    def test_render_portfolio_center_page_stops_without_selection(self) -> None:
        period = SimpleNamespace(cache_key="current", label="05/2023 a 04/2026")

        with (
            patch("tabs.portfolio_page.carteira_tab.render_portfolio_control_panel", return_value=(None, False)),
            patch("tabs.portfolio_page.carteira_tab.render_portfolio_aging_analysis") as aging,
            patch("tabs.portfolio_page.st.info") as info,
        ):
            portfolio_page.render_portfolio_center_page(period)

        aging.assert_not_called()
        info.assert_called_once_with("Selecione uma carteira.")


if __name__ == "__main__":
    unittest.main()
