from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from services import industry_revision_export as export
from services.industry_taxonomy_review import (
    TAXONOMY_REVIEW_AUDIT_COLUMNS,
    TAXONOMY_REVIEW_COLUMNS,
    save_taxonomy_review_actions,
    taxonomy_review_audit_digest,
    taxonomy_review_ledger_digest,
)


ARTIFACTS = (
    ("pptx", export.MATERIALIZED_PPTX_NAME, "validate_revision_pptx", "build_revision_pptx_bytes"),
    ("xlsx", export.MATERIALIZED_XLSX_NAME, "validate_revision_xlsx", "build_revision_xlsx_bytes"),
    ("portfolio_xlsx", export.MATERIALIZED_PORTFOLIO_XLSX_NAME, "validate_revision_portfolio_xlsx", "build_revision_portfolio_xlsx_bytes"),
    ("top100_xlsx", export.MATERIALIZED_TOP100_XLSX_NAME, "validate_revision_top100_xlsx", "build_revision_top100_xlsx_bytes"),
    ("html", export.MATERIALIZED_HTML_NAME, "validate_revision_html", "build_revision_html_bytes"),
)


@dataclass
class PublishedBundle:
    data_dir: Path
    manifest: dict[str, object]
    payload: dict[str, object]
    contents: dict[str, bytes]
    artifacts: dict[str, Path]
    sources: dict[str, Path]
    validations: dict[str, int]

    def publish_metadata(self) -> None:
        raw = json.dumps(self.payload, sort_keys=True).encode()
        signature = hashlib.sha256(raw).hexdigest()
        self.manifest.update(payload_sha256=signature, source_signature=signature)
        export.revision_payload_path(self.data_dir).write_bytes(raw)
        export.revision_bundle_manifest_path(self.data_dir).write_text(
            json.dumps(self.manifest, sort_keys=True), encoding="utf-8"
        )


