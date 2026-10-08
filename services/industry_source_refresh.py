"""Detect new CVM publications and rectifications by their actual bytes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urljoin
import zipfile


MONTHLY_URL = "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/"
HISTORICAL_URL = MONTHLY_URL + "HIST/"
REGISTRATION_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
PROVIDER_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi_hist.zip"
OFFERS_URL = "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/oferta_distribuicao.zip"
ANBIMA_PUBLICATION_API = "https://data-strapi.prd.anbima.com.br/api/publicacao-ranking-de-renda-fixa-e-hibridos?populate=template,template.connected_documents.file,template.publication_document.file"
ANBIMA_MARKET_API = "https://data-strapi.prd.anbima.com.br/api/boletim-mercado-de-capitais?populate=template.attachment&sort=publishedAt:desc&locale=pt-BR"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def curl_text(url: str) -> str:
    return subprocess.run(
        ["curl", "--fail", "--location", "--silent", "--show-error", "--retry", "2",
         "--connect-timeout", "20", "--max-time", "180", url],
        check=True, capture_output=True, text=True,
    ).stdout


def archive_names(index: str, *, annual: bool) -> list[str]:
    digits = r"\d{4}" if annual else r"\d{6}"
    names = set(re.findall(rf'href=[\"\x27](inf_mensal_fidc_{digits}\.zip)[\"\x27]', index))
    if not names:
        raise ValueError("Índice oficial CVM sem arquivos de Informe Mensal reconhecidos")
    return sorted(names)


@dataclass(frozen=True)
class SourceArchive:
    url: str
    path: Path


def discover_sources(raw_dir: Path, cadastro_dir: Path, offers_dir: Path) -> list[SourceArchive]:
    monthly = archive_names(curl_text(MONTHLY_URL), annual=False)
    annual = archive_names(curl_text(HISTORICAL_URL), annual=True)
    sources = [
        *(SourceArchive(MONTHLY_URL + name, raw_dir / name) for name in monthly),
        *(SourceArchive(HISTORICAL_URL + name, raw_dir / name) for name in annual),
        SourceArchive(REGISTRATION_URL, raw_dir / "registro_fundo_classe.zip"),
        SourceArchive(PROVIDER_URL, cadastro_dir / "cad_fi_hist_current.zip"),
        SourceArchive(OFFERS_URL, offers_dir / "oferta_distribuicao.zip"),
    ]
    publication = json.loads(curl_text(ANBIMA_PUBLICATION_API))
    template = publication["data"]["attributes"]["template"]
    anbima_urls = set()
    for group in ("publication_document", "connected_documents"):
        for document in template.get(group) or []:
            for item in (document.get("file") or {}).get("data") or []:
                url = urljoin("https://data-strapi.prd.anbima.com.br", item["attributes"]["url"])
                if url.lower().endswith(".xlsx"):
                    anbima_urls.add(url)
            alternative = document.get("alternative_file_url")
            if alternative and alternative.lower().endswith(".xlsx"):
                anbima_urls.add(alternative)
    if not anbima_urls:
        raise ValueError("Publicação ANBIMA sem workbook oficial reconhecido")
    market = json.loads(curl_text(ANBIMA_MARKET_API))
    market_url = None
    for item in market["data"]:
        market_template = item["attributes"]["template"]
        attachment = ((market_template.get("attachment") or {}).get("data") or {}).get("attributes", {})
        candidate = attachment.get("url") or market_template.get("alternative_file_url")
        if candidate and candidate.lower().endswith(".xlsx"):
            market_url = urljoin("https://data-strapi.prd.anbima.com.br", candidate)
            break
    if not market_url:
        raise ValueError("Boletim ANBIMA sem anexo oficial reconhecido")
    anbima_urls.add(market_url)
    sources.extend(SourceArchive(url, offers_dir / "anbima" / url.rsplit("/", 1)[-1]) for url in sorted(anbima_urls))
    return sources


def _headers(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="latin-1").splitlines():
        if line.startswith("HTTP/"):
            result = {}
        elif ":" in line:
            key, value = line.split(":", 1)
            result[key.lower().strip()] = value.strip()
    return result


def refresh_archive(source: SourceArchive, previous: dict, backup_dir: Path) -> dict:
    """Conditional HTTP is used only for previously verified identical local bytes."""
    source.path.parent.mkdir(parents=True, exist_ok=True)
    if source.path.is_symlink():
        raise ValueError(f"Cache de fonte não pode ser symlink: {source.path}")
    old_sha = file_sha256(source.path) if source.path.is_file() else None
    conditional = old_sha is not None and old_sha == previous.get("sha256")
    with tempfile.TemporaryDirectory(prefix=".source-refresh-", dir=source.path.parent) as temporary:
        payload = Path(temporary) / "download.zip"
        headers = Path(temporary) / "headers.txt"
        command = ["curl", "--fail", "--location", "--silent", "--show-error", "--retry", "2",
                   "--connect-timeout", "20", "--max-time", "300", "--dump-header", str(headers),
                   "--output", str(payload), "--write-out", "%{http_code}"]
        if conditional and previous.get("etag"):
            command += ["--header", "If-None-Match: " + previous["etag"]]
        elif conditional and previous.get("last_modified"):
            command += ["--header", "If-Modified-Since: " + previous["last_modified"]]
        command.append(source.url)
        status = subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
        response = _headers(headers)
        if status == "304":
            if not conditional:
                raise ValueError("Resposta 304 sem cache validado")
            return {**previous, "url": source.url, "path": str(source.path), "changed": False}
        if status != "200":
            raise ValueError(f"Resposta CVM inesperada: {status}")
        with zipfile.ZipFile(payload) as archive:
            if not archive.namelist() or archive.testzip() is not None:
                raise ValueError(f"ZIP CVM inválido: {source.url}")
        new_sha = file_sha256(payload)
        changed = new_sha != old_sha
        if changed:
            if old_sha:
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup = backup_dir / f"{source.path.stem}-{old_sha}.zip"
                if backup.exists() and file_sha256(backup) != old_sha:
                    raise ValueError("Backup de fonte existente tem hash divergente")
                if not backup.exists():
                    shutil.copy2(source.path, backup)
            os.replace(payload, source.path)
        return {"url": source.url, "path": str(source.path), "sha256": new_sha,
                "bytes": source.path.stat().st_size, "etag": response.get("etag", ""),
                "last_modified": response.get("last-modified", ""), "changed": changed}


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
