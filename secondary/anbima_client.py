"""Cliente HTTP do ANBIMA Feed - Preços & Índices.

Endpoints usados:
- GET /v1/fidc/mercado-secundario  -> preços indicativos de cotas de FIDC (1 data/chamada).
- GET /v1/reune/negociacoes        -> negociações reais (REUNE), resposta paginada.

Rate limit de produção ~15 req/s: há um throttle configurável entre chamadas
(ANBIMA_SLEEP_SECONDS, default 0.1s) e retry com backoff exponencial para
erros de rede, 429 e 5xx. 404/dia sem dado retorna lista vazia, nunca quebra.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import time
from typing import Any

import requests

from secondary.auth import auth_headers

logger = logging.getLogger(__name__)

BASE_PROD = "https://api.anbima.com.br/feed/precos-indices"
BASE_SANDBOX = "https://api-sandbox.anbima.com.br/feed/precos-indices"

_MAX_RETRIES = 4
_BACKOFF_BASE_SECONDS = 2.0
_REQUEST_TIMEOUT = 60
_MAX_PAGES_GUARD = 10_000

_last_request_at = 0.0


def base_url() -> str:
    """URL base conforme ANBIMA_ENV (production | sandbox)."""
    env = os.getenv("ANBIMA_ENV", "production").strip().lower()
    return BASE_SANDBOX if env == "sandbox" else BASE_PROD


def _sleep_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("ANBIMA_SLEEP_SECONDS", "0.1")))
    except ValueError:
        return 0.1


def _throttle() -> None:
    global _last_request_at
    wait = _sleep_seconds() - (time.time() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.time()


def _iso_date(data: str | dt.date) -> str:
    if isinstance(data, dt.date):
        return data.isoformat()
    return str(data).strip()


def _get(path: str, params: dict[str, Any]) -> Any | None:
    """GET com throttle, retry/backoff e refresh de token em 401.

    Retorna o JSON da resposta, ou None para 404 (dia sem dado).
    """
    url = f"{base_url()}{path}"
    headers = auth_headers()
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        _throttle()
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=_REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            last_error = exc
            logger.warning("Erro de rede em %s (tentativa %s): %s", path, attempt + 1, exc)
        else:
            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                return None
            if response.status_code == 401:
                logger.info("401 em %s; renovando token.", path)
                headers = auth_headers(force_refresh=True)
                last_error = RuntimeError(f"401 em {path}")
            elif response.status_code == 429 or response.status_code >= 500:
                last_error = RuntimeError(
                    f"{response.status_code} em {path}: {response.text[:200]}"
                )
                logger.warning("%s; aguardando backoff.", last_error)
            else:
                raise RuntimeError(
                    f"Resposta inesperada {response.status_code} em {path}: "
                    f"{response.text[:300]}"
                )
        if attempt < _MAX_RETRIES:
            time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))
    raise RuntimeError(f"Falha após {_MAX_RETRIES + 1} tentativas em {path}: {last_error}")


def precos_fidc(data: str | dt.date) -> list[dict[str, Any]]:
    """Preços indicativos de cotas de FIDC para uma data (YYYY-MM-DD).

    Retorna a lista de objetos da API (vazia se não houver dado no dia).
    """
    payload = _get("/v1/fidc/mercado-secundario", {"data": _iso_date(data)})
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    # Tolera envelope {"content": [...]} caso a API mude o formato.
    return list(payload.get("content", []))


def negociacoes_reune(data: str | dt.date, size: int = 500) -> list[dict[str, Any]]:
    """Negociações do REUNE para uma data, iterando as páginas até last=true.

    Cobre debêntures, CRI, CRA e CFF; o filtro de FIDC é feito depois, por ISIN.
    """
    dia = _iso_date(data)
    rows: list[dict[str, Any]] = []
    page = 0
    while page < _MAX_PAGES_GUARD:
        payload = _get(
            "/v1/reune/negociacoes", {"data": dia, "size": size, "page": page}
        )
        if payload is None:
            break
        content = payload.get("content") or []
        rows.extend(content)
        if payload.get("last", True) or not content:
            break
        page += 1
    else:  # pragma: no cover
        raise RuntimeError(f"Paginação do REUNE não terminou em {dia} (guarda de páginas).")
    return rows
