"""Comparative documentary view built from per-fund typed facts.

Each fund is read once (data/documentary_facts/<cnpj>.json). A basket is a view
over its funds: the layout depends on basket size, rows identical for every
fund move to a footnote, and the IME monthly position shows observed value and
headroom next to each contractual limit.
"""
from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from services.documentary_facts_catalog import ROW_BY_ID, ROWS, SECTIONS, row_applies, rows_for_types

ROOT = Path(__file__).resolve().parents[1]
FACTS_DIR = ROOT / "data" / "documentary_facts"
IME_DIR = ROOT / "data" / "documentary_diligence" / "ime"

ABSENT_DISPLAY = {"nd": "n/d", "not_applicable": "—"}
IME_NOTE = ("Posição mensal do IME; o regulamento apura diariamente. Vigência pela versão mais recente "
            "do regulamento anterior à competência.")
TRANSPOSED_ROWS = ("fund_type", "quota_structure", "sub_senior", "allocation", "debtor_limit", "reserve",
                   "admin_fee", "target_senior", "originator")
SIDE_BY_SIDE_MAX = 8


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


# Loading ----------------------------------------------------------------------

def _facts_signature() -> tuple:
    try:
        return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in FACTS_DIR.glob("*.json")))
    except OSError:
        return ()


@lru_cache(maxsize=256)
def _load(cnpj: str, mtime: int) -> dict | None:
    path = FACTS_DIR / f"{cnpj}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_facts(cnpj: object) -> dict | None:
    cnpj = _digits(cnpj)
    path = FACTS_DIR / f"{cnpj}.json"
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return None
    payload = _load(cnpj, mtime)
    return payload if payload and payload.get("cnpj") == cnpj else None


def fund_approved(cnpj: object) -> bool:
    payload = load_facts(cnpj)
    return bool(payload and payload.get("validation", {}).get("approved"))


def portfolio_cnpjs(portfolio: Any) -> list[str]:
    return [_digits(getattr(f, "cnpj", None) or (f.get("cnpj") if isinstance(f, Mapping) else f)) for f in getattr(portfolio, "funds", [])]


def portfolio_ready(portfolio: Any) -> bool:
    cnpjs = portfolio_cnpjs(portfolio)
    return bool(cnpjs) and all(fund_approved(c) for c in cnpjs)


def portfolio_has_any_facts(portfolio: Any) -> bool:
    return any(fund_approved(c) for c in portfolio_cnpjs(portfolio))


@lru_cache(maxsize=4)
def _peer_index(signature: tuple) -> dict:
    """Numeric facts of every approved fund, grouped by fund type, row and unit."""
    _ = signature
    index: dict = {}
    for path in FACTS_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not payload.get("validation", {}).get("approved"):
            continue
        fund_type = payload.get("fund_type", "")
        for row_id, fact in payload.get("facts", {}).items():
            value = fact.get("value")
            if value is None or fact.get("status") != "confirmed":
                continue
            index.setdefault((fund_type, row_id, _peer_unit(fact)), []).append((payload["cnpj"], float(value)))
    return index


def _peer_unit(fact: dict) -> str:
    # PL/sênior ratios (≥ 100%) are not comparable with subordination shares of the PL.
    return "pl_sr" if fact.get("basis") == "PL/sr" else _unit_kind(fact.get("display", ""))


def _unit_kind(display: str) -> str:
    if "cobertura" in display.casefold():
        return "cov"
    if "R$" in display:
        return "brl"
    if "%" in display:
        return "pct"
    return "num"


# IME --------------------------------------------------------------------------

def _competences(cnpj: str) -> list[str]:
    return sorted(p.stem.split("_")[1] for p in IME_DIR.glob(f"{cnpj}_*.json"))


@lru_cache(maxsize=512)
def _ime_values(cnpj: str, competence: str) -> dict:
    path = IME_DIR / f"{cnpj}_{competence}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload.get("values") or {} if payload.get("status") == "parsed" else {}


def common_competence(cnpjs: list[str]) -> str | None:
    sets = [set(_competences(c)) for c in cnpjs]
    sets = [s for s in sets if s]
    if not sets:
        return None
    common = set.intersection(*sets)
    return max(common) if common else None


