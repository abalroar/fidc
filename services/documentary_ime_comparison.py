"""Read-only, bounded IME snapshots for documentary diligence.

The declared basket determines the reference. An observation at month-end never
certifies daily compliance, a contractual cure period, or a different asset base.
"""
from __future__ import annotations

import calendar
import csv
from datetime import date, datetime, timedelta
from functools import lru_cache
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Mapping
import zipfile

IME_TRANSFORMATION_VERSION = 4


def _cnpj(value: object) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    # Numeric XML representations may omit exactly one leading zero. Keep
    # formatted/malformed identifiers conservative; compare the restored
    # fourteen digits against the declared CNPJ, never by a name or alias.
    if re.fullmatch(r"\d{13}", text):
        return text.zfill(14)
    return re.sub(r"\D", "", text)


def normalize_documentary_competence(value: object) -> str | None:
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{2})/(\d{4})", text)
    if match:
        month, year = map(int, match.groups())
    else:
        match = re.fullmatch(r"(\d{4})-(\d{2})(?:-\d{2})?", text)
        if not match:
            return None
        year, month = map(int, match.groups())
    return f"{month:02d}/{year:04d}" if 1 <= month <= 12 and year > 0 else None


def _month_key(value: str) -> tuple[int, int]:
    return int(value[3:]), int(value[:2])


def _date(value: object) -> date | None:
    text = str(value or "").strip()[:10]
    for pattern, order in ((r"(\d{4})-(\d{2})-(\d{2})", (0, 1, 2)), (r"(\d{2})/(\d{2})/(\d{4})", (2, 1, 0))):
        match = re.fullmatch(pattern, text)
        if match:
            values = [int(part) for part in match.groups()]
            try:
                return date(*(values[i] for i in order))
            except ValueError:
                return None
    return None


