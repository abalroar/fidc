from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd


INDUSTRY_STUDY_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"

ANNUAL_FILENAME = "industry_closed_offers_annual.csv"
MONTHLY_FILENAME = "industry_closed_offers_monthly.csv"
ORIGINATORS_FILENAME = "industry_closed_offer_originators_2026.csv"

PAYLOAD_SCHEMA_VERSION = "industry_closed_offers.v1"
JAN_JUNE_YEARS = (2024, 2025, 2026)
# Compatibility alias for downstream readers that imported the old constant.
JAN_MAY_YEARS = JAN_JUNE_YEARS

SOURCE_COLUMNS = (
    "source_dataset",
    "source_url",
    "source_as_of_date",
    "source_archive_sha256",
    "latest_source_closing_date",
    "scope",
    "methodology",
)

OFFER_METRIC_COLUMNS = (
    "closed_offers",
    "issuer_cnpjs",
    "registered_volume_brl",
    "mean_registered_ticket_brl",
    "median_registered_ticket_brl",
    "offers_with_registered_quantity",
    "registered_quantity_offer_coverage",
    "registered_quantity_volume_coverage",
    "offers_with_placed_quantity",
    "placed_quantity_offer_coverage",
    "placed_quantity_registered_volume_coverage",
    "placed_volume_proxy_brl",
    "mean_placed_ticket_brl",
    "median_placed_ticket_brl",
    "placed_proxy_share_of_registered_covered",
    "offers_with_investor_count_data",
    "investor_count_offer_coverage",
    "investor_count_registered_volume_coverage",
    "median_investor_accounts",
    "offers_with_up_to_5_investors",
    "up_to_5_investors_offer_share_covered",
    "up_to_5_investors_registered_volume_share_covered",
    "professional_target_registered_volume_brl",
    "professional_target_registered_volume_share",
    "qualified_target_registered_volume_brl",
    "qualified_target_registered_volume_share",
    "general_target_registered_volume_brl",
    "general_target_registered_volume_share",
    "natural_person_accounts",
    "offers_with_natural_person",
    "natural_person_offer_presence_share_covered",
    "natural_person_placed_volume_proxy_brl",
    "natural_person_placed_volume_share",
)

ANNUAL_COLUMNS = (
    "year",
    "period_label",
    "period_start",
    "period_end",
    "is_full_year",
    *OFFER_METRIC_COLUMNS,
    *SOURCE_COLUMNS,
)

MONTHLY_COLUMNS = (
    "year",
    "month",
    "competence",
    "period_start",
    "period_end",
    "is_complete_month",
    *OFFER_METRIC_COLUMNS,
    *SOURCE_COLUMNS,
)

ORIGINATOR_COLUMNS = (
    "rank",
    "period_label",
    "period_start",
    "period_end",
    "originator_group",
    "closed_offers",
    "issuer_cnpjs",
    "registered_volume_brl",
    "mean_registered_ticket_brl",
    "median_registered_ticket_brl",
    "placed_volume_proxy_brl",
    "offers_with_placed_quantity",
    "placed_quantity_offer_coverage",
    "placed_quantity_registered_volume_coverage",
    "mean_placed_ticket_brl",
    "median_placed_ticket_brl",
    "share_of_total_registered_volume",
    "share_of_identified_registered_volume",
    "originator_source_fields",
    "originator_evidence_sample",
    "confidence",
    "universe_closed_offers",
    "universe_registered_volume_brl",
    "identified_registered_volume_brl",
    "unidentified_registered_volume_brl",
    "identified_registered_volume_coverage",
    *SOURCE_COLUMNS,
    "originator_methodology",
)

COMMON_COUNT_COLUMNS = {
    "closed_offers",
    "issuer_cnpjs",
    "offers_with_registered_quantity",
    "offers_with_placed_quantity",
    "offers_with_investor_count_data",
    "offers_with_up_to_5_investors",
    "natural_person_accounts",
    "offers_with_natural_person",
}

