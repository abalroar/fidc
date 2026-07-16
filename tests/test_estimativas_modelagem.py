from __future__ import annotations

from contextlib import nullcontext
import inspect

import pandas as pd
import pytest

from tabs import tab_estimativas_modelagem as estimates_tab
from tabs import tab_modelo_fidc as model_tab
from tabs.tab_cloudwalk_financial_cost import _cost_coverage_label


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, estimates_tab.VIEW_CEDENT_COST),
        ("", estimates_tab.VIEW_CEDENT_COST),
        ("obsoleto", estimates_tab.VIEW_CEDENT_COST),
        (estimates_tab.VIEW_CEDENT_COST, estimates_tab.VIEW_CEDENT_COST),
        (estimates_tab.VIEW_MATURITY_ASSUMPTIONS, estimates_tab.VIEW_MATURITY_ASSUMPTIONS),
    ],
)
def test_estimates_view_normalizes_none_and_stale_values(value: object, expected: str) -> None:
    assert estimates_tab.normalize_estimates_modeling_view(value) == expected


@pytest.mark.parametrize(
    ("selected", "expected_call"),
    [
        (estimates_tab.VIEW_CEDENT_COST, "cost"),
        (estimates_tab.VIEW_MATURITY_ASSUMPTIONS, "model"),
    ],
)
def test_combined_page_renders_only_the_selected_engine(
    monkeypatch: pytest.MonkeyPatch,
    selected: str,
    expected_call: str,
) -> None:
    calls: list[tuple[str, bool]] = []
    state: dict[str, object] = {}

    monkeypatch.setattr(estimates_tab.st, "session_state", state)
    monkeypatch.setattr(estimates_tab.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(estimates_tab.st, "container", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(estimates_tab.st, "segmented_control", lambda *args, **kwargs: selected)
    monkeypatch.setattr(estimates_tab, "render_page_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        estimates_tab,
        "render_tab_cloudwalk_financial_cost",
        lambda *, embedded=False: calls.append(("cost", embedded)),
    )
    monkeypatch.setattr(
        estimates_tab,
        "render_tab_modelo_fidc",
        lambda *, embedded=False: calls.append(("model", embedded)),
    )

    estimates_tab.render_tab_estimativas_modelagem()

    assert calls == [(expected_call, True)]


def test_cost_coverage_label_counts_funds_and_series() -> None:
    frame = pd.DataFrame(
        {
            "fund_name": ["FIDC A", "FIDC A", "FIDC B"],
            "classe": ["Sênior", "Subordinada", "Sênior"],
        }
    )

    assert _cost_coverage_label(frame) == "2 FIDCs · 3 séries mapeadas"
    assert _cost_coverage_label(pd.DataFrame()) == "Sem séries mapeadas"


def test_model_pptx_uses_python_fallback_without_pptxgen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_tab, "_build_model_dashboard_pptx_bytes_pptxgen", lambda **kwargs: None)
    monkeypatch.setattr(model_tab, "_build_model_dashboard_pptx_bytes_python", lambda **kwargs: b"python-fallback")

    result = model_tab._build_model_dashboard_pptx_bytes(
        kpi_cards=[],
        revolvency_cards=[],
        premissas_summary_df=pd.DataFrame(),
        timeline_frame=pd.DataFrame(),
        balance_chart_df=pd.DataFrame(),
        loss_chart_df=pd.DataFrame(),
        protection_chart_df=pd.DataFrame(),
    )

    assert result == b"python-fallback"


def test_embedded_model_header_avoids_duplicate_page_title(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_tab.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        model_tab,
        "render_page_header",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("título duplicado")),
    )

    model_tab._render_model_header(embedded=True)


def test_model_keeps_detailed_assumptions_collapsed_by_default() -> None:
    source = inspect.getsource(model_tab.render_tab_modelo_fidc)

    assert 'st.expander("Crédito e provisão", expanded=False)' in source
    assert 'st.expander("Premissas utilizadas", expanded=False)' in source
    assert 'st.expander("Premissas avançadas de prazo, revolvência e waterfall", expanded=False)' in source


def test_model_text_inputs_do_not_repeat_defaults_over_session_state(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    state: dict[str, object] = {}

    monkeypatch.setattr(model_tab.st, "session_state", state)
    monkeypatch.setattr(
        model_tab.st,
        "text_input",
        lambda _label, **kwargs: calls.append(kwargs) or str(kwargs.get("value", state.get(kwargs["key"], ""))),
    )

    model_tab._text_percent_input("Taxa", default=12.5, key="modelo_teste", decimals=1)
    state["modelo_teste"] = "13,0%"
    model_tab._text_percent_input("Taxa", default=12.5, key="modelo_teste", decimals=1)

    assert calls[0]["value"] == "12,5%"
    assert "value" not in calls[1]
    assert model_tab._session_widget_index("ausente", 2) == 2
    assert model_tab._session_widget_index("modelo_teste", 2) is None
