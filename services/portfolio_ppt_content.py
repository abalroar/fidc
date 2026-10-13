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
    RETURN_TRAILING_12M_COLUMN,
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
    snapshot_history: dict[str, tuple[float | None, ...]] = field(default_factory=dict)
    cell_colors: dict[tuple[int, str], str] = field(default_factory=dict)


@dataclass(frozen=True)
class ChartSeries:
    key: str
    label: str
    values: tuple[float | None, ...]
    unit: str = "%"
    decimals: int = 1


@dataclass(frozen=True)
class ChartBlock:
    title: str
    categories: tuple[str, ...]
    series: tuple[ChartSeries, ...]
    unit: str = "%"
    notes: tuple[str, ...] = ()


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
    return isinstance(value, str) and value.strip().casefold() in {"", "-", "—", "n/d", "nan", "none", "não localizado"}


def _text(value: Any) -> str:
    return "N/D" if _is_missing(value) else str(value)


def _br(value: Any, decimals: int = 1) -> str:
    number = _number(value)
    return "N/D" if number is None else f"{number:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


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
    meanings = {"reported_zero": "Zero informado", "not_reported": "Não reportado", "missing_field": "Campo ausente", "reported": "Informado", "reported_value": "Valor informado", "ok": "Válido", "calculated": "Calculado", "calculado": "Calculado", "missing": "Ausente", "partial": "Cobertura parcial", "incomplete": "Incompleto"}
    rows, notes = [], []
    for column in state_columns:
        label = str(column)
        for suffix in ("_source_status", "_status", "_data_quality", "_quality", "_source", "_fonte"):
            if label.endswith(suffix):
                label = label[: -len(suffix)]
        label = _ALIASES.get(label, label.replace("_", " "))
        values = source[column].map(_text).tolist()
        readable = [meanings.get(value, value) for value in values]
        # Repeating the same status in every month adds no information. Its
        # exact per-month association stays in notes and in the source record.
        if len(set(values)) > 1:
            rows.append({"Indicador": label, **dict(zip(labels, readable, strict=True))})
        notes.append(f"{origin} · {column}: " + "; ".join(f"{month}={value}" for month, value in zip(labels, values, strict=True)))
    if not rows:
        return None
    return TableBlock(f"Qualidade e cobertura · {origin}", pd.DataFrame(rows), notes=tuple(notes))


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
    rows, history, colors, notes = [], {}, {}, []
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
        rows.append({"Indicador": label, "Valor": display, "Var. mensal": monthly_display, "Var. anual": annual_display, "Evolução": ""})
        history[label] = tuple(_number(v) for v in source[column])
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
        rows.append({"Indicador": label, "Valor": _br(value, 1) + ("%" if value is not None else ""), "Var. mensal": _br(delta, 1) + " p.p." if delta is not None else "N/D", "Var. anual": "N/D", "Evolução": ""})
        if "cobertura_pct" in defaults and same_cut:
            history[label] = tuple(_number(v) for v in defaults["cobertura_pct"])
        if delta is not None and round(delta, 1) != 0:
            colors[(row_index, "Var. mensal")] = "good" if delta > 0 else "bad"
        notes.append(f"Cobertura IME: posição original {summary_cut}; histórico selecionado termina em {history_cut}; provisão / vencidos; denominador diferente do NPL ex-360.")
        if not same_cut:
            notes.append("Posição do resumo e último ponto histórico diferentes: comparação mensal indisponível (N/D), sem combinar cortes. A série histórica selecionada permanece completa no anexo.")
    notes.append("Variações anuais só aparecem quando já fornecidas pela base. N/D significa comparação indisponível. Mudanças de percentuais são p.p.; crescimento de carteira usa a variação já calculada.")
    return TableBlock(name, pd.DataFrame(rows, columns=["Indicador", "Valor", "Var. mensal", "Var. anual", "Evolução"]), notes=tuple(notes), numeric_columns=("Valor", "Var. mensal", "Var. anual"), snapshot_history=history, cell_colors=colors)


