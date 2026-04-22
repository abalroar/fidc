from __future__ import annotations

from html import escape

import streamlit as st

from services.fidc_book import FIDCBookIndex, FIDCBookPage, load_fidc_book_index


_BOOK_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');

html, body, .stApp, .stMarkdown, .stTextInput, .stSelectbox, .stRadio, .stTabs, div, p, label, input, button, h1, h2, h3, h4, h5, h6, li, table, th, td {
    font-family: 'IBM Plex Sans', sans-serif !important;
}

.fidc-book-header {
    margin: 0.15rem 0 1.1rem 0;
    padding-bottom: 0.9rem;
    border-bottom: 1px solid #ece5de;
}

.fidc-book-title {
    color: #12171d;
    font-size: 1.9rem;
    line-height: 1.02;
    letter-spacing: -0.03em;
    font-weight: 600;
    margin: 0;
}

.fidc-book-subtitle {
    margin-top: 0.35rem;
    color: #68727d;
    font-size: 0.92rem;
    line-height: 1.4;
}

.fidc-book-nav {
    padding-top: 0.1rem;
}

.fidc-book-nav-divider {
    margin: 0.8rem 0 0.7rem 0;
    border-top: 1px solid #ece5de;
}

.fidc-book-page-shell {
    padding-bottom: 1.15rem;
    margin-bottom: 1.35rem;
    border-bottom: 1px solid #ece5de;
}

.fidc-book-page-section {
    color: #d35714;
    font-size: 0.76rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.45rem;
}

.fidc-book-page-title {
    color: #12171d;
    font-size: 2.45rem;
    line-height: 1.02;
    letter-spacing: -0.035em;
    font-weight: 600;
    margin-bottom: 0.7rem;
}

.fidc-book-page-summary {
    max-width: 44rem;
    color: #59626d;
    font-size: 1.03rem;
    line-height: 1.68;
}

div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] {
    max-width: 48rem;
}

div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] h1 {
    display: none;
}

div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] h2 {
    color: #161c23;
    font-size: 1.5rem;
    line-height: 1.18;
    letter-spacing: -0.02em;
    font-weight: 600;
    margin: 2rem 0 0.8rem 0;
}

div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] h3 {
    color: #d35714;
    font-size: 0.8rem;
    line-height: 1.2;
    letter-spacing: 0.08em;
    font-weight: 600;
    text-transform: uppercase;
    margin: 1.75rem 0 0.45rem 0;
}

div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] p,
div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] li,
div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] td,
div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] th {
    color: #27313b;
    font-size: 1rem;
    line-height: 1.76;
}

div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] p,
div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] ul,
div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] ol,
div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] table {
    margin-bottom: 1rem;
}

div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] ul,
div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] ol {
    padding-left: 1.15rem;
}

div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] strong {
    color: #141a20;
    font-weight: 600;
}

div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] table {
    width: 100%;
    border-collapse: collapse;
    border: 1px solid #e9e3dd;
}

div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] thead tr {
    background: #f7f3ef;
}

div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] th {
    color: #a64916;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    text-align: left;
    padding: 0.75rem 0.85rem;
    border-bottom: 1px solid #e9e3dd;
}

div.element-container:has(.fidc-book-page-shell) + div.element-container [data-testid="stMarkdownContainer"] td {
    padding: 0.8rem 0.85rem;
    border-bottom: 1px solid #eee8e2;
    vertical-align: top;
}

[data-testid="stTextInput"] input {
    border: 1px solid #e1e5ea;
    border-radius: 8px;
    color: #18212a;
    background: #ffffff;
}

[data-testid="stTextInput"] input::placeholder {
    color: #7a8591;
}

[data-testid="stSelectbox"] > div[data-baseweb="select"] {
    margin-top: 0.2rem;
}

[data-testid="stSelectbox"] > div[data-baseweb="select"] > div {
    border: 1px solid #e1e5ea;
    border-radius: 8px;
}

[data-testid="stRadio"] div[role="radiogroup"] {
    gap: 0 !important;
}

[data-testid="stRadio"] div[role="radiogroup"] label {
    align-items: flex-start !important;
    justify-content: flex-start !important;
    width: 100%;
    margin: 0;
    padding: 0.12rem 0 0.12rem 0.7rem;
    min-height: auto !important;
    border-left: 2px solid transparent;
}

[data-testid="stRadio"] div[role="radiogroup"] label > div:first-child {
    display: none;
}

[data-testid="stRadio"] div[role="radiogroup"] label > div:last-child {
    justify-content: flex-start !important;
    width: 100%;
}

