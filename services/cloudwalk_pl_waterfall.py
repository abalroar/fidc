from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from services.fundonet_dashboard import (
    OFFICIAL_PL_PATH,
    _build_event_history,
    _competencia_sort_key,
    _extract_competencias,
    _get_wide_series,
)
from services.ime_loader import DEFAULT_PORTABLE_CACHE_ROOT, DEFAULT_RUNTIME_CACHE_ROOT, materialize_latest_portable_cache_for_cnpj
from services.waterfall_schedule import only_digits


@dataclass(frozen=True)
class CloudwalkPlWaterfall:
    summary_df: pd.DataFrame
    by_fund_df: pd.DataFrame
    steps_df: pd.DataFrame


def build_cloudwalk_pl_waterfall(
    cnpjs: Iterable[str],
    *,
    fund_names: dict[str, str] | None = None,
    year: int | None = None,
    end_date: date | None = None,
    cache_root: str | Path = DEFAULT_RUNTIME_CACHE_ROOT,
    portable_cache_root: str | Path | None = DEFAULT_PORTABLE_CACHE_ROOT,
) -> CloudwalkPlWaterfall:
    runtime_cache_root = Path(cache_root)
    portable_root = Path(portable_cache_root) if portable_cache_root is not None else None
    cnpj_list = sorted({only_digits(cnpj) for cnpj in cnpjs if only_digits(cnpj)})
    names = {only_digits(key): value for key, value in (fund_names or {}).items()}
    target_year = int(year or (end_date.year if end_date else date.today().year))
    start_comp = f"12/{target_year - 1}"
    max_end_comp = f"{(end_date.month if end_date else 12):02d}/{target_year}" if end_date else f"12/{target_year}"

    rows: list[dict[str, object]] = []
    for cnpj in cnpj_list:
        fund_name = names.get(cnpj, cnpj)
        cached = _find_latest_cached_ime(cnpj, runtime_cache_root)
        if cached is None and portable_root is not None:
            materialized = materialize_latest_portable_cache_for_cnpj(
                cnpj,
                runtime_cache_root=runtime_cache_root,
                portable_cache_root=portable_root,
            )
            if materialized is not None:
                cached = _find_latest_cached_ime(cnpj, runtime_cache_root)
        if cached is None:
            rows.append(_empty_row(fund_name, cnpj, start_comp, max_end_comp, "Sem IME em cache."))
            continue
        rows.append(_fund_waterfall_row(fund_name, cnpj, cached, start_comp=start_comp, max_end_comp=max_end_comp))

    by_fund_df = pd.DataFrame(rows)
    if by_fund_df.empty:
        by_fund_df = pd.DataFrame(columns=_by_fund_columns())
    summary = {
        "pl_inicial": _sum(by_fund_df, "pl_inicial"),
        "captacoes": _sum(by_fund_df, "captacoes"),
        "resgates": _sum(by_fund_df, "resgates"),
        "amortizacoes": _sum(by_fund_df, "amortizacoes"),
        "accrual_rentabilidade_residual": _sum(by_fund_df, "accrual_rentabilidade_residual"),
        "pl_final": _sum(by_fund_df, "pl_final"),
        "fundos": int(len(by_fund_df.index)),
        "fundos_com_ime": int(pd.to_numeric(by_fund_df.get("pl_final"), errors="coerce").fillna(0.0).gt(0).sum()),
        "start_comp": start_comp,
        "max_end_comp": max_end_comp,
    }
    summary_df = pd.DataFrame([summary])
    steps_df = _steps_frame(summary)
    return CloudwalkPlWaterfall(summary_df=summary_df, by_fund_df=by_fund_df, steps_df=steps_df)


