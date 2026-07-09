from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path


class OCRUnavailableError(RuntimeError):
    """Raised when a requested OCR backend cannot run in this environment."""


def resolve_ocr_engine(engine: str = "auto", *, root: Path | None = None) -> str:
    requested = str(engine or "auto").strip().lower().replace("-", "_")
    if requested in {"", "auto"}:
        if platform.system() == "Darwin" and shutil.which("swift"):
            script = (root or Path(__file__).resolve().parents[1]) / "scripts" / "ocr_pdf_macos_vision.swift"
            if script.exists():
                return "macos_vision"
        return "none"
    if requested in {"none", "off", "disabled"}:
        return "none"
    if requested != "macos_vision":
        raise ValueError(f"Backend OCR não suportado: {engine!r}.")
    script = (root or Path(__file__).resolve().parents[1]) / "scripts" / "ocr_pdf_macos_vision.swift"
    if platform.system() != "Darwin" or not shutil.which("swift") or not script.exists():
        raise OCRUnavailableError("Apple Vision OCR requer macOS, Swift e o helper ocr_pdf_macos_vision.swift.")
    return requested


def ocr_pdf_pages(
    path: Path,
    *,
    engine: str = "auto",
    max_pages: int = 0,
    page_numbers: list[int] | None = None,
    languages: str = "pt-BR,en-US",
    root: Path | None = None,
    timeout_seconds: int = 1800,
) -> dict[str, object]:
    """Extract page-level OCR text using a locally available backend."""

    project_root = root or Path(__file__).resolve().parents[1]
    resolved = resolve_ocr_engine(engine, root=project_root)
    if resolved == "none":
        raise OCRUnavailableError("Nenhum backend OCR disponível.")
    if resolved != "macos_vision":
        raise OCRUnavailableError(f"Backend OCR sem executor: {resolved}.")

    script = project_root / "scripts" / "ocr_pdf_macos_vision.swift"
    command = [
        shutil.which("swift") or "/usr/bin/swift",
        str(script),
        str(path),
        str(max(int(max_pages), 0)),
        str(languages or "pt-BR,en-US"),
        ",".join(str(int(value)) for value in (page_numbers or []) if int(value) > 0),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=max(int(timeout_seconds), 30),
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit={completed.returncode}"
        raise RuntimeError(f"Apple Vision OCR falhou: {detail[:2000]}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Apple Vision OCR retornou JSON inválido: {completed.stdout[:1000]}") from exc

    pages = payload.get("pages", []) if isinstance(payload, dict) else []
    normalized_pages: list[dict[str, object]] = []
    confidences: list[float] = []
    for page in pages if isinstance(pages, list) else []:
        if not isinstance(page, dict):
            continue
        page_number = int(page.get("page_number", 0) or 0)
        text = str(page.get("text", "") or "")
        confidence = float(page.get("confidence", 0.0) or 0.0)
        normalized_pages.append({"page_number": page_number or None, "text": text})
        if text.strip() and confidence > 0:
            confidences.append(confidence)

    errors = payload.get("errors", []) if isinstance(payload, dict) else []
    return {
        "engine": resolved,
        "pages": normalized_pages,
        "page_count": int(payload.get("page_count", len(normalized_pages)) or len(normalized_pages)),
        "pages_processed": int(payload.get("pages_processed", len(normalized_pages)) or len(normalized_pages)),
        "confidence_score": sum(confidences) / len(confidences) if confidences else 0.0,
        "errors": [str(value) for value in errors] if isinstance(errors, list) else [],
    }
