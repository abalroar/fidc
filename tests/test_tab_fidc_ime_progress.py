from __future__ import annotations

import sys
import types
import unittest
from datetime import datetime
from unittest.mock import patch


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


if __name__ == "__main__":
    unittest.main()
