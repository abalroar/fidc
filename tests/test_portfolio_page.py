from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from services.portfolio_store import PortfolioFund, PortfolioRecord
from tabs import portfolio_page


class PortfolioPageTests(unittest.TestCase):
    def test_portfolio_views_end_with_document_curation(self) -> None:
        self.assertEqual(
            (
                "Estrutura",
                "Crédito e prazo",
                "Inadimplência",
                "Rentabilidade",
                "Curadoria de Leitura (Documentos)",
            ),
            portfolio_page.PORTFOLIO_VIEW_TABS,
        )

    def test_inline_loading_state_preserves_context_without_marketing_stages(self) -> None:
        portfolio = PortfolioRecord(
            id="portfolio-1",
            name="Carteira Crédito & Consignado",
            funds=(
                PortfolioFund(cnpj="33254370000104", display_name="FIDC A"),
                PortfolioFund(cnpj="11222333000181", display_name="FIDC B"),
            ),
            created_at="2026-05-14T00:00:00Z",
            updated_at="2026-05-14T00:00:00Z",
        )
        period = SimpleNamespace(label="01/2025 a 06/2026")

        html = portfolio_page._portfolio_loading_state_html(
            selected_portfolio=portfolio,
            period=period,
        )

        self.assertIn("Carteira Crédito &amp; Consignado", html)
        self.assertIn("01/2025 a 06/2026", html)
        self.assertIn("2 fundos", html)
        self.assertIn('role="status"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn("Buscando informes mensais", html)
        self.assertNotIn("portfolio-loading-stage", html)
        self.assertNotIn("portfolio-loading-progress", html)
        self.assertNotIn("PREPARANDO ANÁLISE", html)
        self.assertNotIn("position: fixed", portfolio_page._PORTFOLIO_PAGE_CSS)
        self.assertNotIn("z-index: 999999", portfolio_page._PORTFOLIO_PAGE_CSS)
        self.assertNotIn("visibility: hidden", portfolio_page._PORTFOLIO_PAGE_CSS)

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

    def test_curadoria_selection_does_not_force_monitoring_context(self) -> None:
        resolved = portfolio_page._resolve_workflow_sections([portfolio_page.SECTION_DEEP_DIVE])

        self.assertEqual(
            (
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
        self.assertNotIn(portfolio_page.SECTION_MONITORING, selected)
        self.assertIn(portfolio_page.SECTION_DEEP_DIVE, selected)
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

    def test_complete_portfolio_ppt_forwards_cdi_and_benchmark_inputs(self) -> None:
        cnpj = "12345678000199"
        outputs = SimpleNamespace(fund_monthly={cnpj: SimpleNamespace()})
        analysis = portfolio_page.PortfolioAnalysisData(
            scopes=(
                portfolio_page.PortfolioAnalysisScope(
                    value=cnpj,
                    label="FIDC A",
                    kind="fund",
                    cnpj=cnpj,
                    dashboard=SimpleNamespace(),
                ),
            ),
            aggregate_bundle=None,
            outputs=outputs,
            monitor_outputs=SimpleNamespace(),
            research_outputs=SimpleNamespace(),
            verification_report=None,
            dashboard_errors={},
            load_errors={},
        )
        portfolio = PortfolioRecord(
            id="portfolio-1",
            name="Carteira Teste",
            funds=(PortfolioFund(cnpj=cnpj, display_name="FIDC A"),),
            created_at="2026-05-14T00:00:00Z",
            updated_at="2026-05-14T00:00:00Z",
        )
        period = SimpleNamespace(label="07/2025 a 06/2026")
        cdi_by_fund = {cnpj: ("cdi-rate",)}
        benchmark_by_fund = {cnpj: {"senior:1": 0.035}}

        with (
            patch(
                "tabs.portfolio_page.credit_tab.resolve_fund_return_export_inputs",
                return_value=(cdi_by_fund, benchmark_by_fund),
            ) as resolve_inputs,
            patch(
                "services.somatorio_fidcs_ppt_export.build_somatorio_fidcs_pptx_bytes",
                return_value=b"pptx",
            ) as build_pptx,
            patch("tabs.portfolio_page.build_consolidated_snapshot_excel_bytes", return_value=b"xlsx"),
            patch("tabs.portfolio_page.build_full_variable_excel_export_bytes", return_value=b"xlsx"),
            patch("tabs.portfolio_page.build_full_variable_csv_zip_bytes", return_value=b"zip"),
            patch("tabs.portfolio_page.st.expander", return_value=nullcontext()),
            patch("tabs.portfolio_page.st.download_button") as download_button,
        ):
            portfolio_page._render_unified_portfolio_download(
                analysis=analysis,
                selected_portfolio=portfolio,
                period=period,
            )

        resolve_inputs.assert_called_once_with(outputs=outputs, cnpjs=[cnpj])
        build_pptx.assert_called_once_with(
            outputs=outputs,
            monitor_outputs=analysis.monitor_outputs,
            research_outputs=analysis.research_outputs,
            monthly_cdi_rates_by_fund=cdi_by_fund,
            benchmark_spreads_by_fund=benchmark_by_fund,
        )
        self.assertTrue(
            any(call.kwargs.get("data") == b"pptx" for call in download_button.call_args_list)
        )

    def test_transient_provider_failure_keeps_the_recoverable_cause(self) -> None:
        fund = PortfolioFund(cnpj="12345678000199", display_name="FIDC A")
        portfolio = PortfolioRecord(
            id="portfolio-1",
            name="Carteira Teste",
            funds=(fund,),
            created_at="2026-05-14T00:00:00Z",
            updated_at="2026-05-14T00:00:00Z",
        )
        period = SimpleNamespace(cache_key="current", label="07/2025 a 06/2026")
        runtime_state = {
            "results": {
                fund.cnpj: {
                    "result": None,
                    "error": TimeoutError("provider timeout"),
                    "context": {"automatic_retry_attempted": True},
                }
            }
        }

        with (
            patch("tabs.portfolio_page.carteira_tab.ensure_portfolio_ime_data", return_value=runtime_state),
            patch("tabs.portfolio_page.carteira_tab._build_loaded_dashboards_by_cnpj", return_value=({}, {})),
        ):
            with self.assertRaises(portfolio_page.PortfolioAnalysisUnavailable) as raised:
                portfolio_page._load_portfolio_analysis_data(
                    selected_portfolio=portfolio,
                    period=period,
                )

        failure = raised.exception
        self.assertTrue(failure.retryable)
        self.assertIn("fonte regulatória demorou", failure.message)
        self.assertIn("provider timeout", failure.details[0])

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

    def test_document_curation_remains_available_without_analytics(self) -> None:
        portfolio = Mock(id="portfolio-1")
        period = SimpleNamespace(cache_key="period-1")
        tabs = [nullcontext() for _ in portfolio_page.PORTFOLIO_VIEW_TABS]
        failure = portfolio_page.PortfolioAnalysisUnavailable(message="Dados indisponíveis.")

        with (
            patch("tabs.portfolio_page.st.tabs", return_value=tabs),
            patch("tabs.portfolio_page.st.button", return_value=False),
            patch("tabs.portfolio_page.st.markdown") as markdown,
            patch("tabs.portfolio_page.diagnostics_enabled", return_value=False),
            patch("tabs.portfolio_page.deep_dive_tab.render_tab_deep_dive") as deep_dive,
        ):
            portfolio_page._render_unavailable_portfolio_views(
                selected_portfolio=portfolio,
                period=period,
                failure=failure,
            )

        self.assertEqual(len(portfolio_page.PORTFOLIO_VIEW_TABS), markdown.call_count)
        deep_dive.assert_called_once_with(
            selected_portfolio=portfolio,
            show_portfolio_selector=False,
            show_curation_tools=False,
            compact=True,
        )

    def test_retry_action_forces_a_fresh_load_and_reruns(self) -> None:
        portfolio = Mock(id="portfolio-1")
        period = SimpleNamespace(cache_key="period-1")
        tabs = [nullcontext() for _ in portfolio_page.PORTFOLIO_VIEW_TABS]
        failure = portfolio_page.PortfolioAnalysisUnavailable(message="Falha transitória.")
        session_state = {"portfolio_page_context_signature": "stale"}

        with (
            patch("tabs.portfolio_page.st.tabs", return_value=tabs),
            patch("tabs.portfolio_page.st.button", return_value=True),
            patch("tabs.portfolio_page.st.markdown"),
            patch("tabs.portfolio_page.st.session_state", session_state),
            patch("tabs.portfolio_page.st.rerun") as rerun,
            patch("tabs.portfolio_page.diagnostics_enabled", return_value=False),
            patch("tabs.portfolio_page.carteira_tab.load_portfolio_ime_data") as reload_data,
            patch("tabs.portfolio_page.deep_dive_tab.render_tab_deep_dive"),
        ):
            portfolio_page._render_unavailable_portfolio_views(
                selected_portfolio=portfolio,
                period=period,
                failure=failure,
            )

        reload_data.assert_called_once_with(
            selected_portfolio=portfolio,
            period=period,
        )
        self.assertNotIn("portfolio_page_context_signature", session_state)
        rerun.assert_called_once_with()

    def test_document_curation_remains_available_when_analytics_raise(self) -> None:
        portfolio = Mock()
        period = Mock()

        with (
            patch("tabs.portfolio_page._preload_portfolio_data", side_effect=RuntimeError("falha analítica")),
            patch("tabs.portfolio_page._render_unavailable_portfolio_views") as fallback,
        ):
            ready = portfolio_page._render_portfolio_analysis_surface(
                selected_portfolio=portfolio,
                period=period,
                selected_sections=portfolio_page.DEFAULT_SECTIONS,
            )

        self.assertFalse(ready)
        fallback.assert_called_once()
        self.assertIs(portfolio, fallback.call_args.kwargs["selected_portfolio"])
        self.assertIs(period, fallback.call_args.kwargs["period"])
        failure = fallback.call_args.kwargs["failure"]
        self.assertIsInstance(failure, portfolio_page.PortfolioAnalysisUnavailable)
        self.assertIn("falha inesperada", failure.message)
        self.assertIn("RuntimeError: falha analítica", failure.details)


if __name__ == "__main__":
    unittest.main()
