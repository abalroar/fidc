from __future__ import annotations

import json
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.monitoring_metrics import build_monitoring_tables, read_wide_csv
from services.variaveis_fnet import competencia_columns

RAW_DIR = ROOT / "data" / "raw"
KNOWLEDGE_DIR = ROOT / "data" / "regulatory_knowledge"
PROFILE_DIR = ROOT / "data" / "regulatory_profiles"
REPORTS_DIR = ROOT / "reports"
IME_CACHE_DIR = ROOT / ".cache" / "fundonet-ime"


TARGET_FUNDS: dict[str, dict[str, str]] = {
    "50473039000102": {"grupo": "Sellers", "nome_curto": "Seller FIDC"},
    "55471753000177": {"grupo": "Sellers", "nome_curto": "Seller II FIDC"},
    "63572282000111": {"grupo": "Sellers", "nome_curto": "Seller 3 FIDC"},
    "28472333000132": {"grupo": "Mercado Crédito", "nome_curto": "Mercado Crédito Merchant FIDC"},
    "33254370000104": {"grupo": "Mercado Crédito", "nome_curto": "Mercado Crédito FIDC"},
    "37511828000114": {"grupo": "Mercado Crédito", "nome_curto": "Mercado Crédito I Brasil FIDC"},
    "41970012000126": {"grupo": "Mercado Crédito", "nome_curto": "Mercado Crédito II Brasil FIDC"},
}


EVIDENCE_PATTERNS: dict[str, list[str]] = {
    "emissoes": [
        r"\bemiss[aã]o\b",
        r"\bs[ée]rie\b",
        r"\bcotas? seniores?\b",
        r"\bcotas? subordinadas?\b",
        r"\bintegraliza[cç][aã]o\b",
        r"\bISIN\b",
        r"\bvalor unit[aá]rio\b",
    ],
    "preco_economia": [
        r"\bpre[cç]o de emiss[aã]o\b",
        r"\bremunera[cç][aã]o\b",
        r"\bmeta de remunera[cç][aã]o\b",
        r"\bCDI\b",
        r"\bDI\b",
        r"\bspread\b",
        r"\bsobretaxa\b",
        r"\b[aá]gio\b",
        r"\bdes[aá]gio\b",
        r"\bbenchmark\b",
    ],
    "amortizacao": [
        r"\bamortiza[cç][aã]o\b",
        r"\bresgate\b",
        r"\bvencimento\b",
        r"\bdata de pagamento\b",
        r"\bcronograma\b",
        r"\bcar[eê]ncia\b",
        r"\brevolv[eê]ncia\b",
        r"\bclean[- ]?up\b",
    ],
    "alteracoes_assembleias": [
        r"\bassembleia\b",
        r"\bdeliberou\b",
        r"\baprovar\b",
        r"\baltera[cç][aã]o\b",
        r"\bwaiver\b",
        r"\bdispensa\b",
        r"\baditamento\b",
        r"\bconflito de interesses?\b",
    ],
    "cotistas_partes_relacionadas": [
        r"\bcotistas?\b",
        r"\bpartes? relacionadas?\b",
        r"\bcedente\b",
        r"\boriginador\b",
        r"\bdevedor\b",
        r"\bcontrolad[ao]r",
        r"\bvinculad[ao]s?\b",
        r"\bconcentra[cç][aã]o\b",
    ],
    "direitos_creditorios_cessoes": [
        r"\bdireitos credit[oó]rios\b",
        r"\bcess[aã]o\b",
        r"\bcedidos?\b",
        r"\bcrit[eé]rios? de elegibilidade\b",
        r"\bcondi[cç][oõ]es de cess[aã]o\b",
        r"\brecompra\b",
        r"\bsubstitui[cç][aã]o\b",
        r"\bdilui[cç][aã]o\b",
        r"\bchargeback\b",
    ],
    "performance_risco": [
        r"\binadimpl[eê]ncia\b",
        r"\batraso\b",
        r"\bover ?30\b",
        r"\bover ?60\b",
        r"\bover ?90\b",
        r"\bover ?180\b",
        r"\bover ?360\b",
        r"\bPDD\b",
        r"\bprovis[aã]o\b",
        r"\bperda\b",
        r"\bcobertura\b",
        r"\bexcess spread\b",
    ],
    "triggers_protecao": [
        r"\bsubordina[cç][aã]o\b",
        r"\brela[cç][aã]o m[ií]nima\b",
        r"\b[ií]ndice de cobertura\b",
        r"\b[ií]ndice de aloca[cç][aã]o\b",
        r"\bevento de avalia[cç][aã]o\b",
        r"\bevento de liquida[cç][aã]o\b",
        r"\breserva de liquidez\b",
        r"\bliquida[cç][aã]o antecipada\b",
    ],
    "governanca_operacional": [
        r"\badministrador[ae]?\b",
        r"\bgestor[ae]?\b",
        r"\bcustodiante\b",
        r"\bescriturador\b",
        r"\bagente de cobran[cç]a\b",
        r"\bauditor",
        r"\brating\b",
        r"\bag[eê]ncia classificadora\b",
        r"\bsubstitui[cç][aã]o\b",
    ],
}


OUTPUTS = {
    "inventory": REPORTS_DIR / "sellers_mercado_credito_document_inventory.csv",
    "coverage": REPORTS_DIR / "sellers_mercado_credito_document_coverage.csv",
    "evidence": REPORTS_DIR / "sellers_mercado_credito_pdf_evidence.csv",
    "doc_digest": REPORTS_DIR / "sellers_mercado_credito_document_by_document_digest.csv",
    "emissions": REPORTS_DIR / "sellers_mercado_credito_emissions.csv",
    "emissions_raw": REPORTS_DIR / "sellers_mercado_credito_emissions_raw.csv",
    "criteria": REPORTS_DIR / "sellers_mercado_credito_triggers_criteria.csv",
    "threshold_versions": REPORTS_DIR / "sellers_mercado_credito_threshold_versions.csv",
    "eligibility": REPORTS_DIR / "sellers_mercado_credito_eligibility_criteria.csv",
    "timeline": REPORTS_DIR / "sellers_mercado_credito_timeline.csv",
    "reg_changes": REPORTS_DIR / "sellers_mercado_credito_regulation_changes.csv",
    "assemblies": REPORTS_DIR / "sellers_mercado_credito_assembly_events.csv",
    "cotistas": REPORTS_DIR / "sellers_mercado_credito_cotistas_related_parties.csv",
    "amortizations": REPORTS_DIR / "sellers_mercado_credito_amortizations.csv",
    "pricing": REPORTS_DIR / "sellers_mercado_credito_pricing_economics.csv",
    "cessions": REPORTS_DIR / "sellers_mercado_credito_cessions_credit_rights.csv",
    "governance": REPORTS_DIR / "sellers_mercado_credito_governance_operational.csv",
    "performance": REPORTS_DIR / "sellers_mercado_credito_performance_metrics.csv",
    "report": REPORTS_DIR / "sellers_mercado_credito_deep_dive.md",
}


