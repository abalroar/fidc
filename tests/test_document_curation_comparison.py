from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from services.deep_dive_models import DeepDiveTableSpec
from services.document_curation_comparison import CELL_REFERENCES_SUBTITLE, build_document_comparison_pages, comparison_column_chunks
from tabs.tab_deep_dive import _comparison_table_html


def _manifest(tmp_path, specs):
    return SimpleNamespace(
        package_dir=tmp_path,
        tables=tuple(specs),
        funds=({"cnpj": "11111111000111", "name": "FIDC A", "short_name": "FIDC A"},
               {"cnpj": "22222222000122", "name": "FIDC B", "short_name": "FIDC B"}),
    )


def test_reviewed_pages_preserve_zero_missing_and_source(tmp_path: Path):
    pd.DataFrame({"Critério": ["Spread", "Reserva"], "FIDC A": ["0% a.a.", ""], "FIDC B": ["DI + 2% a.a.", "3 meses"]}).to_csv(tmp_path / "short.csv", index=False)
    pd.DataFrame({"Tabela": ["short"], "Nota": ["Despesas estimadas"], "Fonte": ["ID CVM 123, p. 7"]}).to_csv(tmp_path / "sources.csv", index=False)
    manifest = _manifest(tmp_path, [
        DeepDiveTableSpec("short", "Proteções", "short.csv", first_column="Critério", kind="document_comparison"),
        DeepDiveTableSpec("comparison_evidence", "Fontes", "sources.csv", first_column="Tabela", kind="source_table"),
    ])
    pages = build_document_comparison_pages(manifest)
    assert pages[0].frame.iloc[0]["FIDC A"] == "0% a.a."
    assert pages[0].frame.iloc[1]["FIDC A"] == "Não localizado"
    assert pages[0].notes == ("Despesas estimadas",)
    assert pages[0].sources == ("ID CVM 123, p. 7",)


def test_legacy_package_shows_all_funds_and_all_schedules(tmp_path: Path):
    pd.DataFrame({"Nome": ["CNPJ", "PL (R$ mm)", "Subordinação mínima"], "FIDC A": ["11111111000111", "2", "15%"], "FIDC B": ["22222222000122", "4", "20%"]}).to_csv(tmp_path / "main.csv", index=False)
    schedule = "15/12/2027: 16,67%; 15/05/2028: 100,00%"
    pd.DataFrame({"CNPJ": ["11111111000111", "11111111000111", "22222222000122"], "Tipo": ["Sênior", "Sênior", "Sênior"], "Classe/Série": ["Série 1", "Série 2", "Série B"], "Remuneração-alvo": ["DI + 1% a.a.", "DI + 2% a.a.", ""], "Amortização/vencimento": [schedule, "Mensal", "Não localizado"], "Fonte": ["Regulamento A", "Suplemento 2", "Regulamento B"]}).to_csv(tmp_path / "emissions.csv", index=False)
    pages = build_document_comparison_pages(_manifest(tmp_path, [
        DeepDiveTableSpec("comparison_main", "Principal", "main.csv"),
        DeepDiveTableSpec("emissions", "Emissões", "emissions.csv", first_column="CNPJ"),
    ]))
    assert "PL (R$ mm)" not in pages[0].frame["Critério"].tolist()
    assert list(pages[0].frame.columns) == ["Critério", "FIDC A", "FIDC B"]
    rate = next(p for p in pages if p.title == "Remuneração das cotas")
    assert "Série 1" in rate.frame.iloc[0]["FIDC A"] and "Série 2" in rate.frame.iloc[0]["FIDC A"]
    assert rate.frame.iloc[0]["FIDC B"] == "Série B: Não localizado"
    payments = next(p for p in pages if p.title == "Amortização e pagamentos")
    assert schedule in payments.frame.iloc[0]["FIDC A"]


def test_cell_qualifications_stay_with_fund_and_rule_in_slide_sources(tmp_path: Path):
    pd.DataFrame({'Critério': ['Subordinação'], 'FIDC A': ['5% numeral; 3% por extenso'], 'FIDC B': ['15%']}).to_csv(tmp_path / 'short.csv', index=False)
    pd.DataFrame([{'Tabela': 'short', 'CNPJ': '11111111000111', 'Critério': 'Subordinação', 'Valor': '5% numeral; 3% por extenso', 'Fonte': 'ID 123 p.8', 'Nota': 'Divergência; obter esclarecimento'}, {'Tabela': 'short', 'CNPJ': 'Carteira', 'Critério': 'Nota', 'Valor': 'Base documental', 'Fonte': '', 'Nota': 'Versões identificadas por data'}]).to_csv(tmp_path / 'sources.csv', index=False)
    pages = build_document_comparison_pages(_manifest(tmp_path, [DeepDiveTableSpec('short', 'Proteções', 'short.csv', first_column='Critério', kind='document_comparison'), DeepDiveTableSpec('comparison_evidence', 'Fontes', 'sources.csv', subtitle=CELL_REFERENCES_SUBTITLE, first_column='Tabela', kind='source_table')]))
    assert pages[0].notes == ('Versões identificadas por data',)
    assert all(term in pages[0].sources[0] for term in ('11111111000111', 'Subordinação', '5% numeral', 'ID 123 p.8', 'Divergência'))


def test_column_pagination_retains_every_fund():
    frame = pd.DataFrame({"Critério": ["Regra"], **{f"Fundo {i}": [str(i)] for i in range(9)}})
    chunks = comparison_column_chunks(frame)
    assert [c for chunk in chunks for c in chunk.columns[1:]] == list(frame.columns[1:])
    assert all(chunk.columns[0] == "Critério" and len(chunk.columns) <= 5 for chunk in chunks)


def test_html_table_escapes_text_without_truncating_conditions():
    html = _comparison_table_html("<Título>", pd.DataFrame({"Critério": ["Reserva"], "A": ["3 meses\n<script>bad</script>"], "B": [""]}), 1)
    assert "<table>" in html and "scope='row'" in html
    assert "#ec7000" in html
    assert "3 meses<br>&lt;script&gt;bad&lt;/script&gt;" in html
    assert "<script>" not in html
    assert "Não localizado" in html


def test_fund_reading_has_no_fund_dropdown():
    from inspect import getsource
    from tabs.tab_deep_dive import _render_fund_reading
    assert "selectbox" not in getsource(_render_fund_reading)
