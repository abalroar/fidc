from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
from urllib import error, request
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

import pandas as pd

from services.fundonet_service import InformeMensalResult, InformeMensalService


IME_CACHE_SCHEMA_VERSION = 1
DEFAULT_RUNTIME_CACHE_ROOT = Path(".cache/fundonet-ime")
DEFAULT_PORTABLE_CACHE_ROOT = Path("data/ime_cache/fundonet-ime")
REMOTE_CACHE_BASE_URL_ENV = "FIDC_IME_CACHE_BASE_URL"
REQUIRED_CACHE_FILE_KEYS = {
    "docs_csv_path",
    "contas_csv_path",
    "listas_csv_path",
    "wide_csv_path",
    "excel_path",
    "audit_json_path",
    "audit_csv_path",
}


@dataclass(frozen=True)
class CachedInformeLoad:
    result: InformeMensalResult
    cache_key: str
    cache_dir: Path
    cache_status: str
    cache_source: str = ""
    source_refresh_attempted: bool = False


@dataclass(frozen=True)
class CachedInformeProbe:
    cache_key: str
    cache_dir: Path
    manifest_path: Path
    is_cached: bool
    cache_status: str = "miss"
    cache_source: str = ""
    requested_cache_key: str = ""
    source_refresh_attempted: bool = False


def load_or_extract_informe(
    *,
    cnpj_fundo: str,
    data_inicial: date,
    data_final: date,
    service: InformeMensalService | None = None,
    cache_root: Path | None = None,
    portable_cache_root: Path | None = None,
    remote_cache_base_url: str | None = None,
    force_refresh: bool = False,
    progress_callback=None,  # noqa: ANN001
) -> CachedInformeLoad:
    cache_key = _build_cache_key(cnpj_fundo=cnpj_fundo, data_inicial=data_inicial, data_final=data_final)
    runtime_cache_root = (cache_root or DEFAULT_RUNTIME_CACHE_ROOT).resolve()
    cache_dir = runtime_cache_root / cache_key
    manifest_path = cache_dir / "manifest.json"

    if not force_refresh:
        cached = _load_cached_result(
            cache_dir=cache_dir,
            manifest_path=manifest_path,
            cache_key=cache_key,
            cache_status="hit",
            cache_source="runtime",
        )
        if cached is not None:
            return cached

        cached = _load_portable_cached_result(
            cache_key=cache_key,
            cnpj_fundo=cnpj_fundo,
            data_inicial=data_inicial,
            data_final=data_final,
            runtime_cache_root=runtime_cache_root,
            portable_cache_root=portable_cache_root,
            remote_cache_base_url=remote_cache_base_url,
        )
        if cached is not None:
            return cached

    runtime_service = service or InformeMensalService()
    fresh = runtime_service.run(
        cnpj_fundo=cnpj_fundo,
        data_inicial=data_inicial,
        data_final=data_final,
        progress_callback=progress_callback,
    )
    _persist_result_to_cache(
        result=fresh,
        cache_dir=cache_dir,
        manifest_path=manifest_path,
        cache_key=cache_key,
        cnpj_fundo=cnpj_fundo,
        data_inicial=data_inicial,
        data_final=data_final,
    )
    cache_status = "refresh" if force_refresh else "miss"
    cached = _load_cached_result(
        cache_dir=cache_dir,
        manifest_path=manifest_path,
        cache_key=cache_key,
        cache_status=cache_status,
        cache_source="fundonet",
    )
    if cached is None:
        raise RuntimeError("Falha ao reconstruir a extração a partir do cache persistido.")
    return CachedInformeLoad(
        result=cached.result,
        cache_key=cached.cache_key,
        cache_dir=cached.cache_dir,
        cache_status=cache_status,
        cache_source="fundonet",
        source_refresh_attempted=True,
    )


