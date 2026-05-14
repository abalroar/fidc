from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
import calendar
import json
import re
import unicodedata
from typing import Any

import pandas as pd


DEFAULT_REFERENCE_DATE = date(2026, 5, 14)
DEFAULT_CLOUDWALK_EMISSIONS = Path("data/regulatory_profiles/cloudwalk_cotas_emissoes_pagamentos.csv")
DEFAULT_WATERFALL_OUTPUT_DIR = Path("reports/waterfall")


@dataclass(frozen=True)
class FidcAmortizationSchedule:
    fund_name: str
    cnpj: str
    classe: str
    volume_emitido: float
    saldo_atual: float
    convention: str
    schedule: list[tuple[date, float]]
    included: bool
    exclusion_reason: str | None
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WaterfallRow:
    data: date
    saldo_devedor_total: float
    amortizacao_total: float
    recebiveis_bucket: float
    caixa_disponivel: float
    posicao_liquida: float
    breakdown: dict[str, float]


@dataclass(frozen=True)
class ParsedAmortization:
    percentages: list[tuple[date, float]]
    convention_hint: str | None = None


def detect_amortization_convention(dates: list[date], percentages: list[float]) -> str:
    """Detecta se percentuais documentais são incrementais ou acumulados."""

    if not dates or not percentages or len(dates) != len(percentages):
        raise ValueError("Cronograma de amortização sem pares válidos de data e percentual.")

    total = sum(percentages)
    is_monotone = all(percentages[index] <= percentages[index + 1] for index in range(len(percentages) - 1))
    last = percentages[-1]
    last_is_100 = abs(last - 100.0) < 0.5

    if abs(total - 100.0) <= 2.0:
        return "incremental"
    if is_monotone and last_is_100 and total > 100.0:
        return "cumulative"
    if 95.0 <= total <= 105.0 and not last_is_100:
        return "incremental"
    if is_monotone and total > 100.0:
        raise ValueError(
            "Cronograma parece acumulado, mas o último percentual não fecha em 100%; "
            "exige normalização explícita por FIDC."
        )
    raise ValueError(
        "Não foi possível determinar a convenção de amortização automaticamente. "
        f"Soma={total:.1f}%, monotone={is_monotone}, last={last:.1f}%. "
        "Adicione campo 'amortization_convention: incremental|cumulative' nos dados do FIDC."
    )


def percentages_to_incremental(percentages: list[float], convention: str) -> list[float]:
    if convention == "incremental":
        return list(percentages)
    if convention != "cumulative":
        raise ValueError(f"Convenção de amortização inválida: {convention}")

    previous = 0.0
    output: list[float] = []
    for value in percentages:
        delta = value - previous
        if delta < -1e-9:
            raise ValueError("Percentuais acumulados não são monotonicamente crescentes.")
        output.append(max(delta, 0.0))
        previous = value
    return output


def validate_incremental_percentages(percentages: list[float]) -> tuple[bool, tuple[str, ...]]:
    total = sum(percentages)
    if 95.0 <= total <= 105.0:
        warnings = ()
        if abs(total - 100.0) > 2.0:
            warnings = (f"Soma incremental de amortização fecha em {total:.1f}%, fora da banda operacional de 98%-102%.",)
        return True, warnings
    return False, (f"Soma incremental de amortização fecha em {total:.1f}%, fora da faixa aceita de 95%-105%.",)


def parse_amortization_schedule(
    text: Any,
    volume_emitido: float,
    *,
    amortization_convention: str | None = None,
) -> tuple[str, list[tuple[date, float]], tuple[str, ...]]:
    raw = str(text or "").strip()
    normalized = normalize_text(raw)
    if not raw or normalized in {"nan", "none", "<na>"}:
        raise ValueError("Amortização não mapeada.")
    if any(token in normalized for token in ["sem amortizacao", "sem calendario fixo", "cronograma nao estruturado"]):
        raise ValueError("Amortização não mapeada no campo de curadoria.")
    if "cronograma nao localizado" in normalized or "sem campo numerico" in normalized:
        raise ValueError("Cronograma de amortização não localizado na curadoria.")

    parsed = _parse_bullet(raw) or _parse_linear(raw) or _parse_dated_percentages(raw)
    if not parsed.percentages:
        raise ValueError("Não foi possível extrair datas e percentuais de amortização do texto.")

    dates = [item[0] for item in parsed.percentages]
    percentages = [item[1] for item in parsed.percentages]
    convention = amortization_convention or parsed.convention_hint
    if convention is None:
        convention = detect_amortization_convention(dates, percentages)
    if convention not in {"incremental", "cumulative"}:
        raise ValueError(f"Convenção de amortização inválida: {convention}")

    incremental_percentages = percentages_to_incremental(percentages, convention)
    is_valid, warnings = validate_incremental_percentages(incremental_percentages)
    if not is_valid:
        raise ValueError(warnings[0])

    values = [(item_date, volume_emitido * pct / 100.0) for item_date, pct in zip(dates, incremental_percentages)]
    if values and abs(sum(incremental_percentages) - 100.0) <= 0.1:
        current_total = sum(amount for _, amount in values)
        final_date, final_amount = values[-1]
        values[-1] = (final_date, max(final_amount + (volume_emitido - current_total), 0.0))
    return convention, values, warnings


