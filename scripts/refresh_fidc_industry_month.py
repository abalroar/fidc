"""Refresh one CVM FIDC monthly competence without losing the last complete snapshot.

The CVM publishes the latest competence incrementally. This command always
replaces the granular rows for the requested month, but only promotes
``universe_latest.csv`` when both vehicle count and PL are at least 85% of the
previous competence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_fidc_industry_study import build_concentration, run_pipeline  # noqa: E402
from services.industry_intelligence import build_competence_status, latest_complete_competence  # noqa: E402


MONTHLY_OUTPUTS = (
    "industry_monthly.csv",
    "segments_monthly.csv",
    "flows_monthly.csv",
    "cotistas_tipo_monthly.csv",
    "admin_monthly.csv",
    "vehicle_monthly.csv.gz",
    "update_audit_monthly.csv",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="Competência no formato AAAA-MM")
    parser.add_argument("--industry-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument("--raw-dir", type=Path, default=Path(".cache/cvm-industry-study"))
    parser.add_argument("--source-zip", type=Path)
    parser.add_argument("--skip-download", action="store_true")
    return parser.parse_args()


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def replace_month(existing: pd.DataFrame, replacement: pd.DataFrame, month: str) -> pd.DataFrame:
    if "competencia" not in existing or "competencia" not in replacement:
        raise ValueError("Saída mensal sem coluna competencia")
    kept = existing[existing["competencia"].astype(str).ne(month)]
    output = pd.concat([kept, replacement], ignore_index=True)
    sort_columns = [column for column in ["competencia", "cnpj", "cnpj_fundo", "segmento", "nivel"] if column in output]
    return output.sort_values(sort_columns).reset_index(drop=True)


def save(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, compression="gzip" if path.suffix == ".gz" else None)


def main() -> None:
    args = parse_args()
    month = args.month
    if len(month) != 7 or month[4] != "-":
        raise SystemExit("--month deve usar AAAA-MM")
    yyyymm = month.replace("-", "")
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    if args.source_zip:
        destination = args.raw_dir / f"inf_mensal_fidc_{yyyymm}.zip"
        if args.source_zip.resolve() != destination.resolve():
            shutil.copy2(args.source_zip, destination)

    with tempfile.TemporaryDirectory(prefix=f"fidc-{yyyymm}-") as temp:
        temp_output = Path(temp) / "output"
        pipeline_args = argparse.Namespace(
            raw_dir=str(args.raw_dir),
            output_dir=str(temp_output),
            start=month,
            end=month,
            skip_download=args.skip_download,
            snapshot_month=month,
            report=False,
            report_path="",
        )
        run_pipeline(pipeline_args)

        args.industry_dir.mkdir(parents=True, exist_ok=True)
        for filename in MONTHLY_OUTPUTS:
            current_path = args.industry_dir / filename
            replacement_path = temp_output / filename
            if not replacement_path.exists():
                continue
            replacement = _read(replacement_path)
            merged = replace_month(_read(current_path), replacement, month) if current_path.exists() else replacement
            save(merged, current_path)

        admin = _read(args.industry_dir / "admin_monthly.csv")
        save(build_concentration(admin), args.industry_dir / "concentration_monthly.csv")

        industry = _read(args.industry_dir / "industry_monthly.csv")
        audit = _read(args.industry_dir / "update_audit_monthly.csv")
        status = build_competence_status(industry, audit)
        save(status, args.industry_dir / "industry_competence_status.csv")
        complete_month = latest_complete_competence(status)

        month_status = status[status["competencia"].astype(str).eq(month)].iloc[0]
        promoted = month_status["publication_status"] == "completa"
        if promoted:
            shutil.copy2(temp_output / "universe_latest.csv", args.industry_dir / "universe_latest.csv")
            shutil.copy2(temp_output / "prestadores_latest.csv", args.industry_dir / "prestadores_latest.csv")

        metadata_path = args.industry_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        metadata["competencia_final"] = str(industry.sort_values("competencia").iloc[-1]["competencia"]).replace("-", "")
        metadata["competencia_snapshot"] = complete_month.replace("-", "")
        metadata["ultima_atualizacao_status"] = {
            "competencia": month,
            "status": month_status["publication_status"],
            "veiculos_vs_mes_anterior": float(month_status["vehicle_ratio_vs_previous"]),
            "pl_vs_mes_anterior": float(month_status["pl_ratio_vs_previous"]),
            "snapshot_promovido": bool(promoted),
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"[ok] {month}: {month_status['publication_status']}; "
        f"snapshot consolidado preservado em {complete_month}"
    )


if __name__ == "__main__":
    main()
