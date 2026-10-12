from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from tabs import tab_fidc_ime as ime


@pytest.fixture
def ui(monkeypatch):
    mocks = {}
    for name in ("markdown", "caption", "info", "html", "altair_chart", "dataframe"):
        mocks[name] = Mock()
        monkeypatch.setattr(ime.st, name, mocks[name])
    monkeypatch.setattr(ime.st, "columns", lambda widths: [nullcontext() for _ in widths])
    monkeypatch.setattr(ime.st, "expander", lambda *args, **kwargs: nullcontext())
    mocks["popover"] = Mock(side_effect=lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ime.st, "popover", mocks["popover"])
    monkeypatch.setattr(ime.st, "radio", lambda *args, **kwargs: "Valores absolutos (R$)")
    return mocks


def _summary(**changes):
    return {
        "pl_total": 100_000_000.0,
        "direitos_creditorios": 0.0,
        "inadimplencia_denominador": 99_000_000.0,
        "subordinacao_pct": 14.36,
        "ativos_totais": 100_100_000.0,
        "inadimplencia_total": 0.0,
        "cobertura_pct": None,
        **changes,
    }


def _credit_history(inad, pdd, coverage, overdue):
    count = len(inad)
    dates = pd.date_range("2026-01-01", periods=count, freq="MS")
    return pd.DataFrame({
        "competencia": dates.strftime("%m/%Y"), "competencia_dt": dates,
        "inadimplencia_pct": inad, "provisao_pct_direitos": pdd,
        "cobertura_pct": coverage, "inadimplencia_total": overdue,
    })


def _credit_dashboard(history):
    return SimpleNamespace(
        default_history_df=history, default_aging_history_df=pd.DataFrame(),
        default_over_history_df=pd.DataFrame(), default_buckets_latest_df=pd.DataFrame(),
    )


def test_compact_snapshot_keeps_zero_and_all_six_indicators_available(ui):
    summary = _summary()
    before = deepcopy(summary)
    ime._render_financial_snapshot_cards(SimpleNamespace(summary=summary), portfolio_mode=True)

    html = ui["markdown"].call_args.args[0]
    assert html.count('class="fidc-snapshot-card"') == 3
    assert "PL total" in html and "DCs totais" in html and "Subordinação reportada" in html
    assert "R$ 0,00" in html  # A reported DC zero cannot become the fallback denominator.
    assert "R$ 99,0 mm" not in html
    assert "14,36%" in html
    support = ui["caption"].call_args.args[0]
    assert "Ativo R$ 100,1 mm" in support
    assert "Vencidos R$ 0,00" in support
    assert "Cobertura não calculável (vencidos zero)" in support
    assert summary == before


@pytest.mark.parametrize(
    ("coverage", "overdue", "expected"),
    [(0.0, 5.0, "0,00%"), (None, 0.0, "não calculável (vencidos zero)"),
     (None, None, "N/D"), (None, 5.0, "N/D"),
     ("N/D", "N/D", "N/D"), (None, -1.0, "não calculável (vencidos não positivos)")],
)
def test_support_coverage_distinguishes_valid_zero_missing_and_denominator(coverage, overdue, expected):
    values = dict(ime._portfolio_snapshot_support_values(_summary(cobertura_pct=coverage, inadimplencia_total=overdue)))
    assert values["Cobertura"] == expected


def test_default_snapshot_retains_six_cards_and_legacy_fallback(ui):
    ime._render_financial_snapshot_cards(SimpleNamespace(summary=_summary()))
    html = ui["markdown"].call_args.args[0]
    assert html.count('class="fidc-snapshot-card"') == 6
    assert "R$ 99,0 mm" in html
    ui["caption"].assert_not_called()
    ui["popover"].assert_not_called()


