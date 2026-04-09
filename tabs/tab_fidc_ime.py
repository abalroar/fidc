from __future__ import annotations

from datetime import date, datetime
import json
import traceback
from typing import Any

import pandas as pd
import streamlit as st

from services.fundonet_errors import FundosNetError
from services.fundonet_service import InformeMensalResult, InformeMensalService


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
        "timestamp_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
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

    col1, col2 = st.columns(2)
    col1.metric("Tipo de erro", report["erro_tipo"])
    col2.metric("Timestamp (UTC)", report["timestamp_utc"])
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
        data=json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
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
    st.subheader("Informe Mensal Estruturado (Fundos.NET)")
    st.caption(
        "Informe um CNPJ de fundo FIDC, escolha um intervalo de competências e gere um Excel "
        "com uma coluna por mês. Somente o mês/ano das datas abaixo é considerado."
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
        context = {
            "cnpj_informado": cnpj_input,
            "competencia_inicial": competencia_inicial.isoformat(),
            "competencia_final": competencia_final.isoformat(),
        }
        _render_failure_diagnostics(exc, tb_text, context)
        return

    _update_progress_bar(progress, 1.0, "Concluído.")
    status_box.caption("Processamento concluído.")
    _render_result(result)


def _render_result(result: InformeMensalResult) -> None:
    docs_ok = int((result.docs_df["processamento"] == "ok").sum()) if not result.docs_df.empty else 0
    docs_error = int((result.docs_df["processamento"] == "erro").sum()) if not result.docs_df.empty else 0
    competencias = sorted(result.contas_df["competencia"].dropna().unique().tolist()) if not result.contas_df.empty else []

    col1, col2, col3 = st.columns(3)
    col1.metric("Competências", len(competencias))
    col2.metric("Documentos OK", docs_ok)
    col3.metric("Documentos com falha", docs_error)

    if docs_error:
        st.warning("Nem todos os documentos foram processados. O Excel foi gerado com os documentos válidos.")
        with st.expander("Diagnóstico de documentos com falha", expanded=True):
            failed_docs = result.docs_df[result.docs_df["processamento"] == "erro"].copy()
            st.dataframe(failed_docs, use_container_width=True)
            st.download_button(
                "Baixar documentos com falha (CSV)",
                data=failed_docs.to_csv(index=False).encode("utf-8"),
                file_name="documentos_falha_fidc_ime.csv",
                mime="text/csv",
            )

    st.subheader("Documentos selecionados")
    st.dataframe(result.docs_df, use_container_width=True)

    st.subheader("Prévia do wide final")
    st.dataframe(result.wide_df, use_container_width=True)

    if not result.listas_df.empty:
        st.subheader("Prévia das estruturas repetitivas")
        st.dataframe(result.listas_df, use_container_width=True)

    st.subheader("Auditoria")
    st.dataframe(result.audit_df, use_container_width=True)

    st.download_button(
        "Baixar Excel",
        data=result.excel_bytes,
        file_name="fidc_ime.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.download_button(
        "Baixar auditoria (JSON)",
        data=json.dumps(result.audit_df.to_dict(orient="records"), ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="auditoria_fidc_ime.json",
        mime="application/json",
    )
