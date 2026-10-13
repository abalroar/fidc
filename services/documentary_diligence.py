"""Documentary criteria, evidence and coverage shared by the app and downloads.

The saved basket defines column identity and order. A missing answer is a typed
state, never a value; an unresolved applicability remains in the denominator.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from html import escape
from io import BytesIO, StringIO, TextIOWrapper
import csv
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlsplit
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd

from services.deep_dive_models import DeepDiveManifest
from services.document_curation_comparison import DocumentComparisonPage
from services.documentary_criteria_catalog import CRITERIA
from services.fund_name_display import short_fund_name
from services.presentation_text import public_document_text


SOURCE_ROOT = Path(__file__).resolve().parents[1]
CRITERION_THEMES = {key: theme for key, theme, _label, _expressions in CRITERIA}
CATALOG_THEMES = tuple(dict.fromkeys(CRITERION_THEMES.values()))
STATUS_LABELS = {
    "confirmed": "Confirmado",
    "document_not_obtained": "Documento não obtido",
    "access_blocked": "Documento inacessível",
    "parse_failed": "Texto não recuperado",
    "clause_not_found": "Cláusula não localizada",
    "referenced_document_missing": "Anexo referido não obtido",
    "version_conflict": "Conflito entre versões",
    "not_applicable": "Não se aplica",
    "extraction_pending": "Extração pendente",
}
THEME_LABELS = {
    "eligibility": "Recebíveis e elegibilidade",
    "protection": "Subordinação, gatilhos e proteção",
    "mechanics": "Alocação e mecânica contratual",
    "emissions": "Emissões e remuneração",
    "payments": "Amortização e pagamentos",
    "costs": "Custos e prestadores",
    "governance": "Governança e alterações",
    "monitoring": "Monitoramento",
}
_ABSENCE_VALUE = re.compile(
    r"^(?:n/?d|n/?a|nan|none|null|[-–—]|não (?:localizado|obtido|identificado|confirmado)|"
    r"sem (?:informação|documento|dados)|(?:precisa|exige|requer) (?:de )?document|"
    r"controles documentais|divergência documental)\b", re.I,
)


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _root(source_root: str | Path | None) -> Path:
    return Path(source_root) if source_root is not None else SOURCE_ROOT


def _fund_path(cnpj: str, source_root: str | Path | None = None) -> Path:
    return _root(source_root) / "data" / "documentary_diligence" / "funds" / f"{_digits(cnpj)}.json"


def has_documentary_diligence(portfolio: Any, source_root: str | Path | None = None) -> bool:
    """A partially published basket uses explicit pending states for the rest."""
    return any(_fund_path(fund.cnpj, source_root).exists() for fund in portfolio.funds)


def _history_summary(item: Mapping) -> dict:
    history = item.get("history") or []
    dates, identifiers, references = set(), set(), []
    for entry in history:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("reference_date"):
            dates.add(_text(entry["reference_date"]))
        sources = entry.get("sources") or ([entry.get("source")] if entry.get("source") else [entry])
        for source in sources:
            if not isinstance(source, Mapping):
                continue
            if source.get("reference_date"):
                dates.add(_text(source["reference_date"]))
            if source.get("document_id"):
                identifiers.add(_text(source["document_id"]))
            if len(references) < 8:
                reference = {key: source[key] for key in ("document_id", "title", "reference_date", "version", "page", "clause", "url", "sha256") if source.get(key) is not None}
                if reference and reference not in references:
                    references.append(reference)
    return {"count": item.get("history_count") or len(history), "dates": sorted(dates)[:16], "document_count": len(identifiers), "sources": references, "reference": item.get("history_ref")}


def load_documentary_fund(cnpj: str, *, source_root: str | Path | None = None, name: str = "", full_history: bool = False) -> dict:
    path = _fund_path(cnpj, source_root)
    fallback = {"schema_version": 2, "cnpj": _digits(cnpj), "name": name,
                "reviewed_at": "", "corpus_status": {"status": "document_not_obtained"},
                "criteria": [], "lookthrough": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback
    except (OSError, json.JSONDecodeError) as exc:
        fallback["corpus_status"] = {"status": "parse_failed", "reason": "Arquivo de curadoria não legível", "error": str(exc)}
        return fallback
    if not isinstance(payload, dict) or payload.get("schema_version") != 2 or _digits(payload.get("cnpj")) != _digits(cnpj):
        fallback["corpus_status"] = {"status": "parse_failed", "reason": "Identidade ou versão inválida no arquivo de curadoria"}
        return fallback
    criteria = payload.get("criteria")
    if not isinstance(criteria, list) or any(not isinstance(item, dict) or not item.get("criterion_id") for item in criteria):
        fallback["corpus_status"] = {"status": "parse_failed", "reason": "Critérios documentais inválidos"}
        return fallback
    ids = [_text(item["criterion_id"]) for item in criteria]
    if len(ids) != len(set(ids)):
        fallback["corpus_status"] = {"status": "parse_failed", "reason": "Critérios documentais duplicados"}
        return fallback
    if not full_history:
        for item in criteria:
            if item.get("history") or item.get("history_ref") or item.get("history_count"):
                item["history_summary"] = _history_summary(item)
                item.pop("history", None)
            if isinstance(item.get("manual_review"), (list, dict)):
                item["manual_review_summary"] = {"available": True, "reference": item.get("history_ref")}
                item.pop("manual_review", None)
    return payload


def _theme(item: Mapping) -> str:
    return CRITERION_THEMES.get(item.get("criterion_id"), _text(item.get("theme") or "mechanics").removeprefix("comparison_"))


def load_documentary_portfolio(portfolio: Any, source_root: str | Path | None = None, *, full_history: bool = False) -> list[dict]:
    funds = [load_documentary_fund(f.cnpj, source_root=source_root, name=f.display_name, full_history=full_history) for f in portfolio.funds]
    # If one file is unavailable, retain every criterion and its fund column.
    catalog = OrderedDict((item["criterion_id"], item) for fund in funds for item in fund["criteria"])
    for fund in funds:
        existing = {item["criterion_id"] for item in fund["criteria"]}
        corpus = fund.get("corpus_status") or {}
        corpus_status = corpus.get("status") if isinstance(corpus, dict) else str(corpus)
        for key, item in catalog.items():
            if key in existing:
                continue
            fund["criteria"].append({"criterion_id": key, "label": item.get("label", key), "theme": item.get("theme", "mechanics"),
                                     "applicability": "unresolved", "status": corpus_status if corpus_status in STATUS_LABELS and corpus_status != "confirmed" else "extraction_pending",
                                     "value": None, "sources": [], "risk_note": "Critério ainda sem leitura para este CNPJ"})
    return funds


def source_is_traceable(source: Mapping) -> bool:
    """Require a real document identity, date, and clause/page locator."""
    if not isinstance(source, Mapping):
        return False
    identifier = _text(source.get("document_id"))
    title = _text(source.get("title"))
    date = _text(source.get("reference_date"))
    locator = _text(source.get("page")) or _text(source.get("clause"))
    if not identifier or not title or not date or not locator or source.get("identity_verified") is False:
        return False
    if any(_ABSENCE_VALUE.search(value) for value in (identifier, title, date, locator)):
        return False
    if any(word in (identifier + " " + title).casefold() for word in ("access_status", "corpus acessível", "inventário de", "falha http", "consulta fundos.net sem")):
        return False
    date_match = re.search(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", date)
    if date_match is None:
        return False
    try:
        datetime.strptime(date_match.group(), "%Y-%m-%d" if "-" in date_match.group() else "%d/%m/%Y")
    except ValueError:
        return False
    if source.get("page") is not None and not source.get("clause"):
        return bool(re.search(r"[1-9]\d*", _text(source["page"])))
    return True


def criterion_has_answer(item: Mapping) -> bool:
    value = _text(item.get("value"))
    return bool(item.get("status") == "confirmed" and value and value.casefold() not in {"-", "—", "n/d", "n/a", "null", "none", "nan"} and not _ABSENCE_VALUE.search(value)
                and any(source_is_traceable(source) for source in item.get("sources", [])))


def criterion_is_documented_not_applicable(item: Mapping) -> bool:
    value = _text(item.get("value"))
    meaningful = bool(value and value.casefold() not in {"-", "—", "n/d", "n/a", "null", "none", "nan"} and not _ABSENCE_VALUE.search(value))
    return bool(item.get("applicability") == "not_applicable" and any(source_is_traceable(source) for source in item.get("sources", []))
                and (_text(item.get("reason")) or meaningful))


def documentary_coverage(fund: Mapping) -> dict:
    criteria = fund.get("criteria") or []
    not_applicable = sum(criterion_is_documented_not_applicable(item) for item in criteria)
    applicable = sum(item.get("applicability") == "applicable" for item in criteria)
    unresolved = len(criteria) - not_applicable - applicable
    answered = sum(item.get("applicability") == "applicable" and criterion_has_answer(item) for item in criteria)
    denominator = applicable + unresolved
    return {"cnpj": fund.get("cnpj"), "total": len(criteria), "applicable": applicable,
            "not_applicable": not_applicable, "unresolved": unresolved, "answered": answered,
            "denominator": denominator, "ratio": answered / denominator if denominator else None,
            "pending": denominator - answered}


def criterion_status(item: Mapping) -> str:
    if item.get("applicability") == "not_applicable":
        return STATUS_LABELS["not_applicable"] if criterion_is_documented_not_applicable(item) else "Aplicabilidade sem comprovação"
    status = item.get("status")
    if status == "confirmed" and not criterion_has_answer(item):
        return "Fonte ou extração incompleta"
    return STATUS_LABELS.get(status, STATUS_LABELS["extraction_pending"])


def criterion_display(item: Mapping) -> str:
    if criterion_has_answer(item):
        return _text(item.get("value"))
    if item.get("status") == "version_conflict" and _text(item.get("value")):
        return _text(item["value"]) + "; " + STATUS_LABELS["version_conflict"]
    return criterion_status(item)


def source_display(source: Mapping) -> str:
    pieces = [_text(source.get("title")), "ID " + _text(source.get("document_id")) if source.get("document_id") else "",
              _text(source.get("reference_date")), "versão " + _text(source.get("version")) if source.get("version") else "",
              "p. " + _text(source.get("page")) if source.get("page") is not None else "",
              _text(source.get("clause")), "XPath " + _text(source.get("xpath")) if source.get("xpath") else ""]
    if source.get("verification") == "visual_directed":
        pieces.append("Revisão visual da página; fonte PDF original")
    elif source.get("parse_method") == "apple_vision_ocr" or source.get("verification") == "ocr_primary_passage":
        pieces.append("Texto por OCR local; fonte PDF original")
    return " · ".join(piece for piece in pieces if piece)


def _safe_url(value: Any) -> str:
    value = _text(value)
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    return value if parsed.scheme in {"https", "http"} and parsed.hostname else ""


def _sources_html(sources: list[dict]) -> str:
    if not sources:
        return ""
    entries = []
    for source in sources:
        label = escape(source_display(source))
        url = _safe_url(source.get("url"))
        if url:
            label = f"<a href='{escape(url, quote=True)}' target='_blank' rel='noopener noreferrer'>{label}</a>"
        excerpt = _text(source.get("excerpt"))
        entries.append("<li>" + label + (f"<blockquote>{escape(excerpt)}</blockquote>" if excerpt else "") + "</li>")
    first = sources[0]
    locator = ("p. " + _text(first.get("page"))) if first.get("page") is not None else _text(first.get("clause") or first.get("xpath"))
    summary = " · ".join(filter(None, ["ID " + _text(first.get("document_id")) if first.get("document_id") else _text(first.get("title")), _text(first.get("reference_date")), locator]))
    if first.get("verification") == "visual_directed":
        summary += " · Revisão visual da página"
    elif first.get("parse_method") == "apple_vision_ocr" or first.get("verification") == "ocr_primary_passage":
        summary += " · OCR local"
    return f"<details class='documentary-source'><summary>{escape(summary or 'Fonte documental')}</summary><ul>{''.join(entries)}</ul></details>"


def _observation_display(observation: Mapping) -> str:
    display = _text(observation.get("observed_display") or observation.get("observed_value_display") or observation.get("value_display"))
    if not display and observation.get("observed_value") is not None:
        number = float(observation["observed_value"])
        display = f"{number:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
        display += "%" if observation.get("unit") == "percent" else "×" if observation.get("unit") == "ratio" else ""
    status = _text(observation.get("status_label") or observation.get("enquadramento") or observation.get("assessment"))
    if not status:
        status = {"compliant_snapshot": "Dentro do limite na posição mensal", "observed_below_limit": "Abaixo do limite na posição mensal", "observed_above_limit": "Acima do limite na posição mensal", "not_comparable": "Comparação não reproduzível", "ime_unavailable": "Dado IME indisponível", "version_not_applicable": "Versão fora da competência"}.get(observation.get("status"), "Confronto em apuração")
    competence = _text(observation.get("reference_competence") or observation.get("competence"))
    context = ""
    if observation.get("context_value") is not None:
        number = float(observation["context_value"])
        context = f"{number:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
        unit = observation.get("context_unit") or observation.get("unit")
        context += "%" if unit == "percent" else "×" if unit == "ratio" else ""
        context = "Referência agregada: " + context
    return " · ".join(filter(None, ["IME " + competence if competence else "IME", display, context, status]))


def _show_observation(item: Mapping, observation: Mapping | None) -> bool:
    return bool(observation and (item.get("rule") or observation.get("comparison_required")))


def _ime_source_html(source: Mapping) -> str:
    pieces = []
    url = _safe_url(source.get("url"))
    label = " · ".join(_text(source.get(key)) for key in ("cnpj", "competence", "document_id", "version") if source.get(key))
    pieces.append(f"<a href='{escape(url, quote=True)}' target='_blank' rel='noopener noreferrer'>{escape(label)}</a>" if url else escape(label))
    warnings = source.get("warnings") or []
    if isinstance(warnings, str):
        warnings = [warnings]
    if warnings:
        pieces.append("<ul>" + "".join(f"<li>{escape(public_document_text(warning))}</li>" for warning in warnings) + "</ul>")
    mapping = source.get("identity_mapping") or {}
    if source.get("identity_basis") == "verified_fund_class_inversion" and mapping:
        pair = mapping.get("allowed_header_pair") or {}
        description = f"Classe da cesta: {mapping.get('class_cnpj')}; fundo vinculado: {mapping.get('fund_cnpj')}. No cabeçalho do IME, NR_CNPJ_FUNDO={pair.get('NR_CNPJ_FUNDO')} e NR_CNPJ_CLASSE={pair.get('NR_CNPJ_CLASSE')}. Vínculo registrado desde {mapping.get('effective_from')}."
        pieces.append("<details><summary>Inversão fundo/classe comprovada</summary><p>" + escape(description) + "</p><p>" + escape(_text(mapping.get("reason"))) + "</p>" + _sources_html(mapping.get("sources") or []) + "</details>")
    field_paths = source.get("field_paths") or {}
    if field_paths:
        names = {"net_asset_value": "Patrimônio líquido", "cash": "Disponibilidades", "fidc_quotas": "Cotas de FIDC", "pdd": "Provisão de perdas"}
        pieces.append("<details><summary>Campos do IME</summary><ul>" + "".join(f"<li>{escape(names.get(key, key))}: {escape(_text(paths))}</li>" for key, paths in field_paths.items()) + "</ul></details>")
    elif source.get("fields"):
        pieces.append(escape(_text(source["fields"])))
    if source.get("path"):
        pieces.append(escape(public_document_text(source["path"])))
    return "<br>".join(filter(None, pieces))


def _cell_html(item: Mapping, observation: Mapping | None = None) -> str:
    answer = criterion_has_answer(item)
    content = f"<span class='documentary-{'value' if answer else 'status'}'>{escape(criterion_display(item))}</span>"
    if item.get("applicability") == "unresolved":
        content += "<div class='documentary-context'>Aplicabilidade em apuração</div>"
    content += _sources_html(item.get("sources") or [])
    rule = item.get("rule") or {}
    details = []
    for key, label in (("formula", "Fórmula"), ("unit", "Unidade"), ("denominator", "Base"), ("window", "Janela"), ("cure", "Cura"), ("cure_period", "Cura"), ("event", "Evento"), ("priority", "Prioridade")):
        if rule.get(key) is not None and _text(rule.get(key)):
            details.append(f"{escape(label)}: {escape(_text(rule[key]))}")
    if item.get("risk_note"):
        details.append(escape(_text(item["risk_note"])))
    if item.get("reason"):
        details.append(escape(_text(item["reason"])))
    if item.get("precedence"):
        details.append("Versão e prevalência: " + escape(_text(item["precedence"])))
    history = item.get("history_summary") or (_history_summary(item) if item.get("history") or item.get("history_ref") else {})
    if history:
        dates = ", ".join(history.get("dates") or [])
        details.append(f"Histórico: {escape(_text(history.get('count')))} registros; {escape(_text(history.get('document_count')))} documentos identificados nas prévias. Datas: {escape(dates)}. Evidência integral no download.")
    if details:
        content += "<details class='documentary-rule'><summary>Condição e mecânica</summary>" + "<br>".join(details) + "</details>"
    if history.get("sources"):
        content += "<details><summary>Referências do histórico</summary>" + _sources_html(history["sources"]) + "</details>"
    if _show_observation(item, observation):
        content += f"<div class='documentary-observation'>{escape(_observation_display(observation))}</div>"
        note = _text(observation.get("risk_note") or observation.get("reason") or observation.get("note"))
        context_formula = _text(observation.get("context_formula"))
        ime_source = observation.get("source") or {}
        if note or ime_source or context_formula:
            formula_note = f"<br>Fórmula da referência agregada: {escape(context_formula)}" if context_formula else ""
            content += f"<details><summary>Base da comparação</summary>{escape(note)}{formula_note}<br>{_ime_source_html(ime_source)}</details>"
    return content


@dataclass(frozen=True)
class DocumentaryTheme:
    key: str
    label: str
    criteria: tuple[tuple[str, str], ...]


def documentary_themes(funds: list[dict]) -> tuple[DocumentaryTheme, ...]:
    grouped: dict[str, OrderedDict] = OrderedDict()
    for fund in funds:
        for item in fund.get("criteria", []):
            grouped.setdefault(_theme(item), OrderedDict()).setdefault(item["criterion_id"], _text(item.get("label") or item["criterion_id"]))
    known = (*CATALOG_THEMES, *THEME_LABELS)
    keys = [key for key in dict.fromkeys(known) if key in grouped] + [key for key in grouped if key not in known]
    return tuple(DocumentaryTheme(key, THEME_LABELS.get(key, key), tuple(grouped[key].items())) for key in keys)


def _index(fund: Mapping) -> dict:
    return {item["criterion_id"]: item for item in fund.get("criteria", [])}


def _short_name(fund: Mapping) -> str:
    name = _text(fund.get("short_name") or fund.get("name") or fund.get("cnpj"))
    return short_fund_name(name, max_length=max(28, len(name))) or name


def documentary_common_criteria(funds: list[dict]) -> dict[str, list[dict]]:
    if len(funds) < 2:
        return {}
    indices = [_index(fund) for fund in funds]
    common = {}
    for key in indices[0]:
        items = [idx.get(key, {}) for idx in indices]
        meanings = {json.dumps({"value": item.get("value"), "rule": item.get("rule") or {}, "risk_note": item.get("risk_note") or ""}, ensure_ascii=False, sort_keys=True) for item in items}
        if all(item.get("applicability") == "applicable" and criterion_has_answer(item) for item in items) and len(meanings) == 1:
            common[key] = items
    return common


def documentary_table_html(theme: DocumentaryTheme, funds: list[dict], observations: Mapping | None = None) -> str:
    indices = [_index(fund) for fund in funds]
    observations = observations or {}
    common = documentary_common_criteria(funds)
    rows = []
    for key, label in theme.criteria:
        if key in common:
            continue
        items = [idx.get(key, {"criterion_id": key, "status": "extraction_pending", "applicability": "unresolved"}) for idx in indices]
        if not any(criterion_has_answer(item) or item.get("status") == "version_conflict" for item in items):
            continue
        cells = [_cell_html(item, observations.get(_text(fund.get("cnpj")), {}).get(key)) for fund, item in zip(funds, items)]
        rows.append(f"<tr><th scope='row'>{escape(label)}</th>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    if not rows:
        return ""
    headers = []
    for fund in funds:
        headers.append(f"<th scope='col'>{escape(_short_name(fund))}<details><summary>Identificação</summary>{escape(_text(fund.get('name')))}<br>CNPJ {escape(_text(fund.get('cnpj')))}</details></th>")
    widths = "<colgroup><col style='width:220px'>" + "<col style='width:280px'>" * len(funds) + "</colgroup>"
    return "<section class='documentary-diligence'>" + f"<h4>{escape(theme.label)}</h4><div class='documentary-scroll' tabindex='0' role='region' aria-label='{escape(theme.label)}: comparação por fundo'>" + f"<table style='width:{220 + len(funds) * 280}px'>{widths}<thead><tr><th scope='col'>Critério</th>" + "".join(headers) + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></section>"


def documentary_records(funds: list[dict], observations: Mapping | None = None) -> list[dict]:
    observations = observations or {}
    records = []
    for fund in funds:
        for item in fund.get("criteria", []):
            observed = observations.get(_text(fund.get("cnpj")), {}).get(item["criterion_id"], {})
            records.append({"CNPJ": fund.get("cnpj"), "Fundo": fund.get("name"), "Camada": "Próprio", "FIC de origem": "", "Vínculo documental": "", "Critério": item.get("label"), "Chave": item["criterion_id"],
                            "Tema": _theme(item), "Aplicabilidade": item.get("applicability"), "Status": criterion_status(item),
                            "Valor": _text(item.get("value")), "Cobertura válida": criterion_has_answer(item) and item.get("applicability") == "applicable",
                            "Fontes": json.dumps(public_document_payload(item.get("sources", [])), ensure_ascii=False), "Mecânica": json.dumps(public_document_payload(item.get("rule", {})), ensure_ascii=False),
                            "Observação": public_document_text("; ".join(filter(None, [_text(item.get("reason")), _text(item.get("risk_note"))]))), "IME": _observation_display(observed) if _show_observation(item, observed) else "", "Base IME": json.dumps(public_document_payload(observed), ensure_ascii=False) if _show_observation(item, observed) else "", "Leitura": fund.get("reviewed_at")})
        for report in _quarterly_reports(fund):
            for item in report.get("records") or []:
                sources = _quarterly_sources(item, report)
                records.append({"CNPJ": fund.get("cnpj"), "Fundo": fund.get("name"), "Camada": "Declaração trimestral", "FIC de origem": "", "Vínculo documental": "", "Critério": item.get("label"), "Chave": "quarterly::" + _text(item.get("criterion_id")),
                                "Tema": "Declarações trimestrais", "Aplicabilidade": "Observação declarada", "Status": _quarterly_status(item, report), "Valor": _text(item.get("value")) if _quarterly_verified(item, report) else "", "Cobertura válida": False,
                                "Fontes": json.dumps(public_document_payload(sources), ensure_ascii=False), "Mecânica": "{}", "Observação": _quarterly_note(item, report), "IME": "", "Base IME": "", "Leitura": fund.get("reviewed_at")})
    return records


def _quarterly_reports(fund: Mapping) -> list[dict]:
    reports = fund.get("quarterly_observations") or []
    if isinstance(reports, Mapping):
        return list(reports.get("reports") or []) if "reports" in reports else [dict(reports)]
    return [report for report in reports if isinstance(report, Mapping)]


def _quarterly_source(item: Mapping, report: Mapping) -> dict:
    return {"title": "Informe Trimestral", **(report.get("source") or {}), **(item.get("source") or {})}


def _quarterly_sources(item: Mapping, report: Mapping) -> list[dict]:
    sources = [_quarterly_source(item, report)]
    markers = {tuple(_text(source.get(key)) for key in ("document_id", "page", "clause", "xpath")) for source in sources}
    for source in item.get("sources") or []:
        marker = tuple(_text(source.get(key)) for key in ("document_id", "page", "clause", "xpath"))
        if marker not in markers:
            sources.append(source)
            markers.add(marker)
    return sources


def _quarterly_verified(item: Mapping, report: Mapping) -> bool:
    source = _quarterly_source(item, report)
    return bool(report.get("status") in {"parsed", "reported"} and item.get("status") in {"reported", "reported_raw", "declared", "confirmed", "parsed", "documentary_conflict"}
                and source.get("identity_verified") is True and source.get("document_id") and source.get("reference_date")
                and (source.get("page") or source.get("clause") or source.get("xpath")))


def _quarterly_status(item: Mapping, report: Mapping) -> str:
    if _quarterly_verified(item, report) and item.get("status") == "documentary_conflict":
        return "Declaração em conflito com o regulamento"
    if _quarterly_verified(item, report):
        return "Declaração do informe trimestral"
    if item.get("status") == "extraction_pending":
        return "Resposta trimestral em apuração"
    state = report.get("status") or "unavailable"
    return {"identity_mapping_pending": "Identidade do informe em apuração", "identity_missing": "Identidade do informe não comprovada", "competence_conflict": "Competência do informe em conflito", "unavailable": "Informe trimestral não disponível", "parse_failed": "Informe trimestral sem leitura", "no_mapped_observations": "Informe lido; respostas sem extração"}.get(state, "Declaração trimestral sem verificação")


def _quarterly_note(item: Mapping, report: Mapping) -> str:
    period = _text(report.get("quarter") or report.get("competence") or report.get("reference_date"))
    return public_document_text(" · ".join(filter(None, [period, "Resposta declarada no informe; a cláusula permanece no documento normativo", _text(item.get("reason")), _text(item.get("risk_note")), _text(report.get("reason"))])))


def quarterly_documentary_table_html(funds: list[dict]) -> str:
    reports = {fund["cnpj"]: _quarterly_reports(fund) for fund in funds}
    criteria = OrderedDict()
    for fund_reports in reports.values():
        for report in fund_reports:
            for item in report.get("records") or []:
                criteria.setdefault(_text(item.get("criterion_id")), _text(item.get("label") or item.get("criterion_id")))
    if not criteria:
        return ""
    rows = []
    for key, label in criteria.items():
        cells = []
        for fund in funds:
            values = []
            for report in reports[fund["cnpj"]]:
                for item in report.get("records") or []:
                    if _text(item.get("criterion_id")) != key:
                        continue
                    text = _text(item.get("value")) if _quarterly_verified(item, report) else _quarterly_status(item, report)
                    state = _quarterly_status(item, report)
                    values.append(f"<p>{escape(text)}</p><small>{escape(state)} · {escape(_quarterly_note(item, report))}</small>" + _sources_html(_quarterly_sources(item, report)))
            if not values:
                state = reports[fund["cnpj"]][0] if reports[fund["cnpj"]] else {"status": "unavailable"}
                missing = "Campo não extraído do informe" if state.get("status") in {"parsed", "reported"} else _quarterly_status({}, state)
                values = [escape(missing) + (f"<details><summary>Motivo</summary>{escape(_text(state.get('reason')))}</details>" if state.get("reason") else "")]
            cells.append("<td>" + "".join(values) + "</td>")
        rows.append(f"<tr><th scope='row'>{escape(label)}</th>" + "".join(cells) + "</tr>")
    headers = "".join(f"<th scope='col'>{escape(_short_name(fund))}<details><summary>Identificação</summary>{escape(_text(fund.get('name')))}<br>CNPJ {escape(fund['cnpj'])}</details></th>" for fund in funds)
    widths = "<colgroup><col style='width:220px'>" + "<col style='width:280px'>" * len(funds) + "</colgroup>"
    return "<section class='documentary-diligence'><div class='documentary-scroll' tabindex='0' role='region' aria-label='Declarações trimestrais por fundo'>" + f"<table style='width:{220 + len(funds) * 280}px'>{widths}<thead><tr><th scope='col'>Declaração</th>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>"


def public_document_payload(value: Any) -> Any:
    """Preserve URLs, hashes and citations without publishing personal paths."""
    if isinstance(value, Mapping):
        return {key: public_document_payload(item) for key, item in value.items() if key not in {"local_path", "text_path", "local_sources", "inventory_sources"}}
    if isinstance(value, (list, tuple)):
        return [public_document_payload(item) for item in value]
    return public_document_text(value) if isinstance(value, str) else value


def load_documentary_corpus(cnpj: str, source_root: str | Path | None = None) -> dict:
    path = _root(source_root) / "data/documentary_diligence/corpus" / f"{_digits(cnpj)}.json"
    if not path.exists():
        path = _root(source_root) / "data/documentary_diligence/audit_corpus" / f"{_digits(cnpj)}.json"
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return result if isinstance(result, dict) and _digits(result.get("cnpj")) == _digits(cnpj) else {}


def documentary_corpus_html(fund: Mapping, corpus: Mapping) -> str:
    state_labels = {"local_available": "Documento local disponível", "downloaded": "Obtido nesta rodada", "inventory_only": "Inventariado, documento não obtido", "excluded_ime_pipeline": "IME tratado na base de carteira", "complete": "Texto recuperado", "unreadable_text": "Texto ilegível por codificação do PDF", "cached_version_conflict": "Versão do arquivo local diverge do catálogo", "catalog_version_conflict": "Catálogo com versões conflitantes", "not_downloaded": "Documento não obtido", "not_applicable_ime_pipeline": "IME tratado na base de carteira", "access_blocked": "Acesso bloqueado", "parse_failed": "Texto não recuperado", "error": "Falha de acesso", "failed": "Falha de acesso", "indexed": "Acervo local consultado", "success": "Consulta concluída", "not_searched": "Busca ainda não executada", "download_limit": "Limite de recursos da rodada"}
    parts = [f"<details class='documentary-acquisition'><summary>{escape(_short_name(fund))} · CNPJ {escape(_text(fund.get('cnpj')))}</summary>"]
    docs = corpus.get("documents") or []
    if docs:
        parts.append("<ul>")
        for doc in docs:
            source = {"document_id": doc.get("id"), "title": doc.get("title"), "reference_date": doc.get("reference_date"), "version": doc.get("version")}
            label = source_display(source)
            url = _safe_url(doc.get("url"))
            label = f"<a href='{escape(url, quote=True)}' target='_blank' rel='noopener noreferrer'>{escape(label)}</a>" if url else escape(label)
            statuses = [state_labels.get(doc.get(key), _text(doc.get(key)).replace("_", " ")) for key in ("download_status", "parse_status") if doc.get(key)]
            if doc.get("parse_method") == "apple_vision_ocr":
                statuses.append("Texto por OCR local; fonte PDF original")
                if doc.get("ocr_excluded_pages"):
                    statuses.append("Páginas fora do limiar de confiança: " + _text(doc["ocr_excluded_pages"]))
            reason = public_document_text(doc.get("error"))
            parts.append(f"<li>{label}<br>{escape('; '.join(dict.fromkeys(statuses)))}" + (f" · {escape(reason)}" if reason else "") + "</li>")
        parts.append("</ul>")
    corpus_state = fund.get("corpus_status") if isinstance(fund.get("corpus_status"), Mapping) else {}
    searches = corpus.get("searches") or corpus_state.get("searches") or []
    parts.append("<p>Registro de buscas</p><ul>")
    for search in searches:
        label = public_document_text(search.get("url") or search.get("source"))
        url = _safe_url(search.get("url"))
        label = f"<a href='{escape(url, quote=True)}' target='_blank' rel='noopener noreferrer'>{escape(label)}</a>" if url else escape(label)
        state = state_labels.get(search.get("status"), _text(search.get("status")).replace("_", " "))
        parts.append(f"<li>{label} · {escape(_text(search.get('queried_at')))} · {escape(state)}" + (" · " + escape(public_document_text(search["error"])) if search.get("error") else "") + "</li>")
    for pending in corpus.get("pending_sources", []):
        name = {"administrator_and_manager": "Administrador e gestor", "rating_agencies": "Agências de rating", "anbima_and_offer_documents": "ANBIMA e documentos de ofertas", "lastro_verifier": "Verificação de lastro"}.get(pending.get("source"), _text(pending.get("source")))
        state = state_labels.get(pending.get("status"), _text(pending.get("status")).replace("_", " "))
        parts.append(f"<li>{escape(name)} · {escape(state)}</li>")
    parts.append("</ul></details>")
    return "".join(parts)


def load_documentary_lookthrough(funds: list[dict], source_root: str | Path | None = None) -> list[dict]:
    result = []
    for fund in funds:
        seen = set()
        for relation in fund.get("lookthrough", []):
            cnpj = _digits(relation.get("cnpj"))
            if len(cnpj) != 14 or cnpj == fund.get("cnpj") or cnpj in seen:
                continue
            seen.add(cnpj)
            underlying = load_documentary_fund(cnpj, source_root=source_root, name=relation.get("label") or cnpj)
            result.append({"parent_cnpj": fund["cnpj"], "parent_name": _short_name(fund), "relation": relation, "fund": underlying})
    return result


def documentary_csv_bytes(funds: list[dict], observations: Mapping | None = None, lookthrough: list[dict] | None = None) -> bytes:
    records = documentary_records(funds, observations)
    for detail in (load_documentary_lookthrough(funds) if lookthrough is None else lookthrough):
        for record in documentary_records([detail["fund"]], observations):
            relation = public_document_payload(detail["relation"])
            relation["sources"] = [{key: source.get(key) for key in ("document_id", "title", "url", "reference_date", "page", "clause") if source.get(key) is not None} for source in relation.get("sources", [])]
            record.update({"Camada": "Vínculo de investimento", "FIC de origem": detail["parent_cnpj"], "Vínculo documental": json.dumps(relation, ensure_ascii=False)})
            records.append(record)
    stream = StringIO()
    if records:
        writer = csv.DictWriter(stream, fieldnames=list(records[0])); writer.writeheader(); writer.writerows(records)
    return stream.getvalue().encode("utf-8-sig")


def documentary_evidence_zip_bytes(portfolio: Any, cnpjs: list[str], *, reference_competence: str | None = None,
                                    observations: Mapping | None = None, relationships: list[dict] | None = None,
                                    source_root: str | Path | None = None) -> bytes:
    """Serialize one fund and history sidecar at a time, on download request."""
    output = BytesIO()
    root = _root(source_root)
    def write_json(archive, name, value):
        with archive.open(name, "w") as stream:
            with TextIOWrapper(stream, encoding="utf-8") as text:
                json.dump(public_document_payload(value), text, ensure_ascii=False, indent=2)
                text.write("\n")
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        write_json(archive, "portfolio.json", {"schema_version": 2, "portfolio_id": portfolio.id, "portfolio_name": portfolio.name,
                                             "reference_competence": reference_competence, "cnpjs": list(dict.fromkeys(cnpjs)),
                                             "observations": observations or {}, "relationships": relationships or []})
        for cnpj in dict.fromkeys(cnpjs):
            fund = load_documentary_fund(cnpj, source_root=root, full_history=True)
            write_json(archive, f"funds/{cnpj}.json", fund)
            write_json(archive, f"corpora/{cnpj}.json", load_documentary_corpus(cnpj, root))
            history = root / "data/documentary_diligence/history" / f"{_digits(cnpj)}.json"
            if history.is_file():
                with history.open(encoding="utf-8") as stream:
                    write_json(archive, f"history/{cnpj}.json", json.load(stream))
    return output.getvalue()


def documentary_manifest(portfolio: Any, funds: list[dict], reference_competence: str | None = None) -> DeepDiveManifest:
    from services.portfolio_store import portfolio_basket_signature
    dates = [_text(fund.get("reviewed_at")) for fund in funds if fund.get("reviewed_at")]
    return DeepDiveManifest.from_dict({"schema_version": 1, "deep_dive_id": f"documentary_diligence_{portfolio.id}", "title": "Documentos · " + portfolio.name,
                                      "generated_at": max(dates) if dates else "", "portfolio_id": portfolio.id, "portfolio_signature": portfolio_basket_signature(portfolio.funds),
                                      "source": "Documentos identificados por célula; competência IME " + _text(reference_competence), "funds": funds,
                                      "audit": {"warnings": ["Aplicabilidade em apuração permanece no denominador da cobertura. Ausências tipificadas constam na tabela de pendências."]}}, package_dir=SOURCE_ROOT)


def build_documentary_comparison_pages(portfolio: Any, funds: list[dict] | None = None, observations: Mapping | None = None, *, include_lookthrough: bool = True) -> list[DocumentComparisonPage]:
    funds = load_documentary_portfolio(portfolio) if funds is None else funds
    observations = observations or {}
    labels = [f"{_short_name(fund)} · {_text(fund.get('cnpj'))}" for fund in funds]
    indices = [_index(fund) for fund in funds]
    pages = []
    for theme in documentary_themes(funds):
        rows, sources = [], []
        for key, label in theme.criteria:
            row = {"Critério": label}
            for name, fund, idx in zip(labels, funds, indices):
                item = idx.get(key, {"status": "extraction_pending"})
                row[name] = criterion_display(item)
                observed = observations.get(_text(fund.get("cnpj")), {}).get(key)
                if _show_observation(item, observed):
                    row[name] += "\n" + _observation_display(observed)
                    sources.append(f"CNPJ {fund['cnpj']} · {label} · Base da comparação IME: {json.dumps(public_document_payload(observed), ensure_ascii=False)}")
                for source in item.get("sources", []):
                    sources.append(f"CNPJ {fund['cnpj']} · {label} · {source_display(source)} · {_text(source.get('url'))}")
                    if source.get("excerpt"):
                        sources.append(f"CNPJ {fund['cnpj']} · {label} · Excerto da fonte:\n{source['excerpt']}")
                if item.get("risk_note"):
                    sources.append(f"CNPJ {fund['cnpj']} · {label} · Condição: {item['risk_note']}")
                for field, description in (("rule", "Mecânica"), ("reason", "Motivo"), ("precedence", "Versão e prevalência"), ("history_summary", "Resumo do histórico")):
                    if item.get(field):
                        content = json.dumps(item[field], ensure_ascii=False) if isinstance(item[field], (dict, list)) else str(item[field])
                        sources.append(f"CNPJ {fund['cnpj']} · {label} · {description}: {content}")
            rows.append(row)
        if rows:
            pages.append(DocumentComparisonPage(theme.label, pd.DataFrame(rows), sources=tuple(sources), preserve_typed_statuses=True))
    quarterly_keys = OrderedDict()
    for fund in funds:
        for report in _quarterly_reports(fund):
            for item in report.get("records") or []:
                quarterly_keys.setdefault(_text(item.get("criterion_id")), _text(item.get("label") or item.get("criterion_id")))
    if quarterly_keys:
        quarterly_rows, quarterly_sources = [], []
        for key, label in quarterly_keys.items():
            row = {"Critério": label}
            for name, fund in zip(labels, funds):
                values = []
                for report in _quarterly_reports(fund):
                    for item in report.get("records") or []:
                        if _text(item.get("criterion_id")) != key:
                            continue
                        values.append((_text(item.get("value")) + "\n" + _quarterly_status(item, report) if _quarterly_verified(item, report) else _quarterly_status(item, report)) + "\n" + _quarterly_note(item, report))
                        for source in _quarterly_sources(item, report):
                            quarterly_sources.append(f"CNPJ {fund['cnpj']} · {label} · {source_display(source)} · {_text(source.get('url'))} · {_text(source.get('excerpt'))}")
                row[name] = "\n\n".join(values) or "Declaração trimestral não extraída"
            quarterly_rows.append(row)
        pages.append(DocumentComparisonPage("Declarações trimestrais", pd.DataFrame(quarterly_rows), sources=tuple(quarterly_sources), preserve_typed_statuses=True))
    if include_lookthrough:
        for detail in load_documentary_lookthrough(funds):
            underlying = detail["fund"]
            for page in build_documentary_comparison_pages(portfolio, [underlying], observations, include_lookthrough=False):
                relation_sources = tuple(f"Vínculo: {detail['parent_name']} · CNPJ {detail['parent_cnpj']} → CNPJ {underlying['cnpj']} · {source_display(source)}" for source in detail["relation"].get("sources", []))
                relation_sources += ("Condição do vínculo: " + json.dumps(public_document_payload({key: value for key, value in detail["relation"].items() if key != "sources"}), ensure_ascii=False),)
                pages.append(DocumentComparisonPage(f"{detail['parent_name']} · vínculo CNPJ {underlying['cnpj']} · {page.title}", page.frame, sources=(*relation_sources, *page.sources), preserve_typed_statuses=True))
    return pages


_TABLE_CSS = """<style>
.documentary-diligence{margin:1rem 0;color:#202020}.documentary-diligence h4{font-size:1.05rem;font-weight:500}
.documentary-scroll{overflow:auto;max-height:72vh;border:1px solid #e4e4e4;border-radius:4px}
.documentary-scroll:focus-visible,.documentary-diligence summary:focus-visible{outline:2px solid #ff6200;outline-offset:2px}
.documentary-diligence table{table-layout:fixed;border-collapse:separate;border-spacing:0;min-width:100%;font-size:.86rem;line-height:1.4}
.documentary-diligence th,.documentary-diligence td{width:280px;box-sizing:border-box;padding:.6rem .7rem;vertical-align:top;border-bottom:1px solid #e4e4e4;overflow-wrap:anywhere}
.documentary-diligence thead th{position:sticky;top:0;background:#f7f7f7;z-index:2;text-align:left;font-weight:500}
.documentary-diligence th:first-child{position:sticky;left:0;width:220px;min-width:220px;max-width:220px;background:#fff;z-index:1;text-align:left;font-weight:500}
.documentary-diligence thead th:first-child{background:#f7f7f7;z-index:3}
.documentary-diligence summary{cursor:pointer;min-height:32px;padding:.3rem 0;color:#6f5135;font-size:.78rem}
.documentary-acquisition summary{cursor:pointer;min-height:44px;padding:.6rem 0}.documentary-acquisition li{margin:.45rem 0;font-size:.85rem}
.documentary-diligence details{margin-top:.2rem}.documentary-diligence ul{padding-left:1rem}
.documentary-diligence blockquote{margin:.5rem 0;font-size:.8rem;color:#4b5563}
.documentary-status,.documentary-context{color:#68717e}.documentary-context{font-size:.76rem}
.documentary-observation{border-top:1px solid #ececec;margin-top:.5rem;padding-top:.5rem;font-variant-numeric:tabular-nums}
</style>"""


def render_documentary_diligence(portfolio: Any, reference_competence: str | None = None, dashboards: Mapping | None = None) -> None:
    import streamlit as st
    funds = load_documentary_portfolio(portfolio)
    from services.documentary_ime_comparison import build_documentary_observations, resolve_documentary_reference, normalize_documentary_competence
    resolved = resolve_documentary_reference(portfolio, dashboards=dashboards)
    reference = resolved.get("competence")
    requested = normalize_documentary_competence(reference_competence)
    warnings = list(resolved.get("warnings") or [])
    if requested and requested != reference:
        if requested in resolved.get("common_competences", []):
            reference = requested
        else:
            reference = None
            warnings.append("A posição selecionada não é comum a todos os fundos elegíveis; confronto suspenso nesta seleção.")
    observations = {}
    for fund in funds:
        records = build_documentary_observations(fund, competence=reference, dashboard=(dashboards or {}).get(fund["cnpj"]))
        observations[fund["cnpj"]] = {item["criterion_id"]: item for item in records}
    lookthrough = load_documentary_lookthrough(funds)
    for detail in lookthrough:
        underlying = detail["fund"]
        records = build_documentary_observations(underlying, competence=reference, dashboard=(dashboards or {}).get(underlying["cnpj"]))
        observations[underlying["cnpj"]] = {item["criterion_id"]: item for item in records}
    st.markdown("### Documentos")
    st.caption("Competência de confronto: " + (str(reference) if reference else "posição comum ainda sem dados") + ". As fontes e condições ficam junto de cada critério.")
    for warning in warnings:
        st.caption(warning)
    # Monetary clauses contain R$; HTML avoids treating pairs of dollar signs
    # inside evidence as Markdown/LaTeX delimiters.
    st.html(_TABLE_CSS)
    common = documentary_common_criteria(funds)
    if common:
        with st.expander("Regras comuns comprovadas", expanded=False):
            for key, items in common.items():
                st.html(f"<p><strong>{escape(_text(items[0].get('label') or key))}:</strong> {escape(_text(items[0].get('value')))}</p>")
                for fund, item in zip(funds, items):
                    observation = observations.get(fund["cnpj"], {}).get(key)
                    st.html(f"<div class='documentary-diligence'><strong>{escape(_short_name(fund))}</strong>{_cell_html(item, observation)}</div>")
    for theme in documentary_themes(funds):
        markup = documentary_table_html(theme, funds, observations)
        if markup:
            st.html(markup)
    quarterly = quarterly_documentary_table_html(funds)
    if quarterly:
        with st.expander("Declarações trimestrais", expanded=False):
            st.caption("Respostas do informe com trimestre, documento e fonte. Estas observações conservam seu próprio período e não aumentam a cobertura das cláusulas.")
            st.html(quarterly)
    with st.expander("Cobertura e pendências por fundo", expanded=False):
        st.caption("Cobertura = respostas confirmadas com documento, data e página ou cláusula ÷ critérios aplicáveis e de aplicabilidade em apuração. Cada ausência conserva seu motivo.")
        for fund in funds:
            coverage = documentary_coverage(fund)
            ratio = f"{coverage['ratio']:.1%}" if coverage["ratio"] is not None else "sem critérios aplicáveis"
            st.markdown(f"**{_short_name(fund)} · CNPJ {fund['cnpj']}**")
            st.caption(f"{coverage['answered']}/{coverage['denominator']} ({ratio}); {coverage['unresolved']} em apuração; {coverage['not_applicable']} não aplicáveis. Leitura: {fund.get('reviewed_at') or 'ainda não concluída'}.")
            pending = [item for item in fund["criteria"] if not criterion_is_documented_not_applicable(item) and not (item.get("applicability") == "applicable" and criterion_has_answer(item))]
            if pending:
                st.dataframe(pd.DataFrame([{"Critério": item.get("label"), "Motivo": criterion_status(item), "Aplicabilidade": "Em apuração" if item.get("applicability") == "unresolved" else "Aplicável", "Condição": "; ".join(filter(None, [_text(item.get("reason")), _text(item.get("risk_note"))]))} for item in pending]), hide_index=True, width="stretch")
    for detail in lookthrough:
        underlying, invested = detail["fund"], detail["relation"]
        with st.expander(f"{detail['parent_name']} · vínculo de investimento {invested.get('label') or underlying['cnpj']}", expanded=False):
            st.caption(f"CNPJ {underlying['cnpj']} · Subclasse: {invested.get('subclass') or 'não individualizada na fonte'}")
            if invested.get("reason"):
                st.caption(invested["reason"])
            if invested.get("current_position_confirmed") is False:
                st.caption("Posição atual no veículo ainda não comprovada; o vínculo conserva a data da fonte histórica.")
            st.html(_sources_html(invested.get("sources", [])))
            if not underlying["criteria"]:
                st.caption("Documento do veículo referido não obtido nesta leitura.")
            for theme in documentary_themes([underlying]):
                markup = documentary_table_html(theme, [underlying], observations)
                if markup:
                    st.html(markup)
            unresolved = [item for item in underlying["criteria"] if not criterion_is_documented_not_applicable(item) and not (item.get("applicability") == "applicable" and criterion_has_answer(item))]
            if unresolved:
                st.dataframe(pd.DataFrame([{"Critério": item.get("label"), "Motivo": criterion_status(item), "Condição": item.get("reason") or item.get("risk_note") or ""} for item in unresolved]), hide_index=True, width="stretch")
    with st.expander("Downloads e fontes completas", expanded=False):
        token = re.sub(r"[^A-Za-z0-9_-]", "", portfolio.id)
        audit_funds = {fund["cnpj"]: fund for fund in [*funds, *(detail["fund"] for detail in lookthrough)]}
        audit_selection = st.selectbox("Documentos e buscas por fundo", options=list(audit_funds), index=None,
                                       format_func=lambda cnpj: f"{_short_name(audit_funds[cnpj])} · {cnpj}",
                                       placeholder="Escolha um fundo para consultar o inventário", key=f"documentary_audit::{token}")
        if audit_selection:
            st.html(documentary_corpus_html(audit_funds[audit_selection], load_documentary_corpus(audit_selection)))
        from services.deep_dive_ppt_export import build_document_comparison_pptx_bytes
        from services.on_demand_download import current_download_store, download_context_signature, render_native_deferred_download
        # The signature carries the exact basket, portfolio ID and source
        # versions. A single documentary slot releases previous exports on
        # basket changes without touching the financial session caches.
        namespace = "documentary_v2"
        source_paths = [Path(__file__), SOURCE_ROOT / "services/deep_dive_ppt_export.py", SOURCE_ROOT / "services/documentary_ime_comparison.py"]
        for cnpj in audit_funds:
            source_paths.extend(SOURCE_ROOT / "data/documentary_diligence" / directory / f"{cnpj}.json" for directory in ("funds", "history", "corpus", "audit_corpus"))
        signature = download_context_signature(portfolio.id, tuple(audit_funds), reference, observations, source_paths=tuple(source_paths))
        store = current_download_store(st.session_state, namespace=namespace, signature=signature)
        render_native_deferred_download(store=store, namespace=namespace, artifact="documentary_csv", label="Critérios, fontes e pendências (CSV)", file_name=f"documentos_{token}.csv", mime="text/csv",
                                        producer=lambda: documentary_csv_bytes(funds, observations, lookthrough))
        relationships = [{key: value for key, value in detail.items() if key != "fund"} for detail in lookthrough]
        render_native_deferred_download(store=store, namespace=namespace, artifact="documentary_json_zip", label="Evidências completas (JSON em ZIP)", file_name=f"documentos_{token}.zip", mime="application/zip",
                                        producer=lambda: documentary_evidence_zip_bytes(portfolio, list(audit_funds), reference_competence=reference, observations=observations, relationships=relationships))
        manifest = documentary_manifest(portfolio, funds, reference)
        if any(fund.get("criteria") for fund in funds):
            render_native_deferred_download(store=store, namespace=namespace, artifact="documentary_pptx", label="Comparativos (PPTX)", file_name=f"documentos_{token}.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                            producer=lambda: build_document_comparison_pptx_bytes(manifest, build_documentary_comparison_pages(portfolio, funds, observations), portfolio_mode=True, compact=False),
                                            help_text="Mesmos critérios, estados e competência; documentos completos nas notas de cada quadro.")
