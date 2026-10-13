from scripts.build_documentary_diligence import candidate_score, numeric_rule, reviewed_source, material_answer, extract_primary_candidates, choose_passages, build_fund, documented_lookthrough
import json
from pathlib import Path
from scripts import build_documentary_diligence as builder


def test_generic_absence_and_instructions_are_never_values():
    assert not material_answer('Não localizado no corpus acessível')
    assert not material_answer('Elegibilidade e concentração exigem documentos')
    assert not material_answer('selecionar competência para monitorar')
    assert material_answer('Subordinadas/PL ≥ 5%, apuração diária')


def test_history_is_deferred_and_passages_are_deduplicated_without_shortening_current_source():
    source={'document_id':'123456','reference_date':'2025-01-01','page':'9','clause':'4.2',
            'url':'https://example.org/document.pdf','sha256':'pdfhash','excerpt':'Cláusula histórica integral. '*250}
    current=dict(source,document_id='234567',reference_date='2026-01-01')
    original='Valor histórico integral com números e bases. '*100
    records=[builder.historical_answer(original,[source],'Leitura anterior.') for _ in range(5)]
    payload={'cnpj':'11111111000111','criteria':[
        {'criterion_id':'allocation','sources':[current],'history':records},
        {'criterion_id':'subordination','sources':[current],'history':records}]}
    sidecar=builder.compact_history_payload(payload)
    assert len(sidecar['passages'])==1
    assert len(sidecar['entries'])==1
    assert next(iter(sidecar['entries'].values()))['value']==original
    assert next(iter(sidecar['passages'].values()))['excerpt']==source['excerpt']
    for row in payload['criteria']:
        assert row['sources'][0]['excerpt']==current['excerpt']
        assert len(row['history'])==1
        assert len(row['history'][0]['value'])<=321
        assert 'excerpt' not in row['history'][0]['sources'][0]
        assert row['history_ref']['path']=='history/11111111000111.json'
        assert row['history_ref']['total_count']==1
    assert 'não houve revisão retrospectiva integral' in sidecar['scope']


def test_history_preview_is_bounded_but_all_original_records_remain_accessible():
    source={'document_id':'123456','page':'9','clause':'4.2','excerpt':'Trecho integral.'}
    records=[builder.historical_answer(str(index),[dict(source,reference_date=f'2025-01-{index+1:02d}')],str(index)) for index in range(10)]
    payload={'cnpj':'11111111000111','criteria':[{'criterion_id':'allocation','sources':[],'history':records}]}
    sidecar=builder.compact_history_payload(payload)
    row=payload['criteria'][0]
    assert len(row['history'])==3
    assert row['history_count']==10
    assert len(sidecar['criteria']['allocation'])==10
    assert row['history'][0]['value']=='9'
    assert len(sidecar['passages'])==1
    assert {entry['value'] for entry in sidecar['entries'].values()}=={str(i) for i in range(10)}


def test_old_manual_review_is_compacted_and_its_full_value_is_preserved():
    manual={'criterion_id':'allocation','value':'Manual antigo integral. '*100,
            'sources':[{'document_id':'123456','page':'4','excerpt':'Fonte antiga. '*500}],
            'status':'confirmed','applicability':'applicable'}
    payload={'cnpj':'11111111000111','criteria':[{'criterion_id':'allocation','sources':[],
             'history':[],'manual_review':manual}]}
    sidecar=builder.compact_history_payload(payload)
    row=payload['criteria'][0]
    assert len(row['manual_review']['value'])<=321
    assert 'excerpt' not in row['manual_review']['sources'][0]
    assert next(iter(sidecar['entries'].values()))['value']==manual['value']
    assert row['history_ref']['total_count']==1


def test_numeric_zero_quarterly_field_without_text_is_preserved():
    document={'fields':[{'xpath':'/INFORME/RESULTADO_VERIFICACAO_LASTRO','value':0}],
              'source':{'document_id':'123456','identity_verified':True,'type':'quarterly_xml'}}
    records=builder.quarterly_xml_records(document)
    assert records[0]['value']=='0'
    assert records[0]['status']=='reported_raw'
    assert records[0]['source']['xpath']=='/INFORME/RESULTADO_VERIFICACAO_LASTRO'


