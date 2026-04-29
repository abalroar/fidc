from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from openpyxl import load_workbook
import pandas as pd

from services.mercado_livre_dashboard import (
    build_consolidated_monthly_base,
    build_excel_export_bytes,
    build_fund_monthly_base,
    build_mercado_livre_outputs,
    build_wide_table,
    load_outputs_from_cache,
    portfolio_identity_key,
    save_outputs_to_cache,
)
from services.portfolio_store import PortfolioFund, PortfolioRecord
from tabs.tab_mercado_livre import _resolve_existing_portfolio_for_save


class MercadoLivreDashboardTests(unittest.TestCase):
    def test_build_fund_monthly_base_calculates_accumulated_npl_and_ex360(self) -> None:
        dashboard = _dashboard(
            fund_name="FIDC A",
            cnpj="11111111000111",
            pl_total=100.0,
            pl_senior=75.0,
            pl_mezz=15.0,
            pl_sub=10.0,
            carteira=1_000.0,
            pdd=100.0,
            buckets={
                1: 100.0,
                2: 50.0,
                3: 30.0,
                4: 20.0,
                5: 10.0,
                6: 5.0,
                7: 15.0,
                8: 7.0,
                9: 3.0,
                10: 0.0,
            },
        )

        monthly = build_fund_monthly_base(cnpj="11111111000111", fund_name="FIDC A", dashboard=dashboard)
        row = monthly.iloc[0]

        self.assertAlmostEqual(25.0, row["subordinacao_total_pct"])
        self.assertAlmostEqual(60.0, row["npl_over90"])
        self.assertAlmostEqual(10.0, row["npl_over360"])
        self.assertAlmostEqual(50.0, row["npl_over90_ex360"])
        self.assertAlmostEqual(990.0, row["carteira_ex360"])
        self.assertAlmostEqual(50.0 / 990.0 * 100.0, row["npl_over90_ex360_pct"], places=6)
        self.assertTrue(bool(row["pdd_ex360_calculavel"]))
        self.assertAlmostEqual(10.0, row["baixa_over360_carteira"])
        self.assertAlmostEqual(10.0, row["baixa_over360_pdd"])
        self.assertAlmostEqual(0.0, row["baixa_over360_pl"])
        self.assertAlmostEqual(90.0, row["pdd_ex360"])
        self.assertAlmostEqual(900.0, row["carteira_liquida_ex360"])
        self.assertNotIn("PDD ex-360 não calculável", row["warnings"])

    def test_ex360_writeoff_reduces_pl_when_pdd_is_insufficient(self) -> None:
        dashboard = _dashboard(
            fund_name="FIDC A",
            cnpj="11111111000111",
            pl_total=100.0,
            pl_senior=75.0,
            pl_mezz=15.0,
            pl_sub=10.0,
            carteira=1_000.0,
            pdd=5.0,
            buckets={8: 10.0},
        )

        monthly = build_fund_monthly_base(cnpj="11111111000111", fund_name="FIDC A", dashboard=dashboard)
        row = monthly.iloc[0]

        self.assertAlmostEqual(10.0, row["baixa_over360_carteira"])
        self.assertAlmostEqual(5.0, row["baixa_over360_pdd"])
        self.assertAlmostEqual(5.0, row["baixa_over360_pl"])
        self.assertAlmostEqual(0.0, row["pdd_ex360"])
        self.assertAlmostEqual(95.0, row["pl_total_ex360"])
        self.assertAlmostEqual(20.0, row["pl_subordinada_mezz_ex360"])
        self.assertIn("PDD menor que Over 360", row["warnings"])

    def test_official_pl_overrides_class_sum_and_keeps_reconciliation(self) -> None:
        dashboard = _dashboard(
            fund_name="FIDC A",
            cnpj="11111111000111",
            pl_total=100.0,
            pl_senior=75.0,
            pl_mezz=15.0,
            pl_sub=10.0,
            carteira=1_000.0,
            pdd=100.0,
            buckets={4: 40.0, 7: 10.0, 8: 10.0},
        )
        official_pl = pd.DataFrame(
            [{"competencia": "01/2026", "pl_total_oficial": 110.0, "pl_total_oficial_source_status": "reported_value"}]
        )

        monthly = build_fund_monthly_base(
            cnpj="11111111000111",
            fund_name="FIDC A",
            dashboard=dashboard,
            official_pl_history_df=official_pl,
        )
        row = monthly.iloc[0]

        self.assertAlmostEqual(110.0, row["pl_total"])
        self.assertAlmostEqual(100.0, row["pl_total_classes"])
        self.assertAlmostEqual(10.0, row["pl_reconciliacao_delta"])
        self.assertEqual("PATRLIQ/VL_PATRIM_LIQ", row["pl_total_usado_fonte"])
        self.assertIn("PL oficial diverge", row["warnings"])

    def test_consolidated_base_sums_absolute_values_and_recalculates_ratios(self) -> None:
        dashboard_a = _dashboard(
            fund_name="FIDC A",
            cnpj="11111111000111",
            pl_total=100.0,
            pl_senior=75.0,
            pl_mezz=15.0,
            pl_sub=10.0,
            carteira=1_000.0,
            pdd=100.0,
            buckets={4: 40.0, 7: 10.0, 8: 10.0},
        )
        dashboard_b = _dashboard(
            fund_name="FIDC B",
            cnpj="22222222000122",
            pl_total=200.0,
            pl_senior=160.0,
            pl_mezz=0.0,
            pl_sub=40.0,
            carteira=2_000.0,
            pdd=200.0,
            buckets={4: 80.0, 7: 20.0, 8: 0.0},
        )
        monthly_a = build_fund_monthly_base(cnpj="11111111000111", fund_name="FIDC A", dashboard=dashboard_a)
        monthly_b = build_fund_monthly_base(cnpj="22222222000122", fund_name="FIDC B", dashboard=dashboard_b)

        consolidated = build_consolidated_monthly_base(
            portfolio_name="Carteira",
            fund_monthly_frames={"11111111000111": monthly_a, "22222222000122": monthly_b},
        )
        row = consolidated.iloc[0]

        self.assertAlmostEqual(300.0, row["pl_total"])
        self.assertAlmostEqual(65.0, row["pl_subordinada_mezz"])
        self.assertAlmostEqual(65.0 / 300.0 * 100.0, row["subordinacao_total_pct"], places=6)
        self.assertAlmostEqual(160.0, row["npl_over90"])
        self.assertAlmostEqual(300.0 / 160.0 * 100.0, row["pdd_npl_over90_pct"], places=6)

    def test_wide_table_and_excel_export_include_required_blocks(self) -> None:
        dashboard = _dashboard(
            fund_name="FIDC A",
            cnpj="11111111000111",
            pl_total=100.0,
            pl_senior=75.0,
            pl_mezz=15.0,
            pl_sub=10.0,
            carteira=1_000.0,
            pdd=100.0,
            buckets={4: 40.0, 7: 10.0, 8: 10.0},
        )
        outputs = build_mercado_livre_outputs(
            portfolio_id="portfolio-1",
            portfolio_name="Carteira",
            dashboards_by_cnpj={"11111111000111": ("FIDC A", dashboard)},
            period_label="01/2026 a 01/2026",
        )
        wide = build_wide_table(outputs.fund_monthly["11111111000111"], scope_name="FIDC A")

        self.assertIn("jan/26", wide.columns)
        self.assertIn("7. Visão Ex-Vencidos > 360d", set(wide["Bloco"]))
        self.assertIn("NPL Over 90d", set(wide["Métrica"]))

        excel_bytes = build_excel_export_bytes(outputs)
        workbook = load_workbook(BytesIO(excel_bytes), data_only=True)
        self.assertIn("Consolidado", workbook.sheetnames)
        self.assertIn("Auditoria", workbook.sheetnames)

    def test_outputs_cache_roundtrip_uses_deterministic_identity(self) -> None:
        dashboard = _dashboard(
            fund_name="FIDC A",
            cnpj="11111111000111",
            pl_total=100.0,
            pl_senior=75.0,
            pl_mezz=15.0,
            pl_sub=10.0,
            carteira=1_000.0,
            pdd=100.0,
            buckets={4: 40.0, 7: 10.0, 8: 10.0},
        )
        outputs = build_mercado_livre_outputs(
            portfolio_id="portfolio-1",
            portfolio_name="Carteira",
            dashboards_by_cnpj={"11111111000111": ("FIDC A", dashboard)},
            period_label="01/2026 a 01/2026",
        )
        funds = (PortfolioFund(cnpj="11111111000111", display_name="FIDC A"),)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = save_outputs_to_cache(
                outputs,
                portfolio_id="portfolio-1",
                period_key="2026-01-01::2026-01-01",
                portfolio_funds=funds,
                base_dir=Path(tmp_dir),
            )
            loaded = load_outputs_from_cache(
                portfolio_id="outro-id-visual",
                period_key="2026-01-01::2026-01-01",
                portfolio_funds=funds,
                base_dir=Path(tmp_dir),
            )
            self.assertTrue((root / "metadata.json").exists())

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertIn("11111111000111", loaded.fund_monthly)
        self.assertEqual(outputs.metadata["loaded_period_label"], loaded.metadata["loaded_period_label"])

    def test_portfolio_identity_key_is_deterministic_and_duplicate_save_reuses_same_basket(self) -> None:
        funds_a = (
            PortfolioFund(cnpj="11111111000111", display_name="A"),
            PortfolioFund(cnpj="22222222000122", display_name="B"),
        )
        funds_b = (
            PortfolioFund(cnpj="22222222000122", display_name="B"),
            PortfolioFund(cnpj="11111111000111", display_name="A"),
        )

        self.assertEqual(
            portfolio_identity_key(funds_a, fallback="p1"),
            portfolio_identity_key(funds_b, fallback="p2"),
        )

        existing = PortfolioRecord(
            id="portfolio-1",
            name="Mercado Livre",
            funds=funds_a,
            created_at="2026-04-29T00:00:00Z",
            updated_at="2026-04-29T00:00:00Z",
        )
        action = _resolve_existing_portfolio_for_save(
            portfolios=[existing],
            target=None,
            name="Outro Nome",
            funds=list(funds_b),
        )

        self.assertEqual("reuse", action["action"])
        self.assertEqual(existing.id, action["portfolio"].id)


