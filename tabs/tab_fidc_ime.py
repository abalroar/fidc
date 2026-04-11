from __future__ import annotations

import altair as alt
from datetime import date, datetime, timezone
from html import escape
import json
from pathlib import Path
import re
import time
import traceback
from typing import Any
import uuid

import pandas as pd
import streamlit as st

from services.fundonet_dashboard import FundonetDashboardData, build_dashboard_data
from services.fundonet_errors import FundosNetError
from services.fundonet_service import InformeMensalResult, InformeMensalService


FIDC_CHART_COLORS = [
    "#ff5a00",
    "#111111",
    "#6e6e6e",
    "#c9864a",
    "#b8b8b8",
    "#3a3a3a",
    "#e2a06c",
]


_FIDC_REPORT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@100;200;300;400;500;600;700&display=swap');

html, body, .stApp, .stMarkdown, .stDataFrame, div, p, label, input, select, textarea, button, h1, h2, h3, h4, h5, h6 {
    font-family: 'IBM Plex Sans', sans-serif !important;
}

.stApp {
    background: #ffffff;
    color: #2f3a48;
}

.block-container {
    padding-top: 1rem !important;
}

.fidc-hero {
    background: linear-gradient(180deg, rgba(255,90,0,0.08), rgba(255,255,255,0.98));
    border: 1px solid rgba(255,90,0,0.16);
    border-radius: 16px;
    padding: 18px 20px;
    margin: 0.5rem 0 1.0rem 0;
    box-shadow: 0 10px 26px rgba(0,0,0,0.04);
}

.fidc-hero__kicker {
    color: #ff5a00;
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-weight: 600;
    margin-bottom: 5px;
}

.fidc-hero__title {
    color: #212529;
    font-size: 1.25rem;
    line-height: 1.25;
    font-weight: 500;
    margin-bottom: 10px;
}

.fidc-hero__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}

.fidc-pill {
    display: inline-flex;
    gap: 5px;
    align-items: center;
    border-radius: 999px;
    border: 1px solid rgba(255,90,0,0.22);
    background: #ffffff;
    color: #5a5a5a;
    padding: 4px 9px;
    font-size: 0.76rem;
    box-shadow: 0 3px 10px rgba(0,0,0,0.03);
}

.fidc-pill strong {
    color: #111111;
    font-weight: 500;
}

.fidc-grid {
    display: grid;
    gap: 12px;
    margin: 0.4rem 0 1.0rem 0;
}

.fidc-grid--hero {
    grid-template-columns: repeat(4, minmax(0, 1fr));
}

.fidc-grid--supporting {
    grid-template-columns: repeat(3, minmax(0, 1fr));
}

.fidc-card {
    background: #ffffff;
    border: 1px solid #e9ecef;
    border-left: 3px solid #ff5a00;
    border-radius: 10px;
    padding: 14px 15px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    min-height: 92px;
}

.fidc-card--risk {
    border-left-color: #111111;
}

.fidc-card--neutral {
    border-left-color: #adb5bd;
}

.fidc-card__label {
    color: #5a5a5a;
    font-size: 0.68rem;
    font-weight: 600;
    line-height: 1.25;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 8px;
}

.fidc-card__value {
    color: #212529;
    font-size: 1.45rem;
    font-weight: 400;
    line-height: 1.05;
}

.fidc-card__source {
    color: #8a96a3;
    font-size: 0.72rem;
    line-height: 1.3;
    margin-top: 9px;
}

.fidc-section {
    color: #ff5a00;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 1.45rem 0 0.35rem 0;
    padding-bottom: 0.35rem;
    border-bottom: 1px solid #e9ecef;
}

.fidc-section-caption {
    color: #667382;
    font-size: 0.82rem;
    margin: -0.1rem 0 0.75rem 0;
}

.fidc-period-bar {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    font-size: 0.78rem;
    color: #5a5a5a;
    margin: -0.2rem 0 0.85rem 0;
    padding: 8px 12px;
    background: #f8f9fa;
    border-radius: 8px;
    border-left: 3px solid #ff5a00;
}

.fidc-period-bar span {
    display: inline-flex;
    align-items: center;
    gap: 4px;
}

