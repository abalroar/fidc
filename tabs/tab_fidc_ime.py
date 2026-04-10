from __future__ import annotations

from datetime import date, datetime
import json
import time
import traceback
from typing import Any
import uuid

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


def _extract_competencias(contas_df: pd.DataFrame) -> list[str]:
    if contas_df.empty or "competencia" not in contas_df.columns:
        return []
    return sorted(contas_df["competencia"].dropna().astype(str).unique().tolist())



def _validate_result_contract(result: InformeMensalResult) -> dict[str, list[str]]:
    contract = {
        "docs_df": ["documento_id", "competencia", "processamento", "erro_processamento"],
        "wide_df": ["tag", "descricao"],
        "audit_df": ["etapa", "status", "detalhe"],
    }
    missing: dict[str, list[str]] = {}
    for attr, required_cols in contract.items():
        df = getattr(result, attr)
        absent = [col for col in required_cols if col not in df.columns]
        if absent:
            missing[attr] = absent
    return missing


def _render_execution_observability(context: dict[str, Any], elapsed_seconds: float | None = None) -> None:
    st.caption(f"Execução: {context.get('request_id', 'N/D')}")
    with st.expander("Observabilidade da execução", expanded=False):
        payload = dict(context)
        if elapsed_seconds is not None:
            payload["duracao_segundos"] = round(elapsed_seconds, 3)
        st.json(payload)


def _render_result(result: InformeMensalResult, context: dict[str, Any]) -> None:
    contract_missing = _validate_result_contract(result)
    if contract_missing:
        st.warning("Contrato de dados parcial detectado. Alguns blocos podem ficar incompletos.")
        with st.expander("Diagnóstico de contrato de dados", expanded=True):
            st.json(contract_missing)

    docs_ok = _count_docs_by_status(result.docs_df, "ok")
    docs_error = _count_docs_by_status(result.docs_df, "erro")
    competencias = _extract_competencias(result.contas_df)

    col1, col2, col3 = st.columns(3)
    col1.metric("Competências", len(competencias))
    col2.metric("Documentos OK", docs_ok)
    col3.metric("Documentos com falha", docs_error)

    st.download_button(
        "Baixar Excel",
        data=result.excel_bytes,
        file_name=f"fidc_ime_{context.get('request_id', 'execucao')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.download_button(
        "Baixar auditoria (JSON)",
        data=_safe_json_bytes(result.audit_df.to_dict(orient="records")),
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

    max_preview_rows = 300
    st.caption(
        f"Pré-visualizações limitadas a {max_preview_rows} linhas para manter a sessão estável. "
        "Use o Excel para análise completa."
    )

    st.subheader("Documentos selecionados")
    st.dataframe(result.docs_df.head(max_preview_rows), use_container_width=True)
    if len(result.docs_df) > max_preview_rows:
        st.info(f"Exibindo {max_preview_rows} de {len(result.docs_df)} documentos.")

    st.subheader("Prévia do wide final")
    st.dataframe(result.wide_df.head(max_preview_rows), use_container_width=True)
    if len(result.wide_df) > max_preview_rows:
        st.info(f"Exibindo {max_preview_rows} de {len(result.wide_df)} linhas do wide final.")

    if not result.listas_df.empty:
        st.subheader("Prévia das estruturas repetitivas")
        st.dataframe(result.listas_df.head(max_preview_rows), use_container_width=True)
        if len(result.listas_df) > max_preview_rows:
            st.info(f"Exibindo {max_preview_rows} de {len(result.listas_df)} linhas das estruturas repetitivas.")

    st.subheader("Auditoria")
    st.dataframe(result.audit_df.head(max_preview_rows), use_container_width=True)
    if len(result.audit_df) > max_preview_rows:
        st.info(f"Exibindo {max_preview_rows} de {len(result.audit_df)} eventos de auditoria.")
