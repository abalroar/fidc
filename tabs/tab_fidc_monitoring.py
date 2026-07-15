from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import time
from typing import Any

import pandas as pd
import streamlit as st

from services.fundonet_dashboard import build_dashboard_data
from services.ime_loader import load_or_extract_informe, peek_cached_informe
from services.ime_period import (
    ImePeriodSelection,
    build_custom_period,
    build_preset_period,
    current_default_end_month,
    display_month_count_for_period,
    parse_competencia_label,
    select_competencia_labels_for_period,
    shift_month,
)
from services.monitoring_metrics import (
    MonitoringTables,
    build_monitoring_tables,
    load_manual_overrides,
    read_wide_csv,
)
from services.portfolio_store import PortfolioRecord
from services.regulatory_knowledge import (
    common_criteria_summary,
    document_inventory_rows,
    emission_rows,
    extracted_criteria_rows,
    knowledge_summary_rows,
    load_regulatory_knowledge,
    normalize_cnpj,
)
from services.regulatory_profiles import (
    CuratedRegulatoryProfile,
    load_regulatory_profile,
    payment_calendar_rows,
)
from services.variaveis_fnet import competencia_columns, resolve_tag_path
from tabs.ime_portfolio_support import (
    build_portfolio_record_label_lookup,
    list_saved_portfolios,
    normalize_portfolio_fund_name,
)


_CACHE_MONTH_OPTIONS = (12, 15, 18, 24, 36, 48, 60, 72)
_MONITORING_DERIVED_CACHE_VERSION = 2
_MONITORING_DERIVED_CACHE_ROOT = Path(".cache/fundonet-monitoring")
_CORE_AVAILABILITY_IDS = (
    "PATRLIQ/VL_SOM_PATRLIQ",
    "PATRLIQ/VL_PATRIM_LIQ",
    "APLIC_ATIVO/VL_SOM_APLIC_ATIVO",
    "APLIC_ATIVO/VL_CARTEIRA",
)
@dataclass(frozen=True)
class CockpitMetric:
    section: str
    label: str
    indicator: str
    unit: str
    aggregate: str


_COCKPIT_METRICS: tuple[CockpitMetric, ...] = (
    CockpitMetric("Tamanho e alocação", "PL", "PL (R$)", "R$ bruto", "sum"),
    CockpitMetric("Tamanho e alocação", "Direitos creditórios", "Dir Cred (R$ MM)", "R$ MM", "sum"),
    CockpitMetric("Tamanho e alocação", "Direitos creditórios / PL", "Dir Cred / PL", "ratio", "dircred_pl"),
    CockpitMetric("Inadimplência", "Over 30d / Crédito", "Vencidos Over 30 d / Crédito", "ratio", "over30_credito"),
    CockpitMetric("Inadimplência", "Over 60d / Crédito", "Vencidos Over 60 d / Crédito", "ratio", "over60_credito"),
    CockpitMetric("Inadimplência", "Over 90d / Crédito", "Vencidos Over 90 d / Crédito", "ratio", "over90_credito"),
    CockpitMetric("Inadimplência", "Over 180d / Crédito", "Vencidos Over 180 d / Crédito", "ratio", "over180_credito"),
    CockpitMetric("Inadimplência", "Over 360d / Crédito", "Vencidos Over 360 d / Crédito", "ratio", "over360_credito"),
    CockpitMetric("PDD e recompras", "PDD", "PDD (R$ MM)", "R$ MM", "sum"),
    CockpitMetric("PDD e recompras", "PDD / Crédito", "PDD / Crédito", "ratio", "pdd_credito"),
    CockpitMetric("PDD e recompras", "PDD / Over 90d", "PDD / Venc > 90 d", "ratio", "pdd_over90"),
    CockpitMetric("PDD e recompras", "Recompras / Crédito", "Recompras / Crédito", "ratio", "recompras_credito"),
    CockpitMetric("Cotas e retorno", "Cotas SR / PL", "Cotas SR / PL %", "%", "weighted_pl"),
    CockpitMetric("Cotas e retorno", "Cotas MZ / PL", "Cotas MZ / PL %", "%", "weighted_pl"),
    CockpitMetric("Cotas e retorno", "Cotas Sub / PL", "Cotas Sub / PL %", "%", "weighted_pl"),
    CockpitMetric("Cotas e retorno", "Rentabilidade SR a.m.", "Rentabilidade SR % a.m.", "%", "none"),
    CockpitMetric("Cotas e retorno", "Rentabilidade MZ a.m.", "Rentabilidade MZ % a.m.", "%", "none"),
    CockpitMetric("Cotas e retorno", "Rentabilidade Sub a.m.", "Rentabilidade Sub % a.m.", "%", "none"),
)