def _fund_waterfall_row(
    fund_name: str,
    cnpj: str,
    cached: dict[str, object],
    *,
    start_comp: str,
    max_end_comp: str,
) -> dict[str, object]:
    cache_dir = Path(str(cached["cache_dir"]))
    wide_path = cache_dir / str(cached["wide_csv_path"])
    listas_path = cache_dir / str(cached["listas_csv_path"])
    wide_df = pd.read_csv(wide_path, dtype="object")
    listas_df = pd.read_csv(listas_path, dtype="object") if listas_path.exists() else pd.DataFrame()
    competencias = [
        competencia
        for competencia in _extract_competencias(wide_df)
        if _competencia_sort_key(competencia) <= _competencia_sort_key(max_end_comp)
    ]
    if not competencias:
        return _empty_row(fund_name, cnpj, start_comp, max_end_comp, "Sem competências no intervalo.")

    wide_lookup = wide_df.set_index("tag_path")
    pl_series = pd.to_numeric(_get_wide_series(wide_lookup, competencias, OFFICIAL_PL_PATH), errors="coerce")
    available = pl_series.dropna()
    if available.empty:
        return _empty_row(fund_name, cnpj, start_comp, max_end_comp, "Sem PL oficial no IME.")

    start_candidates = [comp for comp in available.index if _competencia_sort_key(comp) <= _competencia_sort_key(start_comp)]
    effective_start = start_candidates[-1] if start_candidates else available.index[0]
    end_candidates = [comp for comp in available.index if _competencia_sort_key(comp) <= _competencia_sort_key(max_end_comp)]
    effective_end = end_candidates[-1] if end_candidates else available.index[-1]
    if _competencia_sort_key(effective_end) < _competencia_sort_key(effective_start):
        effective_start = available.index[0]

    pl_inicial = float(pl_series.loc[effective_start])
    pl_final = float(pl_series.loc[effective_end])
    event_history = _build_event_history(wide_lookup=wide_lookup, listas_df=listas_df, competencias=competencias)
    if event_history.empty:
        period_events = event_history
    else:
        event_ord = event_history["competencia"].map(_competencia_ordinal)
        start_ord = _competencia_ordinal(effective_start)
        end_ord = _competencia_ordinal(effective_end)
        period_events = event_history[
            event_ord.gt(start_ord)
            & event_ord.le(end_ord)
        ].copy()
    captacoes = _event_sum(period_events, "emissao")
    resgates = _event_sum(period_events, "resgate")
    amortizacoes = _event_sum(period_events, "amortizacao")
    residual = pl_final - pl_inicial - captacoes + resgates + amortizacoes
    return {
        "fund_name": fund_name,
        "short_name": _short_name(fund_name),
        "cnpj": cnpj,
        "start_comp": effective_start,
        "end_comp": effective_end,
        "pl_inicial": round(pl_inicial, 2),
        "captacoes": round(captacoes, 2),
        "resgates": round(resgates, 2),
        "amortizacoes": round(amortizacoes, 2),
        "accrual_rentabilidade_residual": round(residual, 2),
        "pl_final": round(pl_final, 2),
        "event_rows": int(len(period_events.index)) if not period_events.empty else 0,
        "source": str(cache_dir),
        "status": "ok",
    }


def _event_sum(event_history: pd.DataFrame, event_type: str) -> float:
    if event_history.empty:
        return 0.0
    subset = event_history[event_history["event_type"].eq(event_type)]
    if subset.empty:
        return 0.0
    return float(pd.to_numeric(subset["valor_total"], errors="coerce").fillna(0.0).sum())


def _steps_frame(summary: dict[str, object]) -> pd.DataFrame:
    rows = [
        ("PL inicial", float(summary["pl_inicial"]), "total"),
        ("Captações", float(summary["captacoes"]), "relative"),
        ("Resgates", -float(summary["resgates"]), "relative"),
        ("Amortizações", -float(summary["amortizacoes"]), "relative"),
        ("Accrual / rentab.", float(summary["accrual_rentabilidade_residual"]), "relative"),
        ("PL final", float(summary["pl_final"]), "total"),
    ]
    return pd.DataFrame(rows, columns=["etapa", "valor", "measure"])


def _find_latest_cached_ime(cnpj: str, cache_root: Path) -> dict[str, object] | None:
    if not cache_root.exists():
        return None
    candidates: list[dict[str, object]] = []
    for manifest_path in cache_root.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if only_digits(manifest.get("cnpj_fundo")) != cnpj:
            continue
        files = manifest.get("files") or {}
        wide = files.get("wide_csv_path")
        if not wide or not (manifest_path.parent / str(wide)).exists():
            continue
        competencias = manifest.get("competencias") or []
        latest_comp = max(competencias, key=_competencia_sort_key) if competencias else ""
        candidates.append(
            {
                "cache_dir": manifest_path.parent,
                "wide_csv_path": wide,
                "listas_csv_path": files.get("listas_csv_path") or "estruturas_lista.csv",
                "latest_competencia": latest_comp,
            }
        )
    if not candidates:
        return None
    return max(candidates, key=lambda item: _competencia_sort_key(str(item.get("latest_competencia") or "01/1900")))


def _competencia_ordinal(label: str) -> int:
    year, month = _competencia_sort_key(label)
    return year * 12 + month


def _empty_row(fund_name: str, cnpj: str, start_comp: str, end_comp: str, status: str) -> dict[str, object]:
    return {
        "fund_name": fund_name,
        "short_name": _short_name(fund_name),
        "cnpj": cnpj,
        "start_comp": start_comp,
        "end_comp": end_comp,
        "pl_inicial": 0.0,
        "captacoes": 0.0,
        "resgates": 0.0,
        "amortizacoes": 0.0,
        "accrual_rentabilidade_residual": 0.0,
        "pl_final": 0.0,
        "event_rows": 0,
        "source": "",
        "status": status,
    }


def _by_fund_columns() -> list[str]:
    return list(_empty_row("", "", "", "", "").keys())


def _sum(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0.0).sum())


def _short_name(name: str) -> str:
    text = str(name or "").upper()
    for token in [
        "CLOUDWALK",
        "FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS",
        "FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA",
        "FIDC",
        "SEGMENTO MEIOS DE PAGAMENTO",
        "RESPONSABILIDADE LIMITADA",
    ]:
        text = text.replace(token, " ")
    return " ".join(text.title().split()) or str(name or "")
