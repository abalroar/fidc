from pathlib import Path
import pandas as pd
import pytest
from services.industry_comparative_period import ComparisonCut
from services.industry_anbima_market_source import build_anbima_market_snapshot

def _workbook(path: Path, reference: str='ago/2026') -> None:
    rows=[[None,'Data','Debêntures','FIDC','CRI','Notas Comerciais','CRA']]
    names=['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
    for year in (2023,2024,2025,2026):
        for month in range(1,13 if year<2026 else 9):
            rows.append([None,f'{names[month-1]}/{year%100:02d}',1.,2.,3.,4.,5.])
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame([[f'Data referência: {reference}']]).to_excel(writer,sheet_name='Planilha1',header=False,index=False)
        pd.DataFrame(rows).to_excel(writer,sheet_name='02-02-Vlr',header=False,index=False)

def test_bulletin_retains_brl_units_and_observed_august_cut(tmp_path: Path) -> None:
    path=tmp_path/'bulletin.xlsx';_workbook(path)
    frame,meta=build_anbima_market_snapshot(path,comparison_cut=ComparisonCut(2026,8),source_url='https://data-strapi.prd.anbima.com.br/uploads/bulletin.xlsx',source_as_of_date='2026-10-08')
    fidc=frame[frame.instrument_label.eq('FIDCs')]
    assert fidc.closed_volume_brl.tolist()==[24.,24.,24.,16.]
    assert fidc.iloc[-1].period_end=='2026-08-31'
    assert meta['source_reference_competence']=='2026-08'
    assert len(meta['source_workbook_sha256'])==64

def test_bulletin_cannot_relabel_lagging_source(tmp_path: Path) -> None:
    path=tmp_path/'bulletin.xlsx';_workbook(path,'jun/2026')
    frame, meta = build_anbima_market_snapshot(path,comparison_cut=ComparisonCut(2026,8),source_url='https://data-strapi.prd.anbima.com.br/uploads/bulletin.xlsx',source_as_of_date='2026-10-08')
    current = frame[~frame.is_full_year]
    assert current.period_label.eq('2026 jan-jun').all()
    assert current.period_end.eq('2026-06-30').all()
    assert meta['comparison_meta']['current_period_end'] == '2026-06-30'
    assert meta['cvm_latest_complete_meta']['current_period_end'] == '2026-08-31'
    assert meta['source_reference_competence'] == '2026-06'
    assert meta['source_lag_months'] == 2
    assert current.limitation.str.contains('Boletim anterior').all()
    assert current[current.instrument_label.eq('FIDCs')].closed_volume_brl.iloc[0] == 12.0

def test_bulletin_missing_cell_is_not_replaced_by_zero(tmp_path: Path) -> None:
    path=tmp_path/'bulletin.xlsx';_workbook(path)
    import openpyxl
    workbook=openpyxl.load_workbook(path);workbook['02-02-Vlr']['D2']=None;workbook.save(path)
    with pytest.raises(ValueError,match='ausente/negativo'):
        build_anbima_market_snapshot(path,comparison_cut=ComparisonCut(2026,8),source_url='https://data-strapi.prd.anbima.com.br/uploads/bulletin.xlsx',source_as_of_date='2026-10-08')


def test_ranking_reference_uses_declared_month_instead_of_filename(tmp_path: Path) -> None:
    from scripts.build_anbima_fixed_income_ranking import workbook_reference_cut
    path = tmp_path / "ranking-Outubro-2026.xlsx"
    pd.DataFrame([["Ranking de Renda Fixa", "Agosto/2026"]]).to_excel(path, header=False, index=False)
    assert workbook_reference_cut(path) == ComparisonCut(2026, 8)