_CSS = """
<style>
.monitor-card-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0.35rem 0 0.7rem 0;
}
.monitor-chip {
    align-items: center;
    background: #f8f9fa;
    border: 1px solid #eceff3;
    border-radius: 999px;
    color: #5a5a5a;
    display: inline-flex;
    font-size: 0.74rem;
    gap: 5px;
    line-height: 1.2;
    padding: 5px 9px;
}
.monitor-chip strong {
    color: #212529;
    font-weight: 600;
}
.monitor-card-grid {
    display: grid;
    gap: 8px;
    grid-template-columns: repeat(6, minmax(110px, 1fr));
    margin: 0.55rem 0 0.75rem 0;
}
.monitor-kpi-card {
    background: #F7F7F7;
    border: 1px solid #E5E5E5;
    border-radius: 6px;
    min-height: 64px;
    padding: 8px 10px;
}
.monitor-kpi-label {
    color: #6B6B6B;
    font-size: 0.67rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    line-height: 1.15;
    text-transform: uppercase;
}
.monitor-kpi-value {
    color: #1F1F1F;
    font-size: 1.05rem;
    font-weight: 700;
    line-height: 1.25;
    margin-top: 6px;
}
.monitor-kpi-note {
    color: #8C8C8C;
    font-size: 0.68rem;
    line-height: 1.2;
    margin-top: 2px;
}
.monitor-wide-wrapper {
    overflow-x: auto;
    overflow-y: visible;
    max-width: 100%;
    padding-bottom: 5px;
    margin-bottom: 12px;
}
.monitor-wide-section {
    margin: 0 0 8px 0;
}
.monitor-wide-section summary {
    background: #000000;
    color: #FFFFFF;
    cursor: pointer;
    font-size: 13px;
    font-weight: 700;
    line-height: 1.25;
    list-style-position: inside;
    padding: 7px 9px;
    white-space: normal;
}
.monitor-wide-table {
    border-collapse: collapse;
    font-family: inherit;
    font-size: 12px;
    table-layout: fixed;
    width: 100%;
}
.monitor-wide-table th {
    background: #FFFFFF;
    border-bottom: 1px solid #3F3F3F;
    color: #000000;
    font-weight: 600;
    line-height: 1.15;
    overflow-wrap: anywhere;
    padding: 6px 8px;
    position: sticky;
    text-align: right;
    top: 0;
    white-space: normal;
    word-break: normal;
    z-index: 2;
}
.monitor-wide-table th.label-col,
.monitor-wide-table td.label {
    text-align: left;
}
.monitor-wide-table td {
    border-bottom: 1px solid #E5E5E5;
    color: #3F3F3F;
    line-height: 1.22;
    overflow-wrap: anywhere;
    padding: 4px 8px;
    text-align: right;
    vertical-align: top;
    white-space: normal;
    word-break: normal;
}
.monitor-wide-table td.label {
    color: #000000;
    font-weight: 500;
    padding-left: 14px;
}
.monitor-wide-table tr.destaque td {
    color: #000000;
    font-weight: 700;
}
.monitor-wide-table tr:hover td {
    background: #F4F1EA;
}
.monitor-fund-title {
    color: #1f1f1f;
    font-size: 1.02rem;
    font-weight: 700;
    line-height: 1.25;
    margin: 0.35rem 0 0.1rem 0;
}
.monitor-caption {
    color: #6f7a87;
    font-size: 0.78rem;
    line-height: 1.35;
    margin-bottom: 0.45rem;
}
@media (max-width: 1100px) {
    .monitor-card-grid {
        grid-template-columns: repeat(3, minmax(110px, 1fr));
    }
}
</style>
"""

_PT_MONTH_ABBR = {
    "01": "jan",
    "02": "fev",
    "03": "mar",
    "04": "abr",
    "05": "mai",
    "06": "jun",
    "07": "jul",
    "08": "ago",
    "09": "set",
    "10": "out",
    "11": "nov",
    "12": "dez",
}


def _render_monitoring_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def render_tab_fidc_monitoring(
    period: ImePeriodSelection | None = None,
    *,
    selected_portfolio: PortfolioRecord | None = None,
    show_portfolio_selector: bool = True,
    use_tabs: bool = True,
) -> None:
    _render_monitoring_css()
    if show_portfolio_selector:
        st.markdown("## Monitoramento FIDCs")
    if period is None:
        period = build_preset_period(end_month=current_default_end_month(), months=12)

    if selected_portfolio is None:
        portfolios = list_saved_portfolios()
        if not portfolios:
            st.info("Crie uma carteira salva nas abas de carteira/Soma de FIDCs para usar o monitoramento.")
            return
        selected_portfolio = _render_portfolio_selector(portfolios)
    if selected_portfolio is None:
        return

    cache_months = (
        _render_cache_horizon_control(selected_portfolio=selected_portfolio, period=period)
        if show_portfolio_selector
        else _default_cache_months_for_period(period)
    )
    load_period = _build_cache_load_period(period=period, cache_months=cache_months)

    session_key = _session_key(selected_portfolio, period, cache_months)
    if session_key not in st.session_state:
        st.session_state[session_key] = _load_portfolio_monitoring(selected_portfolio, period, cache_months)

    outputs = st.session_state.get(session_key) or []
    regulatory_outputs = _regulatory_outputs_for_portfolio(selected_portfolio, outputs)
    if not outputs:
        st.info("A carteira ainda não possui dados de monitoramento para este período.")
        _render_regulatory_base_tab(regulatory_outputs)
        return

    success_outputs = [item for item in outputs if item.get("tables") is not None]
    error_outputs = [item for item in outputs if item.get("error")]
    if error_outputs:
        with st.expander("Fundos com falha de carga", expanded=False):
            for item in error_outputs:
                st.caption(f"**{item['display_name']}** · {item['cnpj']} — {item['error']}")
    if not success_outputs:
        st.warning("Nenhum fundo carregou dados suficientes para montar o monitoramento.")
        _render_regulatory_base_tab(regulatory_outputs)
        return

    if use_tabs:
        cockpit_tab, regulatory_tab = st.tabs(["Cockpit", "Regulatório"])
        with cockpit_tab:
            _render_cockpit_tab(success_outputs)
        with regulatory_tab:
            _render_regulatory_base_tab(regulatory_outputs)
        return

    st.markdown("### Base regulatória")
    _render_regulatory_base_tab(regulatory_outputs, compact=True)