def _fund_comparison(scopes: list[tuple[str, str, pd.DataFrame, pd.DataFrame, pd.DataFrame]]) -> TableBlock | None:
    funds = [scope for scope in scopes if scope[0] != "consolidado"]
    if len(funds) < 2:
        return None
    specs = (("pl_total", "PL total (R$ mm)"), ("carteira_ex360", "Carteira ex-360 (R$ mm)"),
             ("subordinacao_total_ex360_pct", "Subordinação ex-360 (%)"), ("npl_over90_ex360_pct", "NPL > 90d ex-360 (%)"),
             ("pdd_npl_over90_ex360_pct", "Cobertura PDD / NPL (%)"), ("duration_months", "Duration (meses)"))
    rows = []
    notes = []
    for column, label in specs:
        row = {"Indicador": label}
        for cnpj, name, monthly, monitor, _ in funds:
            source = _ordered(monitor if column in monitor else monthly)
            value = _number(source.iloc[-1].get(column)) if not source.empty else None
            row[name] = _br(value / 1_000_000, 1) if value is not None and _unit(column) == "R$" else _br(value, 1)
            if column == "pdd_npl_over90_ex360_pct" and value is None:
                denominator_source = _ordered(monitor if "npl_over90_ex360" in monitor else monthly)
                denominator = _number(denominator_source.iloc[-1].get("npl_over90_ex360")) if not denominator_source.empty else None
                if denominator == 0:
                    row[name] = "N/A · NPL zero"
                    notes.append(f"{name} · CNPJ {cnpj}: cobertura PDD / NPL > 90d ex-360 não aplicável; NPL é zero na posição. N/D continua reservado ao dado indisponível.")
            if not source.empty:
                notes.append(f"{name} · CNPJ {cnpj}: posição {_month(source.iloc[-1].get('competencia', source.iloc[-1].get('competencia_dt')))}.")
        rows.append(row)
    return TableBlock("Comparação entre fundos", pd.DataFrame(rows), numeric_columns=tuple(scope[1] for scope in funds), notes=tuple(dict.fromkeys(notes)))


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


