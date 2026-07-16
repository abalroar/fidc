from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import math
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.fundonet_client import FundosNetClient  # noqa: E402
from services.fundonet_documents import build_document_filename  # noqa: E402
from services.regulatory_knowledge import classify_document  # noqa: E402


logging.getLogger("pypdf").setLevel(logging.ERROR)

DEFAULT_ISSUANCE_DIR = Path("outputs/fidc_issuance_study_20260609")
DEFAULT_CLASSIFICATION_DIR = Path("outputs/fidc_classification_practices_20260609")
DEFAULT_PLAN_DIR = Path("outputs/fidc_director_diagnostic_plan_20260609")
DEFAULT_OUTPUT_DIR = Path("outputs/fidc_director_deep_diagnostic_20260609")
RAW_DIR = Path("data/raw")
CRITERIA_PATH = Path("data/regulatory_profiles/all_fidcs_criteria_monitoraveis_ime.csv")
CURATED_EMISSIONS_PATH = Path("data/regulatory_profiles/all_fidcs_cotas_emissoes_pagamentos.csv")
KNOWLEDGE_DIR = Path("data/regulatory_knowledge")
AS_OF_DATE = pd.Timestamp("2026-06-09")
START_DATE = pd.Timestamp("2024-01-01")


FEATURE_KEYS = [
    "asset_class_confirmed",
    "named_originator_or_cedente",
    "named_debtor_or_sacado",
    "revolving_period",
    "subordination_minimum",
    "mezzanine_layer",
    "cash_or_liquidity_reserve",
    "repurchase_or_indemnity",
    "eligibility_criteria",
    "concentration_limits",
    "default_or_performance_triggers",
    "rating_required",
    "derivatives_allowed",
    "amortization_profile_defined",
]

DOC_PRIORITY = {
    "regulamento": 4,
    "emissao": 3,
    "assembleia": 2,
    "evento": 1,
    "outro": 0,
}


@dataclass(frozen=True)
class FeatureValue:
    value: str
    evidence: str
    numeric_value: float | None = None


