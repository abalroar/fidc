from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser

import pandas as pd
import pytest

from services.dashboard_ui import analytical_components_css
from services.mercado_livre_dashboard import _wide_metric_specs
from tabs.tab_mercado_livre import _portfolio_wide_value, _render_wide_table_html


class _FinancialTable(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.values: list[tuple[str, str, str]] = []
        self.headers: list[dict[str, str | None]] = []
        self.text: list[str] = []
        self.data_rows = 0
        self.regions = 0
        self.native_help = 0
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "td" and "data-metric" in attrs:
            self.values.append((attrs["data-metric"], attrs["data-period"], attrs["data-original"]))
        if tag == "th":
            self.headers.append(attrs)
        if tag == "tr" and "class" in attrs:
            self.data_rows += 1
        if attrs.get("role") == "region":
            assert attrs.get("tabindex") == "0"
            self.regions += 1
        if tag == "details" and attrs.get("class") == "financial-metric-help":
            self.native_help += 1

    def handle_data(self, value):
        self.text.append(value)


def _fixture():
    periods = ["jan/26", "fev/26", "mar/26"]
    records = []
    for index, spec in enumerate(_wide_metric_specs()):
        records.append({
            "Bloco": spec["block"], "Métrica": spec["metric"],
            "Memória / fórmula": spec["formula"],
            periods[0]: "N/D", periods[1]: None,
            periods[2]: {"money": "R$ mm 0,01", "percent": "0,04%", "text": "Fonte <A> & classe", "bool": "Não", "count": "0"}[spec["unit"]],
        })
    return pd.DataFrame(records), periods


@pytest.mark.parametrize("mode", ["portfolio_mode", "compact"])
def test_every_original_field_formula_and_missing_observation_survives_the_new_table(mode):
    source, periods = _fixture()
    before = source.copy(deep=True)
    html = _render_wide_table_html(source, **{mode: True})
    table = _FinancialTable(html)
    expected = Counter(
        (row["Métrica"], period, "N/D" if pd.isna(row[period]) else row[period])
        for _, row in source.iterrows() for period in periods
    )
    assert Counter(table.values) == expected
    for _, row in source.iterrows():
        assert row["Métrica"] in table.text
        assert f'Fórmula: {row["Memória / fórmula"]}' in "".join(table.text)
    assert table.regions == source["Bloco"].nunique()
    assert table.native_help == table.data_rows
    assert table.data_rows == len(source) - 11  # Six NPL pairs and five ex-360 pairs.
    assert not any("formula-col" in str(header) for header in table.headers)
    assert "&lt;A&gt; &amp; classe" in html
    assert ">N/D<" in html and ">0<" in html
    pd.testing.assert_frame_equal(source, before)


def test_pairs_use_two_month_columns_and_keep_unpaired_rows_without_recalculation():
    source = pd.DataFrame([
        {"Bloco": "5. NPL Over acumulado", "Métrica": "NPL Over 90d / Carteira", "Memória / fórmula": "ratio supplied", "jun/26": "0,00%"},
        {"Bloco": "5. NPL Over acumulado", "Métrica": "NPL Over 90d", "Memória / fórmula": "amount supplied", "jun/26": "R$ mm 0,04"},
        {"Bloco": "5. NPL Over acumulado", "Métrica": "NPL Over 180d", "Memória / fórmula": "missing pair", "jun/26": "R$ 0,00"},
        {"Bloco": "6. Cobertura", "Métrica": "PDD / NPL Over 90d", "Memória / fórmula": "coverage supplied", "jun/26": "N/D"},
    ])
    html = _render_wide_table_html(source, portfolio_mode=True)
    table = _FinancialTable(html)
    assert table.data_rows == 3
    assert Counter(table.values) == Counter((row["Métrica"], "jun/26", row["jun/26"]) for _, row in source.iterrows())
    assert '<th scope="colgroup" colspan="2">jun/26</th>' in html
    assert '<th scope="col">R$ mm</th>' in html and '<th scope="col">%</th>' in html
    assert '<td colspan="2" data-metric="NPL Over 180d"' in html
    assert '<th scope="colgroup" colspan="1">jun/26</th>' in html
    assert ">0,00<" in html  # Supplied zero ratio survives even with a nonzero amount.


def test_duplicate_metrics_and_separate_blocks_are_never_collapsed():
    rows = [
        {"Bloco": "A", "Métrica": "NPL Over 1d", "jan/26": "R$ mm 1,0"},
        {"Bloco": "A", "Métrica": "NPL Over 1d", "jan/26": "R$ mm 2,0"},
        {"Bloco": "A", "Métrica": "NPL Over 1d / Carteira", "jan/26": "3,00%"},
        {"Bloco": "B", "Métrica": "NPL Over 1d / Carteira", "jan/26": "4,00%"},
    ]
    table = _FinancialTable(_render_wide_table_html(pd.DataFrame(rows), portfolio_mode=True))
    assert table.data_rows == len(rows)
    assert len(table.values) == len(rows)


def test_all_reconciliation_rows_long_names_and_long_history_remain_available():
    metrics = ["PL FIDC oficial", "PL soma das classes", "Reconciliação PL oficial vs classes", "Reconciliação PL oficial vs classes (%)"]
    periods = pd.date_range("2022-01-01", periods=50, freq="MS")
    labels = [f"{('jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez')[date.month-1]}/{date.year%100:02}" for date in periods]
    records = [dict(Bloco="2. PL FIDC", Métrica=metric, **{label: "N/D" for label in labels}) for metric in metrics]
    records.append(dict(Bloco="", Métrica="Nome longo <A> & identificação " * 8, **{label: "Nome documental longo " * 15 for label in labels}))
    source = pd.DataFrame(records)
    html = _render_wide_table_html(source, portfolio_mode=True)
    table = _FinancialTable(html)
    assert table.data_rows == 5 and len(table.values) == 250
    assert html.count('role="region"') == 2
    assert "Nome longo &lt;A&gt; &amp; identificação" in html
    for metric in metrics:
        assert metric in table.text


@pytest.mark.parametrize(("source", "unit", "expected"), [
    (None, "money", "N/D"), ("N/D", "percent", "N/D"),
    ("R$ 0,00", "money", "0,00"), ("0,00%", "percent", "0,00"),
    ("R$ mm 0,04", "money", "0,04"), ("R$ mm 9,1", "money", "9,1"),
    ("R$ bi 1.200,0", "money", "1.200.000,0"), ("R$ mil 40,0", "money", "0,04"),
    ("R$ 1,00", "money", "<0,01"), ("R$ -1,00", "money", "−<0,01"),
    ("0,04%", "percent", "0,04"), ("178,04%", "percent", "178,04"),
    ("0,0005%", "percent", "<0,01"), ("Livre", "text", "Livre"),
])
def test_presentation_scale_distinguishes_missing_zero_and_small_nonzero(source, unit, expected):
    assert _portfolio_wide_value(source, unit) == expected


def test_clean_css_is_scoped_and_keeps_touch_focus_and_contained_help():
    for scope in ("portfolio_analysis", "portfolio_structure_pilot"):
        css = analytical_components_css(scope)
        assert f".st-key-{scope}" in css
        assert "font-size: 1.8rem" in css and "font-variant-numeric: tabular-nums" in css
        assert "text-transform: none" in css and "box-shadow: none" in css
        assert "width: 44px; min-height: 44px" in css and ":focus-visible" in css
        assert ".financial-metric-help-body" in css and "overflow-wrap: anywhere" in css
        assert "max-height: 620px; overflow: auto" in css
        assert "overflow-x: clip" not in css  # Overflow belongs to each financial table.
