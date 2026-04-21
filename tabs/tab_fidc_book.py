from __future__ import annotations

from html import escape

import streamlit as st

from services.fidc_book import FIDCBookIndex, FIDCBookPage, load_fidc_book_index


_BOOK_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');

html, body, .stApp, .stMarkdown, .stTextInput, .stRadio, .stTabs, div, p, label, input, button, h1, h2, h3, h4, h5, h6, li, table, th, td {
    font-family: 'IBM Plex Sans', sans-serif !important;
}

.fidc-book-header {
    margin: 0.25rem 0 1.35rem 0;
    padding-bottom: 1rem;
    border-bottom: 1px solid #ece5de;
}

.fidc-book-eyebrow {
    color: #d35714;
    font-size: 0.76rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.35rem;
}

.fidc-book-title {
    color: #12171d;
    font-size: 2.1rem;
    line-height: 1.04;
    letter-spacing: -0.03em;
    font-weight: 600;
    margin: 0;
}

.fidc-book-subtitle {
    max-width: 42rem;
    margin-top: 0.7rem;
    color: #5b6570;
    font-size: 1rem;
    line-height: 1.65;
}

.fidc-book-nav-label {
    color: #d35714;
    font-size: 0.74rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 0.2rem 0 0.45rem 0;
}

.fidc-book-page-shell {
    padding-bottom: 1.2rem;
    margin-bottom: 1.4rem;
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
    border: 1px solid #d8dde3;
    border-radius: 10px;
    color: #18212a;
    background: #ffffff;
}

[data-testid="stTextInput"] input::placeholder {
    color: #7a8591;
}

[data-testid="stRadio"] div[role="radiogroup"] {
    gap: 0.15rem;
}

[data-testid="stRadio"] div[role="radiogroup"] label {
    align-items: flex-start !important;
    justify-content: flex-start !important;
    width: 100%;
    margin: 0;
    padding: 0.18rem 0;
}

[data-testid="stRadio"] div[role="radiogroup"] label > div {
    justify-content: flex-start !important;
}

[data-testid="stRadio"] div[role="radiogroup"] label p {
    margin: 0;
    color: #26313b;
    font-size: 0.97rem;
    line-height: 1.35;
    text-align: left !important;
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
          <div class="fidc-book-eyebrow">Glossário FIDC</div>
          <div class="fidc-book-title">Estrutura, risco e regulação em FIDCs</div>
          <div class="fidc-book-subtitle">
            Referência de leitura para entender a estrutura do fundo, a lógica de risco da carteira e o que o Informe Mensal efetivamente informa.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left_col, right_col = st.columns([0.78, 2.42], gap="large")

    with left_col:
        st.markdown('<div class="fidc-book-nav-label">Buscar</div>', unsafe_allow_html=True)
        query = st.text_input(
            "Buscar",
            key="fidc_book_query",
            placeholder="Buscar por tema, métrica ou participante",
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
            st.info("Nenhuma página encontrada para esse filtro.")
            return

        section_lookup = {section.section_id: section for section in available_sections}
        st.markdown('<div class="fidc-book-nav-label">Capítulos</div>', unsafe_allow_html=True)
        section_id = st.radio(
            "Capítulos",
            options=[section.section_id for section in available_sections],
            format_func=lambda value: section_lookup[value].title,
            label_visibility="collapsed",
        )
        section = section_lookup[section_id]

        section_pages = tuple(page for page in section.pages if page.page_id in filtered_page_ids)
        page_lookup = {page.page_id: page for page in section_pages}
        st.markdown('<div class="fidc-book-nav-label">Páginas</div>', unsafe_allow_html=True)
        page_id = st.radio(
            "Páginas",
            options=[page.page_id for page in section_pages],
            format_func=lambda value: page_lookup[value].title,
            label_visibility="collapsed",
        )
        selected_page = page_lookup[page_id]

    with right_col:
        _render_page(index, selected_page)


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
