from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import escape
import time
import traceback
from typing import Any
import uuid

import pandas as pd
import streamlit as st

from services.dashboard_ui import diagnostics_enabled
from services.fundonet_errors import FundosNetError, ProviderUnavailableError
from services.fundonet_portfolio_dashboard import PortfolioDashboardBundle, build_portfolio_dashboard_bundle
from services.ime_loader import load_or_extract_informe, peek_cached_informe
from services.ime_period import ImePeriodSelection
from services.portfolio_store import PortfolioFund, PortfolioRecord
from tabs import tab_fidc_ime as ime_tab
from tabs.ime_portfolio_support import (
    build_catalog_option_lookup,
    build_portfolio_record_label_lookup,
    build_portfolio_funds_from_cnpjs,
    delete_portfolio_record,
    enrich_portfolio_funds_with_catalog,
    format_portfolio_fund_label,
    list_saved_portfolios,
    load_fidc_catalog_cached,
    normalize_portfolio_fund_name,
    render_saved_portfolio_delete_manager,
    resolve_default_active_portfolio_id,
    save_portfolio_record,
)


PARTIAL_CACHE_STATUSES = {"partial_hit", "github_cache_partial"}

PORTFOLIO_ENTRY_SAVED = "Carteira salva"
PORTFOLIO_ENTRY_CNPJ = "CNPJ específico"
PORTFOLIO_ENTRY_NEW = "Nova carteira"
PORTFOLIO_ENTRY_OPTIONS = (
    PORTFOLIO_ENTRY_SAVED,
    PORTFOLIO_ENTRY_CNPJ,
    PORTFOLIO_ENTRY_NEW,
)
_PORTFOLIO_ANALYSIS_CONTEXT_KEY = "ime_portfolio_analysis_context"
_PORTFOLIO_ENTRY_MODE_KEY = "ime_portfolio_entry_mode"
_PENDING_PORTFOLIO_ENTRY_MODE_KEY = "ime_portfolio_pending_entry_mode"
_TEMPORARY_PORTFOLIO_ID_PREFIX = "adhoc-cnpj-"


def render_tab_fidc_ime_carteira(period: ImePeriodSelection | None = None) -> None:
    if period is None:
        period = ime_tab._render_period_selector(state_prefix="ime_portfolio", title="Período da carteira")

    selected_portfolio, _ = render_portfolio_control_panel(
        load_button_label="Carregar seleção",
        load_button_key="ime_portfolio_load_button",
        show_load_button=False,
    )
    if selected_portfolio is None:
        return

    render_portfolio_aging_analysis(
        selected_portfolio=selected_portfolio,
        period=period,
        section_mode="tabs",
    )


def render_portfolio_control_panel(
    *,
    load_button_label: str,
    load_button_key: str,
    show_load_button: bool = True,
) -> tuple[PortfolioRecord | None, bool]:
    _apply_pending_portfolio_selection()

    portfolio_status = st.empty()
    portfolio_status.info("Carregando carteiras salvas...", icon=":material/folder_open:")
    portfolio_store_error: Exception | None = None
    try:
        portfolios = list_saved_portfolios()
    except Exception as exc:  # noqa: BLE001 - a consulta avulsa deve continuar disponível
        portfolios = []
        portfolio_store_error = exc
    finally:
        portfolio_status.empty()

    selected_portfolio = _resolve_active_analysis_portfolio(
        portfolios=portfolios,
        catalog_df=_empty_fidc_catalog(),
    )
    if selected_portfolio is None:
        _render_portfolio_entry_panel(
            portfolios=portfolios,
            portfolio_store_error=portfolio_store_error,
        )
        return None, False

    _render_active_analysis_bar(selected_portfolio)

    editor_mode = _normalize_portfolio_editor_mode(
        st.session_state.get("ime_portfolio_editor_mode"),
        has_portfolios=bool(portfolios),
    )
    st.session_state["ime_portfolio_editor_mode"] = editor_mode
    editor_open_key = "ime_portfolio_editor_open"
    preload_clicked = False
    if show_load_button:
        preload_clicked = st.button(
            load_button_label,
            type="secondary",
            key=load_button_key,
        )

    selected_saved_portfolio = next(
        (portfolio for portfolio in portfolios if portfolio.id == selected_portfolio.id),
        None,
    )
    catalog_df = _empty_fidc_catalog()
    if selected_saved_portfolio is not None or st.session_state.get(editor_open_key, False):
        catalog_df = _load_fidc_catalog_for_ui()

    def _render_portfolio_management_actions() -> None:
        action_cols = st.columns(2)
        with action_cols[0]:
            if st.button(
                "Criar nova carteira",
                key="ime_portfolio_new_button",
                use_container_width=True,
            ):
                _reset_new_portfolio_form_state()
                st.session_state["ime_portfolio_editor_mode"] = "create"
                st.session_state[editor_open_key] = True
                st.rerun()
        with action_cols[1]:
            if st.button(
                "Editar carteira atual",
                key="ime_portfolio_edit_button",
                use_container_width=True,
                disabled=selected_saved_portfolio is None,
            ):
                st.session_state["ime_portfolio_editor_mode"] = "edit"
                st.session_state[editor_open_key] = True
                st.rerun()

    if st.session_state.get(editor_open_key, False):
        st.markdown('<div style="height:0.35rem"></div>', unsafe_allow_html=True)
        _render_portfolio_editor(
            portfolios=portfolios,
            catalog_df=catalog_df,
            selected_portfolio=selected_saved_portfolio,
            editor_mode=editor_mode,
            activate_on_save=editor_mode == "create",
        )
    if portfolios:
        render_saved_portfolio_delete_manager(
            portfolios=portfolios,
            key_prefix="ime_portfolio",
            selected_portfolio_id=selected_saved_portfolio.id if selected_saved_portfolio is not None else None,
            on_delete=_handle_deleted_portfolio,
            render_actions=_render_portfolio_management_actions,
        )

    if not _is_temporary_portfolio(selected_portfolio):
        selected_portfolio = _enrich_portfolio_record(selected_portfolio=selected_portfolio, catalog_df=catalog_df)

    return selected_portfolio, preload_clicked


def _render_portfolio_entry_panel(
    *,
    portfolios: list[PortfolioRecord],
    portfolio_store_error: Exception | None = None,
) -> None:
    default_mode = PORTFOLIO_ENTRY_SAVED if portfolios else PORTFOLIO_ENTRY_CNPJ
    pending_mode = st.session_state.pop(_PENDING_PORTFOLIO_ENTRY_MODE_KEY, None)
    if pending_mode in PORTFOLIO_ENTRY_OPTIONS:
        st.session_state[_PORTFOLIO_ENTRY_MODE_KEY] = pending_mode
    current_mode = st.session_state.get(_PORTFOLIO_ENTRY_MODE_KEY)
    if current_mode not in PORTFOLIO_ENTRY_OPTIONS:
        st.session_state[_PORTFOLIO_ENTRY_MODE_KEY] = default_mode

    with st.container(border=True):
        st.markdown("#### Escolha o que analisar")
        st.caption("Carregue uma carteira salva, consulte um CNPJ sem cadastro ou crie uma nova carteira.")
        if portfolio_store_error is not None:
            st.warning("Não foi possível acessar as carteiras salvas agora. A consulta por CNPJ continua disponível.")
            if diagnostics_enabled():
                st.caption(f"Diagnóstico do armazenamento: {portfolio_store_error}")
        mode = st.segmented_control(
            "Forma de acesso",
            options=PORTFOLIO_ENTRY_OPTIONS,
            key=_PORTFOLIO_ENTRY_MODE_KEY,
            selection_mode="single",
            required=True,
            width="stretch",
            label_visibility="collapsed",
        )
        mode = mode if mode in PORTFOLIO_ENTRY_OPTIONS else default_mode

        if mode == PORTFOLIO_ENTRY_SAVED:
            _render_saved_portfolio_entry(portfolios)
        elif mode == PORTFOLIO_ENTRY_CNPJ:
            _render_direct_cnpj_entry(_catalog_from_saved_portfolios(portfolios))
        else:
            catalog_df = _load_fidc_catalog_for_ui()
            _render_portfolio_editor(
                portfolios=portfolios,
                catalog_df=catalog_df,
                selected_portfolio=None,
                editor_mode="create",
                activate_on_save=True,
            )


