from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from services.portfolio_store import PortfolioFund, PortfolioRecord, PortfolioStoreConfig
from tabs import ime_portfolio_support
from tabs.ime_portfolio_support import (
    build_portfolio_funds_display_df,
    build_portfolio_record_label_lookup,
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

    def test_portfolio_label_disambiguates_duplicate_names(self) -> None:
        portfolios = [
            PortfolioRecord(
                id="aaaa1111portfolio",
                name="Mercado Livre Soma",
                funds=(PortfolioFund(cnpj="12345678000199", display_name="FIDC A"),),
                created_at="2026-04-14T12:00:00Z",
                updated_at="2026-04-14T12:00:00Z",
            ),
            PortfolioRecord(
                id="bbbb2222portfolio",
                name="Mercado Livre Soma",
                funds=(PortfolioFund(cnpj="22345678000199", display_name="FIDC B"),),
                created_at="2026-04-14T12:05:00Z",
                updated_at="2026-04-14T12:05:00Z",
            ),
        ]

        labels = build_portfolio_record_label_lookup(portfolios)

        self.assertIn("ID aaaa1111", labels["aaaa1111portfolio"])
        self.assertIn("ID bbbb2222", labels["bbbb2222portfolio"])
        self.assertNotEqual(labels["aaaa1111portfolio"], labels["bbbb2222portfolio"])

    def test_portfolio_funds_display_df_shows_clean_names_and_formatted_cnpjs(self) -> None:
        portfolio = PortfolioRecord(
            id="portfolio-1",
            name="Carteira",
            funds=(
                PortfolioFund(
                    cnpj="12345678000199",
                    display_name="FIDC XPTO · 12.345.678/0001-99",
                ),
            ),
            created_at="2026-04-14T12:00:00Z",
            updated_at="2026-04-14T12:00:00Z",
        )

        display = build_portfolio_funds_display_df(portfolio)

        self.assertEqual(["Fundo", "CNPJ"], display.columns.tolist())
        self.assertEqual("FIDC XPTO", display.iloc[0]["Fundo"])
        self.assertEqual("12.345.678/0001-99", display.iloc[0]["CNPJ"])

    def test_portfolio_store_signature_tracks_local_file_changes(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "portfolios.json"
            path.write_text('{"schema_version": 1, "portfolios": []}\n', encoding="utf-8")
            config = PortfolioStoreConfig(backend="local", local_path=str(path))
            with patch.object(ime_portfolio_support, "get_portfolio_store_config", return_value=config):
                first = json.loads(ime_portfolio_support._portfolio_store_signature())
                path.write_text('{"schema_version": 1, "portfolios": [{"id": "a"}]}\n', encoding="utf-8")
                second = json.loads(ime_portfolio_support._portfolio_store_signature())

        self.assertNotEqual(first["local_file"], second["local_file"])


if __name__ == "__main__":
    unittest.main()
