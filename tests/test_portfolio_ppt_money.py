import pytest

from services.somatorio_fidcs_ppt_export import _fmt_money


@pytest.mark.parametrize("value", [0, 1, -1, 1_000, 1_000_000, 1_000_000_000])
def test_currency_label_has_exactly_one_currency_symbol(value):
    assert _fmt_money(value).count("R$") == 1


def test_missing_money_is_not_zero():
    assert _fmt_money(None) == "N/D"
    assert _fmt_money(0) == "R$ 0,0"