ANNUAL_INTEGER_COLUMNS = {"year", *COMMON_COUNT_COLUMNS}
MONTHLY_INTEGER_COLUMNS = {"year", "month", *COMMON_COUNT_COLUMNS}
ORIGINATOR_INTEGER_COLUMNS = {
    "rank",
    "closed_offers",
    "issuer_cnpjs",
    "offers_with_placed_quantity",
    "universe_closed_offers",
}

ANNUAL_BOOLEAN_COLUMNS = {"is_full_year"}
MONTHLY_BOOLEAN_COLUMNS = {"is_complete_month"}

ANNUAL_DATE_COLUMNS = {"period_start", "period_end", "source_as_of_date", "latest_source_closing_date"}
MONTHLY_DATE_COLUMNS = {"period_start", "period_end", "source_as_of_date", "latest_source_closing_date"}
ORIGINATOR_DATE_COLUMNS = {"period_start", "period_end", "source_as_of_date", "latest_source_closing_date"}

ANNUAL_NUMERIC_COLUMNS = ANNUAL_INTEGER_COLUMNS | {
    column for column in OFFER_METRIC_COLUMNS if column not in COMMON_COUNT_COLUMNS
}
MONTHLY_NUMERIC_COLUMNS = MONTHLY_INTEGER_COLUMNS | {
    column for column in OFFER_METRIC_COLUMNS if column not in COMMON_COUNT_COLUMNS
}
ORIGINATOR_NUMERIC_COLUMNS = ORIGINATOR_INTEGER_COLUMNS | {
    "registered_volume_brl",
    "mean_registered_ticket_brl",
    "median_registered_ticket_brl",
    "placed_volume_proxy_brl",
    "placed_quantity_offer_coverage",
    "placed_quantity_registered_volume_coverage",
    "mean_placed_ticket_brl",
    "median_placed_ticket_brl",
    "share_of_total_registered_volume",
    "share_of_identified_registered_volume",
    "universe_registered_volume_brl",
    "identified_registered_volume_brl",
    "unidentified_registered_volume_brl",
    "identified_registered_volume_coverage",
}

ADDITIVE_COLUMNS = (
    "closed_offers",
    "registered_volume_brl",
    "offers_with_registered_quantity",
    "offers_with_placed_quantity",
    "placed_volume_proxy_brl",
    "offers_with_investor_count_data",
    "offers_with_up_to_5_investors",
    "professional_target_registered_volume_brl",
    "qualified_target_registered_volume_brl",
    "general_target_registered_volume_brl",
    "natural_person_accounts",
    "offers_with_natural_person",
    "natural_person_placed_volume_proxy_brl",
)


class ClosedOffersDataError(ValueError):
    """Raised when a closed-offers artifact violates the published contract."""


@dataclass(frozen=True)
class ClosedOffersTables:
    annual: pd.DataFrame
    monthly: pd.DataFrame
    originators: pd.DataFrame


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Base de ofertas encerradas não encontrada: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


def _normalize_frame(
    frame: pd.DataFrame,
    *,
    name: str,
    columns: tuple[str, ...],
    numeric_columns: set[str],
    integer_columns: set[str],
    boolean_columns: set[str],
    date_columns: set[str],
) -> pd.DataFrame:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ClosedOffersDataError(f"{name}: colunas obrigatórias ausentes: {', '.join(missing)}")

    result = frame.loc[:, columns].copy()
    if result.empty:
        raise ClosedOffersDataError(f"{name}: a base está vazia.")

    for column in numeric_columns:
        values = pd.to_numeric(result[column], errors="coerce")
        if values.isna().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
            raise ClosedOffersDataError(f"{name}: coluna numérica inválida: {column}.")
        if (values < 0).any():
            raise ClosedOffersDataError(f"{name}: valor negativo em {column}.")
        if column in integer_columns:
            if not np.isclose(values, np.round(values), atol=1e-9).all():
                raise ClosedOffersDataError(f"{name}: valor não inteiro em {column}.")
            result[column] = values.astype("int64")
        else:
            result[column] = values.astype(float)

    true_values = {"1", "true", "t", "sim", "yes"}
    false_values = {"0", "false", "f", "não", "nao", "no"}
    for column in boolean_columns:
        normalized = result[column].astype(str).str.strip().str.casefold()
        invalid = ~normalized.isin(true_values | false_values)
        if invalid.any():
            raise ClosedOffersDataError(f"{name}: valor booleano inválido em {column}.")
        result[column] = normalized.isin(true_values)

    for column in date_columns:
        values = pd.to_datetime(result[column], errors="coerce", format="%Y-%m-%d")
        if values.isna().any():
            raise ClosedOffersDataError(f"{name}: data inválida em {column}.")
        result[column] = values.dt.strftime("%Y-%m-%d")

    text_columns = set(columns) - numeric_columns - boolean_columns
    for column in text_columns:
        values = result[column].astype(str).str.strip()
        if values.eq("").any():
            raise ClosedOffersDataError(f"{name}: texto obrigatório ausente em {column}.")
        result[column] = values

    share_columns = [
        column
        for column in numeric_columns
        if "share" in column or "coverage" in column
    ]
    for column in share_columns:
        if ((result[column] < 0) | (result[column] > 1)).any():
            raise ClosedOffersDataError(f"{name}: percentual fora de [0, 1] em {column}.")
    return result


