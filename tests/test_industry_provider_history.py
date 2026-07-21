from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest

from services.industry_provider_history import (
    CAD_FI_HISTORY_URL,
    SOURCE_SCOPE_NOTE,
    build_current_fund_cohort,
    build_provider_history_outputs,
    read_provider_history_zip,
    write_provider_history_outputs,
)


def _history_frame(
    role: str,
    rows: list[tuple[str, str, str, str, str]],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "papel": role,
                "cnpj_fundo": fund,
                "prestador_id_legal": provider_id,
                "prestador_nome": provider_name,
                "tipo_pessoa_prestador": "PJ",
                "data_inicio": pd.Timestamp(start),
                "data_fim": pd.Timestamp(end) if end else pd.NaT,
                "arquivo_fonte": f"fixture_{role}.csv",
            }
            for fund, provider_id, provider_name, start, end in rows
        ]
    )


def _fund_base() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "competencia": "2026-05",
                "cnpj_fundo": "10000000000001",
                "denominacao": "FIDC UM",
                "pl": 100.0,
                "is_fic_fidc": False,
            },
            {
                "competencia": "2026-05",
                "cnpj_fundo": "10000000000002",
                "denominacao": "FIDC DOIS",
                "pl": 80.0,
                "is_fic_fidc": False,
            },
            {
                "competencia": "2026-05",
                "cnpj_fundo": "10000000000003",
                "denominacao": "FIDC TRÊS",
                "pl": 60.0,
                "is_fic_fidc": "False",
            },
            {
                "competencia": "2026-05",
                "cnpj_fundo": "10000000000004",
                "denominacao": "FIC EXCLUÍDO",
                "pl": 500.0,
                "is_fic_fidc": "True",
            },
            {
                "competencia": "2026-05",
                "cnpj_fundo": "09195235000150",
                "denominacao": "FIDC SISTEMA PETROBRAS",
                "pl": 1_000.0,
                "is_fic_fidc": False,
            },
            {
                "competencia": "2026-05",
                "cnpj_fundo": "10000000000005",
                "denominacao": "FIDC PL ZERO",
                "pl": 0.0,
                "is_fic_fidc": False,
            },
        ]
    )


def _histories() -> dict[str, pd.DataFrame]:
    return {
        "administrador": _history_frame(
            "administrador",
            [
                ("10000000000001", "11111111000111", "ADMIN A", "2020-01-01", "2025-02-01"),
                ("10000000000001", "22222222000122", "ADMIN B", "2025-02-01", ""),
                ("10000000000002", "62285390000140", "SINGULARE CTVM", "2020-01-01", "2025-01-01"),
                ("10000000000002", "46955383000152", "QI TECH DTVM", "2025-01-01", ""),
                ("10000000000003", "33333333000133", "ADMIN C", "2020-01-01", ""),
                ("10000000000003", "44444444000144", "ADMIN D", "2024-01-01", ""),
            ],
        ),
        "gestor": _history_frame(
            "gestor",
            [
                ("10000000000001", "55555555000155", "GESTOR A", "2020-01-01", ""),
            ],
        ),
        "custodiante": _history_frame(
            "custodiante",
            [
                ("10000000000001", "66666666000166", "CUSTODIANTE A", "2020-01-01", ""),
            ],
        ),
    }


def _ownership() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"participant_pattern": r"(?i)\bSINGULARE\b", "normalized_group": "QI Tech"},
            {"participant_pattern": r"(?i)\bQI\s+TECH\b", "normalized_group": "QI Tech"},
        ]
    )


def _write_zip(path: Path, *, include_custodian: bool = True) -> None:
    frames = {
        "cad_fi_hist_admin.csv": pd.DataFrame(
            [
                {
                    "CNPJ_FUNDO": "10.000.000/0000-01",
                    "CNPJ_ADMIN": "11.111.111/0001-11",
                    "ADMIN": "ADMIN A",
                    "DT_INI_ADMIN": "2020-01-01",
                    "DT_FIM_ADMIN": "",
                }
            ]
        ),
        "cad_fi_hist_gestor.csv": pd.DataFrame(
            [
                {
                    "CNPJ_FUNDO": "10.000.000/0000-01",
                    "CPF_CNPJ_GESTOR": "123.456.789-01",
                    "GESTOR": "GESTOR PF",
                    "PF_PJ_GESTOR": "PF",
                    "DT_INI_GESTOR": "2020-01-01",
                    "DT_FIM_GESTOR": "",
                }
            ]
        ),
        "cad_fi_hist_custodiante.csv": pd.DataFrame(
            [
                {
                    "CNPJ_FUNDO": "10.000.000/0000-01",
                    "CNPJ_CUSTODIANTE": "66.666.666/0001-66",
                    "CUSTODIANTE": "CUSTODIANTE A",
                    "DT_INI_CUSTODIANTE": "2020-01-01",
                    "DT_FIM_CUSTODIANTE": "",
                }
            ]
        ),
    }
    if not include_custodian:
        del frames["cad_fi_hist_custodiante.csv"]
    with ZipFile(path, "w") as archive:
        for filename, frame in frames.items():
            buffer = BytesIO()
            frame.to_csv(buffer, sep=";", index=False, encoding="latin1")
            archive.writestr(filename, buffer.getvalue())


