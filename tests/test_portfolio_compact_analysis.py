from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from services.document_curation_comparison import DocumentComparisonPage
from tabs import tab_deep_dive as documents
from tabs import tab_dashboard_meli as credit


def test_single_fund_documentary_rows_keep_zero_and_complete_conditions():
    schedule = "15/12/2027: 16,67%; 15/05/2028: 100,00%"
    original = pd.DataFrame({
        "Critério": ["Spread", "Amortização", "Reserva", "Rating"],
        "Nome legal extenso": [0, schedule, None, "-"],
    })
    frozen = original.copy(deep=True)
    shown, groups, missing = documents._portfolio_document_frame(
        original, funds=({"name": "Nome legal extenso", "cnpj": "63615161000100"},),
    )
    assert list(shown.columns) == ["Critério", "Informação"]
    assert shown["Critério"].tolist() == ["Spread", "Amortização"]
    assert shown["Informação"].tolist() == ["0", schedule]
    assert missing == ("Reserva", "Rating") and groups == ()
    pd.testing.assert_frame_equal(original, frozen)


def test_multiple_funds_keep_every_criterion_and_missing_identity():
    original = pd.DataFrame({"Critério": ["Spread", "Reserva"], "A": ["0%", None], "B": ["2%", "-"]})
    frozen = original.copy(deep=True)
    shown, groups, missing = documents._portfolio_document_frame(
        original, funds=({"short_name": "A", "name": "Fundo A", "cnpj": "11111111000111"},
                         {"short_name": "B", "name": "Fundo B", "cnpj": "22222222000122"}),
    )
    assert shown["Critério"].tolist() == ["Spread", "Reserva"]
    assert shown["A"].tolist() == ["0%", "N/D"]
    assert shown["B"].tolist() == ["2%", "N/D"]
    assert missing == () and len(groups) == 2
    html = documents._comparison_table_html("Proteções", shown, 1, portfolio_mode=True)
    assert "<td>0%</td>" in html and html.count("<td>N/D</td>") == 2
    assert "Reserva" in html and "<td>-</td>" not in html
    pd.testing.assert_frame_equal(original, frozen)


def test_documentary_date_sources_missing_fields_and_tools_keep_their_scope(monkeypatch):
    scopes = []; markups = []; captions = []; calls = []
    @contextmanager
    def expander(label, **kwargs):
        scopes.append(label)
        try:
            yield
        finally:
            scopes.pop()
    monkeypatch.setattr(documents.st, "expander", expander)
    monkeypatch.setattr(documents.st, "markdown", lambda text, **kwargs: markups.append((tuple(scopes), text)))
    monkeypatch.setattr(documents.st, "caption", lambda text: captions.append((tuple(scopes), text)))
    monkeypatch.setattr(documents, "_render_document_export", lambda *args, **kwargs: calls.append((tuple(scopes), "export", args, kwargs)))
    monkeypatch.setattr(documents, "_render_update_prompt", lambda **kwargs: calls.append((tuple(scopes), "prompt", (), kwargs)))
    page = DocumentComparisonPage("Proteções", pd.DataFrame({"Critério": ["Taxa", "Reserva"], "Fundo A": ["0%", "-"]}),
                                  notes=("Cobertura documental parcial.",), sources=("CVM ID 101, cláusula 8, p. 4",))
    manifest = SimpleNamespace(generated_at="2026-10-07T10:00:00-03:00", deep_dive_id="docs", warnings=("Ressalva integral.",),
                               funds=({"name": "Fundo A", "cnpj": "63615161000100"},))
    monkeypatch.setattr(documents, "build_document_comparison_pages", lambda _manifest: [page])
    documents._render_document_curation(manifest, portfolio_mode=True)
    body = "\n".join(text for scope, text in markups if not scope)
    assert "### Documentos" in body and body.count("07/10/2026") == 1
    assert "Informação" in body and "0%" in body and "<th scope='col'>Fundo A</th>" not in body
    visible_captions = [text for scope, text in captions if not scope]
    assert visible_captions == ["Fundo A · CNPJ 63.615.161/0001-00", "Sem informação documental para: Reserva."]
    assert any(scope == ("Auditoria documental",) and "CVM ID 101" in text for scope, text in markups)
    assert any(scope == ("Auditoria documental",) and "Ressalva integral." in text for scope, text in markups)
    assert any(scope == ("Auditoria documental",) and text == "Cobertura documental parcial." for scope, text in captions)
    assert [call[1] for call in calls] == ["export", "prompt"]
    assert all(call[0] == ("Ferramentas documentais",) for call in calls)
    assert calls[-1][3]["embedded"] is True
    assert page.frame.iloc[1, 1] == "-"


