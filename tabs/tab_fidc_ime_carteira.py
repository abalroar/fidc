from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import escape
import traceback
from typing import Any
import uuid

import pandas as pd
import streamlit as st

from services.fundonet_errors import FundosNetError, ProviderUnavailableError
from services.ime_loader import load_or_extract_informe
from services.ime_period import ImePeriodSelection
from services.portfolio_store import PortfolioFund, PortfolioRecord
from tabs import tab_fidc_ime as ime_tab
from tabs.ime_portfolio_support import (
    build_catalog_option_lookup,
    build_portfolio_funds_from_cnpjs,
    delete_portfolio_record,
    list_saved_portfolios,
    load_fidc_catalog_cached,
    save_portfolio_record,
)


def render_tab_fidc_ime_carteira(period: ImePeriodSelection | None = None) -> None:
    # Inject shared CSS so the compact header and downstream dashboard share the same tokens.
    st.markdown(ime_tab._FIDC_REPORT_CSS, unsafe_allow_html=True)

    portfolios = list_saved_portfolios()
    catalog_df = load_fidc_catalog_cached()

    if period is None:
        period = ime_tab._render_period_selector(state_prefix="ime_portfolio", title="Período da carteira")

    if portfolios:
        sel_col, btn_col = st.columns([5, 1])
        with sel_col:
            selected_portfolio = _render_portfolio_selector(portfolios)
        with btn_col:
            # Vertical spacer aligns button baseline with the selectbox control.
            st.markdown('<div style="height:1.75rem"></div>', unsafe_allow_html=True)
            load_clicked = st.button(
                "Carregar",
                type="primary",
                key="ime_portfolio_load_button",
                use_container_width=True,
            )
    else:
        selected_portfolio = None
        load_clicked = False

    with st.expander("Criar / Editar carteira", expanded=not bool(portfolios)):
        _render_portfolio_editor(
            portfolios=portfolios,
            catalog_df=catalog_df,
            selected_portfolio=selected_portfolio,
        )

    if load_clicked and selected_portfolio is not None:
        _execute_portfolio_load(selected_portfolio=selected_portfolio, period=period)

    loaded_state = st.session_state.get("ime_portfolio_loaded")
    if not loaded_state or selected_portfolio is None:
        return
    if loaded_state.get("portfolio_id") != selected_portfolio.id or loaded_state.get("period_key") != period.cache_key:
        return

    _render_loaded_portfolio_analysis(
        selected_portfolio=selected_portfolio,
        loaded_state=loaded_state,
        period=period,
    )


def _render_portfolio_selector(portfolios: list[PortfolioRecord]) -> PortfolioRecord | None:
    if not portfolios:
        return None
    options = [portfolio.id for portfolio in portfolios]
    default_id = st.session_state.get("ime_portfolio_active_id")
    if default_id not in options:
        default_id = options[0]
        st.session_state["ime_portfolio_active_id"] = default_id
    selected_id = st.selectbox(
        "Carteira ativa",
        options=options,
        index=options.index(default_id),
        key="ime_portfolio_active_id",
        format_func=lambda value: next(
            (
                f"{portfolio.name} · {len(portfolio.funds)} fundo(s)"
                for portfolio in portfolios
                if portfolio.id == value
            ),
            value,
        ),
    )
    return next((portfolio for portfolio in portfolios if portfolio.id == selected_id), None)


