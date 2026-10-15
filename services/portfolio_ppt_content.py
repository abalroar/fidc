"""Plan the portfolio PowerPoint from existing analytical results.

This module selects presentation forms and retains the selected source tables.
It does not recalculate portfolio metrics, consolidate funds, or adjudicate
documentary discrepancies. Renderers own pagination, geometry and typography.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
import json
import math
import re
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from services.fund_name_display import short_fund_name
from services.fund_return_disclosures import CVM_RETURN_REINVESTMENT_NOTE
from services.fund_return_matrix import (
    RETURN_SERIES_COLUMN,
    RETURN_TRAILING_12M_CDI_COLUMN,
    RETURN_TRAILING_12M_COLUMN,
    RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN,
    RETURN_YTD_COLUMN,
    build_fund_return_matrix,
)
from services.presentation_text import document_comparison_value, public_document_text
from services.fundonet_ppt_export import _format_brl_compact


@dataclass(frozen=True)
class TableBlock:
    title: str
    frame: pd.DataFrame
    formats: dict[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    numeric_columns: tuple[str, ...] = ()
    cell_colors: dict[tuple[int, str], str] = field(default_factory=dict)
    compact: bool = False
    # The position summary: preformatted values, never pruned or split.
    snapshot: bool = False
    # Index labels of rows that name a group (theme) of the rows below them.
    section_rows: tuple[Any, ...] = ()


@dataclass(frozen=True)
class ChartSeries:
    key: str
    label: str
    values: tuple[float | None, ...]
    unit: str = "%"
    decimals: int = 1
    # A reference (e.g. 100% parity) is drawn but never makes a chart worth
    # showing on its own, and carries no end label.
    reference: bool = False


@dataclass(frozen=True)
class ChartBlock:
    title: str
    categories: tuple[str, ...]
    series: tuple[ChartSeries, ...]
    unit: str = "%"
    notes: tuple[str, ...] = ()
    # "line"; "column" (one series: history in grey, latest in orange;
    # several: side by side); "stacked" (parts of a whole, with the total);
    # "bar" (horizontal, one category per series).
    kind: str = "line"
    # Values the axis must also span: small multiples share one scale.
    axis_range: tuple[float, ...] = ()


@dataclass(frozen=True)
class TextBlock:
    title: str
    text: str


@dataclass(frozen=True)
class SlideSpec:
    title: str
    context: str
    blocks: tuple[TableBlock | ChartBlock | TextBlock, ...]
    source: str = ""
    notes: tuple[str, ...] = ()
    kind: str = "content"
    # ``panels`` puts up to two blocks side by side with a shared plot height;
    # ``flow`` stacks tables and texts and paginates them.
    layout: str = "flow"
    # Divider label of the deck section this slide belongs to.
    section: str = ""


@dataclass(frozen=True)
class DeckSpec:
    title: str
    context: str
    metadata: tuple[str, ...]
    slides: tuple[SlideSpec, ...]


_MONTHS = ("", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
_SOURCE = "CVM / Fundos.NET · Informe mensal"
_ALIASES = {
    "pl_total": "PL total", "pl_senior": "PL sênior",
    "pl_subordinada_strict": "PL subordinado", "pl_mezzanino": "PL mezanino",
    "pl_subordinada_mezz_ex360": "PL subordinado + mezanino ex-360",
    "carteira_bruta": "Carteira bruta", "carteira_ex360": "Carteira bruta ex-360",
    "carteira_a_vencer": "Carteira a vencer", "pdd_total": "PDD total", "pdd_ex360": "PDD ex-360",
    "subordinacao_total_pct": "Subordinação total", "subordinacao_total_ex360_pct": "Subordinação ex-360",
    "npl_over1_ex360_pct": "NPL > 1d ex-360", "npl_over30_ex360_pct": "NPL > 30d ex-360",
    "npl_over60_ex360_pct": "NPL > 60d ex-360", "npl_over90_ex360_pct": "NPL > 90d ex-360",
    "pdd_npl_over90_ex360_pct": "Cobertura PDD / NPL > 90d ex-360",
    "pdd_npl90_ex360_pct": "Cobertura PDD / NPL > 90d ex-360",
    "npl_1_90_pct": "NPL 1–90d / carteira ex-360", "npl_91_360_pct": "NPL 91–360d / carteira ex-360",
    "npl_1_360_pct": "NPL 1–360d / carteira ex-360", "npl_1_90": "NPL 1–90d",
    "npl_91_360": "NPL 91–360d", "npl_1_360": "NPL 1–360d", "npl_over360": "NPL > 360d",
    "carteira_ex360_mom_pct": "Carteira ex-360 · variação mensal",
    "carteira_ex360_yoy_pct": "Carteira ex-360 · variação anual",
    "roll_61_90_m3_pct": "Roll 61–90 / a vencer M-3", "roll_91_120_m4_pct": "Roll 91–120 / a vencer M-4",
    "roll_121_150_m5_pct": "Roll 121–150 / a vencer M-5", "roll_151_180_m6_pct": "Roll 151–180 / a vencer M-6",
    "duration_months": "Duration estimada (meses)", "duration_days": "Duration estimada (dias)",
    "ativos_totais": "Ativo total", "direitos_creditorios": "Direitos creditórios",
    "inadimplencia_total": "Vencidos", "inadimplencia_pct": "Inadimplência / direitos creditórios",
    "provisao": "Provisão", "provisao_pct_direitos": "Provisão / direitos creditórios",
    "cobertura_pct": "Cobertura provisão / vencidos", "subordinacao_pct": "Subordinação reportada",
    "atraso_ate30": "Até 30 dias", "atraso_31_60": "31–60 dias", "atraso_61_90": "61–90 dias",
    "atraso_91_120": "91–120 dias", "atraso_121_150": "121–150 dias", "atraso_151_180": "151–180 dias",
    "atraso_181_360": "181–360 dias", "atraso_361_720": "361–720 dias", "atraso_721_1080": "721–1080 dias",
    "atraso_1080": "Acima de 1080 dias", "valor": "Saldo", "percentual": "Percentual",
    "percentual_inadimplencia": "Composição dos vencidos", "provisao_total": "Provisão total",
    "pl": "PL por cota", "pl_share_pct": "Participação da cota no PL",
    "npl_over90_ex360": "NPL > 90d ex-360 (saldo)", "npl_over90": "NPL > 90d (saldo)",
}
_MONTHLY_COLUMNS = (
    "pl_total", "pl_senior", "pl_subordinada_strict", "pl_mezzanino", "pl_subordinada_mezz_ex360",
    "carteira_bruta", "carteira_ex360", "carteira_a_vencer", "pdd_total", "pdd_ex360",
    "subordinacao_total_pct", "subordinacao_total_ex360_pct", "npl_1_90", "npl_91_360", "npl_1_360",
    "npl_over360", "npl_over90_ex360", "npl_over1_ex360_pct", "npl_over30_ex360_pct",
    "npl_over60_ex360_pct", "npl_over90_ex360_pct", "npl_1_90_pct", "npl_91_360_pct",
    "npl_1_360_pct", "pdd_npl_over90_ex360_pct", "pdd_npl90_ex360_pct",
    "carteira_ex360_mom_pct", "carteira_ex360_yoy_pct", "duration_months", "duration_days",
    "roll_61_90_m3_pct", "roll_91_120_m4_pct", "roll_121_150_m5_pct", "roll_151_180_m6_pct",
    "atraso_ate30", "atraso_31_60", "atraso_61_90", "atraso_91_120", "atraso_121_150",
    "atraso_151_180", "atraso_181_360", "atraso_361_720", "atraso_721_1080", "atraso_1080",
)
_ROLL_COLUMNS = ("roll_61_90_m3_pct", "roll_91_120_m4_pct", "roll_121_150_m5_pct", "roll_151_180_m6_pct")
_DASHBOARD_ANNEXES = (
    ("Estrutura de cotas", "quota_pl_history_df"),
    ("Subordinação reportada", "subordination_history_df"),
    ("Atraso e provisão", "default_history_df"),
    ("Aging · saldos", "default_buckets_history_df"),
    ("Aging · composição", "default_aging_history_df"),
    ("Atraso acumulado", "default_over_history_df"),
)
_DASHBOARD_DISPLAY_COLUMNS = {
    "quota_pl_history_df": ("pl", "pl_share_pct", "valor"),
    "subordination_history_df": ("subordinacao_pct",),
    "default_history_df": ("inadimplencia_total", "provisao_total", "inadimplencia_pct", "provisao_pct_direitos", "cobertura_pct"),
    "default_buckets_history_df": ("valor",),
    "default_aging_history_df": ("percentual_inadimplencia",),
    "default_over_history_df": ("percentual",),
}


def _frame(value: Any) -> pd.DataFrame:
    return value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if not isinstance(value, str):
        return False
    text = value.strip().casefold()
    # Curated absence often carries its reason ("N/D — texto extraído sem
    # associação confiável", "Não localizado nas cláusulas revisadas"); it is
    # still absence, and the reason stays in the notes.
    return text in {"", "-", "—", "n/d", "nan", "none"} or text.startswith(("não localizado", "não informado", "n/d —", "n/d -"))


def _text(value: Any) -> str:
    return "N/D" if _is_missing(value) else str(value)


def _br(value: Any, decimals: int = 1) -> str:
    number = _number(value)
    if number is None:
        return "N/D"
    if round(number, decimals) == 0:
        number = 0.0  # never "-0,0"
    return f"{number:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _date(value: Any) -> pd.Timestamp | None:
    if _is_missing(value):
        return None
    text = str(value)
    parsed = pd.to_datetime("01/" + text, dayfirst=True, errors="coerce") if len(text) == 7 and text[2:3] == "/" else pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed


def _month(value: Any) -> str:
    parsed = _date(value)
    return f"{_MONTHS[parsed.month]}/{parsed.year % 100:02d}" if parsed is not None else _text(value)


def _ordered(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    column = "competencia_dt" if "competencia_dt" in frame else "competencia" if "competencia" in frame else None
    if column is None:
        return frame.copy()
    out = frame.copy()
    out["__sort"] = out[column].map(_date)
    return out.sort_values("__sort", kind="stable", na_position="last").drop(columns="__sort").reset_index(drop=True)


def _period(frame: pd.DataFrame) -> str:
    ordered = _ordered(frame)
    column = "competencia" if "competencia" in ordered else "competencia_dt" if "competencia_dt" in ordered else None
    if column is None or ordered.empty:
        return "período N/D"
    first, last = _month(ordered.iloc[0][column]), _month(ordered.iloc[-1][column])
    return first if first == last else f"{first}–{last}"


def _unit(column: str) -> str:
    if column.endswith("_pct") or "_pct_" in column or column.startswith("percentual") or column in {"retorno_mensal_pct", "retorno_ano_pct", "retorno_12m_pct", "valor_pct", "value_pct"}:
        return "%"
    if "duration" in column:
        return "dias" if "days" in column or "dias" in column else "meses"
    if column.endswith("_pp") or "folga" in column:
        return "p.p."
    return "R$"


def _formats(frame: pd.DataFrame) -> dict[str, str]:
    formats = {}
    for column in frame:
        if pd.api.types.is_numeric_dtype(frame[column]) and not pd.api.types.is_bool_dtype(frame[column]):
            unit = _unit(str(column))
            is_money = (str(column) == "pl" or str(column).startswith(("pl_", "atraso_", "carteira", "pdd_", "npl_", "prazo_", "vl_"))) and unit == "R$"
            formats[str(column)] = "percent:2" if unit == "%" else "money:2" if is_money else "number:2"
    return formats


def _native_table(title: str, frame: pd.DataFrame, *, notes: Iterable[str] = ()) -> TableBlock:
    source = _frame(frame)
    if "competencia" in source:
        source["competencia"] = source["competencia"].map(_month)
    # Date columns duplicate a human-readable competence; their exact originals
    # stay in the block notes for inspection without adding redundant ink.
    if "competencia_dt" in source and "competencia" in source:
        source = source.drop(columns="competencia_dt")
    return TableBlock(title, source, _formats(source), (*tuple(notes), _raw_note(frame)), tuple(c for c in source if c in _formats(source)))


def _raw_note(frame: pd.DataFrame) -> str:
    """Keep source precision and state independently of the visible formatter."""
    records = []
    for _, row in frame.iterrows():
        record = {}
        for column, value in row.items():
            if _is_missing(value) and not isinstance(value, str):
                value = None
            elif hasattr(value, "item"):
                value = value.item()
            if isinstance(value, float) and not math.isfinite(value):
                value = None
            record[str(column)] = value
        records.append(record)
    return "Valores originais, precisão e estados: " + json.dumps(records, ensure_ascii=False, default=str, allow_nan=False)


def _history_tables(title: str, frame: pd.DataFrame) -> list[TableBlock]:
    """Represent long monthly source records as dense identity × month tables.

    Only a reshape occurs. Exact source identities, column names, and textual
    qualifications stay in notes; changing qualifications have their own matrix.
    """
    source = _ordered(frame)
    if source.empty or "competencia" not in source:
        return [_native_table(title, source)] if not source.empty else []
    identity_columns = [column for column in ("scope", "cnpj", "metric_id", "class_key", "faixa", "serie") if column in source]
    # The strongest cota identity is used; labels remain in its row caption and
    # notes, so two cotas with equal names never share a row implicitly.
    if "class_key" not in identity_columns:
        identity_columns.extend(column for column in ("class_label", "classe", "class_name") if column in source)
    numeric = [column for column in source if pd.api.types.is_numeric_dtype(source[column]) and not pd.api.types.is_bool_dtype(source[column]) and column not in {"year", "month", "schema_version", "classe_ordem", "class_order", "ordem", "line_rank"}]
    metadata = [column for column in source if column not in {*identity_columns, *numeric, "competencia", "competencia_dt"}]
    groups = source.groupby(identity_columns, sort=False, dropna=False) if identity_columns else [((), source)]
    grouped_rows: dict[str, list[dict[str, Any]]] = {}
    note_lines = [f"Origem: {title}; nomes canônicos e qualificações preservados.", _raw_note(frame)]
    all_months: list[str] = []
    for identity, segment in groups:
        if not isinstance(identity, tuple):
            identity = (identity,)
        label_parts = [_text(value) for value in identity if not _is_missing(value)]
        if "class_label" in segment:
            labels = segment["class_label"].dropna().astype(str).drop_duplicates().tolist()
            label_parts = [*labels, *label_parts]
        label = " · ".join(dict.fromkeys(label_parts))
        labels = segment["competencia"].map(_month).tolist()
        if len(labels) != len(set(labels)):
            # Unknown source multiplicity: keep the original records verbatim.
            return [_native_table(title, source)]
        for month in labels:
            if month not in all_months:
                all_months.append(month)
        for column in numeric:
            unit = _unit(str(column))
            indicator = " · ".join(part for part in (label, _ALIASES.get(str(column), str(column))) if part)
            grouped_rows.setdefault(unit, []).append({"Indicador": indicator, **dict(zip(labels, segment[column].tolist(), strict=True))})
        for column in metadata:
            values = segment[column].map(_text)
            unique = values.drop_duplicates().tolist()
            if len(unique) <= 1:
                note_lines.append(f"{label + ' · ' if label else ''}{column}: {unique[0] if unique else 'N/D'}")
            else:
                grouped_rows.setdefault("texto", []).append({"Indicador": " · ".join(part for part in (label, str(column)) if part), **dict(zip(labels, values.tolist(), strict=True))})
    output = []
    # Chronological order comes from the original already sorted source records.
    for unit, rows in grouped_rows.items():
        view = pd.DataFrame(rows).reindex(columns=["Indicador", *all_months])
        token = "percent:2" if unit == "%" else "money_value:2" if unit == "R$" else "text" if unit == "texto" else "number:2"
        unit_title = "R$ milhões" if unit == "R$" else unit
        output.append(TableBlock(f"{title} · {unit_title}", view, {month: token for month in all_months}, tuple(dict.fromkeys(note_lines)), tuple(all_months)))
    return output or [_native_table(title, source)]


def _quality_block(frame: pd.DataFrame, origin: str) -> TableBlock | None:
    source = _ordered(frame)
    state_columns = [column for column in source if any(token in str(column).lower() for token in ("status", "quality", "coverage", "missing", "fonte", "source")) and not pd.api.types.is_numeric_dtype(source[column])]
    if source.empty or not state_columns:
        return None
    time_column = "competencia" if "competencia" in source else "competencia_dt" if "competencia_dt" in source else None
    labels = [_month(value) for value in source[time_column]] if time_column else [str(index + 1) for index in range(len(source))]
    meanings = {"reported_zero": "Zero informado", "not_reported": "Não reportado", "missing_field": "Campo ausente", "reported": "Informado", "reported_value": "Valor informado", "ok": "Válido", "calculated": "Calculado", "calculado": "Calculado", "missing": "Ausente", "partial": "Cobertura parcial", "incomplete": "Incompleto",
                "sem_dados": "Sem dados", "nao_calculavel_bucket_aberto_dominante": "Não calculável: faixa aberta dominante",
                "soma_classes_cotas": "Soma das classes de cotas", "PATRLIQ/VL_PATRIM_LIQ": "PL do informe"}
    state_labels = {"pl_total_usado": "PL total · fonte usada", "pl_total_oficial": "PL total oficial", "duration": "Duration"}

    def readable_state(value: str) -> str:
        # Unknown codes still read as words, never as snake_case.
        return meanings.get(value) or (value.replace("_", " ").capitalize() if re.fullmatch(r"[a-z0-9_]+", value) else value)
    rows, notes = [], []
    for column in state_columns:
        label = str(column)
        for suffix in ("_source_status", "_status", "_data_quality", "_quality", "_source", "_fonte"):
            if label.endswith(suffix):
                label = label[: -len(suffix)]
        label = state_labels.get(label) or _ALIASES.get(label, label.replace("_", " ").capitalize())
        values = source[column].map(_text).tolist()
        readable = [readable_state(value) for value in values]
        # Repeating the same status in every month adds no information. Its
        # exact per-month association stays in notes and in the source record.
        if len(set(values)) > 1:
            rows.append({"Indicador": label, "Estado por competência": _state_runs(labels, readable)})
        notes.append(f"{origin} · {column}: " + "; ".join(f"{month}={value}" for month, value in zip(labels, values, strict=True)))
    if not rows:
        return None
    return TableBlock(f"Qualidade e cobertura · {origin}", pd.DataFrame(rows), notes=tuple(notes))


def _state_runs(labels: list[str], states: list[str]) -> str:
    """'Válido: nov/25–set/26; Sem dados: set/25–out/25' instead of one
    text column per month, which a slide can only show in fragments."""
    runs: list[list[Any]] = []
    for label, state in zip(labels, states, strict=True):
        if runs and runs[-1][0] == state:
            runs[-1][2] = label
        else:
            runs.append([state, label, label])
    by_state: dict[str, list[str]] = {}
    for state, first, last in runs:
        by_state.setdefault(state, []).append(first if first == last else f"{first}–{last}")
    return "; ".join(f"{state}: {', '.join(spans)}" for state, spans in by_state.items())


def _roll_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    source = _frame(frame)
    if source.empty or not {"metric_name", "value_pct", "month"}.issubset(source.columns):
        return pd.DataFrame()
    identifiers = [column for column in ("scope", "fund_name", "cnpj", "metric_name", "year") if column in source]
    if source.duplicated([*identifiers, "month"]).any():
        return source[[*identifiers, "month", "value_pct"]]
    view = source.pivot(index=identifiers, columns="month", values="value_pct").reset_index()
    single_scope = source["cnpj"].astype(str).nunique() <= 1 if "cnpj" in source else source.get("fund_name", pd.Series(dtype="object")).astype(str).nunique() <= 1
    labels = []
    for _, row in view.iterrows():
        parts = []
        if not single_scope:
            parts.append("Consolidado" if str(row.get("scope")) == "consolidado" else short_fund_name(str(row.get("fund_name") or row.get("cnpj") or "FIDC")))
        parts.extend(str(row[column]) for column in ("metric_name", "year") if column in row)
        labels.append(" · ".join(parts))
    output = pd.DataFrame({"Série": labels})
    for column in view:
        if column not in identifiers:
            output[_MONTHS[int(column)] if _number(column) is not None and 1 <= int(column) <= 12 else str(column)] = view[column]
    return output


def _monthly_tables(title: str, frame: pd.DataFrame, columns: Iterable[str], *, notes: Iterable[str] = ()) -> list[TableBlock]:
    ordered = _ordered(frame)
    available = [column for column in dict.fromkeys(columns) if column in ordered]
    if ordered.empty or not available:
        return []
    time_column = "competencia" if "competencia" in ordered else "competencia_dt" if "competencia_dt" in ordered else None
    if time_column is None:
        return [_native_table(title, ordered[available], notes=notes)]
    labels = [_month(value) for value in ordered[time_column]]
    # Repeated dates are source records, and must not be aggregated silently.
    if len(labels) != len(set(labels)):
        return [_native_table(title, ordered[[time_column, *available]], notes=notes)]
    output = []
    for unit in dict.fromkeys(_unit(column) for column in available):
        selected = [column for column in available if _unit(column) == unit]
        rows = [{"Indicador": _ALIASES.get(column, column), **dict(zip(labels, ordered[column].tolist(), strict=True))} for column in selected]
        view = pd.DataFrame(rows)
        token = "percent:2" if unit == "%" else "money_value:2" if unit == "R$" else "number:2"
        unit_title = "R$ milhões" if unit == "R$" else unit
        output.append(TableBlock(
            f"{title} · {unit_title}", view, {column: token for column in labels},
            tuple(notes) + tuple(f"{_ALIASES.get(column, column)}: {column}" for column in selected) + (_raw_note(ordered[[time_column, *selected]]),), tuple(labels),
        ))
    return output


def _chart(title: str, frame: pd.DataFrame, columns: Iterable[str], *, key_prefix: str, unit: str = "%", notes: Iterable[str] = ()) -> ChartBlock | TextBlock | None:
    ordered = _ordered(frame)
    if ordered.empty:
        return None
    names = [column for column in columns if column in ordered]
    if not names:
        return None
    time_column = "competencia" if "competencia" in ordered else "competencia_dt" if "competencia_dt" in ordered else None
    categories = tuple(_month(v) for v in ordered[time_column]) if time_column else tuple(str(i + 1) for i in range(len(ordered)))
    series = []
    for column in names:
        raw = tuple(_number(value) for value in ordered[column])
        label = _ALIASES.get(column, column)
        values = tuple(value / 1_000_000 if value is not None and unit == "R$" else value for value in raw)
        series.append(ChartSeries(f"{key_prefix}:{column}", label, values, "R$ mm" if unit == "R$" else unit))
    # The native renderer turns constant/missing series into visible sentences
    # beside variable lines. Their monthly values remain in appendix tables.
    return ChartBlock(title, categories, tuple(series), "R$ mm" if unit == "R$" else unit, tuple(notes))


def _varies(frame: pd.DataFrame, columns: Iterable[str]) -> bool:
    for column in columns:
        if column not in frame:
            continue
        values = [number for value in frame[column] if (number := _number(value)) is not None]
        if len(values) > 1 and max(values) - min(values) > max(1.0, max(abs(value) for value in values)) * 1e-12:
            return True
    return False


def _fund_identity(fund: Any) -> tuple[str, str]:
    if isinstance(fund, Mapping):
        return str(fund.get("cnpj") or ""), str(fund.get("display_name") or fund.get("name") or fund.get("short_name") or fund.get("cnpj") or "FIDC")
    return str(getattr(fund, "cnpj", "")), str(getattr(fund, "display_name", None) or getattr(fund, "name", None) or getattr(fund, "cnpj", "FIDC"))


def _digits(value: Any) -> str:
    return "".join(char for char in str(value) if char.isdigit())


def _reference_label(source: str) -> str:
    urls = tuple(dict.fromkeys(value.rstrip(".,)") for value in re.findall(r"https?://[^\s;|]+", source)))
    ids = tuple(dict.fromkeys(re.findall(r"(?i)\b(?:ID|documento|CVM)\s*[:#]?\s*(?:n[º°.]?\s*)?\d[\w./-]*", source)))
    if urls or ids:
        return "; ".join((*ids, *urls))
    return source if len(source) <= 240 else "Fontes por célula nas notas da matriz documental no anexo."


def _document_blocks(title: str, frame: pd.DataFrame, *, notes: Iterable[str] = (),
                     entity: str = "", formats: dict[str, str] | None = None,
                     numeric_columns: tuple[str, ...] = ()) -> tuple[TableBlock | TextBlock, ...]:
    """Keep documentary absence as an identified sentence, including in annexes."""
    original = _frame(frame)
    if original.empty or not len(original.columns):
        return ()
    visible = original.copy()
    for column in visible.columns[1:]:
        visible[column] = visible[column].map(lambda value: "Não localizado" if _is_missing(value) else value)
    missing_columns = [column for column in visible.columns[1:] if visible[column].map(_is_missing).all()]
    all_missing_rows = visible.iloc[:, 1:].apply(lambda column: column.map(_is_missing)).all(axis=1)
    absent_criteria = original.loc[all_missing_rows].iloc[:, 0].map(str).tolist()
    kept = visible.loc[~all_missing_rows].drop(columns=missing_columns)
    qualified_notes = (*tuple(notes), _raw_note(original))
    blocks: list[TableBlock | TextBlock] = []
    if not kept.empty and len(kept.columns) > 1:
        blocks.append(TableBlock(title, kept, formats or {}, qualified_notes,
                                 tuple(column for column in numeric_columns if column in kept)))
    missing_sentences = []
    if absent_criteria:
        names = entity or "; ".join(map(str, original.columns[1:])) or "entidade indicada"
        missing_sentences.append(f"Não localizados para {names}: " + "; ".join(absent_criteria) + ".")
    if missing_columns and not kept.empty:
        names = entity or "; ".join(map(str, missing_columns))
        remaining_criteria = original.loc[~all_missing_rows].iloc[:, 0].map(str).tolist()
        missing_sentences.append(f"Não localizados para {names}: " + "; ".join(remaining_criteria) + ".")
    if missing_sentences:
        blocks.append(TextBlock("Campos documentais", " ".join(missing_sentences)))
    return tuple(blocks)


def _with_sections(blocks: list[Any]) -> list[Any]:
    """Documentary matrices with the same columns become one table: each
    theme is a sub-header row instead of a title, a header and a gap."""
    out: list[Any] = []
    for block in blocks:
        previous = out[-1] if out else None
        if not isinstance(block, TableBlock):
            out.append(block)
            continue
        heading = pd.DataFrame([{column: (block.title if index == 0 else "") for index, column in enumerate(block.frame.columns)}])
        if isinstance(previous, TableBlock) and previous.section_rows and list(previous.frame.columns) == list(block.frame.columns):
            frame = pd.concat([previous.frame, heading, block.frame], ignore_index=True)
            sections = (*previous.section_rows, len(previous.frame))
            out[-1] = replace(previous, frame=frame.astype(object), section_rows=sections,
                              notes=tuple(dict.fromkeys((*previous.notes, *block.notes))))
        else:
            frame = pd.concat([heading, block.frame], ignore_index=True)
            out.append(replace(block, title="Documentos", frame=frame.astype(object), section_rows=(0,)))
    return out


def _lookup(mapping: Any, cnpj: str) -> Any:
    if not isinstance(mapping, Mapping):
        return None
    if cnpj in mapping:
        return mapping[cnpj]
    return next((value for key, value in mapping.items() if _digits(key) == _digits(cnpj)), None)


def _scope_frames(funds: tuple[Any, ...], outputs: Any, monitor_outputs: Any) -> list[tuple[str, str, pd.DataFrame, pd.DataFrame, pd.DataFrame]]:
    fund_monthly = getattr(outputs, "fund_monthly", {}) or {}
    identities = [_fund_identity(fund) for fund in funds]
    known = {_digits(cnpj) for cnpj, _ in identities}
    identities.extend((str(cnpj), str(frame.iloc[0].get("fund_name") or cnpj) if isinstance(frame, pd.DataFrame) and not frame.empty else str(cnpj)) for cnpj, frame in fund_monthly.items() if _digits(cnpj) not in known)
    scopes = []
    if len(identities) > 1:
        scopes.append(("consolidado", "Consolidado", _frame(getattr(outputs, "consolidated_monthly", None)), _frame(getattr(monitor_outputs, "consolidated_monitor", None)), _frame(getattr(monitor_outputs, "consolidated_cohorts", None))))
    for cnpj, name in identities:
        monthly = _frame(_lookup(fund_monthly, cnpj))
        monitor = _frame(_lookup(getattr(monitor_outputs, "fund_monitor", {}), cnpj))
        cohorts = _frame(_lookup(getattr(monitor_outputs, "fund_cohorts", {}), cnpj))
        if len(identities) == 1:
            # Older fixtures may carry only the consolidated representation.
            if monthly.empty:
                monthly = _frame(getattr(outputs, "consolidated_monthly", None))
            if monitor.empty:
                monitor = _frame(getattr(monitor_outputs, "consolidated_monitor", None))
            if cohorts.empty:
                cohorts = _frame(getattr(monitor_outputs, "consolidated_cohorts", None))
        display_name = short_fund_name(name) or name
        if any(existing[1] == display_name for existing in scopes):
            display_name += f" · {cnpj}"
        scopes.append((cnpj, display_name, monthly, monitor, cohorts))
    if not scopes:
        scopes.append(("consolidado", "Consolidado", _frame(getattr(outputs, "consolidated_monthly", None)), _frame(getattr(monitor_outputs, "consolidated_monitor", None)), _frame(getattr(monitor_outputs, "consolidated_cohorts", None))))
    return scopes


def _snapshot(scopes: list[tuple[str, str, pd.DataFrame, pd.DataFrame, pd.DataFrame]], dashboard: Any,
              summary_competencia: str | None = None) -> TableBlock:
    from services.somatorio_fidcs_ppt_export import _latest_delta

    _, name, monthly, monitor, _ = scopes[0]
    base, credit = _ordered(monthly), _ordered(monitor)
    rows, colors, notes = [], {}, []
    specs = (("pl_total", "PL total", "R$", "neutral"), ("carteira_ex360", "Carteira bruta ex-360", "R$", "neutral"),
             ("subordinacao_total_ex360_pct", "Subordinação ex-360", "%", "higher"),
             ("npl_over1_ex360_pct", "NPL > 1d ex-360", "%", "lower"),
             ("npl_over90_ex360_pct", "NPL > 90d ex-360", "%", "lower"),
             ("pdd_npl_over90_ex360_pct", "Cobertura PDD / NPL > 90d", "%", "higher"),
             ("duration_months", "Duration estimada", "meses", "neutral"))
    for column, label, unit, polarity in specs:
        source = credit if column in credit else base
        if source.empty or column not in source:
            continue
        value = _number(source.iloc[-1][column])
        display = _format_brl_compact(value) if unit == "R$" else _br(value, 1) + ("%" if unit == "%" and value is not None else f" {unit}" if value is not None else "")
        not_applicable = False
        if column == "pdd_npl_over90_ex360_pct" and value is None:
            denominator_source = credit if "npl_over90_ex360" in credit else base
            denominator = _number(denominator_source.iloc[-1].get("npl_over90_ex360")) if not denominator_source.empty else None
            # The same zero-denominator presentation condition used by the
            # existing portfolio producer. No ratio is recomputed here.
            if denominator == 0:
                not_applicable = True
                display = "N/A · NPL zero"
        delta, annual = None, None
        monthly_display = annual_display = "N/D"
        if column == "carteira_ex360" and not credit.empty:
            delta = _number(credit.iloc[-1].get("carteira_ex360_mom_pct"))
            annual = _number(credit.iloc[-1].get("carteira_ex360_yoy_pct"))
            monthly_display = _br(delta, 1) + "%" if delta is not None else "N/D"
            annual_display = _br(annual, 1) + "%" if annual is not None else "N/D"
        elif unit == "%" and value is not None:
            # Same existing presentation comparison helper as the live credit
            # view; it is a change in percentage points, not a new risk metric.
            delta = _latest_delta(source, column)
            monthly_display = _br(delta, 1) + " p.p." if delta is not None else "N/D"
        row_index = len(rows)
        rows.append({"Indicador": label, "Valor": display, "Var. mensal": monthly_display, "Var. anual": annual_display})
        if delta is not None and round(delta, 1) != 0 and polarity != "neutral":
            favorable = delta > 0 if polarity == "higher" else delta < 0
            colors[(row_index, "Var. mensal")] = "good" if favorable else "bad"
        notes.append(f"{label}: posição {_month(source.iloc[-1].get('competencia', source.iloc[-1].get('competencia_dt')))}; fonte {column}.")
        if not_applicable:
            notes.append("Cobertura PDD / NPL > 90d ex-360: não aplicável; NPL é zero na posição. N/A é distinto de dado não reportado (N/D).")
    summary = getattr(dashboard, "summary", {}) or {}
    defaults = _ordered(_frame(getattr(dashboard, "default_history_df", None)))
    if "cobertura_pct" in summary:
        summary_cut = _month(summary_competencia or getattr(dashboard, "latest_competencia", None))
        history_cut = _month(defaults.iloc[-1].get("competencia", defaults.iloc[-1].get("competencia_dt"))) if not defaults.empty else "N/D"
        same_cut = summary_cut != "N/D" and summary_cut == history_cut
        label = "Cobertura provisão / vencidos · IME" + (f" (posição {summary_cut})" if not same_cut else "")
        value = _number(summary["cobertura_pct"])
        delta = _latest_delta(defaults, "cobertura_pct") if value is not None and same_cut else None
        row_index = len(rows)
        rows.append({"Indicador": label, "Valor": _br(value, 1) + ("%" if value is not None else ""), "Var. mensal": _br(delta, 1) + " p.p." if delta is not None else "N/D", "Var. anual": "N/D"})
        if delta is not None and round(delta, 1) != 0:
            colors[(row_index, "Var. mensal")] = "good" if delta > 0 else "bad"
        notes.append(f"Cobertura IME: posição original {summary_cut}; histórico selecionado termina em {history_cut}; provisão / vencidos; denominador diferente do NPL ex-360.")
        if not same_cut:
            notes.append("Posição do resumo e último ponto histórico diferentes: comparação mensal indisponível (N/D), sem combinar cortes. A série histórica selecionada permanece completa no anexo.")
    notes.append("Variações anuais só aparecem quando já fornecidas pela base. N/D significa comparação indisponível. Mudanças de percentuais são p.p.; crescimento de carteira usa a variação já calculada.")
    frame = pd.DataFrame(rows, columns=["Indicador", "Valor", "Var. mensal", "Var. anual"])
    # A comparison column that is N/D in every row carries no information.
    empty = [column for column in ("Var. mensal", "Var. anual") if not frame.empty and frame[column].eq("N/D").all()]
    if empty:
        notes.append("Colunas sem comparação disponível em nenhuma linha omitidas: " + ", ".join(empty) + ".")
        frame = frame.drop(columns=empty)
    return TableBlock(name, frame, notes=tuple(notes), numeric_columns=tuple(c for c in ("Valor", "Var. mensal", "Var. anual") if c in frame), cell_colors=colors, snapshot=True)


def _fund_comparison(scopes: list[tuple[str, str, pd.DataFrame, pd.DataFrame, pd.DataFrame]]) -> TableBlock | None:
    """One row per fund, so the table grows downwards for any basket size
    and every fund shows its own position cut."""
    funds = [scope for scope in scopes if scope[0] != "consolidado"]
    if len(funds) < 2:
        return None
    specs = (("pl_total", "PL (R$ mm)"), ("carteira_ex360", "Carteira ex-360 (R$ mm)"),
             ("subordinacao_total_ex360_pct", "Subordinação ex-360 (%)"), ("npl_over90_ex360_pct", "NPL > 90d ex-360 (%)"),
             ("pdd_npl_over90_ex360_pct", "Cobertura PDD / NPL > 90d (%)"), ("duration_months", "Duration (meses)"))
    rows = []
    notes = []
    for cnpj, name, monthly, monitor, _ in funds:
        row = {"Fundo": name}
        positions = set()
        for column, label in specs:
            source = _ordered(monitor if column in monitor else monthly)
            value = _number(source.iloc[-1].get(column)) if not source.empty else None
            row[label] = _br(value / 1_000_000, 1) if value is not None and _unit(column) == "R$" else _br(value, 1)
            if column == "pdd_npl_over90_ex360_pct" and value is None:
                denominator_source = _ordered(monitor if "npl_over90_ex360" in monitor else monthly)
                denominator = _number(denominator_source.iloc[-1].get("npl_over90_ex360")) if not denominator_source.empty else None
                if denominator == 0:
                    row[label] = "N/A · NPL zero"
                    notes.append(f"{name} · CNPJ {cnpj}: cobertura PDD / NPL > 90d ex-360 não aplicável; NPL é zero na posição. N/D continua reservado ao dado indisponível.")
            if not source.empty:
                positions.add(_month(source.iloc[-1].get("competencia", source.iloc[-1].get("competencia_dt"))))
        row["Posição"] = " / ".join(sorted(positions, key=_month_key)) or "N/D"
        notes.append(f"{name} · CNPJ {cnpj}: posição {row['Posição']}.")
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame = frame[["Fundo", "Posição", *[label for _, label in specs]]]
    empty = [label for _, label in specs if frame[label].eq("N/D").all()]
    frame = frame.drop(columns=empty)
    return TableBlock("Comparação entre fundos", frame, numeric_columns=tuple(label for _, label in specs if label in frame),
                      notes=tuple(dict.fromkeys(notes)))


def _aging_matrix(frame: pd.DataFrame, value_column: str) -> pd.DataFrame:
    source = _ordered(frame)
    if source.empty or "competencia" not in source or "faixa" not in source or value_column not in source:
        return pd.DataFrame()
    if source.duplicated(["competencia", "faixa"]).any():
        return source[["competencia", "faixa", value_column]].copy()
    view = source.pivot(index="competencia", columns="faixa", values=value_column)
    view = view.reindex(source["competencia"].drop_duplicates().tolist())
    preferred = ("Até 30 dias", "31 a 60 dias", "61 a 90 dias", "91 a 120 dias", "121 a 150 dias", "151 a 180 dias", "181 a 360 dias", "361 a 720 dias", "721 a 1080 dias", "Acima de 1080 dias")
    view = view[[*[column for column in preferred if column in view], *[column for column in view if column not in preferred]]]
    view.index = view.index.map(_month)
    return view.T.rename_axis("Faixa").reset_index()


def _cohort_matrix(frame: pd.DataFrame, *, recent: bool) -> pd.DataFrame:
    source = _frame(frame)
    if source.empty:
        return pd.DataFrame()
    cohort = "cohort" if "cohort" in source else "series_name" if "series_name" in source else None
    cycle = "mes_ciclo" if "mes_ciclo" in source else "ordem" if "ordem" in source else None
    value = "valor_pct" if "valor_pct" in source else "value_pct" if "value_pct" in source else None
    if not all((cohort, cycle, value)):
        return source
    available = source[[cohort, "cohort_dt"]].drop_duplicates().sort_values("cohort_dt") if "cohort_dt" in source else source[[cohort]].drop_duplicates()
    if recent:
        source = source[source[cohort].isin(available[cohort].tail(6))]
    if source.duplicated([cohort, cycle]).any():
        return source
    pivot = source.pivot(index=cohort, columns=cycle, values=value)
    pivot = pivot.reindex([label for label in available[cohort] if label in pivot.index])
    if "cohort_dt" in available:
        names = {row[cohort]: _month(row["cohort_dt"]) for _, row in available.iterrows()}
        pivot.index = pivot.index.map(lambda label: names.get(label, str(label)))
    return pivot.rename_axis("Safra").rename(columns=lambda value: str(value) if str(value).startswith("M") else f"M{value}").reset_index()


# --------------------------------------------------------------------------
# Thematic plan. A metric lives in one place: the table of its theme, right
# after the charts it supports (or in the appendix, in the same theme order).
# --------------------------------------------------------------------------

THEMES = (
    ("estrutura", "Estrutura"),
    ("atraso", "Atraso e provisão"),
    ("migracao", "Migração e safras"),
    ("rentabilidade", "Rentabilidade"),
    ("outros", "Outros indicadores"),
)
THEME_TITLES = dict(THEMES)
TABLE_PLACEMENTS = ("inline", "appendix")
SECTION_DOCUMENTS = "Documental"
SECTION_FUNDS = "Anexo por fundo"
SECTION_APPENDIX = "Apêndice · tabelas"
SECTION_COVERAGE = "Referências e cobertura"
# Reference lines the cover already shows (or, for the source, every footer).
_ON_COVER = {"Carteira", "Consulta solicitada", "Histórico selecionado", "Posição comum",
             "Última competência observada", "Fonte mensal", "Consulta"}

# (theme, table title, unit, columns). The monthly base and the monitor feed
# the same tables; a monitor column is shown only when it adds information.
_THEME_TABLES = (
    ("estrutura", "PL e carteira", "R$", ("pl_total", "pl_senior", "pl_mezzanino", "pl_subordinada_strict",
                                          "pl_subordinada_mezz_ex360", "carteira_bruta", "carteira_ex360", "carteira_a_vencer")),
    ("estrutura", "Subordinação e crescimento da carteira", "%", ("subordinacao_total_pct", "subordinacao_total_ex360_pct",
                                                                 "carteira_ex360_mom_pct", "carteira_ex360_yoy_pct")),
    ("estrutura", "Duration estimada", "meses", ("duration_months",)),
    ("atraso", "Atraso e provisão", "R$", ("pdd_total", "pdd_ex360", "npl_over90_ex360", "npl_1_90", "npl_91_360",
                                           "npl_1_360", "npl_over360")),
    ("atraso", "Atraso e provisão", "%", ("npl_over1_ex360_pct", "npl_over30_ex360_pct", "npl_over60_ex360_pct",
                                          "npl_over90_ex360_pct", "npl_1_90_pct", "npl_91_360_pct", "npl_1_360_pct",
                                          "pdd_npl_over90_ex360_pct", "pdd_npl90_ex360_pct")),
    ("atraso", "Aging · saldos por faixa", "R$", ("atraso_ate30", "atraso_31_60", "atraso_61_90", "atraso_91_120",
                                                  "atraso_121_150", "atraso_151_180", "atraso_181_360", "atraso_361_720",
                                                  "atraso_721_1080", "atraso_1080")),
    ("migracao", "Roll rates", "%", _ROLL_COLUMNS),
)
# Same metric in another unit: values stay in the notes, not in a second row.
_UNIT_DUPLICATES = {"duration_days": "Duration estimada em dias (mesma métrica de Duration estimada em meses)"}
_LABEL_FIXES = (("Mezzanino", "Mezanino"), ("Subordinada Júnior", "Subordinada"))
_OVER_LABELS = {"over 1": "Atraso > 1 dia", "over 30": "Atraso > 30 dias", "over 60": "Atraso > 60 dias",
                "over 90": "Atraso > 90 dias", "over 180": "Atraso > 180 dias", "over 360": "Atraso > 360 dias"}
_LONG_CELL = 320


@dataclass(frozen=True)
class _Row:
    label: str
    values: dict[str, Any]
    origin: str = "derivada"


def _month_key(label: str) -> tuple[int, int]:
    month, _, year = str(label).partition("/")
    try:
        return (int(year), _MONTHS.index(month))
    except ValueError:
        return (9999, 99)


def _clean_label(value: Any) -> str:
    text = str(value)
    for old, new in _LABEL_FIXES:
        text = text.replace(old, new)
    text = re.sub(r"\b(\d+) a (\d+) dias\b", r"\1–\2 dias", text)
    return text


def _time_labels(frame: pd.DataFrame) -> list[str] | None:
    column = "competencia" if "competencia" in frame else "competencia_dt" if "competencia_dt" in frame else None
    if column is None:
        return None
    labels = [_month(value) for value in frame[column]]
    return labels if len(labels) == len(set(labels)) else None


def _frame_rows(frame: pd.DataFrame, columns: Iterable[str], origin: str) -> dict[str, _Row]:
    ordered = _ordered(frame)
    labels = _time_labels(ordered) if not ordered.empty else None
    if labels is None:
        return {}
    return {column: _Row(_ALIASES.get(column, column), dict(zip(labels, ordered[column].tolist(), strict=True)), origin)
            for column in columns if column in ordered}


def _identity_rows(frame: pd.DataFrame, identity: str, value: str, origin: str, *, labels: Mapping[str, str] | None = None) -> list[_Row] | None:
    source = _ordered(frame)
    if source.empty or identity not in source or value not in source or "competencia" not in source:
        return []
    if source.duplicated(["competencia", identity]).any():
        return None
    rows = []
    for key, segment in source.groupby(identity, sort=False):
        label = _clean_label(key)
        label = (labels or {}).get(str(key).strip().casefold(), label)
        rows.append(_Row(label, dict(zip(segment["competencia"].map(_month), segment[value].tolist(), strict=True)), origin))
    # "Subordinada 1 · item 1" is a source list position, not a class name;
    # it goes only when the remaining names stay distinct.
    stripped = [re.sub(r"\s*·\s*item\s+\d+$", "", row.label) for row in rows]
    if len(set(stripped)) == len(stripped):
        rows = [replace(row, label=label) for row, label in zip(rows, stripped)]
    return rows


def _display(value: Any, unit: str) -> str | None:
    number = _number(value)
    if number is None:
        return None
    return _br(number / 1_000_000 if unit == "R$" else number, 2)


def _same_values(left: _Row, right: _Row, unit: str) -> bool:
    """Equal at the displayed precision in every month both report, with one
    window inside the other (IME and the monthly base may differ by a month)."""
    shown_left = {month: _display(value, unit) for month, value in left.values.items() if _display(value, unit) is not None}
    shown_right = {month: _display(value, unit) for month, value in right.values.items() if _display(value, unit) is not None}
    common = shown_left.keys() & shown_right.keys()
    if not common or not (shown_left.keys() <= shown_right.keys() or shown_right.keys() <= shown_left.keys()):
        return False
    return all(shown_left[month] == shown_right[month] for month in common)


def _rows_block(title: str, unit: str, rows: list[_Row], notes: Iterable[str] = ()) -> TableBlock:
    months = sorted({month for row in rows for month in row.values}, key=_month_key)
    frame = pd.DataFrame([{"Indicador": row.label, **{month: row.values.get(month) for month in months}} for row in rows],
                         columns=["Indicador", *months])
    token = {"%": "percent:2", "R$": "money_value:2"}.get(unit, "number:2")
    unit_title = {"R$": "R$ milhões"}.get(unit, unit)
    return TableBlock(f"{title} · {unit_title}", frame, {month: token for month in months}, tuple(dict.fromkeys(notes)), tuple(months),
                      compact=len(frame) > 11)


def _theme_tables(monthly: pd.DataFrame, monitor: pd.DataFrame, dashboard: Any = None) -> tuple[dict[str, list[TableBlock]], list[str]]:
    """All series of one scope, grouped by theme. Returns the tables and the
    sentences that explain each row left out for being a repetition."""
    tables: dict[str, list[TableBlock]] = {theme: [] for theme, _ in THEMES}
    omitted: list[str] = []
    all_columns = [column for _, _, _, columns in _THEME_TABLES for column in columns]
    base_rows = _frame_rows(monthly, all_columns, "Base mensal")
    monitor_rows = _frame_rows(monitor, all_columns, "Monitoramento")
    ime: dict[tuple[str, str, str], list[_Row]] = {}
    ime_tables: list[tuple[str, str, str, list[_Row], tuple[str, ...]]] = []
    ime_fallback: list[tuple[str, TableBlock]] = []
    if dashboard is not None:
        subordination = _frame(getattr(dashboard, "subordination_history_df", None))
        ime[("estrutura", "Subordinação e crescimento da carteira", "%")] = list(_frame_rows(subordination, ("subordinacao_pct",), "IME").values())
        defaults = _frame(getattr(dashboard, "default_history_df", None))
        ime[("atraso", "Atraso e provisão", "R$")] = list(_frame_rows(defaults, ("inadimplencia_total", "provisao_total"), "IME").values())
        ime[("atraso", "Atraso e provisão", "%")] = list(_frame_rows(defaults, ("inadimplencia_pct", "provisao_pct_direitos", "cobertura_pct"), "IME").values())
        quotas = _frame(getattr(dashboard, "quota_pl_history_df", None))
        quota_identity = "class_label" if "class_label" in quotas else "classe" if "classe" in quotas else "class_key"
        for theme, title, unit, frame, identity, value, labels in (
            ("estrutura", "Estrutura de cotas", "R$", quotas, quota_identity, "pl", None),
            ("estrutura", "Estrutura de cotas · participação no PL", "%", quotas, quota_identity, "pl_share_pct", None),
            ("atraso", "Aging · saldos por faixa", "R$", _frame(getattr(dashboard, "default_buckets_history_df", None)), "faixa", "valor", None),
            ("atraso", "Aging · composição dos vencidos", "%", _frame(getattr(dashboard, "default_aging_history_df", None)), "faixa", "percentual_inadimplencia", None),
            ("atraso", "Atraso acumulado / direitos creditórios", "%", _frame(getattr(dashboard, "default_over_history_df", None)), "serie", "percentual", _OVER_LABELS),
        ):
            rows = _identity_rows(frame, identity, value, "IME", labels=labels)
            if rows is None:
                # Unknown multiplicity: the original records are kept verbatim.
                for table in _history_tables(title, frame[[c for c in frame if c in {"competencia", "competencia_dt", identity, value}]]):
                    ime_fallback.append((theme, replace(table, notes=(*table.notes, _raw_note(frame)))))
                continue
            if (theme, title, unit) in {(t, n, u) for t, n, u, _ in _THEME_TABLES}:
                ime.setdefault((theme, title, unit), []).extend(rows)
            elif rows:
                ime_tables.append((theme, title, unit, rows, (_raw_note(frame),)))
    shown: dict[str, list[tuple[str, _Row]]] = {theme: [] for theme, _ in THEMES}

    def keep(theme: str, unit: str, row: _Row) -> bool:
        # Only a repetition across sources (IME × base × monitor) is dropped;
        # two distinct derived metrics that happen to coincide both stay.
        for other_unit, other in shown[theme]:
            if other_unit == unit and other.origin != row.origin and _same_values(other, row, unit):
                omitted.append(f"{row.label} ({row.origin}) coincide com {other.label} ({other.origin}) em todas as competências; exibida uma vez.")
                return False
        shown[theme].append((unit, row))
        return True

    for theme, title, unit, columns in _THEME_TABLES:
        rows = []
        for column in columns:
            base, monitored = base_rows.get(column), monitor_rows.get(column)
            if base is not None and keep(theme, unit, base):
                rows.append(base)
            has_values = monitored is not None and any(_display(v, unit) is not None for v in monitored.values.values())
            if has_values and (base is None or not _same_values(base, monitored, unit)):
                if base is not None:
                    monitored = replace(monitored, label=f"{monitored.label} · monitoramento")
                if keep(theme, unit, monitored):
                    rows.append(monitored)
        rows.extend(row for row in ime.get((theme, title, unit), ()) if keep(theme, unit, row))
        empty = [row for row in rows if all(_display(value, unit) is None for value in row.values.values())]
        if empty:
            omitted.append("Sem dados no período: " + ", ".join(row.label for row in empty) + ".")
            rows = [row for row in rows if row not in empty]
        if rows:
            notes = [f"{row.label}: origem {row.origin}." for row in rows]
            if theme == "estrutura" and unit == "meses":
                for column, sentence in _UNIT_DUPLICATES.items():
                    extra = _frame_rows(monthly, (column,), "Base mensal").get(column)
                    if extra is not None:
                        notes.append(f"{sentence}: " + "; ".join(f"{m}={_br(v, 0)}" for m, v in extra.values.items()))
            for frame in (monthly, monitor):
                selected = [column for column in columns if column in frame]
                if selected and not frame.empty:
                    time_column = [c for c in ("competencia",) if c in frame]
                    notes.append(_raw_note(_ordered(frame)[[*time_column, *selected]]))
            tables[theme].append(_rows_block(title, unit, rows, notes))
    for theme, title, unit, rows, notes in ime_tables:
        rows = [row for row in rows if keep(theme, unit, row)]
        if rows:
            tables[theme].append(_rows_block(title, unit, rows, (*notes, "Origem: IME.")))
    for theme, table in ime_fallback:
        tables[theme].append(table)
    return tables, omitted


def _chart_from_rows(title: str, rows: Iterable[tuple[str, str, _Row]], unit: str, *, decimals: int = 1,
                     reference: tuple[str, float] | None = None, notes: Iterable[str] = (), kind: str = "line") -> ChartBlock | None:
    rows = [(key, label, row) for key, label, row in rows if row is not None]
    if kind in {"stacked", "column"}:
        # A part that is zero in every month adds nothing to columns.
        rows = [(key, label, row) for key, label, row in rows if any(_number(value) for value in row.values.values())]
    if not rows:
        return None
    months = sorted({month for _, _, row in rows for month in row.values}, key=_month_key)
    series = []
    for key, label, row in rows:
        values = tuple(_number(row.values.get(month)) for month in months)
        if unit == "R$ mm":
            values = tuple(value / 1_000_000 if value is not None else None for value in values)
        series.append(ChartSeries(key, label, values, unit, decimals))
    drawn = [value for spec in series for value in spec.values if value is not None]
    if reference is not None and drawn and max(map(abs, drawn)) < .25 * abs(reference[1]):
        # A reference four times above every value only squeezes the series.
        notes = (*tuple(notes), f"{reference[0]} fora da escala: máximo do período {_br(max(drawn), decimals)}{'%' if unit == '%' else ''}.")
        reference = None
    if reference is not None:
        series.append(ChartSeries("reference", reference[0], tuple(reference[1] for _ in months), unit, decimals, reference=True))
    return ChartBlock(title, tuple(months), tuple(series), unit, tuple(notes), kind=kind)


def _share_chart(title: str, chart: ChartBlock | None, notes: Iterable[str] = ()) -> ChartBlock | None:
    """The same parts as a percentage of their monthly total."""
    if chart is None:
        return None
    totals = [sum(value for spec in chart.series if (value := spec.values[index]) is not None) for index in range(len(chart.categories))]
    series = tuple(replace(spec, unit="%", decimals=0, values=tuple(
        value / total * 100 if value is not None and total > 0 else None for value, total in zip(spec.values, totals)))
        for spec in chart.series)
    return ChartBlock(title, chart.categories, series, "%", tuple(notes), kind="stacked")


#: Aging buckets of the overdue composition, grouped so a stacked column
#: reads at slide size: (label, first day, last day).
_AGING_GROUPS = (("Até 30d", 0, 30), ("31–90d", 31, 90), ("91–180d", 91, 180), ("181–360d", 181, 360), ("> 360d", 361, 10**6))


def _aging_chart(dashboard: Any) -> ChartBlock | None:
    rows = _identity_rows(_frame(getattr(dashboard, "default_aging_history_df", None)), "faixa", "percentual_inadimplencia", "IME")
    if not rows:
        return None
    grouped: dict[str, dict[str, float]] = {}
    for row in rows:
        days = [int(number) for number in re.findall(r"\d+", row.label)]
        if not days:
            return None
        first = days[0] if not row.label.lower().startswith("até") else 0
        label = next(name for name, low, high in _AGING_GROUPS if low <= first <= high)
        for month, value in row.values.items():
            number = _number(value)
            if number is not None:
                grouped.setdefault(label, {}).setdefault(month, 0.0)
                grouped[label][month] += number
    if not grouped:
        return None
    months = sorted({month for values in grouped.values() for month in values}, key=_month_key)
    series = tuple(ChartSeries(f"aging:{name}", name, tuple(grouped[name].get(month) for month in months), "%", 0)
                   for name, _, _ in _AGING_GROUPS if name in grouped and any(grouped[name].values()))
    return ChartBlock("Aging dos vencidos (IME) · % dos vencidos", tuple(months), series, "%",
                      ("Composição dos créditos vencidos por faixa de atraso; informe mensal (IME).",), kind="stacked")


#: A line needs at least this many observations; fewer read better as values.
_MIN_LINE_POINTS = 3


def _is_trivial(chart: ChartBlock) -> bool:
    """Constant, empty, or too short to be a line (every series with fewer
    than three observations)."""
    drawn = [spec for spec in chart.series if not spec.reference]
    if chart.kind == "line" and all(sum(value is not None for value in spec.values) < _MIN_LINE_POINTS for spec in drawn):
        return True
    for spec in drawn:
        shown = {_br(value, spec.decimals) for value in spec.values if value is not None}
        if len(shown) > 1:
            return False
    return True


def _trivial_sentence(chart: ChartBlock) -> TextBlock:
    """A constant, empty or very short series becomes a sentence, never a
    flat line or a two-point segment."""
    parts = []
    for spec in chart.series:
        if spec.reference:
            continue
        valid = [(month, value) for month, value in zip(chart.categories, spec.values) if value is not None]
        suffix = "%" if spec.unit == "%" else f" {spec.unit}"
        shown = {_br(value, spec.decimals) for _, value in valid}
        if not valid:
            parts.append(f"{spec.label}: sem dados no período.")
        elif len(valid) == 1:
            parts.append(f"{spec.label}: {_br(valid[0][1], spec.decimals)}{suffix} em {valid[0][0]} (1 observação).")
        elif len(shown) > 1:
            parts.append(f"{spec.label}: " + " → ".join(f"{_br(value, spec.decimals)}{suffix} ({month})" for month, value in valid) + ".")
        else:
            qualifier = "nas competências disponíveis" if len(valid) < len(spec.values) else "em todo o período"
            parts.append(f"{spec.label}: {_br(valid[0][1], spec.decimals)}{suffix} {qualifier}.")
    return TextBlock(chart.title, "\n".join(parts))


def _panel_pairs(pairs: Iterable[tuple[Any, Any]]) -> tuple[list[tuple[Any, ...]], list[TextBlock]]:
    """Derived metric on the left, reported on the right. Constant charts turn
    into sentences: one may fill the free half of a slide, the rest go to the
    theme text. Half-empty pairs are merged so a slide never holds one lonely plot."""
    complete, singles, leftovers = [], [], []
    for pair in pairs:
        panels, kpis, slots = [], [], []
        for block in pair:
            if block is None:
                continue
            if isinstance(block, ChartBlock) and _is_trivial(block):
                kpis.append(_trivial_sentence(block))
                slots.append(kpis[-1])
            else:
                panels.append(block)
                slots.append(block)
        if len(panels) == 2:
            complete.append(tuple(panels))
        elif len(panels) == 1 and kpis:
            # The sentence keeps its side: derived left, reported right.
            first = next(block for block in slots if block is panels[0] or block is kpis[0])
            complete.append((panels[0], kpis[0]) if first is panels[0] else (kpis[0], panels[0]))
            kpis.pop(0)
        elif panels:
            singles.append(panels[0])
        leftovers.extend(kpis)
    while len(singles) >= 2:
        complete.append((singles.pop(0), singles.pop(0)))
    if singles:
        complete.append((singles[0], leftovers.pop(0)) if leftovers else (singles[0],))
    return complete, leftovers


def _clean_series_labels(frame: pd.DataFrame) -> pd.DataFrame:
    """'Subordinada 1 · item 3' is a source list position, not a series name."""
    if frame.empty or RETURN_SERIES_COLUMN not in frame:
        return frame
    out = frame.copy()
    stripped = out[RETURN_SERIES_COLUMN].astype(str).map(lambda value: re.sub(r"\s*·\s*item\s+\d+$", "", _clean_label(value)))
    counts = stripped.value_counts()
    out[RETURN_SERIES_COLUMN] = [
        new if counts[new] == 1 else re.sub(r"\s*·\s*item\s+(\d+)$", r" (posição \1)", _clean_label(old))
        for old, new in zip(out[RETURN_SERIES_COLUMN].astype(str), stripped)
    ]
    return out


def _return_blocks(outputs: Any, cnpj: str, monthly: pd.DataFrame, monthly_cdi_rates_by_fund, benchmark_spreads_by_fund) -> dict[str, Any]:
    history = _frame(_lookup(getattr(outputs, "fund_return_history", {}), cnpj))
    summary_frame = _frame(_lookup(getattr(outputs, "fund_return_summary", {}), cnpj))
    history_dates = [value for value in history.get("competencia", pd.Series(dtype="object")).map(_date) if value is not None]
    visual_frame = monthly if not monthly.empty else _frame(getattr(outputs, "consolidated_monthly", None))
    visual_dates = [value for value in visual_frame.get("competencia", pd.Series(dtype="object")).map(_date) if value is not None]
    summary_dates = [value for value in summary_frame.get("latest_competencia", pd.Series(dtype="object")).map(_date) if value is not None]
    end_dates = [*history_dates, *summary_dates]
    # Producer summaries keep their calculation buffer. The monthly
    # presentation cells obey the independently selected visual window.
    start = min(visual_dates) if visual_dates else min(history_dates) if history_dates else None
    end = max(end_dates) if end_dates else max(visual_dates) if visual_dates else None
    months = max(1, (end.year - start.year) * 12 + end.month - start.month + 1) if start is not None and end is not None else max(1, len(monthly))
    matrix = build_fund_return_matrix(
        outputs, cnpj, months=months,
        monthly_cdi_rates=_lookup(monthly_cdi_rates_by_fund, cnpj) if monthly_cdi_rates_by_fund is not None else None,
        benchmark_spreads=_lookup(benchmark_spreads_by_fund, cnpj) if benchmark_spreads_by_fund is not None else None,
    )
    result: dict[str, Any] = {"history": history, "summary": summary_frame, "matrix": matrix}
    if matrix.empty:
        return result
    if visual_dates:
        visible_months = {_month(value) for value in visual_dates}
        matrix = matrix.loc[:, [column for column in matrix if not (len(str(column)) == 6 and str(column)[3:4] == "/") or str(column) in visible_months]].copy()
    raw_series = matrix[RETURN_SERIES_COLUMN].astype(str).tolist() if RETURN_SERIES_COLUMN in matrix else []
    matrix = _clean_series_labels(matrix)
    month_columns = [column for column in matrix if len(str(column)) == 6 and str(column)[3:4] == "/"]
    summary_columns = [column for column in (RETURN_SERIES_COLUMN, RETURN_TRAILING_12M_COLUMN, RETURN_TRAILING_12M_CDI_COLUMN,
                                             RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN, RETURN_YTD_COLUMN) if column in matrix]
    rest_columns = [column for column in matrix if column not in summary_columns and column not in month_columns]
    formats = {str(column): "number:0" if "bps" in str(column) else "percent:2" for column in matrix.columns[1:]}
    label_note = "Séries originais: " + "; ".join(raw_series)
    informed = [number for column in [*month_columns, RETURN_TRAILING_12M_COLUMN, RETURN_YTD_COLUMN] if column in matrix
                for value in matrix[column] if (number := _number(value)) is not None]
    if informed and all(value == 0 for value in informed):
        result["summary_block"] = TextBlock("Retorno por cota", "Rentabilidade de 0,00% nas observações informadas.")
    elif not any(_number(value) is not None for column in summary_columns[1:] for value in matrix[column]):
        result["summary_block"] = TextBlock("Acumulados", "Acumulados de 12 meses e YTD indisponíveis no período.")
    else:
        result["summary_block"] = TableBlock("Retorno acumulado por série · %", matrix[summary_columns].copy(),
            {str(c): formats[str(c)] for c in summary_columns[1:]}, (CVM_RETURN_REINVESTMENT_NOTE, label_note), tuple(map(str, summary_columns[1:])))
    twelve = [_number(value) for value in matrix.get(RETURN_TRAILING_12M_COLUMN, pd.Series(dtype=float))]
    cdi = [_number(value) for value in matrix.get(RETURN_TRAILING_12M_CDI_COLUMN, pd.Series(dtype=float))] or [None] * len(twelve)
    # A series without a 12-month return is not an empty bar slot.
    shown = [index for index, value in enumerate(twelve) if value is not None]
    if 0 < len(shown) <= 8 and isinstance(result["summary_block"], TableBlock):
        categories = [str(matrix[RETURN_SERIES_COLUMN].iloc[index]) for index in shown]
        twelve = [twelve[index] for index in shown]
        cdi = [cdi[index] for index in shown]
        series = [ChartSeries("return_12m", "Retorno 12m", tuple(twelve), "%", 1)]
        known_cdi = {round(value, 4) for value in cdi if value is not None}
        if len(known_cdi) == 1:
            # Same window for every series: the CDI is one reference bar.
            categories.append("CDI 12m")
            series = [ChartSeries("return_12m", "Retorno 12m", (*twelve, next(iter(known_cdi))), "%", 1)]
        elif known_cdi:
            series.append(ChartSeries("cdi_12m", "CDI 12m", tuple(cdi), "%", 1))
        result["chart"] = ChartBlock("Retorno 12m por série" + (" vs. CDI" if known_cdi else "") + " · %",
                                     tuple(categories), tuple(series), "%", (CVM_RETURN_REINVESTMENT_NOTE,), kind="bar")
    cdi_notes = (CVM_RETURN_REINVESTMENT_NOTE, f"CDI: {matrix.attrs.get('cdi_source', 'benchmark não solicitado')}",
                 f"CDI sem competência: {matrix.attrs.get('cdi_missing_competencias', ())}", label_note)
    if month_columns:
        result["monthly_block"] = TableBlock("Retorno mensal por série · %", matrix[[RETURN_SERIES_COLUMN, *month_columns]].copy(),
            {str(c): "percent:2" for c in month_columns}, cdi_notes, tuple(map(str, month_columns)))
    if rest_columns:
        result["rest_block"] = TableBlock("Acumulados YTD, CDI e emissão", matrix[[RETURN_SERIES_COLUMN, *rest_columns]].copy(),
            {str(c): formats[str(c)] for c in rest_columns}, cdi_notes, tuple(map(str, rest_columns)))
    return result


def _short_citation(value: str) -> str:
    """A list of citations shows its first source; the rest stay in the notes."""
    parts = [part.strip() for part in re.split(r";\s*", value) if part.strip()]
    first = re.sub(r"\s*·?\s*(?:data|reports)/\S+", "", parts[0]).strip(" ·") if parts else value
    first = re.sub(r"\s*·?\s*https?://\S+", "", first).strip(" ·")
    return first + (f" (+{len(parts) - 1} fontes nas notas)" if len(parts) > 1 else "")


def _shorten_long_cells(frame: pd.DataFrame, entity: str, clauses: list[dict[str, str]], *, target: str = "anexo") -> pd.DataFrame:
    """Long legal text leaves the cell; the full clause goes to the appendix
    (or to the notes, e.g. ``target="notas da Ficha documental"``, in a summarized large basket)."""
    out = frame.copy()
    for row_index in range(len(out)):
        for column in out.columns[1:]:
            value = out.iat[row_index, out.columns.get_loc(column)]
            if isinstance(value, str) and str(column).casefold().startswith("fonte") and len(value) > 120:
                out.iat[row_index, out.columns.get_loc(column)] = _short_citation(value)
                continue
            if isinstance(value, str) and len(value) > _LONG_CELL:
                code = f"C{len(clauses) + 1}"
                clauses.append({"Ref.": code, "Campo": f"{column} · {out.iat[row_index, 0]}" if entity == "" else f"{entity} · {out.iat[row_index, 0]}",
                                "Cláusula integral": value})
                out.iat[row_index, out.columns.get_loc(column)] = f"Cláusula longa · texto integral em {code} ({target})"
    return out


def _prune_empty(block: Any) -> tuple[Any, list[str]]:
    """Series tables without any value in a row or column lose that row or
    column; what was left out is said once in the coverage slide."""
    if not isinstance(block, TableBlock) or block.snapshot or not block.numeric_columns or block.frame.empty:
        return block, []
    frame = block.frame
    numeric = [column for column in frame.columns[1:] if column in block.numeric_columns]
    missing = frame[numeric].apply(lambda column: column.map(_is_missing)) if numeric else pd.DataFrame()
    if missing.empty:
        return block, []
    empty_columns = [column for column in numeric if missing[column].all()]
    others = [column for column in frame.columns[1:] if column not in numeric]
    empty_rows = missing.all(axis=1) & (frame[others].apply(lambda column: column.map(_is_missing)).all(axis=1) if others else True)
    if not empty_columns and not empty_rows.any():
        return block, []
    if empty_rows.all() or len(empty_columns) == len(frame.columns) - 1:
        return None, [f"{block.title}: sem valores no período."]
    said = []
    if empty_rows.any():
        said.append(f"{block.title}: sem valores no período para " + ", ".join(map(str, frame.loc[empty_rows].iloc[:, 0])) + ".")
    if empty_columns:
        said.append(f"{block.title}: colunas sem valores omitidas ({', '.join(map(str, empty_columns))}).")
    kept = frame.loc[~empty_rows].drop(columns=empty_columns)
    return replace(block, frame=kept, numeric_columns=tuple(c for c in block.numeric_columns if c in kept)), said


#: A theme's reading table in the body: longer tables go to the appendix.
BODY_TABLE_ROWS = 20

#: Above this many funds the per-fund annex becomes one comparison table.
FUND_ANNEX_MAX_FUNDS = 12
FUND_ANNEX_MODES = ("auto", "metrics", "full", "summary")

# Small multiples of the per-fund annex: (column, title, unit, shared scale).
# Ratios share one scale so funds compare at a glance; volumes and coverage
# (which spikes when NPL is near zero) keep each fund's own scale.
_FUND_METRICS = (
    ("pl_total", "PL total · R$ milhões", "R$ mm", False),
    ("subordinacao_total_ex360_pct", "Subordinação ex-360 · %", "%", True),
    ("npl_over30_ex360_pct", "NPL > 30d ex-360 · %", "%", True),
    ("npl_over90_ex360_pct", "NPL > 90d ex-360 · %", "%", True),
    ("pdd_npl_over90_ex360_pct", "Cobertura PDD / NPL > 90d ex-360 · %", "%", False),
    ("roll_61_90_m3_pct", "Roll 61–90 / a vencer M-3 · %", "%", True),
)


def _fund_metric_charts(fund_scopes: list[tuple[str, str, pd.DataFrame, pd.DataFrame, pd.DataFrame]]) -> tuple[list[tuple[str, tuple[ChartBlock, ...]]], list[str]]:
    """One page per metric with one small chart per fund, on common months.
    A metric that is constant in every fund is a sentence, not a page."""
    pages, constant = [], []
    for column, title, unit, shared in _FUND_METRICS:
        rows = {}
        for cnpj, name, monthly, monitor, _ in fund_scopes:
            source = _ordered(monitor if column in monitor else monthly)
            if source.empty or column not in source or "competencia" not in source:
                continue
            values = {_month(month): _number(value) for month, value in zip(source["competencia"], source[column])}
            if unit == "R$ mm":
                values = {month: value / 1_000_000 if value is not None else None for month, value in values.items()}
            if any(value is not None for value in values.values()):
                rows[cnpj] = (name, values)
        if not rows:
            continue
        if all(len({_br(value, 1) for value in values.values() if value is not None}) <= 1 for _, values in rows.values()):
            constant.append(f"Por fundo · {title}: sem variação em nenhum fundo no período.")
            continue
        months = tuple(sorted({month for _, values in rows.values() for month in values}, key=_month_key))
        pooled = [value for _, values in rows.values() for value in values.values() if value is not None]
        axis = (min(pooled), max(pooled)) if shared else ()
        charts = tuple(ChartBlock(name, months, (ChartSeries(f"{cnpj}:{column}", name, tuple(values.get(month) for month in months), unit, 1),),
                                  unit, (f"{name} · {title}: escala {'comum a todos os fundos' if shared else 'própria do fundo'}.",), axis_range=axis)
                       for cnpj, (name, values) in rows.items())
        pages.append((title + (" · escala comum" if shared else " · escala própria"), charts))
    return pages, constant


def build_portfolio_deck_spec(
    *, portfolio_name: str, funds: Iterable[Any], outputs: Any, monitor_outputs: Any,
    research_outputs: Any = None, dashboard: Any = None,
    dashboard_summary_competencia: str | None = None,
    documentary_pages: Iterable[Any] = (), documentary_manifest: Any = None,
    analytical_data: Iterable[Any] = (), requested_period_label: str | None = None,
    monthly_cdi_rates_by_fund: Mapping[str, Iterable[Any]] | None = None,
    benchmark_spreads_by_fund: Mapping[str, Mapping[str, float]] | None = None,
    include_conclusions: bool = False, generated_at: datetime | None = None,
    table_placement: str = "appendix", reference_lines: Iterable[str] = (),
    export_warnings: Iterable[str] = (), fund_annex: str = "auto",
) -> DeckSpec:
    """Return one ordered content plan, preserving all selected source values.

    Order: Snapshot (beside the fund sheet for one fund) → themes (charts
    and one reading table) → fund by fund (small multiples per metric) →
    series appendix → documents → references and coverage. With
    ``table_placement="inline"`` each theme keeps its series tables instead.
    """
    if table_placement not in TABLE_PLACEMENTS:
        raise ValueError(f"table_placement deve ser um de {TABLE_PLACEMENTS}.")
    if fund_annex not in FUND_ANNEX_MODES:
        raise ValueError(f"fund_annex deve ser um de {FUND_ANNEX_MODES}.")
    funds = tuple(funds)
    documentary_pages = tuple(documentary_pages)
    analytical_data = tuple(analytical_data)
    single_fund = len(funds) <= 1
    scopes = _scope_frames(funds, outputs, monitor_outputs)
    # Funds without any monthly record (failed load, no informe) leave the
    # quantitative sections and are named once in the coverage slide.
    without_data: list[str] = []
    empty_funds = [index for index, scope in enumerate(scopes) if scope[0] != "consolidado" and scope[2].empty and scope[3].empty]
    if not single_fund and len(empty_funds) < sum(scope[0] != "consolidado" for scope in scopes):
        without_data = [f"{scopes[index][1]} · CNPJ {scopes[index][0]}" for index in empty_funds]
        scopes = [scope for index, scope in enumerate(scopes) if index not in empty_funds]
    # One canonical name per fund. A single-fund deck uses the name chosen
    # for the portfolio; legal CVM names stay in the notes.
    canonical = {_digits(cnpj): name for cnpj, name, *_ in scopes if cnpj != "consolidado"}
    if single_fund and scopes:
        scopes[0] = (scopes[0][0], portfolio_name, *scopes[0][2:])
        canonical = {key: portfolio_name for key in canonical} or canonical
    main_cnpj, main_name, main_monthly, main_monitor, main_cohorts = scopes[0]
    deck_entity = main_name if single_fund else portfolio_name
    legal_names = {_digits(cnpj): name for cnpj, name in map(_fund_identity, funds)}

    def name_for(cnpj: Any, fallback: str) -> str:
        return canonical.get(_digits(cnpj), fallback)

    now = generated_at or datetime.now(ZoneInfo("America/Sao_Paulo"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
    period = _period(_frame(getattr(outputs, "consolidated_monthly", None)))
    if period == "período N/D":
        period = _period(main_monthly)
    identity_notes = tuple(f"{name} · CNPJ {cnpj}" for cnpj, name in map(_fund_identity, funds))
    references: list[dict[str, str]] = []
    coverage_notes: list[str] = []
    missing_fields: dict[str, list[str]] = {}
    all_document_sources: list[str] = []
    documentary_references: dict[str, list[str]] = {}
    clauses: list[dict[str, str]] = []
    documentary_themes_without_id: list[str] = []

    def slide(title: str, entity: str, blocks: Iterable[Any], *, source: str = _SOURCE, notes: Iterable[str] = (),
              appendix: bool = False, unit: str = "", layout: str = "flow", section: str = "") -> SlideSpec | None:
        blocks = tuple(block for block in blocks if block is not None)
        if section != SECTION_COVERAGE:
            pruned = []
            for block in blocks:
                block, said = _prune_empty(block)
                coverage_notes.extend(f"{entity}: {sentence}" for sentence in said)
                if block is not None:
                    pruned.append(block)
            blocks = tuple(pruned)
        if not blocks:
            return None
        context = " · ".join(part for part in (entity, unit, period) if part)
        return SlideSpec(title, context, blocks, source, (*tuple(notes), *identity_notes),
                         "appendix" if appendix else "content", layout, section)

    snapshot = _snapshot(scopes, dashboard, dashboard_summary_competencia)
    comparison = _fund_comparison(scopes)
    if comparison is not None and not comparison.numeric_columns:
        comparison = None  # no fund has any value: the coverage slide says why
    annex_mode = fund_annex if fund_annex != "auto" else ("metrics" if len(funds) <= FUND_ANNEX_MAX_FUNDS else "summary")
    annex_comparison = None
    if comparison is not None and annex_mode == "summary":
        # A long fund list is the annex itself, not part of the snapshot.
        annex_comparison, comparison = comparison, None
    if comparison is not None:
        # Consolidated position and one row per fund read together: the small
        # type lets both share the first slide.
        snapshot, comparison = replace(snapshot, compact=True), replace(comparison, compact=True)
    head: list[SlideSpec | None] = [slide("Snapshot", deck_entity, tuple(block for block in (snapshot, comparison)
                                                                    if block is not None and not block.frame.empty))]

    # ---- Main scope (single fund or consolidated): charts and series by theme.
    main_dashboard = dashboard
    theme_tables, omitted = _theme_tables(main_monthly, main_monitor, main_dashboard)
    coverage_notes.extend(omitted)
    credit = main_monitor if not main_monitor.empty else main_monthly
    rows_main = {**_frame_rows(main_monthly, [c for _, _, _, cols in _THEME_TABLES for c in cols], "Base mensal"),
                 **{k: v for k, v in _frame_rows(main_monitor, [c for _, _, _, cols in _THEME_TABLES for c in cols], "Monitoramento").items()
                    if k not in main_monthly}}
    ime_rows: dict[str, _Row] = {}
    if main_dashboard is not None:
        ime_rows.update(_frame_rows(_frame(getattr(main_dashboard, "subordination_history_df", None)), ("subordinacao_pct",), "IME"))
        ime_rows.update(_frame_rows(_frame(getattr(main_dashboard, "default_history_df", None)),
                                    ("inadimplencia_pct", "provisao_pct_direitos", "cobertura_pct"), "IME"))
    key = main_cnpj

    def series(column: str, label: str | None = None, source: dict[str, _Row] = rows_main):
        row = source.get(column)
        return (f"{key}:{column}", label or _ALIASES.get(column, column), row) if row is not None else None

    subordination_series = [series("subordinacao_total_ex360_pct")]
    reported = ime_rows.get("subordinacao_pct")
    derived_sub = rows_main.get("subordinacao_total_ex360_pct")
    if reported is not None and not (derived_sub is not None and _same_values(derived_sub, reported, "%")):
        subordination_series.append(("ime:subordinacao_pct", "Subordinação reportada (IME)", reported))
    elif reported is not None:
        coverage_notes.append("Subordinação reportada (IME) coincide com a subordinação ex-360 em todas as competências; exibida uma vez.")
    theme_pairs: dict[str, list[tuple[Any, Any]]] = {theme: [] for theme, _ in THEMES}
    # Parts of the PL by class: the junior classes collapse into one when the
    # base does not tell mezzanine from subordinated.
    classes = [s for s in (series("pl_senior", "Sênior"), series("pl_mezzanino", "Mezanino"), series("pl_subordinada_strict", "Subordinada")) if s]
    if len(classes) < 2:
        classes = [s for s in (series("pl_senior", "Sênior"), series("pl_subordinada_mezz_ex360", "Subordinada + mezanino")) if s]
    pl_by_class = _chart_from_rows("PL por classe · R$ milhões", classes, "R$ mm", kind="stacked",
                                   notes=("Classes de cota da base mensal; total no topo da coluna.",)) if len(classes) >= 2 else None
    theme_pairs["estrutura"].append((pl_by_class, _share_chart("PL por classe · % do PL", pl_by_class)))
    theme_pairs["estrutura"].append((
        _chart_from_rows("Subordinação · %", [s for s in subordination_series if s], "%",
                         notes=("Ex-360: derivada da base mensal. Reportada: informe mensal (IME).",)),
        _chart_from_rows("Carteira bruta ex-360 · R$ milhões", [s for s in (series("carteira_ex360", "Carteira ex-360"),) if s], "R$ mm", kind="column",
                         notes=("Último mês em laranja.",)),
    ))
    severity = [s for s in (series("npl_1_90_pct", "1–90 dias"), series("npl_91_360_pct", "91–360 dias")) if s]
    theme_pairs["atraso"].append((
        _chart_from_rows("NPL ex-360 por faixa · % da carteira", severity, "%", kind="stacked",
                         notes=("Denominador: carteira bruta ex-360; vencidos acima de 360 dias excluídos.",)) if severity else
        _chart_from_rows("NPL / carteira ex-360 · %", [s for s in (series("npl_over30_ex360_pct", "NPL > 30d"), series("npl_over90_ex360_pct", "NPL > 90d")) if s], "%",
                         notes=("Denominador: carteira bruta ex-360; vencidos acima de 360 dias excluídos.",)),
        _chart_from_rows("Vencidos e provisão / direitos creditórios (IME) · %",
                         [s for s in (series("inadimplencia_pct", "Vencidos", ime_rows), series("provisao_pct_direitos", "Provisão", ime_rows)) if s], "%",
                         notes=("Informe mensal (IME); denominador próprio, não substituído pelo NPL ex-360.",)),
    ))
    theme_pairs["atraso"].append((
        _chart_from_rows("Cobertura PDD / NPL > 90d ex-360 · %", [s for s in (series("pdd_npl_over90_ex360_pct", "PDD / NPL > 90d"),) if s], "%", kind="column",
                         notes=("Último mês em laranja.",)),
        _aging_chart(main_dashboard) if main_dashboard is not None else None,
    ))
    roll_chart = _chart_from_rows("Roll rates · %", [series(c, _ALIASES[c].replace(" / a vencer", "")) for c in _ROLL_COLUMNS if series(c)], "%", decimals=2,
                                  notes=("Proxies: faixa de atraso atual / carteira a vencer M-3, M-4, M-5 ou M-6.",))
    complete_cohorts = _cohort_matrix(main_cohorts, recent=False) if not main_cohorts.empty else pd.DataFrame()
    cohort_panel = None
    cohorts_in_panel = False
    if not complete_cohorts.empty and "Safra" in complete_cohorts:
        recent = _cohort_matrix(main_cohorts, recent=True)
        # The body shows the recent cohorts beside the roll rates; the full
        # matrix goes with the theme's series.
        cohorts_in_panel = len(complete_cohorts) <= 6 and len(complete_cohorts.columns) <= 8
        view = complete_cohorts if cohorts_in_panel else recent
        cohort_panel = TableBlock("Safras · %" if cohorts_in_panel else "Safras recentes · %", view,
                                  {str(c): "percent:1" for c in view.columns[1:]}, (_raw_note(main_cohorts),), tuple(map(str, view.columns[1:])), compact=True)
        if len(view) < 2:
            # One cohort is a sentence, not a matrix.
            cells = [f"{column} {_br(value, 1)}%" for column, value in zip(view.columns[1:], view.iloc[0, 1:]) if _number(value) is not None]
            cohort_panel = TextBlock("Safras · %", f"Safra {view.iloc[0, 0]}: " + ("; ".join(cells) or "sem valores") + ".") if len(view) else None
    theme_pairs["migracao"].append((roll_chart, cohort_panel))
    if not complete_cohorts.empty and not cohorts_in_panel:
        theme_tables["migracao"].append(TableBlock("Safras · %", complete_cohorts, {str(c): "percent:1" for c in complete_cohorts.columns[1:]},
                                                   (_raw_note(main_cohorts), "Safra proxy, numerador, denominador e estados originais preservados."),
                                                   tuple(map(str, complete_cohorts.columns[1:]))))
    if research_outputs is not None:
        roll_source = _frame(getattr(research_outputs, "roll_seasonality", None))
        if not roll_source.empty:
            if "scope" in roll_source:
                main_rows = roll_source["scope"].eq("consolidado") if not single_fund else roll_source["scope"].ne("consolidado")
                if main_rows.any() or not single_fund:
                    # Several funds without a consolidated series: the
                    # per-fund seasonality belongs to the per-fund annex.
                    roll_source = roll_source[main_rows].copy()
            roll = _roll_matrix(roll_source)
            if not roll.empty and any(_number(value) is not None for value in roll_source["value_pct"]):
                theme_tables["migracao"].append(TableBlock("Sazonalidade da migração · roll rates por mês do ano · %", roll,
                    {str(c): "percent:1" for c in roll.columns[1:]}, (_raw_note(roll_source),), tuple(map(str, roll.columns[1:]))))
            elif not roll.empty:
                criteria = "; ".join(roll_source["metric_name"].astype(str).drop_duplicates())
                coverage_notes.append("Sazonalidade da migração: sem observações válidas no período para " + criteria + ".")
        methodology = _frame(getattr(research_outputs, "methodology", None))
        if not methodology.empty:
            references.append({"Referência": "Migração e safras", "Conteúdo": "Proxies e denominadores originais do app; fórmulas nas notas."})
            all_document_sources.append("Metodologia: " + _raw_note(methodology))

    # Rentabilidade: per fund, since returns belong to share classes.
    fund_scopes = [scope for scope in scopes if scope[0] != "consolidado"]
    returns_by_fund: dict[str, dict[str, Any]] = {}
    for cnpj, name, monthly, *_ in fund_scopes:
        result = _return_blocks(outputs, cnpj, monthly, monthly_cdi_rates_by_fund, benchmark_spreads_by_fund)
        returns_by_fund[cnpj] = result
        for label, frame in (("Retorno mensal original", result["history"]), ("Retorno acumulado original", result["summary"])):
            if not frame.empty:
                references.append({"Referência": f"{name} · {label}", "Conteúdo": "Identidades de cota, competências e estados completos nas notas da rentabilidade."})
                all_document_sources.append(f"{name} · {label}: buffer recebido do produtor para os acumulados. " + _raw_note(frame))
    return_texts: list[TextBlock] = []
    if single_fund and fund_scopes:
        result = returns_by_fund[fund_scopes[0][0]]
        if "chart" in result:
            theme_pairs["rentabilidade"].append((result["chart"], replace(result["summary_block"], compact=True)))
        elif "summary_block" in result:
            block = result["summary_block"]
            if isinstance(block, TextBlock) or (table_placement == "appendix" and len(block.frame) <= BODY_TABLE_ROWS):
                return_texts.append(block)
            else:
                rest = result.get("rest_block")
                if rest is not None and list(rest.frame.index) == list(block.frame.index):
                    # One row per series: the 12-month and the YTD, CDI and
                    # issuance accumulations side by side, not two tables
                    # repeating every series name.
                    frame = pd.concat([block.frame, rest.frame.drop(columns=[RETURN_SERIES_COLUMN])], axis=1)
                    block = TableBlock("Acumulados por série · %", frame, {**block.formats, **rest.formats},
                                       tuple(dict.fromkeys((*block.notes, *rest.notes))),
                                       tuple(dict.fromkeys((*block.numeric_columns, *rest.numeric_columns))))
                    result = {key: value for key, value in result.items() if key != "rest_block"}
                theme_tables["rentabilidade"].append(block)
                if table_placement == "appendix":
                    return_texts.append(TextBlock(block.title, f"{len(block.frame)} séries; tabela completa no apêndice."))
        theme_tables["rentabilidade"].extend(result[k] for k in ("monthly_block", "rest_block") if k in result)
    else:
        # One table across funds (a "Fundo" column) instead of one header
        # per fund; funds without accumulated returns share one sentence.
        frames, notes, sentences = [], [], []
        for cnpj, name, *_ in fund_scopes:
            block = returns_by_fund[cnpj].get("summary_block")
            if isinstance(block, TableBlock):
                frame = block.frame.copy()
                frame.insert(0, "Fundo", name)
                frames.append(frame)
                notes.extend(block.notes)
                template = block
            elif isinstance(block, TextBlock):
                sentences.append(f"{name}: {block.text[:1].lower()}{block.text[1:]}")
        if frames:
            combined = pd.concat(frames, ignore_index=True, sort=False).astype(object)
            combined_block = replace(template, frame=combined, notes=tuple(dict.fromkeys(notes)),
                numeric_columns=tuple(c for c in combined.columns[2:]), formats={str(c): template.formats.get(str(c), "percent:2") for c in combined.columns[2:]})
            if len(funds) <= FUND_ANNEX_MAX_FUNDS or fund_annex == "full":
                theme_tables["rentabilidade"].append(combined_block)
            else:
                # Hundreds of share classes are not read on slides: the
                # values stay in the notes and the page keeps the detail.
                return_texts.append(TextBlock("Retorno acumulado por série",
                    f"{len(combined)} séries de {len(frames)} fundos; valores completos nas notas deste slide e na página da carteira."))
                all_document_sources.append("Retorno acumulado por série: " + _raw_note(combined))
        if sentences:
            return_texts.append(TextBlock("Sem retorno acumulado", "\n".join(sentences)))
    if main_dashboard is not None and hasattr(main_dashboard, "return_history_df") and hasattr(main_dashboard, "return_summary_df") \
            and not any("summary_block" in result for result in returns_by_fund.values()):
        from services.fundonet_ppt_export import _build_return_inline_table_for_ppt
        return_table = _build_return_inline_table_for_ppt(main_dashboard, selected_labels=None, months=max(1, len(getattr(main_dashboard, "competencias", ())) or 12))
        if not return_table.empty:
            theme_tables["rentabilidade"].append(TableBlock("Retornos por cota (IME) · %", return_table,
                notes=(_raw_note(_frame(getattr(main_dashboard, "return_history_df", None))), CVM_RETURN_REINVESTMENT_NOTE),
                numeric_columns=tuple(map(str, return_table.columns[1:]))))

    # IME position: only what no series already shows (assets, receivables).
    summary = getattr(main_dashboard, "summary", {}) or {} if main_dashboard is not None else {}
    ime_position_text = ""
    if summary:
        summary_cut = _month(dashboard_summary_competencia or getattr(main_dashboard, "latest_competencia", None))
        position_rows = []
        for item in ("ativos_totais", "direitos_creditorios"):
            if item in summary:
                number = _number(summary[item])
                position_rows.append({"Indicador": _ALIASES.get(item, item), f"Posição {summary_cut}": _br(number / 1_000_000, 1) if number is not None else "N/D"})
        all_document_sources.append(f"Posição IME original ({summary_cut}): " + _raw_note(pd.DataFrame([summary])))
        if position_rows:
            ime_position_text = f"{summary_cut}: " + "; ".join(f"{row['Indicador']} R$ {row[f'Posição {summary_cut}']} mm" for row in position_rows) + "."
    if main_dashboard is not None:
        for note in getattr(main_dashboard, "methodology_notes", ()) or ():
            all_document_sources.append(f"Metodologia IME: {note}")
        if getattr(main_dashboard, "methodology_notes", None):
            references.append({"Referência": "Metodologia IME", "Conteúdo": f"{len(main_dashboard.methodology_notes)} notas metodológicas do informe mensal; texto integral nas notas deste slide."})

    analysis: list[SlideSpec | None] = []
    appendix_tables: list[SlideSpec | None] = []
    for theme, title in THEMES:
        pairs, kpis = _panel_pairs(theme_pairs[theme])
        unit = "% " if False else ""
        for panels in pairs:
            analysis.append(slide(title, main_name, panels, layout="panels", section=title,
                                  source=_SOURCE if theme != "rentabilidade" else "CVM / Fundos.NET · rentabilidade por cota"))
        texts = [*kpis, *(return_texts if theme == "rentabilidade" else ())]
        tables = theme_tables[theme]
        if theme == "rentabilidade" and not single_fund:
            # Summaries across funds are the theme's body; a table longer than
            # a reading table goes to the appendix and the body says so.
            long = [table for table in tables if table_placement == "appendix" and isinstance(table, TableBlock) and len(table.frame) > BODY_TABLE_ROWS]
            pointers = [TextBlock(table.title, f"{len(table.frame)} séries" + (f" de {table.frame['Fundo'].nunique()} fundos" if "Fundo" in table.frame else "")
                                  + "; tabela completa no apêndice.") for table in long]
            analysis.append(slide(title, deck_entity, (*texts, *[t for t in tables if all(t is not other for other in long)], *pointers), section=title,
                                  source="CVM / Fundos.NET · rentabilidade por cota", notes=(CVM_RETURN_REINVESTMENT_NOTE,)))
            if long:
                appendix_tables.append(slide("Apêndice · séries", main_name, [replace(table, title=f"{title} · {table.title}") for table in long],
                                             appendix=True, section=SECTION_APPENDIX))
            continue
        if texts:
            analysis.append(slide(title, main_name, texts, section=title))
        if table_placement == "inline":
            analysis.append(slide(title, main_name, tables, section=title, notes=("Séries do tema; uma métrica aparece em um só lugar.",)))
        else:
            # One appendix: themes share slides and each table says its theme.
            appendix_tables.append(slide("Apêndice · séries", main_name, [replace(table, title=table.title if table.title.startswith(title) else f"{title} · {table.title}") for table in tables],
                                         appendix=True, section=SECTION_APPENDIX))

    # ---- Per-fund annex (multi-fund only): same themes, fund by fund.
    fund_annex: list[SlideSpec | None] = []
    if not single_fund and annex_mode == "full":
        for cnpj, name, monthly, monitor, cohorts in fund_scopes:
            tables, omitted = _theme_tables(monthly, monitor)
            coverage_notes.extend(f"{name}: {sentence}" for sentence in omitted)
            if not cohorts.empty:
                matrix = _cohort_matrix(cohorts, recent=False)
                tables["migracao"].append(TableBlock("Safras · %", matrix, {str(c): "percent:1" for c in matrix.columns[1:]},
                                                     (_raw_note(cohorts),), tuple(map(str, matrix.columns[1:]))))
            if research_outputs is not None:
                roll_source = _frame(getattr(research_outputs, "roll_seasonality", None))
                if not roll_source.empty and "cnpj" in roll_source:
                    own = roll_source[roll_source["cnpj"].map(_digits) == _digits(cnpj)]
                    roll = _roll_matrix(own)
                    if not roll.empty and any(_number(v) is not None for v in own["value_pct"]):
                        tables["migracao"].append(TableBlock("Sazonalidade da migração · %", roll, {str(c): "percent:1" for c in roll.columns[1:]},
                                                             (_raw_note(own),), tuple(map(str, roll.columns[1:]))))
            result = returns_by_fund.get(cnpj, {})
            tables["rentabilidade"].extend(result[k] for k in ("monthly_block", "rest_block") if k in result)
            # All themes of a fund in one flow: a small theme shares the page
            # with the next one instead of taking a slide of its own.
            fund_annex.append(slide(name, SECTION_FUNDS, [table for theme, _ in THEMES for table in tables[theme]],
                                    appendix=True, section=SECTION_FUNDS))
    elif not single_fund and annex_mode == "metrics":
        # By metric, not by fund: each page puts every fund side by side.
        metric_pages, constant = _fund_metric_charts(fund_scopes)
        coverage_notes.extend(constant)
        for title, charts in metric_pages:
            fund_annex.append(slide(f"Por fundo · {title}", deck_entity, charts, appendix=True, layout="grid", section=SECTION_FUNDS,
                                    notes=("Séries mensais completas de cada fundo na página da carteira e no Excel.",)))
    elif annex_comparison is not None:
        fund_annex.append(slide(SECTION_FUNDS, deck_entity, (annex_comparison,), appendix=True, section=SECTION_FUNDS,
                                notes=(f"Com mais de {FUND_ANNEX_MAX_FUNDS} fundos o anexo traz uma linha por fundo; "
                                       "as séries mensais de cada fundo ficam na página da carteira.",)))

    # ---- Documents: one sheet, then emissions and the complete matrices.
    # A summarized large basket keeps fund-level detail (emissions, full
    # clauses) in the notes: hundreds of rows are not read on slides.
    summarized = annex_mode == "summary" and not single_fund
    # Full clauses are read on demand, not presented: they go to the notes.
    clause_target = "notas do slide"
    documentary_slides: list[SlideSpec | None] = []
    position_rows = []
    issuance_tables = []
    for item in analytical_data:
        name = name_for(getattr(item, "cnpj", ""), short_fund_name(str(getattr(item, "name", "FIDC"))) or str(getattr(item, "name", "FIDC")))
        competence = _month(getattr(item, "competence", None))
        fields = (("Posição documental", competence), ("CNPJ", getattr(item, "cnpj", None)),
                  ("Classificação", getattr(item, "classification", None)),
                  ("PL documental", _format_brl_compact(float(item.pl_mm) * 1_000_000) if _number(getattr(item, "pl_mm", None)) is not None else None),
                  ("Direitos creditórios / PL", _br(float(item.receivables_pct_pl) * 100, 1) + "%" if _number(getattr(item, "receivables_pct_pl", None)) is not None else None),
                  ("Cotas sênior / PL", _br(float(item.senior_pct_pl) * 100, 1) + "%" if _number(getattr(item, "senior_pct_pl", None)) is not None else None),
                  ("Cotas subordinadas / PL", _br(float(item.subordinated_pct_pl) * 100, 1) + "%" if _number(getattr(item, "subordinated_pct_pl", None)) is not None else None),
                  ("Volume emitido identificado", _format_brl_compact(float(item.identified_issuance_volume_mm) * 1_000_000) if _number(getattr(item, "identified_issuance_volume_mm", None)) is not None else None),
                  ("Primeira emissão", getattr(item, "first_issuance", None)), ("Última emissão", getattr(item, "last_issuance", None)),
                  ("Subordinação mínima", getattr(item, "minimum_subordination", None)), ("RDB · status", getattr(item, "rdb_status", None)),
                  ("RDB · leitura", getattr(item, "rdb_finding", None)), ("RDB · fonte", getattr(item, "rdb_source", None)))
        found = {label: str(value) for label, value in fields if not _is_missing(value)}
        absent = [label for label, value in fields if _is_missing(value)]
        if absent:
            missing_fields.setdefault(name, []).extend(absent)
        position_rows.append((name, found, tuple(getattr(item, "validations", ()) or ())))
        all_document_sources.append(f"{name} · posição documental original: " + _raw_note(pd.DataFrame([{"Campo": label, "Valor original": value} for label, value in fields])))
        issuances = [{"Data": getattr(i, "date", None), "Série / classe": getattr(i, "series", None), "Tipo de cota": getattr(i, "quota_class", None),
                      "Volume (R$ mm)": getattr(i, "volume_mm", None), "Remuneração": getattr(i, "remuneration", None),
                      "Amortização": getattr(i, "amortization", None), "Fonte": getattr(i, "source", None)} for i in getattr(item, "issuances", ())]
        frame = pd.DataFrame(issuances)
        if not single_fund and not frame.empty:
            frame.insert(0, "Fundo", name)
        if not frame.empty:
            frame = frame.astype(object)
            # A row with no documented content (only its date and citation)
            # is an absence; the citation stays in the notes.
            content = [c for c in frame if c not in {"Fundo", "Data", "Fonte"}]
            documented = ~frame[content].apply(lambda column: column.map(_is_missing)).all(axis=1) if content else pd.Series(False, index=frame.index)
            frame = frame.loc[documented]
            frame = frame.drop(columns=[c for c in frame if frame[c].map(_is_missing).all()])
            if not frame.empty:
                frame = frame.map(lambda value: None if _is_missing(value) else value)
                frame = _shorten_long_cells(frame, name, clauses, target=clause_target)
                issuance_tables.append(TableBlock("Emissões documentadas", frame,
                                                  {"Volume (R$ mm)": "number:1"}, notes=tuple(str(v) for v in pd.DataFrame(issuances).get("Fonte", ())),
                                                  numeric_columns=tuple(c for c in ("Volume (R$ mm)",) if c in frame), compact=True))
            else:
                missing_fields.setdefault(name, []).append("Emissões documentadas")
    # Documentary matrices first: the sheet reuses their short, curated fields.
    matrix_names = {legal: canonical.get(key, legal) for key, legal in legal_names.items()}
    matrix_blocks: list[Any] = []
    matrix_notes: list[str] = []
    curated_short: dict[str, dict[str, str]] = {}
    for page in documentary_pages:
        frame = _frame(getattr(page, "frame", None))
        for column in frame.columns[1:]:
            frame[column] = frame[column].map(lambda value: "Não localizado" if _is_missing(document_comparison_value(value)) else document_comparison_value(value))
        if single_fund:
            # The matrix header names the fund as curated; the deck uses one name.
            short_legal = {short_fund_name(legal) for legal in legal_names.values()}
            frame = frame.rename(columns={c: deck_entity for c in frame.columns[1:] if c in short_legal or c in matrix_names})
        page_notes = tuple(public_document_text(note) for note in getattr(page, "notes", ()) if public_document_text(note))
        page_sources = tuple(public_document_text(source) for source in getattr(page, "sources", ()) if public_document_text(source))
        theme = str(getattr(page, "title", "Documentos"))
        if not frame.empty:
            for _, row in frame.iterrows():
                for column in frame.columns[1:]:
                    value = row[column]
                    if isinstance(value, str) and not _is_missing(value) and value != "Não localizado" and len(value) <= 120:
                        curated_short.setdefault(str(column), {})[str(row.iloc[0])] = value
            for block in _document_blocks(theme, frame):
                if isinstance(block, TextBlock):
                    # "Não localizados" moves to the single coverage slide.
                    for sentence in re.split(r"(?<=\.)\s+(?=Não localizados)", block.text):
                        match = re.match(r"Não localizados para (.+): (.+)\.$", sentence.strip())
                        if match:
                            missing_fields.setdefault(match.group(1), []).extend(f"{theme}: {item}" for item in match.group(2).split("; "))
                        else:
                            coverage_notes.append(sentence)
                else:
                    frame = _shorten_long_cells(block.frame, "", clauses, target=clause_target)
                    if single_fund:
                        # Peer columns are a reference: where a peer has
                        # nothing, the cell stays quiet instead of repeating
                        # "Não localizado".
                        for column in frame.columns[1:]:
                            if column != deck_entity:
                                frame[column] = frame[column].map(lambda value: "—" if value == "Não localizado" else value)
                    matrix_blocks.append(replace(block, frame=frame, compact=True))
            matrix_notes.extend((*page_notes, *page_sources, _raw_note(_frame(getattr(page, "frame", None)))))
            coverage_notes.extend(note for note in page_notes if "cobertura" in note.casefold() or "inválid" in note.casefold())
        for source in page_sources:
            all_document_sources.append(source)
            urls = tuple(dict.fromkeys(value.rstrip(".,)") for value in re.findall(r"https?://[^\s;|]+", source)))
            ids = tuple(dict.fromkeys(re.findall(r"(?i)\b(?:ID|documento|CVM)\s*[:#]?\s*(?:n[º°.]?\s*)?\d[\w./-]*", source)))
            for reference in (*ids, *urls):
                themes = documentary_references.setdefault(reference, [])
                if theme not in themes:
                    themes.append(theme)
            if not (urls or ids):
                documentary_themes_without_id.append(theme)

    def subordination_summary(name: str) -> str | None:
        """Known structure only: the curated 'Subordinação mínima da <classe>'
        fields. Free legal text is never paraphrased."""
        fields = curated_short.get(name, {})
        parts = [f"{label.split(' da ', 1)[1].capitalize()}: {value}" for label, value in fields.items()
                 if label.casefold().startswith("subordinação mínima da ")]
        return "; ".join(parts) or None

    sheet_blocks = []
    if single_fund and position_rows:
        name, found, validations = position_rows[0]
        summary_text = subordination_summary(name)
        if summary_text and "Subordinação mínima" in found:
            found = {**found, "Subordinação mínima": summary_text + (" · cláusula integral nas notas" if len(found["Subordinação mínima"]) > _LONG_CELL else "")}
            if len(position_rows[0][1]["Subordinação mínima"]) > _LONG_CELL:
                clauses.append({"Ref.": f"C{len(clauses) + 1}", "Campo": f"{name} · Subordinação mínima", "Cláusula integral": position_rows[0][1]["Subordinação mínima"]})
        rows = [{"Campo": label, "Informação": value} for label, value in found.items() if label != "CNPJ"]
        if rows:
            frame = _shorten_long_cells(pd.DataFrame(rows), name, clauses, target=clause_target)
            sheet_blocks.append(TableBlock("Ficha do fundo", frame, notes=validations, compact=True))
    elif position_rows:
        columns = ("Posição documental", "PL documental", "Direitos creditórios / PL", "Cotas sênior / PL", "Cotas subordinadas / PL", "Subordinação mínima")
        frame = pd.DataFrame([{"Fundo": name, **{c: (subordination_summary(name) or found.get(c, "N/D")) if c == "Subordinação mínima" else found.get(c, "N/D") for c in columns}}
                              for name, found, _ in position_rows])
        frame = frame.drop(columns=[c for c in columns if frame[c].eq("N/D").all()])
        frame = _shorten_long_cells(frame, "", clauses, target=clause_target)
        sheet_blocks.append(TableBlock("Ficha dos fundos", frame, notes=tuple(v for _, _, vs in position_rows for v in vs)))
    if len(issuance_tables) > 1:
        combined = pd.concat([block.frame for block in issuance_tables], ignore_index=True, sort=False)
        combined = combined.drop(columns=[c for c in combined.columns[1:] if combined[c].map(_is_missing).all()])
        issuance_tables = [replace(issuance_tables[0], frame=combined.astype(object),
                                   notes=tuple(note for block in issuance_tables for note in block.notes),
                                   numeric_columns=tuple(c for c in ("Volume (R$ mm)",) if c in combined))]
    sheet_notes: list[str] = ["Cada posição documental conserva seu corte próprio."]
    if summarized and issuance_tables:
        frame = issuance_tables[0].frame
        funds_with = frame["Fundo"].nunique() if "Fundo" in frame else 1
        sheet_notes.append("Emissões documentadas: " + _raw_note(frame))
        issuance_tables = [TextBlock("Emissões documentadas", f"{len(frame)} emissões de {funds_with} fundos; tabela completa nas notas deste slide.")]
    if clauses:
        if single_fund:
            # One fund: the field name alone; the fund is in the slide context.
            clauses = [{**clause, "Campo": clause["Campo"].removeprefix(f"{deck_entity} · ")} for clause in clauses]
        clause_notes = [f"{clause['Ref.']} · {clause['Campo']}: {clause['Cláusula integral']}" for clause in clauses]
        clauses = []
    else:
        clause_notes = []
    # One fund: the documentary sheet sits beside the snapshot, so the
    # position and the contractual minimum are read together.
    sheet_beside_snapshot = single_fund and bool(sheet_blocks) and head[0] is not None
    if sheet_beside_snapshot:
        head[0] = replace(head[0], blocks=(*head[0].blocks, *(replace(block, compact=False) for block in sheet_blocks)), layout="panels",
                          source=f"{head[0].source} · posição documental Fundos.NET/B3",
                          notes=(*head[0].notes, *sheet_notes, *clause_notes))
    # Sheet, emissions and matrices form one documentary flow.
    documentary_slides.append(slide("Ficha documental", deck_entity, (*(() if sheet_beside_snapshot else sheet_blocks), *issuance_tables),
                                    source="CVM / Fundos.NET · posição documental · Fundos.NET/B3 · emissões",
                                    section=SECTION_DOCUMENTS, notes=(*sheet_notes, *clause_notes)))
    documentary_slides.append(slide("Documentos completos", deck_entity, _with_sections(matrix_blocks), source="Fundos.NET/B3",
                                    section=SECTION_DOCUMENTS, notes=tuple(dict.fromkeys((*matrix_notes, *clause_notes)))))

    # ---- References and coverage: one table, compacted by subject. Detail
    # (fund list, citations, methodology, repetitions) stays in the notes.
    context_rows = []
    for line in reference_lines:
        label, _, content = str(line).partition(": ")
        if label in _ON_COVER or not content:
            # The cover carries periods, position and consultation time; the
            # footers carry the source. The full lines stay in the notes.
            all_document_sources.append(str(line))
            continue
        context_rows.append({"Referência": label if content else "Contexto", "Conteúdo": content or label})
    by_label = {row["Referência"]: row for row in context_rows}
    if "Posição comum" in by_label and "Última competência observada" in by_label:
        last = by_label["Última competência observada"]
        by_label["Posição comum"]["Referência"] = "Posição comum · última observada"
        if last["Conteúdo"] != by_label["Posição comum"]["Conteúdo"]:
            by_label["Posição comum"]["Conteúdo"] += f" · {last['Conteúdo']}"
        context_rows.remove(last)
    known = {row["Referência"] for row in context_rows}
    equivalents = {"Período visual": "Histórico selecionado", "Período solicitado": "Consulta solicitada", "Fonte quantitativa": "Fonte mensal"}
    fund_list = [f"{name_for(cnpj, name)} · {name} · CNPJ {cnpj}" for cnpj, name in map(_fund_identity, funds)]
    base_rows = [{"Referência": "Fundos", "Conteúdo": "; ".join(f"{name_for(c, n)} · CNPJ {c}" for c, n in map(_fund_identity, funds))
                  if len(fund_list) <= 4 else f"{len(fund_list)} fundos; nomes legais e CNPJs nas notas."}]
    all_document_sources.extend((f"Período visual: {period}", "Fonte quantitativa: CVM / Fundos.NET · informes mensais; fórmulas, denominadores e proxies do app.",
                                 f"Rentabilidade: {CVM_RETURN_REINVESTMENT_NOTE}"))
    for label, content in (("Leitura documental", str(getattr(documentary_manifest, "generated_at", None) or "não disponível")),):
        if label not in known and equivalents.get(label) not in known:
            base_rows.append({"Referência": label, "Conteúdo": content})
    sources_summary = []
    if documentary_references:
        sources_summary.append(f"{len(documentary_references)} documentos citados nas matrizes")
        all_document_sources.extend(f"{reference}: {'; '.join(themes)}" for reference, themes in documentary_references.items())
    if documentary_themes_without_id:
        sources_summary.append("fontes sem identificador em " + ", ".join(dict.fromkeys(documentary_themes_without_id)))
    if sources_summary:
        base_rows.append({"Referência": "Fontes documentais", "Conteúdo": "; ".join(sources_summary) + ". Citações completas nas notas."})
    if ime_position_text:
        base_rows.append({"Referência": "Posição IME", "Conteúdo": ime_position_text})
    methodology_parts = [row["Conteúdo"] for row in references if row["Referência"] in {"Metodologia IME", "Migração e safras"}]
    if methodology_parts:
        base_rows.append({"Referência": "Metodologia", "Conteúdo": " ".join(methodology_parts)})
    # Warnings name funds by legal name or CNPJ; the deck uses one name.
    aliases = sorted(((legal, canonical.get(key, legal)) for key, legal in legal_names.items()), key=lambda item: -len(item[0]))
    aliases += [(key, canonical.get(key, key)) for key in legal_names]

    def public_names(text: str) -> str:
        for alias, name in aliases:
            if alias:
                text = re.sub(re.escape(alias), name, text, flags=re.IGNORECASE)
        return text

    def grouped_by_message(items: Iterable[str]) -> str:
        """'Fund: message' items become 'message: fund A, fund B'."""
        groups: dict[str, list[str]] = {}
        for item in items:
            entity, sep, message = item.partition(": ")
            key, who = (message.rstrip(". "), entity) if sep and len(entity) <= 80 else (item.rstrip(". "), "")
            groups.setdefault(key, [])
            if who and who not in groups[key]:
                groups[key].append(who)
        parts = []
        for message, who in groups.items():
            if not who:
                parts.append(message)
            elif len(who) <= 4:
                parts.append(f"{message}: {', '.join(who)}")
            else:
                parts.append(f"{message}: {len(who)} fundos (lista nas notas)")
        return "; ".join(parts) + "."

    for obj, label in ((monitor_outputs, "Monitoramento"), (research_outputs, "Research")):
        warnings_list = [public_names(str(w)) for w in getattr(obj, "warnings", ()) or ()]
        if warnings_list:
            all_document_sources.extend(f"Ressalva ({label}): {w}" for w in warnings_list)
            base_rows.append({"Referência": f"Ressalvas · {label}", "Conteúdo": grouped_by_message(warnings_list)})
    # Base warnings (one record per fund and month) become one line per
    # warning, with the months compressed; the records stay in the notes.
    warnings_frame = _frame(getattr(outputs, "warnings_df", None))
    if not warnings_frame.empty and "warning" in warnings_frame:
        all_document_sources.append("Avisos da base: " + _raw_note(warnings_frame))
        by_warning: dict[str, dict[str, list[str]]] = {}
        for _, record in warnings_frame.iterrows():
            cnpj = _digits(record.get("cnpj", ""))
            if not cnpj or not cnpj.isdigit():
                if not single_fund and str(record.get("cnpj", "")).strip().casefold() == "consolidado":
                    who = "Consolidado"
                else:
                    continue  # a single fund's consolidated copy repeats the fund
            else:
                who = canonical.get(cnpj, public_names(str(record.get("scope_name") or cnpj)))
            for message in str(record.get("warning", "")).split(";"):
                message = message.strip().rstrip(".")
                if message:
                    by_warning.setdefault(message, {}).setdefault(who, []).append(_month(record.get("competencia")))
        for message, entities in by_warning.items():
            def months_text(months: list[str]) -> str:
                months = sorted(dict.fromkeys(months), key=_month_key)
                if len(months) <= 3:
                    return ", ".join(months)
                return f"{len(months)} competências, {months[0]}–{months[-1]}"
            if len(entities) <= 4:
                content = "; ".join(f"{who}: {months_text(months)}" for who, months in entities.items())
            else:
                content = f"{len(entities)} fundos; competências nas notas"
            base_rows.append({"Referência": f"Aviso da base · {message}", "Conteúdo": content + "."})
    repetitions = list(dict.fromkeys(coverage_notes))
    if repetitions:
        all_document_sources.append(f"Repetições e observações ({len(repetitions)}); séries iguais em fontes diferentes exibidas uma vez:")
        all_document_sources.extend(repetitions)
    portfolio_entities = {*canonical.values(), deck_entity}
    own = {entity: list(dict.fromkeys(items)) for entity, items in missing_fields.items() if entity in portfolio_entities}
    peers = {entity: list(dict.fromkeys(items)) for entity, items in missing_fields.items() if entity not in portfolio_entities}
    for entity, items in {**own, **peers}.items():
        all_document_sources.append(f"Não localizados · {entity}: " + "; ".join(items))
    if len(own) <= 6:
        for entity, items in own.items():
            # Grouped by theme: "Recebíveis: Tipo de fundo, Recebível; ..."
            grouped: dict[str, list[str]] = {}
            for item in items:
                theme, _, field = item.partition(": ")
                grouped.setdefault(theme if field else "", []).append(field or theme)
            content = "; ".join(f"{theme}: {', '.join(fields)}" if theme else ", ".join(fields) for theme, fields in grouped.items())
            base_rows.append({"Referência": f"Não localizados · {entity}", "Conteúdo": content + ("" if content.endswith(".") else ".")})
    else:
        # Many funds: one line by field, with the number of funds.
        counts: dict[str, int] = {}
        for items in own.values():
            for item in items:
                counts[item] = counts.get(item, 0) + 1
        content = "; ".join(f"{item} ({count})" for item, count in sorted(counts.items(), key=lambda pair: -pair[1]))
        base_rows.append({"Referência": f"Não localizados · {len(own)} fundos", "Conteúdo": f"{content}. Número de fundos entre parênteses; lista nas notas."})
    if without_data:
        names = [entry.split(" · CNPJ ")[0] for entry in without_data]
        all_document_sources.append("Fundos sem informe mensal no período: " + "; ".join(without_data))
        base_rows.append({"Referência": "Sem informe mensal",
                          "Conteúdo": (", ".join(names) if len(names) <= 6 else f"{len(names)} fundos; lista nas notas")
                          + f". Fora do consolidado e das comparações ({len(funds) - len(names)} de {len(funds)} fundos com dados)."})
    if annex_comparison is not None:
        base_rows.append({"Referência": SECTION_FUNDS, "Conteúdo": f"{len(fund_scopes)} fundos: uma linha por fundo (acima de {FUND_ANNEX_MAX_FUNDS} fundos); "
                          "séries mensais de cada fundo na página da carteira."})
    for warning in export_warnings:
        base_rows.append({"Referência": "Parte indisponível", "Conteúdo": public_document_text(warning)})
    quality_rows, quality_notes = [], []
    for frame, origin in ((main_monthly, "Base mensal"), (main_monitor, "Monitoramento")):
        quality = _quality_block(frame, origin)
        if quality is None:
            continue
        quality_notes.extend(quality.notes)
        for _, row in quality.frame.iterrows():
            entry = {"Referência": f"Qualidade · {row['Indicador']}", "Conteúdo": f"{row['Estado por competência']} ({origin.lower()})."}
            if not any(existing["Referência"] == entry["Referência"] for existing in quality_rows):
                quality_rows.append(entry)
    reference_frame = pd.DataFrame([*context_rows, *base_rows, *quality_rows]).drop_duplicates(ignore_index=True)
    coverage_blocks: list[Any] = [TableBlock("Fontes, cortes e cobertura", reference_frame, compact=True,
                                             notes=(*fund_list, *(f"{r['Referência']}: {r['Conteúdo']}" for r in references),
                                                    *dict.fromkeys(all_document_sources), *quality_notes))]
    coverage = [slide(SECTION_COVERAGE, deck_entity, coverage_blocks, source="CVM / Fundos.NET / B3", appendix=True, section=SECTION_COVERAGE)]

    if include_conclusions:
        from services.somatorio_fidcs_ppt_export import _build_synthesis_sections
        sections = _build_synthesis_sections(
            consolidated_monitor=main_monitor, consolidated_monthly=main_monthly,
            fund_monitor_map=getattr(monitor_outputs, "fund_monitor", {}),
            fund_monthly_map=getattr(outputs, "fund_monthly", {}),
        )
        labels = {"attention": "Pontos de atenção", "highlights": "Destaques"}
        generic = {
            "Sem alerta automático adicional com a base disponível.",
            "Verificar manualmente eventos regulatórios relevantes antes de uso externo.",
            "Manter leitura por fundo para identificar concentração de risco.",
            "Deck gerado com gráficos nativos e editáveis no PowerPoint.",
            "Data-base, fonte e paginação preservadas automaticamente.",
            "Indicadores percentuais recalculados a partir das bases consolidadas.",
        }
        blocks = tuple(TextBlock(labels.get(str(title), str(title)), "\n".join(str(point) for point in points if str(point) not in generic))
                       for title, points in sections.items() if any(str(point) not in generic for point in points)) if isinstance(sections, dict) else ()
        source_summary = tuple(f"Síntese original · {title}: " + " | ".join(map(str, points)) for title, points in sections.items())
        if blocks:
            head.append(SlideSpec("Conclusões", f"{deck_entity} · {period}", blocks, _SOURCE, notes=(*source_summary, *identity_notes)))

    # Analysis first (themes, then fund by fund); the material read on demand
    # (series, documents, references) closes the deck, in that order.
    ordered = [*head, *analysis, *fund_annex, *appendix_tables, *documentary_slides, *coverage]
    metadata = (f"{len(funds)} fundo{'s' if len(funds) != 1 else ''} · {period}",
                f"Período solicitado: {requested_period_label or period}",
                "Consulta: " + now.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"))
    return DeckSpec(portfolio_name, f"Carteira · {period}", metadata, tuple(page for page in ordered if page is not None))


__all__ = ["TableBlock", "ChartSeries", "ChartBlock", "TextBlock", "SlideSpec", "DeckSpec", "THEMES",
           "TABLE_PLACEMENTS", "build_portfolio_deck_spec"]