def _assert_unique(frame: pd.DataFrame, columns: Iterable[str], *, name: str) -> None:
    keys = list(columns)
    if frame.duplicated(keys).any():
        raise ClosedOffersDataError(f"{name}: chaves duplicadas em {', '.join(keys)}.")


def _assert_close(left: float, right: float, *, message: str, atol: float = 1e-4) -> None:
    if not math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=atol):
        raise ClosedOffersDataError(message)


def _validate_offer_metrics(frame: pd.DataFrame, *, name: str) -> None:
    for count_column in (
        "offers_with_registered_quantity",
        "offers_with_placed_quantity",
        "offers_with_investor_count_data",
        "offers_with_natural_person",
    ):
        if (frame[count_column] > frame["closed_offers"]).any():
            raise ClosedOffersDataError(f"{name}: {count_column} supera closed_offers.")
    if (frame["offers_with_up_to_5_investors"] > frame["offers_with_investor_count_data"]).any():
        raise ClosedOffersDataError(f"{name}: ofertas com até 5 investidores superam a cobertura disponível.")

    expected_mean = frame["registered_volume_brl"] / frame["closed_offers"]
    if not np.isclose(frame["mean_registered_ticket_brl"], expected_mean, rtol=1e-10, atol=1e-4).all():
        raise ClosedOffersDataError(f"{name}: ticket médio registrado não reconcilia com volume/ofertas.")

    expected_placed_mean = frame["placed_volume_proxy_brl"] / frame["offers_with_placed_quantity"]
    if not np.isclose(frame["mean_placed_ticket_brl"], expected_placed_mean, rtol=1e-10, atol=1e-4).all():
        raise ClosedOffersDataError(f"{name}: ticket médio colocado não reconcilia com volume/ofertas cobertas.")

    target_total = frame[
        [
            "professional_target_registered_volume_brl",
            "qualified_target_registered_volume_brl",
            "general_target_registered_volume_brl",
        ]
    ].sum(axis=1)
    if not np.isclose(target_total, frame["registered_volume_brl"], rtol=1e-10, atol=1e-4).all():
        raise ClosedOffersDataError(f"{name}: público-alvo não reconcilia com o volume registrado.")

    target_shares = frame[
        [
            "professional_target_registered_volume_share",
            "qualified_target_registered_volume_share",
            "general_target_registered_volume_share",
        ]
    ].sum(axis=1)
    if not np.isclose(target_shares, 1.0, rtol=1e-10, atol=2e-6).all():
        raise ClosedOffersDataError(f"{name}: shares de público-alvo não fecham em 100%.")


