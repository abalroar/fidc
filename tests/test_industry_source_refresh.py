from pathlib import Path
from types import SimpleNamespace
import json
import zipfile

import pytest

from scripts.update_fidc_industry import promote_dataset
from services.industry_source_refresh import SourceArchive, archive_names, file_sha256, refresh_archive


def zipped(path, text="official"):
    with zipfile.ZipFile(path, "w") as stream:
        stream.writestr("report.csv", text)


def response(monkeypatch, *, status="200", text="new", malformed=False):
    def run(command, **kwargs):
        Path(command[command.index("--dump-header") + 1]).write_text(
            'HTTP/1.1 ' + status + '\r\nETag: "source-v2"\r\nLast-Modified: Thu, 08 Oct 2026 12:00:00 GMT\r\n')
        path = Path(command[command.index("--output") + 1])
        if malformed:
            path.write_text("upstream error page")
        elif status == "200":
            zipped(path, text)
        return SimpleNamespace(stdout=status)
    monkeypatch.setattr("services.industry_source_refresh.subprocess.run", run)


def test_official_inventory_accepts_new_years_and_rejects_untrusted_names():
    index = '<a href="inf_mensal_fidc_202701.zip">a</a><a href="inf_mensal_fidc_202608.zip">b</a><a href="../other.zip">c</a>'
    assert archive_names(index, annual=False) == ["inf_mensal_fidc_202608.zip", "inf_mensal_fidc_202701.zip"]
    assert archive_names('<a href="inf_mensal_fidc_2025.zip">a</a>', annual=True) == ["inf_mensal_fidc_2025.zip"]
    with pytest.raises(ValueError):
        archive_names("maintenance", annual=False)


def test_same_month_rectification_preserves_previous_bytes(monkeypatch, tmp_path):
    target = tmp_path / "inf_mensal_fidc_202608.zip"
    zipped(target, "old")
    old_sha = file_sha256(target)
    response(monkeypatch)
    result = refresh_archive(SourceArchive("https://dados.cvm.gov.br/aug.zip", target), {}, tmp_path / "backups")
    assert result["changed"] and result["sha256"] != old_sha
    assert file_sha256(next((tmp_path / "backups").glob("*.zip"))) == old_sha


def test_failed_source_never_replaces_existing_archive(monkeypatch, tmp_path):
    target = tmp_path / "source.zip"
    zipped(target)
    original = target.read_bytes()
    response(monkeypatch, malformed=True)
    with pytest.raises(zipfile.BadZipFile):
        refresh_archive(SourceArchive("https://dados.cvm.gov.br/source.zip", target), {}, tmp_path / "backups")
    assert target.read_bytes() == original


def test_304_requires_verified_local_bytes(monkeypatch, tmp_path):
    target = tmp_path / "source.zip"
    zipped(target)
    response(monkeypatch, status="304")
    source = SourceArchive("https://dados.cvm.gov.br/source.zip", target)
    previous = {"sha256": file_sha256(target), "etag": '"v1"'}
    assert not refresh_archive(source, previous, tmp_path / "backups")["changed"]
    with pytest.raises(ValueError, match="304"):
        refresh_archive(source, {"sha256": "wrong"}, tmp_path / "backups")


def test_promotion_restores_old_dataset_on_failure(monkeypatch, tmp_path):
    destination = tmp_path / "published"
    destination.mkdir()
    (destination / "data.csv").write_text("old")
    staged = tmp_path / "stage"
    staged.mkdir()
    (staged / "data.csv").write_text("new")
    import os
    replace = os.replace
    def failed_replace(source, target):
        if source == staged:
            raise OSError("promotion error")
        replace(source, target)
    monkeypatch.setattr("scripts.update_fidc_industry.os.replace", failed_replace)
    with pytest.raises(OSError):
        promote_dataset(staged, destination, tmp_path / "backup")
    assert (destination / "data.csv").read_text() == "old"
    assert (staged / "data.csv").read_text() == "new"


def test_symlink_cache_is_rejected_before_any_http_request(tmp_path):
    target = tmp_path / "real.zip"
    zipped(target)
    alias = tmp_path / "alias.zip"
    alias.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        refresh_archive(SourceArchive("https://dados.cvm.gov.br/source.zip", alias), {}, tmp_path / "backups")


