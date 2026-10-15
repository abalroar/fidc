from contextlib import nullcontext
import re
from types import SimpleNamespace
from unittest.mock import Mock, patch

from services.portfolio_store import PortfolioFund, PortfolioRecord
from tabs import portfolio_page, tab_fidc_monitoring


def test_compact_identification_preserves_all_table_values_and_exact_identifiers(monkeypatch):
    outputs = [{"cnpj": "33254370000104", "display_name": "MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS"}]
    monkeypatch.setattr(tab_fidc_monitoring, "_aggregate_metric", lambda *args: 0)
    monkeypatch.setattr(tab_fidc_monitoring, "_metric_numeric", lambda *args: None)
    original = tab_fidc_monitoring._render_cockpit_table_html(outputs, "08/2026", compact_identity=True)
    compact = tab_fidc_monitoring._render_cockpit_table_html(outputs, "08/2026", compact_identity=True, inline_identifiers=False)
    assert re.findall(r"<td[^>]*>(.*?)</td>", original) == re.findall(r"<td[^>]*>(.*?)</td>", compact)
    assert outputs[0]["display_name"] in compact
    assert "33.254.370/0001-04" in compact
    assert "<small>33.254.370/0001-04</small>" not in compact
    assert "<br>CNPJ 33.254.370/0001-04</span></details>" in compact


def test_compact_data_exports_render_native_callables_without_generating_any_file():
    portfolio = PortfolioRecord(id="p", name="Nome 1T26", funds=(PortfolioFund(cnpj="33254370000104", display_name="MC 0"),), created_at="", updated_at="")
    analysis = SimpleNamespace(monitor_outputs=SimpleNamespace(), research_outputs=SimpleNamespace())
    with (
        patch.object(portfolio_page.st, "session_state", {}),
        patch.object(portfolio_page, "_portfolio_download_context_signature", return_value="current"),
        patch.object(portfolio_page.st, "expander", return_value=nullcontext()),
        patch("services.on_demand_download.st.button", return_value=False) as prepare,
        patch("services.on_demand_download.st.download_button") as download,
        patch.object(portfolio_page, "_prepare_complete_portfolio_pptx") as ppt,
        patch.object(portfolio_page, "build_consolidated_snapshot_excel_bytes") as excel,
    ):
        portfolio_page._render_unified_portfolio_download(
            analysis=analysis, selected_portfolio=portfolio, period=SimpleNamespace(label="12M"), compact=True,
        )
    ppt.assert_not_called()
    excel.assert_not_called()
    # In the Exportar popover the presentation is the primary action.
    assert prepare.call_args.kwargs["type"] == "primary"
    assert len(download.call_args_list) == 4
    assert all(callable(call.kwargs["data"]) for call in download.call_args_list)
