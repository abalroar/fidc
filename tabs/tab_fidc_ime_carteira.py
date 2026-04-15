from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import escape
import re
import traceback
from typing import Any
import uuid

import pandas as pd
import streamlit as st

from services.ime_loader import load_or_extract_informe
from services.ime_period import ImePeriodSelection
from services.portfolio_store import PortfolioFund, PortfolioRecord
from tabs import tab_fidc_ime as ime_tab
from tabs.ime_portfolio_support import (
    delete_portfolio_record,
    get_portfolio_status_caption,
    list_saved_portfolios,
    load_fidc_catalog_cached,
    save_portfolio_record,
)


def render_tab_fidc_ime_carteira() -> None:
    # Inject shared CSS so the compact header and downstream dashboard share the same tokens.
    st.markdown(ime_tab._FIDC_REPORT_CSS, unsafe_allow_html=True)

    portfolios = list_saved_portfolios()
    catalog_df = load_fidc_catalog_cached()

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
        st.info("Clique em 'Carregar' para atualizar com a carteira e o período ativos.")
        return

    _render_loaded_portfolio_analysis(selected_portfolio=selected_portfolio, loaded_state=loaded_state)


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
    st.caption(get_portfolio_status_caption())

    if portfolios:
        editor_mode = st.radio(
            "Modo",
            options=["Nova carteira", "Editar carteira ativa"],
            horizontal=True,
            key="ime_portfolio_editor_mode",
        )
    else:
        editor_mode = "Nova carteira"

    target = selected_portfolio if editor_mode == "Editar carteira ativa" and selected_portfolio is not None else None
    option_labels, option_lookup = _build_catalog_option_lookup(catalog_df)
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
                help="Selecione até 20 FIDCs. A busca usa o cadastro público da CVM.",
            )
        else:
            selected_labels = []
            st.info("Catálogo CVM indisponível. Use a entrada manual de CNPJs abaixo.")
        manual_cnpjs = st.text_area(
            "CNPJs adicionais (um por linha)",
            value="\n".join(
                fund.cnpj
                for fund in (target.funds if target is not None else ())
                if fund.display_name == fund.cnpj
            )
            if target is not None
            else "",
            placeholder="00.000.000/0000-00",
            height=110,
        )
        notes = st.text_area(
            "Notas",
            value=target.notes if target is not None else "",
            placeholder="Opcional",
            height=80,
        ).strip()
        save_clicked = st.form_submit_button("Salvar carteira", type="primary")

    if save_clicked:
        if not name:
            st.warning("Informe um nome para a carteira.")
        else:
            funds = [option_lookup[label] for label in selected_labels]
            funds.extend(_build_manual_portfolio_funds(manual_cnpjs, catalog_df))
            if not funds:
                st.warning("Selecione ao menos um fundo.")
            else:
                stored = save_portfolio_record(
                    PortfolioRecord(
                        id=target.id if target is not None else uuid.uuid4().hex,
                        name=name,
                        funds=tuple(funds),
                        created_at=target.created_at if target is not None else _utc_now_iso(),
                        updated_at=target.updated_at if target is not None else _utc_now_iso(),
                        notes=notes,
                    )
                )
                st.session_state["ime_portfolio_active_id"] = stored.id
                st.success(f"Carteira '{stored.name}' salva com {len(stored.funds)} fundo(s).")
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
    total = len(selected_portfolio.funds)
    if total == 0:
        st.warning("A carteira não tem fundos.")
        return

    progress_bar = st.progress(0.0, text="Preparando carga...")
    status_box = st.empty()
    results: dict[str, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=min(4, total)) as executor:
        futures = {
            executor.submit(_load_single_portfolio_fund, fund, period): fund
            for fund in selected_portfolio.funds
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            fund = futures[future]
            try:
                payload = future.result()
            except Exception as exc:  # noqa: BLE001
                payload = {
                    "result": None,
                    "context": {
                        "request_id": uuid.uuid4().hex,
                        "cnpj_informado": fund.cnpj,
                        "competencia_inicial": period.start_month.isoformat(),
                        "competencia_final": period.end_month.isoformat(),
                        "periodo_analisado_label": period.label,
                        "portfolio_fund_name": fund.display_name,
                    },
                    "error": exc,
                    "tb": traceback.format_exc(),
                }
            results[fund.cnpj] = payload
            progress_bar.progress(
                completed / total,
                text=f"{selected_portfolio.name}: {completed}/{total} fundo(s)",
            )
            status_box.caption(f"{fund.display_name} · {fund.cnpj}")

    progress_bar.empty()
    status_box.empty()
    st.session_state["ime_portfolio_loaded"] = {
        "portfolio_id": selected_portfolio.id,
        "portfolio_name": selected_portfolio.name,
        "period_key": period.cache_key,
        "period_label": period.label,
        "results": results,
        "loaded_at": _utc_now_iso(),
    }


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


def _render_loaded_portfolio_analysis(*, selected_portfolio: PortfolioRecord, loaded_state: dict[str, Any]) -> None:
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
        for cnpj in failed_cnpjs:
            payload = results.get(cnpj) or {}
            context = payload.get("context") or {}
            fund_name = context.get("portfolio_fund_name") or cnpj
            error = payload.get("error")
            st.caption(f"**{fund_name}** · {cnpj} — {str(error) if error else 'Erro desconhecido'}")


def _build_catalog_option_lookup(catalog_df: pd.DataFrame) -> tuple[list[str], dict[str, PortfolioFund]]:
    if catalog_df.empty:
        return [], {}
    option_lookup: dict[str, PortfolioFund] = {}
    for row in catalog_df.itertuples(index=False):
        cnpj = re.sub(r"\D", "", str(getattr(row, "cnpj_fundo", "") or ""))
        if len(cnpj) != 14:
            continue
        name = str(getattr(row, "nome_fundo", "") or cnpj).strip() or cnpj
        label = f"{name} · {cnpj}"
        option_lookup[label] = PortfolioFund(cnpj=cnpj, display_name=name)
    return list(option_lookup.keys()), option_lookup


def _build_manual_portfolio_funds(raw_text: str, catalog_df: pd.DataFrame) -> list[PortfolioFund]:
    name_lookup = {}
    if not catalog_df.empty:
        name_lookup = catalog_df.set_index("cnpj_fundo")["nome_fundo"].to_dict()
    funds: list[PortfolioFund] = []
    for line in str(raw_text or "").splitlines():
        digits = re.sub(r"\D", "", line)
        if len(digits) != 14:
            continue
        funds.append(
            PortfolioFund(
                cnpj=digits,
                display_name=str(name_lookup.get(digits) or digits),
            )
        )
    return funds


def _focus_option_label(cnpj: str, results: dict[str, dict[str, Any]]) -> str:
    payload = results.get(cnpj) or {}
    result = payload.get("result")
    context = payload.get("context") or {}
    if result is None:
        return f"{context.get('portfolio_fund_name') or cnpj} · erro"
    dashboard = ime_tab._load_dashboard_data(
        str(result.wide_csv_path),
        str(result.listas_csv_path),
        str(result.docs_csv_path),
        ime_tab.DASHBOARD_SCHEMA_VERSION,
    )
    name = (
        dashboard.fund_info.get("nome_fundo")
        or dashboard.fund_info.get("nome_classe")
        or context.get("portfolio_fund_name")
        or cnpj
    )
    return f"{name} · {cnpj}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
