#!/usr/bin/env python3
"""Produce a reproducible acceptance report without changing documentary data."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
from hashlib import sha256
from io import StringIO
import csv
import json
import os
import re
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_documentary_diligence import iso_date, material_answer, primary_source, source_locator
from services.documentary_criteria_catalog import CRITERIA, LEGACY_MAP
from services.documentary_diligence import (
    criterion_has_answer, criterion_is_documented_not_applicable, criterion_status, load_documentary_corpus,
    load_documentary_fund, public_document_payload, source_is_traceable,
)
from services.documentary_ime_comparison import build_documentary_observations, resolve_documentary_reference
from services.portfolio_store import PortfolioRecord


PAIR_IDS = frozenset(LEGACY_MAP.values())
LABELS = {key: (label, theme) for key, theme, label, _expressions in CRITERIA}
for old_label, key in LEGACY_MAP.items():
    LABELS.setdefault(key, (old_label, "Critério do quadro anterior"))
BEFORE_LIMIT = (
    "Reconstrução dos pareceres antigos pelo LEGACY_MAP, com valor substantivo, ID citado, URL primária, SHA256 "
    "e processamento completo registrados no inventário público ou local; páginas fora da extensão física conhecida são recusadas. "
    "A aplicabilidade antiga não era modelada. O denominador é o catálogo atual conservador, incluindo os critérios "
    "anteriores ausentes do arquivo publicado. O locator é reconstruído na coleção atual; isso não prova que o "
    "documento tivesse sido obtido em 07/10/2026. O número mede afirmações antigas "
    "rastreáveis reconstruídas, sem certificar revisão semântica ou disponibilidade em 07/10/2026."
)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {} if default is None else default


def atomic_bytes(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def csv_bytes(rows: list[dict], columns: tuple[str, ...] | None = None) -> bytes:
    stream = StringIO()
    fields = list(columns or (rows[0].keys() if rows else ()))
    if fields:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def supported_not_applicable(item: dict) -> bool:
    return criterion_is_documented_not_applicable(item)


def reported_criteria(fund: dict) -> tuple[list[dict], set[str]]:
    """Retain the former questions even when their missing rows disappeared."""
    published = {item["criterion_id"]: item for item in fund.get("criteria", [])}
    expected = {item[0] for item in CRITERIA} | PAIR_IDS | set(published)
    result, synthetic = [], set()
    for key in sorted(expected):
        item = published.get(key)
        if item is None:
            label, theme = LABELS.get(key, (key, "Critério específico"))
            item = {"criterion_id": key, "label": label, "theme": theme, "applicability": "unresolved", "status": "extraction_pending", "value": None, "sources": [],
                    "reason": "Pergunta do comparativo anterior ou do catálogo comum ainda sem registro no arquivo publicado; mantida no denominador e nas pendências.",
                    "risk_note": "Critério reintroduzido apenas no relatório de aceite; não representa cláusula extraída."}
            synthetic.add(key)
        result.append(item)
    return result, synthetic


def before_answers(review: dict, documents: list[dict]) -> dict[str, dict]:
    result = {}
    for _theme, facts in review.get("facts", {}).items():
        if not isinstance(facts, dict):
            continue
        for label, fact in facts.items():
            key = LEGACY_MAP.get(label)
            if key is None or not isinstance(fact, dict) or not material_answer(fact.get("value")):
                continue
            sources = reconstruct_before_sources(fact, documents)
            if not any(source_is_traceable(source) for source in sources):
                continue
            result[key] = {"value": fact.get("value"), "sources": sources, "original_label": label}
    return result


def reconstruct_before_sources(fact: dict, documents: list[dict]) -> list[dict]:
    """Reconstruct old citations identically from local and portable inventories.

    A local filesystem path is operational state, not additional proof of a
    historical answer. Require the portable acquisition/parsing evidence for
    both inventories so removing private paths cannot change the coverage.
    """
    text = str(fact.get("source") or "")
    note = str(fact.get("note") or "")
    ids = re.findall(r"\bID\s*(\d{5,})", text, re.I)
    if not ids:
        ids = re.findall(r"(?:id=|/)(\d{5,})(?:[_&\s]|$)", text)
    reference_date = iso_date(text)
    page, clause = source_locator(text + " " + note)
    if not ids or not reference_date or not (page or clause) or text.startswith(("Corpus", "Consulta", "Inventário")):
        return []
    candidates = {str(doc.get("id") or doc.get("document_id")): doc for doc in documents}
    result = []
    for ident in dict.fromkeys(ids):
        doc = candidates.get(ident)
        if not doc or doc.get("parse_status") != "complete":
            continue
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(doc.get("sha256") or "")):
            continue
        if not re.match(r"^https?://", str(doc.get("url") or "")):
            continue
        pages_total = doc.get("pages_total")
        cited_pages = [int(number) for number in re.findall(r"\d+", str(page or ""))]
        if pages_total and cited_pages and (min(cited_pages) < 1 or max(cited_pages) > int(pages_total)):
            continue
        source = primary_source(doc, page=page, clause=clause)
        source["reference_date"] = source["reference_date"] or reference_date
        source["citation_original"] = text
        source["verification"] = "historical_citation_reconstructed_current_collection"
        if source_is_traceable(source):
            result.append(source)
    return result


def _ratio(numerator: int, denominator: int):
    return numerator / denominator if denominator else None


def _percent(value) -> str:
    return f"{value * 100:.1f}%".replace(".", ",") if value is not None else "sem denominador"


def coverage_row(fund: dict, before: dict, membership: dict, *, registered: bool):
    criteria, synthetic = reported_criteria(fund)
    excluded = {item["criterion_id"] for item in criteria if supported_not_applicable(item)}
    denominator_ids = {item["criterion_id"] for item in criteria} - excluded
    applicable = sum(item.get("applicability") == "applicable" and item["criterion_id"] not in excluded for item in criteria)
    unresolved = len(denominator_ids) - applicable
    answered_ids = {item["criterion_id"] for item in criteria if item.get("applicability") == "applicable" and criterion_has_answer(item)} - excluded
    before_ids = set(before) & denominator_ids
    paired_denominator = denominator_ids & PAIR_IDS
    paired_before = before_ids & PAIR_IDS
    paired_after = answered_ids & PAIR_IDS
    provenances = Counter(item.get("provenance") or "unclassified" for item in criteria if item["criterion_id"] in answered_ids)
    row = {
        "cnpj": fund["cnpj"], "name": fund.get("name", ""), "registered": registered,
        "portfolio_count": len(membership.get(fund["cnpj"], [])), "portfolio_ids": " | ".join(p["id"] for p in membership.get(fund["cnpj"], [])),
        "published_criteria_count": len(fund.get("criteria", [])), "acceptance_criteria_count": len(criteria),
        "reintroduced_missing_criteria": len(synthetic), "applicable": applicable, "applicability_unresolved": unresolved,
        "documented_not_applicable": len(excluded), "denominator": len(denominator_ids),
        "before_reconstructed_answered": len(before_ids), "after_answered": len(answered_ids),
        "before_expanded_ratio": _ratio(len(before_ids), len(denominator_ids)), "after_expanded_ratio": _ratio(len(answered_ids), len(denominator_ids)),
        "paired_denominator": len(paired_denominator), "paired_before_answered": len(paired_before), "paired_after_answered": len(paired_after),
        "paired_before_ratio": _ratio(len(paired_before), len(paired_denominator)), "paired_after_ratio": _ratio(len(paired_after), len(paired_denominator)),
        "pending": len(denominator_ids) - len(answered_ids), "primary_passage_answered": provenances.get("primary_passage", 0),
        "previous_review_answered": provenances.get("previous_review_with_primary_locator", 0), "verified_override_answered": provenances.get("verified_override", 0),
        "other_provenance_answered": sum(v for k, v in provenances.items() if k not in {"primary_passage", "previous_review_with_primary_locator", "verified_override"}),
        "reviewed_at": fund.get("reviewed_at", ""),
    }
    return row, criteria, excluded, answered_ids, synthetic


def pending_rows(fund: dict, criteria: list[dict], excluded: set[str], answered: set[str], synthetic: set[str], corpus: dict, membership: dict):
    rows = []
    for item in criteria:
        key = item["criterion_id"]
        if key in excluded or key in answered:
            continue
        status = item.get("status") or "extraction_pending"
        reasons = [str(item.get("reason") or "").strip(), str(item.get("risk_note") or "").strip()]
        if item.get("applicability") == "not_applicable":
            status = "extraction_pending"
            reasons.append("Não aplicabilidade sem fundamento documental suficiente; exclusão do denominador recusada.")
        if item.get("status") == "confirmed" and not criterion_has_answer(item):
            reasons.append("Afirmação declarada como confirmada sem valor substantivo ou fonte com documento, data e página/cláusula válidos.")
        if item.get("applicability") != "applicable":
            reasons.append("Aplicabilidade permanece em apuração e está incluída no denominador conservador.")
        reason = " ".join(dict.fromkeys(reason for reason in reasons if reason))
        if not reason:
            reason = f"Estado {status} declarado sem justificativa individual; exigir leitura da pergunta {item.get('label') or key} nos documentos identificados para este CNPJ."
        rows.append({
            "cnpj": fund["cnpj"], "fund": fund.get("name", ""), "criterion_id": key, "criterion": item.get("label", key), "theme": LABELS.get(key, (key, item.get("theme", "")))[1],
            "applicability": "unresolved" if item.get("applicability") != "applicable" else "applicable", "status": status,
            "status_label": criterion_status({**item, "status": status, "applicability": "unresolved" if item.get("applicability") == "not_applicable" else item.get("applicability")}),
            "reason": reason, "reintroduced_in_acceptance": key in synthetic,
            "portfolio_ids": " | ".join(p["id"] for p in membership.get(fund["cnpj"], [])),
            "sources": json.dumps(public_document_payload(item.get("sources", [])), ensure_ascii=False),
            "acquisition_ledger": f"acquisition_by_fund.csv#cnpj={fund['cnpj']}",
            "corpus_reference": f"data/documentary_diligence/audit_corpus/{fund['cnpj']}.json",
        })
    return rows


def acquisition_row(fund: dict, corpus: dict, registered: bool, quarterly: dict | None = None, *, quarterly_ledger="quarterly_index.json"):
    documents = corpus.get("documents") or []
    downloads = Counter(d.get("download_status") or "unclassified" for d in documents)
    parses = Counter(d.get("parse_status") or "unclassified" for d in documents)
    searches = corpus.get("searches") or []
    pending = corpus.get("pending_sources") or fund.get("corpus_status", {}).get("pending_sources", [])
    corpus_reference = f"data/documentary_diligence/audit_corpus/{fund['cnpj']}.json"
    quarterly_documents = (quarterly or {}).get("documents", {})
    quarterly_states = Counter(doc.get("status") or "unclassified" for doc in quarterly_documents.values())
    quarterly_formats = Counter((doc.get("source") or {}).get("type") or "unknown" for doc in quarterly_documents.values())
    return {"cnpj": fund["cnpj"], "name": fund.get("name", ""), "registered": registered,
            "documents_inventoried": len(documents), "local_or_downloaded": sum(downloads[s] for s in ("local_available", "downloaded")),
            "complete_texts": parses.get("complete", 0), "parse_failed": sum(v for k, v in parses.items() if k in {"failed", "parse_failed", "error", "no_text", "unreadable_text"}),
            "unreadable_text": parses.get("unreadable_text", 0), "unreadable_text_label": "Texto ilegível por codificação do PDF" if parses.get("unreadable_text") else "",
            "ocr_documents": sum(doc.get("parse_method") == "apple_vision_ocr" for doc in documents),
            "inventory_only": downloads.get("inventory_only", 0), "ime_separate_pipeline": downloads.get("excluded_ime_pipeline", 0),
            "search_records": len(searches), "pending_routes": len(pending),
            "download_states": json.dumps(downloads, ensure_ascii=False), "parse_states": json.dumps(parses, ensure_ascii=False),
            "corpus_reference": corpus_reference,
            "document_counts_by_classification": json.dumps(Counter(doc.get("classification") or doc.get("document_type") or "unclassified" for doc in documents), ensure_ascii=False),
            "search_reference": corpus_reference + "#searches", "pending_sources_reference": corpus_reference + "#pending_sources",
            "search_counts_by_status": json.dumps(Counter(search.get("status") or "unclassified" for search in searches), ensure_ascii=False),
            "search_counts_by_provider": json.dumps(Counter(search.get("provider") or search.get("source") or "unclassified" for search in searches), ensure_ascii=False),
            "pending_source_counts_by_status": json.dumps(Counter(source.get("status") or "unclassified" for source in pending), ensure_ascii=False),
            "quarterly_documents": len(quarterly_documents), "quarterly_parsed": quarterly_states.get("parsed", 0),
            "quarterly_states": json.dumps(quarterly_states, ensure_ascii=False), "quarterly_formats": json.dumps(quarterly_formats, ensure_ascii=False),
            "quarterly_ledger": f"data/documentary_diligence/{quarterly_ledger}#cnpj={fund['cnpj']}",
            "generated_at": corpus.get("generated_at", ""), "mode": corpus.get("mode", "not_available")}


def input_hashes(root: Path) -> dict[str, str]:
    paths = [root / "portfolios.json", root / "data/documentary_diligence/baseline.json", root / "data/documentary_diligence/index.json", root / "data/documentary_diligence/ime_index.json", root / "data/documentary_diligence/quarterly_index.json", root / "data/documentary_diligence/audit_quarterly_index.json", root / "data/documentary_diligence/registry_statuses.json"]
    paths.extend(root / filename for filename in ("scripts/report_documentary_diligence.py", "scripts/build_documentary_diligence.py", "scripts/refresh_documentary_quarterly.py", "services/documentary_diligence.py", "services/documentary_criteria_catalog.py", "services/documentary_clause_validation.py", "services/documentary_ime_comparison.py", "services/documentary_corpus.py"))
    paths.extend(root / filename for filename in ("scripts/refresh_documentary_corpus.py", "scripts/refresh_all_documentary_diligence.py", "scripts/refresh_documentary_ime.py", "scripts/find_documentary_sources.py", "scripts/recover_documentary_ocr.py", "scripts/documentary_vision_ocr.swift", "services/deep_dive_ppt_export.py", "services/document_curation_comparison.py", "services/on_demand_download.py", "tabs/portfolio_page.py", "tabs/tab_deep_dive.py"))
    for folder in ("funds", "history", "corpus", "audit_corpus", "ime", "source_routes", "qa", "verified_overrides", "identity_mappings"):
        paths.extend((root / "data/documentary_diligence" / folder).glob("*.json"))
    paths.extend((root / "data/regulatory_profiles/documentary_comparisons").glob("*.json"))
    paths.extend((root / "data/documentary_diligence/quarterly").rglob("*.json"))
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest() for path in sorted(set(paths)) if path.is_file()}


def build_report(root: Path, *, include_ime: bool = True):
    inputs_before = input_hashes(root)
    portfolios = [PortfolioRecord.from_dict(p) for p in read_json(root / "portfolios.json").get("portfolios", [])]
    membership = defaultdict(list)
    for p in portfolios:
        for fund in p.funds:
            membership[fund.cnpj].append({"id": p.id, "name": p.name, "fund_name": fund.display_name})
    declared = set(membership)
    quarterly_index_path = root / "data/documentary_diligence/audit_quarterly_index.json"
    if not quarterly_index_path.is_file():
        quarterly_index_path = root / "data/documentary_diligence/quarterly_index.json"
    quarterly_index = read_json(quarterly_index_path)
    quarterly_by_fund = quarterly_index.get("cnpjs", {})
    funds = {cnpj: load_documentary_fund(cnpj, source_root=root, name=membership[cnpj][0]["fund_name"]) for cnpj in sorted(declared)}
    # Only explicitly linked vehicles join look-through scope, not every generated file.
    frontier = list(funds)
    relationships = []
    while frontier:
        parent = frontier.pop()
        for relation in funds[parent].get("lookthrough", []):
            cnpj = str(relation.get("cnpj") or "")
            if len(cnpj) != 14 or not cnpj.isdigit() or cnpj == parent:
                continue
            relationships.append({"parent_cnpj": parent, **public_document_payload(relation), "cnpj": cnpj})
            if cnpj not in funds:
                funds[cnpj] = load_documentary_fund(cnpj, source_root=root, name=relation.get("label") or cnpj)
                frontier.append(cnpj)
    coverage, remaining, acquisition, quarterly_rows, provenance = [], [], [], [], Counter()
    by_cnpj = {}
    for cnpj, fund in sorted(funds.items()):
        corpus = load_documentary_corpus(cnpj, root)
        old = read_json(root / "data/regulatory_profiles/documentary_comparisons" / f"{cnpj}.json")
        before = before_answers(old, corpus.get("documents") or [])
        row, criteria, excluded, answered, synthetic = coverage_row(fund, before, membership, registered=cnpj in declared)
        coverage.append(row); by_cnpj[cnpj] = row
        remaining.extend(pending_rows(fund, criteria, excluded, answered, synthetic, corpus, membership))
        acquisition.append(acquisition_row(fund, corpus, cnpj in declared, quarterly_by_fund.get(cnpj), quarterly_ledger=quarterly_index_path.name))
        quarterly = fund.get("quarterly_observations") or {}
        reports = [quarterly] if isinstance(quarterly, dict) else quarterly
        for report in reports:
            for item in report.get("records") or []:
                sources = item.get("sources") or [{**(report.get("source") or {}), **(item.get("source") or {})}]
                quarterly_rows.append({"cnpj": cnpj, "fund": fund.get("name"), "registered": cnpj in declared, "quarter": report.get("quarter"), "competence": report.get("competence"), "report_status": report.get("status"),
                                       "criterion_id": item.get("criterion_id"), "criterion": item.get("label"), "status": item.get("status"), "value": item.get("value"),
                                       "reason": item.get("reason"), "risk_note": item.get("risk_note"), "evidence_basis": report.get("evidence_basis") or "Declaração do informe trimestral; não substitui cláusula ou comprova operação individual.", "sources": json.dumps(public_document_payload(sources), ensure_ascii=False), "normative_coverage": False})
        provenance.update(item.get("provenance") or "unclassified" for item in criteria if item["criterion_id"] in answered)
    portfolio_rows, ime_rows = [], []
    for p in portfolios:
        members = [by_cnpj[fund.cnpj] for fund in p.funds]
        totals = {key: sum(row[key] for row in members) for key in ("denominator", "before_reconstructed_answered", "after_answered", "applicability_unresolved", "documented_not_applicable", "pending", "paired_denominator", "paired_before_answered", "paired_after_answered", "reintroduced_missing_criteria")}
        row = {"portfolio_id": p.id, "portfolio": p.name, "funds": len(p.funds), **totals,
               "before_expanded_ratio": _ratio(totals["before_reconstructed_answered"], totals["denominator"]), "after_expanded_ratio": _ratio(totals["after_answered"], totals["denominator"]),
               "paired_before_ratio": _ratio(totals["paired_before_answered"], totals["paired_denominator"]), "paired_after_ratio": _ratio(totals["paired_after_answered"], totals["paired_denominator"])}
        if include_ime:
            reference = resolve_documentary_reference(p, source_root=root)
            competence = reference.get("competence")
            row.update({"reference_competence": competence or "", "ime_declared": reference.get("declared_count"), "ime_available": reference.get("available_count"), "ime_missing_cnpjs": " | ".join(reference.get("missing_cnpjs", [])),
                        "ime_warnings": json.dumps(public_document_payload(reference.get("warnings", [])), ensure_ascii=False)})
            comparison_funds = [(f.cnpj, f.display_name, "Próprio", "", {}) for f in p.funds]
            for f in p.funds:
                for relation in funds[f.cnpj].get("lookthrough", []):
                    target = str(relation.get("cnpj") or "")
                    if target in funds and target != f.cnpj:
                        comparison_funds.append((target, relation.get("label") or funds[target].get("name"), "Vínculo de investimento", f.cnpj, relation))
            for cnpj, name, layer, parent_cnpj, relation in comparison_funds:
                for observed in build_documentary_observations(funds[cnpj], competence=competence, cache_root=root):
                    item = next((c for c in funds[cnpj].get("criteria", []) if c["criterion_id"] == observed["criterion_id"]), {})
                    if not item.get("rule") and not observed.get("comparison_required"):
                        continue
                    ime_rows.append({"portfolio_id": p.id, "portfolio": p.name, "cnpj": cnpj, "fund": name, "layer": layer, "parent_cnpj": parent_cnpj,
                                     "relationship_status": relation.get("status"), "position_date": relation.get("position_date"), "current_position_confirmed": relation.get("current_position_confirmed"), "relationship_reason": relation.get("reason"),
                                     "relationship_sources": json.dumps(public_document_payload(relation.get("sources", [])), ensure_ascii=False),
                                     "criterion_id": observed["criterion_id"], "criterion": item.get("label", ""),
                                     "competence": observed.get("competence"), "status": observed.get("status"), "reason": observed.get("reason"), "observed_value": observed.get("observed_value"), "limit": observed.get("limit"), "unit": observed.get("unit"), "headroom": observed.get("headroom"), "formula": observed.get("formula"), "comparison_required": observed.get("comparison_required", False), "context_value": observed.get("context_value"), "context_unit": observed.get("context_unit"), "context_formula": observed.get("context_formula"),
                                     "ime_source": json.dumps(public_document_payload(observed.get("source", {})), ensure_ascii=False), "documentary_sources": json.dumps(public_document_payload(item.get("sources", [])), ensure_ascii=False), "rule": json.dumps(item.get("rule", {}), ensure_ascii=False)})
        portfolio_rows.append(row)
    registered_rows = [row for row in coverage if row["registered"]]
    totals = {key: sum(row[key] for row in registered_rows) for key in ("denominator", "before_reconstructed_answered", "after_answered", "pending", "applicability_unresolved", "documented_not_applicable", "paired_denominator", "paired_before_answered", "paired_after_answered", "published_criteria_count", "acceptance_criteria_count", "reintroduced_missing_criteria")}
    baseline = read_json(root / "data/documentary_diligence/baseline.json")
    final_validation = root / "data/documentary_diligence/qa/clause_validation_final_v6.json"
    qa = read_json(final_validation if final_validation.is_file() else root / "data/documentary_diligence/qa/clause_validation.json")
    distributed_qa = read_json(root / "data/documentary_diligence/qa/distributed_credit_review.json")
    revision_qa = read_json(root / "data/documentary_diligence/qa/distributed_credit_review_revision.json")
    ui_qa = read_json(root / "data/documentary_diligence/qa/ui_validation.json")
    routes = read_json(root / "data/documentary_diligence/source_routes/summary.json")
    generated = {path.stem for path in (root / "data/documentary_diligence/funds").glob("*.json")}
    quarterly_documents = [doc for cnpj in funds for doc in quarterly_by_fund.get(cnpj, {}).get("documents", {}).values()]
    inputs_after = input_hashes(root)
    changed = sorted(set(inputs_before) ^ set(inputs_after) | {path for path in inputs_before.keys() & inputs_after.keys() if inputs_before[path] != inputs_after[path]})
    summary = {"schema_version": 1, "generated_at": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds"),
               "scope": {"portfolios": len(portfolios), "registered_cnpjs": len(declared), "membership_count": sum(len(p.funds) for p in portfolios), "active_cnpjs_including_lookthrough": len(funds), "lookthrough_relations": relationships, "generated_files_outside_active_scope": sorted(generated - set(funds))},
               "registered_coverage": {**totals, "before_expanded_ratio": _ratio(totals["before_reconstructed_answered"], totals["denominator"]), "after_expanded_ratio": _ratio(totals["after_answered"], totals["denominator"]), "paired_before_ratio": _ratio(totals["paired_before_answered"], totals["paired_denominator"]), "paired_after_ratio": _ratio(totals["paired_after_answered"], totals["paired_denominator"])},
               "before_method_limit": BEFORE_LIMIT, "after_method": "Confirmado + aplicável + valor substantivo + documento/data/página ou cláusula válidos, dividido por aplicáveis e aplicabilidade em apuração. N/A só excluído com fonte e fundamento documental. Critérios anteriores ausentes são mantidos como pendências.",
               "original_mechanical_baseline": baseline, "provenance_counts_including_lookthrough": dict(provenance),
               "quarterly_acquisition": {"active_funds_with_documents": sum(bool(quarterly_by_fund.get(cnpj, {}).get("documents")) for cnpj in funds), "documents": len(quarterly_documents), "states": dict(Counter(doc.get("status") or "unclassified" for doc in quarterly_documents)), "formats": dict(Counter((doc.get("source") or {}).get("type") or "unknown" for doc in quarterly_documents)), "updated_at": quarterly_index.get("updated_at"), "acquisition_pass": quarterly_index.get("acquisition_pass"), "stopped_reason": quarterly_index.get("stopped_reason")},
               "pending_states": dict(Counter(row["status"] for row in remaining)), "acquisition_totals_including_lookthrough": {key: sum(row[key] for row in acquisition) for key in ("documents_inventoried", "local_or_downloaded", "complete_texts", "parse_failed", "unreadable_text", "ocr_documents", "inventory_only", "ime_separate_pipeline", "pending_routes")},
               "ime_statuses": dict(Counter(row["status"] for row in ime_rows)), "ime_comparisons_included": include_ime,
               "ime_coverage": {"comparison_rows": len(ime_rows), "own_layer_rows": sum(row["layer"] == "Próprio" for row in ime_rows), "linked_layer_rows": sum(row["layer"] == "Vínculo de investimento" for row in ime_rows),
                                "contractual_observed_rows": sum(row.get("observed_value") is not None for row in ime_rows), "aggregate_context_rows": sum(row.get("context_value") is not None for row in ime_rows),
                                "concluded_rows": sum(row["status"] in {"compliant_snapshot", "observed_below_limit", "observed_above_limit"} for row in ime_rows), "ime_unavailable_rows": sum(row["status"] == "ime_unavailable" for row in ime_rows)},
               "qa": {"automated_scope": qa.get("scope"), "fund_files": qa.get("fund_files", qa.get("funds_checked")), "states": qa.get("states", qa.get("counts")), "sample_cnpjs": qa.get("sample_cnpjs", []), "sample_primary_passages": qa.get("sample_primary_passages"), "limitations": qa.get("limitations", []),
                      "validator_revision": qa.get("validator_revision"), "validator_fingerprint": qa.get("validator_fingerprint"), "source_verifications": qa.get("source_verifications"), "ocr_documents_checked": qa.get("ocr_documents_checked"), "excluded_pages_visual_review_sources": qa.get("excluded_pages_visual_review_sources", []), "inputs_changed_while_read": qa.get("inputs_changed_while_read", [])},
               "distributed_credit_qa": {key: distributed_qa.get(key) for key in ("generated_at", "method", "scope", "sample_answered", "sample_pending", "sample_provenance", "outcomes", "critical_findings", "limitations", "changed_since_sample")},
               "distributed_credit_qa_revision": {key: revision_qa.get(key) for key in ("generated_at", "method", "scope", "sample_answered_after", "sample_pending_after", "outcomes_after", "initial_critical_findings", "critical_recheck", "remaining_critical_findings", "known_initial_material_limits_without_full_recheck", "limitations", "inputs_changed_during_review")},
               "ui_validation": ui_qa,
               "external_source_routes": routes,
               "input_fingerprints": inputs_after, "inputs_changed_during_report": changed,
               "acceptance_snapshot_consistent": not changed,
               "claims_not_supported": ["Leitura humana certificada de todos os documentos", "Inventário externo exaustivo de administradores, gestores, rating e lastro", "Conformidade diária, cura e reincidência demonstradas pelo snapshot IME mensal", "Look-through de posições efetivas ou pesos sem declaração documental"]}
    return {"coverage_funds.csv": coverage, "coverage_portfolios.csv": portfolio_rows, "remaining_cells.csv": remaining, "acquisition_by_fund.csv": acquisition, "ime_comparisons.csv": ime_rows, "quarterly_declarations.csv": quarterly_rows}, public_document_payload(summary)


def diagnostic_text(summary: dict) -> str:
    scope, coverage, acquisition = summary["scope"], summary["registered_coverage"], summary["acquisition_totals_including_lookthrough"]
    return f"""# Curadoria documental — diagnóstico e aceite

