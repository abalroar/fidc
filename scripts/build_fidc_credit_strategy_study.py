from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


DEFAULT_ISSUANCE_DIR = Path("outputs/fidc_credit_strategy_study_20260609/issuance")
DEFAULT_DEEP_DIR = Path("outputs/fidc_director_deep_diagnostic_20260609")
DEFAULT_OUTPUT_DIR = Path("outputs/fidc_credit_strategy_study_20260609/strategy")
DEFAULT_APP_DATA_DIR = Path("data/fidc_credit_strategy")
DEFAULT_IME_DIR = Path("outputs/fidc_credit_strategy_study_20260609/raw_sources/inf_mensal_fidc")
AS_OF_DATE = "2026-06-09"
FEATURE_KEYS = [
    "asset_class_confirmed",
    "named_originator_or_cedente",
    "named_debtor_or_sacado",
    "revolving_period",
    "subordination_minimum",
    "mezzanine_layer",
    "cash_or_liquidity_reserve",
    "repurchase_or_indemnity",
    "eligibility_criteria",
    "concentration_limits",
    "default_or_performance_triggers",
    "rating_required",
    "derivatives_allowed",
    "amortization_profile_defined",
]
FEATURE_LABELS = {
    "asset_class_confirmed": "Lastro confirmado",
    "named_originator_or_cedente": "Cedente/originador nomeado",
    "named_debtor_or_sacado": "Sacado/devedor nomeado",
    "revolving_period": "Revolvência",
    "subordination_minimum": "Subordinação mínima",
    "mezzanine_layer": "Mezanino",
    "cash_or_liquidity_reserve": "Reserva/caixa",
    "repurchase_or_indemnity": "Recompra/indenização",
    "eligibility_criteria": "Elegibilidade",
    "concentration_limits": "Concentração",
    "default_or_performance_triggers": "Triggers/performance",
    "rating_required": "Rating",
    "derivatives_allowed": "Derivativos",
    "amortization_profile_defined": "Amortização definida",
}


@dataclass(frozen=True)
class StudyPaths:
    issuance_dir: Path
    deep_dir: Path
    ime_dir: Path
    output_dir: Path
    app_data_dir: Path


def only_digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def clean_text(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if text.lower() in {"nan", "none", "nat"}:
        return ""
    return text


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def quota_type(value: object) -> str:
    text = normalize_text(value)
    if "senior" in text:
        return "Sênior"
    if "mezan" in text:
        return "Mezanino"
    if "subord" in text:
        return "Subordinada"
    return "Outras"


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def parse_number(value: object) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return math.nan
    text = str(value).strip().replace("\u00a0", " ")
    if text == "" or text.lower() in {"nan", "none", "nat"}:
        return math.nan
    text = re.sub(r"R\$|%|\s", "", text, flags=re.IGNORECASE)
    if not text:
        return math.nan
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return math.nan


def to_num(series: pd.Series) -> pd.Series:
    return series.map(parse_number)


def parse_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.replace("", pd.NA), errors="coerce", dayfirst=True)


def yes_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"sim", "yes", "true", "1"})


def safe_div(a: float, b: float) -> float:
    if not b or pd.isna(b):
        return math.nan
    return a / b


def weighted_average(values: pd.Series, weights: pd.Series) -> float:
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce")
    mask = v.notna() & w.notna() & (w > 0)
    if not mask.any():
        return math.nan
    return float((v[mask] * w[mask]).sum() / w[mask].sum())


def weighted_median(values: pd.Series, weights: pd.Series) -> float:
    frame = pd.DataFrame({"value": pd.to_numeric(values, errors="coerce"), "weight": pd.to_numeric(weights, errors="coerce")})
    frame = frame[frame["value"].notna() & frame["weight"].notna() & (frame["weight"] > 0)].sort_values("value")
    if frame.empty:
        return math.nan
    cutoff = frame["weight"].sum() / 2
    return float(frame.loc[frame["weight"].cumsum() >= cutoff, "value"].iloc[0])


def period_label(year: object) -> str:
    try:
        y = int(float(year))
    except (TypeError, ValueError):
        return "Sem ano"
    return f"{y}FY" if y in {2024, 2025} else f"{y}YTD" if y == 2026 else str(y)


def load_sources(paths: StudyPaths) -> dict[str, pd.DataFrame]:
    return {
        "offers": read_csv(paths.issuance_dir / "fidc_public_offers_2024_2026ytd.csv"),
        "entities": read_csv(paths.issuance_dir / "fidc_cvm_entities_all.csv"),
        "features": read_csv(paths.deep_dir / "fidc_regulatory_feature_matrix.csv"),
        "pricing": read_csv(paths.deep_dir / "fidc_pricing_tranches.csv"),
        "participants": read_csv(paths.deep_dir / "fidc_market_participants_by_sector.csv"),
        "cedentes_sacados": read_csv(paths.deep_dir / "fidc_cedentes_sacados_candidates.csv"),
        "manual_queue": read_csv(paths.deep_dir / "fidc_manual_review_queue_enriched.csv"),
    }


def prepare_offers(offers: pd.DataFrame) -> pd.DataFrame:
    if offers.empty:
        return offers
    frame = offers.copy()
    frame["cnpj"] = frame["cnpj_emissor"].map(only_digits)
    frame["year_num"] = pd.to_numeric(frame["year"], errors="coerce")
    frame["valor_total_registrado_num"] = to_num(frame["valor_total_registrado"])
    for col in ["volume_encerrado_conservador_flag", "volume_registrado_valido_flag", "issuer_born_since_2024_strict"]:
        if col in frame.columns:
            frame[col] = yes_bool(frame[col])
    frame["volume_encerrado_num"] = frame["valor_total_registrado_num"].where(frame["volume_encerrado_conservador_flag"], 0)
    frame["volume_valido_num"] = frame["valor_total_registrado_num"].where(frame["volume_registrado_valido_flag"], 0)
    return frame


def prepare_entities(entities: pd.DataFrame) -> pd.DataFrame:
    if entities.empty:
        return entities
    frame = entities.copy()
    frame["cnpj_entity"] = frame["cnpj_entity"].map(only_digits)
    frame["cnpj_fundo"] = frame.get("cnpj_fundo", "").map(only_digits)
    frame["cnpj_classe"] = frame.get("cnpj_classe", "").map(only_digits)
    frame["patrimonio_liquido_latest_num"] = to_num(frame["patrimonio_liquido_latest"])
    frame["data_patrimonio_liquido_latest_dt"] = parse_date(frame["data_patrimonio_liquido_latest"])
    rows: list[pd.Series] = []
    for cnpj, group in frame.groupby("cnpj_entity", dropna=False):
        if not cnpj:
            continue
        group = group.copy()
        group["_active_score"] = group["situacao_latest"].astype(str).str.contains("Funcionamento", case=False, na=False).astype(int)
        group["_pl_score"] = group["patrimonio_liquido_latest_num"].notna().astype(int)
        group = group.sort_values(
            ["_active_score", "_pl_score", "data_patrimonio_liquido_latest_dt", "latest_data_registro"],
            ascending=[False, False, False, False],
            na_position="last",
        )
        rows.append(group.iloc[0])
    best = pd.DataFrame(rows).drop(columns=[c for c in ["_active_score", "_pl_score"] if c in frame.columns], errors="ignore")
    return best


