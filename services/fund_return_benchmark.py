from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
import unicodedata
from typing import Any

import pandas as pd

from services.regulatory_knowledge import normalize_cnpj
from services.regulatory_profiles import CuratedRegulatoryProfile, load_regulatory_profile


ACCEPTED_PROFILE_TYPES = frozenset({"curado", "curado parcial"})

BENCHMARK_DIAGNOSTIC_COLUMNS = [
    "class_key",
    "class_label",
    "class_macro",
    "series_number",
    "spread_aa",
    "status",
    "source",
    "curation_status",
    "remuneration",
    "matched_class",
    "candidate_count",
    "profile_type",
]

_UNSAFE_REMUNERATION_PATTERNS = (
    r"\bate\b",
    r"\bcap\b",
    r"\badicion\w*\b",
    r"\bexcesso\b",
    r"\baceler\w*\b",
    r"\bstep[ -]?up\b",
    r"\bbookbuilding\b",
    r"\bqualific\w*\b",
    r"\bfator\s+de\s+nao\s+utilizacao\b",
    r"\b\d+(?:[.,]\d+)?\s*%\s*(?:do|da)\s*(?:di|cdi)\b",
    r"\bipca\b",
    r"\bntn[ -]?b\b",
    r"\bmaior\b",
    r"\bou\b",
    r"\bconforme\b",
    r"\bsobretaxa\b",
    r"\bsem\s+parametro\b",
    r"\bnao\s+localizad\w*\b",
    r"\bresidual\b",
)

_SIMPLE_CDI_PLUS_RE = re.compile(
    r"^\s*(?:taxa\s+)?(?:di|cdi)\s*\+\s*"
    r"(?P<spread>\d{1,2}(?:[.,]\d{1,6})?)\s*%"
    r"(?:\s*(?:a\.?\s*a\.?|ao\s+ano))?"
    r"(?:\s*\(\s*252\s*(?:d\.?\s*u\.?|dias?\s+uteis?)\s*\))?"
    r"\s*[.;]?\s*$",
    re.IGNORECASE,
)

