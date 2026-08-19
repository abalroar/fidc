"""Materialized case-study deck exposed by Dados da Indústria."""

from __future__ import annotations

from pathlib import Path


CASE_STUDIES_PPTX_NAME = "fidc_case_studies.pptx"
CASE_STUDIES_PROMPT_NAME = "fidc_case_studies_prompt.md"


def _revision_dir(data_dir: str | Path) -> Path:
    return Path(data_dir).resolve() / "generated_revision"


def build_case_studies_deck_bytes(data_dir: str | Path) -> bytes:
    """Return the validated materialized PowerPoint payload."""

    path = _revision_dir(data_dir) / CASE_STUDIES_PPTX_NAME
    payload = path.read_bytes()
    if not payload.startswith(b"PK"):
        raise ValueError(f"PPTX de estudos de caso inválido: {path}")
    return payload


def load_case_studies_prompt(data_dir: str | Path) -> str:
    """Return the reproducible prompt displayed next to the download."""

    path = _revision_dir(data_dir) / CASE_STUDIES_PROMPT_NAME
    prompt = path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"Prompt de estudos de caso vazio: {path}")
    return prompt
