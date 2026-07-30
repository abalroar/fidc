"""Operational queue for the manual curation of FIDC analytical taxonomies.

The panel this module feeds is deliberately independent of the published Office
bundle.  The bundle fails closed whenever the ledger changes — which is exactly
what curating does — so a queue that read from it would lock itself out after
the first decision.  Here the queue is built straight from the documentary
conclusions and the ledger, both plain CSV files in ``data/industry_study``.

Nothing in this module writes.  Persistence goes through
``commit_taxonomy_review_action``, which keeps the audit trail.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from services.industry_anbima import ANBIMA_TYPES
from services.industry_taxonomy_review import (
    ANALYTICAL_ANBIMA_FOCUS_BY_TYPE,
    CVM_TABLE_II_CATEGORIES,
    FUNCTIONAL_TAXONOMY,
    TAXONOMY_CONFIDENCE_LEVELS,
    load_taxonomy_review_actions,
    normalize_cnpj,
    taxonomy_review_id,
)


DEFAULT_DATA_DIR = Path("data/industry_study")
CONCLUSIONS_FILENAME = "industry_outros_reclassification_conclusions.csv"
PENDING_CURATION_FILENAME = "industry_top20_pending_curation.csv"

#: Recorded in ``responsavel`` when the queue is open and nobody signed.
ANONYMOUS_REVIEWER = "curadoria_manual_streamlit"
REVIEWER_PREFIX = "curadoria_manual_streamlit"
MAX_SIGNATURE_LENGTH = 48

#: Statuses that still ask for a human decision, in the order they are offered.
OPEN_STATUSES: tuple[str, ...] = ("em_revisao", "pendente")
DECISION_STATUSES: tuple[str, ...] = ("aprovado", "em_revisao", "pendente", "rejeitado")

QUEUE_COLUMNS: tuple[str, ...] = (
    "cnpj_fundo",
    "nome_fidc",
    "pl_max",
    "competencia_pl_max",
    "tipo_anbima_oficial",
    "foco_anbima_oficial",
    "status_atual",
    "responsavel_atual",
    "tipo_sugerido",
    "foco_sugerido",
    "tabela_ii_sugerida",
    "n1_sugerida",
    "n2_sugerida",
    "confianca",
    "justificativa",
    "evidencia",
    "pagina_clausula",
    "documentos_lidos",
    "family_scores",
    "limitacao",
    "motivo_revisao",
    "documento_url",
)


def _text(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    return "" if text.lower() == "nan" else text.strip()


def focus_options(anbima_type: str) -> tuple[str, ...]:
    """Focus values the ledger accepts for a given ANBIMA type."""

    return ANALYTICAL_ANBIMA_FOCUS_BY_TYPE.get(anbima_type, ())


def functional_level2_options(level1: str) -> tuple[str, ...]:
    """Functional N2 values the ledger accepts for a given N1."""

    return FUNCTIONAL_TAXONOMY.get(level1, ("",))


def taxonomy_vocabularies() -> dict[str, tuple[str, ...]]:
    """Every closed vocabulary the form must offer, so a save never fails."""

    return {
        "tipo": ANBIMA_TYPES,
        "tabela_ii": CVM_TABLE_II_CATEGORIES,
        "n1": tuple(FUNCTIONAL_TAXONOMY),
        "confianca": TAXONOMY_CONFIDENCE_LEVELS,
        "status": DECISION_STATUSES,
    }


def _load_conclusions(data_dir: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for filename in (CONCLUSIONS_FILENAME, PENDING_CURATION_FILENAME):
        path = data_dir / filename
        if not path.exists():
            continue
        frames.append(pd.read_csv(path, dtype=str, keep_default_na=False))
    if not frames:
        return pd.DataFrame()
    frame = pd.concat(frames, ignore_index=True)
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame["pl_max"] = pd.to_numeric(frame["pl_max"], errors="coerce").fillna(0.0)
    return (
        frame.sort_values("pl_max", ascending=False)
        .drop_duplicates("cnpj_fundo", keep="first")
        .reset_index(drop=True)
    )


def build_queue(data_dir: Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    """One row per CNPJ with a documentary conclusion, ordered by net assets.

    The ledger is the source of truth for the current status: a decision saved
    in the panel immediately changes where the fund appears, without rebuilding
    the conclusions file.
    """

    conclusions = _load_conclusions(Path(data_dir))
    if conclusions.empty:
        return pd.DataFrame(columns=list(QUEUE_COLUMNS))
    ledger = load_taxonomy_review_actions(Path(data_dir) / "taxonomy_review_actions.csv")
    if not ledger.empty:
        ledger = ledger.copy()
        ledger["cnpj_fundo"] = ledger["cnpj_fundo"].map(normalize_cnpj)
        ledger = ledger.drop_duplicates("cnpj_fundo", keep="last").set_index("cnpj_fundo")

    rows: list[dict[str, object]] = []
    for record in conclusions.to_dict(orient="records"):
        cnpj = str(record["cnpj_fundo"])
        saved = ledger.loc[cnpj] if not ledger.empty and cnpj in ledger.index else None

        def prefer(ledger_field: str, conclusion_field: str) -> str:
            if saved is not None and _text(saved.get(ledger_field)):
                return _text(saved.get(ledger_field))
            return _text(record.get(conclusion_field))

        rows.append(
            {
                "cnpj_fundo": cnpj,
                "nome_fidc": _text(record.get("nome_fidc")),
                "pl_max": float(record.get("pl_max") or 0.0),
                "competencia_pl_max": _text(record.get("competencia_pl_max")),
                "tipo_anbima_oficial": _text(record.get("tipo_anbima_oficial")),
                "foco_anbima_oficial": _text(record.get("foco_anbima_oficial")),
                "status_atual": (
                    _text(saved.get("status")) if saved is not None else ""
                ) or _text(record.get("decision_status")) or "pendente",
                "responsavel_atual": (
                    _text(saved.get("responsavel")) if saved is not None else ""
                ),
                "tipo_sugerido": prefer("tipo_analitico", "tipo_anbima_sugerido"),
                "foco_sugerido": prefer("foco_analitico", "foco_anbima_sugerido"),
                "tabela_ii_sugerida": prefer(
                    "tabela_ii_analitica", "tabela_ii_sugerida_documental"
                ),
                "n1_sugerida": prefer(
                    "taxonomia_funcional_n1", "taxonomia_funcional_n1_sugerida"
                ),
                "n2_sugerida": prefer(
                    "taxonomia_funcional_n2", "taxonomia_funcional_n2_sugerida"
                ),
                "confianca": prefer("confianca", "confianca_documental") or "media",
                "justificativa": _text(record.get("justificativa_curta")),
                "evidencia": prefer("evidencia", "evidence_summary"),
                "pagina_clausula": prefer("pagina_clausula", "pagina_clausula"),
                "documentos_lidos": _text(record.get("documentos_lidos")),
                "family_scores": _text(record.get("family_scores")),
                "limitacao": _text(record.get("source_limitations")),
                "motivo_revisao": _text(record.get("manual_validation_reason")),
                "documento_url": _text(record.get("document_url")),
            }
        )
    frame = pd.DataFrame(rows, columns=list(QUEUE_COLUMNS))
    return frame.sort_values("pl_max", ascending=False).reset_index(drop=True)


def queue_summary(queue: pd.DataFrame) -> dict[str, object]:
    """Counters and net assets by status, for the header of the panel."""

    if queue.empty:
        return {"total": 0, "abertos": 0, "pl_aberto": 0.0, "por_status": {}}
    open_mask = queue["status_atual"].isin(OPEN_STATUSES)
    return {
        "total": int(len(queue)),
        "abertos": int(open_mask.sum()),
        "pl_aberto": float(queue.loc[open_mask, "pl_max"].sum()),
        "pl_total": float(queue["pl_max"].sum()),
        "por_status": queue["status_atual"].value_counts().to_dict(),
    }


def filter_queue(
    queue: pd.DataFrame,
    *,
    statuses: tuple[str, ...] = OPEN_STATUSES,
    search: str = "",
) -> pd.DataFrame:
    """Apply the two filters the panel offers: status and free text."""

    if queue.empty:
        return queue
    frame = queue
    if statuses:
        frame = frame[frame["status_atual"].isin(statuses)]
    term = str(search or "").strip()
    if term:
        digits = "".join(character for character in term if character.isdigit())
        by_name = frame["nome_fidc"].str.contains(term, case=False, regex=False)
        by_cnpj = (
            frame["cnpj_fundo"].str.contains(digits, regex=False)
            if digits
            else pd.Series(False, index=frame.index)
        )
        frame = frame[by_name | by_cnpj]
    return frame.reset_index(drop=True)


def reviewer_responsible(signature: str) -> str:
    """Turn a free-text signature into a stable value for ``responsavel``.

    The queue is meant to be open: whoever holds the link reviews, with no login
    and no token.  That trades authentication for attribution, and attribution
    is the part worth keeping — a ledger where every decision is
    ``curadoria_manual_streamlit`` cannot tell you who decided what.  So the
    panel asks for a name and this function records it.

    It is a signature, not an identity.  Nothing verifies it, and the audit
    trail is what makes the claim checkable: an unsigned decision is honestly
    recorded as anonymous rather than attributed to someone who did not take it.
    """

    cleaned = _text(signature).casefold()
    kept = [
        character if (character.isalnum() or character in {".", "-", "_"}) else " "
        for character in cleaned
    ]
    slug = "-".join("".join(kept).split())[:MAX_SIGNATURE_LENGTH].strip("-")
    if not slug:
        return ANONYMOUS_REVIEWER
    return f"{REVIEWER_PREFIX}:{slug}"


def build_decision(
    row: pd.Series,
    *,
    status: str,
    tipo: str,
    foco: str,
    tabela_ii: str,
    n1: str,
    n2: str,
    confianca: str,
    justificativa: str,
    responsavel: str,
    saved_at_utc: str,
    motivo_override: str = "",
) -> dict[str, object]:
    """Assemble the ledger action for one manual decision.

    ``motivo_override`` leads the notes when the decision replaces an existing
    approval, mirroring the ``--override-reason`` the batch scripts demand.
    """

    cnpj = normalize_cnpj(row["cnpj_fundo"])
    notes = " ".join(
        part
        for part in (
            f"Sobrescreve aprovação anterior: {_text(motivo_override)}"
            if _text(motivo_override)
            else "",
            _text(justificativa),
            _text(row.get("limitacao")),
            f"Escores documentais: {_text(row.get('family_scores'))}."
            if _text(row.get("family_scores"))
            else "",
            f"Documentos lidos: {_text(row.get('documentos_lidos'))}."
            if _text(row.get("documentos_lidos"))
            else "",
        )
        if part
    )
    return {
        "review_id": taxonomy_review_id(cnpj),
        "competencia_referencia": _text(row.get("competencia_pl_max")) or "2026-06",
        "cnpj_fundo": cnpj,
        "denominacao_referencia": _text(row.get("nome_fidc")),
        "status": status,
        "tipo_analitico": _text(tipo),
        "foco_analitico": _text(foco),
        "tabela_ii_analitica": _text(tabela_ii),
        "taxonomia_funcional_n1": _text(n1),
        "taxonomia_funcional_n2": _text(n2),
        "confianca": _text(confianca),
        "documento_id": "",
        "fonte_documental": _text(row.get("documento_url")),
        "documento_data": "",
        "pagina_clausula": _text(row.get("pagina_clausula")),
        "evidencia": _text(row.get("evidencia"))[:6000],
        "cedente_originador_expresso": "",
        "notas": notes[:6000],
        "responsavel": responsavel,
        "competencia_inicio": "",
        "updated_at_utc": saved_at_utc,
    }
