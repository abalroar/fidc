"""Serial documentary acquisition with bounded memory and explicit evidence states.

The corpus indexes documents and parsing outcomes. It never turns legacy regex
extractions, CNPJ mentions or availability flags into contractual conclusions.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, BinaryIO, Iterable
import urllib.request
from urllib.parse import urlparse

from services.fundonet_client import FundosNetClient
from services.regulatory_knowledge import classify_document, normalize_cnpj


SCHEMA_VERSION = 1
CHUNK_SIZE = 64 * 1024
CNPJ_RE = re.compile(r"(?<!\d)(?:\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14})(?!\d)")
DOC_ID_RE = re.compile(r"^(?:\d{14}_)?(\d{5,10})(?:_|\.|$)")
PRIORITY = {"regulamento": 0, "anexo": 1, "emissao": 2, "assembleia": 3,
            "rating": 4, "lastro": 5, "demonstracoes_financeiras": 6, "evento": 7, "outro": 8}
DOWNLOADABLE = frozenset(PRIORITY)
TEXT_CACHE_FIELDS = ("text_path", "parse_method", "parse_quality", "ocr_quality", "ocr_excluded_pages",
                     "original_text_map_status", "original_parse_quality")
SKIP_DIRS = {".git", ".venv", "node_modules", "worktrees", "__pycache__", "pdfdeps"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def load_registered_funds(path: Path) -> dict[str, dict[str, Any]]:
    """Deduplicate by exact CNPJ while retaining every saved portfolio membership."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    portfolios = payload.get("portfolios", []) if isinstance(payload, dict) else payload
    funds: dict[str, dict[str, Any]] = {}
    for portfolio in portfolios:
        for fund in portfolio.get("funds", []):
            cnpj = normalize_cnpj(fund.get("cnpj", ""))
            if len(cnpj) != 14:
                raise ValueError(f"CNPJ inválido na carteira {portfolio.get('id')}: {fund.get('cnpj')}")
            item = funds.setdefault(cnpj, {"cnpj": cnpj, "name": fund.get("display_name", cnpj), "portfolios": []})
            member = {"id": portfolio.get("id"), "name": portfolio.get("name")}
            if member not in item["portfolios"]:
                item["portfolios"].append(member)
    return funds


def corpus_classification(row: dict[str, Any], filename: str = "") -> str:
    text = " ".join(str(row.get(key) or "") for key in ("classification", "categoria", "tipo", "especie", "title", "nome_arquivo")) + " " + filename
    folded = text.casefold()
    if any(word in folded for word in ("lastro", "verificação dos direitos", "verificacao dos direitos")):
        return "lastro"
    if any(word in folded for word in ("anexo", "apêndice", "apendice", "complemento")) and "regulamento" in folded:
        return "anexo"
    classification = classify_document(categoria=text)
    declared = str(row.get("classification") or "")
    if classification == "outro" and declared in DOWNLOADABLE:
        return declared
    return classification


def document_url(document_id: int | str | None) -> str:
    return f"https://fnet.bmfbovespa.com.br/fnet/publico/visualizarDocumento?id={document_id}" if document_id else ""


def document_date_key(value: object) -> datetime:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%m/%Y"):
        try:
            return datetime.strptime(text[:19] if "T" in fmt else text, fmt)
        except ValueError:
            continue
    return datetime.min


def numeric_document_id(value: object) -> int:
    text = str(value or "")
    return int(text) if text.isdigit() else 0


def file_catalog_metadata(document: dict[str, Any]) -> dict[str, Any]:
    return {key: document.get(key) for key in ("version", "reference_date", "delivery_date")}


def changed_catalog_metadata(previous: dict[str, Any], observed: dict[str, Any]) -> list[str]:
    """Equivalent date formatting is not a new version; unknown dates stay unknown."""
    baseline = previous.get("file_catalog_metadata") or file_catalog_metadata(previous)
    changed = []
    for key in ("version", "reference_date", "delivery_date"):
        old, new = baseline.get(key), observed.get(key)
        if old in (None, "") or new in (None, ""):
            continue
        if key == "reference_date" and previous.get("reference_date_provenance") == "filename_unverified":
            continue
        if key == "version":
            equivalent = str(old).strip() == str(new).strip()
        else:
            old_date, new_date = document_date_key(old), document_date_key(new)
            equivalent = old_date == new_date if old_date != datetime.min and new_date != datetime.min else str(old).strip() == str(new).strip()
        if not equivalent:
            changed.append(key)
    return changed


def clear_text_cache(document: dict[str, Any]) -> None:
    for field in TEXT_CACHE_FIELDS:
        document.pop(field, None)
    document.update(parse_status="not_parsed", pages_total=None, pages_extracted=None)


