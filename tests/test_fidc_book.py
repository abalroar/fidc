from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re
import unittest

from services.fidc_book import load_fidc_book_index
from services.fidc_monitoring import build_mini_glossary_df


ROOT = Path(__file__).resolve().parents[1]
BOOK_ROOT = ROOT / "docs" / "fidc"
DATA_ROOT = BOOK_ROOT / "_data"
REPORT_ROOT = ROOT / "reports" / "glossario_100_fidcs_20260716"


def _payload(filename: str) -> dict:
    return json.loads((DATA_ROOT / filename).read_text(encoding="utf-8"))


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


class FIDCBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = load_fidc_book_index()

    def test_load_book_index_exposes_revised_corpus(self) -> None:
        self.assertEqual(len(self.index.pages), 18)
        self.assertGreaterEqual(len(self.index.sections), 8)
        self.assertGreaterEqual(len(self.index.concepts), 45)
        self.assertGreaterEqual(len(self.index.metrics), 25)
        self.assertEqual(len(self.index.reference_funds), 10)
        self.assertEqual(len(self.index.document_entries), 16)
        self.assertIn("rcvm_175_page", self.index.sources)
        self.assertIn("cvm_dados_abertos_fidc", self.index.sources)
        self.assertNotIn("seller_regulamento", self.index.sources)

    def test_all_indexed_pages_exist_and_load(self) -> None:
        expected_new_pages = {
            "informe-mensal-tabela-ii",
            "reforcos-revolvencia-liquidez",
            "instrumentos-garantias-concentracao",
            "referencias",
        }
        self.assertTrue(expected_new_pages.issubset({page.page_id for page in self.index.pages}))
        for page in self.index.pages:
            path = self.index.resolve_page_path(page)
            self.assertTrue(path.is_file(), page.relative_path)
            markdown = self.index.load_page_markdown(page)
            self.assertTrue(markdown.startswith("# "), page.page_id)
            self.assertGreater(len(markdown), 300, page.page_id)

    def test_overview_uses_current_terminology(self) -> None:
        markdown = self.index.load_page_markdown(self.index.page_by_id("overview"))
        self.assertIn("Guia de uso do Glossário de FIDCs", markdown)
        self.assertIn("segmento oficial da Tabela II do Informe Mensal", markdown)
        self.assertIn("taxonomia funcional documental", markdown)
        self.assertIn("Sem segmentação IME", markdown)
        self.assertNotIn("Informe Mensal Estruturado", markdown)

    def test_ids_are_unique_and_cross_references_exist(self) -> None:
        raw_groups = [
            (_payload("sources.json")["sources"], "source_id"),
            (_payload("concepts.json")["concepts"], "concept_id"),
            (_payload("metrics.json")["metrics"], "metric_id"),
            (_payload("reference_funds.json")["funds"], "fund_id"),
            (_payload("document_index.json")["documents"], "document_id"),
        ]
        page_items = [
            page
            for section in _payload("book_index.json")["sections"]
            for page in section["pages"]
        ]
        raw_groups.append((page_items, "page_id"))
        for items, key in raw_groups:
            values = [item[key] for item in items]
            self.assertEqual(len(values), len(set(values)), f"IDs duplicados em {key}")

        page_ids = {page.page_id for page in self.index.pages}
        source_ids = set(self.index.sources)
        for source in _payload("sources.json")["sources"]:
            location = source.get("location", "")
            if location and not location.startswith(("https://", "http://")):
                self.assertTrue((ROOT / location).is_file(), location)
        for page in self.index.pages:
            self.assertTrue(set(page.source_ids).issubset(source_ids), page.page_id)
        for entry in (*self.index.concepts, *self.index.metrics, *self.index.reference_funds):
            self.assertTrue(set(entry.page_ids).issubset(page_ids), entry)
            self.assertTrue(set(entry.source_ids).issubset(source_ids), entry)
        for document in self.index.document_entries:
            self.assertIn(document.source_id, source_ids)
            self.assertTrue(set(document.page_ids).issubset(page_ids), document.document_id)

    def test_declared_local_documents_exist(self) -> None:
        for document in self.index.document_entries:
            self.assertTrue(document.local_status, document.document_id)
            if document.local_path:
                path = ROOT / document.local_path
                self.assertTrue(path.is_file(), document.local_path)
                self.assertRegex(document.sha256, r"^[0-9a-f]{64}$")
                actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(actual_sha256, document.sha256, document.local_path)
                self.assertIsNotNone(document.pages)
                self.assertGreater(document.pages or 0, 0)

    def test_narrative_reference_funds_match_structured_json(self) -> None:
        markdown = self.index.load_page_markdown(self.index.page_by_id("fundos-de-referencia"))
        table_rows = [
            line
            for line in markdown.splitlines()
            if line.startswith("|") and re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", line)
        ]
        narrative_cnpjs = {_digits(line.split("|")[2]) for line in table_rows}
        structured_cnpjs = {fund.cnpj for fund in self.index.reference_funds}
        self.assertEqual(len(table_rows), 10)
        self.assertEqual(narrative_cnpjs, structured_cnpjs)
        for fund in self.index.reference_funds:
            self.assertIn(fund.title, markdown)
            self.assertIn("fundos-de-referencia", fund.page_ids)
            self.assertEqual(fund.last_verified, "2026-07-16")

    def test_search_finds_aliases_without_accents_and_essential_terms(self) -> None:
        cases = {
            "endossante": "cessao-e-resolucao",
            "first payment default": "provisao-perdas-e-inadimplencia",
            "write off": "provisao-perdas-e-inadimplencia",
            "segmentacao ime": "informe-mensal-tabela-ii",
            "subtipo funcional documental": "informe-mensal-tabela-ii",
            "classe subordinada": "classes-cotas-waterfall",
            "revolving period": "reforcos-revolvencia-liquidez",
            "auditoria de lastro": "lastro-rating-reporting",
        }
        for query, expected_page in cases.items():
            page_ids = {page.page_id for page in self.index.search_pages(query)}
            self.assertIn(expected_page, page_ids, query)

    def test_related_documents_concepts_and_metrics_are_consistent(self) -> None:
        page = self.index.page_by_id("metricas-estruturais")
        concept_ids = {concept.concept_id for concept in self.index.related_concepts(page)}
        metric_ids = {metric.metric_id for metric in self.index.related_metrics(page)}
        document_ids = {entry.document_id for entry in self.index.related_documents(page)}
        self.assertIn("subordinacao", concept_ids)
        self.assertIn("indice_cobertura", metric_ids)
        self.assertIn("fnet_reg_830304", document_ids)

    def test_metrics_have_formula_numerator_denominator_and_unit(self) -> None:
        for metric in self.index.metrics:
            self.assertTrue(metric.formula, metric.metric_id)
            self.assertTrue(metric.numerator, metric.metric_id)
            self.assertTrue(metric.denominator, metric.metric_id)
            self.assertTrue(metric.unit, metric.metric_id)
            self.assertTrue(metric.source_ids, metric.metric_id)

    def test_mini_glossary_is_derived_from_canonical_book_entries(self) -> None:
        glossary = build_mini_glossary_df()
        expected = {
            entry.mini_glossary_title or entry.title: entry.mini_glossary_definition
            for entry in (*self.index.concepts, *self.index.metrics)
            if entry.mini_glossary_order is not None and entry.mini_glossary_definition
        }
        actual = dict(zip(glossary["termo"], glossary["definicao"], strict=True))
        self.assertEqual(actual, expected)
        self.assertIn("Subordinação reportada (IME)", actual)
        self.assertIn("Sem segmentação IME", actual)
        self.assertIn("acima de 1.080 dias", actual["Aging da inadimplência"])
        self.assertNotIn("Quanto maior, mais protegido", " ".join(actual.values()))

    def test_selection_ledger_has_exactly_100_unique_funds(self) -> None:
        with (REPORT_ROOT / "selection_100.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        cnpjs = [row["cnpj_fundo"] for row in rows]
        self.assertEqual(len(rows), 100)
        self.assertEqual(len(set(cnpjs)), 100)
        self.assertTrue(all(re.fullmatch(r"\d{14}", cnpj) for cnpj in cnpjs))
        self.assertTrue(all(float(row["pl_agregado"]) > 0 for row in rows))
        self.assertTrue(all(row["pl_classes_reconciliado"] == "True" for row in rows))

    def test_occupied_segments_are_represented_and_manifest_reconciles(self) -> None:
        with (REPORT_ROOT / "selection_coverage_by_subtype.csv").open(encoding="utf-8", newline="") as handle:
            coverage = list(csv.DictReader(handle))
        self.assertTrue(coverage)
        self.assertTrue(all(int(float(row["fundos_industria"])) > 0 for row in coverage))
        self.assertTrue(all(int(float(row["fundos_selecionados"])) > 0 for row in coverage))
        manifest = json.loads((REPORT_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["competencia_snapshot"], "202605")
        self.assertEqual(manifest["sample"]["n_fundos"], 100)
        self.assertAlmostEqual(manifest["snapshot_reconciliation"]["residuo_reconciliacao"], 0.0, places=2)
        self.assertIn("Marcas e patentes", manifest["segmentos_oficiais_sem_populacao"])

    def test_versioned_audit_artifacts_match_manifest_hashes(self) -> None:
        manifest = json.loads((REPORT_ROOT / "manifest.json").read_text(encoding="utf-8"))
        expected = {
            "selection_100.csv",
            "selection_coverage_by_subtype.csv",
            "document_coverage.csv",
            "evidence_long.csv",
            "term_candidates.csv",
            "glossary_gap_matrix.csv",
            "methodology.md",
            "glossary_change_log.md",
            "glossary_review_report.md",
        }
        self.assertEqual(set(manifest["artifact_sha256"]), expected)
        for name, declared_hash in manifest["artifact_sha256"].items():
            path = REPORT_ROOT / name
            self.assertTrue(path.is_file(), name)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), declared_hash, name)

    def test_all_100_funds_have_explicit_document_status(self) -> None:
        allowed = {"lido", "ausente", "não aplicável", "inacessível", "OCR necessário", "cache-only"}
        with (REPORT_ROOT / "document_coverage.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        by_fund: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            by_fund.setdefault(row["cnpj_fundo"], []).append(row)
            self.assertIn(row["read_status"], allowed)
        self.assertEqual(len(by_fund), 100)
        for cnpj, fund_rows in by_fund.items():
            priorities = {row["prioridade_documental"] for row in fund_rows}
            self.assertIn("regulamento vigente", priorities, cnpj)


if __name__ == "__main__":
    unittest.main()
