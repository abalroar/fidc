"""Aba "Industria FIDCs": estudo da industria a partir dos dados abertos da CVM.

Consome os agregados versionados em data/industry_study/ (gerados por
scripts/build_fidc_industry_study.py). Nao acessa rede: se os CSVs nao
existirem, orienta a rodar o pipeline.

Paleta da aba (pedido do produto): laranja, preto e tons de cinza, com o maior
contraste possivel entre os tons. Validada contra fundo branco (contraste >= 3:1
e separacao CVD deltaE 49); como preto/cinza sao acromaticos por escolha, a
identidade das series nunca fica so na cor - toda serie tem legenda visivel,
rotulo direto ou tabela ao lado.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from services.dashboard_ui import diagnostics_enabled, render_context_strip, render_page_header
from services.industry_executive_pack import (
    ANBIMA_FIC,
    ANBIMA_FOCUS_BY_TYPE,
    ANBIMA_ND,
    ANBIMA_TYPES,
    HOLDER_BUCKETS,
    STRUCTURE_MODELS,
    IndustryExecutivePack,
    build_holder_histograms,
    build_industry_executive_pack,
)
from services.industry_study import (
    CEDENTE_REVIEW_COLUMNS,
    CRITERIA_REVIEW_COLUMNS,
    DOCUMENT_CHUNK_ACTION_COLUMNS,
    DIMENSION_CATALOG_SPECS,
    HEATMAP_PRESET_SPECS,
    MARKET_SHARE_DIMENSIONS,
    MARKET_SHARE_METRICS,
    MONTHLY_DELTA_ACTION_COLUMNS,
    append_review_audit_events,
    apply_document_chunk_actions,
    apply_monthly_delta_actions,
    build_document_chunk_plan,
    build_curation_queue_pipeline_manifest,
    build_industry_curation_queue,
    build_industry_curation_queue_summary,
    build_industry_dimension_value_atlas,
    build_industry_heatmap_registry,
    build_review_audit_events,
    build_cedente_pipeline_manifest,
    build_cedente_structured,
    build_criteria_pipeline_manifest,
    build_criteria_structured,
    build_industry_pipeline_index,
    clean_candidate_name,
    load_dataframe,
    load_cedente_candidates,
    load_criteria_reviews,
    load_criteria_source,
    load_monthly_delta_actions,
    load_pipeline_manifest,
    load_cedente_reviews,
    load_fund_universe,
    load_regulatory_feature_criteria,
    load_review_audit,
    normalize_cnpj,
    save_cedente_reviews,
    save_criteria_reviews,
    save_dataframe,
    save_monthly_delta_actions,
    save_pipeline_manifest,
    save_cedente_structured,
)

_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"
_REGULATORY_DB = Path(__file__).resolve().parents[1] / "data" / "fidc_credit_strategy" / "fidc_credit_strategy.sqlite"
INDUSTRY_VIEW_TABS = (
    "Principais conclusões",
    "Escala e taxonomia",
    "Breakdown FIDCs Cartão",
    "Base investidora",
    "Carteira e inadimplência",
    "Prestadores",
    "Top 20",
    "Ofertas e originação",
    "Dados e exportações",
)
INDUSTRY_EXECUTIVE_CHARTS = (
    "industry-executive-pl",
    "industry-executive-relevant-offers",
    "industry-executive-net-flow",
    "industry-executive-holders",
    "industry-executive-delinquency",
)
INDUSTRY_STRUCTURE_CHARTS = (
    "industry-provider-monostructure-history",
    "industry-provider-structure-current",
    "industry-holder-histogram-funds",
    "industry-holder-histogram-pl",
)
INDUSTRY_HOLDER_PL_CUTS_MM = (0, 100, 300, 1000)
_INDUSTRY_EXECUTIVE_PACK_INPUTS = (
    "vehicle_monthly.csv.gz",
    "industry_competence_status.csv",
    "industry_monthly.csv",
    "industry_anbima_classification.csv.gz",
    "industry_large_fund_classification.csv",
)
_INDUSTRY_EXPORT_INPUTS = (
    *_INDUSTRY_EXECUTIVE_PACK_INPUTS,
    "industry_anbima_classification_manifest.json",
    "segments_monthly.csv",
    "concentration_monthly.csv",
    "industry_offers_annual.csv",
    "industry_closed_offers_annual.csv",
    "industry_closed_offers_monthly.csv",
    "industry_closed_offer_originators_2026.csv",
    "industry_competitive_position.csv",
    "industry_offer_rankings.csv.gz",
    "industry_stock_ranking_deltas.csv.gz",
    "industry_originators_annual.csv",
    "industry_investor_distribution.csv",
    "industry_investor_types.csv",
    "industry_offers.csv.gz",
    "industry_large_fund_documents.csv.gz",
    "provider_ownership_curation.csv",
    "bank_fidc_curation.csv",
    "acquiring_reclassification_curation.csv",
    "card_receivables_curation.csv",
    "industry_intelligence_manifest.json",
    "generated_revision/artifact_payload.json",
    "generated_revision/revision_manifest.json",
    "generated_revision/industry_export_bundle.json",
    "generated_revision/industry_executive_revised.pptx",
    "generated_revision/industry_data_revised.xlsx",
    "generated_revision/provider_flows_explorer.html",
)
_ALL_FIDCS_CRITERIA = Path(__file__).resolve().parents[1] / "data" / "regulatory_profiles" / "all_fidcs_criteria_monitoraveis_ime.csv"
_CEDENTE_REVIEW_PATH = _DATA_DIR / "cedente_reviews.csv"
_CEDENTE_REVIEW_AUDIT_PATH = _DATA_DIR / "cedente_review_audit.csv"
_CEDENTE_STRUCTURED_PATH = _DATA_DIR / "cedentes_structured.csv.gz"
_PIPELINE_MANIFEST_PATH = _DATA_DIR / "industry_pipeline_manifest.json"
_PIPELINE_INDEX_PATH = _DATA_DIR / "industry_pipeline_index.json"
_CURATION_QUEUE_PATH = _DATA_DIR / "industry_curation_queue.csv.gz"
_CURATION_QUEUE_SUMMARY_PATH = _DATA_DIR / "industry_curation_queue_summary.csv.gz"
_CURATION_QUEUE_MANIFEST_PATH = _DATA_DIR / "industry_curation_queue_manifest.json"
_MONTHLY_DELTA_PATH = _DATA_DIR / "industry_monthly_delta.csv.gz"
_MONTHLY_DELTA_MANIFEST_PATH = _DATA_DIR / "industry_monthly_delta_manifest.json"
_MONTHLY_DELTA_ACTIONS_PATH = _DATA_DIR / "monthly_delta_actions.csv"
_MONTHLY_DELTA_ACTION_AUDIT_PATH = _DATA_DIR / "monthly_delta_action_audit.csv"
_SNAPSHOT_GAP_ACTIONS_PATH = _DATA_DIR / "snapshot_gap_actions.csv"
_SNAPSHOT_GAP_ACTION_AUDIT_PATH = _DATA_DIR / "snapshot_gap_action_audit.csv"
_CATALOG_GAP_ACTIONS_PATH = _DATA_DIR / "dimension_catalog_gap_actions.csv"
_CATALOG_GAP_ACTION_AUDIT_PATH = _DATA_DIR / "dimension_catalog_gap_action_audit.csv"
_FUND_SNAPSHOT_PATH = _DATA_DIR / "industry_fund_snapshot.csv.gz"
_FUND_SNAPSHOT_MANIFEST_PATH = _DATA_DIR / "industry_fund_snapshot_manifest.json"
_DIMENSION_CATALOG_PATH = _DATA_DIR / "industry_dimension_catalog.csv.gz"
_DIMENSION_CATALOG_MANIFEST_PATH = _DATA_DIR / "industry_dimension_catalog_manifest.json"
_DIMENSION_MONTHLY_PATH = _DATA_DIR / "industry_dimension_monthly.csv.gz"
_DIMENSION_VALUE_ATLAS_PATH = _DATA_DIR / "industry_dimension_value_atlas.csv.gz"
_DIMENSION_MONTHLY_MANIFEST_PATH = _DATA_DIR / "industry_dimension_monthly_manifest.json"
_DIMENSION_PROFILE_PATH = _DATA_DIR / "industry_dimension_profiles.csv.gz"
_HEATMAP_REGISTRY_PATH = _DATA_DIR / "industry_heatmap_registry.csv"
_DIMENSION_PROFILE_MANIFEST_PATH = _DATA_DIR / "industry_dimension_profile_manifest.json"
_DIMENSION_DOSSIER_PATH = _DATA_DIR / "industry_dimension_dossiers.csv"
_DIMENSION_DOSSIER_MANIFEST_PATH = _DATA_DIR / "industry_dimension_dossier_manifest.json"
_MARKET_SHARE_PATH = _DATA_DIR / "industry_market_share.csv.gz"
_MARKET_SHARE_MANIFEST_PATH = _DATA_DIR / "industry_market_share_manifest.json"
_ISSUANCE_ANNUAL_PATH = _DATA_DIR / "issuance_annual.csv"
_ISSUANCE_SECTOR_YEAR_PATH = _DATA_DIR / "issuance_sector_year.csv"
_ISSUANCE_TRANCHES_PATH = _DATA_DIR / "issuance_tranches.csv.gz"
_ISSUANCE_MANIFEST_PATH = _DATA_DIR / "industry_issuance_manifest.json"
_PUBLIC_CLAIM_AUDIT_PATH = _DATA_DIR / "industry_public_claim_audit.csv"
_PUBLIC_CLAIM_AUDIT_MANIFEST_PATH = _DATA_DIR / "industry_public_claim_audit_manifest.json"
_DOCUMENT_INVENTORY_PATH = _DATA_DIR / "document_inventory.csv.gz"
_DOCUMENT_CHUNKS_PATH = _DATA_DIR / "document_processing_chunks.csv"
_DOCUMENT_CHUNK_PLAN_PATH = _DATA_DIR / "document_chunk_plan.csv"
_DOCUMENT_MANIFEST_PATH = _DATA_DIR / "industry_document_manifest.json"
_DOCUMENT_CHUNK_ACTIONS_PATH = _DATA_DIR / "document_chunk_actions.csv"
_DOCUMENT_CHUNK_ACTION_AUDIT_PATH = _DATA_DIR / "document_chunk_action_audit.csv"
_CRITERIA_REVIEW_PATH = _DATA_DIR / "criteria_reviews.csv"
_CRITERIA_REVIEW_AUDIT_PATH = _DATA_DIR / "criteria_review_audit.csv"
_CRITERIA_STRUCTURED_PATH = _DATA_DIR / "criteria_structured.csv.gz"
_CRITERIA_MANIFEST_PATH = _DATA_DIR / "industry_criteria_manifest.json"
_CEDENTE_REVIEW_COLUMNS = CEDENTE_REVIEW_COLUMNS
_CRITERIA_REVIEW_COLUMNS = CRITERIA_REVIEW_COLUMNS
_SNAPSHOT_GAP_ACTION_COLUMNS = [
    "gap_id",
    "status_lacuna",
    "acao_revisada",
    "responsavel",
    "prazo",
    "notas",
    "updated_at_utc",
]
_CATALOG_GAP_ACTION_COLUMNS = [
    "traceability_gap_id",
    "status_lacuna",
    "acao_revisada",
    "responsavel",
    "prazo",
    "notas",
    "updated_at_utc",
]
_DOCUMENT_CHUNK_ACTION_COLUMNS = DOCUMENT_CHUNK_ACTION_COLUMNS

# Paleta laranja/preto/cinza - maior contraste entre tons sobre fundo branco.
_ORANGE = "#EC7000"
_ORANGE_SOFT = "rgba(236, 112, 0, 0.14)"
_BLACK = "#151515"
_GRAY = "#8D9399"
_GRAY_LIGHT = "#D7DADD"
_PROVIDER_COLORS = {
    "genial": "#6EC5E9",
    "qi tech": "#2456D6",
    "btg pactual": "#1D4080",
    "oliveira trust": "#7A1F3D",
    "banco do brasil": "#D6A800",
    "itaú": "#FF5500",
    "itau": "#FF5500",
    "cbsf": "#73C6A1",
    "reag": "#73C6A1",
}
_PROVIDER_GRAYS = ("#30353A", "#454A4F", "#5B6065", "#73787D", "#8D9399", "#A7ACB0", "#BEC2C5")


def _provider_color(name: object) -> str:
    key = re.sub(r"\s+", " ", str(name or "").strip().casefold())
    if key == "outros identificados":
        return _GRAY_LIGHT
    if key in {"prestador não informado", "prestador nao informado", "não informado", "nao informado"}:
        return "#F5F6F7"
    for token, color in _PROVIDER_COLORS.items():
        if token in key:
            return color
    digest = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
    return _PROVIDER_GRAYS[digest % len(_PROVIDER_GRAYS)]
_INK_SECONDARY = "#73787D"

# Vocabulario centralizado da aba (rotulos de series e metricas).
_LABELS = {
    "pl": "PL da indústria (R$ bi)",
    "capt_liq": "Captação líquida mensal (R$ bi)",
    "entrada": "entrada líquida",
    "saida": "saída líquida",
    "cotistas": "Contas de cotistas (mil)",
    "inad_ajustada": "ajustada (inadimplência de cada veículo limitada à própria carteira)",
    "inad_bruta": "bruta (como reportada, NPL a valor de face)",
    "top5": "top 5 administradores",
    "top10": "top 10 administradores",
}

_CSS = """
<style>
.industry-header {
    border-bottom: 1px solid #e5e3e0;
    margin: 0.1rem 0 1rem 0;
    padding-bottom: 0.9rem;
}
.industry-kicker {
    color: #EC7000;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    line-height: 1.2;
    text-transform: uppercase;
}
.industry-title {
    color: #1a1a1a;
    font-size: 2.1rem;
    font-weight: 650;
    line-height: 1.05;
    margin: 0.25rem 0 0.35rem 0;
}
.industry-subtitle {
    color: #595959;
    font-size: 0.94rem;
    line-height: 1.45;
    max-width: 64rem;
}
.industry-kpi-grid {
    display: grid;
    gap: 0.55rem;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    margin: 0.7rem 0 1rem 0;
}
@media (max-width: 1100px) {
    .industry-kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 640px) {
    .industry-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.industry-kpi {
    background: #ffffff;
    border: 1px solid #e5e3e0;
    border-top: 3px solid #EC7000;
    border-radius: 6px;
    min-height: 76px;
    padding: 0.65rem 0.75rem;
}
.industry-kpi-label {
    color: #595959;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.055em;
    line-height: 1.2;
    text-transform: uppercase;
}
.industry-kpi-value {
    color: #1a1a1a;
    font-size: 1.28rem;
    font-weight: 750;
    line-height: 1.25;
    margin-top: 0.34rem;
    font-variant-numeric: tabular-nums;
}
.industry-kpi-note {
    color: #8c8c8c;
    font-size: 0.74rem;
    line-height: 1.3;
    margin-top: 0.18rem;
}
.industry-section {
    color: #1a1a1a;
    font-size: 1.12rem;
    font-weight: 700;
    margin: 1.1rem 0 0.15rem 0;
}
.industry-def {
    color: #8c8c8c;
    font-size: 0.8rem;
    line-height: 1.4;
    margin-bottom: 0.35rem;
}
.industry-curation-note {
    color: #595959;
    font-size: 0.82rem;
    line-height: 1.45;
    margin: 0.2rem 0 0.8rem 0;
}
</style>
"""


_PRESTADOR_ABREVIACOES = [
    ("DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS", "DTVM"),
    ("DISTRIBUIDORA DE TÍTULOS E VALORES MOBILIÁRIOS", "DTVM"),
    ("CORRETORA DE TÍTULOS E VALORES MOBILIÁRIOS", "CTVM"),
    ("CORRETORA DE TITULOS E VALORES MOBILIARIOS", "CTVM"),
    ("CORRETORA DE VALORES MOBILIÁRIOS", "CVM"),
    (" S.A.", ""),
    (" S/A", ""),
    (" LTDA.", ""),
    (" LTDA", ""),
]


def _short_prestador(nome: str) -> str:
    out = str(nome)
    for longo, curto in _PRESTADOR_ABREVIACOES:
        out = out.replace(longo, curto)
    return out.strip(" -")


def _fmt_bi(value: float, digits: int = 1) -> str:
    return (
        f"R$ {value / 1e9:,.{digits}f} bi".replace(",", "@").replace(".", ",").replace("@", ".")
    )


def _fmt_mi(value: float, digits: int = 1) -> str:
    return (
        f"R$ {value / 1e6:,.{digits}f} mi".replace(",", "@").replace(".", ",").replace("@", ".")
    )


def _fmt_pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%".replace(".", ",")


def _fmt_int(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", ".")


def _pct_label(value: float | None, digits: int = 1) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return "n/d"
    return f"{float(number):.{digits}f}%".replace(".", ",")


@st.cache_data(show_spinner=False)
def _load_csv(name: str, source_signature: str) -> pd.DataFrame | None:
    del source_signature  # participates in the cache key
    path = _DATA_DIR / name
    if not path.exists():
        return None
    return pd.read_csv(path, low_memory=False)


@st.cache_data(show_spinner=False)
def _load_metadata() -> dict:
    path = _DATA_DIR / "metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_pct_values(text: object) -> list[float]:
    values: list[float] = []
    for match in re.finditer(r"(\d+(?:[\.,]\d+)?)\s*%", str(text or "")):
        try:
            values.append(float(match.group(1).replace(",", ".")))
        except ValueError:
            continue
    return values


def _clean_candidate_name(value: object) -> str:
    return clean_candidate_name(value)


def _load_cedente_reviews() -> pd.DataFrame:
    return load_cedente_reviews(_CEDENTE_REVIEW_PATH)


def _save_cedente_reviews(reviews: pd.DataFrame) -> None:
    save_cedente_reviews(reviews, _CEDENTE_REVIEW_PATH)


@st.cache_data(show_spinner=False)
def _load_cedente_candidates() -> pd.DataFrame:
    return load_cedente_candidates(_REGULATORY_DB)


@st.cache_data(show_spinner=False)
def _load_cedente_fund_universe() -> pd.DataFrame:
    return load_fund_universe(_REGULATORY_DB)


def _build_structured_cedentes(
    candidates: pd.DataFrame | None = None,
    reviews: pd.DataFrame | None = None,
) -> pd.DataFrame:
    candidates = _load_cedente_candidates() if candidates is None else candidates
    reviews = _load_cedente_reviews() if reviews is None else reviews
    vehicle_latest = _load_csv(
        "universe_latest.csv",
        _industry_files_signature(("universe_latest.csv",)),
    )
    return build_cedente_structured(
        candidates,
        reviews,
        fund_universe=_load_cedente_fund_universe(),
        vehicle_latest=vehicle_latest if vehicle_latest is not None else pd.DataFrame(),
        review_audit=load_review_audit(_CEDENTE_REVIEW_AUDIT_PATH),
    )


def _persist_structured_cedentes(candidates: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    fund_universe = _load_cedente_fund_universe()
    vehicle_latest = _load_csv(
        "universe_latest.csv",
        _industry_files_signature(("universe_latest.csv",)),
    )
    structured = build_cedente_structured(
        candidates,
        reviews,
        fund_universe=fund_universe,
        vehicle_latest=vehicle_latest if vehicle_latest is not None else pd.DataFrame(),
        review_audit=load_review_audit(_CEDENTE_REVIEW_AUDIT_PATH),
    )
    save_cedente_structured(structured, _CEDENTE_STRUCTURED_PATH)
    manifest = build_cedente_pipeline_manifest(
        industry_dir=_DATA_DIR,
        strategy_db=_REGULATORY_DB,
        reviews_path=_CEDENTE_REVIEW_PATH,
        output_path=_CEDENTE_STRUCTURED_PATH,
        candidates=candidates,
        reviews=reviews,
        fund_universe=fund_universe,
        vehicle_latest=vehicle_latest if vehicle_latest is not None else pd.DataFrame(),
        structured=structured,
    )
    save_pipeline_manifest(manifest, _PIPELINE_MANIFEST_PATH)
    return structured


@st.cache_data(show_spinner=False)
def _load_regulatory_overlay() -> dict[str, pd.DataFrame | dict[str, float | int | str]]:
    criteria = pd.DataFrame()
    if _ALL_FIDCS_CRITERIA.exists():
        criteria = pd.read_csv(_ALL_FIDCS_CRITERIA)

    fund_universe = pd.DataFrame()
    candidates = pd.DataFrame()
    queue = pd.DataFrame()
    metadata: dict[str, str] = {}
    if _REGULATORY_DB.exists():
        try:
            with sqlite3.connect(_REGULATORY_DB) as conn:
                fund_universe = pd.read_sql_query(
                    """
                    select cnpj, fund_name_final, setor_n1, setor_n2, pl_atual_brl,
                           has_regulatory_matrix, named_originator_or_cedente_bool,
                           named_debtor_or_sacado_bool, subordination_main_pct_num,
                           monocedente_or_multicedente, concentrated_or_pulverized_debtors,
                           regulamento_count, document_count_total, latest_regulamento_date
                    from fund_universe
                    """,
                    conn,
                )
                candidates = pd.read_sql_query(
                    """
                    select cnpj_fundo, fund_name, setor_n1, setor_n2, participant_type,
                           participant_name_candidate, evidence_context, source_cache
                    from cedentes_sacados_candidates
                    """,
                    conn,
                )
                queue = pd.read_sql_query(
                    """
                    select review_wave, platform_coverage_level, manual_review_status,
                           cnpj, setor_n1, setor_n2
                    from manual_review_queue
                    """,
                    conn,
                )
                meta = pd.read_sql_query("select key, value from study_metadata", conn)
                metadata = dict(zip(meta["key"].astype(str), meta["value"].astype(str), strict=False))
        except sqlite3.Error:
            fund_universe = pd.DataFrame()
            candidates = pd.DataFrame()
            queue = pd.DataFrame()

    summary: dict[str, float | int | str] = {
        "db_date": metadata.get("as_of_date", ""),
        "universe_funds": int(fund_universe["cnpj"].nunique()) if not fund_universe.empty else 0,
        "matrix_funds": int(pd.to_numeric(fund_universe.get("has_regulatory_matrix"), errors="coerce").fillna(0).sum()) if not fund_universe.empty else 0,
        "cedente_funds": int(pd.to_numeric(fund_universe.get("named_originator_or_cedente_bool"), errors="coerce").fillna(0).sum()) if not fund_universe.empty else 0,
        "sacado_funds": int(pd.to_numeric(fund_universe.get("named_debtor_or_sacado_bool"), errors="coerce").fillna(0).sum()) if not fund_universe.empty else 0,
        "criteria_rows": int(len(criteria)),
        "criteria_funds": int(criteria["CNPJ"].nunique()) if "CNPJ" in criteria.columns else 0,
    }

    sub_rules = pd.DataFrame()
    if not criteria.empty and {"Chave", "Limite/regra"}.issubset(criteria.columns):
        sub_rules = criteria[criteria["Chave"].eq("subordination_ratio_min")].copy()
        sub_rules["pct_values"] = sub_rules["Limite/regra"].map(_extract_pct_values)
        sub_rules["pct_min"] = sub_rules["pct_values"].map(lambda values: min(values) if values else None)
        sub_values = pd.to_numeric(sub_rules["pct_min"], errors="coerce").dropna()
        summary["sub_rules"] = int(len(sub_rules))
        summary["sub_funds"] = int(sub_rules["CNPJ"].nunique()) if "CNPJ" in sub_rules.columns else 0
        summary["sub_median"] = float(sub_values.median()) if not sub_values.empty else float("nan")
        summary["sub_p25"] = float(sub_values.quantile(0.25)) if not sub_values.empty else float("nan")
        summary["sub_p75"] = float(sub_values.quantile(0.75)) if not sub_values.empty else float("nan")
    else:
        summary["sub_rules"] = 0
        summary["sub_funds"] = 0
        summary["sub_median"] = float("nan")
        summary["sub_p25"] = float("nan")
        summary["sub_p75"] = float("nan")

    sector_summary = pd.DataFrame()
    if not fund_universe.empty:
        frame = fund_universe.copy()
        for col in ["has_regulatory_matrix", "named_originator_or_cedente_bool", "named_debtor_or_sacado_bool"]:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0)
        frame["subordination_main_pct_num"] = pd.to_numeric(frame["subordination_main_pct_num"], errors="coerce")
        sector_summary = (
            frame.groupby("setor_n1", dropna=False)
            .agg(
                CNPJs=("cnpj", "nunique"),
                Matrizes=("has_regulatory_matrix", "sum"),
                Cedente=("named_originator_or_cedente_bool", "sum"),
                Sacado=("named_debtor_or_sacado_bool", "sum"),
                Sub_n=("subordination_main_pct_num", "count"),
                Sub_mediana=("subordination_main_pct_num", "median"),
                PL=("pl_atual_brl", "sum"),
            )
            .reset_index()
            .rename(columns={"setor_n1": "Setor"})
            .sort_values(["Matrizes", "PL"], ascending=False)
        )
        for col in ["Matrizes", "Cedente", "Sacado", "Sub_n"]:
            sector_summary[col] = sector_summary[col].astype(int)
        sector_summary["Sub mediana"] = sector_summary["Sub_mediana"].map(_pct_label)
        sector_summary["PL"] = sector_summary["PL"].map(lambda value: _fmt_bi(float(value), 1))
        sector_summary = sector_summary[["Setor", "CNPJs", "Matrizes", "Cedente", "Sacado", "Sub_n", "Sub mediana", "PL"]]

    candidate_summary = pd.DataFrame()
    candidate_examples = pd.DataFrame()
    if not candidates.empty:
        candidate_summary = (
            candidates.groupby(["setor_n1", "participant_type"], dropna=False)
            .agg(Evidências=("participant_type", "size"), FIDCs=("cnpj_fundo", "nunique"))
            .reset_index()
            .rename(columns={"setor_n1": "Setor", "participant_type": "Tipo"})
            .sort_values(["FIDCs", "Evidências"], ascending=False)
        )
        candidate_examples = candidates.copy()
        candidate_examples["Participante"] = candidate_examples["participant_name_candidate"].map(_clean_candidate_name)
        candidate_examples = candidate_examples[candidate_examples["Participante"] != ""]
        if not candidate_examples.empty:
            candidate_examples = (
                candidate_examples.groupby(["participant_type", "Participante"], dropna=False)
                .agg(FIDCs=("cnpj_fundo", "nunique"), Evidências=("evidence_context", "size"), Setores=("setor_n1", lambda s: ", ".join(sorted(set(map(str, s)))[:3])))
                .reset_index()
                .rename(columns={"participant_type": "Tipo"})
                .sort_values(["FIDCs", "Evidências"], ascending=False)
                .head(12)
            )

    criteria_summary = pd.DataFrame()
    if not criteria.empty and {"Chave", "CNPJ", "Monitorabilidade IME"}.issubset(criteria.columns):
        criteria_summary = (
            criteria.groupby("Chave", dropna=False)
            .agg(Regras=("Chave", "size"), FIDCs=("CNPJ", "nunique"), Monitorabilidade=("Monitorabilidade IME", lambda s: ", ".join(sorted(set(map(str, s)))[:3])))
            .reset_index()
            .sort_values(["FIDCs", "Regras"], ascending=False)
            .head(12)
        )

    queue_summary = pd.DataFrame()
    if not queue.empty:
        queue_summary = (
            queue.groupby("review_wave", dropna=False)
            .agg(Linhas=("review_wave", "size"), FIDCs=("cnpj", "nunique"))
            .reset_index()
            .rename(columns={"review_wave": "Onda de revisão"})
            .sort_values("Linhas", ascending=False)
        )

    return {
        "summary": summary,
        "sector_summary": sector_summary,
        "candidate_summary": candidate_summary,
        "candidate_examples": candidate_examples,
        "criteria_summary": criteria_summary,
        "sub_rules": sub_rules,
        "queue_summary": queue_summary,
    }


def _month_axis(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["mes"] = pd.to_datetime(out["competencia"] + "-01")
    return out


def _base_line(df: pd.DataFrame, y_col: str, y_title: str, color: str) -> alt.Chart:
    return (
        alt.Chart(df)
        .mark_line(strokeWidth=2, color=color)
        .encode(
            x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False)),
            y=alt.Y(f"{y_col}:Q", title=y_title, axis=alt.Axis(gridColor=_GRAY_LIGHT)),
            tooltip=[
                alt.Tooltip("competencia:N", title="competência"),
                alt.Tooltip(f"{y_col}:Q", title=y_title, format=",.1f"),
            ],
        )
    )


def _drop_partial_tail(industry: pd.DataFrame) -> pd.DataFrame:
    """Remove competencias finais ainda em carga no dataset da CVM."""
    out = industry.sort_values("competencia").reset_index(drop=True)
    while len(out) > 1 and out.iloc[-1]["pl_total"] < 0.7 * out.iloc[-2]["pl_total"]:
        out = out.iloc[:-1]
    return out


def _curation_card(label: str, value: str, note: str = "") -> str:
    note_html = f'<div class="industry-kpi-note">{note}</div>' if note else ""
    return (
        f'<div class="industry-kpi"><div class="industry-kpi-label">{label}</div>'
        f'<div class="industry-kpi-value">{value}</div>{note_html}</div>'
    )


def _fmt_signed_bi(value: float, digits: int = 1) -> str:
    prefix = "+" if value > 0 else ""
    return prefix + _fmt_bi(value, digits)


def _format_vehicle_table(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    column_map = {
        "denominacao": "Veículo",
        "cnpj": "CNPJ",
        "cnpj_fundo": "CNPJ fundo",
        "admin_nome": "Administrador",
        "segmento_principal": "Segmento",
        "pl": "PL",
        "captacao_liquida": "Captação líquida",
        "carteira_dc": "Carteira DC",
        "inad_pct_ajustada": "Inad. ajustada",
        "subordinacao_pct": "Subordinação",
        "cotistas": "Cotistas",
    }
    keep = [col for col in column_map if col in out.columns]
    out = out[keep].rename(columns=column_map)
    for col in ["PL", "Captação líquida", "Carteira DC"]:
        if col in out.columns:
            out[col] = out[col].map(lambda value: _fmt_bi(float(value), 1))
    for col in ["Inad. ajustada", "Subordinação"]:
        if col in out.columns:
            out[col] = out[col].map(lambda value: _fmt_pct(float(value)))
    if "Cotistas" in out.columns:
        out["Cotistas"] = out["Cotistas"].map(lambda value: _fmt_int(float(value)))
    return out


@st.cache_data(show_spinner=False)
def _load_fund_snapshot_tables() -> dict[str, pd.DataFrame | dict[str, object]]:
    return {
        "snapshot": load_dataframe(_FUND_SNAPSHOT_PATH),
        "manifest": load_pipeline_manifest(_FUND_SNAPSHOT_MANIFEST_PATH),
    }


@st.cache_data(show_spinner=False)
def _load_market_share_tables() -> dict[str, pd.DataFrame | dict[str, object]]:
    return {
        "market_share": load_dataframe(_MARKET_SHARE_PATH),
        "manifest": load_pipeline_manifest(_MARKET_SHARE_MANIFEST_PATH),
    }


@st.cache_data(show_spinner=False)
def _load_dimension_catalog_tables() -> dict[str, pd.DataFrame | dict[str, object]]:
    return {
        "catalog": load_dataframe(_DIMENSION_CATALOG_PATH),
        "manifest": load_pipeline_manifest(_DIMENSION_CATALOG_MANIFEST_PATH),
    }


@st.cache_data(show_spinner=False)
def _load_dimension_monthly_tables() -> dict[str, pd.DataFrame | dict[str, object]]:
    monthly = load_dataframe(_DIMENSION_MONTHLY_PATH)
    atlas = load_dataframe(_DIMENSION_VALUE_ATLAS_PATH)
    if atlas.empty and not monthly.empty:
        catalog = load_dataframe(_DIMENSION_CATALOG_PATH)
        atlas = build_industry_dimension_value_atlas(monthly, dimension_catalog=catalog)
    return {
        "monthly": monthly,
        "atlas": atlas,
        "manifest": load_pipeline_manifest(_DIMENSION_MONTHLY_MANIFEST_PATH),
    }


@st.cache_data(show_spinner=False)
def _load_dimension_profile_tables() -> dict[str, pd.DataFrame | dict[str, object]]:
    profiles = load_dataframe(_DIMENSION_PROFILE_PATH)
    registry = load_dataframe(_HEATMAP_REGISTRY_PATH)
    if registry.empty:
        catalog = load_dataframe(_DIMENSION_CATALOG_PATH)
        registry = build_industry_heatmap_registry(dimension_catalog=catalog, profiles=profiles)
    return {
        "profiles": profiles,
        "heatmap_registry": registry,
        "manifest": load_pipeline_manifest(_DIMENSION_PROFILE_MANIFEST_PATH),
    }


@st.cache_data(show_spinner=False)
def _load_dimension_dossier_tables() -> dict[str, pd.DataFrame | dict[str, object]]:
    return {
        "dossiers": load_dataframe(_DIMENSION_DOSSIER_PATH),
        "manifest": load_pipeline_manifest(_DIMENSION_DOSSIER_MANIFEST_PATH),
    }


@st.cache_data(show_spinner=False)
def _load_public_claim_audit_tables() -> dict[str, pd.DataFrame | dict[str, object]]:
    return {
        "audit": load_dataframe(_PUBLIC_CLAIM_AUDIT_PATH),
        "manifest": load_pipeline_manifest(_PUBLIC_CLAIM_AUDIT_MANIFEST_PATH),
    }


@st.cache_data(show_spinner=False)
def _load_snapshot_gap_actions() -> pd.DataFrame:
    actions = load_dataframe(_SNAPSHOT_GAP_ACTIONS_PATH)
    for col in _SNAPSHOT_GAP_ACTION_COLUMNS:
        if col not in actions.columns:
            actions[col] = ""
    return actions[_SNAPSHOT_GAP_ACTION_COLUMNS]


def _save_snapshot_gap_actions(actions: pd.DataFrame) -> pd.DataFrame:
    out = actions.copy() if actions is not None else pd.DataFrame(columns=_SNAPSHOT_GAP_ACTION_COLUMNS)
    for col in _SNAPSHOT_GAP_ACTION_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[_SNAPSHOT_GAP_ACTION_COLUMNS]
    out = out[out["gap_id"].fillna("").astype(str).str.strip().ne("")].drop_duplicates("gap_id", keep="last")
    save_dataframe(out, _SNAPSHOT_GAP_ACTIONS_PATH)
    return out


def _apply_snapshot_gap_actions(gaps: pd.DataFrame, actions: pd.DataFrame | None) -> pd.DataFrame:
    if gaps is None or gaps.empty:
        return pd.DataFrame() if gaps is None else gaps.copy()
    out = gaps.copy()
    for col in ["status_lacuna", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        if col not in out.columns:
            out[col] = ""
    if actions is None or actions.empty or "gap_id" not in actions.columns or "gap_id" not in out.columns:
        out["status_lacuna"] = out["status_lacuna"].replace("", "pendente")
        return out
    overlay = actions.copy()
    for col in _SNAPSHOT_GAP_ACTION_COLUMNS:
        if col not in overlay.columns:
            overlay[col] = ""
    overlay = overlay[_SNAPSHOT_GAP_ACTION_COLUMNS].drop_duplicates("gap_id", keep="last")
    out = out.merge(overlay, on="gap_id", how="left", suffixes=("", "_review"))
    for col in ["status_lacuna", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        review_col = f"{col}_review"
        if review_col in out.columns:
            out[col] = out[review_col].fillna("").astype(str).where(
                out[review_col].fillna("").astype(str).str.strip().ne(""),
                out[col].fillna("").astype(str),
            )
            out = out.drop(columns=[review_col])
    out["status_lacuna"] = out["status_lacuna"].replace("", "pendente")
    return out


def _snapshot_gap_actions_for_audit(actions: pd.DataFrame | None) -> pd.DataFrame:
    if actions is None or actions.empty:
        return pd.DataFrame(columns=["gap_id", "status", "acao_revisada", "responsavel", "prazo", "notas"])
    out = actions.copy()
    for col in _SNAPSHOT_GAP_ACTION_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out["status"] = out["status_lacuna"].fillna("").astype(str).replace("", "pendente")
    return out[["gap_id", "status", "acao_revisada", "responsavel", "prazo", "notas"]]


@st.cache_data(show_spinner=False)
def _load_catalog_gap_actions() -> pd.DataFrame:
    actions = load_dataframe(_CATALOG_GAP_ACTIONS_PATH)
    for col in _CATALOG_GAP_ACTION_COLUMNS:
        if col not in actions.columns:
            actions[col] = ""
    return actions[_CATALOG_GAP_ACTION_COLUMNS]


def _save_catalog_gap_actions(actions: pd.DataFrame) -> pd.DataFrame:
    out = actions.copy() if actions is not None else pd.DataFrame(columns=_CATALOG_GAP_ACTION_COLUMNS)
    for col in _CATALOG_GAP_ACTION_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[_CATALOG_GAP_ACTION_COLUMNS]
    out = out[out["traceability_gap_id"].fillna("").astype(str).str.strip().ne("")]
    out = out.drop_duplicates("traceability_gap_id", keep="last")
    save_dataframe(out, _CATALOG_GAP_ACTIONS_PATH)
    return out


def _apply_catalog_gap_actions(gaps: pd.DataFrame, actions: pd.DataFrame | None) -> pd.DataFrame:
    if gaps is None or gaps.empty:
        return pd.DataFrame() if gaps is None else gaps.copy()
    out = gaps.copy()
    for col in ["status_lacuna", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        if col not in out.columns:
            out[col] = ""
    if (
        actions is None
        or actions.empty
        or "traceability_gap_id" not in actions.columns
        or "traceability_gap_id" not in out.columns
    ):
        out["status_lacuna"] = out["status_lacuna"].replace("", "pendente")
        return out
    overlay = actions.copy()
    for col in _CATALOG_GAP_ACTION_COLUMNS:
        if col not in overlay.columns:
            overlay[col] = ""
    overlay = overlay[_CATALOG_GAP_ACTION_COLUMNS].drop_duplicates("traceability_gap_id", keep="last")
    out = out.merge(overlay, on="traceability_gap_id", how="left", suffixes=("", "_review"))
    for col in ["status_lacuna", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        review_col = f"{col}_review"
        if review_col in out.columns:
            out[col] = out[review_col].fillna("").astype(str).where(
                out[review_col].fillna("").astype(str).str.strip().ne(""),
                out[col].fillna("").astype(str),
            )
            out = out.drop(columns=[review_col])
    out["status_lacuna"] = out["status_lacuna"].replace("", "pendente")
    return out


def _catalog_gap_actions_for_audit(actions: pd.DataFrame | None) -> pd.DataFrame:
    if actions is None or actions.empty:
        return pd.DataFrame(columns=["traceability_gap_id", "status", "acao_revisada", "responsavel", "prazo", "notas"])
    out = actions.copy()
    for col in _CATALOG_GAP_ACTION_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out["status"] = out["status_lacuna"].fillna("").astype(str).replace("", "pendente")
    return out[["traceability_gap_id", "status", "acao_revisada", "responsavel", "prazo", "notas"]]


def _monthly_delta_actions_for_audit(actions: pd.DataFrame | None) -> pd.DataFrame:
    if actions is None or actions.empty:
        return pd.DataFrame(columns=["delta_id", "status", "acao_revisada", "responsavel", "prazo", "notas"])
    out = actions.copy()
    for col in ["delta_id", "status_acao", "acao_revisada", "responsavel", "prazo", "notas"]:
        if col not in out.columns:
            out[col] = ""
    out["status"] = out["status_acao"].fillna("").astype(str).replace("", "pendente")
    return out[["delta_id", "status", "acao_revisada", "responsavel", "prazo", "notas"]]


@st.cache_data(show_spinner=False)
def _load_document_chunk_actions() -> pd.DataFrame:
    actions = load_dataframe(_DOCUMENT_CHUNK_ACTIONS_PATH)
    for col in _DOCUMENT_CHUNK_ACTION_COLUMNS:
        if col not in actions.columns:
            actions[col] = ""
    return actions[_DOCUMENT_CHUNK_ACTION_COLUMNS]


def _save_document_chunk_actions(actions: pd.DataFrame) -> pd.DataFrame:
    out = actions.copy() if actions is not None else pd.DataFrame(columns=_DOCUMENT_CHUNK_ACTION_COLUMNS)
    for col in _DOCUMENT_CHUNK_ACTION_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[_DOCUMENT_CHUNK_ACTION_COLUMNS]
    out = out[out["chunk_id"].fillna("").astype(str).str.strip().ne("")]
    out = out.drop_duplicates("chunk_id", keep="last")
    save_dataframe(out, _DOCUMENT_CHUNK_ACTIONS_PATH)
    return out


def _apply_document_chunk_actions(plan: pd.DataFrame, actions: pd.DataFrame | None) -> pd.DataFrame:
    return apply_document_chunk_actions(plan, actions)


def _document_chunk_actions_for_audit(actions: pd.DataFrame | None) -> pd.DataFrame:
    if actions is None or actions.empty:
        return pd.DataFrame(columns=["chunk_id", "status", "acao_revisada", "responsavel", "prazo", "notas"])
    out = actions.copy()
    for col in _DOCUMENT_CHUNK_ACTION_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out["status"] = out["status_lote"].fillna("").astype(str).replace("", "pendente")
    return out[["chunk_id", "status", "acao_revisada", "responsavel", "prazo", "notas"]]


def _format_fund_snapshot_table(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    column_map = {
        "cnpj_fundo": "CNPJ",
        "nome_exibicao": "FIDC",
        "competencia": "Competência",
        "pl": "PL",
        "segmento_principal": "Segmento IME",
        "segmento_estrategia": "Segmento Estratégia",
        "subsegmento_estrategia": "Subsegmento",
        "admin_nome": "Administrador",
        "gestor_nome": "Gestor",
        "valid_volume_2024_2026_brl": "Emissões 24-26",
        "valid_volume_2025_brl": "Emissões 2025",
        "valid_volume_2026_brl": "Emissões 2026",
        "document_rows": "Docs",
        "cedente_rows": "Cedentes",
        "participant_signal_rows": "Sinal ced/sac",
        "criteria_rows": "Critérios",
        "sub_min_pct_median": "Sub mín.",
        "camadas_com_evidencia": "Camadas",
        "snapshot_status": "Status",
        "cedentes_top": "Cedentes top",
        "indexadores": "Indexadores",
        "document_chunk_ids": "Chunks",
    }
    keep = [col for col in column_map if col in out.columns]
    out = out[keep].rename(columns=column_map)
    for col in ["PL", "Emissões 24-26", "Emissões 2025", "Emissões 2026"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_bi(float(value), 1))
    for col in ["Docs", "Cedentes", "Sinal ced/sac", "Critérios", "Camadas"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
    if "Sub mín." in out.columns:
        out["Sub mín."] = pd.to_numeric(out["Sub mín."], errors="coerce").map(lambda value: _pct_label(value))
    return out


def _cedente_signal_focus_frame(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Return funds with regulatory participant signal but no identified cedente/sacado."""

    columns = [
        "cnpj_fundo",
        "pl_sinal_brl",
        "signal_admin_nome",
        "signal_segmento_principal",
        "participant_signal_rows",
        "participant_signal_keys",
        "participant_signal_evidence",
        "criteria_documentos",
        "document_chunk_ids",
        "latest_regulamento_date",
    ]
    if snapshot is None or snapshot.empty:
        return pd.DataFrame(columns=columns)
    frame = snapshot.copy()
    frame["cnpj_fundo"] = frame.get("cnpj_fundo", pd.Series("", index=frame.index)).map(normalize_cnpj)
    participant_signal = pd.to_numeric(frame.get("participant_signal_rows"), errors="coerce").fillna(0)
    cedente_rows = pd.to_numeric(frame.get("cedente_rows"), errors="coerce").fillna(0)
    focus = frame[participant_signal.gt(0) & cedente_rows.le(0)].copy()
    if focus.empty:
        return pd.DataFrame(columns=columns)
    focus["pl_sinal_brl"] = pd.to_numeric(focus.get("pl"), errors="coerce").fillna(0.0)
    focus["signal_admin_nome"] = focus.get("admin_nome", pd.Series("", index=focus.index)).fillna("").astype(str)
    focus["signal_segmento_principal"] = focus.get("segmento_principal", pd.Series("", index=focus.index)).fillna("").astype(str)
    for col in [
        "participant_signal_rows",
        "participant_signal_keys",
        "participant_signal_evidence",
        "criteria_documentos",
        "document_chunk_ids",
        "latest_regulamento_date",
    ]:
        if col not in focus.columns:
            focus[col] = ""
    focus = focus[columns].drop_duplicates("cnpj_fundo", keep="first")
    return focus.sort_values("pl_sinal_brl", ascending=False).reset_index(drop=True)


def _snapshot_gap_frame(snapshot: pd.DataFrame) -> pd.DataFrame:
    if snapshot.empty:
        return pd.DataFrame()
    frame = snapshot.copy()
    for col in [
        "pl",
        "valid_volume_2024_2026_brl",
        "document_rows",
        "document_local_ready",
        "cedente_rows",
        "participant_signal_rows",
        "criteria_rows",
        "criteria_subordination_rows",
    ]:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
        else:
            frame[col] = 0.0
    bool_source = frame.get("tem_emissao_2025_2026", pd.Series(False, index=frame.index))
    frame["priority_2025_2026"] = bool_source.astype(str).str.lower().isin({"true", "1", "sim", "s", "yes"})
    competencia = frame.get("competencia", pd.Series("", index=frame.index)).fillna("").astype(str).replace("", "snapshot")
    cnpj_norm = frame.get("cnpj_fundo", pd.Series("", index=frame.index)).map(normalize_cnpj)
    frame["gap_id"] = competencia + "_" + cnpj_norm

    missing_cedente = frame["cedente_rows"].le(0)
    has_participant_signal = frame["participant_signal_rows"].gt(0)
    gap_specs = [
        ("sem documento", frame["document_rows"].le(0)),
        ("sem documento local", frame["document_local_ready"].le(0)),
        ("cedente/sacado sinalizado sem participante", missing_cedente & has_participant_signal),
        ("sem cedente/sacado", missing_cedente & ~has_participant_signal),
        ("sem critérios", frame["criteria_rows"].le(0)),
        ("sem sub mínima", frame["criteria_subordination_rows"].le(0)),
    ]
    missing_layers: list[str] = []
    gap_counts: list[int] = []
    for idx in frame.index:
        gaps = [label for label, mask in gap_specs if bool(mask.loc[idx])]
        missing_layers.append(" | ".join(gaps))
        gap_counts.append(len(gaps))
    frame["missing_layers"] = missing_layers
    frame["gap_count"] = gap_counts
    frame["gap_priority_score"] = (
        frame["gap_count"] * 10
        + frame["priority_2025_2026"].astype(int) * 20
        + pd.to_numeric(frame["pl"], errors="coerce").fillna(0.0).rank(pct=True).fillna(0.0) * 5
    )
    frame = frame[frame["gap_count"].gt(0)].copy()
    if frame.empty:
        return frame
    return frame.sort_values(["priority_2025_2026", "gap_priority_score", "pl"], ascending=[False, False, False]).reset_index(drop=True)


def _format_snapshot_gap_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    cols = [
        "gap_id",
        "cnpj_fundo",
        "nome_exibicao",
        "pl",
        "valid_volume_2024_2026_brl",
        "priority_2025_2026",
        "gap_count",
        "missing_layers",
        "status_lacuna",
        "acao_revisada",
        "responsavel",
        "prazo",
        "notas",
        "updated_at_utc",
        "admin_nome",
        "gestor_nome",
        "segmento_principal",
        "document_chunk_ids",
    ]
    out = frame[[col for col in cols if col in frame.columns]].copy()
    out = out.rename(
        columns={
            "gap_id": "ID",
            "cnpj_fundo": "CNPJ",
            "nome_exibicao": "FIDC",
            "pl": "PL",
            "valid_volume_2024_2026_brl": "Emissões 24-26",
            "priority_2025_2026": "Prioridade 25-26",
            "gap_count": "Lacunas",
            "missing_layers": "Camadas faltantes",
            "status_lacuna": "Status lacuna",
            "acao_revisada": "Ação revisada",
            "responsavel": "Responsável",
            "prazo": "Prazo",
            "notas": "Notas",
            "updated_at_utc": "Atualizado",
            "admin_nome": "Administrador",
            "gestor_nome": "Gestor",
            "segmento_principal": "Segmento",
            "document_chunk_ids": "Chunks",
        }
    )
    for col in ["PL", "Emissões 24-26"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).map(lambda value: _fmt_bi(float(value), 1))
    if "Lacunas" in out.columns:
        out["Lacunas"] = pd.to_numeric(out["Lacunas"], errors="coerce").fillna(0.0).map(lambda value: _fmt_int(float(value)))
    if "Prioridade 25-26" in out.columns:
        out["Prioridade 25-26"] = out["Prioridade 25-26"].astype(bool).map({True: "sim", False: "não"})
    return out


def _join_distinct(values: pd.Series, *, limit: int = 5) -> str:
    seen: list[str] = []
    for value in values.fillna("").astype(str):
        value = value.strip()
        if not value or value.lower() in {"nan", "none", "n/d"} or value in seen:
            continue
        seen.append(value)
        if len(seen) >= limit:
            break
    return " | ".join(seen)


def _dimension_value_snapshot_frame(
    catalog: pd.DataFrame,
    snapshot: pd.DataFrame,
    dimension_id: str,
    selected_value: str,
) -> pd.DataFrame:
    dim = _dimension_catalog_rows(catalog, dimension_id)
    if dim.empty:
        return pd.DataFrame()
    dim = dim[dim["dimension_value"].astype(str).eq(str(selected_value))].copy()
    if dim.empty:
        return dim
    for col in [
        "source_layer",
        "source_document",
        "source_page",
        "source_method",
        "review_status",
        "participant_cnpj",
    ]:
        if col not in dim.columns:
            dim[col] = ""
    if "dimension_label" not in dim.columns:
        dim["dimension_label"] = str(dimension_id)
    if "confidence_score" in dim.columns:
        dim["confidence_score"] = pd.to_numeric(dim["confidence_score"], errors="coerce")
    else:
        dim["confidence_score"] = pd.NA
    for col in ["is_curated", "is_multivalue"]:
        if col in dim.columns:
            dim[col] = dim[col].astype(str).str.lower().isin({"true", "1", "sim", "s", "yes"})
        else:
            dim[col] = False
    evidence = (
        dim.groupby("cnpj_fundo_norm", dropna=False)
        .agg(
            dimension_value=("dimension_value", "first"),
            dimension_label=("dimension_label", "first"),
            dimension_links=("dimension_value", "size"),
            dimension_weight=("value_weight", "sum"),
            dimension_source_layers=("source_layer", _join_distinct),
            dimension_documents=("source_document", _join_distinct),
            dimension_pages=("source_page", _join_distinct),
            dimension_methods=("source_method", _join_distinct),
            dimension_review_status=("review_status", _join_distinct),
            dimension_participant_cnpjs=("participant_cnpj", _join_distinct),
            dimension_confidence=("confidence_score", "median"),
            dimension_curated=("is_curated", "max"),
            dimension_multivalue=("is_multivalue", "max"),
        )
        .reset_index()
    )
    if snapshot is not None and not snapshot.empty:
        funds = snapshot.copy()
        id_col = "cnpj_fundo" if "cnpj_fundo" in funds.columns else "cnpj"
        funds["cnpj_fundo_norm"] = funds[id_col].map(normalize_cnpj)
        snapshot_cols = [
            "cnpj_fundo_norm",
            "cnpj_fundo",
            "nome_exibicao",
            "competencia",
            "pl",
            "valid_volume_2024_2026_brl",
            "admin_nome",
            "gestor_nome",
            "segmento_principal",
            "segmento_estrategia",
            "subsegmento_estrategia",
            "document_rows",
            "document_local_ready",
            "cedente_rows",
            "criteria_rows",
            "criteria_subordination_rows",
            "sub_min_pct_median",
            "tem_emissao_2025_2026",
            "document_chunk_ids",
            "snapshot_status",
        ]
        funds = funds[[col for col in snapshot_cols if col in funds.columns]].drop_duplicates("cnpj_fundo_norm")
        out = evidence.merge(funds, on="cnpj_fundo_norm", how="left")
    else:
        out = evidence.copy()
    if "cnpj_fundo" not in out.columns:
        out["cnpj_fundo"] = out["cnpj_fundo_norm"]
    out["cnpj_fundo"] = out["cnpj_fundo"].fillna("").astype(str).where(
        out["cnpj_fundo"].fillna("").astype(str).str.strip().ne(""),
        out["cnpj_fundo_norm"],
    )
    competencia = out.get("competencia", pd.Series("snapshot", index=out.index)).fillna("").astype(str).replace("", "snapshot")
    out["gap_id"] = competencia + "_" + out["cnpj_fundo_norm"].fillna("").astype(str)
    gaps = _snapshot_gap_frame(out)
    gap_cols = ["cnpj_fundo_norm", "gap_id", "gap_count", "missing_layers", "gap_priority_score", "priority_2025_2026"]
    if not gaps.empty:
        out = out.merge(gaps[[col for col in gap_cols if col in gaps.columns]], on="cnpj_fundo_norm", how="left", suffixes=("", "_gap"))
        if "gap_id_gap" in out.columns:
            out["gap_id"] = out["gap_id_gap"].fillna("").astype(str).where(out["gap_id_gap"].fillna("").astype(str).str.strip().ne(""), out["gap_id"])
            out = out.drop(columns=["gap_id_gap"])
    for col in ["gap_count", "gap_priority_score"]:
        out[col] = pd.to_numeric(out.get(col), errors="coerce").fillna(0.0)
    out["missing_layers"] = out.get("missing_layers", pd.Series("", index=out.index)).fillna("").astype(str)
    priority_values = out.get("priority_2025_2026", pd.Series(False, index=out.index))
    out["priority_2025_2026"] = priority_values.astype(str).str.lower().isin({"true", "1", "sim", "s", "yes"})
    for col in ["pl", "valid_volume_2024_2026_brl", "document_rows", "document_local_ready", "cedente_rows", "criteria_rows", "criteria_subordination_rows"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
        else:
            out[col] = 0.0
    return out.sort_values(["priority_2025_2026", "gap_count", "pl", "dimension_confidence"], ascending=[False, False, False, False]).reset_index(drop=True)


def _format_dimension_value_snapshot(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    cols = [
        "cnpj_fundo",
        "nome_exibicao",
        "pl",
        "valid_volume_2024_2026_brl",
        "gap_count",
        "missing_layers",
        "status_lacuna",
        "admin_nome",
        "segmento_principal",
        "document_rows",
        "cedente_rows",
        "criteria_rows",
        "criteria_subordination_rows",
        "sub_min_pct_median",
        "dimension_links",
        "dimension_source_layers",
        "dimension_documents",
        "dimension_pages",
        "dimension_methods",
        "dimension_confidence",
        "dimension_review_status",
        "document_chunk_ids",
    ]
    out = frame[[col for col in cols if col in frame.columns]].copy()
    out = out.rename(
        columns={
            "cnpj_fundo": "CNPJ",
            "nome_exibicao": "FIDC",
            "pl": "PL",
            "valid_volume_2024_2026_brl": "Emissões 24-26",
            "gap_count": "Lacunas",
            "missing_layers": "Camadas faltantes",
            "status_lacuna": "Status lacuna",
            "admin_nome": "Administrador",
            "segmento_principal": "Segmento",
            "document_rows": "Docs",
            "cedente_rows": "Cedentes",
            "criteria_rows": "Critérios",
            "criteria_subordination_rows": "Sub mín. evid.",
            "sub_min_pct_median": "Sub mín. mediana",
            "dimension_links": "Links dimensão",
            "dimension_source_layers": "Fonte dimensão",
            "dimension_documents": "Docs dimensão",
            "dimension_pages": "Págs dimensão",
            "dimension_methods": "Métodos dimensão",
            "dimension_confidence": "Score dimensão",
            "dimension_review_status": "Revisão dimensão",
            "document_chunk_ids": "Chunks",
        }
    )
    for col in ["PL", "Emissões 24-26"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).map(lambda value: _fmt_bi(float(value), 2))
    for col in ["Lacunas", "Docs", "Cedentes", "Critérios", "Sub mín. evid.", "Links dimensão"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).map(lambda value: _fmt_int(float(value)))
    if "Sub mín. mediana" in out.columns:
        out["Sub mín. mediana"] = pd.to_numeric(out["Sub mín. mediana"], errors="coerce").map(
            lambda value: _pct_label(float(value)) if pd.notna(value) else "n/d"
        )
    if "Score dimensão" in out.columns:
        out["Score dimensão"] = pd.to_numeric(out["Score dimensão"], errors="coerce").map(
            lambda value: "n/d" if pd.isna(value) else f"{float(value):.2f}".replace(".", ",")
        )
    return out


def _pl_fic_impact_frame(industry: pd.DataFrame) -> pd.DataFrame:
    required = {"competencia", "pl_total"}
    if industry.empty or not required.issubset(industry.columns):
        return pd.DataFrame()
    frame = industry.copy()
    frame["pl_total"] = pd.to_numeric(frame["pl_total"], errors="coerce").fillna(0.0)
    frame["pl_fic_fidc"] = pd.to_numeric(frame.get("pl_fic_fidc", pd.Series(0.0, index=frame.index)), errors="coerce").fillna(0.0)
    frame["pl_ex_fic_fidc"] = (frame["pl_total"] - frame["pl_fic_fidc"]).clip(lower=0.0)
    frame["fic_share"] = frame["pl_fic_fidc"] / frame["pl_total"].replace(0.0, pd.NA)
    frame["fic_share"] = frame["fic_share"].fillna(0.0)
    keep = [
        "competencia",
        "pl_total",
        "pl_fic_fidc",
        "pl_ex_fic_fidc",
        "fic_share",
    ]
    if "mes" in frame.columns:
        keep.insert(1, "mes")
    return frame[keep].sort_values("competencia").reset_index(drop=True)


def _filter_fund_rows(frame: pd.DataFrame, cnpj: object, *, column: str = "cnpj_fundo") -> pd.DataFrame:
    if frame.empty or column not in frame.columns:
        return frame.iloc[0:0].copy()
    target = normalize_cnpj(cnpj)
    if not target:
        return frame.iloc[0:0].copy()
    out = frame.copy()
    return out[out[column].map(normalize_cnpj).eq(target)].copy()


def _sort_fund_detail(frame: pd.DataFrame, preferred: list[tuple[str, bool]]) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    sort_cols: list[str] = []
    ascending: list[bool] = []
    for col, asc in preferred:
        if col not in out.columns:
            continue
        sort_col = f"__sort_{col}"
        if col in {"volume_brl", "score_confianca", "score_confianca_final", "pct_min", "document_date"}:
            out[sort_col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
        elif col in {"local_exists", "priority_2025_2026", "ativo_curadoria"}:
            out[sort_col] = out[col].astype(str).str.lower().isin({"true", "1", "sim"})
        else:
            out[sort_col] = out[col].fillna("").astype(str)
        sort_cols.append(sort_col)
        ascending.append(asc)
    if sort_cols:
        out = out.sort_values(sort_cols, ascending=ascending)
    return out.drop(columns=sort_cols, errors="ignore")


def _build_fund_dossier_tables(
    *,
    cnpj: object,
    snapshot: pd.DataFrame,
    tranches: pd.DataFrame,
    documents: pd.DataFrame,
    cedentes: pd.DataFrame,
    criteria: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Return all structured Industry layers for one normalized FIDC CNPJ."""

    snapshot_rows = _filter_fund_rows(snapshot, cnpj)
    tranche_rows = _sort_fund_detail(
        _filter_fund_rows(tranches, cnpj),
        [("ano", False), ("volume_brl", False), ("data_deliberacao", False)],
    )
    document_rows = _sort_fund_detail(
        _filter_fund_rows(documents, cnpj),
        [("priority_2025_2026", False), ("local_exists", False), ("document_date", False)],
    )
    cedente_rows = _sort_fund_detail(
        _filter_fund_rows(cedentes, cnpj),
        [("ativo_curadoria", False), ("score_confianca_final", False), ("razao_social", True)],
    )
    criteria_rows = _sort_fund_detail(
        _filter_fund_rows(criteria, cnpj),
        [("ativo_curadoria", False), ("pct_min", False), ("score_confianca_final", False)],
    )
    return {
        "snapshot": snapshot_rows,
        "tranches": tranche_rows,
        "documents": document_rows,
        "cedentes": cedente_rows,
        "criteria": criteria_rows,
    }


def _fund_dossier_layer_summary(dossier: dict[str, pd.DataFrame]) -> pd.DataFrame:
    snapshot = dossier.get("snapshot", pd.DataFrame())
    row = snapshot.iloc[0] if snapshot is not None and not snapshot.empty else pd.Series(dtype=object)
    return pd.DataFrame(
        [
            {
                "Camada": "IME mensal",
                "Linhas": 1 if not snapshot.empty else 0,
                "Status": row.get("competencia", ""),
                "Evidência": row.get("admin_nome", ""),
            },
            {
                "Camada": "Emissões",
                "Linhas": len(dossier.get("tranches", pd.DataFrame())),
                "Status": row.get("indexadores", ""),
                "Evidência": row.get("pricing_documentos", ""),
            },
            {
                "Camada": "Documentos",
                "Linhas": len(dossier.get("documents", pd.DataFrame())),
                "Status": row.get("document_classes", ""),
                "Evidência": row.get("document_chunk_ids", ""),
            },
            {
                "Camada": "Cedentes/sacados",
                "Linhas": len(dossier.get("cedentes", pd.DataFrame())),
                "Status": row.get("cedente_statuses", ""),
                "Evidência": row.get("cedentes_top", ""),
            },
            {
                "Camada": "Critérios",
                "Linhas": len(dossier.get("criteria", pd.DataFrame())),
                "Status": row.get("criteria_keys", ""),
                "Evidência": row.get("criteria_documentos", ""),
            },
        ]
    )


def _select_display_columns(frame: pd.DataFrame, columns: list[str], rename: dict[str, str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[rename.get(col, col) for col in columns])
    keep = [col for col in columns if col in frame.columns]
    out = frame[keep].copy()
    return out.rename(columns={col: rename[col] for col in keep if col in rename})


def _format_dossier_money(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_bi(float(value), 2))
    return out


def _render_fund_dossier(snapshot: pd.DataFrame) -> None:
    st.markdown("**Dossiê por FIDC**")
    ctrl_a, ctrl_b = st.columns([1.15, 1.35])
    with ctrl_a:
        query = st.text_input("Buscar FIDC", key="industry_dossier_query", placeholder="nome, CNPJ, administrador ou cedente")

    options_frame = snapshot.copy()
    if query:
        search_cols = [
            col
            for col in ["nome_exibicao", "cnpj_fundo", "admin_nome", "gestor_nome", "cedentes_top", "segmento_estrategia"]
            if col in options_frame.columns
        ]
        haystack = options_frame[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=options_frame.index)
        options_frame = options_frame[haystack.str.contains(query, case=False, na=False)].copy()
    if "camadas_com_evidencia" in options_frame.columns:
        options_frame["camadas_num"] = pd.to_numeric(options_frame["camadas_com_evidencia"], errors="coerce").fillna(0)
    else:
        options_frame["camadas_num"] = 0
    if "pl" in options_frame.columns:
        options_frame["pl_num"] = pd.to_numeric(options_frame["pl"], errors="coerce").fillna(0)
    else:
        options_frame["pl_num"] = 0
    options_frame = options_frame.sort_values(["camadas_num", "pl_num"], ascending=[False, False]).head(250)
    options = {
        f"{row.get('nome_exibicao', row.get('denominacao', 'FIDC'))} · {row.get('cnpj_fundo', '')}": row.get("cnpj_fundo", "")
        for _, row in options_frame.iterrows()
    }
    with ctrl_b:
        selected_label = st.selectbox("FIDC", list(options), key="industry_dossier_fund") if options else ""
    if not selected_label:
        st.caption("Nenhum FIDC encontrado para a busca.")
        return

    selected_cnpj = options[selected_label]
    issuance_tables = _load_issuance_tables()
    document_tables = _load_document_tables()
    criteria_tables = _load_criteria_tables()
    dossier = _build_fund_dossier_tables(
        cnpj=selected_cnpj,
        snapshot=snapshot,
        tranches=issuance_tables["tranches"] if isinstance(issuance_tables["tranches"], pd.DataFrame) else pd.DataFrame(),
        documents=document_tables["inventory"] if isinstance(document_tables["inventory"], pd.DataFrame) else pd.DataFrame(),
        cedentes=_build_structured_cedentes(),
        criteria=criteria_tables["structured"] if isinstance(criteria_tables["structured"], pd.DataFrame) else pd.DataFrame(),
    )
    snapshot_rows = dossier["snapshot"]
    row = snapshot_rows.iloc[0] if not snapshot_rows.empty else pd.Series(dtype=object)
    cards = [
        _curation_card("PL", _fmt_bi(float(pd.to_numeric(pd.Series([row.get("pl", 0)]), errors="coerce").fillna(0).iloc[0]), 1), str(row.get("competencia", ""))),
        _curation_card("Status", str(row.get("snapshot_status", "n/d")), f"{row.get('camadas_com_evidencia', 0)} camadas"),
        _curation_card("Emissões 25-26", _fmt_bi(float(pd.to_numeric(pd.Series([row.get("valid_volume_2025_brl", 0)]), errors="coerce").fillna(0).iloc[0]) + float(pd.to_numeric(pd.Series([row.get("valid_volume_2026_brl", 0)]), errors="coerce").fillna(0).iloc[0]), 1), str(row.get("indexadores", "n/d"))[:48]),
        _curation_card("Documentos", _fmt_int(float(len(dossier["documents"]))), str(row.get("document_chunk_ids", ""))[:48]),
        _curation_card("Cedentes", _fmt_int(float(len(dossier["cedentes"]))), str(row.get("cedentes_top", ""))[:48]),
        _curation_card("Critérios", _fmt_int(float(len(dossier["criteria"]))), f"sub mín. {_pct_label(row.get('sub_min_pct_median'))}"),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    tab_snapshot, tab_emissions, tab_documents, tab_cedentes, tab_criteria = st.tabs(
        ["Resumo", "Emissões", "Documentos", "Cedentes", "Critérios"]
    )
    with tab_snapshot:
        st.dataframe(_format_fund_snapshot_table(snapshot_rows), hide_index=True, width="stretch")
        summary = _fund_dossier_layer_summary(dossier)
        st.dataframe(summary, hide_index=True, width="stretch")
    with tab_emissions:
        columns = [
            "data_deliberacao",
            "ano",
            "periodo",
            "tipo_cota",
            "indexador",
            "volume_brl",
            "documento_origem",
            "score_confianca",
            "pricing_evidence",
            "remuneracao_texto",
            "amortizacao_texto",
        ]
        show = _select_display_columns(
            dossier["tranches"],
            columns,
            {
                "data_deliberacao": "Data",
                "ano": "Ano",
                "periodo": "Período",
                "tipo_cota": "Tipo cota",
                "indexador": "Indexador",
                "volume_brl": "Volume",
                "documento_origem": "Documento",
                "score_confianca": "Score",
                "pricing_evidence": "Evidência",
                "remuneracao_texto": "Remuneração",
                "amortizacao_texto": "Amortização",
            },
        )
        st.dataframe(_format_dossier_money(show, ["Volume"]), hide_index=True, width="stretch")
    with tab_documents:
        columns = [
            "chunk_id",
            "document_class",
            "content_kind",
            "document_date",
            "local_exists",
            "bytes",
            "hash_status",
            "processing_status",
            "documento_id",
            "documento_origem",
            "source_table",
            "source_field",
            "local_path",
            "sha256",
        ]
        show = _select_display_columns(
            dossier["documents"],
            columns,
            {
                "chunk_id": "Chunk",
                "document_class": "Classe",
                "content_kind": "Tipo",
                "document_date": "Data",
                "local_exists": "Local",
                "bytes": "Tamanho",
                "hash_status": "Hash",
                "processing_status": "Status",
                "documento_id": "ID doc",
                "documento_origem": "Documento",
                "source_table": "Fonte",
                "source_field": "Campo fonte",
                "local_path": "Arquivo local",
                "sha256": "SHA-256",
            },
        )
        if "Tamanho" in show.columns:
            show["Tamanho"] = show["Tamanho"].map(_format_bytes)
        st.dataframe(show, hide_index=True, width="stretch")
    with tab_cedentes:
        columns = [
            "tipo_participante",
            "razao_social",
            "nome_fantasia",
            "cnpj_participante",
            "grupo_economico",
            "setor",
            "segmento",
            "status_revisao",
            "review_event_count",
            "last_review_at_utc",
            "last_review_field",
            "score_confianca_final",
            "n_evidencias",
            "documento_origem",
            "pagina",
            "metodo_extracao",
            "evidencia",
        ]
        show = _select_display_columns(
            dossier["cedentes"],
            columns,
            {
                "tipo_participante": "Tipo",
                "razao_social": "Razão social",
                "nome_fantasia": "Fantasia",
                "cnpj_participante": "CNPJ participante",
                "grupo_economico": "Grupo",
                "setor": "Setor",
                "segmento": "Segmento",
                "status_revisao": "Status revisão",
                "review_event_count": "Eventos revisão",
                "last_review_at_utc": "Última revisão",
                "last_review_field": "Campo revisado",
                "score_confianca_final": "Score",
                "n_evidencias": "Evidências",
                "documento_origem": "Documento",
                "pagina": "Página",
                "metodo_extracao": "Método",
                "evidencia": "Trecho",
            },
        )
        st.dataframe(show, hide_index=True, width="stretch")
    with tab_criteria:
        columns = [
            "criterio",
            "chave",
            "limite_regra",
            "pct_min",
            "pct_max",
            "monitorabilidade_ime",
            "metrica_ime_proxy",
            "condicao_alerta_sugerida",
            "documento_origem",
            "documento_id",
            "document_date",
            "pagina",
            "status_revisao",
            "review_event_count",
            "last_review_at_utc",
            "last_review_field",
            "score_confianca_final",
            "notas_revisao",
        ]
        show = _select_display_columns(
            dossier["criteria"],
            columns,
            {
                "criterio": "Critério",
                "chave": "Chave",
                "limite_regra": "Limite/regra",
                "pct_min": "Mín. %",
                "pct_max": "Máx. %",
                "monitorabilidade_ime": "Monitorabilidade",
                "metrica_ime_proxy": "Proxy IME",
                "condicao_alerta_sugerida": "Alerta",
                "documento_origem": "Documento",
                "documento_id": "ID doc",
                "document_date": "Data doc.",
                "pagina": "Página",
                "status_revisao": "Status revisão",
                "review_event_count": "Eventos revisão",
                "last_review_at_utc": "Última revisão",
                "last_review_field": "Campo revisado",
                "score_confianca_final": "Score",
                "notas_revisao": "Notas",
            },
        )
        st.dataframe(show, hide_index=True, width="stretch")


_SNAPSHOT_MARKET_MULTI_COLUMNS = {"indexadores", "tipo_cotas", "document_classes", "criteria_keys", "document_chunk_ids"}


def _snapshot_metric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _snapshot_bool_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(False, index=frame.index)
    return frame[column].astype(str).str.lower().isin({"true", "1", "sim", "s", "yes"})


def _prepare_snapshot_market_frame(snapshot: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if snapshot.empty:
        return snapshot.copy()
    frame = snapshot.copy()
    frame["_metric_weight"] = 1.0
    if dimension in _SNAPSHOT_MARKET_MULTI_COLUMNS:
        if dimension not in frame.columns:
            return frame.iloc[0:0].copy()
        values = frame[dimension].map(_split_multivalue)
        counts = values.map(len)
        frame = frame[counts.gt(0)].copy()
        if frame.empty:
            return frame
        values = values.loc[frame.index]
        counts = counts.loc[frame.index]
        frame[dimension] = values
        frame["_metric_weight"] = 1.0 / counts
        frame = frame.explode(dimension).reset_index(drop=True)
    frame["_dimension"] = _dimension_series(frame, dimension)
    frame = frame[frame["_dimension"].ne("n/d")].copy()
    return frame


def _build_snapshot_market_share(snapshot: pd.DataFrame, dimension: str, metric: str = "pl") -> tuple[pd.DataFrame, dict[str, float]]:
    frame = _prepare_snapshot_market_frame(snapshot, dimension)
    if frame.empty:
        empty = pd.DataFrame(
            columns=[
                "Dimensão",
                "PL",
                "Emissões 24-26",
                "Fundos eq.",
                "Fundos únicos",
                "Docs",
                "Cedentes",
                "Critérios",
                "Com sub mín.",
                "Com emissão 25-26",
                "Camadas méd.",
                "Métrica",
                "Share",
            ]
        )
        return empty, {"groups": 0.0, "top5_share": 0.0, "top10_share": 0.0, "hhi": 0.0, "total_metric": 0.0}

    frame["_pl_metric"] = _snapshot_metric_series(frame, "pl") * frame["_metric_weight"]
    frame["_issuance_metric"] = _snapshot_metric_series(frame, "valid_volume_2024_2026_brl") * frame["_metric_weight"]
    frame["_fund_metric"] = frame["_metric_weight"]
    frame["_document_metric"] = _snapshot_metric_series(frame, "document_rows") * frame["_metric_weight"]
    frame["_cedente_metric"] = _snapshot_metric_series(frame, "cedente_rows") * frame["_metric_weight"]
    frame["_criteria_metric"] = _snapshot_metric_series(frame, "criteria_rows") * frame["_metric_weight"]
    frame["_sub_min_metric"] = _snapshot_bool_series(frame, "tem_sub_minima").astype(float) * frame["_metric_weight"]
    frame["_emission_2526_metric"] = _snapshot_bool_series(frame, "tem_emissao_2025_2026").astype(float) * frame["_metric_weight"]
    frame["_layers_metric"] = _snapshot_metric_series(frame, "camadas_com_evidencia") * frame["_metric_weight"]

    fund_id = "cnpj_fundo" if "cnpj_fundo" in frame.columns else "cnpj"
    grouped = (
        frame.groupby("_dimension", dropna=False)
        .agg(
            PL=("_pl_metric", "sum"),
            Emissoes_24_26=("_issuance_metric", "sum"),
            Fundos_eq=("_fund_metric", "sum"),
            Fundos_unicos=(fund_id, "nunique"),
            Docs=("_document_metric", "sum"),
            Cedentes=("_cedente_metric", "sum"),
            Criterios=("_criteria_metric", "sum"),
            Com_sub_min=("_sub_min_metric", "sum"),
            Com_emissao_25_26=("_emission_2526_metric", "sum"),
            Camadas_total=("_layers_metric", "sum"),
        )
        .reset_index()
        .rename(columns={"_dimension": "Dimensão"})
    )
    grouped["Camadas méd."] = grouped["Camadas_total"] / grouped["Fundos_eq"].replace(0, pd.NA)
    metric_map = {
        "pl": "PL",
        "issuance": "Emissoes_24_26",
        "funds": "Fundos_eq",
        "documents": "Docs",
        "cedentes": "Cedentes",
        "criteria": "Criterios",
    }
    metric_col = metric_map.get(metric, "PL")
    grouped["Métrica"] = pd.to_numeric(grouped[metric_col], errors="coerce").fillna(0.0)
    total_metric = float(grouped["Métrica"].sum())
    grouped["Share"] = grouped["Métrica"] / total_metric if total_metric else 0.0
    grouped = grouped.sort_values("Métrica", ascending=False).reset_index(drop=True)
    shares = grouped["Share"].fillna(0.0)
    summary = {
        "groups": float(len(grouped)),
        "top5_share": float(shares.head(5).sum()),
        "top10_share": float(shares.head(10).sum()),
        "hhi": float((shares.pow(2).sum()) * 10000),
        "total_metric": total_metric,
    }
    grouped = grouped.rename(
        columns={
            "Emissoes_24_26": "Emissões 24-26",
            "Fundos_eq": "Fundos eq.",
            "Fundos_unicos": "Fundos únicos",
            "Com_sub_min": "Com sub mín.",
            "Com_emissao_25_26": "Com emissão 25-26",
        }
    )
    return grouped.drop(columns=["Camadas_total"], errors="ignore"), summary


def _market_share_options(frame: pd.DataFrame, field_id: str, field_label: str, specs: list[dict[str, object]]) -> dict[str, str]:
    if frame.empty or field_id not in frame.columns or field_label not in frame.columns:
        return {str(spec["label"]): str(spec.get("dimension_id") or spec.get("metric_id")) for spec in specs}
    available = (
        frame[[field_label, field_id]]
        .dropna()
        .astype(str)
        .drop_duplicates()
        .set_index(field_label)[field_id]
        .to_dict()
    )
    ordered: dict[str, str] = {}
    key = "dimension_id" if field_id == "dimension_id" else "metric_id"
    for spec in specs:
        label = str(spec["label"])
        identifier = str(spec[key])
        if available.get(label) == identifier:
            ordered[label] = identifier
    return ordered or available


def _build_materialized_market_share(market_share: pd.DataFrame, dimension_id: str, metric_id: str) -> tuple[pd.DataFrame, dict[str, float]]:
    if market_share.empty:
        return pd.DataFrame(), {"groups": 0.0, "top5_share": 0.0, "top10_share": 0.0, "hhi": 0.0, "total_metric": 0.0}
    frame = market_share[
        market_share.get("dimension_id", pd.Series("", index=market_share.index)).astype(str).eq(dimension_id)
        & market_share.get("metric_id", pd.Series("", index=market_share.index)).astype(str).eq(metric_id)
    ].copy()
    if frame.empty:
        return pd.DataFrame(), {"groups": 0.0, "top5_share": 0.0, "top10_share": 0.0, "hhi": 0.0, "total_metric": 0.0}
    numeric_cols = [
        "metric_value",
        "share",
        "rank",
        "groups",
        "top5_share",
        "top10_share",
        "hhi",
        "pl_brl",
        "issuance_2024_2026_brl",
        "funds_equivalent",
        "funds_unique",
        "document_rows",
        "cedente_rows",
        "criteria_rows",
        "with_subordination_min_equiv",
        "with_issuance_2025_2026_equiv",
        "average_evidence_layers",
    ]
    for col in numeric_cols:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
    frame = frame.sort_values(["rank", "metric_value"], ascending=[True, False])
    out = pd.DataFrame(
        {
            "Dimensão": frame.get("dimension_value", pd.Series("", index=frame.index)).astype(str),
            "PL": frame.get("pl_brl", pd.Series(0.0, index=frame.index)),
            "Emissões 24-26": frame.get("issuance_2024_2026_brl", pd.Series(0.0, index=frame.index)),
            "Fundos eq.": frame.get("funds_equivalent", pd.Series(0.0, index=frame.index)),
            "Fundos únicos": frame.get("funds_unique", pd.Series(0.0, index=frame.index)),
            "Docs": frame.get("document_rows", pd.Series(0.0, index=frame.index)),
            "Cedentes": frame.get("cedente_rows", pd.Series(0.0, index=frame.index)),
            "Critérios": frame.get("criteria_rows", pd.Series(0.0, index=frame.index)),
            "Com sub mín.": frame.get("with_subordination_min_equiv", pd.Series(0.0, index=frame.index)),
            "Com emissão 25-26": frame.get("with_issuance_2025_2026_equiv", pd.Series(0.0, index=frame.index)),
            "Camadas méd.": frame.get("average_evidence_layers", pd.Series(0.0, index=frame.index)),
            "Métrica": frame.get("metric_value", pd.Series(0.0, index=frame.index)),
            "Share": frame.get("share", pd.Series(0.0, index=frame.index)),
        }
    )
    first = frame.iloc[0]
    return out, {
        "groups": float(first.get("groups", len(out)) or 0.0),
        "top5_share": float(first.get("top5_share", 0.0) or 0.0),
        "top10_share": float(first.get("top10_share", 0.0) or 0.0),
        "hhi": float(first.get("hhi", 0.0) or 0.0),
        "total_metric": float(frame.get("metric_value", pd.Series(0.0, index=frame.index)).sum()),
    }


def _format_snapshot_market_table(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in ["PL", "Emissões 24-26"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_bi(float(value), 1))
    for col in ["Fundos eq.", "Docs", "Cedentes", "Critérios", "Com sub mín.", "Com emissão 25-26"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: f"{float(value):,.1f}".replace(",", "@").replace(".", ",").replace("@", "."))
    if "Fundos únicos" in out.columns:
        out["Fundos únicos"] = pd.to_numeric(out["Fundos únicos"], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
    if "Camadas méd." in out.columns:
        out["Camadas méd."] = pd.to_numeric(out["Camadas méd."], errors="coerce").map(
            lambda value: "n/d" if pd.isna(value) else f"{float(value):.1f}".replace(".", ",")
        )
    if "Share" in out.columns:
        out["Share"] = pd.to_numeric(out["Share"], errors="coerce").fillna(0).map(_fmt_pct)
    if "Métrica" in out.columns:
        out = out.drop(columns=["Métrica"])
    return out


def _render_snapshot_market_share(snapshot: pd.DataFrame) -> None:
    st.markdown("**Market share e concentração do snapshot**")
    market_tables = _load_market_share_tables()
    market_share = market_tables["market_share"]
    market_manifest = market_tables["manifest"]
    assert isinstance(market_share, pd.DataFrame)
    assert isinstance(market_manifest, dict)
    dimension_columns = {str(spec["label"]): str(spec["column"]) for spec in MARKET_SHARE_DIMENSIONS}
    metric_ids = {str(spec["label"]): str(spec["metric_id"]) for spec in MARKET_SHARE_METRICS}
    if not market_share.empty:
        dimensions = _market_share_options(market_share, "dimension_id", "dimension_label", MARKET_SHARE_DIMENSIONS)
        metrics = _market_share_options(market_share, "metric_id", "metric_label", MARKET_SHARE_METRICS)
    else:
        dimensions = {str(spec["label"]): str(spec["column"]) for spec in MARKET_SHARE_DIMENSIONS}
        metrics = metric_ids
    ctrl_a, ctrl_b, ctrl_c = st.columns([1.0, 0.9, 0.65])
    with ctrl_a:
        dim_label = st.selectbox("Dimensão", list(dimensions), key="industry_snapshot_market_dimension")
    with ctrl_b:
        metric_label = st.selectbox("Métrica", list(metrics), key="industry_snapshot_market_metric")
    with ctrl_c:
        top_n = st.slider("Top", min_value=5, max_value=30, value=15, step=1, key="industry_snapshot_market_top")

    uses_materialized = not market_share.empty
    if uses_materialized:
        market, summary = _build_materialized_market_share(market_share, dimensions[dim_label], metrics[metric_label])
        if market.empty and dim_label in dimension_columns:
            uses_materialized = False
            market, summary = _build_snapshot_market_share(snapshot, dimension_columns[dim_label], metric_ids.get(metric_label, "pl"))
    else:
        market, summary = _build_snapshot_market_share(snapshot, dimensions[dim_label], metrics[metric_label])
    if market.empty:
        st.caption("Sem dados para a dimensão selecionada.")
        return

    cards = [
        _curation_card("Grupos", _fmt_int(summary["groups"]), dim_label),
        _curation_card("Top 5", _fmt_pct(summary["top5_share"]), metric_label),
        _curation_card("Top 10", _fmt_pct(summary["top10_share"]), metric_label),
        _curation_card("HHI", _fmt_int(summary["hhi"]), "0-10.000"),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    chart_data = market.head(top_n).copy()
    chart_data["Métrica_fmt"] = chart_data["Métrica"]
    if metric_label in {"PL", "Emissões 24-26"}:
        chart_data["Métrica_plot"] = chart_data["Métrica"] / 1e9
        x_title = "R$ bi"
    else:
        chart_data["Métrica_plot"] = chart_data["Métrica"]
        x_title = metric_label
    chart = (
        alt.Chart(chart_data)
        .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
        .encode(
            x=alt.X("Métrica_plot:Q", title=x_title, axis=alt.Axis(gridColor=_GRAY_LIGHT)),
            y=alt.Y("Dimensão:N", title=None, sort="-x", axis=alt.Axis(labelLimit=260)),
            tooltip=[
                alt.Tooltip("Dimensão:N", title=dim_label),
                alt.Tooltip("Métrica_plot:Q", title=x_title, format=",.2f"),
                alt.Tooltip("Share:Q", title="share", format=".1%"),
                alt.Tooltip("Fundos únicos:Q", title="fundos"),
            ],
        )
        .properties(height=max(280, 24 * len(chart_data)))
    )
    st.altair_chart(chart, width="stretch")
    st.dataframe(_format_snapshot_market_table(market.head(120)), hide_index=True, width="stretch")
    if uses_materialized:
        weighted = market_share[
            market_share.get("dimension_id", pd.Series("", index=market_share.index)).astype(str).eq(dimensions[dim_label])
        ].get("weighted_multivalue", pd.Series(False)).astype(str).str.lower().isin({"true", "1"}).any()
        generated_at = market_manifest.get("generated_at_utc", "")
        source_note = f"Fonte: `{_MARKET_SHARE_PATH.name}`"
        if generated_at:
            source_note += f" · gerado em {generated_at}"
        st.caption(source_note)
    else:
        weighted = dimension_columns.get(dim_label, dimensions[dim_label]) in _SNAPSHOT_MARKET_MULTI_COLUMNS
    if weighted:
        st.caption("Dimensões multivalor são ponderadas por item para preservar o PL/volume total do snapshot.")


def _render_fund_snapshot_universe() -> None:
    st.markdown('<div class="industry-section">Universo estruturado por FIDC</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Uma linha por CNPJ, consolidando foto IME, emissões, documentos, '
        "cedentes/sacados e critérios. As bases detalhe continuam preservadas para auditoria.</div>",
        unsafe_allow_html=True,
    )
    tables = _load_fund_snapshot_tables()
    snapshot = tables["snapshot"]
    manifest = tables["manifest"]
    assert isinstance(snapshot, pd.DataFrame)
    assert isinstance(manifest, dict)
    if snapshot.empty:
        st.info("Snapshot ainda não gerado. Rode `python scripts/build_fidc_industry_fund_snapshot.py`.")
        return

    numeric = snapshot.copy()
    for col in [
        "pl",
        "valid_volume_2024_2026_brl",
        "document_rows",
        "document_local_ready",
        "cedente_rows",
        "participant_signal_rows",
        "criteria_rows",
        "criteria_subordination_rows",
        "camadas_com_evidencia",
    ]:
        if col in numeric.columns:
            numeric[col] = pd.to_numeric(numeric[col], errors="coerce").fillna(0)
    cards = [
        _curation_card("FIDCs no snapshot", _fmt_int(float(len(numeric))), f"{_fmt_bi(float(numeric.get('pl', pd.Series(dtype=float)).sum()), 0)} PL"),
        _curation_card("Com emissões 25-26", _fmt_int(float(numeric.get("tem_emissao_2025_2026", pd.Series(False, index=numeric.index)).astype(str).str.lower().isin({"true", "1"}).sum())), "base Estratégia/ofertas"),
        _curation_card("Com documentos", _fmt_int(float((numeric.get("document_rows", pd.Series(0, index=numeric.index)) > 0).sum())), "inventário local/CVM"),
        _curation_card("Cedentes identificados", _fmt_int(float((numeric.get("cedente_rows", pd.Series(0, index=numeric.index)) > 0).sum())), "participante extraído"),
        _curation_card("Sinal cedente/sacado", _fmt_int(float((numeric.get("participant_signal_rows", pd.Series(0, index=numeric.index)) > 0).sum())), "matriz Estratégia"),
        _curation_card("Com critérios", _fmt_int(float((numeric.get("criteria_rows", pd.Series(0, index=numeric.index)) > 0).sum())), "regras monitoráveis"),
        _curation_card("Com sub mín.", _fmt_int(float((numeric.get("criteria_subordination_rows", pd.Series(0, index=numeric.index)) > 0).sum())), "percentual extraído"),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    tab_table, tab_dossier, tab_market, tab_coverage, tab_manifest = st.tabs(["Tabela", "Dossiê", "Market Share", "Cobertura", "Manifesto"])
    with tab_table:
        ctrl_a, ctrl_b, ctrl_c, ctrl_d = st.columns([1.15, 0.9, 0.75, 0.65])
        with ctrl_a:
            query = st.text_input("Buscar", key="industry_snapshot_query", placeholder="FIDC, CNPJ, administrador, cedente")
        with ctrl_b:
            segment_options = sorted(
                set(
                    numeric.get("segmento_principal", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
                    .replace("", "n/d")
                    .tolist()
                )
            )
            segment_filter = st.multiselect("Segmento", segment_options, default=segment_options, key="industry_snapshot_segment")
        with ctrl_c:
            status_options = sorted(numeric.get("snapshot_status", pd.Series(dtype=str)).fillna("").astype(str).replace("", "n/d").unique())
            status_filter = st.multiselect("Status", status_options, default=status_options, key="industry_snapshot_status")
        with ctrl_d:
            min_layers = st.slider("Camadas mín.", min_value=1, max_value=5, value=1, step=1, key="industry_snapshot_layers")

        filtered = numeric.copy()
        segment_values = filtered.get("segmento_principal", pd.Series("", index=filtered.index)).fillna("").astype(str).str.strip().replace("", "n/d")
        status_values = filtered.get("snapshot_status", pd.Series("", index=filtered.index)).fillna("").astype(str).replace("", "n/d")
        filtered = filtered[
            segment_values.isin(segment_filter)
            & status_values.isin(status_filter)
            & pd.to_numeric(filtered.get("camadas_com_evidencia", pd.Series(0, index=filtered.index)), errors="coerce").fillna(0).ge(min_layers)
        ].copy()
        if query:
            haystack = (
                filtered.get("nome_exibicao", pd.Series("", index=filtered.index)).fillna("").astype(str)
                + " "
                + filtered.get("cnpj_fundo", pd.Series("", index=filtered.index)).fillna("").astype(str)
                + " "
                + filtered.get("admin_nome", pd.Series("", index=filtered.index)).fillna("").astype(str)
                + " "
                + filtered.get("cedentes_top", pd.Series("", index=filtered.index)).fillna("").astype(str)
            )
            filtered = filtered[haystack.str.contains(query, case=False, na=False)].copy()
        filtered = filtered.sort_values(["pl", "camadas_com_evidencia"], ascending=[False, False]).head(300)
        st.dataframe(_format_fund_snapshot_table(filtered), hide_index=True, width="stretch")

    with tab_dossier:
        _render_fund_dossier(numeric)

    with tab_market:
        _render_snapshot_market_share(numeric)

    with tab_coverage:
        coverage_rows = [
            {"Camada": "Emissões 2025-2026", "FIDCs": int(numeric.get("tem_emissao_2025_2026", pd.Series(False, index=numeric.index)).astype(str).str.lower().isin({"true", "1"}).sum())},
            {"Camada": "Documentos", "FIDCs": int((numeric.get("document_rows", pd.Series(0, index=numeric.index)) > 0).sum())},
            {"Camada": "Documentos locais", "FIDCs": int((numeric.get("document_local_ready", pd.Series(0, index=numeric.index)) > 0).sum())},
            {"Camada": "Cedentes/sacados identificados", "FIDCs": int((numeric.get("cedente_rows", pd.Series(0, index=numeric.index)) > 0).sum())},
            {"Camada": "Sinal cedente/sacado", "FIDCs": int((numeric.get("participant_signal_rows", pd.Series(0, index=numeric.index)) > 0).sum())},
            {"Camada": "Critérios", "FIDCs": int((numeric.get("criteria_rows", pd.Series(0, index=numeric.index)) > 0).sum())},
            {"Camada": "Sub mínima", "FIDCs": int((numeric.get("criteria_subordination_rows", pd.Series(0, index=numeric.index)) > 0).sum())},
        ]
        coverage = pd.DataFrame(coverage_rows)
        coverage["Cobertura"] = coverage["FIDCs"] / max(len(numeric), 1) * 100
        st.altair_chart(
            alt.Chart(coverage)
            .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
            .encode(
                x=alt.X("Cobertura:Q", title="% dos FIDCs", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                y=alt.Y("Camada:N", title=None, sort="-x"),
                tooltip=[
                    alt.Tooltip("Camada:N"),
                    alt.Tooltip("FIDCs:Q"),
                    alt.Tooltip("Cobertura:Q", format=",.1f"),
                ],
            )
            .properties(height=260),
            width="stretch",
        )
        if "snapshot_status" in numeric.columns:
            status = numeric["snapshot_status"].fillna("n/d").astype(str).value_counts().reset_index()
            status.columns = ["Status", "FIDCs"]
            st.dataframe(status, hide_index=True, width="stretch")
        gap_actions = _load_snapshot_gap_actions()
        gaps = _apply_snapshot_gap_actions(_snapshot_gap_frame(numeric), gap_actions)
        st.markdown("**Fila de lacunas por FIDC**")
        if gaps.empty:
            st.caption("Nenhuma lacuna encontrada nas camadas estruturadas do snapshot.")
        else:
            gap_a, gap_b, gap_c = st.columns([1.05, 0.8, 1.1])
            all_layers = sorted(
                {
                    layer
                    for value in gaps["missing_layers"].fillna("").astype(str)
                    for layer in [part.strip() for part in value.split("|")]
                    if layer
                }
            )
            with gap_a:
                selected_layers = st.multiselect(
                    "Camada faltante",
                    all_layers,
                    default=all_layers,
                    key="industry_snapshot_gap_layers",
                )
            with gap_b:
                priority_only = st.checkbox("Só prioridade 25-26", value=True, key="industry_snapshot_gap_priority")
            with gap_c:
                gap_query = st.text_input("Buscar lacuna", key="industry_snapshot_gap_query", placeholder="FIDC, CNPJ, administrador")
            gap_view = gaps.copy()
            if selected_layers:
                gap_view = gap_view[
                    gap_view["missing_layers"].fillna("").astype(str).map(
                        lambda value: any(layer in {part.strip() for part in value.split("|")} for layer in selected_layers)
                    )
                ].copy()
            if priority_only and "priority_2025_2026" in gap_view.columns:
                gap_view = gap_view[gap_view["priority_2025_2026"].astype(bool)].copy()
            if gap_query:
                search_cols = [
                    col
                    for col in [
                        "nome_exibicao",
                        "cnpj_fundo",
                        "admin_nome",
                        "gestor_nome",
                        "segmento_principal",
                        "missing_layers",
                    ]
                    if col in gap_view.columns
                ]
                haystack = gap_view[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=gap_view.index)
                gap_view = gap_view[haystack.str.contains(gap_query, case=False, na=False)].copy()
            gap_cards = [
                _curation_card("FIDCs com lacuna", _fmt_int(float(len(gap_view))), "filtro atual"),
                _curation_card(
                    "Prioridade 25-26",
                    _fmt_int(float(gap_view.get("priority_2025_2026", pd.Series(False, index=gap_view.index)).astype(bool).sum())),
                    "emissões recentes",
                ),
                _curation_card("PL monitorado", _fmt_bi(float(pd.to_numeric(gap_view.get("pl", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()), 1), "filtro atual"),
            ]
            st.markdown(f'<div class="industry-kpi-grid">{"".join(gap_cards)}</div>', unsafe_allow_html=True)
            gap_page = gap_view.head(160).copy()
            gap_display = _format_snapshot_gap_table(gap_page)
            edited_gaps = st.data_editor(
                gap_display,
                hide_index=True,
                width="stretch",
                height=520,
                disabled=[
                    col
                    for col in gap_display.columns
                    if col not in {"Status lacuna", "Ação revisada", "Responsável", "Prazo", "Notas"}
                ],
                column_config={
                    "ID": st.column_config.TextColumn("ID", width="small"),
                    "Status lacuna": st.column_config.SelectboxColumn(
                        "Status lacuna",
                        options=["pendente", "em andamento", "corrigido", "aceito", "ignorado"],
                        required=True,
                    ),
                    "Ação revisada": st.column_config.TextColumn("Ação revisada", width="large"),
                    "Notas": st.column_config.TextColumn("Notas", width="large"),
                },
                key="industry_snapshot_gap_editor",
            )
            if st.button("Salvar acompanhamento das lacunas", type="primary", key="industry_save_snapshot_gap_actions"):
                saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                edited_actions_all = pd.DataFrame(
                    {
                        "gap_id": edited_gaps["ID"].fillna("").astype(str),
                        "status_lacuna": edited_gaps["Status lacuna"].fillna("").astype(str).replace("", "pendente"),
                        "acao_revisada": edited_gaps["Ação revisada"].fillna("").astype(str),
                        "responsavel": edited_gaps["Responsável"].fillna("").astype(str),
                        "prazo": edited_gaps["Prazo"].fillna("").astype(str),
                        "notas": edited_gaps["Notas"].fillna("").astype(str),
                        "updated_at_utc": saved_at,
                    }
                )
                text_cols = ["acao_revisada", "responsavel", "prazo", "notas"]
                material = edited_actions_all["status_lacuna"].ne("pendente") | (
                    edited_actions_all[text_cols].fillna("").astype(str).agg(" ".join, axis=1).str.strip().ne("")
                )
                edited_actions_all = edited_actions_all[edited_actions_all["gap_id"].str.strip().ne("")].copy()
                edited_actions = edited_actions_all[material.loc[edited_actions_all.index]].copy()
                visible_ids = set(edited_gaps["ID"].fillna("").astype(str))
                existing = gap_actions.copy()
                if not existing.empty and "gap_id" in existing.columns:
                    existing = existing[~existing["gap_id"].fillna("").astype(str).isin(visible_ids)].copy()
                updated_actions = pd.concat([existing, edited_actions], ignore_index=True)
                audit_source = pd.concat([existing, edited_actions_all], ignore_index=True)
                audit_events = build_review_audit_events(
                    previous=_snapshot_gap_actions_for_audit(gap_actions),
                    updated=_snapshot_gap_actions_for_audit(audit_source),
                    key_column="gap_id",
                    review_domain="snapshot_gap",
                    saved_at_utc=saved_at,
                    source="industry_snapshot_gap_editor",
                )
                _save_snapshot_gap_actions(updated_actions)
                append_review_audit_events(audit_events, _SNAPSHOT_GAP_ACTION_AUDIT_PATH)
                _load_snapshot_gap_actions.clear()
                st.success(
                    f"Acompanhamento salvo para {_fmt_int(float(len(edited_actions)))} lacunas visíveis; "
                    f"{_fmt_int(float(len(audit_events)))} eventos no histórico."
                )
            st.download_button(
                "Baixar fila de lacunas",
                data=gap_view.to_csv(index=False).encode("utf-8"),
                file_name="industry_snapshot_gap_queue.csv",
                mime="text/csv",
                key="industry_snapshot_gap_download",
            )
            with st.expander("Histórico de revisão das lacunas"):
                _render_review_audit(
                    _SNAPSHOT_GAP_ACTION_AUDIT_PATH,
                    empty_label="Nenhum histórico de lacunas salvo ainda.",
                )

    with tab_manifest:
        if manifest:
            st.download_button(
                "Baixar manifesto",
                data=json.dumps(manifest, ensure_ascii=False, indent=2),
                file_name="industry_fund_snapshot_manifest.json",
                mime="application/json",
            )
            st.json(manifest)
        else:
            st.caption("Manifesto do snapshot ainda não encontrado.")


def _render_monthly_audit_and_base(industry: pd.DataFrame, comp: str) -> None:
    vehicle = _load_csv(
        "vehicle_monthly.csv.gz",
        _industry_files_signature(("vehicle_monthly.csv.gz",)),
    )
    audit = _load_csv(
        "update_audit_monthly.csv",
        _industry_files_signature(("update_audit_monthly.csv",)),
    )
    if (vehicle is None or vehicle.empty) and (audit is None or audit.empty):
        st.markdown('<div class="industry-section">Auditoria mensal e base granular</div>', unsafe_allow_html=True)
        st.info(
            "A base granular ainda não foi gerada. Rode `python scripts/build_fidc_industry_study.py --report` "
            "para criar `vehicle_monthly.csv.gz` e `update_audit_monthly.csv`."
        )
        return

    st.markdown('<div class="industry-section">Auditoria mensal e base granular</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Camada inspirada na aba Estratégia: cada agregado pode ser reaberto '
        "em competência × veículo reportante, com cobertura de tabelas-fonte e filtros de sanidade.</div>",
        unsafe_allow_html=True,
    )

    current_vehicle = pd.DataFrame()
    if vehicle is not None and not vehicle.empty:
        current_vehicle = vehicle[vehicle["competencia"].eq(comp)].copy()

    audit_last = None
    if audit is not None and not audit.empty:
        match = audit[audit["competencia"].eq(comp)]
        audit_last = match.iloc[0] if not match.empty else audit.sort_values("competencia").iloc[-1]

    cards = []
    if not current_vehicle.empty:
        cards.append(_curation_card("Linhas granulares", _fmt_int(len(current_vehicle)), f"{comp} · veículo/classe"))
        cards.append(_curation_card("Fundos únicos", _fmt_int(current_vehicle["cnpj_fundo"].nunique() if "cnpj_fundo" in current_vehicle else current_vehicle["cnpj"].nunique()), "após mapa classe → fundo"))
    if audit_last is not None:
        cards.extend(
            [
                _curation_card("Cobertura Tab I", _fmt_pct(float(audit_last.get("tab1_coverage", 0))), "ativo, DC, admin"),
                _curation_card("Cobertura Tab X.4", _fmt_pct(float(audit_last.get("x4_coverage", 0))), "fluxos de cotas"),
                _curation_card("Fluxo descartado", _fmt_bi(float(audit_last.get("x4_valor_descartado", 0))), f"{_fmt_int(float(audit_last.get('x4_linhas_descartadas', 0)))} linhas"),
                _curation_card("Picos removidos", _fmt_int(float(audit_last.get("pl_spike_excluidos", 0)) + float(audit_last.get("cotistas_spike_excluidos", 0))), "PL/cotistas"),
            ]
        )
    if cards:
        st.markdown(f'<div class="industry-kpi-grid">{"".join(cards[:6])}</div>', unsafe_allow_html=True)

    col_a, col_b = st.columns([0.9, 1.1])
    with col_a:
        st.markdown("**Cobertura das tabelas-fonte**")
        if audit is not None and not audit.empty:
            coverage_cols = [
                ("tab1_coverage", "Tab I"),
                ("tab2_coverage", "Tab II"),
                ("x1_coverage", "X.1"),
                ("x2_coverage", "X.2"),
                ("x4_coverage", "X.4"),
            ]
            cov = audit.tail(36).copy()
            cov["mes"] = pd.to_datetime(cov["competencia"] + "-01")
            cov_long = []
            for col, label in coverage_cols:
                if col in cov.columns:
                    cov_long.append(cov.assign(Tabela=label, Cobertura=cov[col] * 100))
            if cov_long:
                cov_long_df = pd.concat(cov_long, ignore_index=True)
                chart = (
                    alt.Chart(cov_long_df)
                    .mark_line(strokeWidth=2)
                    .encode(
                        x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False)),
                        y=alt.Y("Cobertura:Q", title="% dos veículos", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                        color=alt.Color("Tabela:N", legend=alt.Legend(title=None, orient="top")),
                        tooltip=[
                            alt.Tooltip("competencia:N", title="competência"),
                            alt.Tooltip("Tabela:N", title="tabela"),
                            alt.Tooltip("Cobertura:Q", title="cobertura", format=",.1f"),
                        ],
                    )
                    .properties(height=260)
                )
                st.altair_chart(chart, width="stretch")
        else:
            st.caption("Arquivo de auditoria mensal indisponível.")

    with col_b:
        st.markdown("**Maiores variações de PL no mês**")
        if vehicle is not None and not vehicle.empty and not current_vehicle.empty:
            comps = sorted(vehicle["competencia"].dropna().unique())
            if comp in comps and comps.index(comp) > 0:
                prev_comp = comps[comps.index(comp) - 1]
                prev = vehicle[vehicle["competencia"].eq(prev_comp)][["cnpj", "pl"]].rename(columns={"pl": "pl_anterior"})
                movers = current_vehicle.merge(prev, on="cnpj", how="left")
                movers["pl_delta"] = movers["pl"] - movers["pl_anterior"].fillna(0.0)
                movers = movers[movers["pl_delta"].abs() > 5e7].copy()
                movers = movers.reindex(movers["pl_delta"].abs().sort_values(ascending=False).index).head(12)
                if not movers.empty:
                    movers["nome_curto"] = movers["denominacao"].astype(str).str.slice(0, 54)
                    movers["delta_bi"] = movers["pl_delta"] / 1e9
                    chart = (
                        alt.Chart(movers)
                        .mark_bar(cornerRadiusEnd=2)
                        .encode(
                            x=alt.X("delta_bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                            y=alt.Y("nome_curto:N", title=None, sort="-x", axis=alt.Axis(labelLimit=260)),
                            color=alt.condition("datum.delta_bi >= 0", alt.value(_ORANGE), alt.value(_BLACK)),
                            tooltip=[
                                alt.Tooltip("denominacao:N", title="veículo"),
                                alt.Tooltip("cnpj:N", title="CNPJ"),
                                alt.Tooltip("delta_bi:Q", title="variação PL (R$ bi)", format=",.2f"),
                            ],
                        )
                        .properties(height=260)
                    )
                    st.altair_chart(chart, width="stretch")
                else:
                    st.caption("Sem variações materiais acima de R$ 50 mi.")
            else:
                st.caption("Competência sem mês anterior na base granular.")
        else:
            st.caption("Base granular indisponível.")

    if vehicle is None or vehicle.empty:
        return

    st.markdown("**Base granular filtrável**")
    comps = sorted(vehicle["competencia"].dropna().unique(), reverse=True)
    default_idx = comps.index(comp) if comp in comps else 0
    selected_comp = st.selectbox("Competência granular", comps, index=default_idx, key="industry_granular_comp")
    filtered = vehicle[vehicle["competencia"].eq(selected_comp)].copy()
    left, mid, right = st.columns([1.15, 1.0, 1.0])
    with left:
        query = st.text_input("Buscar veículo/CNPJ", key="industry_granular_query", placeholder="nome, CNPJ ou administrador")
    with mid:
        metric_label = st.selectbox(
            "Ordenar por",
            ["PL", "Captação líquida", "Carteira DC", "Inadimplência ajustada", "Subordinação"],
            key="industry_granular_metric",
        )
    with right:
        top_n = st.slider("Linhas", min_value=10, max_value=100, value=30, step=10, key="industry_granular_rows")
    if query:
        mask = (
            filtered["denominacao"].astype(str).str.contains(query, case=False, na=False)
            | filtered["cnpj"].astype(str).str.contains(query, case=False, na=False)
            | filtered.get("admin_nome", pd.Series("", index=filtered.index)).astype(str).str.contains(query, case=False, na=False)
        )
        filtered = filtered[mask].copy()
    metric_col = {
        "PL": "pl",
        "Captação líquida": "captacao_liquida",
        "Carteira DC": "carteira_dc",
        "Inadimplência ajustada": "inad_pct_ajustada",
        "Subordinação": "subordinacao_pct",
    }[metric_label]
    if metric_col in filtered.columns:
        filtered = filtered.sort_values(metric_col, ascending=False)
    st.dataframe(_format_vehicle_table(filtered.head(top_n)), hide_index=True, width="stretch")

    with st.expander("Auditoria mensal completa"):
        if audit is not None and not audit.empty:
            show = audit.tail(24).copy()
            percent_cols = [col for col in show.columns if col.endswith("_coverage")]
            for col in percent_cols:
                show[col] = (show[col] * 100).round(1)
            st.dataframe(show, hide_index=True, width="stretch")
        else:
            st.caption("Arquivo `update_audit_monthly.csv` não encontrado.")


def _dimension_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series("n/d", index=frame.index)
    if column == "is_fic_fidc":
        values = frame[column].astype(str).str.lower().isin({"true", "1", "sim", "s", "yes"})
        return values.map({True: "FIC-FIDC", False: "FIDC direto"})
    boolean_labels = {
        "tem_emissao_2025_2026": ("com emissão 2025-2026", "sem emissão 2025-2026"),
        "tem_sub_minima": ("com sub mínima", "sem sub mínima"),
        "tem_cedente": ("com cedente/sacado", "sem cedente/sacado"),
        "tem_documento_local": ("com documento local", "sem documento local"),
    }
    if column in boolean_labels:
        values = frame[column].astype(str).str.lower().isin({"true", "1", "sim", "s", "yes"})
        yes, no = boolean_labels[column]
        return values.map({True: yes, False: no})
    if column == "camadas_com_evidencia":
        numbers = pd.to_numeric(frame[column], errors="coerce").fillna(0).round().astype(int)
        return numbers.map(lambda value: f"{value} camada" if value == 1 else f"{value} camadas")
    values = frame[column].fillna("").astype(str).str.strip()
    values = values.where(values != "", "n/d")
    return values.str.slice(0, 70)


def _period_filter(frame: pd.DataFrame, comp: str, period: str) -> pd.DataFrame:
    comps = sorted(frame["competencia"].dropna().astype(str).unique())
    comps = [value for value in comps if value <= comp]
    if not comps:
        return frame.iloc[0:0].copy()
    if period == "Última competência":
        selected = [comp if comp in comps else comps[-1]]
    elif period == "Últimos 12 meses":
        selected = comps[-12:]
    elif period == "2025 até data-base":
        selected = [value for value in comps if value >= "2025-01"]
    else:
        selected = comps
    return frame[frame["competencia"].astype(str).isin(selected)].copy()


_CEDENTE_HEATMAP_COLUMNS = {
    "razao_social",
    "grupo_economico",
    "tipo_participante",
    "status_revisao",
    "periodo_prioritario",
}


_SNAPSHOT_MULTI_COLUMNS = {
    "indexadores",
    "tipo_cotas",
    "document_classes",
    "criteria_keys",
    "document_chunk_ids",
}

_SNAPSHOT_ANALYSIS_COLUMNS = [
    "cnpj_fundo",
    "segmento_estrategia",
    "subsegmento_estrategia",
    "snapshot_status",
    "camadas_com_evidencia",
    "tem_emissao_2025_2026",
    "tem_sub_minima",
    "tem_cedente",
    "tem_documento_local",
    "sub_min_pct_median",
    "indexadores",
    "tipo_cotas",
    "document_classes",
    "criteria_keys",
    "document_chunk_ids",
    "document_rows",
    "cedente_rows",
    "criteria_rows",
]


def _split_multivalue(value: object) -> list[str]:
    parts = [part.strip() for part in str(value or "").split("|")]
    return [part for part in parts if part and part.lower() not in {"nan", "none", "n/d"}]


def _sub_min_bucket(value: object) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return "sem sub mínima"
    if number < 10:
        return "<10%"
    if number < 15:
        return "10%-15%"
    if number < 25:
        return "15%-25%"
    return ">=25%"


def _enrich_vehicle_with_snapshot(vehicle: pd.DataFrame, snapshot: pd.DataFrame | None) -> pd.DataFrame:
    frame = vehicle.copy()
    id_col = "cnpj_fundo" if "cnpj_fundo" in frame.columns else "cnpj"
    frame["cnpj_fundo_norm"] = frame[id_col].map(normalize_cnpj)
    if snapshot is None or snapshot.empty:
        return frame
    snap = snapshot.copy()
    if "cnpj_fundo" not in snap.columns:
        return frame
    snap["cnpj_fundo_norm"] = snap["cnpj_fundo"].map(normalize_cnpj)
    snap_cols = ["cnpj_fundo_norm"] + [col for col in _SNAPSHOT_ANALYSIS_COLUMNS if col in snap.columns and col != "cnpj_fundo"]
    snap = snap[snap_cols].drop_duplicates("cnpj_fundo_norm", keep="first")
    frame = frame.merge(snap, on="cnpj_fundo_norm", how="left")
    if "sub_min_pct_median" in frame.columns:
        frame["sub_min_bucket"] = frame["sub_min_pct_median"].map(_sub_min_bucket)
    else:
        frame["sub_min_bucket"] = "sem sub mínima"
    return frame


def _apply_multivalue_dimensions(frame: pd.DataFrame, row_col: str, col_col: str) -> pd.DataFrame:
    out = frame.copy()
    if "_metric_weight" not in out.columns:
        out["_metric_weight"] = 1.0
    selected = [col for col in [row_col, col_col] if col in _SNAPSHOT_MULTI_COLUMNS]
    for col in dict.fromkeys(selected):
        if col not in out.columns:
            return out.iloc[0:0].copy()
        values = out[col].map(_split_multivalue)
        counts = values.map(len).replace(0, 1)
        out[col] = values
        out["_metric_weight"] = out["_metric_weight"] / counts
        out = out.explode(col).reset_index(drop=True)
        out[col] = out[col].fillna("").astype(str)
    return out


def _heatmap_base_frame(
    vehicle: pd.DataFrame,
    cedentes: pd.DataFrame,
    snapshot: pd.DataFrame | None,
    row_col: str,
    col_col: str,
) -> pd.DataFrame:
    base = _enrich_vehicle_with_snapshot(vehicle, snapshot)
    if row_col not in _CEDENTE_HEATMAP_COLUMNS and col_col not in _CEDENTE_HEATMAP_COLUMNS:
        frame = base.copy()
        frame["_metric_weight"] = 1.0
        return _apply_multivalue_dimensions(frame, row_col, col_col)
    if cedentes.empty:
        return base.iloc[0:0].copy()
    relations = cedentes.copy()
    relations = relations[relations.get("ativo_curadoria", pd.Series(True, index=relations.index)).astype(bool)].copy()
    relations = relations[relations.get("razao_social", pd.Series("", index=relations.index)).fillna("").astype(str).str.strip() != ""]
    if relations.empty:
        return base.iloc[0:0].copy()
    relations["cnpj_fundo_norm"] = relations["cnpj_fundo"].map(normalize_cnpj)
    relation_cols = [
        "cnpj_fundo_norm",
        "razao_social",
        "grupo_economico",
        "tipo_participante",
        "status_revisao",
        "periodo_prioritario",
        "score_confianca_final",
    ]
    relations = relations[[col for col in relation_cols if col in relations.columns]].drop_duplicates()
    frame = base.copy()
    frame = frame.merge(relations, on="cnpj_fundo_norm", how="inner")
    if frame.empty:
        frame["_metric_weight"] = 1.0
        return frame
    relation_count = frame.groupby(["competencia", "cnpj"], dropna=False)["razao_social"].transform("nunique")
    frame["_metric_weight"] = 1.0 / relation_count.clip(lower=1)
    return _apply_multivalue_dimensions(frame, row_col, col_col)


def _dimension_catalog_options(catalog: pd.DataFrame) -> dict[str, str]:
    if catalog.empty or "dimension_id" not in catalog.columns or "dimension_label" not in catalog.columns:
        return {}
    available = set(catalog["dimension_id"].dropna().astype(str))
    ordered: dict[str, str] = {}
    for spec in DIMENSION_CATALOG_SPECS:
        dimension_id = str(spec["dimension_id"])
        if dimension_id in available:
            ordered[str(spec["label"])] = dimension_id
    return ordered


def _heatmap_preset_options(dimension_labels: list[str]) -> dict[str, tuple[str, str] | None]:
    available = set(dimension_labels)
    options: dict[str, tuple[str, str] | None] = {"Personalizado": None}
    for spec in HEATMAP_PRESET_SPECS:
        label = str(spec["label"])
        row_label = str(spec["row_label"])
        col_label = str(spec["col_label"])
        if row_label in available and col_label in available:
            options[label] = (row_label, col_label)
    return options


def _dimension_catalog_rows(catalog: pd.DataFrame, dimension_id: str) -> pd.DataFrame:
    if catalog.empty or "dimension_id" not in catalog.columns:
        return pd.DataFrame()
    rows = catalog[catalog["dimension_id"].astype(str).eq(str(dimension_id))].copy()
    if rows.empty:
        return rows
    rows["cnpj_fundo_norm"] = rows["cnpj_fundo"].map(normalize_cnpj)
    rows["dimension_value"] = rows["dimension_value"].fillna("").astype(str).str.strip()
    rows["value_weight"] = pd.to_numeric(rows.get("value_weight"), errors="coerce").fillna(1.0)
    return rows[rows["cnpj_fundo_norm"].str.len().eq(14) & rows["dimension_value"].ne("")].copy()


def _base_with_catalog_id(vehicle: pd.DataFrame) -> pd.DataFrame:
    frame = vehicle.copy()
    id_col = "cnpj_fundo" if "cnpj_fundo" in frame.columns else "cnpj"
    frame["cnpj_fundo_norm"] = frame[id_col].map(normalize_cnpj)
    return frame


def _catalog_heatmap_base_frame(vehicle: pd.DataFrame, catalog: pd.DataFrame, row_id: str, col_id: str) -> pd.DataFrame:
    base = _base_with_catalog_id(vehicle)
    row_dim = _dimension_catalog_rows(catalog, row_id)
    col_dim = _dimension_catalog_rows(catalog, col_id)
    if base.empty or row_dim.empty or col_dim.empty:
        return base.iloc[0:0].copy()
    row_keep = [
        "cnpj_fundo_norm",
        "dimension_value",
        "value_weight",
        "source_layer",
        "is_multivalue",
        "is_curated",
    ]
    if row_id == col_id:
        pairs = row_dim[[col for col in row_keep if col in row_dim.columns]].copy()
        pairs = pairs.rename(
            columns={
                "dimension_value": "linha",
                "value_weight": "_metric_weight",
                "source_layer": "row_source_layer",
                "is_multivalue": "row_is_multivalue",
                "is_curated": "row_is_curated",
            }
        )
        pairs["coluna"] = pairs["linha"]
        pairs["col_source_layer"] = pairs["row_source_layer"]
        pairs["col_is_multivalue"] = pairs["row_is_multivalue"]
        pairs["col_is_curated"] = pairs["row_is_curated"]
    else:
        left = row_dim[[col for col in row_keep if col in row_dim.columns]].rename(
            columns={
                "dimension_value": "linha",
                "value_weight": "row_weight",
                "source_layer": "row_source_layer",
                "is_multivalue": "row_is_multivalue",
                "is_curated": "row_is_curated",
            }
        )
        right = col_dim[[col for col in row_keep if col in col_dim.columns]].rename(
            columns={
                "dimension_value": "coluna",
                "value_weight": "col_weight",
                "source_layer": "col_source_layer",
                "is_multivalue": "col_is_multivalue",
                "is_curated": "col_is_curated",
            }
        )
        pairs = left.merge(right, on="cnpj_fundo_norm", how="inner")
        pairs["_metric_weight"] = (
            pd.to_numeric(pairs.get("row_weight"), errors="coerce").fillna(1.0)
            * pd.to_numeric(pairs.get("col_weight"), errors="coerce").fillna(1.0)
        )
    if pairs.empty:
        return base.iloc[0:0].copy()
    frame = base.merge(pairs, on="cnpj_fundo_norm", how="inner")
    return frame


def _catalog_heatmap_cell_frame(
    catalog: pd.DataFrame,
    snapshot: pd.DataFrame,
    row_id: str,
    row_value: str,
    col_id: str,
    col_value: str,
) -> pd.DataFrame:
    row_dim = _dimension_catalog_rows(catalog, row_id)
    col_dim = _dimension_catalog_rows(catalog, col_id)
    if row_dim.empty or col_dim.empty:
        return pd.DataFrame()
    row_dim = row_dim[row_dim["dimension_value"].astype(str).eq(str(row_value))].copy()
    col_dim = col_dim[col_dim["dimension_value"].astype(str).eq(str(col_value))].copy()
    if row_dim.empty or col_dim.empty:
        return pd.DataFrame()

    evidence_cols = [
        "cnpj_fundo_norm",
        "cnpj_fundo",
        "nome_exibicao",
        "dimension_value",
        "value_weight",
        "source_layer",
        "source_field",
        "source_value",
        "is_multivalue",
        "is_curated",
        "participant_type",
        "participant_cnpj",
        "source_document",
        "source_page",
        "source_date",
        "source_method",
        "confidence_score",
        "review_status",
        "priority_2025_2026",
    ]

    def _prefix_dimension(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
        keep = [col for col in evidence_cols if col in frame.columns]
        out = frame[keep].copy()
        return out.rename(columns={col: f"{prefix}_{col}" for col in keep if col != "cnpj_fundo_norm"})

    left = _prefix_dimension(row_dim, "row")
    right = _prefix_dimension(col_dim, "col")
    if str(row_id) == str(col_id):
        if str(row_value) != str(col_value):
            return pd.DataFrame()
        pairs = pd.concat(
            [
                left.reset_index(drop=True),
                right.drop(columns=["cnpj_fundo_norm"], errors="ignore").reset_index(drop=True),
            ],
            axis=1,
        )
    else:
        pairs = left.merge(right, on="cnpj_fundo_norm", how="inner")
    if pairs.empty:
        return pd.DataFrame()

    fund_cols = [
        "cnpj_fundo",
        "nome_exibicao",
        "competencia",
        "pl",
        "valid_volume_2024_2026_brl",
        "admin_nome",
        "gestor_nome",
        "segmento_principal",
        "segmento_estrategia",
        "subsegmento_estrategia",
        "document_rows",
        "cedente_rows",
        "criteria_rows",
        "sub_min_pct_median",
        "snapshot_status",
        "document_chunk_ids",
    ]
    if snapshot is not None and not snapshot.empty:
        funds = snapshot.copy()
        id_col = "cnpj_fundo" if "cnpj_fundo" in funds.columns else "cnpj"
        funds["cnpj_fundo_norm"] = funds[id_col].map(normalize_cnpj)
        funds = funds[[col for col in ["cnpj_fundo_norm", *fund_cols] if col in funds.columns]].drop_duplicates("cnpj_fundo_norm")
        out = pairs.merge(funds, on="cnpj_fundo_norm", how="left")
    else:
        out = pairs.copy()
        out["cnpj_fundo"] = out["cnpj_fundo_norm"]
    if "cnpj_fundo" in out.columns:
        out["cnpj_fundo"] = out["cnpj_fundo"].fillna(out["cnpj_fundo_norm"])
    for col in [
        "pl",
        "valid_volume_2024_2026_brl",
        "document_rows",
        "cedente_rows",
        "criteria_rows",
        "sub_min_pct_median",
        "row_confidence_score",
        "col_confidence_score",
    ]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    sort_cols = [col for col in ["pl", "valid_volume_2024_2026_brl", "nome_exibicao"] if col in out.columns]
    if sort_cols:
        ascending = [False if col != "nome_exibicao" else True for col in sort_cols]
        out = out.sort_values(sort_cols, ascending=ascending)
    return out.reset_index(drop=True)


def _format_heatmap_cell_drilldown(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    columns = [
        "cnpj_fundo",
        "nome_exibicao",
        "pl",
        "valid_volume_2024_2026_brl",
        "admin_nome",
        "gestor_nome",
        "segmento_principal",
        "snapshot_status",
        "row_source_layer",
        "row_source_document",
        "row_source_page",
        "row_source_method",
        "row_confidence_score",
        "row_review_status",
        "col_source_layer",
        "col_source_document",
        "col_source_page",
        "col_source_method",
        "col_confidence_score",
        "col_review_status",
        "document_chunk_ids",
    ]
    out = frame[[col for col in columns if col in frame.columns]].copy()
    out = out.rename(
        columns={
            "cnpj_fundo": "CNPJ",
            "nome_exibicao": "FIDC",
            "pl": "PL",
            "valid_volume_2024_2026_brl": "Emissões 24-26",
            "admin_nome": "Administrador",
            "gestor_nome": "Gestor",
            "segmento_principal": "Segmento",
            "snapshot_status": "Status",
            "row_source_layer": "Fonte linha",
            "row_source_document": "Doc linha",
            "row_source_page": "Pág. linha",
            "row_source_method": "Método linha",
            "row_confidence_score": "Score linha",
            "row_review_status": "Revisão linha",
            "col_source_layer": "Fonte coluna",
            "col_source_document": "Doc coluna",
            "col_source_page": "Pág. coluna",
            "col_source_method": "Método coluna",
            "col_confidence_score": "Score coluna",
            "col_review_status": "Revisão coluna",
            "document_chunk_ids": "Chunks",
        }
    )
    for money_col in ["PL", "Emissões 24-26"]:
        if money_col in out.columns:
            out[money_col] = pd.to_numeric(out[money_col], errors="coerce").fillna(0.0).map(lambda value: _fmt_bi(float(value), 2))
    for score_col in ["Score linha", "Score coluna"]:
        if score_col in out.columns:
            out[score_col] = pd.to_numeric(out[score_col], errors="coerce").map(
                lambda value: "n/d" if pd.isna(value) else f"{float(value):.2f}".replace(".", ",")
            )
    return out


_PROFILE_HEATMAP_METRICS = {
    "PL médio": ("pl_brl", 1e9, "PL (R$ bi)", ",.1f"),
    "Fundos": ("funds_unique", 1.0, "Fundos", ",.0f"),
    "Veículos": ("vehicles_unique", 1.0, "Veículos", ",.0f"),
}


def _profile_heatmap_metric_config(metric_label: str) -> tuple[str, float, str, str] | None:
    return _PROFILE_HEATMAP_METRICS.get(metric_label)


def _profile_heatmap_frame(profiles: pd.DataFrame, row_id: str, col_id: str, metric_label: str) -> pd.DataFrame:
    config = _profile_heatmap_metric_config(metric_label)
    if config is None or profiles.empty:
        return pd.DataFrame()
    metric_col, divisor, _, _ = config
    required = {
        "competencia",
        "source_dimension_id",
        "source_dimension_label",
        "source_dimension_value",
        "target_dimension_id",
        "target_dimension_label",
        "target_dimension_value",
        metric_col,
    }
    if not required.issubset(profiles.columns):
        return pd.DataFrame()
    frame = profiles[
        profiles["source_dimension_id"].astype(str).eq(str(row_id))
        & profiles["target_dimension_id"].astype(str).eq(str(col_id))
    ].copy()
    if frame.empty:
        return pd.DataFrame()
    if str(row_id) == str(col_id):
        frame = frame[
            frame["source_dimension_value"].astype(str).eq(frame["target_dimension_value"].astype(str))
        ].copy()
    if frame.empty:
        return pd.DataFrame()

    frame["linha"] = frame["source_dimension_value"].fillna("").astype(str).str.strip().replace("", "n/d")
    frame["coluna"] = frame["target_dimension_value"].fillna("").astype(str).str.strip().replace("", "n/d")
    frame["valor"] = pd.to_numeric(frame[metric_col], errors="coerce").fillna(0.0) / divisor
    numeric_cols = [
        "catalog_links",
        "source_document_links",
        "curated_links",
        "weighted_links",
        "avg_confidence_score",
    ]
    for col in numeric_cols:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
        else:
            frame[col] = 0.0
    return (
        frame.groupby(["linha", "coluna"], dropna=False)
        .agg(
            valor=("valor", "sum"),
            competencia=("competencia", "first"),
            source_dimension_label=("source_dimension_label", "first"),
            target_dimension_label=("target_dimension_label", "first"),
            catalog_links=("catalog_links", "sum"),
            source_document_links=("source_document_links", "sum"),
            curated_links=("curated_links", "sum"),
            weighted_links=("weighted_links", "sum"),
            avg_confidence_score=("avg_confidence_score", "mean"),
        )
        .reset_index()
    )


def _dimension_profile_coverage_frame(profiles: pd.DataFrame) -> pd.DataFrame:
    required = {
        "source_dimension_id",
        "source_dimension_label",
        "source_dimension_value",
        "target_dimension_id",
        "target_dimension_value",
    }
    if profiles.empty or not required.issubset(profiles.columns):
        return pd.DataFrame()
    frame = profiles.copy()
    numeric_cols = [
        "catalog_links",
        "source_document_links",
        "curated_links",
        "weighted_links",
        "avg_confidence_score",
    ]
    for col in numeric_cols:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
        else:
            frame[col] = 0.0
    coverage = (
        frame.groupby(["source_dimension_label", "source_dimension_id"], dropna=False)
        .agg(
            source_values=("source_dimension_value", "nunique"),
            target_dimensions=("target_dimension_id", "nunique"),
            target_values=("target_dimension_value", "nunique"),
            profile_rows=("target_dimension_value", "size"),
            profile_links=("catalog_links", "sum"),
            source_document_links=("source_document_links", "sum"),
            curated_links=("curated_links", "sum"),
            weighted_links=("weighted_links", "sum"),
            avg_confidence_score=("avg_confidence_score", "mean"),
        )
        .reset_index()
    )
    links = pd.to_numeric(coverage["profile_links"], errors="coerce").fillna(0.0).replace(0, pd.NA)
    coverage["source_document_ratio"] = pd.to_numeric(coverage["source_document_links"], errors="coerce").fillna(0.0) / links
    coverage["curated_ratio"] = pd.to_numeric(coverage["curated_links"], errors="coerce").fillna(0.0) / links
    coverage["weighted_ratio"] = pd.to_numeric(coverage["weighted_links"], errors="coerce").fillna(0.0) / links
    return coverage.sort_values(["profile_links", "profile_rows"], ascending=[False, False]).reset_index(drop=True)


def _format_dimension_profile_coverage(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.rename(
        columns={
            "source_dimension_label": "Dimensão origem",
            "source_dimension_id": "ID",
            "source_values": "Valores origem",
            "target_dimensions": "Dimensões alvo",
            "target_values": "Valores alvo",
            "profile_rows": "Células",
            "profile_links": "Links",
            "source_document_links": "Links com fonte",
            "curated_links": "Links curados",
            "weighted_links": "Links ponderados",
            "source_document_ratio": "% com fonte",
            "curated_ratio": "% curado",
            "weighted_ratio": "% ponderado",
            "avg_confidence_score": "Score médio",
        }
    )
    count_cols = [
        "Valores origem",
        "Dimensões alvo",
        "Valores alvo",
        "Células",
        "Links",
        "Links com fonte",
        "Links curados",
        "Links ponderados",
    ]
    for col in count_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
    for col in ["% com fonte", "% curado", "% ponderado"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").map(
                lambda value: "n/d" if pd.isna(value) else _fmt_pct(float(value))
            )
    if "Score médio" in out.columns:
        out["Score médio"] = pd.to_numeric(out["Score médio"], errors="coerce").map(
            lambda value: "n/d" if pd.isna(value) else f"{float(value):.2f}".replace(".", ",")
        )
    return out


def _format_heatmap_registry(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    cols = [
        "preset_label",
        "status",
        "row_dimension_label",
        "col_dimension_label",
        "profile_rows",
        "profile_links",
        "source_document_links",
        "curated_links",
        "weighted_links",
        "avg_confidence_score",
        "missing_dimensions",
        "metrics_supported",
        "source_mode",
        "rerun_command",
    ]
    out = frame[[col for col in cols if col in frame.columns]].copy()
    out = out.rename(
        columns={
            "preset_label": "Preset",
            "status": "Status",
            "row_dimension_label": "Linha",
            "col_dimension_label": "Coluna",
            "profile_rows": "Células",
            "profile_links": "Links",
            "source_document_links": "Links com fonte",
            "curated_links": "Links curados",
            "weighted_links": "Links ponderados",
            "avg_confidence_score": "Score médio",
            "missing_dimensions": "Dimensões faltantes",
            "metrics_supported": "Métricas",
            "source_mode": "Fonte cálculo",
            "rerun_command": "Comando",
        }
    )
    for col in ["Células", "Links", "Links com fonte", "Links curados", "Links ponderados"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
    if "Score médio" in out.columns:
        out["Score médio"] = pd.to_numeric(out["Score médio"], errors="coerce").map(
            lambda value: "" if pd.isna(value) else f"{float(value):.2f}".replace(".", ",")
        )
    return out


def _format_prd_coverage(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    cols = [
        "tema",
        "requisito",
        "status_prd",
        "evidencia",
        "metrica",
        "artefato",
        "proximo_passo",
        "comando",
    ]
    out = frame[[col for col in cols if col in frame.columns]].copy()
    out = out.rename(
        columns={
            "tema": "Tema",
            "requisito": "Requisito PRD",
            "status_prd": "Status",
            "evidencia": "Evidência materializada",
            "metrica": "Métrica",
            "artefato": "Artefato",
            "proximo_passo": "Próximo passo",
            "comando": "Comando",
        }
    )
    if "Status" in out.columns:
        out["Status"] = out["Status"].map(_status_badge_text)
    return out


def _truthy_series(values: pd.Series) -> pd.Series:
    return values.astype("string").fillna("").str.lower().isin({"true", "1", "sim", "s", "yes"})


def _nonempty_series(values: pd.Series) -> pd.Series:
    return values.fillna("").astype(str).str.strip().ne("")


def _numeric_median_or_na(values: pd.Series) -> object:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return pd.NA
    return float(numeric.median())


def _dimension_catalog_quality_frame(catalog: pd.DataFrame) -> pd.DataFrame:
    required = {"dimension_id", "dimension_label", "dimension_value", "cnpj_fundo"}
    if catalog.empty or not required.issubset(catalog.columns):
        return pd.DataFrame()
    frame = catalog.copy()
    for col in [
        "source_layer",
        "source_document",
        "source_page",
        "source_date",
        "source_method",
        "confidence_score",
        "review_status",
        "participant_cnpj",
        "is_curated",
        "is_multivalue",
    ]:
        if col not in frame.columns:
            frame[col] = ""
    frame["_cnpj_norm"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame["_has_source_layer"] = _nonempty_series(frame["source_layer"])
    frame["_has_source_document"] = _nonempty_series(frame["source_document"])
    frame["_has_source_page"] = _nonempty_series(frame["source_page"])
    frame["_has_source_date"] = _nonempty_series(frame["source_date"])
    frame["_has_source_method"] = _nonempty_series(frame["source_method"])
    frame["_has_confidence"] = pd.to_numeric(frame["confidence_score"], errors="coerce").notna()
    frame["_has_review_status"] = _nonempty_series(frame["review_status"])
    frame["_has_participant_cnpj"] = _nonempty_series(frame["participant_cnpj"].map(normalize_cnpj))
    frame["_is_curated"] = _truthy_series(frame["is_curated"])
    frame["_is_multivalue"] = _truthy_series(frame["is_multivalue"])
    source_layer = frame["source_layer"].fillna("").astype(str)
    frame["_doc_expected"] = frame["_is_curated"] | source_layer.isin({"cedente", "criteria"}) | frame["_has_source_document"]
    frame["_review_expected"] = frame["_is_curated"] | source_layer.isin({"cedente", "criteria"})
    confidence = pd.to_numeric(frame["confidence_score"], errors="coerce")
    grouped = (
        frame.groupby(["dimension_label", "dimension_id"], dropna=False)
        .agg(
            rows=("dimension_value", "size"),
            funds=("_cnpj_norm", "nunique"),
            values=("dimension_value", "nunique"),
            curated_rows=("_is_curated", "sum"),
            multivalue_rows=("_is_multivalue", "sum"),
            document_expected_rows=("_doc_expected", "sum"),
            review_expected_rows=("_review_expected", "sum"),
            with_source_layer=("_has_source_layer", "sum"),
            with_source_document=("_has_source_document", "sum"),
            with_source_page=("_has_source_page", "sum"),
            with_source_date=("_has_source_date", "sum"),
            with_source_method=("_has_source_method", "sum"),
            with_confidence=("_has_confidence", "sum"),
            with_review_status=("_has_review_status", "sum"),
            with_participant_cnpj=("_has_participant_cnpj", "sum"),
            confidence_median=("confidence_score", _numeric_median_or_na),
        )
        .reset_index()
    )
    rows = pd.to_numeric(grouped["rows"], errors="coerce").astype(float)
    rows = rows.where(rows.ne(0))
    doc_expected = pd.to_numeric(grouped["document_expected_rows"], errors="coerce").astype(float)
    doc_expected = doc_expected.where(doc_expected.ne(0))
    review_expected = pd.to_numeric(grouped["review_expected_rows"], errors="coerce").astype(float)
    review_expected = review_expected.where(review_expected.ne(0))
    grouped["source_layer_ratio"] = grouped["with_source_layer"] / rows
    grouped["source_method_ratio"] = grouped["with_source_method"] / rows
    grouped["confidence_ratio"] = grouped["with_confidence"] / rows
    grouped["source_document_ratio"] = grouped["with_source_document"] / doc_expected
    grouped["source_page_ratio"] = grouped["with_source_page"] / doc_expected
    grouped["review_status_ratio"] = grouped["with_review_status"] / review_expected
    grouped["quality_score"] = (
        grouped["source_layer_ratio"].fillna(0.0) * 0.15
        + grouped["source_method_ratio"].fillna(0.0) * 0.20
        + grouped["confidence_ratio"].fillna(0.0) * 0.20
        + grouped["source_document_ratio"].fillna(1.0) * 0.20
        + grouped["source_page_ratio"].fillna(1.0) * 0.15
        + grouped["review_status_ratio"].fillna(1.0) * 0.10
    )
    return grouped.sort_values(["quality_score", "rows"], ascending=[True, False]).reset_index(drop=True)


def _dimension_catalog_gap_frame(catalog: pd.DataFrame) -> pd.DataFrame:
    if catalog.empty or "dimension_id" not in catalog.columns:
        return pd.DataFrame()
    frame = catalog.copy()
    for col in [
        "cnpj_fundo",
        "nome_exibicao",
        "dimension_label",
        "dimension_value",
        "source_layer",
        "source_document",
        "source_page",
        "source_date",
        "source_method",
        "confidence_score",
        "review_status",
        "participant_type",
        "participant_cnpj",
        "is_curated",
        "priority_2025_2026",
    ]:
        if col not in frame.columns:
            frame[col] = ""
    source_layer = frame["source_layer"].fillna("").astype(str)
    is_curated = _truthy_series(frame["is_curated"])
    doc_expected = is_curated | source_layer.isin({"cedente", "criteria"}) | _nonempty_series(frame["source_document"])
    review_expected = is_curated | source_layer.isin({"cedente", "criteria"})
    has_source_layer = _nonempty_series(frame["source_layer"])
    has_source_document = _nonempty_series(frame["source_document"])
    has_source_page = _nonempty_series(frame["source_page"])
    has_source_method = _nonempty_series(frame["source_method"])
    has_confidence = pd.to_numeric(frame["confidence_score"], errors="coerce").notna()
    has_review_status = _nonempty_series(frame["review_status"])
    missing: list[str] = []
    scores: list[int] = []
    for idx in frame.index:
        fields: list[str] = []
        if not bool(has_source_layer.loc[idx]):
            fields.append("fonte")
        if not bool(has_source_method.loc[idx]):
            fields.append("método")
        if not bool(has_confidence.loc[idx]):
            fields.append("score")
        if bool(doc_expected.loc[idx]) and not bool(has_source_document.loc[idx]):
            fields.append("documento")
        if bool(doc_expected.loc[idx]) and not bool(has_source_page.loc[idx]):
            fields.append("página")
        if bool(review_expected.loc[idx]) and not bool(has_review_status.loc[idx]):
            fields.append("status revisão")
        missing.append(" | ".join(fields))
        scores.append(len(fields) + int(bool(is_curated.loc[idx])) + int(bool(doc_expected.loc[idx])))
    frame["missing_traceability_fields"] = missing
    frame["traceability_gap_score"] = scores
    out = frame[frame["missing_traceability_fields"].astype(str).str.strip().ne("")].copy()
    if out.empty:
        return out
    out["cnpj_fundo_norm"] = out["cnpj_fundo"].map(normalize_cnpj)
    value_hash = out["dimension_value"].fillna("").astype(str).map(
        lambda value: hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    )
    out["traceability_gap_id"] = (
        "catalog_"
        + out["dimension_id"].fillna("").astype(str).str.replace(r"[^A-Za-z0-9_]+", "_", regex=True)
        + "_"
        + out["cnpj_fundo_norm"].fillna("").astype(str)
        + "_"
        + value_hash
    )
    out["priority_2025_2026"] = _truthy_series(out["priority_2025_2026"])
    out["confidence_score"] = pd.to_numeric(out["confidence_score"], errors="coerce")
    return out.sort_values(
        ["priority_2025_2026", "traceability_gap_score", "dimension_label", "dimension_value"],
        ascending=[False, False, True, True],
    ).reset_index(drop=True)


def _format_dimension_catalog_quality(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.rename(
        columns={
            "dimension_label": "Dimensão",
            "dimension_id": "ID",
            "rows": "Linhas",
            "funds": "FIDCs",
            "values": "Valores",
            "curated_rows": "Curadas",
            "document_expected_rows": "Doc esperado",
            "source_method_ratio": "% método",
            "confidence_ratio": "% score",
            "source_document_ratio": "% documento",
            "source_page_ratio": "% página",
            "review_status_ratio": "% revisão",
            "confidence_median": "Score mediano",
            "quality_score": "Score qualidade",
        }
    )
    keep = [
        "Dimensão",
        "ID",
        "Linhas",
        "FIDCs",
        "Valores",
        "Curadas",
        "Doc esperado",
        "% método",
        "% score",
        "% documento",
        "% página",
        "% revisão",
        "Score mediano",
        "Score qualidade",
    ]
    out = out[[col for col in keep if col in out.columns]].copy()
    for col in ["Linhas", "FIDCs", "Valores", "Curadas", "Doc esperado"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
    for col in ["% método", "% score", "% documento", "% página", "% revisão", "Score qualidade"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").map(
                lambda value: "n/d" if pd.isna(value) else _fmt_pct(float(value))
            )
    if "Score mediano" in out.columns:
        out["Score mediano"] = pd.to_numeric(out["Score mediano"], errors="coerce").map(
            lambda value: "n/d" if pd.isna(value) else f"{float(value):.2f}".replace(".", ",")
        )
    return out


def _format_dimension_catalog_gaps(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    cols = [
        "traceability_gap_id",
        "dimension_label",
        "dimension_value",
        "cnpj_fundo",
        "nome_exibicao",
        "missing_traceability_fields",
        "traceability_gap_score",
        "status_lacuna",
        "acao_revisada",
        "responsavel",
        "prazo",
        "notas",
        "updated_at_utc",
        "source_layer",
        "source_document",
        "source_page",
        "source_method",
        "confidence_score",
        "review_status",
        "participant_type",
        "participant_cnpj",
        "priority_2025_2026",
    ]
    out = frame[[col for col in cols if col in frame.columns]].copy()
    out = out.rename(
        columns={
            "traceability_gap_id": "ID",
            "dimension_label": "Dimensão",
            "dimension_value": "Valor",
            "cnpj_fundo": "CNPJ",
            "nome_exibicao": "FIDC",
            "missing_traceability_fields": "Campos faltantes",
            "traceability_gap_score": "Score lacuna",
            "status_lacuna": "Status lacuna",
            "acao_revisada": "Ação revisada",
            "responsavel": "Responsável",
            "prazo": "Prazo",
            "notas": "Notas",
            "updated_at_utc": "Atualizado",
            "source_layer": "Fonte",
            "source_document": "Documento",
            "source_page": "Página",
            "source_method": "Método",
            "confidence_score": "Score",
            "review_status": "Revisão",
            "participant_type": "Tipo participante",
            "participant_cnpj": "CNPJ participante",
            "priority_2025_2026": "Prioridade 25-26",
        }
    )
    if "Score lacuna" in out.columns:
        out["Score lacuna"] = pd.to_numeric(out["Score lacuna"], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
    if "Score" in out.columns:
        out["Score"] = pd.to_numeric(out["Score"], errors="coerce").map(
            lambda value: "n/d" if pd.isna(value) else f"{float(value):.2f}".replace(".", ",")
        )
    if "Prioridade 25-26" in out.columns:
        out["Prioridade 25-26"] = out["Prioridade 25-26"].astype(bool).map({True: "sim", False: "não"})
    return out


def _norm_status_label(series: pd.Series, default: str = "") -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .replace("", default)
    )


def _boolish(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(str).str.strip().str.lower().isin({"true", "1", "sim", "yes", "y"})


def _competencia_key(value: object) -> str:
    text = str(value or "").strip()
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 6:
        return digits[:6]
    return digits


def _sample_join(frame: pd.DataFrame, cols: list[str], limit: int = 4) -> str:
    if frame is None or frame.empty:
        return ""
    pieces: list[str] = []
    for _, row in frame.head(limit).iterrows():
        values = [str(row.get(col, "") or "").strip() for col in cols]
        values = [value for value in values if value]
        if values:
            pieces.append(" · ".join(values))
    return " | ".join(pieces)


def _monthly_readiness_frame(
    *,
    index: dict[str, object],
    monthly_delta: pd.DataFrame,
    snapshot: pd.DataFrame,
    dimension_catalog: pd.DataFrame,
    snapshot_gap_actions: pd.DataFrame | None = None,
    catalog_gap_actions: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Operational checklist for releasing the next Industry monthly update."""

    rollup = index.get("quality_rollup", {}) if isinstance(index.get("quality_rollup"), dict) else {}
    modules = index.get("modules", []) if isinstance(index.get("modules"), list) else []
    artifacts = index.get("artifact_index", []) if isinstance(index.get("artifact_index"), list) else []
    rows: list[dict[str, object]] = []

    def add_row(
        check_id: str,
        ordem: int,
        frente: str,
        escopo: str,
        status: str,
        pendencias: int,
        amostra: str,
        acao: str,
        fonte: str,
        comando: str = "",
    ) -> None:
        rows.append(
            {
                "check_id": check_id,
                "ordem": ordem,
                "frente": frente,
                "escopo": escopo,
                "status_prontidao": status,
                "pendencias": int(pendencias),
                "amostra": amostra,
                "acao_sugerida": acao,
                "fonte": fonte,
                "comando": comando,
            }
        )

    snapshot_comp = str(rollup.get("competencia_snapshot") or rollup.get("competencia_final") or "").strip()
    dimension_monthly_comp = str(rollup.get("dimension_monthly_latest_competencia") or "").strip()
    delta_comp = ""
    if monthly_delta is not None and not monthly_delta.empty and "competencia_atual" in monthly_delta.columns:
        delta_comp = str(monthly_delta["competencia_atual"].fillna("").astype(str).max()).strip()
    stale_items: list[str] = []
    snapshot_key = _competencia_key(snapshot_comp)
    dimension_monthly_key = _competencia_key(dimension_monthly_comp)
    delta_key = _competencia_key(delta_comp)
    if snapshot_key and dimension_monthly_key and snapshot_key != dimension_monthly_key:
        stale_items.append("séries por dimensão")
    if snapshot_key and delta_key and snapshot_key != delta_key:
        stale_items.append("delta mensal")
    status = "bloqueado" if stale_items else "ok"
    add_row(
        "competencia_alignment",
        1,
        "Competência",
        "Sincronia dos artefatos mensais",
        status,
        len(stale_items),
        f"snapshot {snapshot_comp or 'n/d'}; dimensão {dimension_monthly_comp or 'n/d'}; delta {delta_comp or 'n/d'}",
        "Reexecutar módulos derivados depois de atualizar a base granular.",
        "industry_pipeline_index.json",
        "python scripts/build_fidc_industry_dimension_monthly.py && python scripts/build_fidc_industry_monthly_delta.py",
    )

    module_frame = pd.DataFrame([item for item in modules if isinstance(item, dict)])
    if module_frame.empty:
        bad_modules = module_frame
    else:
        module_status = _norm_status_label(module_frame.get("status", pd.Series("", index=module_frame.index)), "missing")
        bad_modules = module_frame[~module_status.eq("ok")].copy()
    add_row(
        "module_status",
        2,
        "Pipeline",
        "Módulos com manifesto válido",
        "bloqueado" if not bad_modules.empty else "ok",
        len(bad_modules),
        _sample_join(bad_modules.rename(columns={"label": "module_label"}), ["module_label", "status"]),
        "Rodar os comandos dos módulos pendentes antes de fechar a competência.",
        "industry_pipeline_index.json",
        " && ".join([str(value) for value in bad_modules.get("command", pd.Series(dtype=str)).head(3) if str(value).strip()]),
    )

    artifact_frame = pd.DataFrame([item for item in artifacts if isinstance(item, dict)])
    if artifact_frame.empty:
        missing_required = artifact_frame
        missing_optional = artifact_frame
    else:
        exists = artifact_frame.get("exists", pd.Series(False, index=artifact_frame.index)).eq(True)
        required = artifact_frame.get("required", pd.Series(False, index=artifact_frame.index)).eq(True)
        missing_required = artifact_frame[required & ~exists].copy()
        missing_optional = artifact_frame[~required & ~exists].copy()
    artifact_status = "bloqueado" if not missing_required.empty else ("atenção" if not missing_optional.empty else "ok")
    add_row(
        "artifact_presence",
        3,
        "Artefatos",
        "Arquivos obrigatórios e opcionais",
        artifact_status,
        len(missing_required) if not missing_required.empty else len(missing_optional),
        _sample_join(pd.concat([missing_required, missing_optional], ignore_index=True), ["module_id", "artifact"]),
        "Gerar os arquivos ausentes; opcionais indicam histórico de revisão ainda não iniciado.",
        "artifact_index",
        "",
    )

    delta = pd.DataFrame() if monthly_delta is None else monthly_delta.copy()
    if not delta.empty:
        status_delta = _norm_status_label(delta.get("status_acao", pd.Series("", index=delta.index)), "pendente")
        open_delta = delta[~status_delta.isin({"concluído", "concluido", "ignorado"})].copy()
        priority_text = _norm_status_label(open_delta.get("priority_band", pd.Series("", index=open_delta.index)))
        priority_score = pd.to_numeric(open_delta.get("priority_score", pd.Series(0, index=open_delta.index)), errors="coerce").fillna(0)
        high_priority = open_delta[priority_text.str.contains("alta|high", regex=True) | priority_score.ge(80)].copy()
    else:
        open_delta = delta
        high_priority = delta
    delta_status = "bloqueado" if not high_priority.empty else ("atenção" if not open_delta.empty else "ok")
    add_row(
        "monthly_delta_queue",
        4,
        "Delta mensal",
        "Novos, reativados, saídas e grandes variações",
        delta_status,
        len(high_priority) if not high_priority.empty else len(open_delta),
        _sample_join(high_priority if not high_priority.empty else open_delta, ["fundo", "cnpj_fundo", "next_actions"]),
        "Fechar ou justificar as ações de delta de maior prioridade.",
        "industry_monthly_delta.csv.gz",
        "python scripts/build_fidc_industry_monthly_delta.py",
    )

    snapshot_gaps = _apply_snapshot_gap_actions(_snapshot_gap_frame(snapshot), snapshot_gap_actions)
    if not snapshot_gaps.empty:
        status_gap = _norm_status_label(snapshot_gaps.get("status_lacuna", pd.Series("", index=snapshot_gaps.index)), "pendente")
        open_snapshot = snapshot_gaps[~status_gap.isin({"corrigido", "aceito", "ignorado"})].copy()
        priority_snapshot = open_snapshot[_boolish(open_snapshot.get("priority_2025_2026", pd.Series(False, index=open_snapshot.index)))].copy()
    else:
        open_snapshot = snapshot_gaps
        priority_snapshot = snapshot_gaps
    snapshot_status = "bloqueado" if not priority_snapshot.empty else ("atenção" if not open_snapshot.empty else "ok")
    add_row(
        "snapshot_structural_gaps",
        5,
        "Snapshot",
        "Documentos, cedentes, critérios e sub mínima por FIDC",
        snapshot_status,
        len(priority_snapshot) if not priority_snapshot.empty else len(open_snapshot),
        _sample_join(priority_snapshot if not priority_snapshot.empty else open_snapshot, ["nome_exibicao", "cnpj_fundo", "missing_layers"]),
        "Usar a fila de lacunas do snapshot para completar camadas estruturadas dos FIDCs materiais.",
        "industry_fund_snapshot.csv.gz",
        "python scripts/build_fidc_industry_fund_snapshot.py",
    )

    catalog_gaps = _apply_catalog_gap_actions(_dimension_catalog_gap_frame(dimension_catalog), catalog_gap_actions)
    if not catalog_gaps.empty:
        status_catalog = _norm_status_label(catalog_gaps.get("status_lacuna", pd.Series("", index=catalog_gaps.index)), "pendente")
        open_catalog = catalog_gaps[~status_catalog.isin({"corrigido", "aceito", "ignorado"})].copy()
        priority_catalog = open_catalog[
            _boolish(open_catalog.get("priority_2025_2026", pd.Series(False, index=open_catalog.index)))
            | open_catalog.get("dimension_id", pd.Series("", index=open_catalog.index)).isin(
                {"cedente_sacado", "setor_cedente", "segmento_cedente", "criterio", "faixa_sub_minima", "tem_sub_minima"}
            )
        ].copy()
    else:
        open_catalog = catalog_gaps
        priority_catalog = catalog_gaps
    catalog_status = "bloqueado" if not priority_catalog.empty else ("atenção" if not open_catalog.empty else "ok")
    add_row(
        "catalog_traceability_gaps",
        6,
        "Catálogo",
        "Fonte, documento, página, método, score e revisão",
        catalog_status,
        len(priority_catalog) if not priority_catalog.empty else len(open_catalog),
        _sample_join(priority_catalog if not priority_catalog.empty else open_catalog, ["dimension_label", "dimension_value", "missing_traceability_fields"]),
        "Resolver rastreabilidade dos valores usados em heatmaps e deep dives.",
        "industry_dimension_catalog.csv.gz",
        "python scripts/build_fidc_industry_dimensions.py",
    )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    status_order = {"bloqueado": 0, "atenção": 1, "ok": 2}
    out["_status_order"] = out["status_prontidao"].map(status_order).fillna(9)
    return out.sort_values(["_status_order", "ordem"]).drop(columns=["_status_order"]).reset_index(drop=True)


def _format_monthly_readiness(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.rename(
        columns={
            "check_id": "ID",
            "frente": "Frente",
            "escopo": "Escopo",
            "status_prontidao": "Status",
            "pendencias": "Pendências",
            "amostra": "Amostra",
            "acao_sugerida": "Ação sugerida",
            "fonte": "Fonte",
            "comando": "Comando",
        }
    )
    keep = ["Status", "Frente", "Escopo", "Pendências", "Amostra", "Ação sugerida", "Fonte", "Comando", "ID"]
    out = out[[col for col in keep if col in out.columns]].copy()
    if "Pendências" in out.columns:
        out["Pendências"] = pd.to_numeric(out["Pendências"], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
    return out


def _format_monthly_update_plan(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.rename(
        columns={
            "order": "Ordem",
            "fase": "Fase",
            "etapa": "Etapa",
            "competencia_referencia": "Competência",
            "status_modulo": "Status módulo",
            "status_prontidao": "Prontidão",
            "bloqueios_ou_atencoes": "Bloqueios/atenções",
            "acao_antes_de_rodar": "Antes de rodar",
            "comando": "Comando",
            "validacao": "Validação",
            "entradas": "Entradas",
            "saidas": "Saídas",
            "evidencia_atual": "Evidência atual",
            "artefatos": "Artefatos",
            "gerado_em_utc": "Gerado em",
            "motivo": "Motivo",
            "incrementalidade": "Incrementalidade",
            "module_id": "Módulo ID",
            "plan_id": "ID",
        }
    )
    keep = [
        "Ordem",
        "Fase",
        "Etapa",
        "Prontidão",
        "Status módulo",
        "Bloqueios/atenções",
        "Antes de rodar",
        "Comando",
        "Validação",
        "Entradas",
        "Saídas",
        "Evidência atual",
        "Artefatos",
        "Gerado em",
        "Motivo",
        "Incrementalidade",
        "Módulo ID",
        "ID",
    ]
    out = out[[col for col in keep if col in out.columns]].copy()
    if "Ordem" in out.columns:
        out["Ordem"] = pd.to_numeric(out["Ordem"], errors="coerce").fillna(0).astype(int)
    for col in ["Prontidão", "Status módulo"]:
        if col in out.columns:
            out[col] = out[col].map(_status_badge_text)
    if "Gerado em" in out.columns:
        out["Gerado em"] = out["Gerado em"].fillna("").astype(str).str.slice(0, 19)
    return out


def _format_manual_review_ledger(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.rename(
        columns={
            "label": "Domínio",
            "status_ledger": "Status",
            "ui_surface": "Tela",
            "comparison": "Comparação",
            "action_file": "Arquivo ações",
            "audit_file": "Arquivo auditoria",
            "action_exists": "Ações existem",
            "audit_exists": "Auditoria existe",
            "action_rows": "Ações",
            "action_records": "Registros",
            "open_rows": "Abertas",
            "closed_rows": "Fechadas",
            "status_mix": "Mix status",
            "audit_events": "Eventos auditoria",
            "audited_records": "Registros auditados",
            "audit_domains": "Domínios auditoria",
            "latest_action_utc": "Última ação",
            "latest_audit_utc": "Última auditoria",
            "source_artifacts": "Artefatos",
            "rerun_command": "Comando",
            "domain_id": "ID",
        }
    )
    keep = [
        "Status",
        "Domínio",
        "Tela",
        "Comparação",
        "Ações",
        "Registros",
        "Abertas",
        "Fechadas",
        "Eventos auditoria",
        "Registros auditados",
        "Ações existem",
        "Auditoria existe",
        "Mix status",
        "Última ação",
        "Última auditoria",
        "Arquivo ações",
        "Arquivo auditoria",
        "Comando",
        "ID",
    ]
    out = out[[col for col in keep if col in out.columns]].copy()
    if "Status" in out.columns:
        out["Status"] = out["Status"].map(_status_badge_text)
    for col in ["Ações", "Registros", "Abertas", "Fechadas", "Eventos auditoria", "Registros auditados"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
    for col in ["Ações existem", "Auditoria existe"]:
        if col in out.columns:
            out[col] = out[col].map(lambda value: "sim" if bool(value) else "não")
    for col in ["Última ação", "Última auditoria"]:
        if col in out.columns:
            out[col] = out[col].fillna("").astype(str).str.slice(0, 19)
    return out


def _format_public_claim_audit(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.rename(
        columns={
            "source_name": "Fonte",
            "published_at": "Data",
            "metric_group": "Métrica",
            "claim_text": "Claim público",
            "period_start": "Início",
            "period_end": "Fim",
            "unit": "Unidade",
            "public_value": "Valor público",
            "local_value": "Valor aba",
            "delta_value": "Diferença",
            "delta_pct": "Dif. %",
            "status_auditoria": "Status",
            "comparability": "Comparabilidade",
            "local_source_artifact": "Artefato local",
            "local_evidence": "Evidência local",
            "method_note": "Nota metodológica",
            "source_url": "URL",
            "rerun_command": "Comando",
            "claim_id": "ID",
        }
    )
    keep = [
        "Status",
        "Fonte",
        "Data",
        "Métrica",
        "Claim público",
        "Início",
        "Fim",
        "Valor público",
        "Valor aba",
        "Diferença",
        "Dif. %",
        "Comparabilidade",
        "Artefato local",
        "Evidência local",
        "Nota metodológica",
        "URL",
        "Comando",
        "ID",
    ]
    out = out[[col for col in keep if col in out.columns]].copy()
    unit = frame.get("unit", pd.Series("", index=frame.index)).fillna("").astype(str).reset_index(drop=True)
    for col in ["Valor público", "Valor aba", "Diferença"]:
        if col in out.columns:
            values = pd.to_numeric(out[col], errors="coerce")
            formatted: list[str] = []
            for idx, value in enumerate(values):
                if pd.isna(value):
                    formatted.append("")
                elif idx < len(unit) and unit.iloc[idx] == "BRL":
                    formatted.append(_fmt_bi(float(value), 2))
                else:
                    formatted.append(_fmt_int(float(value)))
            out[col] = formatted
    if "Dif. %" in out.columns:
        out["Dif. %"] = pd.to_numeric(out["Dif. %"], errors="coerce").map(
            lambda value: "" if pd.isna(value) else _fmt_pct(float(value))
        )
    if "Status" in out.columns:
        out["Status"] = out["Status"].map(_status_badge_text)
    return out


def _catalog_deep_dive_frame(vehicle: pd.DataFrame, catalog: pd.DataFrame, dimension_id: str) -> pd.DataFrame:
    base = _base_with_catalog_id(vehicle)
    dim = _dimension_catalog_rows(catalog, dimension_id)
    if base.empty or dim.empty:
        return base.iloc[0:0].copy()
    keep = [
        "cnpj_fundo_norm",
        "dimension_value",
        "value_weight",
        "source_layer",
        "source_document",
        "source_page",
        "source_method",
        "confidence_score",
        "review_status",
        "participant_type",
        "participant_cnpj",
        "is_curated",
        "is_multivalue",
    ]
    dim = dim[[col for col in keep if col in dim.columns]].rename(
        columns={
            "dimension_value": "valor_dimensao",
            "value_weight": "_metric_weight",
            "source_layer": "dimension_source_layer",
            "source_document": "dimension_source_document",
            "source_page": "dimension_source_page",
            "source_method": "dimension_source_method",
            "confidence_score": "dimension_confidence_score",
            "review_status": "dimension_review_status",
            "participant_type": "dimension_participant_type",
            "participant_cnpj": "dimension_participant_cnpj",
        }
    )
    frame = base.merge(dim, on="cnpj_fundo_norm", how="inner")
    frame["_metric_weight"] = pd.to_numeric(frame.get("_metric_weight"), errors="coerce").fillna(1.0)
    return frame


def _dimension_monthly_for_value(
    monthly: pd.DataFrame,
    *,
    dimension_id: str,
    selected_value: str,
    comp: str,
    period: str,
) -> pd.DataFrame:
    if monthly.empty:
        return pd.DataFrame()
    required = {"competencia", "dimension_id", "dimension_value"}
    if not required.issubset(monthly.columns):
        return pd.DataFrame()
    frame = monthly[
        monthly["dimension_id"].astype(str).eq(str(dimension_id))
        & monthly["dimension_value"].astype(str).eq(str(selected_value))
    ].copy()
    if frame.empty:
        return frame
    frame = _period_filter(frame, comp, period)
    if frame.empty:
        return frame
    numeric_cols = [
        "pl_brl",
        "captacao_liquida_brl",
        "carteira_dc_brl",
        "dc_inadimplentes_ajustado_brl",
        "inad_pct_ajustada",
        "funds_unique",
        "vehicles_unique",
        "funds_equiv",
        "cotistas_equiv",
    ]
    for col in numeric_cols:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
        else:
            frame[col] = 0.0
    frame = (
        frame.groupby("competencia", dropna=False)
        .agg(
            pl=("pl_brl", "sum"),
            captacao=("captacao_liquida_brl", "sum"),
            carteira=("carteira_dc_brl", "sum"),
            inad=("dc_inadimplentes_ajustado_brl", "sum"),
            fundos=("funds_unique", "max"),
            veiculos=("vehicles_unique", "max"),
            funds_equiv=("funds_equiv", "sum"),
            cotistas=("cotistas_equiv", "sum"),
        )
        .reset_index()
        .sort_values("competencia")
    )
    frame["inad_pct_ajustada"] = frame["inad"] / frame["carteira"].replace(0, pd.NA)
    frame["inad_pct_ajustada"] = frame["inad_pct_ajustada"].fillna(0.0)
    frame["mes"] = pd.to_datetime(frame["competencia"] + "-01")
    frame["pl_bi"] = frame["pl"] / 1e9
    frame["captacao_bi"] = frame["captacao"] / 1e9
    return frame


def _dimension_radar_frame(monthly: pd.DataFrame, *, dimension_id: str, comp: str, period: str) -> pd.DataFrame:
    required = {"competencia", "dimension_id", "dimension_value"}
    if monthly.empty or not required.issubset(monthly.columns):
        return pd.DataFrame()
    frame = monthly[monthly["dimension_id"].astype(str).eq(str(dimension_id))].copy()
    if frame.empty:
        return frame
    numeric_cols = [
        "pl_brl",
        "captacao_liquida_brl",
        "carteira_dc_brl",
        "dc_inadimplentes_ajustado_brl",
        "funds_unique",
        "vehicles_unique",
        "catalog_links",
        "source_document_links",
        "curated_links",
        "weighted_links",
    ]
    for col in numeric_cols:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
        else:
            frame[col] = 0.0
    all_comps = sorted([value for value in frame["competencia"].dropna().astype(str).unique() if value <= comp])
    previous_comp = all_comps[-13] if len(all_comps) >= 13 else ""
    period_frame = _period_filter(frame, comp, period)
    if period_frame.empty:
        return period_frame
    grouped = (
        period_frame.groupby(["competencia", "dimension_value"], dropna=False)
        .agg(
            pl_brl=("pl_brl", "sum"),
            captacao_liquida_brl=("captacao_liquida_brl", "sum"),
            carteira_dc_brl=("carteira_dc_brl", "sum"),
            dc_inadimplentes_ajustado_brl=("dc_inadimplentes_ajustado_brl", "sum"),
            funds_unique=("funds_unique", "max"),
            vehicles_unique=("vehicles_unique", "max"),
            catalog_links=("catalog_links", "sum"),
            source_document_links=("source_document_links", "sum"),
            curated_links=("curated_links", "sum"),
            weighted_links=("weighted_links", "sum"),
        )
        .reset_index()
    )
    if grouped.empty:
        return grouped
    comps = sorted(grouped["competencia"].dropna().astype(str).unique())
    latest_comp = comps[-1]
    current = grouped[grouped["competencia"].astype(str).eq(latest_comp)].copy()
    current = current.rename(
        columns={
            "pl_brl": "pl_atual_brl",
            "carteira_dc_brl": "carteira_atual_brl",
            "dc_inadimplentes_ajustado_brl": "inad_atual_brl",
            "funds_unique": "fundos_atuais",
            "vehicles_unique": "veiculos_atuais",
            "catalog_links": "links_catalogo",
            "source_document_links": "links_com_fonte",
            "curated_links": "links_curados",
            "weighted_links": "links_ponderados",
        }
    )
    flow = (
        grouped.groupby("dimension_value", dropna=False)["captacao_liquida_brl"]
        .sum()
        .reset_index(name="captacao_janela_brl")
    )
    out = current.merge(flow, on="dimension_value", how="outer")
    if previous_comp:
        previous = (
            frame[frame["competencia"].astype(str).eq(previous_comp)]
            .groupby("dimension_value", dropna=False)["pl_brl"]
            .sum()
            .reset_index(name="pl_12m_antes_brl")
        )
        out = out.merge(previous, on="dimension_value", how="left")
    else:
        out["pl_12m_antes_brl"] = pd.NA
    for col in [
        "pl_atual_brl",
        "captacao_janela_brl",
        "pl_12m_antes_brl",
        "carteira_atual_brl",
        "inad_atual_brl",
        "fundos_atuais",
        "veiculos_atuais",
        "links_catalogo",
        "links_com_fonte",
        "links_curados",
        "links_ponderados",
    ]:
        out[col] = pd.to_numeric(out.get(col), errors="coerce").fillna(0.0)
    out["competencia_atual"] = latest_comp
    out["competencia_12m_antes"] = previous_comp
    out["pl_delta_12m_brl"] = out["pl_atual_brl"] - out["pl_12m_antes_brl"]
    denom = out["pl_12m_antes_brl"].where(out["pl_12m_antes_brl"].ne(0))
    out["pl_growth_12m_pct"] = out["pl_delta_12m_brl"] / denom
    carteira = out["carteira_atual_brl"].where(out["carteira_atual_brl"].ne(0))
    links = out["links_catalogo"].where(out["links_catalogo"].ne(0))
    out["inad_pct_atual"] = out["inad_atual_brl"] / carteira
    out["evidence_coverage"] = out["links_com_fonte"] / links
    out["curated_coverage"] = out["links_curados"] / links
    out["rank_score"] = out["pl_atual_brl"].abs() + out["captacao_janela_brl"].abs()
    return (
        out.sort_values(["rank_score", "links_com_fonte", "dimension_value"], ascending=[False, False, True])
        .reset_index(drop=True)
    )


def _format_dimension_radar(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    out = out.rename(
        columns={
            "dimension_value": "Valor",
            "competencia_atual": "Competência",
            "pl_atual_brl": "PL atual",
            "captacao_janela_brl": "Captação janela",
            "pl_delta_12m_brl": "Delta PL 12m",
            "pl_growth_12m_pct": "Cresc. PL 12m",
            "fundos_atuais": "Fundos",
            "veiculos_atuais": "Veículos",
            "inad_pct_atual": "Inad. atual",
            "links_catalogo": "Links catálogo",
            "links_com_fonte": "Links documento",
            "evidence_coverage": "% documento",
            "curated_coverage": "% curado",
        }
    )
    keep = [
        "Valor",
        "Competência",
        "PL atual",
        "Captação janela",
        "Delta PL 12m",
        "Cresc. PL 12m",
        "Fundos",
        "Veículos",
        "Inad. atual",
        "Links catálogo",
        "Links documento",
        "% documento",
        "% curado",
    ]
    out = out[[col for col in keep if col in out.columns]].copy()
    for col in ["PL atual", "Captação janela", "Delta PL 12m"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).map(lambda value: _fmt_bi(float(value), 2))
    for col in ["Cresc. PL 12m", "Inad. atual", "% documento", "% curado"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").map(
                lambda value: "n/d" if pd.isna(value) else _fmt_pct(float(value))
            )
    for col in ["Fundos", "Veículos", "Links catálogo", "Links documento"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
    return out


def _format_dimension_value_atlas(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    out = out.rename(
        columns={
            "dimension_value": "Valor",
            "rank_in_dimension": "# dim.",
            "competencia_atual": "Competência",
            "pl_atual_brl": "PL atual",
            "captacao_12m_brl": "Captação 12m",
            "pl_delta_12m_brl": "Delta PL 12m",
            "pl_growth_12m_pct": "Cresc. PL 12m",
            "fundos_atuais": "Fundos",
            "veiculos_atuais": "Veículos",
            "inad_pct_atual": "Inad. atual",
            "links_catalogo": "Links catálogo",
            "links_com_fonte": "Links documento",
            "links_com_metodo": "Links método",
            "links_com_camada": "Links camada",
            "traceability_coverage": "% rastreável",
            "evidence_coverage": "% documento",
            "source_documents_sample": "Documentos",
            "source_pages_sample": "Páginas",
            "source_methods_sample": "Métodos",
            "review_status_mix": "Status revisão",
            "avg_confidence_score": "Score médio",
            "source_method": "Método",
        }
    )
    keep = [
        "Valor",
        "# dim.",
        "Competência",
        "PL atual",
        "Captação 12m",
        "Delta PL 12m",
        "Cresc. PL 12m",
        "Fundos",
        "Veículos",
        "Inad. atual",
        "Links catálogo",
        "Links documento",
        "Links método",
        "Links camada",
        "% rastreável",
        "% documento",
        "Documentos",
        "Páginas",
        "Métodos",
        "Status revisão",
        "Score médio",
        "Método",
    ]
    out = out[[col for col in keep if col in out.columns]].copy()
    for col in ["PL atual", "Captação 12m", "Delta PL 12m"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).map(lambda value: _fmt_bi(float(value), 2))
    for col in ["Cresc. PL 12m", "Inad. atual", "% rastreável", "% documento"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").map(
                lambda value: "n/d" if pd.isna(value) else _fmt_pct(float(value))
            )
    for col in ["# dim.", "Fundos", "Veículos", "Links catálogo", "Links documento", "Links método", "Links camada"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
    if "Score médio" in out.columns:
            out["Score médio"] = pd.to_numeric(out["Score médio"], errors="coerce").map(
            lambda value: "" if pd.isna(value) else f"{float(value):.2f}".replace(".", ",")
        )
    return out


def _format_dimension_dossiers(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    out = out.rename(
        columns={
            "dimension_label": "Dimensão",
            "dimension_id": "ID",
            "status_dossie": "Status",
            "status_reasons": "Pendências",
            "latest_competencia": "Competência",
            "atlas_values": "Valores",
            "atlas_values_with_pl": "Com PL",
            "top_values_sample": "Top valores",
            "pl_total_atual_brl": "PL atual",
            "pl_top_20_brl": "PL top 20",
            "captacao_12m_top_20_brl": "Captação 12m top 20",
            "traceability_coverage": "% rastreável",
            "source_document_coverage": "% documento",
            "links_com_metodo": "Links método",
            "links_com_camada": "Links camada",
            "curated_coverage": "% curado",
            "weighted_coverage": "% ponderado",
            "profile_rows": "Perfis",
            "profile_target_dimensions": "Dim. alvo",
            "profile_target_values": "Valores alvo",
            "heatmap_presets": "Presets",
            "heatmap_presets_ok": "Presets ok",
            "source_documents_sample": "Documentos",
            "source_pages_sample": "Páginas",
            "source_methods_sample": "Métodos",
            "review_status_mix": "Revisão",
        }
    )
    keep = [
        "Dimensão",
        "ID",
        "Status",
        "Pendências",
        "Competência",
        "Valores",
        "Com PL",
        "PL atual",
        "PL top 20",
        "Captação 12m top 20",
        "% rastreável",
        "% documento",
        "Links método",
        "Links camada",
        "% curado",
        "% ponderado",
        "Perfis",
        "Dim. alvo",
        "Valores alvo",
        "Presets",
        "Presets ok",
        "Top valores",
        "Documentos",
        "Páginas",
        "Métodos",
        "Revisão",
    ]
    out = out[[col for col in keep if col in out.columns]].copy()
    for col in ["PL atual", "PL top 20", "Captação 12m top 20"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).map(lambda value: _fmt_bi(float(value), 2))
    for col in ["% rastreável", "% documento", "% curado", "% ponderado"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").map(
                lambda value: "n/d" if pd.isna(value) else _fmt_pct(float(value))
            )
    for col in ["Valores", "Com PL", "Links método", "Links camada", "Perfis", "Dim. alvo", "Valores alvo", "Presets", "Presets ok"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
    if "Status" in out.columns:
        out["Status"] = out["Status"].map(_status_badge_text)
    return out


def _render_generic_heatmaps(vehicle: pd.DataFrame | None, comp: str) -> None:
    st.markdown('<div class="industry-section">Heatmaps granulares</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Combinações livres sobre a base competência × veículo. '
        "O PL em janelas longas é média mensal; fluxos são somados no período.</div>",
        unsafe_allow_html=True,
    )
    if vehicle is None or vehicle.empty:
        st.info("A base `vehicle_monthly.csv.gz` ainda não está disponível para montar heatmaps.")
        return

    fallback_dimensions = {
        "Administrador": "admin_nome",
        "Gestor": "gestor_nome",
        "Custodiante": "custodiante_nome",
        "Cedente/sacado": "razao_social",
        "Grupo econômico": "grupo_economico",
        "Tipo participante": "tipo_participante",
        "Segmento": "segmento_principal",
        "Subsegmento financeiro": "segmento_financeiro_principal",
        "Condomínio": "condominio",
        "Público-alvo": "publico_alvo",
        "FIC-FIDC": "is_fic_fidc",
        "Status curadoria": "status_revisao",
        "Segmento Estratégia": "segmento_estrategia",
        "Subsegmento Estratégia": "subsegmento_estrategia",
        "Status snapshot": "snapshot_status",
        "Camadas evidência": "camadas_com_evidencia",
        "Emissão 25-26": "tem_emissao_2025_2026",
        "Faixa sub mín.": "sub_min_bucket",
        "Tem sub mín.": "tem_sub_minima",
        "Documento local": "tem_documento_local",
        "Indexador": "indexadores",
        "Tipo de cota": "tipo_cotas",
        "Classe documento": "document_classes",
        "Critério": "criteria_keys",
        "Chunk docs": "document_chunk_ids",
    }
    catalog_tables = _load_dimension_catalog_tables()
    catalog = catalog_tables["catalog"]
    catalog_manifest = catalog_tables["manifest"]
    assert isinstance(catalog, pd.DataFrame)
    assert isinstance(catalog_manifest, dict)
    catalog_dimensions = _dimension_catalog_options(catalog)
    use_catalog = bool(catalog_dimensions)
    monthly_tables = _load_dimension_monthly_tables() if use_catalog else {"monthly": pd.DataFrame(), "manifest": {}}
    dimension_monthly = monthly_tables["monthly"]
    dimension_value_atlas = monthly_tables.get("atlas", pd.DataFrame())
    dimension_monthly_manifest = monthly_tables["manifest"]
    assert isinstance(dimension_monthly, pd.DataFrame)
    assert isinstance(dimension_value_atlas, pd.DataFrame)
    assert isinstance(dimension_monthly_manifest, dict)
    profile_tables = _load_dimension_profile_tables() if use_catalog else {"profiles": pd.DataFrame(), "manifest": {}}
    dimension_profiles = profile_tables["profiles"]
    dimension_profile_manifest = profile_tables["manifest"]
    assert isinstance(dimension_profiles, pd.DataFrame)
    assert isinstance(dimension_profile_manifest, dict)
    dimensions = catalog_dimensions if use_catalog else fallback_dimensions
    metric_options = ["PL médio", "Captação líquida", "Veículos", "Fundos"]
    dimension_labels = list(dimensions)
    preset_options = _heatmap_preset_options(dimension_labels)
    preset_labels = list(preset_options)
    default_preset = "Administrador × Segmento" if "Administrador × Segmento" in preset_options else "Personalizado"

    ctrl_a, ctrl_b, ctrl_c, ctrl_d = st.columns([1.35, 0.9, 0.9, 0.65])
    with ctrl_a:
        preset_label = st.selectbox(
            "Combinação",
            preset_labels,
            index=preset_labels.index(default_preset),
            key="industry_heatmap_preset",
        )
    with ctrl_b:
        metric_label = st.selectbox("Métrica", metric_options, key="industry_heatmap_metric")
    with ctrl_c:
        period = st.selectbox(
            "Janela",
            ["Última competência", "Últimos 12 meses", "2025 até data-base", "Histórico completo"],
            key="industry_heatmap_period",
        )
    with ctrl_d:
        top_n = st.slider("Top", min_value=5, max_value=25, value=12, step=1, key="industry_heatmap_top")

    preset_pair = preset_options[preset_label]
    if preset_pair is None:
        row_ctrl, col_ctrl = st.columns([1.0, 1.0])
        with row_ctrl:
            row_label = st.selectbox(
                "Linhas",
                dimension_labels,
                index=dimension_labels.index("Administrador") if "Administrador" in dimension_labels else 0,
                key="industry_heatmap_rows",
            )
        with col_ctrl:
            col_label = st.selectbox(
                "Colunas",
                dimension_labels,
                index=dimension_labels.index("Segmento") if "Segmento" in dimension_labels else 0,
                key="industry_heatmap_cols",
            )
    else:
        row_label, col_label = preset_pair

    profile_heatmap_used = False
    frame = pd.DataFrame()
    profile_config = _profile_heatmap_metric_config(metric_label)
    if use_catalog and period == "Última competência" and profile_config is not None:
        heatmap = _profile_heatmap_frame(
            dimension_profiles,
            dimensions[row_label],
            dimensions[col_label],
            metric_label,
        )
        profile_heatmap_used = not heatmap.empty
        _, _, value_title, value_format = profile_config
    else:
        heatmap = pd.DataFrame()

    if not profile_heatmap_used:
        frame = _period_filter(vehicle, comp, period)
        if use_catalog:
            frame = _catalog_heatmap_base_frame(frame, catalog, dimensions[row_label], dimensions[col_label])
        else:
            cedentes = _build_structured_cedentes()
            snapshot_tables = _load_fund_snapshot_tables()
            snapshot = snapshot_tables["snapshot"]
            assert isinstance(snapshot, pd.DataFrame)
            frame = _heatmap_base_frame(frame, cedentes, snapshot, dimensions[row_label], dimensions[col_label])
        if frame.empty:
            st.caption("Sem linhas para a janela selecionada.")
            return
        frame = frame.copy()
        if not use_catalog:
            frame["linha"] = _dimension_series(frame, dimensions[row_label])
            frame["coluna"] = _dimension_series(frame, dimensions[col_label])
        frame = frame[(frame["linha"] != "n/d") & (frame["coluna"] != "n/d")]
        if frame.empty:
            st.caption("As dimensões selecionadas não têm dados preenchidos nessa janela.")
            return

        if metric_label == "PL médio":
            frame["pl_metric"] = pd.to_numeric(frame["pl"], errors="coerce").fillna(0) * frame["_metric_weight"]
            monthly = (
                frame.groupby(["competencia", "linha", "coluna"], dropna=False)["pl_metric"]
                .sum()
                .reset_index(name="valor_base")
            )
            heatmap = (
                monthly.groupby(["linha", "coluna"], dropna=False)["valor_base"]
                .mean()
                .reset_index(name="valor")
            )
            value_title = "PL médio (R$ bi)"
            value_format = ",.1f"
            heatmap["valor"] = heatmap["valor"] / 1e9
        elif metric_label == "Captação líquida":
            frame["captacao_metric"] = pd.to_numeric(frame["captacao_liquida"], errors="coerce").fillna(0) * frame["_metric_weight"]
            heatmap = (
                frame.groupby(["linha", "coluna"], dropna=False)["captacao_metric"]
                .sum()
                .reset_index(name="valor")
            )
            value_title = "Captação líquida (R$ bi)"
            value_format = ",.1f"
            heatmap["valor"] = heatmap["valor"] / 1e9
        elif metric_label == "Fundos":
            id_col = "cnpj_fundo" if "cnpj_fundo" in frame.columns else "cnpj"
            heatmap = (
                frame.groupby(["linha", "coluna"], dropna=False)[id_col]
                .nunique()
                .reset_index(name="valor")
            )
            value_title = "Fundos"
            value_format = ",.0f"
        else:
            heatmap = (
                frame.groupby(["linha", "coluna"], dropna=False)["cnpj"]
                .nunique()
                .reset_index(name="valor")
            )
            value_title = "Veículos"
            value_format = ",.0f"

    heatmap = heatmap[pd.to_numeric(heatmap["valor"], errors="coerce").fillna(0).ne(0)].copy()
    if heatmap.empty:
        st.caption("A combinação escolhida só retornou valores zerados.")
        return

    row_order = (
        heatmap.assign(abs_val=heatmap["valor"].abs())
        .groupby("linha", dropna=False)["abs_val"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
        .index.tolist()
    )
    col_order = (
        heatmap.assign(abs_val=heatmap["valor"].abs())
        .groupby("coluna", dropna=False)["abs_val"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
        .index.tolist()
    )
    heatmap = heatmap[heatmap["linha"].isin(row_order) & heatmap["coluna"].isin(col_order)].copy()
    heatmap["valor_formatado"] = heatmap["valor"].map(
        lambda value: f"{value:,.1f}".replace(",", "@").replace(".", ",").replace("@", ".")
        if metric_label in {"PL médio", "Captação líquida"}
        else _fmt_int(float(value))
    )

    scale = (
        alt.Scale(domainMid=0, range=[_BLACK, "#f7f2ed", _ORANGE])
        if metric_label == "Captação líquida"
        else alt.Scale(range=["#f7f2ed", _ORANGE])
    )
    chart = (
        alt.Chart(heatmap)
        .mark_rect(cornerRadius=2)
        .encode(
            x=alt.X("coluna:N", title=None, sort=col_order, axis=alt.Axis(labelLimit=130)),
            y=alt.Y("linha:N", title=None, sort=row_order, axis=alt.Axis(labelLimit=250)),
            color=alt.Color("valor:Q", title=value_title, scale=scale),
            tooltip=[
                alt.Tooltip("linha:N", title=row_label),
                alt.Tooltip("coluna:N", title=col_label),
                alt.Tooltip("valor:Q", title=value_title, format=value_format),
            ],
        )
        .properties(height=max(280, min(560, 26 * len(row_order))))
    )
    st.altair_chart(chart, width="stretch")

    pivot = heatmap.pivot_table(index="linha", columns="coluna", values="valor", aggfunc="sum", fill_value=0)
    pivot = pivot.reindex(index=row_order, columns=col_order).reset_index().rename(columns={"linha": row_label})
    st.dataframe(pivot, hide_index=True, width="stretch")
    if use_catalog:
        row_options = [value for value in row_order if value in set(heatmap["linha"].astype(str))]
        if row_options:
            st.markdown("**Evidências da célula selecionada**")
            drill_a, drill_b = st.columns([1.0, 1.0])
            with drill_a:
                drill_row = st.selectbox("Linha auditada", row_options, key="industry_heatmap_drill_row")
            col_candidates = (
                heatmap[heatmap["linha"].astype(str).eq(str(drill_row))]
                .assign(abs_val=lambda df: pd.to_numeric(df["valor"], errors="coerce").fillna(0).abs())
                .sort_values("abs_val", ascending=False)["coluna"]
                .drop_duplicates()
                .astype(str)
                .tolist()
            )
            col_options_for_row = [value for value in col_order if str(value) in set(col_candidates)] or col_candidates
            with drill_b:
                drill_col = st.selectbox("Coluna auditada", col_options_for_row, key="industry_heatmap_drill_col")
            snapshot_tables = _load_fund_snapshot_tables()
            snapshot = snapshot_tables["snapshot"]
            assert isinstance(snapshot, pd.DataFrame)
            drilldown = _catalog_heatmap_cell_frame(
                catalog,
                snapshot,
                dimensions[row_label],
                str(drill_row),
                dimensions[col_label],
                str(drill_col),
            )
            if drilldown.empty:
                st.caption("Sem evidências estruturadas para a célula selecionada.")
            else:
                unique_funds = drilldown.drop_duplicates("cnpj_fundo_norm") if "cnpj_fundo_norm" in drilldown.columns else drilldown
                total_pl = float(pd.to_numeric(unique_funds.get("pl", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
                row_docs = drilldown.get("row_source_document", pd.Series("", index=drilldown.index)).fillna("").astype(str).str.strip()
                col_docs = drilldown.get("col_source_document", pd.Series("", index=drilldown.index)).fillna("").astype(str).str.strip()
                evidence_pairs = len(drilldown)
                source_docs = pd.concat([row_docs[row_docs.ne("")], col_docs[col_docs.ne("")]]).nunique()
                drill_cards = [
                    _curation_card("FIDCs", _fmt_int(float(len(unique_funds))), f"{drill_row} × {drill_col}"[:60]),
                    _curation_card("PL", _fmt_bi(total_pl, 1), "fundos únicos"),
                    _curation_card("Evidências", _fmt_int(float(evidence_pairs)), "pares linha × coluna"),
                    _curation_card("Documentos", _fmt_int(float(source_docs)), "fontes distintas"),
                ]
                st.markdown(f'<div class="industry-kpi-grid">{"".join(drill_cards)}</div>', unsafe_allow_html=True)
                table_drill = drilldown.drop_duplicates(
                    [
                        col
                        for col in [
                            "cnpj_fundo_norm",
                            "row_source_layer",
                            "row_source_document",
                            "row_source_page",
                            "col_source_layer",
                            "col_source_document",
                            "col_source_page",
                        ]
                        if col in drilldown.columns
                    ]
                ).head(120)
                st.dataframe(_format_heatmap_cell_drilldown(table_drill), hide_index=True, width="stretch")
                st.download_button(
                    "Baixar evidências da célula",
                    data=drilldown.to_csv(index=False).encode("utf-8"),
                    file_name="industry_heatmap_cell_evidence.csv",
                    mime="text/csv",
                    key="industry_heatmap_cell_download",
                )
    if use_catalog:
        if profile_heatmap_used:
            uses_curated = pd.to_numeric(heatmap.get("curated_links", pd.Series(dtype=float)), errors="coerce").fillna(0).gt(0).any()
            uses_multivalue = pd.to_numeric(heatmap.get("weighted_links", pd.Series(dtype=float)), errors="coerce").fillna(0).gt(0).any()
            generated_at = dimension_profile_manifest.get("generated_at_utc", "")
            profile_comp = ""
            if "competencia" in heatmap.columns and not heatmap["competencia"].dropna().empty:
                profile_comp = str(heatmap["competencia"].dropna().iloc[0])
            visible_links = pd.to_numeric(heatmap.get("catalog_links", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
            source_links = pd.to_numeric(heatmap.get("source_document_links", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
            source_note = f"Fonte: `{_DIMENSION_PROFILE_PATH.name}`"
            if profile_comp:
                source_note += f" · competência {profile_comp}"
            if generated_at:
                source_note += f" · gerado em {generated_at}"
            source_note += f" · links visíveis {_fmt_int(float(visible_links))}"
            if source_links:
                source_note += f" · com fonte {_fmt_int(float(source_links))}"
            st.caption(source_note)
        else:
            uses_curated = False
            uses_multivalue = False
            for col in ["row_is_curated", "col_is_curated"]:
                if col in frame.columns:
                    uses_curated = uses_curated or frame[col].astype(str).str.lower().isin({"true", "1"}).any()
            for col in ["row_is_multivalue", "col_is_multivalue"]:
                if col in frame.columns:
                    uses_multivalue = uses_multivalue or frame[col].astype(str).str.lower().isin({"true", "1"}).any()
            generated_at = catalog_manifest.get("generated_at_utc", "")
            source_note = f"Fonte: `{_DIMENSION_CATALOG_PATH.name}`"
            if generated_at:
                source_note += f" · gerado em {generated_at}"
            st.caption(source_note)
    else:
        uses_curated = dimensions[row_label] in _CEDENTE_HEATMAP_COLUMNS or dimensions[col_label] in _CEDENTE_HEATMAP_COLUMNS
        uses_multivalue = dimensions[row_label] in _SNAPSHOT_MULTI_COLUMNS or dimensions[col_label] in _SNAPSHOT_MULTI_COLUMNS
    if uses_curated:
        st.caption(
            "Quando a dimensão é cedente/sacado, PL e fluxo são alocados igualmente entre os participantes ativos "
            "do mesmo fundo para evitar dupla contagem direta."
        )
    if uses_multivalue:
        st.caption(
            "Dimensões multivalor vindas do snapshot, como indexador e critérios, ponderam PL e fluxo entre os itens "
            "extraídos para preservar a ordem de grandeza agregada."
        )


@st.cache_data(show_spinner=False)
def _load_issuance_tables() -> dict[str, pd.DataFrame | dict[str, object]]:
    return {
        "annual": load_dataframe(_ISSUANCE_ANNUAL_PATH),
        "sector_year": load_dataframe(_ISSUANCE_SECTOR_YEAR_PATH),
        "tranches": load_dataframe(_ISSUANCE_TRANCHES_PATH),
        "manifest": load_pipeline_manifest(_ISSUANCE_MANIFEST_PATH),
    }


def _format_money_bi_column(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_bi(float(value), 1))
    return out


def _render_issuance_study() -> None:
    st.markdown('<div class="industry-section">Emissões, ofertas e pricing documental</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Camada inspirada na aba Estratégia: volume anual de emissões/ofertas, '
        "CNPJs emissores, setor × ano e tranches extraídas de documentos. Conceito distinto de captação líquida do IME.</div>",
        unsafe_allow_html=True,
    )
    tables = _load_issuance_tables()
    annual = tables["annual"]
    sector_year = tables["sector_year"]
    tranches = tables["tranches"]
    manifest = tables["manifest"]
    assert isinstance(annual, pd.DataFrame)
    assert isinstance(sector_year, pd.DataFrame)
    assert isinstance(tranches, pd.DataFrame)
    assert isinstance(manifest, dict)
    if annual.empty and sector_year.empty and tranches.empty:
        st.info("Artefatos de emissão ainda não foram gerados. Rode `python scripts/build_fidc_industry_issuance.py`.")
        return

    annual_num = annual.copy()
    for col in ["ano", "emissores_cnpj", "ofertas_linhas", "volume_registrado_brl", "volume_conservador_brl", "pl_atual_brl", "com_matriz_regulatoria"]:
        if col in annual_num.columns:
            annual_num[col] = pd.to_numeric(annual_num[col], errors="coerce").fillna(0)
    latest = annual_num.sort_values("ano").iloc[-1] if not annual_num.empty else pd.Series(dtype=object)
    total_conservador = float(annual_num.get("volume_conservador_brl", pd.Series(dtype=float)).sum()) if not annual_num.empty else 0.0
    cards = [
        _curation_card("Volume conservador", _fmt_bi(total_conservador, 1), "2024-2026 YTD"),
        _curation_card("Último ano/YTD", _fmt_bi(float(latest.get("volume_conservador_brl", 0)), 1), str(latest.get("periodo", ""))),
        _curation_card("CNPJs emissores", _fmt_int(float(latest.get("emissores_cnpj", 0))), "último período"),
        _curation_card("Tranches documentais", _fmt_int(float(len(tranches))), f"{_fmt_int(float(tranches['cnpj_fundo'].nunique())) if 'cnpj_fundo' in tranches else '0'} FIDCs"),
        _curation_card("Setores × ano", _fmt_int(float(len(sector_year))), "base agregada"),
        _curation_card("Manifesto", str(manifest.get("schema_version", "n/d")).split("/")[-1], str(manifest.get("generated_at_utc", ""))[:10]),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    tab_annual, tab_sector, tab_pricing, tab_base = st.tabs(["Anual", "Setor × ano", "Indexadores", "Base"])
    with tab_annual:
        if not annual_num.empty:
            chart_data = annual_num.copy()
            chart_data["volume_bi"] = chart_data["volume_conservador_brl"] / 1e9
            chart_data["ano_label"] = chart_data["periodo"].astype(str)
            bars = (
                alt.Chart(chart_data)
                .mark_bar(color=_ORANGE, cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
                .encode(
                    x=alt.X("ano_label:N", title=None),
                    y=alt.Y("volume_bi:Q", title="Volume conservador (R$ bi)", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    tooltip=[
                        alt.Tooltip("periodo:N", title="período"),
                        alt.Tooltip("volume_bi:Q", title="volume R$ bi", format=",.1f"),
                        alt.Tooltip("emissores_cnpj:Q", title="CNPJs emissores"),
                    ],
                )
            )
            points = (
                alt.Chart(chart_data)
                .mark_point(color=_BLACK, filled=True, size=95)
                .encode(
                    x=alt.X("ano_label:N", title=None),
                    y=alt.Y("emissores_cnpj:Q", title="CNPJs emissores"),
                    tooltip=[alt.Tooltip("emissores_cnpj:Q", title="CNPJs emissores")],
                )
            )
            st.altair_chart(alt.layer(bars, points).resolve_scale(y="independent").properties(height=330), width="stretch")
            display = annual_num.copy()
            display = display.rename(
                columns={
                    "ano": "Ano",
                    "periodo": "Período",
                    "emissores_cnpj": "CNPJs emissores",
                    "ofertas_linhas": "Linhas oferta",
                    "volume_registrado_brl": "Volume registrado",
                    "volume_conservador_brl": "Volume conservador",
                    "pl_atual_brl": "PL atual",
                    "com_matriz_regulatoria": "Com matriz",
                }
            )
            st.dataframe(_format_money_bi_column(display, ["Volume registrado", "Volume conservador", "PL atual"]), hide_index=True, width="stretch")
        else:
            st.caption("Agregado anual indisponível.")
    with tab_sector:
        if not sector_year.empty:
            data = sector_year.copy()
            data["ano"] = pd.to_numeric(data["ano"], errors="coerce").fillna(0).astype(int).astype(str)
            data["volume_bi"] = pd.to_numeric(data["volume_conservador_brl"], errors="coerce").fillna(0) / 1e9
            data["setor"] = data["setor_n1"].astype(str) + " | " + data["setor_n2"].astype(str)
            top = data.groupby("setor")["volume_bi"].sum().sort_values(ascending=False).head(18).index.tolist()
            data = data[data["setor"].isin(top)].copy()
            heat = (
                alt.Chart(data)
                .mark_rect(cornerRadius=2)
                .encode(
                    x=alt.X("ano:N", title="Ano"),
                    y=alt.Y("setor:N", title=None, sort=top),
                    color=alt.Color("volume_bi:Q", title="R$ bi", scale=alt.Scale(range=["#f7f2ed", _ORANGE])),
                    tooltip=[
                        alt.Tooltip("ano:N", title="ano"),
                        alt.Tooltip("setor:N", title="setor"),
                        alt.Tooltip("volume_bi:Q", title="volume R$ bi", format=",.1f"),
                        alt.Tooltip("emissores_cnpj:Q", title="CNPJs"),
                    ],
                )
                .properties(height=max(320, 24 * len(top)))
            )
            st.altair_chart(heat, width="stretch")
            table = data.sort_values(["ano", "volume_bi"], ascending=[False, False]).rename(
                columns={
                    "ano": "Ano",
                    "setor_n1": "Setor",
                    "setor_n2": "Subsegmento",
                    "emissores_cnpj": "CNPJs",
                    "volume_registrado_brl": "Volume registrado",
                    "volume_conservador_brl": "Volume conservador",
                    "pl_atual_brl": "PL atual",
                }
            )
            st.dataframe(_format_money_bi_column(table[["Ano", "Setor", "Subsegmento", "CNPJs", "Volume registrado", "Volume conservador", "PL atual"]], ["Volume registrado", "Volume conservador", "PL atual"]), hide_index=True, width="stretch")
        else:
            st.caption("Setor × ano indisponível.")
    with tab_pricing:
        if not tranches.empty:
            data = tranches.copy()
            data["volume_bi"] = pd.to_numeric(data["volume_brl"], errors="coerce").fillna(0) / 1e9
            data["setor"] = data["setor_n1"].astype(str)
            data["indexador"] = data["indexador"].replace("", "n/d")
            grouped = (
                data.groupby(["setor", "indexador"], dropna=False)
                .agg(Volume=("volume_bi", "sum"), Tranches=("cnpj_fundo", "size"), FIDCs=("cnpj_fundo", "nunique"))
                .reset_index()
            )
            top_sectors = grouped.groupby("setor")["Volume"].sum().sort_values(ascending=False).head(14).index.tolist()
            grouped = grouped[grouped["setor"].isin(top_sectors)].copy()
            chart = (
                alt.Chart(grouped)
                .mark_rect(cornerRadius=2)
                .encode(
                    x=alt.X("indexador:N", title="Indexador"),
                    y=alt.Y("setor:N", title=None, sort=top_sectors),
                    color=alt.Color("Volume:Q", title="R$ bi", scale=alt.Scale(range=["#f7f2ed", _ORANGE])),
                    tooltip=[
                        alt.Tooltip("setor:N", title="setor"),
                        alt.Tooltip("indexador:N", title="indexador"),
                        alt.Tooltip("Volume:Q", title="volume R$ bi", format=",.2f"),
                        alt.Tooltip("Tranches:Q", title="tranches"),
                        alt.Tooltip("FIDCs:Q", title="FIDCs"),
                    ],
                )
                .properties(height=max(300, 26 * len(top_sectors)))
            )
            st.altair_chart(chart, width="stretch")
            detail = data.sort_values("volume_bi", ascending=False).head(80).copy()
            detail = detail.rename(
                columns={
                    "fundo": "Fundo",
                    "cnpj_fundo": "CNPJ",
                    "ano": "Ano",
                    "tipo_cota": "Tipo cota",
                    "indexador": "Indexador",
                    "volume_brl": "Volume",
                    "setor_n1": "Setor",
                    "setor_n2": "Subsegmento",
                    "documento_origem": "Documento",
                    "score_confianca": "Score",
                }
            )
            keep = ["Fundo", "CNPJ", "Ano", "Tipo cota", "Indexador", "Volume", "Setor", "Subsegmento", "Documento", "Score"]
            st.dataframe(_format_money_bi_column(detail[[col for col in keep if col in detail.columns]], ["Volume"]), hide_index=True, width="stretch")
        else:
            st.caption("Tranches documentais indisponíveis.")
    with tab_base:
        selected = st.selectbox(
            "Tabela",
            ["issuance_annual.csv", "issuance_sector_year.csv", "issuance_tranches.csv.gz", "industry_issuance_manifest.json"],
            key="industry_issuance_base_select",
        )
        if selected == "issuance_annual.csv":
            st.dataframe(annual.head(500), hide_index=True, width="stretch")
        elif selected == "issuance_sector_year.csv":
            st.dataframe(sector_year.head(500), hide_index=True, width="stretch")
        elif selected == "issuance_tranches.csv.gz":
            st.dataframe(tranches.head(500), hide_index=True, width="stretch")
        else:
            st.json(manifest)


@st.cache_data(show_spinner=False)
def _load_document_tables() -> dict[str, pd.DataFrame | dict[str, object]]:
    return {
        "inventory": load_dataframe(_DOCUMENT_INVENTORY_PATH),
        "chunks": load_dataframe(_DOCUMENT_CHUNKS_PATH),
        "manifest": load_pipeline_manifest(_DOCUMENT_MANIFEST_PATH),
    }


def _format_bytes(value: object) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number) or float(number) <= 0:
        return ""
    size = float(number)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:,.1f} {unit}".replace(",", "@").replace(".", ",").replace("@", ".")
        size /= 1024
    return ""


def _document_chunk_plan_frame(chunks: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    return build_document_chunk_plan(chunks, inventory)


def _format_document_chunk_plan(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    columns = [
        "status_lote",
        "chunk_status",
        "chunk_id",
        "next_action",
        "acao_revisada",
        "responsavel",
        "prazo",
        "notas",
        "updated_at_utc",
        "document_count",
        "cnpj_count",
        "priority_docs_effective",
        "local_ready_docs",
        "missing_local_docs",
        "hashed_docs",
        "hash_pending_docs",
        "local_ready_ratio",
        "hash_ratio",
        "total_bytes",
        "document_date_min",
        "document_date_max",
        "document_classes",
        "dominant_stage",
        "dominant_processing_status",
        "sample_funds",
        "rerun_command",
    ]
    out = frame[[col for col in columns if col in frame.columns]].copy()
    out = out.rename(
        columns={
            "status_lote": "Status acomp.",
            "chunk_status": "Status",
            "chunk_id": "Chunk",
            "next_action": "Próxima ação",
            "acao_revisada": "Ação revisada",
            "responsavel": "Responsável",
            "prazo": "Prazo",
            "notas": "Notas",
            "updated_at_utc": "Atualizado",
            "document_count": "Docs",
            "cnpj_count": "CNPJs",
            "priority_docs_effective": "Prioridade 25-26",
            "local_ready_docs": "Locais",
            "missing_local_docs": "Faltam local",
            "hashed_docs": "Com hash",
            "hash_pending_docs": "Faltam hash",
            "local_ready_ratio": "% local",
            "hash_ratio": "% hash",
            "total_bytes": "Tamanho",
            "document_date_min": "Data mín.",
            "document_date_max": "Data máx.",
            "document_classes": "Classes",
            "dominant_stage": "Etapa",
            "dominant_processing_status": "Status proc.",
            "sample_funds": "Amostra FIDCs",
            "rerun_command": "Comando",
        }
    )
    for col in ["Docs", "CNPJs", "Prioridade 25-26", "Locais", "Faltam local", "Com hash", "Faltam hash"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
    for col in ["% local", "% hash"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").map(
                lambda value: "n/d" if pd.isna(value) else _fmt_pct(float(value))
            )
    if "Tamanho" in out.columns:
        out["Tamanho"] = out["Tamanho"].map(_format_bytes)
    return out


def _render_document_inventory() -> None:
    st.markdown('<div class="industry-section">Documentos, caches e chunks</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Inventário documental versionável para descoberta, OCR, parsing e extração incremental. '
        "Cada linha preserva fonte, documento, status local, fingerprint e chunk sugerido.</div>",
        unsafe_allow_html=True,
    )
    tables = _load_document_tables()
    inventory = tables["inventory"]
    chunks = tables["chunks"]
    manifest = tables["manifest"]
    assert isinstance(inventory, pd.DataFrame)
    assert isinstance(chunks, pd.DataFrame)
    assert isinstance(manifest, dict)
    if inventory.empty and chunks.empty:
        st.info("Inventário documental ainda não gerado. Rode `python scripts/build_fidc_industry_documents.py`.")
        return

    quality = manifest.get("quality", {}) if isinstance(manifest, dict) else {}
    coverage = quality.get("coverage", {}) if isinstance(quality, dict) else {}
    doc_rows = int(quality.get("document_rows", len(inventory))) if isinstance(quality, dict) else len(inventory)
    funds = int(quality.get("funds", inventory["cnpj_fundo"].nunique() if "cnpj_fundo" in inventory else 0)) if isinstance(quality, dict) else 0
    local_ready = int(quality.get("local_ready_docs", 0)) if isinstance(quality, dict) else 0
    priority_docs = int(quality.get("priority_2025_2026_docs", 0)) if isinstance(quality, dict) else 0
    chunk_count = int(quality.get("chunks", len(chunks))) if isinstance(quality, dict) else len(chunks)
    max_docs = int(quality.get("max_documents_per_chunk", 0)) if isinstance(quality, dict) else 0
    cards = [
        _curation_card("Documentos", _fmt_int(float(doc_rows)), f"{_fmt_int(float(funds))} FIDCs"),
        _curation_card("Prioridade 2025-2026", _fmt_int(float(priority_docs)), "emissões recentes"),
        _curation_card("Local ready", _fmt_int(float(local_ready)), _fmt_pct(local_ready / doc_rows) if doc_rows else "n/d"),
        _curation_card("Chunks", _fmt_int(float(chunk_count)), f"até {_fmt_int(float(max_docs))} docs/chunk"),
        _curation_card("CNPJ", _fmt_pct(float(coverage.get("cnpj_fundo", 0))) if isinstance(coverage, dict) else "n/d", "cobertura"),
        _curation_card("Data doc.", _fmt_pct(float(coverage.get("document_date", 0))) if isinstance(coverage, dict) else "n/d", "cobertura"),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    tab_cov, tab_chunks, tab_inventory, tab_manifest = st.tabs(["Cobertura", "Chunks", "Inventário", "Manifesto"])
    with tab_cov:
        col_a, col_b = st.columns([1.0, 1.0])
        with col_a:
            st.markdown("**Classes documentais**")
            if "document_class" in inventory.columns:
                class_counts = (
                    inventory["document_class"].fillna("outro").replace("", "outro").value_counts().reset_index()
                )
                class_counts.columns = ["Classe", "Documentos"]
                chart = (
                    alt.Chart(class_counts)
                    .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
                    .encode(
                        x=alt.X("Documentos:Q", title="documentos", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                        y=alt.Y("Classe:N", title=None, sort="-x"),
                        tooltip=[
                            alt.Tooltip("Classe:N", title="classe"),
                            alt.Tooltip("Documentos:Q", title="documentos"),
                        ],
                    )
                    .properties(height=260)
                )
                st.altair_chart(chart, width="stretch")
            else:
                st.caption("Classe documental indisponível.")
        with col_b:
            st.markdown("**Status por tipo de arquivo**")
            if {"content_kind", "local_exists"}.issubset(inventory.columns):
                status = inventory.copy()
                status["Status"] = status["local_exists"].astype(str).str.lower().isin({"true", "1", "sim"}).map(
                    {True: "local", False: "lacuna"}
                )
                grouped = (
                    status.groupby(["content_kind", "Status"], dropna=False)
                    .size()
                    .reset_index(name="Documentos")
                    .rename(columns={"content_kind": "Tipo"})
                )
                chart = (
                    alt.Chart(grouped)
                    .mark_bar(cornerRadiusEnd=2)
                    .encode(
                        x=alt.X("Documentos:Q", title="documentos", stack="zero", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                        y=alt.Y("Tipo:N", title=None, sort="-x"),
                        color=alt.Color("Status:N", scale=alt.Scale(domain=["local", "lacuna"], range=[_ORANGE, _BLACK]), legend=alt.Legend(title=None, orient="top")),
                        tooltip=[
                            alt.Tooltip("Tipo:N", title="tipo"),
                            alt.Tooltip("Status:N", title="status"),
                            alt.Tooltip("Documentos:Q", title="documentos"),
                        ],
                    )
                    .properties(height=260)
                )
                st.altair_chart(chart, width="stretch")
            else:
                st.caption("Status local indisponível.")
        if isinstance(coverage, dict) and coverage:
            cov = pd.DataFrame([{"Campo": key, "Cobertura": float(value) * 100} for key, value in coverage.items()])
            cov = cov.sort_values("Cobertura", ascending=True)
            st.markdown("**Cobertura dos campos de rastreabilidade**")
            st.altair_chart(
                alt.Chart(cov)
                .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
                .encode(
                    x=alt.X("Cobertura:Q", title="%", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    y=alt.Y("Campo:N", title=None, sort="x"),
                    tooltip=[
                        alt.Tooltip("Campo:N", title="campo"),
                        alt.Tooltip("Cobertura:Q", title="cobertura", format=",.1f"),
                    ],
                )
                .properties(height=260),
                width="stretch",
            )
    with tab_chunks:
        if chunks.empty:
            st.caption("Chunks indisponíveis.")
        else:
            chunk_actions = _load_document_chunk_actions()
            plan = _apply_document_chunk_actions(_document_chunk_plan_frame(chunks, inventory), chunk_actions)
            if plan.empty:
                st.caption("Não foi possível montar plano de processamento por chunk.")
            else:
                status_counts = plan["chunk_status"].value_counts().to_dict()
                action_counts = plan["status_lote"].replace("", "pendente").value_counts().to_dict()
                missing_docs = float(pd.to_numeric(plan.get("missing_local_docs", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
                priority_open = float(
                    pd.to_numeric(
                        plan.loc[~plan["chunk_status"].eq("pronto"), "priority_docs_effective"],
                        errors="coerce",
                    ).fillna(0).sum()
                )
                chunk_cards = [
                    _curation_card("Baixar", _fmt_int(float(status_counts.get("baixar", 0))), f"{_fmt_int(missing_docs)} docs faltantes"),
                    _curation_card("Fingerprint", _fmt_int(float(status_counts.get("fingerprint", 0))), "hash pendente"),
                    _curation_card("Processar", _fmt_int(float(status_counts.get("processar", 0))), f"{_fmt_int(priority_open)} docs prioridade"),
                    _curation_card("Em andamento", _fmt_int(float(action_counts.get("em andamento", 0))), "acompanhamento salvo"),
                ]
                st.markdown(f'<div class="industry-kpi-grid">{"".join(chunk_cards)}</div>', unsafe_allow_html=True)
                chunk_ctrl_a, chunk_ctrl_b, chunk_ctrl_c, chunk_ctrl_d = st.columns([0.8, 1.0, 0.9, 1.2])
                with chunk_ctrl_a:
                    status_options = [value for value in ["baixar", "fingerprint", "processar", "pronto"] if value in set(plan["chunk_status"])]
                    default_status = [value for value in status_options if value != "pronto"] or status_options
                    selected_statuses = st.multiselect(
                        "Status",
                        status_options,
                        default=default_status,
                        key="industry_document_chunk_status",
                    )
                with chunk_ctrl_b:
                    stage_options = sorted([value for value in plan.get("dominant_stage", pd.Series(dtype=str)).fillna("").astype(str).unique() if value])
                    selected_stages = st.multiselect(
                        "Etapa",
                        stage_options,
                        default=stage_options,
                        key="industry_document_chunk_stage",
                    )
                with chunk_ctrl_c:
                    action_status_options = ["pendente", "em andamento", "processado", "bloqueado", "ignorado"]
                    selected_action_statuses = st.multiselect(
                        "Acompanhamento",
                        action_status_options,
                        default=action_status_options,
                        key="industry_document_chunk_action_status",
                    )
                with chunk_ctrl_d:
                    chunk_query = st.text_input(
                        "Buscar chunk",
                        key="industry_document_chunk_query",
                        placeholder="chunk, classe, FIDC, CNPJ ou comando",
                    )
                chunk_view = plan[plan["chunk_status"].isin(selected_statuses)].copy() if selected_statuses else plan.iloc[0:0].copy()
                if selected_stages and "dominant_stage" in chunk_view.columns:
                    chunk_view = chunk_view[chunk_view["dominant_stage"].isin(selected_stages)].copy()
                if selected_action_statuses and "status_lote" in chunk_view.columns:
                    chunk_view = chunk_view[
                        chunk_view["status_lote"].fillna("").replace("", "pendente").isin(selected_action_statuses)
                    ].copy()
                if chunk_query:
                    search_cols = [
                        col
                        for col in [
                            "chunk_id",
                            "document_classes",
                            "source_tables",
                            "sample_cnpjs",
                            "sample_funds",
                            "dominant_stage",
                            "dominant_processing_status",
                            "rerun_command",
                        ]
                        if col in chunk_view.columns
                    ]
                    search = chunk_view[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=chunk_view.index)
                    chunk_view = chunk_view[search.str.contains(chunk_query, case=False, na=False)].copy()
                chunk_display = _format_document_chunk_plan(chunk_view)
                edited_chunks = st.data_editor(
                    chunk_display,
                    hide_index=True,
                    width="stretch",
                    height=520,
                    disabled=[
                        "Status",
                        "Chunk",
                        "Próxima ação",
                        "Atualizado",
                        "Docs",
                        "CNPJs",
                        "Prioridade 25-26",
                        "Locais",
                        "Faltam local",
                        "Com hash",
                        "Faltam hash",
                        "% local",
                        "% hash",
                        "Tamanho",
                        "Data mín.",
                        "Data máx.",
                        "Classes",
                        "Etapa",
                        "Status proc.",
                        "Amostra FIDCs",
                        "Comando",
                    ],
                    column_config={
                        "Status acomp.": st.column_config.SelectboxColumn(
                            "Status acomp.",
                            options=action_status_options,
                            required=True,
                        ),
                        "Ação revisada": st.column_config.TextColumn("Ação revisada", width="large"),
                        "Notas": st.column_config.TextColumn("Notas", width="large"),
                        "Comando": st.column_config.TextColumn("Comando", width="large"),
                    },
                    key="industry_document_chunk_editor",
                )
                if st.button("Salvar acompanhamento dos chunks", type="primary", key="industry_save_document_chunk_actions"):
                    edited_actions = pd.DataFrame(
                        {
                            "chunk_id": edited_chunks["Chunk"].fillna("").astype(str),
                            "status_lote": edited_chunks["Status acomp."].fillna("").astype(str).replace("", "pendente"),
                            "acao_revisada": edited_chunks["Ação revisada"].fillna("").astype(str),
                            "responsavel": edited_chunks["Responsável"].fillna("").astype(str),
                            "prazo": edited_chunks["Prazo"].fillna("").astype(str),
                            "notas": edited_chunks["Notas"].fillna("").astype(str),
                            "updated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        }
                    )
                    material_cols = ["acao_revisada", "responsavel", "prazo", "notas"]
                    material = edited_actions["status_lote"].ne("pendente") | (
                        edited_actions[material_cols].fillna("").astype(str).agg(" ".join, axis=1).str.strip().ne("")
                    )
                    edited_actions = edited_actions[edited_actions["chunk_id"].str.strip().ne("") & material].copy()
                    visible_ids = set(edited_chunks["Chunk"].fillna("").astype(str))
                    existing = chunk_actions.copy()
                    if not existing.empty and "chunk_id" in existing.columns:
                        existing = existing[~existing["chunk_id"].fillna("").astype(str).isin(visible_ids)].copy()
                    updated_actions = pd.concat([existing, edited_actions], ignore_index=True)
                    audit_events = build_review_audit_events(
                        previous=_document_chunk_actions_for_audit(chunk_actions),
                        updated=_document_chunk_actions_for_audit(updated_actions),
                        key_column="chunk_id",
                        review_domain="document_chunk_action",
                        source="industry_document_chunk_editor",
                    )
                    audit = append_review_audit_events(audit_events, _DOCUMENT_CHUNK_ACTION_AUDIT_PATH)
                    _save_document_chunk_actions(updated_actions)
                    materialized_plan = build_document_chunk_plan(chunks, inventory, actions=updated_actions)
                    save_dataframe(materialized_plan, _DOCUMENT_CHUNK_PLAN_PATH)
                    _load_document_chunk_actions.clear()
                    st.success(
                        f"Acompanhamento salvo para {_fmt_int(float(len(edited_actions)))} chunks visíveis. "
                        f"Histórico: {len(audit_events):,} eventos novos, {len(audit):,} eventos no total. "
                        f"Plano atualizado com {len(materialized_plan):,} chunks."
                    )
                st.download_button(
                    "Baixar plano de chunks",
                    data=chunk_view.to_csv(index=False).encode("utf-8"),
                    file_name="industry_document_chunk_plan.csv",
                    mime="text/csv",
                    key="industry_document_chunk_plan_download",
                )
                with st.expander("Histórico do acompanhamento de chunks"):
                    _render_review_audit(
                        _DOCUMENT_CHUNK_ACTION_AUDIT_PATH,
                        empty_label="Ainda não há histórico de acompanhamento dos chunks documentais.",
                    )
                with st.expander("Tabela bruta de chunks"):
                    show = chunks.copy()
                    for col in ["document_count", "cnpj_count", "priority_2025_2026_docs", "local_ready_docs", "hashed_docs"]:
                        if col in show.columns:
                            show[col] = pd.to_numeric(show[col], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
                    if "total_bytes" in show.columns:
                        show["total_bytes"] = show["total_bytes"].map(_format_bytes)
                    rename = {
                        "chunk_id": "Chunk",
                        "document_count": "Docs",
                        "cnpj_count": "CNPJs",
                        "priority_2025_2026_docs": "Prioridade",
                        "local_ready_docs": "Locais",
                        "hashed_docs": "Com hash",
                        "total_bytes": "Tamanho",
                        "document_date_min": "Data mín.",
                        "document_date_max": "Data máx.",
                        "document_classes": "Classes",
                        "source_tables": "Fontes",
                        "sample_cnpjs": "Amostra CNPJs",
                        "rerun_command": "Reexecução",
                    }
                    cols = [col for col in rename if col in show.columns]
                    st.dataframe(show[cols].rename(columns=rename), hide_index=True, width="stretch")
    with tab_inventory:
        frame = inventory.copy()
        ctrl_a, ctrl_b, ctrl_c, ctrl_d = st.columns([1.2, 0.9, 0.9, 0.7])
        with ctrl_a:
            query = st.text_input("Buscar documento/FIDC", key="industry_document_query", placeholder="nome, CNPJ, ID, fonte")
        with ctrl_b:
            class_values = sorted([value for value in frame.get("document_class", pd.Series(dtype=str)).fillna("").astype(str).unique() if value])
            selected_classes = st.multiselect("Classe", class_values, default=class_values, key="industry_document_classes")
        with ctrl_c:
            chunk_values = ["Todos"] + sorted([value for value in frame.get("chunk_id", pd.Series(dtype=str)).fillna("").astype(str).unique() if value])
            selected_chunk = st.selectbox("Chunk", chunk_values, key="industry_document_chunk")
        with ctrl_d:
            only_priority = st.checkbox("2025-2026", value=False, key="industry_document_priority")

        if selected_classes and "document_class" in frame.columns:
            frame = frame[frame["document_class"].isin(selected_classes)].copy()
        if selected_chunk != "Todos" and "chunk_id" in frame.columns:
            frame = frame[frame["chunk_id"].eq(selected_chunk)].copy()
        if only_priority and "priority_2025_2026" in frame.columns:
            frame = frame[frame["priority_2025_2026"].astype(str).str.lower().isin({"true", "1", "sim"})].copy()
        if query:
            search_cols = [
                col
                for col in ["cnpj_fundo", "fundo", "documento_origem", "documento_id", "source_table", "local_path", "chunk_id"]
                if col in frame.columns
            ]
            search = frame[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=frame.index)
            frame = frame[search.str.contains(query, case=False, na=False)].copy()

        frame["bytes_num"] = pd.to_numeric(frame.get("bytes"), errors="coerce").fillna(0)
        frame = frame.sort_values(["priority_2025_2026", "bytes_num"], ascending=[False, False]).head(400)
        display_cols = [
            "chunk_id",
            "cnpj_fundo",
            "fundo",
            "setor_n1",
            "document_class",
            "content_kind",
            "document_date",
            "documento_origem",
            "documento_id",
            "local_exists",
            "bytes",
            "hash_status",
            "source_table",
            "suggested_stage",
            "processing_status",
        ]
        show = frame[[col for col in display_cols if col in frame.columns]].copy()
        if "bytes" in show.columns:
            show["bytes"] = show["bytes"].map(_format_bytes)
        for col in show.columns:
            show[col] = show[col].fillna("").astype(str)
        show = show.rename(
            columns={
                "chunk_id": "Chunk",
                "cnpj_fundo": "CNPJ",
                "fundo": "Fundo",
                "setor_n1": "Setor",
                "document_class": "Classe",
                "content_kind": "Tipo",
                "document_date": "Data",
                "documento_origem": "Documento",
                "documento_id": "ID doc",
                "local_exists": "Local",
                "bytes": "Tamanho",
                "hash_status": "Hash",
                "source_table": "Fonte",
                "suggested_stage": "Próxima etapa",
                "processing_status": "Status",
            }
        )
        st.dataframe(show, hide_index=True, width="stretch")
    with tab_manifest:
        if manifest:
            st.download_button(
                "Baixar manifesto",
                data=json.dumps(manifest, ensure_ascii=False, indent=2),
                file_name="industry_document_manifest.json",
                mime="application/json",
            )
            st.json(manifest)
        else:
            st.caption("Manifesto documental não encontrado.")


def _format_review_audit_table(audit: pd.DataFrame) -> pd.DataFrame:
    if audit.empty:
        return pd.DataFrame(
            columns=[
                "Quando",
                "Domínio",
                "ID",
                "Campo",
                "Antes",
                "Depois",
                "Status",
                "Origem",
            ]
        )
    out = audit.copy()
    out = out.sort_values("saved_at_utc", ascending=False).head(400)
    return out.rename(
        columns={
            "saved_at_utc": "Quando",
            "review_domain": "Domínio",
            "record_id": "ID",
            "field": "Campo",
            "old_value": "Antes",
            "new_value": "Depois",
            "status_after": "Status",
            "source": "Origem",
        }
    )[
        ["Quando", "Domínio", "ID", "Campo", "Antes", "Depois", "Status", "Origem"]
    ]


def _render_review_audit(path: Path, *, empty_label: str) -> None:
    audit = load_review_audit(path)
    if audit.empty:
        st.caption(empty_label)
        return
    col_a, col_b = st.columns([1.0, 1.0])
    with col_a:
        query = st.text_input("Buscar histórico", key=f"review_audit_query_{path.stem}", placeholder="ID, campo, valor ou status")
    with col_b:
        fields = sorted(audit["field"].dropna().astype(str).unique())
        selected_fields = st.multiselect("Campo", fields, default=fields, key=f"review_audit_fields_{path.stem}")
    filtered = audit[audit["field"].isin(selected_fields)].copy() if selected_fields else audit.iloc[0:0].copy()
    if query:
        search = filtered.fillna("").astype(str).agg(" ".join, axis=1)
        filtered = filtered[search.str.contains(query, case=False, na=False)].copy()
    st.dataframe(_format_review_audit_table(filtered), hide_index=True, width="stretch")


def _load_criteria_reviews() -> pd.DataFrame:
    return load_criteria_reviews(_CRITERIA_REVIEW_PATH)


def _save_criteria_reviews(reviews: pd.DataFrame) -> None:
    save_criteria_reviews(reviews, _CRITERIA_REVIEW_PATH)


def _persist_structured_criteria(reviews: pd.DataFrame) -> pd.DataFrame:
    criteria = pd.concat(
        [
            load_criteria_source(_ALL_FIDCS_CRITERIA),
            load_regulatory_feature_criteria(_REGULATORY_DB),
        ],
        ignore_index=True,
        sort=False,
    )
    fund_universe = _load_cedente_fund_universe()
    structured = build_criteria_structured(
        criteria,
        reviews,
        fund_universe=fund_universe,
        review_audit=load_review_audit(_CRITERIA_REVIEW_AUDIT_PATH),
    )
    save_dataframe(structured, _CRITERIA_STRUCTURED_PATH)
    manifest = build_criteria_pipeline_manifest(
        industry_dir=_DATA_DIR,
        strategy_db=_REGULATORY_DB,
        criteria_source_path=_ALL_FIDCS_CRITERIA,
        reviews_path=_CRITERIA_REVIEW_PATH,
        output_path=_CRITERIA_STRUCTURED_PATH,
        manifest_path=_CRITERIA_MANIFEST_PATH,
        criteria=criteria,
        reviews=reviews,
        fund_universe=fund_universe,
        structured=structured,
    )
    save_pipeline_manifest(manifest, _CRITERIA_MANIFEST_PATH)
    return structured


@st.cache_data(show_spinner=False)
def _load_criteria_tables() -> dict[str, pd.DataFrame | dict[str, object]]:
    return {
        "structured": load_dataframe(_CRITERIA_STRUCTURED_PATH),
        "manifest": load_pipeline_manifest(_CRITERIA_MANIFEST_PATH),
    }


def _render_criteria_study() -> None:
    st.markdown('<div class="industry-section">Critérios, subordinação mínima e monitorabilidade</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Base documental estruturada para regras contratuais extraídas de todos os FIDCs cobertos pela curadoria local. '
        "A camada de features reaproveita a matriz regulatória da aba Estratégia sem contaminar a mediana de subordinação percentual. "
        "A revisão manual altera um overlay persistido e recompõe a base estruturada.</div>",
        unsafe_allow_html=True,
    )
    tables = _load_criteria_tables()
    structured = tables["structured"]
    manifest = tables["manifest"]
    assert isinstance(structured, pd.DataFrame)
    assert isinstance(manifest, dict)
    if structured.empty:
        st.info("Base de critérios ainda não gerada. Rode `python scripts/build_fidc_industry_criteria.py`.")
        return

    reviews = _load_criteria_reviews()
    frame = structured.copy()
    frame["pct_min_num"] = pd.to_numeric(frame.get("pct_min"), errors="coerce")
    frame["score_num"] = pd.to_numeric(frame.get("score_confianca_final"), errors="coerce")
    active = frame[frame.get("ativo_curadoria", pd.Series(True, index=frame.index)).astype(str).str.lower().isin({"true", "1", "sim"})].copy()
    sub = active[active["chave"].eq("subordination_ratio_min")].copy() if "chave" in active.columns else active.iloc[0:0]
    sub_values = sub["pct_min_num"].dropna() if "pct_min_num" in sub.columns else pd.Series(dtype=float)
    quality = manifest.get("quality", {}) if isinstance(manifest, dict) else {}
    cards = [
        _curation_card("Regras estruturadas", _fmt_int(float(len(active))), f"{_fmt_int(float(active['cnpj_fundo'].nunique())) if 'cnpj_fundo' in active else '0'} FIDCs"),
        _curation_card("Features Estratégia", _fmt_int(float(quality.get("feature_rows", 0))) if isinstance(quality, dict) else "0", f"{_fmt_int(float(quality.get('feature_funds', 0)))} FIDCs"),
        _curation_card("Sub mínima mediana", _pct_label(float(sub_values.median()) if not sub_values.empty else None), f"{_fmt_int(float(len(sub)))} regras · {_fmt_int(float(sub['cnpj_fundo'].nunique())) if 'cnpj_fundo' in sub else '0'} FIDCs"),
        _curation_card("IQR sub mínima", f"{_pct_label(float(sub_values.quantile(0.25)) if not sub_values.empty else None)}-{_pct_label(float(sub_values.quantile(0.75)) if not sub_values.empty else None)}", "p25-p75"),
        _curation_card("Monitoráveis", _fmt_int(float(quality.get("monitorable_rows", 0))) if isinstance(quality, dict) else "0", "proxy IME disponível"),
        _curation_card("Parciais", _fmt_int(float(quality.get("partial_rows", 0))) if isinstance(quality, dict) else "0", "exigem leitura/operacional"),
        _curation_card("Revisões", _fmt_int(float(len(reviews))), _CRITERIA_REVIEW_PATH.name),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    tab_sub, tab_heat, tab_base, tab_review, tab_history, tab_manifest = st.tabs(
        ["Sub mínima", "Heatmap", "Base", "Revisão", "Histórico", "Manifesto"]
    )
    with tab_sub:
        if sub.empty:
            st.caption("Nenhuma regra de subordinação mínima na base estruturada.")
        else:
            col_a, col_b = st.columns([0.95, 1.05])
            with col_a:
                plot = sub.dropna(subset=["pct_min_num"]).copy()
                if not plot.empty:
                    plot["pct_label"] = plot["pct_min_num"].map(lambda value: f"{value:.1f}%")
                    chart = (
                        alt.Chart(plot)
                        .mark_bar(color=_ORANGE, cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
                        .encode(
                            x=alt.X("pct_min_num:Q", title="Subordinação mínima (%)", bin=alt.Bin(maxbins=20), axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                            y=alt.Y("count():Q", title="regras", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                            tooltip=[
                                alt.Tooltip("count():Q", title="regras"),
                            ],
                        )
                        .properties(height=280)
                    )
                    st.altair_chart(chart, width="stretch")
                else:
                    st.caption("Percentuais numéricos indisponíveis.")
            with col_b:
                st.markdown("**Subordinação mínima por regra**")
                show = sub.sort_values("pct_min_num", ascending=True).copy()
                keep = ["fundo", "cnpj_fundo", "setor", "segmento", "pct_min", "limite_regra", "monitorabilidade_ime", "documento_origem", "document_date", "score_confianca_final"]
                show = show[[col for col in keep if col in show.columns]].head(80)
                show = show.rename(
                    columns={
                        "fundo": "Fundo",
                        "cnpj_fundo": "CNPJ",
                        "setor": "Setor",
                        "segmento": "Segmento",
                        "pct_min": "Sub mínima",
                        "limite_regra": "Regra",
                        "monitorabilidade_ime": "Monitorabilidade",
                        "documento_origem": "Documento",
                        "document_date": "Data",
                        "score_confianca_final": "Score",
                    }
                )
                st.dataframe(show, hide_index=True, width="stretch")
    with tab_heat:
        data = active.copy()
        if data.empty:
            st.caption("Sem dados ativos.")
        else:
            left, right, top_ctrl = st.columns([0.9, 0.9, 0.6])
            dim_options = {
                "Setor": "setor",
                "Segmento": "segmento",
                "Monitorabilidade": "monitorabilidade_ime",
                "Prioridade": "periodo_prioritario",
            }
            with left:
                row_label = st.selectbox("Linhas", list(dim_options), key="industry_criteria_heat_rows")
            with right:
                metric = st.selectbox("Métrica", ["Regras", "FIDCs", "Sub mínima mediana"], key="industry_criteria_heat_metric")
            with top_ctrl:
                top_n = st.slider("Top", min_value=5, max_value=25, value=14, step=1, key="industry_criteria_heat_top")
            row_col = dim_options[row_label]
            data["linha"] = data.get(row_col, pd.Series("", index=data.index)).fillna("").astype(str).replace("", "n/d")
            data["chave_plot"] = data["chave"].fillna("").astype(str).replace("", "n/d")
            if metric == "FIDCs":
                heat = data.groupby(["linha", "chave_plot"], dropna=False)["cnpj_fundo"].nunique().reset_index(name="valor")
                title = "FIDCs"
                fmt = ",.0f"
            elif metric == "Sub mínima mediana":
                sub_data = data[data["chave"].eq("subordination_ratio_min")].copy()
                heat = sub_data.groupby(["linha", "chave_plot"], dropna=False)["pct_min_num"].median().reset_index(name="valor")
                title = "Sub mínima mediana (%)"
                fmt = ",.1f"
            else:
                heat = data.groupby(["linha", "chave_plot"], dropna=False).size().reset_index(name="valor")
                title = "Regras"
                fmt = ",.0f"
            heat = heat[pd.to_numeric(heat["valor"], errors="coerce").fillna(0).gt(0)].copy()
            if heat.empty:
                st.caption("A combinação selecionada não retornou valores.")
            else:
                row_order = heat.groupby("linha")["valor"].sum().sort_values(ascending=False).head(top_n).index.tolist()
                col_order = heat.groupby("chave_plot")["valor"].sum().sort_values(ascending=False).head(12).index.tolist()
                heat = heat[heat["linha"].isin(row_order) & heat["chave_plot"].isin(col_order)].copy()
                chart = (
                    alt.Chart(heat)
                    .mark_rect(cornerRadius=2)
                    .encode(
                        x=alt.X("chave_plot:N", title=None, sort=col_order, axis=alt.Axis(labelAngle=-35, labelLimit=150)),
                        y=alt.Y("linha:N", title=None, sort=row_order, axis=alt.Axis(labelLimit=220)),
                        color=alt.Color("valor:Q", title=title, scale=alt.Scale(range=["#f7f2ed", _ORANGE])),
                        tooltip=[
                            alt.Tooltip("linha:N", title=row_label),
                            alt.Tooltip("chave_plot:N", title="critério"),
                            alt.Tooltip("valor:Q", title=title, format=fmt),
                        ],
                    )
                    .properties(height=max(300, 26 * len(row_order)))
                )
                st.altair_chart(chart, width="stretch")
    with tab_base:
        data = active.copy()
        filt_a, filt_b, filt_c = st.columns([1.2, 0.9, 0.8])
        with filt_a:
            query = st.text_input("Buscar regra", key="industry_criteria_query", placeholder="fundo, CNPJ, critério, documento")
        with filt_b:
            keys = sorted([value for value in data.get("chave", pd.Series(dtype=str)).fillna("").astype(str).unique() if value])
            selected_keys = st.multiselect("Chave", keys, default=keys, key="industry_criteria_keys")
        with filt_c:
            only_priority = st.checkbox("2025-2026", value=False, key="industry_criteria_priority")
        if selected_keys and "chave" in data.columns:
            data = data[data["chave"].isin(selected_keys)].copy()
        if only_priority and "periodo_prioritario" in data.columns:
            data = data[data["periodo_prioritario"].eq("2025-2026 YTD")].copy()
        if query:
            search_cols = [col for col in ["fundo", "cnpj_fundo", "criterio", "chave", "limite_regra", "documento_origem"] if col in data.columns]
            search = data[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=data.index)
            data = data[search.str.contains(query, case=False, na=False)].copy()
        show = data.sort_values(["periodo_prioritario", "score_num"], ascending=[False, False]).head(300)
        keep = ["fundo", "cnpj_fundo", "setor", "segmento", "criterio", "chave", "fonte_camada", "limite_regra", "pct_min", "monitorabilidade_ime", "documento_origem", "document_date", "status_revisao", "score_confianca_final"]
        st.dataframe(
            show[[col for col in keep if col in show.columns]].rename(
                columns={
                    "fundo": "Fundo",
                    "cnpj_fundo": "CNPJ",
                    "setor": "Setor",
                    "segmento": "Segmento",
                    "criterio": "Critério",
                    "chave": "Chave",
                    "fonte_camada": "Camada",
                    "limite_regra": "Regra",
                    "pct_min": "Pct mín.",
                    "monitorabilidade_ime": "Monitorabilidade",
                    "documento_origem": "Documento",
                    "document_date": "Data",
                    "status_revisao": "Status",
                    "score_confianca_final": "Score",
                }
            ),
            hide_index=True,
            width="stretch",
        )
    with tab_review:
        merged = structured.merge(reviews, on="rule_id", how="left", suffixes=("", "_review"))
        for col in _CRITERIA_REVIEW_COLUMNS:
            if col not in merged.columns:
                merged[col] = ""
        merged["status"] = merged["status"].fillna("").replace("", "pendente")
        merged = merged.sort_values(["periodo_prioritario", "score_confianca_final"], ascending=[True, False]).head(120)
        display = pd.DataFrame(
            {
                "ID": merged["rule_id"],
                "Status": merged["status"],
                "Fundo": merged["fundo"].astype(str).str.slice(0, 72),
                "CNPJ": merged["cnpj_fundo"],
                "Critério auto": merged["criterio"],
                "Chave auto": merged["chave"],
                "Regra auto": merged["limite_regra"].astype(str).str.slice(0, 180),
                "Pct auto": pd.to_numeric(merged["pct_min"], errors="coerce"),
                "Monitor auto": merged["monitorabilidade_ime"],
                "Critério revisado": merged["criterio_revisado"].fillna("").astype(str),
                "Chave revisada": merged["chave_revisada"].fillna("").astype(str),
                "Regra revisada": merged["limite_revisado"].fillna("").astype(str),
                "Pct revisado": pd.to_numeric(merged["pct_min_revisado"], errors="coerce"),
                "Monitor revisado": merged["monitorabilidade_revisada"].fillna("").astype(str),
                "Confiança manual": pd.to_numeric(merged["confianca_manual"], errors="coerce"),
                "Documento": merged["documento_origem"],
                "Data": merged["document_date"],
                "Notas": merged["notas"].fillna("").astype(str),
            }
        )
        edited = st.data_editor(
            display,
            hide_index=True,
            width="stretch",
            height=520,
            disabled=["ID", "Fundo", "CNPJ", "Critério auto", "Chave auto", "Regra auto", "Pct auto", "Monitor auto", "Documento", "Data"],
            column_config={
                "Status": st.column_config.SelectboxColumn(
                    "Status",
                    options=["pendente", "aprovado", "corrigido", "rejeitado"],
                    required=True,
                ),
                "Confiança manual": st.column_config.NumberColumn("Confiança manual", min_value=0.0, max_value=1.0, step=0.05, format="%.2f"),
                "Pct revisado": st.column_config.NumberColumn("Pct revisado", min_value=0.0, step=0.1, format="%.2f"),
            },
            key="industry_criteria_review_editor",
        )
        if st.button("Salvar revisões de critérios", type="primary", key="industry_save_criteria_reviews"):
            edited_reviews = pd.DataFrame(
                {
                    "rule_id": edited["ID"],
                    "status": edited["Status"],
                    "criterio_revisado": edited["Critério revisado"],
                    "chave_revisada": edited["Chave revisada"],
                    "limite_revisado": edited["Regra revisada"],
                    "pct_min_revisado": edited["Pct revisado"],
                    "monitorabilidade_revisada": edited["Monitor revisado"],
                    "confianca_manual": edited["Confiança manual"],
                    "notas": edited["Notas"],
                }
            ).fillna("")
            keep_existing = reviews[~reviews["rule_id"].isin(edited_reviews["rule_id"])].copy() if not reviews.empty else reviews
            updated_reviews = pd.concat([keep_existing, edited_reviews], ignore_index=True)
            audit_events = build_review_audit_events(
                previous=reviews,
                updated=updated_reviews,
                key_column="rule_id",
                review_domain="criteria",
                source="industry_ui",
            )
            audit = append_review_audit_events(audit_events, _CRITERIA_REVIEW_AUDIT_PATH)
            _save_criteria_reviews(updated_reviews)
            structured_saved = _persist_structured_criteria(updated_reviews)
            _load_criteria_tables.clear()
            st.success(
                f"Revisões salvas em `{_CRITERIA_REVIEW_PATH}` e base recomposta "
                f"em `{_CRITERIA_STRUCTURED_PATH.name}` ({len(structured_saved):,} regras). "
                f"Histórico: {len(audit_events):,} eventos novos, {len(audit):,} eventos no total."
            )
    with tab_history:
        _render_review_audit(
            _CRITERIA_REVIEW_AUDIT_PATH,
            empty_label="Ainda não há histórico de alterações em critérios. O primeiro salvamento com mudança material cria o ledger.",
        )
    with tab_manifest:
        if manifest:
            st.download_button(
                "Baixar manifesto",
                data=json.dumps(manifest, ensure_ascii=False, indent=2),
                file_name="industry_criteria_manifest.json",
                mime="application/json",
            )
            st.json(manifest)
        else:
            st.caption("Manifesto de critérios não encontrado.")


def _render_cedente_review_workbench() -> None:
    st.markdown('<div class="industry-section">Cedentes, sacados e revisão manual</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Mesa de curadoria sobre todos os FIDCs cobertos pelo SQLite regulatório. '
        "A extração automática fica ao lado dos campos revisáveis; o arquivo salvo vira trilha auditável mês a mês.</div>",
        unsafe_allow_html=True,
    )

    candidates = _load_cedente_candidates()
    if candidates.empty:
        st.info("Ainda não há candidatos de cedente/sacado no SQLite regulatório.")
        return

    reviews = _load_cedente_reviews()
    frame = candidates.merge(reviews, on="review_id", how="left")
    for col in _CEDENTE_REVIEW_COLUMNS:
        if col not in frame.columns:
            frame[col] = ""
    frame["status"] = frame["status"].fillna("").replace("", "pendente")
    frame["score_confianca"] = pd.to_numeric(frame["score_confianca"], errors="coerce").fillna(0)
    structured = _build_structured_cedentes(candidates, reviews)
    snapshot_tables = _load_fund_snapshot_tables()
    snapshot = snapshot_tables.get("snapshot", pd.DataFrame())
    signal_focus = _cedente_signal_focus_frame(snapshot if isinstance(snapshot, pd.DataFrame) else pd.DataFrame())
    if not signal_focus.empty:
        frame = frame.merge(signal_focus, on="cnpj_fundo", how="left")
    else:
        for col in [
            "pl_sinal_brl",
            "signal_admin_nome",
            "signal_segmento_principal",
            "participant_signal_rows",
            "participant_signal_keys",
            "participant_signal_evidence",
            "criteria_documentos",
            "document_chunk_ids",
            "latest_regulamento_date",
        ]:
            if col not in frame.columns:
                frame[col] = ""
    focus_cnpjs = set(signal_focus["cnpj_fundo"].astype(str)) if not signal_focus.empty else set()

    type_labels = {
        "cedente_originador": "cedente/originador",
        "sacado_devedor": "sacado/devedor",
        "consultora": "consultora",
    }
    cards = [
        _curation_card("Candidatos automáticos", _fmt_int(float(len(frame))), "deduplicados por fundo/participante"),
        _curation_card("Base estruturada", _fmt_int(float(len(structured))), "linhas reutilizáveis"),
        _curation_card("FIDCs com evidência", _fmt_int(float(structured["cnpj_fundo"].nunique() if not structured.empty else frame["cnpj_fundo"].nunique())), "universo regulatório"),
        _curation_card(
            "Cedente/originador",
            _fmt_int(float(frame[frame["participant_type"].eq("cedente_originador")]["cnpj_fundo"].nunique())),
            "FIDCs com menção",
        ),
        _curation_card(
            "Sacado/devedor",
            _fmt_int(float(frame[frame["participant_type"].eq("sacado_devedor")]["cnpj_fundo"].nunique())),
            "FIDCs com menção",
        ),
        _curation_card("Sinal sem participante", _fmt_int(float(len(focus_cnpjs))), "prioridade de extração"),
        _curation_card("Revisões salvas", _fmt_int(float(len(reviews))), _CEDENTE_REVIEW_PATH.name),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    filter_a, filter_b, filter_c, filter_d, filter_e = st.columns([1.2, 0.78, 0.78, 0.65, 0.78])
    with filter_a:
        query = st.text_input("Buscar", key="industry_cedente_query", placeholder="fundo, CNPJ, participante ou evidência")
    with filter_b:
        types = sorted(frame["participant_type"].dropna().astype(str).unique())
        selected_types = st.multiselect(
            "Tipo",
            types,
            default=types,
            format_func=lambda value: type_labels.get(value, value),
            key="industry_cedente_types",
        )
    with filter_c:
        statuses = ["pendente", "aprovado", "corrigido", "rejeitado"]
        selected_statuses = st.multiselect("Status", statuses, default=statuses, key="industry_cedente_status")
    with filter_d:
        min_score = st.slider("Score mín.", 0.0, 0.95, 0.55, 0.05, key="industry_cedente_score")
    with filter_e:
        only_signal_focus = st.checkbox("Sinal sem participante", value=False, key="industry_cedente_signal_focus")

    score_mask = frame["score_confianca"].ge(min_score)
    if only_signal_focus:
        score_mask = pd.Series(True, index=frame.index)
    filtered = frame[frame["participant_type"].isin(selected_types) & frame["status"].isin(selected_statuses) & score_mask].copy()
    if only_signal_focus:
        filtered = filtered[filtered["cnpj_fundo"].astype(str).isin(focus_cnpjs)].copy()
    if query:
        search = (
            filtered["fund_name"].astype(str)
            + " "
            + filtered["cnpj_fundo"].astype(str)
            + " "
            + filtered["participante_extraido"].astype(str)
            + " "
            + filtered["participant_cnpj_candidate"].astype(str)
            + " "
            + filtered["evidence_context"].astype(str)
            + " "
            + filtered.get("participant_signal_evidence", pd.Series("", index=filtered.index)).astype(str)
        )
        filtered = filtered[search.str.contains(query, case=False, na=False)].copy()

    if only_signal_focus and "pl_sinal_brl" in filtered.columns:
        filtered["pl_sinal_num"] = pd.to_numeric(filtered["pl_sinal_brl"], errors="coerce").fillna(0.0)
        filtered = filtered.sort_values(["pl_sinal_num", "score_confianca", "cnpj_fundo"], ascending=[False, False, True])
    else:
        filtered = filtered.sort_values(["score_confianca", "cnpj_fundo"], ascending=[False, True])
    filtered = filtered.head(120)
    if filtered.empty:
        st.caption("Nenhum candidato passou pelos filtros.")
        return

    display = pd.DataFrame(
        {
            "ID": filtered["review_id"],
            "Status": filtered["status"],
            "Tipo": filtered["participant_type"].replace(type_labels),
            "Fundo": filtered["fund_name"].astype(str).str.slice(0, 78),
            "CNPJ fundo": filtered["cnpj_fundo"],
            "Participante extraído": filtered["participante_extraido"],
            "CNPJ extraído": filtered["participant_cnpj_candidate"].fillna("").astype(str),
            "Nome revisado": filtered["nome_revisado"].fillna("").astype(str),
            "Nome fantasia": filtered["nome_fantasia_revisado"].fillna("").astype(str),
            "CNPJ revisado": filtered["cnpj_revisado"].fillna("").astype(str),
            "Grupo econômico": filtered["grupo_economico"].fillna("").astype(str),
            "Setor revisado": filtered["setor_revisado"].fillna("").astype(str),
            "Segmento revisado": filtered["segmento_revisado"].fillna("").astype(str),
            "Confiança manual": pd.to_numeric(filtered["confianca_manual"], errors="coerce"),
            "Score auto": filtered["score_confianca"].round(2),
            "Evidências": filtered["evidencias_agrupadas"],
            "PL sinal": pd.to_numeric(filtered.get("pl_sinal_brl", pd.Series(0, index=filtered.index)), errors="coerce").fillna(0.0),
            "Sinal regulatório": filtered.get("participant_signal_keys", pd.Series("", index=filtered.index)).fillna("").astype(str),
            "Evidência sinal": filtered.get("participant_signal_evidence", pd.Series("", index=filtered.index)).fillna("").astype(str).str.slice(0, 240),
            "Chunks sinal": filtered.get("document_chunk_ids", pd.Series("", index=filtered.index)).fillna("").astype(str),
            "Documento": filtered["documento_origem"],
            "Página": filtered["pagina"],
            "Evidência": filtered["evidence_context"].astype(str).str.slice(0, 240),
            "Notas": filtered["notas"].fillna("").astype(str),
        }
    )
    display["PL sinal"] = display["PL sinal"].map(lambda value: _fmt_bi(float(value), 1) if float(value or 0) else "")
    disabled_cols = [
        "ID",
        "Tipo",
        "Fundo",
        "CNPJ fundo",
        "Participante extraído",
        "CNPJ extraído",
        "Score auto",
        "Evidências",
        "PL sinal",
        "Sinal regulatório",
        "Evidência sinal",
        "Chunks sinal",
        "Documento",
        "Página",
        "Evidência",
    ]
    edited = st.data_editor(
        display,
        hide_index=True,
        width="stretch",
        height=520,
        disabled=disabled_cols,
        column_config={
            "Status": st.column_config.SelectboxColumn(
                "Status",
                options=["pendente", "aprovado", "corrigido", "rejeitado"],
                required=True,
            ),
            "Confiança manual": st.column_config.NumberColumn(
                "Confiança manual",
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                format="%.2f",
            ),
            "Evidência": st.column_config.TextColumn("Evidência", width="large"),
        },
        key="industry_cedente_review_editor",
    )

    if st.button("Salvar revisões da página filtrada", type="primary", key="industry_save_cedente_reviews"):
        edited_reviews = pd.DataFrame(
            {
                "review_id": edited["ID"],
                "status": edited["Status"],
                "nome_revisado": edited["Nome revisado"],
                "nome_fantasia_revisado": edited["Nome fantasia"],
                "cnpj_revisado": edited["CNPJ revisado"],
                "grupo_economico": edited["Grupo econômico"],
                "setor_revisado": edited["Setor revisado"],
                "segmento_revisado": edited["Segmento revisado"],
                "confianca_manual": edited["Confiança manual"],
                "notas": edited["Notas"],
            }
        )
        edited_reviews = edited_reviews.fillna("")
        keep_existing = reviews[~reviews["review_id"].isin(edited_reviews["review_id"])].copy()
        updated_reviews = pd.concat([keep_existing, edited_reviews], ignore_index=True)
        audit_events = build_review_audit_events(
            previous=reviews,
            updated=updated_reviews,
            key_column="review_id",
            review_domain="cedente",
            source="industry_ui",
        )
        audit = append_review_audit_events(audit_events, _CEDENTE_REVIEW_AUDIT_PATH)
        _save_cedente_reviews(updated_reviews)
        structured_saved = _persist_structured_cedentes(candidates, updated_reviews)
        st.success(
            f"Revisões salvas em `{_CEDENTE_REVIEW_PATH}` e base estruturada atualizada "
            f"em `{_CEDENTE_STRUCTURED_PATH.name}` ({len(structured_saved):,} linhas). "
            f"Histórico: {len(audit_events):,} eventos novos, {len(audit):,} eventos no total."
        )

    st.markdown("**Histórico de revisões**")
    _render_review_audit(
        _CEDENTE_REVIEW_AUDIT_PATH,
        empty_label="Ainda não há histórico de alterações em cedentes. O primeiro salvamento com mudança material cria o ledger.",
    )


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _render_industry_deep_dive(vehicle: pd.DataFrame | None, comp: str) -> None:
    st.markdown('<div class="industry-section">Deep Dive por dimensão</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Exploração reutilizável da base estruturada: escolha uma dimensão, '
        "um valor e uma janela; o painel recompõe PL, fluxo, veículos, segmentos e evidências sem regra específica.</div>",
        unsafe_allow_html=True,
    )
    if vehicle is None or vehicle.empty:
        st.info("A base granular `vehicle_monthly.csv.gz` ainda não está disponível para Deep Dive.")
        return

    fallback_dimensions = {
        "Administrador": "admin_nome",
        "Gestor": "gestor_nome",
        "Custodiante": "custodiante_nome",
        "Cedente/sacado": "razao_social",
        "Grupo econômico": "grupo_economico",
        "Tipo participante": "tipo_participante",
        "Segmento": "segmento_principal",
        "Subsegmento financeiro": "segmento_financeiro_principal",
        "FIC-FIDC": "is_fic_fidc",
        "Condomínio": "condominio",
        "Público-alvo": "publico_alvo",
        "Segmento Estratégia": "segmento_estrategia",
        "Subsegmento Estratégia": "subsegmento_estrategia",
        "Status snapshot": "snapshot_status",
        "Camadas evidência": "camadas_com_evidencia",
        "Emissão 25-26": "tem_emissao_2025_2026",
        "Faixa sub mín.": "sub_min_bucket",
        "Tem sub mín.": "tem_sub_minima",
        "Documento local": "tem_documento_local",
        "Indexador": "indexadores",
        "Tipo de cota": "tipo_cotas",
        "Classe documento": "document_classes",
        "Critério": "criteria_keys",
        "Chunk docs": "document_chunk_ids",
    }
    catalog_tables = _load_dimension_catalog_tables()
    catalog = catalog_tables["catalog"]
    catalog_manifest = catalog_tables["manifest"]
    assert isinstance(catalog, pd.DataFrame)
    assert isinstance(catalog_manifest, dict)
    catalog_dimensions = _dimension_catalog_options(catalog)
    use_catalog = bool(catalog_dimensions)
    monthly_tables = _load_dimension_monthly_tables() if use_catalog else {"monthly": pd.DataFrame(), "manifest": {}}
    dimension_monthly = monthly_tables["monthly"]
    dimension_value_atlas = monthly_tables.get("atlas", pd.DataFrame())
    dimension_monthly_manifest = monthly_tables["manifest"]
    assert isinstance(dimension_monthly, pd.DataFrame)
    assert isinstance(dimension_value_atlas, pd.DataFrame)
    assert isinstance(dimension_monthly_manifest, dict)
    profile_tables = _load_dimension_profile_tables() if use_catalog else {"profiles": pd.DataFrame(), "manifest": {}}
    dimension_profiles = profile_tables["profiles"]
    dimension_profile_manifest = profile_tables["manifest"]
    assert isinstance(dimension_profiles, pd.DataFrame)
    assert isinstance(dimension_profile_manifest, dict)
    dossier_tables = _load_dimension_dossier_tables() if use_catalog else {"dossiers": pd.DataFrame(), "manifest": {}}
    dimension_dossiers = dossier_tables["dossiers"]
    dimension_dossier_manifest = dossier_tables["manifest"]
    assert isinstance(dimension_dossiers, pd.DataFrame)
    assert isinstance(dimension_dossier_manifest, dict)
    dimensions = catalog_dimensions if use_catalog else fallback_dimensions
    ctrl_a, ctrl_b, ctrl_c = st.columns([0.9, 0.9, 1.2])
    with ctrl_a:
        dimension_label = st.selectbox("Dimensão", list(dimensions), key="industry_deep_dimension")
    with ctrl_b:
        period = st.selectbox(
            "Janela",
            ["Última competência", "Últimos 12 meses", "2025 até data-base", "Histórico completo"],
            index=1,
            key="industry_deep_period",
        )
    with ctrl_c:
        query = st.text_input("Buscar valor", key="industry_deep_query", placeholder="nome, CNPJ, segmento ou participante")

    dim_col = dimensions[dimension_label]
    if use_catalog and not dimension_dossiers.empty:
        dossier_view = dimension_dossiers[
            dimension_dossiers.get("dimension_id", pd.Series("", index=dimension_dossiers.index)).astype(str).eq(str(dim_col))
        ].copy()
        if not dossier_view.empty:
            dossier_row = dossier_view.iloc[0]
            profile_rows = float(pd.to_numeric(pd.Series([dossier_row.get("profile_rows")]), errors="coerce").fillna(0).iloc[0])
            presets = float(pd.to_numeric(pd.Series([dossier_row.get("heatmap_presets")]), errors="coerce").fillna(0).iloc[0])
            presets_ok = float(pd.to_numeric(pd.Series([dossier_row.get("heatmap_presets_ok")]), errors="coerce").fillna(0).iloc[0])
            traceability_cov = pd.to_numeric(pd.Series([dossier_row.get("traceability_coverage")]), errors="coerce").iloc[0]
            st.markdown("**Dossiê materializado da dimensão**")
            dossier_cards = [
                _curation_card("Status", _status_badge_text(dossier_row.get("status_dossie")), str(dossier_row.get("status_reasons") or "sem pendência")),
                _curation_card("Valores", _fmt_int(float(dossier_row.get("atlas_values") or 0)), f"{_fmt_int(float(dossier_row.get('atlas_values_with_pl') or 0))} com PL"),
                _curation_card("Rastreabilidade", _fmt_pct(float(traceability_cov)) if pd.notna(traceability_cov) else "n/d", "fonte ou método"),
                _curation_card("Perfis", _fmt_int(profile_rows), f"{_fmt_int(float(dossier_row.get('profile_target_dimensions') or 0))} quebras"),
                _curation_card("Heatmaps", f"{_fmt_int(presets_ok)}/{_fmt_int(presets)}", "presets ligados"),
            ]
            st.markdown(f'<div class="industry-kpi-grid">{"".join(dossier_cards)}</div>', unsafe_allow_html=True)
            st.dataframe(_format_dimension_dossiers(dossier_view), hide_index=True, width="stretch")
            generated_at = dimension_dossier_manifest.get("generated_at_utc", "")
            source_note = f"Fonte: `{_DIMENSION_DOSSIER_PATH.name}`"
            if generated_at:
                source_note += f" · gerado em {generated_at}"
            st.caption(source_note)
    frame = _period_filter(vehicle, comp, period)
    cedentes = pd.DataFrame()
    if use_catalog:
        frame = _catalog_deep_dive_frame(frame, catalog, dim_col)
    else:
        cedentes = _build_structured_cedentes()
        snapshot_tables = _load_fund_snapshot_tables()
        snapshot = snapshot_tables["snapshot"]
        assert isinstance(snapshot, pd.DataFrame)
        frame = _heatmap_base_frame(frame, cedentes, snapshot, dim_col, dim_col)
    if frame.empty:
        st.caption("Sem dados para a dimensão/janela selecionada.")
        return

    frame = frame.copy()
    if not use_catalog:
        frame["valor_dimensao"] = _dimension_series(frame, dim_col)
    frame = frame[frame["valor_dimensao"] != "n/d"].copy()
    if query:
        frame = frame[frame["valor_dimensao"].astype(str).str.contains(query, case=False, na=False)].copy()
    if frame.empty:
        st.caption("Nenhum valor passou pela busca.")
        return

    frame["pl_metric"] = _numeric_column(frame, "pl") * frame["_metric_weight"]
    frame["captacao_metric"] = _numeric_column(frame, "captacao_liquida") * frame["_metric_weight"]
    frame["carteira_metric"] = _numeric_column(frame, "carteira_dc") * frame["_metric_weight"]
    frame["inad_metric"] = _numeric_column(frame, "dc_inadimplentes_ajustado") * frame["_metric_weight"]
    fund_id = "cnpj_fundo" if "cnpj_fundo" in frame.columns else "cnpj"
    latest_comp = sorted(frame["competencia"].dropna().astype(str).unique())[-1]
    current = frame[frame["competencia"].eq(latest_comp)].copy()
    summary = (
        current.groupby("valor_dimensao", dropna=False)
        .agg(
            PL=("pl_metric", "sum"),
            Veículos=("cnpj", "nunique"),
            Fundos=(fund_id, "nunique"),
            Carteira=("carteira_metric", "sum"),
            Inad=("inad_metric", "sum"),
        )
        .reset_index()
    )
    flow_summary = (
        frame.groupby("valor_dimensao", dropna=False)["captacao_metric"]
        .sum()
        .reset_index(name="Captacao")
    )
    summary = summary.merge(flow_summary, on="valor_dimensao", how="left")
    summary["_rank"] = summary["PL"].abs() + summary["Captacao"].abs()
    summary = summary.sort_values("_rank", ascending=False).head(80)
    options = summary["valor_dimensao"].astype(str).tolist()
    if not options:
        st.caption("Sem valores ranqueáveis para a dimensão.")
        return
    if use_catalog and not dimension_value_atlas.empty:
        atlas_view = dimension_value_atlas[
            dimension_value_atlas.get("dimension_id", pd.Series("", index=dimension_value_atlas.index)).astype(str).eq(str(dim_col))
        ].copy()
        if query and not atlas_view.empty:
            atlas_view = atlas_view[
                atlas_view.get("dimension_value", pd.Series("", index=atlas_view.index))
                .astype(str)
                .str.contains(query, case=False, na=False)
            ].copy()
        if not atlas_view.empty:
            atlas_view["rank_score_num"] = pd.to_numeric(atlas_view.get("rank_score"), errors="coerce").fillna(0.0)
            atlas_view = atlas_view.sort_values(["rank_score_num", "links_com_fonte", "dimension_value"], ascending=[False, False, True]).drop(
                columns=["rank_score_num"], errors="ignore"
            )
            st.markdown("**Atlas materializado da dimensão**")
            atlas_cards = [
                _curation_card("Valores", _fmt_int(float(len(atlas_view))), dimension_label),
                _curation_card(
                    "PL top 20",
                    _fmt_bi(float(pd.to_numeric(atlas_view.head(20).get("pl_atual_brl"), errors="coerce").fillna(0).sum()), 1),
                    str(atlas_view.get("competencia_atual", pd.Series([""])).iloc[0]),
                ),
                _curation_card(
                    "Captação 12m top 20",
                    _fmt_signed_bi(
                        float(pd.to_numeric(atlas_view.head(20).get("captacao_12m_brl"), errors="coerce").fillna(0).sum()),
                        1,
                    ),
                    "atlas",
                ),
                _curation_card(
                    "Com documento",
                    _fmt_pct(
                        float(pd.to_numeric(atlas_view.get("links_com_fonte"), errors="coerce").fillna(0).sum())
                        / float(pd.to_numeric(atlas_view.get("links_catalogo"), errors="coerce").fillna(0).sum())
                    )
                    if float(pd.to_numeric(atlas_view.get("links_catalogo"), errors="coerce").fillna(0).sum())
                    else "n/d",
                    "documento regulatório",
                ),
            ]
            st.markdown(f'<div class="industry-kpi-grid">{"".join(atlas_cards)}</div>', unsafe_allow_html=True)
            st.dataframe(_format_dimension_value_atlas(atlas_view.head(80)), hide_index=True, width="stretch")
            st.download_button(
                "Baixar atlas da dimensão",
                data=atlas_view.drop(columns=["rank_score_num"], errors="ignore").to_csv(index=False).encode("utf-8"),
                file_name=f"industry_deep_dive_{dim_col}_atlas.csv",
                mime="text/csv",
                key=f"industry_deep_atlas_download_{dim_col}",
            )
    if use_catalog and not dimension_monthly.empty:
        radar = _dimension_radar_frame(dimension_monthly, dimension_id=dim_col, comp=comp, period=period)
        if query and not radar.empty:
            radar = radar[radar["dimension_value"].astype(str).str.contains(query, case=False, na=False)].copy()
        if not radar.empty:
            st.markdown("**Radar da dimensão**")
            total_catalog_links = float(pd.to_numeric(radar["links_catalogo"], errors="coerce").fillna(0.0).sum())
            total_source_links = float(pd.to_numeric(radar["links_com_fonte"], errors="coerce").fillna(0.0).sum())
            top_pl = radar.sort_values("pl_atual_brl", ascending=False).head(20)
            radar_cards = [
                _curation_card("Valores", _fmt_int(float(len(radar))), dimension_label),
                _curation_card(
                    "PL top 20",
                    _fmt_bi(float(top_pl["pl_atual_brl"].sum()), 1),
                    str(radar["competencia_atual"].iloc[0]),
                ),
                _curation_card(
                    "Captação top 20",
                    _fmt_signed_bi(float(radar.head(20)["captacao_janela_brl"].sum()), 1),
                    period,
                ),
                _curation_card(
                    "Com documento",
                    _fmt_pct(total_source_links / total_catalog_links) if total_catalog_links else "n/d",
                    "documento regulatório",
                ),
            ]
            st.markdown(f'<div class="industry-kpi-grid">{"".join(radar_cards)}</div>', unsafe_allow_html=True)
            radar_plot = radar.sort_values("pl_atual_brl", ascending=False).head(18).copy()
            radar_plot["pl_bi"] = radar_plot["pl_atual_brl"] / 1e9
            st.altair_chart(
                alt.Chart(radar_plot)
                .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
                .encode(
                    x=alt.X("pl_bi:Q", title="PL atual (R$ bi)", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    y=alt.Y("dimension_value:N", title=None, sort="-x", axis=alt.Axis(labelLimit=300)),
                    tooltip=[
                        alt.Tooltip("dimension_value:N", title=dimension_label),
                        alt.Tooltip("pl_bi:Q", title="PL R$ bi", format=",.2f"),
                        alt.Tooltip("captacao_janela_brl:Q", title="captação janela", format=",.0f"),
                        alt.Tooltip("pl_growth_12m_pct:Q", title="crescimento 12m", format=".1%"),
                        alt.Tooltip("fundos_atuais:Q", title="fundos", format=",.0f"),
                    ],
                )
                .properties(height=max(260, 24 * len(radar_plot))),
                width="stretch",
            )
            st.dataframe(_format_dimension_radar(radar.head(80)), hide_index=True, width="stretch")
            st.download_button(
                "Baixar radar da dimensão",
                data=radar.drop(columns=["rank_score"], errors="ignore").to_csv(index=False).encode("utf-8"),
                file_name=f"industry_deep_dive_{dim_col}_radar.csv",
                mime="text/csv",
                key=f"industry_deep_radar_download_{dim_col}",
            )
    selected_value = st.selectbox("Valor", options, key="industry_deep_value")
    selected = frame[frame["valor_dimensao"].eq(selected_value)].copy()
    selected_current = current[current["valor_dimensao"].eq(selected_value)].copy()
    monthly = pd.DataFrame()
    uses_dimension_monthly = False
    if use_catalog and not dimension_monthly.empty:
        monthly = _dimension_monthly_for_value(
            dimension_monthly,
            dimension_id=dim_col,
            selected_value=str(selected_value),
            comp=comp,
            period=period,
        )
        uses_dimension_monthly = not monthly.empty

    if uses_dimension_monthly:
        latest_comp = sorted(monthly["competencia"].dropna().astype(str).unique())[-1]
        current_monthly = monthly[monthly["competencia"].eq(latest_comp)].iloc[-1]
        total_pl = float(current_monthly["pl"])
        total_capt = float(monthly["captacao"].sum())
        funds = float(current_monthly["fundos"])
        vehicles = float(current_monthly["veiculos"])
        carteira = float(current_monthly["carteira"])
        inad = float(current_monthly["inad"])
    else:
        total_pl = float(selected_current["pl_metric"].sum())
        total_capt = float(selected["captacao_metric"].sum())
        funds = float(selected_current[fund_id].nunique())
        vehicles = float(selected_current["cnpj"].nunique())
        carteira = float(selected_current["carteira_metric"].sum())
        inad = float(selected_current["inad_metric"].sum())
    sub_med = _numeric_column(selected_current, "subordinacao_pct").median()
    cards = [
        _curation_card("PL atual", _fmt_bi(total_pl, 1), latest_comp),
        _curation_card("Captação líquida", _fmt_signed_bi(total_capt, 1), period),
        _curation_card("Fundos", _fmt_int(float(funds)), f"{_fmt_int(float(vehicles))} veículos"),
        _curation_card("Carteira DC", _fmt_bi(carteira, 1), f"Inad. ajustada {_fmt_pct(inad / carteira) if carteira else 'n/d'}"),
        _curation_card("Sub mediana", _pct_label(sub_med * 100 if pd.notna(sub_med) else None), "observada no IME"),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    if use_catalog:
        snapshot_tables = _load_fund_snapshot_tables()
        snapshot = snapshot_tables["snapshot"]
        assert isinstance(snapshot, pd.DataFrame)
        value_snapshot = _dimension_value_snapshot_frame(catalog, snapshot, dim_col, str(selected_value))
        if not value_snapshot.empty:
            value_snapshot = _apply_snapshot_gap_actions(value_snapshot, _load_snapshot_gap_actions())
            with_gap = value_snapshot[pd.to_numeric(value_snapshot.get("gap_count"), errors="coerce").fillna(0).gt(0)]
            priority_gap = with_gap[
                with_gap.get("priority_2025_2026", pd.Series(False, index=with_gap.index)).astype(bool)
            ]
            dimension_links = pd.to_numeric(
                value_snapshot.get("dimension_links", pd.Series(0.0, index=value_snapshot.index)),
                errors="coerce",
            ).fillna(0.0)
            evidence_links = float(dimension_links.sum())
            curated_flags = value_snapshot.get("dimension_curated", pd.Series(False, index=value_snapshot.index)).astype(bool)
            curated_links = float(dimension_links[curated_flags].sum())
            st.markdown("**Curadoria do valor selecionado**")
            curation_cards = [
                _curation_card("FIDCs ligados", _fmt_int(float(len(value_snapshot))), "snapshot estruturado"),
                _curation_card("Com lacuna", _fmt_int(float(len(with_gap))), _fmt_bi(float(with_gap.get("pl", pd.Series(dtype=float)).sum()), 1)),
                _curation_card("Prioridade 25-26", _fmt_int(float(len(priority_gap))), "lacunas recentes"),
                _curation_card("Links de evidência", _fmt_int(evidence_links), f"{_fmt_int(curated_links)} curados"),
            ]
            st.markdown(f'<div class="industry-kpi-grid">{"".join(curation_cards)}</div>', unsafe_allow_html=True)
            st.dataframe(_format_dimension_value_snapshot(value_snapshot.head(120)), hide_index=True, width="stretch")
            st.download_button(
                "Baixar curadoria do valor",
                data=value_snapshot.to_csv(index=False).encode("utf-8"),
                file_name=f"industry_deep_dive_{dim_col}_curadoria.csv",
                mime="text/csv",
                key=f"industry_deep_value_snapshot_download_{dim_col}",
            )
            st.caption("Curadoria combina catálogo dimensional, snapshot por FIDC, lacunas e overlay de acompanhamento manual quando existir.")

    if not uses_dimension_monthly:
        monthly = (
            selected.groupby("competencia", dropna=False)
            .agg(
                pl=("pl_metric", "sum"),
                captacao=("captacao_metric", "sum"),
                veiculos=("cnpj", "nunique"),
                fundos=(fund_id, "nunique"),
                carteira=("carteira_metric", "sum"),
                inad=("inad_metric", "sum"),
            )
            .reset_index()
            .sort_values("competencia")
        )
        monthly["mes"] = pd.to_datetime(monthly["competencia"] + "-01")
        monthly["pl_bi"] = monthly["pl"] / 1e9
        monthly["captacao_bi"] = monthly["captacao"] / 1e9
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**PL e fundos no tempo**")
        line = (
            alt.Chart(monthly)
            .mark_line(color=_ORANGE, strokeWidth=2)
            .encode(
                x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False)),
                y=alt.Y("pl_bi:Q", title="PL (R$ bi)", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                tooltip=[
                    alt.Tooltip("competencia:N", title="competência"),
                    alt.Tooltip("pl_bi:Q", title="PL R$ bi", format=",.2f"),
                    alt.Tooltip("fundos:Q", title="fundos"),
                ],
            )
            .properties(height=260)
        )
        st.altair_chart(line, width="stretch")
    with col_b:
        st.markdown("**Captação líquida mensal**")
        bars = (
            alt.Chart(monthly)
            .mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
            .encode(
                x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False)),
                y=alt.Y("captacao_bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                color=alt.condition("datum.captacao_bi >= 0", alt.value(_ORANGE), alt.value(_BLACK)),
                tooltip=[
                    alt.Tooltip("competencia:N", title="competência"),
                    alt.Tooltip("captacao_bi:Q", title="captação R$ bi", format=",.2f"),
                ],
            )
            .properties(height=260)
        )
        st.altair_chart(bars, width="stretch")

    col_c, col_d = st.columns([0.95, 1.05])
    with col_c:
        st.markdown("**Mix por segmento na competência atual**")
        if "segmento_principal" in selected_current.columns:
            mix = (
                selected_current.groupby("segmento_principal", dropna=False)["pl_metric"]
                .sum()
                .reset_index(name="PL")
                .sort_values("PL", ascending=False)
                .head(12)
            )
            mix["segmento_principal"] = mix["segmento_principal"].fillna("").replace("", "n/d")
            mix["PL_bi"] = mix["PL"] / 1e9
            st.altair_chart(
                alt.Chart(mix)
                .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
                .encode(
                    x=alt.X("PL_bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    y=alt.Y("segmento_principal:N", title=None, sort="-x"),
                    tooltip=[
                        alt.Tooltip("segmento_principal:N", title="segmento"),
                        alt.Tooltip("PL_bi:Q", title="PL R$ bi", format=",.2f"),
                    ],
                )
                .properties(height=280),
                width="stretch",
            )
        else:
            st.caption("Segmento não disponível na base granular.")
    with col_d:
        st.markdown("**Top veículos/fundos**")
        table = selected_current.sort_values("pl_metric", ascending=False).head(30).copy()
        show = _format_vehicle_table(table)
        st.dataframe(show, hide_index=True, width="stretch")

    if use_catalog and not dimension_profiles.empty:
        profile = dimension_profiles[
            dimension_profiles.get("source_dimension_id", pd.Series("", index=dimension_profiles.index)).astype(str).eq(str(dim_col))
            & dimension_profiles.get("source_dimension_value", pd.Series("", index=dimension_profiles.index)).astype(str).eq(str(selected_value))
        ].copy()
        if not profile.empty:
            st.markdown("**Perfil cruzado estruturado**")
            option_rows = (
                profile[["target_dimension_label", "target_dimension_id"]]
                .drop_duplicates()
                .sort_values("target_dimension_label")
            )
            target_options = {
                str(row["target_dimension_label"]): str(row["target_dimension_id"])
                for _, row in option_rows.iterrows()
                if str(row["target_dimension_label"]).strip()
            }
            default_label = next(
                (
                    label
                    for label in ["Segmento", "Administrador", "Cedente/sacado", "Critério", "Indexador"]
                    if label in target_options and target_options[label] != str(dim_col)
                ),
                next(iter(target_options), ""),
            )
            metric_options = {
                "PL": "pl_brl",
                "Emissões 24-26": "issuance_2024_2026_brl",
                "Fundos eq.": "funds_equiv",
                "Documentos": "document_rows_equiv",
                "Cedentes": "cedente_rows_equiv",
                "Critérios": "criteria_rows_equiv",
            }
            ctrl_profile_a, ctrl_profile_b = st.columns([1.0, 0.8])
            with ctrl_profile_a:
                target_label = st.selectbox(
                    "Quebra",
                    list(target_options),
                    index=list(target_options).index(default_label) if default_label in target_options else 0,
                    key="industry_deep_profile_target",
                )
            with ctrl_profile_b:
                profile_metric_label = st.selectbox(
                    "Métrica do perfil",
                    list(metric_options),
                    key="industry_deep_profile_metric",
                )
            target_id = target_options[target_label]
            metric_col = metric_options[profile_metric_label]
            breakdown = profile[profile["target_dimension_id"].astype(str).eq(target_id)].copy()
            breakdown[metric_col] = pd.to_numeric(breakdown.get(metric_col), errors="coerce").fillna(0.0)
            breakdown = breakdown.sort_values(metric_col, ascending=False).head(20)
            if not breakdown.empty:
                value_col = "Valor"
                chart_data = breakdown[["target_dimension_value", metric_col]].rename(
                    columns={"target_dimension_value": value_col, metric_col: "Métrica"}
                )
                chart_data["Métrica bi"] = chart_data["Métrica"] / 1e9 if metric_col.endswith("_brl") else chart_data["Métrica"]
                axis_title = "R$ bi" if metric_col.endswith("_brl") else profile_metric_label
                st.altair_chart(
                    alt.Chart(chart_data)
                    .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
                    .encode(
                        x=alt.X("Métrica bi:Q", title=axis_title, axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                        y=alt.Y(f"{value_col}:N", title=None, sort="-x"),
                        tooltip=[
                            alt.Tooltip(f"{value_col}:N", title=target_label),
                            alt.Tooltip("Métrica bi:Q", title=axis_title, format=",.2f"),
                        ],
                    )
                    .properties(height=320),
                    width="stretch",
                )
                table_profile = breakdown[
                    [
                        "target_dimension_value",
                        "pl_brl",
                        "issuance_2024_2026_brl",
                        "funds_equiv",
                        "funds_unique",
                        "document_rows_equiv",
                        "cedente_rows_equiv",
                        "criteria_rows_equiv",
                        "curated_links",
                        "source_document_links",
                    ]
                ].rename(
                    columns={
                        "target_dimension_value": target_label,
                        "pl_brl": "PL",
                        "issuance_2024_2026_brl": "Emissões 24-26",
                        "funds_equiv": "Fundos eq.",
                        "funds_unique": "Fundos únicos",
                        "document_rows_equiv": "Docs",
                        "cedente_rows_equiv": "Cedentes",
                        "criteria_rows_equiv": "Critérios",
                        "curated_links": "Links curados",
                        "source_document_links": "Links com fonte",
                    }
                )
                for money_col in ["PL", "Emissões 24-26"]:
                    table_profile[money_col] = pd.to_numeric(table_profile[money_col], errors="coerce").fillna(0).map(
                        lambda value: _fmt_bi(float(value), 2)
                    )
                for count_col in ["Fundos eq.", "Fundos únicos", "Docs", "Cedentes", "Critérios", "Links curados", "Links com fonte"]:
                    table_profile[count_col] = pd.to_numeric(table_profile[count_col], errors="coerce").fillna(0).map(
                        lambda value: _fmt_int(float(value))
                    )
                st.dataframe(table_profile, hide_index=True, width="stretch")
                generated_at = dimension_profile_manifest.get("generated_at_utc", "")
                source = f"Perfil: `{_DIMENSION_PROFILE_PATH.name}`"
                if generated_at:
                    source += f" · gerado em {generated_at}"
                st.caption(source)

    if use_catalog:
        generated_at = catalog_manifest.get("generated_at_utc", "")
        source_note = f"Fonte: `{_DIMENSION_CATALOG_PATH.name}`"
        if generated_at:
            source_note += f" · gerado em {generated_at}"
        if uses_dimension_monthly:
            monthly_generated_at = dimension_monthly_manifest.get("generated_at_utc", "")
            source_note += f" · séries: `{_DIMENSION_MONTHLY_PATH.name}`"
            if monthly_generated_at:
                source_note += f" ({monthly_generated_at})"
        st.caption(source_note)
        related = catalog[
            catalog.get("dimension_id", pd.Series("", index=catalog.index)).astype(str).eq(str(dim_col))
            & catalog.get("dimension_value", pd.Series("", index=catalog.index)).astype(str).eq(str(selected_value))
        ].copy()
        if not related.empty and related.get("source_layer", pd.Series("", index=related.index)).astype(str).isin({"cedente", "criteria", "snapshot"}).any():
            st.markdown("**Evidências da dimensão selecionada**")
            cols = [
                "dimension_label",
                "dimension_value",
                "source_layer",
                "participant_type",
                "participant_cnpj",
                "nome_exibicao",
                "cnpj_fundo",
                "source_document",
                "source_page",
                "source_method",
                "confidence_score",
                "review_status",
                "priority_2025_2026",
            ]
            st.dataframe(related[[col for col in cols if col in related.columns]].head(80), hide_index=True, width="stretch")
            st.caption("A tabela preserva fonte, documento, página, método, score e status de revisão quando disponíveis.")
    elif dim_col in _CEDENTE_HEATMAP_COLUMNS and not cedentes.empty:
        st.markdown("**Evidências de cedente/sacado da dimensão selecionada**")
        related = cedentes[cedentes[dim_col].astype(str).eq(str(selected_value))].copy()
        cols = [
            "tipo_participante",
            "razao_social",
            "cnpj_participante",
            "fundo",
            "cnpj_fundo",
            "setor",
            "segmento",
            "status_revisao",
            "score_confianca_final",
            "n_evidencias",
            "documento_origem",
            "pagina",
        ]
        st.dataframe(related[[col for col in cols if col in related.columns]].head(80), hide_index=True, width="stretch")
        st.caption("A tabela preserva documento, página, método e status de revisão para rastrear a origem da relação.")


@st.cache_data(show_spinner=False)
def _load_industry_pipeline_manifest() -> dict[str, object]:
    return load_pipeline_manifest(_PIPELINE_MANIFEST_PATH)


@st.cache_data(show_spinner=False)
def _load_industry_pipeline_index() -> dict[str, object]:
    index = load_pipeline_manifest(_PIPELINE_INDEX_PATH)
    if index:
        return index
    return build_industry_pipeline_index(industry_dir=_DATA_DIR, output_path=_PIPELINE_INDEX_PATH)


@st.cache_data(show_spinner=False)
def _load_monthly_delta_tables() -> dict[str, pd.DataFrame | dict[str, object]]:
    return {
        "delta": load_dataframe(_MONTHLY_DELTA_PATH),
        "actions": load_monthly_delta_actions(_MONTHLY_DELTA_ACTIONS_PATH),
        "manifest": load_pipeline_manifest(_MONTHLY_DELTA_MANIFEST_PATH),
    }


@st.cache_data(show_spinner=False)
def _load_curation_queue_tables() -> dict[str, pd.DataFrame | dict[str, object]]:
    queue = load_dataframe(_CURATION_QUEUE_PATH)
    summary = load_dataframe(_CURATION_QUEUE_SUMMARY_PATH)
    if summary.empty and not queue.empty:
        summary = build_industry_curation_queue_summary(queue)
    return {
        "queue": queue,
        "summary": summary,
        "manifest": load_pipeline_manifest(_CURATION_QUEUE_MANIFEST_PATH),
    }


def _status_badge_text(status: object) -> str:
    mapping = {
        "ok": "ok",
        "warning": "atenção",
        "missing": "ausente",
        "missing_artifact": "artefato ausente",
        "diferença_metodológica": "dif. metodologia",
        "sem_base_local": "sem base local",
        "sem_uso": "sem uso",
        "aderente": "aderente",
        "divergente": "divergente",
    }
    return mapping.get(str(status or ""), str(status or "n/d"))


def _format_curation_queue(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    cols = [
        "queue_domain",
        "status_curadoria",
        "priority_band",
        "priority_score",
        "competencia",
        "cnpj_fundo",
        "nome_exibicao",
        "action_type",
        "next_action",
        "gap_summary",
        "acao_revisada",
        "responsavel",
        "prazo",
        "notas",
        "updated_at_utc",
        "pl",
        "admin_nome",
        "gestor_nome",
        "segmento_principal",
        "source_document",
        "source_page",
        "source_method",
        "confidence_score",
        "rerun_command",
        "record_id",
        "queue_id",
    ]
    out = frame[[col for col in cols if col in frame.columns]].copy()
    out = out.rename(
        columns={
            "queue_domain": "Frente",
            "status_curadoria": "Status",
            "priority_band": "Prioridade",
            "priority_score": "Score",
            "competencia": "Competência",
            "cnpj_fundo": "CNPJ",
            "nome_exibicao": "FIDC/escopo",
            "action_type": "Tipo",
            "next_action": "Próxima ação",
            "gap_summary": "Resumo lacuna",
            "acao_revisada": "Ação revisada",
            "responsavel": "Responsável",
            "prazo": "Prazo",
            "notas": "Notas",
            "updated_at_utc": "Atualizado",
            "pl": "PL",
            "admin_nome": "Administrador",
            "gestor_nome": "Gestor",
            "segmento_principal": "Segmento",
            "source_document": "Documento",
            "source_page": "Página",
            "source_method": "Método",
            "confidence_score": "Score conf.",
            "rerun_command": "Comando",
            "record_id": "Registro",
            "queue_id": "ID",
        }
    )
    if "PL" in out.columns:
        out["PL"] = pd.to_numeric(out["PL"], errors="coerce").fillna(0).map(lambda value: "" if value == 0 else _fmt_bi(float(value), 2))
    for col in ["Score", "Score conf."]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").map(
                lambda value: "" if pd.isna(value) else f"{float(value):.1f}".replace(".", ",")
            )
    return out


def _format_curation_queue_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    cols = [
        "summary_type",
        "rank",
        "scope_label",
        "rows",
        "open_rows",
        "closed_rows",
        "high_priority_rows",
        "priority_2025_2026_rows",
        "funds",
        "max_priority_score",
        "pl_reference_brl",
        "latest_competencia",
        "domains",
        "status_mix",
        "priority_mix",
        "action_types",
        "next_actions_sample",
        "source_documents_sample",
        "rerun_commands_sample",
    ]
    out = frame[[col for col in cols if col in frame.columns]].copy()
    out = out.rename(
        columns={
            "summary_type": "Visão",
            "rank": "#",
            "scope_label": "Escopo",
            "rows": "Linhas",
            "open_rows": "Abertas",
            "closed_rows": "Fechadas",
            "high_priority_rows": "Alta prioridade",
            "priority_2025_2026_rows": "Prioridade 2025-26",
            "funds": "FIDCs",
            "max_priority_score": "Score máx.",
            "pl_reference_brl": "PL ref.",
            "latest_competencia": "Última comp.",
            "domains": "Frentes",
            "status_mix": "Status",
            "priority_mix": "Prioridades",
            "action_types": "Tipos",
            "next_actions_sample": "Ações",
            "source_documents_sample": "Documentos",
            "rerun_commands_sample": "Comandos",
        }
    )
    for col in ["Linhas", "Abertas", "Fechadas", "Alta prioridade", "Prioridade 2025-26", "FIDCs", "#"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    if "Score máx." in out.columns:
        out["Score máx."] = pd.to_numeric(out["Score máx."], errors="coerce").map(
            lambda value: "" if pd.isna(value) else f"{float(value):.1f}".replace(".", ",")
        )
    if "PL ref." in out.columns:
        out["PL ref."] = pd.to_numeric(out["PL ref."], errors="coerce").fillna(0).map(
            lambda value: "" if value == 0 else _fmt_bi(float(value), 2)
        )
    return out


def _coerce_curation_queue_status(domain: object, status: object) -> str:
    text = str(status or "").strip().lower() or "pendente"
    domain_text = str(domain or "").strip()
    if domain_text == "monthly_delta" and text in {"corrigido", "aceito", "processado"}:
        return "concluído"
    if domain_text in {"snapshot_gap", "catalog_gap"} and text in {"concluído", "concluido", "processado"}:
        return "corrigido"
    if domain_text == "document_chunk" and text in {"concluído", "concluido", "corrigido", "aceito"}:
        return "processado"
    return text


def _curation_queue_updates_to_domain_actions(updates: pd.DataFrame) -> dict[str, pd.DataFrame]:
    frames = {
        "monthly_delta": pd.DataFrame(columns=MONTHLY_DELTA_ACTION_COLUMNS),
        "snapshot_gap": pd.DataFrame(columns=_SNAPSHOT_GAP_ACTION_COLUMNS),
        "catalog_gap": pd.DataFrame(columns=_CATALOG_GAP_ACTION_COLUMNS),
        "document_chunk": pd.DataFrame(columns=_DOCUMENT_CHUNK_ACTION_COLUMNS),
    }
    if updates is None or updates.empty:
        return frames
    frame = updates.copy().fillna("")
    for col in ["queue_domain", "record_id", "status_curadoria", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        if col not in frame.columns:
            frame[col] = ""
    frame["status_curadoria"] = [
        _coerce_curation_queue_status(domain, status)
        for domain, status in zip(frame["queue_domain"], frame["status_curadoria"], strict=False)
    ]
    monthly = frame[frame["queue_domain"].eq("monthly_delta")].copy()
    if not monthly.empty:
        monthly = monthly.rename(columns={"record_id": "delta_id", "status_curadoria": "status_acao"})
        frames["monthly_delta"] = monthly[["delta_id", "status_acao", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]]
    snapshot = frame[frame["queue_domain"].eq("snapshot_gap")].copy()
    if not snapshot.empty:
        snapshot = snapshot.rename(columns={"record_id": "gap_id", "status_curadoria": "status_lacuna"})
        frames["snapshot_gap"] = snapshot[["gap_id", "status_lacuna", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]]
    catalog = frame[frame["queue_domain"].eq("catalog_gap")].copy()
    if not catalog.empty:
        catalog = catalog.rename(columns={"record_id": "traceability_gap_id", "status_curadoria": "status_lacuna"})
        frames["catalog_gap"] = catalog[["traceability_gap_id", "status_lacuna", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]]
    chunks = frame[frame["queue_domain"].eq("document_chunk")].copy()
    if not chunks.empty:
        chunks = chunks.rename(columns={"record_id": "chunk_id", "status_curadoria": "status_lote"})
        frames["document_chunk"] = chunks[["chunk_id", "status_lote", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]]
    for key, cols in [
        ("monthly_delta", MONTHLY_DELTA_ACTION_COLUMNS),
        ("snapshot_gap", _SNAPSHOT_GAP_ACTION_COLUMNS),
        ("catalog_gap", _CATALOG_GAP_ACTION_COLUMNS),
        ("document_chunk", _DOCUMENT_CHUNK_ACTION_COLUMNS),
    ]:
        out = frames[key].copy()
        for col in cols:
            if col not in out.columns:
                out[col] = ""
        id_col = cols[0]
        out = out[cols]
        out = out[out[id_col].fillna("").astype(str).str.strip().ne("")]
        frames[key] = out.drop_duplicates(id_col, keep="last")
    return frames


def _render_pipeline_manifest() -> None:
    st.markdown('<div class="industry-section">Pipeline mensal e cockpit de atualização</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Índice consolidado dos módulos da aba Indústria: base granular mensal, '
        "emissões, documentos, cedentes, critérios, fingerprints, freshness e comandos de refresh.</div>",
        unsafe_allow_html=True,
    )
    index = _load_industry_pipeline_index()
    if not index:
        st.info(
            "Índice do pipeline ainda não disponível. Rode `python scripts/build_fidc_industry_pipeline_index.py`."
        )
        return
    monthly_delta_tables = _load_monthly_delta_tables()
    monthly_delta = monthly_delta_tables["delta"]
    monthly_delta_actions = monthly_delta_tables["actions"]
    assert isinstance(monthly_delta, pd.DataFrame)
    assert isinstance(monthly_delta_actions, pd.DataFrame)
    monthly_delta = apply_monthly_delta_actions(monthly_delta, monthly_delta_actions)
    curation_queue_tables = _load_curation_queue_tables()
    curation_queue = curation_queue_tables["queue"]
    curation_queue_summary = curation_queue_tables["summary"]
    curation_queue_manifest = curation_queue_tables["manifest"]
    assert isinstance(curation_queue, pd.DataFrame)
    assert isinstance(curation_queue_summary, pd.DataFrame)
    assert isinstance(curation_queue_manifest, dict)
    profile_tables = _load_dimension_profile_tables()
    dimension_profiles = profile_tables["profiles"]
    heatmap_registry = profile_tables["heatmap_registry"]
    dimension_profile_manifest = profile_tables["manifest"]
    assert isinstance(dimension_profiles, pd.DataFrame)
    assert isinstance(heatmap_registry, pd.DataFrame)
    assert isinstance(dimension_profile_manifest, dict)
    profile_quality = (
        dimension_profile_manifest.get("quality", {})
        if isinstance(dimension_profile_manifest.get("quality"), dict)
        else {}
    )
    dossier_tables = _load_dimension_dossier_tables()
    dimension_dossiers = dossier_tables["dossiers"]
    dimension_dossier_manifest = dossier_tables["manifest"]
    assert isinstance(dimension_dossiers, pd.DataFrame)
    assert isinstance(dimension_dossier_manifest, dict)
    dossier_quality = (
        dimension_dossier_manifest.get("quality", {})
        if isinstance(dimension_dossier_manifest.get("quality"), dict)
        else {}
    )
    public_claim_tables = _load_public_claim_audit_tables()
    public_claim_audit = public_claim_tables["audit"]
    public_claim_manifest = public_claim_tables["manifest"]
    assert isinstance(public_claim_audit, pd.DataFrame)
    assert isinstance(public_claim_manifest, dict)
    catalog_tables = _load_dimension_catalog_tables()
    dimension_catalog = catalog_tables["catalog"]
    dimension_catalog_manifest = catalog_tables["manifest"]
    assert isinstance(dimension_catalog, pd.DataFrame)
    assert isinstance(dimension_catalog_manifest, dict)

    rollup = index.get("quality_rollup", {}) if isinstance(index.get("quality_rollup"), dict) else {}
    status_counts = rollup.get("module_status_counts", {}) if isinstance(rollup.get("module_status_counts"), dict) else {}
    modules = index.get("modules", []) if isinstance(index.get("modules"), list) else []
    refresh_plan = index.get("refresh_plan", []) if isinstance(index.get("refresh_plan"), list) else []
    artifacts = index.get("artifact_index", []) if isinstance(index.get("artifact_index"), list) else []
    prd_coverage = index.get("prd_coverage", []) if isinstance(index.get("prd_coverage"), list) else []
    monthly_update_plan = index.get("monthly_update_plan", []) if isinstance(index.get("monthly_update_plan"), list) else []
    manual_review_ledger = index.get("manual_review_ledger", []) if isinstance(index.get("manual_review_ledger"), list) else []
    public_claim_quality = (
        public_claim_manifest.get("quality", {})
        if isinstance(public_claim_manifest.get("quality"), dict)
        else {}
    )
    prd_status_counts = rollup.get("prd_status_counts", {}) if isinstance(rollup.get("prd_status_counts"), dict) else {}
    update_plan_status_counts = (
        rollup.get("monthly_update_plan_status_counts", {})
        if isinstance(rollup.get("monthly_update_plan_status_counts"), dict)
        else {}
    )
    manual_review_status_counts = (
        rollup.get("manual_review_status_counts", {})
        if isinstance(rollup.get("manual_review_status_counts"), dict)
        else {}
    )
    cards = [
        _curation_card(
            "Módulos ok",
            f"{_fmt_int(float(status_counts.get('ok', 0)))}/{_fmt_int(float(rollup.get('modules_total', 0)))}",
            f"gerado {str(index.get('generated_at_utc', ''))[:10]}",
        ),
        _curation_card(
            "Artefatos presentes",
            f"{_fmt_int(float(rollup.get('artifacts_present', 0)))}/{_fmt_int(float(rollup.get('artifacts_total', 0)))}",
            f"{_fmt_int(float(rollup.get('artifacts_missing', 0)))} ausentes · revisão {_fmt_int(float(rollup.get('manual_review_artifacts_present', 0)))}/{_fmt_int(float(rollup.get('manual_review_artifacts_total', 0)))}",
        ),
        _curation_card(
            "Competência IME",
            str(rollup.get("competencia_snapshot") or rollup.get("competencia_final") or "n/d"),
            "snapshot granular",
        ),
        _curation_card(
            "Delta alta prioridade",
            _fmt_int(float(rollup.get("monthly_delta_high_priority", 0))),
            f"{_fmt_int(float(rollup.get('monthly_delta_new_funds', 0)))} novos · {_fmt_int(float(rollup.get('monthly_delta_reactivated_funds', 0)))} reativados",
        ),
        _curation_card(
            "Fila única",
            _fmt_int(float(rollup.get("curation_queue_open_rows", len(curation_queue)) or 0)),
            f"{_fmt_int(float(rollup.get('curation_queue_high_priority_rows', 0) or 0))} alta prioridade",
        ),
        _curation_card(
            "PRD",
            f"{_fmt_int(float(prd_status_counts.get('ok', 0) or 0))}/{_fmt_int(float(rollup.get('prd_requirements_total', len(prd_coverage)) or 0))}",
            f"{_fmt_int(float(prd_status_counts.get('atenção', 0) or 0))} atenção · {_fmt_int(float(prd_status_counts.get('bloqueado', 0) or 0))} bloqueado",
        ),
        _curation_card(
            "Plano mensal",
            f"{_fmt_int(float(update_plan_status_counts.get('ok', 0) or 0))}/{_fmt_int(float(rollup.get('monthly_update_plan_rows', len(monthly_update_plan)) or 0))}",
            f"{_fmt_int(float(update_plan_status_counts.get('atenção', 0) or 0))} atenção · {_fmt_int(float(update_plan_status_counts.get('bloqueado', 0) or 0))} bloqueado",
        ),
        _curation_card(
            "Revisões",
            _fmt_int(float(rollup.get("manual_review_action_rows", 0) or 0)),
            f"{_fmt_int(float(rollup.get('manual_review_audit_events', 0) or 0))} eventos · {_fmt_int(float(manual_review_status_counts.get('atenção', 0) or 0))} atenção",
        ),
        _curation_card(
            "Claims públicos",
            _fmt_int(float(public_claim_quality.get("rows", rollup.get("public_claim_audit_rows", len(public_claim_audit))) or 0)),
            f"{_fmt_int(float(public_claim_quality.get('methodology_gap_claims', rollup.get('public_claim_audit_methodology_gap_claims', 0)) or 0))} dif. metodologia",
        ),
        _curation_card(
            "Chunks docs",
            f"{_fmt_int(float(rollup.get('document_chunks_processed', 0)))}/{_fmt_int(float(rollup.get('document_chunks', 0)))}",
            f"{_fmt_int(float(rollup.get('document_chunks_without_action', 0)))} sem acomp.",
        ),
        _curation_card(
            "Snapshot FIDCs",
            _fmt_int(float(rollup.get("fund_snapshot_rows", 0))),
            "base unificada",
        ),
        _curation_card(
            "Perfis cruzados",
            _fmt_int(float(profile_quality.get("rows", rollup.get("dimension_profile_rows", 0)) or 0)),
            f"{_fmt_int(float(profile_quality.get('source_dimensions', rollup.get('dimension_profile_source_dimensions', 0)) or 0))} dimensões",
        ),
        _curation_card(
            "Dossiês",
            f"{_fmt_int(float(dossier_quality.get('ok_rows', rollup.get('dimension_dossier_ok_rows', 0)) or 0))}/{_fmt_int(float(dossier_quality.get('rows', rollup.get('dimension_dossier_rows', len(dimension_dossiers))) or 0))}",
            f"{_fmt_int(float(dossier_quality.get('attention_rows', rollup.get('dimension_dossier_attention_rows', 0)) or 0))} atenção",
        ),
        _curation_card(
            "Cedentes",
            _fmt_int(float(rollup.get("fund_snapshot_with_cedentes", rollup.get("cedentes_structured_rows", 0)))),
            "FIDCs com evidência",
        ),
        _curation_card(
            "Sub mínima",
            _pct_label(float(rollup.get("subordination_median_pct", 0))) if rollup.get("subordination_median_pct") is not None else "n/d",
            f"{_fmt_int(float(rollup.get('subordination_funds', 0)))} FIDCs",
        ),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    tab_modules, tab_prd, tab_public, tab_reviews, tab_queue, tab_profiles, tab_dossiers, tab_catalog_quality, tab_delta, tab_refresh, tab_artifacts, tab_json = st.tabs(
        [
            "Módulos",
            "PRD",
            "Público",
            "Revisões",
            "Fila única",
            "Perfis cruzados",
            "Dossiês",
            "Qualidade catálogo",
            "Delta mensal",
            "Refresh mensal",
            "Artefatos",
            "Manifesto",
        ]
    )
    with tab_modules:
        module_rows = []
        for module in modules:
            if not isinstance(module, dict):
                continue
            quality = module.get("quality_highlights", {}) if isinstance(module.get("quality_highlights"), dict) else {}
            quality_text = " · ".join(
                f"{key}: {value}"
                for key, value in quality.items()
                if value not in ("", None, {})
            )
            module_rows.append(
                {
                    "Módulo": module.get("label", module.get("id", "")),
                    "Status": _status_badge_text(module.get("status")),
                    "Gerado em": str(module.get("generated_at_utc", ""))[:19],
                    "Cadência": module.get("cadence", ""),
                    "Etapas": _fmt_int(float(module.get("stage_count", 0))) if module.get("stage_count") not in ("", None) else "",
                    "Artefatos": f"{module.get('artifacts_present', 0)}/{module.get('artifact_count', 0)}",
                    "Comando": module.get("command", ""),
                    "Métricas": quality_text[:260],
                }
            )
        if module_rows:
            st.dataframe(pd.DataFrame(module_rows), hide_index=True, width="stretch")
        else:
            st.caption("Nenhum módulo encontrado no índice.")

        if status_counts:
            status_frame = pd.DataFrame(
                [{"Status": _status_badge_text(key), "Módulos": int(value)} for key, value in status_counts.items()]
            )
            chart = (
                alt.Chart(status_frame)
                .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
                .encode(
                    x=alt.X("Módulos:Q", title="módulos", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    y=alt.Y("Status:N", title=None, sort="-x"),
                    tooltip=[alt.Tooltip("Status:N"), alt.Tooltip("Módulos:Q")],
                )
                .properties(height=160)
            )
            st.altair_chart(chart, width="stretch")

    with tab_prd:
        if not prd_coverage:
            st.caption("Matriz PRD ainda não materializada. Recalcule o índice do pipeline.")
        else:
            prd_frame = pd.DataFrame(prd_coverage)
            status_values = sorted(
                [value for value in prd_frame.get("status_prd", pd.Series(dtype=str)).fillna("").astype(str).unique() if value]
            )
            default_status = [value for value in ["bloqueado", "atenção", "ok"] if value in set(status_values)] or status_values
            prd_a, prd_b = st.columns([0.85, 1.35])
            with prd_a:
                selected_prd_status = st.multiselect(
                    "Status PRD",
                    status_values,
                    default=default_status,
                    key="industry_prd_status",
                )
            with prd_b:
                prd_query = st.text_input(
                    "Buscar requisito",
                    key="industry_prd_query",
                    placeholder="cedentes, heatmap, revisão, documento, score",
                )
            prd_view = prd_frame.copy()
            if selected_prd_status:
                prd_view = prd_view[
                    prd_view.get("status_prd", pd.Series("", index=prd_view.index)).fillna("").astype(str).isin(selected_prd_status)
                ].copy()
            if prd_query:
                search_cols = [
                    col
                    for col in [
                        "tema",
                        "requisito",
                        "status_prd",
                        "evidencia",
                        "metrica",
                        "artefato",
                        "proximo_passo",
                        "comando",
                    ]
                    if col in prd_view.columns
                ]
                search = prd_view[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=prd_view.index)
                prd_view = prd_view[search.str.contains(prd_query, case=False, na=False)].copy()
            st.dataframe(_format_prd_coverage(prd_view), hide_index=True, width="stretch", height=460)
            if prd_status_counts:
                prd_status_frame = pd.DataFrame(
                    [{"Status": _status_badge_text(key), "Requisitos": int(value)} for key, value in prd_status_counts.items()]
                )
                st.dataframe(prd_status_frame, hide_index=True, width="stretch")

    with tab_public:
        if public_claim_audit.empty:
            st.caption("Auditoria pública ainda não materializada. Rode `python scripts/build_fidc_industry_public_claim_audit.py`.")
        else:
            public_status = public_claim_audit.get("status_auditoria", pd.Series("", index=public_claim_audit.index)).fillna("").astype(str).value_counts().to_dict()
            public_cards = [
                _curation_card("Claims", _fmt_int(float(len(public_claim_audit))), "notícias/boletins"),
                _curation_card("Com métrica local", _fmt_int(float(public_claim_quality.get("claims_with_local_metric", 0) or 0)), "comparação calculada"),
                _curation_card("Fontes", _fmt_int(float(public_claim_quality.get("public_sources", public_claim_audit.get("source_name", pd.Series(dtype=str)).nunique()) or 0)), "origens públicas"),
                _curation_card("Dif. metodologia", _fmt_int(float(public_status.get("diferença_metodológica", 0))), "não é erro automático"),
                _curation_card("Aderentes", _fmt_int(float(public_status.get("aderente", 0))), "dentro da tolerância"),
            ]
            st.markdown(f'<div class="industry-kpi-grid">{"".join(public_cards)}</div>', unsafe_allow_html=True)
            public_a, public_b, public_c, public_d = st.columns([0.8, 0.8, 0.9, 1.4])
            with public_a:
                source_options = sorted([value for value in public_claim_audit.get("source_name", pd.Series(dtype=str)).fillna("").astype(str).unique() if value])
                selected_sources = st.multiselect(
                    "Fonte",
                    source_options,
                    default=source_options,
                    key="industry_public_claim_source",
                )
            with public_b:
                metric_options = sorted([value for value in public_claim_audit.get("metric_group", pd.Series(dtype=str)).fillna("").astype(str).unique() if value])
                selected_metrics = st.multiselect(
                    "Métrica",
                    metric_options,
                    default=metric_options,
                    key="industry_public_claim_metric",
                )
            with public_c:
                status_options = sorted([value for value in public_claim_audit.get("status_auditoria", pd.Series(dtype=str)).fillna("").astype(str).unique() if value])
                selected_public_status = st.multiselect(
                    "Status",
                    status_options,
                    default=status_options,
                    key="industry_public_claim_status",
                )
            with public_d:
                public_query = st.text_input(
                    "Buscar claim",
                    key="industry_public_claim_query",
                    placeholder="ANBIMA, PL, captação, ofertas, metodologia",
                )
            public_view = public_claim_audit.copy()
            if selected_sources:
                public_view = public_view[public_view.get("source_name", pd.Series("", index=public_view.index)).fillna("").astype(str).isin(selected_sources)].copy()
            if selected_metrics:
                public_view = public_view[public_view.get("metric_group", pd.Series("", index=public_view.index)).fillna("").astype(str).isin(selected_metrics)].copy()
            if selected_public_status:
                public_view = public_view[public_view.get("status_auditoria", pd.Series("", index=public_view.index)).fillna("").astype(str).isin(selected_public_status)].copy()
            if public_query:
                search_cols = [
                    col
                    for col in [
                        "source_name",
                        "source_title",
                        "metric_group",
                        "claim_text",
                        "status_auditoria",
                        "comparability",
                        "local_source_artifact",
                        "local_evidence",
                        "method_note",
                    ]
                    if col in public_view.columns
                ]
                search = public_view[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=public_view.index)
                public_view = public_view[search.str.contains(public_query, case=False, na=False)].copy()
            st.dataframe(_format_public_claim_audit(public_view), hide_index=True, width="stretch", height=440)
            st.download_button(
                "Baixar auditoria pública",
                data=public_claim_audit.to_csv(index=False).encode("utf-8"),
                file_name="industry_public_claim_audit.csv",
                mime="text/csv",
                key="industry_public_claim_download",
            )
            if public_claim_manifest:
                generated_at = public_claim_manifest.get("generated_at_utc", "")
                source_note = f"Fonte: `{_PUBLIC_CLAIM_AUDIT_PATH.name}`"
                if generated_at:
                    source_note += f" · gerado em {generated_at}"
                st.caption(source_note)

    with tab_reviews:
        if not manual_review_ledger:
            st.caption("Ledger de revisão manual ainda não materializado. Recalcule o índice do pipeline.")
        else:
            ledger = pd.DataFrame(manual_review_ledger)
            ledger_status = ledger.get("status_ledger", pd.Series("", index=ledger.index)).fillna("").astype(str).value_counts().to_dict()
            review_cards = [
                _curation_card("Domínios", _fmt_int(float(len(ledger))), "mesas e filas com persistência"),
                _curation_card("Com ações", _fmt_int(float(rollup.get("manual_review_domains_with_actions", 0) or 0)), "arquivos não vazios"),
                _curation_card("Com auditoria", _fmt_int(float(rollup.get("manual_review_domains_with_audit", 0) or 0)), "eventos salvos"),
                _curation_card("Ações", _fmt_int(float(rollup.get("manual_review_action_rows", 0) or 0)), "linhas persistidas"),
                _curation_card("Eventos", _fmt_int(float(rollup.get("manual_review_audit_events", 0) or 0)), "histórico append-only"),
                _curation_card("Atenção", _fmt_int(float(ledger_status.get("atenção", 0))), "ação sem auditoria ou vice-versa"),
            ]
            st.markdown(f'<div class="industry-kpi-grid">{"".join(review_cards)}</div>', unsafe_allow_html=True)
            review_a, review_b, review_c = st.columns([0.9, 1.0, 1.4])
            with review_a:
                status_options = sorted([value for value in ledger.get("status_ledger", pd.Series(dtype=str)).fillna("").astype(str).unique() if value])
                selected_review_status = st.multiselect(
                    "Status ledger",
                    status_options,
                    default=status_options,
                    key="industry_manual_review_ledger_status",
                )
            with review_b:
                surface_options = sorted([value for value in ledger.get("ui_surface", pd.Series(dtype=str)).fillna("").astype(str).unique() if value])
                selected_surfaces = st.multiselect(
                    "Tela",
                    surface_options,
                    default=surface_options,
                    key="industry_manual_review_ledger_surface",
                )
            with review_c:
                review_query = st.text_input(
                    "Buscar revisão",
                    key="industry_manual_review_ledger_query",
                    placeholder="cedentes, critérios, auditoria, snapshot, catálogo",
                )
            ledger_view = ledger.copy()
            if selected_review_status:
                ledger_view = ledger_view[
                    ledger_view.get("status_ledger", pd.Series("", index=ledger_view.index)).fillna("").astype(str).isin(selected_review_status)
                ].copy()
            if selected_surfaces:
                ledger_view = ledger_view[
                    ledger_view.get("ui_surface", pd.Series("", index=ledger_view.index)).fillna("").astype(str).isin(selected_surfaces)
                ].copy()
            if review_query:
                search_cols = [
                    col
                    for col in [
                        "domain_id",
                        "label",
                        "status_ledger",
                        "ui_surface",
                        "comparison",
                        "action_file",
                        "audit_file",
                        "status_mix",
                        "audit_domains",
                        "source_artifacts",
                        "rerun_command",
                    ]
                    if col in ledger_view.columns
                ]
                search = ledger_view[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=ledger_view.index)
                ledger_view = ledger_view[search.str.contains(review_query, case=False, na=False)].copy()
            st.dataframe(_format_manual_review_ledger(ledger_view), hide_index=True, width="stretch", height=420)
            st.download_button(
                "Baixar ledger de revisões",
                data=ledger.to_csv(index=False).encode("utf-8"),
                file_name="industry_manual_review_ledger.csv",
                mime="text/csv",
                key="industry_manual_review_ledger_download",
            )

    with tab_queue:
        if curation_queue.empty:
            st.caption("Fila única ainda não materializada. Rode `python scripts/build_fidc_industry_curation_queue.py`.")
        else:
            queue = curation_queue.copy()
            queue_quality = (
                curation_queue_manifest.get("quality", {})
                if isinstance(curation_queue_manifest.get("quality"), dict)
                else {}
            )
            domain_counts = queue_quality.get("domain_counts", {}) if isinstance(queue_quality.get("domain_counts"), dict) else {}
            status_counts_queue = queue_quality.get("status_counts", {}) if isinstance(queue_quality.get("status_counts"), dict) else {}
            queue_cards = [
                _curation_card("Linhas abertas", _fmt_int(float(queue_quality.get("open_rows", len(queue)) or 0)), "fila consolidada"),
                _curation_card("FIDCs", _fmt_int(float(queue_quality.get("funds", 0) or 0)), "CNPJs normalizados"),
                _curation_card("Alta prioridade", _fmt_int(float(queue_quality.get("high_priority_rows", 0) or 0)), "prioridade explícita"),
                _curation_card("Snapshot", _fmt_int(float(domain_counts.get("snapshot_gap", 0))), "lacunas all-FIDCs"),
                _curation_card("Catálogo", _fmt_int(float(domain_counts.get("catalog_gap", 0))), "rastreabilidade"),
                _curation_card("Delta", _fmt_int(float(domain_counts.get("monthly_delta", 0))), "mudança mensal"),
            ]
            st.markdown(f'<div class="industry-kpi-grid">{"".join(queue_cards)}</div>', unsafe_allow_html=True)
            summary = curation_queue_summary.copy()
            if summary.empty:
                summary = build_industry_curation_queue_summary(queue)
            if not summary.empty:
                type_labels = {
                    "frente_status": "Frente/status",
                    "fidc_backlog": "FIDC",
                    "admin_backlog": "Administrador",
                    "segment_backlog": "Segmento",
                }
                summary_types = [value for value in ["frente_status", "fidc_backlog", "admin_backlog", "segment_backlog"] if value in set(summary["summary_type"].fillna("").astype(str))]
                if summary_types:
                    st.markdown("**Resumo operacional**")
                    summary_a, summary_b = st.columns([0.85, 1.4])
                    with summary_a:
                        selected_summary_type = st.selectbox(
                            "Visão",
                            summary_types,
                            format_func=lambda value: type_labels.get(value, value),
                            key="industry_curation_queue_summary_type",
                        )
                    with summary_b:
                        summary_query = st.text_input(
                            "Buscar resumo",
                            key="industry_curation_queue_summary_query",
                            placeholder="FIDC, administrador, segmento, ação ou documento",
                        )
                    summary_view = summary[summary["summary_type"].fillna("").astype(str).eq(selected_summary_type)].copy()
                    if summary_query:
                        summary_search_cols = [
                            col
                            for col in [
                                "scope_label",
                                "domains",
                                "status_mix",
                                "priority_mix",
                                "action_types",
                                "next_actions_sample",
                                "gap_sample",
                                "source_documents_sample",
                                "rerun_commands_sample",
                                "admin_nome",
                                "segmento_principal",
                                "cnpj_fundo",
                            ]
                            if col in summary_view.columns
                        ]
                        if summary_search_cols:
                            summary_search = summary_view[summary_search_cols].fillna("").astype(str).agg(" ".join, axis=1)
                            summary_view = summary_view[summary_search.str.contains(summary_query, case=False, na=False)].copy()
                    st.dataframe(_format_curation_queue_summary(summary_view.head(120)), hide_index=True, width="stretch", height=300)
            queue_a, queue_b, queue_c, queue_d = st.columns([0.85, 0.85, 0.85, 1.3])
            with queue_a:
                domain_options = sorted([value for value in queue.get("queue_domain", pd.Series(dtype=str)).fillna("").astype(str).unique() if value])
                selected_domains = st.multiselect("Frente", domain_options, default=domain_options, key="industry_curation_queue_domain")
            with queue_b:
                status_options = sorted([value for value in queue.get("status_curadoria", pd.Series(dtype=str)).fillna("").astype(str).replace("", "pendente").unique() if value])
                default_status = [value for value in status_options if value not in {"corrigido", "aceito", "ignorado", "processado"}] or status_options
                selected_queue_status = st.multiselect("Status", status_options, default=default_status, key="industry_curation_queue_status")
            with queue_c:
                priority_options = sorted([value for value in queue.get("priority_band", pd.Series(dtype=str)).fillna("").astype(str).replace("", "n/d").unique() if value])
                priority_default = [value for value in priority_options if value in {"alta", "média", "media"}] or priority_options
                selected_priorities = st.multiselect("Prioridade", priority_options, default=priority_default, key="industry_curation_queue_priority")
            with queue_d:
                queue_query = st.text_input("Buscar fila", key="industry_curation_queue_query", placeholder="FIDC, CNPJ, ação, frente ou documento")
            queue_view = queue.copy()
            if selected_domains:
                queue_view = queue_view[queue_view["queue_domain"].isin(selected_domains)].copy()
            if selected_queue_status:
                queue_view = queue_view[
                    queue_view.get("status_curadoria", pd.Series("", index=queue_view.index)).fillna("").replace("", "pendente").isin(selected_queue_status)
                ].copy()
            if selected_priorities:
                priorities = queue_view.get("priority_band", pd.Series("", index=queue_view.index)).fillna("").astype(str).replace("", "n/d")
                queue_view = queue_view[priorities.isin(selected_priorities)].copy()
            if queue_query:
                search_cols = [
                    col
                    for col in [
                        "queue_domain",
                        "record_id",
                        "cnpj_fundo",
                        "nome_exibicao",
                        "admin_nome",
                        "gestor_nome",
                        "next_action",
                        "gap_summary",
                        "acao_revisada",
                        "responsavel",
                        "notas",
                        "source_document",
                        "rerun_command",
                    ]
                    if col in queue_view.columns
                ]
                search = queue_view[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=queue_view.index)
                queue_view = queue_view[search.str.contains(queue_query, case=False, na=False)].copy()
            if not queue_view.empty and "priority_score" in queue_view.columns:
                queue_view["priority_score_num"] = pd.to_numeric(queue_view["priority_score"], errors="coerce").fillna(0)
                queue_view["pl_num"] = pd.to_numeric(queue_view.get("pl", pd.Series(0, index=queue_view.index)), errors="coerce").fillna(0)
                priority_order = {"alta": 0, "média": 1, "media": 1, "baixa": 2}
                queue_view["priority_order"] = (
                    queue_view.get("priority_band", pd.Series("", index=queue_view.index))
                    .fillna("")
                    .astype(str)
                    .str.lower()
                    .map(priority_order)
                    .fillna(4)
                )
                queue_view = queue_view.sort_values(["priority_order", "priority_score_num", "pl_num"], ascending=[True, False, False]).drop(
                    columns=["priority_order", "priority_score_num", "pl_num"]
                )
            queue_page = queue_view.head(600).copy()
            queue_display = _format_curation_queue(queue_page)
            unified_status_options = [
                "pendente",
                "em andamento",
                "bloqueado",
                "corrigido",
                "aceito",
                "concluído",
                "processado",
                "ignorado",
            ]
            edited_queue = st.data_editor(
                queue_display,
                hide_index=True,
                width="stretch",
                height=560,
                disabled=[
                    "Frente",
                    "Prioridade",
                    "Score",
                    "Competência",
                    "CNPJ",
                    "FIDC/escopo",
                    "Tipo",
                    "Próxima ação",
                    "Resumo lacuna",
                    "Atualizado",
                    "PL",
                    "Administrador",
                    "Gestor",
                    "Segmento",
                    "Documento",
                    "Página",
                    "Método",
                    "Score conf.",
                    "Comando",
                    "Registro",
                    "ID",
                ],
                column_config={
                    "Status": st.column_config.SelectboxColumn("Status", options=unified_status_options, required=True),
                    "Ação revisada": st.column_config.TextColumn("Ação revisada", width="large"),
                    "Notas": st.column_config.TextColumn("Notas", width="large"),
                    "Comando": st.column_config.TextColumn("Comando", width="large"),
                },
                key="industry_curation_queue_editor",
            )
            if st.button("Salvar ajustes da fila única", type="primary", key="industry_save_curation_queue_actions"):
                saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                edited_updates = pd.DataFrame(
                    {
                        "queue_domain": edited_queue["Frente"].fillna("").astype(str),
                        "record_id": edited_queue["Registro"].fillna("").astype(str),
                        "status_curadoria": edited_queue["Status"].fillna("").astype(str).replace("", "pendente"),
                        "acao_revisada": edited_queue["Ação revisada"].fillna("").astype(str),
                        "responsavel": edited_queue["Responsável"].fillna("").astype(str),
                        "prazo": edited_queue["Prazo"].fillna("").astype(str),
                        "notas": edited_queue["Notas"].fillna("").astype(str),
                        "updated_at_utc": saved_at,
                    }
                )
                material_cols = ["acao_revisada", "responsavel", "prazo", "notas"]
                material = edited_updates["status_curadoria"].fillna("").astype(str).str.lower().ne("pendente") | (
                    edited_updates[material_cols].fillna("").astype(str).agg(" ".join, axis=1).str.strip().ne("")
                )
                all_domain_updates = _curation_queue_updates_to_domain_actions(edited_updates)
                material_domain_updates = _curation_queue_updates_to_domain_actions(edited_updates[material].copy())

                audit_events_total = 0
                saved_rows_total = 0

                visible_monthly = set(all_domain_updates["monthly_delta"].get("delta_id", pd.Series(dtype=str)).fillna("").astype(str))
                existing_monthly = monthly_delta_actions.copy()
                if visible_monthly and "delta_id" in existing_monthly.columns:
                    existing_monthly = existing_monthly[~existing_monthly["delta_id"].fillna("").astype(str).isin(visible_monthly)].copy()
                updated_monthly_actions = pd.concat([existing_monthly, material_domain_updates["monthly_delta"]], ignore_index=True)
                events = build_review_audit_events(
                    previous=_monthly_delta_actions_for_audit(monthly_delta_actions),
                    updated=_monthly_delta_actions_for_audit(updated_monthly_actions),
                    key_column="delta_id",
                    review_domain="monthly_delta_action",
                    saved_at_utc=saved_at,
                    source="industry_curation_queue_editor",
                )
                append_review_audit_events(events, _MONTHLY_DELTA_ACTION_AUDIT_PATH)
                updated_monthly_actions = save_monthly_delta_actions(updated_monthly_actions, _MONTHLY_DELTA_ACTIONS_PATH)
                audit_events_total += len(events)
                saved_rows_total += len(material_domain_updates["monthly_delta"])

                snapshot_actions = _load_snapshot_gap_actions()
                visible_snapshot = set(all_domain_updates["snapshot_gap"].get("gap_id", pd.Series(dtype=str)).fillna("").astype(str))
                existing_snapshot = snapshot_actions.copy()
                if visible_snapshot and "gap_id" in existing_snapshot.columns:
                    existing_snapshot = existing_snapshot[~existing_snapshot["gap_id"].fillna("").astype(str).isin(visible_snapshot)].copy()
                updated_snapshot_actions = pd.concat([existing_snapshot, material_domain_updates["snapshot_gap"]], ignore_index=True)
                events = build_review_audit_events(
                    previous=_snapshot_gap_actions_for_audit(snapshot_actions),
                    updated=_snapshot_gap_actions_for_audit(updated_snapshot_actions),
                    key_column="gap_id",
                    review_domain="snapshot_gap",
                    saved_at_utc=saved_at,
                    source="industry_curation_queue_editor",
                )
                append_review_audit_events(events, _SNAPSHOT_GAP_ACTION_AUDIT_PATH)
                updated_snapshot_actions = _save_snapshot_gap_actions(updated_snapshot_actions)
                audit_events_total += len(events)
                saved_rows_total += len(material_domain_updates["snapshot_gap"])

                catalog_actions = _load_catalog_gap_actions()
                visible_catalog = set(
                    all_domain_updates["catalog_gap"].get("traceability_gap_id", pd.Series(dtype=str)).fillna("").astype(str)
                )
                existing_catalog = catalog_actions.copy()
                if visible_catalog and "traceability_gap_id" in existing_catalog.columns:
                    existing_catalog = existing_catalog[
                        ~existing_catalog["traceability_gap_id"].fillna("").astype(str).isin(visible_catalog)
                    ].copy()
                updated_catalog_actions = pd.concat([existing_catalog, material_domain_updates["catalog_gap"]], ignore_index=True)
                events = build_review_audit_events(
                    previous=_catalog_gap_actions_for_audit(catalog_actions),
                    updated=_catalog_gap_actions_for_audit(updated_catalog_actions),
                    key_column="traceability_gap_id",
                    review_domain="dimension_catalog_gap",
                    saved_at_utc=saved_at,
                    source="industry_curation_queue_editor",
                )
                append_review_audit_events(events, _CATALOG_GAP_ACTION_AUDIT_PATH)
                updated_catalog_actions = _save_catalog_gap_actions(updated_catalog_actions)
                audit_events_total += len(events)
                saved_rows_total += len(material_domain_updates["catalog_gap"])

                chunk_actions = _load_document_chunk_actions()
                visible_chunks = set(all_domain_updates["document_chunk"].get("chunk_id", pd.Series(dtype=str)).fillna("").astype(str))
                existing_chunks = chunk_actions.copy()
                if visible_chunks and "chunk_id" in existing_chunks.columns:
                    existing_chunks = existing_chunks[~existing_chunks["chunk_id"].fillna("").astype(str).isin(visible_chunks)].copy()
                updated_chunk_actions = pd.concat([existing_chunks, material_domain_updates["document_chunk"]], ignore_index=True)
                events = build_review_audit_events(
                    previous=_document_chunk_actions_for_audit(chunk_actions),
                    updated=_document_chunk_actions_for_audit(updated_chunk_actions),
                    key_column="chunk_id",
                    review_domain="document_chunk_action",
                    saved_at_utc=saved_at,
                    source="industry_curation_queue_editor",
                )
                append_review_audit_events(events, _DOCUMENT_CHUNK_ACTION_AUDIT_PATH)
                updated_chunk_actions = _save_document_chunk_actions(updated_chunk_actions)
                audit_events_total += len(events)
                saved_rows_total += len(material_domain_updates["document_chunk"])

                document_tables = _load_document_tables()
                inventory = document_tables["inventory"] if isinstance(document_tables["inventory"], pd.DataFrame) else pd.DataFrame()
                chunks = document_tables["chunks"] if isinstance(document_tables["chunks"], pd.DataFrame) else pd.DataFrame()
                materialized_plan = build_document_chunk_plan(chunks, inventory, actions=updated_chunk_actions)
                save_dataframe(materialized_plan, _DOCUMENT_CHUNK_PLAN_PATH)
                monthly_delta_refreshed = apply_monthly_delta_actions(monthly_delta_tables["delta"], updated_monthly_actions)
                snapshot_tables = _load_fund_snapshot_tables()
                snapshot = snapshot_tables["snapshot"] if isinstance(snapshot_tables["snapshot"], pd.DataFrame) else pd.DataFrame()
                materialized_queue = build_industry_curation_queue(
                    snapshot=snapshot,
                    monthly_delta=monthly_delta_refreshed,
                    document_chunk_plan=materialized_plan,
                    dimension_catalog=dimension_catalog,
                    snapshot_gap_actions=updated_snapshot_actions,
                    catalog_gap_actions=updated_catalog_actions,
                )
                save_dataframe(materialized_queue, _CURATION_QUEUE_PATH)
                materialized_summary = build_industry_curation_queue_summary(materialized_queue)
                save_dataframe(materialized_summary, _CURATION_QUEUE_SUMMARY_PATH)
                curation_manifest = build_curation_queue_pipeline_manifest(
                    industry_dir=_DATA_DIR,
                    output_path=_CURATION_QUEUE_PATH,
                    manifest_path=_CURATION_QUEUE_MANIFEST_PATH,
                    summary_path=_CURATION_QUEUE_SUMMARY_PATH,
                    snapshot=snapshot,
                    monthly_delta=monthly_delta_refreshed,
                    document_chunk_plan=materialized_plan,
                    dimension_catalog=dimension_catalog,
                    queue=materialized_queue,
                    summary=materialized_summary,
                )
                save_pipeline_manifest(curation_manifest, _CURATION_QUEUE_MANIFEST_PATH)
                new_index = build_industry_pipeline_index(industry_dir=_DATA_DIR, output_path=_PIPELINE_INDEX_PATH)
                save_pipeline_manifest(new_index, _PIPELINE_INDEX_PATH)
                _load_monthly_delta_tables.clear()
                _load_snapshot_gap_actions.clear()
                _load_catalog_gap_actions.clear()
                _load_document_chunk_actions.clear()
                _load_curation_queue_tables.clear()
                _load_industry_pipeline_index.clear()
                st.success(
                    f"Fila única salva: {_fmt_int(float(saved_rows_total))} ações persistidas, "
                    f"{_fmt_int(float(audit_events_total))} eventos de auditoria e "
                    f"{_fmt_int(float(len(materialized_queue)))} linhas rematerializadas."
                )
            st.download_button(
                "Baixar fila filtrada",
                data=queue_view.to_csv(index=False).encode("utf-8"),
                file_name="industry_curation_queue_filtered.csv",
                mime="text/csv",
                key="industry_curation_queue_download",
            )
            if status_counts_queue:
                status_frame = pd.DataFrame(
                    [{"Status": key, "Linhas": int(value)} for key, value in status_counts_queue.items()]
                )
                st.dataframe(status_frame, hide_index=True, width="stretch")
            generated_at = curation_queue_manifest.get("generated_at_utc", "")
            source_note = f"Fonte: `{_CURATION_QUEUE_PATH.name}`"
            if generated_at:
                source_note += f" · gerado em {generated_at}"
            st.caption(source_note)

    with tab_profiles:
        if dimension_profiles.empty:
            st.caption("Perfis cruzados ainda não materializados. Rode `python scripts/build_fidc_industry_dimension_profiles.py`.")
        else:
            profile_links = float(profile_quality.get("profile_links", 0) or 0)
            with_source = float(profile_quality.get("with_source_document_links", 0) or 0)
            curated = float(profile_quality.get("curated_links", 0) or 0)
            weighted = float(profile_quality.get("weighted_links", 0) or 0)
            heatmap_available = float(profile_quality.get("heatmap_preset_profile_available", 0) or 0)
            heatmap_total = float(profile_quality.get("heatmap_preset_rows", len(heatmap_registry)) or 0)
            profile_cards = [
                _curation_card(
                    "Células origem × alvo",
                    _fmt_int(float(profile_quality.get("rows", len(dimension_profiles)) or 0)),
                    f"{profile_quality.get('competencia', 'n/d')}",
                ),
                _curation_card(
                    "Dimensões",
                    f"{_fmt_int(float(profile_quality.get('source_dimensions', 0) or 0))} × {_fmt_int(float(profile_quality.get('target_dimensions', 0) or 0))}",
                    "origem × alvo",
                ),
                _curation_card(
                    "Links de perfil",
                    _fmt_int(profile_links),
                    "relações fundo-dimensão",
                ),
                _curation_card(
                    "Com fonte",
                    _fmt_int(with_source),
                    _fmt_pct(with_source / profile_links) if profile_links else "n/d",
                ),
                _curation_card(
                    "Curados",
                    _fmt_int(curated),
                    _fmt_pct(curated / profile_links) if profile_links else "n/d",
                ),
                _curation_card(
                    "Ponderados",
                    _fmt_int(weighted),
                    _fmt_pct(weighted / profile_links) if profile_links else "n/d",
                ),
                _curation_card(
                    "Presets heatmap",
                    f"{_fmt_int(heatmap_available)}/{_fmt_int(heatmap_total)}",
                    "com perfil materializado",
                ),
            ]
            st.markdown(f'<div class="industry-kpi-grid">{"".join(profile_cards)}</div>', unsafe_allow_html=True)
            if not heatmap_registry.empty:
                st.markdown("**Presets auditáveis de heatmap**")
                status_filter = st.multiselect(
                    "Status preset",
                    sorted(heatmap_registry.get("status", pd.Series(dtype=str)).fillna("").astype(str).unique()),
                    default=[
                        value
                        for value in ["ok", "sem_perfil"]
                        if value in set(heatmap_registry.get("status", pd.Series(dtype=str)).fillna("").astype(str))
                    ]
                    or sorted(heatmap_registry.get("status", pd.Series(dtype=str)).fillna("").astype(str).unique()),
                    key="industry_heatmap_registry_status",
                )
                registry_view = heatmap_registry.copy()
                if status_filter:
                    registry_view = registry_view[registry_view.get("status", pd.Series("", index=registry_view.index)).isin(status_filter)].copy()
                st.dataframe(_format_heatmap_registry(registry_view), hide_index=True, width="stretch")
            coverage = _dimension_profile_coverage_frame(dimension_profiles)
            if coverage.empty:
                st.caption("Não foi possível resumir cobertura por dimensão.")
            else:
                top_coverage = coverage.head(18).copy()
                chart = (
                    alt.Chart(top_coverage)
                    .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
                    .encode(
                        x=alt.X("profile_links:Q", title="links", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                        y=alt.Y("source_dimension_label:N", title=None, sort="-x", axis=alt.Axis(labelLimit=260)),
                        tooltip=[
                            alt.Tooltip("source_dimension_label:N", title="dimensão"),
                            alt.Tooltip("profile_links:Q", title="links", format=",.0f"),
                            alt.Tooltip("source_document_ratio:Q", title="% com fonte", format=".1%"),
                            alt.Tooltip("curated_ratio:Q", title="% curado", format=".1%"),
                            alt.Tooltip("weighted_ratio:Q", title="% ponderado", format=".1%"),
                        ],
                    )
                    .properties(height=max(260, 22 * len(top_coverage)))
                )
                st.altair_chart(chart, width="stretch")
                keep_cols = [
                    "source_dimension_label",
                    "source_dimension_id",
                    "source_values",
                    "target_dimensions",
                    "target_values",
                    "profile_rows",
                    "profile_links",
                    "source_document_links",
                    "source_document_ratio",
                    "curated_links",
                    "curated_ratio",
                    "weighted_links",
                    "weighted_ratio",
                    "avg_confidence_score",
                ]
                st.dataframe(
                    _format_dimension_profile_coverage(coverage[[col for col in keep_cols if col in coverage.columns]]),
                    hide_index=True,
                    width="stretch",
                )
            generated_at = dimension_profile_manifest.get("generated_at_utc", "")
            source_note = f"Fonte: `{_DIMENSION_PROFILE_PATH.name}`"
            if generated_at:
                source_note += f" · gerado em {generated_at}"
            st.caption(source_note)

    with tab_dossiers:
        if dimension_dossiers.empty:
            st.caption("Dossiês dimensionais ainda não materializados. Rode `python scripts/build_fidc_industry_dimension_dossiers.py`.")
        else:
            dossier_status = (
                dimension_dossiers.get("status_dossie", pd.Series("", index=dimension_dossiers.index))
                .fillna("")
                .astype(str)
                .value_counts()
                .to_dict()
            )
            dossier_links = float(pd.to_numeric(dimension_dossiers.get("links_catalogo"), errors="coerce").fillna(0).sum())
            dossier_source_links = float(pd.to_numeric(dimension_dossiers.get("links_com_fonte"), errors="coerce").fillna(0).sum())
            dossier_traceability_links = float(pd.to_numeric(dimension_dossiers.get("traceability_links"), errors="coerce").fillna(0).sum())
            dossier_profile_rows = float(pd.to_numeric(dimension_dossiers.get("profile_rows"), errors="coerce").fillna(0).sum())
            dossier_presets = float(pd.to_numeric(dimension_dossiers.get("heatmap_presets"), errors="coerce").fillna(0).sum())
            dossier_presets_ok = float(pd.to_numeric(dimension_dossiers.get("heatmap_presets_ok"), errors="coerce").fillna(0).sum())
            dossier_cards = [
                _curation_card("Dimensões", _fmt_int(float(len(dimension_dossiers))), "dossiês materializados"),
                _curation_card("Ok", _fmt_int(float(dossier_status.get("ok", 0))), f"{_fmt_int(float(dossier_status.get('atenção', 0)))} atenção"),
                _curation_card("Rastreável", _fmt_pct(dossier_traceability_links / dossier_links) if dossier_links else "n/d", "fonte ou método"),
                _curation_card("Com documento", _fmt_pct(dossier_source_links / dossier_links) if dossier_links else "n/d", "documento regulatório"),
                _curation_card("Perfis", _fmt_int(dossier_profile_rows), "células origem × alvo"),
                _curation_card("Heatmaps", f"{_fmt_int(dossier_presets_ok)}/{_fmt_int(dossier_presets)}", "presets ligados"),
            ]
            st.markdown(f'<div class="industry-kpi-grid">{"".join(dossier_cards)}</div>', unsafe_allow_html=True)
            dossier_a, dossier_b = st.columns([0.8, 1.4])
            with dossier_a:
                status_options = sorted(
                    [
                        value
                        for value in dimension_dossiers.get("status_dossie", pd.Series(dtype=str)).fillna("").astype(str).unique()
                        if value
                    ]
                )
                selected_status = st.multiselect(
                    "Status",
                    status_options,
                    default=status_options,
                    key="industry_dimension_dossier_status",
                )
            with dossier_b:
                dossier_query = st.text_input(
                    "Buscar dossiê",
                    key="industry_dimension_dossier_query",
                    placeholder="administrador, cedente, segmento, indexador, pendência",
                )
            dossier_view = dimension_dossiers.copy()
            if selected_status:
                dossier_view = dossier_view[
                    dossier_view.get("status_dossie", pd.Series("", index=dossier_view.index)).fillna("").astype(str).isin(selected_status)
                ].copy()
            if dossier_query:
                search_cols = [
                    col
                    for col in [
                        "dimension_id",
                        "dimension_label",
                        "status_dossie",
                        "status_reasons",
                        "top_values_sample",
                        "source_documents_sample",
                        "heatmap_preset_labels_sample",
                    ]
                    if col in dossier_view.columns
                ]
                search = dossier_view[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=dossier_view.index)
                dossier_view = dossier_view[search.str.contains(dossier_query, case=False, na=False)].copy()
            st.dataframe(_format_dimension_dossiers(dossier_view), hide_index=True, width="stretch", height=460)
            st.download_button(
                "Baixar dossiês dimensionais",
                data=dimension_dossiers.to_csv(index=False).encode("utf-8"),
                file_name="industry_dimension_dossiers.csv",
                mime="text/csv",
                key="industry_dimension_dossier_download",
            )
            generated_at = dimension_dossier_manifest.get("generated_at_utc", "")
            source_note = f"Fonte: `{_DIMENSION_DOSSIER_PATH.name}`"
            if generated_at:
                source_note += f" · gerado em {generated_at}"
            st.caption(source_note)

    with tab_catalog_quality:
        if dimension_catalog.empty:
            st.caption("Catálogo dimensional ainda não materializado. Rode `python scripts/build_fidc_industry_dimensions.py`.")
        else:
            quality = _dimension_catalog_quality_frame(dimension_catalog)
            catalog_gap_actions = _load_catalog_gap_actions()
            gaps = _apply_catalog_gap_actions(_dimension_catalog_gap_frame(dimension_catalog), catalog_gap_actions)
            total_rows = float(len(dimension_catalog))
            gap_rows = float(len(gaps))
            doc_expected = float(pd.to_numeric(quality.get("document_expected_rows", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not quality.empty else 0.0
            with_doc = float(pd.to_numeric(quality.get("with_source_document", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not quality.empty else 0.0
            with_method = float(pd.to_numeric(quality.get("with_source_method", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not quality.empty else 0.0
            with_confidence = float(pd.to_numeric(quality.get("with_confidence", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not quality.empty else 0.0
            cards_quality = [
                _curation_card("Linhas catálogo", _fmt_int(total_rows), f"{_fmt_int(float(dimension_catalog['dimension_id'].nunique())) if 'dimension_id' in dimension_catalog else '0'} dimensões"),
                _curation_card("Com lacuna", _fmt_int(gap_rows), _fmt_pct(gap_rows / total_rows) if total_rows else "n/d"),
                _curation_card("Documento", _fmt_pct(with_doc / doc_expected) if doc_expected else "n/d", "quando esperado"),
                _curation_card("Método", _fmt_pct(with_method / total_rows) if total_rows else "n/d", "todas as linhas"),
                _curation_card("Score", _fmt_pct(with_confidence / total_rows) if total_rows else "n/d", "todas as linhas"),
            ]
            st.markdown(f'<div class="industry-kpi-grid">{"".join(cards_quality)}</div>', unsafe_allow_html=True)
            if not quality.empty:
                plot = quality.sort_values("quality_score", ascending=True).head(18).copy()
                plot["quality_pct"] = pd.to_numeric(plot["quality_score"], errors="coerce").fillna(0.0) * 100
                st.altair_chart(
                    alt.Chart(plot)
                    .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
                    .encode(
                        x=alt.X("quality_pct:Q", title="score de qualidade (%)", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                        y=alt.Y("dimension_label:N", title=None, sort="x", axis=alt.Axis(labelLimit=260)),
                        tooltip=[
                            alt.Tooltip("dimension_label:N", title="dimensão"),
                            alt.Tooltip("rows:Q", title="linhas", format=",.0f"),
                            alt.Tooltip("quality_pct:Q", title="score", format=",.1f"),
                            alt.Tooltip("source_document_ratio:Q", title="% documento", format=".1%"),
                            alt.Tooltip("source_page_ratio:Q", title="% página", format=".1%"),
                        ],
                    )
                    .properties(height=max(260, 22 * len(plot))),
                    width="stretch",
                )
                st.dataframe(_format_dimension_catalog_quality(quality), hide_index=True, width="stretch")
            if not gaps.empty:
                st.markdown("**Fila de lacunas de rastreabilidade**")
                gap_ctrl_a, gap_ctrl_b, gap_ctrl_c = st.columns([1.0, 0.8, 1.2])
                with gap_ctrl_a:
                    dim_options = sorted(gaps["dimension_label"].fillna("").astype(str).unique())
                    selected_dims = st.multiselect("Dimensão", dim_options, default=dim_options[:8], key="industry_catalog_gap_dimensions")
                with gap_ctrl_b:
                    status_options = ["pendente", "em andamento", "corrigido", "aceito", "ignorado"]
                    selected_gap_status = st.multiselect(
                        "Status lacuna",
                        status_options,
                        default=status_options,
                        key="industry_catalog_gap_status",
                    )
                with gap_ctrl_c:
                    gap_query = st.text_input("Buscar lacuna", key="industry_catalog_gap_query", placeholder="valor, FIDC, CNPJ, documento")
                gap_view = gaps[gaps["dimension_label"].isin(selected_dims)].copy() if selected_dims else gaps.iloc[0:0].copy()
                if selected_gap_status and "status_lacuna" in gap_view.columns:
                    gap_view = gap_view[gap_view["status_lacuna"].fillna("").replace("", "pendente").isin(selected_gap_status)].copy()
                if gap_query:
                    search_cols = [
                        col
                        for col in [
                            "dimension_value",
                            "cnpj_fundo",
                            "nome_exibicao",
                            "missing_traceability_fields",
                            "source_document",
                            "acao_revisada",
                            "responsavel",
                            "notas",
                        ]
                        if col in gap_view.columns
                    ]
                    search = gap_view[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=gap_view.index)
                    gap_view = gap_view[search.str.contains(gap_query, case=False, na=False)].copy()
                gap_page = gap_view.head(300).copy()
                gap_display = _format_dimension_catalog_gaps(gap_page)
                edited_catalog_gaps = st.data_editor(
                    gap_display,
                    hide_index=True,
                    width="stretch",
                    height=520,
                    disabled=[
                        "ID",
                        "Dimensão",
                        "Valor",
                        "CNPJ",
                        "FIDC",
                        "Campos faltantes",
                        "Score lacuna",
                        "Atualizado",
                        "Fonte",
                        "Documento",
                        "Página",
                        "Método",
                        "Score",
                        "Revisão",
                        "Tipo participante",
                        "CNPJ participante",
                        "Prioridade 25-26",
                    ],
                    column_config={
                        "Status lacuna": st.column_config.SelectboxColumn(
                            "Status lacuna",
                            options=status_options,
                            required=True,
                        ),
                        "Ação revisada": st.column_config.TextColumn("Ação revisada", width="large"),
                        "Notas": st.column_config.TextColumn("Notas", width="large"),
                    },
                    key="industry_catalog_gap_editor",
                )
                if st.button("Salvar acompanhamento do catálogo", type="primary", key="industry_save_catalog_gap_actions"):
                    edited_actions = pd.DataFrame(
                        {
                            "traceability_gap_id": edited_catalog_gaps["ID"],
                            "status_lacuna": edited_catalog_gaps["Status lacuna"],
                            "acao_revisada": edited_catalog_gaps["Ação revisada"],
                            "responsavel": edited_catalog_gaps["Responsável"],
                            "prazo": edited_catalog_gaps["Prazo"],
                            "notas": edited_catalog_gaps["Notas"],
                            "updated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        }
                    ).fillna("")
                    material_cols = ["status_lacuna", "acao_revisada", "responsavel", "prazo", "notas"]
                    material_mask = edited_actions[material_cols].fillna("").astype(str).apply(
                        lambda row: any(value.strip() and value.strip() != "pendente" for value in row),
                        axis=1,
                    )
                    edited_actions = edited_actions[material_mask].copy()
                    keep_existing = (
                        catalog_gap_actions[
                            ~catalog_gap_actions["traceability_gap_id"].isin(edited_actions["traceability_gap_id"])
                        ].copy()
                        if not catalog_gap_actions.empty
                        else catalog_gap_actions
                    )
                    updated_actions = pd.concat([keep_existing, edited_actions], ignore_index=True)
                    audit_events = build_review_audit_events(
                        previous=_catalog_gap_actions_for_audit(catalog_gap_actions),
                        updated=_catalog_gap_actions_for_audit(updated_actions),
                        key_column="traceability_gap_id",
                        review_domain="dimension_catalog_gap",
                        source="industry_catalog_gap_editor",
                    )
                    audit = append_review_audit_events(audit_events, _CATALOG_GAP_ACTION_AUDIT_PATH)
                    _save_catalog_gap_actions(updated_actions)
                    _load_catalog_gap_actions.clear()
                    st.success(
                        f"Acompanhamento salvo em `{_CATALOG_GAP_ACTIONS_PATH.name}`. "
                        f"Histórico: {len(audit_events):,} eventos novos, {len(audit):,} eventos no total."
                    )
                st.download_button(
                    "Baixar lacunas do catálogo",
                    data=gap_view.to_csv(index=False).encode("utf-8"),
                    file_name="industry_dimension_catalog_traceability_gaps.csv",
                    mime="text/csv",
                    key="industry_catalog_gap_download",
                )
                with st.expander("Histórico das lacunas de rastreabilidade"):
                    _render_review_audit(
                        _CATALOG_GAP_ACTION_AUDIT_PATH,
                        empty_label="Ainda não há histórico de acompanhamento das lacunas do catálogo.",
                    )
            generated_at = dimension_catalog_manifest.get("generated_at_utc", "")
            source_note = f"Fonte: `{_DIMENSION_CATALOG_PATH.name}`"
            if generated_at:
                source_note += f" · gerado em {generated_at}"
            st.caption(source_note)

    with tab_delta:
        st.markdown(
            '<div class="industry-curation-note">Fila operacional da competência atual contra a anterior. '
            "Use para decidir quais CNPJs precisam de descoberta documental, cedentes, critérios ou validação de saída.</div>",
            unsafe_allow_html=True,
        )
        if monthly_delta.empty:
            st.caption("Delta mensal ainda não materializado. Rode `python scripts/build_fidc_industry_monthly_delta.py`.")
        else:
            ctrl_a, ctrl_b, ctrl_c = st.columns([0.9, 0.9, 1.2])
            with ctrl_a:
                bands = sorted([value for value in monthly_delta.get("priority_band", pd.Series(dtype=str)).fillna("").astype(str).unique() if value])
                selected_bands = st.multiselect("Prioridade", bands, default=bands, key="industry_delta_priority")
            with ctrl_b:
                statuses = sorted([value for value in monthly_delta.get("status_delta", pd.Series(dtype=str)).fillna("").astype(str).unique() if value])
                selected_statuses = st.multiselect("Status", statuses, default=statuses, key="industry_delta_status")
            with ctrl_c:
                query = st.text_input("Buscar delta", key="industry_delta_query", placeholder="FIDC, CNPJ, administrador, ação")
            delta = monthly_delta.copy()
            if "delta_id" not in delta.columns and {"competencia_atual", "cnpj_fundo"}.issubset(delta.columns):
                competencia_key = delta["competencia_atual"].fillna("").astype(str).str.replace("-", "", regex=False)
                delta["delta_id"] = competencia_key + "_" + delta["cnpj_fundo"].fillna("").astype(str)
            for col in ["status_acao", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
                if col not in delta.columns:
                    delta[col] = ""
            delta["status_acao"] = delta["status_acao"].fillna("").replace("", "pendente")
            if selected_bands and "priority_band" in delta.columns:
                delta = delta[delta["priority_band"].isin(selected_bands)].copy()
            if selected_statuses and "status_delta" in delta.columns:
                delta = delta[delta["status_delta"].isin(selected_statuses)].copy()
            if query:
                search_cols = [
                    col
                    for col in [
                        "fundo",
                        "cnpj_fundo",
                        "admin_nome",
                        "gestor_nome",
                        "segmento_principal",
                        "next_actions",
                        "status_acao",
                        "acao_revisada",
                        "responsavel",
                        "notas",
                    ]
                    if col in delta.columns
                ]
                search = delta[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=delta.index)
                delta = delta[search.str.contains(query, case=False, na=False)].copy()
            show_cols = [
                "delta_id",
                "competencia_atual",
                "cnpj_fundo",
                "fundo",
                "status_delta",
                "priority_band",
                "priority_score",
                "status_acao",
                "acao_revisada",
                "responsavel",
                "prazo",
                "notas",
                "updated_at_utc",
                "next_actions",
                "pl_atual",
                "pl_delta",
                "captacao_liquida_mes",
                "admin_nome",
                "segmento_principal",
                "document_rows",
                "cedente_rows",
                "criteria_rows",
                "tem_sub_minima",
                "document_chunk_ids",
            ]
            show = delta[[col for col in show_cols if col in delta.columns]].head(400).copy()
            for col in ["pl_atual", "pl_delta", "captacao_liquida_mes"]:
                if col in show.columns:
                    show[col] = pd.to_numeric(show[col], errors="coerce").fillna(0).map(lambda value: _fmt_bi(float(value), 2))
            display = show.rename(
                columns={
                    "delta_id": "ID",
                    "competencia_atual": "Competência",
                    "cnpj_fundo": "CNPJ",
                    "fundo": "FIDC",
                    "status_delta": "Status",
                    "priority_band": "Prioridade",
                    "priority_score": "Score",
                    "status_acao": "Status ação",
                    "acao_revisada": "Ação revisada",
                    "responsavel": "Responsável",
                    "prazo": "Prazo",
                    "notas": "Notas",
                    "updated_at_utc": "Atualizado",
                    "next_actions": "Próximas ações",
                    "pl_atual": "PL atual",
                    "pl_delta": "Delta PL",
                    "captacao_liquida_mes": "Captação mês",
                    "admin_nome": "Administrador",
                    "segmento_principal": "Segmento",
                    "document_rows": "Docs",
                    "cedente_rows": "Cedentes",
                    "criteria_rows": "Critérios",
                    "tem_sub_minima": "Sub mín.",
                    "document_chunk_ids": "Chunks",
                }
            )
            edited = st.data_editor(
                display,
                hide_index=True,
                width="stretch",
                height=560,
                disabled=[
                    "ID",
                    "Competência",
                    "CNPJ",
                    "FIDC",
                    "Status",
                    "Prioridade",
                    "Score",
                    "Atualizado",
                    "Próximas ações",
                    "PL atual",
                    "Delta PL",
                    "Captação mês",
                    "Administrador",
                    "Segmento",
                    "Docs",
                    "Cedentes",
                    "Critérios",
                    "Sub mín.",
                    "Chunks",
                ],
                column_config={
                    "ID": st.column_config.TextColumn("ID", width="small"),
                    "Status ação": st.column_config.SelectboxColumn(
                        "Status ação",
                        options=["pendente", "em andamento", "concluído", "ignorado"],
                        required=True,
                    ),
                    "Ação revisada": st.column_config.TextColumn("Ação revisada", width="large"),
                    "Notas": st.column_config.TextColumn("Notas", width="large"),
                    "Próximas ações": st.column_config.TextColumn("Próximas ações", width="large"),
                },
                key="industry_monthly_delta_editor",
            )
            if st.button("Salvar acompanhamento do delta", type="primary", key="industry_save_monthly_delta_actions"):
                edited_actions = pd.DataFrame(
                    {
                        "delta_id": edited["ID"].fillna("").astype(str),
                        "status_acao": edited["Status ação"].fillna("").astype(str).replace("", "pendente"),
                        "acao_revisada": edited["Ação revisada"].fillna("").astype(str),
                        "responsavel": edited["Responsável"].fillna("").astype(str),
                        "prazo": edited["Prazo"].fillna("").astype(str),
                        "notas": edited["Notas"].fillna("").astype(str),
                        "updated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    }
                )
                text_cols = ["acao_revisada", "responsavel", "prazo", "notas"]
                material = edited_actions["status_acao"].ne("pendente") | (
                    edited_actions[text_cols].fillna("").astype(str).agg(" ".join, axis=1).str.strip().ne("")
                )
                edited_actions = edited_actions[edited_actions["delta_id"].str.strip().ne("") & material].copy()
                visible_ids = set(edited["ID"].fillna("").astype(str))
                existing = monthly_delta_actions.copy()
                if not existing.empty and "delta_id" in existing.columns:
                    existing = existing[~existing["delta_id"].fillna("").astype(str).isin(visible_ids)].copy()
                updated_actions = pd.concat([existing, edited_actions], ignore_index=True)
                audit_events = build_review_audit_events(
                    previous=_monthly_delta_actions_for_audit(monthly_delta_actions),
                    updated=_monthly_delta_actions_for_audit(updated_actions),
                    key_column="delta_id",
                    review_domain="monthly_delta_action",
                    source="industry_monthly_delta_editor",
                )
                audit = append_review_audit_events(audit_events, _MONTHLY_DELTA_ACTION_AUDIT_PATH)
                save_monthly_delta_actions(updated_actions, _MONTHLY_DELTA_ACTIONS_PATH)
                _load_monthly_delta_tables.clear()
                st.success(
                    f"Acompanhamento salvo para {_fmt_int(float(len(edited_actions)))} linhas visíveis. "
                    f"Histórico: {len(audit_events):,} eventos novos, {len(audit):,} eventos no total."
                )
            with st.expander("Histórico do acompanhamento mensal"):
                _render_review_audit(
                    _MONTHLY_DELTA_ACTION_AUDIT_PATH,
                    empty_label="Ainda não há histórico de acompanhamento do delta mensal.",
                )

    with tab_refresh:
        st.markdown(
            '<div class="industry-curation-note">A ordem abaixo foi pensada para atualização mensal: '
            "primeiro os informes e séries granulares, depois camadas derivadas, e por último o próprio índice. "
            "Os módulos documentais e de curadoria podem ser reexecutados em lotes.</div>",
            unsafe_allow_html=True,
        )
        plan_frame = pd.DataFrame(monthly_update_plan)
        if not plan_frame.empty:
            plan_status = plan_frame.get("status_prontidao", pd.Series("", index=plan_frame.index)).fillna("").astype(str).value_counts().to_dict()
            plan_cards = [
                _curation_card("Etapas plano", _fmt_int(float(len(plan_frame))), "ordem mensal"),
                _curation_card("Bloqueadas", _fmt_int(float(plan_status.get("bloqueado", 0))), "não publicar antes de fechar"),
                _curation_card("Em atenção", _fmt_int(float(plan_status.get("atenção", 0))), "rodar com ressalva"),
                _curation_card("Prontas", _fmt_int(float(plan_status.get("ok", 0))), "sem bloqueio vinculado"),
            ]
            st.markdown("**Plano operacional da competência**")
            st.markdown(f'<div class="industry-kpi-grid">{"".join(plan_cards)}</div>', unsafe_allow_html=True)
            plan_a, plan_b, plan_c = st.columns([0.9, 0.9, 1.4])
            with plan_a:
                phase_options = sorted([value for value in plan_frame.get("fase", pd.Series(dtype=str)).fillna("").astype(str).unique() if value])
                selected_phases = st.multiselect(
                    "Fase",
                    phase_options,
                    default=phase_options,
                    key="industry_monthly_update_plan_phase",
                )
            with plan_b:
                plan_status_options = [value for value in ["bloqueado", "atenção", "ok"] if value in set(plan_frame.get("status_prontidao", pd.Series(dtype=str)).fillna("").astype(str))]
                selected_plan_status = st.multiselect(
                    "Prontidão etapa",
                    plan_status_options,
                    default=plan_status_options,
                    key="industry_monthly_update_plan_status",
                )
            with plan_c:
                plan_query = st.text_input(
                    "Buscar etapa",
                    key="industry_monthly_update_plan_query",
                    placeholder="informes, cedentes, chunks, heatmaps, validação",
                )
            plan_view = plan_frame.copy()
            if selected_phases:
                plan_view = plan_view[plan_view.get("fase", pd.Series("", index=plan_view.index)).fillna("").astype(str).isin(selected_phases)].copy()
            if selected_plan_status:
                plan_view = plan_view[
                    plan_view.get("status_prontidao", pd.Series("", index=plan_view.index)).fillna("").astype(str).isin(selected_plan_status)
                ].copy()
            if plan_query:
                search_cols = [
                    col
                    for col in [
                        "fase",
                        "etapa",
                        "status_prontidao",
                        "bloqueios_ou_atencoes",
                        "acao_antes_de_rodar",
                        "comando",
                        "entradas",
                        "saidas",
                        "evidencia_atual",
                        "motivo",
                        "incrementalidade",
                    ]
                    if col in plan_view.columns
                ]
                search = plan_view[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=plan_view.index)
                plan_view = plan_view[search.str.contains(plan_query, case=False, na=False)].copy()
            if "order" in plan_view.columns:
                plan_view = plan_view.sort_values("order").copy()
            st.dataframe(_format_monthly_update_plan(plan_view), hide_index=True, width="stretch", height=460)
            st.download_button(
                "Baixar plano mensal",
                data=plan_frame.to_csv(index=False).encode("utf-8"),
                file_name="industry_monthly_update_plan.csv",
                mime="text/csv",
                key="industry_monthly_update_plan_download",
            )
        else:
            st.caption("Plano operacional mensal ainda não materializado no índice.")

        snapshot_tables = _load_fund_snapshot_tables()
        fund_snapshot = snapshot_tables["snapshot"]
        assert isinstance(fund_snapshot, pd.DataFrame)
        readiness = _monthly_readiness_frame(
            index=index,
            monthly_delta=monthly_delta,
            snapshot=fund_snapshot,
            dimension_catalog=dimension_catalog,
            snapshot_gap_actions=_load_snapshot_gap_actions(),
            catalog_gap_actions=_load_catalog_gap_actions(),
        )
        if not readiness.empty:
            readiness_status = readiness["status_prontidao"].value_counts().to_dict()
            open_readiness = readiness[~readiness["status_prontidao"].eq("ok")].copy()
            pending_total = float(pd.to_numeric(open_readiness.get("pendencias", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
            st.markdown("**Prontidão da competência**")
            readiness_cards = [
                _curation_card("Bloqueios", _fmt_int(float(readiness_status.get("bloqueado", 0))), "precisam fechar antes da publicação"),
                _curation_card("Atenções", _fmt_int(float(readiness_status.get("atenção", 0))), "não bloqueiam, mas entram no log"),
                _curation_card("Checks ok", _fmt_int(float(readiness_status.get("ok", 0))), "prontos para refresh"),
                _curation_card("Pendências abertas", _fmt_int(pending_total), "somente checks não-ok"),
            ]
            st.markdown(f'<div class="industry-kpi-grid">{"".join(readiness_cards)}</div>', unsafe_allow_html=True)
            ready_a, ready_b = st.columns([0.8, 1.2])
            with ready_a:
                readiness_options = [value for value in ["bloqueado", "atenção", "ok"] if value in set(readiness["status_prontidao"])]
                readiness_default = [value for value in readiness_options if value != "ok"] or readiness_options
                selected_readiness = st.multiselect(
                    "Status prontidão",
                    readiness_options,
                    default=readiness_default,
                    key="industry_monthly_readiness_status",
                )
            with ready_b:
                readiness_query = st.text_input(
                    "Buscar prontidão",
                    key="industry_monthly_readiness_query",
                    placeholder="frente, escopo, amostra, ação ou fonte",
                )
            readiness_view = readiness[readiness["status_prontidao"].isin(selected_readiness)].copy() if selected_readiness else readiness.iloc[0:0].copy()
            if readiness_query:
                search_cols = [
                    col
                    for col in ["frente", "escopo", "status_prontidao", "amostra", "acao_sugerida", "fonte", "comando"]
                    if col in readiness_view.columns
                ]
                search = readiness_view[search_cols].fillna("").astype(str).agg(" ".join, axis=1) if search_cols else pd.Series("", index=readiness_view.index)
                readiness_view = readiness_view[search.str.contains(readiness_query, case=False, na=False)].copy()
            st.dataframe(_format_monthly_readiness(readiness_view), hide_index=True, width="stretch")
            st.download_button(
                "Baixar prontidão mensal",
                data=readiness.to_csv(index=False).encode("utf-8"),
                file_name="industry_monthly_readiness.csv",
                mime="text/csv",
                key="industry_monthly_readiness_download",
            )
        persisted_readiness = pd.DataFrame(index.get("readiness_checks", []))
        if not persisted_readiness.empty:
            with st.expander("Checklist persistido no índice"):
                st.caption(
                    "Este checklist vem de `industry_pipeline_index.json` e usa apenas manifestos, artefatos e rollups. "
                    "A tabela acima recalcula também lacunas linha a linha quando as bases estruturadas estão disponíveis."
                )
                st.dataframe(_format_monthly_readiness(persisted_readiness), hide_index=True, width="stretch")

        refresh_rows = []
        for stage in refresh_plan:
            if not isinstance(stage, dict):
                continue
            refresh_rows.append(
                {
                    "Ordem": stage.get("order", ""),
                    "Módulo": stage.get("label", stage.get("module_id", "")),
                    "Comando": stage.get("command", ""),
                    "Por quê": stage.get("reason", ""),
                    "Incrementalidade": stage.get("incremental_note", ""),
                }
            )
        if refresh_rows:
            st.dataframe(pd.DataFrame(refresh_rows), hide_index=True, width="stretch")
        else:
            st.caption("Plano de refresh não encontrado no índice.")

    with tab_artifacts:
        artifact_rows = []
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            artifact_rows.append(
                {
                    "Módulo": item.get("module_id", ""),
                    "Grupo": item.get("group", ""),
                    "Artefato": item.get("artifact", ""),
                    "Existe": "sim" if item.get("exists") is True else "não",
                    "Bytes": _fmt_int(float(item.get("bytes", 0))) if item.get("bytes") not in ("", None) else "",
                    "SHA-256": str(item.get("sha256", ""))[:16],
                    "Caminho": item.get("path", ""),
                }
            )
        if artifact_rows:
            artifact_frame = pd.DataFrame(artifact_rows)
            col_status, col_module = st.columns([1, 1])
            with col_status:
                status_filter = st.multiselect(
                    "Status do artefato",
                    ["sim", "não"],
                    default=["sim", "não"],
                    key="industry_pipeline_artifact_status",
                )
            with col_module:
                module_options = sorted(artifact_frame["Módulo"].dropna().astype(str).unique())
                module_filter = st.multiselect(
                    "Módulo",
                    module_options,
                    default=module_options,
                    key="industry_pipeline_artifact_module",
                )
            filtered = artifact_frame[
                artifact_frame["Existe"].isin(status_filter) & artifact_frame["Módulo"].isin(module_filter)
            ].copy()
            st.dataframe(filtered, hide_index=True, width="stretch")
        else:
            st.caption("Índice de artefatos vazio.")

    with tab_json:
        st.download_button(
            "Baixar índice",
            data=json.dumps(index, ensure_ascii=False, indent=2),
            file_name="industry_pipeline_index.json",
            mime="application/json",
        )
        st.json(index)

    legacy_manifest = _load_industry_pipeline_manifest()
    if legacy_manifest:
        with st.expander("Manifesto legado de cedentes"):
            st.json(legacy_manifest)


def _render_regulatory_curation_overlay() -> None:
    overlay = _load_regulatory_overlay()
    summary = overlay["summary"]
    assert isinstance(summary, dict)

    if not int(summary.get("universe_funds", 0)) and not int(summary.get("criteria_rows", 0)):
        return

    st.markdown('<div class="industry-section">Curadoria regulatória do universo</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Leitura documental estruturada para cedentes/sacados, subordinação mínima e critérios monitoráveis. '
        "As contagens abaixo são de curadoria, não de informação obrigatória padronizada no IME.</div>",
        unsafe_allow_html=True,
    )

    cards = [
        _curation_card("CNPJs no SQLite", _fmt_int(float(summary.get("universe_funds", 0))), f"data-base {summary.get('db_date') or 'n/d'}"),
        _curation_card("Matrizes lidas", _fmt_int(float(summary.get("matrix_funds", 0))), "regulamentos/documentos parseados"),
        _curation_card("Cedente/originador", _fmt_int(float(summary.get("cedente_funds", 0))), "FIDCs com menção nomeada"),
        _curation_card("Sacado/devedor", _fmt_int(float(summary.get("sacado_funds", 0))), "FIDCs com menção nomeada"),
        _curation_card("Sub mínima mediana", _pct_label(summary.get("sub_median")), f"{_fmt_int(float(summary.get('sub_rules', 0)))} regras · {_fmt_int(float(summary.get('sub_funds', 0)))} FIDCs"),
        _curation_card("Critérios all FIDCs", _fmt_int(float(summary.get("criteria_rows", 0))), f"{_fmt_int(float(summary.get('criteria_funds', 0)))} FIDCs com evidência"),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="industry-curation-note">Sub mínima: mediana dos percentuais mínimos extraídos em '
        f'<code>{_ALL_FIDCS_CRITERIA.name}</code>; intervalo interquartil '
        f'{_pct_label(summary.get("sub_p25"))}–{_pct_label(summary.get("sub_p75"))}. '
        "Quando há mais de um percentual na mesma regra, usa-se o menor valor explícito como mínimo conservador.</div>",
        unsafe_allow_html=True,
    )

    sector_summary = overlay["sector_summary"]
    candidate_summary = overlay["candidate_summary"]
    candidate_examples = overlay["candidate_examples"]
    criteria_summary = overlay["criteria_summary"]
    sub_rules = overlay["sub_rules"]
    queue_summary = overlay["queue_summary"]

    left, right = st.columns([1.2, 0.8])
    with left:
        st.markdown("**Cobertura por setor**")
        if isinstance(sector_summary, pd.DataFrame) and not sector_summary.empty:
            st.dataframe(sector_summary.head(12), hide_index=True, width="stretch")
        else:
            st.caption("Sem cobertura setorial disponível.")
    with right:
        st.markdown("**Cedente, sacado e consultora**")
        if isinstance(candidate_summary, pd.DataFrame) and not candidate_summary.empty:
            display = candidate_summary.head(12).copy()
            display["Tipo"] = display["Tipo"].replace(
                {
                    "cedente_originador": "cedente/originador",
                    "sacado_devedor": "sacado/devedor",
                    "consultora": "consultora",
                }
            )
            st.dataframe(display, hide_index=True, width="stretch")
        else:
            st.caption("Sem evidências de participantes no cache regulatório.")

    tab_sub, tab_criteria, tab_examples, tab_queue = st.tabs(["Sub mínima", "Critérios", "Cedentes", "Fila"])
    with tab_sub:
        if isinstance(sub_rules, pd.DataFrame) and not sub_rules.empty:
            cols = ["Fundo", "CNPJ", "Limite/regra", "pct_min", "Monitorabilidade IME", "Fonte", "Status curadoria"]
            table = sub_rules[[col for col in cols if col in sub_rules.columns]].copy()
            if "pct_min" in table.columns:
                table["Mínimo extraído"] = table.pop("pct_min").map(_pct_label)
            st.dataframe(table.head(40), hide_index=True, width="stretch")
        else:
            st.caption("Nenhuma regra de subordinação mínima encontrada na curadoria all FIDCs.")
    with tab_criteria:
        if isinstance(criteria_summary, pd.DataFrame) and not criteria_summary.empty:
            st.dataframe(criteria_summary, hide_index=True, width="stretch")
        else:
            st.caption("Resumo de critérios indisponível.")
    with tab_examples:
        if isinstance(candidate_examples, pd.DataFrame) and not candidate_examples.empty:
            display = candidate_examples.copy()
            display["Tipo"] = display["Tipo"].replace(
                {
                    "cedente_originador": "cedente/originador",
                    "sacado_devedor": "sacado/devedor",
                    "consultora": "consultora",
                }
            )
            st.dataframe(display, hide_index=True, width="stretch")
        else:
            st.caption(
                "Há evidências textuais de cedente/sacado, mas poucos nomes limpos o bastante para exibir sem revisão manual."
            )
    with tab_queue:
        if isinstance(queue_summary, pd.DataFrame) and not queue_summary.empty:
            st.dataframe(queue_summary, hide_index=True, width="stretch")
        else:
            st.caption("Fila de curadoria não encontrada no SQLite regulatório.")


def _render_tab_industry_study_legacy() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

    industry = _load_csv(
        "industry_monthly.csv",
        _industry_files_signature(("industry_monthly.csv",)),
    )
    if industry is None or industry.empty:
        st.info(
            "Agregados da indústria não encontrados em `data/industry_study/`. "
            "Rode `python scripts/build_fidc_industry_study.py --report` para gerá-los."
        )
        return

    industry = _drop_partial_tail(industry)
    industry = _month_axis(industry)
    last = industry.iloc[-1]
    comp = last["competencia"]
    ano_anterior = f"{int(comp[:4]) - 1}{comp[4:]}"
    ref_12m = industry[industry["competencia"] == ano_anterior]
    ref_12m = ref_12m.iloc[0] if not ref_12m.empty else None
    capt_12m = industry.tail(12)["captacao_liquida"].sum()

    metadata = _load_metadata()
    serie_ini = str(metadata.get("competencia_inicial", "201301"))

    st.markdown(
        f"""
        <div class="industry-header">
          <div class="industry-kicker">Indústria FIDCs</div>
          <div class="industry-title">Crescimento, fluxos e concentração</div>
          <div class="industry-subtitle">
            Série CVM reconstruída de {serie_ini[:4]} até <b>{comp}</b>, com PL, captação líquida,
            cotistas, inadimplência e administradores. Universo CVM pode divergir da ANBIMA; metodologia no rodapé.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    def _kpi(label: str, value: str, note: str = "") -> str:
        note_html = f'<div class="industry-kpi-note">{note}</div>' if note else ""
        return (
            f'<div class="industry-kpi"><div class="industry-kpi-label">{label}</div>'
            f'<div class="industry-kpi-value">{value}</div>{note_html}</div>'
        )

    concentration = _load_csv(
        "concentration_monthly.csv",
        _industry_files_signature(("concentration_monthly.csv",)),
    )
    conc_last = None
    if concentration is not None and not concentration.empty:
        conc_match = concentration[concentration["competencia"] == comp]
        conc_last = conc_match.iloc[0] if not conc_match.empty else None

    pl_delta = (last["pl_total"] / ref_12m["pl_total"] - 1) if ref_12m is not None else None
    cot_delta = (
        (last["cotistas_total"] / ref_12m["cotistas_total"] - 1)
        if ref_12m is not None and ref_12m["cotistas_total"]
        else None
    )
    pl_ex_fic = float(last["pl_total"] - last.get("pl_fic_fidc", 0))
    kpis = [
        _kpi(
            "PL total",
            _fmt_bi(last["pl_total"], 0),
            f"{_fmt_bi(pl_ex_fic, 0)} ex-FIC-FIDC · +{_fmt_pct(pl_delta)} em 12m"
            if pl_delta is not None
            else f"{_fmt_bi(pl_ex_fic, 0)} ex-FIC-FIDC",
        ),
        _kpi("Captação líquida 12m", _fmt_bi(capt_12m, 0), "captações − resgates − amortizações"),
        _kpi("Veículos reportantes", _fmt_int(last["n_veiculos"]), f"+{_fmt_int(last['n_veiculos'] - ref_12m['n_veiculos'])} em 12m" if ref_12m is not None else ""),
        _kpi("Contas de cotistas", f"{_fmt_int(last['cotistas_total'] / 1000)} mil", f"+{_fmt_pct(cot_delta)} em 12m" if cot_delta is not None else ""),
        _kpi("Inadimplência ajustada", _fmt_pct(last["inad_pct_ajustada"]), f"bruta: {_fmt_pct(last['inad_pct'])}"),
        _kpi("Top 5 administradores", _fmt_pct(conc_last["share_top5"]) if conc_last is not None else "n/d", "do PL administrado"),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(kpis)}</div>', unsafe_allow_html=True)

    vehicle = _load_csv(
        "vehicle_monthly.csv.gz",
        _industry_files_signature(("vehicle_monthly.csv.gz",)),
    )
    universe_tab, audit_tab, issuance_tab, documents_tab, criteria_tab, heatmap_tab, cedente_tab, deep_dive_tab, pipeline_tab = st.tabs(
        ["Universo", "Base granular", "Emissões", "Documentos", "Critérios", "Heatmaps", "Cedentes", "Deep Dive", "Pipeline"]
    )
    with universe_tab:
        _render_fund_snapshot_universe()
    with audit_tab:
        _render_monthly_audit_and_base(industry, comp)
    with issuance_tab:
        _render_issuance_study()
    with documents_tab:
        _render_document_inventory()
    with criteria_tab:
        _render_criteria_study()
    with heatmap_tab:
        _render_generic_heatmaps(vehicle, comp)
    with cedente_tab:
        _render_cedente_review_workbench()
    with deep_dive_tab:
        _render_industry_deep_dive(vehicle, comp)
    with pipeline_tab:
        _render_pipeline_manifest()

    # --- PL da industria -------------------------------------------------
    st.markdown('<div class="industry-section">Patrimônio líquido da indústria</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Soma do PL de todos os veículos reportantes (Tab IV), em R$ bilhões. '
        "A linha preta remove FIC-FIDC para reduzir dupla contagem potencial; picos de um único mês por veículo são excluídos.</div>",
        unsafe_allow_html=True,
    )
    pl_df = industry.assign(
        total_bi=industry["pl_total"] / 1e9,
        ex_fic_bi=(industry["pl_total"] - industry["pl_fic_fidc"].fillna(0)) / 1e9,
    )
    pl_long = pd.concat(
        [
            pl_df.assign(serie="FIDCs + FIC-FIDCs", valor_bi=pl_df["total_bi"]),
            pl_df.assign(serie="Somente FIDCs (ex-FIC-FIDCs)", valor_bi=pl_df["ex_fic_bi"]),
        ],
        ignore_index=True,
    )
    area = (
        alt.Chart(pl_df)
        .mark_area(color=_ORANGE_SOFT)
        .encode(
            x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False)),
            y=alt.Y("total_bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
            tooltip=[
                alt.Tooltip("competencia:N", title="competência"),
                alt.Tooltip("total_bi:Q", title="PL total (R$ bi)", format=",.1f"),
                alt.Tooltip("ex_fic_bi:Q", title="PL ex-FIC-FIDC (R$ bi)", format=",.1f"),
            ],
        )
    )
    lines = (
        alt.Chart(pl_long)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False)),
            y=alt.Y("valor_bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
            color=alt.Color(
                "serie:N",
                scale=alt.Scale(
                    domain=["FIDCs + FIC-FIDCs", "Somente FIDCs (ex-FIC-FIDCs)"],
                    range=[_ORANGE, _BLACK],
                ),
                legend=alt.Legend(title=None, orient="top"),
            ),
            strokeDash=alt.StrokeDash(
                "serie:N",
                scale=alt.Scale(
                    domain=["FIDCs + FIC-FIDCs", "Somente FIDCs (ex-FIC-FIDCs)"],
                    range=[[1, 0], [5, 3]],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("competencia:N", title="competência"),
                alt.Tooltip("serie:N", title="série"),
                alt.Tooltip("valor_bi:Q", title="PL (R$ bi)", format=",.1f"),
            ],
        )
    )
    st.altair_chart((area + lines).properties(height=300), width="stretch")
    fic_impact = _pl_fic_impact_frame(industry)
    if not fic_impact.empty:
        latest_fic = fic_impact.iloc[-1]
        fic_share = float(latest_fic.get("fic_share", 0.0))
        last_12 = fic_impact.tail(12)
        max_12 = last_12.loc[last_12["fic_share"].idxmax()] if not last_12.empty else latest_fic
        fic_cards = [
            _curation_card("PL sem FIC-FIDC", _fmt_bi(float(latest_fic.get("pl_ex_fic_fidc", 0.0)), 1), str(latest_fic.get("competencia", ""))),
            _curation_card("PL em FIC-FIDC", _fmt_bi(float(latest_fic.get("pl_fic_fidc", 0.0)), 1), _fmt_pct(fic_share)),
            _curation_card("Maior impacto 12m", _fmt_pct(float(max_12.get("fic_share", 0.0))), str(max_12.get("competencia", ""))),
        ]
        st.markdown(f'<div class="industry-kpi-grid">{"".join(fic_cards)}</div>', unsafe_allow_html=True)
        recent_fic = fic_impact.tail(12).copy()
        recent_fic["PL total"] = recent_fic["pl_total"].map(lambda value: _fmt_bi(float(value), 1))
        recent_fic["Somente FIDCs"] = recent_fic["pl_ex_fic_fidc"].map(lambda value: _fmt_bi(float(value), 1))
        recent_fic["FIC-FIDC"] = recent_fic["pl_fic_fidc"].map(lambda value: _fmt_bi(float(value), 1))
        recent_fic["% FIC-FIDC"] = recent_fic["fic_share"].map(lambda value: _fmt_pct(float(value)))
        st.dataframe(
            recent_fic[["competencia", "PL total", "Somente FIDCs", "FIC-FIDC", "% FIC-FIDC"]].rename(
                columns={"competencia": "Competência"}
            ),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Metodologia: `FIDCs + FIC-FIDCs` soma todos os veículos reportantes; `Somente FIDCs` subtrai veículos "
            "classificados como FIC-FIDC para reduzir dupla contagem potencial. A subtração é uma aproximação conservadora, "
            "pois não recompõe as carteiras investidas pelos FICs."
        )

    col_a, col_b = st.columns(2)

    # --- Captacao liquida mensal -----------------------------------------
    with col_a:
        st.markdown('<div class="industry-section">Captação líquida mensal</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="industry-def">Captações − resgates − amortizações (Tab X.4), últimos 48 meses. '
            f'Laranja = {_LABELS["entrada"]}; preto = {_LABELS["saida"]}.</div>',
            unsafe_allow_html=True,
        )
        flow_df = industry.tail(48).assign(capt_bi=lambda d: d["captacao_liquida"] / 1e9)
        flow_df["sinal"] = flow_df["capt_bi"].map(lambda v: _LABELS["entrada"] if v >= 0 else _LABELS["saida"])
        bars = (
            alt.Chart(flow_df)
            .mark_bar(size=6, cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
            .encode(
                x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False)),
                y=alt.Y("capt_bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                color=alt.Color(
                    "sinal:N",
                    scale=alt.Scale(
                        domain=[_LABELS["entrada"], _LABELS["saida"]],
                        range=[_ORANGE, _BLACK],
                    ),
                    legend=alt.Legend(title=None, orient="top"),
                ),
                tooltip=[
                    alt.Tooltip("competencia:N", title="competência"),
                    alt.Tooltip("capt_bi:Q", title="captação líq. (R$ bi)", format=",.2f"),
                ],
            )
            .properties(height=260)
        )
        st.altair_chart(bars, width="stretch")

    # --- Cotistas ---------------------------------------------------------
    with col_b:
        st.markdown('<div class="industry-section">Contas de cotistas</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="industry-def">Mil contas por classe/série (Tab X.1) — não são CPFs únicos. '
            "O salto pós-2024 reflete o acesso do varejo via RCVM 175.</div>",
            unsafe_allow_html=True,
        )
        cot_df = industry.assign(cot_mil=industry["cotistas_total"] / 1000)
        st.altair_chart(
            _base_line(cot_df, "cot_mil", "mil contas", _ORANGE).properties(height=260),
            width="stretch",
        )

    col_c, col_d = st.columns(2)

    # --- Inadimplencia ------------------------------------------------------
    with col_c:
        st.markdown('<div class="industry-section">Inadimplência da carteira</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="industry-def">% da carteira de direitos creditórios (Tab I). '
            f'Laranja = {_LABELS["inad_ajustada"]}; preto = {_LABELS["inad_bruta"]}.</div>',
            unsafe_allow_html=True,
        )
        inad_long = pd.concat(
            [
                industry.assign(serie="ajustada", pct=industry["inad_pct_ajustada"] * 100),
                industry.assign(serie="bruta", pct=industry["inad_pct"] * 100),
            ]
        )
        inad_chart = (
            alt.Chart(inad_long)
            .mark_line(strokeWidth=2)
            .encode(
                x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False)),
                y=alt.Y("pct:Q", title="% da carteira", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                color=alt.Color(
                    "serie:N",
                    scale=alt.Scale(domain=["ajustada", "bruta"], range=[_ORANGE, _BLACK]),
                    legend=alt.Legend(title=None, orient="top"),
                ),
                tooltip=[
                    alt.Tooltip("competencia:N", title="competência"),
                    alt.Tooltip("serie:N", title="série"),
                    alt.Tooltip("pct:Q", title="%", format=",.1f"),
                ],
            )
            .properties(height=260)
        )
        st.altair_chart(inad_chart, width="stretch")

    # --- Concentracao -------------------------------------------------------
    with col_d:
        st.markdown('<div class="industry-section">Concentração de administradores</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="industry-def">Participação no PL total administrado. '
            f'Laranja = {_LABELS["top10"]}; preto = {_LABELS["top5"]}.</div>',
            unsafe_allow_html=True,
        )
        if concentration is not None and not concentration.empty:
            conc_df = _month_axis(concentration[concentration["competencia"] <= comp])
            conc_long = pd.concat(
                [
                    conc_df.assign(serie="top 10", pct=conc_df["share_top10"] * 100),
                    conc_df.assign(serie="top 5", pct=conc_df["share_top5"] * 100),
                ]
            )
            conc_chart = (
                alt.Chart(conc_long)
                .mark_line(strokeWidth=2)
                .encode(
                    x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False)),
                    y=alt.Y("pct:Q", title="% do PL", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    color=alt.Color(
                        "serie:N",
                        scale=alt.Scale(domain=["top 10", "top 5"], range=[_ORANGE, _BLACK]),
                        legend=alt.Legend(title=None, orient="top"),
                    ),
                    tooltip=[
                        alt.Tooltip("competencia:N", title="competência"),
                        alt.Tooltip("serie:N", title="série"),
                        alt.Tooltip("pct:Q", title="%", format=",.1f"),
                    ],
                )
                .properties(height=260)
            )
            st.altair_chart(conc_chart, width="stretch")
        else:
            st.caption("Série de concentração indisponível.")

    col_e, col_f = st.columns(2)

    # --- Segmentos ------------------------------------------------------------
    with col_e:
        st.markdown('<div class="industry-section">Carteira por tipo de recebível</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="industry-def">R$ bilhões em {comp} · classificação oficial da Tab II.</div>',
            unsafe_allow_html=True,
        )
        segments = _load_csv(
            "segments_monthly.csv",
            _industry_files_signature(("segments_monthly.csv",)),
        )
        if segments is not None and not segments.empty:
            seg = segments[(segments["competencia"] == comp) & (segments["nivel"] == "top")]
            seg = seg[seg["valor"] > 5e7].sort_values("valor", ascending=False)
            seg = seg.assign(valor_bi=seg["valor"] / 1e9)
            seg_chart = (
                alt.Chart(seg)
                .mark_bar(color=_ORANGE, size=14, cornerRadiusEnd=2)
                .encode(
                    x=alt.X("valor_bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    y=alt.Y("segmento:N", title=None, sort="-x"),
                    tooltip=[
                        alt.Tooltip("segmento:N", title="segmento"),
                        alt.Tooltip("valor_bi:Q", title="R$ bi", format=",.1f"),
                    ],
                )
                .properties(height=280)
            )
            st.altair_chart(seg_chart, width="stretch")

    # --- Top administradores ---------------------------------------------------
    with col_f:
        st.markdown('<div class="industry-section">Top 10 administradores por PL</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="industry-def">R$ bilhões em {comp} (Tab I + IV, auditável mês a mês).</div>',
            unsafe_allow_html=True,
        )
        prestadores = _load_csv(
            "prestadores_latest.csv",
            _industry_files_signature(("prestadores_latest.csv",)),
        )
        if prestadores is not None and not prestadores.empty:
            adm = prestadores[prestadores["papel"] == "administrador"].head(10).copy()
            adm["pl_bi"] = adm["pl"] / 1e9
            adm["nome_curto"] = adm["nome"].map(_short_prestador)
            adm_chart = (
                alt.Chart(adm)
                .mark_bar(color=_ORANGE, size=14, cornerRadiusEnd=2)
                .encode(
                    x=alt.X("pl_bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    y=alt.Y("nome_curto:N", title=None, sort="-x", axis=alt.Axis(labelLimit=230)),
                    tooltip=[
                        alt.Tooltip("nome:N", title="administrador"),
                        alt.Tooltip("pl_bi:Q", title="PL (R$ bi)", format=",.1f"),
                        alt.Tooltip("n_veiculos:Q", title="veículos"),
                    ],
                )
                .properties(height=280)
            )
            st.altair_chart(adm_chart, width="stretch")

    _render_regulatory_curation_overlay()

    # --- Tabelas e metodologia ---------------------------------------------------
    with st.expander("Dados anuais (dezembro de cada ano)"):
        dez = industry[
            industry["competencia"].str.endswith("-12") | (industry["competencia"] == comp)
        ].copy()
        tabela = pd.DataFrame(
            {
                "Competência": dez["competencia"],
                "PL (R$ bi)": (dez["pl_total"] / 1e9).round(1),
                "Veículos": dez["n_veiculos"].astype(int),
                "Contas de cotistas": dez["cotistas_total"].astype(int),
                "Captação líq. no mês (R$ bi)": (dez["captacao_liquida"] / 1e9).round(2),
                "Inad. ajustada (%)": (dez["inad_pct_ajustada"] * 100).round(1),
            }
        )
        st.dataframe(tabela, hide_index=True, width="stretch")

    with st.expander("Metodologia, fontes e limitações"):
        st.markdown(
            """
- **Fonte:** dataset público *FIDC — Documentos: Informe Mensal* (Portal de Dados
  Abertos da CVM) e cadastro `registro_fundo_classe`. Reconstrução via
  `scripts/build_fidc_industry_study.py`; agregados versionados em `data/industry_study/`.
- **Unidade:** veículo reportante — fundo até a adaptação à RCVM 175, classe depois
  (sem sobreposição de CNPJ entre os dois grupos; veículos ≈ fundos únicos, pois a
  quase totalidade das classes usa o CNPJ do próprio fundo).
- **Inadimplência ajustada:** a inadimplência de cada veículo é limitada à sua
  própria carteira antes da agregação — corrige compradores de NPL que reportam
  créditos vencidos a valor de face contra carteira a valor contábil.
- **Filtros de sanidade:** fluxos da Tab X.4 acima de max(3× PL do veículo, R$ 2 bi)
  e picos de um único mês (>20× o mês anterior e o seguinte) são descartados como
  erro de preenchimento.
- **Por que não bate com ANBIMA/Uqbar:** universo (CVM inclui exclusivos, NP e
  FIC-FIDC), conceito (captação líquida ≠ emissões/ofertas), data-base e contas
  vs investidores únicos. Reconciliação completa no relatório
  `reports/fidc_industry_study.md`.
            """
        )


# ---------------------------------------------------------------------------
# Executive product surface
# ---------------------------------------------------------------------------

_EXECUTIVE_CSS = """
<style>
.industry-status-band {
    align-items: center;
    background: #fff7f1;
    border-left: 4px solid #EC7000;
    display: grid;
    gap: 1rem;
    grid-template-columns: minmax(12rem, 1.1fr) minmax(16rem, 3fr);
    margin: 0.2rem 0 0.85rem 0;
    padding: 0.7rem 0.85rem;
}
.industry-status-band strong { color: #1a1a1a; font-size: 0.9rem; }
.industry-status-band span { color: #595959; font-size: 0.82rem; line-height: 1.4; }
.industry-thesis {
    border-bottom: 1px solid #e5e3e0;
    border-top: 1px solid #e5e3e0;
    color: #1a1a1a;
    font-size: 1rem;
    font-weight: 650;
    line-height: 1.45;
    margin: 0.55rem 0 1rem 0;
    padding: 0.75rem 0;
}
.industry-thesis b { color: #EC7000; }
.industry-note {
    border-left: 3px solid #1a1a1a;
    color: #595959;
    font-size: 0.82rem;
    line-height: 1.45;
    margin: 0.55rem 0 0.8rem 0;
    padding: 0.2rem 0 0.2rem 0.7rem;
}
.industry-note.warning { border-left-color: #b5463c; color: #6e302b; }
.industry-conclusions {
    display: grid;
    gap: 0 1.4rem;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin: 0.35rem 0 1.1rem 0;
}
.industry-conclusion {
    border-top: 1px solid #d7dadd;
    padding: 0.72rem 0 0.8rem 0;
}
.industry-conclusion h3 {
    color: #ec7000;
    font-size: 0.84rem;
    font-weight: 700;
    letter-spacing: 0.01em;
    line-height: 1.3;
    margin: 0 0 0.35rem 0;
}
.industry-conclusion p,
.industry-conclusion ul {
    color: #30353a;
    font-size: 0.86rem;
    line-height: 1.45;
    margin: 0;
}
.industry-conclusion ul { padding-left: 1.05rem; }
.industry-conclusion li { margin: 0 0 0.22rem 0; }
.industry-summary {
    border-bottom: 1px solid #d7dadd;
    margin: 0.35rem 0 0.7rem 0;
}
.industry-summary-row {
    border-top: 1px solid #d7dadd;
    display: grid;
    gap: 1.1rem;
    grid-template-columns: minmax(7rem, 0.65fr) minmax(0, 3fr);
    padding: 0.8rem 0;
}
.industry-summary-value {
    color: #151515;
    font-size: 1.65rem;
    font-weight: 750;
    letter-spacing: -0.02em;
    line-height: 1.05;
}
.industry-summary-row:first-child .industry-summary-value { color: #ec7000; }
.industry-summary-copy h3 {
    color: #30353a;
    font-size: 0.92rem;
    line-height: 1.3;
    margin: 0 0 0.25rem 0;
}
.industry-summary-copy p {
    color: #73787d;
    font-size: 0.82rem;
    line-height: 1.4;
    margin: 0;
}
@media (max-width: 700px) {
    .industry-status-band { grid-template-columns: 1fr; }
    .industry-conclusions { grid-template-columns: 1fr; }
    .industry-summary-row { grid-template-columns: 1fr; gap: 0.35rem; }
}
</style>
"""


def _intelligence_frame(name: str) -> pd.DataFrame:
    frame = _load_csv(name, _industry_files_signature((name,)))
    return frame if frame is not None else pd.DataFrame()


def _industry_intelligence_manifest() -> dict:
    path = _DATA_DIR / "industry_intelligence_manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _competence_label(value: object, *, lower: bool = False) -> str:
    month_names = (
        "Janeiro",
        "Fevereiro",
        "Março",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro",
    )
    try:
        period = pd.Period(str(value), freq="M")
    except (TypeError, ValueError):
        return str(value)
    label = f"{month_names[period.month - 1]}/{str(period.year)[-2:]}"
    return label.lower() if lower else label


def _date_label(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return str(value) if pd.isna(parsed) else parsed.strftime("%d/%m/%Y")


def _short_competence_label(value: object) -> str:
    try:
        period = pd.Period(str(value), freq="M")
    except (TypeError, ValueError):
        return str(value)
    months = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")
    return f"{months[period.month - 1]}/{str(period.year)[-2:]}"


def _industry_files_signature(
    names: tuple[str, ...],
    *,
    data_dir: Path = _DATA_DIR,
) -> str:
    """Return a cheap, deterministic cache token for every declared input file."""

    digest = hashlib.sha256()
    for name in dict.fromkeys(names):
        path = data_dir / name
        if path.exists():
            stat = path.stat()
            state = f"{name}:{stat.st_size}:{stat.st_mtime_ns}"
        else:
            state = f"{name}:missing"
        digest.update(state.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _industry_executive_pack_signature() -> str:
    return _industry_files_signature(_INDUSTRY_EXECUTIVE_PACK_INPUTS)


def _industry_revision_signature() -> str:
    return _industry_files_signature(
        (
            "generated_revision/artifact_payload.json",
            "generated_revision/revision_manifest.json",
            "generated_revision/industry_export_bundle.json",
        )
    )


_REVISION_PAYLOAD_SCHEMA_PATTERN = re.compile(
    r"^fidc_revision_artifact_payload_v(?P<version>[1-9]\d*)$"
)


def _revision_payload_schema_version(schema: str) -> int | None:
    """Return the numeric payload version for a well-formed revision schema."""

    match = _REVISION_PAYLOAD_SCHEMA_PATTERN.fullmatch(str(schema or ""))
    return int(match.group("version")) if match else None


def _industry_tab4_conflict_notice(executive_pack: IndustryExecutivePack | None) -> str:
    """Summarize audited Classe/Fundo conflicts without exposing noisy row detail."""

    if executive_pack is None or executive_pack.source_conflicts.empty:
        return ""
    conflicts = executive_pack.source_conflicts.copy()
    if "tab4_type_conflict" in conflicts:
        conflicts = conflicts[_truthy(conflicts["tab4_type_conflict"])]
    if conflicts.empty:
        return ""
    identifiers = [column for column in ("competencia", "cnpj_fundo") if column in conflicts]
    conflict_count = len(conflicts.drop_duplicates(identifiers)) if identifiers else len(conflicts)
    competences = sorted(
        {
            str(value)
            for value in conflicts.get("competencia", pd.Series(dtype="object")).dropna()
            if str(value).strip()
        }
    )
    competence_label = ", ".join(_competence_label(value) for value in competences) or "competência auditada"
    noun = "CNPJ" if conflict_count == 1 else "CNPJs"
    return (
        f"Integridade CVM: {conflict_count} {noun} com registros Classe/Fundo duplicados em "
        f"{competence_label}. Para evitar dupla contagem, foi aplicada a regra Classe > Fundo."
    )


def _render_industry_tab4_conflict_notice(
    executive_pack: IndustryExecutivePack | None,
) -> None:
    notice = _industry_tab4_conflict_notice(executive_pack)
    if notice:
        st.warning(notice)


@st.cache_data(show_spinner=False)
def _load_industry_executive_pack(signature: str) -> IndustryExecutivePack:
    """Load and build the executive pack; ``signature`` invalidates every source."""

    del signature  # the value participates in Streamlit's cache key

    def read(name: str) -> pd.DataFrame:
        path = _DATA_DIR / name
        return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()

    return build_industry_executive_pack(
        vehicle_monthly=read("vehicle_monthly.csv.gz"),
        competence_status=read("industry_competence_status.csv"),
        industry_monthly=read("industry_monthly.csv"),
        anbima_classification=read("industry_anbima_classification.csv.gz"),
        published_classifications=read("industry_large_fund_classification.csv"),
        holder_min_pl_brl=0.0,
    )


@st.cache_data(show_spinner=False)
def _load_industry_revision_payload(signature: str) -> dict[str, object]:
    """Load the editorial payload shared by the UI and the reviewed exports."""

    del signature
    path = _DATA_DIR / "generated_revision" / "artifact_payload.json"
    if not path.exists():
        raise FileNotFoundError(f"payload revisado ausente: {path}")
    payload_raw = path.read_bytes()
    payload = json.loads(payload_raw)
    schema = str(payload.get("schema_version") or "")
    schema_version = _revision_payload_schema_version(schema)
    if schema_version is None or schema_version < 2:
        label = schema or "ausente"
        raise ValueError(f"schema do payload revisado incompatível: {label}")
    # The page renders the fields it knows and validates the latest known
    # contract below. Office downloads remain strict in industry_revision_export.

    manifest_path = _DATA_DIR / "generated_revision" / "industry_export_bundle.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_schema = str(manifest.get("payload_schema") or "")
        if manifest_schema == schema:
            expected_hash = str(manifest.get("payload_sha256") or "")
            if expected_hash and expected_hash != hashlib.sha256(payload_raw).hexdigest():
                raise ValueError("payload revisado diverge do hash do bundle publicado")
        elif manifest_schema:
            manifest_version = _revision_payload_schema_version(manifest_schema)
            if manifest_version is None or manifest_version >= schema_version:
                raise ValueError("schema do payload diverge do bundle publicado")
            # During an atomic release, the analytical payload can arrive before
            # the heavier Office bundle.  The page uses the newer validated
            # payload while the export status keeps the stale bundle blocked.

    # Deploys can briefly expose the previous, internally consistent bundle
    # while code and large analytical artifacts are synchronized.  Keep v2
    # readable during that window and validate each generation only against
    # the blocks it actually introduced.  v1 is not accepted because it lacks
    # the historical comparisons required by the current page narrative.
    required = {
        "classification_coverage",
        "holder_distribution_meta",
        "investor_composition",
        "pl_history",
        "investor_base_history",
        "holder_distribution",
        "material_focus_top6",
        "market_share_top10_fixed",
        "monostructure_concentration",
        "offers_ytd",
        "originators_2026",
        "provider_concentration",
        "qa_latest",
        "qa_series",
        "receivables",
        "service_model",
        "type_mix",
        "market_share",
        "top20_fidcs",
        "top20_outros",
        "profiles",
    }
    if schema_version >= 2:
        required.update(
            {
                "holder_distribution_meta_history",
                "holder_distribution_history",
                "provider_concentration_history",
                "receivables_history",
                "receivables_meta_history",
                "type_mix_history",
            }
        )
    if schema_version >= 3:
        required.update(
            {
                "provider_historical_ranking",
                "market_share_scope_summary",
                "market_share_exclusions",
                "acquiring_taxonomy",
            }
        )
    if schema_version >= 4:
        required.update(
            {
                "delinquency_single_receivable",
                "delinquency_single_receivable_summary",
                "provider_independent_ranking",
                "bank_fidc_evolution",
                "acquiring_reclassified_mix",
                "closed_offers_annual",
                "closed_offers_monthly",
                "closed_offer_originators_2026",
            }
        )
    if schema_version >= 5:
        required.update(
            {
                "delinquency_frozen_cohort_history",
                "delinquency_frozen_cohort_summary",
                "bank_fidc_detail",
                "btg_provider_ex_controlled_scenario",
                "closed_offer_ticket_distribution",
                "provider_history_cvm_coverage",
                "provider_history_cvm_links",
                "provider_history_cvm_detail",
                "conclusion_metrics",
            }
        )
    if schema_version >= 6:
        required.update(
            {
                "card_taxonomy_audit",
                "card_taxonomy_summary",
                "acquiring_curation_detail",
            }
        )
    missing = sorted(required.difference(payload))
    comparable_offer_key = next(
        (
            key
            for key in ("closed_offers_jan_june", "closed_offers_jan_may")
            if isinstance(payload.get(key), list) and bool(payload.get(key))
        ),
        None,
    )
    if schema_version >= 4 and comparable_offer_key is None:
        missing.append("closed_offers_jan_june")
    if missing:
        raise ValueError(
            "payload revisado incompleto: " + ", ".join(sorted(set(missing)))
        )
    if schema_version >= 3:
        exclusions = payload.get("market_share_exclusions")
        excluded_cnpjs = set()
        if isinstance(exclusions, list):
            excluded_cnpjs = {
                re.sub(r"\D", "", str(row.get("cnpj") or ""))
                for row in exclusions
                if isinstance(row, dict)
            }
        required_exclusions = {"09195235000150", "26287464000114"}
        if not required_exclusions.issubset(excluded_cnpjs):
            raise ValueError(
                "payload v3 sem as exclusões nominais de Sistema Petrobras e TAPSO"
            )
        if not isinstance(payload.get("acquiring_taxonomy"), dict):
            raise ValueError("payload v3 sem curadoria estruturada de adquirência")
    if len(payload["top20_fidcs"]) != 20 or len(payload["top20_outros"]) != 20:
        raise ValueError("rankings revisados devem conter exatamente 20 fundos")
    required_columns = {
        "pl_history": {"competencia", "year", "pl_total", "pl_ex_fic", "pl_fic_componente"},
        "investor_base_history": {"competencia", "year", "cotistas_total", "n_veiculos"},
        "classification_coverage": {"categoria", "pl", "share"},
        "service_model": {"modelo_prestacao", "fundos", "pl", "share_fundos", "share_pl"},
        "market_share": {
            "papel",
            "tipo_anbima",
            "foco_anbima",
            "participante_bucket",
            "share_subtipo",
            "publication_status",
        },
        "top20_fidcs": {"rank", "denominacao", "pl", "market_share_ex_fic"},
        "top20_outros": {"rank_outros", "denominacao", "pl", "market_share_outros"},
        "profiles": {"rank", "cnpj_fundo_formatado", "nome_curto", "pl"},
    }
    if schema_version >= 2:
        required_columns.update(
            {
                "holder_distribution_history": {"competencia", "bucket", "fundos", "pl"},
                "holder_distribution_meta_history": {
                    "competencia",
                    "minimum_pl_brl",
                    "fund_coverage",
                    "pl_coverage",
                },
                "type_mix_history": {"competencia", "anbima_tipo", "pl", "share"},
                "receivables_history": {
                    "competencia",
                    "segmento",
                    "valor",
                    "share_reported",
                },
                "receivables_meta_history": {
                    "competencia",
                    "reported_total",
                    "portfolio_total",
                    "gap",
                    "gap_pct",
                },
                "provider_concentration_history": {
                    "competencia",
                    "papel",
                    "top5_share",
                    "top10_share",
                    "coverage_pl",
                    "missing_share",
                },
            }
        )
    if schema_version >= 3:
        required_columns.update(
            {
                "provider_historical_ranking": {
                    "competencia",
                    "papel",
                    "participante",
                    "rank_periodo",
                    "pl_brl",
                },
                "market_share_scope_summary": {
                    "papel",
                    "pl_total_ex_fic_brl",
                    "cobertura_classificacao_14_focos_pl",
                },
            }
        )
    if schema_version >= 4:
        required_columns.update(
            {
                "delinquency_single_receivable": {
                    "tipo_recebivel_tabela_ii",
                    "fundos_incluidos",
                    "pl_incluido_brl",
                    "inadimplencia_sobre_pl",
                },
                "provider_independent_ranking": {
                    "competencia",
                    "papel",
                    "participante",
                    "rank_independente",
                    "rank_geral",
                    "pl_brl",
                    "selected_latest_top_n",
                },
                "bank_fidc_evolution": {
                    "competencia",
                    "grupo_bancario",
                    "pl_bruto_brl",
                    "is_total_5_banks",
                    "observado",
                },
                "acquiring_reclassified_mix": {
                    "competencia",
                    "categoria_analitica",
                    "pl_brl",
                    "share_pl",
                },
                "closed_offers_annual": {
                    "year",
                    "closed_offers",
                    "registered_volume_brl",
                    "mean_registered_ticket_brl",
                    "median_registered_ticket_brl",
                    "natural_person_placed_volume_share",
                    "placed_quantity_registered_volume_coverage",
                    "professional_target_registered_volume_share",
                },
                "closed_offers_monthly": {
                    "year",
                    "month",
                    "registered_volume_brl",
                },
                "closed_offer_originators_2026": {
                    "rank",
                    "originator_group",
                    "closed_offers",
                    "registered_volume_brl",
                    "mean_registered_ticket_brl",
                    "identified_registered_volume_coverage",
                    "identified_registered_volume_brl",
                    "confidence",
                    "share_of_total_registered_volume",
                },
            }
        )
        required_columns[str(comparable_offer_key)] = {
            "year",
            "closed_offers",
            "registered_volume_brl",
            "mean_registered_ticket_brl",
        }
    if schema_version >= 5:
        required_columns.update(
            {
                "delinquency_frozen_cohort_history": {
                    "competencia",
                    "tipo_recebivel_tabela_ii",
                    "fundos_incluidos",
                    "pl_incluido_brl",
                    "inadimplencia_sobre_carteira",
                    "fundos_coorte",
                    "pl_coorte_referencia_brl",
                },
                "delinquency_frozen_cohort_summary": {
                    "competencia",
                    "fundos_incluidos",
                    "pl_incluido_brl",
                    "inadimplencia_sobre_carteira",
                    "fundos_coorte",
                    "pl_coorte_referencia_brl",
                },
                "bank_fidc_detail": {
                    "competencia",
                    "grupo_bancario",
                    "cnpj_fundo",
                    "denominacao",
                    "pl_brl",
                    "observado",
                },
                "btg_provider_ex_controlled_scenario": {
                    "competencia",
                    "papel",
                    "btg_pl_brl",
                    "btg_rank",
                    "fidcs_controlados_excluidos",
                    "pl_controlado_excluido_brl",
                    "btg_pl_ex_controlados_brl",
                    "btg_rank_ex_controlados",
                },
                "closed_offer_ticket_distribution": {
                    "period_label",
                    "ticket_bucket",
                    "closed_offers",
                    "offer_share",
                    "registered_volume_brl",
                    "registered_volume_share",
                    "period_mean_ticket_brl",
                    "period_median_ticket_brl",
                },
                "provider_history_cvm_coverage": {
                    "papel",
                    "data_referencia",
                    "fundos_coorte",
                    "pl_coorte_mai26_brl",
                    "fundos_resolvidos_unicos",
                    "cobertura_pl_resolvida",
                },
                "provider_history_cvm_links": {
                    "papel",
                    "origem_prestador_grupo",
                    "destino_prestador_grupo",
                    "fundos",
                    "pl_mai26_brl",
                },
                "provider_history_cvm_detail": {
                    "papel",
                    "cnpj_fundo",
                    "denominacao",
                    "pl_mai26_brl",
                    "origem_prestador_grupo",
                    "destino_prestador_grupo",
                },
            }
        )
    for key, columns in required_columns.items():
        rows = payload.get(key)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"bloco revisado vazio ou inválido: {key}")
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise ValueError(f"{key} contém linha {index} inválida")
            missing_columns = sorted(columns.difference(row))
            if missing_columns:
                raise ValueError(
                    f"{key} linha {index} sem colunas obrigatórias: "
                    + ", ".join(missing_columns)
                )
    if schema_version >= 4:
        summary = payload.get("delinquency_single_receivable_summary")
        required_summary = {
            "fundos_universo_ex_fic_pl_positivo",
            "pl_universo_ex_fic_positivo_brl",
            "fundos_incluidos",
            "pl_incluido_brl",
            "cobertura_pl",
            "fundos_multitipo_excluidos",
            "pl_multitipo_excluido_brl",
            "fundos_sem_tipo_excluidos",
            "pl_sem_tipo_excluido_brl",
            "fundos_inad_supera_carteira_excluidos",
            "pl_inad_supera_carteira_excluido_brl",
            "fundos_fic_excluidos",
            "pl_fic_excluido_brl",
        }
        if not isinstance(summary, dict):
            raise ValueError("delinquency_single_receivable_summary inválido")
        missing_summary = sorted(required_summary.difference(summary))
        if missing_summary:
            raise ValueError(
                "delinquency_single_receivable_summary sem campos obrigatórios: "
                + ", ".join(missing_summary)
            )
    if schema_version >= 5 and not isinstance(
        payload.get("conclusion_metrics"), dict
    ):
        raise ValueError("conclusion_metrics inválido")
    return payload


def _industry_export_signature() -> str:
    from services.industry_revision_export import revision_export_signature

    return revision_export_signature(_DATA_DIR)


@st.cache_data(show_spinner=False)
def _industry_export_payloads(signature: str) -> tuple[bytes, bytes, bytes]:
    from services.industry_ppt_export import build_industry_pptx_bytes, build_industry_xlsx_bytes
    from services.industry_revision_export import build_revision_html_bytes

    del signature  # the value participates in Streamlit's cache key
    return (
        build_industry_pptx_bytes(_DATA_DIR),
        build_industry_xlsx_bytes(_DATA_DIR),
        build_revision_html_bytes(_DATA_DIR),
    )


@st.cache_data(show_spinner=False)
def _industry_provider_flow_html(signature: str) -> str:
    from services.industry_revision_export import build_revision_html_bytes

    del signature  # the value participates in Streamlit's cache key
    return build_revision_html_bytes(_DATA_DIR).decode("utf-8")


def _industry_kpi(label: str, value: str, note: str = "") -> str:
    note_html = f'<div class="industry-kpi-note">{note}</div>' if note else ""
    return (
        f'<div class="industry-kpi"><div class="industry-kpi-label">{label}</div>'
        f'<div class="industry-kpi-value">{value}</div>{note_html}</div>'
    )


def _industry_headline(text: str) -> None:
    st.markdown(
        f'<div class="industry-thesis">{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def _truthy(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(str).str.strip().str.lower().isin({"true", "1", "sim", "s"})


def _industry_monostructure_frames(
    pack: IndustryExecutivePack,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return chart-ready history and the current six-model decomposition."""

    base = pack.monostructure_history.copy()
    if base.empty:
        return pd.DataFrame(), pd.DataFrame()
    competence_order = list(pack.competences.ordered)
    base["period_label"] = base["competencia"].map(
        lambda value: _competence_label(value).replace("embro", "")
    )
    base.loc[
        base["competencia"].ne(pack.competences.latest_complete), "period_label"
    ] = (
        base.loc[
            base["competencia"].ne(pack.competences.latest_complete), "period_label"
        ].astype(str)
        + "*"
    )
    base["_period_order"] = base["competencia"].map(
        {competence: order for order, competence in enumerate(competence_order)}
    )
    history = base[base["structure_model"].eq("Monoestrutura")].melt(
        id_vars=["competencia", "period_label", "_period_order"],
        value_vars=["fund_share_total", "pl_share_total"],
        var_name="metric",
        value_name="share",
    )
    history["metric"] = history["metric"].map(
        {"fund_share_total": "% dos fundos", "pl_share_total": "% do PL"}
    )
    history = history.sort_values(["_period_order", "metric"]).reset_index(drop=True)

    current = base[base["competencia"].eq(pack.competences.latest_complete)].copy()
    current["structure_model"] = pd.Categorical(
        current["structure_model"], categories=list(STRUCTURE_MODELS), ordered=True
    )
    current = current.sort_values("structure_model").reset_index(drop=True)
    return history, current


def _industry_holder_focus_options(
    pack: IndustryExecutivePack,
    anbima_type: str,
) -> list[str]:
    latest = pack.latest_funds
    latest = latest[latest["anbima_tipo"].ne(ANBIMA_FIC)]
    if anbima_type != "Todos":
        latest = latest[latest["anbima_tipo"].eq(anbima_type)]
    available = {
        str(value)
        for value in latest.get("anbima_foco", pd.Series(dtype=str)).dropna()
        if str(value).strip() and str(value) != ANBIMA_FIC
    }
    preferred: list[str] = []
    types = ANBIMA_TYPES if anbima_type == "Todos" else (anbima_type,)
    for category in types:
        preferred.extend(ANBIMA_FOCUS_BY_TYPE.get(category, ()))
    if ANBIMA_ND in available:
        preferred.append(ANBIMA_ND)
    ordered = list(dict.fromkeys(value for value in preferred if value in available))
    ordered.extend(sorted(available.difference(ordered)))
    return ["Todos", *ordered]


def _industry_anbima_coverage_note(pack: IndustryExecutivePack) -> str:
    latest = pack.coverage[
        pack.coverage["competencia"].eq(pack.competences.latest_complete)
    ]
    if latest.empty:
        return (
            "* Tipo e foco usam a fotografia cadastral pública ANBIMA de dez/25; "
            "proxy CVM e N/D permanecem sinalizados."
        )
    official_coverage = pd.to_numeric(
        latest.iloc[0].get("official_anbima_ex_fic_pl_coverage"), errors="coerce"
    )
    coverage_text = "n/d" if pd.isna(official_coverage) else _fmt_pct(float(official_coverage))
    return (
        "* Tipo e foco usam a fotografia cadastral pública ANBIMA de dez/25. Em "
        f"{_competence_label(pack.competences.latest_complete)}, a classificação oficial cobre "
        f"{coverage_text} do PL ex-FIC; o complemento permanece em evidência publicada, proxy "
        "CVM ou N/D, sempre sinalizado."
    )


def _industry_holder_histogram_frames(
    pack: IndustryExecutivePack,
    *,
    min_pl_brl: float,
    anbima_type: str = "Todos",
    anbima_focus: str = "Todos",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply UI filters before delegating the bucket calculation to the service."""

    funds = pack.fund_monthly.copy()
    if anbima_type != "Todos":
        funds = funds[funds["anbima_tipo"].eq(anbima_type)]
    if anbima_focus != "Todos":
        funds = funds[funds["anbima_foco"].eq(anbima_focus)]
    histogram, coverage = build_holder_histograms(
        funds,
        pack.competences.latest_complete,
        min_pl_brl=float(min_pl_brl),
    )
    if anbima_type != "Todos":
        histogram = histogram[histogram["anbima_tipo"].eq(anbima_type)].copy()
    if not histogram.empty:
        active = (
            histogram.groupby("anbima_tipo", dropna=False)[["fund_count", "pl_brl"]]
            .sum()
            .sum(axis=1)
        )
        histogram = histogram[
            histogram["anbima_tipo"].isin(active[active.gt(0)].index)
        ].copy()
        histogram["pl_bi"] = pd.to_numeric(histogram["pl_brl"], errors="coerce") / 1e9
    return histogram.reset_index(drop=True), coverage.reset_index(drop=True)


def _render_industry_exports(*, suffix: str, as_of_date: str) -> None:
    try:
        pptx_bytes, xlsx_bytes, html_bytes = _industry_export_payloads(
            _industry_export_signature()
        )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Exportação executiva indisponível: {exc}")
        return
    file_period = str(as_of_date).replace("-", "")[:6] or "atual"
    left, middle, right, _spacer = st.columns([1, 1, 1, 2])
    with left:
        st.download_button(
            "PPTX",
            data=pptx_bytes,
            file_name=f"Industria_FIDC_Executivo_{file_period}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            icon=":material/slideshow:",
            help="Baixar apresentação executiva",
            width="stretch",
            key=f"industry-pptx-{suffix}",
        )
    with middle:
        st.download_button(
            "XLSX",
            data=xlsx_bytes,
            file_name=f"Industria_FIDC_Dados_{file_period}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/table_view:",
            help="Baixar bases e tabelas da apresentação",
            width="stretch",
            key=f"industry-xlsx-{suffix}",
        )
    with right:
        st.download_button(
            "HTML interativo",
            data=html_bytes,
            file_name=f"Industria_FIDC_Fluxos_Prestadores_{file_period}.html",
            mime="text/html",
            icon=":material/hub:",
            help="Baixar o explorador interativo dos fluxos de prestadores",
            width="stretch",
            key=f"industry-html-{suffix}",
        )


def _stock_delta_display(stock: pd.DataFrame, role: str, segment: str, metric: str, top_n: int) -> pd.DataFrame:
    frame = stock[
        stock["role"].eq(role)
        & stock["segment"].eq(segment)
        & stock["metric"].eq(metric)
    ].copy()
    current = frame[frame["period"].eq("2026YTD")].sort_values("rank").head(top_n)
    rows: list[dict[str, object]] = []
    for participant in current["participant"]:
        item: dict[str, object] = {"Participante": participant}
        for period in ("2024", "2025", "2026YTD"):
            match = frame[frame["participant"].eq(participant) & frame["period"].eq(period)]
            item[f"Pos. {period}"] = int(match.iloc[0]["rank"]) if not match.empty else None
            item[f"Share {period}"] = float(match.iloc[0]["share"]) if not match.empty else None
        start = frame[frame["participant"].eq(participant) & frame["period"].eq("2024")]
        end = frame[frame["participant"].eq(participant) & frame["period"].eq("2026YTD")]
        item["Delta share (p.p.)"] = (
            (float(end.iloc[0]["share"]) - float(start.iloc[0]["share"])) * 100
            if not start.empty and not end.empty
            else None
        )
        item["Valor 2026"] = float(end.iloc[0]["value"]) if not end.empty else 0.0
        rows.append(item)
    return pd.DataFrame(rows)


def _industry_executive_trend_frames(industry: pd.DataFrame) -> dict[str, pd.DataFrame]:
    empty = {
        "pl": pd.DataFrame(),
        "flow": pd.DataFrame(),
        "holders": pd.DataFrame(),
        "delinquency": pd.DataFrame(),
    }
    if industry.empty or "competencia" not in industry.columns:
        return empty

    base = _month_axis(industry.sort_values("competencia").copy())
    if "pl_total" in base.columns:
        pl = base.tail(72).copy()
        pl_total = pd.to_numeric(pl["pl_total"], errors="coerce")
        pl_fic = (
            pd.to_numeric(pl["pl_fic_fidc"], errors="coerce").fillna(0.0)
            if "pl_fic_fidc" in pl.columns
            else pd.Series(0.0, index=pl.index)
        )
        total = pl.assign(Série="FIDCs + FIC-FIDCs", valor_bi=pl_total / 1e9)
        ex_fic = pl.assign(Série="Somente FIDCs (ex-FIC-FIDCs)", valor_bi=(pl_total - pl_fic) / 1e9)
        empty["pl"] = pd.concat([total, ex_fic], ignore_index=True).dropna(subset=["valor_bi"])

    if "captacao_liquida" in base.columns:
        flow = base.tail(48).copy()
        flow["valor_bi"] = pd.to_numeric(flow["captacao_liquida"], errors="coerce") / 1e9
        flow["Sinal"] = flow["valor_bi"].map(
            lambda value: _LABELS["entrada"] if pd.notna(value) and value >= 0 else _LABELS["saida"]
        )
        empty["flow"] = flow.dropna(subset=["valor_bi"])

    if "cotistas_total" in base.columns:
        holders = base.tail(72).copy()
        holders["contas_mil"] = pd.to_numeric(holders["cotistas_total"], errors="coerce") / 1000
        empty["holders"] = holders.dropna(subset=["contas_mil"])

    if {"inad_pct_ajustada", "inad_pct"}.issubset(base.columns):
        delinquency = base.tail(72).copy()
        adjusted = delinquency.assign(
            Série="Ajustada",
            percentual=pd.to_numeric(delinquency["inad_pct_ajustada"], errors="coerce") * 100,
        )
        gross = delinquency.assign(
            Série="Bruta",
            percentual=pd.to_numeric(delinquency["inad_pct"], errors="coerce") * 100,
        )
        empty["delinquency"] = pd.concat([adjusted, gross], ignore_index=True).dropna(subset=["percentual"])
    return empty


def _render_industry_executive(
    industry: pd.DataFrame,
    status: pd.DataFrame,
    competitive: pd.DataFrame,
    latest_complete: str,
) -> None:
    complete_industry = industry[industry["competencia"].astype(str).le(latest_complete)].sort_values("competencia")
    last = complete_industry.iloc[-1]
    ref = complete_industry[complete_industry["competencia"].astype(str).eq(f"{int(latest_complete[:4]) - 1}-{latest_complete[5:]}")]
    ref = ref.iloc[0] if not ref.empty else None
    cap_12m = float(complete_industry.tail(12)["captacao_liquida"].sum())
    latest_position = competitive.sort_values("year").iloc[-1] if not competitive.empty else pd.Series(dtype=object)
    pl_ex_fic = float(last["pl_total"] - last.get("pl_fic_fidc", 0))
    pl_growth = float(pl_ex_fic / (ref["pl_total"] - ref.get("pl_fic_fidc", 0)) - 1) if ref is not None else 0.0

    kpis = [
        _industry_kpi("PL ex-FIC", _fmt_bi(pl_ex_fic, 0), f"{_fmt_pct(pl_growth)} em 12m"),
        _industry_kpi("Captação líquida 12m", _fmt_bi(cap_12m, 0), "captações − resgates − amortizações"),
        _industry_kpi("Contas de cotistas", f"{_fmt_int(last['cotistas_total'] / 1000)} mil", "contas por classe, não CPFs únicos"),
        _industry_kpi("Inad. ajustada", _fmt_pct(last["inad_pct_ajustada"]), f"bruta {_fmt_pct(last['inad_pct'])}"),
        _industry_kpi(
            "Itaú em tickets >R$300 mi",
            f"#{int(latest_position.get('itau_coordinator_rank', 0) or 0)}",
            f"{_fmt_pct(float(latest_position.get('itau_coordinator_share', 0)))} do volume 2026YTD",
        ),
        _industry_kpi(
            "Admin./custódia Itaú",
            _fmt_pct(float(latest_position.get("itau_administrator_share", 0))),
            "share nas ofertas >R$300 mi em 2026YTD",
        ),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(kpis)}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-thesis"><b>Tese:</b> o Itaú já é competitivo na originação de tickets relevantes; '
        "o espaço econômico está na conversão desses mandatos em administração, custódia e distribuição institucional.</div>",
        unsafe_allow_html=True,
    )

    trend_frames = _industry_executive_trend_frames(complete_industry)

    left, right = st.columns([1.15, 0.85])
    with left:
        pl_frame = trend_frames["pl"]
        total_pl = pl_frame[pl_frame["Série"].eq("FIDCs + FIC-FIDCs")]
        area = (
            alt.Chart(total_pl)
            .mark_area(color=_ORANGE_SOFT)
            .encode(
                x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False)),
                y=alt.Y("valor_bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
            )
        )
        lines = (
            alt.Chart(pl_frame)
            .mark_line(strokeWidth=2.3)
            .encode(
                x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False)),
                y=alt.Y("valor_bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                color=alt.Color(
                    "Série:N",
                    scale=alt.Scale(
                        domain=["FIDCs + FIC-FIDCs", "Somente FIDCs (ex-FIC-FIDCs)"],
                        range=[_ORANGE, _BLACK],
                    ),
                    legend=alt.Legend(title=None, orient="bottom"),
                ),
                strokeDash=alt.StrokeDash(
                    "Série:N",
                    scale=alt.Scale(
                        domain=["FIDCs + FIC-FIDCs", "Somente FIDCs (ex-FIC-FIDCs)"],
                        range=[[1, 0], [5, 3]],
                    ),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("competencia:N", title="Competência"),
                    alt.Tooltip("Série:N"),
                    alt.Tooltip("valor_bi:Q", title="PL (R$ bi)", format=",.1f"),
                ],
            )
        )
        st.altair_chart(
            (area + lines).properties(height=310, title="PL total e ex-FIC-FIDC"),
            width="stretch",
            key=INDUSTRY_EXECUTIVE_CHARTS[0],
        )
    with right:
        if not competitive.empty:
            plot = competitive.copy()
            plot["Mercado"] = plot["market_relevant_volume_brl"] / 1e9
            plot["Itaú coordenador"] = plot["itau_coordinator_volume_brl"] / 1e9
            long = plot.melt(
                id_vars=["period"],
                value_vars=["Mercado", "Itaú coordenador"],
                var_name="Série",
                value_name="R$ bi",
            )
            chart = (
                alt.Chart(long)
                .mark_bar()
                .encode(
                    x=alt.X("period:N", title=None),
                    y=alt.Y("R$ bi:Q", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    xOffset="Série:N",
                    color=alt.Color(
                        "Série:N",
                        scale=alt.Scale(domain=["Mercado", "Itaú coordenador"], range=[_BLACK, _ORANGE]),
                        legend=alt.Legend(title=None, orient="top"),
                    ),
                    tooltip=["period:N", "Série:N", alt.Tooltip("R$ bi:Q", format=",.1f")],
                )
                .properties(height=310, title="Ofertas acima de R$ 300 mi")
            )
            st.altair_chart(chart, width="stretch", key=INDUSTRY_EXECUTIVE_CHARTS[1])

    st.markdown("<h2>Tendências estruturais</h2>", unsafe_allow_html=True)
    flow_col, holders_col, delinquency_col = st.columns(3)
    with flow_col:
        st.markdown("**Captação líquida mensal**")
        flow = trend_frames["flow"]
        if flow.empty:
            st.caption("Série indisponível.")
        else:
            flow_chart = (
                alt.Chart(flow)
                .mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
                .encode(
                    x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False, tickCount=5)),
                    y=alt.Y("valor_bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    color=alt.Color(
                        "Sinal:N",
                        scale=alt.Scale(
                            domain=[_LABELS["entrada"], _LABELS["saida"]],
                            range=[_ORANGE, _BLACK],
                        ),
                        legend=alt.Legend(title=None, orient="bottom"),
                    ),
                    tooltip=[
                        alt.Tooltip("competencia:N", title="Competência"),
                        alt.Tooltip("valor_bi:Q", title="Captação líquida (R$ bi)", format=",.2f"),
                    ],
                )
                .properties(height=245)
            )
            st.altair_chart(flow_chart, width="stretch", key=INDUSTRY_EXECUTIVE_CHARTS[2])
    with holders_col:
        st.markdown("**Contas de cotistas**")
        holders = trend_frames["holders"]
        if holders.empty:
            st.caption("Série indisponível.")
        else:
            holders_base = (
                alt.Chart(holders)
                .encode(
                    x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False, tickCount=5)),
                    y=alt.Y("contas_mil:Q", title="mil contas", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    tooltip=[
                        alt.Tooltip("competencia:N", title="Competência"),
                        alt.Tooltip("contas_mil:Q", title="Mil contas", format=",.0f"),
                    ],
                )
            )
            holders_chart = (
                holders_base.mark_line(color=_ORANGE, strokeWidth=2.3)
                + holders_base.mark_point(color=_ORANGE, filled=True, size=22)
            ).properties(height=245)
            st.altair_chart(holders_chart, width="stretch", key=INDUSTRY_EXECUTIVE_CHARTS[3])
    with delinquency_col:
        st.markdown("**Inadimplência da carteira**")
        delinquency = trend_frames["delinquency"]
        if delinquency.empty:
            st.caption("Série indisponível.")
        else:
            delinquency_chart = (
                alt.Chart(delinquency)
                .mark_line(strokeWidth=2.2)
                .encode(
                    x=alt.X("mes:T", title=None, axis=alt.Axis(format="%b/%y", grid=False, tickCount=5)),
                    y=alt.Y("percentual:Q", title="% da carteira", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    color=alt.Color(
                        "Série:N",
                        scale=alt.Scale(domain=["Ajustada", "Bruta"], range=[_ORANGE, _BLACK]),
                        legend=alt.Legend(title=None, orient="bottom"),
                    ),
                    tooltip=[
                        alt.Tooltip("competencia:N", title="Competência"),
                        alt.Tooltip("Série:N"),
                        alt.Tooltip("percentual:Q", title="%", format=",.1f"),
                    ],
                )
                .properties(height=245)
            )
            st.altair_chart(delinquency_chart, width="stretch", key=INDUSTRY_EXECUTIVE_CHARTS[4])

    preliminary = status[status["publication_status"].ne("completa")].sort_values("competencia").tail(1)
    if not preliminary.empty:
        row = preliminary.iloc[0]
        preliminary_label = _competence_label(row["competencia"])
        consolidated_label = _competence_label(latest_complete, lower=True)
        st.markdown(
            f'<div class="industry-status-band"><strong>{preliminary_label} é prévia</strong>'
            f'<span>{_fmt_int(row["n_veiculos"])} veículos · {_fmt_bi(row["pl_total"], 1)} de PL · '
            f'{_fmt_pct(row["vehicle_ratio_vs_previous"])} dos veículos e {_fmt_pct(row["pl_ratio_vs_previous"])} do PL da competência anterior. '
            f"Rankings e KPIs consolidados permanecem em {consolidated_label}.</span></div>",
            unsafe_allow_html=True,
        )


def _render_industry_offers(annual: pd.DataFrame, rankings: pd.DataFrame, competitive: pd.DataFrame) -> None:
    st.markdown("<h2>Atividade primária e tickets relevantes</h2>", unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Oferta válida = registro não revogado, suspenso ou caducado. '
        "Oferta inicial é o campo oficial da CVM; ofertas subsequentes permanecem na atividade total de DCM.</div>",
        unsafe_allow_html=True,
    )
    if not annual.empty:
        display = pd.DataFrame(
            {
                "Período": annual["period"],
                "Ofertas válidas": annual["valid_offers"].astype(int),
                "Volume válido": annual["valid_registered_volume_brl"].map(lambda value: _fmt_bi(value, 1)),
                "Ofertas iniciais": annual["initial_offers"].astype(int),
                "Volume inicial": annual["initial_registered_volume_brl"].map(lambda value: _fmt_bi(value, 1)),
                "> R$300 mi": annual["relevant_ticket_offers"].astype(int),
                "Volume >R$300 mi": annual["relevant_ticket_volume_brl"].map(lambda value: _fmt_bi(value, 1)),
            }
        )
        st.dataframe(display, hide_index=True, width="stretch")

    if not competitive.empty:
        latest = competitive.sort_values("year").iloc[-1]
        cards = [
            _industry_kpi("Itaú coordenação", f"#{int(latest['itau_coordinator_rank'])}", _fmt_pct(latest["itau_coordinator_share"])),
            _industry_kpi("Volume Itaú", _fmt_bi(latest["itau_coordinator_volume_brl"], 1), "2026YTD > R$300 mi"),
            _industry_kpi("Administração Itaú", _fmt_pct(latest["itau_administrator_share"]), "nas ofertas relevantes"),
            _industry_kpi("Custódia Itaú", _fmt_pct(latest["itau_custodian_share"]), "nas ofertas relevantes"),
            _industry_kpi("Monoestrutura", _fmt_pct(latest["market_monostructure_volume_share"]), "mesmo grupo em adm./gestão/custódia"),
            _industry_kpi("Mediana cotistas Itaú", _fmt_int(latest["itau_median_investors"]), "ofertas encerradas com composição"),
        ]
        st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
    if rankings.empty:
        return
    controls = st.columns([1, 1, 1.35, 1.35])
    with controls[0]:
        period = st.selectbox("Período", list(dict.fromkeys(rankings.sort_values("year")["period"])), index=2, key="industry-offer-period")
    with controls[1]:
        ticket = st.selectbox("Ticket", [">= R$ 300 mi", "todas"], key="industry-offer-ticket")
    with controls[2]:
        role = st.selectbox("Papel", ["coordenador", "administrador", "gestor", "custodiante"], key="industry-offer-role")
    segment_options = ["Todos"] + sorted(value for value in rankings["segment"].dropna().unique() if value != "Todos")
    with controls[3]:
        segment = st.selectbox("Segmento", segment_options, key="industry-offer-segment")
    selected = rankings[
        rankings["period"].astype(str).eq(str(period))
        & rankings["ticket_scope"].eq(ticket)
        & rankings["role"].eq(role)
        & rankings["segment"].eq(segment)
    ].sort_values("rank").head(15)
    if selected.empty:
        st.info("Sem observações para o recorte selecionado.")
        return
    selected = selected.assign(volume_bi=selected["volume_brl"] / 1e9)
    chart = (
        alt.Chart(selected)
        .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
        .encode(
            x=alt.X("volume_bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
            y=alt.Y("participant:N", title=None, sort=alt.SortField("rank", order="ascending"), axis=alt.Axis(labelLimit=280)),
            tooltip=["participant:N", alt.Tooltip("volume_bi:Q", format=",.2f"), alt.Tooltip("share:Q", format=".1%"), "offers:Q"],
        )
        .properties(height=max(300, len(selected) * 26), title=f"Ranking de {role} · {period}")
    )
    st.altair_chart(chart, width="stretch")
    table = selected[["rank", "participant", "offers", "volume_brl", "share"]].copy()
    table.columns = ["Posição", "Participante", "Ofertas", "Volume", "Share"]
    table["Volume"] = table["Volume"].map(lambda value: _fmt_bi(value, 2))
    table["Share"] = table["Share"].map(_fmt_pct)
    st.dataframe(table, hide_index=True, width="stretch")


def _render_industry_providers(
    stock: pd.DataFrame,
    pack: IndustryExecutivePack | None,
) -> None:
    st.markdown("<h2>Integração dos prestadores no estoque</h2>", unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Cada fundo é classificado pela combinação observada entre '
        "administrador, gestor e custodiante. Monoestrutura significa que o mesmo grupo canônico "
        "ocupa as três funções; dados ausentes permanecem separados e não geram inferência.</div>",
        unsafe_allow_html=True,
    )
    if pack is None:
        st.info("Análise estrutural indisponível; o ranking histórico permanece abaixo.")
    else:
        history, current = _industry_monostructure_frames(pack)
        if history.empty or current.empty:
            st.info("Série de estrutura dos prestadores indisponível.")
        else:
            current_label = _short_competence_label(pack.competences.latest_complete)
            st.markdown(
                '<div class="industry-note warning">* Dez/24 e dez/25 são reconstruções '
                "indicativas: o administrador vem do informe mensal de cada período, mas gestor "
                f"e custodiante vêm do cadastro CVM vigente. {current_label} é a fotografia atual.</div>",
                unsafe_allow_html=True,
            )
            period_sort = list(
                dict.fromkeys(history.sort_values("_period_order")["period_label"].astype(str))
            )
            history_chart = (
                alt.Chart(history)
                .mark_line(point=alt.OverlayMarkDef(size=55), strokeWidth=2.5)
                .encode(
                    x=alt.X("period_label:N", title=None, sort=period_sort),
                    y=alt.Y(
                        "share:Q",
                        title="Participação no estoque",
                        axis=alt.Axis(format=".0%", gridColor=_GRAY_LIGHT),
                        scale=alt.Scale(zero=True),
                    ),
                    color=alt.Color(
                        "metric:N",
                        title=None,
                        scale=alt.Scale(
                            domain=["% dos fundos", "% do PL"], range=[_ORANGE, _BLACK]
                        ),
                        legend=alt.Legend(orient="bottom"),
                    ),
                    tooltip=[
                        alt.Tooltip("period_label:N", title="Data-base"),
                        alt.Tooltip("metric:N", title="Métrica"),
                        alt.Tooltip("share:Q", title="Participação", format=".1%"),
                    ],
                )
                .properties(height=300, title="Evolução da monoestrutura")
            )
            st.altair_chart(
                history_chart,
                width="stretch",
                key=INDUSTRY_STRUCTURE_CHARTS[0],
            )

            current_long = current.melt(
                id_vars=["structure_model", "model_order"],
                value_vars=["fund_share_total", "pl_share_total"],
                var_name="metric",
                value_name="share",
            )
            current_long["metric"] = current_long["metric"].map(
                {"fund_share_total": "% dos fundos", "pl_share_total": "% do PL"}
            )
            current_long["structure_model"] = current_long["structure_model"].astype(str)
            structure_chart = (
                alt.Chart(current_long)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "share:Q",
                        title="Composição do estoque",
                        stack="normalize",
                        axis=alt.Axis(format=".0%", gridColor=_GRAY_LIGHT),
                    ),
                    y=alt.Y("metric:N", title=None, sort=["% dos fundos", "% do PL"]),
                    color=alt.Color(
                        "structure_model:N",
                        title=None,
                        sort=list(STRUCTURE_MODELS),
                        scale=alt.Scale(
                            domain=list(STRUCTURE_MODELS),
                            range=[_ORANGE, _BLACK, "#555555", "#777777", "#a6a6a6", "#d3d3d3"],
                        ),
                        legend=alt.Legend(orient="bottom", columns=3),
                    ),
                    order=alt.Order("model_order:Q"),
                    tooltip=[
                        alt.Tooltip("structure_model:N", title="Modelo"),
                        alt.Tooltip("metric:N", title="Métrica"),
                        alt.Tooltip("share:Q", title="Participação", format=".1%"),
                    ],
                )
                .properties(
                    height=180,
                    title=f"Decomposição atual · {_competence_label(pack.competences.latest_complete)}",
                )
            )
            st.altair_chart(
                structure_chart,
                width="stretch",
                key=INDUSTRY_STRUCTURE_CHARTS[1],
            )
            structure_table = current[
                ["structure_model", "funds", "fund_share_total", "pl_brl", "pl_share_total"]
            ].copy()
            structure_table.columns = ["Modelo", "Fundos", "% dos fundos", "PL", "% do PL"]
            structure_table["Modelo"] = structure_table["Modelo"].astype(str)
            structure_table["Fundos"] = structure_table["Fundos"].map(_fmt_int)
            structure_table["% dos fundos"] = structure_table["% dos fundos"].map(_fmt_pct)
            structure_table["PL"] = structure_table["PL"].map(lambda value: _fmt_bi(value, 1))
            structure_table["% do PL"] = structure_table["% do PL"].map(_fmt_pct)
            st.dataframe(structure_table, hide_index=True, width="stretch")
            coverage_row = current.iloc[0]
            st.markdown(
                '<div class="industry-note">Cobertura simultânea de administrador, gestor e '
                f'custodiante: <b>{_fmt_pct(coverage_row["provider_fund_coverage"])}</b> dos fundos '
                f'e <b>{_fmt_pct(coverage_row["provider_pl_coverage"])}</b> do PL. '
                "A parcela sem os três prestadores informados está em Dados incompletos.</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<h2>Ranking do estoque por prestador</h2>", unsafe_allow_html=True)
    if stock.empty:
        st.info("Base de ranking indisponível.")
        return
    controls = st.columns([1, 1.5, 1, 1])
    with controls[0]:
        role = st.selectbox("Papel", ["administrador", "gestor", "custodiante"], key="industry-stock-role")
    segments = ["Todos"] + sorted(value for value in stock["segment"].dropna().unique() if value != "Todos")
    with controls[1]:
        segment = st.selectbox("Segmento CVM", segments, key="industry-stock-segment")
    with controls[2]:
        metric = st.selectbox("Métrica", ["PL", "Fundos"], key="industry-stock-metric")
    with controls[3]:
        top_n = st.selectbox("Top", [5, 10, 15, 20], index=1, key="industry-stock-top")
    display = _stock_delta_display(stock, role, segment, metric, int(top_n))
    if display.empty:
        st.info("Sem dados para o recorte selecionado.")
        return
    current = display.sort_values("Pos. 2026YTD")
    chart_value = current["Valor 2026"] / (1e9 if metric == "PL" else 1)
    chart_frame = pd.DataFrame({"Participante": current["Participante"], "Valor": chart_value, "Posição": current["Pos. 2026YTD"]})
    chart = (
        alt.Chart(chart_frame)
        .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
        .encode(
            x=alt.X("Valor:Q", title="R$ bi" if metric == "PL" else "Fundos", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
            y=alt.Y("Participante:N", title=None, sort=alt.SortField("Posição", order="ascending"), axis=alt.Axis(labelLimit=280)),
            tooltip=["Participante:N", "Posição:Q", alt.Tooltip("Valor:Q", format=",.1f")],
        )
        .properties(height=max(300, len(chart_frame) * 26))
    )
    st.altair_chart(chart, width="stretch")
    formatted = display.drop(columns="Valor 2026").copy()
    for column in ["Share 2024", "Share 2025", "Share 2026YTD"]:
        formatted[column] = formatted[column].map(lambda value: "-" if pd.isna(value) else _fmt_pct(value))
    formatted["Delta share (p.p.)"] = formatted["Delta share (p.p.)"].map(
        lambda value: "-" if pd.isna(value) else f"{value:+.1f}".replace(".", ",")
    )
    st.dataframe(formatted, hide_index=True, width="stretch")
    nature = stock[stock["role"].eq(role)]["data_nature"].dropna()
    if not nature.empty:
        warning = role in {"gestor", "custodiante"}
        css_class = "industry-note warning" if warning else "industry-note"
        st.markdown(f'<div class="{css_class}">{nature.iloc[0]}.</div>', unsafe_allow_html=True)


def _render_industry_originators(originators: pd.DataFrame) -> None:
    st.markdown("<h2>Cedentes e originadores nomináveis</h2>", unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Ranking conservador: somente nomes acionados por evidência nominal no emissor, lastro ou devedor identificado. '
        "O restante do volume permanece explicitamente não identificado.</div>",
        unsafe_allow_html=True,
    )
    if originators.empty:
        st.info("Curadoria nominal indisponível.")
        return
    periods = list(dict.fromkeys(originators.sort_values("year")["period"]))
    period = st.selectbox("Período", periods, index=len(periods) - 1, key="industry-originator-period")
    selected = originators[originators["period"].astype(str).eq(str(period))].sort_values("rank")
    coverage = float(selected["identified_volume_coverage"].max()) if not selected.empty else 0.0
    top = selected.head(15).copy()
    cards = [
        _industry_kpi("Cobertura nominal", _fmt_pct(coverage), "do volume válido"),
        _industry_kpi("Nomes identificados", _fmt_int(selected["originator_group"].nunique()), str(period)),
        _industry_kpi("Volume identificado", _fmt_bi(selected["volume_brl"].sum(), 1), "regras de alta confiança"),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
    top["Volume (R$ bi)"] = top["volume_brl"] / 1e9
    chart = (
        alt.Chart(top)
        .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
        .encode(
            x=alt.X("Volume (R$ bi):Q", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
            y=alt.Y("originator_group:N", title=None, sort=alt.SortField("rank", order="ascending"), axis=alt.Axis(labelLimit=260)),
            tooltip=["originator_group:N", alt.Tooltip("Volume (R$ bi):Q", format=",.2f"), "offers:Q"],
        )
        .properties(height=max(320, len(top) * 26))
    )
    st.altair_chart(chart, width="stretch")
    table = top[["rank", "originator_group", "offers", "funds", "volume_brl", "share_of_total", "confidence"]].copy()
    table.columns = ["Posição", "Cedente/originador", "Ofertas", "Fundos", "Volume", "Share total", "Confiança"]
    table["Volume"] = table["Volume"].map(lambda value: _fmt_bi(value, 2))
    table["Share total"] = table["Share total"].map(_fmt_pct)
    st.dataframe(table, hide_index=True, width="stretch")


def _render_industry_investors(
    annual: pd.DataFrame,
    distribution: pd.DataFrame,
    investor_types: pd.DataFrame,
    offers: pd.DataFrame,
    pack: IndustryExecutivePack | None,
) -> None:
    st.markdown("<h2>Estrutura de cotistas do estoque</h2>", unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Distribuição dos fundos por número de contas de cotistas no '
        "Informe Mensal CVM. Os dois histogramas usam exatamente o mesmo universo, corte de PL e "
        "filtro ANBIMA.</div>",
        unsafe_allow_html=True,
    )
    if pack is None:
        st.info("Histograma do estoque indisponível.")
    else:
        st.markdown(
            f'<div class="industry-note warning">{_industry_anbima_coverage_note(pack)}</div>',
            unsafe_allow_html=True,
        )
        filter_columns = st.columns([1, 1.35, 1.65])
        with filter_columns[0]:
            min_pl_mm = st.selectbox(
                "Corte mínimo de PL",
                INDUSTRY_HOLDER_PL_CUTS_MM,
                format_func=lambda value: "Sem corte" if value == 0 else f"R$ {value:,} mi".replace(",", "."),
                key="industry-holder-min-pl",
            )
        with filter_columns[1]:
            anbima_type = st.selectbox(
                "Tipo ANBIMA",
                ["Todos", *ANBIMA_TYPES, ANBIMA_ND],
                key="industry-holder-anbima-type",
            )
        focus_options = _industry_holder_focus_options(pack, anbima_type)
        if st.session_state.get("industry-holder-anbima-focus") not in focus_options:
            st.session_state["industry-holder-anbima-focus"] = "Todos"
        with filter_columns[2]:
            anbima_focus = st.selectbox(
                "Foco de atuação ANBIMA",
                focus_options,
                key="industry-holder-anbima-focus",
            )
        holder_histogram, holder_coverage = _industry_holder_histogram_frames(
            pack,
            min_pl_brl=float(min_pl_mm) * 1e6,
            anbima_type=anbima_type,
            anbima_focus=anbima_focus,
        )
        if holder_histogram.empty:
            st.info("Nenhum fundo com número de cotistas válido para o recorte selecionado.")
        else:
            color = alt.Color(
                "anbima_tipo:N",
                title=None,
                sort=[*ANBIMA_TYPES, ANBIMA_ND],
                scale=alt.Scale(
                    domain=[*ANBIMA_TYPES, ANBIMA_ND],
                    range=[_ORANGE, _BLACK, "#666666", "#999999", "#c7c7c7"],
                ),
                legend=alt.Legend(orient="bottom", columns=2),
            )
            left, right = st.columns(2)
            with left:
                funds_chart = (
                    alt.Chart(holder_histogram)
                    .mark_bar()
                    .encode(
                        x=alt.X(
                            "cotistas_bucket:N",
                            title="Contas de cotistas",
                            sort=list(HOLDER_BUCKETS),
                        ),
                        y=alt.Y(
                            "sum(fund_count):Q",
                            title="Quantidade de fundos",
                            axis=alt.Axis(gridColor=_GRAY_LIGHT, tickMinStep=1),
                        ),
                        color=color,
                        order=alt.Order("type_order:Q"),
                        tooltip=[
                            alt.Tooltip("cotistas_bucket:N", title="Contas"),
                            alt.Tooltip("anbima_tipo:N", title="Tipo ANBIMA"),
                            alt.Tooltip("fund_count:Q", title="Fundos", format=",.0f"),
                        ],
                    )
                    .properties(height=320, title="Quantidade de fundos")
                )
                st.altair_chart(
                    funds_chart,
                    width="stretch",
                    key=INDUSTRY_STRUCTURE_CHARTS[2],
                )
            with right:
                pl_chart = (
                    alt.Chart(holder_histogram)
                    .mark_bar()
                    .encode(
                        x=alt.X(
                            "cotistas_bucket:N",
                            title="Contas de cotistas",
                            sort=list(HOLDER_BUCKETS),
                        ),
                        y=alt.Y(
                            "sum(pl_bi):Q",
                            title="PL (R$ bi)",
                            axis=alt.Axis(gridColor=_GRAY_LIGHT),
                        ),
                        color=color,
                        order=alt.Order("type_order:Q"),
                        tooltip=[
                            alt.Tooltip("cotistas_bucket:N", title="Contas"),
                            alt.Tooltip("anbima_tipo:N", title="Tipo ANBIMA"),
                            alt.Tooltip("pl_bi:Q", title="PL (R$ bi)", format=",.1f"),
                        ],
                    )
                    .properties(height=320, title="Volume de PL")
                )
                st.altair_chart(
                    pl_chart,
                    width="stretch",
                    key=INDUSTRY_STRUCTURE_CHARTS[3],
                )
        if not holder_coverage.empty:
            coverage = holder_coverage.iloc[0]
            warning_class = " warning" if str(coverage.get("warning", "")).strip() else ""
            st.markdown(
                f'<div class="industry-note{warning_class}">Cobertura do histograma: '
                f'<b>{_fmt_pct(coverage["fund_coverage"])}</b> dos fundos elegíveis e '
                f'<b>{_fmt_pct(coverage["pl_coverage"])}</b> do PL elegível. '
                f'{str(coverage.get("warning", ""))}</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<h2>Distribuição primária nas ofertas</h2>", unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Os indicadores abaixo descrevem investidores informados em '
        "ofertas públicas encerradas. Não representam a estrutura atual de cotistas do estoque "
        "nem negociação no mercado secundário.</div>",
        unsafe_allow_html=True,
    )
    if not annual.empty:
        latest = annual.sort_values("year").iloc[-1]
        cards = [
            _industry_kpi("Ofertas c/ composição", _fmt_int(latest["offers_with_investor_data"]), str(latest["period"])),
            _industry_kpi("1 investidor", _fmt_pct(latest["single_investor_share"]), "ofertas encerradas com dado"),
            _industry_kpi("Mediana", _fmt_int(latest["median_investors"]), "investidores por oferta"),
            _industry_kpi("Cobertura", _fmt_pct(latest["investor_data_coverage"]), "ofertas encerradas"),
        ]
        st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
    left, right = st.columns([1.1, 0.9])
    with left:
        if not distribution.empty:
            order = ["1 investidor", "2 investidores", "3-5 investidores", "6-20 investidores", "21+ investidores"]
            plot = distribution[distribution["investor_bucket"].isin(order)].copy()
            chart = (
                alt.Chart(plot)
                .mark_bar()
                .encode(
                    x=alt.X("period:N", title=None),
                    y=alt.Y("offer_share:Q", title="% das ofertas", stack="normalize", axis=alt.Axis(format="%")),
                    color=alt.Color(
                        "investor_bucket:N",
                        sort=order,
                        scale=alt.Scale(domain=order, range=[_ORANGE, _BLACK, "#168aad", "#2b7a55", _GRAY]),
                        legend=alt.Legend(title=None, orient="bottom"),
                    ),
                    order=alt.Order("investor_bucket:N", sort="ascending"),
                    tooltip=["period:N", "investor_bucket:N", alt.Tooltip("offer_share:Q", format=".1%")],
                )
                .properties(height=330, title="Número de investidores por oferta")
            )
            st.altair_chart(chart, width="stretch")
    with right:
        if not investor_types.empty:
            latest_period = investor_types.sort_values("year").iloc[-1]["period"]
            types = investor_types[investor_types["period"].eq(latest_period)].sort_values("placed_volume_proxy_brl", ascending=False)
            types = types.assign(valor_bi=types["placed_volume_proxy_brl"] / 1e9)
            chart = (
                alt.Chart(types)
                .mark_bar(color=_ORANGE, cornerRadiusEnd=2)
                .encode(
                    x=alt.X("valor_bi:Q", title="R$ bi, proxy", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    y=alt.Y("investor_type:N", title=None, sort="-x", axis=alt.Axis(labelLimit=220)),
                    tooltip=["investor_type:N", alt.Tooltip("valor_bi:Q", format=",.2f"), alt.Tooltip("value_share:Q", format=".1%")],
                )
                .properties(height=330, title=f"Composição por tipo · {latest_period}")
            )
            st.altair_chart(chart, width="stretch")
    if not offers.empty and "secondary_market_infrastructure" in offers:
        closed = offers[_truthy(offers["closed_offer"])]
        market = closed[_truthy(closed["secondary_market_infrastructure"])]
        st.markdown(
            '<div class="industry-note warning">'
            f'{_fmt_int(market["offer_id"].nunique())} ofertas encerradas mencionam infraestrutura/mercado de negociação. '
            "Isso indica elegibilidade contratual, não volume negociado, giro ou velocidade de venda. "
            "Turnover secundário exige negócios da B3/ANBIMA em base transacional.</div>",
            unsafe_allow_html=True,
        )


def _render_large_funds(large_funds: pd.DataFrame, large_docs: pd.DataFrame, latest_complete: str) -> None:
    st.markdown("<h2>FIDCs acima de R$ 5 bilhões</h2>", unsafe_allow_html=True)
    if large_funds.empty:
        st.info("Classificação documental indisponível.")
        return
    publishable = large_funds["classification_confidence"].astype(str).str.lower().eq("alta").sum()
    cards = [
        _industry_kpi("Fundos", _fmt_int(len(large_funds)), f"corte {_competence_label(latest_complete, lower=True)}"),
        _industry_kpi("PL coberto", _fmt_bi(large_funds["pl_brl"].sum(), 1), "16 maiores veículos"),
        _industry_kpi("Classificação publicável", f"{_fmt_int(publishable)}/{_fmt_int(len(large_funds))}", "confiança alta"),
    ]
    if diagnostics_enabled():
        cards.extend(
            [
                _industry_kpi("Documentos listados", _fmt_int(large_funds["documents_listed"].sum()), "CVM/FundosNet"),
                _industry_kpi("Docs classificatórios", _fmt_int(large_funds["documents_relevant"].sum()), "regulamentos, emissões, atas e eventos"),
                _industry_kpi("Docs lidos", _fmt_int(large_funds["documents_read"].sum()), "payloads PDF/DOCX processados"),
                _industry_kpi("Com texto", _fmt_int(large_funds["documents_with_text"].sum()), "extração textual utilizável"),
            ]
        )
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
    display = large_funds[
        [
            "fund_name",
            "pl_brl",
            "ime_segment",
            "anbima_type_document",
            "anbima_focus_document",
            "document_segment_n1",
            "document_segment_n2",
            "classification_confidence",
            "documents_read",
            "documents_relevant",
        ]
    ].copy()
    display.columns = ["Fundo", "PL", "Segmento IME", "Tipo ANBIMA", "Foco ANBIMA", "Segmento econômico", "Subsegmento", "Confiança", "Lidos", "Escopo"]
    for column in ("Segmento IME", "Tipo ANBIMA", "Foco ANBIMA", "Segmento econômico", "Subsegmento", "Confiança"):
        display[column] = display[column].fillna("não localizado").replace({"None": "não localizado", "nan": "não localizado", "": "não localizado"})
    display["PL"] = display["PL"].map(lambda value: _fmt_bi(value, 1))
    display["Cobertura"] = display.apply(lambda row: f"{int(row['Lidos'])}/{int(row['Escopo'])}", axis=1)
    display = display.drop(columns=["Lidos", "Escopo"])
    st.dataframe(display, hide_index=True, width="stretch", height=610)
    cloudwalk = large_funds[large_funds["fund_name"].str.contains("CLOUDWALK", case=False, na=False)]
    if not cloudwalk.empty:
        row = cloudwalk.iloc[0]
        st.markdown(
            '<div class="industry-note">CloudWalk confirma a necessidade do duplo rótulo: '
            f'ANBIMA <b>{row.get("anbima_type_document", "n/d")}</b> / {row.get("anbima_focus_document", "n/d")}; '
            f'lastro econômico <b>{row["document_segment_n2"]}</b>.</div>',
            unsafe_allow_html=True,
        )
    with st.expander("Dados e exportações", expanded=False):
        left, right, _spacer = st.columns([1, 1, 3])
        with left:
            st.download_button(
                "Baixar classificação",
                large_funds.to_csv(index=False).encode("utf-8"),
                file_name="fidcs_acima_5bi_classificacao.csv",
                mime="text/csv",
                icon=":material/download:",
                width="stretch",
            )
        with right:
            st.download_button(
                "Baixar ledger documental",
                large_docs.to_csv(index=False).encode("utf-8") if not large_docs.empty else b"",
                file_name="fidcs_acima_5bi_documentos.csv",
                mime="text/csv",
                icon=":material/download:",
                width="stretch",
            )


def _revision_frame(payload: dict[str, object], key: str) -> pd.DataFrame:
    rows = payload.get(key, [])
    return pd.DataFrame(rows if isinstance(rows, list) else [])


def _revision_offer_comparable_frame(payload: dict[str, object]) -> pd.DataFrame:
    """Return the current Jan–Jun comparison, with the prior key as fallback."""

    frame = _revision_frame(payload, "closed_offers_jan_june")
    if frame.empty:
        frame = _revision_frame(payload, "closed_offers_jan_may")
    return frame


def _revision_offer_current_row(
    payload: dict[str, object],
    annual: pd.DataFrame | None = None,
) -> pd.Series:
    """Merge the 2026 annual metrics with the authoritative comparable cutoff."""

    annual_frame = annual.copy() if annual is not None else _revision_frame(
        payload, "closed_offers_annual"
    )
    current = pd.Series(dtype=object)
    if not annual_frame.empty and "year" in annual_frame:
        annual_frame["year"] = pd.to_numeric(annual_frame["year"], errors="coerce")
        annual_2026 = annual_frame[annual_frame["year"].eq(2026)]
        source = annual_2026 if not annual_2026.empty else annual_frame
        current = source.sort_values("year").iloc[-1].copy()

    comparable = _revision_offer_comparable_frame(payload)
    if not comparable.empty and "year" in comparable:
        comparable = comparable.copy()
        comparable["year"] = pd.to_numeric(comparable["year"], errors="coerce")
        comparable_2026 = comparable[comparable["year"].eq(2026)]
        source = comparable_2026 if not comparable_2026.empty else comparable
        comparable_current = source.sort_values("year").iloc[-1]
        for key, value in comparable_current.items():
            if pd.notna(value):
                current.loc[key] = value
    return current


def _revision_offers_cutoff(payload: dict[str, object]) -> str:
    """Return the audited comparable cutoff used by every offers view."""

    comparable = _revision_offer_comparable_frame(payload)
    if not comparable.empty and "period_end" in comparable:
        years = pd.to_numeric(comparable.get("year"), errors="coerce")
        current = comparable.loc[years.eq(2026), "period_end"]
        parsed = pd.to_datetime(current, errors="coerce").dropna()
        if not parsed.empty:
            return parsed.max().strftime("%Y-%m-%d")
    return "2026-06-30"


def _revision_holder_distribution_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize holder-bucket shares from absolute values within each period."""
    holders = frame.copy()
    if holders.empty:
        return holders

    for column in ("fundos", "pl"):
        values = holders[column] if column in holders.columns else pd.Series(0.0, index=holders.index)
        holders[column] = pd.to_numeric(values, errors="coerce").fillna(0)
        if holders[column].lt(0).any():
            raise ValueError(f"distribuição por cotistas contém {column} negativo")

    grouping = holders["competencia"] if "competencia" in holders else pd.Series("total", index=holders.index)
    fund_total = holders["fundos"].groupby(grouping).transform("sum")
    pl_total = holders["pl"].groupby(grouping).transform("sum")
    holders["share_fundos"] = holders["fundos"].div(fund_total.where(fund_total.gt(0))).fillna(0.0)
    holders["share_pl"] = holders["pl"].div(pl_total.where(pl_total.gt(0))).fillna(0.0)
    return holders


def _revision_history_frame(
    payload: dict[str, object],
    key: str,
    *,
    fallback_key: str | None = None,
) -> pd.DataFrame:
    """Load a comparison block and add a concise period label for charts."""
    frame = _revision_frame(payload, key)
    if frame.empty and fallback_key:
        frame = _revision_frame(payload, fallback_key)
        if not frame.empty and "competencia" not in frame:
            frame.insert(0, "competencia", str(payload.get("latest_complete") or ""))
    if frame.empty:
        return frame
    if "competencia" not in frame:
        raise ValueError(f"bloco histórico sem competência: {key}")
    frame = frame.copy()
    frame["competencia"] = frame["competencia"].astype(str)
    frame["Período"] = frame["competencia"].map(_short_competence_label)
    return frame


def _revision_period_encoding(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Return chronological labels and the fixed before/after neutral-accent palette."""
    order = (
        frame[["competencia", "Período"]]
        .drop_duplicates()
        .sort_values("competencia")["Período"]
        .astype(str)
        .tolist()
    )
    if not order:
        return [], []
    colors = [_GRAY] * max(len(order) - 1, 0) + [_ORANGE]
    return order, colors


def _revision_comparison_color(frame: pd.DataFrame, *, show_legend: bool = True) -> alt.Color:
    period_order, period_colors = _revision_period_encoding(frame)
    return alt.Color(
        "Período:N",
        scale=alt.Scale(domain=period_order, range=period_colors),
        legend=alt.Legend(title=None, orient="bottom") if show_legend else None,
    )


def _revision_profile_value(profile: dict[str, object], *keys: str) -> object:
    for key in keys:
        value = profile.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def _revision_profile_text(value: object) -> str:
    if isinstance(value, list):
        text = "; ".join(str(item) for item in value if str(item).strip())
        return text.replace("—", "-").replace("–", "-")
    if isinstance(value, dict):
        text = "; ".join(f"{key}: {item}" for key, item in value.items() if str(item).strip())
        return text.replace("—", "-").replace("–", "-")
    return str(value or "").strip().replace("—", "-").replace("–", "-")


def _render_revision_atlantico(payload: dict[str, object]) -> None:
    """Render the sourced Atlântico case study when the payload carries it."""
    raw_profile = payload.get("atlantico_profile")
    profile = raw_profile if isinstance(raw_profile, dict) else {}
    history = _revision_history_frame(payload, "atlantico_history")
    if not profile and history.empty:
        return

    name = _revision_profile_text(
        _revision_profile_value(profile, "denominacao", "nome", "fundo")
    ) or "Atlântico FIDC"
    cnpj = _revision_profile_text(_revision_profile_value(profile, "cnpj", "cnpj_fundo"))
    st.markdown(f"<h2>{name}: estrutura e leitura da inadimplência</h2>", unsafe_allow_html=True)
    if cnpj:
        st.caption(f"CNPJ {cnpj}")

    left, right = st.columns(2)
    structure_fields = (
        ("Estratégia", ("estrategia", "tese", "funcionamento_economico")),
        ("Cedente/originador", ("cedente_originador", "cedentes", "originador")),
        ("Sacados/devedores", ("perfil_sacados", "sacado_devedor", "sacados")),
        ("Recebíveis", ("natureza_recebiveis", "recebiveis", "ativos")),
    )
    evidence_fields = (
        ("Classificação", ("classificacao", "status_np", "categoria")),
        ("Administrador", ("administrador", "admin_nome")),
        ("Gestor", ("gestor", "gestor_nome")),
        ("Custodiante", ("custodiante", "custodiante_nome")),
        ("Público-alvo", ("publico_alvo", "investidores")),
        ("Subordinação", ("subordinacao", "subordinacao_garantias")),
        ("Garantias", ("garantias",)),
    )
    with left:
        st.markdown("**Funcionamento econômico**")
        for label, aliases in structure_fields:
            value = _revision_profile_text(_revision_profile_value(profile, *aliases))
            if value:
                st.markdown(f"**{label}:** {value}")
    with right:
        st.markdown("**Enquadramento e prestadores**")
        for label, aliases in evidence_fields:
            value = _revision_profile_text(_revision_profile_value(profile, *aliases))
            if value:
                st.markdown(f"**{label}:** {value}")

    explanation = _revision_profile_text(
        _revision_profile_value(
            profile,
            "leitura_inadimplencia",
            "explicacao_inadimplencia",
            "interpretacao",
        )
    )
    if explanation:
        st.info(explanation)
    bridge_interpretation = _revision_profile_text(
        _revision_profile_value(profile, "bridge_interpretacao", "leitura_bridge")
    )
    if bridge_interpretation:
        st.markdown(f"**Quebra de série em jul/24:** {bridge_interpretation}")
    audit_reading = _revision_profile_text(
        _revision_profile_value(profile, "auditoria_valor_justo", "auditoria")
    )
    if audit_reading:
        st.markdown(f"**Auditoria e valor justo:** {audit_reading}")

    snapshot = profile.get("snapshot")
    if isinstance(snapshot, dict) and snapshot:
        snapshot_period = _short_competence_label(snapshot.get("competencia"))
        snapshot_parts = []
        for label, key in (
            ("PL", "pl"),
            ("carteira", "carteira"),
            ("inadimplência bruta", "inadimplencia_bruta"),
            ("acima de 1.080 dias", "vencidos_mais_1080d"),
        ):
            value = pd.to_numeric(pd.Series([snapshot.get(key)]), errors="coerce").iloc[0]
            if pd.notna(value):
                snapshot_parts.append(f"{label} {_fmt_bi(float(value), 3)}")
        share_parts = []
        for label, key in (
            ("inadimplência/carteira", "inadimplencia_share_carteira"),
            (">1.080 dias/inadimplência", "mais_1080_share_inadimplencia"),
        ):
            value = pd.to_numeric(pd.Series([snapshot.get(key)]), errors="coerce").iloc[0]
            if pd.notna(value):
                share_parts.append(f"{label} {_fmt_pct(float(value))}")
        if snapshot_parts or share_parts:
            st.markdown(
                f"**Fotografia de {snapshot_period}:** "
                + "; ".join(snapshot_parts + share_parts)
                + "."
            )

    if not history.empty:
        aliases = {
            "PL": ("pl", "pl_brl"),
            "Carteira": ("carteira", "carteira_brl", "carteira_dc"),
            "Inad. bruta": (
                "inadimplencia_bruta",
                "inadimplencia_reportada",
                "inad_bruta_brl",
            ),
            "Inad. ajustada": ("inadimplencia_ajustada", "inad_ajustada_brl"),
            ">360 dias": ("vencidos_mais_360d", "aging_mais_360d", "bucket_acima_360d"),
            ">1.080 dias": ("vencidos_mais_1080d", "aging_mais_1080d"),
            "Excesso": ("excesso", "excesso_brl", "excesso_removido_brl"),
        }
        display = pd.DataFrame({"Competência": history["Período"]})
        for label, candidates in aliases.items():
            column = next((candidate for candidate in candidates if candidate in history), None)
            if column:
                display[label] = pd.to_numeric(history[column], errors="coerce").map(
                    lambda value: _fmt_bi(float(value), 3) if pd.notna(value) else "n/d"
                )
        if "administrador" in history:
            display["Administrador"] = history["administrador"].fillna("").astype(str)
        st.dataframe(display, hide_index=True, width="stretch")

    limitations = _revision_profile_text(
        _revision_profile_value(profile, "limitacoes", "limitações", "lacunas")
    )
    if limitations:
        st.warning(limitations)

    sources = _revision_profile_value(profile, "fontes", "sources")
    if isinstance(sources, dict):
        sources = [{"label": key, "url": value} for key, value in sources.items()]
    if isinstance(sources, list) and sources:
        st.markdown("**Fontes consultadas**")
        for item in sources:
            if isinstance(item, dict):
                label = _revision_profile_text(
                    item.get("label") or item.get("nome") or item.get("source") or "Fonte"
                )
                url = str(item.get("url") or item.get("link") or "")
                consulted = str(item.get("data_consulta") or item.get("consulted_on") or "")
                if url:
                    suffix = f" (consulta em {consulted})" if consulted else ""
                    st.markdown(f"[{label}]({url}){suffix}")
                else:
                    st.markdown(label)
            elif str(item).strip():
                st.markdown(str(item))


def _render_revision_conclusions(payload: dict[str, object]) -> None:
    """Mirror the executive conclusion slide with values from the revision payload."""

    metrics = dict(payload.get("conclusion_metrics") or {})
    annual = _revision_frame(payload, "closed_offers_annual")
    latest_period = str(payload.get("latest_complete") or "2026-06")
    latest_stock_label = _short_competence_label(latest_period).lower()
    offers_cutoff = _revision_offers_cutoff(payload)
    holder_history = _revision_history_frame(payload, "holder_distribution_history")
    concentration = _revision_history_frame(
        payload,
        "provider_concentration_history",
        fallback_key="provider_concentration",
    )
    ranking = _revision_frame(payload, "provider_historical_ranking")
    service_model = _revision_frame(payload, "service_model")
    originators = _revision_frame(payload, "closed_offer_originators_2026")
    ticket_distribution = _revision_frame(payload, "closed_offer_ticket_distribution")
    qa = dict(payload.get("qa_latest") or {})
    reag = dict(payload.get("reag_admin_summary") or {})
    leadership = dict(payload.get("provider_leadership_attribution") or {})

    current_offer = _revision_offer_current_row(payload, annual)
    holder_latest = (
        holder_history[
            holder_history["competencia"].eq(latest_period)
        ]
        if not holder_history.empty
        else pd.DataFrame()
    )
    share_funds_up_to_10 = float(
        metrics.get("holder_ge_200m_share_fundos_ate_10_contas")
        or (
            holder_latest[
                holder_latest["bucket"].astype(str).isin(["0", "1", "2–3", "4–5", "6–10"])
            ]["share_fundos"].sum()
            if not holder_latest.empty
            else 0.0
        )
    )
    concentration_latest = pd.DataFrame()
    if not concentration.empty:
        concentration_latest = concentration[
            concentration["competencia"].eq(latest_period)
        ].set_index("papel")

    def top10(role: str) -> float:
        if concentration_latest.empty or role not in concentration_latest.index:
            return 0.0
        return float(concentration_latest.loc[role, "top10_share"])

    current_ranking = (
        ranking[ranking["competencia"].eq(latest_period)].copy()
        if not ranking.empty
        else pd.DataFrame()
    )

    def provider_pl(role: str, participant: str) -> float:
        if current_ranking.empty:
            return 0.0
        match = current_ranking[
            current_ranking["papel"].eq(role)
            & current_ranking["participante"].astype(str).str.casefold().eq(participant.casefold())
        ]
        return float(match.iloc[0]["pl_brl"]) if not match.empty else 0.0

    mono = service_model[service_model["modelo_prestacao"].eq("Monoestrutura")]
    same_admin_custody = service_model[
        service_model["modelo_prestacao"].isin(
            ["Monoestrutura", "Administração + Custódia"]
        )
    ]
    same_admin_custody_funds = int(
        metrics.get("admin_custodia_juntas_fundos")
        or same_admin_custody.get("fundos", pd.Series(dtype=float)).sum()
    )
    same_admin_custody_share = float(
        metrics.get("admin_custodia_juntas_share_pl")
        or same_admin_custody.get("share_pl", pd.Series(dtype=float)).sum()
    )
    mono_share = float(
        metrics.get("monoestrutura_share_pl")
        or (mono.iloc[0]["share_pl"] if not mono.empty else 0.0)
    )

    cloudwalk = (
        originators[
            originators["originator_group"].astype(str).str.casefold().eq("cloudwalk")
        ]
        if not originators.empty
        else pd.DataFrame()
    )
    cloudwalk_volume = (
        float(cloudwalk.iloc[0]["registered_volume_brl"])
        if not cloudwalk.empty
        else 0.0
    )

    ticket_mean = float(current_offer.get("mean_registered_ticket_brl", 0.0))
    ticket_median = float(current_offer.get("median_registered_ticket_brl", 0.0))
    pf_share = float(current_offer.get("natural_person_placed_volume_share", 0.0))
    pf_coverage = float(
        current_offer.get("placed_quantity_registered_volume_coverage", 0.0)
    )
    offers_count = int(current_offer.get("closed_offers", 0))
    offers_volume = float(current_offer.get("registered_volume_brl", 0.0))

    jan_june = _revision_offer_comparable_frame(payload)
    jan_june_lookup = (
        jan_june.set_index("year")["registered_volume_brl"].to_dict()
        if not jan_june.empty
        else {}
    )
    jan_june_2026 = float(jan_june_lookup.get(2026, 0.0))

    def comparable_growth(year: int) -> float:
        prior = float(jan_june_lookup.get(year, 0.0))
        return jan_june_2026 / prior - 1 if prior else 0.0

    growth_2025 = comparable_growth(2025)
    growth_2024 = comparable_growth(2024)
    btg_roots = int(metrics.get("btg_bank_cohort_listed_roots", 0))
    btg_observed = int(metrics.get("btg_bank_cohort_observed_funds", 0))
    btg_observed_pl = float(metrics.get("btg_bank_cohort_pl_brl", 0))
    btg_combo_funds = int(metrics.get("btg_bank_cohort_combo_funds", 0))
    btg_combo_pl = float(metrics.get("btg_bank_cohort_combo_pl_brl", 0))

    large_offer_bucket = pd.DataFrame()
    if not ticket_distribution.empty:
        large_offer_bucket = ticket_distribution[
            ticket_distribution["period_label"].astype(str).eq("2026 jan–jun")
            & pd.to_numeric(
                ticket_distribution.get("ticket_floor_brl"), errors="coerce"
            ).ge(500_000_000)
        ]
    large_offer_count = int(
        large_offer_bucket.iloc[0].get("closed_offers", 0)
        if not large_offer_bucket.empty
        else 0
    )
    large_offer_share = float(
        large_offer_bucket.iloc[0].get("offer_share", 0.0)
        if not large_offer_bucket.empty
        else 0.0
    )
    large_offer_volume_share = float(
        large_offer_bucket.iloc[0].get("registered_volume_share", 0.0)
        if not large_offer_bucket.empty
        else 0.0
    )
    qi_legacy_share = float(
        dict(leadership.get("qi") or {}).get("legacy_share_2024", 0.0)
    )
    cielo_share_migrated = (
        float(metrics.get("admin_transition_2024_2025_cielo_pl_brl", 0.0))
        / float(metrics.get("admin_transition_2024_2025_changed_pl_brl", 0.0))
        if float(metrics.get("admin_transition_2024_2025_changed_pl_brl", 0.0))
        else 0.0
    )
    btg_combo_share = (
        btg_combo_pl / float(metrics.get("btg_combo_tres_funcoes_pl_brl", 0.0))
        if float(metrics.get("btg_combo_tres_funcoes_pl_brl", 0.0))
        else 0.0
    )
    cloudwalk_share = cloudwalk_volume / offers_volume if offers_volume else 0.0
    offer_growth_brl = jan_june_2026 - float(jan_june_lookup.get(2025, 0.0))
    cloudwalk_growth_share = (
        cloudwalk_volume / offer_growth_brl if offer_growth_brl else 0.0
    )
    growth_2025_ex_cloudwalk = (
        (jan_june_2026 - cloudwalk_volume)
        / float(jan_june_lookup.get(2025, 0.0))
        - 1
        if float(jan_june_lookup.get(2025, 0.0))
        else 0.0
    )

    conclusions = [
        (
            "01 · Distribuição após a RCVM 175 segue institucional e concentrada",
            [
                f"A mediana equivale a {_fmt_pct(ticket_median / ticket_mean if ticket_mean else 0)} da média ({_fmt_mi(ticket_median)} versus {_fmt_mi(ticket_mean)}); {_fmt_int(large_offer_count)} ofertas ({_fmt_pct(large_offer_share)}) ≥ R$ 500 mi concentraram {_fmt_pct(large_offer_volume_share)} do volume.",
                f"Pessoas físicas responderam por apenas {_fmt_pct(pf_share)} do volume colocado estimado; {_fmt_pct(share_funds_up_to_10)} dos fundos com PL ≥ R$ 200 mi têm até dez contas.",
            ],
        ),
        (
            "02 · Verticalização define o modelo operacional da indústria",
            [
                f"Administração e custódia estão no mesmo conglomerado em {_fmt_pct(same_admin_custody_share)} do PL — nove em cada dez reais da indústria.",
                f"Monoestruturas, com as três funções no mesmo grupo, já concentram {_fmt_pct(mono_share)} do PL.",
            ],
        ),
        (
            "03 · Escala independente está concentrada em poucas plataformas",
            [
                f"QI Tech lidera administração e praticamente empata com o BTG em custódia; {_fmt_pct(qi_legacy_share, 0)} de sua base administrativa em dez/24 veio do legado Singulare.",
                f"Oliveira Trust é a 3ª maior gestora, com {_fmt_bi(provider_pl('gestor', 'Oliveira Trust'), 1)}; na coorte CBSF/Reag, {_fmt_pct(float(reag.get('migrated_share_current', 0)))} do PL continuante já havia migrado até {latest_stock_label}.",
            ],
        ),
        (
            "04 · Trocas de administrador são pontuais e concentradas",
            [
                f"Apenas {_fmt_pct(float(metrics.get('admin_transition_2024_2025_changed_share_pl', 0)))} do PL comparável trocou de administrador entre dez/24 e dez/25: {_fmt_bi(float(metrics.get('admin_transition_2024_2025_changed_pl_brl', 0)), 1)} em {_fmt_int(metrics.get('admin_transition_2024_2025_changed_funds', 0))} fundos.",
                f"Dois FIDCs Cielo responderam por {_fmt_pct(cielo_share_migrated, 0)} do fluxo, com {_fmt_bi(float(metrics.get('admin_transition_2024_2025_cielo_pl_brl', 0)), 1)} migrando de Oliveira Trust para Bradesco.",
            ],
        ),
        (
            "05 · Gestão preserva o maior espaço competitivo",
            [
                f"As dez maiores gestoras reúnem apenas {_fmt_pct(top10('gestor'))} do PL ex-FIC, cerca da metade da fatia dos Top 10 de administração e custódia.",
                "A concentração menor deixa uma parcela maior do mercado acessível a gestoras independentes.",
            ],
        ),
        (
            "06 · Coorte bancária explica dois terços do combo completo do BTG",
            [
                f"Dos {_fmt_int(btg_observed)} FIDCs observados na coorte, {_fmt_int(btg_combo_funds)} concentram as três funções no BTG e representam {_fmt_pct(float(metrics.get('btg_bank_cohort_combo_share_pl', 0)))} do PL da coorte — {_fmt_bi(btg_combo_pl, 1)}.",
                f"Essa carteira responde por {_fmt_pct(btg_combo_share, 0)} de todo o PL atendido pelo BTG no combo completo.",
            ],
        ),
        (
            "07 · Emissões aceleraram; a maior oferta explica dois terços do avanço",
            [
                f"As {_fmt_int(offers_count)} ofertas encerradas em jan–jun/26 somaram {_fmt_bi(offers_volume, 1)}, avanço de {_fmt_pct(growth_2025, 0)} sobre 2025 e {_fmt_pct(growth_2024, 0)} sobre 2024.",
                f"CloudWalk Bela respondeu por {_fmt_pct(cloudwalk_share, 0)} do volume e {_fmt_pct(cloudwalk_growth_share, 0)} do crescimento; numa sensibilidade sem essa oferta, o avanço seria {_fmt_pct(growth_2025_ex_cloudwalk, 0)}.",
            ],
        ),
    ]

    editorial_conclusions = payload.get("executive_conclusions")
    if isinstance(editorial_conclusions, list):
        materialized_conclusions: list[tuple[str, list[str]]] = []
        for row in sorted(
            (item for item in editorial_conclusions if isinstance(item, dict)),
            key=lambda item: int(item.get("order") or 0),
        ):
            title = str(row.get("title") or "").strip()
            bullets = [
                str(item).strip()
                for item in row.get("bullets", [])
                if str(item).strip()
            ]
            if title and bullets:
                materialized_conclusions.append((title, bullets))
        if len(materialized_conclusions) == 7:
            conclusions = materialized_conclusions

    st.markdown("<h2>Principais conclusões</h2>", unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-conclusions">'
        + "".join(
            f'<article class="industry-conclusion"><h3>{html.escape(title)}</h3><ul>'
            + "".join(f"<li>{html.escape(item)}</li>" for item in items)
            + "</ul></article>"
            for title, items in conclusions
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    editorial_notes = payload.get("executive_conclusion_notes")
    if isinstance(editorial_notes, list) and editorial_notes:
        st.caption(" · ".join(str(note).strip() for note in editorial_notes if str(note).strip()))
    else:
        st.caption(
            f"Fontes: CVM, ANBIMA, FundosNet, BCB e FIDCs.xlsx. Estoque em {latest_stock_label}; "
            f"ofertas até {_date_label(offers_cutoff)}; proxy colocado com {_fmt_pct(pf_coverage)} de cobertura."
        )

    st.markdown("<h2>Grandes números</h2>", unsafe_allow_html=True)
    pl = _revision_frame(payload, "pl_history")
    latest = pl.iloc[-1] if not pl.empty else pd.Series(dtype=object)
    first = pl.iloc[0] if not pl.empty else pd.Series(dtype=object)
    latest_pl = float(latest.get("pl_ex_fic", 0))
    first_pl = float(first.get("pl_ex_fic", 0))
    growth_multiple = latest_pl / first_pl if first_pl else 0.0
    growth_multiple_label = f"{growth_multiple:.1f}".replace(".", ",")
    summary_rows = [
        (
            _fmt_bi(latest_pl, 0),
            f"PL ex-FIC em {latest_stock_label}",
            f"{growth_multiple_label}× 2015; FIC-FIDC: {_fmt_bi(float(latest.get('pl_fic_componente', 0)), 1)}.",
        ),
        (
            _fmt_pct(share_funds_up_to_10, 0),
            "dos fundos ≥ R$ 200 mi têm até 10 contas",
            f"{_fmt_pct(float(metrics.get('holder_ge_200m_share_pl_ate_10_contas', 0)))} do PL do recorte.",
        ),
        (
            _fmt_int(qa.get("casos_inad_supera_carteira", 0)),
            "veículos acima da carteira",
            f"Cap: {_fmt_bi(float(qa.get('excesso_removido_brl', 0)), 1)}.",
        ),
        (
            _fmt_pct(mono_share),
            "do PL em monoestruturas",
            "Três funções no mesmo conglomerado.",
        ),
    ]
    st.markdown(
        '<div class="industry-summary">'
        + "".join(
            '<div class="industry-summary-row">'
            f'<div class="industry-summary-value">{value}</div>'
            f'<div class="industry-summary-copy"><h3>{title}</h3><p>{detail}</p></div>'
            "</div>"
            for value, title, detail in summary_rows
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Mesmas fontes e datas-base da seção anterior.")


def _render_revision_overview(payload: dict[str, object]) -> None:
    pl = _revision_frame(payload, "pl_history")
    pl_cagr_periods = _revision_frame(payload, "pl_total_cagr_periods")
    qa = dict(payload.get("qa_latest") or {})
    service_model = _revision_frame(payload, "service_model")
    top20 = _revision_frame(payload, "top20_fidcs")
    latest = pl.iloc[-1] if not pl.empty else pd.Series(dtype=object)
    mono = service_model[service_model["modelo_prestacao"].eq("Monoestrutura")]
    mono_share = float(mono.iloc[0]["share_pl"]) if not mono.empty else 0.0
    top20_share = float(pd.to_numeric(top20.get("market_share_ex_fic"), errors="coerce").sum())
    latest_competence = str(latest.get("competencia") or payload.get("latest_complete") or "")
    latest_label = _short_competence_label(latest_competence)
    latest_pl_ex_fic = float(latest.get("pl_ex_fic", 0.0))
    kpis = [
        _industry_kpi(
            "PL ex-FIC",
            _fmt_bi(float(latest.get("pl_ex_fic", 0.0)), 0),
            f"FIC-FIDC adiciona {_fmt_bi(float(latest.get('pl_fic_componente', 0.0)), 0)}",
        ),
        _industry_kpi(
            "Top 20 FIDCs",
            _fmt_pct(top20_share),
            "do PL ex-FIC",
        ),
        _industry_kpi(
            "Casos acima da carteira",
            _fmt_int(qa.get("casos_inad_supera_carteira", 0)),
            f"{_fmt_pct(float(qa.get('casos_inad_supera_carteira_share_pl', 0)))} do PL",
        ),
        _industry_kpi(
            "Monoestruturas",
            _fmt_pct(mono_share),
            "do PL bruto dos fundos",
        ),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(kpis)}</div>', unsafe_allow_html=True)

    st.markdown("<h2>Evolução do PL</h2>", unsafe_allow_html=True)
    if not pl.empty:
        pl = pl.copy()
        pl["Período"] = pl.apply(
            lambda row: _short_competence_label(row["competencia"])
            if str(row["competencia"]) == latest_competence
            else str(int(row["year"])),
            axis=1,
        )
        order = pl["Período"].tolist()
        long = pd.concat(
            [
                pl.assign(Série="PL ex-FIC", valor_bi=pl["pl_ex_fic"] / 1e9),
                pl.assign(Série="FIC-FIDC", valor_bi=pl["pl_fic_componente"] / 1e9),
            ],
            ignore_index=True,
        )
        bars = (
            alt.Chart(long)
            .mark_bar()
            .encode(
                x=alt.X("Período:N", title=None, sort=order, axis=alt.Axis(labelAngle=0, grid=False)),
                y=alt.Y("sum(valor_bi):Q", title="R$ bi", stack="zero", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                color=alt.Color(
                    "Série:N",
                    scale=alt.Scale(domain=["PL ex-FIC", "FIC-FIDC"], range=[_ORANGE, _GRAY_LIGHT]),
                    legend=alt.Legend(title=None, orient="bottom"),
                ),
                order=alt.Order("Série:N", sort="ascending"),
                tooltip=[
                    alt.Tooltip("Período:N"),
                    alt.Tooltip("Série:N"),
                    alt.Tooltip("valor_bi:Q", title="PL (R$ bi)", format=",.1f"),
                ],
            )
        )
        labels = (
            alt.Chart(pl.assign(total_bi=pl["pl_total"] / 1e9))
            .mark_text(dy=-8, color=_BLACK, fontSize=11)
            .encode(
                x=alt.X("Período:N", sort=order),
                y=alt.Y("total_bi:Q"),
                text=alt.Text("total_bi:Q", format=",.0f"),
            )
        )
        st.altair_chart((bars + labels).properties(height=360), width="stretch", key="industry-revision-pl")
        if not pl_cagr_periods.empty:
            cagr_parts = [
                f"{int(row.start_year)}–{int(row.end_year)}: {_fmt_pct(float(row.cagr))} a.a."
                for row in pl_cagr_periods.itertuples(index=False)
            ]
            st.caption("CAGR do PL bruto · " + " · ".join(cagr_parts))
        st.caption(
            "Fonte: CVM, Informe Mensal de FIDC. PL bruto = PL ex-FIC + PL dos FIC-FIDCs; "
            "os dois componentes não se sobrepõem. CAGRs calculados dezembro contra dezembro, "
            f"com o número de intervalos igual à diferença entre os anos. Data-base: {latest_label.lower()}."
        )

    st.markdown(
        "<h2>Classificação ANBIMA · evolução do PL ex-FIC</h2>",
        unsafe_allow_html=True,
    )
    mix = _revision_history_frame(payload, "type_mix_history", fallback_key="type_mix")
    mix_meta = dict(payload.get("type_mix_meta") or {})
    if not mix.empty:
        if "period_order" not in mix:
            period_map = {
                period: index
                for index, period in enumerate(
                    sorted(mix["competencia"].astype(str).unique())
                )
            }
            mix["period_order"] = mix["competencia"].astype(str).map(period_map)
        if "period_label" not in mix:
            mix["period_label"] = mix["Período"].astype(str).str.lower()
        if "category_order" not in mix:
            mix["category_order"] = mix["anbima_tipo"].map(
                {
                    "Fomento Mercantil": 0,
                    "Agro, Indústria e Comércio": 1,
                    "Financeiro": 2,
                    "Outros": 3,
                    "N/D": 4,
                }
            )
        mix = mix.sort_values(["period_order", "category_order"]).copy()
        mix["pl"] = pd.to_numeric(mix["pl"], errors="coerce").fillna(0.0)
        mix["share"] = pd.to_numeric(mix["share"], errors="coerce").fillna(0.0)
        mix["volume_bi"] = mix["pl"] / 1e9
        mix["volume_start"] = (
            mix.groupby("competencia")["volume_bi"].cumsum() - mix["volume_bi"]
        )
        mix["volume_end"] = mix["volume_start"] + mix["volume_bi"]
        mix["volume_mid"] = (mix["volume_start"] + mix["volume_end"]) / 2
        mix["share_start"] = (
            mix.groupby("competencia")["share"].cumsum() - mix["share"]
        )
        mix["share_end"] = mix["share_start"] + mix["share"]
        mix["share_mid"] = (mix["share_start"] + mix["share_end"]) / 2
        period_order = (
            mix.sort_values("period_order")["period_label"].drop_duplicates().tolist()
        )
        category_order = list(
            mix_meta.get("categories")
            or [
                "Fomento Mercantil",
                "Agro, Indústria e Comércio",
                "Financeiro",
                "Outros",
            ]
        )
        category_colors = ["#73787D", _GRAY, _ORANGE, _GRAY_LIGHT]
        color = alt.Color(
            "anbima_tipo:N",
            title=None,
            sort=category_order,
            scale=alt.Scale(domain=category_order, range=category_colors),
            legend=alt.Legend(orient="bottom", columns=2),
        )
        x = alt.X(
            "period_label:N",
            title=None,
            sort=period_order,
            axis=alt.Axis(labelAngle=0, grid=False),
        )
        tooltip = [
            alt.Tooltip("period_label:N", title="Competência"),
            alt.Tooltip("anbima_tipo:N", title="Tipo ANBIMA"),
            alt.Tooltip("volume_bi:Q", title="PL ex-FIC (R$ bi)", format=",.1f"),
            alt.Tooltip("share:Q", title="Participação", format=".1%"),
        ]
        label_color = alt.condition(
            alt.datum.anbima_tipo == "Outros",
            alt.value(_BLACK),
            alt.value("#FFFFFF"),
        )
        visible_label = alt.condition(alt.datum.pl > 0, alt.value(1), alt.value(0))

        volume_bars = (
            alt.Chart(mix)
            .mark_bar()
            .encode(
                x=x,
                y=alt.Y(
                    "volume_end:Q",
                    title="R$ bi",
                    axis=alt.Axis(gridColor=_GRAY_LIGHT),
                ),
                y2="volume_start:Q",
                color=color,
                tooltip=tooltip,
            )
        )
        volume_labels = (
            alt.Chart(mix)
            .mark_text(fontSize=10, fontWeight=600)
            .encode(
                x=x,
                y=alt.Y("volume_mid:Q"),
                text=alt.Text("volume_bi:Q", format=",.1f"),
                color=label_color,
                opacity=visible_label,
            )
        )
        share_bars = (
            alt.Chart(mix)
            .mark_bar()
            .encode(
                x=x,
                y=alt.Y(
                    "share_end:Q",
                    title="% do PL ex-FIC",
                    scale=alt.Scale(domain=[0, 1]),
                    axis=alt.Axis(format=".0%", gridColor=_GRAY_LIGHT),
                ),
                y2="share_start:Q",
                color=color,
                tooltip=tooltip,
            )
        )
        share_labels = (
            alt.Chart(mix)
            .mark_text(fontSize=10, fontWeight=600)
            .encode(
                x=x,
                y=alt.Y("share_mid:Q"),
                text=alt.Text("share:Q", format=".1%"),
                color=label_color,
                opacity=visible_label,
            )
        )
        left, right = st.columns(2)
        with left:
            st.markdown("**PL ex-FIC · R$ bilhões**")
            st.altair_chart(
                (volume_bars + volume_labels).properties(height=340),
                width="stretch",
                key="industry-revision-type-mix-volume",
            )
        with right:
            st.markdown("**Participação no PL ex-FIC**")
            st.altair_chart(
                (share_bars + share_labels).properties(height=340),
                width="stretch",
                key="industry-revision-type-mix-share",
            )
        st.caption(
            str(mix_meta.get("classification_method") or "")
            + " N/D foi incorporado em Outros somente nesta visualização. "
            + "Tipo e Foco ANBIMA permanecem campos distintos."
        )

    acquiring_mix = _revision_history_frame(
        payload,
        "acquiring_reclassified_mix",
    )
    if not acquiring_mix.empty:
        st.markdown(
            "<h2>Taxonomia CVM com abertura analítica de adquirência</h2>",
            unsafe_allow_html=True,
        )
        acquiring_mix["PL (R$ bi)"] = pd.to_numeric(
            acquiring_mix["pl_brl"], errors="coerce"
        ).fillna(0.0) / 1e9
        acquiring_mix["share_pl"] = pd.to_numeric(
            acquiring_mix["share_pl"], errors="coerce"
        ).fillna(0.0)
        period_order, _period_colors = _revision_period_encoding(acquiring_mix)
        latest_period = acquiring_mix["competencia"].max()
        category_order = (
            acquiring_mix[acquiring_mix["competencia"].eq(latest_period)]
            .sort_values("PL (R$ bi)", ascending=False)["categoria_analitica"]
            .astype(str)
            .tolist()
        )
        left, right = st.columns(2)
        with left:
            chart = (
                alt.Chart(acquiring_mix)
                .mark_bar(cornerRadiusEnd=2)
                .encode(
                    x=alt.X("PL (R$ bi):Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    y=alt.Y("categoria_analitica:N", title=None, sort=category_order),
                    yOffset=alt.YOffset("Período:N", sort=period_order),
                    color=_revision_comparison_color(acquiring_mix),
                    tooltip=[
                        "Período:N",
                        "categoria_analitica:N",
                        alt.Tooltip("PL (R$ bi):Q", format=",.1f"),
                        alt.Tooltip("share_pl:Q", format=".1%"),
                    ],
                )
                .properties(height=410, title="PL reclassificado")
            )
            labels = (
                alt.Chart(acquiring_mix)
                .mark_text(align="left", baseline="middle", dx=4, color=_BLACK, fontSize=9)
                .encode(
                    x=alt.X("PL (R$ bi):Q"),
                    y=alt.Y("categoria_analitica:N", sort=category_order),
                    yOffset=alt.YOffset("Período:N", sort=period_order),
                    text=alt.Text("PL (R$ bi):Q", format=".1f"),
                )
            )
            st.altair_chart(chart + labels, width="stretch", key="industry-revision-acquiring-pl")
        with right:
            chart = (
                alt.Chart(acquiring_mix)
                .mark_bar(cornerRadiusEnd=2)
                .encode(
                    x=alt.X("share_pl:Q", title="% do PL ex-FIC", axis=alt.Axis(format="%", gridColor=_GRAY_LIGHT)),
                    y=alt.Y("categoria_analitica:N", title=None, sort=category_order, axis=None),
                    yOffset=alt.YOffset("Período:N", sort=period_order),
                    color=_revision_comparison_color(acquiring_mix, show_legend=False),
                    tooltip=[
                        "Período:N",
                        "categoria_analitica:N",
                        alt.Tooltip("share_pl:Q", format=".1%"),
                        alt.Tooltip("PL (R$ bi):Q", format=",.1f"),
                    ],
                )
                .properties(height=410, title="Participação no PL ex-FIC")
            )
            labels = (
                alt.Chart(acquiring_mix)
                .mark_text(align="left", baseline="middle", dx=4, color=_BLACK, fontSize=9)
                .encode(
                    x=alt.X("share_pl:Q"),
                    y=alt.Y("categoria_analitica:N", sort=category_order),
                    yOffset=alt.YOffset("Período:N", sort=period_order),
                    text=alt.Text("share_pl:Q", format=".1%"),
                )
            )
            st.altair_chart(chart + labels, width="stretch", key="industry-revision-acquiring-share")
        current_acquiring = acquiring_mix[
            acquiring_mix["competencia"].eq(latest_period)
            & acquiring_mix["categoria_analitica"].eq("Adquirência")
        ]
        if not current_acquiring.empty:
            row = current_acquiring.iloc[0]
            curated_count = int(row.get("fundos_adquirencia_curados", 0))
            observed_count = int(row.get("fundos_adquirencia_observados", 0))
            missing_count = max(0, curated_count - observed_count)
            current_rows = acquiring_mix[acquiring_mix["competencia"].eq(latest_period)]
            moved_by_category = (
                current_rows.set_index("categoria_analitica")[
                    "fundos_movidos_da_categoria"
                ].to_dict()
                if "fundos_movidos_da_categoria" in current_rows
                else {}
            )
            st.caption(
                f"Adquirência: {curated_count} CNPJs, {_fmt_bi(float(row['pl_brl']), 1)} e "
                f"{_fmt_pct(float(row['share_pl']))} do PL ex-FIC. Origem CVM dos ativos: "
                f"{int(moved_by_category.get('Cartão', 0))} Cartão, "
                f"{int(moved_by_category.get('Comercial', 0))} Comercial, "
                f"{int(moved_by_category.get('Serviços', 0))} Serviços e "
                f"{int(moved_by_category.get('Financeiro', 0))} Financeiro; "
                f"{missing_count} sem reporte ativo. A classificação original permanece na base."
            )
        st.caption(
            "Fonte: CVM, Informe Mensal e documentos primários. Reclassificação documental em "
            "21/jul/26; categoria original e denominador PL ex-FIC preservados."
        )

    with st.expander("Origem da classificação", expanded=False):
        coverage = _revision_frame(payload, "classification_coverage")
        if not coverage.empty:
            display = coverage[["categoria", "pl", "share"]].copy()
            display.columns = ["Origem", "PL", "Cobertura"]
            display["PL"] = display["PL"].map(lambda value: _fmt_bi(value, 1))
            display["Cobertura"] = display["Cobertura"].map(_fmt_pct)
            st.dataframe(display, hide_index=True, width="stretch")
        st.caption(
            "Tipo e Foco ANBIMA permanecem separados. "
            + str(dict(payload.get("sources") or {}).get("anbima") or "A origem da classificação permanece identificada por fundo.")
            + "."
        )


def _render_revision_card_breakdown(payload: dict[str, object]) -> None:
    stock_competence = str(payload.get("latest_complete") or "")
    stock_label_lower = _short_competence_label(stock_competence).lower()
    card_audit = _revision_frame(payload, "card_taxonomy_audit")
    card_summary = dict(payload.get("card_taxonomy_summary") or {})
    if card_audit.empty:
        st.info("A curadoria do bucket Cartão de crédito não está disponível no payload publicado.")
        return
    st.markdown(
        "<h2>Cartão de crédito: lista completa e decisão de curadoria</h2>",
        unsafe_allow_html=True,
    )
    total_card = int(card_summary.get("fundos_total", len(card_audit)))
    audit_cards = [
        _industry_kpi(
            "Em Adquirência",
            _fmt_int(card_summary.get("fundos_incluidos_adquirencia", 0)),
            _fmt_bi(float(card_summary.get("pl_incluido_adquirencia_brl", 0)), 1),
        ),
        _industry_kpi(
            "Fora de Adquirência",
            _fmt_int(card_summary.get("fundos_fora_adquirencia", 0)),
            _fmt_bi(float(card_summary.get("pl_fora_adquirencia_brl", 0)), 1),
        ),
        _industry_kpi(
            "Pendentes",
            _fmt_int(card_summary.get("fundos_pendentes_curadoria", 0)),
            _fmt_bi(float(card_summary.get("pl_pendente_curadoria_brl", 0)), 1),
        ),
        _industry_kpi(
            f"PL em {stock_label_lower}",
            f"{_fmt_int(card_summary.get('fundos_pl_atual_observavel', 0))}/{_fmt_int(total_card)}",
            f"fallback mai/26: {_fmt_int(card_summary.get('fundos_pl_fallback_usado', 0))}",
        ),
    ]
    st.markdown(
        f'<div class="industry-kpi-grid">{"".join(audit_cards)}</div>',
        unsafe_allow_html=True,
    )
    display = card_audit.copy()
    display["PL de referência"] = pd.to_numeric(
        display["pl_referencia_brl"], errors="coerce"
    ).map(lambda value: _fmt_bi(float(value), 2) if pd.notna(value) else "N/D")
    display["Período PL"] = display["pl_referencia_competencia"].map(
        _short_competence_label
    )
    visible_columns = [
        "ordem_materialidade",
        "cnpj_fundo_formatado",
        "denominacao",
        "PL de referência",
        "Período PL",
        "status_curadoria",
        "cedente_originador",
        "devedor_sacado",
        "instrumento",
        "natureza_economica",
        "evidencia_curta",
        "fonte_url",
    ]
    visible = display[visible_columns].rename(
        columns={
            "ordem_materialidade": "#",
            "cnpj_fundo_formatado": "CNPJ",
            "denominacao": "Fundo",
            "status_curadoria": "Decisão",
            "cedente_originador": "Cedente / originador",
            "devedor_sacado": "Devedor / sacado",
            "instrumento": "Instrumento",
            "natureza_economica": "Natureza econômica",
            "evidencia_curta": "Evidência",
            "fonte_url": "Fonte",
        }
    )
    st.dataframe(
        visible,
        hide_index=True,
        width="stretch",
        height=620,
        column_config={
            "Fonte": st.column_config.LinkColumn(
                "Fonte", display_text="Documento primário"
            )
        },
    )
    st.download_button(
        "Baixar curadoria em CSV",
        data=visible.to_csv(index=False).encode("utf-8-sig"),
        file_name="fidcs_cartao_credito_curadoria_202606.csv",
        mime="text/csv",
        key="industry-revision-card-taxonomy-download",
    )
    st.caption(
        "Critério: transações do arranjo e da cadeia de pagamentos entram em Adquirência; "
        "crédito a PF/PJ ou CCB permanece fora. Fonte principal: regulamento vigente no FundosNet. "
        "A categoria reportada na Tabela II continua preservada."
    )

def _render_revision_investors(payload: dict[str, object]) -> None:
    stock_competence = str(payload.get("latest_complete") or "")
    stock_label = _short_competence_label(stock_competence)
    stock_label_lower = stock_label.lower()
    history = _revision_frame(payload, "investor_base_history")
    composition = _revision_frame(payload, "investor_composition")
    holders = _revision_holder_distribution_frame(
        _revision_history_frame(payload, "holder_distribution_history", fallback_key="holder_distribution")
    )
    holder_meta = _revision_history_frame(payload, "holder_distribution_meta_history")
    st.markdown("<h2>Contas e veículos reportantes</h2>", unsafe_allow_html=True)
    st.markdown(
        '<div class="industry-def">Contas são observações por classe ou série. A base pública não permite tratá-las como investidores únicos ou CPFs.</div>',
        unsafe_allow_html=True,
    )
    if not history.empty:
        history = history.copy()
        latest_competence = str(payload.get("latest_complete") or history.iloc[-1].get("competencia") or "")
        history["Período"] = history.apply(
            lambda row: _short_competence_label(row["competencia"])
            if str(row["competencia"]) == latest_competence
            else str(int(row["year"])),
            axis=1,
        )
        order = history["Período"].tolist()
        left, right = st.columns(2)
        with left:
            accounts = history.assign(contas_mil=history["cotistas_total"] / 1000)
            chart = (
                alt.Chart(accounts)
                .mark_line(color=_ORANGE, strokeWidth=2.7)
                .encode(
                    x=alt.X("Período:N", title=None, sort=order),
                    y=alt.Y("contas_mil:Q", title="mil contas", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    tooltip=["Período:N", alt.Tooltip("contas_mil:Q", format=",.1f")],
                )
                .properties(height=260, title="Evolução das contas")
            )
            labels = (
                alt.Chart(accounts[accounts["Período"].eq(order[-1])])
                .mark_text(align="left", dx=6, color=_ORANGE, fontSize=10, fontWeight=700)
                .encode(
                    x=alt.X("Período:N", sort=order),
                    y=alt.Y("contas_mil:Q"),
                    text=alt.Text("contas_mil:Q", format=",.1f"),
                )
            )
            st.altair_chart(chart + labels, width="stretch", key="industry-revision-accounts")
        with right:
            chart = (
                alt.Chart(history)
                .mark_line(color=_BLACK, strokeWidth=2.4)
                .encode(
                    x=alt.X("Período:N", title=None, sort=order),
                    y=alt.Y("n_veiculos:Q", title="veículos", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    tooltip=["Período:N", alt.Tooltip("n_veiculos:Q", format=",.0f")],
                )
                .properties(height=260, title="Veículos reportantes")
            )
            labels = (
                alt.Chart(history[history["Período"].eq(order[-1])])
                .mark_text(align="left", dx=6, color=_BLACK, fontSize=10, fontWeight=700)
                .encode(
                    x=alt.X("Período:N", sort=order),
                    y=alt.Y("n_veiculos:Q"),
                    text=alt.Text("n_veiculos:Q", format=",.0f"),
                )
            )
            st.altair_chart(chart + labels, width="stretch", key="industry-revision-vehicles")
    st.markdown("<h2>Composição das contas</h2>", unsafe_allow_html=True)
    if not composition.empty:
        composition = composition.sort_values("contas", ascending=False).copy()
        chart = (
            alt.Chart(composition)
            .mark_bar(cornerRadiusEnd=2)
            .encode(
                x=alt.X("share:Q", title="participação", axis=alt.Axis(format="%", gridColor=_GRAY_LIGHT)),
                y=alt.Y("categoria:N", title=None, sort="-x"),
                color=alt.condition(alt.datum.categoria == "Fundos", alt.value(_ORANGE), alt.value(_BLACK)),
                tooltip=["categoria:N", alt.Tooltip("contas:Q", format=",.0f"), alt.Tooltip("share:Q", format=".1%")],
            )
            .properties(height=260)
        )
        labels = (
            alt.Chart(composition)
            .mark_text(align="left", baseline="middle", dx=4, color=_BLACK, fontSize=10)
            .encode(
                x=alt.X("share:Q"),
                y=alt.Y("categoria:N", sort="-x"),
                text=alt.Text("share:Q", format=".1%"),
            )
        )
        st.altair_chart(chart + labels, width="stretch", key="industry-revision-investor-composition")
        total_accounts = int(pd.to_numeric(composition["contas"], errors="coerce").fillna(0).sum())
        unidentified_accounts = int(
            pd.to_numeric(
                composition.loc[
                    composition["categoria"].astype(str).str.casefold().isin(
                        {"não classificado", "não identificado", "nao identificado", "n/d"}
                    ),
                    "contas",
                ],
                errors="coerce",
            ).fillna(0).sum()
        )
        st.caption(
            f"Fonte: CVM, Informe Mensal de FIDC, {stock_label_lower}. "
            f"Total: {_fmt_int(total_accounts)} contas; "
            f"{_fmt_int(unidentified_accounts)} sem tipo identificado."
        )

    st.markdown(
        f"<h2>Distribuição por número de contas: dez/23 e {stock_label_lower}</h2>",
        unsafe_allow_html=True,
    )
    if not holders.empty:
        order = holders["bucket"].astype(str).drop_duplicates().tolist()
        period_order, _period_colors = _revision_period_encoding(holders)
        above_ten = (
            holders[~holders["bucket"].astype(str).isin({"0", "1", "2–3", "4–10", "6–10"})]
            .groupby("competencia", as_index=False)[["share_fundos", "share_pl"]]
            .sum()
            .sort_values("competencia")
        )
        if len(above_ten) >= 2:
            first_above_ten = above_ten.iloc[0]
            latest_above_ten = above_ten.iloc[-1]
            fund_delta_pp = (
                float(latest_above_ten["share_fundos"])
                - float(first_above_ten["share_fundos"])
            ) * 100
            pl_delta_pp = (
                float(latest_above_ten["share_pl"])
                - float(first_above_ten["share_pl"])
            ) * 100
            fund_delta_label = f"{fund_delta_pp:.1f}".replace(".", ",")
            pl_delta_label = f"{pl_delta_pp:.1f}".replace(".", ",")
            _industry_headline(
                "Fundos com mais de 10 contas ganharam "
                f"{fund_delta_label} p.p. do universo e {pl_delta_label} p.p. do PL desde dez/23."
            )
        fund_share_ceiling = max(float(holders["share_fundos"].max()) * 1.15, 0.01)
        pl_share_ceiling = max(float(holders["share_pl"].max()) * 1.15, 0.01)
        left, right = st.columns(2)
        with left:
            chart = (
                alt.Chart(holders)
                .mark_bar()
                .encode(
                    x=alt.X("bucket:N", title="contas", sort=order),
                    xOffset=alt.XOffset("Período:N", sort=period_order),
                    y=alt.Y("fundos:Q", title="fundos", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    color=_revision_comparison_color(holders),
                    tooltip=[
                        "Período:N",
                        "bucket:N",
                        alt.Tooltip("fundos:Q", format=",.0f"),
                        alt.Tooltip("share_fundos:Q", format=".1%"),
                    ],
                )
                .properties(height=260, title="Quantidade de fundos por faixa")
            )
            labels = (
                alt.Chart(holders)
                .mark_text(dy=-5, color=_BLACK, fontSize=8)
                .encode(
                    x=alt.X("bucket:N", sort=order),
                    xOffset=alt.XOffset("Período:N", sort=period_order),
                    y=alt.Y("fundos:Q"),
                    text=alt.Text("fundos:Q", format=",.0f"),
                )
            )
            st.altair_chart(chart + labels, width="stretch", key="industry-revision-holder-funds-history")
        with right:
            holders_pl = holders.assign(pl_bi=holders["pl"] / 1e9)
            chart = (
                alt.Chart(holders_pl)
                .mark_bar()
                .encode(
                    x=alt.X("bucket:N", title="contas", sort=order),
                    xOffset=alt.XOffset("Período:N", sort=period_order),
                    y=alt.Y("pl_bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    color=_revision_comparison_color(holders, show_legend=False),
                    tooltip=[
                        "Período:N",
                        "bucket:N",
                        alt.Tooltip("pl_bi:Q", format=",.1f"),
                        alt.Tooltip("share_pl:Q", format=".1%"),
                    ],
                )
                .properties(height=260, title="PL por faixa")
            )
            labels = (
                alt.Chart(holders_pl)
                .mark_text(dy=-5, color=_BLACK, fontSize=8)
                .encode(
                    x=alt.X("bucket:N", sort=order),
                    xOffset=alt.XOffset("Período:N", sort=period_order),
                    y=alt.Y("pl_bi:Q"),
                    text=alt.Text("pl_bi:Q", format=".1f"),
                )
            )
            st.altair_chart(chart + labels, width="stretch", key="industry-revision-holder-pl-history")

        left, right = st.columns(2)
        with left:
            chart = (
                alt.Chart(holders)
                .mark_bar()
                .encode(
                    x=alt.X("bucket:N", title="contas", sort=order),
                    xOffset=alt.XOffset("Período:N", sort=period_order),
                    y=alt.Y(
                        "share_fundos:Q",
                        title="% dos fundos",
                        axis=alt.Axis(format=".0%", gridColor=_GRAY_LIGHT),
                        scale=alt.Scale(domain=[0, fund_share_ceiling]),
                    ),
                    color=_revision_comparison_color(holders, show_legend=False),
                    tooltip=[
                        "Período:N",
                        "bucket:N",
                        alt.Tooltip("fundos:Q", title="Fundos", format=",.0f"),
                        alt.Tooltip("share_fundos:Q", title="% do total", format=".2%"),
                    ],
                )
            )
            labels = (
                alt.Chart(holders)
                .mark_text(dy=-5, color=_BLACK, fontSize=8)
                .encode(
                    x=alt.X("bucket:N", sort=order),
                    xOffset=alt.XOffset("Período:N", sort=period_order),
                    y=alt.Y("share_fundos:Q"),
                    text=alt.Text("share_fundos:Q", format=".1%"),
                )
            )
            st.altair_chart(
                (chart + labels).properties(height=260, title="Fundos por faixa: % do total"),
                width="stretch",
                key="industry-revision-holder-funds-share-history",
            )
        with right:
            chart = (
                alt.Chart(holders)
                .mark_bar()
                .encode(
                    x=alt.X("bucket:N", title="contas", sort=order),
                    xOffset=alt.XOffset("Período:N", sort=period_order),
                    y=alt.Y(
                        "share_pl:Q",
                        title="% do PL",
                        axis=alt.Axis(format=".0%", gridColor=_GRAY_LIGHT),
                        scale=alt.Scale(domain=[0, pl_share_ceiling]),
                    ),
                    color=_revision_comparison_color(holders, show_legend=False),
                    tooltip=[
                        "Período:N",
                        "bucket:N",
                        alt.Tooltip("pl:Q", title="PL (R$)", format=",.0f"),
                        alt.Tooltip("share_pl:Q", title="% do total", format=".2%"),
                    ],
                )
            )
            labels = (
                alt.Chart(holders)
                .mark_text(dy=-5, color=_BLACK, fontSize=8)
                .encode(
                    x=alt.X("bucket:N", sort=order),
                    xOffset=alt.XOffset("Período:N", sort=period_order),
                    y=alt.Y("share_pl:Q"),
                    text=alt.Text("share_pl:Q", format=".1%"),
                )
            )
            st.altair_chart(
                (chart + labels).properties(height=260, title="PL por faixa: % do total"),
                width="stretch",
                key="industry-revision-holder-pl-share-history",
            )
        minimum = (
            float(pd.to_numeric(holder_meta["minimum_pl_brl"], errors="coerce").dropna().iloc[0])
            if not holder_meta.empty
            else 200_000_000
        )
        coverage = []
        if not holder_meta.empty:
            for _, row in holder_meta.sort_values("competencia").iterrows():
                coverage.append(
                    f"{row['Período']}: {_fmt_pct(float(row['fund_coverage']))} dos fundos e "
                    f"{_fmt_pct(float(row['pl_coverage']))} do PL ex-FIC"
                )
        eligible_counts = (
            holder_meta.sort_values("competencia")["eligible_funds"]
            .map(_fmt_int)
            .tolist()
            if not holder_meta.empty and "eligible_funds" in holder_meta
            else []
        )
        count_bridge = (
            f"{eligible_counts[0]} → {eligible_counts[-1]} fundos; "
            if len(eligible_counts) >= 2
            else ""
        )
        st.caption(
            f"Fonte: CVM, dez/23 e {stock_label_lower}. "
            f"Ex-FIC com PL ≥ R$ {_fmt_int(minimum / 1e6)} mi; "
            + count_bridge
            + ("cobertura: " + "; ".join(coverage) + ". " if coverage else "")
            + "Percentuais fecham em 100% por período; sem coorte fixa."
        )


def _render_revision_credit(payload: dict[str, object]) -> None:
    stock_competence = str(payload.get("latest_complete") or "")
    stock_label = _short_competence_label(stock_competence)
    stock_label_lower = stock_label.lower()
    qa = dict(payload.get("qa_latest") or {})
    portfolio_tab, observability_tab, history_tab, series_break_tab = st.tabs(
        ["Carteira", "Observabilidade", "Histórico por tipo", "Quebra de série"]
    )
    with portfolio_tab:
        rows = _revision_history_frame(payload, "receivables_history")
        receivables_meta = _revision_history_frame(payload, "receivables_meta_history")
        st.markdown(
            f"<h2>Carteira por tipo de recebível: dez/23 e {stock_label_lower}</h2>",
            unsafe_allow_html=True,
        )
        if not rows.empty:
            rows["valor"] = pd.to_numeric(rows["valor"], errors="coerce").fillna(0.0)
            rows = rows[rows["valor"].gt(0)].copy()
            rows["share_reported"] = rows.groupby("competencia")["valor"].transform(
                lambda values: values / values.sum() if float(values.sum()) > 0 else 0.0
            )
            rows["R$ bi"] = rows["valor"] / 1e9
            period_order, _period_colors = _revision_period_encoding(rows)
            latest_period = rows["competencia"].max()
            segment_order = (
                rows[rows["competencia"].eq(latest_period)]
                .sort_values("valor", ascending=False)["segmento"]
                .astype(str)
                .head(10)
                .tolist()
            )
            visible = rows[rows["segmento"].isin(segment_order)].copy()
            left, right = st.columns(2)
            with left:
                chart = (
                    alt.Chart(visible)
                    .mark_bar(cornerRadiusEnd=2)
                    .encode(
                        x=alt.X("R$ bi:Q", title="R$ bi", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                        y=alt.Y("segmento:N", title=None, sort=segment_order),
                        yOffset=alt.YOffset("Período:N", sort=period_order),
                        color=_revision_comparison_color(visible),
                        tooltip=["Período:N", "segmento:N", alt.Tooltip("R$ bi:Q", format=",.1f")],
                    )
                    .properties(height=390, title="Volume reportado")
                )
                st.altair_chart(chart, width="stretch", key="industry-revision-receivables-pl-history")
            with right:
                chart = (
                    alt.Chart(visible)
                    .mark_bar(cornerRadiusEnd=2)
                    .encode(
                        x=alt.X(
                            "share_reported:Q",
                            title="% da abertura reportada",
                            axis=alt.Axis(format="%", gridColor=_GRAY_LIGHT),
                        ),
                        y=alt.Y("segmento:N", title=None, sort=segment_order, axis=None),
                        yOffset=alt.YOffset("Período:N", sort=period_order),
                        color=_revision_comparison_color(visible, show_legend=False),
                        tooltip=[
                            "Período:N",
                            "segmento:N",
                            alt.Tooltip("share_reported:Q", title="% do total reportado", format=".1%"),
                            alt.Tooltip("R$ bi:Q", format=",.1f"),
                        ],
                    )
                    .properties(height=390, title="Participação no total reportado")
                )
                st.altair_chart(chart, width="stretch", key="industry-revision-receivables-share-history")
            gaps = []
            if not receivables_meta.empty:
                for _, row in receivables_meta.sort_values("competencia").iterrows():
                    gaps.append(
                        f"{row['Período']}: {_fmt_bi(float(row['reported_total']), 1)}; "
                        f"diferença para a Tabela I de {_fmt_bi(float(row['gap']), 1)} "
                        f"({_fmt_pct(float(row['gap_pct']))})"
                    )
            denominator_note = (
                "Base dos percentuais: soma dos segmentos da Tabela II, fechando 100%. "
                + ("; ".join(gaps) + "." if gaps else "")
            )
            st.caption(denominator_note.replace("$", r"\$"))
            acquiring = dict(payload.get("acquiring_taxonomy") or {})
            acquiring_summary = dict(acquiring.get("summary") or {})
            if acquiring_summary:
                acquiring_mix = pd.DataFrame(payload.get("acquiring_reclassified_mix") or [])
                latest_acquiring = (
                    acquiring_mix[
                        acquiring_mix.get("competencia", pd.Series(dtype=str))
                        .astype(str)
                        .eq(str(payload.get("latest_complete") or ""))
                    ]
                    if not acquiring_mix.empty and "competencia" in acquiring_mix.columns
                    else pd.DataFrame()
                )
                commercial_value = 0.0
                financial_value = 0.0
                if not latest_acquiring.empty and "categoria_cvm" in latest_acquiring.columns:
                    commercial_value = float(
                        pd.to_numeric(
                            latest_acquiring.loc[
                                latest_acquiring["categoria_cvm"].eq("Comercial"),
                                "pl_movido_da_categoria_brl",
                            ],
                            errors="coerce",
                        ).sum()
                    )
                    financial_value = float(
                        pd.to_numeric(
                            latest_acquiring.loc[
                                latest_acquiring["categoria_cvm"].eq("Financeiro"),
                                "pl_movido_da_categoria_brl",
                            ],
                            errors="coerce",
                        ).sum()
                    )
                taxonomy_note = (
                    "Regra CVM: os campos são mutuamente excludentes e prevalece o mais específico; "
                    f"adquirência com cartão pertence a II.g. Em {stock_label_lower}, A.I. e PI reportaram "
                    f"{_fmt_bi(commercial_value, 2)} em Comercial; Akira I, "
                    f"{_fmt_bi(financial_value, 2)} em Financeiro. O painel mantém o campo declarado."
                )
                st.caption(taxonomy_note.replace("$", r"\$"))
            st.caption(
                f"Fonte: CVM, Informe Mensal de FIDC, dez/23 e {stock_label_lower}. "
                "Tabela II e Tipo/Foco ANBIMA permanecem separados."
            )
    with observability_tab:
        st.markdown("<h2>Observabilidade da inadimplência</h2>", unsafe_allow_html=True)
        cards = [
            _industry_kpi("Veículos / fundos", f"{_fmt_int(qa.get('veiculos_total', 0))} / {_fmt_int(qa.get('fundos_total', 0))}", str(payload.get("latest_complete", ""))),
            _industry_kpi("Carteira positiva", _fmt_int(qa.get("veiculos_com_carteira_positiva", 0)), "veículos"),
            _industry_kpi("Campos reportados", _fmt_int(qa.get("veiculos_com_campos_reportados", 0)), f"{_fmt_pct(float(qa.get('cobertura_pl', 0)))} do PL"),
            _industry_kpi(
                "Acima da carteira",
                _fmt_int(qa.get("casos_inad_supera_carteira", 0)),
                f"{_fmt_pct(float(qa.get('casos_inad_supera_carteira_share_veiculos_total', 0)))} dos veículos; "
                f"{_fmt_pct(float(qa.get('casos_inad_supera_carteira_share_carteira_positiva', 0)))} com carteira positiva",
            ),
            _industry_kpi("Inad. bruta", _fmt_pct(float(qa.get("inadimplencia_bruta_pct", 0))), "sobre carteira coberta"),
            _industry_kpi("Inad. ajustada", _fmt_pct(float(qa.get("inadimplencia_ajustada_pct", 0))), f"ex-NP {_fmt_pct(float(qa.get('inadimplencia_ajustada_ex_np_pct', 0)))}"),
        ]
        st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
        st.caption(
            f"O ajuste remove {_fmt_bi(float(qa.get('excesso_removido_brl', 0)), 2)}. "
            f"Top 1/5/10 concentram {_fmt_pct(float(qa.get('excesso_top1_share', 0)))} / "
            f"{_fmt_pct(float(qa.get('excesso_top5_share', 0)))} / {_fmt_pct(float(qa.get('excesso_top10_share', 0)))} do valor removido. "
            f"Excluindo integralmente esses casos, a métrica seria {_fmt_pct(float(qa.get('sensibilidade_ex_casos_acima_carteira_pct', 0)))}."
        )

        single = _revision_frame(payload, "delinquency_single_receivable")
        single_summary = dict(payload.get("delinquency_single_receivable_summary") or {})
        if not single.empty:
            st.markdown(
                "<h2>Inadimplência em fundos com um único tipo de recebível</h2>",
                unsafe_allow_html=True,
            )
            single["PL incluído (R$ bi)"] = pd.to_numeric(
                single["pl_incluido_brl"], errors="coerce"
            ).fillna(0.0) / 1e9
            single["Inadimplência / PL"] = pd.to_numeric(
                single["inadimplencia_sobre_pl"], errors="coerce"
            ).fillna(0.0)
            chart = (
                alt.Chart(single)
                .mark_bar(cornerRadiusEnd=2)
                .encode(
                    x=alt.X(
                        "Inadimplência / PL:Q",
                        title="inadimplência reportada / PL",
                        axis=alt.Axis(format="%", gridColor=_GRAY_LIGHT),
                    ),
                    y=alt.Y(
                        "tipo_recebivel_tabela_ii:N",
                        title=None,
                        sort=alt.EncodingSortField(field="PL incluído (R$ bi)", order="descending"),
                    ),
                    color=alt.condition(
                        alt.datum.tipo_recebivel_tabela_ii == "Financeiro",
                        alt.value(_ORANGE),
                        alt.value(_BLACK),
                    ),
                    tooltip=[
                        alt.Tooltip("tipo_recebivel_tabela_ii:N", title="Tipo Tabela II"),
                        alt.Tooltip("fundos_incluidos:Q", title="Fundos", format=",.0f"),
                        alt.Tooltip("PL incluído (R$ bi):Q", format=",.1f"),
                        alt.Tooltip("Inadimplência / PL:Q", format=".2%"),
                    ],
                )
                .properties(height=390)
            )
            st.altair_chart(chart, width="stretch", key="industry-revision-delinquency-single-type")
            display = single[
                [
                    "tipo_recebivel_tabela_ii",
                    "fundos_incluidos",
                    "PL incluído (R$ bi)",
                    "Inadimplência / PL",
                ]
            ].copy()
            display.columns = ["Tipo Tabela II", "Fundos", "PL incluído (R$ bi)", "Inadimplência / PL"]
            st.dataframe(
                display.style.format(
                    {
                        "Fundos": "{:,.0f}",
                        "PL incluído (R$ bi)": "{:,.1f}",
                        "Inadimplência / PL": "{:.2%}",
                    }
                ),
                hide_index=True,
                width="stretch",
            )
            st.caption(
                f"Incluídos: {_fmt_int(single_summary.get('fundos_incluidos', 0))} fundos e "
                f"{_fmt_bi(float(single_summary.get('pl_incluido_brl', 0)), 1)}, equivalentes a "
                f"{_fmt_pct(float(single_summary.get('cobertura_pl', 0)))} do PL ex-FIC positivo. "
                f"Excluídos {_fmt_int(single_summary.get('fundos_multitipo_excluidos', 0))} fundos com mais de um tipo e "
                f"{_fmt_int(single_summary.get('fundos_inad_supera_carteira_excluidos', 0))} casos com inadimplência acima da carteira. "
                "O numerador é a inadimplência reportada e o denominador é o PL total dos fundos incluídos."
            )
    with history_tab:
        frozen = _revision_frame(payload, "delinquency_frozen_cohort_history")
        frozen_summary = _revision_frame(payload, "delinquency_frozen_cohort_summary")
        cohort_revision = dict(payload.get("delinquency_cohort_revision_summary") or {})
        cohort_transitions = _revision_frame(
            payload, "delinquency_cohort_revision_transitions"
        )
        cohort_sensitivity = _revision_frame(
            payload, "delinquency_cohort_revision_sensitivity"
        )
        if not frozen.empty and not frozen_summary.empty:
            st.markdown(
                f"<h2>Histórico por tipo na coorte classificada em {stock_label_lower}</h2>",
                unsafe_allow_html=True,
            )
            if cohort_revision:
                previous_label = _short_competence_label(
                    cohort_revision.get("competencia_anterior")
                ).lower()
                current_label = _short_competence_label(
                    cohort_revision.get("competencia_atual")
                ).lower()
                st.markdown(
                    '<div class="industry-note"><b>Revisão da série.</b> '
                    f"A coorte passou de {previous_label} para {current_label}: "
                    f"{_fmt_int(cohort_revision.get('fundos_reclassificados', 0))} fundos "
                    f"({_fmt_bi(float(cohort_revision.get('pl_atual_reclassificado_brl', 0)), 1)}), "
                    f"incluiu {_fmt_int(cohort_revision.get('fundos_entraram', 0))} e retirou "
                    f"{_fmt_int(cohort_revision.get('fundos_sairam', 0))}. O histórico usa o subtipo de {current_label}.</div>",
                    unsafe_allow_html=True,
                )
                if not cohort_transitions.empty or not cohort_sensitivity.empty:
                    with st.expander("Detalhes da revisão da coorte", expanded=False):
                        if not cohort_transitions.empty:
                            transitions = cohort_transitions.copy()
                            transitions["PL atual (R$ bi)"] = pd.to_numeric(
                                transitions["pl_atual_brl"], errors="coerce"
                            ) / 1e9
                            transitions = transitions.rename(
                                columns={
                                    "subtipo_anterior": "Subtipo anterior",
                                    "subtipo_atual": "Subtipo atual",
                                    "fundos": "Fundos",
                                }
                            )
                            st.dataframe(
                                transitions[
                                    [
                                        "Subtipo anterior",
                                        "Subtipo atual",
                                        "Fundos",
                                        "PL atual (R$ bi)",
                                    ]
                                ].style.format(
                                    {
                                        "Fundos": "{:,.0f}",
                                        "PL atual (R$ bi)": "{:,.1f}",
                                    }
                                ),
                                hide_index=True,
                                width="stretch",
                            )
                        if not cohort_sensitivity.empty:
                            sensitivity = cohort_sensitivity.copy()
                            sensitivity["Coorte anterior"] = pd.to_numeric(
                                sensitivity[
                                    "inadimplencia_sobre_carteira_coorte_anterior"
                                ],
                                errors="coerce",
                            )
                            sensitivity["Coorte atual"] = pd.to_numeric(
                                sensitivity[
                                    "inadimplencia_sobre_carteira_coorte_atual"
                                ],
                                errors="coerce",
                            )
                            sensitivity["Δ (p.p.)"] = (
                                pd.to_numeric(
                                    sensitivity["delta_inadimplencia_pp"],
                                    errors="coerce",
                                )
                                * 100
                            )
                            sensitivity["_abs_delta"] = sensitivity["Δ (p.p.)"].abs()
                            sensitivity = sensitivity.nlargest(10, "_abs_delta").rename(
                                columns={
                                    "competencia": "Competência",
                                    "tipo_recebivel_tabela_ii": "Tipo Tabela II",
                                }
                            )
                            st.markdown("**Maiores revisões da série histórica**")
                            st.dataframe(
                                sensitivity[
                                    [
                                        "Competência",
                                        "Tipo Tabela II",
                                        "Coorte anterior",
                                        "Coorte atual",
                                        "Δ (p.p.)",
                                    ]
                                ].style.format(
                                    {
                                        "Coorte anterior": "{:.2%}",
                                        "Coorte atual": "{:.2%}",
                                        "Δ (p.p.)": "{:+.2f}",
                                    }
                                ),
                                hide_index=True,
                                width="stretch",
                            )
            latest_complete = stock_competence
            frozen = frozen[
                frozen["competencia"].between("2023-12", latest_complete)
            ].copy()
            frozen_summary = frozen_summary[
                frozen_summary["competencia"].between("2023-12", latest_complete)
            ].copy()
            frozen["percentual"] = pd.to_numeric(
                frozen["inadimplencia_sobre_carteira"], errors="coerce"
            )
            frozen["Série"] = frozen["tipo_recebivel_tabela_ii"].astype(str)
            frozen = frozen[frozen["percentual"].notna()].copy()
            qa_adjusted = _revision_frame(payload, "qa_series")
            if not qa_adjusted.empty:
                qa_adjusted = qa_adjusted[
                    qa_adjusted["competencia"].between("2023-12", latest_complete)
                ].copy()
                qa_adjusted = qa_adjusted[
                    ["competencia", "inadimplencia_ajustada_pct"]
                ].rename(columns={"inadimplencia_ajustada_pct": "percentual"})
                qa_adjusted["Série"] = "Consolidado ajustado"
                historical = pd.concat(
                    [frozen[["competencia", "percentual", "Série"]], qa_adjusted],
                    ignore_index=True,
                )
            else:
                historical = frozen[["competencia", "percentual", "Série"]]
            subtype_order = (
                frozen[frozen["competencia"].eq(str(payload.get("latest_complete") or ""))]
                .sort_values("pl_incluido_brl", ascending=False)["Série"]
                .drop_duplicates()
                .tolist()
            )
            series_order = ["Consolidado ajustado", *subtype_order]
            gray_scale = [
                "#151515",
                "#30353A",
                "#50555A",
                "#686D72",
                "#73787D",
                "#858A8F",
                "#979CA1",
                "#A9AEB3",
                "#BBC0C5",
                "#CDD1D5",
            ]
            color_range = [_ORANGE, *gray_scale[: len(subtype_order)]]
            selection = alt.selection_point(fields=["Série"], bind="legend")
            chart = (
                alt.Chart(historical)
                .mark_line(strokeWidth=2.0)
                .encode(
                    x=alt.X(
                        "competencia:T",
                        title=None,
                        axis=alt.Axis(format="%b/%y", grid=False),
                    ),
                    y=alt.Y(
                        "percentual:Q",
                        title="inadimplência / carteira",
                        axis=alt.Axis(format=".0%", gridColor=_GRAY_LIGHT),
                    ),
                    color=alt.Color(
                        "Série:N",
                        scale=alt.Scale(domain=series_order, range=color_range),
                        legend=alt.Legend(title=None, orient="bottom", columns=4),
                    ),
                    opacity=alt.condition(selection, alt.value(1.0), alt.value(0.18)),
                    tooltip=[
                        "competencia:N",
                        "Série:N",
                        alt.Tooltip("percentual:Q", format=".2%"),
                    ],
                )
                .add_params(selection)
                .properties(height=430)
            )
            endpoints = historical[historical["competencia"].eq(latest_complete)]
            endpoint_labels = (
                alt.Chart(endpoints)
                .mark_text(align="left", dx=5, color=_BLACK, fontSize=8)
                .encode(
                    x=alt.X("competencia:T"),
                    y=alt.Y("percentual:Q"),
                    text=alt.Text("percentual:Q", format=".1%"),
                )
            )
            st.altair_chart(
                chart + endpoint_labels,
                width="stretch",
                key="industry-revision-delinquency-frozen-cohort-history",
            )
            snapshot = frozen[frozen["competencia"].eq(latest_complete)].copy()
            if not snapshot.empty:
                snapshot["PL incluído (R$ bi)"] = (
                    pd.to_numeric(snapshot["pl_incluido_brl"], errors="coerce") / 1e9
                )
                snapshot["Inadimplência / carteira"] = pd.to_numeric(
                    snapshot["inadimplencia_sobre_carteira"], errors="coerce"
                )
                snapshot = snapshot.sort_values("PL incluído (R$ bi)", ascending=False)
                display = snapshot[
                    [
                        "tipo_recebivel_tabela_ii",
                        "fundos_incluidos",
                        "PL incluído (R$ bi)",
                        "Inadimplência / carteira",
                    ]
                ].rename(
                    columns={
                        "tipo_recebivel_tabela_ii": "Tipo Tabela II",
                        "fundos_incluidos": "Fundos",
                    }
                )
                st.markdown(f"**Fotografia da coorte em {_short_competence_label(latest_complete)}**")
                st.dataframe(
                    display.style.format(
                        {
                            "Fundos": "{:,.0f}",
                            "PL incluído (R$ bi)": "{:,.1f}",
                            "Inadimplência / carteira": "{:.2%}",
                        }
                    ),
                    hide_index=True,
                    width="stretch",
                )
            latest_frozen = frozen_summary.sort_values("competencia").iloc[-1]
            small_subtypes = []
            for subtype in ("Factoring", "Imobiliário"):
                subtype_row = snapshot[
                    snapshot["tipo_recebivel_tabela_ii"].eq(subtype)
                ]
                if not subtype_row.empty:
                    item = subtype_row.iloc[0]
                    fund_count = int(item.get("fundos_incluidos", 0))
                    small_subtypes.append(
                        f"{subtype}: {_fmt_int(fund_count)} {'fundo' if fund_count == 1 else 'fundos'} e "
                        f"{_fmt_bi(float(item.get('pl_incluido_brl', 0)), 1)}"
                    )
            st.caption(
                f"Fonte: CVM, Informe Mensal, Tabelas I, II e IV. Coorte e subtipo definidos em {stock_label_lower}; "
                "entram CNPJs ex-FIC com PL positivo, campos reportados e inadimplência até a carteira. "
                "A linha laranja mostra o consolidado ajustado de mercado. "
                f"A coorte fixa reúne {_fmt_int(latest_frozen.get('fundos_coorte', 0))} fundos e "
                f"{_fmt_bi(float(latest_frozen.get('pl_coorte_referencia_brl', 0)), 1)} de PL; há viés de sobrevivência. "
                + ("Baixa representatividade em " + "; ".join(small_subtypes) + ". " if small_subtypes else "")
                + f"Consolidado ajustado de mercado: {_fmt_pct(float(qa.get('inadimplencia_ajustada_pct', 0)))}."
            )
    with series_break_tab:
        series = _revision_frame(payload, "qa_series")
        if not series.empty:
            st.caption(
                "Nos meses legados, presença de reporte é inferida por registro da Tabela I; "
                "os snapshots brutos reprocessados mantêm a identificação exata do campo."
            )
            long = pd.concat(
                [
                    series.assign(Série="Bruta", percentual=series["inadimplencia_bruta_pct"]),
                    series.assign(Série="Ajustada", percentual=series["inadimplencia_ajustada_pct"]),
                ],
                ignore_index=True,
            )
            chart = (
                alt.Chart(long)
                .mark_line(strokeWidth=2.5)
                .encode(
                    x=alt.X("competencia:T", title=None, axis=alt.Axis(format="%b/%y", grid=False)),
                    y=alt.Y("percentual:Q", title="% da carteira", axis=alt.Axis(format=".0%", gridColor=_GRAY_LIGHT)),
                    color=alt.Color(
                        "Série:N",
                        scale=alt.Scale(domain=["Ajustada", "Bruta"], range=[_ORANGE, _BLACK]),
                        legend=alt.Legend(title=None, orient="bottom"),
                    ),
                    tooltip=["competencia:N", "Série:N", alt.Tooltip("percentual:Q", format=".2%")],
                )
                .properties(height=320, title="Evolução da métrica bruta e ajustada")
            )
            st.altair_chart(chart, width="stretch", key="industry-revision-delinquency")

        bridge = _revision_frame(payload, "bridge_summary")
        atlantic = _revision_frame(payload, "bridge_atlantico")
        if not bridge.empty:
            display = bridge[["bridge_group", "veiculos", "delta_inad_bruta_brl", "delta_inad_ajustada_brl", "delta_excesso_brl"]].copy()
            display.columns = ["Bridge jun→jul/24", "Veículos", "Δ inad. bruta", "Δ ajustada", "Δ excesso"]
            for column in ("Δ inad. bruta", "Δ ajustada", "Δ excesso"):
                display[column] = display[column].map(lambda value: _fmt_bi(value, 2))
            st.dataframe(display, hide_index=True, width="stretch")
            if not atlantic.empty:
                row = atlantic.iloc[0]
                st.caption(
                    "Atlântico FIDC explica "
                    f"{_fmt_bi(abs(float(row.get('delta_excesso_brl', 0))), 2)} da redução do excesso; "
                    "a série ajustada não repete a queda."
                )
        aging_message = (
            f"Os buckets de aging somam {_fmt_pct(float(qa.get('aging_reconciliacao_ratio', 0)))} "
            f"da inadimplência da Tabela I, com diferença de {_fmt_bi(float(qa.get('aging_gap_vs_inadimplencia_reportada_brl', 0)), 2)}."
        )
        if str(qa.get("aging_publication_status") or "").startswith("bloqueado"):
            st.warning("Ex-360 bloqueado: " + aging_message)
        else:
            st.info(aging_message)


def _market_share_focus_label(row: pd.Series) -> str:
    return f"{row['tipo_anbima']} · {row['foco_anbima']}"


def _render_revision_providers(payload: dict[str, object]) -> None:
    stock_competence = str(payload.get("latest_complete") or "")
    stock_label = _short_competence_label(stock_competence)
    stock_label_lower = stock_label.lower()
    conclusion_metrics = dict(payload.get("conclusion_metrics") or {})
    adjusted_universe = payload.get("schema_version") in {
        "fidc_revision_artifact_payload_v3",
        "fidc_revision_artifact_payload_v4",
        "fidc_revision_artifact_payload_v5",
        "fidc_revision_artifact_payload_v6",
    }
    ranking_tab, flows_tab, market_share_tab, model_tab = st.tabs(
        ["Ranking", "Bancos e fluxos", "Market share", "Modelo de prestação"]
    )
    with ranking_tab:
        concentration = _revision_history_frame(
            payload,
            "provider_concentration_history",
            fallback_key="provider_concentration",
        )
        if not concentration.empty:
            st.markdown(
                "<h2>Ranking e concentração dos prestadores</h2>",
                unsafe_allow_html=True,
            )
            concentration["Papel"] = concentration["papel"].map(
                {"administrador": "Administração", "gestor": "Gestão", "custodiante": "Custódia"}
            )
            concentration = concentration[concentration["Papel"].notna()].copy()
            latest_concentration = concentration[
                concentration["competencia"].eq(concentration["competencia"].max())
            ].set_index("papel")
            if {"administrador", "gestor", "custodiante"}.issubset(latest_concentration.index):
                _industry_headline(
                    f"Top 10 concentra {_fmt_pct(float(latest_concentration.loc['administrador', 'top10_share']))} "
                    f"em administração e {_fmt_pct(float(latest_concentration.loc['custodiante', 'top10_share']))} "
                    f"em custódia; gestão está em {_fmt_pct(float(latest_concentration.loc['gestor', 'top10_share']))}."
                )
            period_order, _period_colors = _revision_period_encoding(concentration)
            role_order = ["Administração", "Gestão", "Custódia"]
            left, right = st.columns(2)
            for container, field, title, key in (
                (left, "top10_share", "Participação do Top 10", "industry-revision-provider-top10-history"),
                (right, "top5_share", "Participação do Top 5", "industry-revision-provider-top5-history"),
            ):
                with container:
                    chart = (
                        alt.Chart(concentration)
                        .mark_bar(cornerRadiusEnd=2)
                        .encode(
                            x=alt.X(
                                f"{field}:Q",
                                title="% do PL ex-FIC",
                                axis=alt.Axis(format="%", gridColor=_GRAY_LIGHT),
                            ),
                            y=alt.Y(
                                "Papel:N",
                                title=None,
                                sort=role_order,
                                axis=None if field == "top5_share" else alt.Axis(),
                            ),
                            yOffset=alt.YOffset("Período:N", sort=period_order),
                            color=_revision_comparison_color(
                                concentration,
                                show_legend=field == "top10_share",
                            ),
                            tooltip=[
                                "Período:N",
                                "Papel:N",
                                alt.Tooltip(f"{field}:Q", title=title, format=".1%"),
                                alt.Tooltip("coverage_pl:Q", title="Cobertura identificada", format=".1%"),
                            ],
                        )
                        .properties(height=260, title=title)
                    )
                    labels = (
                        alt.Chart(concentration)
                        .mark_text(
                            align="right",
                            baseline="middle",
                            dx=-5,
                            color="white",
                            font="Arial",
                            fontSize=10,
                            fontWeight=700,
                        )
                        .encode(
                            x=alt.X(f"{field}:Q"),
                            y=alt.Y("Papel:N", sort=role_order),
                            yOffset=alt.YOffset("Período:N", sort=period_order),
                            text=alt.Text(f"{field}:Q", format=".1%"),
                        )
                    )
                    st.altair_chart(chart + labels, width="stretch", key=key)
            coverage_parts = []
            for _, row in concentration.sort_values(["papel", "competencia"]).iterrows():
                coverage_parts.append(
                    f"{row['Papel']} {row['Período']}: {_fmt_pct(float(row.get('coverage_pl', 0)))}"
                )
            universe_note = (
                "Sistema Petrobras/TAPSO excluídos"
                if adjusted_universe
                else "bundle v2: Sistema Petrobras/TAPSO ainda incluídos"
            )
            st.caption(
                f"Fonte: CVM, dez/25 e {stock_label_lower}. "
                f"Concentração sobre o PL ex-FIC, com prestador não informado mantido no denominador; {universe_note}. "
                + "Cobertura identificada: "
                + "; ".join(coverage_parts)
                + ". Administração é histórica por competência; gestão e custódia em dez/25 usam o cadastro vigente e não são uma série like-for-like."
            )

        ranking_history = _revision_frame(payload, "provider_historical_ranking")
        if not ranking_history.empty:
            latest_period = stock_competence
            latest_label = _short_competence_label(latest_period)
            btg_scenario = _revision_frame(
                payload, "btg_provider_ex_controlled_scenario"
            )
            scenario_by_role = (
                btg_scenario.set_index("papel")
                if not btg_scenario.empty
                else pd.DataFrame()
            )
            st.markdown("<h2>Evolução do ranking dos prestadores</h2>", unsafe_allow_html=True)
            if not scenario_by_role.empty and "gestor" in scenario_by_role.index:
                manager_scenario = scenario_by_role.loc["gestor"]
                st.markdown(
                    '<div class="industry-note">'
                    "Cenário BTG ex-coorte bancária: em gestão, a posição passa de "
                    f"#{int(manager_scenario['btg_rank'])} para "
                    f"#{int(manager_scenario['btg_rank_ex_controlados'])}. A exclusão usa a aba BTG "
                    "de FIDCs.xlsx; controle econômico fica fora do escopo dessa lista."
                    "</div>",
                    unsafe_allow_html=True,
                )
            role_labels = {
                "administrador": "Administração",
                "gestor": "Gestão",
                "custodiante": "Custódia",
            }
            role_tabs = st.tabs(list(role_labels.values()))
            for container, (role, label) in zip(role_tabs, role_labels.items(), strict=True):
                with container:
                    scoped = ranking_history[ranking_history["papel"].eq(role)].copy()
                    current_all = scoped[
                        scoped["competencia"].eq(latest_period)
                    ].sort_values("rank_periodo")
                    current = current_all.head(7).copy()
                    if not current["participante"].astype(str).str.contains(
                        "itaú|itau", case=False, regex=True
                    ).any():
                        itau = current_all[
                            current_all["participante"].astype(str).str.contains(
                                "itaú|itau", case=False, regex=True
                            )
                        ].head(1)
                        current = pd.concat([current_all.head(6), itau], ignore_index=True)
                    current = current.drop_duplicates("participante").sort_values(
                        "pl_brl", ascending=False
                    )
                    participants = current["participante"].astype(str).tolist()
                    lookup = scoped.set_index(["competencia", "participante"])
                    rows = []
                    for participant in participants:
                        row = {"Participante": participant}
                        for period, period_label in (
                            ("2024-12", "Dez/24"),
                            ("2025-12", "Dez/25"),
                            (latest_period, latest_label),
                        ):
                            if (period, participant) not in lookup.index:
                                row[period_label] = "—"
                                continue
                            item = lookup.loc[(period, participant)]
                            value = (
                                f"#{int(item['rank_periodo'])} · "
                                f"{_fmt_bi(float(item['pl_brl']), 1).removeprefix('R$ ').removesuffix(' bi')}"
                            )
                            if (
                                period == latest_period
                                and str(participant).casefold() == "btg pactual"
                                and not scenario_by_role.empty
                                and role in scenario_by_role.index
                            ):
                                scenario_item = scenario_by_role.loc[role]
                                value += (
                                    "\nex-coorte "
                                    f"#{int(scenario_item['btg_rank_ex_controlados'])} · "
                                    f"{_fmt_bi(float(scenario_item['btg_pl_ex_controlados_brl']), 1).removeprefix('R$ ').removesuffix(' bi')}"
                                )
                            row[period_label] = value
                        rows.append(row)
                    left, right = st.columns([1.15, 0.85])
                    with left:
                        st.dataframe(
                            pd.DataFrame(rows),
                            hide_index=True,
                            width="stretch",
                        )
                    with right:
                        current["PL (R$ bi)"] = pd.to_numeric(
                            current["pl_brl"], errors="coerce"
                        ) / 1e9
                        bars = (
                            alt.Chart(current)
                            .mark_bar(cornerRadiusEnd=2)
                            .encode(
                                x=alt.X(
                                    "PL (R$ bi):Q",
                                    title="R$ bi",
                                    axis=alt.Axis(gridColor=_GRAY_LIGHT),
                                ),
                                y=alt.Y(
                                    "participante:N",
                                    title=None,
                                    sort=participants,
                                ),
                                color=alt.Color(
                                    "participante:N",
                                    scale=alt.Scale(
                                        domain=participants,
                                        range=[
                                            _provider_color(name)
                                            for name in participants
                                        ],
                                    ),
                                    legend=None,
                                ),
                                tooltip=[
                                    "participante:N",
                                    alt.Tooltip("rank_periodo:Q", title="Posição"),
                                    alt.Tooltip("PL (R$ bi):Q", format=".1f"),
                                ],
                            )
                            .properties(height=280, title=f"{label} · PL observado em {latest_label}")
                        )
                        labels = (
                            alt.Chart(current)
                            .mark_text(
                                align="right",
                                baseline="middle",
                                dx=-5,
                                color="white",
                                font="Arial",
                                fontSize=10,
                                fontWeight=700,
                            )
                            .encode(
                                x=alt.X("PL (R$ bi):Q"),
                                y=alt.Y("participante:N", sort=participants),
                                text=alt.Text("PL (R$ bi):Q", format=".1f"),
                            )
                        )
                        st.altair_chart(
                            bars + labels,
                            width="stretch",
                            key=f"industry-revision-provider-ranking-{role}",
                        )
            btg_exclusion_note = ""
            if not btg_scenario.empty:
                exclusion_parts = []
                for _, item in btg_scenario.iterrows():
                    role_label = role_labels.get(str(item.get("papel")), str(item.get("papel")))
                    excluded_funds = item.get(
                        "fidcs_coorte_bancaria_excluidos",
                        item.get("fidcs_controlados_excluidos", 0),
                    )
                    excluded_pl = item.get(
                        "pl_coorte_bancaria_excluido_brl",
                        item.get("pl_controlado_excluido_brl", 0),
                    )
                    exclusion_parts.append(
                        f"{role_label}: {_fmt_int(excluded_funds)} fundos/{_fmt_bi(float(excluded_pl), 1)}"
                    )
                btg_exclusion_note = (
                    "Exclusão da coorte por função: " + "; ".join(exclusion_parts) + ". "
                )
            st.caption(
                "Fonte: CVM e aba BTG de FIDCs.xlsx; "
                f"{_fmt_int(conclusion_metrics.get('btg_bank_cohort_listed_roots', 0))} raízes listadas e "
                f"{_fmt_int(conclusion_metrics.get('btg_bank_cohort_observed_funds', 0))} observadas em {stock_label_lower}. "
                + btg_exclusion_note
                + f"Posição · PL em R$ bi; linhas ordenadas pelo PL observado de {latest_label.lower()}. "
                "Na célula do BTG, a segunda linha mostra o cenário ex-coorte; as barras mostram o PL observado. "
                "PL ex-FIC, sem Sistema Petrobras e TAPSO. "
                "Administração é observada; gestão e custódia de dez/24 e dez/25 são reconstruídas com o cadastro vigente."
            )

            if not btg_scenario.empty:
                scenario = btg_scenario.copy()
                scenario["Atividade"] = scenario["papel"].map(role_labels)
                scenario["BTG observado"] = scenario.apply(
                    lambda row: (
                        f"#{int(row['btg_rank'])} · "
                        f"{float(row['btg_pl_brl']) / 1e9:,.1f}"
                    ),
                    axis=1,
                )
                scenario["BTG ex-coorte"] = scenario.apply(
                    lambda row: (
                        f"#{int(row['btg_rank_ex_controlados'])} · "
                        f"{float(row['btg_pl_ex_controlados_brl']) / 1e9:,.1f}"
                    ),
                    axis=1,
                )
                excluded_count_column = (
                    "fidcs_coorte_bancaria_excluidos"
                    if "fidcs_coorte_bancaria_excluidos" in scenario
                    else "fidcs_controlados_excluidos"
                )
                excluded_pl_column = (
                    "pl_coorte_bancaria_excluido_brl"
                    if "pl_coorte_bancaria_excluido_brl" in scenario
                    else "pl_controlado_excluido_brl"
                )
                scenario["Fundos retirados"] = pd.to_numeric(
                    scenario[excluded_count_column], errors="coerce"
                ).fillna(0).astype(int)
                scenario["PL retirado"] = scenario[excluded_pl_column].map(
                    lambda value: _fmt_bi(float(value), 1)
                )
                st.markdown("**BTG ex-coorte bancária de FIDCs.xlsx**")
                st.dataframe(
                    scenario[
                        [
                            "Atividade",
                            "BTG observado",
                            "BTG ex-coorte",
                            "Fundos retirados",
                            "PL retirado",
                        ]
                    ],
                    hide_index=True,
                    width="stretch",
                )
                st.caption(
                    "Posição · PL em R$ bi. Cada função exclui somente os fundos da coorte que têm o BTG naquele papel. "
                    "A lista delimita a coorte bancária atual; controle, consolidação contábil e propriedade ficam fora do escopo."
                )

        independent = _revision_frame(payload, "provider_independent_ranking")
        if not independent.empty:
            st.markdown("<h2>Prestadores independentes</h2>", unsafe_allow_html=True)
            latest_period = stock_competence
            qi_latest = independent[
                independent["competencia"].eq(latest_period)
                & independent["participante"].astype(str).str.casefold().eq("qi tech")
            ].set_index("papel")
            if {"administrador", "custodiante"}.issubset(qi_latest.index):
                _industry_headline(
                    "QI Tech lidera administração e custódia entre independentes, com "
                    f"{_fmt_bi(float(qi_latest.loc['administrador', 'pl_brl']), 1)} e "
                    f"{_fmt_bi(float(qi_latest.loc['custodiante', 'pl_brl']), 1)}, respectivamente."
                )
            tabs = st.tabs(["Administração", "Gestão", "Custódia"])
            for container, (role, label) in zip(
                tabs,
                (("administrador", "Administração"), ("gestor", "Gestão"), ("custodiante", "Custódia")),
                strict=True,
            ):
                with container:
                    scoped = independent[independent["papel"].eq(role)].copy()
                    current = (
                        scoped[
                            scoped["competencia"].eq(latest_period)
                            & scoped["selected_latest_top_n"].fillna(False).astype(bool)
                        ]
                        .sort_values("rank_independente")
                        .head(6)
                    )
                    participants = current["participante"].astype(str).tolist()
                    lookup = scoped.set_index(["competencia", "participante"])
                    table_rows = []
                    for participant in participants:
                        output = {"Participante": participant}
                        for period, period_label in (
                            ("2024-12", "Dez/24"),
                            ("2025-12", "Dez/25"),
                            (latest_period, _short_competence_label(latest_period)),
                        ):
                            if (period, participant) not in lookup.index:
                                output[period_label] = "—"
                                continue
                            item = lookup.loc[(period, participant)]
                            output[period_label] = (
                                f"{int(item['rank_independente'])}/{int(item['rank_geral'])} · "
                                f"{float(item['pl_brl']) / 1e9:,.1f}"
                            )
                        table_rows.append(output)
                    left, right = st.columns([1.15, 0.85])
                    with left:
                        st.dataframe(pd.DataFrame(table_rows), hide_index=True, width="stretch")
                    with right:
                        current = current.assign(**{"PL (R$ bi)": pd.to_numeric(current["pl_brl"], errors="coerce") / 1e9})
                        chart = (
                            alt.Chart(current)
                            .mark_bar(cornerRadiusEnd=2)
                            .encode(
                                x=alt.X("PL (R$ bi):Q", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                                y=alt.Y("participante:N", title=None, sort="-x"),
                                color=alt.Color(
                                    "participante:N",
                                    scale=alt.Scale(
                                        domain=current["participante"].tolist(),
                                        range=[_provider_color(name) for name in current["participante"].tolist()],
                                    ),
                                    legend=None,
                                ),
                                tooltip=["participante:N", alt.Tooltip("PL (R$ bi):Q", format=",.1f")],
                            )
                            .properties(height=250, title=f"{label} · PL atual")
                        )
                        labels = (
                            alt.Chart(current)
                            .mark_text(
                                align="right",
                                baseline="middle",
                                dx=-5,
                                color="white",
                                font="Arial",
                                fontSize=10,
                                fontWeight=700,
                            )
                            .encode(
                                x=alt.X("PL (R$ bi):Q"),
                                y=alt.Y("participante:N", title=None, sort="-x"),
                                text=alt.Text("PL (R$ bi):Q", format=".1f"),
                            )
                        )
                        st.altair_chart(
                            chart + labels,
                            width="stretch",
                            key=f"industry-revision-independent-{role}",
                        )
            st.caption(
                "Fonte: CVM, PL ex-FIC; Sistema Petrobras e TAPSO excluídos. "
                "Posição = ranking entre independentes / ranking geral. Singulare é consolidada em QI Tech; "
                "Kanastra é alocada ao Itaú pela regra de afiliação solicitada e fica fora deste recorte."
            )
    with flows_tab:
        bank_history = _revision_frame(payload, "bank_fidc_evolution")
        if not bank_history.empty:
            st.markdown("<h2>Coorte atual de FIDCs dos cinco bancos</h2>", unsafe_allow_html=True)
            groups = bank_history[~bank_history["is_total_5_banks"].fillna(False).astype(bool)].copy()
            groups["PL (R$ bi)"] = pd.to_numeric(groups["pl_bruto_brl"], errors="coerce") / 1e9
            groups["Período"] = groups["competencia"].map(_short_competence_label)
            bank_order = ["BTG Pactual", "Itaú", "Santander", "Bradesco", "Banco do Brasil"]
            chart = (
                alt.Chart(groups)
                .mark_bar()
                .encode(
                    x=alt.X("Período:N", title=None, sort=[_short_competence_label(value) for value in ["2023-12", "2024-12", "2025-12", payload.get("latest_complete")]]),
                    y=alt.Y("PL (R$ bi):Q", title="PL bruto (R$ bi)", stack="zero", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    color=alt.Color(
                        "grupo_bancario:N",
                        scale=alt.Scale(
                            domain=bank_order,
                            range=["#1D4080", _ORANGE, "#8D9399", "#454A4F", "#D6A800"],
                        ),
                        legend=alt.Legend(title=None, orient="bottom"),
                    ),
                    tooltip=["Período:N", "grupo_bancario:N", alt.Tooltip("PL (R$ bi):Q", format=",.1f")],
                )
                .properties(height=360)
            )
            st.altair_chart(chart, width="stretch", key="industry-revision-bank-fidc-history")
            pivot = groups.pivot(index="grupo_bancario", columns="Período", values="PL (R$ bi)").reindex(bank_order)
            st.dataframe(pivot.style.format("{:,.1f}", na_rep="—"), width="stretch")
            bank_detail = _revision_frame(payload, "bank_fidc_detail")
            if not bank_detail.empty:
                latest_detail = bank_detail[
                    bank_detail["competencia"].eq(str(payload.get("latest_complete") or ""))
                    & bank_detail["grupo_bancario"].eq("BTG Pactual")
                    & bank_detail["observado"].fillna(False).astype(bool)
                ].copy()
                latest_detail["PL (R$ mm)"] = (
                    pd.to_numeric(latest_detail["pl_brl"], errors="coerce") / 1e6
                )
                latest_detail = latest_detail.sort_values(
                    "PL (R$ mm)", ascending=False
                ).head(5)
                if not latest_detail.empty:
                    latest_detail["Banco"] = "BTG Pactual"
                    btg_table = latest_detail[
                        ["Banco", "denominacao", "PL (R$ mm)"]
                    ].rename(columns={"denominacao": "FIDC"})
                    st.markdown(f"**BTG Pactual · cinco maiores FIDCs em {stock_label_lower}**")
                    st.dataframe(
                        btg_table.style.format({"PL (R$ mm)": "{:,.0f}"}),
                        hide_index=True,
                        width="stretch",
                    )

                btg_detail = bank_detail[
                    bank_detail["grupo_bancario"].eq("BTG Pactual")
                    & bank_detail["competencia"].isin(["2024-12", "2025-12"])
                ].copy()
                if not btg_detail.empty:
                    btg_detail["pl_brl"] = pd.to_numeric(
                        btg_detail["pl_brl"], errors="coerce"
                    ).fillna(0.0)
                    changes = (
                        btg_detail.pivot_table(
                            index=["cnpj_fundo", "denominacao"],
                            columns="competencia",
                            values="pl_brl",
                            aggfunc="sum",
                            fill_value=0.0,
                        )
                        .reset_index()
                    )
                    for period in ("2024-12", "2025-12"):
                        if period not in changes:
                            changes[period] = 0.0
                    changes["delta"] = changes["2025-12"] - changes["2024-12"]
                    largest_drop = changes.sort_values("delta").iloc[0]
                    if float(largest_drop["delta"]) < 0:
                        st.info(
                            f"A maior queda individual observada no BTG entre dez/24 e dez/25 é "
                            f"{largest_drop['denominacao']}: "
                            f"{_fmt_bi(float(largest_drop['2024-12']), 2)} para "
                            f"{_fmt_bi(float(largest_drop['2025-12']), 2)}. "
                            "O fundo reaparece em 2026 sob registro por classe; a série trata o movimento como quebra de reporte, "
                            "sem inferir liquidação econômica."
                        )
            st.caption(
                "Coorte fixa dos FIDCs listados nos conglomerados prudenciais dos cinco bancos no site do BCB, consulta em jul/26. "
                "A leitura retroativa acompanha somente os CNPJs presentes nessa fotografia atual. Fundos que integravam o conglomerado "
                "em datas passadas e foram depois liquidados, descontinuados ou retirados da consolidação não podem ser recuperados por essa fonte. "
                "Ausência de reporte permanece vazia; datas societárias não são inferidas."
            )

        from services.industry_revision_export import get_revision_export_status

        export_status = get_revision_export_status(_DATA_DIR)
        if export_status.bundle_valid and getattr(export_status, "html_path", ""):
            try:
                explorer_html = _industry_provider_flow_html(_industry_export_signature())
            except Exception as exc:  # noqa: BLE001
                st.caption(f"Explorador de fluxos indisponível: {exc}")
            else:
                st.iframe(explorer_html, width="stretch", height=980)
    with market_share_tab:
        st.markdown("<h2>Market share por subtipo ANBIMA</h2>", unsafe_allow_html=True)
        role = st.selectbox(
            "Função",
            ["administrador", "gestor", "custodiante"],
            format_func=lambda value: {"administrador": "Administração", "gestor": "Gestão", "custodiante": "Custódia"}[value],
            key="industry-revision-market-role",
        )
        market = _revision_frame(payload, "market_share")
        material = _revision_frame(payload, "material_focus_top6")
        if not market.empty and not material.empty:
            material["Foco"] = material.apply(_market_share_focus_label, axis=1)
            role_market = market[market["papel"].eq(role)].copy()
            blocked_all = (
                role_market[
                    role_market["publication_status"].astype(str).str.startswith("bloqueado")
                ][["tipo_anbima", "foco_anbima"]]
                .drop_duplicates()
                .apply(_market_share_focus_label, axis=1)
                .tolist()
            )
            selected = role_market.merge(
                material[["tipo_anbima", "foco_anbima", "Foco"]],
                on=["tipo_anbima", "foco_anbima"],
                how="inner",
            )
            blocked_visible = selected[
                selected["publication_status"].astype(str).str.startswith("bloqueado")
            ]["Foco"].unique().tolist()
            publishable = selected[~selected["Foco"].isin(blocked_visible)].copy()
            fixed = _revision_frame(payload, "market_share_top10_fixed")
            participants = fixed[fixed["papel"].eq(role)].sort_values("rank_top10_geral")["participante"].tolist()
            participants += ["Outros identificados", "Prestador não informado"]
            palette = [_provider_color(participant) for participant in participants]
            chart = (
                alt.Chart(publishable)
                .mark_bar()
                .encode(
                    x=alt.X("Foco:N", title=None, sort=material["Foco"].tolist(), axis=alt.Axis(labelAngle=-22, labelLimit=180)),
                    y=alt.Y("share_subtipo:Q", title="% do PL do subtipo", stack="zero", axis=alt.Axis(format="%", gridColor=_GRAY_LIGHT)),
                    color=alt.Color(
                        "participante_bucket:N",
                        scale=alt.Scale(domain=participants, range=palette),
                        legend=alt.Legend(title=None, orient="bottom", columns=4),
                    ),
                    order=alt.Order("stack_order:Q"),
                    tooltip=["Foco:N", "participante_bucket:N", alt.Tooltip("share_subtipo:Q", format=".1%")],
                )
                .properties(height=410)
            )
            st.altair_chart(chart, width="stretch", key=f"industry-revision-market-{role}")
            omitted = dict(payload.get("material_focus_omitted") or {})
            scope = _revision_frame(payload, "market_share_scope_summary")
            scope_row = scope[scope["papel"].eq(role)].iloc[0] if not scope.empty and scope["papel"].eq(role).any() else pd.Series(dtype=object)
            taxonomy_note = (
                "Subtipos = Tipo/Foco ANBIMA (cadastro dez/25, evidência documental e "
                "proxy determinístico da Tabela II). "
            )
            if adjusted_universe and not scope_row.empty:
                universe_note = (
                    f"Universo: PL ex-FIC de {stock_label_lower} sem Sistema Petrobras/TAPSO; cobertura dos 14 focos "
                    f"{_fmt_pct(float(scope_row.get('cobertura_classificacao_14_focos_pl', 0)))}. "
                )
            else:
                universe_note = (
                    "Bundle v2: universo ainda inclui Sistema Petrobras/TAPSO; a cobertura consolidada "
                    "dos 14 focos não estava disponível nessa geração. "
                )
            st.caption(
                taxonomy_note
                + universe_note
                + "Top 10 fixo da função. "
                + f"O gráfico principal cobre 6 focos; ficam fora {_fmt_int(omitted.get('focuses', 0))} focos e "
                + f"{_fmt_bi(float(omitted.get('pl', 0)), 1)}."
            )
            if blocked_all:
                omitted_blocked = [focus for focus in blocked_all if focus not in blocked_visible]
                suffix = " (fora dos seis focos exibidos)" if omitted_blocked else ""
                st.warning(
                    "Combinações não publicadas após o QA de denominador e cobertura: "
                    + "; ".join(blocked_all)
                    + suffix
                )
    with model_tab:
        st.markdown("<h2>Modelo de prestação e monoestruturas</h2>", unsafe_allow_html=True)
        model = _revision_frame(payload, "service_model")
        if not model.empty:
            model = model.copy()
            model["fundos"] = pd.to_numeric(model["fundos"], errors="coerce").fillna(0)
            mono_model = model[model["modelo_prestacao"].eq("Monoestrutura")]
            incomplete_model = model[model["modelo_prestacao"].eq("Dados incompletos")]
            if not mono_model.empty and not incomplete_model.empty:
                _industry_headline(
                    f"Monoestruturas são {_fmt_pct(float(mono_model.iloc[0]['share_fundos']))} dos fundos e "
                    f"{_fmt_pct(float(mono_model.iloc[0]['share_pl']))} do PL; dados incompletos cobrem "
                    f"{_fmt_pct(float(incomplete_model.iloc[0]['share_pl']))}."
                )
            model["pl"] = pd.to_numeric(model["pl"], errors="coerce").fillna(0.0)
            model["share_fundos"] = pd.to_numeric(
                model["share_fundos"], errors="coerce"
            ).fillna(0.0)
            model["share_pl"] = pd.to_numeric(
                model["share_pl"], errors="coerce"
            ).fillna(0.0)
            model_order = model["modelo_prestacao"].astype(str).tolist()
            long_model = pd.concat(
                [
                    model.assign(Série="% dos fundos", Participação=model["share_fundos"]),
                    model.assign(Série="% do PL bruto", Participação=model["share_pl"]),
                ],
                ignore_index=True,
            )
            left, right = st.columns([1.0, 1.15])
            with left:
                display = model[
                    ["modelo_prestacao", "fundos", "share_fundos", "pl", "share_pl"]
                ].copy()
                display.columns = [
                    "Modelo",
                    "Fundos",
                    "% dos fundos",
                    "PL",
                    "% do PL bruto",
                ]
                display["PL"] = display["PL"].map(lambda value: _fmt_bi(value, 1))
                display["% dos fundos"] = display["% dos fundos"].map(_fmt_pct)
                display["% do PL bruto"] = display["% do PL bruto"].map(_fmt_pct)
                st.dataframe(display, hide_index=True, width="stretch")
            with right:
                bars = (
                    alt.Chart(long_model)
                    .mark_bar(cornerRadiusEnd=2)
                    .encode(
                        x=alt.X(
                            "Participação:Q",
                            title="participação",
                            axis=alt.Axis(format="%", gridColor=_GRAY_LIGHT),
                        ),
                        y=alt.Y(
                            "modelo_prestacao:N",
                            title=None,
                            sort=model_order,
                        ),
                        yOffset=alt.YOffset(
                            "Série:N", sort=["% dos fundos", "% do PL bruto"]
                        ),
                        color=alt.Color(
                            "Série:N",
                            title=None,
                            scale=alt.Scale(
                                domain=["% dos fundos", "% do PL bruto"],
                                range=[_GRAY_LIGHT, _ORANGE],
                            ),
                            legend=alt.Legend(orient="bottom"),
                        ),
                        tooltip=[
                            "modelo_prestacao:N",
                            "Série:N",
                            alt.Tooltip("Participação:Q", format=".1%"),
                        ],
                    )
                    .properties(height=330, title="Quantidade de fundos e PL")
                )
                labels = (
                    alt.Chart(long_model)
                    .mark_text(
                        align="left",
                        baseline="middle",
                        dx=4,
                        color=_BLACK,
                        font="Arial",
                        fontSize=9,
                    )
                    .encode(
                        x=alt.X("Participação:Q"),
                        y=alt.Y("modelo_prestacao:N", sort=model_order),
                        yOffset=alt.YOffset(
                            "Série:N", sort=["% dos fundos", "% do PL bruto"]
                        ),
                        text=alt.Text("Participação:Q", format=".1%"),
                    )
                )
                st.altair_chart(
                    bars + labels,
                    width="stretch",
                    key="industry-revision-service-model-shares",
                )
            st.caption(
                f"Fonte: CVM, cadastro vigente em {stock_label_lower}. Universo bruto de {_fmt_int(model['fundos'].sum())} fundos, incluindo FIC-FIDCs. "
                "A classificação usa o mesmo conglomerado econômico normalizado para administração, gestão e custódia; campos ausentes permanecem em Dados incompletos."
            )
        mono = _revision_frame(payload, "monostructure_concentration")
        if not mono.empty:
            display = mono.head(10)[
                [
                    "grupo_economico",
                    "pl_mono_brl",
                    "fundos_mono",
                    "fundos_top20",
                    "pl_top20_brl",
                    "maior_fundo",
                    "maior_fundo_share",
                    "top3_share",
                    "top10_share",
                ]
            ].copy()
            display.columns = [
                "Grupo",
                "PL mono",
                "Fundos",
                "Fundos no Top 20",
                "PL no Top 20",
                "Maior fundo",
                "% maior",
                "% Top 3",
                "% Top 10",
            ]
            display["PL mono"] = display["PL mono"].map(lambda value: _fmt_bi(value, 1))
            display["PL no Top 20"] = display["PL no Top 20"].map(lambda value: _fmt_bi(value, 1))
            for column in ("% maior", "% Top 3", "% Top 10"):
                display[column] = display[column].map(_fmt_pct)
            st.dataframe(display, hide_index=True, width="stretch")
            st.caption("PL mono usa o universo bruto dos fundos, incluindo FIC-FIDCs; o cruzamento Top 20 usa o ranking ex-FIC.")
            bb = mono[mono["grupo_economico"].eq("Banco do Brasil")]
            oliveira = mono[mono["grupo_economico"].eq("Oliveira Trust")]
            if not bb.empty and not oliveira.empty:
                st.info(
                    f"No Banco do Brasil, {bb.iloc[0]['maior_fundo']} representa {_fmt_pct(bb.iloc[0]['maior_fundo_share'])} do PL mono. "
                    f"Na Oliveira Trust, TAPSO representa {_fmt_pct(oliveira.iloc[0]['maior_fundo_share'])}."
                )


def _render_revision_top20(payload: dict[str, object]) -> None:
    stock_label_lower = _short_competence_label(payload.get("latest_complete")).lower()
    top20 = _revision_frame(payload, "top20_fidcs")
    outros = _revision_frame(payload, "top20_outros")
    profiles = _revision_frame(payload, "profiles")
    ranking_tab, others_tab, profile_tab = st.tabs(["Top 20 FIDCs", "Top 20 Outros", "Ficha do fundo"])
    with ranking_tab:
        top20_share = float(
            pd.to_numeric(top20["market_share_ex_fic"], errors="coerce").fillna(0).sum()
        )
        _industry_headline(
            f"Os 20 maiores FIDCs representam {_fmt_pct(top20_share)} do PL ex-FIC; "
            "a curadoria completa fica na ficha individual."
        )
        display = top20[["rank", "denominacao", "pl", "market_share_ex_fic", "anbima_tipo", "anbima_foco", "admin_nome", "modelo_prestacao"]].copy()
        display.columns = ["#", "Fundo", "PL", "Share ex-FIC", "Tipo ANBIMA", "Foco ANBIMA", "Administrador", "Modelo"]
        display["PL"] = display["PL"].map(lambda value: _fmt_bi(value, 1))
        display["Share ex-FIC"] = display["Share ex-FIC"].map(_fmt_pct)
        st.dataframe(display, hide_index=True, width="stretch", height=730)
        st.caption(
            f"Fonte: ANBIMA e documentos primários locais; ranking em {stock_label_lower}. Evidência e links completos constam no workbook."
        )
    with others_tab:
        top20_outros_share = float(
            pd.to_numeric(outros["market_share_outros"], errors="coerce").fillna(0).sum()
        )
        _industry_headline(
            f"Top 20 representam {_fmt_pct(top20_outros_share)} de Outros; classificação oficial, hipótese e status permanecem separados."
        )
        columns = [
            "rank_outros",
            "denominacao",
            "pl",
            "market_share_outros",
            "classificacao_oficial",
            "hipotese_revisao",
            "evidencia_revisao",
            "fonte_revisao",
            "status_revisao",
        ]
        available = [column for column in columns if column in outros]
        display = outros[available].copy()
        display = display.rename(
            columns={
                "rank_outros": "#",
                "denominacao": "Fundo",
                "pl": "PL",
                "market_share_outros": "Share de Outros",
                "classificacao_oficial": "Classificação oficial",
                "hipotese_revisao": "Hipótese",
                "evidencia_revisao": "Evidência",
                "fonte_revisao": "Fonte",
                "status_revisao": "Status",
            }
        )
        display["PL"] = display["PL"].map(lambda value: _fmt_bi(value, 1))
        display["Share de Outros"] = display["Share de Outros"].map(_fmt_pct)
        st.dataframe(display, hide_index=True, width="stretch", height=730)
        st.caption(
            f"Fonte: ANBIMA e documentos primários locais; ranking em {stock_label_lower}. Ranking dos 20 maiores fundos classificados "
            f"em Outros, sobre o universo ex-FIC. Os 20 fundos representam {_fmt_pct(top20_outros_share)} de Outros. "
            "Hipóteses de reenquadramento permanecem separadas da classificação oficial; evidência, fonte e status documentam a revisão."
        )
    with profile_tab:
        if profiles.empty:
            st.info("Curadoria dos 20 maiores fundos indisponível.")
        else:
            options = profiles.sort_values("rank").to_dict(orient="records")
            selected_rank = st.selectbox(
                "Fundo",
                [int(row["rank"]) for row in options],
                format_func=lambda rank: next(f"#{rank} · {row['nome_curto']}" for row in options if int(row["rank"]) == rank),
                key="industry-revision-profile",
            )
            row = next(row for row in options if int(row["rank"]) == int(selected_rank))
            st.markdown(f"### {row['nome_curto']}")
            st.caption(f"{row['cnpj_fundo_formatado']} · {_fmt_bi(float(row['pl']), 1)} · {_fmt_pct(float(row['market_share_ex_fic']))} do PL ex-FIC")
            left, right = st.columns(2)
            with left:
                st.markdown("**Mecânica do fundo**")
                st.markdown(f"**Cedente/originador:** {row.get('cedente_originador') or 'não identificado'}")
                st.markdown(f"**Sacado/devedor:** {row.get('sacado_devedor') or 'não identificado'}")
                st.markdown(f"**Recebíveis:** {row.get('natureza_recebiveis') or 'não identificado'}")
                st.markdown(f"**Funcionamento:** {row.get('funcionamento_economico') or 'não identificado'}")
            with right:
                st.markdown("**Capital, prestadores e evidência**")
                st.markdown(f"**Emissões:** {row.get('emissoes') or 'não identificado'}")
                st.markdown(f"**Classes/garantias:** {row.get('classes_subordinacao_garantias') or 'não identificado'}")
                st.markdown(f"**Prestadores:** {row.get('administrador')} · {row.get('gestor')} · {row.get('custodiante')}")
                st.markdown(f"**ANBIMA:** {row.get('anbima_tipo')} · {row.get('anbima_foco')}")
            st.markdown(f"**Status:** {row.get('status_curadoria')} · **Lacunas:** {row.get('campos_nao_identificados') or 'nenhuma registrada'}")
            if row.get("fonte"):
                st.markdown(f"[Fonte primária]({row['fonte']}) · consulta em {row.get('data_consulta', 'n/d')}")


def _render_revision_offer_ticket_distribution(
    payload: dict[str, object],
    *,
    offers_cutoff: object,
    source_as_of: str,
    chart_key: str,
) -> None:
    ticket_distribution = _revision_frame(
        payload, "closed_offer_ticket_distribution"
    )
    if ticket_distribution.empty:
        return

    ticket_distribution["% das ofertas"] = pd.to_numeric(
        ticket_distribution["offer_share"], errors="coerce"
    )
    ticket_distribution["Volume (R$ bi)"] = (
        pd.to_numeric(
            ticket_distribution["registered_volume_brl"], errors="coerce"
        )
        / 1e9
    )
    ticket_distribution["% do volume"] = pd.to_numeric(
        ticket_distribution["registered_volume_share"], errors="coerce"
    )
    ticket_distribution["Ticket médio (R$ mi)"] = (
        pd.to_numeric(
            ticket_distribution["period_mean_ticket_brl"], errors="coerce"
        )
        / 1e6
    )
    ticket_distribution["Ticket mediano (R$ mi)"] = (
        pd.to_numeric(
            ticket_distribution["period_median_ticket_brl"], errors="coerce"
        )
        / 1e6
    )
    ticket_distribution["% ofertas · rótulo"] = ticket_distribution[
        "% das ofertas"
    ].map(lambda value: _fmt_pct(float(value)))
    ticket_distribution["% volume · rótulo"] = ticket_distribution[
        "% do volume"
    ].map(lambda value: _fmt_pct(float(value)))
    ticket_distribution["Volume · rótulo"] = ticket_distribution[
        "Volume (R$ bi)"
    ].map(
        lambda value: f"{float(value):,.1f}".replace(",", "@")
        .replace(".", ",")
        .replace("@", ".")
    )
    bucket_order = (
        ticket_distribution.sort_values("bucket_order")["ticket_bucket"]
        .drop_duplicates()
        .tolist()
    )
    period_order = (
        ticket_distribution.sort_values("period_order")["period_label"]
        .drop_duplicates()
        .tolist()
    )
    def _chart(
        *,
        field: str,
        label_field: str,
        title: str,
        axis_title: str,
        percent: bool,
        key: str,
        height: int,
    ) -> None:
        chart = (
            alt.Chart(ticket_distribution)
            .mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
            .encode(
                x=alt.X(
                    "ticket_bucket:N",
                    title="valor total registrado por oferta",
                    sort=bucket_order,
                    axis=alt.Axis(labelAngle=0, labelLimit=105),
                ),
                xOffset=alt.XOffset("period_label:N", sort=period_order),
                y=alt.Y(
                    f"{field}:Q",
                    title=axis_title,
                    axis=alt.Axis(
                        format=".0%" if percent else ",.0f",
                        gridColor=_GRAY_LIGHT,
                    ),
                ),
                color=alt.Color(
                    "period_label:N",
                    title=None,
                    sort=period_order,
                    scale=alt.Scale(
                        domain=period_order,
                        range=[_GRAY, _BLACK, _ORANGE],
                    ),
                    legend=alt.Legend(orient="bottom"),
                ),
                tooltip=[
                    alt.Tooltip("period_label:N", title="Período"),
                    alt.Tooltip("ticket_bucket:N", title="Faixa"),
                    alt.Tooltip("closed_offers:Q", title="Ofertas", format=",.0f"),
                    alt.Tooltip("% das ofertas:Q", format=".1%"),
                    alt.Tooltip("Volume (R$ bi):Q", format=",.2f"),
                    alt.Tooltip("% do volume:Q", format=".1%"),
                ],
            )
            .properties(height=height, title=title)
        )
        labels = (
            alt.Chart(ticket_distribution)
            .mark_text(dy=-5, color=_BLACK, font="Arial", fontSize=8.5)
            .encode(
                x=alt.X("ticket_bucket:N", sort=bucket_order),
                xOffset=alt.XOffset("period_label:N", sort=period_order),
                y=alt.Y(f"{field}:Q"),
                text=alt.Text(f"{label_field}:N"),
            )
        )
        st.altair_chart(chart + labels, width="stretch", key=key)

    _chart(
        field="% das ofertas",
        label_field="% ofertas · rótulo",
        title="Distribuição do valor das emissões",
        axis_title="% das ofertas encerradas",
        percent=True,
        key=chart_key,
        height=330,
    )
    left, right = st.columns(2)
    with left:
        _chart(
            field="% do volume",
            label_field="% volume · rótulo",
            title="Participação no volume registrado",
            axis_title="% do volume encerrado",
            percent=True,
            key=f"{chart_key}-volume-share",
            height=330,
        )
    with right:
        _chart(
            field="Volume (R$ bi)",
            label_field="Volume · rótulo",
            title="Volume registrado por faixa",
            axis_title="R$ bilhões",
            percent=False,
            key=f"{chart_key}-volume-absolute",
            height=330,
        )
    current_period = ticket_distribution[
        ticket_distribution["period_label"].eq(period_order[-1])
        & ticket_distribution["ticket_bucket"].astype(str).str.startswith("≥")
    ]
    if not current_period.empty:
        current_bucket = current_period.iloc[0]
        st.markdown(
            '<div class="industry-note">'
            f'Em jan–jun/26, ofertas ≥ R$ 500 mi representam '
            f'<b>{_fmt_pct(float(current_bucket["% do volume"]))}</b> do volume, '
            f'ou <b>{_fmt_bi(float(current_bucket["registered_volume_brl"]), 1)}</b>.'
            "</div>",
            unsafe_allow_html=True,
        )
    st.caption(
        f"2024 e 2025 = ano completo; 2026 = jan–jun até {_date_label(offers_cutoff)}. "
        "Faixas por Valor Total Registrado; os gráficos de quantidade e volume "
        "fecham 100% em cada período."
    )


def _render_revision_offers(payload: dict[str, object]) -> None:
    annual = _revision_frame(payload, "closed_offers_annual")
    monthly = _revision_frame(payload, "closed_offers_monthly")
    jan_june = _revision_offer_comparable_frame(payload)
    current = _revision_offer_current_row(payload, annual)
    offers_cutoff = _revision_offers_cutoff(payload)
    source_as_of = _date_label(payload.get("offers_source_as_of", "n/d"))

    st.markdown("<h2>Ofertas encerradas e ticket de emissão</h2>", unsafe_allow_html=True)
    if not current.empty:
        cards = [
            _industry_kpi(
                "Ofertas encerradas 2026",
                _fmt_int(current.get("closed_offers", 0)),
                f"até {_date_label(offers_cutoff)}",
            ),
            _industry_kpi(
                "Volume registrado",
                _fmt_bi(float(current.get("registered_volume_brl", 0)), 1),
                "jan–jun/26",
            ),
            _industry_kpi(
                "Ticket médio",
                _fmt_mi(float(current.get("mean_registered_ticket_brl", 0))),
                "por Número do Requerimento",
            ),
            _industry_kpi(
                "PF no volume colocado",
                _fmt_pct(float(current.get("natural_person_placed_volume_share", 0))),
                "cobertura "
                + _fmt_pct(
                    float(
                        current.get(
                            "placed_quantity_registered_volume_coverage", 0
                        )
                    )
                ),
            ),
        ]
        st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    st.caption(
        "Fonte: [CVM — Ofertas Públicas de Distribuição](https://dados.cvm.gov.br/dataset/oferta-distrib), "
        f"arquivo oferta_resolucao_160.csv, consulta em {source_as_of}. Uma oferta corresponde a "
        "Numero_Requerimento. Filtros: Valor_Mobiliario = Cotas de FIDC; Tipo_Oferta = Primária; "
        "Status_Requerimento = Oferta Encerrada; Data_Encerramento até "
        f"{_date_label(offers_cutoff)}; Valor_Total_Registrado positivo. Status abertos ficam fora. "
        "Oferta Encerrada é a denominação literal do fluxo da CVM e não comprova colocação integral."
    )

    if not jan_june.empty and not monthly.empty:
        jan_june = jan_june.copy()
        jan_june["year"] = pd.to_numeric(jan_june["year"], errors="coerce").astype("Int64")
        jan_june["Período"] = jan_june["year"].astype(str) + " jan–jun"
        jan_june["Volume (R$ bi)"] = pd.to_numeric(
            jan_june["registered_volume_brl"], errors="coerce"
        ) / 1e9
        jan_june["Ticket médio (R$ mi)"] = pd.to_numeric(
            jan_june["mean_registered_ticket_brl"], errors="coerce"
        ) / 1e6
        current_year = int(jan_june["year"].max())
        left, right = st.columns(2)
        with left:
            chart = (
                alt.Chart(jan_june)
                .mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
                .encode(
                    x=alt.X("Período:N", title=None, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("Volume (R$ bi):Q", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    color=alt.condition(alt.datum.year == current_year, alt.value(_ORANGE), alt.value(_BLACK)),
                    tooltip=[
                        "Período:N",
                        alt.Tooltip("Volume (R$ bi):Q", format=",.1f"),
                        alt.Tooltip("closed_offers:Q", title="Ofertas", format=",.0f"),
                        alt.Tooltip("Ticket médio (R$ mi):Q", format=",.1f"),
                    ],
                )
                .properties(height=340, title="Jan–jun comparável")
            )
            labels = (
                alt.Chart(jan_june)
                .mark_text(
                    dy=-8,
                    color=_BLACK,
                    font="Arial",
                    fontSize=10,
                    fontWeight=700,
                )
                .encode(
                    x=alt.X("Período:N"),
                    y=alt.Y("Volume (R$ bi):Q"),
                    text=alt.Text("Volume (R$ bi):Q", format=".1f"),
                )
            )
            st.altair_chart(
                chart + labels,
                width="stretch",
                key="industry-revision-closed-offers-jan-june",
            )
        with right:
            monthly["year"] = pd.to_numeric(monthly["year"], errors="coerce").astype("Int64")
            monthly["month"] = pd.to_numeric(monthly["month"], errors="coerce").astype("Int64")
            monthly = monthly[
                monthly["year"].isin([2024, 2025, 2026])
                & monthly["month"].le(6)
            ].sort_values(["year", "month"])
            monthly["Volume acumulado (R$ bi)"] = (
                pd.to_numeric(monthly["registered_volume_brl"], errors="coerce")
                .groupby(monthly["year"])
                .cumsum()
                / 1e9
            )
            monthly["Mês"] = monthly["month"].map(
                {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun"}
            )
            chart = (
                alt.Chart(monthly)
                .mark_line(strokeWidth=2.5)
                .encode(
                    x=alt.X(
                        "month:Q",
                        title=None,
                        axis=alt.Axis(
                            values=list(range(1, 7)),
                            labelExpr="['','Jan','Fev','Mar','Abr','Mai','Jun'][datum.value]",
                            grid=False,
                        ),
                    ),
                    y=alt.Y("Volume acumulado (R$ bi):Q", axis=alt.Axis(gridColor=_GRAY_LIGHT)),
                    color=alt.Color(
                        "year:N",
                        title=None,
                        scale=alt.Scale(domain=[2024, 2025, 2026], range=[_GRAY, _BLACK, _ORANGE]),
                    ),
                    tooltip=["year:N", "Mês:N", alt.Tooltip("Volume acumulado (R$ bi):Q", format=",.1f")],
                )
                .properties(height=340, title="Janeiro a junho · acumulado")
            )
            end_labels = (
                alt.Chart(monthly)
                .transform_filter(alt.datum.month == 6)
                .mark_text(
                    align="left",
                    baseline="middle",
                    dx=5,
                    font="Arial",
                    fontSize=10,
                    fontWeight=700,
                )
                .encode(
                    x=alt.X("month:Q"),
                    y=alt.Y("Volume acumulado (R$ bi):Q"),
                    color=alt.Color(
                        "year:N",
                        scale=alt.Scale(
                            domain=[2024, 2025, 2026],
                            range=[_GRAY, _BLACK, _ORANGE],
                        ),
                        legend=None,
                    ),
                    text=alt.Text("Volume acumulado (R$ bi):Q", format=".1f"),
                )
            )
            st.altair_chart(
                chart + end_labels,
                width="stretch",
                key="industry-revision-closed-offers-cumulative",
            )

    _render_revision_offer_ticket_distribution(
        payload,
        offers_cutoff=offers_cutoff,
        source_as_of=source_as_of,
        chart_key="industry-revision-closed-offer-ticket-histogram",
    )

    annual_display_source = annual.copy()
    if not current.empty:
        if not annual_display_source.empty:
            annual_display_source["year"] = pd.to_numeric(
                annual_display_source["year"], errors="coerce"
            )
            annual_display_source = annual_display_source[
                ~annual_display_source["year"].eq(2026)
            ]
        annual_display_source = pd.concat(
            [annual_display_source, current.to_frame().T], ignore_index=True
        )

    if not annual_display_source.empty:
        annual_display_source["year"] = pd.to_numeric(
            annual_display_source["year"], errors="coerce"
        )
        annual_display_source = annual_display_source.sort_values("year")
        annual_display = annual_display_source[
            [
                "year",
                "closed_offers",
                "registered_volume_brl",
                "mean_registered_ticket_brl",
                "median_registered_ticket_brl",
                "natural_person_placed_volume_share",
                "professional_target_registered_volume_share",
            ]
        ].copy()
        annual_display.columns = ["Ano", "Ofertas", "Volume registrado", "Ticket médio", "Ticket mediano", "PF no colocado", "Público profissional"]
        annual_display["Ano"] = (
            annual_display["Ano"]
            .astype(int)
            .astype(str)
            .replace({"2026": "2026 jan–jun"})
        )
        for column in ("Volume registrado", "Ticket médio", "Ticket mediano"):
            annual_display[column] = annual_display[column].map(
                lambda value: _fmt_bi(float(value), 3) if pd.notna(value) else "n/d"
            )
        for column in ("PF no colocado", "Público profissional"):
            annual_display[column] = annual_display[column].map(
                lambda value: _fmt_pct(float(value)) if pd.notna(value) else "n/d"
            )
        st.dataframe(annual_display, hide_index=True, width="stretch")
        st.caption(
            "PF no colocado usa quantidade colocada × preço unitário e mantém a cobertura sobre o valor registrado; "
            "Público profissional usa o público-alvo informado no requerimento."
        )

    top15 = _revision_frame(payload, "closed_offer_top15")
    top15_summary = _revision_frame(payload, "closed_offer_top15_summary")
    st.markdown(
        "<h2>Top 15 ofertas encerradas e originadores</h2>",
        unsafe_allow_html=True,
    )
    if not top15.empty and not top15_summary.empty:
        top15["registered_volume_brl"] = pd.to_numeric(
            top15["registered_volume_brl"], errors="coerce"
        )
        top15["investor_count"] = pd.to_numeric(
            top15["investor_count"], errors="coerce"
        )
        summary_by_period = top15_summary.set_index("period_label")
        summary_2025 = summary_by_period.loc["2025 FY"]
        summary_2026 = summary_by_period.loc["2026 jan-jun"]
        st.markdown(
            '<div class="industry-note">'
            f'O Itaú BBA liderou <b>{_fmt_int(summary_2026["ibba_lead_offers_top15"])}</b> '
            f'das 15 maiores ofertas em jan–jun/26 '
            f'({_fmt_bi(float(summary_2026["ibba_lead_volume_top15_brl"]), 1)}), '
            f'ante <b>{_fmt_int(summary_2025["ibba_lead_offers_top15"])}</b> em 2025FY '
            f'({_fmt_bi(float(summary_2025["ibba_lead_volume_top15_brl"]), 1)}).'
            "</div>",
            unsafe_allow_html=True,
        )

        def _top15_display(period_label: str) -> pd.DataFrame:
            frame = top15[top15["period_label"].eq(period_label)].sort_values(
                "rank"
            ).copy()
            frame["Volume"] = frame["registered_volume_brl"].map(
                lambda value: _fmt_bi(float(value), 2)
            )
            frame["Nº de Inv."] = frame["investor_count"].map(
                lambda value: _fmt_int(value) if pd.notna(value) else "N/D"
            )
            frame = frame[
                [
                    "rank",
                    "fund_name_short",
                    "originator_group",
                    "Volume",
                    "ibba_coord_lead_label",
                    "firm_commitment_label",
                    "publico",
                    "Nº de Inv.",
                ]
            ]
            frame.columns = [
                "#",
                "FIDC",
                "Originador",
                "Volume",
                "IBBA Coord-Líder?",
                "Garantia Firme?",
                "Público",
                "Nº de Inv.",
            ]
            return frame

        left, right = st.columns(2)
        for column, period_label, heading in (
            (left, "2026 jan-jun", "Jan–jun/26"),
            (right, "2025 FY", "2025FY"),
        ):
            summary = summary_by_period.loc[period_label]
            with column:
                st.markdown(f"#### {heading} · 15 maiores")
                st.dataframe(
                    _top15_display(period_label),
                    hide_index=True,
                    width="stretch",
                    height=610,
                )
                st.caption(
                    f"Subtotal: {_fmt_bi(float(summary['top15_registered_volume_brl']), 2)} "
                    f"({_fmt_pct(float(summary['top15_share_of_period_volume']))} "
                    "do volume encerrado no período)."
                )
        st.caption(
            "Universo: CVM, Cotas de FIDC, oferta primária, status Oferta Encerrada, "
            "Data de Encerramento no período e Valor Total Registrado positivo. "
            "Originador não identificável permanece como “Não identificado”. "
            "IBBA Coord-Líder usa Nome_Lider; Garantia Firme usa Regime_distribuicao. "
            "Nº de Inv. soma todas as colunas Num_Invest_*; a coluna de pessoa natural "
            "isolada não representa o total. Empates de volume usam o Número do "
            "Requerimento em ordem crescente. A base pública não contém propostas, fees "
            "ou preço de coordenação para atribuir competitividade."
        )


def _render_revision_data_exports(
    payload: dict[str, object],
    status: pd.DataFrame,
    industry: pd.DataFrame,
) -> None:
    from services.industry_revision_export import get_revision_export_status

    export_status = get_revision_export_status(_DATA_DIR)
    st.markdown(
        "<h2>Apresentação, workbook e explorador revisados</h2>",
        unsafe_allow_html=True,
    )
    if export_status.bundle_valid:
        st.success(
            f"Bundle {export_status.bundle_id} validado para {export_status.latest_complete}: "
            "PPTX, XLSX e HTML reconciliados pelo mesmo payload e por hashes."
        )
        _render_industry_exports(suffix="revision", as_of_date=str(payload.get("offers_as_of") or ""))
    else:
        st.error(
            "Exportação revisada bloqueada. "
            + (export_status.validation_error or "bundle publicado indisponível")
        )

    st.markdown("<h2>Escopo, fontes e limitações</h2>", unsafe_allow_html=True)
    qa = dict(payload.get("qa_latest") or {})
    coverage = _revision_frame(payload, "classification_coverage")
    sources = dict(payload.get("sources") or {})
    profiles = _revision_frame(payload, "profiles")
    curation_date = (
        str(profiles["data_consulta"].dropna().max())
        if not profiles.empty and "data_consulta" in profiles
        else "n/d"
    )
    source_table = pd.DataFrame(
        [
            ["Estoque, cotistas e carteira", "CVM — Informe Mensal FIDC", payload.get("latest_complete"), f"{_fmt_int(qa.get('veiculos_total', 0))} veículos / {_fmt_int(qa.get('fundos_total', 0))} fundos"],
            ["Tipo e Foco ANBIMA", "ANBIMA Data + evidência documental + proxy CVM", sources.get("anbima", payload.get("latest_complete")), f"{_fmt_pct(float(coverage.loc[coverage['categoria'].eq('Oficial ANBIMA'), 'share'].sum()))} do PL oficial" if not coverage.empty else "n/d"],
            ["Ofertas", "CVM — Ofertas Públicas", payload.get("offers_as_of"), "comparação YTD no mesmo corte"],
            ["Curadoria Top 20", "CVM, FundosNet e documentos de emissão", curation_date, "lacunas marcadas como não identificado"],
        ],
        columns=["Dimensão", "Fonte", "Data-base", "Cobertura/regra"],
    )
    st.dataframe(source_table, hide_index=True, width="stretch")
    limitations = [
        "Gestor e custodiante de 2024/2025 são reconstruções com cadastro vigente; não formam série histórica comparável.",
        "Market share usa Top 10 geral fixo por função e separa Outros identificados de prestador não informado.",
        "Monoestrutura usa conglomerado econômico normalizado e PL bruto dos fundos; não permite inferir preço ou contrato.",
    ]
    if str(qa.get("aging_publication_status") or "").startswith("bloqueado"):
        limitations.insert(
            0,
            "Inadimplência ex-360 dias permanece bloqueada porque os buckets não reconciliam a Tabela I.",
        )
    st.markdown("\n".join(f"- {item}" for item in limitations))

    with st.expander("Bases revisadas para download", expanded=False):
        files = {
            "QA inadimplência": "qa_inadimplencia_competencia.csv",
            "Histórico de inadimplência da coorte atual": "inadimplencia_coorte_atual_historico.csv",
            "Top 20 FIDCs": "top20_fidcs.csv",
            "Top 20 Outros": "top20_outros.csv",
            "Market share por subtipo": "market_share_por_subtipo.csv",
            "Concentração de monoestruturas": "monoestrutura_concentracao.csv",
            "Detalhe da coorte bancária": "bancos_fidcs_detalhe.csv",
            "BTG ex-coorte bancária": "btg_prestadores_ex_controlados.csv",
            "Histórico CVM de prestadores": "prestadores_historico_cvm_transicoes_links.csv",
            "Histograma das ofertas": "../industry_closed_offer_ticket_distribution.csv",
            "Manifest analítico": "revision_manifest.json",
            "Manifest do bundle": "industry_export_bundle.json",
        }
        for label, filename in files.items():
            path = (_DATA_DIR / "generated_revision" / filename).resolve()
            if path.exists():
                st.download_button(
                    label,
                    path.read_bytes(),
                    file_name=path.name,
                    mime="application/json" if path.suffix == ".json" else "text/csv",
                    key=f"industry-revision-download-{path.name}",
                    width="stretch",
                )


def _render_industry_data_audit(
    status: pd.DataFrame,
    industry: pd.DataFrame,
    latest_complete: str,
    offers_as_of: str,
    large_funds: pd.DataFrame,
) -> None:
    st.markdown("<h2>Dados e exportações</h2>", unsafe_allow_html=True)
    _render_industry_exports(suffix="audit", as_of_date=offers_as_of)
    if diagnostics_enabled() and not status.empty:
        st.markdown("<h2>Diagnóstico de competências</h2>", unsafe_allow_html=True)
        display = status.tail(18).copy()
        display["PL"] = display["pl_total"].map(lambda value: _fmt_bi(value, 1))
        display["Veículos vs. anterior"] = display["vehicle_ratio_vs_previous"].map(
            lambda value: "-" if pd.isna(value) else _fmt_pct(value)
        )
        display["PL vs. anterior"] = display["pl_ratio_vs_previous"].map(
            lambda value: "-" if pd.isna(value) else _fmt_pct(value)
        )
        display = display[["competencia", "publication_status", "n_veiculos", "PL", "Veículos vs. anterior", "PL vs. anterior", "status_reason"]]
        display.columns = ["Competência", "Status", "Veículos", "PL", "Veículos vs. anterior", "PL vs. anterior", "Motivo"]
        st.dataframe(display, hide_index=True, width="stretch")
    with st.expander("Sobre a base", expanded=False):
        source_table = pd.DataFrame(
            [
                ["Estoque, fluxos, cotistas e inadimplência", "CVM — Informe Mensal FIDC", latest_complete, "Consolidado"],
                ["Ofertas, participantes e investidores", "CVM — Ofertas Públicas de Distribuição", offers_as_of, "Atualização diária"],
                ["FIDCs > R$ 5 bi", "CVM/FundosNet", latest_complete, "Classificação documental"],
                ["Classes formais", "ANBIMA — Deliberação nº 72", "Referencial", "Tipo e foco separados"],
            ],
            columns=["Dimensão", "Fonte", "Data-base", "Status"],
        )
        st.dataframe(source_table, hide_index=True, width="stretch")
        st.markdown(
            "- [CVM — Informe Mensal FIDC](https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal)\n"
            "- [CVM — Ofertas Públicas de Distribuição](https://dados.cvm.gov.br/dataset/oferta-distrib)\n"
            "- Gestor e custodiante históricos são reconstruções com cadastro vigente; administração é observada mensalmente.\n"
            "- Investidores nominais e turnover secundário não constam das bases públicas gratuitas usadas no estudo."
        )
    dataset_names = {
        "Indústria mensal": "industry_monthly.csv",
        "Status de competências": "industry_competence_status.csv",
        "Ofertas anuais": "industry_offers_annual.csv",
        "Ranking de ofertas": "industry_offer_rankings.csv.gz",
        "Ranking de estoque": "industry_stock_ranking_deltas.csv.gz",
        "Cedentes/originadores": "industry_originators_annual.csv",
        "Investidores": "industry_investor_distribution.csv",
        "FIDCs > R$5 bi": "industry_large_fund_classification.csv",
    }
    with st.expander("Bases detalhadas", expanded=False):
        selected_name = st.selectbox("Artefato", list(dataset_names), key="industry-raw-artifact")
        frame = _intelligence_frame(dataset_names[selected_name])
        st.dataframe(frame.head(500), hide_index=True, width="stretch", height=420)
        st.download_button(
            "Baixar CSV",
            data=frame.to_csv(index=False).encode("utf-8"),
            file_name=dataset_names[selected_name].replace(".gz", ""),
            mime="text/csv",
            icon=":material/download:",
            width="content",
            key="industry-raw-download",
        )


def render_tab_industry_study() -> None:
    st.markdown(_CSS + _EXECUTIVE_CSS, unsafe_allow_html=True)
    industry = _intelligence_frame("industry_monthly.csv")
    status = _intelligence_frame("industry_competence_status.csv")
    if industry.empty:
        st.info("Base da indústria não encontrada.")
        return
    complete_status = status[status["publication_status"].eq("completa")].sort_values("competencia")
    latest_complete = str(complete_status.iloc[-1]["competencia"]) if not complete_status.empty else str(industry.iloc[-1]["competencia"])
    revision_payload: dict[str, object]
    try:
        revision_payload = _load_industry_revision_payload(_industry_revision_signature())
    except Exception as exc:  # noqa: BLE001
        st.error(
            "A revisão analítica da indústria não está materializada ou falhou na validação. "
            f"Detalhe: {exc}"
        )
        st.code(
            "FIDC_INPUT_WORKBOOK=/caminho/Industria_FIDC_Dados_202607.xlsx "
            "python scripts/publish_fidc_revision_bundle.py"
        )
        return
    payload_latest = str(revision_payload.get("latest_complete") or latest_complete)
    offers_as_of = str(revision_payload.get("offers_as_of") or "n/d")
    qa = dict(revision_payload.get("qa_latest") or {})
    coverage = f"{_fmt_int(qa.get('veiculos_total', 0))} veículos / {_fmt_int(qa.get('fundos_total', 0))} fundos"
    render_page_header(
        "Dados da Indústria",
        "Escala, base investidora, qualidade do dado, prestadores e fundos que explicam a concentração.",
    )
    render_context_strip(
        source="CVM e ANBIMA",
        base_until=f"{_competence_label(payload_latest)} (estoque) | {_date_label(offers_as_of)} (ofertas)",
        coverage=coverage,
    )
    if revision_payload.get("schema_version") == "fidc_revision_artifact_payload_v2":
        st.warning(
            "Bundle analítico v2 carregado durante a atualização. O conteúdo permanece disponível, "
            "com as limitações de universo indicadas nas notas; os arquivos Office continuam "
            "bloqueados até a sincronização integral do bundle v3."
        )
    if payload_latest != latest_complete:
        st.warning(
            f"O painel mensal marca {latest_complete} como última competência completa, mas o "
            f"payload revisado publicado usa {payload_latest}. Atualize o bundle antes de publicar."
        )

    (
        conclusions_tab,
        overview_tab,
        card_breakdown_tab,
        investors_tab,
        credit_tab,
        providers_tab,
        top20_tab,
        offers_tab,
        audit_tab,
    ) = st.tabs(INDUSTRY_VIEW_TABS)
    with conclusions_tab:
        _render_revision_conclusions(revision_payload)
    with overview_tab:
        _render_revision_overview(revision_payload)
    with card_breakdown_tab:
        _render_revision_card_breakdown(revision_payload)
    with investors_tab:
        _render_revision_investors(revision_payload)
    with credit_tab:
        _render_revision_credit(revision_payload)
    with providers_tab:
        _render_revision_providers(revision_payload)
    with top20_tab:
        _render_revision_top20(revision_payload)
    with offers_tab:
        _render_revision_offers(revision_payload)
    with audit_tab:
        _render_revision_data_exports(revision_payload, status, industry)
