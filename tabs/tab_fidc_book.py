from __future__ import annotations

from html import escape

import streamlit as st

from services.fidc_book import FIDCBookIndex, FIDCBookPage, load_fidc_book_index


_BOOK_CSS = """
<style>
.fidc-book-shell {
    background: linear-gradient(180deg, rgba(31,119,180,0.08), rgba(255,255,255,0.98));
    border: 1px solid rgba(31,119,180,0.12);
    border-radius: 20px;
    padding: 1.4rem 1.5rem;
    margin-bottom: 1rem;
}
.fidc-book-title {
    font-size: 1.55rem;
    font-weight: 700;
    color: #17324d;
    margin-bottom: 0.25rem;
}
.fidc-book-subtitle {
    color: #49657d;
    font-size: 0.98rem;
}
.fidc-book-nav-card {
    background: #ffffff;
    border: 1px solid rgba(31,119,180,0.12);
    border-radius: 16px;
    padding: 0.9rem 1rem;
    margin-bottom: 0.75rem;
    box-shadow: 0 10px 24px rgba(17, 24, 39, 0.05);
}
.fidc-book-nav-title {
    color: #17324d;
    font-weight: 700;
    margin-bottom: 0.2rem;
}
.fidc-book-nav-copy {
    color: #5f7283;
    font-size: 0.93rem;
}
.fidc-book-chip {
    display: inline-block;
    margin-right: 0.4rem;
    margin-bottom: 0.4rem;
    padding: 0.2rem 0.55rem;
    border-radius: 999px;
    background: rgba(31,119,180,0.09);
    color: #1f4b73;
    font-size: 0.8rem;
    font-weight: 600;
}
.fidc-book-page-shell {
    background: #ffffff;
    border: 1px solid rgba(31,119,180,0.12);
    border-radius: 18px;
    padding: 1.2rem 1.3rem;
    box-shadow: 0 10px 24px rgba(17, 24, 39, 0.05);
}
.fidc-book-page-title {
    font-size: 1.35rem;
    font-weight: 700;
    color: #17324d;
    margin-bottom: 0.2rem;
}
.fidc-book-page-summary {
    color: #5f7283;
    margin-bottom: 0.75rem;
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
        <div class="fidc-book-shell">
          <div class="fidc-book-title">Glossário / Book FIDC</div>
          <div class="fidc-book-subtitle">
            Base canônica em Markdown, ancorada em normas oficiais da CVM e em documentos oficiais do acervo local.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    stats = st.columns(4)
    stats[0].metric("Páginas", len(index.pages))
    stats[1].metric("Conceitos", len(index.concepts))
    stats[2].metric("Métricas", len(index.metrics))
    stats[3].metric("Fundos Âncora", len(index.reference_funds))

    left_col, right_col = st.columns([1.05, 2.2], gap="large")

    with left_col:
        query = st.text_input("Buscar tema", placeholder="Ex.: subordinação, cessão, consignado")
        section_options = ["Todas as seções"] + [section.title for section in index.sections]
        selected_section = st.selectbox("Seção", section_options, index=0)

        st.caption("Trilha sugerida")
        for page_id in [
            "hierarquia-regulatoria",
            "o-que-e-fidc",
            "participantes",
            "classes-cotas-waterfall",
            "metricas-estruturais",
            "fidcs-originacao-if",
        ]:
            page = index.page_by_id(page_id)
            st.markdown(f"- **{page.title}**")

        filtered_pages = index.search_pages(query)
        if selected_section != "Todas as seções":
            filtered_pages = tuple(page for page in filtered_pages if page.section_title == selected_section)

        if not filtered_pages:
            st.info("Nenhuma página encontrada para esse filtro.")
            return

        sections_to_render = [
            section
            for section in index.sections
            if any(page.page_id in {candidate.page_id for candidate in filtered_pages} for page in section.pages)
        ]

        for section in sections_to_render:
            st.markdown(
                (
                    '<div class="fidc-book-nav-card">'
                    f'<div class="fidc-book-nav-title">{escape(section.title)}</div>'
                    f'<div class="fidc-book-nav-copy">{escape(section.description)}</div>'
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

        page_lookup = {page.label: page for page in filtered_pages}
        selected_label = st.radio(
            "Página",
            options=list(page_lookup.keys()),
            label_visibility="collapsed",
        )
        selected_page = page_lookup[selected_label]

        with st.expander("Fundos de referência", expanded=False):
            for fund in index.reference_funds:
                st.markdown(f"**{fund.title}**")
                st.caption(f"{fund.receivable_family} · {fund.origin_profile}")

    with right_col:
        _render_page(index, selected_page)


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
        with st.expander("Conceitos canônicos relacionados", expanded=False):
            for concept in related_concepts:
                st.markdown(f"**{concept.title}**")
                st.caption(concept.summary)

    related_metrics = index.related_metrics(page)
    if related_metrics:
        with st.expander("Métricas relacionadas", expanded=False):
            for metric in related_metrics:
                st.markdown(f"**{metric.title}** · {metric.classification}")
                st.caption(metric.summary)

    related_funds = index.related_reference_funds(page)
    if related_funds:
        with st.expander("Fundos do acervo usados como referência", expanded=False):
            for fund in related_funds:
                st.markdown(f"**{fund.title}**")
                st.caption(f"{fund.receivable_family} · {fund.risk_focus}")

    related_documents = index.related_documents(page)
    if related_documents:
        with st.expander("Documentos do acervo para aprofundar", expanded=False):
            for entry in related_documents:
                st.markdown(f"**{entry.title}** · {entry.doc_type}")
                st.caption(f"{entry.notes} | {entry.path}")

    if page.source_ids:
        with st.expander("Fontes desta página", expanded=False):
            for source_id in page.source_ids:
                source = index.sources.get(source_id)
                if source is None:
                    continue
                label = f"**{source.title}**"
                location = f"`{source.location}`" if "http" not in source.location else f"[link oficial]({source.location})"
                notes = f" — {source.notes}" if source.notes else ""
                st.markdown(f"- {label} ({source.source_type}) · {location}{notes}")
