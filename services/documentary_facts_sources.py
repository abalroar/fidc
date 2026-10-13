"""Local document access for the documentary fact reading.

Text files keep one form feed per PDF page. Folding keeps a 1:1 index with the
original text so a match position maps back to the exact page and clause.
"""
from __future__ import annotations

import bisect
import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DILIGENCE = ROOT / "data" / "documentary_diligence"
DEEP_DIVES = ROOT / "data" / "deep_dives"


def digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def fold(text: str) -> str:
    """Lowercase, accentless copy with the same length as ``text``."""
    out = []
    for ch in text:
        base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)).lower()
        out.append(base[0] if base else " ")
    return "".join(out)


def _date_key(value: str) -> tuple:
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).timetuple()[:5]
        except (ValueError, AttributeError):
            continue
    return (0,)


@dataclass(eq=False)
class Document:
    id: str
    classification: str
    title: str
    reference_date: str
    delivery_date: str
    url: str
    text_path: str
    pages: int | None = None
    _text: str | None = field(default=None, repr=False)
    _folded: str | None = field(default=None, repr=False)
    _breaks: list[int] | None = field(default=None, repr=False)

    @property
    def text(self) -> str:
        if self._text is None:
            self._text = Path(self.text_path).read_text(encoding="utf-8", errors="ignore")
        return self._text

    @property
    def folded(self) -> str:
        if self._folded is None:
            self._folded = fold(self.text)
        return self._folded

    def page_at(self, position: int) -> int:
        if self._breaks is None:
            self._breaks = [i for i, ch in enumerate(self.text) if ch == "\f"]
        return bisect.bisect_right(self._breaks, position) + 1

    def page_text(self, page: int) -> tuple[int, int]:
        if self._breaks is None:
            self.page_at(0)
        start = self._breaks[page - 2] + 1 if page >= 2 and page - 2 < len(self._breaks) else 0
        end = self._breaks[page - 1] if page - 1 < len(self._breaks) else len(self.text)
        return start, end

    def release(self) -> None:
        self._text = self._folded = None
        self._breaks = None

    @property
    def display_date(self) -> str:
        value = (self.reference_date or "").strip()
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}.*", value):
            return value[:10]
        return (self.delivery_date or "")[:10] or value

    @property
    def kind(self) -> str:
        title = fold(self.title)
        if "suplemento" in title:
            return "Suplemento"
        if "apendice" in title:
            return "Apêndice"
        if "anexo" in title:
            return "Anexo"
        return {"regulamento": "Regulamento", "emissao": "Instrumento de emissão", "assembleia": "Ata",
                "demonstracoes_financeiras": "DF", "rating": "Rating", "evento": "Fato relevante",
                "anexo": "Anexo"}.get(self.classification, self.title.split(" ")[0] if self.title else "Documento")


_CLAUSE = re.compile(r"(?m)^[ \t]{0,12}((?:\d{1,2}\.){1,4}\d{0,2}|\d{1,2}\.\d{1,2})\.?[ \t]+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ(“\"a-z])")
_PART = re.compile(r"(?m)^[ \t]{0,40}(ANEXO|APÊNDICE|APENDICE|SUPLEMENTO|PARTE GERAL)\b[^\n]{0,50}")


def clause_at(doc: Document, position: int) -> str:
    text = doc.text
    window = text[max(0, position - 6000):position + 1]
    matches = list(_CLAUSE.finditer(window))
    clause = matches[-1].group(1).rstrip(".") if matches else ""
    part = ""
    parts = list(_PART.finditer(text[max(0, position - 400000):position + 1]))
    if parts:
        label = re.sub(r"\s+", " ", parts[-1].group(0).strip())
        head = label.split(" ")[0].upper()
        if head in {"ANEXO", "APÊNDICE", "APENDICE", "SUPLEMENTO"}:
            roman = re.match(r"(ANEXO|AP[ÊE]NDICE|SUPLEMENTO)\s+([IVXLC]+|[A-Z]|\d+|ÚNICO|UNICO)\b", label.upper())
            part = (head.capitalize().replace("Apendice", "Apêndice") + (" " + roman.group(2) if roman else ""))
    return ", ".join(filter(None, [part, ("cl. " + clause) if clause else ""]))


