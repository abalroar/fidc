from __future__ import annotations

import json
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

    assert len(slides) == 23
    assert slide_xml.count("<a:tbl>") == 29
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
    assert "Quatro fundos têm uma posição sênior" in slide_xml
    assert "beneficiário final identificado publicamente" in slide_xml
    assert "98,95% QC" in slide_xml
    assert "98,77% QC" in slide_xml
    assert "80,69% QC" in slide_xml
    assert "53.577.135/0001-80" in slide_xml
    assert "50.988.212/0001-05" in slide_xml


def test_monocotista_governance_data_preserves_positions_votes_and_alerts() -> None:
    path = (
        DATA_DIR
        / "generated_revision"
        / "directors_update"
        / "fidc_monocotista_governance_202607.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["competencia"] == "2026-07-31"
    assert len(data["fundos"]) == 20
    assert sum(row["uma_posicao_senior"] for row in data["fundos"]) == 4
    assert sum(row["voto_sub_pct"] > 50 for row in data["fundos"]) == 3
    assert sum(row["alerta_reconciliacao"] for row in data["fundos"]) == 3
    assert data["resumo"]["beneficiario_final_publico"] == 0
    assert "não identifica o beneficiário final" in data["metodologia"]["posicao"]


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
        "governança dos cotistas",
        "beneficiário final",
        "uma posição sênior reportada",
        "Tipo ANBIMA Financeiro",
        "Operação Carbono Oculto",
        "Banco Master",
        "tabelas nativas do Office",
        "Prompt usado para atualizar este artefato",
        "Dados da Indústria > Exportações",
    ):
        assert required in prompt