Data: {summary['generated_at']}. Escopo: {scope['portfolios']} carteiras, {scope['registered_cnpjs']} CNPJs cadastrados e {scope['membership_count']} participações fundo/carteira. Os veículos vinculados documentalmente entram em camada própria.

No catálogo ampliado conservador, as respostas rastreáveis reconstruídas passam de {coverage['before_reconstructed_answered']}/{coverage['denominator']} ({_percent(coverage['before_expanded_ratio'])}) para {coverage['after_answered']}/{coverage['denominator']} ({_percent(coverage['after_expanded_ratio'])}). Nos 27 conceitos anteriores pareados, passam de {coverage['paired_before_answered']}/{coverage['paired_denominator']} ({_percent(coverage['paired_before_ratio'])}) para {coverage['paired_after_answered']}/{coverage['paired_denominator']} ({_percent(coverage['paired_after_ratio'])}). Aplicabilidade em apuração: {coverage['applicability_unresolved']}; não aplicabilidade documentada: {coverage['documented_not_applicable']}. Pendências: {coverage['pending']}. Foram reintroduzidas {coverage['reintroduced_missing_criteria']} perguntas ausentes dos arquivos publicados para impedir ganho de cobertura pela remoção de linhas.

{BEFORE_LIMIT}

## Causas e correções

