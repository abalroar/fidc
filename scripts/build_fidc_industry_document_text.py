"""Materializa texto normalizado de um chunk documental da aba Indústria.

Uso:
    python scripts/build_fidc_industry_document_text.py --chunk-id doc-0001

Sem ``--chunk-id``, o primeiro chunk ainda ausente do índice é selecionado.
Caches completos ficam fora do Git; índice, resumo e manifesto são persistidos.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (  # noqa: E402
    build_document_chunk_text_index,
    build_document_text_manifest,
    build_document_text_run_summary,
    load_dataframe,
    merge_document_text_index,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract normalized page text for one Industry document chunk.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--inventory", type=Path, default=None)
    parser.add_argument("--chunk-plan", type=Path, default=None)
    parser.add_argument("--text-index-output", type=Path, default=None)
    parser.add_argument("--run-summary-output", type=Path, default=None)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--chunk-id", type=str, default="")
    parser.add_argument("--max-pdf-pages", type=int, default=0, help="0 processa todas as páginas.")
    parser.add_argument(
        "--ocr-engine",
        choices=["auto", "none", "macos_vision"],
        default="auto",
        help="OCR de fallback para PDFs sem camada textual; auto usa Apple Vision no macOS.",
    )
    parser.add_argument("--ocr-languages", default="pt-BR,en-US")
    parser.add_argument("--force", action="store_true", help="Ignora cache existente do chunk selecionado.")
    return parser.parse_args()


def _select_chunk_id(inventory, chunk_plan, existing, requested: str) -> str:
    requested = str(requested or "").strip()
    if requested:
        return requested
    source = chunk_plan if chunk_plan is not None and not chunk_plan.empty else inventory
    if source is None or source.empty or "chunk_id" not in source.columns:
        return ""
    chunks = [value for value in source["chunk_id"].fillna("").astype(str).tolist() if value]
    chunks = list(dict.fromkeys(chunks))
    processed: set[str] = set()
    if existing is not None and not existing.empty and "chunk_id" in existing.columns:
        processed = set(existing["chunk_id"].fillna("").astype(str))
    for chunk_id in chunks:
        if chunk_id not in processed:
            return chunk_id
    return chunks[0] if chunks else ""


def main() -> None:
    args = parse_args()
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    inventory_path = args.inventory or args.industry_dir / "document_inventory.csv.gz"
    chunk_plan_path = args.chunk_plan or args.industry_dir / "document_chunk_plan.csv"
    text_index_path = args.text_index_output or args.industry_dir / "document_text_index.csv.gz"
    run_summary_path = args.run_summary_output or args.industry_dir / "document_text_run_summary.csv"
    cache_dir = args.cache_dir or args.industry_dir / "document_text_cache"
    manifest_path = args.manifest or args.industry_dir / "industry_document_text_manifest.json"

    inventory = load_dataframe(inventory_path)
    chunk_plan = load_dataframe(chunk_plan_path)
    existing = load_dataframe(text_index_path)
    chunk_id = _select_chunk_id(inventory, chunk_plan, existing, args.chunk_id)
    if not chunk_id:
        raise SystemExit("Nenhum chunk documental encontrado. Rode scripts/build_fidc_industry_documents.py primeiro.")
    if inventory.empty or "chunk_id" not in inventory.columns:
        raise SystemExit(f"Inventário documental sem coluna chunk_id: {inventory_path}")
    if not inventory["chunk_id"].fillna("").astype(str).eq(chunk_id).any():
        raise SystemExit(f"Chunk {chunk_id!r} não encontrado no inventário.")

    current = build_document_chunk_text_index(
        inventory,
        chunk_id=chunk_id,
        root=ROOT,
        cache_dir=cache_dir if cache_dir.is_absolute() else ROOT / cache_dir,
        existing=existing,
        max_pdf_pages=args.max_pdf_pages,
        ocr_engine=args.ocr_engine,
        ocr_languages=args.ocr_languages,
        force=args.force,
    )
    text_index = merge_document_text_index(existing, current)
    run_summary = build_document_text_run_summary(text_index, chunk_plan)
    save_dataframe(text_index, text_index_path)
    save_dataframe(run_summary, run_summary_path)
    manifest = build_document_text_manifest(
        industry_dir=args.industry_dir,
        text_index_path=text_index_path,
        run_summary_path=run_summary_path,
        cache_dir=cache_dir,
        manifest_path=manifest_path,
        text_index=text_index,
        run_summary=run_summary,
        chunk_plan=chunk_plan,
        chunk_id=chunk_id,
    )
    save_pipeline_manifest(manifest, manifest_path)

    quality = manifest.get("quality", {})
    print(f"[ok] texto materializado: {chunk_id} ({len(current):,} documentos nesta execução)")
    print(
        f"[ok] índice acumulado em {text_index_path} "
        f"({quality.get('rows', 0):,} documentos; "
        f"{quality.get('processed_chunks', 0)}/{quality.get('total_chunks', 0)} chunks)"
    )
    print(
        f"[ok] prontos: {quality.get('ready_docs', 0):,}; "
        f"OCR: {quality.get('ocr_required_docs', 0):,}; "
        f"erros: {quality.get('error_docs', 0):,}; "
        f"páginas processadas: {quality.get('pages_processed', 0):,}"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
