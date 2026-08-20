from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "industry_study" / "generated_revision" / "directors_update"


def test_carteira_101_one_senior_account_reconciliation() -> None:
    payload = json.loads((OUTPUT / "fidc_directors_update_data.json").read_text())
    summary = payload["carteira_101"]["summary"]
    funds = payload["carteira_101"]["one_senior_account_funds"]

    assert summary["portfolio_funds"] == 101
    assert summary["funds_with_cvm_data"] == 78
    assert summary["one_senior_account_funds"] == 19
    assert summary["pl_coverage"] > 0.98
    assert summary["primary_competence"] == "2026-07"
    assert summary["fallback_competence"] == "2026-06"
    assert len(funds) == 19
    assert all(row["contas_senior_reportadas"] == 1 for row in funds)
    assert [row["pl_publicado_brl"] for row in funds] == sorted(
        (row["pl_publicado_brl"] for row in funds), reverse=True
    )

    with (OUTPUT / "carteira_101_cotistas_senior_202607.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert sum(1 for _ in csv.DictReader(handle)) == 101


def test_financeiro_decomposition_closes_and_keeps_unsegmented_buckets() -> None:
    payload = json.loads((OUTPUT / "fidc_directors_update_data.json").read_text())
    summary = payload["financeiro"]["summary"]
    rows = payload["financeiro"]["decomposition"]

    assert summary["financeiro_funds"] == 1103
    assert round(sum(row["pl_brl"] for row in rows), 2) == round(
        summary["financeiro_pl_brl"], 2
    )
    assert abs(sum(row["share"] for row in rows) - 1) < 1e-8
    assert sum(row["fundos"] for row in rows) == summary["financeiro_funds"]
    assert summary["tapso_inside_financeiro"] is True
    assert summary["tapso_type_applied"] == "Financeiro"
    assert summary["tapso_pl_brl"] > 41_000_000_000
    assert any("sem segregacao" in row["bucket_financeiro"] for row in rows)