def competence_label(competence: str | None) -> str:
    return f"{competence[4:]}/{competence[:4]}" if competence else ""


def _ratio(values: Mapping, numerator: str, denominator: str = "net_asset_value", subtract: str = "") -> float | None:
    num, den = values.get(numerator), values.get(denominator)
    if num is None or den is None or den <= 0:
        return None
    if subtract:
        num = num - (values.get(subtract) or 0)
    return num / den * 100


@dataclass
class Observation:
    observed: float | None = None
    headroom: float | None = None
    basis: str = ""
    note: str = ""


def observe(row_id: str, fact: Mapping, values: Mapping, fund_type: str) -> Observation:
    """Monthly position against a contractual minimum, or a specific reason."""
    if not values:
        return Observation(note="IME da competência indisponível")
    limit = fact.get("value")
    if fact.get("status") != "confirmed" or limit is None:
        return Observation()
    if row_id in {"allocation", "investee_share"}:
        if fund_type == "FIC":
            observed, basis = _ratio(values, "fidc_quotas"), "cotas de FIDC / PL"
        else:
            observed, basis = _ratio(values, "credit_rights", subtract="pdd"), "DC líquidos de PDD / PL"
        upper = 110.0
    elif row_id == "sub_senior" and fact.get("basis") == "PL/sr":
        observed, basis = _ratio(values, "net_asset_value", "senior_quotas"), "PL / cotas sênior"
        upper = 10000.0
    elif row_id == "sub_senior" and str(fact.get("basis", "")).startswith("cobertura"):
        return Observation(note="cobertura por camada exige valor presente dos créditos, ausente no IME")
    elif row_id == "sub_senior":
        key = {"jr/PL": "subordinated_quotas", "mez+jr/PL": "subordinated_and_mezzanine_quotas"}.get(fact.get("basis", ""), "subordinated_and_mezzanine_quotas")
        observed, basis = _ratio(values, key), "subordinadas / PL" if key == "subordinated_quotas" else "(mezanino + subordinadas) / PL"
        upper = 100.0
    elif row_id == "sub_mezz":
        observed, basis = _ratio(values, "subordinated_quotas"), "subordinadas / PL"
        upper = 100.0
    else:
        return Observation()
    if observed is None:
        return Observation(note="campo do IME ausente para " + basis)
    if observed < 0 or observed > upper:
        return Observation(note=f"valor do IME incoerente para {basis}; não exibido")
    return Observation(observed=observed, headroom=observed - float(limit), basis=basis)


