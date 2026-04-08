from __future__ import annotations

import re
import json
import time
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
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        self.csrf_token: Optional[str] = None
        self.referer_url: Optional[str] = None

    def _url(self, path: str) -> str:
        return f"{BASE_URL}/{path.lstrip('/')}"

    def resolve_fundo(self, cnpj_fundo: str) -> FundoResolution:
        cnpj = only_digits(cnpj_fundo)
        self._bootstrap_context(cnpj)
        params = {
            "term": cnpj,
            "page": 1,
            "idTipoFundo": 0,
            "idAdm": 0,
            "paraCerts": "false",
        }
        response = self.session.get(
            self._url("listarFundos"),
            params=params,
            headers=self._headers_with_csrf(),
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"Fundos.NET indisponível ao listar fundos (HTTP {response.status_code}).",
                details={
                    "etapa": "resolve_fundo",
                    "endpoint": "listarFundos",
                    "http_status": response.status_code,
                    "cnpj_fundo": cnpj,
                },
            )
        try:
            payload = response.json()
            results = payload.get("results", [])
        except ValueError as exc:
            raise ProviderUnavailableError(
                "Resposta inesperada do provedor na resolução do fundo.",
                details={
                    "etapa": "resolve_fundo",
                    "endpoint": "listarFundos",
                    "http_status": response.status_code,
                },
            ) from exc

        id_fundo = str(results[0]["id"]) if results else None
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
        start = 0
        draw = 1
        documentos: List[DocumentoFundo] = []
        self._bootstrap_context(only_digits(cnpj_fundo))

        while True:
            params = {
                "d": draw,
                "s": start,
                "l": page_size,
                "q": "",
                "o": json.dumps([{"dataEntrega": "desc"}]),
                "tipoFundo": tipo_fundo,
                "administrador": "0",
                "idFundo": id_fundo or "",
                "cnpj": only_digits(cnpj_fundo),
                "cnpjFundo": only_digits(cnpj_fundo),
                "idCategoriaDocumento": "0",
                "idTipoDocumento": "0",
                "idEspecieDocumento": "0",
                "dataReferencia": "",
                "ultimaDataReferencia": "false",
                "dataInicial": data_inicial,
                "dataFinal": data_final,
                "idModalidade": "0",
                "palavraChave": "",
            }
            response = self.session.get(
                self._url("pesquisarGerenciadorDocumentosDados"),
                params=params,
                headers=self._headers_with_csrf(),
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
            if payload.get("msg"):
                raise ProviderUnavailableError(
                    f"Listagem rejeitada pelo provedor: {payload.get('msg')}",
                    details={
                        "etapa": "listar_documentos",
                        "endpoint": "pesquisarGerenciadorDocumentosDados",
                        "msg": payload.get("msg"),
                        "draw": draw,
                        "start": start,
                    },
                )

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
            headers=self._headers_with_csrf(),
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

    def _bootstrap_context(self, cnpj_fundo: str) -> None:
        last_response = None
        params_candidates = [{"cnpjFundo": cnpj_fundo}, {}]
        for params in params_candidates:
            for attempt in range(3):
                response = self.session.get(
                    self._url("abrirGerenciadorDocumentosCVM"),
                    params=params,
                    timeout=self.timeout_seconds,
                )
                last_response = response
                if response.status_code >= 500:
                    time.sleep(0.8)
                    continue
                match = re.search(r"csrf_token\\s*=\\s*['\\\"]([^'\\\"]+)['\\\"]", response.text)
                if not match:
                    match = re.search(r"token\\s*=\\s*['\\\"]([^'\\\"]+)['\\\"]", response.text)
                if match:
                    self.csrf_token = match.group(1)
                    self.referer_url = response.url
                    return
                time.sleep(0.8)

        if last_response is not None and last_response.status_code >= 500:
            raise ProviderUnavailableError(
                f"Fundos.NET indisponível ao abrir gerenciador (HTTP {last_response.status_code}).",
                details={
                    "etapa": "bootstrap_context",
                    "endpoint": "abrirGerenciadorDocumentosCVM",
                    "http_status": last_response.status_code,
                    "cnpj_fundo": cnpj_fundo,
                },
            )
        raise ProviderUnavailableError(
            "Token CSRF não encontrado na página pública do gerenciador.",
            details={
                "etapa": "bootstrap_context",
                "endpoint": "abrirGerenciadorDocumentosCVM",
                "snippet": (last_response.text[:160] if last_response is not None else ""),
            },
        )

    def _headers_with_csrf(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
        if self.csrf_token:
            headers["CSRFToken"] = self.csrf_token
        if self.referer_url:
            headers["Referer"] = self.referer_url
        return headers


def _first_present(item: Dict[str, Any], candidates: List[str]) -> Optional[str]:
    for key in candidates:
        val = item.get(key)
        if val not in (None, ""):
            return str(val)
    return None
