from __future__ import annotations

from pathlib import Path

import pytest

from scripts.build_fidc_revision_artifact_payload import (
    _digits,
    _json_value,
    _load_top100_plus2_curation,
)


ROOT = Path(__file__).resolve().parents[1]
CURATION_PATH = ROOT / "data" / "industry_study" / "top100_plus2_2026_curation.csv"


def test_top100_plus2_curation_has_the_two_documented_2026_issuances() -> None:
    frame = _load_top100_plus2_curation(CURATION_PATH).set_index("cnpj")

    assert set(frame.index) == {"44302112000172", "61669748000176"}
    citi = frame.loc["44302112000172"]
    lavoro = frame.loc["61669748000176"]

    assert "BAYER S.A." in citi["cedente_originador"]
    assert "MONSANTO DO BRASIL" in citi["cedente_originador"]
    assert "Citibank" not in citi["cedente_originador"]
    assert "Produtores rurais" in citi["sacado_devedor"]
    assert citi["taxonomia_funcional_n1"] == "Agro / Revenda"
    assert float(citi["minimo_subordinacao_estrutural"]) == pytest.approx(0.15)
    assert "1100035" == citi["documento_regulamento_id"]
    assert "1173013" == citi["documento_emissao_id"]

    assert "LAVORO AGRO HOLDING" in lavoro["cedente_originador"]
    assert "Pessoas físicas" in lavoro["sacado_devedor"]
    assert lavoro["taxonomia_funcional_n1"] == "Agro / Revenda"
    assert float(lavoro["minimo_subordinacao_junior"]) == pytest.approx(0.01)
    assert float(lavoro["minimo_subordinacao_estrutural"]) == pytest.approx(0.25)
    assert "1121937" == lavoro["documento_regulamento_id"]
    assert "1211950" == lavoro["documento_emissao_id"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4,4302112000172E+13", "44302112000172"),
        ("6.1669748000176e13", "61669748000176"),
        (44302112000172, "44302112000172"),
        ("44.302.112/0001-72", "44302112000172"),
    ],
)
def test_payload_cnpj_normalizer_handles_excel_scientific_notation(
    raw: object,
    expected: str,
) -> None:
    assert _digits(raw) == expected


def test_payload_text_sanitizer_blocks_mojibake_and_marks_irrecoverable_text() -> None:
    for corrupt_text in ("Cr√©dito", "M√°quinas", "Adquir√™ncia", "CrÃ©dito"):
        with pytest.raises(ValueError, match="mojibake"):
            _json_value(corrupt_text)

    assert _json_value("Crédito ���� corporativo") == (
        "Crédito [trecho ilegível na extração] corporativo"
    )
