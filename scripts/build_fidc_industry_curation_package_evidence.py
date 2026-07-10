"""Materializa cobertura técnica e próxima ação para cada pacote de curadoria."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (  # noqa: E402
    build_curation_package_evidence_pipeline_manifest,
    build_industry_curation_package_evidence,
    load_cvm_registration_scope,
    load_dataframe,
    load_industry_universe_reviews,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")
DEFAULT_REGISTRATION_ZIP = Path("data/raw/registro_fundo_classe.zip")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build technical evidence coverage for Industry curation packages.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--registration-zip", type=Path, default=DEFAULT_REGISTRATION_ZIP)
    parser.add_argument("--registration-output", type=Path, default=None)
    parser.add_argument(
        "--refresh-registration",
        action="store_true",
        help="Atualizar o cache do cadastro oficial CVM quando o ZIP local não existir.",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = args.output or args.industry_dir / "industry_curation_package_evidence.csv.gz"
    manifest_path = args.manifest or args.industry_dir / "industry_curation_package_evidence_manifest.json"
    registration_output_path = args.registration_output or args.industry_dir / "industry_registration_scope.csv.gz"
    registration_scope = load_cvm_registration_scope(
        args.registration_zip,
        allow_network=args.refresh_registration,
    )
    save_dataframe(registration_scope, registration_output_path)
    evidence = build_industry_curation_package_evidence(
        packages=load_dataframe(args.industry_dir / "industry_curation_packages.csv.gz"),
        registration_scope=registration_scope,
        document_inventory=load_dataframe(args.industry_dir / "document_inventory.csv.gz"),
        document_text_index=load_dataframe(args.industry_dir / "document_text_index.csv.gz"),
        package_document_discovery_status=load_dataframe(
            args.industry_dir / "industry_package_document_discovery_status.csv.gz"
        ),
        alternative_document_status=load_dataframe(
            args.industry_dir / "industry_alternative_document_status.csv.gz"
        ),
        document_field_run_summary=load_dataframe(args.industry_dir / "document_field_run_summary.csv"),
        document_participant_candidates=load_dataframe(
            args.industry_dir / "document_participant_candidates.csv.gz"
        ),
        document_criteria_candidates=load_dataframe(args.industry_dir / "document_criteria_candidates.csv.gz"),
        universe_reviews=load_industry_universe_reviews(args.industry_dir / "universe_scope_reviews.csv"),
        cedentes=load_dataframe(args.industry_dir / "cedentes_structured.csv.gz"),
        criteria=load_dataframe(args.industry_dir / "criteria_structured.csv.gz"),
        dimension_catalog=load_dataframe(args.industry_dir / "industry_dimension_catalog.csv.gz"),
    )
    save_dataframe(evidence, output_path)
    manifest = build_curation_package_evidence_pipeline_manifest(
        industry_dir=args.industry_dir,
        registration_scope_path=registration_output_path,
        output_path=output_path,
        manifest_path=manifest_path,
        evidence=evidence,
    )
    save_pipeline_manifest(manifest, manifest_path)
    quality = manifest.get("quality", {})
    print(
        f"[ok] evidência por pacote gravada em {output_path} "
        f"({quality.get('rows', 0):,} pacotes; P0 docs {quality.get('p0_with_documents', 0)}/"
        f"{quality.get('p0_rows', 0)}; P0 texto {quality.get('p0_with_text', 0)}/{quality.get('p0_rows', 0)})"
    )
    print(f"[ok] estágios técnicos: {quality.get('technical_stage_counts', {})}")
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