def render_portfolio_cockpit_snapshot(
    *,
    period: ImePeriodSelection | None,
    selected_portfolio: PortfolioRecord,
    selected_cnpjs: set[str] | None = None,
) -> bool:
    """Render the compact per-fund monitoring snapshot inside another page section."""
    _render_monitoring_css()
    if period is None:
        period = build_preset_period(end_month=current_default_end_month(), months=12)
    cache_months = _default_cache_months_for_period(period)
    session_key = _session_key(selected_portfolio, period, cache_months)
    if session_key not in st.session_state:
        st.session_state[session_key] = _load_portfolio_monitoring(selected_portfolio, period, cache_months)
    outputs = st.session_state.get(session_key) or []
    success_outputs = [item for item in outputs if item.get("tables") is not None]
    if selected_cnpjs is not None:
        success_outputs = [
            item for item in success_outputs if str(item.get("cnpj") or "") in selected_cnpjs
        ]
    if not success_outputs:
        st.caption("Sem indicadores por fundo para a competência de referência.")
        return False
    _render_cockpit_tab(success_outputs)
    return True


def _render_portfolio_selector(portfolios: list[PortfolioRecord]) -> PortfolioRecord | None:
    labels = build_portfolio_record_label_lookup(portfolios)
    portfolio_id = st.selectbox(
        "Carteira",
        options=[portfolio.id for portfolio in portfolios],
        format_func=lambda value: labels.get(value, value),
        key="monitoring_portfolio_id",
    )
    return next((portfolio for portfolio in portfolios if portfolio.id == portfolio_id), None)


def _render_cache_horizon_control(*, selected_portfolio: PortfolioRecord, period: ImePeriodSelection) -> int:
    target_months = display_month_count_for_period(period)
    recommended = _default_cache_months_for_period(period)
    options = sorted({*_CACHE_MONTH_OPTIONS, recommended, target_months})
    default_index = options.index(recommended)
    key = f"monitoring_cache_months::{selected_portfolio.id}"
    return int(
        st.selectbox(
            "Histórico do cache",
            options=options,
            index=default_index,
            format_func=lambda value: f"{value} meses",
            key=key,
            help="Meses lidos do cache local.",
        )
    )


def _default_cache_months_for_period(period: ImePeriodSelection) -> int:
    return max(display_month_count_for_period(period) + 3, 15)


def _build_cache_load_period(*, period: ImePeriodSelection, cache_months: int) -> ImePeriodSelection:
    cache_months = max(int(cache_months), display_month_count_for_period(period))
    return build_custom_period(
        start_month=shift_month(period.end_month, -(cache_months - 1)),
        end_month=period.end_month,
    )


