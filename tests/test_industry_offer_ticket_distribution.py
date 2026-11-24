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
    cohort = outputs.cohort
    assert not cohort.empty
    assert cohort["numero_requerimento"].is_unique
    assert (cohort["registered_volume_brl"] > 0).all()
    closing = pd.to_datetime(cohort["data_encerramento"])
    assert closing.between(pd.to_datetime(cohort["period_start"]), pd.to_datetime(cohort["period_end"])).all()
    assert set(distribution["period_label"]).issubset(set(cohort["period_label"]))
    source_hashes = set(cohort["source_archive_sha256"])
    assert len(source_hashes) == 1
    assert set(distribution["source_archive_sha256"]) == source_hashes
    for label, period in distribution.groupby("period_label", sort=False):
        source = cohort[cohort["period_label"].eq(label)]
        tickets = source["registered_volume_brl"]
        volume = float(tickets.sum())
        assert int(period["closed_offers"].sum()) == len(source)
        assert float(period["registered_volume_brl"].sum()) == pytest.approx(volume, abs=0.01, rel=0)
        for field, expected in (
            ("period_mean_ticket_brl", tickets.mean()),
            ("period_median_ticket_brl", tickets.median()),
            ("period_p25_ticket_brl", tickets.quantile(0.25)),
            ("period_p75_ticket_brl", tickets.quantile(0.75)),
            ("period_p90_ticket_brl", tickets.quantile(0.90)),
        ):
            assert period[field].tolist() == pytest.approx([expected] * len(period), abs=0.01, rel=0)
        assert math.isclose(float(period["offer_share"].sum()), 1.0, abs_tol=1e-12)
        assert math.isclose(float(period["registered_volume_share"].sum()), 1.0, abs_tol=1e-12)
        over_100m = tickets[tickets.gt(100_000_000)]
        assert period["over_100m_closed_offers"].eq(len(over_100m)).all()
        assert period["over_100m_registered_volume_brl"].tolist() == pytest.approx([over_100m.sum()] * len(period), abs=0.01, rel=0)
        assert period["over_100m_registered_volume_share"].tolist() == pytest.approx([over_100m.sum() / volume] * len(period))
        for field in ("period_start", "period_end", "is_full_year"):
            assert period[field].nunique() == source[field].nunique() == 1
            assert period[field].iloc[0] == source[field].iloc[0]


def test_published_bucket_counts_follow_declared_ticket_intervals() -> None:
    outputs = load_materialized_offer_ticket_outputs()
    for row in outputs.distribution.itertuples(index=False):
        source = outputs.cohort[outputs.cohort["period_label"].eq(row.period_label)]
        tickets = source["registered_volume_brl"]
        in_bucket = tickets.ge(row.ticket_floor_brl) & tickets.lt(row.ticket_ceiling_brl)
        assert int(row.closed_offers) == int(in_bucket.sum())
        assert row.registered_volume_brl == pytest.approx(float(tickets[in_bucket].sum()), abs=0.01, rel=0)
        assert set(source.loc[in_bucket, "bucket_order"]) <= {row.bucket_order}
        assert row.offer_share == pytest.approx(in_bucket.sum() / len(source))
        assert row.registered_volume_share == pytest.approx(tickets[in_bucket].sum() / tickets.sum())


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
    legacy_text = pd.DataFrame(columns=legacy_columns).to_csv(
        index=False, sep=";"
    )
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("oferta_resolucao_160.csv", csv_text.encode("latin-1"))
        archive.writestr(
            "oferta_distribuicao.csv", legacy_text.encode("latin-1")
        )


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

@pytest.mark.parametrize('year,month', [(2026,8),(2027,3)])
def test_cohort_advances_with_cut_and_excludes_later_closings(tmp_path: Path, year: int, month: int) -> None:
    from services.industry_comparative_period import ComparisonCut
    cut = ComparisonCut(year,month)
    rows = [
        {'Numero_Requerimento':str(index),'Data_Encerramento':date,'Status_Requerimento':'Oferta Encerrada','Valor_Mobiliario':'Cotas de FIDC','Tipo_Oferta':'PRIMARIA','CNPJ_Emissor':'12.345.678/0001-90','Nome_Emissor':'FIDC TESTE','Valor_Total_Registrado':'10000000'}
        for index,date in enumerate([f'{year-3}-01-02',f'{year-2}-01-02',f'{year-1}-01-02',cut.period_end.isoformat(),f'{year}-{month+1:02d}-01'],start=1)
    ]
    archive=tmp_path/'current.zip'
    _write_source_zip(archive,rows)
    cohort=load_closed_offer_ticket_cohort(archive,expected_archive_sha256=None,source_as_of_date=f'{year}-12-31',comparison_cut=cut)
    assert set(cohort.numero_requerimento)=={'1','2','3','4'}
    distribution=build_offer_ticket_distribution(cohort)
    assert distribution.period_label.drop_duplicates().tolist()==[f'{year-3} FY',f'{year-2} FY',f'{year-1} FY',cut.period_id()]
    assert cohort.loc[cohort.numero_requerimento.eq('4'),'period_end'].iloc[0]==cut.period_end.isoformat()