def _dashboard(
    *,
    fund_name: str,
    cnpj: str,
    pl_total: float,
    pl_senior: float,
    pl_mezz: float,
    pl_sub: float,
    carteira: float,
    pdd: float,
    buckets: dict[int, float],
) -> SimpleNamespace:
    competencia = "01/2026"
    bucket_labels = {
        1: "Até 30 dias",
        2: "31 a 60 dias",
        3: "61 a 90 dias",
        4: "91 a 120 dias",
        5: "121 a 150 dias",
        6: "151 a 180 dias",
        7: "181 a 360 dias",
        8: "361 a 720 dias",
        9: "721 a 1080 dias",
        10: "Acima de 1080 dias",
    }
    return SimpleNamespace(
        competencias=[competencia],
        fund_info={"nome_fundo": fund_name, "cnpj_fundo": cnpj, "nome_classe": "Classe única"},
        subordination_history_df=pd.DataFrame(
            [
                {
                    "competencia": competencia,
                    "competencia_dt": pd.Timestamp("2026-01-01"),
                    "pl_total": pl_total,
                    "pl_senior": pl_senior,
                    "pl_mezzanino": pl_mezz,
                    "pl_subordinada_strict": pl_sub,
                    "pl_subordinada": pl_mezz + pl_sub,
                }
            ]
        ),
        default_history_df=pd.DataFrame(
            [
                {
                    "competencia": competencia,
                    "competencia_dt": pd.Timestamp("2026-01-01"),
                    "direitos_creditorios": carteira,
                    "direitos_creditorios_fonte": "teste",
                    "provisao_total": pdd,
                }
            ]
        ),
        dc_canonical_history_df=pd.DataFrame(
            [
                {
                    "competencia": competencia,
                    "competencia_dt": pd.Timestamp("2026-01-01"),
                    "dc_total_canonico": carteira,
                    "dc_total_fonte_efetiva": "teste",
                }
            ]
        ),
        default_buckets_history_df=pd.DataFrame(
            [
                {
                    "competencia": competencia,
                    "competencia_dt": pd.Timestamp("2026-01-01"),
                    "ordem": ordem,
                    "faixa": bucket_labels[ordem],
                    "valor": valor,
                    "source_status": "reported_value",
                }
                for ordem, valor in buckets.items()
            ]
        ),
    )


if __name__ == "__main__":
    unittest.main()
