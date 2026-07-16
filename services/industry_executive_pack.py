"""Pure, auditable analytics for the executive FIDC industry pack.

The module deliberately does not read files or render UI/PPTX.  Callers pass the
already loaded CVM frames and receive presentation-ready tables with explicit
classification provenance, coverage and warnings.

Two rules are intentionally conservative:

* fund/class rows are summed before any market analysis; and
* missing ANBIMA evidence is never silently relabelled as ``Outros``.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable, Mapping

import pandas as pd

from services.industry_anbima import (
    ANBIMA_FOCUS_BY_TYPE as OFFICIAL_ANBIMA_FOCUS_BY_TYPE,
    ANBIMA_TYPES as OFFICIAL_ANBIMA_TYPES,
)
from services.industry_intelligence import canonical_provider


ANBIMA_TYPES: tuple[str, ...] = (
    "Fomento Mercantil",
    "Agro, Indústria e Comércio",
    "Financeiro",
    "Outros",
)
if set(ANBIMA_TYPES) != set(OFFICIAL_ANBIMA_TYPES):
    raise AssertionError("taxonomia executiva diverge da whitelist oficial ANBIMA")
ANBIMA_ND = "N/D"
ANBIMA_FIC = "FIC-FIDC"
ANBIMA_CLASSIFICATION_VALUES: tuple[str, ...] = (*ANBIMA_TYPES, ANBIMA_ND, ANBIMA_FIC)

ANBIMA_FOCUS_BY_TYPE: Mapping[str, tuple[str, ...]] = {
    **OFFICIAL_ANBIMA_FOCUS_BY_TYPE,
    ANBIMA_ND: (ANBIMA_ND,),
    ANBIMA_FIC: (ANBIMA_FIC,),
}

HOLDER_BUCKETS: tuple[str, ...] = ("0", "1", "2–3", "4–10", "11–50", "51+")
STRUCTURE_MODELS: tuple[str, ...] = (
    "Monoestrutura",
    "Administração + Gestão",
    "Administração + Custódia",
    "Gestão + Custódia",
    "Três prestadores distintos",
    "Dados incompletos",
)
ROLE_COLUMNS: Mapping[str, str] = {
    "administrador": "admin_nome",
    "gestor": "gestor_nome",
    "custodiante": "custodiante_nome",
}


@dataclass(frozen=True)
class ExecutiveCompetences:
    """Audited periods used in the executive pack."""

    december_2024: str
    december_2025: str
    latest_complete: str
    latest_available: str
    excluded_tail: tuple[str, ...] = ()

    @property
    def ordered(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.december_2024, self.december_2025, self.latest_complete)))

    @property
    def period_by_competence(self) -> dict[str, str]:
        labels = {
            self.december_2024: "2024",
            self.december_2025: "2025",
            self.latest_complete: str(self.latest_complete)[:4],
        }
        return {competence: labels[competence] for competence in self.ordered}


@dataclass(frozen=True)
class IndustryExecutivePack:
    """All pure analytical outputs needed by the Industry UI and deck."""

    competences: ExecutiveCompetences
    fund_monthly: pd.DataFrame
    annual_pl: pd.DataFrame
    market_share: pd.DataFrame
    top_20_outros: pd.DataFrame
    curation_queue: pd.DataFrame
    holder_histogram: pd.DataFrame
    holder_coverage: pd.DataFrame
    monostructure_history: pd.DataFrame
    rankings: pd.DataFrame
    coverage: pd.DataFrame
    source_conflicts: pd.DataFrame
    warnings: tuple[str, ...]

    @property
    def latest_funds(self) -> pd.DataFrame:
        return self.fund_monthly[
            self.fund_monthly["competencia"].eq(self.competences.latest_complete)
        ].copy()


def _normalized_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Z0-9]+", " ", text.upper())
    return re.sub(r"\s+", " ", text).strip()


def _clean_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = re.sub(r"\s+", " ", str(value).strip())
    return "" if text.lower() in {"", "nan", "none", "nat", "n/d", "n.a."} else text


def _normalize_cnpj(value: object) -> str:
    raw = _clean_text(value)
    if not raw:
        return ""
    if re.fullmatch(r"\d{13,14}(?:\.0+)?", raw):
        raw = raw.split(".", 1)[0]
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 13:
        digits = digits.zfill(14)
    return digits if len(digits) == 14 else ""


def _competence_key(value: object) -> str:
    text = _clean_text(value)
    match = re.search(r"(20\d{2})[-/](1[0-2]|0?[1-9])(?:\D|$)", text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    parsed = pd.to_datetime(text, errors="coerce")
    return "" if pd.isna(parsed) else parsed.strftime("%Y-%m")


def _as_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    normalized = series.fillna("").map(_normalized_text)
    return normalized.isin({"TRUE", "T", "SIM", "S", "1", "Y", "YES"})


def _join_warnings(values: Iterable[object]) -> str:
    warnings: list[str] = []
    for value in values:
        for item in str(value or "").split(" | "):
            item = item.strip()
            if item and item not in warnings:
                warnings.append(item)
    return " | ".join(warnings)


def select_executive_competences(competence_status: pd.DataFrame) -> ExecutiveCompetences:
    """Select Dec/24, Dec/25 and the last competence explicitly marked complete."""

    if competence_status is None or competence_status.empty:
        raise ValueError("competence_status vazio: não é seguro inferir a última competência completa")
    required = {"competencia", "publication_status"}
    missing = required.difference(competence_status.columns)
    if missing:
        raise ValueError(f"competence_status sem colunas obrigatórias: {sorted(missing)}")

    status = competence_status.copy()
    status["competencia"] = status["competencia"].map(_competence_key)
    status = status[status["competencia"].ne("")].sort_values("competencia")
    status["_is_complete"] = status["publication_status"].map(_normalized_text).eq("COMPLETA")
    complete = status[status["_is_complete"]]
    if complete.empty:
        raise ValueError("nenhuma competência foi explicitamente marcada como completa")
    complete_keys = set(complete["competencia"])
    missing_decembers = [key for key in ("2024-12", "2025-12") if key not in complete_keys]
    if missing_decembers:
        raise ValueError(
            "competências anuais obrigatórias ausentes ou não completas: " + ", ".join(missing_decembers)
        )

    latest_complete = str(complete.iloc[-1]["competencia"])
    latest_available = str(status.iloc[-1]["competencia"])
    excluded = tuple(status.loc[status["competencia"].gt(latest_complete), "competencia"].astype(str))
    return ExecutiveCompetences(
        december_2024="2024-12",
        december_2025="2025-12",
        latest_complete=latest_complete,
        latest_available=latest_available,
        excluded_tail=excluded,
    )


def aggregate_vehicle_monthly_by_fund(vehicle_monthly: pd.DataFrame) -> pd.DataFrame:
    """Aggregate every fund/class row by CNPJ and competence.

    Numeric class values are summed with ``min_count=1``.  Text attributes come
    from the class with the largest absolute PL, while conflicts remain visible
    through count and warning fields.
    """

    if vehicle_monthly is None or vehicle_monthly.empty:
        return pd.DataFrame()
    required = {"competencia", "pl"}
    missing = required.difference(vehicle_monthly.columns)
    if missing:
        raise ValueError(f"vehicle_monthly sem colunas obrigatórias: {sorted(missing)}")
    if "cnpj_fundo" not in vehicle_monthly.columns and "cnpj" not in vehicle_monthly.columns:
        raise ValueError("vehicle_monthly precisa conter cnpj_fundo ou cnpj")

    base = vehicle_monthly.copy().reset_index(drop=True)
    base["competencia"] = base["competencia"].map(_competence_key)
    base = base[base["competencia"].ne("")].copy()
    identifier = base.get("cnpj_fundo", pd.Series("", index=base.index)).map(_normalize_cnpj)
    if "cnpj" in base.columns:
        fallback = base["cnpj"].map(_normalize_cnpj)
        identifier = identifier.where(identifier.ne(""), fallback)
    base["cnpj_fundo"] = identifier
    base["cnpj_classe"] = (
        base["cnpj"].map(_normalize_cnpj) if "cnpj" in base.columns else identifier
    )
    base["cnpj_valid"] = identifier.ne("")
    base["_row_order"] = range(len(base))
    base["fund_key"] = identifier
    invalid = ~base["cnpj_valid"]
    base.loc[invalid, "fund_key"] = (
        "SEM_CNPJ:" + base.loc[invalid, "competencia"] + ":" + base.loc[invalid, "_row_order"].astype(str)
    )

    base["_pl"] = pd.to_numeric(base["pl"], errors="coerce")
    base["_pl_abs"] = base["_pl"].abs().fillna(-1)
    if "cotistas" in base.columns:
        base["_cotistas"] = pd.to_numeric(base["cotistas"], errors="coerce")
    else:
        base["_cotistas"] = pd.Series(float("nan"), index=base.index, dtype=float)
    if "is_fic_fidc" in base.columns:
        base["_is_fic"] = _as_bool(base["is_fic_fidc"])
    else:
        base["_is_fic"] = False
    for source_column in (
        "tab4_duplicate_detected",
        "tab4_type_conflict",
        "tab4_pl_conflict",
    ):
        base[f"_{source_column}"] = (
            _as_bool(base[source_column])
            if source_column in base.columns
            else pd.Series(False, index=base.index)
        )
    base["_tab4_duplicate_rows_dropped"] = pd.to_numeric(
        base.get("tab4_duplicate_rows_dropped", pd.Series(0, index=base.index)),
        errors="coerce",
    ).fillna(0)
    base["_tab4_warning"] = base.get(
        "tab4_warning", pd.Series("", index=base.index)
    ).map(_clean_text)

    text_columns = [
        "denominacao",
        "admin_nome",
        "gestor_nome",
        "custodiante_nome",
        "segmento_principal",
        "segmento_financeiro_principal",
        "classificacao_anbima",
        "publico_alvo",
    ]
    for column in text_columns:
        if column not in base.columns:
            base[column] = ""
        base[column] = base[column].map(_clean_text)

    keys = ["competencia", "fund_key"]
    dominant = (
        base.sort_values(keys + ["_pl_abs", "_row_order"], ascending=[True, True, False, True])
        .drop_duplicates(keys)
        [keys + ["cnpj_fundo", "cnpj_classe", "cnpj_valid", *text_columns]]
    )
    grouped = (
        base.groupby(keys, dropna=False)
        .agg(
            pl=("_pl", lambda values: values.sum(min_count=1)),
            cotistas=("_cotistas", lambda values: values.sum(min_count=1)),
            is_fic_fidc=("_is_fic", "any"),
            source_rows=("fund_key", "size"),
            pl_source_rows=("_pl", "count"),
            cotistas_source_rows=("_cotistas", "count"),
            fic_value_count=("_is_fic", "nunique"),
            tab4_duplicate_detected=("_tab4_duplicate_detected", "any"),
            tab4_type_conflict=("_tab4_type_conflict", "any"),
            tab4_pl_conflict=("_tab4_pl_conflict", "any"),
            tab4_duplicate_rows_dropped=("_tab4_duplicate_rows_dropped", "sum"),
            tab4_warning=("_tab4_warning", _join_warnings),
            admin_value_count=("admin_nome", lambda values: values[values.ne("")].nunique()),
            gestor_value_count=("gestor_nome", lambda values: values[values.ne("")].nunique()),
            custodiante_value_count=("custodiante_nome", lambda values: values[values.ne("")].nunique()),
            segmento_value_count=("segmento_principal", lambda values: values[values.ne("")].nunique()),
            segmento_cvm_values=(
                "segmento_principal",
                lambda values: " | ".join(sorted(set(values[values.ne("")].astype(str)))),
            ),
            cnpj_classe_count=("cnpj_classe", lambda values: values[values.ne("")].nunique()),
            cnpj_classes=(
                "cnpj_classe",
                lambda values: " | ".join(sorted(set(values[values.ne("")].astype(str)))),
            ),
        )
        .reset_index()
    )
    output = grouped.merge(dominant, on=keys, how="left", validate="one_to_one")

    def aggregation_warning(row: pd.Series) -> str:
        warnings: list[str] = []
        if not bool(row["cnpj_valid"]):
            warnings.append("CNPJ do fundo inválido; linha preservada com chave técnica")
        if pd.isna(row["pl"]):
            warnings.append("PL não disponível nas classes")
        if int(row["fic_value_count"]) > 1:
            warnings.append("classes divergem sobre identificação FIC-FIDC")
        if int(row["admin_value_count"]) > 1:
            warnings.append("classes divergem sobre administrador")
        if int(row["gestor_value_count"]) > 1:
            warnings.append("classes divergem sobre gestor")
        if int(row["custodiante_value_count"]) > 1:
            warnings.append("classes divergem sobre custodiante")
        if int(row["segmento_value_count"]) > 1:
            warnings.append("classes divergem sobre segmento CVM")
        if bool(row["tab4_duplicate_detected"]):
            warnings.append(
                str(row["tab4_warning"])
                or "Tab IV continha registros repetidos; uma única linha foi selecionada"
            )
        return " | ".join(warnings)

    output["aggregation_warning"] = output.apply(aggregation_warning, axis=1)
    output["aggregation_status"] = output["aggregation_warning"].eq("").map({True: "ok", False: "atenção"})
    output["cotistas_aggregation_method"] = (
        "soma das classes; contas não deduplicadas entre classes"
    )
    output["pl"] = pd.to_numeric(output["pl"], errors="coerce")
    output["cotistas"] = pd.to_numeric(output["cotistas"], errors="coerce")
    output = output.sort_values(["competencia", "pl", "fund_key"], ascending=[True, False, True])
    return output.reset_index(drop=True)


_TYPE_ALIASES: Mapping[str, str] = {
    "FOMENTO MERCANTIL": "Fomento Mercantil",
    "AGRO INDUSTRIA E COMERCIO": "Agro, Indústria e Comércio",
    "AGRO INDUSTRIA COMERCIO": "Agro, Indústria e Comércio",
    "AGRO INDUSTRIA E COMERCIO E": "Agro, Indústria e Comércio",
    "FINANCEIRO": "Financeiro",
    "OUTROS": "Outros",
}

_FOCUS_ALIASES: Mapping[str, str] = {
    _normalized_text(focus): focus
    for focuses in ANBIMA_FOCUS_BY_TYPE.values()
    for focus in focuses
}
_FOCUS_ALIASES = {
    **_FOCUS_ALIASES,
    "CONSIGNADO": "Crédito Consignado",
    "CREDITO CONSIGNADO": "Crédito Consignado",
    "PESSOAL": "Crédito Pessoal",
    "VEICULOS": "Financiamento de Veículos",
    "CREDITO VEICULOS": "Financiamento de Veículos",
    "FINANCIAMENTO DE VEICULOS": "Financiamento de Veículos",
    "IMOBILIARIO": "Crédito Imobiliário",
    "MULTICARTEIRAS OUTROS": "Multicarteira Outros",
    "MULTICARTEIRA AIC": "Multicarteira Agro, Indústria e Comércio",
}


def _canonical_anbima_type(value: object) -> str:
    normalized = _normalized_text(value)
    if normalized.startswith("FIDC "):
        normalized = normalized[5:].strip()
    return _TYPE_ALIASES.get(normalized, "")


def _canonical_anbima_focus(value: object, anbima_type: str) -> str:
    focus = _FOCUS_ALIASES.get(_normalized_text(value), "")
    return focus if focus in ANBIMA_FOCUS_BY_TYPE.get(anbima_type, ()) else ""


def _first_existing_column(frame: pd.DataFrame, candidates: Iterable[str]) -> str:
    return next((column for column in candidates if column in frame.columns), "")


def _column_by_semantic_name(frame: pd.DataFrame, candidates: Iterable[str]) -> str:
    lookup = {_normalized_text(column): column for column in frame.columns}
    return next((lookup[name] for name in map(_normalized_text, candidates) if name in lookup), "")


def _prepare_official_anbima(classification: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize the public ANBIMA file without inferring unknown labels."""

    columns = [
        "official_cnpj_fundo",
        "official_cnpj_classe",
        "official_type",
        "official_focus",
        "official_source",
        "official_snapshot_date",
        "official_evidence",
        "official_conflict",
        "official_invalid",
    ]
    if classification is None or classification.empty:
        return pd.DataFrame(columns=columns)
    frame = classification.copy().reset_index(drop=True)
    fund_col = _column_by_semantic_name(
        frame, ("cnpj_fundo", "CNPJ Fundo", "CNPJ do Fundo", "fund_cnpj")
    )
    class_col = _column_by_semantic_name(
        frame, ("cnpj_classe", "CNPJ Classe", "CNPJ da Classe", "class_cnpj")
    )
    type_col = _column_by_semantic_name(
        frame, ("tipo_anbima", "Tipo ANBIMA", "anbima_tipo", "anbima_type")
    )
    focus_col = _column_by_semantic_name(
        frame,
        (
            "foco_atuacao",
            "Foco de Atuação",
            "Foco Atuacao",
            "foco_anbima",
            "anbima_foco",
            "anbima_focus",
        ),
    )
    source_col = _column_by_semantic_name(
        frame, ("source", "source_kind", "fonte", "classification_source")
    )
    snapshot_col = _column_by_semantic_name(
        frame,
        ("source_snapshot_date", "source_published_date", "data_fotografia", "snapshot_date"),
    )
    evidence_col = _column_by_semantic_name(
        frame, ("evidence", "evidencia", "classification_evidence")
    )
    if not type_col or (not fund_col and not class_col):
        return pd.DataFrame(columns=columns)
    frame["official_cnpj_fundo"] = frame[fund_col].map(_normalize_cnpj) if fund_col else ""
    frame["official_cnpj_classe"] = frame[class_col].map(_normalize_cnpj) if class_col else ""
    frame["official_type"] = frame[type_col].map(_canonical_anbima_type)
    if focus_col:
        frame["official_focus"] = [
            _canonical_anbima_focus(focus, anbima_type)
            for focus, anbima_type in zip(frame[focus_col], frame["official_type"])
        ]
    else:
        frame["official_focus"] = ""
    frame["official_source"] = (
        frame[source_col].map(_clean_text) if source_col else "ANBIMA Data — arquivo público de características"
    )
    frame["official_snapshot_date"] = (
        frame[snapshot_col].map(_clean_text) if snapshot_col else ""
    )
    frame["official_evidence"] = (
        frame[evidence_col].map(_clean_text)
        if evidence_col
        else "tipo e foco de atuação do cadastro público ANBIMA"
    )
    frame["official_invalid"] = frame["official_type"].eq("")
    frame = frame[
        frame["official_cnpj_fundo"].ne("") | frame["official_cnpj_classe"].ne("")
    ].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    conflict_keys: set[tuple[str, str]] = set()
    for key_column in ("official_cnpj_classe", "official_cnpj_fundo"):
        valid = frame[frame[key_column].ne("") & frame["official_type"].ne("")]
        for key in valid.groupby(key_column)["official_type"].nunique().loc[lambda values: values.gt(1)].index:
            conflict_keys.add((key_column, str(key)))
    frame["official_conflict"] = [
        ("official_cnpj_classe", str(class_cnpj)) in conflict_keys
        or ("official_cnpj_fundo", str(fund_cnpj)) in conflict_keys
        for class_cnpj, fund_cnpj in zip(
            frame["official_cnpj_classe"], frame["official_cnpj_fundo"]
        )
    ]
    return frame[columns].reset_index(drop=True)


