"""Run the global documentary refresh serially; scheduling is always external."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time
from typing import Any, Callable
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.documentary_corpus import atomic_json, load_registered_funds, normalize_cnpj, utc_now


STAGES = ("current", "history", "quarterly_current", "quarterly_history", "ime", "build", "report")
STAGES_WITH_OCR = (*STAGES[:5], "ocr", *STAGES[5:])


class RefreshLockedError(RuntimeError):
    pass


class ResourceFloorError(RuntimeError):
    pass


@dataclass
class RefreshConfig:
    root: Path
    resume: bool = True
    skip_network: bool = False
    network_timeout_seconds: int = 8
    attempts: int = 2
    max_download_gb: float = 6
    max_quarterly_download_gb: float = .25
    disk_floor_gb: float = 10
    only_stage: tuple[str, ...] = ()
    source_root: Path | None = None
    through: str = ""
    recover_unreadable_text: bool = False


@contextmanager
def exclusive_refresh_lock(base: Path):
    """The lock remains held by the parent while every child process runs."""
    base.mkdir(parents=True, exist_ok=True)
    with (base / ".global-refresh.lock").open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RefreshLockedError("Outra atualização global mantém o bloqueio; nenhum processo foi iniciado.") from exc
        try:
            handle.seek(0)
            handle.truncate()
            json.dump({"pid": os.getpid(), "started_at": utc_now()}, handle)
            handle.flush()
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def rss_bytes(who: int) -> int:
    peak = resource.getrusage(who).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)


def run_command(command: list[str], *, root: Path, env: dict[str, str], log_path: Path) -> dict[str, Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("a", encoding="utf-8") as output:
        process = subprocess.run(command, cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT, check=False)
    return {"returncode": process.returncode, "elapsed_seconds": round(time.monotonic() - started, 3),
            "peak_children_rss_bytes": rss_bytes(resource.RUSAGE_CHILDREN)}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def documented_additional_cnpjs(root: Path, registered: set[str]) -> list[str]:
    """Use reviewed relationships, never arbitrary CNPJ mentions from the search queue."""
    extra = set()
    for cnpj in sorted(registered):
        for directory in ("verified_overrides", "funds"):
            payload = _read_json(root / "data/documentary_diligence" / directory / f"{cnpj}.json")
            for relation in payload.get("lookthrough", []):
                target = normalize_cnpj(relation.get("cnpj", ""))
                if relation.get("relationship") not in {"named_investee", "permitted_mandate", "observed_investee"}:
                    continue
                if len(target) != 14 or target in registered:
                    continue
                sources = relation.get("sources", [])
                if any(source.get("document_id") and source.get("reference_date") and (source.get("page") or source.get("clause"))
                       and source.get("identity_verified") is not False for source in sources):
                    extra.add(target)
    return sorted(extra)


def stage_command(stage: str, config: RefreshConfig, *, remaining_bytes: int, additional: list[str]) -> list[str] | None:
    root = config.root
    selection = ["--all"] if not additional else [argument for cnpj in sorted(set(load_registered_funds(root / "portfolios.json")) | set(additional))
                                                 for argument in ("--only-cnpj", cnpj)]
    if stage in {"current", "history"}:
        if stage == "history" and (config.skip_network or remaining_bytes <= 0):
            return None
        command = [sys.executable, str(root / "scripts/refresh_documentary_corpus.py"), *selection, "--resume",
                   "--acquisition-pass", stage, "--root", str(root), "--max-download-gb", str(max(0, remaining_bytes) / 1024**3),
                   "--disk-floor-gb", str(config.disk_floor_gb), "--network-timeout-seconds", str(config.network_timeout_seconds),
                   "--attempts", str(config.attempts), "--local-only" if config.skip_network else "--network"]
        if config.source_root:
            command += ["--source-root", str(config.source_root)]
        return command
    if stage == "ime":
        script = root / "scripts/refresh_documentary_ime.py"
        if config.skip_network and "--offline-reprocess" not in script.read_text(encoding="utf-8"):
            return None
        command = [sys.executable, str(script), *selection, "--months", "3", "--through", config.through,
                   "--use-corpus-catalog", "--network-timeout-seconds", str(min(30, config.network_timeout_seconds))]
        if config.skip_network:
            command.append("--offline-reprocess")
        return command
    if stage in {"quarterly_current", "quarterly_history"}:
        if stage == "quarterly_history" and config.skip_network or remaining_bytes <= 0:
            return None
        command = [sys.executable, str(root / "scripts/refresh_documentary_quarterly.py"), *selection, "--resume",
                   "--root", str(root), "--acquisition-pass", stage.removeprefix("quarterly_"),
                   "--max-download-gb", str(max(0, remaining_bytes) / 1024**3), "--disk-floor-gb", str(config.disk_floor_gb),
                   "--network-timeout-seconds", str(config.network_timeout_seconds), "--attempts", str(config.attempts)]
        if config.skip_network:
            command.append("--offline-reprocess")
        return command
    if stage == "build":
        # Always rebuild after acquisition. --resume here would preserve stale criterion files.
        command = [sys.executable, str(root / "scripts/build_documentary_diligence.py"), "--all"]
        if config.source_root:
            command += ["--source-root", str(config.source_root)]
        return command
    if stage == "ocr":
        if not config.recover_unreadable_text:
            raise ValueError("OCR requires explicit --recover-unreadable-text")
        return [sys.executable, str(root / "scripts/recover_documentary_ocr.py"), "--root", str(root), "--all-unreadable",
                "--resume", "--max-pages", "300", "--dpi", "150", "--page-timeout-seconds", "25",
                "--disk-floor-gb", str(config.disk_floor_gb)]
    if stage == "report":
        return [sys.executable, str(root / "scripts/report_documentary_diligence.py"), "--root", str(root)]
    raise ValueError(f"Etapa desconhecida: {stage}")


def stage_downloaded_bytes(base: Path, stage: str, started_epoch: float) -> int:
    if stage.startswith("quarterly_"):
        path = base / "quarterly_index.json"
        if not path.exists() or path.stat().st_mtime < started_epoch:
            return 0
        payload = _read_json(path)
        return int(payload.get("downloaded_bytes_this_run") or 0) if payload.get("acquisition_pass") == stage.removeprefix("quarterly_") else 0
    counter = 0
    for path in (base / "corpus").glob("*.json"):
        if path.stat().st_mtime < started_epoch:
            continue
        payload = _read_json(path)
        if payload.get("mode") == "network" and payload.get("acquisition_pass") == stage:
            counter = max(counter, int(payload.get("downloaded_bytes_this_run") or 0))
    return counter


def reconcile_interrupted_downloads(base: Path, status: dict[str, Any]) -> None:
    """A stopped parent may not have copied the child's last byte checkpoint."""
    for stage in ("current", "history", "quarterly_current", "quarterly_history"):
        entry = status.get("stages", {}).get(stage, {})
        if entry.get("state") not in {"RUNNING", "ERROR", "RESOURCE_LIMIT"}:
            continue
        started = entry.get("started_epoch")
        if started is None and entry.get("started_at"):
            try:
                started = datetime.fromisoformat(entry["started_at"].replace("Z", "+00:00")).timestamp()
            except (TypeError, ValueError):
                continue
        if started is None:
            continue
        counter = "downloaded_quarterly_bytes" if stage.startswith("quarterly_") else "downloaded_pdf_bytes"
        observed = stage_downloaded_bytes(base, stage, float(started))
        accounted = int(entry.get(counter) or 0)
        additional = max(0, observed - accounted)
        status[counter] = int(status.get(counter) or 0) + additional
        entry[counter] = max(accounted, observed)
        if additional:
            entry["download_checkpoint_reconciled_at"] = utc_now()


