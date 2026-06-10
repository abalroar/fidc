from __future__ import annotations

from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from services.fidc_credit_strategy import (
    DEFAULT_DB_PATH,
    database_exists,
    load_metadata,
    load_strategy_tables,
    load_table,
)

_STATIC_REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "fidc_strategy_static_20260609.html"

_CSS = """
<style>
.strategy-header {
    border-bottom: 1px solid #ece5de;
    margin: 0.1rem 0 1rem 0;
    padding-bottom: 0.9rem;
}
.strategy-kicker {
    color: #d35714;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    line-height: 1.2;
    text-transform: uppercase;
}
.strategy-title {
    color: #12171d;
    font-size: 2.1rem;
    font-weight: 650;
    letter-spacing: 0;
    line-height: 1.05;
    margin: 0.25rem 0 0.35rem 0;
}
.strategy-subtitle {
    color: #66717d;
    font-size: 0.94rem;
    line-height: 1.45;
    max-width: 64rem;
}
.strategy-card-grid {
    display: grid;
    gap: 0.55rem;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    margin: 0.7rem 0 1rem 0;
}
.strategy-kpi {
    background: #f8f9fa;
    border: 1px solid #e8edf2;
    border-radius: 6px;
    min-height: 72px;
    padding: 0.65rem 0.75rem;
}
.strategy-kpi-label {
    color: #68727d;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.055em;
    line-height: 1.2;
    text-transform: uppercase;
}
.strategy-kpi-value {
    color: #111820;
    font-size: 1.22rem;
    font-weight: 750;
    line-height: 1.25;
    margin-top: 0.34rem;
}
.strategy-note {
    color: #68727d;
    font-size: 0.78rem;
    line-height: 1.45;
    margin: 0.25rem 0 0.7rem 0;
}
@media (max-width: 1100px) {
    .strategy-card-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}
</style>
"""


@st.cache_data(show_spinner=False)
def _load_tables() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    return load_strategy_tables(DEFAULT_DB_PATH), load_metadata(DEFAULT_DB_PATH)


def render_tab_fidc_credit_strategy() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="strategy-header">
          <div class="strategy-kicker">FIDC Market Strategy</div>
          <div class="strategy-title">Matrizes regulatórias, subordinação e pricing por subtipo</div>
          <div class="strategy-subtitle">
            Base persistente para comparar fundos emitidos em 2024 versus 2025, separando leitura equal-weight,
            ponderação por PL atual e ponderação por volume emitido. A leitura é uma triagem analítica, não parecer jurídico.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not database_exists(DEFAULT_DB_PATH):
        _render_static_snapshot_fallback()
        return

    tables, metadata = _load_tables()
    fund_universe = tables["fund_universe"]
    heatmap_year = tables["regulatory_feature_heatmap_year"]
    subordination = tables["subordination_by_sector_year"]
    pricing = tables["pricing_senior_by_sector_year"]
    ime_subordination = tables.get("ime_current_subordination_by_sector_year", pd.DataFrame())
    opportunities = tables["market_opportunities"]
    ime_cache = tables["ime_cache_summary"]
    _render_kpis(fund_universe, pricing, opportunities, ime_cache, metadata)

    cohort = st.radio("Coorte", ["2024FY", "2025FY"], horizontal=True, key="strategy_cohort")
    available_sectors = sorted(
        s for s in heatmap_year.loc[heatmap_year["emission_cohort"] == cohort, "setor_n1"].dropna().unique() if str(s).strip()
    )
    selected_sectors = st.multiselect(
        "Filtrar setores",
        options=available_sectors,
        default=available_sectors[: min(6, len(available_sectors))],
        key="strategy_sector_filter",
    )
    if not selected_sectors:
        selected_sectors = available_sectors

    tabs = st.tabs(["Matriz tem/não tem", "Subordinação", "Pricing sênior", "Ideias comerciais", "Base"])
    with tabs[0]:
        _render_feature_heatmap(heatmap_year, cohort, selected_sectors)
    with tabs[1]:
        _render_subordination(subordination, ime_subordination, cohort, selected_sectors)
    with tabs[2]:
        _render_pricing(pricing, cohort, selected_sectors)
    with tabs[3]:
        _render_opportunities(opportunities, cohort, selected_sectors)
    with tabs[4]:
        _render_base_tables(tables)


