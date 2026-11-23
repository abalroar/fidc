"""Vencidos / PL: the regulation view of overdue receivables, next to the DC view."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone
from io import BytesIO
import unittest

import pandas as pd
from pptx import Presentation

from services.fundonet_dashboard import FundonetDashboardData, attach_pl_denominator
from services.fundonet_ppt_export import (
    _build_over_pl_history_for_ppt,
    _over_pl_latest_table_for_ppt,
    build_dashboard_pptx_bytes,
)

COMPETENCIAS = ["01/2026", "02/2026", "03/2026"]


def _over_frame(statuses: dict[str, str] | None = None) -> pd.DataFrame:
    statuses = statuses or {}
    rows = []
    for competencia in COMPETENCIAS:
        for ordem, (serie, valor) in enumerate([("Over 1", 120.0), ("Over 30", 80.0), ("Over 90", 40.0)], start=1):
            rows.append(
                {
                    "competencia": competencia,
                    "competencia_dt": pd.Timestamp(f"{competencia[3:]}-{competencia[:2]}-01"),
                    "ordem": ordem,
                    "serie": serie,
                    "valor": valor,
                    "percentual": valor / 2_000.0 * 100.0,
                    "calculo_status": statuses.get(competencia, "calculado"),
                    "denominador_fonte": "malha_vencimento",
                }
            )
    return pd.DataFrame(rows)


def _history_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "competencia": COMPETENCIAS,
            "inadimplencia_total": [120.0, 120.0, 120.0],
            "direitos_creditorios": [2_000.0, 2_000.0, 2_000.0],
        }
    )


def _subordination(pl_values: list[float | None]) -> pd.DataFrame:
    return pd.DataFrame({"competencia": COMPETENCIAS, "pl_total": pl_values})


class AttachPlDenominatorTests(unittest.TestCase):
    def test_same_numerator_divided_by_pl(self) -> None:
        history, over = attach_pl_denominator(
            default_history_df=_history_frame(),
            default_over_history_df=_over_frame(),
            subordination_history_df=_subordination([1_500.0, 1_500.0, 1_500.0]),
        )
        self.assertAlmostEqual(120.0 / 1_500.0 * 100.0, history["inadimplencia_pct_pl"].iloc[-1])
        over_30 = over[(over["serie"] == "Over 30") & (over["competencia"] == "03/2026")].iloc[0]
        self.assertAlmostEqual(80.0 / 1_500.0 * 100.0, over_30["percentual_pl"])
        # DC view untouched.
        self.assertAlmostEqual(80.0 / 2_000.0 * 100.0, over_30["percentual"])
        self.assertEqual("calculado", over_30["calculo_status_pl"])

    def test_missing_or_non_positive_pl_is_na_not_zero(self) -> None:
        history, over = attach_pl_denominator(
            default_history_df=_history_frame(),
            default_over_history_df=_over_frame(),
            subordination_history_df=_subordination([None, 0.0, 1_500.0]),
        )
        self.assertTrue(pd.isna(history["inadimplencia_pct_pl"].iloc[0]))
        self.assertTrue(pd.isna(history["inadimplencia_pct_pl"].iloc[1]))
        no_pl = over[over["competencia"].isin(["01/2026", "02/2026"])]
        self.assertTrue(no_pl["percentual_pl"].isna().all())
        self.assertEqual({"sem_pl"}, set(no_pl["calculo_status_pl"]))

    def test_incomplete_buckets_stay_na_but_missing_dc_denominator_does_not_block_pl(self) -> None:
        _, over = attach_pl_denominator(
            default_history_df=_history_frame(),
            default_over_history_df=_over_frame({"01/2026": "bucket_incompleto", "02/2026": "sem_denominador"}),
            subordination_history_df=_subordination([1_500.0, 1_500.0, 1_500.0]),
        )
        jan = over[over["competencia"] == "01/2026"]
        self.assertTrue(jan["percentual_pl"].isna().all())
        self.assertEqual({"bucket_incompleto"}, set(jan["calculo_status_pl"]))
        feb = over[over["competencia"] == "02/2026"]
        self.assertTrue(feb["percentual_pl"].notna().all())

    def test_empty_frames_keep_contract_columns(self) -> None:
        history, over = attach_pl_denominator(
            default_history_df=pd.DataFrame(columns=["competencia", "inadimplencia_total"]),
            default_over_history_df=pd.DataFrame(columns=["competencia", "serie", "valor", "calculo_status"]),
            subordination_history_df=pd.DataFrame(),
        )
        self.assertIn("inadimplencia_pct_pl", history.columns)
        self.assertTrue({"pl_total", "percentual_pl", "calculo_status_pl"} <= set(over.columns))


def _dashboard(over_df: pd.DataFrame) -> FundonetDashboardData:
    kwargs = {field.name: pd.DataFrame() for field in fields(FundonetDashboardData) if field.name.endswith("_df")}
    kwargs.update(
        competencias=COMPETENCIAS,
        latest_competencia="03/2026",
        fund_info={"nome_fundo": "FIDC Teste", "periodo_analisado": "01/2026 a 03/2026"},
        summary={"pl_total": 1_500.0},
        methodology_notes=[],
        default_over_history_df=over_df,
    )
    return FundonetDashboardData(**kwargs)


def _slide_titles(payload: bytes) -> list[str]:
    titles = []
    for slide in Presentation(BytesIO(payload)).slides:
        texts = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame and shape.text_frame.text.strip()]
        titles.append(texts[0] if texts else "")
    return titles


class VencidosPlPptTests(unittest.TestCase):
    def _over_with_pl(self) -> pd.DataFrame:
        _, over = attach_pl_denominator(
            default_history_df=_history_frame(),
            default_over_history_df=_over_frame(),
            subordination_history_df=_subordination([None, 1_500.0, 1_500.0]),
        )
        return over

    def test_ppt_history_keeps_gap_for_month_without_pl(self) -> None:
        history = _build_over_pl_history_for_ppt(_dashboard(self._over_with_pl()), max_periods=18)
        self.assertEqual(COMPETENCIAS, history["competencia"].tolist())
        self.assertIsNone(history["Over 30"].iloc[0])
        self.assertAlmostEqual(80.0 / 1_500.0 * 100.0, history["Over 30"].iloc[-1])

    def test_latest_table_shows_both_bases(self) -> None:
        table = _over_pl_latest_table_for_ppt(_dashboard(self._over_with_pl()))
        self.assertEqual(["Série", "Vencido", "% DCs", "% PL"], table.columns.tolist())
        over_30 = table[table["Série"] == "Over 30"].iloc[0]
        self.assertEqual("4,00%", over_30["% DCs"])
        self.assertEqual("5,33%", over_30["% PL"])

    def test_deck_adds_vencidos_pl_slide_after_over(self) -> None:
        payload = build_dashboard_pptx_bytes(
            _dashboard(self._over_with_pl()), generated_at=datetime(2026, 11, 23, tzinfo=timezone.utc),
        )
        titles = _slide_titles(payload)
        self.assertIn("Vencidos / PL", titles)
        self.assertEqual(titles.index("Deterioração acumulada") + 1, titles.index("Vencidos / PL"))

    def test_deck_without_pl_columns_skips_slide(self) -> None:
        payload = build_dashboard_pptx_bytes(
            _dashboard(_over_frame()), generated_at=datetime(2026, 11, 23, tzinfo=timezone.utc),
        )
        self.assertNotIn("Vencidos / PL", _slide_titles(payload))


class VencidosPlDashboardFramesTests(unittest.TestCase):
    def test_chart_frame_drops_months_without_pl_and_table_shows_nd(self) -> None:
        from tabs.tab_fidc_ime import _format_over_pl_latest_table, _over_pl_chart_frame

        _, over = attach_pl_denominator(
            default_history_df=_history_frame(),
            default_over_history_df=_over_frame(),
            subordination_history_df=_subordination([None, 1_500.0, None]),
        )
        chart = _over_pl_chart_frame(over)
        self.assertEqual({"02/2026"}, set(chart["competencia"]))
        table = _format_over_pl_latest_table(over, "03/2026")
        self.assertEqual({"N/D"}, set(table["% do PL"]))
        self.assertEqual("Over 1 (total)", table["Série"].iloc[0])


if __name__ == "__main__":
    unittest.main()


class VencidosPlPortfolioDeckTests(unittest.TestCase):
    """Portfolio deck: PL view beside the gross-portfolio view, from the monthly base."""

    def _kwargs(self, *, with_pl: bool):
        from tests.test_portfolio_ppt_export import _inputs

        kwargs = _inputs(months=13)
        if with_pl:
            for mapping in (kwargs["outputs"].fund_monthly, kwargs["monitor_outputs"].fund_monitor):
                for frame in mapping.values():
                    frame["npl_over30_pct"] = 8.0
                    frame["npl_over90_pct"] = 4.0
                    frame["npl_over30_pl_pct"] = 9.5
                    frame["npl_over90_pl_pct"] = 4.75
            for frame in (kwargs["outputs"].consolidated_monthly, kwargs["monitor_outputs"].consolidated_monitor):
                frame["npl_over30_pct"], frame["npl_over90_pct"] = 8.0, 4.0
                frame["npl_over30_pl_pct"], frame["npl_over90_pl_pct"] = 9.5, 4.75
        return kwargs

    @staticmethod
    def _block_titles(spec) -> list[str]:
        return [str(getattr(block, "title", "")) for page in spec.slides for block in page.blocks]

    def test_deck_shows_pl_and_gross_portfolio_charts_and_pl_table(self) -> None:
        from tests.test_portfolio_ppt_export import _spec

        titles = self._block_titles(_spec(self._kwargs(with_pl=True)))
        self.assertIn("Atraso acumulado / PL · %", titles)
        self.assertIn("Atraso acumulado / carteira bruta · %", titles)
        self.assertIn("Atraso e provisão · Atraso acumulado / PL · %", titles)

    def test_deck_without_pl_columns_has_no_empty_pl_blocks(self) -> None:
        from tests.test_portfolio_ppt_export import _spec

        titles = self._block_titles(_spec(self._kwargs(with_pl=False)))
        self.assertFalse(any("/ PL" in title for title in titles))
