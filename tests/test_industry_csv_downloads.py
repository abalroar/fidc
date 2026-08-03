from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

from tabs.tab_industry_study import _ptbr_csv_bytes


ROOT = Path(__file__).resolve().parents[1]


def test_ptbr_csv_bytes_is_excel_safe_for_accents_and_cnpj() -> None:
    source = pd.DataFrame(
        {
            "CNPJ": [9195235000150, "1.234567000189E+12", "42.462.306/0001-00"],
            "Nome": ["Crédito", "Adquirência", "Itaú"],
            "cnpj_count": [1, 2, 3],
        }
    )

    payload = _ptbr_csv_bytes(source)
    decoded = payload.decode("utf-8-sig")
    loaded = pd.read_csv(BytesIO(payload), sep=";", dtype=str, encoding="utf-8-sig")

    assert payload.startswith(b"\xef\xbb\xbf")
    assert loaded["CNPJ"].tolist() == [
        "09.195.235/0001-50",
        "01.234.567/0001-89",
        "42.462.306/0001-00",
    ]
    assert loaded["Nome"].tolist() == ["Crédito", "Adquirência", "Itaú"]
    assert loaded["cnpj_count"].tolist() == ["1", "2", "3"]
    assert "E+" not in decoded
    assert "Cr√©dito" not in decoded
    assert "CrÃ©dito" not in decoded
    assert source.loc[0, "CNPJ"] == 9195235000150


def test_ptbr_csv_bytes_formats_cnpj_lists_and_keeps_empty_exports() -> None:
    list_payload = _ptbr_csv_bytes(
        pd.DataFrame(
            {
                "CNPJs": ["09195235000150; 01234567000189"],
                "Descrição": ["Crédito corporativo"],
            }
        )
    ).decode("utf-8-sig")
    empty_payload = _ptbr_csv_bytes(pd.DataFrame(columns=["CNPJ", "Nome"]))

    assert "09.195.235/0001-50; 01.234.567/0001-89" in list_payload
    assert empty_payload.startswith(b"\xef\xbb\xbf")
    assert empty_payload.decode("utf-8-sig") == "CNPJ;Nome\n"


def test_industry_downloads_do_not_serialize_user_csv_without_bom() -> None:
    source = (ROOT / "tabs" / "tab_industry_study.py").read_text(encoding="utf-8")

    assert '.to_csv(index=False).encode("utf-8")' not in source
