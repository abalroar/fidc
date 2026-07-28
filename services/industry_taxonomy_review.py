"""Manual analytical taxonomy overlay for the FIDC industry study.

The official ANBIMA fields remain immutable.  Approved decisions are stored in
their own ledger and materialized as ``*_curado`` columns for the Streamlit
queue and the executive bundle.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
from typing import Mapping

import pandas as pd

from services.industry_anbima import ANBIMA_FOCUS_BY_TYPE, ANBIMA_TYPES, valid_type_focus_pair


TAXONOMY_REVIEW_COLUMNS: tuple[str, ...] = (
    "cnpj_fundo",
    "denominacao_referencia",
    "status",
    "tipo_analitico",
    "foco_analitico",
    "taxonomia_funcional_n1",
    "taxonomia_funcional_n2",
    "confianca",
    "fonte_documental",
    "pagina_clausula",
    "evidencia",
    "notas",
    "responsavel",
    "competencia_inicio",
    "updated_at_utc",
)

TAXONOMY_REVIEW_STATUSES: tuple[str, ...] = (
    "pendente",
    "em_revisao",
    "aprovado",
    "rejeitado",
)

TAXONOMY_CONFIDENCE_LEVELS: tuple[str, ...] = ("", "baixa", "media", "alta")

# Taxonomia funcional já observada nas bases documentais e regulatórias do
# projeto.  Ela permanece separada de Tipo/Foco ANBIMA.
FUNCTIONAL_TAXONOMY: Mapping[str, tuple[str, ...]] = {
    "": ("",),
    "Agro": ("Agro",),
    "Crédito PF": (
        "Auto/Veículos",
        "Consignado/INSS",
        "Crédito estudantil",
        "Crédito pessoal/consumo",
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
    ),
    "Multissetorial / Outros": ("Multicarteira outros",),
}


def normalize_cnpj(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    raw = str(value).strip()
    if re.fullmatch(r"\d{1,14}(?:\.0+)?", raw):
        raw = raw.split(".", 1)[0]
    digits = re.sub(r"\D", "", raw)
    return digits.zfill(14)[-14:] if digits else ""


def _text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return re.sub(r"\s+", " ", str(value).strip())


def _blank_actions() -> pd.DataFrame:
    return pd.DataFrame(columns=list(TAXONOMY_REVIEW_COLUMNS))


def load_taxonomy_review_actions(path: Path) -> pd.DataFrame:
    """Load one current action row per legal fund without inventing decisions."""

    path = Path(path)
    if not path.exists():
        return _blank_actions()
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    for column in TAXONOMY_REVIEW_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[list(TAXONOMY_REVIEW_COLUMNS)].copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame = frame[frame["cnpj_fundo"].ne("")]
    return frame.drop_duplicates("cnpj_fundo", keep="last").reset_index(drop=True)


def validate_taxonomy_review_action(action: Mapping[str, object]) -> None:
    """Validate controlled fields and the stricter approval contract."""

    cnpj = normalize_cnpj(action.get("cnpj_fundo"))
    if len(cnpj) != 14:
        raise ValueError("CNPJ do fundo deve conter 14 dígitos")
    status = _text(action.get("status")) or "pendente"
    if status not in TAXONOMY_REVIEW_STATUSES:
        raise ValueError(f"status de revisão inválido: {status}")
    confidence = _text(action.get("confianca"))
    if confidence not in TAXONOMY_CONFIDENCE_LEVELS:
        raise ValueError(f"confiança inválida: {confidence}")

    functional_n1 = _text(action.get("taxonomia_funcional_n1"))
    functional_n2 = _text(action.get("taxonomia_funcional_n2"))
    if functional_n1 not in FUNCTIONAL_TAXONOMY:
        raise ValueError(f"taxonomia funcional N1 inválida: {functional_n1}")
    if functional_n2 not in FUNCTIONAL_TAXONOMY[functional_n1]:
        raise ValueError("taxonomia funcional N2 incompatível com N1")

    if status != "aprovado":
        return
    anbima_type = _text(action.get("tipo_analitico"))
    anbima_focus = _text(action.get("foco_analitico"))
    if anbima_type not in ANBIMA_TYPES or not valid_type_focus_pair(anbima_type, anbima_focus):
        raise ValueError("Tipo e Foco analíticos formam uma combinação inválida")
    competence = _text(action.get("competencia_inicio"))
    if not re.fullmatch(r"\d{4}-\d{2}", competence):
        raise ValueError("competência inicial deve seguir AAAA-MM")
    required = {
        "fonte_documental": "fonte documental",
        "evidencia": "evidência",
        "responsavel": "responsável",
    }
    missing = [label for field, label in required.items() if not _text(action.get(field))]
    if missing:
        raise ValueError("aprovação requer " + ", ".join(missing))


def save_taxonomy_review_actions(actions: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Atomically persist the current ledger without touching source datasets."""

    path = Path(path)
    out = _blank_actions() if actions is None else actions.copy()
    for column in TAXONOMY_REVIEW_COLUMNS:
        if column not in out.columns:
            out[column] = ""
    out = out[list(TAXONOMY_REVIEW_COLUMNS)].fillna("").astype(str)
    out["cnpj_fundo"] = out["cnpj_fundo"].map(normalize_cnpj)
    out["status"] = out["status"].replace("", "pendente")
    out = out[out["cnpj_fundo"].ne("")].drop_duplicates("cnpj_fundo", keep="last")
    for action in out.to_dict(orient="records"):
        validate_taxonomy_review_action(action)
    out = out.sort_values(["status", "cnpj_fundo"]).reset_index(drop=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        out.to_csv(temporary, index=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return out


def taxonomy_review_ledger_digest(path: Path) -> str:
    """Return a stable digest; an absent ledger is equivalent to an empty one."""

    frame = load_taxonomy_review_actions(path)
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _effective_actions(actions: pd.DataFrame, competence: object) -> pd.DataFrame:
    frame = _blank_actions() if actions is None else actions.copy()
    if frame.empty:
        return frame
    for column in TAXONOMY_REVIEW_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame = frame[
        frame["status"].astype(str).str.strip().eq("aprovado")
        & frame["competencia_inicio"].astype(str).str.match(r"^\d{4}-\d{2}$")
        & frame["competencia_inicio"].astype(str).le(str(competence))
    ].copy()
    valid = frame.apply(
        lambda row: valid_type_focus_pair(row.get("tipo_analitico"), row.get("foco_analitico")),
        axis=1,
    )
    return frame[valid].drop_duplicates("cnpj_fundo", keep="last")


def apply_taxonomy_review_overlay(
    funds: pd.DataFrame,
    actions: pd.DataFrame | None,
) -> pd.DataFrame:
    """Add analytical columns while preserving the official ANBIMA values."""

    if funds is None or funds.empty:
        return pd.DataFrame() if funds is None else funds.copy()
    frame = funds.copy()
    if "cnpj_fundo" not in frame.columns:
        frame["cnpj_fundo"] = [str(index) for index in frame.index]
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    official_type = frame["anbima_tipo"] if "anbima_tipo" in frame else pd.Series("", index=frame.index)
    official_focus = frame["anbima_foco"] if "anbima_foco" in frame else pd.Series("", index=frame.index)
    frame["anbima_tipo_oficial"] = official_type.map(_text)
    frame["anbima_foco_oficial"] = official_focus.map(_text)
    frame["anbima_tipo_curado"] = frame["anbima_tipo_oficial"]
    frame["anbima_foco_curado"] = frame["anbima_foco_oficial"]
    frame["taxonomia_funcional_n1_curada"] = ""
    frame["taxonomia_funcional_n2_curada"] = ""
    frame["taxonomy_review_status"] = "pendente"
    frame["taxonomy_review_applied"] = False

    action_frame = _blank_actions() if actions is None else actions.copy()
    if action_frame.empty:
        return frame
    action_frame["cnpj_fundo"] = action_frame["cnpj_fundo"].map(normalize_cnpj)
    action_frame = action_frame.drop_duplicates("cnpj_fundo", keep="last").set_index("cnpj_fundo")
    for index, row in frame.iterrows():
        cnpj = row["cnpj_fundo"]
        if cnpj not in action_frame.index:
            continue
        action = action_frame.loc[cnpj]
        frame.at[index, "taxonomy_review_status"] = _text(action.get("status")) or "pendente"
        competence = _text(row.get("competencia"))
        approved = _text(action.get("status")) == "aprovado"
        starts_at = _text(action.get("competencia_inicio"))
        pair_is_valid = valid_type_focus_pair(
            action.get("tipo_analitico"), action.get("foco_analitico")
        )
        if not approved or not pair_is_valid:
            continue
        if competence and (not re.fullmatch(r"\d{4}-\d{2}", starts_at) or starts_at > competence):
            continue
        frame.at[index, "anbima_tipo_curado"] = _text(action.get("tipo_analitico"))
        frame.at[index, "anbima_foco_curado"] = _text(action.get("foco_analitico"))
        frame.at[index, "taxonomia_funcional_n1_curada"] = _text(
            action.get("taxonomia_funcional_n1")
        )
        frame.at[index, "taxonomia_funcional_n2_curada"] = _text(
            action.get("taxonomia_funcional_n2")
        )
        frame.at[index, "taxonomy_review_applied"] = True
    return frame


def _display_type(value: object) -> str:
    text = _text(value)
    return text if text in set(ANBIMA_TYPES).difference({"Outros"}) else "Outros"


def _documentary_by_fund(
    documentary: pd.DataFrame | None,
    reconciliation: pd.DataFrame | None,
) -> pd.DataFrame:
    if documentary is None or documentary.empty:
        return pd.DataFrame()
    class_to_fund: dict[str, str] = {}
    if reconciliation is not None and not reconciliation.empty:
        for row in reconciliation.to_dict(orient="records"):
            fund = normalize_cnpj(row.get("cnpj_fundo_14") or row.get("cnpj_fundo"))
            if not fund:
                continue
            class_to_fund[fund] = fund
            for token in str(row.get("cnpjs_reportantes") or "").split("|"):
                reported = normalize_cnpj(token)
                if reported:
                    class_to_fund[reported] = fund
    doc = documentary.copy()
    documentary_cnpj = doc["cnpj"] if "cnpj" in doc else pd.Series("", index=doc.index)
    doc["cnpj_documental"] = documentary_cnpj.map(normalize_cnpj)
    doc["cnpj_fundo"] = doc["cnpj_documental"].map(
        lambda value: class_to_fund.get(value, value)
    )
    confidence = (
        doc["classification_confidence"]
        if "classification_confidence" in doc.columns
        else pd.Series("", index=doc.index)
    )
    doc["_confidence_order"] = confidence.map(
        {"alta": 3, "media": 2, "média": 2, "baixa": 1}
    ).fillna(0)
    if "pl_brl" not in doc.columns:
        doc["pl_brl"] = 0.0
    return (
        doc.sort_values(["_confidence_order", "pl_brl"], ascending=[False, False])
        .drop_duplicates("cnpj_fundo", keep="first")
        .drop(columns=["_confidence_order"])
    )


def suggested_anbima_pair(functional_n1: object, functional_n2: object) -> tuple[str, str]:
    """Map a documentary functional class to a controlled analytical suggestion."""

    n1, n2 = _text(functional_n1), _text(functional_n2)
    if n1 == "Crédito PF":
        if "Consignado" in n2 or n2 == "FGTS":
            return "Financeiro", "Crédito Consignado"
        if "Auto" in n2 or "Veículo" in n2:
            return "Financeiro", "Financiamento de Veículos"
        return "Financeiro", "Crédito Pessoal"
    if n1 == "Imobiliário":
        return "Financeiro", "Crédito Imobiliário"
    if n1 == "Infra/Energia":
        return "Agro, Indústria e Comércio", "Infraestrutura"
    if n1 == "Agro":
        return "Agro, Indústria e Comércio", "Agronegócio"
    if n1 == "Meios de Pagamento e Cartões":
        return "Agro, Indústria e Comércio", "Recebíveis Comerciais"
    if n1 == "Crédito PJ":
        if "Capital de giro" in n2 or "Crédito privado" in n2:
            return "Agro, Indústria e Comércio", "Crédito Corporativo"
        return "Agro, Indústria e Comércio", "Recebíveis Comerciais"
    if n1 == "Judicial/Precatórios/NPL":
        return "Outros", "Poder Público" if "Precatório" in n2 else "Recuperação"
    if n1 == "Multissetorial / Outros":
        return "Outros", "Multicarteira Outros"
    return "", ""


def build_taxonomy_review_queue(
    funds: pd.DataFrame,
    actions: pd.DataFrame | None,
    *,
    latest: str,
    documentary: pd.DataFrame | None = None,
    reconciliation: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the PL-ranked queue behind the current ``Outros`` slide bucket."""

    latest_funds = funds[
        funds["competencia"].astype(str).eq(latest)
        & ~funds["is_fic_fidc"].fillna(False).astype(bool)
    ].copy()
    latest_funds["pl"] = pd.to_numeric(latest_funds["pl"], errors="coerce").fillna(0.0)
    latest_funds = latest_funds.sort_values(["pl", "cnpj_fundo"], ascending=[False, True])
    latest_funds["rank_mercado"] = range(1, len(latest_funds) + 1)
    latest_funds = apply_taxonomy_review_overlay(latest_funds, actions)
    latest_funds["tipo_slide_oficial"] = latest_funds["anbima_tipo_oficial"].map(_display_type)
    latest_funds["tipo_slide_curado"] = latest_funds["anbima_tipo_curado"].map(_display_type)
    queue = latest_funds[latest_funds["tipo_slide_oficial"].eq("Outros")].copy()
    queue["top100"] = queue["rank_mercado"].le(100)

    action_frame = _blank_actions() if actions is None else actions.copy()
    if not action_frame.empty:
        action_frame["cnpj_fundo"] = action_frame["cnpj_fundo"].map(normalize_cnpj)
        action_frame = action_frame.drop_duplicates("cnpj_fundo", keep="last")
        queue = queue.merge(
            action_frame.add_prefix("acao_").rename(columns={"acao_cnpj_fundo": "cnpj_fundo"}),
            on="cnpj_fundo",
            how="left",
            validate="one_to_one",
        )
    if "acao_status" not in queue.columns:
        queue["acao_status"] = "pendente"
    else:
        queue["acao_status"] = queue["acao_status"].fillna("").replace("", "pendente")

    doc = _documentary_by_fund(documentary, reconciliation)
    if not doc.empty:
        wanted = [
            "cnpj_fundo",
            "document_segment_n1",
            "document_segment_n2",
            "classification_confidence",
            "classification_evidence",
            "source",
        ]
        documentary_fields = doc[[column for column in wanted if column in doc.columns]].rename(
            columns={
                "classification_evidence": "document_classification_evidence",
                "source": "document_source",
            }
        )
        queue = queue.merge(documentary_fields, on="cnpj_fundo", how="left")
    for column in (
        "document_segment_n1",
        "document_segment_n2",
        "classification_confidence",
        "document_classification_evidence",
        "document_source",
    ):
        if column not in queue.columns:
            queue[column] = ""
        queue[column] = queue[column].fillna("").astype(str)
    # Compatibility aliases remain documentary and never overwrite the
    # immutable ANBIMA classification fields.
    queue["classification_evidence"] = queue["document_classification_evidence"]
    queue["source"] = queue["document_source"]
    suggestions = queue.apply(
        lambda row: suggested_anbima_pair(row["document_segment_n1"], row["document_segment_n2"]),
        axis=1,
    )
    queue["sugestao_tipo_analitico"] = [pair[0] for pair in suggestions]
    queue["sugestao_foco_analitico"] = [pair[1] for pair in suggestions]
    queue["pl_reclassificado_brl"] = queue["pl"].where(
        queue["taxonomy_review_applied"] & queue["tipo_slide_curado"].ne("Outros"),
        0.0,
    )
    return queue.sort_values(["pl", "cnpj_fundo"], ascending=[False, True]).reset_index(drop=True)


def taxonomy_review_summary(
    funds: pd.DataFrame,
    actions: pd.DataFrame | None,
    *,
    latest: str,
) -> dict[str, object]:
    """Reconcile the official slide bucket, approved reductions and residual."""

    latest_funds = funds[
        funds["competencia"].astype(str).eq(latest)
        & ~funds["is_fic_fidc"].fillna(False).astype(bool)
    ].copy()
    latest_funds["pl"] = pd.to_numeric(latest_funds["pl"], errors="coerce").fillna(0.0)
    latest_funds = latest_funds.sort_values(["pl", "cnpj_fundo"], ascending=[False, True])
    latest_funds["rank_mercado"] = range(1, len(latest_funds) + 1)
    latest_funds = apply_taxonomy_review_overlay(latest_funds, actions)
    official = latest_funds["anbima_tipo_oficial"].map(_display_type)
    curated = latest_funds["anbima_tipo_curado"].map(_display_type)
    official_outros = float(latest_funds.loc[official.eq("Outros"), "pl"].sum())
    curated_outros = float(latest_funds.loc[curated.eq("Outros"), "pl"].sum())
    approved_change = latest_funds["taxonomy_review_applied"] & official.ne(curated)
    removed = official.eq("Outros") & curated.ne("Outros") & latest_funds["taxonomy_review_applied"]
    added = official.ne("Outros") & curated.eq("Outros") & latest_funds["taxonomy_review_applied"]
    top100 = latest_funds["rank_mercado"].le(100)
    destinations = (
        latest_funds[removed]
        .groupby(["anbima_tipo_curado", "anbima_foco_curado"], as_index=False)
        .agg(pl_brl=("pl", "sum"), fundos=("cnpj_fundo", "nunique"))
        .sort_values("pl_brl", ascending=False)
    )
    return {
        "competencia": latest,
        "pl_ex_fic_brl": float(latest_funds["pl"].sum()),
        "outros_oficial_brl": official_outros,
        "outros_curado_brl": curated_outros,
        "reducao_liquida_brl": official_outros - curated_outros,
        "pl_reclassificado_para_fora_brl": float(latest_funds.loc[removed, "pl"].sum()),
        "pl_adicionado_a_outros_brl": float(latest_funds.loc[added, "pl"].sum()),
        "decisoes_aplicadas": int(latest_funds["taxonomy_review_applied"].sum()),
        "decisoes_com_mudanca": int(approved_change.sum()),
        "fundos_outros_oficial": int(latest_funds.loc[official.eq("Outros"), "cnpj_fundo"].nunique()),
        "fundos_outros_curado": int(latest_funds.loc[curated.eq("Outros"), "cnpj_fundo"].nunique()),
        "top100_outros_oficial_brl": float(latest_funds.loc[top100 & official.eq("Outros"), "pl"].sum()),
        "top100_outros_curado_brl": float(latest_funds.loc[top100 & curated.eq("Outros"), "pl"].sum()),
        "destinos": destinations,
    }


__all__ = [
    "ANBIMA_FOCUS_BY_TYPE",
    "ANBIMA_TYPES",
    "FUNCTIONAL_TAXONOMY",
    "TAXONOMY_CONFIDENCE_LEVELS",
    "TAXONOMY_REVIEW_COLUMNS",
    "TAXONOMY_REVIEW_STATUSES",
    "apply_taxonomy_review_overlay",
    "build_taxonomy_review_queue",
    "load_taxonomy_review_actions",
    "normalize_cnpj",
    "save_taxonomy_review_actions",
    "suggested_anbima_pair",
    "taxonomy_review_ledger_digest",
    "taxonomy_review_summary",
    "validate_taxonomy_review_action",
]
