from __future__ import annotations

from dataclasses import dataclass
import json
import posixpath
import re
from pathlib import Path
import unicodedata
from urllib.parse import quote, unquote, urlsplit


_LEADING_H1 = re.compile(r"\A\s*#[ \t]+[^\n]*\n+")
_MARKDOWN_PAGE_LINK = re.compile(
    r"(?P<prefix>\[[^\]\n]+\]\()"
    r"(?P<target>[^)\s]+\.md(?:#[^)\s]+)?)"
    r"(?P<suffix>\))",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class FIDCBookSource:
    source_id: str
    title: str
    source_type: str
    location: str
    notes: str = ""


@dataclass(frozen=True)
class FIDCBookConcept:
    concept_id: str
    title: str
    summary: str
    aliases: tuple[str, ...]
    page_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    category: str = ""
    legacy_terms: tuple[str, ...] = ()
    mini_glossary_title: str = ""
    mini_glossary_definition: str = ""
    mini_glossary_order: int | None = None


@dataclass(frozen=True)
class FIDCBookMetric:
    metric_id: str
    title: str
    summary: str
    metric_type: str
    classification: str
    aliases: tuple[str, ...]
    page_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    formula: str = ""
    numerator: str = ""
    denominator: str = ""
    unit: str = ""
    mini_glossary_title: str = ""
    mini_glossary_definition: str = ""
    mini_glossary_order: int | None = None


@dataclass(frozen=True)
class FIDCReferenceFund:
    fund_id: str
    title: str
    receivable_family: str
    origin_profile: str
    risk_focus: str
    source_ids: tuple[str, ...]
    page_ids: tuple[str, ...]
    cnpj: str = ""
    evidence_status: str = ""
    last_verified: str = ""


@dataclass(frozen=True)
class FIDCDocumentEntry:
    document_id: str
    source_id: str
    title: str
    doc_type: str
    cnpj: str
    fundosnet_id: str
    official_url: str
    local_path: str
    local_status: str
    document_date: str
    version: str
    sha256: str
    pages: int | None
    extraction_method: str
    themes: tuple[str, ...]
    page_ids: tuple[str, ...]
    notes: str

    @property
    def path(self) -> str:
        """Compatibilidade com consumidores anteriores do indice."""
        return self.local_path or self.official_url


@dataclass(frozen=True)
class FIDCBookPage:
    page_id: str
    title: str
    summary: str
    relative_path: str
    level: str
    keywords: tuple[str, ...]
    source_ids: tuple[str, ...]
    section_id: str
    section_title: str

    @property
    def label(self) -> str:
        return f"{self.section_title} · {self.title}"


@dataclass(frozen=True)
class FIDCBookSection:
    section_id: str
    title: str
    description: str
    pages: tuple[FIDCBookPage, ...]


@dataclass(frozen=True)
class FIDCBookIndex:
    root_dir: Path
    sections: tuple[FIDCBookSection, ...]
    sources: dict[str, FIDCBookSource]
    concepts: tuple[FIDCBookConcept, ...]
    metrics: tuple[FIDCBookMetric, ...]
    reference_funds: tuple[FIDCReferenceFund, ...]
    document_entries: tuple[FIDCDocumentEntry, ...]

    @property
    def pages(self) -> tuple[FIDCBookPage, ...]:
        return tuple(page for section in self.sections for page in section.pages)

    def page_by_id(self, page_id: str) -> FIDCBookPage:
        for page in self.pages:
            if page.page_id == page_id:
                return page
        raise KeyError(f"Unknown FIDC book page: {page_id}")

    def resolve_page_path(self, page: FIDCBookPage) -> Path:
        root = self.root_dir.resolve()
        target = (self.root_dir / page.relative_path).resolve()
        if root not in target.parents and target != root:
            raise ValueError(f"Invalid FIDC book page path: {page.relative_path}")
        return target

    def load_page_markdown(self, page: FIDCBookPage) -> str:
        markdown = self.resolve_page_path(page).read_text(encoding="utf-8")
        markdown = _strip_optional_sections(markdown)
        return re.sub(r"\n{3,}", "\n\n", markdown).strip()

    def load_page_body(self, page: FIDCBookPage) -> str:
        raw = _normalize_book_text(self.load_page_markdown(page))
        return _LEADING_H1.sub("", raw, count=1)

    def page_for_markdown_link(self, page: FIDCBookPage, target: str) -> FIDCBookPage | None:
        """Resolve um link Markdown local sem acoplar o conteúdo ao app."""
        clean_target = str(target or "").strip().strip("<>")
        parsed = urlsplit(clean_target)
        if parsed.scheme or parsed.netloc or parsed.query or clean_target.startswith(("/", "#")):
            return None
        if not parsed.path.lower().endswith(".md"):
            return None

        linked_path = unquote(parsed.path)
        source_dir = posixpath.dirname(page.relative_path)
        candidates = (
            posixpath.normpath(posixpath.join(source_dir, linked_path)),
            posixpath.normpath(linked_path),
        )
        pages_by_path = {
            posixpath.normpath(candidate.relative_path): candidate
            for candidate in self.pages
        }
        for candidate_path in candidates:
            linked_page = pages_by_path.get(candidate_path)
            if linked_page is not None:
                return linked_page
        return None

    def load_page_body_for_app(self, page: FIDCBookPage) -> str:
        """Converte links entre artigos em rotas do app e preserva o Markdown-fonte."""
        body = self.load_page_body(page)

        def replace(match: re.Match[str]) -> str:
            raw_target = match.group("target")
            linked_page = self.page_for_markdown_link(page, raw_target)
            if linked_page is None:
                return match.group(0)
            fragment = urlsplit(raw_target).fragment
            app_target = f"?section=glossario&book_page={quote(linked_page.page_id, safe='')}"
            if fragment:
                app_target += f"#{quote(unquote(fragment), safe='-._~')}"
            return f"{match.group('prefix')}{app_target}{match.group('suffix')}"

        return _MARKDOWN_PAGE_LINK.sub(replace, body)

    def search_pages(self, query: str) -> tuple[FIDCBookPage, ...]:
        terms = [term for term in _search_normalize(_normalize_book_text(query)).split() if term]
        if not terms:
            return self.pages

        def matches(page: FIDCBookPage) -> bool:
            concept_terms = [
                " ".join((concept.title, *concept.aliases, *concept.legacy_terms))
                for concept in self.concepts
                if page.page_id in concept.page_ids
            ]
            metric_terms = [
                " ".join((metric.title, *metric.aliases))
                for metric in self.metrics
                if page.page_id in metric.page_ids
            ]
            haystack = _search_normalize(" ".join(
                [
                    page.title,
                    page.summary,
                    page.section_title,
                    " ".join(page.keywords),
                    self.load_page_markdown(page),
                    *concept_terms,
                    *metric_terms,
                ]
            ))
            return all(term in haystack for term in terms)

        return tuple(page for page in self.pages if matches(page))

    def related_concepts(self, page: FIDCBookPage) -> tuple[FIDCBookConcept, ...]:
        related: list[FIDCBookConcept] = []
        keywords = {keyword.lower() for keyword in page.keywords}
        for concept in self.concepts:
            if page.page_id in concept.page_ids:
                related.append(concept)
                continue
            aliases = {alias.lower() for alias in concept.aliases}
            if keywords.intersection(aliases):
                related.append(concept)
        return tuple(related)

    def related_metrics(self, page: FIDCBookPage) -> tuple[FIDCBookMetric, ...]:
        related: list[FIDCBookMetric] = []
        keywords = {keyword.lower() for keyword in page.keywords}
        for metric in self.metrics:
            if page.page_id in metric.page_ids:
                related.append(metric)
                continue
            aliases = {alias.lower() for alias in metric.aliases}
            if keywords.intersection(aliases):
                related.append(metric)
        return tuple(related)

    def related_reference_funds(self, page: FIDCBookPage) -> tuple[FIDCReferenceFund, ...]:
        related = [fund for fund in self.reference_funds if page.page_id in fund.page_ids]
        return tuple(related)

    def related_documents(self, page: FIDCBookPage) -> tuple[FIDCDocumentEntry, ...]:
        return tuple(entry for entry in self.document_entries if page.page_id in entry.page_ids)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _book_root() -> Path:
    return _repo_root() / "docs" / "fidc"


_BOOK_TEXT_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Informe Mensal Estruturado\s*\(IME\)", flags=re.IGNORECASE), "Informe Mensal"),
    (re.compile(r"\bInforme Mensal Estruturado\b", flags=re.IGNORECASE), "Informe Mensal"),
)