def peek_cached_informe(
    *,
    cnpj_fundo: str,
    data_inicial: date,
    data_final: date,
    cache_root: Path | None = None,
    portable_cache_root: Path | None = None,
) -> CachedInformeProbe:
    cache_key = _build_cache_key(cnpj_fundo=cnpj_fundo, data_inicial=data_inicial, data_final=data_final)
    runtime_cache_root = (cache_root or DEFAULT_RUNTIME_CACHE_ROOT).resolve()
    cache_dir = runtime_cache_root / cache_key
    manifest_path = cache_dir / "manifest.json"
    if _is_cache_complete(cache_dir=cache_dir, manifest_path=manifest_path):
        return CachedInformeProbe(
            cache_key=cache_key,
            cache_dir=cache_dir,
            manifest_path=manifest_path,
            is_cached=True,
            cache_status="hit",
            cache_source="runtime",
            requested_cache_key=cache_key,
            source_refresh_attempted=bool((_read_cache_manifest(manifest_path) or {}).get("source_refresh_attempted")),
        )
    portable_root = _portable_cache_root_path(portable_cache_root)
    if portable_root is not None:
        portable_dir = portable_root / cache_key
        portable_manifest_path = portable_dir / "manifest.json"
        if _is_cache_complete(cache_dir=portable_dir, manifest_path=portable_manifest_path):
            return CachedInformeProbe(
                cache_key=cache_key,
                cache_dir=portable_dir,
                manifest_path=portable_manifest_path,
                is_cached=True,
                cache_status="github_cache",
                cache_source="portable_dir",
                requested_cache_key=cache_key,
                source_refresh_attempted=bool((_read_cache_manifest(portable_manifest_path) or {}).get("source_refresh_attempted")),
            )
        portable_zip = portable_root / f"{cache_key}.zip"
        if _is_cache_zip_complete(portable_zip):
            return CachedInformeProbe(
                cache_key=cache_key,
                cache_dir=cache_dir,
                manifest_path=manifest_path,
                is_cached=True,
                cache_status="github_cache",
                cache_source="portable_zip",
                requested_cache_key=cache_key,
                source_refresh_attempted=bool((_read_cache_zip_manifest(portable_zip) or {}).get("source_refresh_attempted")),
            )
    compatible = _find_compatible_cache_manifest(
        cnpj_fundo=cnpj_fundo,
        data_inicial=data_inicial,
        data_final=data_final,
        search_root=runtime_cache_root,
    )
    if compatible is not None:
        compatible_dir, compatible_manifest = compatible
        return CachedInformeProbe(
            cache_key=str(compatible_manifest.get("cache_key") or cache_key),
            cache_dir=compatible_dir,
            manifest_path=compatible_dir / "manifest.json",
            is_cached=True,
            cache_status="partial_hit",
            cache_source="runtime_compatible",
            requested_cache_key=cache_key,
            source_refresh_attempted=bool(compatible_manifest.get("source_refresh_attempted")),
        )
    if portable_root is not None:
        compatible_package = _find_compatible_portable_package(
            cnpj_fundo=cnpj_fundo,
            data_inicial=data_inicial,
            data_final=data_final,
            portable_root=portable_root,
        )
        if compatible_package is not None:
            package_path, package_manifest = compatible_package
            return CachedInformeProbe(
                cache_key=str(package_manifest.get("cache_key") or cache_key),
                cache_dir=cache_dir,
                manifest_path=manifest_path,
                is_cached=True,
                cache_status="github_cache_partial",
                cache_source=f"portable_index:{package_path.name}",
                requested_cache_key=cache_key,
                source_refresh_attempted=bool(package_manifest.get("source_refresh_attempted")),
            )
    return CachedInformeProbe(
        cache_key=cache_key,
        cache_dir=cache_dir,
        manifest_path=manifest_path,
        is_cached=False,
        requested_cache_key=cache_key,
    )


