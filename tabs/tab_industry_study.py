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

import json
import re
import sqlite3
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from services.industry_study import (
    CEDENTE_REVIEW_COLUMNS,
    CRITERIA_REVIEW_COLUMNS,
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
    load_pipeline_manifest,
    load_cedente_reviews,
    load_fund_universe,
    normalize_cnpj,
    save_cedente_reviews,
    save_criteria_reviews,
    save_dataframe,
    save_pipeline_manifest,
    save_cedente_structured,
)

_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"
_REGULATORY_DB = Path(__file__).resolve().parents[1] / "data" / "fidc_credit_strategy" / "fidc_credit_strategy.sqlite"
_ALL_FIDCS_CRITERIA = Path(__file__).resolve().parents[1] / "data" / "regulatory_profiles" / "all_fidcs_criteria_monitoraveis_ime.csv"
_CEDENTE_REVIEW_PATH = _DATA_DIR / "cedente_reviews.csv"
_CEDENTE_STRUCTURED_PATH = _DATA_DIR / "cedentes_structured.csv.gz"
_PIPELINE_MANIFEST_PATH = _DATA_DIR / "industry_pipeline_manifest.json"
_PIPELINE_INDEX_PATH = _DATA_DIR / "industry_pipeline_index.json"
_FUND_SNAPSHOT_PATH = _DATA_DIR / "industry_fund_snapshot.csv.gz"
_FUND_SNAPSHOT_MANIFEST_PATH = _DATA_DIR / "industry_fund_snapshot_manifest.json"
_ISSUANCE_ANNUAL_PATH = _DATA_DIR / "issuance_annual.csv"
_ISSUANCE_SECTOR_YEAR_PATH = _DATA_DIR / "issuance_sector_year.csv"
_ISSUANCE_TRANCHES_PATH = _DATA_DIR / "issuance_tranches.csv.gz"
_ISSUANCE_MANIFEST_PATH = _DATA_DIR / "industry_issuance_manifest.json"
_DOCUMENT_INVENTORY_PATH = _DATA_DIR / "document_inventory.csv.gz"
_DOCUMENT_CHUNKS_PATH = _DATA_DIR / "document_processing_chunks.csv"
_DOCUMENT_MANIFEST_PATH = _DATA_DIR / "industry_document_manifest.json"
_CRITERIA_REVIEW_PATH = _DATA_DIR / "criteria_reviews.csv"
_CRITERIA_STRUCTURED_PATH = _DATA_DIR / "criteria_structured.csv.gz"
_CRITERIA_MANIFEST_PATH = _DATA_DIR / "industry_criteria_manifest.json"
_CEDENTE_REVIEW_COLUMNS = CEDENTE_REVIEW_COLUMNS
_CRITERIA_REVIEW_COLUMNS = CRITERIA_REVIEW_COLUMNS

# Paleta laranja/preto/cinza - maior contraste entre tons sobre fundo branco.
_ORANGE = "#ff5a00"
_ORANGE_SOFT = "rgba(255, 90, 0, 0.16)"
_BLACK = "#1a1a1a"
_GRAY = "#8c8c8c"
_GRAY_LIGHT = "#e5e3e0"
_INK_SECONDARY = "#595959"

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
    color: #ff5a00;
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
    border-top: 3px solid #ff5a00;
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


def _fmt_pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%".replace(".", ",")


