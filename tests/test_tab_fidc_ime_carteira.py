from __future__ import annotations

from datetime import date
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from services.portfolio_store import PortfolioFund, PortfolioRecord
from tabs.tab_fidc_ime_carteira import (
    _apply_pending_portfolio_selection,
    _build_portfolio_selector_label_lookup,
    _build_loaded_dashboards_by_cnpj,
    _execute_portfolio_load_for_funds,
    _is_cache_ready_for_portfolio_load,
    _load_single_portfolio_fund,
    _normalize_portfolio_editor_mode,
    _portfolio_worker_count,
    _queue_portfolio_selection,
    _resolve_active_analysis_portfolio,
    _sync_portfolio_fund_names_from_results,
    build_temporary_portfolio_from_cnpj,
    ensure_portfolio_ime_data,
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
    def test_build_temporary_portfolio_accepts_masked_valid_cnpj(self) -> None:
        catalog_df = pd.DataFrame(
            [
                {
                    "cnpj_fundo": "33254370000104",
                    "nome_fundo": "FIDC Mercado Crédito",
                    "situacao": "EM FUNCIONAMENTO",
                }
            ]
        )

        portfolio = build_temporary_portfolio_from_cnpj(
            "33.254.370/0001-04",
            catalog_df=catalog_df,
        )

        self.assertEqual("adhoc-cnpj-33254370000104", portfolio.id)
        self.assertEqual("FIDC Mercado Crédito", portfolio.name)
        self.assertEqual("33254370000104", portfolio.funds[0].cnpj)
        self.assertEqual("FIDC Mercado Crédito", portfolio.funds[0].display_name)
        self.assertEqual("Consulta temporária por CNPJ", portfolio.notes)

    def test_build_temporary_portfolio_rejects_invalid_cnpj_checksum(self) -> None:
        invalid_values = (
            "33.254.370/0001-05",
            "11.111.111/1111-11",
        )

        for raw_cnpj in invalid_values:
            with self.subTest(raw_cnpj=raw_cnpj):
                with self.assertRaisesRegex(ValueError, "dígitos verificadores"):
                    build_temporary_portfolio_from_cnpj(
                        raw_cnpj,
                        catalog_df=pd.DataFrame(columns=["cnpj_fundo", "nome_fundo"]),
                    )

    def test_resolve_active_analysis_without_context_does_not_select_meli(self) -> None:
        meli = PortfolioRecord(
            id="portfolio-meli",
            name="MELI (FIDCs Mercado Crédito 0, I e II)",
            funds=(PortfolioFund(cnpj="33254370000104", display_name="FIDC Mercado Crédito"),),
            created_at="2026-04-15T00:00:00Z",
            updated_at="2026-04-15T00:00:00Z",
        )

        with patch.dict("tabs.tab_fidc_ime_carteira.st.session_state", {}, clear=True):
            selected = _resolve_active_analysis_portfolio(
                portfolios=[meli],
                catalog_df=pd.DataFrame(columns=["cnpj_fundo", "nome_fundo"]),
            )

        self.assertIsNone(selected)

    def test_resolve_active_analysis_uses_saved_and_cnpj_contexts(self) -> None:
        saved = PortfolioRecord(
            id="portfolio-saved",
            name="Carteira salva",
            funds=(PortfolioFund(cnpj="33254370000104", display_name="FIDC Mercado Crédito"),),
            created_at="2026-04-15T00:00:00Z",
            updated_at="2026-04-15T00:00:00Z",
        )
        catalog_df = pd.DataFrame(
            [
                {
                    "cnpj_fundo": "11222333000181",
                    "nome_fundo": "FIDC Consulta Direta",
                }
            ]
        )

        with patch.dict(
            "tabs.tab_fidc_ime_carteira.st.session_state",
            {"ime_portfolio_analysis_context": {"kind": "saved", "value": saved.id}},
            clear=True,
        ):
            selected_saved = _resolve_active_analysis_portfolio(
                portfolios=[saved],
                catalog_df=catalog_df,
            )

        with patch.dict(
            "tabs.tab_fidc_ime_carteira.st.session_state",
            {"ime_portfolio_analysis_context": {"kind": "cnpj", "value": "11.222.333/0001-81"}},
            clear=True,
        ):
            selected_cnpj = _resolve_active_analysis_portfolio(
                portfolios=[saved],
                catalog_df=catalog_df,
            )

        with patch.dict(
            "tabs.tab_fidc_ime_carteira.st.session_state",
            {
                "ime_portfolio_analysis_context": {
                    "kind": "cnpj",
                    "value": "11222333000181",
                    "display_name": "FIDC Nome Guardado",
                }
            },
            clear=True,
        ):
            selected_from_context = _resolve_active_analysis_portfolio(
                portfolios=[saved],
                catalog_df=pd.DataFrame(columns=["cnpj_fundo", "nome_fundo"]),
            )

        self.assertIs(saved, selected_saved)
        self.assertIsNotNone(selected_cnpj)
        assert selected_cnpj is not None
        self.assertEqual("adhoc-cnpj-11222333000181", selected_cnpj.id)
        self.assertEqual("FIDC Consulta Direta", selected_cnpj.name)
        self.assertEqual("11222333000181", selected_cnpj.funds[0].cnpj)
        self.assertIsNotNone(selected_from_context)
        assert selected_from_context is not None
        self.assertEqual("FIDC Nome Guardado", selected_from_context.name)

    def test_build_portfolio_selector_label_lookup_disambiguates_duplicate_name_and_basket(self) -> None:
        portfolio_a = PortfolioRecord(
            id="57f3418c1e9341e79edeef6086b8c25d",
            name="MELI (FIDCs Mercado Crédito 0, I e II)",
            funds=(
                PortfolioFund(cnpj="33254370000104", display_name="FIDC A"),
                PortfolioFund(cnpj="37511828000114", display_name="FIDC B"),
                PortfolioFund(cnpj="41970012000126", display_name="FIDC C"),
            ),
            created_at="2026-04-15T00:00:00Z",
            updated_at="2026-04-15T00:00:00Z",
        )
        portfolio_b = PortfolioRecord(
            id="4220dda141ea442abd86a6ee11ed249f",
            name="MELI (FIDCs Mercado Crédito 0, I e II)",
            funds=(
                PortfolioFund(cnpj="41970012000126", display_name="FIDC C"),
                PortfolioFund(cnpj="37511828000114", display_name="FIDC B"),
                PortfolioFund(cnpj="33254370000104", display_name="FIDC A"),
            ),
            created_at="2026-04-16T00:00:00Z",
            updated_at="2026-04-16T00:00:00Z",
        )

        labels = _build_portfolio_selector_label_lookup([portfolio_a, portfolio_b])

        self.assertEqual(
            "MELI (FIDCs Mercado Crédito 0, I e II) · ID 57f3418c",
            labels[portfolio_a.id],
        )
        self.assertEqual(
            "MELI (FIDCs Mercado Crédito 0, I e II) · ID 4220dda1",
            labels[portfolio_b.id],
        )

    def test_queue_and_apply_pending_portfolio_selection(self) -> None:
        with patch.dict("tabs.tab_fidc_ime_carteira.st.session_state", {}, clear=True):
            _queue_portfolio_selection("portfolio-2")
            _apply_pending_portfolio_selection()

            from tabs.tab_fidc_ime_carteira import st  # local import to read patched state

            self.assertEqual("portfolio-2", st.session_state.get("ime_portfolio_active_id"))
            self.assertNotIn("_ime_portfolio_active_id_pending", st.session_state)

    def test_apply_pending_portfolio_selection_can_clear_active_value(self) -> None:
        with patch.dict(
            "tabs.tab_fidc_ime_carteira.st.session_state",
            {"ime_portfolio_active_id": "portfolio-1"},
            clear=True,
        ):
            _queue_portfolio_selection(None, clear=True)
            _apply_pending_portfolio_selection()

            from tabs.tab_fidc_ime_carteira import st  # local import to read patched state

            self.assertNotIn("ime_portfolio_active_id", st.session_state)

    def test_normalize_portfolio_editor_mode_distinguishes_create_and_edit(self) -> None:
        self.assertEqual("create", _normalize_portfolio_editor_mode(None, has_portfolios=False))
        self.assertEqual("edit", _normalize_portfolio_editor_mode(None, has_portfolios=True))
        self.assertEqual("create", _normalize_portfolio_editor_mode("create", has_portfolios=True))

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

    def test_sync_portfolio_fund_names_ignores_predictable_duplicate_selection(self) -> None:
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

        with patch(
            "tabs.tab_fidc_ime_carteira.save_portfolio_record",
            side_effect=ValueError("Já existe uma seleção idêntica salva com este nome e a mesma cesta de fundos (57f3418c)."),
        ):
            updated = _sync_portfolio_fund_names_from_results(
                selected_portfolio=portfolio,
                results=results,
            )

        self.assertIsNone(updated)

    def test_sync_temporary_portfolio_fund_name_does_not_persist_record(self) -> None:
        portfolio = build_temporary_portfolio_from_cnpj(
            "33.254.370/0001-04",
            catalog_df=pd.DataFrame(columns=["cnpj_fundo", "nome_fundo"]),
        )
        results = {
            "33254370000104": {
                "context": {
                    "portfolio_fund_name_resolved": "FIDC Nome Resolvido",
                }
            }
        }

        with (
            patch("tabs.tab_fidc_ime_carteira.save_portfolio_record") as mocked_save,
            patch.dict(
                "tabs.tab_fidc_ime_carteira.st.session_state",
                {"ime_portfolio_analysis_context": {"kind": "cnpj", "value": "33254370000104"}},
                clear=True,
            ),
        ):
            updated = _sync_portfolio_fund_names_from_results(
                selected_portfolio=portfolio,
                results=results,
            )

            from tabs.tab_fidc_ime_carteira import st  # local import to read patched state

            active_context = st.session_state["ime_portfolio_analysis_context"]

        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual("FIDC Nome Resolvido", updated.name)
        self.assertEqual("FIDC Nome Resolvido", updated.funds[0].display_name)
        self.assertEqual("FIDC Nome Resolvido", active_context["display_name"])
        mocked_save.assert_not_called()

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
            start_month=date(2026, 1, 1),
            end_month=date(2026, 12, 1),
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
            patch("tabs.tab_fidc_ime_carteira._count_cached_portfolio_funds", return_value=0),
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

    def test_cached_portfolio_uses_parallel_worker_count_for_36m_target(self) -> None:
        period = SimpleNamespace(month_count=36)
        self.assertEqual(10, _portfolio_worker_count(total=10, period=period, cached_count=10))

    def test_partial_cache_is_not_counted_as_ready_for_portfolio_load(self) -> None:
        self.assertFalse(
            _is_cache_ready_for_portfolio_load(
                SimpleNamespace(is_cached=True, cache_status="github_cache_partial")
            )
        )
        self.assertTrue(
            _is_cache_ready_for_portfolio_load(
                SimpleNamespace(is_cached=True, cache_status="github_cache")
            )
        )

    def test_load_single_portfolio_fund_refreshes_partial_cache_before_returning(self) -> None:
        fund = PortfolioFund(cnpj="12345678000199", display_name="FIDC A")
        period = SimpleNamespace(
            month_count=2,
            cache_key="period-2",
            label="01/2026 a 02/2026",
            start_month=date(2026, 1, 1),
            end_month=date(2026, 2, 1),
        )
        partial_result = SimpleNamespace(competencias=["02/2026"], docs_df=None)
        refreshed_result = SimpleNamespace(competencias=["01/2026", "02/2026"], docs_df=None)
        partial_load = SimpleNamespace(
            result=partial_result,
            cache_status="github_cache_partial",
            cache_source="portable_index:abc.zip",
            cache_key="compatible-cache",
            cache_dir=Path("/tmp/compatible"),
            source_refresh_attempted=False,
        )
        refreshed_load = SimpleNamespace(
            result=refreshed_result,
            cache_status="refresh",
            cache_source="fundonet",
            cache_key="exact-cache",
            cache_dir=Path("/tmp/exact"),
            source_refresh_attempted=True,
        )
        probe = SimpleNamespace(
            cache_status="github_cache_partial",
            cache_source="portable_index:abc.zip",
            cache_key="compatible-cache",
            requested_cache_key="exact-cache",
            cache_dir=Path("/tmp/compatible"),
        )

        with (
            patch("tabs.tab_fidc_ime_carteira.peek_cached_informe", return_value=probe),
            patch("tabs.tab_fidc_ime_carteira.load_or_extract_informe", side_effect=[partial_load, refreshed_load]) as loader,
        ):
            payload = _load_single_portfolio_fund(fund, period)

        self.assertEqual(2, loader.call_count)
        self.assertTrue(loader.call_args_list[1].kwargs["force_refresh"])
        context = payload["context"]
        self.assertTrue(context["cache_refresh_attempted"])
        self.assertEqual(["01/2026"], context["missing_competencias_before_refresh"])
        self.assertEqual([], context["missing_competencias_after_refresh"])
        self.assertEqual("refresh", context["cache_status"])

    def test_load_single_portfolio_fund_does_not_repeat_source_refresh_marker(self) -> None:
        fund = PortfolioFund(cnpj="12345678000199", display_name="FIDC A")
        period = SimpleNamespace(
            month_count=2,
            cache_key="period-2",
            label="01/2026 a 02/2026",
            start_month=date(2026, 1, 1),
            end_month=date(2026, 2, 1),
        )
        cached_result = SimpleNamespace(competencias=["02/2026"], docs_df=None)
        cached_load = SimpleNamespace(
            result=cached_result,
            cache_status="hit",
            cache_source="runtime",
            cache_key="exact-cache",
            cache_dir=Path("/tmp/exact"),
            source_refresh_attempted=True,
        )
        probe = SimpleNamespace(
            cache_status="hit",
            cache_source="runtime",
            cache_key="exact-cache",
            requested_cache_key="exact-cache",
            cache_dir=Path("/tmp/exact"),
        )

        with (
            patch("tabs.tab_fidc_ime_carteira.peek_cached_informe", return_value=probe),
            patch("tabs.tab_fidc_ime_carteira.load_or_extract_informe", return_value=cached_load) as loader,
        ):
            payload = _load_single_portfolio_fund(fund, period)

        loader.assert_called_once()
        context = payload["context"]
        self.assertFalse(context["cache_refresh_attempted"])
        self.assertEqual(["01/2026"], context["missing_competencias_after_refresh"])
        self.assertEqual("source_refresh_previously_attempted_for_this_cache", context["cache_refresh_skipped_reason"])

    def test_ensure_portfolio_ime_data_loads_all_missing_funds_without_button(self) -> None:
        portfolio = PortfolioRecord(
            id="portfolio-1",
            name="Carteira Teste",
            funds=(
                PortfolioFund(cnpj="12345678000199", display_name="FIDC A"),
                PortfolioFund(cnpj="22345678000199", display_name="FIDC B"),
            ),
            created_at="2026-04-15T00:00:00Z",
            updated_at="2026-04-15T00:00:00Z",
        )
        period = SimpleNamespace(
            month_count=36,
            cache_key="period-36",
            label="36 meses",
            mode="preset",
            start_month=date(2023, 5, 1),
            end_month=date(2026, 4, 1),
            preset_months=36,
        )
        runtime_state = {"results": {}}

        with (
            patch("tabs.tab_fidc_ime_carteira._get_portfolio_runtime_state", return_value=runtime_state),
            patch("tabs.tab_fidc_ime_carteira.st.spinner"),
            patch("tabs.tab_fidc_ime_carteira._execute_portfolio_load_for_funds") as mocked_load,
        ):
            ensure_portfolio_ime_data(selected_portfolio=portfolio, period=period)

        mocked_load.assert_called_once()
        self.assertEqual(tuple(portfolio.funds), mocked_load.call_args.kwargs["funds"])
        self.assertEqual({}, mocked_load.call_args.kwargs["existing_results"])

    def test_ensure_portfolio_ime_data_reloads_stale_partial_results_without_button(self) -> None:
        portfolio = PortfolioRecord(
            id="portfolio-1",
            name="Carteira Teste",
            funds=(
                PortfolioFund(cnpj="12345678000199", display_name="FIDC A"),
                PortfolioFund(cnpj="22345678000199", display_name="FIDC B"),
            ),
            created_at="2026-04-15T00:00:00Z",
            updated_at="2026-04-15T00:00:00Z",
        )
        period = SimpleNamespace(
            month_count=2,
            cache_key="period-2",
            label="01/2026 a 02/2026",
            mode="preset",
            start_month=date(2026, 1, 1),
            end_month=date(2026, 2, 1),
            preset_months=2,
        )
        runtime_state = {
            "results": {
                "12345678000199": {
                    "result": SimpleNamespace(competencias=["02/2026"]),
                    "context": {
                        "cache_status": "partial_hit",
                        "found_competencias": ["02/2026"],
                        "cache_source_refresh_attempted": False,
                    },
                },
                "22345678000199": {
                    "result": SimpleNamespace(competencias=["01/2026", "02/2026"]),
                    "context": {
                        "cache_status": "hit",
                        "found_competencias": ["01/2026", "02/2026"],
                        "cache_source_refresh_attempted": False,
                    },
                },
            }
        }

        with (
            patch("tabs.tab_fidc_ime_carteira._get_portfolio_runtime_state", return_value=runtime_state),
            patch("tabs.tab_fidc_ime_carteira.st.spinner"),
            patch("tabs.tab_fidc_ime_carteira._execute_portfolio_load_for_funds") as mocked_load,
        ):
            ensure_portfolio_ime_data(selected_portfolio=portfolio, period=period)

        mocked_load.assert_called_once()
        self.assertEqual((portfolio.funds[0],), mocked_load.call_args.kwargs["funds"])
        self.assertEqual(runtime_state["results"], mocked_load.call_args.kwargs["existing_results"])

    def test_build_loaded_dashboards_by_cnpj_skips_funds_with_dashboard_error(self) -> None:
        portfolio = PortfolioRecord(
            id="portfolio-1",
            name="Carteira Teste",
            funds=(
                PortfolioFund(cnpj="12345678000199", display_name="FIDC A"),
                PortfolioFund(cnpj="22345678000199", display_name="FIDC B"),
            ),
            created_at="2026-04-15T00:00:00Z",
            updated_at="2026-04-15T00:00:00Z",
        )
        fake_result = SimpleNamespace(
            wide_csv_path=Path("wide.csv"),
            listas_csv_path=Path("listas.csv"),
            docs_csv_path=Path("docs.csv"),
        )
        results = {
            "12345678000199": {"result": fake_result, "context": {}},
            "22345678000199": {"result": fake_result, "context": {}},
        }

        with patch(
            "tabs.tab_fidc_ime_carteira.ime_tab._load_dashboard_data",
            side_effect=[object(), RuntimeError("quebra de teste")],
        ):
            dashboards, errors = _build_loaded_dashboards_by_cnpj(
                selected_portfolio=portfolio,
                results=results,
            )

        self.assertEqual(1, len(dashboards))
        self.assertEqual(1, len(errors))
        self.assertIn("22345678000199", errors)


if __name__ == "__main__":
    unittest.main()
