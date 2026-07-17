"""Auditable analytical tables for the July 2026 FIDC industry revision.

The presentation layer consumes these tables; it does not recalculate ranks,
coverage or denominators.  The module is deliberately file-format agnostic and
keeps three distinctions explicit throughout:

* reporting vehicle / class CNPJ versus legal fund CNPJ;
* a reported numeric zero versus a source field that was empty; and
* an identified provider outside a fixed Top 10 versus a provider not reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Iterable, Mapping

import pandas as pd

from services.industry_anbima import ANBIMA_FOCUS_BY_TYPE
from services.industry_executive_pack import apply_anbima_classification
from services.industry_intelligence import canonical_provider


LATEST_COMPLETE = "2026-05"
BRIDGE_FROM = "2024-06"
BRIDGE_TO = "2024-07"
ROLE_COLUMNS: Mapping[str, tuple[str, str]] = {
    "administrador": ("admin_nome", "admin_cnpj"),
    "gestor": ("gestor_nome", "gestor_cnpj"),
    "custodiante": ("custodiante_nome", "custodiante_cnpj"),
}
AGING_VALUE_COLUMNS: tuple[str, ...] = (
    "inad_ate_30d",
    "inad_31_60d",
    "inad_61_90d",
    "inad_91_120d",
    "inad_121_150d",
    "inad_151_180d",
    "inad_181_360d",
    "inad_361_720d",
    "inad_721_1080d",
    "inad_maior_1080d",
    "inad_acima_360d",
)


def _digits(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    raw = str(value).strip()
    if re.fullmatch(r"\d{1,14}(?:\.0+)?", raw):
        raw = raw.split(".", 1)[0]
    digits = re.sub(r"\D", "", raw)
    return digits.zfill(14) if 0 < len(digits) <= 14 else ""


def format_cnpj(value: object) -> str:
    digits = _digits(value)
    if len(digits) != 14:
        return ""
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = re.sub(r"\s+", " ", str(value).strip())
    return "" if text.lower() in {"", "nan", "none", "nat", "n/d"} else text


def _as_nullable_bool(series: pd.Series) -> pd.Series:
    if str(series.dtype) == "boolean":
        return series
    if pd.api.types.is_bool_dtype(series):
        return series.astype("boolean")
    normalized = series.map(_clean).str.upper()
    output = pd.Series(pd.NA, index=series.index, dtype="boolean")
    output.loc[normalized.isin({"1", "TRUE", "T", "SIM", "S", "YES", "Y"})] = True
    output.loc[normalized.isin({"0", "FALSE", "F", "NAO", "NÃO", "N", "NO"})] = False
    return output


def _sum_min(values: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce")
    return float(numeric.sum(min_count=1)) if numeric.notna().any() else float("nan")


def _bool_any_preserve_unknown(values: pd.Series) -> object:
    nullable = _as_nullable_bool(values)
    if nullable.eq(True).any():  # noqa: E712 - pandas nullable comparison
        return True
    if nullable.notna().any():
        return False
    return pd.NA


def add_reporting_flags(vehicle_monthly: pd.DataFrame) -> pd.DataFrame:
    """Attach report-presence flags without interpreting numeric zero as presence.

    New pipeline materializations contain exact ``reports_*`` flags captured
    before numeric coercion.  Older materializations cannot recover field-level
    blanks.  For them, the function exposes a clearly labelled upper-bound
    proxy based on the presence of the Table I row; it never calls a zero a
    reported value merely because the numeric column is zero.
    """

    frame = vehicle_monthly.copy()
    explicit = "reports_carteira_dc" in frame.columns
    if "reports_tab_i" in frame.columns:
        tab_i = _as_nullable_bool(frame["reports_tab_i"])
    else:
        tab_i = pd.Series(False, index=frame.index, dtype="boolean")
        for column in ("admin_nome", "admin_cnpj", "condominio", "exclusivo"):
            if column in frame.columns:
                tab_i |= frame[column].map(_clean).ne("").astype("boolean")
        frame["reports_tab_i"] = tab_i

    for column in (
        "reports_carteira_dc",
        "reports_dc_inadimplentes",
        "reports_dc_a_vencer_com_parcela_inad",
    ):
        if column in frame.columns:
            frame[column] = _as_nullable_bool(frame[column])
        else:
            # Field-level presence was lost in the old CSV.  Table-I row
            # presence is useful as an upper bound, not as an exact claim.
            frame[column] = tab_i.copy()

    for value_column in AGING_VALUE_COLUMNS:
        report_column = f"reports_{value_column}"
        if report_column in frame.columns:
            frame[report_column] = _as_nullable_bool(frame[report_column])
        else:
            frame[report_column] = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    if "reports_aging" in frame.columns:
        frame["reports_aging"] = _as_nullable_bool(frame["reports_aging"])
    else:
        frame["reports_aging"] = pd.Series(pd.NA, index=frame.index, dtype="boolean")

    frame["report_flag_source"] = frame.get(
        "report_flag_source",
        pd.Series("", index=frame.index),
    ).map(_clean)
    empty_source = frame["report_flag_source"].eq("")
    frame.loc[empty_source, "report_flag_source"] = (
        "campo_bruto_CVM" if explicit else "presença_da_linha_Tab_I_inferida_no_legado"
    )
    frame["field_presence_exact"] = bool(explicit)
    return frame


def build_base_by_vehicle(vehicle_monthly: pd.DataFrame) -> pd.DataFrame:
    """Build the competence × reporting-CNPJ audit base used by every QA table."""

    if vehicle_monthly is None or vehicle_monthly.empty:
        return pd.DataFrame()
    required = {"competencia", "cnpj", "pl", "carteira_dc", "dc_inadimplentes"}
    missing = required.difference(vehicle_monthly.columns)
    if missing:
        raise ValueError(f"vehicle_monthly sem colunas obrigatórias: {sorted(missing)}")
    frame = add_reporting_flags(vehicle_monthly)
    frame["competencia"] = frame["competencia"].astype(str).str[:7]
    frame["cnpj_veiculo"] = frame["cnpj"].map(_digits)
    fund_source = frame.get("cnpj_fundo", frame["cnpj"])
    frame["cnpj_fundo"] = fund_source.map(_digits)
    frame["cnpj_fundo"] = frame["cnpj_fundo"].where(
        frame["cnpj_fundo"].ne(""), frame["cnpj_veiculo"]
    )
    frame["cnpj_formatado"] = frame["cnpj_veiculo"].map(format_cnpj)
    frame["cnpj_fundo_formatado"] = frame["cnpj_fundo"].map(format_cnpj)

    numeric_columns = (
        "pl",
        "carteira_dc",
        "dc_inadimplentes",
        "dc_inadimplentes_ajustado",
        "dc_a_vencer_com_parcela_inad",
        *AGING_VALUE_COLUMNS,
    )
    for column in numeric_columns:
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    report_pair = frame["reports_carteira_dc"].eq(True) & frame[  # noqa: E712
        "reports_dc_inadimplentes"
    ].eq(True)
    frame["reports_inadimplencia_pair"] = report_pair.astype("boolean")
    frame["carteira_positiva"] = frame["carteira_dc"].gt(0)
    frame["inad_supera_carteira"] = (
        report_pair
        & frame["dc_inadimplentes"].gt(frame["carteira_dc"])
    )
    nonnegative_inad = frame["dc_inadimplentes"].clip(lower=0)
    nonnegative_dc = frame["carteira_dc"].clip(lower=0)
    frame["dc_inadimplentes_ajustado_recalculado"] = nonnegative_inad.where(
        nonnegative_inad.le(nonnegative_dc), nonnegative_dc
    )
    frame.loc[~report_pair, "dc_inadimplentes_ajustado_recalculado"] = pd.NA
    frame["excesso_removido_ajuste"] = (
        nonnegative_inad - frame["dc_inadimplentes_ajustado_recalculado"]
    ).clip(lower=0)
    frame.loc[~report_pair, "excesso_removido_ajuste"] = pd.NA
    frame["motivo_ajuste"] = "sem ajuste"
    frame.loc[frame["inad_supera_carteira"], "motivo_ajuste"] = (
        "inadimplência reportada supera a carteira; limite aplicado por veículo"
    )
    frame.loc[~report_pair, "motivo_ajuste"] = "campos não observáveis em conjunto"
    frame["regra_inclusao"] = "fora do denominador"
    frame.loc[report_pair & frame["carteira_dc"].gt(0), "regra_inclusao"] = (
        "campos reportados e carteira positiva"
    )
    frame.loc[report_pair & frame["carteira_dc"].le(0), "regra_inclusao"] = (
        "campos reportados; carteira não positiva"
    )
    frame["is_np"] = _as_nullable_bool(
        frame.get("is_np", pd.Series(False, index=frame.index))
    ).fillna(False)
    ex360_observable = frame["reports_inad_acima_360d"].eq(True)  # noqa: E712
    aging_bucket_columns = [
        column
        for column in AGING_VALUE_COLUMNS
        if column != "inad_acima_360d"
    ]
    frame["inad_aging_total"] = frame[aging_bucket_columns].sum(axis=1, min_count=1)
    frame.loc[~frame["reports_aging"].eq(True), "inad_aging_total"] = pd.NA  # noqa: E712
    frame["inadimplencia_ex_360d"] = (
        frame["dc_inadimplentes"] - frame["inad_acima_360d"]
    ).clip(lower=0)
    frame.loc[~ex360_observable, "inadimplencia_ex_360d"] = pd.NA
    frame["inadimplencia_ex_360d_ajustada"] = frame["inadimplencia_ex_360d"].where(
        frame["inadimplencia_ex_360d"].le(nonnegative_dc), nonnegative_dc
    )
    frame.loc[~ex360_observable, "inadimplencia_ex_360d_ajustada"] = pd.NA
    return frame.sort_values(
        ["competencia", "pl", "cnpj_veiculo"], ascending=[True, False, True]
    ).reset_index(drop=True)


def overlay_raw_source_presence(
    base: pd.DataFrame,
    raw_audit_vehicle: pd.DataFrame | None,
) -> pd.DataFrame:
    """Overlay source-presence flags/aging from a fresh raw-CVM extraction.

    Core PL, portfolio and delinquency values remain those of the versioned
    study base so every published total continues to reconcile with the deck.
    The overlay is keyed by competence and reporting CNPJ and therefore also
    quantifies snapshot drift when a freshly downloaded CVM file has added or
    removed vehicles since the versioned extract.
    """

    output = base.copy()
    output["raw_audit_matched"] = False
    output["raw_audit_snapshot"] = ""
    if raw_audit_vehicle is None or raw_audit_vehicle.empty:
        return output
    raw = build_base_by_vehicle(raw_audit_vehicle)
    keys = ["competencia", "cnpj_veiculo"]
    overlay_columns = [
        "reports_tab_i",
        "reports_carteira_dc",
        "reports_dc_inadimplentes",
        "reports_dc_a_vencer_com_parcela_inad",
        "reports_inadimplencia_pair",
        "reports_aging",
        "reports_inad_acima_360d",
        *AGING_VALUE_COLUMNS,
        "inad_aging_total",
        "inadimplencia_ex_360d",
        "inadimplencia_ex_360d_ajustada",
    ]
    raw_overlay = raw[keys + [column for column in overlay_columns if column in raw.columns]].copy()
    raw_overlay = raw_overlay.drop_duplicates(keys)
    raw_overlay["raw_audit_matched"] = True
    raw_overlay["raw_audit_snapshot"] = "download CVM reprocessado com flags pré-coerção"
    rename = {
        column: f"_raw_{column}"
        for column in raw_overlay.columns
        if column not in {*keys, "raw_audit_matched", "raw_audit_snapshot"}
    }
    raw_overlay = raw_overlay.rename(columns=rename)
    output = output.merge(raw_overlay, on=keys, how="left", suffixes=("", "_overlay"))
    matched = output["raw_audit_matched_overlay"].fillna(False).astype(bool)
    for column in overlay_columns:
        raw_column = f"_raw_{column}"
        if raw_column not in output.columns:
            continue
        output.loc[matched, column] = output.loc[matched, raw_column]
        output = output.drop(columns=raw_column)
    output.loc[matched, "field_presence_exact"] = True
    output.loc[matched, "report_flag_source"] = "campo_bruto_CVM_reprocessado"
    output.loc[matched, "raw_audit_matched"] = True
    output.loc[matched, "raw_audit_snapshot"] = output.loc[
        matched, "raw_audit_snapshot_overlay"
    ]
    output = output.drop(
        columns=["raw_audit_matched_overlay", "raw_audit_snapshot_overlay"], errors="ignore"
    )
    return output


def build_delinquency_qa(base: pd.DataFrame) -> pd.DataFrame:
    """Summarize observability, adjustment and sensitivity by competence."""

    rows: list[dict[str, object]] = []
    for competence, group in base.groupby("competencia", sort=True):
        total_n = int(group["cnpj_veiculo"].nunique())
        total_funds = int(group["cnpj_fundo"].nunique())
        total_pl = _sum_min(group["pl"])
        positive = group["carteira_dc"].gt(0)
        reporters = group["reports_inadimplencia_pair"].eq(True)  # noqa: E712
        observed_group = group[reporters]
        observed_positive = group[reporters & positive]
        portfolio_total = _sum_min(group.loc[positive, "carteira_dc"])
        portfolio_observed = _sum_min(observed_positive["carteira_dc"])
        pl_observed = _sum_min(observed_group["pl"])
        raw = _sum_min(observed_group["dc_inadimplentes"])
        adjusted = _sum_min(observed_group["dc_inadimplentes_ajustado_recalculado"])
        excess = _sum_min(observed_group["excesso_removido_ajuste"])
        over = observed_group[observed_group["inad_supera_carteira"]].copy()
        over_positive = over[over["carteira_dc"].gt(0)]
        excess_ranked = pd.to_numeric(over["excesso_removido_ajuste"], errors="coerce").clip(lower=0).sort_values(
            ascending=False
        )
        non_np = observed_group[~observed_group["is_np"].fillna(False)]
        non_over = observed_group[~observed_group["inad_supera_carteira"]]
        aging_observed = observed_group[
            observed_group["reports_inad_acima_360d"].eq(True)  # noqa: E712
        ]
        aging_denominator = _sum_min(aging_observed["carteira_dc"])
        ex360 = _sum_min(aging_observed["inadimplencia_ex_360d"])
        ex360_adjusted = _sum_min(aging_observed["inadimplencia_ex_360d_ajustada"])
        aging_total = _sum_min(aging_observed["inad_aging_total"])
        aging_reported_inad = _sum_min(aging_observed["dc_inadimplentes"])
        exact_flags = bool(group["field_presence_exact"].all())
        exact = group["field_presence_exact"].fillna(False).astype(bool)
        exact_pl = _sum_min(group.loc[exact, "pl"])
        exact_dc = _sum_min(group.loc[exact & positive, "carteira_dc"])

        def ratio(numerator: float, denominator: float) -> float:
            return numerator / denominator if pd.notna(denominator) and denominator != 0 else float("nan")

        aging_coverage = ratio(aging_denominator, portfolio_observed)
        aging_reconciliation = ratio(aging_total, aging_reported_inad)
        if pd.isna(aging_coverage) or aging_coverage < 0.95:
            aging_status = "bloqueado_cobertura_aging_insuficiente"
        elif pd.isna(aging_reconciliation) or not 0.98 <= aging_reconciliation <= 1.02:
            aging_status = "bloqueado_aging_nao_reconcilia_tab_I"
        else:
            aging_status = "publicável"

        rows.append(
            {
                "competencia": competence,
                "veiculos_total": total_n,
                "fundos_total": total_funds,
                "veiculos_com_carteira_positiva": int(group.loc[positive, "cnpj_veiculo"].nunique()),
                "veiculos_com_campos_reportados": int(group.loc[reporters, "cnpj_veiculo"].nunique()),
                "veiculos_incluidos_metrica": int(observed_group["cnpj_veiculo"].nunique()),
                "cobertura_quantidade": len(observed_group) / len(group) if len(group) else float("nan"),
                "pl_total_brl": total_pl,
                "pl_coberto_brl": pl_observed,
                "cobertura_pl": ratio(pl_observed, total_pl),
                "carteira_positiva_total_brl": portfolio_total,
                "carteira_coberta_brl": portfolio_observed,
                "cobertura_carteira": ratio(portfolio_observed, portfolio_total),
                "casos_inad_supera_carteira": int(len(over)),
                "casos_inad_supera_carteira_share_n": len(over) / len(observed_group)
                if len(observed_group)
                else float("nan"),
                "casos_inad_supera_carteira_share_veiculos_total": len(over) / len(group)
                if len(group)
                else float("nan"),
                "casos_inad_supera_carteira_com_carteira_positiva": int(len(over_positive)),
                "casos_inad_supera_carteira_share_carteira_positiva": len(over_positive)
                / len(observed_positive)
                if len(observed_positive)
                else float("nan"),
                "casos_inad_supera_carteira_pl_brl": _sum_min(over["pl"]),
                "casos_inad_supera_carteira_share_pl": ratio(_sum_min(over["pl"]), total_pl),
                "casos_inad_supera_carteira_dc_brl": _sum_min(over["carteira_dc"]),
                "casos_inad_supera_carteira_share_dc": ratio(
                    _sum_min(over["carteira_dc"]), portfolio_total
                ),
                "inadimplencia_bruta_brl": raw,
                "inadimplencia_ajustada_brl": adjusted,
                "excesso_removido_brl": excess,
                "excesso_top1_share": ratio(float(excess_ranked.head(1).sum()), excess),
                "excesso_top5_share": ratio(float(excess_ranked.head(5).sum()), excess),
                "excesso_top10_share": ratio(float(excess_ranked.head(10).sum()), excess),
                "inadimplencia_bruta_pct": ratio(raw, portfolio_observed),
                "inadimplencia_ajustada_pct": ratio(adjusted, portfolio_observed),
                "inadimplencia_ajustada_ex_np_pct": ratio(
                    _sum_min(non_np["dc_inadimplentes_ajustado_recalculado"]),
                    _sum_min(non_np["carteira_dc"]),
                ),
                "sensibilidade_ex_casos_acima_carteira_pct": ratio(
                    _sum_min(non_over["dc_inadimplentes"]),
                    _sum_min(non_over["carteira_dc"]),
                ),
                "veiculos_com_aging_ex360": int(len(aging_observed)),
                "cobertura_carteira_aging_ex360": aging_coverage,
                "aging_inadimplente_total_brl": aging_total,
                "aging_gap_vs_inadimplencia_reportada_brl": aging_total - aging_reported_inad
                if pd.notna(aging_total) and pd.notna(aging_reported_inad)
                else float("nan"),
                "aging_reconciliacao_ratio": aging_reconciliation,
                "aging_publication_status": aging_status,
                "inadimplencia_ex_360d_publicavel": aging_status == "publicável",
                "inadimplencia_ex_360d_pct_sobre_cobertura": ratio(ex360, aging_denominator),
                "inadimplencia_ex_360d_ajustada_pct_sobre_cobertura": ratio(
                    ex360_adjusted, aging_denominator
                ),
                "casos_carteira_negativa": int(group["carteira_dc"].lt(0).sum()),
                "casos_inadimplencia_negativa": int(group["dc_inadimplentes"].lt(0).sum()),
                "presenca_campo_exata": exact_flags,
                "veiculos_com_presenca_campo_exata": int(group.loc[exact, "cnpj_veiculo"].nunique()),
                "cobertura_presenca_campo_exata_n": exact.mean() if len(group) else float("nan"),
                "cobertura_presenca_campo_exata_pl": ratio(exact_pl, total_pl),
                "cobertura_presenca_campo_exata_carteira": ratio(exact_dc, portfolio_total),
                "qualidade_cobertura": "campo bruto CVM"
                if exact_flags
                else "cobertura mista: flags exatas onde houve match com o bruto; legado é limite superior",
            }
        )
    return pd.DataFrame(rows).sort_values("competencia").reset_index(drop=True)


def build_delinquency_cases(base: pd.DataFrame, *, competence: str = LATEST_COMPLETE) -> pd.DataFrame:
    scoped = base[
        base["competencia"].eq(competence) & base["inad_supera_carteira"]
    ].copy()
    scoped = scoped.sort_values(
        ["excesso_removido_ajuste", "pl"], ascending=[False, False]
    ).reset_index(drop=True)
    scoped["rank_excesso"] = range(1, len(scoped) + 1)
    total_excess = _sum_min(scoped["excesso_removido_ajuste"])
    scoped["share_excesso"] = scoped["excesso_removido_ajuste"].div(total_excess)
    scoped["share_excesso_acumulado"] = scoped["share_excesso"].cumsum()
    columns = [
        "rank_excesso",
        "competencia",
        "cnpj_veiculo",
        "cnpj_fundo",
        "cnpj_formatado",
        "cnpj_fundo_formatado",
        "denominacao",
        "pl",
        "carteira_dc",
        "dc_inadimplentes",
        "dc_inadimplentes_ajustado_recalculado",
        "excesso_removido_ajuste",
        "share_excesso",
        "share_excesso_acumulado",
        "is_np",
        "report_flag_source",
    ]
    return scoped[[column for column in columns if column in scoped.columns]]


def build_break_bridge(
    base: pd.DataFrame,
    *,
    from_competence: str = BRIDGE_FROM,
    to_competence: str = BRIDGE_TO,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Explain the month-on-month break at CNPJ level.

    The bridge is additive for raw delinquency, the capped metric, portfolio
    and removed excess.  ``mudança de reporte`` is separated from ordinary
    continuers when the source-presence flags change.
    """

    key = "cnpj_veiculo"
    metrics = {
        "pl": "pl",
        "carteira": "carteira_dc",
        "inad_bruta": "dc_inadimplentes",
        "inad_ajustada": "dc_inadimplentes_ajustado_recalculado",
        "excesso": "excesso_removido_ajuste",
    }
    old = base[base["competencia"].eq(from_competence)].copy().set_index(key, drop=False)
    new = base[base["competencia"].eq(to_competence)].copy().set_index(key, drop=False)
    keys = sorted(set(old.index).union(new.index))
    records: list[dict[str, object]] = []
    for cnpj in keys:
        in_old, in_new = cnpj in old.index, cnpj in new.index
        old_row = old.loc[cnpj] if in_old else None
        new_row = new.loc[cnpj] if in_new else None
        if in_old and in_new:
            report_changed = bool(
                old_row["reports_inadimplencia_pair"]
                != new_row["reports_inadimplencia_pair"]
            )
            bridge_group = "mudança de reporte" if report_changed else "fundos continuantes"
        elif in_new:
            bridge_group = "entradas"
        else:
            bridge_group = "saídas"
        record: dict[str, object] = {
            "competencia_origem": from_competence,
            "competencia_destino": to_competence,
            "bridge_group": bridge_group,
            "cnpj_14": _digits(cnpj),
            "cnpj": format_cnpj(cnpj),
            "cnpj_fundo_14": _digits(
                (new_row if new_row is not None else old_row).get("cnpj_fundo", "")
            ),
            "cnpj_fundo": format_cnpj(
                (new_row if new_row is not None else old_row).get("cnpj_fundo", "")
            ),
            "denominacao": _clean(
                (new_row if new_row is not None else old_row).get("denominacao", "")
            ),
            "reportava_origem": bool(old_row["reports_inadimplencia_pair"])
            if old_row is not None and pd.notna(old_row["reports_inadimplencia_pair"])
            else pd.NA,
            "reportava_destino": bool(new_row["reports_inadimplencia_pair"])
            if new_row is not None and pd.notna(new_row["reports_inadimplencia_pair"])
            else pd.NA,
        }
        for label, column in metrics.items():
            before = pd.to_numeric(
                pd.Series([old_row[column] if old_row is not None else 0]), errors="coerce"
            ).iloc[0]
            after = pd.to_numeric(
                pd.Series([new_row[column] if new_row is not None else 0]), errors="coerce"
            ).iloc[0]
            before = float(before) if pd.notna(before) else 0.0
            after = float(after) if pd.notna(after) else 0.0
            record[f"{label}_origem_brl"] = before
            record[f"{label}_destino_brl"] = after
            record[f"delta_{label}_brl"] = after - before
        records.append(record)
    detail = pd.DataFrame(records)
    if detail.empty:
        return detail, detail
    detail["contribuicao_abs"] = detail[
        ["delta_inad_bruta_brl", "delta_inad_ajustada_brl", "delta_excesso_brl"]
    ].abs().max(axis=1)
    detail = detail.sort_values(["contribuicao_abs", "cnpj"], ascending=[False, True])
    summary = (
        detail.groupby("bridge_group", as_index=False)
        .agg(
            veiculos=("cnpj", "nunique"),
            delta_pl_brl=("delta_pl_brl", "sum"),
            delta_carteira_brl=("delta_carteira_brl", "sum"),
            delta_inad_bruta_brl=("delta_inad_bruta_brl", "sum"),
            delta_inad_ajustada_brl=("delta_inad_ajustada_brl", "sum"),
            delta_excesso_brl=("delta_excesso_brl", "sum"),
        )
        .sort_values("bridge_group")
    )
    summary.insert(0, "competencia_origem", from_competence)
    summary.insert(1, "competencia_destino", to_competence)
    return detail.reset_index(drop=True), summary.reset_index(drop=True)


