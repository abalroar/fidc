from xml.etree import ElementTree as ET

import pytest

from scripts.patch_pptx_native_market_charts import _normalize_line_chart_gaps, _normalize_native_data_labels

CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"


def _chart(value: str, *, gap: bool = True, kind: str = "lineChart") -> bytes:
    return f'''<c:chartSpace xmlns:c="{CHART}"><c:chart><c:plotArea><c:{kind}><c:ser><c:val><c:numLit><c:ptCount val="2"/><c:pt idx="0"><c:v>0</c:v></c:pt><c:pt idx="1"><c:v>{value}</c:v></c:pt></c:numLit></c:val></c:ser></c:{kind}></c:plotArea><c:dispBlanksAs val="{'gap' if gap else 'zero'}"/></c:chart></c:chartSpace>'''.encode()


def test_native_gap_omits_nan_without_changing_zero_or_category_count() -> None:
    root = ET.fromstring(_normalize_line_chart_gaps(_chart("NaN")))
    cache = root.find(f".//{{{CHART}}}numLit")
    assert cache.find(f"{{{CHART}}}ptCount").attrib["val"] == "2"
    points = cache.findall(f"{{{CHART}}}pt")
    assert [point.attrib["idx"] for point in points] == ["0"]
    assert points[0].findtext(f"{{{CHART}}}v") == "0"


@pytest.mark.parametrize("value,gap,kind", [("NaN", False, "lineChart"), ("NaN", True, "barChart"), ("Infinity", True, "lineChart")])
def test_unexplained_nonfinite_chart_value_is_rejected(value, gap, kind) -> None:
    with pytest.raises(RuntimeError, match="não finito"):
        _normalize_line_chart_gaps(_chart(value, gap=gap, kind=kind))


def test_value_only_labels_are_explicit_and_preserve_hidden_points_and_format() -> None:
    original = f'''<c:chartSpace xmlns:c="{CHART}"><c:chart><c:plotArea><c:barChart><c:ser><c:dLbls><c:dLbl><c:idx val="0"/><c:numFmt formatCode="0.0%" sourceLinked="0"/><c:showVal val="0"/></c:dLbl><c:dLbl><c:idx val="1"/><c:showVal val="1"/></c:dLbl><c:showVal val="1"/></c:dLbls></c:ser></c:barChart></c:plotArea></c:chart></c:chartSpace>'''.encode()
    patched = _normalize_native_data_labels(original)
    assert _normalize_native_data_labels(patched) == patched
    root = ET.fromstring(patched)
    scopes = [root.find(f".//{{{CHART}}}dLbls"), *root.findall(f".//{{{CHART}}}dLbl")]
    assert [scope.find(f"{{{CHART}}}showVal").attrib["val"] for scope in scopes] == ["1", "0", "1"]
    for scope in scopes:
        for flag in ("showLegendKey", "showCatName", "showSerName", "showPercent", "showBubbleSize"):
            assert scope.find(f"{{{CHART}}}{flag}").attrib["val"] == "0"
    assert root.find(f".//{{{CHART}}}numFmt").attrib["formatCode"] == "0.0%"
