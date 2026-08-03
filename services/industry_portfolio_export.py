"""Normalize Carteira 1 and flagship rows for a separate analytical workbook.

The module is intentionally independent from the revision bundle publisher.  It
consumes the curation and structural-risk frames already materialized by the
industry pipeline and returns typed, auditable tables that a workbook renderer
can write without reconstructing documentary rules.

Percentages are stored as fractions (``0.05`` means 5%).  Missing documentary
information remains missing: numeric gaps are ``NaN`` and textual gaps are
``N/D``.  A manual overlay may complement party and receivable fields, but it
never replaces an existing value and never splits an ambiguous
``Cedente/Originador`` label into inferred roles.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Mapping

import numpy as np
import pandas as pd

from services.industry_structural_risk import (
    _apply_financeiro_agro_risk_review,
    _load_financeiro_agro_risk_review,
)
from services.structural_risk import loss_until_trigger


TEXT_ND = "N/D"

MANUAL_ENRICHMENT_COLUMNS: tuple[str, ...] = (
    "cnpj",
    "cedente_originador_literal",
    "papel_literal",
    "originador",
    "cedente",
    "sacado_devedor",
    "tipo_recebivel_literal",
    "fonte_manual",
    "status_transcricao",
    "observacao",
)

MANUAL_CNPJ_RESOLUTION_COLUMNS: tuple[str, ...] = (
    "status_resolucao_cnpj",
    "quantidade_candidatos_cnpj",
    "candidatos_cnpj",
)

PARTY_COLUMNS: tuple[str, ...] = (
    "cedente_originador_literal",
    "papel_literal",
    "originador",
    "cedente",
    "sacado_devedor",
    "tipo_recebivel_literal",
)

PRICE_COLUMNS: tuple[str, ...] = (
    "preco_cota_brl",
    "preco_cota_display",
    "preco_cota_natureza",
    "preco_cota_classe_serie",
    "preco_cota_documento_data",
    "preco_cota_documento_id",
    "preco_cota_fonte",
    "preco_cota_status",
    "preco_cota_excecao_asterisco_flag",
)

NORMALIZED_COLUMNS: tuple[str, ...] = (
    "coorte",
    "ordem",
    "cnpj",
    "cnpj_numerico",
    "cnpj_formatado",
    "nome_oficial_cvm",
    "nome_referencia",
    "status_identidade",
    "data_ref",
    "pl_atual_brl",
    "pl_classes_reportadas_brl",
    "pl_subordinado_atual_brl",
    "sub_pl_atual",
    "status_sub_pl_atual",
    "minimo_junior_literal",
    "minimo_junior_calculado",
    "minimo_junior_ajustado",
    "suporte_total",
    "suporte_combinado_junior_mezanino",
    "minimo_estrutural_usado",
    "minimo_estrutural_display",
    "minimo_estrutural_natureza",
    "minimo_estrutural_formula",
    "comparavel_flag",
    "comparabilidade_motivo",
    "excecao_asterisco_flag",
    "folga_pp",
    "capacidade_ate_gatilho",
    "situacao_regulatoria",
    "mvp_slide_categoria",
    "mvp_slide_categoria_original",
    "mvp_slide_categoria_override_flag",
    "mvp_slide_categoria_fonte",
    "mvp_slide_categoria_motivo",
    "mvp_faixa_sub_atual",
    "mvp_elegivel_flag",
    "mvp_situacao_piso",
    "posicao_mercado",
    "excesso_vs_mercado",
    "benchmark_confiavel",
    "n_comparaveis_categoria",
    "tipo_exibicao",
    "foco_exibicao",
    "taxonomia_estrutural",
    "grupo_comparacao",
    "categoria_risco_atual",
    "categoria_risco_proposta",
    "subtipo_risco_diagnosticado",
    "reclassificacao_proposta_flag",
    "status_avaliacao_reclassificacao",
    "fundamento_avaliacao_reclassificacao",
    "fonte_avaliacao_reclassificacao",
    "middle_market_status",
    "middle_market_evidencia",
    "middle_market_porte_documentado_flag",
    "preco_cota_brl",
    "preco_cota_display",
    "preco_cota_natureza",
    "preco_cota_classe_serie",
    "preco_cota_documento_data",
    "preco_cota_documento_id",
    "preco_cota_fonte",
    "preco_cota_status",
    "preco_cota_excecao_asterisco_flag",
    "cedente_originador_literal",
    "papel_literal",
    "originador",
    "cedente",
    "sacado_devedor",
    "tipo_recebivel_literal",
    "fonte_partes_recebivel",
    "status_complemento_manual",
    "observacao_complemento_manual",
    "documento_id",
    "documento_data",
    "pagina_clausula",
    "status_curadoria_documental",
    "fonte_documental",
    "texto_minimo",
    "campos_nao_preenchidos",
    "status_preenchimento",
)

_MANUAL_ALIASES: Mapping[str, str] = {
    "cnpj_fundo": "cnpj",
    "fonte_imagem": "fonte_manual",
    "fonte": "fonte_manual",
    "sacado": "sacado_devedor",
    "devedor": "sacado_devedor",
    "tipo_recebivel": "tipo_recebivel_literal",
    "observacao_manual": "observacao",
}

_APPROVED_MANUAL_STATUSES = {
    "aprovado",
    "confirmado",
    "confirmado legivel",
    "confirmado pelo usuario",
    "manual confirmado",
    "validado",
}

_APPROVED_PRICE_STATUSES = {
    "aceito payload",
    "encontrado explicito",
}

_PRICE_SOURCE_PRIORITY: Mapping[str, int] = {
    "rating_report": 10,
    "regulamento": 20,
    "emissao": 25,
    "assembleia": 30,
    "informe_mensal": 40,
    "payload_documental": 50,
    "planilha_manual": 60,
    "candidate_extraction": 90,
}

_PORTFOLIO_PRICE_ALIASES: Mapping[str, tuple[str, ...]] = {
    "preco_cota_brl": (
        "preco_cota_brl",
        "preco_emissao_brl",
        "vnu_brl",
    ),
    "preco_cota_display": (
        "preco_cota_display",
        "preco_emissao_display",
        "vnu_display",
    ),
    "preco_cota_natureza": (
        "preco_cota_natureza",
        "preco_emissao_natureza",
        "vnu_natureza",
    ),
    "preco_cota_classe_serie": (
        "preco_cota_classe_serie",
        "preco_emissao_classe",
        "cota_classe_serie",
        "cota_classe",
    ),
    "preco_cota_documento_data": (
        "preco_cota_documento_data",
        "preco_emissao_data",
        "preco_cota_data",
    ),
    "preco_cota_documento_id": (
        "preco_cota_documento_id",
        "preco_emissao_documento_id",
        "preco_cota_source_id",
    ),
    "preco_cota_fonte": (
        "preco_cota_fonte",
        "preco_emissao_fonte",
        "preco_cota_source_url",
        "vnu_fonte",
    ),
    "preco_cota_status": (
        "preco_cota_status",
        "preco_emissao_status",
    ),
    "preco_cota_excecao_asterisco_flag": (
        "preco_cota_excecao_asterisco_flag",
        "preco_emissao_excecao_asterisco_flag",
    ),
}

_FLAGSHIP_PRICE_ALIASES: Mapping[str, tuple[str, ...]] = {
    **_PORTFOLIO_PRICE_ALIASES,
    "preco_cota_brl": ("preco_emissao_brl", "preco_cota_brl"),
    "preco_cota_display": (
        "preco_emissao_display",
        "preco_cota_display",
    ),
    "preco_cota_natureza": (
        "preco_emissao_natureza",
        "preco_cota_natureza",
    ),
    "preco_cota_classe_serie": (
        "preco_emissao_classe",
        "preco_cota_classe_serie",
    ),
    "preco_cota_documento_data": (
        "preco_emissao_data",
        "preco_cota_documento_data",
    ),
    "preco_cota_documento_id": (
        "preco_emissao_documento_id",
        "preco_cota_documento_id",
    ),
    "preco_cota_fonte": (
        "preco_emissao_fonte",
        "preco_cota_fonte",
    ),
    "preco_cota_status": (
        "preco_emissao_status",
        "preco_cota_status",
    ),
    "preco_cota_excecao_asterisco_flag": (
        "preco_emissao_excecao_asterisco_flag",
        "preco_cota_excecao_asterisco_flag",
    ),
}


@dataclass(frozen=True)
class IndustryPortfolioExportResult:
    """Tables needed by the standalone Carteira 1/flagships workbook."""

    carteira: pd.DataFrame
    flagships: pd.DataFrame
    coverage: pd.DataFrame
    gaps: pd.DataFrame
    manual: pd.DataFrame
    dictionary: pd.DataFrame
    prices: pd.DataFrame


def _series(frame: pd.DataFrame, column: str, default: object = None) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series(default, index=frame.index, dtype="object")


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(_series(frame, column), errors="coerce")


def _bool_series(frame: pd.DataFrame, column: str) -> pd.Series:
    values = _series(frame, column, False)
    return values.map(
        lambda value: value
        if isinstance(value, (bool, np.bool_))
        else str(value).strip().lower() in {"1", "true", "sim", "yes"}
    ).fillna(False).astype(bool)


def _is_missing_text(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (float, np.floating)) and pd.isna(value):
        return True
    text = str(value).strip()
    return not text or text.upper().startswith("N/D") or text.lower() == "nan"


def _text(value: object, *, default: str = TEXT_ND) -> str:
    return default if _is_missing_text(value) else str(value).strip()


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    unaccented = "".join(
        char for char in text if not unicodedata.combining(char)
    ).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", unaccented).split())


def _coalesce_text(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    result = pd.Series(TEXT_ND, index=frame.index, dtype="object")
    for column in columns:
        if column not in frame.columns:
            continue
        values = frame[column].map(_text)
        result = result.where(~result.map(_is_missing_text), values)
    return result


def _coalesce_numeric(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    result = pd.Series(np.nan, index=frame.index, dtype="float64")
    for column in columns:
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        result = result.where(result.notna(), values)
    return result


def _price_fields(
    frame: pd.DataFrame,
    aliases: Mapping[str, tuple[str, ...]],
) -> pd.DataFrame:
    price = pd.DataFrame(index=frame.index)
    price["preco_cota_brl"] = _coalesce_numeric(
        frame, aliases["preco_cota_brl"]
    )
    for column in (
        "preco_cota_display",
        "preco_cota_natureza",
        "preco_cota_classe_serie",
        "preco_cota_documento_data",
        "preco_cota_documento_id",
        "preco_cota_fonte",
        "preco_cota_status",
    ):
        price[column] = _coalesce_text(frame, aliases[column])

    has_price = price["preco_cota_brl"].notna() | ~price[
        "preco_cota_display"
    ].map(_is_missing_text)
    nature_missing = price["preco_cota_natureza"].map(_is_missing_text)
    price.loc[nature_missing & has_price, "preco_cota_natureza"] = (
        "preço/VNU conforme fonte"
    )
    document_id_missing = price["preco_cota_documento_id"].map(_is_missing_text)
    parsed_document_ids = price["preco_cota_fonte"].map(
        _document_ids_from_source
    )
    price.loc[
        document_id_missing & parsed_document_ids.ne(TEXT_ND),
        "preco_cota_documento_id",
    ] = parsed_document_ids
    status_missing = price["preco_cota_status"].map(_is_missing_text)
    price.loc[status_missing & has_price, "preco_cota_status"] = (
        "localizado documentalmente"
    )
    price.loc[status_missing & ~has_price, "preco_cota_status"] = "não localizado"
    exception = pd.Series(False, index=frame.index, dtype="bool")
    for column in aliases["preco_cota_excecao_asterisco_flag"]:
        if column in frame.columns:
            exception = _bool_series(frame, column)
            break
    multiple_readings = price["preco_cota_display"].astype(str).str.contains(
        r"\s[/|]\s", regex=True, na=False
    )
    price["preco_cota_excecao_asterisco_flag"] = (
        exception | (nature_missing & has_price) | multiple_readings
    )
    return price


def _document_ids_from_source(value: object) -> str:
    if _is_missing_text(value):
        return TEXT_ND
    identifiers = re.findall(r"(?<!\d)(\d{6,7})(?!\d)", str(value))
    return " | ".join(dict.fromkeys(identifiers)) or TEXT_ND


def _comparison_group_from_portfolio(row: pd.Series) -> str:
    """Apply the comparison taxonomy already used by flagship curation."""

    reference = _fold(row.get("familia_flagship_referencia"))
    if reference.startswith("adquirencia"):
        return "Adquirência"
    if reference == "consignado inss":
        return "Consignado INSS"
    if reference == "consignado fgts":
        return "Consignado FGTS"
    if reference == "veiculos":
        return "Veículos"
    if reference == "factoring":
        return "Factoring"
    displayed_type = _fold(row.get("tipo_exibicao"))
    if displayed_type == "fomento mercantil":
        return "Factoring"
    if displayed_type == "agro industria e comercio":
        return "Agro / Revenda"
    if displayed_type == "financeiro":
        return "Financeiro"
    return TEXT_ND


def _comparison_group_from_flagship(row: pd.Series) -> str:
    """Apply the comparison taxonomy already used by flagship curation."""

    category = _fold(row.get("categoria"))
    if category.startswith("adquirencia"):
        return "Adquirência"
    if category == "consignado inss":
        return "Consignado INSS"
    if category == "consignado fgts":
        return "Consignado FGTS"
    if category == "veiculos":
        return "Veículos"
    if category == "factoring":
        return "Factoring"
    return "Financeiro"


def _parse_brl(value: object) -> float | None:
    if value is None or (isinstance(value, (float, np.floating)) and pd.isna(value)):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        return number if np.isfinite(number) else None
    raw = str(value).strip()
    match = re.search(r"(?:R\$\s*)?([0-9][0-9.\s]*(?:,[0-9]+)?)", raw)
    if not match:
        return None
    normalized = match.group(1).replace(" ", "").replace(".", "").replace(",", ".")
    try:
        number = float(normalized)
    except ValueError:
        return None
    return number if np.isfinite(number) else None


def _price_nature(excerpt: object) -> tuple[str, bool]:
    folded = _fold(excerpt)
    if "valor nominal unitario" in folded:
        return "valor nominal unitário (VNU)", False
    if "preco de integralizacao" in folded:
        return "preço unitário de integralização", False
    if "preco de subscricao" in folded:
        return "preço unitário de subscrição", False
    if (
        "preco de emissao" in folded
        or "valor unitario de emissao" in folded
    ):
        return "preço/valor unitário de emissão", False
    return "preço unitário conforme fonte", True


def _unique_text(values: pd.Series) -> list[str]:
    return list(
        dict.fromkeys(
            _text(value)
            for value in values
            if not _is_missing_text(value)
        )
    )


def _parse_document_date(value: object) -> object:
    """Parse supported documentary dates without locale-dependent ambiguity."""

    text = _text(value)
    if _is_missing_text(text):
        return pd.NaT
    for date_format in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
    ):
        try:
            return pd.Timestamp(datetime.strptime(text, date_format))
        except ValueError:
            continue
    iso_candidate = text.replace("Z", "+00:00")
    try:
        return pd.Timestamp(datetime.fromisoformat(iso_candidate)).tz_localize(None)
    except (TypeError, ValueError):
        return pd.NaT


def _aggregate_price_evidence(
    evidence: pd.DataFrame | None,
) -> pd.DataFrame:
    columns = ["cnpj", *PRICE_COLUMNS]
    if evidence is None or evidence.empty:
        return pd.DataFrame(columns=columns)
    if "cnpj" not in evidence.columns:
        raise KeyError("evidência de preço sem coluna cnpj")

    source = evidence.copy().reset_index(drop=True)
    source["cnpj"] = source["cnpj"].map(_cnpj_digits)
    source["_approved"] = _series(source, "status").map(
        lambda value: _fold(value) in _APPROVED_PRICE_STATUSES
    )
    output: list[dict[str, object]] = []
    for cnpj, group in source.groupby("cnpj", sort=False):
        accepted = group[group["_approved"]].copy()
        if accepted.empty:
            output.append(
                {
                    "cnpj": cnpj,
                    "preco_cota_brl": np.nan,
                    "preco_cota_display": TEXT_ND,
                    "preco_cota_natureza": TEXT_ND,
                    "preco_cota_classe_serie": TEXT_ND,
                    "preco_cota_documento_data": TEXT_ND,
                    "preco_cota_documento_id": TEXT_ND,
                    "preco_cota_fonte": TEXT_ND,
                    "preco_cota_status": "pendente de revisão documental",
                    "preco_cota_excecao_asterisco_flag": True,
                }
            )
            continue

        accepted["_source_priority"] = _series(
            accepted, "source_kind"
        ).map(lambda value: _PRICE_SOURCE_PRIORITY.get(str(value), 80))
        accepted = accepted[
            accepted["_source_priority"].eq(accepted["_source_priority"].min())
        ].copy()
        accepted["_document_date_parsed"] = _series(
            accepted, "document_date"
        ).map(_parse_document_date)
        if accepted["_document_date_parsed"].notna().any():
            latest_date = accepted["_document_date_parsed"].max()
            accepted = accepted[
                accepted["_document_date_parsed"].eq(latest_date)
            ].copy()

        pairs: list[tuple[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
        numeric_values: set[float] = set()
        for row in accepted.itertuples(index=False):
            row_values = row._asdict()
            class_series = _text(row_values.get("class_series"))
            display = _text(row_values.get("price_display"))
            pair = (class_series, display)
            if not _is_missing_text(display) and pair not in seen_pairs:
                pairs.append(pair)
                seen_pairs.add(pair)
            parsed = _parse_brl(display)
            if parsed is not None:
                numeric_values.add(parsed)
        displays = [
            f"{class_series}: {display}"
            if not _is_missing_text(class_series)
            else display
            for class_series, display in pairs
        ]
        classes = list(
            dict.fromkeys(
                class_series
                for class_series, _ in pairs
                if not _is_missing_text(class_series)
            )
        )
        class_exception = any(
            _is_missing_text(class_series) for class_series, _ in pairs
        )
        nature_rows = [
            _price_nature(value)
            for value in _series(accepted, "excerpt")
        ]
        natures = list(dict.fromkeys(value for value, _ in nature_rows))
        nature_exception = any(exception for _, exception in nature_rows)
        source_values = _unique_text(
            _coalesce_text(
                accepted,
                ("source_url", "source_path", "source_kind"),
            )
        )
        output.append(
            {
                "cnpj": cnpj,
                "preco_cota_brl": (
                    next(iter(numeric_values))
                    if len(numeric_values) == 1
                    else np.nan
                ),
                "preco_cota_display": " | ".join(displays) or TEXT_ND,
                "preco_cota_natureza": " | ".join(natures) or TEXT_ND,
                "preco_cota_classe_serie": " | ".join(classes) or TEXT_ND,
                "preco_cota_documento_data": " | ".join(
                    _unique_text(_series(accepted, "document_date"))
                )
                or TEXT_ND,
                "preco_cota_documento_id": " | ".join(
                    _unique_text(_series(accepted, "source_id"))
                )
                or TEXT_ND,
                "preco_cota_fonte": " | ".join(source_values) or TEXT_ND,
                "preco_cota_status": (
                    "localizado documentalmente — múltiplos valores/classes"
                    if len(pairs) > 1
                    else "localizado documentalmente"
                ),
                "preco_cota_excecao_asterisco_flag": (
                    len(pairs) > 1 or nature_exception or class_exception
                ),
            }
        )
    return pd.DataFrame(output, columns=columns)


def _price_evidence_table(evidence: pd.DataFrame | None) -> pd.DataFrame:
    base_columns = [
        "coorte",
        "cnpj",
        "class_series",
        "price_display",
        "price_brl",
        "price_nature",
        "excecao_asterisco_flag",
        "source_kind",
        "source_id",
        "document_class",
        "document_date",
        "source_path",
        "source_url",
        "page",
        "status",
        "aprovado_para_export_flag",
        "excerpt",
    ]
    if evidence is None or evidence.empty:
        return pd.DataFrame(columns=base_columns)
    if "cnpj" not in evidence.columns:
        raise KeyError("evidência de preço sem coluna cnpj")
    result = evidence.copy().reset_index(drop=True)
    result["cnpj"] = result["cnpj"].map(_cnpj_digits)
    result.insert(0, "coorte", "Carteira 101")
    result["price_brl"] = _series(result, "price_display").map(_parse_brl)
    nature = _series(result, "excerpt").map(_price_nature)
    result["price_nature"] = nature.map(lambda value: value[0])
    raw_exception = _series(result, "exception_flag").map(
        lambda value: (
            not _is_missing_text(value)
            and _fold(value) not in {"0", "false", "nao", "não"}
        )
    )
    class_exception = _series(result, "class_series").map(_is_missing_text)
    result["excecao_asterisco_flag"] = (
        nature.map(lambda value: value[1]) | raw_exception | class_exception
    )
    result["aprovado_para_export_flag"] = _series(result, "status").map(
        lambda value: _fold(value) in _APPROVED_PRICE_STATUSES
    )
    for column in base_columns:
        if column not in result.columns:
            result[column] = np.nan if column == "price_brl" else TEXT_ND
    return result.loc[:, base_columns]


def _apply_price_evidence(
    rows: pd.DataFrame,
    evidence: pd.DataFrame | None,
) -> pd.DataFrame:
    if rows.empty:
        return rows
    aggregated = _aggregate_price_evidence(evidence)
    if aggregated.empty:
        return rows
    output = rows.copy()
    for _, price in aggregated.iterrows():
        mask = output["cnpj"].eq(price["cnpj"])
        if not mask.any():
            continue
        existing = output.loc[mask, "preco_cota_brl"].notna() | ~output.loc[
            mask, "preco_cota_display"
        ].map(_is_missing_text)
        if existing.any():
            continue
        for column in PRICE_COLUMNS:
            output.loc[mask, column] = price[column]
    return output


def _apply_document_audit(
    rows: pd.DataFrame,
    audit: pd.DataFrame | None,
) -> pd.DataFrame:
    """Fill documentary party gaps from the per-CNPJ scan without replacing data."""

    if rows.empty or audit is None or audit.empty:
        return rows
    if "cnpj" not in audit.columns:
        raise KeyError("auditoria documental sem coluna cnpj")
    source = audit.copy().reset_index(drop=True)
    source["cnpj"] = source["cnpj"].map(_cnpj_digits)
    duplicated = source.loc[source["cnpj"].duplicated(keep=False), "cnpj"].unique()
    if len(duplicated):
        raise ValueError(
            "auditoria documental contém CNPJ duplicado: "
            f"{duplicated.tolist()}"
        )

    output = rows.copy()
    field_map = {
        "originador": "originador",
        "cedente": "cedente",
        "sacado_devedor": "sacado_devedor",
        "tipo_recebivel": "tipo_recebivel_literal",
    }
    for _, audited in source.iterrows():
        mask = output["cnpj"].eq(audited["cnpj"])
        if not mask.any():
            continue
        applied_sources: list[str] = []
        for audit_field, output_field in field_map.items():
            value = audited.get(audit_field)
            status = _fold(audited.get(f"{audit_field}_status"))
            if (
                _is_missing_text(value)
                or status not in _APPROVED_PRICE_STATUSES
                or not output.loc[mask, output_field].map(_is_missing_text).any()
            ):
                continue
            output.loc[
                mask & output[output_field].map(_is_missing_text), output_field
            ] = _text(value)
            source_value = next(
                (
                    _text(audited.get(column))
                    for column in (
                        f"{audit_field}_link",
                        f"{audit_field}_fonte",
                    )
                    if not _is_missing_text(audited.get(column))
                ),
                TEXT_ND,
            )
            if not _is_missing_text(source_value):
                applied_sources.append(f"{audit_field}: {source_value}")
        if applied_sources:
            output.loc[
                mask & output["fonte_partes_recebivel"].map(_is_missing_text),
                "fonte_partes_recebivel",
            ] = " | ".join(dict.fromkeys(applied_sources))
    return output


def _cnpj_digits(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("CNPJ ausente")
    if isinstance(value, (int, np.integer)):
        digits = str(int(value))
    elif isinstance(value, (float, np.floating)) and np.isfinite(value):
        if not float(value).is_integer():
            raise ValueError(f"CNPJ numérico não inteiro: {value!r}")
        digits = str(int(value))
    else:
        raw = str(value).strip()
        if re.fullmatch(r"[0-9]+(?:\.0+)?[eE][+-]?[0-9]+", raw):
            try:
                decimal = Decimal(raw)
            except InvalidOperation as exc:
                raise ValueError(f"CNPJ inválido: {value!r}") from exc
            if decimal != decimal.to_integral_value():
                raise ValueError(f"CNPJ numérico não inteiro: {value!r}")
            digits = str(int(decimal))
        else:
            digits = re.sub(r"\D", "", raw)
    if not digits or len(digits) > 14:
        raise ValueError(f"CNPJ deve ter até 14 dígitos: {value!r}")
    return digits.zfill(14)


def _format_cnpj(value: object) -> str:
    digits = _cnpj_digits(value)
    return (
        f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/"
        f"{digits[8:12]}-{digits[12:]}"
    )


def _validate_cnpj_frame(
    frame: pd.DataFrame,
    *,
    column: str,
    label: str,
) -> pd.Series:
    if column not in frame.columns:
        raise KeyError(f"{label} sem coluna de CNPJ: {column}")
    cnpj = frame[column].map(_cnpj_digits)
    duplicated = cnpj[cnpj.duplicated(keep=False)].unique().tolist()
    if duplicated:
        raise ValueError(f"{label} contém CNPJ duplicado: {duplicated}")
    return cnpj


def _fraction_from_percent_points(frame: pd.DataFrame, column: str) -> pd.Series:
    return _numeric(frame, column) / 100.0


def _documentary_parties(frame: pd.DataFrame) -> pd.DataFrame:
    parties = pd.DataFrame(index=frame.index)
    for column in PARTY_COLUMNS:
        parties[column] = _series(frame, column).map(_text)
    parties["fonte_partes_recebivel"] = _series(
        frame, "fonte_partes_recebivel"
    ).map(_text)
    parties["status_complemento_manual"] = "sem_overlay"
    parties["observacao_complemento_manual"] = TEXT_ND
    return parties


def _portfolio_rows(
    detail: pd.DataFrame,
    structural: pd.DataFrame,
    *,
    data_ref: str | None,
) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS)
    detail = detail.copy().reset_index(drop=True)
    detail["cnpj"] = _validate_cnpj_frame(
        detail, column="cnpj_fundo", label="carteira"
    )

    structural = structural.copy().reset_index(drop=True)
    if structural.empty:
        structural = pd.DataFrame({"cnpj": pd.Series(dtype="object")})
    else:
        structural["cnpj"] = _validate_cnpj_frame(
            structural, column="cnpj", label="risco estrutural da carteira"
        )
    structural_columns = [
        "cnpj",
        "sub_jr_min_regulamento",
        "minimo_estrutural_display",
        "minimo_estrutural_natureza",
        "minimo_estrutural_formula",
        "comparacao_estrutural_completa_flag",
        "comparacao_estrutural_motivo",
        "excecao_asterisco_flag",
        "folga_pp",
        "perda_ate_gatilho",
        "situacao_regulatoria",
        "mvp_slide_categoria",
        "mvp_slide_categoria_original",
        "mvp_slide_categoria_override_flag",
        "mvp_slide_categoria_fonte",
        "mvp_slide_categoria_motivo",
        "mvp_faixa_sub_atual",
        "mvp_elegivel_flag",
        "mvp_situacao_piso",
        "posicao_mercado",
        "excesso_vs_mercado",
        "benchmark_confiavel",
        "n_comparaveis_categoria",
        "categoria",
        "data_ref",
    ]
    structural = structural[
        [column for column in structural_columns if column in structural.columns]
    ].rename(
        columns={
            "sub_jr_min_regulamento": "_minimo_estrutural_usado",
            "minimo_estrutural_display": "_minimo_estrutural_display",
            "minimo_estrutural_natureza": "_minimo_estrutural_natureza",
            "minimo_estrutural_formula": "_minimo_estrutural_formula",
            "comparacao_estrutural_completa_flag": "_comparavel_flag",
            "comparacao_estrutural_motivo": "_comparabilidade_motivo",
            "excecao_asterisco_flag": "_excecao_asterisco_flag",
            "folga_pp": "_folga_pp",
            "perda_ate_gatilho": "_capacidade_ate_gatilho",
            "situacao_regulatoria": "_situacao_regulatoria",
            "mvp_slide_categoria": "_mvp_slide_categoria",
            "mvp_slide_categoria_original": "_mvp_slide_categoria_original",
            "mvp_slide_categoria_override_flag": "_mvp_slide_categoria_override_flag",
            "mvp_slide_categoria_fonte": "_mvp_slide_categoria_fonte",
            "mvp_slide_categoria_motivo": "_mvp_slide_categoria_motivo",
            "mvp_faixa_sub_atual": "_mvp_faixa_sub_atual",
            "mvp_elegivel_flag": "_mvp_elegivel_flag",
            "mvp_situacao_piso": "_mvp_situacao_piso",
            "posicao_mercado": "_posicao_mercado",
            "excesso_vs_mercado": "_excesso_vs_mercado",
            "benchmark_confiavel": "_benchmark_confiavel",
            "n_comparaveis_categoria": "_n_comparaveis_categoria",
            "categoria": "_taxonomia_estrutural",
            "data_ref": "_data_ref",
        }
    )
    source = detail.merge(structural, on="cnpj", how="left", validate="one_to_one")

    nature = _series(source, "subordinacao_minima_natureza").map(_text)
    junior = _fraction_from_percent_points(source, "subordinacao_minima_junior_pct")
    support = _fraction_from_percent_points(source, "suporte_estrutural_minimo_pct")
    current = _numeric(source, "subordinacao_atual_pct")
    comparable = _bool_series(source, "_comparavel_flag")

    rows = pd.DataFrame(index=source.index)
    rows["coorte"] = "Carteira 101"
    rows["ordem"] = _numeric(source, "ordem")
    rows["cnpj"] = source["cnpj"]
    rows["cnpj_numerico"] = rows["cnpj"].map(int)
    rows["cnpj_formatado"] = rows["cnpj"].map(_format_cnpj)
    status_identity = _series(source, "status_identidade").map(_text)
    official_name = _series(source, "denominacao").map(_text)
    official_name = official_name.mask(
        status_identity.map(_fold).eq("fora base fidc"), TEXT_ND
    )
    rows["nome_oficial_cvm"] = official_name
    rows["nome_referencia"] = _series(source, "nome_foto").map(_text)
    rows["status_identidade"] = status_identity
    source_ref = _series(source, "_data_ref").map(
        lambda value: _text(value, default="")
    )
    rows["data_ref"] = source_ref.where(source_ref.ne(""), data_ref or TEXT_ND)
    rows["pl_atual_brl"] = _numeric(source, "pl_atual_brl")
    rows["pl_classes_reportadas_brl"] = _numeric(
        source, "pl_classes_reportadas_brl"
    )
    rows["pl_subordinado_atual_brl"] = _numeric(
        source, "pl_subordinado_atual_brl"
    )
    rows["sub_pl_atual"] = current
    rows["status_sub_pl_atual"] = _series(
        source, "subordinacao_atual_status"
    ).map(_text)

    rows["minimo_junior_literal"] = junior.where(nature.eq("junior_pl"))
    rows["minimo_junior_calculado"] = junior.where(
        nature.eq("junior_pl_calculado")
    )
    rows["minimo_junior_ajustado"] = junior.where(
        nature.eq("junior_pl_ajustado")
    )
    rows["suporte_total"] = support.where(
        ~nature.eq("suporte_combinado_pl")
    )
    rows["suporte_combinado_junior_mezanino"] = support.where(
        nature.eq("suporte_combinado_pl")
    )
    rows["minimo_estrutural_usado"] = _numeric(
        source, "_minimo_estrutural_usado"
    )
    rows["minimo_estrutural_display"] = _series(
        source, "_minimo_estrutural_display"
    ).map(_text)
    rows["minimo_estrutural_natureza"] = nature
    rows["minimo_estrutural_formula"] = _series(
        source, "_minimo_estrutural_formula"
    ).map(_text)
    rows["comparavel_flag"] = comparable
    rows["comparabilidade_motivo"] = _series(
        source, "_comparabilidade_motivo"
    ).map(_text)
    rows["excecao_asterisco_flag"] = _bool_series(
        source, "_excecao_asterisco_flag"
    )
    rows["folga_pp"] = _numeric(source, "_folga_pp").where(comparable)
    rows["capacidade_ate_gatilho"] = _numeric(
        source, "_capacidade_ate_gatilho"
    ).where(comparable)
    rows["situacao_regulatoria"] = _series(
        source, "_situacao_regulatoria"
    ).map(_text)
    rows["mvp_slide_categoria"] = _series(
        source, "_mvp_slide_categoria"
    ).map(_text)
    rows["mvp_slide_categoria_original"] = _series(
        source, "_mvp_slide_categoria_original"
    ).map(_text)
    rows["mvp_slide_categoria_override_flag"] = _bool_series(
        source, "_mvp_slide_categoria_override_flag"
    )
    rows["mvp_slide_categoria_fonte"] = _series(
        source, "_mvp_slide_categoria_fonte"
    ).map(_text)
    rows["mvp_slide_categoria_motivo"] = _series(
        source, "_mvp_slide_categoria_motivo"
    ).map(_text)
    rows["mvp_faixa_sub_atual"] = _series(
        source, "_mvp_faixa_sub_atual"
    ).map(_text)
    rows["mvp_elegivel_flag"] = _bool_series(
        source, "_mvp_elegivel_flag"
    )
    rows["mvp_situacao_piso"] = _series(
        source, "_mvp_situacao_piso"
    ).map(_text)
    rows["posicao_mercado"] = _series(source, "_posicao_mercado").map(_text)
    rows["excesso_vs_mercado"] = _numeric(source, "_excesso_vs_mercado")
    rows["benchmark_confiavel"] = _series(
        source, "_benchmark_confiavel", pd.NA
    )
    rows["n_comparaveis_categoria"] = _numeric(
        source, "_n_comparaveis_categoria"
    )
    rows["tipo_exibicao"] = _series(source, "tipo_exibicao").map(_text)
    rows["foco_exibicao"] = _series(source, "foco_exibicao").map(_text)
    rows["taxonomia_estrutural"] = _series(
        source, "_taxonomia_estrutural"
    ).map(_text)
    rows["grupo_comparacao"] = source.apply(
        _comparison_group_from_portfolio, axis=1
    )
    rows = pd.concat(
        [rows, _price_fields(source, _PORTFOLIO_PRICE_ALIASES)], axis=1
    )
    rows = pd.concat([rows, _documentary_parties(source)], axis=1)
    rows["documento_id"] = _series(
        source, "documento_id_regulamento"
    ).map(_text)
    rows["documento_data"] = _series(
        source, "documento_data_regulamento"
    ).map(_text)
    rows["pagina_clausula"] = _series(source, "pagina_clausula").map(_text)
    rows["status_curadoria_documental"] = _series(
        source, "status_curadoria_documental"
    ).map(_text)
    rows["fonte_documental"] = _series(
        source, "subordinacao_minima_fonte"
    ).map(_text)
    rows["texto_minimo"] = _series(source, "subordinacao_minima_texto").map(
        _text
    )
    return rows


def _flagship_comparable(detail: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    junior = _numeric(detail, "subordinacao_minima_junior_pct").notna()
    current = _numeric(detail, "subordinacao_atual_pct").notna()
    text = _series(detail, "subordinacao_minima_texto").map(_fold)
    no_mezzanine = text.str.contains(
        r"(?:nao tem|sem) (?:cota )?mezanin", regex=True, na=False
    )
    explicit_flag = _bool_series(detail, "comparabilidade_tranche_flag")
    comparable = junior & current & (no_mezzanine | explicit_flag)

    reason = pd.Series(
        "N/D — mínimo estrutural ou subordinação atual ausente",
        index=detail.index,
        dtype="object",
    )
    reason = reason.mask(
        junior & current,
        "N/D — equivalência entre mínimo júnior e subordinação total não comprovada",
    )
    reason = reason.mask(
        comparable,
        "Comparável — documento confirma ausência de mezanino",
    )
    return comparable, reason


def _flagship_rows(
    detail: pd.DataFrame,
    *,
    data_ref: str | None,
) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS)
    source = detail.copy().reset_index(drop=True)
    source["cnpj"] = _validate_cnpj_frame(
        source, column="cnpj_fundo", label="flagships"
    )
    current = _numeric(source, "subordinacao_atual_pct")
    junior = _fraction_from_percent_points(source, "subordinacao_minima_junior_pct")
    comparable, comparable_reason = _flagship_comparable(source)
    headroom = (current - junior).where(comparable)
    capacity = loss_until_trigger(current, junior).where(comparable)

    rows = pd.DataFrame(index=source.index)
    rows["coorte"] = "Flagships"
    rows["ordem"] = _numeric(source, "ordem_familia")
    rows["cnpj"] = source["cnpj"]
    rows["cnpj_numerico"] = rows["cnpj"].map(int)
    rows["cnpj_formatado"] = rows["cnpj"].map(_format_cnpj)
    rows["nome_oficial_cvm"] = _series(source, "denominacao").map(_text)
    rows["nome_referencia"] = _series(source, "familia_flagship").map(_text)
    rows["status_identidade"] = "localizado"
    rows["data_ref"] = data_ref or TEXT_ND
    rows["pl_atual_brl"] = _numeric(source, "pl_atual_brl")
    rows["pl_classes_reportadas_brl"] = _numeric(
        source, "pl_classes_reportadas_brl"
    )
    rows["pl_subordinado_atual_brl"] = _numeric(
        source, "pl_subordinado_atual_brl"
    )
    rows["sub_pl_atual"] = current
    rows["status_sub_pl_atual"] = _series(
        source, "subordinacao_atual_status"
    ).map(_text)
    rows["minimo_junior_literal"] = junior
    rows["minimo_junior_calculado"] = np.nan
    rows["minimo_junior_ajustado"] = np.nan
    rows["suporte_total"] = np.nan
    rows["suporte_combinado_junior_mezanino"] = np.nan
    rows["minimo_estrutural_usado"] = junior.where(comparable)
    rows["minimo_estrutural_display"] = _series(
        source, "subordinacao_minima_junior_display"
    ).map(_text)
    rows["minimo_estrutural_natureza"] = np.where(
        junior.notna(), "junior_pl", "sem_indice"
    )
    rows["minimo_estrutural_formula"] = np.where(
        junior.notna(), "direto no regulamento", TEXT_ND
    )
    rows["comparavel_flag"] = comparable.astype(bool)
    rows["comparabilidade_motivo"] = comparable_reason
    rows["excecao_asterisco_flag"] = junior.notna() & ~comparable
    rows["folga_pp"] = headroom
    rows["capacidade_ate_gatilho"] = capacity
    rows["situacao_regulatoria"] = np.where(
        ~comparable,
        "não medido",
        np.where(headroom.lt(0), "abaixo do mínimo", "acima do mínimo"),
    )
    rows["mvp_slide_categoria"] = TEXT_ND
    rows["mvp_faixa_sub_atual"] = TEXT_ND
    rows["mvp_elegivel_flag"] = False
    rows["mvp_situacao_piso"] = TEXT_ND
    rows["posicao_mercado"] = TEXT_ND
    rows["excesso_vs_mercado"] = np.nan
    rows["benchmark_confiavel"] = pd.NA
    rows["n_comparaveis_categoria"] = np.nan
    rows["tipo_exibicao"] = TEXT_ND
    rows["foco_exibicao"] = TEXT_ND
    rows["taxonomia_estrutural"] = _series(source, "categoria").map(_text)
    rows["grupo_comparacao"] = source.apply(
        _comparison_group_from_flagship, axis=1
    )
    rows = pd.concat(
        [rows, _price_fields(source, _FLAGSHIP_PRICE_ALIASES)], axis=1
    )
    rows = pd.concat([rows, _documentary_parties(source)], axis=1)
    rows["documento_id"] = _series(
        source, "documento_id_regulamento"
    ).map(_text)
    rows["documento_data"] = _series(
        source, "documento_data_regulamento"
    ).map(_text)
    rows["pagina_clausula"] = _series(source, "pagina_clausula").map(_text)
    rows["status_curadoria_documental"] = _series(
        source, "status_curadoria_documental"
    ).map(_text)
    rows["fonte_documental"] = _series(
        source, "subordinacao_minima_fonte"
    ).map(_text)
    rows["texto_minimo"] = _series(source, "subordinacao_minima_texto").map(
        _text
    )
    return rows


def _empty_manual_frame() -> pd.DataFrame:
    columns = [
        *MANUAL_ENRICHMENT_COLUMNS,
        *MANUAL_CNPJ_RESOLUTION_COLUMNS,
        "coortes_encontradas",
        "campos_aplicados",
        "aplicado_flag",
        "motivo_aplicacao",
    ]
    return pd.DataFrame(columns=columns)


def _normalize_manual(
    manual: pd.DataFrame | None,
    *,
    known_cnpjs: tuple[str, ...] = (),
) -> pd.DataFrame:
    if manual is None or manual.empty:
        return _empty_manual_frame()
    normalized = manual.copy().rename(columns=_MANUAL_ALIASES).reset_index(drop=True)
    if "cnpj" not in normalized.columns:
        if "raiz_cnpj_foto" not in normalized.columns:
            raise KeyError(
                "overlay manual sem coluna cnpj, cnpj_fundo ou raiz_cnpj_foto"
            )
        roots = normalized["raiz_cnpj_foto"].map(
            lambda value: re.sub(r"\D", "", str(value or "")).zfill(8)
            if re.sub(r"\D", "", str(value or ""))
            else ""
        )
        normalized["raiz_cnpj_foto"] = roots
        mapped: list[str] = []
        resolution_status: list[str] = []
        candidate_counts: list[int] = []
        candidate_lists: list[str] = []
        for root in roots:
            candidates = [
                cnpj for cnpj in known_cnpjs if root and cnpj.startswith(root)
            ]
            candidate_counts.append(len(candidates))
            candidate_lists.append("; ".join(candidates))
            if len(candidates) > 1:
                raise ValueError(
                    "raiz manual ambígua: "
                    f"{root} resolve para {len(candidates)} CNPJs nas coortes "
                    f"({'; '.join(candidates)})"
                )
            if candidates:
                mapped.append(candidates[0])
                resolution_status.append("correspondencia_unica")
            else:
                mapped.append("")
                resolution_status.append("sem_correspondencia")
        normalized["cnpj"] = mapped
        normalized["status_resolucao_cnpj"] = resolution_status
        normalized["quantidade_candidatos_cnpj"] = candidate_counts
        normalized["candidatos_cnpj"] = candidate_lists
    else:
        normalized["cnpj"] = normalized["cnpj"].map(_cnpj_digits)
        normalized["status_resolucao_cnpj"] = "cnpj_informado"
        normalized["quantidade_candidatos_cnpj"] = normalized["cnpj"].map(
            lambda cnpj: int(cnpj in known_cnpjs) if known_cnpjs else 1
        )
        normalized["candidatos_cnpj"] = normalized["cnpj"].where(
            normalized["cnpj"].isin(known_cnpjs) if known_cnpjs else True,
            "",
        )
    resolved_cnpj = ~normalized["cnpj"].map(_is_missing_text)
    duplicated_mask = resolved_cnpj & normalized["cnpj"].duplicated(keep=False)
    if duplicated_mask.any():
        duplicated = normalized.loc[
            duplicated_mask, "cnpj"
        ].unique().tolist()
        raise ValueError(f"overlay manual contém CNPJ duplicado: {duplicated}")
    for column in MANUAL_ENRICHMENT_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = ""
    missing_status = normalized["status_transcricao"].map(_is_missing_text)
    normalized.loc[missing_status, "status_transcricao"] = "confirmado pelo usuario"
    normalized["_status_aprovado"] = normalized["status_transcricao"].map(
        lambda value: _fold(value) in _APPROVED_MANUAL_STATUSES
    )
    return normalized


def _apply_manual_overlay(
    rows_by_cohort: list[pd.DataFrame],
    manual: pd.DataFrame | None,
) -> tuple[list[pd.DataFrame], pd.DataFrame]:
    known_cnpjs = tuple(
        dict.fromkeys(
            cnpj
            for rows in rows_by_cohort
            for cnpj in rows.get("cnpj", pd.Series(dtype="object")).astype(str)
        )
    )
    audit = _normalize_manual(manual, known_cnpjs=known_cnpjs)
    if audit.empty:
        return rows_by_cohort, audit

    audit["coortes_encontradas"] = ""
    audit["campos_aplicados"] = ""
    audit["aplicado_flag"] = False
    audit["motivo_aplicacao"] = ""

    for audit_index, manual_row in audit.iterrows():
        cnpj = manual_row["cnpj"]
        matched_cohorts: list[str] = []
        applied_fields: list[str] = []
        if manual_row["status_resolucao_cnpj"] == "sem_correspondencia":
            audit.loc[audit_index, "motivo_aplicacao"] = (
                "raiz de CNPJ não resolvida nas duas coortes"
            )
            continue
        if not bool(manual_row["_status_aprovado"]):
            audit.loc[audit_index, "motivo_aplicacao"] = (
                "status de transcrição não aprovado"
            )
            continue
        for rows in rows_by_cohort:
            mask = rows["cnpj"].eq(cnpj)
            if not mask.any():
                continue
            matched_cohorts.extend(rows.loc[mask, "coorte"].astype(str).unique())
            cohort_applied: list[str] = []
            for column in PARTY_COLUMNS:
                value = manual_row.get(column)
                if _is_missing_text(value):
                    continue
                existing_missing = rows.loc[mask, column].map(_is_missing_text)
                if existing_missing.any():
                    rows.loc[mask & rows[column].map(_is_missing_text), column] = str(
                        value
                    ).strip()
                    cohort_applied.append(column)
            if cohort_applied:
                source = _text(manual_row.get("fonte_manual"))
                rows.loc[mask, "fonte_partes_recebivel"] = rows.loc[
                    mask, "fonte_partes_recebivel"
                ].where(
                    ~rows.loc[mask, "fonte_partes_recebivel"].map(_is_missing_text),
                    source,
                )
                rows.loc[mask, "status_complemento_manual"] = "manual_aplicado"
                rows.loc[mask, "observacao_complemento_manual"] = _text(
                    manual_row.get("observacao")
                )
                applied_fields.extend(cohort_applied)

        audit.loc[audit_index, "coortes_encontradas"] = "; ".join(
            dict.fromkeys(matched_cohorts)
        )
        audit.loc[audit_index, "campos_aplicados"] = "; ".join(
            dict.fromkeys(applied_fields)
        )
        audit.loc[audit_index, "aplicado_flag"] = bool(applied_fields)
        if applied_fields:
            audit.loc[audit_index, "motivo_aplicacao"] = (
                "overlay aplicado somente em lacunas"
            )
        elif matched_cohorts:
            audit.loc[audit_index, "motivo_aplicacao"] = (
                "campos ausentes no overlay ou já preenchidos documentalmente"
            )
        else:
            audit.loc[audit_index, "motivo_aplicacao"] = "CNPJ fora das duas coortes"

    return rows_by_cohort, audit.drop(columns=["_status_aprovado"])


def _completion_fields(row: pd.Series) -> list[str]:
    missing: list[str] = []
    for column, label in (
        ("nome_oficial_cvm", "nome oficial CVM"),
        ("pl_atual_brl", "PL atual"),
        ("sub_pl_atual", "Sub/PL atual"),
        ("minimo_estrutural_usado", "mínimo estrutural comparável"),
        ("grupo_comparacao", "grupo de comparação"),
        ("preco_cota_display", "preço unitário da cota"),
        ("originador", "originador"),
        ("cedente", "cedente"),
        ("sacado_devedor", "sacado/devedor"),
        ("tipo_recebivel_literal", "tipo de recebível"),
    ):
        value = row.get(column)
        if isinstance(value, (int, float, np.integer, np.floating)):
            is_missing = pd.isna(value)
        else:
            is_missing = _is_missing_text(value)
        if is_missing:
            missing.append(label)
    return missing


def _status_preenchimento(row: pd.Series) -> str:
    if _fold(row.get("status_identidade")) == "fora base fidc":
        return "fora_perimetro"
    if pd.isna(row.get("sub_pl_atual")):
        return "sub_pl_atual_ausente"
    junior_any = any(
        pd.notna(row.get(column))
        for column in (
            "minimo_junior_literal",
            "minimo_junior_calculado",
            "minimo_junior_ajustado",
            "suporte_total",
            "suporte_combinado_junior_mezanino",
        )
    )
    if not junior_any:
        return "minimo_estrutural_ausente"
    if not bool(row.get("comparavel_flag")):
        return "estrutura_incomparavel"
    return "completo_para_folga"


def _finalize(rows: pd.DataFrame) -> pd.DataFrame:
    rows = rows.copy()
    missing = rows.apply(_completion_fields, axis=1)
    rows["campos_nao_preenchidos"] = missing.map(
        lambda values: "; ".join(values) if values else "Nenhum"
    )
    rows["status_preenchimento"] = rows.apply(_status_preenchimento, axis=1)
    for column in NORMALIZED_COLUMNS:
        if column not in rows.columns:
            rows[column] = (
                np.nan
                if column.endswith(("_brl", "_pp"))
                or column
                in {
                    "excesso_vs_mercado",
                    "n_comparaveis_categoria",
                }
                else False
                if column == "reclassificacao_proposta_flag"
                else pd.NA
                if column
                in {
                    "benchmark_confiavel",
                    "middle_market_porte_documentado_flag",
                }
                else TEXT_ND
            )
    return rows.loc[:, NORMALIZED_COLUMNS].reset_index(drop=True)


def _has_numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(_series(frame, column), errors="coerce").notna()


def _has_text(frame: pd.DataFrame, column: str) -> pd.Series:
    return ~_series(frame, column).map(_is_missing_text)


def _coverage(rows: pd.DataFrame) -> pd.DataFrame:
    definitions: tuple[tuple[str, pd.Series], ...] = (
        ("nome_oficial_cvm", _has_text(rows, "nome_oficial_cvm")),
        ("pl_atual_brl", _has_numeric(rows, "pl_atual_brl")),
        ("sub_pl_atual", _has_numeric(rows, "sub_pl_atual")),
        (
            "indice_minimo_junior",
            pd.concat(
                [
                    _numeric(rows, "minimo_junior_literal"),
                    _numeric(rows, "minimo_junior_calculado"),
                    _numeric(rows, "minimo_junior_ajustado"),
                ],
                axis=1,
            ).notna().any(axis=1),
        ),
        (
            "indice_minimo_estrutural",
            pd.concat(
                [
                    _numeric(rows, "minimo_junior_literal"),
                    _numeric(rows, "minimo_junior_calculado"),
                    _numeric(rows, "minimo_junior_ajustado"),
                    _numeric(rows, "suporte_total"),
                    _numeric(rows, "suporte_combinado_junior_mezanino"),
                ],
                axis=1,
            ).notna().any(axis=1),
        ),
        ("folga_pp", _has_numeric(rows, "folga_pp")),
        ("grupo_comparacao", _has_text(rows, "grupo_comparacao")),
        (
            "preco_cota_unitario",
            _has_numeric(rows, "preco_cota_brl")
            | _has_text(rows, "preco_cota_display"),
        ),
        (
            "preco_cota_classe_serie",
            _has_text(rows, "preco_cota_classe_serie"),
        ),
        (
            "preco_cota_natureza",
            _has_text(rows, "preco_cota_natureza"),
        ),
        (
            "preco_cota_documento_data",
            _has_text(rows, "preco_cota_documento_data"),
        ),
        (
            "preco_cota_documento_id",
            _has_text(rows, "preco_cota_documento_id"),
        ),
        ("preco_cota_fonte", _has_text(rows, "preco_cota_fonte")),
        ("posicao_mercado", _has_text(rows, "posicao_mercado")),
        (
            "excesso_vs_mercado",
            _has_numeric(rows, "excesso_vs_mercado"),
        ),
        (
            "n_comparaveis_categoria",
            _has_numeric(rows, "n_comparaveis_categoria"),
        ),
        (
            "benchmark_confiavel",
            _series(rows, "benchmark_confiavel").notna(),
        ),
        (
            "cedente_originador_literal",
            _has_text(rows, "cedente_originador_literal"),
        ),
        ("originador", _has_text(rows, "originador")),
        ("cedente", _has_text(rows, "cedente")),
        ("sacado_devedor", _has_text(rows, "sacado_devedor")),
        (
            "tipo_recebivel_literal",
            _has_text(rows, "tipo_recebivel_literal"),
        ),
        (
            "fonte_partes_recebivel",
            _has_text(rows, "fonte_partes_recebivel"),
        ),
    )
    pl = pd.to_numeric(rows["pl_atual_brl"], errors="coerce")
    positive_pl = pl.where(pl.gt(0))
    result: list[dict[str, object]] = []
    for cohort, cohort_rows in rows.groupby("coorte", sort=False):
        cohort_index = cohort_rows.index
        cohort_pl = positive_pl.loc[cohort_index]
        total_pl = cohort_pl.sum(min_count=1)
        for field, available in definitions:
            available = available.loc[cohort_index].fillna(False)
            pl_with_data = cohort_pl.where(available).sum()
            result.append(
                {
                    "coorte": cohort,
                    "campo": field,
                    "linhas_com_dado": int(available.sum()),
                    "linhas_total": int(len(cohort_rows)),
                    "cobertura_contagem_pct": float(available.mean())
                    if len(cohort_rows)
                    else np.nan,
                    "pl_com_dado_brl": float(pl_with_data),
                    "pl_total_brl": float(total_pl)
                    if pd.notna(total_pl)
                    else np.nan,
                    "cobertura_pl_pct": float(pl_with_data / total_pl)
                    if pd.notna(pl_with_data)
                    and pd.notna(total_pl)
                    and total_pl > 0
                    else np.nan,
                }
            )
    return pd.DataFrame(result)


def _gaps(rows: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "coorte",
        "cnpj",
        "nome_referencia",
        "status_preenchimento",
        "campos_nao_preenchidos",
        "grupo_comparacao",
        "preco_cota_status",
        "preco_cota_natureza",
        "preco_cota_excecao_asterisco_flag",
        "preco_cota_fonte",
        "comparabilidade_motivo",
        "status_curadoria_documental",
    ]
    return rows.loc[
        rows["campos_nao_preenchidos"].ne("Nenhum"), columns
    ].reset_index(drop=True)


def _dictionary() -> pd.DataFrame:
    descriptions: Mapping[str, tuple[str, str]] = {
        "grupo_comparacao": (
            "Grupo comparável já usado na curadoria Carteira I versus flagships.",
            "Taxonomia de comparação estabelecida em industry_flagship_curation.",
        ),
        "preco_cota_brl": (
            "Preço unitário em reais quando há um único valor documental distinto.",
            "Curadoria de emissão/VNU; múltiplos valores permanecem no campo de leitura.",
        ),
        "preco_cota_display": (
            "Leitura do preço unitário preservada por classe ou série.",
            "Documento de emissão/VNU; remuneração e quantidade são excluídas.",
        ),
        "preco_cota_natureza": (
            "Natureza explícita: VNU, emissão, subscrição ou integralização.",
            "Texto da fonte; ausência de termo explícito fica marcada com asterisco.",
        ),
        "preco_cota_classe_serie": (
            "Classe ou série à qual o preço unitário se refere.",
            "Documento de emissão/VNU.",
        ),
        "preco_cota_documento_data": (
            "Data do documento ou deliberação que sustenta o preço unitário.",
            "Documento de emissão/VNU.",
        ),
        "preco_cota_documento_id": (
            "Identificador do documento que sustenta o preço unitário.",
            "Documento de emissão/VNU.",
        ),
        "preco_cota_fonte": (
            "Fonte, caminho ou URL da evidência de preço unitário.",
            "Documento de emissão/VNU.",
        ),
        "preco_cota_status": (
            "Status de localização e revisão documental do preço unitário.",
            "Curadoria documental.",
        ),
        "preco_cota_excecao_asterisco_flag": (
            "Marca múltiplas classes/valores ou natureza documental ambígua.",
            "Regra de apresentação; a explicação permanece nos campos de preço.",
        ),
        "posicao_mercado": (
            "Posição relativa aos pares, calculada pelo pacote estrutural.",
            "Propagado de carteira_structural, sem recálculo.",
        ),
        "excesso_vs_mercado": (
            "Subordinação atual menos mediana de mercado; fração, quando confiável.",
            "Propagado de carteira_structural, sem recálculo.",
        ),
        "benchmark_confiavel": (
            "Indica se a comparação de mercado cumpre o limiar de pares.",
            "Propagado de carteira_structural, sem recálculo.",
        ),
        "n_comparaveis_categoria": (
            "Número de pares comparáveis na categoria.",
            "Propagado de carteira_structural, sem recálculo.",
        ),
        "categoria_risco_atual": (
            "Categoria vigente antes da revisão documental Financeiro/Agro.",
            "Ledger versionado por CNPJ; demais casos preservam a categoria estrutural vigente.",
        ),
        "categoria_risco_proposta": (
            "Categoria após decisões explicitamente aplicadas.",
            "Ledger versionado por CNPJ; applied_flag=NAO mantém a categoria atual.",
        ),
        "subtipo_risco_diagnosticado": (
            "Tipo de risco descrito na revisão documental por CNPJ.",
            "Ledger versionado; N/D fora do universo auditado, sem inferência pelo nome.",
        ),
        "reclassificacao_proposta_flag": (
            "Indica decisão de reclassificação efetivamente aplicada.",
            "Verdadeiro somente quando applied_flag=SIM no ledger.",
        ),
        "status_avaliacao_reclassificacao": (
            "Status da decisão ou pendência documental.",
            "Ledger versionado por CNPJ.",
        ),
        "fundamento_avaliacao_reclassificacao": (
            "Racional registrado para a decisão.",
            "Ledger versionado por CNPJ.",
        ),
        "fonte_avaliacao_reclassificacao": (
            "Fonte ou evidência registrada para a decisão.",
            "Ledger versionado por CNPJ.",
        ),
        "middle_market_status": (
            "Triagem documental da hipótese Middle Market.",
            "Ledger versionado; Candidato e Pendente não comprovam porte.",
        ),
        "middle_market_evidencia": (
            "Evidência associada à triagem Middle Market.",
            "Ledger versionado por CNPJ.",
        ),
        "middle_market_porte_documentado_flag": (
            "Indica se o porte Middle Market foi documentado.",
            "N/D para candidatos e pendências sem evidência de porte.",
        ),
    }
    numeric_columns = {
        "ordem",
        "cnpj_numerico",
        "pl_atual_brl",
        "pl_classes_reportadas_brl",
        "pl_subordinado_atual_brl",
        "sub_pl_atual",
        "minimo_junior_literal",
        "minimo_junior_calculado",
        "minimo_junior_ajustado",
        "suporte_total",
        "suporte_combinado_junior_mezanino",
        "minimo_estrutural_usado",
        "folga_pp",
        "capacidade_ate_gatilho",
        "excesso_vs_mercado",
        "n_comparaveis_categoria",
        "preco_cota_brl",
    }
    boolean_columns = {
        "comparavel_flag",
        "excecao_asterisco_flag",
        "benchmark_confiavel",
        "mvp_elegivel_flag",
        "mvp_slide_categoria_override_flag",
        "preco_cota_excecao_asterisco_flag",
        "reclassificacao_proposta_flag",
        "middle_market_porte_documentado_flag",
    }
    rows: list[dict[str, str]] = []
    for column in NORMALIZED_COLUMNS:
        description, source = descriptions.get(
            column,
            (column.replace("_", " "), "Base normalizada compartilhada."),
        )
        if column in boolean_columns:
            data_type = "booleano"
            gap = "vazio/NA quando não calculado"
        elif column in numeric_columns:
            data_type = "numérico"
            gap = "NaN; nunca convertido em zero"
        else:
            data_type = "texto"
            gap = "N/D quando não localizado"
        rows.append(
            {
                "campo": column,
                "tipo_dado": data_type,
                "descricao": description,
                "origem_regra": source,
                "tratamento_lacuna": gap,
            }
        )
    return pd.DataFrame(rows)


def build_industry_portfolio_export(
    *,
    carteira_detail: pd.DataFrame,
    carteira_structural: pd.DataFrame,
    flagship_detail: pd.DataFrame,
    manual_enrichment: pd.DataFrame | None = None,
    carteira_document_audit: pd.DataFrame | None = None,
    carteira_price_evidence: pd.DataFrame | None = None,
    risk_review: pd.DataFrame | None = None,
    data_ref: str | None = None,
) -> IndustryPortfolioExportResult:
    """Build normalized portfolio, flagship, coverage and gap tables."""

    carteira = _portfolio_rows(
        carteira_detail, carteira_structural, data_ref=data_ref
    )
    carteira = _apply_document_audit(carteira, carteira_document_audit)
    carteira = _apply_price_evidence(carteira, carteira_price_evidence)
    flagships = _flagship_rows(flagship_detail, data_ref=data_ref)
    cohorts, manual_audit = _apply_manual_overlay(
        [carteira, flagships], manual_enrichment
    )
    carteira, flagships = cohorts
    if risk_review is None:
        risk_review = _load_financeiro_agro_risk_review()
    carteira = _finalize(
        _apply_financeiro_agro_risk_review(carteira, risk_review)
    )
    flagships = _finalize(flagships)
    combined = pd.concat([carteira, flagships], ignore_index=True)
    return IndustryPortfolioExportResult(
        carteira=carteira,
        flagships=flagships,
        coverage=_coverage(combined),
        gaps=_gaps(combined),
        manual=manual_audit.reset_index(drop=True),
        dictionary=_dictionary(),
        prices=_price_evidence_table(carteira_price_evidence),
    )


def build_industry_portfolio_export_from_payload(
    payload: Mapping[str, object],
    *,
    manual_enrichment: pd.DataFrame | None = None,
    carteira_document_audit: pd.DataFrame | None = None,
    carteira_price_evidence: pd.DataFrame | None = None,
    risk_review: pd.DataFrame | None = None,
    data_ref: str | None = None,
) -> IndustryPortfolioExportResult:
    """Convenience wrapper for the existing revision artifact payload."""

    if data_ref is None:
        candidate = payload.get("latest_complete") or payload.get("latest")
        data_ref = str(candidate) if candidate else None
    if carteira_document_audit is None:
        audit_records = payload.get("carteira_1_document_audit")
        if audit_records is None:
            audit_records = payload.get("carteira_101_document_audit", [])
        carteira_document_audit = pd.DataFrame(audit_records)
    if carteira_price_evidence is None:
        price_records = payload.get("carteira_1_price_evidence")
        if price_records is None:
            price_records = payload.get("carteira_101_document_prices", [])
        carteira_price_evidence = pd.DataFrame(price_records)
    return build_industry_portfolio_export(
        carteira_detail=pd.DataFrame(payload.get("carteira_1_curation", [])),
        carteira_structural=pd.DataFrame(
            payload.get("carteira_1_structural_assets", [])
        ),
        flagship_detail=pd.DataFrame(payload.get("flagship_curation", [])),
        manual_enrichment=manual_enrichment,
        carteira_document_audit=carteira_document_audit,
        carteira_price_evidence=carteira_price_evidence,
        risk_review=risk_review,
        data_ref=data_ref,
    )
