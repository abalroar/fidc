import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_fidc_industry_study import (  # noqa: E402
    FIC_FIDC_PATTERN,
    _norm_name,
    _strip_digits,
    month_range,
)


def test_month_range_spans_years():
    months = month_range("2013-01", "2014-03")
    assert months[0] == "201301"
    assert months[-1] == "201403"
    assert len(months) == 15


def test_month_range_single_month():
    assert month_range("2026-05", "2026-05") == ["202605"]


def test_strip_digits():
    assert _strip_digits("05.753.599/0001-58") == "05753599000158"
    assert _strip_digits(None) == ""


def test_norm_name_collapses_spaces_and_uppercases():
    assert _norm_name("  BTG  Pactual   Servicos ") == "BTG PACTUAL SERVICOS"


def test_fic_fidc_pattern():
    assert FIC_FIDC_PATTERN.search("XPTO FIC FIDC MULTIMERCADO")
    assert FIC_FIDC_PATTERN.search(
        "FUNDO DE INVESTIMENTO EM COTAS DE FUNDOS DE INVESTIMENTO EM DIREITOS CREDITORIOS ABC"
    )
    assert not FIC_FIDC_PATTERN.search("FUNDO DE INVESTIMENTO EM DIREITOS CREDITORIOS ABC")


def test_versioned_granular_industry_outputs_have_expected_schema():
    data_dir = Path(__file__).resolve().parents[1] / "data" / "industry_study"
    vehicle_cols = set(pd.read_csv(data_dir / "vehicle_monthly.csv.gz", nrows=0).columns)
    audit_cols = set(pd.read_csv(data_dir / "update_audit_monthly.csv", nrows=0).columns)

    assert {
        "competencia",
        "cnpj",
        "denominacao",
        "pl",
        "captacao_liquida",
        "inad_pct_ajustada",
        "subordinacao_pct",
        "cnpj_fundo",
    }.issubset(vehicle_cols)
    assert {
        "competencia",
        "n_veiculos_usados",
        "tab1_coverage",
        "tab2_coverage",
        "x4_coverage",
        "x4_valor_descartado",
    }.issubset(audit_cols)


def test_granular_vehicle_panel_reconciles_to_monthly_aggregates():
    data_dir = Path(__file__).resolve().parents[1] / "data" / "industry_study"
    industry = pd.read_csv(data_dir / "industry_monthly.csv", usecols=["competencia", "pl_total", "captacao_liquida"])
    vehicle = pd.read_csv(
        data_dir / "vehicle_monthly.csv.gz",
        usecols=["competencia", "pl", "captacao_liquida"],
    )
    granular = vehicle.groupby("competencia", as_index=False).agg(
        pl=("pl", "sum"),
        captacao_liquida_granular=("captacao_liquida", "sum"),
    )
    reconciled = industry.merge(granular, on="competencia", how="inner")

    assert (reconciled["pl_total"] - reconciled["pl"]).abs().max() < 1.0
    assert (
        reconciled["captacao_liquida"] - reconciled["captacao_liquida_granular"]
    ).abs().max() < 1.0