@lru_cache(maxsize=4)
def corpus(cnpj: str) -> dict:
    path = DILIGENCE / "corpus" / f"{digits(cnpj)}.json"
    return json.loads(path.read_text()) if path.exists() else {"documents": []}


def documents(cnpj: str) -> list[Document]:
    out = []
    for raw in corpus(cnpj).get("documents", []):
        path = raw.get("text_path") or ""
        if not path or not Path(path).exists():
            local = list((DILIGENCE / "text" / digits(cnpj)).glob(f"{raw.get('id')}_*.txt"))
            path = str(local[0]) if local else ""
        if not path:
            continue
        out.append(Document(str(raw.get("id")), raw.get("classification") or "", raw.get("title") or "",
                            raw.get("reference_date") or "", raw.get("delivery_date") or "", raw.get("url") or "",
                            path, raw.get("pages_total")))
    return out


def current_documents(cnpj: str) -> tuple[list[Document], list[Document]]:
    """Return (regulation set, issuance set), most recent first."""
    docs = documents(cnpj)
    fund_path = DILIGENCE / "funds" / f"{digits(cnpj)}.json"
    selected = set()
    if fund_path.exists():
        selected = {str(i) for i in json.loads(fund_path.read_text()).get("document_selection", {}).get("current_document_ids", [])}
    regs = sorted((d for d in docs if d.classification in {"regulamento", "anexo"}), key=lambda d: _date_key(d.delivery_date), reverse=True)
    chosen = [d for d in regs if d.id in selected]
    if regs and regs[0] not in chosen:
        chosen.insert(0, regs[0])
    # Keep at most the latest two regulation texts plus selected annexes.
    chosen = list(dict.fromkeys(chosen))[:4]
    issuance = sorted((d for d in docs if d.classification == "emissao"), key=lambda d: _date_key(d.delivery_date), reverse=True)[:4]
    return chosen, issuance


# Legacy curated answers -------------------------------------------------------

LEGACY_TO_ROWS = {
    "natureza dos recebiveis": ("receivables", "agro_backing", "card_receivables"),
    "originador/endossante": ("originator", "assignor"),
    "devedor": ("debtor",),
    "garantia": ("collateral", "real_collateral", "payroll", "card_lock"),
    "elegibilidade": ("eligibility", "age_limit", "installment_min", "term_max"),
    "condicoes de cessao": ("eligibility",),
    "concentracao": ("debtor_limit", "assignor_limit", "sacado_limit"),
    "limite de concentracao": ("debtor_limit", "assignor_limit", "sacado_limit"),
    "subordinacao minima": ("sub_senior", "quota_structure", "sub_check"),
    "indice de subordinacao": ("sub_senior",),
    "subordinacao mezanino": ("sub_mezz",),
    "subordinacao mezanino por camada": ("sub_mezz",),
    "gatilhos de avaliacao/liquidacao": ("eval_triggers", "liquidation"),
    "eventos de avaliacao": ("eval_triggers",),
    "liquidacao antecipada": ("liquidation",),
    "reserva de caixa": ("reserve",), "reserva de despesas": ("reserve",), "reserva de liquidez": ("reserve",),
    "reserva ou caixa minimo": ("reserve",),
    "pdd": ("pdd",), "cobertura minima de pdd/provisao": ("pdd",),
    "alocacao minima": ("allocation",), "alocacao minima em direitos creditorios": ("allocation",),
    "alocacao minima regulatoria": ("allocation",),
    "pool/revolvencia": ("revolving",),
    "duracao/publico-alvo": ("duration", "investors"),
    "cessao/recompra": ("recourse",), "coobrigacao": ("recourse",), "resolucao de cessao": ("recourse",),
    "waterfall": ("amortization",), "carencia": ("amortization",), "juros/amortizacao": ("amortization",),
    "vencimento": ("amortization", "duration"),
    "classes/series": ("quota_structure",),
    "remuneracao": ("target_senior", "target_mezz"), "remuneracao senior": ("target_senior",),
    "remuneracao mezanino": ("target_mezz",),
    "administracao": ("admin_fee",), "gestao": ("mgmt_fee",),
    "prazo dos recebiveis": ("term_max",),
    "prestadores": ("administrator", "manager", "custodian", "servicer"),
    "prestadores essenciais": ("administrator", "manager", "custodian"),
}

