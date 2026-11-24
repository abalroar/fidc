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

def test_materialized_comparison_reconciles_fidc_and_rest() -> None:
    frame = load_materialized_fixed_income_offer_comparison(DATA_DIR)
    view_a = frame[frame["view"].eq("FIDCs vs demais elegíveis")]
    # Reconcile FIDC levels against the granular ticket cohort, with the
    # explicitly documented ANBIMA correction retained for the first CVM160 year.
    cohort = pd.read_csv(DATA_DIR / "industry_closed_offer_ticket_cohort.csv.gz")
    reconciliation = pd.read_csv(DATA_DIR / "industry_market_offer_reconciliation.csv")
    anbima = load_anbima_market_offers(DATA_DIR)
    correction = float(anbima.loc[
        anbima["period_label"].eq("2023 FY") & anbima["instrument_label"].eq("FIDCs"),
        "closed_volume_brl",
    ].iloc[0])
    for period, scoped in view_a.groupby("period_label", sort=False):
        indexed = scoped.set_index("series_label")
        assert set(indexed.index) == {"FIDCs", "Demais elegíveis"}
        source = cohort[cohort["period_label"].eq(period)]
        assert not source.empty
        expected_fidc = correction if period == "2023 FY" else source["registered_volume_brl"].sum()
        fidc = indexed.loc["FIDCs"]
        assert fidc["registered_volume_brl"] == pytest.approx(expected_fidc, abs=0.01, rel=0)
        for field in ("period_start", "period_end", "is_full_year"):
            assert source[field].nunique() == 1
            assert fidc[field] == source[field].iloc[0]
        assert scoped["universe_registered_volume_brl"].tolist() == pytest.approx([scoped["registered_volume_brl"].sum()] * 2, abs=0.01, rel=0)
        assert scoped["share_of_period_view_volume"].sum() == pytest.approx(1.0)
        for row in scoped.itertuples(index=False):
            if row.yoy_comparable:
                assert row.yoy_growth == pytest.approx(row.registered_volume_brl / row.previous_registered_volume_brl - 1)
                assert pd.Timestamp(row.previous_period_start).month == pd.Timestamp(row.period_start).month
                assert pd.Timestamp(row.previous_period_end).month == pd.Timestamp(row.period_end).month
                if row.series_label == "FIDCs":
                    previous = cohort[pd.to_datetime(cohort["data_encerramento"]).between(
                        pd.Timestamp(row.previous_period_start), pd.Timestamp(row.previous_period_end),
                    )]
                    previous_volume = correction if row.previous_period_label == "2023 FY" else previous["registered_volume_brl"].sum()
                    assert row.previous_registered_volume_brl == pytest.approx(previous_volume, abs=0.01, rel=0)
            else:
                assert pd.isna(row.previous_registered_volume_brl) and pd.isna(row.yoy_growth)

        # The same material instruments are reconciled separately to the CVM
        # series, while the aggregate view retains all eligible instruments.
        material = frame[
            frame["view"].eq("FIDCs vs instrumentos materiais de 2025")
            & frame["period_label"].eq(period)
            & frame["series_label"].ne("FIDCs")
        ].set_index("series_label")
        bridge_source = reconciliation[reconciliation["period_label"].eq(period)].set_index("instrument_label")
        for instrument, row in material.iterrows():
            assert row["registered_volume_brl"] == pytest.approx(bridge_source.loc[instrument, "cvm_registered_volume_brl"], abs=0.01, rel=0)
        assert indexed.loc["Demais elegíveis", "registered_volume_brl"] >= material["registered_volume_brl"].sum()


def test_2023_fidc_level_comes_from_anbima_with_documented_source() -> None:
    frame = load_materialized_fixed_income_offer_comparison(DATA_DIR)
    fidc_2023 = frame[
        frame["series_label"].eq("FIDCs") & frame["period_label"].eq("2023 FY")
    ]
    assert not fidc_2023.empty
    official = load_anbima_market_offers(DATA_DIR)
    corrected_2023 = float(official.loc[official["period_label"].eq("2023 FY") & official["instrument_label"].eq("FIDCs"), "closed_volume_brl"].iloc[0])
    assert fidc_2023["registered_volume_brl"].tolist() == pytest.approx(
        [corrected_2023] * len(fidc_2023)
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
    from services.industry_comparative_period import ComparisonCut
    cut = ComparisonCut(2026, 6)
    rows: list[dict[str, object]] = []
    instruments = [
        "Cotas de FIDC",
        "Debêntures",
        "Certificados de Recebíveis Imobiliários",
        "Notas Comerciais",
        "Certificados de Recebíveis do Agronegócio",
    ]
    sequence = 0
    for year, month in ((2023, 12), (2024, 12), (2025, 6), (2025, 12), (2026, 6)):
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
        comparison_cut=cut,
    )
    assert len(result) == 28
    assert not result["instrument_official"].isin(
        {value.upper() for value in EXCLUDED_INSTRUMENTS}
    ).any()
    assert result["universe_closed_offers"].max() == 10
    # Exact monetary expectations are independent of the builder's output.
    # Early and late 2025 offers ensure current YTD uses only the early cohort.
    rest = result[
        result["view"].eq("FIDCs vs demais elegíveis")
        & result["series_label"].eq("Demais elegíveis")
    ].set_index("period_label")
    expected = {
        "2023 FY": (20_230.0, 4, None),
        "2024 FY": (20_240.0, 4, 20_230.0),
        "2025 FY": (40_500.0, 8, 20_240.0),
        "2026 jan-jun": (20_260.0, 4, 20_250.0),
    }
    assert set(rest.index) == set(expected)
    for label, (volume, count, prior) in expected.items():
        row = rest.loc[label]
        assert row["registered_volume_brl"] == pytest.approx(volume, abs=0.01, rel=0)
        assert row["closed_offers"] == count
        if prior is None:
            assert pd.isna(row["previous_registered_volume_brl"])
            assert pd.isna(row["yoy_growth"])
        else:
            assert row["previous_registered_volume_brl"] == pytest.approx(prior, abs=0.01, rel=0)
            assert row["yoy_growth"] == pytest.approx(volume / prior - 1)
    assert rest.loc["2026 jan-jun", "previous_period_label"] == "2025 jan-jun"
    assert rest.loc["2026 jan-jun", "previous_period_end"] == "2025-06-30"


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


def test_anbima_2023_correction_is_inactive_when_year_rolls_out(tmp_path: Path) -> None:
    from services.industry_comparative_period import ComparisonCut
    instruments = ("Cotas de FIDC", "Debêntures", "Certificados de Recebíveis Imobiliários",
                   "Notas Comerciais", "Certificados de Recebíveis do Agronegócio")
    rows = [_row(str(index * 5 + rank), f"{year}-{3 if year == 2027 else 12:02d}-15", instrument, float(10_000 - rank))
            for index, year in enumerate(range(2024, 2028))
            for rank, instrument in enumerate(instruments)]
    archive = _write_archive(tmp_path / "offers-2027.zip", rows)
    frame = build_fixed_income_offer_comparison(archive, comparison_cut=ComparisonCut(2027, 3))
    assert set(frame["period_label"]) == {"2024 FY", "2025 FY", "2026 FY", "2027 jan-mar"}
    anbima = load_anbima_market_offers(DATA_DIR)
    anbima = anbima[~anbima["period_label"].eq("2023 FY")].copy()
    corrected = apply_anbima_2023_fidc_issuance_correction(frame, anbima)
    pd.testing.assert_frame_equal(frame, corrected)
