from __future__ import annotations

from html import escape
from pathlib import Path
import re
from typing import Any

import pandas as pd
import streamlit as st

from services.deep_dive_ppt_export import build_deep_dive_pptx_bytes
from services.deep_dive_store import (
    deep_dive_matches_portfolio,
    list_deep_dives,
    load_deep_dive_table,
)
from services.portfolio_store import portfolio_basket_signature
from tabs.ime_portfolio_support import (
    build_portfolio_record_label_lookup,
    list_saved_portfolios,
)


_CSS = """
<style>
.deepdive-kicker {
    color: #6b7280;
    font-size: 0.74rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.deepdive-title {
    color: #1f1f1f;
    font-size: 1.55rem;
    font-weight: 650;
    line-height: 1.15;
    margin: 0.1rem 0 0.25rem 0;
}
.deepdive-subtitle {
    color: #6b7280;
    font-size: 0.86rem;
    line-height: 1.35;
    margin-bottom: 0.65rem;
}
.deepdive-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin: 0.45rem 0 0.8rem 0;
}
.deepdive-chip {
    background: #f7f7f7;
    border: 1px solid #e0e0e0;
    border-radius: 999px;
    color: #4d4d4d;
    display: inline-flex;
    font-size: 0.74rem;
    line-height: 1.15;
    padding: 5px 9px;
}
.deepdive-table-wrap {
    border: 1px solid #d9dee5;
    border-radius: 4px;
    max-width: 100%;
    overflow-x: auto;
}
.deepdive-table {
    border-collapse: collapse;
    font-size: 0.76rem;
    table-layout: fixed;
    width: 100%;
}
.deepdive-table th {
    background: #111827;
    border-right: 1px solid rgba(255,255,255,0.14);
    color: #ffffff;
    font-weight: 650;
    line-height: 1.18;
    padding: 6px 7px;
    text-align: center;
    vertical-align: middle;
}
.deepdive-table th:first-child {
    text-align: left;
    width: 230px;
}
.deepdive-table th.highlight {
    background: #ec7000;
}
.deepdive-table td {
    border-bottom: 1px solid #e5e7eb;
    border-right: 1px solid #eeeeee;
    color: #1f1f1f;
    line-height: 1.20;
    padding: 5px 7px;
    text-align: center;
    vertical-align: middle;
    word-break: normal;
    overflow-wrap: anywhere;
}
.deepdive-table td:first-child {
    background: #f7f7f7;
    font-weight: 650;
    text-align: left;
}
.deepdive-table td.highlight {
    background: #fff2e8;
}
.deepdive-table tr:nth-child(even) td:not(:first-child):not(.highlight) {
    background: #fbfbfb;
}
</style>
"""


