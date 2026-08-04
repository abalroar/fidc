"""Auditable analytical overlay for the FIDC ANBIMA/CVM taxonomies.

Official ANBIMA and CVM fields remain immutable.  Analysts work in a separate
ledger and only approved, traceable decisions affect the analytical mix used by
the next Office bundle.  The same module materializes the Top 20 by displayed
ANBIMA Type and the 100 largest funds behind the ``Outros`` bucket on slide 8.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Mapping
import unicodedata
import uuid

import pandas as pd

from services.industry_anbima import (
    ANBIMA_FOCUS_BY_TYPE,
    ANBIMA_TYPES,
    normalize_anbima_focus,
    normalize_anbima_type,
)
from services.industry_revision_analysis import TABLE_II_RECEIVABLE_COLUMNS


ANBIMA_REFERENCE_DATE = "2025-12-29"
DISPLAY_TYPES: tuple[str, ...] = ANBIMA_TYPES
CVM_TABLE_II_CATEGORIES: tuple[str, ...] = (
    *TABLE_II_RECEIVABLE_COLUMNS.values(),
    "Adquirência",
    "N/D",
)

TAXONOMY_REVIEW_COLUMNS: tuple[str, ...] = (
    "review_id",
    "competencia_referencia",
    "cnpj_fundo",
    "denominacao_referencia",
    "status",
    "tipo_analitico",
    "foco_analitico",
    "tabela_ii_analitica",
    "taxonomia_funcional_n1",
    "taxonomia_funcional_n2",
    "confianca",
    "documento_id",
    "fonte_documental",
    "documento_data",
    "pagina_clausula",
    "evidencia",
    "cedente_originador_expresso",
    "notas",
    "responsavel",
    "competencia_inicio",
    "updated_at_utc",
)
TAXONOMY_REVIEW_KEY_COLUMN = "review_id"
TAXONOMY_REVIEW_STATUSES: tuple[str, ...] = (
    "pendente",
    "em_revisao",
    "aprovado",
    "rejeitado",
)
TAXONOMY_CONFIDENCE_LEVELS: tuple[str, ...] = ("", "baixa", "media", "alta")
ANALYTICAL_ANBIMA_FOCUS_BY_TYPE: Mapping[str, tuple[str, ...]] = {
    **ANBIMA_FOCUS_BY_TYPE,
    "Financeiro": (
        *ANBIMA_FOCUS_BY_TYPE["Financeiro"],
        "Adquirência",
        "Crédito PF",
        "Cartão de crédito",
    ),
    "Outros": (
        *ANBIMA_FOCUS_BY_TYPE["Outros"],
        "Multicedente/Multissacado",
    ),
}
TAXONOMY_REVIEW_AUDIT_COLUMNS: tuple[str, ...] = (
    "event_id",
    "saved_at_utc",
    "review_domain",
    "record_id",
    "field",
    "old_value",
    "new_value",
    "status_after",
    "source",
)

FUNCTIONAL_TAXONOMY: Mapping[str, tuple[str, ...]] = {
    "": ("",),
    "Agro": ("Agro",),
    "Crédito PF": (
        "Auto/Veículos",
        "Consignado/INSS",
        "Crédito estudantil",
        "Crédito pessoal/consumo",
        "Crédito PF parcelado / BNPL",
        "FGTS",
    ),
    "Crédito PJ": (
        "CCB/Notas comerciais/Capital de giro",
        "Recebíveis comerciais/multissetorial",
        "Risco sacado/fornecedores",
        "Crédito privado/mercado de capitais",
    ),
    "Imobiliário": ("Imobiliário",),
    "Infra/Energia": ("Energia/infra",),
    "Judicial/Precatórios/NPL": (
        "Não padronizado/NPL",
        "Precatórios/direitos judiciais",
    ),
    "Meios de Pagamento e Cartões": (
        "Arranjos de pagamento/adquirência",
        "Bancos Emissores",
        "Banco emissor/cartão de crédito",
    ),
    "Multissetorial / Outros": (
        "Multicarteira outros",
        "Multicarteira financeiro",
    ),
}


def normalize_analytical_anbima_focus(value: object) -> str:
    """Normalize a review focus without expanding the official ANBIMA vocabulary."""

    normalized = unicodedata.normalize("NFKD", _text(value))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    analytical = {
        "adquirencia": "Adquirência",
        "credito pf": "Crédito PF",
        "cartao de credito": "Cartão de crédito",
        "multicedente/multissacado": "Multicedente/Multissacado",
    }
    if normalized.casefold() in analytical:
        return analytical[normalized.casefold()]
    return normalize_anbima_focus(value)


def valid_analytical_type_focus_pair(anbima_type: object, focus: object) -> bool:
    normalized_type = normalize_anbima_type(anbima_type)
    normalized_focus = normalize_analytical_anbima_focus(focus)
    return bool(
        normalized_type
        and normalized_focus
        and normalized_focus in ANALYTICAL_ANBIMA_FOCUS_BY_TYPE[normalized_type]
    )


def normalize_cnpj(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    raw = str(value).strip()
    if re.fullmatch(r"\d{1,14}(?:\.0+)?", raw):
        raw = raw.split(".", 1)[0]
    digits = re.sub(r"\D", "", raw)
    return digits.zfill(14)[-14:] if digits else ""


def _normalize_review_cnpj(value: object) -> str:
    """Normalize a ledger key without truncating or accepting arbitrary text."""

    raw = _text(value)
    if not raw:
        return ""
    if re.fullmatch(r"[0-9]{1,14}(?:\.0+)?", raw):
        digits = raw.split(".", 1)[0]
    elif re.fullmatch(
        r"[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2}",
        raw,
    ):
        digits = re.sub(r"[^0-9]", "", raw)
    else:
        digits = re.sub(r"[^0-9]", "", raw)
        if len(digits) > 14:
            raise ValueError("CNPJ do fundo não pode conter mais de 14 dígitos")
        raise ValueError(
            "CNPJ do fundo deve usar somente dígitos ou a máscara 00.000.000/0000-00"
        )
    return digits.zfill(14)


def _safe_normalize_review_cnpj(value: object) -> str:
    try:
        return _normalize_review_cnpj(value)
    except ValueError:
        return ""


def format_cnpj(value: object) -> str:
    digits = normalize_cnpj(value)
    if len(digits) != 14:
        return digits
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return re.sub(r"\s+", " ", str(value).strip())


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).casefold() in {"1", "true", "sim", "yes"}


def _fold_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", _text(value))
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def _meaningful_documentary_text(value: object) -> bool:
    folded = re.sub(r"[^a-z0-9]+", " ", _fold_text(value)).strip()
    if not folded:
        return False
    sentinels = {
        "n d",
        "nd",
        "n a",
        "na",
        "ausente",
        "nao informado",
        "nao informada",
        "nao localizado",
        "nao localizada",
        "sem documento",
        "sem evidencia",
        "pendente",
        "a definir",
        "nao disponivel",
        "aguardando documento",
    }
    return folded not in sentinels and not any(
        folded.startswith(prefix)
        for prefix in (
            "n d ",
            "nao localizado ",
            "nao localizada ",
            "sem documento ",
            "sem evidencia ",
            "pendente ",
            "a definir ",
            "nao disponivel ",
            "aguardando documento ",
        )
    )


def _valid_month_competence(value: object) -> bool:
    competence = _text(value)
    match = re.fullmatch(r"([0-9]{4})-([0-9]{2})", competence)
    return bool(match and 1 <= int(match.group(2)) <= 12)


def taxonomy_review_id(cnpj_or_competence: object, cnpj: object | None = None) -> str:
    """Return the stable CNPJ key used by the consolidated taxonomy ledger.

    The optional second argument keeps old callers readable while migrating
    historical period-aware identifiers.  Competence is provenance only.
    """

    value = cnpj if cnpj is not None else cnpj_or_competence
    return _normalize_review_cnpj(value)


def _safe_taxonomy_review_id(cnpj_or_competence: object, cnpj: object | None = None) -> str:
    try:
        return taxonomy_review_id(cnpj_or_competence, cnpj)
    except ValueError:
        return ""


def _blank_actions() -> pd.DataFrame:
    return pd.DataFrame(columns=list(TAXONOMY_REVIEW_COLUMNS))


def load_taxonomy_review_actions(path: Path) -> pd.DataFrame:
    """Load one current action per unique fund CNPJ."""

    path = Path(path)
    if not path.exists() or not path.stat().st_size:
        return _blank_actions()
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    for column in TAXONOMY_REVIEW_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[list(TAXONOMY_REVIEW_COLUMNS)].copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(_normalize_review_cnpj)
    frame["competencia_referencia"] = frame["competencia_referencia"].where(
        frame["competencia_referencia"].astype(str).str.strip().ne(""),
        frame["competencia_inicio"],
    )
    frame["review_id"] = frame["cnpj_fundo"].map(_safe_taxonomy_review_id)
    frame = frame[frame["review_id"].ne("")]
    frame["_updated_at"] = pd.to_datetime(
        frame["updated_at_utc"], errors="coerce", utc=True
    )
    return (
        frame.sort_values(["_updated_at", "competencia_referencia"])
        .drop_duplicates("review_id", keep="last")
        .drop(columns="_updated_at")
        .reset_index(drop=True)
    )


def validate_taxonomy_review_action(action: Mapping[str, object]) -> None:
    cnpj = _normalize_review_cnpj(action.get("cnpj_fundo"))
    if len(cnpj) != 14:
        raise ValueError("CNPJ do fundo deve conter 14 dígitos")
    status = _text(action.get("status")) or "pendente"
    if status not in TAXONOMY_REVIEW_STATUSES:
        raise ValueError(f"status de revisão inválido: {status}")
    confidence = _text(action.get("confianca"))
    if confidence and confidence not in TAXONOMY_CONFIDENCE_LEVELS:
        raise ValueError(f"confiança inválida: {confidence}")
    competence_reference = _text(action.get("competencia_referencia"))
    if competence_reference and not _valid_month_competence(competence_reference):
        raise ValueError("competência de referência deve seguir AAAA-MM")
    review_id = taxonomy_review_id(cnpj)
    supplied_review_id = _text(action.get("review_id"))
    if supplied_review_id and supplied_review_id != review_id:
        raise ValueError("review_id incompatível com o CNPJ")
    functional_n1 = _text(action.get("taxonomia_funcional_n1"))
    functional_n2 = _text(action.get("taxonomia_funcional_n2"))
    if functional_n1 not in FUNCTIONAL_TAXONOMY:
        raise ValueError(f"taxonomia funcional N1 inválida: {functional_n1}")
    if status == "aprovado" and (not functional_n1 or not functional_n2):
        raise ValueError("aprovação requer taxonomia funcional N1 e N2")
    if functional_n2 not in FUNCTIONAL_TAXONOMY[functional_n1]:
        raise ValueError("taxonomia funcional N2 incompatível com N1")
    table_ii = _text(action.get("tabela_ii_analitica"))
    if table_ii and table_ii not in CVM_TABLE_II_CATEGORIES:
        raise ValueError(f"categoria analítica da Tabela II inválida: {table_ii}")
    if status != "aprovado":
        return
    if not table_ii:
        raise ValueError("aprovação requer categoria analítica da Tabela II")
    anbima_type = normalize_anbima_type(action.get("tipo_analitico"))
    anbima_focus = normalize_analytical_anbima_focus(action.get("foco_analitico"))
    if (
        not anbima_type
        or not anbima_focus
        or not valid_analytical_type_focus_pair(anbima_type, anbima_focus)
    ):
        raise ValueError("Tipo e Foco analíticos formam uma combinação inválida")
    competence = _text(action.get("competencia_inicio"))
    if competence and not _valid_month_competence(competence):
        raise ValueError("competência inicial deve seguir AAAA-MM")
    document_date = _text(action.get("documento_data"))
    if document_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", document_date):
        raise ValueError("data do documento deve seguir AAAA-MM-DD")
    if not document_date:
        return
    try:
        parsed_date = pd.Timestamp(document_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("data do documento inválida") from exc
    if parsed_date.strftime("%Y-%m-%d") != document_date:
        raise ValueError("data do documento inválida")


def _prepare_taxonomy_review_actions(actions: pd.DataFrame | None) -> pd.DataFrame:
    out = _blank_actions() if actions is None else actions.copy()
    for column in TAXONOMY_REVIEW_COLUMNS:
        if column not in out.columns:
            out[column] = ""
    out = out[list(TAXONOMY_REVIEW_COLUMNS)].fillna("").astype(str)
    if out.empty:
        return out
    out["cnpj_fundo"] = out["cnpj_fundo"].map(_normalize_review_cnpj)
    out["competencia_referencia"] = out["competencia_referencia"].where(
        out["competencia_referencia"].str.strip().ne(""),
        out["competencia_inicio"],
    )
    out["competencia_inicio"] = out["competencia_inicio"].where(
        out["competencia_inicio"].str.strip().ne(""),
        out["competencia_referencia"],
    )
    out["review_id"] = out["cnpj_fundo"].map(taxonomy_review_id)
    out["status"] = out["status"].replace("", "pendente")
    out = out[out["review_id"].ne("")].drop_duplicates("review_id", keep="last")
    for action in out.to_dict(orient="records"):
        validate_taxonomy_review_action(action)
    return out.sort_values(["status", "cnpj_fundo"]).reset_index(drop=True)


@contextmanager
def _taxonomy_review_ledger_lock(path: Path):
    """Serialize writers through a stable sidecar lock file."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _write_taxonomy_review_actions(actions: pd.DataFrame, path: Path) -> None:
    """Replace the ledger atomically using a process/thread-unique temporary."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.tmp-{os.getpid()}-{threading.get_ident()}-",
        suffix=".csv",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            actions.to_csv(handle, index=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def save_taxonomy_review_actions(actions: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Persist a ledger fixture without audit; production writes use ``commit``."""

    path = Path(path)
    out = _prepare_taxonomy_review_actions(actions)
    with _taxonomy_review_ledger_lock(path):
        _write_taxonomy_review_actions(out, path)
    return out


