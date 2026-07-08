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
import json
import re
import sqlite3
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"
_REGULATORY_DB = Path(__file__).resolve().parents[1] / "data" / "fidc_credit_strategy" / "fidc_credit_strategy.sqlite"
_ALL_FIDCS_CRITERIA = Path(__file__).resolve().parents[1] / "data" / "regulatory_profiles" / "all_fidcs_criteria_monitoraveis_ime.csv"
_CEDENTE_REVIEW_PATH = _DATA_DIR / "cedente_reviews.csv"
_CEDENTE_REVIEW_COLUMNS = [
    "review_id",
    "status",
    "nome_revisado",
    "cnpj_revisado",
    "grupo_economico",
    "setor_revisado",
    "segmento_revisado",
    "confianca_manual",
    "notas",
]

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
    text = re.sub(r"\s+", " ", str(value or "").strip(" ;,."))
    if len(text) < 8:
        return ""
    upper = text.upper()
    noisy_tokens = (
        "CEP",
        "ANDAR",
        "CONJUNTO",
        "SALA",
        "BAIRRO",
        "MUNICÍPIO",
        "MUNICIPIO",
        "RUA ",
        "AVENIDA",
        "DO DE INVESTIMENTO",
    )
    if any(token in upper for token in noisy_tokens):
        return ""
    if sum(char.isdigit() for char in text) > 4:
        return ""
    if not re.search(r"\b(S\.A\.?|LTDA|BANCO|INSTITUI|FUNDO|COMPANHIA|SOCIEDADE|SERVIÇOS|SERVICOS|TECH|TRANSPORTES)\b", upper):
        return ""
    return text[:120]


def _review_id(row: pd.Series) -> str:
    key = "|".join(
        str(row.get(col, ""))
        for col in ["cnpj_fundo", "participant_type", "participant_name_candidate", "participant_cnpj_candidate", "source_cache"]
    )
    return hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _extract_page(value: object) -> str:
    match = re.search(r"p[aá]gina\s+(\d+)|pagina\s+(\d+)|page\s+(\d+)", str(value or ""), flags=re.IGNORECASE)
    if not match:
        return ""
    return next(group for group in match.groups() if group)


def _load_cedente_reviews() -> pd.DataFrame:
    if not _CEDENTE_REVIEW_PATH.exists():
        return pd.DataFrame(columns=_CEDENTE_REVIEW_COLUMNS)
    reviews = pd.read_csv(_CEDENTE_REVIEW_PATH, dtype=str, keep_default_na=False)
    for col in _CEDENTE_REVIEW_COLUMNS:
        if col not in reviews.columns:
            reviews[col] = ""
    return reviews[_CEDENTE_REVIEW_COLUMNS]


def _save_cedente_reviews(reviews: pd.DataFrame) -> None:
    out = reviews.copy()
    for col in _CEDENTE_REVIEW_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[_CEDENTE_REVIEW_COLUMNS].drop_duplicates("review_id", keep="last")
    out.to_csv(_CEDENTE_REVIEW_PATH, index=False)


@st.cache_data(show_spinner=False)
def _load_cedente_candidates() -> pd.DataFrame:
    if not _REGULATORY_DB.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(_REGULATORY_DB) as conn:
            candidates = pd.read_sql_query(
                """
                select cnpj_fundo, fund_name, setor_n1, setor_n2, participant_type,
                       participant_cnpj_candidate, participant_name_candidate,
                       evidence_context, source_cache
                from cedentes_sacados_candidates
                """,
                conn,
            )
    except sqlite3.Error:
        return pd.DataFrame()
    if candidates.empty:
        return candidates
    candidates["review_id"] = candidates.apply(_review_id, axis=1)
    candidates["participante_extraido"] = candidates["participant_name_candidate"].map(_clean_candidate_name)
    candidates["participante_extraido"] = candidates["participante_extraido"].where(
        candidates["participante_extraido"].astype(str).str.len() > 0,
        candidates["participant_cnpj_candidate"].fillna("").astype(str),
    )
    candidates["documento_origem"] = candidates["source_cache"].map(lambda value: Path(str(value)).name if str(value) else "")
    candidates["pagina"] = candidates["evidence_context"].map(_extract_page)
    candidates["metodo_extracao"] = "regex_contexto_documental"
    has_name = candidates["participante_extraido"].astype(str).str.len() > 0
    has_cnpj = candidates["participant_cnpj_candidate"].astype(str).str.replace(r"\D", "", regex=True).str.len().eq(14)
    has_doc = candidates["source_cache"].astype(str).str.len() > 0
    candidates["score_confianca"] = (0.35 + 0.25 * has_name + 0.25 * has_cnpj + 0.15 * has_doc).clip(upper=0.95)
    candidates["evidencias_agrupadas"] = candidates.groupby("review_id")["review_id"].transform("size")
    candidates = candidates.sort_values(["score_confianca", "cnpj_fundo"], ascending=[False, True])
    return candidates.drop_duplicates("review_id", keep="first").reset_index(drop=True)


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
        "Segmento": "segmento_principal",
        "Subsegmento financeiro": "segmento_financeiro_principal",
        "Condomínio": "condominio",
        "Público-alvo": "publico_alvo",
        "FIC-FIDC": "is_fic_fidc",
    }
    metric_options = ["PL médio", "Captação líquida", "Veículos", "Fundos"]

    ctrl_a, ctrl_b, ctrl_c, ctrl_d, ctrl_e = st.columns([1.0, 1.0, 0.9, 0.9, 0.65])
    with ctrl_a:
        row_label = st.selectbox("Linhas", list(dimensions), index=0, key="industry_heatmap_rows")
    with ctrl_b:
        col_label = st.selectbox("Colunas", list(dimensions), index=3, key="industry_heatmap_cols")
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

    frame = _period_filter(vehicle, comp, period)
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
        monthly = (
            frame.groupby(["competencia", "linha", "coluna"], dropna=False)["pl"]
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
        heatmap = (
            frame.groupby(["linha", "coluna"], dropna=False)["captacao_liquida"]
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

    type_labels = {
        "cedente_originador": "cedente/originador",
        "sacado_devedor": "sacado/devedor",
        "consultora": "consultora",
    }
    cards = [
        _curation_card("Candidatos automáticos", _fmt_int(float(len(frame))), "deduplicados por fundo/participante"),
        _curation_card("FIDCs com evidência", _fmt_int(float(frame["cnpj_fundo"].nunique())), "universo regulatório"),
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
        _save_cedente_reviews(pd.concat([keep_existing, edited_reviews], ignore_index=True))
        st.success(f"Revisões salvas em `{_CEDENTE_REVIEW_PATH}`.")


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
    audit_tab, heatmap_tab, cedente_tab = st.tabs(["Base granular", "Heatmaps", "Cedentes"])
    with audit_tab:
        _render_monthly_audit_and_base(industry, comp)
    with heatmap_tab:
        _render_generic_heatmaps(vehicle, comp)
    with cedente_tab:
        _render_cedente_review_workbench()

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