def test_current_cohort_is_positive_pl_ex_fic_and_applies_named_exclusions() -> None:
    cohort = build_current_fund_cohort(_fund_base())

    assert cohort["cnpj_fundo"].tolist() == [
        "10000000000001",
        "10000000000002",
        "10000000000003",
    ]
    assert cohort["pl_mai26_brl"].sum() == 240.0


def test_provider_history_uses_end_date_exclusively_and_may26_pl_as_weight() -> None:
    outputs = build_provider_history_outputs(
        _fund_base(),
        _histories(),
        ownership_curation=_ownership(),
        from_date="2024-12-31",
        to_date="2026-05-31",
    )

    admin = outputs.detail.loc[outputs.detail["papel"].eq("administrador")].set_index(
        "cnpj_fundo"
    )
    assert admin.loc["10000000000001", "origem_prestador_grupo"] == "Admin A"
    assert admin.loc["10000000000001", "destino_prestador_grupo"] == "Admin B"
    assert bool(admin.loc["10000000000001", "mudou_grupo"])
    assert admin.loc["10000000000001", "pl_mai26_brl"] == 100.0

    assert admin.loc["10000000000002", "origem_prestador_grupo"] == "QI Tech"
    assert admin.loc["10000000000002", "destino_prestador_grupo"] == "QI Tech"
    assert not bool(admin.loc["10000000000002", "mudou_grupo"])
    assert bool(admin.loc["10000000000002", "mudou_entidade_legal"])

    assert not bool(admin.loc["10000000000003", "comparavel"])
    assert admin.loc["10000000000003", "origem_status_resolucao"] == (
        "multiplos_registros_ativos"
    )

    admin_links = outputs.links.loc[outputs.links["papel"].eq("administrador")]
    assert admin_links["pl_mai26_brl"].sum() == 180.0
    changed = admin_links.loc[admin_links["mudou_grupo"].astype(bool)].iloc[0]
    assert changed["origem_prestador_grupo"] == "Admin A"
    assert changed["destino_prestador_grupo"] == "Admin B"
    assert changed["pl_mai26_brl"] == 100.0

    coverage = outputs.coverage.loc[
        outputs.coverage["papel"].eq("administrador")
        & outputs.coverage["data_referencia"].astype(str).str.contains("→", regex=False)
    ].iloc[0]
    assert coverage["fundos_coorte"] == 3
    assert coverage["fundos_resolvidos_unicos"] == 2
    assert coverage["pl_resolvido_unico_brl"] == 180.0
    assert coverage["cobertura_pl_resolvida"] == pytest.approx(0.75)
    assert coverage["pl_mudou_grupo_mai26_brl"] == 100.0
    assert outputs.checks["weight_definition"] == "PL de mai/26 por CNPJ legal de fundo"
    assert outputs.checks["source_scope_note"] == SOURCE_SCOPE_NOTE


def test_interval_end_is_exclusive_on_the_reference_date() -> None:
    histories = _histories()
    histories["administrador"] = _history_frame(
        "administrador",
        [
            ("10000000000001", "11111111000111", "ADMIN ANTIGO", "2020-01-01", "2024-12-31"),
            ("10000000000001", "22222222000122", "ADMIN NOVO", "2024-12-31", ""),
        ],
    )
    outputs = build_provider_history_outputs(
        _fund_base(), histories, from_date="2024-12-31", to_date="2026-05-31"
    )
    row = outputs.snapshot.loc[
        outputs.snapshot["papel"].eq("administrador")
        & outputs.snapshot["data_referencia"].eq("2024-12-31")
        & outputs.snapshot["cnpj_fundo"].eq("10000000000001")
    ].iloc[0]
    assert row["prestador_nome"] == "ADMIN NOVO"
    assert row["prestadores_distintos"] == 1


def test_zip_reader_preserves_manager_cpf_and_validates_required_files(tmp_path: Path) -> None:
    archive = tmp_path / "cad_fi_hist.zip"
    _write_zip(archive)
    histories = read_provider_history_zip(
        archive, cohort_cnpjs=["10000000000001"]
    )

    assert set(histories) == {"administrador", "gestor", "custodiante"}
    assert histories["gestor"].iloc[0]["prestador_id_legal"] == "12345678901"
    assert histories["administrador"].iloc[0]["cnpj_fundo"] == "10000000000001"

    invalid = tmp_path / "cad_fi_hist_incomplete.zip"
    _write_zip(invalid, include_custodian=False)
    with pytest.raises(ValueError, match="cad_fi_hist_custodiante.csv"):
        read_provider_history_zip(invalid)


def test_output_manifest_hashes_compact_tables_and_records_source_scope(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "cad_fi_hist.zip"
    _write_zip(archive)
    outputs = build_provider_history_outputs(
        _fund_base(), _histories(), ownership_curation=_ownership()
    )
    output_dir = tmp_path / "generated"
    manifest = write_provider_history_outputs(
        outputs, output_dir, source_archive=archive
    )

    assert manifest["schema_version"] == "provider_history_cvm_v1"
    assert manifest["source"]["url"] == CAD_FI_HISTORY_URL
    assert manifest["source"]["scope_note"] == SOURCE_SCOPE_NOTE
    assert manifest["outputs"]["snapshot"]["rows"] == 18
    assert len(manifest["source"]["archive_sha256"]) == 64
    stored = json.loads(
        (output_dir / "prestadores_historico_cvm_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["outputs"]["links"]["sha256"] == manifest["outputs"]["links"][
        "sha256"
    ]