def only_digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def normalize_text(value: object) -> str:
    text = str(value or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    text = re.sub(r"[^A-Z0-9%$+.,:/()\- ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: object, *, max_len: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if text.lower() in {"nan", "none", "nat"}:
        text = ""
    if max_len and len(text) > max_len:
        return text[: max_len - 1].rstrip() + "..."
    return text


def parse_date_any(value: object) -> pd.Timestamp | pd.NaT:
    text = clean_text(value)
    if not text:
        return pd.NaT
    return pd.to_datetime(text, errors="coerce", dayfirst=True)


def parse_date_from_filename(path: Path) -> pd.Timestamp | pd.NaT:
    match = re.search(r"_(20\d{2}-\d{2}-\d{2})\.pdf$", path.name)
    if match:
        return pd.to_datetime(match.group(1), errors="coerce")
    return pd.NaT


def parse_brl(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("\u00a0", " ")
    text = re.sub(r"R\$|\s", "", text, flags=re.IGNORECASE)
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def format_brl(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"R$ {number:,.0f}".replace(",", "_").replace(".", ",").replace("_", ".")


def format_pct(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if math.isnan(number):
        return ""
    return f"{number:.2f}%".replace(".", ",")


def format_share(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if math.isnan(number):
        return ""
    return format_pct(number * 100)


def load_classification_module() -> Any:
    import importlib.util

    path = ROOT / "scripts/classify_fidc_sectors_and_practices.py"
    spec = importlib.util.spec_from_file_location("fidc_sector_rules", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Nao foi possivel carregar regras setoriais.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fundonet_storage_name(document: Any, *, classification: str) -> str:
    name = build_document_filename(document, default_stem=f"{classification}_{document.id}")
    stem = Path(name).stem
    suffix = Path(name).suffix or ".pdf"
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or f"{classification}_{document.id}"
    date_part = ""
    ref = getattr(document, "data_referencia_dt", None)
    if ref is not None:
        date_part = f"_{ref.isoformat()}"
    return f"{document.id}_{classification}_{safe_stem}{date_part}{suffix.lower()}"


def download_review_documents(
    review_queue: pd.DataFrame,
    *,
    output_dir: Path,
    limit: int,
    offset: int,
    max_docs_per_fund: int,
    timeout_seconds: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if limit <= 0 or review_queue.empty:
        return pd.DataFrame(rows)

    queue = review_queue.copy()
    queue["priority_rank_numeric"] = pd.to_numeric(queue.get("priority_rank", ""), errors="coerce")
    offset = max(0, int(offset))
    queue = queue.sort_values("priority_rank_numeric", na_position="last").iloc[offset : offset + limit]
    client = FundosNetClient(timeout_seconds=timeout_seconds, max_retries=1)

    for index, row in queue.iterrows():
        cnpj = only_digits(row.get("cnpj_emissor"))
        name = clean_text(row.get("nome_emissor"))
        if len(cnpj) != 14:
            continue
        fund_dir = RAW_DIR / cnpj
        fund_dir.mkdir(parents=True, exist_ok=True)
        print(f"[download {len(rows) + 1}] {cnpj} {clean_text(name, max_len=74)}", flush=True)
        try:
            docs = client.listar_documentos(cnpj, error_stage="listar_documentos_diagnostic")
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "cnpj": cnpj,
                    "nome": name,
                    "status": "erro_listagem",
                    "erro": f"{type(exc).__name__}: {exc}",
                    "documentos_listados": 0,
                    "documentos_baixados": 0,
                }
            )
            print(f"  erro listagem: {type(exc).__name__}: {exc}", flush=True)
            continue

        selected = []
        for doc in docs:
            classification = classify_document(
                categoria=doc.categoria,
                tipo=doc.tipo,
                especie=doc.especie,
                nome_arquivo=doc.nome_arquivo or "",
            )
            if classification not in DOC_PRIORITY or DOC_PRIORITY[classification] <= 0:
                continue
            doc_date = pd.Timestamp(doc.data_referencia_dt) if doc.data_referencia_dt else pd.NaT
            keep_recent = pd.isna(doc_date) or doc_date >= START_DATE
            keep_regulation = classification == "regulamento"
            if keep_recent or keep_regulation:
                selected.append((doc, classification, doc_date))

        selected = sorted(
            selected,
            key=lambda item: (
                DOC_PRIORITY.get(item[1], 0),
                item[2] if not pd.isna(item[2]) else pd.Timestamp.min,
                item[0].id,
            ),
            reverse=True,
        )
        if max_docs_per_fund > 0:
            selected = selected[:max_docs_per_fund]

        downloaded = 0
        errors: list[str] = []
        for doc, classification, _doc_date in selected:
            path = fund_dir / fundonet_storage_name(doc, classification=classification)
            if path.exists() and path.stat().st_size > 0:
                downloaded += 1
                continue
            try:
                content = client.download_documento(doc.id)
                path.write_bytes(content)
                downloaded += 1
                print(f"  baixado {classification}: {path.name}", flush=True)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{doc.id}:{type(exc).__name__}")
                print(f"  erro download {doc.id}: {type(exc).__name__}: {exc}", flush=True)

        rows.append(
            {
                "cnpj": cnpj,
                "nome": name,
                "priority_rank": row.get("priority_rank", ""),
                "status": "ok" if not errors else "parcial",
                "erro": "; ".join(errors),
                "documentos_listados": len(docs),
                "documentos_selecionados": len(selected),
                "documentos_baixados": downloaded,
            }
        )

    out = pd.DataFrame(rows)
    if not out.empty:
        write_csv(out, output_dir / "download_review_documents_status.csv")
    return out


def extract_pdf_text(pdf_path: Path, *, max_pages: int) -> tuple[str, int, str]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages = min(len(reader.pages), max(1, max_pages))
    parts = []
    for page in reader.pages[:pages]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            parts.append("")
    return "\n".join(parts), pages, "pypdf"


def latest_pdf(paths: Iterable[Path]) -> Path | None:
    items = list(paths)
    if not items:
        return None
    return max(
        items,
        key=lambda path: (
            parse_date_from_filename(path) if not pd.isna(parse_date_from_filename(path)) else pd.Timestamp.min,
            path.stat().st_mtime,
            path.name,
        ),
    )


def all_raw_document_inventory() -> pd.DataFrame:
    rows = []
    for fund_dir in sorted(RAW_DIR.glob("*")):
        if not fund_dir.is_dir():
            continue
        cnpj = only_digits(fund_dir.name)
        for path in sorted(fund_dir.glob("*.pdf")):
            lower = path.name.lower()
            if "regulamento" in lower:
                classification = "regulamento"
            elif "emissao" in lower:
                classification = "emissao"
            elif "assembleia" in lower:
                classification = "assembleia"
            elif "evento" in lower:
                classification = "evento"
            else:
                classification = "outro"
            rows.append(
                {
                    "cnpj": cnpj,
                    "document_classification": classification,
                    "source_file": str(path),
                    "file_name": path.name,
                    "document_date": parse_date_from_filename(path).date().isoformat()
                    if not pd.isna(parse_date_from_filename(path))
                    else "",
                    "file_size_bytes": path.stat().st_size,
                }
            )
    return pd.DataFrame(rows)


def first_match_evidence(text_norm: str, patterns: Iterable[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text_norm)
        if match:
            return clean_text(match.group(0), max_len=180)
    return ""


def has_any(text_norm: str, patterns: Iterable[str]) -> FeatureValue:
    evidence = first_match_evidence(text_norm, patterns)
    return FeatureValue("sim" if evidence else "nao", evidence)


def extract_percentages(value: object) -> list[float]:
    text = str(value or "")
    out: list[float] = []
    for match in re.finditer(r"(\d{1,3}(?:[.,]\d{1,3})?)\s*%", text):
        try:
            out.append(float(match.group(1).replace(".", "").replace(",", ".")))
        except ValueError:
            continue
    return out


def plausible_percentages_for_key(rows: pd.DataFrame, key: str) -> list[float]:
    if rows.empty or "Chave" not in rows.columns:
        return []
    subset = rows[rows["Chave"].astype(str).eq(key)]
    values: list[float] = []
    for _, row in subset.iterrows():
        raw_values = extract_percentages(row.get("Limite/regra", ""))
        if not raw_values:
            raw_values = extract_percentages(row.get("Observação técnica", ""))
        for value in raw_values:
            if 0 < value <= 100:
                values.append(value)
    return sorted(set(round(value, 4) for value in values))


def derive_derivatives_profile(text_norm: str, criteria_rows: pd.DataFrame) -> FeatureValue:
    criteria_hit = False
    if not criteria_rows.empty and "Chave" in criteria_rows.columns:
        criteria_hit = criteria_rows["Chave"].astype(str).eq("permitted_hedges").any()
    if re.search(r"VEDAD[AO].{0,160}DERIVATIV", text_norm):
        return FeatureValue("vedado", "VEDADO ... DERIVATIVOS")
    if re.search(r"DERIVATIV.{0,220}(EXCLUSIVAMENTE|SOMENTE|APENAS).{0,120}(PROTECAO|HEDGE)", text_norm) or re.search(
        r"(PROTECAO|HEDGE).{0,180}DERIVATIV", text_norm
    ):
        return FeatureValue("hedge_apenas", "DERIVATIVOS PARA PROTECAO/HEDGE")
    if criteria_hit or "DERIVATIV" in text_norm:
        return FeatureValue("permitido_ou_textual", "Regra textual de derivativos identificada")
    return FeatureValue("nao_identificado", "")


def derive_amortization_profile(text_norm: str) -> FeatureValue:
    if re.search(r"PASS[- ]?THROUGH|REGIME DE CAIXA|FLUXO DE CAIXA", text_norm):
        return FeatureValue("pass_through", first_match_evidence(text_norm, [r"PASS[- ]?THROUGH", r"FLUXO DE CAIXA"]))
    if re.search(r"PERIODO DE REVOLVENCIA|PERIODO REVOLVENTE|REVOLVENCIA", text_norm) and re.search(
        r"AMORTIZACAO", text_norm
    ):
        return FeatureValue("revolvente_mais_amortizacao", "REVOLVENCIA + AMORTIZACAO")
    if re.search(r"BULLET|RESGATE.{0,80}VENCIMENTO|PAGAMENTO.{0,80}DATA DE VENCIMENTO", text_norm):
        return FeatureValue("bullet", first_match_evidence(text_norm, [r"BULLET", r"RESGATE.{0,80}VENCIMENTO"]))
    if re.search(r"AMORTIZACAO.{0,120}(PROGRAMADA|MENSAL|TRIMESTRAL|SEMESTRAL|PERIODICA)", text_norm):
        return FeatureValue("amortizacao_programada", first_match_evidence(text_norm, [r"AMORTIZACAO.{0,120}(PROGRAMADA|MENSAL|TRIMESTRAL|SEMESTRAL|PERIODICA)"]))
    if "AMORTIZACAO" in text_norm:
        return FeatureValue("definido_textual", "AMORTIZACAO")
    return FeatureValue("nao_identificado", "")


def build_feature_matrix(
    *,
    issuer_map: pd.DataFrame,
    criteria: pd.DataFrame,
    output_dir: Path,
    max_pages: int,
    sector_rules: Any,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    inventory = all_raw_document_inventory()
    if inventory.empty:
        return pd.DataFrame(), inventory

    criteria = criteria.copy()
    criteria["cnpj_digits"] = criteria.get("CNPJ", pd.Series(dtype=str)).map(only_digits) if not criteria.empty else ""
    issuer_lookup = issuer_map.set_index("cnpj_emissor").to_dict(orient="index") if not issuer_map.empty else {}

    text_cache_dir = output_dir / "pdf_text_cache"
    text_cache_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    grouped_inventory = list(inventory.groupby("cnpj"))
    for position, (cnpj, docs) in enumerate(grouped_inventory, start=1):
        print(f"[reg {position}/{len(grouped_inventory)}] {cnpj}", flush=True)
        reg_paths = [Path(path) for path in docs.loc[docs["document_classification"].eq("regulamento"), "source_file"]]
        latest_reg = latest_pdf(reg_paths)
        text = ""
        pages = 0
        extraction_status = "sem_regulamento"
        if latest_reg is not None:
            cache_path = text_cache_dir / f"{cnpj}_{latest_reg.stem}.txt"
            if cache_path.exists() and cache_path.stat().st_size > 0:
                text = cache_path.read_text(encoding="utf-8", errors="replace")
                pages = -1
                extraction_status = "cache"
            else:
                try:
                    text, pages, _method = extract_pdf_text(latest_reg, max_pages=max_pages)
                    cache_path.write_text(text, encoding="utf-8", errors="replace")
                    extraction_status = "ok"
                except Exception as exc:  # noqa: BLE001
                    extraction_status = f"erro_pdf:{type(exc).__name__}"
        text_norm = normalize_text(text)
        base = issuer_lookup.get(cnpj, {})
        fund_name = clean_text(base.get("nome_emissor")) or knowledge_fund_name(cnpj) or cnpj
        criteria_rows = criteria[criteria["cnpj_digits"].eq(cnpj)] if not criteria.empty else pd.DataFrame()

        classification_window = text_norm[:50000]
        doc_classification = sector_rules.classify_texts(
            {
                "nome_fundo": fund_name,
                "descricao_lastro": classification_window,
                "observacao_tecnica": classification_window,
            }
        )
        meta_setor_n1 = clean_text(base.get("setor_n1")) or "Sem oferta CVM mapeada"
        meta_setor_n2 = clean_text(base.get("setor_n2")) or "Sem oferta CVM mapeada"
        meta_conf = clean_text(base.get("confidence")) or ""
        if meta_setor_n1 == "Não classificado" or meta_setor_n1 == "Nao classificado" or not meta_setor_n1:
            final_setor_n1 = doc_classification.setor_n1
            final_setor_n2 = doc_classification.setor_n2
            final_source = "documento_regulamento"
        else:
            final_setor_n1 = meta_setor_n1
            final_setor_n2 = meta_setor_n2
            final_source = "metadado_cvm_oferta"

        sub_values = plausible_percentages_for_key(criteria_rows, "subordination_ratio_min")
        cash_values = plausible_percentages_for_key(criteria_rows, "minimum_cash_ratio")
        concentration_values = plausible_percentages_for_key(criteria_rows, "concentration_limits")
        default_values = plausible_percentages_for_key(criteria_rows, "default_rate_evaluation_event")
        credit_alloc_values = plausible_percentages_for_key(criteria_rows, "credit_rights_allocation_min")

        features: dict[str, FeatureValue] = {}
        features["asset_class_confirmed"] = has_any(
            text_norm,
            [
                r"DIREITOS CREDITORIOS.{0,180}(VEICUL|INSS|FGTS|AGRO|AGRONEGOCIO|CARTAO|MEIOS DE PAGAMENTO|DUPLICAT|PRECATOR|CCB|NOTAS COMERCIAIS|IMOBILIAR|ENERGIA|FORNECEDOR)",
                r"OBJETIVO.{0,220}DIREITOS CREDITORIOS",
                r"POLITICA DE INVESTIMENTO.{0,220}DIREITOS CREDITORIOS",
            ],
        )
        features["named_originator_or_cedente"] = has_any(
            text_norm,
            [
                r"CEDENTE[S]?.{0,160}CNPJ",
                r"ORIGINADOR[ES]?.{0,160}CNPJ",
                r"CONSULTOR[A]?.{0,160}CNPJ",
                r"PLATAFORMA.{0,160}CNPJ",
            ],
        )
        features["named_debtor_or_sacado"] = has_any(
            text_norm,
            [
                r"SACADO[S]?.{0,180}CNPJ",
                r"DEVEDOR[ES]?.{0,180}CNPJ",
                r"BANCO[S]? EMISSOR[ES]?",
                r"INSS",
                r"FGTS",
            ],
        )
        features["revolving_period"] = has_any(
            text_norm,
            [
                r"PERIODO DE REVOLVENCIA",
                r"PERIODO REVOLVENTE",
                r"REVOLVENCIA",
                r"AQUISICAO DE NOVOS DIREITOS CREDITORIOS",
            ],
        )
        features["subordination_minimum"] = FeatureValue(
            "sim" if sub_values or "INDICE DE SUBORDINACAO" in text_norm or "RELACAO MINIMA" in text_norm else "nao",
            "; ".join(format_pct(value) for value in sub_values[:6]) or first_match_evidence(text_norm, [r"INDICE DE SUBORDINACAO.{0,140}", r"RELACAO MINIMA.{0,140}"]),
            max(sub_values) if sub_values else None,
        )
        features["mezzanine_layer"] = has_any(text_norm, [r"MEZANIN", r"COTAS SUBORDINADAS MEZANINO"])
        features["cash_or_liquidity_reserve"] = FeatureValue(
            "sim" if cash_values or re.search(r"RESERVA (DE )?(CAIXA|LIQUIDEZ|AMORTIZACAO|DESPESAS)", text_norm) else "nao",
            "; ".join(format_pct(value) for value in cash_values[:6])
            or first_match_evidence(text_norm, [r"RESERVA (DE )?(CAIXA|LIQUIDEZ|AMORTIZACAO|DESPESAS).{0,120}"]),
            max(cash_values) if cash_values else None,
        )
        features["repurchase_or_indemnity"] = has_any(
            text_norm,
            [
                r"RECOMPRA",
                r"SUBSTITUICAO DOS DIREITOS CREDITORIOS",
                r"INDENIZACAO",
                r"OBRIGACAO DE RECOMPRA",
            ],
        )
        features["eligibility_criteria"] = FeatureValue(
            "sim" if "CRITERIOS DE ELEGIBILIDADE" in text_norm or (not criteria_rows.empty and criteria_rows["Chave"].astype(str).eq("eligibility_criteria_text").any()) else "nao",
            first_match_evidence(text_norm, [r"CRITERIOS DE ELEGIBILIDADE.{0,140}"]),
        )
        features["concentration_limits"] = FeatureValue(
            "sim" if concentration_values or re.search(r"LIMITE[S]? DE CONCENTRACAO|CONCENTRACAO MAXIMA|POR CEDENTE|POR SACADO|POR DEVEDOR", text_norm) else "nao",
            "; ".join(format_pct(value) for value in concentration_values[:6])
            or first_match_evidence(text_norm, [r"LIMITE[S]? DE CONCENTRACAO.{0,140}", r"POR (CEDENTE|SACADO|DEVEDOR).{0,120}"]),
            max(concentration_values) if concentration_values else None,
        )
        features["default_or_performance_triggers"] = FeatureValue(
            "sim" if default_values or re.search(r"EVENTOS DE AVALIACAO|EVENTOS DE LIQUIDACAO|INDICE DE INADIMPLENCIA|DIREITOS CREDITORIOS INADIMPLIDOS", text_norm) else "nao",
            "; ".join(format_pct(value) for value in default_values[:6])
            or first_match_evidence(text_norm, [r"EVENTOS DE AVALIACAO.{0,140}", r"INDICE DE INADIMPLENCIA.{0,140}"]),
            max(default_values) if default_values else None,
        )
        features["rating_required"] = has_any(
            text_norm,
            [
                r"CLASSIFICACAO DE RISCO",
                r"AGENCIA DE CLASSIFICACAO",
                r"RATING",
            ],
        )
        features["derivatives_allowed"] = derive_derivatives_profile(text_norm, criteria_rows)
        features["amortization_profile_defined"] = derive_amortization_profile(text_norm)

        monocedente_profile = "indeterminado"
        if re.search(r"MULTI[- ]?CEDENTE|MULTICEDENTE|DIVERSOS CEDENTES", text_norm):
            monocedente_profile = "multicedente"
        elif re.search(r"CEDENTE UNICO|UNICO CEDENTE|MONOCEDENTE", text_norm):
            monocedente_profile = "monocedente"
        elif features["named_originator_or_cedente"].value == "sim":
            monocedente_profile = "cedente_nomeado"

        debtor_profile = "indeterminado"
        if re.search(r"PULVERIZAD|DIVERSOS SACADOS|DIVERSOS DEVEDORES", text_norm):
            debtor_profile = "pulverizado"
        elif re.search(r"UNICO DEVEDOR|UM DEVEDOR|SACADO CONCENTRADO|DEVEDOR CONCENTRADO", text_norm):
            debtor_profile = "concentrado"
        elif features["named_debtor_or_sacado"].value == "sim":
            debtor_profile = "devedor_nomeado"

        row_out: dict[str, object] = {
            "cnpj": cnpj,
            "fund_name": fund_name,
            "setor_n1_metadata": meta_setor_n1,
            "setor_n2_metadata": meta_setor_n2,
            "metadata_confidence": meta_conf,
            "setor_n1_document": doc_classification.setor_n1,
            "setor_n2_document": doc_classification.setor_n2,
            "document_classification_evidence": doc_classification.evidence,
            "setor_n1_final": final_setor_n1,
            "setor_n2_final": final_setor_n2,
            "final_classification_source": final_source,
            "regulamento_count": int(len(reg_paths)),
            "document_count_total": int(len(docs)),
            "latest_regulamento_file": str(latest_reg or ""),
            "latest_regulamento_date": parse_date_from_filename(latest_reg).date().isoformat()
            if latest_reg and not pd.isna(parse_date_from_filename(latest_reg))
            else "",
            "pdf_extraction_status": extraction_status,
            "pages_extracted": pages,
            "monocedente_or_multicedente": monocedente_profile,
            "concentrated_or_pulverized_debtors": debtor_profile,
            "credit_rights_allocation_min_pct": max(credit_alloc_values) if credit_alloc_values else "",
            "subordination_main_pct": max(sub_values) if sub_values else "",
            "subordination_all_pcts": ";".join(format_pct(value) for value in sub_values),
            "cash_reserve_main_pct": max(cash_values) if cash_values else "",
            "concentration_limit_main_pct": max(concentration_values) if concentration_values else "",
            "default_trigger_main_pct": max(default_values) if default_values else "",
        }
        yes_count = 0
        for key in FEATURE_KEYS:
            value = features[key]
            row_out[key] = value.value
            row_out[f"{key}_evidence"] = value.evidence
            if value.value in {"sim", "hedge_apenas", "permitido_ou_textual", "vedado", "pass_through", "revolvente_mais_amortizacao", "bullet", "amortizacao_programada", "definido_textual"}:
                yes_count += 1
        row_out["feature_hits_count"] = yes_count
        row_out["feature_hits_share"] = yes_count / len(FEATURE_KEYS)
        rows.append(row_out)

    matrix = pd.DataFrame(rows)
    if not matrix.empty:
        matrix = matrix.sort_values(["setor_n1_final", "setor_n2_final", "fund_name"])
    return matrix, inventory


def knowledge_fund_name(cnpj: str) -> str:
    path = KNOWLEDGE_DIR / f"{cnpj}.json"
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return clean_text(payload.get("fund_name"))
    except Exception:  # noqa: BLE001
        return ""


def build_feature_prevalence(matrix: pd.DataFrame) -> pd.DataFrame:
    if matrix.empty:
        return pd.DataFrame()
    rows = []
    for (n1, n2), group in matrix.groupby(["setor_n1_final", "setor_n2_final"], dropna=False):
        base: dict[str, object] = {
            "setor_n1": n1,
            "setor_n2": n2,
            "fundos_com_regulamento": int(len(group)),
        }
        for key in FEATURE_KEYS:
            values = group[key].astype(str)
            positive = values.isin(["sim", "hedge_apenas", "permitido_ou_textual", "vedado", "pass_through", "revolvente_mais_amortizacao", "bullet", "amortizacao_programada", "definido_textual"])
            base[f"{key}_share"] = float(positive.mean()) if len(group) else 0.0
            base[f"{key}_count"] = int(positive.sum())
        base["feature_hits_share_median"] = float(pd.to_numeric(group["feature_hits_share"], errors="coerce").median())
        rows.append(base)
    return pd.DataFrame(rows).sort_values(["fundos_com_regulamento", "setor_n1", "setor_n2"], ascending=[False, True, True])


def common_value_bins(values: Iterable[float]) -> str:
    bins: Counter[str] = Counter()
    for value in values:
        rounded = round(float(value) * 2) / 2
        bins[f"{rounded:g}%"] += 1
    return "; ".join(f"{label} ({count})" for label, count in bins.most_common(8))


def build_subordination_summary(matrix: pd.DataFrame) -> pd.DataFrame:
    if matrix.empty or "subordination_main_pct" not in matrix.columns:
        return pd.DataFrame()
    sub = matrix.copy()
    sub["subordination_main_pct_num"] = pd.to_numeric(sub["subordination_main_pct"], errors="coerce")
    sub = sub[sub["subordination_main_pct_num"].notna()]
    rows = []
    for (n1, n2), group in sub.groupby(["setor_n1_final", "setor_n2_final"], dropna=False):
        values = group["subordination_main_pct_num"].astype(float)
        rows.append(
            {
                "setor_n1": n1,
                "setor_n2": n2,
                "fundos_com_subordinacao": int(len(group)),
                "subordinacao_mediana_pct_equal_weight": float(values.median()),
                "subordinacao_p25_pct": float(values.quantile(0.25)),
                "subordinacao_p75_pct": float(values.quantile(0.75)),
                "subordinacao_min_pct": float(values.min()),
                "subordinacao_max_pct": float(values.max()),
                "valores_comuns": common_value_bins(values),
            }
        )
    return pd.DataFrame(rows).sort_values(["fundos_com_subordinacao", "setor_n1"], ascending=[False, True])


def infer_quota_type(value: object) -> str:
    text = normalize_text(value)
    if "SENIOR" in text or "SENIORES" in text:
        return "Senior"
    if "MEZAN" in text:
        return "Mezanino"
    if "SUBORD" in text or "JUNIOR" in text:
        return "Subordinada"
    return "Nao identificado"


def parse_spread_from_text(value: object) -> tuple[str, float | None, float | None, float | None, str]:
    text_raw = clean_text(value)
    text = normalize_text(text_raw)
    if not text:
        return "sem_remuneracao", None, None, None, ""

    for pattern in [
        r"(?:TAXA\s*)?(?:DI|CDI)(?:\s*OVER)?\s*(?:\+|MAIS|ACRESCID[AO]?\s*DE|ACRESCIDA DE|ACRESCIDO DE|ACRESCIDO DA|ACRESCIDA DA|SOBRETAXA(?: SENIOR)?(?: DE)?)\s*(?:ATE\s*)?(\d{1,2}(?:[,.]\d{1,2})?)\s*%",
        r"(?:SOBRETAXA|SPREAD)(?: SENIOR)?(?:\s*DE)?\s*(\d{1,2}(?:[,.]\d{1,2})?)\s*%.*?(?:DI|CDI)",
        r"(?:DI|CDI).{0,160}(?:SOBRETAXA|SPREAD).{0,80}(\d{1,2}(?:[,.]\d{1,2})?)\s*%",
    ]:
        match = re.search(pattern, text)
        if match:
            return "CDI+", float(match.group(1).replace(",", ".")), None, None, match.group(0)

    match_pct_cdi = re.search(r"(\d{2,3}(?:[,.]\d{1,2})?)\s*%\s*(?:DO\s*)?(?:CDI|DI)\b", text)
    if match_pct_cdi:
        return "%CDI", None, float(match_pct_cdi.group(1).replace(",", ".")), None, match_pct_cdi.group(0)

    match_ipca = re.search(r"IPCA\s*(?:\+|MAIS|ACRESCID[AO]?\s*DE)\s*(\d{1,2}(?:[,.]\d{1,2})?)\s*%", text)
    if match_ipca:
        return "IPCA+", None, None, float(match_ipca.group(1).replace(",", ".")), match_ipca.group(0)

    if re.search(r"NAO POSSUEM REMUNERACAO|NAO POSSUI REMUNERACAO|RESIDUAL|EXCEDENTE", text):
        return "Residual", None, None, None, first_match_evidence(text, [r"NAO POSSUEM REMUNERACAO", r"RESIDUAL", r"EXCEDENTE"])
    if "CDI" in text or "TAXA DI" in text:
        return "CDI_textual_sem_spread", None, None, None, first_match_evidence(text, [r"(CDI|TAXA DI).{0,160}"])
    return "outro", None, None, None, ""


def build_pricing_base(emissions: pd.DataFrame, issuer_map: pd.DataFrame) -> pd.DataFrame:
    if emissions.empty:
        return pd.DataFrame()
    df = emissions.copy()
    df["cnpj"] = df.get("CNPJ", "").map(only_digits)
    df["volume_brl"] = df.get("Volume", "").map(parse_brl)
    df["data_deliberacao"] = df.get("Data deliberação", "").map(parse_date_any)
    df["periodo_estudo"] = df["data_deliberacao"].apply(period_label)
    df["tipo_cota_normalizado"] = df.apply(
        lambda row: clean_text(row.get("Tipo")) or infer_quota_type(row.get("Cota/Classe")),
        axis=1,
    )
    parsed = df.get("Remuneração", pd.Series(dtype=str)).map(parse_spread_from_text)
    df["pricing_basis"] = [item[0] for item in parsed]
    df["spread_cdi_aa"] = [item[1] for item in parsed]
    df["pct_cdi"] = [item[2] for item in parsed]
    df["spread_ipca_aa"] = [item[3] for item in parsed]
    df["pricing_evidence"] = [item[4] for item in parsed]
    if not issuer_map.empty:
        lookup = issuer_map[
            [
                "cnpj_emissor",
                "nome_emissor",
                "setor_n1",
                "setor_n2",
                "confidence",
                "volume_total_registrado",
                "volume_encerrado_conservador",
            ]
        ].drop_duplicates("cnpj_emissor")
        df = df.merge(lookup, left_on="cnpj", right_on="cnpj_emissor", how="left")
    else:
        df["setor_n1"] = ""
        df["setor_n2"] = ""
    df["setor_n1"] = df["setor_n1"].fillna("").replace("", "Nao classificado")
    df["setor_n2"] = df["setor_n2"].fillna("").replace("", "Sem classificacao")
    return df


def period_label(ts: pd.Timestamp | pd.NaT) -> str:
    if pd.isna(ts):
        return ""
    if ts < START_DATE or ts > AS_OF_DATE:
        return "fora_do_periodo"
    if ts.year == 2024:
        return "2024FY"
    if ts.year == 2025:
        return "2025FY"
    if ts.year == 2026:
        return "2026YTD"
    return ""


def build_pricing_summary(pricing: pd.DataFrame) -> pd.DataFrame:
    if pricing.empty:
        return pd.DataFrame()
    df = pricing[pricing["periodo_estudo"].isin(["2024FY", "2025FY", "2026YTD"])].copy()
    df["volume_brl"] = pd.to_numeric(df["volume_brl"], errors="coerce").fillna(0)
    rows = []
    for keys, group in df.groupby(["setor_n1", "setor_n2", "tipo_cota_normalizado"], dropna=False):
        cdi = pd.to_numeric(group["spread_cdi_aa"], errors="coerce").dropna()
        rows.append(
            {
                "setor_n1": keys[0],
                "setor_n2": keys[1],
                "tipo_cota": keys[2],
                "linhas_tranche": int(len(group)),
                "fundos_unicos": int(group["cnpj"].nunique()),
                "volume_brl": float(group["volume_brl"].sum()),
                "volume_com_spread_cdi_brl": float(group.loc[group["spread_cdi_aa"].notna(), "volume_brl"].sum()),
                "spread_cdi_mediano_aa": float(cdi.median()) if len(cdi) else None,
                "spread_cdi_p25_aa": float(cdi.quantile(0.25)) if len(cdi) else None,
                "spread_cdi_p75_aa": float(cdi.quantile(0.75)) if len(cdi) else None,
                "share_linhas_com_spread_cdi": float(group["spread_cdi_aa"].notna().mean()) if len(group) else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["volume_brl", "linhas_tranche"], ascending=[False, False])


def build_offer_volume_base(offers: pd.DataFrame, classified_offers: pd.DataFrame) -> pd.DataFrame:
    if classified_offers.empty:
        return pd.DataFrame()
    df = classified_offers.copy()
    for col in ["valor_total_registrado"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["tipo_cota_normalizado"] = df.apply(
        lambda row: infer_quota_type(" ".join(str(row.get(col, "")) for col in ["valor_mobiliario", "classe_ativo", "serie", "emissao"])),
        axis=1,
    )
    return df


def build_participant_rankings(offers: pd.DataFrame, entities: pd.DataFrame, issuer_map: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    sector_lookup = issuer_map.set_index("cnpj_emissor")[["setor_n1", "setor_n2"]].to_dict(orient="index") if not issuer_map.empty else {}

    def add_row(cnpj: str, role: str, name: object, volume: float, line_count: int) -> None:
        participant = clean_text(name)
        if not participant:
            return
        sector = sector_lookup.get(cnpj, {})
        rows.append(
            {
                "cnpj": cnpj,
                "setor_n1": sector.get("setor_n1", "Nao classificado"),
                "setor_n2": sector.get("setor_n2", "Sem classificacao"),
                "role": role,
                "participant": participant,
                "volume_brl": volume,
                "line_count": line_count,
            }
        )

    if not offers.empty:
        off = offers.copy()
        off["valor_total_registrado"] = pd.to_numeric(off.get("valor_total_registrado", ""), errors="coerce").fillna(0)
        for _, row in off.iterrows():
            cnpj = only_digits(row.get("cnpj_emissor"))
            vol = float(row.get("valor_total_registrado") or 0)
            add_row(cnpj, "coordenador_lider", row.get("nome_lider"), vol, 1)
            add_row(cnpj, "administrador_oferta", row.get("administrador"), vol, 1)
            add_row(cnpj, "gestor_oferta", row.get("gestor"), vol, 1)
            add_row(cnpj, "custodiante_oferta", row.get("custodiante"), vol, 1)

    if not entities.empty:
        ent = entities.copy()
        ent["patrimonio_liquido_latest"] = pd.to_numeric(ent.get("patrimonio_liquido_latest", ""), errors="coerce").fillna(0)
        for _, row in ent.iterrows():
            cnpj = only_digits(row.get("cnpj_entity"))
            vol = float(row.get("patrimonio_liquido_latest") or 0)
            add_row(cnpj, "administrador_cvm", row.get("administrador"), vol, 1)
            add_row(cnpj, "gestor_cvm", row.get("gestor"), vol, 1)
            add_row(cnpj, "custodiante_cvm", row.get("custodiante"), vol, 1)

    raw = pd.DataFrame(rows)
    if raw.empty:
        return raw
    grouped = (
        raw.groupby(["setor_n1", "setor_n2", "role", "participant"], dropna=False)
        .agg(
            cnpjs_unicos=("cnpj", "nunique"),
            linhas=("line_count", "sum"),
            volume_brl=("volume_brl", "sum"),
        )
        .reset_index()
    )
    grouped["rank_no_setor_role"] = grouped.groupby(["setor_n1", "setor_n2", "role"])["volume_brl"].rank(method="first", ascending=False)
    return grouped.sort_values(["setor_n1", "setor_n2", "role", "rank_no_setor_role"])


def extract_cedentes_sacados(matrix: pd.DataFrame, *, output_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    cache_dir = output_dir / "pdf_text_cache"
    if matrix.empty or not cache_dir.exists():
        return pd.DataFrame()
    cnpj_context_re = re.compile(
        r"(?P<context>.{0,220}(?:CEDENTE|CEDENTES|ORIGINADOR|ORIGINADORES|SACADO|SACADOS|DEVEDOR|DEVEDORES|CONSULTORA|BANCO EMISSOR|EMISSOR DE CARTAO).{0,220})",
        flags=re.IGNORECASE | re.DOTALL,
    )
    cnpj_re = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
    matrix_lookup = matrix.set_index("cnpj").to_dict(orient="index")
    for cache_path in sorted(cache_dir.glob("*.txt")):
        cnpj = cache_path.name.split("_", 1)[0]
        meta = matrix_lookup.get(cnpj, {})
        text = cache_path.read_text(encoding="utf-8", errors="replace")
        for match in cnpj_context_re.finditer(text[:700000]):
            context = clean_text(match.group("context"), max_len=600)
            cnpjs = cnpj_re.findall(context)
            participant_type = "indeterminado"
            context_norm = normalize_text(context)
            if "CEDENTE" in context_norm or "ORIGINADOR" in context_norm:
                participant_type = "cedente_originador"
            if "SACADO" in context_norm or "DEVEDOR" in context_norm or "BANCO EMISSOR" in context_norm:
                participant_type = "sacado_devedor"
            if "CONSULTORA" in context_norm:
                participant_type = "consultora"
            candidate_name = guess_name_before_cnpj(context, cnpjs[0] if cnpjs else "")
            rows.append(
                {
                    "cnpj_fundo": cnpj,
                    "fund_name": meta.get("fund_name", ""),
                    "setor_n1": meta.get("setor_n1_final", ""),
                    "setor_n2": meta.get("setor_n2_final", ""),
                    "participant_type": participant_type,
                    "participant_cnpj_candidate": cnpjs[0] if cnpjs else "",
                    "participant_name_candidate": candidate_name,
                    "evidence_context": context,
                    "source_cache": str(cache_path),
                }
            )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.drop_duplicates(["cnpj_fundo", "participant_type", "participant_cnpj_candidate", "participant_name_candidate", "evidence_context"])
    return out


def guess_name_before_cnpj(context: str, cnpj: str) -> str:
    if not cnpj:
        return ""
    pos = context.find(cnpj)
    if pos < 0:
        return ""
    before = context[:pos]
    before = re.sub(r"inscrit[ao]s?\s+(?:no|sob o)\s+CNPJ.*$", "", before, flags=re.IGNORECASE)
    candidates = re.findall(r"([A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ0-9&.,' -]{8,140})$", before.upper())
    if candidates:
        return clean_text(candidates[-1], max_len=160).strip(" ,.-")
    return ""


def make_svg_bar_point(data: pd.DataFrame, *, label_col: str, bar_col: str, point_col: str, title: str, subtitle: str) -> str:
    if data.empty:
        return "<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='260'><text x='20' y='40'>Sem dados para o grafico.</text></svg>"
    rows = data.copy().head(36)
    rows[bar_col] = pd.to_numeric(rows[bar_col], errors="coerce").fillna(0)
    rows[point_col] = pd.to_numeric(rows[point_col], errors="coerce")
    width = 1280
    height = 620
    margin_left = 86
    margin_right = 96
    margin_top = 74
    margin_bottom = 178
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    max_bar = max(rows[bar_col].max(), 1)
    point_values = rows[point_col].dropna()
    max_point = max(point_values.max() if len(point_values) else 1, 1)
    min_point = min(point_values.min() if len(point_values) else 0, 0)
    step = plot_w / max(len(rows), 1)
    bar_w = max(8, min(24, step * 0.58))
    colors = ["#1f6f8b", "#c05a2b", "#466b35", "#7b5aa6", "#9b6a2f", "#2d7c73"]
    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>",
        "<rect width='100%' height='100%' fill='#f7f4ee'/>",
        f"<text x='{margin_left}' y='34' font-family='Arial' font-size='24' font-weight='700' fill='#222'>{html.escape(title)}</text>",
        f"<text x='{margin_left}' y='58' font-family='Arial' font-size='13' fill='#555'>{html.escape(subtitle)}</text>",
        f"<line x1='{margin_left}' y1='{margin_top + plot_h}' x2='{margin_left + plot_w}' y2='{margin_top + plot_h}' stroke='#333' stroke-width='1'/>",
        f"<line x1='{margin_left}' y1='{margin_top}' x2='{margin_left}' y2='{margin_top + plot_h}' stroke='#333' stroke-width='1'/>",
    ]
    for tick in range(5):
        y = margin_top + plot_h - (plot_h * tick / 4)
        value = max_bar * tick / 4
        parts.append(f"<line x1='{margin_left - 5}' y1='{y:.1f}' x2='{margin_left + plot_w}' y2='{y:.1f}' stroke='#ddd' stroke-width='1'/>")
        parts.append(f"<text x='{margin_left - 10}' y='{y + 4:.1f}' font-family='Arial' font-size='11' text-anchor='end' fill='#555'>{format_brl(value)}</text>")
    for tick in range(5):
        y = margin_top + plot_h - (plot_h * tick / 4)
        value = min_point + (max_point - min_point) * tick / 4
        parts.append(f"<text x='{margin_left + plot_w + 10}' y='{y + 4:.1f}' font-family='Arial' font-size='11' fill='#7a2e20'>{value:.1f}%</text>")
    for idx, row in rows.reset_index(drop=True).iterrows():
        x_center = margin_left + idx * step + step / 2
        bar_h = plot_h * float(row[bar_col]) / max_bar
        y_bar = margin_top + plot_h - bar_h
        color = colors[idx % len(colors)]
        label = clean_text(row[label_col], max_len=42)
        parts.append(f"<rect x='{x_center - bar_w / 2:.1f}' y='{y_bar:.1f}' width='{bar_w:.1f}' height='{bar_h:.1f}' rx='2' fill='{color}' opacity='0.88'/>")
        if not pd.isna(row[point_col]):
            point = float(row[point_col])
            y_point = margin_top + plot_h - ((point - min_point) / max(max_point - min_point, 0.001)) * plot_h
            parts.append(f"<circle cx='{x_center:.1f}' cy='{y_point:.1f}' r='5.5' fill='#d83f2a' stroke='white' stroke-width='1.5'/>")
            parts.append(f"<line x1='{x_center:.1f}' y1='{y_bar:.1f}' x2='{x_center:.1f}' y2='{y_point:.1f}' stroke='#d83f2a' stroke-width='1' stroke-dasharray='2,3' opacity='0.55'/>")
        parts.append(
            f"<text x='{x_center:.1f}' y='{margin_top + plot_h + 16}' font-family='Arial' font-size='10' text-anchor='end' fill='#333' transform='rotate(-55 {x_center:.1f},{margin_top + plot_h + 16})'>{html.escape(label)}</text>"
        )
    parts.extend(
        [
            f"<text x='{margin_left}' y='{height - 24}' font-family='Arial' font-size='12' fill='#333'>Barras: volume de emissao/linha. Pontos vermelhos: spread mediano CDI+ a.a. quando extraido.</text>",
            f"<text x='{margin_left + plot_w - 160}' y='34' font-family='Arial' font-size='12' fill='#7a2e20'>escala direita: CDI+ a.a.</text>",
            "</svg>",
        ]
    )
    return "\n".join(parts)


def build_charts(pricing_summary: pd.DataFrame, pricing: pd.DataFrame, output_dir: Path) -> dict[str, str]:
    chart_dir = output_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    chart_paths: dict[str, str] = {}

    if not pricing_summary.empty:
        df = pricing_summary.copy()
        df["label"] = df["setor_n2"].astype(str) + " / " + df["tipo_cota"].astype(str)
        df = df[df["volume_brl"].astype(float) > 0].sort_values("volume_brl", ascending=False).head(36)
        svg = make_svg_bar_point(
            df,
            label_col="label",
            bar_col="volume_brl",
            point_col="spread_cdi_mediano_aa",
            title="Volume de emissoes e spread CDI+ por subtipo/cota",
            subtitle="Base documental curada localmente; pontos aparecem apenas quando ha CDI+ extraido.",
        )
        path = chart_dir / "volume_spread_by_sector_quota.svg"
        path.write_text(svg, encoding="utf-8")
        chart_paths["volume_spread_by_sector_quota"] = str(path)

    if not pricing.empty:
        top = pricing[
            pricing["periodo_estudo"].isin(["2024FY", "2025FY", "2026YTD"])
            & pricing["volume_brl"].notna()
            & pricing["spread_cdi_aa"].notna()
        ].copy()
        if not top.empty:
            top["label"] = top["Fundo"].astype(str).str[:32] + " / " + top["Cota/Classe"].astype(str).str[:16]
            top = top.sort_values("volume_brl", ascending=False).head(36)
            svg = make_svg_bar_point(
                top,
                label_col="label",
                bar_col="volume_brl",
                point_col="spread_cdi_aa",
                title="Top tranches com CDI+ extraido",
                subtitle="Volume documental extraido de atos/suplementos/anuncios; nao deduplicado contra CVM quando documentos repetem evento.",
            )
            path = chart_dir / "top_tranches_cdi_spread.svg"
            path.write_text(svg, encoding="utf-8")
            chart_paths["top_tranches_cdi_spread"] = str(path)
    return chart_paths


def html_table(frame: pd.DataFrame, columns: list[str], *, max_rows: int = 12) -> str:
    if frame.empty:
        return "<p class='empty'>Sem dados.</p>"
    shown = frame[columns].head(max_rows).copy()
    rows = ["<table>", "<thead><tr>" + "".join(f"<th>{html.escape(col)}</th>" for col in columns) + "</tr></thead>", "<tbody>"]
    for _, row in shown.iterrows():
        cells = []
        for col in columns:
            value = row.get(col, "")
            if isinstance(value, float):
                if "volume" in col.lower():
                    value_text = format_brl(value)
                elif "share" in col.lower():
                    value_text = format_share(value)
                elif "spread" in col.lower() or "subordinacao" in col.lower():
                    value_text = format_pct(value)
                else:
                    value_text = f"{value:,.2f}"
            else:
                value_text = clean_text(value, max_len=120)
            cells.append(f"<td>{html.escape(value_text)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    rows.append("</tbody></table>")
    return "\n".join(rows)


def build_html_dashboard(
    *,
    output_dir: Path,
    chart_paths: dict[str, str],
    feature_prevalence: pd.DataFrame,
    subordination_summary: pd.DataFrame,
    pricing_summary: pd.DataFrame,
    participant_rankings: pd.DataFrame,
    summary: dict[str, object],
) -> Path:
    cards = [
        ("Ofertas CVM", f"{summary.get('offer_rows', 0):,}"),
        ("Emissores unicos", f"{summary.get('issuer_count', 0):,}"),
        ("CNPJs com docs locais", f"{summary.get('local_document_cnpj_count', 0):,}"),
        ("Regulamentos lidos", f"{summary.get('feature_matrix_count', 0):,}"),
        ("Tranches curadas", f"{summary.get('pricing_rows_in_period', 0):,}"),
        ("CDI+ extraido", f"{summary.get('pricing_cdi_rows', 0):,}"),
    ]
    chart_html = []
    for title, path in chart_paths.items():
        chart_html.append((Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""))
    css = """
    body { margin:0; font-family: Arial, sans-serif; background:#f7f4ee; color:#232323; }
    header { padding:28px 38px 18px; background:#222; color:#fff; }
    h1 { margin:0; font-size:28px; letter-spacing:0; }
    h2 { margin:28px 0 12px; font-size:20px; }
    .sub { color:#d7d1c6; margin-top:8px; font-size:14px; }
    main { padding:24px 38px 48px; }
    .cards { display:grid; grid-template-columns: repeat(6, minmax(130px, 1fr)); gap:10px; }
    .card { background:#fff; border:1px solid #ddd2c3; border-radius:6px; padding:12px; }
    .metric { font-size:22px; font-weight:700; margin-top:4px; }
    .label { font-size:12px; color:#6b6258; }
    .chart { margin-top:18px; background:#fff; border:1px solid #ddd2c3; border-radius:6px; overflow:auto; }
    table { width:100%; border-collapse:collapse; background:#fff; font-size:12px; }
    th { background:#e8dfd1; text-align:left; padding:8px; border-bottom:1px solid #c8bba8; }
    td { padding:7px 8px; border-bottom:1px solid #eadfd1; vertical-align:top; }
    .grid { display:grid; grid-template-columns: 1fr 1fr; gap:18px; align-items:start; }
    .note { color:#5f574e; font-size:13px; max-width:1120px; line-height:1.45; }
    .empty { color:#777; }
    @media (max-width: 980px) { .cards, .grid { grid-template-columns:1fr; } }
    """
    html_doc = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>Diagnostico FIDC 2024-2026YTD</title>",
        f"<style>{css}</style></head><body>",
        "<header>",
        "<h1>Diagnostico FIDC 2024FY, 2025FY e 2026YTD</h1>",
        f"<div class='sub'>Gerado em {html.escape(str(summary.get('run_timestamp_utc', '')))}. Base CVM + documentos locais/FNET quando disponiveis.</div>",
        "</header><main>",
        "<section class='cards'>",
    ]
    for label, metric in cards:
        html_doc.append(f"<div class='card'><div class='label'>{html.escape(label)}</div><div class='metric'>{html.escape(metric)}</div></div>")
    html_doc.append("</section>")
    html_doc.append("<p class='note'>Leitura documental automatizada por regras auditaveis. Os campos 'sim/nao' indicam presenca textual/criterio extraido, nao substituem QA juridico manual. A analise equal-weight evita que apenas FIDCs grandes determinem o que e 'comum'.</p>")
    for svg in chart_html:
        html_doc.append(f"<section class='chart'>{svg}</section>")
    html_doc.append("<div class='grid'>")
    html_doc.append("<section><h2>Prevalencia de praticas</h2>")
    prevalence_cols = ["setor_n1", "setor_n2", "fundos_com_regulamento", "subordination_minimum_share", "cash_or_liquidity_reserve_share", "revolving_period_share", "repurchase_or_indemnity_share"]
    html_doc.append(html_table(feature_prevalence, [col for col in prevalence_cols if col in feature_prevalence.columns], max_rows=14))
    html_doc.append("</section><section><h2>Subordinacao equal-weight</h2>")
    sub_cols = ["setor_n1", "setor_n2", "fundos_com_subordinacao", "subordinacao_mediana_pct_equal_weight", "subordinacao_p25_pct", "subordinacao_p75_pct", "valores_comuns"]
    html_doc.append(html_table(subordination_summary, [col for col in sub_cols if col in subordination_summary.columns], max_rows=14))
    html_doc.append("</section></div>")
    html_doc.append("<div class='grid'>")
    html_doc.append("<section><h2>Pricing por subtipo/cota</h2>")
    price_cols = ["setor_n1", "setor_n2", "tipo_cota", "linhas_tranche", "volume_brl", "spread_cdi_mediano_aa", "share_linhas_com_spread_cdi"]
    html_doc.append(html_table(pricing_summary, [col for col in price_cols if col in pricing_summary.columns], max_rows=14))
    html_doc.append("</section><section><h2>Participantes relevantes</h2>")
    part = participant_rankings[participant_rankings.get("rank_no_setor_role", pd.Series(dtype=float)).astype(float) <= 3].copy() if not participant_rankings.empty else participant_rankings
    part_cols = ["setor_n1", "setor_n2", "role", "participant", "cnpjs_unicos", "volume_brl"]
    html_doc.append(html_table(part, [col for col in part_cols if col in part.columns], max_rows=18))
    html_doc.append("</section></div>")
    html_doc.append("</main></body></html>")
    path = output_dir / "fidc_director_dashboard.html"
    path.write_text("\n".join(html_doc), encoding="utf-8")
    return path


def build_markdown_report(
    *,
    output_dir: Path,
    summary: dict[str, object],
    feature_prevalence: pd.DataFrame,
    subordination_summary: pd.DataFrame,
    pricing_summary: pd.DataFrame,
    participant_rankings: pd.DataFrame,
    download_status: pd.DataFrame,
) -> Path:
    lines = [
        "# Diagnostico profundo FIDC - 2024FY, 2025FY, 2026YTD",
        "",
        f"Gerado em: {summary.get('run_timestamp_utc')}.",
        "",
        "## Leitura executiva",
        "",
        f"- Universo CVM de ofertas analisado: {summary.get('offer_rows', 0):,} linhas, {summary.get('issuer_count', 0):,} emissores.",
        f"- Documentos locais/FNET cobertos: {summary.get('local_document_cnpj_count', 0):,} CNPJs com PDFs, {summary.get('regulation_pdf_count', 0):,} regulamentos, {summary.get('emission_pdf_count', 0):,} documentos de emissao.",
        f"- Regulamentos efetivamente lidos para matriz tem/nao tem: {summary.get('feature_matrix_count', 0):,}.",
        f"- Base de tranches/documentos de emissao no periodo: {summary.get('pricing_rows_in_period', 0):,}; linhas com CDI+ extraido: {summary.get('pricing_cdi_rows', 0):,}.",
        "",
        "## Como interpretar",
        "",
        "- Os agregados CVM medem volume de emissao/registro; a matriz regulatoria mede fundos equal-weight.",
        "- As praticas comuns devem ser lidas por subtipo e por frequencia de fundos, nao apenas por volume.",
        "- Campos de cedentes/sacados sao candidatos extraidos por contexto textual e exigem QA manual antes de uso em memorando juridico.",
        "",
        "## Principais proximos usos",
        "",
        "- Revisar manualmente a Onda 1 onde `feature_hits_share` for baixo ou documento faltar.",
        "- Validar spreads CDI+ em documentos repetidos para remover duplicatas de anuncio/ata/suplemento.",
        "- Converter os achados em slides: tamanho de mercado, pricing por cota, padroes de subordinação, ranking de prestadores e lacunas competitivas.",
    ]

    if not download_status.empty:
        ok = int(download_status["status"].astype(str).eq("ok").sum())
        partial = int(download_status["status"].astype(str).eq("parcial").sum())
        errors = int(download_status["status"].astype(str).str.startswith("erro").sum())
        lines.extend(
            [
                "",
                "## Download incremental FNET",
                "",
                f"- CNPJs processados para download: {len(download_status):,}.",
                f"- OK: {ok:,}; parcial: {partial:,}; erro: {errors:,}.",
            ]
        )

    lines.extend(["", "## Top praticas por setor", ""])
    lines.extend(markdown_table(feature_prevalence.head(12), ["setor_n1", "setor_n2", "fundos_com_regulamento", "subordination_minimum_share", "cash_or_liquidity_reserve_share", "revolving_period_share"]))
    lines.extend(["", "## Subordinacao por setor", ""])
    lines.extend(markdown_table(subordination_summary.head(12), ["setor_n1", "setor_n2", "fundos_com_subordinacao", "subordinacao_mediana_pct_equal_weight", "subordinacao_p25_pct", "subordinacao_p75_pct", "valores_comuns"]))
    lines.extend(["", "## Pricing por setor/cota", ""])
    lines.extend(markdown_table(pricing_summary.head(12), ["setor_n1", "setor_n2", "tipo_cota", "linhas_tranche", "volume_brl", "spread_cdi_mediano_aa", "share_linhas_com_spread_cdi"]))
    lines.extend(["", "## Participantes", ""])
    part = participant_rankings[participant_rankings["rank_no_setor_role"].astype(float) <= 2].head(18) if not participant_rankings.empty else participant_rankings
    lines.extend(markdown_table(part, ["setor_n1", "setor_n2", "role", "participant", "cnpjs_unicos", "volume_brl"]))
    lines.extend(
        [
            "",
            "## Arquivos principais",
            "",
            "- `fidc_regulatory_feature_matrix.csv`: matriz tem/nao tem por CNPJ e regulamento.",
            "- `fidc_feature_prevalence_by_sector.csv`: frequencia equal-weight das praticas.",
            "- `fidc_pricing_tranches.csv`: tranches/eventos com volume, tipo de cota e spread extraido.",
            "- `fidc_pricing_summary_by_sector_quota.csv`: resumo para grafico barra+ponto.",
            "- `fidc_market_participants_by_sector.csv`: rankings de prestadores por subtipo.",
            "- `fidc_cedentes_sacados_candidates.csv`: candidatos extraidos de contexto textual.",
            "- `fidc_director_dashboard.html`: dashboard visual local.",
        ]
    )
    path = output_dir / "director_deep_diagnostic_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    if frame.empty:
        return ["_Sem dados._"]
    cols = [col for col in columns if col in frame.columns]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for _, row in frame[cols].iterrows():
        values = []
        for col in cols:
            value = row.get(col, "")
            if isinstance(value, float):
                if "volume" in col.lower():
                    value = format_brl(value)
                elif "share" in col.lower():
                    value = format_share(value)
                elif "spread" in col.lower() or "subordinacao" in col.lower():
                    value = format_pct(value)
                else:
                    value = f"{value:.2f}"
            values.append(clean_text(value, max_len=160).replace("|", "\\|"))
        lines.append("| " + " | ".join(values) + " |")
    return lines


def build_review_queue_enriched(review: pd.DataFrame, feature_matrix: pd.DataFrame) -> pd.DataFrame:
    if review.empty:
        return pd.DataFrame()
    out = review.copy()
    out["cnpj_emissor"] = out["cnpj_emissor"].map(only_digits)
    if not feature_matrix.empty:
        keep = [
            "cnpj",
            "regulamento_count",
            "document_count_total",
            "latest_regulamento_file",
            "latest_regulamento_date",
            "pdf_extraction_status",
            "setor_n1_document",
            "setor_n2_document",
            "setor_n1_final",
            "setor_n2_final",
            "feature_hits_count",
            "feature_hits_share",
            "subordination_main_pct",
            "monocedente_or_multicedente",
            "concentrated_or_pulverized_debtors",
        ]
        out = out.merge(feature_matrix[keep], left_on="cnpj_emissor", right_on="cnpj", how="left")
    out["manual_review_status"] = "sem_documento_local"
    out.loc[out.get("regulamento_count", pd.Series(dtype=float)).fillna(0).astype(float) > 0, "manual_review_status"] = "regulamento_lido_heuristico"
    out.loc[out.get("feature_hits_share", pd.Series(dtype=float)).fillna(0).astype(float) >= 0.65, "manual_review_status"] = "triagem_documental_forte"
    return out


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    sector_rules = load_classification_module()
    offers = read_csv(args.issuance_dir / "fidc_public_offers_2024_2026ytd.csv")
    classified_offers = read_csv(args.classification_dir / "fidc_offer_sector_classification.csv")
    issuer_map = read_csv(args.classification_dir / "fidc_issuer_sector_classification.csv")
    entities = read_csv(args.issuance_dir / "fidc_cvm_entities_all.csv")
    review = read_csv(args.plan_dir / "manual_review_batches.csv")
    criteria = read_csv(CRITERIA_PATH)
    curated_emissions = read_csv(CURATED_EMISSIONS_PATH)

    if not issuer_map.empty:
        issuer_map["cnpj_emissor"] = issuer_map["cnpj_emissor"].map(only_digits)

    download_status = download_review_documents(
        review,
        output_dir=args.output_dir,
        limit=args.download_limit,
        offset=args.download_offset,
        max_docs_per_fund=args.max_docs_per_fund,
        timeout_seconds=args.timeout_seconds,
    )

    feature_matrix, inventory = build_feature_matrix(
        issuer_map=issuer_map,
        criteria=criteria,
        output_dir=args.output_dir,
        max_pages=args.max_pages,
        sector_rules=sector_rules,
    )
    feature_prevalence = build_feature_prevalence(feature_matrix)
    subordination_summary = build_subordination_summary(feature_matrix)
    pricing = build_pricing_base(curated_emissions, issuer_map)
    pricing_summary = build_pricing_summary(pricing)
    offer_volume_base = build_offer_volume_base(offers, classified_offers)
    participant_rankings = build_participant_rankings(offers, entities, issuer_map)
    cedentes_sacados = extract_cedentes_sacados(feature_matrix, output_dir=args.output_dir)
    review_enriched = build_review_queue_enriched(review, feature_matrix)

    write_csv(inventory, args.output_dir / "fidc_local_document_inventory.csv")
    write_csv(feature_matrix, args.output_dir / "fidc_regulatory_feature_matrix.csv")
    write_csv(feature_prevalence, args.output_dir / "fidc_feature_prevalence_by_sector.csv")
    write_csv(subordination_summary, args.output_dir / "fidc_subordination_distribution_by_sector.csv")
    write_csv(pricing, args.output_dir / "fidc_pricing_tranches.csv")
    write_csv(pricing_summary, args.output_dir / "fidc_pricing_summary_by_sector_quota.csv")
    write_csv(offer_volume_base, args.output_dir / "fidc_offer_volume_chart_base.csv")
    write_csv(participant_rankings, args.output_dir / "fidc_market_participants_by_sector.csv")
    write_csv(cedentes_sacados, args.output_dir / "fidc_cedentes_sacados_candidates.csv")
    write_csv(review_enriched, args.output_dir / "fidc_manual_review_queue_enriched.csv")

    pricing_in_period = pricing[pricing["periodo_estudo"].isin(["2024FY", "2025FY", "2026YTD"])] if not pricing.empty else pd.DataFrame()
    summary = {
        "run_timestamp_utc": now_iso(),
        "as_of_date": AS_OF_DATE.date().isoformat(),
        "offer_rows": int(len(offers)),
        "issuer_count": int(issuer_map["cnpj_emissor"].nunique()) if not issuer_map.empty else 0,
        "manual_review_rows": int(len(review)),
        "local_document_cnpj_count": int(inventory["cnpj"].nunique()) if not inventory.empty else 0,
        "local_pdf_count": int(len(inventory)),
        "regulation_pdf_count": int(inventory["document_classification"].eq("regulamento").sum()) if not inventory.empty else 0,
        "emission_pdf_count": int(inventory["document_classification"].eq("emissao").sum()) if not inventory.empty else 0,
        "feature_matrix_count": int(len(feature_matrix)),
        "feature_prevalence_sector_count": int(len(feature_prevalence)),
        "pricing_rows": int(len(pricing)),
        "pricing_rows_in_period": int(len(pricing_in_period)),
        "pricing_cdi_rows": int(pricing_in_period["spread_cdi_aa"].notna().sum()) if not pricing_in_period.empty else 0,
        "participant_ranking_rows": int(len(participant_rankings)),
        "cedentes_sacados_candidate_rows": int(len(cedentes_sacados)),
        "download_limit": int(args.download_limit),
        "download_offset": int(args.download_offset),
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    chart_paths = build_charts(pricing_summary, pricing, args.output_dir)
    dashboard_path = build_html_dashboard(
        output_dir=args.output_dir,
        chart_paths=chart_paths,
        feature_prevalence=feature_prevalence,
        subordination_summary=subordination_summary,
        pricing_summary=pricing_summary,
        participant_rankings=participant_rankings,
        summary=summary,
    )
    report_path = build_markdown_report(
        output_dir=args.output_dir,
        summary=summary,
        feature_prevalence=feature_prevalence,
        subordination_summary=subordination_summary,
        pricing_summary=pricing_summary,
        participant_rankings=participant_rankings,
        download_status=download_status,
    )
    print(json.dumps({"summary": summary, "dashboard": str(dashboard_path), "report": str(report_path)}, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Executa diagnostico diretor-level de FIDCs 2024-2026YTD.")
    parser.add_argument("--issuance-dir", type=Path, default=DEFAULT_ISSUANCE_DIR)
    parser.add_argument("--classification-dir", type=Path, default=DEFAULT_CLASSIFICATION_DIR)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--download-limit", type=int, default=0, help="Quantidade de CNPJs da fila manual a consultar no FNET antes da consolidacao.")
    parser.add_argument("--download-offset", type=int, default=0, help="Quantidade de CNPJs prioritarios a pular antes do download incremental.")
    parser.add_argument("--max-docs-per-fund", type=int, default=18)
    parser.add_argument("--timeout-seconds", type=int, default=35)
    parser.add_argument("--max-pages", type=int, default=120)
    return parser.parse_args()


if __name__ == "__main__":
    main()
