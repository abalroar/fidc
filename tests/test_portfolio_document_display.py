from io import BytesIO
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.enum.text import PP_ALIGN

from services.deep_dive_models import DeepDiveManifest
from services.deep_dive_ppt_export import build_document_comparison_pptx_bytes
from services.document_curation_comparison import DocumentComparisonPage


def _manifest():
    return DeepDiveManifest.from_dict({
        "title": "Curadoria Carteira Cloudwalk 1T26",
        "generated_at": "2026-10-07T11:08:04-03:00",
        "source": "CVM / Fundos.NET",
        "funds": [{
            "cnpj": "42085816000105", "short_name": "CW Kick Ass I",
            "name": "CLOUDWALK KICK ASS I FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA",
        }],
    }, package_dir=Path("unused"))


def _page():
    return DocumentComparisonPage(
        "Recebíveis e elegibilidade",
        pd.DataFrame({"Critério": ["Devedor", "Taxa", "Quantidade"], "CW Kick Ass I": ["Emissores dos instrumentos de pagamento", None, 0]}, dtype=object),
        notes=("A leitura se limita aos documentos consultados.",),
        sources=("Regulamento ID Fundos.NET 211003 · p. 3 · https://fnet.bmfbovespa.com.br/fnet/publico/visualizarDocumento?id=211003",),
    )


def _presentation(*, portfolio_mode=False, pages=None):
    return Presentation(BytesIO(build_document_comparison_pptx_bytes(_manifest(), pages or [_page()], portfolio_mode=portfolio_mode)))


def _tables(presentation):
    return [shape.table for slide in presentation.slides for shape in slide.shapes if shape.has_table]


def _values(presentation):
    return [[[cell.text for cell in row.cells] for row in table.rows] for table in _tables(presentation)]


def test_portfolio_mode_is_opt_in_and_preserves_native_content_and_slide_count():
    default = _presentation()
    portfolio = _presentation(portfolio_mode=True)
    assert len(default.slides) == len(portfolio.slides) == 1
    assert _values(default) == _values(portfolio)
    assert _tables(portfolio)[0].cell(2, 1).text == "-"
    assert _tables(portfolio)[0].cell(3, 1).text == "0"
    assert _tables(default)[0].cell(1, 1).text_frame.paragraphs[0].alignment == PP_ALIGN.CENTER
    assert _tables(portfolio)[0].cell(1, 1).text_frame.paragraphs[0].alignment == PP_ALIGN.LEFT


def test_portfolio_title_and_footer_are_short_with_complete_identification_in_notes():
    slide = _presentation(portfolio_mode=True).slides[0]
    visible = "\n".join(shape.text for shape in slide.shapes if shape.has_text_frame)
    notes = slide.notes_slide.notes_text_frame.text
    assert "Recebíveis e elegibilidade" in visible
    assert _manifest().title not in visible
    assert "Documentos · Leitura: 07/10/2026 · Fontes nas notas" in visible
    assert _manifest().title in notes
    assert _manifest().funds[0]["name"] in notes
    assert "CNPJ 42085816000105" in notes
    assert _page().sources[0] in notes
    assert _page().notes[0] in notes


def test_default_document_title_footer_and_alignment_remain_available():
    slide = _presentation().slides[0]
    visible = "\n".join(shape.text for shape in slide.shapes if shape.has_text_frame)
    assert f"{_manifest().title} – {_page().title}" in visible
    assert "Leitura documental: 07/10/2026. Fontes e referências nas notas do slide." in visible


def test_portfolio_mode_keeps_pagination_for_long_rows_and_many_funds():
    frame = pd.DataFrame({"Critério": [f"Regra {index}" for index in range(30)]})
    for index in range(7):
        frame[f"Fundo {index}"] = [f"Valor contratual fundo {index}, regra {row}" for row in range(30)]
    page = DocumentComparisonPage("Regras extensas", frame)
    default = _presentation(pages=[page])
    portfolio = _presentation(portfolio_mode=True, pages=[page])
    assert len(default.slides) == len(portfolio.slides)
    assert _values(default) == _values(portfolio)
