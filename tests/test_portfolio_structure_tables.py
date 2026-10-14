from __future__ import annotations

from html.parser import HTMLParser

import pandas as pd
import pytest

from services.identifier_utils import format_cnpj
from services.monitoring_metrics import MonitoringTables
from tabs.tab_fidc_monitoring import _COCKPIT_METRICS, _render_cockpit_table_html


class _TableContent(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._cells: list[str] = []
        self._cell: list[str] | None = None
        self.identities: list[str] = []
        self._identity: list[str] | None = None
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._cells = []
        elif tag == "td":
            self._cell = []
        elif tag == "span":
            self._identity = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._cell is not None:
            self._cells.append("".join(self._cell))
            self._cell = None
        elif tag == "tr" and self._cells:
            self.rows.append(self._cells)
        elif tag == "span" and self._identity is not None:
            self.identities.append("".join(self._identity))
            self._identity = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)
        if self._identity is not None:
            self._identity.append(data)


def _outputs(count: int) -> list[dict]:
    result = []
    for index in range(count):
        rows = []
        for metric in _COCKPIT_METRICS:
            base = 1_250_000.0 if metric.unit == "R$ bruto" else 1.25
            value = base if index % 3 == 0 else (0.0 if index % 3 == 1 else None)
            rows.append({"indicador": metric.indicator, "03/2026": value})
        result.append({
            "display_name": (
                f'FUNDO {index + 1} & CLASSE <A> "PRINCIPAL" DE INVESTIMENTO EM DIREITOS '
                "CREDITÓRIOS SEGMENTO MEIOS DE PAGAMENTO DE RESPONSABILIDADE LIMITADA"
            ),
            "cnpj": f"{index + 1:014d}",
            "competencias": ["03/2026"],
            "tables": MonitoringTables(
                raw_variables_df=pd.DataFrame(), indicators_df=pd.DataFrame(rows),
                aging_df=pd.DataFrame(), audit_df=pd.DataFrame(),
            ),
        })
    return result


@pytest.mark.parametrize("count", [3, 11, 101, 150])
def test_compact_comparison_preserves_values_and_exact_fund_identity(count: int) -> None:
    outputs = _outputs(count)
    original = [item["tables"].indicators_df.copy(deep=True) for item in outputs]
    legacy_html = _render_cockpit_table_html(outputs, "03/2026")
    refined_html = _render_cockpit_table_html(outputs, "03/2026", compact_identity=True)
    legacy = _TableContent(legacy_html)
    refined = _TableContent(refined_html)

    assert refined.rows == legacy.rows
    assert len(refined.rows) == len(_COCKPIT_METRICS)
    assert all(len(row) == count + 2 for row in refined.rows)
    assert refined.rows[0][2:5] == ["R$ 1,2 mm", "R$ 0", "-"]
    assert refined.identities == [
        item["display_name"]
        for _section in dict.fromkeys(metric.section for metric in _COCKPIT_METRICS)
        for item in outputs
    ]
    assert "<A>" not in refined_html
    assert "&lt;A&gt;" in refined_html
    assert "tabindex='0' role='region'" in refined_html
    for item, before in zip(outputs, original, strict=True):
        assert f"<small>{format_cnpj(item['cnpj'])}</small>" in refined_html
        pd.testing.assert_frame_equal(item["tables"].indicators_df, before)