def render_tab_deep_dive() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    manifests = list_deep_dives()
    st.markdown("<div class='deepdive-kicker'>Análise offline</div>", unsafe_allow_html=True)
    st.markdown("<div class='deepdive-title'>Deep Dive</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='deepdive-subtitle'>Pacotes comparativos gerados por extração offline, versionados no repositório e exportáveis em PPTX editável.</div>",
        unsafe_allow_html=True,
    )

    if not manifests:
        st.info("Nenhum pacote em `data/deep_dives/`.")
        return

    portfolios = list_saved_portfolios()
    portfolio_labels = build_portfolio_record_label_lookup(portfolios)
    portfolio_options = ["Todos", *[portfolio.id for portfolio in portfolios]]
    selected_portfolio_id = st.selectbox(
        "Carteira",
        options=portfolio_options,
        format_func=lambda value: "Todos os Deep Dives" if value == "Todos" else portfolio_labels.get(value, value),
        key="deep_dive_portfolio",
    )
    selected_portfolio = next((portfolio for portfolio in portfolios if portfolio.id == selected_portfolio_id), None)
    selected_signature = portfolio_basket_signature(selected_portfolio.funds) if selected_portfolio else ""
    available = [
        manifest
        for manifest in manifests
        if selected_portfolio_id == "Todos" or deep_dive_matches_portfolio(manifest, selected_portfolio_id, selected_signature)
    ]
    if not available:
        st.warning("Não há Deep Dive salvo para a carteira selecionada.")
        return

    manifest = st.selectbox(
        "Material",
        options=available,
        format_func=lambda item: f"{item.title} · {item.generated_at or item.deep_dive_id}",
        key="deep_dive_manifest",
    )
    _render_manifest_header(manifest)

    if not manifest.tables:
        st.warning("Pacote sem tabelas configuradas.")
        return
    table_spec = st.selectbox(
        "Tabela",
        options=list(manifest.tables),
        format_func=lambda item: item.title,
        key=f"deep_dive_table::{manifest.deep_dive_id}",
    )
    frame = load_deep_dive_table(manifest, table_spec)
    if frame.empty:
        st.warning("Tabela vazia ou arquivo ausente.")
        return

    highlight_options = ["Nenhuma", *frame.columns[1:].tolist()]
    highlighted_column = st.selectbox(
        "Coluna em destaque",
        options=highlight_options,
        index=0,
        key=f"deep_dive_highlight::{manifest.deep_dive_id}::{table_spec.id}",
    )
    highlight_value = None if highlighted_column == "Nenhuma" else highlighted_column

    top_cols = st.columns([1, 1, 4], gap="small")
    with top_cols[0]:
        st.download_button(
            "Baixar CSV",
            data=frame.to_csv(index=False).encode("utf-8"),
            file_name=f"{_safe_token(manifest.deep_dive_id)}_{_safe_token(table_spec.id)}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with top_cols[1]:
        try:
            pptx_bytes = build_deep_dive_pptx_bytes(
                manifest,
                [(table_spec, frame)],
                highlighted_column=highlight_value,
            )
            st.download_button(
                "Baixar PPTX",
                data=pptx_bytes,
                file_name=f"{_safe_token(manifest.deep_dive_id)}_{_safe_token(table_spec.id)}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                use_container_width=True,
            )
        except RuntimeError as exc:
            st.warning(str(exc))

    _render_comparison_table(frame, highlighted_column=highlight_value)

    with st.expander("Fontes e lacunas", expanded=False):
        if manifest.warnings:
            for warning in manifest.warnings:
                st.caption(f"- {warning}")
        st.dataframe(_source_files_df(manifest), hide_index=True, use_container_width=True)


def _render_manifest_header(manifest: Any) -> None:
    chips = [
        f"{len(manifest.funds)} fundo(s)",
        manifest.generated_at or "sem timestamp",
        manifest.source or "fonte offline",
        manifest.confidentiality,
    ]
    st.markdown(
        "<div class='deepdive-chip-row'>"
        + "".join(f"<span class='deepdive-chip'>{escape(chip)}</span>" for chip in chips if chip)
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_comparison_table(frame: pd.DataFrame, *, highlighted_column: str | None) -> None:
    header_cells = []
    for column in frame.columns:
        css_class = " class='highlight'" if column == highlighted_column else ""
        header_cells.append(f"<th{css_class}>{escape(str(column))}</th>")
    rows: list[str] = []
    for _, row in frame.iterrows():
        cells = []
        for column in frame.columns:
            css_class = " class='highlight'" if column == highlighted_column else ""
            cells.append(f"<td{css_class}>{escape(str(row.get(column, '—')))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(
        "<div class='deepdive-table-wrap'><table class='deepdive-table'><thead><tr>"
        + "".join(header_cells)
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>",
        unsafe_allow_html=True,
    )


def _source_files_df(manifest: Any) -> pd.DataFrame:
    rows = [
        {
            "Tabela": table.title,
            "Arquivo": str(Path(table.source_file)),
            "Tipo": table.kind,
        }
        for table in manifest.tables
    ]
    return pd.DataFrame(rows)


def _safe_token(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip().lower())
    return token.strip("_") or "deep_dive"
