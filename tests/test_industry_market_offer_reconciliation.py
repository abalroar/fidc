from __future__ import annotations

from pathlib import Path
import hashlib
import json
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
    official_path = DATA_DIR / "industry_anbima_market_offers.csv"
    manifest = json.loads(
        (DATA_DIR / "industry_anbima_market_offers_manifest.json").read_text()
    )
    assert hashlib.sha256(official_path.read_bytes()).hexdigest() == manifest["output_sha256"]
    official = load_anbima_market_offers(DATA_DIR).set_index(
        ["period_label", "instrument_label"]
    )
    indexed = frame.set_index(["period_label", "instrument_label"])
    assert len(frame) == len(official) == 20
    assert indexed.index.is_unique and official.index.is_unique
    assert set(indexed.index) == set(official.index)
    meta = manifest["comparison_meta"]
    current = frame[~frame["is_full_year"]]
    assert set(current["period_label"]) == {meta["current_period_id"]}
    assert current["period_start"].eq(meta["current_period_start"]).all()
    assert current["period_end"].eq(meta["current_period_end"]).all()

    for key, row in indexed.iterrows():
        source = official.loc[key]
        for field in ("period_start", "period_end", "is_full_year"):
            assert row[field] == source[field], (key, field)
        assert row["anbima_closed_volume_brl"] == pytest.approx(
            source["closed_volume_brl"], abs=0.01, rel=0,
        )
        assert row["anbima_source_workbook_sha256"] == manifest["source_workbook_sha256"]
        assert row["anbima_source_url"] == source["source_url"] == manifest["source_url"]
        assert row["anbima_source_sheet"] == source["source_sheet"]
        assert row["anbima_source_range"] == source["source_range"]
        raw = float(row["cvm_registered_volume_brl"])
        bridge = float(row["cvm_harmonization_volume_brl"])
        closed = float(source["closed_volume_brl"])
        assert row["cvm_harmonized_volume_brl"] == pytest.approx(raw + bridge, abs=0.01, rel=0)
        assert row["raw_gap_brl"] == pytest.approx(raw - closed, abs=0.01, rel=0)
        assert row["harmonized_gap_brl"] == pytest.approx(raw + bridge - closed, abs=0.01, rel=0)
        if closed:
            assert row["raw_gap_pct"] == pytest.approx((raw - closed) / closed)
            assert row["harmonized_gap_pct"] == pytest.approx((raw + bridge - closed) / closed)
        else:
            assert pd.isna(row["raw_gap_pct"]) and pd.isna(row["harmonized_gap_pct"])
        if key[1] == "Debêntures":
            assert row["cvm_harmonization_instrument"] == "OUTROS TITULOS DE SECURITIZACAO"
        else:
            assert bridge == 0


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


def _synthetic_archive(path: Path, *, years: tuple[int, ...]) -> Path:
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
    for year in years:
        month = 1 if year == max(years) else 12
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
    anbima = load_anbima_market_offers(DATA_DIR)
    years = tuple(sorted(pd.to_datetime(anbima["period_start"]).dt.year.unique()))
    archive = _synthetic_archive(tmp_path / "offers.zip", years=years)
    result = build_market_offer_reconciliation(
        archive,
        anbima,
        expected_cvm_archive_sha256=None,
    )
    assert len(result) == 20
    # Every raw and bridge amount is known from the synthetic source records;
    # self-consistent arithmetic alone cannot establish the source level.
    instrument_positions = {
        "Debêntures": 1, "FIDCs": 3, "CRI": 4,
        "Notas comerciais": 5, "CRA": 6,
    }
    for row in result.to_dict("records"):
        year = pd.Timestamp(row["period_start"]).year
        raw = float(year * 1_000_000 + instrument_positions[row["instrument_label"]])
        bridge = float(year * 1_000_000 + 2) if row["instrument_label"] == "Debêntures" else 0.0
        assert row["cvm_closed_offers"] == 1
        assert row["cvm_registered_volume_brl"] == pytest.approx(raw, abs=0.01, rel=0)
        assert row["cvm_harmonization_volume_brl"] == pytest.approx(bridge, abs=0.01, rel=0)
        assert row["cvm_harmonized_volume_brl"] == pytest.approx(raw + bridge, abs=0.01, rel=0)