def load_cloudwalk_emissions(
    csv_path: str | Path = DEFAULT_CLOUDWALK_EMISSIONS,
    *,
    reference_date: date = DEFAULT_REFERENCE_DATE,
) -> list[FidcAmortizationSchedule]:
    path = Path(csv_path)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    schedules: list[FidcAmortizationSchedule] = []
    for _, row in frame.iterrows():
        fund_name = display(row.get("Fundo"))
        cnpj = display(row.get("CNPJ"))
        classe = display(row.get("Cota/Classe"))
        tipo = display(row.get("Tipo"))
        if not _is_senior(classe, tipo):
            schedules.append(
                _excluded_schedule(
                    fund_name,
                    cnpj,
                    classe,
                    "Classe não sênior; waterfall considera apenas dívida sênior.",
                )
            )
            continue

        volume = parse_money_value(row.get("Volume"))
        if volume <= 0.0:
            schedules.append(_excluded_schedule(fund_name, cnpj, classe, "Volume sênior ausente ou zero."))
            continue

        try:
            convention, full_schedule, warnings = parse_amortization_schedule(row.get("Amortização principal"), volume)
        except ValueError as exc:
            schedules.append(_excluded_schedule(fund_name, cnpj, classe, str(exc), volume_emitido=volume))
            continue

        paid = sum(amount for item_date, amount in full_schedule if item_date < reference_date)
        future_schedule = [(item_date, amount) for item_date, amount in full_schedule if item_date >= reference_date]
        saldo_atual = max(volume - paid, 0.0)
        schedules.append(
            FidcAmortizationSchedule(
                fund_name=fund_name,
                cnpj=cnpj,
                classe=classe,
                volume_emitido=volume,
                saldo_atual=saldo_atual,
                convention=convention,
                schedule=future_schedule,
                included=True,
                exclusion_reason=None,
                warnings=warnings,
            )
        )
    return schedules


def build_waterfall_schedule(
    schedules: list[FidcAmortizationSchedule],
    caixa_inicial: float,
    recebiveis_por_bucket: dict[str, float],
    *,
    reference_date: date = DEFAULT_REFERENCE_DATE,
) -> list[WaterfallRow]:
    included = [schedule for schedule in schedules if schedule.included]
    if not included:
        return []

    amortization_by_date: dict[date, dict[str, float]] = {}
    for schedule in included:
        for item_date, amount in schedule.schedule:
            if item_date < reference_date:
                continue
            by_fund = amortization_by_date.setdefault(item_date, {})
            by_fund[schedule.fund_name] = by_fund.get(schedule.fund_name, 0.0) + amount

    receivables_by_date = _receivables_by_date(recebiveis_por_bucket, reference_date)
    event_dates = sorted(set(amortization_by_date) | set(receivables_by_date))
    if not event_dates:
        return []

    saldo = sum(schedule.saldo_atual for schedule in included)
    caixa = float(caixa_inicial)
    recebiveis_acumulados = 0.0
    rows: list[WaterfallRow] = []
    for item_date in event_dates:
        breakdown = amortization_by_date.get(item_date, {})
        amortizacao_total = sum(breakdown.values())
        saldo = max(saldo - amortizacao_total, 0.0)
        recebiveis_acumulados += receivables_by_date.get(item_date, 0.0)
        rows.append(
            WaterfallRow(
                data=item_date,
                saldo_devedor_total=saldo,
                amortizacao_total=amortizacao_total,
                recebiveis_bucket=recebiveis_acumulados,
                caixa_disponivel=caixa,
                posicao_liquida=caixa + recebiveis_acumulados - saldo,
                breakdown=dict(sorted(breakdown.items())),
            )
        )
    return rows