def _build_cache_key(*, cnpj_fundo: str, data_inicial: date, data_final: date) -> str:
    payload = f"{''.join(ch for ch in str(cnpj_fundo) if ch.isdigit())}|{data_inicial.isoformat()}|{data_final.isoformat()}|{IME_CACHE_SCHEMA_VERSION}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _portable_cache_root_path(portable_cache_root: Path | None) -> Path | None:
    root = portable_cache_root if portable_cache_root is not None else DEFAULT_PORTABLE_CACHE_ROOT
    resolved = root.resolve()
    return resolved if resolved.exists() else None


def _remote_cache_base_url(value: str | None) -> str:
    return str(value or os.environ.get(REMOTE_CACHE_BASE_URL_ENV) or "").strip().rstrip("/")


def _load_portable_cached_result(
    *,
    cache_key: str,
    cnpj_fundo: str,
    data_inicial: date,
    data_final: date,
    runtime_cache_root: Path,
    portable_cache_root: Path | None,
    remote_cache_base_url: str | None,
) -> CachedInformeLoad | None:
    runtime_cache_dir = runtime_cache_root / cache_key
    runtime_manifest_path = runtime_cache_dir / "manifest.json"
    portable_root = _portable_cache_root_path(portable_cache_root)
    if portable_root is not None:
        portable_dir = portable_root / cache_key
        portable_manifest_path = portable_dir / "manifest.json"
        if _is_cache_complete(cache_dir=portable_dir, manifest_path=portable_manifest_path):
            return _load_cached_result(
                cache_dir=portable_dir,
                manifest_path=portable_manifest_path,
                cache_key=cache_key,
                cache_status="github_cache",
                cache_source="portable_dir",
            )
        portable_zip = portable_root / f"{cache_key}.zip"
        if _extract_cache_zip(portable_zip, runtime_cache_dir):
            cached = _load_cached_result(
                cache_dir=runtime_cache_dir,
                manifest_path=runtime_manifest_path,
                cache_key=cache_key,
                cache_status="github_cache",
                cache_source="portable_zip",
            )
            if cached is not None:
                return cached

    remote_base_url = _remote_cache_base_url(remote_cache_base_url)
    if remote_base_url:
        remote_zip = _download_remote_cache_zip(
            cache_key=cache_key,
            runtime_cache_root=runtime_cache_root,
            remote_cache_base_url=remote_base_url,
        )
        if remote_zip is not None and _extract_cache_zip(remote_zip, runtime_cache_dir):
            return _load_cached_result(
                cache_dir=runtime_cache_dir,
                manifest_path=runtime_manifest_path,
                cache_key=cache_key,
                cache_status="github_cache",
                cache_source="remote_zip",
            )
    compatible = _find_compatible_cache_manifest(
        cnpj_fundo=cnpj_fundo,
        data_inicial=data_inicial,
        data_final=data_final,
        search_root=runtime_cache_root,
    )
    if compatible is not None:
        compatible_dir, compatible_manifest = compatible
        compatible_key = str(compatible_manifest.get("cache_key") or compatible_dir.name)
        cached = _load_cached_result(
            cache_dir=compatible_dir,
            manifest_path=compatible_dir / "manifest.json",
            cache_key=compatible_key,
            cache_status="partial_hit",
            cache_source="runtime_compatible",
        )
        if cached is not None:
            return cached
    if portable_root is not None:
        compatible_package = _find_compatible_portable_package(
            cnpj_fundo=cnpj_fundo,
            data_inicial=data_inicial,
            data_final=data_final,
            portable_root=portable_root,
        )
        if compatible_package is not None:
            package_path, package_manifest = compatible_package
            compatible_key = str(package_manifest.get("cache_key") or package_path.stem)
            compatible_cache_dir = runtime_cache_root / compatible_key
            if _extract_cache_zip(package_path, compatible_cache_dir):
                cached = _load_cached_result(
                    cache_dir=compatible_cache_dir,
                    manifest_path=compatible_cache_dir / "manifest.json",
                    cache_key=compatible_key,
                    cache_status="github_cache_partial",
                    cache_source=f"portable_index:{package_path.name}",
                )
                if cached is not None:
                    return cached
    return None


