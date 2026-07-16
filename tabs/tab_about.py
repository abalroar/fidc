from __future__ import annotations

import streamlit as st

from services.dashboard_ui import diagnostics_enabled, render_page_header
from tabs.tab_development_investment import render_development_investment_section


_ABOUT_CSS = """
<style>
.about-page,
.about-page * {
    font-family: 'IBM Plex Sans', sans-serif !important;
}

.about-page {
    margin: 0.15rem 0 1.3rem 0;
    padding-bottom: 1rem;
    border-bottom: 1px solid #ece5de;
}

.about-kicker {
    color: #ff5a00;
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    line-height: 1.2;
    margin-bottom: 0.35rem;
    text-transform: uppercase;
}

.about-title {
    color: #12171d;
    font-size: 2.15rem;
    line-height: 1.08;
    font-weight: 650;
    margin: 0;
}

.about-summary {
    color: #59626d;
    font-size: 1rem;
    line-height: 1.62;
    margin-top: 0.65rem;
    max-width: none;
    width: 100%;
}

.about-statement {
    color: #3f4854;
    font-size: 0.96rem;
    line-height: 1.58;
    margin-top: 0.85rem;
    max-width: none;
    width: 100%;
}

.about-statement p {
    margin: 0 0 0.6rem 0;
}

.about-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.8rem;
    margin: 1rem 0 0.4rem 0;
}

.about-card {
    background: #f7f8fa;
    border: 1px solid #e6ebf1;
    border-radius: 8px;
    padding: 0.9rem 1rem;
}

.about-card-title {
    color: #12171d;
    font-size: 0.96rem;
    font-weight: 650;
    margin-bottom: 0.35rem;
}

.about-card-body {
    color: #68727d;
    font-size: 0.9rem;
    line-height: 1.5;
}

@media (max-width: 900px) {
    .about-grid {
        grid-template-columns: 1fr;
    }
}
</style>
"""


def render_tab_about() -> None:
    st.markdown(_ABOUT_CSS, unsafe_allow_html=True)
    render_page_header(
        "Sobre",
        "Análise de FIDCs com dados públicos, documentação regulatória e premissas explícitas.",
    )
    st.markdown(
        """
        <div class="about-statement">
          <p>O aplicativo reúne indústria, mercado secundário, carteiras, regulamentos e modelagem econômico-financeira em uma leitura única.</p>
          <p>Criado por Matheus Prates, CFA. Projeto independente em evolução.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Sobre a base", expanded=False):
        st.markdown(
            "As análises usam principalmente informes mensais e cadastros da **CVM**, "
            "documentos do **Fundos.NET** e referências da **ANBIMA**. "
            "Datas de competência, cobertura e limitações materiais são mostradas em cada página. "
            "Valide os números antes de qualquer uso externo."
        )
    if diagnostics_enabled():
        render_development_investment_section()