def _render_static_snapshot_fallback() -> None:
    st.info(
        "Versão leve carregada: este ambiente não tem o SQLite completo de 212 MB, "
        "então a aba mostra o snapshot executivo committado no repositório."
    )
    if not _STATIC_REPORT_PATH.exists():
        st.warning(
            "Snapshot estático não encontrado. Rode `scripts/export_fidc_strategy_static_report.py` "
            "em um ambiente que tenha a base completa."
        )
        return
    html_report = _STATIC_REPORT_PATH.read_text(encoding="utf-8")
    st.download_button(
        "Baixar snapshot HTML",
        data=html_report,
        file_name="fidc_strategy_static_20260609.html",
        mime="text/html",
    )
    components.html(html_report, height=7200, scrolling=True)


def _render_kpis(
    fund_universe: pd.DataFrame,
    pricing: pd.DataFrame,
    opportunities: pd.DataFrame,
    ime_cache: pd.DataFrame,
    metadata: dict[str, str],
) -> None:
    funds = int(fund_universe["cnpj"].nunique()) if not fund_universe.empty else 0
    with_matrix = int(_num(fund_universe.get("has_regulatory_matrix")).fillna(0).sum()) if not fund_universe.empty else 0
    matrix_2024 = int((_bool_series(fund_universe.get("emitted_2024")) & _bool_series(fund_universe.get("has_regulatory_matrix"))).sum())
    matrix_2025 = int((_bool_series(fund_universe.get("emitted_2025")) & _bool_series(fund_universe.get("has_regulatory_matrix"))).sum())
    db_date = metadata.get("as_of_date", "")
    cards = [
        ("Data-base", db_date or "-"),
        ("CNPJs na base", f"{funds:,.0f}".replace(",", ".")),
        ("Matrizes lidas", f"{with_matrix:,.0f}".replace(",", ".")),
        ("Emitidos 2024/2025 com matriz", f"{matrix_2024:,.0f} / {matrix_2025:,.0f}".replace(",", ".")),
        ("Cortes pricing / ideias", f"{len(pricing):,.0f} / {len(opportunities):,.0f}".replace(",", ".")),
    ]
    html = "<div class='strategy-card-grid'>"
    for label, value in cards:
        html += (
            "<div class='strategy-kpi'>"
            f"<div class='strategy-kpi-label'>{escape(label)}</div>"
            f"<div class='strategy-kpi-value'>{escape(str(value))}</div>"
            "</div>"
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)
    st.caption(f"IME/cache granular disponível para {ime_cache['cnpj'].nunique() if not ime_cache.empty else 0} CNPJs. O PL amplo vem do cadastro CVM atualizado.")


def _render_feature_heatmap(frame: pd.DataFrame, cohort: str, sectors: list[str]) -> None:
    metric_options = {
        "Equal-weight: % de fundos": "feature_share",
        "Ponderado por PL atual": "pl_weighted_share",
        "Ponderado pelo volume emitido da coorte": "volume_cohort_weighted_share",
    }
    metric_label = st.selectbox("Métrica do heatmap", list(metric_options), key="strategy_heatmap_metric")
    metric = metric_options[metric_label]
    data = frame[(frame["emission_cohort"] == cohort) & frame["setor_n1"].isin(sectors)].copy()
    if data.empty:
        st.info("Sem dados para os filtros selecionados.")
        return
    data["subtipo"] = data["setor_n1"].astype(str) + " | " + data["setor_n2"].astype(str)
    data["share_pct"] = _num(data[metric]) * 100
    data["funds_num"] = _num(data["funds"])
    top_subtypes = (
        data[["subtipo", "funds_num"]].drop_duplicates().sort_values("funds_num", ascending=False).head(18)["subtipo"].tolist()
    )
    data = data[data["subtipo"].isin(top_subtypes)].copy()
    chart = (
        alt.Chart(data)
        .mark_rect(stroke="#ffffff", strokeWidth=1)
        .encode(
            x=alt.X("feature_label:N", title="", sort=list(data["feature_label"].drop_duplicates())),
            y=alt.Y("subtipo:N", title="", sort=top_subtypes),
            color=alt.Color("share_pct:Q", title="%", scale=alt.Scale(scheme="tealblues", domain=[0, 100])),
            tooltip=[
                alt.Tooltip("emission_cohort:N", title="Coorte"),
                alt.Tooltip("subtipo:N", title="Subtipo"),
                alt.Tooltip("feature_label:N", title="Cláusula"),
                alt.Tooltip("share_pct:Q", title="Frequência", format=".1f"),
                alt.Tooltip("funds:Q", title="Fundos"),
                alt.Tooltip("feature_count:Q", title="Com evidência"),
            ],
        )
        .properties(height=max(360, 26 * len(top_subtypes)))
    )
    st.altair_chart(chart, width="stretch")
    st.markdown("<div class='strategy-note'>Leitura equal-weight mostra o que é comum; PL/volume mostram onde a prática pesa em dinheiro.</div>", unsafe_allow_html=True)
    st.dataframe(_format_heatmap_table(data), hide_index=True, width="stretch")


