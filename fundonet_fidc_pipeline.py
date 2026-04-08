from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import xml.etree.ElementTree as ET

import pandas as pd
import requests


BASE_URL = "https://fnet.bmfbovespa.com.br/fnet/publico"


@dataclass(frozen=True)
class DocumentoFundo:
    id: int
    categoria: str
    tipo: str
    especie: str
    data_referencia: Optional[str]
    data_entrega: Optional[str]
    nome_arquivo: Optional[str]
    raw: Dict[str, Any]


class FundosNetClient:
    """Cliente para listagem e download de documentos públicos do Fundos.NET."""

    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    def _url(self, path: str) -> str:
        return f"{BASE_URL}/{path.lstrip('/')}"

    def resolve_id_fundo(self, cnpj_fundo: str) -> Optional[str]:
        """Extrai idFundo da página pública pelo data-id da .fundoItemInicial."""
        r = self.session.get(
            self._url("abrirGerenciadorDocumentosCVM"),
            params={"cnpjFundo": only_digits(cnpj_fundo)},
            timeout=self.timeout,
        )
        r.raise_for_status()
        match = re.search(r'class="fundoItemInicial"[^>]*data-id="(\d+)"', r.text)
        return match.group(1) if match else None

    def listar_documentos(
        self,
        cnpj_fundo: str,
        data_inicial: str,
        data_final: str,
        tipo_fundo: str = "0",
        page_size: int = 200,
    ) -> List[DocumentoFundo]:
        """Itera paginação DataTables do pesquisarGerenciadorDocumentosDados."""
        draw = 1
        start = 0
        cnpj_digits = only_digits(cnpj_fundo)
        documentos: List[DocumentoFundo] = []

        while True:
            params = {
                "draw": draw,
                "start": start,
                "length": page_size,
                "tipoFundo": tipo_fundo,
                "idFundo": "",
                "cnpj": "",
                "cnpjFundo": cnpj_digits,
                "idCategoriaDocumento": "",
                "idTipoDocumento": "",
                "idEspecieDocumento": "",
                "dataReferencia": "",
                "dataInicial": data_inicial,
                "dataFinal": data_final,
                "idModalidade": "",
                "palavraChave": "",
            }
            r = self.session.get(
                self._url("pesquisarGerenciadorDocumentosDados"),
                params=params,
                timeout=self.timeout,
            )
            r.raise_for_status()
            payload = r.json()
            data = payload.get("data", []) or []
            if not data:
                break

            for item in data:
                documentos.append(
                    DocumentoFundo(
                        id=int(item["id"]),
                        categoria=str(item.get("categoriaDocumento", "")),
                        tipo=str(item.get("tipoDocumento", "")),
                        especie=str(item.get("especieDocumento", "")),
                        data_referencia=_first_present(item, ["dataReferencia", "dtReferencia"]),
                        data_entrega=_first_present(item, ["dataEntrega", "dtEntrega"]),
                        nome_arquivo=_first_present(item, ["nomeArquivo", "nmArquivo"]),
                        raw=item,
                    )
                )

            start += page_size
            draw += 1
            total = int(payload.get("recordsFiltered", len(documentos)))
            if start >= total:
                break

        return documentos

    def download_documento(self, doc_id: int) -> bytes:
        r = self.session.get(
            self._url("downloadDocumento"),
            params={"id": doc_id},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.content


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def parse_period_label(label: str) -> datetime:
    """Aceita Jan-25, 01/2025, 2025-01 etc e converte para primeiro dia do mês."""
    s = (label or "").strip()
    for fmt in ("%b-%y", "%m/%Y", "%Y-%m", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return datetime(dt.year, dt.month, 1)
        except ValueError:
            continue
    raise ValueError(f"Período inválido: {label!r}")


def to_br_date(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y")


def is_informe_mensal_estruturado(doc: DocumentoFundo) -> bool:
    text = " ".join([doc.categoria, doc.tipo, doc.especie]).upper()
    return "INFORME" in text and "MENSAL" in text and "ESTRUTUR" in text


def flatten_xml_contas(xml_content: bytes, doc_id: int) -> pd.DataFrame:
    root = ET.fromstring(xml_content)
    rows: List[Dict[str, Any]] = []

    def walk(node: ET.Element, trail: List[str], attrs: Dict[str, str]) -> None:
        tag = _strip_ns(node.tag)
        current_attrs = dict(attrs)
        for k, v in node.attrib.items():
            current_attrs[_strip_ns(k)] = v

        ident = (
            current_attrs.get("codigoConta")
            or current_attrs.get("codigo")
            or current_attrs.get("codConta")
            or ""
        )
        label = (
            current_attrs.get("descricaoConta")
            or current_attrs.get("descricao")
            or current_attrs.get("nomeConta")
            or current_attrs.get("nome")
            or tag
        )

        path_chunk = f"{ident} - {label}".strip(" -")
        next_trail = trail + [path_chunk]

        text = (node.text or "").strip()
        numeric = _parse_br_number(text)
        if numeric is not None:
            rows.append(
                {
                    "documento_id": doc_id,
                    "conta_codigo": ident,
                    "conta_descricao": label,
                    "conta_caminho": " > ".join(next_trail),
                    "valor": numeric,
                }
            )

        for child in list(node):
            walk(child, next_trail, current_attrs)

    walk(root, [], {})
    return pd.DataFrame(rows)


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_br_number(value: str) -> Optional[float]:
    if not value:
        return None
    normalized = value.replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _first_present(item: Dict[str, Any], candidates: Iterable[str]) -> Optional[str]:
    for key in candidates:
        val = item.get(key)
        if val not in (None, ""):
            return str(val)
    return None


def run_pipeline(cnpj_fundo: str, periodo_inicio: str, periodo_fim: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    inicio = parse_period_label(periodo_inicio)
    fim = parse_period_label(periodo_fim)

    if inicio > fim:
        raise ValueError("periodo_inicio deve ser <= periodo_fim")

    client = FundosNetClient()
    docs = client.listar_documentos(
        cnpj_fundo=cnpj_fundo,
        data_inicial=to_br_date(inicio),
        data_final=to_br_date(fim),
    )
    docs_target = [d for d in docs if is_informe_mensal_estruturado(d)]

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
            }
            for d in docs_target
        ]
    )
    docs_df.to_csv(output_dir / "documentos_filtrados.csv", index=False)

    frames = []
    for d in docs_target:
        xml_bytes = client.download_documento(d.id)
        xml_path = output_dir / f"{d.id}.xml"
        xml_path.write_bytes(xml_bytes)

        conta_df = flatten_xml_contas(xml_bytes, doc_id=d.id)
        conta_df["data_referencia"] = d.data_referencia
        conta_df["fundo_cnpj"] = only_digits(cnpj_fundo)
        frames.append(conta_df)

    contas_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    contas_df.to_csv(output_dir / "contas_empilhadas.csv", index=False)

    xlsx = output_dir / "fidc_informes_mensais_estruturados.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        docs_df.to_excel(writer, index=False, sheet_name="documentos")
        contas_df.to_excel(writer, index=False, sheet_name="contas")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Pipeline Fundos.NET: lista documentos, baixa XML de Informes Mensais "
            "Estruturados de FIDC e empilha contas em CSV/XLSX."
        )
    )
    parser.add_argument("--cnpj-fundo", required=True, help="CNPJ do fundo (com ou sem máscara)")
    parser.add_argument("--periodo-inicio", required=True, help="Ex: Jan-25, 01/2025 ou 2025-01")
    parser.add_argument("--periodo-fim", required=True, help="Ex: Jan-26, 01/2026 ou 2026-01")
    parser.add_argument("--output-dir", default="saida_fundonet", help="Diretório de saída")
    args = parser.parse_args()

    run_pipeline(
        cnpj_fundo=args.cnpj_fundo,
        periodo_inicio=args.periodo_inicio,
        periodo_fim=args.periodo_fim,
        output_dir=Path(args.output_dir),
    )


if __name__ == "__main__":
    main()
