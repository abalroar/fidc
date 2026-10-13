"""Documentos tab: comparative table built from reviewed per-fund facts."""
from __future__ import annotations

import re
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from services.documentary_facts import (
    FACTS_DIR, IME_NOTE, build_view, competence_label, facts_csv_bytes, facts_zip_bytes, view_frames,
)

NOTE_CSS = (
    "<style>.facts-box{border-left:3px solid #ff6200;background:#fff7f1;padding:0.55rem 0.8rem;margin:0.3rem 0 0.6rem;"
    "font-size:0.9rem;color:#202020}.facts-box p{margin:0.15rem 0}.facts-foot{font-size:0.78rem;color:#6b6b6b;"
    "margin:0.15rem 0 0.2rem;line-height:1.35}.facts-foot strong{color:#4a4a4a}</style>"
)


def _table(title: str, frame: pd.DataFrame, number: int) -> str:
    from tabs.tab_deep_dive import _comparison_table_html
    return _comparison_table_html(title, frame, number, raw_values=True, min_column_px=150)


def _box(title: str, lines: list[str]) -> None:
    if lines:
        items = "".join(f"<p>· {escape(line)}</p>" for line in lines)
        st.markdown(f"<div class='facts-box'><p><strong>{escape(title)}</strong></p>{items}</div>", unsafe_allow_html=True)


def _foot(label: str, text: str) -> None:
    if text:
        st.markdown(f"<div class='facts-foot'><strong>{escape(label)}</strong> {escape(text)}</div>", unsafe_allow_html=True)


def _evidence(section, key: str) -> None:
    funds = list(dict.fromkeys(item["fund"] for item in section.evidence))
    if not funds:
        return
    with st.expander("Texto integral e fontes", expanded=False):
        chosen = st.selectbox("Fundo", funds, index=None, placeholder="Escolha um fundo para ver os trechos",
                              key=f"facts_evidence::{key}", label_visibility="collapsed")
        if not chosen:
            return
        for item in section.evidence:
            if item["fund"] != chosen:
                continue
            source = escape(item["source"])
            if item["url"]:
                source = f"<a href='{escape(item['url'], quote=True)}' target='_blank' rel='noopener noreferrer'>{source}</a>"
            st.markdown(f"**{escape(item['row'])}** — {escape(item['display'])}<br><span class='facts-foot'>{source}</span>",
                        unsafe_allow_html=True)
            st.markdown(f"> {escape(item['excerpt'])}")


def render_documentary_facts(portfolio: Any) -> None:
    view = build_view(portfolio)
    st.markdown("### Documentos")
    st.markdown(NOTE_CSS, unsafe_allow_html=True)
    if view.competence:
        st.caption(f"Leitura documental por fundo, com fonte em cada célula. Confronto com o IME de "
                   f"{competence_label(view.competence)}, posição comum da cesta.")
    else:
        st.caption("Leitura documental por fundo, com fonte em cada célula. Sem competência de IME comum à cesta; confronto suspenso.")
    st.caption("— não se aplica ao fundo · n/d não localizado nos documentos lidos (motivo em Pendências)")
    if view.missing:
        names = ", ".join(c.short for c in view.columns if c.cnpj in view.missing)
        st.info(f"Fundo ainda sem leitura documental: {names}. A comparação mostra os demais e inclui este fundo na fila de leitura.")

    token = re.sub(r"[^A-Za-z0-9_-]", "", str(getattr(portfolio, "id", "carteira")))
    readings = [(c.short, c.leitura) for c in view.columns if c.leitura]
    if view.layout == "single" and readings:
        _box("Leitura de crédito", [readings[0][1]])
    elif view.layout == "side_by_side" and readings:
        frame = pd.DataFrame([["Leitura de crédito", *[c.leitura or "—" for c in view.columns]]],
                             columns=["Critério", *[c.short for c in view.columns]])
        st.markdown(_table("Leitura de crédito", frame, 0), unsafe_allow_html=True)

    if view.layout == "transposed":
        frame = pd.DataFrame(view.transposed)
        st.markdown(_table(f"Comparativo da cesta ({len(view.columns)} fundos)", frame, 1), unsafe_allow_html=True)
        notes = [line for section in view.sections for line in section.differences]
        _box("O que difere", notes[:6])
        _foot("Nota:", IME_NOTE)
        with st.expander("Leitura de crédito por fundo", expanded=False):
            st.dataframe(pd.DataFrame(readings, columns=["Fundo", "Leitura de crédito"]), hide_index=True, width="stretch")
    else:
        frames = view_frames(view)
        for number, ((title, frame, notes), section) in enumerate(zip(frames, view.sections), start=1):
            st.markdown(_table(title, frame, number), unsafe_allow_html=True)
            _box("Onde o fundo se afasta dos pares" if view.layout == "single" else "O que difere", section.differences)
            for note in notes:
                _foot("Nota:", note)
            _foot("Fontes:", " | ".join(section.sources))
            _evidence(section, f"{token}::{number}")

    if view.pending:
        with st.expander(f"Pendências ({len(view.pending)})", expanded=False):
            st.dataframe(pd.DataFrame(view.pending).rename(columns={"fund": "Fundo", "row": "Critério", "reason": "Motivo"}),
                         hide_index=True, width="stretch")

    with st.expander("Downloads", expanded=False):
        _downloads(portfolio, view, token)


