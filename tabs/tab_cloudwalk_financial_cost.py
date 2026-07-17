from __future__ import annotations

from dataclasses import replace
from datetime import date
from html import escape
from io import BytesIO
from pathlib import Path
import re
import unicodedata
from zipfile import ZIP_DEFLATED, ZipFile

import altair as alt
import pandas as pd
import streamlit as st

from services.dashboard_ui import diagnostics_enabled, render_context_strip, render_page_header
from services.cloudwalk_financial_cost import (
    CostRunConfig,
    FinancialCostOutputs,
    FundingLine,
    build_financial_cost_outputs,
    funding_lines_from_frame,
    load_amortization_convention_overrides,
    load_cash_yield_factor,
    load_ime_financial_snapshots,
    load_spread_overrides,
)
from services.cloudwalk_financial_cost_exports import (
    build_cloudwalk_financial_cost_pptx_bytes,
    build_cloudwalk_financial_cost_xlsx_bytes,
)
from services.cloudwalk_pl_waterfall import CloudwalkPlWaterfall, build_cloudwalk_pl_waterfall
from services.financial_cost_scope import (
    FinancialCostCuration,
    FinancialCostScope,
    SCOPE_CLOUDWALK,
    SCOPE_CNPJS,
    SCOPE_PORTFOLIO,
    build_cloudwalk_scope,
    curation_data_signature,
    parse_manual_cnpj_selection,
    resolve_scope_curation,
    scope_from_cnpjs,
    scope_from_portfolio,
)
from services.fidc_model.b3_cdi import B3CdiError, B3CdiMonthlyRate, fetch_b3_cdi_monthly_rates
from services.fidc_model.b3_curves import fetch_latest_taxaswap_curve
from services.fidc_model.curves import INTERPOLATION_METHOD_FLAT_FORWARD_252, interpolate_curve
from services.fund_name_display import short_fund_name as shared_short_fund_name
from services.identifier_utils import format_cnpj, normalize_cnpj_digits
from services.waterfall_schedule import DEFAULT_REFERENCE_DATE, only_digits
from tabs.ime_portfolio_support import build_portfolio_record_label_lookup, list_saved_portfolios


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EMISSIONS_CSV = ROOT / "data/regulatory_profiles/cloudwalk_cotas_emissoes_pagamentos.csv"
DEFAULT_CONFIG_JSON = ROOT / "config/cloudwalk_financial_cost_inputs.json"
DEFAULT_RUNTIME_CACHE_ROOT = ROOT / ".cache/fundonet-ime"
DEFAULT_PORTABLE_CACHE_ROOT = ROOT / "data/ime_cache/fundonet-ime"
CLOUDWALK_VIEW_TABS = ("Resumo", "Séries", "Mensal", "Waterfall", "Caixa", "Dados e exportações")
SCOPE_MODE_OPTIONS = (SCOPE_CLOUDWALK, SCOPE_PORTFOLIO, SCOPE_CNPJS)
SCOPE_MODE_LABELS = {
    SCOPE_CLOUDWALK: "CloudWalk (padrão)",
    SCOPE_PORTFOLIO: "Carteira cadastrada",
    SCOPE_CNPJS: "CNPJs específicos",
}
SCOPE_MODE_KEY = "cedent_cost_scope_mode"
SAVED_PORTFOLIO_KEY = "cedent_cost_saved_portfolio"
MANUAL_CNPJS_KEY = "cedent_cost_manual_cnpjs"

_CSS = """
<style>
.cloudwalk-purpose {
    color: #68727d;
    font-size: 0.86rem;
    line-height: 1.45;
    margin: 0 0 0.75rem;
    max-width: 72rem;
}
.cloudwalk-note {
    border-bottom: 1px solid #e5e9ef;
    color: #4f5c69;
    font-size: 0.78rem;
    line-height: 1.42;
    margin: 0.1rem 0 0.75rem;
    padding: 0 0 0.55rem;
}
.st-key-cedent_cost_scope {
    background: #f8f9fa;
    border: 1px solid #e3e7ec;
    border-radius: 8px;
    margin: 0.2rem 0 0.85rem;
    padding: 0.8rem 0.9rem 0.65rem;
}
.st-key-cedent_cost_scope [data-baseweb="button-group"] {
    display: grid !important;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    width: 100%;
}
.st-key-cedent_cost_scope [data-testid^="stBaseButton-segmented_control"] {
    min-height: 2.55rem !important;
    white-space: normal !important;
    width: 100% !important;
}
.cedent-cost-scope-summary {
    border-left: 3px solid #ff5a00;
    color: #26313d;
    margin: 0.2rem 0 0.75rem;
    padding: 0.25rem 0 0.25rem 0.75rem;
}
.cedent-cost-scope-summary strong {
    display: block;
    font-size: 0.94rem;
    margin-bottom: 0.1rem;
}
.cedent-cost-scope-summary span {
    color: #68727d;
    font-size: 0.8rem;
    line-height: 1.4;
}
@media (max-width: 700px) {
    .st-key-cedent_cost_scope [data-baseweb="button-group"] {
        grid-template-columns: 1fr;
    }
}
</style>
"""


def render_tab_cloudwalk_financial_cost(*, embedded: bool = False) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    if not embedded:
        render_page_header(
            "Custo Financeiro do Cedente",
            "Custo implícito da carteira de FIDCs e projeção da despesa financeira do cedente.",
        )
    st.markdown(
        '<p class="cloudwalk-purpose">Consolida uma carteira mapeada de FIDCs, estima seu custo implícito em CDI+ '
        "e projeta a despesa financeira anual do cedente.</p>",
        unsafe_allow_html=True,
    )

    scope = _render_scope_selector()
    if scope is None:
        return

    controls = _render_controls(scope)
    if controls is None:
        return

    try:
        outputs, pl_waterfall = _run_cost_engine(**controls)
    except Exception as exc:  # noqa: BLE001
        st.error("Não foi possível calcular o custo financeiro da carteira.")
        if diagnostics_enabled():
            st.caption(f"{type(exc).__name__}: {exc}")
        return

    render_context_strip(
        source=f"{controls['scope_label']} + {controls['curation_source_label']} + {controls['cdi_source']}",
        base_until=f"{controls['start_date']} a {controls['end_date']}",
        coverage=_cost_coverage_label(outputs.line_df, selected_funds=len(controls["scope_cnpjs"])),
    )
    _render_headline(outputs)
    tabs = st.tabs(CLOUDWALK_VIEW_TABS)
    with tabs[0]:
        _render_summary(outputs, controls)
    with tabs[1]:
        _render_lines(outputs)
    with tabs[2]:
        _render_monthly(outputs)
    with tabs[3]:
        _render_pl_waterfall(pl_waterfall)
    with tabs[4]:
        _render_cash(outputs)
    with tabs[5]:
        _render_downloads(outputs, pl_waterfall, controls)


