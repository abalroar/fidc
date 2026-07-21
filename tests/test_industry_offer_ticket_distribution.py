from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import math
import pandas as pd
import pytest

from services.industry_offer_ticket_distribution import (
    COHORT_FILENAME,
    DISTRIBUTION_FILENAME,
    INDUSTRY_STUDY_DIR,
    OfferTicketDataError,
    build_offer_ticket_distribution,
    load_closed_offer_ticket_cohort,
    load_materialized_offer_ticket_outputs,
)


def test_materialized_ticket_distribution_reconciles_published_cohorts() -> None:
    outputs = load_materialized_offer_ticket_outputs()
    distribution = outputs.distribution
    expected = {
        "2024 FY": (1_009, 95_416_726_133.75, 94_565_635.41501486, 29_999_999.98),
        "2025 FY": (1_470, 116_348_319_054.77, 79_148_516.36378913, 25_000_000.0),
        "2026 jan-jun": (771, 65_488_118_983.56, 84_939_194.53120622, 22_500_000.0),
    }
    for label, (offers, volume, mean_ticket, median_ticket) in expected.items():
        period = distribution[distribution["period_label"].eq(label)]
        assert int(period["closed_offers"].sum()) == offers
        assert math.isclose(float(period["registered_volume_brl"].sum()), volume, abs_tol=0.01)
        assert math.isclose(float(period["period_mean_ticket_brl"].iloc[0]), mean_ticket, abs_tol=0.01)
        assert math.isclose(
            float(period["period_median_ticket_brl"].iloc[0]), median_ticket, abs_tol=0.01
        )
        assert math.isclose(float(period["offer_share"].sum()), 1.0, abs_tol=1e-12)
        assert math.isclose(
            float(period["registered_volume_share"].sum()), 1.0, abs_tol=1e-12
        )
        assert (period["closed_offers"] > 0).all()

    assert len(outputs.cohort) == 3_250
    assert outputs.cohort["numero_requerimento"].nunique() == 3_250


def test_published_bucket_counts_are_stable() -> None:
    distribution = load_materialized_offer_ticket_outputs().distribution
    pivot = distribution.pivot(
        index="bucket_order", columns="period_label", values="closed_offers"
    ).sort_index()
    assert pivot["2024 FY"].tolist() == [231, 237, 175, 158, 94, 83, 31]
    assert pivot["2025 FY"].tolist() == [350, 374, 240, 232, 140, 98, 36]
    assert pivot["2026 jan-jun"].tolist() == [185, 207, 118, 121, 72, 46, 22]


def _write_source_zip(path: Path, rows: list[dict[str, str]]) -> None:
    columns = [
        "Numero_Requerimento",
        "Data_Encerramento",
        "Status_Requerimento",
        "Valor_Mobiliario",
        "Tipo_Oferta",
        "CNPJ_Emissor",
        "Nome_Emissor",
        "Valor_Total_Registrado",
    ]
    csv_text = pd.DataFrame(rows, columns=columns).to_csv(index=False, sep=";")
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("oferta_resolucao_160.csv", csv_text.encode("latin-1"))


def test_source_filters_periods_and_identical_deduplication(tmp_path: Path) -> None:
    base = {
        "Numero_Requerimento": "1",
        "Data_Encerramento": "2024-02-01",
        "Status_Requerimento": "Oferta Encerrada",
        "Valor_Mobiliario": "Cotas de FIDC",
        "Tipo_Oferta": "PRIMARIA",
        "CNPJ_Emissor": "12.345.678/0001-90",
        "Nome_Emissor": "FIDC TESTE",
        "Valor_Total_Registrado": "10000000.00",
    }
    rows = [base, dict(base)]
    rows.append({**base, "Numero_Requerimento": "2", "Status_Requerimento": "Em análise"})
    rows.append({**base, "Numero_Requerimento": "3", "Valor_Mobiliario": "Cotas de FIAGRO - FIDC"})
    rows.append({**base, "Numero_Requerimento": "4", "Tipo_Oferta": "SECUNDARIA"})
    rows.append({**base, "Numero_Requerimento": "5", "Valor_Total_Registrado": "0"})
    rows.append({**base, "Numero_Requerimento": "6", "Data_Encerramento": "2026-06-01"})
    archive_path = tmp_path / "source.zip"
    _write_source_zip(archive_path, rows)

    cohort = load_closed_offer_ticket_cohort(
        archive_path, expected_archive_sha256=None, source_as_of_date="2026-07-20"
    )
    assert cohort["numero_requerimento"].tolist() == ["1", "6"]
    assert cohort.iloc[0]["ticket_bucket"] == "R$ 10–25 mi"


def test_conflicting_requirement_duplicates_are_rejected(tmp_path: Path) -> None:
    base = {
        "Numero_Requerimento": "1",
        "Data_Encerramento": "2024-02-01",
        "Status_Requerimento": "Oferta Encerrada",
        "Valor_Mobiliario": "Cotas de FIDC",
        "Tipo_Oferta": "PRIMARIA",
        "CNPJ_Emissor": "12.345.678/0001-90",
        "Nome_Emissor": "FIDC TESTE",
        "Valor_Total_Registrado": "10000000.00",
    }
    archive_path = tmp_path / "source.zip"
    _write_source_zip(
        archive_path,
        [base, {**base, "Valor_Total_Registrado": "20000000.00"}],
    )
    with pytest.raises(OfferTicketDataError, match="linhas conflitantes"):
        load_closed_offer_ticket_cohort(
            archive_path, expected_archive_sha256=None
        )


def test_distribution_validation_rejects_missing_bucket() -> None:
    cohort = load_materialized_offer_ticket_outputs().cohort
    incomplete = cohort[~(
        cohort["period_label"].eq("2024 FY") & cohort["bucket_order"].eq(7)
    )]
    distribution = build_offer_ticket_distribution(incomplete)
    missing = distribution[
        distribution["period_label"].eq("2024 FY")
        & distribution["bucket_order"].eq(7)
    ].iloc[0]
    assert int(missing["closed_offers"]) == 0
    assert float(missing["offer_share"]) == 0.0


def test_materialized_filenames_are_present() -> None:
    assert (INDUSTRY_STUDY_DIR / COHORT_FILENAME).is_file()
    assert (INDUSTRY_STUDY_DIR / DISTRIBUTION_FILENAME).is_file()