def validate_closed_offers_annual(frame: pd.DataFrame) -> pd.DataFrame:
    result = _normalize_frame(
        frame,
        name="ofertas anuais",
        columns=ANNUAL_COLUMNS,
        numeric_columns=ANNUAL_NUMERIC_COLUMNS,
        integer_columns=ANNUAL_INTEGER_COLUMNS,
        boolean_columns=ANNUAL_BOOLEAN_COLUMNS,
        date_columns=ANNUAL_DATE_COLUMNS,
    )
    _assert_unique(result, ("year",), name="ofertas anuais")
    result = result.sort_values("year", kind="stable").reset_index(drop=True)
    if tuple(result["year"]) != (2023, 2024, 2025, 2026):
        raise ClosedOffersDataError("ofertas anuais: são esperados os anos de 2023 a 2026.")
    if not result.loc[result["year"].lt(2026), "is_full_year"].all():
        raise ClosedOffersDataError("ofertas anuais: 2023–2025 devem estar marcados como anos completos.")
    if bool(result.loc[result["year"].eq(2026), "is_full_year"].iloc[0]):
        raise ClosedOffersDataError("ofertas anuais: 2026 deve permanecer identificado como YTD.")
    starts = pd.to_datetime(result["period_start"])
    if not (starts.dt.year.eq(result["year"]) & starts.dt.month.eq(1) & starts.dt.day.eq(1)).all():
        raise ClosedOffersDataError("ofertas anuais: period_start deve ser o primeiro dia do ano.")
    complete = result["is_full_year"]
    ends = pd.to_datetime(result["period_end"])
    if not (ends.loc[complete].dt.month.eq(12) & ends.loc[complete].dt.day.eq(31)).all():
        raise ClosedOffersDataError("ofertas anuais: anos completos devem terminar em 31 de dezembro.")
    if not result.loc[~complete, "period_end"].eq(
        result.loc[~complete, "latest_source_closing_date"]
    ).all():
        raise ClosedOffersDataError("ofertas anuais: o período YTD deve terminar no último encerramento da fonte.")
    _validate_offer_metrics(result, name="ofertas anuais")
    _uniform_source(result, name="ofertas anuais")
    return result


def validate_closed_offers_monthly(frame: pd.DataFrame) -> pd.DataFrame:
    result = _normalize_frame(
        frame,
        name="ofertas mensais",
        columns=MONTHLY_COLUMNS,
        numeric_columns=MONTHLY_NUMERIC_COLUMNS,
        integer_columns=MONTHLY_INTEGER_COLUMNS,
        boolean_columns=MONTHLY_BOOLEAN_COLUMNS,
        date_columns=MONTHLY_DATE_COLUMNS,
    )
    _assert_unique(result, ("competence",), name="ofertas mensais")
    result = result.sort_values(["year", "month"], kind="stable").reset_index(drop=True)

    expected_competence = result["year"].astype(str) + "-" + result["month"].astype(str).str.zfill(2)
    if not result["competence"].eq(expected_competence).all():
        raise ClosedOffersDataError("ofertas mensais: competência diverge de year/month.")
    starts = pd.to_datetime(result["period_start"])
    ends = pd.to_datetime(result["period_end"])
    if not (starts.dt.year.eq(result["year"]) & starts.dt.month.eq(result["month"]) & starts.dt.day.eq(1)).all():
        raise ClosedOffersDataError("ofertas mensais: period_start não corresponde à competência.")
    month_ends = starts + pd.offsets.MonthEnd(0)
    latest_closing = pd.to_datetime(result["latest_source_closing_date"])
    valid_period_end = ends.eq(month_ends) | ends.eq(latest_closing)
    if not (
        ends.dt.year.eq(result["year"])
        & ends.dt.month.eq(result["month"])
        & valid_period_end
    ).all():
        raise ClosedOffersDataError("ofertas mensais: period_end não corresponde à competência.")

    source_month = pd.to_datetime(result["source_as_of_date"].iloc[0]).to_period("M")
    observed_months = pd.PeriodIndex(result["competence"], freq="M")
    expected_complete = observed_months < source_month
    if not result["is_complete_month"].eq(expected_complete).all():
        raise ClosedOffersDataError("ofertas mensais: flag is_complete_month incompatível com a data-base.")
    _validate_offer_metrics(result, name="ofertas mensais")
    _uniform_source(result, name="ofertas mensais")
    return result


