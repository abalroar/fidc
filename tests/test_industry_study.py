import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_fidc_industry_study import (  # noqa: E402
    FIC_FIDC_PATTERN,
    _norm_name,
    _strip_digits,
    month_range,
)


def test_month_range_spans_years():
    months = month_range("2013-01", "2014-03")
    assert months[0] == "201301"
    assert months[-1] == "201403"
    assert len(months) == 15


def test_month_range_single_month():
    assert month_range("2026-05", "2026-05") == ["202605"]


def test_strip_digits():
    assert _strip_digits("05.753.599/0001-58") == "05753599000158"
    assert _strip_digits(None) == ""


def test_norm_name_collapses_spaces_and_uppercases():
    assert _norm_name("  BTG  Pactual   Servicos ") == "BTG PACTUAL SERVICOS"


def test_fic_fidc_pattern():
    assert FIC_FIDC_PATTERN.search("XPTO FIC FIDC MULTIMERCADO")
    assert FIC_FIDC_PATTERN.search(
        "FUNDO DE INVESTIMENTO EM COTAS DE FUNDOS DE INVESTIMENTO EM DIREITOS CREDITORIOS ABC"
    )
    assert not FIC_FIDC_PATTERN.search("FUNDO DE INVESTIMENTO EM DIREITOS CREDITORIOS ABC")
