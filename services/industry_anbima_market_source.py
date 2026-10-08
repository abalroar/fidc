"""Read ANBIMA's official market bulletin with source lineage and a common cut."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import pandas as pd
from services.industry_comparative_period import ComparisonCut, MONTH_LABELS
from services.industry_offer_periods import offer_periods
from services.industry_market_offer_reconciliation import validate_anbima_market_offers

PUBLICATION_API = 'https://data-strapi.prd.anbima.com.br/api/boletim-mercado-de-capitais?populate=template.attachment&sort=publishedAt:desc'
STRAPI_BASE = 'https://data-strapi.prd.anbima.com.br'
SOURCE_SHEET = '02-02-Vlr'
INSTRUMENT_HEADERS = {'Debêntures':'Debêntures','FIDCs':'FIDC','CRI':'CRI','Notas comerciais':'Notas Comerciais','CRA':'CRA'}

def resolve_market_bulletin() -> dict[str, str]:
    with urlopen(Request(PUBLICATION_API,headers={'User-Agent':'FIDC-industry-audit/1.0'}), timeout=120) as response:
        rows=json.loads(response.read().decode())['data']
    for row in rows:
        attributes=row['attributes']
        attached=(attributes.get('template') or {}).get('attachment') or {}
        data=attached.get('data')
        if not data:
            continue
        source=data['attributes']
        if str(source.get('url','')).lower().endswith('.xlsx'):
            return {'url':urljoin(STRAPI_BASE,source['url']),'file_name':source['name'],'published_at':attributes.get('publishedAt',''),'publication_title':attributes.get('title','')}
    raise ValueError('Boletim ANBIMA sem anexo XLSX público')

def build_anbima_market_snapshot(workbook: str | Path, *, comparison_cut: ComparisonCut, source_url: str, source_as_of_date: str, source_published_at: str = '') -> tuple[pd.DataFrame, dict]:
    workbook=Path(workbook)
    digest=sha256(workbook.read_bytes()).hexdigest()
    reference=pd.read_excel(workbook,sheet_name='Planilha1',header=None)
    label=str(reference.iat[0,0]).split(':',1)[-1].strip().casefold()
    match=re.fullmatch(r'([a-z]{3})/(\d{4})',label)
    if match is None or match[1] not in MONTH_LABELS:
        raise ValueError('Boletim ANBIMA sem data de referência reconhecível')
    available=ComparisonCut(int(match[2]),MONTH_LABELS.index(match[1])+1)
    requested_cut = comparison_cut
    comparison_cut = min((requested_cut, available), key=lambda cut: (cut.year, cut.month))
    source_lag_months = max(0, (requested_cut.year - available.year) * 12 + requested_cut.month - available.month)
    raw=pd.read_excel(workbook,sheet_name=SOURCE_SHEET,header=None)
    header_indices=raw.index[raw.iloc[:,1].astype(str).eq('Data')]
    if len(header_indices)!=1:
        raise ValueError('Boletim ANBIMA sem cabeçalho único Data')
    header=raw.loc[header_indices[0]]
    columns={}
    for instrument,name in INSTRUMENT_HEADERS.items():
        matches=header.index[header.astype(str).eq(name)].tolist()
        if len(matches)!=1:raise ValueError(f'Cabeçalho ANBIMA ausente/duplicado: {name}')
        columns[instrument]=matches[0]
    dates={}
    for index, value in raw.iloc[:,1].items():
        match=re.fullmatch(r'([A-Za-z]{3})/(\d{2})',str(value))
        if not match:continue
        month=match[1].casefold()
        if month not in MONTH_LABELS:continue
        key=(2000+int(match[2]),MONTH_LABELS.index(month)+1)
        if key in dates:raise ValueError(f'Mês ANBIMA duplicado {key}')
        dates[key]=index
    rows=[]
    for period in offer_periods(comparison_cut):
        year=int(str(period['period_start'])[:4]);months=12 if period['is_full_year'] else comparison_cut.month
        required=[(year,month) for month in range(1,months+1)]
        if any(key not in dates for key in required):raise ValueError(f'Boletim ANBIMA com meses ausentes em {period["period_label"]}')
        indices=[dates[key] for key in required]
        for order,(instrument,name) in enumerate(INSTRUMENT_HEADERS.items(),start=1):
            column=columns[instrument]
            values=pd.to_numeric(raw.loc[indices,column],errors='coerce')
            if values.isna().any() or values.lt(0).any():raise ValueError(f'ANBIMA {instrument}: volume ausente/negativo em {period["period_label"]}')
            # Excel numbers already use BRL, never millions.
            from openpyxl.utils import get_column_letter
            cell_range=f'{get_column_letter(column+1)}{min(indices)+1}:{get_column_letter(column+1)}{max(indices)+1}'
            rows.append({**period,'instrument_order':order,'instrument_label':instrument,'anbima_instrument_label':name,'closed_volume_brl':float(values.sum()),'source_name':'ANBIMA Data — Boletim de Mercado de Capitais','source_snapshot':f'{MONTH_LABELS[available.month-1]}/{available.year%100:02d}','source_sheet':SOURCE_SHEET,'source_range':cell_range,'source_url':source_url,'source_workbook_sha256':digest,'metric':'Valor Encerrado','scope':'Ofertas públicas encerradas por data de encerramento','limitation':'O anexo não segrega sistematicamente ofertas primárias e secundárias; série sujeita a retificações.' + (f' Boletim anterior ao corte CVM {requested_cut.competence}; esta comparação mantém {comparison_cut.period_label()}.' if source_lag_months else '')})
    frame=validate_anbima_market_offers(pd.DataFrame(rows))
    manifest={'schema':'anbima_market_offers.v2','comparison_meta':comparison_cut.to_meta(),'cvm_latest_complete_meta':requested_cut.to_meta(),'source_lag_months':source_lag_months,'source_reference_competence':available.competence,'source_url':source_url,'source_as_of_date':source_as_of_date,'source_published_at':source_published_at,'source_workbook_sha256':digest,'source_path':str(workbook),'source_sheet':SOURCE_SHEET,'row_count':len(frame)}
    return frame,manifest