def validate_closed_offer_originators(frame: pd.DataFrame) -> pd.DataFrame:
    result = _normalize_frame(
        frame,
        name="originadores 2026",
        columns=ORIGINATOR_COLUMNS,
        numeric_columns=ORIGINATOR_NUMERIC_COLUMNS,
        integer_columns=ORIGINATOR_INTEGER_COLUMNS,
        boolean_columns=set(),
        date_columns=ORIGINATOR_DATE_COLUMNS,
    )
    _assert_unique(result, ("originator_group",), name="originadores 2026")
    result = result.sort_values("rank", kind="stable").reset_index(drop=True)
    if result["rank"].tolist() != list(range(1, len(result) + 1)):
        raise ClosedOffersDataError("originadores 2026: ranking deve ser contínuo e começar em 1.")
    if not result["registered_volume_brl"].is_monotonic_decreasing:
        raise ClosedOffersDataError("originadores 2026: ranking não está ordenado pelo volume registrado.")
    if not result["period_start"].eq("2026-01-01").all():
        raise ClosedOffersDataError("originadores 2026: period_start deve ser 2026-01-01.")

    expected_mean = result["registered_volume_brl"] / result["closed_offers"]
    if not np.isclose(result["mean_registered_ticket_brl"], expected_mean, rtol=1e-10, atol=1e-4).all():
        raise ClosedOffersDataError("originadores 2026: ticket médio registrado não reconcilia.")
    expected_placed_mean = result["placed_volume_proxy_brl"] / result["offers_with_placed_quantity"]
    if not np.isclose(result["mean_placed_ticket_brl"], expected_placed_mean, rtol=1e-10, atol=1e-4).all():
        raise ClosedOffersDataError("originadores 2026: ticket médio colocado não reconcilia.")

    identified = float(result["registered_volume_brl"].sum())
    _assert_close(
        identified,
        result["identified_registered_volume_brl"].iloc[0],
        message="originadores 2026: volume identificado não reconcilia com as linhas.",
    )
    repeated_columns = (
        "universe_closed_offers",
        "universe_registered_volume_brl",
        "identified_registered_volume_brl",
        "unidentified_registered_volume_brl",
        "identified_registered_volume_coverage",
    )
    for column in repeated_columns:
        if result[column].nunique(dropna=False) != 1:
            raise ClosedOffersDataError(f"originadores 2026: metadado divergente entre linhas: {column}.")
    _assert_close(
        result["identified_registered_volume_brl"].iloc[0]
        + result["unidentified_registered_volume_brl"].iloc[0],
        result["universe_registered_volume_brl"].iloc[0],
        message="originadores 2026: volumes identificado e residual não fecham o universo.",
    )
    expected_total_share = result["registered_volume_brl"] / result["universe_registered_volume_brl"]
    if not np.isclose(result["share_of_total_registered_volume"], expected_total_share, rtol=1e-10).all():
        raise ClosedOffersDataError("originadores 2026: share do universo não reconcilia.")
    expected_identified_share = result["registered_volume_brl"] / identified
    if not np.isclose(result["share_of_identified_registered_volume"], expected_identified_share, rtol=1e-10).all():
        raise ClosedOffersDataError("originadores 2026: share identificado não reconcilia.")
    if result["originator_methodology"].nunique(dropna=False) != 1:
        raise ClosedOffersDataError("originadores 2026: metodologia divergente entre linhas.")
    _uniform_source(result, name="originadores 2026")
    return result


def load_closed_offers_annual(path: str | Path = INDUSTRY_STUDY_DIR / ANNUAL_FILENAME) -> pd.DataFrame:
    return validate_closed_offers_annual(_read_csv(Path(path)))


def load_closed_offers_monthly(path: str | Path = INDUSTRY_STUDY_DIR / MONTHLY_FILENAME) -> pd.DataFrame:
    return validate_closed_offers_monthly(_read_csv(Path(path)))


def load_closed_offer_originators(
    path: str | Path = INDUSTRY_STUDY_DIR / ORIGINATORS_FILENAME,
) -> pd.DataFrame:
    return validate_closed_offer_originators(_read_csv(Path(path)))


def _uniform_source(frame: pd.DataFrame, *, name: str) -> dict[str, Any]:
    source: dict[str, Any] = {}
    for column in SOURCE_COLUMNS:
        if frame[column].nunique(dropna=False) != 1:
            raise ClosedOffersDataError(f"{name}: metadado de fonte divergente entre linhas: {column}.")
        source[column.removeprefix("source_")] = _json_scalar(frame[column].iloc[0])
    return source


