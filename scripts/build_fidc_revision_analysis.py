"""Materialize the auditable analytical tables used by the revised FIDC deck."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from services.industry_revision_analysis import build_revision_outputs, write_revision_outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/industry_study")
    parser.add_argument(
        "--output-dir",
        default="data/industry_study/generated_revision",
    )
    parser.add_argument(
        "--latest-complete",
        default="",
        help="competência AAAA-MM; vazio usa a última marcada como completa",
    )
    parser.add_argument("--raw-dir", default=".cache/cvm-industry-study")
    parser.add_argument(
        "--refresh-source-presence",
        action="store_true",
        help="reprocessa competências críticas no bruto CVM para preservar vazio versus zero e aging",
    )
    parser.add_argument(
        "--presence-months",
        default="2024-06,2024-07,2026-05",
    )
    parser.add_argument("--skip-download", action="store_true")
    return parser.parse_args(argv)


def _read_optional(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path, low_memory=False) if path.exists() else None


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    vehicle_path = data_dir / "vehicle_monthly.csv.gz"
    if not vehicle_path.exists():
        raise SystemExit(f"base ausente: {vehicle_path}")
    vehicle = pd.read_csv(vehicle_path, low_memory=False)
    latest_complete = str(args.latest_complete or "").strip()
    if not latest_complete:
        status = _read_optional(data_dir / "industry_competence_status.csv")
        if status is not None and not status.empty and "publication_status" in status:
            complete = status[status["publication_status"].astype(str).eq("completa")]
            if not complete.empty:
                latest_complete = str(complete["competencia"].astype(str).max())
        if not latest_complete:
            latest_complete = str(vehicle["competencia"].astype(str).max())
    official = _read_optional(data_dir / "industry_anbima_classification.csv.gz")
    published = _read_optional(data_dir / "industry_large_fund_classification.csv")
    raw_audit = None
    if args.refresh_source_presence:
        from scripts.build_fidc_industry_study import RawStore, aggregate_month, load_tab4

        store = RawStore(Path(args.raw_dir), allow_download=not args.skip_download)
        raw_frames: list[pd.DataFrame] = []
        for competence in [item.strip() for item in args.presence_months.split(",") if item.strip()]:
            yyyymm = competence.replace("-", "")
            tab4 = load_tab4(store, yyyymm)
            aggregate = aggregate_month(store, yyyymm, tab4) if tab4 is not None else None
            if aggregate is None:
                print(f"[warn] bruto CVM indisponível para {competence}; overlay omitido")
                continue
            raw_frames.append(pd.DataFrame(aggregate.vehicle))
        raw_audit = pd.concat(raw_frames, ignore_index=True) if raw_frames else pd.DataFrame()
    outputs = build_revision_outputs(
        vehicle_monthly=vehicle,
        anbima_classification=official,
        published_classifications=published,
        raw_audit_vehicle=raw_audit,
        latest_complete=latest_complete,
    )
    manifest = write_revision_outputs(outputs, Path(args.output_dir))
    checks = manifest["checks"]
    print(
        "[ok] revisão analítica materializada em "
        f"{args.output_dir}: {checks['latest_vehicles']} veículos, "
        f"{checks['latest_funds']} fundos, {checks['top20_fidcs_rows']} no Top 20"
    )


if __name__ == "__main__":
    main()
