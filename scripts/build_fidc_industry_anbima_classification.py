"""Materialize the official public ANBIMA FIDC classification workbook.

The source workbook must be supplied explicitly.  The script intentionally
does not crawl or automate ANBIMA Data; it only transforms a manually obtained
official attachment into a compact, auditable cache used by the application.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_anbima import build_public_anbima_fidc_mapping  # noqa: E402


DEFAULT_OUTPUT = Path("data/industry_study/industry_anbima_classification.csv.gz")
DEFAULT_MANIFEST = Path("data/industry_study/industry_anbima_classification_manifest.json")
DEFAULT_VEHICLE_MONTHLY = Path("data/industry_study/vehicle_monthly.csv.gz")
SOURCE_CATALOG = "https://data.anbima.com.br/datasets"
SOURCE_PAGE = "https://data.anbima.com.br/datasets/fundos-175-caracteristicas-publico/detalhes"
SOURCE_ATTACHMENT = "https://data-strapi.prd.anbima.com.br/uploads/fundos_175_caracteristicas_publico_29_12_bf94e071bd.xlsx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xlsx", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--vehicle-monthly", type=Path, default=DEFAULT_VEHICLE_MONTHLY)
    parser.add_argument("--source-url", default=SOURCE_PAGE)
    parser.add_argument("--attachment-url", default=SOURCE_ATTACHMENT)
    parser.add_argument("--published-date", default="2025-12-29")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cnpj(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(14)[-14:] if digits else ""


def _coverage_by_competence(mapping: pd.DataFrame, vehicle_path: Path) -> list[dict[str, object]]:
    if not vehicle_path.exists():
        return []
    vehicle = pd.read_csv(vehicle_path, low_memory=False)
    if not {"competencia", "cnpj", "pl"}.issubset(vehicle.columns):
        return []
    published = mapping[mapping["mapping_status"].eq("publicada")]
    aliases = {
        _cnpj(value)
        for column in ("cnpj_classe", "cnpj_fundo")
        for value in published[column]
        if _cnpj(value)
    }
    rows: list[dict[str, object]] = []
    for competence in ("2024-12", "2025-12", "2026-05"):
        frame = vehicle[vehicle["competencia"].astype(str).eq(competence)].copy()
        if frame.empty:
            continue
        matched = frame["cnpj"].map(_cnpj).isin(aliases)
        pl = pd.to_numeric(frame["pl"], errors="coerce")
        total_pl = float(pl.sum(min_count=1))
        matched_pl = float(pl[matched].sum(min_count=1))
        rows.append(
            {
                "competencia": competence,
                "reporting_rows": int(len(frame)),
                "matched_rows": int(matched.sum()),
                "row_coverage": float(matched.mean()),
                "pl_brl": total_pl,
                "matched_pl_brl": matched_pl,
                "pl_coverage": matched_pl / total_pl if total_pl else None,
            }
        )
    return rows


def main() -> None:
    args = parse_args()
    if not args.source_xlsx.exists():
        raise SystemExit(f"Planilha ANBIMA não encontrada: {args.source_xlsx}")
    source = pd.read_excel(args.source_xlsx, sheet_name="Consulta1", dtype=str)
    mapping = build_public_anbima_fidc_mapping(source)
    mapping["source_snapshot_date"] = args.published_date
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(args.output, index=False, compression="gzip")

    fidc_source = source[source["Categoria ANBIMA"].astype(str).str.strip().str.upper().eq("FIDC")]
    source_max_activity = pd.to_datetime(
        fidc_source["Data de Início de Atividade"], errors="coerce"
    ).max()

    manifest = {
        "schema_version": "industry-anbima-classification/v1",
        "normalization_version": "official-anbima-whitelist/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_catalog_url": SOURCE_CATALOG,
        "source_detail_url": args.source_url,
        "source_attachment_url": args.attachment_url,
        "source_published_date": args.published_date,
        "source_filename": args.source_xlsx.name,
        "source_sha256": sha256(args.source_xlsx),
        "source_rows": int(len(source)),
        "source_fidc_rows": int(len(fidc_source)),
        "source_max_activity_start": (
            source_max_activity.date().isoformat() if pd.notna(source_max_activity) else None
        ),
        "fidc_mapping_rows": int(len(mapping)),
        "published_rows": int(mapping["mapping_status"].eq("publicada").sum()),
        "conflict_rows": int(mapping["mapping_status"].ne("publicada").sum()),
        "active_rows": int(mapping["status_anbima"].eq("Ativo").sum()),
        "selection_rule": (
            "registros ativos têm precedência; conflitos no mesmo nível permanecem N/D; "
            "tipo/foco passam por whitelist da Deliberação ANBIMA nº 72"
        ),
        "cvm_join_coverage": _coverage_by_competence(mapping, args.vehicle_monthly),
        "notes": [
            "PL e competências vêm do Informe Mensal FIDC/CVM; este artefato fornece somente tipo e foco ANBIMA.",
            "Registros repetidos são colapsados por CNPJ de classe; conflitos permanecem explícitos.",
            "A atualização automática integral requer o ANBIMA Feed autenticado.",
        ],
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[ok] ANBIMA FIDC: {len(mapping):,} classes; "
        f"{manifest['published_rows']:,} publicadas; {manifest['conflict_rows']:,} conflitos"
    )


if __name__ == "__main__":
    main()
