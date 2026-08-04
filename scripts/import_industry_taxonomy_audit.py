"""Normalize and apply the audited June/2026 FIDC Type/Focus de-para."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.industry_taxonomy_audit_import import (
    import_taxonomy_audit,
    materialize_taxonomy_audit,
    prepare_audited_actions,
)
from services.industry_taxonomy_review import (
    assert_taxonomy_review_ledger_matches_audit,
    commit_taxonomy_review_actions,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook")
    parser.add_argument("--data-dir", default="data/industry_study")
    parser.add_argument(
        "--saved-at-utc",
        default="2026-08-04T12:00:00+00:00",
        help="timestamp determinístico da transação do ledger",
    )
    parser.add_argument("--normalize-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    imported = import_taxonomy_audit(Path(args.workbook))
    paths = materialize_taxonomy_audit(imported, data_dir)
    print(
        "[ok] auditoria normalizada: "
        f"{len(imported.decisions)} decisões; manifest={paths['manifest']}"
    )
    if args.normalize_only:
        return
    ledger_path = data_dir / "taxonomy_review_actions.csv"
    audit_path = data_dir / "taxonomy_review_audit.csv"
    actions = prepare_audited_actions(
        imported,
        ledger_path,
        updated_at_utc=args.saved_at_utc,
    )
    _updated, events = commit_taxonomy_review_actions(
        actions,
        ledger_path,
        audit_path,
        saved_at_utc=args.saved_at_utc,
        source="industry_taxonomy_audit_202606",
    )
    assert_taxonomy_review_ledger_matches_audit(ledger_path, audit_path)
    print(
        f"[ok] ledger atualizado em uma transação: {len(actions)} CNPJs, "
        f"{len(events)} eventos de campo"
    )


if __name__ == "__main__":
    main()
