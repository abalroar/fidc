from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest

from services.industry_market_offer_reconciliation import (
    MarketOfferReconciliationError,
    build_market_offer_reconciliation,
    load_anbima_market_offers,
    load_materialized_market_offer_reconciliation,
    validate_anbima_market_offers,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "industry_study"


def test_materialized_reconciliation_matches_official_snapshot() -> None:
    frame = load_materialized_market_offer_reconciliation(DATA_DIR)
    assert len(frame) == 20
    indexed = frame.set_index(["period_label", "instrument_label"])
    debentures_2025 = indexed.loc[("2025 FY", "Debêntures")]
    assert debentures_2025["cvm_registered_volume_brl"] == pytest.approx(
        453_665_574_708.05
    )
    assert debentures_2025["cvm_harmonization_volume_brl"] == pytest.approx(
        38_753_636_501.0
    )
    assert debentures_2025["cvm_harmonized_volume_brl"] == pytest.approx(
        492_419_211_209.05
    )
    assert debentures_2025["anbima_closed_volume_brl"] == pytest.approx(
        493_390_073_108.00165
    )
    debentures_2026 = indexed.loc[("2026 jan-jun", "Debêntures")]
    assert debentures_2026["anbima_closed_volume_brl"] == pytest.approx(
        169_800_000_000.0
    )
    assert debentures_2026["raw_gap_pct"] == pytest.approx(-0.1282180)
    assert debentures_2026["harmonized_gap_pct"] == pytest.approx(
        0.0448646
    )


def test_anbima_snapshot_blocks_missing_instrument() -> None:
    frame = load_anbima_market_offers(DATA_DIR).iloc[:-1]
    with pytest.raises(MarketOfferReconciliationError, match="20 linhas"):
        validate_anbima_market_offers(frame)


def _automatic_row(
    requirement: str,
    date: str,
    instrument: str,
    volume: float,
) -> dict[str, object]:
    return {
        "Numero_Requerimento": requirement,
        "Data_Encerramento": date,
        "Status_Requerimento": "Oferta Encerrada",
        "Valor_Mobiliario": instrument,
        "Tipo_Oferta": "Primária",
        "Valor_Total_Registrado": volume,
    }


def _synthetic_archive(path: Path) -> Path:
    rows: list[dict[str, object]] = []
    labels = (
        "Debêntures",
        "Outros títulos de securitização",
        "Cotas de FIDC",
        "Certificados de Recebíveis Imobiliários",
        "Notas Comerciais",
        "Certificados de Recebíveis do Agronegócio",
    )
    sequence = 0
    for year in (2023, 2024, 2025, 2026):
        month = 5 if year == 2026 else 12
        for index, label in enumerate(labels, start=1):
            sequence += 1
            rows.append(
                _automatic_row(
                    str(sequence),
                    f"{year}-{month:02d}-15",
                    label,
                    float(year * 1_000_000 + index),
                )
            )
    legacy_columns = [
        "Numero_Registro_Oferta",
        "Numero_Processo",
        "Data_Encerramento_Oferta",
        "Tipo_Ativo",
        "Tipo_Oferta",
        "CNPJ_Emissor",
        "Nome_Emissor",
        "Valor_Total",
        "Nome_Lider",
        "Rito_Oferta",
        "Quantidade_Total",
        "Nr_Pessoa_Fisica",
        "Qtd_Pessoa_Fisica",
    ]
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "oferta_resolucao_160.csv",
            pd.DataFrame(rows).to_csv(index=False, sep=";").encode("latin-1"),
        )
        archive.writestr(
            "oferta_distribuicao.csv",
            pd.DataFrame(columns=legacy_columns)
            .to_csv(index=False, sep=";")
            .encode("latin-1"),
        )
    return path


def test_builder_harmonizes_other_securitization_only_for_debentures(
    tmp_path: Path,
) -> None:
    archive = _synthetic_archive(tmp_path / "offers.zip")
    anbima = load_anbima_market_offers(DATA_DIR)
    result = build_market_offer_reconciliation(
        archive,
        anbima,
        expected_cvm_archive_sha256=None,
    )
    indexed = result.set_index(["period_label", "instrument_label"])
    debentures = indexed.loc[("2025 FY", "Debêntures")]
    fidcs = indexed.loc[("2025 FY", "FIDCs")]
    assert debentures["cvm_harmonization_volume_brl"] > 0
    assert debentures["cvm_harmonized_volume_brl"] > debentures[
        "cvm_registered_volume_brl"
    ]
    assert fidcs["cvm_harmonization_volume_brl"] == 0
    assert fidcs["cvm_harmonized_volume_brl"] == fidcs[
        "cvm_registered_volume_brl"
    ]
