"""Thematic layout rules of the portfolio deck, valid for every basket."""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pandas as pd
from pptx import Presentation

from tests.test_portfolio_ppt_export import _build, _inputs, _spec, _tables, _visible_text


def _titles(payload):
    presentation = Presentation(BytesIO(payload))
    return [next((shape.text for shape in slide.shapes if shape.has_text_frame and shape.top < 914400), "")
            for slide in presentation.slides]


def _dashboard(months=13, *, subordination=None, coverage=None):
    dates = pd.date_range("2025-06-01", periods=months, freq="MS").strftime("%m/%Y")
    return SimpleNamespace(
        latest_competencia=dates[-1], summary={"ativos_totais": 1_200_000_000.0, "direitos_creditorios": 900_000_000.0},
        subordination_history_df=pd.DataFrame({"competencia": dates, "subordinacao_pct": subordination if subordination is not None else [30.0] * months}),
        default_history_df=pd.DataFrame({"competencia": dates, "inadimplencia_pct": [1.0 + i / 10 for i in range(months)],
                                         "provisao_pct_direitos": [0.5 + i / 20 for i in range(months)],
                                         "cobertura_pct": coverage if coverage is not None else [100.0] * months}),
    )


def test_themes_follow_snapshot_then_documents_then_one_coverage_slide():
    kwargs = _inputs(months=13)
    kwargs["dashboard"] = _dashboard()
    titles = [title for title in _titles(_build(kwargs)) if title]
    order = ["Snapshot", "Estrutura", "Atraso e provisão", "Migração e safras", "Rentabilidade",
             "Documentos completos", "Referências e cobertura"]
    positions = [titles.index(title) for title in order]
    assert positions == sorted(positions)
    # Each theme is contiguous: charts and their series never split apart.
    for theme in order[1:5]:
        indexes = [index for index, title in enumerate(titles) if title == theme]
        assert indexes == list(range(indexes[0], indexes[-1] + 1))
    assert titles.count("Referências e cobertura") == 1
    assert "Séries mensais" not in titles and "Séries IME" not in titles


def test_appendix_placement_moves_series_tables_after_documents_in_theme_order():
    kwargs = _inputs(months=13)
    spec = _spec({**kwargs, "table_placement": "appendix"})
    titles = [page.title for page in spec.slides]
    appendix = [title for title in titles if title.startswith("Apêndice · ")]
    assert appendix and titles.index(appendix[0]) > titles.index("Documentos completos")
    assert appendix == sorted(appendix, key=["Apêndice · Estrutura", "Apêndice · Atraso e provisão",
                                             "Apêndice · Migração e safras", "Apêndice · Rentabilidade"].index)
    body = [page for page in spec.slides if page.title in {"Estrutura", "Atraso e provisão"}]
    assert body and all(page.layout == "panels" for page in body)


def test_reported_series_equal_to_derived_is_shown_once():
    kwargs = _inputs(months=13)
    kwargs["dashboard"] = _dashboard(subordination=[30.0] * 13)
    spec = _spec(kwargs)
    labels = [str(row.iloc[0]) for page in spec.slides for block in page.blocks
              if hasattr(block, "frame") and page.title == "Estrutura" for _, row in block.frame.iterrows()]
    assert "Subordinação ex-360" in labels and "Subordinação reportada" not in labels
    charts = [block for page in spec.slides for block in page.blocks if getattr(block, "title", "") == "Subordinação · %"]
    assert all(len(chart.series) == 1 for chart in charts if hasattr(chart, "series"))
    assert "coincide" in _visible_text(_build(kwargs))


def test_different_reported_series_shares_the_derived_chart():
    kwargs = _inputs(months=13)
    kwargs["dashboard"] = _dashboard(subordination=[25.0 + i / 10 for i in range(13)])
    chart = next(block for page in _spec(kwargs).slides for block in page.blocks
                 if getattr(block, "title", "") == "Subordinação · %")
    assert [series.label for series in chart.series] == ["Subordinação ex-360", "Subordinação reportada (IME)"]


def test_constant_coverage_becomes_a_sentence_not_a_chart():
    kwargs = _inputs(months=13)
    kwargs["dashboard"] = _dashboard(coverage=[100.0] * 13)
    spec = _spec(kwargs)
    charts = [block.title for page in spec.slides for block in page.blocks if hasattr(block, "series")]
    assert "Cobertura provisão / vencidos (IME) · %" not in charts
    assert "Provisão / vencidos: 100,0% em todo o período." in _visible_text(_build(kwargs))


