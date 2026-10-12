from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import re
from types import SimpleNamespace
from unittest.mock import patch

from pptx import Presentation

from services.fidc_analytical_slide import (
    FidcSlideData,
    Issuance,
    build_fidc_analytical_pptx_bytes,
)


GENERATED_AT = datetime(2026, 10, 12, 13, 34)


def _presentation(items, *, legal_names=None, generated_at=GENERATED_AT):
    funds = [SimpleNamespace(cnpj=item.cnpj, display_name=(legal_names or {}).get(item.cnpj, item.name)) for item in items]
    with patch("services.fidc_analytical_slide.build_slide_data", return_value=items):
        payload = build_fidc_analytical_pptx_bytes(funds, portfolio_name="Carteira 1T26", generated_at=generated_at)
    return Presentation(BytesIO(payload))


def _text(presentation):
    pieces = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                pieces.append(shape.text)
            if shape.has_table:
                pieces.extend(cell.text for row in shape.table.rows for cell in row.cells)
        if slide.has_notes_slide:
            pieces.append(slide.notes_slide.notes_text_frame.text)
    return "\n".join(pieces)


def test_no_rdb_evidence_cannot_publish_an_unrelated_conclusion_or_static_date():
    item = FidcSlideData(name="Cloudwalk Kick Ass I", cnpj="42085816000105", pl_mm=0)
    presentation = _presentation([item])
    text = _text(presentation)
    assert len(presentation.slides) == 2
    assert "RDB não localizado nos documentos consultados" in text
    assert "não comprova inexistência" in text
    assert "Não localizado" in text
    assert "R$ 0,0 mm" in text
    assert "12/10/2026" in text
    assert "14/08/2026" not in text
    assert "MT FGTS" not in text
    assert "CCB Tudo Serviços" not in text
    assert "Parati" not in text
    assert "não aplicável" not in text.lower()


def test_evidence_is_retained_and_public_notes_keep_primary_citations():
    source = "Fundos.NET ID 211003 | 01/09/2021 | Regulamento | p. 3 | data/raw/42085816000105/documento.pdf | https://fnet.bmfbovespa.com.br/fnet/publico/visualizarDocumento?id=211003"
    item = FidcSlideData(
        name="Fundo", cnpj="42085816000105", rdb_status="Explícito",
        rdb_finding="RDB Parati localizado no regulamento; uso condicionado ao contrato.",
        rdb_source="/Users/analista/projeto/data/raw/42085816000105/documento.pdf · p. 3",
        issuances=[Issuance("09/2021", "Subordinadas", "Subordinada", 5.6, "Residual", "N/D", source)],
    )
    presentation = _presentation([item])
    text = _text(presentation)
    assert "RDB Parati localizado" in text
    assert "Explícito: 1" in text
    assert "Fundos.NET ID 211003" in text
    assert "p. 3" in text
    assert "https://fnet.bmfbovespa.com.br/fnet/publico/visualizarDocumento?id=211003" in text
    assert "data/raw/" not in text
    assert "/Users/" not in text
    assert all(slide.has_notes_slide for slide in presentation.slides)


def test_cloudwalk_size_keeps_slide_count_and_separates_conclusion_from_table():
    items = [FidcSlideData(name=f"FIDC {index}", cnpj=f"{index:014d}") for index in range(11)]
    presentation = _presentation(items)
    assert len(presentation.slides) == 12
    rdb_slide = presentation.slides[0]
    table = next(shape for shape in rdb_slide.shapes if shape.has_table)
    conclusion = next(shape for shape in rdb_slide.shapes if shape.has_text_frame and "RDB não localizado nos documentos consultados" in shape.text)
    assert len(table.table.rows) == 12
    assert table.top + table.height < conclusion.top


def test_path_only_source_keeps_document_identifier_without_internal_directory():
    item = FidcSlideData(
        name="FIDC", cnpj="42085816000105",
        rdb_source="data/raw/42085816000105/211003_review_20261007.pdf · p. 3",
    )
    text = _text(_presentation([item]))
    assert "211003_review_20261007.pdf · p. 3" in text
    assert "data/raw/" not in text


