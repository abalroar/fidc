from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Iterable

import pandas as pd

from services.fundonet_client import FundosNetClient, only_digits
from services.fundonet_errors import (
    DocumentDownloadError,
    DocumentParseError,
    FundosNetError,
    FundoNotFoundError,
    InvalidCnpjError,
    NoDocumentsFoundError,
)
from services.fundonet_export import build_excel_bytes, build_wide_dataset
from services.fundonet_models import DocumentoFundo
from services.fundonet_parser import ParsedInformeXml, parse_informe_mensal_xml


ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class InformeMensalResult:
    docs_df: pd.DataFrame
    contas_df: pd.DataFrame
    listas_df: pd.DataFrame
    wide_df: pd.DataFrame
    excel_bytes: bytes
    audit_df: pd.DataFrame


class InformeMensalService:
    def __init__(self, client: FundosNetClient | None = None) -> None:
        self.client = client or FundosNetClient()

    def run(
        self,
        cnpj_fundo: str,
        data_inicial: date,
        data_final: date,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> InformeMensalResult:
        audit_rows: list[dict] = []

        def add_audit(etapa: str, status: str, detalhe: str, **extra: object) -> None:
            audit_rows.append({"etapa": etapa, "status": status, "detalhe": detalhe, **extra})

        cnpj = only_digits(cnpj_fundo)
        if not re.fullmatch(r"\d{14}", cnpj):
            raise InvalidCnpjError("CNPJ inválido: informe 14 dígitos.")

        competencia_inicial = _to_competencia(data_inicial)
        competencia_final = _to_competencia(data_final)
        if competencia_inicial > competencia_final:
            raise ValueError("Competência inicial deve ser menor ou igual à competência final.")

        add_audit(
            "validacao_entrada",
            "ok",
            "Entrada validada.",
            cnpj_fundo=cnpj,
            competencia_inicial=competencia_inicial.strftime("%m/%Y"),
            competencia_final=competencia_final.strftime("%m/%Y"),
        )
        _report_progress(progress_callback, 0, 1, "Abrindo contexto público do fundo...")

        try:
            resolution = self.client.resolve_fundo(cnpj)
            add_audit(
                "resolve_fundo",
                "ok",
                "Contexto público do fundo carregado.",
                id_fundo=resolution.id_fundo or "",
                nome_fundo=resolution.nome_fundo or "",
            )
            raw_documentos = self.client.listar_documentos_ime(cnpj)
            add_audit(
                "listar_documentos",
                "ok",
                "Listagem pública de IMEs concluída.",
                qtd_documentos_brutos=len(raw_documentos),
            )
        except (InvalidCnpjError, ValueError):
            raise
        except FundosNetError as exc:
            current_trace = list(exc.trace)
            current_trace.extend(audit_rows)
            raise exc.__class__(str(exc), details=exc.details, trace=current_trace) from exc

        if not raw_documentos:
            # Probe for any document type to give a more actionable error.
            outros_docs = self.client.probe_documentos_disponiveis(cnpj)
            tipos_disponiveis = sorted({f"{d['categoria']} / {d['tipo']}" for d in outros_docs if d["tipo"]})
            add_audit(
                "probe_documentos_disponiveis",
                "ok" if outros_docs else "aviso",
                (
                    f"Sondagem sem filtro IME: {len(outros_docs)} documento(s) de outro(s) tipo(s) encontrado(s)."
                    if outros_docs
                    else "Sondagem sem filtro IME: nenhum documento de nenhum tipo encontrado para este CNPJ."
                ),
                tipos_disponiveis=tipos_disponiveis,
            )
            if outros_docs:
                msg = (
                    "O CNPJ informado possui documentos no Fundos.NET, mas nenhum é do tipo "
                    f"'Informe Mensal Estruturado' (categoria 6 / tipo 40). "
                    f"Tipos encontrados: {', '.join(tipos_disponiveis) or 'desconhecido'}. "
                    "Verifique se o CNPJ corresponde ao fundo correto ou se os informes são "
                    "arquivados sob o CNPJ do fundo-mestre."
                )
                exc_cls = NoDocumentsFoundError
            else:
                msg = (
                    "Nenhum documento foi encontrado para este CNPJ no Fundos.NET. "
                    "Possíveis causas: (1) CNPJ não corresponde a um FIDC registrado; "
                    "(2) o fundo arquiva seus informes sob o CNPJ do fundo-mestre — "
                    "tente o CNPJ do fundo principal; "
                    "(3) o fundo ainda não entregou documentos na plataforma."
                )
                exc_cls = FundoNotFoundError if resolution.id_fundo is None else NoDocumentsFoundError
            raise exc_cls(msg, trace=audit_rows)

        documentos_no_intervalo = [
            doc
            for doc in raw_documentos
            if doc.competencia is not None and competencia_inicial <= doc.competencia <= competencia_final
        ]
        add_audit(
            "filtrar_intervalo_competencia",
            "ok",
            "Filtro local por competência aplicado.",
            qtd_documentos_intervalo=len(documentos_no_intervalo),
        )
        if not documentos_no_intervalo:
            raise NoDocumentsFoundError(
                "Nenhum Informe Mensal Estruturado encontrado no intervalo de competências informado.",
                trace=audit_rows,
            )

        documentos_selecionados = select_latest_documents(documentos_no_intervalo)
        documentos_selecionados = sorted(
            documentos_selecionados,
            key=lambda doc: (doc.competencia or date.min, doc.data_entrega_dt or datetime.min, doc.id),
        )
        add_audit(
            "deduplicar_retificacoes",
            "ok",
            "Documentos definitivos por competência selecionados.",
            qtd_competencias=len(documentos_selecionados),
        )

        scalar_frames: list[pd.DataFrame] = []
        list_frames: list[pd.DataFrame] = []
        docs_status_rows: list[dict[str, object]] = []

        total_docs = len(documentos_selecionados)
        for index, doc in enumerate(documentos_selecionados, start=1):
            competencia = doc.competencia_label or doc.data_referencia or ""
            _report_progress(progress_callback, index - 1, total_docs, f"Processando {competencia} ({index}/{total_docs})...")
            add_audit(
                "processar_documento",
                "iniciado",
                "Iniciando download e parse do documento.",
                documento_id=doc.id,
                competencia=competencia,
                versao=doc.versao,
                data_entrega=doc.data_entrega or "",
                status_documento=doc.status,
            )
            try:
                xml_bytes = self.client.download_documento(doc.id)
                parsed = parse_informe_mensal_xml(xml_bytes, doc_id=doc.id)
                scalar_df, list_df = self._decorate_parsed_frames(parsed, doc)
                scalar_frames.append(scalar_df)
                list_frames.append(list_df)
                docs_status_rows.append(
                    self._build_doc_status_row(
                        doc,
                        processamento="ok",
                        erro="",
                        competencia_xml=parsed.metadata.get("competencia_xml"),
                        xml_version=parsed.metadata.get("xml_version"),
                    )
                )
                if parsed.metadata.get("competencia_xml") and parsed.metadata.get("competencia_xml") != competencia:
                    add_audit(
                        "validar_competencia_xml",
                        "aviso",
                        "Competência do XML diverge da listagem.",
                        documento_id=doc.id,
                        competencia_listagem=competencia,
                        competencia_xml=parsed.metadata.get("competencia_xml"),
                    )
                add_audit(
                    "processar_documento",
                    "ok",
                    "Documento processado com sucesso.",
                    documento_id=doc.id,
                    competencia=competencia,
                    linhas_escalares=len(scalar_df),
                    linhas_lista=len(list_df),
                )
            except Exception as exc:  # noqa: BLE001
                docs_status_rows.append(
                    self._build_doc_status_row(
                        doc,
                        processamento="erro",
                        erro=str(exc),
                        competencia_xml=None,
                        xml_version=None,
                    )
                )
                add_audit(
                    "processar_documento",
                    "erro",
                    f"Falha ao processar documento {doc.id}: {exc}",
                    documento_id=doc.id,
                    competencia=competencia,
                )
                continue

        docs_df = pd.DataFrame(docs_status_rows)
        contas_base_df = pd.concat(scalar_frames, ignore_index=True) if scalar_frames else pd.DataFrame()
        listas_df = pd.concat(list_frames, ignore_index=True) if list_frames else pd.DataFrame()

        if contas_base_df.empty:
            raise DocumentParseError(
                "Todos os documentos selecionados falharam no download ou parse.",
                trace=audit_rows,
            )

        contas_df = self._build_tidy_contract(contas_base_df=contas_base_df, cnpj_fundo=cnpj)
        competencias_ordenadas = [doc.competencia_label for doc in documentos_selecionados if doc.competencia_label]
        competencias_ordenadas = _dedupe_preserve_order([c for c in competencias_ordenadas if c])
        wide_df = build_wide_dataset(contas_df, competencias_ordenadas)
        add_audit(
            "montagem_dataset",
            "ok",
            "Dataframes e Excel gerados.",
            linhas_escalares=len(contas_df),
            linhas_lista=len(listas_df),
            linhas_wide=len(wide_df),
        )
        audit_df = pd.DataFrame(audit_rows)
        excel_bytes = build_excel_bytes(wide_df, listas_df, docs_df, audit_df)
        _report_progress(progress_callback, total_docs, total_docs, "Concluído.")
        return InformeMensalResult(
            docs_df=docs_df,
            contas_df=contas_df,
            listas_df=listas_df,
            wide_df=wide_df,
            excel_bytes=excel_bytes,
            audit_df=audit_df,
        )

    @staticmethod
    def _decorate_parsed_frames(parsed: ParsedInformeXml, doc: DocumentoFundo) -> tuple[pd.DataFrame, pd.DataFrame]:
        competencia = doc.competencia_label or parsed.metadata.get("competencia_xml") or doc.data_referencia

        scalar_df = parsed.scalar_df.copy()
        if scalar_df.empty:
            scalar_df = pd.DataFrame(columns=parsed.scalar_df.columns.tolist())
        scalar_df["competencia"] = competencia
        scalar_df["data_entrega"] = doc.data_entrega
        scalar_df["versao_documento"] = doc.versao
        scalar_df["status_documento"] = doc.status

        list_df = parsed.list_df.copy()
        if list_df.empty:
            list_df = pd.DataFrame(columns=parsed.list_df.columns.tolist())
        list_df["competencia"] = competencia
        list_df["data_entrega"] = doc.data_entrega
        list_df["versao_documento"] = doc.versao
        list_df["status_documento"] = doc.status
        return scalar_df, list_df

    @staticmethod
    def _build_doc_status_row(
        doc: DocumentoFundo,
        *,
        processamento: str,
        erro: str,
        competencia_xml: str | None,
        xml_version: str | None,
    ) -> dict[str, object]:
        return {
            "documento_id": doc.id,
            "competencia": doc.competencia_label or doc.data_referencia,
            "data_referencia": doc.data_referencia,
            "competencia_xml": competencia_xml,
            "data_entrega": doc.data_entrega,
            "versao": doc.versao,
            "status_documento": doc.status,
            "categoria": doc.categoria,
            "tipo": doc.tipo,
            "especie": doc.especie,
            "fundo_ou_classe": doc.fundo_ou_classe,
            "nome_fundo": doc.nome_fundo,
            "xml_version": xml_version,
            "processamento": processamento,
            "erro_processamento": erro,
        }

    @staticmethod
    def _build_tidy_contract(contas_base_df: pd.DataFrame, cnpj_fundo: str) -> pd.DataFrame:
        base_columns = [
            "cnpj_fundo",
            "documento_id",
            "competencia",
            "bloco",
            "sub_bloco",
            "tag",
            "tag_path",
            "descricao",
            "valor_raw",
            "valor_num",
            "fonte",
        ]
        if contas_base_df.empty:
            return pd.DataFrame(columns=base_columns)

        required_columns = [
            "documento_id",
            "competencia",
            "bloco",
            "sub_bloco",
            "tag",
            "tag_path",
            "descricao",
            "valor_raw",
            "valor_num",
            "ordem_xml",
            "valor_excel",
        ]
        missing_columns = [column for column in required_columns if column not in contas_base_df.columns]
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise ValueError(f"Contrato inválido do parser: colunas ausentes em contas_base_df: {missing}")

        tidy_df = contas_base_df.copy()
        tidy_df["cnpj_fundo"] = cnpj_fundo
        tidy_df["fonte"] = "fundonet"
        extra_columns = [column for column in tidy_df.columns if column not in base_columns]
        return tidy_df[base_columns + extra_columns]


def select_latest_documents(documentos: Iterable[DocumentoFundo]) -> list[DocumentoFundo]:
    grouped: dict[str, list[DocumentoFundo]] = {}
    for doc in documentos:
        if not doc.competencia_label:
            continue
        grouped.setdefault(doc.competencia_label, []).append(doc)

    selected: list[DocumentoFundo] = []
    for competencia, docs in grouped.items():
        best = max(
            docs,
            key=lambda doc: (
                1 if doc.is_active else 0,
                doc.versao,
                doc.data_entrega_dt or datetime.min,
                doc.id,
            ),
        )
        selected.append(best)
    return selected


def is_informe_mensal_estruturado(doc: DocumentoFundo) -> bool:
    text = " ".join([doc.categoria, doc.tipo, doc.especie, doc.nome_arquivo or ""]).upper()
    return "INFORME" in text and "MENSAL" in text and "ESTRUTUR" in text


def _to_competencia(raw_date: date) -> date:
    return date(raw_date.year, raw_date.month, 1)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _report_progress(callback: ProgressCallback | None, current: int, total: int, message: str) -> None:
    if callback is None:
        return
    callback(current, total, message)
