from __future__ import annotations

import re
from html import escape

import streamlit as st

from services.fidc_book import FIDCBookIndex, FIDCBookPage, load_fidc_book_index


_BOOK_CSS = """
<style>
.fidc-book-topbar {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.4rem 0 0.9rem 0;
    border-bottom: 1px solid #e6e9ee;
    margin-bottom: 1.1rem;
}
.fidc-book-topbar-title {
    color: #111111;
    font-size: 1.15rem;
    font-weight: 700;
    letter-spacing: -0.01em;
}
.fidc-book-topbar-meta {
    color: #7a8593;
    font-size: 0.82rem;
}
.fidc-book-nav-section {
    color: #7a8593;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 0.9rem 0 0.15rem 0.15rem;
}
.fidc-book-nav-section:first-child { margin-top: 0; }
.fidc-book-breadcrumb {
    color: #7a8593;
    font-size: 0.78rem;
    letter-spacing: 0.02em;
    margin-bottom: 0.35rem;
}
.fidc-book-page-title {
    color: #111111;
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    line-height: 1.2;
    margin-bottom: 0.35rem;
}
.fidc-book-page-summary {
    color: #566270;
    font-size: 0.95rem;
    font-weight: 400;
    margin-bottom: 0.6rem;
    max-width: 760px;
}
.fidc-book-level-tag {
    display: inline-block;
    margin-bottom: 1.1rem;
    padding: 0.12rem 0.5rem;
    border-radius: 4px;
    background: #eef2f6;
    color: #4f5b67;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
}
.fidc-book-search-results {
    background: #fafbfc;
    border: 1px solid #e6e9ee;
    border-radius: 10px;
    padding: 0.7rem 0.9rem;
    margin-bottom: 1.2rem;
}
.fidc-book-search-results-title {
    color: #394552;
    font-size: 0.82rem;
    font-weight: 600;
    margin-bottom: 0.4rem;
}
.fidc-book-related-card {
    background: #ffffff;
    border: 1px solid #e6e9ee;
    border-radius: 10px;
    padding: 0.7rem 0.85rem;
    height: 100%;
}
.fidc-book-related-card-title {
    color: #111111;
    font-size: 0.88rem;
    font-weight: 600;
    margin-bottom: 0.2rem;
}
.fidc-book-related-card-body {
    color: #566270;
    font-size: 0.82rem;
    line-height: 1.4;
}
.fidc-book-related-heading {
    color: #7a8593;
    font-size: 0.74rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 1.8rem 0 0.5rem 0;
}
.fidc-book-pager {
    display: flex;
    gap: 0.7rem;
    margin-top: 1.8rem;
    padding-top: 1rem;
    border-top: 1px solid #e6e9ee;
}
mark.fidc-book-hit {
    background: #fff4cc;
    color: inherit;
    padding: 0 0.1rem;
    border-radius: 2px;
}
</style>
"""


@st.cache_data(show_spinner=False)
def _load_index() -> FIDCBookIndex:
    return load_fidc_book_index()


def render_tab_fidc_book() -> None:
    index = _load_index()
    st.markdown(_BOOK_CSS, unsafe_allow_html=True)

    all_pages = list(index.pages)
    if "fidc_book_page_id" not in st.session_state:
        st.session_state["fidc_book_page_id"] = all_pages[0].page_id
    if "fidc_book_visited" not in st.session_state:
        st.session_state["fidc_book_visited"] = set()
    st.session_state["fidc_book_visited"].add(st.session_state["fidc_book_page_id"])

    header_left, header_right = st.columns([0.55, 0.45], gap="small")
    with header_left:
        st.markdown(
            f'<div class="fidc-book-topbar-title">Glossário FIDC</div>'
            f'<div class="fidc-book-topbar-meta">'
            f'{len(index.sections)} capítulos · {len(all_pages)} páginas · conteúdo ancorado em normas CVM e no acervo documental do repositório.'
            f'</div>',
            unsafe_allow_html=True,
        )
    with header_right:
        query = st.text_input(
            "Buscar",
            key="fidc_book_query",
            placeholder="Ex.: subordinação, cessão, consignado",
            label_visibility="collapsed",
        )
    st.markdown('<div style="margin-top:-0.4rem;border-bottom:1px solid #e6e9ee;margin-bottom:1.1rem"></div>', unsafe_allow_html=True)

    filtered_pages = index.search_pages(query)
    match_ids = {page.page_id for page in filtered_pages}

    nav_col, body_col = st.columns([0.95, 2.3], gap="large")

    with nav_col:
        _render_nav(index, match_ids, query)

    selected_id = st.session_state["fidc_book_page_id"]
    try:
        selected_page = index.page_by_id(selected_id)
    except KeyError:
        selected_page = all_pages[0]
        st.session_state["fidc_book_page_id"] = selected_page.page_id

    with body_col:
        if query.strip():
            _render_search_results(filtered_pages, query)
        _render_page(index, selected_page, all_pages)


def _render_nav(index: FIDCBookIndex, match_ids: set[str], query: str) -> None:
    active_id = st.session_state["fidc_book_page_id"]
    has_query = bool(query.strip())
    any_visible = False

    for section in index.sections:
        section_pages = section.pages
        if has_query:
            section_pages = tuple(p for p in section_pages if p.page_id in match_ids)
            if not section_pages:
                continue
        any_visible = True
        st.markdown(
            f'<div class="fidc-book-nav-section">{escape(section.title)}</div>',
            unsafe_allow_html=True,
        )
        visited = st.session_state.get("fidc_book_visited", set())
        for page in section_pages:
            is_active = page.page_id == active_id
            dot = "• " if (page.page_id in visited and not is_active) else ""
            label = f"{dot}{page.title}"
            if st.button(
                label,
                key=f"fidc_nav_{page.page_id}",
                use_container_width=True,
                type="secondary" if is_active else "tertiary",
            ):
                st.session_state["fidc_book_page_id"] = page.page_id
                st.rerun()

    if has_query and not any_visible:
        st.caption("Nenhuma página corresponde a essa busca.")