def prepare_features(features: pd.DataFrame) -> pd.DataFrame:
    if features.empty:
        return features
    frame = features.copy()
    frame["cnpj"] = frame["cnpj"].map(only_digits)
    frame["subordination_main_pct_num"] = to_num(frame["subordination_main_pct"])
    frame["feature_hits_count_num"] = to_num(frame["feature_hits_count"])
    frame["feature_hits_share_num"] = to_num(frame["feature_hits_share"])
    frame["latest_regulamento_date_dt"] = parse_date(frame["latest_regulamento_date"])
    for key in FEATURE_KEYS:
        if key in frame.columns:
            frame[f"{key}_bool"] = yes_bool(frame[key])
    return frame


def prepare_pricing(pricing: pd.DataFrame) -> pd.DataFrame:
    if pricing.empty:
        return pricing
    frame = pricing.copy()
    frame["cnpj"] = frame["cnpj"].map(only_digits)
    frame["volume_brl_num"] = to_num(frame["volume_brl"])
    frame["volume_total_registrado_num"] = to_num(frame["volume_total_registrado"])
    frame["spread_cdi_aa_num"] = to_num(frame["spread_cdi_aa"])
    frame["pct_cdi_num"] = to_num(frame["pct_cdi"])
    frame["spread_ipca_aa_num"] = to_num(frame["spread_ipca_aa"])
    frame["data_deliberacao_dt"] = parse_date(frame["data_deliberacao"])
    frame["year_num"] = frame["data_deliberacao_dt"].dt.year
    frame.loc[frame["year_num"].isna() & frame["periodo_estudo"].str.contains("2024", na=False), "year_num"] = 2024
    frame.loc[frame["year_num"].isna() & frame["periodo_estudo"].str.contains("2025", na=False), "year_num"] = 2025
    frame.loc[frame["year_num"].isna() & frame["periodo_estudo"].str.contains("2026", na=False), "year_num"] = 2026
    return frame


def build_fund_universe(sources: dict[str, pd.DataFrame]) -> pd.DataFrame:
    offers = prepare_offers(sources["offers"])
    entities = prepare_entities(sources["entities"])
    features = prepare_features(sources["features"])

    offer_agg = (
        offers.groupby("cnpj", dropna=False)
        .agg(
            first_offer_date=("data_registro", "min"),
            first_offer_year=("year_num", "min"),
            offers_2024=("year_num", lambda x: int((x == 2024).sum())),
            offers_2025=("year_num", lambda x: int((x == 2025).sum())),
            offers_2026=("year_num", lambda x: int((x == 2026).sum())),
            volume_2024_brl=("volume_encerrado_num", lambda x: float(x[offers.loc[x.index, "year_num"] == 2024].sum())),
            volume_2025_brl=("volume_encerrado_num", lambda x: float(x[offers.loc[x.index, "year_num"] == 2025].sum())),
            volume_2026_brl=("volume_encerrado_num", lambda x: float(x[offers.loc[x.index, "year_num"] == 2026].sum())),
            valid_volume_2024_brl=("volume_valido_num", lambda x: float(x[offers.loc[x.index, "year_num"] == 2024].sum())),
            valid_volume_2025_brl=("volume_valido_num", lambda x: float(x[offers.loc[x.index, "year_num"] == 2025].sum())),
            valid_volume_2026_brl=("volume_valido_num", lambda x: float(x[offers.loc[x.index, "year_num"] == 2026].sum())),
            offer_rows=("cnpj", "size"),
        )
        .reset_index()
    )
    offer_agg["emission_cohort"] = offer_agg["first_offer_year"].map(period_label)
    offer_agg["emitted_2024"] = offer_agg["offers_2024"] > 0
    offer_agg["emitted_2025"] = offer_agg["offers_2025"] > 0

    entity_cols = [
        "cnpj_entity",
        "nome_entity",
        "entity_kind",
        "situacao_latest",
        "administrador",
        "gestor",
        "custodiante",
        "patrimonio_liquido_latest_num",
        "data_patrimonio_liquido_latest",
        "first_known_date",
        "born_since_2024_strict",
    ]
    entity_view = entities[[c for c in entity_cols if c in entities.columns]].rename(columns={"cnpj_entity": "cnpj"})

    feature_cols = [
        "cnpj",
        "fund_name",
        "setor_n1_final",
        "setor_n2_final",
        "final_classification_source",
        "metadata_confidence",
        "regulamento_count",
        "document_count_total",
        "latest_regulamento_date",
        "subordination_main_pct_num",
        "subordination_all_pcts",
        "monocedente_or_multicedente",
        "concentrated_or_pulverized_debtors",
        "credit_rights_allocation_min_pct",
        "cash_reserve_main_pct",
        "concentration_limit_main_pct",
        "default_trigger_main_pct",
        "feature_hits_count_num",
        "feature_hits_share_num",
    ] + [f"{key}_bool" for key in FEATURE_KEYS if f"{key}_bool" in features.columns]
    feature_view = features[[c for c in feature_cols if c in features.columns]]

    cnpjs = sorted(set(offer_agg["cnpj"]) | set(entity_view["cnpj"]) | set(feature_view["cnpj"]))
    universe = pd.DataFrame({"cnpj": cnpjs})
    universe = universe.merge(offer_agg, on="cnpj", how="left")
    universe = universe.merge(entity_view, on="cnpj", how="left")
    universe = universe.merge(feature_view, on="cnpj", how="left")
    universe["fund_name_final"] = universe["fund_name"].where(universe["fund_name"].astype(str).str.strip() != "", universe["nome_entity"])
    universe["setor_n1"] = universe["setor_n1_final"].fillna("").replace("", "Não classificado")
    universe["setor_n2"] = universe["setor_n2_final"].fillna("").replace("", "Sem classificação")
    universe["pl_atual_brl"] = universe["patrimonio_liquido_latest_num"]
    universe["subordination_estimated_brl"] = universe["pl_atual_brl"] * universe["subordination_main_pct_num"] / 100
    universe["has_regulatory_matrix"] = universe["regulamento_count"].notna()
    return universe


