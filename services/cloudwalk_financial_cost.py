from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json
import math
import re
from typing import Any, Iterable

import pandas as pd

from services.fidc_model.calendar import b3_market_holidays_for_dates, networkdays
from services.ime_loader import DEFAULT_PORTABLE_CACHE_ROOT, DEFAULT_RUNTIME_CACHE_ROOT, materialize_latest_portable_cache_for_cnpj
from services.waterfall_schedule import (
    DEFAULT_CLOUDWALK_EMISSIONS,
    DEFAULT_REFERENCE_DATE,
    normalize_text,
    only_digits,
    parse_amortization_schedule,
    parse_date_label,
    parse_money_value,
)


DEFAULT_FINANCIAL_COST_OUTPUT_DIR = Path("reports/cloudwalk_financial_cost")
DEFAULT_FINANCIAL_COST_CONFIG = Path("config/cloudwalk_financial_cost_inputs.json")
DEFAULT_CASH_YIELD_CDI_FACTOR = 1.0
MONEY_SCALE = 1_000_000.0


@dataclass(frozen=True)
class FundingLine:
    fund_name: str
    cnpj: str
    classe: str
    tipo: str
    class_macro: str
    issue_date: date | None
    volume: float
    spread_aa: float | None
    spread_source: str
    remuneration: str
    amortization_text: str
    amortization_convention: str
    amortizations: tuple[tuple[date, float], ...]
    source: str
    included: bool
    exclusion_reason: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def line_key(self) -> str:
        return line_key(self.cnpj, self.classe)

    @property
    def has_rate(self) -> bool:
        return self.spread_aa is not None


@dataclass(frozen=True)
class ImeFinancialSnapshot:
    fund_name: str
    cnpj: str
    competencia: str
    pl_total: float | None
    caixa: float
    titulos_publicos: float
    recebiveis: float
    cash_like_reported: float
    cash_like_residual_proxy: float
    cash_like: float
    cash_like_method: str
    source: str
    included: bool
    exclusion_reason: str | None = None


@dataclass(frozen=True)
class CostRunConfig:
    start_date: date
    end_date: date
    snapshot_date: date
    cdi_aa: float
    cdi_source: str
    cash_yield_cdi_factor: float = DEFAULT_CASH_YIELD_CDI_FACTOR


@dataclass(frozen=True)
class FinancialCostOutputs:
    summary_df: pd.DataFrame
    line_df: pd.DataFrame
    monthly_df: pd.DataFrame
    ime_snapshot_df: pd.DataFrame
    missing_inputs_df: pd.DataFrame
    methodology_md: str


def line_key(cnpj: str, classe: str) -> str:
    return f"{only_digits(cnpj)}|{str(classe or '').strip()}"


