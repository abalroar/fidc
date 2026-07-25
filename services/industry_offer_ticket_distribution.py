"""Auditable ticket distribution for closed primary FIDC offerings.

The source is the CVM public-offerings archive.  One offer is one
``Numero_Requerimento`` and cohorts are determined by ``Data_Encerramento``.
Only primary, closed ``Cotas de FIDC`` offerings with positive registered
volume are retained.  FIAGRO-FIDC offerings are outside this scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
from typing import Any

import numpy as np
import pandas as pd

from services.industry_public_offers import (
    FIDC_CANONICAL,
    PublicOffersError,
    SOURCE_DATASET_LABEL,
    SOURCE_URL,
    load_public_primary_closed_offers,
)

INDUSTRY_STUDY_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"

SOURCE_DATASET = SOURCE_DATASET_LABEL
SOURCE_AS_OF_DATE = "2026-07-21"
EXPECTED_SOURCE_ARCHIVE_SHA256 = (
    "46a5a3c35e500dd4560a5a4b286a7a302311ea02b397c1a67821bc197514b4e5"
)

DISTRIBUTION_FILENAME = "industry_closed_offer_ticket_distribution.csv"
COHORT_FILENAME = "industry_closed_offer_ticket_cohort.csv.gz"

SCOPE = (
    "Cotas de FIDC | oferta pública primária encerrada | todos os ritos CVM | "
    "data de encerramento no período | volume registrado positivo"
)
DEDUPLICATION = (
    "Rito automático: Numero_Requerimento. Ritos ordinários/legados: registro + "
    "emissor + data de encerramento + instrumento; classes do mesmo FIDC são somadas."
)
METHODOLOGY = (
    "Coorte por Data_Encerramento; ticket = Valor_Total_Registrado. "
    "2024 e 2025 usam o ano completo; 2026 usa 1 jan a 30 jun. "
    "Os buckets são fechados à esquerda e abertos à direita, exceto o último."
)

PERIODS = (
    (1, "2024 FY", "2024-01-01", "2024-12-31", True),
    (2, "2025 FY", "2025-01-01", "2025-12-31", True),
    (3, "2026 jan-jun", "2026-01-01", "2026-06-30", False),
)

# The cuts separate the dense sub-R$50m population from the economically
# material upper tail.  Every bucket is populated in each published period.
TICKET_BUCKETS = (
    (1, "< R$ 10 mi", 0.0, 10_000_000.0),
    (2, "R$ 10–25 mi", 10_000_000.0, 25_000_000.0),
    (3, "R$ 25–50 mi", 25_000_000.0, 50_000_000.0),
    (4, "R$ 50–100 mi", 50_000_000.0, 100_000_000.0),
    (5, "R$ 100–200 mi", 100_000_000.0, 200_000_000.0),
    (6, "R$ 200–500 mi", 200_000_000.0, 500_000_000.0),
    (7, "≥ R$ 500 mi", 500_000_000.0, math.inf),
)

REQUIRED_SOURCE_COLUMNS = (
    "Numero_Requerimento",
    "Data_Encerramento",
    "Status_Requerimento",
    "Valor_Mobiliario",
    "Tipo_Oferta",
    "CNPJ_Emissor",
    "Nome_Emissor",
    "Valor_Total_Registrado",
)

COHORT_COLUMNS = (
    "period_order",
    "period_label",
    "period_start",
    "period_end",
    "is_full_year",
    "numero_requerimento",
    "data_encerramento",
    "cnpj_emissor",
    "nome_emissor",
    "registered_volume_brl",
    "bucket_order",
    "ticket_bucket",
    "ticket_floor_brl",
    "ticket_ceiling_brl",
    "source_dataset",
    "source_url",
    "source_as_of_date",
    "source_archive_sha256",
    "scope",
    "deduplication",
)

DISTRIBUTION_COLUMNS = (
    "period_order",
    "period_label",
    "period_start",
    "period_end",
    "is_full_year",
    "bucket_order",
    "ticket_bucket",
    "ticket_floor_brl",
    "ticket_ceiling_brl",
    "closed_offers",
    "offer_share",
    "registered_volume_brl",
    "registered_volume_share",
    "period_closed_offers",
    "period_registered_volume_brl",
    "period_mean_ticket_brl",
    "period_median_ticket_brl",
    "period_p25_ticket_brl",
    "period_p75_ticket_brl",
    "period_p90_ticket_brl",
    "source_dataset",
    "source_url",
    "source_as_of_date",
    "source_archive_sha256",
    "scope",
    "deduplication",
    "methodology",
)


class OfferTicketDataError(ValueError):
    """Raised when the offer-ticket source or output violates its contract."""


@dataclass(frozen=True)
class OfferTicketOutputs:
    cohort: pd.DataFrame
    distribution: pd.DataFrame


def _normalize_cnpj(series: pd.Series) -> pd.Series:
    return series.astype(str).str.replace(r"\D", "", regex=True)


def _deduplicate_offers(frame: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate identical requirement rows and reject conflicting ones."""

    if frame["Numero_Requerimento"].eq("").any():
        raise OfferTicketDataError("Numero_Requerimento vazio na coorte selecionada.")
    duplicate_mask = frame.duplicated("Numero_Requerimento", keep=False)
    if not duplicate_mask.any():
        return frame.copy()

    comparison_columns = [
        "Data_Encerramento",
        "CNPJ_Emissor",
        "Nome_Emissor",
        "Valor_Total_Registrado",
        "Valor_Mobiliario",
        "Tipo_Oferta",
        "Status_Requerimento",
    ]
    conflicts: list[str] = []
    for requirement, group in frame.loc[duplicate_mask].groupby("Numero_Requerimento"):
        if len(group.loc[:, comparison_columns].drop_duplicates()) != 1:
            conflicts.append(str(requirement))
    if conflicts:
        sample = ", ".join(conflicts[:5])
        raise OfferTicketDataError(
            f"Numero_Requerimento com linhas conflitantes: {sample}"
        )
    return frame.drop_duplicates("Numero_Requerimento", keep="first").copy()


