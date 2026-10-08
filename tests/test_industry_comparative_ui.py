from __future__ import annotations

import pytest
import pandas as pd
from streamlit.testing.v1 import AppTest

from services.industry_comparative_period import ComparisonCut
from tabs import tab_industry_study as tab


def _offer_row(year: int, end: str, volume: float = 1e9) -> dict[str, object]:
    return {
        "year": year, "period_start": f"{year}-01-01", "period_end": end,
        "closed_offers": 10, "registered_volume_brl": volume,
        "mean_registered_ticket_brl": volume / 10, "median_registered_ticket_brl": volume / 20,
        "natural_person_placed_volume_share": 0.1,
        "placed_quantity_registered_volume_coverage": 0.9,
        "professional_target_registered_volume_share": 0.8,
    }


@pytest.mark.parametrize("competence", ["2026-08", "2026-09", "2027-03"])
def test_generic_comparable_window_overrides_legacy_june_and_advances_year(competence: str) -> None:
    cut = ComparisonCut.from_competence(competence)
    row = _offer_row(cut.year, cut.period_end.isoformat(), 9e9)
    payload = {
        "offers_comparison_meta": cut.to_meta(),
        "closed_offers_ytd_comparable": [row],
        "closed_offers_jan_june": [_offer_row(2026, "2026-06-30", 2e9)],
    }
    assert tab._revision_offers_cutoff(payload) == cut.period_end.isoformat()
    assert tab._revision_offer_current_row(payload)["registered_volume_brl"] == 9e9
    assert tab._revision_offer_comparison_meta(payload)["period_label"] == cut.period_label()
    assert tab._revision_offer_period_display(cut.period_id(), cut.to_meta()) == cut.period_label()


def test_legacy_comparable_uses_its_own_end_date_and_preserves_unknown_cutoff() -> None:
    assert tab._revision_offers_cutoff({
        "latest_complete": "2026-08",
        "closed_offers_jan_june": [_offer_row(2026, "2026-06-30")],
    }) == "2026-06-30"
    assert tab._revision_offers_cutoff({"closed_offers_jan_may": [{"year": 2026}]}) == "N/D"


@pytest.mark.parametrize("end,previous", [("2027-07-10", "2026-07-10"), ("2028-02-29", "2027-02-28")])
def test_legacy_comparable_preserves_exact_date_without_extending_window(end: str, previous: str) -> None:
    meta = tab._revision_offer_comparison_meta({
        "closed_offers_jan_may": [_offer_row(int(end[:4]), end)],
    })
    assert meta["current_period_end"] == end
    assert meta["previous_period_end"] == previous


def test_conclusion_fallback_uses_august_offer_share_and_keeps_majority_phrase() -> None:
    cut = ComparisonCut(2026, 8)
    rows = tab._revision_conclusion_items({
        "latest_complete": "2026-08", "offers_comparison_meta": cut.to_meta(),
        "conclusion_metrics": {"competencia": "2026-08", "holder_ge_200m_share_fundos_ate_10_contas": 0.574728},
        "closed_offer_ticket_distribution": [
            {"period_end": "2026-08-31", "ticket_floor_brl": 500e6, "registered_volume_share": 0.44526},
            {"period_end": "2026-06-30", "ticket_floor_brl": 500e6, "registered_volume_share": 0.40},
        ],
    })
    assert "45%" in rows[4][1]
    assert "40%" not in rows[4][1]
    assert rows[2][1] == "Mais da metade dos fundos de maior porte reporta até dez contas."


def _offers_app(payload: dict[str, object]) -> None:
    from tabs.tab_industry_study import _render_revision_offers
    _render_revision_offers(payload)