| Falha relatada | Causa identificada | Tratamento e limite |
| --- | --- | --- |
| Fundos quase inteiros em N/D | Aquisição por CNPJ falhou com timeout/HTTP 520; havia inventário sem regulamento local. Extrações e pareceres não cobriam todo o acervo. | Inventário por documento, download e parsing com estados próprios; recuperação local e novas buscas. Documento inventariado não equivale a documento lido. |
| Afirmações genéricas e controles iguais | Critérios fixos, fallback textual e validação de campos preenchidos aceitavam textos de processo como fatos. | Catálogo de crédito, cláusula localizada e valor específico; proveniência separada e regras comuns só quando confirmadas. |
| Frases de lacuna substituíam conteúdo | O contrato aceitava qualquer descrição não vazia; o renderizador limpava remissões e faltas. | Estado, motivo e busca ficam nas pendências individuais; resposta e mecânica ficam na matriz. |
| N/D sem motivo | Ausência e aplicabilidade não eram campos independentes; a apresentação trocava lacunas por hífen e depois N/D. | Estados de aquisição, acesso, parsing, cláusula, documento referido e conflito; aplicabilidade em apuração permanece no denominador. |
| Fundos mudavam de agrupamento | Colunas com vetores visuais iguais eram agrupadas por seção, inclusive grupos inteiros sem informação. | Uma coluna por CNPJ na ordem da cesta, com largura fixa e identificação acessível. |
| Fontes afastadas das células | Fontes por célula existiam no CSV, mas a tela as concentrava em auditoria e o PPT nas notas. | ID, data e página/cláusula junto da resposta; links e excertos em detalhes; conteúdo integral nos arquivos. |
| Instruções de interface e competências divergentes | O enriquecimento escolhia o último cache de cada CNPJ e escrevia “selecionar competência”; Documentos não recebia o contexto financeiro. | Resolução da posição comum de toda a cesta; snapshot publicado e dados carregados com identidade e competência explícitas. |
| Limites sem confronto com IME | A aba mostrava descrições de monitorabilidade; faltavam fórmula, vigência, camada e observação ligada à célula. | Confronto com numerador/base/unidade; diferença de vigência, ausência de saldo individual, carência ou apuração diária impedem certificado. |
| FIC sem classe investida | O vínculo era citado em texto e a aquisição/exposição não era seguida até o veículo declarado. | Documentos e critérios do investido em camada própria, preservando CNPJ/subclasse e distinguindo vínculo permitido de posição efetiva. |