def _validate_cross_table_reconciliation(tables: ClosedOffersTables) -> None:
    annual = tables.annual
    monthly = tables.monthly
    originators = tables.originators

    source_keys = ("source_dataset", "source_url", "source_as_of_date", "source_archive_sha256")
    for column in source_keys:
        values = {
            annual[column].iloc[0],
            monthly[column].iloc[0],
            originators[column].iloc[0],
        }
        if len(values) != 1:
            raise ClosedOffersDataError(f"bases de ofertas: fonte divergente em {column}.")

    for year, annual_row in annual.set_index("year").iterrows():
        monthly_year = monthly.loc[monthly["year"].eq(year)]
        if monthly_year.empty:
            raise ClosedOffersDataError(f"bases de ofertas: nenhum mês disponível para {year}.")
        for column in ADDITIVE_COLUMNS:
            _assert_close(
                monthly_year[column].sum(),
                annual_row[column],
                message=f"bases de ofertas: {column} não reconcilia em {year}.",
            )

    annual_2026 = annual.loc[annual["year"].eq(2026)].iloc[0]
    if int(originators["universe_closed_offers"].iloc[0]) != int(annual_2026["closed_offers"]):
        raise ClosedOffersDataError("bases de ofertas: universo de originadores diverge das ofertas anuais de 2026.")
    _assert_close(
        originators["universe_registered_volume_brl"].iloc[0],
        annual_2026["registered_volume_brl"],
        message="bases de ofertas: volume dos originadores diverge das ofertas anuais de 2026.",
    )


def load_closed_offers_tables(data_dir: str | Path = INDUSTRY_STUDY_DIR) -> ClosedOffersTables:
    root = Path(data_dir)
    tables = ClosedOffersTables(
        annual=load_closed_offers_annual(root / ANNUAL_FILENAME),
        monthly=load_closed_offers_monthly(root / MONTHLY_FILENAME),
        originators=load_closed_offer_originators(root / ORIGINATORS_FILENAME),
    )
    _validate_cross_table_reconciliation(tables)
    return tables