def test_snapshot_drops_comparison_columns_without_data_and_negative_zero():
    kwargs = _inputs(months=13)
    cnpj = kwargs["funds"][0].cnpj
    for frame in (kwargs["outputs"].fund_monthly[cnpj], kwargs["monitor_outputs"].fund_monitor[cnpj]):
        frame["carteira_ex360_yoy_pct"] = float("nan")
        frame["subordinacao_total_ex360_pct"] = [30.0] * 12 + [29.99]
    snapshot = next(page for page in _spec(kwargs).slides if page.title == "Snapshot").blocks[0]
    assert "Var. anual" not in snapshot.frame.columns
    assert not any("-0,0" in str(value) for value in snapshot.frame.to_numpy().ravel())


def test_long_documentary_text_leaves_the_cell_and_keeps_full_clause_in_appendix():
    payload = _build(_inputs(long_document=True))
    cells = [cell.text for table in _tables(payload) for row in table.rows for cell in row.cells]
    assert any("texto integral em C1" in cell for cell in cells)
    assert "Cláusulas integrais" in _titles(payload)
    assert "cláusula219" in _visible_text(payload)


def test_continued_table_says_cont_and_never_repeats_a_subtitle_on_a_slide():
    kwargs = _inputs(months=13, series=23)
    presentation = Presentation(BytesIO(_build(kwargs)))
    for slide in presentation.slides:
        subtitles = [shape.text for shape in slide.shapes if shape.has_text_frame and shape.name == "Título"
                     and 1.3 * 914400 < shape.top < 6.6 * 914400]
        assert len(subtitles) == len(set(subtitles))


def test_spike_caps_the_axis_and_is_reported():
    from services.portfolio_ppt_export import _axis_cap

    values = [340, 314, 700, 247, 437, 276, 256, 247, 261, 262, 245, 246, 274]
    cap = _axis_cap(values)
    # Only the 700% spike is far out; 437% stays visible under the cap.
    assert cap is not None and 437 < cap < 700
    assert _axis_cap([1, 2, 3, 4, 5, 6, 7, 8, 9]) is None


def test_dividers_only_in_long_decks_and_before_sections_with_three_slides():
    from services.portfolio_ppt_export import DIVIDER_MIN_SLIDES, _section_dividers

    pages = [SimpleNamespace(section=label) for label in ("", "Estrutura", "Atraso e provisão", "Rentabilidade")]
    spec = SimpleNamespace(slides=pages)
    long_counts = [1, 10, 12, 2]
    assert _section_dividers(spec, long_counts, "auto") == {1: ("Estrutura", 10), 2: ("Atraso e provisão", 12)}
    short_counts = [1, 5, 5, 2]
    assert 1 + sum(short_counts) <= DIVIDER_MIN_SLIDES
    assert _section_dividers(spec, short_counts, "auto") == {}
    assert _section_dividers(spec, short_counts, "always") == {1: ("Estrutura", 5), 2: ("Atraso e provisão", 5)}
    assert _section_dividers(spec, long_counts, "never") == {}


def test_multi_fund_keeps_fund_detail_in_a_per_fund_annex():
    spec = _spec(_inputs(months=13, funds=3))
    sections = [page.section for page in spec.slides]
    assert "Anexo por fundo" in sections
    first_annex = sections.index("Anexo por fundo")
    assert sections.index("Referências e cobertura") > first_annex
    assert all(page.context.startswith("Consolidado") for page in spec.slides
               if page.title in {"Estrutura", "Atraso e provisão"})


def test_two_spikes_in_a_short_series_still_cap_the_axis():
    from services.portfolio_ppt_export import _axis_cap

    # A coverage ratio over a near-zero NPL: two far-out points in eight.
    values = [804_685.9, 1_146_011.0, 20_905.1, 23_791.8, 3_027.7, 3_165.0, 3_016.4, 1_736.8]
    cap = _axis_cap(values)
    assert cap is not None and 23_791.8 < cap < 804_685.9


def test_series_with_fewer_than_three_points_become_values_not_lines():
    from services.portfolio_ppt_content import ChartBlock, ChartSeries, _is_trivial, _trivial_sentence

    chart = ChartBlock("Vencidos · %", ("jan/26", "fev/26", "mar/26"),
                       (ChartSeries("a", "Vencidos", (0.0, 0.7, None)), ChartSeries("b", "Provisão", (None, 3.4, None))))
    assert _is_trivial(chart)
    text = _trivial_sentence(chart).text
    assert "Vencidos: 0,0% (jan/26) → 0,7% (fev/26)." in text
    assert "Provisão: 3,4% em fev/26 (1 observação)." in text


