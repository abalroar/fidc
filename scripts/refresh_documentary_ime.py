"""Acquire bounded recent IME snapshots for every documentary CNPJ, serially."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.documentary_corpus import atomic_json, load_registered_funds
from services.documentary_ime_comparison import _cache_snapshot, normalize_documentary_competence, IME_TRANSFORMATION_VERSION
from services.fundonet_client import FundosNetClient, _decode_download_payload
from services.fundonet_parser import parse_informe_mensal_xml
from services.fundonet_service import select_latest_documents
import time

TRANSFORMATION_VERSION = IME_TRANSFORMATION_VERSION


def default_through():
    today = date.today()
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f'{month:02d}/{year}'


def month_key(value):
    return int(value[3:]),int(value[:2])


def recent_corpus_catalog(cnpj, base):
    """Reuse today's completed all-type catalog; never trust an old FIDC-only search."""
    from services.fundonet_models import DocumentoFundo
    path = base / 'corpus' / f'{cnpj}.json'
    if not path.exists():
        return None
    corpus = json.loads(path.read_text())
    today = date.today().isoformat()
    if not any(search.get('source') == 'fundosnet' and search.get('status') in {'found','no_results'}
               and search.get('scope') == 'cnpj_all_fund_types' and str(search.get('queried_at','')).startswith(today)
               for search in corpus.get('searches',[])):
        return None
    documents = []
    for item in corpus.get('documents',[]):
        if item.get('classification') != 'informe_mensal' or not item.get('id'):
            continue
        documents.append(DocumentoFundo(int(item['id']), 'Informes Periódicos', item.get('title') or 'Informe Mensal Estruturado', '',
                         item.get('reference_date'), item.get('delivery_date'), None, None, int(item.get('version') or 0),
                         item.get('provider_status') or '', item.get('scope'), {}))
    return documents


def download_xml(client, document_id):
    url=client._url('downloadDocumento',params={'id':str(document_id)})
    request=urllib.request.Request(url,headers={'User-Agent':client.user_agent,'Accept':'text/xml,application/xml,text/plain,*/*'})
    chunks,total=[],0
    with client.opener.open(request,timeout=client.timeout_seconds) as response:
        for chunk in iter(lambda:response.read(65536),b''):
            total+=len(chunk)
            if total>5*1024**2:
                raise ValueError('IME response exceeds bounded 5MB limit')
            chunks.append(chunk)
    return _decode_download_payload(b''.join(chunks))


def fetch_fund(cnpj, documents, base, *, months=3, through=None, force_reprocess=False, timeout_seconds=8):
    candidates={}
    monthly=[d for d in documents if 'mensal' in d.tipo.lower() and 'estruturado' in d.tipo.lower()]
    for document in select_latest_documents(monthly):
        comp=normalize_documentary_competence(document.competencia_label or document.data_referencia)
        if not comp or (through and month_key(comp)>month_key(through)):
            continue
        candidates[comp]=document
    selected=sorted(candidates,key=month_key,reverse=True)[:months]
    result={'competences':[],'snapshots':{},'attempts':[]}
    client=FundosNetClient(timeout_seconds=timeout_seconds,max_retries=0)
    for competence in selected:
        document=candidates[competence]
        filename=f'{cnpj}_{competence[3:]}{competence[:2]}.json'
        target=base/'ime'/filename
        cached=json.loads(target.read_text()) if target.exists() else {}
        if not force_reprocess and cached.get('source',{}).get('document_id')==str(document.id) and cached.get('status')=='parsed' and cached.get('transformation_version')==TRANSFORMATION_VERSION:
            result['competences'].append(competence)
            result['snapshots'][competence]=f'ime/{filename}'
            continue
        attempt={'competence':competence,'document_id':document.id,'status':'failed','error':''}
        try:
            work=ROOT/'.cache/documentary-ime'/cnpj/filename.removesuffix('.json')
            work.mkdir(parents=True,exist_ok=True)
            wide=work/'wide.csv'; lists=work/'lists.csv'; docs=work/'docs.csv'
            reusable=False
            if all(p.exists() for p in (wide,lists,docs)):
                with docs.open(encoding='utf-8',newline='') as stream:
                    reusable=any(str(r['documento_id'])==str(document.id) for r in csv.DictReader(stream))
            xml_hash=''
            if not reusable:
                xml=download_xml(client,document.id)
                parsed=parse_informe_mensal_xml(xml,document.id)
                xml_comp=normalize_documentary_competence(parsed.metadata.get('competencia_xml'))
                if xml_comp!=competence:
                    raise ValueError('XML competence differs from document catalog')
                with wide.open('w',encoding='utf-8',newline='') as stream:
                    writer=csv.writer(stream);writer.writerow(['tag_path',competence])
                    for row in parsed.scalar_df.to_dict('records'):
                        writer.writerow([row['tag_path'],row['valor_raw']])
                parsed.list_df['competencia']=competence
                parsed.list_df.to_csv(lists,index=False)
                with docs.open('w',encoding='utf-8',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=['documento_id','competencia','versao','data_entrega']);writer.writeheader()
                    writer.writerow({'documento_id':document.id,'competencia':competence,'versao':document.versao,'data_entrega':document.data_entrega})
                xml_hash=sha256(xml).hexdigest()
            else:
                decorate_local_lists(lists,competence)
            files={'wide_csv_path':'wide.csv','listas_csv_path':'lists.csv','docs_csv_path':'docs.csv'}
            values,source,error=_cache_snapshot(str(work),json.dumps(files),cnpj,competence,wide.stat().st_mtime_ns)
            if error:
                raise ValueError(error)
            source.update({'type':'ime_document','document_id':str(document.id),'version':document.versao,'delivered_at':document.data_entrega,'path':f'data/documentary_diligence/ime/{filename}'})
            source['sha256' if xml_hash else 'declared_fields_sha256']=xml_hash or sha256(wide.read_bytes()).hexdigest()
            atomic_json(target,{'schema_version':1,'transformation_version':TRANSFORMATION_VERSION,'cnpj':cnpj,'competence':competence,'status':'parsed','values':values,'source':source,'error':''})
            result['competences'].append(competence);result['snapshots'][competence]=f'ime/{filename}'
            attempt.update(status='parsed')
        except Exception as error:
            attempt['error']=f'{type(error).__name__}: {error}'
        result['attempts'].append(attempt)
    return result


