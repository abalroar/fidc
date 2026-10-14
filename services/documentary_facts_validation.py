"""Grounding checks for short documentary answers.

An answer may paraphrase, but every number, date and named party it shows must
be present in the passage it cites, and it must not copy the clause.
"""
from __future__ import annotations

import re

from services.documentary_facts_sources import fold

MAX_CELL = 90
BANNED = ("sintese pendente", "aplicabilidade em apuracao", "nao localizad", "sem informacao documental",
          "extracao pendente", "clausula nao localizada", "requer documento", "precisa de documento")
_MULT = {"mil": 1e3, "mi": 1e6, "milhao": 1e6, "milhoes": 1e6, "bi": 1e9, "bilhao": 1e9, "bilhoes": 1e9}
_NUMBER = re.compile(r"(?<![\w.,/])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)(?![ªº°])(?:\s*(mil|mi|milhao|milhoes|bi|bilhao|bilhoes)\b)?")
_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_MONTHS = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
_STOP_ENTITY = {"Classe", "Fundo", "Cotas", "Gestor", "Gestora", "Administrador", "Administradora", "Custodiante",
                "Regulamento", "Cedente", "Cedentes", "Endossante", "Originador", "Originadora", "Sociedade", "Grupo",
                "Instituição", "Pagamento", "Pessoas", "Físicas", "Jurídicas", "Varia", "Não", "Diversos", "Mesmo", "Agente",
                "Emissores", "Distribuidores", "Produtores", "Endossantes", "Instituições", "Correspondentes", "Múltiplos",
                "Tomadores", "Empresas"}


def _value(token: str) -> float:
    return float(token.replace(".", "").replace(",", ".")) if "," in token or re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token) else float(token)


def numbers_in(text: str) -> list[float]:
    """Numbers shown in a short answer, with mil/mi/bi applied; dates excluded."""
    folded = fold(re.sub(r"\d+\s*[ªº°]", " ", _DATE.sub(" ", text)))
    values = []
    for token, mult in _NUMBER.findall(folded):
        try:
            values.append(_value(token) * _MULT.get(mult, 1))
        except ValueError:
            continue
    return values


def _evidence_numbers(text: str) -> set[float]:
    folded = fold(text)
    values: set[float] = set()
    for token, mult in _NUMBER.findall(folded):
        try:
            base = _value(token)
        except ValueError:
            continue
        values.add(base)
        if mult:
            values.add(base * _MULT[mult])
    return values


def _date_present(day: str, month: str, year: str, folded: str) -> bool:
    d, m = int(day), int(month)
    if re.search(rf"\b0?{d}/0?{m}/{year}\b", folded):
        return True
    return 1 <= m <= 12 and bool(re.search(rf"\b0?{d}(?:º)?\s+de\s+{_MONTHS[m - 1]}\s+de\s+{year}", folded))


def unsupported_numbers(display: str, evidence: str) -> list[str]:
    folded = fold(evidence)
    have = _evidence_numbers(evidence)
    missing = []
    for day, month, year in _DATE.findall(display):
        if not _date_present(day, month, year, folded):
            missing.append(f"{day}/{month}/{year}")
    for value in numbers_in(display):
        if not any(abs(value - v) <= 1e-6 * max(1.0, abs(v)) for v in have):
            missing.append(f"{value:g}")
    return missing


def unsupported_names(display: str, evidence: str) -> list[str]:
    folded = fold(evidence)
    words = re.findall(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç&-]{4,}\b", display)
    return [w for w in words if w not in _STOP_ENTITY and fold(w) not in folded]


def copied_sequence(display: str, evidence: str, size: int = 8) -> str:
    words = re.findall(r"\w+", fold(display))
    folded = " ".join(re.findall(r"\w+", fold(evidence)))
    for i in range(0, max(0, len(words) - size + 1)):
        chunk = " ".join(words[i:i + size])
        if chunk in folded:
            return chunk
    return ""


def check_answer(row, display: str, status: str, sources: list[dict], reason: str) -> list[str]:
    problems = []
    if len(display) > MAX_CELL:
        problems.append(f"célula com {len(display)} caracteres (máx. {MAX_CELL})")
    folded = fold(display)
    if any(b in folded for b in BANNED):
        problems.append("frase de lacuna proibida")
    if status in {"nd", "not_applicable", "absent"}:
        if not reason:
            problems.append("ausência sem motivo")
        return problems
    if status == "not_named":
        return problems
    if not sources:
        problems.append("resposta sem fonte")
        return problems
    evidence = " ".join(s.get("excerpt", "") for s in sources)
    missing = unsupported_numbers(display, evidence)
    if missing:
        problems.append("números fora da fonte: " + ", ".join(missing))
    if row.unit == "entity":
        names = unsupported_names(display, evidence)
        if names:
            problems.append("nomes fora da fonte: " + ", ".join(names))
    copied = copied_sequence(display, evidence)
    if copied:
        problems.append(f"cópia literal: '{copied}'")
    return problems
