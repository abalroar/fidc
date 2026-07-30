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
from services.ledger_publisher import (
    publish_decisions,
    repository_status,
    resolve_push_credential,
)
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
    reviewer_responsible,
    taxonomy_vocabularies,
)


_ROOT = Path(__file__).resolve().parents[1]
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


def _secrets() -> dict[str, object]:
    try:
        return dict(st.secrets)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 - no secrets file is a normal setup.
        return {}


def _publish(reason: str) -> None:
    """Commit and push the ledger, recording the outcome for the next run."""

    result = publish_decisions(_ROOT, message=reason, secrets=_secrets())
    st.session_state["taxonomy_queue_publish_flash"] = (
        ("ok" if result.pushed else "erro"),
        result.detail,
    )


def _render_publish_controls() -> None:
    status = repository_status(_ROOT)
    if not status.is_repository:
        st.caption(
            "As decisões são gravadas nos CSV do ledger. Este diretório não é um "
            f"repositório git ({status.detail}), então a publicação é manual."
        )
        return

    auto_key = "taxonomy-queue-autopublish"
    control, toggle_column = st.columns([3, 2])
    with toggle_column:
        st.toggle(
            "Publicar a cada decisão",
            key=auto_key,
            help=(
                "Faz commit e push do ledger no repositório logo após gravar, "
                f"na branch {status.branch}."
            ),
        )
    with control:
        if status.has_pending:
            st.warning(
                f"{len(status.pending_files)} arquivo(s) do ledger com decisões "
                f"ainda não publicadas em {status.branch}.",
                icon=":material/cloud_upload:",
            )
            if st.button("Publicar no repositório", width="stretch"):
                _publish("Curadoria manual de taxonomia pela fila do app")
                st.rerun()
        else:
            st.caption(f"Ledger sincronizado com o último commit de {status.branch}.")

    credential = resolve_push_credential(_ROOT, _secrets())
    st.caption(
        ("Token dos secrets em uso. " if credential.configured else "")
        + credential.detail
    )


def _render_bundle_notice() -> None:
    """Warn that curating invalidates the published Office bundle.

    The bundle records the ledger hash and refuses to serve once the curation
    moves past it, which takes the industry screen offline until someone
    republishes.  Saying so here, next to the decisions that cause it, is
    cheaper than discovering it in the other tab.
    """

    try:
        from services.industry_revision_export import get_revision_export_status

        status = get_revision_export_status(_DATA_DIR)
    except Exception:  # noqa: BLE001
        return
    if getattr(status, "bundle_valid", False):
        return
    with st.expander(
        "A tela Dados da Indústria precisa do bundle republicado", expanded=False
    ):
        st.write(
            "O pacote Office publicado guarda o hash do ledger e recusa servir "
            "quando a curadoria avança além dele. Curar aqui é justamente o que "
            "faz o hash mudar. A fila de taxonomia não depende do pacote e "
            "continua funcionando; a tela Dados da Indústria fica indisponível "
            "até a republicação, que exige o runtime Node do Codex."
        )
        st.code(
            "python3 scripts/publish_fidc_revision_bundle.py \\\n"
            "    --input-workbook ~/Downloads/Industria_FIDC_Dados_202607.xlsx \\\n"
            "    --skip-download",
            language="bash",
        )


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
    publish_flash = st.session_state.pop("taxonomy_queue_publish_flash", None)
    if publish_flash is not None:
        level, detail = publish_flash
        (st.success if level == "ok" else st.error)(detail)

    _render_publish_controls()
    _render_bundle_notice()

    signature = st.text_input(
        "Quem está revisando",
        key="taxonomy-queue-signature",
        placeholder="seu nome ou apelido",
        help=(
            "Assinatura, não login: fica gravada em cada decisão para que o "
            "ledger diga quem decidiu o quê. Em branco, a decisão é registrada "
            "como anônima."
        ),
    )
    responsavel = reviewer_responsible(signature)

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

    # Reabrir um fundo já aprovado é o único caminho pelo qual a fila aberta
    # pode destruir trabalho concluído. Exigir motivo explícito aqui espelha o
    # --override-reason que os scripts em lote cobram.
    overriding = str(row["status_atual"]) == "aprovado"
    motivo_override = ""
    if overriding:
        st.warning(
            "Este fundo já está aprovado"
            + (f" por {row['responsavel_atual']}." if row["responsavel_atual"] else ".")
            + " Gravar por cima exige um motivo.",
            icon=":material/lock_reset:",
        )
        motivo_override = st.text_input(
            "Motivo para sobrescrever a aprovação",
            key=f"tq-override-{selected_cnpj}",
            placeholder="o que na evidência mudou a conclusão",
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
    if overriding and not motivo_override.strip():
        st.error(
            "Informe o motivo antes de sobrescrever uma aprovação. A decisão "
            "anterior foi preservada."
        )
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
        responsavel=responsavel,
        saved_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        motivo_override=motivo_override,
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
    if st.session_state.get("taxonomy-queue-autopublish"):
        _publish(
            f"Curadoria manual: {row['nome_fidc'][:60]} como "
            f"{_STATUS_LABELS.get(decision, decision)}"
        )
    st.rerun()
