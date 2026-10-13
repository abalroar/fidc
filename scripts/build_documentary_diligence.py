#!/usr/bin/env python3
"""Build auditable credit comparisons without copying the primary PDF corpus.

Each fund is processed separately. Previous reviews remain archival evidence;
current primary passages and verified analyst overrides provide answers.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import unicodedata
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BUILD_REVISION = 6
EXTRACTOR_REVISION=sha256(Path(__file__).read_bytes()).hexdigest()
sys.path.insert(0, str(ROOT))
from services.documentary_criteria_catalog import CRITERIA, LEGACY_MAP
from services.documentary_clause_validation import validate_primary_clause, validation_fingerprint
from services.documentary_corpus import current_document_ids
VALIDATOR_REVISION=validation_fingerprint()


def fold(value):
    text=''.join(c for c in unicodedata.normalize('NFKD', str(value)) if not unicodedata.combining(c)).casefold()
    return re.sub(r'\s+', ' ',text).strip()


def iso_date(value):
    value = str(value or '')
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', value)
    if match:
        return match.group(0)
    match = re.search(r'(\d{2})/(\d{2})/(\d{4})', value)
    return f'{match[3]}-{match[2]}-{match[1]}' if match else ''


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def read_json(path, default=None):
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding='utf-8'))


def load_quarterly_inventory():
    base=ROOT/'data/documentary_diligence'
    private=base/'quarterly_index.json'
    return read_json(private if private.exists() else base/'audit_quarterly_index.json')


def load_documentary_corpus(cnpj):
    base=ROOT/'data/documentary_diligence'
    private=base/'corpus'/f'{cnpj}.json'
    return read_json(private if private.exists() else base/'audit_corpus'/f'{cnpj}.json')


def resolve_path(path, roots):
    if not path:
        return None
    p = Path(path)
    if p.is_absolute():
        return p if p.is_file() else None
    return next((r / p for r in roots if (r / p).is_file()), None)


def document_id(doc):
    return str(doc.get('id') or doc.get('document_id') or '')


def normative_scope(doc):
    category = doc.get('classification')
    # The corpus selects one consolidated general regulation, while annexes
    # remain independent by class scope. A class annex does not retire the
    # current general regulation merely because it has a later date.
    scope = fold(doc.get('fund_or_class_name') or doc.get('scope') or 'unspecified_class') if category == 'anexo' else 'general_regulation'
    return category, scope


def version_context(documents):
    normalized = [dict(doc, id=document_id(doc)) for doc in documents if document_id(doc).isdigit()]
    current_ids = current_document_ids(normalized)
    by_id = {document_id(doc): doc for doc in documents if document_id(doc)}
    current = [doc for doc in documents if document_id(doc) in current_ids]
    superseded = {}
    for doc in documents:
        ident = document_id(doc)
        if doc.get('classification') not in {'regulamento', 'anexo'} or ident in current_ids:
            continue
        successors = [new for new in current if normative_scope(new) == normative_scope(doc)]
        if successors:
            superseded[ident] = successors
    return {'current_ids': current_ids, 'current_documents': current, 'by_id': by_id, 'superseded': superseded}


def partition_sources(sources, context):
    available, historical = [], []
    for source in sources:
        (historical if str(source.get('document_id')) in context['superseded'] else available).append(source)
    return available, historical


def historical_answer(value, sources, assessment, *, provenance='primary_passage'):
    return {'reference_date': max((source.get('reference_date') or '' for source in sources), default=''),
            'value': value, 'sources': sources, 'source': sources[0] if sources else {},
            'assessment': assessment, 'provenance': provenance}


def compact_history_payload(payload, *, preview_limit=3, existing_history=None):
    """Move historical text to a portable, deduplicated file for deferred reads.

    The ordinary fund JSON has at most three short history previews per
    criterion. Every original historical value and passage is retained in the
    sidecar. This storage conversion does not retrospectively validate it.
    Current rule sources are deliberately untouched.
    """
    cnpj=payload['cnpj']
    path=f'history/{cnpj}.json'
    sidecar={'schema_version':1,'cnpj':cnpj,
             'scope':'Material histórico preservado; não houve revisão retrospectiva integral nem certificação de vigência jurídica.',
             'criteria':{},'entries':{},'passages':{}}
    if existing_history and existing_history.get('cnpj')==cnpj:
        for name in ('criteria','entries','passages'):
            sidecar[name]=dict(existing_history.get(name) or {})

    def digest(value):
        return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

    def store_source(source):
        source=dict(source)
        excerpt=str(source.get('excerpt') or '')
        key=digest({'document_id':str(source.get('document_id') or ''),
                    'page':source.get('page'),'clause':source.get('clause'),
                    'excerpt_sha256':sha256(excerpt.encode()).hexdigest()})
        sidecar['passages'].setdefault(key,source)
        allowed={'document_id','title','url','reference_date','version','page','clause','sha256','verification','identity_verified','xpath'}
        compact={name:value for name,value in source.items() if name in allowed and value not in (None,'')}
        compact.update(passage_id=key,excerpt_sha256=sha256(excerpt.encode()).hexdigest())
        return key,compact

    def store_entry(original):
        original=dict(original)
        sources=original.get('sources') or ([original['source']] if original.get('source') else [])
        references=[]
        compact_sources=[]
        for source in sources:
            key,compact=store_source(source)
            if key not in references:
                references.append(key)
                compact_sources.append(compact)
        entry={name:value for name,value in original.items() if name not in {'source','sources'}}
        entry['sources']=references
        ident=digest(entry)
        sidecar['entries'].setdefault(ident,entry)
        value=str(original.get('value') or '')
        preview={'history_id':ident,'history_path':path,
                 'reference_date':original.get('reference_date') or '',
                 'value':value[:320]+('…' if len(value)>320 else ''),
                 'value_truncated':len(value)>320,'sources':compact_sources,
                 'assessment':str(original.get('assessment') or '')[:320],
                 'provenance':original.get('provenance') or ''}
        return ident,preview

    for item in payload.get('criteria') or []:
        historical=item.get('history') or []
        # A previous build may already be compact. Its full sidecar is kept by
        # the main resume path, rather than rebuilding from shortened previews.
        if historical and all(record.get('history_path') and record.get('history_id') for record in historical):
            continue
        previous_ids=sidecar['criteria'].pop(item['criterion_id'],[])
        has_compact=any(record.get('history_path') and record.get('history_id') for record in historical)
        identities=list(previous_ids) if has_compact else []
        previews=[]
        for original in historical:
            if original.get('history_path') and original.get('history_id'):
                if original['history_id'] not in identities:
                    identities.append(original['history_id'])
                previews.append(original)
                continue
            ident,preview=store_entry(original)
            if ident not in identities:
                identities.append(ident)
                previews.append(preview)
        manual=item.get('manual_review')
        if manual and not manual.get('history_path'):
            original=dict(manual,assessment='Leitura manual anterior preservada; documento atual não confirmou sua continuidade jurídica.',provenance='verified_override')
            ident,preview=store_entry(original)
            if ident not in identities:
                identities.append(ident)
            item['manual_review']=preview
        if not identities:
            continue
        sidecar['criteria'][item['criterion_id']]=identities
        previews.sort(key=lambda record:iso_date(record['reference_date']),reverse=True)
        item['history']=previews[:preview_limit]
        item['history_count']=len(identities)
        item['history_ref']={'path':path,'criterion_id':item['criterion_id'],
                             'total_count':len(identities),'preview_count':len(item['history']),
                             'full_text_deferred':True}
    retained={ident for references in sidecar['criteria'].values() for ident in references}
    sidecar['entries']={ident:entry for ident,entry in sidecar['entries'].items() if ident in retained}
    passages={ident for entry in sidecar['entries'].values() for ident in entry.get('sources') or []}
    sidecar['passages']={ident:source for ident,source in sidecar['passages'].items() if ident in passages}
    if not sidecar['entries']:
        return None
    return sidecar


def corpus_revision(corpus):
    return sha256(json.dumps(corpus.get('documents') or [],sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def validator_revision():
    """A resume must not keep answers accepted by an older semantic validator."""
    # Freeze the fingerprint beside the imported implementation: a file edit
    # during a long batch must not label the old in-memory validator as new.
    return VALIDATOR_REVISION


def processing_revisions_current(payload,criterion_ids):
    return all((payload.get('criterion_revisions') or {}).get(ident)==validator_revision()
               and (payload.get('criterion_extractor_revisions') or {}).get(ident)==EXTRACTOR_REVISION
               for ident in criterion_ids)


def criterion_anchors(ident,anchors):
    aliases={'providers':('administrado','gerido'),
             'originator':('cedente','endossante'),
             'receivables':('financiamentos estudantis','financiamento de matrículas','instrumentos de concessão de crédito'),
             'pdd':('perdas estimadas em créditos','perdas estimadas em crédito','créditos de liquidação duvidosa','perdas por redução')}
    return tuple(anchors)+aliases.get(ident,())


def override_revision(cnpj):
    path=ROOT/'data/documentary_diligence/verified_overrides'/f'{cnpj}.json'
    return sha256(path.read_bytes() if path.exists() else b'').hexdigest()


def partial_override_change_safe(cached, criterion_ids, cnpj):
    """A target-only analyst correction need not re-extract unrelated rows.

    A changed graph or any override outside this batch still requires the full
    path. This also protects removals of previously applied, untargeted work.
    """
    override=read_json(ROOT/'data/documentary_diligence/verified_overrides'/f'{cnpj}.json')
    if any(key in override for key in ('lookthrough','excluded_candidates','excluded_relationship_candidates','identity_mappings')):
        return False
    requested=set(criterion_ids)
    replacement_ids={row.get('criterion_id') for row in override.get('criteria') or []}
    applied_ids={row.get('criterion_id') for row in cached.get('criteria') or [] if row.get('provenance')=='verified_override' or row.get('manual_review')}
    return replacement_ids<=requested and applied_ids<=requested


QUARTER_TOPICS = (
    ('collateral_check','Resultado da verificação de lastro',r'lastro|verificacao.*document',r'LASTRO|RESULT.*VERIFIC.*DOCUMENT'),
    ('registration','Registro dos direitos creditórios',r'registro.*direitos? cred',r'REGISTRO.*DIREIT|DIREIT.*REGISTRO'),
    ('litigation','Processos judiciais',r'processos? judicia|acoes? judicia',r'PROCESSO.*JUDICI|ACAO.*JUDICI'),
    ('precatórios','Aquisição de precatórios',r'aquisicao.*precatorio',r'AQUISIC.*PRECATOR'),
    ('investment_changes','Alterações da política de investimento',r'alteracao.*politica.*invest|politica.*invest.*rentabilidade',r'ALTERAC.*POLITICA.*INVEST'),
    ('origination_policy','Critérios de concessão dos originadores',r'criterios?.*concessao|concessao.*originador',r'CRITERIO.*CONCESS|CONCESS.*ORIGIN'),
    ('guarantee_changes','Alterações das garantias',r'garantias? existentes|alteracao.*garantia',r'ALTERAC.*GARANT|GARANT.*ALTERAC'),
    ('discontinued_origination','Descontinuidade de originação ou cessão',r'descontinuidade.*origin|descontinuidade.*cess',r'DESCONTIN.*ORIGIN|DESCONTIN.*CESS'),
    ('cession','Cessões no trimestre',r'cessao.*direitos? cred|cessoes.*periodo',r'CESSAO.*DIREIT|CESSOES.*PERIODO'),
    ('prepayment','Eventos de pré-pagamento',r'pre.?pagamento',r'PREPAGAMENTO'),
    ('asset_sale','Alienação de direitos creditórios',r'alienacao.*direitos? cred|condicoes.*alienacao',r'ALIENAC.*DIREIT|CONDIC.*ALIENA'),
    ('provider_changes','Alterações de prestadores',r'alteracao.*prestador|substituicao.*(?:gestor|administrad|custod)',r'ALTERAC.*PRESTADOR|SUBSTIT.*GESTOR|SUBSTIT.*ADMINISTR|SUBSTIT.*CUSTOD'),
    ('conflicts','Conflitos de interesses reportados',r'conflito.*interesse',r'CONFLITO.*INTERESSE'),
)


def quarterly_revision(cnpj,inventory):
    return sha256(json.dumps((inventory.get('cnpjs') or {}).get(cnpj) or {},sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def quarterly_topic_header(text):
    normalized=fold(text)
    normalized=re.sub(r'^\(?[a-z0-9]+\)?[.)–-]\s*','',normalized)
    if len(normalized)>550 or re.match(r'^(?:nao foram|foram observ|ocorreram|de acordo|o fundo|a classe|os criterios)',normalized):
        return None
    if not re.match(r'^(?:sobre|criterios|impactos|resultados|registro|existencia|aquisicao|alteracao|garantias|cessao|condicoes|descontinuidade|processos|conflitos)',normalized):
        return None
    return next((topic for topic in QUARTER_TOPICS if re.search(topic[2],normalized)),None)


def quarterly_pdf_records(document):
    blocks=[]
    active=None
    for page in document.get('pages') or []:
        for paragraph in re.split(r'\n\s*\n',page.get('text') or ''):
            paragraph=re.sub(r'\s+',' ',paragraph).strip()
            if not paragraph:
                continue
            normalized=fold(paragraph)
            if re.match(r'^(?:btgpactual\.com|sac:|ouvidoria:|clicksign|sendo o que|atenciosamente)',normalized):
                active=None
                continue
            topic=quarterly_topic_header(paragraph)
            if topic:
                active={'topic':topic,'heading':paragraph,'first_page':page['page'],'last_page':page['page'],'body':[]}
                blocks.append(active)
            elif active:
                active['body'].append(paragraph)
                active['last_page']=page['page']
    records=[]
    for block in blocks:
        value=' '.join(block['body'])
        if not value:
            continue
        ident,label,_,_=block['topic']
        location=str(block['first_page']) if block['first_page']==block['last_page'] else f"{block['first_page']}–{block['last_page']}"
        source=dict(document['source'],page=location,clause=block['heading'],excerpt=block['heading']+' '+value)
        source.pop('xpath',None)
        ambiguous=bool(re.search(r'\[(?:\s|x|X|●)*\]|☐|☑|□|■|\(\s*(?:sim|nao)\s*\)',value,re.I))
        if len(value)>1600 or ambiguous:
            records.append({'criterion_id':ident,'label':label,'status':'extraction_pending','value':'','source':source,
                            'reason':'Resposta extensa ou com seleção de opções não verificada; transcrição disponível na fonte, sem inferir o resultado.'})
            continue
        risk=''
        if value.rstrip().endswith(':'):
            risk='O informe anuncia uma lista, mas não apresenta os itens neste trecho.'
        records.append({'criterion_id':ident,'label':label,'status':'reported','value':value,'source':source,'risk_note':risk})
    return records


def quarterly_xml_records(document):
    records=[]
    for field in document.get('fields') or []:
        literal=field.get('text') if field.get('text') is not None else field.get('value')
        value=str(literal if literal is not None else '').strip()
        xpath=str(field.get('xpath') or '')
        if not xpath or not value:
            continue
        topic=next((topic for topic in QUARTER_TOPICS if re.search(topic[3],xpath,re.I)),None)
        if not topic:
            continue
        ident,label,_,_=topic
        source=dict(document['source'],xpath=xpath,excerpt=value)
        source.pop('page',None)
        records.append({'criterion_id':ident,'label':label,'status':'reported_raw','value':value,'source':source,
                        'risk_note':'Valor literal do campo XML; códigos não são convertidos em conclusões ou limites jurídicos.'})
    return records


def load_quarterly_observations(cnpj,inventory=None):
    base=ROOT/'data/documentary_diligence'
    inventory=load_quarterly_inventory() if inventory is None else inventory
    entry=(inventory.get('cnpjs') or {}).get(cnpj) or {}
    by_quarter=entry.get('by_quarter') or {}
    if not by_quarter:
        return {'status':'unavailable','quarter':None,'competence':None,'document_id':None,'source':{},'records':[],
                'reason':entry.get('error') or 'Nenhum informe trimestral efetivo com identidade verificada disponível nesta rodada.'}
    quarter=max(by_quarter)
    ident=str(by_quarter[quarter].get('effective_document_id') or '')
    metadata=(entry.get('documents') or {}).get(ident) or {}
    relative=metadata.get('path') or f'quarterly/{cnpj}/{ident}.json'
    path=(base/relative).resolve()
    if not path.is_relative_to((base/'quarterly'/cnpj).resolve()):
        return {'status':'unavailable','quarter':quarter,'document_id':ident,'records':[],'source':{},'reason':'Referência do informe fora do diretório do CNPJ solicitado.'}
    document=read_json(path)
    source=document.get('source') or metadata.get('source') or {}
    output={'status':'unavailable','quarter':quarter,'competence':document.get('competence'),'document_id':ident,'source':source,'records':[],
            'identity':document.get('identity') or metadata.get('identity') or {},
            'reason':document.get('error') or metadata.get('error') or 'Informe efetivo sem processamento e identidade confirmados; não foi substituído por uma versão anterior.'}
    if document.get('status')!='parsed' or source.get('identity_verified') is not True or document.get('cnpj')!=cnpj or document.get('quarter')!=quarter or str(source.get('document_id'))!=ident:
        return output
    if source.get('type')=='quarterly_pdf' and document.get('parse_status')!='complete':
        return output
    records=quarterly_pdf_records(document) if source.get('type')=='quarterly_pdf' else quarterly_xml_records(document) if source.get('type')=='quarterly_xml' else []
    output.update(status='reported' if records else 'no_mapped_observations',records=records[:32],reason='',
                  evidence_basis='Declarações do informe trimestral; não substituem o regulamento nem comprovam verificação independente.',
                  record_count_available=len(records),records_limit=32)
    if not records:
        output['reason']='Informe processado com identidade verificada, sem campo/resposta de eventos e verificação reconhecido neste formato. Não equivale à inexistência de eventos.'
    return output


def primary_source(doc, *, page=None, clause='', excerpt=''):
    ident = str(doc.get('id') or doc.get('document_id') or '')
    source={
        'document_id': ident, 'title': doc.get('title') or doc.get('classification') or 'Documento primário',
        'url': doc.get('url') or (f'https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id={ident}&cvm=true' if ident.isdigit() else ''),
        'reference_date': iso_date(doc.get('reference_date') or doc.get('data_referencia')),
        'version': str(doc.get('version') or doc.get('versao') or ''), 'page': page,
        'clause': clause, 'excerpt': excerpt, 'sha256': doc.get('sha256') or '',
        'local_path': doc.get('local_path') or doc.get('source_file') or '',
        'text_path': doc.get('text_path') or '',
        'verification': 'primary_passage' if excerpt else 'previous_review',
    }
    if doc.get('parse_method'):
        source['parse_method']=doc['parse_method']
    if 'ocr' in str(doc.get('parse_method') or '').casefold():
        source['verification']='ocr_primary_passage'
        source['ocr_excluded_pages']=doc.get('ocr_excluded_pages') or []
        quality=doc.get('ocr_quality') or doc.get('ocr_page_quality') or {}
        if isinstance(quality,dict):
            entries=quality.get('pages') or quality.get('page_quality') or quality
            aggregate={key:value for key,value in quality.items() if isinstance(value,(str,int,float,bool))}
        else:
            entries=quality
            aggregate={}
        if isinstance(entries,dict):
            page_quality=entries.get(str(page)) or entries.get(page)
        elif isinstance(entries,list):
            page_quality=next((item for item in entries if isinstance(item,dict) and str(item.get('page') or item.get('page_number'))==str(page)),None)
        else:
            page_quality=None
        source['ocr_quality']={'page':page,'page_quality':page_quality,'aggregate':aggregate}
        source['review_scope']='Texto reconhecido por OCR da página física; não certifica conferência humana de cada número.'
    return source


MISSING = re.compile(r'nao (?:localiz|identific|valid|confirm|obt|extra|acess|transcrit)|sem (?:documento|corpus|acesso|informacao)|requerem regulamento|exigem document|precisa de|a confirmar|divergencia documental|selecionar competencia', re.I)
REMISSION = re.compile(r'^(?:conforme|ver |vide |remetid|definid[oa] em|sobretaxa definida|spread final)', re.I)


def material_answer(value):
    text = fold(value).strip()
    if not text or text in {'-', '—', 'n/d', 'nan', 'none'}:
        return False
    # Mixed answers keep their factual sentence; qualifications stay separately.
    parts = re.split(r';\s*|\.\s+(?=[A-ZÁÉÍÓÚ])', str(value))
    return any(not MISSING.search(fold(p)) and not REMISSION.search(fold(p)) and len(p.strip()) > 9 for p in parts)


def source_locator(text):
    page = re.search(r'\b(?:p\.?|pg\.?|pag(?:ina)?\.?|página)\s*(\d+(?:\s*[-–,]\s*\d+)*)', text, re.I)
    clause = re.search(r'\b(?:cl\.?|cláusula|clausula|item|art\.?)\s*(\d+(?:\.\d+)*(?:\s*\([ivx]+\))?)', text, re.I)
    return page.group(1).strip() if page else None, clause.group(1) if clause else ''


def reviewed_source(fact, documents):
    text = str(fact.get('source') or '')
    note = str(fact.get('note') or '')
    ids = re.findall(r'\bID\s*(\d{5,})', text, re.I)
    if not ids:
        ids = re.findall(r'(?:id=|/)(\d{5,})(?:[_&\s]|$)', text)
    date = iso_date(text)
    page, clause = source_locator(text + ' ' + note)
    if not ids or not date or not (page or clause) or text.startswith(('Corpus', 'Consulta', 'Inventário')):
        return []
    candidates = {str(d.get('id') or d.get('document_id')): d for d in documents}
    result = []
    for ident in dict.fromkeys(ids):
        d = candidates.get(ident)
        if not d or not (d.get('text_path') or d.get('local_path') or d.get('source_file')):
            continue
        source = primary_source(d, page=page, clause=clause)
        source['reference_date'] = source['reference_date'] or date
        source['citation_original'] = text
        result.append(source)
    return result


def paragraphs(page, *, join_alpha_lists=False):
    """Retain paragraph/list boundaries and page identity, without an 80p cut."""
    # Numbered legal clauses are essential boundaries even when Poppler sees no
    # blank line between them. Otherwise a keyword can inherit another clause's
    # percentage or a different quota's pari-passu wording.
    page=re.sub(r'(?m)^\s*(?:Este documento foi assinado|Para verificar as assinaturas|Docusign Envelope ID|Clicksign)[^\n]*','',page)
    parts = re.split(r'\n\s*\n|(?m:^\s*(?=\d{1,2}(?:\.\d{1,3})+\.?\s))|(?m:^\s*(?=[“"][^”"\n]{3,100}[”"]\s*:))', page)
    prepared=[]
    for part in parts:
        part = re.sub(r'[ \t]+', ' ', part).strip()
        if not part:
            continue
        # PDF lines wrap inside paragraphs; retain actual numbered list starts.
        part = re.sub(r'(?<![.;:])\n(?!\s*(?:\d+\.\d+|\([a-zivx]+\)|[a-z]\)))', ' ', part)
        list_item=re.match(r'^\s*(?:\([a-zivxlcdm]+\)|[a-zivxlcdm]+[.)])\s',part,re.I)
        if len(part) >= 35 or (join_alpha_lists and list_item):
            prepared.append(part)
    index=0
    while index<len(prepared):
        part=prepared[index]
        index+=1
        # Blank PDF lines can separate an operative colon from its actual
        # numbered payments. Retain that adjacent list in the same evidence.
        if part.rstrip().endswith(':'):
            parent=re.match(r'^(\d+(?:\.\d+)+)',part)
            markers=r'^\s*(?:\([ivxlcdm]+\)|[ivxlcdm]+\s*[–-])'
            if join_alpha_lists:
                markers=r'^\s*(?:\([a-zivxlcdm]+\)|[a-zivxlcdm]+[.)]\s)'
                if parent:
                    markers+='|^'+re.escape(parent[1])+r'\.\d+(?:\.\d+)*[.)]?\s'
            while index<len(prepared) and re.match(markers,prepared[index],re.I):
                part+='\n'+prepared[index]
                index+=1
        yield part


def eligibility_passages(pages, page_index, excluded_pages=()):
    """Recover adjacent conditions while retaining physical page boundaries.

    Only an eligibility/acquisition list can join following lettered or nested
    items. A new numbered clause stops it. Excluded OCR pages never supply
    text, and an unresolved continuation is marked rather than completed.
    """
    marker=re.compile(r'^\s*(?:\([a-zivxlcdm]+\)|[a-zivxlcdm]+[.)])\s',re.I)
    excluded={str(value) for value in excluded_pages}
    blocks=list(paragraphs(pages[page_index],join_alpha_lists=True))
    for part_index,part in enumerate(blocks):
        start=end=page_index+1
        parent=re.match(r'^(\d+(?:\.\d+)+)',part)
        is_list=bool(re.search(r'criterios de elegibilidade|condicoes de (?:aquisicao|cessao)',fold(part)) and ':' in part)
        complete=True
        if is_list and part.rstrip().endswith((':',';',' e')) and part_index==len(blocks)-1:
            if page_index+1>=len(pages):
                complete=False
            for next_index in range(page_index+1,min(len(pages),page_index+3)):
                if str(next_index+1) in excluded:
                    complete=False
                    break
                continuation=list(paragraphs(pages[next_index],join_alpha_lists=True))
                # Repeated document headers have no role in the clause.
                while continuation and re.match(r'^(?:anexo|regulamento|parte geral)\b',fold(continuation[0])) and not marker.match(continuation[0]):
                    header=continuation.pop(0)
                    embedded=re.search(r'(?m)^\s*(?:\([a-zivxlcdm]+\)|[a-zivxlcdm]+[.)])\s',header,re.I)
                    if embedded:
                        continuation.insert(0,header[embedded.start():].strip())
                        break
                joined=[]
                for item in continuation:
                    nested=parent and re.match(r'^'+re.escape(parent[1])+r'\.\d+(?:\.\d+)*[.)]?\s',item)
                    if not marker.match(item) and not nested:
                        break
                    if len(part)+sum(len(value) for value in joined)+len(item)>6000:
                        complete=False
                        break
                    joined.append(item)
                if not joined:
                    break
                part+='\n'+'\n'.join(joined)
                end=next_index+1
                if len(joined)<len(continuation) or part.rstrip().endswith('.'):
                    break
                if next_index==min(len(pages),page_index+3)-1 and part.rstrip().endswith((':',';',' e')):
                    complete=False
        yield part,start,end,complete


def candidate_score(criterion_id, anchors, text, *, folded=None, folded_anchors=None):
    f = fold(text) if folded is None else folded
    normalized_anchors = tuple(fold(a) for a in anchors) if folded_anchors is None else folded_anchors
    matched = [a for a in normalized_anchors if a in f]
    if not matched:
        return 0
    if len(text) > 6000:
        return 0  # A page-long collapsed table is not a safely bounded clause.
    if re.fullmatch(r'[\w\s.\d\-–]+', text) and len(text) < 90:
        return 0
    if re.search(r'(?:significa|significado atribuido|termos definidos|sumario)', f) and not re.search(r'\d\s*%|\bformula\b|\bcalculad', f):
        concrete_definition=criterion_id in {'receivables','originator','debtor','providers','investee','guarantee'} and validate_primary_clause(criterion_id,text)['valid']
        if criterion_id=='investee':
            concrete_definition=concrete_definition and bool(re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|(?<!\d)\d{14}(?!\d)',text))
        if not concrete_definition:
            return 0
    if criterion_id in {'allocation', 'tax_allocation'}:
        if not re.search(r'direitos creditorios|cotas (?:de|da|do) (?:fund|classe)', f) or not re.search(r'\d\s*%|cinquenta|sessenta e sete', f):
            return 0
        if 'cotas de classes de fundos de investimento em direitos' in f and 'significa' in f:
            return 0
    if criterion_id in {'subordination', 'coverage'} and not re.search(r'\d\s*%|formula|calculad|razao entre|quociente|relacao entre', f):
        return 0
    if criterion_id == 'subordination' and not re.search(r'(?:indice|razao|relacao|minim)[^.;\n]{0,70}subordin|subordin[^.;\n]{0,70}(?:minim|patrimonio|razao|indice)', f):
        return 0
    if criterion_id == 'ticket' and not re.search(r'direit|devedor|sacado|contrato|ccb|recebiv', f):
        return 0
    if criterion_id == 'term' and not re.search(r'direit|credito|ccb|contrato|recebiv', f):
        return 0
    if criterion_id == 'investee':
        if not re.search(r'classe investida|fundos? investidos?|cotas (?:do|da|de) (?:[a-z ]{0,40})?(?:fidc|fundo|classe)', f):
            return 0
        if re.search(r'chamadas de capital|cotista inadimplente|capital autorizado', f) and not re.search(r'classe investida|fundo investido', f):
            return 0
    if criterion_id=='payments' and re.search(r'cotista inadimplente|cotas nao integralizadas|chamadas de capital|direitos politicos', f) and not re.search(r'amortizacao|pagamento de juros',f):
        return 0
    if criterion_id == 'changes' and not re.search(r'(?:fica|passa|deliber|aprova|altera|nova redacao)', f):
        return 0
    if criterion_id.endswith('_fee'):
        if re.search(r'assembleia|competencia privativa|quorum|deliberar|criacao ou aumento', f) and not re.search(r'\d\s*%|r\$|nao (?:sera|havera|cobrada)|sem taxa de',f):
            return 0
    if criterion_id=='receivables' and re.search(r'ativos recuperados|nao representarao direitos|nao serao classificados',f):
        return 0
    # Prefer an operative numbered clause over generic headings/definitions.
    operative = bool(re.search(r'devera|deverao|sera|serao|vedad|permitid|obrig|minim|maxim|exig|poder|destinad|priorid|correspond|constitui|calculad|remuner|limit', f))
    substantive = bool(re.search(r'\d\s*(?:%|dias|meses|anos)|r\$|\b(?:sem coobrigacao|pari passu|nao sera|nao havera)', f))
    if not operative and not substantive and criterion_id not in {'originator','providers','debtor','receivables','guarantee','servicing','rating','audit'}:
        return 0
    heading = bool(re.match(r'\d+(?:\.\d+)+[.)]?\s', text))
    return len(matched) * 3 + operative * 3 + substantive * 3 + heading * 2


def extract_primary_candidates(documents, roots, criterion_ids=None):
    results = {item[0]: [] for item in CRITERIA}
    versions = version_context(documents)
    normalized_catalog = [(ident,theme,label,criterion_anchors(ident,anchors),tuple(fold(a) for a in criterion_anchors(ident,anchors)))
                          for ident,theme,label,anchors in CRITERIA if criterion_ids is None or ident in criterion_ids]
    for doc in documents:
        if doc.get('classification') in {'informe_mensal','informe_trimestral'}:
            continue
        path = resolve_path(doc.get('text_path'), roots)
        if not path:
            continue
        mapped_pages = doc.get('parse_status') in {'complete', 'partial'}
        cached_primary = doc.get('parse_status') == 'text_only_unverified_pages'
        if not mapped_pages and not cached_primary:
            continue
        # One document lives in memory. It is released before the next document.
        text = path.read_text(encoding='utf-8', errors='replace')
        pages = text.split('\f')
        full_regulation = doc.get('classification') in {'regulamento', 'anexo'} and len(pages) >= 5
        metadata = dict(doc, _full_regulation=full_regulation)
        excluded_pages={str(page) for page in doc.get('ocr_excluded_pages') or []}
        for page_no, page in enumerate(pages, 1):
            if str(page_no) in excluded_pages:
                continue
            regular_catalog=[row for row in normalized_catalog if row[0]!='eligibility']
            eligibility_catalog=[row for row in normalized_catalog if row[0]=='eligibility']
            passages=((paragraph,page_no,page_no,True,regular_catalog) for paragraph in paragraphs(page))
            if eligibility_catalog:
                from itertools import chain
                passages=chain(passages,((paragraph,start,end,complete,eligibility_catalog) for paragraph,start,end,complete in eligibility_passages(pages,page_no-1,excluded_pages)))
            for paragraph,start_page,end_page,list_complete,catalog in passages:
                clause_match = re.match(r'(\d+(?:\.\d+)+)', paragraph)
                clause = clause_match.group(1) if clause_match else ''
                if not mapped_pages and not clause:
                    continue
                folded = fold(paragraph)
                for ident, theme, label, anchors, folded_anchors in catalog:
                    if not any(anchor in folded for anchor in folded_anchors):
                        continue
                    score = candidate_score(ident, anchors, paragraph, folded=folded, folded_anchors=folded_anchors)
                    if score and validate_primary_clause(ident,paragraph)['valid']:
                        bucket = results[ident]
                        page_locator=start_page if start_page==end_page else f'{start_page}–{end_page}'
                        source = primary_source(metadata, page=page_locator if mapped_pages else None, clause=clause, excerpt=paragraph)
                        if ident=='eligibility':
                            source['list_recovery_complete']=list_complete
                        if not mapped_pages:
                            source['verification'] = 'cached_primary_text_clause_pdf_not_local'
                        record = {'score': score, 'text': paragraph, 'source': source, 'full_regulation': full_regulation, 'classification': doc.get('classification'), 'provider_status':doc.get('provider_status') or doc.get('status') or '',
                                  'current_document': document_id(doc) not in versions['superseded'], 'scope': normative_scope(doc)}
                        # Keep a bounded sample per criterion/date, not all hits.
                        bucket.append(record)
                        bucket.sort(key=lambda r:(r['current_document'],r['full_regulation'],r['source']['reference_date'],r['score']), reverse=True)
                        per_document = Counter()
                        bounded = []
                        for item in bucket:
                            per_document[item['source']['document_id']] += 1
                            if per_document[item['source']['document_id']] <= 4:
                                bounded.append(item)
                        bucket[:] = bounded
                        del bucket[32:]
        del text, pages
    return results


def choose_passages(records, ident):
    if not records:
        return [], ''
    regulation_ids = {'receivables','originator','debtor','eligibility','ticket','term','concentration','allocation','tax_allocation','perimeter','res175','subordination','coverage','junior_release','liquidity_reserve','expense_reserve','pdd','aging_trigger','dilution','repurchase','coobligation','evaluation','liquidation','cure','cross_default','waterfall','sequential','revolving','guarantee','enforcement','servicing','collection_account','collateral_check','hedge','hedge_priority','providers','replacement','quorum','related_parties','admin_fee','management_fee','performance_fee','custody_fee'}
    current = [r for r in records if r.get('current_document', True)]
    if not current:
        return [], 'Os trechos encontrados pertencem a documentos anteriores; preservados no histórico, sem promoção à resposta atual.'
    full = [r for r in current if r['full_regulation']]
    normative = [r for r in current if r.get('classification') in {'regulamento', 'anexo'}]
    eligible = normative if ident in regulation_ids and normative else current
    active=[r for r in eligible if str(r.get('provider_status','')).upper()=='AC']
    if active:
        eligible=active
    if normative and ident in regulation_ids:
        # Every selected scope is independently current in the inventory.
        # A missing clause in a newer general version cannot resurrect its
        # predecessor. Concurrent general/class documents do not conflict by
        # date alone. Later operative amendments are retained even if short.
        latest = eligible
    else:
        version = max(r['source']['reference_date'] for r in eligible)
        latest = [r for r in eligible if r['source']['reference_date'] == version]
    latest.sort(key=lambda r:(r['source'].get('list_recovery_complete',True),r['score'],r['source']['reference_date']), reverse=True)
    if ident=='eligibility' and any(r['source'].get('list_recovery_complete') is True for r in latest):
        latest=[r for r in latest if r['source'].get('list_recovery_complete') is not False]
    selected, seen = [], set()
    for r in latest:
        marker = fold(r['text'])
        if marker not in seen:
            selected.append(r)
            seen.add(marker)
        if len(selected) == 3:
            break
    reason = 'Documentos atuais selecionados no inventário por categoria/escopo; a data documental isolada não comprova vigência jurídica.' if normative else 'Trechos do documento específico identificado com data mais recente; vigência jurídica não inferida.'
    return selected, reason


def brief_clause(ident, text):
    """A literal reading aid; the complete clause remains in source.excerpt.

    Whole sentences are retained. Numbers, comparisons and units are never
    rewritten, inferred or chosen by a first-percentage rule.
    """
    compact=re.sub(r'\s+',' ',text).strip()
    if ident=='eligibility' and len(compact)<=2500:
        return compact if validate_primary_clause(ident,compact)['valid'] else ''
    if len(compact)<=650:
        return compact if validate_primary_clause(ident,compact)['valid'] else ''
    if ident in {'evaluation','liquidation','legacy_events'}:
        # The legal heading may list the parties responsible for checking the
        # events before the operative numbered triggers. Keep short complete
        # triggers, rather than turning those responsibilities into an answer.
        parts=re.split(r'(?=\((?:[ivxlcdm]{1,8})\)\s+)',compact,flags=re.I)
        label={'evaluation':'Evento de avaliação: ','liquidation':'Evento de liquidação: ','legacy_events':'Evento de avaliação ou liquidação: '}[ident]
        triggers=[part.strip() for part in parts if re.match(r'^\([ivxlcdm]+\)',part,re.I)
                  and len(part)<=1000 and validate_primary_clause(ident,label+part)['valid']]
        chosen=[]
        for trigger in triggers:
            if len(' '.join(chosen))+len(trigger)>1000:
                continue
            chosen.append(trigger)
            if len(chosen)>=2:
                break
        if chosen:
            return label+' '.join(chosen)
    sentences=re.split(r'(?<=[a-záéíóúãõç%\)])\.\s+(?=[A-ZÁÉÍÓÚÃÕ“\(])|(?<=;)\s+(?=\((?i:[ivxlcdm]+)\)|[A-ZÁÉÍÓÚ])',compact)
    anchors=next((r[3] for r in CRITERIA if r[0]==ident),())
    folded_anchors=[fold(a) for a in anchors]
    relevant=[s for s in sentences if any(a in fold(s) for a in folded_anchors)]
    if not relevant:
        relevant=sentences[:1]
    if ident in {'waterfall','sequential'}:
        # A partial priority list can reverse the credit conclusion. Keep an
        # intact short clause, or leave the long clause for analyst synthesis.
        return compact if len(compact)<=1200 and validate_primary_clause(ident,compact)['valid'] else ''
    first=relevant[0]
    if len(first)>1000:
        return ''
    selected=[first]
    # Keep a short adjacent condition when it qualifies the actual clause.
    ix=sentences.index(first)
    for sentence in sentences[ix+1:]:
        if len(' '.join(selected))+len(sentence)>1000:
            break
        if re.search(r'^(?:Caso|Se |Após|Decorridos|Observad|Desde|Quando|Durante|Salvo|Exceto)',sentence):
            selected.append(sentence)
        elif selected:
            break
    summary='. '.join(selected).rstrip('.')+'.'
    return summary if validate_primary_clause(ident,summary)['valid'] else ''


def numeric_rule(ident, value, sources):
    """Only unambiguous literal ratios; formulas with several layers stay text."""
    if ident not in {'allocation','subordination'}:
        return {}
    f = fold(value)
    all_ratios={float(m.replace(',','.')) for m in re.findall(r'(\d+(?:[.,]\d+)?)\s*%',f)}
    if len(all_ratios) != 1:
        return {}
    if ident == 'subordination' and re.search(r'pari passu|sem subordina|cotas unicas|subclasse unica', f):
        return {}
    patterns = (r'(?:≥|>=|minimo(?: de)?|no minimo|nao (?:sera|podera ser) inferior a|igual ou superior a)\s*(\d+(?:[.,]\d+)?)\s*%',
                r'(\d+(?:[.,]\d+)?)\s*%\s*\([^)]*\)\s*(?:do|de)\s*(?:patrimonio|pl|ativo)')
    values = set()
    for pattern in patterns:
        for m in re.finditer(pattern, f):
            values.add(float(m[1].replace(',','.')))
    if len(values) != 1 or not re.search(r'patrimonio liquido|\bpl\b', f):
        return {}
    if ident == 'subordination' and not re.search(r'cotas subordinadas|subordinadas/pl|subordinad',f):
        return {}
    if ident == 'allocation' and not re.search(r'direitos creditorios|dc/pl|direitos cred/pl',f):
        return {}
    rule = {'operator':'>=', 'limit': values.pop(), 'unit':'percent', 'numerator': 'credit_rights' if ident == 'allocation' else 'subordinated_quotas', 'denominator':'net_asset_value', 'frequency':'daily' if 'diari' in f else 'not_stated', 'effective_status':'document_date_only', 'document_date':max((s['reference_date'] for s in sources),default=''), 'layer':'class'}
    # A stated initial ramp-up cannot be inferred from registration or first IME.
    if re.search(r'apos|decorrid|a partir|primeira integraliza', f):
        rule['requires_initial_date'] = True
    return rule


def absence_status(documents, corpus, context=None):
    regs = [d for d in documents if d.get('classification') in {'regulamento','anexo'}]
    if context and context['current_documents']:
        regs = context['current_documents']
    if not regs:
        return 'document_not_obtained', 'Nenhum regulamento foi incorporado ao acervo identificado deste CNPJ.'
    readable = [d for d in regs if d.get('text_path')]
    if not readable:
        failed = [str(d.get('error') or '') for d in regs if d.get('error')]
        absent = any(d.get('parse_status') in {'not_downloaded','inventory_only','deferred_document'} or d.get('download_status') in {'inventory_only','deferred_document','not_downloaded'} for d in regs)
        status = 'access_blocked' if failed else 'document_not_obtained' if absent else 'parse_failed'
        ids = ', '.join(document_id(d) for d in regs if document_id(d))
        return status, ('; '.join(dict.fromkeys(failed)) or f'Documentos atuais selecionados ({ids}) sem texto legível incorporado; documentos anteriores não comprovam a regra atual.')
    if not any(d.get('parse_status') == 'complete' for d in readable):
        return 'extraction_pending', 'Há texto ou extrações anteriores, sem leitura integral e mapa de páginas verificados para o regulamento.'
    return 'clause_not_found', 'Não localizada uma cláusula material para este critério nos textos identificados e processados. A ausência de resultado não comprova inexistência da regra.'


def documented_lookthrough(owner, criteria):
    """An exact invested-class CNPJ needs a primary passage identifying its role.

    Mere CNPJ mentions (providers, cedentes, administrators) are excluded. A
    mandate never supplies actual holdings, weights or an aggregated NAV.
    """
    relationships={}
    pattern=re.compile(r'(?<!\d)(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14})(?!\d)')
    for criterion in criteria:
        if criterion['criterion_id'] not in {'receivables','investee'} or criterion['status']!='confirmed':
            continue
        text=criterion['value']
        for match in pattern.finditer(text):
            target=re.sub(r'\D','',match[1])
            if target==owner:
                continue
            prefix=text[max(0,match.start()-280):match.start()]
            context=fold(prefix)
            # An investor holding this fund's junior quotas points in the
            # reverse direction; it is not an investee of the analysed fund.
            if re.search(r'titularidade|cotistas?|subscritores?|detentores?',context):
                continue
            if not re.search(r'cotas|classe investida|fundo investido|fic.fidc|mezanino do',context):
                continue
            if re.search(r'(?:administrador|gestor|custodiante|originador)[^.;]{0,65}$',context):
                continue
            if re.search(r'custodia|custodiante|banco btg pactual|instituicao financeira|agente de cobranca|cogestor|administrad[ao]|gestor[a:]?',context):
                continue
            if not re.search(r'fidc|fundo[^.;]{0,180}direitos creditorios|classe investida|mercado credito',context):
                continue
            if re.search(r'tesouro selic|renda fixa|referenciado di|fundo de investimento financeiro',context):
                continue
            subclass='Mezanino' if 'mezanino' in context else 'Sênior' if 'senior' in context else 'Subordinada' if 'subordinad' in context else ''
            label=re.sub(r'^.*(?:cotas (?:da|do|de)|mezanino do|classe investida[: ]+|fundo investido[: ]+)', '',prefix, flags=re.I).strip(' :;,(\n')
            label=re.sub(r'\s*CNPJ\s*$', '',label,flags=re.I).strip(' :;,(\n')
            relationships[target]={'cnpj':target,'label':label or target,'subclass':subclass,'status':'permitted_mandate','sources':criterion['sources'],'weight_pct':None,'reason':'Vínculo de investimento identificado documentalmente. Peso e posição efetiva não são inferidos.'}
    return list(relationships.values())


def merge_verified_override(current, replacement, versions, cnpj=None):
    """Retain analyst work without presenting a retired source as current."""
    replacement = dict(replacement)
    available, historical = partition_sources(replacement.get('sources') or [], versions)
    current_normative = [source for source in available
                         if str(source.get('document_id')) in versions['current_ids']]
    if historical and not current_normative and current['criterion_id'] != 'changes':
        merged = dict(current)
        merged['history'] = list(current.get('history') or []) + [historical_answer(
            replacement.get('value',''), replacement.get('sources') or [],
            'Leitura manual preservada. A fonte normativa foi substituída na seleção atual do mesmo escopo; continuidade da cláusula não comprovada.',
            provenance='verified_override')]
        merged['manual_review'] = replacement
        merged['risk_note'] = (current.get('risk_note','') + ' Leitura manual anterior preservada no histórico; seleção documental por data não resolve vigência jurídica.').strip()
        manual_rule = replacement.get('rule') or numeric_rule(current['criterion_id'],replacement.get('value',''),replacement.get('sources') or [])
        current_rule = current.get('rule') or numeric_rule(current['criterion_id'],current.get('value',''),current.get('sources') or [])
        def rule_layer(rule):
            layer=rule.get('layer')
            return 'class' if layer in {'class','classe',cnpj} else layer
        same_basis = manual_rule and current_rule and all(manual_rule.get(key) == current_rule.get(key) for key in ('operator','unit','numerator','denominator')) and rule_layer(manual_rule)==rule_layer(current_rule)
        manual_scopes = {normative_scope(versions['by_id'][str(source['document_id'])]) for source in historical}
        current_scopes = {normative_scope(versions['by_id'][str(source['document_id'])]) for source in current.get('sources',[]) if str(source.get('document_id')) in versions['by_id']}
        if same_basis and manual_scopes & current_scopes and manual_rule.get('limit') != current_rule.get('limit'):
            merged.update(status='version_conflict',applicability='unresolved',rule={},
                          reason='Patamares diferentes na leitura manual anterior e no documento atual do mesmo escopo, com a mesma fórmula/base. Prevalência jurídica não certificada pela data isolada.')
            merged['risk_note'] += f" Patamar anterior: {manual_rule.get('limit')}; atual: {current_rule.get('limit')} ({current_rule.get('unit')})."
        elif current.get('status') != 'confirmed':
            merged['reason'] = (current.get('reason','') + ' A resposta manual anterior não foi promovida porque o documento atual não confirmou este critério.').strip()
        return merged
    merged = dict(current, **replacement)
    if replacement.get('status') in {'confirmed','not_applicable'}:
        merged['reason']=replacement.get('reason') or ''
    if replacement.get('history'):
        merged['history']=list(current.get('history') or [])+list(replacement['history'])
    merged['rule'] = replacement.get('rule',{})
    merged['provenance'] = 'verified_override'
    merged['precedence'] = 'Leitura específica das cláusulas indicadas; condições e conflitos preservados. Seleção documental atual não comprova vigência jurídica por data isolada.'
    if historical:
        merged['history'] = list(current.get('history') or []) + [historical_answer(
            replacement.get('value',''),historical,'Fonte histórica complementar à leitura manual, confirmada também por documento selecionado atualmente.',provenance='verified_override')]
    return merged


def lookthrough_targets(payload):
    excluded = {str(item.get('cnpj')) for item in payload.get('excluded_relationship_candidates',[])}
    targets = set()
    for relation in payload.get('lookthrough') or []:
        cnpj = re.sub(r'\D','',str(relation.get('cnpj') or ''))
        role = relation.get('relationship') or relation.get('status')
        located = any(source.get('document_id') and (source.get('page') or source.get('clause')) for source in relation.get('sources') or [])
        if len(cnpj)==14 and cnpj!=payload.get('cnpj') and cnpj not in excluded and located and role in {'permitted_mandate','named_investee','verified_position'}:
            targets.add(cnpj)
    return targets


def annotate_quarterly_conflicts(criteria,quarterly):
    # Documentary statements do not prove a transaction or legal breach.
    rules=[item for item in criteria if item.get('status')=='confirmed' and re.search(r'precat[oó]rios? federais',item.get('value',''),re.I) and re.search(r'vedad|proibid',item.get('value',''),re.I)]
    for record in quarterly.get('records') or []:
        text=fold(record.get('value',''))
        if record['criterion_id']=='precatórios' and rules and re.search(r'adquiriu|adquiridos|adquiriram',text) and not re.search(r'nao.{0,50}(?:adquiri|aquisic)',text):
            record['status']='documentary_conflict'
            record['risk_note']='O informe declara aquisição de precatórios federais; o regulamento citado veda essa aquisição. Operação efetiva e vigência jurídica durante o trimestre não foram comprovadas por essas duas declarações.'
            record['sources']=[record['source']]+[source for item in rules for source in item.get('sources',[])]
    return quarterly


def build_fund(cnpj, name, corpus, review, roots, quarterly_inventory=None, criterion_ids=None):
    documents = corpus.get('documents') or []
    versions = version_context(documents)
    candidates = extract_primary_candidates(documents, roots,criterion_ids)
    previous = {}
    for theme, facts in review.get('facts',{}).items():
        if theme == 'comparison_monitoring':
            continue
        for label,fact in facts.items():
            ident = LEGACY_MAP.get(label)
            if ident:
                previous[ident] = (label, fact, theme)
    criteria = []
    for ident,theme,label,anchors in CRITERIA:
        if criterion_ids is not None and ident not in criterion_ids:
            continue
        selected,precedence = choose_passages(candidates[ident], ident)
        old = previous.get(ident)
        old_sources = reviewed_source(old[1],documents) if old else []
        old_value = str(old[1].get('value') or '') if old else ''
        latest_date = max((r['source']['reference_date'] for r in selected), default='')
        # A textual locator does not validate a legacy regex/LLM synthesis.
        # Current primary passages and explicitly verified analyst overrides
        # provide answers; every previous review remains archival evidence.
        if selected:
            summaries=list(dict.fromkeys(brief_clause(ident,r['text']) for r in selected))
            value = '\n\n'.join(summary for summary in summaries if summary)
            if ident=='eligibility' and any(r['source'].get('list_recovery_complete') is False for r in selected):
                value=''
            rule_text='\n\n'.join(r['text'] for r in selected)
            sources = [r['source'] for r in selected]
            provenance = 'primary_passage'
            note = precedence
        else:
            value,sources,provenance,note = '',[],'',''
            rule_text=''
        status,reason = ('confirmed','') if value and sources and all(s['reference_date'] and (s['page'] or s['clause']) for s in sources) else absence_status(documents,corpus,versions)
        if selected and not value:
            status,reason='extraction_pending','Cláusula primária localizada e citada, mas sua lista/condições extensas não admitem uma síntese literal curta confirmada. O trecho integral permanece nas fontes.'
            if ident=='eligibility' and any(r['source'].get('list_recovery_complete') is False for r in selected):
                reason='Lista de elegibilidade recuperada parcialmente: continuação em página excluída do OCR ou além do limite de leitura adjacente. Não foi tratada como conjunto completo de condições.'
        if status != 'confirmed':
            value = ''
        applicability = 'applicable' if status=='confirmed' else 'unresolved'
        historical=[]
        if old and old_sources and material_answer(old_value):
            historical.append(historical_answer(old_value, old_sources,
                'Revisão anterior arquivada. Localizador textual e frase material não validam sua semântica, números ou base; não promovida à resposta atual.',
                provenance='previous_review_with_primary_locator'))
            historical[-1]['risk_note']=str(old[1].get('note') or '')
        seen_dates=set()
        for earlier in candidates[ident]:
            source=earlier['source']
            date=source['reference_date']
            if (not earlier.get('current_document',True) or (date and date<latest_date)) and (source['document_id'],date) not in seen_dates:
                seen_dates.add((source['document_id'],date))
                historical.append(historical_answer(brief_clause(ident,earlier['text']),[source],
                    'Documento anterior do mesmo escopo; não promovido à resposta atual. A vigência jurídica e eventual continuidade da cláusula não são inferidas.' if not earlier.get('current_document',True) else 'Trecho anterior preservado sem inferir a vigência jurídica.'))
        if old_sources and status!='confirmed':
            reason = (reason+' A resposta da revisão anterior foi preservada no histórico, sem confirmação pelo documento atual.').strip()
        criteria.append({'criterion_id':ident,'label':label,'theme':theme,'applicability':applicability,'status':status,'value':value,'reason':reason,'sources':sources,'rule':numeric_rule(ident,rule_text,sources) if status=='confirmed' else {},'risk_note':note,'provenance':provenance,'precedence':precedence,'history':historical})
    # Keep previously curated specialized questions rather than dropping them
    # to fit the common catalog. No placeholder becomes a fact.
    for ident,(label,fact,theme) in previous.items():
        if criterion_ids is not None:
            continue
        if ident in {c['criterion_id'] for c in criteria}:
            continue
        sources=reviewed_source(fact,documents)
        if sources and material_answer(fact.get('value','')):
            criteria.append({'criterion_id':ident,'label':label,'theme':{'comparison_emissions':'Emissões e custos','comparison_mechanics':'Fluxo de caixa e prazo','comparison_protection':'Eventos e cura','comparison_payments':'Fluxo de caixa e prazo'}.get(theme,'Governança e alterações'),'applicability':'unresolved','status':'extraction_pending','value':'','sources':[],'rule':{},'risk_note':'','provenance':'previous_review_archived',
                             'reason':'Pergunta especializada preservada da revisão anterior; síntese antiga não validada por cláusula primária atual compatível.',
                             'history':[historical_answer(fact['value'],sources,'Revisão anterior arquivada; fonte textual não valida a síntese.',provenance='previous_review_with_primary_locator')]})
    lookthrough=documented_lookthrough(cnpj,criteria)
    override=read_json(ROOT/'data/documentary_diligence/verified_overrides'/f'{cnpj}.json')
    if override:
        replacements={c['criterion_id']:c for c in override.get('criteria',[]) if criterion_ids is None or c['criterion_id'] in criterion_ids}
        merged=[]
        for c in criteria:
            if c['criterion_id'] in replacements:
                replacement=replacements.pop(c['criterion_id'])
                c=merge_verified_override(c,replacement,versions,cnpj)
            merged.append(c)
        criteria=merged
        for replacement in replacements.values():
            status,reason=absence_status(documents,corpus,versions)
            initial=dict(replacement,status=status,applicability='unresolved',value='',sources=[],rule={},reason=reason,history=[])
            criteria.append(merge_verified_override(initial,replacement,versions,cnpj))
        if 'lookthrough' in override:
            lookthrough=[]
            for relation in override['lookthrough']:
                _, historical=partition_sources(relation.get('sources') or [],versions)
                if not historical:
                    lookthrough.append(relation)
    # Recompute inferred links after manual changes so a retired passage or a
    # provider's CNPJ cannot leave a stale child in the portable index.
    if not override or 'lookthrough' not in override:
        lookthrough=documented_lookthrough(cnpj,criteria)
    quarterly_inventory=load_quarterly_inventory() if quarterly_inventory is None else quarterly_inventory
    quarterly=load_quarterly_observations(cnpj,quarterly_inventory)
    quarterly=annotate_quarterly_conflicts(criteria,quarterly)
    return {'schema_version':2,'build_revision':BUILD_REVISION,'corpus_revision':corpus_revision(corpus),'override_revision':override_revision(cnpj),'quarterly_revision':quarterly_revision(cnpj,quarterly_inventory),
            'criterion_revisions':{row['criterion_id']:validator_revision() for row in criteria},
            'criterion_extractor_revisions':{row['criterion_id']:EXTRACTOR_REVISION for row in criteria},
            'cnpj':cnpj,'name':name,'reviewed_at':datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(timespec='seconds'),'corpus_status':{'inventoried':len(documents),'readable':sum(bool(d.get('text_path')) for d in documents),'searches':corpus.get('searches',[]),'limitations':corpus.get('limitations',[]),'pending_sources':corpus.get('pending_sources',[])},'criteria':criteria,'lookthrough':lookthrough,
            'lookthrough_provenance':'verified_override' if override and 'lookthrough' in override else 'primary_passage',
            'quarterly_observations':quarterly,
            'document_selection':{'current_document_ids':sorted(versions['current_ids']),'basis':'Inventário por categoria/escopo; não certifica vigência jurídica por data isolada.'},
            'excluded_relationship_candidates':override.get('excluded_candidates',[]) if override else []}


def merge_partial_fund(cached,refreshed,criterion_ids):
    """Replace only selected questions; preserve other answers and history refs."""
    replacements={item['criterion_id']:item for item in refreshed['criteria']}
    payload=dict(cached,**{name:value for name,value in refreshed.items() if name not in {'criteria','criterion_revisions','criterion_extractor_revisions','lookthrough'}})
    payload['criteria']=[replacements.pop(item['criterion_id'],item) if item['criterion_id'] in criterion_ids else item for item in cached['criteria']]
    payload['criteria'].extend(replacements.values())
    payload['criterion_revisions']=dict(cached.get('criterion_revisions') or {},**refreshed.get('criterion_revisions',{}))
    payload['criterion_extractor_revisions']=dict(cached.get('criterion_extractor_revisions') or {},**refreshed.get('criterion_extractor_revisions',{}))
    if criterion_ids & {'receivables','investee'}:
        payload['lookthrough']=refreshed.get('lookthrough',[]) if refreshed.get('lookthrough_provenance')=='verified_override' else documented_lookthrough(payload['cnpj'],payload['criteria'])
    else:
        payload['lookthrough']=cached.get('lookthrough',[])
    payload['quarterly_observations']=annotate_quarterly_conflicts(payload['criteria'],payload.get('quarterly_observations') or {})
    return payload


def revalidate_published_answers(payload):
    """Check stored primary sources/visible answers without claiming new extraction."""
    checked=rejected=0
    for item in payload.get('criteria') or []:
        if item.get('status')!='confirmed' or item.get('provenance')!='primary_passage':
            continue
        ident=item['criterion_id']
        checks=[validate_primary_clause(ident,item.get('value',''))]
        checks.extend(validate_primary_clause(ident,source.get('excerpt','')) for source in item.get('sources') or [])
        checked+=1
        failures=[check['reason'] for check in checks if not check['valid']]
        item['semantic_validation']={'validator_fingerprint':validator_revision(),'basis':'Fontes e resposta publicadas revalidadas; não houve nova extração para esta conferência.','valid':not failures}
        if failures:
            rejected+=1
            item['history']=list(item.get('history') or [])+[historical_answer(item.get('value',''),item.get('sources') or [],
                'Resposta anteriormente publicada rejeitada na validação de relevância: '+' '.join(dict.fromkeys(failures)),provenance='published_primary_answer_rejected')]
            item.update(status='extraction_pending',value='',rule={},applicability='unresolved',
                        reason='Validação da resposta publicada: '+' '.join(dict.fromkeys(failures)))
        else:
            payload.setdefault('criterion_revisions',{})[ident]=validator_revision()
    payload['semantic_validation_receipt']={'validator_fingerprint':validator_revision(),'confirmed_primary_checked':checked,'rejected':rejected,
        'basis':'Relevância das fontes e valores disponíveis; não certifica vigência jurídica, números ou interpretação de leituras manuais.'}
    return payload


def reachable_fund_index(base, registered):
    """Index declared funds and exact documented permissions reachable from them."""
    queue=list(registered)
    visited=set()
    output={}
    while queue:
        cnpj=queue.pop()
        if cnpj in visited:
            continue
        visited.add(cnpj)
        path=base/'funds'/f'{cnpj}.json'
        payload=read_json(path)
        if not payload or payload.get('cnpj')!=cnpj:
            continue
        output[cnpj]=str(path.relative_to(base))
        queue.extend(lookthrough_targets(payload)-visited)
    return dict(sorted(output.items()))


def measure_before(root, portfolios):
    from services.presentation_text import document_comparison_value
    import csv
    by_fund={}
    by_portfolio=[]
    for portfolio in portfolios:
        packages=[]
        for mp in (root/'data/deep_dives').glob('*/manifest.json'):
            m=read_json(mp)
            if m.get('portfolio_id')==portfolio['id']:
                packages.append((mp,m))
        if not packages:
            continue
        mp,m=max(packages,key=lambda r:r[1].get('generated_at',''))
        mapping=m.get('comparison_columns',{})
        count=filled=located=0
        epath=mp.parent/'evidence/comparison_sources.csv'
        if not epath.exists():
            continue
        with epath.open(encoding='utf-8') as stream:
            for row in csv.DictReader(stream):
                cnpj=re.sub(r'\D','',row.get('CNPJ',''))
                if len(cnpj)!=14:
                    continue
                count+=1
                answer=document_comparison_value(row['Valor'])!='-'
                page,clause=source_locator(row.get('Fonte','')+' '+row.get('Nota',''))
                loc=bool(page or clause)
                filled+=answer
                located+=answer and loc
                f=by_fund.setdefault(cnpj,{'cells':0,'display_answers':0,'answer_with_locator':0})
                f['cells']+=1;f['display_answers']+=answer;f['answer_with_locator']+=answer and loc
        by_portfolio.append({'portfolio_id':portfolio['id'],'name':portfolio['name'],'cells':count,'display_answers':filled,'answer_with_locator':located})
    return {'method':'Baseline mécanique: texto renderizável + localizador textual. Aplicabilidade e validade semântica não estavam modeladas. Não equivale à cobertura auditada.','funds':by_fund,'portfolios':by_portfolio}


def main():
    from services.documentary_diligence import public_document_payload
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--only-cnpj',action='append',default=[])
    parser.add_argument('--only-criterion',action='append',default=[],choices=[row[0] for row in CRITERIA],
                        help='Revalida somente estes critérios quando o corpus e a revisão de base não mudaram.')
    parser.add_argument('--source-root',type=Path,default=ROOT)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    portfolios=read_json(ROOT/'portfolios.json')['portfolios']
    registered={f['cnpj']:f['display_name'] for p in portfolios for f in p['funds']}
    wanted=set(args.only_cnpj) if args.only_cnpj else set(registered)
    if not args.all and not args.only_cnpj:
        parser.error('Especifique --all ou --only-cnpj.')
    base=ROOT/'data/documentary_diligence'
    quarterly_inventory=load_quarterly_inventory()
    if not (base/'baseline.json').exists():
        atomic_json(base/'baseline.json',measure_before(ROOT,portfolios))
    processed=set()
    wanted_criteria=set(args.only_criterion) if args.only_criterion else {row[0] for row in CRITERIA}
    queue=sorted(wanted)
    while queue:
        cnpj=queue.pop(0)
        if cnpj in processed:
            continue
        processed.add(cnpj)
        target=base/'funds'/f'{cnpj}.json'
        corpus=load_documentary_corpus(cnpj)
        cached=read_json(target)
        history_complete=not any(item.get('history_ref') for item in cached.get('criteria') or []) or (base/'history'/f'{cnpj}.json').is_file()
        semantic_current=processing_revisions_current(cached,wanted_criteria)
        source_text_available=any(resolve_path(doc.get('text_path'),[ROOT,args.source_root]) for doc in corpus.get('documents') or [])
        if cached.get('cnpj')==cnpj and not source_text_available:
            # A public clone contains audited metadata and published answers,
            # not the private PDFs. Never erase those answers by pretending to
            # have re-extracted a primary document that is unavailable here.
            payload=dict(cached)
            payload['build_warnings']=list(dict.fromkeys(list(cached.get('build_warnings') or [])+[
                'Corpus público de auditoria sem textos primários locais: curadoria publicada preservada, sem nova extração ou validação semântica.']))
            payload['quarterly_observations']=annotate_quarterly_conflicts(payload.get('criteria') or [],load_quarterly_observations(cnpj,quarterly_inventory))
        elif args.resume and semantic_current and history_complete and cached.get('build_revision')==BUILD_REVISION and cached.get('corpus_revision')==corpus_revision(corpus) and cached.get('override_revision')==override_revision(cnpj) and cached.get('quarterly_revision')==quarterly_revision(cnpj,quarterly_inventory):
            payload=cached
        else:
            review=read_json(ROOT/'data/regulatory_profiles/documentary_comparisons'/f'{cnpj}.json')
            same_or_scoped_override=cached.get('override_revision')==override_revision(cnpj) or partial_override_change_safe(cached,wanted_criteria,cnpj)
            partial=bool(args.only_criterion and history_complete and cached.get('build_revision')==BUILD_REVISION and cached.get('corpus_revision')==corpus_revision(corpus) and same_or_scoped_override)
            refreshed=build_fund(cnpj,registered.get(cnpj,review.get('label',cnpj)),corpus,review,[ROOT,args.source_root],quarterly_inventory=quarterly_inventory,
                                 criterion_ids=wanted_criteria if partial else None)
            payload=merge_partial_fund(cached,refreshed,wanted_criteria) if partial else refreshed
        if source_text_available:
            payload=revalidate_published_answers(payload)
        payload=public_document_payload(payload)
        previous_history=read_json(base/'history'/f'{cnpj}.json') if any(item.get('history_ref') for item in payload.get('criteria') or []) else None
        history=compact_history_payload(payload,existing_history=previous_history)
        if history:
            history=public_document_payload(history)
            history_sha=sha256((json.dumps(history,ensure_ascii=False,indent=2)+'\n').encode()).hexdigest()
            for item in payload['criteria']:
                if item.get('history_ref'):
                    item['history_ref']['sha256']=history_sha
            atomic_json(base/'history'/f'{cnpj}.json',history)
        atomic_json(target,payload)
        if corpus:
            atomic_json(base/'audit_corpus'/f'{cnpj}.json',public_document_payload(corpus))
        counts=Counter(r['status'] for r in payload['criteria'])
        print(cnpj,json.dumps(counts,ensure_ascii=False),flush=True)
        queue.extend(lookthrough_targets(payload)-processed)
    # Older runs may have emitted files for providers or reverse ownership
    # links. Keep those files recoverable while excluding them from the index.
    indexed=reachable_fund_index(base,registered)
    for ident in indexed:
        path=base/'funds'/f'{ident}.json'
        atomic_json(path,public_document_payload(read_json(path)))
        audit=load_documentary_corpus(ident)
        if audit:
            atomic_json(base/'audit_corpus'/f'{ident}.json',public_document_payload(audit))
    index={'schema_version':2,'generated_at':datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(timespec='seconds'),'registered_portfolios':len(portfolios),'registered_cnpjs':len(registered),'funds':indexed,
           'unbuilt_registered_cnpjs':sorted(set(registered)-set(indexed)),
           'unreachable_generated_cnpjs':sorted(p.stem for p in (base/'funds').glob('*.json') if p.stem not in indexed),
           'analysis_scope':'Todos os CNPJs declarados; somente investidas ou permissões com CNPJ, papel e fonte explícitos alcançáveis. IME por carteira/competência; perímetro investido separado.'}
    atomic_json(base/'index.json',index)


if __name__=='__main__':
    main()
