"""Find primary-source routes from local evidence and probe headers serially.

This script writes an independent search registry; it never downloads documents
or changes a corpus checkpoint being used by the acquisition worker.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.documentary_corpus import atomic_json, load_registered_funds, utc_now
from services.documentary_diligence import public_document_payload


PRIMARY_DOMAINS = {
    "btgpactual.com": "administrator", "btgpactualdigital.com": "administrator",
    "oliveiratrust.com.br": "administrator", "vortx.com.br": "administrator", "kanastra.com.br": "administrator",
    "genialinvestimentos.com.br": "administrator", "bancogenial.com.br": "administrator", "daycoval.com.br": "administrator",
    "singulare.com.br": "administrator", "tercon.com.br": "administrator", "brltrust.com.br": "administrator",
    "bny.com": "administrator", "bny.com.br": "administrator", "bnymellon.com.br": "administrator",
    "itau.com.br": "administrator", "itau.com": "administrator", "bradesco.com.br": "administrator",
    "santander.com.br": "administrator", "pentagonotrustee.com.br": "administrator",
    "angaasset.com.br": "manager", "jgp.com.br": "manager", "creditas.com.br": "originator",
    "austin.com.br": "rating_agency", "liberumratings.com.br": "rating_agency", "fitchratings.com": "rating_agency",
    "moodyslocal.com.br": "rating_agency", "moodyslocal.com": "rating_agency", "moodys.com": "rating_agency",
    "spglobal.com": "rating_agency", "srating.com.br": "rating_agency", "srap.com.br": "rating_agency",
    "anbima.com.br": "industry_association", "cvm.gov.br": "regulator", "gov.br": "regulator",
    "b3.com.br": "exchange", "fnet.bmfbovespa.com.br": "fundosnet",
}
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"'{}\[\]]+|(?<![@\w])(?:[\w-]+\.)+[a-z]{2,}(?:/[^\s<>\"'{}\[\]]*)?", re.IGNORECASE)
DOC_URL_RE = re.compile(r"\.(?:pdf|docx?|zip)(?:$|[?#])|regulament|rating|lastro|demonstra|prospect|suplement|emissao|assembleia", re.IGNORECASE)


def normalized_url(raw: str) -> str:
    raw = raw.rstrip(".,;:)»›")
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or "@" in parsed.netloc:
        return ""
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def source_type(url: str) -> str:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    for domain, kind in PRIMARY_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return kind
    return "unverified_domain"


def candidate_document_type(url: str) -> str:
    text = urllib.parse.unquote(url).casefold()
    for kind, keywords in [("regulamento", ("regulament",)), ("anexo", ("anexo", "apendice", "apêndice")),
                           ("rating", ("rating",)), ("lastro", ("lastro",)),
                           ("demonstracoes_financeiras", ("demonstra", "balanco", "balanço", "audit")),
                           ("emissao", ("emissao", "emissão", "prospect", "suplement", "oferta")),
                           ("assembleia", ("assembleia", "ata-", "ata_"))]:
        if any(word in text for word in keywords):
            return kind
    return "document_unknown" if DOC_URL_RE.search(text) else "portal"


def iter_text_pages(path: Path) -> Iterable[tuple[int, str]]:
    """Bound each page buffer and keep physical page numbers from verified text."""
    with path.open(encoding="utf-8", errors="replace") as handle:
        pending, number = "", 1
        for chunk in iter(lambda: handle.read(64 * 1024), ""):
            pending += chunk
            while "\f" in pending:
                content, pending = pending.split("\f", 1)
                yield number, content
                number += 1
            if len(pending) > 2 * 1024**2:
                pending = pending[-8192:]
        if pending.strip():
            yield number, pending


def discover_routes(cnpj: str, corpus: dict[str, Any], seeds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    routes: dict[str, dict[str, Any]] = {}
    scanned = set()
    for doc in corpus.get("documents", []):
        if doc.get("classification") not in {"regulamento", "anexo", "demonstracoes_financeiras", "rating", "lastro"}:
            continue
        if doc.get("parse_status") != "complete" or not doc.get("text_path"):
            continue
        path = Path(doc["text_path"])
        if str(path) in scanned or not path.exists():
            continue
        scanned.add(str(path))
        for page, text in iter_text_pages(path):
            for match in URL_RE.finditer(text):
                url = normalized_url(match.group())
                kind = source_type(url)
                if not url or kind == "fundosnet" or kind == "unverified_domain":
                    continue
                nearby = text[max(0, match.start() - 200):match.end() + 200]
                route = routes.setdefault(url, {"url": url, "source_type": kind, "candidate_type": candidate_document_type(url),
                                               "identity_status": "fund_corpus_route_requires_target_document_validation", "evidence": [],
                                               "probe": {"status": "not_probed", "queried_at": None, "error": ""}})
                evidence = {"document_id": doc.get("id"), "reference_date": doc.get("reference_date"), "page": page,
                            "source_url": doc.get("url"), "text_path": str(path), "source_excerpt": nearby.strip()}
                if evidence not in route["evidence"] and len(route["evidence"]) < 5:
                    route["evidence"].append(evidence)
    for seed in seeds:
        if seed.get("cnpj") != cnpj:
            continue
        url = normalized_url(seed["url"])
        route = routes.setdefault(url, {"url": url, "source_type": source_type(url), "candidate_type": candidate_document_type(url),
                                        "identity_status": seed.get("identity_status", "candidate_requires_cnpj_validation"),
                                        "evidence": [], "probe": {"status": "not_probed", "queried_at": None, "error": ""}})
        route["evidence"].append({"source": "documented_web_search", "query": seed.get("query"), "source_url": seed.get("source_url", url),
                                  "entity_validation": seed.get("entity_validation"), "searched_at": seed.get("searched_at")})
    return list(routes.values())


class PrimaryRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if source_type(newurl) == "unverified_domain":
            raise urllib.error.HTTPError(newurl, code, "Redirect to unverified domain; provenance validation required", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def probe_headers(url: str, timeout: int = 8) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "error", "method": "HEAD", "queried_at": utc_now(), "error": ""}
    if source_type(url) == "unverified_domain":
        return {**result, "status": "not_probed_unverified_domain", "error": "primary_origin_not_validated"}
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0 DocumentaryEvidenceIndex/1.0"})
    try:
        with urllib.request.build_opener(PrimaryRedirectHandler()).open(request, timeout=timeout) as response:
            mime = response.headers.get("Content-Type", "").split(";", 1)[0]
            result.update(status="reachable_candidate_document" if mime in {"application/pdf", "application/zip"} else "portal_reachable",
                          http_status=response.status, mime_type=mime, content_length=response.headers.get("Content-Length"),
                          final_url=response.url, error="", identity_validation="not_performed_by_head")
    except urllib.error.HTTPError as exc:
        result.update(status="blocked" if exc.code in {401, 403, 429} else "head_unsupported" if exc.code == 405 else "not_found" if exc.code == 404 else "http_error",
                      http_status=exc.code, error=str(exc))
    except (OSError, ValueError, TimeoutError) as exc:
        result.update(status="error", error=f"{type(exc).__name__}: {exc}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--all", action="store_true")
    selector.add_argument("--only-cnpj", action="append", default=[])
    parser.add_argument("--probe", action="store_true", help="HEAD serial de URLs primárias; não baixa documentos")
    parser.add_argument("--max-probes", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=8)
    parser.add_argument("--seeds", type=Path)
    args = parser.parse_args()
    if args.timeout_seconds < 1 or args.max_probes < 0:
        parser.error("Timeout deve ser positivo e max-probes não negativo")
    funds = load_registered_funds(args.root / "portfolios.json")
    selected = sorted(funds) if args.all else [re.sub(r"\D", "", cnpj) for cnpj in args.only_cnpj]
    seed_payload = json.loads(args.seeds.read_text()) if args.seeds else {}
    seeds = seed_payload.get("candidates", [])
    registry = args.root / "data/documentary_diligence/source_routes"
    snapshots = []
    for cnpj in selected:
        checkpoint = args.root / "data/documentary_diligence/corpus" / f"{cnpj}.json"
        corpus = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        regulatory_complete = any(doc.get("classification") in {"regulamento", "anexo"} and doc.get("parse_status") == "complete" for doc in corpus.get("documents", []))
        routes = discover_routes(cnpj, corpus, seeds)
        snapshots.append({"schema_version": 1, "cnpj": cnpj, "name": funds.get(cnpj, {}).get("name"), "generated_at": utc_now(),
                          "priority": "no_complete_regulatory_document" if not regulatory_complete else "complementary_sources",
                          "corpus_snapshot_at": corpus.get("generated_at"), "routes": routes,
                          "status": "routes_found" if routes else "no_primary_route_in_local_evidence",
                          "note": "Portal accessibility is not document acquisition; HEAD does not validate issuer/CNPJ or version."})
    cache, probes = {}, 0
    for snapshot in sorted(snapshots, key=lambda row: row["priority"] != "no_complete_regulatory_document"):
        for route in sorted(snapshot["routes"], key=lambda row: row["candidate_type"] == "portal"):
            url = route["url"]
            if url in cache:
                route["probe"] = cache[url]
            elif args.probe and probes < args.max_probes:
                route["probe"] = cache[url] = probe_headers(url, args.timeout_seconds)
                probes += 1
            elif args.probe:
                route["probe"]["status"] = "probe_budget_reached"
        atomic_json(registry / f"{snapshot['cnpj']}.json", public_document_payload(snapshot))
    summary = {"generated_at": utc_now(), "cnpjs": len(snapshots), "funds_with_routes": sum(bool(row["routes"]) for row in snapshots),
               "funds_without_complete_regulatory_document": sum(row["priority"] == "no_complete_regulatory_document" for row in snapshots),
               "routes": sum(len(row["routes"]) for row in snapshots), "unique_urls_probed": probes,
               "probe_states": dict(Counter(route["probe"]["status"] for row in snapshots for route in row["routes"])),
               "web_searches": seed_payload.get("searches", []), "no_document_downloads": True}
    atomic_json(registry / "summary.json", public_document_payload(summary))
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