def upsert_taxonomy_review_action(
    action: Mapping[str, object],
    path: Path,
) -> pd.DataFrame:
    """Upsert a ledger fixture without audit; production writes use ``commit``."""

    path = Path(path)
    candidate = pd.DataFrame([dict(action)], columns=list(TAXONOMY_REVIEW_COLUMNS))
    candidate = _prepare_taxonomy_review_actions(candidate)
    if len(candidate) != 1:
        raise ValueError("upsert requer uma ação com CNPJ válido")
    review_id = str(candidate.iloc[0]["review_id"])
    with _taxonomy_review_ledger_lock(path):
        current = load_taxonomy_review_actions(path)
        updated = pd.concat(
            [
                current[~current["review_id"].astype(str).eq(review_id)],
                candidate,
            ],
            ignore_index=True,
        )
        out = _prepare_taxonomy_review_actions(updated)
        _write_taxonomy_review_actions(out, path)
    return out


def load_taxonomy_review_audit(path: Path) -> pd.DataFrame:
    """Load the field-level taxonomy audit with a stable schema."""

    path = Path(path)
    if not path.exists() or not path.stat().st_size:
        return pd.DataFrame(columns=list(TAXONOMY_REVIEW_AUDIT_COLUMNS))
    audit = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    for column in TAXONOMY_REVIEW_AUDIT_COLUMNS:
        if column not in audit.columns:
            audit[column] = ""
    return audit[list(TAXONOMY_REVIEW_AUDIT_COLUMNS)].copy()


def _taxonomy_audit_event_id(
    row: Mapping[str, object],
    *,
    transaction_id: str,
) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
        raise ValueError("UUID da transação de auditoria inválido")
    event_key = "|".join(
        _text(row.get(column))
        for column in (
            "review_domain",
            "record_id",
            "field",
            "saved_at_utc",
            "old_value",
            "new_value",
            "status_after",
            "source",
        )
    )
    digest = hashlib.sha1(event_key.encode("utf-8", errors="ignore")).hexdigest()[:20]
    return f"{transaction_id}:{digest}"


def _recover_prepared_taxonomy_audit(
    audit: pd.DataFrame,
    ledger: pd.DataFrame,
) -> pd.DataFrame:
    """Resolve an interrupted two-file commit from its explicit audit marker."""

    if audit.empty or not audit["source"].astype(str).str.contains(":prepared:", regex=False).any():
        return audit.copy()
    recovered = audit.copy()
    ledger_by_review_id = ledger.set_index("review_id", drop=False)
    prepared_sources = recovered.loc[
        recovered["source"].astype(str).str.contains(":prepared:", regex=False),
        "source",
    ].drop_duplicates()
    for prepared_source in prepared_sources:
        mask = recovered["source"].eq(prepared_source)
        events = recovered[mask]
        record_ids = events["record_id"].drop_duplicates().tolist()
        committed = (
            len(record_ids) == 1 and record_ids[0] in ledger_by_review_id.index
        )
        if committed:
            ledger_row = ledger_by_review_id.loc[record_ids[0]]
            committed = all(
                _text(ledger_row.get(field)) == _text(new_value)
                for field, new_value in zip(events["field"], events["new_value"], strict=True)
            )
        if not committed:
            recovered = recovered[~mask].copy()
            continue
        base_source, transaction_id = str(prepared_source).split(":prepared:", 1)
        recovered.loc[mask, "source"] = base_source
        recovered.loc[mask, "event_id"] = recovered.loc[mask].apply(
            lambda row: _taxonomy_audit_event_id(
                row,
                transaction_id=transaction_id,
            ),
            axis=1,
        )
    return recovered.drop_duplicates("event_id", keep="last").reset_index(drop=True)


