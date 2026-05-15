from __future__ import annotations

import altair as alt
from datetime import date, datetime, timezone
from html import escape
import json
from pathlib import Path
import re
import time
import traceback
from typing import Any, Callable
import uuid

import pandas as pd
import streamlit as st

from services.fundonet_dashboard import (
    FundonetDashboardData,
    build_dashboard_data,
    filter_dashboard_to_competencias,
    ordered_class_labels,
    sort_class_display_frame,
)
from services.fundonet_executive_compare import (
    available_comparison_metric_labels,
    build_executive_comparison_df,
    dashboard_column_labels,
    default_comparison_metric_labels,
)
from services.fundonet_errors import FundosNetError
from services.identifier_utils import format_cnpj
from services.fundonet_service import InformeMensalResult
from services.ime_loader import load_or_extract_informe
from services.ime_period import (
    DEFAULT_PRESET_MONTHS,
    ImePeriodSelection,
    PERIOD_PRESET_OPTIONS,
    build_custom_period,
    build_preset_period,
    current_default_end_month,
    display_month_count_for_period,
    load_period_for_available_data,
    month_options as _period_month_options,
    select_competencia_labels_for_period,
    shift_month as _period_shift_month,
)


# Feature flag: set to True when global PDF dashboard export is stable and ready.
# While False, the dashboard-level PDF button is hidden to prevent broken UX.
ENABLE_GLOBAL_PDF_EXPORT: bool = False
DASHBOARD_SCHEMA_VERSION: int = 5

FIDC_CHART_COLORS = [
    "#ff5a00",
    "#111111",
    "#6e6e6e",
    "#c9864a",
    "#b8b8b8",
    "#3a3a3a",
    "#e2a06c",
]

# Aging color scale: green (short overdue) → yellow → orange → red (long overdue).
# Explicitly ordered from ≤30 d (least severe) to >1080 d (most severe).
AGING_CHART_COLORS = [
    "#27ae60",  # ≤30 d  — verde
    "#82ca3f",  # 31-60 d — verde-limão
    "#f9ca24",  # 61-90 d — amarelo
    "#f0932b",  # 91-120 d — laranja
    "#ef7c1a",  # 121-150 d — laranja escuro
    "#e55039",  # 151-180 d — vermelho claro
    "#c0392b",  # 181-360 d — vermelho
    "#943126",  # 361-720 d — bordô
    "#7b241c",  # 721-1080 d — vinho
    "#4a1310",  # >1080 d — vermelho muito escuro
]

AGING_SERIES_ORDER = [
    "Até 30 dias",
    "31 a 60 dias",
    "61 a 90 dias",
    "91 a 120 dias",
    "121 a 150 dias",
    "151 a 180 dias",
    "181 a 360 dias",
    "361 a 720 dias",
    "721 a 1080 dias",
    "Acima de 1080 dias",
]

OVER_AGING_CHART_COLORS = [
    "#1f6f46",
    "#4f9a63",
    "#8abc4a",
    "#f0c340",
    "#d97a28",
    "#8a3b22",
]

OVER_SERIES_ORDER = ["Over 1", "Over 30", "Over 60", "Over 90", "Over 180", "Over 360"]

COVERAGE_LINE_COLOR = "#EC7000"

_PT_MONTH_ABBR: dict[str, str] = {
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
_PT_MONTH_NUMBER_BY_ABBR: dict[str, int] = {abbr: int(month) for month, abbr in _PT_MONTH_ABBR.items()}


_FIDC_REPORT_CSS = """
<style>
.block-container {
    padding-top: 1rem !important;
    max-width: 100% !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
}

.fidc-hero {
    background: linear-gradient(180deg, rgba(255,90,0,0.08), rgba(255,255,255,0.98));
    border: 1px solid rgba(255,90,0,0.16);
    border-radius: 16px;
    padding: 16px 18px;
    margin: 0.35rem 0 0.8rem 0;
    box-shadow: 0 10px 26px rgba(0,0,0,0.04);
}

.fidc-hero__title {
    color: #212529;
    font-size: 1.18rem;
    line-height: 1.25;
    font-weight: 600;
    margin-bottom: 8px;
}

.fidc-chart-title {
    color: #223247;
    font-size: 0.9rem;
    font-weight: 600;
    margin: 0.05rem 0 0.28rem 0;
    white-space: normal;
    overflow: visible;
    word-break: break-word;
    line-height: 1.35;
}

.fidc-section {
    color: #ff5a00;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 1.2rem 0 0.35rem 0;
    padding-bottom: 0.28rem;
    border-bottom: 1px solid #e9ecef;
}

.fidc-block-spacer {
    margin-top: 0.2rem;
}

.fidc-detail-title {
    color: #223247;
    font-size: 0.8rem;
    font-weight: 600;
    margin: 0.2rem 0 0.35rem 0;
}

.fidc-timing-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0.2rem 0 0.8rem 0;
}

.fidc-timing-chip {
    align-items: center;
    background: #f8f9fa;
    border: 1px solid #eceff3;
    border-radius: 999px;
    color: #5a5a5a;
    display: inline-flex;
    font-size: 0.76rem;
    gap: 5px;
    line-height: 1.2;
    padding: 5px 9px;
}

.fidc-timing-chip strong {
    color: #212529;
    font-weight: 500;
}

div[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e9ecef;
    border-left: 3px solid #ff5a00;
    border-radius: 10px;
    padding: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

div[data-testid="stMetricValue"] {
    font-weight: 400 !important;
    color: #212529 !important;
}

div[data-testid="stMetricLabel"] {
    color: #6c757d !important;
    font-weight: 500 !important;
}

.fidc-exec-compare-wrapper {
    overflow-x: auto;
    max-width: 100%;
    margin-top: 0.4rem;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
}

.fidc-exec-compare {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.78rem;
    table-layout: fixed;
}

.fidc-exec-compare th {
    background: #1f1f1f;
    color: #ffffff;
    font-weight: 600;
    padding: 7px 8px;
    text-align: center;
    border-right: 1px solid rgba(255,255,255,0.16);
    line-height: 1.25;
}

.fidc-exec-compare th:first-child {
    text-align: left;
    width: 230px;
}

.fidc-exec-compare th.highlight {
    background: #ec7000;
}

.fidc-exec-compare td {
    color: #1f1f1f;
    padding: 6px 8px;
    text-align: center;
    border-bottom: 1px solid #e0e0e0;
    border-right: 1px solid #eeeeee;
    line-height: 1.28;
    overflow-wrap: anywhere;
    vertical-align: middle;
}

.fidc-exec-compare td:first-child {
    color: #1f1f1f;
    font-weight: 600;
    text-align: left;
    background: #f7f7f7;
}

.fidc-exec-compare td.highlight {
    background: #fff2e8;
}

.fidc-exec-compare tr:nth-child(even) td:not(:first-child):not(.highlight) {
    background: #fafafa;
}

.fidc-exec-compare tr:hover td {
    background: #f4f1ea !important;
}

</style>
"""


_cache_data = getattr(st, "cache_data", None)
if callable(_cache_data):
    _cache_data_decorator = _cache_data(show_spinner=False)
else:
    def _cache_data_decorator(func):  # type: ignore[misc]
        return func


def _init_progress_bar(initial_value: float, message: str, status_box=None) -> object:
    """Compatibilidade com versões antigas do Streamlit."""
    if status_box is None:
        status_box = st.empty()
    normalized = max(0.0, min(1.0, float(initial_value)))
    try:
        return st.progress(normalized, text=message)
    except TypeError:
        try:
            progress = st.progress(normalized)
        except Exception:  # noqa: BLE001
            progress = st.progress(int(round(normalized * 100)))
        status_box.caption(message)
        return progress



def _format_error_category(exc: Exception) -> str:
    name = exc.__class__.__name__
    if isinstance(exc, FundosNetError):
        if name == "AuthenticationRequiredError":
            return "Bloqueio do provedor (autenticação/captcha)"
        if name == "ProviderUnavailableError":
            return "Instabilidade ou mudança no endpoint público"
        if name == "FundoNotFoundError":
            return "CNPJ não localizado no contexto público"
        if name == "NoDocumentsFoundError":
            return "Sem Informes Mensais no intervalo solicitado"
        if name == "DocumentParseError":
            return "XML baixado, porém inválido/incompatível"
    if isinstance(exc, ValueError):
        return "Erro de validação de entrada"
    if isinstance(exc, TypeError):
        return "Erro de compatibilidade da aplicação"
    return "Erro inesperado de execução"


def _build_failure_report(exc: Exception, tb_text: str, context: dict[str, Any]) -> dict[str, Any]:
    details = exc.details if isinstance(exc, FundosNetError) else {}
    trace_rows = exc.trace if isinstance(exc, FundosNetError) else []
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "categoria": _format_error_category(exc),
        "erro_tipo": exc.__class__.__name__,
        "erro_mensagem": str(exc),
        "contexto_execucao": context,
        "detalhes_provedor": details,
        "trilha_auditoria": trace_rows,
        "traceback": tb_text,
    }


def _render_failure_diagnostics(exc: Exception, tb_text: str, context: dict[str, Any]) -> None:
    _ = _build_failure_report(exc, tb_text, context)
    st.error("Não foi possível carregar os informes para esta seleção.")


def _update_progress_bar(progress_bar, value: float, message: str) -> None:
    """Compatibilidade com versões antigas do Streamlit."""
    normalized = max(0.0, min(1.0, float(value)))
    try:
        progress_bar.progress(normalized, text=message)
    except TypeError:
        try:
            progress_bar.progress(normalized)
        except Exception:  # noqa: BLE001
            progress_bar.progress(int(round(normalized * 100)))


def render_period_selector(*, state_prefix: str, title: str = "Período da análise") -> ImePeriodSelection:
    """Public period selector — reused by app.py as a global control shared across tabs."""
    return _render_period_selector(state_prefix=state_prefix, title=title)


def _render_period_selector(*, state_prefix: str, title: str = "Período da análise") -> ImePeriodSelection:
    end_month = current_default_end_month()
    max_options = _period_month_options(end_month, months_back=59)
    default_period = build_preset_period(end_month=end_month, months=DEFAULT_PRESET_MONTHS)

    custom_key = f"{state_prefix}_show_custom"
    if custom_key not in st.session_state:
        st.session_state[custom_key] = False

    show_custom = st.session_state.get(custom_key, False)

    if not show_custom:
        radio_col, btn_col = st.columns([6, 1])
        with radio_col:
            preset_months = st.radio(
                "Janela móvel",
                options=list(PERIOD_PRESET_OPTIONS),
                index=list(PERIOD_PRESET_OPTIONS).index(DEFAULT_PRESET_MONTHS),
                horizontal=True,
                key=f"{state_prefix}_period_preset_months",
                format_func=lambda v: f"{v}M",
                label_visibility="collapsed",
            )
        with btn_col:
            st.write("")
            if st.button("Personalizar →", key=f"{state_prefix}_btn_custom", use_container_width=True):
                st.session_state[custom_key] = True
                st.rerun()
        period = build_preset_period(end_month=end_month, months=int(preset_months))
    else:
        start_default = default_period.start_month
        start_index = max_options.index(start_default) if start_default in max_options else 0
        sel_col1, sel_col2, back_col = st.columns([2, 2, 1])
        with sel_col1:
            start_month = st.selectbox(
                "Competência inicial",
                options=max_options,
                index=start_index,
                key=f"{state_prefix}_period_start_month",
                format_func=_format_month_option_label,
            )
        end_candidates = [v for v in max_options if v >= start_month]
        default_end_index = len(end_candidates) - 1
        with sel_col2:
            end_month_selected = st.selectbox(
                "Competência final",
                options=end_candidates,
                index=default_end_index,
                key=f"{state_prefix}_period_end_month",
                format_func=_format_month_option_label,
            )
        with back_col:
            st.write("")
            if st.button("← Janela móvel", key=f"{state_prefix}_btn_preset"):
                st.session_state[custom_key] = False
                st.rerun()
        period = build_custom_period(start_month=start_month, end_month=end_month_selected)

    return period


def render_tab_fidc_ime(period: ImePeriodSelection | None = None) -> None:
    MAX_SLOTS = 4
    if period is None:
        period = _render_period_selector(state_prefix="ime_simple")
    load_period = load_period_for_available_data(period)

    _slots_key = "fidc_active_slots"
    _next_id_key = "fidc_next_slot_id"
    if _slots_key not in st.session_state:
        st.session_state[_slots_key] = [0]
        st.session_state[_next_id_key] = 1

    active_slots: list[int] = st.session_state[_slots_key]

    _, center_col, _ = st.columns([1, 2, 1])
    with center_col:
        cnpj_values: dict[int, str] = {}
        for slot_id in list(active_slots):
            if len(active_slots) == 1:
                val = st.text_input(
                    "CNPJ",
                    placeholder="00.000.000/0000-00",
                    key=f"fidc_cnpj_{slot_id}",
                    label_visibility="collapsed",
                )
                cnpj_values[slot_id] = val.strip()
            else:
                inp_col, rem_col = st.columns([10, 1])
                with inp_col:
                    val = st.text_input(
                        "CNPJ",
                        placeholder="00.000.000/0000-00",
                        key=f"fidc_cnpj_{slot_id}",
                        label_visibility="collapsed",
                    )
                    cnpj_values[slot_id] = val.strip()
                with rem_col:
                    st.write("")
                    if st.button("×", key=f"fidc_rm_{slot_id}"):
                        st.session_state[_slots_key] = [s for s in active_slots if s != slot_id]
                        st.rerun()

        if len(active_slots) < MAX_SLOTS:
            if st.button("＋  Adicionar fundo", key="fidc_add_cnpj"):
                new_id = st.session_state[_next_id_key]
                st.session_state[_slots_key] = active_slots + [new_id]
                st.session_state[_next_id_key] = new_id + 1
                st.rerun()

        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

        any_cnpj = any(v for v in cnpj_values.values())
        load_clicked = st.button(
            "Carregar Informes Mensais",
            type="primary",
            key="fidc_load_btn",
            use_container_width=True,
            disabled=not any_cnpj,
        )

    slots: dict[int, dict] = st.session_state.get("fidc_slots", {})

    if load_clicked:
        active_cnpjs = [(i, cnpj_values[sid]) for i, sid in enumerate(active_slots) if cnpj_values.get(sid)]
        if not active_cnpjs:
            st.warning("Informe ao menos um CNPJ para carregar.")
            return

        # Clear any cached dashboard objects from a previous load so the new
        # data replaces them on the next render cycle.
        for key in list(st.session_state.keys()):
            if key.startswith("_dashboard_slot"):
                del st.session_state[key]

        slots = {}
        for slot_i, cnpj in active_cnpjs:
            request_id = uuid.uuid4().hex
            start_ts = time.perf_counter()
            context: dict[str, Any] = {
                "request_id": request_id,
                "cnpj_informado": cnpj,
                "competencia_inicial": period.start_month.isoformat(),
                "competencia_final": period.end_month.isoformat(),
                "period_month_count": period.month_count,
                "display_month_count": display_month_count_for_period(period),
                "periodo_analisado_label": period.label,
                "period_mode": period.mode,
                "period_preset_months": period.preset_months,
                "load_competencia_inicial": load_period.start_month.isoformat(),
                "load_competencia_final": load_period.end_month.isoformat(),
                "load_period_month_count": load_period.month_count,
                "slot": slot_i,
            }
            status_box = st.empty()
            try:
                progress = _init_progress_bar(0.0, f"[Slot {slot_i + 1}] Preparando...", status_box=status_box)
            except TypeError:
                progress = _init_progress_bar(0.0, f"[Slot {slot_i + 1}] Preparando...")
                status_box.caption(f"[Slot {slot_i + 1}] Preparando...")

            def _make_reporter(prog, sbox, prefix):
                def report_progress(current: int, total: int, message: str) -> None:
                    fraction = 0.0 if total <= 0 else min(1.0, max(0.0, current / total))
                    _update_progress_bar(prog, fraction, f"{prefix} {message}")
                    sbox.caption(f"{prefix} {message}")
                return report_progress

            report_progress = _make_reporter(progress, status_box, f"[Slot {slot_i + 1}]")
            try:
                cached_load = load_or_extract_informe(
                    cnpj_fundo=cnpj,
                    data_inicial=load_period.start_month,
                    data_final=load_period.end_month,
                    progress_callback=report_progress,
                )
                result = cached_load.result
                context["cache_status"] = cached_load.cache_status
                context["cache_key"] = cached_load.cache_key
                context["cache_dir"] = str(cached_load.cache_dir)
            except Exception as exc:  # noqa: BLE001
                progress.empty()
                status_box.empty()
                tb_text = traceback.format_exc()
                slots[slot_i] = {"result": None, "context": context, "error": exc, "tb": tb_text}
                continue

            elapsed_seconds = time.perf_counter() - start_ts
            context["elapsed_seconds"] = round(elapsed_seconds, 3)
            context["timings"] = {
                "extracao_cache_segundos": round(elapsed_seconds, 3),
            }
            _update_progress_bar(progress, 1.0, f"[Slot {slot_i + 1}] Concluído.")
            status_box.empty()
            slots[slot_i] = {"result": result, "context": context}

        st.session_state["fidc_slots"] = slots

    if not slots:
        return

    # Build tab labels from fund names in loaded slots
    def _slot_tab_label(slot_data: dict, slot_i: int) -> str:
        result = slot_data.get("result")
        if result is None:
            return f"FIDC {slot_i + 1} (erro)"
        cnpj = slot_data.get("context", {}).get("cnpj_informado", "")
        return cnpj[:14] if cnpj else f"FIDC {slot_i + 1}"

    sorted_slots = sorted(slots.items())
    tab_labels = [_slot_tab_label(sd, si) for si, sd in sorted_slots]
    if len(tab_labels) == 1:
        # Single slot — no nested tabs needed
        slot_i, slot_data = sorted_slots[0]
        _render_slot(slot_data, slot_key=f"slot{slot_i}")
    else:
        fidc_tabs = st.tabs(tab_labels)
        for tab, (slot_i, slot_data) in zip(fidc_tabs, sorted_slots):
            with tab:
                _render_slot(slot_data, slot_key=f"slot{slot_i}")

    _render_executive_comparison_section(sorted_slots)


def _render_slot(slot_data: dict, slot_key: str) -> None:
    """Render one loaded FIDC slot (result + context)."""
    result = slot_data.get("result")
    context = dict(slot_data.get("context") or {})
    error = slot_data.get("error")
    tb_text = slot_data.get("tb", "")
    if result is None:
        if error is not None:
            _render_failure_diagnostics(error, tb_text, context)
        else:
            st.warning("Sem dados carregados para este slot.")
        return
    try:
        _render_result(result, context, slot_key=slot_key)
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        render_context = dict(context)
        render_context["etapa"] = "renderizacao_resultado"
        _render_failure_diagnostics(exc, tb, render_context)



def _safe_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def _count_docs_by_status(docs_df: pd.DataFrame, status: str) -> int:
    if docs_df.empty or "processamento" not in docs_df.columns:
        return 0
    return int((docs_df["processamento"] == status).sum())


def _validate_result_contract(result: InformeMensalResult) -> dict[str, list[str]]:
    contract = {
        "docs_df": ["documento_id", "competencia", "processamento", "erro_processamento"],
        "audit_df": ["etapa", "status", "detalhe"],
    }
    missing: dict[str, list[str]] = {}
    for attr, required_cols in contract.items():
        df = getattr(result, attr)
        absent = [col for col in required_cols if col not in df.columns]
        if absent:
            missing[attr] = absent
    required_paths = {
        "docs_csv_path": result.docs_csv_path,
        "contas_csv_path": result.contas_csv_path,
        "listas_csv_path": result.listas_csv_path,
        "wide_csv_path": result.wide_csv_path,
        "excel_path": result.excel_path,
        "audit_json_path": result.audit_json_path,
    }
    for attr, path in required_paths.items():
        if not path.exists():
            missing[attr] = ["arquivo_nao_encontrado"]
    return missing


def _period_from_context(context: dict[str, Any]) -> ImePeriodSelection | None:
    try:
        start_month = pd.Timestamp(context.get("competencia_inicial")).date()
        end_month = pd.Timestamp(context.get("competencia_final")).date()
    except Exception:  # noqa: BLE001
        return None
    if pd.isna(pd.Timestamp(start_month)) or pd.isna(pd.Timestamp(end_month)):
        return None
    preset_months = context.get("period_preset_months")
    if context.get("period_mode") == "preset" and preset_months in PERIOD_PRESET_OPTIONS:
        return ImePeriodSelection(
            mode="preset",
            start_month=start_month,
            end_month=end_month,
            preset_months=int(preset_months),
        )
    return build_custom_period(start_month=start_month, end_month=end_month)


def _dashboard_for_context_display_window(
    dashboard: FundonetDashboardData,
    context: dict[str, Any],
) -> FundonetDashboardData:
    period = _period_from_context(context)
    if period is None:
        return dashboard
    selected_competencias = select_competencia_labels_for_period(dashboard.competencias, period)
    if not selected_competencias:
        return dashboard
    filtered = filter_dashboard_to_competencias(dashboard, selected_competencias)
    context["display_month_count"] = len(filtered.competencias)
    context["periodo_exibido_label"] = filtered.fund_info.get("periodo_analisado")
    return filtered


