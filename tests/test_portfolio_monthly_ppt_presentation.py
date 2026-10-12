"""Portfolio-only presentation rules retain the shared export defaults and data."""
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import pandas as pd
from pptx import Presentation

from services.somatorio_fidcs_ppt_export import build_somatorio_fidcs_pptx_bytes


def _inputs(*, fund_count=1, credit=3.0, fund_ends_before_portfolio=False):
    dates = pd.date_range('2026-01-01', periods=3, freq='MS')
    consolidated = pd.DataFrame({
        'competencia_dt': dates, 'competencia': [date.strftime('%m/%Y') for date in dates],
        'fund_name': ['Carteira de teste'] * 3, 'pl_senior': [700.0] * 3,
        'pl_subordinada_mezz_ex360': [300.0] * 3, 'subordinacao_total_ex360_pct': [30.0] * 3,
        'carteira_ex360': [1000.0] * 3, 'carteira_ex360_yoy_pct': [10.0] * 3,
        'npl_over1_ex360_pct': [credit + 3] * 3, 'npl_over30_ex360_pct': [credit + 2] * 3,
        'npl_over60_ex360_pct': [credit + 1] * 3, 'npl_over90_ex360_pct': [credit] * 3,
        'npl_over90_ex360': [credit * 10] * 3,
        'pdd_npl_over90_ex360_pct': [200.0 if credit else float('nan')] * 3,
        'npl_1_90_pct': [credit] * 3, 'npl_91_360_pct': [credit] * 3,
        'duration_months': [6.0] * 3,
        'roll_61_90_m3_pct': [1.0] * 3, 'roll_91_120_m4_pct': [2.0] * 3,
        'roll_121_150_m5_pct': [3.0] * 3, 'roll_151_180_m6_pct': [4.0] * 3,
    })
    funds = {}
    for index in range(fund_count):
        fund = consolidated.copy()
        fund['fund_name'] = f'CLOUDWALK KICK ASS {index + 1} FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS SEGMENTO MEIOS DE PAGAMENTO'
        fund['duration_months'] = 4.0 + index
        if fund_ends_before_portfolio:
            fund = fund.head(1).copy()
        funds[f'{index:014d}'] = fund
    outputs = SimpleNamespace(consolidated_monthly=consolidated, fund_monthly=funds,
                              fund_return_history={}, fund_return_summary={},
                              metadata={'portfolio_name': 'Nome do usuário 1T26', 'funds': []})
    monitor = SimpleNamespace(consolidated_monitor=consolidated, fund_monitor=funds,
                              consolidated_cohorts=pd.DataFrame(), fund_cohorts={})
    return outputs, monitor


def _deck(outputs, monitor, **kwargs):
    payload = build_somatorio_fidcs_pptx_bytes(outputs=outputs, monitor_outputs=monitor, **kwargs)
    with ZipFile(BytesIO(payload)) as package:
        assert package.testzip() is None
        assert any(name.startswith('ppt/charts/chart') for name in package.namelist())
        assert any(name.startswith('ppt/embeddings/') for name in package.namelist())
    return Presentation(BytesIO(payload))


def _texts(deck):
    return '\n'.join(shape.text for slide in deck.slides for shape in slide.shapes if shape.has_text_frame)


def _chart_data(deck):
    return [[(series.name, list(series.values)) for series in shape.chart.series]
            for slide in deck.slides for shape in slide.shapes if shape.has_chart]


def test_portfolio_style_is_opt_in_and_preserves_original_financial_chart_values():
    outputs, monitor = _inputs()
    before = _deck(outputs, monitor)
    after = _deck(outputs, monitor, portfolio_mode=True)
    assert len(before.slides) == len(after.slides) == 11
    assert 'Mercado de FIDCs' in _texts(before)
    assert 'Soma de FIDCs — Consolidado' in _texts(before)
    assert 'Nome do usuário 1T26' in _texts(after)
    assert 'Carteira — Consolidado' in _texts(after)
    assert _chart_data(before) == _chart_data(after)
    assert '00000000000000' in after.slides[6].notes_slide.notes_text_frame.text
    assert 'FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS' in after.slides[6].notes_slide.notes_text_frame.text


