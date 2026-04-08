from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import List

import pandas as pd

from services.fundonet_client import FundosNetClient, only_digits
from services.fundonet_errors import (
    DocumentDownloadError,
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


class InformeMensalService:
    def __init__(self, client: FundosNetClient | None = None) -> None:
        self.client = client or FundosNetClient()

    def run(self, cnpj_fundo: str, data_inicial: date, data_final: date) -> InformeMensalResult:
        cnpj = only_digits(cnpj_fundo)
        if not re.fullmatch(r"\d{14}", cnpj):
            raise InvalidCnpjError("CNPJ inválido: informe 14 dígitos.")
        if data_inicial > data_final:
            raise ValueError("Data inicial deve ser menor ou igual à data final.")

        resolution = self.client.resolve_fundo(cnpj)
        documentos = self.client.listar_documentos(
            cnpj_fundo=cnpj,
            data_inicial=self._to_br_date(data_inicial),
            data_final=self._to_br_date(data_final),
            id_fundo=resolution.id_fundo,
        )

        if not documentos:
            raise FundoNotFoundError(
                "Nenhum documento encontrado para o CNPJ/período informado. "
                "Isso pode indicar fundo inexistente, sem publicações ou bloqueio do provedor."
            )

        docs_target = [d for d in documentos if is_informe_mensal_estruturado(d)]
        if not docs_target:
            raise NoDocumentsFoundError(
                "Nenhum Informe Mensal Estruturado encontrado para o período informado."
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
                xml_bytes = self.client.download_documento(doc.id)
                conta_df = flatten_xml_contas(xml_bytes, doc_id=doc.id)
            except Exception as exc:
                raise DocumentDownloadError(
                    f"Falha ao processar documento {doc.id}: {exc}"
                ) from exc

            conta_df["data_referencia"] = doc.data_referencia
            conta_df["coluna_informe"] = doc.coluna_informe
            contas_frames.append(conta_df)

        contas_df = pd.concat(contas_frames, ignore_index=True) if contas_frames else pd.DataFrame()
        wide_df = build_wide_dataset(contas_df, docs_df)
        excel_bytes = build_excel_bytes(wide_df)
        return InformeMensalResult(docs_df=docs_df, contas_df=contas_df, wide_df=wide_df, excel_bytes=excel_bytes)

    @staticmethod
    def _to_br_date(dt: date) -> str:
        return dt.strftime("%d/%m/%Y")


def is_informe_mensal_estruturado(doc: DocumentoFundo) -> bool:
    text = " ".join([doc.categoria, doc.tipo, doc.especie, doc.nome_arquivo or ""]).upper()
    return "INFORME" in text and "MENSAL" in text and "ESTRUTUR" in text
