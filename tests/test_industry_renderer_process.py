"""Renderer process limits and durable phase diagnostics, without rendering Office files."""

from pathlib import Path
import subprocess

import pytest

from scripts import publish_fidc_revision_bundle as publisher


def _builder_args(tmp_path: Path) -> dict:
    output = tmp_path / "exports"
    output.mkdir()
    args = {
        "node": tmp_path / "node",
        "artifact_script": tmp_path / "renderer.mjs",
        "provider_flow_builder": tmp_path / "flow.mjs",
        "node_modules": tmp_path / "node_modules",
        "data_dir": tmp_path / "data",
        "input_workbook": tmp_path / "input.xlsx",
        "revision_dir": tmp_path / "revision",
        "payload_path": tmp_path / "payload.json",
        "output_dir": output,
        "pptx_path": output / "industry.pptx",
        "xlsx_path": output / "industry.xlsx",
        "portfolio_xlsx_path": output / "portfolio.xlsx",
        "top100_xlsx_path": output / "top100.xlsx",
        "html_path": output / "industry.html",
        "renderer_manifest_path": output / "renderer.json",
        "timeout_seconds": 120,
    }
    for name in (
        "pptx_path", "xlsx_path", "portfolio_xlsx_path", "top100_xlsx_path",
        "html_path", "renderer_manifest_path",
    ):
        args[name].write_bytes(b"mock renderer output")
    return args


@pytest.mark.parametrize(
    ("configured", "expected"),
    [(None, "12288"), ("2048", "2048"), ("16384", "16384"), ("24576", "24576")],
)
def test_renderer_heap_and_success_logs(tmp_path, monkeypatch, configured, expected):
    args = _builder_args(tmp_path)
    if configured is None:
        monkeypatch.delenv("FIDC_XLSX_HEAP_MB", raising=False)
    else:
        monkeypatch.setenv("FIDC_XLSX_HEAP_MB", configured)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        kwargs["stdout"].write(f"complete stdout {len(calls)}\n".encode())
        kwargs["stderr"].write(f"complete stderr {len(calls)}\n".encode())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(publisher.subprocess, "run", run)
    publisher._run_artifact_builder(**args)

    assert [call[0][1] for call in calls] == [
        "--max-old-space-size=4096", f"--max-old-space-size={expected}",
    ]
    assert calls[0][1]["env"]["FIDC_SKIP_WORKBOOK"] == "1"
    assert calls[1][1]["env"]["FIDC_SKIP_PRESENTATION"] == "1"
    assert calls[1][1]["env"]["FIDC_WRITE_MANIFEST"] == "1"
    for index, phase in enumerate(("pptx", "xlsx"), 1):
        assert (args["output_dir"] / f"renderer_{phase}.stdout.log").read_bytes() == (
            f"complete stdout {index}\n".encode()
        )
        assert (args["output_dir"] / f"renderer_{phase}.stderr.log").read_bytes() == (
            f"complete stderr {index}\n".encode()
        )
    assert all(call[1]["timeout"] == 120 for call in calls)


@pytest.mark.parametrize("configured", ["", "abc", "8192.0", "2047", "24577", "-4096", "1e4"])
def test_renderer_rejects_invalid_heap_before_start(tmp_path, monkeypatch, configured):
    args = _builder_args(tmp_path)
    monkeypatch.setenv("FIDC_XLSX_HEAP_MB", configured)
    calls = []
    monkeypatch.setattr(publisher.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    with pytest.raises(publisher.RevisionBundlePublishError, match="FIDC_XLSX_HEAP_MB.*2048.*24576"):
        publisher._run_artifact_builder(**args)

    assert calls == []


@pytest.mark.parametrize(("phase", "failure_index"), [("PPTX", 1), ("XLSX", 2)])
def test_renderer_failure_keeps_full_logs_and_header_and_tail(tmp_path, monkeypatch, phase, failure_index):
    args = _builder_args(tmp_path)
    monkeypatch.delenv("FIDC_XLSX_HEAP_MB", raising=False)
    stdout = b"complete progress output\n" * 300
    stderr = b"FATAL ERROR: Reached heap limit\n" + b"middle trace\n" * 1000 + b"FINAL TRACE: process aborted\n"
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        kwargs["stdout"].write(stdout)
        kwargs["stderr"].write(stderr)
        return subprocess.CompletedProcess(command, 134 if len(calls) == failure_index else 0)

    monkeypatch.setattr(publisher.subprocess, "run", run)
    with pytest.raises(publisher.RevisionBundlePublishError) as error:
        publisher._run_artifact_builder(**args)

    stdout_path = args["output_dir"] / f"renderer_{phase.lower()}.stdout.log"
    stderr_path = args["output_dir"] / f"renderer_{phase.lower()}.stderr.log"
    message = str(error.value)
    assert stdout_path.read_bytes() == stdout
    assert stderr_path.read_bytes() == stderr
    assert "FATAL ERROR: Reached heap limit" in message
    assert "FINAL TRACE: process aborted" in message
    assert str(stdout_path) in message and str(stderr_path) in message
    assert f"renderer {phase}" in message and "134" in message
    assert len(message) < 3000
    assert len(calls) == failure_index


@pytest.mark.parametrize(("phase", "failure_index"), [("PPTX", 1), ("XLSX", 2)])
def test_renderer_timeout_keeps_partial_logs(tmp_path, monkeypatch, phase, failure_index):
    args = _builder_args(tmp_path)
    monkeypatch.delenv("FIDC_XLSX_HEAP_MB", raising=False)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        kwargs["stdout"].write(b"partial progress before timeout\n")
        kwargs["stderr"].write(b"partial diagnostic before timeout\n")
        if len(calls) == failure_index:
            raise subprocess.TimeoutExpired(command, 120)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(publisher.subprocess, "run", run)
    with pytest.raises(publisher.RevisionBundlePublishError) as error:
        publisher._run_artifact_builder(**args)

    stdout_path = args["output_dir"] / f"renderer_{phase.lower()}.stdout.log"
    stderr_path = args["output_dir"] / f"renderer_{phase.lower()}.stderr.log"
    assert stdout_path.read_bytes() == b"partial progress before timeout\n"
    assert stderr_path.read_bytes() == b"partial diagnostic before timeout\n"
    assert f"renderer {phase} excedeu 120s" in str(error.value)
    assert "partial diagnostic before timeout" in str(error.value)
    assert str(stdout_path) in str(error.value) and str(stderr_path) in str(error.value)
    assert isinstance(error.value.__cause__, subprocess.TimeoutExpired)
    assert len(calls) == failure_index


def test_renderer_failure_uses_stdout_when_stderr_is_empty(tmp_path, monkeypatch):
    args = _builder_args(tmp_path)
    monkeypatch.delenv("FIDC_XLSX_HEAP_MB", raising=False)

    def run(command, **kwargs):
        kwargs["stdout"].write(b"actual diagnostic on stdout\n")
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(publisher.subprocess, "run", run)
    with pytest.raises(publisher.RevisionBundlePublishError, match="actual diagnostic on stdout"):
        publisher._run_artifact_builder(**args)
