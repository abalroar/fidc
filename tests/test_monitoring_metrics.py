from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import pandas as pd

from services.monitoring_metrics import (
    build_monitoring_tables,
    load_manual_overrides,
    save_manual_overrides,
)
from services.variaveis_fnet import resolve_tag_path


class MonitoringMetricsTests(unittest.TestCase):
    def test_resolve_tag_path_by_suffix(self) -> None:
        wide_df = _fixture_wide_df()

        resolved = resolve_tag_path("PATRLIQ/VL_SOM_PATRLIQ", wide_df)

        self.assertEqual("DOC_ARQ/LISTA_INFORM/PATRLIQ/VL_SOM_PATRLIQ", resolved)

    def test_build_monitoring_tables_core_metrics(self) -> None:
        wide_df = _fixture_wide_df()
        tables = build_monitoring_tables(wide_df, ["10/2025"], cnpj="12345678000199")

        self.assertAlmostEqual(672_084_551.63, _indicator(tables.indicators_df, "PL (R$)", "10/2025"), places=2)
        self.assertAlmostEqual(672.08455163, _indicator(tables.indicators_df, "PL (R$ MM)", "10/2025"), places=8)
        self.assertAlmostEqual(0.9901, _indicator(tables.indicators_df, "Dir Cred / PL", "10/2025"), places=4)
        self.assertAlmostEqual(53_548.38 / 1_000_000.0, _indicator(tables.indicators_df, "PDD (R$ MM)", "10/2025"), places=8)
        self.assertAlmostEqual(0.0, _indicator(tables.indicators_df, "Recompras (R$ MM)", "10/2025"), places=8)
        self.assertAlmostEqual(89.69, _indicator(tables.indicators_df, "Cotas SR / PL %", "10/2025"), places=2)
        self.assertAlmostEqual(5.31, _indicator(tables.indicators_df, "Cotas Sub / PL %", "10/2025"), places=2)
        self.assertAlmostEqual(1.01, _indicator(tables.indicators_df, "Rentabilidade SR % a.m.", "10/2025"), places=2)
        self.assertAlmostEqual(1.34, _indicator(tables.indicators_df, "Rentabilidade Sub % a.m.", "10/2025"), places=2)

    def test_build_monitoring_tables_pdd_credit_and_aging_buckets(self) -> None:
        wide_df = _fixture_wide_df()
        tables = build_monitoring_tables(wide_df, ["10/2025"], cnpj="12345678000199")
        dircred = 672_084_551.63 * 0.9901

        self.assertAlmostEqual(53_548.38 / dircred, _indicator(tables.indicators_df, "PDD / Crédito", "10/2025"), places=8)
        self.assertAlmostEqual(60_000.0 / 1_000_000.0, _aging(tables.aging_df, "1-30d", "10/2025"), places=8)
        self.assertAlmostEqual((60_000.0 + 15_000.0 + 5_000.0) / dircred, _indicator(tables.indicators_df, "Vencidos <= 90 d / Crédito", "10/2025"), places=8)
        self.assertAlmostEqual((15_000.0 + 5_000.0 + 4_000.0 + 3_000.0 + 2_000.0 + 1_000.0) / dircred, _indicator(tables.indicators_df, "Vencidos Over 30 d / Crédito", "10/2025"), places=8)
        self.assertAlmostEqual((4_000.0 + 3_000.0 + 2_000.0 + 1_000.0) / dircred, _indicator(tables.indicators_df, "Vencidos Over 90 d / Crédito", "10/2025"), places=8)

    def test_division_by_zero_returns_pd_na(self) -> None:
        wide_df = _fixture_wide_df(pl=0.0, dircred=0.0)
        tables = build_monitoring_tables(wide_df, ["10/2025"], cnpj="12345678000199")

        self.assertTrue(pd.isna(_indicator(tables.indicators_df, "Dir Cred / PL", "10/2025")))
        self.assertTrue(pd.isna(_indicator(tables.indicators_df, "Cotas SR / PL %", "10/2025")))

    def test_manual_overrides_are_loaded_and_merged(self) -> None:
        wide_df = _fixture_wide_df()
        with tempfile.TemporaryDirectory() as tmpdir:
            overrides_dir = Path(tmpdir)
            save_manual_overrides(
                "12.345.678/0001-99",
                {"competencias": {"10/2025": {"vl_total_mz": 33_604_227.58, "rent_mz": 1.02}}},
                overrides_dir=overrides_dir,
            )
            overrides = load_manual_overrides("12345678000199", overrides_dir=overrides_dir)

        tables = build_monitoring_tables(wide_df, ["10/2025"], cnpj="12345678000199", overrides=overrides)

        self.assertAlmostEqual(5.0, _indicator(tables.indicators_df, "Cotas MZ / PL %", "10/2025"), places=2)
        self.assertAlmostEqual(1.02, _indicator(tables.indicators_df, "Rentabilidade MZ % a.m.", "10/2025"), places=2)


def _indicator(frame: pd.DataFrame, label: str, competencia: str) -> object:
    return frame.loc[frame["indicador"] == label, competencia].iloc[0]


def _aging(frame: pd.DataFrame, bucket: str, competencia: str) -> object:
    return frame.loc[frame["bucket"] == bucket, competencia].iloc[0]


def _fixture_wide_df(*, pl: float = 672_084_551.63, dircred: float | None = None) -> pd.DataFrame:
    dircred = pl * 0.9901 if dircred is None else dircred
    sr = pl * 0.8969
    sub = pl * 0.0531
    rows = {
        "DOC_ARQ/LISTA_INFORM/PATRLIQ/VL_SOM_PATRLIQ": pl,
        "DOC_ARQ/LISTA_INFORM/CRED_EXISTE/VL_SOM_DICRED_AQUIS": dircred,
        "DOC_ARQ/LISTA_INFORM/DICRED/VL_DICRED": pd.NA,
        "DOC_ARQ/LISTA_INFORM/CRED_EXISTE/VL_PROVIS_REDUC_RECUP": 53_548.38,
        "DOC_ARQ/LISTA_INFORM/DICRED/VL_DICRED_PROVIS_REDUC_RECUP": pd.NA,
        "DOC_ARQ/LISTA_INFORM/NEGOC_DICRED_MES/DICRED_MES_ALIEN_RECOMP/VL_DICRED_ALIEN": 0.0,
        "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/AMORT/CLASSE_SENIOR/VL_TOTAL": sr,
        "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/AMORT/CLASSE_SUBORD/VL_TOTAL": sub,
        "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/RENT_MES/RENT_CLASSE_SENIOR/PR_APURADA": 1.01,
        "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/RENT_MES/RENT_CLASSE_SUBORD/PR_APURADA": 1.34,
        "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_30": 60_000.0,
        "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_31_60": 15_000.0,
        "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_61_90": 5_000.0,
        "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_91_120": 4_000.0,
        "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_121_150": 3_000.0,
        "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_151_180": 2_000.0,
        "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_181_360": 1_000.0,
    }
    return pd.DataFrame(
        [{"tag_path": tag_path, "10/2025": value} for tag_path, value in rows.items()]
    )


if __name__ == "__main__":
    unittest.main()