def test_each_fund_uses_its_own_last_observed_competence():
    outputs, monitor = _inputs(fund_ends_before_portfolio=True)
    after = _deck(outputs, monitor, portfolio_mode=True)
    individual_text = '\n'.join(shape.text for slide in list(after.slides)[7:10]
                                for shape in slide.shapes if shape.has_text_frame)
    assert 'Data-base: jan/26' in individual_text
    assert 'Data-base: mar/26' not in individual_text


def test_zero_credit_denominator_is_explicit_and_missing_data_is_distinct():
    outputs, monitor = _inputs(credit=0)
    after = _deck(outputs, monitor, portfolio_mode=True)
    assert 'Não aplicável: NPL > 90d ex-360 é zero na janela.' in _texts(after)
    assert '0,0%' in _texts(after)
    assert any(value == 0.0 for slide in after.slides for shape in slide.shapes if shape.has_chart
               for series in shape.chart.series for value in series.values)
    outputs.consolidated_monthly['npl_over90_ex360'] = float('nan')
    outputs.fund_monthly['00000000000000']['npl_over90_ex360'] = float('nan')
    missing = _deck(outputs, monitor, portfolio_mode=True)
    assert 'N/D: série sem valor informado na janela.' in _texts(missing)


def test_portfolio_duration_keeps_every_fund_in_the_editable_chart():
    outputs, monitor = _inputs(fund_count=5)
    after = _deck(outputs, monitor, portfolio_mode=True)
    duration = next(shape.chart for shape in after.slides[4].shapes if shape.has_chart)
    assert len(duration.series) == 6
    latest = sorted(series.values[-1] for series in duration.series)
    assert latest == [4.0, 5.0, 6.0, 6.0, 7.0, 8.0]


def test_short_duration_label_does_not_change_the_original_series_lookup():
    outputs, monitor = _inputs()
    outputs.fund_monthly['00000000000000']['fund_name'] = 'MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA'
    after = _deck(outputs, monitor, portfolio_mode=True)
    duration = next(shape.chart for shape in after.slides[4].shapes if shape.has_chart)
    assert sorted(series.values[-1] for series in duration.series) == [4.0, 6.0]


def test_portfolio_font_floor_and_credit_band_values_remain_visible():
    outputs, monitor = _inputs()
    after = _deck(outputs, monitor, portfolio_mode=True)
    sizes = [run.font.size.pt for slide in after.slides for shape in slide.shapes
             for frame in ([shape.text_frame] if shape.has_text_frame else
                           [cell.text_frame for row in shape.table.rows for cell in row.cells] if shape.has_table else [])
             for paragraph in frame.paragraphs for run in paragraph.runs if run.font.size]
    assert min(sizes) >= 11
    native_rows = [cell.text for shape in after.slides[2].shapes if shape.has_table
                   for row in shape.table.rows for cell in row.cells]
    assert 'NPL > 1d: 6,0%' in native_rows
    assert 'NPL > 30d: 5,0%' in native_rows
    assert 'NPL > 60d: 4,0%' in native_rows


def test_return_headers_are_short_and_every_native_value_is_preserved():
    outputs, monitor = _inputs()
    history = outputs.consolidated_monthly[['competencia', 'competencia_dt']].copy()
    history['class_kind'] = 'senior'
    history['class_key'] = 'senior:1'
    history['class_label'] = 'Sênior — série 1'
    history['retorno_mensal_pct'] = [1.0, 2.0, 0.0]
    outputs.fund_return_history = {'00000000000000': history}
    extra = {'monthly_cdi_rates_by_fund': {}, 'benchmark_spreads_by_fund': {}}
    before = _deck(outputs, monitor, **extra)
    after = _deck(outputs, monitor, portfolio_mode=True, **extra)
    before_tables = [[[cell.text for cell in row.cells] for row in shape.table.rows]
                     for slide in before.slides for shape in slide.shapes if shape.has_table]
    after_tables = [[[cell.text for cell in row.cells] for row in shape.table.rows]
                    for slide in after.slides for shape in slide.shapes if shape.has_table]
    assert before_tables
    for table in before_tables:
        matching = next(candidate for candidate in after_tables if candidate[1:] == table[1:])
        assert matching[0] != table[0]
        assert matching[0][0] == 'Série'
    notes = '\n'.join(slide.notes_slide.notes_text_frame.text for slide in after.slides)
    assert 'Ac. Últ. 12m (%)' in notes
