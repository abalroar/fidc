from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from scripts.build_fidc_industry_study import parse_args as parse_study_args
from scripts.publish_fidc_revision_bundle import (
    ANALYSIS_MANIFEST_NAME,
    BUNDLE_MANIFEST_NAME,
    MATERIALIZED_PPTX_NAME,
    MATERIALIZED_XLSX_NAME,
    PAYLOAD_SCHEMA,
    REQUIRED_ANALYSIS_FILES,
    RevisionBundlePublishError,
    build_bundle_manifest,
    discover_artifact_node_modules,
    discover_latest_complete,
    publish_staged_bundle,
    serialize_analysis_manifest,
    validate_artifact_payload,
    validate_bundle_manifest,
    validate_deck_snapshot,
    validate_renderer_manifest,
)


def test_discover_latest_complete_ignores_newer_preliminary_month(tmp_path: Path) -> None:
    (tmp_path / "industry_competence_status.csv").write_text(
        "competencia,publication_status\n"
        "2026-04,completa\n"
        "2026-05,completa\n"
        "2026-06,preliminar\n",
        encoding="utf-8",
    )

    assert discover_latest_complete(tmp_path) == "2026-05"


def test_discover_artifact_node_modules_uses_explicit_offline_runtime(
    tmp_path: Path,
) -> None:
    node_modules = tmp_path / "node_modules"
    package = node_modules / "@oai" / "artifact-tool" / "package.json"
    package.parent.mkdir(parents=True)
    package.write_text('{"version":"1.2.3"}', encoding="utf-8")

    assert discover_artifact_node_modules(node_modules) == node_modules.resolve()


def _payload() -> dict[str, object]:
    return {
        "schema_version": PAYLOAD_SCHEMA,
        "latest_complete": "2026-05",
        "offers_as_of": "2026-07-15",
        "top20_fidcs": [{}] * 20,
        "top20_outros": [{}] * 20,
        "profiles": [{}] * 20,
        "holder_distribution_history": [
            {"competencia": "2023-12"},
            {"competencia": "2026-05"},
        ],
        "type_mix_history": [
            {"competencia": "2023-12"},
            {"competencia": "2026-05"},
        ],
        "receivables_history": [
            {"competencia": "2023-12"},
            {"competencia": "2026-05"},
        ],
        "provider_concentration_history": [
            {"competencia": "2025-12"},
            {"competencia": "2026-05"},
        ],
        "atlantico_profile": {"cnpj": "09.194.841/0001-51"},
        "atlantico_history": [{"competencia": "2026-05"}],
    }


def test_payload_schema_and_required_historical_comparisons_are_versioned() -> None:
    assert PAYLOAD_SCHEMA == "fidc_revision_artifact_payload_v2"
    payload = _payload()
    validate_artifact_payload(payload, "2026-05")

    for key in (
        "holder_distribution_history",
        "type_mix_history",
        "receivables_history",
        "provider_concentration_history",
        "atlantico_profile",
        "atlantico_history",
    ):
        broken = dict(payload)
        broken.pop(key)
        with pytest.raises(RevisionBundlePublishError, match=key):
            validate_artifact_payload(broken, "2026-05")


def test_bundle_manifest_is_content_addressed_and_validated() -> None:
    payload = _payload()
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    kwargs = {
        "payload_bytes": payload_bytes,
        "payload": payload,
        "analysis_manifest_bytes": b"analysis",
        "pptx_bytes": b"pptx",
        "xlsx_bytes": b"xlsx",
        "input_hashes": {"data/a.csv": "a" * 64},
        "renderer": {
            "artifact_tool_version": "1",
            "node_version": "v22",
            "renderer_sha256": "f" * 64,
        },
    }
    first = build_bundle_manifest(
        **kwargs,
        generated_at_utc="2026-07-16T12:00:00+00:00",
    )
    second = build_bundle_manifest(
        **kwargs,
        generated_at_utc="2026-07-17T12:00:00+00:00",
    )

    assert first["bundle_id"] == second["bundle_id"]
    validate_bundle_manifest(
        first,
        payload_bytes=payload_bytes,
        payload=payload,
        analysis_manifest_bytes=b"analysis",
        pptx_bytes=b"pptx",
        xlsx_bytes=b"xlsx",
    )
    validate_renderer_manifest(
        first,
        payload_bytes=payload_bytes,
        payload=payload,
        pptx_bytes=b"pptx",
        xlsx_bytes=b"xlsx",
        renderer_sha256="f" * 64,
    )

    with pytest.raises(RevisionBundlePublishError, match="snapshot"):
        validate_renderer_manifest(
            first,
            payload_bytes=payload_bytes,
            payload=payload,
            pptx_bytes=b"pptx",
            xlsx_bytes=b"xlsx",
            renderer_sha256="0" * 64,
        )

    broken = dict(first)
    broken["pptx"] = {**dict(first["pptx"]), "sha256": "0" * 64}
    with pytest.raises(RevisionBundlePublishError, match="pptx"):
        validate_bundle_manifest(
            broken,
            payload_bytes=payload_bytes,
            payload=payload,
            analysis_manifest_bytes=b"analysis",
            pptx_bytes=b"pptx",
            xlsx_bytes=b"xlsx",
        )


