from __future__ import annotations

import argparse
import calendar
from html import escape
import json
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from services.cvm_cadastro import list_fidc_catalog
from services.fundonet_dashboard import build_dashboard_data, _competencia_sort_key
from services.waterfall_schedule import (
    only_digits,
    parse_amortization_schedule,
    parse_date_label,
    parse_money_value,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EMISSIONS_CSV = ROOT / "data/regulatory_profiles/cloudwalk_cotas_emissoes_pagamentos.csv"
DEFAULT_PORTFOLIOS_JSON = ROOT / "portfolios.json"
DEFAULT_CACHE_ROOT = ROOT / ".cache/fundonet-ime"
DEFAULT_OUTPUT_DIR = ROOT / "reports/cloudwalk_runoff_waterfall_20260618"

YEAR_BUCKETS = ("2026", "2027", "2028", "2029+")
FUND_COLORS = {
    "Kick Ass I": "#1f4e79",
    "Akira I": "#ed7d31",
    "Akira II": "#70ad47",
    "Big Picture I": "#5b9bd5",
    "Big Picture II": "#a5a5a5",
    "Big Picture III": "#ffc000",
    "Big Picture IV": "#4472c4",
    "Cloudwalk A.I.": "#9e480e",
    "Cloudwalk PI": "#8064a2",
    "Bela": "#c00000",
    "Kick Ass II": "#7f7f7f",
}


@dataclass(frozen=True)
class CacheHit:
    latest_competencia: str
    cache_dir: Path
    wide_csv_path: Path
    listas_csv_path: Path
    docs_csv_path: Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera waterfall de run-off do PL atual dos FIDCs Cloudwalk.")
    parser.add_argument("--emissions-csv", type=Path, default=DEFAULT_EMISSIONS_CSV)
    parser.add_argument("--portfolios-json", type=Path, default=DEFAULT_PORTFOLIOS_JSON)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    funds = _load_cloudwalk_funds(args.portfolios_json)
    cnpj_to_short = {item["cnpj"]: item["short_name"] for item in funds}
    current_snapshot_df, class_snapshot_df = _current_pl_snapshot(
        funds,
        cache_root=args.cache_root,
    )
    schedule_df, schedule_audit_df = _schedule_by_year(
        args.emissions_csv,
        cnpj_to_short=cnpj_to_short,
        current_snapshot_df=current_snapshot_df,
    )
    allocation_df = _allocate_current_pl(current_snapshot_df, class_snapshot_df, schedule_df)
    year_fund_df = (
        allocation_df.groupby(["bucket", "short_name"], as_index=False)["allocated_pl"].sum()
        if not allocation_df.empty
        else pd.DataFrame(columns=["bucket", "short_name", "allocated_pl"])
    )
    year_summary_df = _year_summary(allocation_df)

    _write_outputs(
        output_dir=args.output_dir,
        current_snapshot_df=current_snapshot_df,
        class_snapshot_df=class_snapshot_df,
        schedule_df=schedule_df,
        schedule_audit_df=schedule_audit_df,
        allocation_df=allocation_df,
        year_fund_df=year_fund_df,
        year_summary_df=year_summary_df,
    )
    _plot_waterfall(
        year_fund_df=year_fund_df,
        current_snapshot_df=current_snapshot_df,
        output_dir=args.output_dir,
    )
    _write_methodology(
        output_dir=args.output_dir,
        current_snapshot_df=current_snapshot_df,
        allocation_df=allocation_df,
        schedule_audit_df=schedule_audit_df,
    )
    print(f"Pacote gerado em: {args.output_dir}")
    print(year_summary_df.to_string(index=False))


def _load_cloudwalk_funds(portfolios_json: Path) -> list[dict[str, str]]:
    payload = json.loads(portfolios_json.read_text(encoding="utf-8"))
    portfolio = next(
        item for item in payload.get("portfolios", []) if "Cloudwalk" in str(item.get("name", ""))
    )
    funds: list[dict[str, str]] = []
    for item in portfolio.get("funds", []):
        cnpj = only_digits(item.get("cnpj"))
        name = str(item.get("display_name") or "").strip()
        funds.append(
            {
                "cnpj": cnpj,
                "fund_name": name,
                "short_name": _short_name(name),
            }
        )
    return funds


def _current_pl_snapshot(
    funds: Iterable[dict[str, str]],
    *,
    cache_root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    catalog = list_fidc_catalog()
    catalog = catalog.assign(cnpj_norm=catalog["cnpj_fundo"].map(only_digits)) if not catalog.empty else catalog
    rows: list[dict[str, object]] = []
    class_rows: list[dict[str, object]] = []
    for fund in funds:
        cnpj = fund["cnpj"]
        short_name = fund["short_name"]
        cache_hit = _find_latest_cached_ime(cnpj, cache_root)
        catalog_row = (
            catalog[catalog["cnpj_norm"].eq(cnpj)].iloc[0].to_dict()
            if not catalog.empty and not catalog[catalog["cnpj_norm"].eq(cnpj)].empty
            else {}
        )
        if cache_hit is None:
            rows.append(
                {
                    **fund,
                    "latest_competencia": "",
                    "competencia_base_date": "",
                    "pl_atual": 0.0,
                    "situacao_cvm": catalog_row.get("situacao", ""),
                    "cache_status": "sem_ime_cache",
                    "cache_dir": "",
                }
            )
            continue
        try:
            dashboard = build_dashboard_data(
                wide_csv_path=cache_hit.wide_csv_path,
                listas_csv_path=cache_hit.listas_csv_path,
                docs_csv_path=cache_hit.docs_csv_path,
            )
            latest_comp = dashboard.latest_competencia
            base_date = _month_end_from_competencia(latest_comp)
            pl_total = float(dashboard.summary.get("pl_total") or 0.0)
            rows.append(
                {
                    **fund,
                    "latest_competencia": latest_comp,
                    "competencia_base_date": base_date.isoformat(),
                    "pl_atual": pl_total,
                    "situacao_cvm": catalog_row.get("situacao", ""),
                    "cache_status": "ok",
                    "cache_dir": str(cache_hit.cache_dir),
                }
            )
            quota_df = dashboard.quota_pl_history_df.copy()
            if not quota_df.empty:
                quota_df = quota_df[quota_df["competencia"].astype(str).eq(str(latest_comp))].copy()
                for _, quota_row in quota_df.iterrows():
                    class_rows.append(
                        {
                            **fund,
                            "competencia": latest_comp,
                            "class_kind": quota_row.get("class_kind", ""),
                            "class_macro": quota_row.get("class_macro", ""),
                            "class_label": quota_row.get("class_label", ""),
                            "qt_cotas": quota_row.get("qt_cotas", 0.0),
                            "vl_cota": quota_row.get("vl_cota", 0.0),
                            "pl_classe": quota_row.get("pl", 0.0),
                            "pl_share_pct": quota_row.get("pl_share_pct", 0.0),
                            "pl_reconciliacao_role": quota_row.get("pl_reconciliacao_role", ""),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    **fund,
                    "latest_competencia": cache_hit.latest_competencia,
                    "competencia_base_date": "",
                    "pl_atual": 0.0,
                    "situacao_cvm": catalog_row.get("situacao", ""),
                    "cache_status": f"erro_dashboard: {exc}",
                    "cache_dir": str(cache_hit.cache_dir),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(class_rows)


def _find_latest_cached_ime(cnpj: str, cache_root: Path) -> CacheHit | None:
    candidates: list[CacheHit] = []
    for manifest_path in cache_root.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if only_digits(manifest.get("cnpj_fundo")) != cnpj:
            continue
        competencias = manifest.get("competencias") or []
        if not competencias:
            continue
        files = manifest.get("files") or {}
        cache_dir = manifest_path.parent
        wide_csv = cache_dir / str(files.get("wide_csv_path") or "informes_wide.csv")
        listas_csv = cache_dir / str(files.get("listas_csv_path") or "estruturas_lista.csv")
        docs_csv = cache_dir / str(files.get("docs_csv_path") or "documentos_filtrados.csv")
        if not (wide_csv.exists() and listas_csv.exists() and docs_csv.exists()):
            continue
        latest = max(competencias, key=_competencia_sort_key)
        candidates.append(CacheHit(latest, cache_dir, wide_csv, listas_csv, docs_csv))
    if not candidates:
        return None
    return max(candidates, key=lambda item: _competencia_sort_key(item.latest_competencia))


def _schedule_by_year(
    emissions_csv: Path,
    *,
    cnpj_to_short: dict[str, str],
    current_snapshot_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = pd.read_csv(emissions_csv, dtype=str, keep_default_na=False)
    schedule_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    base_dates = current_snapshot_df.set_index("cnpj")["competencia_base_date"].to_dict()
    current_pl = current_snapshot_df.set_index("cnpj")["pl_atual"].to_dict()

    for _, row in frame.iterrows():
        cnpj = only_digits(row.get("CNPJ"))
        if cnpj not in cnpj_to_short:
            continue
        short_name = cnpj_to_short[cnpj]
        tipo = str(row.get("Tipo") or "")
        classe = str(row.get("Cota/Classe") or "")
        class_key = _schedule_class_key(short_name, tipo, classe)
        volume = parse_money_value(row.get("Volume"))
        if volume <= 0.0:
            audit_rows.append(_audit_row(row, cnpj, cnpj_to_short, "excluido", "Volume ausente/zero."))
            continue
        try:
            convention, full_schedule, warnings = _parse_documentary_schedule(row.get("Amortização principal"), volume)
        except ValueError as exc:
            audit_rows.append(_audit_row(row, cnpj, cnpj_to_short, "excluido", str(exc)))
            continue
        base_date = _parse_iso_date(base_dates.get(cnpj))
        if base_date is None:
            audit_rows.append(_audit_row(row, cnpj, cnpj_to_short, "excluido", "Sem data-base de PL atual."))
            continue
        future_schedule = [(item_date, amount) for item_date, amount in full_schedule if item_date > base_date]
        if not future_schedule:
            audit_rows.append(_audit_row(row, cnpj, cnpj_to_short, "sem_evento_futuro", "Cronograma sem principal futuro após a competência-base."))
            continue
        fund_current_pl = float(current_pl.get(cnpj) or 0.0)
        if fund_current_pl <= 0.0:
            audit_rows.append(_audit_row(row, cnpj, cnpj_to_short, "sem_pl_atual", "PL atual oficial zerado ou ausente."))
            continue
        total_future = sum(amount for _, amount in future_schedule)
        for item_date, amount in future_schedule:
            bucket = _year_bucket(item_date)
            schedule_rows.append(
                {
                    "short_name": short_name,
                    "cnpj": cnpj,
                    "fund_name": row.get("Fundo"),
                    "classe": classe,
                    "tipo": tipo,
                    "class_key": class_key,
                    "source": row.get("Fonte"),
                    "status_evidencia": row.get("Status/evidência"),
                    "convention": convention,
                    "warning": "; ".join(warnings),
                    "data_amortizacao": item_date.isoformat(),
                    "bucket": bucket,
                    "scheduled_original_amount": amount,
                    "scheduled_original_share_remaining": amount / total_future if total_future else 0.0,
                }
            )
        audit_rows.append(_audit_row(row, cnpj, cnpj_to_short, "incluido", f"{len(future_schedule)} datas futuras após {base_date.isoformat()}."))
    return pd.DataFrame(schedule_rows), pd.DataFrame(audit_rows)


def _parse_documentary_schedule(
    text: object,
    volume: float,
) -> tuple[str, list[tuple[date, float]], tuple[str, ...]]:
    try:
        return parse_amortization_schedule(text, volume)
    except ValueError as exc:
        ranged = _parse_linear_range_schedule(text, volume)
        if ranged is not None:
            return ranged
        raise exc


def _parse_linear_range_schedule(
    text: object,
    volume: float,
) -> tuple[str, list[tuple[date, float]], tuple[str, ...]] | None:
    raw = str(text or "")
    normalized = _ascii(raw)
    if "amortizacao programada de" not in normalized:
        return None
    dates = _dates_in_schedule_text(raw)
    if len(dates) < 2:
        return None
    start, end = dates[0], dates[-1]
    if end < start:
        raise ValueError("Intervalo de amortização programada termina antes do início.")

    schedule_dates: list[date] = []
    index = 0
    while index <= 240:
        item_date = _add_months_preserve_day(start, index)
        if item_date > end:
            break
        schedule_dates.append(item_date)
        if item_date == end:
            break
        index += 1
    if not schedule_dates or schedule_dates[-1] != end:
        schedule_dates.append(end)

    amount = volume / len(schedule_dates)
    return (
        "linear_range",
        [(item_date, amount) for item_date in schedule_dates],
        ("Cronograma documental informa intervalo de amortização sem percentuais; waterfall usa parcelas mensais lineares.",),
    )


def _dates_in_schedule_text(text: str) -> list[date]:
    output: list[date] = []
    seen: set[date] = set()
    for match in re.finditer(r"\d{1,2}/\d{1,2}/\d{2,4}", text):
        parsed = parse_date_label(match.group(0))
        if parsed is not None and parsed not in seen:
            output.append(parsed)
            seen.add(parsed)
    return output


def _add_months_preserve_day(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _schedule_class_key(short_name: str, tipo: str, classe: str) -> str:
    text = _ascii(f"{tipo} {classe}")
    if "senior" in text:
        return "senior_2" if "2a serie" in text or "serie 2" in text else "senior_1"
    if "mezanino" in text or "mezzanino" in text:
        if short_name == "Bela":
            if "2a serie" in text and _has_class_suffix(text, "b"):
                return "mezz_bela_2b"
            if "2a serie" in text:
                return "mezz_bela_2a"
            if _has_class_suffix(text, "b"):
                return "mezz_bela_1b"
            return "mezz_bela_1a"
        if short_name == "Cloudwalk PI":
            return "mezz_pi_b" if _has_class_suffix(text, "b") else "mezz_pi_a"
        return "mezz_1"
    if "subordin" in text:
        return "subordinada_1"
    return "classe_" + re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _pl_class_key(class_row: pd.Series) -> str:
    short_name = str(class_row.get("short_name") or "")
    text = _ascii(
        " ".join(
            [
                str(class_row.get("class_label") or ""),
                str(class_row.get("class_macro") or ""),
                str(class_row.get("class_kind") or ""),
            ]
        )
    )
    if "senior" in text:
        return "senior_2" if "serie 2" in text else "senior_1"
    if "mezanino" in text or "mezzanino" in text:
        if short_name == "Bela":
            series = _first_int_after_token(text, "serie")
            return {
                1: "mezz_bela_1a",
                2: "mezz_bela_1b",
                3: "mezz_bela_2a",
                4: "mezz_bela_2b",
            }.get(series, "mezz_bela_1a")
        if short_name == "Cloudwalk PI":
            return "mezz_pi_b" if "mezanino 2" in text or "mezzanino 2" in text else "mezz_pi_a"
        return "mezz_1"
    if "subordin" in text:
        return "subordinada_1"
    return "classe_" + re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _has_class_suffix(text: str, suffix: str) -> bool:
    return bool(re.search(rf"\b{re.escape(suffix)}\b", text))


def _first_int_after_token(text: str, token: str) -> int | None:
    match = re.search(rf"\b{re.escape(token)}\s+(\d+)\b", text)
    return int(match.group(1)) if match else None


def _allocate_current_pl(
    current_snapshot_df: pd.DataFrame,
    class_snapshot_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
) -> pd.DataFrame:
    if class_snapshot_df.empty:
        return _allocate_current_pl_fund_level(current_snapshot_df, schedule_df)

    rows: list[dict[str, object]] = []
    class_schedule = (
        schedule_df.groupby(["cnpj", "class_key", "bucket"], as_index=False)["scheduled_original_amount"].sum()
        if not schedule_df.empty
        else pd.DataFrame(columns=["cnpj", "class_key", "bucket", "scheduled_original_amount"])
    )
    fund_schedule = (
        schedule_df.groupby(["cnpj", "bucket"], as_index=False)["scheduled_original_amount"].sum()
        if not schedule_df.empty
        else pd.DataFrame(columns=["cnpj", "bucket", "scheduled_original_amount"])
    )
    fund_info = {str(row.get("cnpj")): row for _, row in current_snapshot_df.iterrows()}
    class_totals = class_snapshot_df.groupby("cnpj")["pl_classe"].sum().to_dict()

    for _, class_row in class_snapshot_df.iterrows():
        cnpj = str(class_row.get("cnpj") or "")
        fund = fund_info.get(cnpj, pd.Series(dtype=object))
        raw_pl_classe = float(class_row.get("pl_classe") or 0.0)
        fund_pl_atual = float(fund.get("pl_atual") or 0.0)
        class_total = float(class_totals.get(cnpj) or 0.0)
        reconciliation_factor = fund_pl_atual / class_total if class_total > 0.0 and fund_pl_atual >= 0.0 else 1.0
        pl_classe = raw_pl_classe * reconciliation_factor
        class_row = class_row.copy()
        class_row["pl_classe_raw_ime"] = raw_pl_classe
        class_row["pl_classe"] = pl_classe
        class_row["pl_reconciliation_factor"] = reconciliation_factor
        class_key = _pl_class_key(class_row)
        if pl_classe <= 0.0:
            rows.append(_class_allocation_row(fund, class_row, class_key, "Sem PL", 0.0, 0.0, "PL da classe zerado no IME."))
            continue

        own_schedule = class_schedule[
            class_schedule["cnpj"].eq(cnpj) & class_schedule["class_key"].eq(class_key)
        ].copy()
        total_schedule = float(own_schedule["scheduled_original_amount"].sum()) if not own_schedule.empty else 0.0
        method_note = "PL da classe alocado pelo cronograma documental da própria classe/cota."

        if total_schedule <= 0.0:
            own_schedule = fund_schedule[fund_schedule["cnpj"].eq(cnpj)].copy()
            total_schedule = float(own_schedule["scheduled_original_amount"].sum()) if not own_schedule.empty else 0.0
            method_note = "Classe sem cronograma próprio parseável; PL alocado pela curva documental remanescente do fundo."
            if total_schedule <= 0.0:
                rows.append(_class_allocation_row(fund, class_row, class_key, "Sem cronograma", pl_classe, 1.0, "Classe sem cronograma próprio e sem curva documental de fundo."))
                continue

        for bucket in YEAR_BUCKETS:
            amount = float(own_schedule[own_schedule["bucket"].eq(bucket)]["scheduled_original_amount"].sum())
            share = amount / total_schedule if total_schedule else 0.0
            rows.append(_class_allocation_row(fund, class_row, class_key, bucket, pl_classe * share, share, method_note))
    output = pd.DataFrame(rows)
    output = output[output["allocated_pl"].abs().gt(0.01) | output["bucket"].isin(["Sem PL", "Sem cronograma"])].copy()
    return output


def _allocate_current_pl_fund_level(current_snapshot_df: pd.DataFrame, schedule_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    schedule_shares = (
        schedule_df.groupby(["cnpj", "bucket"], as_index=False)["scheduled_original_amount"].sum()
        if not schedule_df.empty
        else pd.DataFrame(columns=["cnpj", "bucket", "scheduled_original_amount"])
    )
    for _, fund in current_snapshot_df.iterrows():
        cnpj = str(fund.get("cnpj") or "")
        pl_atual = float(fund.get("pl_atual") or 0.0)
        fund_schedule = schedule_shares[schedule_shares["cnpj"].eq(cnpj)].copy()
        if pl_atual <= 0.0:
            rows.append(_allocation_row(fund, "Sem PL", 0.0, 0.0, "PL atual oficial zerado."))
            continue
        total_schedule = float(fund_schedule["scheduled_original_amount"].sum()) if not fund_schedule.empty else 0.0
        if total_schedule <= 0.0:
            rows.append(_allocation_row(fund, "Sem cronograma", pl_atual, 1.0, "PL sem cronograma futuro parseável."))
            continue
        for bucket in YEAR_BUCKETS:
            amount = float(fund_schedule[fund_schedule["bucket"].eq(bucket)]["scheduled_original_amount"].sum())
            share = amount / total_schedule if total_schedule else 0.0
            rows.append(_allocation_row(fund, bucket, pl_atual * share, share, "PL atual alocado pela participação do bucket no cronograma documental remanescente."))
    output = pd.DataFrame(rows)
    output = output[output["allocated_pl"].abs().gt(0.01) | output["bucket"].isin(["Sem PL", "Sem cronograma"])].copy()
    return output


def _allocation_row(fund: pd.Series, bucket: str, allocated_pl: float, share: float, note: str) -> dict[str, object]:
    return {
        "short_name": fund.get("short_name"),
        "cnpj": fund.get("cnpj"),
        "fund_name": fund.get("fund_name"),
        "situacao_cvm": fund.get("situacao_cvm"),
        "latest_competencia": fund.get("latest_competencia"),
        "competencia_base_date": fund.get("competencia_base_date"),
        "pl_atual": float(fund.get("pl_atual") or 0.0),
        "bucket": bucket,
        "allocation_share": share,
        "allocated_pl": allocated_pl,
        "method_note": note,
    }


def _class_allocation_row(
    fund: pd.Series,
    class_row: pd.Series,
    class_key: str,
    bucket: str,
    allocated_pl: float,
    share: float,
    note: str,
) -> dict[str, object]:
    return {
        "short_name": class_row.get("short_name") or fund.get("short_name"),
        "cnpj": class_row.get("cnpj") or fund.get("cnpj"),
        "fund_name": class_row.get("fund_name") or fund.get("fund_name"),
        "situacao_cvm": fund.get("situacao_cvm", ""),
        "latest_competencia": fund.get("latest_competencia") or class_row.get("competencia"),
        "competencia_base_date": fund.get("competencia_base_date", ""),
        "pl_atual": float(fund.get("pl_atual") or 0.0),
        "class_kind": class_row.get("class_kind", ""),
        "class_macro": class_row.get("class_macro", ""),
        "class_label": class_row.get("class_label", ""),
        "class_key": class_key,
        "pl_classe_raw_ime": float(class_row.get("pl_classe_raw_ime") or class_row.get("pl_classe") or 0.0),
        "pl_reconciliation_factor": float(class_row.get("pl_reconciliation_factor") or 1.0),
        "pl_classe": float(class_row.get("pl_classe") or 0.0),
        "bucket": bucket,
        "allocation_share": share,
        "allocated_pl": allocated_pl,
        "method_note": note,
    }


def _year_summary(allocation_df: pd.DataFrame) -> pd.DataFrame:
    if allocation_df.empty:
        return pd.DataFrame(columns=["bucket", "allocated_pl", "share_total"])
    valid = allocation_df[allocation_df["bucket"].isin(YEAR_BUCKETS)].copy()
    total = float(valid["allocated_pl"].sum())
    summary = (
        valid.groupby("bucket")["allocated_pl"]
        .sum()
        .reindex(YEAR_BUCKETS, fill_value=0.0)
        .rename_axis("bucket")
        .reset_index()
    )
    summary["share_total"] = summary["allocated_pl"] / total if total else 0.0
    return summary


def _plot_waterfall(
    *,
    year_fund_df: pd.DataFrame,
    current_snapshot_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    valid = year_fund_df[year_fund_df["bucket"].isin(YEAR_BUCKETS)].copy()
    total_pl = float(current_snapshot_df["pl_atual"].sum())
    total_by_bucket = valid.groupby("bucket")["allocated_pl"].sum().reindex(YEAR_BUCKETS, fill_value=0.0)

    width, height = 2800, 1600
    margin_left, margin_right = 185, 115
    margin_top, margin_bottom = 285, 360
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]

    def add_rect(x1: float, y1: float, x2: float, y2: float, fill: str, outline: str | None = None, width_px: int = 1) -> None:
        draw.rectangle((x1, y1, x2, y2), fill=fill, outline=outline, width=width_px)
        outline_attr = f' stroke="{outline}" stroke-width="{width_px}"' if outline else ""
        svg.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{max(x2 - x1, 0):.1f}" height="{max(y2 - y1, 0):.1f}" fill="{fill}"{outline_attr}/>')

    def add_line(x1: float, y1: float, x2: float, y2: float, fill: str, width_px: int = 1, dash: str | None = None) -> None:
        if dash:
            _draw_dashed_line(draw, x1, y1, x2, y2, fill, width_px)
        else:
            draw.line((x1, y1, x2, y2), fill=fill, width=width_px)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        svg.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{fill}" stroke-width="{width_px}"{dash_attr}/>')

    def add_text(
        x: float,
        y: float,
        text: str,
        *,
        size: int,
        fill: str = "#222222",
        bold: bool = False,
        anchor: str = "mm",
    ) -> None:
        font = _font(size, bold=bold)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        draw_x = x
        draw_y = y
        svg_anchor = "middle"
        if anchor.endswith("m"):
            draw_x -= text_width / 2
        elif anchor.endswith("r"):
            draw_x -= text_width
            svg_anchor = "end"
        elif anchor.endswith("l"):
            svg_anchor = "start"
        if anchor.startswith("m"):
            draw_y -= text_height / 2
            svg_y = y + text_height * 0.35
        elif anchor.startswith("b"):
            draw_y -= text_height
            svg_y = y
        else:
            svg_y = y + text_height
        draw.text((draw_x, draw_y), text, font=font, fill=fill)
        weight = "700" if bold else "400"
        svg.append(
            f'<text x="{x:.1f}" y="{svg_y:.1f}" font-family="Arial, Helvetica, sans-serif" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{svg_anchor}">{escape(text)}</text>'
        )

    add_rect(0, 0, width, height, "white")
    add_rect(margin_left, margin_top, width - margin_right, height - margin_bottom, "#fbfbfb")
    add_text(margin_left, 82, "Cloudwalk FIDCs: run-off contratual do PL atual", size=38, bold=True, anchor="tl")
    add_text(
        margin_left,
        132,
        "PL oficial mais recente por FIDC (CVM/IME), alocado por ano conforme cronogramas de amortização em regulamentos e anexos.",
        size=22,
        fill="#555555",
        anchor="tl",
    )
    add_text(
        margin_left,
        170,
        "As cores dentro de cada queda identificam o FIDC responsável pelo run-off daquele ano.",
        size=20,
        fill="#777777",
        anchor="tl",
    )

    ymax = max(total_pl * 1.12, 1_000_000_000.0)
    max_bn = ymax / 1e9
    grid_step_bn = _nice_grid_step(max_bn)
    y_zero = margin_top + plot_height

    def y_of(value: float) -> float:
        return margin_top + (ymax - max(value, 0.0)) / ymax * plot_height

    tick = 0.0
    while tick <= max_bn + 0.001:
        y = y_of(tick * 1e9)
        add_line(margin_left, y, width - margin_right, y, "#e3e3e3", 1)
        label = "0" if tick == 0 else f"{tick:g}"
        add_text(margin_left - 20, y, label, size=18, fill="#666666", anchor="mr")
        tick += grid_step_bn
    add_text(margin_left - 105, margin_top - 28, "R$ bi", size=18, fill="#555555", bold=True, anchor="ml")
    add_line(margin_left, y_zero, width - margin_right, y_zero, "#333333", 2)

    labels = ["PL atual", *YEAR_BUCKETS, "PL pós runoff"]
    slot_count = len(labels)
    slot_width = plot_width / slot_count
    centers = [margin_left + slot_width * (idx + 0.5) for idx in range(slot_count)]
    bar_width = min(250, slot_width * 0.58)
    total_color = "#222222"

    def add_bar_segment(center_x: float, top_value: float, bottom_value: float, color: str, outline: str = "white") -> None:
        x1 = center_x - bar_width / 2
        x2 = center_x + bar_width / 2
        y1 = y_of(top_value)
        y2 = y_of(bottom_value)
        add_rect(x1, min(y1, y2), x2, max(y1, y2), color, outline, 2)

    add_bar_segment(centers[0], total_pl, 0.0, total_color, total_color)
    add_text(centers[0], y_of(total_pl) - 22, _format_brl_bn(total_pl), size=20, bold=True, anchor="bm")

    running = total_pl
    for idx, bucket in enumerate(YEAR_BUCKETS, start=1):
        bucket_total = float(total_by_bucket.loc[bucket])
        top = running
        bottom = running - bucket_total
        bucket_df = valid[valid["bucket"].eq(bucket)].copy()
        bucket_df["order"] = bucket_df["short_name"].map(_fund_order)
        bucket_df = bucket_df.sort_values(["order", "short_name"])
        segment_top = top
        for _, row in bucket_df.iterrows():
            value = float(row["allocated_pl"])
            if value <= 0.0:
                continue
            segment_bottom = segment_top - value
            color = FUND_COLORS.get(str(row["short_name"]), "#999999")
            add_bar_segment(centers[idx], segment_top, segment_bottom, color)
            if value / 1e9 >= 0.45:
                add_text(
                    centers[idx],
                    (y_of(segment_top) + y_of(segment_bottom)) / 2,
                    _format_brl_bn(value),
                    size=16,
                    fill="white",
                    bold=True,
                )
            segment_top = segment_bottom
        add_line(
            centers[idx - 1] + bar_width / 2,
            y_of(top),
            centers[idx] - bar_width / 2,
            y_of(top),
            "#9b9b9b",
            2,
            dash="9 7",
        )
        add_text(centers[idx], min(y_of(bottom) + 44, y_zero + 58), f"-{_format_brl_bn(bucket_total)}", size=19, fill="#333333", bold=True)
        running = bottom

    final_value = max(running, 0.0)
    add_bar_segment(centers[-1], final_value, 0.0, "#d9d9d9", "#888888")
    add_text(centers[-1], y_zero - 22 if final_value <= 1_000_000 else y_of(final_value) - 22, _format_brl_bn(final_value), size=19, bold=True, anchor="bm")

    for center, label in zip(centers, labels, strict=True):
        add_text(center, y_zero + 92, label, size=20, fill="#222222", bold=True)

    legend_names = ["PL atual total", *_ordered_fund_names(valid["short_name"].dropna().astype(str).unique())]
    legend_colors = {"PL atual total": total_color, **FUND_COLORS}
    legend_y = height - 230
    legend_col_width = plot_width / 4
    for idx, name in enumerate(legend_names):
        row = idx // 4
        col = idx % 4
        x = margin_left + col * legend_col_width
        y = legend_y + row * 48
        add_rect(x, y - 14, x + 30, y + 14, legend_colors.get(name, "#999999"))
        add_text(x + 44, y, name, size=18, fill="#333333", anchor="ml")

    add_text(
        margin_left,
        height - 42,
        "Fonte: CVM/Fundos.NET IME para PL atual; cronogramas documentais curados de regulamentos, atas e apêndices. Valores em R$ bilhões.",
        size=16,
        fill="#666666",
        anchor="tl",
    )
    svg.append("</svg>")
    image.save(output_dir / "cloudwalk_pl_runoff_waterfall.png", "PNG")
    (output_dir / "cloudwalk_pl_runoff_waterfall.svg").write_text("\n".join(svg) + "\n", encoding="utf-8")


def _write_outputs(
    *,
    output_dir: Path,
    current_snapshot_df: pd.DataFrame,
    class_snapshot_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
    schedule_audit_df: pd.DataFrame,
    allocation_df: pd.DataFrame,
    year_fund_df: pd.DataFrame,
    year_summary_df: pd.DataFrame,
) -> None:
    files = {
        "current_pl_snapshot.csv": current_snapshot_df,
        "current_class_pl_snapshot.csv": class_snapshot_df,
        "documentary_schedule_long.csv": schedule_df,
        "schedule_audit.csv": schedule_audit_df,
        "runoff_allocation_long.csv": allocation_df,
        "runoff_by_year_fund.csv": year_fund_df,
        "runoff_by_year_summary.csv": year_summary_df,
    }
    for filename, frame in files.items():
        frame.to_csv(output_dir / filename, index=False)
    xlsx_path = output_dir / "cloudwalk_pl_runoff_waterfall.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
        workbook = writer.book
        formats = _xlsx_formats(workbook)
        dashboard_ws = workbook.add_worksheet("Dashboard")
        chart_data_ws = workbook.add_worksheet("ChartData")
        writer.sheets["Dashboard"] = dashboard_ws
        writer.sheets["ChartData"] = chart_data_ws
        _write_dashboard_sheet(
            workbook=workbook,
            dashboard_ws=dashboard_ws,
            chart_data_ws=chart_data_ws,
            current_snapshot_df=current_snapshot_df,
            allocation_df=allocation_df,
            year_fund_df=year_fund_df,
            year_summary_df=year_summary_df,
            formats=formats,
        )
        for sheet_name, frame in [
            ("current_pl", current_snapshot_df),
            ("class_pl", class_snapshot_df),
            ("allocation", allocation_df),
            ("year_fund", year_fund_df),
            ("year_summary", year_summary_df),
            ("schedule", schedule_df),
            ("schedule_audit", schedule_audit_df),
        ]:
            frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            _format_dataframe_sheet(writer.sheets[sheet_name[:31]], frame, formats)


def _xlsx_formats(workbook: object) -> dict[str, object]:
    return {
        "title": workbook.add_format({"bold": True, "font_size": 20, "font_color": "#1F1F1F"}),
        "subtitle": workbook.add_format({"font_size": 10, "font_color": "#666666"}),
        "section": workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E79", "border": 0}),
        "header": workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E79", "border": 1, "border_color": "#D9E2F3"}),
        "subheader": workbook.add_format({"bold": True, "font_color": "#333333", "bg_color": "#D9EAF7", "border": 1, "border_color": "#B7C9D6"}),
        "body": workbook.add_format({"font_color": "#222222", "border": 1, "border_color": "#E7E7E7"}),
        "note": workbook.add_format({"font_color": "#666666", "font_size": 9, "text_wrap": True, "valign": "top"}),
        "currency_bi": workbook.add_format({"num_format": 'R$ #,##0.00 "bi";[Red]-R$ #,##0.00 "bi";-'}),
        "currency_abs": workbook.add_format({"num_format": 'R$ #,##0;[Red]-R$ #,##0;-'}),
        "pct": workbook.add_format({"num_format": "0.0%;[Red](0.0%);-"}),
        "num": workbook.add_format({"num_format": "#,##0.00"}),
        "date": workbook.add_format({"num_format": "yyyy-mm-dd"}),
        "kpi_label": workbook.add_format({"font_size": 9, "font_color": "#666666", "bg_color": "#F3F6F8", "border": 1, "border_color": "#D9E2F3"}),
        "kpi_value": workbook.add_format({"bold": True, "font_size": 15, "font_color": "#1F1F1F", "bg_color": "#F3F6F8", "border": 1, "border_color": "#D9E2F3"}),
    }


def _write_dashboard_sheet(
    *,
    workbook: object,
    dashboard_ws: object,
    chart_data_ws: object,
    current_snapshot_df: pd.DataFrame,
    allocation_df: pd.DataFrame,
    year_fund_df: pd.DataFrame,
    year_summary_df: pd.DataFrame,
    formats: dict[str, object],
) -> None:
    total_pl = float(current_snapshot_df["pl_atual"].sum()) if not current_snapshot_df.empty else 0.0
    total_bi = total_pl / 1e9
    summary = year_summary_df.set_index("bucket")["allocated_pl"].to_dict() if not year_summary_df.empty else {}
    runoff_2026 = float(summary.get("2026") or 0.0)
    runoff_2027 = float(summary.get("2027") or 0.0)
    runoff_2028 = float(summary.get("2028") or 0.0)
    runoff_2029p = float(summary.get("2029+") or 0.0)
    fallback_total = float(
        allocation_df[
            allocation_df["method_note"].astype(str).str.contains("sem cronograma próprio", case=False, na=False)
        ]["allocated_pl"].sum()
    ) if not allocation_df.empty and "method_note" in allocation_df else 0.0

    dashboard_ws.hide_gridlines(2)
    dashboard_ws.set_tab_color("#1F4E79")
    dashboard_ws.set_column("A:A", 2)
    dashboard_ws.set_column("B:F", 16)
    dashboard_ws.set_column("G:T", 12)
    dashboard_ws.set_column("U:U", 2)
    dashboard_ws.set_row(0, 28)
    dashboard_ws.merge_range("B2:T2", "Cloudwalk FIDCs: run-off contratual do PL atual", formats["title"])
    dashboard_ws.merge_range(
        "B3:T3",
        "Gráficos nativos do Excel: waterfall principal e zoom dos vencimentos 2026 por FIDC. Valores em R$ bilhões.",
        formats["subtitle"],
    )

    kpis = [
        ("PL oficial atual", total_bi),
        ("Run-off 2026", runoff_2026 / 1e9),
        ("Run-off 2027", runoff_2027 / 1e9),
        ("Run-off 2028", runoff_2028 / 1e9),
        ("Run-off 2029+", runoff_2029p / 1e9),
        ("Fallback subordinadas", fallback_total / 1e9),
    ]
    for idx, (label, value) in enumerate(kpis):
        col = 1 + idx * 3
        dashboard_ws.merge_range(4, col, 4, col + 1, label, formats["kpi_label"])
        dashboard_ws.merge_range(5, col, 5, col + 1, value, formats["kpi_value"])
        dashboard_ws.set_row(4, 18)
        dashboard_ws.set_row(5, 27)

    zoom_2026_count = _write_chart_data_sheet(
        chart_data_ws=chart_data_ws,
        current_snapshot_df=current_snapshot_df,
        allocation_df=allocation_df,
        year_fund_df=year_fund_df,
        year_summary_df=year_summary_df,
        formats=formats,
    )
    _add_main_waterfall_chart(workbook, dashboard_ws, chart_data_ws, total_bi, year_fund_df)
    _add_2026_zoom_chart(workbook, dashboard_ws, chart_data_ws, year_fund_df, zoom_2026_count)

    dashboard_ws.merge_range("L34:T34", "Leitura executiva", formats["section"])
    notes = [
        ["Base", "PL atual por FIDC vem do último IME CVM/Fundos.NET em cache local."],
        ["Cronograma", "Regulamentos/anexos determinam a distribuição temporal; quando há classe/cota no IME, a curva é aplicada por classe."],
        ["Fallback", "Subordinadas sem calendário próprio seguem a curva documental remanescente do respectivo fundo e ficam marcadas em allocation.method_note."],
        ["Reconciliação", "O total do waterfall fecha exatamente com o PL oficial atual; diferenças brutas entre soma de classes e PL total foram escaladas dentro de cada fundo."],
    ]
    dashboard_ws.write_row("L35", ["Item", "Nota"], formats["subheader"])
    for offset, row in enumerate(notes, start=36):
        dashboard_ws.write_row(f"L{offset}", row, formats["body"])
        dashboard_ws.set_row(offset - 1, 34)
    dashboard_ws.set_column("L:L", 16)
    dashboard_ws.set_column("M:T", 82)


def _write_chart_data_sheet(
    *,
    chart_data_ws: object,
    current_snapshot_df: pd.DataFrame,
    allocation_df: pd.DataFrame,
    year_fund_df: pd.DataFrame,
    year_summary_df: pd.DataFrame,
    formats: dict[str, object],
) -> int:
    chart_data_ws.hide_gridlines(2)
    chart_data_ws.set_tab_color("#70AD47")
    total_pl = float(current_snapshot_df["pl_atual"].sum()) if not current_snapshot_df.empty else 0.0
    total_by_bucket = (
        year_fund_df[year_fund_df["bucket"].isin(YEAR_BUCKETS)].groupby("bucket")["allocated_pl"].sum().reindex(YEAR_BUCKETS, fill_value=0.0)
        if not year_fund_df.empty
        else pd.Series(0.0, index=YEAR_BUCKETS)
    )
    valid = year_fund_df[year_fund_df["bucket"].isin(YEAR_BUCKETS)].copy() if not year_fund_df.empty else pd.DataFrame()
    fund_names = _ordered_fund_names(valid["short_name"].dropna().astype(str).unique()) if not valid.empty else []

    chart_data_ws.write("A1", "Main waterfall chart data", formats["section"])
    categories = ["PL atual", *YEAR_BUCKETS, "PL pós runoff"]
    headers = ["Categoria", "Base invisível", "PL atual total", *fund_names, "PL pós runoff"]
    chart_data_ws.write_row(1, 0, headers, formats["header"])
    running = total_pl
    for row_idx, category in enumerate(categories, start=2):
        if category in YEAR_BUCKETS:
            bucket_total = float(total_by_bucket.loc[category])
            running_after = running - bucket_total
            if abs(running_after) < 1.0:
                running_after = 0.0
            base_value = max(running_after, 0.0) / 1e9
            running = running_after
        else:
            base_value = 0.0
        chart_data_ws.write(row_idx, 0, category, formats["body"])
        chart_data_ws.write_number(row_idx, 1, base_value, formats["num"])
        chart_data_ws.write_number(row_idx, 2, total_pl / 1e9 if category == "PL atual" else 0.0, formats["num"])
        for col_offset, name in enumerate(fund_names, start=3):
            value = 0.0
            if category in YEAR_BUCKETS and not valid.empty:
                match = valid[valid["bucket"].eq(category) & valid["short_name"].eq(name)]
                value = float(match["allocated_pl"].sum()) / 1e9 if not match.empty else 0.0
            chart_data_ws.write_number(row_idx, col_offset, value, formats["num"])
        chart_data_ws.write_number(row_idx, len(headers) - 1, max(running, 0.0) / 1e9 if category == "PL pós runoff" else 0.0, formats["num"])

    zoom_2026 = (
        valid[valid["bucket"].eq("2026")].groupby("short_name", as_index=False)["allocated_pl"].sum()
        if not valid.empty
        else pd.DataFrame(columns=["short_name", "allocated_pl"])
    )
    zoom_2026["order"] = zoom_2026["short_name"].map(_fund_order)
    zoom_2026 = zoom_2026[zoom_2026["allocated_pl"].gt(0)].sort_values(["allocated_pl", "order"], ascending=[True, True])
    start_row = 12
    chart_data_ws.write("A12", "Zoom 2026 chart data", formats["section"])
    chart_data_ws.write_row(start_row, 0, ["FIDC", "Run-off 2026", "% do 2026", "% do PL total"], formats["header"])
    total_2026 = float(zoom_2026["allocated_pl"].sum()) if not zoom_2026.empty else 0.0
    for idx, row in enumerate(zoom_2026.itertuples(index=False), start=start_row + 1):
        value = float(row.allocated_pl)
        chart_data_ws.write(idx, 0, str(row.short_name), formats["body"])
        chart_data_ws.write_number(idx, 1, value / 1e9, formats["num"])
        chart_data_ws.write_number(idx, 2, value / total_2026 if total_2026 else 0.0, formats["pct"])
        chart_data_ws.write_number(idx, 3, value / total_pl if total_pl else 0.0, formats["pct"])

    audit_start = start_row + len(zoom_2026) + 4
    chart_data_ws.write(audit_start, 0, "Chart audit", formats["section"])
    audit_rows = [
        ["PL oficial atual", total_pl / 1e9],
        ["Soma buckets do waterfall", float(total_by_bucket.sum()) / 1e9],
        ["Diferença", (total_pl - float(total_by_bucket.sum())) / 1e9],
    ]
    chart_data_ws.write_row(audit_start + 1, 0, ["Check", "R$ bi"], formats["header"])
    for offset, row in enumerate(audit_rows, start=audit_start + 2):
        chart_data_ws.write(offset, 0, row[0], formats["body"])
        chart_data_ws.write_number(offset, 1, row[1], formats["num"])

    chart_data_ws.set_column(0, 0, 22)
    chart_data_ws.set_column(1, max(len(headers), 4), 15)
    return len(zoom_2026)


def _add_main_waterfall_chart(
    workbook: object,
    dashboard_ws: object,
    chart_data_ws: object,
    total_bi: float,
    year_fund_df: pd.DataFrame,
) -> None:
    del chart_data_ws
    sheet_name = "ChartData"
    categories = f"='{sheet_name}'!$A$3:$A$8"
    first_row, last_row = 2, 7
    valid = year_fund_df[year_fund_df["bucket"].isin(YEAR_BUCKETS)].copy() if not year_fund_df.empty else pd.DataFrame()
    fund_names = _ordered_fund_names(valid["short_name"].dropna().astype(str).unique()) if not valid.empty else []
    chart = workbook.add_chart({"type": "column", "subtype": "stacked"})
    chart.set_size({"width": 1325, "height": 565})
    chart.set_title({"name": "Cloudwalk FIDCs: run-off contratual do PL atual", "name_font": {"bold": True, "size": 14, "color": "#222222"}})
    chart.set_chartarea({"fill": {"color": "#FFFFFF"}, "border": {"none": True}})
    chart.set_plotarea({"fill": {"color": "#FBFBFB"}, "border": {"none": True}})
    chart.set_legend({"position": "bottom", "font": {"size": 8}, "delete_series": [0, 2 + len(fund_names)]})
    chart.set_x_axis({"text_axis": True, "num_font": {"size": 9, "bold": True}, "line": {"color": "#333333"}})
    chart.set_y_axis(
        {
            "name": "R$ bi",
            "min": 0,
            "max": max(1.0, math.ceil(max(total_bi * 1.12, 20.0) * 2) / 2),
            "major_unit": _nice_grid_step(max(total_bi * 1.12, 20.0)),
            "num_format": "#,##0.0",
            "major_gridlines": {"visible": True, "line": {"color": "#E5E5E5"}},
            "line": {"none": True},
            "num_font": {"size": 8, "color": "#666666"},
        }
    )
    chart.add_series(
        {
            "name": "Base invisível",
            "categories": categories,
            "values": f"='{sheet_name}'!$B$3:$B$8",
            "fill": {"none": True},
            "border": {"none": True},
        }
    )
    chart.add_series(
        {
            "name": "PL atual total",
            "categories": categories,
            "values": f"='{sheet_name}'!$C$3:$C$8",
            "fill": {"color": "#222222"},
            "border": {"color": "#222222"},
            "data_labels": {
                "custom": [{"value": _format_brl_bn(total_bi * 1e9), "font": {"bold": True, "color": "#222222", "size": 9}}, *[{"delete": True} for _ in range(5)]],
                "position": "outside_end",
            },
        }
    )
    for idx, name in enumerate(fund_names, start=3):
        col_letter = _excel_col(idx)
        labels = []
        for category in ["PL atual", *YEAR_BUCKETS, "PL pós runoff"]:
            value = 0.0
            if category in YEAR_BUCKETS and not valid.empty:
                value = float(valid[valid["bucket"].eq(category) & valid["short_name"].eq(name)]["allocated_pl"].sum())
            labels.append({"value": _format_brl_bn(value), "font": {"bold": True, "color": "#FFFFFF", "size": 8}} if value / 1e9 >= 0.45 else {"delete": True})
        chart.add_series(
            {
                "name": name,
                "categories": categories,
                "values": f"='{sheet_name}'!${col_letter}$3:${col_letter}$8",
                "fill": {"color": FUND_COLORS.get(name, "#999999")},
                "border": {"color": "#FFFFFF"},
                "data_labels": {
                    "custom": labels,
                    "position": "center",
                    "font": {"bold": True, "color": "#FFFFFF", "size": 8},
                },
            }
        )
    residual_col = _excel_col(3 + len(fund_names))
    chart.add_series(
        {
            "name": "PL pós runoff",
            "categories": categories,
            "values": f"='{sheet_name}'!${residual_col}$3:${residual_col}$8",
            "fill": {"color": "#D9D9D9"},
            "border": {"color": "#888888"},
        }
    )
    dashboard_ws.insert_chart("B8", chart)


def _add_2026_zoom_chart(
    workbook: object,
    dashboard_ws: object,
    chart_data_ws: object,
    year_fund_df: pd.DataFrame,
    zoom_2026_count: int,
) -> None:
    del chart_data_ws
    sheet_name = "ChartData"
    first_row = 14
    max_row = first_row + max(zoom_2026_count, 1) - 1
    valid = year_fund_df[year_fund_df["bucket"].eq("2026")].copy() if not year_fund_df.empty else pd.DataFrame()
    if not valid.empty:
        valid = valid.groupby("short_name", as_index=False)["allocated_pl"].sum()
        valid = valid[valid["allocated_pl"].gt(0)].sort_values(["allocated_pl", "short_name"], ascending=[True, True])
    zoom_points = [
        {"fill": {"color": FUND_COLORS.get(str(row.short_name), "#999999")}, "border": {"color": "#FFFFFF"}}
        for row in valid.itertuples(index=False)
    ]
    chart = workbook.add_chart({"type": "bar"})
    chart.set_size({"width": 635, "height": 405})
    chart.set_title({"name": "Zoom 2026: principal vencendo por FIDC", "name_font": {"bold": True, "size": 12, "color": "#222222"}})
    chart.set_chartarea({"fill": {"color": "#FFFFFF"}, "border": {"none": True}})
    chart.set_plotarea({"fill": {"color": "#FBFBFB"}, "border": {"none": True}})
    chart.set_legend({"none": True})
    chart.set_x_axis(
        {
            "name": "R$ bi",
            "min": 0,
            "num_format": "#,##0.00",
            "major_gridlines": {"visible": True, "line": {"color": "#E5E5E5"}},
            "num_font": {"size": 8, "color": "#666666"},
        }
    )
    chart.set_y_axis({"num_font": {"size": 8, "bold": True}, "line": {"none": True}})
    chart.add_series(
        {
            "name": "Run-off 2026",
            "categories": f"='{sheet_name}'!$A${first_row}:$A${max_row}",
            "values": f"='{sheet_name}'!$B${first_row}:$B${max_row}",
            "points": zoom_points,
            "data_labels": {
                "value": True,
                "num_format": 'R$ #,##0.00 "bi"',
                "position": "outside_end",
                "font": {"size": 8, "color": "#222222", "bold": True},
            },
        }
    )
    dashboard_ws.insert_chart("B35", chart)


def _excel_col(index_zero_based: int) -> str:
    index = index_zero_based
    letters = ""
    while index >= 0:
        index, remainder = divmod(index, 26)
        letters = chr(65 + remainder) + letters
        index -= 1
    return letters


def _format_dataframe_sheet(worksheet: object, frame: pd.DataFrame, formats: dict[str, object]) -> None:
    worksheet.hide_gridlines(2)
    if frame.empty:
        worksheet.write(0, 0, "Sem dados", formats["note"])
        return
    rows, cols = frame.shape
    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, max(rows, 1), max(cols - 1, 0))
    for col_idx, col in enumerate(frame.columns):
        values = frame[col].astype(str).head(200).tolist()
        max_len = max([len(str(col)), *(len(str(value)) for value in values)] or [10])
        width = min(max(max_len + 2, 10), 42)
        worksheet.set_column(col_idx, col_idx, width)
    worksheet.set_row(0, 22, formats["header"])
    for col_idx, col in enumerate(frame.columns):
        lower = str(col).lower()
        if any(token in lower for token in ["pl", "amount", "volume", "allocated", "scheduled"]):
            worksheet.set_column(col_idx, col_idx, 16, formats["currency_abs"])
        elif "share" in lower or "pct" in lower or "factor" in lower:
            worksheet.set_column(col_idx, col_idx, 12, formats["pct"])


def _write_methodology(
    *,
    output_dir: Path,
    current_snapshot_df: pd.DataFrame,
    allocation_df: pd.DataFrame,
    schedule_audit_df: pd.DataFrame,
) -> None:
    total = float(current_snapshot_df["pl_atual"].sum()) if not current_snapshot_df.empty else 0.0
    by_year = _year_summary(allocation_df)
    valid_allocation = allocation_df[allocation_df["bucket"].isin(YEAR_BUCKETS)].copy()
    allocated_total = float(valid_allocation["allocated_pl"].sum()) if not valid_allocation.empty else 0.0
    fallback_total = (
        float(
            valid_allocation[
                valid_allocation["method_note"].astype(str).str.contains("sem cronograma próprio", case=False, na=False)
            ]["allocated_pl"].sum()
        )
        if not valid_allocation.empty
        else 0.0
    )
    lines = [
        "# Cloudwalk FIDCs - Run-off do PL atual",
        "",
        f"Data de geração: {date.today().isoformat()}",
        f"PL oficial reconciliado: {_format_brl_bn(total)}",
        f"PL alocado no waterfall: {_format_brl_bn(allocated_total)}",
        "",
        "## Metodologia",
        "",
        "1. Universo: carteira Cloudwalk cadastrada em `portfolios.json`.",
        "2. PL atual: último Informe Mensal Estruturado disponível no cache CVM/Fundos.NET para cada CNPJ.",
        "3. PL por classe/cota: classes do IME foram normalizadas para chaves comparáveis aos regulamentos, como `senior_1`, `senior_2` e mezaninos específicos.",
        "4. Reconciliação: a soma bruta das classes foi escalada dentro de cada fundo para bater exatamente no PL total oficial do IME; o fator fica em `runoff_allocation_long.csv`.",
        "5. Situação cadastral: cadastro aberto CVM `registro_fundo_classe.zip`.",
        "6. Cronogramas: campo curado `Amortização principal` em `data/regulatory_profiles/cloudwalk_cotas_emissoes_pagamentos.csv`, com fonte documental por regulamento/ata/anexo.",
        "7. Alocação: cada classe foi distribuída pelos anos conforme seu cronograma documental remanescente após a competência-base do IME.",
        "8. Fallback: classes sem cronograma próprio parseável, principalmente subordinadas, foram alocadas pela curva documental remanescente do respectivo fundo; isso soma "
        f"{_format_brl_bn(fallback_total)}.",
        "9. Buckets: 2026, 2027, 2028 e 2029+.",
        "",
        "## Resumo por ano",
        "",
        "| Ano | PL alocado | % total |",
        "|---|---:|---:|",
    ]
    for _, row in by_year.iterrows():
        lines.append(f"| {row['bucket']} | {_format_brl_bn(float(row['allocated_pl']))} | {float(row['share_total']):.1%} |")
    lines.extend(
        [
            "",
            "## Limitações explícitas",
            "",
            "- O gráfico não é uma projeção de rentabilidade ou recompra antecipada; é um run-off contratual de principal.",
            "- Quando o regulamento lista datas sem percentuais, a curadoria usa distribuição linear entre as datas documentadas, com aviso no `schedule_audit.csv`.",
            "- Quando o documento informa apenas intervalo de amortização, a curadoria usa parcelas mensais lineares no intervalo documentado.",
            "- Subordinadas sem calendário fixo próprio não são tratadas como vencimento contratual independente; entram pelo fallback de curva do fundo e ficam marcadas em `method_note`.",
            "- Kick Ass II aparece com PL atual zero e situação CVM cancelada; fica fora do run-off futuro.",
            "- Fundos em liquidação podem ter última competência anterior a maio/2026 se o Fundos.NET não publicou IME posterior ou se a consulta pública falhou.",
            "",
            "## Arquivos gerados",
            "",
            "- `cloudwalk_pl_runoff_waterfall.png`",
            "- `cloudwalk_pl_runoff_waterfall.svg`",
            "- `cloudwalk_pl_runoff_waterfall.xlsx`",
            "- `current_pl_snapshot.csv`",
            "- `current_class_pl_snapshot.csv`",
            "- `runoff_allocation_long.csv`",
            "- `runoff_by_year_fund.csv`",
            "- `documentary_schedule_long.csv`",
            "- `schedule_audit.csv`",
        ]
    )
    excluded = schedule_audit_df[schedule_audit_df["status"].ne("incluido")] if not schedule_audit_df.empty else pd.DataFrame()
    if not excluded.empty:
        lines.extend(["", "## Linhas documentais não usadas no cronograma", ""])
        for _, row in excluded.head(30).iterrows():
            lines.append(f"- {row.get('short_name')}: {row.get('classe')} - {row.get('reason')}")
    (output_dir / "methodology.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _audit_row(row: pd.Series, cnpj: str, cnpj_to_short: dict[str, str], status: str, reason: str) -> dict[str, object]:
    short_name = cnpj_to_short.get(cnpj, cnpj)
    return {
        "short_name": short_name,
        "cnpj": cnpj,
        "fund_name": row.get("Fundo"),
        "classe": row.get("Cota/Classe"),
        "tipo": row.get("Tipo"),
        "class_key": _schedule_class_key(short_name, str(row.get("Tipo") or ""), str(row.get("Cota/Classe") or "")),
        "status": status,
        "reason": reason,
        "source": row.get("Fonte"),
        "status_evidencia": row.get("Status/evidência"),
    }


def _short_name(name: str) -> str:
    text = str(name or "").upper()
    if "KICK ASS II" in text:
        return "Kick Ass II"
    if "KICK ASS I" in text:
        return "Kick Ass I"
    if "AKIRA II" in text:
        return "Akira II"
    if "AKIRA I" in text:
        return "Akira I"
    if "BIG PICTURE IV" in text:
        return "Big Picture IV"
    if "BIG PICTURE III" in text:
        return "Big Picture III"
    if "BIG PICTURE II" in text:
        return "Big Picture II"
    if "BIG PICTURE I" in text:
        return "Big Picture I"
    if "A.I." in text or " A I " in text:
        return "Cloudwalk A.I."
    if " PI " in f" {text} ":
        return "Cloudwalk PI"
    if "BELA" in text:
        return "Bela"
    return str(name or "").strip()[:28]


def _ascii(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value.lower())
    return normalized.encode("ascii", "ignore").decode("ascii")


def _month_end_from_competencia(label: str) -> date:
    month, year = str(label).split("/")
    year_int = int(year)
    month_int = int(month)
    return date(year_int, month_int, calendar.monthrange(year_int, month_int)[1])


def _parse_iso_date(value: object) -> date | None:
    try:
        text = str(value or "")
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def _year_bucket(item_date: date) -> str:
    if item_date.year <= 2026:
        return "2026"
    if item_date.year == 2027:
        return "2027"
    if item_date.year == 2028:
        return "2028"
    return "2029+"


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for candidate in candidates:
        try:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_dashed_line(
    draw: ImageDraw.ImageDraw,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    fill: str,
    width_px: int,
    *,
    dash_len: float = 12.0,
    gap_len: float = 8.0,
) -> None:
    length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    if length == 0:
        return
    dx = (x2 - x1) / length
    dy = (y2 - y1) / length
    pos = 0.0
    while pos < length:
        end = min(pos + dash_len, length)
        draw.line(
            (x1 + dx * pos, y1 + dy * pos, x1 + dx * end, y1 + dy * end),
            fill=fill,
            width=width_px,
        )
        pos += dash_len + gap_len


def _nice_grid_step(max_bn: float) -> float:
    if max_bn <= 6:
        return 1.0
    if max_bn <= 15:
        return 2.0
    if max_bn <= 30:
        return 2.5
    if max_bn <= 80:
        return 5.0
    return 10.0


def _format_brl_bn(value: float) -> str:
    return f"R$ {value / 1e9:,.2f} bi".replace(",", "X").replace(".", ",").replace("X", ".")


def _fund_order(name: object) -> int:
    order = {
        "Kick Ass I": 1,
        "Akira I": 2,
        "Akira II": 3,
        "Big Picture I": 4,
        "Big Picture II": 5,
        "Big Picture III": 6,
        "Big Picture IV": 7,
        "Cloudwalk A.I.": 8,
        "Cloudwalk PI": 9,
        "Bela": 10,
        "Kick Ass II": 11,
    }
    return order.get(str(name), 99)


def _ordered_fund_names(names: Iterable[str]) -> list[str]:
    return sorted(set(names), key=lambda item: (_fund_order(item), item))


if __name__ == "__main__":
    main()
