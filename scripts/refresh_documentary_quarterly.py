"""Acquire quarterly declarations serially and preserve their XML values and identity."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from services.documentary_corpus import (atomic_json, document_date_key, document_url,
                                        load_registered_funds, normalize_cnpj, utc_now, sha256_file)
from services.fundonet_client import FundosNetClient, _decode_download_payload
from services.documentary_diligence import public_document_payload

TRANSFORMATION_VERSION = 3
CHUNK = 65536
MAX_XML_BYTES = 5 * 1024**2
HEADER_NAMES = {'CAB_INFORM', 'CABECALHO', 'HEADER', 'CAB_INFORM_TRIMESTRAL', 'CAB_INFORM_TRIM', 'CAB_INF', 'DADOSGERAIS'}
CNPJ_HEADER_RE = re.compile(r'(?<!\d)(?:\d{2}\s*\.\s*\d{3}\s*\.\s*\d{3}\s*/\s*\d{4}\s*-\s*\d{2}|\d{14})(?!\d)')


def tag_name(tag: str) -> str:
    return tag.rsplit('}', 1)[-1].upper()


def local_name(tag: str) -> str:
    return tag.rsplit('}', 1)[-1]


def quarter_key(value: object) -> str:
    text = str(value or '').strip()
    match = re.fullmatch(r'(\d{4})-Q([1-4])', text, flags=re.I)
    if match:
        return f'{match[1]}-Q{match[2]}'
    for fmt in ('%m/%Y', '%d/%m/%Y', '%Y-%m-%d', '%Y-%m', '%Y%m'):
        try:
            date = datetime.strptime(text[:10] if fmt == '%Y-%m-%d' else text, fmt)
            return f'{date.year:04d}-Q{(date.month-1)//3+1}'
        except ValueError:
            continue
    return ''


def xml_fields(root: ET.Element) -> list[dict]:
    """Use stable, indexed local-name XPaths, including repeated list fields."""
    rows = []
    def visit(node, path):
        if len(rows) > 100000:
            raise ValueError('XML field count exceeds explicit 100000 field limit')
        if not list(node):
            text = (node.text or '').strip()
            rows.append({'xpath': path, 'tag': tag_name(node.tag), 'value': text, 'text': text,
                         'namespace': node.tag[1:].split('}', 1)[0] if node.tag.startswith('{') else ''})
        for name, value in node.attrib.items():
            rows.append({'xpath': f'{path}/@{local_name(name)}', 'tag': tag_name(name), 'value': value, 'text': value})
        counts = Counter()
        for child in node:
            name = local_name(child.tag)
            counts[name] += 1
            visit(child, f'{path}/{name}[{counts[name]}]')
    visit(root, '/' + local_name(root.tag) + '[1]')
    return rows


def parse_quarterly_xml(payload: bytes, cnpj: str, document: dict) -> dict:
    """No rule, frequency or event is inferred from a tag or an absent answer."""
    expected = normalize_cnpj(cnpj)
    if len(payload) > MAX_XML_BYTES:
        raise ValueError('Decoded XML exceeds explicit 5MB limit')
    if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
        raise ValueError('XML declarations with DTD/entities are unsupported')
    root = ET.fromstring(payload)
    fields = xml_fields(root)
    headers = [field for field in fields if any('/' + name + '[' in field['xpath'].upper() for name in HEADER_NAMES)]
    identity = {'status': 'missing_header', 'expected_cnpj': expected, 'cnpj_fundo': '', 'cnpj_classe': '', 'header_fields': []}
    competence = ''
    if headers:
        identity['status'] = 'identity_missing'
        for field in headers:
            tag = field['tag']
            if 'CNPJ' in tag and ('FUNDO' in tag or 'CLASSE' in tag or tag in {'CNPJ', 'NR_CNPJ'}):
                value = normalize_cnpj(field['value'])
                if len(value) == 14:
                    key = 'cnpj_classe' if 'CLASSE' in tag else 'cnpj_fundo'
                    identity[key] = value
                    identity['header_fields'].append(field)
            if tag in {'DT_COMPT', 'DT_COMPETENCIA', 'COMPETENCIA', 'DATA_COMPETENCIA', 'DT_REFERENCIA', 'DT_TRIMESTRE', 'DATAENCERTRIMESTRE', 'DATAENCERRAMENTOTRIMESTRE'}:
                competence = field['value']
        present = {identity['cnpj_fundo'], identity['cnpj_classe']} - {''}
        if present:
            identity['status'] = 'verified' if expected in present else 'identity_mapping_pending'
    declared_quarter = quarter_key(competence)
    catalog_quarter = quarter_key(document.get('reference_date'))
    status = 'parsed' if identity['status'] == 'verified' else identity['status']
    error = ''
    if status == 'parsed' and declared_quarter and catalog_quarter and declared_quarter != catalog_quarter:
        status, error = 'competence_conflict', 'XML quarter differs from the document inventory reference date'
    source = {'type': 'quarterly_xml', 'document_id': str(document['id']),
              'reference_date': document.get('reference_date'), 'delivered_at': document.get('delivery_date'),
              'version': document.get('version'), 'url': document.get('url') or document_url(document['id']),
              'sha256': sha256(payload).hexdigest(), 'xpath': None, 'xpath_syntax': 'indexed local names preserving source case; namespace stored per field',
              'identity_verified': identity['status'] == 'verified'}
    return {'schema_version': 1, 'transformation_version': TRANSFORMATION_VERSION, 'cnpj': expected,
            'quarter': declared_quarter or catalog_quarter, 'competence': competence, 'identity': identity,
            'status': status, 'fields': fields, 'source': source, 'parsed_at': utc_now(), 'error': error}


def parse_quarterly_pdf(path: Path, cnpj: str, document: dict) -> dict:
    """Extract every physical page, using exact CNPJ in the first page as identity evidence."""
    expected = normalize_cnpj(cnpj)
    source = {'type': 'quarterly_pdf', 'document_id': str(document['id']),
              'reference_date': document.get('reference_date'), 'delivered_at': document.get('delivery_date'),
              'version': document.get('version'), 'url': document.get('url') or document_url(document['id']),
              'sha256': sha256_file(path), 'identity_verified': False}
    result = {'schema_version': 1, 'transformation_version': TRANSFORMATION_VERSION, 'cnpj': expected,
              'quarter': quarter_key(document.get('reference_date')), 'competence': document.get('reference_date'),
              'quarter_source': 'document_catalog', 'status': 'parse_error', 'parse_status': 'not_parsed',
              'fields': [], 'pages': [], 'pages_total': None, 'pages_extracted': 0, 'source': source,
              'identity': {'status': 'not_verified', 'expected_cnpj': expected, 'cnpj_fundo': '', 'cnpj_classe': '', 'header_fields': []},
              'parsed_at': utc_now(), 'error': ''}
    if not shutil.which('pdftotext') or not shutil.which('pdfinfo'):
        result.update(status='pdf_parser_unavailable', error='Poppler pdftotext/pdfinfo not installed')
        return result
    try:
        info = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True, timeout=30, check=True)
        match = re.search(r'^Pages:\s*(\d+)\s*$', info.stdout, re.M)
        if not match:
            raise ValueError('pdfinfo did not return a physical page count')
        total = int(match[1]); result['pages_total'] = total
        with tempfile.TemporaryDirectory(prefix='quarterly-pdf-') as temporary:
            target = Path(temporary) / 'full.txt'
            subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', str(path), str(target)],
                           capture_output=True, timeout=60, check=True)
            if target.stat().st_size > 10 * 1024**2:
                raise ResourceLimitError('quarterly_pdf_text_size_limit')
            text = target.read_text(encoding='utf-8')
        pages = text.split('\f')
        if pages and not pages[-1].strip():
            pages.pop()
        result['pages'] = [{'page': number, 'text': value.strip()} for number, value in enumerate(pages, 1)]
        result['pages_extracted'] = sum(bool(page.strip()) for page in pages)
        result['parse_status'] = 'complete' if len(pages) == total and result['pages_extracted'] else 'partial' if result['pages_extracted'] else 'no_text'
        if not result['pages_extracted']:
            result.update(status='no_text', error='PDF has no extractable text; OCR not performed')
            return result
        header = pages[0] if pages else ''
        candidates = [{'cnpj': normalize_cnpj(item.group()), 'page': 1,
                       'text': header[max(0, item.start()-250):item.end()+150].strip()}
                      for item in CNPJ_HEADER_RE.finditer(header)]
        result['identity']['header_fields'] = candidates
        exact = next((item for item in candidates if item['cnpj'] == expected), None)
        if exact:
            result['identity'].update(status='verified', header_cnpj=expected,
                                      basis='exact requested CNPJ in first physical page', page=1)
            source['identity_verified'] = True
            # Do not guess whether a PDF header's CNPJ is a fund or a class.
            result['identity']['cnpj_fundo'] = expected if re.search(r'\bFUNDO\b', exact['text'], re.I) else ''
            result['identity']['cnpj_classe'] = expected if re.search(r'\bCLASSE\b', exact['text'], re.I) else ''
            result['status'] = 'parsed' if result['parse_status'] == 'complete' else 'partial_parse'
        else:
            state = 'identity_mapping_pending' if candidates else 'identity_missing'
            result['identity']['status'] = state; result['status'] = state
            result['error'] = 'Expected CNPJ not found in the first physical page of the PDF'
        period = re.search(r'([1-4])\s*[º°o]?\s*TRIMESTRE\s*(?:DE\s*)?(20\d{2})', header, re.I)
        if period:
            declared = f'{period[2]}-Q{period[1]}'
            if result['quarter'] and declared != result['quarter']:
                result.update(status='competence_conflict', error='PDF header quarter differs from the document inventory reference date')
            result.update(quarter=declared, quarter_source='pdf_header')
    except ResourceLimitError:
        raise
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result.update(status='parse_error', error=f'{type(exc).__name__}: {exc}')
    return result


def select_documents(documents: list[dict], acquisition_pass: str) -> tuple[list[dict], list[str]]:
    quarterly = [dict(doc) for doc in documents if doc.get('classification') == 'informe_trimestral' and doc.get('id')]
    valid_quarters = sorted({quarter_key(doc.get('reference_date')) for doc in quarterly} - {''}, reverse=True)
    selected_quarters = valid_quarters if acquisition_pass == 'history' else valid_quarters[:1]
    selected = [doc for doc in quarterly if quarter_key(doc.get('reference_date')) in selected_quarters]
    selected.sort(key=lambda doc: (quarter_key(doc.get('reference_date')), doc_order(doc)), reverse=True)
    return selected, selected_quarters


def doc_order(doc):
    return (str(doc.get('provider_status', '')).upper().startswith('A'), int(doc.get('version') or 0),
            document_date_key(doc.get('delivery_date')), int(doc.get('id') or 0))


@dataclass
class Limits:
    timeout_seconds: int = 8
    attempts: int = 2
    max_download_bytes: int = 256 * 1024**2
    disk_floor_bytes: int = 10 * 1024**3
    max_document_bytes: int = 8 * 1024**2


class ResourceLimitError(RuntimeError):
    pass


class QuarterlyCollector:
    def __init__(self, root: Path, *, limits: Limits | None = None, client=None):
        self.root = root.resolve()
        self.base = self.root / 'data/documentary_diligence'
        self.cache = self.root / '.cache/documentary-quarterly'
        self.limits = limits or Limits()
        self.client = client or FundosNetClient(timeout_seconds=self.limits.timeout_seconds, max_retries=0)
        self.downloaded_bytes = 0

    def checkpoint(self, index: dict) -> None:
        """Keep private resume metadata and a portable audit snapshot together."""
        atomic_json(self.base / 'quarterly_index.json', index)
        atomic_json(self.base / 'audit_quarterly_index.json', public_document_payload(index))

    def room(self, chunk_bytes=0):
        self.base.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.base).free - chunk_bytes < self.limits.disk_floor_bytes:
            raise ResourceLimitError('disk_floor_reached')
        if self.downloaded_bytes + chunk_bytes > self.limits.max_download_bytes:
            raise ResourceLimitError('download_budget_reached')

    def catalog(self, cnpj: str, *, offline=False) -> tuple[list[dict], dict]:
        path = self.base / 'corpus' / f'{cnpj}.json'
        corpus = json.loads(path.read_text()) if path.exists() else {}
        searches = [search for search in corpus.get('searches', []) if search.get('source') == 'fundosnet'
                    and search.get('scope') == 'cnpj_all_fund_types' and search.get('cnpj_filter') == cnpj
                    and search.get('status') in {'found', 'no_results'}]
        if searches:
            return corpus.get('documents', []), {'source': 'fundosnet', 'scope': 'cnpj_all_fund_types',
                    'basis': 'completed_all_type_documentary_corpus', 'queried_at': searches[-1].get('queried_at'),
                    'status': searches[-1]['status'], 'url': searches[-1].get('url'), 'error': ''}
        if offline:
            return corpus.get('documents', []), {'source': 'local_inventory', 'scope': 'unverified_catalog_scope',
                    'basis': 'offline_local_inventory', 'queried_at': utc_now(), 'status': 'incomplete', 'error': 'No completed all-type FundosNet catalog; offline mode'}
        last_error = None
        for attempt in range(self.limits.attempts):
            try:
                self.room()
                docs = self.client.listar_documentos(cnpj, tipo_fundo='', error_stage='documentary_quarterly_catalog')
                rows = [{'id': doc.id, 'classification': 'informe_trimestral', 'title': doc.tipo,
                         'reference_date': doc.data_referencia, 'delivery_date': doc.data_entrega,
                         'version': doc.versao, 'provider_status': doc.status, 'url': document_url(doc.id)}
                        for doc in docs if 'trimestral' in doc.tipo.casefold()]
                return rows, {'source': 'fundosnet', 'scope': 'cnpj_all_fund_types', 'basis': 'fresh_exact_cnpj_query',
                              'queried_at': utc_now(), 'status': 'found' if rows else 'no_results', 'url': self.client._url('listarDocumentos'), 'error': ''}
            except ResourceLimitError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt + 1 < self.limits.attempts:
                    time.sleep(1)
        raise RuntimeError(f'quarterly catalog failed: {last_error}')

    def download(self, cnpj: str, document: dict) -> bytes:
        self.room()
        url = self.client._url('downloadDocumento', params={'id': str(document['id'])})
        request = urllib.request.Request(url, headers={'User-Agent': self.client.user_agent, 'Accept': 'application/xml,text/xml,text/plain,*/*'})
        self.cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile() as stream:
            total = 0
            with self.client.opener.open(request, timeout=self.limits.timeout_seconds) as response:
                declared = response.headers.get('Content-Length')
                for chunk in iter(lambda: response.read(CHUNK), b''):
                    self.room(len(chunk))
                    total += len(chunk)
                    self.downloaded_bytes += len(chunk)
                    if total > self.limits.max_document_bytes:
                        raise ResourceLimitError('encoded_document_size_limit')
                    stream.write(chunk)
                if declared and int(declared) != total:
                    raise ValueError('HTTP Content-Length differs from bytes received')
            stream.seek(0)
            raw = stream.read(self.limits.max_document_bytes + 1)
        payload = raw if raw.lstrip().startswith(b'<') else _decode_download_payload(raw)
        if len(payload) > MAX_XML_BYTES:
            raise ResourceLimitError('decoded_document_size_limit')
        # Preserve a returned PDF explicitly; XML extraction is not available for that format.
        if not payload.lstrip().startswith((b'<', b'%PDF')):
            raise ValueError('Response is neither XML nor PDF')
        suffix = '.pdf' if payload.lstrip().startswith(b'%PDF') else '.xml'
        target = self.cache / cnpj / (str(document['id']) + suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=target.name + '.', dir=target.parent)
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(payload)
            os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)
        return payload

    def process(self, cnpj: str, document: dict, *, offline=False, resume=True) -> dict:
        target = self.base / 'quarterly' / cnpj / f"{document['id']}.json"
        if resume and target.exists():
            old = json.loads(target.read_text())
            if old.get('status') == 'parsed' and old.get('transformation_version') == TRANSFORMATION_VERSION:
                return old
        cached = self.cache / cnpj / f"{document['id']}.xml"
        if cached.exists():
            if cached.stat().st_size > MAX_XML_BYTES:
                raise ResourceLimitError('cached_xml_size_limit')
            payload = cached.read_bytes()
        else:
            pdf = cached.with_suffix('.pdf')
            if pdf.exists():
                if pdf.stat().st_size > MAX_XML_BYTES:
                    raise ResourceLimitError('cached_pdf_size_limit')
                payload = pdf.read_bytes()
            elif offline:
                return {'cnpj': cnpj, 'status': 'not_acquired', 'error': 'XML not in local cache; network disabled', 'source': {'document_id': str(document['id'])}}
            else:
                error = None
                for attempt in range(self.limits.attempts):
                    try:
                        payload = self.download(cnpj, document)
                        error = None
                        break
                    except ResourceLimitError:
                        raise
                    except Exception as exc:
                        error = exc
                        if attempt + 1 < self.limits.attempts:
                            time.sleep(1)
                if error:
                    raise error
        if payload.lstrip().startswith(b'%PDF'):
            result = parse_quarterly_pdf(cached.with_suffix('.pdf'), cnpj, document)
        else:
            result = parse_quarterly_xml(payload, cnpj, document)
        atomic_json(target, result)
        return result

    def refresh(self, selected: list[str], *, acquisition_pass='current', offline=False, resume=True) -> dict:
        path = self.base / 'quarterly_index.json'
        index = json.loads(path.read_text()) if path.exists() else {'schema_version': 1, 'cnpjs': {}}
        index.update(selected_cnpjs=selected, acquisition_pass=acquisition_pass, run_state='running', started_at=utc_now(), stopped_reason='')
        for cnpj in selected:
            index['cnpjs'].setdefault(cnpj, {'documents': {}, 'status': 'not_processed'})
        self.checkpoint(index)
        for position, cnpj in enumerate(selected, 1):
            record = index['cnpjs'].setdefault(cnpj, {'documents': {}})
            try:
                documents, search = self.catalog(cnpj, offline=offline)
                chosen, quarters = select_documents(documents, acquisition_pass)
                all_quarterly = [doc for doc in documents if doc.get('classification') == 'informe_trimestral' and doc.get('id')]
                chosen_ids = {str(doc['id']) for doc in chosen}
                for document in all_quarterly:
                    key = str(document['id'])
                    previous = record['documents'].get(key, {})
                    record['documents'][key] = {**document, **previous, 'quarter': quarter_key(document.get('reference_date'))}
                    if key not in chosen_ids and not previous:
                        record['documents'][key].update(status='deferred_document', error='Historical quarter not acquired in current pass')
                record.update(search=search, selected_quarters=quarters, acquisition_pass=acquisition_pass,
                              catalog_count=len(all_quarterly), last_run_at=utc_now(), error='')
                for document in chosen:
                    key = str(document['id'])
                    try:
                        result = self.process(cnpj, document, offline=offline, resume=resume)
                        record['documents'][key].update(status=result['status'], error=result.get('error', ''),
                            path=str((Path('quarterly') / cnpj / f'{key}.json').as_posix()), source=result.get('source', {}), identity=result.get('identity', {}))
                    except ResourceLimitError as exc:
                        record['documents'][key].update(status='resource_limit', error=str(exc))
                        if str(exc) not in {'disk_floor_reached', 'download_budget_reached'}:
                            self.checkpoint(index)
                            continue
                        for pending in chosen:
                            pending_record = record['documents'][str(pending['id'])]
                            if not pending_record.get('status'):
                                pending_record.update(status='not_acquired_resource_limit', error=str(exc))
                        record['error'] = str(exc)
                        self.checkpoint(index)
                        raise
                    except Exception as exc:
                        record['documents'][key].update(status='parse_or_download_error', error=f'{type(exc).__name__}: {exc}')
                    self.checkpoint(index)
                record['by_quarter'] = {}
                for quarter in quarters:
                    group = [doc for doc in chosen if quarter_key(doc.get('reference_date')) == quarter]
                    ordered = sorted(group, key=doc_order, reverse=True)
                    record['by_quarter'][quarter] = {'document_ids': [str(doc['id']) for doc in ordered],
                        'effective_document_id': str(ordered[0]['id']) if ordered else None,
                        'selection_basis': 'active provider status, version, delivery date, document ID; all revisions retained'}
                record['status'] = 'catalog_incomplete' if search['status'] == 'incomplete' else 'no_reports_in_searched_catalog' if not all_quarterly else 'catalog_reference_date_unrecognized' if not quarters else 'processed'
                record['history_complete'] = acquisition_pass == 'history' and bool(quarters) and all(
                    doc.get('status') == 'parsed' for doc in record['documents'].values())
            except ResourceLimitError as exc:
                record.update(status='resource_limit', error=str(exc), last_run_at=utc_now())
                index.update(downloaded_bytes_this_run=self.downloaded_bytes, updated_at=utc_now(), stopped_reason=str(exc), run_state='resource_limit')
                self.checkpoint(index)
                raise
            except Exception as exc:
                record.update(status='catalog_error', error=f'{type(exc).__name__}: {exc}', last_run_at=utc_now())
            index.update(downloaded_bytes_this_run=self.downloaded_bytes, updated_at=utc_now(), acquisition_pass=acquisition_pass)
            self.checkpoint(index)
            counts = Counter(doc.get('status', 'inventory_only') for doc in record['documents'].values())
            print(f'[{position}/{len(selected)}] {cnpj}: {dict(counts)}', flush=True)
        index.update(run_state='processed', ended_at=utc_now())
        self.checkpoint(index)
        return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--only-cnpj', action='append', default=[])
    parser.add_argument('--resume', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--acquisition-pass', choices=('current', 'history'), default='current')
    parser.add_argument('--offline-reprocess', action='store_true')
    parser.add_argument('--network-timeout-seconds', type=int, default=8)
    parser.add_argument('--attempts', type=int, default=2)
    parser.add_argument('--max-download-gb', type=float, default=.25)
    parser.add_argument('--disk-floor-gb', type=float, default=10)
    args = parser.parse_args()
    if not args.all and not args.only_cnpj:
        parser.error('Use --all or --only-cnpj')
    if args.network_timeout_seconds < 1 or not 1 <= args.attempts <= 3 or min(args.max_download_gb, args.disk_floor_gb) < 0:
        parser.error('Invalid bounded resource settings')
    selected = set(load_registered_funds(args.root / 'portfolios.json')) if args.all else set()
    selected.update(normalize_cnpj(cnpj) for cnpj in args.only_cnpj)
    if any(len(cnpj) != 14 for cnpj in selected):
        parser.error('Every selected CNPJ must have fourteen digits')
    limits = Limits(timeout_seconds=args.network_timeout_seconds, attempts=args.attempts,
                    max_download_bytes=int(args.max_download_gb * 1024**3), disk_floor_bytes=int(args.disk_floor_gb * 1024**3))
    collector = QuarterlyCollector(args.root, limits=limits)
    try:
        result = collector.refresh(sorted(selected), acquisition_pass=args.acquisition_pass, offline=args.offline_reprocess, resume=args.resume)
    except ResourceLimitError as exc:
        parser.exit(2, f'Resource limit: {exc}; checkpoint retained in quarterly_index.json\n')
    print(f'Quarterly index: {len(result["cnpjs"])} CNPJs retained; downloaded {collector.downloaded_bytes} bytes', flush=True)


if __name__ == '__main__':
    main()