def test_analysis_manifest_uses_publisher_clock_for_reproducibility() -> None:
    first, first_bytes = serialize_analysis_manifest(
        {"generated_at_utc": "wall-clock-a", "latest_complete": "2026-05"},
        "2026-07-17T00:00:00+00:00",
    )
    second, second_bytes = serialize_analysis_manifest(
        {"generated_at_utc": "wall-clock-b", "latest_complete": "2026-05"},
        "2026-07-17T00:00:00+00:00",
    )

    assert first == second
    assert first_bytes == second_bytes
    assert first["generated_at_utc"] == "2026-07-17T00:00:00+00:00"


def test_publish_staged_bundle_replaces_commit_manifest_last(tmp_path: Path) -> None:
    stage_revision = tmp_path / "stage" / "revision"
    stage_revision.mkdir(parents=True)
    (stage_revision / "artifact_payload.json").write_text("payload", encoding="utf-8")
    (stage_revision / ANALYSIS_MANIFEST_NAME).write_text("analysis", encoding="utf-8")
    (stage_revision / BUNDLE_MANIFEST_NAME).write_text(
        "provisional renderer manifest", encoding="utf-8"
    )
    staged_pptx = tmp_path / "stage" / "deck.pptx"
    staged_xlsx = tmp_path / "stage" / "book.xlsx"
    staged_manifest = tmp_path / "stage" / "bundle.json"
    staged_pptx.write_bytes(b"pptx")
    staged_xlsx.write_bytes(b"xlsx")
    staged_manifest.write_text("manifest", encoding="utf-8")
    publish_dir = tmp_path / "published"
    destinations: list[Path] = []

    def recording_replace(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        destinations.append(Path(target))
        os.replace(source, target)

    publish_staged_bundle(
        staged_revision_dir=stage_revision,
        staged_pptx=staged_pptx,
        staged_xlsx=staged_xlsx,
        staged_bundle_manifest=staged_manifest,
        publish_dir=publish_dir,
        replace=recording_replace,
    )

    assert destinations[-1] == publish_dir / BUNDLE_MANIFEST_NAME
    assert destinations.count(publish_dir / BUNDLE_MANIFEST_NAME) == 1
    assert destinations[-3:-1] == [
        publish_dir / MATERIALIZED_PPTX_NAME,
        publish_dir / MATERIALIZED_XLSX_NAME,
    ]
    assert (publish_dir / BUNDLE_MANIFEST_NAME).read_text() == "manifest"


def _minimal_pptx(text: str) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            f'<p:sld xmlns:p="p" xmlns:a="a"><a:t>{text}</a:t></p:sld>',
        )
    return output.getvalue()


def test_validate_deck_snapshot_rejects_hardcoded_wrong_competence() -> None:
    validate_deck_snapshot(_minimal_pptx("Base consolidada Mai/26"), "2026-05")

    with pytest.raises(RevisionBundlePublishError, match="jun/26"):
        validate_deck_snapshot(_minimal_pptx("Base consolidada Mai/26"), "2026-06")


def test_analysis_manifest_requires_materialized_tables(tmp_path: Path) -> None:
    from scripts.publish_fidc_revision_bundle import validate_analysis_manifest

    for filename in REQUIRED_ANALYSIS_FILES:
        (tmp_path / filename).write_bytes(b"")
    manifest = {
        "latest_complete": "2026-05",
        "files": {name: {} for name in REQUIRED_ANALYSIS_FILES},
        "checks": {
            "top20_fidcs_rows": 20,
            "top20_outros_rows": 20,
            "latest_funds": 4222,
        },
    }

    validate_analysis_manifest(
        manifest,
        revision_dir=tmp_path,
        latest_complete="2026-05",
    )


def test_main_pipeline_exposes_explicit_offline_publish_switch() -> None:
    args = parse_study_args(
        [
            "--publish-revision-bundle",
            "--revision-input-workbook",
            "base.xlsx",
        ]
    )

    assert args.publish_revision_bundle is True
    assert args.revision_input_workbook == "base.xlsx"
