from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import Iterable, Mapping

import pandas as pd

from services.cloudwalk_financial_cost import (
    FundingLine,
    funding_lines_from_frame,
)
from services.identifier_utils import format_cnpj, normalize_cnpj_digits
from services.portfolio_store import PortfolioRecord
from services.regulatory_knowledge import REGULATORY_KNOWLEDGE_DIR
from services.regulatory_profiles import REGULATORY_PROFILES_DIR, load_regulatory_profile
from services.waterfall_schedule import normalize_text


SCOPE_CLOUDWALK = "cloudwalk"
SCOPE_PORTFOLIO = "portfolio"
SCOPE_CNPJS = "cnpjs"
SCOPE_KINDS = (SCOPE_CLOUDWALK, SCOPE_PORTFOLIO, SCOPE_CNPJS)


@dataclass(frozen=True)
class FinancialCostScope:
    kind: str
    label: str
    cnpjs: tuple[str, ...]
    fund_names: tuple[tuple[str, str], ...] = ()
    emissions_path: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in SCOPE_KINDS:
            raise ValueError("Tipo de escopo inválido para custo financeiro.")
        normalized = _deduplicate_cnpjs(self.cnpjs)
        if not normalized:
            raise ValueError("O escopo precisa conter ao menos um CNPJ de fundo.")
        object.__setattr__(self, "cnpjs", normalized)
        object.__setattr__(self, "label", str(self.label or "Seleção de FIDCs").strip() or "Seleção de FIDCs")

        names: list[tuple[str, str]] = []
        seen: set[str] = set()
        for raw_cnpj, raw_name in self.fund_names:
            cnpj = normalize_cnpj_digits(raw_cnpj)
            if cnpj not in normalized or cnpj in seen:
                continue
            seen.add(cnpj)
            name = str(raw_name or cnpj).strip() or cnpj
            names.append((cnpj, name))
        object.__setattr__(self, "fund_names", tuple(names))

    @property
    def fund_name_map(self) -> dict[str, str]:
        return dict(self.fund_names)

    @property
    def signature(self) -> str:
        payload = "\n".join(
            [self.kind, self.label, self.emissions_path or "", *self.cnpjs, *(f"{cnpj}|{name}" for cnpj, name in self.fund_names)]
        )
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ManualCnpjSelection:
    cnpjs: tuple[str, ...]
    invalid: tuple[str, ...]
    duplicates: tuple[str, ...]


@dataclass
class FinancialCostCuration:
    emissions_df: pd.DataFrame
    coverage_df: pd.DataFrame
    source_files: tuple[str, ...]

    @property
    def has_emissions(self) -> bool:
        return self.emissions_df is not None and not self.emissions_df.empty

    @property
    def resolved_cnpjs(self) -> tuple[str, ...]:
        if self.coverage_df.empty:
            return ()
        mask = pd.to_numeric(self.coverage_df.get("series_found"), errors="coerce").fillna(0).gt(0)
        return tuple(self.coverage_df.loc[mask, "cnpj"].astype(str))

    @property
    def missing_cnpjs(self) -> tuple[str, ...]:
        if self.coverage_df.empty:
            return ()
        mask = pd.to_numeric(self.coverage_df.get("series_found"), errors="coerce").fillna(0).eq(0)
        return tuple(self.coverage_df.loc[mask, "cnpj"].astype(str))


def build_cloudwalk_scope(emissions_path: str | Path) -> FinancialCostScope:
    path = Path(emissions_path)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "CNPJ" not in frame.columns:
        raise ValueError("A base padrão da CloudWalk não contém a coluna CNPJ.")
    names = _fund_names_from_frame(frame)
    return FinancialCostScope(
        kind=SCOPE_CLOUDWALK,
        label="CloudWalk",
        cnpjs=tuple(names),
        fund_names=tuple(names.items()),
        emissions_path=str(path.resolve()),
    )


def scope_from_portfolio(portfolio: PortfolioRecord) -> FinancialCostScope:
    return FinancialCostScope(
        kind=SCOPE_PORTFOLIO,
        label=portfolio.name,
        cnpjs=tuple(fund.cnpj for fund in portfolio.funds),
        fund_names=tuple((fund.cnpj, fund.display_name) for fund in portfolio.funds),
    )


def scope_from_cnpjs(
    cnpjs: Iterable[str],
    *,
    fund_names: Mapping[str, str] | None = None,
    label: str | None = None,
) -> FinancialCostScope:
    normalized = _deduplicate_cnpjs(cnpjs)
    names = {
        digits: str(name or digits).strip() or digits
        for raw_cnpj, name in (fund_names or {}).items()
        if (digits := normalize_cnpj_digits(raw_cnpj)) in normalized
    }
    scope_label = str(label or "").strip() or (
        format_cnpj(normalized[0]) if len(normalized) == 1 else f"Seleção manual ({len(normalized)} fundos)"
    )
    return FinancialCostScope(
        kind=SCOPE_CNPJS,
        label=scope_label,
        cnpjs=normalized,
        fund_names=tuple(names.items()),
    )


