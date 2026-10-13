import base64
import io
import json
from pathlib import Path
import tempfile
import shutil
import unittest
from unittest.mock import patch

from scripts.refresh_documentary_quarterly import (Limits, QuarterlyCollector, ResourceLimitError,
    parse_quarterly_xml, parse_quarterly_pdf, quarter_key, select_documents)


CNPJ = '63953620000165'
DOC = {'id': 123456, 'classification': 'informe_trimestral', 'reference_date': '06/2026',
       'delivery_date': '12/08/2026 12:00', 'version': 2, 'provider_status': 'AC'}
XML = b'''<?xml version="1.0" encoding="UTF-8"?><DOC_INF_FIDC>
<CAB_INFORM><NR_CNPJ_FUNDO>63.953.620/0001-65</NR_CNPJ_FUNDO><DT_COMPT>2026-06-30</DT_COMPT></CAB_INFORM>
<VERIFICACAO_LASTRO><PERIODICIDADE>Trimestral</PERIODICIDADE><QUANTIDADE>120</QUANTIDADE>
<LISTA><ITEM><OCORRENCIA>Documento ausente</OCORRENCIA></ITEM><ITEM><OCORRENCIA>Regular</OCORRENCIA></ITEM></LISTA>
</VERIFICACAO_LASTRO></DOC_INF_FIDC>'''


def pdf_bytes(page_texts):
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    children = []
    for text in page_texts:
        page_id, content_id = len(objects)+1, len(objects)+2
        children.append(f'{page_id} 0 R')
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>'.encode())
        content = f'BT /F1 12 Tf 72 720 Td ({text}) Tj ET'.encode()
        objects.append(f'<< /Length {len(content)} >>\nstream\n'.encode()+content+b'\nendstream')
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(children)}] /Count {len(page_texts)} >>".encode()
    pdf=bytearray(b'%PDF-1.4\n');offsets=[0]
    for number,value in enumerate(objects,1):
        offsets.append(len(pdf));pdf.extend(f'{number} 0 obj\n'.encode()+value+b'\nendobj\n')
    xref=len(pdf);pdf.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:pdf.extend(f'{offset:010d} 00000 n \n'.encode())
    pdf.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode())
    return bytes(pdf)


class Response(io.BytesIO):
    def __init__(self, data, declared=None):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data) if declared is None else declared)}


class Client:
    user_agent = 'test'
    def __init__(self, data=XML):
        self.data=data;self.calls=[];self.opener=self
    def _url(self, endpoint, params=None):return 'https://example.test/'+endpoint
    def open(self,request,timeout=None):
        self.calls.append(timeout);return Response(self.data)
    def listar_documentos(self,*args,**kwargs):raise AssertionError('Network catalog was not authorized in test')


class DocumentaryQuarterlyTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.client=Client();self.collector=QuarterlyCollector(self.root,client=self.client,limits=Limits(disk_floor_bytes=0))
    def tearDown(self):self.temporary.cleanup()

    def test_declared_fields_keep_xpath_repetitions_and_source(self):
        result=parse_quarterly_xml(XML,CNPJ,DOC)
        self.assertEqual('parsed',result['status']);self.assertTrue(result['source']['identity_verified'])
        self.assertEqual('2026-Q2',result['quarter']);self.assertEqual('123456',result['source']['document_id'])
        values=[f for f in result['fields'] if f['tag']=='OCORRENCIA']
        self.assertIn('/ITEM[1]/',values[0]['xpath']);self.assertIn('/ITEM[2]/',values[1]['xpath'])
        self.assertEqual('Documento ausente',values[0]['value']);self.assertNotIn('page',result['source'])

    def test_missing_header_cannot_be_replaced_by_debtor_identity(self):
        payload=b'<INFORM><DEVEDOR><CNPJ>'+CNPJ.encode()+b'</CNPJ></DEVEDOR></INFORM>'
        result=parse_quarterly_xml(payload,CNPJ,DOC)
        self.assertEqual('missing_header',result['status']);self.assertFalse(result['source']['identity_verified'])

    def test_divergent_header_is_mapping_pending_and_keeps_fields(self):
        result=parse_quarterly_xml(XML,'41970012000126',DOC)
        self.assertEqual('identity_mapping_pending',result['status']);self.assertTrue(result['fields'])
        self.assertFalse(result['source']['identity_verified'])

    def test_exact_class_identity_and_namespace_are_preserved(self):
        payload=b'<n:INFORM xmlns:n="urn:cvm"><n:CAB_INFORM><n:NR_CNPJ_FUNDO>11111111000111</n:NR_CNPJ_FUNDO><n:NR_CNPJ_CLASSE>'+CNPJ.encode()+b'</n:NR_CNPJ_CLASSE></n:CAB_INFORM></n:INFORM>'
        result=parse_quarterly_xml(payload,CNPJ,DOC)
        self.assertEqual('parsed',result['status']);self.assertEqual(CNPJ,result['identity']['cnpj_classe'])

    def test_fiagro_dados_gerais_header_uses_explicit_quarter_end(self):
        payload=b'<DadosEconomicoFinanceiros><DadosGerais><CNPJFundo>'+CNPJ.encode()+b'</CNPJFundo><Competencia>2/2026</Competencia><DataEncerTrimestre>2026-06-30</DataEncerTrimestre></DadosGerais></DadosEconomicoFinanceiros>'
        result=parse_quarterly_xml(payload,CNPJ,DOC)
        self.assertEqual('parsed',result['status']);self.assertEqual('2026-Q2',result['quarter'])
        self.assertEqual('2026-06-30',result['competence'])
        self.assertEqual('/DadosEconomicoFinanceiros[1]/DadosGerais[1]/CNPJFundo[1]',result['identity']['header_fields'][0]['xpath'])

    def test_quarter_conflict_is_not_parsed_or_reassigned(self):
        result=parse_quarterly_xml(XML.replace(b'2026-06-30',b'2026-03-31'),CNPJ,DOC)
        self.assertEqual('competence_conflict',result['status']);self.assertEqual('2026-Q1',result['quarter'])

    def test_latest_quarter_keeps_all_revisions_and_history_keeps_earlier(self):
        docs=[DOC,{**DOC,'id':123457,'version':3},{**DOC,'id':100000,'reference_date':'03/2026'}]
        selected,quarters=select_documents(docs,'current')
        self.assertEqual([123457,123456],[d['id'] for d in selected]);self.assertEqual(['2026-Q2'],quarters)
        selected,quarters=select_documents(docs,'history');self.assertEqual(3,len(selected))
        self.assertEqual('2026-Q2',quarter_key('30/06/2026'))

    def test_completed_all_type_catalog_is_reused_without_network(self):
        directory=self.root/'data/documentary_diligence/corpus';directory.mkdir(parents=True)
        (directory/f'{CNPJ}.json').write_text(json.dumps({'documents':[DOC],'searches':[{'source':'fundosnet','scope':'cnpj_all_fund_types','cnpj_filter':CNPJ,'status':'found','queried_at':'2026-10-13'}]}))
        docs,search=self.collector.catalog(CNPJ)
        self.assertEqual(1,len(docs));self.assertEqual('completed_all_type_documentary_corpus',search['basis'])

    def test_streamed_base64_is_decoded_and_resume_never_fetches_again(self):
        self.client.data=b'"'+base64.b64encode(XML)+b'"'
        first=self.collector.process(CNPJ,DOC);self.assertEqual('parsed',first['status'])
        self.assertEqual(1,len(self.client.calls));self.assertTrue((self.collector.cache/CNPJ/'123456.xml').exists())
        self.collector.process(CNPJ,DOC);self.assertEqual(1,len(self.client.calls))

    @unittest.skipUnless(shutil.which('pdftotext') and shutil.which('pdfinfo'), 'Poppler required')
    def test_pdf_response_preserves_physical_pages_without_xml_fields(self):
        self.client.data=pdf_bytes(['FUNDO CNPJ 63.953.620/0001-65 2 TRIMESTRE 2026','Lastro: 120 direitos analisados, 2 documentos ausentes.'])
        result=self.collector.process(CNPJ,DOC)
        self.assertEqual('parsed',result['status']);self.assertEqual([],result['fields'])
        self.assertEqual('complete',result['parse_status']);self.assertEqual(2,result['pages_total'])
        self.assertEqual(2,result['pages'][1]['page']);self.assertIn('2 documentos ausentes',result['pages'][1]['text'])
        self.assertNotIn('xpath',result['source']);self.assertEqual('quarterly_pdf',result['source']['type'])
        self.assertTrue((self.collector.cache/CNPJ/'123456.pdf').exists())

    @unittest.skipUnless(shutil.which('pdftotext') and shutil.which('pdfinfo'), 'Poppler required')
    def test_pdf_identity_conflict_and_no_text_are_explicit(self):
        path=self.root/'report.pdf';path.write_bytes(pdf_bytes(['FUNDO CNPJ 41.970.012/0001-26']))
        result=parse_quarterly_pdf(path,CNPJ,DOC)
        self.assertEqual('identity_mapping_pending',result['status']);self.assertFalse(result['source']['identity_verified'])
        path.write_bytes(pdf_bytes(['']))
        result=parse_quarterly_pdf(path,CNPJ,DOC)
        self.assertEqual('no_text',result['status']);self.assertEqual(1,result['pages_total'])

    @unittest.skipUnless(shutil.which('pdftotext') and shutil.which('pdfinfo'), 'Poppler required')
    def test_pdf_cnpj_with_layout_spaces_retains_exact_identity(self):
        path=self.root/'spaced.pdf';path.write_bytes(pdf_bytes(['FUNDO CNPJ 63.953.620/0001- 65']))
        result=parse_quarterly_pdf(path,CNPJ,DOC)
        self.assertEqual('parsed',result['status']);self.assertEqual(CNPJ,result['identity']['header_cnpj'])

    def test_resource_floor_prevents_download_and_keeps_old_cache(self):
        cache=self.collector.cache/CNPJ;cache.mkdir(parents=True);target=cache/'123456.xml';target.write_bytes(XML)
        self.collector.limits.disk_floor_bytes=10
        with patch('scripts.refresh_documentary_quarterly.shutil.disk_usage') as usage:
            usage.return_value.free=1
            with self.assertRaises(ResourceLimitError):self.collector.download(CNPJ,DOC)
        self.assertEqual(XML,target.read_bytes());self.assertEqual([],self.client.calls)

    def test_no_headers_and_dtd_are_never_invented(self):
        result=parse_quarterly_xml(b'<INFORM><CAB_INFORM><NOME>Fundo</NOME></CAB_INFORM></INFORM>',CNPJ,DOC)
        self.assertEqual('identity_missing',result['status'])
        with self.assertRaises(ValueError):parse_quarterly_xml(b'<!DOCTYPE FOO [<!ENTITY x "anything">]><FOO>&x;</FOO>',CNPJ,DOC)

    def test_offline_refresh_preserves_prior_documents(self):
        base=self.collector.base;base.mkdir(parents=True)
        (base/'quarterly_index.json').write_text(json.dumps({'schema_version':1,'cnpjs':{CNPJ:{'documents':{'99999':{'id':99999,'status':'parsed'}}}}}))
        with patch.object(self.collector,'catalog',return_value=([DOC],{'status':'incomplete','scope':'unverified_catalog_scope'})):
            result=self.collector.refresh([CNPJ],offline=True)
        self.assertIn('99999',result['cnpjs'][CNPJ]['documents'])
        self.assertEqual('not_acquired',result['cnpjs'][CNPJ]['documents']['123456']['status'])
        self.assertEqual('catalog_incomplete',result['cnpjs'][CNPJ]['status'])

    def test_public_checkpoint_keeps_relative_reference_and_removes_private_paths(self):
        record={'schema_version':1,'run_state':'resource_limit','stopped_reason':'download_budget_reached',
                'cnpjs':{CNPJ:{'documents':{'123456':{**DOC,'path':f'quarterly/{CNPJ}/123456.json',
                 'inventory_sources':['/Users/example/fidc/.cache/raw.pdf'],
                 'local_path':'/Users/example/fidc/.cache/raw.pdf','text_path':'/Users/example/fidc/.cache/raw.txt',
                 'source':{'document_id':'123456','url':'https://example.test/123456','sha256':'abc'}}}}}}
        self.collector.checkpoint(record)
        private=json.loads((self.collector.base/'quarterly_index.json').read_text())
        public=json.loads((self.collector.base/'audit_quarterly_index.json').read_text())
        self.assertIn('inventory_sources',private['cnpjs'][CNPJ]['documents']['123456'])
        document=public['cnpjs'][CNPJ]['documents']['123456']
        self.assertEqual(f'quarterly/{CNPJ}/123456.json',document['path'])
        self.assertNotIn('inventory_sources',document);self.assertNotIn('local_path',document);self.assertNotIn('text_path',document)
        self.assertEqual('resource_limit',public['run_state']);self.assertEqual('abc',document['source']['sha256'])


if __name__=='__main__':unittest.main()
