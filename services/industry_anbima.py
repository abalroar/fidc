"""Curated ANBIMA type/focus mapping for the FIDC industry study.

The public ANBIMA workbook contains repeated rows for some classes.  This
module turns that workbook into a deterministic, one-row-per-class mapping
without treating CVM portfolio segments as formal ANBIMA classifications.
"""

from __future__ import annotations

from collections.abc import Iterable
import re
import unicodedata

import pandas as pd


ANBIMA_TYPES: tuple[str, ...] = (
    "Fomento Mercantil",
    "Agro, Indústria e Comércio",
    "Financeiro",
    "Outros",
)

ANBIMA_FOCUS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "Fomento Mercantil": ("Fomento Mercantil",),
    "Financeiro": (
        "Crédito Imobiliário",
        "Crédito Consignado",
        "Crédito Pessoal",
        "Financiamento de Veículos",
        "Multicarteira Financeiro",
    ),
    "Agro, Indústria e Comércio": (
        "Infraestrutura",
        "Recebíveis Comerciais",
        "Crédito Corporativo",
        "Agronegócio",
        "Multicarteira Agro, Indústria e Comércio",
    ),
    "Outros": (
        "Recuperação",
        "Poder Público",
        "Multicarteira Outros",
    ),
}

PUBLIC_WORKBOOK_COLUMNS: tuple[str, ...] = (
    "Código ANBIMA",
    "Estrutura",
    "Nome Comercial",
    "CNPJ da Classe",
    "CNPJ do Fundo",
    "Status",
    "Data de Início de Atividade",
    "Quantidade de Subclasses",
    "Categoria ANBIMA",
    "Tipo ANBIMA",
    "Composição do Fundo",
    "Aberto Estatutariamente",
    "Fundo ESG",
    "Tributação Alvo",
    "Administrador",
    "Gestor Principal",
    "Primeiro Aporte",
    "Tipo de Investidor",
    "Característica do Investidor",
    "Cota de Abertura",
    "Aplicação Inicial Mínima",
    "Prazo Pagamento Resgate em dias",
    "Adptado 175",
    "Código CVM Subclasse",
    "foco_atuacao",
    "nivel_1_categoria",
    "nivel_2_categoria",
    "nivel_3_subcategoria",
)