def test_partial_refresh_replaces_only_requested_criterion_and_preserves_deferred_history():
    unchanged={'criterion_id':'allocation','status':'confirmed','value':'≥50% PL','history_ref':{'path':'history/1.json'},'history_count':4}
    cached={'cnpj':'1','criteria':[unchanged,{'criterion_id':'providers','value':'agências possíveis'}],
            'criterion_revisions':{'allocation':'old','providers':'old'},'lookthrough':[{'cnpj':'2'}]}
    refreshed={'cnpj':'1','criteria':[{'criterion_id':'providers','value':'Genial'}],
               'criterion_revisions':{'providers':'new'},'lookthrough':[],'quarterly_observations':{}}
    merged=builder.merge_partial_fund(cached,refreshed,{'providers'})
    assert merged['criteria'][0] is unchanged
    assert merged['criteria'][1]['value']=='Genial'
    assert merged['criterion_revisions']=={'allocation':'old','providers':'new'}
    assert merged['lookthrough']==cached['lookthrough']


def test_partial_history_compaction_preserves_untouched_original_values_and_replaces_old_entries():
    source={'document_id':'123456','page':'1','excerpt':'Integral.'}
    first={'cnpj':'1','criteria':[{'criterion_id':'allocation','history':[builder.historical_answer('A',[source],'A')]},
                                 {'criterion_id':'providers','history':[builder.historical_answer('Old',[source],'Old')]}]}
    original=builder.compact_history_payload(first)
    first['criteria'][1]={'criterion_id':'providers','history':[builder.historical_answer('New',[source],'New')]}
    revised=builder.compact_history_payload(first,existing_history=original)
    assert {entry['value'] for entry in revised['entries'].values()}=={'A','New'}
    assert revised['criteria']['allocation']==original['criteria']['allocation']
    assert first['criteria'][0]['history_ref']['path']=='history/1.json'


def test_partial_primary_extraction_does_not_revalidate_other_criteria(tmp_path):
    doc=regulation(tmp_path,123456,'01/01/2026','4.2. A Classe deverá manter no mínimo50% do patrimônio líquido em direitos creditórios.')
    payload=build_fund('1','A',{'documents':[doc]},{},[tmp_path],criterion_ids={'allocation'})
    assert [item['criterion_id'] for item in payload['criteria']]==['allocation']
    assert payload['criterion_revisions']=={'allocation':builder.validator_revision()}


def test_refresh_receivables_preserves_investee_link_supported_by_untouched_investee_criterion():
    investee={'criterion_id':'investee','status':'confirmed','value':'Aplicação em cotas do FIDC EXEMPLO CNPJ11.111.111/0001-11.',
              'sources':[{'document_id':'123456','page':'1'}]}
    cached={'cnpj':'22222222000122','criteria':[investee,{'criterion_id':'receivables','status':'confirmed','value':'Anterior'}],
            'lookthrough':[]}
    refreshed={'cnpj':cached['cnpj'],'criteria':[{'criterion_id':'receivables','status':'confirmed','value':'Duplicatas','sources':[]}],
               'lookthrough':[],'lookthrough_provenance':'primary_passage','quarterly_observations':{}}
    payload=builder.merge_partial_fund(cached,refreshed,{'receivables'})
    assert payload['lookthrough'][0]['cnpj']=='11111111000111'


def test_builder_can_read_portable_audits_without_private_indexes(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'ROOT',tmp_path)
    base=tmp_path/'data/documentary_diligence';(base/'audit_corpus').mkdir(parents=True)
    (base/'audit_corpus/1.json').write_text(json.dumps({'cnpj':'1','documents':[{'id':123456}]}))
    (base/'audit_quarterly_index.json').write_text(json.dumps({'cnpjs':{'1':{'status':'parsed'}}}))
    assert builder.load_documentary_corpus('1')['documents'][0]['id']==123456
    assert builder.load_quarterly_inventory()['cnpjs']['1']['status']=='parsed'


