"""Package the validated 2026-09-01 director revision for site download."""
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
    DOWNLOADS,
    METHODOLOGY_NAME,
    PROMPT_NAME,
    RELEASE_DIR,
    RELEASE_SCHEMA,
    REPORT_NAME,
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
    require(manifest["schema"] == "industry_requested_revision.v2", "Manifesto de bases incompatível")
    for name, spec in manifest["outputs"].items():
        require(
            hashlib.sha256((source / "bases" / name).read_bytes()).hexdigest() == spec["sha256"],
            f"Base divergente: {name}",
        )
    for spec in manifest["inputs"]:
        path = args.data_dir / spec["path"]
        require(hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"], f"Insumo divergente: {path}")

    qa = json.loads((source / "qa/auditoria_entrega.json").read_text())
    require(qa["status"] == "pass", "Auditoria da entrega não aprovada")
    require(
        digest((source / DOWNLOADS["complete"]).read_bytes())["sha256"] == qa["full_sha256"],
        "PPTX completo mudou após a auditoria",
    )
    require(
        digest((source / DOWNLOADS["slides"]).read_bytes())["sha256"] == qa["compact_sha256"],
        "PPTX de lâminas mudou após a auditoria",
    )
    require("Test passed" in (source / "qa/overflow_apresentacao_completa.txt").read_text(), "Overflow no PPTX completo")
    require("Test passed" in (source / "qa/overflow_laminas.txt").read_text(), "Overflow no PPTX de lâminas")

    standalone = (
        DOWNLOADS["complete"],
        DOWNLOADS["slides"],
        REPORT_NAME,
        PROMPT_NAME,
        METHODOLOGY_NAME,
    )
    members: dict[str, bytes] = {name: (source / name).read_bytes() for name in standalone}
    for folder in ("bases", "qa"):
        for path in sorted((source / folder).iterdir()):
            if path.suffix not in {".csv", ".json", ".md", ".txt", ".py"}:
                continue
            members[str(path.relative_to(source))] = path.read_bytes()

    for name, payload in list(members.items()):
        if name.endswith(".pptx"):
            continue
        text = payload.decode("utf-8")
        for prefix in (str(ROOT) + "/", str(Path.home() / "fidc") + "/"):
            text = text.replace(prefix, "")
        if "/Users/" in text:
            raise ValueError(f"Caminho local não tratado: {name}")
        members[name] = text.encode("utf-8")

    args.data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="director-release-", dir=args.data_dir) as temporary:
        stage = Path(temporary) / RELEASE_DIR
        stage.mkdir()
        for name in standalone:
            (stage / name).write_bytes(members[name])
        with ZipFile(stage / DOWNLOADS["package"], "w", ZIP_DEFLATED) as archive:
            for name, payload in sorted(members.items()):
                archive.writestr(name, payload)
        release = {
            "schema": RELEASE_SCHEMA,
            "revision_date": "2026-09-01",
            "competencia": "2026-06",
            "scope": "Slides 4-6, prestadores e apêndice; cenário sem TAPSO/Petrobras; abertura PF/PJ auditável.",
            "stock_scenario": "sem_tapso_petrobras",
            "pfpj_fundos": 24,
            "pfpj_pl_brl": qa["pfpj_pl_brl"],
            "pfpj_exposure_brl": "N/D",
            "pfpj_total_debtors": "N/D",
            "files": {
                name: digest((stage / name).read_bytes())
                for name in (*DOWNLOADS.values(), REPORT_NAME, PROMPT_NAME, METHODOLOGY_NAME)
            },
            "package_members": {
                name: digest(payload) for name, payload in sorted(members.items())
            },
        }
        (stage / "release.json").write_text(json.dumps(release, ensure_ascii=False, indent=2))
        load_requested_revision_downloads(Path(temporary))
        stage.rename(destination)
    print(destination)


if __name__ == "__main__":
    main()