def _render_search_results(pages: tuple[FIDCBookPage, ...], query: str) -> None:
    if not pages:
        return
    items_html = []
    for page in pages[:8]:
        title = _highlight(page.title, query)
        items_html.append(f"<div style='margin:0.15rem 0'>· {title} <span style='color:#7a8593;font-size:0.78rem'>— {escape(page.section_title)}</span></div>")
    st.markdown(
        '<div class="fidc-book-search-results">'
        f'<div class="fidc-book-search-results-title">{len(pages)} página(s) com “{escape(query.strip())}”</div>'
        + "".join(items_html)
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_page(index: FIDCBookIndex, page: FIDCBookPage, all_pages: list[FIDCBookPage]) -> None:
    position = next((i for i, p in enumerate(all_pages) if p.page_id == page.page_id), 0)
    total = len(all_pages)

    breadcrumb = f"{escape(page.section_title)} · Página {position + 1} de {total}"
    st.markdown(f'<div class="fidc-book-breadcrumb">{breadcrumb}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="fidc-book-page-title">{escape(page.title)}</div>', unsafe_allow_html=True)

    body = index.load_page_body(page)
    if not _summary_is_prefix_of_body(page.summary, body):
        st.markdown(f'<div class="fidc-book-page-summary">{escape(page.summary)}</div>', unsafe_allow_html=True)

    if page.level and page.level.lower() != "base":
        st.markdown(
            f'<div class="fidc-book-level-tag">Nível {escape(page.level)}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(body)

    _render_related(index, page)
    _render_pager(all_pages, position)


def _render_related(index: FIDCBookIndex, page: FIDCBookPage) -> None:
    concepts = index.related_concepts(page)
    metrics = index.related_metrics(page)
    fix_items: list[tuple[str, str]] = []
    for concept in concepts:
        fix_items.append((concept.title, concept.summary))
    for metric in metrics:
        fix_items.append((f"{metric.title} · {metric.classification}", metric.summary))

    if fix_items:
        st.markdown('<div class="fidc-book-related-heading">Para fixar nesta leitura</div>', unsafe_allow_html=True)
        _render_cards_grid(fix_items)

    funds = index.related_reference_funds(page)
    public_sources = [
        index.sources[source_id]
        for source_id in page.source_ids
        if source_id in index.sources and "http" in index.sources[source_id].location
    ]

    if funds or public_sources:
        with st.expander("Para consultar depois", expanded=False):
            if funds:
                st.markdown("**Exemplos de perfis de recebíveis**")
                for fund in funds:
                    st.markdown(f"- **{fund.receivable_family}** — foco de risco em {fund.risk_focus}")
            if public_sources:
                if funds:
                    st.markdown("")
                st.markdown("**Normas e referências oficiais**")
                for source in public_sources:
                    notes = f" — {source.notes}" if source.notes else ""
                    st.markdown(f"- **{source.title}** · [link oficial]({source.location}){notes}")


def _render_cards_grid(items: list[tuple[str, str]]) -> None:
    if not items:
        return
    cols = st.columns(2)
    for idx, (title, body) in enumerate(items):
        with cols[idx % 2]:
            st.markdown(
                '<div class="fidc-book-related-card">'
                f'<div class="fidc-book-related-card-title">{escape(title)}</div>'
                f'<div class="fidc-book-related-card-body">{escape(body)}</div>'
                "</div>",
                unsafe_allow_html=True,
            )


def _render_pager(all_pages: list[FIDCBookPage], position: int) -> None:
    prev_page = all_pages[position - 1] if position > 0 else None
    next_page = all_pages[position + 1] if position < len(all_pages) - 1 else None

    st.markdown('<div class="fidc-book-pager"></div>', unsafe_allow_html=True)
    col_prev, col_next = st.columns(2)
    with col_prev:
        if prev_page is not None:
            if st.button(f"← Anterior · {prev_page.title}", key="fidc_pager_prev", use_container_width=True):
                st.session_state["fidc_book_page_id"] = prev_page.page_id
                st.rerun()
    with col_next:
        if next_page is not None:
            if st.button(f"Próxima · {next_page.title} →", key="fidc_pager_next", use_container_width=True):
                st.session_state["fidc_book_page_id"] = next_page.page_id
                st.rerun()


def _summary_is_prefix_of_body(summary: str, body: str) -> bool:
    norm_summary = _normalize(summary)
    if not norm_summary:
        return False
    first_para = body.strip().split("\n\n", 1)[0]
    norm_body = _normalize(first_para)
    return norm_body.startswith(norm_summary[:60]) if len(norm_summary) >= 40 else False


_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().lower()


def _highlight(text: str, query: str) -> str:
    escaped = escape(text)
    terms = [t for t in (query or "").split() if t.strip()]
    if not terms:
        return escaped
    pattern = re.compile("(" + "|".join(re.escape(t) for t in terms) + ")", re.IGNORECASE)
    return pattern.sub(lambda m: f'<mark class="fidc-book-hit">{m.group(0)}</mark>', escaped)
