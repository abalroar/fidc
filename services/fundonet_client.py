from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from services.fundonet_errors import (
    AuthenticationRequiredError,
    ProviderUnavailableError,
)
from services.fundonet_models import DocumentoFundo, FundoResolution


BASE_URL = "https://fnet.bmfbovespa.com.br/fnet/publico"


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


class FundosNetClient:
    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        retry = Retry(
            total=2,
            backoff_factor=0.7,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    def _url(self, path: str) -> str:
        return f"{BASE_URL}/{path.lstrip('/')}"

    def resolve_fundo(self, cnpj_fundo: str) -> FundoResolution:
        cnpj = only_digits(cnpj_fundo)
        response = self.session.get(
            self._url("abrirGerenciadorDocumentosCVM"),
            params={"cnpjFundo": cnpj},
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"Fundos.NET indisponível ao abrir gerenciador (HTTP {response.status_code}).",
                details={
                    "etapa": "resolve_fundo",
                    "endpoint": "abrirGerenciadorDocumentosCVM",
                    "http_status": response.status_code,
                    "cnpj_fundo": cnpj,
                },
            )

        html = response.text
        patterns = [
            r'class="fundoItemInicial"[^>]*data-id="(\d+)"',
            r'id="idFundo"[^>]*value="(\d+)"',
            r'"idFundo"\s*:\s*"?(\d+)"?',
        ]
        id_fundo: Optional[str] = None
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                id_fundo = match.group(1)
                break

        return FundoResolution(cnpj=cnpj, id_fundo=id_fundo)

    def listar_documentos(
        self,
        cnpj_fundo: str,
        data_inicial: str,
        data_final: str,
        id_fundo: Optional[str],
        tipo_fundo: str = "0",
        page_size: int = 200,
    ) -> List[DocumentoFundo]:
        draw = 1
        start = 0
        documentos: List[DocumentoFundo] = []

        while True:
            params = {
                "draw": draw,
                "start": start,
                "length": page_size,
                "tipoFundo": tipo_fundo,
                "idFundo": id_fundo or "",
                "cnpj": "",
                "cnpjFundo": only_digits(cnpj_fundo),
                "idCategoriaDocumento": "",
                "idTipoDocumento": "",
                "idEspecieDocumento": "",
                "dataReferencia": "",
                "dataInicial": data_inicial,
                "dataFinal": data_final,
                "idModalidade": "",
                "palavraChave": "",
            }
            response = self.session.get(
                self._url("pesquisarGerenciadorDocumentosDados"),
                params=params,
                timeout=self.timeout_seconds,
            )
            if response.status_code in (401, 403):
                raise AuthenticationRequiredError(
                    f"Listagem bloqueada pelo provedor (HTTP {response.status_code}).",
                    details={
                        "etapa": "listar_documentos",
                        "endpoint": "pesquisarGerenciadorDocumentosDados",
                        "http_status": response.status_code,
                        "draw": draw,
                        "start": start,
                    },
                )
            if response.status_code >= 500:
                raise ProviderUnavailableError(
                    "Listagem de documentos retornou erro interno no provedor "
                    f"(HTTP {response.status_code}).",
                    details={
                        "etapa": "listar_documentos",
                        "endpoint": "pesquisarGerenciadorDocumentosDados",
                        "http_status": response.status_code,
                        "draw": draw,
                        "start": start,
                        "cnpj_fundo": only_digits(cnpj_fundo),
                        "id_fundo": id_fundo or "",
                    },
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderUnavailableError(
                    "Resposta inesperada do provedor na listagem de documentos.",
                    details={
                        "etapa": "listar_documentos",
                        "endpoint": "pesquisarGerenciadorDocumentosDados",
                        "http_status": response.status_code,
                        "content_type": response.headers.get("content-type", ""),
                    },
                ) from exc

            data = payload.get("data", []) or []
            if not data:
                break

            for item in data:
                try:
                    doc_id = int(item["id"])
                except (KeyError, ValueError, TypeError):
                    continue
                documentos.append(
                    DocumentoFundo(
                        id=doc_id,
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
        response = self.session.get(
            self._url("downloadDocumento"),
            params={"id": doc_id},
            timeout=self.timeout_seconds,
        )
        if response.status_code in (401, 403):
            raise AuthenticationRequiredError(
                f"Download bloqueado (HTTP {response.status_code}) para documento {doc_id}.",
                details={
                    "etapa": "download_documento",
                    "endpoint": "downloadDocumento",
                    "http_status": response.status_code,
                    "documento_id": doc_id,
                },
            )
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"Provedor indisponível no download do documento {doc_id} (HTTP {response.status_code}).",
                details={
                    "etapa": "download_documento",
                    "endpoint": "downloadDocumento",
                    "http_status": response.status_code,
                    "documento_id": doc_id,
                },
            )
        return response.content


def _first_present(item: Dict[str, Any], candidates: List[str]) -> Optional[str]:
    for key in candidates:
        val = item.get(key)
        if val not in (None, ""):
            return str(val)
    return None