@pytest.fixture
def bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PublishedBundle:
    for name in (
        "FIDC_EXPORT_MANIFEST", "FIDC_REVISION_PPTX", "FIDC_REVISION_XLSX",
        "FIDC_REVISION_PORTFOLIO_XLSX", "FIDC_REVISION_TOP100_XLSX", "FIDC_REVISION_HTML",
        "FIDC_INPUT_WORKBOOK",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(export, "ROOT", tmp_path)
    monkeypatch.setattr(export, "artifact_runtime_available", lambda: False)
    export._cached_validated_bundle.cache_clear()
    data_dir = tmp_path / "data" / "industry_study"
    revision = export.revision_dir(data_dir)
    revision.mkdir(parents=True)
    ledger_path = data_dir / "taxonomy_review_actions.csv"
    audit_path = data_dir / "taxonomy_review_audit.csv"
    save_taxonomy_review_actions(pd.DataFrame(columns=TAXONOMY_REVIEW_COLUMNS), ledger_path)
    pd.DataFrame(columns=TAXONOMY_REVIEW_AUDIT_COLUMNS).to_csv(audit_path, index=False)
    payload = {
        "schema_version": export.PAYLOAD_SCHEMA,
        "latest_complete": "2026-08",
        "offers_as_of": "2026-06-30",
        "taxonomy_review_meta": {
            "ledger_path": "taxonomy_review_actions.csv",
            "ledger_sha256": taxonomy_review_ledger_digest(ledger_path),
            "audit_path": "taxonomy_review_audit.csv",
            "audit_sha256": taxonomy_review_audit_digest(audit_path),
        },
    }
    sources = {
        "data": data_dir / "industry.csv.gz",
        "analysis": revision / "base_fundo.csv.gz",
        "builder": tmp_path / "scripts" / "builder.py",
        "source": tmp_path / ".cache" / "cvm-cadastro" / "cad_fi_hist.zip",
        "curation": tmp_path / "outputs" / "analysis" / "top20_fidcs_curadoria.csv",
        "workbook": tmp_path / "custom" / "input.xlsx",
        "custom_source": tmp_path / "custom" / "registro_fundo_classe.zip",
        "analysis_manifest": revision / "revision_manifest.json",
    }
    for path in sources.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"signed source")
    monkeypatch.setenv("FIDC_INPUT_WORKBOOK", str(sources["workbook"]))
    inputs = {
        "data/industry.csv.gz": "data signature",
        "analysis/base_fundo.csv.gz": "analysis signature",
        "builder/builder.py": "builder signature",
        "source/cad_fi_hist.zip": "source signature",
        "source/registro_fundo_classe.zip": "custom source signature",
        "curation/top20.csv": "curation signature",
        "workbook/input.xlsx": "workbook signature",
    }
    manifest: dict[str, object] = {
        "schema_version": export.BUNDLE_SCHEMA,
        "payload_schema": export.PAYLOAD_SCHEMA,
        "latest_complete": "2026-08",
        "bundle_id": "test-bundle",
        "inputs": inputs,
        "input_paths": {"source/registro_fundo_classe.zip": str(sources["custom_source"])},
    }
    contents: dict[str, bytes] = {}
    paths: dict[str, Path] = {}
    validations: dict[str, int] = {}
    # Mock only expensive Office parsing. The real manifest, hashes, schema,
    # competence and taxonomy guards run on every cache miss.
    for kind, name, validator, _builder in ARTIFACTS:
        raw = f"published {kind} bytes".encode()
        path = revision / name
        path.write_bytes(raw)
        paths[kind] = path
        contents[kind] = raw
        manifest[kind] = {"name": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        validations[kind] = 0

        def validate(raw: bytes, *, _kind: str = kind, **_kwargs: object) -> None:
            assert raw == contents[_kind]
            validations[_kind] += 1

        monkeypatch.setattr(export, validator, validate)
    published = PublishedBundle(data_dir, manifest, payload, contents, paths, sources, validations)
    published.publish_metadata()
    yield published
    export._cached_validated_bundle.cache_clear()


def test_all_five_builders_and_status_share_one_validated_bundle(bundle: PublishedBundle) -> None:
    assert export.get_revision_export_status(bundle.data_dir).bundle_valid
    for kind, _name, _validator, builder in ARTIFACTS:
        assert getattr(export, builder)(bundle.data_dir) == bundle.contents[kind]
    assert export.get_revision_export_status(bundle.data_dir).bundle_valid
    assert set(bundle.validations.values()) == {1}
    assert export._cached_validated_bundle.cache_info().hits == 6


@pytest.mark.parametrize("kind", [row[0] for row in ARTIFACTS])
def test_changed_artifact_cannot_be_served_from_warm_cache(bundle: PublishedBundle, kind: str) -> None:
    export._load_validated_bundle(bundle.data_dir)
    bundle.artifacts[kind].write_bytes(b"corrupt artifact")
    with pytest.raises(export.RevisionExportUnavailable, match="não corresponde ao hash"):
        export.build_revision_pptx_bytes(bundle.data_dir)
    assert not export.get_revision_export_status(bundle.data_dir).bundle_valid


def test_same_size_edit_with_restored_mtime_invalidates_cache(bundle: PublishedBundle) -> None:
    export._load_validated_bundle(bundle.data_dir)
    path = bundle.artifacts["pptx"]
    previous = path.stat()
    path.write_bytes(b"X" * previous.st_size)
    os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    assert path.stat().st_size == previous.st_size
    assert path.stat().st_mtime_ns == previous.st_mtime_ns
    with pytest.raises(export.RevisionExportUnavailable, match="não corresponde ao hash"):
        export.build_revision_pptx_bytes(bundle.data_dir)


@pytest.mark.parametrize("metadata", ["manifest", "payload"])
def test_changed_metadata_keeps_publication_guards(bundle: PublishedBundle, metadata: str) -> None:
    export._load_validated_bundle(bundle.data_dir)
    if metadata == "manifest":
        bundle.manifest["source_signature"] = "incorrect"
        export.revision_bundle_manifest_path(bundle.data_dir).write_text(json.dumps(bundle.manifest))
        message = "assinatura de fontes"
    else:
        bundle.payload["latest_complete"] = "2026-09"
        export.revision_payload_path(bundle.data_dir).write_text(json.dumps(bundle.payload))
        message = "payload mudou"
    with pytest.raises(export.RevisionExportUnavailable, match=message):
        export.build_revision_pptx_bytes(bundle.data_dir)
    assert set(bundle.validations.values()) == {1}


def test_new_publication_invalidates_cache_and_returns_new_bytes(bundle: PublishedBundle) -> None:
    export._load_validated_bundle(bundle.data_dir)
    raw = b"new published pptx bytes"
    bundle.contents["pptx"] = raw
    bundle.artifacts["pptx"].write_bytes(raw)
    bundle.manifest["pptx"].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    bundle.payload["editorial_revision"] = "new revision"
    bundle.publish_metadata()
    assert export.build_revision_pptx_bytes(bundle.data_dir) == raw
    assert set(bundle.validations.values()) == {2}


@pytest.mark.parametrize("kind", ["ledger", "audit"])
def test_changed_taxonomy_cannot_be_served_from_warm_cache(bundle: PublishedBundle, kind: str) -> None:
    export._load_validated_bundle(bundle.data_dir)
    if kind == "ledger":
        action = {column: "" for column in TAXONOMY_REVIEW_COLUMNS}
        action.update(cnpj_fundo="1", status="em_revisao", competencia_referencia="2026-08",
                      competencia_inicio="2026-08", updated_at_utc="2026-10-08T12:00:00+00:00")
        save_taxonomy_review_actions(
            pd.DataFrame([action], columns=TAXONOMY_REVIEW_COLUMNS),
            bundle.data_dir / "taxonomy_review_actions.csv",
        )
    else:
        audit = pd.DataFrame(columns=TAXONOMY_REVIEW_AUDIT_COLUMNS)
        audit.loc[0] = ["event-1", "2026-10-08T12:00:00+00:00", "taxonomy_review",
                        "00000000000001", "status", "pendente", "em_revisao", "em_revisao", "teste"]
        audit.to_csv(bundle.data_dir / "taxonomy_review_audit.csv", index=False)
    with pytest.raises(export.RevisionExportUnavailable, match="curadoria ou auditoria"):
        export.build_revision_pptx_bytes(bundle.data_dir)
    assert set(bundle.validations.values()) == {1}


@pytest.mark.parametrize("source", [
    "data", "analysis", "builder", "source", "curation", "workbook", "custom_source", "analysis_manifest",
])
def test_changed_signed_input_revalidates_all_artifacts(bundle: PublishedBundle, source: str) -> None:
    export._load_validated_bundle(bundle.data_dir)
    bundle.sources[source].write_bytes(b"changed source")
    assert export.build_revision_pptx_bytes(bundle.data_dir) == bundle.contents["pptx"]
    assert set(bundle.validations.values()) == {2}


def test_missing_signed_source_becoming_available_invalidates_cache(bundle: PublishedBundle) -> None:
    source = bundle.sources["source"]
    source.unlink()
    export._load_validated_bundle(bundle.data_dir)
    source.write_bytes(b"newly available source")
    export._load_validated_bundle(bundle.data_dir)
    assert set(bundle.validations.values()) == {2}


def test_artifact_environment_override_changes_selected_candidate(
    bundle: PublishedBundle, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = export._load_validated_bundle(bundle.data_dir)
    override = bundle.data_dir.parent / "custom.pptx"
    override.write_bytes(bundle.contents["pptx"])
    monkeypatch.setenv("FIDC_REVISION_PPTX", str(override))
    second = export._load_validated_bundle(bundle.data_dir)
    assert first.pptx_path == bundle.artifacts["pptx"]
    assert second.pptx_path == override
    assert set(bundle.validations.values()) == {2}


def test_validation_failures_are_not_cached(bundle: PublishedBundle, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def reject(_raw: bytes, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise export.RevisionExportUnavailable("Office inválido")

    monkeypatch.setattr(export, "validate_revision_pptx", reject)
    for _ in range(2):
        with pytest.raises(export.RevisionExportUnavailable, match="Office inválido"):
            export._load_validated_bundle(bundle.data_dir)
    assert calls == 2
    assert export._cached_validated_bundle.cache_info().currsize == 0


def test_source_race_during_validation_is_rejected_and_not_cached(
    bundle: PublishedBundle, monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = export.validate_revision_pptx
    changed = False

    def mutate(raw: bytes, **kwargs: object) -> None:
        nonlocal changed
        validator(raw, **kwargs)
        if not changed:
            bundle.sources["source"].write_bytes(b"raced source")
            changed = True

    monkeypatch.setattr(export, "validate_revision_pptx", mutate)
    with pytest.raises(export.RevisionExportUnavailable, match="durante a validação"):
        export._load_validated_bundle(bundle.data_dir)
    assert export._cached_validated_bundle.cache_info().currsize == 0
    export._load_validated_bundle(bundle.data_dir)
    assert set(bundle.validations.values()) == {2}


def test_source_race_during_cache_hit_is_rejected_and_cache_cleared(
    bundle: PublishedBundle, monkeypatch: pytest.MonkeyPatch,
) -> None:
    export._load_validated_bundle(bundle.data_dir)
    fingerprint = export._bundle_cache_fingerprint
    calls = 0

    def mutate(data_dir: Path) -> tuple[object, ...]:
        nonlocal calls
        result = fingerprint(data_dir)
        calls += 1
        if calls == 1:
            bundle.sources["source"].write_bytes(b"raced source")
        return result

    monkeypatch.setattr(export, "_bundle_cache_fingerprint", mutate)
    with pytest.raises(export.RevisionExportUnavailable, match="durante a leitura"):
        export._load_validated_bundle(bundle.data_dir)
    assert export._cached_validated_bundle.cache_info().currsize == 0
    assert set(bundle.validations.values()) == {1}


def test_simultaneous_builders_share_cold_validation(bundle: PublishedBundle) -> None:
    builders = [getattr(export, row[3]) for row in ARTIFACTS]
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda builder: builder(bundle.data_dir), builders))
    assert results == [bundle.contents[row[0]] for row in ARTIFACTS]
    assert set(bundle.validations.values()) == {1}