def test_support_help_is_a_native_popover_and_reuses_canonical_help(ui, monkeypatch):
    from services import portfolio_structure_ui

    helper = Mock(side_effect=lambda label, dashboard: (
        '<details class="dashboard-indicator-help">'
        f'<summary aria-label="Sobre {label}"><span aria-hidden="true">i</span></summary>'
        '<div class="dashboard-indicator-help-body"><p>Fonte canônica</p></div></details>'
    ))
    monkeypatch.setattr(portfolio_structure_ui, "structural_snapshot_help_html", helper)
    dashboard = SimpleNamespace(summary=_summary())
    ime._render_financial_snapshot_cards(
        dashboard, portfolio_mode=True, interactive_help=True, slot_key="fundo123",
    )
    assert ui["popover"].call_args.kwargs["key"] == "portfolio_snapshot_support::fundo123"
    assert ui["popover"].call_args.kwargs["type"] == "tertiary"
    assert [call.args[0] for call in helper.call_args_list] == [
        "PL total", "DCs totais", "Subordinação reportada",
        "Ativo total", "Vencidos", "Cobertura de provisão",
    ]
    html = ui["html"].call_args.args[0]
    assert html.count("Fonte canônica") == 3
    assert "<script" not in html


def test_zero_credit_is_explicit_and_zero_coverage_is_plotted(ui, monkeypatch):
    history = _credit_history([0.0], [0.0], [0.0], [100.0])
    original = history.copy(deep=True)
    monkeypatch.setattr(ime, "_line_history_chart", lambda frame, **kwargs: frame.copy())
    ime._render_credit_risk_section(_credit_dashboard(history), portfolio_mode=True)

    assert any("Inadimplência 0,00% · PDD 0,00%" in call.args[0] for call in ui["caption"].call_args_list)
    assert ui["altair_chart"].call_count == 1
    assert ui["altair_chart"].call_args.args[0]["valor"].tolist() == [0.0]
    pd.testing.assert_frame_equal(history, original)


def test_tiny_nonzero_npl_is_retained_without_threshold(ui, monkeypatch):
    history = _credit_history([0.0005], [0.0], [None], [1.0])
    monkeypatch.setattr(ime, "_grouped_bar_chart", lambda frame, **kwargs: frame.copy())
    ime._render_credit_risk_section(_credit_dashboard(history), portfolio_mode=True)
    assert ui["altair_chart"].call_count == 1
    assert ui["altair_chart"].call_args.args[0]["valor"].tolist() == [0.0005, 0.0]


def test_real_npl_and_pdd_curves_remain_complete(ui, monkeypatch):
    history = _credit_history([8.0, 10.0], [12.0, 15.0], [150.0, 150.0], [8_000.0, 10_000.0])
    original = history.copy(deep=True)
    monkeypatch.setattr(ime, "_grouped_bar_chart", lambda frame, **kwargs: frame.copy())
    monkeypatch.setattr(ime, "_line_history_chart", lambda frame, **kwargs: frame.copy())
    ime._render_credit_risk_section(_credit_dashboard(history), portfolio_mode=True)
    assert ui["altair_chart"].call_count == 2
    assert ui["altair_chart"].call_args_list[0].args[0]["valor"].tolist() == [8.0, 10.0, 12.0, 15.0]
    assert ui["altair_chart"].call_args_list[1].args[0]["valor"].tolist() == [150.0, 150.0]
    pd.testing.assert_frame_equal(history, original)


def test_missing_credit_is_not_described_as_zero(ui):
    history = _credit_history([None], [None], [None], [None])
    ime._render_credit_risk_section(_credit_dashboard(history), portfolio_mode=True)
    notes = " ".join(call.args[0] for call in ui["caption"].call_args_list)
    assert "N/D — inadimplência e PDD sem dados" in notes
    assert "as séries disponíveis são zero" not in notes
    assert "vencidos reportados zero" not in notes
    ui["altair_chart"].assert_not_called()


def test_partial_zero_credit_keeps_missing_observations_explicit():
    history = _credit_history([0.0, None], [None, None], [None, None], [0.0, None])
    assert "Inadimplência 0,00% (1/2 competências com dado) · PDD N/D" in ime._portfolio_credit_zero_note(history)
    assert "vencidos zero em 1/2 competências" in ime._portfolio_coverage_unavailable_note(history)


def test_default_credit_keeps_current_text_and_visibility(ui):
    history = _credit_history([0.0], [0.0], [0.0], [100.0])
    ime._render_credit_risk_section(_credit_dashboard(history))
    notes = [call.args[0] for call in ui["caption"].call_args_list]
    assert "Sem dados de inadimplência ou provisão nos informes do período." in notes
    assert "Cobertura não disponível para o período selecionado." in notes
    ui["altair_chart"].assert_not_called()
    ui["popover"].assert_not_called()