def _load_portfolio_monitoring(portfolio: PortfolioRecord, period: ImePeriodSelection, cache_months: int) -> list[dict[str, Any]]:
    progress = st.progress(0.0, text="Preparando monitoramento...")
    outputs: list[dict[str, Any]] = []
    total = len(portfolio.funds)
    load_period = _build_cache_load_period(period=period, cache_months=cache_months)
    cached_count = sum(
        1
        for fund in portfolio.funds
        if peek_cached_informe(
            cnpj_fundo=fund.cnpj,
            data_inicial=load_period.start_month,
            data_final=load_period.end_month,
        ).is_cached
    )
    worker_count = min(10, total) if cached_count == total else min(4, total)
    with ThreadPoolExecutor(max_workers=max(worker_count, 1)) as executor:
        futures = {
            executor.submit(_load_single_monitoring_fund, fund, period, load_period): fund
            for fund in portfolio.funds
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            fund = futures[future]
            progress.progress(completed / max(total, 1), text=f"{completed}/{total} · {fund.display_name}")
            try:
                outputs.append(future.result())
            except Exception as exc:  # noqa: BLE001
                outputs.append(
                    {
                        "cnpj": fund.cnpj,
                        "display_name": normalize_portfolio_fund_name(fund.display_name, fund.cnpj),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    progress.empty()
    return outputs


def _load_single_monitoring_fund(
    fund,  # noqa: ANN001
    period: ImePeriodSelection,
    load_period: ImePeriodSelection,
) -> dict[str, Any]:
    fund_started = time.perf_counter()
    cached = load_or_extract_informe(
        cnpj_fundo=fund.cnpj,
        data_inicial=load_period.start_month,
        data_final=load_period.end_month,
    )
    wide_df = read_wide_csv(cached.result.wide_csv_path)
    all_competencias = _available_competencias_from_wide(wide_df)
    competencias = select_competencia_labels_for_period(all_competencias, period) or all_competencias
    overrides = load_manual_overrides(fund.cnpj)
    tables, metric_source, dashboard_error, derived_cache_status = _load_or_build_monitoring_tables(
        wide_df=wide_df,
        cnpj=fund.cnpj,
        competencias=competencias,
        overrides=overrides,
        ime_cache_key=cached.cache_key,
        wide_csv_path=cached.result.wide_csv_path,
        listas_csv_path=cached.result.listas_csv_path,
        docs_csv_path=cached.result.docs_csv_path,
    )
    return {
        "cnpj": fund.cnpj,
        "display_name": normalize_portfolio_fund_name(fund.display_name, fund.cnpj),
        "competencias": competencias,
        "all_competencias": all_competencias,
        "tables": tables,
        "cache_status": cached.cache_status,
        "derived_cache_status": derived_cache_status,
        "cache_dir": str(cached.cache_dir),
        "load_period_label": _format_period_label(load_period),
        "metric_source": metric_source,
        "dashboard_error": dashboard_error,
        "load_seconds": round(time.perf_counter() - fund_started, 3),
    }


def _regulatory_outputs_for_portfolio(portfolio: PortfolioRecord, outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_cnpj: dict[str, dict[str, Any]] = {}
    for item in outputs:
        cnpj = normalize_cnpj(str(item.get("cnpj") or ""))
        if not cnpj:
            continue
        normalized = dict(item)
        normalized["cnpj"] = cnpj
        normalized["display_name"] = normalize_portfolio_fund_name(str(item.get("display_name") or cnpj), cnpj)
        by_cnpj[cnpj] = normalized

    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fund in portfolio.funds:
        cnpj = normalize_cnpj(fund.cnpj)
        if not cnpj:
            continue
        item = by_cnpj.get(cnpj)
        if item is None:
            item = {
                "cnpj": cnpj,
                "display_name": normalize_portfolio_fund_name(fund.display_name, cnpj),
            }
        ordered.append(item)
        seen.add(cnpj)

    ordered.extend(item for cnpj, item in by_cnpj.items() if cnpj not in seen)
    return ordered


def _load_or_build_monitoring_tables(
    *,
    wide_df: pd.DataFrame,
    cnpj: str,
    competencias: list[str],
    overrides: dict[str, Any],
    ime_cache_key: str,
    wide_csv_path: Path,
    listas_csv_path: Path,
    docs_csv_path: Path,
) -> tuple[MonitoringTables, str, str, str]:
    cache_key = _monitoring_derived_cache_key(
        cnpj=cnpj,
        ime_cache_key=ime_cache_key,
        competencias=competencias,
        overrides=overrides,
    )
    cached = _read_monitoring_derived_cache(cache_key)
    if cached is not None:
        return cached

    dashboard_data = None
    dashboard_error = ""
    try:
        dashboard_data = build_dashboard_data(
            wide_csv_path=wide_csv_path,
            listas_csv_path=listas_csv_path,
            docs_csv_path=docs_csv_path,
        )
    except Exception as dashboard_exc:  # noqa: BLE001
        dashboard_error = f"{type(dashboard_exc).__name__}: {dashboard_exc}"
    tables = build_monitoring_tables(
        wide_df,
        competencias,
        cnpj=cnpj,
        overrides=overrides,
        dashboard_data=dashboard_data,
    )
    metric_source = "Visão Executiva canônica" if dashboard_data is not None else "Campos escalares IME"
    _write_monitoring_derived_cache(
        cache_key=cache_key,
        tables=tables,
        metric_source=metric_source,
        dashboard_error=dashboard_error,
    )
    return tables, metric_source, dashboard_error, "miss"


def _monitoring_derived_cache_key(
    *,
    cnpj: str,
    ime_cache_key: str,
    competencias: list[str],
    overrides: dict[str, Any],
) -> str:
    payload = {
        "schema_version": _MONITORING_DERIVED_CACHE_VERSION,
        "cnpj": "".join(ch for ch in str(cnpj) if ch.isdigit()),
        "ime_cache_key": ime_cache_key,
        "competencias": list(competencias),
        "overrides": overrides or {},
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _read_monitoring_derived_cache(cache_key: str) -> tuple[MonitoringTables, str, str, str] | None:
    cache_dir = _MONITORING_DERIVED_CACHE_ROOT / cache_key
    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(manifest.get("schema_version") or 0) != _MONITORING_DERIVED_CACHE_VERSION:
        return None
    files = manifest.get("files") or {}
    required = {"raw_variables_df", "indicators_df", "aging_df", "audit_df"}
    if not required.issubset(files):
        return None
    paths = {key: cache_dir / str(value) for key, value in files.items()}
    if not all(paths[key].exists() for key in required):
        return None
    try:
        tables = MonitoringTables(
            raw_variables_df=pd.read_csv(paths["raw_variables_df"], dtype=str, keep_default_na=False),
            indicators_df=pd.read_csv(paths["indicators_df"], dtype=str, keep_default_na=False),
            aging_df=pd.read_csv(paths["aging_df"], dtype=str, keep_default_na=False),
            audit_df=pd.read_csv(paths["audit_df"], dtype=str, keep_default_na=False),
        )
    except (OSError, pd.errors.ParserError):
        return None
    return (
        tables,
        str(manifest.get("metric_source") or "cache derivado"),
        str(manifest.get("dashboard_error") or ""),
        "hit",
    )


def _write_monitoring_derived_cache(
    *,
    cache_key: str,
    tables: MonitoringTables,
    metric_source: str,
    dashboard_error: str,
) -> None:
    cache_dir = _MONITORING_DERIVED_CACHE_ROOT / cache_key
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_map = {
        "raw_variables_df": "raw_variables.csv",
        "indicators_df": "indicators.csv",
        "aging_df": "aging.csv",
        "audit_df": "audit.csv",
    }
    tables.raw_variables_df.to_csv(cache_dir / file_map["raw_variables_df"], index=False)
    tables.indicators_df.to_csv(cache_dir / file_map["indicators_df"], index=False)
    tables.aging_df.to_csv(cache_dir / file_map["aging_df"], index=False)
    tables.audit_df.to_csv(cache_dir / file_map["audit_df"], index=False)
    manifest = {
        "schema_version": _MONITORING_DERIVED_CACHE_VERSION,
        "metric_source": metric_source,
        "dashboard_error": dashboard_error,
        "files": file_map,
    }
    (cache_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _available_competencias_from_wide(wide_df: pd.DataFrame) -> list[str]:
    competencias = competencia_columns(wide_df)
    if not competencias:
        return []
    core_paths = [resolve_tag_path(short_id, wide_df) for short_id in _CORE_AVAILABILITY_IDS]
    core_paths = [path for path in core_paths if path and path in wide_df.index]
    if not core_paths:
        return competencias

    available: list[str] = []
    for competencia in competencias:
        values = []
        for path in core_paths:
            row = wide_df.loc[path]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            values.append(row.get(competencia))
        numeric = pd.to_numeric(pd.Series(values), errors="coerce")
        if numeric.notna().any():
            available.append(competencia)
    return available or competencias


def _render_cockpit_tab(outputs: list[dict[str, Any]]) -> None:
    reference, reference_count, reference_total = _portfolio_reference_competencia(
        outputs,
        min_coverage_pct=1.0,
    )
    if not reference:
        st.info("Não há competência disponível para montar o cockpit.")
        return
    if reference_count < reference_total:
        st.warning(
            "Sem competência comum a 100% dos fundos selecionados; o comparativo mais recente foi omitido "
            "para não apresentar um consolidado parcial."
        )
        return
    st.markdown(_render_cockpit_table_html(outputs, reference), unsafe_allow_html=True)


def _render_regulatory_base_tab(outputs: list[dict[str, Any]], *, compact: bool = False) -> None:
    loaded = []
    missing = []
    profiles: dict[str, CuratedRegulatoryProfile] = {}
    for item in outputs:
        cnpj = str(item.get("cnpj") or "")
        knowledge = load_regulatory_knowledge(cnpj)
        if knowledge is None:
            missing.append(item)
        else:
            loaded.append(knowledge)
        profile = load_regulatory_profile(cnpj)
        if profile is not None and profile.available:
            profiles[profile.cnpj] = profile

    if not loaded and not profiles:
        st.info("Base regulatória ainda não gerada para esta carteira.")
        st.code("python3 scripts/build_regulatory_knowledge.py", language="bash")
        return

    if loaded:
        st.dataframe(pd.DataFrame(knowledge_summary_rows(loaded)), hide_index=True, use_container_width=True)
    else:
        st.caption("Esta carteira só possui perfis regulatórios curados locais.")

    common = common_criteria_summary(loaded)
    if common:
        with st.expander("Critérios recorrentes na carteira", expanded=False):
            st.dataframe(pd.DataFrame(common), hide_index=True, use_container_width=True)

    options = sorted(
        {item.cnpj for item in loaded} | set(profiles),
        key=lambda cnpj: _regulatory_fund_label(cnpj, loaded, outputs),
    )
    by_cnpj = {item.cnpj: item for item in loaded}
    by_output = {normalize_cnpj(str(item.get("cnpj") or "")): item for item in outputs}
    selected_cnpj = st.selectbox(
        "Fundo",
        options=options,
        format_func=lambda cnpj: _regulatory_fund_label(cnpj, loaded, outputs),
        key="monitoring_regulatory_fund",
    )
    selected = by_cnpj.get(selected_cnpj)
    selected_output = by_output.get(selected_cnpj)
    profile = profiles.get(selected_cnpj)

    criteria_df = _selected_criteria_df(selected, profile)
    emissions_df = _selected_emissions_df(selected, profile)
    inventory_df = pd.DataFrame(document_inventory_rows(selected)) if selected is not None else pd.DataFrame()
    timeline_df = (
        inventory_df[inventory_df["Tipo"].isin(["regulamento", "assembleia", "emissao", "evento"])]
        if not inventory_df.empty and "Tipo" in inventory_df
        else pd.DataFrame()
    )

    if selected_output is not None and selected_output.get("tables") is not None and profile is not None and not profile.criteria_df.empty:
        st.markdown("#### Monitoramento IME")
        checks_df = _build_regulatory_monitoring_checks(selected_output, profile.criteria_df)
        if checks_df.empty:
            st.caption("Sem critério curado com proxy IME para a competência carregada.")
        else:
            st.dataframe(checks_df, hide_index=True, use_container_width=True)
    elif profile is not None and not profile.criteria_df.empty:
        st.markdown("#### Monitoramento IME")
        st.caption("Base regulatória disponível; carregue o IME da carteira para calcular os checks monitoráveis do período.")

    st.markdown("#### Emissões e calendário de pagamentos")
    calendar_df = pd.DataFrame(payment_calendar_rows(profile.emissions_df)) if profile is not None else pd.DataFrame()
    if emissions_df.empty and calendar_df.empty:
        st.caption("Nenhum evento de emissão, juros ou amortização extraído dos documentos processados.")
    else:
        if not emissions_df.empty:
            st.dataframe(_drop_selected_fund_columns(emissions_df), hide_index=True, use_container_width=True)
        _ = calendar_df

    st.markdown("#### Critérios monitoráveis e qualitativos")
    extraction_errors = selected.payload.get("extraction_errors") if selected is not None else []
    if extraction_errors:
        st.warning(f"{len(extraction_errors)} documento(s) ainda sem extração estruturada.")
    if criteria_df.empty:
        st.caption("Nenhum threshold extraído para este fundo até agora.")
    else:
        st.dataframe(_drop_selected_fund_columns(criteria_df), hide_index=True, use_container_width=True)

    _ = timeline_df, inventory_df

    if missing:
        with st.expander("Fundos sem base gerada", expanded=False):
            for item in missing:
                st.caption(str(item.get("display_name") or item.get("cnpj") or "-"))


def _regulatory_fund_label(cnpj: str, loaded: list[Any], outputs: list[dict[str, Any]]) -> str:
    digits = normalize_cnpj(cnpj)
    for item in loaded:
        if item.cnpj == digits:
            return item.fund_name
    for item in outputs:
        if normalize_cnpj(str(item.get("cnpj") or "")) == digits:
            return str(item.get("display_name") or cnpj)
    return cnpj


def _selected_criteria_df(selected: Any | None, profile: CuratedRegulatoryProfile | None) -> pd.DataFrame:
    if profile is not None and not profile.criteria_df.empty:
        return profile.criteria_df.copy()
    return pd.DataFrame(extracted_criteria_rows(selected)) if selected is not None else pd.DataFrame()


def _selected_emissions_df(selected: Any | None, profile: CuratedRegulatoryProfile | None) -> pd.DataFrame:
    if profile is not None and not profile.emissions_df.empty:
        return profile.emissions_df.copy()
    return pd.DataFrame(emission_rows(selected)) if selected is not None else pd.DataFrame()


def _render_regulatory_profile_chips(selected: Any | None, profile: CuratedRegulatoryProfile | None) -> None:
    if selected is None and profile is None:
        return
    doc_count = len(selected.payload.get("documents") or []) if selected is not None else 0
    criteria_count = len(profile.criteria_df) if profile is not None else 0
    emission_count = len(profile.emissions_df) if profile is not None else 0
    profile_type = profile.profile_type if profile is not None else "heurístico"
    st.markdown(
        f"""
<div class="monitor-card-row">
  <span class="monitor-chip"><strong>Perfil:</strong> {escape(profile_type)}</span>
  <span class="monitor-chip"><strong>Documentos:</strong> {doc_count}</span>
  <span class="monitor-chip"><strong>Emissões:</strong> {emission_count}</span>
  <span class="monitor-chip"><strong>Critérios:</strong> {criteria_count}</span>
</div>
""",
        unsafe_allow_html=True,
    )


def _drop_selected_fund_columns(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.drop(columns=[column for column in ("Fundo", "CNPJ") if column in frame.columns]).copy()


def _build_regulatory_monitoring_checks(item: dict[str, Any], criteria_df: pd.DataFrame) -> pd.DataFrame:
    latest = _latest_competencia(item)
    if not latest or criteria_df.empty:
        return pd.DataFrame()

    rows = []
    for _, criterion in criteria_df.iterrows():
        evaluated = _evaluate_regulatory_criterion(item, latest, criterion)
        if evaluated:
            rows.append(evaluated)
    return pd.DataFrame(rows)


def _evaluate_regulatory_criterion(item: dict[str, Any], competencia: str, criterion: pd.Series) -> dict[str, str] | None:
    name = str(criterion.get("Critério") or "").strip()
    key = str(criterion.get("Chave") or "").strip()
    monitorability = str(criterion.get("Monitorabilidade IME") or criterion.get("Monitoramento") or "").strip()
    rule = str(criterion.get("Limite/regra") or criterion.get("Limite") or "").strip()
    proxy = str(criterion.get("Métrica IME / proxy") or criterion.get("Métrica IME sugerida") or "").strip()
    alert = str(criterion.get("Condição de alerta sugerida") or "").strip()
    note = str(criterion.get("Observação técnica") or criterion.get("Comentário") or "").strip()

    status = "Referência"
    current_value = "-"

    lowered_name = name.lower()
    if _is_senior_coverage_rule(name, rule):
        senior_pct = _metric_numeric(item, "Cotas SR / PL %", competencia)
        value = (10_000.0 / senior_pct) if senior_pct and senior_pct > 0 else None
        limit = _parse_percent_limit(rule)
        current_value = _format_metric_value(value, "%")
        status = _limit_status(value, limit, higher_is_better=True)
    elif key == "subordination_ratio_min" or "subordinação" in lowered_name or "relação mínima" in lowered_name:
        value = _metric_numeric(item, "Cotas Sub / PL %", competencia)
        limit = _parse_percent_limit(rule)
        current_value = _format_metric_value(value, "%")
        status = _limit_status(value, limit, higher_is_better=True)
    elif key == "credit_rights_allocation_min" or "alocação mínima" in lowered_name:
        value = _metric_numeric(item, "Dir Cred / PL", competencia)
        limit = _parse_percent_limit(rule)
        current_value = _format_metric_value(value, "ratio")
        status = _limit_status((value * 100.0) if value is not None else None, limit, higher_is_better=True)
    elif key in {"default_rate_evaluation_event", "default_rate_early_maturity"}:
        indicator = _default_rate_indicator_for_rule(" ".join([name, rule, proxy, note]))
        if indicator:
            value = _metric_numeric(item, indicator, competencia)
            limit = _parse_percent_limit(rule)
            current_value = _format_metric_value(value, "ratio")
            status = _limit_status((value * 100.0) if value is not None else None, limit, higher_is_better=False)
        else:
            status = "Qualitativo"
    elif key == "pdd_coverage_min" or "pdd" in lowered_name:
        value = _metric_numeric(item, "PDD / Venc Total", competencia)
        limit = _parse_percent_limit(rule)
        current_value = _format_metric_value(value, "ratio")
        status = _limit_status((value * 100.0) if value is not None else None, limit, higher_is_better=True)
    elif key == "recompras_max" or "recompra" in lowered_name:
        value = _metric_numeric(item, "Recompras / Crédito", competencia)
        limit = _parse_percent_limit(rule)
        current_value = _format_metric_value(value, "ratio")
        status = _limit_status((value * 100.0) if value is not None else None, limit, higher_is_better=False)
    elif key == "permitted_hedges" or "derivativo" in lowered_name or "hedge" in lowered_name:
        value = _raw_variable_numeric(item, "MERC_DERIVATIVO/VL_SOM_MERC_DERIVATIVO", competencia)
        current_value = _format_metric_value(value, "R$ bruto")
        if re.search(r"\b(vedad|proibid|não\s+poder|nao\s+poder)\w*", rule.lower()):
            status = "OK" if value is not None and abs(value) <= 1.0 else ("Sem dado" if value is None else "Alerta")
        else:
            status = "Qualitativo"
    elif "pl mínimo" in lowered_name:
        value = _metric_numeric(item, "PL (R$)", competencia)
        current_value = _format_metric_value(value, "R$ bruto")
        status = "OK" if value is not None and value >= 1_000_000 else ("Sem dado" if value is None else "Alerta")
    elif key == "minimum_cash_ratio":
        caixa = _raw_variable_numeric(item, "APLIC_ATIVO/VL_DISPONIB", competencia)
        pl = _metric_numeric(item, "PL (R$)", competencia)
        current_value = _format_metric_value(_safe_ratio(caixa, pl), "ratio")
        status = "Qualitativo"
    elif "direto" not in monitorability.lower():
        status = "Qualitativo"

    return {
        "Critério": name,
        "Regra": rule,
        "Monitorabilidade": monitorability,
        "Proxy IME": proxy,
        "Competência": _format_competencia_label(competencia),
        "Valor IME": current_value,
        "Status": status,
        "Alerta sugerido": alert,
        "Observação": note,
    }


def _is_senior_coverage_rule(name: str, rule: str) -> bool:
    text = f"{name} {rule}".lower()
    return bool(
        ("pl / cotas sênior" in text)
        or ("pl / cotas senior" in text)
        or ("pl/cotas sênior" in text)
        or ("pl/cotas senior" in text)
        or ("patrimônio líquido / cotas seniores" in text)
        or ("patrimonio liquido / cotas seniores" in text)
    )


def _raw_variable_numeric(item: dict[str, Any], id_cvm: str, competencia: str) -> float | None:
    tables: MonitoringTables = item["tables"]
    raw_df = tables.raw_variables_df
    if competencia not in raw_df.columns:
        return None
    match = raw_df[raw_df["id_cvm"] == id_cvm]
    if match.empty:
        return None
    value = pd.to_numeric(pd.Series([match.iloc[0].get(competencia)]), errors="coerce").iloc[0]
    if pd.isna(value):
        return None
    return float(value)


def _parse_percent_limit(value: str) -> float | None:
    match = re.search(r"(\d+(?:[,.]\d+)?)\s*%", str(value or ""))
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _default_rate_indicator_for_rule(value: str) -> str | None:
    text = str(value or "").lower()
    if re.search(r"(over|acima|superior|maior|vencid\w*)\s*(?:a|de)?\s*360|360\s*d", text):
        return "Vencidos Over 360 d / Crédito"
    if re.search(r"(over|acima|superior|maior|vencid\w*)\s*(?:a|de)?\s*180|180\s*d", text):
        return "Vencidos Over 180 d / Crédito"
    if re.search(r"(over|acima|superior|maior|vencid\w*)\s*(?:a|de)?\s*90|90\s*d", text):
        return "Vencidos Over 90 d / Crédito"
    if re.search(r"(over|acima|superior|maior|vencid\w*)\s*(?:a|de)?\s*60|60\s*d", text):
        return "Vencidos Over 60 d / Crédito"
    if re.search(r"(over|acima|superior|maior|vencid\w*)\s*(?:a|de)?\s*30|30\s*d", text):
        return "Vencidos Over 30 d / Crédito"
    return None


def _limit_status(value: float | None, limit: float | None, *, higher_is_better: bool) -> str:
    if value is None or limit is None:
        return "Sem dado"
    if higher_is_better:
        return "OK" if value >= limit else "Alerta"
    return "OK" if value <= limit else "Alerta"


def _render_cockpit_table_html(outputs: list[dict[str, Any]], latest: str) -> str:
    fund_width = 172
    min_width = max(460 + fund_width * (len(outputs) + 1), 980)
    html = [f"<div class='monitor-wide-wrapper' style='min-width: 100%; --monitor-table-min-width: {min_width}px;'>"]
    by_section: dict[str, list[CockpitMetric]] = {}
    for metric in _COCKPIT_METRICS:
        by_section.setdefault(metric.section, []).append(metric)

    for section, metrics in by_section.items():
        html.append(f"<details class='monitor-wide-section' open style='min-width: {min_width}px;'>")
        html.append(f"<summary>{escape(section)}</summary>")
        html.append(f"<table class='monitor-wide-table' style='min-width: {min_width}px;'>")
        html.append("<colgroup><col style='width: 230px;'><col style='width: 120px;'>")
        html.extend(f"<col style='width: {fund_width}px;'>" for _ in outputs)
        html.append("</colgroup><thead><tr><th class='label-col'>Nome</th><th>Consolidado</th>")
        for item in outputs:
            html.append(f"<th>{escape(str(item['display_name']))}</th>")
        html.append("</tr></thead><tbody>")
        for metric in metrics:
            row_class = "destaque" if metric.indicator in {"PL (R$)", "Vencidos Over 90 d / Crédito", "PDD / Venc > 90 d"} else ""
            html.append(f"<tr class='{row_class}'>")
            html.append(f"<td class='label'>{escape(metric.label)}</td>")
            html.append(f"<td>{escape(_format_metric_value(_aggregate_metric(metric, outputs, latest), metric.unit))}</td>")
            for item in outputs:
                value = _metric_numeric(item, metric.indicator, latest)
                html.append(f"<td>{escape(_format_metric_value(value, metric.unit))}</td>")
            html.append("</tr>")
        html.append("</tbody></table></details>")
    html.append("</div>")
    return "\n".join(html)


def _aggregate_metric(metric: CockpitMetric, outputs: list[dict[str, Any]], competencia: str) -> object:
    if metric.aggregate == "none":
        return pd.NA
    if metric.aggregate == "sum":
        values = [_metric_numeric(item, metric.indicator, competencia) for item in outputs]
        total = _sum_numbers(values)
        return pd.NA if total is None else total
    if metric.aggregate == "dircred_pl":
        dircred = _sum_numbers([_metric_numeric(item, "Dir Cred (R$ MM)", competencia) for item in outputs])
        pl = _sum_numbers([_metric_numeric(item, "PL (R$)", competencia) for item in outputs])
        return _safe_ratio(dircred, (pl / 1_000_000.0) if pl is not None else None)
    if metric.aggregate.startswith("over") and metric.aggregate.endswith("_credito"):
        prefix = metric.aggregate.removesuffix("_credito").replace("over", "Vencidos Over ") + " d (R$ MM)"
        vencidos = _sum_numbers([_metric_numeric(item, prefix, competencia) for item in outputs])
        dircred = _sum_numbers([_metric_numeric(item, "Dir Cred (R$ MM)", competencia) for item in outputs])
        return _safe_ratio(vencidos, dircred)
    if metric.aggregate == "pdd_credito":
        pdd = _sum_numbers([_metric_numeric(item, "PDD (R$ MM)", competencia) for item in outputs])
        dircred = _sum_numbers([_metric_numeric(item, "Dir Cred (R$ MM)", competencia) for item in outputs])
        return _safe_ratio(pdd, dircred)
    if metric.aggregate == "pdd_over90":
        pdd = _sum_numbers([_metric_numeric(item, "PDD (R$ MM)", competencia) for item in outputs])
        over90 = _sum_numbers([_metric_numeric(item, "Vencidos Over 90 d (R$ MM)", competencia) for item in outputs])
        return _safe_ratio(pdd, over90)
    if metric.aggregate == "recompras_credito":
        recomp = _sum_numbers([_metric_numeric(item, "Recompras (R$ MM)", competencia) for item in outputs])
        dircred = _sum_numbers([_metric_numeric(item, "Dir Cred (R$ MM)", competencia) for item in outputs])
        return _safe_ratio(recomp, dircred)
    if metric.aggregate == "weighted_pl":
        weighted = 0.0
        weight_sum = 0.0
        for item in outputs:
            value = _metric_numeric(item, metric.indicator, competencia)
            pl = _metric_numeric(item, "PL (R$)", competencia)
            if value is None or pl is None:
                continue
            weighted += value * pl
            weight_sum += pl
        return pd.NA if weight_sum <= 0 else weighted / weight_sum
    return pd.NA


def _metric_numeric(item: dict[str, Any], indicator: str, competencia: str | None) -> float | None:
    if not competencia:
        return None
    tables: MonitoringTables = item["tables"]
    frame = tables.indicators_df
    if competencia not in frame.columns:
        return None
    match = frame[frame["indicador"] == indicator]
    if match.empty:
        return None
    value = pd.to_numeric(pd.Series([match.iloc[0].get(competencia)]), errors="coerce").iloc[0]
    if pd.isna(value):
        return None
    return float(value)


def _sum_numbers(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None and pd.notna(value)]
    if not clean:
        return None
    return float(sum(clean))


def _safe_ratio(numerator: float | None, denominator: float | None) -> object:
    if numerator is None or denominator is None or denominator <= 0:
        return pd.NA
    return float(numerator) / float(denominator)


def _format_metric_value(value: object, unit: str) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "-"
    if unit == "R$ bruto":
        return _format_brl(float(numeric))
    if unit == "R$ MM":
        return f"R$ {_format_decimal(float(numeric), 1)} MM"
    if unit == "ratio":
        return f"{_format_decimal(float(numeric) * 100.0, 2)}%"
    if unit == "%":
        return f"{_format_decimal(float(numeric), 2)}%"
    return _format_decimal(float(numeric), 2)


def _format_brl(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"R$ {_format_decimal(value / 1_000_000_000_000, 1)} bi"
    if abs_value >= 1_000_000:
        return f"R$ {_format_decimal(value / 1_000_000, 1)} MM"
    if abs_value >= 1_000:
        return f"R$ {_format_decimal(value / 1_000, 1)} mil"
    return f"R$ {_format_decimal(value, 0)}"


def _format_decimal(value: float, decimals: int) -> str:
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _format_competencia_label(value: object) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text[2] == "/":
        return f"{_PT_MONTH_ABBR.get(text[:2], text[:2])}/{text[-2:]}"
    return text


def _format_month_date_label(value: date) -> str:
    return f"{_PT_MONTH_ABBR.get(f'{value.month:02d}', f'{value.month:02d}')}/{str(value.year)[-2:]}"


def _format_period_label(period: ImePeriodSelection) -> str:
    return f"{_format_month_date_label(period.start_month)} → {_format_month_date_label(period.end_month)}"


def _portfolio_reference_competencia(
    outputs: list[dict[str, Any]],
    *,
    min_coverage_pct: float = 0.8,
) -> tuple[str | None, int, int]:
    total = len([item for item in outputs if item.get("tables") is not None])
    if total <= 0:
        return None, 0, 0
    coverage: dict[str, int] = {}
    for item in outputs:
        competencias = {str(value) for value in (item.get("competencias") or []) if str(value or "").strip()}
        for competencia in competencias:
            coverage[competencia] = coverage.get(competencia, 0) + 1
    if not coverage:
        return None, 0, total
    required = max(1, math.ceil(total * min_coverage_pct))
    ordered = sorted(coverage, key=lambda value: parse_competencia_label(value), reverse=True)
    for competencia in ordered:
        if coverage.get(competencia, 0) >= required:
            return competencia, coverage.get(competencia, 0), total
    latest = ordered[0]
    return latest, coverage.get(latest, 0), total


def _latest_competencia(item: dict[str, Any]) -> str | None:
    competencias = list(item.get("competencias") or [])
    return competencias[-1] if competencias else None


def _session_key(portfolio: PortfolioRecord, period: ImePeriodSelection, cache_months: int) -> str:
    return f"fidc_monitoring::{portfolio.id}::{period.cache_key}::{cache_months}"