def _dominant_text_rows(base: pd.DataFrame) -> pd.DataFrame:
    ordered = base.assign(_pl_abs=pd.to_numeric(base["pl"], errors="coerce").abs().fillna(-1))
    return ordered.sort_values(
        ["competencia", "cnpj_fundo", "_pl_abs", "cnpj_veiculo"],
        ascending=[True, True, False, True],
    ).drop_duplicates(["competencia", "cnpj_fundo"])


def build_fund_base(
    base: pd.DataFrame,
    *,
    anbima_classification: pd.DataFrame | None = None,
    published_classifications: pd.DataFrame | None = None,
    latest_complete: str = LATEST_COMPLETE,
) -> pd.DataFrame:
    """Aggregate reporting CNPJs to one legal-fund row and attach ANBIMA provenance."""

    if base.empty:
        return pd.DataFrame()
    keys = ["competencia", "cnpj_fundo"]
    dominant_columns = [
        "denominacao",
        "cnpj_veiculo",
        "admin_nome",
        "admin_cnpj",
        "gestor_nome",
        "gestor_cnpj",
        "custodiante_nome",
        "custodiante_cnpj",
        "segmento_principal",
        "segmento_financeiro_principal",
        "classificacao_anbima",
        "publico_alvo",
    ]
    dominant = _dominant_text_rows(base)
    for column in dominant_columns:
        if column not in dominant.columns:
            dominant[column] = ""
    dominant = dominant[keys + dominant_columns]
    numeric_columns = [
        "pl",
        "carteira_dc",
        "dc_inadimplentes",
        "dc_inadimplentes_ajustado_recalculado",
        "dc_a_vencer_com_parcela_inad",
        *AGING_VALUE_COLUMNS,
        "inad_aging_total",
        "inadimplencia_ex_360d",
        "inadimplencia_ex_360d_ajustada",
    ]
    # Built-in aggregators are material for performance here: the historical
    # panel has more than 200 thousand rows and almost one group per fund-month.
    # Presence flags retain the distinction required to interpret a resulting
    # numeric zero when every source field in a group was absent.
    aggregations: dict[str, tuple[str, object]] = {
        column: (column, "sum") for column in numeric_columns if column in base.columns
    }
    aggregations.update(
        {
            "cnpj_classe_count": ("cnpj_veiculo", "nunique"),
            "cnpj_classes": ("cnpj_veiculo", "first"),
            "is_fic_fidc": ("is_fic_fidc", "max"),
            "is_np": ("is_np", "max"),
            "reports_carteira_dc": ("reports_carteira_dc", "max"),
            "reports_dc_inadimplentes": ("reports_dc_inadimplentes", "max"),
            "reports_inad_acima_360d": ("reports_inad_acima_360d", "max"),
            "field_presence_exact": ("field_presence_exact", "all"),
        }
    )
    grouped = base.groupby(keys, as_index=False).agg(**aggregations)
    funds = grouped.merge(dominant, on=keys, how="left", validate="one_to_one")
    funds["fund_key"] = funds["cnpj_fundo"]
    funds["cnpj_classe"] = funds["cnpj_veiculo"]
    funds["cnpj_fundo_formatado"] = funds["cnpj_fundo"].map(format_cnpj)
    funds["aggregation_warning"] = funds["cnpj_classe_count"].gt(1).map(
        {True: "fundo agregado a partir de mais de um CNPJ reportante", False: ""}
    )
    for column, default in (
        ("tab4_duplicate_detected", False),
        ("tab4_type_conflict", False),
        ("tab4_pl_conflict", False),
        ("tab4_duplicate_rows_dropped", 0),
        ("tab4_warning", ""),
    ):
        funds[column] = default
    # The ANBIMA file is a cadastral snapshot, not a monthly series.  Classify
    # one representative row per legal fund and merge that result back to the
    # historical panel.  Prefer the latest complete competence over the partial
    # tail so new/incomplete June rows do not define the bridge.
    preferred = funds[funds["competencia"].eq(latest_complete)]
    fallback = funds.sort_values(["competencia", "pl"], ascending=[False, False])
    representatives = pd.concat([preferred, fallback], ignore_index=True).drop_duplicates(
        "cnpj_fundo"
    )
    classified_representatives = apply_anbima_classification(
        representatives,
        anbima_classification=anbima_classification,
        published_classifications=published_classifications,
    )
    classification_columns = [
        "anbima_tipo",
        "anbima_foco",
        "classification_tier",
        "classification_status",
        "classification_source",
        "classification_evidence",
        "classification_requires_warning",
        "classification_warning",
    ]
    classified = funds.merge(
        classified_representatives[["cnpj_fundo", *classification_columns]],
        on="cnpj_fundo",
        how="left",
        validate="many_to_one",
    )
    return classified.sort_values(
        ["competencia", "pl", "cnpj_fundo"], ascending=[True, False, True]
    ).reset_index(drop=True)


