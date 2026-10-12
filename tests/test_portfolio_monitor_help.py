from contextlib import contextmanager
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from tabs import tab_dashboard_meli as credit


class _Help(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, text):
        self.text.append(text)


@pytest.fixture
def ui(monkeypatch):
    scope = []
    captions = []
    warnings = []
    mocks = {name: Mock() for name in ("markdown", "dataframe")}
    for name, mock in mocks.items():
        monkeypatch.setattr(credit.st, name, mock)
    monkeypatch.setattr(credit.st, "caption", lambda text: captions.append((tuple(scope), text)))
    monkeypatch.setattr(credit.st, "warning", lambda text: warnings.append((tuple(scope), text)))

    @contextmanager
    def expander(label, **kwargs):
        scope.append(label)
        try:
            yield
        finally:
            scope.pop()

    monkeypatch.setattr(credit.st, "expander", expander)
    return SimpleNamespace(**mocks, captions=captions, warnings=warnings)


def _return_inputs(monkeypatch, *, cdi_error=None, missing=()):
    frame = pd.DataFrame({"Série": ["Sênior 1"], "Mês": ["0,00%"], "YTD": ["N/D"]})
    frame.attrs.update(cdi_source="B3/Cetip — fonte identificada", cdi_missing_competencias=missing)
    summary = pd.DataFrame({
        "class_label": ["Sênior 1"], "trailing_12m_status": ["incompleto"],
        "trailing_12m_competencias_ausentes": ["02/2026"],
        "ytd_status": ["incompleto"], "ytd_competencias_ausentes": ["02/2026"],
    })
    rates = (object(),)
    resolution = SimpleNamespace(spreads_by_class_key={"senior:1": 0.04}, diagnostics_df=pd.DataFrame())
    cdi = Mock(return_value=(rates, cdi_error))
    benchmark = Mock(return_value=resolution)
    builder = Mock(return_value=frame)
    monkeypatch.setattr(credit, "_resolve_fund_return_cdi_rates", cdi)
    monkeypatch.setattr(credit, "_resolve_fund_return_benchmark", benchmark)
    monkeypatch.setattr(credit, "_build_fund_return_table", builder)
    outputs = SimpleNamespace(fund_return_summary={"123": summary})
    return SimpleNamespace(frame=frame, summary=summary, rates=rates, resolution=resolution,
                           cdi=cdi, benchmark=benchmark, builder=builder, outputs=outputs)


def test_native_help_preserves_notes_and_safe_identification():
    notes = ["Denominador: carteira bruta ex-360", "Fonte <CVM> & Fundos.NET"]
    html = credit._portfolio_chart_info_html("NPL <30> 'A'", notes)
    parsed = _Help(html)
    assert any(tag == "details" for tag, _attrs in parsed.tags)
    summary = next(attrs for tag, attrs in parsed.tags if tag == "summary")
    assert summary["aria-label"] == "Metodologia de NPL <30> 'A'"
    assert notes[0] in parsed.text and notes[1] in parsed.text
    assert "<CVM>" not in html and "&lt;CVM&gt;" in html
    assert not any(tag == "script" for tag, _attrs in parsed.tags)
    assert "onclick" not in html and "onkeydown" not in html


def test_chart_heading_default_is_exactly_the_existing_markup(ui):
    notes = ["Janela de 12 meses", "% dos DCs"]
    credit._chart_title("NPL & crédito", notes)
    expected = (
        "<div class='meli-chart-heading'><div class='meli-chart-title'>NPL &amp; crédito</div>"
        + credit._chart_info_html(notes) + "</div>"
    )
    assert ui.markdown.call_args.args[0] == expected


def test_interactive_heading_uses_only_scoped_css_and_native_disclosure(ui):
    credit._chart_title("Roll rates", ("Proxy M-3", "Fonte CVM"), interactive_help=True)
    html = ui.markdown.call_args.args[0]
    assert "<details class='portfolio-monitor-help'>" in html
    assert "<summary aria-label='Metodologia de Roll rates'>" in html
    assert "min-width:44px;min-height:44px" in html
    assert ".portfolio-chart-heading .portfolio-monitor-help summary:focus-visible" in html
    assert "<style>\n.portfolio-chart-heading" in html
    assert "<p>Proxy M-3</p><p>Fonte CVM</p>" in html
    assert "<span class='meli-info-dot'" not in html


def test_empty_help_does_not_create_an_empty_disclosure(ui):
    assert credit._portfolio_chart_info_html("NPL", []) == ""
    credit._chart_title("NPL", None, interactive_help=True)
    html = ui.markdown.call_args.args[0]
    assert "<details" not in html and "<style" not in html


@pytest.mark.parametrize("compact", [False, True])
def test_return_mode_preserves_producer_inputs_table_values_and_series_gaps(ui, monkeypatch, compact):
    inputs = _return_inputs(monkeypatch)
    original = inputs.frame.copy(deep=True)
    original_summary = inputs.summary.copy(deep=True)
    credit._render_fund_return_table(outputs=inputs.outputs, cnpj="123", compact=compact)

    inputs.cdi.assert_called_once_with(outputs=inputs.outputs, cnpj="123")
    inputs.benchmark.assert_called_once_with(outputs=inputs.outputs, cnpj="123")
    inputs.builder.assert_called_once_with(
        outputs=inputs.outputs, cnpj="123", monthly_cdi_rates=inputs.rates,
        benchmark_spreads=inputs.resolution.spreads_by_class_key,
    )
    displayed = ui.dataframe.call_args_list[0].args[0]
    pd.testing.assert_frame_equal(displayed, original)
    pd.testing.assert_frame_equal(inputs.frame, original)
    pd.testing.assert_frame_equal(inputs.summary, original_summary)
    visible_notes = [text for scope, text in ui.captions if not scope]
    assert any("Acumulado de 12 meses indisponível" in text and "02/2026" in text for text in visible_notes)
    assert any("YTD indisponível" in text and "02/2026" in text for text in visible_notes)


