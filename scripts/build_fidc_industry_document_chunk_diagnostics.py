"""Diagnostica documentos de um chunk da aba Industria.

O script executa uma passada leve por um unico chunk documental: verifica
existencia local, tenta ler caches de texto/JSON e amostra as primeiras paginas
dos PDFs para separar arquivos com texto extraivel de PDFs que precisam OCR.

Uso:
    python scripts/build_fidc_industry_document_chunk_diagnostics.py --chunk-id doc-0001
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (
    build_document_chunk_diagnostics,
    build_document_chunk_diagnostics_manifest,
    build_document_chunk_run_summary,
    load_dataframe,
    merge_document_chunk_diagnostics,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe one document chunk and accumulate diagnostics.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--inventory", type=Path, default=None)
    parser.add_argument("--chunk-plan", type=Path, default=None)
    parser.add_argument("--diagnostics-output", type=Path, default=None)
    parser.add_argument("--run-summary-output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--chunk-id", type=str, default="")
    parser.add_argument("--max-text-chars", type=int, default=2000)
    parser.add_argument("--max-pdf-pages", type=int, default=2)
    return parser.parse_args()


def _select_chunk_id(inventory, chunk_plan, existing, requested: str) -> str:
    requested = str(requested or "").strip()
    if requested:
        return requested
    if chunk_plan is not None and not chunk_plan.empty and "chunk_id" in chunk_plan.columns:
        chunks = [value for value in chunk_plan["chunk_id"].fillna("").astype(str).tolist() if value]
    elif inventory is not None and not inventory.empty and "chunk_id" in inventory.columns:
        chunks = [value for value in inventory["chunk_id"].fillna("").astype(str).tolist() if value]
    else:
        chunks = []
    chunks = list(dict.fromkeys(chunks))
    if not chunks:
        return ""
    processed = set()
    if existing is not None and not existing.empty and "chunk_id" in existing.columns:
        processed = set(existing["chunk_id"].fillna("").astype(str))
    for chunk_id in chunks:
        if chunk_id not in processed:
            return chunk_id
    return chunks[0]


def main() -> None:
    args = parse_args()
    inventory_path = args.inventory or args.industry_dir / "document_inventory.csv.gz"
    chunk_plan_path = args.chunk_plan or args.industry_dir / "document_chunk_plan.csv"
    diagnostics_path = args.diagnostics_output or args.industry_dir / "document_chunk_diagnostics.csv.gz"
    run_summary_path = args.run_summary_output or args.industry_dir / "document_chunk_run_summary.csv"
    manifest_path = args.manifest or args.industry_dir / "industry_document_chunk_diagnostics_manifest.json"

    inventory = load_dataframe(inventory_path)
    chunk_plan = load_dataframe(chunk_plan_path)
    existing = load_dataframe(diagnostics_path)
    chunk_id = _select_chunk_id(inventory, chunk_plan, existing, args.chunk_id)
    if not chunk_id:
        raise SystemExit("Nenhum chunk documental encontrado. Rode scripts/build_fidc_industry_documents.py primeiro.")
    if inventory.empty or "chunk_id" not in inventory.columns:
        raise SystemExit(f"Inventario documental sem coluna chunk_id: {inventory_path}")
    if not inventory["chunk_id"].fillna("").astype(str).eq(chunk_id).any():
        available = ", ".join(inventory["chunk_id"].fillna("").astype(str).drop_duplicates().head(8).tolist())
        raise SystemExit(f"Chunk {chunk_id!r} nao encontrado no inventario. Exemplos: {available or 'nenhum'}")

    current = build_document_chunk_diagnostics(
        inventory,
        chunk_id=chunk_id,
        root=ROOT,
        max_text_chars=args.max_text_chars,
        max_pdf_pages=args.max_pdf_pages,
    )
    diagnostics = merge_document_chunk_diagnostics(existing, current)
    run_summary = build_document_chunk_run_summary(diagnostics, chunk_plan)
    save_dataframe(diagnostics, diagnostics_path)
    save_dataframe(run_summary, run_summary_path)
    manifest = build_document_chunk_diagnostics_manifest(
        industry_dir=args.industry_dir,
        diagnostics_path=diagnostics_path,
        run_summary_path=run_summary_path,
        manifest_path=manifest_path,
        diagnostics=diagnostics,
        run_summary=run_summary,
        chunk_plan=chunk_plan,
        chunk_id=chunk_id,
    )
    save_pipeline_manifest(manifest, manifest_path)

    quality = manifest.get("quality", {})
    print(f"[ok] chunk diagnosticado: {chunk_id} ({len(current):,} documentos nesta execucao)")
    print(
        f"[ok] diagnosticos acumulados em {diagnostics_path} "
        f"({quality.get('diagnostics_rows', 0):,} documentos; "
        f"{quality.get('processed_chunks', 0)}/{quality.get('total_chunks', 0)} chunks)"
    )
    print(
        f"[ok] texto detectado em {quality.get('docs_with_text', 0):,} docs; "
        f"PDFs para OCR: {quality.get('pdf_needs_ocr_docs', 0):,}; "
        f"erros: {quality.get('error_docs', 0):,}"
    )
    print(f"[ok] resumo gravado em {run_summary_path}")
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