def test_event_brief_keeps_a_trigger_instead_of_only_responsibility_heading():
    heading='11.1. São considerados Eventos de Avaliação as ocorrências, observado que o Administrador verificará os subitens e o Gestor os demais. '
    text=heading*6+'(i) não observância do prazo de 180 dias contados da Data da Primeira Integralização de Cotas do Fundo para alocação na aquisição de Direitos Creditórios no mínimo exigido pela política de investimento; (ii) não realização do pagamento sênior em 2 Dias Úteis.'
    result=builder.brief_clause('evaluation',text)
    assert 'não observância' in result
    assert '180' in result
    assert 'Administrador verificará' not in result


def test_revalidation_labels_stored_answer_check_and_archives_rejected_value():
    source={'document_id':'123456','reference_date':'2026-01-01','page':'1','excerpt':'A Classe deverá manter no mínimo50% do patrimônio líquido em direitos creditórios.'}
    payload={'cnpj':'1','criteria':[{'criterion_id':'allocation','status':'confirmed','provenance':'primary_passage','value':source['excerpt'],'sources':[source]},
              {'criterion_id':'evaluation','status':'confirmed','provenance':'primary_passage','value':'Os eventos serão verificados pelo Administrador.','sources':[dict(source,excerpt='Os eventos serão verificados pelo Administrador.')]}]}
    builder.revalidate_published_answers(payload)
    assert payload['criteria'][0]['semantic_validation']['valid']
    assert payload['criterion_revisions']['allocation']==builder.validator_revision()
    assert payload['criteria'][1]['status']=='extraction_pending'
    assert payload['criteria'][1]['value']==''
    assert payload['criteria'][1]['history'][0]['value']=='Os eventos serão verificados pelo Administrador.'
    assert payload['semantic_validation_receipt']['rejected']==1


def test_appending_rejected_answer_does_not_replace_full_old_history_with_its_short_previews():
    old='Integral antigo. '*100
    source={'document_id':'123456','page':'1','excerpt':'Excerto antigo.'}
    payload={'cnpj':'1','criteria':[{'criterion_id':'evaluation','history':[builder.historical_answer(old,[source],'Anterior')]}]}
    previous=builder.compact_history_payload(payload)
    payload['criteria'][0]['history'].append(builder.historical_answer('Resposta rejeitada',[source],'Nova validação'))
    revised=builder.compact_history_payload(payload,existing_history=previous)
    assert {entry['value'] for entry in revised['entries'].values()}=={old,'Resposta rejeitada'}


def test_ocr_excluded_page_never_supplies_a_rule_and_other_page_carries_machine_provenance(tmp_path):
    path=tmp_path/'ocr.txt';path.write_text('4.2. A Classe deverá manter no mínimo50% do patrimônio líquido em direitos creditórios.\f4.3. A Classe deverá manter no mínimo67% do patrimônio líquido em direitos creditórios.')
    doc={'id':123456,'classification':'regulamento','reference_date':'2026-01-01','parse_status':'partial','parse_method':'vision_ocr',
         'text_path':str(path),'ocr_excluded_pages':[1],'ocr_quality':{'pages':[{'page':1,'confidence':0.3},{'page':2,'confidence':0.99}]}}
    records=extract_primary_candidates([doc],[tmp_path],{'allocation'})['allocation']
    assert len(records)==1
    assert records[0]['source']['page']==2
    assert records[0]['source']['verification']=='ocr_primary_passage'
    assert records[0]['source']['ocr_quality']['page_quality']['confidence']==0.99
    assert records[0]['source']['ocr_excluded_pages']==[1]


def test_verified_answer_clears_old_extraction_pending_reason():
    current={'criterion_id':'providers','status':'extraction_pending','reason':'Cláusula primária localizada, mas lista extensa sem síntese.','history':[]}
    replacement={'criterion_id':'providers','status':'confirmed','value':'Administrador identificado','sources':[]}
    result=builder.merge_verified_override(current,replacement,{'superseded':{},'current_ids':set(),'by_id':{}})
    assert result['status']=='confirmed'
    assert result['reason']==''


def test_named_provider_definition_is_material_while_possible_entity_definition_is_not():
    concrete='Administrador significa a EXEMPLO DISTRIBUIDORA LTDA., CNPJ11.111.111/0001-11, contratada para a administração fiduciária do Fundo.'
    generic='Administrador significa a instituição que poderá ser escolhida dentre os prestadores disponíveis no mercado, conforme deliberação posterior.'
    assert candidate_score('providers',('administrador',),concrete)>0
    assert candidate_score('providers',('administrador',),generic)==0