def verify_generated_scope(root: Path, registered: set[str]) -> dict[str, Any]:
    missing, invalid = [], []
    for cnpj in sorted(registered):
        path = root / "data/documentary_diligence/funds" / f"{cnpj}.json"
        if not path.exists():
            missing.append(cnpj)
            continue
        try:
            payload = _read_json(path)
            if payload.get("schema_version") != 2 or normalize_cnpj(payload.get("cnpj", "")) != cnpj or not isinstance(payload.get("criteria"), list):
                invalid.append(cnpj)
        except (OSError, ValueError):
            invalid.append(cnpj)
    return {"registered_cnpjs": len(registered), "generated_valid": len(registered) - len(missing) - len(invalid),
            "missing": missing, "invalid": invalid}


def run_refresh(config: RefreshConfig, *, runner: Callable[..., dict[str, Any]] = run_command) -> dict[str, Any]:
    config.root = config.root.resolve()
    if not config.through:
        today = datetime.now(ZoneInfo("America/Sao_Paulo"))
        config.through = (today.replace(day=1) - timedelta(days=1)).strftime("%m/%Y")
    registered = set(load_registered_funds(config.root / "portfolios.json"))
    if not registered:
        raise ValueError("Nenhum CNPJ registrado em portfolios.json.")
    planned = STAGES_WITH_OCR if config.recover_unreadable_text else STAGES
    if "ocr" in config.only_stage and not config.recover_unreadable_text:
        raise ValueError("Use --recover-unreadable-text for the optional local OCR stage")
    requested = tuple(stage for stage in planned if not config.only_stage or stage in config.only_stage)
    if not requested:
        raise ValueError("Nenhuma etapa selecionada.")
    base = config.root / "data/documentary_diligence"
    status_path = base / "run_status.json"
    fingerprint_payload = {**asdict(config), "root": str(config.root), "source_root": str(config.source_root or ""), "registered": sorted(registered)}
    fingerprint = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True).encode()).hexdigest()
    with exclusive_refresh_lock(base):
        previous = _read_json(status_path)
        continuing = config.resume and previous.get("config_fingerprint") == fingerprint and previous.get("state") not in {"COMPLETE", "PARTIAL_COMPLETE", "COMPLETE_WITH_RESOURCE_LIMITS"}
        status = previous if continuing else {"schema_version": 1, "run_id": str(int(time.time())), "started_at": utc_now(),
                                             "config_fingerprint": fingerprint, "stages": {}, "downloaded_pdf_bytes": 0, "downloaded_quarterly_bytes": 0}
        status.update(state="RUNNING", owner_pid=os.getpid(), updated_at=utc_now(), requested_stages=list(requested),
                      scope="all_registered_and_documented_relationships" if requested == planned else "selected_stages_only",
                      registered_cnpjs=len(registered), skip_network=config.skip_network, through=config.through,
                      download_budget_scope="PDF documents in current and history passes", max_download_bytes=int(config.max_download_gb * 1024**3),
                      quarterly_budget_scope="HTTP bytes for quarterly declarations; XML and returned PDF formats", max_quarterly_download_bytes=int(config.max_quarterly_download_gb * 1024**3),
                      disk_floor_bytes=int(config.disk_floor_gb * 1024**3), error="")
        env = dict(os.environ)
        env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", NUMEXPR_MAX_THREADS="1")
        additional = documented_additional_cnpjs(config.root, registered)
        status["additional_documented_cnpjs"] = additional
        if continuing:
            reconcile_interrupted_downloads(base, status)
        atomic_json(status_path, status)
        try:
            for stage in requested:
                existing = status["stages"].get(stage, {})
                if continuing and existing.get("state") in {"COMPLETE", "SKIPPED_NETWORK", "SKIPPED_BUDGET"}:
                    continue
                if shutil.disk_usage(base).free < status["disk_floor_bytes"]:
                    raise ResourceFloorError(f"Espaço livre abaixo do piso de {config.disk_floor_gb:g} GB antes de {stage}.")
                quarterly = stage.startswith("quarterly_")
                budget_key = "max_quarterly_download_bytes" if quarterly else "max_download_bytes"
                counter_key = "downloaded_quarterly_bytes" if quarterly else "downloaded_pdf_bytes"
                remaining = max(0, status[budget_key] - status[counter_key])
                if quarterly and status.get('quarterly_budget_exhausted'):
                    remaining = 0
                command = stage_command(stage, config, remaining_bytes=remaining, additional=additional)
                if command is None:
                    state = "SKIPPED_NETWORK" if config.skip_network else "SKIPPED_BUDGET"
                    status["stages"][stage] = {"state": state, "ended_at": utc_now(), "reason": "Network disabled" if state == "SKIPPED_NETWORK" else "Stage download budget reached"}
                    atomic_json(status_path, status)
                    continue
                started_epoch = time.time()
                entry = {"state": "RUNNING", "started_at": utc_now(), "started_epoch": started_epoch, "command": command,
                         "log_path": str(base / "logs" / f"{status['run_id']}_{stage}.log")}
                status["stages"][stage] = entry
                atomic_json(status_path, status)
                outcome = runner(command, root=config.root, env=env, log_path=Path(entry["log_path"]))
                transferred = stage_downloaded_bytes(base, stage, started_epoch) if stage in {"current", "history", "quarterly_current", "quarterly_history"} else 0
                status[counter_key] += transferred
                quarterly_budget_limit = quarterly and outcome['returncode'] == 2 and _read_json(base / 'quarterly_index.json').get('stopped_reason') == 'download_budget_reached'
                ocr_budget_limit = stage == 'ocr' and outcome['returncode'] == 2 and str(_read_json(base / 'qa/ocr_recovery.json').get('stopped_reason') or '').startswith('page_budget_reached')
                recoverable_limit = quarterly_budget_limit or ocr_budget_limit
                if quarterly_budget_limit:
                    status['quarterly_budget_exhausted'] = True
                entry.update(outcome, **({"downloaded_quarterly_bytes": transferred} if quarterly else {"downloaded_pdf_bytes": transferred}),
                             ended_at=utc_now(), state="RESOURCE_LIMIT" if recoverable_limit else "COMPLETE" if outcome["returncode"] == 0 else "ERROR")
                status["peak_parent_rss_bytes"] = rss_bytes(resource.RUSAGE_SELF)
                status["peak_children_rss_bytes"] = max(int(status.get("peak_children_rss_bytes") or 0), int(outcome.get("peak_children_rss_bytes") or 0))
                entry["disk_free_bytes_after"] = shutil.disk_usage(base).free
                status["updated_at"] = utc_now()
                atomic_json(status_path, status)
                if outcome["returncode"] != 0 and not recoverable_limit:
                    raise RuntimeError(f"Etapa {stage} terminou com código {outcome['returncode']}; consultar {entry['log_path']}.")
                if entry["disk_free_bytes_after"] < status["disk_floor_bytes"]:
                    raise ResourceFloorError(f"Espaço livre abaixo do piso após {stage}; etapas restantes não foram iniciadas.")
            scope = verify_generated_scope(config.root, registered)
            status["verification"] = scope
            if "build" in requested and (scope["missing"] or scope["invalid"]):
                raise RuntimeError(f"Escopo gerado incompleto: {scope['generated_valid']}/{len(registered)} CNPJs válidos.")
            status["state"] = "PARTIAL_COMPLETE" if requested != planned or config.skip_network else "COMPLETE_WITH_RESOURCE_LIMITS" if any(
                item["state"] in {"SKIPPED_BUDGET", "RESOURCE_LIMIT"} for item in status["stages"].values()) else "COMPLETE"
            status["ended_at"] = utc_now()
            atomic_json(status_path, status)
            return status
        except (Exception, KeyboardInterrupt) as exc:
            status.update(state="RESOURCE_LIMIT" if isinstance(exc, ResourceFloorError) else "ERROR", error=f"{type(exc).__name__}: {exc}",
                          updated_at=utc_now(), ended_at=utc_now(), peak_parent_rss_bytes=rss_bytes(resource.RUSAGE_SELF),
                          peak_children_rss_bytes=rss_bytes(resource.RUSAGE_CHILDREN))
            for entry in status["stages"].values():
                if entry.get("state") == "RUNNING":
                    entry.update(state="ERROR", error=status["error"], ended_at=utc_now())
            atomic_json(status_path, status)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--skip-network", action="store_true")
    parser.add_argument("--network-timeout-seconds", "--network-timeout", type=int, default=8)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--max-download-gb", type=float, default=6)
    parser.add_argument("--max-quarterly-download-gb", type=float, default=.25)
    parser.add_argument("--disk-floor-gb", type=float, default=10)
    parser.add_argument("--recover-unreadable-text", action="store_true", help="Optional local Apple Vision OCR before rebuilding; never downloads or installs an OCR engine")
    parser.add_argument("--only-stage", choices=STAGES_WITH_OCR, action="append", default=[])
    parser.add_argument("--source-root", type=Path, default=Path(os.environ["DOCUMENTARY_SOURCE_ROOT"]) if os.environ.get("DOCUMENTARY_SOURCE_ROOT") else None)
    parser.add_argument("--through", default="", help="Competência máxima IME MM/AAAA; padrão mês anterior em America/Sao_Paulo")
    args = parser.parse_args()
    if args.network_timeout_seconds < 1 or not 1 <= args.attempts <= 3 or min(args.max_download_gb, args.max_quarterly_download_gb, args.disk_floor_gb) < 0:
        parser.error("Timeout positivo, tentativas entre 1 e 3 e limites de recursos não negativos são necessários.")
    if args.through:
        try:
            datetime.strptime(args.through, "%m/%Y")
        except ValueError:
            parser.error("Use --through MM/AAAA.")
    config = RefreshConfig(root=args.root, resume=args.resume, skip_network=args.skip_network,
                           network_timeout_seconds=args.network_timeout_seconds, attempts=args.attempts,
                           max_download_gb=args.max_download_gb, disk_floor_gb=args.disk_floor_gb,
                           max_quarterly_download_gb=args.max_quarterly_download_gb,
                           only_stage=tuple(args.only_stage), source_root=args.source_root, through=args.through,
                           recover_unreadable_text=args.recover_unreadable_text)
    try:
        status = run_refresh(config)
    except (RefreshLockedError, ResourceFloorError, OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Atualização interrompida: {exc}\n")
    print(f"{status['state']}: {status['registered_cnpjs']} CNPJs cadastrados; escopo {status['scope']}; PDF {status['downloaded_pdf_bytes']} bytes; quarterly {status['downloaded_quarterly_bytes']} bytes; peak children RSS {status.get('peak_children_rss_bytes', 0)} bytes", flush=True)
    print(f"Checkpoint: {config.root / 'data/documentary_diligence/run_status.json'}", flush=True)


if __name__ == "__main__":
    main()