def _prepare_published_classifications(published: pd.DataFrame | None) -> pd.DataFrame:
    columns = [
        "cnpj_fundo",
        "published_competencia",
        "published_type",
        "published_focus",
        "published_evidence",
        "published_source",
        "published_conflict",
        "published_invalid",
    ]
    if published is None or published.empty:
        return pd.DataFrame(columns=columns)
    frame = published.copy().reset_index(drop=True)
    cnpj_col = _first_existing_column(frame, ("cnpj_fundo", "cnpj", "fund_cnpj"))
    type_col = _first_existing_column(
        frame,
        ("anbima_type_document", "anbima_tipo", "anbima_type", "tipo_anbima"),
    )
    if not cnpj_col or not type_col:
        return pd.DataFrame(columns=columns)
    focus_col = _first_existing_column(
        frame,
        ("anbima_focus_document", "anbima_foco", "anbima_focus", "foco_anbima"),
    )
    evidence_col = _first_existing_column(
        frame,
        ("anbima_evidence", "classification_evidence", "evidence", "evidencia"),
    )
    source_col = _first_existing_column(frame, ("source", "classification_source", "fonte"))
    competence_col = _first_existing_column(
        frame,
        ("competencia", "competencia_snapshot", "effective_competence"),
    )

    frame["cnpj_fundo"] = frame[cnpj_col].map(_normalize_cnpj)
    frame["published_competencia"] = frame[competence_col].map(_competence_key) if competence_col else ""
    frame["published_type"] = frame[type_col].map(_canonical_anbima_type)
    if focus_col:
        frame["published_focus"] = [
            _canonical_anbima_focus(focus, anbima_type)
            for focus, anbima_type in zip(frame[focus_col], frame["published_type"])
        ]
    else:
        frame["published_focus"] = ""
    frame["published_evidence"] = frame[evidence_col].map(_clean_text) if evidence_col else ""
    frame["published_source"] = frame[source_col].map(_clean_text) if source_col else "evidência publicada"
    frame["published_invalid"] = frame["published_type"].eq("")
    frame = frame[frame["cnpj_fundo"].ne("")].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)

    frame["_row_order"] = range(len(frame))
    frame["_sort_comp"] = frame["published_competencia"].replace("", "0000-00")
    conflict = (
        frame[frame["published_type"].ne("")]
        .groupby(["cnpj_fundo", "published_competencia"])["published_type"]
        .nunique()
        .gt(1)
    )
    frame = (
        frame.sort_values(
            ["cnpj_fundo", "_sort_comp", "published_invalid", "_row_order"],
            ascending=[True, False, True, True],
        )
        .drop_duplicates(["cnpj_fundo", "published_competencia"])
        .copy()
    )
    frame["published_conflict"] = [
        bool(conflict.get((cnpj, competence), False))
        for cnpj, competence in zip(frame["cnpj_fundo"], frame["published_competencia"])
    ]
    return frame[columns].reset_index(drop=True)