def _render_scope_selector() -> FinancialCostScope | None:
    try:
        default_scope = _default_cloudwalk_scope()
    except Exception as exc:  # noqa: BLE001
        st.error("Não foi possível carregar o preset padrão da CloudWalk.")
        if diagnostics_enabled():
            st.caption(f"{type(exc).__name__}: {exc}")
        return None

    current_mode = str(st.session_state.get(SCOPE_MODE_KEY) or "")
    if current_mode not in SCOPE_MODE_OPTIONS:
        st.session_state[SCOPE_MODE_KEY] = SCOPE_CLOUDWALK

    with st.container(key="cedent_cost_scope"):
        st.markdown("**Escopo do cálculo**")
        st.caption("Use o preset CloudWalk, uma carteira já cadastrada ou informe até 20 CNPJs.")
        mode = st.segmented_control(
            "Forma de seleção",
            options=SCOPE_MODE_OPTIONS,
            format_func=SCOPE_MODE_LABELS.get,
            selection_mode="single",
            required=True,
            key=SCOPE_MODE_KEY,
            label_visibility="collapsed",
            width="stretch",
        )
        mode = mode if mode in SCOPE_MODE_OPTIONS else SCOPE_CLOUDWALK

        if mode == SCOPE_CLOUDWALK:
            st.caption(f"Preset de sistema com {len(default_scope.cnpjs)} fundos e a curadoria atual preservada.")
            return default_scope

        if mode == SCOPE_PORTFOLIO:
            try:
                portfolios = list_saved_portfolios()
            except Exception as exc:  # noqa: BLE001
                st.warning("Não foi possível acessar as carteiras cadastradas. O preset CloudWalk continua disponível.")
                if diagnostics_enabled():
                    st.caption(f"{type(exc).__name__}: {exc}")
                return None
            if not portfolios:
                st.info("Nenhuma carteira cadastrada está disponível.")
                return None
            options = [portfolio.id for portfolio in portfolios]
            current_id = str(st.session_state.get(SAVED_PORTFOLIO_KEY) or "")
            if current_id not in options:
                st.session_state[SAVED_PORTFOLIO_KEY] = _default_portfolio_id(portfolios, default_scope)
            labels = build_portfolio_record_label_lookup(portfolios)
            selected_id = st.selectbox(
                "Carteira cadastrada",
                options=options,
                format_func=lambda value: labels.get(value, value),
                key=SAVED_PORTFOLIO_KEY,
            )
            selected = next((portfolio for portfolio in portfolios if portfolio.id == selected_id), None)
            if selected is None:
                st.warning("A carteira selecionada não está mais disponível.")
                return None
            st.caption(f"{len(selected.funds)} fundo{'s' if len(selected.funds) != 1 else ''} na carteira.")
            return scope_from_portfolio(selected)

        raw_cnpjs = st.text_area(
            "CNPJs dos fundos",
            key=MANUAL_CNPJS_KEY,
            placeholder="Um CNPJ por linha, ou separados por vírgula",
            height=105,
            help="São aceitos CNPJs com ou sem máscara. Duplicados são removidos e os dígitos verificadores são validados.",
        )
        parsed = parse_manual_cnpj_selection(raw_cnpjs)
        if parsed.invalid:
            st.error("Corrija os CNPJs inválidos: " + ", ".join(parsed.invalid))
            return None
        if len(parsed.cnpjs) > 20:
            st.error("A seleção manual pode conter no máximo 20 fundos.")
            return None
        if parsed.duplicates:
            st.caption(f"{len(parsed.duplicates)} CNPJ{'s' if len(parsed.duplicates) != 1 else ''} duplicado{'s' if len(parsed.duplicates) != 1 else ''} removido{'s' if len(parsed.duplicates) != 1 else ''}.")
        if not parsed.cnpjs:
            st.info("Informe ao menos um CNPJ válido para montar o escopo.")
            return None
        st.caption(f"{len(parsed.cnpjs)} fundo{'s' if len(parsed.cnpjs) != 1 else ''} selecionado{'s' if len(parsed.cnpjs) != 1 else ''}.")
        return scope_from_cnpjs(parsed.cnpjs)


@st.cache_data(show_spinner=False)
def _build_cloudwalk_scope_cached(path: str, mtime_ns: int, size: int) -> FinancialCostScope:
    _ = (mtime_ns, size)
    return build_cloudwalk_scope(path)


def _default_cloudwalk_scope() -> FinancialCostScope:
    stat = DEFAULT_EMISSIONS_CSV.stat()
    return _build_cloudwalk_scope_cached(str(DEFAULT_EMISSIONS_CSV), stat.st_mtime_ns, stat.st_size)


@st.cache_data(show_spinner="Resolvendo séries e curadoria do escopo...")
def _resolve_scope_curation_cached(scope: FinancialCostScope, signature: str) -> FinancialCostCuration:
    _ = signature
    return resolve_scope_curation(scope)


def _default_portfolio_id(portfolios: list[object], default_scope: FinancialCostScope) -> str:
    default_basket = set(default_scope.cnpjs)
    for portfolio in portfolios:
        basket = {normalize_cnpj_digits(fund.cnpj) for fund in portfolio.funds}
        if basket == default_basket:
            return str(portfolio.id)
    return str(portfolios[0].id)