def export_waterfall(
    rows: list[WaterfallRow],
    schedules: list[FidcAmortizationSchedule],
    output_dir: str | Path = DEFAULT_WATERFALL_OUTPUT_DIR,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    waterfall_path = output_path / "waterfall_cloudwalk.csv"
    plot_path = output_path / "waterfall_cloudwalk_plot.png"
    report_path = output_path / "waterfall_inclusion_report.csv"

    _waterfall_frame(rows).to_csv(waterfall_path, index=False)
    _inclusion_report_frame(schedules).to_csv(report_path, index=False)
    _save_waterfall_plot(rows, plot_path)
    return {
        "waterfall_csv": str(waterfall_path),
        "plot_png": str(plot_path),
        "inclusion_report_csv": str(report_path),
    }


def load_waterfall_inputs(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    caixa = float(payload.get("caixa_disponivel") or 0.0) + float(payload.get("tvm") or 0.0)
    return {
        "reference_date": date.fromisoformat(str(payload.get("data_referencia") or DEFAULT_REFERENCE_DATE.isoformat())),
        "caixa_inicial": caixa,
        "recebiveis": {str(key): float(value or 0.0) for key, value in (payload.get("recebiveis") or {}).items()},
    }


def parse_money_value(value: Any) -> float:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return 0.0
    if any(token in normalize_text(text) for token in ["nao inform", "nao fix", "depende"]):
        return 0.0
    cleaned = re.sub(r"[^\d,.\-]", "", text)
    if not cleaned:
        return 0.0
    if "," in cleaned:
        integer, decimal = cleaned.rsplit(",", 1)
        integer_digits = re.sub(r"\D", "", integer)
        decimal_digits = re.sub(r"\D", "", decimal)[:2].ljust(2, "0")
        if not integer_digits:
            return 0.0
        return float(f"{integer_digits}.{decimal_digits}")
    if "." in cleaned and cleaned.count(".") == 1:
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    digits = re.sub(r"\D", "", cleaned)
    return float(digits or 0.0)


def display(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return "—"
    return text


def normalize_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip()


def _parse_bullet(text: str) -> ParsedAmortization | None:
    normalized = normalize_text(text)
    if "bullet" not in normalized:
        return None
    parsed_date = _first_date_in_text(text)
    if parsed_date is None:
        raise ValueError("Bullet identificado sem data de vencimento parseável.")
    return ParsedAmortization(percentages=[(parsed_date, 100.0)], convention_hint="incremental")


def _parse_linear(text: str) -> ParsedAmortization | None:
    normalized = normalize_text(text)
    match = re.search(r"linear\s+(?:em\s+)?(\d+)\s+parcelas?.*?(?:a partir de|desde)\s+([^.;,]+)", normalized)
    if not match:
        return None
    count = int(match.group(1))
    if count <= 0:
        raise ValueError("Cronograma linear com número de parcelas inválido.")
    start = parse_date_label(match.group(2))
    if start is None:
        raise ValueError("Cronograma linear sem data inicial parseável.")
    amount = 100.0 / count
    return ParsedAmortization(
        percentages=[(_add_months(start, index), amount) for index in range(count)],
        convention_hint="incremental",
    )


def _parse_dated_percentages(text: str) -> ParsedAmortization:
    entries: list[tuple[date, float]] = []
    normalized = normalize_text(text)
    date_pattern = r"(?:\d{1,2}/\d{1,2}/\d{2,4}|(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-z]*/\d{2,4})"
    percent_pattern = r"\d{1,3}(?:[,.]\d{1,4})?\s*%"

    date_then_percent = rf"({date_pattern})(?:\s*(?::|=|->|-)\s*|\s+)({percent_pattern})"
    for match in re.finditer(date_then_percent, normalized):
        item_date = parse_date_label(match.group(1))
        percent = parse_percent(match.group(2))
        if item_date is not None and percent is not None:
            entries.append((item_date, percent))

    for match in re.finditer(rf"({percent_pattern})\D{{0,40}}?(?:em|no|na|para|ate|até)\s+({date_pattern})", normalized):
        item_date = parse_date_label(match.group(2))
        percent = parse_percent(match.group(1))
        if item_date is not None and percent is not None:
            entries.append((item_date, percent))

    unique: dict[tuple[date, float], tuple[date, float]] = {}
    for item in entries:
        unique[(item[0], round(item[1], 6))] = item
    return ParsedAmortization(percentages=sorted(unique.values(), key=lambda item: item[0]))


def parse_percent(value: str) -> float | None:
    cleaned = re.sub(r"[^\d,.]", "", value)
    if not cleaned:
        return None
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date_label(value: Any) -> date | None:
    raw = str(value or "").strip()
    normalized = normalize_text(raw)
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", normalized)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = _normalize_year(int(match.group(3)))
        return date(year, month, day)

    match = re.search(r"\b(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-z]*/(\d{2,4})\b", normalized)
    if not match:
        return None
    month = {
        "jan": 1,
        "fev": 2,
        "mar": 3,
        "abr": 4,
        "mai": 5,
        "jun": 6,
        "jul": 7,
        "ago": 8,
        "set": 9,
        "out": 10,
        "nov": 11,
        "dez": 12,
    }[match.group(1)]
    year = _normalize_year(int(match.group(2)))
    return date(year, month, calendar.monthrange(year, month)[1])


def _first_date_in_text(text: str) -> date | None:
    normalized = normalize_text(text)
    match = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", normalized)
    if match:
        return parse_date_label(match.group(0))
    match = re.search(r"\b(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-z]*/\d{2,4}\b", normalized)
    if match:
        return parse_date_label(match.group(0))
    return None


def _waterfall_frame(rows: list[WaterfallRow]) -> pd.DataFrame:
    fund_columns = sorted({fund for row in rows for fund in row.breakdown})
    output: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "data": row.data.isoformat(),
            "saldo_devedor_total": row.saldo_devedor_total,
            "amortizacao_total": row.amortizacao_total,
            "recebiveis_bucket_acumulado": row.recebiveis_bucket,
            "caixa_disponivel": row.caixa_disponivel,
            "posicao_liquida": row.posicao_liquida,
        }
        for fund in fund_columns:
            item[fund] = row.breakdown.get(fund, 0.0)
        output.append({key: round(value, 2) if isinstance(value, float) else value for key, value in item.items()})
    return pd.DataFrame(
        output,
        columns=[
            "data",
            "saldo_devedor_total",
            "amortizacao_total",
            "recebiveis_bucket_acumulado",
            "caixa_disponivel",
            "posicao_liquida",
            *fund_columns,
        ],
    )


def _inclusion_report_frame(schedules: list[FidcAmortizationSchedule]) -> pd.DataFrame:
    rows = []
    for schedule in schedules:
        dates = [item[0] for item in schedule.schedule]
        rows.append(
            {
                "fund_name": schedule.fund_name,
                "cnpj": schedule.cnpj,
                "classe": schedule.classe,
                "included": schedule.included,
                "exclusion_reason": schedule.exclusion_reason or "",
                "convention_detected": schedule.convention,
                "volume_emitido": schedule.volume_emitido,
                "saldo_atual": schedule.saldo_atual,
                "num_amortization_dates": len(dates),
                "first_date": min(dates).isoformat() if dates else "",
                "last_date": max(dates).isoformat() if dates else "",
                "warnings": " | ".join(schedule.warnings),
            }
        )
    return pd.DataFrame(rows)


def _save_waterfall_plot(rows: list[WaterfallRow], plot_path: Path) -> None:
    try:
        import matplotlib
    except ModuleNotFoundError:
        _save_pillow_plot(rows, plot_path)
        return

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(13, 7))
    if not rows:
        ax.text(
            0.5,
            0.5,
            "Nenhum FIDC Cloudwalk incluído: cronogramas sênior insuficientes ou ambíguos.",
            ha="center",
            va="center",
            fontsize=13,
        )
        ax.axis("off")
        fig.savefig(plot_path, dpi=160, bbox_inches="tight")
        plt.close(fig)
        return

    dates = [row.data for row in rows]
    saldo = [row.saldo_devedor_total / 1_000_000.0 for row in rows]
    posicao = [row.posicao_liquida / 1_000_000.0 for row in rows]
    funds = sorted({fund for row in rows for fund in row.breakdown})
    bottoms = [0.0] * len(rows)
    for fund in funds:
        values = [row.breakdown.get(fund, 0.0) / 1_000_000.0 for row in rows]
        ax.bar(dates, values, bottom=bottoms, width=18, alpha=0.65, label=fund[:32])
        bottoms = [base + value for base, value in zip(bottoms, values)]

    ax.plot(dates, saldo, color="#1F1F1F", linewidth=2.4, label="Saldo devedor")
    ax.fill_between(dates, saldo, color="#E5E5E5", alpha=0.35)
    ax.plot(dates, posicao, color="#EC7000", linewidth=2.0, label="Posição líquida")
    ax.set_title("Waterfall Cloudwalk — Cronograma de Amortizações")
    ax.set_ylabel("R$ milhões")
    ax.grid(axis="y", color="#E5E5E5", linewidth=0.8)
    ax.legend(loc="best", fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(plot_path, dpi=160)
    plt.close(fig)


def _save_pillow_plot(rows: list[WaterfallRow], plot_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1280, 720
    margin_left, margin_right, margin_top, margin_bottom = 90, 40, 86, 86
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    title = "Waterfall Cloudwalk - Cronograma de Amortizacoes"
    draw.text((margin_left, 30), title, fill="#1F1F1F", font=font)

    if not rows:
        message = "Nenhum FIDC Cloudwalk incluido: cronogramas senior insuficientes ou ambiguos."
        draw.text((margin_left, height // 2), message, fill="#1F1F1F", font=font)
        image.save(plot_path)
        return

    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    x0, y0 = margin_left, margin_top + plot_height
    draw.line((x0, margin_top, x0, y0), fill="#6B6B6B", width=1)
    draw.line((x0, y0, width - margin_right, y0), fill="#6B6B6B", width=1)

    saldo = [row.saldo_devedor_total / 1_000_000.0 for row in rows]
    posicao = [row.posicao_liquida / 1_000_000.0 for row in rows]
    amort = [row.amortizacao_total / 1_000_000.0 for row in rows]
    y_min = min([0.0, *posicao])
    y_max = max([1.0, *saldo, *amort])
    if abs(y_max - y_min) <= 1e-9:
        y_max = y_min + 1.0

    def x_at(index: int) -> float:
        if len(rows) == 1:
            return x0 + plot_width / 2
        return x0 + (plot_width * index / (len(rows) - 1))

    def y_at(value: float) -> float:
        return margin_top + plot_height - ((value - y_min) / (y_max - y_min) * plot_height)

    zero_y = y_at(0.0)
    draw.line((x0, zero_y, width - margin_right, zero_y), fill="#E5E5E5", width=1)
    bar_width = max(8, min(36, int(plot_width / max(len(rows), 1) * 0.45)))
    for index, value in enumerate(amort):
        x = x_at(index)
        draw.rectangle((x - bar_width / 2, y_at(value), x + bar_width / 2, zero_y), fill="#EC7000")

    saldo_points = [(x_at(index), y_at(value)) for index, value in enumerate(saldo)]
    posicao_points = [(x_at(index), y_at(value)) for index, value in enumerate(posicao)]
    if len(saldo_points) == 1:
        x, y = saldo_points[0]
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill="#1F1F1F")
    else:
        draw.line(saldo_points, fill="#1F1F1F", width=3)
        draw.line(posicao_points, fill="#6B6B6B", width=2)

    draw.text((margin_left, height - 48), "Preto: saldo devedor | Laranja: amortizacao | Cinza: posicao liquida", fill="#6B6B6B", font=font)
    draw.text((margin_left, height - 28), "Eixo Y em R$ milhoes", fill="#6B6B6B", font=font)
    image.save(plot_path)


def _receivables_by_date(recebiveis_por_bucket: dict[str, float], reference_date: date) -> dict[date, float]:
    bucket_days = {
        "0_30d": 30,
        "0-30d": 30,
        "31_60d": 60,
        "31-60d": 60,
        "61_90d": 90,
        "61-90d": 90,
        "91_180d": 180,
        "91-180d": 180,
        "181_360d": 360,
        "181-360d": 360,
        "acima_360d": 720,
        "acima-360d": 720,
    }
    output: dict[date, float] = {}
    for key, value in recebiveis_por_bucket.items():
        days = bucket_days.get(str(key))
        if days is None:
            continue
        numeric = float(value or 0.0)
        if abs(numeric) <= 1e-9:
            continue
        output[reference_date + timedelta(days=days)] = output.get(reference_date + timedelta(days=days), 0.0) + numeric
    return output


def _excluded_schedule(
    fund_name: str,
    cnpj: str,
    classe: str,
    reason: str,
    *,
    volume_emitido: float = 0.0,
) -> FidcAmortizationSchedule:
    return FidcAmortizationSchedule(
        fund_name=fund_name,
        cnpj=cnpj,
        classe=classe,
        volume_emitido=volume_emitido,
        saldo_atual=0.0,
        convention="",
        schedule=[],
        included=False,
        exclusion_reason=reason,
    )


def _is_senior(classe: str, tipo: str) -> bool:
    text = normalize_text(f"{classe} {tipo}")
    return "senior" in text


def _normalize_year(year: int) -> int:
    if year < 100:
        return 2000 + year
    return year


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