def _assign_period(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["period_order"] = pd.NA
    result["period_label"] = ""
    result["period_start"] = ""
    result["period_end"] = ""
    result["is_full_year"] = False
    for order, label, start, end, full_year in PERIODS:
        mask = result["data_encerramento"].between(start, end)
        result.loc[mask, "period_order"] = order
        result.loc[mask, "period_label"] = label
        result.loc[mask, "period_start"] = start
        result.loc[mask, "period_end"] = end
        result.loc[mask, "is_full_year"] = full_year
    result = result[result["period_label"].ne("")].copy()
    result["period_order"] = result["period_order"].astype(int)
    return result


def _assign_ticket_bucket(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["bucket_order"] = pd.NA
    result["ticket_bucket"] = ""
    result["ticket_floor_brl"] = np.nan
    result["ticket_ceiling_brl"] = np.nan
    for order, label, floor, ceiling in TICKET_BUCKETS:
        mask = result["registered_volume_brl"].ge(floor)
        if math.isfinite(ceiling):
            mask &= result["registered_volume_brl"].lt(ceiling)
        result.loc[mask, "bucket_order"] = order
        result.loc[mask, "ticket_bucket"] = label
        result.loc[mask, "ticket_floor_brl"] = floor
        result.loc[mask, "ticket_ceiling_brl"] = ceiling
    if result["ticket_bucket"].eq("").any():
        raise OfferTicketDataError("Há tickets positivos fora dos buckets publicados.")
    result["bucket_order"] = result["bucket_order"].astype(int)
    return result


def load_closed_offer_ticket_cohort(
    archive_path: str | Path,
    *,
    source_as_of_date: str = SOURCE_AS_OF_DATE,
    expected_archive_sha256: str | None = EXPECTED_SOURCE_ARCHIVE_SHA256,
) -> pd.DataFrame:
    """Read the official archive and return the three published cohorts."""

    try:
        selected, archive_digest = load_public_primary_closed_offers(
            archive_path,
            cutoff="2026-06-30",
            expected_archive_sha256=expected_archive_sha256,
        )
    except PublicOffersError as exc:
        raise OfferTicketDataError(str(exc)) from exc
    selected = selected[
        selected["canonical_instrument"].eq(FIDC_CANONICAL)
    ].copy()

    cohort = pd.DataFrame(
        {
            "numero_requerimento": selected["offer_id"].str.strip(),
            "data_encerramento": selected["closing_date"].dt.strftime("%Y-%m-%d"),
            "cnpj_emissor": _normalize_cnpj(selected["issuer_cnpj"]),
            "nome_emissor": selected["issuer_name"].str.strip(),
            "registered_volume_brl": selected["registered_volume_brl"].astype(float),
            "source_dataset": selected["source_dataset"],
        }
    )
    cohort = _assign_period(cohort)
    cohort = _assign_ticket_bucket(cohort)
    cohort["source_url"] = SOURCE_URL
    cohort["source_as_of_date"] = source_as_of_date
    cohort["source_archive_sha256"] = archive_digest
    cohort["scope"] = SCOPE
    cohort["deduplication"] = DEDUPLICATION
    cohort = cohort.loc[:, COHORT_COLUMNS]
    return validate_offer_ticket_cohort(cohort)


def validate_offer_ticket_cohort(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in COHORT_COLUMNS if column not in frame]
    if missing:
        raise OfferTicketDataError(
            "Coorte de tickets sem colunas obrigatórias: " + ", ".join(missing)
        )
    result = frame.loc[:, COHORT_COLUMNS].copy()
    result["registered_volume_brl"] = pd.to_numeric(
        result["registered_volume_brl"], errors="coerce"
    )
    result["period_order"] = pd.to_numeric(result["period_order"], errors="coerce")
    result["bucket_order"] = pd.to_numeric(result["bucket_order"], errors="coerce")
    if result["registered_volume_brl"].isna().any() or result["registered_volume_brl"].le(0).any():
        raise OfferTicketDataError("Coorte contém ticket ausente ou não positivo.")
    if result["numero_requerimento"].astype(str).duplicated().any():
        raise OfferTicketDataError("Coorte contém Numero_Requerimento duplicado.")
    expected_periods = {period[1] for period in PERIODS}
    unexpected_periods = set(result["period_label"].astype(str)) - expected_periods
    if unexpected_periods:
        raise OfferTicketDataError(
            "Coorte contém período fora do contrato: "
            + ", ".join(sorted(unexpected_periods))
        )
    return result.sort_values(
        ["period_order", "data_encerramento", "numero_requerimento"]
    ).reset_index(drop=True)


def build_offer_ticket_distribution(cohort: pd.DataFrame) -> pd.DataFrame:
    """Aggregate a validated offer cohort into stable chart buckets."""

    validated = validate_offer_ticket_cohort(cohort)
    expected_periods = {period[1] for period in PERIODS}
    if set(validated["period_label"].astype(str)) != expected_periods:
        raise OfferTicketDataError(
            "A distribuição requer exatamente os três períodos publicados."
        )
    rows: list[dict[str, Any]] = []
    metadata_columns = [
        "source_dataset",
        "source_url",
        "source_as_of_date",
        "source_archive_sha256",
        "scope",
        "deduplication",
    ]
    for order, label, start, end, full_year in PERIODS:
        period = validated[validated["period_label"].eq(label)].copy()
        period_count = int(len(period))
        period_volume = float(period["registered_volume_brl"].sum())
        period_metrics = {
            "period_closed_offers": period_count,
            "period_registered_volume_brl": period_volume,
            "period_mean_ticket_brl": float(period["registered_volume_brl"].mean()),
            "period_median_ticket_brl": float(period["registered_volume_brl"].median()),
            "period_p25_ticket_brl": float(period["registered_volume_brl"].quantile(0.25)),
            "period_p75_ticket_brl": float(period["registered_volume_brl"].quantile(0.75)),
            "period_p90_ticket_brl": float(period["registered_volume_brl"].quantile(0.90)),
        }
        metadata = {column: str(period.iloc[0][column]) for column in metadata_columns}
        for bucket_order, bucket_label, floor, ceiling in TICKET_BUCKETS:
            bucket = period[period["bucket_order"].eq(bucket_order)]
            bucket_count = int(len(bucket))
            bucket_volume = float(bucket["registered_volume_brl"].sum())
            rows.append(
                {
                    "period_order": order,
                    "period_label": label,
                    "period_start": start,
                    "period_end": end,
                    "is_full_year": full_year,
                    "bucket_order": bucket_order,
                    "ticket_bucket": bucket_label,
                    "ticket_floor_brl": floor,
                    "ticket_ceiling_brl": ceiling,
                    "closed_offers": bucket_count,
                    "offer_share": bucket_count / period_count,
                    "registered_volume_brl": bucket_volume,
                    "registered_volume_share": bucket_volume / period_volume,
                    **period_metrics,
                    **metadata,
                    "methodology": METHODOLOGY,
                }
            )
    return validate_offer_ticket_distribution(pd.DataFrame(rows))


def validate_offer_ticket_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in DISTRIBUTION_COLUMNS if column not in frame]
    if missing:
        raise OfferTicketDataError(
            "Distribuição de tickets sem colunas obrigatórias: " + ", ".join(missing)
        )
    result = frame.loc[:, DISTRIBUTION_COLUMNS].copy()
    numeric_columns = [
        "period_order",
        "bucket_order",
        "ticket_floor_brl",
        "ticket_ceiling_brl",
        "closed_offers",
        "offer_share",
        "registered_volume_brl",
        "registered_volume_share",
        "period_closed_offers",
        "period_registered_volume_brl",
        "period_mean_ticket_brl",
        "period_median_ticket_brl",
        "period_p25_ticket_brl",
        "period_p75_ticket_brl",
        "period_p90_ticket_brl",
    ]
    for column in numeric_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    if result[numeric_columns].isna().any().any():
        raise OfferTicketDataError("Distribuição contém métrica numérica ausente.")
    if len(result) != len(PERIODS) * len(TICKET_BUCKETS):
        raise OfferTicketDataError("Distribuição deve conter 7 buckets por período.")
    for label, period in result.groupby("period_label", sort=False):
        if period["bucket_order"].nunique() != len(TICKET_BUCKETS):
            raise OfferTicketDataError(f"Buckets incompletos em {label}.")
        if not math.isclose(float(period["offer_share"].sum()), 1.0, abs_tol=1e-12):
            raise OfferTicketDataError(f"Shares de quantidade não fecham em {label}.")
        if not math.isclose(
            float(period["registered_volume_share"].sum()), 1.0, abs_tol=1e-12
        ):
            raise OfferTicketDataError(f"Shares de volume não fecham em {label}.")
        if int(period["closed_offers"].sum()) != int(period["period_closed_offers"].iloc[0]):
            raise OfferTicketDataError(f"Contagem por bucket não reconcilia em {label}.")
        if not math.isclose(
            float(period["registered_volume_brl"].sum()),
            float(period["period_registered_volume_brl"].iloc[0]),
            abs_tol=0.01,
        ):
            raise OfferTicketDataError(f"Volume por bucket não reconcilia em {label}.")
    return result.sort_values(["period_order", "bucket_order"]).reset_index(drop=True)


def load_materialized_offer_ticket_outputs(
    data_dir: str | Path = INDUSTRY_STUDY_DIR,
) -> OfferTicketOutputs:
    root = Path(data_dir)
    cohort = pd.read_csv(root / COHORT_FILENAME, dtype=str, keep_default_na=False)
    distribution = pd.read_csv(
        root / DISTRIBUTION_FILENAME, dtype=str, keep_default_na=False
    )
    return OfferTicketOutputs(
        cohort=validate_offer_ticket_cohort(cohort),
        distribution=validate_offer_ticket_distribution(distribution),
    )


def write_offer_ticket_outputs(
    outputs: OfferTicketOutputs,
    data_dir: str | Path = INDUSTRY_STUDY_DIR,
) -> dict[str, Any]:
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    cohort = validate_offer_ticket_cohort(outputs.cohort)
    distribution = validate_offer_ticket_distribution(outputs.distribution)
    cohort.to_csv(
        root / COHORT_FILENAME,
        index=False,
        compression={"method": "gzip", "compresslevel": 9, "mtime": 0},
    )
    distribution.to_csv(root / DISTRIBUTION_FILENAME, index=False)
    return {
        "cohort_path": str(root / COHORT_FILENAME),
        "distribution_path": str(root / DISTRIBUTION_FILENAME),
        "cohort_rows": int(len(cohort)),
        "distribution_rows": int(len(distribution)),
        "source_archive_sha256": str(cohort["source_archive_sha256"].iloc[0]),
    }


def build_offer_ticket_outputs(
    archive_path: str | Path,
    *,
    source_as_of_date: str = SOURCE_AS_OF_DATE,
    expected_archive_sha256: str | None = EXPECTED_SOURCE_ARCHIVE_SHA256,
) -> OfferTicketOutputs:
    cohort = load_closed_offer_ticket_cohort(
        archive_path,
        source_as_of_date=source_as_of_date,
        expected_archive_sha256=expected_archive_sha256,
    )
    return OfferTicketOutputs(
        cohort=cohort,
        distribution=build_offer_ticket_distribution(cohort),
    )


__all__ = [
    "COHORT_FILENAME",
    "DISTRIBUTION_FILENAME",
    "EXPECTED_SOURCE_ARCHIVE_SHA256",
    "INDUSTRY_STUDY_DIR",
    "OfferTicketDataError",
    "OfferTicketOutputs",
    "PERIODS",
    "SOURCE_AS_OF_DATE",
    "SOURCE_URL",
    "TICKET_BUCKETS",
    "build_offer_ticket_distribution",
    "build_offer_ticket_outputs",
    "load_closed_offer_ticket_cohort",
    "load_materialized_offer_ticket_outputs",
    "validate_offer_ticket_cohort",
    "validate_offer_ticket_distribution",
    "write_offer_ticket_outputs",
]
