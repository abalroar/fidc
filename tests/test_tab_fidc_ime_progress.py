from __future__ import annotations

import sys
import types
import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd


def _make_streamlit_stub():
    """Return a minimal streamlit stub that exercises the legacy-compat paths."""

    class _DummyStatusBox:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def caption(self, message: str) -> None:
            self.messages.append(message)

    class _DummyProgress:
        def __init__(self) -> None:
            self.values: list[object] = []

        def progress(self, value):  # noqa: ANN001
            self.values.append(value)

    class _LegacyStreamlitStub:
        """Simulates old Streamlit that does not accept the `text` kwarg in progress()."""

        def __init__(self) -> None:
            self.status_box = _DummyStatusBox()
            self._DummyProgress = _DummyProgress

        def empty(self) -> _DummyStatusBox:
            return self.status_box

        def progress(self, value):  # noqa: ANN001
            bar = _DummyProgress()
            bar.values.append(value)
            return bar

    return _LegacyStreamlitStub()


# Inject a minimal stub for the `streamlit` module so the tab can be imported
# in test environments where Streamlit is not installed.
if "streamlit" not in sys.modules:
    _stub_module = types.ModuleType("streamlit")
    _stub_module.progress = lambda *a, **kw: None  # type: ignore[attr-defined]
    _stub_module.empty = lambda: None  # type: ignore[attr-defined]
    _stub_module.caption = lambda *a, **kw: None  # type: ignore[attr-defined]
    sys.modules["streamlit"] = _stub_module

from tabs import tab_fidc_ime  # noqa: E402  (import after stub injection)


class TabFidcImeProgressTests(unittest.TestCase):
    def test_init_progress_bar_accepts_legacy_two_arg_call(self) -> None:
        stub = _make_streamlit_stub()
        with patch.object(tab_fidc_ime, "st", stub):
            bar = tab_fidc_ime._init_progress_bar(0.0, "Preparando execução...")

        self.assertIsInstance(bar, stub._DummyProgress)
        self.assertEqual([0.0], bar.values)
        self.assertEqual(["Preparando execução..."], stub.status_box.messages)

    def test_build_failure_report_includes_context(self) -> None:
        context = {"cnpj_informado": "00.000.000/0000-00"}
        report = tab_fidc_ime._build_failure_report(ValueError("entrada inválida"), "tb", context)

        self.assertEqual("Erro de validação de entrada", report["categoria"])
        self.assertEqual(context, report["contexto_execucao"])
        self.assertEqual("tb", report["traceback"])

    def test_safe_json_bytes_handles_non_serializable_values(self) -> None:
        payload = {"quando": datetime(2026, 4, 9, 12, 30)}

        encoded = tab_fidc_ime._safe_json_bytes(payload)

        self.assertIn(b'"quando"', encoded)
        self.assertIn(b"2026-04-09 12:30:00", encoded)

    def test_line_history_chart_accepts_over_chart_frame_without_duplicate_columns(self) -> None:
        chart_df = pd.DataFrame(
            {
                "competencia": ["03/2026", "03/2026", "04/2026", "04/2026"],
                "competencia_dt": pd.to_datetime(["2026-03-01", "2026-03-01", "2026-04-01", "2026-04-01"]),
                "serie": ["Até 30d", "Over 30", "Até 30d", "Over 30"],
                "valor": [4.2, 7.8, 4.5, 8.1],
            }
        )

        chart = tab_fidc_ime._line_history_chart(
            chart_df,
            title=None,
            y_title="%",
            color_range=tab_fidc_ime.OVER_AGING_CHART_COLORS,
            show_point_labels=False,
        )

        spec = chart.to_dict()
        self.assertEqual("line", spec["mark"]["type"])
        self.assertEqual("valor", spec["encoding"]["y"]["field"])

    def test_altair_compatible_df_ignores_duplicate_column_slices(self) -> None:
        duplicate_df = pd.DataFrame([["A", "B"], ["C", "D"]], columns=["valor", "valor"])

        converted = tab_fidc_ime._altair_compatible_df(duplicate_df)

        self.assertEqual(["valor", "valor"], list(converted.columns))
        self.assertEqual((2, 2), converted.shape)

    def test_altair_compatible_df_handles_single_row_string_columns(self) -> None:
        frame = pd.DataFrame(
            {
                "competencia": pd.Series(["01/2026"], dtype="string"),
                "serie": pd.Series(["Cobertura"], dtype="string"),
                "valor": [500.0],
            }
        )

        converted = tab_fidc_ime._altair_compatible_df(frame)

        self.assertEqual("object", str(converted["competencia"].dtype))
        self.assertEqual("object", str(converted["serie"].dtype))
        self.assertEqual("01/2026", converted.iloc[0]["competencia"])

    def test_grouped_bar_with_rhs_line_chart_preserves_high_coverage_scale(self) -> None:
        bar_df = pd.DataFrame(
            {
                "competencia": ["01/2026", "01/2026"],
                "competencia_dt": pd.to_datetime(["2026-01-01", "2026-01-01"]),
                "serie": ["Inadimplência", "Provisão"],
                "valor": [10.0, 50.0],
            }
        )
        line_df = pd.DataFrame(
            {
                "competencia": ["01/2026"],
                "competencia_dt": pd.to_datetime(["2026-01-01"]),
                "serie": ["Cobertura"],
                "valor": [500.0],
            }
        )

        chart = tab_fidc_ime._grouped_bar_with_rhs_line_chart(
            bar_df,
            line_df,
            title=None,
            bar_y_title="% dos DCs",
            line_y_title="Cobertura (%)",
            reference_value=100.0,
            reference_label="100% (paridade)",
        )

        spec = chart.to_dict()
        rhs_scale = spec["layer"][1]["layer"][1]["encoding"]["y"]["scale"]["domain"]

        self.assertEqual("right", spec["layer"][1]["layer"][1]["encoding"]["y"]["axis"]["orient"])
        self.assertGreaterEqual(rhs_scale[1], 500.0)

    def test_build_line_series_end_labels_df_uses_value_only_labels(self) -> None:
        chart_df = pd.DataFrame(
            {
                "competencia": ["03/2026", "03/2026"],
                "competencia_dt": pd.to_datetime(["2026-03-01", "2026-03-01"]),
                "serie": ["Over 30", "Over 60"],
                "valor": [12.4, 8.1],
                "label_fmt": ["12,4%", "8,1%"],
            }
        )

        labels_df = tab_fidc_ime._build_line_series_end_labels_df(chart_df, y_title="%")

        self.assertEqual(["8,1%", "12,4%"], labels_df["end_label"].tolist())


if __name__ == "__main__":
    unittest.main()
