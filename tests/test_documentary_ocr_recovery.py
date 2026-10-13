import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.recover_documentary_ocr import OCRRecovery, OCRLimits, OCRResourceLimit, select_documents, ocr_resume_valid
from services.documentary_corpus import sha256_file


class DocumentaryOCRRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.cnpj='62310468000130';self.base=self.root/'data/documentary_diligence'
        self.pdf=self.root/'source.pdf';self.pdf.write_bytes(b'%PDF-1.4\nfixture')
        self.document={'id':1153514,'classification':'regulamento','local_path':str(self.pdf),
                       'sha256':sha256_file(self.pdf),'parse_status':'unreadable_text','pages_total':2,
                       'url':'https://example.test/1153514','reference_date':'2026-04-01'}
        self.path=self.base/'corpus'/f'{self.cnpj}.json';self.path.parent.mkdir(parents=True)
        self.save([self.document]);self.calls=[];self.page=0;self.low_page=None;self.fail_page=None;self.image_side=1754
        self.recovery=OCRRecovery(self.root,limits=OCRLimits(disk_floor_bytes=0),runner=self.runner)
        self.recovery.engine=lambda:Path('recognize_fixture')

    def tearDown(self):self.temporary.cleanup()
    def save(self,documents):self.path.write_text(json.dumps({'cnpj':self.cnpj,'documents':documents}))
    def runner(self,command,**kwargs):
        self.calls.append(command)
        if command[0]=='pdfinfo':return SimpleNamespace(stdout='Pages: 2\n')
        if command[0]=='pdftoppm':
            self.page=int(command[command.index('-f')+1])
            Path(command[-1]+'.png').write_bytes(b'\x89PNG\r\n\x1a\n'+(13).to_bytes(4,'big')+b'IHDR'+(1240).to_bytes(4,'big')+self.image_side.to_bytes(4,'big'))
            return SimpleNamespace()
        if self.page==self.fail_page:raise subprocess.TimeoutExpired(command,25)
        confidence=.8 if self.page==self.low_page else 1.0
        Path(command[2]).write_text(json.dumps({'lines':[{'text':'Os direitos creditórios são originados de empréstimos consignados.',
                         'confidence':confidence,'x':.1,'y':.7,'height':.02}]}))
        return SimpleNamespace()

    def test_unreadable_selector_and_explicit_id_keep_exact_scope(self):
        complete={**self.document,'id':1153512,'parse_status':'complete'}
        self.save([self.document,complete])
        self.assertEqual([(self.path,'1153514')],select_documents(self.root,all_unreadable=True))
        self.assertEqual([],select_documents(self.root,cnpjs=['08692888000182']))
        self.assertEqual([(self.path,'1153512')],select_documents(self.root,cnpjs=[self.cnpj],document_ids=['1153512']))
        self.assertEqual([],select_documents(self.root,all_unreadable=True,document_ids=['1153512']))

    def test_page_budget_does_not_start_or_silently_truncate_document(self):
        self.recovery.limits.max_pages=1
        with self.assertRaisesRegex(OCRResourceLimit,'page_budget_reached'):self.recovery.recover(self.path,'1153514')
        self.assertEqual(1,len(self.calls));self.assertEqual('pdfinfo',self.calls[0][0])
        self.assertEqual('unreadable_text',json.loads(self.path.read_text())['documents'][0]['parse_status'])

    def test_disk_floor_prevents_native_calls(self):
        self.recovery.limits.disk_floor_bytes=10
        with patch('scripts.recover_documentary_ocr.shutil.disk_usage') as usage:
            usage.return_value.free=1
            with self.assertRaisesRegex(OCRResourceLimit,'disk_floor_reached'):self.recovery.recover(self.path,'1153514')
        self.assertEqual([],self.calls)

    def test_serial_recovery_preserves_pdf_hash_pages_and_resumes_without_engine(self):
        first=self.recovery.recover(self.path,'1153514')
        document=json.loads(self.path.read_text())['documents'][0]
        self.assertEqual('complete',document['parse_status']);self.assertEqual('apple_vision_ocr',document['parse_method'])
        self.assertEqual(self.document['sha256'],document['sha256']);self.assertEqual(2,len(document['ocr_quality']['pages']))
        self.assertEqual(2,self.recovery.pages_used);self.assertEqual(5,len(self.calls))
        self.assertTrue(ocr_resume_valid(document,self.pdf))
        result=self.recovery.recover(self.path,'1153514');self.assertEqual('resumed_existing_ocr',result['status'])
        self.assertEqual(5,len(self.calls));self.assertEqual(first['source_sha256'],result['source_sha256'])
        audit=json.loads((self.base/'audit_corpus'/self.path.name).read_text())
        self.assertNotIn('local_path',audit['documents'][0]);self.assertNotIn('text_path',audit['documents'][0])

    def test_low_confidence_keeps_page_but_excludes_automatic_use(self):
        self.low_page=2;self.recovery.recover(self.path,'1153514')
        document=json.loads(self.path.read_text())['documents'][0]
        self.assertEqual('partial',document['parse_status']);self.assertEqual([2],document['ocr_excluded_pages'])
        self.assertEqual(2,Path(document['text_path']).read_text().count('\f'))
        self.assertEqual('not_certified',document['ocr_quality']['human_review'])

    def test_interrupted_page_resumes_checkpoint_without_repeating_first_page(self):
        self.fail_page=2
        with self.assertRaises(subprocess.TimeoutExpired):self.recovery.recover(self.path,'1153514')
        self.assertEqual('unreadable_text',json.loads(self.path.read_text())['documents'][0]['parse_status'])
        self.fail_page=None;self.calls.clear();self.recovery.recover(self.path,'1153514')
        rendered=[int(command[command.index('-f')+1]) for command in self.calls if command[0]=='pdftoppm']
        self.assertEqual([2],rendered)
        self.assertEqual('complete',json.loads(self.path.read_text())['documents'][0]['parse_status'])

    def test_source_hash_mismatch_cannot_replace_primary_text(self):
        self.pdf.write_bytes(b'%PDF-1.4\nchanged')
        with self.assertRaisesRegex(ValueError,'sha256_mismatch'):self.recovery.recover(self.path,'1153514')
        self.assertEqual([],self.calls)

    def test_oversized_page_is_not_sent_to_vision(self):
        self.image_side=10000
        with self.assertRaisesRegex(OCRResourceLimit,'rendered_page_pixel_limit'):self.recovery.recover(self.path,'1153514')
        self.assertEqual(['pdfinfo','pdftoppm'],[command[0] for command in self.calls])
        self.assertEqual(0,self.recovery.pages_used)

    def test_ocr_cannot_certify_cached_pdf_after_catalog_version_changed(self):
        self.document.update(catalog_file_binding='conflict',version=2,
                             file_catalog_metadata={'version':1,'reference_date':'2026-01-31'})
        self.save([self.document])
        with self.assertRaisesRegex(ValueError,'version_conflict_requires_document_acquisition'):
            self.recovery.recover(self.path,'1153514')
        self.assertEqual([],self.calls)

    def test_recovered_ocr_carries_pdf_hash_and_catalog_binding(self):
        self.document['version']=1;self.save([self.document]);self.recovery.recover(self.path,'1153514')
        document=json.loads(self.path.read_text())['documents'][0]
        self.assertEqual(document['sha256'],document['ocr_quality']['source_sha256'])
        self.assertEqual(1,document['ocr_quality']['source_catalog_metadata']['version'])
        document['version']=2
        self.assertFalse(ocr_resume_valid(document,self.pdf))


if __name__=='__main__':unittest.main()