_OPTIONAL_SECTION_HEADINGS = {
    "para consultar depois",
    "para fixar nesta leitura",
}


def _normalize_book_text(value: str) -> str:
    normalized = value
    for pattern, replacement in _BOOK_TEXT_REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def _search_normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "")).casefold()
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def _ensure_unique(items: list[dict], key: str, label: str) -> None:
    values = [str(item.get(key, "")) for item in items]
    duplicates = sorted({value for value in values if value and values.count(value) > 1})
    if duplicates:
        raise ValueError(f"Duplicate {label}: {', '.join(duplicates)}")


def _strip_optional_sections(markdown: str) -> str:
    output: list[str] = []
    skip_level: int | None = None

    for line in markdown.splitlines():
        heading_match = re.match(r"^(#{2,6})\s+(.*?)\s*$", line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip().lower()
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None and title in _OPTIONAL_SECTION_HEADINGS:
                skip_level = level
                continue
        if skip_level is not None:
            continue
        output.append(line)

    return "\n".join(output)


def load_fidc_book_index() -> FIDCBookIndex:
    root = _book_root()
    index_payload = json.loads((root / "_data" / "book_index.json").read_text(encoding="utf-8"))
    sources_payload = json.loads((root / "_data" / "sources.json").read_text(encoding="utf-8"))
    concepts_payload = json.loads((root / "_data" / "concepts.json").read_text(encoding="utf-8"))
    metrics_payload = json.loads((root / "_data" / "metrics.json").read_text(encoding="utf-8"))
    reference_funds_payload = json.loads((root / "_data" / "reference_funds.json").read_text(encoding="utf-8"))
    document_index_payload = json.loads((root / "_data" / "document_index.json").read_text(encoding="utf-8"))

    _ensure_unique(sources_payload["sources"], "source_id", "FIDC source_id")
    _ensure_unique(concepts_payload["concepts"], "concept_id", "FIDC concept_id")
    _ensure_unique(metrics_payload["metrics"], "metric_id", "FIDC metric_id")
    _ensure_unique(reference_funds_payload["funds"], "fund_id", "FIDC fund_id")
    _ensure_unique(document_index_payload["documents"], "document_id", "FIDC document_id")
    _ensure_unique(index_payload["sections"], "section_id", "FIDC section_id")
    page_payloads = [page for section in index_payload["sections"] for page in section["pages"]]
    _ensure_unique(page_payloads, "page_id", "FIDC page_id")

    sources = {
        item["source_id"]: FIDCBookSource(
            source_id=item["source_id"],
            title=_normalize_book_text(item["title"]),
            source_type=item["source_type"],
            location=item["location"],
            notes=_normalize_book_text(item.get("notes", "")),
        )
        for item in sources_payload["sources"]
    }

    sections: list[FIDCBookSection] = []
    for section_payload in index_payload["sections"]:
        pages: list[FIDCBookPage] = []
        for page_payload in section_payload["pages"]:
            page = FIDCBookPage(
                page_id=page_payload["page_id"],
                title=_normalize_book_text(page_payload["title"]),
                summary=_normalize_book_text(page_payload["summary"]),
                relative_path=page_payload["path"],
                level=page_payload.get("level", "base"),
                keywords=tuple(_normalize_book_text(keyword) for keyword in page_payload.get("keywords", [])),
                source_ids=tuple(page_payload.get("source_ids", [])),
                section_id=section_payload["section_id"],
                section_title=_normalize_book_text(section_payload["title"]),
            )
            if not loadable_markdown_path(root, page.relative_path).exists():
                raise FileNotFoundError(f"FIDC book page not found: {page.relative_path}")
            pages.append(page)
        sections.append(
            FIDCBookSection(
                section_id=section_payload["section_id"],
                title=_normalize_book_text(section_payload["title"]),
                description=_normalize_book_text(section_payload["description"]),
                pages=tuple(pages),
            )
        )

    concepts = tuple(
        FIDCBookConcept(
            concept_id=item["concept_id"],
            title=_normalize_book_text(item["title"]),
            summary=_normalize_book_text(item["summary"]),
            aliases=tuple(_normalize_book_text(alias) for alias in item.get("aliases", [])),
            page_ids=tuple(item.get("page_ids", [])),
            source_ids=tuple(item.get("source_ids", [])),
            category=_normalize_book_text(item.get("category", "")),
            legacy_terms=tuple(_normalize_book_text(term) for term in item.get("legacy_terms", [])),
            mini_glossary_title=_normalize_book_text(item.get("mini_glossary_title", "")),
            mini_glossary_definition=_normalize_book_text(item.get("mini_glossary_definition", "")),
            mini_glossary_order=item.get("mini_glossary_order"),
        )
        for item in concepts_payload["concepts"]
    )
    metrics = tuple(
        FIDCBookMetric(
            metric_id=item["metric_id"],
            title=_normalize_book_text(item["title"]),
            summary=_normalize_book_text(item["summary"]),
            metric_type=item["metric_type"],
            classification=_normalize_book_text(item["classification"]),
            aliases=tuple(_normalize_book_text(alias) for alias in item.get("aliases", [])),
            page_ids=tuple(item.get("page_ids", [])),
            source_ids=tuple(item.get("source_ids", [])),
            formula=_normalize_book_text(item.get("formula", "")),
            numerator=_normalize_book_text(item.get("numerator", "")),
            denominator=_normalize_book_text(item.get("denominator", "")),
            unit=_normalize_book_text(item.get("unit", "")),
            mini_glossary_title=_normalize_book_text(item.get("mini_glossary_title", "")),
            mini_glossary_definition=_normalize_book_text(item.get("mini_glossary_definition", "")),
            mini_glossary_order=item.get("mini_glossary_order"),
        )
        for item in metrics_payload["metrics"]
    )
    reference_funds = tuple(
        FIDCReferenceFund(
            fund_id=item["fund_id"],
            title=_normalize_book_text(item["title"]),
            receivable_family=_normalize_book_text(item["receivable_family"]),
            origin_profile=_normalize_book_text(item["origin_profile"]),
            risk_focus=_normalize_book_text(item["risk_focus"]),
            source_ids=tuple(item.get("source_ids", [])),
            page_ids=tuple(item.get("page_ids", [])),
            cnpj=item.get("cnpj", ""),
            evidence_status=_normalize_book_text(item.get("evidence_status", "")),
            last_verified=item.get("last_verified", ""),
        )
        for item in reference_funds_payload["funds"]
    )
    document_entries = tuple(
        FIDCDocumentEntry(
            document_id=item["document_id"],
            source_id=item.get("source_id", item["document_id"]),
            title=_normalize_book_text(item["title"]),
            doc_type=_normalize_book_text(item["doc_type"]),
            cnpj=item.get("cnpj", ""),
            fundosnet_id=str(item.get("fundosnet_id", "")),
            official_url=item.get("official_url", ""),
            local_path=item.get("local_path", item.get("path", "")),
            local_status=_normalize_book_text(item.get("local_status", "")),
            document_date=item.get("document_date", ""),
            version=str(item.get("version", "")),
            sha256=item.get("sha256", ""),
            pages=item.get("pages"),
            extraction_method=item.get("extraction_method", ""),
            themes=tuple(_normalize_book_text(theme) for theme in item.get("themes", [])),
            page_ids=tuple(item.get("page_ids", [])),
            notes=_normalize_book_text(item.get("notes", "")),
        )
        for item in document_index_payload["documents"]
    )

    page_ids = {page.page_id for section in sections for page in section.pages}
    source_ids = set(sources)
    errors: list[str] = []
    for page in (page for section in sections for page in section.pages):
        errors.extend(
            f"page {page.page_id} -> unknown source {source_id}"
            for source_id in page.source_ids
            if source_id not in source_ids
        )
    for label, entries in (
        ("concept", concepts),
        ("metric", metrics),
        ("fund", reference_funds),
        ("document", document_entries),
    ):
        for entry in entries:
            entry_id = getattr(entry, f"{label}_id", getattr(entry, "document_id", ""))
            errors.extend(
                f"{label} {entry_id} -> unknown page {page_id}"
                for page_id in entry.page_ids
                if page_id not in page_ids
            )
            errors.extend(
                f"{label} {entry_id} -> unknown source {source_id}"
                for source_id in getattr(entry, "source_ids", ())
                if source_id not in source_ids
            )
    for entry in document_entries:
        if entry.source_id not in source_ids:
            errors.append(f"document {entry.document_id} -> unknown source {entry.source_id}")
    if errors:
        raise ValueError("Invalid FIDC book references: " + "; ".join(errors))

    return FIDCBookIndex(
        root_dir=root,
        sections=tuple(sections),
        sources=sources,
        concepts=concepts,
        metrics=metrics,
        reference_funds=reference_funds,
        document_entries=document_entries,
    )


def loadable_markdown_path(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    root_resolved = root.resolve()
    if root_resolved not in target.parents and target != root_resolved:
        raise ValueError(f"Invalid FIDC book path: {relative_path}")
    return target
