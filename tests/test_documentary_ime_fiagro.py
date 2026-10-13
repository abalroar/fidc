import csv
import json
from services import documentary_ime_comparison as ime


def test_fiagro_pl_and_cpr_are_declared_fields_and_not_eligible_credit_or_cash(tmp_path, monkeypatch):
    cnpj='62696791000193'
    fields={
        'DOC_ARQ/CAB_INFORM/NR_CNPJ_FUNDO':cnpj,
        'DOC_ARQ/CAB_INFORM/NR_CNPJ_CLASSE':cnpj,
        'DOC_ARQ/LISTA_INFORM/VL_PATRIMONIO_LIQUIDO':'100,00',
        'DOC_ARQ/LISTA_INFORM/INFO_ATIVO/VL_TOTAL_INVEST':'99,00',
        'DOC_ARQ/LISTA_INFORM/INFO_ATIVO/VL_TOTAL_MANTIDO_NECES_LIQ':'1,00',
        'DOC_ARQ/LISTA_INFORM/INFO_ATIVO/DET_VL_TOTAL_INVEST/DET_VL_ATIV_FINAN_LATO_SENSU/DET_TIT_CRED/VL_CPR':'99,00',
        'DOC_ARQ/LISTA_INFORM/PL_SUBCLASSES/VL_PL_SUBCLASSE':'10,00',
    }
    path=tmp_path/'wide.csv'
    with path.open('w') as stream:
        writer=csv.writer(stream);writer.writerow(['tag_path','08/2026']);writer.writerows(fields.items())
    values,source,error=ime._cache_snapshot(str(tmp_path),json.dumps({'wide_csv_path':'wide.csv'}),cnpj,'08/2026',path.stat().st_mtime_ns)
    assert not error
    assert values['net_asset_value']==100
    assert values['cpr']==99 and values['liquid_assets']==1
    assert values['cash'] is None and values['credit_rights'] is None
    assert values['senior_quotas'] is None
    assert source['layout']=='FIAGRO-IME'
    assert source['field_paths']['net_asset_value']==['DOC_ARQ/LISTA_INFORM/VL_PATRIMONIO_LIQUIDO']
    monkeypatch.setattr(ime,'_snapshot',lambda *_:(values,source,''))
    fund={'cnpj':cnpj,'criteria':[{'criterion_id':'allocation','status':'confirmed','applicability':'applicable',
          'sources':[{'document_id':1143317,'reference_date':'2026-03-23','page':14}],
          'rule':{'numerator':'agribusiness_credit_rights','denominator':'net_asset_value','operator':'>=',
                  'limit':51,'unit':'percent','layer':'class','effective_from':'2026-03-23'}}]}
    observation=ime.build_documentary_observations(fund,competence='08/2026')[0]
    assert observation['context_value']==99
    assert observation['observed_value'] is None
    assert observation['status']=='not_comparable'
    assert 'elegibilidade individual' in observation['reason']
