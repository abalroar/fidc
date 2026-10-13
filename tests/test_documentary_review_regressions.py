"""Independent review regressions: synthetic fixtures never stand for fund facts."""
import csv
import json
from pathlib import Path
from types import SimpleNamespace

from services import documentary_ime_comparison as ime

CNPJ = '60010416000112'
OTHER = '63953620000165'


def make_cache(root, *, fund_header=CNPJ, class_header=None, competence='02/2026'):
    directory=root/'.cache/fundonet-ime/review';directory.mkdir(parents=True)
    files={'wide_csv_path':'wide.csv','docs_csv_path':'docs.csv'}
    (directory/'manifest.json').write_text(json.dumps({'cnpj_fundo':CNPJ,'competencias':[competence],'files':files}))
    with (directory/'wide.csv').open('w') as stream:
        writer=csv.writer(stream);writer.writerow(['tag_path',competence])
        writer.writerow(['DOC_ARQ/CAB_INFORM/NR_CNPJ_FUNDO',fund_header])
        if class_header:writer.writerow(['DOC_ARQ/CAB_INFORM/NR_CNPJ_CLASSE',class_header])
        writer.writerow(['DOC_ARQ/LISTA_INFORM/PATRLIQ/VL_PATRIM_LIQ','100'])
        writer.writerow(['DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_DISPONIB','2'])
    (directory/'docs.csv').write_text(f'documento_id,competencia,versao,data_entrega,status_documento\n123456,{competence},1,14/03/2026 10:00,AC\n')
    return directory,files


def make_portable(root, cnpj, competence):
    base=root/'data/documentary_diligence';relative=f'ime/{cnpj}_{competence[3:]}{competence[:2]}.json'
    path=base/relative;path.parent.mkdir(parents=True,exist_ok=True)
    source={'type':'ime_document','cnpj':cnpj,'competence':competence,'document_id':'1234567','version':2,'delivered_at':'2026-03-15T12:00:00'}
    path.write_text(json.dumps({'schema_version':1,'transformation_version':ime.IME_TRANSFORMATION_VERSION,'cnpj':cnpj,'competence':competence,'status':'parsed','values':{'net_asset_value':100,'cash':2},'source':source}))
    indexpath=base/'ime_index.json';index=json.loads(indexpath.read_text()) if indexpath.exists() else {'schema_version':1,'cnpjs':{}}
    entry=index['cnpjs'].setdefault(cnpj,{'snapshots':{}});entry['snapshots'][competence]=relative;indexpath.write_text(json.dumps(index))


def test_reference_excludes_invalid_local_header_before_common_month(tmp_path):
    make_cache(tmp_path,fund_header=OTHER)
    make_portable(tmp_path,CNPJ,'01/2026')
    make_portable(tmp_path,OTHER,'01/2026');make_portable(tmp_path,OTHER,'02/2026')
    portfolio=SimpleNamespace(funds=[SimpleNamespace(cnpj=CNPJ),SimpleNamespace(cnpj=OTHER)])
    reference=ime.resolve_documentary_reference(portfolio,source_root=tmp_path)
    assert reference['competence']=='01/2026', 'February from a manifest with another CNPJ cannot define the common basket position.'


def test_explicit_source_root_uses_its_verified_identity_mapping(tmp_path,monkeypatch):
    monkeypatch.delenv('FIDC_DOCUMENTARY_SOURCE_ROOT',raising=False)
    directory,files=make_cache(tmp_path,class_header=OTHER)
    mapping={'status':'verified','relationship':'class_of_fund','allowed_header_layout':'fund_class_inverted',
             'cnpj':CNPJ,'class_cnpj':CNPJ,'fund_cnpj':OTHER,'effective_from':'2025-01-01',
             'allowed_header_pair':{'NR_CNPJ_FUNDO':CNPJ,'NR_CNPJ_CLASSE':OTHER},'registry_fund_id':'111','registry_class_id':'222',
             'sources':[{'identity_verified':True,'document_id':'registry-fi-cvm','clause':'registry IDs 111/222',
                         'sha256':'a'*64,'url':'https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip'}]}
    location=tmp_path/'data/documentary_diligence/identity_mappings';location.mkdir(parents=True)
    (location/f'{CNPJ}.json').write_text(json.dumps(mapping))
    values,source,error=ime._snapshot(CNPJ,'02/2026',None,tmp_path)
    assert not error, 'An explicit data root must not read mapping files from a different checkout.'
    assert source['identity_basis']=='verified_fund_class_inversion'
    assert values['cash']==2


def test_cell_keeps_full_historical_evidence_out_of_initial_html():
    from services.documentary_diligence import _cell_html
    item={'criterion_id':'allocation','label':'Synthetic allocation','status':'confirmed','applicability':'applicable',
          'value':'A classe deverá manter 51% do PL em direitos creditórios.',
          'sources':[{'document_id':'123456','title':'Synthetic current regulation','reference_date':'2026-01-01','page':3}],
          'history':[{'document_id':str(100000+i),'reference_date':'2025-01-01','page':3,
                      'value':'HISTORICAL_EVIDENCE_BODY_'*180} for i in range(50)]}
    markup=_cell_html(item)
    assert len(markup.encode())<12000, 'History needs a bounded summary in initial HTML; full passages belong in the evidence download.'