def _downloads(portfolio: Any, view, token: str) -> None:
    from services.on_demand_download import current_download_store, download_context_signature, render_native_deferred_download
    paths = tuple(FACTS_DIR / f"{c.cnpj}.json" for c in view.columns)
    signature = download_context_signature(getattr(portfolio, "id", ""), tuple(c.cnpj for c in view.columns), view.competence, source_paths=paths)
    namespace = "documentary_facts"
    store = current_download_store(st.session_state, namespace=namespace, signature=signature)
    render_native_deferred_download(store=store, namespace=namespace, artifact="facts_csv", label="Comparativo e fontes (CSV)",
                                    file_name=f"documentos_{token}.csv", mime="text/csv", producer=lambda: facts_csv_bytes(view))
    render_native_deferred_download(store=store, namespace=namespace, artifact="facts_zip", label="Fatos e trechos completos (JSON em ZIP)",
                                    file_name=f"documentos_{token}.zip", mime="application/zip", producer=lambda: facts_zip_bytes(view))
    render_native_deferred_download(store=store, namespace=namespace, artifact="facts_pptx", label="Comparativo (PPTX)",
                                    file_name=f"documentos_{token}.pptx",
                                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                    producer=lambda: facts_pptx_bytes(portfolio, view))


def facts_comparison_content(portfolio: Any, view=None):
    """(manifest, pages) for the PowerPoint export, mirroring the screen layout."""
    from services.deep_dive_store import DeepDiveManifest
    from services.document_curation_comparison import DocumentComparisonPage
    view = view or build_view(portfolio)
    funds = [{"cnpj": c.cnpj, "name": c.name, "short_name": c.short} for c in view.columns]
    manifest = DeepDiveManifest.from_dict({
        "schema_version": 1, "deep_dive_id": f"documentary_facts_{getattr(portfolio, 'id', 'carteira')}",
        "title": "Documentos · " + str(getattr(portfolio, "name", "Carteira")), "generated_at": "",
        "portfolio_id": getattr(portfolio, "id", ""), "source": "Leitura documental por fundo; IME " + competence_label(view.competence),
        "funds": funds}, package_dir=FACTS_DIR.parent.parent)
    pages = []
    if view.layout == "transposed":
        frame = pd.DataFrame(view.transposed)
        for start in range(0, len(frame), 20):
            pages.append(DocumentComparisonPage("Comparativo da cesta", frame.iloc[start:start + 20].reset_index(drop=True),
                                                (IME_NOTE,), (), preserve_typed_statuses=True))
    else:
        for (title, frame, notes), section in zip(view_frames(view), view.sections):
            pages.append(DocumentComparisonPage(title, frame, tuple(notes) + tuple(section.differences), tuple(section.sources),
                                                preserve_typed_statuses=True))
    return manifest, pages


def facts_pptx_bytes(portfolio: Any, view) -> bytes:
    from services.deep_dive_ppt_export import build_document_comparison_pptx_bytes
    manifest, pages = facts_comparison_content(portfolio, view)
    return build_document_comparison_pptx_bytes(manifest, pages, portfolio_mode=True, compact=False)
