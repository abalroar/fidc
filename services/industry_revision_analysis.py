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
from services.industry_revision_additions import (
    build_acquiring_reclassified_cvm_mix,
    build_fixed_bank_fidc_cohort_detail,
    build_fixed_bank_fidc_cohort_history,
    build_independent_provider_historical_ranking,
)


LATEST_COMPLETE = "2026-06"
BRIDGE_FROM = "2024-06"
BRIDGE_TO = "2024-07"
PROVIDER_TRANSITION_FROM = "2024-12"
PROVIDER_TRANSITION_TO = LATEST_COMPLETE
REAG_COHORT_FROM = "2025-12"
REAG_COHORT_TO = LATEST_COMPLETE
REAG_CBSF_ADMIN_CNPJ = "34829992000186"
QI_LEGACY_SINGULARE_CNPJ = "62285390000140"
QI_ORIGINAL_DTVM_CNPJ = "46955383000152"
BTG_CONTROLLED_FIDCS: Mapping[str, str] = {
    "52242420000188": "BTG Pactual Consignados II FIDC",
    "50906397000153": "BTG Pactual Consignados FIDC",
    "29225241000110": "FIDC Alternative Assets III",
    "60010416000112": "MT Consignado Privado I FIDC",
    "24194675000187": "FIDC Alternative Assets I",
    "54871427000194": "Consignado Delta Receivables I FIDC",
}
BTG_IFRS_1Q26_URL = (
    "https://d169uzu5o4xu1k.cloudfront.net/"
    "78a5a309-f13a-41ed-a7d1-814e37b63259/2026/"
    "03dec8c5-4ac7-4de5-89b5-2bad97ed63cc.pdf"
)
QI_SINGULARE_ACQUISITION_URL = (
    "https://qitech.com.br/newsroom/"
    "qi-tech-faz-aquisicao-da-singulare-corretora-lider-em-fidcs/"
)
QI_REORGANIZATION_BCB_URL = (
    "https://www.bcb.gov.br/content/estabilidadefinanceira/evolucaosfnmes/"
    "202511%20-%20Quadro%2004%20-%20Autoriza%C3%A7%C3%B5es%20e%20"
    "altera%C3%A7%C3%B5es%20societ%C3%A1rias%20-%20principais%20ocorr%C3%AAncias.pdf"
)
REAG_LIQUIDATION_BCB_URL = (
    "https://www.bcb.gov.br/estabilidadefinanceira/"
    "exibenormativo?numero=1375&tipo=Ato+do+Presidente"
)
FUNDOSNET_MANAGER_URL = (
    "https://fnet.bmfbovespa.com.br/fnet/publico/"
    "abrirGerenciadorDocumentosCVM?cnpjFundo={cnpj}"
)
MARKET_SHARE_EXCLUDED_FUNDS: Mapping[str, str] = {
    "09195235000150": "FIDC Sistema Petrobras",
    "26287464000114": "FIDC TAPSO",
}
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
TABLE_II_RECEIVABLE_COLUMNS: Mapping[str, str] = {
    "table_ii_industrial_brl": "Industrial",
    "table_ii_imobiliario_brl": "Imobiliário",
    "table_ii_comercial_brl": "Comercial",
    "table_ii_servicos_brl": "Serviços",
    "table_ii_agronegocio_brl": "Agronegócio",
    "table_ii_financeiro_brl": "Financeiro",
    "table_ii_cartao_credito_brl": "Cartão de crédito",
    "table_ii_factoring_brl": "Factoring",
    "table_ii_setor_publico_brl": "Setor público",
    "table_ii_acoes_judiciais_brl": "Ações judiciais",
    "table_ii_marcas_patentes_brl": "Marcas e patentes",
}


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


def fundosnet_fund_url(value: object) -> str:
    """Return the public Fundos.NET document-manager link for a fund CNPJ."""

    cnpj = _digits(value)
    return FUNDOSNET_MANAGER_URL.format(cnpj=cnpj) if cnpj else ""


def cvm_monthly_source_url(competence: str) -> str:
    """Return the official CVM ZIP used for a monthly FIDC competence."""

    yyyymm = re.sub(r"\D", "", str(competence))[:6]
    if len(yyyymm) != 6:
        return ""
    return (
        "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/"
        f"inf_mensal_fidc_{yyyymm}.zip"
    )


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = re.sub(r"\s+", " ", str(value).strip())
    return "" if text.lower() in {"", "nan", "none", "nat", "n/d"} else text


def exclude_market_share_funds(
    frame: pd.DataFrame,
    *,
    excluded_fund_cnpjs: Iterable[str] = MARKET_SHARE_EXCLUDED_FUNDS,
) -> pd.DataFrame:
    """Remove the funds explicitly excluded from provider-share universes."""

    if frame is None:
        return pd.DataFrame()
    if frame.empty or "cnpj_fundo" not in frame.columns:
        return frame.copy()
    excluded = {_digits(value) for value in excluded_fund_cnpjs if _digits(value)}
    return frame.loc[~frame["cnpj_fundo"].map(_digits).isin(excluded)].copy()


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
    inferred_tab_i = pd.Series(False, index=frame.index, dtype="boolean")
    for column in ("admin_nome", "admin_cnpj", "condominio", "exclusivo"):
        if column in frame.columns:
            inferred_tab_i |= frame[column].map(_clean).ne("").astype("boolean")
    if "reports_tab_i" in frame.columns:
        tab_i = _as_nullable_bool(frame["reports_tab_i"]).fillna(inferred_tab_i)
    else:
        tab_i = inferred_tab_i
    frame["reports_tab_i"] = tab_i

    exact_pair = pd.Series(True, index=frame.index, dtype="boolean")

    for column in (
        "reports_carteira_dc",
        "reports_dc_inadimplentes",
        "reports_dc_a_vencer_com_parcela_inad",
    ):
        if column in frame.columns:
            reported = _as_nullable_bool(frame[column])
            if column in {"reports_carteira_dc", "reports_dc_inadimplentes"}:
                exact_pair &= reported.notna().astype("boolean")
            frame[column] = reported.fillna(tab_i)
        else:
            # Field-level presence was lost in the old CSV.  Table-I row
            # presence is useful as an upper bound, not as an exact claim.
            frame[column] = tab_i.copy()
            if column in {"reports_carteira_dc", "reports_dc_inadimplentes"}:
                exact_pair &= False

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
    frame.loc[empty_source & exact_pair, "report_flag_source"] = "campo_bruto_CVM"
    frame.loc[empty_source & ~exact_pair, "report_flag_source"] = (
        "presença_da_linha_Tab_I_inferida_no_legado"
    )
    frame["field_presence_exact"] = exact_pair
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
    # The overlay changes observability flags and can also replace aging
    # values.  Rebuild every dependent audit field after the replacement;
    # carrying derivatives calculated before the merge creates internally
    # inconsistent snapshots (for example, an observed excess with zero
    # `inad_supera_carteira`).
    report_pair = (
        _as_nullable_bool(output["reports_carteira_dc"]).eq(True)  # noqa: E712
        & _as_nullable_bool(output["reports_dc_inadimplentes"]).eq(True)  # noqa: E712
    )
    output["reports_inadimplencia_pair"] = report_pair.astype("boolean")
    output["carteira_positiva"] = output["carteira_dc"].gt(0)
    output["inad_supera_carteira"] = (
        report_pair & output["dc_inadimplentes"].gt(output["carteira_dc"])
    )
    nonnegative_inad = output["dc_inadimplentes"].clip(lower=0)
    nonnegative_dc = output["carteira_dc"].clip(lower=0)
    output["dc_inadimplentes_ajustado_recalculado"] = nonnegative_inad.where(
        nonnegative_inad.le(nonnegative_dc), nonnegative_dc
    )
    output.loc[
        ~report_pair, "dc_inadimplentes_ajustado_recalculado"
    ] = pd.NA
    output["excesso_removido_ajuste"] = (
        nonnegative_inad - output["dc_inadimplentes_ajustado_recalculado"]
    ).clip(lower=0)
    output.loc[~report_pair, "excesso_removido_ajuste"] = pd.NA
    output["motivo_ajuste"] = "sem ajuste"
    output.loc[output["inad_supera_carteira"], "motivo_ajuste"] = (
        "inadimplência reportada supera a carteira; limite aplicado por veículo"
    )
    output.loc[~report_pair, "motivo_ajuste"] = "campos não observáveis em conjunto"
    output["regra_inclusao"] = "fora do denominador"
    output.loc[report_pair & output["carteira_dc"].gt(0), "regra_inclusao"] = (
        "campos reportados e carteira positiva"
    )
    output.loc[report_pair & output["carteira_dc"].le(0), "regra_inclusao"] = (
        "campos reportados; carteira não positiva"
    )
    aging_bucket_columns = [
        column for column in AGING_VALUE_COLUMNS if column != "inad_acima_360d"
    ]
    output["inad_aging_total"] = output[aging_bucket_columns].sum(
        axis=1, min_count=1
    )
    output.loc[
        ~_as_nullable_bool(output["reports_aging"]).eq(True), "inad_aging_total"  # noqa: E712
    ] = pd.NA
    ex360_observable = _as_nullable_bool(output["reports_inad_acima_360d"]).eq(
        True  # noqa: E712
    )
    output["inadimplencia_ex_360d"] = (
        output["dc_inadimplentes"] - output["inad_acima_360d"]
    ).clip(lower=0)
    output.loc[~ex360_observable, "inadimplencia_ex_360d"] = pd.NA
    output["inadimplencia_ex_360d_ajustada"] = output[
        "inadimplencia_ex_360d"
    ].where(output["inadimplencia_ex_360d"].le(nonnegative_dc), nonnegative_dc)
    output.loc[~ex360_observable, "inadimplencia_ex_360d_ajustada"] = pd.NA
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