def decorate_local_lists(path,competence):
    import pandas as pd
    frame=pd.read_csv(path,dtype=str,keep_default_na=False)
    if 'competencia' not in frame:
        frame['competencia']=competence
        frame.to_csv(path,index=False)


def reprocess_local(base,index):
    from services.fundonet_models import DocumentoFundo
    for directory in sorted((ROOT/'.cache/documentary-ime').glob('*/*')):
        docs=directory/'docs.csv'
        if not docs.exists():
            continue
        with docs.open(encoding='utf-8',newline='') as stream:
            rows=list(csv.DictReader(stream))
        if not rows:
            continue
        row=rows[0];cnpj=directory.parent.name;competence=row['competencia']
        doc=DocumentoFundo(id=int(row['documento_id']),categoria='Informes Periódicos',tipo='Informe Mensal Estruturado',especie='',data_referencia=competence,data_entrega=row.get('data_entrega'),versao=int(row.get('versao') or 0),status='AC',nome_fundo=None,nome_arquivo=None,fundo_ou_classe=None,raw={})
        record=fetch_fund(cnpj,[doc],base,months=1,force_reprocess=True)
        existing=index['cnpjs'].setdefault(cnpj,{'competences':[],'snapshots':{},'attempts':[]})
        for comp in record['competences']:
            if comp not in existing['competences']:
                existing['competences'].append(comp)
        existing['snapshots'].update(record['snapshots'])
        existing['attempts']=[a for a in existing.get('attempts',[]) if a.get('competence')!=competence]+record['attempts']
        atomic_json(base/'ime_index.json',index)
        print('Local',cnpj,competence,record['competences'],flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all',action='store_true');parser.add_argument('--only-cnpj',action='append',default=[])
    parser.add_argument('--months',type=int,default=3);parser.add_argument('--through',default=default_through())
    parser.add_argument('--offline-reprocess',action='store_true')
    parser.add_argument('--use-corpus-catalog',action='store_true')
    parser.add_argument('--network-timeout-seconds',type=int,default=8)
    args=parser.parse_args()
    if not args.all and not args.only_cnpj and not args.offline_reprocess:
        parser.error('Use --all or --only-cnpj')
    if not 1<=args.months<=6:
        parser.error('At most six recent months are allowed for this bounded snapshot job')
    if normalize_documentary_competence(args.through) != args.through:
        parser.error('--through must be a valid MM/YYYY competence')
    if not 1 <= args.network_timeout_seconds <= 30:
        parser.error('Network timeout must be between one and thirty seconds')
    selected=set(load_registered_funds(ROOT/'portfolios.json')) if args.all else set(args.only_cnpj)
    base=ROOT/'data/documentary_diligence';path=base/'ime_index.json'
    index=json.loads(path.read_text()) if path.exists() else {'schema_version':1,'cnpjs':{}}
    if args.offline_reprocess:
        reprocess_local(base,index)
        return
    client=FundosNetClient(timeout_seconds=args.network_timeout_seconds,max_retries=0)
    for position,cnpj in enumerate(sorted(selected),1):
        try:
            documents = recent_corpus_catalog(cnpj,base) if args.use_corpus_catalog else None
            catalog_basis = 'same_day_all_type_documentary_corpus' if documents is not None else 'fresh_fundosnet_query'
            last_error=None
            for attempt in range(2) if documents is None else ():
                try:
                    documents=client.listar_documentos(cnpj,tipo_fundo='',error_stage='documentary_ime_catalog')
                    last_error=None
                    break
                except Exception as error:
                    last_error=error
                    if attempt==0:
                        time.sleep(1)
            if last_error:
                raise last_error
            item=fetch_fund(cnpj,documents,base,months=args.months,through=args.through,timeout_seconds=args.network_timeout_seconds)
            old = index['cnpjs'].get(cnpj,{})
            item['snapshots'] = {**old.get('snapshots',{}), **item['snapshots']}
            item['competences'] = sorted(set(old.get('competences',[])) | set(item['competences']),key=month_key,reverse=True)
            current_competences = {attempt['competence'] for attempt in item['attempts']}
            item['attempts'] = [attempt for attempt in old.get('attempts',[]) if attempt.get('competence') not in current_competences] + item['attempts']
            item.update(catalog_scope='cnpj_all_fund_types',catalog_basis=catalog_basis,searched_at=date.today().isoformat())
        except Exception as error:
            item=index['cnpjs'].get(cnpj,{'competences':[],'snapshots':{},'attempts':[]})
            item['catalog_error']=f'{type(error).__name__}: {error}'
        index['cnpjs'][cnpj]=item
        atomic_json(path,index)
        print(f'[{position}/{len(selected)}] {cnpj}: {item["competences"]}',flush=True)
        _cache_snapshot.cache_clear()
    print('All declared CNPJs retained, including failed catalogs and unavailable months.',flush=True)


if __name__=='__main__':
    main()
