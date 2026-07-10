"""Extrai candidatos estruturados de um chunk documental da aba Indústria.

Uso:
    python scripts/build_fidc_industry_document_fields.py --chunk-id doc-0001

Sem ``--chunk-id``, seleciona o primeiro chunk ainda ausente do resumo. A saída
é uma fila automática; decisões finais continuam na curadoria da aplicação.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_study import (  # noqa: E402
    DOCUMENT_CRITERIA_CANDIDATE_COLUMNS,
    DOCUMENT_PARTICIPANT_CANDIDATE_COLUMNS,
    build_document_field_candidates,
    build_document_field_chunk_summary,
    build_document_field_manifest,
    load_dataframe,
    merge_document_field_candidates,
    merge_document_field_run_summary,
    save_dataframe,
    save_pipeline_manifest,
)


DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract participant and criteria candidates from one text chunk.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--text-index", type=Path, default=None)
    parser.add_argument("--chunk-plan", type=Path, default=None)
    parser.add_argument("--participants-output", type=Path, default=None)
    parser.add_argument("--criteria-output", type=Path, default=None)
    parser.add_argument("--run-summary-output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--chunk-id", type=str, default="")
    return parser.parse_args()


def _select_chunk_id(text_index, chunk_plan, run_summary, requested: str) -> str:
    requested = str(requested or "").strip()
    if requested:
        return requested
    source = chunk_plan if chunk_plan is not None and not chunk_plan.empty else text_index
    if source is None or source.empty or "chunk_id" not in source.columns:
        return ""
    chunks = [value for value in source["chunk_id"].fillna("").astype(str).tolist() if value]
    chunks = list(dict.fromkeys(chunks))
    processed: set[str] = set()
    if run_summary is not None and not run_summary.empty and "chunk_id" in run_summary.columns:
        processed = set(run_summary["chunk_id"].fillna("").astype(str))
    for chunk_id in chunks:
        if chunk_id not in processed:
            return chunk_id
    return chunks[0] if chunks else ""


def main() -> None:
    args = parse_args()
    text_index_path = args.text_index or args.industry_dir / "document_text_index.csv.gz"
    chunk_plan_path = args.chunk_plan or args.industry_dir / "document_chunk_plan.csv"
    participant_path = args.participants_output or args.industry_dir / "document_participant_candidates.csv.gz"
    criteria_path = args.criteria_output or args.industry_dir / "document_criteria_candidates.csv.gz"
    run_summary_path = args.run_summary_output or args.industry_dir / "document_field_run_summary.csv"
    manifest_path = args.manifest or args.industry_dir / "industry_document_field_manifest.json"

    text_index = load_dataframe(text_index_path)
    chunk_plan = load_dataframe(chunk_plan_path)
    participant_existing = load_dataframe(participant_path)
    criteria_existing = load_dataframe(criteria_path)
    summary_existing = load_dataframe(run_summary_path)
    chunk_id = _select_chunk_id(text_index, chunk_plan, summary_existing, args.chunk_id)
    if not chunk_id:
        raise SystemExit("Nenhum chunk textual encontrado. Rode scripts/build_fidc_industry_document_text.py primeiro.")
    if text_index.empty or "chunk_id" not in text_index.columns:
        raise SystemExit(f"Índice textual sem coluna chunk_id: {text_index_path}")
    if not text_index["chunk_id"].fillna("").astype(str).eq(chunk_id).any():
        raise SystemExit(f"Chunk {chunk_id!r} não encontrado no índice textual.")

    participants_current, criteria_current = build_document_field_candidates(
        text_index,
        chunk_id=chunk_id,
        root=ROOT,
    )
    participants = merge_document_field_candidates(
        participant_existing,
        participants_current,
        columns=DOCUMENT_PARTICIPANT_CANDIDATE_COLUMNS,
        chunk_id=chunk_id,
    )
    criteria = merge_document_field_candidates(
        criteria_existing,
        criteria_current,
        columns=DOCUMENT_CRITERIA_CANDIDATE_COLUMNS,
        chunk_id=chunk_id,
    )
    summary_current = build_document_field_chunk_summary(
        chunk_id=chunk_id,
        text_index=text_index,
        participant_candidates=participants_current,
        criteria_candidates=criteria_current,
    )
    run_summary = merge_document_field_run_summary(summary_existing, summary_current)
    save_dataframe(participants, participant_path)
    save_dataframe(criteria, criteria_path)
    save_dataframe(run_summary, run_summary_path)
    manifest = build_document_field_manifest(
        industry_dir=args.industry_dir,
        participant_path=participant_path,
        criteria_path=criteria_path,
        run_summary_path=run_summary_path,
        manifest_path=manifest_path,
        participant_candidates=participants,
        criteria_candidates=criteria,
        run_summary=run_summary,
        chunk_plan=chunk_plan,
        chunk_id=chunk_id,
    )
    save_pipeline_manifest(manifest, manifest_path)

    quality = manifest.get("quality", {})
    print(
        f"[ok] campos extraídos: {chunk_id} "
        f"({len(participants_current):,} participantes; {len(criteria_current):,} critérios nesta execução)"
    )
    print(
        f"[ok] acumulado: {quality.get('processed_chunks', 0)}/{quality.get('total_chunks', 0)} chunks; "
        f"{quality.get('participant_candidates', 0):,} participantes em {quality.get('participant_funds', 0):,} FIDCs; "
        f"{quality.get('criteria_candidates', 0):,} critérios em {quality.get('criteria_funds', 0):,} FIDCs"
    )
    print(
        f"[ok] triagem contextual: {quality.get('participant_accepted', 0):,} aceitos; "
        f"{quality.get('participant_suppressed', 0):,} suprimidos e preservados para auditoria"
    )
    print(
        f"[ok] página: participantes {quality.get('participant_with_page', 0):,}; "
        f"critérios {quality.get('criteria_with_page', 0):,}; "
        f"subordinação {quality.get('subordination_candidates', 0):,} candidatos"
    )
    print(f"[ok] manifesto gravado em {manifest_path}")


if __name__ == "__main__":
    main()
