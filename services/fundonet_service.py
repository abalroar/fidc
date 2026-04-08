from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import List

import pandas as pd

from services.fundonet_client import FundosNetClient, only_digits
from services.fundonet_errors import (
    DocumentDownloadError,
    FundosNetError,
    FundoNotFoundError,
    InvalidCnpjError,
    NoDocumentsFoundError,
)
from services.fundonet_export import build_excel_bytes, build_wide_dataset
from services.fundonet_models import DocumentoFundo
from services.fundonet_parser import flatten_xml_contas


@dataclass(frozen=True)
class InformeMensalResult:
    docs_df: pd.DataFrame
    contas_df: pd.DataFrame
    wide_df: pd.DataFrame
    excel_bytes: bytes
    audit_df: pd.DataFrame


class InformeMensalService:
    def __init__(self, client: FundosNetClient | None = None) -> None:
        self.client = client or FundosNetClient()

    def run(self, cnpj_fundo: str, data_inicial: date, data_final: date) -> InformeMensalResult:
        audit_rows: List[dict] = []

        def add_audit(etapa: str, status: str, detalhe: str, extra: dict | None = None) -> None:
            row = {"etapa": etapa, "status": status, "detalhe": detalhe}
            if extra:
                row.update(extra)
            audit_rows.append(row)

        cnpj = only_digits(cnpj_fundo)
        if not re.fullmatch(r"\d{14}", cnpj):
            raise InvalidCnpjError("CNPJ inválido: informe 14 dígitos.")
        if data_inicial > data_final:
            raise ValueError("Data inicial deve ser menor ou igual à data final.")

        add_audit("validacao_entrada", "ok", "Entrada validada.", {"cnpj_fundo": cnpj})
        try:
            resolution = self.client.resolve_fundo(cnpj)
            add_audit(
                "resolve_fundo",
                "ok",
                "Resolução de fundo executada.",
                {"id_fundo": resolution.id_fundo or ""},
            )
            documentos = self.client.listar_documentos(
                cnpj_fundo=cnpj,
                data_inicial=self._to_br_date(data_inicial),
                data_final=self._to_br_date(data_final),
                id_fundo=resolution.id_fundo,
            )
            add_audit(
                "listar_documentos",
                "ok",
                "Listagem de documentos concluída.",
                {"qtd_documentos_brutos": len(documentos)},
            )
        except (InvalidCnpjError, ValueError):
            raise
        except FundosNetError as exc:
            details = exc.details
            add_audit("integracao", "erro", str(exc), details)
            current_trace = list(exc.trace)
            current_trace.extend(audit_rows)
            raise exc.__class__(
                str(exc),
                details=details,
                trace=current_trace,
            ) from exc
        except Exception as exc:
            add_audit("integracao", "erro", str(exc))
            raise DocumentDownloadError(
                f"Falha de integração não mapeada: {exc}",
                trace=audit_rows,
            ) from exc

        if not documentos:
            raise FundoNotFoundError(
                "Nenhum documento encontrado para o CNPJ/período informado. "
                "Isso pode indicar fundo inexistente, sem publicações ou bloqueio do provedor.",
                trace=audit_rows,
            )

        docs_target = [d for d in documentos if is_informe_mensal_estruturado(d)]
        add_audit("filtrar_informes", "ok", "Filtro de Informe Mensal Estruturado aplicado.", {"qtd_informes": len(docs_target)})
        if not docs_target:
            raise NoDocumentsFoundError(
                "Nenhum Informe Mensal Estruturado encontrado para o período informado.",
                trace=audit_rows,
            )

        docs_target = sorted(
            docs_target,
            key=lambda d: (d.periodo_ordenacao, d.data_entrega or "", d.id),
        )

        docs_df = pd.DataFrame(
            [
                {
                    "id": d.id,
                    "categoria": d.categoria,
                    "tipo": d.tipo,
                    "especie": d.especie,
                    "data_referencia": d.data_referencia,
                    "data_entrega": d.data_entrega,
                    "nome_arquivo": d.nome_arquivo,
                    "coluna_informe": d.coluna_informe,
                }
                for d in docs_target
            ]
        )

        contas_frames: List[pd.DataFrame] = []
        for doc in docs_target:
            try:
                add_audit("download_documento", "iniciado", "Iniciando download.", {"documento_id": doc.id})
                xml_bytes = self.client.download_documento(doc.id)
                conta_df = flatten_xml_contas(xml_bytes, doc_id=doc.id)
                add_audit("parse_documento", "ok", "Documento processado.", {"documento_id": doc.id, "linhas_extraidas": len(conta_df)})
            except Exception as exc:
                raise DocumentDownloadError(
                    f"Falha ao processar documento {doc.id}: {exc}",
                    trace=audit_rows,
                ) from exc

            conta_df["data_referencia"] = doc.data_referencia
            conta_df["coluna_informe"] = doc.coluna_informe
            contas_frames.append(conta_df)

        contas_df = pd.concat(contas_frames, ignore_index=True) if contas_frames else pd.DataFrame()
        wide_df = build_wide_dataset(contas_df, docs_df)
        excel_bytes = build_excel_bytes(wide_df)
        add_audit("montagem_dataset", "ok", "Dataset final e excel gerados.", {"linhas_wide": len(wide_df)})
        audit_df = pd.DataFrame(audit_rows)
        return InformeMensalResult(
            docs_df=docs_df,
            contas_df=contas_df,
            wide_df=wide_df,
            excel_bytes=excel_bytes,
            audit_df=audit_df,
        )

    @staticmethod
    def _to_br_date(dt: date) -> str:
        return dt.strftime("%d/%m/%Y")


def is_informe_mensal_estruturado(doc: DocumentoFundo) -> bool:
    text = " ".join([doc.categoria, doc.tipo, doc.especie, doc.nome_arquivo or ""]).upper()
    return "INFORME" in text and "MENSAL" in text and "ESTRUTUR" in text