@_cache_data_decorator
def _load_dashboard_data(
    wide_csv_path: str,
    listas_csv_path: str,
    docs_csv_path: str,
    dashboard_schema_version: int,
) -> FundonetDashboardData:
    _ = dashboard_schema_version
    return build_dashboard_data(
        wide_csv_path=Path(wide_csv_path),
        listas_csv_path=Path(listas_csv_path),
        docs_csv_path=Path(docs_csv_path),
    )


def _dashboard_contract_is_current(candidate: object) -> bool:
    required_attrs = (
        "dc_canonical_history_df",
        "default_history_df",
        "default_aging_history_df",
        "default_over_history_df",
        "executive_memory_df",
        "current_dashboard_inventory_df",
        "consistency_audit_df",
    )
    return isinstance(candidate, FundonetDashboardData) and all(
        hasattr(candidate, attr) for attr in required_attrs
    )


def _render_dashboard(
    result: InformeMensalResult,
    context: dict[str, Any],
    *,
    contract_missing: dict[str, list[str]],
    docs_error: int,
    slot_key: str = "slot0",
) -> None:
    # Cache the dashboard data in session_state so that widget interactions
    # do not trigger a full CSV reload on every
    # Streamlit rerun.  The cache entry is invalidated when the user clicks
    # "Carregar Informes Mensais" (see load_clicked handler above).
    _session_dashboard_key = f"_dashboard_{slot_key}"
    _session_dashboard_version_key = f"{_session_dashboard_key}_version"
    _session_timing_key = f"{_session_dashboard_key}_timings"
    timings = dict(st.session_state.get(_session_timing_key) or context.get("timings") or {})
    cached_dashboard = st.session_state.get(_session_dashboard_key)
    cached_version = st.session_state.get(_session_dashboard_version_key)
    if (
        cached_dashboard is None
        or cached_version != DASHBOARD_SCHEMA_VERSION
        or not _dashboard_contract_is_current(cached_dashboard)
    ):
        dashboard_start = time.perf_counter()
        with st.spinner("Montando dados da Visão Executiva..."):
            st.session_state[_session_dashboard_key] = _load_dashboard_data(
                str(result.wide_csv_path),
                str(result.listas_csv_path),
                str(result.docs_csv_path),
                DASHBOARD_SCHEMA_VERSION,
            )
        st.session_state[_session_dashboard_version_key] = DASHBOARD_SCHEMA_VERSION
        timings["dashboard_data_segundos"] = round(time.perf_counter() - dashboard_start, 3)
    else:
        timings.setdefault("dashboard_data_segundos", 0.0)
    extraction_seconds = pd.to_numeric(pd.Series([timings.get("extracao_cache_segundos", context.get("elapsed_seconds"))]), errors="coerce").iloc[0]
    dashboard_seconds = pd.to_numeric(pd.Series([timings.get("dashboard_data_segundos")]), errors="coerce").iloc[0]
    if pd.notna(extraction_seconds) and pd.notna(dashboard_seconds):
        timings["total_ate_dashboard_segundos"] = round(float(extraction_seconds) + float(dashboard_seconds), 3)
    st.session_state[_session_timing_key] = timings
    context["timings"] = timings
    dashboard: FundonetDashboardData = _dashboard_for_context_display_window(
        st.session_state[_session_dashboard_key],
        context,
    )
    st.session_state[_session_dashboard_key] = dashboard
    _render_dashboard_header(dashboard)
    _render_dashboard_controls(dashboard, context)
    if docs_error:
        st.warning(f"{docs_error} informe(s) ignorados.")
    if contract_missing:
        st.warning("Dados incompletos nesta janela.")
    _render_structural_risk_section(
        dashboard,
        slot_key=slot_key,
        return_months=int(context.get("display_month_count") or len(dashboard.competencias) or 12),
    )
    _render_credit_risk_section(dashboard)
    _render_liquidity_risk_section(dashboard)


def _render_dashboard_controls(dashboard: FundonetDashboardData, context: dict[str, Any]) -> None:
    _render_pptx_export_button(dashboard, context)
    with st.expander("Anexos", expanded=False):
        _render_regulamento_export_button(dashboard, context)
        if ENABLE_GLOBAL_PDF_EXPORT:
            _render_pdf_export_button(dashboard, context)


def _render_executive_comparison_section(sorted_slots: list[tuple[int, dict]]) -> None:
    entries: list[tuple[int, FundonetDashboardData]] = []
    for slot_i, _slot_data in sorted_slots:
        dashboard = st.session_state.get(f"_dashboard_slot{slot_i}")
        if _dashboard_contract_is_current(dashboard):
            entries.append((slot_i, dashboard))
    if len(entries) < 2:
        return

    dashboards = [dashboard for _slot_i, dashboard in entries]
    labels = dashboard_column_labels(dashboards)
    label_to_dashboard = dict(zip(labels, dashboards))

    _render_fidc_section(
        "Comparativo Executivo de FIDCs",
        "Matriz lado a lado dos FIDCs já carregados.",
    )
    selected_labels = st.multiselect(
        "FIDCs no comparativo",
        options=labels,
        default=labels,
        key="fidc_exec_compare_funds",
        placeholder="Selecione fundos já carregados...",
    )
    selected_dashboards = [label_to_dashboard[label] for label in selected_labels if label in label_to_dashboard]
    if len(selected_dashboards) < 2:
        st.info("Selecione ao menos dois FIDCs já carregados para montar o comparativo.")
        return

    available_rows = available_comparison_metric_labels(selected_dashboards)
    default_rows = default_comparison_metric_labels(selected_dashboards)
    selected_rows = st.multiselect(
        "Linhas exibidas",
        options=available_rows,
        default=default_rows or available_rows,
        key="fidc_exec_compare_rows",
        placeholder="Selecione métricas disponíveis...",
    )
    if not selected_rows:
        st.warning("Selecione ao menos uma linha para exibir a tabela comparativa.")
        return

    comparison_df = build_executive_comparison_df(
        selected_dashboards,
        selected_metric_labels=selected_rows,
    )
    if comparison_df.empty:
        st.info("Nenhuma métrica selecionada está disponível nos FIDCs carregados.")
        return

    highlight_options = ["Nenhuma", *comparison_df.columns[1:].tolist()]
    highlighted_column = st.selectbox(
        "Coluna em destaque",
        options=highlight_options,
        index=0,
        key="fidc_exec_compare_highlight",
    )
    highlight_value = None if highlighted_column == "Nenhuma" else highlighted_column
    _render_executive_comparison_table(comparison_df, highlighted_column=highlight_value)

    try:
        from services.fundonet_executive_compare_ppt import build_executive_comparison_pptx_bytes

        latest_labels = sorted(
            {
                _format_competencia_label(dashboard.latest_competencia)
                for dashboard in selected_dashboards
                if dashboard.latest_competencia
            }
        )
        subtitle = "Competência: " + ", ".join(latest_labels) if latest_labels else None
        pptx_bytes = build_executive_comparison_pptx_bytes(
            comparison_df,
            highlighted_column=highlight_value,
            subtitle=subtitle,
        )
        st.download_button(
            "Exportar comparativo (PPTX)",
            data=pptx_bytes,
            file_name=_executive_comparison_file_name(selected_dashboards),
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            help="Exporta somente a matriz comparativa exibida, sem buscar dados adicionais.",
        )
    except RuntimeError as exc:
        st.warning(str(exc))