def test_concrete_credit_definition_can_supply_nature_without_a_percentage():
    concrete='Direitos Creditórios Elegíveis significa os empréstimos pessoais concedidos por Banco Exemplo S.A. a pessoas físicas, representados por CCBs e cedidos ao Fundo.'
    generic='Direitos Creditórios Elegíveis significa os direitos creditórios que atendam aos critérios deste regulamento e possam ser ofertados ao Fundo.'
    assert candidate_score('receivables',('direitos creditórios elegíveis',),concrete)>0
    assert candidate_score('receivables',('direitos creditórios elegíveis',),generic)==0


def test_resume_does_not_skip_changed_extractor_when_validator_is_unchanged():
    snapshot={'criterion_revisions':{'providers':builder.validator_revision()},
              'criterion_extractor_revisions':{'providers':'old-extractor'}}
    assert not builder.processing_revisions_current(snapshot,{'providers'})
    snapshot['criterion_extractor_revisions']['providers']=builder.EXTRACTOR_REVISION
    assert builder.processing_revisions_current(snapshot,{'providers'})


def test_allocation_ignores_generic_definition_fifty_percent():
    text='Cotas de Classes de Fundos de Investimento em Direitos Creditórios significa classes com no mínimo 50% de seu patrimônio líquido.'
    assert candidate_score('allocation', ('no mínimo',), text) == 0
    text='4.2. Após 180 dias, a Classe deverá manter no mínimo 51% de seu patrimônio líquido em Direitos Creditórios do Agronegócio.'
    assert candidate_score('allocation', ('no mínimo',), text)>0
    rule=numeric_rule('allocation',text,[{'reference_date':'2026-03-20'}])
    assert rule['limit']==51
    assert rule['requires_initial_date']
    assert rule['effective_status']=='document_date_only'


def test_multiple_layers_never_become_single_ratio():
    assert numeric_rule('subordination','Subordinadas/PL ≥ 5%; júnior/PL ≥ 2%',[])=={}
    assert numeric_rule('allocation','No mínimo 50% do patrimônio líquido em direitos creditórios e mínimo de 67% para tributação',[])=={}
    assert numeric_rule('allocation','Direitos creditórios: no mínimo 67% do patrimônio líquido para tributação e 50% para regulação',[])=={}


def test_corpus_description_cannot_be_counted_as_document_source():
    doc={'id':123456,'reference_date':'2026-01-01','text_path':'some.txt'}
    assert reviewed_source({'source':'Corpus ID 123456 01/01/2026 p. 1'},[doc])==[]
    assert reviewed_source({'source':'Fundos.NET ID 123456 01/01/2026 p. 9'},[doc])[0]['page']=='9'


def test_no_page_is_invented_for_legacy_text_with_identified_clause(tmp_path):
    p=tmp_path/'cached.txt'
    p.write_text('4.2. No mínimo 51% do patrimônio líquido deve ser investido em direitos creditórios.')
    doc={'id':123456,'reference_date':'2026-01-01','text_path':str(p),'classification':'regulamento','parse_status':'text_only_unverified_pages'}
    found=extract_primary_candidates([doc],[tmp_path])['allocation']
    assert found[0]['source']['page'] is None
    assert found[0]['source']['clause']=='4.2'
    assert found[0]['source']['verification']=='cached_primary_text_clause_pdf_not_local'


def test_document_pages_are_preserved_and_latest_full_version_wins(tmp_path):
    p=tmp_path/'current.txt'
    p.write_text(('\f'*80)+'4.2. No mínimo 51% do patrimônio líquido deve ser investido em direitos creditórios.\f')
    doc={'id':123456,'reference_date':'2026-03-20','text_path':str(p),'classification':'regulamento','parse_status':'complete'}
    records=extract_primary_candidates([doc],[tmp_path])['allocation']
    selected,_=choose_passages(records,'allocation')
    assert selected[0]['source']['page']==81
    assert selected[0]['source']['clause']=='4.2'


def test_missing_documents_leave_applicability_unresolved():
    fund=build_fund('11111111000111','A',{'documents':[]},{},[])
    assert all(c['status']=='document_not_obtained' for c in fund['criteria'])
    assert all(c['applicability']=='unresolved' for c in fund['criteria'])


