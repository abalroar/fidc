from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from services.industry_case_studies_export import (
    CASE_STUDIES_PPTX_NAME,
    build_case_studies_deck_bytes,
    load_case_studies_prompt,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "industry_study"


def test_case_studies_materialized_export_is_native_and_editable() -> None:
    payload = build_case_studies_deck_bytes(DATA_DIR)
    assert payload.startswith(b"PK")

    path = DATA_DIR / "generated_revision" / CASE_STUDIES_PPTX_NAME
    with ZipFile(path) as package:
        slides = [
            name
            for name in package.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        ]
        slide_xml = "".join(
            package.read(name).decode("utf-8", errors="ignore") for name in slides
        )

    assert len(slides) == 22
    assert slide_xml.count("<a:tbl>") == 27
    assert "Itau Display" in slide_xml
    assert "Itau Display Black" in slide_xml
    assert "Itau Display X-Bold" in slide_xml
    assert "Estudos de Caso" in slide_xml
    assert "uma única conta sênior reportada" in slide_xml
    assert "R$ 323,9 bi" in slide_xml
    assert "Operação Carbono Oculto" in slide_xml
    assert "Credcesta" in slide_xml
    assert "SAV Nexoos" in slide_xml
    assert "38.284.301/0001-67" in slide_xml
    assert "FIDC Light" in slide_xml
    assert "29.665.468/0001-87" in slide_xml
    assert "99,70353%" in slide_xml


def test_case_studies_prompt_covers_research_design_and_publication() -> None:
    prompt = load_case_studies_prompt(DATA_DIR)

    for required in (
        "Blue II/Azul",
        "MCPO/Maqcampo",
        "Lavoro Agro FIDC I",
        "Vinci Antecipe Plus FIDC",
        "SAV Nexoos",
        "FIDC Light",
        "Carteira 101",
        "Tipo ANBIMA Financeiro",
        "Operação Carbono Oculto",
        "Banco Master",
        "tabelas nativas do Office",
        "Prompt usado para atualizar este artefato",
        "Dados da Indústria > Exportações",
    ):
        assert required in prompt
