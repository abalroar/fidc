from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts import refresh_fidc_industry_month as refresh


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_valid_monthly_outputs(output_dir: Path, month: str) -> None:
    rows_by_file = {
        "industry_monthly.csv": [
            {"competencia": month, "n_veiculos": 12, "pl_total": 120.0}
        ],
        "segments_monthly.csv": [
            {"competencia": month, "segmento": "Financeiro", "nivel": "top", "valor": 50.0}
        ],
        "flows_monthly.csv": [
            {"competencia": month, "tp_oper": "Captações no Mês", "valor": 10.0}
        ],
        "cotistas_tipo_monthly.csv": [
            {"competencia": month, "tipo_cotista": "Pessoa fisica", "n_cotistas": 10}
        ],
        "admin_monthly.csv": [
            {"competencia": month, "admin_cnpj": "new", "pl": 120.0}
        ],
        "vehicle_monthly.csv.gz": [
            {"competencia": month, "cnpj": "new", "pl": 120.0}
        ],
        "update_audit_monthly.csv": [
            {"competencia": month, "n_veiculos_usados": 12}
        ],
    }
    for filename, rows in rows_by_file.items():
        _write_csv(output_dir / filename, rows)


def _write_valid_snapshot(output_dir: Path, month: str) -> None:
    _write_csv(
        output_dir / "universe_latest.csv",
        [
            {
                "competencia": month,
                "cnpj": "1",
                "pl": 60.0,
                "admin_nome": "Prestador administrador",
                "gestor_nome": "Prestador gestor",
                "custodiante_nome": "Prestador custodiante",
            },
            {
                "competencia": month,
                "cnpj": "2",
                "pl": 40.0,
                "admin_nome": "Prestador administrador",
                "gestor_nome": "Prestador gestor",
                "custodiante_nome": "Prestador custodiante",
            },
        ],
    )
    rows = []
    for role in refresh.EXPECTED_PROVIDER_ROLES:
        rows.append(
            {
                "papel": role,
                "nome": f"Prestador {role}",
                "cnpj_prestador": role,
                "pl": 100.0,
                "n_veiculos": 2,
                "n_fundos": 2,
                "share_pl": 1.0,
                "fonte": "teste",
            }
        )
    _write_csv(output_dir / "prestadores_latest.csv", rows)


def _prepare_existing_industry(industry_dir: Path) -> tuple[bytes, bytes]:
    _write_csv(
        industry_dir / "industry_monthly.csv",
        [{"competencia": "2026-04", "n_veiculos": 10, "pl_total": 100.0}],
    )
    _write_csv(
        industry_dir / "admin_monthly.csv",
        [{"competencia": "2026-04", "admin_cnpj": "old", "pl": 100.0}],
    )
    _write_csv(
        industry_dir / "update_audit_monthly.csv",
        [{"competencia": "2026-04", "n_veiculos_usados": 10}],
    )
    _write_csv(
        industry_dir / "universe_latest.csv",
        [{"competencia": "2026-04", "cnpj": "old", "pl": 100.0}],
    )
    _write_csv(
        industry_dir / "prestadores_latest.csv",
        [{"sentinela": "snapshot anterior"}],
    )
    (industry_dir / "metadata.json").write_text(
        json.dumps({"competencia_snapshot": "202604"}),
        encoding="utf-8",
    )
    return (
        (industry_dir / "universe_latest.csv").read_bytes(),
        (industry_dir / "prestadores_latest.csv").read_bytes(),
    )


def _published_state(industry_dir: Path) -> dict[str, bytes | None]:
    filenames = (
        *refresh.MONTHLY_OUTPUTS,
        "concentration_monthly.csv",
        "industry_competence_status.csv",
        *refresh.SNAPSHOT_OUTPUTS,
        "metadata.json",
    )
    return {
        filename: (industry_dir / filename).read_bytes()
        if (industry_dir / filename).exists()
        else None
        for filename in filenames
    }


