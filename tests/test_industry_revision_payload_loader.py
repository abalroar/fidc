from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from services.industry_revision_export import (
    BUNDLE_SCHEMA,
    RevisionExportUnavailable,
    _load_validated_bundle,
)
from tabs import tab_industry_study


SCHEMA_V1 = "fidc_revision_artifact_payload_v1"
SCHEMA_V2 = "fidc_revision_artifact_payload_v2"
SCHEMA_V3 = "fidc_revision_artifact_payload_v3"


def _ranking_rows(kind: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rank in range(1, 21):
        if kind == "fidcs":
            rows.append(
                {
                    "rank": rank,
                    "denominacao": f"FIDC {rank}",
                    "pl": 21 - rank,
                    "market_share_ex_fic": (21 - rank) / 210,
                }
            )
        else:
            rows.append(
                {
                    "rank_outros": rank,
                    "denominacao": f"Outros {rank}",
                    "pl": 21 - rank,
                    "market_share_outros": (21 - rank) / 210,
                }
            )
    return rows


def _core_payload(schema: str) -> dict[str, object]:
    return {
        "schema_version": schema,
        "latest_complete": "2026-05",
        "offers_as_of": "2026-07-10",
        "classification_coverage": [
            {"categoria": "Oficial ANBIMA", "pl": 100.0, "share": 1.0}
        ],
        "holder_distribution_meta": {
            "minimum_pl_brl": 0.0,
            "fund_coverage": 1.0,
            "pl_coverage": 1.0,
        },
        "investor_composition": [
            {"categoria": "Fundos", "contas": 1_000, "share": 1.0}
        ],
        "pl_history": [
            {
                "competencia": "2026-05",
                "year": 2026,
                "pl_total": 110.0,
                "pl_ex_fic": 100.0,
                "pl_fic_componente": 10.0,
            }
        ],
        "investor_base_history": [
            {
                "competencia": "2026-05",
                "year": 2026,
                "cotistas_total": 1_000,
                "n_veiculos": 100,
            }
        ],
        "holder_distribution": [
            {"bucket": "1 cotista", "fundos": 100, "pl": 100.0}
        ],
        "material_focus_top6": [
            {
                "tipo_anbima": "Financeiro",
                "foco_anbima": "Crédito Pessoal",
                "denominador_pl_subtipo_brl": 100.0,
            }
        ],
        "market_share_top10_fixed": [
            {"papel": "administrador", "participante": "Administrador A", "rank_top10_geral": 1}
        ],
        "monostructure_concentration": [
            {"grupo_economico": "Grupo A", "pl_mono_brl": 10.0, "fundos_mono": 1}
        ],
        "offers_ytd": [{"year": 2026, "volume": 10.0}],
        "originators_2026": {"identified_share": 1.0, "rows": []},
        "provider_concentration": [
            {"papel": "administrador", "top5_share": 0.5, "top10_share": 0.8}
        ],
        "qa_latest": {"veiculos_total": 100, "fundos_total": 100},
        "qa_series": [{"competencia": "2026-05", "inad_pct": 0.01}],
        "receivables": {"rows": [], "reported_total": 100.0},
        "service_model": [
            {
                "modelo_prestacao": "Integrado",
                "fundos": 1,
                "pl": 100.0,
                "share_fundos": 1.0,
                "share_pl": 1.0,
            }
        ],
        "type_mix": [
            {"anbima_tipo": "Financeiro", "pl": 100.0, "share": 1.0}
        ],
        "market_share": [
            {
                "papel": "administrador",
                "tipo_anbima": "Financeiro",
                "foco_anbima": "Crédito Pessoal",
                "participante_bucket": "Administrador A",
                "share_subtipo": 1.0,
                "publication_status": "publicável",
            }
        ],
        "top20_fidcs": _ranking_rows("fidcs"),
        "top20_outros": _ranking_rows("outros"),
        "profiles": [
            {
                "rank": 1,
                "cnpj_fundo_formatado": "00.000.000/0001-00",
                "nome_curto": "FIDC 1",
                "pl": 20.0,
            }
        ],
    }


def _payload_for_schema(schema: str) -> dict[str, object]:
    payload = _core_payload(schema)
    if schema in {SCHEMA_V2, SCHEMA_V3}:
        payload.update(
            {
                "holder_distribution_history": [
                    {
                        "competencia": "2023-12",
                        "bucket": "1 cotista",
                        "fundos": 80,
                        "pl": 70.0,
                    }
                ],
                "holder_distribution_meta_history": [
                    {
                        "competencia": "2023-12",
                        "minimum_pl_brl": 0.0,
                        "fund_coverage": 1.0,
                        "pl_coverage": 1.0,
                    }
                ],
                "provider_concentration_history": [
                    {
                        "competencia": "2025-12",
                        "papel": "administrador",
                        "top5_share": 0.5,
                        "top10_share": 0.8,
                        "coverage_pl": 0.95,
                        "missing_share": 0.05,
                    }
                ],
                "receivables_history": [
                    {
                        "competencia": "2023-12",
                        "segmento": "Financeiro",
                        "valor": 70.0,
                        "share_reported": 1.0,
                    }
                ],
                "receivables_meta_history": [
                    {
                        "competencia": "2023-12",
                        "reported_total": 70.0,
                        "portfolio_total": 70.0,
                        "gap": 0.0,
                        "gap_pct": 0.0,
                    }
                ],
                "type_mix_history": [
                    {
                        "competencia": "2023-12",
                        "anbima_tipo": "Financeiro",
                        "pl": 70.0,
                        "share": 1.0,
                    }
                ],
            }
        )
    if schema == SCHEMA_V3:
        payload.update(
            {
                "provider_historical_ranking": [
                    {
                        "competencia": "2025-12",
                        "papel": "administrador",
                        "participante": "Administrador A",
                        "rank_periodo": 1,
                        "pl_brl": 100.0,
                    }
                ],
                "market_share_scope_summary": [
                    {
                        "papel": "administrador",
                        "pl_total_ex_fic_brl": 100.0,
                        "cobertura_classificacao_14_focos_pl": 0.98,
                    }
                ],
                "market_share_exclusions": [
                    {"cnpj": "09195235000150", "fund": "FIDC Sistema Petrobras"},
                    {"cnpj": "26287464000114", "fund": "FIDC TAPSO"},
                ],
                "acquiring_taxonomy": {"classification": "Tabela II.g - Cartão"},
            }
        )
    return payload


def _write_payload(data_dir: Path, payload: dict[str, object]) -> bytes:
    revision_dir = data_dir / "generated_revision"
    revision_dir.mkdir(parents=True)
    payload_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    (revision_dir / "artifact_payload.json").write_bytes(payload_bytes)
    return payload_bytes


def _load_payload(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    monkeypatch.setattr(tab_industry_study, "_DATA_DIR", data_dir)
    return tab_industry_study._load_industry_revision_payload.__wrapped__("test-signature")


@pytest.mark.parametrize("schema", [SCHEMA_V2, SCHEMA_V3])
def test_revision_payload_loader_accepts_each_published_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    schema: str,
) -> None:
    payload = _payload_for_schema(schema)
    _write_payload(tmp_path, payload)

    loaded = _load_payload(tmp_path, monkeypatch)

    assert loaded == payload
    if schema == SCHEMA_V2:
        assert "market_share_scope_summary" not in loaded


def test_revision_payload_loader_rejects_v1_without_historical_comparisons(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload_for_schema(SCHEMA_V1)
    _write_payload(tmp_path, payload)

    with pytest.raises(
        ValueError,
        match=r"schema do payload revisado incompatível: fidc_revision_artifact_payload_v1",
    ):
        _load_payload(tmp_path, monkeypatch)


def test_revision_payload_loader_rejects_unknown_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload_for_schema(SCHEMA_V3)
    payload["schema_version"] = "fidc_revision_artifact_payload_v4"
    _write_payload(tmp_path, payload)

    with pytest.raises(
        ValueError,
        match=r"schema do payload revisado incompatível: fidc_revision_artifact_payload_v4",
    ):
        _load_payload(tmp_path, monkeypatch)


def test_revision_payload_loader_requires_both_v3_market_share_exclusions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload_for_schema(SCHEMA_V3)
    payload["market_share_exclusions"] = [
        {"cnpj": "09.195.235/0001-50", "fund": "FIDC Sistema Petrobras"}
    ]
    _write_payload(tmp_path, payload)

    with pytest.raises(
        ValueError,
        match="payload v3 sem as exclusões nominais de Sistema Petrobras e TAPSO",
    ):
        _load_payload(tmp_path, monkeypatch)


@pytest.mark.parametrize(
    ("schema", "missing_block"),
    [
        (SCHEMA_V2, "receivables_history"),
        (SCHEMA_V3, "acquiring_taxonomy"),
    ],
)
def test_revision_payload_loader_enforces_blocks_introduced_by_each_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    schema: str,
    missing_block: str,
) -> None:
    payload = _payload_for_schema(schema)
    del payload[missing_block]
    _write_payload(tmp_path, payload)

    with pytest.raises(ValueError, match=rf"payload revisado incompleto:.*{missing_block}"):
        _load_payload(tmp_path, monkeypatch)


@pytest.mark.parametrize(
    ("manifest_override", "expected_error"),
    [
        (
            {"payload_schema": SCHEMA_V2},
            "schema do payload diverge do bundle publicado",
        ),
        (
            {"payload_sha256": "0" * 64},
            "payload revisado diverge do hash do bundle publicado",
        ),
    ],
)
def test_revision_payload_loader_rejects_bundle_payload_divergence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest_override: dict[str, str],
    expected_error: str,
) -> None:
    payload = _payload_for_schema(SCHEMA_V3)
    payload_bytes = _write_payload(tmp_path, payload)
    manifest = {
        "payload_schema": SCHEMA_V3,
        "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        **manifest_override,
    }
    manifest_path = tmp_path / "generated_revision" / "industry_export_bundle.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_error):
        _load_payload(tmp_path, monkeypatch)


def test_office_export_remains_strictly_v3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload_for_schema(SCHEMA_V2)
    payload_bytes = _write_payload(tmp_path, payload)
    payload_hash = hashlib.sha256(payload_bytes).hexdigest()
    manifest = {
        "schema_version": BUNDLE_SCHEMA,
        "payload_schema": SCHEMA_V2,
        "payload_sha256": payload_hash,
        "source_signature": payload_hash,
        "latest_complete": "2026-05",
    }
    manifest_path = tmp_path / "generated_revision" / "industry_export_bundle.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.delenv("FIDC_EXPORT_MANIFEST", raising=False)

    with pytest.raises(
        RevisionExportUnavailable,
        match="schema do payload revisado incompatível",
    ):
        _load_validated_bundle(tmp_path)