def _number(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _header_cnpj(value: object) -> str:
    # Fundos.NET also serializes NR_CNPJ as an integer, omitting leading zeroes.
    # Apply padding only to an explicitly named CNPJ field, not arbitrary IDs.
    raw = str(value or "").strip()
    digits = _cnpj(raw)
    return digits.zfill(14) if raw.isdigit() and 1 <= len(digits) < 14 else digits


def _verified_header_mapping(cnpj: str, fund_id: str, class_id: str, competence: str, source_root=None) -> dict:
    """Accept only a saved, independently evidenced exact fund/class inversion."""
    configured = os.environ.get("FIDC_DOCUMENTARY_SOURCE_ROOT")
    root = Path(source_root).resolve() if source_root else Path(configured).resolve() if configured else Path(__file__).resolve().parents[1]
    if root.name == "fundonet-ime":
        root = root.parent.parent
    path = root / "data/documentary_diligence/identity_mappings" / f"{cnpj}.json"
    try:
        mapping = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    pair = mapping.get("allowed_header_pair") or {}
    effective = _date(mapping.get("effective_from"))
    normalized = normalize_documentary_competence(competence)
    if not normalized or not effective:
        return {}
    year, month = _month_key(normalized)
    cutoff = date(year, month, calendar.monthrange(year, month)[1])
    if (mapping.get("status") != "verified" or mapping.get("relationship") != "class_of_fund"
        or mapping.get("allowed_header_layout") != "fund_class_inverted"
        or _cnpj(mapping.get("cnpj")) != cnpj or _cnpj(mapping.get("class_cnpj")) != cnpj
        or _cnpj(mapping.get("fund_cnpj")) != class_id
        or pair.get("NR_CNPJ_FUNDO") != fund_id or pair.get("NR_CNPJ_CLASSE") != class_id
        or fund_id != cnpj or class_id == cnpj or cutoff < effective):
        return {}
    # Registry IDs join the two rows; names and CLASS_UNICA cannot authorize an alias.
    if not mapping.get("registry_fund_id") or not mapping.get("registry_class_id"):
        return {}
    if not any(source.get("identity_verified") is True and source.get("document_id")
               and source.get("clause") and source.get("sha256")
               and str(source.get("url", "")).startswith("https://dados.cvm.gov.br/")
               for source in mapping.get("sources", [])):
        return {}
    return mapping


def _source_root(source_root: object = None) -> Path:
    if source_root:
        return Path(str(source_root)).resolve()
    configured = os.environ.get("FIDC_DOCUMENTARY_SOURCE_ROOT")
    if configured:
        return Path(configured).resolve()
    # Portable evidence belongs to this checkout. Resolving Git's common
    # directory here would silently read another branch's stale IME/index.
    return Path(__file__).resolve().parents[1]


def _cache_root(source_root: object = None) -> Path:
    root = _source_root(source_root)
    return root if root.name == "fundonet-ime" else root / ".cache" / "fundonet-ime"


def _safe_file(cache_dir: Path, filename: object) -> Path | None:
    if not filename:
        return None
    path = (cache_dir / str(filename)).resolve()
    return path if path.is_relative_to(cache_dir.resolve()) and path.is_file() else None


@lru_cache(maxsize=4)
def _manifest_index(root_text: str, directory_mtime: int) -> dict[str, tuple[dict, ...]]:
    _ = directory_mtime
    output: dict[str, list[dict]] = {}
    for path in Path(root_text).glob("*/manifest.json"):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        digits = _cnpj(manifest.get("cnpj_fundo"))
        competencies = tuple(dict.fromkeys(filter(None, (normalize_documentary_competence(c) for c in manifest.get("competencias", [])))))
        files = manifest.get("files") or {}
        if len(digits) != 14 or not competencies or not _safe_file(path.parent, files.get("wide_csv_path")):
            continue
        output.setdefault(digits, []).append({"directory": str(path.parent), "competences": competencies, "files": files})
    return {cnpj: tuple(sorted(items, key=lambda item: (_month_key(max(item["competences"], key=_month_key)), len(item["competences"])), reverse=True)) for cnpj, items in output.items()}


def _index(cache_root: Path) -> dict[str, tuple[dict, ...]]:
    try:
        # Existing cache directories can receive a refreshed manifest in place.
        stamp = max([cache_root.stat().st_mtime_ns] + [path.stat().st_mtime_ns for path in cache_root.glob("*/manifest.json")])
        return _manifest_index(str(cache_root.resolve()), stamp)
    except OSError:
        return {}


def _validated_cache_competences(cache: Mapping, cnpj: str, source_root=None) -> set[str]:
    """A manifest's month is usable only with a matching primary CNPJ header."""
    directory = Path(cache["directory"])
    path = _safe_file(directory, cache["files"].get("wide_csv_path"))
    if not path:
        return set()
    wanted = set(cache["competences"])
    headers = {}
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            wanted &= set(reader.fieldnames or [])
            for row in reader:
                key = row.get("tag_path", "")
                if key in {"DOC_ARQ/CAB_INFORM/NR_CNPJ_FUNDO", "DOC_ARQ/CAB_INFORM/NR_CNPJ_CLASSE"}:
                    headers[key] = row
                    if len(headers) == 2:
                        break
    except (OSError, csv.Error):
        return set()
    result = set()
    for competence in wanted:
        fund = _header_cnpj(headers.get("DOC_ARQ/CAB_INFORM/NR_CNPJ_FUNDO", {}).get(competence))
        klass = _header_cnpj(headers.get("DOC_ARQ/CAB_INFORM/NR_CNPJ_CLASSE", {}).get(competence))
        declared = klass if len(klass) == 14 else fund
        if declared == cnpj or _verified_header_mapping(cnpj,fund,klass,competence,source_root):
            result.add(competence)
    return result


def _portable_roots(source_root: object = None) -> tuple[Path, ...]:
    """Published snapshots live with the app; explicit roots keep reads isolated."""
    roots = [Path(str(source_root)).resolve()] if source_root else [Path(__file__).resolve().parents[1], _source_root()]
    return tuple(dict.fromkeys(root / "data" / "documentary_diligence" for root in roots))


@lru_cache(maxsize=4)
def _portable_index(root_text: str, mtime: int, size: int) -> dict[str, dict[str, str]]:
    _ = mtime, size
    root = Path(root_text)
    try:
        payload = json.loads((root / "ime_index.json").read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            return {}
        output = {}
        for raw_cnpj, entry in (payload.get("cnpjs") or {}).items():
            cnpj = _cnpj(raw_cnpj)
            if len(cnpj) != 14 or not isinstance(entry, dict):
                continue
            snapshots = {}
            for month, filename in (entry.get("snapshots") or {}).items():
                competence = normalize_documentary_competence(month)
                path = _safe_file(root, filename)
                if competence and path:
                    snapshots[competence] = str(path)
            if snapshots:
                output[cnpj] = snapshots
        return output
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


@lru_cache(maxsize=32)
def _portable_snapshot(path_text: str, cnpj: str, competence: str, mtime: int, size: int) -> tuple[dict, dict, str]:
    _ = mtime, size
    try:
        payload = json.loads(Path(path_text).read_text(encoding="utf-8"))
        if _cnpj(payload.get("cnpj")) != cnpj or normalize_documentary_competence(payload.get("competence")) != competence:
            return {}, {}, "Identidade ou competência do snapshot IME publicado diverge do solicitado."
        source = payload.get("source") or {}
        if payload.get("transformation_version") != IME_TRANSFORMATION_VERSION:
            return {}, source, "Snapshot IME produzido por transformação anterior; reprocessar os campos declarados antes do confronto."
        if _cnpj(source.get("cnpj")) != cnpj or normalize_documentary_competence(source.get("competence")) != competence:
            return {}, {}, "Fonte do snapshot IME publicado sem identidade e competência correspondentes."
        if payload.get("status") != "parsed" or source.get("type") != "ime_document" or not source.get("document_id"):
            return {}, {}, "Snapshot IME publicado sem processamento confirmado ou documento de origem."
        raw_values = payload.get("values")
        if not isinstance(raw_values, dict):
            return {}, {}, "Snapshot IME publicado sem campos canônicos."
        values = {key: _number(value) for key, value in raw_values.items()}
        return values, dict(source, snapshot_path=path_text), ""
    except (OSError, ValueError, TypeError, AttributeError):
        return {}, {}, "Snapshot IME publicado ilegível."


def _portable_candidates(cnpj: str, source_root: object = None) -> dict[str, list[tuple[dict, dict, str]]]:
    output: dict[str, list[tuple[dict, dict, str]]] = {}
    for root in _portable_roots(source_root):
        path = root / "ime_index.json"
        try:
            stat = path.stat()
            index = _portable_index(str(root), stat.st_mtime_ns, stat.st_size)
            for competence, path_text in index.get(cnpj, {}).items():
                snapshot_stat = Path(path_text).stat()
                snapshot = _portable_snapshot(path_text, cnpj, competence, snapshot_stat.st_mtime_ns, snapshot_stat.st_size)
                output.setdefault(competence, []).append(snapshot)
        except OSError:
            continue
    return output


def _dashboard(value: Any) -> Any:
    return value[-1] if isinstance(value, tuple) and value else value


def _dashboard_identity(dashboard: Any, cnpj: str) -> bool:
    info = getattr(dashboard, "fund_info", {}) or {}
    # A class can have a different umbrella-fund CNPJ; the exact class wins.
    class_id = _cnpj(info.get("cnpj_classe"))
    identity = class_id if len(class_id) == 14 else _cnpj(info.get("cnpj_fundo") or info.get("cnpj"))
    return identity == cnpj


def _portable_registry_statuses(root: Path, requested: set[str]) -> dict[str, dict]:
    """Use the published exact-ID registry snapshot when the ZIP is absent."""
    path = root / "data/documentary_diligence/registry_statuses.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if (data.get("schema_version") != 1
            or data.get("source_url") != "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
            or not re.fullmatch(r"[0-9a-f]{64}", str(data.get("source_sha256") or ""))
            or not _date(str(data.get("observed_at") or "")[:10])):
        return {}
    observed = str(data["observed_at"])[:10]
    rows = data.get("cnpjs")
    if not isinstance(rows, dict):
        return {}
    output = {}
    for cnpj in requested:
        row = rows.get(cnpj)
        if not isinstance(row, dict):
            continue
        output[cnpj] = {key: row.get(key, "") for key in ("Data_Cancelamento", "Data_Registro", "Data_Inicio_Situacao", "Situacao")}
        output[cnpj]["source"] = f"CVM registro_fundo_classe.zip; snapshot {observed}; SHA256 {data['source_sha256']}"
    return output


def _registry_statuses(root: Path, requested: set[str]) -> dict[str, dict]:
    """Stream only selected registry rows, without downloading or copying a ZIP."""
    url = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
    path = root / ".cache" / "cvm-cadastro" / (hashlib.sha256(url.encode()).hexdigest() + ".bin")
    output: dict[str, dict] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            for filename, column in (("registro_fundo.csv", "CNPJ_Fundo"), ("registro_classe.csv", "CNPJ_Classe")):
                with archive.open(filename) as stream:
                    for row in csv.DictReader(io.TextIOWrapper(stream, encoding="latin-1"), delimiter=";"):
                        cnpj = _cnpj(row.get(column))
                        if cnpj not in requested or (filename == "registro_classe.csv" and cnpj in output):
                            continue
                        previous = output.get(cnpj, {})
                        if previous and str(previous.get("Data_Inicio_Situacao", "")) > str(row.get("Data_Inicio_Situacao", "")):
                            continue
                        output[cnpj] = {k: row.get(k, "") for k in ("Data_Cancelamento", "Data_Registro", "Data_Inicio_Situacao", "Situacao")}
                        output[cnpj]["source"] = f"CVM {filename}; cache local {path.name}"
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        pass
    return output or _portable_registry_statuses(root, requested)


def resolve_documentary_reference(portfolio, dashboards=None, source_root=None) -> dict:
    declared = {_cnpj(fund.cnpj) for fund in portfolio.funds}
    root = _source_root(source_root)
    caches = _index(_cache_root(source_root))
    dashboards = {_cnpj(k): _dashboard(v) for k, v in (dashboards or {}).items()}
    sets: dict[str, set[str]] = {}
    warnings: list[str] = []
    for cnpj in declared:
        available = {c for cache in caches.get(cnpj, ()) for c in _validated_cache_competences(cache,cnpj,source_root)}
        available.update(c for c, snapshots in _portable_candidates(cnpj, source_root).items() if any(not snapshot[2] for snapshot in snapshots))
        dashboard = dashboards.get(cnpj)
        if dashboard is not None and _dashboard_identity(dashboard, cnpj):
            values = getattr(dashboard, "competencias", [])
            sets[cnpj] = available | set(filter(None, (normalize_documentary_competence(v) for v in values)))
        elif dashboard is not None:
            sets[cnpj] = available
            warnings.append(f"{cnpj}: identidade do IME carregado diverge do CNPJ declarado.")
        else:
            sets[cnpj] = available
    latest = max(set().union(*sets.values()), key=_month_key, default=None)
    statuses = _registry_statuses(root, declared)
    excluded = {}
    if latest:
        latest_date = date(int(latest[3:]), int(latest[:2]), 1)
        for cnpj, status in statuses.items():
            cancelled, registered = _date(status.get("Data_Cancelamento")), _date(status.get("Data_Registro"))
            if cancelled and latest_date > cancelled.replace(day=1):
                excluded[cnpj] = f"Cancelado em {cancelled.strftime('%d/%m/%Y')}; {status['source']}"
            elif registered and latest_date < registered.replace(day=1):
                excluded[cnpj] = f"Registro em {registered.strftime('%d/%m/%Y')} posterior à competência; {status['source']}"
            if registered and any(_month_key(c) < (registered.year, registered.month) for c in sets.get(cnpj, set())):
                warnings.append(f"{cnpj}: existem IMEs anteriores ao registro cadastral {registered.strftime('%d/%m/%Y')}; conferir histórico de enquadramento.")
    eligible = declared - set(excluded)
    missing = sorted(cnpj for cnpj in eligible if not sets[cnpj])
    common = set.intersection(*(sets[cnpj] for cnpj in eligible)) if eligible else set()
    competence = max(common, key=_month_key, default=None)
    if missing:
        warnings.append(f"IME ausente para {len(missing)} de {len(declared)} CNPJs declarados; posição comum da cesta indisponível.")
    elif not competence:
        warnings.append("Sem competência comum entre os CNPJs elegíveis da cesta declarada.")
    if excluded:
        warnings.append("Exclusões usam datas comprovadas no snapshot cadastral CVM; a fonte e a data de cada exclusão estão indicadas.")
    return {"competence": competence, "common_competences": sorted(common, key=_month_key), "declared_count": len(declared), "available_count": sum(bool(sets[c]) for c in declared), "missing_cnpjs": missing, "excluded": excluded, "warnings": warnings, "latest_observed": latest, "eligible_count": len(eligible)}


def _frame_row(dashboard: Any, name: str, competence: str) -> dict:
    frame = getattr(dashboard, name, None)
    if frame is None or getattr(frame, "empty", True) or "competencia" not in frame:
        return {}
    selected = frame[frame["competencia"].map(normalize_documentary_competence).eq(competence)]
    return selected.iloc[-1].to_dict() if not selected.empty else {}


def _dashboard_snapshot(dashboard: Any, cnpj: str, competence: str) -> tuple[dict, dict, str]:
    info = getattr(dashboard, "fund_info", {}) or {}
    source = {"type": "ime_dashboard", "cnpj": cnpj, "competence": competence,
              "reported_fund_cnpj": _cnpj(info.get("cnpj_fundo") or info.get("cnpj")),
              "reported_class_cnpj": _cnpj(info.get("cnpj_classe"))}
    if not _dashboard_identity(dashboard, cnpj):
        return {}, source, f"Identidade do dashboard IME diverge do CNPJ {cnpj}; fundo={source['reported_fund_cnpj'] or 'ausente'}, classe={source['reported_class_cnpj'] or 'ausente'}."
    assets = _frame_row(dashboard, "asset_history_df", competence)
    quotas = _frame_row(dashboard, "subordination_history_df", competence)
    credits = _frame_row(dashboard, "dc_canonical_history_df", competence)
    defaults = _frame_row(dashboard, "default_history_df", competence)
    values = {"net_asset_value": _number(quotas.get("pl_total_oficial")), "credit_rights": _number(credits.get("dc_total_canonico")), "cash": _number(assets.get("disponibilidades")), "pdd": _number(defaults.get("provisao_total")), "overdue_credit": _number(credits.get("dc_vencidos_canonico")), "senior_quotas": None, "subordinated_quotas": None, "mezzanine_quotas": None, "subordinated_and_mezzanine_quotas": None}
    if not quotas.get("pl_reconciliacao_warning", False):
        values.update({"senior_quotas": _number(quotas.get("pl_senior")), "subordinated_quotas": _number(quotas.get("pl_subordinada_strict")), "mezzanine_quotas": _number(quotas.get("pl_mezzanino")), "subordinated_and_mezzanine_quotas": _number(quotas.get("pl_subordinada"))})
    source["fields"] = "asset_history_df; subordination_history_df; dc_canonical_history_df; default_history_df"
    return values, source, ""


@lru_cache(maxsize=16)
def _cache_snapshot(directory: str, files_json: str, cnpj: str, competence: str, mtime: int, identity_root: str = "") -> tuple[dict, dict, str]:
    _ = mtime
    import pandas as pd
    from services.fundonet_dashboard import _build_dc_canonical_history_df, _build_quota_pl_history, _build_subordination_history
    from services.fundonet_parser import _parse_numeric

    cache_dir, files = Path(directory), json.loads(files_json)
    wide_path = _safe_file(cache_dir, files.get("wide_csv_path"))
    rows = []
    try:
        with wide_path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if competence not in (reader.fieldnames or []):
                return {}, {}, "A competência solicitada não consta do CSV IME."
            rows = [{"tag_path": row.get("tag_path", ""), competence: row.get(competence, "")} for row in reader]
    except (OSError, TypeError, AttributeError, csv.Error) as exc:
        return {}, {}, f"CSV IME indisponível: {type(exc).__name__}."
    scalar = {row['tag_path']: row[competence] for row in rows}
    class_id = _header_cnpj(scalar.get("DOC_ARQ/CAB_INFORM/NR_CNPJ_CLASSE"))
    fund_id = _header_cnpj(scalar.get("DOC_ARQ/CAB_INFORM/NR_CNPJ_FUNDO"))
    raw_id = class_id if len(class_id) == 14 else fund_id
    source = {"type": "ime_cache", "cnpj": cnpj, "competence": competence, "path": str(wide_path),
              "reported_fund_cnpj": fund_id, "reported_class_cnpj": class_id,
              "reported_fund_cnpj_raw": scalar.get("DOC_ARQ/CAB_INFORM/NR_CNPJ_FUNDO"),
              "reported_class_cnpj_raw": scalar.get("DOC_ARQ/CAB_INFORM/NR_CNPJ_CLASSE"),
              "identity_basis": "class" if len(class_id) == 14 else "fund", "warnings": []}
    if _cnpj(raw_id) != cnpj:
        mapping = _verified_header_mapping(cnpj,fund_id,class_id,competence,identity_root or None)
        if not mapping:
            return {}, source, f"CNPJ no cabeçalho do IME diverge da regra ({cnpj}); fundo={fund_id or 'ausente'}, classe={class_id or 'ausente'}. Comparação suspensa; vínculo fundo/classe deve ser comprovado."
        source.update(identity_basis="verified_fund_class_inversion", identity_mapping=mapping)
        source["warnings"].append(mapping.get("reason", "Inversão exata fundo/classe comprovada pelo cadastro CVM."))
    # Mini CSVs can contain raw XML decimals ("318511287,13"); canonical
    # dashboard readers expect the parser's numeric Excel values. Keep CNPJs
    # as exact strings, including leading zeros, while using the same parser.
    for row in rows:
        if "NR_CNPJ" not in row["tag_path"]:
            parsed_number = _parse_numeric(str(row[competence]))
            if parsed_number is not None:
                row[competence] = float(parsed_number)
    scalar = {row["tag_path"]: row[competence] for row in rows}
    source["numeric_normalization"] = "FundosNet XML numeric parser; CNPJ strings preserved"
    lists_path = _safe_file(cache_dir, files.get("listas_csv_path"))
    list_rows = []
    if lists_path:
        with lists_path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                if normalize_documentary_competence(row.get("competencia") or row.get("competencia_xml")) == competence and "DESC_SERIE_CLASSE" in row.get("list_group_path", ""):
                    value = row.get("valor_excel", row.get("valor_raw", ""))
                    parsed_number = _parse_numeric(str(value))
                    list_rows.append(dict(row, competencia=competence, valor_excel=float(parsed_number) if parsed_number is not None else value))
    wide = pd.DataFrame(rows).drop_duplicates("tag_path").set_index("tag_path", drop=False)
    credit_frame = _build_dc_canonical_history_df(wide_lookup=wide, competencias=[competence])
    credit = credit_frame.iloc[0].to_dict() if not credit_frame.empty else {}
    fidc_pl_path = "DOC_ARQ/LISTA_INFORM/PATRLIQ/VL_PATRIM_LIQ"
    fiagro_pl_path = "DOC_ARQ/LISTA_INFORM/VL_PATRIMONIO_LIQUIDO"
    fiagro_layout = fiagro_pl_path in scalar and "DOC_ARQ/LISTA_INFORM/INFO_ATIVO/VL_TOTAL_INVEST" in scalar
    official_pl = _number(scalar.get(fiagro_pl_path if fiagro_layout else fidc_pl_path))
    quota = {}
    if official_pl is None or official_pl <= 0:
        pl_reason = "PL oficial ausente ou não numérico" if official_pl is None else "PL oficial declarado igual a zero" if official_pl == 0 else "PL oficial declarado negativo"
        source["warnings"].append(pl_reason + "; saldos por camada não certificados e razão de subordinação não calculável.")
    else:
        try:
            quota_frame = _build_quota_pl_history(wide_lookup=wide, listas_df=pd.DataFrame(list_rows), competencias=[competence])
            quotas = _build_subordination_history(quota_frame, wide_lookup=wide, competencias=[competence])
            quota = quotas.iloc[0].to_dict() if not quotas.empty else {}
            if not quota:
                source["warnings"].append("IME sem linhas de cotas suficientes para reconciliar saldos por camada; ausência preservada.")
            elif quota.get("pl_reconciliacao_warning", False):
                source["warnings"].append("Soma dos saldos de cotas diverge do PL oficial; saldos por camada não certificados.")
        except (ZeroDivisionError, KeyError, ValueError, TypeError) as exc:
            source["warnings"].append(f"Cotas não calculáveis pelo reconciliador canônico ({type(exc).__name__}); PL declarado e demais campos preservados.")
    pdd_paths = ("DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_PROVIS_REDUC_RECUP", "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/DICRED/VL_DICRED_PROVIS_REDUC_RECUP")
    pdds = [_number(scalar.get(path)) for path in pdd_paths]
    quota_paths = ("DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_COTA_FIDC", "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VALORES_MOB/VL_COTA_FIDC")
    reported_quotas = {_number(scalar.get(path)) for path in quota_paths} - {None}
    fidc_quotas = reported_quotas.pop() if len(reported_quotas) == 1 else None
    if len(reported_quotas) > 1:
        source["warnings"].append("Campos de cotas FIDC divergentes no XML; total não certificado.")
    values = {"net_asset_value": official_pl, "credit_rights": _number(credit.get("dc_total_canonico")), "overdue_credit": _number(credit.get("dc_vencidos_canonico")), "cash": _number(scalar.get("DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_DISPONIB")), "pdd": sum(pdds) if all(v is not None for v in pdds) else None, "fidc_quotas": fidc_quotas, "senior_quotas": None, "subordinated_quotas": None, "mezzanine_quotas": None, "subordinated_and_mezzanine_quotas": None}
    cpr_path = "DOC_ARQ/LISTA_INFORM/INFO_ATIVO/DET_VL_TOTAL_INVEST/DET_VL_ATIV_FINAN_LATO_SENSU/DET_TIT_CRED/VL_CPR"
    liquid_assets_path = "DOC_ARQ/LISTA_INFORM/INFO_ATIVO/VL_TOTAL_MANTIDO_NECES_LIQ"
    if fiagro_layout:
        values.update(cpr=_number(scalar.get(cpr_path)), liquid_assets=_number(scalar.get(liquid_assets_path)))
        source["layout"] = "FIAGRO-IME"
        source["warnings"].append("IME de FIAGRO: CPR e ativos para necessidades de liquidez são rubricas próprias; não equivalem automaticamente a direitos creditórios elegíveis ou reserva contratual. Saldos de subclasse sem identificação sênior/mezanino/júnior não demonstram subordinação.")
    if quota and not quota.get("pl_reconciliacao_warning", False):
        values.update({"senior_quotas": _number(quota.get("pl_senior")), "subordinated_quotas": _number(quota.get("pl_subordinada_strict")), "mezzanine_quotas": _number(quota.get("pl_mezzanino")), "subordinated_and_mezzanine_quotas": _number(quota.get("pl_subordinada"))})
    source["fields"] = [key for key, value in values.items() if value is not None]
    source["field_paths"] = {
        "net_asset_value": [fiagro_pl_path if fiagro_layout else fidc_pl_path],
        "cash": ["DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_DISPONIB"],
        "fidc_quotas": [path for path in quota_paths if _number(scalar.get(path)) is not None],
        "pdd": list(pdd_paths),
    }
    if fiagro_layout:
        source["field_paths"].update(cpr=[cpr_path], liquid_assets=[liquid_assets_path])
    docs_path = _safe_file(cache_dir, files.get("docs_csv_path"))
    if docs_path:
        with docs_path.open(encoding="utf-8-sig", newline="") as stream:
            docs = [r for r in csv.DictReader(stream) if normalize_documentary_competence(r.get("competencia") or r.get("competencia_xml")) == competence]
        if docs:
            doc = max(docs, key=lambda d: _source_authority({"version": d.get("versao"), "delivered_at": d.get("data_entrega"), "document_id": d.get("documento_id")}))
            source.update({"document_id": doc.get("documento_id"), "version": doc.get("versao"), "delivered_at": doc.get("data_entrega"), "url": f"https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id={doc.get('documento_id')}"})
    return values, source, ""


def _source_authority(source: Mapping) -> tuple[float, str, float]:
    delivered_text = str(source.get("delivered_at") or "").strip()
    delivered = ""
    for pattern in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            delivered = datetime.strptime(delivered_text, pattern).isoformat()
            break
        except ValueError:
            pass
    if not delivered:
        try:
            delivered = datetime.fromisoformat(delivered_text.replace("Z", "+00:00")).replace(tzinfo=None).isoformat()
        except ValueError:
            pass
    return _number(source.get("version")) or 0.0, delivered, _number(source.get("document_id")) or 0.0


def _snapshot(cnpj: str, competence: str, dashboard: Any, cache_root: object) -> tuple[dict, dict, str]:
    snapshots = list(_portable_candidates(cnpj, cache_root).get(competence, ()))
    if dashboard is not None:
        dashboard_snapshot = _dashboard_snapshot(_dashboard(dashboard), cnpj, competence)
        if dashboard_snapshot[2]:
            return dashboard_snapshot
        snapshots.append(dashboard_snapshot)
    root = _cache_root(cache_root)
    candidates = [c for c in _index(root).get(cnpj, ()) if competence in c["competences"]]
    def authority(cache):
        docs_path = _safe_file(Path(cache["directory"]), cache["files"].get("docs_csv_path"))
        latest = (0.0, "", 0.0)
        if docs_path:
            with docs_path.open(encoding="utf-8-sig", newline="") as stream:
                for doc in csv.DictReader(stream):
                    if normalize_documentary_competence(doc.get("competencia") or doc.get("competencia_xml")) == competence:
                        latest = max(latest, _source_authority({"version": doc.get("versao"), "delivered_at": doc.get("data_entrega"), "document_id": doc.get("documento_id")}))
        return latest
    if candidates:
        cache = max(candidates, key=authority)
        stamps = [path.stat().st_mtime_ns for name in ("wide_csv_path", "listas_csv_path", "docs_csv_path") if (path := _safe_file(Path(cache["directory"]), cache["files"].get(name)))]
        snapshots.append(_cache_snapshot(cache["directory"], json.dumps(cache["files"], sort_keys=True), cnpj, competence, max(stamps), str(cache_root) if cache_root else ""))
    valid = [snapshot for snapshot in snapshots if not snapshot[2]]
    if valid:
        return max(valid, key=lambda snapshot: (_source_authority(snapshot[1]), snapshot[1].get("type") == "ime_document"))
    return snapshots[0] if snapshots else ({}, {}, "Não há IME local ou publicado desse CNPJ na competência comum solicitada.")


_ALIASES = {"pl": "net_asset_value", "PL": "net_asset_value", "direitos_creditorios": "credit_rights", "subordinadas": "subordinated_quotas", "disponibilidades": "cash", "PDD": "pdd"}
_UNITS = {"percent": 100.0, "%": 100.0, "ratio": 1.0}
_CONTEXT_CRITERIA = {
    "allocation": ("credit_rights", "net_asset_value", "percent", "Direitos creditórios / PL", "Alocação contém bases, ativos elegíveis ou percentuais distintos; fórmula única ainda não demonstrada."),
    "tax_allocation": ("credit_rights", "net_asset_value", "percent", "Direitos creditórios / PL", "Enquadramento tributário exige ativos elegíveis, prazo e regime fiscal da classe; o agregado mensal não certifica esses requisitos."),
    "subordination": ("subordinated_and_mezzanine_quotas", "net_asset_value", "percent", "Mezanino + subordinadas / PL", "Proteção agregada não resolve a fórmula, a camada ou a série da subordinação contratual."),
    "coverage": (None, None, "", "", "Cobertura contratual exige saldos, valor presente ou fatores de cada camada; os dados agregados não reproduzem a fórmula."),
    "liquidity_reserve": ("cash", None, "currency", "Disponibilidades", "Reserva contratual exige segregação, ativos elegíveis, cronograma ou despesas; disponibilidades agregadas não comprovam a reserva."),
    "expense_reserve": ("cash", None, "currency", "Disponibilidades", "Reserva de despesas depende da base de encargos e da segregação previstas; disponibilidades não demonstram meses de despesas cobertos."),
    "pdd": ("pdd", "credit_rights", "percent", "PDD / direitos creditórios", "A curva de PDD requer atraso, contágio e garantias por operação; o agregado mensal não demonstra aplicação da metodologia."),
    "concentration": (None, None, "", "", "Limite por devedor, cedente ou grupo exige exposição individual e agregação de vínculos; esse perímetro não foi reconciliado no snapshot disponível."),
}


def _unreproduced_rule_context(criterion, values, row, ime_error):
    ident = criterion.get("criterion_id")
    spec = _CONTEXT_CRITERIA.get(ident)
    if not spec or criterion.get("status") != "confirmed" or criterion.get("applicability") != "applicable":
        return row
    num_key, den_key, unit, label, reason = spec
    row.update(comparison_required=True, reason=reason, context_formula=label,
               context_value=None, context_unit=unit)
    if ime_error:
        row.update(status="ime_unavailable", reason=ime_error + " " + reason)
        return row
    num, den = values.get(num_key), values.get(den_key) if den_key else None
    if num is not None and (not den_key or (den is not None and den > 0)):
        row["context_value"] = num if not den_key else num / den * 100
    return row


def build_documentary_observations(fund_json, *, competence, dashboard=None, cache_root=None) -> list[dict]:
    competence = normalize_documentary_competence(competence)
    cnpj = _cnpj(fund_json.get("cnpj"))
    needs_ime = any(criterion.get("rule") or (criterion.get("criterion_id") in _CONTEXT_CRITERIA and criterion.get("status") == "confirmed") for criterion in fund_json.get("criteria", []))
    values, ime_source, ime_error = _snapshot(cnpj, competence, dashboard, cache_root) if competence and needs_ime else ({}, {}, "Cesta sem competência comum para todos os CNPJs elegíveis.")
    output = []
    for criterion in fund_json.get("criteria", []):
        rule = criterion.get("rule") or {}
        row = {"criterion_id": criterion.get("criterion_id"), "observed_value": None, "unit": rule.get("unit", ""), "competence": competence, "status": "not_comparable", "reason": "Critério qualitativo ou sem fórmula contratual reproduzível no IME.", "formula": "", "source": ime_source, "headroom": None, "limit": rule.get("limit")}
        numerator = _ALIASES.get(rule.get("numerator"), rule.get("numerator"))
        denominator = _ALIASES.get(rule.get("denominator"), rule.get("denominator"))
        unit, operator, limit = rule.get("unit"), rule.get("operator"), _number(rule.get("limit"))
        if not rule:
            row = _unreproduced_rule_context(criterion, values, row, ime_error)
            output.append(row); continue
        if not competence or ime_error:
            row.update(status="ime_unavailable", reason=ime_error); output.append(row); continue
        if str(criterion.get("applicability", "")).lower() in {"not_applicable", "nao_aplicavel", "não aplicável"}:
            row["reason"] = "Critério documentado como não aplicável ao fundo/classe."
            output.append(row); continue
        if str(criterion.get("status", "")).lower() != "confirmed":
            row["reason"] = "Regra com conflito ou ausência documental ainda não resolvidos; comparação suspensa."
            output.append(row); continue
        if criterion.get("applicability") != "applicable":
            row["reason"] = "Aplicabilidade da regra ao fundo/classe ainda não demonstrada."
            output.append(row); continue
        sources = criterion.get("sources") or []
        valid_source = any(s.get("document_id") and (s.get("page") or s.get("clause")) and (s.get("reference_date") or s.get("version")) and s.get("identity_verified") is not False for s in sources)
        if not valid_source or (rule.get("cnpj") and _cnpj(rule["cnpj"]) != cnpj):
            row["reason"] = "Regra sem identidade, versão e localização documental verificáveis."
            output.append(row); continue
        if rule.get("layer") not in {"fund", "fundo", "class", "classe", cnpj}:
            row["reason"] = "Regra de subclasse/série exige saldo individual; IME disponível é agregado."
            output.append(row); continue
        year, month = _month_key(competence)
        cutoff = date(year, month, calendar.monthrange(year, month)[1])
        effective_from, effective_to = _date(rule.get("effective_from")), _date(rule.get("effective_to"))
        source_dates = [_date(s.get("reference_date")) for s in sources]
        version_outside = (effective_from and cutoff < effective_from) or (effective_to and cutoff > effective_to) or (not effective_from and any(d and cutoff < d for d in source_dates))
        if unit not in _UNITS or operator not in {">=", ">", "<=", "<", "==", "="} or limit is None or numerator not in values or denominator not in values:
            if version_outside:
                row.update(status="version_not_applicable", reason="Versão da regra fora da competência IME; recuperar o regulamento vigente nessa data. Base contratual também não reproduzível no IME disponível.")
            else:
                row["reason"] = "Operador, unidade, numerador ou base contratual sem correspondência exata no IME; proxies de PL/ativos não são intercambiáveis."
            if criterion.get("criterion_id") == "allocation" and values.get("cpr") is not None and values.get("net_asset_value") is not None and values["net_asset_value"] > 0:
                row.update(comparison_required=True, context_value=values["cpr"] / values["net_asset_value"] * 100,
                           context_unit="percent", context_formula="CPR / PL (rubrica declarada no FIAGRO)")
                row["reason"] += " CPR declarada no FIAGRO não comprova elegibilidade individual nem correspondência integral com a definição contratual de direitos creditórios do agronegócio."
            output.append(row); continue
        row["formula"] = f"{numerator} / {denominator}" + (" × 100" if _UNITS[unit] == 100 else "")
        num, den = values[numerator], values[denominator]
        if den is not None and den <= 0:
            row["reason"] = "Denominador IME nulo ou negativo; razão contratual não calculável."
            output.append(row); continue
        if num is None or den is None:
            row.update(status="ime_unavailable", reason="Campo IME ausente ou cotas não reconciliadas; ausência preservada sem substituir por zero.")
            output.append(row); continue
        observed = num / den * _UNITS[unit]
        row["observed_value"] = observed
        if version_outside:
            row.update(status="version_not_applicable", reason="Versão da regra fora da competência IME; recuperar o regulamento vigente nessa data.")
            output.append(row); continue
        if not effective_from or rule.get("effective_status") == "document_date_only":
            row["reason"] = "Vigência efetiva não comprovada; data do documento isolada não certifica enquadramento histórico."
            output.append(row); continue
        initial_days = _number(rule.get("initial_days"))
        if initial_days is not None or rule.get("requires_initial_date"):
            initial_date = _date(rule.get("initial_date"))
            if not initial_date:
                row["reason"] = "Carência inicial da regra depende de data de início/primeira integralização ainda não comprovada."
                output.append(row); continue
            if initial_days is None:
                row["reason"] = "Prazo inicial da regra ainda sem parâmetro contratual verificável; confronto de enquadramento suspenso."
                output.append(row); continue
            if initial_days < 0 or cutoff < initial_date + timedelta(days=initial_days):
                row.update(status="version_not_applicable", reason="Regra ainda dentro da carência inicial na competência observada.")
                output.append(row); continue
        if rule.get("requires_senior_outstanding"):
            senior = values.get("senior_quotas")
            if senior is None:
                row["reason"] = "Regra exige cotas seniores em circulação; saldo sênior reconciliado não identificado no IME."
                output.append(row); continue
            if senior <= 0:
                row["reason"] = "Regra condicionada a cotas seniores em circulação; condição não presente no snapshot mensal."
                output.append(row); continue
        lower = operator in {">=", ">"}
        row["headroom"] = observed - limit if lower else limit - observed
        conforms = {">=": observed >= limit, ">": observed > limit, "<=": observed <= limit, "<": observed < limit, "==": math.isclose(observed, limit), "=": math.isclose(observed, limit)}[operator]
        row["status"] = "compliant_snapshot" if conforms else "observed_below_limit" if observed < limit else "observed_above_limit"
        reason = "Observação na posição mensal; comparação reproduz a base contratual explicitada."
        if str(rule.get("frequency", "")).lower() not in {"monthly", "mensal", "month_end", "fim_do_mes"}:
            reason += " IME mensal não comprova apuração diária/contínua."
        if rule.get("cure_days") is not None:
            reason += f" Prazo de cura de {rule['cure_days']} {rule.get('cure_unit') or 'dias'} não aferido pelo snapshot mensal."
        row["reason"] = reason
        output.append(row)
    return output
