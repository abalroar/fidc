"""Enriquece participantes ativos por CNPJ com cache local incremental."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import file_fingerprint, load_dataframe, save_dataframe  # noqa: E402
from services.participant_registry import build_participant_registry  # noqa: E402


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the incremental participant CNPJ registry.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--structured", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--cnpj", action="append", default=[])
    parser.add_argument("--max-cnpjs", type=int, default=25, help="0 consulta todos os CNPJs sem cache.")
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    structured_path = args.structured or args.industry_dir / "cedentes_structured.csv.gz"
    output_path = args.output or args.industry_dir / "participant_registry.csv.gz"
    cache_dir = args.cache_dir or args.industry_dir / "participant_registry_cache"
    manifest_path = args.manifest or args.industry_dir / "industry_participant_registry_manifest.json"
    structured = load_dataframe(structured_path)
    existing = load_dataframe(output_path)
    registry, quality = build_participant_registry(
        structured,
        cache_dir=cache_dir,
        existing=existing,
        requested_cnpjs=args.cnpj,
        max_network_requests=max(int(args.max_cnpjs), 0),
        refresh=args.refresh,
        sleep_seconds=max(float(args.sleep_seconds), 0.0),
    )
    save_dataframe(registry, output_path)
    manifest = {
        "schema_version": "industry-participant-registry-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_participant_registry",
        "design_constraints": {
            "incremental": True,
            "cache_redacted": True,
            "notes": [
                "O cache persiste somente campos cadastrais necessários; QSA, telefone, e-mail e endereço não são armazenados.",
                "Setor usa a seção CNAE e segmento usa a descrição do CNAE principal.",
                "Raiz de CNPJ não é tratada como grupo econômico; grupo permanece sujeito a curadoria.",
            ],
        },
        "inputs": {"cedentes_structured": file_fingerprint(structured_path)},
        "outputs": {
            "participant_registry": file_fingerprint(output_path),
            "cache_dir": file_fingerprint(cache_dir),
            "manifest": {"path": str(manifest_path)},
        },
        "quality": quality,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[ok] registry gravado em {output_path} "
        f"({quality['ok']:,}/{quality['targets']:,} CNPJs; {quality['pending']:,} pendentes; {quality['errors']:,} erros)"
    )
    print(f"[ok] rede: {quality['network_requests']:,} consultas; cache: {quality['cache_hits']:,} hits")
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
