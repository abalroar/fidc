import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_fidc_extended_market_intelligence import (  # noqa: E402
    build_investor_stock_delta,
    clean_named_investor_candidate,
    digits,
    secondary_market_data_request,
    subscriber_bucket,
)
from tabs.tab_industry_study import _fmt_pp  # noqa: E402


def test_digits_preserves_cnpj_across_csv_numeric_representations():
    assert digits("32.402.502/0001-35") == "32402502000135"
    assert digits(32402502000135.0) == "32402502000135"
    assert digits("3.2402502000135e13") == "32402502000135"


def test_percentage_point_label_keeps_portuguese_decimal_and_pp_punctuation():
    assert _fmt_pp(3.045) == "+3,0 p.p."
    assert _fmt_pp(-1.512) == "-1,5 p.p."


def test_build_investor_stock_delta_uses_account_totals_and_share_change(tmp_path: Path):
    pd.DataFrame(
        [
            {"competencia": "2025-05", "tipo_cotista": "Pessoa física", "n_cotistas": 100},
            {"competencia": "2025-05", "tipo_cotista": "Outros fundos", "n_cotistas": 100},
            {"competencia": "2026-05", "tipo_cotista": "Pessoa física", "n_cotistas": 150},
            {"competencia": "2026-05", "tipo_cotista": "Outros fundos", "n_cotistas": 200},
        ]
    ).to_csv(tmp_path / "cotistas_tipo_monthly.csv", index=False)

    detail, family = build_investor_stock_delta(
        tmp_path,
        pd.Period("2026-05", freq="M"),
        pd.Period("2025-05", freq="M"),
    )

    people = detail.loc[detail["tipo_cotista"].eq("Pessoa física")].iloc[0]
    funds = family.loc[family["investor_family"].eq("Fundos de investimento")].iloc[0]
    assert people["accounts_current"] == 150
    assert people["growth"] == 0.5
    assert round(people["delta_share_pp"], 6) == round((150 / 350 - 0.5) * 100, 6)
    assert funds["accounts_current"] == 200
    assert funds["accounts_previous"] == 100


def test_named_investor_candidate_removes_list_marker_and_registration_tail():
    value = clean_named_investor_candidate(
        "E PINAMAR FUNDO DE INVESTIMENTO MULTIMERCADO CREDITO PRIVADO, "
        "INSCRITO NO CNPJ SOB O N"
    )
    assert value == "PINAMAR FUNDO DE INVESTIMENTO MULTIMERCADO CREDITO PRIVADO"


def test_subscriber_histogram_buckets_are_stable():
    assert [subscriber_bucket(value) for value in (0, 1, 2, 5, 6, 50, 100, 500, 501)] == [
        "0",
        "1",
        "2-5",
        "2-5",
        "6-10",
        "11-50",
        "51-100",
        "101-500",
        ">500",
    ]


def test_secondary_market_request_contains_fields_needed_for_speed_and_turnover():
    request = secondary_market_data_request()
    fields = set(request["field"])
    assert {"trade_date", "trade_identifier", "financial_volume_brl", "trade_status"} <= fields
    assert request["minimum_history"].eq("36 months").all()
