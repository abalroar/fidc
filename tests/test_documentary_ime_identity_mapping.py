import json
from services import documentary_ime_comparison as ime
from tests.test_documentary_ime_comparison import fund, observe, make_cache, CNPJ


def test_only_evidenced_exact_inverse_pair_after_registration_is_accepted(tmp_path, monkeypatch):
    cnpj='63953620000165'; parent='63953619000130'
    folder=tmp_path/'data/documentary_diligence/identity_mappings';folder.mkdir(parents=True)
    monkeypatch.setenv('FIDC_DOCUMENTARY_SOURCE_ROOT',str(tmp_path))
    mapping={'cnpj':cnpj,'status':'verified','relationship':'class_of_fund',
             'class_cnpj':cnpj,'fund_cnpj':parent,'allowed_header_layout':'fund_class_inverted',
             'effective_from':'2025-12-05','registry_fund_id':'15695','registry_class_id':'33546',
             'allowed_header_pair':{'NR_CNPJ_FUNDO':cnpj,'NR_CNPJ_CLASSE':parent},
             'sources':[{'document_id':'CVM-register','identity_verified':True,
                         'url':'https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip',
                         'clause':'Join ID_Registro_Fundo15695','sha256':'a'*64}]}
    path=folder/f'{cnpj}.json';path.write_text(json.dumps(mapping))
    assert ime._verified_header_mapping(cnpj,cnpj,parent,'08/2026')
    assert not ime._verified_header_mapping(cnpj,cnpj,parent,'11/2025')
    assert not ime._verified_header_mapping(cnpj,cnpj,'11111111000111','08/2026')
    mapping['sources'][0]['url']='https://example.com/registry'
    path.write_text(json.dumps(mapping))
    assert not ime._verified_header_mapping(cnpj,cnpj,parent,'08/2026')


def test_requires_initial_date_flag_alone_suspends_compliance():
    item=observe(fund(requires_initial_date=True))
    assert item['observed_value'] is not None
    assert item['status']=='not_comparable'
    assert 'data de início' in item['reason']


def test_fidc_quota_field_outside_securities_and_conflicting_alias(tmp_path):
    make_cache(tmp_path)
    directory=tmp_path/'.cache/fundonet-ime/test'
    wide=directory/'wide.csv'
    with wide.open('a') as stream:
        stream.write('DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_COTA_FIDC,80\n')
    files=json.dumps({'wide_csv_path':'wide.csv','listas_csv_path':'listas.csv','docs_csv_path':'docs.csv'})
    values,source,error=ime._cache_snapshot(str(directory),files,CNPJ,'02/2026',wide.stat().st_mtime_ns)
    assert not error
    assert values['fidc_quotas']==80
    with wide.open('a') as stream:
        stream.write('DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VALORES_MOB/VL_COTA_FIDC,70\n')
    values,source,error=ime._cache_snapshot(str(directory),files,CNPJ,'02/2026',wide.stat().st_mtime_ns)
    assert not error
    assert values['fidc_quotas'] is None
    assert any('FIDC divergentes' in note for note in source['warnings'])