def _render_controls(scope: FinancialCostScope) -> dict[str, object] | None:
    base_config = _load_base_config()
    curation_signature = curation_data_signature(scope)
    curation = _resolve_scope_curation_cached(scope, curation_signature)
    _render_curation_coverage(scope, curation)
    if not curation.has_emissions:
        st.warning(
            "Nenhuma série foi localizada para os fundos selecionados. O spread sozinho não é suficiente: "
            "também são necessários série, tipo, volume e cronograma para calcular o custo."
        )
        return None

    curated_lines = funding_lines_from_frame(
        curation.emissions_df,
        amortization_convention_overrides=dict(base_config["amortization_conventions"]),
    )
    active_lines = [line for line in curated_lines if line.included]
    if not active_lines:
        st.warning(
            "Há documentos para o escopo, mas nenhuma série remunerada com volume utilizável. "
            "Revise a cobertura da curadoria antes de calcular."
        )
        return None
    visible_keys = {line.line_key for line in active_lines}
    persisted_manual = {
        key: value
        for key, value in dict(base_config["spread_overrides"]).items()
        if key in visible_keys
    }
    manual_state_key = f"cedent_cost_manual_overrides::{scope.signature[:16]}::{curation_signature[:16]}"
    if manual_state_key in st.session_state:
        current_manual = {
            str(key): float(value)
            for key, value in dict(st.session_state.get(manual_state_key) or {}).items()
            if str(key) in visible_keys
        }
    else:
        current_manual = persisted_manual

    current_year = date.today().year
    form_key = f"cedent_financial_cost_controls_{scope.signature[:12]}"
    with st.form(form_key, border=False):
        col1, col2, col3 = st.columns([0.8, 1.1, 1.1])
        year = col1.number_input(
            "Ano-base",
            min_value=2020,
            max_value=2035,
            value=current_year,
            step=1,
            help="Preenche automaticamente o período de 01/jan a 31/dez. Ajuste as datas ao lado para simular outro intervalo.",
        )
        default_start = date(int(year), 1, 1)
        default_end = date(int(year), 12, 31)
        start_date = col2.date_input(
            "Data inicial",
            value=default_start,
            format="YYYY-MM-DD",
            help="Primeiro dia considerado para captações, amortizações, CDI e saldo médio das cotas.",
        )
        end_date = col3.date_input(
            "Data final",
            value=default_end,
            format="YYYY-MM-DD",
            help="Último dia considerado. O motor corta emissões futuras e amortizações fora do período.",
        )

        spread_table = _spread_input_table(curated_lines, current_manual)
        edited_spreads = spread_table
        pending_count = int(spread_table["Status"].eq("Pendente").sum()) if not spread_table.empty else 0
        with st.expander("Taxas CDI+ por série", expanded=scope.kind != SCOPE_CLOUDWALK or pending_count > 0):
            st.caption(
                "O valor manual é opcional e vale somente nesta simulação. Quando preenchido, prevalece sobre a curadoria; "
                "ao limpar a célula, a taxa volta para a curadoria."
            )
            if spread_table.empty:
                st.caption("Nenhuma série ativa remunerada para editar.")
            else:
                edited_spreads = st.data_editor(
                    spread_table,
                    hide_index=True,
                    width="stretch",
                    key=f"cedent_cost_spreads_{scope.signature[:10]}_{curation_signature[:10]}",
                    disabled=[
                        "FIDC",
                        "CNPJ",
                        "Série",
                        "CDI+ curadoria (% a.a.)",
                        "CDI+ efetivo (% a.a.)",
                        "Origem efetiva",
                        "Status",
                        "Fonte documento",
                        "Chave",
                    ],
                    column_config={
                        "CDI+ curadoria (% a.a.)": st.column_config.NumberColumn(format="%.2f"),
                        "CDI+ manual (% a.a.)": st.column_config.NumberColumn(
                            "CDI+ manual (% a.a.)",
                            help="Opcional. Preencha em pontos percentuais: 0,95 para CDI+0,95% a.a.",
                            format="%.2f",
                            min_value=-10.0,
                            max_value=30.0,
                        ),
                        "CDI+ efetivo (% a.a.)": st.column_config.NumberColumn(format="%.2f"),
                        "Chave": None,
                    },
                )

        with st.expander("Premissas avançadas", expanded=False):
            col4, col5 = st.columns([1.1, 2.2])
            cash_yield_factor = col4.number_input(
                "Caixa/LFT (x CDI)",
                value=float(base_config["cash_yield_factor"]),
                min_value=0.0,
                max_value=2.0,
                step=0.05,
                help="Multiplicador aplicado à rentabilidade do caixa/LFT. Use 1,00 para 100% do CDI; use 0,00 para não abater carry de caixa.",
            )
            curve_date = col5.date_input(
                "CDI fallback B3",
                value=date.today(),
                format="YYYY-MM-DD",
                help="Só é usado se o CDI mensal B3/Cetip não estiver disponível para o período.",
            )

        submitted = st.form_submit_button("Atualizar estimativa", width="stretch")

    if end_date < start_date:
        st.warning("A data final precisa ser maior ou igual à data inicial.")
        return None

    manual_overrides = _parse_spread_editor(edited_spreads)
    if submitted:
        st.session_state[manual_state_key] = manual_overrides
        if manual_overrides != current_manual:
            st.rerun()

    try:
        monthly_cdi_rates = _resolve_monthly_cdi(start_date, end_date)
    except B3CdiError as exc:
        monthly_cdi_rates = ()
        st.warning("O CDI mensal realizado não pôde ser carregado; usando a curva B3 como fallback.")
        if diagnostics_enabled():
            st.caption(f"{type(exc).__name__}: {exc}")
    monthly_cdi_aa = _annualize_monthly_cdi(monthly_cdi_rates)
    if monthly_cdi_aa is not None:
        cdi_aa, cdi_source = monthly_cdi_aa, _monthly_cdi_source_label(monthly_cdi_rates)
    else:
        cdi_aa, cdi_source = _resolve_b3_cdi(curve_date, 0.1399364)

    funding_lines = funding_lines_from_frame(
        curation.emissions_df,
        spread_overrides=manual_overrides,
        amortization_convention_overrides=dict(base_config["amortization_conventions"]),
    )
    active_lines = [line for line in funding_lines if line.included]
    priced_count = sum(line.has_rate for line in active_lines)
    missing_count = sum(not line.has_rate for line in active_lines)
    if priced_count == 0:
        st.warning("Nenhuma série possui CDI+ efetivo. Preencha as taxas pendentes para calcular.")
        return None
    if missing_count:
        verb = "ficaram" if missing_count != 1 else "ficou"
        st.warning(
            f"Estimativa parcial: {missing_count} série{'s' if missing_count != 1 else ''} ativa{'s' if missing_count != 1 else ''} "
            f"sem CDI+ {verb} fora dos totais."
        )

    fund_names = dict(scope.fund_name_map)
    for line in funding_lines:
        cnpj = normalize_cnpj_digits(line.cnpj)
        if cnpj and line.fund_name:
            fund_names[cnpj] = line.fund_name
    return {
        "funding_lines": tuple(funding_lines),
        "scope_cnpjs": tuple(scope.cnpjs),
        "fund_names": tuple((cnpj, fund_names.get(cnpj, cnpj)) for cnpj in scope.cnpjs),
        "scope_label": scope.label,
        "scope_kind": scope.kind,
        "curation_source_label": _curation_source_label(curation),
        "start_date": start_date,
        "end_date": end_date,
        "snapshot_date": _default_snapshot_date(start_date, end_date),
        "cdi_aa": cdi_aa,
        "cdi_source": cdi_source,
        "monthly_cdi_rates": monthly_cdi_rates,
        "cash_yield_factor": cash_yield_factor,
    }