def _find_compatible_cache_manifest(
    *,
    cnpj_fundo: str,
    data_inicial: date,
    data_final: date,
    search_root: Path,
) -> tuple[Path, dict[str, object]] | None:
    requested_cnpj = _normalize_cnpj(cnpj_fundo)
    candidates: list[tuple[tuple[int, date, str], Path, dict[str, object]]] = []
    for manifest_path in search_root.glob("*/manifest.json"):
        cache_dir = manifest_path.parent
        manifest = _read_cache_manifest(manifest_path)
        if manifest is None:
            continue
        if not _cache_manifest_matches_request(
            manifest=manifest,
            requested_cnpj=requested_cnpj,
            requested_start=data_inicial,
            requested_end=data_final,
        ):
            continue
        if _resolve_cache_files(cache_dir=cache_dir, manifest=manifest) is None:
            continue
        manifest_start = _parse_manifest_month(manifest.get("data_inicial"))
        if manifest_start is None:
            continue
        candidates.append((_compatible_cache_score(manifest_start, data_inicial, cache_dir.name), cache_dir, manifest))
    if not candidates:
        return None
    _, cache_dir, manifest = min(candidates, key=lambda item: item[0])
    return cache_dir, manifest


def _find_compatible_portable_package(
    *,
    cnpj_fundo: str,
    data_inicial: date,
    data_final: date,
    portable_root: Path,
) -> tuple[Path, dict[str, object]] | None:
    requested_cnpj = _normalize_cnpj(cnpj_fundo)
    candidates: list[tuple[tuple[int, date, str], Path, dict[str, object]]] = []
    for package_path, manifest in _iter_portable_package_manifests(portable_root):
        if not _cache_manifest_matches_request(
            manifest=manifest,
            requested_cnpj=requested_cnpj,
            requested_start=data_inicial,
            requested_end=data_final,
        ):
            continue
        if not _is_cache_zip_complete(package_path):
            continue
        manifest_start = _parse_manifest_month(manifest.get("data_inicial"))
        if manifest_start is None:
            continue
        candidates.append(
            (
                _compatible_cache_score(manifest_start, data_inicial, str(manifest.get("cache_key") or package_path.stem)),
                package_path,
                manifest,
            )
        )
    if not candidates:
        return None
    _, package_path, manifest = min(candidates, key=lambda item: item[0])
    return package_path, manifest


def _iter_portable_package_manifests(portable_root: Path) -> list[tuple[Path, dict[str, object]]]:
    index_path = portable_root / "index.json"
    indexed_rows: list[dict[str, object]] = []
    if index_path.exists():
        try:
            raw_index = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw_index = []
        if isinstance(raw_index, list):
            indexed_rows = [row for row in raw_index if isinstance(row, dict)]
    if indexed_rows:
        packages: list[tuple[Path, dict[str, object]]] = []
        for row in indexed_rows:
            package_name = str(row.get("package") or f"{row.get('cache_key', '')}.zip")
            package_path = portable_root / package_name
            if package_path.exists():
                packages.append((package_path, row))
        return packages

    manifests: list[tuple[Path, dict[str, object]]] = []
    for package_path in sorted(portable_root.glob("*.zip")):
        manifest = _read_cache_zip_manifest(package_path)
        if manifest is not None:
            manifests.append((package_path, manifest))
    return manifests


def _cache_manifest_matches_request(
    *,
    manifest: dict[str, object],
    requested_cnpj: str,
    requested_start: date,
    requested_end: date,
) -> bool:
    manifest_start = _parse_manifest_month(manifest.get("data_inicial"))
    manifest_end = _parse_manifest_month(manifest.get("data_final"))
    return (
        _normalize_cnpj(manifest.get("cnpj_fundo")) == requested_cnpj
        and manifest_start is not None
        and manifest_end == requested_end
        and manifest_end >= requested_start
        and manifest_start <= requested_end
    )


