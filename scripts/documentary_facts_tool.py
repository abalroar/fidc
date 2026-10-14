"""Reading workflow for documentary facts, one fund at a time.

  dossier <cnpj> [--work DIR]   print a compact reading dossier (legacy answers + candidate passages)
  compile <cnpj> <facts.txt> [--work DIR]   validate a reader's facts file and write data/documentary_facts/<cnpj>.json

The dossier only locates passages. Every answer is written by the reader in the
facts file, citing candidate ids; ``compile`` checks that each number and name
in the answer appears in the cited passage before anything is published.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.documentary_facts_catalog import MODULE_TYPES, ROW_BY_ID, ROWS, FUND_TYPES, row_applies  # noqa: E402
from services.documentary_facts_sources import (  # noqa: E402
    Document, clause_at, current_documents, digits, documents, fold, legacy_answers, parse_legacy_source,
)
from services.documentary_facts_validation import check_answer, numbers_in  # noqa: E402

FACTS_DIR = ROOT / "data" / "documentary_facts"
DEFAULT_WORK = Path("/tmp/documentary_facts_work")

LONG_ROWS = {"eligibility": 1300, "eval_triggers": 1400, "liquidation": 1100, "amortization": 900, "reserve": 800, "pdd": 800}
SHORT_ROWS = {"administrator": 320, "manager": 320, "custodian": 320, "investors": 300, "duration": 360}
MODULE_SIGNALS = {
    "consignado": (r"consign|saque.aniversario|fgts", 3),
    "cartao": (r"unidades? de recebiveis|arranjos? de pagamento|recebiveis de cartao|subcredenciador|credenciador", 3),
    "agro": (r"agroneg|cedula de produto rural|\bcpr\b|fiagro", 5),
    "garantia_real": (r"alienacao fiduciaria de (veiculo|imove|bem)|\bveiculos?\b|home equity|garantia imobiliaria", 3),
    "multicedente": (r"\bsacad[oa]s?\b|duplicata", 6),
    "fic": (r"classe investida|fundo investido|cotas de (outros )?(fundos|fidc|classes)", 3),
}


def _compile(pattern: str) -> re.Pattern:
    return re.compile(pattern.replace(" ", r"\s+"))


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\f", " ")).strip()


def _window(doc: Document, start: int, end: int, size: int) -> tuple[int, int]:
    text = doc.text
    left = max(0, start - min(260, size // 3))
    cut = text.rfind("\n", left, start)
    if cut > 0 and start - cut < 260:
        left = cut + 1
    right = min(len(text), end + size)
    # "Name, ... (“Gestor”)": the defined party precedes the term.
    if "(“" in text[max(0, start - 3):start + 2]:
        left = max(0, start - 420)
        cut = max(text.rfind(". ", left, start), text.rfind(";", left, start))
        return (cut + 1 if cut > 0 else left), min(len(text), end + 40)
    # A glossary entry ends where the next defined term starts.
    if "“" in text[max(0, start - 3):start + 1]:
        left = max(left, text.rfind("“", 0, start + 1))
        nxt = re.search(r";\s*“|\.\s*“", text[end:right])
        if nxt and nxt.start() > 40:
            return left, end + nxt.start() + 1
    stop = max(text.rfind(". ", end, right), text.rfind(";\n", end, right), text.rfind(".\n", end, right))
    if stop > end + size // 3:
        right = stop + 1
    return left, right


GOVERNANCE_ROWS = {"administrator", "manager", "custodian", "investors", "duration", "quota_structure"}


def _score(row, index: int, doc_rank: int, doc: Document, start: int, window: str) -> float:
    score = 10.0 - 1.5 * index - 1.0 * doc_rank
    before = doc.text[max(0, start - 3):start + 1]
    if "“" in before or '"' in before:
        score += 4
    if row.unit in {"pct", "brl"} or row.numeric:
        score += 3 if re.search(r"\d\s*%|R\$\s*\d", window) else -2
    if re.search(r"\.{6,}|…{3,}", window):
        score -= 8
    if len(re.findall(r"\brisco", fold(window))) >= 2:
        score -= 3
    if row.id not in GOVERNANCE_ROWS and doc.page_at(start) <= 3:
        score -= 3
    if re.search(r"\(i{1,3}v?\)[^()]{0,60}\(v?i{1,3}\)[^()]{0,60}\(i?x\)", fold(window)) and "elegib" not in row.id:
        score -= 2
    return score


def candidates(row, docs: list[Document], *, limit: int, taken: list[tuple] | None = None) -> list[dict]:
    size = LONG_ROWS.get(row.id) or SHORT_ROWS.get(row.id) or 620
    found = []
    for doc_rank, doc in enumerate(docs):
        folded = doc.folded
        for index, pattern in enumerate(row.patterns):
            for match in _compile(pattern).finditer(folded):
                left, right = _window(doc, match.start(), match.end(), size)
                window = _clean(doc.text[left:right])
                if len(window) < 40:
                    continue
                found.append({"score": _score(row, index, doc_rank, doc, match.start(), window), "doc": doc, "left": left,
                              "right": right, "start": match.start(), "text": window})
                if len(found) > 400:
                    break
    found.sort(key=lambda c: -c["score"])
    chosen: list[dict] = []
    taken = taken or []
    for item in found:
        if any(item["doc"] is c["doc"] and min(item["right"], c["right"]) - max(item["left"], c["left"]) > 0.4 * (item["right"] - item["left"]) for c in chosen):
            continue
        if any(item["doc"].id == d.id and min(item["right"], r) - max(item["left"], l) > 0.4 * (item["right"] - item["left"]) for d, l, r in taken):
            continue
        chosen.append(item)
        if len(chosen) >= limit:
            break
    return chosen


def _legacy_snippet(entry: dict, all_docs: dict[str, Document]) -> dict | None:
    doc_id, pages = parse_legacy_source(entry.get("source", ""))
    doc = all_docs.get(doc_id)
    if not doc or not pages:
        return None
    nums = []
    for number, unit in re.findall(r"(\d+(?:[.,]\d+)?)\s*(%|mil|mi\b|dias|meses|anos|DU)?", entry["value"]):
        if number in {"0", "1"} and not unit:
            continue
        base = re.escape(number.replace(".", ""))
        if unit == "%":
            nums.append(base + r"(?:,0+)?\s*%")
        elif unit == "mil":
            nums.append(re.escape(number) + r"\.000")
        elif unit in {"dias", "meses", "anos", "DU"}:
            nums.append(base + r"\s*\(")
        else:
            nums.append(base)
    row = ROW_BY_ID[entry["row"]]
    for page in pages:
        try:
            start, end = doc.page_text(page)
        except Exception:  # noqa: BLE001
            continue
        segment = doc.text[start:end]
        folded = fold(segment)
        position = None
        for number in nums:
            hit = re.search(r"(?<![\d.,])" + number + r"(?![\dº°ª])", segment)
            if hit:
                position = hit.start()
                break
        if position is None:
            for pattern in row.patterns:
                hit = _compile(pattern).search(folded)
                if hit:
                    position = hit.start()
                    break
        if position is None:
            continue
        left, right = _window(doc, start + position, start + position + 1, 520)
        return {"doc": doc, "left": left, "right": right, "start": start + position, "text": _clean(doc.text[left:right])}
    return None


def _modules(docs: list[Document]) -> set[str]:
    text = " ".join(d.folded[:400000] for d in docs)
    return {m for m, (pattern, minimum) in MODULE_SIGNALS.items() if len(re.findall(pattern, text)) >= minimum}


def _fund_name(cnpj: str) -> str:
    path = ROOT / "data" / "documentary_diligence" / "funds" / f"{cnpj}.json"
    return json.loads(path.read_text()).get("name", cnpj) if path.exists() else cnpj


def build_dossier(cnpj: str, work: Path) -> str:
    cnpj = digits(cnpj)
    regs, issuance = current_documents(cnpj)
    every = {d.id: d for d in documents(cnpj)}
    labels: dict[str, str] = {}
    lines = [f"# {cnpj} · {_fund_name(cnpj)}"]
    for i, doc in enumerate([*regs, *issuance], 1):
        labels[doc.id] = f"D{i}"
        lines.append(f"D{i} = {doc.kind} {doc.display_date} · id {doc.id} · {doc.title[:60]} · {doc.pages or '?'} p.")
    modules = _modules(regs)
    lines.append("módulos sugeridos: " + (", ".join(sorted(modules)) or "nenhum") + "  | tipos: " + "; ".join(FUND_TYPES))
    legacy = legacy_answers(cnpj)
    cache: dict[str, dict] = {}
    counter = 0
    for row in ROWS:
        if row.module != "core" and row.module not in modules:
            continue
        lines.append(f"\n## {row.id} — {row.label} [{row.unit}]")
        taken = []
        for entry in legacy.get(row.id, [])[:3]:
            counter += 1
            key = f"o{counter}"
            snippet = _legacy_snippet(entry, every)
            src = entry["source"][:110]
            if not snippet:
                cache[key] = {"legacy": entry["value"], "document_id": "", "text": entry["value"]}
                lines.append(f"  {key} antiga (sem trecho localizável): {entry['value'][:160]}  ‹{src}›")
                continue
            doc = snippet["doc"]
            labels.setdefault(doc.id, f"D{len(labels) + 1}")
            cache[key] = {"document_id": doc.id, "left": snippet["left"], "right": snippet["right"], "start": snippet["start"], "legacy": entry["value"]}
            duplicate = any(doc.id == d.id and min(snippet["right"], r) - max(snippet["left"], l) > 0 for d, l, r in taken)
            taken.append((doc, snippet["left"], snippet["right"]))
            if duplicate:
                lines.append(f"  {key} antiga: {entry['value'][:160]}  (trecho já mostrado acima)")
                continue
            lines.append(f"  {key} antiga: {entry['value'][:160]}  ‹{src}›")
            lines.append(f"     [{labels[doc.id]} p{doc.page_at(snippet['start'])} {clause_at(doc, snippet['start'])}] {snippet['text'][:700]}")
        scope = issuance + regs if row.docs == "issuance" else regs
        limit = 1 if row.id in SHORT_ROWS else (2 if legacy.get(row.id) else 3)
        for item in candidates(row, scope, limit=limit, taken=taken):
            counter += 1
            key = f"c{counter}"
            doc = item["doc"]
            cache[key] = {"document_id": doc.id, "left": item["left"], "right": item["right"], "start": item["start"]}
            lines.append(f"  {key} [{labels[doc.id]} p{doc.page_at(item['start'])} {clause_at(doc, item['start'])}] {item['text']}")
    for doc in every.values():
        doc.release()
    work.mkdir(parents=True, exist_ok=True)
    (work / f"{cnpj}.json").write_text(json.dumps({"cnpj": cnpj, "labels": labels, "modules": sorted(modules), "candidates": cache}, ensure_ascii=False))
    return "\n".join(lines)


# Compile ----------------------------------------------------------------------

_EVIDENCE = re.compile(r"^(?:[co]\d+|q\d+)(?:\s*,\s*(?:[co]\d+|q\d+))*$")
STATUS_BY_DISPLAY = {"—": "not_applicable", "-": "not_applicable", "n/d": "nd"}


def _parse_facts(text: str) -> dict:
    out = {"rows": {}, "quotes": {}, "lookthrough": [], "type": "", "leitura": ""}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key == "type":
            out["type"] = rest
        elif key == "leitura":
            out["leitura"] = rest
        elif re.fullmatch(r"q\d+", key):
            # q1: D2 "exact passage from the document"
            m = re.match(r"((?:D|id)\d+|\*)\s+[\"“](.+)[\"”]\s*$", rest)
            if not m:
                raise ValueError(f"Citação mal formada: {line}")
            out["quotes"][key] = (m.group(1), m.group(2))
        elif key == "lookthrough":
            parts = [p.strip() for p in rest.split("|")]
            out["lookthrough"].append({"cnpj": digits(parts[0]), "subclass": parts[1] if len(parts) > 1 else "",
                                       "share": parts[2] if len(parts) > 2 else ""})
        elif key in ROW_BY_ID:
            parts = [p.strip() for p in rest.split(" | ")]
            fact = {"display": parts[0], "evidence": [], "reason": "", "extra": {}}
            for part in parts[1:]:
                if _EVIDENCE.match(part):
                    fact["evidence"] = [p.strip() for p in part.split(",")]
                elif re.match(r"^[a-z_]+=", part):
                    k, _, v = part.partition("=")
                    fact["extra"][k] = v
                else:
                    fact["reason"] = part
            out["rows"][key] = fact
        else:
            raise ValueError(f"Linha não reconhecida: {line}")
    return out


def _source(doc: Document, left: int, right: int, start: int, label: str) -> dict:
    return {"doc": label, "document_id": doc.id, "kind": doc.kind, "title": doc.title, "date": doc.display_date,
            "page": doc.page_at(start), "clause": clause_at(doc, start), "url": doc.url,
            "excerpt": _clean(doc.text[left:right])}


def compile_facts(cnpj: str, facts_path: Path, work: Path) -> dict:
    cnpj = digits(cnpj)
    cache = json.loads((work / f"{cnpj}.json").read_text())
    parsed = _parse_facts(facts_path.read_text(encoding="utf-8"))
    every = {d.id: d for d in documents(cnpj)}
    by_label = {label: every[doc_id] for doc_id, label in cache["labels"].items() if doc_id in every}
    issues: list[str] = []
    fund_type = parsed["type"]
    if fund_type not in FUND_TYPES:
        issues.append(f"Tipo de fundo fora da lista: {fund_type!r}")
    quotes = {}
    for key, (label, quote) in parsed["quotes"].items():
        words = re.findall(r"\S+", fold(quote))
        pattern = re.compile(r"\s+".join(re.escape(w) for w in words)) if words else None
        if label == "*":  # any labelled document, in label order
            label, doc, match = next(((lab, d, pattern.search(d.folded)) for lab, d in sorted(by_label.items(), key=lambda item: int(item[0][1:]))
                                      if pattern and pattern.search(d.folded)), ("*", None, None))
            if not doc:
                issues.append(f"{key}: citação não encontrada em nenhum documento")
                continue
        else:
            doc = every.get(label[2:]) if label.startswith("id") else by_label.get(label)
            if not doc:
                issues.append(f"{key}: documento {label} inexistente")
                continue
            match = pattern.search(doc.folded) if pattern else None
        if not match:
            issues.append(f"{key}: citação não encontrada em {label}")
            continue
        position = match.start()
        left = max(0, position - 120)
        right = min(len(doc.text), match.end() + 1100)
        stop = max(doc.text.rfind(". ", match.end(), right), doc.text.rfind(";", match.end(), right))
        if stop > match.end() + 300:
            right = stop + 1
        quotes[key] = _source(doc, left, right, position, label)
    legacy = legacy_answers(cnpj)
    facts: dict[str, dict] = {}
    for row in ROWS:
        if row.id == "fund_type":
            facts[row.id] = {"display": fund_type, "status": "confirmed", "unit": "enum", "reason": "Classificação pelo lastro e pela estrutura", "sources": []}
            continue
        applies = row_applies(row, fund_type)
        entry = parsed["rows"].get(row.id)
        if entry is None:
            if applies and row.module == "core":
                issues.append(f"{row.id}: linha obrigatória ausente")
            continue
        display = entry["display"]
        lowered = display.casefold()
        status = STATUS_BY_DISPLAY.get(lowered) or ("not_named" if lowered.startswith("não nomead") else
                                                    "absent" if re.match(r"^n[ãa]o previst", lowered) else "confirmed")
        sources = []
        for ref in entry["evidence"]:
            if ref.startswith("q"):
                if ref in quotes:
                    sources.append(quotes[ref])
                continue
            cand = cache["candidates"].get(ref)
            if not cand:
                issues.append(f"{row.id}: evidência {ref} inexistente")
                continue
            doc = every.get(cand.get("document_id", ""))
            if not doc:
                issues.append(f"{row.id}: {ref} sem documento local (resposta antiga sem fonte)")
                continue
            label = cache["labels"].get(doc.id, "")
            sources.append(_source(doc, cand["left"], cand["right"], cand["start"], label))
        reason = entry["reason"]
        problems = check_answer(row, display, status, sources, reason)
        issues.extend(f"{row.id}: {p}" for p in problems)
        fact = {"display": display, "status": status, "unit": row.unit, "reason": reason, "sources": sources}
        if entry["extra"].get("basis"):
            fact["basis"] = entry["extra"]["basis"]
        if row.numeric or row.ime:
            values = numbers_in(display)
            if entry["extra"].get("value") == "none":
                pass
            elif entry["extra"].get("value"):
                fact["value"] = float(entry["extra"]["value"].replace(",", "."))
            elif values and status == "confirmed":
                fact["value"] = values[0]
        old = legacy.get(row.id, [])
        if old:
            previous = old[0]["value"]
            decision = "kept"
            if status in {"nd"}:
                decision = "regression"
                if not entry["extra"].get("why"):
                    issues.append(f"{row.id}: resposta antiga '{previous[:60]}' virou n/d sem justificativa (why=)")
            else:
                old_numbers = set(numbers_in(previous))
                new_numbers = set(numbers_in(display))
                if old_numbers and not old_numbers <= new_numbers:
                    decision = "revised"
            fact["legacy"] = {"value": previous, "decision": decision, "why": entry["extra"].get("why", "")}
            if decision == "revised" and sources:
                src = sources[0]
                fact["legacy"]["why"] = fact["legacy"]["why"] or f"Texto integral prevalece: {src['kind']} {src['date']}, {src['clause'] or 'p. ' + str(src['page'])}"
        elif status == "confirmed":
            fact["legacy"] = {"value": "", "decision": "new"}
        facts[row.id] = fact
    for row in ROWS:
        if row.id not in facts and row.module != "core" and row_applies(row, fund_type):
            issues.append(f"{row.id}: módulo aplicável ao tipo {fund_type} sem resposta")
    leitura = parsed["leitura"]
    if not leitura or len(leitura) > 140:
        issues.append("leitura de crédito ausente ou acima de 140 caracteres")
    shown = " ".join(f["display"] for f in facts.values())
    loose = [n for n in numbers_in(leitura) if not any(abs(n - v) < 1e-6 * max(1, abs(v)) for v in numbers_in(shown))]
    if loose:
        issues.append("leitura com número que não está nos fatos: " + ", ".join(f"{n:g}" for n in loose))
    if fund_type == "FIC" and not parsed["lookthrough"]:
        issues.append("FIC sem look-through")
    labels = {label: doc_id for doc_id, label in cache["labels"].items()}
    payload = {
        "schema_version": 1, "cnpj": cnpj, "name": _fund_name(cnpj), "fund_type": fund_type,
        "reviewed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reader": "Leitura documental assistida (Claude), validada por fonte",
        "documents": {label: {"document_id": doc_id, "kind": every[doc_id].kind, "title": every[doc_id].title,
                              "date": every[doc_id].display_date, "url": every[doc_id].url}
                      for label, doc_id in labels.items() if doc_id in every},
        "facts": facts, "leitura": leitura, "lookthrough": parsed["lookthrough"],
        "validation": {"approved": not issues, "issues": issues},
    }
    for doc in every.values():
        doc.release()
    return payload


def search(cnpj: str, pattern: str, work: Path, *, every_doc: bool = False, limit: int = 8, width: int = 380) -> str:
    cnpj = digits(cnpj)
    cache_path = work / f"{cnpj}.json"
    labels = json.loads(cache_path.read_text())["labels"] if cache_path.exists() else {}
    regs, issuance = current_documents(cnpj)
    docs = documents(cnpj) if every_doc else [*regs, *issuance]
    compiled = _compile(fold(pattern))
    out = []
    for doc in docs:
        for match in compiled.finditer(doc.folded):
            label = labels.get(doc.id) or f"id{doc.id}"
            out.append(f"[{label} {doc.kind} {doc.display_date} p{doc.page_at(match.start())} {clause_at(doc, match.start())}] "
                       + _clean(doc.text[max(0, match.start() - width // 3):match.end() + width]))
            if len(out) >= limit:
                return "\n".join(out)
    return "\n".join(out) or "(sem ocorrências)"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["dossier", "compile", "search"])
    parser.add_argument("cnpj")
    parser.add_argument("facts", nargs="?")
    parser.add_argument("--work", default=str(DEFAULT_WORK))
    parser.add_argument("--force", action="store_true", help="grava mesmo com pendências de validação")
    parser.add_argument("--all", action="store_true", help="search: todos os documentos do fundo")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--width", type=int, default=380)
    args = parser.parse_args()
    work = Path(args.work)
    if args.command == "dossier":
        print(build_dossier(args.cnpj, work))
        return
    if args.command == "search":
        print(search(args.cnpj, args.facts, work, every_doc=args.all, limit=args.limit, width=args.width))
        return
    payload = compile_facts(args.cnpj, Path(args.facts), work)
    issues = payload["validation"]["issues"]
    if issues and not args.force:
        print("REPROVADO:\n- " + "\n- ".join(issues))
        sys.exit(1)
    FACTS_DIR.mkdir(parents=True, exist_ok=True)
    (FACTS_DIR / f"{digits(args.cnpj)}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    print(("APROVADO" if not issues else "GRAVADO COM PENDÊNCIAS") + f": {len(payload['facts'])} fatos · tipo {payload['fund_type']}")
    if issues:
        print("- " + "\n- ".join(issues))


if __name__ == "__main__":
    main()