def _proxy_cvm_classification(segment: object, financial_segment: object) -> tuple[str, str, str]:
    top = _normalized_text(segment)
    financial = _normalized_text(financial_segment)
    combined = f"{top} {financial}".strip()
    if top == "FACTORING" or "FOMENTO MERCANTIL" in combined:
        return "Fomento Mercantil", "Fomento Mercantil", "segmento CVM Factoring"
    if top in {"FINANCEIRO", "IMOBILIARIO"}:
        if "IMOBILI" in combined:
            focus = "Crédito Imobiliário"
        elif "CONSIGN" in combined or "INSS" in combined or "FGTS" in combined:
            focus = "Crédito Consignado"
        elif "VEICUL" in combined or "AUTO" in combined:
            focus = "Financiamento de Veículos"
        elif "PESSOAL" in combined or "CONSUM" in combined:
            focus = "Crédito Pessoal"
        else:
            focus = "Multicarteira Financeiro"
        return "Financeiro", focus, f"segmento CVM {top or 'Financeiro'}"
    if top in {"AGRONEGOCIO", "AGRO"}:
        return "Agro, Indústria e Comércio", "Agronegócio", "segmento CVM Agronegócio"
    if top in {"INDUSTRIAL", "INDUSTRIA"}:
        return "Agro, Indústria e Comércio", "Crédito Corporativo", "segmento CVM Industrial"
    if top in {"COMERCIAL", "CARTAO DE CREDITO", "SERVICOS"}:
        return "Agro, Indústria e Comércio", "Recebíveis Comerciais", f"segmento CVM {top.title()}"
    if top in {"INFRAESTRUTURA", "ENERGIA"}:
        return "Agro, Indústria e Comércio", "Infraestrutura", f"segmento CVM {top.title()}"
    if top in {"ACOES JUDICIAIS", "JUDICIAL", "PRECATORIOS", "NPL"}:
        return "Outros", "Recuperação", f"segmento CVM {top.title()}"
    if top in {"SETOR PUBLICO", "PODER PUBLICO"}:
        return "Outros", "Poder Público", f"segmento CVM {top.title()}"
    return ANBIMA_ND, ANBIMA_ND, "segmento CVM sem equivalência segura"