def _render_curation_coverage(scope: FinancialCostScope, curation: FinancialCostCuration) -> None:
    coverage = curation.coverage_df
    series_count = int(pd.to_numeric(coverage.get("active_series"), errors="coerce").fillna(0).sum()) if not coverage.empty else 0
    auto_count = int(pd.to_numeric(coverage.get("automatic_spreads"), errors="coerce").fillna(0).sum()) if not coverage.empty else 0
    resolved_funds = int(pd.to_numeric(coverage.get("series_found"), errors="coerce").fillna(0).gt(0).sum()) if not coverage.empty else 0
    fund_count = len(scope.cnpjs)
    selected_fund_label = f"{fund_count} fundo{'s' if fund_count != 1 else ''} selecionado{'s' if fund_count != 1 else ''}"
    st.markdown(
        '<div class="cedent-cost-scope-summary">'
        f"<strong>{escape(scope.label)}</strong>"
        f"<span>{selected_fund_label} | {resolved_funds} com séries localizadas | "
        f"{series_count} séries ativas | {auto_count} CDI+ automáticos</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    missing = coverage[pd.to_numeric(coverage.get("series_found"), errors="coerce").fillna(0).eq(0)] if not coverage.empty else pd.DataFrame()
    if not missing.empty:
        labels = [f"{shared_short_fund_name(row.fund_name)} ({format_cnpj(row.cnpj)})" for row in missing.itertuples()]
        st.warning("Sem curadoria de séries para: " + "; ".join(labels))
    ambiguous = int(pd.to_numeric(coverage.get("ambiguous_rows_blocked"), errors="coerce").fillna(0).sum()) if not coverage.empty else 0
    if ambiguous:
        st.warning(
            f"{ambiguous} registro{'s' if ambiguous != 1 else ''} com identidade de série ambígua "
            f"foi{'ram' if ambiguous != 1 else ''} bloqueado{'s' if ambiguous != 1 else ''} para evitar dupla contagem."
        )
    low_confidence = coverage[
        coverage.get("profile_type", pd.Series("", index=coverage.index)).isin(["triagem estruturada", "heurístico"])
    ] if not coverage.empty else pd.DataFrame()
    if not low_confidence.empty:
        st.info(
            "Parte do escopo usa triagem documental ou extração heurística. As linhas não ambíguas podem ser simuladas, "
            "mas devem ser revisadas antes de uma decisão final."
        )
    if not coverage.empty:
        with st.expander("Cobertura da curadoria", expanded=False):
            display = coverage.copy()
            display["cnpj"] = display["cnpj"].map(format_cnpj)
            display["fund_name"] = display["fund_name"].map(shared_short_fund_name)
            display = display.rename(
                columns={
                    "fund_name": "FIDC",
                    "cnpj": "CNPJ",
                    "profile_type": "Tipo de perfil",
                    "series_found": "Séries localizadas",
                    "active_series": "Séries ativas",
                    "automatic_spreads": "CDI+ automático",
                    "pending_spreads": "CDI+ pendente",
                    "ambiguous_rows_blocked": "Registros ambíguos bloqueados",
                    "source_files": "Fontes",
                    "status": "Status",
                }
            )
            st.dataframe(display, hide_index=True, width="stretch")


def _curation_source_label(curation: FinancialCostCuration) -> str:
    if not curation.source_files:
        return "curadoria não localizada"
    names = {Path(path).name for path in curation.source_files}
    if names == {DEFAULT_EMISSIONS_CSV.name}:
        return "curadoria CloudWalk"
    return f"curadoria regulatória ({len(names)} fonte{'s' if len(names) != 1 else ''})"


@st.cache_data(show_spinner=False)
def _load_base_config() -> dict[str, object]:
    return {
        "spread_overrides": load_spread_overrides(DEFAULT_CONFIG_JSON),
        "amortization_conventions": load_amortization_convention_overrides(DEFAULT_CONFIG_JSON),
        "cash_yield_factor": load_cash_yield_factor(DEFAULT_CONFIG_JSON),
    }


@st.cache_data(ttl=3600, show_spinner="Buscando e compondo CDI B3 mês a mês...")
def _resolve_monthly_cdi(start_date: date, end_date: date) -> tuple[B3CdiMonthlyRate, ...]:
    return fetch_b3_cdi_monthly_rates(start_date, end_date)


@st.cache_data(show_spinner="Buscando CDI na B3...")
def _fetch_b3_cdi(curve_date_iso: str) -> tuple[float, str]:
    snapshot = fetch_latest_taxaswap_curve(start_date=date.fromisoformat(curve_date_iso), curve_code="PRE")
    cdi_aa = interpolate_curve(
        252.0,
        snapshot.curva_du,
        snapshot.curva_taxa_aa,
        method=INTERPOLATION_METHOD_FLAT_FORWARD_252,
    )
    return float(cdi_aa), f"B3 TaxaSwap PRE {snapshot.generated_at.isoformat()} DU252"


def _resolve_b3_cdi(curve_date: date, fallback_cdi_aa: float) -> tuple[float, str]:
    try:
        return _fetch_b3_cdi(curve_date.isoformat())
    except Exception as exc:  # noqa: BLE001
        st.warning("A consulta à B3 falhou; usando o CDI manual como fallback.")
        if diagnostics_enabled():
            st.caption(f"{type(exc).__name__}: {exc}")
        return fallback_cdi_aa, "manual fallback após falha B3"


@st.cache_data(show_spinner="Calculando custo financeiro da carteira...")
def _run_cost_engine(
    *,
    funding_lines: tuple[FundingLine, ...],
    scope_cnpjs: tuple[str, ...],
    fund_names: tuple[tuple[str, str], ...],
    scope_label: str,
    scope_kind: str,
    curation_source_label: str,
    start_date: date,
    end_date: date,
    snapshot_date: date,
    cdi_aa: float,
    cdi_source: str,
    monthly_cdi_rates: tuple[B3CdiMonthlyRate, ...],
    cash_yield_factor: float,
) -> tuple[FinancialCostOutputs, CloudwalkPlWaterfall]:
    _ = curation_source_label
    lines = list(funding_lines)
    fund_name_map = dict(fund_names)
    priced_cnpjs = {only_digits(line.cnpj) for line in lines if line.included and line.has_rate}
    snapshots = load_ime_financial_snapshots(
        scope_cnpjs,
        fund_names=fund_name_map,
        cache_root=DEFAULT_RUNTIME_CACHE_ROOT,
        portable_cache_root=DEFAULT_PORTABLE_CACHE_ROOT,
        as_of_date=snapshot_date,
    )
    snapshots = [
        snapshot
        if only_digits(snapshot.cnpj) in priced_cnpjs
        else replace(
            snapshot,
            included=False,
            exclusion_reason="Fundo sem série precificada no escopo; caixa não abatido do custo líquido.",
        )
        for snapshot in snapshots
    ]
    outputs = build_financial_cost_outputs(
        lines=lines,
        snapshots=snapshots,
        config=CostRunConfig(
            start_date=start_date,
            end_date=end_date,
            snapshot_date=snapshot_date,
            cdi_aa=float(cdi_aa),
            cdi_source=cdi_source,
            cash_yield_cdi_factor=float(cash_yield_factor),
            monthly_cdi_rates=monthly_cdi_rates,
            scope_label=scope_label,
            scope_kind=scope_kind,
        ),
    )
    pl_waterfall = build_cloudwalk_pl_waterfall(
        scope_cnpjs,
        fund_names=fund_name_map,
        year=start_date.year,
        end_date=end_date,
        cache_root=DEFAULT_RUNTIME_CACHE_ROOT,
        portable_cache_root=DEFAULT_PORTABLE_CACHE_ROOT,
    )
    return outputs, pl_waterfall


def _render_headline(outputs: FinancialCostOutputs) -> None:
    summary = outputs.summary_df
    recommended = _summary_row(summary, "2_programado_bruto_com_amortizacao")
    net = _summary_row(summary, "3_programado_liquido_caixa_lft")
    cash_base, cash_yield = _cash_totals(outputs)
    cdi_aa = float(recommended["cdi_aa"])
    implied_spread = _solve_implied_spread(outputs.monthly_df, float(recommended["despesa_financeira_bruta"]), cdi_aa)
    weighted_spread = _weighted_average_spread(outputs.line_df)

    cols = st.columns(4)
    cols[0].metric("CDI+ implícito", _format_cdi_plus(implied_spread))
    cols[1].metric("Despesa bruta", _format_money(float(recommended["despesa_financeira_bruta"])))
    cols[2].metric("Custo líquido", _format_money(float(net["despesa_financeira_liquida"])))
    cols[3].metric("Saldo médio", _format_money(float(recommended["saldo_base"])))

    note = (
        f"CDI usado: {_format_percent(cdi_aa)} a.a. equivalente ({recommended['cdi_source']}). "
        f"Spread ponderado por saldo médio: {_format_cdi_plus(weighted_spread)} "
        f"Caixa/LFT: {_format_money(cash_base)}; rendimento estimado: {_format_money(cash_yield)}."
    )
    st.markdown(f"<div class='cloudwalk-note'>{note}</div>", unsafe_allow_html=True)


def _render_summary(outputs: FinancialCostOutputs, controls: dict[str, object]) -> None:
    st.markdown("<h2>Estimativas principais</h2>", unsafe_allow_html=True)
    display = outputs.summary_df.copy()
    display = display[display["estimativa"].isin(["2_programado_bruto_com_amortizacao", "3_programado_liquido_caixa_lft"])].copy()
    display["estimativa"] = display["estimativa"].map(
        {
            "2_programado_bruto_com_amortizacao": "Bruto programado",
            "3_programado_liquido_caixa_lft": "Líquido após caixa/LFT",
        }
    )
    display["descricao"] = display["descricao"].map(_short_description)
    money_columns = [
        "despesa_financeira_bruta",
        "receita_antecipacao_gross_up_sugerida",
        "rendimento_caixa_lft",
        "despesa_financeira_liquida",
        "saldo_base",
        "saldo_snapshot_sem_spread",
    ]
    for column in money_columns:
        display[column] = display[column].map(_format_money)
    display["cdi_aa"] = display["cdi_aa"].map(_format_percent)
    display = display.rename(
        columns={
            "estimativa": "Estimativa",
            "descricao": "Como ler",
            "despesa_financeira_bruta": "Despesa bruta",
            "receita_antecipacao_gross_up_sugerida": "Gross-up receita",
            "rendimento_caixa_lft": "Rendimento caixa/LFT",
            "despesa_financeira_liquida": "Despesa líquida",
            "saldo_base": "Saldo médio",
            "linhas_incluidas": "Séries incluídas",
            "linhas_sem_spread": "Séries sem CDI+",
            "periodo_inicio": "Início",
            "periodo_fim": "Fim",
            "cdi_aa": "CDI a.a.",
            "cdi_source": "Fonte CDI",
        }
    )
    summary_columns = [
        "Estimativa",
        "Como ler",
        "Despesa bruta",
        "Gross-up receita",
        "Rendimento caixa/LFT",
        "Despesa líquida",
        "Saldo médio",
        "Séries incluídas",
        "Séries sem CDI+",
        "Início",
        "Fim",
        "CDI a.a.",
        "Fonte CDI",
    ]
    display = display[[column for column in summary_columns if column in display.columns]]
    st.dataframe(display, hide_index=True, width="stretch")
    cdi_frame = _cdi_rates_frame(controls.get("monthly_cdi_rates") or ())
    if not cdi_frame.empty:
        with st.expander("CDI mensal utilizado", expanded=False):
            cdi_display = cdi_frame.copy()
            cdi_display["cdi_mensal"] = pd.to_numeric(cdi_display["cdi_mensal"], errors="coerce").map(_format_percent)
            cdi_display["cdi_aa_equivalente"] = pd.to_numeric(cdi_display["cdi_aa_equivalente"], errors="coerce").map(_format_percent)
            cdi_display = cdi_display.rename(
                columns={
                    "mes": "Mês",
                    "cdi_mensal": "CDI mensal",
                    "cdi_aa_equivalente": "CDI a.a. equivalente",
                    "dias_uteis": "Dias úteis",
                }
            )
            st.dataframe(cdi_display, hide_index=True, width="stretch")


def _render_lines(outputs: FinancialCostOutputs) -> None:
    frame = outputs.line_df.copy()
    active = frame[frame["included_in_cost"].fillna(False).astype(bool)].copy()
    if active.empty:
        st.info("Nenhuma linha incluída no custo.")
        return

    st.markdown("<h2>Despesa por FIDC</h2>", unsafe_allow_html=True)
    fund_cost = (
        active.groupby("fund_name", as_index=False)
        .agg(saldo_medio_programado=("saldo_medio_programado", "sum"), custo_programado_bruto=("custo_programado_bruto", "sum"))
        .sort_values("custo_programado_bruto", ascending=False)
    )
    chart = (
        alt.Chart(fund_cost)
        .mark_bar(color="#25282d")
        .encode(
            x=alt.X("custo_programado_bruto:Q", title="Custo bruto estimado"),
            y=alt.Y("fund_name:N", sort="-x", title="FIDC"),
            tooltip=[
                alt.Tooltip("fund_name:N", title="FIDC"),
                alt.Tooltip("custo_programado_bruto:Q", title="Custo", format=",.0f"),
                alt.Tooltip("saldo_medio_programado:Q", title="Saldo médio", format=",.0f"),
            ],
        )
        .properties(height=max(260, 26 * len(fund_cost)))
    )
    st.altair_chart(chart, width="stretch")

    with st.expander("Detalhamento por série", expanded=False):
        st.dataframe(_series_price_frame(frame), hide_index=True, width="stretch")


def _render_monthly(outputs: FinancialCostOutputs) -> None:
    frame = outputs.monthly_df.copy()
    if frame.empty:
        st.info("Sem custo mensal calculado.")
        return
    monthly = frame.groupby("mes", as_index=False).agg(
        saldo_base=("saldo_base", "sum"),
        custo_programado_bruto=("custo_programado_bruto", "sum"),
    )
    chart = (
        alt.Chart(monthly)
        .mark_bar(color="#d35714")
        .encode(
            x=alt.X("mes:N", title="Mês"),
            y=alt.Y("custo_programado_bruto:Q", title="Custo bruto"),
            tooltip=[
                alt.Tooltip("mes:N", title="Mês"),
                alt.Tooltip("custo_programado_bruto:Q", title="Custo", format=",.0f"),
                alt.Tooltip("saldo_base:Q", title="Saldo base", format=",.0f"),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, width="stretch")
    monthly_display = monthly.copy()
    monthly_display["saldo_base"] = monthly_display["saldo_base"].map(_format_money)
    monthly_display["custo_programado_bruto"] = monthly_display["custo_programado_bruto"].map(_format_money)
    monthly_display = monthly_display.rename(
        columns={
            "mes": "Mês",
            "saldo_base": "Saldo base",
            "custo_programado_bruto": "Custo bruto",
        }
    )
    with st.expander("Detalhamento mensal", expanded=False):
        st.dataframe(monthly_display, hide_index=True, width="stretch")


def _render_pl_waterfall(pl_waterfall: CloudwalkPlWaterfall) -> None:
    if pl_waterfall.steps_df.empty:
        st.info("Sem dados de PL para montar o waterfall.")
        return
    chart_df = _waterfall_chart_frame(pl_waterfall.steps_df)
    color_scale = alt.Scale(domain=["total", "up", "down"], range=["#111111", "#0f9d58", "#d93025"])
    bars = (
        alt.Chart(chart_df)
        .mark_bar(size=42)
        .encode(
            x=alt.X("etapa:N", title=None, sort=None),
            y=alt.Y("bar_start:Q", title="PL / variação"),
            y2="bar_end:Q",
            color=alt.Color("tipo:N", scale=color_scale, legend=None),
            tooltip=[
                alt.Tooltip("etapa:N", title="Etapa"),
                alt.Tooltip("valor:Q", title="Valor", format=",.0f"),
                alt.Tooltip("acumulado:Q", title="Acumulado", format=",.0f"),
            ],
        )
    )
    labels = (
        alt.Chart(chart_df)
        .mark_text(dy=-8, fontSize=11, color="#111111")
        .encode(x=alt.X("etapa:N", sort=None), y=alt.Y("label_y:Q"), text="label:N")
    )
    st.altair_chart((bars + labels).properties(height=360), width="stretch")
    with st.expander("Reconciliação por FIDC", expanded=False):
        st.dataframe(_pl_waterfall_frame(pl_waterfall.by_fund_df), hide_index=True, width="stretch")


def _render_cash(outputs: FinancialCostOutputs) -> None:
    frame = outputs.ime_snapshot_df.copy()
    if frame.empty:
        st.info("Sem informe mensal em cache para caixa/LFT.")
        return
    total_cash, total_yield = _cash_totals(outputs)
    reported_cash = pd.to_numeric(frame["cash_like_reported"], errors="coerce").fillna(0.0).sum()
    residual_proxy = pd.to_numeric(frame["cash_like_residual_proxy"], errors="coerce").fillna(0.0).sum()
    cols = st.columns(4)
    cols[0].metric("Aplicação caixa/LFT", _format_money(total_cash))
    cols[1].metric("Rendimento estimado", _format_money(total_yield))
    cols[2].metric("Caixa + títulos", _format_money(reported_cash))
    cols[3].metric("Proxy PL - recebíveis", _format_money(residual_proxy))
    with st.expander("Detalhamento por FIDC", expanded=False):
        st.dataframe(_cash_frame(frame), hide_index=True, width="stretch")


def _render_downloads(outputs: FinancialCostOutputs, pl_waterfall: CloudwalkPlWaterfall, controls: dict[str, object]) -> None:
    recommended = _summary_row(outputs.summary_df, "2_programado_bruto_com_amortizacao")
    scope_label = str(controls.get("scope_label") or "Seleção de FIDCs")
    scope_kind = str(controls.get("scope_kind") or "")
    export_prefix = _scope_export_prefix(scope_kind, scope_label)
    assumptions = pd.DataFrame(
        [
            ("Escopo", scope_label),
            ("Fundos selecionados", str(len(controls.get("scope_cnpjs") or ()))),
            ("Período calculado", f"{recommended['periodo_inicio']} a {recommended['periodo_fim']}"),
            ("CDI", f"Mensal composto - {recommended['cdi_source']}"),
            ("Caixa/LFT", f"IME mais recente até o snapshot por fundo; rendimento a {float(recommended['cash_yield_cdi_factor']):.2f}x CDI"),
            ("CDI+ manual", "Editável em 'Taxas CDI+ por série'; o valor manual prevalece somente nesta simulação."),
            ("Base de cotas", str(controls.get("curation_source_label") or "Curadoria regulatória por CNPJ")),
            ("Cache IME", "Cache local e portátil do Toma Conta FIDCs."),
        ],
        columns=["Premissa", "Valor"],
    )
    if not outputs.missing_inputs_df.empty:
        st.warning("Há linhas ativas sem spread CDI+.")
        st.dataframe(outputs.missing_inputs_df, hide_index=True, width="stretch")

    with st.expander("Sobre a base", expanded=False):
        st.dataframe(assumptions, hide_index=True, width="stretch")
        st.markdown(outputs.methodology_md)

    xlsx_bytes = build_cloudwalk_financial_cost_xlsx_bytes(
        outputs,
        pl_waterfall=pl_waterfall,
        monthly_cdi_rates=controls.get("monthly_cdi_rates") or (),
        scope_label=scope_label,
    )
    pptx_bytes = build_cloudwalk_financial_cost_pptx_bytes(
        outputs,
        pl_waterfall=pl_waterfall,
        scope_label=scope_label,
    )
    if scope_kind == SCOPE_CLOUDWALK:
        xlsx_name = f"cloudwalk_memoria_custo_fidcs_{controls['start_date']}_{controls['end_date']}.xlsx"
        pptx_name = f"cloudwalk_custo_fidcs_{controls['start_date']}_{controls['end_date']}.pptx"
    else:
        xlsx_name = f"{export_prefix}_memoria_custo_fidcs_{controls['start_date']}_{controls['end_date']}.xlsx"
        pptx_name = f"{export_prefix}_custo_fidcs_{controls['start_date']}_{controls['end_date']}.pptx"
    col1, col2, col3 = st.columns(3)
    col1.download_button(
        "Baixar memória XLSX",
        data=xlsx_bytes,
        file_name=xlsx_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
    col2.download_button(
        "Baixar PPTX",
        data=pptx_bytes,
        file_name=pptx_name,
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        width="stretch",
    )
    col3.download_button(
        "Baixar pacote CSV",
        data=_zip_outputs(outputs, prefix=export_prefix),
        file_name=f"{export_prefix}_{controls['start_date']}_{controls['end_date']}.zip",
        mime="application/zip",
        width="stretch",
    )


def _summary_row(summary: pd.DataFrame, estimativa: str) -> pd.Series:
    return summary.loc[summary["estimativa"].eq(estimativa)].iloc[0]


def _cost_coverage_label(line_df: pd.DataFrame, *, selected_funds: int | None = None) -> str:
    if line_df is None or line_df.empty:
        return "Sem séries mapeadas"
    active = line_df.copy()
    if "included" in active.columns:
        active = active[active["included"].fillna(False).astype(bool)]
    fund_count = 0
    if "cnpj" in active.columns:
        fund_count = int(active["cnpj"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique())
    elif "fund_name" in active.columns:
        fund_names = active["fund_name"].fillna("").astype(str).str.strip()
        fund_count = int(fund_names[fund_names.ne("")].nunique())
    series_count = len(active)
    fund_label = "FIDC" if fund_count == 1 else "FIDCs"
    series_label = "série" if series_count == 1 else "séries"
    if selected_funds is not None and selected_funds != fund_count:
        return f"{fund_count}/{selected_funds} {fund_label} com séries ativas · {series_count} {series_label} ativas"
    return f"{fund_count} {fund_label} · {series_count} {series_label} mapeadas"


def _spread_input_table(lines: list[FundingLine], manual_overrides: dict[str, float]) -> pd.DataFrame:
    rows = []
    for line in lines:
        if not line.included or not _is_priced_class(line.class_macro):
            continue
        curated = line.curated_spread_aa
        manual = manual_overrides.get(line.line_key)
        effective = manual if manual is not None else curated
        origin = "Manual" if manual is not None else ("Documento/curadoria" if curated is not None else "Pendente")
        rows.append(
            {
                "FIDC": _short_fund_name(line.fund_name),
                "CNPJ": format_cnpj(line.cnpj),
                "Série": line.classe,
                "CDI+ curadoria (% a.a.)": None if curated is None else round(curated * 100.0, 4),
                "CDI+ manual (% a.a.)": None if manual is None else round(manual * 100.0, 4),
                "CDI+ efetivo (% a.a.)": None if effective is None else round(effective * 100.0, 4),
                "Origem efetiva": origin,
                "Status": "Pendente" if effective is None else "Pronto",
                "Fonte documento": line.source,
                "Chave": line.line_key,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["FIDC", "Série"]).reset_index(drop=True)


def _parse_spread_editor(frame: pd.DataFrame) -> dict[str, float]:
    if frame is None or frame.empty:
        return {}
    parsed: dict[str, float] = {}
    for _, row in frame.iterrows():
        key = str(row.get("Chave") or "").strip()
        value = pd.to_numeric(pd.Series([row.get("CDI+ manual (% a.a.)")]), errors="coerce").iloc[0]
        if key and pd.notna(value):
            parsed[key] = float(value) / 100.0
    return parsed


def _is_priced_class(class_macro: str) -> bool:
    return str(class_macro).strip().lower() in {"senior", "mezzanino"}


def _cash_totals(outputs: FinancialCostOutputs) -> tuple[float, float]:
    frame = outputs.ime_snapshot_df
    if frame.empty:
        return 0.0, 0.0
    cash_base = pd.to_numeric(frame.get("cash_like_caixa_lft", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()
    cash_yield = pd.to_numeric(frame.get("rendimento_estimado_caixa_lft", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()
    return float(cash_base), float(cash_yield)


def _short_description(value: object) -> str:
    text = str(value or "")
    if "Custo bruto por linha" in text:
        return "Saldo por série, mês a mês, com CDI B3 composto, captações e amortizações."
    if "Custo bruto programado menos rendimento" in text:
        return "Mesma despesa bruta, abatendo o rendimento estimado da aplicação em caixa/LFT."
    return text


def _series_price_frame(line_df: pd.DataFrame) -> pd.DataFrame:
    frame = line_df[line_df["included"].fillna(False).astype(bool)].copy()
    if frame.empty:
        return pd.DataFrame()
    frame["FIDC"] = frame["fund_name"].map(_short_fund_name)
    frame["Série"] = frame["classe"]
    frame["Classe"] = frame["class_macro"].map(_class_label)
    frame["Data emissão"] = frame["issue_date"].replace("", "N/D")
    frame["Volume emitido"] = pd.to_numeric(frame["volume_emitido"], errors="coerce").map(_format_money)
    frame["CDI+ a.a."] = pd.to_numeric(frame["spread_cdi_plus_aa"], errors="coerce").map(_format_percent)
    frame["Fonte CDI+"] = frame["spread_source"].map(_spread_source_label)
    frame["Saldo médio"] = pd.to_numeric(frame["saldo_medio_programado"], errors="coerce").map(_format_money)
    frame["Custo bruto"] = pd.to_numeric(frame["custo_programado_bruto"], errors="coerce").map(_format_money)
    frame["Amortização"] = pd.to_numeric(frame["amortizacao_no_periodo"], errors="coerce").map(_format_money)
    frame["Convenção amort."] = frame["amortization_convention"].map(_amortization_label)
    frame["Observação"] = frame["warnings"].fillna("").replace("", "OK")
    frame["Chave"] = frame["line_key"]
    return frame[
        [
            "FIDC",
            "Série",
            "Classe",
            "Data emissão",
            "Volume emitido",
            "CDI+ a.a.",
            "Fonte CDI+",
            "Saldo médio",
            "Custo bruto",
            "Amortização",
            "Convenção amort.",
            "Observação",
            "Chave",
        ]
    ].sort_values(["FIDC", "Série"])


def _cash_frame(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    if output.empty:
        return output
    output["FIDC"] = output["fund_name"].map(_short_fund_name)
    output["Competência IME"] = output["competencia"]
    output["PL"] = pd.to_numeric(output["pl_total"], errors="coerce").map(_format_money)
    output["Caixa"] = pd.to_numeric(output["caixa"], errors="coerce").map(_format_money)
    output["Títulos públicos"] = pd.to_numeric(output["titulos_publicos"], errors="coerce").map(_format_money)
    output["Recebíveis"] = pd.to_numeric(output["recebiveis"], errors="coerce").map(_format_money)
    output["Caixa + títulos"] = pd.to_numeric(output["cash_like_reported"], errors="coerce").map(_format_money)
    output["Proxy PL - recebíveis"] = pd.to_numeric(output["cash_like_residual_proxy"], errors="coerce").map(_format_money)
    output["Aplicação caixa/LFT"] = pd.to_numeric(output["cash_like_caixa_lft"], errors="coerce").map(_format_money)
    output["Critério usado"] = output["cash_like_method"].map(_cash_method_label)
    output["Rendimento estimado"] = pd.to_numeric(output["rendimento_estimado_caixa_lft"], errors="coerce").map(_format_money)
    return output[
        [
            "FIDC",
            "Competência IME",
            "PL",
            "Caixa",
            "Títulos públicos",
            "Recebíveis",
            "Caixa + títulos",
            "Proxy PL - recebíveis",
            "Aplicação caixa/LFT",
            "Critério usado",
            "Rendimento estimado",
        ]
    ]


def _pl_waterfall_frame(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    if output.empty:
        return output
    output["FIDC"] = output.get("short_name", output.get("fund_name", pd.Series(dtype=str))).map(_short_fund_name)
    output["PL inicial"] = pd.to_numeric(output["pl_inicial"], errors="coerce").map(_format_money)
    output["Captações"] = pd.to_numeric(output["captacoes"], errors="coerce").map(_format_money)
    output["Resgates"] = pd.to_numeric(output["resgates"], errors="coerce").map(_format_money)
    output["Amortizações"] = pd.to_numeric(output["amortizacoes"], errors="coerce").map(_format_money)
    output["Accrual / residual"] = pd.to_numeric(output["accrual_rentabilidade_residual"], errors="coerce").map(_format_money)
    output["PL final"] = pd.to_numeric(output["pl_final"], errors="coerce").map(_format_money)
    output["Início"] = output["start_comp"]
    output["Fim"] = output["end_comp"]
    output["Status"] = output["status"]
    return output[["FIDC", "Início", "Fim", "PL inicial", "Captações", "Resgates", "Amortizações", "Accrual / residual", "PL final", "Status"]]


def _short_fund_name(name: object) -> str:
    text = str(name or "").upper()
    if "BELA" in text:
        return "Bela"
    if "PI FUNDO" in text:
        return "PI"
    if "A.I." in text:
        return "A.I."
    if "AKIRA II" in text:
        return "Akira II"
    if "AKIRA I" in text:
        return "Akira I"
    if "KICK ASS I" in text:
        return "Kick Ass I"
    if "KICK ASS II" in text:
        return "Kick Ass II"
    if "BIG PICTURE IV" in text:
        return "Big Picture IV"
    if "BIG PICTURE III" in text:
        return "Big Picture III"
    if "BIG PICTURE II" in text:
        return "Big Picture II"
    if "BIG PICTURE I" in text:
        return "Big Picture I"
    return shared_short_fund_name(name)


def _class_label(value: object) -> str:
    mapping = {"senior": "Sênior", "mezzanino": "Mezanino", "subordinada": "Subordinada"}
    return mapping.get(str(value or "").strip().lower(), str(value or ""))


def _spread_source_label(value: object) -> str:
    text = str(value or "")
    if text.startswith("override:"):
        return "Manual"
    if text == "curadoria:remuneracao":
        return "Documento/curadoria"
    if text == "pendente":
        return "Pendente"
    return text


def _amortization_label(value: object) -> str:
    mapping = {
        "incremental": "%/valor sobre principal original",
        "cumulative": "% acumulado",
        "current_balance": "% sobre saldo remanescente",
        "linear_de_intervalo_documentado": "Linear por intervalo",
        "nao_aplicavel": "Não aplicável",
        "sem_cronograma_parseavel": "Saldo constante",
    }
    return mapping.get(str(value or ""), str(value or ""))


def _cash_method_label(value: object) -> str:
    mapping = {
        "reportado_caixa_titpub": "Caixa + títulos públicos",
        "proxy_pl_menos_recebiveis": "Proxy PL - recebíveis",
        "sem_cache": "Sem IME em cache",
        "erro": "Erro de leitura",
    }
    return mapping.get(str(value or ""), str(value or ""))


def _annualize_monthly_cdi(monthly_cdi_rates: tuple[B3CdiMonthlyRate, ...]) -> float | None:
    if not monthly_cdi_rates:
        return None
    total_du = sum(item.dias_uteis for item in monthly_cdi_rates)
    if total_du <= 0:
        return None
    compounded = 1.0
    for item in monthly_cdi_rates:
        compounded *= 1.0 + item.cdi_mensal
    return compounded ** (252.0 / total_du) - 1.0


def _monthly_cdi_source_label(monthly_cdi_rates: tuple[B3CdiMonthlyRate, ...]) -> str:
    sources = tuple(
        dict.fromkeys(
            source
            for rate in monthly_cdi_rates
            if (source := str(rate.source or "").strip())
        )
    )
    if sources:
        return "; ".join(sources)
    return "B3 CDI realizado"


def _cdi_rates_frame(monthly_cdi_rates: tuple[B3CdiMonthlyRate, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "mes": item.mes,
                "cdi_mensal": item.cdi_mensal,
                "cdi_aa_equivalente": item.cdi_aa_equivalente,
                "dias_uteis": item.dias_uteis,
            }
            for item in monthly_cdi_rates
        ]
    )


def _waterfall_chart_frame(steps_df: pd.DataFrame) -> pd.DataFrame:
    running = 0.0
    rows = []
    for index, row in steps_df.reset_index(drop=True).iterrows():
        value = float(row["valor"])
        measure = str(row["measure"])
        if measure == "total":
            bar_start, bar_end = 0.0, value
            running = value
            tipo = "total"
        else:
            previous = running
            running += value
            bar_start, bar_end = min(previous, running), max(previous, running)
            tipo = "up" if value >= 0 else "down"
        rows.append(
            {
                "etapa": row["etapa"],
                "valor": value,
                "bar_start": bar_start,
                "bar_end": bar_end,
                "label_y": bar_end,
                "acumulado": running,
                "tipo": tipo,
                "label": _format_money(value),
            }
        )
    return pd.DataFrame(rows)


def _default_snapshot_date(start_date: date, end_date: date) -> date:
    if start_date <= DEFAULT_REFERENCE_DATE <= end_date:
        return DEFAULT_REFERENCE_DATE
    if DEFAULT_REFERENCE_DATE > end_date:
        return end_date
    return start_date


def _solve_implied_spread(monthly_df: pd.DataFrame, target_cost: float, cdi_aa: float) -> float | None:
    if monthly_df.empty or target_cost <= 0.0:
        return None
    frame = monthly_df.copy()
    frame["saldo_base"] = pd.to_numeric(frame["saldo_base"], errors="coerce").fillna(0.0)
    frame["dias_uteis"] = pd.to_numeric(frame["dias_uteis"], errors="coerce").fillna(0.0)
    frame["cdi_mensal"] = pd.to_numeric(frame.get("cdi_mensal", pd.Series(dtype=float)), errors="coerce")
    frame["dias_uteis_cdi_mes"] = pd.to_numeric(frame.get("dias_uteis_cdi_mes", pd.Series(dtype=float)), errors="coerce")
    frame = frame[(frame["saldo_base"] > 0.0) & (frame["dias_uteis"] > 0.0)]
    if frame.empty:
        return None

    def cost_for_spread(spread: float) -> float:
        monthly_mask = frame["cdi_mensal"].notna() & frame["dias_uteis_cdi_mes"].gt(0)
        cost = 0.0
        if monthly_mask.any():
            subset = frame[monthly_mask]
            cdi_factor = (1.0 + subset["cdi_mensal"]) ** (subset["dias_uteis"] / subset["dias_uteis_cdi_mes"]) - 1.0
            spread_factor = (1.0 + spread) ** (subset["dias_uteis"] / 252.0) - 1.0
            cost += float((subset["saldo_base"] * ((1.0 + cdi_factor) * (1.0 + spread_factor) - 1.0)).sum())
        if (~monthly_mask).any():
            subset = frame[~monthly_mask]
            rate = max(cdi_aa + spread, -0.999999)
            cost += float((subset["saldo_base"] * ((1.0 + rate) ** (subset["dias_uteis"] / 252.0) - 1.0)).sum())
        return cost

    lo, hi = -0.5, 0.5
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if cost_for_spread(mid) < target_cost:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _weighted_average_spread(line_df: pd.DataFrame) -> float | None:
    if line_df.empty:
        return None
    frame = line_df[line_df["included_in_cost"].fillna(False).astype(bool)].copy()
    frame["spread_cdi_plus_aa"] = pd.to_numeric(frame["spread_cdi_plus_aa"], errors="coerce")
    frame["saldo_medio_programado"] = pd.to_numeric(frame["saldo_medio_programado"], errors="coerce").fillna(0.0)
    frame = frame[(frame["spread_cdi_plus_aa"].notna()) & (frame["saldo_medio_programado"] > 0.0)]
    denominator = frame["saldo_medio_programado"].sum()
    if denominator <= 0.0:
        return None
    return float((frame["spread_cdi_plus_aa"] * frame["saldo_medio_programado"]).sum() / denominator)


def _format_line_table(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in output.columns:
        if column in {
            "volume_emitido",
            "saldo_snapshot",
            "saldo_inicio_periodo",
            "saldo_medio_programado",
            "custo_snapshot_sem_amortizacao",
            "custo_programado_bruto",
            "amortizacao_no_periodo",
            "saldo_base",
            "rendimento_estimado_caixa_lft",
            "pl_total",
            "caixa",
            "titulos_publicos",
            "recebiveis",
            "cash_like_reported",
            "cash_like_residual_proxy",
            "cash_like_caixa_lft",
        }:
            output[column] = pd.to_numeric(output[column], errors="coerce").map(_format_money)
        elif column in {"spread_cdi_plus_aa", "taxa_total_aa", "cdi_aa"}:
            output[column] = pd.to_numeric(output[column], errors="coerce").map(_format_percent)
        elif column in {"cdi_mensal", "cdi_aa_equivalente"}:
            output[column] = pd.to_numeric(output[column], errors="coerce").map(_format_percent)
    return output


def _scope_export_prefix(scope_kind: str, scope_label: str) -> str:
    if scope_kind == SCOPE_CLOUDWALK:
        return "cloudwalk_financial_cost"
    normalized = unicodedata.normalize("NFKD", str(scope_label or "selecao_fidcs"))
    ascii_label = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_label).strip("_")[:48] or "selecao_fidcs"
    return f"{slug}_financial_cost"


def _zip_outputs(outputs: FinancialCostOutputs, *, prefix: str = "cloudwalk_financial_cost") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(f"{prefix}_summary.csv", outputs.summary_df.to_csv(index=False))
        archive.writestr(f"{prefix}_by_line.csv", outputs.line_df.to_csv(index=False))
        archive.writestr(f"{prefix}_monthly.csv", outputs.monthly_df.to_csv(index=False))
        archive.writestr(f"{prefix}_ime_snapshot.csv", outputs.ime_snapshot_df.to_csv(index=False))
        archive.writestr(f"{prefix}_missing_inputs.csv", outputs.missing_inputs_df.to_csv(index=False))
        archive.writestr(f"{prefix}_methodology.md", outputs.methodology_md)
    return buffer.getvalue()


def _format_money(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(number):
        return ""
    sign = "-" if number < 0 else ""
    number = abs(number)
    if number >= 1_000_000_000:
        return f"{sign}R$ {number / 1_000_000_000:,.2f} bi"
    if number >= 1_000_000:
        return f"{sign}R$ {number / 1_000_000:,.1f} mi"
    return f"{sign}R$ {number:,.0f}"


def _format_percent(value: object, decimals: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(number):
        return ""
    return f"{number * 100:.{decimals}f}%"


def _format_cdi_plus(value: float | None) -> str:
    if value is None or pd.isna(value):
        return ""
    sign = "+" if value >= 0.0 else "-"
    return f"CDI{sign}{abs(value) * 100:.2f}% a.a."
