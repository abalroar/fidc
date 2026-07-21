from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest

from services.industry_closed_offers_source import (
    ClosedOffersSourceError,
    RELEASE_CUTOFF,
    SOURCE_ARCHIVE_SHA256,
    SOURCE_DATASET,
    build_closed_offer_originators,
    load_closed_offer_source,
)


def _offer(requirement: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Numero_Requerimento": requirement,
        "Data_Encerramento": "2026-06-30",
        "Status_Requerimento": "Oferta Encerrada",
        "Valor_Mobiliario": "Cotas de FIDC",
        "Tipo_Oferta": "Primária",
        "CNPJ_Emissor": "12.345.678/0001-90",
        "Nome_Emissor": "FIDC TESTE",
        "Qtde_Total_Registrada": "100",
        "Valor_Total_Registrado": "1000",
        "Publico_alvo": "Profissional",
        "Ativos_alvo": "Direitos creditórios",
        "Descricao_lastro": "Recebíveis diversos",
        "Identificacao_devedores_coobrigados": "",
        "Num_Invest_Pessoa_Natural": "2",
        "Qtde_VM_Pessoa_Natural": "20",
        "Num_Invest_Profissional": "3",
        "Qtde_VM_Profissional": "50",
    }
    row.update(overrides)
    return row


def _write_archive(
    path: Path,
    rows: list[dict[str, object]],
    *,
    drop_columns: tuple[str, ...] = (),
) -> tuple[Path, str]:
    frame = pd.DataFrame(rows).drop(columns=list(drop_columns), errors="ignore")
    payload = frame.to_csv(index=False, sep=";").encode("latin-1")
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(SOURCE_DATASET, payload)
    digest = sha256(path.read_bytes()).hexdigest()
    return path, digest


def test_release_contract_is_pinned_to_june_and_a_sha256_snapshot() -> None:
    assert RELEASE_CUTOFF == "2026-06-30"
    assert re.fullmatch(r"[0-9a-f]{64}", SOURCE_ARCHIVE_SHA256)


def test_source_enforces_archive_hash_and_required_columns(tmp_path: Path) -> None:
    archive_path, digest = _write_archive(
        tmp_path / "offers.zip", [_offer("REQ-1")]
    )

    source, observed_digest = load_closed_offer_source(
        archive_path,
        source_as_of_date="2026-07-21",
        expected_archive_sha256=digest,
    )
    assert observed_digest == digest
    assert source.attrs["source_as_of_date"] == "2026-07-21"

    with pytest.raises(ClosedOffersSourceError, match="SHA-256"):
        load_closed_offer_source(
            archive_path,
            expected_archive_sha256="0" * 64,
        )

    incomplete_path, _ = _write_archive(
        tmp_path / "offers-missing-column.zip",
        [_offer("REQ-2")],
        drop_columns=("Publico_alvo",),
    )
    with pytest.raises(ClosedOffersSourceError, match="Publico_alvo"):
        load_closed_offer_source(
            incomplete_path,
            expected_archive_sha256=None,
        )


def test_source_scopes_primary_closed_fidc_through_june_and_deduplicates(
    tmp_path: Path,
) -> None:
    valid = _offer("REQ-VALID")
    rows = [
        valid,
        dict(valid),
        _offer("REQ-OPEN", Status_Requerimento="Em análise"),
        _offer("REQ-SECONDARY", Tipo_Oferta="Secundária"),
        _offer("REQ-NON-FIDC", Valor_Mobiliario="Debêntures"),
        _offer("REQ-JULY", Data_Encerramento="2026-07-01"),
        _offer("REQ-ZERO", Valor_Total_Registrado="0"),
    ]
    archive_path, _ = _write_archive(tmp_path / "scope.zip", rows)

    source, _ = load_closed_offer_source(
        archive_path,
        expected_archive_sha256=None,
    )

    assert source["Numero_Requerimento"].tolist() == ["REQ-VALID"]
    row = source.iloc[0]
    assert row["data_encerramento"] == pd.Timestamp("2026-06-30")
    assert row["cnpj_emissor"] == "12345678000190"
    assert row["placed_quantity"] == 70
    assert row["placed_volume_proxy_brl"] == 700
    assert row["natural_person_placed_volume_proxy_brl"] == 200
    assert row["investor_accounts"] == 5


def test_source_rejects_conflicting_rows_for_same_requirement(tmp_path: Path) -> None:
    archive_path, _ = _write_archive(
        tmp_path / "conflict.zip",
        [
            _offer("REQ-CONFLICT", Valor_Total_Registrado="1000"),
            _offer("REQ-CONFLICT", Valor_Total_Registrado="1200"),
        ],
    )

    with pytest.raises(ClosedOffersSourceError, match="linhas conflitantes"):
        load_closed_offer_source(
            archive_path,
            expected_archive_sha256=None,
        )


def test_proxy_is_capped_and_originator_rules_are_auditable(tmp_path: Path) -> None:
    archive_path, digest = _write_archive(
        tmp_path / "originators.zip",
        [
            _offer(
                "REQ-CLOUDWALK",
                Nome_Emissor="CLOUDWALK MEIOS DE PAGAMENTO FIDC",
                Ativos_alvo="Recebíveis Mercado Pago",
                Qtde_VM_Profissional="100",
            ),
            _offer(
                "REQ-MERCADO",
                Nome_Emissor="FIDC GENÉRICO",
                Ativos_alvo="Créditos originados pelo Mercado Pago",
                Qtde_Total_Registrada="200",
                Valor_Total_Registrado="2000",
                Num_Invest_Pessoa_Natural="0",
                Qtde_VM_Pessoa_Natural="0",
                Qtde_VM_Profissional="150",
            ),
            _offer(
                "REQ-UNKNOWN",
                Nome_Emissor="FIDC SEM REGRA NOMINAL",
                Valor_Total_Registrado="500",
            ),
        ],
    )
    source, _ = load_closed_offer_source(
        archive_path,
        expected_archive_sha256=digest,
    )

    cloudwalk = source.loc[
        source["Numero_Requerimento"].eq("REQ-CLOUDWALK")
    ].iloc[0]
    assert cloudwalk["placed_quantity"] == 120
    assert cloudwalk["placed_volume_proxy_brl"] == 1000
    assert cloudwalk["natural_person_placed_volume_proxy_brl"] == 200

    originators = build_closed_offer_originators(
        source,
        source_as_of_date="2026-07-21",
        archive_digest=digest,
    ).set_index("originator_group")

    assert set(originators.index) == {
        "CloudWalk",
        "Mercado Pago / Mercado Crédito",
    }
    assert originators.loc["CloudWalk", "registered_volume_brl"] == 1000
    assert originators.loc[
        "Mercado Pago / Mercado Crédito", "registered_volume_brl"
    ] == 2000
    assert originators.loc["CloudWalk", "originator_source_fields"] == "Nome_Emissor"
    assert originators.loc[
        "Mercado Pago / Mercado Crédito", "originator_source_fields"
    ] == "Ativos_alvo"
    assert originators["identified_registered_volume_coverage"].eq(3000 / 3500).all()
