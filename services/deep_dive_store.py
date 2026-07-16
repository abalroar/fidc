from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from services.deep_dive_models import DeepDiveManifest, DeepDiveTableSpec


DEFAULT_DEEP_DIVE_ROOT = Path("data/deep_dives")


def list_deep_dives(base_dir: Path = DEFAULT_DEEP_DIVE_ROOT) -> list[DeepDiveManifest]:
    if not base_dir.exists():
        return []
    manifests: list[DeepDiveManifest] = []
    for manifest_path in sorted(base_dir.glob("*/manifest.json")):
        manifest = load_deep_dive_manifest(manifest_path.parent)
        if manifest is not None:
            manifests.append(manifest)
    return sorted(manifests, key=lambda item: (item.title.lower(), item.generated_at), reverse=False)


def load_deep_dive_manifest(package_dir: str | Path) -> DeepDiveManifest | None:
    root = Path(package_dir)
    path = root / "manifest.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return DeepDiveManifest.from_dict(payload, package_dir=root)


def load_deep_dive_table(manifest: DeepDiveManifest, table_spec: DeepDiveTableSpec) -> pd.DataFrame:
    path = manifest.package_dir / table_spec.source_file
    if not path.exists():
        return pd.DataFrame(columns=[table_spec.first_column])
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if frame.empty:
        return pd.DataFrame(columns=[table_spec.first_column])
    if table_spec.first_column not in frame.columns:
        first = frame.columns[0]
        frame = frame.rename(columns={first: table_spec.first_column})
    return frame.fillna("—").replace("", "—")


def deep_dive_matches_portfolio(manifest: DeepDiveManifest, portfolio_id: str | None, portfolio_signature: str | None) -> bool:
    if not portfolio_id and not portfolio_signature:
        return True
    if portfolio_signature and manifest.portfolio_signature:
        return manifest.portfolio_signature == portfolio_signature
    if portfolio_id and manifest.portfolio_id:
        return manifest.portfolio_id == portfolio_id
    return False


def write_deep_dive_index(base_dir: Path = DEFAULT_DEEP_DIVE_ROOT) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    index_path = base_dir / "index.json"
    payload: dict[str, Any] = {
        "deep_dives": [
            {
                "deep_dive_id": manifest.deep_dive_id,
                "title": manifest.title,
                "subtitle": manifest.subtitle,
                "generated_at": manifest.generated_at,
                "portfolio_id": manifest.portfolio_id,
                "portfolio_signature": manifest.portfolio_signature,
                "manifest_path": str((manifest.package_dir / "manifest.json").relative_to(base_dir)),
            }
            for manifest in list_deep_dives(base_dir)
        ]
    }
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return index_path