def _json_scalar(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ClosedOffersDataError("payload de ofertas contém número não finito.")
        return value
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if pd.isna(value):
        return None
    return str(value)


def _records(frame: pd.DataFrame, columns: Iterable[str]) -> list[dict[str, Any]]:
    selected = list(columns)
    return [
        {column: _json_scalar(value) for column, value in row.items()}
        for row in frame.loc[:, selected].to_dict(orient="records")
    ]


def _payload_block(
    frame: pd.DataFrame,
    *,
    block_name: str,
    row_columns: Iterable[str],
    extra_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    columns = list(row_columns)
    source = _uniform_source(frame, name=block_name)
    source.update({key: _json_scalar(value) for key, value in (extra_source or {}).items()})
    block = {
        "schema": f"{PAYLOAD_SCHEMA_VERSION}.{block_name}",
        "columns": columns,
        "row_count": int(len(frame)),
        "rows": _records(frame, columns),
        "source": source,
    }
    json.dumps(block, ensure_ascii=False, allow_nan=False)
    return block


def build_closed_offers_annual_payload(frame: pd.DataFrame) -> dict[str, Any]:
    normalized = validate_closed_offers_annual(frame)
    row_columns = [column for column in ANNUAL_COLUMNS if column not in SOURCE_COLUMNS]
    return _payload_block(normalized, block_name="annual", row_columns=row_columns)


def build_closed_offers_monthly_payload(frame: pd.DataFrame) -> dict[str, Any]:
    normalized = validate_closed_offers_monthly(frame)
    row_columns = [column for column in MONTHLY_COLUMNS if column not in SOURCE_COLUMNS]
    return _payload_block(normalized, block_name="monthly", row_columns=row_columns)


def build_closed_offer_originators_payload(frame: pd.DataFrame) -> dict[str, Any]:
    normalized = validate_closed_offer_originators(frame)
    row_columns = [
        column
        for column in ORIGINATOR_COLUMNS
        if column not in SOURCE_COLUMNS and column != "originator_methodology"
    ]
    return _payload_block(
        normalized,
        block_name="originators_2026_ytd",
        row_columns=row_columns,
        extra_source={"originator_methodology": normalized["originator_methodology"].iloc[0]},
    )


def _weighted_numerator(frame: pd.DataFrame, share_column: str, weight_column: str) -> float:
    return float((frame[share_column] * frame[weight_column]).sum())


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def build_jan_june_closed_offers_payload(monthly: pd.DataFrame) -> dict[str, Any]:
    normalized = validate_closed_offers_monthly(monthly)
    rows: list[dict[str, Any]] = []
    for year in JAN_JUNE_YEARS:
        period = normalized.loc[normalized["year"].eq(year) & normalized["month"].between(1, 6)].copy()
        if set(period["month"]) != {1, 2, 3, 4, 5, 6}:
            raise ClosedOffersDataError(f"recorte jan–jun: meses incompletos para {year}.")
        if not period["is_complete_month"].all():
            raise ClosedOffersDataError(f"recorte jan–jun: há mês parcial em {year}.")

        closed_offers = int(period["closed_offers"].sum())
        registered_volume = float(period["registered_volume_brl"].sum())
        offers_with_registered_quantity = int(period["offers_with_registered_quantity"].sum())
        offers_with_placed_quantity = int(period["offers_with_placed_quantity"].sum())
        placed_volume = float(period["placed_volume_proxy_brl"].sum())
        offers_with_investor_count = int(period["offers_with_investor_count_data"].sum())
        offers_with_up_to_5 = int(period["offers_with_up_to_5_investors"].sum())
        offers_with_natural_person = int(period["offers_with_natural_person"].sum())

        registered_quantity_covered_volume = _weighted_numerator(
            period, "registered_quantity_volume_coverage", "registered_volume_brl"
        )
        placed_quantity_covered_volume = _weighted_numerator(
            period, "placed_quantity_registered_volume_coverage", "registered_volume_brl"
        )
        investor_count_covered_volume = _weighted_numerator(
            period, "investor_count_registered_volume_coverage", "registered_volume_brl"
        )
        # The monthly share is relative to covered registered volume. Rebuild its
        # numerator explicitly before aggregating across months.
        up_to_5_covered_volume = float(
            (
                period["up_to_5_investors_registered_volume_share_covered"]
                * period["investor_count_registered_volume_coverage"]
                * period["registered_volume_brl"]
            ).sum()
        )

        professional = float(period["professional_target_registered_volume_brl"].sum())
        qualified = float(period["qualified_target_registered_volume_brl"].sum())
        general = float(period["general_target_registered_volume_brl"].sum())
        natural_person_volume = float(period["natural_person_placed_volume_proxy_brl"].sum())
        rows.append(
            {
                "year": year,
                "period_label": f"jan–jun/{str(year)[-2:]}",
                "period_start": f"{year}-01-01",
                "period_end": f"{year}-06-30",
                "closed_offers": closed_offers,
                "registered_volume_brl": registered_volume,
                "mean_registered_ticket_brl": _safe_ratio(registered_volume, closed_offers),
                "offers_with_registered_quantity": offers_with_registered_quantity,
                "registered_quantity_offer_coverage": _safe_ratio(
                    offers_with_registered_quantity, closed_offers
                ),
                "registered_quantity_volume_coverage": _safe_ratio(
                    registered_quantity_covered_volume, registered_volume
                ),
                "offers_with_placed_quantity": offers_with_placed_quantity,
                "placed_quantity_offer_coverage": _safe_ratio(offers_with_placed_quantity, closed_offers),
                "placed_quantity_registered_volume_coverage": _safe_ratio(
                    placed_quantity_covered_volume, registered_volume
                ),
                "placed_volume_proxy_brl": placed_volume,
                "mean_placed_ticket_brl": _safe_ratio(placed_volume, offers_with_placed_quantity),
                "placed_proxy_share_of_registered_covered": _safe_ratio(
                    placed_volume, placed_quantity_covered_volume
                ),
                "offers_with_investor_count_data": offers_with_investor_count,
                "investor_count_offer_coverage": _safe_ratio(offers_with_investor_count, closed_offers),
                "investor_count_registered_volume_coverage": _safe_ratio(
                    investor_count_covered_volume, registered_volume
                ),
                "offers_with_up_to_5_investors": offers_with_up_to_5,
                "up_to_5_investors_offer_share_covered": _safe_ratio(
                    offers_with_up_to_5, offers_with_investor_count
                ),
                "up_to_5_investors_registered_volume_share_covered": _safe_ratio(
                    up_to_5_covered_volume, investor_count_covered_volume
                ),
                "professional_target_registered_volume_brl": professional,
                "professional_target_registered_volume_share": _safe_ratio(
                    professional, registered_volume
                ),
                "qualified_target_registered_volume_brl": qualified,
                "qualified_target_registered_volume_share": _safe_ratio(qualified, registered_volume),
                "general_target_registered_volume_brl": general,
                "general_target_registered_volume_share": _safe_ratio(general, registered_volume),
                "natural_person_accounts": int(period["natural_person_accounts"].sum()),
                "offers_with_natural_person": offers_with_natural_person,
                "natural_person_offer_presence_share_covered": _safe_ratio(
                    offers_with_natural_person, offers_with_investor_count
                ),
                "natural_person_placed_volume_proxy_brl": natural_person_volume,
                "natural_person_placed_volume_share": _safe_ratio(natural_person_volume, placed_volume),
            }
        )

    row_columns = list(rows[0])
    block = {
        "schema": f"{PAYLOAD_SCHEMA_VERSION}.jan_june_2024_2026",
        "columns": row_columns,
        "row_count": len(rows),
        "rows": rows,
        "source": {
            **_uniform_source(normalized, name="recorte jan–jun"),
            "cohort": "Data_Encerramento entre 1º de janeiro e 30 de junho de cada ano",
            "median_disclosure": "Medianas mensais não são agregadas; o recorte publica apenas médias recalculadas.",
        },
    }
    json.dumps(block, ensure_ascii=False, allow_nan=False)
    return block


def build_jan_may_closed_offers_payload(monthly: pd.DataFrame) -> dict[str, Any]:
    """Compatibility alias; the current comparable period is January–June."""

    return build_jan_june_closed_offers_payload(monthly)


def list_nominable_originators_2026_ytd(frame: pd.DataFrame) -> list[dict[str, Any]]:
    block = build_closed_offer_originators_payload(frame)
    return list(block["rows"])


def build_closed_offers_payload(data_dir: str | Path = INDUSTRY_STUDY_DIR) -> dict[str, Any]:
    tables = load_closed_offers_tables(data_dir)
    payload = {
        "schema": PAYLOAD_SCHEMA_VERSION,
        "annual": build_closed_offers_annual_payload(tables.annual),
        "monthly": build_closed_offers_monthly_payload(tables.monthly),
        "jan_june_2024_2026": build_jan_june_closed_offers_payload(tables.monthly),
        # Retained for one release so older site/export readers do not reject
        # the payload.  The row labels and dates explicitly say jan–jun.
        "jan_may_2024_2026": build_jan_june_closed_offers_payload(tables.monthly),
        "originators_2026_ytd": build_closed_offer_originators_payload(tables.originators),
    }
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return payload


__all__ = [
    "ANNUAL_FILENAME",
    "ClosedOffersDataError",
    "ClosedOffersTables",
    "INDUSTRY_STUDY_DIR",
    "JAN_MAY_YEARS",
    "JAN_JUNE_YEARS",
    "MONTHLY_FILENAME",
    "ORIGINATORS_FILENAME",
    "PAYLOAD_SCHEMA_VERSION",
    "build_closed_offer_originators_payload",
    "build_closed_offers_annual_payload",
    "build_closed_offers_monthly_payload",
    "build_closed_offers_payload",
    "build_jan_may_closed_offers_payload",
    "build_jan_june_closed_offers_payload",
    "list_nominable_originators_2026_ytd",
    "load_closed_offer_originators",
    "load_closed_offers_annual",
    "load_closed_offers_monthly",
    "load_closed_offers_tables",
    "validate_closed_offer_originators",
    "validate_closed_offers_annual",
    "validate_closed_offers_monthly",
]