Na aquisição FIAGRO, o endpoint `pesquisarGerenciadorDocumentosDados` podia receber o filtro padrão `tipoFundo=2` de FIDC. O adaptador passa a consultar o CNPJ exato sem limitar o tipo e registra `scope=cnpj_all_fund_types`. O experimento para Ceres retornou 9 documentos com tipo 2 e 17 sem o filtro, incluindo IMEs de maio a agosto/2026 e CDA. Esse experimento e o inventário persistido são evidências distintas; o estado realmente gravado consta em `acquisition_by_fund.csv` e nos corpora.

## Entrega verificável

- `coverage_funds.csv`: antes/depois por CNPJ, denominadores, aplicabilidade e proveniência.
- `coverage_portfolios.csv`: as {scope['portfolios']} cestas completas, incluindo repetição de CNPJ entre carteiras.
- `remaining_cells.csv`: uma linha por pergunta pendente, com estado, motivo, fonte criterial e referência ao registro de aquisição do CNPJ.
- `acquisition_by_fund.csv`: inventário, disponibilidade, parsing, buscas e rotas pendentes.
- `ime_comparisons.csv`: competência comum, observação, limite, fórmula, fonte e ressalva de comparação; referências agregadas ficam em campos próprios quando a base contratual não é reproduzível.
- `quarterly_declarations.csv`: respostas declaradas no informe trimestral e conflitos com a norma, preservando período, fonte e ressalva; sem aumentar a cobertura normativa.
- `summary.json`: método, fingerprints dos insumos e limites das afirmações.

