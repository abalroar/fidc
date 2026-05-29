from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from services.portfolio_store import PortfolioFund, PortfolioRecord
from tabs import portfolio_page


class PortfolioPageTests(unittest.TestCase):
    def test_resolve_workflow_sections_orders_blocks_and_deduplicates(self) -> None:
        selected = [
            portfolio_page.SECTION_RETURNS,
            "fora-do-menu",
            portfolio_page.SECTION_AGING,
            portfolio_page.SECTION_RETURNS,
        ]

        resolved = portfolio_page._resolve_workflow_sections(selected)

        self.assertEqual(
            (
                portfolio_page.SECTION_AGING,
                portfolio_page.SECTION_RETURNS,
            ),
            resolved,
        )

    def test_deep_dive_selection_includes_monitoring_context(self) -> None:
        resolved = portfolio_page._resolve_workflow_sections([portfolio_page.SECTION_DEEP_DIVE])

        self.assertEqual(
            (
                portfolio_page.SECTION_MONITORING,
                portfolio_page.SECTION_DEEP_DIVE,
            ),
            resolved,
        )

    def test_workflow_selector_uses_fixed_basic_package_without_extra_controls(self) -> None:
        with (
            patch("tabs.portfolio_page.st.radio") as radio,
            patch("tabs.portfolio_page.st.multiselect") as multiselect,
        ):
            selected = portfolio_page._render_workflow_selector()

        self.assertEqual(portfolio_page.DEFAULT_SECTIONS, selected)
        radio.assert_not_called()
        multiselect.assert_not_called()

    def test_sections_grouped_for_render_keeps_related_blocks_together(self) -> None:
        groups = portfolio_page._sections_grouped_for_render(
            (
                portfolio_page.SECTION_AGING,
                portfolio_page.SECTION_RETURNS,
                portfolio_page.SECTION_MONITORING,
                portfolio_page.SECTION_DEEP_DIVE,
            )
        )

        self.assertEqual(
            (
                (
                    "Contexto e risco",
                    (
                        portfolio_page.SECTION_AGING,
                        portfolio_page.SECTION_RETURNS,
                    ),
                ),
                (
                    "Monitoramento e governança",
                    (
                        portfolio_page.SECTION_MONITORING,
                        portfolio_page.SECTION_DEEP_DIVE,
                    ),
                ),
            ),
            groups,
        )

    def test_preload_uses_returns_lookback_before_current_period(self) -> None:
        portfolio = PortfolioRecord(
            id="portfolio-1",
            name="Carteira Teste",
            funds=(PortfolioFund(cnpj="12345678000199", display_name="FIDC A"),),
            created_at="2026-05-14T00:00:00Z",
            updated_at="2026-05-14T00:00:00Z",
        )
        period = SimpleNamespace(cache_key="current", label="05/2023 a 04/2026")
        calculation_period = SimpleNamespace(cache_key="lookback", label="05/2022 a 04/2026")

        with (
            patch("tabs.portfolio_page.somatorio_tab._period_with_yoy_lookback", return_value=calculation_period),
            patch("tabs.portfolio_page._returns_outputs_cached", return_value=False),
            patch("tabs.portfolio_page.carteira_tab.ensure_portfolio_ime_data") as ensure_data,
        ):
            portfolio_page._preload_portfolio_data(
                selected_portfolio=portfolio,
                period=period,
                selected_sections=(
                    portfolio_page.SECTION_AGING,
                    portfolio_page.SECTION_RETURNS,
                ),
            )

        self.assertEqual(2, ensure_data.call_count)
        self.assertEqual(calculation_period, ensure_data.call_args_list[0].kwargs["period"])
        self.assertEqual(period, ensure_data.call_args_list[1].kwargs["period"])

    def test_preload_skips_returns_when_output_cache_exists(self) -> None:
        portfolio = PortfolioRecord(
            id="portfolio-1",
            name="Carteira Teste",
            funds=(PortfolioFund(cnpj="12345678000199", display_name="FIDC A"),),
            created_at="2026-05-14T00:00:00Z",
            updated_at="2026-05-14T00:00:00Z",
        )
        period = SimpleNamespace(cache_key="current", label="05/2023 a 04/2026")
        calculation_period = SimpleNamespace(cache_key="lookback", label="05/2022 a 04/2026")

        with (
            patch("tabs.portfolio_page.somatorio_tab._period_with_yoy_lookback", return_value=calculation_period),
            patch("tabs.portfolio_page._returns_outputs_cached", return_value=True),
            patch("tabs.portfolio_page.carteira_tab.ensure_portfolio_ime_data") as ensure_data,
        ):
            portfolio_page._preload_portfolio_data(
                selected_portfolio=portfolio,
                period=period,
                selected_sections=(portfolio_page.SECTION_RETURNS,),
            )

        ensure_data.assert_not_called()

    def test_render_section_dispatches_existing_chart_renderers_unchanged(self) -> None:
        portfolio = Mock()
        period = Mock()

        with (
            patch("tabs.portfolio_page.carteira_tab.render_portfolio_aging_analysis") as aging,
            patch("tabs.portfolio_page.somatorio_tab.render_tab_somatorio_fidcs") as returns,
            patch("tabs.portfolio_page.monitoring_tab.render_tab_fidc_monitoring") as monitoring,
            patch("tabs.portfolio_page.deep_dive_tab.render_tab_deep_dive") as deep_dive,
        ):
            portfolio_page._render_section(
                section=portfolio_page.SECTION_AGING,
                selected_portfolio=portfolio,
                period=period,
            )
            portfolio_page._render_section(
                section=portfolio_page.SECTION_RETURNS,
                selected_portfolio=portfolio,
                period=period,
            )
            portfolio_page._render_section(
                section=portfolio_page.SECTION_MONITORING,
                selected_portfolio=portfolio,
                period=period,
            )
            portfolio_page._render_section(
                section=portfolio_page.SECTION_DEEP_DIVE,
                selected_portfolio=portfolio,
                period=period,
            )

        aging.assert_called_once_with(
            selected_portfolio=portfolio,
            period=period,
            section_mode="stacked",
        )
        returns.assert_called_once_with(
            period=period,
            selected_portfolio=portfolio,
            show_portfolio_controls=False,
            use_tabs=False,
            show_guide=False,
        )
        monitoring.assert_called_once_with(
            period=period,
            selected_portfolio=portfolio,
            show_portfolio_selector=False,
            use_tabs=False,
        )
        deep_dive.assert_called_once_with(
            selected_portfolio=portfolio,
            show_portfolio_selector=False,
            show_curation_tools=False,
            compact=True,
        )


if __name__ == "__main__":
    unittest.main()