def _main_fixture(monkeypatch, tmp_path, *, bundle_valid=True, published_sha=None):
    from scripts import update_fidc_industry as update
    source_path = tmp_path / "raw/inf_mensal_fidc_202608.zip"
    source_path.parent.mkdir()
    zipped(source_path)
    source = SourceArchive("https://dados.cvm.gov.br/aug.zip", source_path)
    digest = file_sha256(source_path)
    state = tmp_path / "cache/state.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"published_sources": {source.url: published_sha or digest}}))
    monkeypatch.setattr(update, "discover_sources", lambda *_: [source])
    monkeypatch.setattr(update, "refresh_archive", lambda *_: {
        "path": str(source.path), "sha256": digest, "changed": False,
    })
    monkeypatch.setattr(update, "get_revision_export_status", lambda *_: SimpleNamespace(
        bundle_valid=bundle_valid, validation_error="bundle corrompido" if not bundle_valid else "",
    ))
    arguments = ["--data-dir", str(tmp_path / "published"), "--state", str(state)]
    return update, arguments, state, source, digest


def test_unchanged_verified_sources_skip_all_producers(monkeypatch, tmp_path):
    update, arguments, state, source, digest = _main_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(update, "rebuild", lambda *_: pytest.fail("no-op não deve reconstruir"))
    result = update.main([*arguments, "--apply"])
    assert result["status"] == "unchanged"
    assert json.loads(state.read_text())["published_sources"] == {source.url: digest}


def test_state_inside_published_dataset_is_rejected_before_discovery(monkeypatch, tmp_path):
    from scripts import update_fidc_industry as update
    monkeypatch.setattr(update, "discover_sources", lambda *_: pytest.fail("caminho deve ser rejeitado antes da rede"))
    with pytest.raises(SystemExit) as error:
        update.main(["--data-dir", str(tmp_path / "published"),
                     "--state", str(tmp_path / "published/cache/state.json")])
    assert error.value.code == 2
    assert not (tmp_path / "published").exists()


@pytest.mark.parametrize("apply", [False, True])
def test_corrupt_bundle_prevents_noop_even_with_identical_source_hashes(monkeypatch, tmp_path, apply):
    update, arguments, _, _, _ = _main_fixture(monkeypatch, tmp_path, bundle_valid=False)
    calls = []
    monkeypatch.setattr(update, "rebuild", lambda *args: calls.append(args) or {"bundle_id": "repaired"})
    mode = ["--apply"] if apply else ["--check-only"]
    result = update.main([*arguments, *mode])
    assert result["status"] == ("published" if apply else "update_available")
    assert result["validation_error"] == "bundle corrompido"
    assert len(calls) == int(apply)