Confronto IME: {summary['ime_coverage']['comparison_rows']} linhas de critério/CNPJ/carteira, sendo {summary['ime_coverage']['own_layer_rows']} da camada própria e {summary['ime_coverage']['linked_layer_rows']} de veículos vinculados. Há {summary['ime_coverage']['contractual_observed_rows']} valores observados para medidas contratuais e {summary['ime_coverage']['aggregate_context_rows']} referências agregadas, mantidos em campos distintos; essas contagens podem coexistir numa linha e não representam CNPJs únicos. Resultado conclusivo de enquadramento: {summary['ime_coverage']['concluded_rows']} linhas. Dado IME indisponível para a medida ou posição comum: {summary['ime_coverage']['ime_unavailable_rows']} linhas, com motivo individual no CSV. Vigência efetiva, início/carência, base individual e frequência de apuração impedem as conclusões pendentes; referência agregada não certifica cumprimento.

Aquisição no escopo ativo: {acquisition['documents_inventoried']} registros inventariados, {acquisition['local_or_downloaded']} documentos locais/obtidos e {acquisition['complete_texts']} textos com parsing completo. Os números de registros e arquivos podem diferir por versão, tipo e reaproveitamento de acervo. Buscas externas direcionadas não constituem levantamento exaustivo de todas as fontes.

