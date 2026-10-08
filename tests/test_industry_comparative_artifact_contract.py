"""Comparative periods follow the consolidated month across artifact consumers."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from services.industry_comparative_period import ComparisonCut
from scripts.publish_fidc_revision_bundle import (
    RevisionBundlePublishError,
    _validate_offer_comparison_cut,
    _validate_fixed_income_offer_comparison,
    required_data_inputs,
)

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node") or "/Users/matheusjprates/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"


def _cut_payload(competence="2026-08"):
    cut = ComparisonCut.from_competence(competence)
    row = {"period_label": cut.period_id(), "period_start": f"{cut.year}-01-01", "period_end": cut.period_end.isoformat(), "previous_period_end": cut.previous_period_end.isoformat()}
    payload = {
        "latest_complete": cut.competence,
        "offers_as_of": cut.period_end.isoformat(),
        "offers_comparison_meta": cut.to_meta(),
        "closed_offers_ytd_comparable": [{"year": year, "period_start": f"{year}-01-01", "period_end": ComparisonCut(year, cut.month).period_end.isoformat(), "registered_volume_brl": float(cut.month), "closed_offers": cut.month} for year in range(cut.year - 2, cut.year + 1)],
        "closed_offers_monthly": [{"year": year, "month": month, "registered_volume_brl": 1.0, "closed_offers": 1} for year in range(cut.year - 2, cut.year + 1) for month in range(1, cut.month + 1)],
        "offer_ticket_concentration_2026": dict(row),
    }
    for key in ("closed_offer_ticket_distribution", "closed_offer_placement_regime", "closed_offer_top15_summary", "fixed_income_offer_comparison", "market_offer_reconciliation", "offer_target_public_shares", "closed_offer_originators_2026"):
        payload[key] = [dict(row)]
    return payload


@pytest.mark.parametrize("competence", ["2026-01", "2026-08", "2026-12", "2027-02", "2028-02"])
def test_python_ppt_and_html_agree_on_every_comparative_period_field(competence):
    payload = _cut_payload(competence)
    _validate_offer_comparison_cut(payload)
    for script in ("build_fidc_revision_artifacts.mjs", "build_provider_flow_explorer.mjs"):
        source = (ROOT / "scripts" / script).read_text()
        helper = source.split("function comparativePeriod(payload) {", 1)[1].split("\n}\n", 1)[0]
        code = "function comparativePeriod(payload) {" + helper + "\n}\n" + "process.stdout.write(JSON.stringify(comparativePeriod(" + json.dumps(payload) + ")));"
        result = subprocess.run([NODE, "-e", code], check=True, text=True, capture_output=True, timeout=20)
        metadata = json.loads(result.stdout)
        assert {key: metadata[key] for key in payload["offers_comparison_meta"]} == payload["offers_comparison_meta"]
        assert metadata["annual_years"] == list(range(ComparisonCut.from_competence(competence).year - 3, ComparisonCut.from_competence(competence).year))


@pytest.mark.parametrize("mutation", ["stale_cut", "short_comparison", "stale_taxonomy_key", "duplicate_year", "old_current_window", "unequal_prior_window", "future_month", "source_total_drift"])
def test_publisher_rejects_stale_or_noncomparable_windows(mutation):
    payload = _cut_payload()
    if mutation == "stale_cut":
        payload["latest_complete"] = "2026-09"
    elif mutation == "short_comparison":
        payload["closed_offers_ytd_comparable"][0]["period_end"] = "2024-06-30"
    elif mutation == "stale_taxonomy_key":
        payload["offers_comparison_meta"]["current_period_key"] = "jun26"
    elif mutation == "duplicate_year":
        payload["closed_offers_ytd_comparable"].append(deepcopy(payload["closed_offers_ytd_comparable"][0]))
    elif mutation == "old_current_window":
        payload["offer_target_public_shares"][0]["period_end"] = "2026-06-30"
    elif mutation == "future_month":
        payload["closed_offers_monthly"].append({"year": 2026, "month": 9, "registered_volume_brl": 1.0, "closed_offers": 1})
    elif mutation == "source_total_drift":
        payload["closed_offers_monthly"][0]["registered_volume_brl"] = 2.0
    else:
        payload["closed_offer_placement_regime"][0]["previous_period_end"] = "2025-06-30"
    with pytest.raises(RevisionBundlePublishError):
        _validate_offer_comparison_cut(payload)


def test_required_sources_preserve_documentary_june_and_require_current_quantitative_artifacts(tmp_path):
    (tmp_path / "industry_competence_status.csv").write_text("competencia,publication_status\n2026-08,completa\n2026-09,preliminar\n")
    names = set(required_data_inputs(tmp_path))
    assert "industry_taxonomy_audited_decisions_202606.csv" in names
    assert "industry_taxonomy_audit_manifest_202606.json" in names
    assert "industry_taxonomy_impact_summary_202608.csv" in names
    assert "industry_taxonomy_impact_summary_202606.csv" not in names
    assert "cedente_triage/202608/fidc_cedentes_manifest_202608.json" in names
    assert not any(name.startswith("cedente_triage/202606/") for name in names)
    assert not any(name.startswith("cedente_triage/202609/") for name in names)


def _fixed_income_rollover_payload():
    cut = ComparisonCut(2027, 2)
    periods = [f"{year} FY" for year in range(2024, 2027)] + [cut.period_id()]
    rows = []
    for period in periods:
        for view, labels in (("FIDCs vs demais elegíveis", ("FIDCs", "Demais elegíveis")), ("FIDCs vs instrumentos materiais de 2026", ("FIDCs", "Debêntures", "CRI", "Notas comerciais", "CRA"))):
            for label in labels:
                rows.append({"period_label": period, "view": view, "series_label": label, "registered_volume_brl": 3.0 if label == "Demais elegíveis" else 1.0, "universe_registered_volume_brl": 4.0, "yoy_growth": None if period == periods[0] else 0.0})
    return {"offers_as_of": cut.period_end.isoformat(), "fixed_income_offer_comparison": rows, "closed_offers_annual": [{"period_label": period, "registered_volume_brl": 1.0} for period in periods[:3]], "closed_offers_ytd_comparable": [{"year": 2027, "registered_volume_brl": 1.0}]}


def test_fixed_income_guard_rolls_annual_windows_and_keeps_2023_exception_outside_2027():
    payload = _fixed_income_rollover_payload()
    _validate_fixed_income_offer_comparison(payload)
    payload["fixed_income_offer_comparison"][0]["yoy_growth"] = 0.2
    with pytest.raises(RevisionBundlePublishError, match="2024 deve permanecer sem YoY"):
        _validate_fixed_income_offer_comparison(payload)


def test_manifest_preserves_only_signed_durable_source_paths(tmp_path):
    from scripts.publish_fidc_revision_bundle import build_bundle_manifest
    kwargs = dict(payload_bytes=b"{}", payload={"latest_complete": "2026-08"}, analysis_manifest_bytes=b"{}", pptx_bytes=b"p", xlsx_bytes=b"x", input_hashes={"source/registro_fundo_classe.zip": "a" * 64}, renderer={}, generated_at_utc="2026-10-08T18:00:00Z")
    location = tmp_path / "source-snapshot-abcd" / "registro_fundo_classe.zip"
    result = build_bundle_manifest(**kwargs, input_paths={"source/registro_fundo_classe.zip": location})
    assert result["input_paths"] == {"source/registro_fundo_classe.zip": str(location)}
    with pytest.raises(RevisionBundlePublishError, match="não durável"):
        build_bundle_manifest(**kwargs, input_paths={"source/registro_fundo_classe.zip": tmp_path / ".fidc-revision-publish-temporary" / "source.zip"})
    with pytest.raises(RevisionBundlePublishError, match="não assinado"):
        build_bundle_manifest(**kwargs, input_paths={"source/cad_fi_hist.zip": location})


def test_current_taxonomy_impact_rejects_false_zero_and_stale_cut():
    from scripts.publish_fidc_revision_bundle import _validate_current_taxonomy_impacts
    payload = _cut_payload()
    payload.update({
        "taxonomy_audit_impact_summary": [{"competence": "2026-08"}],
        "taxonomy_audit_market_share_impact": [{"competence": "2026-08", "tipo_anbima": "Financeiro", "foco_anbima": "Crédito", "before_denominator_brl": 100.0, "after_denominator_brl": 100.0, "delta_denominator_brl": 0.0, "scope_total_before_brl": 100.0, "scope_total_after_brl": 100.0}],
        "market_share_scope_summary": [{"competencia": "2026-08", "papel": role, "pl_nos_14_focos_brl": 100.0} for role in ("administrador", "gestor", "custodiante")],
        "issuance_taxonomy": [{"period_key": "ago26", "categoria": "Financeiro", "volume_brl": 50.0}],
        "taxonomy_audit_issuance_impact": [{"period_key": "ago26", "categoria": "Financeiro", "after_volume_brl": 50.0}],
    })
    _validate_current_taxonomy_impacts(payload)
    row = payload["taxonomy_audit_market_share_impact"][0]
    row["before_denominator_brl"] = row["after_denominator_brl"] = 0.0
    with pytest.raises(RevisionBundlePublishError, match="sem denominador positivo"):
        _validate_current_taxonomy_impacts(payload)
    row["before_denominator_brl"] = row["after_denominator_brl"] = 100.0
    row["competence"] = "2026-06"
    with pytest.raises(RevisionBundlePublishError, match="competência corrente"):
        _validate_current_taxonomy_impacts(payload)


@pytest.mark.parametrize(("primary_competence", "source_competence"), [("2026-08", "2026-06"), ("2026-08", "2026-08"), ("2026-08", "2026-09"), ("2027-01", "2026-12"), ("2028-01", "2027-12")])
def test_anbima_secondary_cut_is_explicit_and_comparable_when_source_lags(primary_competence, source_competence):
    from scripts.publish_fidc_revision_bundle import _secondary_offer_comparison_cut
    payload = _cut_payload(primary_competence)
    primary = ComparisonCut.from_competence(primary_competence)
    source_cut = ComparisonCut.from_competence(source_competence)
    secondary = min((primary, source_cut), key=lambda cut: cut.period_end)
    payload["anbima_market_offers_manifest"] = {
        "comparison_meta": secondary.to_meta(),
        "cvm_latest_complete_meta": primary.to_meta(),
        "source_reference_competence": source_cut.competence,
        "source_lag_months": max(0, (primary.year - source_cut.year) * 12 + primary.month - source_cut.month),
    }
    assert _secondary_offer_comparison_cut(payload, "anbima_market_offers_manifest") == secondary
    source = (ROOT / "scripts/build_fidc_revision_artifacts.mjs").read_text()
    helper = source.split("function comparativePeriod(payload) {", 1)[1].split("\n}\n", 1)[0]
    secondary_helper = source.split("function secondaryComparativePeriod(payload, manifestKey = \"anbima_market_offers_manifest\") {", 1)[1].split("\n}\n", 1)[0]
    code = "function comparativePeriod(payload) {" + helper + "\n}\nfunction secondaryComparativePeriod(payload, manifestKey = 'anbima_market_offers_manifest') {" + secondary_helper + "\n}\nprocess.stdout.write(JSON.stringify(secondaryComparativePeriod(" + json.dumps(payload) + ")));"
    result = subprocess.run([NODE, "-e", code], check=True, capture_output=True, text=True, timeout=20)
    assert json.loads(result.stdout)["period_label"] == secondary.period_label()
    payload["anbima_market_offers_manifest"]["comparison_meta"] = primary.to_meta()
    if secondary != primary:
        with pytest.raises(RevisionBundlePublishError, match="mesma janela"):
            _secondary_offer_comparison_cut(payload, "anbima_market_offers_manifest")


@pytest.mark.parametrize("competence", ["2026-08", "2027-03"])
def test_provider_and_bank_history_guard_rolls_year_ends_without_relabeling_old_values(competence):
    from scripts.publish_fidc_revision_bundle import _validate_current_history_windows
    cut = ComparisonCut.from_competence(competence)
    payload = _cut_payload(competence)
    for key, count in (("provider_historical_ranking", 2), ("provider_independent_ranking", 2), ("provider_concentration_history", 1), ("bank_fidc_evolution", 3), ("bank_fidc_detail", 3)):
        payload[key] = [{"competencia": f"{year}-12"} for year in range(cut.year - count, cut.year)] + [{"competencia": cut.competence}]
    _validate_current_history_windows(payload)
    source = (ROOT / "scripts/build_fidc_revision_artifacts.mjs").read_text()
    helper = source.split("function historicalFrameCompetences(rows, latest, count) {", 1)[1].split("\n}\n", 1)[0]
    code = "function historicalFrameCompetences(rows, latest, count) {" + helper + "\n}\nprocess.stdout.write(JSON.stringify(historicalFrameCompetences(" + json.dumps(payload["provider_historical_ranking"]) + "," + json.dumps(cut.competence) + ",2)));"
    result = subprocess.run([NODE, "-e", code], check=True, capture_output=True, text=True, timeout=20)
    assert json.loads(result.stdout) == [f"{year}-12" for year in range(cut.year - 2, cut.year)]
    payload["provider_historical_ranking"][0]["competencia"] = f"{cut.year - 3}-12"
    with pytest.raises(RevisionBundlePublishError, match="encerramentos anuais anteriores"):
        _validate_current_history_windows(payload)