def mark_catalog_file_conflict(document: dict[str, Any], previous: dict[str, Any]) -> bool:
    changed = changed_catalog_metadata(previous, document)
    if not changed:
        document["file_catalog_metadata"] = previous.get("file_catalog_metadata") or file_catalog_metadata(document)
        return False
    document.update(file_catalog_metadata=previous.get("file_catalog_metadata") or file_catalog_metadata(previous),
                    catalog_file_binding="conflict", catalog_changed_fields=changed,
                    parse_status="catalog_version_conflict", download_status="cached_version_conflict",
                    error="catalog_metadata_changed_since_pdf_acquisition")
    return True


def current_document_ids(documents: list[dict[str, Any]]) -> set[str]:
    """Select consolidated regulations, latest class annexes and subsequent amendments.

    This is an acquisition order, not a legal assertion about which clause wins.
    Every historical ID remains in the inventory for the history pass.
    """
    def active(doc: dict[str, Any]) -> int:
        return int(str(doc.get("provider_status") or "").upper().startswith("A"))

    def order(doc: dict[str, Any]) -> tuple[Any, ...]:
        return (active(doc), document_date_key(doc.get("reference_date")), document_date_key(doc.get("delivery_date")),
                int(doc.get("version") or 0), numeric_document_id(doc.get("id")))

    def amendment(doc: dict[str, Any]) -> bool:
        text = " ".join(str(doc.get(field) or "") for field in ("title", "category", "document_type")).casefold()
        return any(term in text for term in ("alteração do regulamento", "alteracao do regulamento", "alteração de regulamento",
                                             "alteracao de regulamento", "aditamento", "instrumento de alteração", "instrumento de alteracao"))

    regulations = [doc for doc in documents if doc.get("classification") == "regulamento"]
    consolidated = [doc for doc in regulations if not amendment(doc)]
    selected: list[dict[str, Any]] = []
    if consolidated:
        selected.append(max(consolidated, key=order))
    elif regulations:
        # Inventory may contain only amendment records. Acquire the best candidate,
        # retaining its role so it cannot be mistaken for a complete consolidated regulation.
        selected.append(max(regulations, key=order))
    annex_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in documents:
        if doc.get("classification") == "anexo":
            scope = " ".join(str(doc.get("fund_or_class_name") or doc.get("scope") or "unspecified_class").casefold().split())
            annex_groups[scope].append(doc)
    selected.extend(max(group, key=order) for group in annex_groups.values())
    if selected:
        base_date = min(document_date_key(doc.get("reference_date")) for doc in selected)
        active_available = any(active(doc) for doc in regulations)
        selected.extend(doc for doc in regulations if amendment(doc) and document_date_key(doc.get("reference_date")) >= base_date
                        and (active(doc) or not active_available))
    return {str(doc["id"]) for doc in selected if doc.get("id")}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_stats(path: Path) -> tuple[int, int]:
    """Return explicit page separators and visible text bytes without loading the file."""
    pages, visible = 0, 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            pages += chunk.count(b"\f")
            visible += len(chunk.strip())
    return pages, visible


def text_extraction_quality(path: Path) -> dict[str, Any]:
    """Detect strong character-map corruption with bounded streaming counters.

    No warning is not a certificate of readability. Page recovery and character
    quality remain separate measurements; this guard does not interpret clauses.
    """
    characters, controls, extended, replacements = 0, 0, 0, 0
    with path.open(encoding="utf-8", errors="replace") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), ""):
            characters += len(chunk)
            controls += len(re.findall(r"[\x00-\x08\x0b\x0e-\x1f\x7f]", chunk))
            extended += len(re.findall(r"[\u0100-\u024f]", chunk))
            replacements += chunk.count("\ufffd")
    control_ratio = controls / characters if characters else 0
    extended_ratio = extended / characters if characters else 0
    replacement_ratio = replacements / characters if characters else 0
    corruption = characters >= 1000 and ((control_ratio >= .02 and extended_ratio >= .10) or replacement_ratio >= .03)
    return {"status": "encoding_suspect" if corruption else "no_strong_encoding_warning",
            "characters": characters, "unexpected_controls": controls,
            "latin_extended_characters": extended, "replacement_characters": replacements,
            "control_ratio": round(control_ratio, 6), "latin_extended_ratio": round(extended_ratio, 6),
            "replacement_ratio": round(replacement_ratio, 6),
            "measurement": "full text streamed once; controls with LatinExtended, or replacement-character prevalence"}


def managed_repository_source(root: Path) -> Path | None:
    """Read the shared repository location only for a real managed Git worktree."""
    git_file = root / ".git"
    if not git_file.is_file():
        return None
    try:
        text = git_file.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir:"):
            return None
        git_directory = (root / text.partition(":")[2].strip()).resolve()
        common_file = git_directory / "commondir"
        if not common_file.is_file():
            return None
        common = (git_directory / common_file.read_text(encoding="utf-8").strip()).resolve()
        return common.parent if common.is_dir() and common.name == ".git" else None
    except (OSError, ValueError):
        return None