Qualidade de leitura: {acquisition.get('unreadable_text', 0)} documentos com texto ilegível por codificação e {acquisition.get('ocr_documents', 0)} recuperados por OCR local, com método, confiança e páginas excluídas no inventário. Páginas físicas completas não certificam texto legível. OCR conserva a referência ao PDF original e não representa leitura humana.

Rotas externas: `{json.dumps(summary.get('external_source_routes', {}), ensure_ascii=False)}`. O registro inicial usa 20 URLs únicas sondadas por HEAD para 430 rotas identificadas; retornos compartilhados por URL são contados por rota no resumo. Links de PDF podem ser candidatos por nome com CNPJ ainda não verificado. Acessibilidade de portal ou resultado vazio não comprova existência, identidade ou ausência de documento.

Proveniência das respostas: `{json.dumps(summary['provenance_counts_including_lookthrough'], ensure_ascii=False)}`. `primary_passage` identifica extração de trecho; `previous_review_with_primary_locator` identifica parecer anterior reaproveitado; `verified_override` identifica leitura dirigida registrada nesta execução. Nenhuma categoria certifica revisão humana integral.

O QA automatizado cobre os arquivos declarados no relatório do validador; a amostra material e a inspeção visual têm escopo próprio, indicado em `summary.json`. A matriz foi exercitada para BTG, cesta de 101 fundos e fundo individual, com fontes, valores monetários literais e downloads locais. Implementação, publicação e validação pública devem ser comprovadas separadamente.

