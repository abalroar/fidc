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
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Mapping

import numpy as np
import pandas as pd

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
    "tipo_exibicao",
    "foco_exibicao",
    "taxonomia_estrutural",
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


@dataclass(frozen=True)
class IndustryPortfolioExportResult:
    """Tables needed by the standalone Carteira 1/flagships workbook."""

    carteira: pd.DataFrame
    flagships: pd.DataFrame
    coverage: pd.DataFrame
    gaps: pd.DataFrame
    manual: pd.DataFrame


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
    rows["tipo_exibicao"] = _series(source, "tipo_exibicao").map(_text)
    rows["foco_exibicao"] = _series(source, "foco_exibicao").map(_text)
    rows["taxonomia_estrutural"] = _series(
        source, "_taxonomia_estrutural"
    ).map(_text)
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
    rows["tipo_exibicao"] = TEXT_ND
    rows["foco_exibicao"] = TEXT_ND
    rows["taxonomia_estrutural"] = _series(source, "categoria").map(_text)
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
            rows[column] = np.nan if column.endswith(("_brl", "_pp")) else TEXT_ND
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
        "comparabilidade_motivo",
        "status_curadoria_documental",
    ]
    return rows.loc[
        rows["campos_nao_preenchidos"].ne("Nenhum"), columns
    ].reset_index(drop=True)


def build_industry_portfolio_export(
    *,
    carteira_detail: pd.DataFrame,
    carteira_structural: pd.DataFrame,
    flagship_detail: pd.DataFrame,
    manual_enrichment: pd.DataFrame | None = None,
    data_ref: str | None = None,
) -> IndustryPortfolioExportResult:
    """Build normalized portfolio, flagship, coverage and gap tables."""

    carteira = _portfolio_rows(
        carteira_detail, carteira_structural, data_ref=data_ref
    )
    flagships = _flagship_rows(flagship_detail, data_ref=data_ref)
    cohorts, manual_audit = _apply_manual_overlay(
        [carteira, flagships], manual_enrichment
    )
    carteira, flagships = (_finalize(frame) for frame in cohorts)
    combined = pd.concat([carteira, flagships], ignore_index=True)
    return IndustryPortfolioExportResult(
        carteira=carteira,
        flagships=flagships,
        coverage=_coverage(combined),
        gaps=_gaps(combined),
        manual=manual_audit.reset_index(drop=True),
    )


def build_industry_portfolio_export_from_payload(
    payload: Mapping[str, object],
    *,
    manual_enrichment: pd.DataFrame | None = None,
    data_ref: str | None = None,
) -> IndustryPortfolioExportResult:
    """Convenience wrapper for the existing revision artifact payload."""

    if data_ref is None:
        candidate = payload.get("latest_complete") or payload.get("latest")
        data_ref = str(candidate) if candidate else None
    return build_industry_portfolio_export(
        carteira_detail=pd.DataFrame(payload.get("carteira_1_curation", [])),
        carteira_structural=pd.DataFrame(
            payload.get("carteira_1_structural_assets", [])
        ),
        flagship_detail=pd.DataFrame(payload.get("flagship_curation", [])),
        manual_enrichment=manual_enrichment,
        data_ref=data_ref,
    )