_SERIES_TOKEN = r"(?:\d+|[ivxlcdm]+)"
_SERIES_PATTERNS = (
    re.compile(rf"\bserie\s*(?:n(?:o|umero)?\s*)?({_SERIES_TOKEN})\b", re.IGNORECASE),
    re.compile(rf"\b({_SERIES_TOKEN})\s*(?:a|o)?\s*serie\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class FundReturnBenchmarkResolution:
    """Conservative issuance-spread resolution for the return matrix.

    ``spreads_by_class_key`` always uses annual decimal rates. For example,
    CDI + 3.50% a.a. is represented as ``0.035``.
    """

    spreads_by_class_key: dict[str, float]
    diagnostics_df: pd.DataFrame


ProfileLoader = Callable[[str], CuratedRegulatoryProfile | None]


def resolve_fund_return_benchmarks(
    cnpj: str,
    series_df: pd.DataFrame,
    *,
    profile_loader: ProfileLoader = load_regulatory_profile,
) -> FundReturnBenchmarkResolution:
    """Resolve unambiguous fixed CDI/DI spreads for reported fund series.

    The fund is scoped by its CNPJ through ``load_regulatory_profile``. Only
    manually curated profiles are eligible. Matching requires an exact class
    macro and an explicit series number on both the IME series and the
    documentary emission row. Any competing or unsupported term fails closed.
    """

    identities = _series_identities(series_df)
    if identities.empty:
        return FundReturnBenchmarkResolution({}, _empty_diagnostics())

    digits = normalize_cnpj(cnpj)
    if len(digits) != 14:
        return _unresolved_resolution(identities, status="invalid_cnpj")

    try:
        profile = profile_loader(digits)
    except Exception:  # noqa: BLE001 - diagnostics must fail closed
        return _unresolved_resolution(identities, status="profile_load_error")

    if profile is None or not profile.available:
        return _unresolved_resolution(identities, status="profile_unavailable")

    profile_type = _normalized_text(profile.profile_type)
    if profile_type not in ACCEPTED_PROFILE_TYPES:
        return _unresolved_resolution(
            identities,
            status="profile_not_manually_curated",
            profile_type=profile.profile_type,
        )
    if normalize_cnpj(profile.cnpj) != digits:
        return _unresolved_resolution(
            identities,
            status="profile_cnpj_mismatch",
            profile_type=profile.profile_type,
        )

    emissions = _normalized_emissions(profile.emissions_df)
    spreads: dict[str, float] = {}
    diagnostics: list[dict[str, Any]] = []
    duplicated_keys = _duplicated_identity_keys(identities)

    for _, identity in identities.iterrows():
        class_key = _display(identity.get("class_key"))
        class_label = _display(identity.get("class_label"))
        class_macro = _series_macro(identity)
        series_number = _series_number_from_values(
            identity.get("serie_raw"),
            identity.get("class_label"),
            identity.get("class_key"),
        )
        base = _diagnostic_row(
            class_key=class_key,
            class_label=class_label,
            class_macro=class_macro,
            series_number=series_number,
            profile_type=profile.profile_type,
        )

        if not class_key:
            diagnostics.append({**base, "status": "missing_class_key"})
            continue
        if class_key in duplicated_keys:
            diagnostics.append({**base, "status": "ambiguous_series_identity"})
            continue
        if not class_macro:
            diagnostics.append({**base, "status": "missing_class_macro"})
            continue
        if series_number is None:
            diagnostics.append({**base, "status": "missing_explicit_series_number"})
            continue

        candidates = emissions[
            emissions["__class_macro"].eq(class_macro)
            & emissions["__series_number"].eq(series_number)
        ].copy()
        base["candidate_count"] = int(len(candidates.index))
        if candidates.empty:
            diagnostics.append({**base, "status": "no_matching_emission"})
            continue

        base.update(_candidate_diagnostic_values(candidates))
        parsed = candidates["__spread_aa"]
        if parsed.isna().any():
            status = "unsupported_remuneration" if len(candidates.index) == 1 else "ambiguous_or_unsupported_terms"
            diagnostics.append({**base, "status": status})
            continue

        distinct_spreads = sorted({float(value) for value in parsed.tolist()})
        if len(distinct_spreads) != 1:
            diagnostics.append({**base, "status": "ambiguous_spread"})
            continue

        spread = distinct_spreads[0]
        spreads[class_key] = spread
        diagnostics.append({**base, "spread_aa": spread, "status": "resolved"})

    return FundReturnBenchmarkResolution(
        spreads_by_class_key=spreads,
        diagnostics_df=pd.DataFrame(diagnostics, columns=BENCHMARK_DIAGNOSTIC_COLUMNS),
    )


def parse_simple_cdi_plus_spread(value: Any) -> float | None:
    """Parse only a fixed, standalone CDI/DI + x% a.a. remuneration."""

    text = _normalized_text(value)
    if not text or any(re.search(pattern, text) for pattern in _UNSAFE_REMUNERATION_PATTERNS):
        return None
    matches = list(_SIMPLE_CDI_PLUS_RE.finditer(text))
    if len(matches) != 1:
        return None
    raw_spread = matches[0].group("spread").replace(",", ".")
    try:
        percentage_points = float(raw_spread)
    except ValueError:
        return None
    if not 0.0 <= percentage_points < 100.0:
        return None
    return percentage_points / 100.0


def _series_identities(series_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(series_df, pd.DataFrame) or series_df.empty:
        return pd.DataFrame()
    output = series_df.copy()
    if "class_key" not in output.columns:
        output["class_key"] = ""
    if "class_label" not in output.columns:
        output["class_label"] = output.get("label", "")
    identity_columns = [
        column
        for column in ("class_key", "class_label", "class_kind", "class_macro", "serie_raw")
        if column in output.columns
    ]
    return output[identity_columns].drop_duplicates().reset_index(drop=True)


def _duplicated_identity_keys(identities: pd.DataFrame) -> set[str]:
    keys = identities.get("class_key", pd.Series(dtype="object")).fillna("").astype(str).str.strip()
    return set(keys[keys.ne("") & keys.duplicated(keep=False)].tolist())


def _normalized_emissions(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(
            columns=[
                "__class_macro",
                "__series_number",
                "__spread_aa",
                "__remuneration",
                "__source",
                "__curation_status",
                "__matched_class",
            ]
        )
    output = frame.copy()
    output["__matched_class"] = _column_or_blank(output, "Cota/Classe").map(_display)
    output["__class_macro"] = output.apply(
        lambda row: _macro_from_text(row.get("Tipo"), row.get("Cota/Classe")),
        axis=1,
    )
    output["__series_number"] = output.apply(
        lambda row: _series_number_from_values(row.get("Cota/Classe")),
        axis=1,
    )
    output["__remuneration"] = output.apply(
        lambda row: _first_display(row.get("Remuneração"), row.get("Juros/remuneração")),
        axis=1,
    )
    output["__spread_aa"] = output["__remuneration"].map(parse_simple_cdi_plus_spread)
    output["__source"] = _column_or_blank(output, "Fonte").map(_display)
    output["__curation_status"] = _column_or_blank(output, "Status curadoria").map(_display)
    return output


def _series_macro(row: pd.Series) -> str:
    return _macro_from_text(
        row.get("class_macro"),
        row.get("class_kind"),
        row.get("class_label"),
        row.get("class_key"),
    )


def _macro_from_text(*values: Any) -> str:
    text = " ".join(_normalized_text(value) for value in values if _display(value))
    if re.search(r"\b(?:mezan|mezz)", text):
        return "mezzanino"
    if re.search(r"\bsenior(?:es)?\b", text):
        return "senior"
    if re.search(r"\bsubordinad[ao]s?\b|\bjunior(?:es)?\b", text):
        return "subordinada"
    return ""


def _series_number_from_values(*values: Any) -> int | None:
    numbers: set[int] = set()
    for value in values:
        text = _normalized_text(value).replace("ª", "a").replace("º", "o")
        for pattern in _SERIES_PATTERNS:
            for match in pattern.finditer(text):
                parsed = _series_token_to_int(match.group(1))
                if parsed is not None:
                    numbers.add(parsed)
    if len(numbers) != 1:
        return None
    return next(iter(numbers))


def _series_token_to_int(value: str) -> int | None:
    token = str(value or "").strip().lower()
    if token.isdigit():
        return int(token)
    if not token or not re.fullmatch(r"[ivxlcdm]+", token):
        return None
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total = 0
    previous = 0
    for char in reversed(token):
        current = values[char]
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return total if total > 0 else None


def _candidate_diagnostic_values(candidates: pd.DataFrame) -> dict[str, Any]:
    return {
        "source": _joined_unique(candidates["__source"]),
        "curation_status": _joined_unique(candidates["__curation_status"]),
        "remuneration": _joined_unique(candidates["__remuneration"]),
        "matched_class": _joined_unique(candidates["__matched_class"]),
    }


def _joined_unique(values: pd.Series) -> str:
    unique = [value for value in dict.fromkeys(values.fillna("").astype(str).str.strip()) if value]
    return " | ".join(unique)


def _column_or_blank(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series("", index=frame.index, dtype="object")


def _diagnostic_row(
    *,
    class_key: str,
    class_label: str,
    class_macro: str,
    series_number: int | None,
    profile_type: str,
) -> dict[str, Any]:
    return {
        "class_key": class_key,
        "class_label": class_label,
        "class_macro": class_macro,
        "series_number": series_number,
        "spread_aa": None,
        "status": "",
        "source": "",
        "curation_status": "",
        "remuneration": "",
        "matched_class": "",
        "candidate_count": 0,
        "profile_type": profile_type,
    }


def _unresolved_resolution(
    identities: pd.DataFrame,
    *,
    status: str,
    profile_type: str = "",
) -> FundReturnBenchmarkResolution:
    rows: list[dict[str, Any]] = []
    for _, identity in identities.iterrows():
        rows.append(
            {
                **_diagnostic_row(
                    class_key=_display(identity.get("class_key")),
                    class_label=_display(identity.get("class_label")),
                    class_macro=_series_macro(identity),
                    series_number=_series_number_from_values(
                        identity.get("serie_raw"),
                        identity.get("class_label"),
                        identity.get("class_key"),
                    ),
                    profile_type=profile_type,
                ),
                "status": status,
            }
        )
    return FundReturnBenchmarkResolution(
        {},
        pd.DataFrame(rows, columns=BENCHMARK_DIAGNOSTIC_COLUMNS),
    )


def _empty_diagnostics() -> pd.DataFrame:
    return pd.DataFrame(columns=BENCHMARK_DIAGNOSTIC_COLUMNS)


def _display(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "<na>"} else text


def _first_display(*values: Any) -> str:
    for value in values:
        displayed = _display(value)
        if displayed:
            return displayed
    return ""


def _normalized_text(value: Any) -> str:
    text = _display(value).lower()
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text).strip()
