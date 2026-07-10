from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PARTICIPANT_REGISTRY_COLUMNS = [
    "cnpj",
    "cnpj_raiz",
    "razao_social",
    "nome_fantasia",
    "cnae_fiscal",
    "cnae_descricao",
    "cnae_secao",
    "setor",
    "segmento",
    "cnaes_secundarios",
    "natureza_juridica",
    "porte",
    "situacao_cadastral",
    "data_inicio_atividade",
    "uf",
    "municipio",
    "source_provider",
    "source_url",
    "fetched_at_utc",
    "registry_status",
    "error_message",
]


_CNAE_SECTIONS = [
    (1, 3, "A", "Agricultura, pecuária, produção florestal, pesca e aquicultura"),
    (5, 9, "B", "Indústrias extrativas"),
    (10, 33, "C", "Indústrias de transformação"),
    (35, 35, "D", "Eletricidade e gás"),
    (36, 39, "E", "Água, esgoto, resíduos e descontaminação"),
    (41, 43, "F", "Construção"),
    (45, 47, "G", "Comércio e reparação de veículos"),
    (49, 53, "H", "Transporte, armazenagem e correio"),
    (55, 56, "I", "Alojamento e alimentação"),
    (58, 63, "J", "Informação e comunicação"),
    (64, 66, "K", "Atividades financeiras, seguros e serviços relacionados"),
    (68, 68, "L", "Atividades imobiliárias"),
    (69, 75, "M", "Atividades profissionais, científicas e técnicas"),
    (77, 82, "N", "Atividades administrativas e serviços complementares"),
    (84, 84, "O", "Administração pública, defesa e seguridade social"),
    (85, 85, "P", "Educação"),
    (86, 88, "Q", "Saúde humana e serviços sociais"),
    (90, 93, "R", "Artes, cultura, esporte e recreação"),
    (94, 96, "S", "Outras atividades de serviços"),
    (97, 97, "T", "Serviços domésticos"),
    (99, 99, "U", "Organismos internacionais e outras instituições extraterritoriais"),
]


def _normalize_cnpj(value: object) -> str:
    digits = "".join(char for char in str(value or "") if char.isdigit())
    return digits.zfill(14)[-14:] if digits else ""