def commit_taxonomy_review_action(
    action: Mapping[str, object],
    ledger_path: Path,
    audit_path: Path,
    *,
    saved_at_utc: str,
    source: str = "industry_taxonomy_review",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Persist one decision and its field-level audit under the same locks.

    The audit file is replaced first and rolled back if the ledger replacement
    fails.  This prevents an applied decision from existing without its audit
    events while preserving concurrent decisions for other funds.
    """

    from services.industry_study import build_review_audit_events  # Local import avoids module cycle.

    ledger_path = Path(ledger_path)
    audit_path = Path(audit_path)
    candidate = pd.DataFrame([dict(action)], columns=list(TAXONOMY_REVIEW_COLUMNS))
    candidate = _prepare_taxonomy_review_actions(candidate)
    if len(candidate) != 1:
        raise ValueError("commit requer uma ação com CNPJ válido")
    review_id = str(candidate.iloc[0]["review_id"])

    with _taxonomy_review_ledger_lock(ledger_path):
        with _taxonomy_review_ledger_lock(audit_path):
            previous = load_taxonomy_review_actions(ledger_path)
            updated = pd.concat(
                [
                    previous[~previous["review_id"].astype(str).eq(review_id)],
                    candidate,
                ],
                ignore_index=True,
            )
            updated = _prepare_taxonomy_review_actions(updated)
            previous_audit = _recover_prepared_taxonomy_audit(
                load_taxonomy_review_audit(audit_path),
                previous,
            )
            transaction_id = uuid.uuid4().hex
            transaction_source = f"{source}:prepared:{transaction_id}"
            events = build_review_audit_events(
                previous=previous,
                updated=updated,
                key_column="review_id",
                review_domain="taxonomy_review",
                saved_at_utc=saved_at_utc,
                source=transaction_source,
            )
            next_audit = pd.concat(
                [previous_audit, events[list(TAXONOMY_REVIEW_AUDIT_COLUMNS)]],
                ignore_index=True,
            ).drop_duplicates("event_id", keep="last")
            _write_taxonomy_review_actions(next_audit, audit_path)
            try:
                _write_taxonomy_review_actions(updated, ledger_path)
            except Exception:
                _write_taxonomy_review_actions(previous_audit, audit_path)
                raise
            committed_mask = next_audit["source"].eq(transaction_source)
            next_audit.loc[committed_mask, "source"] = source
            next_audit.loc[committed_mask, "event_id"] = next_audit.loc[
                committed_mask
            ].apply(
                lambda row: _taxonomy_audit_event_id(
                    row,
                    transaction_id=transaction_id,
                ),
                axis=1,
            )
            committed_event_ids = set(
                next_audit.loc[committed_mask, "event_id"].astype(str)
            )
            next_audit = next_audit.drop_duplicates("event_id", keep="last")
            _write_taxonomy_review_actions(next_audit, audit_path)
            events = next_audit[
                next_audit["event_id"].astype(str).isin(committed_event_ids)
            ].copy()
    return updated, events.reset_index(drop=True)


def commit_taxonomy_review_actions(
    actions: pd.DataFrame,
    ledger_path: Path,
    audit_path: Path,
    *,
    saved_at_utc: str,
    source: str = "industry_taxonomy_review",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Persist many decisions as one transaction, with the same guarantees.

    ``commit_taxonomy_review_action`` rewrites the ledger and the audit once per
    decision, which is quadratic and unusable for a whole-queue reprocessing.
    This variant computes the field-level diff for every CNPJ at once and
    replaces both files a single time, keeping the audit-first ordering, the
    rollback on failure and the prepared/committed event identifiers.
    """

    from services.industry_study import build_review_audit_events  # Local import avoids module cycle.

    ledger_path = Path(ledger_path)
    audit_path = Path(audit_path)
    candidate = _prepare_taxonomy_review_actions(actions)
    if candidate.empty:
        return (
            load_taxonomy_review_actions(ledger_path),
            load_taxonomy_review_audit(audit_path).head(0),
        )
    review_ids = set(candidate["review_id"].astype(str))

    with _taxonomy_review_ledger_lock(ledger_path):
        with _taxonomy_review_ledger_lock(audit_path):
            previous = load_taxonomy_review_actions(ledger_path)
            updated = pd.concat(
                [
                    previous[~previous["review_id"].astype(str).isin(review_ids)],
                    candidate,
                ],
                ignore_index=True,
            )
            updated = _prepare_taxonomy_review_actions(updated)
            previous_audit = _recover_prepared_taxonomy_audit(
                load_taxonomy_review_audit(audit_path),
                previous,
            )
            transaction_id = uuid.uuid4().hex
            transaction_source = f"{source}:prepared:{transaction_id}"
            events = build_review_audit_events(
                previous=previous,
                updated=updated,
                key_column="review_id",
                review_domain="taxonomy_review",
                saved_at_utc=saved_at_utc,
                source=transaction_source,
            )
            next_audit = pd.concat(
                [previous_audit, events[list(TAXONOMY_REVIEW_AUDIT_COLUMNS)]],
                ignore_index=True,
            ).drop_duplicates("event_id", keep="last")
            _write_taxonomy_review_actions(next_audit, audit_path)
            try:
                _write_taxonomy_review_actions(updated, ledger_path)
            except Exception:
                _write_taxonomy_review_actions(previous_audit, audit_path)
                raise
            committed_mask = next_audit["source"].eq(transaction_source)
            next_audit.loc[committed_mask, "source"] = source
            next_audit.loc[committed_mask, "event_id"] = next_audit.loc[
                committed_mask
            ].apply(
                lambda row: _taxonomy_audit_event_id(
                    row,
                    transaction_id=transaction_id,
                ),
                axis=1,
            )
            committed_event_ids = set(
                next_audit.loc[committed_mask, "event_id"].astype(str)
            )
            next_audit = next_audit.drop_duplicates("event_id", keep="last")
            _write_taxonomy_review_actions(next_audit, audit_path)
            events = next_audit[
                next_audit["event_id"].astype(str).isin(committed_event_ids)
            ].copy()
    return updated, events.reset_index(drop=True)


def taxonomy_review_ledger_digest(path: Path) -> str:
    frame = load_taxonomy_review_actions(path)
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def taxonomy_review_audit_digest(path: Path) -> str:
    audit = load_taxonomy_review_audit(path)
    payload = audit.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def taxonomy_review_audit_has_pending(path: Path) -> bool:
    audit = load_taxonomy_review_audit(path)
    return bool(
        not audit.empty
        and audit["source"].astype(str).str.contains(":prepared:", regex=False).any()
    )


def assert_taxonomy_review_ledger_matches_audit(
    ledger_path: Path,
    audit_path: Path,
) -> None:
    """Fail closed unless the ledger is exactly reproducible from its audit."""

    ledger = _prepare_taxonomy_review_actions(
        load_taxonomy_review_actions(Path(ledger_path))
    )
    audit = load_taxonomy_review_audit(Path(audit_path))
    if taxonomy_review_audit_has_pending(Path(audit_path)):
        raise ValueError(
            "auditoria de taxonomia contém transação preparada e não reconciliada"
        )
    if audit["event_id"].astype(str).duplicated().any():
        raise ValueError("auditoria de taxonomia contém event_id duplicado")

    state: dict[str, dict[str, str]] = {}
    valid_fields = set(TAXONOMY_REVIEW_COLUMNS).difference({"review_id"})
    for row_number, row in enumerate(audit.to_dict(orient="records"), start=2):
        if _text(row.get("review_domain")) != "taxonomy_review":
            raise ValueError(
                f"auditoria de taxonomia possui domínio inválido na linha {row_number}"
            )
        record_id = _text(row.get("record_id"))
        record_match = re.fullmatch(r"[0-9]{14}", record_id)
        if not record_match:
            raise ValueError(
                f"auditoria de taxonomia possui review_id inválido na linha {row_number}"
            )
        field = _text(row.get("field"))
        if field not in valid_fields:
            raise ValueError(
                f"auditoria de taxonomia possui campo inválido na linha {row_number}"
            )
        event_id = _text(row.get("event_id"))
        event_match = re.fullmatch(r"([0-9a-f]{32}):([0-9a-f]{20})", event_id)
        if not event_match or _taxonomy_audit_event_id(
            row,
            transaction_id=event_match.group(1) if event_match else "",
        ) != event_id:
            raise ValueError(
                f"auditoria de taxonomia possui event_id inválido na linha {row_number}"
            )
        record_state = state.setdefault(
            record_id,
            {column: "" for column in valid_fields},
        )
        old_value = _text(row.get("old_value"))
        if record_state[field] != old_value:
            raise ValueError(
                f"auditoria de taxonomia rompe a cadeia de old_value na linha {row_number}"
            )
        record_state[field] = _text(row.get("new_value"))

    reconstructed = _prepare_taxonomy_review_actions(
        pd.DataFrame(
            [
                {"review_id": record_id, **values}
                for record_id, values in state.items()
            ],
            columns=list(TAXONOMY_REVIEW_COLUMNS),
        )
    )
    ledger_payload = ledger.to_csv(index=False, lineterminator="\n")
    audit_payload = reconstructed.to_csv(index=False, lineterminator="\n")
    if ledger_payload != audit_payload:
        raise ValueError(
            "ledger de taxonomia não é reproduzível pela trilha de auditoria"
        )


def _display_type(value: object) -> str:
    normalized = normalize_anbima_type(value)
    return normalized if normalized in set(ANBIMA_TYPES).difference({"Outros"}) else "Outros"


def _effective_actions(actions: pd.DataFrame | None) -> pd.DataFrame:
    frame = _blank_actions() if actions is None else actions.copy()
    if frame.empty:
        return frame
    for column in TAXONOMY_REVIEW_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(_safe_normalize_review_cnpj)
    frame = frame[
        frame["status"].astype(str).str.strip().eq("aprovado")
    ].copy()
    valid = frame.apply(
        lambda row: valid_analytical_type_focus_pair(
            row.get("tipo_analitico"), row.get("foco_analitico")
        ),
        axis=1,
    )
    frame = frame.loc[valid.fillna(False).astype(bool)].copy()
    if frame.empty:
        return frame
    frame["_updated_at"] = pd.to_datetime(
        frame.get("updated_at_utc"), errors="coerce", utc=True
    )
    return (
        frame.sort_values(["_updated_at", "competencia_referencia"])
        .drop_duplicates("cnpj_fundo", keep="last")
        .drop(columns="_updated_at")
    )


def apply_taxonomy_review_overlay(
    funds: pd.DataFrame,
    actions: pd.DataFrame | None,
) -> pd.DataFrame:
    """Add effective analytical fields while preserving every official field."""

    if funds is None or funds.empty:
        return pd.DataFrame() if funds is None else funds.copy()
    frame = funds.copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    # The payload/export path may apply this overlay more than once. Preserve
    # the original official fields rather than promoting a curated display
    # value to official status on a later pass.
    frame["anbima_tipo_oficial"] = frame.get(
        "anbima_tipo_oficial",
        frame.get("anbima_tipo", pd.Series("", index=frame.index)),
    ).map(_text)
    frame["anbima_foco_oficial"] = frame.get(
        "anbima_foco_oficial",
        frame.get("anbima_foco", pd.Series("", index=frame.index)),
    ).map(_text)
    frame["anbima_tipo_curado"] = frame["anbima_tipo_oficial"]
    frame["anbima_foco_curado"] = frame["anbima_foco_oficial"]
    frame["tabela_ii_curada"] = frame.get(
        "tabela_ii_dominante", pd.Series("N/D", index=frame.index)
    ).map(lambda value: _text(value) or "N/D")
    frame["taxonomia_funcional_n1_curada"] = ""
    frame["taxonomia_funcional_n2_curada"] = ""
    frame["taxonomy_review_status"] = "pendente"
    frame["taxonomy_review_applied"] = False
    action_frame = _effective_actions(actions)
    if not action_frame.empty:
        # Validate once per decision, then map by CNPJ. The historical fund
        # base has hundreds of thousands of rows; assigning Arrow-backed
        # strings one cell at a time is both quadratic and memory intensive.
        valid_rows: list[dict[str, object]] = []
        for action in action_frame.to_dict(orient="records"):
            try:
                validate_taxonomy_review_action(action)
            except ValueError:
                continue
            valid_rows.append(action)
        action_frame = pd.DataFrame(valid_rows)
    if not action_frame.empty:
        action_frame = action_frame.drop_duplicates("cnpj_fundo", keep="last").set_index(
            "cnpj_fundo"
        )
        keys = frame["cnpj_fundo"]
        applied = keys.isin(action_frame.index)

        def mapped(column: str) -> pd.Series:
            return keys.map(action_frame[column].to_dict())

        mapped_type = mapped("tipo_analitico").map(normalize_anbima_type)
        mapped_focus = mapped("foco_analitico").map(
            normalize_analytical_anbima_focus
        )
        mapped_table_ii = mapped("tabela_ii_analitica").map(_text)
        mapped_n1 = mapped("taxonomia_funcional_n1").map(_text)
        mapped_n2 = mapped("taxonomia_funcional_n2").map(_text)
        frame["anbima_tipo_curado"] = frame["anbima_tipo_curado"].where(
            ~applied, mapped_type
        )
        frame["anbima_foco_curado"] = frame["anbima_foco_curado"].where(
            ~applied, mapped_focus
        )
        valid_table_ii = applied & mapped_table_ii.isin(CVM_TABLE_II_CATEGORIES)
        frame["tabela_ii_curada"] = frame["tabela_ii_curada"].where(
            ~valid_table_ii, mapped_table_ii
        )
        frame["taxonomia_funcional_n1_curada"] = frame[
            "taxonomia_funcional_n1_curada"
        ].where(~applied, mapped_n1)
        frame["taxonomia_funcional_n2_curada"] = frame[
            "taxonomia_funcional_n2_curada"
        ].where(~applied, mapped_n2)
        frame["taxonomy_review_status"] = frame["taxonomy_review_status"].where(
            ~applied, "aprovado"
        )
        frame["taxonomy_review_applied"] = applied
    frame["manual_override_applied"] = frame["taxonomy_review_applied"]
    return frame


def _latest_regulations(document_inventory: pd.DataFrame | None) -> pd.DataFrame:
    if document_inventory is None or document_inventory.empty:
        return pd.DataFrame(columns=["cnpj_fundo", "inventario_documento_id", "inventario_documento_data", "inventario_documento_origem"])
    frame = document_inventory.copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame = frame[
        frame.get("document_class", pd.Series("", index=frame.index)).astype(str).str.casefold().eq("regulamento")
        & frame.get("local_exists", pd.Series(False, index=frame.index)).map(_bool)
    ].copy()
    if frame.empty:
        return pd.DataFrame(columns=["cnpj_fundo", "inventario_documento_id", "inventario_documento_data", "inventario_documento_origem"])
    frame["_document_date"] = pd.to_datetime(frame.get("document_date"), errors="coerce")
    frame = frame.sort_values(
        ["cnpj_fundo", "_document_date", "documento_id"],
        ascending=[True, False, False],
        na_position="last",
    ).drop_duplicates("cnpj_fundo", keep="first")
    return frame.rename(
        columns={
            "documento_id": "inventario_documento_id",
            "document_date": "inventario_documento_data",
            "documento_origem": "inventario_documento_origem",
        }
    )[["cnpj_fundo", "inventario_documento_id", "inventario_documento_data", "inventario_documento_origem"]]


def _originator_evidence(
    curated_top20: pd.DataFrame | None,
    regulation_review: pd.DataFrame | None,
    card_curation: pd.DataFrame | None = None,
    document_review: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if curated_top20 is not None and not curated_top20.empty:
        for row in curated_top20.to_dict(orient="records"):
            rows.append(
                {
                    "cnpj_fundo": normalize_cnpj(row.get("cnpj_fundo") or row.get("cnpj_classe")),
                    "cedente_originador": _text(row.get("cedente_originador")) or "N/D",
                    "cedente_status": "curadoria_documental_concluida",
                    "regulamento_id": _text(row.get("documentos_primarios_ids")),
                    "regulamento_data": "",
                    "regulamento_url": _text(row.get("fundosnet_gerenciador") or row.get("fonte")),
                    "pagina_clausula": "N/D — não registrada na curadoria disponível",
                    "evidencia_cedente": _text(row.get("nota_classificacao")),
                    "confianca_cedente": "N/D — curadoria sem nível publicado",
                    "limitacao_cedente": _text(row.get("campos_nao_identificados")),
                    "_priority": 1,
                }
            )
    if regulation_review is not None and not regulation_review.empty:
        for row in regulation_review.to_dict(orient="records"):
            rows.append(
                {
                    "cnpj_fundo": normalize_cnpj(row.get("cnpj_fundo")),
                    "cedente_originador": _text(row.get("cedent_originator_explicit")) or "N/D",
                    "cedente_status": "curadoria_documental_concluida",
                    "regulamento_id": _text(row.get("document_id")),
                    "regulamento_data": _text(row.get("document_reference_date")),
                    "regulamento_url": _text(row.get("document_url")),
                    "pagina_clausula": "N/D — não registrada na curadoria disponível",
                    "evidencia_cedente": _text(row.get("evidence_summary")),
                    "confianca_cedente": "N/D — curadoria sem nível publicado",
                    "limitacao_cedente": _text(row.get("manual_validation_reason") or row.get("source_limitations")),
                    "_priority": 2,
                }
            )
    if card_curation is not None and not card_curation.empty:
        cards = card_curation[
            ~card_curation.get(
                "status_curadoria", pd.Series("Pendente", index=card_curation.index)
            ).astype(str).str.strip().eq("Pendente")
        ]
        for row in cards.to_dict(orient="records"):
            source_name = _text(row.get("fonte_documento"))
            source_id = "".join(re.findall(r"\d+", source_name))
            rows.append(
                {
                    "cnpj_fundo": normalize_cnpj(row.get("cnpj14_digits")),
                    "cedente_originador": _text(row.get("cedente_originador")) or "N/D",
                    "cedente_status": "curadoria_documental_concluida",
                    "regulamento_id": source_id,
                    "regulamento_data": _text(row.get("fonte_data")),
                    "regulamento_url": _text(row.get("fonte_url")),
                    "pagina_clausula": "N/D — não registrada na curadoria disponível",
                    "evidencia_cedente": _text(row.get("evidencia_curta")),
                    "confianca_cedente": _text(row.get("confianca")) or "N/D",
                    "limitacao_cedente": _text(row.get("decisao_curadoria")),
                    "_priority": 3,
                }
            )
    if document_review is not None and not document_review.empty:
        for row in document_review.to_dict(orient="records"):
            historical_automation = _text(row.get("review_scope")).startswith(
                "top20_por_tipo_periodos_"
            )
            automated = (
                historical_automation
                and _meaningful_documentary_text(row.get("document_id"))
                and _text(row.get("reading_method")).startswith(
                    "leitura integral automatizada"
                )
            )
            if historical_automation and not automated:
                continue
            rows.append(
                {
                    "cnpj_fundo": normalize_cnpj(row.get("cnpj_fundo")),
                    "cedente_originador": _text(
                        row.get("cedent_originator_explicit")
                    )
                    or "N/D",
                    "cedente_status": (
                        "leitura_automatizada_pendente_validacao"
                        if automated
                        else "curadoria_documental_concluida"
                    ),
                    "regulamento_id": _text(row.get("document_id")),
                    "regulamento_data": _text(row.get("document_reference_date")),
                    "regulamento_url": _text(
                        row.get("document_url") or row.get("local_path")
                    ),
                    "pagina_clausula": _text(row.get("pagina_clausula"))
                    or "N/D — página não recuperável",
                    "evidencia_cedente": _text(row.get("evidence_summary")),
                    "confianca_cedente": _text(row.get("confianca_documental"))
                    or "N/D",
                    "limitacao_cedente": _text(
                        row.get("manual_validation_reason")
                        or row.get("source_limitations")
                    ),
                    "_priority": 0 if automated else 4,
                }
            )
    if not rows:
        return pd.DataFrame()
    return (
        pd.DataFrame(rows)
        .sort_values(["cnpj_fundo", "_priority"])
        .drop_duplicates("cnpj_fundo", keep="last")
        .drop(columns="_priority")
    )


def build_top20_by_anbima_type(
    funds: pd.DataFrame,
    *,
    latest: str,
    actions: pd.DataFrame | None = None,
    curated_top20: pd.DataFrame | None = None,
    regulation_review: pd.DataFrame | None = None,
    document_inventory: pd.DataFrame | None = None,
    card_curation: pd.DataFrame | None = None,
    document_review: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return 20 funds for each of the four categories displayed on slide 8."""

    current = funds[
        funds["competencia"].astype(str).eq(latest)
        & ~funds["is_fic_fidc"].map(_bool)
    ].copy()
    current["pl"] = pd.to_numeric(current["pl"], errors="coerce")
    current["cnpj_fundo"] = current["cnpj_fundo"].map(normalize_cnpj)
    current = apply_taxonomy_review_overlay(current, actions)
    current["tipo_exibicao"] = current["anbima_tipo_curado"].map(_display_type)
    # O denominador deve reconciliar com o slide 8, que soma o universo ex-FIC
    # completo, inclusive saldos zero ou negativos. Esses saldos não são
    # elegíveis ao ranking, mas permanecem no total auditável do bucket.
    type_totals = current.groupby("tipo_exibicao")["pl"].sum(min_count=1)
    current = current[current["pl"].gt(0)].copy()
    current = current.sort_values(
        ["tipo_exibicao", "pl", "cnpj_fundo"],
        ascending=[True, False, True],
    )
    current["rank_tipo"] = current.groupby("tipo_exibicao").cumcount() + 1
    top = current[current["rank_tipo"].le(20)].copy()
    if set(top["tipo_exibicao"]) != set(DISPLAY_TYPES) or len(top) != 80:
        raise ValueError("Top 20 por Tipo deve conter 80 linhas nas quatro categorias")
    if top["cnpj_fundo"].duplicated().any():
        raise ValueError("Top 20 por Tipo contém CNPJ repetido")
    previous_competence = str(pd.Period(latest, freq="M") - 1)
    previous = funds[
        funds["competencia"].astype(str).eq(previous_competence)
        & ~funds["is_fic_fidc"].map(_bool)
    ].copy()
    previous["pl"] = pd.to_numeric(previous["pl"], errors="coerce")
    previous["cnpj_fundo"] = previous["cnpj_fundo"].map(normalize_cnpj)
    previous_positive = set(previous.loc[previous["pl"].gt(0), "cnpj_fundo"])
    top["pl_anterior_positivo"] = top["cnpj_fundo"].isin(previous_positive)
    if not top["pl_anterior_positivo"].all():
        raise ValueError(
            f"{latest} não possui cobertura integral após verificar {previous_competence}"
        )
    top["pl_tipo_brl"] = top["tipo_exibicao"].map(type_totals)
    top["share_tipo"] = top["pl"] / top["pl_tipo_brl"]

    evidence = _originator_evidence(
        curated_top20,
        regulation_review,
        card_curation,
        document_review,
    )
    if not evidence.empty:
        top = top.merge(evidence, on="cnpj_fundo", how="left", validate="one_to_one")
    latest_regulations = _latest_regulations(document_inventory)
    top = top.merge(latest_regulations, on="cnpj_fundo", how="left", validate="one_to_one")
    for column in (
        "cedente_originador",
        "cedente_status",
        "regulamento_id",
        "regulamento_data",
        "regulamento_url",
        "pagina_clausula",
        "evidencia_cedente",
        "confianca_cedente",
        "limitacao_cedente",
        "inventario_documento_id",
        "inventario_documento_data",
        "inventario_documento_origem",
    ):
        if column not in top:
            top[column] = ""
        top[column] = top[column].fillna("").map(_text)
    has_curated = top["cedente_status"].eq("curadoria_documental_concluida")
    has_automated = top["cedente_status"].eq(
        "leitura_automatizada_pendente_validacao"
    )
    has_local = top["inventario_documento_id"].ne("")
    top.loc[~has_curated & ~has_automated, "cedente_originador"] = "N/D"
    top.loc[~has_curated & ~has_automated & has_local, "cedente_status"] = "regulamento_local_sem_curadoria_concluida"
    top.loc[~has_curated & ~has_automated & ~has_local, "cedente_status"] = "regulamento_nao_localizado_no_corpus_versionado"
    top.loc[~has_curated & ~has_automated & has_local, "limitacao_cedente"] = (
        "Regulamento local inventariado; leitura curada de cedente/originador ainda não concluída."
    )
    top.loc[~has_curated & ~has_automated & ~has_local, "limitacao_cedente"] = (
        "Documento oficial não localizado no corpus versionado em 28/jul/26; nome do fundo e prestadores não foram usados como inferência."
    )
    top.loc[top["regulamento_id"].eq(""), "regulamento_id"] = top["inventario_documento_id"]
    top.loc[top["regulamento_data"].eq(""), "regulamento_data"] = top["inventario_documento_data"]
    top["regulamento_url"] = top["regulamento_url"].where(
        top["regulamento_url"].ne(""),
        top["cnpj_fundo"].map(
            lambda cnpj: "https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM?cnpjFundo=" + cnpj
        ),
    )
    top["classification_reference_date"] = top["classification_tier"].map(
        lambda value: ANBIMA_REFERENCE_DATE if _text(value) == "oficial_anbima" else latest
    )
    top["classification_limitation"] = top.get(
        "classification_warning", pd.Series("", index=top.index)
    ).fillna("").map(_text)
    top["administrador"] = top.get("admin_nome", pd.Series("", index=top.index)).fillna("").map(_text).replace("", "N/D")
    top["gestor"] = top.get("gestor_nome", pd.Series("", index=top.index)).fillna("").map(_text).replace("", "N/D")
    top["custodiante"] = top.get("custodiante_nome", pd.Series("", index=top.index)).fillna("").map(_text).replace("", "N/D")
    top["administrador_source"] = f"CVM, Informe Mensal FIDC, Tabela I, {latest}"
    top["gestor_source"] = "Cadastro vigente carregado em 21/jul/26; fotografia cadastral"
    top["custodiante_source"] = "Cadastro vigente carregado em 21/jul/26; fotografia cadastral"
    top["pl_source"] = f"CVM, Informe Mensal FIDC, Tabela IV, {latest}; CNPJ do fundo com classes agregadas"
    top["competencia_pl"] = latest
    top["cnpj_fundo_formatado"] = top["cnpj_fundo"].map(format_cnpj)
    top["cedente_originador_qtd"] = pd.NA

    output_columns = (
        "tipo_exibicao",
        "rank_tipo",
        "cnpj_fundo",
        "cnpj_fundo_formatado",
        "denominacao",
        "pl",
        "pl_tipo_brl",
        "share_tipo",
        "competencia_pl",
        "pl_anterior_positivo",
        "pl_source",
        "anbima_tipo",
        "anbima_foco",
        "anbima_tipo_oficial",
        "anbima_foco_oficial",
        "anbima_tipo_curado",
        "anbima_foco_curado",
        "tabela_ii_curada",
        "taxonomia_funcional_n1_curada",
        "taxonomia_funcional_n2_curada",
        "taxonomy_review_applied",
        "classification_tier",
        "classification_status",
        "classification_source",
        "classification_reference_date",
        "classification_limitation",
        "cnpj_classe_count",
        "administrador",
        "admin_cnpj",
        "administrador_source",
        "gestor",
        "gestor_cnpj",
        "gestor_source",
        "custodiante",
        "custodiante_cnpj",
        "custodiante_source",
        "cedente_originador",
        "cedente_originador_qtd",
        "cedente_status",
        "regulamento_id",
        "regulamento_data",
        "regulamento_url",
        "pagina_clausula",
        "evidencia_cedente",
        "confianca_cedente",
        "limitacao_cedente",
    )
    for column in output_columns:
        if column not in top:
            top[column] = ""
    output = top.loc[:, output_columns].sort_values(
        ["tipo_exibicao", "rank_tipo"],
        key=lambda series: series.map({name: index for index, name in enumerate(DISPLAY_TYPES)})
        if series.name == "tipo_exibicao"
        else series,
    ).reset_index(drop=True)

    coverage_rows: list[dict[str, object]] = []
    for type_name in (*DISPLAY_TYPES, "Total"):
        scoped = output if type_name == "Total" else output[output["tipo_exibicao"].eq(type_name)]
        coverage_rows.append(
            {
                "tipo_exibicao": type_name,
                "fundos": int(len(scoped)),
                "pl_brl": float(pd.to_numeric(scoped["pl"], errors="coerce").sum()),
                "administrador_preenchido": int(scoped["administrador"].ne("N/D").sum()),
                "gestor_preenchido": int(scoped["gestor"].ne("N/D").sum()),
                "custodiante_preenchido": int(scoped["custodiante"].ne("N/D").sum()),
                "cedente_curadoria_concluida": int(scoped["cedente_status"].eq("curadoria_documental_concluida").sum()),
                "regulamento_local_sem_curadoria": int(scoped["cedente_status"].eq("regulamento_local_sem_curadoria_concluida").sum()),
                "sem_regulamento_local": int(scoped["cedente_status"].eq("regulamento_nao_localizado_no_corpus_versionado").sum()),
                "competencia_pl": latest,
                "competencia_anterior_verificada": previous_competence,
                "fundos_pl_anterior_positivo": int(scoped["pl_anterior_positivo"].sum()),
                "criterio_competencia": "jun/26 é a competência completa mais recente e possui PL positivo para 80/80 fundos; mai/26 também cobre 80/80",
            }
        )
    return output, pd.DataFrame(coverage_rows)


def _table_ii_by_fund(table_ii: pd.DataFrame | None, latest: str) -> pd.DataFrame:
    columns = list(TABLE_II_RECEIVABLE_COLUMNS)
    if table_ii is None or table_ii.empty or not set(columns).issubset(table_ii.columns):
        return pd.DataFrame(columns=["cnpj_fundo", "tabela_ii_reportada", "tabela_ii_dominante", "tabela_ii_multisegmento"])
    frame = table_ii[table_ii["competencia"].astype(str).eq(latest)].copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    grouped = frame.groupby("cnpj_fundo", as_index=False)[columns].sum()
    positive = grouped[columns].gt(0)
    grouped["tabela_ii_segmentos_positivos"] = positive.sum(axis=1)
    grouped["tabela_ii_multisegmento"] = grouped["tabela_ii_segmentos_positivos"].gt(1)
    grouped["tabela_ii_dominante"] = grouped[columns].idxmax(axis=1).map(TABLE_II_RECEIVABLE_COLUMNS)
    grouped.loc[grouped["tabela_ii_segmentos_positivos"].eq(0), "tabela_ii_dominante"] = "N/D"

    def reported(row: pd.Series) -> str:
        parts = [
            f"{TABLE_II_RECEIVABLE_COLUMNS[column]}: {float(row[column]):.2f}"
            for column in columns
            if float(row[column]) > 0
        ]
        return " | ".join(parts) if parts else "N/D — nenhuma categoria positiva observada"

    grouped["tabela_ii_reportada"] = grouped.apply(reported, axis=1)
    return grouped


def _documentary_top20(regulation_review: pd.DataFrame | None) -> pd.DataFrame:
    if regulation_review is None or regulation_review.empty:
        return pd.DataFrame()
    frame = regulation_review.copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame["status_revisao_documental"] = frame["reclassification_status"].map(
        {
            "potencial_reclassificação": "validacao_manual",
            "manter_em_outros": "manter_em_outros",
            "validação_manual": "validacao_manual",
        }
    ).fillna("validacao_manual")
    frame["confianca_documental"] = frame["reclassification_status"].map(
        {
            "potencial_reclassificação": "media",
            "manter_em_outros": "media",
            "validação_manual": "baixa",
        }
    ).fillna("baixa")
    proposed_pairs: dict[int, tuple[str, str, str, str]] = {
        1: ("Agro, Indústria e Comércio", "Recebíveis Comerciais", "Meios de Pagamento e Cartões", "Arranjos de pagamento/adquirência"),
        2: ("Agro, Indústria e Comércio", "Crédito Corporativo", "Crédito PJ", "Crédito privado/mercado de capitais"),
        4: ("Agro, Indústria e Comércio", "Recebíveis Comerciais", "Meios de Pagamento e Cartões", "Arranjos de pagamento/adquirência"),
        6: ("Agro, Indústria e Comércio", "Recebíveis Comerciais", "Meios de Pagamento e Cartões", "Arranjos de pagamento/adquirência"),
        9: ("Agro, Indústria e Comércio", "Recebíveis Comerciais", "Crédito PJ", "Recebíveis comerciais/multissetorial"),
    }
    keep_focus: dict[int, tuple[str, str, str, str]] = {
        3: ("Outros", "Recuperação", "Judicial/Precatórios/NPL", "Precatórios/direitos judiciais"),
        5: ("Outros", "Recuperação", "Judicial/Precatórios/NPL", "Não padronizado/NPL"),
        7: ("Outros", "Multicarteira Outros", "Multissetorial / Outros", "Multicarteira outros"),
        10: ("Outros", "Multicarteira Outros", "Multissetorial / Outros", "Multicarteira outros"),
        15: ("Outros", "Multicarteira Outros", "Multissetorial / Outros", "Multicarteira outros"),
        16: ("Outros", "Recuperação", "Judicial/Precatórios/NPL", "Não padronizado/NPL"),
        17: ("Outros", "Recuperação", "Judicial/Precatórios/NPL", "Precatórios/direitos judiciais"),
        19: ("Outros", "Recuperação", "Judicial/Precatórios/NPL", "Não padronizado/NPL"),
        20: ("Outros", "Multicarteira Outros", "Multissetorial / Outros", "Multicarteira outros"),
    }
    all_pairs = {**proposed_pairs, **keep_focus}
    for index, row in frame.iterrows():
        pair = all_pairs.get(int(float(row.get("rank_outros") or 0)))
        if pair:
            frame.at[index, "tipo_anbima_sugerido"] = pair[0]
            frame.at[index, "foco_anbima_sugerido"] = pair[1]
            frame.at[index, "taxonomia_funcional_n1_sugerida"] = pair[2]
            frame.at[index, "taxonomia_funcional_n2_sugerida"] = pair[3]
    return frame


def _card_documentary(card_curation: pd.DataFrame | None) -> pd.DataFrame:
    if card_curation is None or card_curation.empty:
        return pd.DataFrame()
    frame = card_curation.copy()
    frame["cnpj_fundo"] = frame["cnpj14_digits"].map(normalize_cnpj)
    frame = frame[
        frame["status_curadoria"].astype(str).str.strip().eq("Incluído em Adquirência")
    ].copy()
    frame["tabela_ii_sugerida_cartao"] = "Adquirência"
    frame["tipo_anbima_sugerido_cartao"] = "Agro, Indústria e Comércio"
    frame["foco_anbima_sugerido_cartao"] = "Recebíveis Comerciais"
    return frame.drop_duplicates("cnpj_fundo", keep="last")


def _supplemental_documentary(
    document_review: pd.DataFrame | None,
) -> pd.DataFrame:
    if document_review is None or document_review.empty:
        return pd.DataFrame()
    frame = document_review.copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    status = frame.get(
        "reclassification_status", pd.Series("ambigua", index=frame.index)
    ).map(lambda value: re.sub(r"[^a-z0-9]+", " ", _fold_text(value)).strip())
    frame["status_revisao_documental"] = status.map(
        {
            "potencial reclassificacao": "validacao_manual",
            "manter outros": "manter_em_outros",
            "ambigua": "validacao_manual",
        }
    ).fillna("validacao_manual")
    frame["confianca_documental"] = frame.get(
        "confianca_documental", pd.Series("baixa", index=frame.index)
    ).map(_fold_text).replace("média", "media")
    frame["document_id"] = frame.get(
        "document_id", pd.Series("", index=frame.index)
    )
    frame["document_reference_date"] = frame.get(
        "document_reference_date", pd.Series("", index=frame.index)
    )
    frame["document_url"] = frame.get(
        "document_url", pd.Series("", index=frame.index)
    ).where(
        frame.get("document_url", pd.Series("", index=frame.index)).astype(str).ne(""),
        frame.get("local_path", pd.Series("", index=frame.index)),
    )
    frame["cedent_originator_explicit"] = frame.get(
        "cedent_originator_explicit", pd.Series("", index=frame.index)
    )
    frame["evidence_summary"] = frame.get(
        "evidence_summary", pd.Series("", index=frame.index)
    )
    frame["manual_validation_reason"] = frame.get(
        "manual_validation_reason", pd.Series("", index=frame.index)
    )
    frame["source_limitations"] = frame.get(
        "source_limitations", pd.Series("", index=frame.index)
    )
    return frame.drop_duplicates("cnpj_fundo", keep="last")


def build_taxonomy_review_queue(
    funds: pd.DataFrame,
    actions: pd.DataFrame | None,
    *,
    latest: str,
    table_ii: pd.DataFrame | None = None,
    regulation_review: pd.DataFrame | None = None,
    document_inventory: pd.DataFrame | None = None,
    card_curation: pd.DataFrame | None = None,
    document_review: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the exact 100-largest queue behind slide 8's expanded Outros."""

    current = funds[
        funds["competencia"].astype(str).eq(latest)
        & ~funds["is_fic_fidc"].map(_bool)
    ].copy()
    current["pl"] = pd.to_numeric(current["pl"], errors="coerce")
    current["cnpj_fundo"] = current["cnpj_fundo"].map(normalize_cnpj)
    current["bucket_slide_atual"] = current["anbima_tipo"].map(_display_type)
    current = current[current["bucket_slide_atual"].eq("Outros")].copy()
    current = current.sort_values(["pl", "cnpj_fundo"], ascending=[False, True])
    current["rank_outros_slide"] = range(1, len(current) + 1)
    current = current.head(100).copy()
    if len(current) != 100 or current["rank_outros_slide"].tolist() != list(range(1, 101)):
        raise ValueError("Fila de Outros deve conter os 100 maiores fundos em ranks sequenciais")

    table_profile = _table_ii_by_fund(table_ii, latest)
    current = current.merge(table_profile, on="cnpj_fundo", how="left", validate="one_to_one")
    current["tabela_ii_reportada"] = current["tabela_ii_reportada"].fillna("N/D — nenhuma categoria positiva observada")
    current["tabela_ii_dominante"] = current["tabela_ii_dominante"].fillna("N/D")
    current["tabela_ii_multisegmento"] = current["tabela_ii_multisegmento"].fillna(False).astype(bool)

    documentary = _documentary_top20(regulation_review)
    supplemental = _supplemental_documentary(document_review)
    if not supplemental.empty:
        documentary = pd.concat(
            [documentary, supplemental],
            ignore_index=True,
            sort=False,
        ).drop_duplicates("cnpj_fundo", keep="last")
    if not documentary.empty:
        wanted = [
            "cnpj_fundo",
            "reclassification_status",
            "document_id",
            "document_reference_date",
            "document_url",
            "cedent_originator_explicit",
            "evidence_summary",
            "proposed_category",
            "status_revisao_documental",
            "confianca_documental",
            "manual_validation_reason",
            "source_limitations",
            "tipo_anbima_sugerido",
            "foco_anbima_sugerido",
            "taxonomia_funcional_n1_sugerida",
            "taxonomia_funcional_n2_sugerida",
            "tabela_ii_sugerida_documental",
            "perimeter_proposal",
            "is_fic_fidc_suggested",
            "pagina_clausula",
        ]
        current = current.merge(
            documentary[[column for column in wanted if column in documentary]],
            on="cnpj_fundo",
            how="left",
            validate="one_to_one",
        )
    regulations = _latest_regulations(document_inventory)
    current = current.merge(regulations, on="cnpj_fundo", how="left", validate="one_to_one")
    card = _card_documentary(card_curation)
    if not card.empty:
        card_wanted = [
            "cnpj_fundo",
            "status_curadoria",
            "decisao_curadoria",
            "cedente_originador",
            "evidencia_curta",
            "fonte_documento",
            "fonte_data",
            "fonte_url",
            "confianca",
            "tabela_ii_sugerida_cartao",
            "tipo_anbima_sugerido_cartao",
            "foco_anbima_sugerido_cartao",
        ]
        current = current.merge(
            card[[column for column in card_wanted if column in card]],
            on="cnpj_fundo",
            how="left",
            validate="one_to_one",
            suffixes=("", "_cartao"),
        )

    for column in (
        "document_id",
        "document_reference_date",
        "document_url",
        "cedent_originator_explicit",
        "evidence_summary",
        "proposed_category",
        "status_revisao_documental",
        "confianca_documental",
        "manual_validation_reason",
        "source_limitations",
        "reclassification_status",
        "tipo_anbima_sugerido",
        "foco_anbima_sugerido",
        "taxonomia_funcional_n1_sugerida",
        "taxonomia_funcional_n2_sugerida",
        "tabela_ii_sugerida_documental",
        "perimeter_proposal",
        "is_fic_fidc_suggested",
        "pagina_clausula",
        "inventario_documento_id",
        "inventario_documento_data",
        "inventario_documento_origem",
        "status_curadoria",
        "decisao_curadoria",
        "cedente_originador",
        "evidencia_curta",
        "fonte_documento",
        "fonte_data",
        "fonte_url",
        "confianca",
        "tabela_ii_sugerida_cartao",
        "tipo_anbima_sugerido_cartao",
        "foco_anbima_sugerido_cartao",
    ):
        if column not in current:
            current[column] = ""
        current[column] = current[column].fillna("").map(_text)

    has_review = current["document_id"].ne("") | current["status_revisao_documental"].ne("")
    has_card = current["status_curadoria"].eq("Incluído em Adquirência")
    has_inventory = current["inventario_documento_id"].ne("")
    current["documento_id_base"] = current["document_id"].where(
        current["document_id"].ne(""), current["inventario_documento_id"]
    )
    current["documento_data_base"] = current["document_reference_date"].where(
        current["document_reference_date"].ne(""), current["inventario_documento_data"]
    )
    current["documento_url_base"] = current["document_url"].where(
        current["document_url"].ne(""),
        current["cnpj_fundo"].map(
            lambda cnpj: "https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM?cnpjFundo=" + cnpj
        ),
    )
    current["cedente_originador_expresso"] = current["cedent_originator_explicit"].where(
        current["cedent_originator_explicit"].ne(""), current["cedente_originador"]
    ).replace("", "N/D")
    current["evidencia_documental"] = current["evidence_summary"].where(
        current["evidence_summary"].ne(""), current["evidencia_curta"]
    )
    current["status_revisao_base"] = current["status_revisao_documental"].where(
        current["status_revisao_documental"].ne(""),
        pd.Series("pendente", index=current.index),
    )
    current.loc[~has_review & has_inventory, "status_revisao_base"] = "regulamento_local_sem_curadoria"
    current.loc[~has_review & ~has_inventory, "status_revisao_base"] = "sem_regulamento_versionado"
    current["confianca_base"] = current["confianca_documental"].where(
        current["confianca_documental"].ne(""), current["confianca"].str.casefold()
    ).replace("média", "media").replace("média-alta", "media")
    current.loc[current["confianca_base"].eq(""), "confianca_base"] = "baixa"
    current["motivo_validacao_manual_base"] = current["manual_validation_reason"].where(
        current["manual_validation_reason"].ne(""), current["source_limitations"]
    )
    current.loc[~has_review & has_inventory, "motivo_validacao_manual_base"] = (
        "Regulamento local inventariado; leitura curada ainda não concluída."
    )
    current.loc[~has_review & ~has_inventory, "motivo_validacao_manual_base"] = (
        "Regulamento oficial não localizado no corpus versionado; classificação mantida em Outros."
    )
    current["tipo_anbima_sugerido"] = current["tipo_anbima_sugerido"].where(
        current["tipo_anbima_sugerido"].ne(""), current["tipo_anbima_sugerido_cartao"]
    )
    current["foco_anbima_sugerido"] = current["foco_anbima_sugerido"].where(
        current["foco_anbima_sugerido"].ne(""), current["foco_anbima_sugerido_cartao"]
    )
    current["tabela_ii_sugerida"] = current["tabela_ii_dominante"]
    current.loc[current["tabela_ii_multisegmento"], "tabela_ii_sugerida"] = "N/D"
    has_documentary_table = current["tabela_ii_sugerida_documental"].ne("")
    current.loc[has_documentary_table, "tabela_ii_sugerida"] = current.loc[
        has_documentary_table, "tabela_ii_sugerida_documental"
    ]
    current.loc[has_card, "tabela_ii_sugerida"] = current.loc[has_card, "tabela_ii_sugerida_cartao"]
    current["pagina_clausula_base"] = current["pagina_clausula"].where(
        current["pagina_clausula"].ne(""),
        "N/D — não registrada na curadoria disponível",
    )
    current["is_fic_fidc_sugerido"] = current["is_fic_fidc_suggested"].map(
        _bool
    )
    current["pl_correcao_perimetro_candidata_brl"] = current["pl"].where(
        current["is_fic_fidc_sugerido"] & ~current["is_fic_fidc"].map(_bool),
        0.0,
    )

    current = apply_taxonomy_review_overlay(current, actions)
    current["competencia_referencia"] = latest
    current["review_id"] = current["cnpj_fundo"].map(taxonomy_review_id)
    action_frame = _blank_actions() if actions is None else actions.copy()
    if not action_frame.empty:
        for column in TAXONOMY_REVIEW_COLUMNS:
            if column not in action_frame:
                action_frame[column] = ""
        action_frame = _prepare_taxonomy_review_actions(action_frame)
        current = current.merge(
            action_frame.add_prefix("acao_").rename(
                columns={"acao_review_id": "review_id"}
            ),
            on="review_id",
            how="left",
            validate="one_to_one",
        )
    if "acao_status" not in current:
        current["acao_status"] = "pendente"
    current["acao_status"] = current["acao_status"].fillna("").replace("", "pendente")
    current["tipo_slide_oficial"] = current["anbima_tipo_oficial"].map(_display_type)
    current["tipo_slide_curado"] = current["anbima_tipo_curado"].map(_display_type)
    current["pl_reclassificado_aprovado_brl"] = current["pl"].where(
        current["taxonomy_review_applied"] & current["tipo_slide_curado"].ne("Outros"),
        0.0,
    )
    current["pl_candidato_documental_brl"] = current["pl"].where(
        current["status_revisao_documental"].eq("validacao_manual")
        & current["tipo_anbima_sugerido"].ne("")
        & current["tipo_anbima_sugerido"].ne("Outros"),
        0.0,
    )
    current["cnpj_fundo_formatado"] = current["cnpj_fundo"].map(format_cnpj)
    current["competencia_pl"] = latest
    current["anbima_referencia"] = current["classification_tier"].map(
        lambda value: ANBIMA_REFERENCE_DATE if _text(value) == "oficial_anbima" else latest
    )
    return current.sort_values("rank_outros_slide").reset_index(drop=True)


def build_historical_top20_taxonomy_review(
    funds: pd.DataFrame,
    actions: pd.DataFrame | None,
    *,
    periods: tuple[str, ...],
    table_ii: pd.DataFrame | None = None,
    curated_top20: pd.DataFrame | None = None,
    regulation_review: pd.DataFrame | None = None,
    document_inventory: pd.DataFrame | None = None,
    card_curation: pd.DataFrame | None = None,
    document_review: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the auditable Top 20 by displayed ANBIMA Type for each period."""

    if not periods or any(not _valid_month_competence(period) for period in periods):
        raise ValueError("competências do Top 20 histórico devem seguir AAAA-MM")
    scoped = funds[
        funds["competencia"].astype(str).isin(periods)
        & ~funds["is_fic_fidc"].map(_bool)
    ].copy()
    scoped["pl"] = pd.to_numeric(scoped["pl"], errors="coerce")
    scoped["cnpj_fundo"] = scoped["cnpj_fundo"].map(normalize_cnpj)

    table_profiles: list[pd.DataFrame] = []
    for period in periods:
        profile = _table_ii_by_fund(table_ii, period)
        profile["competencia"] = period
        table_profiles.append(profile)
    if table_profiles:
        scoped = scoped.merge(
            pd.concat(table_profiles, ignore_index=True),
            on=["competencia", "cnpj_fundo"],
            how="left",
            validate="one_to_one",
        )
    scoped = apply_taxonomy_review_overlay(scoped, actions)
    scoped["tipo_exibicao"] = scoped["anbima_tipo_curado"].map(_display_type)
    scoped = scoped[scoped["pl"].gt(0)].sort_values(
        ["competencia", "tipo_exibicao", "pl", "cnpj_fundo"],
        ascending=[True, True, False, True],
    )
    scoped["rank_tipo"] = scoped.groupby(
        ["competencia", "tipo_exibicao"]
    ).cumcount() + 1
    top = scoped[scoped["rank_tipo"].le(20)].copy()
    counts = top.groupby(["competencia", "tipo_exibicao"]).size()
    expected = pd.MultiIndex.from_product(
        [periods, DISPLAY_TYPES], names=["competencia", "tipo_exibicao"]
    )
    if not counts.reindex(expected, fill_value=0).eq(20).all() or len(top) != 80 * len(periods):
        raise ValueError("Top 20 histórico deve conter 20 fundos em cada Tipo e competência")

    evidence = _originator_evidence(
        curated_top20,
        regulation_review,
        card_curation,
        document_review,
    )
    if not evidence.empty:
        top = top.merge(evidence, on="cnpj_fundo", how="left", validate="many_to_one")
    regulations = _latest_regulations(document_inventory)
    top = top.merge(regulations, on="cnpj_fundo", how="left", validate="many_to_one")

    documentary = _documentary_top20(regulation_review)
    supplemental = _supplemental_documentary(document_review)
    if not supplemental.empty:
        documentary = pd.concat(
            [documentary, supplemental], ignore_index=True, sort=False
        ).drop_duplicates("cnpj_fundo", keep="last")
    if not documentary.empty:
        wanted = [
            "cnpj_fundo",
            "reclassification_status",
            "tipo_anbima_sugerido",
            "foco_anbima_sugerido",
            "tabela_ii_sugerida_documental",
            "taxonomia_funcional_n1_sugerida",
            "taxonomia_funcional_n2_sugerida",
            "status_revisao_documental",
            "confianca_documental",
            "pagina_clausula",
            "manual_validation_reason",
            "source_limitations",
        ]
        top = top.merge(
            documentary[[column for column in wanted if column in documentary]],
            on="cnpj_fundo",
            how="left",
            validate="many_to_one",
        )

    text_columns = (
        "tabela_ii_reportada",
        "tabela_ii_dominante",
        "cedente_originador",
        "cedente_status",
        "regulamento_id",
        "regulamento_data",
        "regulamento_url",
        "pagina_clausula",
        "evidencia_cedente",
        "confianca_cedente",
        "limitacao_cedente",
        "inventario_documento_id",
        "inventario_documento_data",
        "inventario_documento_origem",
        "tipo_anbima_sugerido",
        "foco_anbima_sugerido",
        "tabela_ii_sugerida_documental",
        "taxonomia_funcional_n1_sugerida",
        "taxonomia_funcional_n2_sugerida",
        "status_revisao_documental",
        "confianca_documental",
        "manual_validation_reason",
        "source_limitations",
        "reclassification_status",
    )
    for column in text_columns:
        if column not in top:
            top[column] = ""
        top[column] = top[column].fillna("").map(_text)

    has_curated = top["cedente_status"].eq("curadoria_documental_concluida")
    has_automated = top["cedente_status"].eq(
        "leitura_automatizada_pendente_validacao"
    )
    has_local = top["inventario_documento_id"].ne("")
    top.loc[~has_curated & ~has_automated & has_local, "cedente_status"] = (
        "regulamento_local_sem_curadoria_concluida"
    )
    top.loc[~has_curated & ~has_automated & ~has_local, "cedente_status"] = (
        "regulamento_nao_localizado_no_corpus_versionado"
    )
    top.loc[~has_curated & ~has_automated, "cedente_originador"] = "N/D"
    top["regulamento_id"] = top["regulamento_id"].where(
        top["regulamento_id"].ne(""), top["inventario_documento_id"]
    )
    top["regulamento_data"] = top["regulamento_data"].where(
        top["regulamento_data"].ne(""), top["inventario_documento_data"]
    )
    top["regulamento_url"] = top["regulamento_url"].where(
        top["regulamento_url"].ne(""),
        top["cnpj_fundo"].map(
            lambda cnpj: "https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM?cnpjFundo="
            + cnpj
        ),
    )
    top["pagina_clausula"] = top["pagina_clausula"].replace(
        "", "N/D — página não registrada"
    )
    top["tabela_ii_dominante"] = top["tabela_ii_dominante"].replace("", "N/D")
    top["tabela_ii_reportada"] = top["tabela_ii_reportada"].replace(
        "", "N/D — nenhuma categoria positiva observada"
    )
    top["sugestao_documental_disponivel"] = top[
        "tipo_anbima_sugerido"
    ].ne("")
    top["tipo_anbima_sugerido"] = top["tipo_anbima_sugerido"].where(
        top["tipo_anbima_sugerido"].ne(""), top["anbima_tipo"]
    )
    top["foco_anbima_sugerido"] = top["foco_anbima_sugerido"].where(
        top["foco_anbima_sugerido"].ne(""), top["anbima_foco"]
    )
    top["tabela_ii_sugerida"] = top["tabela_ii_sugerida_documental"].where(
        top["tabela_ii_sugerida_documental"].ne(""), top["tabela_ii_dominante"]
    )
    top["competencia_referencia"] = top["competencia"].astype(str)
    top["review_id"] = top["cnpj_fundo"].map(taxonomy_review_id)
    top["anbima_tipo_oficial"] = top["anbima_tipo"].map(_text)
    top["anbima_foco_oficial"] = top["anbima_foco"].map(_text)
    top["classification_reference_date"] = top["classification_tier"].map(
        lambda value: ANBIMA_REFERENCE_DATE
        if _text(value) == "oficial_anbima"
        else ""
    )
    top["classification_limitation"] = top.get(
        "classification_warning", pd.Series("", index=top.index)
    ).fillna("").map(_text)
    top["classification_period_status"] = (
        "fotografia_cadastral_2025-12-29_aplicada_ao_periodo"
    )
    top.loc[
        top["classification_tier"].ne("oficial_anbima"),
        "classification_period_status",
    ] = "classificacao_nao_oficial_ou_indisponivel"
    top["cnpj_fundo_formatado"] = top["cnpj_fundo"].map(format_cnpj)

    exact_actions = _blank_actions() if actions is None else _prepare_taxonomy_review_actions(actions)
    if not exact_actions.empty:
        top = top.merge(
            exact_actions.add_prefix("acao_").rename(
                columns={"acao_review_id": "review_id"}
            ),
            on="review_id",
            how="left",
            validate="many_to_one",
        )
    if "acao_status" not in top:
        top["acao_status"] = "pendente"
    top["acao_status"] = top["acao_status"].fillna("").replace("", "pendente")
    top["manual_override_applied"] = top["taxonomy_review_applied"].astype(bool)
    return top.sort_values(
        ["competencia", "tipo_exibicao", "rank_tipo"],
        key=lambda series: series.map(
            {name: index for index, name in enumerate(DISPLAY_TYPES)}
        )
        if series.name == "tipo_exibicao"
        else series,
    ).reset_index(drop=True)


def build_unique_taxonomy_operational_queue(
    review_rows: pd.DataFrame,
    actions: pd.DataFrame | None,
) -> pd.DataFrame:
    """Return one unresolved operational item per CNPJ, ordered by maximum PL."""

    if review_rows is None or review_rows.empty:
        return pd.DataFrame()
    frame = review_rows.copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame["pl"] = pd.to_numeric(frame.get("pl"), errors="coerce").fillna(0.0)
    frame["competencia"] = frame.get(
        "competencia", pd.Series("", index=frame.index)
    ).fillna("").astype(str)
    status = frame.get(
        "reclassification_status", pd.Series("", index=frame.index)
    ).fillna("").astype(str)
    candidates = frame[
        status.isin(
            {
                "propor_reclassificacao_documental",
                "requer_validacao_manual",
                "manter_provisoriamente_por_limitacao_documental",
            }
        )
    ].copy()
    if candidates.empty:
        return candidates

    periods = (
        candidates.groupby("cnpj_fundo")["competencia"]
        .agg(lambda values: ", ".join(sorted(set(values), reverse=True)))
        .rename("competencias_observadas")
    )
    occurrences = candidates.groupby("cnpj_fundo").size().rename("ocorrencias")
    representatives = (
        candidates.sort_values(
            ["pl", "competencia", "cnpj_fundo"],
            ascending=[False, False, True],
        )
        .drop_duplicates("cnpj_fundo", keep="first")
        .copy()
    )
    representatives = representatives.rename(
        columns={"pl": "pl_max", "competencia": "competencia_pl_max"}
    )
    representatives["pl"] = representatives["pl_max"]
    representatives["competencia"] = representatives["competencia_pl_max"]
    representatives = representatives.merge(
        periods,
        on="cnpj_fundo",
        how="left",
        validate="one_to_one",
    ).merge(
        occurrences,
        on="cnpj_fundo",
        how="left",
        validate="one_to_one",
    )
    representatives = apply_taxonomy_review_overlay(representatives, actions)
    representatives = representatives[
        ~representatives["taxonomy_review_applied"].astype(bool)
    ].copy()
    representatives["review_id"] = representatives["cnpj_fundo"].map(
        taxonomy_review_id
    )
    return representatives.sort_values(
        ["pl_max", "cnpj_fundo"], ascending=[False, True]
    ).reset_index(drop=True)


def taxonomy_review_summary(
    funds: pd.DataFrame,
    actions: pd.DataFrame | None,
    *,
    latest: str,
    queue: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Reconcile official slide 8, approved changes and documentary scenarios."""

    current = funds[
        funds["competencia"].astype(str).eq(latest)
        & ~funds["is_fic_fidc"].map(_bool)
    ].copy()
    current["pl"] = pd.to_numeric(current["pl"], errors="coerce")
    current["cnpj_fundo"] = current["cnpj_fundo"].map(normalize_cnpj)
    current = apply_taxonomy_review_overlay(current, actions)
    official = current["anbima_tipo_oficial"].map(_display_type)
    curated = current["anbima_tipo_curado"].map(_display_type)
    official_outros = float(current.loc[official.eq("Outros"), "pl"].sum())
    curated_outros = float(current.loc[curated.eq("Outros"), "pl"].sum())
    removed = official.eq("Outros") & curated.ne("Outros") & current["taxonomy_review_applied"]
    destinations = (
        current[removed]
        .groupby(["anbima_tipo_curado", "anbima_foco_curado"], as_index=False)
        .agg(pl_brl=("pl", "sum"), fundos=("cnpj_fundo", "nunique"))
        .sort_values("pl_brl", ascending=False)
    )
    top100_pl = float(queue["pl"].sum()) if queue is not None and not queue.empty else 0.0
    if queue is not None and not queue.empty:
        type_candidate = pd.to_numeric(
            queue["pl_candidato_documental_brl"], errors="coerce"
        ).fillna(0.0)
        perimeter_candidate = pd.to_numeric(
            queue.get(
                "pl_correcao_perimetro_candidata_brl",
                pd.Series(0.0, index=queue.index),
            ),
            errors="coerce",
        ).fillna(0.0)
        candidate_mask = type_candidate.gt(0) | perimeter_candidate.gt(0)
        candidate_pl = float(
            pd.to_numeric(queue["pl"], errors="coerce")
            .fillna(0.0)
            .where(candidate_mask, 0.0)
            .sum()
        )
        candidate_type_pl = float(type_candidate.sum())
        candidate_perimeter_pl = float(perimeter_candidate.sum())
        candidate_funds = int(candidate_mask.sum())
    else:
        candidate_pl = 0.0
        candidate_type_pl = 0.0
        candidate_perimeter_pl = 0.0
        candidate_funds = 0
    target = 150_000_000_000.0
    minimum_residual_top100 = official_outros - top100_pl
    candidate_residual = official_outros - candidate_pl
    return {
        "competencia": latest,
        "pl_ex_fic_brl": float(current["pl"].sum()),
        "outros_oficial_brl": official_outros,
        "outros_curado_brl": curated_outros,
        "reducao_aprovada_brl": official_outros - curated_outros,
        "decisoes_aprovadas": int(current["taxonomy_review_applied"].sum()),
        "decisoes_aprovadas_com_saida": int(removed.sum()),
        "fundos_outros_oficial": int(current.loc[official.eq("Outros"), "cnpj_fundo"].nunique()),
        "fundos_outros_curado": int(current.loc[curated.eq("Outros"), "cnpj_fundo"].nunique()),
        "top100_outros_brl": top100_pl,
        "candidatos_documentais": candidate_funds,
        "candidatos_documentais_brl": candidate_pl,
        "candidatos_reclassificacao_tipo_brl": candidate_type_pl,
        "candidatos_correcao_perimetro_brl": candidate_perimeter_pl,
        "outros_pos_candidatos_brl": candidate_residual,
        "residual_minimo_top100_brl": minimum_residual_top100,
        "meta_brl": target,
        "gap_meta_candidatos_brl": max(0.0, candidate_residual - target),
        "gap_meta_minimo_top100_brl": max(0.0, minimum_residual_top100 - target),
        "meta_atingivel_top100": minimum_residual_top100 <= target,
        "casos_validacao_manual": int(
            queue["status_revisao_base"].ne("manter_em_outros").sum()
        ) if queue is not None and not queue.empty else 0,
        "destinos": destinations,
        "metodologia": (
            "Bucket do slide 8 = Outros literal + N/D incorporado; Top 100 ordenado por PL descrescente e CNPJ crescente. "
            "Somente ações aprovadas com documento, página/cláusula, evidência e par Tipo/Foco válido alteram o mix analítico."
        ),
    }


def build_curated_type_mix(
    funds: pd.DataFrame,
    actions: pd.DataFrame | None,
    *,
    latest: str,
) -> pd.DataFrame:
    """Return the four-category current mix after effective approved actions."""

    current = funds[
        funds["competencia"].astype(str).eq(latest)
        & ~funds["is_fic_fidc"].map(_bool)
    ].copy()
    current["pl"] = pd.to_numeric(current["pl"], errors="coerce")
    current = apply_taxonomy_review_overlay(current, actions)
    current["anbima_tipo"] = current["anbima_tipo_curado"].map(_display_type)
    mix = current.groupby("anbima_tipo", as_index=False).agg(
        pl=("pl", "sum"),
        fundos=("cnpj_fundo", "nunique"),
    )
    mix = mix.set_index("anbima_tipo").reindex(DISPLAY_TYPES, fill_value=0).reset_index()
    total = float(mix["pl"].sum())
    mix["share"] = mix["pl"] / total if total else 0.0
    mix["competencia"] = latest
    return mix


def build_curated_taxonomy_level_history(
    funds: pd.DataFrame,
    actions: pd.DataFrame | None,
    *,
    periods: tuple[str, ...],
    table_ii: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Materialize reconciled analytical drill-downs below displayed Type."""

    if not periods or any(not _valid_month_competence(period) for period in periods):
        raise ValueError("competências da taxonomia analítica devem seguir AAAA-MM")
    scoped = funds[
        funds["competencia"].astype(str).isin(periods)
        & ~funds["is_fic_fidc"].map(_bool)
    ].copy()
    scoped["pl"] = pd.to_numeric(scoped["pl"], errors="coerce").fillna(0.0)
    scoped["cnpj_fundo"] = scoped["cnpj_fundo"].map(normalize_cnpj)

    table_profiles: list[pd.DataFrame] = []
    for period in periods:
        profile = _table_ii_by_fund(table_ii, period)
        profile["competencia"] = period
        table_profiles.append(profile)
    if table_profiles:
        scoped = scoped.merge(
            pd.concat(table_profiles, ignore_index=True),
            on=["competencia", "cnpj_fundo"],
            how="left",
            validate="one_to_one",
        )

    scoped = apply_taxonomy_review_overlay(scoped, actions)
    scoped["tipo_exibicao"] = scoped["anbima_tipo_curado"].map(_display_type)
    level_fields = {
        "foco_analitico": "anbima_foco_curado",
        "tabela_ii_analitica": "tabela_ii_curada",
        "taxonomia_funcional_n1": "taxonomia_funcional_n1_curada",
        "taxonomia_funcional_n2": "taxonomia_funcional_n2_curada",
    }
    total_by_period = scoped.groupby("competencia")["pl"].sum(min_count=1)
    parent_totals = scoped.groupby(["competencia", "tipo_exibicao"])["pl"].sum(
        min_count=1
    )
    outputs: list[pd.DataFrame] = []
    for level_name, source_column in level_fields.items():
        level = scoped[
            ["competencia", "tipo_exibicao", "cnpj_fundo", "pl", source_column]
        ].copy()
        level["categoria"] = (
            level[source_column].fillna("").map(_text).replace("", "N/D")
        )
        grouped = level.groupby(
            ["competencia", "tipo_exibicao", "categoria"],
            as_index=False,
        ).agg(
            pl_brl=("pl", "sum"),
            fundos=("cnpj_fundo", "nunique"),
        )
        grouped["nivel"] = level_name
        grouped["pl_tipo_brl"] = grouped.set_index(
            ["competencia", "tipo_exibicao"]
        ).index.map(parent_totals)
        grouped["pl_total_brl"] = grouped["competencia"].map(total_by_period)
        grouped["share_tipo"] = (
            grouped["pl_brl"] / grouped["pl_tipo_brl"].replace(0.0, pd.NA)
        ).fillna(0.0)
        grouped["share_total"] = (
            grouped["pl_brl"] / grouped["pl_total_brl"].replace(0.0, pd.NA)
        ).fillna(0.0)
        outputs.append(grouped)
    output = pd.concat(outputs, ignore_index=True)
    level_order = {name: index for index, name in enumerate(level_fields)}
    type_order = {name: index for index, name in enumerate(DISPLAY_TYPES)}
    output["_nivel_ordem"] = output["nivel"].map(level_order)
    output["_tipo_ordem"] = output["tipo_exibicao"].map(type_order)
    return output.sort_values(
        [
            "_nivel_ordem",
            "competencia",
            "_tipo_ordem",
            "pl_brl",
            "categoria",
        ],
        ascending=[True, True, True, False, True],
    ).drop(columns=["_nivel_ordem", "_tipo_ordem"]).reset_index(drop=True)


__all__ = [
    "ANALYTICAL_ANBIMA_FOCUS_BY_TYPE",
    "ANBIMA_TYPES",
    "CVM_TABLE_II_CATEGORIES",
    "FUNCTIONAL_TAXONOMY",
    "TAXONOMY_CONFIDENCE_LEVELS",
    "TAXONOMY_REVIEW_AUDIT_COLUMNS",
    "TAXONOMY_REVIEW_COLUMNS",
    "TAXONOMY_REVIEW_KEY_COLUMN",
    "TAXONOMY_REVIEW_STATUSES",
    "apply_taxonomy_review_overlay",
    "assert_taxonomy_review_ledger_matches_audit",
    "build_curated_taxonomy_level_history",
    "build_curated_type_mix",
    "build_historical_top20_taxonomy_review",
    "build_unique_taxonomy_operational_queue",
    "build_taxonomy_review_queue",
    "build_top20_by_anbima_type",
    "commit_taxonomy_review_action",
    "format_cnpj",
    "load_taxonomy_review_actions",
    "load_taxonomy_review_audit",
    "normalize_analytical_anbima_focus",
    "normalize_cnpj",
    "taxonomy_review_ledger_digest",
    "taxonomy_review_audit_digest",
    "taxonomy_review_audit_has_pending",
    "taxonomy_review_summary",
    "taxonomy_review_id",
    "validate_taxonomy_review_action",
    "valid_analytical_type_focus_pair",
]