def build_feature_long(universe: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    evidence_lookup = features.set_index("cnpj", drop=False) if not features.empty else pd.DataFrame()
    for _, row in universe.iterrows():
        has_matrix_value = row.get("has_regulatory_matrix", False)
        has_matrix = False if pd.isna(has_matrix_value) else bool(has_matrix_value)
        if not has_matrix:
            continue
        cnpj = row["cnpj"]
        source_row = evidence_lookup.loc[cnpj] if cnpj in evidence_lookup.index else None
        if isinstance(source_row, pd.DataFrame):
            source_row = source_row.iloc[0]
        for key in FEATURE_KEYS:
            bool_col = f"{key}_bool"
            has_feature = bool(row.get(bool_col, False)) if bool_col in universe.columns else False
            evidence = ""
            if source_row is not None and f"{key}_evidence" in source_row.index:
                evidence = clean_text(source_row.get(f"{key}_evidence"))
            rows.append(
                {
                    "cnpj": cnpj,
                    "fund_name": row.get("fund_name_final", ""),
                    "setor_n1": row.get("setor_n1", "Não classificado"),
                    "setor_n2": row.get("setor_n2", "Sem classificação"),
                    "emission_cohort": row.get("emission_cohort", ""),
                    "emitted_2024": row.get("emitted_2024", False),
                    "emitted_2025": row.get("emitted_2025", False),
                    "has_regulatory_matrix": has_matrix,
                    "feature_key": key,
                    "feature_label": FEATURE_LABELS[key],
                    "has_feature": has_feature,
                    "evidence": evidence,
                    "pl_atual_brl": row.get("pl_atual_brl", math.nan),
                    "volume_2024_brl": row.get("volume_2024_brl", 0),
                    "volume_2025_brl": row.get("volume_2025_brl", 0),
                }
            )
    return pd.DataFrame(rows)


def build_feature_heatmaps(feature_long: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if feature_long.empty:
        return pd.DataFrame(), pd.DataFrame()
    grouped_frames: list[pd.DataFrame] = []
    for cohort, flag_col, volume_col in [
        ("2024FY", "emitted_2024", "volume_2024_brl"),
        ("2025FY", "emitted_2025", "volume_2025_brl"),
    ]:
        scoped = feature_long[feature_long[flag_col].fillna(False).astype(bool)].copy()
        if scoped.empty:
            continue
        scoped["emission_cohort"] = cohort
        grouped_frames.append(
            scoped.groupby(["emission_cohort", "setor_n1", "setor_n2", "feature_key", "feature_label"], dropna=False)
            .agg(
                funds=("cnpj", "nunique"),
                feature_count=("has_feature", "sum"),
                feature_share=("has_feature", "mean"),
                pl_weighted_share=("has_feature", lambda x: weighted_average(x.astype(float), scoped.loc[x.index, "pl_atual_brl"])),
                volume_cohort_weighted_share=("has_feature", lambda x: weighted_average(x.astype(float), scoped.loc[x.index, volume_col])),
                volume_2024_weighted_share=("has_feature", lambda x: weighted_average(x.astype(float), scoped.loc[x.index, "volume_2024_brl"])),
                volume_2025_weighted_share=("has_feature", lambda x: weighted_average(x.astype(float), scoped.loc[x.index, "volume_2025_brl"])),
            )
            .reset_index()
        )
    grouped = pd.concat(grouped_frames, ignore_index=True) if grouped_frames else pd.DataFrame()
    current = (
        feature_long.groupby(["setor_n1", "setor_n2", "feature_key", "feature_label"], dropna=False)
        .agg(
            funds=("cnpj", "nunique"),
            feature_count=("has_feature", "sum"),
            feature_share=("has_feature", "mean"),
            pl_weighted_share=("has_feature", lambda x: weighted_average(x.astype(float), feature_long.loc[x.index, "pl_atual_brl"])),
        )
        .reset_index()
    )
    return grouped, current


def build_subordination(universe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail = universe[
        [
            "cnpj",
            "fund_name_final",
            "setor_n1",
            "setor_n2",
            "emission_cohort",
            "first_offer_year",
            "emitted_2024",
            "emitted_2025",
            "offers_2024",
            "offers_2025",
            "volume_2024_brl",
            "volume_2025_brl",
            "pl_atual_brl",
            "data_patrimonio_liquido_latest",
            "subordination_main_pct_num",
            "subordination_estimated_brl",
            "subordination_all_pcts",
            "monocedente_or_multicedente",
            "concentrated_or_pulverized_debtors",
            "latest_regulamento_date",
        ]
    ].copy()
    detail = detail.rename(
        columns={
            "fund_name_final": "fund_name",
            "subordination_main_pct_num": "subordination_main_pct",
        }
    )
    rows: list[dict[str, object]] = []
    for cohort, flag_col in [("2024FY", "emitted_2024"), ("2025FY", "emitted_2025")]:
        scoped = detail[detail[flag_col].fillna(False).astype(bool)].copy()
        for (s1, s2), group in scoped.groupby(["setor_n1", "setor_n2"], dropna=False):
            values = pd.to_numeric(group["subordination_main_pct"], errors="coerce")
            has = group[values.notna()].copy()
            rows.append(
                {
                    "emission_cohort": cohort,
                    "setor_n1": s1,
                    "setor_n2": s2,
                    "funds_total": int(group["cnpj"].nunique()),
                    "funds_with_subordination_pct": int(has["cnpj"].nunique()),
                    "coverage_pct": safe_div(float(has["cnpj"].nunique()), float(group["cnpj"].nunique())) * 100,
                    "subordination_median_equal_weight_pct": float(values.median()) if values.notna().any() else math.nan,
                    "subordination_p25_pct": float(values.quantile(0.25)) if values.notna().any() else math.nan,
                    "subordination_p75_pct": float(values.quantile(0.75)) if values.notna().any() else math.nan,
                    "subordination_weighted_by_pl_pct": weighted_average(group["subordination_main_pct"], group["pl_atual_brl"]),
                    "subordination_weighted_by_issued_volume_pct": weighted_average(
                        group["subordination_main_pct"],
                        group["volume_2024_brl"] if cohort == "2024FY" else group["volume_2025_brl"],
                    ),
                    "current_pl_total_brl": float(pd.to_numeric(group["pl_atual_brl"], errors="coerce").sum(skipna=True)),
                    "estimated_subordination_capital_brl": float(pd.to_numeric(group["subordination_estimated_brl"], errors="coerce").sum(skipna=True)),
                    "closed_issued_volume_brl": float(pd.to_numeric(group["volume_2024_brl" if cohort == "2024FY" else "volume_2025_brl"], errors="coerce").sum(skipna=True)),
                }
            )
    return detail, pd.DataFrame(rows).sort_values(["emission_cohort", "current_pl_total_brl"], ascending=[True, False])


def enrich_pricing(pricing: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    frame = prepare_pricing(pricing)
    cols = [
        "cnpj",
        "fund_name_final",
        "setor_n1",
        "setor_n2",
        "emission_cohort",
        "pl_atual_brl",
        "subordination_main_pct_num",
        "feature_hits_share_num",
    ]
    frame = frame.merge(universe[[c for c in cols if c in universe.columns]], on="cnpj", how="left")
    if "setor_n1_y" in frame.columns or "setor_n1_x" in frame.columns:
        frame["setor_n1"] = frame.get("setor_n1_y", "").replace("", pd.NA).fillna(frame.get("setor_n1_x", ""))
    if "setor_n2_y" in frame.columns or "setor_n2_x" in frame.columns:
        frame["setor_n2"] = frame.get("setor_n2_y", "").replace("", pd.NA).fillna(frame.get("setor_n2_x", ""))
    frame["setor_n1"] = frame["setor_n1"].fillna("").replace("", "Não classificado")
    frame["setor_n2"] = frame["setor_n2"].fillna("").replace("", "Sem classificação")
    frame["tipo_cota_normalizado"] = frame["tipo_cota_normalizado"].replace("", "Não identificado")
    frame["pricing_year"] = pd.to_numeric(frame["year_num"], errors="coerce")
    frame["pricing_period"] = frame["pricing_year"].map(period_label)
    return frame


def build_pricing_summary(pricing_enriched: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    senior = pricing_enriched[
        pricing_enriched["tipo_cota_normalizado"].astype(str).str.contains("Sênior|Senior", case=False, na=False)
        & pricing_enriched["pricing_year"].isin([2024, 2025])
    ].copy()
    for (period, s1, s2), group in senior.groupby(["pricing_period", "setor_n1", "setor_n2"], dropna=False):
        spread = pd.to_numeric(group["spread_cdi_aa_num"], errors="coerce")
        pct_cdi = pd.to_numeric(group["pct_cdi_num"], errors="coerce")
        ipca = pd.to_numeric(group["spread_ipca_aa_num"], errors="coerce")
        volume = pd.to_numeric(group["volume_brl_num"], errors="coerce").fillna(0)
        fund_spread = (
            group[group["spread_cdi_aa_num"].notna()]
            .groupby("cnpj")
            .apply(lambda x: pd.Series({
                "fund_spread_cdi_aa": weighted_average(x["spread_cdi_aa_num"], x["volume_brl_num"].fillna(1)),
                "fund_pl": pd.to_numeric(x["pl_atual_brl"], errors="coerce").max(),
            }), include_groups=False)
            .reset_index()
        )
        rows.append(
            {
                "pricing_period": period,
                "setor_n1": s1,
                "setor_n2": s2,
                "senior_tranche_rows": int(len(group)),
                "funds": int(group["cnpj"].nunique()),
                "volume_brl": float(volume.sum()),
                "spread_cdi_coverage_rows": int(spread.notna().sum()),
                "spread_cdi_coverage_pct": safe_div(float(spread.notna().sum()), float(len(group))) * 100,
                "spread_cdi_median_equal_weight_aa": float(spread.median()) if spread.notna().any() else math.nan,
                "spread_cdi_p25_aa": float(spread.quantile(0.25)) if spread.notna().any() else math.nan,
                "spread_cdi_p75_aa": float(spread.quantile(0.75)) if spread.notna().any() else math.nan,
                "spread_cdi_weighted_by_issue_volume_aa": weighted_average(group["spread_cdi_aa_num"], group["volume_brl_num"]),
                "spread_cdi_weighted_by_current_pl_aa": weighted_average(fund_spread["fund_spread_cdi_aa"], fund_spread["fund_pl"]) if not fund_spread.empty else math.nan,
                "pct_cdi_median_equal_weight": float(pct_cdi.median()) if pct_cdi.notna().any() else math.nan,
                "pct_cdi_weighted_by_issue_volume": weighted_average(group["pct_cdi_num"], group["volume_brl_num"]),
                "ipca_spread_median_equal_weight_aa": float(ipca.median()) if ipca.notna().any() else math.nan,
                "current_pl_total_brl": float(pd.to_numeric(group["pl_atual_brl"], errors="coerce").drop_duplicates().sum(skipna=True)),
            }
        )
    senior_summary = pd.DataFrame(rows).sort_values(["pricing_period", "volume_brl"], ascending=[True, False])

    quota_rows: list[dict[str, object]] = []
    scoped = pricing_enriched[pricing_enriched["pricing_year"].isin([2024, 2025])].copy()
    for (period, s1, s2, quota), group in scoped.groupby(["pricing_period", "setor_n1", "setor_n2", "tipo_cota_normalizado"], dropna=False):
        quota_rows.append(
            {
                "pricing_period": period,
                "setor_n1": s1,
                "setor_n2": s2,
                "tipo_cota": quota,
                "tranche_rows": int(len(group)),
                "funds": int(group["cnpj"].nunique()),
                "volume_brl": float(pd.to_numeric(group["volume_brl_num"], errors="coerce").sum(skipna=True)),
                "spread_cdi_median_equal_weight_aa": float(pd.to_numeric(group["spread_cdi_aa_num"], errors="coerce").median(skipna=True)),
                "spread_cdi_weighted_by_issue_volume_aa": weighted_average(group["spread_cdi_aa_num"], group["volume_brl_num"]),
                "pct_cdi_median_equal_weight": float(pd.to_numeric(group["pct_cdi_num"], errors="coerce").median(skipna=True)),
                "coverage_spread_cdi_pct": safe_div(float(pd.to_numeric(group["spread_cdi_aa_num"], errors="coerce").notna().sum()), float(len(group))) * 100,
            }
        )
    return senior_summary, pd.DataFrame(quota_rows).sort_values(["pricing_period", "setor_n1", "volume_brl"], ascending=[True, True, False])


def build_ime_cache_summary() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for manifest_path in Path(".cache/fundonet-ime").glob("*/manifest.json"):
        rows.append(_ime_manifest_row(manifest_path))
    for zip_path in Path("data/ime_cache/fundonet-ime").glob("*.zip"):
        try:
            with zipfile.ZipFile(zip_path) as archive:
                with archive.open("manifest.json") as f:
                    manifest = json.loads(f.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        rows.append(
            {
                "cache_source": "portable_zip",
                "cache_path": str(zip_path),
                "cnpj": only_digits(manifest.get("cnpj_fundo")),
                "data_inicial": manifest.get("data_inicial", ""),
                "data_final": manifest.get("data_final", ""),
                "cache_key": manifest.get("cache_key", ""),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.drop_duplicates(["cnpj", "data_inicial", "data_final", "cache_key"])


def read_ime_table(ime_dir: Path, table_token: str) -> pd.DataFrame:
    if not ime_dir.exists():
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    pattern = f"_tab_{table_token}_"
    for zip_path in sorted(ime_dir.glob("inf_mensal_fidc_*.zip")):
        try:
            with zipfile.ZipFile(zip_path) as archive:
                for member in archive.namelist():
                    if pattern not in member:
                        continue
                    with archive.open(member) as f:
                        frame = pd.read_csv(f, sep=";", encoding="latin1", dtype=str, keep_default_na=False)
                    frame["source_zip"] = zip_path.name
                    frame["source_file"] = member
                    frames.append(frame)
        except zipfile.BadZipFile:
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_ime_current_snapshot(ime_dir: Path, universe: pd.DataFrame) -> pd.DataFrame:
    tab_iv = read_ime_table(ime_dir, "IV")
    tab_x2 = read_ime_table(ime_dir, "X_2")
    if tab_iv.empty and tab_x2.empty:
        return pd.DataFrame()

    base_cols = [
        "cnpj",
        "fund_name_final",
        "setor_n1",
        "setor_n2",
        "emitted_2024",
        "emitted_2025",
        "pl_atual_brl",
    ]
    base = universe[[c for c in base_cols if c in universe.columns]].copy()

    latest_pl = pd.DataFrame()
    if not tab_iv.empty:
        tab_iv["cnpj"] = tab_iv["CNPJ_FUNDO_CLASSE"].map(only_digits)
        tab_iv["ime_dt_comptc"] = parse_date(tab_iv["DT_COMPTC"])
        tab_iv["ime_pl_brl"] = to_num(tab_iv["TAB_IV_A_VL_PL"])
        tab_iv["ime_pl_medio_brl"] = to_num(tab_iv["TAB_IV_B_VL_PL_MEDIO"])
        latest_pl = (
            tab_iv.sort_values(["cnpj", "ime_dt_comptc"])
            .groupby("cnpj", dropna=False)
            .tail(1)[["cnpj", "DENOM_SOCIAL", "ime_dt_comptc", "ime_pl_brl", "ime_pl_medio_brl"]]
            .rename(columns={"DENOM_SOCIAL": "ime_denom_social"})
        )

    quota_pivot = pd.DataFrame({"cnpj": []})
    if not tab_x2.empty:
        tab_x2["cnpj"] = tab_x2["CNPJ_FUNDO_CLASSE"].map(only_digits)
        tab_x2["ime_dt_comptc"] = parse_date(tab_x2["DT_COMPTC"])
        tab_x2["quota_type"] = tab_x2["TAB_X_CLASSE_SERIE"].map(quota_type)
        tab_x2["quota_qty"] = to_num(tab_x2["TAB_X_QT_COTA"])
        tab_x2["quota_value"] = to_num(tab_x2["TAB_X_VL_COTA"])
        tab_x2["quota_nav_brl"] = tab_x2["quota_qty"] * tab_x2["quota_value"]
        latest_dt = tab_x2.groupby("cnpj", dropna=False)["ime_dt_comptc"].transform("max")
        latest_x2 = tab_x2[tab_x2["ime_dt_comptc"] == latest_dt].copy()
        quota_agg = (
            latest_x2.groupby(["cnpj", "quota_type"], dropna=False)
            .agg(
                quota_nav_brl=("quota_nav_brl", "sum"),
                quota_qty=("quota_qty", "sum"),
                classes=("TAB_X_CLASSE_SERIE", "nunique"),
            )
            .reset_index()
        )
        nav = quota_agg.pivot_table(index="cnpj", columns="quota_type", values="quota_nav_brl", aggfunc="sum", fill_value=0)
        qty = quota_agg.pivot_table(index="cnpj", columns="quota_type", values="quota_qty", aggfunc="sum", fill_value=0)
        cls = quota_agg.pivot_table(index="cnpj", columns="quota_type", values="classes", aggfunc="sum", fill_value=0)
        quota_pivot = pd.DataFrame(index=sorted(set(quota_agg["cnpj"])))
        for label in ["Sênior", "Mezanino", "Subordinada", "Outras"]:
            quota_pivot[f"{label}_quota_nav_brl"] = nav[label] if label in nav.columns else 0.0
            quota_pivot[f"{label}_quota_qty"] = qty[label] if label in qty.columns else 0.0
            quota_pivot[f"{label}_classes"] = cls[label] if label in cls.columns else 0.0
        quota_pivot = quota_pivot.reset_index().rename(columns={"index": "cnpj"})

    snapshot = base.merge(latest_pl, on="cnpj", how="outer").merge(quota_pivot, on="cnpj", how="outer")
    for label in ["Sênior", "Mezanino", "Subordinada", "Outras"]:
        for suffix in ["quota_nav_brl", "quota_qty", "classes"]:
            col = f"{label}_{suffix}"
            if col not in snapshot.columns:
                snapshot[col] = 0.0
            snapshot[col] = pd.to_numeric(snapshot[col], errors="coerce").fillna(0)
    snapshot["quota_total_nav_brl"] = snapshot[["Sênior_quota_nav_brl", "Mezanino_quota_nav_brl", "Subordinada_quota_nav_brl", "Outras_quota_nav_brl"]].sum(axis=1)
    snapshot["subordinated_plus_mezz_nav_brl"] = snapshot["Mezanino_quota_nav_brl"] + snapshot["Subordinada_quota_nav_brl"]
    snapshot["actual_subordination_ime_pct"] = snapshot.apply(
        lambda row: safe_div(row["subordinated_plus_mezz_nav_brl"], row["quota_total_nav_brl"]) * 100,
        axis=1,
    )
    snapshot["senior_share_ime_pct"] = snapshot.apply(lambda row: safe_div(row["Sênior_quota_nav_brl"], row["quota_total_nav_brl"]) * 100, axis=1)
    snapshot["ime_pl_vs_cadastro_delta_pct"] = (
        (pd.to_numeric(snapshot["ime_pl_brl"], errors="coerce") - pd.to_numeric(snapshot["pl_atual_brl"], errors="coerce"))
        / pd.to_numeric(snapshot["pl_atual_brl"], errors="coerce")
        * 100
    )
    return snapshot


def build_ime_current_subordination_by_sector(snapshot: pd.DataFrame) -> pd.DataFrame:
    if snapshot.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for cohort, flag_col, volume_col in [("2024FY", "emitted_2024", "volume_2024_brl"), ("2025FY", "emitted_2025", "volume_2025_brl")]:
        scoped = snapshot[snapshot[flag_col].fillna(False).astype(bool)].copy() if flag_col in snapshot.columns else pd.DataFrame()
        if scoped.empty:
            continue
        for (s1, s2), group in scoped.groupby(["setor_n1", "setor_n2"], dropna=False):
            values = pd.to_numeric(group["actual_subordination_ime_pct"], errors="coerce")
            with_values = group[values.notna()].copy()
            rows.append(
                {
                    "emission_cohort": cohort,
                    "setor_n1": s1,
                    "setor_n2": s2,
                    "funds_total": int(group["cnpj"].nunique()),
                    "funds_with_ime_quota_structure": int(with_values["cnpj"].nunique()),
                    "coverage_pct": safe_div(float(with_values["cnpj"].nunique()), float(group["cnpj"].nunique())) * 100,
                    "actual_subordination_median_equal_weight_pct": float(values.median()) if values.notna().any() else math.nan,
                    "actual_subordination_p25_pct": float(values.quantile(0.25)) if values.notna().any() else math.nan,
                    "actual_subordination_p75_pct": float(values.quantile(0.75)) if values.notna().any() else math.nan,
                    "actual_subordination_weighted_by_current_ime_pl_pct": weighted_average(group["actual_subordination_ime_pct"], group["ime_pl_brl"]),
                    "actual_subordination_weighted_by_quota_nav_pct": weighted_average(group["actual_subordination_ime_pct"], group["quota_total_nav_brl"]),
                    "current_ime_pl_total_brl": float(pd.to_numeric(group["ime_pl_brl"], errors="coerce").sum(skipna=True)),
                    "senior_quota_nav_total_brl": float(pd.to_numeric(group["Sênior_quota_nav_brl"], errors="coerce").sum(skipna=True)),
                    "subordinated_plus_mezz_nav_total_brl": float(pd.to_numeric(group["subordinated_plus_mezz_nav_brl"], errors="coerce").sum(skipna=True)),
                }
            )
    return pd.DataFrame(rows).sort_values(["emission_cohort", "current_ime_pl_total_brl"], ascending=[True, False])


def build_ime_cota_movements(ime_dir: Path, universe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    tab_x4 = read_ime_table(ime_dir, "X_4")
    if tab_x4.empty:
        return pd.DataFrame(), pd.DataFrame()
    frame = tab_x4.copy()
    frame["cnpj"] = frame["CNPJ_FUNDO_CLASSE"].map(only_digits)
    frame["dt_comptc"] = parse_date(frame["DT_COMPTC"])
    frame["year_num"] = frame["dt_comptc"].dt.year
    frame["periodo"] = frame["year_num"].map(period_label)
    frame["quota_type"] = frame["TAB_X_CLASSE_SERIE"].map(quota_type)
    frame["operation_type"] = frame["TAB_X_TP_OPER"].map(clean_text)
    frame["movement_volume_brl"] = to_num(frame["TAB_X_VL_TOTAL"]).fillna(0)
    frame["movement_quota_qty"] = to_num(frame["TAB_X_QT_COTA"]).fillna(0)
    frame["unit_price"] = frame.apply(lambda row: safe_div(row["movement_volume_brl"], row["movement_quota_qty"]), axis=1)
    cols = ["cnpj", "fund_name_final", "setor_n1", "setor_n2", "pl_atual_brl", "emitted_2024", "emitted_2025"]
    frame = frame.merge(universe[[c for c in cols if c in universe.columns]], on="cnpj", how="left")
    frame["setor_n1"] = frame["setor_n1"].fillna("Não classificado")
    frame["setor_n2"] = frame["setor_n2"].fillna("Sem classificação")
    frame = frame[
        [
            "cnpj",
            "fund_name_final",
            "dt_comptc",
            "periodo",
            "setor_n1",
            "setor_n2",
            "quota_type",
            "operation_type",
            "movement_volume_brl",
            "movement_quota_qty",
            "unit_price",
            "pl_atual_brl",
            "source_zip",
            "source_file",
        ]
    ].copy()

    rows: list[dict[str, object]] = []
    scoped = frame[frame["periodo"].isin(["2024FY", "2025FY"])].copy()
    scoped = scoped[pd.to_numeric(scoped["movement_volume_brl"], errors="coerce") > 0]
    for (period, s1, s2, qtype, operation), group in scoped.groupby(["periodo", "setor_n1", "setor_n2", "quota_type", "operation_type"], dropna=False):
        fund_unit = (
            group[pd.to_numeric(group["unit_price"], errors="coerce").notna()]
            .groupby("cnpj")
            .apply(
                lambda x: pd.Series(
                    {
                        "fund_unit_price": weighted_average(x["unit_price"], x["movement_volume_brl"]),
                        "fund_pl": pd.to_numeric(x["pl_atual_brl"], errors="coerce").max(),
                    }
                ),
                include_groups=False,
            )
            .reset_index()
        )
        rows.append(
            {
                "periodo": period,
                "setor_n1": s1,
                "setor_n2": s2,
                "quota_type": qtype,
                "operation_type": operation,
                "movement_rows": int(len(group)),
                "funds": int(group["cnpj"].nunique()),
                "movement_volume_brl": float(pd.to_numeric(group["movement_volume_brl"], errors="coerce").sum(skipna=True)),
                "unit_price_coverage_pct": safe_div(float(pd.to_numeric(group["unit_price"], errors="coerce").notna().sum()), float(len(group))) * 100,
                "unit_price_median_equal_weight": float(pd.to_numeric(group["unit_price"], errors="coerce").median(skipna=True)),
                "unit_price_weighted_by_movement_volume": weighted_average(group["unit_price"], group["movement_volume_brl"]),
                "unit_price_weighted_by_current_pl": weighted_average(fund_unit["fund_unit_price"], fund_unit["fund_pl"]) if not fund_unit.empty else math.nan,
            }
        )
    summary = pd.DataFrame(rows).sort_values(["periodo", "movement_volume_brl"], ascending=[True, False]) if rows else pd.DataFrame()
    return frame, summary


def _ime_manifest_row(manifest_path: Path) -> dict[str, object]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        manifest = {}
    return {
        "cache_source": "runtime",
        "cache_path": str(manifest_path.parent),
        "cnpj": only_digits(manifest.get("cnpj_fundo")),
        "data_inicial": manifest.get("data_inicial", ""),
        "data_final": manifest.get("data_final", ""),
        "cache_key": manifest.get("cache_key", manifest_path.parent.name),
    }


def build_opportunities(
    subordination_summary: pd.DataFrame,
    senior_pricing_summary: pd.DataFrame,
    feature_heatmap: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if not senior_pricing_summary.empty:
        benchmark = pd.to_numeric(senior_pricing_summary["spread_cdi_median_equal_weight_aa"], errors="coerce").median()
        for _, row in senior_pricing_summary.head(60).iterrows():
            spread = parse_number(row.get("spread_cdi_median_equal_weight_aa"))
            volume = parse_number(row.get("volume_brl"))
            if pd.notna(spread) and pd.notna(benchmark) and spread > benchmark + 1 and volume > 100_000_000:
                rows.append(
                    {
                        "tema": "Pricing acima da mediana",
                        "periodo": row["pricing_period"],
                        "setor_n1": row["setor_n1"],
                        "setor_n2": row["setor_n2"],
                        "sinal": f"Spread CDI mediano {spread:.2f}% a.a. vs benchmark {benchmark:.2f}% a.a.",
                        "ideia_estrutura": "Avaliar senior tranche com reforço de crédito incremental, gatilhos operacionais e covenant de elegibilidade para comprimir spread sem perder proteção.",
                        "materialidade_brl": volume,
                    }
                )
    if not subordination_summary.empty:
        for _, row in subordination_summary.iterrows():
            pl = parse_number(row.get("current_pl_total_brl"))
            med = parse_number(row.get("subordination_median_equal_weight_pct"))
            coverage = parse_number(row.get("coverage_pct"))
            if pd.notna(pl) and pl > 300_000_000 and pd.notna(med) and med < 10 and pd.notna(coverage) and coverage >= 25:
                rows.append(
                    {
                        "tema": "Subordinação baixa em mercado material",
                        "periodo": row["emission_cohort"],
                        "setor_n1": row["setor_n1"],
                        "setor_n2": row["setor_n2"],
                        "sinal": f"Mediana equal-weight de subordinação {med:.1f}% com PL atual agregado relevante.",
                        "ideia_estrutura": "Estrutura comercial pode testar reserva dinâmica, overcollateral escalonado ou gatilhos de spread excess como alternativa a subordinação estática alta.",
                        "materialidade_brl": pl,
                    }
                )
    if not feature_heatmap.empty:
        target = feature_heatmap[
            (feature_heatmap["feature_key"].isin(["cash_or_liquidity_reserve", "default_or_performance_triggers", "concentration_limits"]))
            & (pd.to_numeric(feature_heatmap["feature_share"], errors="coerce") < 0.55)
            & (pd.to_numeric(feature_heatmap["funds"], errors="coerce") >= 8)
        ].copy()
        for _, row in target.head(40).iterrows():
            rows.append(
                {
                    "tema": "Cláusula-chave menos comum",
                    "periodo": row["emission_cohort"],
                    "setor_n1": row["setor_n1"],
                    "setor_n2": row["setor_n2"],
                    "sinal": f"{row['feature_label']} aparece em {float(row['feature_share']) * 100:.1f}% dos fundos lidos.",
                    "ideia_estrutura": "Usar a lacuna como argumento comercial: padronizar cláusula verificável em IME e reduzir fricção de comitê/ratings.",
                    "materialidade_brl": math.nan,
                }
            )
    return pd.DataFrame(rows)


def write_sqlite(tables: dict[str, pd.DataFrame], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as conn:
        for name, frame in tables.items():
            clean = frame.copy()
            clean.columns = make_sqlite_columns(clean.columns)
            for col in clean.columns:
                if pd.api.types.is_datetime64_any_dtype(clean[col]):
                    clean[col] = clean[col].dt.strftime("%Y-%m-%d")
            clean.to_sql(name, conn, index=False, if_exists="replace")
        conn.execute(
            "CREATE TABLE study_metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        metadata = {
            "run_timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "as_of_date": AS_OF_DATE,
            "tables": ",".join(tables.keys()),
        }
        conn.executemany("INSERT INTO study_metadata (key, value) VALUES (?, ?)", metadata.items())


def make_unique_columns(columns: Iterable[object]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for column in columns:
        base = str(column)
        count = seen.get(base, 0)
        seen[base] = count + 1
        out.append(base if count == 0 else f"{base}_{count + 1}")
    return out


def make_sqlite_columns(columns: Iterable[object]) -> list[str]:
    normalized = []
    for column in columns:
        text = str(column).strip().lower()
        text = re.sub(r"[^a-z0-9_]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        normalized.append(text or "col")
    return make_unique_columns(normalized)


def write_report(tables: dict[str, pd.DataFrame], output_dir: Path, app_db_path: Path) -> None:
    fund_universe = tables["fund_universe"]
    sub = tables["subordination_by_sector_year"]
    senior = tables["pricing_senior_by_sector_year"]
    opp = tables["market_opportunities"]
    ime_current = tables.get("ime_current_snapshot", pd.DataFrame())
    ime_price = tables.get("ime_cota_price_by_sector_year", pd.DataFrame())
    ime_dates = pd.to_datetime(ime_current.get("ime_dt_comptc", pd.Series(dtype=str)), errors="coerce") if not ime_current.empty else pd.Series(dtype="datetime64[ns]")
    lines = [
        "# FIDC Credit Strategy Study",
        "",
        f"Data-base: {AS_OF_DATE}.",
        "",
        "## O que a base responde",
        "",
        "- O que consta/não consta nos regulamentos por subtipo e por coorte de emissão 2024 vs 2025.",
        "- Tamanho atual de subordinação mínima por subtipo, com leitura equal-weight, ponderada por PL atual e ponderada por volume emitido.",
        "- Pricing de cotas seniores por subtipo, separando mediana equal-weight, média ponderada por volume e média ponderada por PL atual.",
        "- Ideias comerciais/estruturais derivadas de lacunas de cláusulas, spreads altos e subordinação baixa em mercados materiais.",
        "",
        "## Cobertura",
        "",
        f"- Fundos/CNPJs na base consolidada: {fund_universe['cnpj'].nunique():,}.",
        f"- Fundos com matriz regulatória lida: {int(fund_universe['has_regulatory_matrix'].sum()):,}.",
        f"- Fundos emitidos em 2024 com matriz: {int((fund_universe['emitted_2024'].fillna(False) & fund_universe['has_regulatory_matrix']).sum()):,}.",
        f"- Fundos emitidos em 2025 com matriz: {int((fund_universe['emitted_2025'].fillna(False) & fund_universe['has_regulatory_matrix']).sum()):,}.",
        f"- Informes Mensais CVM integrados: {ime_dates.min().date() if ime_dates.notna().any() else 'n/d'} a {ime_dates.max().date() if ime_dates.notna().any() else 'n/d'}.",
        f"- Cortes de preço unitário de cotas no IME: {len(ime_price):,}.",
        f"- SQLite para Streamlit: `{app_db_path}`.",
        "",
        "## Top subtipos por PL atual e subordinação",
        "",
        "| Coorte | Setor | Subtipo | Fundos | Cobertura % | Mediana subord. | Ponderada por PL | PL atual |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in sub.head(15).iterrows():
        lines.append(
            "| {cohort} | {s1} | {s2} | {funds:,} | {cov:.1f}% | {med:.1f}% | {plw:.1f}% | R$ {pl:,.0f} |".format(
                cohort=row["emission_cohort"],
                s1=row["setor_n1"],
                s2=row["setor_n2"],
                funds=int(row["funds_total"]),
                cov=float(row["coverage_pct"]) if pd.notna(row["coverage_pct"]) else 0,
                med=float(row["subordination_median_equal_weight_pct"]) if pd.notna(row["subordination_median_equal_weight_pct"]) else float("nan"),
                plw=float(row["subordination_weighted_by_pl_pct"]) if pd.notna(row["subordination_weighted_by_pl_pct"]) else float("nan"),
                pl=float(row["current_pl_total_brl"]) if pd.notna(row["current_pl_total_brl"]) else 0,
            )
        )
    lines.extend(
        [
            "",
            "## Top pricing senior por volume",
            "",
            "| Período | Setor | Subtipo | Linhas | Volume | Mediana CDI+ | Ponderado volume | Ponderado PL | Cobertura spread |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in senior.head(15).iterrows():
        lines.append(
            "| {period} | {s1} | {s2} | {rows:,} | R$ {vol:,.0f} | {med:.2f}% | {vw:.2f}% | {plw:.2f}% | {cov:.1f}% |".format(
                period=row["pricing_period"],
                s1=row["setor_n1"],
                s2=row["setor_n2"],
                rows=int(row["senior_tranche_rows"]),
                vol=float(row["volume_brl"]) if pd.notna(row["volume_brl"]) else 0,
                med=float(row["spread_cdi_median_equal_weight_aa"]) if pd.notna(row["spread_cdi_median_equal_weight_aa"]) else float("nan"),
                vw=float(row["spread_cdi_weighted_by_issue_volume_aa"]) if pd.notna(row["spread_cdi_weighted_by_issue_volume_aa"]) else float("nan"),
                plw=float(row["spread_cdi_weighted_by_current_pl_aa"]) if pd.notna(row["spread_cdi_weighted_by_current_pl_aa"]) else float("nan"),
                cov=float(row["spread_cdi_coverage_pct"]) if pd.notna(row["spread_cdi_coverage_pct"]) else 0,
            )
        )
    lines.extend(["", "## Ideias estruturais geradas", ""])
    if opp.empty:
        lines.append("- Sem sinais suficientes nos filtros automáticos.")
    else:
        for _, row in opp.head(20).iterrows():
            lines.append(f"- **{row['tema']} | {row['periodo']} | {row['setor_n1']} / {row['setor_n2']}**: {row['sinal']} {row['ideia_estrutura']}")
    (output_dir / "fidc_credit_strategy_report.md").write_text("\n".join(lines), encoding="utf-8")


def build(paths: StudyPaths) -> dict[str, pd.DataFrame]:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.app_data_dir.mkdir(parents=True, exist_ok=True)
    sources = load_sources(paths)
    sources["offers"] = prepare_offers(sources["offers"])
    sources["entities"] = prepare_entities(sources["entities"])
    sources["features"] = prepare_features(sources["features"])
    sources["pricing"] = prepare_pricing(sources["pricing"])

    fund_universe = build_fund_universe(sources)
    feature_long = build_feature_long(fund_universe, sources["features"])
    feature_heatmap_year, feature_heatmap_current = build_feature_heatmaps(feature_long)
    sub_detail, sub_summary = build_subordination(fund_universe)
    pricing_enriched = enrich_pricing(sources["pricing"], fund_universe)
    senior_pricing_summary, quota_pricing_summary = build_pricing_summary(pricing_enriched)
    ime_cache_summary = build_ime_cache_summary()
    ime_current_snapshot = build_ime_current_snapshot(paths.ime_dir, fund_universe)
    ime_current_subordination = build_ime_current_subordination_by_sector(ime_current_snapshot)
    ime_cota_movements, ime_cota_price_summary = build_ime_cota_movements(paths.ime_dir, fund_universe)
    market_opportunities = build_opportunities(sub_summary, senior_pricing_summary, feature_heatmap_year)

    tables = {
        "fund_universe": fund_universe,
        "regulatory_feature_long": feature_long,
        "regulatory_feature_heatmap_year": feature_heatmap_year,
        "regulatory_feature_heatmap_current": feature_heatmap_current,
        "subordination_fund_detail": sub_detail,
        "subordination_by_sector_year": sub_summary,
        "pricing_tranche_enriched": pricing_enriched,
        "pricing_senior_by_sector_year": senior_pricing_summary,
        "pricing_quota_by_sector_year": quota_pricing_summary,
        "ime_cache_summary": ime_cache_summary,
        "ime_current_snapshot": ime_current_snapshot,
        "ime_current_subordination_by_sector_year": ime_current_subordination,
        "ime_cota_movements": ime_cota_movements,
        "ime_cota_price_by_sector_year": ime_cota_price_summary,
        "market_opportunities": market_opportunities,
        "market_participants_by_sector": sources["participants"],
        "cedentes_sacados_candidates": sources["cedentes_sacados"],
        "manual_review_queue": sources["manual_queue"],
    }
    for name, frame in tables.items():
        write_csv(frame, paths.output_dir / f"{name}.csv")

    output_db = paths.output_dir / "fidc_credit_strategy.sqlite"
    app_db = paths.app_data_dir / "fidc_credit_strategy.sqlite"
    write_sqlite(tables, output_db)
    write_sqlite(tables, app_db)
    write_report(tables, paths.output_dir, app_db)
    return tables


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build persistent FIDC credit strategy study.")
    parser.add_argument("--issuance-dir", default=str(DEFAULT_ISSUANCE_DIR))
    parser.add_argument("--deep-dir", default=str(DEFAULT_DEEP_DIR))
    parser.add_argument("--ime-dir", default=str(DEFAULT_IME_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--app-data-dir", default=str(DEFAULT_APP_DATA_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = StudyPaths(
        issuance_dir=Path(args.issuance_dir),
        deep_dir=Path(args.deep_dir),
        ime_dir=Path(args.ime_dir),
        output_dir=Path(args.output_dir),
        app_data_dir=Path(args.app_data_dir),
    )
    tables = build(paths)
    summary = {
        "funds": int(tables["fund_universe"]["cnpj"].nunique()),
        "funds_with_matrix": int(tables["fund_universe"]["has_regulatory_matrix"].sum()),
        "senior_pricing_rows": int(len(tables["pricing_senior_by_sector_year"])),
        "ime_current_rows": int(len(tables["ime_current_snapshot"])),
        "ime_cota_price_rows": int(len(tables["ime_cota_price_by_sector_year"])),
        "opportunities": int(len(tables["market_opportunities"])),
        "output_dir": str(paths.output_dir),
        "app_db": str(paths.app_data_dir / "fidc_credit_strategy.sqlite"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
