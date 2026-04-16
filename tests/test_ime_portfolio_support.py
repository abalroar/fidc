from __future__ import annotations

import unittest

import pandas as pd

from services.portfolio_store import PortfolioFund
from tabs.ime_portfolio_support import (
    enrich_portfolio_funds_with_catalog,
    format_portfolio_fund_label,
    normalize_portfolio_fund_name,
)


class ImePortfolioSupportTests(unittest.TestCase):
    def test_normalize_portfolio_fund_name_removes_appended_cnpj(self) -> None:
        self.assertEqual(
            "FIDC XPTO",
            normalize_portfolio_fund_name("FIDC XPTO · 12.345.678/0001-99", "12345678000199"),
        )

    def test_format_portfolio_fund_label_keeps_single_name_and_formats_cnpj(self) -> None:
        self.assertEqual(
            "FIDC XPTO · 12.345.678/0001-99 · não carregado",
            format_portfolio_fund_label(
                display_name="FIDC XPTO · 12.345.678/0001-99",
                cnpj="12345678000199",
                status="não carregado",
            ),
        )

    def test_enrich_portfolio_funds_with_catalog_prefers_cvm_name(self) -> None:
        catalog_df = pd.DataFrame(
            [
                {
                    "cnpj_fundo": "12345678000199",
                    "nome_fundo": "FIDC CVM Oficial",
                    "situacao": "EM FUNCIONAMENTO NORMAL",
                }
            ]
        )
        enriched = enrich_portfolio_funds_with_catalog(
            [PortfolioFund(cnpj="12345678000199", display_name="12345678000199")],
            catalog_df,
        )
        self.assertEqual(1, len(enriched))
        self.assertEqual("FIDC CVM Oficial", enriched[0].display_name)


if __name__ == "__main__":
    unittest.main()