def test_compact_return_metadata_moves_into_help_without_repeated_visible_captions(ui, monkeypatch):
    inputs = _return_inputs(monkeypatch)
    credit._render_fund_return_table(outputs=inputs.outputs, cnpj="123", compact=True)
    html = ui.markdown.call_args.args[0]
    assert "Fonte do CDI: B3/Cetip — fonte identificada" in html
    assert credit.CVM_RETURN_REINVESTMENT_NOTE in "".join(_Help(html).text)
    assert "Últimos 12 meses-calendário" in html
    assert all("Fonte do CDI:" not in text for _scope, text in ui.captions)
    assert all(credit.CVM_RETURN_REINVESTMENT_NOTE not in text for _scope, text in ui.captions)


def test_default_return_metadata_remains_visible_with_original_caption(ui, monkeypatch):
    inputs = _return_inputs(monkeypatch)
    credit._render_fund_return_table(outputs=inputs.outputs, cnpj="123")
    visible = [text for scope, text in ui.captions if not scope]
    assert any(text.startswith("Fonte do CDI: B3/Cetip — fonte identificada") for text in visible)
    assert r"\* " + credit.CVM_RETURN_REINVESTMENT_NOTE in visible
    assert "portfolio-monitor-help" not in ui.markdown.call_args.args[0]


@pytest.mark.parametrize(
    ("error", "missing", "expected"),
    [("Consulta falhou", (), "consulta à B3/Cetip falhou"),
     (None, ("02/2026",), "base B3/Cetip está ausente ou incompleta em 02/2026")],
)
def test_compact_return_cdi_warnings_stay_visible(ui, monkeypatch, error, missing, expected):
    inputs = _return_inputs(monkeypatch, cdi_error=error, missing=missing)
    credit._render_fund_return_table(outputs=inputs.outputs, cnpj="123", compact=True)
    assert any(not scope and expected in text for scope, text in ui.warnings)


def _diagnostics():
    return pd.DataFrame({
        "class_label": ["Sênior 1", "Sênior 2"], "spread_aa": [0.04, None],
        "status": ["resolved", "ambiguous_spread"], "matched_class": ["Emissão 1", "N/D"],
        "remuneration": ["CDI + 4%", "CDI + 4% ou 5%"], "source": ["Doc 1", "Doc 2"],
    })


def test_compact_benchmark_keeps_unresolved_series_visible_and_all_documentary_details(ui):
    diagnostics = _diagnostics()
    original = diagnostics.copy(deep=True)
    credit._render_fund_return_benchmark_diagnostics(SimpleNamespace(diagnostics_df=diagnostics), compact=True)
    visible = [text for scope, text in ui.captions if not scope]
    assert visible == ["Benchmark documental: 1/2 séries vinculadas. 1 sem vínculo válido (N/D)."]
    assert any(scope == ("Memória do benchmark de emissão",) and "ambiguidade permanecem N/D" in text for scope, text in ui.captions)
    displayed = ui.dataframe.call_args.args[0]
    assert displayed["Fonte"].tolist() == ["Doc 1", "Doc 2"]
    assert displayed["Situação"].tolist() == ["Aplicado", "Mais de um spread documental"]
    pd.testing.assert_frame_equal(diagnostics, original)


def test_default_benchmark_retains_current_visible_explanation(ui):
    credit._render_fund_return_benchmark_diagnostics(SimpleNamespace(diagnostics_df=_diagnostics()))
    visible = [text for scope, text in ui.captions if not scope]
    assert len(visible) == 1
    assert visible[0].startswith("Benchmark de emissão aplicado com vínculo documental conservador em 1 de 2")
    assert all(not scope for scope, _text in ui.captions)


@pytest.mark.parametrize("interactive", [False, True])
def test_roll_seasonality_forwards_only_the_requested_help_mode(ui, monkeypatch, interactive):
    frame = pd.DataFrame({"metric_id": ["roll_a"]})
    spec = {"metric_id": "roll_a", "title": "Roll A por mês do ano", "note": "Proxy bucket A"}
    monkeypatch.setattr(credit, "available_roll_seasonality_specs", lambda data: [spec])
    monkeypatch.setattr(credit, "default_roll_seasonality_metric_ids", lambda data: ["roll_a"])
    monkeypatch.setattr(credit.st, "multiselect", lambda *args, **kwargs: ["roll_a"])
    monkeypatch.setattr(credit.st, "altair_chart", Mock())
    chart = Mock(return_value="native-chart")
    monkeypatch.setattr(credit, "research_roll_seasonality_chart", chart)
    title = Mock()
    monkeypatch.setattr(credit, "_chart_title", title)
    credit._render_research_roll_charts(frame, key="scope-a", interactive_help=interactive)
    assert title.call_args.kwargs == ({"interactive_help": True} if interactive else {})
    chart.assert_called_once_with(frame, metric_id="roll_a")
