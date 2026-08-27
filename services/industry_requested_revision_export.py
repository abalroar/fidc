"""Validated, dated supplement; keep the canonical industry bundle unchanged."""

from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


RELEASE_DIR = "director_revision_20260827"
RELEASE_SCHEMA = "fidc.director_revision_release.v1"
DOWNLOADS = {
    "complete": "Industria_FIDC_Completa_Revisada_20260827.pptx",
    "slides": "FIDC_Revisao_Diretoria_20260827.pptx",
    "package": "FIDC_Revisao_Diretoria_20260827.zip",
}
REPORT_NAME = "Relatorio_Revisao_Diretoria.md"


def _safe_path(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Caminho inválido no manifesto da revisão")
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Arquivo fora da revisão")
    return target


def _check_digest(payload: bytes, spec: dict, name: str) -> None:
    if len(payload) != spec["bytes"] or hashlib.sha256(payload).hexdigest() != spec["sha256"]:
        raise ValueError(f"Arquivo da revisão divergente do manifesto: {name}")


def _validate_deck(payload: bytes, expected_slides: int) -> None:
    try:
        with ZipFile(BytesIO(payload)) as archive:
            slides = [n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
            ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
            sequence = ET.fromstring(archive.read("ppt/presentation.xml")).findall("p:sldIdLst/p:sldId", ns)
            if len(slides) != expected_slides or len(sequence) != expected_slides:
                raise ValueError("Quantidade de slides inválida na revisão")
            text = " ".join(archive.read(n).decode("utf-8") for n in slides)
            for required in ("Itaú e Kanastra separados", "Sem TAPSO e Sistema Petrobras", "pulverizado validado = N/D"):
                if required not in text:
                    raise ValueError(f"Conteúdo obrigatório ausente: {required}")
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError("PPTX da revisão inválido") from exc


def load_requested_revision_downloads(data_dir: str | Path) -> dict[str, bytes]:
    """Read and validate the whole dated release before exposing any download.

    No Streamlit cache is used: a changed or damaged file cannot leave cached
    bytes enabled. The release explicitly retains its June 2026 snapshot even
    when the independently maintained main industry bundle advances.
    """
    root = Path(data_dir) / RELEASE_DIR
    manifest = json.loads((root / "release.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != RELEASE_SCHEMA or manifest.get("competencia") != "2026-06":
        raise ValueError("Manifesto incompatível da revisão da diretoria")
    expected_files = set(DOWNLOADS.values()) | {REPORT_NAME}
    if set(manifest.get("files", {})) != expected_files:
        raise ValueError("Pacote incompleto da revisão da diretoria")
    files = {}
    for name, spec in manifest["files"].items():
        payload = _safe_path(root, name).read_bytes()
        _check_digest(payload, spec, name)
        files[name] = payload
    _validate_deck(files[DOWNLOADS["complete"]], 39)
    _validate_deck(files[DOWNLOADS["slides"]], 3)
    try:
        with ZipFile(BytesIO(files[DOWNLOADS["package"]])) as archive:
            members = manifest["package_members"]
            if set(archive.namelist()) != set(members):
                raise ValueError("Conteúdo do ZIP divergente do manifesto")
            for name, spec in members.items():
                _safe_path(root, name)
                _check_digest(archive.read(name), spec, name)
            for name in (DOWNLOADS["complete"], DOWNLOADS["slides"], REPORT_NAME):
                if archive.read(name) != files[name]:
                    raise ValueError("ZIP e arquivos avulsos da revisão divergem")
    except (BadZipFile, KeyError) as exc:
        raise ValueError("ZIP da revisão inválido") from exc
    return {key: files[name] for key, name in DOWNLOADS.items()}
