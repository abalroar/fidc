"""Build the audited data package used by the definitive FIDC executive deck.

The module keeps direct observations separate from reconstructions. Snapshot
market share and fund counts use CVM monthly filings. Public-offer metrics use
equal trailing-twelve-month windows. Manager and custodian history remains a
reconstruction and carries its dated-evidence coverage in every output row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from build_fidc_extended_market_intelligence import (
    assign_role_as_of,
    ascii_upper,
    bool_series,
    digits,
    load_cadastro_history,
    map_offers_to_funds,
    participant_group,
    period_label,
    safe_ratio,
)


ROLE_COLUMNS = {
    "administrador": "admin_nome",
    "gestor": "gestor_nome",
    "custodiante": "custodiante_nome",
}
UNKNOWN_TYPE = "Nao classificado"
PRIMARY_SOURCE_URLS = {
    "cvm_monthly": "https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal",
    "cvm_cadastro": "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/",
    "cvm_offers": "https://dados.cvm.gov.br/dataset/oferta-distrib",
    "anbima_secondary": "https://developers.anbima.com.br/pt/documentacao/precos-indices/apis-de-precos/fidc/",
    "b3_datawise": "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/datawise-reports/",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--industry-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument(
        "--cad-hist-zip",
        type=Path,
        default=Path(".cache/cvm-cadastro/cad_fi_hist.zip"),
    )
    parser.add_argument(
        "--document-cutoff",
        type=str,
        default="2026-06-30",
        help="Inclusive document cutoff. Kept explicit for deck reproducibility.",
    )
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if pd.isna(value) or math.isinf(float(value)) else float(value)
    if isinstance(value, (pd.Timestamp, pd.Period)):
        return str(value)
    if pd.isna(value) if not isinstance(value, str) else False:
        return None
    return value


def normalize_fidc_type(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    return text if text else UNKNOWN_TYPE


def normalize_offer_type(value: object) -> str:
    text = ascii_upper(value)
    if "SECUND" in text:
        return "SECUNDARIA"
    if "PRIM" in text:
        return "PRIMARIA"
    return text or "NAO INFORMADO"


def cnpj14(value: object) -> str:
    value_digits = digits(value)
    if not value_digits or len(value_digits) > 14:
        return value_digits
    return value_digits.zfill(14)


def semantic_offer_signature(frame: pd.DataFrame) -> pd.Series:
    columns = [
        "cnpj_fundo",
        "document_date",
        "total_subscribers",
        "total_quotas",
        "closing_amount_brl",
    ]
    work = frame.copy()
    for column in columns:
        if column not in work:
            work[column] = ""
    return work[columns].fillna("").astype(str).agg("|".join, axis=1)


def deduplicate_closing_profiles(
    profiles: pd.DataFrame,
    categories: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    profiles = profiles.copy()
    profiles["document_date"] = pd.to_datetime(profiles["document_date"], errors="coerce")
    profiles = profiles.loc[
        profiles["parse_status"].eq("parsed_high")
        & profiles["document_date"].between(window_start, window_end)
    ].copy()
    raw_rows = len(profiles)
    profiles["semantic_signature"] = semantic_offer_signature(profiles)
    profiles = profiles.sort_values(
        ["total_row_validated", "document_date", "document_key"],
        ascending=[False, True, True],
    ).drop_duplicates("semantic_signature", keep="first")
    profiles["offer_observation_id"] = "obs-" + profiles["semantic_signature"].map(
        lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    )

    categories = categories.loc[categories["document_key"].isin(profiles["document_key"])].copy()
    categories = categories.merge(
        profiles[["document_key", "offer_observation_id"]],
        on="document_key",
        how="inner",
    )
    diagnostics = {
        "window_start": window_start.date().isoformat(),
        "window_end": window_end.date().isoformat(),
        "validated_rows_before_semantic_dedup": int(raw_rows),
        "semantic_duplicates_removed": int(raw_rows - len(profiles)),
        "validated_unique_observations": int(len(profiles)),
        "funds": int(profiles["cnpj_fundo"].nunique()),
    }
    return profiles, categories, diagnostics


def build_fidc_type_share_delta(
    vehicle: pd.DataFrame,
    current_period: pd.Period,
    previous_period: pd.Period,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    period_frames: dict[str, pd.DataFrame] = {}
    aggregates: dict[str, pd.DataFrame] = {}
    for key, period in (("previous", previous_period), ("current", current_period)):
        month = vehicle.loc[vehicle["competencia"].eq(period_label(period))].copy()
        month["fidc_type"] = month["segmento_principal"].map(normalize_fidc_type)
        month["cnpj_fundo"] = month["cnpj_fundo"].map(digits)
        period_frames[key] = month
        aggregate = month.groupby("fidc_type", dropna=False).agg(
            pl_brl=("pl", "sum"),
            funds=("cnpj_fundo", "nunique"),
            vehicles=("cnpj", "nunique"),
        )
        aggregate["share"] = aggregate["pl_brl"] / month["pl"].sum()
        aggregate["fund_share"] = aggregate["funds"] / month["cnpj_fundo"].nunique()
        aggregate["rank"] = aggregate["pl_brl"].rank(method="min", ascending=False).astype(int)
        aggregates[key] = aggregate

    delta = aggregates["current"].add_suffix("_current").join(
        aggregates["previous"].add_suffix("_previous"), how="outer"
    )
    delta = delta.fillna(0).reset_index()
    delta["delta_pl_brl"] = delta["pl_brl_current"] - delta["pl_brl_previous"]
    delta["delta_share_pp"] = (delta["share_current"] - delta["share_previous"]) * 100
    delta["delta_funds"] = delta["funds_current"] - delta["funds_previous"]
    delta["delta_fund_share_pp"] = (
        delta["fund_share_current"] - delta["fund_share_previous"]
    ) * 100
    delta["rank_change"] = delta["rank_previous"] - delta["rank_current"]
    delta["competencia_previous"] = period_label(previous_period)
    delta["competencia_current"] = period_label(current_period)
    delta["methodology"] = (
        "dominant receivables category in the CVM monthly filing; contemporaneous classification"
    )
    delta = delta.sort_values("share_current", ascending=False)

    previous_entity = (
        period_frames["previous"]
        .sort_values("pl", ascending=False)
        .drop_duplicates("cnpj")
        [["cnpj", "cnpj_fundo", "fidc_type", "pl"]]
        .rename(columns={"fidc_type": "fidc_type_previous", "pl": "pl_previous"})
    )
    current_entity = (
        period_frames["current"]
        .sort_values("pl", ascending=False)
        .drop_duplicates("cnpj")
        [["cnpj", "cnpj_fundo", "fidc_type", "pl"]]
        .rename(columns={"fidc_type": "fidc_type_current", "pl": "pl_current"})
    )
    transitions = previous_entity.merge(
        current_entity, on="cnpj", how="outer", suffixes=("_previous", "_current")
    )
    transitions["cohort_status"] = np.select(
        [
            transitions["fidc_type_previous"].isna(),
            transitions["fidc_type_current"].isna(),
            transitions["fidc_type_previous"].eq(transitions["fidc_type_current"]),
        ],
        ["entrant", "exit", "same_type"],
        default="reclassified",
    )
    transitions["pl_previous"] = transitions["pl_previous"].fillna(0.0)
    transitions["pl_current"] = transitions["pl_current"].fillna(0.0)
    transition_summary = transitions.groupby("cohort_status", as_index=False).agg(
        vehicles=("cnpj", "nunique"),
        pl_previous_brl=("pl_previous", "sum"),
        pl_current_brl=("pl_current", "sum"),
    )
    transition_summary["pl_delta_brl"] = (
        transition_summary["pl_current_brl"] - transition_summary["pl_previous_brl"]
    )

    current = period_frames["current"]
    previous = period_frames["previous"]
    diagnostics = {
        "current_total_pl_brl": float(current["pl"].sum()),
        "previous_total_pl_brl": float(previous["pl"].sum()),
        "classified_pl_share_current": float(
            current.loc[current["fidc_type"].ne(UNKNOWN_TYPE), "pl"].sum() / current["pl"].sum()
        ),
        "classified_pl_share_previous": float(
            previous.loc[previous["fidc_type"].ne(UNKNOWN_TYPE), "pl"].sum()
            / previous["pl"].sum()
        ),
        "reclassified_vehicles": int(
            transitions["cohort_status"].eq("reclassified").sum()
        ),
        "entrant_vehicles": int(transitions["cohort_status"].eq("entrant").sum()),
        "exit_vehicles": int(transitions["cohort_status"].eq("exit").sum()),
        "classification_warning": (
            "A type move may reflect a change in the largest reported receivables balance, not a legal reclassification."
        ),
    }
    return delta, transition_summary, diagnostics


def build_fidc_type_transition_decomposition(
    vehicle: pd.DataFrame,
    current_period: pd.Period,
    previous_period: pd.Period,
) -> pd.DataFrame:
    entities: dict[str, pd.DataFrame] = {}
    for key, period in (("previous", previous_period), ("current", current_period)):
        month = vehicle.loc[vehicle["competencia"].eq(period_label(period))].copy()
        month["cnpj_fundo"] = month["cnpj_fundo"].map(digits)
        month["fidc_type"] = month["segmento_principal"].map(normalize_fidc_type)
        entities[key] = (
            month.groupby(["cnpj", "cnpj_fundo", "fidc_type"], as_index=False)["pl"].sum()
            .sort_values("pl", ascending=False)
            .drop_duplicates("cnpj")
        )
    joined = entities["previous"].rename(
        columns={"fidc_type": "fidc_type_previous", "pl": "pl_previous"}
    ).merge(
        entities["current"].rename(
            columns={"fidc_type": "fidc_type_current", "pl": "pl_current"}
        ),
        on="cnpj",
        how="outer",
        suffixes=("_previous", "_current"),
    )
    joined["cohort_status"] = np.select(
        [
            joined["fidc_type_previous"].isna(),
            joined["fidc_type_current"].isna(),
            joined["fidc_type_previous"].eq(joined["fidc_type_current"]),
        ],
        ["entrant", "exit", "same_type"],
        default="reclassified",
    )
    joined[["pl_previous", "pl_current"]] = joined[
        ["pl_previous", "pl_current"]
    ].fillna(0.0)
    types = sorted(
        set(joined["fidc_type_previous"].dropna())
        | set(joined["fidc_type_current"].dropna())
    )
    rows = []
    for fidc_type in types:
        same = joined.loc[
            joined["cohort_status"].eq("same_type")
            & joined["fidc_type_current"].eq(fidc_type)
        ]
        entrants = joined.loc[
            joined["cohort_status"].eq("entrant")
            & joined["fidc_type_current"].eq(fidc_type)
        ]
        exits = joined.loc[
            joined["cohort_status"].eq("exit")
            & joined["fidc_type_previous"].eq(fidc_type)
        ]
        switched_in = joined.loc[
            joined["cohort_status"].eq("reclassified")
            & joined["fidc_type_current"].eq(fidc_type)
        ]
        switched_out = joined.loc[
            joined["cohort_status"].eq("reclassified")
            & joined["fidc_type_previous"].eq(fidc_type)
        ]
        same_growth = float(same["pl_current"].sum() - same["pl_previous"].sum())
        entrant_contribution = float(entrants["pl_current"].sum())
        exit_contribution = -float(exits["pl_previous"].sum())
        switched_contribution = float(
            switched_in["pl_current"].sum() - switched_out["pl_previous"].sum()
        )
        rows.append(
            {
                "fidc_type": fidc_type,
                "same_type_vehicles": int(same["cnpj"].nunique()),
                "entrant_vehicles": int(entrants["cnpj"].nunique()),
                "exit_vehicles": int(exits["cnpj"].nunique()),
                "switched_in_vehicles": int(switched_in["cnpj"].nunique()),
                "switched_out_vehicles": int(switched_out["cnpj"].nunique()),
                "same_type_pl_growth_brl": same_growth,
                "entrant_pl_contribution_brl": entrant_contribution,
                "exit_pl_contribution_brl": exit_contribution,
                "net_reclassification_contribution_brl": switched_contribution,
                "reconciled_delta_pl_brl": (
                    same_growth
                    + entrant_contribution
                    + exit_contribution
                    + switched_contribution
                ),
            }
        )
    return pd.DataFrame(rows).sort_values("reconciled_delta_pl_brl", ascending=False)


def role_period_frames(
    vehicle: pd.DataFrame,
    offers: pd.DataFrame,
    current_period: pd.Period,
    previous_period: pd.Period,
    cad_hist_zip: Path,
) -> dict[str, dict[str, pd.DataFrame]]:
    output: dict[str, dict[str, pd.DataFrame]] = {}
    for role, column in ROLE_COLUMNS.items():
        history = (
            pd.DataFrame()
            if role == "administrador"
            else load_cadastro_history(cad_hist_zip, role)
        )
        output[role] = {}
        for key, period in (("previous", previous_period), ("current", current_period)):
            month = vehicle.loc[vehicle["competencia"].eq(period_label(period))].copy()
            month["cnpj_fundo"] = month["cnpj_fundo"].map(digits)
            month["fidc_type"] = month["segmento_principal"].map(normalize_fidc_type)
            if role == "administrador":
                month["role_name"] = month[column].fillna("")
                month["role_source"] = "informe_mensal_cvm"
                month["role_source_confidence"] = "alta"
            else:
                month = assign_role_as_of(
                    month,
                    role,
                    period.end_time.normalize(),
                    current_period,
                    offers,
                    history,
                )
            month["participant"] = month["role_name"].map(participant_group)
            output[role][key] = month
    return output


def build_role_type_share_delta(
    frames: dict[str, dict[str, pd.DataFrame]],
    current_period: pd.Period,
    previous_period: pd.Period,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for role, periods in frames.items():
        aggregates: dict[str, pd.DataFrame] = {}
        type_coverage: dict[str, pd.Series] = {}
        for key, frame in periods.items():
            dated = frame["role_source_confidence"].isin({"alta", "media-alta"})
            work = frame.assign(pl_dated=np.where(dated, frame["pl"], 0.0))
            grouped = work.groupby(["fidc_type", "participant"], dropna=False).agg(
                pl_brl=("pl", "sum"),
                pl_dated_brl=("pl_dated", "sum"),
                funds=("cnpj_fundo", "nunique"),
            )
            totals = work.groupby("fidc_type")["pl"].sum()
            fund_totals = work.groupby("fidc_type")["cnpj_fundo"].nunique()
            grouped["share_within_type"] = grouped.index.get_level_values(0).map(totals)
            grouped["share_within_type"] = grouped["pl_brl"] / grouped["share_within_type"]
            grouped["fund_share_within_type"] = grouped["funds"] / grouped.index.get_level_values(0).map(
                fund_totals
            )
            grouped["rank_within_type"] = grouped.groupby(level=0)["pl_brl"].rank(
                method="min", ascending=False
            )
            aggregates[key] = grouped
            type_coverage[key] = work.groupby("fidc_type").apply(
                lambda group: safe_ratio(float(group["pl_dated"].sum()), float(group["pl"].sum())),
                include_groups=False,
            )

        delta = aggregates["current"].add_suffix("_current").join(
            aggregates["previous"].add_suffix("_previous"), how="outer"
        )
        delta = delta.fillna(0).reset_index()
        delta.insert(0, "role", role)
        delta["delta_pl_brl"] = delta["pl_brl_current"] - delta["pl_brl_previous"]
        delta["delta_share_pp"] = (
            delta["share_within_type_current"] - delta["share_within_type_previous"]
        ) * 100
        delta["delta_funds"] = delta["funds_current"] - delta["funds_previous"]
        delta["delta_fund_share_pp"] = (
            delta["fund_share_within_type_current"]
            - delta["fund_share_within_type_previous"]
        ) * 100
        delta["rank_change"] = (
            delta["rank_within_type_previous"] - delta["rank_within_type_current"]
        )
        delta["dated_coverage_previous"] = delta["fidc_type"].map(
            type_coverage["previous"]
        )
        delta["dated_coverage_current"] = delta["fidc_type"].map(
            type_coverage["current"]
        )
        delta["decision_grade"] = np.where(
            role == "administrador",
            "observed",
            np.where(
                delta["dated_coverage_previous"].ge(0.8),
                "reconstructed_high_coverage",
                "directional_only_low_coverage",
            ),
        )
        delta["competencia_previous"] = period_label(previous_period)
        delta["competencia_current"] = period_label(current_period)
        rows.append(delta)
    result = pd.concat(rows, ignore_index=True)
    return result.sort_values(
        ["role", "fidc_type", "share_within_type_current"],
        ascending=[True, True, False],
    )


def build_role_type_mover_summary(
    type_delta: pd.DataFrame,
    role_type_delta: pd.DataFrame,
    role: str,
    minimum_type_share: float = 0.02,
) -> pd.DataFrame:
    material_types = type_delta.loc[
        type_delta["share_current"].ge(minimum_type_share),
        ["fidc_type", "pl_brl_current", "share_current"],
    ]
    role_rows = role_type_delta.loc[role_type_delta["role"].eq(role)].copy()
    rows = []
    for type_row in material_types.itertuples(index=False):
        subset = role_rows.loc[role_rows["fidc_type"].eq(type_row.fidc_type)].copy()
        if subset.empty:
            continue
        eligible = subset.loc[
            subset[["share_within_type_current", "share_within_type_previous"]]
            .max(axis=1)
            .ge(0.005)
        ]
        if eligible.empty:
            eligible = subset
        leader = subset.sort_values("share_within_type_current", ascending=False).iloc[0]
        winner = eligible.sort_values("delta_share_pp", ascending=False).iloc[0]
        loser = eligible.sort_values("delta_share_pp", ascending=True).iloc[0]
        rows.append(
            {
                "role": role,
                "fidc_type": type_row.fidc_type,
                "type_pl_current_brl": type_row.pl_brl_current,
                "type_share_current": type_row.share_current,
                "current_leader": leader["participant"],
                "current_leader_share": leader["share_within_type_current"],
                "top_winner": winner["participant"],
                "top_winner_delta_share_pp": winner["delta_share_pp"],
                "top_winner_delta_pl_brl": winner["delta_pl_brl"],
                "top_loser": loser["participant"],
                "top_loser_delta_share_pp": loser["delta_share_pp"],
                "top_loser_delta_pl_brl": loser["delta_pl_brl"],
                "decision_grade": winner["decision_grade"],
            }
        )
    return pd.DataFrame(rows).sort_values("type_pl_current_brl", ascending=False)


def build_role_share_uncertainty(
    frames: dict[str, dict[str, pd.DataFrame]],
    current_period: pd.Period,
    previous_period: pd.Period,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for role, periods in frames.items():
        previous = periods["previous"].copy()
        current = periods["current"].copy()
        previous_total = float(previous["pl"].sum())
        current_total = float(current["pl"].sum())
        dated_mask = previous["role_source_confidence"].isin({"alta", "media-alta"})
        dated_previous = previous.loc[dated_mask].copy()
        undated_previous_pl = float(previous.loc[~dated_mask, "pl"].sum())

        reconstructed_previous = previous.groupby("participant", dropna=False).agg(
            pl_previous_reconstructed=("pl", "sum"),
            funds_previous_reconstructed=("cnpj_fundo", "nunique"),
        )
        confirmed_previous = dated_previous.groupby("participant", dropna=False).agg(
            pl_previous_confirmed=("pl", "sum"),
            funds_previous_confirmed=("cnpj_fundo", "nunique"),
        )
        observed_current = current.groupby("participant", dropna=False).agg(
            pl_current=("pl", "sum"),
            funds_current=("cnpj_fundo", "nunique"),
        )

        cohort_funds = set(dated_previous["cnpj_fundo"])
        cohort_current = current.loc[current["cnpj_fundo"].isin(cohort_funds)].copy()
        cohort_previous_total = float(dated_previous["pl"].sum())
        cohort_current_total = float(cohort_current["pl"].sum())
        cohort_previous = dated_previous.groupby("participant", dropna=False)["pl"].sum().rename(
            "pl_previous_dated_cohort"
        )
        cohort_current_group = cohort_current.groupby("participant", dropna=False)["pl"].sum().rename(
            "pl_current_dated_cohort"
        )

        combined = observed_current.join(reconstructed_previous, how="outer")
        combined = combined.join(confirmed_previous, how="outer")
        combined = combined.join(cohort_previous, how="outer")
        combined = combined.join(cohort_current_group, how="outer").fillna(0).reset_index()
        combined.insert(0, "role", role)
        combined["share_current"] = combined["pl_current"] / current_total
        combined["share_previous_reconstructed"] = (
            combined["pl_previous_reconstructed"] / previous_total
        )
        combined["delta_share_pp_reconstructed"] = (
            combined["share_current"] - combined["share_previous_reconstructed"]
        ) * 100
        combined["share_previous_min"] = combined["pl_previous_confirmed"] / previous_total
        combined["share_previous_max"] = (
            combined["pl_previous_confirmed"] + undated_previous_pl
        ).clip(upper=previous_total) / previous_total
        combined["delta_share_pp_lower_bound"] = (
            combined["share_current"] - combined["share_previous_max"]
        ) * 100
        combined["delta_share_pp_upper_bound"] = (
            combined["share_current"] - combined["share_previous_min"]
        ) * 100
        combined["share_previous_dated_cohort"] = (
            combined["pl_previous_dated_cohort"] / cohort_previous_total
            if cohort_previous_total
            else 0.0
        )
        combined["share_current_dated_cohort"] = (
            combined["pl_current_dated_cohort"] / cohort_current_total
            if cohort_current_total
            else 0.0
        )
        combined["delta_share_pp_dated_cohort"] = (
            combined["share_current_dated_cohort"]
            - combined["share_previous_dated_cohort"]
        ) * 100
        combined["dated_market_coverage_previous"] = safe_ratio(
            cohort_previous_total, previous_total
        )
        combined["dated_cohort_current_pl_share"] = safe_ratio(
            cohort_current_total, current_total
        )
        reconstructed_sign = np.sign(combined["delta_share_pp_reconstructed"])
        cohort_sign = np.sign(combined["delta_share_pp_dated_cohort"])
        combined["direction_crosscheck"] = np.where(
            role == "administrador",
            "observed",
            np.where(
                reconstructed_sign.eq(cohort_sign) & reconstructed_sign.ne(0),
                "same_direction",
                "indeterminate",
            ),
        )
        combined["decision_grade"] = np.where(
            role == "administrador",
            "observed",
            np.where(
                combined["direction_crosscheck"].eq("same_direction"),
                "directional_only",
                "not_decision_grade",
            ),
        )
        combined["rank_current"] = combined["pl_current"].rank(
            method="min", ascending=False
        ).astype(int)
        combined["rank_previous_reconstructed"] = combined[
            "pl_previous_reconstructed"
        ].rank(method="min", ascending=False).astype(int)
        combined["rank_change_reconstructed"] = (
            combined["rank_previous_reconstructed"] - combined["rank_current"]
        )
        combined["delta_pl_brl_reconstructed"] = (
            combined["pl_current"] - combined["pl_previous_reconstructed"]
        )
        combined["delta_funds_reconstructed"] = (
            combined["funds_current"] - combined["funds_previous_reconstructed"]
        )
        combined["competencia_previous"] = period_label(previous_period)
        combined["competencia_current"] = period_label(current_period)
        rows.append(combined)
    return pd.concat(rows, ignore_index=True).sort_values(
        ["role", "pl_current"], ascending=[True, False]
    )


def build_offer_role_share_delta(
    offers: pd.DataFrame,
    current_period: pd.Period,
) -> tuple[pd.DataFrame, dict[str, object]]:
    current_end = current_period.end_time.normalize()
    current_start = (current_period - 11).start_time.normalize()
    previous_end = (current_period - 12).end_time.normalize()
    previous_start = (current_period - 23).start_time.normalize()
    valid = offers.loc[bool_series(offers, "volume_registrado_valido")].copy()
    valid["offer_type_normalized"] = valid["tipo_oferta"].map(normalize_offer_type)
    valid = valid.loc[valid["offer_type_normalized"].eq("PRIMARIA")].copy()

    rows: list[pd.DataFrame] = []
    for role in ROLE_COLUMNS:
        source_column = "administrador" if role == "administrador" else role
        valid["participant"] = valid[source_column].map(participant_group)
        aggregates: dict[str, pd.DataFrame] = {}
        for key, start, end in (
            ("previous", previous_start, previous_end),
            ("current", current_start, current_end),
        ):
            window = valid.loc[valid["data_registro"].between(start, end)].copy()
            aggregate = window.groupby("participant", dropna=False).agg(
                offer_volume_brl=("valor_total_registrado_brl", "sum"),
                offers=("offer_id", "nunique"),
                issuers=("cnpj_fundo", "nunique"),
            )
            aggregate["volume_share"] = aggregate["offer_volume_brl"] / window[
                "valor_total_registrado_brl"
            ].sum()
            aggregate["offer_count_share"] = aggregate["offers"] / window["offer_id"].nunique()
            aggregate["rank"] = aggregate["offer_volume_brl"].rank(
                method="min", ascending=False
            ).astype(int)
            aggregates[key] = aggregate
        delta = aggregates["current"].add_suffix("_current").join(
            aggregates["previous"].add_suffix("_previous"), how="outer"
        )
        delta = delta.fillna(0).reset_index()
        delta.insert(0, "role", role)
        delta["delta_offer_volume_brl"] = (
            delta["offer_volume_brl_current"] - delta["offer_volume_brl_previous"]
        )
        delta["delta_volume_share_pp"] = (
            delta["volume_share_current"] - delta["volume_share_previous"]
        ) * 100
        delta["delta_offers"] = delta["offers_current"] - delta["offers_previous"]
        delta["delta_offer_count_share_pp"] = (
            delta["offer_count_share_current"] - delta["offer_count_share_previous"]
        ) * 100
        delta["rank_change"] = delta["rank_previous"] - delta["rank_current"]
        delta["window_previous"] = (
            f"{previous_start.date().isoformat()}..{previous_end.date().isoformat()}"
        )
        delta["window_current"] = (
            f"{current_start.date().isoformat()}..{current_end.date().isoformat()}"
        )
        delta["methodology"] = "CVM registered valid primary public distributions"
        rows.append(delta)
    result = pd.concat(rows, ignore_index=True).sort_values(
        ["role", "volume_share_current"], ascending=[True, False]
    )
    diagnostics = {
        "current_window_start": current_start.date().isoformat(),
        "current_window_end": current_end.date().isoformat(),
        "previous_window_start": previous_start.date().isoformat(),
        "previous_window_end": previous_end.date().isoformat(),
        "current_primary_volume_brl": float(
            valid.loc[valid["data_registro"].between(current_start, current_end), "valor_total_registrado_brl"].sum()
        ),
        "previous_primary_volume_brl": float(
            valid.loc[valid["data_registro"].between(previous_start, previous_end), "valor_total_registrado_brl"].sum()
        ),
        "excludes_secondary_distributions": True,
    }
    return result, diagnostics


def build_investor_statistics(
    profiles: pd.DataFrame,
    categories: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    subscribers = pd.to_numeric(profiles["total_subscribers"], errors="coerce").dropna()
    percentiles = subscribers.quantile([0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99])
    stats = pd.DataFrame(
        [
            {"statistic": "observations", "value": float(len(subscribers))},
            {"statistic": "mean", "value": float(subscribers.mean())},
            {"statistic": "median", "value": float(subscribers.median())},
            *[
                {"statistic": f"p{int(level * 100):02d}", "value": float(value)}
                for level, value in percentiles.items()
            ],
            {"statistic": "maximum", "value": float(subscribers.max())},
            {"statistic": "share_le_5", "value": float(subscribers.le(5).mean())},
            {"statistic": "share_le_10", "value": float(subscribers.le(10).mean())},
        ]
    )

    family = categories.groupby("investor_family", as_index=False).agg(
        offers_with_family=(
            "offer_observation_id",
            lambda values: values[
                pd.to_numeric(categories.loc[values.index, "subscribers"], errors="coerce").fillna(0).gt(0)
            ].nunique(),
        ),
        subscriber_accounts=("subscribers", "sum"),
        allocated_amount_proxy_brl=("allocated_amount_proxy_brl", "sum"),
    )
    total_accounts = float(family["subscriber_accounts"].sum())
    total_proxy = float(family["allocated_amount_proxy_brl"].sum())
    family["account_share"] = family["subscriber_accounts"] / total_accounts
    family["amount_proxy_share"] = (
        family["allocated_amount_proxy_brl"] / total_proxy if total_proxy else 0.0
    )
    family = family.sort_values("subscriber_accounts", ascending=False)

    offer_account_totals = profiles.set_index("offer_observation_id")["total_subscribers"]
    top3_account_share = safe_ratio(
        float(offer_account_totals.nlargest(3).sum()), float(offer_account_totals.sum())
    )
    people = categories.loc[categories["investor_family"].eq("Pessoas naturais")]
    people_by_offer = people.groupby("offer_observation_id")["subscribers"].sum()
    amount_eligible = profiles.loc[
        profiles["closing_amount_brl"].notna() & profiles["total_quotas"].fillna(0).gt(0)
    ]
    diagnostics = {
        "unique_observations": int(len(profiles)),
        "funds": int(profiles["cnpj_fundo"].nunique()),
        "subscriber_accounts_total": float(subscribers.sum()),
        "top3_offers_share_of_accounts": top3_account_share,
        "top3_offers_share_of_people_accounts": safe_ratio(
            float(people_by_offer.nlargest(3).sum()), float(people_by_offer.sum())
        ),
        "offers_with_closing_amount": int(profiles["closing_amount_brl"].notna().sum()),
        "offers_with_allocable_amount_proxy": int(len(amount_eligible)),
        "amount_proxy_total_brl": total_proxy,
        "amount_proxy_warning": (
            "Quota-count allocation assumes a common average price across investor categories and is not disclosed cash allocation."
        ),
        "account_warning": "Subscriber rows are offer accounts, not deduplicated CPF/CNPJ.",
    }
    return stats, family, diagnostics


def build_subscriber_histogram(profiles: pd.DataFrame) -> pd.DataFrame:
    values = pd.to_numeric(profiles["total_subscribers"], errors="coerce").fillna(0)
    labels = ["0", "1", "2-5", "6-10", "11-50", "51-100", "101-500", ">500"]
    buckets = pd.cut(
        values,
        bins=[-1, 0, 1, 5, 10, 50, 100, 500, np.inf],
        labels=labels,
    )
    counts = buckets.value_counts(sort=False)
    return pd.DataFrame(
        {
            "bucket": labels,
            "observations": [int(counts.get(label, 0)) for label in labels],
            "share_observations": [
                safe_ratio(int(counts.get(label, 0)), len(profiles)) for label in labels
            ],
        }
    )


def participant_identity(frame: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    output["participant_cnpj"] = output["cnpj_participante"].map(cnpj14)
    output["document_name"] = output["nome_fantasia"].fillna("").astype(str).str.strip()
    empty = output["document_name"].eq("")
    output.loc[empty, "document_name"] = output.loc[empty, "razao_social"].fillna("")
    output["document_name"] = output["document_name"].map(clean_document_participant_name)
    registry_names = registry.set_index("cnpj")["registry_name"].to_dict()
    output["participant_name"] = output["participant_cnpj"].map(registry_names)
    output["participant_name"] = output["participant_name"].fillna(output["document_name"])
    output["participant_key"] = np.where(
        output["participant_cnpj"].str.len().eq(14),
        output["participant_cnpj"],
        output["participant_name"].map(ascii_upper),
    )
    return output


def load_registry(industry_dir: Path) -> pd.DataFrame:
    registry = pd.read_csv(industry_dir / "participant_registry.csv.gz", dtype=str, low_memory=False)
    registry["cnpj"] = registry["cnpj"].map(cnpj14)
    registry["registry_name"] = registry["nome_fantasia"].fillna("").str.strip()
    empty = registry["registry_name"].eq("")
    registry.loc[empty, "registry_name"] = registry.loc[empty, "razao_social"].fillna("")
    return registry.loc[registry["registry_name"].ne("")].drop_duplicates("cnpj")


def clean_document_participant_name(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    marker_matches = list(
        re.finditer(r"(?:^|;)\s*(?:\([ivxabc]+\)|[ivxabc][.)])\s*", text, re.I)
    )
    if marker_matches:
        text = text[marker_matches[-1].end() :]
    text = re.sub(r"^(?:OU\s+A|OU\s+O)\s+", "", text, flags=re.I)
    text = re.sub(r"^CONSIDERANDO-SE[^;]*;\s*", "", text, flags=re.I)
    text = text.replace("I nstituição", "Instituição").replace("Ind ústria", "Indústria")
    return re.sub(r"\s+", " ", text).strip(" ,;:-()\"“”")


def cedent_commercial_group(value: object) -> str:
    name = ascii_upper(value)
    if "QI SOCIEDADE DE CREDITO" in name:
        return "QI SCD"
    if re.search(r"\bBMP\b", name):
        return "BMP"
    if "VIA CAPITAL" in name or "CELCOIN" in name:
        return "CELCOIN / VIA CAPITAL"
    if "PARATI" in name:
        return "PARATI"
    if "SUMUP" in name:
        return "SUMUP"
    if "BANCO PINE" in name:
        return "BANCO PINE"
    if re.search(r"\bUY3\b", name):
        return "UY3"
    return re.sub(r"\s+", " ", name).strip(" .,;:-")


def parse_document_date(value: object) -> pd.Timestamp:
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", "" if pd.isna(value) else str(value))
    return pd.to_datetime(match.group(1), errors="coerce") if match else pd.NaT


def build_participant_outputs(
    industry_dir: Path,
    vehicle: pd.DataFrame,
    current_period: pd.Period,
    document_cutoff: pd.Timestamp,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, object],
]:
    cedentes = pd.read_csv(
        industry_dir / "cedentes_structured.csv.gz",
        low_memory=False,
        dtype={"cnpj_fundo": "string", "cnpj_participante": "string"},
    )
    accepted = cedentes.loc[
        bool_series(cedentes, "ativo_curadoria") & cedentes["candidate_status"].eq("accepted")
    ].copy()
    accepted["document_date"] = accepted["documento_origem"].map(parse_document_date)
    accepted = accepted.loc[
        accepted["document_date"].isna() | accepted["document_date"].le(document_cutoff)
    ].copy()
    accepted["cnpj_fundo"] = accepted["cnpj_fundo"].map(digits)
    accepted["confidence"] = pd.to_numeric(accepted["score_confianca_final"], errors="coerce").fillna(0.0)
    accepted["current_pl_brl"] = pd.to_numeric(accepted["pl"], errors="coerce").fillna(
        pd.to_numeric(accepted["pl_atual_brl"], errors="coerce")
    ).fillna(0.0)
    for column in ("valid_volume_2024_brl", "valid_volume_2025_brl", "valid_volume_2026_brl"):
        accepted[column] = pd.to_numeric(accepted[column], errors="coerce").fillna(0.0)
    accepted["issuance_2024_2026_brl"] = accepted[
        ["valid_volume_2024_brl", "valid_volume_2025_brl", "valid_volume_2026_brl"]
    ].sum(axis=1)
    accepted = participant_identity(accepted, load_registry(industry_dir))

    current = vehicle.loc[vehicle["competencia"].eq(period_label(current_period))].copy()
    current["cnpj_fundo"] = current["cnpj_fundo"].map(digits)
    current_fund_pl = current.groupby("cnpj_fundo")["pl"].sum()
    accepted["current_pl_brl"] = accepted["cnpj_fundo"].map(current_fund_pl).fillna(0.0)

    fund_cnpjs = set(vehicle["cnpj_fundo"].map(digits)) | set(vehicle["cnpj"].map(digits))
    role_names = {
        ascii_upper(name)
        for column in ROLE_COLUMNS.values()
        for name in current[column].dropna().astype(str)
    }
    accepted["likely_role_false_positive"] = (
        accepted["participant_cnpj"].isin(fund_cnpjs)
        | accepted["participant_name"].map(ascii_upper).isin(role_names)
    )

    pair = accepted.sort_values("confidence", ascending=False).drop_duplicates(
        ["participant_type", "cnpj_fundo", "participant_key"]
    )
    pair_counts = pair.groupby(["participant_type", "cnpj_fundo"])["participant_key"].transform(
        "nunique"
    ).clip(lower=1)
    pair["fractional_current_pl_brl"] = pair["current_pl_brl"] / pair_counts
    pair["fractional_issuance_brl"] = pair["issuance_2024_2026_brl"] / pair_counts

    cedent_pairs = pair.loc[pair["participant_type"].eq("cedente_originador")].copy()
    cedent_map = cedent_pairs.groupby(["participant_key", "participant_cnpj"], dropna=False).agg(
        participant_name=("participant_name", "first"),
        funds=("cnpj_fundo", "nunique"),
        linked_pl_fractional_brl=("fractional_current_pl_brl", "sum"),
        linked_issuance_fractional_brl=("fractional_issuance_brl", "sum"),
        confidence_median=("confidence", "median"),
        sector=("setor", lambda values: " | ".join(sorted(set(values.dropna().astype(str)))[:3])),
        administrators=("administrador", lambda values: " | ".join(sorted(set(values.dropna().astype(str)))[:4])),
        managers=("gestor", lambda values: " | ".join(sorted(set(values.dropna().astype(str)))[:4])),
        custodians=("custodiante", lambda values: " | ".join(sorted(set(values.dropna().astype(str)))[:4])),
        first_evidence_date=("document_date", "min"),
        latest_evidence_date=("document_date", "max"),
    ).reset_index()
    cedent_map["commercial_signal_brl"] = (
        cedent_map["linked_pl_fractional_brl"] + cedent_map["linked_issuance_fractional_brl"]
    )
    cedent_map = cedent_map.sort_values(
        ["funds", "commercial_signal_brl"], ascending=[False, False]
    )
    cedent_map.insert(0, "rank", range(1, len(cedent_map) + 1))

    commercial = cedent_map.loc[cedent_map["participant_name"].fillna("").ne("")].copy()
    commercial["commercial_group"] = commercial["participant_name"].map(
        cedent_commercial_group
    )
    commercial = commercial.loc[commercial["commercial_group"].ne("")]
    commercial_group_map = commercial.groupby("commercial_group", as_index=False).agg(
        legal_entities=("participant_cnpj", "nunique"),
        funds=("funds", "sum"),
        linked_pl_fractional_brl=("linked_pl_fractional_brl", "sum"),
        linked_issuance_fractional_brl=("linked_issuance_fractional_brl", "sum"),
        commercial_signal_brl=("commercial_signal_brl", "sum"),
        confidence_median=("confidence_median", "median"),
        sector=("sector", lambda values: " | ".join(sorted(set(values.dropna().astype(str)))[:3])),
    )
    commercial_group_map = commercial_group_map.sort_values(
        ["funds", "commercial_signal_brl"], ascending=[False, False]
    )
    commercial_group_map.insert(0, "rank", range(1, len(commercial_group_map) + 1))

    sector = cedent_map.copy()
    sector["sector"] = sector["sector"].replace("", "Nao identificado")
    sector_summary = sector.groupby("sector", as_index=False).agg(
        cedents=("participant_key", "nunique"),
        funds=("funds", "sum"),
        linked_pl_fractional_brl=("linked_pl_fractional_brl", "sum"),
        linked_issuance_fractional_brl=("linked_issuance_fractional_brl", "sum"),
        commercial_signal_brl=("commercial_signal_brl", "sum"),
    )
    sector_summary["commercial_signal_share"] = (
        sector_summary["commercial_signal_brl"] / sector_summary["commercial_signal_brl"].sum()
    )
    sector_summary = sector_summary.sort_values("commercial_signal_brl", ascending=False)

    sacado_pairs = pair.loc[
        pair["participant_type"].eq("sacado_devedor")
        & ~pair["likely_role_false_positive"]
        & pair["participant_cnpj"].str.len().eq(14)
    ].copy()
    sacado_map = sacado_pairs.groupby(["participant_key", "participant_cnpj"], dropna=False).agg(
        participant_name=("participant_name", "first"),
        funds=("cnpj_fundo", "nunique"),
        linked_pl_fractional_brl=("fractional_current_pl_brl", "sum"),
        confidence_max=("confidence", "max"),
        confidence_median=("confidence", "median"),
        sector=("setor", lambda values: " | ".join(sorted(set(values.dropna().astype(str)))[:3])),
        latest_evidence_date=("document_date", "max"),
        source_document=("documento_origem", "last"),
    ).reset_index()
    sacado_map["executive_grade"] = sacado_map["confidence_max"].ge(0.9)
    sacado_map = sacado_map.sort_values(
        ["executive_grade", "linked_pl_fractional_brl"], ascending=[False, False]
    )

    temporal = cedent_pairs.dropna(subset=["document_date"]).copy()
    temporal["evidence_year"] = temporal["document_date"].dt.year
    temporal = temporal.groupby("evidence_year", as_index=False).agg(
        accepted_fund_cedent_pairs=("participant_key", "count"),
        funds=("cnpj_fundo", "nunique"),
        cedents=("participant_key", "nunique"),
    )
    temporal["scope_note"] = "document evidence date; not economic origination date"

    current_pl = float(current["pl"].sum())
    unique_cedent_funds = cedent_pairs.drop_duplicates("cnpj_fundo")
    high_sacados = sacado_map.loc[sacado_map["executive_grade"]]
    diagnostics = {
        "accepted_rows_all_participant_types": int(len(accepted)),
        "accepted_funds_all_participant_types": int(accepted["cnpj_fundo"].nunique()),
        "accepted_cedent_rows": int(
            accepted["participant_type"].eq("cedente_originador").sum()
        ),
        "accepted_cedent_funds": int(cedent_pairs["cnpj_fundo"].nunique()),
        "accepted_cedent_identities": int(cedent_map["participant_key"].nunique()),
        "accepted_cedent_linked_pl_brl": float(unique_cedent_funds["current_pl_brl"].sum()),
        "accepted_cedent_linked_pl_share": safe_ratio(
            float(unique_cedent_funds["current_pl_brl"].sum()), current_pl
        ),
        "accepted_sacado_funds_after_role_exclusions": int(sacado_pairs["cnpj_fundo"].nunique()),
        "accepted_sacado_identities_after_role_exclusions": int(sacado_map["participant_key"].nunique()),
        "executive_grade_sacado_funds": int(
            sacado_pairs.loc[sacado_pairs["confidence"].ge(0.9), "cnpj_fundo"].nunique()
        ),
        "executive_grade_sacado_identities": int(high_sacados["participant_key"].nunique()),
        "maximum_sacado_recurrence_across_funds": int(sacado_map["funds"].max())
        if not sacado_map.empty
        else 0,
        "sacado_conclusion": (
            "The curated sample supports named examples, not a market-wide ranking or concentration estimate."
        ),
    }
    return (
        cedent_map,
        commercial_group_map,
        sector_summary,
        temporal,
        sacado_map,
        diagnostics,
    )


def build_document_funnel(
    industry_dir: Path,
    vehicle: pd.DataFrame,
    current_period: pd.Period,
    participant_diagnostics: dict[str, object],
    closing_profiles: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    current = vehicle.loc[vehicle["competencia"].eq(period_label(current_period))].copy()
    current["cnpj_fundo"] = current["cnpj_fundo"].map(digits)
    current_funds = current.groupby("cnpj_fundo", as_index=False).agg(
        pl=("pl", "sum"),
        fidc_type=("segmento_principal", lambda values: normalize_fidc_type(values.iloc[0])),
    )
    index = pd.read_csv(industry_dir / "document_text_index.csv.gz", low_memory=False)
    index["cnpj_fundo"] = index["cnpj_fundo"].map(digits)
    candidates = pd.read_csv(industry_dir / "document_participant_candidates.csv.gz", low_memory=False)
    candidates["cnpj_fundo"] = candidates["cnpj_fundo"].map(digits)

    def stage_row(stage: str, fund_ids: set[str], note: str) -> dict[str, object]:
        matched = current_funds.loc[current_funds["cnpj_fundo"].isin(fund_ids)]
        return {
            "stage": stage,
            "funds": int(len(fund_ids)),
            "current_funds_matched": int(matched["cnpj_fundo"].nunique()),
            "current_pl_brl": float(matched["pl"].sum()),
            "current_pl_share": safe_ratio(float(matched["pl"].sum()), float(current_funds["pl"].sum())),
            "note": note,
        }

    funnel = pd.DataFrame(
        [
            stage_row(
                "current_cvm_universe",
                set(current_funds["cnpj_fundo"]),
                "All funds/classes in the May 2026 monthly snapshot.",
            ),
            stage_row(
                "funds_with_local_public_documents",
                set(index["cnpj_fundo"].dropna()),
                "Inventory inherited from Strategy DB and targeted Fundos.NET downloads; not a census.",
            ),
            stage_row(
                "funds_with_text_ready_documents",
                set(index.loc[index["parse_status"].eq("text_ready"), "cnpj_fundo"].dropna()),
                "Documents with extracted searchable text.",
            ),
            stage_row(
                "funds_with_participant_candidates",
                set(candidates["cnpj_fundo"].dropna()),
                "Parser detected at least one cedent, sacado or consultant candidate.",
            ),
            stage_row(
                "funds_with_accepted_cedent",
                set(
                    pd.read_csv(industry_dir / "cedent_fund_map.csv", dtype={"cnpj_fundo": str})[
                        "cnpj_fundo"
                    ].map(digits)
                )
                if (industry_dir / "cedent_fund_map.csv").exists()
                else set(),
                "Accepted high-precision cedent evidence; selection is not random.",
            ),
            stage_row(
                "funds_with_validated_closing_table",
                set(closing_profiles["cnpj_fundo"].map(digits)),
                "Unique high-confidence closing announcements in the exact 24-month window.",
            ),
        ]
    )
    if participant_diagnostics.get("accepted_cedent_funds"):
        row = funnel["stage"].eq("funds_with_accepted_cedent")
        funnel.loc[row, "funds"] = participant_diagnostics["accepted_cedent_funds"]

    current_funds["fidc_type"] = current_funds["fidc_type"].map(normalize_fidc_type)
    doc_funds = set(index["cnpj_fundo"].dropna())
    covered = current_funds.assign(document_covered=current_funds["cnpj_fundo"].isin(doc_funds))
    bias = covered.groupby("fidc_type", as_index=False).agg(
        universe_funds=("cnpj_fundo", "nunique"),
        universe_pl_brl=("pl", "sum"),
        documented_funds=("document_covered", "sum"),
        documented_pl_brl=("pl", lambda values: float(values[covered.loc[values.index, "document_covered"]].sum())),
    )
    bias["fund_coverage"] = bias["documented_funds"] / bias["universe_funds"]
    bias["pl_coverage"] = bias["documented_pl_brl"] / bias["universe_pl_brl"]
    bias = bias.sort_values("universe_pl_brl", ascending=False)
    return funnel, bias


def build_secondary_analysis(
    offers: pd.DataFrame,
    current_period: pd.Period,
) -> tuple[pd.DataFrame, dict[str, object]]:
    valid = offers.loc[bool_series(offers, "volume_registrado_valido")].copy()
    valid["offer_type_normalized"] = valid["tipo_oferta"].map(normalize_offer_type)
    secondary = valid.loc[valid["offer_type_normalized"].eq("SECUNDARIA")].copy()
    current_start = (current_period - 11).start_time.normalize()
    current_end = current_period.end_time.normalize()
    previous_start = (current_period - 23).start_time.normalize()
    previous_end = (current_period - 12).end_time.normalize()
    rows = []
    for label, start, end in (
        ("previous_ltm", previous_start, previous_end),
        ("current_ltm", current_start, current_end),
    ):
        window = secondary.loc[secondary["data_registro"].between(start, end)]
        volume = float(window["valor_total_registrado_brl"].sum())
        top1 = float(window.nlargest(1, "valor_total_registrado_brl")["valor_total_registrado_brl"].sum())
        top3 = float(window.nlargest(3, "valor_total_registrado_brl")["valor_total_registrado_brl"].sum())
        rows.append(
            {
                "window": label,
                "start": start.date().isoformat(),
                "end": end.date().isoformat(),
                "registered_secondary_distribution_volume_brl": volume,
                "registered_secondary_distributions": int(window["offer_id"].nunique()),
                "issuers": int(window["cnpj_fundo"].nunique()),
                "top1_volume_share": safe_ratio(top1, volume),
                "top3_volume_share": safe_ratio(top3, volume),
                "scope": "registered public secondary distributions; not trade turnover",
            }
        )
    result = pd.DataFrame(rows)
    diagnostics = {
        "cvm_trade_level_turnover_available": False,
        "anbima_pricing_api_has_trade_volume": False,
        "anbima_public_fields": [
            "taxa_compra",
            "taxa_venda",
            "taxa_indicativa",
            "pu",
            "percent_pu_par",
            "duration",
        ],
        "required_source_for_speed": "B3 Fundos21/DataWise or participant trade extract",
        "defensible_speed_metrics_after_data_access": [
            "median days between trades by series",
            "share of series with at least one trade in 30/90/180 days",
            "monthly turnover divided by average outstanding PL",
            "buyer/seller concentration",
            "trade PU dispersion versus ANBIMA indicative PU",
        ],
    }
    return result, diagnostics


def metric_catalog(
    current_period: pd.Period,
    previous_period: pd.Period,
    investor_window: str,
) -> pd.DataFrame:
    rows = [
        (
            "market_pl_gross",
            "Gross FIDC PL",
            "Sum of monthly-filing PL across reporting vehicles.",
            "sum(pl)",
            "All CVM FIDC reporting vehicles",
            period_label(current_period),
            "Includes FIC-FIDC and NP",
            "None in gross view",
            "CVM monthly FIDC filing",
            "ANBIMA press releases for external reconciliation",
            "Different scopes explain CVM/ANBIMA gaps.",
            "observed",
            PRIMARY_SOURCE_URLS["cvm_monthly"],
        ),
        (
            "admin_pl_share_delta",
            "Administrator PL share delta",
            "Participant PL divided by total gross FIDC PL at each date.",
            "share_t - share_t-12m",
            "All monthly reporting vehicles grouped to economic participant",
            f"{period_label(previous_period)} vs {period_label(current_period)}",
            "Active reporting rows with PL",
            "No ex-FIC or ex-NP filter",
            "CVM monthly FIDC filing",
            "None",
            "Provider migration can move PL without fundraising.",
            "observed",
            PRIMARY_SOURCE_URLS["cvm_monthly"],
        ),
        (
            "manager_custodian_pl_share_delta",
            "Manager/custodian PL share delta",
            "Same share formula with dated role reconstruction for the prior date.",
            "reconstructed_share_t - reconstructed_share_t-12m",
            "All monthly reporting vehicles",
            f"{period_label(previous_period)} vs {period_label(current_period)}",
            "cad_fi_hist, dated offers, then current-role fallback",
            "No silent imputation beyond flagged fallback",
            "CVM cadastro history and monthly filing",
            "CVM public offers",
            "Prior-date dated evidence covers only about one-third of PL.",
            "directional_only",
            PRIMARY_SOURCE_URLS["cvm_cadastro"],
        ),
        (
            "fidc_type_share_delta",
            "FIDC type PL share delta",
            "Share by largest reported receivables category in each month.",
            "type_pl / total_pl",
            "All monthly reporting vehicles",
            f"{period_label(previous_period)} vs {period_label(current_period)}",
            "Contemporaneous dominant category",
            "None; unknown retained",
            "CVM monthly FIDC filing, receivables tables",
            "None",
            "A move may be a dominant-balance change, not a legal reclassification.",
            "observed_with_classification_caveat",
            PRIMARY_SOURCE_URLS["cvm_monthly"],
        ),
        (
            "primary_offer_role_share",
            "Primary-offer volume share by role",
            "Registered valid primary public-distribution volume by disclosed role.",
            "participant primary volume / total primary volume",
            "CVM public FIDC offers",
            "Two equal trailing-12-month windows ending May 2025 and May 2026",
            "Valid registered primary offers",
            "Secondary distributions and invalid/cancelled volume",
            "CVM public-offer open data",
            "None",
            "Registered amount is not necessarily cash settled or outstanding PL.",
            "observed",
            PRIMARY_SOURCE_URLS["cvm_offers"],
        ),
        (
            "investor_subscriber_distribution",
            "Subscriber count distribution",
            "Unique high-confidence closing-announcement tables after semantic deduplication.",
            "distribution(total_subscribers)",
            "Closing announcements with parseable Annex N allocation tables",
            investor_window,
            "Parsed-high observations",
            "Duplicate semantic copies and lower-confidence parses",
            "CVM/Fundos.NET closing announcements",
            "Monthly filing X.1/X.1.1 for stock cross-check",
            "Accounts are not unique CPF/CNPJ; disclosure is a selected offer subset.",
            "observed_sample",
            PRIMARY_SOURCE_URLS["cvm_offers"],
        ),
        (
            "investor_amount_proxy",
            "Investor-category amount proxy",
            "Closing amount allocated by each category's share of subscribed quotas.",
            "closing_amount * category_quotas / total_quotas",
            "Parsed-high offers with amount and quota totals",
            investor_window,
            "Only fully allocable observations",
            "Offers without amount or quota denominator",
            "CVM/Fundos.NET closing announcements",
            "None",
            "Not disclosed cash allocation; quota prices may differ by class.",
            "directional_proxy",
            PRIMARY_SOURCE_URLS["cvm_offers"],
        ),
        (
            "accepted_cedent_map",
            "Accepted cedent map",
            "Named cedent/originator evidence accepted by the document curation pipeline.",
            "unique fund x participant identity",
            "Local document corpus, not all CVM FIDCs",
            "Evidence through 2026-06-30",
            "Accepted and active curation rows",
            "Rejected/ambiguous candidates",
            "CVM/Fundos.NET regulations, assemblies and offer documents",
            "BrasilAPI/CNPJ for legal-entity enrichment",
            "Non-random document coverage; linked PL is not additive across cedents.",
            "curated_sample",
            PRIMARY_SOURCE_URLS["cvm_monthly"],
        ),
        (
            "sacado_examples",
            "Named sacado examples",
            "High-confidence accepted sacado evidence after fund/role false-positive exclusions.",
            "confidence >= 0.90",
            "Curated local document corpus",
            "Evidence through 2026-06-30",
            "Valid CNPJ and high-confidence relation",
            "Institutional-role/fund self matches",
            "CVM/Fundos.NET regulations and offer documents",
            "BrasilAPI/CNPJ",
            "Coverage is too small for a market ranking or concentration conclusion.",
            "examples_only",
            PRIMARY_SOURCE_URLS["cvm_monthly"],
        ),
        (
            "secondary_distribution_volume",
            "Registered secondary distributions",
            "Valid public offers classified as secondary by CVM.",
            "sum(registered_amount)",
            "CVM public FIDC offers",
            "Two equal trailing-12-month windows",
            "Valid secondary distributions",
            "Primary distributions",
            "CVM public-offer open data",
            "ANBIMA pricing for price/rate context",
            "This is not exchange/OTC turnover or time-to-sell.",
            "observed_not_liquidity",
            PRIMARY_SOURCE_URLS["cvm_offers"],
        ),
        (
            "secondary_trade_speed",
            "Secondary trade speed",
            "Median time between actual trades by quota series.",
            "median(diff(trade_date))",
            "B3 Fundos21/OTC trade-level records",
            "Requires at least 36 months",
            "Executed/registered non-cancelled trades",
            "Offer registrations and corrections",
            "B3 DataWise or participant extract",
            "ANBIMA indicative pricing",
            "Not measurable from free CVM/ANBIMA open data currently loaded.",
            "not_available",
            PRIMARY_SOURCE_URLS["b3_datawise"],
        ),
    ]
    columns = [
        "metric_id",
        "metric_label",
        "definition",
        "formula",
        "universe",
        "period",
        "inclusions",
        "exclusions",
        "primary_source",
        "secondary_source",
        "limitations",
        "decision_grade",
        "source_url",
    ]
    return pd.DataFrame(rows, columns=columns)


def validation_results(
    industry_dir: Path,
    current_period: pd.Period,
    type_delta: pd.DataFrame,
    role_type_delta: pd.DataFrame,
    offer_delta: pd.DataFrame,
    investor_profiles: pd.DataFrame,
    investor_family: pd.DataFrame,
    funnel: pd.DataFrame,
    secondary: pd.DataFrame,
) -> pd.DataFrame:
    industry = pd.read_csv(industry_dir / "industry_monthly.csv")
    current_industry = industry.loc[industry["competencia"].eq(period_label(current_period))].iloc[0]
    tests: list[dict[str, object]] = []

    def add(test_id: str, observed: float, expected: float, tolerance: float, severity: str, note: str) -> None:
        passed = abs(observed - expected) <= tolerance
        tests.append(
            {
                "test_id": test_id,
                "status": "pass" if passed else "fail",
                "observed": observed,
                "expected": expected,
                "tolerance": tolerance,
                "severity": severity,
                "note": note,
            }
        )

    add(
        "snapshot_pl_reconciles_to_industry_monthly",
        float(type_delta["pl_brl_current"].sum()),
        float(current_industry["pl_total"]),
        1.0,
        "critical",
        "Type totals must equal the published gross snapshot.",
    )
    add(
        "type_shares_sum_to_one_current",
        float(type_delta["share_current"].sum()),
        1.0,
        1e-9,
        "critical",
        "Unknown type is retained, so the partition must be exhaustive.",
    )
    for role in ROLE_COLUMNS:
        current = role_type_delta.loc[role_type_delta["role"].eq(role)]
        sums = current.groupby("fidc_type")["share_within_type_current"].sum()
        add(
            f"{role}_shares_sum_to_one_within_type",
            float((sums - 1).abs().max()),
            0.0,
            1e-8,
            "critical",
            "Every FIDC type must be fully allocated across participant groups.",
        )
        offer = offer_delta.loc[offer_delta["role"].eq(role)]
        add(
            f"{role}_primary_offer_shares_sum_to_one",
            float(offer["volume_share_current"].sum()),
            1.0,
            1e-8,
            "critical",
            "Primary-offer participant shares must reconcile to total valid volume.",
        )
    add(
        "investor_observations_semantically_unique",
        float(investor_profiles["semantic_signature"].nunique()),
        float(len(investor_profiles)),
        0.0,
        "critical",
        "No duplicated closing observation remains in the headline sample.",
    )
    add(
        "investor_family_accounts_reconcile",
        float(investor_family["account_share"].sum()),
        1.0,
        1e-8,
        "critical",
        "Investor-family account shares must sum to one.",
    )
    documented_funds = float(
        funnel.loc[
            funnel["stage"].eq("funds_with_local_public_documents"), "current_funds_matched"
        ].iloc[0]
    )
    universe_funds = float(
        funnel.loc[funnel["stage"].eq("current_cvm_universe"), "current_funds_matched"].iloc[0]
    )
    add(
        "document_corpus_is_subset_of_current_universe",
        float(documented_funds <= universe_funds),
        1.0,
        0.0,
        "critical",
        "Document coverage must remain a labeled subset, never an all-FIDC census claim.",
    )
    add(
        "secondary_scope_is_not_turnover",
        float(secondary["scope"].str.contains("not trade turnover").all()),
        1.0,
        0.0,
        "critical",
        "Registered distributions may never be described as trading turnover.",
    )
    return pd.DataFrame(tests)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((args.industry_dir / "metadata.json").read_text())
    current_period = pd.Period(str(metadata["competencia_snapshot"]), freq="M")
    previous_period = current_period - 12
    document_cutoff = pd.Timestamp(args.document_cutoff).normalize()
    investor_window_start = (document_cutoff - pd.DateOffset(years=2) + pd.Timedelta(days=1)).normalize()

    vehicle = pd.read_csv(args.industry_dir / "vehicle_monthly.csv.gz", low_memory=False)
    offers = pd.read_csv(args.industry_dir / "issuance_offers.csv.gz", low_memory=False)
    offers = map_offers_to_funds(offers, vehicle)

    type_delta, type_transitions, type_diagnostics = build_fidc_type_share_delta(
        vehicle, current_period, previous_period
    )
    type_transition_decomposition = build_fidc_type_transition_decomposition(
        vehicle, current_period, previous_period
    )
    frames = role_period_frames(
        vehicle, offers, current_period, previous_period, args.cad_hist_zip
    )
    role_type_delta = build_role_type_share_delta(frames, current_period, previous_period)
    role_type_movers = pd.concat(
        [
            build_role_type_mover_summary(type_delta, role_type_delta, role)
            for role in ROLE_COLUMNS
        ],
        ignore_index=True,
    )
    role_uncertainty = build_role_share_uncertainty(
        frames, current_period, previous_period
    )
    offer_role_delta, offer_diagnostics = build_offer_role_share_delta(offers, current_period)

    profiles_raw = pd.read_csv(args.industry_dir / "investor_offer_profiles.csv", low_memory=False)
    categories_raw = pd.read_csv(args.industry_dir / "investor_offer_categories.csv", low_memory=False)
    investor_profiles, investor_categories, investor_dedup = deduplicate_closing_profiles(
        profiles_raw,
        categories_raw,
        investor_window_start,
        document_cutoff,
    )
    investor_stats, investor_family, investor_diagnostics = build_investor_statistics(
        investor_profiles, investor_categories
    )
    investor_histogram = build_subscriber_histogram(investor_profiles)

    (
        cedent_map,
        cedent_commercial_groups,
        cedent_sectors,
        cedent_temporal,
        sacado_map,
        participant_diagnostics,
    ) = (
        build_participant_outputs(
            args.industry_dir, vehicle, current_period, document_cutoff
        )
    )
    funnel, universe_bias = build_document_funnel(
        args.industry_dir,
        vehicle,
        current_period,
        participant_diagnostics,
        investor_profiles,
    )
    secondary, secondary_diagnostics = build_secondary_analysis(offers, current_period)
    catalog = metric_catalog(
        current_period,
        previous_period,
        f"{investor_window_start.date().isoformat()}..{document_cutoff.date().isoformat()}",
    )
    validations = validation_results(
        args.industry_dir,
        current_period,
        type_delta,
        role_type_delta,
        offer_role_delta,
        investor_profiles,
        investor_family,
        funnel,
        secondary,
    )

    outputs = {
        "fidc_type_share_delta.csv": type_delta,
        "fidc_type_transition_summary.csv": type_transitions,
        "fidc_type_transition_decomposition.csv": type_transition_decomposition,
        "role_fidc_type_share_delta.csv": role_type_delta,
        "role_fidc_type_movers_summary.csv": role_type_movers,
        "role_market_share_uncertainty.csv": role_uncertainty,
        "offer_role_share_delta.csv": offer_role_delta,
        "investor_offer_profiles_deduplicated.csv": investor_profiles,
        "investor_offer_categories_deduplicated.csv": investor_categories,
        "investor_subscriber_statistics.csv": investor_stats,
        "investor_subscriber_histogram_definitive.csv": investor_histogram,
        "investor_family_definitive.csv": investor_family,
        "cedent_definitive_map.csv": cedent_map,
        "cedent_commercial_group_map.csv": cedent_commercial_groups,
        "cedent_sector_summary.csv": cedent_sectors,
        "cedent_evidence_temporal.csv": cedent_temporal,
        "sacado_definitive_map.csv": sacado_map,
        "document_universe_funnel.csv": funnel,
        "document_universe_bias_by_type.csv": universe_bias,
        "secondary_market_definitive.csv": secondary,
        "market_intelligence_metric_catalog.csv": catalog,
        "market_intelligence_validation_results.csv": validations,
    }
    for filename, frame in outputs.items():
        frame.to_csv(args.output_dir / filename, index=False)

    summary = json_safe(
        {
            "schema_version": "fidc-definitive-market-intelligence/v1",
            "pl_snapshot": period_label(current_period),
            "previous_pl_snapshot": period_label(previous_period),
            "document_cutoff": document_cutoff.date().isoformat(),
            "investor_window_start": investor_window_start.date().isoformat(),
            "type_diagnostics": type_diagnostics,
            "offer_diagnostics": offer_diagnostics,
            "investor_deduplication": investor_dedup,
            "investor_diagnostics": investor_diagnostics,
            "participant_diagnostics": participant_diagnostics,
            "secondary_diagnostics": secondary_diagnostics,
            "validation": {
                "tests": int(len(validations)),
                "passed": int(validations["status"].eq("pass").sum()),
                "failed": int(validations["status"].eq("fail").sum()),
                "critical_failures": int(
                    (
                        validations["status"].eq("fail")
                        & validations["severity"].eq("critical")
                    ).sum()
                ),
            },
            "headline_tables": {
                "type_winners": type_delta.sort_values("delta_share_pp", ascending=False).head(5).to_dict("records"),
                "type_losers": type_delta.sort_values("delta_share_pp").head(5).to_dict("records"),
                "type_transition_decomposition": type_transition_decomposition.to_dict("records"),
                "role_share_headlines": {
                    role: role_uncertainty.loc[role_uncertainty["role"].eq(role)]
                    .head(15)
                    .to_dict("records")
                    for role in ROLE_COLUMNS
                },
                "role_type_movers": role_type_movers.to_dict("records"),
                "primary_offer_role_share": {
                    role: offer_role_delta.loc[offer_role_delta["role"].eq(role)]
                    .head(15)
                    .to_dict("records")
                    for role in ROLE_COLUMNS
                },
                "executive_grade_sacados": sacado_map.loc[sacado_map["executive_grade"]].head(15).to_dict("records"),
                "top_cedents": cedent_commercial_groups.head(15).to_dict("records"),
                "investor_families": investor_family.to_dict("records"),
                "investor_statistics": investor_stats.to_dict("records"),
                "investor_histogram": investor_histogram.to_dict("records"),
                "largest_subscriber_observations": investor_profiles.nlargest(
                    5, "total_subscribers"
                )[
                    ["fundo", "document_date", "total_subscribers", "closing_amount_brl"]
                ].to_dict("records"),
                "document_funnel": funnel.to_dict("records"),
                "secondary_windows": secondary.to_dict("records"),
            },
            "source_urls": PRIMARY_SOURCE_URLS,
        }
    )
    (args.output_dir / "definitive_market_intelligence.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )

    critical_failures = summary["validation"]["critical_failures"]
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "critical_failures": critical_failures,
                "investor_observations": investor_dedup["validated_unique_observations"],
                "cedent_funds": participant_diagnostics["accepted_cedent_funds"],
                "sacado_funds_high_confidence": participant_diagnostics[
                    "executive_grade_sacado_funds"
                ],
            },
            ensure_ascii=False,
        )
    )
    if args.strict and critical_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
