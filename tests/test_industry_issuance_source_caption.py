"""The historical correction discloses the source actually used, independently of current cuts."""
from contextlib import nullcontext

import pandas as pd
import pytest

from services.industry_comparative_period import ComparisonCut
from tabs import tab_industry_study as tab


def _source_rows(snapshot="out/26"):
    return pd.DataFrame([{
        "period_label": "2023 FY", "series_label": "FIDCs",
        "source_as_of_date": f"snapshot {snapshot}",
        "source_dataset": "ANBIMA — Valor Encerrado (aba 02-02-Vlr)",
        "source_url": "https://example.org/official-market.xlsx",
    }] * 2)


@pytest.mark.parametrize("snapshot", ["out/26", "set/26"])
def test_correction_source_follows_its_own_observation(snapshot):
    assert tab._issuance_correction_source_details(_source_rows(snapshot)) == (
        snapshot, "02-02-Vlr", "https://example.org/official-market.xlsx",
    )


def test_unknown_or_conflicting_source_is_explicit_nd():
    assert tab._issuance_correction_source_details(pd.DataFrame()) == ("N/D", "N/D", "")
    absent = _source_rows().drop(columns=["source_as_of_date", "source_dataset", "source_url"])
    assert tab._issuance_correction_source_details(absent) == ("N/D", "N/D", "")
    conflict = _source_rows()
    conflict.loc[1, "source_as_of_date"] = "snapshot set/26"
    assert tab._issuance_correction_source_details(conflict)[0] == "N/D"


@pytest.mark.parametrize("snapshot, corrected", [("out/26", True), ("set/26", True), ("out/26", False)])
def test_rendered_correction_caption_uses_row_source_not_ranking_or_cvm_month(snapshot, corrected, monkeypatch):
    captions = []
    monkeypatch.setattr(tab.st, "caption", captions.append)
    monkeypatch.setattr(tab.st, "columns", lambda *_a, **_k: [nullcontext(), nullcontext()])
    for name in ("markdown", "altair_chart", "dataframe", "warning"):
        monkeypatch.setattr(tab.st, name, lambda *_a, **_k: None)
    cut = ComparisonCut(2026, 10)
    rows = []
    periods = [("2023 FY", "2023-12-31"), ("2024 FY", "2024-12-31"),
               ("2025 FY", "2025-12-31"), (cut.period_id(), cut.period_end.isoformat())]
    for order, (period, end) in enumerate(periods, 1):
        for series in ("FIDCs", "Demais elegíveis"):
            row = dict(period_label=period, period_end=end, period_order=order,
                       series_label=series, view="FIDCs vs demais elegíveis",
                       registered_volume_brl=1e9, yoy_growth=None if order == 1 else .1,
                       excluded_instruments="Cotas de FII", methodology="Correção 2023" if corrected else "CVM sem correção")
            if period == "2023 FY" and series == "FIDCs":
                row.update(_source_rows(snapshot).iloc[0].to_dict())
            rows.append(row)
    tab._render_revision_fixed_income_offer_comparison({
        "latest_complete": cut.competence, "offers_comparison_meta": cut.to_meta(),
        "anbima_rf_ranking_manifest": {"source_reference_competence": "2026-08"},
        "fixed_income_offer_comparison": rows,
    })
    if not corrected:
        assert not any(caption.startswith("Correção 2023:") for caption in captions)
        return
    correction = next(caption for caption in captions if caption.startswith("Correção 2023:"))
    assert f"snapshot {snapshot}, aba 02-02-Vlr" in correction
    assert "https://example.org/official-market.xlsx" in correction
    assert "snapshot mai/26" not in correction and "ago/26" not in correction
    assert "Resolução CVM 160" in correction and "YoY de 2024" in correction
