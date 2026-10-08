"""Check official publications, then rebuild and publish a complete industry snapshot.

Checking is the default. --apply runs the producers and Office validation in a
private directory and promotes the dataset only after the entire bundle passes.
Source archives include every reporting fund/class; existing-month rectifications
are detected by SHA-256. An unchanged source set does not regenerate Office files.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_comparative_period import ComparisonCut
from services.industry_revision_export import get_revision_export_status
from services.industry_source_refresh import (
    discover_sources, file_sha256, refresh_archive, write_json_atomic,
)


def run(script: str, *arguments: str | Path) -> None:
    command = [sys.executable, "-u", str(ROOT / "scripts" / script), *map(str, arguments)]
    print("[step] " + script, flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def promote_dataset(staged: Path, destination: Path, backup: Path) -> None:
    """Keep the old dataset recoverable, including on a promotion failure."""
    if destination.is_symlink() or backup.exists():
        raise ValueError("Destino de publicação ou backup incompatível")
    os.replace(destination, backup)
    try:
        os.replace(staged, destination)
    except BaseException:
        os.replace(backup, destination)
        raise


@contextmanager
def staging_directory(cache_dir: Path):
    temporary = Path(tempfile.mkdtemp(prefix="industry-update-", dir=cache_dir))
    try:
        yield temporary
    except BaseException:
        print(f"[retained] Atualização incompleta preservada em {temporary}", flush=True)
        raise
    else:
        shutil.rmtree(temporary)


def rebuild(args: argparse.Namespace, source_records: dict) -> dict:
    data_dir = args.data_dir.resolve()
    cache_dir = args.state.parent
    original_fingerprints = {
        str(path.relative_to(data_dir)): file_sha256(path)
        for path in data_dir.rglob("*") if path.is_file()
    }
    template = args.input_workbook or data_dir / "generated_revision/industry_data_revised.xlsx"
    if not template.is_file():
        raise FileNotFoundError("Workbook canônico ausente; informe --input-workbook")
    template_sha = file_sha256(template)
    frozen_template = cache_dir / f"workbook-style-{template_sha}.xlsx"
    if not frozen_template.exists():
        shutil.copy2(template, frozen_template)
    if file_sha256(frozen_template) != template_sha:
        raise ValueError("Workbook de estilo congelado com hash divergente")
    months = sorted(Path(record["path"]).stem.rsplit("_", 1)[-1]
                    for record in source_records.values()
                    if Path(record["path"]).name.startswith("inf_mensal_fidc_")
                    and len(Path(record["path"]).stem.rsplit("_", 1)[-1]) == 6)
    if not months:
        raise ValueError("Nenhuma fonte mensal descoberta")
    latest_source = months[-1][:4] + "-" + months[-1][4:]
    offer_archive = args.offers_dir / "oferta_distribuicao.zip"
    provider_archive = args.cadastro_dir / "cad_fi_hist_current.zip"
    as_of = datetime.now(timezone.utc).date().isoformat()
    with staging_directory(cache_dir) as temporary:
        # A publication consumes one immutable raw snapshot even if another
        # downloader updates the regular cache while Office is rendering.
        source_identity = json.dumps({url: row["sha256"] for url, row in source_records.items()}, sort_keys=True).encode()
        frozen_sources = cache_dir / ("source-snapshot-" + hashlib.sha256(source_identity).hexdigest()[:20])
        frozen_sources.mkdir(exist_ok=True)
        for record in source_records.values():
            source = Path(record["path"])
            frozen = frozen_sources / source.name
            if not frozen.exists():
                candidate = frozen.with_suffix(frozen.suffix + ".partial")
                shutil.copy2(source, candidate)
                if file_sha256(candidate) != record["sha256"]:
                    candidate.unlink(missing_ok=True)
                    raise ValueError(f"Fonte mudou durante o congelamento: {source.name}")
                os.replace(candidate, frozen)
            if file_sha256(frozen) != record["sha256"]:
                raise ValueError(f"Fonte mudou durante o congelamento: {source.name}")
        raw_dir = frozen_sources
        offer_archive = frozen_sources / "oferta_distribuicao.zip"
        provider_archive = frozen_sources / "cad_fi_hist_current.zip"
        staged = Path(temporary) / "industry_study"
        shutil.copytree(data_dir, staged)
        run("build_fidc_industry_study.py", "--raw-dir", raw_dir,
            "--output-dir", staged, "--start", "2013-01", "--end", latest_source, "--skip-download")
        run("build_fidc_industry_intelligence.py", "--industry-dir", staged,
            "--offers-zip", offer_archive, "--as-of", as_of, "--skip-download")
        cut = ComparisonCut.from_data_dir(staged)
        revision_dir = staged / "generated_revision"
        run("build_fidc_revision_analysis.py", "--data-dir", staged,
            "--output-dir", revision_dir, "--latest-complete", cut.competence,
            "--raw-dir", raw_dir, "--refresh-source-presence", "--presence-months", "all", "--skip-download")
        run("build_fic_detection_audit.py", "--data-dir", staged)
        # Current sources are resolved by the publication API; dates from an
        # older ANBIMA publication remain explicit and are never relabelled.
        ranking_source = next(record for record in source_records.values() if record.get("key") == "anbima:ranking" or "Ranking_de_Renda_Fixa" in Path(record["path"]).name)
        annex_source = next(record for record in source_records.values() if record.get("key") == "anbima:annex" or "Anexo_ao_Ranking" in Path(record["path"]).name)
        market_source = next(record for record in source_records.values() if "Boletim_MK_Anexo" in Path(record["path"]).name)
        run("build_anbima_fixed_income_ranking.py", "--data-dir", staged,
            "--output-dir", staged, "--latest-complete", cut.competence,
            "--ranking-xlsx", frozen_sources / Path(ranking_source["path"]).name,
            "--annex-xlsx", frozen_sources / Path(annex_source["path"]).name,
            "--cvm-archive", offer_archive, "--source-as-of-date", as_of,
            "--ranking-source-url", ranking_source["url"], "--annex-source-url", annex_source["url"])
        run("build_anbima_market_offers.py", "--data-dir", staged,
            "--latest-complete", cut.competence,
            "--workbook", frozen_sources / Path(market_source["path"]).name,
            "--source-url", market_source["url"], "--source-as-of-date", as_of)
        for script in (
            "build_fidc_closed_offers.py", "build_fidc_offer_ticket_distribution.py",
            "build_fidc_fixed_income_offer_comparison.py",
        ):
            run(script, "--archive", offer_archive, "--output-dir", staged,
                "--source-as-of-date", as_of, "--expected-sha256", file_sha256(offer_archive),
                "--latest-complete", cut.competence)
        run("build_fidc_closed_offer_placement_regime.py", "--archive", offer_archive,
            "--data-dir", staged, "--output-dir", staged, "--source-as-of-date", as_of,
            "--expected-sha256", file_sha256(offer_archive), "--latest-complete", cut.competence)
        run("build_fidc_market_offer_reconciliation.py", "--archive", offer_archive,
            "--data-dir", staged, "--source-as-of-date", as_of,
            "--expected-archive-sha256", file_sha256(offer_archive), "--latest-complete", cut.competence)
        run("build_fidc_issuance_taxonomy_delta.py", "--data-dir", staged, "--output-dir", staged, "--csv-only")
        run("build_fidc_cedente_top500.py", "--cvm-dir", raw_dir,
            "--data-dir", staged, "--output-dir", staged / "cedente_triage", "--registry-csv",
            staged / "cedente_triage/fidc_cedentes_cadastro_master.csv.gz",
            "--latest-complete", cut.competence)
        run("build_fidc_taxonomy_impact.py", "--repo-dir", ROOT,
            "--data-dir", staged, "--latest-complete", cut.competence)
        run("build_fidc_bcb_expanded_credit.py", "--data-dir", staged, "--latest-complete", cut.competence)
        run("refresh_fidc_emission_field_audit.py", "--data-dir", staged,
            "--latest", cut.competence, "--funds", revision_dir / "base_fundo_cnpj.csv.gz")
        run("publish_fidc_revision_bundle.py", "--data-dir", staged,
            "--publish-dir", revision_dir, "--latest-complete", cut.competence,
            "--input-workbook", frozen_template, "--raw-dir", raw_dir,
            "--provider-history-archive", provider_archive, "--refresh-source-presence",
            "--presence-months", "all", "--skip-download", "--timeout-seconds", "7200")
        current_fingerprints = {
            str(path.relative_to(data_dir)): file_sha256(path)
            for path in data_dir.rglob("*") if path.is_file()
        }
        if current_fingerprints != original_fingerprints:
            raise ValueError("Base publicada mudou durante a atualização; staging preserva os dados novos e nenhuma promoção será feita")
        status = get_revision_export_status(staged)
        if not status.bundle_valid:
            raise ValueError("Pacote gerado inválido para o consumidor: " + status.validation_error)
        bundle = json.loads((revision_dir / "industry_export_bundle.json").read_text())
        backup = cache_dir / ("published-backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
        promote_dataset(staged, data_dir, backup)
        status = get_revision_export_status(data_dir)
        if not status.bundle_valid:
            os.replace(data_dir, staged)
            os.replace(backup, data_dir)
            raise ValueError("Pacote inválido após promoção; base anterior restaurada: " + status.validation_error)
        return {"latest_complete": cut.competence, "bundle_id": bundle.get("bundle_id"),
                "dataset_backup": str(backup), "offers_comparison_meta": cut.to_meta()}


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/industry_study")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / ".cache/cvm-industry-study")
    parser.add_argument("--cadastro-dir", type=Path, default=ROOT / ".cache/cvm-cadastro")
    parser.add_argument("--offers-dir", type=Path, default=ROOT / ".cache/cvm-offers")
    parser.add_argument("--state", type=Path, default=ROOT / ".cache/industry-refresh/state.json")
    parser.add_argument("--input-workbook", type=Path)
    parser.add_argument("--apply", action="store_true", help="reconstruir e publicar somente quando as fontes mudarem")
    parser.add_argument("--check-only", action="store_true", help="verificar fontes; não altera a base publicada")
    args = parser.parse_args(argv)
    if args.apply and args.check_only:
        parser.error("Use --apply ou --check-only")
    for attribute in ("data_dir", "raw_dir", "cadastro_dir", "offers_dir", "state", "input_workbook"):
        path = getattr(args, attribute)
        if path is not None:
            setattr(args, attribute, path.expanduser().resolve())
    if args.state.parent == args.data_dir or args.state.parent.is_relative_to(args.data_dir):
        parser.error("O estado/staging deve ficar fora da base publicada")
    args.state.parent.mkdir(parents=True, exist_ok=True)
    with (args.state.parent / "update.lock").open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Já existe uma atualização da indústria em andamento") from exc
        state = json.loads(args.state.read_text()) if args.state.exists() else {}
        checked = state.get("checked_sources", {})
        records = {}
        for source in discover_sources(args.raw_dir, args.cadastro_dir, args.offers_dir):
            print("[source] " + source.path.name, flush=True)
            records[source.url] = refresh_archive(source, checked.get(source.url, {}), args.state.parent / "source-backups")
        identities = {url: row["sha256"] for url, row in records.items()}
        needed = identities != state.get("published_sources", {})
        integrity_error = ""
        if not needed:
            status = get_revision_export_status(args.data_dir)
            if not status.bundle_valid:
                needed = True
                integrity_error = status.validation_error
        state["checked_sources"] = records
        state["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_json_atomic(args.state, state)
        result = {"status": "update_available" if needed else "unchanged",
                  "archives_checked": len(records), "changed_archives": [row["path"] for row in records.values() if row["changed"]]}
        if integrity_error:
            result["validation_error"] = integrity_error
        if needed and args.apply:
            result.update(rebuild(args, records))
            result["status"] = "published"
            state["published_sources"] = identities
            state["last_publication"] = result
            write_json_atomic(args.state, state)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return result


if __name__ == "__main__":
    main()