def test_lookthrough_requires_invested_role_and_never_infers_weight():
    criteria=[{'criterion_id':'receivables','status':'confirmed','value':'FIC-FIDC: mezanino do Mercado Crédito II (CNPJ 41.970.012/0001-26)','sources':[{'page':11}]}]
    relation=documented_lookthrough('55563624000109',criteria)[0]
    assert relation['cnpj']=='41970012000126'
    assert relation['subclass']=='Mezanino'
    assert relation['weight_pct'] is None
    criteria[0]['value']='Cotas de fundos. Administrador Banco X CNPJ 41.970.012/0001-26'
    assert not documented_lookthrough('55563624000109',criteria)


def regulation(tmp_path, ident, date, clause, *, classification='regulamento', scope=None):
    path=tmp_path/f'{ident}.txt'
    path.write_text(clause+'\f'*5)
    return {'id':ident,'classification':classification,'title':'Regulamento' if classification=='regulamento' else 'Anexo ao Regulamento',
            'reference_date':date,'provider_status':'AC','parse_status':'complete','text_path':str(path),'fund_or_class_name':scope}


def criterion(payload, ident='allocation'):
    return next(row for row in payload['criteria'] if row['criterion_id']==ident)


def test_current_regulation_without_answer_does_not_resurrect_old_clause(tmp_path):
    old=regulation(tmp_path,123456,'01/01/2025','4.2. A Classe deverá manter no mínimo50% do patrimônio líquido em direitos creditórios.')
    new=regulation(tmp_path,234567,'01/01/2026','1.1. A Classe tem responsabilidade limitada e duração indeterminada.')
    result=criterion(build_fund('11111111000111','A',{'documents':[old,new]},{},[tmp_path]))
    assert result['status']=='clause_not_found'
    assert result['value']==''
    assert not result['sources']
    assert any(item['source']['document_id']=='123456' and '50%' in item['value'] for item in result['history'])


def test_previous_review_fallback_obeys_current_document_guard(tmp_path):
    old=regulation(tmp_path,123456,'01/01/2025','1.1. A Classe tem responsabilidade limitada.')
    new=regulation(tmp_path,234567,'01/01/2026','1.1. A Classe tem responsabilidade limitada.')
    review={'facts':{'comparison_eligibility':{'Alocação mínima':{'value':'Direitos creditórios: no mínimo50% do patrimônio líquido.',
            'source':'Fundos.NET ID123456 01/01/2025 p.1'}}}}
    result=criterion(build_fund('11111111000111','A',{'documents':[old,new]},review,[tmp_path]))
    assert result['value']==''
    assert result['status']=='clause_not_found'
    assert result['history'][0]['provenance']=='previous_review_with_primary_locator'


def test_current_general_regulation_remains_available_beside_newer_class_annex(tmp_path):
    general=regulation(tmp_path,123456,'01/01/2025','13.1. A Classe pagará taxa de administração de0,20% ao ano sobre patrimônio líquido.')
    annex=regulation(tmp_path,234567,'01/01/2026','1.1. Classe A fechada com responsabilidade limitada.',classification='anexo',scope='Classe A')
    result=criterion(build_fund('11111111000111','A',{'documents':[general,annex]},{},[tmp_path]),'admin_fee')
    assert result['status']=='confirmed'
    assert result['sources'][0]['document_id']=='123456'
    assert 'vigência jurídica' in result['precedence']


def test_annex_versions_are_guarded_within_their_own_class_scope(tmp_path):
    old=regulation(tmp_path,123456,'01/01/2025','4.2. A Classe deverá manter no mínimo50% do patrimônio líquido em direitos creditórios.',classification='anexo',scope='Classe A')
    other=regulation(tmp_path,234567,'01/01/2026','1.1. Classe B fechada com responsabilidade limitada.',classification='anexo',scope='Classe B')
    result=criterion(build_fund('11111111000111','A',{'documents':[old,other]},{},[tmp_path]))
    assert result['status']=='confirmed'
    assert result['sources'][0]['document_id']=='123456'