[data-testid="stRadio"] div[role="radiogroup"] label p {
    margin: 0;
    color: #4f5964;
    font-size: 0.95rem;
    line-height: 1.3;
    text-align: left !important;
    transition: color 120ms ease;
}

[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) {
    border-left-color: #d35714;
}

[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) p {
    color: #d35714;
    font-weight: 500;
}
</style>
"""


@st.cache_data(show_spinner=False)
def _load_index() -> FIDCBookIndex:
    return load_fidc_book_index()


def render_tab_fidc_book() -> None:
    index = _load_index()
    st.markdown(_BOOK_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="fidc-book-header">
          <div class="fidc-book-title">Glossário FIDC</div>
          <div class="fidc-book-subtitle">Estrutura, risco e regulação</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    filtered_pages = index.search_pages(st.session_state.get("fidc_book_query", ""))
    filtered_page_ids = {page.page_id for page in filtered_pages}
    available_sections = tuple(
        section
        for section in index.sections
        if any(page.page_id in filtered_page_ids for page in section.pages)
    )
    if not available_sections:
        available_sections = index.sections

    left_col, right_col = st.columns([0.84, 2.36], gap="large")

    with left_col:
        st.markdown('<div class="fidc-book-nav">', unsafe_allow_html=True)
        query = st.text_input(
            "Buscar",
            key="fidc_book_query",
            placeholder="Buscar",
            label_visibility="collapsed",
        )

        filtered_pages = index.search_pages(query)
        filtered_page_ids = {page.page_id for page in filtered_pages}
        available_sections = tuple(
            section
            for section in index.sections
            if any(page.page_id in filtered_page_ids for page in section.pages)
        )
        if not available_sections:
            st.info("Nenhuma página encontrada.")
            st.markdown("</div>", unsafe_allow_html=True)
            return

        section_lookup = {section.section_id: section for section in available_sections}
        current_page = _current_page(index, filtered_page_ids)
        default_section_id = current_page.section_id if current_page else available_sections[0].section_id
        if st.session_state.get("fidc_book_section_id") not in section_lookup:
            st.session_state["fidc_book_section_id"] = default_section_id

        section_id = st.selectbox(
            "Seção",
            options=[section.section_id for section in available_sections],
            index=[section.section_id for section in available_sections].index(default_section_id),
            format_func=lambda value: section_lookup[value].title,
            key="fidc_book_section_id",
            label_visibility="collapsed",
        )
        section = section_lookup[section_id]

        section_pages = tuple(page for page in section.pages if page.page_id in filtered_page_ids)
        page_lookup = {page.page_id: page for page in section_pages}
        default_page_id = current_page.page_id if current_page and current_page.page_id in page_lookup else section_pages[0].page_id
        if st.session_state.get("fidc_book_page_id") not in page_lookup:
            st.session_state["fidc_book_page_id"] = default_page_id

        st.markdown('<div class="fidc-book-nav-divider"></div>', unsafe_allow_html=True)
        page_id = st.radio(
            "Páginas",
            options=[page.page_id for page in section_pages],
            index=[page.page_id for page in section_pages].index(default_page_id),
            format_func=lambda value: page_lookup[value].title,
            key="fidc_book_page_id",
            label_visibility="collapsed",
        )
        st.markdown("</div>", unsafe_allow_html=True)
        selected_page = page_lookup[page_id]

    with right_col:
        _render_page(index, selected_page)


def _current_page(index: FIDCBookIndex, filtered_page_ids: set[str]) -> FIDCBookPage | None:
    page_id = st.session_state.get("fidc_book_page_id")
    if page_id and page_id in filtered_page_ids:
        try:
            return index.page_by_id(page_id)
        except KeyError:
            return None
    return None


def _render_page(index: FIDCBookIndex, page: FIDCBookPage) -> None:
    st.markdown(
        (
            '<div class="fidc-book-page-shell">'
            f'<div class="fidc-book-page-section">{escape(page.section_title)}</div>'
            f'<div class="fidc-book-page-title">{escape(page.title)}</div>'
            f'<div class="fidc-book-page-summary">{escape(page.summary)}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.markdown(index.load_page_body(page))

    public_sources = [
        index.sources[source_id]
        for source_id in page.source_ids
        if source_id in index.sources and "http" in index.sources[source_id].location
    ]
    if public_sources:
        st.markdown('<div class="fidc-book-page-section">Fontes oficiais</div>', unsafe_allow_html=True)
        for source in public_sources:
            notes = f" — {source.notes}" if source.notes else ""
            st.markdown(f"- **{source.title}** · [link oficial]({source.location}){notes}")