@dataclass(frozen=True)
class PdfPage:
    page: int
    text: str


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    knowledge = load_knowledge()
    inventory = build_document_inventory(knowledge)
    inventory.to_csv(OUTPUTS["inventory"], index=False)

    coverage = build_document_coverage(inventory)
    coverage.to_csv(OUTPUTS["coverage"], index=False)

    if OUTPUTS["evidence"].exists() and OUTPUTS["evidence"].stat().st_size > 0:
        evidence = pd.read_csv(OUTPUTS["evidence"], dtype=str, keep_default_na=False)
    else:
        evidence = build_pdf_evidence(inventory)
        evidence.to_csv(OUTPUTS["evidence"], index=False)

    doc_digest = build_document_digest(inventory, evidence)
    doc_digest.to_csv(OUTPUTS["doc_digest"], index=False)

    emissions, emissions_raw = build_emissions_tables(knowledge)
    emissions.to_csv(OUTPUTS["emissions"], index=False)
    emissions_raw.to_csv(OUTPUTS["emissions_raw"], index=False)

    criteria = build_criteria_table(knowledge)
    criteria.to_csv(OUTPUTS["criteria"], index=False)

    threshold_versions = build_threshold_versions(knowledge, inventory)
    threshold_versions.to_csv(OUTPUTS["threshold_versions"], index=False)

    eligibility = build_eligibility_table(knowledge)
    eligibility.to_csv(OUTPUTS["eligibility"], index=False)

    timeline = build_timeline(inventory)
    timeline.to_csv(OUTPUTS["timeline"], index=False)

    write_topic_tables(evidence, inventory, emissions)

    performance = build_performance_metrics()
    performance.to_csv(OUTPUTS["performance"], index=False)

    report = build_markdown_report(
        inventory=inventory,
        coverage=coverage,
        evidence=evidence,
        doc_digest=doc_digest,
        emissions=emissions,
        criteria=criteria,
        threshold_versions=threshold_versions,
        eligibility=eligibility,
        timeline=timeline,
        performance=performance,
    )
    OUTPUTS["report"].write_text(report, encoding="utf-8")

    print("Arquivos gerados:")
    for key, path in OUTPUTS.items():
        print(f"- {key}: {path.relative_to(ROOT)}")


def load_knowledge() -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for cnpj in TARGET_FUNDS:
        path = KNOWLEDGE_DIR / f"{cnpj}.json"
        if not path.exists():
            payloads[cnpj] = {}
            continue
        payloads[cnpj] = json.loads(path.read_text(encoding="utf-8"))
    return payloads