def build_reconciliation(base: pd.DataFrame, *, competence: str = LATEST_COMPLETE) -> pd.DataFrame:
    scoped = base[base["competencia"].eq(competence)].copy()
    grouped = (
        scoped.groupby("cnpj_fundo", as_index=False)
        .agg(
            veiculos_reportantes=("cnpj_veiculo", "nunique"),
            cnpjs_reportantes=(
                "cnpj_veiculo",
                lambda values: " | ".join(format_cnpj(value) for value in sorted(set(values))),
            ),
            pl_brl=("pl", _sum_min),
        )
        .sort_values(["veiculos_reportantes", "pl_brl"], ascending=[False, False])
    )
    grouped["cnpj_fundo_14"] = grouped["cnpj_fundo"].map(_digits)
    grouped["cnpj_fundo"] = grouped["cnpj_fundo_14"].map(format_cnpj)
    grouped["diferenca_veiculos_menos_fundo"] = grouped["veiculos_reportantes"] - 1
    grouped["universo_veiculos"] = int(scoped["cnpj_veiculo"].nunique())
    grouped["universo_fundos"] = int(scoped["cnpj_fundo"].nunique())
    return grouped.reset_index(drop=True)


def _attach_structure_model(funds: pd.DataFrame) -> pd.DataFrame:
    output = funds.copy()
    provider_groups: list[str] = []
    provider_legal_ids: list[str] = []
    for role, (name_column, cnpj_column) in ROLE_COLUMNS.items():
        group_column = f"{role}_grupo"
        legal_column = f"{role}_cnpj_normalizado"
        output[group_column] = output.get(name_column, pd.Series("", index=output.index)).map(
            canonical_provider
        )
        output[legal_column] = output.get(cnpj_column, pd.Series("", index=output.index)).map(
            _digits
        )
        provider_groups.append(group_column)
        provider_legal_ids.append(legal_column)
    group_known = output[provider_groups].ne("Não informado").all(axis=1)
    legal_known = output[provider_legal_ids].ne("").all(axis=1)
    output["prestadores_ausentes"] = ~group_known
    output["monoestrutura_conglomerado"] = group_known & output[provider_groups].nunique(axis=1).eq(1)
    output["monoestrutura_entidade_legal"] = legal_known & output[provider_legal_ids].nunique(axis=1).eq(1)
    output["definicao_mono_adotada"] = "mesmo conglomerado econômico normalizado"
    output["grupo_mono"] = output["administrador_grupo"].where(
        output["monoestrutura_conglomerado"], ""
    )
    output["modelo_prestacao"] = "Três prestadores distintos"
    output.loc[output["prestadores_ausentes"], "modelo_prestacao"] = "Dados incompletos"
    output.loc[output["monoestrutura_conglomerado"], "modelo_prestacao"] = "Monoestrutura"
    adm_gest = output["administrador_grupo"].eq(output["gestor_grupo"])
    adm_cust = output["administrador_grupo"].eq(output["custodiante_grupo"])
    gest_cust = output["gestor_grupo"].eq(output["custodiante_grupo"])
    known_non_mono = group_known & ~output["monoestrutura_conglomerado"]
    output.loc[known_non_mono & adm_gest, "modelo_prestacao"] = "Administração + Gestão"
    output.loc[known_non_mono & adm_cust, "modelo_prestacao"] = "Administração + Custódia"
    output.loc[known_non_mono & gest_cust, "modelo_prestacao"] = "Gestão + Custódia"
    return output