def _render_subordination(frame: pd.DataFrame, ime_frame: pd.DataFrame, cohort: str, sectors: list[str]) -> None:
    data = frame[(frame["emission_cohort"] == cohort) & frame["setor_n1"].isin(sectors)].copy()
    if data.empty:
        st.info("Sem subordinação para os filtros selecionados.")
    else:
        data["subtipo"] = data["setor_n1"].astype(str) + " | " + data["setor_n2"].astype(str)
        data["pl_bi"] = _num(data["current_pl_total_brl"]) / 1e9
        data["volume_bi"] = _num(data["closed_issued_volume_brl"]) / 1e9
        data["median_pct"] = _num(data["subordination_median_equal_weight_pct"])
        data["pl_weighted_pct"] = _num(data["subordination_weighted_by_pl_pct"])
        data = data.sort_values("pl_bi", ascending=False).head(18)
        st.markdown("**Mínimo regulatório extraído dos regulamentos**")
        bars = (
            alt.Chart(data)
            .mark_bar(color="#355C7D", opacity=0.82)
            .encode(
                x=alt.X("subtipo:N", title="", sort=data["subtipo"].tolist(), axis=alt.Axis(labelAngle=-35)),
                y=alt.Y("pl_bi:Q", title="PL atual (R$ bi)"),
                tooltip=[alt.Tooltip("subtipo:N"), alt.Tooltip("pl_bi:Q", title="PL atual R$ bi", format=".2f")],
            )
        )
        points = (
            alt.Chart(data)
            .mark_point(color="#D66A2C", filled=True, size=95)
            .encode(
                x=alt.X("subtipo:N", sort=data["subtipo"].tolist()),
                y=alt.Y("median_pct:Q", title="Subordinação mediana (%)"),
                tooltip=[
                    alt.Tooltip("median_pct:Q", title="Mediana equal-weight", format=".1f"),
                    alt.Tooltip("pl_weighted_pct:Q", title="Ponderada PL", format=".1f"),
                    alt.Tooltip("coverage_pct:Q", title="Cobertura", format=".1f"),
                ],
            )
        )
        st.altair_chart(alt.layer(bars, points).resolve_scale(y="independent").properties(height=410), width="stretch")
        st.dataframe(_format_subordination_table(data), hide_index=True, width="stretch")

    _render_ime_subordination(ime_frame, cohort, sectors)


def _render_pricing(frame: pd.DataFrame, cohort: str, sectors: list[str]) -> None:
    data = frame[(frame["pricing_period"] == cohort) & frame["setor_n1"].isin(sectors)].copy()
    if data.empty:
        st.info("Sem pricing sênior para os filtros selecionados.")
    else:
        data["subtipo"] = data["setor_n1"].astype(str) + " | " + data["setor_n2"].astype(str)
        data["volume_bi"] = _num(data["volume_brl"]) / 1e9
        data["median_spread"] = _num(data["spread_cdi_median_equal_weight_aa"])
        data["volume_weighted"] = _num(data["spread_cdi_weighted_by_issue_volume_aa"])
        data["pl_weighted"] = _num(data["spread_cdi_weighted_by_current_pl_aa"])
        data = data.sort_values("volume_bi", ascending=False).head(18)
        st.markdown("**Remuneração de cotas seniores extraída das emissões/documentos**")
        bar = (
            alt.Chart(data)
            .mark_bar(color="#C66A32", opacity=0.86)
            .encode(
                x=alt.X("subtipo:N", title="", sort=data["subtipo"].tolist(), axis=alt.Axis(labelAngle=-35)),
                y=alt.Y("volume_bi:Q", title="Volume sênior mapeado (R$ bi)"),
                tooltip=[alt.Tooltip("subtipo:N"), alt.Tooltip("volume_bi:Q", title="Volume R$ bi", format=".2f")],
            )
        )
        dot = (
            alt.Chart(data)
            .mark_point(color="#1B7F7A", filled=True, size=95)
            .encode(
                x=alt.X("subtipo:N", sort=data["subtipo"].tolist()),
                y=alt.Y("median_spread:Q", title="CDI+ mediano a.a."),
                tooltip=[
                    alt.Tooltip("median_spread:Q", title="Mediana equal-weight", format=".2f"),
                    alt.Tooltip("volume_weighted:Q", title="Pond. volume", format=".2f"),
                    alt.Tooltip("pl_weighted:Q", title="Pond. PL", format=".2f"),
                    alt.Tooltip("spread_cdi_coverage_pct:Q", title="Cobertura spread", format=".1f"),
                ],
            )
        )
        st.altair_chart(alt.layer(bar, dot).resolve_scale(y="independent").properties(height=410), width="stretch")
        st.dataframe(_format_pricing_table(data), hide_index=True, width="stretch")

