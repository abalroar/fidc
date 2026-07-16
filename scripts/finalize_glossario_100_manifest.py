"""Acrescenta estatísticas finais e hashes ao manifesto do Glossário de 100 FIDCs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "glossario_100_fidcs_20260716"
BOOK_DATA = ROOT / "docs" / "fidc" / "_data"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest_path = REPORT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selection = pd.read_csv(REPORT / "selection_100.csv", dtype={"cnpj_fundo": str})
    documents = pd.read_csv(
        REPORT / "document_coverage.csv",
        dtype={"cnpj_fundo": str, "documento_id": str},
        low_memory=False,
    )
    evidence = pd.read_csv(REPORT / "evidence_long.csv", low_memory=False)
    candidates = pd.read_csv(REPORT / "term_candidates.csv", low_memory=False)
    gaps = pd.read_csv(REPORT / "glossary_gap_matrix.csv", low_memory=False)
    current = documents[documents["prioridade_documental"] == "regulamento vigente"]
    current_read_funds = set(current.loc[current["read_status"] == "lido", "cnpj_fundo"])
    sample_pl = float(selection["pl_agregado"].sum())
    current_read_pl = float(selection.loc[selection["cnpj_fundo"].isin(current_read_funds), "pl_agregado"].sum())
    read_documents = documents[documents["read_status"] == "lido"].copy()
    read_unique_sha = read_documents[read_documents["sha256"].fillna("") != ""].drop_duplicates("sha256")
    substantive_funds = {
        "09195235000150", "26286939000158", "26287464000114", "28169275000172",
        "29225241000110", "42922136000107", "50906397000153", "52242420000188",
        "52610624000124", "53216449000158", "53263761000100", "53286499000101",
        "62393679000183", "63700113000110", "63953619000130",
    }
    substantive_pl = float(selection.loc[selection["cnpj_fundo"].isin(substantive_funds), "pl_agregado"].sum())

    def count_priority(priority: str, status: str = "lido") -> int:
        mask = documents["prioridades_documentais"].fillna("").str.split(";").map(lambda values: priority in values)
        return int(documents[mask & (documents["read_status"] == status)]["documento_id"].nunique())

    manifest["schema_version"] = "glossario-100-fidcs/v2"
    manifest["document_corpus"] = {
        "funds_with_explicit_status": int(documents["cnpj_fundo"].nunique()),
        "canonical_ledger_rows": int(len(documents)),
        "unique_primary_document_ids": int(documents["documento_id"].notna().sum()),
        "documents_read_page_by_page": int(read_documents["documento_id"].nunique()),
        "unique_sha256_read": int(read_unique_sha["sha256"].nunique()),
        "pages_read_unique_sha256": int(read_unique_sha["pages"].fillna(0).sum()),
        "documents_ocr_required": int((documents["read_status"] == "OCR necessário").sum()),
        "documents_inaccessible": int((documents["read_status"] == "inacessível").sum()),
        "missing_priority_requests": int((documents["read_status"] == "ausente").sum()),
        "funds_with_current_regulation_read": int(len(current_read_funds)),
        "funds_current_regulation_absent": int((current["read_status"] == "ausente").sum()),
        "funds_current_regulation_inaccessible": int((current["read_status"] == "inacessível").sum()),
        "current_regulation_pl_coverage": current_read_pl / sample_pl,
        "funds_with_any_document_read": int(read_documents["cnpj_fundo"].nunique()),
        "rating_reports_read": count_priority("relatório de rating"),
        "financial_statements_read": count_priority("demonstrações financeiras"),
        "monthly_or_quarterly_reports_read": count_priority("relatório mensal ou trimestral"),
        "prospectuses_or_fact_sheets_read": count_priority("prospecto ou lâmina"),
        "substantive_regulations_manually_reviewed": len(substantive_funds),
        "substantive_review_pl_fund_level": substantive_pl,
        "substantive_review_pl_share_sample": substantive_pl / sample_pl,
        "visual_checks": [
            "RCVM 175 Anexo II, páginas físicas 22 a 24",
            "Cielo 1017493, páginas 55 e 106",
            "Aetos 794164, páginas 40 e 45",
            "PagSeguro 1149521, página 19",
            "Monee 1159092, página 58",
            "MT Global 1222863, página 5",
            "Multiplike 1223029, página 55",
            "Seller 909547, página 46",
            "VTK 1002580, páginas 114 e 118",
            "RED Performance 1127150, página 67",
            "RED Real 1090771, página 51"
        ],
    }
    manifest["evidence_matrix"] = {
        "atomic_rows": int(len(evidence)),
        "term_candidate_rows": int(len(candidates)),
        "gap_matrix_rows": int(len(gaps)),
        "contractual_prevalence_denominator_funds": 15,
        "independent_document_families": 12,
        "fic_fidc_excluded_from_underlying_credit_prevalence": True,
        "literal_excess_spread_occurrences_in_15_regulations": 0,
    }
    manifest["glossary_after_review"] = {
        "pages": sum(len(section["pages"]) for section in json.loads((BOOK_DATA / "book_index.json").read_text())["sections"]),
        "concepts": len(json.loads((BOOK_DATA / "concepts.json").read_text())["concepts"]),
        "metrics": len(json.loads((BOOK_DATA / "metrics.json").read_text())["metrics"]),
        "reference_funds": len(json.loads((BOOK_DATA / "reference_funds.json").read_text())["funds"]),
        "sources": len(json.loads((BOOK_DATA / "sources.json").read_text())["sources"]),
        "indexed_primary_documents": len(json.loads((BOOK_DATA / "document_index.json").read_text())["documents"]),
    }
    manifest["legacy_inventory_audit"] = {
        "document_inventory_rows": 3521,
        "pdfs_declared_local_but_missing": 1501,
        "existing_txt_revalidated": 571,
        "existing_json_revalidated": 1449,
        "legacy_estudo_paths_removed_from_glossary": 13,
        "fidc_local_inventory_declared_paths_missing": 9645,
        "regulatory_knowledge_downloaded_source_files_missing": 1445,
        "text_cache_document_id_equals_cnpj_rows": 571,
    }
    artifact_names = [
        "selection_100.csv",
        "selection_coverage_by_subtype.csv",
        "document_coverage.csv",
        "evidence_long.csv",
        "term_candidates.csv",
        "glossary_gap_matrix.csv",
        "methodology.md",
        "glossary_change_log.md",
        "glossary_review_report.md",
    ]
    manifest["artifact_sha256"] = {name: _sha256(REPORT / name) for name in artifact_names}
    manifest["limitations"] = [
        "Sem segmentação IME é estrato de qualidade de dados, não subtipo oficial.",
        "A flag FIC-FIDC ampliada é inferida da denominação e não substitui validação documental.",
        "Quinze documentos permanecem com OCR necessário; nenhum sustenta afirmação categórica do glossário.",
        "Cinco fundos não tiveram regulamento vigente processado: três sem documento listado e dois com falha de download; todos têm status explícito e ao menos outro documento primário processado.",
        "Frequências contratuais usam 15 regulamentos substantivos e 12 famílias de template, não os 100 como denominador artificial.",
        "A revisão é exaustiva em relação ao corpus e às normas verificadas, não universalmente completa."
    ]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(manifest["document_corpus"])


if __name__ == "__main__":
    main()