def build_document_inventory(knowledge: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    inventory_csv = ROOT / "reports" / "regulatory_document_inventory.csv"
    if inventory_csv.exists():
        inv = pd.read_csv(inventory_csv, dtype=str, keep_default_na=False)
        for _, row in inv.iterrows():
            cnpj = digits(row.get("CNPJ", ""))
            if cnpj not in TARGET_FUNDS:
                continue
            source = str(row.get("Arquivo", "") or "")
            key = (cnpj, str(row.get("ID CVM", "")))
            seen.add(key)
            rows.append(
                normalize_inventory_row(
                    cnpj=cnpj,
                    fund_name=str(row.get("Fundo", "")),
                    doc_id=str(row.get("ID CVM", "")),
                    date=str(row.get("Data", "")),
                    category=str(row.get("Tipo", "")),
                    document_type=str(row.get("Documento", "")),
                    species=str(row.get("Espécie", "")),
                    source_file=source,
                    source_registry="reports/regulatory_document_inventory.csv",
                )
            )

    for cnpj, payload in knowledge.items():
        fund_name = payload.get("fund_name") or TARGET_FUNDS[cnpj]["nome_curto"]
        for doc in payload.get("documents", []) or []:
            doc_id = str(doc.get("id", ""))
            key = (cnpj, doc_id)
            if key in seen:
                continue
            rows.append(
                normalize_inventory_row(
                    cnpj=cnpj,
                    fund_name=fund_name,
                    doc_id=doc_id,
                    date=str(doc.get("data_referencia", "")),
                    category=str(doc.get("classification", "") or doc.get("categoria", "")),
                    document_type=str(doc.get("tipo", "") or doc.get("categoria", "")),
                    species=str(doc.get("especie", "")),
                    source_file=str(doc.get("source_file", "") or ""),
                    source_registry=f"data/regulatory_knowledge/{cnpj}.json",
                    status=str(doc.get("status", "")),
                    downloaded=doc.get("downloaded"),
                )
            )

    for cnpj in TARGET_FUNDS:
        raw_folder = RAW_DIR / cnpj
        if not raw_folder.exists():
            continue
        for path in sorted(raw_folder.glob("*.pdf")):
            doc_id = path.name.split("_", 1)[0]
            key = (cnpj, doc_id)
            if key in seen:
                continue
            rows.append(
                normalize_inventory_row(
                    cnpj=cnpj,
                    fund_name=knowledge.get(cnpj, {}).get("fund_name") or TARGET_FUNDS[cnpj]["nome_curto"],
                    doc_id=doc_id,
                    date=date_from_filename(path.name),
                    category=classification_from_filename(path.name),
                    document_type=classification_from_filename(path.name),
                    species="",
                    source_file=str(path.relative_to(ROOT)),
                    source_registry="data/raw scan",
                    downloaded=True,
                )
            )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["sort_date"] = frame["data_referencia"].map(parse_date_sort)
    frame = frame.sort_values(["grupo", "cnpj", "sort_date", "documento_id", "source_file"], na_position="last")
    frame = frame.drop(columns=["sort_date"])
    return frame.reset_index(drop=True)


def normalize_inventory_row(
    *,
    cnpj: str,
    fund_name: str,
    doc_id: str,
    date: str,
    category: str,
    document_type: str,
    species: str,
    source_file: str,
    source_registry: str,
    status: str = "",
    downloaded: Any = None,
) -> dict[str, Any]:
    source_path = ROOT / source_file if source_file else None
    exists = bool(source_path and source_path.exists())
    return {
        "grupo": TARGET_FUNDS[cnpj]["grupo"],
        "fundo": fund_name or TARGET_FUNDS[cnpj]["nome_curto"],
        "nome_curto": TARGET_FUNDS[cnpj]["nome_curto"],
        "cnpj": format_cnpj(cnpj),
        "cnpj_digits": cnpj,
        "data_referencia": date,
        "categoria": category,
        "tipo_documento": document_type,
        "especie": species,
        "documento_id": doc_id,
        "status_cvm": status,
        "downloaded_flag": downloaded,
        "source_file": source_file,
        "arquivo_local_existe": exists,
        "source_registry": source_registry,
        "page_count": count_pdf_pages(source_path) if exists and source_path else None,
    }


def build_document_coverage(inventory: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if inventory.empty:
        return pd.DataFrame(rows)
    for (cnpj, fundo, grupo), grp in inventory.groupby(["cnpj", "fundo", "grupo"], dropna=False):
        local = grp[grp["arquivo_local_existe"] == True]  # noqa: E712
        missing = grp[grp["arquivo_local_existe"] != True]  # noqa: E712
        by_type = grp.groupby("categoria")["documento_id"].count().to_dict()
        rows.append(
            {
                "grupo": grupo,
                "cnpj": cnpj,
                "fundo": fundo,
                "documentos_inventariados": len(grp),
                "pdfs_locais_analisaveis": len(local),
                "documentos_sem_pdf_local": len(missing),
                "paginas_pdf_locais": int(pd.to_numeric(local["page_count"], errors="coerce").fillna(0).sum()),
                "quebra_por_categoria": "; ".join(f"{k}: {v}" for k, v in sorted(by_type.items())),
            }
        )
    return pd.DataFrame(rows).sort_values(["grupo", "fundo"])


def build_pdf_evidence(inventory: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    local_docs = inventory[inventory["arquivo_local_existe"] == True].copy()  # noqa: E712
    for _, doc in local_docs.iterrows():
        source_file = str(doc["source_file"])
        path = ROOT / source_file
        pages = extract_pdf_pages(path)
        if not pages:
            rows.append(evidence_row(doc, None, "erro_extração", "", "PDF sem texto extraível por pypdf; OCR pode ser necessário."))
            continue
        for category, patterns in EVIDENCE_PATTERNS.items():
            snippets = snippets_for_patterns(pages, patterns, limit_per_doc=5)
            for page, terms, excerpt in snippets:
                rows.append(evidence_row(doc, page, category, ", ".join(sorted(terms)), excerpt))
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values(["grupo", "fundo", "data_referencia", "documento_id", "page", "categoria_evidencia"])
    return frame.reset_index(drop=True)


def build_document_digest(inventory: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if inventory.empty:
        return pd.DataFrame(rows)
    grouped_evidence = {}
    if not evidence.empty:
        grouped_evidence = {key: grp.copy() for key, grp in evidence.groupby(["cnpj", "documento_id"], dropna=False)}
    for _, doc in inventory.iterrows():
        key = (doc["cnpj"], str(doc["documento_id"]))
        ev = grouped_evidence.get(key, pd.DataFrame())
        counts: dict[str, int] = {}
        pages: list[str] = []
        sample = ""
        if not ev.empty:
            counts = ev.groupby("categoria_evidencia")["trecho"].count().to_dict()
            pages = sorted({str(p) for p in ev.get("page", pd.Series(dtype=str)).tolist() if str(p)})
            sample = str(ev.iloc[0].get("trecho", ""))
        rows.append(
            {
                "grupo": doc["grupo"],
                "fundo": doc["fundo"],
                "nome_curto": doc["nome_curto"],
                "cnpj": doc["cnpj"],
                "data_referencia": doc["data_referencia"],
                "categoria": doc["categoria"],
                "tipo_documento": doc["tipo_documento"],
                "documento_id": doc["documento_id"],
                "source_file": doc["source_file"],
                "arquivo_local_existe": doc["arquivo_local_existe"],
                "page_count": doc["page_count"],
                "categorias_com_evidencia": "; ".join(f"{k}: {v}" for k, v in sorted(counts.items())),
                "paginas_com_evidencia": ", ".join(pages[:30]),
                "amostra_trecho": clean_excerpt(sample),
                "status_auditoria": "PDF analisado" if doc["arquivo_local_existe"] else "Inventariado sem PDF local",
            }
        )
    return pd.DataFrame(rows)


def evidence_row(doc: pd.Series, page: int | None, category: str, terms: str, excerpt: str) -> dict[str, Any]:
    return {
        "grupo": doc["grupo"],
        "fundo": doc["fundo"],
        "nome_curto": doc["nome_curto"],
        "cnpj": doc["cnpj"],
        "data_referencia": doc["data_referencia"],
        "documento_id": doc["documento_id"],
        "tipo_documento": doc["tipo_documento"],
        "categoria_documento": doc["categoria"],
        "source_file": doc["source_file"],
        "page": page,
        "categoria_evidencia": category,
        "termos_encontrados": terms,
        "trecho": clean_excerpt(excerpt),
        "fonte_pagina": f"{Path(str(doc['source_file'])).name} p.{page}" if page else Path(str(doc["source_file"])).name,
    }


def build_emissions_tables(knowledge: dict[str, dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    profile_frames = []
    for path in [
        PROFILE_DIR / "seller_cotas_emissoes_pagamentos.csv",
        PROFILE_DIR / "all_fidcs_cotas_emissoes_pagamentos.csv",
        REPORTS_DIR / "seller_cotas_emissoes_pagamentos.csv",
        REPORTS_DIR / "regulatory_emissions_timeline.csv",
    ]:
        if path.exists():
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            cnpj_col = "CNPJ" if "CNPJ" in df.columns else None
            if cnpj_col:
                df["cnpj_digits"] = df[cnpj_col].map(digits)
                df = df[df["cnpj_digits"].isin(TARGET_FUNDS)]
            else:
                continue
            df["arquivo_origem_tabela"] = str(path.relative_to(ROOT))
            profile_frames.append(df)
    emissions = pd.concat(profile_frames, ignore_index=True, sort=False) if profile_frames else pd.DataFrame()
    if not emissions.empty:
        emissions = emissions.drop_duplicates().reset_index(drop=True)

    raw_rows: list[dict[str, Any]] = []
    for cnpj, payload in knowledge.items():
        for item in payload.get("emissions", []) or []:
            raw_rows.append(
                {
                    "grupo": TARGET_FUNDS[cnpj]["grupo"],
                    "fundo": payload.get("fund_name") or TARGET_FUNDS[cnpj]["nome_curto"],
                    "nome_curto": TARGET_FUNDS[cnpj]["nome_curto"],
                    "cnpj": format_cnpj(cnpj),
                    "date": item.get("date"),
                    "event": item.get("event"),
                    "series_or_class": item.get("series_or_class"),
                    "amount": item.get("amount"),
                    "amount_display": item.get("amount_display"),
                    "currency": item.get("currency"),
                    "remuneration": item.get("remuneration"),
                    "amortization_schedule": item.get("amortization_schedule"),
                    "maturity": item.get("maturity"),
                    "source_excerpt": item.get("source_excerpt"),
                    "source_document": item.get("source_document"),
                    "source_document_id": item.get("source_document_id"),
                }
            )
    return emissions, pd.DataFrame(raw_rows)


def build_criteria_table(knowledge: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in [
        PROFILE_DIR / "seller_criteria_monitoraveis_ime.csv",
        PROFILE_DIR / "all_fidcs_criteria_monitoraveis_ime.csv",
        REPORTS_DIR / "seller_criteria_monitoraveis_ime.csv",
        REPORTS_DIR / "regulatory_criteria_matrix.csv",
    ]:
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        if "CNPJ" not in df.columns:
            continue
        df["cnpj_digits"] = df["CNPJ"].map(digits)
        df = df[df["cnpj_digits"].isin(TARGET_FUNDS)].copy()
        if df.empty:
            continue
        df["arquivo_origem_tabela"] = str(path.relative_to(ROOT))
        rows.extend(df.to_dict("records"))

    for cnpj, payload in knowledge.items():
        for item in payload.get("criteria", []) or []:
            mapping = item.get("monitoring_mapping") or {}
            rows.append(
                {
                    "Fundo": payload.get("fund_name") or TARGET_FUNDS[cnpj]["nome_curto"],
                    "CNPJ": format_cnpj(cnpj),
                    "Critério": item.get("name"),
                    "Chave": item.get("canonical_key"),
                    "Evento": item.get("event_type"),
                    "Comparação": item.get("comparison"),
                    "Limite": item.get("threshold_display"),
                    "Monitorabilidade IME": mapping.get("status"),
                    "Métrica IME / proxy": mapping.get("ime_metric"),
                    "Condição de alerta sugerida": "",
                    "Observação técnica": item.get("notes"),
                    "Fonte": f"{item.get('source_document')} · ID {item.get('source_document_id')}",
                    "Trecho/Fórmula": item.get("source_excerpt") or item.get("formula_text"),
                    "arquivo_origem_tabela": f"data/regulatory_knowledge/{cnpj}.json",
                    "cnpj_digits": cnpj,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.drop_duplicates().reset_index(drop=True)


def build_threshold_versions(knowledge: dict[str, dict[str, Any]], inventory: pd.DataFrame) -> pd.DataFrame:
    doc_dates: dict[tuple[str, str], dict[str, Any]] = {}
    if not inventory.empty:
        for _, row in inventory.iterrows():
            doc_dates[(digits(row["cnpj"]), str(row["documento_id"]))] = {
                "data_referencia": row.get("data_referencia", ""),
                "source_file": row.get("source_file", ""),
                "tipo_documento": row.get("tipo_documento", ""),
                "categoria": row.get("categoria", ""),
                "arquivo_local_existe": row.get("arquivo_local_existe", ""),
            }
    rows: list[dict[str, Any]] = []
    for cnpj, payload in knowledge.items():
        for item in payload.get("criteria", []) or []:
            source_id = str(item.get("source_document_id", "") or "")
            doc_meta = doc_dates.get((cnpj, source_id), {})
            mapping = item.get("monitoring_mapping") or {}
            rows.append(
                {
                    "grupo": TARGET_FUNDS[cnpj]["grupo"],
                    "fundo": payload.get("fund_name") or TARGET_FUNDS[cnpj]["nome_curto"],
                    "nome_curto": TARGET_FUNDS[cnpj]["nome_curto"],
                    "cnpj": format_cnpj(cnpj),
                    "data_documento": doc_meta.get("data_referencia", ""),
                    "documento_id": source_id,
                    "source_file": doc_meta.get("source_file", item.get("source_document")),
                    "categoria_documento": doc_meta.get("categoria", ""),
                    "tipo_documento": doc_meta.get("tipo_documento", ""),
                    "criterio": item.get("name"),
                    "chave": item.get("canonical_key"),
                    "evento": item.get("event_type"),
                    "comparacao": item.get("comparison"),
                    "limite": item.get("threshold_display"),
                    "threshold_value": item.get("threshold_value"),
                    "threshold_unit": item.get("threshold_unit"),
                    "monitorabilidade_ime": mapping.get("status"),
                    "metrica_ime": mapping.get("ime_metric"),
                    "fonte_pagina": f"{item.get('source_document')} · ID {source_id}",
                    "trecho": item.get("source_excerpt") or item.get("formula_text"),
                    "data_sort": parse_date_sort(doc_meta.get("data_referencia", "")),
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame.sort_values(["grupo", "cnpj", "chave", "data_sort", "documento_id"]).reset_index(drop=True)
    changed: list[str] = []
    previous_by_key: dict[tuple[str, str], tuple[str, str]] = {}
    for _, row in frame.iterrows():
        key = (str(row["cnpj"]), str(row["chave"]))
        current = (str(row.get("comparacao", "")), str(row.get("limite", "")))
        previous = previous_by_key.get(key)
        if previous is None:
            changed.append("primeira evidência local")
        elif previous != current:
            changed.append(f"alterou de {previous[0]} {previous[1]} para {current[0]} {current[1]}")
        else:
            changed.append("sem mudança vs evidência anterior")
        previous_by_key[key] = current
    frame["mudanca_vs_evidencia_anterior"] = changed
    return frame.drop(columns=["data_sort"])


def build_eligibility_table(knowledge: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for cnpj, payload in knowledge.items():
        for item in payload.get("eligibility_criteria", []) or []:
            rows.append(
                {
                    "grupo": TARGET_FUNDS[cnpj]["grupo"],
                    "fundo": payload.get("fund_name") or TARGET_FUNDS[cnpj]["nome_curto"],
                    "nome_curto": TARGET_FUNDS[cnpj]["nome_curto"],
                    "cnpj": format_cnpj(cnpj),
                    "criterio": item.get("name"),
                    "descricao": item.get("description"),
                    "trecho": item.get("source_excerpt"),
                }
            )
    return pd.DataFrame(rows)


def build_timeline(inventory: pd.DataFrame) -> pd.DataFrame:
    if inventory.empty:
        return inventory
    frame = inventory.copy()
    frame["data_sort"] = frame["data_referencia"].map(parse_date_sort)
    frame["evento"] = frame.apply(timeline_event_label, axis=1)
    cols = [
        "grupo",
        "fundo",
        "nome_curto",
        "cnpj",
        "data_referencia",
        "evento",
        "categoria",
        "tipo_documento",
        "especie",
        "documento_id",
        "arquivo_local_existe",
        "source_file",
    ]
    return frame.sort_values(["grupo", "cnpj", "data_sort", "documento_id"])[cols].reset_index(drop=True)


def write_topic_tables(evidence: pd.DataFrame, inventory: pd.DataFrame, emissions: pd.DataFrame) -> None:
    topic_to_output = {
        "alteracoes_assembleias": OUTPUTS["assemblies"],
        "cotistas_partes_relacionadas": OUTPUTS["cotistas"],
        "direitos_creditorios_cessoes": OUTPUTS["cessions"],
        "governanca_operacional": OUTPUTS["governance"],
        "triggers_protecao": OUTPUTS["reg_changes"],
        "preco_economia": OUTPUTS["pricing"],
    }
    for topic, output in topic_to_output.items():
        subset = evidence[evidence["categoria_evidencia"] == topic].copy() if not evidence.empty else pd.DataFrame()
        subset.to_csv(output, index=False)

    amortization_evidence = evidence[evidence["categoria_evidencia"] == "amortizacao"].copy() if not evidence.empty else pd.DataFrame()
    if not emissions.empty:
        emission_cols = [c for c in emissions.columns if c.lower() in {"fundo", "cnpj", "cota/classe", "classe/série", "tipo", "data deliberação", "data emissão / 1ª integralização", "data encerramento/oferta", "quantidade", "volume", "vnu", "remuneração", "juros/remuneração", "amortização principal", "amortização/vencimento", "fonte", "status/evidência"}]
        emission_part = emissions[emission_cols].copy() if emission_cols else pd.DataFrame()
        emission_part["categoria_evidencia"] = "emissoes_curadas"
        if not amortization_evidence.empty:
            amortization_evidence = pd.concat([emission_part, amortization_evidence], ignore_index=True, sort=False)
        else:
            amortization_evidence = emission_part
    amortization_evidence.to_csv(OUTPUTS["amortizations"], index=False)


def build_performance_metrics() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    cache_by_cnpj = find_ime_caches()
    selected_indicators = [
        "PL (R$)",
        "Dir Cred (R$ MM)",
        "Dir Cred / PL",
        "Vencidos Over 30 d / Crédito",
        "Vencidos Over 60 d / Crédito",
        "Vencidos Over 90 d / Crédito",
        "Vencidos Over 180 d / Crédito",
        "Vencidos Over 360 d / Crédito",
        "PDD (R$ MM)",
        "PDD / Crédito",
        "PDD / Venc Total",
        "Cotas SR / PL %",
        "Cotas MZ / PL %",
        "Cotas Sub / PL %",
        "Rentabilidade SR % a.m.",
        "Rentabilidade MZ % a.m.",
        "Rentabilidade Sub % a.m.",
    ]
    for cnpj, meta in TARGET_FUNDS.items():
        cache = cache_by_cnpj.get(cnpj)
        if not cache:
            rows.append(
                {
                    "grupo": meta["grupo"],
                    "fundo": "",
                    "nome_curto": meta["nome_curto"],
                    "cnpj": format_cnpj(cnpj),
                    "competencia": "",
                    "indicador": "Lacuna IME",
                    "valor": None,
                    "unidade": "",
                    "observacao": "Nenhum cache local de Informe Mensal Estruturado encontrado para este CNPJ.",
                    "cache_folder": "",
                }
            )
            continue
        try:
            wide = read_wide_csv(cache["wide_path"])
            comps = competencia_columns(wide)
            tables = build_monitoring_tables(wide, comps, cnpj=cnpj)
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "grupo": meta["grupo"],
                    "fundo": cache.get("fund_name", ""),
                    "nome_curto": meta["nome_curto"],
                    "cnpj": format_cnpj(cnpj),
                    "competencia": "",
                    "indicador": "Erro IME",
                    "valor": None,
                    "unidade": "",
                    "observacao": f"Falha ao ler cache IME: {exc}",
                    "cache_folder": str(cache["folder"].relative_to(ROOT)),
                }
            )
            continue
        indicators = tables.indicators_df
        for indicator in selected_indicators:
            row = indicators[indicators["indicador"] == indicator]
            if row.empty:
                continue
            row = row.iloc[0]
            for comp in comps:
                value = row.get(comp)
                if pd.isna(value):
                    value = None
                rows.append(
                    {
                        "grupo": meta["grupo"],
                        "fundo": cache.get("fund_name", ""),
                        "nome_curto": meta["nome_curto"],
                        "cnpj": format_cnpj(cnpj),
                        "competencia": comp,
                        "indicador": indicator,
                        "valor": value,
                        "unidade": row.get("unidade", ""),
                        "observacao": "",
                        "cache_folder": str(cache["folder"].relative_to(ROOT)),
                    }
                )
    return pd.DataFrame(rows)


def find_ime_caches() -> dict[str, dict[str, Any]]:
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not IME_CACHE_DIR.exists():
        return {}
    for manifest in IME_CACHE_DIR.glob("*/manifest.json"):
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        cnpj = digits(str(payload.get("cnpj_fundo", "")))
        if cnpj not in TARGET_FUNDS:
            continue
        wide_path = manifest.parent / "informes_wide.csv"
        if not wide_path.exists():
            continue
        try:
            wide = pd.read_csv(wide_path, dtype=str, keep_default_na=False, nrows=5)
            comp_count = len([c for c in wide.columns if re.fullmatch(r"\d{2}/\d{4}|\d{2}/\d{2}", str(c))])
        except Exception:  # noqa: BLE001
            comp_count = 0
        candidates[cnpj].append(
            {
                "folder": manifest.parent,
                "wide_path": wide_path,
                "fund_name": payload.get("nome_fundo", ""),
                "data_inicial": payload.get("data_inicial", ""),
                "data_final": payload.get("data_final", ""),
                "comp_count": comp_count,
            }
        )
    return {cnpj: sorted(rows, key=lambda x: (x["comp_count"], str(x["data_final"])), reverse=True)[0] for cnpj, rows in candidates.items()}


def build_markdown_report(
    *,
    inventory: pd.DataFrame,
    coverage: pd.DataFrame,
    evidence: pd.DataFrame,
    doc_digest: pd.DataFrame,
    emissions: pd.DataFrame,
    criteria: pd.DataFrame,
    threshold_versions: pd.DataFrame,
    eligibility: pd.DataFrame,
    timeline: pd.DataFrame,
    performance: pd.DataFrame,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = []
    lines.append("# Deep dive documental — Sellers e Mercado Crédito")
    lines.append("")
    lines.append(f"Gerado em `{now}` a partir exclusivamente de artefatos locais do repositório.")
    lines.append("")
    lines.append("## Resumo executivo")
    lines.append("")
    lines.append(
        "A varredura cobriu sete veículos: três Sellers e quatro Mercado Crédito. "
        "Foram combinados três níveis de evidência: (i) inventário CVM/regulatory_knowledge, "
        "(ii) PDFs efetivamente existentes em `data/raw/<cnpj>/`, e (iii) caches locais de IME quando disponíveis. "
        "Documentos inventariados sem PDF local foram mantidos como lacuna documental, sem inferência de conteúdo."
    )
    lines.append("")
    lines.append(md_table(coverage, max_rows=20))
    lines.append("")
    lines.append("### Principais conclusões suportadas pela base local")
    lines.append("")
    lines.extend(
        [
            "- Sellers possui curadoria mais completa já estruturada para emissões, subordinação mínima, índices de cobertura e cronogramas de amortização, com suplementos e atas locais cobrindo a formação das séries.",
            "- Mercado Crédito tem maior volume de documentos locais e muitos eventos de assembleia/regulamento, mas os documentos de rating, informes trimestrais e demonstrações financeiras aparecem majoritariamente apenas no inventário, sem PDF local baixado nesta base.",
            "- Em ambos os grupos, vários gatilhos são monitoráveis apenas parcialmente pelo IME: o IME traz PL, direitos creditórios, caixa, PDD, atraso por bucket e cotas, mas não traz de forma padronizada fatores de ponderação, valor presente contratual, reservas regulatórias completas, cronogramas futuros e condições de elegibilidade no nível de contrato.",
            "- Nenhuma métrica contratual deve ser automatizada como breach duro sem validação do texto-fonte mais recente e parametrização manual quando a fonte exige fator, reserva, covenant ou definição não observável no IME.",
        ]
    )
    lines.append("")
    lines.append("## Metodologia e rastreabilidade")
    lines.append("")
    lines.append(
        "Para cada PDF local, o script extraiu texto por página com `pypdf` e registrou evidências por tema. "
        "Cada linha de evidência contém CNPJ, fundo, documento, página, termos encontrados e trecho. "
        "Quando a extração de texto falhou, a linha foi classificada como lacuna/OCR necessário."
    )
    lines.append("")
    lines.append("Arquivos gerados:")
    for key, path in OUTPUTS.items():
        if key == "report":
            continue
        lines.append(f"- `{path.relative_to(ROOT)}`")
    lines.append("")

    lines.append("## Digest documento a documento")
    lines.append("")
    lines.append(
        "Cada documento inventariado recebeu status próprio. Para PDFs locais, a tabela aponta categorias de evidência e páginas onde houve hits; "
        "para documentos sem PDF local, o status fica como lacuna, sem interpretação."
    )
    lines.append("")
    lines.append(md_table(select_existing(doc_digest, ["grupo", "nome_curto", "cnpj", "data_referencia", "categoria", "tipo_documento", "documento_id", "status_auditoria", "page_count", "categorias_com_evidencia"]), max_rows=60))
    lines.append("")

    lines.append("## 1. Mapeamento das emissões")
    lines.append("")
    if emissions.empty:
        lines.append("Não há tabela curada de emissões para os CNPJs alvo nos artefatos locais.")
    else:
        lines.append(
            "A tabela consolidada abaixo vem das curadorias locais já existentes e preserva a coluna de fonte. "
            "Campos vazios significam ausência na extração documental local, não inexistência econômica."
        )
        lines.append("")
        lines.append(md_table(select_existing(emissions, ["Fundo", "CNPJ", "Cota/Classe", "Classe/Série", "Tipo", "Data deliberação", "Data emissão / 1ª integralização", "Quantidade", "Volume", "Remuneração", "Amortização principal", "Fonte"]), max_rows=30))
    lines.append("")

    lines.append("## 2. Preço e economia das emissões")
    lines.append("")
    pricing = read_output_or_empty("pricing")
    lines.append(topic_summary(pricing, "preço/remuneração/CDI/spread/ágio/deságio", max_rows=18))
    lines.append("")

    lines.append("## 3. Cronograma de amortização")
    lines.append("")
    amort = read_output_or_empty("amortizations")
    lines.append(topic_summary(amort, "amortização, resgate, vencimento, carência e revolvência", max_rows=25))
    lines.append("")

    lines.append("## 4. Alterações via atas e assembleias")
    lines.append("")
    assemblies = read_output_or_empty("assemblies")
    lines.append(topic_summary(assemblies, "assembleias, deliberações, alterações, waivers e aditamentos", max_rows=25))
    lines.append("")

    lines.append("## 5. Cotistas e partes relacionadas")
    lines.append("")
    cotistas = read_output_or_empty("cotistas")
    lines.append(topic_summary(cotistas, "cotistas, cedentes, originadores, partes relacionadas e concentração", max_rows=18))
    lines.append("")

    lines.append("## 6. Direitos creditórios e cessões")
    lines.append("")
    cessions = read_output_or_empty("cessions")
    lines.append(topic_summary(cessions, "direitos creditórios, cessão, elegibilidade, recompra, substituição e dilution", max_rows=25))
    lines.append("")
    if not eligibility.empty:
        lines.append("Amostra de critérios de elegibilidade extraídos:")
        lines.append("")
        lines.append(md_table(eligibility[["grupo", "nome_curto", "cnpj", "criterio", "descricao"]], max_rows=20))
    lines.append("")

    lines.append("## 7. Performance e risco")
    lines.append("")
    lines.append(
        "Performance histórica foi reconstruída apenas quando existia cache local de `Informe Mensal Estruturado`; "
        "para CNPJs sem cache, a lacuna fica explícita em `sellers_mercado_credito_performance_metrics.csv`."
    )
    lines.append("")
    lines.append(md_table(performance_summary(performance), max_rows=30))
    lines.append("")

    lines.append("## 8. Governança e operacional")
    lines.append("")
    governance = read_output_or_empty("governance")
    lines.append(topic_summary(governance, "administrador, gestor, custodiante, escriturador, auditor, rating e prestadores", max_rows=25))
    lines.append("")

    lines.append("## 9. Triggers, eventos e monitorabilidade pelo IME")
    lines.append("")

    lines.append("### Evolução documental de limites e thresholds")
    lines.append("")
    if threshold_versions.empty:
        lines.append("Não foram extraídos limites versionados dos documentos locais.")
    else:
        lines.append(
            "A tabela abaixo ordena as evidências por fundo, chave canônica e data do documento, marcando alteração de limite quando o par comparação/limite muda."
        )
        lines.append("")
        lines.append(md_table(select_existing(threshold_versions, ["grupo", "nome_curto", "cnpj", "data_documento", "documento_id", "criterio", "chave", "comparacao", "limite", "monitorabilidade_ime", "mudanca_vs_evidencia_anterior", "fonte_pagina"]), max_rows=50))
    lines.append("")
    if criteria.empty:
        lines.append("Nenhum critério estruturado foi encontrado nos artefatos locais.")
    else:
        cols = ["Fundo", "CNPJ", "Critério", "Chave", "Limite/regra", "Limite", "Monitorabilidade IME", "Métrica IME / proxy", "Observação técnica", "Fonte"]
        lines.append(md_table(select_existing(criteria, cols), max_rows=40))
    lines.append("")

    lines.append("## 10. Timeline histórica consolidada")
    lines.append("")
    lines.append(md_table(timeline[["grupo", "nome_curto", "cnpj", "data_referencia", "evento", "documento_id", "arquivo_local_existe"]], max_rows=60))
    lines.append("")

    lines.append("## Comparativo Sellers vs Mercado Crédito")
    lines.append("")
    lines.extend(build_comparison_bullets(coverage, criteria, emissions, performance))
    lines.append("")

    lines.append("## Lacunas e conflitos identificados")
    lines.append("")
    missing = inventory[inventory["arquivo_local_existe"] != True]  # noqa: E712
    if missing.empty:
        lines.append("Não há documentos inventariados sem PDF local para os CNPJs analisados.")
    else:
        lines.append(
            "Há documentos inventariados sem arquivo local, sobretudo relatórios de rating, informes trimestrais e demonstrações financeiras. "
            "Esses documentos não foram interpretados nesta rodada; a ausência não deve ser lida como ausência de evento econômico/jurídico."
        )
        lines.append("")
        lines.append(md_table(missing[["grupo", "nome_curto", "cnpj", "data_referencia", "categoria", "tipo_documento", "documento_id"]], max_rows=50))
    lines.append("")

    lines.append("## Observação de auditoria")
    lines.append("")
    lines.append(
        "Este relatório não substitui leitura jurídica final dos documentos-fonte. "
        "Ele organiza evidências documentais locais e aponta onde cada conclusão pode ser verificada. "
        "Trechos longos e todos os hits por página estão nos CSVs de evidência; o Markdown mostra apenas amostras para legibilidade."
    )
    lines.append("")
    return "\n".join(lines)


def topic_summary(df: pd.DataFrame, label: str, *, max_rows: int) -> str:
    if df.empty:
        return f"Não foram encontrados trechos locais classificados como {label}."
    cols = ["grupo", "nome_curto", "cnpj", "data_referencia", "fonte_pagina", "termos_encontrados", "trecho"]
    return md_table(select_existing(df, cols), max_rows=max_rows)


def performance_summary(performance: pd.DataFrame) -> pd.DataFrame:
    if performance.empty:
        return pd.DataFrame()
    frame = performance.copy()
    lacuna = frame[frame["indicador"].isin(["Lacuna IME", "Erro IME"])]
    data = frame[~frame["indicador"].isin(["Lacuna IME", "Erro IME"])].copy()
    rows: list[dict[str, Any]] = []
    if not data.empty:
        data["valor_num"] = pd.to_numeric(data["valor"], errors="coerce")
        for (grupo, nome, cnpj, indicador), grp in data.groupby(["grupo", "nome_curto", "cnpj", "indicador"], dropna=False):
            valid = grp.dropna(subset=["valor_num"])
            rows.append(
                {
                    "grupo": grupo,
                    "nome_curto": nome,
                    "cnpj": cnpj,
                    "indicador": indicador,
                    "competencias": f"{grp['competencia'].min()} a {grp['competencia'].max()}",
                    "ultimo_valor": valid.sort_values("competencia")["valor_num"].iloc[-1] if not valid.empty else None,
                    "observacao": "",
                }
            )
    for _, row in lacuna.iterrows():
        rows.append(
            {
                "grupo": row["grupo"],
                "nome_curto": row["nome_curto"],
                "cnpj": row["cnpj"],
                "indicador": row["indicador"],
                "competencias": "",
                "ultimo_valor": "",
                "observacao": row["observacao"],
            }
        )
    return pd.DataFrame(rows)


def build_comparison_bullets(
    coverage: pd.DataFrame,
    criteria: pd.DataFrame,
    emissions: pd.DataFrame,
    performance: pd.DataFrame,
) -> list[str]:
    lines: list[str] = []
    for group in ["Sellers", "Mercado Crédito"]:
        cov = coverage[coverage["grupo"] == group]
        local_docs = int(cov["pdfs_locais_analisaveis"].sum()) if not cov.empty else 0
        missing_docs = int(cov["documentos_sem_pdf_local"].sum()) if not cov.empty else 0
        crit_count = len(criteria[criteria.get("CNPJ", pd.Series(dtype=str)).map(digits).isin([c for c, m in TARGET_FUNDS.items() if m["grupo"] == group])]) if not criteria.empty and "CNPJ" in criteria.columns else 0
        emis_count = len(emissions[emissions.get("cnpj_digits", pd.Series(dtype=str)).isin([c for c, m in TARGET_FUNDS.items() if m["grupo"] == group])]) if not emissions.empty and "cnpj_digits" in emissions.columns else 0
        lines.append(
            f"- **{group}:** {local_docs} PDFs locais analisáveis, {missing_docs} documentos inventariados sem PDF local, "
            f"{crit_count} linhas de critérios/monitorabilidade e {emis_count} linhas de emissões/cronogramas nas curadorias locais."
        )
    lines.extend(
        [
            "- **Agressividade estrutural:** Sellers tende a explicitar subordinação júnior mínima e índices de cobertura por série; Mercado Crédito apresenta maior customização por veículo/série e maior volume de alterações regulatórias/assembleares.",
            "- **Monitorabilidade:** para ambos, PL, direitos creditórios, atraso por buckets, PDD, cotas e rentabilidade podem ser acompanhados via IME. Índices que dependem de valor presente, fatores de ponderação, reservas ou contratos subjacentes exigem parametrização manual.",
            "- **Transparência documental local:** Mercado Crédito tem mais documentos locais baixados, mas também maior quantidade de documentos relevantes apenas inventariados. Sellers tem curadoria manual mais completa dos suplementos centrais já existente no repositório.",
            "- **Risco operacional de automação:** a diversidade de definições contratuais impede criar gatilhos genéricos sem versionamento por fundo, data de vigência e fonte documental.",
        ]
    )
    return lines


def read_output_or_empty(key: str) -> pd.DataFrame:
    path = OUTPUTS[key]
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def select_existing(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    existing = [c for c in cols if c in df.columns]
    return df[existing].copy() if existing else df.copy()


def md_table(df: pd.DataFrame, *, max_rows: int = 20) -> str:
    if df.empty:
        return "_Sem dados._"
    shown = df.head(max_rows).copy()
    for col in shown.columns:
        shown[col] = shown[col].map(lambda x: truncate_markdown_cell(x, 180))
    suffix = ""
    if len(df) > max_rows:
        suffix = f"\n\n_Exibindo {max_rows} de {len(df)} linhas. Ver CSV para a tabela completa._"
    headers = [str(col) for col in shown.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for _, row in shown.iterrows():
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in shown.columns) + " |")
    return "\n".join(lines) + suffix


def truncate_markdown_cell(value: Any, length: int) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).replace("\n", " ").replace("|", "\\|")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= length:
        return text
    return text[: length - 1].rstrip() + "…"


def snippets_for_patterns(pages: list[PdfPage], patterns: list[str], *, limit_per_doc: int) -> list[tuple[int, set[str], str]]:
    compiled = [(pattern, re.compile(pattern, flags=re.IGNORECASE)) for pattern in patterns]
    snippets: list[tuple[int, set[str], str]] = []
    seen: set[tuple[int, str]] = set()
    for page in pages:
        page_text = page.text
        if not page_text:
            continue
        matched_terms: set[str] = set()
        first_span: tuple[int, int] | None = None
        for pattern, regex in compiled:
            match = regex.search(page_text)
            if match:
                matched_terms.add(pattern)
                if first_span is None or match.start() < first_span[0]:
                    first_span = (match.start(), match.end())
        if not matched_terms or first_span is None:
            continue
        excerpt = window(page_text, first_span[0], first_span[1])
        key = (page.page, excerpt[:120])
        if key in seen:
            continue
        seen.add(key)
        snippets.append((page.page, matched_terms, excerpt))
        if len(snippets) >= limit_per_doc:
            break
    return snippets


def extract_pdf_pages(path: Path) -> list[PdfPage]:
    pages: list[PdfPage] = []
    try:
        reader = PdfReader(str(path))
    except Exception:  # noqa: BLE001
        return pages
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        text = re.sub(r"\s+", " ", text).strip()
        pages.append(PdfPage(page=idx, text=text))
    return pages


def count_pdf_pages(path: Path | None) -> int | None:
    if path is None:
        return None
    try:
        return len(PdfReader(str(path)).pages)
    except Exception:  # noqa: BLE001
        return None


def window(text: str, start: int, end: int, *, radius: int = 450) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    prefix = "..." if left > 0 else ""
    suffix = "..." if right < len(text) else ""
    return f"{prefix}{text[left:right]}{suffix}"


def clean_excerpt(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def format_cnpj(cnpj: str) -> str:
    c = digits(cnpj)
    if len(c) != 14:
        return c
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def parse_date_sort(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "9999-99-99"
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d", "%m/%Y", "%m/%y"):
        try:
            return datetime.strptime(text[:16] if "%H" in fmt else text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    match = re.search(r"(20\d{2})[-_](\d{2})[-_](\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    match = re.search(r"(\d{2})/(\d{4})", text)
    if match:
        return f"{match.group(2)}-{match.group(1)}-01"
    return "9999-99-99"


def date_from_filename(name: str) -> str:
    match = re.search(r"(20\d{2})-(\d{2})-(\d{2})", name)
    if match:
        return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"
    return ""


def classification_from_filename(name: str) -> str:
    parts = name.split("_")
    if len(parts) >= 2:
        return parts[1]
    return ""


def timeline_event_label(row: pd.Series) -> str:
    category = str(row.get("categoria", "")).lower()
    doc_type = str(row.get("tipo_documento", "")).lower()
    species = str(row.get("especie", "")).lower()
    text = " ".join([category, doc_type, species])
    if "regul" in text:
        return "Regulamento / alteração regulatória"
    if "assembleia" in text or "age" in text or "ago" in text:
        return "Assembleia / deliberação"
    if "emiss" in text or "anúncio" in text or "aviso ao mercado" in text:
        return "Oferta / emissão de cotas"
    if "rating" in text:
        return "Relatório de rating"
    if "demonstra" in text:
        return "Demonstrações financeiras"
    if "trimestral" in text:
        return "Informe trimestral"
    if "cotista" in text or "evento" in text:
        return "Comunicação / evento"
    return "Outro documento CVM"


if __name__ == "__main__":
    main()
