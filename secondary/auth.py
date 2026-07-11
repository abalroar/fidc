"""Autenticação OAuth2 (client credentials) para o ANBIMA Feed.

Credenciais vêm SOMENTE de variáveis de ambiente / arquivo .env:
    ANBIMA_CLIENT_ID, ANBIMA_CLIENT_SECRET
Opcionais:
    ANBIMA_TOKEN_URL  (default: https://api.anbima.com.br/oauth/access-token)

Fluxo confirmado contra a API real (jul/2026): POST no endpoint de token com
Authorization: Basic base64(client_id:client_secret) e corpo JSON
{"grant_type": "client_credentials"}; a resposta vem com HTTP 201 e
expires_in de 3600s. O mesmo host de token atende produção e sandbox.
"""
from __future__ import annotations

import base64
import os
import threading
import time

import requests

try:  # python-dotenv é opcional em runtime (obrigatório só para .env local)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

DEFAULT_TOKEN_URL = "https://api.anbima.com.br/oauth/access-token"
_EXPIRY_MARGIN_SECONDS = 60.0
_REQUEST_TIMEOUT = 30

_lock = threading.Lock()
_cache: dict[str, object] = {"token": None, "expires_at": 0.0}


class AnbimaAuthError(RuntimeError):
    """Falha de configuração ou de obtenção do token OAuth2."""


def _credentials() -> tuple[str, str]:
    client_id = os.getenv("ANBIMA_CLIENT_ID", "").strip()
    client_secret = os.getenv("ANBIMA_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise AnbimaAuthError(
            "Defina ANBIMA_CLIENT_ID e ANBIMA_CLIENT_SECRET no ambiente ou no .env "
            "(veja .env.example). Nunca hardcode credenciais."
        )
    return client_id, client_secret


def _fetch_token() -> tuple[str, float]:
    """Solicita um novo access_token; retorna (token, epoch de expiração)."""
    client_id, client_secret = _credentials()
    token_url = os.getenv("ANBIMA_TOKEN_URL", DEFAULT_TOKEN_URL)
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    response = requests.post(
        token_url,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/json",
        },
        json={"grant_type": "client_credentials"},
        timeout=_REQUEST_TIMEOUT,
    )
    # A ANBIMA responde 201 Created na emissão do token; aceita qualquer 2xx.
    if not response.ok:
        raise AnbimaAuthError(
            f"Token OAuth2 recusado ({response.status_code}): {response.text[:300]}"
        )
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise AnbimaAuthError(f"Resposta de token sem access_token: {payload}")
    expires_in = float(payload.get("expires_in", 3600))
    return str(token), time.time() + expires_in - _EXPIRY_MARGIN_SECONDS


def get_access_token(force_refresh: bool = False) -> str:
    """Retorna um access_token válido, com cache em memória e refresh automático."""
    with _lock:
        if (
            force_refresh
            or _cache["token"] is None
            or time.time() >= float(_cache["expires_at"])  # type: ignore[arg-type]
        ):
            token, expires_at = _fetch_token()
            _cache["token"] = token
            _cache["expires_at"] = expires_at
        return str(_cache["token"])


def auth_headers(force_refresh: bool = False) -> dict[str, str]:
    """Headers exigidos em toda chamada ao ANBIMA Feed."""
    client_id, _ = _credentials()
    return {
        "client_id": client_id,
        "access_token": get_access_token(force_refresh=force_refresh),
        "Content-Type": "application/json",
    }