def test_four_integer_digits_drop_decimals_in_cells():
    from services.portfolio_ppt_export import format_cell

    assert format_cell(10_971.84, "number:2") == "10.972"
    assert format_cell(1_146_010.95, "percent:2") == "1.146.011%"
    assert format_cell(999.5, "number:2") == "999,50"
    assert format_cell(10_971_840_000.0, "money_value:2") == "10.972"


def test_curated_absence_with_a_reason_is_absence():
    from services.portfolio_ppt_content import _is_missing

    assert _is_missing("N/D — texto extraído sem associação confiável")
    assert _is_missing("Não localizado nas cláusulas revisadas; requer documento aplicável")
    assert _is_missing("Não informado nas fontes consultadas")
    assert not _is_missing("Não previsto")


def test_rows_and_columns_without_values_leave_series_tables():
    from services.portfolio_ppt_content import TableBlock, _prune_empty

    frame = pd.DataFrame({"Indicador": ["A", "B"], "jan/26": [1.0, None], "fev/26": [None, None]})
    block, said = _prune_empty(TableBlock("T · %", frame, numeric_columns=("jan/26", "fev/26")))
    assert list(block.frame.columns) == ["Indicador", "jan/26"] and list(block.frame["Indicador"]) == ["A"]
    assert any("B" in sentence for sentence in said) and any("fev/26" in sentence for sentence in said)


def test_base_warnings_are_one_line_per_warning_with_canonical_names():
    kwargs = _inputs(months=13, funds=2)
    cnpj = kwargs["funds"][0].cnpj
    kwargs["outputs"].warnings_df = pd.DataFrame({
        "scope_name": ["FUNDO 1 LEGAL", "FUNDO 1 LEGAL", "Carteira"], "cnpj": [cnpj, cnpj, "CONSOLIDADO"],
        "competencia": ["07/2025", "08/2025", "07/2025"],
        "warning": ["denominador zero/ausente", "denominador zero/ausente", "consolidado parcial na competência"]})
    cells = [cell.text for table in _tables(_build(kwargs)) for row in table.rows for cell in row.cells]
    assert "scope_name" not in cells and "warning" not in cells
    row = cells.index("Aviso da base · denominador zero/ausente")
    # Canonical fund name (not the legal one), months compressed in one cell.
    assert cells[row + 1].endswith(": jul/25, ago/25.") and "LEGAL" not in cells[row + 1]


def test_large_basket_summarizes_the_annex_in_one_row_per_fund():
    from services.portfolio_ppt_content import FUND_ANNEX_MAX_FUNDS

    funds = FUND_ANNEX_MAX_FUNDS + 1
    spec = _spec(_inputs(months=13, funds=funds))
    annex = [page for page in spec.slides if page.section == "Anexo por fundo"]
    assert len(annex) == 1 and len(annex[0].blocks[0].frame) == funds
    snapshot = next(page for page in spec.slides if page.title == "Snapshot")
    assert all(block.title != "Comparação entre fundos" for block in snapshot.blocks)
    full = _spec({**_inputs(months=13, funds=funds), "fund_annex": "full"})
    assert sum(page.section == "Anexo por fundo" for page in full.slides) == funds


def test_small_basket_annex_has_one_flow_per_fund():
    spec = _spec(_inputs(months=13, funds=3))
    annex = [page for page in spec.slides if page.section == "Anexo por fundo"]
    assert len(annex) == 3 and all(page.context.startswith("Anexo por fundo") for page in annex)


def test_fund_without_monthly_data_leaves_comparisons_and_is_named_in_coverage():
    kwargs = _inputs(months=13, funds=3)
    missing = kwargs["funds"][2].cnpj
    kwargs["outputs"].fund_monthly[missing] = pd.DataFrame()
    kwargs["monitor_outputs"].fund_monitor[missing] = pd.DataFrame()
    spec = _spec(kwargs)
    comparison = next(block for page in spec.slides for block in page.blocks
                      if getattr(block, "title", "") == "Comparação entre fundos")
    assert len(comparison.frame) == 2
    assert sum(page.section == "Anexo por fundo" for page in spec.slides) == 2
    coverage = next(block for page in spec.slides for block in page.blocks
                    if getattr(block, "title", "") == "Fontes, cortes e cobertura").frame
    row = coverage[coverage["Referência"] == "Sem informe mensal"]
    assert len(row) == 1 and "2 de 3 fundos" in row["Conteúdo"].iloc[0]