def build_single_receivable_delinquency(
    base_vehicle: pd.DataFrame,
    fund_base: pd.DataFrame,
    raw_table_ii_vehicle: pd.DataFrame | None,
    *,
    competence: str = LATEST_COMPLETE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate delinquency/PL for funds with one top-level Table-II type.

    Eligibility is assessed after aggregating every reporting class to the
    legal fund CNPJ.  Exactly one of the 11 Table-II fields must be non-zero.
    FIC-FIDCs, non-positive PL, missing portfolio/delinquency pairs and cases
    where reported delinquency exceeds the total portfolio are removed.
    """

    value_columns = list(TABLE_II_RECEIVABLE_COLUMNS)
    result_columns = [
        "competencia",
        "tipo_recebivel_tabela_ii",
        "fundos_incluidos",
        "pl_incluido_brl",
        "carteira_incluida_brl",
        "inadimplencia_reportada_brl",
        "valor_tabela_ii_brl",
        "inadimplencia_sobre_pl",
        "inadimplencia_sobre_carteira",
        "share_pl_universo_ex_fic_positivo",
    ]
    summary_columns = [
        "competencia",
        "fundos_universo_ex_fic_pl_positivo",
        "pl_universo_ex_fic_positivo_brl",
        "fundos_tabela_ii_mapeados",
        "fundos_tipo_unico_antes_filtros",
        "fundos_incluidos",
        "pl_incluido_brl",
        "cobertura_fundos",
        "cobertura_pl",
        "fundos_multitipo_excluidos",
        "pl_multitipo_excluido_brl",
        "fundos_sem_tipo_excluidos",
        "pl_sem_tipo_excluido_brl",
        "fundos_inad_supera_carteira_excluidos",
        "pl_inad_supera_carteira_excluido_brl",
        "fundos_campos_ausentes_excluidos",
        "pl_campos_ausentes_excluido_brl",
        "fundos_fic_excluidos",
        "pl_fic_excluido_brl",
        "regra",
        "fonte",
    ]
    empty_result = pd.DataFrame(columns=result_columns)
    empty_summary = pd.DataFrame(columns=summary_columns)
    if raw_table_ii_vehicle is None or raw_table_ii_vehicle.empty:
        return empty_result, empty_summary
    if not set(value_columns).issubset(raw_table_ii_vehicle.columns):
        return empty_result, empty_summary

    raw = raw_table_ii_vehicle.copy()
    raw["competencia"] = raw["competencia"].astype(str).str[:7]
    raw = raw[raw["competencia"].eq(competence)].copy()
    if raw.empty:
        return empty_result, empty_summary
    raw["cnpj_veiculo"] = raw.get("cnpj", pd.Series("", index=raw.index)).map(_digits)
    for column in value_columns:
        raw[column] = pd.to_numeric(raw[column], errors="coerce").fillna(0.0)
    raw = raw.groupby("cnpj_veiculo", as_index=False)[value_columns].sum()

    mapping = base_vehicle[
        base_vehicle["competencia"].astype(str).eq(competence)
    ][["cnpj_veiculo", "cnpj_fundo"]].copy()
    mapping["cnpj_veiculo"] = mapping["cnpj_veiculo"].map(_digits)
    mapping["cnpj_fundo"] = mapping["cnpj_fundo"].map(_digits)
    mapping = mapping.drop_duplicates("cnpj_veiculo")
    raw = raw.merge(mapping, on="cnpj_veiculo", how="left")
    raw["cnpj_fundo"] = raw["cnpj_fundo"].where(
        raw["cnpj_fundo"].fillna("").astype(str).str.strip().ne(""),
        raw["cnpj_veiculo"],
    )
    table_ii = raw.groupby("cnpj_fundo", as_index=False)[value_columns].sum()
    nonzero = table_ii[value_columns].abs().gt(0.005)
    table_ii["tipos_recebivel_nao_zero"] = nonzero.sum(axis=1)
    table_ii["tipo_recebivel_tabela_ii"] = (
        table_ii[value_columns]
        .abs()
        .idxmax(axis=1)
        .map(TABLE_II_RECEIVABLE_COLUMNS)
    )
    table_ii["valor_tabela_ii_brl"] = table_ii[value_columns].abs().max(axis=1)

    scoped = fund_base[
        fund_base["competencia"].astype(str).eq(competence)
    ].copy()
    scoped["cnpj_fundo"] = scoped["cnpj_fundo"].map(_digits)
    scoped = scoped.drop_duplicates("cnpj_fundo")
    scoped = scoped.merge(
        table_ii[
            [
                "cnpj_fundo",
                "tipos_recebivel_nao_zero",
                "tipo_recebivel_tabela_ii",
                "valor_tabela_ii_brl",
            ]
        ],
        on="cnpj_fundo",
        how="left",
    )
    for column in ("pl", "carteira_dc", "dc_inadimplentes"):
        scoped[column] = pd.to_numeric(scoped[column], errors="coerce")
    scoped["is_fic_fidc"] = _as_nullable_bool(scoped["is_fic_fidc"]).fillna(False)
    reports_pair = (
        _as_nullable_bool(scoped["reports_carteira_dc"]).eq(True)  # noqa: E712
        & _as_nullable_bool(scoped["reports_dc_inadimplentes"]).eq(True)  # noqa: E712
    )
    positive_pl = scoped["pl"].gt(0)
    ex_fic = ~scoped["is_fic_fidc"]
    one_type = scoped["tipos_recebivel_nao_zero"].eq(1)
    multi_type = scoped["tipos_recebivel_nao_zero"].gt(1)
    no_type = scoped["tipos_recebivel_nao_zero"].fillna(0).eq(0)
    over_portfolio = scoped["dc_inadimplentes"].gt(scoped["carteira_dc"])
    universe = ex_fic & positive_pl
    eligible = universe & one_type & reports_pair & ~over_portfolio
    eligible_frame = scoped[eligible].copy()

    grouped = (
        eligible_frame.groupby("tipo_recebivel_tabela_ii", as_index=False)
        .agg(
            fundos_incluidos=("cnpj_fundo", "nunique"),
            pl_incluido_brl=("pl", "sum"),
            carteira_incluida_brl=("carteira_dc", "sum"),
            inadimplencia_reportada_brl=("dc_inadimplentes", "sum"),
            valor_tabela_ii_brl=("valor_tabela_ii_brl", "sum"),
        )
        .sort_values(
            ["pl_incluido_brl", "tipo_recebivel_tabela_ii"],
            ascending=[False, True],
        )
        .reset_index(drop=True)
    )
    grouped.insert(0, "competencia", competence)
    grouped["inadimplencia_sobre_pl"] = grouped["inadimplencia_reportada_brl"].div(
        grouped["pl_incluido_brl"]
    )
    grouped["inadimplencia_sobre_carteira"] = grouped[
        "inadimplencia_reportada_brl"
    ].div(grouped["carteira_incluida_brl"])
    universe_pl = _sum_min(scoped.loc[universe, "pl"])
    universe_funds = int(scoped.loc[universe, "cnpj_fundo"].nunique())
    grouped["share_pl_universo_ex_fic_positivo"] = grouped["pl_incluido_brl"].div(
        universe_pl
    )

    def excluded_stats(mask: pd.Series) -> tuple[int, float]:
        applied = universe & mask
        return (
            int(scoped.loc[applied, "cnpj_fundo"].nunique()),
            _sum_min(scoped.loc[applied, "pl"]),
        )

    multi_n, multi_pl = excluded_stats(multi_type)
    none_n, none_pl = excluded_stats(no_type)
    over_n, over_pl = excluded_stats(one_type & over_portfolio)
    missing_n, missing_pl = excluded_stats(one_type & ~reports_pair)
    fic_mask = scoped["is_fic_fidc"] & positive_pl
    included_pl = _sum_min(eligible_frame["pl"])
    summary = pd.DataFrame(
        [
            {
                "competencia": competence,
                "fundos_universo_ex_fic_pl_positivo": universe_funds,
                "pl_universo_ex_fic_positivo_brl": universe_pl,
                "fundos_tabela_ii_mapeados": int(
                    scoped.loc[
                        scoped["tipos_recebivel_nao_zero"].notna(), "cnpj_fundo"
                    ].nunique()
                ),
                "fundos_tipo_unico_antes_filtros": int(
                    scoped.loc[universe & one_type, "cnpj_fundo"].nunique()
                ),
                "fundos_incluidos": int(eligible_frame["cnpj_fundo"].nunique()),
                "pl_incluido_brl": included_pl,
                "cobertura_fundos": (
                    eligible_frame["cnpj_fundo"].nunique() / universe_funds
                    if universe_funds
                    else float("nan")
                ),
                "cobertura_pl": (
                    included_pl / universe_pl
                    if pd.notna(universe_pl) and universe_pl
                    else float("nan")
                ),
                "fundos_multitipo_excluidos": multi_n,
                "pl_multitipo_excluido_brl": multi_pl,
                "fundos_sem_tipo_excluidos": none_n,
                "pl_sem_tipo_excluido_brl": none_pl,
                "fundos_inad_supera_carteira_excluidos": over_n,
                "pl_inad_supera_carteira_excluido_brl": over_pl,
                "fundos_campos_ausentes_excluidos": missing_n,
                "pl_campos_ausentes_excluido_brl": missing_pl,
                "fundos_fic_excluidos": int(
                    scoped.loc[fic_mask, "cnpj_fundo"].nunique()
                ),
                "pl_fic_excluido_brl": _sum_min(scoped.loc[fic_mask, "pl"]),
                "regra": (
                    "ex-FIC, PL positivo, exatamente um dos 11 campos superiores da "
                    "Tabela II não zero, carteira e inadimplência reportadas, "
                    "inadimplência <= carteira; numerador = inadimplência reportada, "
                    "denominador = PL total dos fundos incluídos"
                ),
                "fonte": f"CVM, Informe Mensal FIDC, Tabelas I, II e IV, {competence}",
            }
        ]
    )
    return grouped[result_columns], summary[summary_columns]


def build_frozen_single_receivable_history(
    base_vehicle: pd.DataFrame,
    fund_base: pd.DataFrame,
    raw_table_ii_vehicle: pd.DataFrame | None,
    *,
    competence: str = LATEST_COMPLETE,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Trace the latest single-receivable cohort through its reported history.

    Cohort membership and the Table-II subtype are frozen at ``competence``.
    Each historical observation then re-applies the reporting-quality filters:
    ex-FIC, positive PL, portfolio and delinquency fields present, and reported
    delinquency not above the total credit-rights portfolio.  The flow is thus
    intentionally subject to survivorship bias and never reclassifies a fund
    using an older portfolio mix.
    """

    member_columns = [
        "competencia_coorte",
        "cnpj_fundo",
        "cnpj_fundo_formatado",
        "denominacao",
        "tipo_recebivel_tabela_ii",
        "pl_referencia_brl",
        "carteira_referencia_brl",
        "inadimplencia_ajustada_referencia_brl",
    ]
    history_columns = [
        "competencia",
        "tipo_recebivel_tabela_ii",
        "fundos_presentes",
        "fundos_incluidos",
        "pl_presente_brl",
        "pl_incluido_brl",
        "carteira_incluida_brl",
        "inadimplencia_ajustada_brl",
        "inadimplencia_sobre_pl",
        "inadimplencia_sobre_carteira",
        "fundos_inad_supera_carteira_excluidos",
        "fundos_campos_ausentes_excluidos",
        "fundos_coorte",
        "pl_coorte_referencia_brl",
        "cobertura_fundos_coorte",
        "cobertura_pl_referencia_coorte",
    ]
    summary_columns = [
        "competencia",
        "fundos_presentes",
        "fundos_incluidos",
        "pl_presente_brl",
        "pl_incluido_brl",
        "carteira_incluida_brl",
        "inadimplencia_ajustada_brl",
        "inadimplencia_sobre_pl",
        "inadimplencia_sobre_carteira",
        "fundos_inad_supera_carteira_excluidos",
        "fundos_campos_ausentes_excluidos",
        "fundos_coorte",
        "pl_coorte_referencia_brl",
        "cobertura_fundos_coorte",
        "cobertura_pl_referencia_coorte",
        "regra",
        "fonte",
    ]
    empty_members = pd.DataFrame(columns=member_columns)
    empty_history = pd.DataFrame(columns=history_columns)
    empty_summary = pd.DataFrame(columns=summary_columns)
    if raw_table_ii_vehicle is None or raw_table_ii_vehicle.empty:
        return empty_members, empty_history, empty_summary
    value_columns = list(TABLE_II_RECEIVABLE_COLUMNS)
    if not set(value_columns).issubset(raw_table_ii_vehicle.columns):
        return empty_members, empty_history, empty_summary

    raw = raw_table_ii_vehicle.copy()
    raw["competencia"] = raw["competencia"].astype(str).str[:7]
    raw = raw.loc[raw["competencia"].eq(competence)].copy()
    if raw.empty:
        return empty_members, empty_history, empty_summary
    raw["cnpj_veiculo"] = raw.get("cnpj", pd.Series("", index=raw.index)).map(_digits)
    for column in value_columns:
        raw[column] = pd.to_numeric(raw[column], errors="coerce").fillna(0.0)
    raw = raw.groupby("cnpj_veiculo", as_index=False)[value_columns].sum()

    mapping = base_vehicle.loc[
        base_vehicle["competencia"].astype(str).str[:7].eq(competence),
        ["cnpj_veiculo", "cnpj_fundo"],
    ].copy()
    mapping["cnpj_veiculo"] = mapping["cnpj_veiculo"].map(_digits)
    mapping["cnpj_fundo"] = mapping["cnpj_fundo"].map(_digits)
    mapping = mapping.drop_duplicates("cnpj_veiculo")
    raw = raw.merge(mapping, on="cnpj_veiculo", how="left")
    raw["cnpj_fundo"] = raw["cnpj_fundo"].where(
        raw["cnpj_fundo"].fillna("").astype(str).str.strip().ne(""),
        raw["cnpj_veiculo"],
    )
    table_ii = raw.groupby("cnpj_fundo", as_index=False)[value_columns].sum()
    nonzero = table_ii[value_columns].abs().gt(0.005)
    table_ii["tipos_recebivel_nao_zero"] = nonzero.sum(axis=1)
    table_ii["tipo_recebivel_tabela_ii"] = (
        table_ii[value_columns].abs().idxmax(axis=1).map(TABLE_II_RECEIVABLE_COLUMNS)
    )

    latest = fund_base.loc[
        fund_base["competencia"].astype(str).str[:7].eq(competence)
    ].copy()
    latest["cnpj_fundo"] = latest["cnpj_fundo"].map(_digits)
    latest = latest.drop_duplicates("cnpj_fundo").merge(
        table_ii[["cnpj_fundo", "tipos_recebivel_nao_zero", "tipo_recebivel_tabela_ii"]],
        on="cnpj_fundo",
        how="left",
    )
    for column in ("pl", "carteira_dc", "dc_inadimplentes"):
        latest[column] = pd.to_numeric(latest[column], errors="coerce")
    latest_is_fic = _as_nullable_bool(latest["is_fic_fidc"]).fillna(False)
    latest_pair = (
        _as_nullable_bool(latest["reports_carteira_dc"]).eq(True)  # noqa: E712
        & _as_nullable_bool(latest["reports_dc_inadimplentes"]).eq(True)  # noqa: E712
    )
    member_mask = (
        ~latest_is_fic
        & latest["pl"].gt(0)
        & latest["tipos_recebivel_nao_zero"].eq(1)
        & latest_pair
        & latest["dc_inadimplentes"].le(latest["carteira_dc"])
    )
    members = latest.loc[member_mask].copy()
    adjusted_latest = pd.to_numeric(
        members.get("dc_inadimplentes_ajustado_recalculado"), errors="coerce"
    )
    fallback_latest = members["dc_inadimplentes"].clip(lower=0).where(
        members["dc_inadimplentes"].clip(lower=0).le(members["carteira_dc"].clip(lower=0)),
        members["carteira_dc"].clip(lower=0),
    )
    members["inadimplencia_ajustada_referencia_brl"] = adjusted_latest.fillna(
        fallback_latest
    )
    members = members.rename(
        columns={"pl": "pl_referencia_brl", "carteira_dc": "carteira_referencia_brl"}
    )
    members["competencia_coorte"] = competence
    members["cnpj_fundo_formatado"] = members["cnpj_fundo"].map(format_cnpj)
    members = members[member_columns].sort_values(
        ["tipo_recebivel_tabela_ii", "pl_referencia_brl", "cnpj_fundo"],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    if members.empty:
        return empty_members, empty_history, empty_summary

    member_map = members[
        ["cnpj_fundo", "tipo_recebivel_tabela_ii", "pl_referencia_brl"]
    ].copy()
    historical = fund_base[
        fund_base["competencia"].astype(str).str[:7].le(competence)
    ].copy()
    historical["competencia"] = historical["competencia"].astype(str).str[:7]
    historical["cnpj_fundo"] = historical["cnpj_fundo"].map(_digits)
    historical = historical.merge(member_map, on="cnpj_fundo", how="inner")
    historical = historical.drop_duplicates(["competencia", "cnpj_fundo"])
    for column in (
        "pl",
        "carteira_dc",
        "dc_inadimplentes",
        "dc_inadimplentes_ajustado_recalculado",
    ):
        historical[column] = pd.to_numeric(historical.get(column), errors="coerce")
    is_fic = _as_nullable_bool(historical["is_fic_fidc"]).fillna(False)
    pair = (
        _as_nullable_bool(historical["reports_carteira_dc"]).eq(True)  # noqa: E712
        & _as_nullable_bool(historical["reports_dc_inadimplentes"]).eq(True)  # noqa: E712
    )
    present = ~is_fic & historical["pl"].gt(0)
    over = historical["dc_inadimplentes"].gt(historical["carteira_dc"])
    eligible = present & pair & ~over
    fallback_adjusted = historical["dc_inadimplentes"].clip(lower=0).where(
        historical["dc_inadimplentes"].clip(lower=0).le(
            historical["carteira_dc"].clip(lower=0)
        ),
        historical["carteira_dc"].clip(lower=0),
    )
    historical["inad_ajustada_usada"] = historical[
        "dc_inadimplentes_ajustado_recalculado"
    ].fillna(fallback_adjusted)
    historical["present"] = present
    historical["eligible"] = eligible
    historical["over"] = present & pair & over
    historical["missing_pair"] = present & ~pair
    historical["pl_present"] = historical["pl"].where(present, 0.0)
    historical["pl_included"] = historical["pl"].where(eligible, 0.0)
    historical["carteira_included"] = historical["carteira_dc"].where(eligible, 0.0)
    historical["inad_included"] = historical["inad_ajustada_usada"].where(eligible, 0.0)
    historical["latest_pl_included"] = historical["pl_referencia_brl"].where(eligible, 0.0)

    cohort_by_type = members.groupby("tipo_recebivel_tabela_ii", as_index=False).agg(
        fundos_coorte=("cnpj_fundo", "nunique"),
        pl_coorte_referencia_brl=("pl_referencia_brl", "sum"),
    )
    history = (
        historical.groupby(["competencia", "tipo_recebivel_tabela_ii"], as_index=False)
        .agg(
            fundos_presentes=("present", "sum"),
            fundos_incluidos=("eligible", "sum"),
            pl_presente_brl=("pl_present", "sum"),
            pl_incluido_brl=("pl_included", "sum"),
            carteira_incluida_brl=("carteira_included", "sum"),
            inadimplencia_ajustada_brl=("inad_included", "sum"),
            fundos_inad_supera_carteira_excluidos=("over", "sum"),
            fundos_campos_ausentes_excluidos=("missing_pair", "sum"),
            pl_referencia_incluido_brl=("latest_pl_included", "sum"),
        )
        .merge(cohort_by_type, on="tipo_recebivel_tabela_ii", how="left")
    )
    history["inadimplencia_sobre_pl"] = history["inadimplencia_ajustada_brl"].div(
        history["pl_incluido_brl"].replace(0, pd.NA)
    )
    history["inadimplencia_sobre_carteira"] = history[
        "inadimplencia_ajustada_brl"
    ].div(history["carteira_incluida_brl"].replace(0, pd.NA))
    history["cobertura_fundos_coorte"] = history["fundos_incluidos"].div(
        history["fundos_coorte"].replace(0, pd.NA)
    )
    history["cobertura_pl_referencia_coorte"] = history[
        "pl_referencia_incluido_brl"
    ].div(history["pl_coorte_referencia_brl"].replace(0, pd.NA))
    history = history[history_columns].sort_values(
        ["competencia", "pl_coorte_referencia_brl"], ascending=[True, False]
    ).reset_index(drop=True)

    summary = (
        historical.groupby("competencia", as_index=False)
        .agg(
            fundos_presentes=("present", "sum"),
            fundos_incluidos=("eligible", "sum"),
            pl_presente_brl=("pl_present", "sum"),
            pl_incluido_brl=("pl_included", "sum"),
            carteira_incluida_brl=("carteira_included", "sum"),
            inadimplencia_ajustada_brl=("inad_included", "sum"),
            fundos_inad_supera_carteira_excluidos=("over", "sum"),
            fundos_campos_ausentes_excluidos=("missing_pair", "sum"),
            pl_referencia_incluido_brl=("latest_pl_included", "sum"),
        )
        .sort_values("competencia")
        .reset_index(drop=True)
    )
    total_cohort_n = int(members["cnpj_fundo"].nunique())
    total_cohort_pl = float(members["pl_referencia_brl"].sum())
    summary["fundos_coorte"] = total_cohort_n
    summary["pl_coorte_referencia_brl"] = total_cohort_pl
    summary["inadimplencia_sobre_pl"] = summary["inadimplencia_ajustada_brl"].div(
        summary["pl_incluido_brl"].replace(0, pd.NA)
    )
    summary["inadimplencia_sobre_carteira"] = summary[
        "inadimplencia_ajustada_brl"
    ].div(summary["carteira_incluida_brl"].replace(0, pd.NA))
    summary["cobertura_fundos_coorte"] = summary["fundos_incluidos"].div(
        total_cohort_n
    )
    summary["cobertura_pl_referencia_coorte"] = summary[
        "pl_referencia_incluido_brl"
    ].div(total_cohort_pl)
    summary["regra"] = (
        f"coorte e subtipo congelados em {competence}; em cada competência: ex-FIC, "
        "PL positivo, carteira e inadimplência reportadas, inadimplência <= carteira"
    )
    summary["fonte"] = "CVM, Informe Mensal FIDC, Tabelas I, II e IV"
    summary = summary[summary_columns]
    return members, history, summary


def build_frozen_cohort_revision_audit(
    previous_members: pd.DataFrame,
    current_members: pd.DataFrame,
    previous_history: pd.DataFrame,
    current_history: pd.DataFrame,
    *,
    previous_competence: str,
    current_competence: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Explain how a refreshed frozen cohort rewrites historical subtype lines."""

    if previous_members.empty or current_members.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    member_columns = [
        "cnpj_fundo",
        "denominacao",
        "tipo_recebivel_tabela_ii",
        "pl_referencia_brl",
    ]
    previous = previous_members[member_columns].rename(
        columns={
            "denominacao": "denominacao_anterior",
            "tipo_recebivel_tabela_ii": "subtipo_anterior",
            "pl_referencia_brl": "pl_anterior_brl",
        }
    )
    current = current_members[member_columns].rename(
        columns={
            "denominacao": "denominacao_atual",
            "tipo_recebivel_tabela_ii": "subtipo_atual",
            "pl_referencia_brl": "pl_atual_brl",
        }
    )
    detail = previous.merge(current, on="cnpj_fundo", how="outer", validate="one_to_one")
    detail["status_revisao"] = "mesmo subtipo"
    detail.loc[detail["subtipo_anterior"].isna(), "status_revisao"] = "entrada"
    detail.loc[detail["subtipo_atual"].isna(), "status_revisao"] = "saída"
    detail.loc[
        detail["subtipo_anterior"].notna()
        & detail["subtipo_atual"].notna()
        & detail["subtipo_anterior"].ne(detail["subtipo_atual"]),
        "status_revisao",
    ] = "reclassificado"
    detail["denominacao"] = detail["denominacao_atual"].fillna(
        detail["denominacao_anterior"]
    )
    detail["pl_referencia_status_brl"] = detail["pl_atual_brl"].where(
        detail["status_revisao"].ne("saída"), detail["pl_anterior_brl"]
    )
    detail["competencia_anterior"] = previous_competence
    detail["competencia_atual"] = current_competence
    detail = detail.sort_values(
        ["status_revisao", "pl_referencia_status_brl", "cnpj_fundo"],
        ascending=[True, False, True],
    ).reset_index(drop=True)

    def count(status: str) -> int:
        return int(detail["status_revisao"].eq(status).sum())

    def pl(status: str) -> float:
        return float(
            pd.to_numeric(
                detail.loc[
                    detail["status_revisao"].eq(status),
                    "pl_referencia_status_brl",
                ],
                errors="coerce",
            ).sum()
        )

    summary = pd.DataFrame(
        [
            {
                "competencia_anterior": previous_competence,
                "competencia_atual": current_competence,
                "fundos_coorte_anterior": int(previous["cnpj_fundo"].nunique()),
                "pl_coorte_anterior_brl": float(previous["pl_anterior_brl"].sum()),
                "fundos_coorte_atual": int(current["cnpj_fundo"].nunique()),
                "pl_coorte_atual_brl": float(current["pl_atual_brl"].sum()),
                "fundos_mesmo_subtipo": count("mesmo subtipo"),
                "pl_atual_mesmo_subtipo_brl": pl("mesmo subtipo"),
                "fundos_reclassificados": count("reclassificado"),
                "pl_atual_reclassificado_brl": pl("reclassificado"),
                "fundos_entraram": count("entrada"),
                "pl_atual_entradas_brl": pl("entrada"),
                "fundos_sairam": count("saída"),
                "pl_anterior_saidas_brl": pl("saída"),
                "regra": (
                    "coortes elegíveis e subtipos definidos separadamente pela "
                    f"Tabela II em {previous_competence} e {current_competence}"
                ),
            }
        ]
    )

    reclassified = detail[detail["status_revisao"].eq("reclassificado")].copy()
    transitions = (
        reclassified
        .groupby(["subtipo_anterior", "subtipo_atual"], as_index=False)
        .agg(
            fundos=("cnpj_fundo", "nunique"),
            pl_atual_brl=("pl_atual_brl", "sum"),
        )
        .sort_values(["pl_atual_brl", "fundos"], ascending=[False, False])
        .reset_index(drop=True)
    )
    if not transitions.empty:
        leaders: list[dict[str, object]] = []
        for keys, group in reclassified.groupby(
            ["subtipo_anterior", "subtipo_atual"], sort=False
        ):
            ordered = group.sort_values("pl_atual_brl", ascending=False)
            leaders.append(
                {
                    "subtipo_anterior": keys[0],
                    "subtipo_atual": keys[1],
                    "principais_fundos": " | ".join(
                        ordered["denominacao"].fillna("").astype(str).head(3)
                    ),
                    "maior_fundo_pl_brl": float(
                        pd.to_numeric(ordered["pl_atual_brl"], errors="coerce").iloc[0]
                    ),
                }
            )
        transitions = transitions.merge(
            pd.DataFrame(leaders),
            on=["subtipo_anterior", "subtipo_atual"],
            how="left",
            validate="one_to_one",
        )
    transitions["competencia_anterior"] = previous_competence
    transitions["competencia_atual"] = current_competence

    history_keys = ["competencia", "tipo_recebivel_tabela_ii"]
    sensitivity_columns = history_keys + [
        "fundos_incluidos",
        "pl_incluido_brl",
        "carteira_incluida_brl",
        "inadimplencia_sobre_carteira",
    ]
    sensitivity = previous_history[sensitivity_columns].merge(
        current_history[sensitivity_columns],
        on=history_keys,
        how="outer",
        suffixes=("_coorte_anterior", "_coorte_atual"),
    )
    sensitivity["delta_inadimplencia_pp"] = (
        sensitivity["inadimplencia_sobre_carteira_coorte_atual"]
        - sensitivity["inadimplencia_sobre_carteira_coorte_anterior"]
    )
    sensitivity["competencia_coorte_anterior"] = previous_competence
    sensitivity["competencia_coorte_atual"] = current_competence
    sensitivity = sensitivity.sort_values(history_keys).reset_index(drop=True)
    return summary, transitions, sensitivity


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
    excluded_fund_cnpjs: Iterable[str] = MARKET_SHARE_EXCLUDED_FUNDS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build 100% stacks using one fixed Top 10 per provider role.

    Invalid role × focus combinations remain in the output with
    ``publication_status`` set to a blocking reason.  They are not silently
    repaired by hiding negative PL or by moving missing providers to Outros.
    """

    latest = fund_base[
        fund_base["competencia"].eq(competence) & ~fund_base["is_fic_fidc"].fillna(False)
    ].copy()
    latest = exclude_market_share_funds(
        latest, excluded_fund_cnpjs=excluded_fund_cnpjs
    )
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
            positive_scoped = scoped[scoped["pl"].ge(0)].copy()
            publication_denominator = _sum_min(positive_scoped["pl"])
            grouped = (
                positive_scoped.groupby("participant")["pl"].apply(_sum_min).to_dict()
            )
            category_values: list[tuple[str, float, int, str]] = []
            for rank, participant in enumerate(fixed_top, start=1):
                category_values.append(
                    (participant, float(grouped.get(participant, 0.0)), rank, "Top 10 geral")
                )
            identified_other = _sum_min(
                positive_scoped.loc[
                    positive_scoped["participant"].ne("Não informado")
                    & ~positive_scoped["participant"].isin(fixed_top),
                    "pl",
                ]
            )
            if pd.isna(identified_other):
                identified_other = 0.0
            not_informed = _sum_min(
                positive_scoped.loc[
                    positive_scoped["participant"].eq("Não informado"), "pl"
                ]
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
            coverage = (
                (publication_denominator - not_informed) / publication_denominator
                if pd.notna(publication_denominator) and publication_denominator != 0
                else float("nan")
            )
            if pd.isna(publication_denominator) or publication_denominator <= 0:
                status = "bloqueado_sem_denominador_positivo"
            elif coverage > 1.000001 or coverage < -0.000001:
                status = "bloqueado_cobertura_fora_de_0_100"
            elif abs(category_sum - publication_denominator) > max(
                1.0, abs(publication_denominator) * 1e-9
            ):
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
                        "denominador_publicacao_pl_positivo_brl": publication_denominator,
                        "share_subtipo": value / publication_denominator
                        if pd.notna(publication_denominator)
                        and publication_denominator != 0
                        else float("nan"),
                        "pl_identificado_brl": publication_denominator - not_informed
                        if pd.notna(publication_denominator)
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
                            "excluído(s) da normalização percentual sobre PL positivo"
                            if negative_funds
                            else ""
                        ),
                        "publication_status": status,
                        "fechamento_100_pct": category_sum / publication_denominator
                        if pd.notna(publication_denominator)
                        and publication_denominator != 0
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
    excluded_fund_cnpjs: Iterable[str] = MARKET_SHARE_EXCLUDED_FUNDS,
) -> pd.DataFrame:
    """Summarize what sits inside and outside the 14-focus market-share scope."""

    latest = fund_base[
        fund_base["competencia"].eq(competence) & ~fund_base["is_fic_fidc"].fillna(False)
    ].copy()
    latest = exclude_market_share_funds(
        latest, excluded_fund_cnpjs=excluded_fund_cnpjs
    )
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


def build_provider_historical_ranking(
    fund_base: pd.DataFrame,
    *,
    periods: Iterable[str] = ("2024-12", "2025-12", LATEST_COMPLETE),
    excluded_fund_cnpjs: Iterable[str] = MARKET_SHARE_EXCLUDED_FUNDS,
) -> pd.DataFrame:
    """Build provider PL and rank history on the excluded ex-FIC universe."""

    rows: list[dict[str, object]] = []
    for period in (str(value) for value in periods):
        scoped = fund_base[
            fund_base["competencia"].astype(str).eq(period)
            & ~fund_base["is_fic_fidc"].fillna(False)
        ].copy()
        scoped = exclude_market_share_funds(
            scoped, excluded_fund_cnpjs=excluded_fund_cnpjs
        )
        scoped["pl"] = pd.to_numeric(scoped["pl"], errors="coerce")
        denominator = _sum_min(scoped["pl"])
        for role, (name_column, _) in ROLE_COLUMNS.items():
            role_frame = scoped.copy()
            role_frame["participante"] = role_frame.get(
                name_column, pd.Series("", index=role_frame.index)
            ).map(canonical_provider)
            grouped = (
                role_frame.groupby("participante", as_index=False)
                .agg(pl_brl=("pl", _sum_min), fundos=("cnpj_fundo", "nunique"))
                .sort_values(["pl_brl", "participante"], ascending=[False, True])
                .reset_index(drop=True)
            )
            grouped["rank_periodo"] = range(1, len(grouped) + 1)
            for item in grouped.itertuples(index=False):
                rows.append(
                    {
                        "competencia": period,
                        "papel": role,
                        "participante": item.participante,
                        "rank_periodo": int(item.rank_periodo),
                        "pl_brl": float(item.pl_brl),
                        "share_pl": float(item.pl_brl) / denominator
                        if denominator
                        else float("nan"),
                        "fundos": int(item.fundos),
                        "denominador_pl_brl": denominator,
                        "fundos_universo": int(scoped["cnpj_fundo"].nunique()),
                        "fonte_prestador": (
                            "Informe Mensal da competência"
                            if role == "administrador"
                            else "cadastro CVM vigente aplicado à competência"
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _period_provider_scope(
    fund_base: pd.DataFrame,
    competence: str,
    *,
    positive_pl_only: bool,
    excluded_fund_cnpjs: Iterable[str] = MARKET_SHARE_EXCLUDED_FUNDS,
) -> pd.DataFrame:
    """Return a unique legal-fund provider scope for one competence."""

    required = {"competencia", "cnpj_fundo", "pl"}
    missing = required.difference(fund_base.columns)
    if missing:
        raise ValueError(f"base de fundos sem colunas obrigatórias: {sorted(missing)}")
    scoped = fund_base[
        fund_base["competencia"].astype(str).str[:7].eq(str(competence)[:7])
    ].copy()
    scoped["cnpj_fundo"] = scoped["cnpj_fundo"].map(_digits)
    scoped["pl"] = pd.to_numeric(scoped["pl"], errors="coerce")
    if "is_fic_fidc" in scoped:
        is_fic = _as_nullable_bool(scoped["is_fic_fidc"]).fillna(False).astype(bool)
    else:
        is_fic = pd.Series(False, index=scoped.index, dtype=bool)
    scoped = scoped.loc[scoped["cnpj_fundo"].ne("") & ~is_fic].copy()
    if positive_pl_only:
        scoped = scoped.loc[scoped["pl"].gt(0)].copy()
    scoped = exclude_market_share_funds(
        scoped, excluded_fund_cnpjs=excluded_fund_cnpjs
    )
    for column in (
        "denominacao",
        "admin_nome",
        "admin_cnpj",
        "gestor_nome",
        "gestor_cnpj",
        "custodiante_nome",
        "custodiante_cnpj",
    ):
        if column not in scoped:
            scoped[column] = ""
    return (
        scoped.sort_values(["pl", "cnpj_fundo"], ascending=[False, True])
        .drop_duplicates("cnpj_fundo", keep="first")
        .reset_index(drop=True)
    )


def build_provider_transition_flows(
    fund_base: pd.DataFrame,
    *,
    from_competence: str = PROVIDER_TRANSITION_FROM,
    to_competence: str = PROVIDER_TRANSITION_TO,
    excluded_fund_cnpjs: Iterable[str] = MARKET_SHARE_EXCLUDED_FUNDS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build administrator flows for the current cohort, weighted by current PL.

    The cohort is defined in ``to_competence`` (positive-PL, ex-FIC funds).
    Administrator is observed directly in both monthly filings. Manager and
    custodian remain unavailable here; the separate ``cad_fi_hist`` module
    publishes its small ICVM-555 sample with explicit coverage.
    """

    old = _period_provider_scope(
        fund_base,
        from_competence,
        positive_pl_only=False,
        excluded_fund_cnpjs=excluded_fund_cnpjs,
    )
    new = _period_provider_scope(
        fund_base,
        to_competence,
        positive_pl_only=True,
        excluded_fund_cnpjs=excluded_fund_cnpjs,
    )
    old = old[
        ["cnpj_fundo", "denominacao", "pl", "admin_nome", "admin_cnpj"]
    ].rename(
        columns={
            "denominacao": "denominacao_origem",
            "pl": "pl_origem_brl",
            "admin_nome": "admin_origem_nome",
            "admin_cnpj": "admin_origem_cnpj",
        }
    )
    new = new[
        ["cnpj_fundo", "denominacao", "pl", "admin_nome", "admin_cnpj"]
    ].rename(
        columns={
            "denominacao": "denominacao_destino",
            "pl": "pl_destino_brl",
            "admin_nome": "admin_destino_nome",
            "admin_cnpj": "admin_destino_cnpj",
        }
    )
    detail = old.merge(new, on="cnpj_fundo", how="inner", validate="one_to_one")
    detail = detail.loc[
        detail["admin_origem_nome"].map(_clean).ne("")
        & detail["admin_destino_nome"].map(_clean).ne("")
    ].copy()
    detail["competencia_origem"] = str(from_competence)[:7]
    detail["competencia_destino"] = str(to_competence)[:7]
    detail["papel"] = "administrador"
    detail["cnpj_fundo_formatado"] = detail["cnpj_fundo"].map(format_cnpj)
    detail["denominacao"] = detail["denominacao_destino"].where(
        detail["denominacao_destino"].map(_clean).ne(""),
        detail["denominacao_origem"],
    )
    detail["admin_origem_cnpj"] = detail["admin_origem_cnpj"].map(_digits)
    detail["admin_destino_cnpj"] = detail["admin_destino_cnpj"].map(_digits)
    detail["grupo_origem"] = detail["admin_origem_nome"].map(canonical_provider)
    detail["grupo_destino"] = detail["admin_destino_nome"].map(canonical_provider)
    detail["pl_comparavel_brl"] = detail["pl_destino_brl"]
    detail["mudou_grupo"] = detail["grupo_origem"].ne(detail["grupo_destino"])
    detail["mudou_entidade_legal"] = detail["admin_origem_cnpj"].ne(
        detail["admin_destino_cnpj"]
    )
    detail["fundosnet_url"] = detail["cnpj_fundo"].map(fundosnet_fund_url)
    detail["fonte_origem_url"] = cvm_monthly_source_url(from_competence)
    detail["fonte_destino_url"] = cvm_monthly_source_url(to_competence)

    comparable_pl = float(detail["pl_comparavel_brl"].sum())
    changed = detail[detail["mudou_grupo"]].copy()
    changed_pl = float(changed["pl_comparavel_brl"].sum())
    summary = pd.DataFrame(
        [
            {
                "papel": "administrador",
                "competencia_origem": str(from_competence)[:7],
                "competencia_destino": str(to_competence)[:7],
                "continuing_funds": int(len(detail)),
                "comparable_pl_brl": comparable_pl,
                "changed_funds": int(len(changed)),
                "changed_comparable_pl_brl": changed_pl,
                "changed_share": changed_pl / comparable_pl
                if comparable_pl
                else float("nan"),
                "universe_funds_current": int(len(new)),
                "universe_pl_current_brl": float(new["pl_destino_brl"].sum()),
                "coverage_funds": int(len(detail)) / int(len(new)) if len(new) else float("nan"),
                "coverage_pl": comparable_pl / float(new["pl_destino_brl"].sum())
                if float(new["pl_destino_brl"].sum())
                else float("nan"),
                "universe_definition": (
                    f"CNPJ ex-FIC com PL positivo em {to_competence}; administrador observado "
                    "também em dez/24; Sistema Petrobras e TAPSO excluídos"
                ),
                "pl_flow_definition": f"PL de {to_competence} por CNPJ",
                "provider_group_definition": "canonical_provider(nome reportado)",
                "source": "CVM, Informe Mensal, administrador reportado por competência",
            }
        ]
    )

    links = (
        changed.groupby(["grupo_origem", "grupo_destino"], as_index=False)
        .agg(
            fundos=("cnpj_fundo", "nunique"),
            pl_origem_brl=("pl_origem_brl", "sum"),
            pl_destino_brl=("pl_destino_brl", "sum"),
            pl_comparavel_brl=("pl_comparavel_brl", "sum"),
        )
        .sort_values(
            ["pl_comparavel_brl", "grupo_origem", "grupo_destino"],
            ascending=[False, True, True],
        )
        .reset_index(drop=True)
    )
    if not links.empty:
        links.insert(0, "papel", "administrador")
        links["share_pl_comparavel"] = links["pl_comparavel_brl"].div(
            comparable_pl
        )
        links["competencia_origem"] = str(from_competence)[:7]
        links["competencia_destino"] = str(to_competence)[:7]

    unavailable_reason = (
        "cad_fi_hist é histórico ICVM 555 e cobre menos de 8% do PL da coorte; "
        "a amostra observada é publicada em bloco separado, sem extrapolação"
    )
    role_availability = pd.DataFrame(
        [
            {
                "papel": "administrador",
                "transition_status": "disponível",
                "serie_historica_observada": True,
                "fonte_prestador": "Informe Mensal da competência",
                "limitation": "",
            },
            {
                "papel": "gestor",
                "transition_status": "indisponível",
                "serie_historica_observada": False,
                "fonte_prestador": "CVM, cad_fi_hist (amostra ICVM 555)",
                "limitation": unavailable_reason,
            },
            {
                "papel": "custodiante",
                "transition_status": "indisponível",
                "serie_historica_observada": False,
                "fonte_prestador": "CVM, cad_fi_hist (amostra ICVM 555)",
                "limitation": unavailable_reason,
            },
        ]
    )
    detail = detail.sort_values(
        ["mudou_grupo", "pl_comparavel_brl", "cnpj_fundo"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    return summary, links, detail, role_availability


def build_reag_admin_cohort(
    fund_base: pd.DataFrame,
    *,
    from_competence: str = REAG_COHORT_FROM,
    to_competence: str = REAG_COHORT_TO,
    origin_admin_cnpj: str = REAG_CBSF_ADMIN_CNPJ,
    excluded_fund_cnpjs: Iterable[str] = MARKET_SHARE_EXCLUDED_FUNDS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Follow the positive-PL ex-FIC CBSF administrator cohort into May/26."""

    origin_admin_cnpj = _digits(origin_admin_cnpj)
    origin = _period_provider_scope(
        fund_base,
        from_competence,
        positive_pl_only=True,
        excluded_fund_cnpjs=excluded_fund_cnpjs,
    )
    origin["admin_cnpj_norm"] = origin["admin_cnpj"].map(_digits)
    origin = origin[origin["admin_cnpj_norm"].eq(origin_admin_cnpj)].copy()
    origin = origin[
        ["cnpj_fundo", "denominacao", "pl", "admin_nome", "admin_cnpj_norm"]
    ].rename(
        columns={
            "denominacao": "denominacao_origem",
            "pl": "pl_origem_brl",
            "admin_nome": "admin_origem_nome",
            "admin_cnpj_norm": "admin_origem_cnpj",
        }
    )

    required = {"competencia", "cnpj_fundo", "pl"}
    missing = required.difference(fund_base.columns)
    if missing:
        raise ValueError(f"base de fundos sem colunas obrigatórias: {sorted(missing)}")
    current = fund_base[
        fund_base["competencia"].astype(str).str[:7].eq(str(to_competence)[:7])
    ].copy()
    current["cnpj_fundo"] = current["cnpj_fundo"].map(_digits)
    current["pl"] = pd.to_numeric(current["pl"], errors="coerce")
    for column in (
        "denominacao",
        "admin_nome",
        "admin_cnpj",
        "gestor_nome",
        "gestor_cnpj",
        "custodiante_nome",
        "custodiante_cnpj",
        "is_fic_fidc",
    ):
        if column not in current:
            current[column] = False if column == "is_fic_fidc" else ""
    current["is_fic_fidc"] = _as_nullable_bool(current["is_fic_fidc"]).fillna(
        False
    )
    current = (
        current.sort_values(["pl", "cnpj_fundo"], ascending=[False, True])
        .drop_duplicates("cnpj_fundo", keep="first")
        [
            [
                "cnpj_fundo",
                "denominacao",
                "pl",
                "admin_nome",
                "admin_cnpj",
                "gestor_nome",
                "gestor_cnpj",
                "custodiante_nome",
                "custodiante_cnpj",
                "is_fic_fidc",
            ]
        ]
        .rename(
            columns={
                "denominacao": "denominacao_destino",
                "pl": "pl_destino_observado_brl",
                "admin_nome": "admin_destino_nome_observado",
                "admin_cnpj": "admin_destino_cnpj_observado",
                "gestor_nome": "gestor_destino_nome_observado",
                "gestor_cnpj": "gestor_destino_cnpj_observado",
                "custodiante_nome": "custodiante_destino_nome_observado",
                "custodiante_cnpj": "custodiante_destino_cnpj_observado",
                "is_fic_fidc": "is_fic_fidc_destino",
            }
        )
    )
    detail = origin.merge(
        current,
        on="cnpj_fundo",
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    detail["competencia_origem"] = str(from_competence)[:7]
    detail["competencia_destino"] = str(to_competence)[:7]
    detail["cnpj_fundo_formatado"] = detail["cnpj_fundo"].map(format_cnpj)
    detail["denominacao"] = detail["denominacao_destino"].where(
        detail["denominacao_destino"].map(_clean).ne(""),
        detail["denominacao_origem"],
    )
    detail["admin_destino_cnpj_observado"] = detail[
        "admin_destino_cnpj_observado"
    ].map(_digits)
    detail["admin_destino_grupo_observado"] = detail[
        "admin_destino_nome_observado"
    ].map(canonical_provider)
    detail["gestor_destino_cnpj_observado"] = detail[
        "gestor_destino_cnpj_observado"
    ].map(_digits)
    detail["gestor_destino_grupo_observado"] = detail[
        "gestor_destino_nome_observado"
    ].map(canonical_provider)
    detail["custodiante_destino_cnpj_observado"] = detail[
        "custodiante_destino_cnpj_observado"
    ].map(_digits)
    detail["custodiante_destino_grupo_observado"] = detail[
        "custodiante_destino_nome_observado"
    ].map(canonical_provider)
    detail["status_destino"] = "continuante_ativo"
    detail.loc[detail["_merge"].eq("left_only"), "status_destino"] = (
        "saida_sem_reporte"
    )
    nonpositive = detail["_merge"].eq("both") & ~detail[
        "pl_destino_observado_brl"
    ].gt(0)
    detail.loc[nonpositive, "status_destino"] = "saida_pl_nao_positivo"
    outside_ex_fic = detail["_merge"].eq("both") & detail[
        "is_fic_fidc_destino"
    ].fillna(False).astype(bool)
    detail.loc[outside_ex_fic, "status_destino"] = "saida_fora_escopo_ex_fic"
    active = detail["status_destino"].eq("continuante_ativo")
    detail["admin_destino_grupo"] = detail[
        "admin_destino_grupo_observado"
    ].where(active, "Saída / sem reporte")
    detail["admin_destino_cnpj"] = detail[
        "admin_destino_cnpj_observado"
    ].where(active, "")
    detail["pl_destino_brl"] = detail["pl_destino_observado_brl"].where(active)
    detail["pl_comparavel_brl"] = detail[
        ["pl_origem_brl", "pl_destino_brl"]
    ].min(axis=1, skipna=False)
    detail["mudou_administrador"] = active & detail["admin_destino_cnpj"].ne(
        origin_admin_cnpj
    )
    detail["fundosnet_url"] = detail["cnpj_fundo"].map(fundosnet_fund_url)
    detail["fonte_origem_url"] = cvm_monthly_source_url(from_competence)
    detail["fonte_destino_url"] = cvm_monthly_source_url(to_competence)

    continuing = detail[active].copy()
    exited = detail[~active].copy()
    continuing["destino_grupo_link"] = continuing["admin_destino_grupo"].where(
        continuing["admin_destino_grupo"].isin(
            {"CBSF", "Banco Master", "Planner Corretora De Valores"}
        ),
        "Outros migrados",
    )
    continuing["admin_destino_cnpj_link"] = continuing[
        "admin_destino_cnpj"
    ].where(continuing["destino_grupo_link"].ne("Outros migrados"), "")
    links = (
        continuing.groupby(
            ["destino_grupo_link", "admin_destino_cnpj_link"], as_index=False
        )
        .agg(
            fundos=("cnpj_fundo", "nunique"),
            pl_2025_12_brl=("pl_origem_brl", "sum"),
            pl_2026_05_brl=("pl_destino_brl", "sum"),
            pl_comparavel_brl=("pl_comparavel_brl", "sum"),
        )
        .rename(
            columns={
                "destino_grupo_link": "destino_grupo",
                "admin_destino_cnpj_link": "admin_destino_cnpj",
            }
        )
    )
    if not exited.empty:
        exit_row = pd.DataFrame(
            [
                {
                    "destino_grupo": "Saída / sem reporte",
                    "admin_destino_cnpj": "",
                    "fundos": int(exited["cnpj_fundo"].nunique()),
                    "pl_2025_12_brl": float(exited["pl_origem_brl"].sum()),
                    "pl_2026_05_brl": 0.0,
                    "pl_comparavel_brl": float("nan"),
                }
            ]
        )
        links = pd.concat([links, exit_row], ignore_index=True)
    links["pl_current_brl"] = links["pl_2026_05_brl"]
    links["pl_flow_brl"] = links["pl_2025_12_brl"]
    links = links.sort_values(
        ["pl_flow_brl", "destino_grupo"], ascending=[False, True]
    ).reset_index(drop=True)

    migrated = continuing[continuing["mudou_administrador"]]
    continuing_current_pl = float(continuing["pl_destino_brl"].sum())

    def current_role_pl(column: str, value: str) -> float:
        return float(
            continuing.loc[continuing[column].eq(value), "pl_destino_brl"].sum()
        )

    summary = pd.DataFrame(
        [
            {
                "cohort_label": "REAG / CBSF",
                "origin_admin_cnpj": origin_admin_cnpj,
                "origin_admin_cnpj_formatado": format_cnpj(origin_admin_cnpj),
                "competencia_origem": str(from_competence)[:7],
                "competencia_destino": str(to_competence)[:7],
                "funds_origin": int(len(detail)),
                "pl_origin_brl": float(detail["pl_origem_brl"].sum()),
                "continuing_funds": int(len(continuing)),
                "continuing_pl_origin_brl": float(
                    continuing["pl_origem_brl"].sum()
                ),
                "continuing_pl_current_brl": continuing_current_pl,
                "continuing_comparable_pl_brl": float(
                    continuing["pl_comparavel_brl"].sum()
                ),
                "migrated_funds": int(len(migrated)),
                "migrated_pl_current_brl": float(migrated["pl_destino_brl"].sum()),
                "migrated_share_current": float(migrated["pl_destino_brl"].sum())
                / continuing_current_pl
                if continuing_current_pl
                else float("nan"),
                "exited_funds": int(len(exited)),
                "exited_pl_origin_brl": float(exited["pl_origem_brl"].sum()),
                "missing_destination_funds": int(
                    exited["status_destino"].eq("saida_sem_reporte").sum()
                ),
                "nonpositive_destination_funds": int(
                    exited["status_destino"].eq("saida_pl_nao_positivo").sum()
                ),
                "manager_cbsf_trust_pl_brl": current_role_pl(
                    "gestor_destino_grupo_observado", "CBSF"
                ),
                "manager_other_reag_pl_brl": current_role_pl(
                    "gestor_destino_grupo_observado", "REAG"
                ),
                "manager_smart_agro_pl_brl": current_role_pl(
                    "gestor_destino_grupo_observado", "Smart Agro Investimentos"
                ),
                "custodian_reag_cbsf_pl_brl": current_role_pl(
                    "custodiante_destino_cnpj_observado", origin_admin_cnpj
                ),
                "custodian_planner_pl_brl": current_role_pl(
                    "custodiante_destino_grupo_observado",
                    "Planner Corretora De Valores",
                ),
                "manager_custodian_history_available": False,
                "manager_custodian_history_limitation": (
                    "gestor e custodiante são fotografia do cadastro vigente; "
                    f"a composição de {to_competence} é válida como corte atual, não como transição histórica"
                ),
                "universe_definition": (
                    "CNPJ administrado por 34.829.992/0001-86 em dez/25, "
                    f"ex-FIC e PL positivo; continuante exige PL positivo em {to_competence}"
                ),
                "source": "CVM, Informe Mensal, administrador reportado por competência",
                "liquidation_source_url": REAG_LIQUIDATION_BCB_URL,
            }
        ]
    )
    detail = detail.drop(columns="_merge").sort_values(
        ["status_destino", "pl_origem_brl", "cnpj_fundo"],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    return summary, links, detail


def _ranking_provider_pl(
    provider_historical_ranking: pd.DataFrame,
    *,
    competence: str,
    role: str,
    provider: str,
) -> float:
    if provider_historical_ranking is None or provider_historical_ranking.empty:
        return float("nan")
    required = {"competencia", "papel", "participante", "pl_brl"}
    if not required.issubset(provider_historical_ranking.columns):
        return float("nan")
    scoped = provider_historical_ranking[
        provider_historical_ranking["competencia"].astype(str).str[:7].eq(
            str(competence)[:7]
        )
        & provider_historical_ranking["papel"].astype(str).eq(role)
        & provider_historical_ranking["participante"]
        .map(canonical_provider)
        .eq(canonical_provider(provider))
    ]
    if scoped.empty:
        return float("nan")
    return float(pd.to_numeric(scoped["pl_brl"], errors="coerce").sum())


def build_btg_controlled_reconciliation(
    base_vehicle: pd.DataFrame,
    provider_historical_ranking: pd.DataFrame,
    *,
    competence: str = LATEST_COMPLETE,
    controlled_fidcs: Mapping[str, str] = BTG_CONTROLLED_FIDCS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconcile the six active Brazilian FIDCs disclosed as BTG-controlled."""

    vehicle_column = "cnpj_veiculo" if "cnpj_veiculo" in base_vehicle else "cnpj"
    required = {"competencia", vehicle_column, "pl"}
    missing = required.difference(base_vehicle.columns)
    if missing:
        raise ValueError(f"base de veículos sem colunas obrigatórias: {sorted(missing)}")
    current = base_vehicle[
        base_vehicle["competencia"].astype(str).str[:7].eq(str(competence)[:7])
    ].copy()
    current["cnpj_veiculo"] = current[vehicle_column].map(_digits)
    current["pl"] = pd.to_numeric(current["pl"], errors="coerce")
    for column in (
        "cnpj_fundo",
        "denominacao",
        "is_fic_fidc",
        "admin_nome",
        "admin_cnpj",
        "gestor_nome",
        "gestor_cnpj",
        "custodiante_nome",
        "custodiante_cnpj",
    ):
        if column not in current:
            current[column] = False if column == "is_fic_fidc" else ""
    current = (
        current.sort_values(["pl", "cnpj_veiculo"], ascending=[False, True])
        .drop_duplicates("cnpj_veiculo", keep="first")
        .reset_index(drop=True)
    )
    controlled = pd.DataFrame(
        [
            {"cnpj_veiculo": _digits(cnpj), "nome_df_btg": name}
            for cnpj, name in controlled_fidcs.items()
        ]
    )
    detail = controlled.merge(
        current[
            [
                "cnpj_veiculo",
                "cnpj_fundo",
                "denominacao",
                "pl",
                "is_fic_fidc",
                "admin_nome",
                "admin_cnpj",
                "gestor_nome",
                "gestor_cnpj",
                "custodiante_nome",
                "custodiante_cnpj",
            ]
        ],
        on="cnpj_veiculo",
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    detail["competencia"] = str(competence)[:7]
    detail["cnpj_veiculo_formatado"] = detail["cnpj_veiculo"].map(format_cnpj)
    detail["cnpj_fundo"] = detail["cnpj_fundo"].map(_digits)
    detail["cnpj_fundo_formatado"] = detail["cnpj_fundo"].map(format_cnpj)
    detail["observado_competencia"] = detail["_merge"].eq("both")
    detail["pl_mai26_brl"] = detail["pl"]
    for role in ("admin", "gestor", "custodiante"):
        detail[f"{role}_cnpj"] = detail[f"{role}_cnpj"].map(_digits)
        detail[f"{role}_grupo"] = detail[f"{role}_nome"].map(canonical_provider)
        detail[f"btg_no_papel_{role}"] = detail[f"{role}_grupo"].eq("BTG Pactual")
    detail["is_fic_fidc"] = _as_nullable_bool(detail["is_fic_fidc"]).fillna(False)
    detail["reconciliado_controlado_ativo"] = (
        detail["observado_competencia"]
        & detail["pl_mai26_brl"].gt(0)
        & ~detail["is_fic_fidc"].astype(bool)
        & detail["btg_no_papel_gestor"]
    )
    if not detail["reconciliado_controlado_ativo"].all():
        failures = detail.loc[
            ~detail["reconciliado_controlado_ativo"],
            ["cnpj_veiculo", "observado_competencia", "pl_mai26_brl", "gestor_grupo"],
        ].to_dict(orient="records")
        raise AssertionError(
            "os seis FIDCs controlados do BTG não reconciliaram como ativos, "
            f"ex-FIC e geridos pelo BTG em {str(competence)[:7]}: {failures}"
        )
    role_totals = {
        role: _ranking_provider_pl(
            provider_historical_ranking,
            competence=competence,
            role=role,
            provider="BTG Pactual",
        )
        for role in ("administrador", "gestor", "custodiante")
    }
    role_column = {
        "administrador": "admin",
        "gestor": "gestor",
        "custodiante": "custodiante",
    }
    for role, total in role_totals.items():
        short = role_column[role]
        detail[f"btg_{role}_pl_brl"] = total
        detail[f"share_pl_btg_{role}"] = detail["pl_mai26_brl"].div(total)
        detail.loc[~detail[f"btg_no_papel_{short}"], f"share_pl_btg_{role}"] = 0.0
    detail["fundosnet_url"] = detail["cnpj_veiculo"].map(fundosnet_fund_url)
    detail["btg_ifrs_source_url"] = BTG_IFRS_1Q26_URL
    detail["btg_ifrs_source_reference"] = (
        "BTG Pactual, demonstrações IFRS 1T26, nota 3.d, p. 19 do PDF"
    )

    managed_pl = role_totals["gestor"]
    confirmed_pl = float(
        detail.loc[detail["reconciliado_controlado_ativo"], "pl_mai26_brl"].sum()
    )
    residual = managed_pl - confirmed_pl
    manager_ranking = provider_historical_ranking[
        provider_historical_ranking.get(
            "competencia", pd.Series("", index=provider_historical_ranking.index)
        )
        .astype(str)
        .str[:7]
        .eq(str(competence)[:7])
        & provider_historical_ranking.get(
            "papel", pd.Series("", index=provider_historical_ranking.index)
        )
        .astype(str)
        .eq("gestor")
    ].copy()
    if not manager_ranking.empty:
        manager_ranking["provider_group"] = manager_ranking["participante"].map(
            canonical_provider
        )
        competitor_pl = pd.to_numeric(
            manager_ranking.loc[
                manager_ranking["provider_group"].ne("BTG Pactual"), "pl_brl"
            ],
            errors="coerce",
        )
        rank_without_confirmed = 1 + int(competitor_pl.gt(residual).sum())
    else:
        rank_without_confirmed = pd.NA
    bradesco_pl = _ranking_provider_pl(
        provider_historical_ranking,
        competence=competence,
        role="gestor",
        provider="Bradesco",
    )
    summary = pd.DataFrame(
        [
            {
                "provider": "btg",
                "competencia": str(competence)[:7],
                "managed_pl_brl": managed_pl,
                "confirmed_controlled_pl_brl": confirmed_pl,
                "residual_unproven_pl_brl": residual,
                "bradesco_managed_pl_brl": bradesco_pl,
                "confirmed_controlled_share": confirmed_pl / managed_pl
                if managed_pl
                else float("nan"),
                "rank_without_confirmed": rank_without_confirmed,
                "controlled_fidcs_expected": int(len(controlled)),
                "controlled_fidcs_reconciled": int(
                    detail["reconciliado_controlado_ativo"].sum()
                ),
                "methodology": (
                    "seis FIDCs brasileiros ativos declarados controlados na DF IFRS "
                    f"1T26, reconciliados por CNPJ ao PL CVM de {competence}"
                ),
                "source_url": BTG_IFRS_1Q26_URL,
            }
        ]
    )
    detail = detail.drop(columns=["pl", "_merge"]).sort_values(
        ["pl_mai26_brl", "cnpj_veiculo"], ascending=[False, True]
    )
    return summary, detail.reset_index(drop=True)


def build_qi_legacy_attribution(
    fund_base: pd.DataFrame,
    *,
    competence: str = PROVIDER_TRANSITION_FROM,
    excluded_fund_cnpjs: Iterable[str] = MARKET_SHARE_EXCLUDED_FUNDS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split QI's Dec/24 administrator book by the two legal provider CNPJs."""

    scoped = _period_provider_scope(
        fund_base,
        competence,
        positive_pl_only=True,
        excluded_fund_cnpjs=excluded_fund_cnpjs,
    )
    scoped["admin_cnpj_norm"] = scoped["admin_cnpj"].map(_digits)
    scoped["admin_group"] = scoped["admin_nome"].map(canonical_provider)
    attributed_cnpjs = {QI_LEGACY_SINGULARE_CNPJ, QI_ORIGINAL_DTVM_CNPJ}
    group = scoped[scoped["admin_cnpj_norm"].isin(attributed_cnpjs)]
    specifications = (
        (
            QI_LEGACY_SINGULARE_CNPJ,
            "CNPJ legado da Singulare / atual QI Corretora",
            "legacy_singulare",
        ),
        (QI_ORIGINAL_DTVM_CNPJ, "QI DTVM original", "original_qi"),
    )
    rows: list[dict[str, object]] = []
    for cnpj, label, attribution in specifications:
        legal = scoped[scoped["admin_cnpj_norm"].eq(cnpj)]
        rows.append(
            {
                "competencia": str(competence)[:7],
                "provider_cnpj": cnpj,
                "provider_cnpj_formatado": format_cnpj(cnpj),
                "provider_legal_label": label,
                "attribution": attribution,
                "pl_brl": float(legal["pl"].sum()),
                "fundos": int(legal["cnpj_fundo"].nunique()),
                "admin_group_pl_brl": float(group["pl"].sum()),
                "share_admin_group": float(legal["pl"].sum()) / float(group["pl"].sum())
                if float(group["pl"].sum())
                else float("nan"),
                "methodology": (
                    "atribuição por CNPJ legal do administrador; nomes históricos "
                    "podem refletir republicação cadastral sob a marca atual"
                ),
                "source_acquisition_url": QI_SINGULARE_ACQUISITION_URL,
                "source_reorganization_url": QI_REORGANIZATION_BCB_URL,
            }
        )
    detail = pd.DataFrame(rows)
    legacy_pl = float(
        detail.loc[detail["attribution"].eq("legacy_singulare"), "pl_brl"].sum()
    )
    original_pl = float(
        detail.loc[detail["attribution"].eq("original_qi"), "pl_brl"].sum()
    )
    group_pl = float(group["pl"].sum())
    summary = pd.DataFrame(
        [
            {
                "provider": "qi",
                "competencia": str(competence)[:7],
                "admin_group_pl_2024_brl": group_pl,
                "legacy_singulare_pl_2024_brl": legacy_pl,
                "original_qi_pl_2024_brl": original_pl,
                "legacy_share_2024": legacy_pl / group_pl
                if group_pl
                else float("nan"),
                "methodology": (
                    "QI Tech canônico de dez/24 separado pelos CNPJs 62.285.390/0001-40 "
                    "e 46.955.383/0001-52"
                ),
                "source_acquisition_url": QI_SINGULARE_ACQUISITION_URL,
                "source_reorganization_url": QI_REORGANIZATION_BCB_URL,
            }
        ]
    )
    return summary, detail


def build_provider_leadership_attribution(
    base_vehicle: pd.DataFrame,
    fund_base: pd.DataFrame,
    provider_historical_ranking: pd.DataFrame,
    *,
    latest_complete: str = LATEST_COMPLETE,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build the BTG controlled-book and QI legacy-CNPJ attribution blocks."""

    btg_summary, btg_detail = build_btg_controlled_reconciliation(
        base_vehicle,
        provider_historical_ranking,
        competence=latest_complete,
    )
    qi_summary, qi_detail = build_qi_legacy_attribution(fund_base)
    summary = pd.concat([btg_summary, qi_summary], ignore_index=True, sort=False)
    return summary, btg_detail, qi_detail


def build_btg_provider_ex_controlled_scenario(
    provider_historical_ranking: pd.DataFrame,
    bank_fidc_detail: pd.DataFrame,
    fund_base: pd.DataFrame,
    *,
    competence: str = LATEST_COMPLETE,
) -> pd.DataFrame:
    """Re-rank BTG by role after removing the fixed BTG bank cohort."""

    ranking = provider_historical_ranking[
        provider_historical_ranking["competencia"].astype(str).str[:7].eq(
            str(competence)[:7]
        )
    ].copy()
    if ranking.empty or bank_fidc_detail.empty or fund_base.empty:
        return pd.DataFrame()
    cohort = bank_fidc_detail[
        bank_fidc_detail["competencia"].astype(str).str[:7].eq(str(competence)[:7])
        & bank_fidc_detail["bank_group"].astype(str).eq("BTG")
        & _as_nullable_bool(bank_fidc_detail["observado"]).fillna(False)
    ].copy()
    cohort["cnpj_fundo"] = cohort["cnpj_fundo"].map(_digits)
    cohort_cnpjs = set(cohort["cnpj_fundo"])
    current_funds = fund_base[
        fund_base["competencia"].astype(str).str[:7].eq(str(competence)[:7])
    ].copy()
    current_funds["cnpj_fundo"] = current_funds["cnpj_fundo"].map(_digits)
    current_funds["pl"] = pd.to_numeric(current_funds["pl"], errors="coerce")
    current_funds = current_funds[
        current_funds["cnpj_fundo"].isin(cohort_cnpjs)
        & ~_as_nullable_bool(current_funds["is_fic_fidc"]).fillna(False)
        & current_funds["pl"].gt(0)
        & ~current_funds["cnpj_fundo"].isin(
            {_digits(value) for value in MARKET_SHARE_EXCLUDED_FUNDS}
        )
    ].copy()
    role_source_column = {
        "administrador": "admin_nome",
        "gestor": "gestor_nome",
        "custodiante": "custodiante_nome",
    }
    rows: list[dict[str, object]] = []
    for role, source_column in role_source_column.items():
        scoped = ranking[ranking["papel"].eq(role)].copy()
        scoped["grupo"] = scoped["participante"].map(canonical_provider)
        btg_rows = scoped[scoped["grupo"].eq("BTG Pactual")]
        if btg_rows.empty:
            continue
        total = float(pd.to_numeric(btg_rows["pl_brl"], errors="coerce").sum())
        current_rank = int(pd.to_numeric(btg_rows["rank_periodo"], errors="coerce").min())
        cohort_role = current_funds[
            current_funds[source_column].map(canonical_provider).eq("BTG Pactual")
        ]
        cohort_pl = float(cohort_role["pl"].sum())
        residual = total - cohort_pl
        competitors = scoped[~scoped["grupo"].eq("BTG Pactual")].copy()
        competitors["pl_brl"] = pd.to_numeric(competitors["pl_brl"], errors="coerce")
        rank_without = 1 + int(competitors["pl_brl"].gt(residual).sum())
        leader = competitors.sort_values("pl_brl", ascending=False).head(1)
        rows.append(
            {
                "competencia": str(competence)[:7],
                "papel": role,
                "btg_pl_brl": total,
                "btg_rank": current_rank,
                "fidcs_controlados_excluidos": int(cohort_role["cnpj_fundo"].nunique()),
                "pl_controlado_excluido_brl": cohort_pl,
                "fidcs_coorte_bancaria_excluidos": int(
                    cohort_role["cnpj_fundo"].nunique()
                ),
                "pl_coorte_bancaria_excluido_brl": cohort_pl,
                "share_pl_btg_excluido": cohort_pl / total if total else float("nan"),
                "btg_pl_ex_controlados_brl": residual,
                "btg_rank_ex_controlados": rank_without,
                "maior_concorrente": str(leader["participante"].iloc[0]) if not leader.empty else "",
                "maior_concorrente_pl_brl": float(leader["pl_brl"].iloc[0]) if not leader.empty else float("nan"),
                "regra": (
                    "retira, em cada função, os FIDCs da coorte fixa BTG de "
                    "FIDCs.xlsx que têm o próprio BTG no papel analisado; o saldo "
                    "não é classificado automaticamente como carteira de terceiros"
                ),
                "fonte": (
                    "FIDCs.xlsx, aba BTG; " f"CVM, Informe Mensal {competence}"
                ),
                "source_reference": "FIDCs.xlsx#BTG!A2:D33",
            }
        )
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class RevisionOutputs:
    latest_complete: str
    raw_source_presence: pd.DataFrame
    base_vehicle: pd.DataFrame
    qa_delinquency: pd.DataFrame
    delinquency_cases: pd.DataFrame
    delinquency_single_receivable: pd.DataFrame
    delinquency_single_receivable_summary: pd.DataFrame
    delinquency_frozen_cohort_members: pd.DataFrame
    delinquency_frozen_cohort_history: pd.DataFrame
    delinquency_frozen_cohort_summary: pd.DataFrame
    delinquency_cohort_revision_summary: pd.DataFrame
    delinquency_cohort_revision_transitions: pd.DataFrame
    delinquency_cohort_revision_sensitivity: pd.DataFrame
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
    provider_historical_ranking: pd.DataFrame
    provider_independent_ranking: pd.DataFrame
    bank_fidc_evolution: pd.DataFrame
    bank_fidc_detail: pd.DataFrame
    acquiring_reclassified_mix: pd.DataFrame
    classification_coverage: pd.DataFrame
    provider_transition_summary: pd.DataFrame
    provider_transition_links: pd.DataFrame
    provider_transition_detail: pd.DataFrame
    provider_transition_role_availability: pd.DataFrame
    reag_admin_summary: pd.DataFrame
    reag_admin_links: pd.DataFrame
    reag_admin_detail: pd.DataFrame
    provider_leadership_attribution: pd.DataFrame
    btg_controlled_reconciliation: pd.DataFrame
    btg_provider_ex_controlled_scenario: pd.DataFrame
    qi_legacy_attribution: pd.DataFrame


def build_revision_outputs(
    *,
    vehicle_monthly: pd.DataFrame,
    anbima_classification: pd.DataFrame | None = None,
    published_classifications: pd.DataFrame | None = None,
    raw_audit_vehicle: pd.DataFrame | None = None,
    raw_table_ii_vehicle: pd.DataFrame | None = None,
    provider_ownership_curation: pd.DataFrame | None = None,
    bank_fidc_curation: pd.DataFrame | None = None,
    acquiring_reclassification_curation: pd.DataFrame | None = None,
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
    delinquency_single_receivable, delinquency_single_receivable_summary = (
        build_single_receivable_delinquency(
            base,
            fund_base,
            raw_table_ii_vehicle,
            competence=latest_complete,
        )
    )
    (
        delinquency_frozen_cohort_members,
        delinquency_frozen_cohort_history,
        delinquency_frozen_cohort_summary,
    ) = build_frozen_single_receivable_history(
        base,
        fund_base,
        raw_table_ii_vehicle,
        competence=latest_complete,
    )
    previous_complete = str(pd.Period(latest_complete, freq="M") - 1)
    (
        previous_cohort_members,
        previous_cohort_history,
        _previous_cohort_summary,
    ) = build_frozen_single_receivable_history(
        base,
        fund_base,
        raw_table_ii_vehicle,
        competence=previous_complete,
    )
    (
        delinquency_cohort_revision_summary,
        delinquency_cohort_revision_transitions,
        delinquency_cohort_revision_sensitivity,
    ) = build_frozen_cohort_revision_audit(
        previous_cohort_members,
        delinquency_frozen_cohort_members,
        previous_cohort_history,
        delinquency_frozen_cohort_history,
        previous_competence=previous_complete,
        current_competence=latest_complete,
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
    provider_historical_ranking = build_provider_historical_ranking(
        fund_base,
        periods=("2024-12", "2025-12", latest_complete),
    )
    provider_independent_ranking = (
        build_independent_provider_historical_ranking(
            provider_historical_ranking,
            provider_ownership_curation,
            latest_period=latest_complete,
            top_n=6,
        )
        if provider_ownership_curation is not None
        and not provider_ownership_curation.empty
        else pd.DataFrame()
    )
    bank_fidc_evolution = (
        build_fixed_bank_fidc_cohort_history(
            fund_base,
            bank_fidc_curation,
            periods=("2023-12", "2024-12", "2025-12", latest_complete),
        )
        if bank_fidc_curation is not None and not bank_fidc_curation.empty
        else pd.DataFrame()
    )
    bank_fidc_detail = (
        build_fixed_bank_fidc_cohort_detail(
            fund_base,
            bank_fidc_curation,
            periods=("2023-12", "2024-12", "2025-12", latest_complete),
        )
        if bank_fidc_curation is not None and not bank_fidc_curation.empty
        else pd.DataFrame()
    )
    acquiring_reclassified_mix = (
        build_acquiring_reclassified_cvm_mix(
            fund_base,
            acquiring_reclassification_curation,
            periods=("2023-12", latest_complete),
        )
        if acquiring_reclassification_curation is not None
        and not acquiring_reclassification_curation.empty
        else pd.DataFrame()
    )
    classification_coverage = build_classification_coverage(
        fund_base, competence=latest_complete
    )
    (
        provider_transition_summary,
        provider_transition_links,
        provider_transition_detail,
        provider_transition_role_availability,
    ) = build_provider_transition_flows(
        fund_base,
        to_competence=latest_complete,
    )
    reag_admin_summary, reag_admin_links, reag_admin_detail = build_reag_admin_cohort(
        fund_base, to_competence=latest_complete
    )
    (
        provider_leadership_attribution,
        btg_controlled_reconciliation,
        qi_legacy_attribution,
    ) = build_provider_leadership_attribution(
        base,
        fund_base,
        provider_historical_ranking,
        latest_complete=latest_complete,
    )
    btg_provider_ex_controlled_scenario = build_btg_provider_ex_controlled_scenario(
        provider_historical_ranking,
        bank_fidc_detail,
        fund_base,
        competence=latest_complete,
    )
    raw_source_presence = pd.DataFrame()
    if raw_audit_vehicle is not None and not raw_audit_vehicle.empty:
        # Preserve the source evidence needed to distinguish blank from zero
        # without duplicating every analytical column from the monthly base.
        evidence_columns = [
            "competencia",
            "cnpj",
            "cnpj_fundo",
            "denominacao",
            "carteira_dc",
            "dc_inadimplentes",
            "dc_a_vencer_com_parcela_inad",
            "report_flag_source",
            *AGING_VALUE_COLUMNS,
        ]
        evidence_columns.extend(
            sorted(
                column
                for column in raw_audit_vehicle.columns
                if column.startswith("reports_")
            )
        )
        evidence_columns = list(dict.fromkeys(evidence_columns))
        raw_source_presence = raw_audit_vehicle[
            [column for column in evidence_columns if column in raw_audit_vehicle]
        ].copy()
    return RevisionOutputs(
        latest_complete=latest_complete,
        raw_source_presence=raw_source_presence,
        base_vehicle=base,
        qa_delinquency=qa,
        delinquency_cases=cases,
        delinquency_single_receivable=delinquency_single_receivable,
        delinquency_single_receivable_summary=delinquency_single_receivable_summary,
        delinquency_frozen_cohort_members=delinquency_frozen_cohort_members,
        delinquency_frozen_cohort_history=delinquency_frozen_cohort_history,
        delinquency_frozen_cohort_summary=delinquency_frozen_cohort_summary,
        delinquency_cohort_revision_summary=delinquency_cohort_revision_summary,
        delinquency_cohort_revision_transitions=delinquency_cohort_revision_transitions,
        delinquency_cohort_revision_sensitivity=delinquency_cohort_revision_sensitivity,
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
        provider_historical_ranking=provider_historical_ranking,
        provider_independent_ranking=provider_independent_ranking,
        bank_fidc_evolution=bank_fidc_evolution,
        bank_fidc_detail=bank_fidc_detail,
        acquiring_reclassified_mix=acquiring_reclassified_mix,
        classification_coverage=classification_coverage,
        provider_transition_summary=provider_transition_summary,
        provider_transition_links=provider_transition_links,
        provider_transition_detail=provider_transition_detail,
        provider_transition_role_availability=provider_transition_role_availability,
        reag_admin_summary=reag_admin_summary,
        reag_admin_links=reag_admin_links,
        reag_admin_detail=reag_admin_detail,
        provider_leadership_attribution=provider_leadership_attribution,
        btg_controlled_reconciliation=btg_controlled_reconciliation,
        btg_provider_ex_controlled_scenario=btg_provider_ex_controlled_scenario,
        qi_legacy_attribution=qi_legacy_attribution,
    )


def write_revision_outputs(outputs: RevisionOutputs, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    table_specs: tuple[tuple[str, pd.DataFrame, bool], ...] = (
        ("source_presence_overlay.csv.gz", outputs.raw_source_presence, True),
        ("base_competencia_cnpj.csv.gz", outputs.base_vehicle, True),
        ("qa_inadimplencia_competencia.csv", outputs.qa_delinquency, False),
        ("qa_inadimplencia_casos_latest.csv", outputs.delinquency_cases, False),
        (
            "inadimplencia_tipo_recebivel_unico.csv",
            outputs.delinquency_single_receivable,
            False,
        ),
        (
            "inadimplencia_tipo_recebivel_unico_resumo.csv",
            outputs.delinquency_single_receivable_summary,
            False,
        ),
        (
            "inadimplencia_coorte_atual_membros.csv.gz",
            outputs.delinquency_frozen_cohort_members,
            True,
        ),
        (
            "inadimplencia_coorte_atual_historico.csv",
            outputs.delinquency_frozen_cohort_history,
            False,
        ),
        (
            "inadimplencia_coorte_atual_resumo.csv",
            outputs.delinquency_frozen_cohort_summary,
            False,
        ),
        (
            "inadimplencia_coorte_revisao_resumo.csv",
            outputs.delinquency_cohort_revision_summary,
            False,
        ),
        (
            "inadimplencia_coorte_revisao_transicoes.csv",
            outputs.delinquency_cohort_revision_transitions,
            False,
        ),
        (
            "inadimplencia_coorte_revisao_sensibilidade.csv",
            outputs.delinquency_cohort_revision_sensitivity,
            False,
        ),
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
        ("prestadores_ranking_historico.csv", outputs.provider_historical_ranking, False),
        (
            "prestadores_independentes_ranking.csv",
            outputs.provider_independent_ranking,
            False,
        ),
        ("bancos_fidcs_evolucao.csv", outputs.bank_fidc_evolution, False),
        ("bancos_fidcs_detalhe.csv", outputs.bank_fidc_detail, False),
        (
            "adquirencia_mix_reclassificado.csv",
            outputs.acquiring_reclassified_mix,
            False,
        ),
        ("cobertura_classificacao.csv", outputs.classification_coverage, False),
        ("prestadores_transicoes_resumo.csv", outputs.provider_transition_summary, False),
        ("prestadores_transicoes_links.csv", outputs.provider_transition_links, False),
        ("prestadores_transicoes_detalhe.csv", outputs.provider_transition_detail, False),
        (
            "prestadores_transicoes_disponibilidade.csv",
            outputs.provider_transition_role_availability,
            False,
        ),
        ("reag_cbsf_coorte_resumo.csv", outputs.reag_admin_summary, False),
        ("reag_cbsf_coorte_links.csv", outputs.reag_admin_links, False),
        ("reag_cbsf_coorte_detalhe.csv", outputs.reag_admin_detail, False),
        (
            "prestadores_lideranca_atribuicao.csv",
            outputs.provider_leadership_attribution,
            False,
        ),
        (
            "btg_fidcs_controlados_reconciliacao.csv",
            outputs.btg_controlled_reconciliation,
            False,
        ),
        (
            "btg_prestadores_ex_controlados.csv",
            outputs.btg_provider_ex_controlled_scenario,
            False,
        ),
        ("qi_atribuicao_cnpjs_legados.csv", outputs.qi_legacy_attribution, False),
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
        "inadimplencia_tipo_recebivel_unico": records(
            outputs.delinquency_single_receivable
        ),
        "inadimplencia_tipo_recebivel_unico_resumo": records(
            outputs.delinquency_single_receivable_summary
        ),
        "inadimplencia_coorte_atual_membros": records(
            outputs.delinquency_frozen_cohort_members
        ),
        "inadimplencia_coorte_atual_historico": records(
            outputs.delinquency_frozen_cohort_history
        ),
        "inadimplencia_coorte_atual_resumo": records(
            outputs.delinquency_frozen_cohort_summary
        ),
        "inadimplencia_coorte_revisao_resumo": records(
            outputs.delinquency_cohort_revision_summary
        ),
        "inadimplencia_coorte_revisao_transicoes": records(
            outputs.delinquency_cohort_revision_transitions
        ),
        "inadimplencia_coorte_revisao_sensibilidade": records(
            outputs.delinquency_cohort_revision_sensitivity
        ),
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
        "prestadores_ranking_historico": records(outputs.provider_historical_ranking),
        "prestadores_independentes_ranking": records(
            outputs.provider_independent_ranking
        ),
        "bancos_fidcs_evolucao": records(outputs.bank_fidc_evolution),
        "bancos_fidcs_detalhe": records(outputs.bank_fidc_detail),
        "adquirencia_mix_reclassificado": records(
            outputs.acquiring_reclassified_mix
        ),
        "cobertura_classificacao": records(outputs.classification_coverage),
        "provider_transition_summary": records(outputs.provider_transition_summary),
        "provider_transition_links": records(outputs.provider_transition_links),
        "provider_transition_detail": records(outputs.provider_transition_detail),
        "provider_transition_role_availability": records(
            outputs.provider_transition_role_availability
        ),
        "reag_admin_summary": records(outputs.reag_admin_summary),
        "reag_admin_links": records(outputs.reag_admin_links),
        "reag_admin_detail": records(outputs.reag_admin_detail),
        "provider_leadership_attribution": records(
            outputs.provider_leadership_attribution
        ),
        "btg_controlled_reconciliation": records(
            outputs.btg_controlled_reconciliation
        ),
        "btg_provider_ex_controlled_scenario": records(
            outputs.btg_provider_ex_controlled_scenario
        ),
        "qi_legacy_attribution": records(outputs.qi_legacy_attribution),
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
    acquiring_curated_funds = int(
        outputs.acquiring_reclassified_mix["fundos_adquirencia_curados"].max()
    )
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
            "single_receivable_delinquency": (
                "ex-FIC com PL positivo e exatamente um dos 11 campos superiores "
                "da Tabela II não zero; casos com inadimplência acima da carteira "
                "são excluídos; numerador = inadimplência reportada e denominador = PL"
            ),
            "frozen_single_receivable_history": (
                "coorte e subtipo Tabela II congelados na competência mais recente; "
                "histórico mantém o mesmo CNPJ e exclui por competência FIC, PL não "
                "positivo, campos ausentes e inadimplência acima da carteira"
            ),
            "independent_provider": (
                "grupo com independência revisada na curadoria societária; aliases "
                "consolidados antes do ranking; Singulare integra QI Tech e Kanastra "
                "é alocada ao Itaú pela regra de afiliação solicitada"
            ),
            "bank_fidc_fixed_cohort": (
                "coorte fixa das raízes de CNPJ listadas no workbook FIDCs.xlsx; "
                "PL histórico do conjunto atual, sem inferir data societária de consolidação; "
                "BTG Consignados I em dez/25 usa valor oficial recuperado do IME v2 "
                "e reconciliado à demonstração financeira auditada"
            ),
            "acquiring_reclassification": (
                f"somente os {acquiring_curated_funds} CNPJs curados são removidos "
                "do segmento principal CVM "
                "e apresentados em Adquirência; classificação original permanece preservada"
            ),
            "market_share_subtype_denominator": (
                "PL positivo do Tipo + Foco ANBIMA, incluindo prestador não informado; "
                "PL negativo é quantificado e excluído apenas da normalização percentual"
            ),
            "market_share_excluded_funds": MARKET_SHARE_EXCLUDED_FUNDS,
            "provider_transition_flow": (
                "CNPJs ex-FIC com PL positivo em dez/24 e dez/25; "
                "PL comparável = min(PL_dez24, PL_dez25) por CNPJ"
            ),
            "provider_transition_roles": (
                "somente administrador é observado por competência; gestor e "
                "custodiante históricos são indisponíveis por overlay cadastral vigente"
            ),
            "reag_cbsf_cohort": (
                "CNPJ administrador 34.829.992/0001-86 em dez/25, ex-FIC e PL "
                f"positivo; destino ativo exige PL positivo em {outputs.latest_complete}"
            ),
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
            "single_receivable_rows": int(
                len(outputs.delinquency_single_receivable)
            ),
            "single_receivable_funds": int(
                outputs.delinquency_single_receivable_summary[
                    "fundos_incluidos"
                ].iloc[0]
            )
            if not outputs.delinquency_single_receivable_summary.empty
            else 0,
            "frozen_single_receivable_funds": int(
                outputs.delinquency_frozen_cohort_members["cnpj_fundo"].nunique()
            ),
            "independent_provider_rows": int(
                len(outputs.provider_independent_ranking)
            ),
            "bank_fidc_evolution_rows": int(len(outputs.bank_fidc_evolution)),
            "bank_fidc_detail_rows": int(len(outputs.bank_fidc_detail)),
            "acquiring_reclassified_rows": int(
                len(outputs.acquiring_reclassified_mix)
            ),
            "provider_transition_continuing_funds": int(
                outputs.provider_transition_summary["continuing_funds"].iloc[0]
            )
            if not outputs.provider_transition_summary.empty
            else 0,
            "provider_transition_changed_funds": int(
                outputs.provider_transition_summary["changed_funds"].iloc[0]
            )
            if not outputs.provider_transition_summary.empty
            else 0,
            "reag_cohort_exited_funds": int(
                outputs.reag_admin_summary["exited_funds"].iloc[0]
            )
            if not outputs.reag_admin_summary.empty
            else 0,
            "btg_controlled_fidcs_reconciled": int(
                outputs.btg_controlled_reconciliation[
                    "reconciliado_controlado_ativo"
                ].sum()
            ),
            "btg_provider_ex_controlled_roles": int(
                outputs.btg_provider_ex_controlled_scenario["papel"].nunique()
            )
            if not outputs.btg_provider_ex_controlled_scenario.empty
            else 0,
        },
        "limitations": [
            (
                "Materializações antigas de vehicle_monthly converteram vazios em zero; "
                "nesses meses, presença por campo é um limite superior inferido da linha da Tabela I."
            ),
            (
                "Buckets de aging e a sensibilidade ex-360 exigem presença no bruto e "
                "reconciliação entre Tabelas V/VI e a inadimplência da Tabela I; "
                f"{outputs.latest_complete} "
                "não passa esse teste e permanece diagnóstico, não headline."
            ),
            (
                "Gestor e custodiante históricos vêm do cadastro vigente e não "
                "constituem série histórica like-for-like."
            ),
            (
                "Por isso, os fluxos dez/24–dez/25 são calculados somente para "
                "administração; nenhuma troca histórica de gestor ou custodiante é inferida."
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
    "BTG_CONTROLLED_FIDCS",
    "BTG_IFRS_1Q26_URL",
    "LATEST_COMPLETE",
    "MARKET_SHARE_EXCLUDED_FUNDS",
    "PROVIDER_TRANSITION_FROM",
    "PROVIDER_TRANSITION_TO",
    "QI_LEGACY_SINGULARE_CNPJ",
    "QI_ORIGINAL_DTVM_CNPJ",
    "REAG_CBSF_ADMIN_CNPJ",
    "REAG_COHORT_FROM",
    "REAG_COHORT_TO",
    "RevisionOutputs",
    "TABLE_II_RECEIVABLE_COLUMNS",
    "add_reporting_flags",
    "build_base_by_vehicle",
    "build_break_bridge",
    "build_delinquency_cases",
    "build_delinquency_qa",
    "build_frozen_single_receivable_history",
    "build_frozen_cohort_revision_audit",
    "build_fund_base",
    "build_market_share_by_subtype",
    "build_market_share_scope_summary",
    "build_provider_historical_ranking",
    "build_classification_coverage",
    "build_btg_controlled_reconciliation",
    "build_btg_provider_ex_controlled_scenario",
    "exclude_market_share_funds",
    "build_provider_leadership_attribution",
    "build_provider_transition_flows",
    "build_qi_legacy_attribution",
    "build_reag_admin_cohort",
    "overlay_raw_source_presence",
    "build_reconciliation",
    "build_revision_outputs",
    "build_top20_and_monostructure",
    "format_cnpj",
    "fundosnet_fund_url",
    "cvm_monthly_source_url",
    "write_revision_outputs",
]
