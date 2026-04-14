from __future__ import annotations

from html import escape

import streamlit as st

from services.fidc_book import FIDCBookIndex, FIDCBookPage, load_fidc_book_index


_BOOK_CSS = """
<style>
.fidc-book-hero {
    background: #ffffff;
    border: 1px solid rgba(255, 90, 0, 0.18);
    border-left: 4px solid #ff5a00;
    border-radius: 14px;
    padding: 1.0rem 1.1rem;
    margin-bottom: 1rem;
}
.fidc-book-kicker {
    color: #ff5a00;
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 0.2rem;
}
.fidc-book-title {
    color: #111111;
    font-size: 1.5rem;
    font-weight: 700;
    margin-bottom: 0.2rem;
}
.fidc-book-subtitle {
    color: #4f5b67;
    font-size: 0.96rem;
}
.fidc-book-panel {
    background: #ffffff;
    border: 1px solid #e6e9ee;
    border-radius: 14px;
    padding: 1rem 1.05rem;
}
.fidc-book-page-shell {
    background: #ffffff;
    border: 1px solid #e6e9ee;
    border-radius: 14px;
    padding: 1rem 1.1rem;
    margin-bottom: 1rem;
}
.fidc-book-page-title {
    color: #111111;
    font-size: 1.35rem;
    font-weight: 700;
    margin-bottom: 0.15rem;
}
.fidc-book-page-summary {
    color: #566270;
    font-size: 0.95rem;
}
.fidc-book-chip {
    display: inline-block;
    margin-right: 0.35rem;
    margin-top: 0.5rem;
    padding: 0.16rem 0.48rem;
    border-radius: 999px;
    background: #f4f6f8;
    color: #394552;
    font-size: 0.78rem;
    font-weight: 600;
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
        <div class="fidc-book-hero">
          <div class="fidc-book-kicker">Book FIDC</div>
          <div class="fidc-book-title">Glossário e base regulatória</div>
          <div class="fidc-book-subtitle">
            Navegação direta por capítulos para consulta rápida. Conteúdo ancorado em normas oficiais da CVM e no acervo documental do repositório.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    query = st.text_input("Buscar tema", placeholder="Ex.: subordinação, cessão, consignado")
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
    left_col, right_col = st.columns([0.95, 2.15], gap="large")

    with left_col:
        section_id = st.radio(
            "Capítulos",
            options=[section.section_id for section in available_sections],
            format_func=lambda value: section_lookup[value].title,
        )
        section = section_lookup[section_id]
        st.caption(section.description)

        section_pages = tuple(page for page in section.pages if page.page_id in filtered_page_ids)
        page_lookup = {page.page_id: page for page in section_pages}
        page_id = st.radio(
            "Páginas",
            options=[page.page_id for page in section_pages],
            format_func=lambda value: page_lookup[value].title,
        )
        selected_page = page_lookup[page_id]

        st.markdown("#### Trilha sugerida")
        for page in _reading_track(index):
            st.markdown(f"- {page.title}")

        st.markdown("#### Fundos de referência")
        for fund in index.reference_funds[:6]:
            st.markdown(f"**{fund.title}**")
            st.caption(f"{fund.receivable_family} · {fund.origin_profile}")

    with right_col:
        _render_page(index, selected_page)


def _reading_track(index: FIDCBookIndex) -> list[FIDCBookPage]:
    page_ids = [
        "overview",
        "o-que-e-fidc",
        "participantes",
        "classes-cotas-waterfall",
        "metricas-estruturais",
        "provisao-perdas-e-inadimplencia",
        "recebiveis-financeiros",
    ]
    pages: list[FIDCBookPage] = []
    for page_id in page_ids:
        try:
            pages.append(index.page_by_id(page_id))
        except KeyError:
            continue
    return pages


def _render_page(index: FIDCBookIndex, page: FIDCBookPage) -> None:
    chips = " ".join(
        [
            f'<span class="fidc-book-chip">{escape(page.section_title)}</span>',
            f'<span class="fidc-book-chip">Nível: {escape(page.level)}</span>',
        ]
    )
    st.markdown(
        (
            '<div class="fidc-book-page-shell">'
            f'<div class="fidc-book-page-title">{escape(page.title)}</div>'
            f'<div class="fidc-book-page-summary">{escape(page.summary)}</div>'
            f"{chips}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.markdown(index.load_page_markdown(page))

    related_concepts = index.related_concepts(page)
    if related_concepts:
        st.markdown("#### Conceitos relacionados")
        for concept in related_concepts:
            st.markdown(f"- **{concept.title}**: {concept.summary}")

    related_metrics = index.related_metrics(page)
    if related_metrics:
        st.markdown("#### Métricas relacionadas")
        for metric in related_metrics:
            st.markdown(f"- **{metric.title}** ({metric.classification}): {metric.summary}")

    related_funds = index.related_reference_funds(page)
    if related_funds:
        st.markdown("#### Fundos de referência")
        for fund in related_funds:
            st.markdown(f"- **{fund.title}**: {fund.receivable_family} · {fund.risk_focus}")

    related_documents = index.related_documents(page)
    if related_documents:
        st.markdown("#### Documentos do acervo usados nesta página")
        for entry in related_documents:
            notes = f" — {entry.notes}" if entry.notes else ""
            st.markdown(f"- **{entry.title}** ({entry.doc_type}){notes}")

    public_sources = [
        index.sources[source_id]
        for source_id in page.source_ids
        if source_id in index.sources and "http" in index.sources[source_id].location
    ]
    if public_sources:
        st.markdown("#### Normas e referências oficiais")
        for source in public_sources:
            notes = f" — {source.notes}" if source.notes else ""
            st.markdown(f"- **{source.title}** · [link oficial]({source.location}){notes}")
