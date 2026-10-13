from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch, Mock

from services.documentary_corpus import DocumentaryCorpus, ResourceLimits, corpus_classification, load_registered_funds, current_document_ids, text_extraction_quality


class DocumentaryCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cnpj = "63953620000165"
        self.limits = ResourceLimits(disk_floor_bytes=0)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def corpus(self) -> DocumentaryCorpus:
        return DocumentaryCorpus(self.root, limits=self.limits)

    def test_normal_clone_default_is_this_checkout_only(self) -> None:
        (self.root/'.git').mkdir()
        self.assertEqual((self.root.resolve(),),self.corpus().source_roots)

    def test_managed_worktree_reuses_shared_repository_without_personal_path(self) -> None:
        original=self.root/'repository';common=original/'.git';worktree=self.root/'managed';worktree.mkdir()
        administrative=common/'worktrees/managed';administrative.mkdir(parents=True)
        (administrative/'commondir').write_text('../..')
        (worktree/'.git').write_text(f'gitdir: {administrative}\n')
        corpus=DocumentaryCorpus(worktree,limits=self.limits)
        self.assertEqual((worktree.resolve(),original.resolve()),corpus.source_roots)

    def test_portfolio_deduplication_preserves_memberships(self) -> None:
        path = self.root / "portfolios.json"
        path.write_text(json.dumps({"portfolios": [{"id": name, "name": name, "funds": [{"cnpj": self.cnpj}]} for name in ("A", "B")]}))
        funds = load_registered_funds(path)
        self.assertEqual(1, len(funds))
        self.assertEqual(2, len(funds[self.cnpj]["portfolios"]))

    def test_categories_include_lastro_and_class_annex(self) -> None:
        self.assertEqual("lastro", corpus_classification({"tipo": "Relatório de verificação de lastro"}))
        self.assertEqual("anexo", corpus_classification({"categoria": "Anexo ao Regulamento"}))
        self.assertEqual("demonstracoes_financeiras", corpus_classification({"tipo": "Demonstrações Financeiras - Fusão"}))

    def test_local_acervo_is_referenced_not_copied_and_hash_duplicates_merge(self) -> None:
        source = self.root / "data/raw/industry_large_funds" / self.cnpj
        source.mkdir(parents=True)
        pdf = b"%PDF-1.4\nfixture"
        for name in ("1222863_regulamento.pdf", "1222863_regulamento_copy.pdf"):
            (source / name).write_bytes(pdf)
        corpus = self.corpus()
        with patch.object(corpus, "_parse") as parse:
            payload = corpus.refresh(self.cnpj)
        self.assertEqual(1, len(payload["documents"]))
        self.assertEqual(2, len(payload["documents"][0]["local_sources"]))
        self.assertEqual(1, parse.call_count)
        self.assertFalse((self.root / "data/documentary_diligence/raw").exists())
        self.assertTrue((self.root / "data/documentary_diligence/corpus" / f"{self.cnpj}.json").exists())

    def test_acquired_raw_pdf_remains_discoverable_without_private_index(self) -> None:
        directory=self.root/'data/documentary_diligence/raw'/self.cnpj;directory.mkdir(parents=True)
        path=directory/'1222863_regulamento.pdf';path.write_bytes(b'%PDF-1.4\nfixture')
        corpus=self.corpus()
        with patch.object(corpus,'_parse'):
            payload=corpus.refresh(self.cnpj,resume=False)
        self.assertEqual(1,len(payload['documents']))
        self.assertEqual(str(path.resolve()),payload['documents'][0]['local_path'])
        self.assertEqual('regulamento',payload['documents'][0]['classification'])

    def test_incomplete_legacy_extraction_is_not_rule_or_complete_text(self) -> None:
        directory = self.root / "data/regulatory_extractions" / self.cnpj
        directory.mkdir(parents=True)
        (directory / "1222863.local.json").write_text(json.dumps({"document_id": 1222863, "classification": "regulamento",
            "source_file": "data/raw/missing.pdf", "criteria": [{"name": "Foo", "threshold_value": 0.5}]}))
        payload = self.corpus().refresh(self.cnpj)
        doc = payload["documents"][0]
        self.assertEqual("legacy_excerpts_only", doc["parse_status"])
        self.assertNotIn("criteria", doc)
        self.assertEqual("inventory_only", doc["download_status"])

    def test_generic_review_does_not_erase_known_regulation_category(self) -> None:
        directory = self.root / "data/regulatory_knowledge"
        directory.mkdir(parents=True)
        (directory / f"{self.cnpj}.json").write_text(json.dumps({"documents": [{"id": 1222863, "classification": "regulamento",
            "categoria": "Regulamento"}], "sources_reviewed": [{"document_id": 1222863, "path": "1222863_documentary_review.pdf"}]}))
        payload = self.corpus().refresh(self.cnpj)
        self.assertEqual("regulamento", payload["documents"][0]["classification"])

    def test_filename_date_is_retained_with_unverified_provenance(self) -> None:
        source = self.root / "data/raw" / self.cnpj
        source.mkdir(parents=True)
        (source / "1222863_regulamento_2026-06-02.pdf").write_bytes(b"%PDF-1.4\nfixture")
        corpus = self.corpus()
        with patch.object(corpus, "_parse"):
            doc = corpus.refresh(self.cnpj)["documents"][0]
        self.assertEqual("2026-06-02", doc["reference_date"])
        self.assertEqual("filename_unverified", doc["reference_date_provenance"])

    def test_mentions_stay_candidates_with_source_reference(self) -> None:
        directory = self.root / "data/regulatory_profiles/documentary_comparisons"
        directory.mkdir(parents=True)
        (directory / f"{self.cnpj}.json").write_text(json.dumps({"facts": {"comparison_eligibility": {"Natureza": {
            "value": "FIC-FIDC investido Mercado Crédito II CNPJ 41.970.012/0001-26", "source": "ID 123456 · p. 12"}}}}))
        candidate = self.corpus().refresh(self.cnpj)["relationship_candidates"][0]
        self.assertEqual("41970012000126", candidate["candidate_cnpj"])
        self.assertEqual("candidate_requires_primary_validation", candidate["status"])
        self.assertEqual("ID 123456 · p. 12", candidate["source_reference"])

    def test_download_stream_accepts_direct_and_quoted_base64(self) -> None:
        pdf = b"%PDF-1.7\n" + b"fixture" * 20000
        for wire in (pdf, b'"' + base64.b64encode(pdf) + b'"'):
            with self.subTest(encoded=wire != pdf):
                output = BytesIO()
                self.corpus()._stream_pdf_response(BytesIO(wire), output, len(wire))
                self.assertEqual(pdf, output.getvalue())

    def test_download_rejects_html_and_truncated_content_length(self) -> None:
        for wire, advertised in ((b"<html>blocked</html>", 0), (b"%PDF-1.7\nfixture", 100)):
            with self.assertRaises(ValueError):
                self.corpus()._stream_pdf_response(BytesIO(wire), BytesIO(), advertised)

    def test_download_budget_is_a_resource_state(self) -> None:
        corpus = self.corpus()
        corpus.limits.max_download_bytes = 2
        with self.assertRaisesRegex(RuntimeError, "download_budget_reached"):
            corpus._stream_pdf_response(BytesIO(b"%PDF-1.7\nfixture"), BytesIO())

    def test_corrupt_pdf_character_map_is_distinct_from_portuguese_accents(self) -> None:
        path=self.root/'extracted.txt'
        path.write_text(('Demonstrações contábeis; provisão; crédito; câmbio; informação.\n'*100)+'\f')
        self.assertEqual('no_strong_encoding_warning',text_extraction_quality(path)['status'])
        path.write_text(('ZĞůĂƚſƌŝŽ\x03WƌŽǀŝƐĆŽ\x03'*150)+'\f')
        quality=text_extraction_quality(path)
        self.assertEqual('encoding_suspect',quality['status'])
        self.assertEqual(300,quality['unexpected_controls'])

    def test_resume_cannot_promote_unreadable_character_map_to_complete(self) -> None:
        corpus=self.corpus();pdf=self.root/'source.pdf';pdf.write_bytes(b'%PDF-1.4\nfixture')
        text=self.root/'full.txt';text.write_text(('ZĞůĂƚſƌŝŽ\x03WƌŽǀŝƐĆŽ\x03'*150)+'\f')
        item={'local_path':str(pdf),'text_path':str(text),'sha256':'a'*64}
        with patch('services.documentary_corpus.shutil.which',return_value='/test/parser'),patch('services.documentary_corpus.subprocess.run',return_value=Mock(returncode=0,stdout='Pages: 1\n',stderr='')) as run:
            corpus._parse(self.cnpj,item,resume=True)
        self.assertEqual('unreadable_text',item['parse_status']);self.assertEqual(1,item['pages_total']);self.assertEqual(1,item['pages_extracted'])
        self.assertEqual('text_character_map_corruption',item['error']);self.assertEqual(1,run.call_count)

    def test_ocr_resume_preserves_method_and_excluded_page_quality(self) -> None:
        corpus=self.corpus();pdf=self.root/'source.pdf';pdf.write_bytes(b'%PDF-1.4\nfixture')
        text=self.root/'ocr.txt';text.write_text('Página1: créditos elegíveis.\fPágina2: leitura visual incompleta.\f')
        item={'local_path':str(pdf),'text_path':str(text),'sha256':'a'*64,'parse_method':'vision_ocr',
              'ocr_excluded_pages':[2],'ocr_quality':{'engine':'Apple Vision','excluded_pages':[2]}}
        with patch('services.documentary_corpus.shutil.which',return_value='/test/parser'),patch('services.documentary_corpus.subprocess.run',return_value=Mock(returncode=0,stdout='Pages: 2\n',stderr='')):
            corpus._parse(self.cnpj,item,resume=True)
        self.assertEqual('vision_ocr',item['parse_method']);self.assertEqual([2],item['ocr_excluded_pages'])
        self.assertEqual('Apple Vision',item['ocr_quality']['engine']);self.assertEqual('partial',item['parse_status'])
        self.assertEqual(str(text),item['text_path'])

    def test_catalog_merge_preserves_cached_ocr_metadata_by_hash(self) -> None:
        corpus=self.corpus();directory=self.root/'data/documentary_diligence/raw'/self.cnpj;directory.mkdir(parents=True)
        pdf=directory/'1222863_regulamento.pdf';pdf.write_bytes(b'%PDF-1.4\nfixture')
        text=self.root/'ocr.txt';text.write_text('Regulamento legível por OCR.\f')
        previous={'documents':[{'id':1222863,'sha256':corpus._hash(pdf),'local_path':str(pdf),
                  'text_path':str(text),'parse_status':'partial','pages_total':1,'pages_extracted':1,
                  'parse_method':'vision_ocr','ocr_quality':{'engine':'Apple Vision'},'ocr_excluded_pages':[1]}]}
        corpus.prepare([self.cnpj])
        with patch.object(corpus,'_parse'):
            result=corpus._discover_local(self.cnpj,{'1222863':corpus._blank_document(1222863)},previous,resume=True)
        self.assertEqual('vision_ocr',result[0]['parse_method']);self.assertEqual([1],result[0]['ocr_excluded_pages'])
        self.assertEqual('Apple Vision',result[0]['ocr_quality']['engine']);self.assertEqual(str(text),result[0]['text_path'])

    def test_same_document_id_new_pdf_hash_discards_old_ocr_fields(self) -> None:
        corpus=self.corpus();directory=self.root/'data/documentary_diligence/raw'/self.cnpj;directory.mkdir(parents=True)
        pdf=directory/'1222863_regulamento.pdf';pdf.write_bytes(b'%PDF-1.4\nnew content')
        old={**corpus._blank_document(1222863),'classification':'regulamento','sha256':'a'*64,
             'local_path':str(pdf),'text_path':'old-ocr.txt','parse_method':'apple_vision_ocr',
             'ocr_quality':{'source_sha256':'a'*64},'ocr_excluded_pages':[1]}
        corpus.prepare([self.cnpj])
        with patch.object(corpus,'_parse'):
            result=corpus._discover_local(self.cnpj,{'1222863':dict(old)},{'documents':[old]},resume=True)
        self.assertEqual(corpus._hash(pdf),result[0]['sha256'])
        self.assertNotIn('text_path',result[0]);self.assertNotIn('parse_method',result[0]);self.assertNotIn('ocr_quality',result[0])

    def test_changed_catalog_version_cannot_promote_old_cached_pdf(self) -> None:
        corpus=self.corpus();directory=self.root/'data/documentary_diligence/raw'/self.cnpj;directory.mkdir(parents=True)
        pdf=directory/'1222863_regulamento.pdf';pdf.write_bytes(b'%PDF-1.4\nold content')
        old={**corpus._blank_document(1222863),'classification':'regulamento','sha256':corpus._hash(pdf),
             'local_path':str(pdf),'parse_status':'complete','version':1,'reference_date':'2026-01-31','delivery_date':'2026-02-01'}
        observed={**corpus._blank_document(1222863),'classification':'regulamento','version':2,
                  'reference_date':'2026-03-31','delivery_date':'2026-04-01'}
        corpus.prepare([self.cnpj])
        with patch.object(corpus,'_parse') as parse:
            result=corpus._discover_local(self.cnpj,{'1222863':observed},{'documents':[old]},resume=True)
        parse.assert_not_called();self.assertEqual('catalog_version_conflict',result[0]['parse_status'])
        self.assertEqual(1,result[0]['file_catalog_metadata']['version'])
        self.assertEqual(2,result[0]['version']);self.assertEqual('conflict',result[0]['catalog_file_binding'])
        self.assertEqual(b'%PDF-1.4\nold content',pdf.read_bytes())

    def test_download_new_hash_preserves_old_pdf_and_clears_old_ocr(self) -> None:
        corpus=self.corpus();corpus.client=Mock();corpus.client.user_agent='test'
        old_path=corpus.base/'raw'/self.cnpj/'external-change_outro.pdf';old_path.parent.mkdir(parents=True)
        old_path.write_bytes(b'%PDF-1.4\nold content')
        item={**corpus._blank_document(None),'id':'external-change','url':'https://example.test/new.pdf',
              'local_path':str(old_path),'sha256':corpus._hash(old_path),'text_path':'old-ocr.txt',
              'parse_method':'apple_vision_ocr','ocr_quality':{'source_sha256':corpus._hash(old_path)}}
        response=BytesIO(b'%PDF-1.4\nnew content');response.headers={}
        corpus.client.opener.open.return_value=response
        with patch.object(corpus,'_parse'):
            corpus._download(self.cnpj,item)
        self.assertEqual(b'%PDF-1.4\nold content',old_path.read_bytes())
        self.assertNotEqual(str(old_path),item['local_path']);self.assertNotIn('text_path',item);self.assertNotIn('ocr_quality',item)
        self.assertEqual('verified_download',item['catalog_file_binding'])
        self.assertEqual(1,len(item['local_versions']))

    @unittest.skipUnless(shutil.which("pdfinfo") and shutil.which("pdftotext"), "Poppler required")
    def test_complete_pdf_over_eighty_pages_is_not_truncated_and_resume_reuses_text(self) -> None:
        source = self.root / "data/raw" / self.cnpj
        source.mkdir(parents=True)
        page_count = 81
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
        children = []
        for page in range(page_count):
            page_id, content_id = len(objects) + 1, len(objects) + 2
            children.append(f"{page_id} 0 R")
            objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode())
            content = f"BT /F1 12 Tf 72 720 Td (Page {page + 1}) Tj ET".encode()
            objects.append(f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream")
        objects[1] = f"<< /Type /Pages /Kids [{' '.join(children)}] /Count {page_count} >>".encode()
        pdf = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for number, value in enumerate(objects, 1):
            offsets.append(len(pdf))
            pdf.extend(f"{number} 0 obj\n".encode() + value + b"\nendobj\n")
        startxref = len(pdf)
        pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode())
        pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF".encode())
        (source / "1222863_regulamento.pdf").write_bytes(pdf)
        corpus = self.corpus()
        payload = corpus.refresh(self.cnpj)
        doc = payload["documents"][0]
        self.assertEqual("complete", doc["parse_status"])
        self.assertEqual(page_count, doc["pages_total"])
        self.assertEqual(page_count, doc["pages_extracted"])
        text = Path(doc["text_path"])
        self.assertIn("Page 81", text.read_text())
        modified = text.stat().st_mtime_ns
        self.assertEqual("complete", corpus.refresh(self.cnpj)["documents"][0]["parse_status"])
        self.assertEqual(modified, text.stat().st_mtime_ns)

    def test_unavailable_network_preserves_prior_inventory(self) -> None:
        corpus = self.corpus()
        corpus.base.joinpath("corpus").mkdir(parents=True)
        previous = {"documents": [corpus._blank_document(123456)]}
        (corpus.base / "corpus" / f"{self.cnpj}.json").write_text(json.dumps(previous))
        search = {"source": "fundosnet", "url": "test", "queried_at": "2026-10-13", "status": "error", "error": "timeout"}
        with patch.object(corpus, "_network_catalog", return_value=([], search)), patch.object(corpus, "_download"):
            payload = corpus.refresh(self.cnpj, network=True)
        self.assertEqual(123456, payload["documents"][0]["id"])
        self.assertIn(search, payload["searches"])

    def test_current_acquisition_orders_dates_and_keeps_regulation_amendment_and_class_annexes(self) -> None:
        documents = [
            {"id": 100001, "classification": "regulamento", "title": "Regulamento", "reference_date": "31/01/2026", "provider_status": "AC"},
            {"id": 100002, "classification": "regulamento", "title": "Regulamento", "reference_date": "02/06/2026", "provider_status": "AC"},
            {"id": 100003, "classification": "regulamento", "title": "Instrumento Particular de Alteração do Regulamento", "reference_date": "02/06/2026", "provider_status": "AC"},
            {"id": 100004, "classification": "regulamento", "title": "Regulamento", "reference_date": "12/10/2026", "provider_status": "CC"},
            {"id": 100005, "classification": "anexo", "title": "Anexo ao Regulamento", "reference_date": "03/06/2026", "fund_or_class_name": "Classe A"},
            {"id": 100006, "classification": "anexo", "title": "Anexo ao Regulamento", "reference_date": "04/06/2026", "fund_or_class_name": "Classe B"},
        ]
        self.assertEqual({"100002", "100003", "100005", "100006"}, current_document_ids(documents))

    def test_current_defers_history_and_history_reuses_successful_catalog(self) -> None:
        corpus = self.corpus()
        rows = [{"id": number, "categoria": "Regulamento" if number != 100003 else "Assembleia", "tipo": "", "data_referencia": reference,
                 "data_entrega": reference, "versao": 1, "status": "AC"} for number, reference in
                [(100001, "31/01/2026"), (100002, "02/06/2026"), (100003, "04/06/2026")]]
        search = {"source": "fundosnet", "url": "test", "queried_at": "2026-10-13", "status": "found", "error": "",
                  "scope": "cnpj_all_fund_types", "cnpj_filter": self.cnpj, "tipo_fundo": "all"}
        with patch.object(corpus, "_network_catalog", return_value=(rows, search)), patch.object(corpus, "_download") as download:
            current = corpus.refresh(self.cnpj, network=True, acquisition_pass="current")
        self.assertEqual([100002], [call.args[1]["id"] for call in download.call_args_list])
        self.assertEqual(2, sum(doc["download_status"] == "deferred_document" for doc in current["documents"]))
        self.assertFalse(current["history_complete"])
        with patch.object(corpus, "_network_catalog") as catalog, patch.object(corpus, "_download") as download:
            history = corpus.refresh(self.cnpj, network=True, acquisition_pass="history")
        catalog.assert_not_called()
        self.assertEqual({100001, 100002, 100003}, {call.args[1]["id"] for call in download.call_args_list})
        self.assertFalse(history["history_complete"])

    def test_catalog_queries_exact_cnpj_without_fidc_type_filter(self) -> None:
        corpus = self.corpus()
        corpus.client = Mock()
        corpus.client.listar_documentos.return_value = []
        _, search = corpus._network_catalog(self.cnpj)
        corpus.client.listar_documentos.assert_called_once_with(self.cnpj, tipo_fundo="", error_stage="documentary_corpus_catalog")
        self.assertEqual("cnpj_all_fund_types", search["scope"])
        self.assertEqual(self.cnpj, search["cnpj_filter"])

    def test_older_unknown_scope_catalog_does_not_skip_full_cnpj_search(self) -> None:
        corpus = self.corpus()
        corpus.base.joinpath("corpus").mkdir(parents=True)
        previous = {"documents": [], "searches": [{"source": "fundosnet", "status": "found"}]}
        (corpus.base / "corpus" / f"{self.cnpj}.json").write_text(json.dumps(previous))
        search = {"source": "fundosnet", "status": "found", "scope": "cnpj_all_fund_types", "cnpj_filter": self.cnpj}
        with patch.object(corpus, "_network_catalog", return_value=([], search)) as catalog:
            corpus.refresh(self.cnpj, network=True, skip_successful_network=True, acquisition_pass="history")
        catalog.assert_called_once_with(self.cnpj)

    def test_external_document_identifier_orders_without_integer_conversion(self) -> None:
        external = {"id": "JGP-SolAgoraII-Oferta-20231222", "classification": "regulamento", "reference_date": "2023-12-22"}
        self.assertEqual({external['id']}, current_document_ids([external]))
        corpus = self.corpus()
        corpus.base.joinpath("corpus").mkdir(parents=True)
        item = {**corpus._blank_document(123456), **external, "url": "https://www.jgp.com.br/official.pdf"}
        (corpus.base / "corpus" / f"{self.cnpj}.json").write_text(json.dumps({"documents": [item]}))
        with patch.object(corpus, "_network_catalog", return_value=([], {"status": "found"})), patch.object(corpus, "_download") as download:
            corpus.refresh(self.cnpj, network=True)
        self.assertEqual(item['id'], download.call_args.args[1]['id'])

    def test_external_document_uses_authoritative_url_without_provider_token(self) -> None:
        corpus = self.corpus();corpus.client = Mock()
        response = BytesIO(b"%PDF-1.7\nfixture");response.headers = {}
        corpus.client.opener.open.return_value = response
        item = {**corpus._blank_document(123456), "id": "JGP-SolAgoraII-Oferta-20231222", "url": "https://www.jgp.com.br/official.pdf"}
        with patch.object(corpus, "_parse"):
            corpus._download(self.cnpj, item)
        request = corpus.client.opener.open.call_args.args[0]
        self.assertEqual(item['url'], request.full_url)
        self.assertNotIn('Csrftoken', request.headers)
        corpus.client._url.assert_not_called()
        self.assertEqual('downloaded', item['download_status'])

    def test_cached_external_pdf_keeps_identifier_and_does_not_duplicate(self) -> None:
        corpus = self.corpus()
        cache = self.root / '.cache/external' / self.cnpj;cache.mkdir(parents=True)
        path = cache / 'JGP-SolAgoraII-Oferta-20231222.pdf';path.write_bytes(b'%PDF-1.7\nfixture')
        item = {**corpus._blank_document(123456), 'id':'JGP-SolAgoraII-Oferta-20231222', 'classification':'emissao',
                'local_path':str(path), 'sha256':corpus._hash(path)}
        corpus.base.joinpath('corpus').mkdir(parents=True)
        (corpus.base/'corpus'/f'{self.cnpj}.json').write_text(json.dumps({'documents':[item]}))
        with patch.object(corpus,'_parse'):
            payload = corpus.refresh(self.cnpj)
        self.assertEqual(1,len(payload['documents']))
        self.assertEqual(item['id'],payload['documents'][0]['id'])
        self.assertEqual('emissao',payload['documents'][0]['classification'])

    def test_quarterly_cache_does_not_erase_prior_inventory_classification(self) -> None:
        corpus = self.corpus()
        cache = self.root/'.cache/documentary-quarterly'/self.cnpj;cache.mkdir(parents=True)
        path=cache/'123456.pdf';path.write_bytes(b'%PDF-1.7\nfixture')
        item={**corpus._blank_document(123456),'classification':'informe_trimestral','reference_date':'06/2026'}
        corpus.base.joinpath('corpus').mkdir(parents=True)
        (corpus.base/'corpus'/f'{self.cnpj}.json').write_text(json.dumps({'documents':[item]}))
        with patch.object(corpus,'_parse'):
            payload=corpus.refresh(self.cnpj)
        self.assertEqual('informe_trimestral',payload['documents'][0]['classification'])


if __name__ == "__main__":
    unittest.main()
