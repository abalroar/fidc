#!/usr/bin/env python3
"""Materialize the FIC audit with the provenance of each perimeter decision.

The audit separates the legacy nominal signal, quantitative confirmations from
the structured monthly report, and cases raised only by the stricter secondary
nominal cross-check.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import uuid

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.fic_detection import (  # noqa: E402
    METHOD_NAME,
    annotate_fic_detection,
    build_fic_audit,
    exclude_fics_from_fidc_universe,
    name_says_fic,
)
from services.fic_perimeter import load_fic_perimeter_overrides  # noqa: E402


AUDIT_FILENAME = "industry_fic_detection_audit.csv"
BASE_RELATIVE = Path("generated_revision") / "base_fundo_cnpj.csv.gz"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument(
        "--base-path",
        type=Path,
        help=(
            "Base por fundo-CNPJ; por padrão usa "
            "generated_revision/base_fundo_cnpj.csv.gz dentro de --data-dir."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Falha se a auditoria materializada divergir da recomposição.",
    )
    return parser.parse_args(argv)


def _annotated_fic_frame(
    data_dir: Path,
    *,
    base_path: Path | None = None,
) -> pd.DataFrame:
    data_dir = Path(data_dir)
    source = Path(base_path) if base_path is not None else data_dir / BASE_RELATIVE
    base = pd.read_csv(
        source,
        dtype=str,
        keep_default_na=False,
        usecols=["competencia", "cnpj_fundo", "denominacao", "is_fic_fidc", "pl"],
    )
    base["pl"] = pd.to_numeric(base["pl"], errors="coerce").fillna(0.0)

    overrides = load_fic_perimeter_overrides(data_dir)
    annotated = annotate_fic_detection(
        base,
        curated_cnpjs=overrides["cnpj_fundo"].tolist(),
        curated_evidence=dict(zip(overrides["cnpj_fundo"], overrides["evidencia"])),
    )
    return annotated


def build_fic_detection_audit_frame(
    data_dir: Path,
    *,
    base_path: Path | None = None,
) -> pd.DataFrame:
    """Recompose the audit without changing any materialized file."""

    return build_fic_audit(
        _annotated_fic_frame(Path(data_dir), base_path=base_path)
    )


def _audit_bytes(audit: pd.DataFrame) -> bytes:
    return audit.to_csv(index=False).encode("utf-8")


def _write_audit_atomically(audit: pd.DataFrame, audit_path: Path) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = audit_path.with_name(
        f".{audit_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary.write_bytes(_audit_bytes(audit))
        os.replace(temporary, audit_path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    annotated = _annotated_fic_frame(
        data_dir,
        base_path=args.base_path,
    )
    audit = build_fic_audit(annotated)
    audit_path = data_dir / AUDIT_FILENAME
    expected_bytes = _audit_bytes(audit)
    if args.check:
        if not audit_path.is_file() or audit_path.read_bytes() != expected_bytes:
            raise SystemExit(
                "auditoria FIC desatualizada; execute "
                f"{Path(__file__).name} --data-dir {data_dir}"
            )
        print(f"auditoria atual em {audit_path} ({len(audit)} linhas)")
    else:
        _write_audit_atomically(audit, audit_path)
        print(f"auditoria gravada em {audit_path} ({len(audit)} linhas)")

    _kept, report = exclude_fics_from_fidc_universe(annotated)

    by_cnpj = annotated.drop_duplicates("cnpj_fundo")
    excluded = by_cnpj[by_cnpj["is_fic"]]
    name_says = by_cnpj["denominacao"].map(lambda text: bool(name_says_fic(text)))
    nominal_review = by_cnpj[by_cnpj["fic_detection_method"].eq(METHOD_NAME)]
    silent_names = excluded[~excluded["cnpj_fundo"].isin(set(by_cnpj[name_says]["cnpj_fundo"]))]

    print(f"CNPJs excluídos como FIC: {excluded['cnpj_fundo'].nunique()}")
    print(
        "PL excluído na competência mais recente "
        f"({report.last_competence}): R$ {report.pl_excluded_last_competence_brl / 1e9:.2f} bi"
    )
    print(f"linhas-mês removidas: {report.rows_excluded} de {report.rows_in}")

    print("\nmétodo de detecção (por CNPJ):")
    print(excluded["fic_detection_method"].value_counts().to_string())

    print(
        "\ncandidatos levantados apenas pelo cross-check nominal secundário: "
        f"{len(nominal_review)}"
    )
    if len(nominal_review):
        top = nominal_review.nlargest(min(15, len(nominal_review)), "pl")
        for _, row in top.iterrows():
            print(f"  R$ {row['pl'] / 1e9:6.2f} bi  {row['denominacao'][:72]}")

    print(
        f"\nexcluídos sem correspondência no cross-check nominal secundário: "
        f"{len(silent_names)} "
        f"({len(silent_names) / max(len(excluded), 1) * 100:.0f}% dos excluídos) — "
        "proveniência quantitativa registrada separadamente"
    )

    print("\nPL excluído por competência de referência:")
    for competence in ("2023-12", "2024-12", "2025-12", "2026-06"):
        window = annotated[annotated["competencia"].eq(competence)]
        gone = window[window["is_fic"]]
        if window.empty:
            continue
        print(
            f"  {competence}: {len(gone):>3} fundos, R$ {gone['pl'].sum() / 1e9:7.2f} bi "
            f"de R$ {window['pl'].sum() / 1e9:7.2f} bi "
            f"({gone['pl'].sum() / max(window['pl'].sum(), 1) * 100:4.1f}%)"
        )


if __name__ == "__main__":
    main()
