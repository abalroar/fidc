"""Package the approved director revision as a validated, dated site download."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.industry_requested_revision_export import (
    DOWNLOADS, RELEASE_DIR, RELEASE_SCHEMA, REPORT_NAME,
    load_requested_revision_downloads,
)


def digest(payload: bytes) -> dict:
    return {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/industry_study")
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.data_dir / RELEASE_DIR
    if destination.exists():
        raise SystemExit("Release datada já existe; não sobrescrever")
    manifest = json.loads((source / "bases/manifest.json").read_text())
    for name, spec in manifest["outputs"].items():
        require(digest((source / "bases" / name).read_bytes())["sha256"] == spec["sha256"], f"Base divergente: {name}")
    for spec in manifest["inputs"]:
        path = args.data_dir / spec["path"]
        require(digest(path.read_bytes())["sha256"] == spec["sha256"], f"Insumo divergente: {path}")
    qa = json.loads((source / "qa/auditoria_entrega.json").read_text())
    require(qa["status"] == "pass", "Auditoria de dados não aprovada")
    original_deck = args.data_dir / "generated_revision/industry_executive_revised.pptx"
    require(digest(original_deck.read_bytes())["sha256"] == qa["source_sha256"], "PPTX de origem mudou desde a revisão")
    for key, field in (("complete", "full_sha256"), ("slides", "compact_sha256")):
        require(digest((source / DOWNLOADS[key]).read_bytes())["sha256"] == qa[field], "PPTX mudou desde a auditoria")
    fidelity = json.loads((source / "qa/fidelidade_apresentacao_completa.json").read_text())
    require(fidelity["status"] == "pass", "Fidelidade do PPTX não aprovada")
    require("Test passed" in (source / "qa/overflow_apresentacao_completa.txt").read_text(), "Verificação de overflow não aprovada")

    members = {}
    for name in (DOWNLOADS["complete"], DOWNLOADS["slides"], REPORT_NAME):
        members[name] = (source / name).read_bytes()
    for folder in ("bases", "qa"):
        for path in sorted((source / folder).iterdir()):
            if path.suffix not in {".csv", ".json", ".md", ".txt"}:
                continue
            if path.name in {"mapeamento_slides.json"}:
                continue
            members[str(path.relative_to(source))] = path.read_bytes()
    # Keep provenance portable; local workstation paths are not public sources.
    for name, payload in list(members.items()):
        if name.endswith(".pptx"):
            continue
        text = payload.decode("utf-8")
        for prefix in (str(ROOT) + "/", str(Path.home() / "fidc") + "/"):
            text = text.replace(prefix, "")
        if "/Users/" in text:
            raise ValueError(f"Caminho local não tratado: {name}")
        members[name] = text.encode("utf-8")
    # Sanitized QA/report files have new hashes; the CSV manifest stays exact.
    for name, spec in manifest["outputs"].items():
        require(digest(members[f"bases/{name}"])["sha256"] == spec["sha256"], f"Base alterada ao preparar release: {name}")

    args.data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="director-release-", dir=args.data_dir) as temporary:
        parent = Path(temporary)
        stage = parent / RELEASE_DIR
        stage.mkdir()
        for name in (DOWNLOADS["complete"], DOWNLOADS["slides"], REPORT_NAME):
            (stage / name).write_bytes(members[name])
        with ZipFile(stage / DOWNLOADS["package"], "w", ZIP_DEFLATED) as archive:
            for name, payload in sorted(members.items()):
                archive.writestr(name, payload)
        release = {
            "schema": RELEASE_SCHEMA,
            "revision_date": "2026-08-27",
            "competencia": "2026-06",
            "scope": "Suplemento datado; preserva o bundle canônico e seus anexos dinâmicos.",
            "pulverizacao_validada": "N/D",
            "source_pptx_sha256": qa["source_sha256"],
            "files": {name: digest((stage / name).read_bytes()) for name in (*DOWNLOADS.values(), REPORT_NAME)},
            "package_members": {name: digest(payload) for name, payload in sorted(members.items())},
        }
        (stage / "release.json").write_text(json.dumps(release, ensure_ascii=False, indent=2))
        load_requested_revision_downloads(parent)
        stage.rename(destination)
    print(destination)


if __name__ == "__main__":
    main()