def test_manual_old_answer_is_preserved_without_promotion_when_current_is_silent(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'ROOT',tmp_path)
    old=regulation(tmp_path,123456,'01/01/2025','4.2. A Classe deverá manter no mínimo50% do patrimônio líquido em direitos creditórios.')
    new=regulation(tmp_path,234567,'01/01/2026','1.1. A Classe tem responsabilidade limitada.')
    override=tmp_path/'data/documentary_diligence/verified_overrides/11111111000111.json'
    override.parent.mkdir(parents=True)
    override.write_text(json.dumps({'criteria':[{'criterion_id':'allocation','status':'confirmed','applicability':'applicable','value':'Direitos creditórios≥50% do patrimônio líquido.',
            'sources':[{'document_id':123456,'reference_date':'01/01/2025','page':'1'}]}]}))
    result=criterion(build_fund('11111111000111','A',{'documents':[old,new]},{},[tmp_path]))
    assert result['value']==''
    assert result['status']=='clause_not_found'
    assert result['manual_review']['value'].endswith('patrimônio líquido.')
    assert any(item['provenance']=='verified_override' for item in result['history'])


def test_manual_numeric_difference_from_current_same_scope_is_explicit(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'ROOT',tmp_path)
    old=regulation(tmp_path,123456,'01/01/2025','4.2. A Classe deverá manter no mínimo50% do patrimônio líquido em direitos creditórios.')
    new=regulation(tmp_path,234567,'01/01/2026','4.2. A Classe deverá manter no mínimo60% do patrimônio líquido em direitos creditórios.')
    override=tmp_path/'data/documentary_diligence/verified_overrides/11111111000111.json'
    override.parent.mkdir(parents=True)
    override.write_text(json.dumps({'criteria':[{'criterion_id':'allocation','status':'confirmed','applicability':'applicable','value':'Direitos creditórios≥50% do patrimônio líquido.',
            'sources':[{'document_id':123456,'reference_date':'01/01/2025','page':'1'}],
            'rule':{'operator':'>=','limit':50.0,'unit':'percent','numerator':'credit_rights','denominator':'net_asset_value','layer':'11111111000111'}}]}))
    result=criterion(build_fund('11111111000111','A',{'documents':[old,new]},{},[tmp_path]))
    assert result['status']=='version_conflict'
    assert '60%' in result['value']
    assert result['rule']=={}
    assert result['manual_review']['rule']['limit']==50.0


def test_current_unobtained_regulation_does_not_use_readable_old_text(tmp_path):
    old=regulation(tmp_path,123456,'01/01/2025','4.2. A Classe deverá manter no mínimo50% do patrimônio líquido em direitos creditórios.')
    new=dict(old,id=234567,reference_date='01/01/2026',text_path='',parse_status='not_downloaded',download_status='inventory_only')
    result=criterion(build_fund('11111111000111','A',{'documents':[old,new]},{},[tmp_path]))
    assert result['status']=='document_not_obtained'
    assert result['value']==''
    assert '234567' in result['reason']
    assert result['history']


def test_lookthrough_excludes_reverse_ownership_and_provider_cnpj():
    row={'criterion_id':'investee','status':'confirmed','sources':[{'document_id':123456,'page':1}],
         'value':'As cotas subordinadas devem ser de titularidade do FIC FIDC Azul, CNPJ26.812.192/0001-24.'}
    assert not documented_lookthrough('11111111000111',[row])
    row['value']='Cotas de outros FIDCs. Administrador Fiduciário: Banco Daycoval S.A., CNPJ62.232.889/0001-90.'
    assert not documented_lookthrough('11111111000111',[row])


def test_index_only_contains_declared_funds_and_reachable_exact_permissions(tmp_path):
    parent='11111111000111';child='22222222000122';provider='33333333000133'
    directory=tmp_path/'funds';directory.mkdir()
    source={'document_id':123456,'page':1}
    for cnpj,relations in [(parent,[{'cnpj':child,'relationship':'permitted_mandate','sources':[source]},
                                  {'cnpj':provider,'relationship':'provider','sources':[source]}]),(child,[]),(provider,[])]:
        (directory/f'{cnpj}.json').write_text(json.dumps({'cnpj':cnpj,'lookthrough':relations}))
    indexed=builder.reachable_fund_index(tmp_path,{parent:'Parent'})
    assert set(indexed)=={parent,child}
    assert (directory/f'{provider}.json').exists()