def test_quota_order_and_colors_are_stable_with_missing_macroclasses():
    history = pd.DataFrame({"class_macro_label": ["Subordinada", "Sênior", "Mezzanino"]})
    order, colors = ime._portfolio_quota_series_style(history)
    assert order == ["Sênior", "Mezzanino", "Subordinada"]
    assert colors == ["#6e6e6e", "#ff5a00", "#111111"]
    subset = history[history["class_macro_label"] != "Mezzanino"]
    order_subset, colors_subset = ime._portfolio_quota_series_style(subset)
    assert dict(zip(order_subset, colors_subset)) == {"Sênior": "#6e6e6e", "Subordinada": "#111111"}


def test_quota_presentation_order_does_not_change_values_or_source():
    frame = pd.DataFrame({"serie": ["Subordinada", "Sênior", "Mezzanino"], "valor": [0.0, None, 1_000.0]})
    original = frame.copy(deep=True)
    ordered = ime._portfolio_order_quota_frame(frame)
    pd.testing.assert_frame_equal(ordered.drop(columns="ordem"), original)
    pd.testing.assert_frame_equal(frame, original)
    assert ordered["ordem"].tolist() == [2, 0, 1]


def test_quota_presentation_handles_missing_identification_without_filling_it():
    frame = pd.DataFrame({"serie": [None, "Sênior"], "valor": [None, 1_000.0]})
    ordered = ime._portfolio_order_quota_frame(frame)
    assert pd.isna(ordered.loc[0, "serie"])
    assert pd.isna(ordered.loc[0, "valor"])
    assert pd.isna(ordered.loc[0, "ordem"])


@pytest.mark.parametrize("view", ["Valores absolutos (R$)", "% do total por competência"])
def test_pl_keeps_one_chart_and_uses_supplied_history_for_subordination(ui, monkeypatch, view):
    monkeypatch.setattr(ime.st, "radio", lambda *args, **kwargs: view)
    quota = pd.DataFrame({
        "competencia": ["02/2026"] * 3, "competencia_dt": [pd.Timestamp("2026-02-01")] * 3,
        "class_macro_label": ["Sênior", "Mezzanino", "Subordinada"], "pl": [88.0, 10.0, 2.0],
    })
    dashboard = SimpleNamespace(
        latest_competencia="02/2026", quota_pl_history_df=quota,
        subordination_history_df=pd.DataFrame({"competencia": ["02/2026"], "subordinacao_pct": [12.0]}),
        summary={"subordinacao_pct": 99.0},
    )
    before = quota.copy(deep=True)
    ime._render_structural_risk_section(
        dashboard, portfolio_mode=True, responsive_labels=True, show_return_section=False,
    )
    assert ui["altair_chart"].call_count == 1
    chart = ui["altair_chart"].call_args.args[0].to_dict()
    bars = chart["layer"][0]["encoding"]
    assert bars["x"]["axis"]["labelAngle"] == 0
    assert bars["color"]["scale"]["domain"] == ["Sênior", "Mezzanino", "Subordinada"]
    assert bars["order"]["field"] == "ordem"
    assert all(layer["mark"]["type"] != "text" or "detail" not in layer.get("encoding", {}) for layer in chart["layer"])
    note = ui["caption"].call_args.args[0]
    assert "1 competência" in note and "12,00%" in note and "99,00%" not in note
    pd.testing.assert_frame_equal(quota, before)


@pytest.mark.parametrize(
    ("pl", "expected"),
    [(0.0, "não calculável — PL reportado zero"), (None, "N/D — PL sem dados")],
)
def test_empty_percentage_pl_explains_zero_or_missing(ui, monkeypatch, pl, expected):
    monkeypatch.setattr(ime.st, "radio", lambda *args, **kwargs: "% do total por competência")
    quota = pd.DataFrame({
        "competencia": ["02/2026"], "competencia_dt": [pd.Timestamp("2026-02-01")],
        "class_macro_label": ["Sênior"], "pl": [pl],
    })
    dashboard = SimpleNamespace(
        latest_competencia="02/2026", quota_pl_history_df=quota,
        subordination_history_df=pd.DataFrame({"competencia": ["02/2026"], "subordinacao_pct": [None]}),
    )
    ime._render_structural_risk_section(dashboard, portfolio_mode=True, show_return_section=False)
    assert any(expected in call.args[0] for call in ui["caption"].call_args_list)
    ui["altair_chart"].assert_not_called()