def parse_manual_cnpj_selection(value: object) -> ManualCnpjSelection:
    tokens = [token.strip() for token in re.split(r"[,;\n\r\t ]+", str(value or "")) if token.strip()]
    valid: list[str] = []
    invalid: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        digits = normalize_cnpj_digits(token)
        if not digits or not is_valid_cnpj(digits):
            invalid.append(token)
            continue
        if digits in seen:
            duplicates.append(digits)
            continue
        seen.add(digits)
        valid.append(digits)
    return ManualCnpjSelection(tuple(valid), tuple(invalid), tuple(duplicates))


def is_valid_cnpj(value: object) -> bool:
    digits = normalize_cnpj_digits(value)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False

    def _check_digit(base: str, weights: tuple[int, ...]) -> str:
        remainder = sum(int(character) * weight for character, weight in zip(base, weights)) % 11
        return "0" if remainder < 2 else str(11 - remainder)

    first = _check_digit(digits[:12], (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    second = _check_digit(digits[:12] + first, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    return digits[-2:] == first + second


def curation_data_signature(
    scope: FinancialCostScope,
    *,
    curated_dir: str | Path = REGULATORY_PROFILES_DIR,
    knowledge_dir: str | Path = REGULATORY_KNOWLEDGE_DIR,
) -> str:
    paths: list[Path] = []
    if scope.emissions_path:
        paths.append(Path(scope.emissions_path))
    else:
        paths.extend(sorted(Path(curated_dir).glob("*.csv")))
        paths.extend(Path(knowledge_dir) / f"{cnpj}.json" for cnpj in scope.cnpjs)
    parts = [scope.signature]
    for path in paths:
        try:
            stat = path.stat()
            parts.append(f"{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}")
        except OSError:
            parts.append(f"{path.resolve()}|missing")
    return sha256("\n".join(parts).encode("utf-8")).hexdigest()


def resolve_scope_curation(
    scope: FinancialCostScope,
    *,
    curated_dir: str | Path = REGULATORY_PROFILES_DIR,
    knowledge_dir: str | Path = REGULATORY_KNOWLEDGE_DIR,
) -> FinancialCostCuration:
    if scope.emissions_path:
        frame = pd.read_csv(scope.emissions_path, dtype=str, keep_default_na=False)
        selected = set(scope.cnpjs)
        frame = frame[frame.get("CNPJ", pd.Series("", index=frame.index)).map(normalize_cnpj_digits).isin(selected)].copy()
        frame, blocked = deduplicate_emission_rows(frame)
        profile_by_cnpj = {cnpj: "curado" for cnpj in scope.cnpjs}
        source_by_cnpj = {cnpj: (scope.emissions_path,) for cnpj in scope.cnpjs}
        blocked_by_cnpj = {cnpj: blocked.get(cnpj, 0) for cnpj in scope.cnpjs}
        emissions = frame
    else:
        frames: list[pd.DataFrame] = []
        profile_by_cnpj: dict[str, str] = {}
        source_by_cnpj: dict[str, tuple[str, ...]] = {}
        blocked_by_cnpj: dict[str, int] = {}
        for cnpj in scope.cnpjs:
            profile = load_regulatory_profile(
                cnpj,
                curated_dir=Path(curated_dir),
                knowledge_dir=Path(knowledge_dir),
            )
            if profile is None or profile.emissions_df.empty:
                profile_by_cnpj[cnpj] = "sem curadoria"
                source_by_cnpj[cnpj] = ()
                blocked_by_cnpj[cnpj] = 0
                continue
            frame, blocked = deduplicate_emission_rows(profile.emissions_df)
            frames.append(frame)
            profile_by_cnpj[cnpj] = profile.profile_type
            emission_sources = tuple(
                str(path)
                for path in profile.source_files
                if "cotas_emissoes_pagamentos" in path.name
            )
            source_by_cnpj[cnpj] = emission_sources or tuple(str(path) for path in profile.source_files)
            blocked_by_cnpj[cnpj] = blocked.get(cnpj, 0)
        emissions = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    emissions = _fill_missing_fund_names(emissions, scope.fund_name_map)
    coverage_rows = []
    all_sources: list[str] = []
    for cnpj in scope.cnpjs:
        subset = _filter_cnpj(emissions, cnpj)
        lines = funding_lines_from_frame(subset) if not subset.empty else []
        active = [line for line in lines if line.included]
        fund_name = _resolved_fund_name(subset, scope.fund_name_map.get(cnpj, cnpj))
        sources = source_by_cnpj.get(cnpj, ())
        all_sources.extend(sources)
        coverage_rows.append(
            {
                "fund_name": fund_name,
                "cnpj": cnpj,
                "profile_type": profile_by_cnpj.get(cnpj, "sem curadoria"),
                "series_found": len(lines),
                "active_series": len(active),
                "automatic_spreads": sum(line.spread_aa is not None for line in active),
                "pending_spreads": sum(line.spread_aa is None for line in active),
                "ambiguous_rows_blocked": int(blocked_by_cnpj.get(cnpj, 0)),
                "source_files": " | ".join(Path(source).name for source in sources),
                "status": _coverage_status(lines, active, int(blocked_by_cnpj.get(cnpj, 0))),
            }
        )
    coverage = pd.DataFrame(coverage_rows, columns=_coverage_columns())
    return FinancialCostCuration(
        emissions_df=emissions.reset_index(drop=True),
        coverage_df=coverage,
        source_files=tuple(dict.fromkeys(all_sources)),
    )


def deduplicate_emission_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(frame.columns) if frame is not None else []), {}
    # Exact duplicate records are safe to collapse. Conflicting records that
    # share CNPJ + class text are not: they can represent revisions, historical
    # events or genuinely different issuances. Until a stable series identifier
    # and record status exist, block the entire ambiguous key instead of picking
    # a seemingly "better" row and risking double-counting or stale economics.
    output = frame.copy().drop_duplicates().reset_index(drop=True)
    output["_cnpj_norm"] = output.get("CNPJ", pd.Series("", index=output.index)).map(normalize_cnpj_digits)
    output["_class_norm"] = output.get("Cota/Classe", pd.Series("", index=output.index)).map(normalize_text)
    output["_row_order"] = range(len(output.index))

    keep_indexes: list[int] = []
    blocked: dict[str, int] = {}
    grouped = output.groupby(["_cnpj_norm", "_class_norm"], sort=False, dropna=False)
    for (cnpj, class_name), group in grouped:
        if not cnpj or not class_name:
            keep_indexes.extend(group.index.tolist())
            continue
        if len(group.index) == 1:
            keep_indexes.append(int(group.index[0]))
            continue
        blocked[str(cnpj)] = blocked.get(str(cnpj), 0) + len(group.index)
    cleaned = output.loc[sorted(keep_indexes, key=lambda idx: int(output.loc[idx, "_row_order"]))].copy()
    return cleaned.drop(columns=["_cnpj_norm", "_class_norm", "_row_order"]), blocked


def _coverage_status(lines: list[FundingLine], active: list[FundingLine], ambiguous_rows_blocked: int) -> str:
    if ambiguous_rows_blocked and not lines:
        return "Curadoria ambígua; séries bloqueadas"
    if ambiguous_rows_blocked:
        return "Parcial; há séries ambíguas bloqueadas"
    if not lines:
        return "Sem curadoria de séries"
    if not active:
        return "Sem série remunerada utilizável"
    pending = sum(line.spread_aa is None for line in active)
    if pending:
        return f"{pending} spread{'s' if pending != 1 else ''} pendente{'s' if pending != 1 else ''}"
    return "Pronto para calcular"


def _coverage_columns() -> list[str]:
    return [
        "fund_name",
        "cnpj",
        "profile_type",
        "series_found",
        "active_series",
        "automatic_spreads",
        "pending_spreads",
        "ambiguous_rows_blocked",
        "source_files",
        "status",
    ]


def _filter_cnpj(frame: pd.DataFrame, cnpj: str) -> pd.DataFrame:
    if frame is None or frame.empty or "CNPJ" not in frame.columns:
        return pd.DataFrame(columns=list(frame.columns) if frame is not None else [])
    return frame[frame["CNPJ"].map(normalize_cnpj_digits).eq(cnpj)].copy()


def _fill_missing_fund_names(frame: pd.DataFrame, names: Mapping[str, str]) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame.copy() if frame is not None else pd.DataFrame()
    output = frame.copy()
    if "Fundo" not in output.columns:
        output["Fundo"] = ""
    for index, row in output.iterrows():
        if str(row.get("Fundo") or "").strip():
            continue
        cnpj = normalize_cnpj_digits(row.get("CNPJ"))
        output.at[index, "Fundo"] = names.get(cnpj, cnpj)
    return output


def _resolved_fund_name(frame: pd.DataFrame, fallback: str) -> str:
    if frame is not None and not frame.empty and "Fundo" in frame.columns:
        names = frame["Fundo"].fillna("").astype(str).str.strip()
        names = names[names.ne("")]
        if not names.empty:
            return str(names.iloc[0])
    return str(fallback or "").strip()


def _fund_names_from_frame(frame: pd.DataFrame) -> dict[str, str]:
    names: dict[str, str] = {}
    for _, row in frame.iterrows():
        cnpj = normalize_cnpj_digits(row.get("CNPJ"))
        if not cnpj or cnpj in names:
            continue
        names[cnpj] = str(row.get("Fundo") or cnpj).strip() or cnpj
    return names


def _deduplicate_cnpjs(cnpjs: Iterable[str]) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in cnpjs:
        digits = normalize_cnpj_digits(raw)
        if not digits or digits in seen:
            continue
        seen.add(digits)
        output.append(digits)
    return tuple(output)