def _digits(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(14)[-14:] if digits else ""


def _ascii_upper(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.upper()).strip()


_TYPE_ALIASES = {
    _ascii_upper(value): value for value in ANBIMA_TYPES
}

_FOCUS_ALIASES = {
    _ascii_upper(value): value
    for values in ANBIMA_FOCUS_BY_TYPE.values()
    for value in values
}
_FOCUS_ALIASES.update(
    {
        "MULTICARTEIRAS OUTROS": "Multicarteira Outros",
        "MULTICARTEIRA OUTRO": "Multicarteira Outros",
        "MULTICARTEIRAS AGRO, INDUSTRIA E COMERCIO": "Multicarteira Agro, Indústria e Comércio",
        "MULTICARTEIRA AGRO, INDUSTRIA E COMERCIO": "Multicarteira Agro, Indústria e Comércio",
    }
)


def normalize_anbima_type(value: object) -> str:
    """Return the canonical FIDC type, or an empty string for invalid input."""

    return _TYPE_ALIASES.get(_ascii_upper(value), "")


def normalize_anbima_focus(value: object) -> str:
    """Return the canonical ANBIMA focus, or an empty string when unavailable."""

    normalized = _ascii_upper(value)
    if normalized in {"", "NAN", "NONE", "NAO SE APLICA", "N/D", "ND"}:
        return ""
    return _FOCUS_ALIASES.get(normalized, "")


def valid_type_focus_pair(anbima_type: object, focus: object) -> bool:
    normalized_type = normalize_anbima_type(anbima_type)
    normalized_focus = normalize_anbima_focus(focus)
    return bool(
        normalized_type
        and (not normalized_focus or normalized_focus in ANBIMA_FOCUS_BY_TYPE[normalized_type])
    )


def _unique_nonempty(values: Iterable[object]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def build_public_anbima_fidc_mapping(workbook: pd.DataFrame) -> pd.DataFrame:
    """Collapse the public ANBIMA 175 workbook to one deterministic class row.

    Active records take precedence when a CNPJ also has closed records.  A
    conflicting type or focus is never resolved silently: the canonical value
    is left blank and ``mapping_status`` records the conflict.
    """

    missing = sorted(set(PUBLIC_WORKBOOK_COLUMNS).difference(workbook.columns))
    if missing:
        raise ValueError(f"Planilha ANBIMA sem colunas obrigatórias: {', '.join(missing)}")

    frame = workbook.copy()
    frame = frame[frame["Categoria ANBIMA"].astype(str).str.strip().str.upper().eq("FIDC")]
    frame["cnpj_classe"] = frame["CNPJ da Classe"].map(_digits)
    frame["cnpj_fundo"] = frame["CNPJ do Fundo"].map(_digits)
    frame = frame[frame["cnpj_classe"].str.len().eq(14)].copy()
    frame["tipo_canonico"] = frame["Tipo ANBIMA"].map(normalize_anbima_type)
    frame["foco_canonico"] = frame["foco_atuacao"].map(normalize_anbima_focus)
    frame["ativo"] = frame["Status"].astype(str).str.strip().str.upper().eq("ATIVO")
    frame["data_inicio"] = pd.to_datetime(frame["Data de Início de Atividade"], errors="coerce")

    rows: list[dict[str, object]] = []
    for cnpj_classe, group in frame.groupby("cnpj_classe", sort=True):
        preferred = group[group["ativo"]]
        if preferred.empty:
            preferred = group
        type_values = _unique_nonempty(preferred["tipo_canonico"])
        focus_values = _unique_nonempty(preferred["foco_canonico"])
        raw_type_values = _unique_nonempty(preferred["Tipo ANBIMA"].fillna(""))
        raw_focus_values = _unique_nonempty(preferred["foco_atuacao"].fillna(""))

        status = "publicada"
        if len(type_values) != 1:
            status = "conflito_tipo" if len(type_values) > 1 else "tipo_invalido"
        elif len(focus_values) > 1:
            status = "conflito_foco"
        elif focus_values and focus_values[0] not in ANBIMA_FOCUS_BY_TYPE[type_values[0]]:
            status = "conflito_tipo_foco"

        representative = preferred.sort_values(
            ["data_inicio", "Código ANBIMA"], ascending=[False, True], na_position="last"
        ).iloc[0]
        type_value = type_values[0] if status == "publicada" else ""
        focus_value = focus_values[0] if status == "publicada" and focus_values else ""
        rows.append(
            {
                "codigo_anbima": str(representative.get("Código ANBIMA") or "").strip(),
                "cnpj_classe": cnpj_classe,
                "cnpj_fundo": representative["cnpj_fundo"] or cnpj_classe,
                "nome_comercial": str(representative.get("Nome Comercial") or "").strip(),
                "status_anbima": "Ativo" if bool(preferred["ativo"].any()) else "Encerrado",
                "data_inicio_atividade": (
                    representative["data_inicio"].date().isoformat()
                    if pd.notna(representative["data_inicio"])
                    else ""
                ),
                "tipo_anbima": type_value,
                "foco_anbima": focus_value,
                "mapping_status": status,
                "raw_tipo_anbima": " | ".join(raw_type_values),
                "raw_foco_anbima": " | ".join(raw_focus_values),
                "administrador_anbima": str(representative.get("Administrador") or "").strip(),
                "gestor_anbima": str(representative.get("Gestor Principal") or "").strip(),
                "record_count": int(len(group)),
                "active_record_count": int(group["ativo"].sum()),
                "source_kind": "ANBIMA Data — Fundos 175: características público",
            }
        )

    output = pd.DataFrame(rows)
    if output.empty:
        return output
    if output["cnpj_classe"].duplicated().any():
        raise AssertionError("Mapeamento ANBIMA não ficou único por CNPJ de classe")
    return output.sort_values(["status_anbima", "nome_comercial", "cnpj_classe"]).reset_index(drop=True)
