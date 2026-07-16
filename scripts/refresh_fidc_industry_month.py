"""Refresh one CVM FIDC monthly competence without losing the last complete snapshot.

The CVM publishes the latest competence incrementally. This command always
replaces the granular rows for the requested month, but only promotes the
latest complete and validated ``universe_latest.csv`` snapshot.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
from uuid import uuid4

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

SNAPSHOT_OUTPUTS = (
    "universe_latest.csv",
    "prestadores_latest.csv",
)

UNIVERSE_PROVIDER_NAME_COLUMNS = {
    "administrador": "admin_nome",
    "gestor": "gestor_nome",
    "custodiante": "custodiante_nome",
}

UNIVERSE_REQUIRED_COLUMNS = {
    "competencia",
    "cnpj",
    "pl",
    *UNIVERSE_PROVIDER_NAME_COLUMNS.values(),
}

PRESTADORES_REQUIRED_COLUMNS = {
    "papel",
    "nome",
    "cnpj_prestador",
    "pl",
    "n_veiculos",
    "n_fundos",
    "share_pl",
    "fonte",
}

EXPECTED_PROVIDER_ROLES = {
    "administrador",
    "gestor",
    "custodiante",
}

PROVIDER_PL_RECONCILIATION_REL_TOL = 1e-12
PROVIDER_PL_RECONCILIATION_ABS_TOL_BRL = 1.0
PROVIDER_SHARE_REL_TOL = 1e-6
PROVIDER_SHARE_ABS_TOL = 1e-6


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


def normalize_snapshot_month(month: str) -> str:
    """Convert an ISO competence into the compact format expected by RawStore."""
    value = str(month).strip()
    if len(value) == 7 and value[4] == "-":
        value = value.replace("-", "")
    if len(value) != 6 or not value.isdigit() or not 1 <= int(value[4:]) <= 12:
        raise ValueError("competência deve usar AAAA-MM ou AAAAMM")
    return value


def _validate_snapshot_outputs(output_dir: Path, month: str) -> tuple[bool, str]:
    """Validate a candidate snapshot before it can replace the published files."""
    compact_month = normalize_snapshot_month(month)
    expected_competence = f"{compact_month[:4]}-{compact_month[4:]}"
    universe_path = output_dir / "universe_latest.csv"
    providers_path = output_dir / "prestadores_latest.csv"

    for path in (universe_path, providers_path):
        if not path.exists() or path.stat().st_size <= 1:
            return False, f"{path.name} ausente ou vazio"

    try:
        universe = _read(universe_path)
        providers = _read(providers_path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeError) as exc:
        return False, f"snapshot ilegível: {exc}"

    if universe.empty:
        return False, "universe_latest.csv sem linhas"
    missing = UNIVERSE_REQUIRED_COLUMNS.difference(universe.columns)
    if missing:
        return False, f"universe_latest.csv sem colunas obrigatórias: {sorted(missing)}"
    competences = set(universe["competencia"].dropna().astype(str).str.strip())
    if competences != {expected_competence}:
        return False, (
            "universe_latest.csv com competência divergente: "
            f"esperado {expected_competence}, encontrado {sorted(competences)}"
        )
    universe_pl = pd.to_numeric(universe["pl"], errors="coerce")
    if universe_pl.isna().any() or not universe_pl.map(math.isfinite).all() or universe_pl.sum() <= 0:
        return False, "universe_latest.csv com PL inválido"

    if providers.empty:
        return False, "prestadores_latest.csv sem linhas"
    missing = PRESTADORES_REQUIRED_COLUMNS.difference(providers.columns)
    if missing:
        return False, f"prestadores_latest.csv sem colunas obrigatórias: {sorted(missing)}"
    roles = set(providers["papel"].dropna().astype(str).str.strip())
    if not EXPECTED_PROVIDER_ROLES.issubset(roles):
        return False, f"prestadores_latest.csv sem papéis obrigatórios: {sorted(EXPECTED_PROVIDER_ROLES - roles)}"
    provider_pl = pd.to_numeric(providers["pl"], errors="coerce")
    shares = pd.to_numeric(providers["share_pl"], errors="coerce")
    if (
        provider_pl.isna().any()
        or not provider_pl.map(math.isfinite).all()
        or shares.isna().any()
        or not shares.map(math.isfinite).all()
        or shares.abs().gt(1).any()
    ):
        return False, "prestadores_latest.csv com PL/share inválido"

    for role in EXPECTED_PROVIDER_ROLES:
        role_mask = providers["papel"].astype(str).eq(role)
        role_total = float(provider_pl[role_mask].sum())
        role_share = float(shares[role_mask].sum())
        role_name_column = UNIVERSE_PROVIDER_NAME_COLUMNS[role]
        known_role = (
            universe[role_name_column]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
        )
        known_role_total = float(universe_pl[known_role].sum())
        if not math.isclose(
            role_total,
            known_role_total,
            rel_tol=PROVIDER_PL_RECONCILIATION_REL_TOL,
            abs_tol=PROVIDER_PL_RECONCILIATION_ABS_TOL_BRL,
        ):
            return False, (
                f"prestadores_latest.csv com PL não reconciliado para {role}: "
                f"prestadores={role_total:.2f}, universo_conhecido={known_role_total:.2f}"
            )
        if not math.isclose(
            role_share,
            1.0,
            rel_tol=PROVIDER_SHARE_REL_TOL,
            abs_tol=PROVIDER_SHARE_ABS_TOL,
        ):
            return False, f"prestadores_latest.csv com share inválido para {role}"

    return True, "ok"


def _promote_snapshot_outputs(source_dir: Path, destination_dir: Path) -> None:
    """Stage both validated files before replacing their published versions."""
    staged: list[tuple[Path, Path]] = []
    try:
        for filename in SNAPSHOT_OUTPUTS:
            destination = destination_dir / filename
            staging = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
            shutil.copy2(source_dir / filename, staging)
            staged.append((staging, destination))
        for staging, destination in staged:
            staging.replace(destination)
    finally:
        for staging, _ in staged:
            staging.unlink(missing_ok=True)


def _published_snapshot_competence(industry_dir: Path, metadata: dict[str, object]) -> str:
    """Return the competence represented by the snapshot that is already published."""
    universe_path = industry_dir / "universe_latest.csv"
    if universe_path.exists() and universe_path.stat().st_size > 1:
        try:
            universe = _read(universe_path)
            if "competencia" in universe and not universe.empty:
                values = universe["competencia"].dropna().astype(str).str.strip().unique()
                if len(values) == 1:
                    return normalize_snapshot_month(values[0])
        except (OSError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeError):
            pass
    current = str(metadata.get("competencia_snapshot", "")).strip()
    if current:
        try:
            return normalize_snapshot_month(current)
        except ValueError:
            pass
    return ""


def replace_month(existing: pd.DataFrame, replacement: pd.DataFrame, month: str) -> pd.DataFrame:
    if "competencia" not in existing or "competencia" not in replacement:
        raise ValueError("Saída mensal sem coluna competencia")
    kept = existing[existing["competencia"].astype(str).ne(month)]
    output = pd.concat([kept, replacement], ignore_index=True)
    sort_columns = [column for column in ["competencia", "cnpj", "cnpj_fundo", "segmento", "nivel"] if column in output]
    return output.sort_values(sort_columns).reset_index(drop=True)


def save(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, compression="gzip" if path.suffix == ".gz" else None)


def _load_validated_monthly_outputs(output_dir: Path, month: str) -> dict[str, pd.DataFrame]:
    """Read the complete candidate batch before any published file is touched."""

    candidates: dict[str, pd.DataFrame] = {}
    for filename in MONTHLY_OUTPUTS:
        path = output_dir / filename
        if not path.exists() or path.stat().st_size <= 1:
            raise ValueError(f"saída mensal ausente ou vazia: {filename}")
        try:
            frame = _read(path)
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeError) as exc:
            raise ValueError(f"saída mensal ilegível ({filename}): {exc}") from exc
        if frame.empty:
            raise ValueError(f"saída mensal sem linhas: {filename}")
        if frame.columns.duplicated().any():
            duplicated = frame.columns[frame.columns.duplicated()].tolist()
            raise ValueError(f"saída mensal com colunas duplicadas ({filename}): {duplicated}")
        if "competencia" not in frame.columns:
            raise ValueError(f"saída mensal sem coluna competencia: {filename}")
        competence = frame["competencia"]
        if competence.isna().any():
            raise ValueError(f"saída mensal com competencia nula: {filename}")
        values = set(competence.astype(str).str.strip())
        if values != {month}:
            raise ValueError(
                f"saída mensal com competencia divergente ({filename}): "
                f"esperado {month}, encontrado {sorted(values)}"
            )
        candidates[filename] = frame
    return candidates


def _prepare_monthly_merges(
    candidates: dict[str, pd.DataFrame],
    destination_dir: Path,
    month: str,
) -> dict[str, pd.DataFrame]:
    """Build every replacement frame in memory, allowing additive schema evolution."""

    prepared: dict[str, pd.DataFrame] = {}
    for filename in MONTHLY_OUTPUTS:
        replacement = candidates[filename]
        current_path = destination_dir / filename
        if not current_path.exists():
            prepared[filename] = replacement.copy()
            continue
        try:
            existing = _read(current_path)
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeError) as exc:
            raise ValueError(f"saída publicada ilegível ({filename}): {exc}") from exc
        missing_columns = set(existing.columns).difference(replacement.columns)
        if missing_columns:
            raise ValueError(
                f"schema mensal divergente ({filename}); colunas publicadas ausentes no candidato: "
                f"{sorted(missing_columns)}"
            )
        prepared[filename] = replace_month(existing, replacement, month)
    return prepared


def _publish_frames_atomically(
    frames: dict[str, pd.DataFrame],
    destination_dir: Path,
) -> None:
    """Stage a complete batch, then atomically replace each file with rollback."""

    destination_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    staged: dict[str, Path] = {}
    backups: dict[str, Path] = {}
    originally_present = {
        filename for filename in frames if (destination_dir / filename).exists()
    }
    try:
        for filename, frame in frames.items():
            destination = destination_dir / filename
            staging = destination.with_name(f".{token}.{destination.name}")
            save(frame, staging)
            staged[filename] = staging

        for filename in frames:
            destination = destination_dir / filename
            if destination.exists():
                backup = destination.with_name(f".{token}.{destination.name}.bak")
                shutil.copy2(destination, backup)
                backups[filename] = backup

        for filename in frames:
            staged[filename].replace(destination_dir / filename)
    except Exception:
        for filename in frames:
            destination = destination_dir / filename
            backup = backups.get(filename)
            if backup is not None and backup.exists():
                backup.replace(destination)
            elif filename not in originally_present:
                destination.unlink(missing_ok=True)
        raise
    finally:
        for path in (*staged.values(), *backups.values()):
            path.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    month = args.month
    if len(month) != 7 or month[4] != "-":
        raise SystemExit("--month deve usar AAAA-MM")
    try:
        yyyymm = normalize_snapshot_month(month)
    except ValueError as exc:
        raise SystemExit(f"--month inválido: {exc}") from exc
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
            snapshot_month=yyyymm,
            report=False,
            report_path="",
        )
        run_pipeline(pipeline_args)

        args.industry_dir.mkdir(parents=True, exist_ok=True)
        candidates = _load_validated_monthly_outputs(temp_output, month)
        merged_outputs = _prepare_monthly_merges(candidates, args.industry_dir, month)
        industry = merged_outputs["industry_monthly.csv"]
        audit = merged_outputs["update_audit_monthly.csv"]
        concentration = build_concentration(merged_outputs["admin_monthly.csv"])
        status = build_competence_status(industry, audit)
        complete_month = latest_complete_competence(status)
        month_rows = status[status["competencia"].astype(str).eq(month)]
        if len(month_rows) != 1:
            raise ValueError(
                f"status mensal inválido para {month}: esperado 1 registro, encontrado {len(month_rows)}"
            )
        month_status = month_rows.iloc[0]
        publish_frames = {
            **merged_outputs,
            "concentration_monthly.csv": concentration,
            "industry_competence_status.csv": status,
        }
        _publish_frames_atomically(publish_frames, args.industry_dir)

        metadata_path = args.industry_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        published_snapshot = _published_snapshot_competence(args.industry_dir, metadata)
        promoted = False
        if month_status["publication_status"] != "completa":
            eligible = False
            promotion_reason = "competência ainda não está completa"
        elif month != complete_month:
            eligible = False
            promotion_reason = "competência é histórica; fotografia mais recente preservada"
        else:
            eligible = True
            promotion_reason = "snapshot aguardando validação"
        if eligible:
            valid_snapshot, promotion_reason = _validate_snapshot_outputs(temp_output, month)
            if valid_snapshot:
                _promote_snapshot_outputs(temp_output, args.industry_dir)
                published_snapshot = yyyymm
                promoted = True
                promotion_reason = "snapshot validado e promovido"
            else:
                print(f"[warn] snapshot de {month} não promovido: {promotion_reason}", file=sys.stderr)

        metadata["competencia_final"] = str(industry.sort_values("competencia").iloc[-1]["competencia"]).replace("-", "")
        metadata["competencia_snapshot"] = published_snapshot
        metadata["gerado_em_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        metadata["ultima_atualizacao_status"] = {
            "competencia": month,
            "status": month_status["publication_status"],
            "veiculos_vs_mes_anterior": float(month_status["vehicle_ratio_vs_previous"]),
            "pl_vs_mes_anterior": float(month_status["pl_ratio_vs_previous"]),
            "snapshot_promovido": bool(promoted),
            "snapshot_promocao_motivo": promotion_reason,
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"[ok] {month}: {month_status['publication_status']}; "
        f"snapshot consolidado em {published_snapshot or 'não disponível'}"
    )


if __name__ == "__main__":
    main()
