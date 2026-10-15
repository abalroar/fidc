from io import BytesIO

from openpyxl import load_workbook
from pptx import Presentation

from scripts.build_deep_dive_package import get_portfolio_by_id
from services.fidc_analytical_slide import (
    build_fidc_analytical_pptx_bytes,
    build_fidc_analytical_xlsx_bytes,
    build_slide_data,
)


def _portfolio():
    portfolio = get_portfolio_by_id("meutudo_ago26_202608")
    assert portfolio is not None
    return portfolio


def test_meutudo_portfolio_has_expected_scope_and_class_substitution():
    portfolio = _portfolio()
    cnpjs = [fund.cnpj for fund in portfolio.funds]
    assert len(cnpjs) == 10
    assert "63953620000165" in cnpjs
    assert "63953619000130" not in cnpjs


def test_slide_data_reconciles_latest_snapshot_and_rdb_evidence():
    data = build_slide_data(_portfolio().funds)
    assert len(data) == 10
    assert {item.competence for item in data} == {"06/2026"}
    explicit = next(item for item in data if item.cnpj == "54464892000100")
    assert explicit.rdb_status == "Explícito"
    assert "RDB Parati" in explicit.rdb_finding
    for item in data:
        if item.senior_pct_pl is not None and item.subordinated_pct_pl is not None:
            assert abs(item.senior_pct_pl + item.subordinated_pct_pl - 1) < 0.01


def test_outputs_are_native_and_auditable():
    portfolio = _portfolio()
    pptx = build_fidc_analytical_pptx_bytes(portfolio.funds, portfolio_name=portfolio.name)
    prs = Presentation(BytesIO(pptx))
    assert len(prs.slides) >= 11
    assert sum(shape.has_table for slide in prs.slides for shape in slide.shapes) >= 11
    assert all(not (shape.left < 0 or shape.top < 0 or shape.left + shape.width > prs.slide_width or shape.top + shape.height > prs.slide_height) for slide in prs.slides for shape in slide.shapes)

    xlsx = build_fidc_analytical_xlsx_bytes(portfolio.funds, portfolio_name=portfolio.name)
    wb = load_workbook(BytesIO(xlsx), data_only=False)
    assert wb.sheetnames == ["Snapshot", "Emissões", "RDB", "Validações", "Metodologia"]
    assert len(wb["Snapshot"].tables) == 1
    assert len(wb["RDB"].tables) == 1


def test_vehicle_rows_reads_only_requested_cnpjs_and_keeps_latest(tmp_path, monkeypatch):
    import pandas as pd
    from types import SimpleNamespace
    from services import fidc_analytical_slide as analytical

    path = tmp_path / "vehicle_monthly.csv.gz"
    pd.DataFrame({
        "competencia": ["2026-05", "2026-06", "2026-06", "2026-04"],
        "cnpj": [1234567000189, 1234567000189, 99999999000199, 1234567000189],
        "denominacao": ["FIDC A", "FIDC A", "FIDC B", "FIDC A"],
        "pl": [100.0, 200.0, 300.0, 50.0],
        "carteira_dc": [80.0, 150.0, 1.0, 40.0],
        "vl_cotas_subordinadas": [20.0, 50.0, 1.0, 10.0],
        "coluna_nao_usada": ["x", "y", "z", "w"],
    }).to_csv(path, index=False, compression="gzip")
    monkeypatch.setattr(analytical, "VEHICLE_MONTHLY", path)
    monkeypatch.setattr(analytical, "_VEHICLE_CHUNK_ROWS", 2)

    rows = analytical._vehicle_monthly_rows({"01234567000189"})
    assert set(rows["_cnpj"]) == {"01234567000189"}
    assert "coluna_nao_usada" not in rows.columns
    assert rows["pl"].tolist() == [100.0, 200.0, 50.0]

    [data] = analytical.build_slide_data([SimpleNamespace(cnpj="01.234.567/0001-89", display_name="")])
    assert data.competence == "06/2026"
    assert data.pl_mm == 200.0 / 1_000_000
    assert data.subordinated_pct_pl == 0.25