def _render_portfolio_editor(
    *,
    portfolios: list[PortfolioRecord],
    catalog_df: pd.DataFrame,
    selected_portfolio: PortfolioRecord | None,
) -> None:
    # Infer edit-vs-create from state: a selected portfolio is implicitly the edit target.
    target = selected_portfolio if portfolios else None
    option_labels, option_lookup = build_catalog_option_lookup(catalog_df)
    default_labels = [
        next((label for label, fund in option_lookup.items() if fund.cnpj == portfolio_fund.cnpj), portfolio_fund.display_name)
        for portfolio_fund in (target.funds if target is not None else ())
    ]

    with st.form("ime_portfolio_editor_form", clear_on_submit=False):
        name = st.text_input(
            "Nome da carteira",
            value=target.name if target is not None else "",
            placeholder="Ex.: Crédito High Yield",
        ).strip()
        if option_labels:
            selected_labels = st.multiselect(
                "Fundos",
                options=option_labels,
                default=default_labels,
                help="Até 20 FIDCs. Busca usa o cadastro público da CVM.",
            )
        else:
            selected_labels = []
        manual_cnpjs = st.text_area(
            "CNPJs adicionais",
            value="\n".join(
                fund.cnpj
                for fund in (target.funds if target is not None else ())
                if fund.display_name == fund.cnpj
            )
            if target is not None
            else "",
            placeholder="00.000.000/0000-00 (um por linha)",
            height=90,
        )
        cols = st.columns([1, 1, 3])
        save_label = "Atualizar carteira" if target is not None else "Salvar carteira"
        save_clicked = cols[0].form_submit_button(save_label, type="primary")
        new_clicked = cols[1].form_submit_button("Nova carteira") if target is not None else False

    if new_clicked:
        st.session_state.pop("ime_portfolio_active_id", None)
        st.rerun()

    if save_clicked:
        if not name:
            st.warning("Informe um nome para a carteira.")
            return
        funds = [option_lookup[label] for label in selected_labels]
        funds.extend(build_portfolio_funds_from_cnpjs(manual_cnpjs.splitlines(), catalog_df))
        if not funds:
            st.warning("Selecione ao menos um fundo.")
            return
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
        st.session_state["ime_portfolio_active_id"] = stored.id
        st.toast(f"Carteira '{stored.name}' salva ({len(stored.funds)} fundo(s)).", icon="✓")
        st.rerun()

    if target is not None:
        if st.button("Excluir carteira", key="ime_portfolio_delete_button"):
            delete_portfolio_record(target.id)
            loaded_state = st.session_state.get("ime_portfolio_loaded")
            if loaded_state and loaded_state.get("portfolio_id") == target.id:
                st.session_state.pop("ime_portfolio_loaded", None)
            st.session_state.pop("ime_portfolio_active_id", None)
            st.rerun()


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
    worker_count = _portfolio_worker_count(total=total, period=period)
    status_box.caption(
        f"{selected_portfolio.name} · {total} fundo(s) · {period.month_count} competência(s) · {worker_count} worker(s)"
    )

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
        progress_bar.progress(0.0, text=f"{selected_portfolio.name}: retry conservador")
        status_box.caption(
            f"{selected_portfolio.name} · reprocessando {retried_count} fundo(s) com falha transitória em modo conservador"
        )
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
    st.session_state["ime_portfolio_loaded"] = {
        "portfolio_id": selected_portfolio.id,
        "portfolio_name": selected_portfolio.name,
        "period_key": period.cache_key,
        "period_label": period.label,
        "period_mode": period.mode,
        "period_start": period.start_month.isoformat(),
        "period_end": period.end_month.isoformat(),
        "period_preset_months": period.preset_months,
        "results": results,
        "loaded_at": _utc_now_iso(),
        "load_strategy": {
            "workers": worker_count,
            "period_month_count": period.month_count,
            "requested_funds": total,
            "retryable_failures_detected": retried_count,
            "complexity_score": total * max(period.month_count, 1),
        },
    }


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
    cached = load_or_extract_informe(
        cnpj_fundo=fund.cnpj,
        data_inicial=period.start_month,
        data_final=period.end_month,
    )
    elapsed_seconds = (datetime.now(timezone.utc) - start_ts).total_seconds()
    return {
        "result": cached.result,
        "context": {
            "request_id": request_id,
            "cnpj_informado": fund.cnpj,
            "competencia_inicial": period.start_month.isoformat(),
            "competencia_final": period.end_month.isoformat(),
            "periodo_analisado_label": period.label,
            "portfolio_fund_name": fund.display_name,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "cache_status": cached.cache_status,
            "cache_key": cached.cache_key,
            "cache_dir": str(cached.cache_dir),
        },
    }


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
            "periodo_analisado_label": period.label,
            "portfolio_fund_name": fund.display_name,
            "error_kind": exc.__class__.__name__,
            "error_details": details,
        },
        "error": exc,
        "tb": traceback.format_exc(),
    }


def _portfolio_worker_count(*, total: int, period: ImePeriodSelection) -> int:
    complexity_score = total * max(period.month_count, 1)
    if complexity_score >= 160:
        return 1
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
    loaded_state: dict[str, Any],
    period: ImePeriodSelection,
) -> None:
    results = loaded_state.get("results") or {}

    successful_cnpjs = [cnpj for cnpj, payload in results.items() if payload.get("result") is not None]
    failed_cnpjs = [cnpj for cnpj, payload in results.items() if payload.get("result") is None]

    _render_portfolio_compact_header(
        name=selected_portfolio.name,
        period_label=loaded_state.get("period_label", "N/D"),
        n_ok=len(successful_cnpjs),
        n_total=len(results),
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

    if not successful_cnpjs:
        st.warning("Nenhum fundo foi carregado com sucesso.")
        return

    default_focus = st.session_state.get("ime_portfolio_focus_cnpj")
    if default_focus not in successful_cnpjs:
        default_focus = successful_cnpjs[0]

    focus_cnpj = st.selectbox(
        "Fundo selecionado",
        options=successful_cnpjs,
        index=successful_cnpjs.index(default_focus),
        key="ime_portfolio_focus_cnpj",
        format_func=lambda cnpj: _focus_option_label(cnpj, results),
    )

    focused_payload = results[focus_cnpj]
    ime_tab._render_result(
        focused_payload["result"],
        focused_payload.get("context") or {},
        slot_key=f"portfolio_{selected_portfolio.id}_{focus_cnpj}",
    )


def _render_portfolio_compact_header(name: str, period_label: str, n_ok: int, n_total: int) -> None:
    count_label = f"{n_ok}/{n_total}" if n_ok < n_total else str(n_total)
    st.markdown(
        f"""
<div class="fidc-period-bar">
  <span><strong>Carteira:</strong> {escape(name)}</span>
  <span><strong>Período:</strong> {escape(period_label)}</span>
  <span><strong>Fundos:</strong> {escape(count_label)}</span>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_portfolio_error_summary(*, failed_cnpjs: list[str], results: dict[str, dict[str, Any]]) -> None:
    n = len(failed_cnpjs)
    plural = n > 1
    label = f"⚠ {n} fundo{'s' if plural else ''} não {'carregados' if plural else 'carregado'}"
    with st.expander(label, expanded=False):
        timeout_like = 0
        for cnpj in failed_cnpjs:
            payload = results.get(cnpj) or {}
            context = payload.get("context") or {}
            fund_name = context.get("portfolio_fund_name") or cnpj
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


def _focus_option_label(cnpj: str, results: dict[str, dict[str, Any]]) -> str:
    payload = results.get(cnpj) or {}
    context = payload.get("context") or {}
    name = context.get("portfolio_fund_name") or cnpj
    if payload.get("result") is None:
        return f"{name} · erro"
    return f"{name} · {cnpj}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
