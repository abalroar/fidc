from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
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
    st.subheader("Informe Mensal Estruturado — Carteira")
    st.caption("Monte carteiras persistentes, carregue até 20 fundos e navegue no dashboard completo por fundo focal.")

    portfolios = list_saved_portfolios()
    catalog_df = load_fidc_catalog_cached()
    period = ime_tab._render_period_selector(state_prefix="ime_portfolio", title="Período da carteira")

    selected_portfolio = _render_portfolio_selector(portfolios)
    left_col, right_col = st.columns([1.1, 1.3])

    with left_col:
        _render_portfolio_editor(
            portfolios=portfolios,
            catalog_df=catalog_df,
            selected_portfolio=selected_portfolio,
        )

    with right_col:
        _render_portfolio_load_panel(selected_portfolio=selected_portfolio, period=period)

    loaded_state = st.session_state.get("ime_portfolio_loaded")
    if not loaded_state:
        return
    if selected_portfolio is None:
        return
    if loaded_state.get("portfolio_id") != selected_portfolio.id or loaded_state.get("period_key") != period.cache_key:
        st.info("Selecione 'Carregar carteira' para atualizar a análise com a carteira e o período ativos.")
        return

    _render_loaded_portfolio_analysis(selected_portfolio=selected_portfolio, loaded_state=loaded_state)


def _render_portfolio_selector(portfolios: list[PortfolioRecord]) -> PortfolioRecord | None:
    if not portfolios:
        st.info("Nenhuma carteira salva ainda. Use o formulário abaixo para criar a primeira.")
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
    st.markdown("#### Gestão de carteiras")
    st.caption(get_portfolio_status_caption())

    editor_mode = st.radio(
        "Modo do formulário",
        options=["Nova carteira", "Editar carteira ativa"],
        horizontal=True,
        key="ime_portfolio_editor_mode",
    )
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
            placeholder="Ex.: Carteira Monitoramento High Yield",
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
            st.info("Catálogo CVM indisponível no momento. Use a entrada manual de CNPJs abaixo.")
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
            "Notas internas",
            value=target.notes if target is not None else "",
            placeholder="Opcional",
            height=100,
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
        if st.button("Excluir carteira ativa", key="ime_portfolio_delete_button"):
            delete_portfolio_record(target.id)
            loaded_state = st.session_state.get("ime_portfolio_loaded")
            if loaded_state and loaded_state.get("portfolio_id") == target.id:
                st.session_state.pop("ime_portfolio_loaded", None)
            st.session_state.pop("ime_portfolio_active_id", None)
            st.success(f"Carteira '{target.name}' excluída.")
            st.rerun()

    if not portfolios:
        st.caption("A carteira salva fica disponível após reinício do app.")


def _render_portfolio_load_panel(*, selected_portfolio: PortfolioRecord | None, period: ImePeriodSelection) -> None:
    st.markdown("#### Carga da carteira")
    if selected_portfolio is None:
        st.info("Selecione ou crie uma carteira para carregar os informes.")
        return

    st.markdown(
        f"""
        <div class="fidc-context-bar">
          <span><strong>Carteira ativa:</strong> {selected_portfolio.name}</span>
          <span><strong>Fundos:</strong> {len(selected_portfolio.funds)}</span>
          <span><strong>Período:</strong> {period.label}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    load_clicked = st.button("Carregar carteira", type="primary", key="ime_portfolio_load_button")
    if not load_clicked:
        return

    total = len(selected_portfolio.funds)
    progress_bar = st.progress(0.0, text="Preparando carga da carteira...")
    status_box = st.empty()
    results: dict[str, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=min(4, total or 1)) as executor:
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
                text=f"Carteira {selected_portfolio.name}: {completed}/{total} fundo(s) carregados.",
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
    st.success(f"Carteira '{selected_portfolio.name}' carregada com {total} fundo(s).")


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
    st.markdown("---")
    st.markdown("#### Carteira carregada")
    st.caption(
        f"Carteira: {selected_portfolio.name} · período: {loaded_state.get('period_label', 'N/D')} · "
        f"fundos carregados: {len(loaded_state.get('results') or {})}"
    )

    results = loaded_state.get("results") or {}
    summary_df = _build_portfolio_summary_df(results)
    if not summary_df.empty:
        st.dataframe(
            summary_df,
            width="stretch",
            hide_index=True,
            column_config={
                "PL total": st.column_config.NumberColumn(format="R$ %.2f"),
                "DC total": st.column_config.NumberColumn(format="R$ %.2f"),
                "Inadimplência (%)": st.column_config.NumberColumn(format="%.2f%%"),
                "Subordinação (%)": st.column_config.NumberColumn(format="%.2f%%"),
            },
        )

    successful_funds = [
        (cnpj, payload)
        for cnpj, payload in results.items()
        if payload.get("result") is not None
    ]
    if not successful_funds:
        st.warning("Nenhum fundo da carteira foi carregado com sucesso.")
        return

    focus_options = [cnpj for cnpj, _ in successful_funds]
    default_focus = st.session_state.get("ime_portfolio_focus_cnpj")
    if default_focus not in focus_options:
        default_focus = focus_options[0]
        st.session_state["ime_portfolio_focus_cnpj"] = default_focus
    focus_cnpj = st.selectbox(
        "Fundo focal",
        options=focus_options,
        index=focus_options.index(default_focus),
        key="ime_portfolio_focus_cnpj",
        format_func=lambda cnpj: _focus_option_label(cnpj, results),
    )
    focused_payload = results[focus_cnpj]
    ime_tab._render_result(
        focused_payload["result"],
        focused_payload.get("context") or {},
        slot_key=f"portfolio_{selected_portfolio.id}_{focus_cnpj}",
    )


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


def _build_portfolio_summary_df(results: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for cnpj, payload in results.items():
        result = payload.get("result")
        context = payload.get("context") or {}
        if result is None:
            rows.append(
                {
                    "Fundo": context.get("portfolio_fund_name") or cnpj,
                    "CNPJ": cnpj,
                    "Status": "Erro",
                    "Última competência": None,
                    "PL total": None,
                    "DC total": None,
                    "Inadimplência (%)": None,
                    "Subordinação (%)": None,
                }
            )
            continue
        dashboard = ime_tab._load_dashboard_data(
            str(result.wide_csv_path),
            str(result.listas_csv_path),
            str(result.docs_csv_path),
            ime_tab.DASHBOARD_SCHEMA_VERSION,
        )
        rows.append(
            {
                "Fundo": dashboard.fund_info.get("nome_fundo") or dashboard.fund_info.get("nome_classe") or context.get("portfolio_fund_name") or cnpj,
                "CNPJ": cnpj,
                "Status": "OK" if context.get("cache_status") == "hit" else "Atualizado",
                "Última competência": ime_tab._format_competencia_label(dashboard.latest_competencia),
                "PL total": dashboard.summary.get("pl_total"),
                "DC total": dashboard.summary.get("direitos_creditorios"),
                "Inadimplência (%)": dashboard.summary.get("inadimplencia_pct"),
                "Subordinação (%)": dashboard.summary.get("subordinacao_pct"),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


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
    name = dashboard.fund_info.get("nome_fundo") or dashboard.fund_info.get("nome_classe") or context.get("portfolio_fund_name") or cnpj
    return f"{name} · {cnpj}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