def test_concurrent_update_lock_stops_before_checking_sources(monkeypatch, tmp_path):
    import fcntl
    update, arguments, state, _, _ = _main_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(update, "discover_sources", lambda *_: pytest.fail("lock deve bloquear antes da rede"))
    with (state.parent / "update.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="atualização da indústria em andamento"):
            update.main([*arguments, "--apply"])


def test_failed_rebuild_preserves_published_identity_and_next_run_retries(monkeypatch, tmp_path):
    update, arguments, state, source, digest = _main_fixture(monkeypatch, tmp_path, published_sha="old")
    def failed(*_):
        raise RuntimeError("Office falhou")
    monkeypatch.setattr(update, "rebuild", failed)
    with pytest.raises(RuntimeError, match="Office falhou"):
        update.main([*arguments, "--apply"])
    after_failure = json.loads(state.read_text())
    assert after_failure["published_sources"] == {source.url: "old"}
    assert after_failure["checked_sources"][source.url]["sha256"] == digest
    calls = []
    monkeypatch.setattr(update, "rebuild", lambda *args: calls.append(args) or {"bundle_id": "retried"})
    assert update.main([*arguments, "--apply"])["status"] == "published"
    assert len(calls) == 1
    assert json.loads(state.read_text())["published_sources"] == {source.url: digest}


def _rebuild_fixture(monkeypatch, tmp_path, *, statuses=(True, True)):
    from scripts import update_fidc_industry as update
    data = tmp_path / "published"
    revision = data / "generated_revision"
    revision.mkdir(parents=True)
    (revision / "industry_data_revised.xlsx").write_bytes(b"style template")
    (data / "metadata.json").write_text(json.dumps({"competencia_snapshot": "2026-08"}))
    (data / "old.txt").write_text("published dataset")
    cache = tmp_path / "cache"
    cache.mkdir()
    source_dir = tmp_path / "raw"
    source_dir.mkdir()
    records = {}
    for name in ("inf_mensal_fidc_202608.zip", "oferta_distribuicao.zip", "cad_fi_hist_current.zip",
                 "Ranking_de_Renda_Fixa.xlsx", "Anexo_ao_Ranking.xlsx", "Boletim_MK_Anexo.xlsx"):
        source = source_dir / name
        zipped(source)
        records[name] = {"url": "https://official.example/" + name,
                         "path": str(source), "sha256": file_sha256(source)}
    args = SimpleNamespace(data_dir=data, state=cache / "state.json", input_workbook=None,
                           raw_dir=source_dir, offers_dir=source_dir, cadastro_dir=source_dir)
    status_values = iter(statuses)
    monkeypatch.setattr(update, "get_revision_export_status", lambda *_: SimpleNamespace(
        bundle_valid=next(status_values), validation_error="falha de integridade",
    ))
    def publish_stub(script, *arguments):
        if script == "publish_fidc_revision_bundle.py":
            staged = Path(arguments[arguments.index("--data-dir") + 1])
            (staged / "new.txt").write_text("validated new dataset")
            (staged / "generated_revision/industry_export_bundle.json").write_text(json.dumps({"bundle_id": "new"}))
    monkeypatch.setattr(update, "run", publish_stub)
    return update, args, records, publish_stub


def test_source_drift_before_freeze_stops_before_any_producer(monkeypatch, tmp_path):
    update, args, records, _ = _rebuild_fixture(monkeypatch, tmp_path)
    source = Path(records["inf_mensal_fidc_202608.zip"]["path"])
    zipped(source, "rectified before copy")
    monkeypatch.setattr(update, "run", lambda *_: pytest.fail("fonte divergente deve bloquear antes dos produtores"))
    with pytest.raises(ValueError, match="Fonte mudou durante o congelamento"):
        update.rebuild(args, records)
    assert (args.data_dir / "old.txt").is_file()
    assert not (args.data_dir / "new.txt").exists()
    assert list(args.state.parent.glob("industry-update-*"))


def test_source_drift_after_freeze_cannot_change_bytes_consumed_by_producers(monkeypatch, tmp_path):
    update, args, records, publish_stub = _rebuild_fixture(monkeypatch, tmp_path)
    source = Path(records["inf_mensal_fidc_202608.zip"]["path"])
    expected_sha = records[source.name]["sha256"]
    consumed = []
    def run(script, *arguments):
        if script == "build_fidc_industry_study.py":
            zipped(source, "external rectification during rebuild")
        for option in ("--raw-dir", "--cvm-dir"):
            if option in arguments:
                frozen = Path(arguments[arguments.index(option) + 1]) / source.name
                consumed.append(frozen)
                assert frozen != source and file_sha256(frozen) == expected_sha
        publish_stub(script, *arguments)
    monkeypatch.setattr(update, "run", run)
    result = update.rebuild(args, records)
    assert result["bundle_id"] == "new" and len(consumed) >= 3
    assert file_sha256(source) != expected_sha
    assert (args.data_dir / "new.txt").is_file()
    assert (Path(result["dataset_backup"]) / "old.txt").is_file()


@pytest.mark.parametrize("statuses", [(False,), (True, False)])
def test_invalid_staged_or_promoted_bundle_preserves_old_dataset(monkeypatch, tmp_path, statuses):
    update, args, records, _ = _rebuild_fixture(monkeypatch, tmp_path, statuses=statuses)
    with pytest.raises(ValueError, match="(Pacote gerado inválido|base anterior restaurada)"):
        update.rebuild(args, records)
    assert (args.data_dir / "old.txt").read_text() == "published dataset"
    assert not (args.data_dir / "new.txt").exists()
    retained = next(args.state.parent.glob("industry-update-*/industry_study"))
    assert (retained / "new.txt").is_file()