def build_portfolio_deck_spec(
    *, portfolio_name: str, funds: Iterable[Any], outputs: Any, monitor_outputs: Any,
    research_outputs: Any = None, dashboard: Any = None,
    dashboard_summary_competencia: str | None = None,
    documentary_pages: Iterable[Any] = (), documentary_manifest: Any = None,
    analytical_data: Iterable[Any] = (), requested_period_label: str | None = None,
    monthly_cdi_rates_by_fund: Mapping[str, Iterable[Any]] | None = None,
    benchmark_spreads_by_fund: Mapping[str, Mapping[str, float]] | None = None,
    include_conclusions: bool = False, generated_at: datetime | None = None,
) -> DeckSpec:
    """Return one ordered content plan, preserving all selected source values."""
    funds = tuple(funds)
    documentary_pages = tuple(documentary_pages)
    analytical_data = tuple(analytical_data)
    scopes = _scope_frames(funds, outputs, monitor_outputs)
    now = generated_at or datetime.now(ZoneInfo("America/Sao_Paulo"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
    period = _period(_frame(getattr(outputs, "consolidated_monthly", None)))
    if period == "período N/D":
        period = _period(scopes[0][2])
    body: list[SlideSpec] = []
    annex: list[SlideSpec] = []
    references: list[dict[str, str]] = []
    documentary_body: list[pd.DataFrame] = []
    analytic_body: list[dict[str, str]] = []
    all_document_sources: list[str] = []
    documentary_references: dict[str, list[str]] = {}
    identity_notes = tuple(f"{name} · CNPJ {cnpj}" for cnpj, name in map(_fund_identity, funds))

    def add(title: str, entity: str, blocks: Iterable[Any], *, source: str = _SOURCE, notes: Iterable[str] = (), appendix: bool = False, unit: str = "") -> None:
        blocks = tuple(block for block in blocks if block is not None)
        if not blocks:
            return
        context = " · ".join(part for part in (entity, unit, period) if part)
        spec = SlideSpec(title, context, blocks, source, (*tuple(notes), *identity_notes), "appendix" if appendix else "content")
        (annex if appendix else body).append(spec)

    add("Snapshot", portfolio_name, (_snapshot(scopes, dashboard, dashboard_summary_competencia), _fund_comparison(scopes)))

    for cnpj, name, monthly, monitor, cohorts in scopes:
        # Existing monthly and monitor representations remain separate when they
        # differ. Charts prefer the monitor that supplied the original credit deck.
        credit = monitor if not monitor.empty else monthly
        main_scope = len(scopes) == 1 or cnpj == "consolidado"
        if main_scope and _varies(credit, ("npl_over30_ex360_pct", "npl_over90_ex360_pct", "pdd_npl_over90_ex360_pct")):
            add("Atraso e provisão", name, (
            _chart("NPL / carteira ex-360", credit, ("npl_over30_ex360_pct", "npl_over90_ex360_pct"), key_prefix=cnpj,
                   notes=("Denominador: carteira bruta ex-360; vencidos acima de 360 dias excluídos.",)),
            _chart("Cobertura PDD / NPL > 90d ex-360", credit, ("pdd_npl_over90_ex360_pct",), key_prefix=cnpj),
            ), unit="%")
        balance_source = monthly if "carteira_ex360" in monthly else credit
        structure_columns = [column for column in ("pl_total", "carteira_ex360") if column in balance_source]
        if main_scope and (_varies(balance_source, structure_columns) or _varies(monthly, ("subordinacao_total_ex360_pct",))):
            add("Estrutura", name, (
                _chart("PL e carteira", balance_source, structure_columns, key_prefix=cnpj, unit="R$"),
                _chart("Subordinação ex-360", monthly, ("subordinacao_total_ex360_pct",), key_prefix=cnpj),
            ), notes=("PL total e carteira são estoques distintos; as composições de PL por cota estão completas no anexo.",))
        migration = _monthly_tables("Migração · roll rates", credit, _ROLL_COLUMNS,
                                    notes=("Proxies: faixa de atraso atual / carteira a vencer M-3, M-4, M-5 ou M-6; regras mantidas.",))
        cohort_view = _cohort_matrix(cohorts, recent=True)
        if not cohort_view.empty:
            migration.append(TableBlock("Safras recentes · %", cohort_view, {str(column): "percent:1" for column in cohort_view.columns[1:]}, numeric_columns=tuple(map(str, cohort_view.columns[1:]))))
        if main_scope and (_varies(credit, _ROLL_COLUMNS) or _varies(cohorts, ("valor_pct", "value_pct"))):
            add("Migração e safras", name, migration)
        # Source-specific appendices preserve numbers independently of the
        # thematic charts, including constant, zero, missing and negative values.
        seen_monthly = _ordered(monthly)
        for label, frame in (("Base mensal", monthly), ("Monitoramento", monitor)):
            columns = list(_MONTHLY_COLUMNS)
            if label == "Monitoramento" and not seen_monthly.empty:
                ordered_monitor = _ordered(frame)
                identical_dates = ("competencia" in ordered_monitor and "competencia" in seen_monthly
                                   and ordered_monitor["competencia"].tolist() == seen_monthly["competencia"].tolist())
                if identical_dates:
                    columns = [column for column in columns if column not in seen_monthly or column not in ordered_monitor
                               or not ((ordered_monitor[column].eq(seen_monthly[column]) | (ordered_monitor[column].isna() & seen_monthly[column].isna())).all())]
            for table in _monthly_tables(label, frame, columns):
                table = replace(table, notes=(*table.notes, _raw_note(frame)))
                add("Séries mensais", name, (table,), appendix=True, notes=(f"Origem: {label}. Valores do período selecionado; sem agregação adicional.",))
            quality = _quality_block(frame, label)
            if label == "Monitoramento" and quality is not None:
                monthly_quality = _quality_block(monthly, "Base mensal")
                if monthly_quality is not None and monthly_quality.frame.equals(quality.frame):
                    quality = None
            if quality is not None:
                add("Qualidade e cobertura", name, (quality,), appendix=True)
        if not cohorts.empty:
            complete_cohorts = _cohort_matrix(cohorts, recent=False)
            add("Safras completas", name, (TableBlock("Safras · %", complete_cohorts,
                {str(column): "percent:1" for column in complete_cohorts.columns[1:]}, (_raw_note(cohorts),), tuple(map(str, complete_cohorts.columns[1:]))),), appendix=True,
                notes=("Safra proxy, numerador, denominador e estados originais preservados.",))
        if cnpj != "consolidado":
            history = _frame(_lookup(getattr(outputs, "fund_return_history", {}), cnpj))
            history_dates = [value for value in history.get("competencia", pd.Series(dtype="object")).map(_date) if value is not None]
            visual_frame = monthly if not monthly.empty else _frame(getattr(outputs, "consolidated_monthly", None))
            visual_dates = [value for value in visual_frame.get("competencia", pd.Series(dtype="object")).map(_date) if value is not None]
            summary_dates = [value for value in _frame(_lookup(getattr(outputs, "fund_return_summary", {}), cnpj)).get("latest_competencia", pd.Series(dtype="object")).map(_date) if value is not None]
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
            if visual_dates and not matrix.empty:
                visible_months = {_month(value) for value in visual_dates}
                visible_columns = [column for column in matrix if not (len(str(column)) == 6 and str(column)[3:4] == "/") or str(column) in visible_months]
                matrix = matrix.loc[:, visible_columns].copy()
            if not matrix.empty:
                summary_columns = [column for column in (RETURN_SERIES_COLUMN, RETURN_TRAILING_12M_COLUMN, RETURN_YTD_COLUMN) if column in matrix]
                returns = TableBlock("Retorno por série · %", matrix[summary_columns].copy(), {str(column): "percent:2" for column in summary_columns[1:]}, notes=(CVM_RETURN_REINVESTMENT_NOTE,), numeric_columns=tuple(map(str, summary_columns[1:])))
                return_columns = [column for column in matrix if str(column) in (RETURN_TRAILING_12M_COLUMN, RETURN_YTD_COLUMN) or (len(str(column)) == 6 and str(column)[3:4] == "/")]
                informed = [number for column in return_columns for value in matrix[column] if (number := _number(value)) is not None]
                if informed and all(value == 0 for value in informed):
                    returns_block: TableBlock | TextBlock = TextBlock("Retorno por cota", "Rentabilidade de 0,00% nas observações informadas. Séries, competências, lacunas, CDI e spreads estão completos no anexo.")
                elif not any(_number(value) is not None for column in summary_columns[1:] for value in matrix[column]):
                    returns_block = TextBlock("Acumulados", "Acumulados de 12 meses e YTD indisponíveis. Os retornos mensais e seus estados estão completos no anexo.")
                else:
                    returns_block = returns
                add("Rentabilidade", name, (returns_block,), source="CVM / Fundos.NET · rentabilidade por cota", notes=(CVM_RETURN_REINVESTMENT_NOTE,))
                formats = {str(column): "number:0" if "bps" in str(column) else "percent:2" for column in matrix.columns[1:]}
                add("Rentabilidade completa", name, (TableBlock("Meses, acumulados, CDI e spreads", matrix, formats, (CVM_RETURN_REINVESTMENT_NOTE,), tuple(map(str, matrix.columns[1:]))),), appendix=True,
                    notes=(f"CDI: {matrix.attrs.get('cdi_source', 'benchmark não solicitado')}", f"CDI sem competência: {matrix.attrs.get('cdi_missing_competencias', ())}"))
            for label, frame in (("Retorno mensal original", history), ("Retorno acumulado original", _frame(_lookup(getattr(outputs, "fund_return_summary", {}), cnpj)))):
                if not frame.empty:
                    references.append({"Referência": f"{name} · {label}", "Conteúdo": "Identidades de cota, competências e estados completos nas notas da rentabilidade."})
                    if not matrix.empty:
                        last = annex[-1]
                        annex[-1] = replace(last, notes=(*last.notes,
                            f"{label}: buffer recebido do produtor para os acumulados. Competências fora do recorte visual aparecem apenas nesta memória de cálculo; a matriz mensal exibe a seleção atual.",
                            _raw_note(frame)))

    if dashboard is not None:
        entity = portfolio_name + " · IME"
        defaults = _frame(getattr(dashboard, "default_history_df", None))
        aging = _aging_matrix(_frame(getattr(dashboard, "default_aging_history_df", None)), "percentual_inadimplencia")
        coverage = _chart("Cobertura provisão / vencidos", defaults, ("cobertura_pct",), key_prefix="ime")
        if isinstance(coverage, ChartBlock):
            coverage = replace(coverage, series=(*coverage.series, ChartSeries("ime:coverage_parity", "Paridade", tuple(100.0 for _ in coverage.categories))),
                               notes=(*coverage.notes, "Referência de paridade: 100%."))
        credit_blocks = [_chart("Inadimplência e provisão / DCs", defaults, ("inadimplencia_pct", "provisao_pct_direitos"), key_prefix="ime"), coverage]
        if not aging.empty:
            visible_aging = aging.loc[~aging.iloc[:, 0].astype(str).str.contains("361|721|1080")].copy()
            selected_columns = [visible_aging.columns[0], *visible_aging.columns[-12:]] if len(visible_aging.columns) > 13 else list(visible_aging.columns)
            visible_aging = visible_aging[selected_columns]
            credit_blocks.append(TableBlock("Aging até 360d · % dos vencidos · últimos 12 meses", visible_aging,
                {str(column): "percent:1" for column in visible_aging.columns[1:]},
                notes=("Faixas acima de 360 dias e competências anteriores preservadas separadamente no anexo.",),
                numeric_columns=tuple(map(str, visible_aging.columns[1:]))))
        aging_varies = any(_varies(pd.DataFrame({"value": row.iloc[1:].tolist()}), ("value",)) for _, row in aging.iterrows()) if not aging.empty else False
        if _varies(defaults, ("inadimplencia_pct", "provisao_pct_direitos", "cobertura_pct")) or aging_varies:
            add("Atraso e provisão", entity, credit_blocks, notes=("Inadimplência IME, provisão/DCs e composição de aging têm denominadores próprios; não são substituídos pelo NPL ex-360.",))
        subordination = _frame(getattr(dashboard, "subordination_history_df", None))
        visible_subordination = pd.to_numeric(subordination.get("subordinacao_pct", pd.Series(dtype="float64")), errors="coerce").dropna()
        if len({_br(value, 1) for value in visible_subordination}) > 1:
            add("Estrutura", entity, (_chart("Subordinação reportada", subordination, ("subordinacao_pct",), key_prefix="ime"),))
        for label, attribute in _DASHBOARD_ANNEXES:
            frame = _frame(getattr(dashboard, attribute, None))
            if not frame.empty:
                identities = [column for column in ("competencia", "competencia_dt", "class_key", "class_label", "classe", "faixa", "serie") if column in frame]
                values = [column for column in _DASHBOARD_DISPLAY_COLUMNS[attribute] if column in frame]
                if not values:
                    all_document_sources.append(f"{entity} · {label}: " + _raw_note(frame))
                    continue
                selected = frame[[*identities, *values]].copy()
                for table in _history_tables(label, selected):
                    table = replace(table, notes=(*table.notes, _raw_note(frame)))
                    add("Séries IME", entity, (table,), appendix=True, notes=(f"Fonte analítica: {attribute}",))
        summary = getattr(dashboard, "summary", {}) or {}
        if summary:
            # Summary includes source-selected balances that may not occur in the
            # monthly frames. Retain every field, without the legacy `or` fallback.
            saldo_rows = []
            for key in ("ativos_totais", "direitos_creditorios", "pl_total", "inadimplencia_total", "cobertura_pct", "subordinacao_pct"):
                if key not in summary:
                    continue
                unit = _unit(key)
                number = _number(summary[key])
                displayed = _br(number / 1_000_000, 1) if unit == "R$" and number is not None else _br(number, 1)
                saldo_rows.append({"Indicador": _ALIASES.get(key, key), "Valor": displayed, "Unidade": "R$ milhões" if unit == "R$" else unit})
            summary_cut = _month(dashboard_summary_competencia or getattr(dashboard, "latest_competencia", None))
            add("Posição IME", entity, (TableBlock(f"Posição original · {summary_cut}", pd.DataFrame(saldo_rows),
                notes=(f"Corte original do resumo: {summary_cut}. A janela das séries mensais permanece {period}; posições de cortes distintos não são combinadas.", _raw_note(pd.DataFrame([summary]))),
                numeric_columns=("Valor",)),), appendix=True)
        if hasattr(dashboard, "return_history_df") and hasattr(dashboard, "return_summary_df"):
            from services.fundonet_ppt_export import _build_return_inline_table_for_ppt
            return_table = _build_return_inline_table_for_ppt(dashboard, selected_labels=None, months=max(1, len(getattr(dashboard, "competencias", ())) or 12))
            if not return_table.empty:
                add("Rentabilidade IME", entity, (TableBlock("Retornos por cota · %", return_table,
                    notes=(_raw_note(_frame(getattr(dashboard, "return_history_df", None))), _raw_note(_frame(getattr(dashboard, "return_summary_df", None))), CVM_RETURN_REINVESTMENT_NOTE),
                    numeric_columns=tuple(map(str, return_table.columns[1:]))),), appendix=True)
        for note in getattr(dashboard, "methodology_notes", ()) or ():
            references.append({"Referência": "Metodologia IME", "Conteúdo": str(note)})

    if research_outputs is not None:
        roll_source = _frame(getattr(research_outputs, "roll_seasonality", None))
        # These are the seasonal values consumed by the previous exporter.
        # Other research frames repeat monitor/source variables and stay in notes.
        if not roll_source.empty:
            if len(scopes) == 1 and "scope" in roll_source and roll_source["scope"].ne("consolidado").any():
                roll_source = roll_source[roll_source["scope"].ne("consolidado")].copy()
            roll = _roll_matrix(roll_source)
            if not roll.empty:
                finite_roll = any(_number(value) is not None for value in roll_source["value_pct"])
                if finite_roll:
                    block: TableBlock | TextBlock = TableBlock("Roll rates por mês do ano · %", roll,
                        {str(column): "percent:1" for column in roll.columns[1:]}, (_raw_note(roll_source),), tuple(map(str, roll.columns[1:])))
                else:
                    criteria = "; ".join(roll_source["metric_name"].astype(str).drop_duplicates())
                    block = TextBlock("Migração sazonal", "Sem observações válidas no período selecionado para: " + criteria + ".")
                add("Sazonalidade da migração", portfolio_name, (block,), appendix=True, notes=(_raw_note(roll_source),))
        methodology = _frame(getattr(research_outputs, "methodology", None))
        if not methodology.empty:
            references.append({"Referência": "Migração e safras", "Conteúdo": "Proxies e denominadores originais do app; fórmulas completas nas notas."})
            all_document_sources.append("Metodologia: " + _raw_note(methodology))

    for item in analytical_data:
        name = str(getattr(item, "name", "FIDC"))
        competence = _month(getattr(item, "competence", None))
        fields = (("CNPJ", getattr(item, "cnpj", None)), ("Classificação", getattr(item, "classification", None)),
                  ("PL documental (R$ mm)", getattr(item, "pl_mm", None)), ("Direitos creditórios / PL", getattr(item, "receivables_pct_pl", None)),
                  ("Cotas sênior / PL", getattr(item, "senior_pct_pl", None)), ("Cotas subordinadas / PL", getattr(item, "subordinated_pct_pl", None)),
                  ("Volume emitido identificado (R$ mm)", getattr(item, "identified_issuance_volume_mm", None)),
                  ("Primeira emissão", getattr(item, "first_issuance", None)), ("Última emissão", getattr(item, "last_issuance", None)),
                  ("Subordinação mínima", getattr(item, "minimum_subordination", None)), ("RDB · status", getattr(item, "rdb_status", None)),
                  ("RDB · leitura", getattr(item, "rdb_finding", None)), ("RDB · fonte", getattr(item, "rdb_source", None)))
        analytic_body.append({"Fundo": name, "Posição documental": competence,
            "PL documental": _format_brl_compact(float(item.pl_mm) * 1_000_000) if _number(getattr(item, "pl_mm", None)) is not None else "N/D",
            "Subordinação mínima": _text(getattr(item, "minimum_subordination", None))})
        original = pd.DataFrame([{"Campo": label, "Valor original": value} for label, value in fields])
        displayed = original.copy()
        for index, (label, value) in enumerate(fields):
            if label.endswith("/ PL") and _number(value) is not None:
                displayed.at[index, "Valor original"] = _br(float(value) * 100.0, 1) + "%"
            elif "R$ mm" in label:
                displayed.at[index, "Campo"] = label.replace(" (R$ mm)", "")
                displayed.at[index, "Valor original"] = _format_brl_compact(float(value) * 1_000_000) if _number(value) is not None else "Não localizado"
            else:
                displayed.at[index, "Valor original"] = _text(value)
        displayed = displayed.rename(columns={"Valor original": "Informação"})
        add("Documentos · posição", name, _document_blocks(f"Posição documental · {competence}", displayed,
            entity=name, notes=tuple(getattr(item, "validations", ()) or ()), numeric_columns=("Informação",)),
            notes=(_raw_note(original), *tuple(getattr(item, "validations", ()) or ())), source="CVM / Fundos.NET", appendix=True)
        issuances = []
        for issuance in getattr(item, "issuances", ()):
            issuances.append({"Data": getattr(issuance, "date", None), "Série / classe": getattr(issuance, "series", None), "Tipo de cota": getattr(issuance, "quota_class", None),
                              "Volume (R$ mm)": getattr(issuance, "volume_mm", None), "Remuneração": getattr(issuance, "remuneration", None),
                              "Amortização": getattr(issuance, "amortization", None), "Fonte": getattr(issuance, "source", None)})
        if issuances:
            add("Emissões", name, (TableBlock("Emissões documentadas", pd.DataFrame(issuances), {"Volume (R$ mm)": "number:1"}, numeric_columns=("Volume (R$ mm)",)),), source="Fundos.NET/B3 · documentos por emissão", appendix=True)

    for page in documentary_pages:
        frame = _frame(getattr(page, "frame", None))
        for column in frame.columns[1:]:
            frame[column] = frame[column].map(lambda value: "Não localizado" if _is_missing(document_comparison_value(value)) else document_comparison_value(value))
        page_notes = tuple(public_document_text(note) for note in getattr(page, "notes", ()) if public_document_text(note))
        page_sources = tuple(public_document_text(source) for source in getattr(page, "sources", ()) if public_document_text(source))
        if not frame.empty:
            documentary_body.append(frame)
            add("Documentos completos", portfolio_name, _document_blocks(str(getattr(page, "title", "Documentos")), frame),
                source="Fundos.NET/B3", notes=(*page_notes, *page_sources, _raw_note(_frame(getattr(page, "frame", None)))), appendix=True)
        for source in page_sources:
            all_document_sources.append(source)
            theme = str(getattr(page, "title", "Documento"))
            urls = tuple(dict.fromkeys(value.rstrip(".,)") for value in re.findall(r"https?://[^\s;|]+", source)))
            ids = tuple(dict.fromkeys(re.findall(r"(?i)\b(?:ID|documento|CVM)\s*[:#]?\s*(?:n[º°.]?\s*)?\d[\w./-]*", source)))
            if urls or ids:
                for reference in (*ids, *urls):
                    themes = documentary_references.setdefault(reference, [])
                    if theme not in themes:
                        themes.append(theme)
            else:
                references.append({"Referência": theme, "Conteúdo": _reference_label(source)})

    # One documentary overview selects short existing criteria; full clauses,
    # empty fields and all fund/issue values are already in the documentary annex.
    documentary_blocks = []
    if analytic_body:
        documentary_blocks.append(TableBlock("Posição e regra", pd.DataFrame(analytic_body), numeric_columns=("PL documental",)))
    if documentary_body:
        first_column = documentary_body[0].columns[0]
        combined = pd.concat([frame.rename(columns={frame.columns[0]: first_column}) for frame in documentary_body], ignore_index=True, sort=False)
        short_rows = combined.iloc[:, 1:].apply(lambda column: column.map(lambda value: len(_text(value)) <= 200)).all(axis=1)
        missing_rows = combined.iloc[:, 1:].apply(lambda column: column.map(_is_missing)).all(axis=1)
        available = combined.loc[short_rows & ~missing_rows].drop_duplicates(subset=[first_column], keep="first")
        tokens = ("receb", "elegib", "revolv", "hedg", "taxa", "subordin", "concent", "amort")
        preferred = available[first_column].astype(str).str.lower().map(lambda label: any(token in label for token in tokens))
        selected = pd.concat([available.loc[preferred], available.loc[~preferred]]).head(7)
        if not selected.empty:
            documentary_blocks.extend(_document_blocks("Regras e características", selected,
                notes=("Critérios curtos extraídos das matrizes existentes. Texto integral, campos restantes e referências por célula no anexo.",)))
        if missing_rows.any():
            documentary_blocks.append(TextBlock("Campos documentais", "Há critérios sem informação nos documentos disponíveis. Os campos e os respectivos fundos estão identificados no anexo."))
    if documentary_blocks:
        add("Ficha documental", portfolio_name, documentary_blocks, source="CVM / Fundos.NET/B3 · curadoria documental",
            notes=("Cada posição documental conserva seu corte próprio. Os valores históricos e os documentais podem referir-se a períodos distintos.",))

    for fund in funds:
        cnpj, name = _fund_identity(fund)
        references.append({"Referência": "Fundo selecionado", "Conteúdo": f"{name} · CNPJ {cnpj}"})
    references.extend((
        {"Referência": "Período visual", "Conteúdo": period},
        {"Referência": "Período solicitado", "Conteúdo": requested_period_label or str((getattr(outputs, "metadata", {}) or {}).get("period_label") or "N/D")},
        {"Referência": "Fonte quantitativa", "Conteúdo": "CVM / Fundos.NET · informes mensais; dados consolidados, fórmulas, denominadores e proxies fornecidos pelo app."},
        {"Referência": "Rentabilidade", "Conteúdo": CVM_RETURN_REINVESTMENT_NOTE},
        {"Referência": "Leitura documental", "Conteúdo": str(getattr(documentary_manifest, "generated_at", None) or "não disponível")},
    ))
    for label, values in (("Aviso da base", getattr(outputs, "warnings_df", None)),):
        frame = _frame(values)
        if not frame.empty:
            add("Cobertura e ressalvas", portfolio_name, (_native_table(label, frame),), appendix=True)
    for obj, label in ((monitor_outputs, "Monitoramento"), (research_outputs, "Research")):
        for warning in getattr(obj, "warnings", ()) or ():
            references.append({"Referência": f"Ressalva · {label}", "Conteúdo": str(warning)})
    if include_conclusions:
        from services.somatorio_fidcs_ppt_export import _build_synthesis_sections
        primary = scopes[0]
        sections = _build_synthesis_sections(
            consolidated_monitor=primary[3], consolidated_monthly=primary[2],
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
        all_document_sources.extend(source_summary)
        if blocks:
            body.insert(1, SlideSpec("Conclusões", f"{portfolio_name} · {period}", blocks, _SOURCE,
                notes=(*source_summary, *identity_notes)))
    references.extend({"Referência": "; ".join(themes), "Conteúdo": reference} for reference, themes in documentary_references.items())
    reference_frame = pd.DataFrame(references).drop_duplicates(ignore_index=True)
    add("Referências", portfolio_name, (TableBlock("Fontes e cortes", reference_frame,
        notes=tuple(dict.fromkeys(all_document_sources))),), source="CVM / Fundos.NET / B3", appendix=True)
    metadata = (f"{len(funds)} fundo{'s' if len(funds) != 1 else ''} · {period}",
                f"Período solicitado: {requested_period_label or period}",
                "Consulta: " + now.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"))
    return DeckSpec(portfolio_name, f"Carteira · {period}", metadata, tuple([*body, *annex]))


__all__ = ["TableBlock", "ChartSeries", "ChartBlock", "TextBlock", "SlideSpec", "DeckSpec", "build_portfolio_deck_spec"]