def test_public_builder_outputs_remove_personal_paths_and_preserve_local_corpus(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'ROOT',tmp_path)
    cnpj='11111111000111';base=tmp_path/'data/documentary_diligence';(base/'corpus').mkdir(parents=True)
    corpus={'cnpj':cnpj,'documents':[{'id':123456,'classification':'regulamento','local_path':'/Users/private/source.pdf','text_path':'/Users/private/source.txt'}],
            'searches':[{'source':'local','url':'/Users/private/cache'}]}
    (base/'corpus'/f'{cnpj}.json').write_text(json.dumps(corpus))
    (base/'baseline.json').write_text('{}')
    (tmp_path/'portfolios.json').write_text(json.dumps({'portfolios':[{'id':'p','name':'P','funds':[{'cnpj':cnpj,'display_name':'A'}]}]}))
    monkeypatch.setattr(builder.sys,'argv',['builder','--all','--source-root',str(tmp_path)])
    builder.main()
    assert '/Users/private' not in (base/'funds'/f'{cnpj}.json').read_text()
    assert '/Users/private' not in (base/'audit_corpus'/f'{cnpj}.json').read_text()
    assert '/Users/private' in (base/'corpus'/f'{cnpj}.json').read_text()


def test_current_document_locator_never_promotes_legacy_synthesis_without_primary_support(tmp_path):
    doc=regulation(tmp_path,123456,'01/01/2026','1.1. Classe fechada com responsabilidade limitada.')
    review={'facts':{'comparison_eligibility':{'Alocação mínima':{'value':'No mínimo90% do patrimônio líquido em direitos creditórios.',
            'source':'Fundos.NET ID123456 01/01/2026 p.1'}}}}
    result=criterion(build_fund('11111111000111','A',{'documents':[doc]},review,[tmp_path]))
    assert result['status']=='clause_not_found'
    assert result['value']==''
    assert result['history'][0]['value'].startswith('No mínimo90%')


def test_current_primary_rule_wins_over_unverified_legacy_number(tmp_path):
    doc=regulation(tmp_path,123456,'01/01/2026','4.2. A Classe deverá manter no mínimo50% do patrimônio líquido em direitos creditórios.')
    review={'facts':{'comparison_eligibility':{'Alocação mínima':{'value':'No mínimo90% do patrimônio líquido em direitos creditórios.',
            'source':'Fundos.NET ID123456 01/01/2026 p.1'}}}}
    result=criterion(build_fund('11111111000111','A',{'documents':[doc]},review,[tmp_path]))
    assert result['status']=='confirmed'
    assert '50%' in result['value']
    assert '90%' not in result['value']
    assert result['provenance']=='primary_passage'


def test_adjacent_priority_list_is_kept_with_its_operative_clause():
    parts=list(builder.paragraphs('6.1. Os recursos serão alocados na seguinte ordem de prioridade:\n\n(i) pagamento de encargos e despesas da Classe;\n\n(ii) constituição de reserva de despesas para os seis meses seguintes;\n\n(iii) pagamento de amortização das cotas seniores;\n\n7.1. As cotas terão valor calculado diariamente.'))
    assert len(parts)==2
    assert '(iii) pagamento de amortização' in parts[0]


def test_long_priority_list_is_not_truncated_to_an_incomplete_claim():
    text='6.1. Os recursos serão alocados na seguinte ordem de prioridade: '+('(i) pagamento de encargos e despesas antes de qualquer outro pagamento; '*40)
    assert builder.brief_clause('waterfall',text)==''


def quarterly_fixture(tmp_path,cnpj,*,ident='123456',status='parsed',identity=True,source_type='quarterly_pdf',text=None):
    base=tmp_path/'data/documentary_diligence'
    path=base/'quarterly'/cnpj/f'{ident}.json';path.parent.mkdir(parents=True,exist_ok=True)
    source={'type':source_type,'document_id':ident,'reference_date':'06/2026','version':1,'url':f'https://example.com/{ident}','sha256':'a'*64,'identity_verified':identity}
    payload={'cnpj':cnpj,'quarter':'2026-Q2','competence':'06/2026','status':status,'parse_status':'complete','source':source,'identity':{'expected_cnpj':cnpj},
             'pages':[{'page':1,'text':text or 'Sobre os resultados da última verificação do lastro.\n\nNão foram identificadas inconsistências significativas na documentação dos direitos creditórios.'}],
             'fields':[],'error':'Falha da retificação' if status!='parsed' else ''}
    path.write_text(json.dumps(payload))
    inventory={'cnpjs':{cnpj:{'by_quarter':{'2026-Q2':{'effective_document_id':ident}},'documents':{ident:{'path':str(path.relative_to(base))}}}}}
    return inventory,path,payload


