from __future__ import annotations

from datetime import date
import json

import pandas as pd
import streamlit as st

from services.fundonet_errors import FundosNetError
from services.fundonet_service import InformeMensalResult, InformeMensalService


def _init_progress_bar(initial_value: float, message: str):
    """Compatibilidade com versões antigas do Streamlit."""
    normalized = max(0.0, min(1.0, float(initial_value)))
    try:
        return st.progress(normalized, text=message)
    except TypeError:
        try:
            progress = st.progress(normalized)
        except Exception:  # noqa: BLE001
            progress = st.progress(int(round(normalized * 100)))
        st.caption(message)
        return progress


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

    progress = _init_progress_bar(0.0, "Preparando execução...")
    status_box = st.empty()

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
    except FundosNetError as exc:
        progress.empty()
        status_box.empty()
        st.error(str(exc))
        if exc.details:
            st.warning("Detalhes técnicos do erro:")
            st.json(exc.details)
        if exc.trace:
            audit_df = pd.DataFrame(exc.trace)
            st.subheader("Auditoria da falha")
            st.dataframe(audit_df, use_container_width=True)
            st.download_button(
                "Baixar auditoria da falha (JSON)",
                data=json.dumps(exc.trace, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name="auditoria_falha_fidc_ime.json",
                mime="application/json",
            )
        return
    except ValueError as exc:
        progress.empty()
        status_box.empty()
        st.error(str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        progress.empty()
        status_box.empty()
        st.error(f"Falha inesperada no processamento: {exc}")
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