@pytest.mark.parametrize("competence", ["2026-08", "2026-09", "2027-01", "2027-03"])
def test_offer_curves_stop_at_dynamic_month_and_top15_uses_current_machine_id(
    competence: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    cut = ComparisonCut.from_competence(competence)
    source_cut = ComparisonCut(cut.year if cut.month > 1 else cut.year - 1,
                               cut.month - 1 if cut.month > 1 else 12)
    secondary_manifest = {"comparison_meta": source_cut.to_meta(),
                          "cvm_latest_complete_meta": cut.to_meta(),
                          "source_reference_competence": source_cut.competence,
                          "source_lag_months": 1}
    payload = {
        "latest_complete": competence, "offers_comparison_meta": cut.to_meta(),
        "anbima_market_offers_manifest": secondary_manifest,
        "anbima_rf_ranking_manifest": secondary_manifest,
        "closed_offers_ytd_comparable": [_offer_row(cut.year, cut.period_end.isoformat())],
        "closed_offers_annual": [_offer_row(year, f"{year}-12-31") for year in range(cut.year - 2, cut.year + 1)],
        "closed_offers_monthly": [
            {"year": year, "month": month, "registered_volume_brl": 1e8}
            for year in range(cut.year - 2, cut.year + 1) for month in range(1, 13)
        ],
    }
    top_row = {field: "N/D" for field in (
        "fund_name_short", "originator_group", "leader_name", "ibba_participant_label",
        "firm_commitment_label", "publico", "investor_categories", "coordinator_entities",
        "rating_agency", "rating_assigned",
    )}
    top_row.update(period_label=cut.period_id(), rank=1, registered_volume_brl=1e9, investor_count=3)
    payload["closed_offer_top15"] = [top_row]
    payload["closed_offer_top15_summary"] = [{
        "period_label": cut.period_id(), "period_order": 5, "period_end": cut.period_end.isoformat(),
        "top15_offers": 1, "top15_registered_volume_brl": 1e9, "top15_share_of_period_volume": 1,
        "ibba_lead_offers_top15": 1, "ibba_participation_offers_top15": 1,
    }]
    monkeypatch.setattr(tab, "_render_revision_issuance_taxonomy", lambda *_: None)
    charts: dict[str, dict[str, object]] = {}
    actual = tab.st.altair_chart

    def capture(chart, **kwargs):
        charts[kwargs["key"]] = chart.to_dict()
        return actual(chart, **kwargs)

    monkeypatch.setattr(tab.st, "altair_chart", capture)
    app = AppTest.from_function(_offers_app, args=(payload,)).run()
    assert not app.exception and not app.error
    assert app.tabs[0].label == cut.period_label()
    chart = charts["industry-revision-closed-offers-cumulative"]
    rows = next(iter(chart["datasets"].values()))
    assert max(row["month"] for row in rows if row["year"] == cut.year) == cut.month
    assert max(row["month"] for row in rows if row["year"] == cut.year - 1) == 12
    text = " ".join(element.value for element in [*app.markdown, *app.caption])
    assert cut.period_label() in text
    assert source_cut.period_label() not in text
    assert tab._revision_offer_comparison_meta(payload) == cut.to_meta()
    assert "jun/26" not in text and "jan–jun/26" not in text


def _regime_app(payload: dict[str, object]) -> None:
    from tabs.tab_industry_study import _render_revision_closed_offer_placement_regime
    _render_revision_closed_offer_placement_regime(payload)


def test_placement_regime_accepts_august_labels_and_preserves_zero() -> None:
    cut = ComparisonCut(2026, 8)
    rows = [{
        "period_order": index, "period_label": period, "regime_order": 1,
        "placement_regime": "Melhores esforços", "closed_offers": 0,
        "closed_offers_share": 0, "registered_volume_brl": 0,
        "registered_volume_share": 0, "period_closed_offers": 1,
        "period_registered_volume_brl": 1e9,
    } for index, period in enumerate(("2024 FY", "2025 FY", cut.period_id()))]
    app = AppTest.from_function(_regime_app, args=({
        "offers_comparison_meta": cut.to_meta(), "closed_offer_placement_regime": rows,
    },)).run()
    assert not app.exception and not app.error
    text = " ".join(element.value for element in app.markdown)
    assert "jan–ago/26" in text and "0%" in text


def _comparison_app(payload: dict[str, object]) -> None:
    from tabs.tab_industry_study import _render_revision_fixed_income_offer_comparison
    _render_revision_fixed_income_offer_comparison(payload)


@pytest.mark.parametrize("competence", ["2026-08", "2027-03"])
def test_comparison_narrative_and_table_use_row_growth_for_current_window(
    competence: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    cut = ComparisonCut.from_competence(competence)
    rows = [{
        "period_label": period, "period_order": order, "period_end": end,
        "registered_volume_brl": 1e9, "yoy_growth": growth,
        "series_label": series, "view": "FIDCs vs demais elegíveis", "excluded_instruments": "",
    } for order, period, end in ((0, f"{cut.year - 1} FY", f"{cut.year - 1}-12-31"),
                                (1, cut.period_id(), cut.period_end.isoformat()))
       for series, growth in (("FIDCs", 0.23), ("Demais elegíveis", -0.11))]
    monkeypatch.setattr(tab, "_issuance_correction_applied", lambda *_: False)
    charts = {}
    actual_chart = tab.st.altair_chart
    def capture(chart, **kwargs):
        charts[kwargs["key"]] = chart.to_dict()
        return actual_chart(chart, **kwargs)
    monkeypatch.setattr(tab.st, "altair_chart", capture)
    app = AppTest.from_function(_comparison_app, args=({
        "offers_comparison_meta": cut.to_meta(), "fixed_income_offer_comparison": rows,
    },)).run()
    assert not app.exception and not app.error and not app.warning
    note = next(element.value for element in app.markdown if "industry-note" in element.value)
    assert cut.period_label() in note and "23%" in note and "-11%" in note
    assert "14,6%" not in note
    assert cut.period_label() in app.dataframe[0].value.columns
    chart = charts["industry-fixed-income-fidc-vs-rest"]
    chart_rows = next(iter(chart["datasets"].values()))
    assert cut.period_label() in {row["Período"] for row in chart_rows}


def _taxonomy_app(payload: dict[str, object]) -> None:
    from tabs.tab_industry_study import _render_revision_issuance_taxonomy
    _render_revision_issuance_taxonomy(payload)


@pytest.mark.parametrize("competence", ["2026-08", "2027-03"])
def test_taxonomy_uses_dynamic_window_and_current_category_delta(
    competence: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import industry_issuance_taxonomy as taxonomy
    cut = ComparisonCut.from_competence(competence)
    rows = []
    periods = [(str(year), str(year)) for year in range(cut.year - 3, cut.year)]
    periods += [(cut.period_key(year), cut.period_label(year)) for year in (cut.year - 1, cut.year)]
    for key, label in periods:
        volumes = {category: 1e9 for category in taxonomy.DISPLAY_CATEGORIES}
        if key == cut.period_key():
            volumes.update(Financeiro=2e9, Outros=0.5e9)
        for category, volume in volumes.items():
            rows.append({"period_key": key, "period_label": label, "categoria": category,
                         "volume_brl": volume, "share": volume / sum(volumes.values())})
    monkeypatch.setattr(taxonomy, "load_issuance_taxonomy", lambda *_: pd.DataFrame(rows))
    app = AppTest.from_function(_taxonomy_app, args=({"offers_comparison_meta": cut.to_meta()},)).run()
    assert not app.exception and not app.error
    assert f"{cut.period_label()} (R$ bi)" in app.dataframe[0].value.columns
    note = next(element.value for element in app.markdown if "industry-note" in element.value)
    assert cut.period_label() in note and cut.period_label(cut.year - 1) in note
    assert "Financeiro" in note and "R$ 1,0 bi" in note and "Outros" in note
    assert "jun/26" not in note


def _cedente_app(payload: dict[str, object]) -> None:
    from tabs.tab_industry_study import _render_revision_cedente_segments
    _render_revision_cedente_segments(payload)


def test_cedente_selector_shows_august_and_excludes_preliminary_september() -> None:
    payload = {
        "latest_complete": "2026-08",
        "cedente_registry_by_competence": [
            {"competencia": competence, "segmento": "Financeiro", "denominacao": "Fundo"}
            for competence in ("2025-12", "2026-06", "2026-08", "2026-09")
        ],
    }
    app = AppTest.from_function(_cedente_app, args=(payload,)).run()
    assert not app.exception and not app.error
    selector = app.multiselect[0]
    assert selector.options == ["dez/25", "jun/26", "ago/26"]
    assert "set/26" not in app.dataframe[0].value["Competência"].tolist()
    selector.select("ago/26").run()
    assert set(app.dataframe[0].value["Competência"]) == {"ago/26"}


def _providers_app(payload: dict[str, object]) -> None:
    from tabs.tab_industry_study import _render_revision_providers
    _render_revision_providers(payload)


@pytest.mark.parametrize("competence", ["2026-08", "2027-03"])
def test_provider_tables_and_bank_chart_use_actual_published_dates(
    competence: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    import services.industry_revision_export as exports
    cut = ComparisonCut.from_competence(competence)
    dates = [f"{cut.year - 2}-12", f"{cut.year - 1}-12", competence]
    roles = ("administrador", "gestor", "custodiante")
    ranking = [{"competencia": date, "papel": role, "participante": "Prestador",
                "rank_periodo": 1, "pl_brl": (index + 1) * 1e9}
               for index, date in enumerate(dates) for role in roles]
    independent = [{**row, "rank_independente": 1, "rank_geral": 1, "selected_latest_top_n": True}
                   for row in ranking]
    bank_dates = [f"{cut.year - 3}-12", *dates]
    payload = {"schema_version": "fidc_revision_artifact_payload_v11", "latest_complete": competence,
               "provider_historical_ranking": ranking, "provider_independent_ranking": independent,
               "bank_fidc_evolution": [{"competencia": date, "grupo_bancario": "BTG Pactual",
                                        "is_total_5_banks": False, "pl_bruto_brl": 1e9}
                                       for date in reversed(bank_dates)]}
    monkeypatch.setattr(exports, "get_revision_export_status", lambda *_: SimpleNamespace(bundle_valid=False))
    charts = {}
    actual_chart = tab.st.altair_chart
    def capture(chart, **kwargs):
        charts[kwargs["key"]] = chart.to_dict()
        return actual_chart(chart, **kwargs)
    monkeypatch.setattr(tab.st, "altair_chart", capture)
    app = AppTest.from_function(_providers_app, args=(payload,)).run()
    assert not app.exception and not app.error
    expected = ["Participante", *[tab._short_competence_label(date) for date in dates]]
    tables = [item.value for item in app.dataframe if "Participante" in item.value.columns]
    assert len(tables) == 6
    assert all(list(frame.columns) == expected for frame in tables)
    assert all("—" not in frame.iloc[0].tolist() for frame in tables)
    chart = charts["industry-revision-bank-fidc-history"]
    assert chart["encoding"]["x"]["sort"] == [tab._short_competence_label(date) for date in bank_dates]
    if cut.year == 2026:
        assert expected == ["Participante", "Dez/24", "Dez/25", "Ago/26"]
    else:
        assert "Dez/26" in expected and "Dez/24" not in expected
