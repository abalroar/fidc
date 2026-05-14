from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_deep_dive_package import (  # noqa: E402
    OUT_ROOT,
    build_structural_costs_for_funds,
    ensure_structural_cost_table_spec,
)
from services.deep_dive_store import write_deep_dive_index  # noqa: E402


WARNING = (
    "Custos estruturais incluídos a partir de data/regulatory_profiles/structural_costs.csv; "
    "lacunas permanecem explícitas quando não há curadoria documental para o CNPJ."
)


def main() -> None:
    args = parse_args()
    manifest_paths = sorted(args.deep_dive_root.glob("*/manifest.json"))
    if args.deep_dive_id:
        manifest_paths = [path for path in manifest_paths if path.parent.name == args.deep_dive_id]
    if not manifest_paths:
        raise SystemExit("Nenhum manifest.json encontrado para atualizar.")

    updated = 0
    for manifest_path in manifest_paths:
        if update_manifest(manifest_path):
            updated += 1
    write_deep_dive_index(args.deep_dive_root)
    print(f"{updated} pacote(s) Deep Dive atualizados com tabela structural_costs.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Adiciona custos estruturais aos pacotes Deep Dive existentes.")
    parser.add_argument("--deep-dive-root", type=Path, default=OUT_ROOT)
    parser.add_argument("--deep-dive-id", default="", help="Opcional: atualiza apenas um pacote.")
    return parser.parse_args()


def update_manifest(manifest_path: Path) -> bool:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    funds = [item for item in payload.get("funds") or [] if isinstance(item, dict)]
    table = build_structural_costs_for_funds(funds)
    tables_dir = manifest_path.parent / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(tables_dir / "structural_costs.csv", index=False)

    payload["tables"] = ensure_structural_cost_table_spec(payload.get("tables") or [])
    audit = payload.setdefault("audit", {})
    if not isinstance(audit, dict):
        audit = {}
        payload["audit"] = audit
    warnings = [str(item) for item in audit.get("warnings") or [] if str(item).strip()]
    if WARNING not in warnings:
        warnings.append(WARNING)
    audit["warnings"] = warnings

    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{manifest_path.parent.name}: {len(table)} linha(s)")
    return True


if __name__ == "__main__":
    main()