.fidc-period-bar strong {
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

@media (max-width: 900px) {
    .fidc-grid--hero,
    .fidc-grid--supporting {
        grid-template-columns: 1fr;
    }
    .fidc-card__value {
        font-size: 1.3rem;
    }
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
            return "Sem IMEs no intervalo solicitado"
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
    report = _build_failure_report(exc, tb_text, context)
    st.error(f"Falha na extração: {report['categoria']}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Tipo de erro", report["erro_tipo"])
    col2.metric("Timestamp (UTC)", report["timestamp_utc"])
    col3.metric("Execução", context.get("request_id", "N/D"))
    st.code(report["erro_mensagem"])

    if isinstance(exc, FundosNetError) and exc.details:
        st.warning("O provedor retornou detalhes técnicos relevantes para investigação.")
        st.json(exc.details)

    st.subheader("Diagnóstico técnico")
    checklist = [
        "Validar se o CNPJ possui 14 dígitos e corresponde a um FIDC ativo no Fundos.NET.",
        "Conferir se há IMEs públicos no intervalo de competência informado.",
        "Checar se houve mudança de contrato no endpoint de listagem/download.",
        "Inspecionar status HTTP e corpo de resposta prefixado em detalhes_provedor.",
        "Comparar a trilha de auditoria para identificar a etapa exata da quebra.",
    ]
    for item in checklist:
        st.markdown(f"- {item}")

    with st.expander("Contexto da execução", expanded=False):
        st.json(context)

    if isinstance(exc, FundosNetError) and exc.trace:
        st.subheader("Auditoria da falha")
        audit_df = pd.DataFrame(exc.trace)
        st.dataframe(audit_df, use_container_width=True)

    with st.expander("Traceback completo", expanded=False):
        st.code(tb_text)

    st.download_button(
        "Baixar relatório técnico da falha (JSON)",
        data=_safe_json_bytes(report),
        file_name="relatorio_falha_fidc_ime.json",
        mime="application/json",
    )


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


def render_tab_fidc_ime() -> None:
    st.subheader("tomaconta FIDCs")
    st.caption(
        "Monitoramento de risco por IME/CVM para comprador de cotas seniores. "
        "Informe um CNPJ, escolha a janela de competências e gere a base auditável em Excel."
    )

    today = date.today()
    default_end = date(today.year, today.month, 1)
    default_start = date(default_end.year - 1, default_end.month, 1)

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        cnpj_input = st.text_input("CNPJ do fundo", placeholder="00.000.000/0000-00")
    with col2:
        competencia_inicial = st.date_input("Competência inicial", value=default_start)
    with col3:
        competencia_final = st.date_input("Competência final", value=default_end)

    if not st.button("Extrair IMEs e gerar Excel", type="primary"):
        return

    if competencia_inicial > competencia_final:
        st.error("A competência inicial deve ser menor ou igual à competência final.")
        return

    request_id = uuid.uuid4().hex
    start_ts = time.perf_counter()
    context = {
        "request_id": request_id,
        "cnpj_informado": cnpj_input,
        "competencia_inicial": competencia_inicial.isoformat(),
        "competencia_final": competencia_final.isoformat(),
    }

    status_box = st.empty()
    try:
        progress = _init_progress_bar(0.0, "Preparando execução...", status_box=status_box)
    except TypeError:
        progress = _init_progress_bar(0.0, "Preparando execução...")
        status_box.caption("Preparando execução...")

    def report_progress(current: int, total: int, message: str) -> None:
        fraction = 0.0 if total <= 0 else min(1.0, max(0.0, current / total))
        _update_progress_bar(progress, fraction, message)
        status_box.caption(message)

    service = InformeMensalService()
    try:
        result = service.run(
            cnpj_fundo=cnpj_input,
            data_inicial=competencia_inicial,
            data_final=competencia_final,
            progress_callback=report_progress,
        )
    except Exception as exc:  # noqa: BLE001
        progress.empty()
        status_box.empty()
        tb_text = traceback.format_exc()
        _render_failure_diagnostics(exc, tb_text, context)
        return

    _update_progress_bar(progress, 1.0, "Concluído.")
    status_box.caption("Processamento concluído.")
    _render_execution_observability(context, elapsed_seconds=time.perf_counter() - start_ts)
    try:
        _render_result(result, context)
    except Exception as exc:  # noqa: BLE001
        progress.empty()
        status_box.empty()
        tb_text = traceback.format_exc()
        render_context = dict(context)
        render_context["etapa"] = "renderizacao_resultado"
        _render_failure_diagnostics(exc, tb_text, render_context)



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


def _render_execution_observability(context: dict[str, Any], elapsed_seconds: float | None = None) -> None:
    st.caption(f"Execução: {context.get('request_id', 'N/D')}")
    with st.expander("Observabilidade da execução", expanded=False):
        payload = dict(context)
        if elapsed_seconds is not None:
            payload["duracao_segundos"] = round(elapsed_seconds, 3)
        st.json(payload)


def _read_csv_preview(csv_path, max_rows: int) -> pd.DataFrame:  # noqa: ANN001
    return pd.read_csv(csv_path, nrows=max_rows)


@_cache_data_decorator
def _load_dashboard_data(
    wide_csv_path: str,
    listas_csv_path: str,
    docs_csv_path: str,
) -> FundonetDashboardData:
    return build_dashboard_data(
        wide_csv_path=Path(wide_csv_path),
        listas_csv_path=Path(listas_csv_path),
        docs_csv_path=Path(docs_csv_path),
    )


def _render_dashboard(result: InformeMensalResult, context: dict[str, Any]) -> None:
    dashboard = _load_dashboard_data(
        str(result.wide_csv_path),
        str(result.listas_csv_path),
        str(result.docs_csv_path),
    )
    st.markdown(_FIDC_REPORT_CSS, unsafe_allow_html=True)

    _render_dashboard_header(dashboard)
    _render_dashboard_context_bar(dashboard)
    _render_dashboard_controls(dashboard, context)
    _render_risk_overview(dashboard)
    _render_credit_risk_section(dashboard)
    _render_structural_risk_section(dashboard)
    _render_liquidity_risk_section(dashboard)
    _render_operational_risk_section(dashboard)
    _render_audit_section(dashboard)

    with st.expander("Notas metodológicas", expanded=False):
        for note in dashboard.methodology_notes:
            st.markdown(f"- {note}")


def _render_dashboard_controls(dashboard: FundonetDashboardData, context: dict[str, Any]) -> None:
    left, right = st.columns([1.25, 1])
    with left:
        st.toggle(
            "Mostrar data labels nos gráficos",
            value=False,
            key="fidc_chart_labels",
            help="Ativa labels visuais nos gráficos. Quando ligado, os rótulos priorizam legibilidade e evitam excesso de texto.",
        )
    with right:
        _render_pdf_export_button(dashboard, context)


def _render_risk_overview(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section(
        "Radar de risco",
        "Leitura rápida para comprador de cotas seniores: crédito, estrutura e liquidez no IME mais recente.",
    )
    metric_lookup = dashboard.risk_metrics_df.set_index("metric_id", drop=False)
    card_ids = [
        "subordinacao_pct",
        "inadimplencia_pct",
        "alocacao_pct",
        "liquidez_30_pct_pl",
        "liquidez_imediata_pct_pl",
        "resgate_solicitado_pct_pl",
    ]
    cards: list[str] = []
    for metric_id in card_ids:
        if metric_id not in metric_lookup.index:
            continue
        row = metric_lookup.loc[metric_id]
        cards.append(
            _render_fidc_card(
                str(row["label"]),
                _format_metric_value(row.get("value"), str(row.get("unit") or "")),
                f"{row.get('risk_block')} · {row.get('source_data')}",
                variant="risk" if row.get("criticality") == "critico" else "",
            )
        )
    cards.append(
        _render_fidc_card(
            "Camadas críticas fora do IME",
            str(len(dashboard.coverage_gap_df)),
            "Cobertura, reservas, triggers, rating, lastro e covenants exigem fonte complementar.",
            variant="neutral",
        )
    )
    st.markdown(_render_fidc_grid(cards, "fidc-grid--supporting"), unsafe_allow_html=True)


def _render_credit_risk_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section(
        "Risco de crédito",
        "Estresse da carteira, provisionamento e concentração proxy com base no IME.",
    )
    top_left, top_right = st.columns([1.25, 1])
    top_left.dataframe(
        _format_risk_metrics_table(dashboard.risk_metrics_df, risk_block="Risco de crédito"),
        use_container_width=True,
        hide_index=True,
    )
    if dashboard.segment_latest_df.empty:
        top_right.info("O IME mais recente não trouxe composição setorial positiva da carteira.")
    else:
        top_right.altair_chart(
            _horizontal_bar_chart(
                dashboard.segment_latest_df,
                category_column="segmento",
                value_column="valor",
                title="Concentração setorial proxy",
            ),
            use_container_width=True,
        )

    bottom_left, bottom_right = st.columns(2)
    bottom_left.altair_chart(
        _line_history_chart(
            _melt_metrics(
                dashboard.default_history_df,
                ["inadimplencia_total", "provisao_total", "pendencia_total"],
                {
                    "inadimplencia_total": "Inadimplência",
                    "provisao_total": "Provisão",
                    "pendencia_total": "Pendências",
                },
            ),
            title="Saldos de crédito problemático",
            y_title="R$",
        ),
        use_container_width=True,
    )
    bottom_right.altair_chart(
        _bar_chart(
            dashboard.default_buckets_latest_df,
            x_column="faixa",
            y_column="valor",
            title=f"Aging da inadimplência em {dashboard.latest_competencia}",
            y_title="R$",
        ),
        use_container_width=True,
    )


def _render_structural_risk_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section(
        "Risco estrutural",
        "Subordinação, alocação e leitura da arquitetura das cotas. O painel separa o que vem do IME do que depende de regulamento.",
    )
    top_left, top_right = st.columns([1.15, 1])
    top_left.dataframe(
        _format_risk_metrics_table(dashboard.risk_metrics_df, risk_block="Risco estrutural"),
        use_container_width=True,
        hide_index=True,
    )
    top_right.altair_chart(
        _line_history_chart(
            _melt_metrics(
                dashboard.subordination_history_df,
                ["subordinacao_pct"],
                {"subordinacao_pct": "Subordinação"},
            ),
            title="Índice de subordinação",
            y_title="%",
        ),
        use_container_width=True,
    )

    bottom_left, bottom_right = st.columns(2)
    bottom_left.altair_chart(
        _stacked_area_chart(
            dashboard.quota_pl_history_df,
            title="Patrimônio líquido das cotas",
            value_column="pl",
            y_title="R$",
        ),
        use_container_width=True,
    )
    if not dashboard.performance_vs_benchmark_latest_df.empty:
        bottom_right.dataframe(
            _format_performance_benchmark_table(dashboard.performance_vs_benchmark_latest_df),
            use_container_width=True,
            hide_index=True,
        )
    else:
        bottom_right.info("O IME não trouxe quadro de benchmark x realizado para a competência mais recente.")

    latest_quota_df = _format_latest_quota_frame(dashboard.quota_pl_history_df, dashboard.latest_competencia)
    if not latest_quota_df.empty:
        st.caption(f"Quadro de cotas em {dashboard.latest_competencia}")
        st.dataframe(latest_quota_df, use_container_width=True, hide_index=True)


def _render_liquidity_risk_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section(
        "Risco de liquidez e funding",
        "Liquidez reportada, vencimentos e fluxos de cotas. A interpretação econômica dos eventos preserva o sinal do caixa.",
    )
    top_left, top_right = st.columns([1.15, 1])
    top_left.dataframe(
        _format_risk_metrics_table(dashboard.risk_metrics_df, risk_block="Risco de liquidez"),
        use_container_width=True,
        hide_index=True,
    )
    top_right.dataframe(
        _format_event_summary_table(dashboard.event_summary_latest_df),
        use_container_width=True,
        hide_index=True,
    )

    mid_left, mid_right = st.columns(2)
    mid_left.altair_chart(
        _line_point_chart(
            dashboard.liquidity_latest_df,
            x_column="horizonte",
            y_column="valor",
            title=f"Liquidez reportada em {dashboard.latest_competencia}",
            y_title="R$",
        ),
        use_container_width=True,
    )
    mid_right.altair_chart(
        _bar_chart(
            dashboard.maturity_latest_df,
            x_column="faixa",
            y_column="valor",
            title=f"Prazo de vencimento em {dashboard.latest_competencia}",
            y_title="R$",
        ),
        use_container_width=True,
    )

    flow_df = _melt_metrics(
        dashboard.asset_history_df,
        ["aquisicoes", "alienacoes"],
        {"aquisicoes": "Aquisições", "alienacoes": "Alienações"},
    )
    bottom_left, bottom_right = st.columns(2)
    bottom_left.altair_chart(
        _grouped_bar_chart(
            flow_df,
            title="Fluxo dos direitos creditórios",
            y_title="R$",
        ),
        use_container_width=True,
    )
    if dashboard.event_history_df.empty:
        bottom_right.info("O intervalo selecionado não trouxe emissões, resgates ou amortizações no bloco CAPTA_RESGA_AMORTI.")
    else:
        event_chart_df = (
            dashboard.event_history_df.groupby(["competencia", "competencia_dt", "event_type"], dropna=False)[
                "valor_total_assinado"
            ]
            .sum()
            .reset_index()
            .rename(columns={"valor_total_assinado": "valor"})
        )
        event_chart_df["serie"] = event_chart_df["event_type"].map(
            {
                "emissao": "Emissão",
                "resgate": "Resgate pago",
                "amortizacao": "Amortização",
            }
        )
        bottom_right.altair_chart(
            _grouped_bar_chart(
                event_chart_df,
                title="Eventos de cotas por competência",
                y_title="R$",
            ),
            use_container_width=True,
        )


def _render_operational_risk_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section(
        "Risco operacional e contratual",
        "O que um comprador de sênior ainda precisa fora do IME para fechar a análise de risco da estrutura.",
    )
    left, right = st.columns(2)
    left.dataframe(
        _format_coverage_gap_table(dashboard.coverage_gap_df),
        use_container_width=True,
        hide_index=True,
    )
    right.dataframe(
        _format_glossary_table(dashboard.mini_glossary_df),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Leitura operacional: este painel usa o IME como camada-base. Cobertura, reservas, rating, gatilhos, cedente/devedor, coobrigação e lastro exigem regulamento, relatório mensal e documentos da oferta."
    )


def _render_audit_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section(
        "Memória de cálculo e evidência",
        "Reconciliação completa entre dado bruto, transformação, output e limitação analítica.",
    )
    with st.expander("Memória de cálculo das métricas exibidas", expanded=False):
        st.dataframe(
            _format_risk_metrics_memory_table(dashboard.risk_metrics_df),
            use_container_width=True,
            hide_index=True,
        )
    with st.expander("Inventário do dashboard atual", expanded=False):
        st.dataframe(
            dashboard.current_dashboard_inventory_df,
            use_container_width=True,
            hide_index=True,
        )
    with st.expander("Base CVM normalizada", expanded=False):
        _render_cvm_tables_section(dashboard)


def _render_dashboard_header(dashboard: FundonetDashboardData) -> None:
    info = dashboard.fund_info
    dominant_segment = ""
    if not dashboard.segment_latest_df.empty and "valor" in dashboard.segment_latest_df.columns:
        dominant_segment = str(
            dashboard.segment_latest_df.sort_values("valor", ascending=False).iloc[0].get("segmento") or ""
        )
    pills = [
        ("Condomínio", info.get("condominio", "N/D")),
        ("Classe única", info.get("classe_unica", "N/D")),
        ("Estrutura subordinada", info.get("estrutura_subordinada", "N/D")),
        ("Cotistas", info.get("total_cotistas", "N/D")),
        ("Segmento CVM", dominant_segment or "N/D"),
        ("CNPJ fundo", _format_cnpj(info.get("cnpj_fundo", ""))),
        ("CNPJ administrador", _format_cnpj(info.get("cnpj_administrador", ""))),
    ]
    pills_html = "\n".join(
        f'<span class="fidc-pill"><strong>{escape(label)}:</strong> {escape(str(value or "N/D"))}</span>'
        for label, value in pills
        if value and value != "N/D"
    )
    title = info.get("nome_fundo") or info.get("nome_classe") or "FIDC selecionado"
    subtitle = info.get("nome_classe") or info.get("fundo_ou_classe") or "Informe Mensal Estruturado"
    st.markdown(
        f"""
<div class="fidc-hero">
  <div class="fidc-hero__kicker">Informe Mensal CVM · Snapshot analítico</div>
  <div class="fidc-hero__title">{escape(str(title))}</div>
  <div class="fidc-section-caption">{escape(str(subtitle))}</div>
  <div class="fidc-hero__meta">{pills_html}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_dashboard_context_bar(dashboard: FundonetDashboardData) -> None:
    info = dashboard.fund_info
    st.markdown(
        f"""
<div class="fidc-period-bar">
  <span><strong>Última competência:</strong> {escape(str(info.get("ultima_competencia") or "N/D"))}</span>
  <span><strong>Janela:</strong> {escape(str(info.get("periodo_analisado") or "N/D"))}</span>
  <span><strong>IMEs processados:</strong> {escape(str(len(dashboard.competencias)))}</span>
  <span><strong>Última entrega:</strong> {escape(str(info.get("ultima_entrega") or "N/D"))}</span>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_pdf_export_button(dashboard: FundonetDashboardData, context: dict[str, Any]) -> None:
    try:
        from services.fundonet_pdf_export import build_dashboard_pdf_bytes
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Exportação em PDF indisponível neste ambiente: {exc}")
        return

    try:
        pdf_bytes = build_dashboard_pdf_bytes(dashboard)
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


def _render_overview_metrics(dashboard: FundonetDashboardData) -> None:
    summary = dashboard.summary
    _render_fidc_section("Visão geral", "O que importa primeiro para se situar no IME mais recente.")
    hero_cards = [
        _render_fidc_card("Direitos creditórios", _format_brl_compact(summary.get("direitos_creditorios")), "DICRED/VL_DICRED"),
        _render_fidc_card("PL total", _format_brl_compact(summary.get("pl_total")), "Cotas sênior + subordinadas"),
        _render_fidc_card("Subordinação", _format_percent(summary.get("subordinacao_pct")), "PL subordinado / PL total"),
        _render_fidc_card("Inadimplência", _format_percent(summary.get("inadimplencia_pct")), "Inadimplência / direitos creditórios", variant="risk"),
    ]
    st.markdown(_render_fidc_grid(hero_cards, "fidc-grid--hero"), unsafe_allow_html=True)

    supporting_cards = [
        _render_fidc_card("Ativos totais", _format_brl_compact(summary.get("ativos_totais")), "APLIC_ATIVO/VL_SOM_APLIC_ATIVO"),
        _render_fidc_card("Alocação", _format_percent(summary.get("alocacao_pct")), "Direitos creditórios / carteira"),
        _render_fidc_card("Provisão", _format_brl_compact(summary.get("provisao_total")), "Provisão para redução/recuperação", variant="neutral"),
        _render_fidc_card("Liquidez imediata", _format_brl_compact(summary.get("liquidez_imediata")), "OUTRAS_INFORM/LIQUIDEZ"),
        _render_fidc_card("Liquidez até 30 dias", _format_brl_compact(summary.get("liquidez_30")), "OUTRAS_INFORM/LIQUIDEZ"),
        _render_fidc_card("Resgate solicitado", _format_brl_compact(summary.get("resgate_solicitado_mes")), "CAPTA_RESGA_AMORTI/RESG_SOLIC", variant="risk"),
    ]
    st.markdown(_render_fidc_grid(supporting_cards, "fidc-grid--supporting"), unsafe_allow_html=True)


def _render_monitoring_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section(
        "Monitoramento estrutural",
        "Indicadores úteis para acompanhamento recorrente que já estão no IME, sem inferir covenants documentais fora da fonte.",
    )
    left, right = st.columns(2)
    with left:
        st.caption("Indicadores calculados")
        st.dataframe(
            _format_tracking_table(dashboard.tracking_latest_df),
            use_container_width=True,
            hide_index=True,
        )
    with right:
        st.caption(f"Eventos e pressões de cotas em {dashboard.latest_competencia}")
        st.dataframe(
            _format_event_summary_table(dashboard.event_summary_latest_df),
            use_container_width=True,
            hide_index=True,
        )


def _render_fidc_section(title: str, caption: str | None = None) -> None:
    st.markdown(f'<div class="fidc-section">{escape(title)}</div>', unsafe_allow_html=True)
    if caption:
        st.markdown(f'<div class="fidc-section-caption">{escape(caption)}</div>', unsafe_allow_html=True)


def _render_fidc_card(label: str, value: str, source: str = "", *, variant: str = "") -> str:
    variant_class = f" fidc-card--{variant}" if variant else ""
    source_html = f'<div class="fidc-card__source">{escape(source)}</div>' if source else ""
    return (
        f'<div class="fidc-card{variant_class}">'
        f'<div class="fidc-card__label">{escape(label)}</div>'
        f'<div class="fidc-card__value">{escape(value)}</div>'
        f"{source_html}"
        "</div>"
    )


def _render_fidc_grid(cards_html: list[str], grid_class: str) -> str:
    return f'<div class="fidc-grid {grid_class}">{"".join(cards_html)}</div>'


def _render_asset_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section(
        "Ativo e carteira",
        "Composição da carteira, liquidez e vencimentos no padrão do relatório mensal.",
    )
    top_left, top_right = st.columns([3, 2])
    top_left.altair_chart(
        _line_history_chart(
            _melt_metrics(
                dashboard.asset_history_df,
                ["ativos_totais", "carteira", "direitos_creditorios"],
                {
                    "ativos_totais": "Ativos totais",
                    "carteira": "Carteira",
                    "direitos_creditorios": "Direitos creditórios",
                },
            ),
            title="Evolução do Ativo",
            y_title="R$",
        ),
        use_container_width=True,
    )
    top_right.altair_chart(
        _horizontal_bar_chart(
            dashboard.composition_latest_df,
            category_column="categoria",
            value_column="valor",
            title=f"Composição do Ativo em {dashboard.composition_latest_df['competencia'].iloc[0]}",
        ),
        use_container_width=True,
    )

    mid_left, mid_right = st.columns(2)
    mid_left.altair_chart(
        _line_history_chart(
            _melt_metrics(
                dashboard.asset_history_df,
                ["alocacao_pct"],
                {"alocacao_pct": "Alocação"},
            ),
            title="Alocação em Direitos Creditórios",
            y_title="%",
        ),
        use_container_width=True,
    )
    mid_right.altair_chart(
        _line_point_chart(
            dashboard.liquidity_latest_df,
            x_column="horizonte",
            y_column="valor",
            title=f"Liquidez Reportada em {dashboard.latest_competencia}",
            y_title="R$",
        ),
        use_container_width=True,
    )

    bottom_left, bottom_right = st.columns(2)
    bottom_left.altair_chart(
        _bar_chart(
            dashboard.maturity_latest_df,
            x_column="faixa",
            y_column="valor",
            title=f"Direitos Creditórios por Prazo de Vencimento em {dashboard.latest_competencia}",
            y_title="R$",
        ),
        use_container_width=True,
    )
    flow_df = _melt_metrics(
        dashboard.asset_history_df,
        ["aquisicoes", "alienacoes"],
        {"aquisicoes": "Aquisições", "alienacoes": "Alienações"},
    )
    bottom_right.altair_chart(
        _grouped_bar_chart(
            flow_df,
            title="Fluxo dos Direitos Creditórios",
            y_title="R$",
        ),
        use_container_width=True,
    )

    table_left, table_right = st.columns(2)
    with table_left:
        st.caption("Composição do ativo/carteira")
        st.dataframe(
            _format_value_percent_table(
                dashboard.composition_latest_df,
                label_column="categoria",
                label_title="Categoria",
            ),
            use_container_width=True,
            hide_index=True,
        )
    with table_right:
        st.caption("Carteira por segmento")
        st.dataframe(
            _format_value_percent_table(
                dashboard.segment_latest_df,
                label_column="segmento",
                label_title="Segmento",
            ),
            use_container_width=True,
            hide_index=True,
        )


def _render_quota_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section(
        "Cotas, PL e remuneração",
        "PL por classe, índice de subordinação e rentabilidade mensal das cotas.",
    )
    top_left, top_right = st.columns(2)
    top_left.altair_chart(
        _stacked_area_chart(
            dashboard.quota_pl_history_df,
            title="Patrimônio Líquido das Cotas",
            value_column="pl",
            y_title="R$",
        ),
        use_container_width=True,
    )
    top_right.altair_chart(
        _line_history_chart(
            _melt_metrics(
                dashboard.subordination_history_df,
                ["subordinacao_pct"],
                {"subordinacao_pct": "Subordinação"},
            ),
            title="Índice de Subordinação",
            y_title="%",
        ),
        use_container_width=True,
    )

    bottom_left, bottom_right = st.columns([3, 2])
    bottom_left.altair_chart(
        _line_history_chart(
            _return_chart_frame(dashboard.return_history_df),
            title="Rentabilidade Mensal das Cotas",
            y_title="%",
        ),
        use_container_width=True,
    )
    bottom_right.dataframe(
        _format_return_summary_frame(dashboard.return_summary_df),
        use_container_width=True,
        hide_index=True,
    )
    if not dashboard.performance_vs_benchmark_latest_df.empty:
        bottom_right.caption(f"Benchmark x realizado em {dashboard.latest_competencia}")
        bottom_right.dataframe(
            _format_performance_benchmark_table(dashboard.performance_vs_benchmark_latest_df),
            use_container_width=True,
            hide_index=True,
        )

    latest_quota_df = _format_latest_quota_frame(dashboard.quota_pl_history_df, dashboard.latest_competencia)
    if not latest_quota_df.empty:
        st.caption(f"Quadro de cotas em {dashboard.latest_competencia}")
        st.dataframe(latest_quota_df, use_container_width=True, hide_index=True)


def _render_default_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section(
        "Inadimplência",
        "Saldos vencidos, provisões e aging da inadimplência reportada.",
    )
    top_left, top_right = st.columns(2)
    top_left.altair_chart(
        _line_history_chart(
            _melt_metrics(
                dashboard.default_history_df,
                ["inadimplencia_total", "provisao_total", "pendencia_total"],
                {
                    "inadimplencia_total": "Inadimplência",
                    "provisao_total": "Provisão",
                    "pendencia_total": "Pendências",
                },
            ),
            title="Saldos de Crédito Problemático",
            y_title="R$",
        ),
        use_container_width=True,
    )
    top_right.altair_chart(
        _line_history_chart(
            _melt_metrics(
                dashboard.default_history_df,
                ["inadimplencia_pct"],
                {"inadimplencia_pct": "Inadimplência / Direitos creditórios"},
            ),
            title="Inadimplência Relativa",
            y_title="%",
        ),
        use_container_width=True,
    )

    st.altair_chart(
        _bar_chart(
            dashboard.default_buckets_latest_df,
            x_column="faixa",
            y_column="valor",
            title=f"Aging da Inadimplência em {dashboard.latest_competencia}",
            y_title="R$",
        ),
        use_container_width=True,
    )
    st.dataframe(
        _format_value_table(dashboard.default_buckets_latest_df, label_column="faixa", label_title="Faixa"),
        use_container_width=True,
        hide_index=True,
    )


def _render_events_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section(
        "Emissões, resgates e amortizações",
        "Eventos de cotas reportados no bloco CAPTA_RESGA_AMORTI, com sinal econômico separado do valor bruto.",
    )
    if not dashboard.event_summary_latest_df.empty:
        st.caption(f"Resumo dos eventos em {dashboard.latest_competencia}")
        st.dataframe(
            _format_event_summary_table(dashboard.event_summary_latest_df),
            use_container_width=True,
            hide_index=True,
        )

    if dashboard.event_history_df.empty:
        st.info("O intervalo selecionado não trouxe eventos de emissão, resgate ou amortização no IME.")
        return

    event_chart_df = (
        dashboard.event_history_df.groupby(["competencia", "competencia_dt", "event_type"], dropna=False)[
            "valor_total_assinado"
        ]
        .sum()
        .reset_index()
        .rename(columns={"valor_total_assinado": "valor"})
    )
    event_chart_df["serie"] = event_chart_df["event_type"].map(
        {
            "emissao": "Emissão",
            "resgate": "Resgate pago",
            "amortizacao": "Amortização",
        }
    )
    st.altair_chart(
        _grouped_bar_chart(
            event_chart_df,
            title="Eventos de Cotas por Competência (Sinal Econômico)",
            y_title="R$",
        ),
        use_container_width=True,
    )

    latest_events_df = dashboard.event_history_df[
        dashboard.event_history_df["competencia"] == dashboard.latest_competencia
    ].copy()
    if not latest_events_df.empty:
        latest_events_df["Evento"] = latest_events_df["event_type"].map(
            {
                "emissao": "Emissão",
                "resgate": "Resgate pago",
                "amortizacao": "Amortização",
            }
        )
        latest_events_df["Valor total"] = latest_events_df["valor_total"].map(_format_brl_compact)
        latest_events_df["Sinal econômico"] = latest_events_df["valor_total_assinado"].map(_format_brl_compact)
        latest_events_df["% PL"] = latest_events_df["valor_total_pct_pl"].map(_format_percent)
        latest_events_df["Valor por cota"] = latest_events_df["valor_cota"].map(_format_brl)
        latest_events_df["Qt. cotas"] = latest_events_df["qt_cotas"].map(_format_decimal)
        latest_events_df["Classe"] = latest_events_df["label"]
        latest_events_df = latest_events_df[
            ["Evento", "Classe", "Qt. cotas", "Valor por cota", "Valor total", "Sinal econômico", "% PL"]
        ]
        st.dataframe(latest_events_df, use_container_width=True, hide_index=True)


def _render_cvm_tables_section(dashboard: FundonetDashboardData) -> None:
    _render_fidc_section(
        "Tabelas CVM normalizadas",
        "Base tabular do XML parseado, útil para conferência e leitura de detalhe.",
    )
    left, right = st.columns(2)
    with left:
        st.caption("Liquidez reportada")
        st.dataframe(
            _format_value_table(dashboard.liquidity_latest_df, label_column="horizonte", label_title="Horizonte"),
            use_container_width=True,
            hide_index=True,
        )
    with right:
        st.caption("Cotistas")
        st.dataframe(
            _format_holder_table(dashboard.holder_latest_df),
            use_container_width=True,
            hide_index=True,
        )

    if not dashboard.rate_negotiation_latest_df.empty:
        with st.expander("Taxas de negociação de direitos creditórios", expanded=False):
            st.dataframe(
                _format_rate_table(dashboard.rate_negotiation_latest_df),
                use_container_width=True,
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
    chart_df = return_history_df[["competencia", "competencia_dt", "label", "retorno_mensal_pct"]].copy()
    chart_df = chart_df.rename(columns={"label": "serie", "retorno_mensal_pct": "valor"})
    chart_df["valor"] = pd.to_numeric(chart_df["valor"], errors="coerce")
    return chart_df.dropna(subset=["valor"])


def _format_return_summary_frame(return_summary_df: pd.DataFrame) -> pd.DataFrame:
    if return_summary_df.empty:
        return pd.DataFrame(columns=["Classe", "Mês", "Ano", "12 Meses"])
    table_df = return_summary_df.copy()
    table_df["Classe"] = table_df["label"]
    table_df["Mês"] = table_df["retorno_mes_pct"].map(_format_percent)
    table_df["Ano"] = table_df["retorno_ano_pct"].map(_format_percent)
    table_df["12 Meses"] = table_df["retorno_12m_pct"].map(_format_percent)
    return table_df[["Classe", "Mês", "Ano", "12 Meses"]]


def _format_performance_benchmark_table(performance_df: pd.DataFrame) -> pd.DataFrame:
    if performance_df.empty:
        return pd.DataFrame(columns=["Classe", "Benchmark", "Realizado", "Gap (bps)"])
    output = performance_df.copy()
    output["Classe"] = output["label"]
    output["Benchmark"] = output["desempenho_esperado_pct"].map(_format_percent)
    output["Realizado"] = output["desempenho_real_pct"].map(_format_percent)
    output["Gap (bps)"] = output["gap_bps"].map(lambda value: _format_decimal(value, decimals=0))
    return output[["Classe", "Benchmark", "Realizado", "Gap (bps)"]]


def _format_latest_quota_frame(quota_pl_history_df: pd.DataFrame, latest_competencia: str) -> pd.DataFrame:
    if quota_pl_history_df.empty:
        return pd.DataFrame(columns=["Classe", "Tipo", "Qt. cotas", "Valor da cota", "PL"])
    latest_df = quota_pl_history_df[quota_pl_history_df["competencia"] == latest_competencia].copy()
    if latest_df.empty:
        return pd.DataFrame(columns=["Classe", "Tipo", "Qt. cotas", "Valor da cota", "PL"])
    latest_df["Classe"] = latest_df["label"]
    latest_df["Tipo"] = latest_df["class_kind"].map({"senior": "Sênior", "subordinada": "Subordinada"}).fillna(
        latest_df["class_kind"]
    )
    latest_df["Qt. cotas"] = latest_df["qt_cotas"].map(lambda value: _format_decimal(value, decimals=4))
    latest_df["Valor da cota"] = latest_df["vl_cota"].map(_format_brl)
    latest_df["PL"] = latest_df["pl"].map(_format_brl_compact)
    return latest_df[["Classe", "Tipo", "Qt. cotas", "Valor da cota", "PL"]]


def _format_value_percent_table(df: pd.DataFrame, *, label_column: str, label_title: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[label_title, "Valor", "%"])
    output = df.copy()
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


def _format_event_summary_table(event_summary_df: pd.DataFrame) -> pd.DataFrame:
    if event_summary_df.empty:
        return pd.DataFrame(columns=["Evento", "Valor bruto", "Sinal econômico", "% PL", "Status", "Leitura"])
    output = event_summary_df.sort_values("ordem").copy() if "ordem" in event_summary_df.columns else event_summary_df.copy()
    output["Evento"] = output["evento"]
    output["Valor bruto"] = output["valor_total"].map(_format_brl_compact)
    output["Sinal econômico"] = output["valor_total_assinado"].map(_format_brl_compact)
    output["% PL"] = output["valor_total_pct_pl"].map(_format_percent)
    output["Status"] = output["source_status"].map(_format_source_status)
    output["Leitura"] = output["interpretação"]
    return output[["Evento", "Valor bruto", "Sinal econômico", "% PL", "Status", "Leitura"]]


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
        return pd.DataFrame(columns=["Métrica", "Valor", "Criticidade", "Fonte", "Interpretação", "Limitação", "Estado"])
    output = metrics_df[metrics_df["risk_block"] == risk_block].copy()
    if output.empty:
        return pd.DataFrame(columns=["Métrica", "Valor", "Criticidade", "Fonte", "Interpretação", "Limitação", "Estado"])
    output["Métrica"] = output["label"]
    output["Valor"] = output.apply(
        lambda row: _format_metric_value(row.get("value"), str(row.get("unit") or "")),
        axis=1,
    )
    output["Criticidade"] = output["criticality"].map(_format_metric_criticality)
    output["Fonte"] = output["source_data"]
    output["Interpretação"] = output["interpretation"]
    output["Limitação"] = output["limitation"]
    output["Estado"] = output["state"].map(_format_risk_metric_state)
    return output[["Métrica", "Valor", "Criticidade", "Fonte", "Interpretação", "Limitação", "Estado"]]


def _format_risk_metrics_memory_table(metrics_df: pd.DataFrame) -> pd.DataFrame:
    if metrics_df.empty:
        return pd.DataFrame(
            columns=[
                "Bloco de risco",
                "Métrica",
                "Variável final",
                "Fonte",
                "Transformação",
                "Fórmula",
                "Pipeline",
                "Interpretação",
                "Limitação",
                "Estado",
            ]
        )
    output = metrics_df.copy()
    output["Bloco de risco"] = output["risk_block"]
    output["Métrica"] = output["label"]
    output["Variável final"] = output["final_variable"]
    output["Fonte"] = output["source_data"]
    output["Transformação"] = output["transformation"]
    output["Fórmula"] = output["formula"]
    output["Pipeline"] = output["pipeline"]
    output["Interpretação"] = output["interpretation"]
    output["Limitação"] = output["limitation"]
    output["Estado"] = output["state"].map(_format_risk_metric_state)
    return output[
        [
            "Bloco de risco",
            "Métrica",
            "Variável final",
            "Fonte",
            "Transformação",
            "Fórmula",
            "Pipeline",
            "Interpretação",
            "Limitação",
            "Estado",
        ]
    ]


def _format_coverage_gap_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Tema", "Status", "Por que importa", "Fonte necessária"])
    output = df.copy()
    output["Tema"] = output["tema"]
    output["Status"] = output["status"]
    output["Por que importa"] = output["por_que_importa"]
    output["Fonte necessária"] = output["fonte_necessaria"]
    return output[["Tema", "Status", "Por que importa", "Fonte necessária"]]


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
    session_state = getattr(st, "session_state", None)
    if session_state is None:
        return False
    try:
        return bool(session_state.get("fidc_chart_labels", False))
    except Exception:  # noqa: BLE001
        return False


def _label_format(unit: str) -> str:
    return ",.2f" if unit in {"R$", "%"} else ",.2f"


def _line_end_label_layer(chart_df: pd.DataFrame, *, y_title: str) -> alt.Chart | None:
    if not _chart_labels_enabled() or chart_df.empty or "serie" not in chart_df.columns:
        return None
    labels_df = (
        chart_df.sort_values(["serie", "competencia_dt"])
        .groupby("serie", as_index=False, dropna=False)
        .tail(1)
    )
    if labels_df.empty:
        return None
    return (
        alt.Chart(labels_df)
        .mark_text(align="left", dx=6, dy=-6, fontSize=11, color="#111111")
        .encode(
            x=alt.X("competencia:N", sort=chart_df["competencia"].drop_duplicates().tolist()),
            y=alt.Y("valor:Q", title=y_title),
            text=alt.Text("valor:Q", format=_label_format(y_title)),
            color=alt.Color("serie:N", legend=None, scale=alt.Scale(range=FIDC_CHART_COLORS)),
        )
    )


def _point_label_layer(chart_df: pd.DataFrame, *, x_encoding: alt.X, y_encoding: alt.Y, y_field: str, color: str = "#111111") -> alt.Chart | None:
    if not _chart_labels_enabled() or chart_df.empty:
        return None
    return (
        alt.Chart(chart_df)
        .mark_text(dy=-10, fontSize=11, color=color)
        .encode(
            x=x_encoding,
            y=y_encoding,
            text=alt.Text(f"{y_field}:Q", format=_label_format(y_encoding.title or "")),
        )
    )


def _bar_label_layer(
    chart_df: pd.DataFrame,
    *,
    x_encoding: alt.X | None,
    y_encoding: alt.Y | None,
    value_field: str,
    orient: str = "vertical",
    color_encoding: alt.Color | None = None,
) -> alt.Chart | None:
    if not _chart_labels_enabled() or chart_df.empty:
        return None
    mark_kwargs = {"fontSize": 11, "color": "#111111"}
    if orient == "horizontal":
        mark_kwargs.update({"align": "left", "dx": 4})
    else:
        mark_kwargs.update({"dy": -8})
    encoding: dict[str, object] = {
        "text": alt.Text(f"{value_field}:Q", format=_label_format(y_encoding.title if y_encoding is not None else "")),
    }
    if x_encoding is not None:
        encoding["x"] = x_encoding
    if y_encoding is not None:
        encoding["y"] = y_encoding
    if color_encoding is not None:
        encoding["color"] = color_encoding
    return alt.Chart(chart_df).mark_text(**mark_kwargs).encode(**encoding)


def _line_history_chart(
    chart_df: pd.DataFrame,
    *,
    title: str,
    y_title: str,
    limit_value: float | None = None,
    limit_label: str | None = None,
) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df)
    x_encoding = alt.X("competencia:N", title="Competência", sort=chart_df["competencia"].drop_duplicates().tolist())
    y_encoding = alt.Y("valor:Q", title=y_title)
    base = (
        alt.Chart(chart_df)
        .mark_line(point=True)
        .encode(
            x=x_encoding,
            y=y_encoding,
            color=alt.Color("serie:N", title="Série", scale=alt.Scale(range=FIDC_CHART_COLORS)),
            tooltip=["competencia:N", "serie:N", alt.Tooltip("valor:Q", format=",.2f")],
        )
        .properties(title=title, height=320)
    )
    labels = _line_end_label_layer(chart_df, y_title=y_title)
    layered = base if labels is None else (base + labels)
    if limit_value is None:
        return _style_altair_chart(layered)

    limit_df = pd.DataFrame({"valor": [limit_value]})
    rule = (
        alt.Chart(limit_df)
        .mark_rule(strokeDash=[6, 4], color="#6b7280")
        .encode(y="valor:Q", tooltip=[alt.Tooltip("valor:Q", format=",.2f", title=limit_label or "Limite")])
    )
    return _style_altair_chart(layered + rule)


def _line_point_chart(
    chart_df: pd.DataFrame,
    *,
    x_column: str,
    y_column: str,
    title: str,
    y_title: str,
) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df)
    x_encoding = alt.X(f"{x_column}:N", title="Horizonte")
    y_encoding = alt.Y(f"{y_column}:Q", title=y_title)
    chart = (
        alt.Chart(chart_df)
        .mark_line(point=True)
        .encode(
            x=x_encoding,
            y=y_encoding,
            tooltip=[f"{x_column}:N", alt.Tooltip(f"{y_column}:Q", format=",.2f")],
        )
        .properties(title=title, height=320)
    )
    labels = _point_label_layer(chart_df, x_encoding=x_encoding, y_encoding=y_encoding, y_field=y_column)
    return _style_altair_chart(chart if labels is None else (chart + labels))


def _horizontal_bar_chart(
    chart_df: pd.DataFrame,
    *,
    category_column: str,
    value_column: str,
    title: str,
) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df)
    x_encoding = alt.X(f"{value_column}:Q", title="R$")
    y_encoding = alt.Y(f"{category_column}:N", title=None, sort="-x")
    color_encoding = alt.Color(f"{category_column}:N", legend=None, scale=alt.Scale(range=FIDC_CHART_COLORS))
    chart = (
        alt.Chart(chart_df)
        .mark_bar()
        .encode(
            x=x_encoding,
            y=y_encoding,
            color=color_encoding,
            tooltip=[f"{category_column}:N", alt.Tooltip(f"{value_column}:Q", format=",.2f")],
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


def _bar_chart(
    chart_df: pd.DataFrame,
    *,
    x_column: str,
    y_column: str,
    title: str,
    y_title: str,
) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df)
    x_sort = (
        chart_df.sort_values("ordem")[x_column].tolist()
        if "ordem" in chart_df.columns
        else chart_df[x_column].drop_duplicates().tolist()
    )
    tooltip = [f"{x_column}:N", alt.Tooltip(f"{y_column}:Q", format=",.2f")]
    if "source_status" in chart_df.columns:
        chart_df["status_fonte"] = chart_df["source_status"].map(_format_source_status)
        tooltip.append("status_fonte:N")
    x_encoding = alt.X(f"{x_column}:N", title=None, sort=x_sort)
    y_encoding = alt.Y(f"{y_column}:Q", title=y_title)
    chart = (
        alt.Chart(chart_df)
        .mark_bar(color="#ff5a00")
        .encode(
            x=x_encoding,
            y=y_encoding,
            tooltip=tooltip,
        )
        .properties(title=title, height=320)
    )
    labels = _bar_label_layer(chart_df, x_encoding=x_encoding, y_encoding=y_encoding, value_field=y_column)
    return _style_altair_chart(chart if labels is None else (chart + labels))


def _grouped_bar_chart(chart_df: pd.DataFrame, *, title: str, y_title: str) -> alt.Chart:
    chart_df = _altair_compatible_df(chart_df)
    value_field = "valor_total" if "valor_total" in chart_df.columns else "valor"
    x_encoding = alt.X("competencia:N", title="Competência", sort=chart_df["competencia"].drop_duplicates().tolist())
    y_encoding = alt.Y(f"{value_field}:Q", title=y_title)
    color_encoding = alt.Color("serie:N", title="Série", scale=alt.Scale(range=FIDC_CHART_COLORS))
    chart = (
        alt.Chart(chart_df)
        .mark_bar()
        .encode(
            x=x_encoding,
            y=y_encoding,
            color=color_encoding,
            xOffset="serie:N",
            tooltip=[
                "competencia:N",
                "serie:N",
                alt.Tooltip(f"{value_field}:Q", format=",.2f"),
            ],
        )
        .properties(title=title, height=320)
    )
    labels = _bar_label_layer(
        chart_df,
        x_encoding=x_encoding,
        y_encoding=y_encoding,
        value_field=value_field,
        color_encoding=alt.Color("serie:N", legend=None, scale=alt.Scale(range=FIDC_CHART_COLORS)),
    )
    return _style_altair_chart(chart if labels is None else (chart + labels))


def _stacked_area_chart(
    chart_df: pd.DataFrame,
    *,
    title: str,
    value_column: str,
    y_title: str,
) -> alt.Chart:
    base_df = chart_df[["competencia", "competencia_dt", "label", value_column]].copy()
    base_df[value_column] = pd.to_numeric(base_df[value_column], errors="coerce")
    base_df = base_df.dropna(subset=[value_column])
    base_df = _altair_compatible_df(base_df)
    x_encoding = alt.X("competencia:N", title="Competência", sort=base_df["competencia"].drop_duplicates().tolist())
    y_encoding = alt.Y(f"{value_column}:Q", stack=True, title=y_title)
    color_encoding = alt.Color("label:N", title="Classe", scale=alt.Scale(range=FIDC_CHART_COLORS))
    chart = (
        alt.Chart(base_df)
        .mark_area(opacity=0.75)
        .encode(
            x=x_encoding,
            y=y_encoding,
            color=color_encoding,
            tooltip=["competencia:N", "label:N", alt.Tooltip(f"{value_column}:Q", format=",.2f")],
        )
        .properties(title=title, height=320)
    )
    if not _chart_labels_enabled():
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
        .configure_view(stroke=None)
        .configure_legend(labelColor="#5f6b7a", titleColor="#5f6b7a", orient="bottom")
    )


def _altair_compatible_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    output = df.copy()
    for column in output.columns:
        dtype_text = str(output[column].dtype)
        dtype_repr = repr(output[column].dtype)
        if dtype_text.startswith("string") or dtype_text == "str" or "StringDtype" in dtype_repr:
            output[column] = output[column].astype(object)
    return output


def _format_cnpj(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 14:
        return value or "N/D"
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


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
    if magnitude >= 1_000_000_000:
        return f"R$ {_format_decimal(numeric / 1_000_000_000, decimals=2)} bi"
    if magnitude >= 1_000_000:
        return f"R$ {_format_decimal(numeric / 1_000_000, decimals=1)} mi"
    if magnitude >= 1_000:
        return f"R$ {_format_decimal(numeric / 1_000, decimals=1)} mil"
    return f"R$ {_format_decimal(numeric, decimals=2)}"


def _render_result(result: InformeMensalResult, context: dict[str, Any]) -> None:
    contract_missing = _validate_result_contract(result)
    if contract_missing:
        st.warning("Contrato de dados parcial detectado. Alguns blocos podem ficar incompletos.")
        with st.expander("Diagnóstico de contrato de dados", expanded=True):
            st.json(contract_missing)

    docs_ok = _count_docs_by_status(result.docs_df, "ok")
    docs_error = _count_docs_by_status(result.docs_df, "erro")
    competencias = result.competencias

    col1, col2, col3 = st.columns(3)
    col1.metric("Competências", len(competencias))
    col2.metric("Documentos OK", docs_ok)
    col3.metric("Documentos com falha", docs_error)

    with result.excel_path.open("rb") as excel_fp:
        st.download_button(
            "Baixar Excel",
            data=excel_fp,
            file_name=f"fidc_ime_{context.get('request_id', 'execucao')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with result.audit_json_path.open("rb") as audit_fp:
        st.download_button(
            "Baixar auditoria (JSON)",
            data=audit_fp,
            file_name=f"auditoria_fidc_ime_{context.get('request_id', 'execucao')}.json",
            mime="application/json",
        )

    if docs_error:
        st.warning("Nem todos os documentos foram processados. O Excel foi gerado com os documentos válidos.")
        with st.expander("Diagnóstico de documentos com falha", expanded=True):
            failed_docs = (
                result.docs_df[result.docs_df["processamento"] == "erro"].copy()
                if "processamento" in result.docs_df.columns
                else result.docs_df.copy()
            )
            st.dataframe(failed_docs, use_container_width=True)
            st.download_button(
                "Baixar documentos com falha (CSV)",
                data=failed_docs.to_csv(index=False).encode("utf-8"),
                file_name=f"documentos_falha_fidc_ime_{context.get('request_id', 'execucao')}.csv",
                mime="text/csv",
            )

    _render_dashboard(result, context)

    max_preview_rows = 300
    with st.expander("Artefatos brutos da extração", expanded=False):
        st.caption(
            f"Pré-visualizações limitadas a {max_preview_rows} linhas para manter a sessão estável. "
            "Use o Excel para análise completa."
        )

        st.subheader("Documentos selecionados")
        st.dataframe(result.docs_df.head(max_preview_rows), use_container_width=True)
        if len(result.docs_df) > max_preview_rows:
            st.info(f"Exibindo {max_preview_rows} de {len(result.docs_df)} documentos.")

        st.subheader("Prévia do wide final")
        wide_preview_df = _read_csv_preview(result.wide_csv_path, max_preview_rows)
        st.dataframe(wide_preview_df, use_container_width=True)
        if result.wide_row_count > max_preview_rows:
            st.info(f"Exibindo {max_preview_rows} de {result.wide_row_count} linhas do wide final.")

        if result.listas_row_count > 0:
            st.subheader("Prévia das estruturas repetitivas")
            listas_preview_df = _read_csv_preview(result.listas_csv_path, max_preview_rows)
            st.dataframe(listas_preview_df, use_container_width=True)
            if result.listas_row_count > max_preview_rows:
                st.info(f"Exibindo {max_preview_rows} de {result.listas_row_count} linhas das estruturas repetitivas.")

        st.subheader("Auditoria")
        st.dataframe(result.audit_df.head(max_preview_rows), use_container_width=True)
        if len(result.audit_df) > max_preview_rows:
            st.info(f"Exibindo {max_preview_rows} de {len(result.audit_df)} eventos de auditoria.")