def _is_valid_cnpj(value: object) -> bool:
    digits = _normalize_cnpj(value)
    if len(digits) != 14 or digits == digits[0] * 14:
        return False
    numbers = [int(char) for char in digits]

    def digit(base: list[int], weights: list[int]) -> int:
        remainder = sum(number * weight for number, weight in zip(base, weights, strict=True)) % 11
        return 0 if remainder < 2 else 11 - remainder

    return (
        digit(numbers[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) == numbers[12]
        and digit(numbers[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) == numbers[13]
    )


def cnae_section(value: object) -> tuple[str, str]:
    digits = "".join(char for char in str(value or "") if char.isdigit()).zfill(7)
    if len(digits) != 7:
        return "", ""
    division = int(digits[:2])
    for start, end, section, label in _CNAE_SECTIONS:
        if start <= division <= end:
            return section, label
    return "", ""


def participant_registry_targets(structured: pd.DataFrame) -> pd.DataFrame:
    if structured is None or structured.empty or "cnpj_participante" not in structured.columns:
        return pd.DataFrame(columns=["cnpj", "evidence_rows", "funds"])
    frame = structured.copy()
    if "ativo_curadoria" in frame.columns:
        active = frame["ativo_curadoria"].astype(str).str.lower().isin({"true", "1", "sim", "yes"})
        frame = frame[active].copy()
    frame["cnpj"] = frame["cnpj_participante"].map(_normalize_cnpj)
    frame = frame[frame["cnpj"].map(_is_valid_cnpj)].copy()
    if frame.empty:
        return pd.DataFrame(columns=["cnpj", "evidence_rows", "funds"])
    return (
        frame.groupby("cnpj", dropna=False)
        .agg(evidence_rows=("cnpj", "size"), funds=("cnpj_fundo", "nunique"))
        .reset_index()
        .sort_values(["funds", "evidence_rows", "cnpj"], ascending=[False, False, True])
        .reset_index(drop=True)
    )


def _secondary_cnaes(payload: dict[str, object]) -> str:
    values = payload.get("cnaes_secundarios", [])
    if not isinstance(values, list):
        return ""
    rows: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        code = "".join(char for char in str(value.get("codigo", "")) if char.isdigit()).zfill(7)
        description = str(value.get("descricao", "") or "").strip()
        label = " - ".join(part for part in [code if len(code) == 7 else "", description] if part)
        if label and label not in rows:
            rows.append(label)
    return " | ".join(rows)


def normalize_registry_payload(
    payload: dict[str, object],
    *,
    cnpj: str,
    source_url: str,
    fetched_at_utc: str,
) -> dict[str, object]:
    normalized_cnpj = _normalize_cnpj(payload.get("cnpj", cnpj))
    cnae = "".join(char for char in str(payload.get("cnae_fiscal", "")) if char.isdigit()).zfill(7)
    if cnae == "0000000":
        cnae = ""
    section, sector = cnae_section(cnae)
    description = str(payload.get("cnae_fiscal_descricao", "") or "").strip()
    return {
        "cnpj": normalized_cnpj or _normalize_cnpj(cnpj),
        "cnpj_raiz": (normalized_cnpj or _normalize_cnpj(cnpj))[:8],
        "razao_social": str(payload.get("razao_social", "") or "").strip(),
        "nome_fantasia": str(payload.get("nome_fantasia", "") or "").strip(),
        "cnae_fiscal": cnae,
        "cnae_descricao": description,
        "cnae_secao": section,
        "setor": sector,
        "segmento": description,
        "cnaes_secundarios": _secondary_cnaes(payload),
        "natureza_juridica": str(payload.get("natureza_juridica", "") or "").strip(),
        "porte": str(payload.get("porte", "") or "").strip(),
        "situacao_cadastral": str(payload.get("situacao_cadastral", "") or "").strip(),
        "data_inicio_atividade": str(payload.get("data_inicio_atividade", "") or "").strip(),
        "uf": str(payload.get("uf", "") or "").strip(),
        "municipio": str(payload.get("municipio", "") or "").strip(),
        "source_provider": "BrasilAPI/CNPJ",
        "source_url": source_url,
        "fetched_at_utc": fetched_at_utc,
        "registry_status": "ok",
        "error_message": "",
    }


def _registry_columns(frame: pd.DataFrame | None) -> pd.DataFrame:
    out = frame.copy() if frame is not None else pd.DataFrame()
    for column in PARTICIPANT_REGISTRY_COLUMNS:
        if column not in out.columns:
            out[column] = ""
    return out[PARTICIPANT_REGISTRY_COLUMNS]


def _read_cache(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and payload.get("registry_status") == "ok" else None


def _write_cache(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_participant_registry_row(
    cnpj: str,
    *,
    provider_url: str = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}",
    timeout_seconds: float = 20.0,
    retries: int = 2,
) -> dict[str, object]:
    normalized = _normalize_cnpj(cnpj)
    source_url = provider_url.format(cnpj=normalized)
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    last_error = ""
    for attempt in range(max(int(retries), 0) + 1):
        try:
            request = urllib.request.Request(
                source_url,
                headers={"Accept": "application/json", "User-Agent": "fidc-industry-study/1.0"},
            )
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Resposta cadastral não é um objeto JSON.")
            return normalize_registry_payload(
                payload,
                cnpj=normalized,
                source_url=source_url,
                fetched_at_utc=fetched_at,
            )
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            if attempt < max(int(retries), 0):
                time.sleep(min(2 ** attempt, 4))
    return {
        **{column: "" for column in PARTICIPANT_REGISTRY_COLUMNS},
        "cnpj": normalized,
        "cnpj_raiz": normalized[:8],
        "source_provider": "BrasilAPI/CNPJ",
        "source_url": source_url,
        "fetched_at_utc": fetched_at,
        "registry_status": "error",
        "error_message": last_error[:500],
    }


def build_participant_registry(
    structured: pd.DataFrame,
    *,
    cache_dir: Path,
    existing: pd.DataFrame | None = None,
    requested_cnpjs: list[str] | None = None,
    max_network_requests: int = 25,
    refresh: bool = False,
    sleep_seconds: float = 0.25,
    provider_url: str = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}",
) -> tuple[pd.DataFrame, dict[str, int]]:
    targets = participant_registry_targets(structured)
    requested = {_normalize_cnpj(value) for value in (requested_cnpjs or []) if _normalize_cnpj(value)}
    if requested:
        targets = targets[targets["cnpj"].isin(requested)].copy()
    existing_frame = _registry_columns(existing)
    existing_by_cnpj = {
        _normalize_cnpj(row.get("cnpj", "")): {column: row.get(column, "") for column in PARTICIPANT_REGISTRY_COLUMNS}
        for _, row in existing_frame.iterrows()
        if _normalize_cnpj(row.get("cnpj", ""))
    }
    rows: list[dict[str, object]] = []
    network_requests = 0
    cache_hits = 0
    pending = 0
    errors = 0
    for cnpj in targets["cnpj"].astype(str):
        cache_path = cache_dir / f"{cnpj}.json"
        cached = None if refresh else _read_cache(cache_path)
        if cached is not None:
            rows.append(cached)
            cache_hits += 1
            continue
        if not refresh and cnpj in existing_by_cnpj and existing_by_cnpj[cnpj].get("registry_status") == "ok":
            rows.append(existing_by_cnpj[cnpj])
            cache_hits += 1
            continue
        if max_network_requests > 0 and network_requests >= max_network_requests:
            rows.append(
                {
                    **{column: "" for column in PARTICIPANT_REGISTRY_COLUMNS},
                    "cnpj": cnpj,
                    "cnpj_raiz": cnpj[:8],
                    "source_provider": "BrasilAPI/CNPJ",
                    "source_url": provider_url.format(cnpj=cnpj),
                    "registry_status": "pending",
                    "error_message": "limite incremental de requisições atingido",
                }
            )
            pending += 1
            continue
        row = fetch_participant_registry_row(cnpj, provider_url=provider_url)
        rows.append(row)
        network_requests += 1
        if row.get("registry_status") == "ok":
            _write_cache(cache_path, row)
        else:
            errors += 1
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    registry = _registry_columns(pd.DataFrame(rows))
    if not registry.empty:
        registry["cnpj"] = registry["cnpj"].map(_normalize_cnpj)
        registry = registry.drop_duplicates("cnpj", keep="last").reset_index(drop=True)
    return registry, {
        "targets": int(len(targets)),
        "network_requests": int(network_requests),
        "cache_hits": int(cache_hits),
        "pending": int(pending),
        "errors": int(errors),
        "ok": int(registry["registry_status"].eq("ok").sum()) if not registry.empty else 0,
    }
