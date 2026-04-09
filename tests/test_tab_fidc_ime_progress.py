from __future__ import annotations

from tabs import tab_fidc_ime


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
    """Simula streamlit antigo sem suporte ao parâmetro text."""

    def __init__(self) -> None:
        self.status_box = _DummyStatusBox()

    def empty(self) -> _DummyStatusBox:
        return self.status_box

    def progress(self, value):  # noqa: ANN001
        bar = _DummyProgress()
        bar.values.append(value)
        return bar


def test_init_progress_bar_accepts_legacy_two_arg_call(monkeypatch) -> None:
    stub = _LegacyStreamlitStub()
    monkeypatch.setattr(tab_fidc_ime, "st", stub)

    bar = tab_fidc_ime._init_progress_bar(0.0, "Preparando execução...")

    assert isinstance(bar, _DummyProgress)
    assert bar.values == [0.0]
    assert stub.status_box.messages == ["Preparando execução..."]



def test_build_failure_report_includes_context() -> None:
    context = {"cnpj_informado": "00.000.000/0000-00"}
    report = tab_fidc_ime._build_failure_report(ValueError("entrada inválida"), "tb", context)

    assert report["categoria"] == "Erro de validação de entrada"
    assert report["contexto_execucao"] == context
    assert report["traceback"] == "tb"