def _render_ime_subordination(frame: pd.DataFrame, cohort: str, sectors: list[str]) -> None:
    if frame.empty:
        return
    data = frame[(frame["emission_cohort"] == cohort) & frame["setor_n1"].isin(sectors)].copy()
    if data.empty:
        return
    data["subtipo"] = data["setor_n1"].astype(str) + " | " + data["setor_n2"].astype(str)
    data["pl_bi"] = _num(data["current_ime_pl_total_brl"]) / 1e9
    data["actual_median_pct"] = _num(data["actual_subordination_median_equal_weight_pct"])
    data["actual_pl_weighted_pct"] = _num(data["actual_subordination_weighted_by_current_ime_pl_pct"])
    data = data.sort_values("pl_bi", ascending=False).head(18)
    st.markdown("**Subordinação atual observada no Informe Mensal CVM**")
    bars = (
        alt.Chart(data)
        .mark_bar(color="#2B6F6C", opacity=0.82)
        .encode(
            x=alt.X("subtipo:N", title="", sort=data["subtipo"].tolist(), axis=alt.Axis(labelAngle=-35)),
            y=alt.Y("pl_bi:Q", title="PL IME atual (R$ bi)"),
            tooltip=[alt.Tooltip("subtipo:N"), alt.Tooltip("pl_bi:Q", title="PL IME R$ bi", format=".2f")],
        )
    )
    points = (
        alt.Chart(data)
        .mark_point(color="#B24D5A", filled=True, size=95)
        .encode(
            x=alt.X("subtipo:N", sort=data["subtipo"].tolist()),
            y=alt.Y("actual_median_pct:Q", title="Subordinação IME mediana (%)"),
            tooltip=[
                alt.Tooltip("actual_median_pct:Q", title="Mediana equal-weight", format=".1f"),
                alt.Tooltip("actual_pl_weighted_pct:Q", title="Ponderada PL IME", format=".1f"),
                alt.Tooltip("coverage_pct:Q", title="Cobertura IME", format=".1f"),
            ],
        )
    )
    st.altair_chart(alt.layer(bars, points).resolve_scale(y="independent").properties(height=410), width="stretch")
    st.dataframe(_format_ime_subordination_table(data), hide_index=True, width="stretch")


def _render_opportunities(frame: pd.DataFrame, cohort: str, sectors: list[str]) -> None:
    data = frame[(frame["periodo"] == cohort) & frame["setor_n1"].isin(sectors)].copy()
    if data.empty:
        st.info("Sem ideias automáticas para os filtros selecionados.")
        return
    st.dataframe(_format_opportunity_table(data), hide_index=True, width="stretch")


def _render_base_tables(tables: dict[str, pd.DataFrame]) -> None:
    st.markdown("Base SQLite persistente:")
    st.code(str(DEFAULT_DB_PATH))
    if Path(DEFAULT_DB_PATH).exists():
        st.download_button(
            "Baixar SQLite",
            data=Path(DEFAULT_DB_PATH).read_bytes(),
            file_name="fidc_credit_strategy.sqlite",
            mime="application/octet-stream",
        )
    table_name = st.selectbox(
        "Tabela",
        [
            "fund_universe",
            "subordination_by_sector_year",
            "pricing_senior_by_sector_year",
            "ime_current_subordination_by_sector_year",
            "ime_current_snapshot",
            "ime_cota_movements",
            "regulatory_feature_heatmap_year",
            "market_opportunities",
            "manual_review_queue",
        ],
        key="strategy_table_select",
    )
    frame = tables.get(table_name)
    if frame is None:
        frame = load_table(table_name, DEFAULT_DB_PATH)
    st.dataframe(frame.head(500), hide_index=True, width="stretch")