def test_portfolio_return_table_keeps_zero_nd_benchmark_and_its_own_12m_window(monkeypatch):
    frame = pd.DataFrame({"Série": ["Sênior 1", "Sênior 2"], "abr-25": ["0,00%", "N/D"],
                          "mar-26": ["1,00%", "N/D"], "CDI+ Emissão (% a.a.)": ["N/D", "N/D"]})
    frozen = frame.copy(deep=True)
    summary = pd.DataFrame({"latest_competencia": ["03/2026"], "trailing_12m_status": ["incompleto"],
                            "trailing_12m_competencias_ausentes": ["02/2026"]})
    outputs = SimpleNamespace(fund_return_summary={"123": summary})
    resolution = SimpleNamespace(spreads_by_class_key={}, diagnostics_df=pd.DataFrame())
    rates = (object(),)
    monkeypatch.setattr(credit, "_resolve_fund_return_cdi_rates", lambda **kwargs: (rates, None))
    monkeypatch.setattr(credit, "_resolve_fund_return_benchmark", lambda **kwargs: resolution)
    builder = Mock(return_value=frame);monkeypatch.setattr(credit, "_build_fund_return_table", builder)
    title = Mock();monkeypatch.setattr(credit, "_chart_title", title)
    captions = Mock();monkeypatch.setattr(credit.st, "caption", captions)
    table = Mock();monkeypatch.setattr(credit.st, "dataframe", table)
    credit._render_fund_return_table(outputs=outputs, cnpj="123", portfolio_mode=True)
    builder.assert_called_once_with(outputs=outputs, cnpj="123", monthly_cdi_rates=rates, benchmark_spreads={})
    pd.testing.assert_frame_equal(table.call_args.args[0], frozen)
    pd.testing.assert_frame_equal(frame, frozen)
    assert title.call_args.args[0] == "Rentabilidade" and title.call_args.kwargs["interactive_help"] is True
    assert any("12 meses · abr/25–mar/26" in call.args[0] for call in captions.call_args_list)
    assert any("Acumulado de 12 meses indisponível" in call.args[0] and "02/2026" in call.args[0] for call in captions.call_args_list)


def test_portfolio_roll_selection_keeps_key_bucket_and_original_input(monkeypatch):
    frame = pd.DataFrame({"metric_id": ["roll_a", "roll_b"], "numerator": [0, None], "denominator": [12, 25]})
    specs = [{"metric_id": key, "title": name + " por mês do ano", "note": "Fonte e proxy " + key}
             for key, name in (("roll_a", "Roll A"), ("roll_b", "Roll B"))]
    monkeypatch.setattr(credit, "available_roll_seasonality_specs", lambda _frame: specs)
    monkeypatch.setattr(credit, "default_roll_seasonality_metric_ids", lambda _specs: ["roll_a"])
    selector = Mock(return_value=["roll_b"]);monkeypatch.setattr(credit.st, "multiselect", selector)
    chart = Mock(return_value="chart");monkeypatch.setattr(credit, "research_roll_seasonality_chart", chart)
    monkeypatch.setattr(credit.st, "altair_chart", Mock())
    titles = Mock();monkeypatch.setattr(credit, "_chart_title", titles)
    credit._render_research_roll_charts(frame, key="portfolio::fund::123", portfolio_mode=True)
    assert selector.call_args.kwargs["key"] == "portfolio::fund::123"
    assert selector.call_args.kwargs["label_visibility"] == "collapsed"
    chart.assert_called_once_with(frame, metric_id="roll_b", portfolio_mode=True)
    assert [call.args[0] for call in titles.call_args_list] == ["Sazonalidade", "Roll B"]
    assert any("Fonte e proxy roll_b" in str(call.args) for call in titles.call_args_list)


def test_embedded_methodology_preserves_tables_and_has_no_nested_expander(monkeypatch):
    axis = pd.DataFrame({"Eixo": ["%"]});method = pd.DataFrame({"Fórmula": ["numerador / denominador"]})
    research = SimpleNamespace(methodology=pd.DataFrame({"Fonte": ["CVM"]}))
    monkeypatch.setattr(credit, "build_meli_chart_axis_table", lambda: axis)
    monkeypatch.setattr(credit, "build_meli_methodology_table", lambda: method)
    monkeypatch.setattr(credit.st, "markdown", Mock())
    tables = Mock();monkeypatch.setattr(credit.st, "dataframe", tables)
    expander = Mock(return_value=nullcontext());monkeypatch.setattr(credit.st, "expander", expander)
    credit._render_methodology(research, embedded=True)
    expander.assert_not_called()
    for actual, expected in zip(tables.call_args_list, (axis, method, research.methodology), strict=True):
        pd.testing.assert_frame_equal(actual.args[0], expected)
    credit._render_methodology()
    expander.assert_called_once_with("Metodologia, fórmulas e fontes dos indicadores", expanded=False)
