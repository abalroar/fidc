from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest

from services.industry_fixed_income_offer_comparison import (
    ANBIMA_2023_FIDC_CORRECTION_NOTE,
    EXCLUDED_INSTRUMENTS,
    FixedIncomeOfferComparisonError,
    apply_anbima_2023_fidc_issuance_correction,
    build_fixed_income_offer_comparison,
    load_materialized_fixed_income_offer_comparison,
)
from services.industry_market_offer_reconciliation import (
    load_anbima_market_offers,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "industry_study"

#: Valor Encerrado ANBIMA de FIDCs em 2023 FY — Boletim de Mercado de Capitais,
#: snapshot mai/26, aba 02-02-Vlr.  Substitui o volume registrado CVM de
#: R$ 26,5 bi, que subestima 2023 (primeiro ano da Resolução CVM 160).
ANBIMA_FIDC_2023 = 43_746_140_196.22


def test_materialized_comparison_reconciles_fidc_and_rest() -> None:
    frame = load_materialized_fixed_income_offer_comparison(DATA_DIR)
    view_a = frame[frame["view"].eq("FIDCs vs demais elegíveis")]
    expected = {
        "2023 FY": (ANBIMA_FIDC_2023, 353_447_879_570.30),
        "2024 FY": (95_416_726_133.75, 628_733_342_247.23),
        "2025 FY": (116_921_319_054.77, 656_094_670_634.27),
        "2026 jan-jun": (65_488_118_983.56, 246_828_872_386.94),
    }
    for period, (fidc_volume, rest_volume) in expected.items():
        scoped = view_a[view_a["period_label"].eq(period)].set_index(
            "series_label"
        )
        assert scoped.loc["FIDCs", "registered_volume_brl"] == pytest.approx(
            fidc_volume
        )
        assert scoped.loc[
            "Demais elegíveis", "registered_volume_brl"
        ] == pytest.approx(rest_volume)

    yoy = view_a.set_index(["period_label", "series_label"])["yoy_growth"]
    assert yoy.loc[("2024 FY", "FIDCs")] == pytest.approx(
        95_416_726_133.75 / ANBIMA_FIDC_2023 - 1
    )
    assert yoy.loc[("2025 FY", "FIDCs")] == pytest.approx(0.2253755059)
    assert yoy.loc[("2025 FY", "Demais elegíveis")] == pytest.approx(
        0.0435181762
    )
    assert yoy.loc[("2026 jan-jun", "FIDCs")] == pytest.approx(0.1457242904)
    assert yoy.loc[("2026 jan-jun", "Demais elegíveis")] == pytest.approx(
        -0.0779777184
    )


def test_2023_fidc_level_comes_from_anbima_with_documented_source() -> None:
    frame = load_materialized_fixed_income_offer_comparison(DATA_DIR)
    fidc_2023 = frame[
        frame["series_label"].eq("FIDCs") & frame["period_label"].eq("2023 FY")
    ]
    assert not fidc_2023.empty
    assert fidc_2023["registered_volume_brl"].tolist() == pytest.approx(
        [ANBIMA_FIDC_2023] * len(fidc_2023)
    )
    assert (
        fidc_2023["source_dataset"]
        .str.contains("ANBIMA", regex=False)
        .all()
    )
    assert (
        fidc_2023["methodology"]
        .str.contains("Correção 2023", regex=False)
        .all()
    )
    # O universo de 2023 reconcilia com FIDC ANBIMA + demais CVM.
    view_a_2023 = frame[
        frame["view"].eq("FIDCs vs demais elegíveis")
        & frame["period_label"].eq("2023 FY")
    ]
    assert view_a_2023["universe_registered_volume_brl"].iloc[0] == pytest.approx(
        view_a_2023["registered_volume_brl"].sum()
    )


def test_anbima_2023_correction_is_idempotent() -> None:
    anbima = load_anbima_market_offers(DATA_DIR)
    once = load_materialized_fixed_income_offer_comparison(DATA_DIR)
    twice = apply_anbima_2023_fidc_issuance_correction(once, anbima)
    pd.testing.assert_frame_equal(once, twice)


def test_material_2025_instruments_are_selected_by_registered_volume() -> None:
    frame = load_materialized_fixed_income_offer_comparison(DATA_DIR)
    scoped = frame[
        frame["view"].eq("FIDCs vs instrumentos materiais de 2025")
        & frame["period_label"].eq("2025 FY")
    ].sort_values("series_order")
    assert scoped["series_label"].tolist() == [
        "FIDCs",
        "Debêntures",
        "CRI",
        "Notas comerciais",
        "CRA",
    ]
    assert scoped["selected_2025_rank"].tolist() == [0, 1, 2, 3, 4]


def _write_archive(path: Path, rows: list[dict[str, object]]) -> Path:
    frame = pd.DataFrame(rows)
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
            frame.to_csv(index=False, sep=";").encode("latin-1"),
        )
        archive.writestr(
            "oferta_distribuicao.csv",
            pd.DataFrame(columns=legacy_columns)
            .to_csv(index=False, sep=";")
            .encode("latin-1"),
        )
    return path


def _row(
    requirement: str,
    date: str,
    instrument: str,
    volume: float,
    *,
    status: str = "Oferta Encerrada",
    offer_type: str = "Primária",
) -> dict[str, object]:
    return {
        "Numero_Requerimento": requirement,
        "Data_Encerramento": date,
        "Status_Requerimento": status,
        "Valor_Mobiliario": instrument,
        "Tipo_Oferta": offer_type,
        "Valor_Total_Registrado": volume,
    }


def test_builder_excludes_named_instruments_and_open_offers(tmp_path: Path) -> None:
    rows: list[dict[str, object]] = []
    instruments = [
        "Cotas de FIDC",
        "Debêntures",
        "Certificados de Recebíveis Imobiliários",
        "Notas Comerciais",
        "Certificados de Recebíveis do Agronegócio",
    ]
    sequence = 0
    for year in (2023, 2024, 2025, 2026):
        month = 6 if year == 2026 else 12
        for rank, instrument in enumerate(instruments, start=1):
            sequence += 1
            rows.append(
                _row(
                    str(sequence),
                    f"{year}-{month:02d}-15",
                    instrument,
                    float((6 - rank) * year),
                )
            )
    for excluded in EXCLUDED_INSTRUMENTS:
        sequence += 1
        rows.append(_row(str(sequence), "2025-12-15", excluded, 99_000.0))
    rows.append(
        _row(
            "open",
            "2025-12-15",
            "Debêntures",
            1_000_000.0,
            status="Em distribuição",
        )
    )
    archive = _write_archive(tmp_path / "offers.zip", rows)
    result = build_fixed_income_offer_comparison(
        archive,
        expected_archive_sha256=None,
    )
    assert len(result) == 28
    assert not result["instrument_official"].isin(
        {value.upper() for value in EXCLUDED_INSTRUMENTS}
    ).any()
    assert result["universe_closed_offers"].max() == 5


def test_conflicting_requirement_is_blocked(tmp_path: Path) -> None:
    rows = [
        _row("1", "2025-12-15", "Cotas de FIDC", 10.0),
        _row("1", "2025-12-16", "Cotas de FIDC", 20.0),
    ]
    archive = _write_archive(tmp_path / "offers.zip", rows)
    with pytest.raises(
        FixedIncomeOfferComparisonError,
        match="linhas conflitantes",
    ):
        build_fixed_income_offer_comparison(
            archive,
            expected_archive_sha256=None,
        )
