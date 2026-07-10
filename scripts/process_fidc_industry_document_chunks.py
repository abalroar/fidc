"""Processa chunks documentais pendentes sem refazer etapas concluídas.

Uso:
    python scripts/process_fidc_industry_document_chunks.py
    python scripts/process_fidc_industry_document_chunks.py --max-chunks 10
    python scripts/process_fidc_industry_document_chunks.py --chunk-id doc-0028
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDUSTRY_DIR = Path("data/industry_study")


def _boolish(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "sim", "yes", "y"}


def select_document_chunks(
    plan: pd.DataFrame,
    *,
    chunk_ids: list[str] | None = None,
    max_chunks: int = 1,
    priority_only: bool = False,
    include_complete: bool = False,
    complete_only: bool = False,
) -> pd.DataFrame:
    if plan is None or plan.empty or "chunk_id" not in plan.columns:
        return pd.DataFrame()
    frame = plan.copy()
    frame["chunk_id"] = frame["chunk_id"].fillna("").astype(str)
    frame = frame[frame["chunk_id"].str.strip().ne("")].drop_duplicates("chunk_id", keep="last")
    requested = [str(value).strip() for value in (chunk_ids or []) if str(value).strip()]
    if requested:
        order = {value: idx for idx, value in enumerate(requested)}
        frame = frame[frame["chunk_id"].isin(order)].copy()
        frame["_requested_order"] = frame["chunk_id"].map(order)
        frame = frame.sort_values("_requested_order").drop(columns=["_requested_order"])
    else:
        technical = frame.get("technical_complete", pd.Series(False, index=frame.index)).map(_boolish)
        status = frame.get("chunk_status", pd.Series("", index=frame.index)).fillna("").astype(str)
        if complete_only:
            frame = frame[technical & status.eq("pronto")].copy()
        elif not include_complete:
            frame = frame[~technical | status.ne("pronto")].copy()
        if priority_only:
            priority = pd.to_numeric(
                frame.get("priority_docs_effective", frame.get("priority_2025_2026_docs")),
                errors="coerce",
            ).fillna(0)
            frame = frame[priority.gt(0)].copy()
        frame["_priority"] = pd.to_numeric(frame.get("priority_score"), errors="coerce").fillna(0)
        frame["_chunk_order"] = pd.to_numeric(frame["chunk_id"].str.extract(r"(\d+)$")[0], errors="coerce").fillna(10**9)
        frame = frame.sort_values(["_priority", "_chunk_order"], ascending=[False, True]).drop(
            columns=["_priority", "_chunk_order"]
        )
    if max_chunks > 0:
        frame = frame.head(max_chunks)
    return frame.reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process pending FIDC industry document chunks incrementally.")
    parser.add_argument("--industry-dir", type=Path, default=DEFAULT_INDUSTRY_DIR)
    parser.add_argument("--chunk-id", action="append", default=[])
    parser.add_argument("--max-chunks", type=int, default=1, help="0 processa todos os chunks selecionados.")
    parser.add_argument("--priority-only", action="store_true")
    parser.add_argument(
        "--complete-only",
        action="store_true",
        help="Seleciona somente chunks tecnicamente concluídos; útil com --force-stage.",
    )
    parser.add_argument(
        "--force-stage",
        action="append",
        choices=["diagnostics", "text", "fields"],
        default=[],
        help="Reexecuta a etapa mesmo se o plano a marcar como concluída; pode ser repetido.",
    )
    parser.add_argument("--stop-on-error", action="store_true")
    return parser.parse_args()


def _run(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return int(completed.returncode)


def main() -> None:
    args = parse_args()
    plan_path = args.industry_dir / "document_chunk_plan.csv"
    if not plan_path.exists():
        raise SystemExit(f"Plano não encontrado: {plan_path}")
    plan = pd.read_csv(plan_path, dtype=str, keep_default_na=False)
    selected = select_document_chunks(
        plan,
        chunk_ids=args.chunk_id,
        max_chunks=max(int(args.max_chunks), 0),
        priority_only=args.priority_only,
        include_complete=bool(args.force_stage),
        complete_only=args.complete_only,
    )
    if selected.empty:
        raise SystemExit("Nenhum chunk pendente corresponde aos filtros.")

    failures: list[str] = []
    for position, row in selected.iterrows():
        chunk_id = str(row["chunk_id"])
        print(f"[{position + 1}/{len(selected)}] {chunk_id}")
        stages = [
            (
                "diagnóstico",
                "diagnostics",
                "diagnostic_complete",
                [sys.executable, "scripts/build_fidc_industry_document_chunk_diagnostics.py", "--chunk-id", chunk_id],
            ),
            (
                "texto/OCR",
                "text",
                "text_complete",
                [sys.executable, "scripts/build_fidc_industry_document_text.py", "--chunk-id", chunk_id],
            ),
            (
                "campos",
                "fields",
                "fields_complete",
                [sys.executable, "scripts/build_fidc_industry_document_fields.py", "--chunk-id", chunk_id],
            ),
        ]
        chunk_failed = False
        forced_stages = set(args.force_stage)
        for label, stage_id, completion_column, command in stages:
            if _boolish(row.get(completion_column, False)) and stage_id not in forced_stages:
                print(f"  [cache] {label}")
                continue
            print(f"  [run] {label}")
            return_code = _run(command)
            if return_code == 0:
                continue
            failures.append(f"{chunk_id}:{label}:exit={return_code}")
            chunk_failed = True
            print(f"  [erro] {label} retornou {return_code}")
            break
        if chunk_failed and args.stop_on_error:
            break

    _run([sys.executable, "scripts/build_fidc_industry_document_chunk_plan.py"])
    if failures:
        raise SystemExit("Falhas: " + " | ".join(failures))
    print(f"[ok] {len(selected)} chunks processados; plano operacional atualizado.")


if __name__ == "__main__":
    main()
