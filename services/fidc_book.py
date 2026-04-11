from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


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


@dataclass(frozen=True)
class FIDCReferenceFund:
    fund_id: str
    title: str
    receivable_family: str
    origin_profile: str
    risk_focus: str
    source_ids: tuple[str, ...]
    page_ids: tuple[str, ...]


@dataclass(frozen=True)
class FIDCDocumentEntry:
    document_id: str
    title: str
    doc_type: str
    path: str
    themes: tuple[str, ...]
    page_ids: tuple[str, ...]
    notes: str


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
        return self.resolve_page_path(page).read_text(encoding="utf-8")

    def search_pages(self, query: str) -> tuple[FIDCBookPage, ...]:
        terms = [term.strip().lower() for term in query.split() if term.strip()]
        if not terms:
            return self.pages

        def matches(page: FIDCBookPage) -> bool:
            haystack = " ".join(
                [
                    page.title.lower(),
                    page.summary.lower(),
                    page.section_title.lower(),
                    " ".join(page.keywords).lower(),
                ]
            )
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


def load_fidc_book_index() -> FIDCBookIndex:
    root = _book_root()
    index_payload = json.loads((root / "_data" / "book_index.json").read_text(encoding="utf-8"))
    sources_payload = json.loads((root / "_data" / "sources.json").read_text(encoding="utf-8"))
    concepts_payload = json.loads((root / "_data" / "concepts.json").read_text(encoding="utf-8"))
    metrics_payload = json.loads((root / "_data" / "metrics.json").read_text(encoding="utf-8"))
    reference_funds_payload = json.loads((root / "_data" / "reference_funds.json").read_text(encoding="utf-8"))
    document_index_payload = json.loads((root / "_data" / "document_index.json").read_text(encoding="utf-8"))

    sources = {
        item["source_id"]: FIDCBookSource(
            source_id=item["source_id"],
            title=item["title"],
            source_type=item["source_type"],
            location=item["location"],
            notes=item.get("notes", ""),
        )
        for item in sources_payload["sources"]
    }

    sections: list[FIDCBookSection] = []
    for section_payload in index_payload["sections"]:
        pages: list[FIDCBookPage] = []
        for page_payload in section_payload["pages"]:
            page = FIDCBookPage(
                page_id=page_payload["page_id"],
                title=page_payload["title"],
                summary=page_payload["summary"],
                relative_path=page_payload["path"],
                level=page_payload.get("level", "base"),
                keywords=tuple(page_payload.get("keywords", [])),
                source_ids=tuple(page_payload.get("source_ids", [])),
                section_id=section_payload["section_id"],
                section_title=section_payload["title"],
            )
            if not loadable_markdown_path(root, page.relative_path).exists():
                raise FileNotFoundError(f"FIDC book page not found: {page.relative_path}")
            pages.append(page)
        sections.append(
            FIDCBookSection(
                section_id=section_payload["section_id"],
                title=section_payload["title"],
                description=section_payload["description"],
                pages=tuple(pages),
            )
        )

    concepts = tuple(
        FIDCBookConcept(
            concept_id=item["concept_id"],
            title=item["title"],
            summary=item["summary"],
            aliases=tuple(item.get("aliases", [])),
            page_ids=tuple(item.get("page_ids", [])),
            source_ids=tuple(item.get("source_ids", [])),
        )
        for item in concepts_payload["concepts"]
    )
    metrics = tuple(
        FIDCBookMetric(
            metric_id=item["metric_id"],
            title=item["title"],
            summary=item["summary"],
            metric_type=item["metric_type"],
            classification=item["classification"],
            aliases=tuple(item.get("aliases", [])),
            page_ids=tuple(item.get("page_ids", [])),
            source_ids=tuple(item.get("source_ids", [])),
        )
        for item in metrics_payload["metrics"]
    )
    reference_funds = tuple(
        FIDCReferenceFund(
            fund_id=item["fund_id"],
            title=item["title"],
            receivable_family=item["receivable_family"],
            origin_profile=item["origin_profile"],
            risk_focus=item["risk_focus"],
            source_ids=tuple(item.get("source_ids", [])),
            page_ids=tuple(item.get("page_ids", [])),
        )
        for item in reference_funds_payload["funds"]
    )
    document_entries = tuple(
        FIDCDocumentEntry(
            document_id=item["document_id"],
            title=item["title"],
            doc_type=item["doc_type"],
            path=item["path"],
            themes=tuple(item.get("themes", [])),
            page_ids=tuple(item.get("page_ids", [])),
            notes=item.get("notes", ""),
        )
        for item in document_index_payload["documents"]
    )

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
