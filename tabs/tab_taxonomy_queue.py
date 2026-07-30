"""Minimal panel to approve and edit the analytical taxonomy of a FIDC.

One fund at a time, five closed dropdowns, three buttons.  The panel reads the
documentary conclusions and the ledger directly from disk, so it keeps working
while the Office bundle is stale — publishing and curating are separate
concerns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from services.dashboard_ui import render_page_header
from services.industry_taxonomy_review import (
    commit_taxonomy_review_action,
    format_cnpj,
    validate_taxonomy_review_action,
)
from services.taxonomy_queue import (
    DECISION_STATUSES,
    OPEN_STATUSES,
    build_decision,
    build_queue,
    filter_queue,
    focus_options,
    functional_level2_options,
    queue_summary,
    taxonomy_vocabularies,
)


_DATA_DIR = Path("data/industry_study")
_LEDGER_PATH = _DATA_DIR / "taxonomy_review_actions.csv"
_AUDIT_PATH = _DATA_DIR / "taxonomy_review_audit.csv"

_STATUS_LABELS = {
    "em_revisao": "Em revisão",
    "pendente": "Pendente",
    "aprovado": "Aprovado",
    "rejeitado": "Rejeitado",
}


def _fmt_bi(value: float) -> str:
    return f"R$ {value / 1e9:,.2f} bi".replace(",", "@").replace(".", ",").replace("@", ".")


def _index_of(options: tuple[str, ...], value: str, default: int = 0) -> int:
    try:
        return options.index(value)
    except ValueError:
        return default


@st.cache_data(ttl=5, show_spinner=False)
def _cached_queue(ledger_signature: float) -> pd.DataFrame:
    return build_queue(_DATA_DIR)


def _ledger_signature() -> float:
    try:
        return _LEDGER_PATH.stat().st_mtime
    except OSError:
        return 0.0


def render_tab_taxonomy_queue() -> None:
    render_page_header(
        "Fila de taxonomia",
        "Aprove ou edite a classificação analítica de cada FIDC. Os campos "
        "oficiais da ANBIMA e da CVM não são alterados.",
    )

    queue = _cached_queue(_ledger_signature())
    if queue.empty:
        st.info(
            "Nenhuma conclusão documental encontrada em "
            f"`{_DATA_DIR}`. Rode `scripts/build_fidc_outros_reclassification.py`."
        )
        return

    summary = queue_summary(queue)
    left, middle, right = st.columns(3)
    left.metric("A decidir", f"{summary['abertos']:,}".replace(",", "."))
    middle.metric("PL a decidir", _fmt_bi(float(summary["pl_aberto"])))
    right.metric(
        "Decididos",
        f"{summary['total'] - summary['abertos']:,}".replace(",", ".")
        + f" de {summary['total']:,}".replace(",", "."),
    )

    flash = st.session_state.pop("taxonomy_queue_flash", "")
    if flash:
        st.success(flash)

    filter_column, search_column = st.columns([2, 3])
    with filter_column:
        show_all = st.toggle(
            "Incluir já decididos",
            value=False,
            help="Permite reabrir um fundo aprovado ou rejeitado para editar.",
        )
    with search_column:
        search = st.text_input(
            "Buscar por nome ou CNPJ", value="", placeholder="ex.: Cobuccio ou 29242769"
        )

    statuses = DECISION_STATUSES if show_all else OPEN_STATUSES
    filtered = filter_queue(queue, statuses=statuses, search=search)
    if filtered.empty:
        st.success("Nada a decidir com os filtros atuais.")
        return

    options = filtered["cnpj_fundo"].tolist()
    cursor_key = "taxonomy-queue-cursor"
    if st.session_state.get(cursor_key) not in options:
        st.session_state[cursor_key] = options[0]
    labels = {
        str(row["cnpj_fundo"]): (
            f"{_fmt_bi(float(row['pl_max']))} · {row['nome_fidc'][:70]} · "
            f"{_STATUS_LABELS.get(row['status_atual'], row['status_atual'])}"
        )
        for _, row in filtered.iterrows()
    }
    selected_cnpj = st.selectbox(
        f"{len(filtered)} fundos na fila",
        options,
        format_func=lambda value: labels[value],
        key=cursor_key,
    )
    row = filtered[filtered["cnpj_fundo"].eq(selected_cnpj)].iloc[0]

    st.markdown(f"### {row['nome_fidc']}")
    st.caption(
        f"{format_cnpj(selected_cnpj)} · {_fmt_bi(float(row['pl_max']))} em "
        f"{row['competencia_pl_max']} · ANBIMA oficial: "
        f"{row['tipo_anbima_oficial'] or 'N/D'} | {row['foco_anbima_oficial'] or 'N/D'}"
        + (f" · situação: {_STATUS_LABELS.get(row['status_atual'], row['status_atual'])}")
    )
    if row["documento_url"]:
        st.caption(f"[Documentos no FundosNet]({row['documento_url']})")

    if row["justificativa"]:
        st.markdown(f"**Leitura automática** — {row['justificativa']}")
    with st.expander("Evidência documental", expanded=False):
        st.write(row["evidencia"] or "Sem evidência registrada.")
        if row["pagina_clausula"]:
            st.caption(f"Páginas: {row['pagina_clausula']}")
        if row["family_scores"]:
            st.caption(f"Escores por família: {row['family_scores']}")
        if row["documentos_lidos"]:
            st.caption(f"Documentos lidos: {row['documentos_lidos']}")
        if row["limitacao"]:
            st.caption(f"Limitação: {row['limitacao']}")
        if row["motivo_revisao"]:
            st.caption(f"Motivo da revisão: {row['motivo_revisao']}")

    vocab = taxonomy_vocabularies()
    type_column, focus_column = st.columns(2)
    with type_column:
        tipo = st.selectbox(
            "Tipo ANBIMA",
            vocab["tipo"],
            index=_index_of(vocab["tipo"], row["tipo_sugerido"]),
            key=f"tq-tipo-{selected_cnpj}",
        )
    focus_choices = focus_options(tipo)
    with focus_column:
        foco = st.selectbox(
            "Foco ANBIMA",
            focus_choices,
            index=_index_of(focus_choices, row["foco_sugerido"]),
            key=f"tq-foco-{selected_cnpj}-{tipo}",
        )

    table_column, level1_column, level2_column = st.columns(3)
    with table_column:
        tabela_ii = st.selectbox(
            "Tabela II",
            vocab["tabela_ii"],
            index=_index_of(vocab["tabela_ii"], row["tabela_ii_sugerida"] or "N/D"),
            key=f"tq-tabela-{selected_cnpj}",
        )
    with level1_column:
        n1_choices = vocab["n1"]
        n1 = st.selectbox(
            "Funcional N1",
            n1_choices,
            index=_index_of(n1_choices, row["n1_sugerida"]),
            key=f"tq-n1-{selected_cnpj}",
        )
    n2_choices = functional_level2_options(n1)
    with level2_column:
        n2 = st.selectbox(
            "Funcional N2",
            n2_choices,
            index=_index_of(n2_choices, row["n2_sugerida"]),
            key=f"tq-n2-{selected_cnpj}-{n1}",
        )

    confidence_column, note_column = st.columns([1, 3])
    with confidence_column:
        confidence_choices = tuple(
            level for level in vocab["confianca"] if level
        )
        confianca = st.selectbox(
            "Confiança",
            confidence_choices,
            index=_index_of(confidence_choices, row["confianca"], default=1),
            key=f"tq-conf-{selected_cnpj}",
        )
    with note_column:
        justificativa = st.text_input(
            "Justificativa da decisão",
            value=row["justificativa"],
            key=f"tq-just-{selected_cnpj}",
        )

    approve, review, reject, skip = st.columns(4)
    decision: str | None = None
    if approve.button("Aprovar e próximo", type="primary", width="stretch"):
        decision = "aprovado"
    if review.button("Manter em revisão", width="stretch"):
        decision = "em_revisao"
    if reject.button("Rejeitar", width="stretch"):
        decision = "rejeitado"
    if skip.button("Pular", width="stretch"):
        position = options.index(selected_cnpj)
        st.session_state[cursor_key] = options[(position + 1) % len(options)]
        st.rerun()

    if decision is None:
        return

    action = build_decision(
        row,
        status=decision,
        tipo=tipo,
        foco=foco,
        tabela_ii=tabela_ii,
        n1=n1,
        n2=n2,
        confianca=confianca,
        justificativa=justificativa,
        responsavel="curadoria_manual_streamlit",
        saved_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )
    try:
        validate_taxonomy_review_action(action)
    except ValueError as error:
        st.error(f"Combinação inválida: {error}")
        return

    commit_taxonomy_review_action(
        action,
        _LEDGER_PATH,
        _AUDIT_PATH,
        saved_at_utc=str(action["updated_at_utc"]),
        source="taxonomy_queue_streamlit",
    )
    _cached_queue.clear()
    remaining = [cnpj for cnpj in options if cnpj != selected_cnpj]
    st.session_state[cursor_key] = remaining[0] if remaining else options[0]
    st.session_state["taxonomy_queue_flash"] = (
        f"{row['nome_fidc'][:60]} gravado como "
        f"{_STATUS_LABELS.get(decision, decision)}."
    )
    st.rerun()