def parse_cdi_plus_spread(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = normalize_text(text)
    if "spread nao localizado" in normalized or "sem parametro" in normalized:
        return None
    if "residual" in normalized and not re.search(r"(?:di|cdi)\s*\+", normalized):
        return None

    match = re.search(
        r"(?:taxa\s*)?(?:di|cdi)\s*\+\s*(?:ate\s*)?([0-9]{1,2}(?:[.,][0-9]{1,4})?)\s*%",
        normalized,
    )
    if not match:
        return None
    return _parse_percentage_points(match.group(1))


def load_spread_overrides(path: str | Path | None = DEFAULT_FINANCIAL_COST_CONFIG) -> dict[str, float]:
    if path is None:
        return {}
    config_path = Path(path)
    if not config_path.exists():
        return {}
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    candidates: dict[str, Any] = {}
    for key in ("spreads_cdi_plus_aa", "manual_spreads", "spreads"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, dict):
            candidates.update(value)

    overrides: dict[str, float] = {}
    for key, raw_value in candidates.items():
        parsed = _parse_override_spread(raw_value)
        if parsed is not None:
            overrides[str(key)] = parsed
    return overrides


def load_cash_yield_factor(path: str | Path | None = DEFAULT_FINANCIAL_COST_CONFIG) -> float:
    if path is None or not Path(path).exists():
        return DEFAULT_CASH_YIELD_CDI_FACTOR
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    value = payload.get("cash_yield_cdi_factor") if isinstance(payload, dict) else None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_CASH_YIELD_CDI_FACTOR
    return max(parsed, 0.0)


def load_funding_lines(
    csv_path: str | Path = DEFAULT_CLOUDWALK_EMISSIONS,
    *,
    spread_overrides: dict[str, float] | None = None,
) -> list[FundingLine]:
    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    overrides = spread_overrides or {}
    lines: list[FundingLine] = []
    for _, row in frame.iterrows():
        lines.append(_funding_line_from_row(row, overrides=overrides))
    return lines


def load_ime_financial_snapshots(
    cnpjs: Iterable[str],
    *,
    fund_names: dict[str, str] | None = None,
    cache_root: str | Path = DEFAULT_RUNTIME_CACHE_ROOT,
    portable_cache_root: str | Path | None = DEFAULT_PORTABLE_CACHE_ROOT,
) -> list[ImeFinancialSnapshot]:
    names = {only_digits(key): value for key, value in (fund_names or {}).items()}
    runtime_cache_root = Path(cache_root)
    portable_root = Path(portable_cache_root) if portable_cache_root is not None else None
    output: list[ImeFinancialSnapshot] = []
    for cnpj in sorted({only_digits(item) for item in cnpjs if only_digits(item)}):
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
            output.append(
                ImeFinancialSnapshot(
                    fund_name=fund_name,
                    cnpj=cnpj,
                    competencia="",
                    pl_total=None,
                    caixa=0.0,
                    titulos_publicos=0.0,
                    recebiveis=0.0,
                    cash_like_reported=0.0,
                    cash_like_residual_proxy=0.0,
                    cash_like=0.0,
                    cash_like_method="sem_cache",
                    source="",
                    included=False,
                    exclusion_reason="Sem IME em cache local para o CNPJ.",
                )
            )
            continue
        output.append(_ime_snapshot_from_cache(cnpj, fund_name, cached))
    return output


def build_financial_cost_outputs(
    *,
    lines: list[FundingLine],
    snapshots: list[ImeFinancialSnapshot],
    config: CostRunConfig,
) -> FinancialCostOutputs:
    line_rows, monthly_rows = _line_and_monthly_rows(lines, config)
    line_df = pd.DataFrame(line_rows)
    monthly_df = pd.DataFrame(monthly_rows)
    ime_df = _ime_snapshot_frame(snapshots, config)
    missing_df = _missing_inputs_frame(lines, config)
    summary_df = _summary_frame(line_df, ime_df, lines, config)
    methodology_md = _methodology_markdown(summary_df, missing_df, ime_df, config)
    return FinancialCostOutputs(
        summary_df=summary_df,
        line_df=line_df,
        monthly_df=monthly_df,
        ime_snapshot_df=ime_df,
        missing_inputs_df=missing_df,
        methodology_md=methodology_md,
    )


def export_financial_cost_outputs(
    outputs: FinancialCostOutputs,
    output_dir: str | Path = DEFAULT_FINANCIAL_COST_OUTPUT_DIR,
) -> dict[str, str]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    files = {
        "summary_csv": path / "cloudwalk_financial_cost_summary.csv",
        "by_line_csv": path / "cloudwalk_financial_cost_by_line.csv",
        "monthly_csv": path / "cloudwalk_financial_cost_monthly.csv",
        "ime_snapshot_csv": path / "cloudwalk_financial_cost_ime_snapshot.csv",
        "missing_inputs_csv": path / "cloudwalk_financial_cost_missing_inputs.csv",
        "methodology_md": path / "cloudwalk_financial_cost_methodology.md",
    }
    outputs.summary_df.to_csv(files["summary_csv"], index=False)
    outputs.line_df.to_csv(files["by_line_csv"], index=False)
    outputs.monthly_df.to_csv(files["monthly_csv"], index=False)
    outputs.ime_snapshot_df.to_csv(files["ime_snapshot_csv"], index=False)
    outputs.missing_inputs_df.to_csv(files["missing_inputs_csv"], index=False)
    files["methodology_md"].write_text(outputs.methodology_md, encoding="utf-8")
    return {key: str(value) for key, value in files.items()}


def _funding_line_from_row(row: pd.Series, *, overrides: dict[str, float]) -> FundingLine:
    fund_name = _display(row.get("Fundo"))
    cnpj = _display(row.get("CNPJ"))
    classe = _display(row.get("Cota/Classe"))
    tipo = _display(row.get("Tipo"))
    class_macro = _class_macro(tipo, classe)
    volume = parse_money_value(row.get("Volume"))
    remuneration = _display(row.get("Remuneração") or row.get("Juros/remuneração"))
    amortization_text = _display(row.get("Amortização principal"))
    source = _display(row.get("Fonte"))
    issue_date = _parse_issue_date(row)

    active_ok, exclusion_reason = _line_activity_status(tipo, classe, amortization_text, row.get("Status/evidência"))
    if not _is_interest_bearing_class(tipo, classe):
        active_ok = False
        exclusion_reason = "Classe subordinada/residual ou não remunerada por benchmark de dívida; excluída do custo financeiro explícito."
    if volume <= 0.0:
        active_ok = False
        exclusion_reason = "Volume emitido ausente ou zero."

    spread, spread_source = _spread_for_line(cnpj, classe, remuneration, overrides)
    convention = "nao_aplicavel"
    amortizations: tuple[tuple[date, float], ...] = ()
    warnings: tuple[str, ...] = ()
    if active_ok:
        convention, amortizations_list, warnings = _parse_line_amortizations(amortization_text, volume)
        amortizations = tuple(amortizations_list)
        if spread is None:
            warnings = warnings + ("Spread CDI+ não localizado; linha fica fora dos totais até input manual.",)

    return FundingLine(
        fund_name=fund_name,
        cnpj=cnpj,
        classe=classe,
        tipo=tipo,
        class_macro=class_macro,
        issue_date=issue_date,
        volume=volume,
        spread_aa=spread,
        spread_source=spread_source,
        remuneration=remuneration,
        amortization_text=amortization_text,
        amortization_convention=convention,
        amortizations=amortizations,
        source=source,
        included=active_ok,
        exclusion_reason=exclusion_reason,
        warnings=warnings,
    )


def _spread_for_line(
    cnpj: str,
    classe: str,
    remuneration: str,
    overrides: dict[str, float],
) -> tuple[float | None, str]:
    exact_key = line_key(cnpj, classe)
    cnpj_key = only_digits(cnpj)
    for key in (exact_key, cnpj_key, classe):
        if key in overrides:
            return overrides[key], f"override:{key}"
    parsed = parse_cdi_plus_spread(remuneration)
    if parsed is not None:
        return parsed, "curadoria:remuneracao"
    return None, "pendente"


def _line_activity_status(tipo: str, classe: str, amortization_text: str, evidence: Any) -> tuple[bool, str | None]:
    text = normalize_text(f"{tipo} {classe} {amortization_text} {evidence or ''}")
    inactive_tokens = (
        "fundo encerrado",
        "resgate total",
        "sem divida futura ativa",
        "substituido",
        "substituida",
        "nao usado",
        "linha desativada",
    )
    if any(token in text for token in inactive_tokens):
        return False, "Linha histórica/inativa segundo curadoria; excluída para evitar duplicidade."
    return True, None


def _is_interest_bearing_class(tipo: str, classe: str) -> bool:
    text = normalize_text(f"{tipo} {classe}")
    if "subordinada" in text and "mezan" not in text and "mezz" not in text:
        return False
    return "senior" in text or "mezan" in text or "mezz" in text


def _class_macro(tipo: str, classe: str) -> str:
    text = normalize_text(f"{tipo} {classe}")
    if "mezan" in text or "mezz" in text:
        return "mezzanino"
    if "senior" in text:
        return "senior"
    if "subordinada" in text:
        return "subordinada"
    return "outro"


def _parse_issue_date(row: pd.Series) -> date | None:
    for column in ("Data emissão / 1ª integralização", "Data encerramento/oferta", "Data deliberação"):
        parsed = parse_date_label(row.get(column))
        if parsed is not None:
            return parsed
    return None


def _parse_line_amortizations(text: str, volume: float) -> tuple[str, list[tuple[date, float]], tuple[str, ...]]:
    try:
        return parse_amortization_schedule(text, volume)
    except ValueError as exc:
        range_schedule = _parse_programmed_range_schedule(text, volume)
        if range_schedule is not None:
            return range_schedule

        normalized = normalize_text(text)
        if any(token in normalized for token in ("sem calendario fixo", "sem amortizacao", "remuneracao mensal")):
            return (
                "sem_cronograma_parseavel",
                [],
                (f"Cronograma não parseado automaticamente ({exc}); saldo mantido constante até novo input.",),
            )
        return (
            "sem_cronograma_parseavel",
            [],
            (f"Cronograma não parseado automaticamente ({exc}); saldo mantido constante até novo input.",),
        )


def _parse_programmed_range_schedule(text: str, volume: float) -> tuple[str, list[tuple[date, float]], tuple[str, ...]] | None:
    normalized = normalize_text(text)
    match = re.search(
        r"amortizacao programada de\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+a\s+(\d{1,2}/\d{1,2}/\d{2,4})",
        normalized,
    )
    if not match:
        return None
    start = parse_date_label(match.group(1))
    end = parse_date_label(match.group(2))
    if start is None or end is None or end < start:
        return None
    dates = _month_dates_inclusive(start, end)
    if not dates:
        return None
    amount = volume / len(dates)
    schedule = [(item_date, amount) for item_date in dates]
    return (
        "linear_de_intervalo_documentado",
        schedule,
        ("Texto informa apenas intervalo de amortização; cálculo usa parcelas mensais lineares nesse intervalo.",),
    )


def _line_and_monthly_rows(lines: list[FundingLine], config: CostRunConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    holidays = b3_market_holidays_for_dates([config.start_date, config.end_date, config.snapshot_date])
    total_du = _business_days_between(config.start_date, config.end_date + timedelta(days=1), holidays)
    total_days = max((config.end_date - config.start_date).days + 1, 1)
    line_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []

    for line in lines:
        saldo_snapshot = _balance_at(line, config.snapshot_date)
        saldo_inicio = _balance_at(line, config.start_date)
        scheduled = _scheduled_cost(line, config, holidays)
        monthly_rows.extend(scheduled["monthly_rows"])
        rate_aa = _line_total_rate(config.cdi_aa, line.spread_aa)
        snapshot_cost = (
            saldo_snapshot * ((1.0 + rate_aa) ** (total_du / 252.0) - 1.0)
            if line.included and line.has_rate and saldo_snapshot > 0.0
            else math.nan
        )
        line_rows.append(
            {
                "fund_name": line.fund_name,
                "cnpj": line.cnpj,
                "classe": line.classe,
                "tipo": line.tipo,
                "class_macro": line.class_macro,
                "line_key": line.line_key,
                "included": line.included,
                "included_in_cost": line.included and line.has_rate,
                "exclusion_reason": line.exclusion_reason or "",
                "volume_emitido": round(line.volume, 2),
                "issue_date": line.issue_date.isoformat() if line.issue_date else "",
                "spread_cdi_plus_aa": _round_or_none(line.spread_aa),
                "spread_source": line.spread_source,
                "cdi_aa": round(config.cdi_aa, 8),
                "taxa_total_aa": _round_or_none(rate_aa if line.has_rate else None),
                "saldo_snapshot": round(saldo_snapshot, 2),
                "saldo_inicio_periodo": round(saldo_inicio, 2),
                "saldo_medio_programado": round(scheduled["average_balance"], 2),
                "custo_snapshot_sem_amortizacao": _round_or_blank(snapshot_cost),
                "custo_programado_bruto": _round_or_blank(scheduled["gross_cost"]),
                "amortizacao_no_periodo": round(scheduled["principal_paid"], 2),
                "dias_corridos_base": total_days,
                "dias_uteis_base": total_du,
                "amortization_convention": line.amortization_convention,
                "warnings": " | ".join(line.warnings),
                "remuneration": line.remuneration,
                "amortization_text": line.amortization_text,
                "source": line.source,
            }
        )
    return line_rows, monthly_rows


def _scheduled_cost(line: FundingLine, config: CostRunConfig, holidays: Iterable[date]) -> dict[str, Any]:
    total_days = max((config.end_date - config.start_date).days + 1, 1)
    if not line.included or not line.has_rate:
        return {"gross_cost": math.nan, "average_balance": _average_balance(line, config), "principal_paid": 0.0, "monthly_rows": []}

    events = _period_event_dates(line, config)
    if not events:
        return {"gross_cost": 0.0, "average_balance": 0.0, "principal_paid": 0.0, "monthly_rows": []}

    gross_cost = 0.0
    balance_weighted_days = 0.0
    monthly_rows: list[dict[str, Any]] = []
    rate_aa = _line_total_rate(config.cdi_aa, line.spread_aa)
    for current, nxt in zip(events, events[1:]):
        if nxt <= current:
            continue
        balance = _balance_at(line, current)
        calendar_days = (nxt - current).days
        balance_weighted_days += balance * calendar_days
        du = _business_days_between(current, nxt, holidays)
        period_cost = balance * ((1.0 + rate_aa) ** (du / 252.0) - 1.0) if balance > 0.0 and du > 0 else 0.0
        gross_cost += period_cost
        if calendar_days > 0:
            monthly_rows.append(
                {
                    "mes": f"{current.year:04d}-{current.month:02d}",
                    "fund_name": line.fund_name,
                    "cnpj": line.cnpj,
                    "classe": line.classe,
                    "class_macro": line.class_macro,
                    "saldo_base": round(balance, 2),
                    "dias_corridos": calendar_days,
                    "dias_uteis": du,
                    "custo_programado_bruto": round(period_cost, 2),
                    "spread_cdi_plus_aa": _round_or_none(line.spread_aa),
                    "taxa_total_aa": round(rate_aa, 8),
                }
            )

    principal_paid = sum(amount for item_date, amount in line.amortizations if config.start_date <= item_date <= config.end_date)
    return {
        "gross_cost": gross_cost,
        "average_balance": balance_weighted_days / total_days,
        "principal_paid": principal_paid,
        "monthly_rows": monthly_rows,
    }


def _average_balance(line: FundingLine, config: CostRunConfig) -> float:
    events = _period_event_dates(line, config)
    if not events:
        return 0.0
    total_days = max((config.end_date - config.start_date).days + 1, 1)
    weighted = 0.0
    for current, nxt in zip(events, events[1:]):
        weighted += _balance_at(line, current) * max((nxt - current).days, 0)
    return weighted / total_days


def _period_event_dates(line: FundingLine, config: CostRunConfig) -> list[date]:
    end_exclusive = config.end_date + timedelta(days=1)
    events = {config.start_date, end_exclusive}
    for month_start in _month_start_dates(config.start_date, config.end_date):
        events.add(month_start)
    if line.issue_date and config.start_date <= line.issue_date <= config.end_date:
        events.add(line.issue_date)
    for item_date, _ in line.amortizations:
        if config.start_date <= item_date <= config.end_date:
            events.add(item_date)
    return sorted(events)


def _balance_at(line: FundingLine, item_date: date) -> float:
    if not line.included:
        return 0.0
    if line.issue_date is not None and item_date < line.issue_date:
        return 0.0
    paid = sum(amount for pay_date, amount in line.amortizations if pay_date <= item_date)
    return max(line.volume - paid, 0.0)


def _summary_frame(
    line_df: pd.DataFrame,
    ime_df: pd.DataFrame,
    lines: list[FundingLine],
    config: CostRunConfig,
) -> pd.DataFrame:
    included_lines = [line for line in lines if line.included]
    missing_lines = [line for line in included_lines if not line.has_rate]
    snapshot_cost = _sum_numeric(line_df.get("custo_snapshot_sem_amortizacao"))
    scheduled_cost = _sum_numeric(line_df.get("custo_programado_bruto"))
    snapshot_balance = _sum_numeric(line_df.get("saldo_snapshot"), included_mask=line_df.get("included_in_cost"))
    scheduled_average_balance = _sum_numeric(line_df.get("saldo_medio_programado"), included_mask=line_df.get("included_in_cost"))
    lines_with_scheduled_balance = int(
        (
            line_df.get("included_in_cost", pd.Series(dtype=bool)).fillna(False).astype(bool)
            & pd.to_numeric(line_df.get("saldo_medio_programado", pd.Series(dtype=float)), errors="coerce").fillna(0.0).gt(0.0)
        ).sum()
    )
    missing_balance = sum(_balance_at(line, config.snapshot_date) for line in missing_lines)
    cash_yield = _sum_numeric(ime_df.get("rendimento_estimado_caixa_lft"))

    rows = [
        {
            "estimativa": "1_snapshot_pl_sem_amortizacao",
            "descricao": "Saldo remunerado na data snapshot vezes CDI+spread por todo o ano; não reflete amortizações/captações intraperíodo.",
            "despesa_financeira_bruta": round(snapshot_cost, 2),
            "receita_antecipacao_gross_up_sugerida": round(snapshot_cost, 2),
            "rendimento_caixa_lft": 0.0,
            "despesa_financeira_liquida": round(snapshot_cost, 2),
            "saldo_base": round(snapshot_balance, 2),
            "linhas_incluidas": lines_with_scheduled_balance,
            "linhas_sem_spread": len(missing_lines),
            "saldo_snapshot_sem_spread": round(missing_balance, 2),
        },
        {
            "estimativa": "2_programado_bruto_com_amortizacao",
            "descricao": "Custo bruto por linha com saldo diário aproximado, cronogramas de amortização e captações dentro do período.",
            "despesa_financeira_bruta": round(scheduled_cost, 2),
            "receita_antecipacao_gross_up_sugerida": round(scheduled_cost, 2),
            "rendimento_caixa_lft": 0.0,
            "despesa_financeira_liquida": round(scheduled_cost, 2),
            "saldo_base": round(scheduled_average_balance, 2),
            "linhas_incluidas": lines_with_scheduled_balance,
            "linhas_sem_spread": len(missing_lines),
            "saldo_snapshot_sem_spread": round(missing_balance, 2),
        },
        {
            "estimativa": "3_programado_liquido_caixa_lft",
            "descricao": "Custo bruto programado menos rendimento CDI estimado sobre caixa/LFT: maior entre caixa+títulos reportados e proxy PL-recebíveis.",
            "despesa_financeira_bruta": round(scheduled_cost, 2),
            "receita_antecipacao_gross_up_sugerida": round(scheduled_cost, 2),
            "rendimento_caixa_lft": round(cash_yield, 2),
            "despesa_financeira_liquida": round(scheduled_cost - cash_yield, 2),
            "saldo_base": round(scheduled_average_balance, 2),
            "linhas_incluidas": lines_with_scheduled_balance,
            "linhas_sem_spread": len(missing_lines),
            "saldo_snapshot_sem_spread": round(missing_balance, 2),
        },
    ]
    output = pd.DataFrame(rows)
    output["periodo_inicio"] = config.start_date.isoformat()
    output["periodo_fim"] = config.end_date.isoformat()
    output["snapshot_date"] = config.snapshot_date.isoformat()
    output["cdi_aa"] = round(config.cdi_aa, 8)
    output["cdi_source"] = config.cdi_source
    output["cash_yield_cdi_factor"] = config.cash_yield_cdi_factor
    return output


def _ime_snapshot_frame(snapshots: list[ImeFinancialSnapshot], config: CostRunConfig) -> pd.DataFrame:
    holidays = b3_market_holidays_for_dates([config.start_date, config.end_date])
    total_du = _business_days_between(config.start_date, config.end_date + timedelta(days=1), holidays)
    cash_rate = config.cdi_aa * config.cash_yield_cdi_factor
    rows = []
    for item in snapshots:
        cash_yield = item.cash_like * ((1.0 + cash_rate) ** (total_du / 252.0) - 1.0) if item.included else 0.0
        rows.append(
            {
                "fund_name": item.fund_name,
                "cnpj": item.cnpj,
                "competencia": item.competencia,
                "pl_total": _round_or_blank(item.pl_total),
                "caixa": round(item.caixa, 2),
                "titulos_publicos": round(item.titulos_publicos, 2),
                "recebiveis": round(item.recebiveis, 2),
                "cash_like_reported": round(item.cash_like_reported, 2),
                "cash_like_residual_proxy": round(item.cash_like_residual_proxy, 2),
                "cash_like_caixa_lft": round(item.cash_like, 2),
                "cash_like_method": item.cash_like_method,
                "rendimento_estimado_caixa_lft": round(cash_yield, 2),
                "included": item.included,
                "exclusion_reason": item.exclusion_reason or "",
                "source": item.source,
            }
        )
    return pd.DataFrame(rows)


def _missing_inputs_frame(lines: list[FundingLine], config: CostRunConfig) -> pd.DataFrame:
    columns = [
        "fund_name",
        "cnpj",
        "classe",
        "tipo",
        "line_key",
        "saldo_snapshot",
        "volume_emitido",
        "remuneration",
        "suggested_override_key",
        "suggested_override_value_example",
        "source",
    ]
    rows = []
    for line in lines:
        if not line.included or line.has_rate:
            continue
        rows.append(
            {
                "fund_name": line.fund_name,
                "cnpj": line.cnpj,
                "classe": line.classe,
                "tipo": line.tipo,
                "line_key": line.line_key,
                "saldo_snapshot": round(_balance_at(line, config.snapshot_date), 2),
                "volume_emitido": round(line.volume, 2),
                "remuneration": line.remuneration,
                "suggested_override_key": line.line_key,
                "suggested_override_value_example": "0.0075 para CDI + 0,75% a.a.",
                "source": line.source,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _methodology_markdown(
    summary_df: pd.DataFrame,
    missing_df: pd.DataFrame,
    ime_df: pd.DataFrame,
    config: CostRunConfig,
) -> str:
    missing_count = len(missing_df.index)
    missing_balance = _sum_numeric(missing_df.get("saldo_snapshot")) if not missing_df.empty else 0.0
    cash_like = _sum_numeric(ime_df.get("cash_like_caixa_lft")) if not ime_df.empty else 0.0
    lines = [
        "# Cloudwalk - estimativas de custo financeiro",
        "",
        f"Período: {config.start_date.isoformat()} a {config.end_date.isoformat()}. Snapshot: {config.snapshot_date.isoformat()}.",
        f"CDI/DI proxy anual: {config.cdi_aa:.4%}. Fonte: {config.cdi_source}.",
        "",
        "## Estimativas",
        "",
        "1. `snapshot_pl_sem_amortizacao`: saldo remunerado na data snapshot vezes CDI+spread por todo o período.",
        "2. `programado_bruto_com_amortizacao`: saldo por linha ajustado por captações e amortizações documentadas; a despesa bruta é a referência para gross-up da receita de antecipação.",
        "3. `programado_liquido_caixa_lft`: mesma despesa bruta, menos rendimento CDI estimado sobre caixa/LFT. A base usa o maior valor entre caixa+títulos públicos reportados e a proxy `PL - recebíveis`, quando há recebíveis positivos.",
        "",
        "## Leitura contábil/gerencial",
        "",
        "A coluna `receita_antecipacao_gross_up_sugerida` repõe, em receita bruta gerencial, a mesma despesa financeira bruta explicitada. O rendimento de caixa/LFT fica separado para não misturar custo de funding com carry de liquidez.",
        "",
        "## Lacunas",
        "",
        f"Linhas ativas sem spread CDI+ parseável: {missing_count}. Saldo snapshot afetado: R$ {missing_balance / MONEY_SCALE:,.1f} mm.",
        f"Caixa/LFT usado na estimativa líquida: R$ {cash_like / MONEY_SCALE:,.1f} mm.",
        "",
        "Quando você passar os spreads pendentes, preencha `config/cloudwalk_financial_cost_inputs.json` em `spreads_cdi_plus_aa` usando a chave `CNPJ|classe` listada em `cloudwalk_financial_cost_missing_inputs.csv`.",
        "",
        "## Totais",
        "",
        _simple_markdown_table(summary_df),
        "",
    ]
    return "\n".join(lines)


def _find_latest_cached_ime(cnpj: str, cache_root: Path) -> dict[str, Any] | None:
    if not cache_root.exists():
        return None
    candidates: list[dict[str, Any]] = []
    for manifest_path in cache_root.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if only_digits(manifest.get("cnpj_fundo")) != cnpj:
            continue
        files = manifest.get("files") or {}
        wide_path = manifest_path.parent / str(files.get("wide_csv_path") or "informes_wide.csv")
        listas_path = manifest_path.parent / str(files.get("listas_csv_path") or "estruturas_lista.csv")
        if not wide_path.exists():
            continue
        competencia = _latest_competencia(manifest.get("competencias") or [])
        if not competencia:
            continue
        candidates.append(
            {
                "cache_dir": manifest_path.parent,
                "wide_csv_path": wide_path,
                "listas_csv_path": listas_path if listas_path.exists() else None,
                "competencia": competencia,
                "competencia_key": _competencia_sort_key(competencia),
            }
        )
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item["competencia_key"])[-1]


def _ime_snapshot_from_cache(cnpj: str, fund_name: str, cached: dict[str, Any]) -> ImeFinancialSnapshot:
    competencia = str(cached["competencia"])
    try:
        wide_df = pd.read_csv(cached["wide_csv_path"], dtype=str, keep_default_na=False)
        wide_lookup = wide_df.set_index("tag_path", drop=False) if "tag_path" in wide_df.columns else pd.DataFrame()
        caixa = _wide_numeric_value(wide_lookup, "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_DISPONIB", competencia) or 0.0
        titpub = _wide_numeric_value(wide_lookup, "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_TITPUB_FED", competencia) or 0.0
        pl_total = _wide_numeric_value(wide_lookup, "DOC_ARQ/LISTA_INFORM/PATRLIQ/VL_PATRIM_LIQ", competencia)
        if pl_total is None:
            pl_total = _wide_numeric_value(wide_lookup, "DOC_ARQ/LISTA_INFORM/PATRLIQ/VL_SOM_PATRLIQ", competencia)
        recebiveis = _ime_receivables_value(wide_lookup, competencia) or 0.0
    except Exception as exc:  # noqa: BLE001
        return ImeFinancialSnapshot(
            fund_name=fund_name,
            cnpj=cnpj,
            competencia=competencia,
            pl_total=None,
            caixa=0.0,
            titulos_publicos=0.0,
            recebiveis=0.0,
            cash_like_reported=0.0,
            cash_like_residual_proxy=0.0,
            cash_like=0.0,
            cash_like_method="erro",
            source=str(cached.get("cache_dir") or ""),
            included=False,
            exclusion_reason=f"Falha ao ler IME: {type(exc).__name__}: {exc}",
        )

    cash_like_reported = float(caixa) + float(titpub)
    cash_like_residual_proxy = max(float(pl_total or 0.0) - float(recebiveis), 0.0) if float(recebiveis) > 0.0 else 0.0
    cash_like = max(cash_like_reported, cash_like_residual_proxy)
    cash_like_method = "reportado_caixa_titpub"
    if cash_like_residual_proxy > cash_like_reported:
        cash_like_method = "proxy_pl_menos_recebiveis"

    return ImeFinancialSnapshot(
        fund_name=fund_name,
        cnpj=cnpj,
        competencia=competencia,
        pl_total=pl_total,
        caixa=float(caixa),
        titulos_publicos=float(titpub),
        recebiveis=float(recebiveis),
        cash_like_reported=cash_like_reported,
        cash_like_residual_proxy=cash_like_residual_proxy,
        cash_like=cash_like,
        cash_like_method=cash_like_method,
        source=str(cached.get("cache_dir") or ""),
        included=True,
        exclusion_reason=None,
    )


def _ime_receivables_value(wide_lookup: pd.DataFrame, competencia: str) -> float | None:
    primary_paths = [
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/DICRED/VL_DICRED",
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_SOM_DICRED_AQUIS",
        "DOC_ARQ/LISTA_INFORM/CART_SEGMT/VL_SOM_CART_SEGMT",
    ]
    primary_values: list[float] = []
    for path in primary_paths:
        value = _wide_numeric_value(wide_lookup, path, competencia)
        if value is not None:
            primary_values.append(float(value))
    positive_primary = [value for value in primary_values if value > 0.0]
    if positive_primary:
        return positive_primary[0]
    if primary_values:
        return primary_values[0]

    granular_paths = [
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_CRED_EXISTE_VENC_ADIMPL",
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_CRED_EXISTE_VENC_INAD",
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_CRED_EXISTE_INAD",
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/DICRED/VL_DICRED_CEDENT",
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/DICRED/VL_DICRED_EXISTE_VENC_INAD",
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/DICRED/VL_DICRED_EXISTE_INAD",
    ]
    granular = [_wide_numeric_value(wide_lookup, path, competencia) for path in granular_paths]
    numeric_granular = [float(value) for value in granular if value is not None]
    return sum(numeric_granular) if numeric_granular else None


def _wide_numeric_value(wide_lookup: pd.DataFrame, tag_path: str, competencia: str) -> float | None:
    if wide_lookup.empty or tag_path not in wide_lookup.index or competencia not in wide_lookup.columns:
        return None
    raw = wide_lookup.loc[tag_path, competencia]
    values = raw.tolist() if isinstance(raw, pd.Series) else [raw]
    for value in values:
        parsed = _parse_number(value)
        if parsed is not None:
            return parsed
    return None


def _parse_override_spread(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed / 100.0 if parsed > 1.0 else parsed
    text = str(value)
    if "%" in text:
        return parse_cdi_plus_spread(text) or _parse_percentage_points(text)
    return parse_cdi_plus_spread(text) or _parse_percent_decimal(text)


def _parse_percentage_points(value: str) -> float | None:
    cleaned = re.sub(r"[^\d,.\-]", "", str(value or ""))
    if not cleaned:
        return None
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned) / 100.0
    except ValueError:
        return None


def _parse_percent_decimal(value: str) -> float | None:
    cleaned = re.sub(r"[^\d,.\-]", "", str(value or ""))
    if not cleaned:
        return None
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    if abs(parsed) > 1.0:
        return parsed / 100.0
    return parsed


def _parse_number(value: Any) -> float | None:
    text = str(value if value is not None else "").strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    cleaned = re.sub(r"[^\d,.\-]", "", text)
    if not cleaned:
        return None
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _month_dates_inclusive(start: date, end: date) -> list[date]:
    output: list[date] = []
    current = start
    while current <= end:
        output.append(current)
        current = _add_months_keep_day(current, 1)
    return output


def _month_start_dates(start: date, end: date) -> list[date]:
    current = date(start.year, start.month, 1)
    if current < start:
        current = _add_months_keep_day(current, 1)
    output: list[date] = []
    while current <= end:
        output.append(current)
        current = _add_months_keep_day(current, 1)
    return output


def _add_months_keep_day(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, _last_day(year, month))
    return date(year, month, day)


def _last_day(year: int, month: int) -> int:
    next_month = date(year + int(month == 12), 1 if month == 12 else month + 1, 1)
    return (next_month - timedelta(days=1)).day


def _business_days_between(start: date, end_exclusive: date, holidays: Iterable[date]) -> int:
    if end_exclusive <= start:
        return 0
    return networkdays(start, end_exclusive - timedelta(days=1), holidays)


def _line_total_rate(cdi_aa: float, spread_aa: float | None) -> float:
    return max(cdi_aa + float(spread_aa or 0.0), -0.999999)


def _sum_numeric(values: Any, included_mask: Any | None = None) -> float:
    if values is None:
        return 0.0
    series = pd.to_numeric(pd.Series(values), errors="coerce")
    if included_mask is not None:
        mask = pd.Series(included_mask).fillna(False).astype(bool)
        series = series[mask]
    return float(series.dropna().sum())


def _round_or_none(value: float | None) -> float | None:
    return None if value is None or pd.isna(value) else round(float(value), 8)


def _round_or_blank(value: float | None) -> float | str:
    if value is None or pd.isna(value):
        return ""
    return round(float(value), 2)


def _display(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    return text if text and text.lower() not in {"nan", "none", "<na>"} else ""


def _latest_competencia(competencias: Iterable[Any]) -> str:
    valid = [str(item) for item in competencias if _competencia_sort_key(str(item)) != (0, 0)]
    return sorted(valid, key=_competencia_sort_key)[-1] if valid else ""


def _competencia_sort_key(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{1,2})/(\d{4})", str(value or "").strip())
    if not match:
        return (0, 0)
    return (int(match.group(2)), int(match.group(1)))


def utc_now_label() -> str:
    return datetime.now(timezone.utc).isoformat()


def _simple_markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_Sem linhas._"
    columns = [str(column) for column in frame.columns]
    rows = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, item in frame.iterrows():
        values = [str(item.get(column, "")) for column in frame.columns]
        rows.append("| " + " | ".join(value.replace("\n", " ") for value in values) + " |")
    return "\n".join(rows)
