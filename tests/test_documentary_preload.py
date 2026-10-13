from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from tabs.portfolio_page import _render_portfolio_analysis_content


class OpenDocumentTab:
    open = True
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


def test_documentary_tab_never_fetches_multi_year_ime():
    portfolio=SimpleNamespace(id='test',funds=())
    tabs=[SimpleNamespace(open=False) for _ in range(4)]+[OpenDocumentTab()]
    with patch('services.documentary_diligence.has_documentary_diligence',return_value=True), patch('tabs.portfolio_page._render_portfolio_view_tabs',return_value=tabs), patch('tabs.portfolio_page._preload_portfolio_data') as preload, patch('tabs.portfolio_page._load_portfolio_analysis_data') as financial, patch('tabs.portfolio_page.deep_dive_tab.render_tab_deep_dive') as documents:
        assert _render_portfolio_analysis_content(selected_portfolio=portfolio,period=None,selected_sections=('Documentos',))
        preload.assert_not_called()
        financial.assert_not_called()
        documents.assert_called_once()