def _empty_fidc_catalog() -> pd.DataFrame:
    return pd.DataFrame(columns=["cnpj_fundo", "nome_fundo", "situacao"])


def _catalog_from_saved_portfolios(portfolios: list[PortfolioRecord]) -> pd.DataFrame:
    rows = [
        {
            "cnpj_fundo": fund.cnpj,
            "nome_fundo": normalize_portfolio_fund_name(fund.display_name, fund.cnpj),
            "situacao": "",
        }
        for portfolio in portfolios
        for fund in portfolio.funds
    ]
    if not rows:
        return _empty_fidc_catalog()
    return pd.DataFrame(rows).drop_duplicates(subset=["cnpj_fundo"], keep="last").reset_index(drop=True)


def _load_fidc_catalog_for_ui() -> pd.DataFrame:
    with st.spinner("Carregando catálogo de FIDCs...", show_time=True):
        try:
            return load_fidc_catalog_cached()
        except Exception as exc:  # noqa: BLE001 - CNPJ manual continua funcional sem catálogo
            st.warning("O catálogo da CVM não respondeu. Você ainda pode informar CNPJs manualmente.")
            if diagnostics_enabled():
                st.caption(f"Diagnóstico do catálogo: {exc}")
            return _empty_fidc_catalog()


def _render_saved_portfolio_entry(portfolios: list[PortfolioRecord]) -> None:
    if not portfolios:
        st.info("Ainda não há carteiras salvas. Use um CNPJ específico ou crie a primeira carteira.")
        return

    options = [portfolio.id for portfolio in portfolios]
    label_lookup = _build_portfolio_selector_label_lookup(portfolios)
    select_col, action_col = st.columns([4.0, 1.35], vertical_alignment="bottom")
    with select_col:
        selected_id = st.selectbox(
            "Carteira salva",
            options=options,
            index=None,
            key="ime_portfolio_entry_saved_id",
            placeholder="Selecione a carteira que deseja carregar",
            format_func=lambda value: label_lookup.get(value, value),
        )
    with action_col:
        load_clicked = st.button(
            "Carregar carteira",
            key="ime_portfolio_entry_saved_load",
            type="primary",
            width="stretch",
            disabled=selected_id is None,
        )
    availability_label = "disponível" if len(portfolios) == 1 else "disponíveis"
    st.caption(f"{len(portfolios)} carteira{'s' if len(portfolios) != 1 else ''} {availability_label}.")
    if load_clicked and selected_id is not None:
        _set_active_analysis_context(kind="saved", value=str(selected_id))
        st.session_state["ime_portfolio_active_id"] = str(selected_id)
        st.rerun()


def _render_direct_cnpj_entry(catalog_df: pd.DataFrame) -> None:
    with st.form("ime_portfolio_direct_cnpj_form", clear_on_submit=False):
        input_col, action_col = st.columns([4.0, 1.35], vertical_alignment="bottom")
        with input_col:
            raw_cnpj = st.text_input(
                "CNPJ do fundo",
                placeholder="00.000.000/0000-00",
                key="ime_portfolio_direct_cnpj",
                help="A consulta é temporária e não cria uma carteira salva.",
            )
        with action_col:
            submit_clicked = st.form_submit_button(
                "Analisar CNPJ",
                type="primary",
                width="stretch",
            )
    st.caption("Consulta avulsa. Nada será salvo na lista de carteiras.")
    if not submit_clicked:
        return
    try:
        temporary = build_temporary_portfolio_from_cnpj(raw_cnpj, catalog_df=catalog_df)
    except ValueError as exc:
        st.error(str(exc))
        return
    _set_active_analysis_context(
        kind="cnpj",
        value=temporary.funds[0].cnpj,
        display_name=temporary.name,
    )
    st.rerun()


def _render_active_analysis_bar(selected_portfolio: PortfolioRecord) -> None:
    kind_label = "CNPJ específico" if _is_temporary_portfolio(selected_portfolio) else "Carteira salva"
    fund_count = len(selected_portfolio.funds)
    with st.container(border=True):
        detail_col, action_col = st.columns([5.0, 1.2], vertical_alignment="center")
        with detail_col:
            st.markdown(f"**{selected_portfolio.name}**")
            st.caption(f"{kind_label} | {fund_count} fundo{'s' if fund_count != 1 else ''}")
        with action_col:
            if st.button(
                "Trocar análise",
                key="ime_portfolio_change_analysis",
                icon=":material/swap_horiz:",
                width="stretch",
            ):
                _clear_active_analysis_context()
                st.rerun()


def build_temporary_portfolio_from_cnpj(
    raw_cnpj: str,
    *,
    catalog_df: pd.DataFrame | None = None,
) -> PortfolioRecord:
    digits = "".join(character for character in str(raw_cnpj or "") if character.isdigit())
    if not _is_valid_cnpj(digits):
        raise ValueError("Informe um CNPJ válido, incluindo os dígitos verificadores.")
    funds = build_portfolio_funds_from_cnpjs([digits], catalog_df)
    if not funds:
        raise ValueError("Não foi possível preparar a consulta para este CNPJ.")
    fund = funds[0]
    return PortfolioRecord(
        id=f"{_TEMPORARY_PORTFOLIO_ID_PREFIX}{digits}",
        name=normalize_portfolio_fund_name(fund.display_name, fund.cnpj),
        funds=(fund,),
        created_at="",
        updated_at="",
        notes="Consulta temporária por CNPJ",
    )