def _render_executive_comparison_table(
    comparison_df: pd.DataFrame,
    *,
    highlighted_column: str | None,
) -> None:
    header_cells = []
    for column in comparison_df.columns:
        css_class = " class='highlight'" if column == highlighted_column else ""
        header_cells.append(f"<th{css_class}>{escape(str(column))}</th>")
    body_rows: list[str] = []
    for _, row in comparison_df.iterrows():
        cells = []
        for column in comparison_df.columns:
            css_class = " class='highlight'" if column == highlighted_column else ""
            cells.append(f"<td{css_class}>{escape(str(row.get(column, '—')))}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    html = (
        "<div class='fidc-exec-compare-wrapper'>"
        "<table class='fidc-exec-compare'>"
        "<thead><tr>"
        + "".join(header_cells)
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table></div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _executive_comparison_file_name(dashboards: list[FundonetDashboardData]) -> str:
    competencias = {
        _format_competencia_label(dashboard.latest_competencia).replace("-", "_")
        for dashboard in dashboards
        if dashboard.latest_competencia
    }
    suffix = "_".join(sorted(competencias)) if competencias else "comparativo"
    return f"comparativo_executivo_fidcs_{suffix}.pptx"


def _render_over_transparency_notes(st_ctx: object, over_history_df: pd.DataFrame) -> None:
    if over_history_df.empty or "calculo_status" not in over_history_df.columns:
        return
    incomplete_competencias = (
        over_history_df[over_history_df["calculo_status"] == "bucket_incompleto"]["competencia"]
        .drop_duplicates()
        .tolist()
    )
    partial_competencias = (
        over_history_df[over_history_df["calculo_status"] == "calculado_parcial"]["competencia"]
        .drop_duplicates()
        .tolist()
    )
    sem_denom = (
        over_history_df[over_history_df["calculo_status"] == "sem_denominador"]["competencia"]
        .drop_duplicates()
        .tolist()
    )
    notes: list[str] = []
    if incomplete_competencias:
        notes.append(f"{len(incomplete_competencias)} omitida(s)")
    if partial_competencias:
        notes.append(f"{len(partial_competencias)} parcial(is)")
    if sem_denom:
        notes.append(f"{len(sem_denom)} sem denominador")
    if notes:
        st_ctx.caption(f"Over: {'; '.join(notes)}.")


def _render_credit_risk_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section("Crédito")
    default_pct_chart_df = _default_ratio_chart_frame(dashboard.default_history_df)
    cobertura_df = _default_cobertura_chart_frame(dashboard.default_history_df)
    _render_chart_heading(st, "Inadimplência, PDD e cobertura")
    _credit_chart_all_zero = (
        default_pct_chart_df.empty
        or (pd.to_numeric(default_pct_chart_df["valor"], errors="coerce").abs().fillna(0) < 0.001).all()
    )
    credit_col, coverage_col = st.columns([0.62, 0.38])
    with credit_col:
        if _credit_chart_all_zero:
            st.caption("Sem dados no período.")
        else:
            credit_bar_size = _executive_grouped_bar_size(
                default_pct_chart_df["competencia"].nunique(),
                default_pct_chart_df["serie"].nunique(),
            )
            st.altair_chart(
                _grouped_bar_chart(
                    default_pct_chart_df,
                    title=None,
                    y_title="% dos DCs",
                    height=320,
                    bar_size=credit_bar_size,
                    label_font_size=10,
                    color_range=[FIDC_CHART_COLORS[0], FIDC_CHART_COLORS[1]],
                ),
                width="stretch",
            )
    with coverage_col:
        coverage_all_zero = (
            cobertura_df.empty
            or (pd.to_numeric(cobertura_df["valor"], errors="coerce").abs().fillna(0) < 0.001).all()
        )
        if coverage_all_zero:
            st.caption("Cobertura indisponível.")
        else:
            st.altair_chart(
                _line_history_chart(
                    cobertura_df,
                    title=None,
                    y_title="%",
                    color_range=[COVERAGE_LINE_COLOR],
                    show_point_labels=False,
                    show_end_labels=True,
                    point_size=64,
                    reference_value=100.0,
                    reference_label="100% (paridade)",
                ),
                width="stretch",
            )
    aging_history_df = dashboard.default_aging_history_df.copy()
    _render_chart_heading(st, "Aging")
    if aging_history_df.empty:
        st.caption("Sem aging.")
    else:
        aging_chart_df = _prepare_aging_history_chart_frame(aging_history_df)
        st.altair_chart(
            _aging_history_callout_chart(
                aging_chart_df,
                title=None,
                height=455,
                bar_size=_executive_monthly_bar_size(aging_history_df["competencia"].nunique()),
            ),
            width="stretch",
        )
    over_history_df = dashboard.default_over_history_df.copy()
    _render_chart_heading(st, "Inadimplência Over")
    if over_history_df.empty:
        st.info("Over indisponível.")
    else:
        over_chart_df = over_history_df[
            ["competencia", "competencia_dt", "ordem", "serie", "percentual"]
        ].rename(columns={"percentual": "valor"})
        over_chart_df = over_chart_df.dropna(subset=["valor"]).sort_values(["ordem", "competencia_dt"])
        if not over_chart_df.empty:
            st.altair_chart(
                _over_focus_line_chart(
                    over_chart_df,
                    title=None,
                    y_title="%",
                ),
                width="stretch",
            )
        else:
            st.caption("Curva Over indisponível.")
        _render_over_transparency_notes(st, over_history_df)
    with st.expander("Aging", expanded=False):
        _aging_detail_df = _format_aging_latest_table(dashboard.default_buckets_latest_df)
        if _aging_detail_df.empty:
            st.caption("Sem aging.")
        else:
            st.dataframe(_aging_detail_df, width="stretch", hide_index=True)


def _render_structural_risk_section(
    dashboard: FundonetDashboardData,
    *,
    slot_key: str = "slot0",
    return_months: int = 12,
) -> None:
    _render_fidc_section("Estrutura")
    latest_subordination_match = (
        dashboard.subordination_history_df[
            dashboard.subordination_history_df["competencia"].astype(str) == str(dashboard.latest_competencia)
        ]
        if not dashboard.subordination_history_df.empty and "competencia" in dashboard.subordination_history_df.columns
        else pd.DataFrame()
    )
    latest_subordination_row = latest_subordination_match.iloc[-1] if not latest_subordination_match.empty else None
    if latest_subordination_row is not None and bool(latest_subordination_row.get("pl_reconciliacao_warning")):
        delta = _format_brl_compact(latest_subordination_row.get("pl_reconciliacao_delta"))
        delta_pct = _format_percent(latest_subordination_row.get("pl_reconciliacao_delta_pct"))
        st.warning(
            "PL oficial diverge da soma das classes reportadas. "
            f"Diferença: {delta} ({delta_pct})."
        )
    subordination_periods = dashboard.subordination_history_df["competencia"].nunique()
    _render_chart_heading(st, "Subordinação reportada")
    st.altair_chart(
        _line_history_chart(
            _melt_metrics(
                dashboard.subordination_history_df,
                ["subordinacao_pct"],
                {"subordinacao_pct": "Subordinação reportada"},
            ),
            title=None,
            y_title="%",
            show_point_labels=subordination_periods <= 12,
            show_end_labels=subordination_periods > 12,
            point_label_font_size=10,
            point_label_font_weight=700,
            point_size=90,
        ),
        width="stretch",
    )

    _render_chart_heading(st, "PL por tipo de cota")
    pl_view = st.radio(
        "Visão do PL",
        options=["Valores absolutos (R$)", "% do total por competência"],
        horizontal=True,
        label_visibility="collapsed",
        key=f"pl_view_{slot_key}",
    )
    pl_periods = dashboard.quota_pl_history_df["competencia"].nunique()
    pl_bar_size = _executive_quota_bar_size(pl_periods)
    # Segment labels only when bars are wide enough (few periods) to avoid overlap
    show_pl_segment_labels = pl_periods <= 6
    if pl_view == "% do total por competência":
        st.altair_chart(
            _stacked_history_bar_chart(
                _quota_pl_share_chart_frame(dashboard.quota_pl_history_df),
                title=None,
                y_title="% do total",
                value_column="percentual",
                bar_size=pl_bar_size,
                label_font_size=9,
                round_percent_labels=True,
                show_segment_labels=show_pl_segment_labels,
                smart_label_placement=False,
            ),
            width="stretch",
        )
    else:
        # For R$ view: total labels only when bars are wide enough to avoid collision
        st.altair_chart(
            _stacked_history_bar_chart(
                _quota_pl_chart_frame(dashboard.quota_pl_history_df),
                title=None,
                y_title="R$",
                value_column="valor",
                bar_size=pl_bar_size,
                label_font_size=9,
                show_total_labels=(pl_periods <= 9),
                show_segment_labels=show_pl_segment_labels,
                smart_label_placement=False,
            ),
            width="stretch",
        )

    selected_set: set[str] | None = None
    return_chart_df = _return_chart_frame(dashboard.return_history_df)
    if not return_chart_df.empty:
        ordered_labels = _return_ordered_labels(dashboard)
        default_labels = ordered_labels[:5]
        selected_labels = st.multiselect(
            "Classes na rentabilidade",
            options=ordered_labels,
            default=default_labels,
            key=f"return_labels_{slot_key}",
            placeholder="Selecione classes para exibir a rentabilidade...",
        )
        selected_for_display = selected_labels if selected_labels else default_labels
        selected_set = set(selected_for_display)
        return_summary_df = dashboard.return_summary_df.copy()
        if selected_set:
            return_summary_df = return_summary_df[return_summary_df[_class_display_column(return_summary_df)].isin(selected_set)].copy()
        return_matrix_df = _format_return_inline_matrix_frame(
            dashboard.return_history_df,
            return_summary_df,
            selected_labels=selected_for_display if selected_for_display else None,
            months=return_months,
        )
        if not return_matrix_df.empty:
            _render_chart_heading(st, "Rentabilidade por tipo de cota")
            st.dataframe(
                return_matrix_df,
                width="stretch",
                hide_index=True,
            )
        base100_chart_df = _return_base100_chart_frame(
            dashboard.return_history_df,
            selected_labels=selected_for_display if selected_for_display else None,
            months=return_months,
        )
        if not base100_chart_df.empty:
            with st.expander("Base 100", expanded=False):
                st.altair_chart(
                    _line_history_chart(
                        base100_chart_df,
                        title=None,
                        y_title="Índice base 100",
                        show_point_labels=False,
                        show_end_labels=True,
                        point_size=76,
                    ),
                    width="stretch",
                )

    structural_tables: list[tuple[str, pd.DataFrame]] = [
        ("Métricas estruturais", _format_risk_metrics_compact_table(dashboard.risk_metrics_df, risk_block="Risco estrutural")),
        (f"Quadro de cotas em {_format_competencia_label(dashboard.latest_competencia)}", _format_latest_quota_frame(dashboard.quota_pl_history_df, dashboard.latest_competencia)),
    ]
    _render_detail_tables_expander("Resumo Qtd e Volume Cotas", structural_tables)


def _render_liquidity_risk_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section("Prazo e eventos")
    _render_chart_heading(
        st,
        f"Prazo de vencimento dos DCs a vencer em {_format_competencia_label(dashboard.latest_competencia)}",
    )
    st.altair_chart(
        _maturity_waterfall_chart(dashboard.maturity_latest_df, title=None),
        width="stretch",
    )

    _render_duration_section(dashboard)



def _render_glossary_section(dashboard: FundonetDashboardData) -> None:
    with st.expander("Glossário", expanded=False):
        glossary_df = dashboard.mini_glossary_df.copy()
        rows_list = glossary_df.to_dict("records")
        # Two-column layout for the glossary
        col_a, col_b = st.columns(2)
        mid = (len(rows_list) + 1) // 2
        for i, row in enumerate(rows_list):
            col = col_a if i < mid else col_b
            col.markdown(
                f"**{row.get('termo', 'Termo')}**  \n"
                f"{row.get('definicao', row.get('definicao_curta', 'N/D'))}"
            )
            col.markdown("")


def _render_dashboard_header(dashboard: FundonetDashboardData) -> None:
    info = dashboard.fund_info
    title = info.get("nome_fundo") or info.get("nome_classe") or "FIDC selecionado"
    st.markdown(
        f"""
<div class="fidc-hero">
  <div class="fidc-hero__title">{escape(str(title))}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _competencia_labels_between(start_month: date, end_month: date) -> list[str]:
    current = date(start_month.year, start_month.month, 1)
    end = date(end_month.year, end_month.month, 1)
    labels: list[str] = []
    while current <= end:
        labels.append(current.strftime("%m/%Y"))
        current = _period_shift_month(current, 1)
    return labels


def _render_chart_heading(container, title: str, caption: str | None = None) -> None:
    container.markdown(f'<div class="fidc-chart-title">{escape(title)}</div>', unsafe_allow_html=True)


def _format_competencia_label(value: object) -> str:
    if value is None:
        return "N/D"
    raw = str(value).strip()
    if not raw:
        return "N/D"
    if re.fullmatch(r"\d{2}/\d{4}", raw):
        month = int(raw[:2])
        year = raw[-2:]
        return f"{_PT_MONTH_ABBR.get(f'{month:02d}', raw[:2])}-{year}"
    try:
        parsed = pd.Timestamp(raw)
        return f"{_PT_MONTH_ABBR.get(f'{int(parsed.month):02d}', parsed.strftime('%m'))}-{str(parsed.year)[-2:]}"
    except Exception:  # noqa: BLE001
        return raw


def _format_competencia_period(value: object) -> str:
    raw = str(value or "").strip()
    if " a " not in raw:
        return _format_competencia_label(raw)
    start, end = raw.split(" a ", 1)
    return f"{_format_competencia_label(start)} a {_format_competencia_label(end)}"


def _competencia_sort_timestamp(value: object) -> pd.Timestamp:
    raw = str(value or "").strip()
    if not raw:
        return pd.NaT
    if re.fullmatch(r"\d{1,2}/\d{4}", raw):
        month, year = raw.split("/", 1)
        try:
            return pd.Timestamp(year=int(year), month=int(month), day=1)
        except ValueError:
            return pd.NaT
    display_match = re.fullmatch(r"([A-Za-z]{3})-(\d{2}|\d{4})", raw.lower())
    if display_match:
        month = _PT_MONTH_NUMBER_BY_ABBR.get(display_match.group(1))
        if month is not None:
            year_text = display_match.group(2)
            year = int(year_text) + 2000 if len(year_text) == 2 else int(year_text)
            try:
                return pd.Timestamp(year=year, month=month, day=1)
            except ValueError:
                return pd.NaT
    try:
        parsed = pd.Timestamp(raw)
    except Exception:  # noqa: BLE001
        return pd.NaT
    if pd.isna(parsed):
        return pd.NaT
    return pd.Timestamp(year=int(parsed.year), month=int(parsed.month), day=1)


def _competencia_axis_sort(
    frame: pd.DataFrame,
    *,
    competencia_column: str = "competencia",
    descending: bool = False,
) -> list[str]:
    if frame.empty or competencia_column not in frame.columns:
        return []
    working = pd.DataFrame({"_label": frame[competencia_column].astype(str)})
    if "competencia_dt" in frame.columns:
        working["_dt"] = pd.to_datetime(frame["competencia_dt"], errors="coerce")
        missing_dt = working["_dt"].isna()
        if missing_dt.any():
            working.loc[missing_dt, "_dt"] = working.loc[missing_dt, "_label"].map(_competencia_sort_timestamp)
    else:
        working["_dt"] = working["_label"].map(_competencia_sort_timestamp)
    working["_fallback_order"] = range(len(working))
    ordered = (
        working.groupby("_label", sort=False, dropna=False)
        .agg(_dt=("_dt", "max"), _fallback_order=("_fallback_order", "min"))
        .reset_index()
        .sort_values(
            ["_dt", "_fallback_order"],
            ascending=[not descending, True],
            na_position="last",
            kind="stable",
        )
    )
    return ordered["_label"].tolist()


def _sort_competencia_display_frame(
    frame: pd.DataFrame,
    *,
    extra_columns: list[str] | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    output = frame.copy()
    sort_columns: list[str] = []
    ascending: list[bool] = []
    helper_column = "__competencia_sort_dt"
    if "competencia_dt" in output.columns:
        sort_columns.append("competencia_dt")
        ascending.append(True)
    elif "competencia" in output.columns:
        output[helper_column] = pd.to_datetime("01/" + output["competencia"].astype(str), format="%d/%m/%Y", errors="coerce")
        sort_columns.append(helper_column)
        ascending.append(True)
    for column in extra_columns or []:
        if column in output.columns:
            sort_columns.append(column)
            ascending.append(True)
    if sort_columns:
        output = output.sort_values(sort_columns, ascending=ascending, kind="stable").reset_index(drop=True)
    if helper_column in output.columns:
        output = output.drop(columns=[helper_column])
    return output


def _shift_month(base: date, offset_months: int) -> date:
    return _period_shift_month(base, offset_months)


def _build_month_options(end_month: date, *, months_back: int) -> list[date]:
    return _period_month_options(end_month, months_back=months_back)


def _format_month_option_label(value: date) -> str:
    return _format_competencia_label(value.isoformat())


def _render_concentration_warning(container, segment_latest_df: pd.DataFrame) -> None:
    if segment_latest_df.empty or "percentual" not in segment_latest_df.columns:
        return
    ordered = segment_latest_df.sort_values("percentual", ascending=False)
    top_row = ordered.iloc[0]
    top_pct = pd.to_numeric(top_row.get("percentual"), errors="coerce")
    if pd.isna(top_pct) or float(top_pct) < 80.0:
        return
    container.caption(
        "⚠️ Dado informado pelo administrador. Concentração elevada pode refletir omissão ou generalização da composição setorial."
    )


def _build_aging_display_df(default_buckets_latest_df: pd.DataFrame) -> pd.DataFrame:
    return default_buckets_latest_df.copy()


def _build_aging_history_display_df(
    default_buckets_history_df: pd.DataFrame,
    default_history_df: pd.DataFrame,
) -> pd.DataFrame:
    if default_buckets_history_df.empty or default_history_df.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "ordem", "faixa", "valor", "percentual"])
    df = default_buckets_history_df.copy()
    df = df.sort_values(["competencia_dt", "ordem"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    overdue_df = (
        df.groupby("competencia", as_index=False, dropna=False)["valor"]
        .sum()
        .rename(columns={"valor": "denominador"})
    )
    df = df.merge(overdue_df, on="competencia", how="left")
    df["percentual"] = (
        df["valor"] / df["denominador"]
    ).where(df["denominador"] > 0).mul(100.0)
    df = df.dropna(subset=["percentual"]).copy()
    return df


def _build_over_aging_history_df(
    default_buckets_history_df: pd.DataFrame,
    default_history_df: pd.DataFrame,
) -> pd.DataFrame:
    if default_buckets_history_df.empty or default_history_df.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "ordem", "serie", "valor", "percentual"])
    source_df = default_buckets_history_df.copy()
    source_df["valor"] = pd.to_numeric(source_df["valor"], errors="coerce").fillna(0.0)
    denominator_df = default_history_df[["competencia", "competencia_dt"]].copy()
    denominator_df["denominador"] = _default_denominator_series(default_history_df).values
    bucket_specs = [
        ("Over 1", 1, None),
        ("Over 30", 2, None),
        ("Over 60", 3, None),
        ("Over 90", 4, None),
        ("Over 180", 7, None),
        ("Over 360", 8, None),
    ]
    frames: list[pd.DataFrame] = []
    for ordem, (serie, ordem_min, ordem_max) in enumerate(bucket_specs, start=1):
        subset = source_df[source_df["ordem"] >= ordem_min].copy()
        if ordem_max is not None:
            subset = subset[subset["ordem"] <= ordem_max].copy()
        grouped = (
            subset.groupby(["competencia", "competencia_dt"], as_index=False, dropna=False)["valor"]
            .sum()
        )
        grouped["serie"] = serie
        grouped["ordem"] = ordem
        frames.append(grouped)
    output = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if output.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "ordem", "serie", "valor", "percentual"])
    output = output.merge(
        denominator_df[["competencia", "denominador"]],
        on="competencia",
        how="left",
    )
    output["percentual"] = (
        output["valor"] / output["denominador"]
    ).where(output["denominador"] > 0).mul(100.0)
    output = output.dropna(subset=["percentual"])
    output = output[output["valor"] > 0].copy()
    return output.sort_values(["competencia_dt", "ordem"]).reset_index(drop=True)


def _render_aging_omission_note(container, default_buckets_latest_df: pd.DataFrame) -> None:
    del container
    del default_buckets_latest_df


def _render_duration_section(dashboard: FundonetDashboardData) -> None:
    """Renders the estimated duration KPI card + monthly evolution chart.

    Duration is the weighted-average remaining term (days) of the receivables
    portfolio, computed from the CVM maturity buckets.

    Formula:
        Duration_t = Σ(saldo_bucket_i,t × prazo_proxy_i) / Σ(saldo_bucket_i,t)

    Bucket proxy assumptions (see fundonet_dashboard._MATURITY_BUCKET_SPECS):
        Vencidos → 0 d  |  ≤30 d → 30 d  |  intervals → midpoint.
        If the open-ended bucket >1080d dominates the balance, the duration
        point estimate is intentionally not shown.
    """
    duration_df = dashboard.duration_history_df
    if duration_df.empty:
        return

    ok_df = duration_df[duration_df["data_quality"] == "ok"]

    # --- KPI destaque: valor mais recente ---
    latest_duration = duration_df.sort_values("competencia_dt").iloc[-1]
    latest_quality = str(latest_duration.get("data_quality") or "")
    if latest_quality == "nao_calculavel_bucket_aberto_dominante":
        open_share = latest_duration.get("open_bucket_share_pct")
        st.warning(f"Duration não calculável: {_format_percent(open_share)} na faixa aberta >1080 dias.")
    elif latest_quality == "sem_dados":
        st.caption("Duration não disponível.")

    # --- Série histórica ---
    if len(ok_df) < 2:
        st.caption("Histórico insuficiente.")
        return

    _render_chart_heading(
        st,
        "Prazo médio proxy dos recebíveis",
    )
    st.altair_chart(
        _duration_line_chart(duration_df),
        width="stretch",
    )


def _render_pdf_export_button(dashboard: FundonetDashboardData, context: dict[str, Any]) -> None:
    try:
        from services.fundonet_pdf_export import build_dashboard_pdf_bytes
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Exportação em PDF indisponível neste ambiente: {exc}")
        return

    try:
        pdf_bytes = build_dashboard_pdf_bytes(
            dashboard,
            requested_period_label=context.get("periodo_analisado_label"),
        )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Não foi possível montar o PDF do dashboard: {exc}")
        return

    st.download_button(
        "Baixar relatório em PDF",
        data=pdf_bytes,
        file_name=f"relatorio_fidc_ime_{context.get('request_id', 'execucao')}.pdf",
        mime="application/pdf",
        help="PDF paginado com tabelas controladas para evitar cortes e sobreposição de conteúdo.",
    )


@st.cache_data(show_spinner=False)
def _load_latest_regulamento_payload(cnpj_fundo: str) -> dict[str, Any] | None:
    from services.fundonet_documents import fetch_latest_regulamento_document

    payload = fetch_latest_regulamento_document(cnpj_fundo)
    if payload is None:
        return None
    document = payload.document
    return {
        "bytes": payload.content,
        "file_name": payload.file_name,
        "document_id": document.id,
        "data_referencia": document.data_referencia or "",
        "data_entrega": document.data_entrega or "",
    }


def _render_regulamento_export_button(dashboard: FundonetDashboardData, context: dict[str, Any]) -> None:
    cnpj_fundo = re.sub(r"\D", "", str(dashboard.fund_info.get("cnpj_fundo") or ""))
    if len(cnpj_fundo) != 14:
        return
    payload_key = f"fidc_regulamento_payload::{cnpj_fundo}"
    payload = st.session_state.get(payload_key)
    if payload is None:
        if st.button(
            "Preparar regulamento",
            key=f"fidc_prepare_regulamento::{cnpj_fundo}",
            use_container_width=True,
            help="Busca o regulamento somente sob demanda para não atrasar o carregamento dos gráficos.",
        ):
            start = time.perf_counter()
            with st.spinner("Buscando regulamento no Fundos.NET..."):
                try:
                    payload = _load_latest_regulamento_payload(cnpj_fundo)
                except Exception:
                    payload = None
            timings = dict(context.get("timings") or {})
            timings["regulamento_segundos"] = round(time.perf_counter() - start, 3)
            context["timings"] = timings
            if payload:
                st.session_state[payload_key] = payload
            else:
                st.warning("Regulamento indisponível para download neste momento.")
        return
    st.download_button(
        "Download regulamento",
        data=payload["bytes"],
        file_name=str(payload["file_name"]),
        mime="application/pdf",
        help=(
            "Documento mais recente da categoria Regulamento disponível no Fundos.NET, "
            f"referência {payload['data_referencia'] or 'N/D'}."
        ),
    )


def _render_pptx_export_button(dashboard: FundonetDashboardData, context: dict[str, Any]) -> None:
    payload_key = (
        f"fidc_pptx_payload::{context.get('cache_key') or context.get('request_id') or 'execucao'}::"
        f"{DASHBOARD_SCHEMA_VERSION}"
    )
    pptx_bytes = st.session_state.get(payload_key)
    if pptx_bytes is None:
        if st.button(
            "Preparar deck de comitê (PPTX)",
            key=f"fidc_prepare_pptx::{payload_key}",
            use_container_width=True,
            help="Monta o PowerPoint somente sob demanda para priorizar a abertura dos gráficos.",
        ):
            try:
                from services.fundonet_ppt_export import build_dashboard_pptx_bytes
            except Exception as exc:  # noqa: BLE001
                st.warning(f"Exportação em slides indisponível neste ambiente: {exc}")
                return
            start = time.perf_counter()
            with st.spinner("Montando slides em PowerPoint..."):
                try:
                    pptx_bytes = build_dashboard_pptx_bytes(
                        dashboard,
                        requested_period_label=context.get("periodo_analisado_label"),
                        return_months=int(context.get("display_month_count") or len(dashboard.competencias) or 12),
                    )
                except Exception as exc:  # noqa: BLE001
                    st.warning(f"Não foi possível montar os slides do dashboard: {exc}")
                    return
            timings = dict(context.get("timings") or {})
            timings["pptx_segundos"] = round(time.perf_counter() - start, 3)
            context["timings"] = timings
            st.session_state[payload_key] = pptx_bytes
        else:
            return
    if not pptx_bytes:
        return

    st.download_button(
        "Baixar deck de comitê (PPTX)",
        data=pptx_bytes,
        file_name=f"relatorio_fidc_ime_{context.get('request_id', 'execucao')}.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        help="Deck executivo em PowerPoint com os principais blocos do painel já carregado.",
    )


def _render_fidc_section(title: str, caption: str | None = None) -> None:
    _ = caption
    st.markdown(f'<div class="fidc-section">{escape(title)}</div>', unsafe_allow_html=True)


def _render_cvm_tables_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section("Tabelas CVM")
    left, right = st.columns(2)
    with left:
        st.caption("Liquidez reportada")
        st.dataframe(
            _format_value_table(dashboard.liquidity_latest_df, label_column="horizonte", label_title="Horizonte"),
            width="stretch",
            hide_index=True,
        )
    with right:
        st.caption("Cotistas")
        st.dataframe(
            _format_holder_table(dashboard.holder_latest_df),
            width="stretch",
            hide_index=True,
        )

    if not dashboard.rate_negotiation_latest_df.empty:
        with st.expander("Taxas", expanded=False):
            st.dataframe(
                _format_rate_table(dashboard.rate_negotiation_latest_df),
                width="stretch",
                hide_index=True,
            )


def _melt_metrics(source_df: pd.DataFrame, columns: list[str], label_map: dict[str, str]) -> pd.DataFrame:
    chart_df = source_df[["competencia", "competencia_dt"] + columns].copy()
    chart_df = chart_df.melt(
        id_vars=["competencia", "competencia_dt"],
        value_vars=columns,
        var_name="serie_key",
        value_name="valor",
    )
    chart_df["serie"] = chart_df["serie_key"].map(label_map).fillna(chart_df["serie_key"])
    chart_df["valor"] = pd.to_numeric(chart_df["valor"], errors="coerce")
    return chart_df.dropna(subset=["valor"])


def _return_chart_frame(return_history_df: pd.DataFrame) -> pd.DataFrame:
    if return_history_df.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "serie", "valor"])
    ordered_history = sort_class_display_frame(
        return_history_df,
        label_column=_class_display_column(return_history_df),
        extra_columns=["competencia_dt"],
    )
    label_column = _class_display_column(ordered_history)
    chart_df = ordered_history[["competencia", "competencia_dt", label_column, "retorno_mensal_pct"]].copy()
    chart_df = chart_df.rename(columns={label_column: "serie", "retorno_mensal_pct": "valor"})
    chart_df["valor"] = pd.to_numeric(chart_df["valor"], errors="coerce")
    return chart_df.dropna(subset=["valor"])


def _return_ordered_labels(dashboard: FundonetDashboardData) -> list[str]:
    return_history_df = dashboard.return_history_df.copy()
    if return_history_df.empty:
        return []
    label_column = _class_display_column(return_history_df)
    labels = return_history_df[label_column].dropna().astype(str).drop_duplicates().tolist()
    return ordered_class_labels(labels, return_history_df)


def _format_return_inline_matrix_frame(
    return_history_df: pd.DataFrame,
    return_summary_df: pd.DataFrame,
    *,
    selected_labels: list[str] | None = None,
    months: int = 12,
) -> pd.DataFrame:
    history_df = _return_history_last_months(return_history_df, months=months)
    if history_df.empty or return_summary_df.empty:
        return pd.DataFrame(columns=["Classe", "YTD", "12 meses"])
    label_column = _class_display_column(history_df)
    summary_label_column = _class_display_column(return_summary_df)
    if selected_labels:
        history_df = history_df[history_df[label_column].isin(selected_labels)].copy()
        return_summary_df = return_summary_df[return_summary_df[summary_label_column].isin(selected_labels)].copy()
    if history_df.empty or return_summary_df.empty:
        return pd.DataFrame(columns=["Classe", "YTD", "12 meses"])
    ordered_history = history_df.sort_values("competencia_dt", ascending=False).copy()
    competencias = ordered_history["competencia"].drop_duplicates().tolist()
    display_competencias = competencias
    pivot = (
        ordered_history.pivot_table(
            index=label_column,
            columns="competencia",
            values="retorno_mensal_pct",
            aggfunc="last",
        )
        .reindex(columns=display_competencias)
    )
    candidate_labels = [label for label in (selected_labels or []) if label in pivot.index]
    candidate_labels += [label for label in pivot.index.tolist() if label not in set(candidate_labels)]
    ordered_labels = ordered_class_labels(candidate_labels, history_df)
    pivot = pivot.reindex(ordered_labels)
    pivot = pivot.reset_index(drop=True)
    labels_series = pd.Series(ordered_labels, dtype="object")
    month_columns = {competencia: _format_competencia_label(competencia) for competencia in display_competencias}
    output = pd.DataFrame({"Classe": labels_series})
    for competencia in display_competencias:
        output[month_columns[competencia]] = pivot[competencia].tolist()
        output[month_columns[competencia]] = output[month_columns[competencia]].map(_format_percent)
    summary_lookup = return_summary_df.set_index(summary_label_column)
    retorno_ano = summary_lookup.get("retorno_ano_pct", pd.Series(dtype="float64"))
    retorno_12m = summary_lookup.get("retorno_12m_pct", pd.Series(dtype="float64"))
    output["YTD"] = output["Classe"].map(lambda label: _format_percent(retorno_ano.get(label)))
    output["12 meses"] = output["Classe"].map(lambda label: _format_percent(retorno_12m.get(label)))
    return output


def _format_return_summary_frame(return_summary_df: pd.DataFrame) -> pd.DataFrame:
    if return_summary_df.empty:
        return pd.DataFrame(columns=["Classe", "Mês", "YTD", "12 Meses"])
    table_df = sort_class_display_frame(return_summary_df, label_column=_class_display_column(return_summary_df))
    table_df["Classe"] = table_df[_class_display_column(table_df)]
    table_df["Mês"] = table_df["retorno_mes_pct"].map(_format_percent)
    table_df["YTD"] = table_df["retorno_ano_pct"].map(_format_percent)
    table_df["12 Meses"] = table_df["retorno_12m_pct"].map(_format_percent)
    return table_df[["Classe", "Mês", "YTD", "12 Meses"]]


def _return_history_last_months(return_history_df: pd.DataFrame, *, months: int = 12) -> pd.DataFrame:
    if return_history_df.empty:
        return return_history_df.copy()
    ordered = return_history_df.sort_values("competencia_dt").copy()
    latest_competencias = ordered["competencia"].drop_duplicates().tail(months).tolist()
    return ordered[ordered["competencia"].isin(latest_competencias)].copy()


def _return_base100_chart_frame(
    return_history_df: pd.DataFrame,
    *,
    selected_labels: list[str] | None = None,
    months: int = 12,
) -> pd.DataFrame:
    history_df = _return_history_last_months(return_history_df, months=months)
    if history_df.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "serie", "valor"])
    label_column = _class_display_column(history_df)
    if selected_labels:
        history_df = history_df[history_df[label_column].isin(selected_labels)].copy()
    if history_df.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "serie", "valor"])
    rows: list[dict[str, object]] = []
    for label in ordered_class_labels(history_df[label_column].dropna().astype(str).drop_duplicates().tolist(), history_df):
        group = history_df[history_df[label_column].astype(str) == label]
        ordered = group.sort_values("competencia_dt").copy()
        current_index = 100.0
        first_valid = True
        for _, row in ordered.iterrows():
            monthly_return = pd.to_numeric(pd.Series([row.get("retorno_mensal_pct")]), errors="coerce").iloc[0]
            if first_valid:
                current_index = 100.0
                first_valid = False
            elif pd.notna(monthly_return):
                current_index = current_index * (1.0 + float(monthly_return) / 100.0)
            rows.append(
                {
                    "competencia": row.get("competencia"),
                    "competencia_dt": row.get("competencia_dt"),
                    "serie": str(label),
                    "valor": current_index,
                }
            )
    return pd.DataFrame(rows)


def _return_monthly_matrix_frame(
    return_history_df: pd.DataFrame,
    *,
    selected_labels: list[str] | None = None,
    months: int = 12,
) -> pd.DataFrame:
    history_df = _return_history_last_months(return_history_df, months=months)
    if history_df.empty:
        return pd.DataFrame(columns=["Competência"])
    label_column = _class_display_column(history_df)
    if selected_labels:
        history_df = history_df[history_df[label_column].isin(selected_labels)].copy()
    if history_df.empty:
        return pd.DataFrame(columns=["Competência"])
    pivot = (
        history_df.pivot_table(
            index=["competencia", "competencia_dt"],
            columns=label_column,
            values="retorno_mensal_pct",
            aggfunc="last",
        )
        .reset_index()
        .sort_values("competencia_dt", ascending=False)
    )
    available_labels = [column for column in pivot.columns if column not in {"competencia", "competencia_dt"}]
    candidate_labels = [label for label in (selected_labels or []) if label in available_labels]
    candidate_labels += [label for label in available_labels if label not in set(candidate_labels)]
    ordered_labels = ordered_class_labels(candidate_labels, history_df)
    display_columns = ["competencia", "competencia_dt"] + [label for label in ordered_labels if label in pivot.columns]
    display_columns += [column for column in pivot.columns if column not in display_columns]
    pivot = pivot[display_columns].copy()
    output = pd.DataFrame({"Competência": pivot["competencia"].map(_format_competencia_label)})
    for column in pivot.columns:
        if column in {"competencia", "competencia_dt"}:
            continue
        output[str(column)] = pivot[column].map(_format_percent)
    return output


def _format_return_monthly_matrix_frame(
    return_history_df: pd.DataFrame,
    *,
    selected_labels: list[str] | None = None,
    months: int = 12,
) -> pd.DataFrame:
    return _return_monthly_matrix_frame(
        return_history_df,
        selected_labels=selected_labels,
        months=months,
    )


def _format_return_base100_matrix_frame(
    return_history_df: pd.DataFrame,
    *,
    selected_labels: list[str] | None = None,
    months: int = 12,
) -> pd.DataFrame:
    base100_df = _return_base100_chart_frame(
        return_history_df,
        selected_labels=selected_labels,
        months=months,
    )
    if base100_df.empty:
        return pd.DataFrame(columns=["Competência"])
    pivot = (
        base100_df.pivot_table(
            index=["competencia", "competencia_dt"],
            columns="serie",
            values="valor",
            aggfunc="last",
        )
        .reset_index()
        .sort_values("competencia_dt", ascending=False)
    )
    ordered_columns = ["competencia", "competencia_dt"] + [label for label in (selected_labels or []) if label in pivot.columns]
    ordered_columns += [column for column in pivot.columns if column not in ordered_columns]
    pivot = pivot[ordered_columns].copy()
    output = pd.DataFrame({"Competência": pivot["competencia"].map(_format_competencia_label)})
    for column in pivot.columns:
        if column in {"competencia", "competencia_dt"}:
            continue
        output[str(column)] = pivot[column].map(lambda value: _format_decimal(value, decimals=1))
    return output


def _format_performance_benchmark_table(
    performance_df: pd.DataFrame,
    *,
    mark_equal_as_na: bool = False,
) -> pd.DataFrame:
    if performance_df.empty:
        return pd.DataFrame(columns=["Classe", "Benchmark", "Realizado", "Gap (bps)"])
    output = performance_df.copy()
    output["Classe"] = output[_class_display_column(output)]
    output["Benchmark"] = output["desempenho_esperado_pct"].map(_format_percent)
    if mark_equal_as_na:
        esperado_num = pd.to_numeric(output["desempenho_esperado_pct"], errors="coerce")
        real_num = pd.to_numeric(output["desempenho_real_pct"], errors="coerce")
        equal_mask = (esperado_num - real_num).abs() < 1e-9
        output["Realizado"] = [
            "Não disponível" if equal else _format_percent(value)
            for equal, value in zip(equal_mask, output["desempenho_real_pct"])
        ]
        output["Gap (bps)"] = [
            "N/D" if equal else _format_decimal(value, decimals=0)
            for equal, value in zip(equal_mask, output["gap_bps"])
        ]
    else:
        output["Realizado"] = output["desempenho_real_pct"].map(_format_percent)
        output["Gap (bps)"] = output["gap_bps"].map(lambda value: _format_decimal(value, decimals=0))
    return output[["Classe", "Benchmark", "Realizado", "Gap (bps)"]]


def _benchmark_equals_realizado(performance_df: pd.DataFrame) -> bool:
    """Detect silent equality: when all rows have benchmark equal to realizado."""
    if performance_df.empty:
        return False
    required = {"desempenho_esperado_pct", "desempenho_real_pct"}
    if not required.issubset(performance_df.columns):
        return False
    esperado = pd.to_numeric(performance_df["desempenho_esperado_pct"], errors="coerce")
    real = pd.to_numeric(performance_df["desempenho_real_pct"], errors="coerce")
    paired = pd.concat([esperado, real], axis=1).dropna()
    if paired.empty:
        return False
    diffs = (paired.iloc[:, 0] - paired.iloc[:, 1]).abs()
    return bool((diffs < 1e-9).all())


def _class_display_column(frame: pd.DataFrame) -> str:
    if "class_label" in frame.columns:
        return "class_label"
    return "label"


def _quota_macro_label_column(frame: pd.DataFrame) -> str:
    if "class_macro_label" in frame.columns:
        return "class_macro_label"
    return _class_display_column(frame)


def _format_latest_quota_frame(quota_pl_history_df: pd.DataFrame, latest_competencia: str) -> pd.DataFrame:
    if quota_pl_history_df.empty:
        return pd.DataFrame(columns=["Classe", "Tipo", "Qt. cotas", "Valor da cota", "PL"])
    latest_df = quota_pl_history_df[quota_pl_history_df["competencia"] == latest_competencia].copy()
    if latest_df.empty:
        return pd.DataFrame(columns=["Classe", "Tipo", "Qt. cotas", "Valor da cota", "PL"])
    if "aggregation_scope" in latest_df.columns and latest_df["aggregation_scope"].eq("portfolio").all():
        share_series = pd.to_numeric(latest_df.get("pl_share_pct"), errors="coerce")
        latest_df["Classe"] = latest_df[_quota_macro_label_column(latest_df)]
        latest_df["PL"] = latest_df["pl"].map(_format_brl_compact)
        latest_df["% do PL"] = share_series.map(_format_percent)
        return latest_df[["Classe", "PL", "% do PL"]]
    latest_df["Classe"] = latest_df[_class_display_column(latest_df)]
    latest_df["Tipo"] = latest_df[_quota_macro_label_column(latest_df)]
    latest_df["Qt. cotas"] = latest_df["qt_cotas"].map(lambda value: _format_decimal(value, decimals=4))
    latest_df["Valor da cota"] = latest_df["vl_cota"].map(_format_brl)
    latest_df["PL"] = latest_df["pl"].map(_format_brl_compact)
    return latest_df[["Classe", "Tipo", "Qt. cotas", "Valor da cota", "PL"]]


def _render_dataframe_expander(title: str, df: pd.DataFrame, *, expanded: bool = False) -> None:
    with st.expander(title, expanded=expanded):
        st.dataframe(df, width="stretch", hide_index=True)


def _render_detail_tables_expander(
    title: str,
    tables: list[tuple[str, pd.DataFrame]],
    *,
    expanded: bool = False,
) -> None:
    valid_tables = [(table_title, df) for table_title, df in tables if df is not None and not df.empty]
    if not valid_tables:
        return
    with st.expander(title, expanded=expanded):
        for idx, (table_title, df) in enumerate(valid_tables):
            st.markdown(f'<div class="fidc-detail-title">{escape(table_title)}</div>', unsafe_allow_html=True)
            st.dataframe(df, width="stretch", hide_index=True)
            if idx != len(valid_tables) - 1:
                st.markdown('<div class="fidc-block-spacer"></div>', unsafe_allow_html=True)


def _format_value_percent_table(df: pd.DataFrame, *, label_column: str, label_title: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[label_title, "Valor", "%"])
    output = df.sort_values("ordem").copy() if "ordem" in df.columns else df.copy()
    output[label_title] = output[label_column]
    output["Valor"] = output["valor"].map(_format_brl_compact)
    output["%"] = output["percentual"].map(_format_percent) if "percentual" in output.columns else "N/D"
    return output[[label_title, "Valor", "%"]]


def _format_value_table(df: pd.DataFrame, *, label_column: str, label_title: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[label_title, "Valor"])
    output = df.sort_values("ordem").copy() if "ordem" in df.columns else df.copy()
    output[label_title] = output[label_column]
    output["Valor"] = output.apply(_format_value_row, axis=1)
    columns = [label_title, "Valor"]
    if "source_status" in output.columns:
        output["Status da fonte"] = output["source_status"].map(_format_source_status)
        columns.append("Status da fonte")
    return output[columns]


def _format_aging_latest_table(default_buckets_latest_df: pd.DataFrame) -> pd.DataFrame:
    if default_buckets_latest_df.empty:
        return pd.DataFrame(columns=["Faixa", "Valor", "% da inadimplência", "% dos DCs"])
    output = default_buckets_latest_df.sort_values("ordem").copy() if "ordem" in default_buckets_latest_df.columns else default_buckets_latest_df.copy()
    output["Faixa"] = output["faixa"]
    output["Valor"] = output["valor"].map(_format_brl_compact)
    aging_percent_column = None
    dc_percent_column = None
    for candidate in ("percentual_inadimplencia", "percentual"):
        if candidate in output.columns:
            aging_percent_column = candidate
            break
    if "percentual_direitos_creditorios" in output.columns:
        dc_percent_column = "percentual_direitos_creditorios"
    output["% da inadimplência"] = output[aging_percent_column].map(_format_percent) if aging_percent_column else "N/D"
    output["% dos DCs"] = output[dc_percent_column].map(_format_percent) if dc_percent_column else "N/D"
    return output[["Faixa", "Valor", "% da inadimplência", "% dos DCs"]]


def _format_event_summary_table(event_summary_df: pd.DataFrame) -> pd.DataFrame:
    if event_summary_df.empty:
        return pd.DataFrame(columns=["Evento", "Valor bruto", "Efeito no caixa", "% do PL"])
    output = event_summary_df.sort_values("ordem").copy() if "ordem" in event_summary_df.columns else event_summary_df.copy()
    output["Evento"] = output["evento"]
    output["Valor bruto"] = output["valor_total"].map(_format_brl_compact)
    output["Efeito no caixa"] = output["valor_total_assinado"].map(_format_brl_compact)
    output["% do PL"] = output["valor_total_pct_pl"].map(_format_percent)
    return output[["Evento", "Valor bruto", "Efeito no caixa", "% do PL"]]


def _format_value_row(row: pd.Series) -> str:
    status = str(row.get("source_status", "reported_value"))
    raw_value = row.get("valor_raw", row.get("valor"))
    if status in {"missing_field", "not_reported", "not_numeric", "not_available"} and _is_missing_value(raw_value):
        return "N/D"
    return _format_brl_compact(row.get("valor"))


def _format_source_status(value: object) -> str:
    labels = {
        "reported_value": "Valor reportado",
        "reported_zero": "Zero reportado",
        "missing_field": "Campo ausente",
        "not_reported": "Não informado",
        "not_numeric": "Valor não numérico",
        "not_available": "Não disponível",
    }
    return labels.get(str(value), str(value or "N/D"))


def _format_tracking_value(row: pd.Series) -> str:
    if row.get("estado_dado") == "nao_aplicavel_sem_inadimplencia":
        return "N/A (sem inadimplência)"
    if row.get("estado_dado") == "nao_disponivel_na_fonte":
        return "N/D"
    if row.get("unidade") == "%":
        return _format_percent(row["valor"])
    return _format_decimal(row["valor"])


def _format_data_state(value: object) -> str:
    labels = {
        "calculado": "Calculado",
        "nao_calculavel": "Não calculável",
        "nao_calculavel_sem_pl": "Não calculável: sem PL",
        "nao_aplicavel_sem_inadimplencia": "Não aplicável: sem inadimplência",
        "nao_disponivel_na_fonte": "Não disponível na fonte",
    }
    return labels.get(str(value), str(value or "N/D"))


def _format_metric_value(value: object, unit: str) -> str:
    if unit == "R$":
        return _format_brl_compact(value)
    if unit == "%":
        return _format_percent(value)
    return _format_decimal(value)


def _format_metric_criticality(value: object) -> str:
    labels = {
        "critico": "Crítico",
        "monitorar": "Monitorar",
        "contexto": "Contexto",
    }
    return labels.get(str(value), str(value or "N/D"))


def _format_risk_metric_state(value: object) -> str:
    labels = {
        "calculado": "Calculado",
        "nao_calculavel": "Não calculável",
        "nao_calculavel_sem_pl": "Não calculável: sem PL",
        "nao_aplicavel_sem_inadimplencia": "Não aplicável: sem inadimplência",
        "nao_disponivel_na_fonte": "Não disponível na fonte",
        "nao_calculavel_sem_base": "Não calculável: sem base",
        "exige_fonte_complementar": "Exige fonte complementar",
    }
    return labels.get(str(value), str(value or "N/D"))


def _format_risk_metrics_table(metrics_df: pd.DataFrame, *, risk_block: str) -> pd.DataFrame:
    if metrics_df.empty:
        return pd.DataFrame(columns=["Métrica", "Valor", "Leitura"])
    output = metrics_df[metrics_df["risk_block"] == risk_block].copy()
    if output.empty:
        return pd.DataFrame(columns=["Métrica", "Valor", "Leitura"])
    output["Métrica"] = output["label"]
    output["Valor"] = output.apply(
        lambda row: _format_metric_value(row.get("value"), str(row.get("unit") or "")),
        axis=1,
    )
    output["Leitura"] = output["interpretation"]
    columns = ["Métrica", "Valor", "Leitura"]
    if not output["state"].fillna("calculado").eq("calculado").all():
        output["Estado"] = output["state"].map(_format_risk_metric_state)
        columns.append("Estado")
    return output[columns]


def _format_risk_metrics_compact_table(metrics_df: pd.DataFrame, *, risk_block: str) -> pd.DataFrame:
    """Compact Métrica | Valor table, without descriptive 'Leitura' column."""
    if metrics_df.empty:
        return pd.DataFrame(columns=["Métrica", "Valor"])
    output = metrics_df[metrics_df["risk_block"] == risk_block].copy()
    if output.empty:
        return pd.DataFrame(columns=["Métrica", "Valor"])
    output["Métrica"] = output["label"]
    output["Valor"] = output.apply(
        lambda row: _format_metric_value(row.get("value"), str(row.get("unit") or "")),
        axis=1,
    )
    return output[["Métrica", "Valor"]]


def _format_glossary_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Termo", "Definição curta", "Variação importante"])
    output = df.copy()
    output["Termo"] = output["termo"]
    output["Definição curta"] = output["definicao_curta"]
    output["Variação importante"] = output["variacao_importante"]
    return output[["Termo", "Definição curta", "Variação importante"]]


def _format_tracking_table(tracking_df: pd.DataFrame) -> pd.DataFrame:
    if tracking_df.empty:
        return pd.DataFrame(columns=["Indicador", "Valor", "Fonte", "Interpretação", "Estado"])
    output = tracking_df.copy()
    output["Indicador"] = output["indicador"]
    output["Valor"] = output.apply(
        _format_tracking_value,
        axis=1,
    )
    output["Fonte"] = output["fonte"]
    output["Interpretação"] = output["interpretação"]
    output["Estado"] = (
        output["estado_dado"].map(_format_data_state)
        if "estado_dado" in output.columns
        else "Calculado"
    )
    return output[["Indicador", "Valor", "Fonte", "Interpretação", "Estado"]]


def _format_holder_table(holder_df: pd.DataFrame) -> pd.DataFrame:
    if holder_df.empty:
        return pd.DataFrame(columns=["Grupo", "Categoria", "Quantidade"])
    output = holder_df.copy()
    output["Grupo"] = output["grupo"]
    output["Categoria"] = output["categoria"]
    output["Quantidade"] = output["quantidade"].map(lambda value: _format_decimal(value, decimals=0))
    return output[["Grupo", "Categoria", "Quantidade"]]


def _format_rate_table(rate_df: pd.DataFrame) -> pd.DataFrame:
    if rate_df.empty:
        return pd.DataFrame(columns=["Grupo", "Operação", "Mín.", "Média", "Máx."])
    output = rate_df.copy()
    output["Grupo"] = output["grupo"]
    output["Operação"] = output["operacao"]
    output["Mín."] = output["taxa_min"].map(_format_percent)
    output["Média"] = output["taxa_media"].map(_format_percent)
    output["Máx."] = output["taxa_max"].map(_format_percent)
    return output[["Grupo", "Operação", "Mín.", "Média", "Máx."]]


def _chart_labels_enabled() -> bool:
    return True


def _label_format(unit: str) -> str:
    return ",.2f" if unit in {"R$", "%"} else ",.2f"


def _single_series_bar_size(category_count: int) -> int:
    if category_count <= 4:
        return 58
    if category_count <= 6:
        return 50
    if category_count <= 9:
        return 42
    if category_count <= 12:
        return 36
    if category_count <= 16:
        return 30
    return 24


def _grouped_series_bar_size(period_count: int, series_count: int) -> int:
    if series_count >= 5:
        if period_count <= 6:
            return 18
        if period_count <= 9:
            return 15
        if period_count <= 12:
            return 12
        return 10
    if period_count <= 6:
        return 24
    if period_count <= 9:
        return 20
    if period_count <= 12:
        return 16
    return 12


def _executive_monthly_bar_size(category_count: int) -> int:
    return max(90, int(_single_series_bar_size(max(category_count, 1)) * 2.5))


def _executive_quota_bar_size(category_count: int) -> int:
    base = _single_series_bar_size(max(category_count, 1))
    if category_count <= 6:
        return max(56, int(base * 1.20))
    if category_count <= 12:
        return max(48, int(base * 1.36))
    return max(40, int(base * 1.52))


def _executive_grouped_bar_size(period_count: int, series_count: int) -> int:
    wide_bar_size = _executive_monthly_bar_size(period_count)
    return max(26, int(wide_bar_size / max(series_count, 1)))


def _hex_is_dark(color: str) -> bool:
    value = str(color or "").strip().lstrip("#")
    if len(value) != 6:
        return False
    try:
        red = int(value[0:2], 16)
        green = int(value[2:4], 16)
        blue = int(value[4:6], 16)
    except ValueError:
        return False
    luminance = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
    return luminance < 150


def _contrast_text_color(fill_color: str) -> str:
    return "#ffffff" if _hex_is_dark(fill_color) else "#111111"


def _category_color_map(categories: list[str], color_range: list[str]) -> dict[str, str]:
    if not categories:
        return {}
    return {category: color_range[index % len(color_range)] for index, category in enumerate(categories)}


def _quant_scale_with_headroom(
    values: pd.Series,
    *,
    percent_like: bool = False,
    floor_zero: bool = True,
    max_cap: float | None = None,
) -> alt.Scale:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return alt.Scale(zero=floor_zero)
    min_value = float(numeric.min())
    max_value = float(numeric.max())
    if percent_like:
        # Proportional headroom: ~25–60% of max, avoiding the previous flat +4 pp
        # that crushed small-range charts (e.g. NPL 0–1%). Guard against zero/negative
        # max_value to prevent invalid Altair domains.
        if max_value <= 0:
            upper = 5.0
        else:
            headroom = max(max_value * 0.25, min(max_value * 0.60, 2.0))
            upper = max_value + headroom
        if max_cap is not None:
            upper = min(upper, max_cap)
        lower = 0.0 if floor_zero else min_value
        if upper <= lower:
            upper = lower + 5.0
        return alt.Scale(domain=[lower, upper], nice=False)
    if max_value >= 0:
        upper = max(max_value * 1.14, max_value + max(1.0, abs(max_value) * 0.06))
    else:
        upper = max_value * 0.94
    lower = 0.0 if floor_zero and min_value >= 0 else min_value * 1.08
    return alt.Scale(domain=[lower, upper], nice=False)


def _nice_axis_ticks(values: pd.Series, *, steps: int = 4) -> list[float] | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return None
    max_value = float(numeric.max())
    if max_value <= 0:
        return [0.0]
    step_value = max_value / max(steps, 1)
    return [round(step_value * idx, 2) for idx in range(steps + 1)]


def _series_legend(title: str, series_count: int) -> alt.Legend:
    return alt.Legend(
        title=title,
        orient="top",
        direction="horizontal",
        columns=max(1, min(series_count, 5)),
        symbolType="square",
        labelLimit=180,
    )


def _line_point_label_layer(
    chart_df: pd.DataFrame,
    *,
    y_title: str,
    font_size: int = 12,
    font_weight: int = 600,
) -> alt.Chart | None:
    if not _chart_labels_enabled() or chart_df.empty or "serie" not in chart_df.columns:
        return None
    labels_df = chart_df.sort_values(["competencia_dt", "serie"]).copy()
    if labels_df.empty:
        return None
    labels_df["label_valor"] = labels_df["valor"]
    adjusted_groups: list[pd.DataFrame] = []
    for _, group_df in labels_df.groupby("competencia", dropna=False):
        ordered = group_df.sort_values("valor").reset_index(drop=True).copy()
        value_span = ordered["valor"].max() - ordered["valor"].min()
        if pd.isna(value_span) or value_span == 0:
            value_span = max(abs(float(ordered["valor"].max() or 0.0)), 1.0)
        step = value_span * 0.05
        midpoint = (len(ordered) - 1) / 2.0
        ordered["label_valor"] = ordered["valor"] + ((ordered.index - midpoint) * step)
        adjusted_groups.append(ordered)
    labels_df = pd.concat(adjusted_groups, ignore_index=True) if adjusted_groups else labels_df
    labels_df["valor_label"] = labels_df["valor"].map(lambda value: _format_value_label(value, y_title))
    x_sort = _competencia_axis_sort(chart_df)
    return (
        alt.Chart(labels_df)
        .mark_text(
            align="center",
            dy=-10,
            fontSize=font_size,
            fontWeight=font_weight,
            color="#111111",
            clip=False,
        )
        .encode(
            x=alt.X("competencia:N", sort=x_sort),
            y=alt.Y("label_valor:Q", title=y_title),
            text=alt.Text("valor_label:N"),
        )
    )


def _build_line_series_end_labels_df(
    chart_df: pd.DataFrame,
    *,
    y_title: str,
    min_gap_override: float | None = None,
    label_text_column: str | None = None,
) -> pd.DataFrame:
    if not _chart_labels_enabled() or chart_df.empty or "serie" not in chart_df.columns:
        return pd.DataFrame()
    sort_columns = [column for column in ["competencia_dt", "competencia", "serie"] if column in chart_df.columns]
    labels_df = chart_df.sort_values(sort_columns).groupby("serie", as_index=False, dropna=False).tail(1).copy()
    if labels_df.empty:
        return pd.DataFrame()
    values = pd.to_numeric(labels_df["valor"], errors="coerce")
    if values.dropna().empty:
        return pd.DataFrame()
    span = float(values.max() - values.min()) if len(values.dropna()) > 1 else 0.0
    max_abs = float(values.abs().max()) if not values.dropna().empty else 0.0
    min_gap = min_gap_override if min_gap_override is not None else max(span * 0.04, 1.2 if "%" in y_title else max(max_abs * 0.02, 0.6))
    ordered = labels_df.assign(valor_num=values).sort_values("valor_num").reset_index(drop=True)
    adjusted_values: list[float] = []
    for _, row in ordered.iterrows():
        current_value = float(row["valor_num"])
        if not adjusted_values:
            adjusted_values.append(current_value)
            continue
        adjusted_values.append(max(current_value, adjusted_values[-1] + min_gap))
    ordered["label_valor"] = adjusted_values
    resolved_label_column = label_text_column if label_text_column and label_text_column in ordered.columns else "label_fmt"
    if resolved_label_column in ordered.columns:
        ordered["end_label"] = ordered[resolved_label_column].astype(str)
    else:
        ordered["end_label"] = ordered["valor"].map(lambda value: _format_value_label(value, y_title))
    return ordered


def _line_series_end_label_layer(
    labels_df: pd.DataFrame,
    *,
    x_sort: list[str],
    y_title: str,
    color_range: list[str],
    series_order: list[str],
) -> alt.Chart | None:
    if labels_df.empty:
        return None
    return (
        alt.Chart(labels_df)
        .mark_text(
            align="left",
            dx=12,
            fontSize=12,
            fontWeight=700,
            clip=False,
        )
        .encode(
            x=alt.X("competencia:N", sort=x_sort),
            y=alt.Y("label_valor:Q", title=y_title),
            text=alt.Text("end_label:N"),
            color=alt.Color(
                "serie:N",
                scale=alt.Scale(domain=series_order, range=color_range),
                sort=series_order,
                legend=None,
            ),
        )
    )


def _point_label_layer(
    chart_df: pd.DataFrame,
    *,
    x_encoding: alt.X,
    y_encoding: alt.Y,
    y_field: str,
    text_field: str | None = None,
    color: str = "#111111",
) -> alt.Chart | None:
    if not _chart_labels_enabled() or chart_df.empty:
        return None
    return (
        alt.Chart(chart_df)
        .mark_text(dy=-9, fontSize=11, fontWeight=600, color=color)
        .encode(
            x=x_encoding,
            y=y_encoding,
            text=alt.Text(f"{text_field or y_field}:N" if text_field else f"{y_field}:Q", format=None if text_field else _label_format(y_encoding.title or "")),
        )
    )


def _bar_label_layer(
    chart_df: pd.DataFrame,
    *,
    x_encoding: alt.X | None,
    y_encoding: alt.Y | None,
    value_field: str,
    text_field: str | None = None,
    orient: str = "vertical",
    color_encoding: alt.Color | None = None,
    x_offset_field: str | None = None,
    font_size: int = 11,
    font_weight: int = 600,
    dy: int = -9,
) -> alt.Chart | None:
    if not _chart_labels_enabled() or chart_df.empty:
        return None
    # Labels above bars land on white background — use dark text, no stroke halo
    # (white stroke with strokeWidth≥2 washes out thin characters on white bg)
    mark_kwargs: dict[str, object] = {
        "fontSize": font_size,
        "fontWeight": font_weight,
        "color": "#111111",
        "clip": False,
    }
    if orient == "horizontal":
        mark_kwargs.update({"align": "left", "dx": 6})
    else:
        mark_kwargs.update({"dy": dy})
    encoding: dict[str, object] = {
        "text": (
            alt.Text(f"{text_field}:N")
            if text_field
            else alt.Text(f"{value_field}:Q", format=_label_format(y_encoding.title if y_encoding is not None else ""))
        ),
    }
    if x_encoding is not None:
        encoding["x"] = x_encoding
    if y_encoding is not None:
        encoding["y"] = y_encoding
    if x_offset_field:
        encoding["xOffset"] = alt.XOffset(f"{x_offset_field}:N")
    # Never inherit bar fill color for above-bar labels — always use dark text
    return alt.Chart(chart_df).mark_text(**mark_kwargs).encode(**encoding)


def _chart_with_optional_title(chart: alt.Chart, *, height: int, title: str | None) -> alt.Chart:
    chart = chart.properties(height=height)
    if title is not None:
        chart = chart.properties(title=title)
    return chart


def _line_history_chart(
    chart_df: pd.DataFrame,
    *,
    title: str | None,
    y_title: str,
    color_range: list[str] | None = None,
    show_point_labels: bool = True,
    show_end_labels: bool = False,
    end_label_text_column: str | None = None,
    point_label_font_size: int = 12,
    point_label_font_weight: int = 600,
    point_size: int = 58,
    limit_value: float | None = None,
    limit_label: str | None = None,
    reference_value: float | None = None,
    reference_label: str | None = None,
) -> alt.Chart:
    if limit_value is None and reference_value is not None:
        limit_value = reference_value
    if limit_label is None and reference_label is not None:
        limit_label = reference_label
    chart_df = _altair_compatible_df(chart_df)
    chart_df = _sort_competencia_display_frame(chart_df)
    if "competencia" in chart_df.columns:
        chart_df["competencia"] = chart_df["competencia"].map(_format_competencia_display)
    x_sort = _competencia_axis_sort(chart_df)
    chart_df["valor_fmt"] = chart_df["valor"].map(lambda value: _format_brl_compact(value) if y_title == "R$" else _format_percent(value) if "%" in y_title else _format_decimal(value))
    chart_df["label_fmt"] = chart_df["valor"].map(lambda value: _format_value_label(value, y_title))
    series_order = chart_df["serie"].drop_duplicates().tolist()
    end_labels_df = (
        _build_line_series_end_labels_df(
            chart_df,
            y_title=y_title,
            label_text_column=end_label_text_column,
        )
        if show_end_labels
        else pd.DataFrame()
    )
    scale_values = pd.to_numeric(chart_df["valor"], errors="coerce")
    if not end_labels_df.empty:
        scale_values = pd.concat(
            [scale_values, pd.to_numeric(end_labels_df["label_valor"], errors="coerce")],
            ignore_index=True,
        )
    if show_point_labels:
        point_values = pd.to_numeric(chart_df["valor"], errors="coerce").dropna()
        if not point_values.empty:
            point_max = float(point_values.max())
            point_min = float(point_values.min())
            point_padding = (
                max(abs(point_max) * 0.08, 2.0)
                if "%" in y_title
                else max(abs(point_max) * 0.08, 1.0)
            )
            scale_values = pd.concat([scale_values, pd.Series([point_max + point_padding])], ignore_index=True)
            if point_min < 0:
                scale_values = pd.concat(
                    [scale_values, pd.Series([point_min - (point_padding * 0.35)])],
                    ignore_index=True,
                )
    x_encoding = alt.X("competencia:N", title="Competência", sort=x_sort)
    y_axis = alt.Axis(labelExpr=_brl_axis_label_expr()) if y_title == "R$" else alt.Axis()
    y_encoding = alt.Y(
        "valor:Q",
        title=y_title,
        axis=y_axis,
        scale=_quant_scale_with_headroom(scale_values, percent_like="%" in y_title),
    )
    base = (
        alt.Chart(chart_df)
        .mark_line(
            point=alt.OverlayMarkDef(filled=True, size=point_size),
            strokeWidth=2.4,
        )
        .encode(
            x=x_encoding,
            y=y_encoding,
            color=alt.Color(
                "serie:N",
                title="Série",
                scale=alt.Scale(domain=series_order, range=(color_range or FIDC_CHART_COLORS)[: len(series_order)]),
                sort=series_order,
                legend=None if len(series_order) <= 1 else alt.Legend(),
            ),
            tooltip=["competencia:N", "serie:N", alt.Tooltip("valor_fmt:N", title="Valor")],
        )
    )
    base = _chart_with_optional_title(base, height=320, title=title)
    labels = (
        _line_point_label_layer(
            chart_df.assign(valor_label=chart_df["label_fmt"]),
            y_title=y_title,
            font_size=point_label_font_size,
            font_weight=point_label_font_weight,
        )
        if show_point_labels
        else None
    )
    layered = base if labels is None else (base + labels)
    if show_end_labels:
        end_labels = _line_series_end_label_layer(
            end_labels_df,
            x_sort=x_sort,
            y_title=y_title,
            color_range=(color_range or FIDC_CHART_COLORS)[: len(series_order)],
            series_order=series_order,
        )
        if end_labels is not None:
            layered = layered + end_labels
        layered = layered.properties(padding={"left": 8, "right": 96, "top": 8, "bottom": 8})
    if limit_value is None:
        return _style_altair_chart(layered)

    limit_df = pd.DataFrame({"valor": [limit_value]})
    rule = (
        alt.Chart(limit_df)
        .mark_rule(strokeDash=[6, 4], color="#6b7280")
        .encode(y="valor:Q", tooltip=[alt.Tooltip("valor:Q", format=",.2f", title=limit_label or "Limite")])
    )
    return _style_altair_chart(layered + rule)


def _over_focus_line_chart(
    chart_df: pd.DataFrame,
    *,
    title: str | None,
    y_title: str,
    headline_series: tuple[str, ...] = ("Over 30", "Over 90"),
) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df)
    chart_df = _sort_competencia_display_frame(chart_df, extra_columns=["serie"])
    if "competencia" in chart_df.columns:
        chart_df["competencia"] = chart_df["competencia"].map(_format_competencia_display)
    chart_df = chart_df.dropna(subset=["valor"]).copy()
    if chart_df.empty:
        empty_chart = (
            alt.Chart(pd.DataFrame(columns=["competencia", "valor"]))
            .mark_line()
            .encode(x="competencia:N", y=alt.Y("valor:Q", title=y_title))
        )
        return _style_altair_chart(_chart_with_optional_title(empty_chart, height=640, title=title))

    x_sort = _competencia_axis_sort(chart_df)
    observed_series = chart_df["serie"].dropna().astype(str).drop_duplicates().tolist()
    series_order = [serie for serie in OVER_SERIES_ORDER if serie in set(observed_series)]
    series_order.extend([serie for serie in observed_series if serie not in set(series_order)])
    color_by_series = {
        "Over 1": "#BDBDBD",
        "Over 30": "#EC7000",
        "Over 60": "#757575",
        "Over 90": "#1F1F1F",
        "Over 180": "#4D4D4D",
        "Over 360": "#E0E0E0",
    }
    color_range = [color_by_series.get(serie, "#6E6E6E") for serie in series_order]
    headline_set = set(headline_series)
    chart_df["stroke_width"] = chart_df["serie"].map(lambda serie: 3.1 if str(serie) in headline_set else 1.45)
    chart_df["series_opacity"] = chart_df["serie"].map(lambda serie: 1.0 if str(serie) in headline_set else 0.48)
    chart_df["point_size"] = chart_df["serie"].map(lambda serie: 80 if str(serie) in headline_set else 34)
    chart_df["valor_fmt"] = chart_df["valor"].map(_format_percent)
    chart_df["label_fmt"] = chart_df["valor"].map(lambda value: _format_value_label(value, y_title))

    end_labels_df = _build_line_series_end_labels_df(chart_df, y_title=y_title, min_gap_override=1.4)
    scale_values = pd.to_numeric(chart_df["valor"], errors="coerce")
    if not end_labels_df.empty:
        scale_values = pd.concat(
            [scale_values, pd.to_numeric(end_labels_df["label_valor"], errors="coerce")],
            ignore_index=True,
        )

    x_encoding = alt.X("competencia:N", title="Competência", sort=x_sort)
    y_encoding = alt.Y(
        "valor:Q",
        title=y_title,
        axis=alt.Axis(),
        scale=_quant_scale_with_headroom(scale_values, percent_like=True),
    )
    color_encoding = alt.Color(
        "serie:N",
        title="Série",
        scale=alt.Scale(domain=series_order, range=color_range),
        sort=series_order,
        legend=_series_legend("Série", len(series_order)),
    )
    base = alt.Chart(chart_df).encode(
        x=x_encoding,
        y=y_encoding,
        color=color_encoding,
        detail="serie:N",
        tooltip=["competencia:N", "serie:N", alt.Tooltip("valor_fmt:N", title="Valor")],
    )
    lines = base.mark_line().encode(
        strokeWidth=alt.StrokeWidth("stroke_width:Q", legend=None),
        opacity=alt.Opacity("series_opacity:Q", legend=None),
    )
    points = base.mark_point(filled=True).encode(
        size=alt.Size("point_size:Q", legend=None),
        opacity=alt.Opacity("series_opacity:Q", legend=None),
    )
    layered: alt.Chart = _chart_with_optional_title(lines + points, height=640, title=title)
    end_labels = _line_series_end_label_layer(
        end_labels_df,
        x_sort=x_sort,
        y_title=y_title,
        color_range=color_range,
        series_order=series_order,
    )
    if end_labels is not None:
        layered = layered + end_labels
        layered = layered.properties(padding={"left": 8, "right": 118, "top": 8, "bottom": 8})
    return _style_altair_chart(layered)


def _line_point_chart(
    chart_df: pd.DataFrame,
    *,
    x_column: str,
    y_column: str,
    title: str | None,
    y_title: str,
) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df)
    chart_df = chart_df.copy()
    chart_df["valor_fmt"] = chart_df[y_column].map(lambda value: _format_brl(value) if y_title == "R$" else _format_percent(value) if "%" in y_title else _format_decimal(value))
    chart_df["label_fmt"] = chart_df[y_column].map(lambda value: _format_value_label(value, y_title))
    x_encoding = alt.X(f"{x_column}:N", title="Horizonte")
    y_encoding = alt.Y(
        f"{y_column}:Q",
        title=y_title,
        scale=_quant_scale_with_headroom(chart_df[y_column], percent_like="%" in y_title),
    )
    chart = (
        alt.Chart(chart_df)
        .mark_line(point=True)
        .encode(
            x=x_encoding,
            y=y_encoding,
            tooltip=[f"{x_column}:N", alt.Tooltip("valor_fmt:N", title="Valor")],
        )
    )
    chart = _chart_with_optional_title(chart, height=320, title=title)
    labels = _point_label_layer(chart_df, x_encoding=x_encoding, y_encoding=y_encoding, y_field=y_column, text_field="label_fmt")
    return _style_altair_chart(chart if labels is None else (chart + labels))


def _horizontal_bar_chart(
    chart_df: pd.DataFrame,
    *,
    category_column: str,
    value_column: str,
    title: str,
) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df)
    chart_df = chart_df.copy()
    chart_df["valor_fmt"] = chart_df[value_column].map(_format_brl_compact)
    x_encoding = alt.X(f"{value_column}:Q", title="R$", axis=alt.Axis(labelExpr=_brl_axis_label_expr()))
    y_encoding = alt.Y(f"{category_column}:N", title=None, sort="-x")
    color_encoding = alt.Color(f"{category_column}:N", legend=None, scale=alt.Scale(range=FIDC_CHART_COLORS))
    chart = (
        alt.Chart(chart_df)
        .mark_bar()
        .encode(
            x=x_encoding,
            y=y_encoding,
            color=color_encoding,
            tooltip=[f"{category_column}:N", alt.Tooltip("valor_fmt:N", title="Valor")],
        )
        .properties(title=title, height=320)
    )
    labels = _bar_label_layer(
        chart_df,
        x_encoding=x_encoding,
        y_encoding=y_encoding,
        value_field=value_column,
        orient="horizontal",
    )
    return _style_altair_chart(chart if labels is None else (chart + labels))


def _percent_bar_chart(
    chart_df: pd.DataFrame,
    *,
    category_column: str,
    percent_column: str,
    title: str | None,
    value_column: str | None = None,
) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df.dropna(subset=[percent_column]).copy())
    chart_df = chart_df.sort_values(percent_column, ascending=False)
    chart_df["percentual_fmt"] = chart_df[percent_column].map(_format_percent)
    chart_df["percentual_label"] = chart_df[percent_column].map(_format_percent_label)
    x_encoding = alt.X(f"{category_column}:N", title=None, sort=chart_df[category_column].drop_duplicates().tolist())
    y_encoding = alt.Y(
        f"{percent_column}:Q",
        title="%",
        scale=_quant_scale_with_headroom(chart_df[percent_column], percent_like=True),
    )
    tooltip: list[object] = [f"{category_column}:N", alt.Tooltip("percentual_fmt:N", title="% do total")]
    if value_column and value_column in chart_df.columns:
        chart_df["valor_fmt"] = chart_df[value_column].map(_format_brl_compact)
        tooltip.append(alt.Tooltip("valor_fmt:N", title="Valor"))
    if "source_status" in chart_df.columns:
        chart_df["status_fonte"] = chart_df["source_status"].map(_format_source_status)
        tooltip.append("status_fonte:N")
    chart = (
        alt.Chart(chart_df)
        .mark_bar(color="#ff5a00")
        .encode(
            x=x_encoding,
            y=y_encoding,
            tooltip=tooltip,
        )
    )
    chart = _chart_with_optional_title(chart, height=320, title=title)
    labels = _bar_label_layer(chart_df, x_encoding=x_encoding, y_encoding=y_encoding, value_field=percent_column, text_field="percentual_label")
    return _style_altair_chart(chart if labels is None else (chart + labels))


def _stacked_share_column_chart(
    chart_df: pd.DataFrame,
    *,
    category_column: str,
    percent_column: str,
    value_column: str,
    title: str | None,
    stack_label: str,
    order_column: str | None = None,
    height: int = 320,
    bar_size: int = 84,
    label_font_size: int = 13,
    color_range: list[str] | None = None,
) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df.dropna(subset=[percent_column]).copy())
    chart_df = chart_df[chart_df[percent_column] > 0].copy()
    if chart_df.empty:
        empty_df = pd.DataFrame(columns=["stack_label", percent_column])
        empty_chart = (
            alt.Chart(empty_df)
            .mark_bar()
            .encode(x="stack_label:N", y=alt.Y(f"{percent_column}:Q", title="% do total"))
        )
        return _style_altair_chart(_chart_with_optional_title(empty_chart, height=height, title=title))
    chart_df["stack_label"] = stack_label
    chart_df["label_pct"] = chart_df[percent_column].map(_format_percent_label)
    chart_df["valor_fmt"] = chart_df[value_column].map(_format_brl)
    x_encoding = alt.X("stack_label:N", title=None, axis=alt.Axis(labels=False, ticks=False))
    y_encoding = alt.Y(
        f"{percent_column}:Q",
        title="% do total",
        stack=True,
        scale=alt.Scale(domain=[0, 112], nice=False),
    )
    color_sort = (
        chart_df.sort_values(order_column)[category_column].tolist()
        if order_column and order_column in chart_df.columns
        else chart_df.sort_values(percent_column, ascending=False)[category_column].tolist()
    )
    color_encoding = alt.Color(
        f"{category_column}:N",
        title=None,
        scale=alt.Scale(range=color_range or FIDC_CHART_COLORS),
        sort=color_sort,
    )
    color_map = _category_color_map(color_sort, color_range or FIDC_CHART_COLORS)
    chart_df["label_color"] = chart_df[category_column].map(lambda value: _contrast_text_color(color_map.get(str(value), "#ff5a00")))
    tooltip: list[object] = [
        alt.Tooltip(f"{category_column}:N", title="Faixa"),
        alt.Tooltip("label_pct:N", title="% do total"),
        alt.Tooltip("valor_fmt:N", title="Valor"),
    ]
    if "source_status" in chart_df.columns:
        chart_df["status_fonte"] = chart_df["source_status"].map(_format_source_status)
        tooltip.append("status_fonte:N")
    chart = (
        alt.Chart(chart_df)
        .mark_bar(size=bar_size)
        .encode(
            x=x_encoding,
            y=y_encoding,
            color=color_encoding,
            order=alt.Order(f"{order_column}:Q", sort="ascending") if order_column and order_column in chart_df.columns else alt.Order(f"{percent_column}:Q", sort="descending"),
            tooltip=tooltip,
        )
    )
    chart = _chart_with_optional_title(chart, height=height, title=title)
    labels_df = chart_df.copy()
    labels = (
        alt.Chart(labels_df)
        .mark_text(fontSize=label_font_size, fontWeight=600, clip=False)
        .encode(
            x=x_encoding,
            y=alt.Y(f"{percent_column}:Q", stack="center", title="% do total"),
            detail=f"{category_column}:N",
            text=alt.Text("label_pct:N"),
            color=alt.Color("label_color:N", scale=None, legend=None),
        )
    )
    return _style_altair_chart(chart + labels)


def _maturity_waterfall_chart_frame(maturity_latest_df: pd.DataFrame) -> pd.DataFrame:
    if maturity_latest_df.empty:
        return pd.DataFrame(
            columns=[
                "ordem",
                "etapa",
                "valor_etapa",
                "bar_start",
                "bar_end",
                "cumulative",
                "tipo",
                "valor_fmt",
                "cumulative_fmt",
            ]
        )
    chart_df = _altair_compatible_df(maturity_latest_df.copy())
    chart_df["valor"] = pd.to_numeric(chart_df["valor"], errors="coerce").fillna(0.0)
    if "ordem" in chart_df.columns:
        chart_df = chart_df.sort_values("ordem").reset_index(drop=True)
    else:
        chart_df = chart_df.reset_index(drop=True)
    chart_df = chart_df[chart_df["faixa"] != "Vencidos"].copy()
    if chart_df.empty:
        return pd.DataFrame(
            columns=[
                "ordem",
                "etapa",
                "valor_etapa",
                "bar_start",
                "bar_end",
                "cumulative",
                "tipo",
                "valor_fmt",
                "cumulative_fmt",
            ]
        )
    rows: list[dict[str, object]] = []
    cumulative = 0.0
    for idx, row in chart_df.iterrows():
        etapa = str(row.get("faixa") or f"Faixa {idx + 1}")
        valor_etapa = float(row.get("valor") or 0.0)
        bar_start = cumulative
        bar_end = cumulative + valor_etapa
        rows.append(
            {
                "ordem": idx + 1,
                "etapa": etapa,
                "valor_etapa": valor_etapa,
                "bar_start": bar_start,
                "bar_end": bar_end,
                "cumulative": bar_end,
                "tipo": "inicio" if idx == 0 else "incremento",
                "valor_fmt": _format_brl_compact(valor_etapa),
                "cumulative_fmt": _format_brl_compact(bar_end),
            }
        )
        cumulative = bar_end
    rows.append(
        {
            "ordem": len(rows) + 1,
            "etapa": "Total",
            "valor_etapa": cumulative,
            "bar_start": 0.0,
            "bar_end": cumulative,
            "cumulative": cumulative,
            "tipo": "total",
            "valor_fmt": _format_brl_compact(cumulative),
            "cumulative_fmt": _format_brl_compact(cumulative),
        }
    )
    return pd.DataFrame(rows)


def _maturity_waterfall_chart(maturity_latest_df: pd.DataFrame, *, title: str | None) -> alt.Chart:
    chart_df = _maturity_waterfall_chart_frame(maturity_latest_df)
    if chart_df.empty:
        empty_chart = (
            alt.Chart(pd.DataFrame(columns=["etapa", "bar_end"]))
            .mark_bar()
            .encode(x="etapa:N", y=alt.Y("bar_end:Q", title="R$"))
        )
        return _style_altair_chart(_chart_with_optional_title(empty_chart, height=340, title=title))
    x_sort = chart_df.sort_values("ordem")["etapa"].tolist()
    color_scale = alt.Scale(
        domain=["inicio", "incremento", "total"],
        range=["#111111", "#ff5a00", "#111111"],
    )
    y_encoding = alt.Y(
        "bar_end:Q",
        title="R$",
        axis=alt.Axis(labelExpr=_brl_axis_label_expr()),
        scale=_quant_scale_with_headroom(chart_df["bar_end"], percent_like=False),
    )
    bars = (
        alt.Chart(chart_df)
        .mark_bar(size=_executive_monthly_bar_size(chart_df["etapa"].nunique()))
        .encode(
            x=alt.X("etapa:N", title=None, sort=x_sort),
            y=y_encoding,
            y2="bar_start:Q",
            color=alt.Color("tipo:N", scale=color_scale, legend=None),
            tooltip=[
                alt.Tooltip("etapa:N", title="Etapa"),
                alt.Tooltip("valor_fmt:N", title="Fluxo"),
                alt.Tooltip("cumulative_fmt:N", title="Acumulado"),
            ],
        )
    )
    connector_df = chart_df.iloc[:-1].copy()
    connector_df["etapa_proxima"] = chart_df["etapa"].shift(-1)
    connector_df = connector_df[connector_df["etapa_proxima"].notna()].copy()
    connectors = (
        alt.Chart(connector_df)
        .mark_rule(color="#9ca3af", strokeDash=[4, 4], strokeWidth=1.3)
        .encode(
            x=alt.X("etapa:N", sort=x_sort),
            x2="etapa_proxima:N",
            y=alt.Y("bar_end:Q", title="R$"),
        )
    )
    labels = (
        alt.Chart(chart_df)
        .mark_text(dy=-9, fontSize=13, fontWeight=700, color="#111111", clip=False)
        .encode(
            x=alt.X("etapa:N", sort=x_sort),
            y=alt.Y("bar_end:Q", title="R$"),
            text=alt.Text("valor_fmt:N"),
        )
    )
    chart = _chart_with_optional_title(bars + connectors + labels, height=340, title=title)
    return _style_altair_chart(chart)


def _bar_chart(
    chart_df: pd.DataFrame,
    *,
    x_column: str,
    y_column: str,
    title: str | None,
    y_title: str,
) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df)
    chart_df = chart_df.copy()
    x_sort = (
        chart_df.sort_values("ordem")[x_column].tolist()
        if "ordem" in chart_df.columns
        else chart_df[x_column].drop_duplicates().tolist()
    )
    chart_df["valor_fmt"] = chart_df[y_column].map(lambda value: _format_brl_compact(value) if y_title == "R$" else _format_percent(value) if "%" in y_title else _format_decimal(value))
    chart_df["label_fmt"] = chart_df[y_column].map(lambda value: _format_value_label(value, y_title))
    tooltip = [f"{x_column}:N", alt.Tooltip("valor_fmt:N", title="Valor")]
    if "source_status" in chart_df.columns:
        chart_df["status_fonte"] = chart_df["source_status"].map(_format_source_status)
        tooltip.append("status_fonte:N")
    x_encoding = alt.X(f"{x_column}:N", title=None, sort=x_sort)
    y_axis = alt.Axis(labelExpr=_brl_axis_label_expr()) if y_title == "R$" else alt.Axis()
    y_encoding = alt.Y(
        f"{y_column}:Q",
        title=y_title,
        axis=y_axis,
        scale=_quant_scale_with_headroom(chart_df[y_column], percent_like="%" in y_title),
    )
    bar_size = _single_series_bar_size(len(x_sort))
    chart = (
        alt.Chart(chart_df)
        .mark_bar(color="#ff5a00", size=bar_size)
        .encode(
            x=x_encoding,
            y=y_encoding,
            tooltip=tooltip,
        )
    )
    chart = _chart_with_optional_title(chart, height=320, title=title)
    labels = _bar_label_layer(
        chart_df,
        x_encoding=x_encoding,
        y_encoding=y_encoding,
        value_field=y_column,
        text_field="label_fmt",
        font_size=12,
    )
    return _style_altair_chart(chart if labels is None else (chart + labels))


def _history_bar_chart(
    chart_df: pd.DataFrame,
    *,
    title: str | None,
    y_title: str,
    reference_value: float | None = None,
    reference_label: str | None = None,
) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df.copy())
    chart_df = _sort_competencia_display_frame(chart_df)
    if "competencia" in chart_df.columns:
        chart_df["competencia"] = chart_df["competencia"].map(_format_competencia_display)
    x_sort = _competencia_axis_sort(chart_df)
    chart_df["valor_fmt"] = chart_df["valor"].map(_format_percent if "%" in y_title else _format_brl_compact)
    chart_df["label_fmt"] = chart_df["valor"].map(lambda value: _format_value_label(value, y_title))
    x_encoding = alt.X("competencia:N", title="Competência", sort=x_sort)
    y_axis = alt.Axis(labelExpr=_brl_axis_label_expr()) if y_title == "R$" else alt.Axis()
    y_encoding = alt.Y(
        "valor:Q",
        title=y_title,
        axis=y_axis,
        scale=_quant_scale_with_headroom(chart_df["valor"], percent_like="%" in y_title, max_cap=140.0 if "%" in y_title else None),
    )
    bar_size = _single_series_bar_size(chart_df["competencia"].nunique())
    chart = (
        alt.Chart(chart_df)
        .mark_bar(color="#ff5a00", size=bar_size)
        .encode(
            x=x_encoding,
            y=y_encoding,
            tooltip=["competencia:N", alt.Tooltip("valor_fmt:N", title="Valor")],
        )
    )
    chart = _chart_with_optional_title(chart, height=300, title=title)
    labels = _bar_label_layer(
        chart_df,
        x_encoding=x_encoding,
        y_encoding=y_encoding,
        value_field="valor",
        text_field="label_fmt",
        font_size=12,
    )
    layered = chart if labels is None else (chart + labels)
    if reference_value is not None:
        ref_df = pd.DataFrame({"y": [reference_value]})
        ref_rule = (
            alt.Chart(ref_df)
            .mark_rule(strokeDash=[6, 4], color="#6b7280", strokeWidth=1.5)
            .encode(
                y=alt.Y("y:Q"),
                tooltip=[alt.Tooltip("y:Q", title=reference_label or "Referência", format=".0f")],
            )
        )
        ref_label = (
            alt.Chart(ref_df)
            .mark_text(align="right", dx=-4, dy=-6, fontSize=10, color="#6b7280", clip=False)
            .encode(
                y=alt.Y("y:Q"),
                x=alt.value(0),
                text=alt.value(reference_label or f"{reference_value:.0f}%"),
            )
        )
        layered = layered + ref_rule + ref_label
    return _style_altair_chart(layered)


def _stacked_history_bar_chart(
    chart_df: pd.DataFrame,
    *,
    title: str | None,
    y_title: str,
    value_column: str,
    show_total_labels: bool = False,
    color_range: list[str] | None = None,
    height: int = 320,
    bar_size: int | None = None,
    label_font_size: int = 9,
    force_all_segment_labels: bool = False,
    inside_label_color: str | None = None,
    inner_label_threshold: float | None = None,
    outer_label_threshold: float | None = None,
    allow_outside_labels: bool = True,
    round_percent_labels: bool = False,
    smart_label_placement: bool = False,
    legend_series_order: list[str] | None = None,
    show_segment_labels: bool = True,
    max_segment_labels_per_competencia: int | None = None,
) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df.copy())
    chart_df = _sort_competencia_display_frame(chart_df, extra_columns=["ordem", "serie"])
    if "competencia" in chart_df.columns:
        chart_df["competencia"] = chart_df["competencia"].map(_format_competencia_display)
    if chart_df.empty:
        empty_chart = (
            alt.Chart(pd.DataFrame(columns=["competencia", value_column]))
            .mark_bar()
            .encode(x="competencia:N", y=alt.Y(f"{value_column}:Q", title=y_title))
        )
        return _style_altair_chart(_chart_with_optional_title(empty_chart, height=height, title=title))
    x_sort = _competencia_axis_sort(chart_df)
    resolved_value_column = _resolve_stacked_chart_value_column(chart_df, value_column)
    chart_df["valor_fmt"] = chart_df[resolved_value_column].map(
        _format_brl_compact if y_title == "R$" else _format_percent
    )
    if "label_fmt" not in chart_df.columns:
        chart_df["label_fmt"] = chart_df[resolved_value_column].map(
            _format_percent_rounded_label
            if round_percent_labels and "%" in y_title
            else (lambda value: _format_value_label(value, y_title))
        )
    x_encoding = alt.X("competencia:N", title="Competência", sort=x_sort)
    y_axis = alt.Axis(labelExpr=_brl_axis_label_expr()) if y_title == "R$" else alt.Axis()
    totals_for_scale = chart_df.groupby("competencia", dropna=False)[resolved_value_column].sum()
    y_encoding = alt.Y(
        f"{resolved_value_column}:Q",
        title=y_title,
        stack=True,
        axis=y_axis,
        scale=_quant_scale_with_headroom(
            totals_for_scale,
            percent_like="%" in y_title,
            max_cap=140.0 if "%" in y_title else None,
        ),
    )
    _colors = color_range or FIDC_CHART_COLORS
    series_order = (
        chart_df.sort_values("ordem")["serie"].drop_duplicates().tolist()
        if "ordem" in chart_df.columns
        else chart_df["serie"].drop_duplicates().tolist()
    )
    if legend_series_order:
        ordered_present = [serie for serie in legend_series_order if serie in set(series_order)]
        remaining = [serie for serie in series_order if serie not in set(ordered_present)]
        series_order = ordered_present + remaining
    color_encoding = alt.Color(
        "serie:N",
        title="Classe",
        scale=alt.Scale(domain=series_order, range=_colors[: len(series_order)]),
        sort=series_order,
        legend=_series_legend("Faixas / séries", len(series_order)),
    )
    color_map = _category_color_map(series_order, _colors)
    chart_df["label_color"] = chart_df["serie"].map(lambda value: _contrast_text_color(color_map.get(str(value), "#ff5a00")))
    if inside_label_color and not smart_label_placement:
        chart_df["label_color"] = inside_label_color
    if smart_label_placement:
        force_all_segment_labels = False
        allow_outside_labels = True
    chart = (
        alt.Chart(chart_df)
        .mark_bar(size=bar_size or _single_series_bar_size(chart_df["competencia"].nunique()))
        .encode(
            x=x_encoding,
            y=y_encoding,
            color=color_encoding,
            order=alt.Order("ordem:Q", sort="ascending") if "ordem" in chart_df.columns else alt.Order("serie:N"),
            tooltip=["competencia:N", "serie:N", alt.Tooltip("valor_fmt:N", title="Valor")],
        )
    )
    chart = _chart_with_optional_title(chart, height=height, title=title)
    layered: alt.Chart = chart
    labels_df = chart_df.copy()
    has_outside_labels = False
    if show_segment_labels and not labels_df.empty:
        if max_segment_labels_per_competencia is not None and "competencia" in labels_df.columns:
            labels_df["_abs_val"] = pd.to_numeric(labels_df[resolved_value_column], errors="coerce").abs()
            labels_df["_segment_rank"] = (
                labels_df.groupby("competencia", dropna=False)["_abs_val"]
                .rank(method="first", ascending=False)
            )
            labels_df = labels_df[labels_df["_segment_rank"] <= float(max_segment_labels_per_competencia)].copy()
        max_value = pd.to_numeric(labels_df[resolved_value_column], errors="coerce").abs().max()
        inner_threshold = inner_label_threshold if inner_label_threshold is not None else 2.1 if "%" in y_title else (
            max_value * 0.08 if pd.notna(max_value) else 0.0
        )
        outer_threshold = outer_label_threshold if outer_label_threshold is not None else 0.65 if "%" in y_title else (
            max_value * 0.03 if pd.notna(max_value) else 0.0
        )
        if smart_label_placement:
            if "%" in y_title:
                inner_threshold = max(float(inner_threshold), 4.0)
                outer_threshold = min(float(outer_threshold), 0.1)
            else:
                competency_totals = pd.to_numeric(labels_df[resolved_value_column], errors="coerce").groupby(
                    labels_df["competencia"], dropna=False
                ).sum()
                totals_map = competency_totals.to_dict()
                labels_df["competencia_total"] = labels_df["competencia"].map(totals_map)
                labels_df["segment_share"] = (
                    pd.to_numeric(labels_df[resolved_value_column], errors="coerce")
                    / pd.to_numeric(labels_df["competencia_total"], errors="coerce")
                ).fillna(0.0)
                # Valores muito pequenos em R$ ficam fora para preservar contraste/legibilidade.
                inner_threshold = max(float(inner_threshold), float(max_value or 0.0) * 0.12)
                outer_threshold = min(float(outer_threshold), float(max_value or 0.0) * 0.015 if pd.notna(max_value) else 0.0)
                labels_df["prefer_outside"] = labels_df["segment_share"] < 0.11
            if "%" in y_title:
                labels_df["prefer_outside"] = False
        else:
            labels_df["prefer_outside"] = False
        inner_labels_df = labels_df[
            (
                pd.to_numeric(labels_df[resolved_value_column], errors="coerce") >= inner_threshold
            )
            & (~labels_df["prefer_outside"])
        ].copy()
        outer_labels_df = labels_df[
            (
                pd.to_numeric(labels_df[resolved_value_column], errors="coerce") >= outer_threshold
            )
            & (
                (pd.to_numeric(labels_df[resolved_value_column], errors="coerce") < inner_threshold)
                | (labels_df["prefer_outside"])
            )
        ].copy()
        if force_all_segment_labels:
            inner_labels_df = labels_df.copy()
            outer_labels_df = labels_df.iloc[0:0].copy()
        if not allow_outside_labels:
            outer_labels_df = outer_labels_df.iloc[0:0].copy()
        outer_offsets = [0, -16, 16, -28, 28, -40, 40]
        if not outer_labels_df.empty:
            has_outside_labels = True
            sort_columns = ["competencia_dt", "competencia", "serie"]
            if "ordem" in outer_labels_df.columns:
                sort_columns.insert(2, "ordem")
            outer_labels_df = outer_labels_df.sort_values(
                sort_columns
            ).reset_index(drop=True)
            if "ordem" in outer_labels_df.columns:
                outer_labels_df["segment_rank"] = (
                    outer_labels_df.groupby("competencia", dropna=False)["ordem"].rank(method="dense").astype(int) - 1
                )
            else:
                outer_labels_df["segment_rank"] = outer_labels_df.groupby("competencia", dropna=False).cumcount()
            if smart_label_placement:
                # Labels pequenos: à direita da barra (xOffset > 0), no centro vertical
                # do próprio segmento (stack="center"). Ranks adicionais deslocam mais
                # à direita para evitar qualquer sobreposição.
                resolved_bar_size_px = bar_size or _single_series_bar_size(chart_df["competencia"].nunique())
                base_right_offset = int(resolved_bar_size_px / 2) + 12
                stagger_step = 34
                outer_labels_df["x_offset"] = outer_labels_df["segment_rank"].mul(stagger_step) + base_right_offset
                outer_labels_df["dy"] = outer_labels_df["segment_rank"].map(
                    lambda rank: -16 + ((int(rank) % 3) * 16)
                )
            else:
                outer_labels_df["outside_y"] = outer_labels_df.groupby("competencia", dropna=False)[resolved_value_column].cumsum()
                outside_step = 0.9 if "%" in y_title else (
                    outer_labels_df["outside_y"].abs().max() * 0.012 if pd.notna(outer_labels_df["outside_y"].abs().max()) else 1.0
                )
                outer_labels_df["outside_label_y"] = outer_labels_df["outside_y"] + 0.8 + outer_labels_df["segment_rank"].mul(outside_step)
                outer_labels_df["x_offset"] = outer_labels_df["segment_rank"].map(
                    lambda rank: outer_offsets[rank] if rank < len(outer_offsets) else outer_offsets[-1]
                )
        if not inner_labels_df.empty:
            segment_labels = (
                alt.Chart(inner_labels_df)
                .mark_text(fontSize=label_font_size, fontWeight=700, clip=False)
                .encode(
                    x=x_encoding,
                    y=alt.Y(f"{resolved_value_column}:Q", title=y_title, stack="center"),
                    detail="serie:N",
                    text=alt.Text("label_fmt:N"),
                    color=alt.Color("label_color:N", scale=None, legend=None),
                )
            )
            layered = layered + segment_labels
        if not outer_labels_df.empty:
            if smart_label_placement:
                if "dy" in outer_labels_df.columns and not outer_labels_df.empty:
                    for rank in sorted(outer_labels_df["segment_rank"].dropna().astype(int).unique().tolist()):
                        rank_df = outer_labels_df[outer_labels_df["segment_rank"] == rank]
                        rank_dy = int(rank_df["dy"].iloc[0])
                        rank_labels = (
                            alt.Chart(rank_df)
                            .mark_text(
                                fontSize=max(label_font_size - 1, 10),
                                fontWeight=700,
                                align="left",
                                color="#111111",
                                stroke="#ffffff",
                                strokeWidth=3.2,
                                dy=rank_dy,
                                clip=False,
                            )
                            .encode(
                                x=x_encoding,
                                y=alt.Y(f"{resolved_value_column}:Q", title=y_title, stack="center"),
                                xOffset=alt.XOffset("x_offset:Q"),
                                detail="serie:N",
                                text=alt.Text("label_fmt:N"),
                            )
                        )
                        layered = layered + rank_labels
                else:
                    outside_labels = (
                        alt.Chart(outer_labels_df)
                        .mark_text(
                            fontSize=max(label_font_size - 1, 10),
                            fontWeight=700,
                            align="left",
                            color="#111111",
                            stroke="#ffffff",
                            strokeWidth=3.2,
                            dy=-4,
                            clip=False,
                        )
                        .encode(
                            x=x_encoding,
                            y=alt.Y(f"{resolved_value_column}:Q", title=y_title, stack="center"),
                            xOffset=alt.XOffset("x_offset:Q"),
                            detail="serie:N",
                            text=alt.Text("label_fmt:N"),
                        )
                    )
                    layered = layered + outside_labels
            else:
                outer_labels_df["outside_y"] = outer_labels_df.groupby("competencia", dropna=False)[resolved_value_column].cumsum()
                outside_labels = (
                    alt.Chart(outer_labels_df)
                    .mark_text(
                        fontSize=max(label_font_size - 1, 10),
                        fontWeight=700,
                        dy=-2,
                        color="#111111",
                        clip=False,
                    )
                    .encode(
                        x=x_encoding,
                        y=alt.Y("outside_label_y:Q", title=y_title),
                        xOffset=alt.XOffset("x_offset:Q"),
                        detail="serie:N",
                        text=alt.Text("label_fmt:N"),
                    )
                )
                layered = layered + outside_labels
    if show_total_labels:
        totals_df = (
            chart_df.groupby("competencia", as_index=False, dropna=False)[resolved_value_column]
            .sum()
            .rename(columns={resolved_value_column: "valor_total"})
        )
        totals_df["total_fmt"] = totals_df["valor_total"].map(
            _format_brl_compact
            if y_title == "R$"
            else _format_percent_rounded_label
            if round_percent_labels and "%" in y_title
            else _format_percent
        )
        totals_df["label_y"] = totals_df["valor_total"] + (
            5.2
            if "%" in y_title
            else totals_df["valor_total"].abs().max() * 0.045 if pd.notna(totals_df["valor_total"].abs().max()) else 1.0
        )
        total_labels = (
            alt.Chart(totals_df)
            .mark_text(dy=-4, fontSize=max(14, label_font_size + 4), fontWeight=800, color="#111111", clip=False)
            .encode(
                x=alt.X("competencia:N", title="Competência", sort=x_sort),
                y=alt.Y("label_y:Q", title=y_title),
                text=alt.Text("total_fmt:N"),
            )
        )
        layered = layered + total_labels
    right_padding = 180 if has_outside_labels else 18
    return _style_altair_chart(layered.properties(padding={"left": 12, "right": right_padding, "top": 18, "bottom": 8}))


def _prepare_aging_history_chart_frame(chart_df: pd.DataFrame) -> pd.DataFrame:
    output = chart_df.copy()
    if "faixa" in output.columns and "serie" not in output.columns:
        output = output.rename(columns={"faixa": "serie"})
    if "percentual" not in output.columns:
        for alias in ("percentual_inadimplencia", "percentual_direitos_creditorios"):
            if alias in output.columns:
                output = output.rename(columns={alias: "percentual"})
                break
    return output


def _aging_history_callout_chart(
    chart_df: pd.DataFrame,
    *,
    title: str | None,
    height: int = 455,
    bar_size: int | None = None,
) -> alt.Chart:
    df = _altair_compatible_df(chart_df.copy())
    df = _sort_competencia_display_frame(df, extra_columns=["ordem", "serie"])
    if "competencia" in df.columns:
        df["competencia"] = df["competencia"].map(_format_competencia_display)
    if df.empty:
        empty_chart = (
            alt.Chart(pd.DataFrame(columns=["competencia", "percentual"]))
            .mark_bar()
            .encode(x="competencia:N", y=alt.Y("percentual:Q", title="% da inadimplência"))
        )
        return _style_altair_chart(_chart_with_optional_title(empty_chart, height=height, title=title))
    resolved_value_column = _resolve_stacked_chart_value_column(df, "percentual")
    x_sort = _competencia_axis_sort(df)
    label_slot = ""
    x_domain = (x_sort + [label_slot]) if x_sort else [label_slot]
    series_order = [serie for serie in AGING_SERIES_ORDER if serie in set(df["serie"].dropna().tolist())]
    remaining = [serie for serie in df["serie"].drop_duplicates().tolist() if serie not in set(series_order)]
    series_order = series_order + remaining
    color_map = _category_color_map(series_order, AGING_CHART_COLORS)
    df["valor_fmt"] = df[resolved_value_column].map(_format_percent)
    df["tooltip_pct_inad"] = df.get("percentual_inadimplencia", df[resolved_value_column]).map(_format_percent)
    if "percentual_direitos_creditorios" in df.columns:
        df["tooltip_pct_dcs"] = df["percentual_direitos_creditorios"].map(_format_percent)
    else:
        df["tooltip_pct_dcs"] = "N/D"
    latest_competencia = x_sort[-1]
    latest_df = df[df["competencia"] == latest_competencia].copy()
    latest_df["valor_num"] = pd.to_numeric(latest_df[resolved_value_column], errors="coerce").fillna(0.0)
    if "ordem" in latest_df.columns:
        latest_df = latest_df.sort_values("ordem").reset_index(drop=True)
    latest_df["segment_top"] = latest_df["valor_num"].cumsum()
    latest_df["segment_center"] = latest_df["segment_top"] - (latest_df["valor_num"] / 2.0)
    ordered_labels = latest_df.sort_values("segment_center").reset_index(drop=True).copy()
    min_gap = 4.2
    adjusted_centers: list[float] = []
    for _, row in ordered_labels.iterrows():
        current = float(row["segment_center"])
        if not adjusted_centers:
            adjusted_centers.append(current)
            continue
        adjusted_centers.append(max(current, adjusted_centers[-1] + min_gap))
    ordered_labels["label_y"] = adjusted_centers
    latest_df = latest_df.merge(
        ordered_labels[["serie", "label_y"]],
        on="serie",
        how="left",
    )
    latest_df["label_text"] = latest_df[resolved_value_column].map(_format_percent_rounded_label)
    latest_df["label_slot"] = label_slot
    latest_df["label_color"] = latest_df["serie"].map(lambda value: color_map.get(str(value), "#111111"))

    connector_rows: list[dict[str, object]] = []
    for _, row in latest_df.iterrows():
        connector_rows.append(
            {
                "serie": row["serie"],
                "competencia_plot": latest_competencia,
                "valor_plot": row["segment_center"],
                "point_order": 0,
            }
        )
        connector_rows.append(
            {
                "serie": row["serie"],
                "competencia_plot": label_slot,
                "valor_plot": row["label_y"],
                "point_order": 1,
            }
        )
    connectors_df = pd.DataFrame(connector_rows)
    _aging_bar_max = float(
        df.groupby("competencia")[resolved_value_column]
        .apply(lambda s: pd.to_numeric(s, errors="coerce").sum())
        .max()
    ) if not df.empty else 0.0
    _aging_label_top = float(latest_df["label_y"].max()) if not latest_df.empty else 0.0
    _aging_y_max = max(105.0, _aging_bar_max * 1.10, _aging_label_top + 4.0)
    x_encoding = alt.X(
        "competencia:N",
        title="Competência",
        sort=x_domain,
        scale=alt.Scale(domain=x_domain),
        axis=alt.Axis(labelExpr="datum.label == '' ? '' : datum.label"),
    )
    color_encoding = alt.Color(
        "serie:N",
        title="Faixas / séries",
        scale=alt.Scale(domain=series_order, range=AGING_CHART_COLORS[: len(series_order)]),
        sort=series_order,
        legend=_series_legend("Faixas / séries", len(series_order)),
    )
    bars = (
        alt.Chart(df)
        .mark_bar(size=bar_size or _executive_monthly_bar_size(df["competencia"].nunique()))
        .encode(
            x=x_encoding,
            y=alt.Y(
                f"{resolved_value_column}:Q",
                title="% da inadimplência",
                stack=True,
                scale=alt.Scale(domain=[0.0, _aging_y_max], nice=False),
            ),
            color=color_encoding,
            order=alt.Order("ordem:Q", sort="ascending") if "ordem" in df.columns else alt.Order("serie:N"),
            tooltip=[
                alt.Tooltip("competencia:N", title="Competência"),
                alt.Tooltip("serie:N", title="Faixa"),
                alt.Tooltip("valor_fmt:N", title="% da inadimplência"),
                alt.Tooltip("tooltip_pct_dcs:N", title="% dos DCs"),
            ],
        )
    )
    connectors = (
        alt.Chart(connectors_df)
        .mark_line(strokeWidth=1.35, strokeDash=[4, 3], clip=False)
        .encode(
            x=alt.X(
                "competencia_plot:N",
                sort=x_domain,
                scale=alt.Scale(domain=x_domain),
                axis=alt.Axis(labelExpr="datum.label == '' ? '' : datum.label"),
            ),
            y=alt.Y("valor_plot:Q", title="% da inadimplência"),
            detail="serie:N",
            order=alt.Order("point_order:Q", sort="ascending"),
            color=alt.Color(
                "serie:N",
                scale=alt.Scale(domain=series_order, range=AGING_CHART_COLORS[: len(series_order)]),
                sort=series_order,
                legend=None,
            ),
        )
    )
    label_points = (
        alt.Chart(latest_df)
        .mark_point(filled=True, size=58, strokeWidth=0, clip=False)
        .encode(
            x=alt.X(
                "label_slot:N",
                sort=x_domain,
                scale=alt.Scale(domain=x_domain),
                axis=alt.Axis(labelExpr="datum.label == '' ? '' : datum.label"),
            ),
            y=alt.Y("label_y:Q", title="% da inadimplência"),
            color=alt.Color("serie:N", scale=alt.Scale(domain=series_order, range=AGING_CHART_COLORS[: len(series_order)]), sort=series_order, legend=None),
        )
    )
    labels = (
        alt.Chart(latest_df)
        .mark_text(align="left", dx=12, fontSize=14, fontWeight=700, clip=False)
        .encode(
            x=alt.X(
                "label_slot:N",
                sort=x_domain,
                scale=alt.Scale(domain=x_domain),
                axis=alt.Axis(labelExpr="datum.label == '' ? '' : datum.label"),
            ),
            y=alt.Y("label_y:Q", title="% da inadimplência"),
            text=alt.Text("label_text:N"),
            color=alt.Color("serie:N", scale=alt.Scale(domain=series_order, range=AGING_CHART_COLORS[: len(series_order)]), sort=series_order, legend=None),
        )
    )
    chart = _chart_with_optional_title(bars + connectors + label_points + labels, height=height, title=title)
    return _style_altair_chart(chart.properties(padding={"left": 12, "right": 248, "top": 18, "bottom": 8}))


def _resolve_stacked_chart_value_column(chart_df: pd.DataFrame, requested_column: str) -> str:
    if requested_column in chart_df.columns:
        return requested_column
    alias_map = {
        "percentual": ("percentual_inadimplencia", "percentual_direitos_creditorios"),
    }
    for alias in alias_map.get(requested_column, ()):
        if alias in chart_df.columns:
            return alias
    raise ValueError(
        f"Coluna '{requested_column}' não encontrada no gráfico empilhado. "
        f"Colunas disponíveis: {', '.join(chart_df.columns.astype(str).tolist())}"
    )


def _grouped_bar_chart(
    chart_df: pd.DataFrame,
    *,
    title: str | None,
    y_title: str,
    value_field: str | None = None,
    height: int = 340,
    bar_size: int | None = None,
    label_font_size: int = 11,
    color_range: list[str] | None = None,
) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df)
    chart_df = _sort_competencia_display_frame(chart_df, extra_columns=["serie"])
    if "competencia" in chart_df.columns:
        chart_df["competencia"] = chart_df["competencia"].map(_format_competencia_display)
    resolved_value_field = value_field or ("valor_total" if "valor_total" in chart_df.columns else "valor")
    chart_df = chart_df.copy()
    x_sort = _competencia_axis_sort(chart_df)
    chart_df["valor_fmt"] = chart_df[resolved_value_field].map(lambda v: _format_brl_compact(v) if y_title == "R$" else _format_percent(v) if "%" in y_title else _format_decimal(v))
    chart_df["label_fmt"] = chart_df[resolved_value_field].map(lambda v: _format_value_label(v, y_title))
    x_encoding = alt.X("competencia:N", title="Competência", sort=x_sort)
    y_axis = alt.Axis(labelExpr=_brl_axis_label_expr()) if y_title == "R$" else alt.Axis()
    y_encoding = alt.Y(
        f"{resolved_value_field}:Q",
        title=y_title,
        axis=y_axis,
        scale=_quant_scale_with_headroom(chart_df[resolved_value_field], percent_like="%" in y_title, max_cap=140.0 if "%" in y_title else None),
    )
    series_order = chart_df["serie"].drop_duplicates().tolist()
    color_encoding = alt.Color(
        "serie:N",
        title="Série",
        scale=alt.Scale(domain=series_order, range=(color_range or FIDC_CHART_COLORS)[: len(series_order)]),
        sort=series_order,
    )
    resolved_bar_size = bar_size or _grouped_series_bar_size(
        chart_df["competencia"].nunique(),
        chart_df["serie"].nunique(),
    )
    chart = (
        alt.Chart(chart_df)
        .mark_bar(size=resolved_bar_size)
        .encode(
            x=x_encoding,
            y=y_encoding,
            color=color_encoding,
            xOffset=alt.XOffset("serie:N", sort=series_order),
            tooltip=["competencia:N", "serie:N", alt.Tooltip("valor_fmt:N", title="Valor")],
        )
    )
    chart = _chart_with_optional_title(chart, height=height, title=title)
    labels = _bar_label_layer(
        chart_df,
        x_encoding=alt.X("competencia:N", title="Competência", sort=x_sort),
        y_encoding=y_encoding,
        value_field=resolved_value_field,
        text_field="label_fmt",
        x_offset_field="serie",
        font_size=label_font_size,
        font_weight=700,
        dy=-8,
    )
    return _style_altair_chart(chart if labels is None else (chart + labels))


def _grouped_bar_with_rhs_line_chart(
    bar_df: pd.DataFrame,
    line_df: pd.DataFrame,
    *,
    title: str | None,
    bar_y_title: str,
    line_y_title: str,
    bar_value_field: str | None = None,
    line_value_field: str = "valor",
    height: int = 360,
    reference_value: float | None = None,
    reference_label: str | None = None,
    bar_size: int | None = None,
    show_line_end_label: bool = True,
    show_bar_labels: bool = False,
    show_all_line_labels: bool = False,
    bar_label_formatter: Callable[[object], str] | None = None,
    line_label_formatter: Callable[[object], str] | None = None,
) -> alt.Chart:
    bar_chart_df = _altair_compatible_df(bar_df.copy())
    line_chart_df = _altair_compatible_df(line_df.copy())
    bar_chart_df = _sort_competencia_display_frame(bar_chart_df, extra_columns=["serie"])
    line_chart_df = _sort_competencia_display_frame(line_chart_df, extra_columns=["serie"])
    if "competencia" in bar_chart_df.columns:
        bar_chart_df["competencia"] = bar_chart_df["competencia"].map(_format_competencia_display)
    if "competencia" in line_chart_df.columns:
        line_chart_df["competencia"] = line_chart_df["competencia"].map(_format_competencia_display)
    resolved_bar_value_field = bar_value_field or ("valor_total" if "valor_total" in bar_chart_df.columns else "valor")
    x_sort = _competencia_axis_sort(pd.concat([bar_chart_df, line_chart_df], ignore_index=True, sort=False))

    bar_chart_df["valor_fmt"] = bar_chart_df[resolved_bar_value_field].map(
        lambda value: _format_brl_compact(value)
        if bar_y_title == "R$"
        else _format_percent(value)
        if "%" in bar_y_title
        else _format_decimal(value)
    )
    bar_chart_df["label_fmt"] = bar_chart_df[resolved_bar_value_field].map(
        lambda value: bar_label_formatter(value) if bar_label_formatter else _format_value_label(value, bar_y_title)
    )
    line_chart_df["valor_fmt"] = line_chart_df[line_value_field].map(
        lambda value: _format_brl_compact(value)
        if line_y_title == "R$"
        else _format_percent(value)
        if "%" in line_y_title
        else _format_decimal(value)
    )
    line_chart_df["label_fmt"] = line_chart_df[line_value_field].map(
        lambda value: line_label_formatter(value) if line_label_formatter else _format_value_label(value, line_y_title)
    )

    x_encoding = alt.X("competencia:N", title="Competência", sort=x_sort)
    bar_series_order = bar_chart_df["serie"].drop_duplicates().tolist()
    bar_y_axis = (
        alt.Axis(labelExpr=_brl_axis_label_expr(), labelPadding=8, titlePadding=12, offset=2)
        if bar_y_title == "R$"
        else alt.Axis(labelPadding=8, titlePadding=12, tickCount=4, grid=True, offset=2)
    )
    bar_y_encoding = alt.Y(
        f"{resolved_bar_value_field}:Q",
        title=bar_y_title,
        axis=bar_y_axis,
        scale=_quant_scale_with_headroom(
            bar_chart_df[resolved_bar_value_field],
            percent_like="%" in bar_y_title,
            max_cap=140.0 if "%" in bar_y_title else None,
        ),
    )
    line_scale_input = pd.to_numeric(line_chart_df[line_value_field], errors="coerce")
    if reference_value is not None:
        line_scale_input = pd.concat([line_scale_input, pd.Series([reference_value])], ignore_index=True)
    line_y_encoding = alt.Y(
        f"{line_value_field}:Q",
        title=line_y_title,
        axis=alt.Axis(
            orient="right",
            grid=False,
            labelColor=COVERAGE_LINE_COLOR,
            titleColor=COVERAGE_LINE_COLOR,
            labelPadding=12,
            titlePadding=18,
            offset=12,
            values=_nice_axis_ticks(line_scale_input),
        ),
        scale=_quant_scale_with_headroom(
            line_scale_input,
            percent_like="%" in line_y_title,
        ),
    )

    bars = (
        alt.Chart(bar_chart_df)
        .mark_bar(size=bar_size or _grouped_series_bar_size(bar_chart_df["competencia"].nunique(), bar_chart_df["serie"].nunique()))
        .encode(
            x=x_encoding,
            y=bar_y_encoding,
            color=alt.Color(
                "serie:N",
                title="Eixo esquerdo",
                scale=alt.Scale(domain=bar_series_order, range=FIDC_CHART_COLORS[: len(bar_series_order)]),
                sort=bar_series_order,
                legend=_series_legend("Eixo esquerdo", len(bar_series_order)),
            ),
            xOffset=alt.XOffset("serie:N", sort=bar_series_order),
            tooltip=["competencia:N", "serie:N", alt.Tooltip("valor_fmt:N", title="Valor")],
        )
    )
    bar_labels = None
    if show_bar_labels:
        bar_labels = _bar_label_layer(
            bar_chart_df,
            x_encoding=x_encoding,
            y_encoding=bar_y_encoding,
            value_field=resolved_bar_value_field,
            text_field="label_fmt",
            x_offset_field="serie",
            font_size=11,
            font_weight=700,
            dy=-8,
        )
    bar_layer = bars if bar_labels is None else (bars + bar_labels)

    line_series_order = line_chart_df["serie"].drop_duplicates().tolist()
    coverage_line = (
        alt.Chart(line_chart_df)
        .mark_line(
            point=alt.OverlayMarkDef(
                filled=True,
                size=52,
                fill=COVERAGE_LINE_COLOR,
                stroke=COVERAGE_LINE_COLOR,
                strokeWidth=1.0,
            ),
            strokeWidth=2.9,
        )
        .encode(
            x=x_encoding,
            y=line_y_encoding,
            color=alt.Color(
                "serie:N",
                title="Eixo direito",
                scale=alt.Scale(
                    domain=line_series_order,
                    range=[COVERAGE_LINE_COLOR] * max(1, line_chart_df["serie"].nunique()),
                ),
                legend=_series_legend("Eixo direito", line_chart_df["serie"].nunique()),
            ),
            tooltip=["competencia:N", alt.Tooltip("valor_fmt:N", title="Cobertura"), alt.Tooltip("serie:N", title="Série")],
        )
    )
    coverage_layers: alt.Chart = coverage_line
    if reference_value is not None:
        reference_df = pd.DataFrame({"valor": [reference_value]})
        reference_rule = (
            alt.Chart(reference_df)
            .mark_rule(strokeDash=[6, 4], color="#6b7280", strokeWidth=1.4)
            .encode(
                y=alt.Y(
                    "valor:Q",
                    title=line_y_title,
                    axis=None,
                    scale=_quant_scale_with_headroom(
                        line_scale_input,
                        percent_like="%" in line_y_title,
                    ),
                ),
                tooltip=[alt.Tooltip("valor:Q", title=reference_label or "Referência", format=".0f")],
            )
        )
        coverage_layers = reference_rule + coverage_line

    if show_all_line_labels and not line_chart_df.empty:
        label_df = line_chart_df.copy()
        point_labels = (
            alt.Chart(label_df)
            .mark_text(
                fontSize=10,
                fontWeight=700,
                color=COVERAGE_LINE_COLOR,
                dy=-14,
                clip=False,
            )
            .encode(
                x=x_encoding,
                y=line_y_encoding,
                text=alt.Text("label_fmt:N"),
            )
        )
        coverage_layers = coverage_layers + point_labels

    layered = alt.layer(bar_layer, coverage_layers).resolve_scale(y="independent")
    if show_line_end_label:
        coverage_labels_df = _build_line_series_end_labels_df(
            line_chart_df[line_chart_df["serie"] != (reference_label or "")].copy()
            if "serie" in line_chart_df.columns and reference_label
            else line_chart_df,
            y_title=line_y_title,
            min_gap_override=18.0 if "%" in line_y_title else None,
        )
        if not coverage_labels_df.empty:
            coverage_labels_df = coverage_labels_df.copy()
            coverage_labels_df["serie"] = coverage_labels_df["serie"].fillna("Cobertura")
            end_labels = _line_series_end_label_layer(
                coverage_labels_df,
                x_sort=x_sort,
                y_title=line_y_title,
                color_range=[COVERAGE_LINE_COLOR],
                series_order=coverage_labels_df["serie"].drop_duplicates().tolist(),
            )
            if end_labels is not None:
                layered = layered + end_labels
    layered = _chart_with_optional_title(layered, height=height, title=title)
    return _style_altair_chart(layered.properties(padding={"left": 24, "right": 196, "top": 18, "bottom": 8}))


def _stacked_area_chart(
    chart_df: pd.DataFrame,
    *,
    title: str,
    value_column: str,
    y_title: str,
) -> alt.Chart:
    label_column = _class_display_column(chart_df)
    base_df = chart_df[["competencia", "competencia_dt", label_column, value_column]].copy()
    base_df = base_df.rename(columns={label_column: "label"})
    base_df = _sort_competencia_display_frame(base_df, extra_columns=["label"])
    base_df["competencia"] = base_df["competencia"].map(_format_competencia_display)
    base_df[value_column] = pd.to_numeric(base_df[value_column], errors="coerce")
    base_df = base_df.dropna(subset=[value_column])
    base_df = _altair_compatible_df(base_df)
    base_df = base_df.copy()
    base_df["valor_fmt"] = base_df[value_column].map(lambda v: _format_brl_compact(v) if y_title == "R$" else _format_percent(v) if "%" in y_title else _format_decimal(v))
    x_sort = _competencia_axis_sort(base_df)
    x_encoding = alt.X("competencia:N", title="Competência", sort=x_sort)
    y_axis = alt.Axis(labelExpr=_brl_axis_label_expr()) if y_title == "R$" else alt.Axis()
    y_encoding = alt.Y(f"{value_column}:Q", stack=True, title=y_title, axis=y_axis)
    color_encoding = alt.Color("label:N", title="Classe", scale=alt.Scale(range=FIDC_CHART_COLORS))
    chart = (
        alt.Chart(base_df)
        .mark_area(opacity=0.75)
        .encode(
            x=x_encoding,
            y=y_encoding,
            color=color_encoding,
            tooltip=["competencia:N", "label:N", alt.Tooltip("valor_fmt:N", title="Valor")],
        )
        .properties(title=title, height=320)
    )
    if not _chart_labels_enabled() or base_df["label"].nunique(dropna=True) > 3:
        return _style_altair_chart(chart)
    labels_df = base_df.sort_values(["label", "competencia_dt"]).groupby("label", as_index=False, dropna=False).tail(1)
    labels = (
        alt.Chart(labels_df)
        .mark_text(align="left", dx=6, dy=-6, fontSize=11, color="#111111")
        .encode(
            x=x_encoding,
            y=alt.Y(f"{value_column}:Q", title=y_title),
            text=alt.Text(f"{value_column}:Q", format=_label_format(y_title)),
            color=alt.Color("label:N", legend=None, scale=alt.Scale(range=FIDC_CHART_COLORS)),
        )
    )
    return _style_altair_chart(chart + labels)


def _duration_line_chart(duration_history_df: pd.DataFrame) -> alt.Chart:
    """Altair line chart for the estimated receivables duration (days) time series.

    Tooltip explains the calculation formula and bucket-proxy assumptions.
    """
    df = _altair_compatible_df(duration_history_df.copy())
    df = df[df["data_quality"] == "ok"].copy()
    df = _sort_competencia_display_frame(df)
    if df.empty or "competencia" not in df.columns:
        return alt.Chart(pd.DataFrame({"competencia": [], "duration_days": []})).mark_line()
    df["competencia"] = df["competencia"].map(_format_competencia_display)
    df["serie"] = "Duration"
    df["duration_fmt"] = df["duration_days"].map(lambda v: f"{v:.0f} dias" if not pd.isna(v) else "N/D")
    df["duration_label"] = df["duration_days"].map(lambda v: f"{float(v):.0f}" if not pd.isna(v) else "N/D")
    df["end_label_text"] = df["duration_days"].map(lambda v: f"{float(v):.0f}" if not pd.isna(v) else "N/D")
    # Tooltip rows — formula + proxy assumptions
    tooltip_nota = (
        "Duration = Σ(saldo_bucket × prazo_proxy) / Σ(saldo_bucket). "
        "Proxies: Vencidos=0d; ≤30d=30d; intervalos=ponto médio; "
        ">1080d só entra se a faixa aberta não dominar a carteira."
    )
    x_sort = _competencia_axis_sort(df)

    # Compute a smart Y-axis domain so tight time-series (e.g. 602–612 days)
    # are rendered with enough vertical resolution to make deltas visible,
    # while wide-range series (e.g. 0–800 days) still start at zero.
    _ZOOM_THRESHOLD = 0.25  # zoom in when range < 25 % of the max value
    _vals = df["duration_days"].dropna()
    if len(_vals) >= 1:
        _data_min = float(_vals.min())
        _data_max = float(_vals.max())
        _data_range = (_data_max - _data_min) if len(_vals) >= 2 else _data_max * 0.1
        if _data_max > 0 and _data_range < _data_max * _ZOOM_THRESHOLD and _data_min > 0:
            _pad = max(_data_range, _data_max * 0.05)
            y_scale = alt.Scale(domain=[max(0.0, _data_min - _pad), _data_max + _pad * 0.5], zero=False)
        else:
            y_scale = alt.Scale(zero=True)
    else:
        y_scale = alt.Scale(zero=True)

    line_chart = (
        alt.Chart(df)
        .mark_line(color="#ff5a00", strokeWidth=2.4)
        .encode(
            x=alt.X("competencia:N", title="Competência", sort=x_sort),
            y=alt.Y(
                "duration_days:Q",
                title="Prazo médio proxy (dias)",
                scale=y_scale,
                axis=alt.Axis(labelColor="#5f6b7a", titleColor="#5f6b7a"),
            ),
            tooltip=[
                alt.Tooltip("competencia:N", title="Competência"),
                alt.Tooltip("duration_days:Q", title="Prazo médio proxy (dias)", format=".0f"),
                alt.Tooltip("duration_fmt:N", title="Formatado"),
            ],
        )
        .properties(height=240)
    )
    points = (
        alt.Chart(df)
        .mark_point(
            filled=True,
            size=130,
            color="#ff5a00",
            stroke="#ff5a00",
            strokeWidth=1.2,
        )
        .encode(
            x=alt.X("competencia:N", sort=x_sort),
            y=alt.Y("duration_days:Q", scale=y_scale),
        )
    )
    all_point_labels = (
        alt.Chart(df)
        .mark_text(
            dy=-12,
            fontSize=11,
            fontWeight=700,
            color="#ff5a00",
            clip=False,
        )
        .encode(
            x=alt.X("competencia:N", sort=x_sort),
            y=alt.Y("duration_days:Q", title="Prazo médio proxy (dias)", scale=y_scale),
            text=alt.Text("duration_label:N"),
        )
    )
    _ = tooltip_nota  # documented; surfaced in UI caption below the chart
    layered = line_chart + points + all_point_labels
    return _style_altair_chart(layered.properties(padding={"left": 8, "right": 56, "top": 8, "bottom": 8}))


def _inadimplentes_aux_sum_line_chart(chart_df: pd.DataFrame) -> alt.Chart:
    df = _altair_compatible_df(chart_df.copy())
    df = _sort_competencia_display_frame(df)
    if df.empty or "competencia" not in df.columns:
        return alt.Chart(pd.DataFrame({"competencia": [], "valor": []})).mark_line()
    df["competencia"] = df["competencia"].map(_format_competencia_display)
    df["valor_label"] = df["valor"].map(lambda value: _format_percent(value))
    x_sort = _competencia_axis_sort(df)
    line_chart = (
        alt.Chart(df)
        .mark_line(color="#ff5a00", strokeWidth=2.4)
        .encode(
            x=alt.X("competencia:N", title="Competência", sort=x_sort),
            y=alt.Y(
                "valor:Q",
                title="Auxílio de validação de inadimplentes / DCs",
                axis=alt.Axis(labelColor="#5f6b7a", titleColor="#5f6b7a"),
                scale=_quant_scale_with_headroom(df["valor"], percent_like=True),
            ),
            tooltip=[
                alt.Tooltip("competencia:N", title="Competência"),
                alt.Tooltip("valor_label:N", title="Somatório"),
            ],
        )
        .properties(height=240)
    )
    points = (
        alt.Chart(df)
        .mark_point(
            filled=True,
            size=130,
            color="#ff5a00",
            stroke="#ff5a00",
            strokeWidth=1.2,
        )
        .encode(
            x=alt.X("competencia:N", sort=x_sort),
            y=alt.Y("valor:Q"),
        )
    )
    end_df = df.sort_values("competencia_dt").tail(1).copy()
    end_df["label_y"] = pd.to_numeric(end_df["valor"], errors="coerce")
    labels = (
        alt.Chart(end_df)
        .mark_text(
            dx=14,
            dy=-10,
            align="left",
            fontSize=12,
            fontWeight=700,
            color="#ff5a00",
            clip=False,
        )
        .encode(
            x=alt.X("competencia:N", sort=x_sort),
            y=alt.Y("label_y:Q"),
            text=alt.Text("valor_label:N"),
        )
    )
    layered = line_chart + points + labels
    return _style_altair_chart(layered.properties(padding={"left": 8, "right": 84, "top": 8, "bottom": 8}))


def _style_altair_chart(chart: alt.Chart) -> alt.Chart:
    return (
        chart.configure_axis(
            labelColor="#5f6b7a",
            titleColor="#5f6b7a",
            gridColor="#eef2f6",
            domainColor="#e9ecef",
        )
        .configure_title(
            color="#223247",
            font="IBM Plex Sans",
            fontSize=14,
            fontWeight=500,
            anchor="start",
        )
        .configure(
            locale=alt.Locale(
                number=alt.NumberLocale(
                    decimal=",",
                    thousands=".",
                    grouping=[3],
                    currency=["R$ ", ""],
                    percent="%",
                    nan="N/D",
                )
            )
        )
        .configure_view(stroke=None)
        .configure_legend(labelColor="#5f6b7a", titleColor="#5f6b7a", orient="bottom")
    )


def _default_ratio_chart_frame(default_history_df: pd.DataFrame) -> pd.DataFrame:
    if default_history_df.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "serie", "valor"])
    chart_df = default_history_df[
        ["competencia", "competencia_dt", "inadimplencia_pct", "provisao_pct_direitos"]
    ].copy()
    chart_df = chart_df.melt(
        id_vars=["competencia", "competencia_dt"],
        value_vars=["inadimplencia_pct", "provisao_pct_direitos"],
        var_name="serie_key",
        value_name="valor",
    )
    chart_df["serie"] = chart_df["serie_key"].map(
        {
            "inadimplencia_pct": "Inadimplência",
            "provisao_pct_direitos": "Provisão",
        }
    )
    chart_df["valor"] = pd.to_numeric(chart_df["valor"], errors="coerce")
    return chart_df.dropna(subset=["valor"])


def _quota_pl_chart_frame(quota_pl_history_df: pd.DataFrame) -> pd.DataFrame:
    if quota_pl_history_df.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "serie", "valor"])
    label_column = _quota_macro_label_column(quota_pl_history_df)
    chart_df = quota_pl_history_df[["competencia", "competencia_dt", label_column, "pl"]].copy()
    chart_df = chart_df.rename(columns={label_column: "serie", "pl": "valor"})
    chart_df["valor"] = pd.to_numeric(chart_df["valor"], errors="coerce")
    chart_df = (
        chart_df.groupby(["competencia", "competencia_dt", "serie"], as_index=False, dropna=False)["valor"]
        .sum()
    )
    chart_df["label_fmt"] = chart_df["valor"].map(_format_compact_money_label)
    return chart_df.dropna(subset=["valor"])


def _quota_pl_share_chart_frame(quota_pl_history_df: pd.DataFrame) -> pd.DataFrame:
    if quota_pl_history_df.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "serie", "percentual"])
    base_df = _quota_pl_chart_frame(quota_pl_history_df)
    if base_df.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "serie", "percentual"])
    totals = base_df.groupby(["competencia", "competencia_dt"], dropna=False)["valor"].transform("sum")
    base_df["percentual"] = (base_df["valor"] / totals).where(totals > 0).mul(100.0)
    return base_df.dropna(subset=["percentual"])[["competencia", "competencia_dt", "serie", "percentual"]]


def _default_cobertura_chart_frame(default_history_df: pd.DataFrame) -> pd.DataFrame:
    """Returns history of cobertura_pct (provisão / vencidos totais * 100)."""
    if default_history_df.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "serie", "valor"])
    df = default_history_df[["competencia", "competencia_dt", "cobertura_pct"]].copy()
    df["valor"] = pd.to_numeric(df["cobertura_pct"], errors="coerce")
    df["serie"] = "Cobertura"
    df = df[["competencia", "competencia_dt", "serie", "valor"]].dropna(subset=["valor"])
    if not df.empty:
        df = df.sort_values("competencia_dt").drop_duplicates(subset=["competencia", "serie"], keep="last")
    return df


def _default_inadimplentes_aux_sum_chart_frame(default_history_df: pd.DataFrame) -> pd.DataFrame:
    if default_history_df.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "valor"])
    required = ["competencia", "competencia_dt", "somatorio_inadimplentes_aux_validacao_pct_dcs"]
    missing = [column for column in required if column not in default_history_df.columns]
    if missing:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "valor"])
    chart_df = default_history_df[required].copy()
    chart_df = chart_df.rename(columns={"somatorio_inadimplentes_aux_validacao_pct_dcs": "valor"})
    chart_df["valor"] = pd.to_numeric(chart_df["valor"], errors="coerce")
    return chart_df.dropna(subset=["valor"])


def _default_denominator_series(default_history_df: pd.DataFrame) -> pd.Series:
    if default_history_df.empty:
        return pd.Series(dtype="float64")
    canonical_total = (
        pd.to_numeric(default_history_df["direitos_creditorios"], errors="coerce")
        if "direitos_creditorios" in default_history_df.columns
        else pd.Series(index=default_history_df.index, dtype="float64")
    )
    total_vencimento = (
        pd.to_numeric(default_history_df["direitos_creditorios_vencimento_total"], errors="coerce")
        if "direitos_creditorios_vencimento_total" in default_history_df.columns
        else pd.Series(index=default_history_df.index, dtype="float64")
    )
    return canonical_total.where(canonical_total > 0, total_vencimento)


def _has_meaningful_benchmark(performance_df: pd.DataFrame) -> bool:
    if performance_df.empty or "desempenho_esperado_pct" not in performance_df.columns:
        return False
    expected = pd.to_numeric(performance_df["desempenho_esperado_pct"], errors="coerce").dropna()
    if expected.empty:
        return False
    return bool((expected.abs() > 0.000001).any())


def _altair_compatible_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    output = df.copy()
    for column in list(output.columns):
        column_data = output.loc[:, column]
        if isinstance(column_data, pd.DataFrame):
            continue
        dtype_text = str(column_data.dtype)
        dtype_repr = repr(column_data.dtype)
        if dtype_text.startswith("string") or dtype_text == "str" or "StringDtype" in dtype_repr:
            output[column] = pd.Series(
                column_data.astype(object).tolist(),
                index=output.index,
                dtype="object",
            )
    return output


def _format_cnpj(value: str) -> str:
    return format_cnpj(value)


def _is_missing_value(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _format_decimal(value: object, decimals: int = 2) -> str:
    if _is_missing_value(value):
        return "N/D"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/D"
    if numeric == 0:
        numeric = 0.0
    formatted = f"{numeric:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _format_percent(value: object) -> str:
    if _is_missing_value(value):
        return "N/D"
    return f"{_format_decimal(value, decimals=2)}%"


def _format_percent_label(value: object) -> str:
    if _is_missing_value(value):
        return "N/D"
    return f"{_format_decimal(value, decimals=1)}%"


def _format_percent_rounded_label(value: object) -> str:
    if _is_missing_value(value):
        return "N/D"
    return f"{int(round(float(value)))}%"


def _format_brl(value: object) -> str:
    if _is_missing_value(value):
        return "N/D"
    return f"R$ {_format_decimal(value, decimals=2)}"


def _format_brl_compact(value: object) -> str:
    if _is_missing_value(value):
        return "N/D"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/D"
    magnitude = abs(numeric)
    if magnitude >= 1_000_000_000_000:
        return f"R$ {_format_decimal(numeric / 1_000_000_000_000, decimals=2)} tri"
    if magnitude >= 1_000_000_000:
        return f"R$ {_format_decimal(numeric / 1_000_000_000, decimals=2)} bi"
    if magnitude >= 1_000_000:
        return f"R$ {_format_decimal(numeric / 1_000_000, decimals=1)} mm"
    return f"R$ {_format_decimal(numeric, decimals=2)}"


def _format_compact_money_label(value: object) -> str:
    if _is_missing_value(value):
        return "N/D"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/D"
    magnitude = abs(numeric)
    if magnitude >= 1_000_000_000_000:
        return f"{int(round(numeric / 1_000_000_000_000))} tri"
    if magnitude >= 1_000_000_000:
        return f"{int(round(numeric / 1_000_000_000))} bi"
    if magnitude >= 1_000_000:
        return f"{int(round(numeric / 1_000_000))} mm"
    return f"{int(round(numeric))}"


def _brl_axis_label_expr() -> str:
    """Vega-Lite labelExpr for abbreviated R$ axis ticks (mm / bi / tri)."""
    return (
        "datum.value >= 1e12 ? format(datum.value / 1e12, '.1f') + ' tri' : "
        "datum.value >= 1e9  ? format(datum.value / 1e9,  '.1f') + ' bi'  : "
        "datum.value >= 1e6  ? format(datum.value / 1e6,  '.1f') + ' mm'  : "
        "datum.value === 0   ? '0' : format(datum.value, ',.0f')"
    )


def _format_value_label(value: object, unit: str) -> str:
    if unit == "R$":
        return _format_brl_compact(value)
    if "%" in unit:
        return _format_percent_label(value)
    return _format_decimal(value, decimals=1)


def _format_competencia_display(competencia: object) -> str:
    """Converts '01/2026' → 'jan-26' for chart axis labels."""
    text = str(competencia or "").strip()
    parts = text.split("/")
    if len(parts) != 2:
        return text
    month, year = parts
    month_abbr = _PT_MONTH_ABBR.get(month, month)
    year_short = year[-2:] if len(year) == 4 else year
    return f"{month_abbr}-{year_short}"


def _render_result(result: InformeMensalResult, context: dict[str, Any], *, slot_key: str = "slot0") -> None:
    contract_missing = _validate_result_contract(result)
    docs_error = _count_docs_by_status(result.docs_df, "erro")

    _render_dashboard(
        result,
        context,
        contract_missing=contract_missing,
        docs_error=docs_error,
        slot_key=slot_key,
    )