_GAP = re.compile(r"n[aã]o localizad|nao localizad|n[aã]o confirmad|^n/?d$|sem informa[cç][aã]o|^[—-]?$|requer|nao validad|não validad", re.I)


def _legacy_rows(label: str) -> tuple[str, ...]:
    return LEGACY_TO_ROWS.get(fold(label).strip(), ())


@lru_cache(maxsize=1)
def _legacy_index() -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for manifest_path in sorted(DEEP_DIVES.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        generated = manifest.get("generated_at") or ""
        tables = manifest_path.parent / "tables"
        funds = manifest.get("funds") or []
        # Long-format thresholds carry the source of each answer.
        path = tables / "thresholds.csv"
        if path.exists():
            for row in csv.DictReader(path.open(encoding="utf-8")):
                value = (row.get("Limite/regra") or row.get("Limite") or "").strip()
                if not value or _GAP.search(value):
                    continue
                index.setdefault(digits(row.get("CNPJ")), []).append({
                    "label": row.get("Critério") or "", "value": value, "source": row.get("Fonte") or "",
                    "generated": generated, "table": "thresholds"})
        path = tables / "structural_costs.csv"
        if path.exists():
            for row in csv.DictReader(path.open(encoding="utf-8")):
                value = (row.get("Percentual a.a.") or "").strip()
                if not value or _GAP.search(value):
                    continue
                index.setdefault(digits(row.get("CNPJ")), []).append({
                    "label": row.get("Item") or "", "value": value, "source": row.get("Fonte") or "",
                    "generated": generated, "table": "costs"})
        path = tables / "comparison_main.csv"
        if path.exists():
            rows = list(csv.reader(path.open(encoding="utf-8")))
            if rows:
                header = rows[0][1:]
                for i, name in enumerate(header):
                    fund = next((f for f in funds if name in {f.get("short_name"), f.get("name")}), funds[i] if i < len(funds) else None)
                    if not fund:
                        continue
                    for row in rows[1:]:
                        label = row[0].split(" · ")[-1]
                        value = (row[i + 1] if i + 1 < len(row) else "").strip()
                        if not value or _GAP.search(value) or not _legacy_rows(label):
                            continue
                        index.setdefault(digits(fund.get("cnpj")), []).append({
                            "label": label, "value": value, "source": "", "generated": generated, "table": "comparison"})
    return index


def legacy_answers(cnpj: str) -> dict[str, list[dict]]:
    """Legacy short answers grouped by target row, most recent package first, deduplicated."""
    grouped: dict[str, list[dict]] = {}
    for item in sorted(_legacy_index().get(digits(cnpj), []), key=lambda x: x["generated"], reverse=True):
        for row_id in _legacy_rows(item["label"]):
            bucket = grouped.setdefault(row_id, [])
            if all(fold(item["value"]) != fold(b["value"]) for b in bucket):
                bucket.append(dict(item, row=row_id))
    # Comparison cells lack sources; borrow the thresholds source of the same label.
    for bucket in grouped.values():
        for item in bucket:
            if not item["source"]:
                match = next((b for b in bucket if b["source"] and fold(b["label"]) == fold(item["label"])), None)
                if match:
                    item["source"] = match["source"]
    return grouped


def parse_legacy_source(source: str) -> tuple[str, list[int]]:
    doc = re.search(r"(?:ID(?: Fundos\.NET)?|Fundos\.NET ID|id=)\s*(\d{5,8})", source)
    pages = []
    for a, b in re.findall(r"p\.\s*(\d{1,3})(?:\s*[–-]\s*(\d{1,3}))?", source):
        a = int(a)
        b = int(b) if b else a
        pages.extend(range(a, min(b, a + 4) + 1))
    return (doc.group(1) if doc else ""), pages