def _run_refresh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    requested_month: str,
    status: pd.DataFrame,
    valid_snapshot: bool = True,
    missing_monthly_output: str | None = None,
    divergent_schema_output: str | None = None,
) -> tuple[Path, dict[str, object]]:
    industry_dir = tmp_path / "industry"
    raw_dir = tmp_path / "raw"
    _prepare_existing_industry(industry_dir)
    captured: dict[str, object] = {}

    def fake_pipeline(args: argparse.Namespace) -> None:
        captured["snapshot_month"] = args.snapshot_month
        output_dir = Path(args.output_dir)
        _write_valid_monthly_outputs(output_dir, requested_month)
        if missing_monthly_output:
            (output_dir / missing_monthly_output).unlink()
        if divergent_schema_output:
            _write_csv(
                output_dir / divergent_schema_output,
                [{"competencia": requested_month, "coluna_inesperada": 1.0}],
            )
        if valid_snapshot:
            _write_valid_snapshot(output_dir, requested_month)
        else:
            (output_dir / "universe_latest.csv").write_bytes(b"x")
            _write_valid_snapshot(output_dir, requested_month)
            (output_dir / "universe_latest.csv").write_bytes(b"x")

    monkeypatch.setattr(
        refresh,
        "parse_args",
        lambda: argparse.Namespace(
            month=requested_month,
            industry_dir=industry_dir,
            raw_dir=raw_dir,
            source_zip=None,
            skip_download=True,
        ),
    )
    monkeypatch.setattr(refresh, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(refresh, "build_competence_status", lambda industry, audit: status.copy())

    refresh.main()
    return industry_dir, captured


@pytest.mark.parametrize(
    ("value", "expected"),
    [("2026-05", "202605"), ("202605", "202605")],
)
def test_normalize_snapshot_month(value: str, expected: str) -> None:
    assert refresh.normalize_snapshot_month(value) == expected


@pytest.mark.parametrize("value", ["2026-13", "2026-00", "20265", "2026/05"])
def test_normalize_snapshot_month_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        refresh.normalize_snapshot_month(value)


def test_snapshot_validation_rejects_wrong_competence(tmp_path: Path) -> None:
    _write_valid_snapshot(tmp_path, "2026-04")

    valid, reason = refresh._validate_snapshot_outputs(tmp_path, "2026-05")

    assert valid is False
    assert "competência divergente" in reason


def test_snapshot_validation_rejects_missing_schema(tmp_path: Path) -> None:
    _write_valid_snapshot(tmp_path, "2026-05")
    providers = pd.read_csv(tmp_path / "prestadores_latest.csv").drop(columns="share_pl")
    providers.to_csv(tmp_path / "prestadores_latest.csv", index=False)

    valid, reason = refresh._validate_snapshot_outputs(tmp_path, "2026-05")

    assert valid is False
    assert "colunas obrigatórias" in reason


def test_snapshot_validation_rejects_non_positive_pl(tmp_path: Path) -> None:
    _write_valid_snapshot(tmp_path, "2026-05")
    universe = pd.read_csv(tmp_path / "universe_latest.csv")
    universe["pl"] = 0.0
    universe.to_csv(tmp_path / "universe_latest.csv", index=False)

    valid, reason = refresh._validate_snapshot_outputs(tmp_path, "2026-05")

    assert valid is False
    assert "PL inválido" in reason


def test_snapshot_validation_rejects_truncated_but_renormalized_provider_roles(
    tmp_path: Path,
) -> None:
    _write_valid_snapshot(tmp_path, "2026-05")
    providers = pd.read_csv(tmp_path / "prestadores_latest.csv")
    providers["pl"] = 60.0
    providers["share_pl"] = 1.0
    providers.to_csv(tmp_path / "prestadores_latest.csv", index=False)

    valid, reason = refresh._validate_snapshot_outputs(tmp_path, "2026-05")

    assert valid is False
    assert "PL não reconciliado" in reason
    assert "prestadores=60.00" in reason
    assert "universo_conhecido=100.00" in reason


def test_snapshot_validation_accepts_missing_providers_when_known_pl_reconciles(
    tmp_path: Path,
) -> None:
    _write_valid_snapshot(tmp_path, "2026-05")
    universe = pd.read_csv(tmp_path / "universe_latest.csv")
    universe.loc[universe["cnpj"].eq(2), "gestor_nome"] = ""
    universe.loc[universe["cnpj"].eq(1), "custodiante_nome"] = ""
    universe.to_csv(tmp_path / "universe_latest.csv", index=False)

    providers = pd.read_csv(tmp_path / "prestadores_latest.csv")
    providers.loc[providers["papel"].eq("gestor"), "pl"] = 60.0
    providers.loc[providers["papel"].eq("custodiante"), "pl"] = 40.0
    providers.to_csv(tmp_path / "prestadores_latest.csv", index=False)

    valid, reason = refresh._validate_snapshot_outputs(tmp_path, "2026-05")

    assert valid is True
    assert reason == "ok"


def test_snapshot_validation_accepts_negative_provider_rows_when_role_reconciles(
    tmp_path: Path,
) -> None:
    _write_valid_snapshot(tmp_path, "2026-05")
    providers = pd.read_csv(tmp_path / "prestadores_latest.csv")
    gestor = providers[providers["papel"].eq("gestor")].iloc[0].to_dict()
    providers.loc[providers["papel"].eq("gestor"), ["pl", "share_pl"]] = [
        60.0,
        0.60,
    ]
    providers = pd.concat(
        [
            providers,
            pd.DataFrame(
                [
                    {**gestor, "nome": "Gestor positivo", "pl": 41.0, "share_pl": 0.41},
                    {**gestor, "nome": "Gestor negativo", "pl": -1.0, "share_pl": -0.01},
                ]
            ),
        ],
        ignore_index=True,
    )
    providers.to_csv(tmp_path / "prestadores_latest.csv", index=False)

    valid, reason = refresh._validate_snapshot_outputs(tmp_path, "2026-05")

    assert valid is True
    assert reason == "ok"


def test_latest_complete_month_is_promoted_after_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    status = pd.DataFrame(
        [
            {
                "competencia": "2026-05",
                "publication_status": "completa",
                "vehicle_ratio_vs_previous": 1.0,
                "pl_ratio_vs_previous": 1.0,
            }
        ]
    )

    industry_dir, captured = _run_refresh(
        monkeypatch,
        tmp_path,
        requested_month="2026-05",
        status=status,
    )

    assert captured["snapshot_month"] == "202605"
    universe = pd.read_csv(industry_dir / "universe_latest.csv")
    assert set(universe["competencia"]) == {"2026-05"}
    assert universe["pl"].sum() == pytest.approx(100.0)
    metadata = json.loads((industry_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["competencia_snapshot"] == "202605"
    assert metadata["gerado_em_utc"].startswith("20")
    assert metadata["gerado_em_utc"].endswith("+00:00")
    assert metadata["ultima_atualizacao_status"]["snapshot_promovido"] is True


def test_historical_refresh_preserves_published_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    industry_dir = tmp_path / "industry"
    before_universe, before_providers = _prepare_existing_industry(industry_dir)
    status = pd.DataFrame(
        [
            {
                "competencia": "2026-04",
                "publication_status": "completa",
                "vehicle_ratio_vs_previous": 1.0,
                "pl_ratio_vs_previous": 1.0,
            },
            {
                "competencia": "2026-05",
                "publication_status": "completa",
                "vehicle_ratio_vs_previous": 1.0,
                "pl_ratio_vs_previous": 1.0,
            },
        ]
    )

    refreshed_dir, _ = _run_refresh(
        monkeypatch,
        tmp_path,
        requested_month="2026-04",
        status=status,
    )

    assert refreshed_dir == industry_dir
    assert (industry_dir / "universe_latest.csv").read_bytes() == before_universe
    assert (industry_dir / "prestadores_latest.csv").read_bytes() == before_providers
    metadata = json.loads((industry_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["competencia_snapshot"] == "202604"
    assert metadata["ultima_atualizacao_status"]["snapshot_promovido"] is False


def test_preliminary_month_preserves_published_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    industry_dir = tmp_path / "industry"
    before_universe, before_providers = _prepare_existing_industry(industry_dir)
    status = pd.DataFrame(
        [
            {
                "competencia": "2026-04",
                "publication_status": "completa",
                "vehicle_ratio_vs_previous": 1.0,
                "pl_ratio_vs_previous": 1.0,
            },
            {
                "competencia": "2026-05",
                "publication_status": "preliminar",
                "vehicle_ratio_vs_previous": 0.4,
                "pl_ratio_vs_previous": 0.3,
            },
        ]
    )

    refreshed_dir, _ = _run_refresh(
        monkeypatch,
        tmp_path,
        requested_month="2026-05",
        status=status,
    )

    assert refreshed_dir == industry_dir
    assert (industry_dir / "universe_latest.csv").read_bytes() == before_universe
    assert (industry_dir / "prestadores_latest.csv").read_bytes() == before_providers
    metadata = json.loads((industry_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["competencia_snapshot"] == "202604"
    assert metadata["ultima_atualizacao_status"]["snapshot_promovido"] is False


def test_invalid_candidate_preserves_published_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    industry_dir = tmp_path / "industry"
    before_universe, before_providers = _prepare_existing_industry(industry_dir)
    status = pd.DataFrame(
        [
            {
                "competencia": "2026-05",
                "publication_status": "completa",
                "vehicle_ratio_vs_previous": 1.0,
                "pl_ratio_vs_previous": 1.0,
            }
        ]
    )

    refreshed_dir, _ = _run_refresh(
        monkeypatch,
        tmp_path,
        requested_month="2026-05",
        status=status,
        valid_snapshot=False,
    )

    assert refreshed_dir == industry_dir
    assert (industry_dir / "universe_latest.csv").read_bytes() == before_universe
    assert (industry_dir / "prestadores_latest.csv").read_bytes() == before_providers
    metadata = json.loads((industry_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["competencia_snapshot"] == "202604"
    assert metadata["ultima_atualizacao_status"]["snapshot_promovido"] is False
    assert "vazio" in metadata["ultima_atualizacao_status"]["snapshot_promocao_motivo"]


def test_missing_monthly_candidate_aborts_before_mutating_any_destination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    industry_dir = tmp_path / "industry"
    _prepare_existing_industry(industry_dir)
    before = _published_state(industry_dir)
    status = pd.DataFrame(
        [
            {
                "competencia": "2026-05",
                "publication_status": "completa",
                "vehicle_ratio_vs_previous": 1.0,
                "pl_ratio_vs_previous": 1.0,
            }
        ]
    )

    with pytest.raises(ValueError, match="saída mensal ausente ou vazia: flows_monthly.csv"):
        _run_refresh(
            monkeypatch,
            tmp_path,
            requested_month="2026-05",
            status=status,
            missing_monthly_output="flows_monthly.csv",
        )

    assert _published_state(industry_dir) == before


def test_divergent_monthly_schema_aborts_before_mutating_any_destination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    industry_dir = tmp_path / "industry"
    _prepare_existing_industry(industry_dir)
    before = _published_state(industry_dir)
    status = pd.DataFrame(
        [
            {
                "competencia": "2026-05",
                "publication_status": "completa",
                "vehicle_ratio_vs_previous": 1.0,
                "pl_ratio_vs_previous": 1.0,
            }
        ]
    )

    with pytest.raises(
        ValueError,
        match=r"schema mensal divergente \(industry_monthly.csv\)",
    ):
        _run_refresh(
            monkeypatch,
            tmp_path,
            requested_month="2026-05",
            status=status,
            divergent_schema_output="industry_monthly.csv",
        )

    assert _published_state(industry_dir) == before


def test_atomic_batch_rolls_back_if_a_replace_fails_mid_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "published"
    _write_csv(destination / "one.csv", [{"value": "old-one"}])
    _write_csv(destination / "two.csv", [{"value": "old-two"}])
    before = {
        filename: (destination / filename).read_bytes()
        for filename in ("one.csv", "two.csv")
    }
    original_replace = Path.replace
    candidate_replaces = 0

    def fail_second_candidate_replace(path: Path, target: Path) -> Path:
        nonlocal candidate_replaces
        if path.name.endswith(("one.csv", "two.csv")) and not path.name.endswith(".bak"):
            candidate_replaces += 1
            if candidate_replaces == 2:
                raise OSError("falha simulada")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_second_candidate_replace)

    with pytest.raises(OSError, match="falha simulada"):
        refresh._publish_frames_atomically(
            {
                "one.csv": pd.DataFrame([{"value": "new-one"}]),
                "two.csv": pd.DataFrame([{"value": "new-two"}]),
            },
            destination,
        )

    assert {
        filename: (destination / filename).read_bytes()
        for filename in ("one.csv", "two.csv")
    } == before
    assert not list(destination.glob(".*.bak"))