def apply_anbima_classification(
    fund_monthly: pd.DataFrame,
    anbima_classification: pd.DataFrame | None = None,
    published_classifications: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Attach whitelisted ANBIMA type/focus and explicit provenance to each fund."""

    if fund_monthly is None or fund_monthly.empty:
        return pd.DataFrame()
    funds = fund_monthly.copy()
    official = _prepare_official_anbima(anbima_classification)
    published = _prepare_published_classifications(published_classifications)
    official_by_class: dict[str, list[pd.Series]] = {}
    official_by_fund: dict[str, list[pd.Series]] = {}
    for _, row in official.iterrows():
        if row["official_cnpj_classe"]:
            official_by_class.setdefault(str(row["official_cnpj_classe"]), []).append(row)
        if row["official_cnpj_fundo"]:
            official_by_fund.setdefault(str(row["official_cnpj_fundo"]), []).append(row)
    exact: dict[tuple[str, str], pd.Series] = {}
    timeless: dict[str, pd.Series] = {}
    for _, row in published.iterrows():
        if row["published_competencia"]:
            exact[(row["cnpj_fundo"], row["published_competencia"])] = row
        elif row["cnpj_fundo"] not in timeless:
            timeless[row["cnpj_fundo"]] = row

    records: list[dict[str, object]] = []
    for row in funds.itertuples(index=False):
        row_dict = row._asdict()
        warnings = [row_dict.get("aggregation_warning", "")]
        anbima_type = ANBIMA_ND
        focus = ANBIMA_ND
        tier = "nao_disponivel"
        status = "N/D"
        source = ""
        evidence = ""
        requires_warning = True

        if bool(row_dict.get("is_fic_fidc", False)):
            anbima_type = ANBIMA_FIC
            focus = ANBIMA_FIC
            tier = "fic_separado"
            status = "FIC separado"
            source = "campo is_fic_fidc do Informe Mensal CVM"
            evidence = "FIC-FIDC é apresentado fora da taxonomia de quatro tipos"
            requires_warning = False
        else:
            published_row = exact.get(
                (row_dict.get("cnpj_fundo", ""), row_dict.get("competencia", ""))
            )
            if published_row is None:
                published_row = timeless.get(row_dict.get("cnpj_fundo", ""))
            class_identifiers = [
                _normalize_cnpj(row_dict.get("cnpj_classe", "")),
                *[
                    _normalize_cnpj(value)
                    for value in str(row_dict.get("cnpj_classes", "") or "").split(" | ")
                ],
            ]
            class_identifiers = list(dict.fromkeys(value for value in class_identifiers if value))
            official_candidates: list[pd.Series] = []
            all_class_candidates: list[pd.Series] = []
            official_match_level = ""
            for class_cnpj in class_identifiers:
                valid = [
                    candidate
                    for candidate in official_by_class.get(class_cnpj, [])
                    if not bool(candidate["official_invalid"])
                ]
                all_class_candidates.extend(valid)
                if valid and not official_candidates:
                    official_candidates = valid
                    official_match_level = "CNPJ da classe"
            if not official_candidates:
                official_candidates = [
                    candidate
                    for candidate in official_by_fund.get(str(row_dict.get("cnpj_fundo", "")), [])
                    if not bool(candidate["official_invalid"])
                ]
                if official_candidates:
                    official_match_level = "CNPJ do fundo"

            if official_candidates:
                official_row = official_candidates[0]
                anbima_type = str(official_row["official_type"])
                focus = str(official_row["official_focus"] or ANBIMA_ND)
                tier = "oficial_anbima"
                status = f"Classificação oficial ANBIMA por {official_match_level}"
                source = str(
                    official_row["official_source"]
                    or "ANBIMA Data — arquivo público de características"
                )
                evidence = str(
                    official_row["official_evidence"]
                    or "tipo e foco de atuação do cadastro público ANBIMA"
                )
                conflict_candidates = all_class_candidates or official_candidates
                distinct_types = {str(candidate["official_type"]) for candidate in conflict_candidates}
                conflict = len(distinct_types) > 1 or any(
                    bool(candidate["official_conflict"]) for candidate in conflict_candidates
                )
                requires_warning = focus == ANBIMA_ND or conflict
                if focus == ANBIMA_ND:
                    warnings.append("tipo oficial ANBIMA disponível, mas foco ausente ou fora da whitelist")
                if conflict:
                    warnings.append("cadastro oficial ANBIMA contém classificações conflitantes")
                source_snapshot = _competence_key(official_row["official_snapshot_date"])
                row_competence = str(row_dict.get("competencia", ""))
                if source_snapshot and row_competence and source_snapshot != row_competence:
                    requires_warning = True
                    if row_competence < source_snapshot:
                        warnings.append(
                            "classificação ANBIMA cadastral de dez/25 aplicada retrospectivamente"
                        )
                    else:
                        warnings.append(
                            "classificação ANBIMA cadastral de dez/25 aplicada após a fotografia; validar novos fundos"
                        )
                if published_row is not None and not bool(published_row["published_invalid"]):
                    documentary_type = str(published_row["published_type"])
                    documentary_focus = str(published_row["published_focus"] or ANBIMA_ND)
                    if documentary_type and documentary_type != anbima_type:
                        requires_warning = True
                        warnings.append(
                            "cadastro oficial ANBIMA diverge da evidência documental publicada"
                        )
                    elif (
                        documentary_focus != ANBIMA_ND
                        and focus != ANBIMA_ND
                        and documentary_focus != focus
                    ):
                        requires_warning = True
                        warnings.append(
                            "foco oficial ANBIMA diverge da evidência documental publicada"
                        )
            else:
                invalid_official = any(
                    official_by_class.get(class_cnpj, []) for class_cnpj in class_identifiers
                ) or bool(official_by_fund.get(str(row_dict.get("cnpj_fundo", "")), []))
                if invalid_official:
                    warnings.append("classificação oficial ANBIMA rejeitada por estar fora da whitelist")
                if published_row is not None and not bool(published_row["published_invalid"]):
                    anbima_type = str(published_row["published_type"])
                    focus = str(published_row["published_focus"] or ANBIMA_ND)
                    tier = "evidencia_publicada"
                    status = "Evidência documental/manual publicada"
                    source = str(published_row["published_source"] or "evidência publicada")
                    evidence = str(published_row["published_evidence"] or "classificação publicada sem trecho transcrito")
                    requires_warning = focus == ANBIMA_ND or bool(published_row["published_conflict"])
                    if focus == ANBIMA_ND:
                        warnings.append("tipo publicado, mas foco ANBIMA ausente ou fora da whitelist")
                    if bool(published_row["published_conflict"]):
                        warnings.append("classificações publicadas conflitantes para o mesmo fundo")
                else:
                    if published_row is not None and bool(published_row["published_invalid"]):
                        warnings.append("classificação publicada rejeitada por estar fora da whitelist")
                    local_type = _canonical_anbima_type(row_dict.get("classificacao_anbima", ""))
                    if local_type:
                        anbima_type = local_type
                        focus = ANBIMA_ND
                        tier = "evidencia_publicada"
                        status = "Classificação publicada no cadastro CVM"
                        source = "campo classificacao_anbima do cadastro CVM"
                        evidence = _clean_text(row_dict.get("classificacao_anbima", ""))
                        requires_warning = True
                        warnings.append("tipo publicado, mas foco ANBIMA não disponível")
                    else:
                        anbima_type, focus, proxy_evidence = _proxy_cvm_classification(
                            row_dict.get("segmento_principal", ""),
                            row_dict.get("segmento_financeiro_principal", ""),
                        )
                        evidence = proxy_evidence
                        if anbima_type != ANBIMA_ND:
                            tier = "proxy_cvm"
                            status = "Proxy CVM; validar"
                            source = "equivalência metodológica a partir do segmento CVM"
                            warnings.append("proxy CVM não equivale a classificação ANBIMA publicada")
                        else:
                            warnings.append("sem evidência segura para classificação ANBIMA")

        if anbima_type not in ANBIMA_CLASSIFICATION_VALUES:
            raise AssertionError(f"tipo fora da whitelist: {anbima_type}")
        if focus not in ANBIMA_FOCUS_BY_TYPE[anbima_type] and focus != ANBIMA_ND:
            raise AssertionError(f"foco fora da whitelist para {anbima_type}: {focus}")
        records.append(
            {
                "anbima_tipo": anbima_type,
                "anbima_foco": focus,
                "classification_tier": tier,
                "classification_status": status,
                "classification_source": source,
                "classification_evidence": evidence,
                "classification_requires_warning": bool(requires_warning),
                "classification_warning": _join_warnings(warnings),
            }
        )
    classified = pd.concat([funds.reset_index(drop=True), pd.DataFrame(records)], axis=1)
    return classified


def _period_rows(competences: ExecutiveCompetences) -> list[tuple[str, str]]:
    return [(competence, competences.period_by_competence[competence]) for competence in competences.ordered]


def build_annual_pl(
    funds: pd.DataFrame,
    competences: ExecutiveCompetences,
    competence_status: pd.DataFrame | None = None,
    industry_monthly: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build Dec/Dec annual PL, with latest complete month for the current year."""

    status_lookup: dict[str, float] = {}
    if competence_status is not None and not competence_status.empty and "pl_total" in competence_status.columns:
        status = competence_status.copy()
        status["competencia"] = status["competencia"].map(_competence_key)
        status_lookup = dict(
            zip(status["competencia"], pd.to_numeric(status["pl_total"], errors="coerce"))
        )
    industry_lookup: dict[str, float] = {}
    if industry_monthly is not None and not industry_monthly.empty and "pl_total" in industry_monthly.columns:
        industry = industry_monthly.copy()
        industry["competencia"] = industry["competencia"].map(_competence_key)
        industry_lookup = dict(
            zip(industry["competencia"], pd.to_numeric(industry["pl_total"], errors="coerce"))
        )

    rows: list[dict[str, object]] = []
    for competence, period in _period_rows(competences):
        frame = funds[funds["competencia"].eq(competence)].copy()
        pl = pd.to_numeric(frame.get("pl"), errors="coerce")
        fic = frame.get("is_fic_fidc", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
        gross = float(pl.sum(min_count=1)) if pl.notna().any() else float("nan")
        fic_pl = float(pl[fic].sum(min_count=1)) if pl[fic].notna().any() else 0.0
        ex_fic = gross - fic_pl if pd.notna(gross) else float("nan")
        official_total = industry_lookup.get(competence, status_lookup.get(competence, float("nan")))
        coverage_ratio = gross / official_total if pd.notna(official_total) and official_total != 0 else float("nan")
        warning = ""
        if frame.empty:
            warning = "competência selecionada sem fundos agregados"
        elif pd.isna(coverage_ratio):
            warning = "total oficial de controle não disponível"
        elif not 0.995 <= coverage_ratio <= 1.005:
            warning = "PL agregado difere em mais de 0,5% do total oficial de controle"
        duplicate_funds = int(frame["tab4_duplicate_detected"].fillna(False).astype(bool).sum())
        pl_conflict_funds = int(frame["tab4_pl_conflict"].fillna(False).astype(bool).sum())
        if pl_conflict_funds:
            warning = _join_warnings(
                [
                    warning,
                    f"{pl_conflict_funds} CNPJs com PL conflitante na Tab IV; Classe priorizada sobre Fundo",
                ]
            )
        rows.append(
            {
                "period": period,
                "competencia": competence,
                "reference_kind": "dezembro" if competence.endswith("-12") else "última competência completa",
                "pl_total_brl": gross,
                "pl_fic_fidc_brl": fic_pl,
                "pl_ex_fic_brl": ex_fic,
                "funds_total": int(frame["fund_key"].nunique()) if not frame.empty else 0,
                "funds_fic_fidc": int(frame.loc[fic, "fund_key"].nunique()) if not frame.empty else 0,
                "official_control_pl_brl": official_total,
                "pl_coverage_ratio": coverage_ratio,
                "coverage_status": "ok" if pd.notna(coverage_ratio) and 0.995 <= coverage_ratio <= 1.005 else "atenção",
                "tab4_duplicate_funds": duplicate_funds,
                "tab4_pl_conflict_funds": pl_conflict_funds,
                "requires_warning": bool(warning),
                "warning": warning,
            }
        )
    output = pd.DataFrame(rows)
    output["pl_total_growth"] = output["pl_total_brl"].pct_change()
    output["pl_ex_fic_growth"] = output["pl_ex_fic_brl"].pct_change()
    return output


def build_market_share(funds: pd.DataFrame, competences: ExecutiveCompetences) -> pd.DataFrame:
    """Return four ANBIMA types plus a distinct N/D bucket, excluding FIC-FIDC."""

    rows: list[dict[str, object]] = []
    category_order = (*ANBIMA_TYPES, ANBIMA_ND)
    for competence, period in _period_rows(competences):
        frame = funds[
            funds["competencia"].eq(competence) & funds["anbima_tipo"].ne(ANBIMA_FIC)
        ].copy()
        frame["pl"] = pd.to_numeric(frame["pl"], errors="coerce")
        total_pl = float(frame["pl"].sum(min_count=1)) if frame["pl"].notna().any() else 0.0
        classified = frame[frame["anbima_tipo"].isin(ANBIMA_TYPES)]
        classified_pl = float(classified["pl"].sum(min_count=1)) if classified["pl"].notna().any() else 0.0
        proxy_pl = float(
            frame.loc[frame["classification_tier"].eq("proxy_cvm"), "pl"].sum(min_count=1)
        ) if frame.loc[frame["classification_tier"].eq("proxy_cvm"), "pl"].notna().any() else 0.0
        official_pl = float(
            frame.loc[frame["classification_tier"].eq("oficial_anbima"), "pl"].sum(min_count=1)
        ) if frame.loc[frame["classification_tier"].eq("oficial_anbima"), "pl"].notna().any() else 0.0
        evidence_pl = float(
            frame.loc[frame["classification_tier"].eq("evidencia_publicada"), "pl"].sum(min_count=1)
        ) if frame.loc[frame["classification_tier"].eq("evidencia_publicada"), "pl"].notna().any() else 0.0
        snapshot_bridge = frame["classification_warning"].astype(str).str.contains(
            "classificação ANBIMA cadastral", case=False, na=False
        )
        snapshot_bridge_pl = float(frame.loc[snapshot_bridge, "pl"].sum(min_count=1)) \
            if frame.loc[snapshot_bridge, "pl"].notna().any() else 0.0
        for order, category in enumerate(category_order):
            part = frame[frame["anbima_tipo"].eq(category)]
            category_pl = float(part["pl"].sum(min_count=1)) if part["pl"].notna().any() else 0.0
            rows.append(
                {
                    "period": period,
                    "competencia": competence,
                    "anbima_tipo": category,
                    "category_order": order,
                    "pl_brl": category_pl,
                    "funds": int(part["fund_key"].nunique()),
                    "share_ex_fic": category_pl / total_pl if total_pl else float("nan"),
                    "share_classified": (
                        category_pl / classified_pl
                        if classified_pl and category in ANBIMA_TYPES
                        else float("nan")
                    ),
                    "classified_pl_coverage": classified_pl / total_pl if total_pl else float("nan"),
                    "official_anbima_pl_coverage": official_pl / total_pl if total_pl else float("nan"),
                    "published_evidence_pl_coverage": evidence_pl / total_pl if total_pl else float("nan"),
                    "proxy_pl_share": proxy_pl / total_pl if total_pl else float("nan"),
                    "snapshot_bridge_pl_share": snapshot_bridge_pl / total_pl if total_pl else float("nan"),
                    "requires_warning": bool(
                        category == ANBIMA_ND or proxy_pl != 0 or snapshot_bridge_pl != 0
                    ),
                    "warning": _join_warnings(
                        [
                            "N/D não foi convertido em Outros" if category == ANBIMA_ND else "",
                            "market share inclui equivalências proxy CVM; validar" if proxy_pl != 0 else "",
                            "cadastro ANBIMA de dez/25 aplicado como ponte estática"
                            if snapshot_bridge_pl != 0
                            else "",
                        ]
                    ),
                }
            )
    return pd.DataFrame(rows).sort_values(["competencia", "category_order"]).reset_index(drop=True)


def build_outros_and_curation(
    funds: pd.DataFrame,
    latest_competence: str,
    *,
    limit: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the largest ``Outros`` funds and the auditable manual-review queue."""

    latest = funds[funds["competencia"].eq(latest_competence)].copy()
    latest["pl"] = pd.to_numeric(latest["pl"], errors="coerce")
    latest = latest.sort_values(["pl", "fund_key"], ascending=[False, True])
    columns = [
        "competencia",
        "cnpj_fundo",
        "denominacao",
        "pl",
        "anbima_tipo",
        "anbima_foco",
        "segmento_principal",
        "segmento_financeiro_principal",
        "classification_tier",
        "classification_status",
        "classification_source",
        "classification_evidence",
        "classification_requires_warning",
        "classification_warning",
    ]
    ex_fic_pl = latest.loc[latest["anbima_tipo"].ne(ANBIMA_FIC), "pl"].sum(min_count=1)
    top = latest[latest["anbima_tipo"].eq("Outros")].head(limit).copy()
    top["outros_rank"] = range(1, len(top) + 1)
    top["pl_share_ex_fic"] = top["pl"].div(ex_fic_pl) if pd.notna(ex_fic_pl) and ex_fic_pl else float("nan")
    top["cumulative_pl_share_ex_fic"] = top["pl_share_ex_fic"].cumsum()
    top["classification_is_published"] = top["classification_tier"].isin(
        ("oficial_anbima", "evidencia_publicada")
    )
    top = top[
        [
            "outros_rank",
            *[column for column in columns if column in top.columns],
            "pl_share_ex_fic",
            "cumulative_pl_share_ex_fic",
            "classification_is_published",
        ]
    ]

    queue = latest[latest["anbima_tipo"].isin(("Outros", ANBIMA_ND))].copy()
    queue["curation_reason"] = [
        "Sem evidência suficiente; manter N/D até validação"
        if anbima_type == ANBIMA_ND
        else "Confirmar se permanece em Outros ou admite reenquadramento documental"
        if tier in {"oficial_anbima", "evidencia_publicada"}
        else "Confirmar proxy CVM de Outros em evidência documental"
        for anbima_type, tier in zip(queue["anbima_tipo"], queue["classification_tier"])
    ]
    queue["curation_priority"] = range(1, len(queue) + 1)
    queue["requires_manual_review"] = True
    queue = queue[
        [
            "curation_priority",
            *[column for column in columns if column in queue.columns],
            "curation_reason",
            "requires_manual_review",
        ]
    ]
    return top.reset_index(drop=True), queue.reset_index(drop=True)


def _holder_bucket(value: float) -> str:
    if value == 0:
        return "0"
    if value == 1:
        return "1"
    if value <= 3:
        return "2–3"
    if value <= 10:
        return "4–10"
    if value <= 50:
        return "11–50"
    return "51+"


def build_holder_histograms(
    funds: pd.DataFrame,
    latest_competence: str,
    *,
    min_pl_brl: float = 200_000_000.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build count and PL histograms using explicit cotista buckets."""

    latest = funds[
        funds["competencia"].eq(latest_competence) & funds["anbima_tipo"].ne(ANBIMA_FIC)
    ].copy()
    latest["pl"] = pd.to_numeric(latest["pl"], errors="coerce")
    latest["cotistas"] = pd.to_numeric(latest["cotistas"], errors="coerce")
    eligible = latest[latest["pl"].ge(float(min_pl_brl))].copy()
    valid_cotistas = eligible["cotistas"].notna() & eligible["cotistas"].ge(0)
    included = eligible[valid_cotistas].copy()
    included["cotistas_bucket"] = included["cotistas"].map(_holder_bucket)

    rows: list[dict[str, object]] = []
    for type_order, anbima_type in enumerate((*ANBIMA_TYPES, ANBIMA_ND)):
        type_frame = included[included["anbima_tipo"].eq(anbima_type)]
        type_funds = int(type_frame["fund_key"].nunique())
        type_pl = float(type_frame["pl"].sum(min_count=1)) if type_frame["pl"].notna().any() else 0.0
        for bucket_order, bucket in enumerate(HOLDER_BUCKETS):
            part = type_frame[type_frame["cotistas_bucket"].eq(bucket)]
            fund_count = int(part["fund_key"].nunique())
            pl_brl = float(part["pl"].sum(min_count=1)) if part["pl"].notna().any() else 0.0
            rows.append(
                {
                    "competencia": latest_competence,
                    "min_pl_brl": float(min_pl_brl),
                    "anbima_tipo": anbima_type,
                    "type_order": type_order,
                    "cotistas_bucket": bucket,
                    "bucket_order": bucket_order,
                    "fund_count": fund_count,
                    "pl_brl": pl_brl,
                    "fund_share_within_type": fund_count / type_funds if type_funds else 0.0,
                    "pl_share_within_type": pl_brl / type_pl if type_pl else 0.0,
                }
            )

    eligible_pl = float(eligible["pl"].sum(min_count=1)) if eligible["pl"].notna().any() else 0.0
    included_pl = float(included["pl"].sum(min_count=1)) if included["pl"].notna().any() else 0.0
    missing = eligible[~valid_cotistas]
    coverage = pd.DataFrame(
        [
            {
                "competencia": latest_competence,
                "min_pl_brl": float(min_pl_brl),
                "eligible_funds": int(eligible["fund_key"].nunique()),
                "included_funds": int(included["fund_key"].nunique()),
                "fund_coverage": len(included) / len(eligible) if len(eligible) else float("nan"),
                "eligible_pl_brl": eligible_pl,
                "included_pl_brl": included_pl,
                "pl_coverage": included_pl / eligible_pl if eligible_pl else float("nan"),
                "funds_excluded_missing_cotistas": int(missing["fund_key"].nunique()),
                "pl_excluded_missing_cotistas_brl": float(missing["pl"].sum(min_count=1))
                if missing["pl"].notna().any()
                else 0.0,
                "warning": "fundos sem cotistas válidos foram excluídos do histograma" if not missing.empty else "",
            }
        ]
    )
    histogram = pd.DataFrame(rows).sort_values(["type_order", "bucket_order"]).reset_index(drop=True)
    return histogram, coverage


def _structure_model(row: pd.Series) -> str:
    admin = row["administrador_canonical"]
    manager = row["gestor_canonical"]
    custodian = row["custodiante_canonical"]
    missing = {"", "Não informado"}
    if admin in missing or manager in missing or custodian in missing:
        return "Dados incompletos"
    if admin == manager == custodian:
        return "Monoestrutura"
    if admin == manager:
        return "Administração + Gestão"
    if admin == custodian:
        return "Administração + Custódia"
    if manager == custodian:
        return "Gestão + Custódia"
    return "Três prestadores distintos"


def build_monostructure_history(
    funds: pd.DataFrame,
    competences: ExecutiveCompetences,
) -> pd.DataFrame:
    """Measure canonical admin/manager/custodian equality by fund count and PL."""

    selected = funds[funds["competencia"].isin(competences.ordered)].copy()
    selected["pl"] = pd.to_numeric(selected["pl"], errors="coerce")
    for role, column in ROLE_COLUMNS.items():
        selected[f"{role}_canonical"] = selected.get(column, pd.Series("", index=selected.index)).map(
            canonical_provider
        )
    selected["structure_model"] = selected.apply(_structure_model, axis=1)

    rows: list[dict[str, object]] = []
    for competence, period in _period_rows(competences):
        frame = selected[selected["competencia"].eq(competence)]
        total_funds = int(frame["fund_key"].nunique())
        total_pl = float(frame["pl"].sum(min_count=1)) if frame["pl"].notna().any() else 0.0
        known = frame[frame["structure_model"].ne("Dados incompletos")]
        known_funds = int(known["fund_key"].nunique())
        known_pl = float(known["pl"].sum(min_count=1)) if known["pl"].notna().any() else 0.0
        for order, model in enumerate(STRUCTURE_MODELS):
            part = frame[frame["structure_model"].eq(model)]
            funds_count = int(part["fund_key"].nunique())
            pl_brl = float(part["pl"].sum(min_count=1)) if part["pl"].notna().any() else 0.0
            historical_registry_proxy = competence != competences.latest_complete
            warning = _join_warnings(
                [
                    "gestor e custodiante reconstruídos com o cadastro CVM vigente; não é uma fotografia histórica"
                    if historical_registry_proxy
                    else "",
                    "prestador ausente; não inferir integração"
                    if model == "Dados incompletos"
                    else "",
                ]
            )
            rows.append(
                {
                    "period": period,
                    "competencia": competence,
                    "structure_model": model,
                    "model_order": order,
                    "is_monostructure": model == "Monoestrutura",
                    "funds": funds_count,
                    "pl_brl": pl_brl,
                    "fund_share_total": funds_count / total_funds if total_funds else float("nan"),
                    "pl_share_total": pl_brl / total_pl if total_pl else float("nan"),
                    "fund_share_known": funds_count / known_funds if known_funds and model != "Dados incompletos" else float("nan"),
                    "pl_share_known": pl_brl / known_pl if known_pl and model != "Dados incompletos" else float("nan"),
                    "provider_fund_coverage": known_funds / total_funds if total_funds else float("nan"),
                    "provider_pl_coverage": known_pl / total_pl if total_pl else float("nan"),
                    "provider_reference_kind": (
                        "reconstrução indicativa com cadastro vigente"
                        if historical_registry_proxy
                        else "fotografia vigente"
                    ),
                    "historical_registry_proxy": historical_registry_proxy,
                    "requires_warning": bool(historical_registry_proxy or warning),
                    "warning": warning,
                }
            )
    return pd.DataFrame(rows).sort_values(["competencia", "model_order"]).reset_index(drop=True)


def build_provider_rankings(
    funds: pd.DataFrame,
    competences: ExecutiveCompetences,
) -> pd.DataFrame:
    """Rank canonical providers by ANBIMA type and focus for each selected period."""

    selected = funds[funds["competencia"].isin(competences.ordered)].copy()
    selected["pl"] = pd.to_numeric(selected["pl"], errors="coerce")
    rows: list[dict[str, object]] = []
    for competence, period in _period_rows(competences):
        period_frame = selected[selected["competencia"].eq(competence)]
        for role, column in ROLE_COLUMNS.items():
            role_frame = period_frame.copy()
            role_frame["participant"] = role_frame.get(column, pd.Series("", index=role_frame.index)).map(
                canonical_provider
            )
            scopes: list[tuple[str, str, str, pd.DataFrame]] = []
            for anbima_type, type_frame in role_frame.groupby("anbima_tipo", dropna=False):
                scopes.append(("tipo", str(anbima_type), "Todos", type_frame))
                if anbima_type in ANBIMA_TYPES:
                    for focus, focus_frame in type_frame.groupby("anbima_foco", dropna=False):
                        if focus != ANBIMA_ND:
                            scopes.append(("foco", str(anbima_type), str(focus), focus_frame))
            for scope, anbima_type, focus, frame in scopes:
                total_pl = float(frame["pl"].sum(min_count=1)) if frame["pl"].notna().any() else 0.0
                total_funds = int(frame["fund_key"].nunique())
                known = frame[frame["participant"].ne("Não informado")]
                known_pl = float(known["pl"].sum(min_count=1)) if known["pl"].notna().any() else 0.0
                grouped = (
                    known.groupby("participant", as_index=False)
                    .agg(pl_brl=("pl", lambda values: values.sum(min_count=1)), funds=("fund_key", "nunique"))
                    .sort_values(["pl_brl", "participant"], ascending=[False, True])
                    .reset_index(drop=True)
                )
                proxy_pl = float(
                    frame.loc[frame["classification_tier"].eq("proxy_cvm"), "pl"].sum(min_count=1)
                ) if frame.loc[frame["classification_tier"].eq("proxy_cvm"), "pl"].notna().any() else 0.0
                historical_registry_proxy = competence != competences.latest_complete
                for rank, item in enumerate(grouped.itertuples(index=False), start=1):
                    rows.append(
                        {
                            "period": period,
                            "competencia": competence,
                            "role": role,
                            "scope": scope,
                            "anbima_tipo": anbima_type,
                            "anbima_foco": focus,
                            "participant": item.participant,
                            "pl_brl": float(item.pl_brl),
                            "funds": int(item.funds),
                            "share_pl": float(item.pl_brl) / total_pl if total_pl else float("nan"),
                            "share_funds": int(item.funds) / total_funds if total_funds else float("nan"),
                            "rank": rank,
                            "role_pl_coverage": known_pl / total_pl if total_pl else float("nan"),
                            "proxy_pl_share": proxy_pl / total_pl if total_pl else float("nan"),
                            "provider_reference_kind": (
                                "reconstrução indicativa com cadastro vigente"
                                if historical_registry_proxy and role in {"gestor", "custodiante"}
                                else "informe mensal histórico"
                                if role == "administrador"
                                else "fotografia vigente"
                            ),
                            "historical_registry_proxy": bool(
                                historical_registry_proxy and role in {"gestor", "custodiante"}
                            ),
                            "requires_warning": bool(
                                proxy_pl != 0
                                or known_pl != total_pl
                                or (historical_registry_proxy and role in {"gestor", "custodiante"})
                            ),
                            "warning": _join_warnings(
                                [
                                    "ranking inclui equivalência proxy CVM" if proxy_pl != 0 else "",
                                    "prestadores não informados foram excluídos do ranking" if known_pl != total_pl else "",
                                    "gestor/custodiante históricos usam o cadastro CVM vigente; tratar como reconstrução indicativa"
                                    if historical_registry_proxy and role in {"gestor", "custodiante"}
                                    else "",
                                ]
                            ),
                        }
                    )
    output = pd.DataFrame(rows)
    if output.empty:
        return output
    order = {competence: index for index, competence in enumerate(competences.ordered)}
    output["_period_order"] = output["competencia"].map(order)
    output = output.sort_values(
        ["role", "scope", "anbima_tipo", "anbima_foco", "participant", "_period_order"]
    )
    grouping = output.groupby(
        ["role", "scope", "anbima_tipo", "anbima_foco", "participant"], dropna=False
    )
    output["rank_change_vs_prior"] = grouping["rank"].shift(1) - output["rank"]
    output["share_change_pp_vs_prior"] = (output["share_pl"] - grouping["share_pl"].shift(1)) * 100.0
    return output.drop(columns="_period_order").reset_index(drop=True)


def build_coverage_summary(funds: pd.DataFrame, competences: ExecutiveCompetences) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for competence, period in _period_rows(competences):
        frame = funds[funds["competencia"].eq(competence)].copy()
        frame["pl"] = pd.to_numeric(frame["pl"], errors="coerce")
        total_pl = float(frame["pl"].sum(min_count=1)) if frame["pl"].notna().any() else 0.0
        non_fic = frame[frame["classification_tier"].ne("fic_separado")]
        non_fic_pl = (
            float(non_fic["pl"].sum(min_count=1)) if non_fic["pl"].notna().any() else 0.0
        )

        def pl_share(mask: pd.Series) -> float:
            value = float(frame.loc[mask, "pl"].sum(min_count=1)) if frame.loc[mask, "pl"].notna().any() else 0.0
            return value / total_pl if total_pl else float("nan")

        def non_fic_pl_share(tier: str) -> float:
            value = frame.loc[frame["classification_tier"].eq(tier), "pl"]
            numerator = float(value.sum(min_count=1)) if value.notna().any() else 0.0
            return numerator / non_fic_pl if non_fic_pl else float("nan")

        provider_known = pd.Series(True, index=frame.index)
        for column in ROLE_COLUMNS.values():
            provider_known &= frame.get(column, pd.Series("", index=frame.index)).map(canonical_provider).ne(
                "Não informado"
            )
        cotistas_known = pd.to_numeric(frame["cotistas"], errors="coerce").ge(0)
        rows.append(
            {
                "period": period,
                "competencia": competence,
                "funds": int(frame["fund_key"].nunique()),
                "pl_brl": total_pl,
                "anbima_scope_ex_fic_pl_brl": non_fic_pl,
                "valid_cnpj_fund_share": frame["cnpj_valid"].mean() if len(frame) else float("nan"),
                "official_anbima_classification_pl_share": pl_share(
                    frame["classification_tier"].eq("oficial_anbima")
                ),
                "published_evidence_classification_pl_share": pl_share(
                    frame["classification_tier"].eq("evidencia_publicada")
                ),
                "proxy_classification_pl_share": pl_share(frame["classification_tier"].eq("proxy_cvm")),
                "nd_classification_pl_share": pl_share(frame["classification_tier"].eq("nao_disponivel")),
                "official_anbima_ex_fic_pl_coverage": non_fic_pl_share("oficial_anbima"),
                "published_evidence_ex_fic_pl_coverage": non_fic_pl_share("evidencia_publicada"),
                "proxy_ex_fic_pl_share": non_fic_pl_share("proxy_cvm"),
                "nd_ex_fic_pl_share": non_fic_pl_share("nao_disponivel"),
                "fic_pl_share": pl_share(frame["classification_tier"].eq("fic_separado")),
                "all_provider_fund_coverage": provider_known.mean() if len(frame) else float("nan"),
                "all_provider_pl_coverage": pl_share(provider_known),
                "cotistas_fund_coverage": cotistas_known.mean() if len(frame) else float("nan"),
                "cotistas_pl_coverage": pl_share(cotistas_known),
                "funds_with_aggregation_warning": int(frame["aggregation_warning"].ne("").sum()),
            }
        )
    return pd.DataFrame(rows)


def build_industry_executive_pack(
    *,
    vehicle_monthly: pd.DataFrame,
    competence_status: pd.DataFrame,
    industry_monthly: pd.DataFrame | None = None,
    anbima_classification: pd.DataFrame | None = None,
    published_classifications: pd.DataFrame | None = None,
    holder_min_pl_brl: float = 200_000_000.0,
    outros_limit: int = 20,
) -> IndustryExecutivePack:
    """Build the full analytical pack without performing I/O or presentation work."""

    competences = select_executive_competences(competence_status)
    selected_vehicle = vehicle_monthly.copy()
    selected_vehicle["_competencia_key"] = selected_vehicle["competencia"].map(_competence_key)
    selected_vehicle = selected_vehicle[
        selected_vehicle["_competencia_key"].isin(competences.ordered)
    ].drop(columns="_competencia_key")
    aggregated = aggregate_vehicle_monthly_by_fund(selected_vehicle)
    missing_selected = set(competences.ordered).difference(set(aggregated.get("competencia", [])))
    if missing_selected:
        raise ValueError("vehicle_monthly sem competências selecionadas: " + ", ".join(sorted(missing_selected)))
    funds = apply_anbima_classification(
        aggregated,
        anbima_classification=anbima_classification,
        published_classifications=published_classifications,
    )
    annual_pl = build_annual_pl(funds, competences, competence_status, industry_monthly)
    market_share = build_market_share(funds, competences)
    top_outros, curation = build_outros_and_curation(
        funds, competences.latest_complete, limit=outros_limit
    )
    holder_histogram, holder_coverage = build_holder_histograms(
        funds, competences.latest_complete, min_pl_brl=holder_min_pl_brl
    )
    monostructure = build_monostructure_history(funds, competences)
    rankings = build_provider_rankings(funds, competences)
    coverage = build_coverage_summary(funds, competences)
    source_conflicts = funds[
        funds["tab4_duplicate_detected"].fillna(False).astype(bool)
    ][
        [
            "competencia",
            "cnpj_fundo",
            "cnpj_classe",
            "denominacao",
            "pl",
            "tab4_type_conflict",
            "tab4_pl_conflict",
            "tab4_duplicate_rows_dropped",
            "tab4_warning",
            "aggregation_warning",
        ]
    ].copy()

    warnings: list[str] = []
    if competences.excluded_tail:
        warnings.append(
            "Competências posteriores à última completa foram excluídas: "
            + ", ".join(competences.excluded_tail)
        )
    if annual_pl["warning"].ne("").any():
        warnings.extend(annual_pl.loc[annual_pl["warning"].ne(""), "warning"].astype(str).tolist())
    latest_coverage = coverage[coverage["competencia"].eq(competences.latest_complete)]
    latest_funds = funds[funds["competencia"].eq(competences.latest_complete)]
    if latest_funds["classification_warning"].astype(str).str.contains(
        "classificação ANBIMA cadastral", case=False, na=False
    ).any():
        warnings.append(
            "Tipo/foco ANBIMA usam a fotografia cadastral pública de dez/25 como ponte estática"
        )
    if not latest_coverage.empty:
        row = latest_coverage.iloc[0]
        if float(row["proxy_classification_pl_share"] or 0) > 0:
            warnings.append("Market share ANBIMA contém proxy CVM explicitamente sinalizado")
        if float(row["nd_classification_pl_share"] or 0) > 0:
            warnings.append("Parte do PL permanece N/D e não foi convertida em Outros")
        if float(row["all_provider_pl_coverage"] or 0) < 1:
            warnings.append("Monoestrutura exclui inferência quando algum prestador não está informado")
    if int(holder_coverage.iloc[0]["funds_excluded_missing_cotistas"]) > 0:
        warnings.append("Histograma exclui fundos sem número de cotistas válido; cobertura foi preservada")
    warnings.append(
        "Monoestrutura de 2024/2025 é reconstrução indicativa: administrador é mensal, "
        "mas gestor e custodiante vêm do cadastro CVM vigente"
    )

    return IndustryExecutivePack(
        competences=competences,
        fund_monthly=funds,
        annual_pl=annual_pl,
        market_share=market_share,
        top_20_outros=top_outros,
        curation_queue=curation,
        holder_histogram=holder_histogram,
        holder_coverage=holder_coverage,
        monostructure_history=monostructure,
        rankings=rankings,
        coverage=coverage,
        source_conflicts=source_conflicts.reset_index(drop=True),
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = [
    "ANBIMA_CLASSIFICATION_VALUES",
    "ANBIMA_FIC",
    "ANBIMA_FOCUS_BY_TYPE",
    "ANBIMA_ND",
    "ANBIMA_TYPES",
    "ExecutiveCompetences",
    "HOLDER_BUCKETS",
    "IndustryExecutivePack",
    "STRUCTURE_MODELS",
    "aggregate_vehicle_monthly_by_fund",
    "apply_anbima_classification",
    "build_annual_pl",
    "build_coverage_summary",
    "build_holder_histograms",
    "build_industry_executive_pack",
    "build_market_share",
    "build_monostructure_history",
    "build_outros_and_curation",
    "build_provider_rankings",
    "select_executive_competences",
]