A revisão distribuída inicial permanece preservada. O recheck dirigido dos achados iniciais e adicionais conserva estado, valor, fontes e hash antes/depois em `distributed_credit_review_revision.json`, com seu escopo explícito no resumo. Retirar confirmação inadequada reduz a cobertura e mantém a pergunta pendente; isso não obtém a cláusula faltante. A ausência de achado remanescente nesse conjunto não certifica todos os critérios ou documentos do universo.

Os critérios preservam número, base, janela, cura/reincidência, waterfall, liberação da júnior, PDD, hedge/MTM, cessão, garantias e cobrança quando documentados. As dimensões do material de referência de 16 slides orientaram as perguntas; esse material não substitui regulamento ou evidência por CNPJ.

Relatório gerado somente por leitura. Insumos alterados durante a geração: {len(summary['inputs_changed_during_report'])}. Se houver alteração, execute novamente após terminar aquisição, snapshots e construção dos critérios.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--as-of", default=datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat())
    parser.add_argument("--skip-ime", action="store_true")
    args = parser.parse_args()
    as_of = date.fromisoformat(args.as_of)
    root = args.root.resolve()
    output = args.output_dir or root / "reports" / f"documentary_diligence_{as_of:%Y%m%d}"
    if not output.is_absolute():
        output = root / output
    tables, summary = build_report(root, include_ime=not args.skip_ime)
    summary["as_of"] = as_of.isoformat()
    for filename, rows in tables.items():
        atomic_bytes(output / filename, csv_bytes(rows))
    atomic_bytes(output / "diagnostic.md", diagnostic_text(summary).encode())
    summary["output_fingerprints"] = {filename: sha256((output / filename).read_bytes()).hexdigest() for filename in (*tables, "diagnostic.md")}
    # The summary is the final publication marker for a completed report run.
    atomic_bytes(output / "summary.json", (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode())
    totals = summary["registered_coverage"]
    print(json.dumps({"output": str(output.relative_to(root)) if output.is_relative_to(root) else str(output), "portfolios": summary["scope"]["portfolios"], "registered_cnpjs": summary["scope"]["registered_cnpjs"], "after_answered": totals["after_answered"], "denominator": totals["denominator"], "pending": totals["pending"], "inputs_changed_during_report": len(summary["inputs_changed_during_report"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