def test_quarterly_pdf_observation_has_physical_page_and_stays_outside_regulatory_criteria(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'ROOT',tmp_path)
    cnpj='11111111000111';inventory,_,_=quarterly_fixture(tmp_path,cnpj)
    result=build_fund(cnpj,'A',{'documents':[]},{},[tmp_path],quarterly_inventory=inventory)
    record=result['quarterly_observations']['records'][0]
    assert record['status']=='reported'
    assert record['criterion_id']=='collateral_check'
    assert record['source']['page']=='1'
    assert 'xpath' not in record['source']
    assert 'Não foram identificadas' in record['value']
    assert criterion(result,'collateral_check')['status']=='document_not_obtained'


def test_quarterly_effective_failed_revision_never_falls_back_to_older_parsed_document(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'ROOT',tmp_path)
    cnpj='11111111000111'
    _,old_path,_=quarterly_fixture(tmp_path,cnpj,ident='111111')
    inventory,_,_=quarterly_fixture(tmp_path,cnpj,ident='222222',status='parse_error')
    inventory['cnpjs'][cnpj]['documents']['111111']={'path':str(old_path.relative_to(tmp_path/'data/documentary_diligence'))}
    result=builder.load_quarterly_observations(cnpj,inventory)
    assert result['status']=='unavailable'
    assert result['records']==[]
    assert result['document_id']=='222222'
    assert result['reason']=='Falha da retificação'


def test_quarterly_identity_failure_is_not_promoted(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'ROOT',tmp_path)
    cnpj='11111111000111';inventory,_,_=quarterly_fixture(tmp_path,cnpj,identity=False)
    assert builder.load_quarterly_observations(cnpj,inventory)['status']=='unavailable'


def test_quarterly_xml_observation_uses_literal_xpath_and_preserves_declared_zero(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'ROOT',tmp_path)
    cnpj='11111111000111';inventory,path,payload=quarterly_fixture(tmp_path,cnpj,source_type='quarterly_xml')
    payload['fields']=[{'xpath':'/Informe/ResultadoVerificacaoLastro/QuantidadeInconsistencias','tag':'QuantidadeInconsistencias','text':'0','value':0}]
    path.write_text(json.dumps(payload))
    result=builder.load_quarterly_observations(cnpj,inventory)
    record=result['records'][0]
    assert record['value']=='0'
    assert record['status']=='reported_raw'
    assert record['source']['xpath']=='/Informe/ResultadoVerificacaoLastro/QuantidadeInconsistencias'
    assert 'page' not in record['source']


def test_quarterly_precatorio_statement_and_prohibition_form_documentary_conflict(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'ROOT',tmp_path)
    cnpj='11111111000111';inventory,_,_=quarterly_fixture(tmp_path,cnpj,text='Sobre a aquisição de precatórios federais.\n\nO fundo adquiriu precatórios federais no trimestre em referência.')
    override=tmp_path/'data/documentary_diligence/verified_overrides'/f'{cnpj}.json';override.parent.mkdir(parents=True)
    override.write_text(json.dumps({'criteria':[{'criterion_id':'concentration','label':'Concentração','theme':'Recebíveis','status':'confirmed','applicability':'applicable',
        'value':'Aquisição de precatórios federais vedada.','sources':[{'document_id':234567,'reference_date':'01/06/2026','page':'7','clause':'4.15'}]}]}))
    result=build_fund(cnpj,'A',{'documents':[]},{},[tmp_path],quarterly_inventory=inventory)
    record=result['quarterly_observations']['records'][0]
    assert record['status']=='documentary_conflict'
    assert len(record['sources'])==2
    assert 'Operação efetiva' in record['risk_note']
    assert criterion(result,'concentration')['status']=='confirmed'