def _pct(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return ""
    text = f"{value:+.1f}" if signed else f"{value:.1f}"
    return text.replace(".", ",") + (" p.p." if signed else "%")


# View model -------------------------------------------------------------------

@dataclass
class Column:
    cnpj: str
    name: str
    short: str
    fund_type: str
    facts: dict
    leitura: str
    documents: dict
    approved: bool


@dataclass
class Section:
    title: str
    rows: list[tuple[str, list[str]]] = field(default_factory=list)   # (label, cells)
    common: list[str] = field(default_factory=list)                   # rows equal for every fund
    differences: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    has_ime: bool = False


@dataclass
class BasketView:
    layout: str                     # single | side_by_side | transposed
    columns: list[Column]
    competence: str | None
    sections: list[Section]
    pending: list[dict]
    peers_label: str = ""
    missing: list[str] = field(default_factory=list)
    transposed: list[dict] = field(default_factory=list)


def _short_name(name: str, fallback: str) -> str:
    try:
        from services.fund_name_display import short_fund_name
        return short_fund_name(name or fallback, max_length=24) or fallback
    except Exception:  # noqa: BLE001
        return (name or fallback)[:24]


def _columns(portfolio: Any) -> tuple[list[Column], list[str]]:
    columns, missing = [], []
    display_names = {}
    for fund in getattr(portfolio, "funds", []):
        cnpj = _digits(getattr(fund, "cnpj", None) or (fund.get("cnpj") if isinstance(fund, Mapping) else ""))
        display_names[cnpj] = getattr(fund, "display_name", None) or (fund.get("display_name") if isinstance(fund, Mapping) else "") or ""
    for cnpj, display in display_names.items():
        payload = load_facts(cnpj)
        if not payload:
            missing.append(cnpj)
            columns.append(Column(cnpj, display or cnpj, _short_name(display, cnpj), "", {}, "", {}, False))
            continue
        name = payload.get("name") or display
        columns.append(Column(cnpj, name, _short_name(display or name, cnpj), payload.get("fund_type", ""),
                              payload.get("facts", {}), payload.get("leitura", ""), payload.get("documents", {}),
                              bool(payload.get("validation", {}).get("approved"))))
    # FIC look-through: the invested class appears next to its FIC.
    basket = {c.cnpj for c in columns}
    expanded: list[Column] = []
    for column in columns:
        expanded.append(column)
        if column.fund_type != "FIC":
            continue
        for link in (load_facts(column.cnpj) or {}).get("lookthrough", []):
            target = _digits(link.get("cnpj"))
            payload = load_facts(target)
            if not payload or target in basket or not payload.get("validation", {}).get("approved"):
                continue
            basket.add(target)
            expanded.append(Column(target, payload.get("name", target), "↳ " + _short_name(payload.get("name", ""), target) + " (investida)",
                                   payload.get("fund_type", ""), payload.get("facts", {}), payload.get("leitura", ""),
                                   payload.get("documents", {}), True))
    columns = expanded
    # Distinct headers even when short names collide.
    seen: dict[str, int] = {}
    for column in columns:
        seen[column.short] = seen.get(column.short, 0) + 1
    for column in columns:
        if seen[column.short] > 1:
            column.short = f"{column.short} ({column.cnpj[:8]})"
    return columns, missing


def _cell(column: Column, row_id: str) -> str:
    if not column.facts:
        return "sem leitura documental"
    fact = column.facts.get(row_id)
    if fact is None:
        return "—" if not row_applies(ROW_BY_ID[row_id], column.fund_type) else "n/d"
    return ABSENT_DISPLAY.get(fact.get("status"), fact.get("display", ""))


def _source_label(source: Mapping) -> str:
    where = ", ".join(filter(None, [source.get("clause", ""), f"p. {source['page']}" if source.get("page") else ""]))
    return f"{source.get('kind', 'Documento')} {source.get('date', '')}" + (f", {where}" if where else "")


def _fmt_value(value: float, unit: str) -> str:
    if unit == "brl":
        if value >= 1e6:
            return f"R$ {value / 1e6:g} mi".replace(".", ",")
        if value >= 1e3:
            return f"R$ {value / 1e3:g} mil".replace(".", ",")
        return f"R$ {value:g}".replace(".", ",")
    if unit in {"pct", "cov"}:
        return f"{value:g}%".replace(".", ",")
    return f"{value:g}".replace(".", ",")


def _differences(rows: list[tuple[str, list[str]]], columns: list[Column], numeric: dict[str, list[tuple[float, str] | None]]) -> list[str]:
    notes = []
    for label, values in numeric.items():
        by_unit: dict[str, list[tuple[float, str]]] = {}
        for item, column in zip(values, columns):
            if item is not None:
                by_unit.setdefault(item[1], []).append((item[0], column.short))
        for unit, pairs in by_unit.items():
            if len(pairs) >= 2 and min(pairs)[0] != max(pairs)[0]:
                low, high = min(pairs), max(pairs)
                notes.append(f"{label}: de {_fmt_value(low[0], unit)} ({low[1]}) a {_fmt_value(high[0], unit)} ({high[1]}).")
    for label, cells in rows:
        absent = [col.short for col, c in zip(columns, cells) if c == "—" or c.casefold().startswith("não previst")]
        present = [c for c in cells if c not in {"—", "n/d", "sem leitura documental"} and not c.casefold().startswith("não previst")]
        if present and absent and label in {"Reserva de caixa", "Subordinação mínima da sênior", "Coobrigação e recompra", "Revolvência"}:
            notes.append(f"{label}: ausente em {', '.join(absent)}.")
    return notes[:5]


def build_view(portfolio: Any) -> BasketView:
    columns, missing = _columns(portfolio)
    cnpjs = [c.cnpj for c in columns]
    competence = common_competence(cnpjs)
    values = {c: (_ime_values(c, competence) if competence else {}) for c in cnpjs}
    size = len(columns)
    layout = "single" if size == 1 else "side_by_side" if size <= SIDE_BY_SIDE_MAX else "transposed"
    types = {c.fund_type for c in columns if c.fund_type}
    view = BasketView(layout, columns, competence, [], [], missing=missing)
    peers = _peer_index(_facts_signature()) if layout == "single" else {}
    if layout == "single" and columns and columns[0].fund_type:
        view.peers_label = f"Pares: {columns[0].fund_type}"
    for section_title in SECTIONS:
        section = Section(section_title)
        numeric: dict[str, list[float | None]] = {}
        for row in rows_for_types(types or {""}):
            if row.section != section_title or row.id == "fund_type" and layout != "single" and section_title != SECTIONS[0]:
                continue
            cells = [_cell(c, row.id) for c in columns]
            if all(cell in {"—", "n/d", "sem leitura documental"} for cell in cells):
                continue
            if layout != "single" and len(set(cells)) == 1 and size > 1:
                section.common.append(f"{row.label}: {cells[0]}")
                continue
            if layout == "single":
                cells = cells + [_peer_cell(peers, columns[0], row.id)]
            section.rows.append((row.label, cells))
            if row.numeric:
                numeric[row.label] = [((c.facts.get(row.id) or {}).get("value"), _unit_kind((c.facts.get(row.id) or {}).get("display", "")))
                                      if (c.facts.get(row.id) or {}).get("status") == "confirmed" and (c.facts.get(row.id) or {}).get("value") is not None else None
                                      for c in columns]
            if row.ime:
                observations = [observe(row.id, c.facts.get(row.id, {}), values.get(c.cnpj, {}), c.fund_type) for c in columns]
                if any(o.observed is not None for o in observations):
                    section.has_ime = True
                    observed = [(_pct(o.observed) if o.observed is not None else (o.note and "n/d") or "—") for o in observations]
                    headroom = [(_pct(o.headroom, signed=True) if o.headroom is not None else "—") for o in observations]
                    label = f"↳ Observado no IME {competence_label(competence)}"
                    if layout == "single":
                        observed.append("")
                        headroom.append("")
                    section.rows.append((label, observed))
                    section.rows.append(("↳ Folga sobre o mínimo", headroom))
                    for column, observation in zip(columns, observations):
                        if observation.observed is None and observation.note and column.facts.get(row.id, {}).get("status") == "confirmed":
                            view.pending.append({"fund": column.short, "row": f"IME · {row.label}", "reason": observation.note})
            for column in columns:
                fact = column.facts.get(row.id) or {}
                for source in fact.get("sources", [])[:2]:
                    section.evidence.append({"fund": column.short, "row": row.label, "display": fact.get("display", ""),
                                             "source": _source_label(source), "url": source.get("url", ""), "excerpt": source.get("excerpt", "")})
        if not section.rows:
            continue
        if layout != "single":
            section.differences = _differences(section.rows, columns, numeric)
        else:
            section.differences = _peer_notes(peers, columns[0], section_title)
        per_fund: dict[str, list[str]] = {}
        for item in section.evidence:
            document = item["source"].split(",")[0]
            per_fund.setdefault(item["fund"], [])
            if document not in per_fund[item["fund"]]:
                per_fund[item["fund"]].append(document)
        section.sources = [f"{fund}: " + ", ".join(documents) for fund, documents in per_fund.items()]
        view.sections.append(section)
    for column in columns:
        for row_id, fact in column.facts.items():
            if fact.get("status") == "nd":
                view.pending.append({"fund": column.short, "row": ROW_BY_ID[row_id].label, "reason": fact.get("reason", "")})
        if not column.facts:
            view.pending.append({"fund": column.short, "row": "Fundo", "reason": "Fundo ainda sem leitura documental; incluído na fila de leitura."})
    if layout == "transposed":
        view.transposed = _transposed(columns, values)
    return view


def _peer_values(peers: dict, column: Column, row_id: str) -> list[float]:
    fact = column.facts.get(row_id) or {}
    return [v for cnpj, v in peers.get((column.fund_type, row_id, _peer_unit(fact)), []) if cnpj != column.cnpj]


def _peer_cell(peers: dict, column: Column, row_id: str) -> str:
    row = ROW_BY_ID[row_id]
    if not row.numeric:
        return ""
    values = _peer_values(peers, column, row_id)
    if len(values) < 3:
        return "pares insuficientes" if values or column.facts.get(row_id, {}).get("value") is not None else ""
    unit = _peer_unit(column.facts.get(row_id) or {})
    fmt = (lambda v: f"{v:g}%".replace(".", ",")) if unit in {"pct", "pl_sr"} else (lambda v: f"{v:,.0f}".replace(",", "."))
    return f"mediana {fmt(statistics.median(values))} ({fmt(min(values))}–{fmt(max(values))}), n={len(values)}"


def _peer_notes(peers: dict, column: Column, section_title: str) -> list[str]:
    notes = []
    for row in ROWS:
        if row.section != section_title or not row.numeric:
            continue
        value = (column.facts.get(row.id) or {}).get("value")
        values = _peer_values(peers, column, row.id)
        if value is None or len(values) < 3:
            continue
        quartiles = statistics.quantiles(values, n=4)
        if value < quartiles[0]:
            notes.append(f"{row.label} abaixo do quartil inferior dos pares ({_num(value)} vs mediana {_num(statistics.median(values))}).")
        elif value > quartiles[2]:
            notes.append(f"{row.label} acima do quartil superior dos pares ({_num(value)} vs mediana {_num(statistics.median(values))}).")
    return notes[:4]


def _num(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _transposed(columns: list[Column], values: Mapping) -> list[dict]:
    rows = []
    for column in sorted(columns, key=lambda c: (c.fund_type or "zz", c.short)):
        record = {"Fundo": column.short}
        for row_id in TRANSPOSED_ROWS:
            record[ROW_BY_ID[row_id].label] = _cell(column, row_id)
        observation = observe("sub_senior", column.facts.get("sub_senior", {}), values.get(column.cnpj, {}), column.fund_type)
        record["Folga subord."] = _pct(observation.headroom, signed=True) if observation.headroom is not None else "—"
        rows.append(record)
    return rows


# Exports ----------------------------------------------------------------------

def view_frames(view: BasketView) -> list[tuple[str, Any, list[str]]]:
    """(title, DataFrame, notes) per section, shared by screen, CSV and PPT."""
    import pandas as pd
    frames = []
    headers = ["Critério", *[c.short for c in view.columns]] + ([view.peers_label or "Pares"] if view.layout == "single" else [])
    for section in view.sections:
        frame = pd.DataFrame([[label, *cells] for label, cells in section.rows], columns=headers)
        notes = []
        if section.common:
            notes.append("Igual para todos: " + " · ".join(section.common))
        if section.has_ime:
            notes.append(IME_NOTE)
        frames.append((section.title, frame, notes))
    return frames


def facts_csv_bytes(view: BasketView) -> bytes:
    import csv
    import io
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Fundo", "CNPJ", "Tipo", "Seção", "Critério", "Resposta", "Status", "Motivo", "Fonte", "Trecho"])
    for column in view.columns:
        for row in ROWS:
            fact = column.facts.get(row.id)
            if not fact:
                continue
            sources = fact.get("sources", [])
            writer.writerow([column.name, column.cnpj, column.fund_type, row.section, row.label, fact.get("display", ""), fact.get("status", ""),
                             fact.get("reason", ""), " | ".join(_source_label(s) for s in sources), " | ".join(s.get("excerpt", "") for s in sources)])
    return buffer.getvalue().encode("utf-8-sig")


def facts_zip_bytes(view: BasketView) -> bytes:
    import io
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for column in view.columns:
            path = FACTS_DIR / f"{column.cnpj}.json"
            if path.exists():
                archive.write(path, f"fatos/{column.cnpj}.json")
    return buffer.getvalue()