def _is_valid_cnpj(value: str) -> bool:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if len(digits) != 14 or len(set(digits)) == 1:
        return False

    def _check_digit(base: str, weights: tuple[int, ...]) -> str:
        remainder = sum(int(character) * weight for character, weight in zip(base, weights)) % 11
        return "0" if remainder < 2 else str(11 - remainder)

    first = _check_digit(digits[:12], (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    second = _check_digit(digits[:12] + first, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    return digits[-2:] == first + second


def _is_temporary_portfolio(portfolio: PortfolioRecord) -> bool:
    return str(portfolio.id).startswith(_TEMPORARY_PORTFOLIO_ID_PREFIX)


def _set_active_analysis_context(*, kind: str, value: str, display_name: str | None = None) -> None:
    context = {
        "kind": str(kind),
        "value": str(value),
    }
    if str(display_name or "").strip():
        context["display_name"] = str(display_name).strip()
    st.session_state[_PORTFOLIO_ANALYSIS_CONTEXT_KEY] = context
    st.session_state["ime_portfolio_editor_open"] = False


def _clear_active_analysis_context() -> None:
    st.session_state.pop(_PORTFOLIO_ANALYSIS_CONTEXT_KEY, None)
    st.session_state.pop("portfolio_page_context_signature", None)
    st.session_state["ime_portfolio_editor_open"] = False


def _resolve_active_analysis_portfolio(
    *,
    portfolios: list[PortfolioRecord],
    catalog_df: pd.DataFrame,
) -> PortfolioRecord | None:
    context = st.session_state.get(_PORTFOLIO_ANALYSIS_CONTEXT_KEY)
    if not isinstance(context, dict):
        return None
    kind = str(context.get("kind") or "")
    value = str(context.get("value") or "")
    if kind == "saved":
        selected = next((portfolio for portfolio in portfolios if portfolio.id == value), None)
        if selected is None:
            _clear_active_analysis_context()
        return selected
    if kind == "cnpj":
        try:
            temporary = build_temporary_portfolio_from_cnpj(value, catalog_df=catalog_df)
        except ValueError:
            _clear_active_analysis_context()
            return None
        stored_display_name = str(context.get("display_name") or "").strip()
        if not stored_display_name:
            return temporary
        display_name = normalize_portfolio_fund_name(stored_display_name, value)
        return PortfolioRecord(
            id=temporary.id,
            name=display_name,
            funds=(PortfolioFund(cnpj=temporary.funds[0].cnpj, display_name=display_name),),
            created_at=temporary.created_at,
            updated_at=temporary.updated_at,
            notes=temporary.notes,
        )
    _clear_active_analysis_context()
    return None


def load_portfolio_ime_data(*, selected_portfolio: PortfolioRecord, period: ImePeriodSelection) -> dict[str, Any]:
    return ensure_portfolio_ime_data(selected_portfolio=selected_portfolio, period=period, force=True)


def render_portfolio_aging_analysis(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
    section_mode: str = "tabs",
) -> None:
    runtime_state = ensure_portfolio_ime_data(selected_portfolio=selected_portfolio, period=period)

    _render_loaded_portfolio_analysis(
        selected_portfolio=selected_portfolio,
        runtime_state=runtime_state,
        period=period,
        section_mode=section_mode,
    )


def _render_portfolio_selector(portfolios: list[PortfolioRecord]) -> PortfolioRecord | None:
    if not portfolios:
        return None
    options = [portfolio.id for portfolio in portfolios]
    label_lookup = _build_portfolio_selector_label_lookup(portfolios)
    default_id = st.session_state.get("ime_portfolio_active_id")
    if default_id not in options:
        default_id = resolve_default_active_portfolio_id(portfolios)
        st.session_state["ime_portfolio_active_id"] = default_id
    selected_id = st.selectbox(
        "Seleção ativa",
        options=options,
        key="ime_portfolio_active_id",
        label_visibility="collapsed",
        format_func=lambda value: label_lookup.get(value, value),
    )
    return next((portfolio for portfolio in portfolios if portfolio.id == selected_id), None)


def _build_portfolio_selector_label_lookup(portfolios: list[PortfolioRecord]) -> dict[str, str]:
    return build_portfolio_record_label_lookup(portfolios)


def _render_portfolio_editor(
    *,
    portfolios: list[PortfolioRecord],
    catalog_df: pd.DataFrame,
    selected_portfolio: PortfolioRecord | None,
    editor_mode: str,
    activate_on_save: bool = False,
) -> None:
    target = selected_portfolio if editor_mode == "edit" and selected_portfolio is not None else None
    mode_suffix = target.id if target is not None else "new"
    option_labels, option_lookup = build_catalog_option_lookup(catalog_df)
    catalog_cnpjs = {fund.cnpj for fund in option_lookup.values()}
    default_labels = [
        next((label for label, fund in option_lookup.items() if fund.cnpj == portfolio_fund.cnpj), portfolio_fund.display_name)
        for portfolio_fund in (target.funds if target is not None else ())
    ]
    st.markdown(
        f"**{'Criar nova carteira' if target is None else 'Editar carteira atual'}**",
    )

    with st.form(f"ime_portfolio_editor_form::{mode_suffix}", clear_on_submit=False):
        name = st.text_input(
            "Nome da carteira",
            value=target.name if target is not None else "",
            placeholder="Ex.: Crédito High Yield",
            key=f"ime_portfolio_name::{mode_suffix}",
        ).strip()
        if option_labels:
            selected_labels = st.multiselect(
                "Fundos",
                options=option_labels,
                default=default_labels,
                placeholder="Busque por nome ou CNPJ",
                help="Até 20 FIDCs. Busca usa o cadastro público da CVM.",
                key=f"ime_portfolio_funds::{mode_suffix}",
            )
        else:
            selected_labels = []
        manual_cnpjs = st.text_area(
            "CNPJs adicionais",
            value="\n".join(
                fund.cnpj
                for fund in (target.funds if target is not None else ())
                if fund.cnpj not in catalog_cnpjs
            )
            if target is not None
            else "",
            placeholder="00.000.000/0000-00 (um por linha)",
            height=90,
            key=f"ime_portfolio_cnpjs::{mode_suffix}",
        )
        cols = st.columns([1.2, 1.2, 3])
        save_label = "Atualizar carteira" if target is not None else "Salvar nova carteira"
        save_clicked = cols[0].form_submit_button(save_label, type="primary")
        cancel_clicked = cols[1].form_submit_button("Cancelar")

    if cancel_clicked:
        if activate_on_save:
            st.session_state[_PENDING_PORTFOLIO_ENTRY_MODE_KEY] = (
                PORTFOLIO_ENTRY_SAVED if portfolios else PORTFOLIO_ENTRY_CNPJ
            )
        st.session_state["ime_portfolio_editor_mode"] = "edit" if portfolios else "create"
        st.session_state["ime_portfolio_editor_open"] = False if portfolios else True
        _reset_new_portfolio_form_state()
        st.rerun()

    if save_clicked:
        if not name:
            st.warning("Informe um nome para a carteira.")
            return
        funds = [option_lookup[label] for label in selected_labels]
        funds.extend(build_portfolio_funds_from_cnpjs(manual_cnpjs.splitlines(), catalog_df))
        funds = enrich_portfolio_funds_with_catalog(funds, catalog_df)
        if not funds:
            st.warning("Selecione ao menos um fundo.")
            return
        try:
            stored = save_portfolio_record(
                PortfolioRecord(
                    id=target.id if target is not None else uuid.uuid4().hex,
                    name=name,
                    funds=tuple(funds),
                    created_at=target.created_at if target is not None else _utc_now_iso(),
                    updated_at=target.updated_at if target is not None else _utc_now_iso(),
                    notes=target.notes if target is not None else "",
                )
            )
        except ValueError as exc:
            st.warning(str(exc))
            return
        if activate_on_save:
            _set_active_analysis_context(kind="saved", value=stored.id)
        _queue_portfolio_selection(stored.id)
        st.session_state["ime_portfolio_editor_mode"] = "edit"
        st.session_state["ime_portfolio_editor_open"] = False
        _reset_new_portfolio_form_state()
        st.toast(f"Carteira '{stored.name}' salva ({len(stored.funds)} fundo(s)).")
        st.rerun()

    if target is not None:
        if st.button("Excluir carteira", key="ime_portfolio_delete_button"):
            delete_portfolio_record(target.id)
            _clear_portfolio_runtime_states(target.id)
            _queue_portfolio_selection(None, clear=True)
            st.session_state["ime_portfolio_editor_mode"] = "edit" if len(portfolios) > 1 else "create"
            st.session_state["ime_portfolio_editor_open"] = False if len(portfolios) > 1 else True
            st.rerun()


def ensure_portfolio_ime_data(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
    force: bool = False,
) -> dict[str, Any]:
    runtime_state = _get_portfolio_runtime_state(selected_portfolio=selected_portfolio, period=period)
    current_results = dict(runtime_state.get("results") or {})
    if force:
        funds_to_load = tuple(selected_portfolio.funds)
        current_results = {}
    else:
        funds_to_load = tuple(
            fund
            for fund in selected_portfolio.funds
            if fund.cnpj not in current_results
            or _portfolio_payload_needs_cache_refresh(current_results.get(fund.cnpj) or {}, period)
        )
    if funds_to_load:
        with st.spinner(_autoload_spinner_label(selected_portfolio=selected_portfolio, period=period, funds=funds_to_load)):
            _execute_portfolio_load_for_funds(
                selected_portfolio=selected_portfolio,
                period=period,
                funds=funds_to_load,
                existing_results=current_results,
            )
        runtime_state = _get_portfolio_runtime_state(selected_portfolio=selected_portfolio, period=period)
    return runtime_state


def _autoload_spinner_label(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
    funds: tuple[PortfolioFund, ...],
) -> str:
    cached_count = _count_cached_portfolio_funds(funds=funds, period=period)
    total = len(funds)
    if cached_count == total:
        source = "cache GitHub/local"
    elif cached_count:
        source = f"{cached_count}/{total} em cache"
    else:
        source = "Fundos.NET"
    return f"Carregando {selected_portfolio.name} ({total} fundo(s), {period.month_count}M, {source})..."


def _execute_portfolio_load(*, selected_portfolio: PortfolioRecord, period: ImePeriodSelection) -> None:
    _execute_portfolio_load_for_funds(
        selected_portfolio=selected_portfolio,
        period=period,
        funds=tuple(selected_portfolio.funds),
        existing_results=None,
    )


def _execute_portfolio_load_for_funds(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
    funds: tuple[PortfolioFund, ...],
    existing_results: dict[str, dict[str, Any]] | None,
) -> None:
    total = len(funds)
    if total == 0:
        st.warning("A carteira não tem fundos.")
        return

    progress_bar = st.progress(0.0, text="Preparando carga...")
    status_box = st.empty()
    results: dict[str, dict[str, Any]] = dict(existing_results or {})
    load_started = time.perf_counter()
    cached_count = _count_cached_portfolio_funds(funds=funds, period=period)
    worker_count = _portfolio_worker_count(total=total, period=period, cached_count=cached_count)
    status_box.caption(f"{selected_portfolio.name} · {total} fundo(s) · {cached_count} em cache")

    initial_results = _load_portfolio_funds_batch(
        funds=funds,
        period=period,
        progress_bar=progress_bar,
        status_box=status_box,
        progress_start=0,
        progress_total=total,
        worker_count=worker_count,
        progress_label=selected_portfolio.name,
    )
    results.update(initial_results)

    retryable_failures = [
        fund
        for fund in funds
        if _is_retryable_portfolio_failure(results.get(fund.cnpj) or {})
    ]
    retried_count = 0
    if retryable_failures and worker_count > 1:
        retried_count = len(retryable_failures)
        progress_bar.progress(0.0, text=f"{selected_portfolio.name}: reprocessando {retried_count} fundo(s)...")
        status_box.caption(f"{selected_portfolio.name} · reprocessando falhas")
        retry_results = _load_portfolio_funds_batch(
            funds=tuple(retryable_failures),
            period=period,
            progress_bar=progress_bar,
            status_box=status_box,
            progress_start=0,
            progress_total=retried_count,
            worker_count=1,
            progress_label=f"{selected_portfolio.name} · retry",
        )
        results.update(retry_results)

    progress_bar.empty()
    status_box.empty()
    stored_portfolio = _sync_portfolio_fund_names_from_results(selected_portfolio=selected_portfolio, results=results)
    selected_portfolio = stored_portfolio or selected_portfolio
    runtime_state = _get_portfolio_runtime_state(selected_portfolio=selected_portfolio, period=period)
    runtime_state["results"] = results
    runtime_state["loaded_at"] = _utc_now_iso()
    runtime_state["load_strategy"] = {
        "workers": worker_count,
        "period_month_count": period.month_count,
        "requested_funds": total,
        "cache_ready_funds": cached_count,
        "selected_funds": [{"cnpj": fund.cnpj, "display_name": fund.display_name} for fund in funds],
        "expected_competencias": _expected_competencias_for_period(period),
        "cache_refresh_attempts": sum(1 for payload in results.values() if (payload.get("context") or {}).get("cache_refresh_attempted")),
        "retryable_failures_detected": retried_count,
        "complexity_score": total * max(period.month_count, 1),
        "elapsed_seconds": round(time.perf_counter() - load_started, 3),
        "target_seconds": 20,
    }
    _save_portfolio_runtime_state(selected_portfolio=selected_portfolio, period=period, runtime_state=runtime_state)


def _enrich_portfolio_record(
    *,
    selected_portfolio: PortfolioRecord,
    catalog_df: pd.DataFrame,
) -> PortfolioRecord:
    return PortfolioRecord(
        id=selected_portfolio.id,
        name=selected_portfolio.name,
        funds=tuple(enrich_portfolio_funds_with_catalog(selected_portfolio.funds, catalog_df)),
        created_at=selected_portfolio.created_at,
        updated_at=selected_portfolio.updated_at,
        notes=selected_portfolio.notes,
    )


def _load_portfolio_funds_batch(
    *,
    funds: tuple[PortfolioFund, ...],
    period: ImePeriodSelection,
    progress_bar,  # noqa: ANN001
    status_box,  # noqa: ANN001
    progress_start: int,
    progress_total: int,
    worker_count: int,
    progress_label: str,
) -> dict[str, dict[str, Any]]:
    if not funds:
        return {}
    total = len(funds)
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, worker_count)) as executor:
        futures = {
            executor.submit(_load_single_portfolio_fund, fund, period): fund
            for fund in funds
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            fund = futures[future]
            try:
                payload = future.result()
            except Exception as exc:  # noqa: BLE001
                payload = _build_portfolio_error_payload(exc=exc, fund=fund, period=period)
            results[fund.cnpj] = payload
            progress_fraction = (progress_start + (completed / total) * progress_total) / max(progress_start + progress_total, 1)
            progress_bar.progress(
                min(progress_fraction, 1.0),
                text=f"{progress_label}: {completed}/{total} fundo(s)",
            )
            status_box.caption(f"{fund.display_name} · {fund.cnpj}")
    return results


def _load_single_portfolio_fund(fund: PortfolioFund, period: ImePeriodSelection) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    start_ts = datetime.now(timezone.utc)
    expected_competencias = _expected_competencias_for_period(period)
    cache_probe = peek_cached_informe(
        cnpj_fundo=fund.cnpj,
        data_inicial=period.start_month,
        data_final=period.end_month,
    )
    cached = load_or_extract_informe(
        cnpj_fundo=fund.cnpj,
        data_inicial=period.start_month,
        data_final=period.end_month,
    )
    missing_before_refresh = _missing_expected_competencias(
        expected_competencias=expected_competencias,
        found_competencias=list(cached.result.competencias or []),
    )
    refresh_reason = _cache_refresh_reason(cached=cached, missing_competencias=missing_before_refresh)
    refresh_attempted = bool(refresh_reason)
    refresh_error = ""
    if refresh_reason:
        try:
            cached = load_or_extract_informe(
                cnpj_fundo=fund.cnpj,
                data_inicial=period.start_month,
                data_final=period.end_month,
                force_refresh=True,
            )
        except Exception as exc:  # noqa: BLE001
            refresh_error = f"{type(exc).__name__}: {exc}"

    found_competencias = list(cached.result.competencias or [])
    missing_after_refresh = _missing_expected_competencias(
        expected_competencias=expected_competencias,
        found_competencias=found_competencias,
    )
    elapsed_seconds = (datetime.now(timezone.utc) - start_ts).total_seconds()
    return {
        "result": cached.result,
        "context": {
            "request_id": request_id,
            "cnpj_informado": fund.cnpj,
            "competencia_inicial": period.start_month.isoformat(),
            "competencia_final": period.end_month.isoformat(),
            "period_month_count": period.month_count,
            "periodo_analisado_label": period.label,
            "expected_competencias": expected_competencias,
            "found_competencias": found_competencias,
            "missing_competencias_before_refresh": missing_before_refresh,
            "missing_competencias_after_refresh": missing_after_refresh,
            "portfolio_fund_name": fund.display_name,
            "portfolio_fund_name_resolved": _extract_loaded_fund_name(cached.result, fallback_name=fund.display_name),
            "elapsed_seconds": round(elapsed_seconds, 3),
            "cache_probe_status": cache_probe.cache_status,
            "cache_probe_source": cache_probe.cache_source,
            "cache_probe_key": cache_probe.cache_key,
            "cache_requested_key": cache_probe.requested_cache_key,
            "cache_probe_dir": str(cache_probe.cache_dir),
            "cache_status": cached.cache_status,
            "cache_source": cached.cache_source,
            "cache_key": cached.cache_key,
            "cache_dir": str(cached.cache_dir),
            "cache_source_refresh_attempted": cached.source_refresh_attempted,
            "cache_refresh_attempted": refresh_attempted,
            "cache_refresh_reason": refresh_reason,
            "cache_refresh_error": refresh_error,
            "cache_refresh_skipped_reason": _cache_refresh_skipped_reason(
                cached=cached,
                missing_competencias=missing_after_refresh,
                refresh_attempted=refresh_attempted,
                refresh_error=refresh_error,
            ),
        },
    }


def _portfolio_runtime_key(*, portfolio_id: str, period: ImePeriodSelection) -> str:
    return f"{portfolio_id}::{period.cache_key}"


def _get_portfolio_runtime_state(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
) -> dict[str, Any]:
    store = st.session_state.setdefault("ime_portfolio_runtime_store", {})
    runtime_key = _portfolio_runtime_key(portfolio_id=selected_portfolio.id, period=period)
    existing = store.get(runtime_key)
    if existing is not None:
        return existing
    runtime_state = {
        "portfolio_id": selected_portfolio.id,
        "portfolio_name": selected_portfolio.name,
        "period_key": period.cache_key,
        "period_label": period.label,
        "period_mode": period.mode,
        "period_start": period.start_month.isoformat(),
        "period_end": period.end_month.isoformat(),
        "period_preset_months": period.preset_months,
        "results": {},
        "loaded_at": None,
        "load_strategy": None,
    }
    store[runtime_key] = runtime_state
    st.session_state["ime_portfolio_runtime_store"] = store
    return runtime_state


def _save_portfolio_runtime_state(
    *,
    selected_portfolio: PortfolioRecord,
    period: ImePeriodSelection,
    runtime_state: dict[str, Any],
) -> None:
    store = st.session_state.setdefault("ime_portfolio_runtime_store", {})
    runtime_key = _portfolio_runtime_key(portfolio_id=selected_portfolio.id, period=period)
    store[runtime_key] = runtime_state
    st.session_state["ime_portfolio_runtime_store"] = store


def _clear_portfolio_runtime_states(portfolio_id: str) -> None:
    store = st.session_state.get("ime_portfolio_runtime_store") or {}
    runtime_keys = [key for key in store if key.startswith(f"{portfolio_id}::")]
    for key in runtime_keys:
        store.pop(key, None)
    st.session_state["ime_portfolio_runtime_store"] = store


def _build_portfolio_error_payload(
    *,
    exc: Exception,
    fund: PortfolioFund,
    period: ImePeriodSelection,
) -> dict[str, Any]:
    details = exc.details if isinstance(exc, FundosNetError) else {}
    return {
        "result": None,
        "context": {
            "request_id": uuid.uuid4().hex,
            "cnpj_informado": fund.cnpj,
            "competencia_inicial": period.start_month.isoformat(),
            "competencia_final": period.end_month.isoformat(),
            "period_month_count": period.month_count,
            "periodo_analisado_label": period.label,
            "portfolio_fund_name": fund.display_name,
            "portfolio_fund_name_resolved": fund.display_name,
            "error_kind": exc.__class__.__name__,
            "error_details": details,
        },
        "error": exc,
        "tb": traceback.format_exc(),
    }


def _count_cached_portfolio_funds(*, funds: tuple[PortfolioFund, ...], period: ImePeriodSelection) -> int:
    return sum(
        1
        for fund in funds
        if _is_cache_ready_for_portfolio_load(
            peek_cached_informe(
                cnpj_fundo=fund.cnpj,
                data_inicial=period.start_month,
                data_final=period.end_month,
            )
        )
    )


def _is_cache_ready_for_portfolio_load(probe) -> bool:  # noqa: ANN001
    return bool(probe.is_cached and probe.cache_status not in PARTIAL_CACHE_STATUSES)


def _expected_competencias_for_period(period: ImePeriodSelection) -> list[str]:
    return ime_tab._competencia_labels_between(period.start_month, period.end_month)


def _missing_expected_competencias(*, expected_competencias: list[str], found_competencias: list[str]) -> list[str]:
    found = {str(value) for value in found_competencias}
    return [competencia for competencia in expected_competencias if competencia not in found]


def _cache_refresh_reason(*, cached, missing_competencias: list[str]) -> str:  # noqa: ANN001
    if not missing_competencias:
        return ""
    if cached.cache_status in {"miss", "refresh"}:
        return ""
    if cached.cache_status in PARTIAL_CACHE_STATUSES:
        return "cache_partial_or_compatible_missing_requested_competencies"
    if not getattr(cached, "source_refresh_attempted", False):
        return "cache_missing_requested_competencies_without_prior_source_refresh"
    return ""


def _cache_refresh_skipped_reason(
    *,
    cached,  # noqa: ANN001
    missing_competencias: list[str],
    refresh_attempted: bool,
    refresh_error: str,
) -> str:
    if not missing_competencias:
        return ""
    if refresh_error:
        return "refresh_failed_kept_best_available_cache"
    if refresh_attempted:
        return "source_refreshed_but_competencies_still_unavailable"
    if cached.cache_status in {"miss", "refresh"}:
        return "source_refresh_already_attempted_in_this_load"
    if getattr(cached, "source_refresh_attempted", False):
        return "source_refresh_previously_attempted_for_this_cache"
    return "not_applicable"


def _portfolio_payload_needs_cache_refresh(payload: dict[str, Any], period: ImePeriodSelection) -> bool:
    result = payload.get("result")
    if result is None:
        return False
    context = payload.get("context") or {}
    expected_competencias = _expected_competencias_for_period(period)
    found_competencias = context.get("found_competencias")
    if found_competencias is None:
        found_competencias = list(getattr(result, "competencias", []) or [])
    missing = _missing_expected_competencias(
        expected_competencias=expected_competencias,
        found_competencias=[str(value) for value in found_competencias],
    )
    if not missing:
        return False
    if context.get("cache_refresh_attempted"):
        return False
    if context.get("cache_refresh_skipped_reason") in {
        "source_refresh_already_attempted_in_this_load",
        "source_refresh_previously_attempted_for_this_cache",
        "source_refreshed_but_competencies_still_unavailable",
    }:
        return False
    cache_status = str(context.get("cache_status") or "")
    if cache_status in PARTIAL_CACHE_STATUSES:
        return True
    return not bool(context.get("cache_source_refresh_attempted"))


def _portfolio_worker_count(*, total: int, period: ImePeriodSelection, cached_count: int = 0) -> int:
    if total <= 0:
        return 1
    if cached_count >= total:
        return min(10, total)
    if cached_count:
        return min(6, total)
    complexity_score = total * max(period.month_count, 1)
    if complexity_score >= 160:
        return min(2, total)
    if complexity_score >= 84:
        return min(2, total)
    if complexity_score >= 36:
        return min(3, total)
    return min(4, total)


def _is_retryable_portfolio_failure(payload: dict[str, Any]) -> bool:
    error = payload.get("error")
    if error is None:
        return False
    if isinstance(error, ProviderUnavailableError):
        return True
    if isinstance(error, FundosNetError):
        return error.__class__.__name__ in {"AuthenticationRequiredError"}
    message = str(error).lower()
    return "timed out" in message or "timeout" in message or "falha de rede" in message


def _render_loaded_portfolio_analysis(
    *,
    selected_portfolio: PortfolioRecord,
    runtime_state: dict[str, Any],
    period: ImePeriodSelection,
    section_mode: str = "tabs",
) -> None:
    results = runtime_state.get("results") or {}

    successful_cnpjs = [
        fund.cnpj
        for fund in selected_portfolio.funds
        if (results.get(fund.cnpj) or {}).get("result") is not None
    ]
    failed_cnpjs = [cnpj for cnpj, payload in results.items() if payload.get("result") is None]

    if section_mode == "tabs":
        _render_portfolio_compact_header(
            name=selected_portfolio.name,
            period_label=runtime_state.get("period_label", "N/D"),
            n_ok=len(successful_cnpjs),
            n_total=len(selected_portfolio.funds),
        )

    if failed_cnpjs:
        _render_portfolio_error_summary(failed_cnpjs=failed_cnpjs, results=results)
        retryable_cnpjs = [cnpj for cnpj in failed_cnpjs if _is_retryable_portfolio_failure(results.get(cnpj) or {})]
        if retryable_cnpjs:
            if st.button(
                "Recarregar só os fundos com falha transitória",
                key=f"ime_portfolio_retry_{selected_portfolio.id}",
                use_container_width=False,
            ):
                funds_to_retry = tuple(fund for fund in selected_portfolio.funds if fund.cnpj in retryable_cnpjs)
                _execute_portfolio_load_for_funds(
                    selected_portfolio=selected_portfolio,
                    period=period,
                    funds=funds_to_retry,
                    existing_results=results,
                )
                st.rerun()

    if section_mode == "tabs":
        view_options = ["Fundo individual"]
        if len(successful_cnpjs) >= 2:
            view_options.insert(0, "Carteira agregada")
        view_mode = st.radio(
            "Visão",
            options=view_options,
            horizontal=True,
            key=f"ime_portfolio_view::{selected_portfolio.id}",
            label_visibility="collapsed",
        )
    else:
        view_mode = "Carteira agregada" if len(successful_cnpjs) >= 2 else "Fundo individual"

    if view_mode == "Carteira agregada":
        dashboards_by_cnpj, dashboard_errors = _build_loaded_dashboards_by_cnpj(
            selected_portfolio=selected_portfolio,
            results=results,
        )
        if len(dashboards_by_cnpj) < 2:
            st.info("Carregue ao menos dois fundos com sucesso para habilitar a visão agregada da carteira.")
            return
        _render_portfolio_aggregate_analysis(
            selected_portfolio=selected_portfolio,
            dashboards_by_cnpj=dashboards_by_cnpj,
            dashboard_errors=dashboard_errors,
            results=results,
            period=period,
            total_selected=len(selected_portfolio.funds),
            section_mode=section_mode,
        )
        return

    focus_cnpj_key = f"ime_portfolio_focus_cnpj::{selected_portfolio.id}"
    if section_mode != "tabs" and len(successful_cnpjs) == 1:
        focus_cnpj = successful_cnpjs[0]
        st.session_state[focus_cnpj_key] = focus_cnpj
    else:
        all_cnpjs = [fund.cnpj for fund in selected_portfolio.funds]
        focus_options, focus_lookup = _build_focus_option_lookup(selected_portfolio=selected_portfolio, results=results)
        reverse_focus_lookup = {cnpj: label for label, cnpj in focus_lookup.items()}

        focus_label_key = f"ime_portfolio_focus_label::{selected_portfolio.id}"
        default_focus_cnpj = st.session_state.get(focus_cnpj_key)
        if default_focus_cnpj not in all_cnpjs:
            default_focus_cnpj = None
        if default_focus_cnpj is None and successful_cnpjs:
            default_focus_cnpj = successful_cnpjs[0]
            st.session_state[focus_cnpj_key] = default_focus_cnpj

        default_focus_label = reverse_focus_lookup.get(default_focus_cnpj)
        if default_focus_label is None:
            st.session_state.pop(focus_label_key, None)
        else:
            current_focus_label = st.session_state.get(focus_label_key)
            if current_focus_label not in focus_options:
                st.session_state[focus_label_key] = default_focus_label

        focus_label = st.selectbox(
            "Fundo selecionado",
            options=focus_options,
            index=focus_options.index(default_focus_label) if default_focus_label in focus_options else None,
            key=focus_label_key,
            label_visibility="collapsed",
            placeholder="Selecione um fundo da carteira",
        )
        if not focus_label:
            st.caption("Selecione um fundo da lista acima.")
            return
        focus_cnpj = focus_lookup.get(focus_label)
        if not focus_cnpj:
            st.caption("Selecione um fundo válido.")
            return
        st.session_state[focus_cnpj_key] = focus_cnpj

    focused_payload = results.get(focus_cnpj)
    if focused_payload is None:
        st.info("A carga automática da carteira ainda não registrou este fundo. Atualize a página para repetir a leitura completa da seleção.")
        return

    if focused_payload.get("result") is None:
        st.warning("O fundo selecionado falhou no carregamento.")
        if st.button(
            "Recarregar fundo selecionado",
            key=f"ime_portfolio_retry_focus_{selected_portfolio.id}_{focus_cnpj}",
            use_container_width=False,
        ):
            focus_fund = next(fund for fund in selected_portfolio.funds if fund.cnpj == focus_cnpj)
            _execute_portfolio_load_for_funds(
                selected_portfolio=selected_portfolio,
                period=period,
                funds=(focus_fund,),
                existing_results=results,
            )
            st.rerun()
        return

    ime_tab._render_result(
        focused_payload["result"],
        focused_payload.get("context") or {},
        slot_key=f"portfolio_{selected_portfolio.id}_{focus_cnpj}",
        compact_visuals=True,
    )


def _build_loaded_dashboards_by_cnpj(
    *,
    selected_portfolio: PortfolioRecord,
    results: dict[str, dict[str, Any]],
) -> tuple[dict[str, tuple[str, Any]], dict[str, str]]:
    dashboards_by_cnpj: dict[str, tuple[str, Any]] = {}
    dashboard_errors: dict[str, str] = {}
    for fund in selected_portfolio.funds:
        payload = results.get(fund.cnpj) or {}
        result = payload.get("result")
        if result is None:
            continue
        try:
            dashboard = ime_tab._load_dashboard_data(
                str(result.wide_csv_path),
                str(result.listas_csv_path),
                str(result.docs_csv_path),
                ime_tab.DASHBOARD_SCHEMA_VERSION,
            )
        except Exception as exc:  # noqa: BLE001
            dashboard_errors[fund.cnpj] = f"{exc.__class__.__name__}: {exc}"
            continue
        dashboards_by_cnpj[fund.cnpj] = (
            _resolve_portfolio_fund_display_name(fund.cnpj, results, fallback_name=fund.display_name),
            dashboard,
        )
    return dashboards_by_cnpj, dashboard_errors


def _render_portfolio_aggregate_analysis(
    *,
    selected_portfolio: PortfolioRecord,
    dashboards_by_cnpj: dict[str, tuple[str, Any]],
    dashboard_errors: dict[str, str],
    results: dict[str, dict[str, Any]],
    period: ImePeriodSelection,
    total_selected: int,
    section_mode: str = "tabs",
) -> None:
    try:
        bundle = build_portfolio_dashboard_bundle(
            portfolio_name=selected_portfolio.name,
            dashboards_by_cnpj=dashboards_by_cnpj,
        )
    except ValueError as exc:
        st.warning(str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        st.error("A visão agregada da carteira falhou nesta combinação de fundos.")
        if diagnostics_enabled():
            with st.expander("Detalhe técnico da falha", expanded=False):
                st.exception(exc)
        return

    loaded_count = len(dashboards_by_cnpj)
    excluded_funds = [
        _resolve_portfolio_fund_display_name(fund.cnpj, results, fallback_name=fund.display_name)
        for fund in selected_portfolio.funds
        if fund.cnpj not in dashboards_by_cnpj
    ]
    excluded_competencias = _portfolio_missing_competencias_for_period(bundle=bundle, period=period)

    def _render_executive_view() -> None:
        if section_mode == "tabs":
            _render_portfolio_aggregate_header(
                selected_portfolio=selected_portfolio,
                bundle=bundle,
                loaded_count=loaded_count,
                total_selected=total_selected,
            )
        with st.expander("Dados e exportações", expanded=False):
            _render_portfolio_aggregate_pptx_export_button(
                selected_portfolio=selected_portfolio,
                bundle=bundle,
                period=period,
            )
        if dashboard_errors:
            with st.expander("Fundos excluídos por falha no dashboard base", expanded=False):
                for cnpj, message in dashboard_errors.items():
                    st.caption(f"**{cnpj}** — {message}")
        ime_tab._render_financial_snapshot_cards(bundle.dashboard)
        ime_tab._render_structural_risk_section(
            bundle.dashboard,
            slot_key=f"portfolio_agg_{selected_portfolio.id}",
        )
        ime_tab._render_credit_risk_section(bundle.dashboard)
        ime_tab._render_liquidity_risk_section(
            bundle.dashboard,
            show_duration_history_chart=False,
        )
        ime_tab._render_calculation_memory_section(
            bundle.dashboard,
            slot_key=f"portfolio_agg_{selected_portfolio.id}",
        )

    def _render_technical_view() -> None:
        _render_portfolio_aggregate_audit(
            bundle=bundle,
            selected_portfolio=selected_portfolio,
            loaded_count=loaded_count,
            total_selected=total_selected,
            excluded_funds=excluded_funds,
            excluded_competencias=excluded_competencias,
            compact=section_mode != "tabs",
        )

    if section_mode == "tabs":
        executive_tab, technical_tab = st.tabs(["Executivo", "Auditoria"])
        with executive_tab:
            _render_executive_view()
        with technical_tab:
            _render_technical_view()
        return

    _render_executive_view()


def _render_portfolio_aggregate_header(
    *,
    selected_portfolio: PortfolioRecord,
    bundle: PortfolioDashboardBundle,
    loaded_count: int,
    total_selected: int,
) -> None:
    _ = bundle, loaded_count, total_selected
    st.markdown(
        f"""
<div class="fidc-hero">
  <div class="fidc-hero__title">{escape(selected_portfolio.name)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_portfolio_aggregate_pptx_export_button(
    *,
    selected_portfolio: PortfolioRecord,
    bundle: PortfolioDashboardBundle,
    period: ImePeriodSelection,
) -> None:
    try:
        from services.fundonet_ppt_export import build_dashboard_pptx_bytes
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Exportação em slides indisponível neste ambiente: {exc}")
        return

    try:
        pptx_bytes = build_dashboard_pptx_bytes(
            bundle.dashboard,
            requested_period_label=getattr(period, "label", None),
        )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Não foi possível montar os slides da carteira agregada: {exc}")
        return

    file_token = selected_portfolio.id[:8] or "carteira"
    st.download_button(
        "Exportar deck de comitê da carteira (PPTX)",
        data=pptx_bytes,
        file_name=f"relatorio_carteira_agregada_{file_token}.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        help="Deck executivo em PowerPoint com a visão agregada da carteira carregada.",
        key=f"ime_portfolio_aggregate_pptx::{selected_portfolio.id}",
    )


def _render_portfolio_period_coverage_warning(
    *,
    bundle: PortfolioDashboardBundle,
    period: ImePeriodSelection,
) -> None:
    expected_competencias = ime_tab._competencia_labels_between(period.start_month, period.end_month)
    common_competencias = set(str(value) for value in bundle.dashboard.competencias)
    missing_competencias = [competencia for competencia in expected_competencias if competencia not in common_competencias]
    if not missing_competencias:
        return
    st.warning(
        "A carteira agregada usa apenas competências comuns aos fundos incluídos. "
        "Consulte a auditoria técnica para a lista de competências fora da interseção."
    )


def _portfolio_missing_competencias_for_period(
    *,
    bundle: PortfolioDashboardBundle,
    period: ImePeriodSelection,
) -> list[str]:
    expected_competencias = ime_tab._competencia_labels_between(period.start_month, period.end_month)
    common_competencias = set(str(value) for value in bundle.dashboard.competencias)
    return [competencia for competencia in expected_competencias if competencia not in common_competencias]


def _render_portfolio_aggregate_audit(
    *,
    bundle: PortfolioDashboardBundle,
    selected_portfolio: PortfolioRecord,
    loaded_count: int,
    total_selected: int,
    excluded_funds: list[str],
    excluded_competencias: list[str],
    compact: bool = False,
) -> None:
    _ = loaded_count, total_selected

    def _render_scope_and_coverage() -> None:
        st.markdown("**Fundos incluídos no agregado**")
        st.dataframe(
            _format_portfolio_scope_table(bundle.fund_scope_df),
            width="stretch",
            hide_index=True,
        )
        if excluded_funds:
            st.markdown("**Fundos fora do agregado atual**")
            st.dataframe(
                pd.DataFrame({"Fundo": excluded_funds}),
                width="stretch",
                hide_index=True,
            )
        if excluded_competencias:
            st.markdown("**Competências fora da interseção comum**")
            st.dataframe(
                pd.DataFrame(
                    {
                        "Competência": [
                            ime_tab._format_competencia_label(value)
                            for value in excluded_competencias
                        ]
                    }
                ),
                width="stretch",
                hide_index=True,
            )
        st.markdown("**Cobertura por bloco e competência**")
        st.dataframe(
            _format_portfolio_coverage_table(bundle.coverage_df),
            width="stretch",
            hide_index=True,
        )

    def _render_reconciliation() -> None:
        st.dataframe(
            _format_portfolio_reconciliation_table(bundle.reconciliation_df),
            width="stretch",
            hide_index=True,
        )

    def _render_methodology_notes() -> None:
        for note in bundle.dashboard.methodology_notes:
            st.markdown(f"- {note}")

    if compact:
        with st.expander("Sobre a base", expanded=False):
            _render_scope_and_coverage()
            _render_reconciliation()
            _render_methodology_notes()
        return

    with st.expander("Escopo e cobertura da carteira", expanded=False):
        _render_scope_and_coverage()
    with st.expander("Reconciliação do consolidado", expanded=False):
        _render_reconciliation()
    ime_tab._render_audit_section(bundle.dashboard)
    with st.expander("Notas metodológicas da carteira", expanded=False):
        _render_methodology_notes()


def _format_portfolio_scope_table(scope_df: pd.DataFrame) -> pd.DataFrame:
    if scope_df.empty:
        return pd.DataFrame(columns=["CNPJ", "Fundo", "Competência inicial", "Competência final", "Competências carregadas"])
    output = scope_df.copy()
    return output.rename(
        columns={
            "cnpj": "CNPJ",
            "fundo": "Fundo",
            "competencia_inicial": "Competência inicial",
            "competencia_final": "Competência final",
            "competencias_carregadas": "Competências carregadas",
        }
    )


def _format_portfolio_coverage_table(coverage_df: pd.DataFrame) -> pd.DataFrame:
    if coverage_df.empty:
        return pd.DataFrame(columns=["Competência", "Bloco", "Fundos esperados", "Fundos prontos", "Status", "Fundos faltantes", "Observação"])
    output = coverage_df.copy()
    output["competencia"] = output["competencia"].map(ime_tab._format_competencia_label)
    return output.rename(
        columns={
            "competencia": "Competência",
            "block": "Bloco",
            "funds_expected": "Fundos esperados",
            "funds_ready": "Fundos prontos",
            "status": "Status",
            "missing_funds": "Fundos faltantes",
            "observacao": "Observação",
        }
    )[
        ["Competência", "Bloco", "Fundos esperados", "Fundos prontos", "Status", "Fundos faltantes", "Observação"]
    ]


def _format_portfolio_reconciliation_table(reconciliation_df: pd.DataFrame) -> pd.DataFrame:
    if reconciliation_df.empty:
        return pd.DataFrame(
            columns=["Componente", "Unidade", "Esperado", "Renderizado", "Delta", "Status", "Origem", "Fórmula"]
        )

    def _format_value(value: object, unit: str) -> str:
        if unit == "R$":
            return ime_tab._format_brl_compact(value)
        if unit == "%":
            return ime_tab._format_percent(value)
        return "N/D" if pd.isna(value) else f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    output = reconciliation_df.copy()
    output["Esperado"] = [
        _format_value(value, unit)
        for value, unit in zip(output["esperado"], output["unidade"], strict=False)
    ]
    output["Renderizado"] = [
        _format_value(value, unit)
        for value, unit in zip(output["renderizado"], output["unidade"], strict=False)
    ]
    output["Delta"] = [
        _format_value(value, unit)
        for value, unit in zip(output["delta_abs"], output["unidade"], strict=False)
    ]
    return output.rename(
        columns={
            "componente": "Componente",
            "unidade": "Unidade",
            "status": "Status",
            "origem": "Origem",
            "formula": "Fórmula",
        }
    )[["Componente", "Unidade", "Esperado", "Renderizado", "Delta", "Status", "Origem", "Fórmula"]]


def _render_portfolio_compact_header(name: str, period_label: str, n_ok: int, n_total: int) -> None:
    _ = n_ok, n_total
    st.markdown(
        f"""
<div class="fidc-period-bar">
  <span><strong>Seleção:</strong> {escape(name)}</span>
  <span><strong>Período:</strong> {escape(period_label)}</span>
</div>
""",
        unsafe_allow_html=True,
    )


def _normalize_portfolio_editor_mode(value: object, *, has_portfolios: bool) -> str:
    if not has_portfolios:
        return "create"
    return "create" if str(value or "").strip().lower() == "create" else "edit"


def _apply_pending_portfolio_selection() -> None:
    pending_key = "_ime_portfolio_active_id_pending"
    clear_key = "_ime_portfolio_active_id_clear"
    should_clear = bool(st.session_state.pop(clear_key, False))
    pending_value = st.session_state.pop(pending_key, None)
    if should_clear:
        st.session_state.pop("ime_portfolio_active_id", None)
    if pending_value:
        st.session_state["ime_portfolio_active_id"] = pending_value


def _queue_portfolio_selection(portfolio_id: str | None, *, clear: bool = False) -> None:
    st.session_state["_ime_portfolio_active_id_clear"] = bool(clear)
    if portfolio_id:
        st.session_state["_ime_portfolio_active_id_pending"] = portfolio_id
    else:
        st.session_state.pop("_ime_portfolio_active_id_pending", None)


def _reset_new_portfolio_form_state() -> None:
    for key in (
        "ime_portfolio_name::new",
        "ime_portfolio_funds::new",
        "ime_portfolio_cnpjs::new",
    ):
        st.session_state.pop(key, None)


def _handle_deleted_portfolio(portfolio_id: str) -> None:
    _clear_portfolio_runtime_states(portfolio_id)
    if st.session_state.get("ime_portfolio_active_id") == portfolio_id:
        _queue_portfolio_selection(None, clear=True)
    context = st.session_state.get(_PORTFOLIO_ANALYSIS_CONTEXT_KEY)
    if isinstance(context, dict) and context.get("kind") == "saved" and context.get("value") == portfolio_id:
        _clear_active_analysis_context()
    st.session_state["ime_portfolio_editor_open"] = False
    st.session_state["ime_portfolio_editor_mode"] = "edit"


def _render_portfolio_error_summary(*, failed_cnpjs: list[str], results: dict[str, dict[str, Any]]) -> None:
    n = len(failed_cnpjs)
    plural = n > 1
    label = f"⚠ {n} fundo{'s' if plural else ''} não {'carregados' if plural else 'carregado'}"
    with st.expander(label, expanded=False):
        timeout_like = 0
        for cnpj in failed_cnpjs:
            payload = results.get(cnpj) or {}
            context = payload.get("context") or {}
            fund_name = context.get("portfolio_fund_name_resolved") or context.get("portfolio_fund_name") or cnpj
            error = payload.get("error")
            if _is_retryable_portfolio_failure(payload):
                timeout_like += 1
            details = []
            elapsed = context.get("elapsed_seconds")
            if elapsed is not None:
                details.append(f"{elapsed}s")
            cache_status = context.get("cache_status")
            if cache_status:
                details.append(f"cache {cache_status}")
            detail_suffix = f" ({', '.join(details)})" if details else ""
            st.caption(f"**{fund_name}** · {cnpj} — {str(error) if error else 'Erro desconhecido'}{detail_suffix}")
        if timeout_like:
            st.info(
                "Falhas de rede/timeout tendem a crescer quando a carteira é grande e a janela tem muitas competências. "
                "A carga agora reduz o paralelismo e reprocessa falhas transitórias em modo conservador."
            )


def _build_focus_option_lookup(
    *,
    selected_portfolio: PortfolioRecord,
    results: dict[str, dict[str, Any]],
) -> tuple[list[str], dict[str, str]]:
    options: list[str] = []
    lookup: dict[str, str] = {}
    for fund in selected_portfolio.funds:
        label = format_portfolio_fund_label(
            display_name=_resolve_portfolio_fund_display_name(fund.cnpj, results, fallback_name=fund.display_name),
            cnpj=fund.cnpj,
        )
        options.append(label)
        lookup[label] = fund.cnpj
    return options, lookup


def _resolve_portfolio_fund_display_name(
    cnpj: str,
    results: dict[str, dict[str, Any]],
    *,
    fallback_name: str,
) -> str:
    payload = results.get(cnpj) or {}
    context = payload.get("context") or {}
    name = context.get("portfolio_fund_name_resolved") or context.get("portfolio_fund_name") or fallback_name or cnpj
    return normalize_portfolio_fund_name(name, cnpj)


def _extract_loaded_fund_name(result: Any, *, fallback_name: str) -> str:
    docs_df = getattr(result, "docs_df", None)
    if docs_df is not None and not docs_df.empty and "nome_fundo" in docs_df.columns:
        names = docs_df["nome_fundo"].astype(str).map(str.strip)
        names = names[(names != "") & names.str.lower().ne("nan")]
        if not names.empty:
            return str(names.iloc[-1])
    return fallback_name


def _sync_portfolio_fund_names_from_results(
    *,
    selected_portfolio: PortfolioRecord,
    results: dict[str, dict[str, Any]],
) -> PortfolioRecord | None:
    updated_funds: list[PortfolioFund] = []
    changed = False
    for fund in selected_portfolio.funds:
        resolved_name = _resolve_portfolio_fund_display_name(fund.cnpj, results, fallback_name=fund.display_name)
        resolved_name = normalize_portfolio_fund_name(resolved_name, fund.cnpj)
        updated_funds.append(PortfolioFund(cnpj=fund.cnpj, display_name=resolved_name))
        if resolved_name != fund.display_name:
            changed = True
    if not changed:
        return None
    updated_portfolio = PortfolioRecord(
        id=selected_portfolio.id,
        name=updated_funds[0].display_name if _is_temporary_portfolio(selected_portfolio) else selected_portfolio.name,
        funds=tuple(updated_funds),
        created_at=selected_portfolio.created_at,
        updated_at=_utc_now_iso(),
        notes=selected_portfolio.notes,
    )
    if _is_temporary_portfolio(selected_portfolio):
        context = st.session_state.get(_PORTFOLIO_ANALYSIS_CONTEXT_KEY)
        if isinstance(context, dict) and str(context.get("value") or "") == updated_funds[0].cnpj:
            st.session_state[_PORTFOLIO_ANALYSIS_CONTEXT_KEY] = {
                **context,
                "display_name": updated_funds[0].display_name,
            }
        return updated_portfolio
    try:
        return save_portfolio_record(updated_portfolio)
    except ValueError as exc:
        if "seleção idêntica" in str(exc).lower() or "selecao identica" in str(exc).lower():
            return None
        raise


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