def build_top20_and_monostructure(
    fund_base: pd.DataFrame,
    *,
    competence: str = LATEST_COMPLETE,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    latest = fund_base[fund_base["competencia"].eq(competence)].copy()
    latest = _attach_structure_model(latest)
    latest["pl"] = pd.to_numeric(latest["pl"], errors="coerce")
    ex_fic = latest[~latest["is_fic_fidc"].fillna(False)].copy()
    denominator = _sum_min(ex_fic["pl"])
    ranked = ex_fic.sort_values(["pl", "cnpj_fundo"], ascending=[False, True]).reset_index(drop=True)
    ranked["rank"] = range(1, len(ranked) + 1)
    ranked["market_share_ex_fic"] = ranked["pl"].div(denominator)
    top20 = ranked.head(20).copy()
    top20["is_top20_fidc"] = True
    if len(ranked) >= 20 and len(top20) != 20:
        raise AssertionError("Top 20 FIDCs não contém exatamente 20 fundos")

    outros = ranked[ranked["anbima_tipo"].eq("Outros")].head(20).copy()
    outros["rank_outros"] = range(1, len(outros) + 1)
    outros_total = _sum_min(ranked.loc[ranked["anbima_tipo"].eq("Outros"), "pl"])
    outros["market_share_outros"] = outros["pl"].div(outros_total)

    latest["is_top20_fidc"] = latest["cnpj_fundo"].isin(set(top20["cnpj_fundo"]))
    mono_funds = latest[latest["monoestrutura_conglomerado"]].copy()
    concentration_rows: list[dict[str, object]] = []
    for group_name, group in mono_funds.groupby("grupo_mono", sort=True):
        ordered = group.sort_values(["pl", "cnpj_fundo"], ascending=[False, True])
        total = _sum_min(ordered["pl"])
        positive_total = float(pd.to_numeric(ordered["pl"], errors="coerce").clip(lower=0).sum())
        shares = pd.to_numeric(ordered["pl"], errors="coerce").clip(lower=0).div(positive_total)
        largest = ordered.iloc[0]
        concentration_rows.append(
            {
                "grupo_economico": group_name,
                "pl_mono_brl": total,
                "fundos_mono": int(ordered["cnpj_fundo"].nunique()),
                "maior_fundo": largest["denominacao"],
                "maior_fundo_cnpj": format_cnpj(largest["cnpj_fundo"]),
                "maior_fundo_pl_brl": float(largest["pl"]),
                "maior_fundo_share": float(largest["pl"]) / total if total else float("nan"),
                "top3_share": float(shares.head(3).sum()),
                "top5_share": float(shares.head(5).sum()),
                "top10_share": float(shares.head(10).sum()),
                "hhi_fundos": float((shares**2).sum()),
                "fundos_top20": int(ordered["is_top20_fidc"].sum()),
                "pl_top20_brl": _sum_min(ordered.loc[ordered["is_top20_fidc"], "pl"]),
            }
        )
    concentration = pd.DataFrame(concentration_rows)
    if not concentration.empty:
        concentration = concentration.sort_values("pl_mono_brl", ascending=False).reset_index(drop=True)
        concentration["rank_pl_mono"] = range(1, len(concentration) + 1)
    return top20.reset_index(drop=True), outros.reset_index(drop=True), latest.reset_index(drop=True), concentration


def build_market_share_by_subtype(
    fund_base: pd.DataFrame,
    *,
    competence: str = LATEST_COMPLETE,
    top_n: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build 100% stacks using one fixed Top 10 per provider role.

    Invalid role × focus combinations remain in the output with
    ``publication_status`` set to a blocking reason.  They are not silently
    repaired by hiding negative PL or by moving missing providers to Outros.
    """

    latest = fund_base[
        fund_base["competencia"].eq(competence) & ~fund_base["is_fic_fidc"].fillna(False)
    ].copy()
    latest["pl"] = pd.to_numeric(latest["pl"], errors="coerce")
    focus_pairs = [
        (anbima_type, focus)
        for anbima_type, focuses in ANBIMA_FOCUS_BY_TYPE.items()
        for focus in focuses
    ]
    rows: list[dict[str, object]] = []
    top_rows: list[dict[str, object]] = []
    for role, (name_column, _) in ROLE_COLUMNS.items():
        role_frame = latest.copy()
        role_frame["participant"] = role_frame.get(
            name_column, pd.Series("", index=role_frame.index)
        ).map(canonical_provider)
        overall = (
            role_frame[role_frame["participant"].ne("Não informado")]
            .groupby("participant", as_index=False)
            .agg(pl_brl=("pl", _sum_min), funds=("cnpj_fundo", "nunique"))
            .sort_values(["pl_brl", "participant"], ascending=[False, True])
            .head(top_n)
            .reset_index(drop=True)
        )
        fixed_top = overall["participant"].tolist()
        for rank, item in enumerate(overall.itertuples(index=False), start=1):
            top_rows.append(
                {
                    "competencia": competence,
                    "papel": role,
                    "rank_top10_geral": rank,
                    "participante": item.participant,
                    "pl_brl": float(item.pl_brl),
                    "fundos": int(item.funds),
                }
            )
        for type_order, (anbima_type, focus) in enumerate(focus_pairs, start=1):
            scoped = role_frame[
                role_frame["anbima_tipo"].eq(anbima_type)
                & role_frame["anbima_foco"].eq(focus)
            ].copy()
            denominator = _sum_min(scoped["pl"])
            grouped = scoped.groupby("participant")["pl"].apply(_sum_min).to_dict()
            category_values: list[tuple[str, float, int, str]] = []
            for rank, participant in enumerate(fixed_top, start=1):
                category_values.append(
                    (participant, float(grouped.get(participant, 0.0)), rank, "Top 10 geral")
                )
            identified_other = _sum_min(
                scoped.loc[
                    scoped["participant"].ne("Não informado")
                    & ~scoped["participant"].isin(fixed_top),
                    "pl",
                ]
            )
            if pd.isna(identified_other):
                identified_other = 0.0
            not_informed = _sum_min(
                scoped.loc[scoped["participant"].eq("Não informado"), "pl"]
            )
            if pd.isna(not_informed):
                not_informed = 0.0
            category_values.extend(
                [
                    ("Outros identificados", identified_other, top_n + 1, "residual identificado"),
                    ("Prestador não informado", not_informed, top_n + 2, "campo ausente"),
                ]
            )
            category_sum = sum(value for _, value, _, _ in category_values)
            negative_funds = int(scoped["pl"].lt(0).sum())
            negative_pl_brl = _sum_min(scoped.loc[scoped["pl"].lt(0), "pl"])
            if pd.isna(negative_pl_brl):
                negative_pl_brl = 0.0
            negative_categories = sum(value < -1e-6 for _, value, _, _ in category_values)
            coverage = (
                (denominator - not_informed) / denominator
                if pd.notna(denominator) and denominator != 0
                else float("nan")
            )
            if pd.isna(denominator) or denominator <= 0:
                status = "bloqueado_sem_denominador_positivo"
            elif negative_categories:
                status = "bloqueado_pl_negativo"
            elif coverage > 1.000001 or coverage < -0.000001:
                status = "bloqueado_cobertura_fora_de_0_100"
            elif abs(category_sum - denominator) > max(1.0, abs(denominator) * 1e-9):
                status = "bloqueado_nao_reconcilia_denominador"
            elif negative_funds:
                status = "publicável_com_nota_pl_negativo"
            else:
                status = "publicável"
            for participant, value, stack_order, bucket_kind in category_values:
                rows.append(
                    {
                        "competencia": competence,
                        "papel": role,
                        "tipo_anbima": anbima_type,
                        "foco_anbima": focus,
                        "foco_order": type_order,
                        "participante_bucket": participant,
                        "bucket_kind": bucket_kind,
                        "stack_order": stack_order,
                        "pl_brl": value,
                        "denominador_pl_subtipo_brl": denominator,
                        "share_subtipo": value / denominator
                        if pd.notna(denominator) and denominator != 0
                        else float("nan"),
                        "pl_identificado_brl": denominator - not_informed
                        if pd.notna(denominator)
                        else float("nan"),
                        "cobertura_prestador_pl": coverage,
                        "fundos_subtipo": int(scoped["cnpj_fundo"].nunique()),
                        "fundos_pl_negativo": negative_funds,
                        "pl_negativo_brl": negative_pl_brl,
                        "pl_negativo_share_denominador": negative_pl_brl / denominator
                        if pd.notna(denominator) and denominator != 0
                        else float("nan"),
                        "quality_note": (
                            f"{negative_funds} fundo(s) com PL negativo, total de R$ {negative_pl_brl:,.2f}; "
                            "categorias agregadas permanecem não negativas e reconciliam o denominador"
                            if negative_funds and not negative_categories
                            else "categoria agregada com PL negativo; não publicar"
                            if negative_categories
                            else ""
                        ),
                        "publication_status": status,
                        "fechamento_100_pct": category_sum / denominator
                        if pd.notna(denominator) and denominator != 0
                        else float("nan"),
                    }
                )
    market = pd.DataFrame(rows)
    top10 = pd.DataFrame(top_rows)
    return market, top10


def build_market_share_scope_summary(
    fund_base: pd.DataFrame,
    market_share: pd.DataFrame,
    *,
    competence: str = LATEST_COMPLETE,
) -> pd.DataFrame:
    """Summarize what sits inside and outside the 14-focus market-share scope."""

    latest = fund_base[
        fund_base["competencia"].eq(competence) & ~fund_base["is_fic_fidc"].fillna(False)
    ].copy()
    latest["pl"] = pd.to_numeric(latest["pl"], errors="coerce")
    valid_pairs = {
        (anbima_type, focus)
        for anbima_type, focuses in ANBIMA_FOCUS_BY_TYPE.items()
        for focus in focuses
    }
    in_focus_scope = pd.Series(
        [
            (anbima_type, focus) in valid_pairs
            for anbima_type, focus in zip(latest["anbima_tipo"], latest["anbima_foco"])
        ],
        index=latest.index,
    )
    total_pl = _sum_min(latest["pl"])
    scope_pl = _sum_min(latest.loc[in_focus_scope, "pl"])
    rows: list[dict[str, object]] = []
    combinations = market_share[
        ["papel", "tipo_anbima", "foco_anbima", "publication_status"]
    ].drop_duplicates()
    for role, (name_column, _) in ROLE_COLUMNS.items():
        participant = latest.get(name_column, pd.Series("", index=latest.index)).map(
            canonical_provider
        )
        known = participant.ne("Não informado")
        known_scope_pl = _sum_min(latest.loc[in_focus_scope & known, "pl"])
        role_combinations = combinations[combinations["papel"].eq(role)]
        rows.append(
            {
                "competencia": competence,
                "papel": role,
                "pl_total_ex_fic_brl": total_pl,
                "pl_nos_14_focos_brl": scope_pl,
                "cobertura_classificacao_14_focos_pl": scope_pl / total_pl
                if total_pl
                else float("nan"),
                "pl_fora_14_focos_nd_brl": total_pl - scope_pl,
                "fundos_total_ex_fic": int(latest["cnpj_fundo"].nunique()),
                "fundos_nos_14_focos": int(latest.loc[in_focus_scope, "cnpj_fundo"].nunique()),
                "focos_taxonomia": len(valid_pairs),
                "focos_com_pl": int(
                    role_combinations[
                        role_combinations["publication_status"].ne(
                            "bloqueado_sem_denominador_positivo"
                        )
                    ]["foco_anbima"].nunique()
                ),
                "pl_prestador_identificado_nos_14_focos_brl": known_scope_pl,
                "cobertura_prestador_nos_14_focos_pl": known_scope_pl / scope_pl
                if scope_pl
                else float("nan"),
                "combinacoes_bloqueadas": int(
                    role_combinations["publication_status"].str.startswith("bloqueado").sum()
                ),
                "combinacoes_com_nota_pl_negativo": int(
                    role_combinations["publication_status"].eq(
                        "publicável_com_nota_pl_negativo"
                    ).sum()
                ),
            }
        )
    return pd.DataFrame(rows)


def build_classification_coverage(
    fund_base: pd.DataFrame,
    *,
    competence: str = LATEST_COMPLETE,
) -> pd.DataFrame:
    """Reconcile classification provenance to the ex-FIC denominator."""

    latest = fund_base[fund_base["competencia"].eq(competence)].copy()
    latest["pl"] = pd.to_numeric(latest["pl"], errors="coerce")
    ex_fic = latest[~latest["is_fic_fidc"].fillna(False)]
    denominator = _sum_min(ex_fic["pl"])
    tier_labels = {
        "oficial_anbima": "Oficial ANBIMA",
        "evidencia_publicada": "Evidência documental/publicada",
        "proxy_cvm": "Proxy CVM",
        "nao_disponivel": "N/D",
    }
    rows: list[dict[str, object]] = []
    for order, (tier, label) in enumerate(tier_labels.items(), start=1):
        scoped = ex_fic[ex_fic["classification_tier"].eq(tier)]
        pl_brl = _sum_min(scoped["pl"])
        rows.append(
            {
                "competencia": competence,
                "tier_order": order,
                "classification_tier": tier,
                "origem_classificacao": label,
                "fundos": int(scoped["cnpj_fundo"].nunique()),
                "pl_brl": pl_brl,
                "denominador_pl_ex_fic_brl": denominator,
                "cobertura_pl_ex_fic": pl_brl / denominator if denominator else float("nan"),
                "data_referencia_classificacao": "mai/26; fotografia ANBIMA de dez/25 quando oficial",
            }
        )
    output = pd.DataFrame(rows)
    output["fechamento_cobertura"] = output["pl_brl"].sum() / denominator if denominator else float("nan")
    return output


@dataclass(frozen=True)
class RevisionOutputs:
    latest_complete: str
    raw_source_presence: pd.DataFrame
    base_vehicle: pd.DataFrame
    qa_delinquency: pd.DataFrame
    delinquency_cases: pd.DataFrame
    bridge_detail: pd.DataFrame
    bridge_summary: pd.DataFrame
    reconciliation: pd.DataFrame
    fund_base: pd.DataFrame
    top20_fidcs: pd.DataFrame
    top20_outros: pd.DataFrame
    monostructure_funds: pd.DataFrame
    monostructure_concentration: pd.DataFrame
    market_share_subtype: pd.DataFrame
    market_share_fixed_top10: pd.DataFrame
    market_share_scope_summary: pd.DataFrame
    classification_coverage: pd.DataFrame


def build_revision_outputs(
    *,
    vehicle_monthly: pd.DataFrame,
    anbima_classification: pd.DataFrame | None = None,
    published_classifications: pd.DataFrame | None = None,
    raw_audit_vehicle: pd.DataFrame | None = None,
    latest_complete: str = LATEST_COMPLETE,
) -> RevisionOutputs:
    base = build_base_by_vehicle(vehicle_monthly)
    base = overlay_raw_source_presence(base, raw_audit_vehicle)
    qa = build_delinquency_qa(base)
    cases = build_delinquency_cases(base, competence=latest_complete)
    bridge_detail, bridge_summary = build_break_bridge(base)
    reconciliation = build_reconciliation(base, competence=latest_complete)
    fund_base = build_fund_base(
        base,
        anbima_classification=anbima_classification,
        published_classifications=published_classifications,
        latest_complete=latest_complete,
    )
    top20, top20_outros, structured_funds, concentration = build_top20_and_monostructure(
        fund_base, competence=latest_complete
    )
    market, fixed_top10 = build_market_share_by_subtype(
        fund_base, competence=latest_complete
    )
    market_scope = build_market_share_scope_summary(
        fund_base, market, competence=latest_complete
    )
    classification_coverage = build_classification_coverage(
        fund_base, competence=latest_complete
    )
    return RevisionOutputs(
        latest_complete=latest_complete,
        raw_source_presence=(
            raw_audit_vehicle.copy()
            if raw_audit_vehicle is not None
            else pd.DataFrame()
        ),
        base_vehicle=base,
        qa_delinquency=qa,
        delinquency_cases=cases,
        bridge_detail=bridge_detail,
        bridge_summary=bridge_summary,
        reconciliation=reconciliation,
        fund_base=fund_base,
        top20_fidcs=top20,
        top20_outros=top20_outros,
        monostructure_funds=structured_funds,
        monostructure_concentration=concentration,
        market_share_subtype=market,
        market_share_fixed_top10=fixed_top10,
        market_share_scope_summary=market_scope,
        classification_coverage=classification_coverage,
    )


def write_revision_outputs(outputs: RevisionOutputs, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    table_specs: tuple[tuple[str, pd.DataFrame, bool], ...] = (
        ("source_presence_overlay.csv.gz", outputs.raw_source_presence, True),
        ("base_competencia_cnpj.csv.gz", outputs.base_vehicle, True),
        ("qa_inadimplencia_competencia.csv", outputs.qa_delinquency, False),
        ("qa_inadimplencia_casos_latest.csv", outputs.delinquency_cases, False),
        ("bridge_inadimplencia_2024-06_2024-07_detalhe.csv", outputs.bridge_detail, False),
        ("bridge_inadimplencia_2024-06_2024-07_resumo.csv", outputs.bridge_summary, False),
        ("reconciliacao_veiculo_fundo_latest.csv", outputs.reconciliation, False),
        ("base_fundo_cnpj.csv.gz", outputs.fund_base, True),
        ("top20_fidcs.csv", outputs.top20_fidcs, False),
        ("top20_outros.csv", outputs.top20_outros, False),
        ("monoestrutura_por_fundo.csv", outputs.monostructure_funds, False),
        ("monoestrutura_concentracao.csv", outputs.monostructure_concentration, False),
        ("market_share_por_subtipo.csv", outputs.market_share_subtype, False),
        ("market_share_top10_fixo.csv", outputs.market_share_fixed_top10, False),
        ("market_share_escopo_resumo.csv", outputs.market_share_scope_summary, False),
        ("cobertura_classificacao.csv", outputs.classification_coverage, False),
    )
    files: dict[str, dict[str, object]] = {}
    for filename, frame, compressed in table_specs:
        path = output_dir / filename
        frame.to_csv(path, index=False, compression="gzip" if compressed else None)
        files[filename] = {"rows": int(len(frame)), "columns": int(len(frame.columns))}

    def records(frame: pd.DataFrame, columns: Iterable[str] | None = None) -> list[dict[str, object]]:
        selected = frame.copy()
        if columns is not None:
            selected = selected[[column for column in columns if column in selected.columns]]
        for column in selected.columns:
            if column == "cnpj_fundo" or column == "cnpj_veiculo" or column.endswith("_14"):
                selected[column] = selected[column].map(_digits)
        return json.loads(selected.to_json(orient="records", force_ascii=False, date_format="iso"))

    top20_columns = (
        "rank",
        "rank_outros",
        "cnpj_fundo",
        "cnpj_fundo_formatado",
        "denominacao",
        "pl",
        "market_share_ex_fic",
        "market_share_outros",
        "anbima_tipo",
        "anbima_foco",
        "classification_tier",
        "classification_status",
        "classification_source",
        "admin_nome",
        "gestor_nome",
        "custodiante_nome",
        "modelo_prestacao",
        "monoestrutura_conglomerado",
        "monoestrutura_entidade_legal",
    )
    mono_columns = (
        "cnpj_fundo",
        "cnpj_fundo_formatado",
        "denominacao",
        "pl",
        "administrador_grupo",
        "gestor_grupo",
        "custodiante_grupo",
        "modelo_prestacao",
        "monoestrutura_conglomerado",
        "monoestrutura_entidade_legal",
        "prestadores_ausentes",
        "is_top20_fidc",
    )
    payload = {
        "schema_version": "fidc_industry_revision_v1",
        "cnpj_encoding": "string de 14 dígitos; zeros à esquerda preservados",
        "latest_complete": outputs.latest_complete,
        "qa_inadimplencia": records(outputs.qa_delinquency),
        "bridge_resumo": records(outputs.bridge_summary),
        "bridge_top_contribuidores": records(outputs.bridge_detail.head(30)),
        "reconciliacao_multiveiculo": records(
            outputs.reconciliation[outputs.reconciliation["veiculos_reportantes"].gt(1)]
        ),
        "top20_fidcs": records(outputs.top20_fidcs, top20_columns),
        "top20_outros": records(outputs.top20_outros, top20_columns),
        "monoestrutura_por_fundo": records(outputs.monostructure_funds, mono_columns),
        "monoestrutura_concentracao": records(outputs.monostructure_concentration),
        "market_share_top10_fixo": records(outputs.market_share_fixed_top10),
        "market_share_por_subtipo": records(outputs.market_share_subtype),
        "market_share_escopo_resumo": records(outputs.market_share_scope_summary),
        "cobertura_classificacao": records(outputs.classification_coverage),
    }
    payload_path = output_dir / "deck_workbook_payload.json"
    payload_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    files[payload_path.name] = {
        "rows": sum(
            len(value) for value in payload.values() if isinstance(value, list)
        ),
        "columns": "schema por bloco",
    }

    latest_qa = outputs.qa_delinquency[
        outputs.qa_delinquency["competencia"].eq(outputs.latest_complete)
    ]
    reconciliation = outputs.reconciliation
    manifest: dict[str, object] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "latest_complete": outputs.latest_complete,
        "definitions": {
            "vehicle": "CNPJ reportante do Informe Mensal (fundo ou classe, conforme regime)",
            "fund": "CNPJ do fundo no cadastro; classes são agregadas por competência",
            "monostructure": "mesmo conglomerado econômico normalizado para administração, gestão e custódia",
            "delinquency_adjustment": (
                "min(max(inadimplência reportada, 0), "
                "max(carteira de direitos creditórios, 0)) por veículo"
            ),
            "market_share_subtype_denominator": "PL total do Tipo + Foco ANBIMA, incluindo prestador não informado",
        },
        "files": files,
        "checks": {
            "top20_fidcs_rows": int(len(outputs.top20_fidcs)),
            "top20_outros_rows": int(len(outputs.top20_outros)),
            "market_share_roles": int(outputs.market_share_subtype["papel"].nunique()),
            "market_share_foci": int(outputs.market_share_subtype["foco_anbima"].nunique()),
            "blocked_market_share_combinations": int(
                outputs.market_share_subtype.loc[
                    outputs.market_share_subtype["publication_status"].str.startswith("bloqueado"),
                    ["papel", "tipo_anbima", "foco_anbima"],
                ].drop_duplicates().shape[0]
            ),
            "latest_vehicles": int(reconciliation["universo_veiculos"].iloc[0])
            if not reconciliation.empty
            else 0,
            "latest_funds": int(reconciliation["universo_fundos"].iloc[0])
            if not reconciliation.empty
            else 0,
            "latest_presence_exact": bool(latest_qa["presenca_campo_exata"].iloc[0])
            if not latest_qa.empty
            else False,
            "latest_aging_publication_status": str(
                latest_qa["aging_publication_status"].iloc[0]
            )
            if not latest_qa.empty
            else "indisponível",
        },
        "limitations": [
            (
                "Materializações antigas de vehicle_monthly converteram vazios em zero; "
                "nesses meses, presença por campo é um limite superior inferido da linha da Tabela I."
            ),
            (
                "Buckets de aging e a sensibilidade ex-360 exigem presença no bruto e "
                "reconciliação entre Tabelas V/VI e a inadimplência da Tabela I; mai/26 "
                "não passa esse teste e permanece diagnóstico, não headline."
            ),
            (
                "Gestor e custodiante históricos vêm do cadastro vigente e não "
                "constituem série histórica like-for-like."
            ),
            (
                "Monoestrutura mede coincidência de conglomerado normalizado; "
                "não demonstra preço, contrato ou venda casada."
            ),
        ],
    }
    (output_dir / "revision_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


__all__ = [
    "BRIDGE_FROM",
    "BRIDGE_TO",
    "LATEST_COMPLETE",
    "RevisionOutputs",
    "add_reporting_flags",
    "build_base_by_vehicle",
    "build_break_bridge",
    "build_delinquency_cases",
    "build_delinquency_qa",
    "build_fund_base",
    "build_market_share_by_subtype",
    "build_market_share_scope_summary",
    "build_classification_coverage",
    "overlay_raw_source_presence",
    "build_reconciliation",
    "build_revision_outputs",
    "build_top20_and_monostructure",
    "format_cnpj",
    "write_revision_outputs",
]
