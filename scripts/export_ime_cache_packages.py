from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ime_loader import DEFAULT_PORTABLE_CACHE_ROOT, DEFAULT_RUNTIME_CACHE_ROOT, export_cached_informe_package


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporta caches IME locais para pacotes versionaveis no GitHub.")
    parser.add_argument("--cache-root", default=str(DEFAULT_RUNTIME_CACHE_ROOT), help="Raiz do cache local fundonet-ime.")
    parser.add_argument("--output-root", default=str(DEFAULT_PORTABLE_CACHE_ROOT), help="Destino dos pacotes .zip.")
    parser.add_argument("--cache-key", action="append", default=[], help="Cache key especifica. Pode repetir.")
    args = parser.parse_args()

    cache_root = Path(args.cache_root).resolve()
    output_root = Path(args.output_root).resolve()
    cache_keys = args.cache_key or _discover_cache_keys(cache_root)
    index_rows: list[dict[str, Any]] = []
    for cache_key in cache_keys:
        package_path = export_cached_informe_package(
            cache_key=cache_key,
            cache_root=cache_root,
            output_root=output_root,
        )
        manifest = json.loads((cache_root / cache_key / "manifest.json").read_text(encoding="utf-8"))
        index_rows.append(
            {
                "cache_key": cache_key,
                "cnpj_fundo": manifest.get("cnpj_fundo"),
                "data_inicial": manifest.get("data_inicial"),
                "data_final": manifest.get("data_final"),
                "competencias": len(manifest.get("competencias") or []),
                "package": package_path.name,
                "bytes": package_path.stat().st_size,
            }
        )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "index.json").write_text(json.dumps(index_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(index_rows)} pacote(s) exportado(s) para {output_root}")


def _discover_cache_keys(cache_root: Path) -> list[str]:
    return sorted(path.parent.name for path in cache_root.glob("*/manifest.json"))


if __name__ == "__main__":
    main()