@dataclass
class ResourceLimits:
    disk_floor_bytes: int = 10 * 1024**3
    max_download_bytes: int = 2 * 1024**3
    max_document_bytes: int = 100 * 1024**2
    parse_timeout_seconds: int = 45
    network_timeout_seconds: int = 20
    attempts: int = 2


class ResourceLimitError(RuntimeError):
    pass


class DocumentaryCorpus:
    def __init__(self, root: Path, source_roots: Iterable[Path] = (), *, limits: ResourceLimits | None = None,
                 client: FundosNetClient | None = None) -> None:
        self.root = root.resolve()
        candidates = [self.root, *source_roots]
        managed_source = managed_repository_source(self.root)
        if managed_source:
            candidates.append(managed_source)
        self.source_roots = tuple(dict.fromkeys(path.resolve() for path in candidates if path.exists()))
        self.limits = limits or ResourceLimits()
        self.client = client
        self.downloaded_bytes = 0
        self.base = self.root / "data/documentary_diligence"
        self.paths: dict[str, list[Path]] = defaultdict(list)
        self.metadata_paths: dict[str, list[Path]] = defaultdict(list)
        self._prepared: set[str] = set()
        self._hash_cache: dict[tuple[str, int, int], str] = {}

    def prepare(self, cnpjs: Iterable[str]) -> None:
        """Scan bounded corpus locations once; excluded worktrees avoid recursive copies."""
        wanted = {normalize_cnpj(cnpj) for cnpj in cnpjs} - self._prepared
        if not wanted:
            return
        for source_root in self.source_roots:
            locations = [source_root / "data/raw", source_root / "data/documentary_diligence/raw", source_root / "data/regulatory_extractions",
                         source_root / "data/regulatory_knowledge", source_root / "data/regulatory_profiles/documentary_comparisons",
                         source_root / "outputs/fidc_director_deep_diagnostic_20260609/pdf_text_cache",
                         source_root / ".cache"]
            for location in locations:
                if not location.exists():
                    continue
                for directory, subdirs, files in os.walk(location):
                    subdirs[:] = [name for name in subdirs if name not in SKIP_DIRS]
                    for name in files:
                        suffix = Path(name).suffix.lower()
                        if suffix not in {".pdf", ".txt", ".json"}:
                            continue
                        path = Path(directory) / name
                        matches = {normalize_cnpj(m.group()) for m in CNPJ_RE.finditer(str(path.relative_to(source_root)))} & wanted
                        if not matches:
                            continue
                        for cnpj in matches:
                            bucket = self.metadata_paths if suffix == ".json" else self.paths
                            if path not in bucket[cnpj]:
                                bucket[cnpj].append(path)
        self._prepared.update(wanted)

    def _read_metadata(self, cnpj: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        docs: dict[str, dict[str, Any]] = {}
        searches, relationships = [], []
        for path in self.metadata_paths.get(cnpj, []):
            try:
                if path.stat().st_size > 20 * 1024**2:
                    raise ValueError("metadata_size_limit")
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue
                rows = payload.get("documents", []) + payload.get("sources_reviewed", [])
                inventory = payload.get("documentary_inventory_review", {})
                if isinstance(inventory, dict):
                    rows += inventory.get("documents", []) + inventory.get("sources_reviewed", [])
                if payload.get("document_id") and ("source_file" in payload or "classification" in payload):
                    rows.append(payload)
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    document_id = row.get("document_id") or row.get("id")
                    if not str(document_id or "").isdigit():
                        continue
                    key = str(document_id)
                    item = docs.setdefault(key, self._blank_document(int(document_id)))
                    incoming_classification = corpus_classification(row, str(row.get("source_file") or row.get("path") or ""))
                    if incoming_classification != "outro" or item["classification"] == "outro":
                        item["classification"] = incoming_classification
                    for output, keys in {"title": ("title", "nome_arquivo", "tipo", "categoria"),
                                         "reference_date": ("reference_date", "data_referencia", "date"),
                                         "delivery_date": ("delivery_date", "data_entrega"), "version": ("version", "versao"),
                                         "provider_status": ("provider_status", "status"), "scope": ("scope", "fundo_ou_classe"),
                                         "fund_or_class_name": ("fund_or_class_name", "nome_fundo"),
                                         "category": ("category", "categoria"), "document_type": ("document_type", "tipo")}.items():
                        value = next((row[k] for k in keys if row.get(k) not in (None, "")), None)
                        if value is not None:
                            item[output] = value
                    item.setdefault("inventory_sources", []).append(str(path))
                    if row.get("extraction_error"):
                        item["historical_parse_error"] = row["extraction_error"]
                    if row.get("criteria"):
                        item["legacy_extraction_path"] = str(path)
                    for field in ("source_file", "path", "text_path"):
                        if not row.get(field):
                            continue
                        local = Path(row[field])
                        if not local.is_absolute():
                            local = next((root / local for root in self.source_roots if (root / local).exists()), path.parents[0] / local)
                        if local.exists() and local.suffix.lower() in {".pdf", ".txt"} and local not in self.paths[cnpj]:
                            self.paths[cnpj].append(local)
                for theme, facts in payload.get("facts", {}).items():
                    if not isinstance(facts, dict):
                        continue
                    for criterion, fact in facts.items():
                        if not isinstance(fact, dict):
                            continue
                        value = str(fact.get("value") or "")
                        context = (criterion + " " + value).casefold()
                        if not any(word in context for word in ("investid", "fic-fidc", "ficfidc", "cotas de", "cotas do")):
                            continue
                        for mention in CNPJ_RE.finditer(value):
                            target = normalize_cnpj(mention.group())
                            if target != cnpj:
                                candidate = {"investor_cnpj": cnpj, "candidate_cnpj": target,
                                             "status": "candidate_requires_primary_validation", "criterion": criterion,
                                             "value": value, "source_reference": str(fact.get("source") or ""),
                                             "review_path": str(path)}
                                if candidate not in relationships:
                                    relationships.append(candidate)
                searches.append({"source": "local_metadata", "url": str(path), "queried_at": utc_now(), "status": "indexed", "error": ""})
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                searches.append({"source": "local_metadata", "url": str(path), "queried_at": utc_now(), "status": "error", "error": str(exc)})
        return docs, searches, relationships

    @staticmethod
    def _blank_document(document_id: int | None) -> dict[str, Any]:
        return {"id": document_id, "classification": "outro", "title": "", "reference_date": None,
                "delivery_date": None, "version": None, "url": document_url(document_id),
                "local_path": "", "text_path": "", "sha256": "", "download_status": "inventory_only",
                "parse_status": "not_downloaded", "pages_total": None, "pages_extracted": None, "error": ""}

    def _room(self, required: int = 0, *, download: bool = False) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.base).free - required < self.limits.disk_floor_bytes:
            raise ResourceLimitError("disk_floor_reached")
        if download and self.downloaded_bytes + required > self.limits.max_download_bytes:
            raise ResourceLimitError("download_budget_reached")

    def _hash(self, path: Path) -> str:
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        if key not in self._hash_cache:
            self._hash_cache[key] = sha256_file(path)
        return self._hash_cache[key]

    def _parse(self, cnpj: str, item: dict[str, Any], *, resume: bool) -> None:
        if item.get("catalog_file_binding") == "conflict":
            item.update(parse_status="catalog_version_conflict", error="catalog_metadata_changed_since_pdf_acquisition")
            return
        pdf = Path(item["local_path"])
        if not pdf.exists():
            item.update(parse_status="not_downloaded", error="referenced_file_missing")
            return
        if not shutil.which("pdfinfo") or not shutil.which("pdftotext"):
            item.update(parse_status="parser_unavailable", error="pdfinfo_or_pdftotext_unavailable")
            return
        temporary: Path | None = None
        try:
            with pdf.open("rb") as handle:
                if not handle.read(8).startswith(b"%PDF-"):
                    raise ValueError("invalid_pdf_magic")
            info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=self.limits.parse_timeout_seconds)
            match = re.search(r"^Pages:\s+(\d+)", info.stdout, re.MULTILINE)
            if info.returncode or not match:
                raise ValueError("pdfinfo_failed: " + info.stderr[:300])
            total = int(match.group(1))
            item["pages_total"] = total
            # One full text per content hash, including documents shared by multiple classes.
            target = self.base / "text" / item["sha256"][:2] / (item["sha256"] + ".txt")
            existing = Path(item.get("text_path") or target)
            if resume:
                for candidate in dict.fromkeys((existing, target)):
                    if not candidate.exists():
                        continue
                    pages, visible = text_stats(candidate)
                    if pages == total and visible:
                        quality = text_extraction_quality(candidate)
                        unreadable = quality["status"] == "encoding_suspect"
                        ocr_partial = item.get("parse_method") in {"vision_ocr", "apple_vision_ocr"} and bool(item.get("ocr_excluded_pages"))
                        if item.get("parse_method") in {"vision_ocr", "apple_vision_ocr"}:
                            ocr_quality = dict(item.get("ocr_quality") or {})
                            if ocr_quality.get("source_sha256") not in (None, item.get("sha256")):
                                clear_text_cache(item)
                                break
                            ocr_quality.update(source_sha256=item.get("sha256"), source_catalog_metadata=item.get("file_catalog_metadata") or file_catalog_metadata(item))
                            item["ocr_quality"] = ocr_quality
                        item.update(text_path=str(candidate), pages_extracted=pages, parse_quality=quality,
                                    parse_status="unreadable_text" if unreadable else "partial" if ocr_partial else "complete",
                                    error="text_character_map_corruption" if unreadable else "ocr_pages_below_confidence" if ocr_partial else "")
                        return
            self._room(min(pdf.stat().st_size * 4, 100 * 1024**2))
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
            os.close(fd)
            temporary = Path(name)
            result = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), str(temporary)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                    timeout=self.limits.parse_timeout_seconds)
            if result.returncode:
                raise ValueError("pdftotext_failed: " + result.stderr[:300])
            pages, visible = text_stats(temporary)
            quality = text_extraction_quality(temporary)
            os.replace(temporary, target)
            unreadable = quality["status"] == "encoding_suspect"
            item.update(text_path=str(target), pages_extracted=pages, parse_quality=quality,
                        parse_status="no_text" if not visible else "unreadable_text" if unreadable else "complete" if pages == total else "partial",
                        error="no_extractable_text" if not visible else "text_character_map_corruption" if unreadable else "" if pages == total else "page_count_mismatch")
        except ResourceLimitError as exc:
            item.update(parse_status="resource_limit", error=str(exc))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            item.update(parse_status="error", error=str(exc))
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def _discover_local(self, cnpj: str, docs: dict[str, dict[str, Any]], previous: dict[str, Any], *, resume: bool) -> list[dict[str, Any]]:
        previous_records = [record for document in previous.get("documents", []) for record in (document, *(document.get("local_versions") or []))]
        previous_by_hash = {(str(d.get("id")), d.get("sha256")): d for d in previous_records if d.get("sha256")}
        previous_by_id = {str(d.get("id")): d for d in previous.get("documents", []) if d.get("id")}
        previous_by_path = {str(Path(d['local_path']).resolve()): d for d in previous.get('documents', []) if d.get('local_path') and d.get('id')}
        previous_identified_hash = {d['sha256']: d for d in previous.get('documents', []) if d.get('sha256') and d.get('id')}
        pdfs, texts = [], {}
        for path in self.paths.get(cnpj, []):
            match = DOC_ID_RE.match(path.name)
            document_id = match.group(1) if match else ""
            if path.suffix.lower() == ".txt":
                if document_id:
                    texts.setdefault(document_id, path)
                continue
            if path.suffix.lower() == ".pdf":
                pdfs.append((path, document_id))
        versions: dict[tuple[str, str], dict[str, Any]] = {}
        for path, key in pdfs:
            try:
                digest = self._hash(path)
            except OSError:
                continue
            if not key:
                identified = previous_by_path.get(str(path.resolve())) or previous_identified_hash.get(digest)
                if identified:
                    key = str(identified['id'])
            identity = (key, digest)
            if identity in versions:
                versions[identity].setdefault("local_sources", []).append(str(path))
                continue
            item = dict(docs.get(key) or previous_by_id.get(key) or self._blank_document(int(key) if key else None))
            cached = previous_by_hash.get((key, digest), {})
            if cached:
                for field in ("text_path", "parse_status", "pages_total", "pages_extracted", "parse_method", "parse_quality", "ocr_quality", "ocr_excluded_pages", "original_text_map_status", "original_parse_quality"):
                    item[field] = cached.get(field, item.get(field))
            elif previous_by_id.get(key, {}).get("sha256") not in (None, "", digest):
                clear_text_cache(item)
            item.update(local_path=str(path), sha256=digest, download_status="local_available", error="")
            if item["classification"] == "outro":
                item["classification"] = corpus_classification({}, path.name)
            if not item["title"]:
                item["title"] = path.name
            if not item["reference_date"]:
                dated = re.search(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)", path.name)
                if dated:
                    item["reference_date"] = dated.group(1)
                    item["reference_date_provenance"] = "filename_unverified"
            if not item.get("text_path") and key in texts:
                item["text_path"] = str(texts[key])
            item["local_sources"] = [str(path)]
            versions[identity] = item
            if cached and mark_catalog_file_conflict(item, cached):
                continue
            # IME is inventoried, but acquisition/parsing is delegated to its own data pipeline.
            if item["classification"] == "informe_mensal":
                item["parse_status"] = "not_applicable_ime_pipeline"
            else:
                self._parse(cnpj, item, resume=resume)
        seen_ids = {key for key, _ in versions if key}
        for key, doc in docs.items():
            if key in seen_ids:
                continue
            if doc["classification"] == "informe_mensal":
                doc.update(download_status="excluded_ime_pipeline", parse_status="not_applicable_ime_pipeline")
                versions[(key, "")] = doc
                continue
            previous_doc = previous_by_id.get(key, {})
            if previous_doc.get("local_path") and Path(previous_doc["local_path"]).exists():
                item = {**previous_doc, **doc}
                for field in ("local_path", "sha256", "text_path", "parse_status", "pages_total", "pages_extracted", "download_status", "parse_method", "parse_quality", "ocr_quality", "ocr_excluded_pages", "original_text_map_status", "original_parse_quality"):
                    item[field] = previous_doc.get(field, item.get(field))
                if mark_catalog_file_conflict(item, previous_doc):
                    versions[(key, item.get("sha256", ""))] = item
                    continue
                self._parse(cnpj, item, resume=resume)
                versions[(key, item.get("sha256", ""))] = item
                continue
            if key in texts:
                doc["text_path"] = str(texts[key])
                pages, visible = text_stats(texts[key])
                doc.update(parse_status="text_only_unverified_pages" if visible else "no_text", pages_extracted=pages or None,
                           download_status="pdf_not_local", error="source_pdf_not_local_page_completeness_unverified")
            elif doc.get("legacy_extraction_path"):
                doc.update(parse_status="legacy_excerpts_only", error="full_text_not_available_legacy_extraction_is_not_a_validated_rule")
            versions[(key, "")] = doc
        # Persist older network inventory even when a fresh source is temporarily inaccessible.
        for old in previous.get("documents", []):
            key = str(old.get("id") or "")
            if key and key not in {str(item.get("id") or "") for item in versions.values()}:
                if old.get("local_path") and not Path(old["local_path"]).exists():
                    old.update(download_status="referenced_file_missing", parse_status="not_downloaded", error="referenced_file_missing")
                versions[(key, old.get("sha256", ""))] = old
        return list(versions.values())

    def _network_catalog(self, cnpj: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        client = self.client or FundosNetClient(timeout_seconds=self.limits.network_timeout_seconds, max_retries=0)
        self.client = client
        search = {"source": "fundosnet", "url": f"https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM?cnpjFundo={cnpj}",
                  "queried_at": utc_now(), "status": "error", "error": "", "scope": "cnpj_all_fund_types",
                  "tipo_fundo": "all", "cnpj_filter": cnpj}
        for attempt in range(self.limits.attempts):
            try:
                self._room(download=True)
                rows = client.listar_documentos(cnpj, tipo_fundo="", error_stage="documentary_corpus_catalog")
                search.update(status="found" if rows else "no_results", error="", document_count=len(rows))
                return [asdict(doc) for doc in rows], search
            except ResourceLimitError as exc:
                search.update(status="resource_limit", error=str(exc))
                break
            except Exception as exc:  # Provider exceptions must be retained rather than converted into absence.
                search["error"] = f"{type(exc).__name__}: {exc}"
                if attempt + 1 < self.limits.attempts:
                    time.sleep(1)
        return [], search

    def _download(self, cnpj: str, item: dict[str, Any]) -> None:
        client = self.client or FundosNetClient(timeout_seconds=self.limits.network_timeout_seconds, max_retries=0)
        self.client = client
        filename_id = re.sub(r"[^A-Za-z0-9._-]", "_", str(item['id']))[:128]
        target = self.base / "raw" / cnpj / f"{filename_id}_{item['classification']}.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        declared_url = str(item.get("url") or "")
        external = not str(item["id"]).isdigit() or bool(declared_url and urlparse(declared_url).hostname != "fnet.bmfbovespa.com.br")
        if external and urlparse(declared_url).scheme not in {"https", "http"}:
            item.update(download_status="error", error="external_document_url_missing_or_invalid")
            return
        url = declared_url if external else client._url("downloadDocumento", {"id": str(item["id"])})
        headers = {"User-Agent": client.user_agent, "Accept": "application/pdf,*/*"}
        if not external and client.referer_url:
            headers["Referer"] = client.referer_url
        if not external and client.csrf_token:
            headers["CSRFToken"] = client.csrf_token
        for attempt in range(self.limits.attempts):
            temporary: Path | None = None
            try:
                self._room(download=True)
                fd, name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
                temporary = Path(name)
                with os.fdopen(fd, "wb") as output:
                    with client.opener.open(urllib.request.Request(url, headers=headers), timeout=self.limits.network_timeout_seconds) as response:
                        advertised = int(response.headers.get("Content-Length") or 0)
                        if advertised > self.limits.max_document_bytes * 2:
                            raise ResourceLimitError("document_size_limit")
                        self._stream_pdf_response(response, output, advertised)
                digest = self._hash(temporary)
                if target.exists() and sha256_file(target) != digest:
                    target = target.with_name(target.stem + "_" + digest[:16] + ".pdf")
                os.replace(temporary, target)
                if item.get("sha256") and item.get("sha256") != digest:
                    historical = {key: value for key, value in item.items() if key != "local_versions"}
                    historical.update(item.get("file_catalog_metadata") or {})
                    item.setdefault("local_versions", []).append(historical)
                    clear_text_cache(item)
                item.update(local_path=str(target), sha256=digest, download_status="downloaded", error="")
                item.update(file_catalog_metadata=file_catalog_metadata(item), catalog_file_binding="verified_download", catalog_verified_at=utc_now())
                item.pop("catalog_changed_fields", None)
                self._parse(cnpj, item, resume=True)
                return
            except ResourceLimitError as exc:
                item.update(download_status="resource_limit", error=str(exc))
                return
            except Exception as exc:
                item.update(download_status="error", error=f"{type(exc).__name__}: {exc}")
                if attempt + 1 < self.limits.attempts:
                    time.sleep(1)
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)

    def _stream_pdf_response(self, response: BinaryIO, output: BinaryIO, advertised: int = 0) -> None:
        """Decode direct or quoted-base64 Fundos.NET PDFs in fixed-size chunks."""
        raw_read, written, pending = 0, 0, b""
        first = response.read(CHUNK_SIZE)
        raw_read += len(first)
        direct = first.startswith(b"%PDF-")
        magic = b""

        def write(chunk: bytes) -> None:
            nonlocal written, magic
            if not chunk:
                return
            written += len(chunk)
            if written > self.limits.max_document_bytes:
                raise ResourceLimitError("document_size_limit")
            self._room(len(chunk), download=True)
            self.downloaded_bytes += len(chunk)
            if len(magic) < 8:
                magic += chunk[:8 - len(magic)]
            output.write(chunk)

        chunk = first
        while chunk:
            if direct:
                write(chunk)
            else:
                pending += re.sub(rb"\s+", b"", chunk).strip(b'"')
                # Retain a quartet so a final '=' padding cannot be followed by further input.
                amount = max(0, (len(pending) // 4 - 1) * 4)
                if amount:
                    write(base64.b64decode(pending[:amount], validate=True))
                    pending = pending[amount:]
            chunk = response.read(CHUNK_SIZE)
            raw_read += len(chunk)
            if raw_read > self.limits.max_document_bytes * 2:
                raise ResourceLimitError("response_size_limit")
        if not direct and pending:
            write(base64.b64decode(pending.strip(b'"'), validate=True))
        if advertised and advertised != raw_read:
            raise ValueError("content_length_mismatch")
        if not magic.startswith(b"%PDF-") or written == 0:
            raise ValueError("invalid_pdf_magic")

    @staticmethod
    def _fic_text_candidates(cnpj: str, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Discover possible invested classes without claiming that a CNPJ mention is a relationship."""
        candidates, seen = [], set()
        for document in documents:
            if document["classification"] not in {"regulamento", "anexo", "assembleia"} or document["parse_status"] != "complete":
                continue
            path = Path(document["text_path"])
            with path.open(encoding="utf-8", errors="replace") as handle:
                pending, page = "", 1
                for chunk in iter(lambda: handle.read(CHUNK_SIZE), ""):
                    pending += chunk
                    while "\f" in pending:
                        content, pending = pending.split("\f", 1)
                        for mention in CNPJ_RE.finditer(content):
                            target = normalize_cnpj(mention.group())
                            context = content[max(0, mention.start() - 400):mention.end() + 400]
                            if target == cnpj or not any(term in context.casefold() for term in ("investid", "cotas do", "cotas de", "cotas da", "cotas desta")):
                                continue
                            key = (target, document["id"], page)
                            if key in seen:
                                continue
                            seen.add(key)
                            candidates.append({"investor_cnpj": cnpj, "candidate_cnpj": target,
                                               "status": "candidate_requires_primary_validation", "document_id": document["id"],
                                               "page": page, "source_reference": document["url"], "local_path": document["local_path"],
                                               "text_path": document["text_path"], "source_excerpt": context.strip(),
                                               "note": "A nearby investment term is a search lead; validate the named class and relationship in the primary clause."})
                        page += 1
                    if len(pending) > 2 * 1024**2:
                        # A malformed oversized text page is omitted from candidate discovery.
                        pending = pending[-4096:]
        return candidates

    def refresh(self, cnpj: str, *, network: bool = False, resume: bool = True, fund: dict[str, Any] | None = None,
                skip_successful_network: bool = False, acquisition_pass: str = "all") -> dict[str, Any]:
        cnpj = normalize_cnpj(cnpj)
        if len(cnpj) != 14:
            raise ValueError("CNPJ must contain 14 digits")
        if acquisition_pass not in {"current", "history", "all"}:
            raise ValueError("acquisition_pass must be current, history or all")
        self.prepare([cnpj])
        output = self.base / "corpus" / f"{cnpj}.json"
        previous = json.loads(output.read_text(encoding="utf-8")) if resume and output.exists() else {}
        docs, searches, relationships = self._read_metadata(cnpj)
        # Keep external search failures across resumed runs; the local index is current.
        searches = [search for search in previous.get("searches", []) if search.get("source") not in {"local_metadata", "local_corpus"}] + searches
        successful_catalog = any(search.get("source") == "fundosnet" and search.get("status") in {"found", "no_results"}
                                 and search.get("scope") == "cnpj_all_fund_types" and search.get("cnpj_filter") == cnpj
                                 for search in previous.get("searches", []))
        reuse_catalog = successful_catalog and (skip_successful_network or acquisition_pass == "history")
        catalog_available = successful_catalog
        if network and not reuse_catalog:
            rows, search = self._network_catalog(cnpj)
            searches.append(search)
            catalog_available = search["status"] in {"found", "no_results"}
            for row in rows:
                key = str(row["id"])
                item = docs.setdefault(key, self._blank_document(row["id"]))
                item.update(classification=corpus_classification(row), title=row.get("tipo") or row.get("categoria") or "",
                            reference_date=row.get("data_referencia"), delivery_date=row.get("data_entrega"), version=row.get("versao"),
                            provider_status=row.get("status"), scope=row.get("fundo_ou_classe"), fund_or_class_name=row.get("nome_fundo"),
                            category=row.get("categoria"), document_type=row.get("tipo"))
        documents = self._discover_local(cnpj, docs, previous, resume=resume)
        identity = fund or previous.get("fund", {})
        name = str(identity.get("name") or "").upper()
        payload = {"schema_version": SCHEMA_VERSION, "cnpj": cnpj, "fund": fund or previous.get("fund", {}),
                   "generated_at": utc_now(), "mode": "network" if network else "local_only", "documents": documents,
                   "searches": searches, "relationship_candidates": relationships,
                   "resource_limits": asdict(self.limits), "downloaded_bytes_this_run": self.downloaded_bytes,
                   "acquisition_pass": acquisition_pass, "history_complete": False,
                   "history_complete_scope": "fundosnet_inventory_only"}
        payload["pending_sources"] = [{"source": source, "status": "not_searched", "queried_at": None,
                                       "reason": "source_adapter_not_executed"} for source in
                                      ("administrator_and_manager", "rating_agencies", "anbima_and_offer_documents", "lastro_verifier")]
        if network:
            current_ids = current_document_ids(documents)
            payload["current_acquisition_ids"] = sorted(current_ids)
            for item in sorted(documents, key=lambda row: (PRIORITY.get(row["classification"], 99),
                                                          -document_date_key(row.get("reference_date")).toordinal(),
                                                          -(int(row.get("version") or 0)), -numeric_document_id(row.get("id")))):
                if item.get("local_path") and Path(item["local_path"]).exists() and item.get("catalog_file_binding") != "conflict":
                    continue
                if item["classification"] not in DOWNLOADABLE:
                    if item["classification"] == "informe_mensal":
                        item.update(download_status="excluded_ime_pipeline", parse_status="not_applicable_ime_pipeline")
                    continue
                if acquisition_pass == "current" and str(item.get("id") or "") not in current_ids:
                    item.update(download_status="deferred_document", deferred_reason="history_pass_not_executed")
                    continue
                if item.get("id"):
                    item.pop("deferred_reason", None)
                    self._download(cnpj, item)
                    payload["downloaded_bytes_this_run"] = self.downloaded_bytes
                    atomic_json(output, payload)
                    if item["download_status"] == "resource_limit" and item["error"] in {"download_budget_reached", "disk_floor_reached"}:
                        for pending in documents:
                            if not pending.get("local_path") and pending["classification"] in DOWNLOADABLE:
                                if acquisition_pass == "current" and str(pending.get("id") or "") not in current_ids:
                                    pending.update(download_status="deferred_document", deferred_reason="history_pass_not_executed")
                                else:
                                    pending.update(download_status="resource_limit", error=item["error"])
                        break
            payload["history_complete"] = catalog_available and acquisition_pass in {"all", "history"} and all(
                doc["classification"] not in DOWNLOADABLE or bool(doc.get("local_path")) and Path(doc["local_path"]).exists() and doc.get("catalog_file_binding") != "conflict"
                for doc in documents)
        if "EM COTAS" in name or re.search(r"\bFIC(?:-FIDC)?\b", name):
            relationships.extend(self._fic_text_candidates(cnpj, documents))
        payload["summary"] = {"documents": len(documents), "local_pdfs": sum(bool(row.get("local_path")) for row in documents),
                              "complete_parses": sum(row["parse_status"] == "complete" for row in documents),
                              "relationship_candidates": len(relationships)}
        searches.append({"source": "local_corpus", "url": "; ".join(map(str, self.source_roots)), "queried_at": utc_now(),
                         "status": "indexed" if documents else "no_local_document", "error": "",
                         "note": "No local document does not establish absence from the public sources."})
        atomic_json(output, payload)
        return payload