def _num(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(series, errors="coerce")


def _bool_series(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype=bool)
    if series.dtype == bool:
        return series.fillna(False)
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().any():
        return numeric.fillna(0) != 0
    return series.astype(str).str.lower().isin({"true", "1", "sim", "yes"})


def _money_bi(value: object) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return ""
    return f"R$ {number / 1e9:,.2f} bi".replace(",", "_").replace(".", ",").replace("_", ".")


def _pct(value: object) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return ""
    return f"{number:.1f}%".replace(".", ",")


def _format_heatmap_table(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame[["emission_cohort", "setor_n1", "setor_n2", "feature_label", "funds", "feature_count", "share_pct"]].copy()
    out.columns = ["Coorte", "Setor", "Subtipo", "Cláusula", "Fundos", "Com evidência", "Frequência"]
    out["Frequência"] = out["Frequência"].map(_pct)
    return out.sort_values(["Setor", "Subtipo", "Cláusula"])


def _format_subordination_table(frame: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "emission_cohort",
        "setor_n1",
        "setor_n2",
        "funds_total",
        "funds_with_subordination_pct",
        "coverage_pct",
        "subordination_median_equal_weight_pct",
        "subordination_weighted_by_pl_pct",
        "subordination_weighted_by_issued_volume_pct",
        "current_pl_total_brl",
        "estimated_subordination_capital_brl",
    ]
    out = frame[cols].copy()
    out.columns = ["Coorte", "Setor", "Subtipo", "Fundos", "Com % subord.", "Cobertura", "Mediana EW", "Pond. PL", "Pond. volume", "PL atual", "Subord. estimada"]
    for col in ["Cobertura", "Mediana EW", "Pond. PL", "Pond. volume"]:
        out[col] = out[col].map(_pct)
    for col in ["PL atual", "Subord. estimada"]:
        out[col] = out[col].map(_money_bi)
    return out


def _format_pricing_table(frame: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "pricing_period",
        "setor_n1",
        "setor_n2",
        "senior_tranche_rows",
        "funds",
        "volume_brl",
        "spread_cdi_coverage_pct",
        "spread_cdi_median_equal_weight_aa",
        "spread_cdi_weighted_by_issue_volume_aa",
        "spread_cdi_weighted_by_current_pl_aa",
    ]
    out = frame[cols].copy()
    out.columns = ["Período", "Setor", "Subtipo", "Linhas", "Fundos", "Volume", "Cobertura CDI+", "Mediana CDI+", "Pond. volume", "Pond. PL"]
    out["Volume"] = out["Volume"].map(_money_bi)
    for col in ["Cobertura CDI+", "Mediana CDI+", "Pond. volume", "Pond. PL"]:
        out[col] = out[col].map(_pct)
    return out


def _format_ime_subordination_table(frame: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "emission_cohort",
        "setor_n1",
        "setor_n2",
        "funds_total",
        "funds_with_ime_quota_structure",
        "coverage_pct",
        "actual_subordination_median_equal_weight_pct",
        "actual_subordination_weighted_by_current_ime_pl_pct",
        "actual_subordination_weighted_by_quota_nav_pct",
        "current_ime_pl_total_brl",
        "senior_quota_nav_total_brl",
        "subordinated_plus_mezz_nav_total_brl",
    ]
    out = frame[cols].copy()
    out.columns = ["Coorte", "Setor", "Subtipo", "Fundos", "Com estrutura IME", "Cobertura", "Mediana EW", "Pond. PL IME", "Pond. cotas", "PL IME", "Cotas senior", "Sub+mez"]
    for col in ["Cobertura", "Mediana EW", "Pond. PL IME", "Pond. cotas"]:
        out[col] = out[col].map(_pct)
    for col in ["PL IME", "Cotas senior", "Sub+mez"]:
        out[col] = out[col].map(_money_bi)
    return out


def _format_opportunity_table(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame[["tema", "periodo", "setor_n1", "setor_n2", "sinal", "ideia_estrutura", "materialidade_brl"]].copy()
    out.columns = ["Tema", "Período", "Setor", "Subtipo", "Sinal", "Ideia estrutural/comercial", "Materialidade"]
    out["Materialidade"] = out["Materialidade"].map(_money_bi)
    return out