def _fmt_int(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", ".")


def _pct_label(value: float | None, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "n/d"
    return f"{value:.{digits}f}%".replace(".", ",")


@st.cache_data(show_spinner=False)
def _load_csv(name: str) -> pd.DataFrame | None:
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
    vehicle_latest = _load_csv("universe_latest.csv")
    return build_cedente_structured(
        candidates,
        reviews,
        fund_universe=_load_cedente_fund_universe(),
        vehicle_latest=vehicle_latest if vehicle_latest is not None else pd.DataFrame(),
    )


def _persist_structured_cedentes(candidates: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    fund_universe = _load_cedente_fund_universe()
    vehicle_latest = _load_csv("universe_latest.csv")
    structured = build_cedente_structured(
        candidates,
        reviews,
        fund_universe=fund_universe,
        vehicle_latest=vehicle_latest if vehicle_latest is not None else pd.DataFrame(),
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
    for col in ["Docs", "Cedentes", "Critérios", "Camadas"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).map(lambda value: _fmt_int(float(value)))
    if "Sub mín." in out.columns:
        out["Sub mín."] = pd.to_numeric(out["Sub mín."], errors="coerce").map(lambda value: _pct_label(value))
    return out


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
        _curation_card("Com cedentes", _fmt_int(float((numeric.get("cedente_rows", pd.Series(0, index=numeric.index)) > 0).sum())), "curadoria estruturada"),
        _curation_card("Com critérios", _fmt_int(float((numeric.get("criteria_rows", pd.Series(0, index=numeric.index)) > 0).sum())), "regras monitoráveis"),
        _curation_card("Com sub mín.", _fmt_int(float((numeric.get("criteria_subordination_rows", pd.Series(0, index=numeric.index)) > 0).sum())), "percentual extraído"),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    tab_table, tab_coverage, tab_manifest = st.tabs(["Tabela", "Cobertura", "Manifesto"])
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

    with tab_coverage:
        coverage_rows = [
            {"Camada": "Emissões 2025-2026", "FIDCs": int(numeric.get("tem_emissao_2025_2026", pd.Series(False, index=numeric.index)).astype(str).str.lower().isin({"true", "1"}).sum())},
            {"Camada": "Documentos", "FIDCs": int((numeric.get("document_rows", pd.Series(0, index=numeric.index)) > 0).sum())},
            {"Camada": "Documentos locais", "FIDCs": int((numeric.get("document_local_ready", pd.Series(0, index=numeric.index)) > 0).sum())},
            {"Camada": "Cedentes/sacados", "FIDCs": int((numeric.get("cedente_rows", pd.Series(0, index=numeric.index)) > 0).sum())},
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
    vehicle = _load_csv("vehicle_monthly.csv.gz")
    audit = _load_csv("update_audit_monthly.csv")
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

    dimensions = {
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
    metric_options = ["PL médio", "Captação líquida", "Veículos", "Fundos"]
    dimension_labels = list(dimensions)

    ctrl_a, ctrl_b, ctrl_c, ctrl_d, ctrl_e = st.columns([1.0, 1.0, 0.9, 0.9, 0.65])
    with ctrl_a:
        row_label = st.selectbox("Linhas", dimension_labels, index=dimension_labels.index("Administrador"), key="industry_heatmap_rows")
    with ctrl_b:
        col_label = st.selectbox("Colunas", dimension_labels, index=dimension_labels.index("Segmento"), key="industry_heatmap_cols")
    with ctrl_c:
        metric_label = st.selectbox("Métrica", metric_options, key="industry_heatmap_metric")
    with ctrl_d:
        period = st.selectbox(
            "Janela",
            ["Última competência", "Últimos 12 meses", "2025 até data-base", "Histórico completo"],
            key="industry_heatmap_period",
        )
    with ctrl_e:
        top_n = st.slider("Top", min_value=5, max_value=25, value=12, step=1, key="industry_heatmap_top")

    cedentes = _build_structured_cedentes()
    snapshot_tables = _load_fund_snapshot_tables()
    snapshot = snapshot_tables["snapshot"]
    assert isinstance(snapshot, pd.DataFrame)
    frame = _period_filter(vehicle, comp, period)
    frame = _heatmap_base_frame(frame, cedentes, snapshot, dimensions[row_label], dimensions[col_label])
    if frame.empty:
        st.caption("Sem linhas para a janela selecionada.")
        return
    frame = frame.copy()
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
    if dimensions[row_label] in _CEDENTE_HEATMAP_COLUMNS or dimensions[col_label] in _CEDENTE_HEATMAP_COLUMNS:
        st.caption(
            "Quando a dimensão é cedente/sacado, PL e fluxo são alocados igualmente entre os participantes ativos "
            "do mesmo fundo para evitar dupla contagem direta."
        )
    if dimensions[row_label] in _SNAPSHOT_MULTI_COLUMNS or dimensions[col_label] in _SNAPSHOT_MULTI_COLUMNS:
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


def _load_criteria_reviews() -> pd.DataFrame:
    return load_criteria_reviews(_CRITERIA_REVIEW_PATH)


def _save_criteria_reviews(reviews: pd.DataFrame) -> None:
    save_criteria_reviews(reviews, _CRITERIA_REVIEW_PATH)


def _persist_structured_criteria(reviews: pd.DataFrame) -> pd.DataFrame:
    criteria = load_criteria_source(_ALL_FIDCS_CRITERIA)
    fund_universe = _load_cedente_fund_universe()
    structured = build_criteria_structured(criteria, reviews, fund_universe=fund_universe)
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
        _curation_card("Sub mínima mediana", _pct_label(float(sub_values.median()) if not sub_values.empty else None), f"{_fmt_int(float(len(sub)))} regras · {_fmt_int(float(sub['cnpj_fundo'].nunique())) if 'cnpj_fundo' in sub else '0'} FIDCs"),
        _curation_card("IQR sub mínima", f"{_pct_label(float(sub_values.quantile(0.25)) if not sub_values.empty else None)}-{_pct_label(float(sub_values.quantile(0.75)) if not sub_values.empty else None)}", "p25-p75"),
        _curation_card("Monitoráveis", _fmt_int(float(quality.get("monitorable_rows", 0))) if isinstance(quality, dict) else "0", "proxy IME disponível"),
        _curation_card("Parciais", _fmt_int(float(quality.get("partial_rows", 0))) if isinstance(quality, dict) else "0", "exigem leitura/operacional"),
        _curation_card("Revisões", _fmt_int(float(len(reviews))), _CRITERIA_REVIEW_PATH.name),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    tab_sub, tab_heat, tab_base, tab_review, tab_manifest = st.tabs(["Sub mínima", "Heatmap", "Base", "Revisão", "Manifesto"])
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
        keep = ["fundo", "cnpj_fundo", "setor", "segmento", "criterio", "chave", "limite_regra", "pct_min", "monitorabilidade_ime", "documento_origem", "document_date", "status_revisao", "score_confianca_final"]
        st.dataframe(
            show[[col for col in keep if col in show.columns]].rename(
                columns={
                    "fundo": "Fundo",
                    "cnpj_fundo": "CNPJ",
                    "setor": "Setor",
                    "segmento": "Segmento",
                    "criterio": "Critério",
                    "chave": "Chave",
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
            _save_criteria_reviews(updated_reviews)
            structured_saved = _persist_structured_criteria(updated_reviews)
            st.success(
                f"Revisões salvas em `{_CRITERIA_REVIEW_PATH}` e base recomposta "
                f"em `{_CRITERIA_STRUCTURED_PATH.name}` ({len(structured_saved):,} regras)."
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
        _curation_card("Revisões salvas", _fmt_int(float(len(reviews))), _CEDENTE_REVIEW_PATH.name),
    ]
    st.markdown(f'<div class="industry-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    filter_a, filter_b, filter_c, filter_d = st.columns([1.3, 0.8, 0.8, 0.7])
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

    filtered = frame[
        frame["participant_type"].isin(selected_types)
        & frame["status"].isin(selected_statuses)
        & frame["score_confianca"].ge(min_score)
    ].copy()
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
        )
        filtered = filtered[search.str.contains(query, case=False, na=False)].copy()

    filtered = filtered.sort_values(["score_confianca", "cnpj_fundo"], ascending=[False, True]).head(120)
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
            "Documento": filtered["documento_origem"],
            "Página": filtered["pagina"],
            "Evidência": filtered["evidence_context"].astype(str).str.slice(0, 240),
            "Notas": filtered["notas"].fillna("").astype(str),
        }
    )
    disabled_cols = [
        "ID",
        "Tipo",
        "Fundo",
        "CNPJ fundo",
        "Participante extraído",
        "CNPJ extraído",
        "Score auto",
        "Evidências",
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
        _save_cedente_reviews(updated_reviews)
        structured_saved = _persist_structured_cedentes(candidates, updated_reviews)
        st.success(
            f"Revisões salvas em `{_CEDENTE_REVIEW_PATH}` e base estruturada atualizada "
            f"em `{_CEDENTE_STRUCTURED_PATH.name}` ({len(structured_saved):,} linhas)."
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

    dimensions = {
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

    cedentes = _build_structured_cedentes()
    snapshot_tables = _load_fund_snapshot_tables()
    snapshot = snapshot_tables["snapshot"]
    assert isinstance(snapshot, pd.DataFrame)
    dim_col = dimensions[dimension_label]
    frame = _period_filter(vehicle, comp, period)
    frame = _heatmap_base_frame(frame, cedentes, snapshot, dim_col, dim_col)
    if frame.empty:
        st.caption("Sem dados para a dimensão/janela selecionada.")
        return

    frame = frame.copy()
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
    selected_value = st.selectbox("Valor", options, key="industry_deep_value")
    selected = frame[frame["valor_dimensao"].eq(selected_value)].copy()
    selected_current = current[current["valor_dimensao"].eq(selected_value)].copy()

    total_pl = float(selected_current["pl_metric"].sum())
    total_capt = float(selected["captacao_metric"].sum())
    funds = selected_current[fund_id].nunique()
    vehicles = selected_current["cnpj"].nunique()
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

    if dim_col in _CEDENTE_HEATMAP_COLUMNS and not cedentes.empty:
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


def _status_badge_text(status: object) -> str:
    mapping = {
        "ok": "ok",
        "warning": "atenção",
        "missing": "ausente",
        "missing_artifact": "artefato ausente",
    }
    return mapping.get(str(status or ""), str(status or "n/d"))


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

    rollup = index.get("quality_rollup", {}) if isinstance(index.get("quality_rollup"), dict) else {}
    status_counts = rollup.get("module_status_counts", {}) if isinstance(rollup.get("module_status_counts"), dict) else {}
    modules = index.get("modules", []) if isinstance(index.get("modules"), list) else []
    refresh_plan = index.get("refresh_plan", []) if isinstance(index.get("refresh_plan"), list) else []
    artifacts = index.get("artifact_index", []) if isinstance(index.get("artifact_index"), list) else []
    cards = [
        _curation_card(
            "Módulos ok",
            f"{_fmt_int(float(status_counts.get('ok', 0)))}/{_fmt_int(float(rollup.get('modules_total', 0)))}",
            f"gerado {str(index.get('generated_at_utc', ''))[:10]}",
        ),
        _curation_card(
            "Artefatos presentes",
            f"{_fmt_int(float(rollup.get('artifacts_present', 0)))}/{_fmt_int(float(rollup.get('artifacts_total', 0)))}",
            f"{_fmt_int(float(rollup.get('artifacts_missing', 0)))} ausentes",
        ),
        _curation_card(
            "Competência IME",
            str(rollup.get("competencia_snapshot") or rollup.get("competencia_final") or "n/d"),
            "snapshot granular",
        ),
        _curation_card(
            "Snapshot FIDCs",
            _fmt_int(float(rollup.get("fund_snapshot_rows", 0))),
            "base unificada",
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

    tab_modules, tab_refresh, tab_artifacts, tab_json = st.tabs(["Módulos", "Refresh mensal", "Artefatos", "Manifesto"])
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

    with tab_refresh:
        st.markdown(
            '<div class="industry-curation-note">A ordem abaixo foi pensada para atualização mensal: '
            "primeiro os informes e séries granulares, depois camadas derivadas, e por último o próprio índice. "
            "Os módulos documentais e de curadoria podem ser reexecutados em lotes.</div>",
            unsafe_allow_html=True,
        )
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


def render_tab_industry_study() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

    industry = _load_csv("industry_monthly.csv")
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

    concentration = _load_csv("concentration_monthly.csv")
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

    vehicle = _load_csv("vehicle_monthly.csv.gz")
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
        segments = _load_csv("segments_monthly.csv")
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
        prestadores = _load_csv("prestadores_latest.csv")
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