def _compatible_cache_score(manifest_start: date, requested_start: date, tie_breaker: str) -> tuple[int, date, str]:
    coverage_rank = 0 if manifest_start <= requested_start else 1
    return coverage_rank, manifest_start, tie_breaker


def _normalize_cnpj(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _parse_manifest_month(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _download_remote_cache_zip(
    *,
    cache_key: str,
    runtime_cache_root: Path,
    remote_cache_base_url: str,
) -> Path | None:
    package_dir = runtime_cache_root / "_packages"
    package_dir.mkdir(parents=True, exist_ok=True)
    package_path = package_dir / f"{cache_key}.zip"
    if _is_cache_zip_complete(package_path):
        return package_path
    url = f"{remote_cache_base_url}/{cache_key}.zip"
    try:
        with request.urlopen(url, timeout=12) as response:  # noqa: S310 - user-configured cache URL
            package_path.write_bytes(response.read())
    except error.HTTPError as exc:
        if exc.code == 404:
            return None
        return None
    except (OSError, error.URLError):
        return None
    return package_path if _is_cache_zip_complete(package_path) else None


def _extract_cache_zip(package_path: Path, target_dir: Path) -> bool:
    if not _is_cache_zip_complete(package_path):
        return False
    if _is_cache_complete(cache_dir=target_dir, manifest_path=target_dir / "manifest.json"):
        return True
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_root = target_dir.resolve()
    try:
        with ZipFile(package_path) as archive:
            for member in archive.infolist():
                destination = (target_dir / member.filename).resolve()
                if destination != target_root and target_root not in destination.parents:
                    raise ValueError("Pacote de cache IME contém caminho inválido.")
                archive.extract(member, target_dir)
    except (BadZipFile, OSError, ValueError):
        shutil.rmtree(target_dir, ignore_errors=True)
        return False
    return _is_cache_complete(cache_dir=target_dir, manifest_path=target_dir / "manifest.json")


def export_cached_informe_package(
    *,
    cache_key: str,
    cache_root: Path | None = None,
    output_root: Path | None = None,
) -> Path:
    runtime_cache_root = (cache_root or DEFAULT_RUNTIME_CACHE_ROOT).resolve()
    cache_dir = runtime_cache_root / cache_key
    manifest_path = cache_dir / "manifest.json"
    if not _is_cache_complete(cache_dir=cache_dir, manifest_path=manifest_path):
        raise FileNotFoundError(f"Cache IME incompleto para {cache_key}.")
    destination_root = (output_root or DEFAULT_PORTABLE_CACHE_ROOT).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    package_path = destination_root / f"{cache_key}.zip"
    manifest = _read_cache_manifest(manifest_path)
    assert manifest is not None
    files = manifest.get("files") or {}
    with ZipFile(package_path, mode="w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(manifest_path, "manifest.json")
        for filename in files.values():
            source = cache_dir / str(filename)
            archive.write(source, str(filename))
    return package_path


def _persist_result_to_cache(
    *,
    result: InformeMensalResult,
    cache_dir: Path,
    manifest_path: Path,
    cache_key: str,
    cnpj_fundo: str,
    data_inicial: date,
    data_final: date,
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_map = {
        "docs_csv_path": result.docs_csv_path,
        "contas_csv_path": result.contas_csv_path,
        "listas_csv_path": result.listas_csv_path,
        "wide_csv_path": result.wide_csv_path,
        "excel_path": result.excel_path,
        "audit_json_path": result.audit_json_path,
        "audit_csv_path": result.workspace_dir / "audit_log.csv",
    }
    manifest_files: dict[str, str] = {}
    for logical_name, source_path in file_map.items():
        destination_name = source_path.name
        destination_path = cache_dir / destination_name
        shutil.copy2(source_path, destination_path)
        manifest_files[logical_name] = destination_name

    manifest = {
        "schema_version": IME_CACHE_SCHEMA_VERSION,
        "cache_key": cache_key,
        "cnpj_fundo": "".join(ch for ch in str(cnpj_fundo) if ch.isdigit()),
        "data_inicial": data_inicial.isoformat(),
        "data_final": data_final.isoformat(),
        "competencias": list(result.competencias),
        "source_refresh_attempted": True,
        "contas_row_count": int(result.contas_row_count),
        "listas_row_count": int(result.listas_row_count),
        "wide_row_count": int(result.wide_row_count),
        "files": manifest_files,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_cached_result(
    *,
    cache_dir: Path,
    manifest_path: Path,
    cache_key: str,
    cache_status: str = "hit",
    cache_source: str = "runtime",
) -> CachedInformeLoad | None:
    manifest = _read_cache_manifest(manifest_path)
    if manifest is None:
        return None
    resolved_files = _resolve_cache_files(cache_dir=cache_dir, manifest=manifest)
    if resolved_files is None:
        return None

    docs_df = pd.read_csv(resolved_files["docs_csv_path"], dtype=str, keep_default_na=False)
    audit_df = pd.read_csv(resolved_files["audit_csv_path"], dtype=str, keep_default_na=False)
    result = InformeMensalResult(
        docs_df=docs_df,
        audit_df=audit_df,
        competencias=list(manifest.get("competencias") or []),
        workspace_dir=cache_dir,
        docs_csv_path=resolved_files["docs_csv_path"],
        contas_csv_path=resolved_files["contas_csv_path"],
        listas_csv_path=resolved_files["listas_csv_path"],
        wide_csv_path=resolved_files["wide_csv_path"],
        excel_path=resolved_files["excel_path"],
        audit_json_path=resolved_files["audit_json_path"],
        contas_row_count=int(manifest.get("contas_row_count") or 0),
        listas_row_count=int(manifest.get("listas_row_count") or 0),
        wide_row_count=int(manifest.get("wide_row_count") or 0),
    )
    return CachedInformeLoad(
        result=result,
        cache_key=cache_key,
        cache_dir=cache_dir,
        cache_status=cache_status,
        cache_source=cache_source,
        source_refresh_attempted=bool(manifest.get("source_refresh_attempted")),
    )


def _read_cache_manifest(manifest_path: Path) -> dict[str, object] | None:
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if int(manifest.get("schema_version") or 0) != IME_CACHE_SCHEMA_VERSION:
        return None
    return manifest


def _resolve_cache_files(*, cache_dir: Path, manifest: dict[str, object]) -> dict[str, Path] | None:
    files = manifest.get("files") or {}
    if not isinstance(files, dict):
        return None
    if not REQUIRED_CACHE_FILE_KEYS.issubset(files):
        return None
    resolved_files = {name: cache_dir / str(filename) for name, filename in files.items()}
    if not all(path.exists() for path in resolved_files.values()):
        return None
    return resolved_files


def _is_cache_complete(*, cache_dir: Path, manifest_path: Path) -> bool:
    manifest = _read_cache_manifest(manifest_path)
    return manifest is not None and _resolve_cache_files(cache_dir=cache_dir, manifest=manifest) is not None


def _read_cache_zip_manifest(package_path: Path) -> dict[str, object] | None:
    if not package_path.exists():
        return None
    try:
        with ZipFile(package_path) as archive:
            if "manifest.json" not in {name.rstrip("/") for name in archive.namelist()}:
                return None
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    except (BadZipFile, KeyError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(manifest, dict):
        return None
    if int(manifest.get("schema_version") or 0) != IME_CACHE_SCHEMA_VERSION:
        return None
    return manifest


def _is_cache_zip_complete(package_path: Path) -> bool:
    manifest = _read_cache_zip_manifest(package_path)
    if manifest is None:
        return False
    try:
        with ZipFile(package_path) as archive:
            names = {name.rstrip("/") for name in archive.namelist()}
            files = manifest.get("files") or {}
            if not isinstance(files, dict) or not REQUIRED_CACHE_FILE_KEYS.issubset(files):
                return False
            return all(str(filename).rstrip("/") in names for filename in files.values())
    except (BadZipFile, OSError):
        return False