def test_legal_name_stays_in_notes_while_canonical_alias_is_used_in_tables():
    legal_name = "CLOUDWALK A.I. FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA"
    item = FidcSlideData(name=legal_name[:56], cnpj="57609282000146", pl_mm=100)
    original = deepcopy(item)
    presentation = _presentation([item], legal_names={item.cnpj: legal_name})
    table = next(shape.table for shape in presentation.slides[0].shapes if shape.has_table)
    assert table.cell(1, 0).text == "CW A.I."
    assert "CW A.I. | estrutura e emissões" in _text(presentation)
    assert legal_name in presentation.slides[1].notes_slide.notes_text_frame.text
    assert item == original


def test_long_rdb_findings_continue_without_silent_word_truncation():
    finding = " ".join(f"cláusula{i}" for i in range(600))
    item = FidcSlideData(name="FIDC com texto extenso", cnpj="12345678000199", rdb_status="Parcial", rdb_finding=finding)
    presentation = _presentation([item])
    rdb_slides = [slide for slide in presentation.slides if any(shape.has_text_frame and "RDB — leitura documental" in shape.text for shape in slide.shapes)]
    assert len(rdb_slides) > 1
    cells = " ".join(shape.table.cell(row, 2).text for slide in rdb_slides for shape in slide.shapes if shape.has_table for row in range(1, len(shape.table.rows)))
    assert re.sub(r"\s+", " ", cells).strip() == finding
    for slide in rdb_slides:
        table = next(shape for shape in slide.shapes if shape.has_table)
        conclusion = next(shape for shape in slide.shapes if shape.has_text_frame and shape.text.startswith("Resultado por fundo"))
        assert table.top + table.height < conclusion.top
    assert finding in presentation.slides[-1].notes_slide.notes_text_frame.text


def test_long_issuance_rows_remain_native_and_all_records_are_present():
    issuances = [Issuance(
        "10/2025", f"Série completa número {index} de emissão subordinada", "Subordinada", float(index),
        "Remuneração vinculada ao CDI conforme índice contratual, com pagamentos e condições descritos integralmente no documento da emissão.",
        "Amortização contratual", f"Fundos.NET ID {10000 + index} · p. 5",
    ) for index in range(12)]
    item = FidcSlideData(name="FIDC", cnpj="12345678000199", issuances=issuances)
    presentation = _presentation([item])
    emission_tables = [shape.table for slide in presentation.slides for shape in slide.shapes if shape.has_table and shape.table.cell(0, 0).text == "Data"]
    rows = [tuple(cell.text for cell in row.cells) for table in emission_tables for row in list(table.rows)[1:]]
    assert len(emission_tables) > 1
    assert len(rows) == len(issuances)
    assert {re.sub(r"\s+", " ", row[1]) for row in rows} == {item.series for item in issuances}
    assert {re.sub(r"\s+", " ", row[3]) for row in rows} == {item.remuneration for item in issuances}
    for table in emission_tables:
        for row in list(table.rows)[1:]:
            for cell in row.cells:
                assert all(run.font.size.pt == 9 for paragraph in cell.text_frame.paragraphs for run in paragraph.runs)
    for slide in presentation.slides:
        for shape in slide.shapes:
            assert shape.left >= 0 and shape.top >= 0
            assert shape.left + shape.width <= presentation.slide_width
            assert shape.top + shape.height <= presentation.slide_height
            if shape.has_table:
                assert shape.top + shape.height < 6.95 * 914400


def test_generation_date_respects_sao_paulo_and_never_uses_portfolio_name():
    item = FidcSlideData(name="FIDC", cnpj="12345678000199")
    presentation = _presentation([item], generated_at=datetime(2026, 10, 13, 1, tzinfo=timezone.utc))
    text = _text(presentation)
    assert "Geração: 12/10/2026" in text
    assert "Geração: 13/10/2026" not in text
    assert "Carteira: Carteira 1T26" in text
