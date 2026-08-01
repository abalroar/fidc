"""Materialize placement-regime views for closed primary FIDC offerings.

The offer-level cohort defines the audited universe and periods.  The official
``Regime_distribuicao`` field is joined from the same CVM public-offering
snapshot by ``Numero_Requerimento``.  No missing regime is imputed.
"""

from __future__ import annotations

from pathlib import Path
import unicodedata

import numpy as np
import pandas as pd

from services.industry_public_offers import (
    FIDC_CANONICAL,
    SOURCE_DATASET_LABEL,
    SOURCE_URL,
    load_public_primary_closed_offers,
)

SOURCE_DATASET = SOURCE_DATASET_LABEL
SOURCE_AS_OF_DATE = "2026-07-24"
SOURCE_ARCHIVE_SHA256 = (
    "46a5a3c35e500dd4560a5a4b286a7a302311ea02b397c1a67821bc197514b4e5"
)
COHORT_FILENAME = "industry_closed_offer_ticket_cohort.csv.gz"
OUTPUT_FILENAME = "industry_closed_offer_placement_regime.csv"
PERIODS = ("2024 FY", "2025 FY", "2026 jan-jun")
REGIME_ORDER = (
    "Melhores esforços",
    "Garantia firme",
    "Misto",
    "Não informado",
)

OUTPUT_COLUMNS = (
    "period_order",
    "period_label",
    "period_start",
    "period_end",
    "is_full_year",
    "regime_order",
    "placement_regime",
    "closed_offers",
    "closed_offers_share",
    "registered_volume_brl",
    "registered_volume_share",
    "comparison_period_label",
    "comparison_period_start",
    "comparison_period_end",
    "comparison_closed_offers",
    "comparison_registered_volume_brl",
    "registered_volume_yoy_ytd",
    "period_closed_offers",
    "period_registered_volume_brl",
    "source_dataset",
    "source_url",
    "source_as_of_date",
    "source_archive_sha256",
    "scope",
    "methodology",
)


class ClosedOfferPlacementRegimeError(ValueError):
    """Raised when the placement-regime table violates its contract."""


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(
        character for character in text
        if not unicodedata.combining(character)
    )
    return " ".join(text.upper().split())


def _regime_bucket(value: object) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        return "Não informado"
    if "MELHORES ESFORCOS" in normalized:
        return "Melhores esforços"
    if "GARANTIA FIRME" in normalized:
        return "Garantia firme"
    if normalized == "MISTO":
        return "Misto"
    raise ClosedOfferPlacementRegimeError(
        f"Regime_distribuicao não mapeado: {value!r}"
    )


def _read_source(
    archive_path: str | Path,
    *,
    expected_archive_sha256: str | None,
) -> tuple[pd.DataFrame, str]:
    source, digest = load_public_primary_closed_offers(
        archive_path,
        cutoff="2026-06-30",
        expected_archive_sha256=expected_archive_sha256,
    )
    source = source[
        source["canonical_instrument"].eq(FIDC_CANONICAL)
    ].copy()
    return source, digest


def build_closed_offer_placement_regime(
    data_dir: str | Path,
    archive_path: str | Path,
    *,
    source_as_of_date: str = SOURCE_AS_OF_DATE,
    expected_archive_sha256: str | None = SOURCE_ARCHIVE_SHA256,
) -> pd.DataFrame:
    """Build the three-period count and volume breakdown by placement regime."""

    root = Path(data_dir)
    cohort_path = root / COHORT_FILENAME
    if not cohort_path.is_file():
        raise FileNotFoundError(f"Coorte de ofertas ausente: {cohort_path}")
    cohort = pd.read_csv(cohort_path, dtype=str, low_memory=False).rename(
        columns={"numero_requerimento": "offer_id"}
    )
    required_cohort = {
        "offer_id",
        "period_order",
        "period_label",
        "period_start",
        "period_end",
        "data_encerramento",
        "is_full_year",
        "registered_volume_brl",
    }
    missing = sorted(required_cohort.difference(cohort.columns))
    if missing:
        raise ClosedOfferPlacementRegimeError(
            "Coorte sem colunas obrigatórias: " + ", ".join(missing)
        )
    cohort = cohort[cohort["period_label"].isin(PERIODS)].copy()
    observed_periods = tuple(
        cohort.sort_values("period_order")["period_label"].drop_duplicates()
    )
    if observed_periods != PERIODS:
        raise ClosedOfferPlacementRegimeError(
            f"Períodos esperados {PERIODS}; observados {observed_periods}."
        )
    cohort["offer_id"] = cohort["offer_id"].str.strip()
    cohort["registered_volume_brl"] = pd.to_numeric(
        cohort["registered_volume_brl"], errors="coerce"
    )
    if (
        cohort["offer_id"].eq("").any()
        or cohort["offer_id"].duplicated().any()
        or cohort["registered_volume_brl"].isna().any()
        or cohort["registered_volume_brl"].le(0).any()
    ):
        raise ClosedOfferPlacementRegimeError(
            "Coorte contém identificador duplicado/vazio ou volume inválido."
        )

    source, digest = _read_source(
        archive_path,
        expected_archive_sha256=expected_archive_sha256,
    )
    source_regime = source[
            [
                "offer_id",
                "status_norm",
                "offer_type_norm",
                "distribution_regime",
            ]
        ].rename(columns={"distribution_regime": "source_distribution_regime"})
    joined = cohort.merge(
        source_regime,
        on="offer_id",
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if not joined["_merge"].eq("both").all():
        missing_ids = joined.loc[
            joined["_merge"].ne("both"), "offer_id"
        ].head(5).tolist()
        raise ClosedOfferPlacementRegimeError(
            "Coorte sem correspondência na fonte CVM: " + ", ".join(missing_ids)
        )
    if not joined["status_norm"].map(_normalize_text).eq(
        "OFERTA ENCERRADA"
    ).all():
        raise ClosedOfferPlacementRegimeError(
            "Coorte contém status diferente de Oferta Encerrada na fonte."
        )
    if not joined["offer_type_norm"].map(_normalize_text).eq("PRIMARIA").all():
        raise ClosedOfferPlacementRegimeError(
            "Coorte contém oferta diferente de primária na fonte."
        )
    joined["placement_regime"] = joined["source_distribution_regime"].map(
        _regime_bucket
    )
    joined["data_encerramento"] = pd.to_datetime(
        joined["data_encerramento"], errors="coerce"
    )
    if joined["data_encerramento"].isna().any():
        raise ClosedOfferPlacementRegimeError(
            "Coorte contém data de encerramento inválida."
        )
    comparable_ytd = joined[
        joined["data_encerramento"].between(
            pd.Timestamp("2025-01-01"), pd.Timestamp("2025-06-30")
        )
    ].copy()

    scope = (
        "Cotas de FIDC | oferta pública primária encerrada | todos os ritos CVM | "
        "data de encerramento no período | volume registrado positivo"
    )
    methodology = (
        "Rito automático: uma oferta = Numero_Requerimento. Ritos ordinários "
        "e legados usam a chave reconciliada do estudo. Regime usa o campo "
        "oficial Regime_distribuicao quando disponível; ausência permanece "
        "Não informado. 2024/2025 são anos completos; 2026 cobre janeiro a junho."
    )
    rows: list[dict[str, object]] = []
    for period_label in PERIODS:
        period = joined[joined["period_label"].eq(period_label)].copy()
        period_offers = int(period["offer_id"].nunique())
        period_volume = float(period["registered_volume_brl"].sum())
        template = period.iloc[0]
        for regime_order, regime in enumerate(REGIME_ORDER, start=1):
            group = period[period["placement_regime"].eq(regime)]
            offers = int(group["offer_id"].nunique())
            volume = float(group["registered_volume_brl"].sum())
            comparable_group = comparable_ytd[
                comparable_ytd["placement_regime"].eq(regime)
            ]
            comparison_offers = int(comparable_group["offer_id"].nunique())
            comparison_volume = float(
                comparable_group["registered_volume_brl"].sum()
            )
            has_ytd_comparison = period_label == "2026 jan-jun"
            rows.append(
                {
                    "period_order": int(template["period_order"]),
                    "period_label": period_label,
                    "period_start": template["period_start"],
                    "period_end": template["period_end"],
                    "is_full_year": str(template["is_full_year"]).strip().casefold()
                    in {"true", "1"},
                    "regime_order": regime_order,
                    "placement_regime": regime,
                    "closed_offers": offers,
                    "closed_offers_share": (
                        offers / period_offers if period_offers else 0.0
                    ),
                    "registered_volume_brl": volume,
                    "registered_volume_share": (
                        volume / period_volume if period_volume else 0.0
                    ),
                    "comparison_period_label": (
                        "2025 jan-jun" if has_ytd_comparison else "N/D"
                    ),
                    "comparison_period_start": (
                        "2025-01-01" if has_ytd_comparison else "N/D"
                    ),
                    "comparison_period_end": (
                        "2025-06-30" if has_ytd_comparison else "N/D"
                    ),
                    "comparison_closed_offers": (
                        comparison_offers if has_ytd_comparison else np.nan
                    ),
                    "comparison_registered_volume_brl": (
                        comparison_volume if has_ytd_comparison else np.nan
                    ),
                    "registered_volume_yoy_ytd": (
                        volume / comparison_volume - 1.0
                        if has_ytd_comparison and comparison_volume > 0
                        else np.nan
                    ),
                    "period_closed_offers": period_offers,
                    "period_registered_volume_brl": period_volume,
                    "source_dataset": SOURCE_DATASET,
                    "source_url": SOURCE_URL,
                    "source_as_of_date": source_as_of_date,
                    "source_archive_sha256": digest,
                    "scope": scope,
                    "methodology": methodology,
                }
            )
    return validate_closed_offer_placement_regime(
        pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    )


def validate_closed_offer_placement_regime(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    missing = [column for column in OUTPUT_COLUMNS if column not in frame]
    if missing:
        raise ClosedOfferPlacementRegimeError(
            "Tabela de regime sem colunas: " + ", ".join(missing)
        )
    result = frame.loc[:, OUTPUT_COLUMNS].copy()
    expected_rows = len(PERIODS) * len(REGIME_ORDER)
    if len(result) != expected_rows:
        raise ClosedOfferPlacementRegimeError(
            f"Tabela deveria conter {expected_rows} linhas; contém {len(result)}."
        )
    if result.duplicated(["period_label", "placement_regime"]).any():
        raise ClosedOfferPlacementRegimeError(
            "Tabela de regime contém chaves duplicadas."
        )
    observed_periods = tuple(
        result.sort_values("period_order")["period_label"].drop_duplicates()
    )
    if observed_periods != PERIODS:
        raise ClosedOfferPlacementRegimeError(
            "Tabela de regime contém períodos inesperados."
        )
    for period_label, period in result.groupby("period_label", sort=False):
        observed_regimes = tuple(
            period.sort_values("regime_order")["placement_regime"]
        )
        if observed_regimes != REGIME_ORDER:
            raise ClosedOfferPlacementRegimeError(
                f"{period_label}: regimes ou ordem inesperados."
            )
    numeric_columns = (
        "period_order",
        "regime_order",
        "closed_offers",
        "closed_offers_share",
        "registered_volume_brl",
        "registered_volume_share",
        "period_closed_offers",
        "period_registered_volume_brl",
    )
    for column in numeric_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
        if result[column].isna().any() or not np.isfinite(
            result[column].to_numpy(dtype=float)
        ).all():
            raise ClosedOfferPlacementRegimeError(
                f"Tabela de regime contém valor inválido em {column}."
            )
        if (result[column] < 0).any():
            raise ClosedOfferPlacementRegimeError(
                f"Tabela de regime contém valor negativo em {column}."
            )
    current = result["period_label"].eq("2026 jan-jun")
    for column in (
        "comparison_closed_offers",
        "comparison_registered_volume_brl",
    ):
        result[column] = pd.to_numeric(result[column], errors="coerce")
        if result.loc[current, column].isna().any():
            raise ClosedOfferPlacementRegimeError(
                f"Comparável YTD ausente em {column}."
            )
    result["registered_volume_yoy_ytd"] = pd.to_numeric(
        result["registered_volume_yoy_ytd"], errors="coerce"
    )
    comparable_positive = current & result["comparison_registered_volume_brl"].gt(0)
    if result.loc[comparable_positive, "registered_volume_yoy_ytd"].isna().any():
        raise ClosedOfferPlacementRegimeError(
            "Crescimento YTD ausente onde o comparável tem volume positivo."
        )
    if not result.loc[~current, "comparison_period_label"].eq("N/D").all():
        raise ClosedOfferPlacementRegimeError(
            "Comparável YTD deve ficar restrito ao período jan–jun/26."
        )
    for period_label, period in result.groupby("period_label", sort=False):
        if int(period["closed_offers"].sum()) != int(
            period["period_closed_offers"].iloc[0]
        ):
            raise ClosedOfferPlacementRegimeError(
                f"{period_label}: quantidade por regime não reconcilia."
            )
        if not np.isclose(
            period["registered_volume_brl"].sum(),
            period["period_registered_volume_brl"].iloc[0],
            rtol=1e-10,
            atol=1e-4,
        ):
            raise ClosedOfferPlacementRegimeError(
                f"{period_label}: volume por regime não reconcilia."
            )
        if not np.isclose(
            period["closed_offers_share"].sum(), 1.0, rtol=1e-10, atol=1e-10
        ):
            raise ClosedOfferPlacementRegimeError(
                f"{period_label}: participação da quantidade não fecha 100%."
            )
        if not np.isclose(
            period["registered_volume_share"].sum(),
            1.0,
            rtol=1e-10,
            atol=1e-10,
        ):
            raise ClosedOfferPlacementRegimeError(
                f"{period_label}: participação do volume não fecha 100%."
            )
    return result.sort_values(
        ["period_order", "regime_order"], kind="stable"
    ).reset_index(drop=True)


def _enrich_materialized_ytd_comparison(
    frame: pd.DataFrame,
    cohort: pd.DataFrame,
) -> pd.DataFrame:
    """Add the Jan-Jun/25 comparison to a pre-extension materialized table."""

    result = frame.copy()
    cohort = cohort.copy()
    cohort["data_encerramento"] = pd.to_datetime(
        cohort["data_encerramento"], errors="coerce"
    )
    cohort["registered_volume_brl"] = pd.to_numeric(
        cohort["registered_volume_brl"], errors="coerce"
    )
    comparison = cohort[
        cohort["data_encerramento"].between(
            pd.Timestamp("2025-01-01"), pd.Timestamp("2025-06-30")
        )
    ].copy()
    comparison["placement_regime"] = comparison["distribution_regime"].map(
        _regime_bucket
    )
    current = result["period_label"].eq("2026 jan-jun")
    result["comparison_period_label"] = np.where(
        current, "2025 jan-jun", "N/D"
    )
    result["comparison_period_start"] = np.where(
        current, "2025-01-01", "N/D"
    )
    result["comparison_period_end"] = np.where(
        current, "2025-06-30", "N/D"
    )
    result["comparison_closed_offers"] = np.nan
    result["comparison_registered_volume_brl"] = np.nan
    result["registered_volume_yoy_ytd"] = np.nan
    for index in result.index[current]:
        regime = result.at[index, "placement_regime"]
        group = comparison[comparison["placement_regime"].eq(regime)]
        offers = int(group["numero_requerimento"].astype(str).nunique())
        volume = float(group["registered_volume_brl"].sum())
        current_volume = float(result.at[index, "registered_volume_brl"])
        result.at[index, "comparison_closed_offers"] = offers
        result.at[index, "comparison_registered_volume_brl"] = volume
        result.at[index, "registered_volume_yoy_ytd"] = (
            current_volume / volume - 1.0 if volume > 0 else np.nan
        )
    return result


def load_materialized_closed_offer_placement_regime(
    data_dir: str | Path,
) -> pd.DataFrame:
    root = Path(data_dir)
    path = root / OUTPUT_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Tabela de regime ausente: {path}")
    frame = pd.read_csv(path, low_memory=False)
    if set(OUTPUT_COLUMNS).difference(frame.columns):
        cohort_path = root / COHORT_FILENAME
        if not cohort_path.is_file():
            raise FileNotFoundError(
                f"Coorte necessária ao comparável YTD ausente: {cohort_path}"
            )
        frame = _enrich_materialized_ytd_comparison(
            frame,
            pd.read_csv(cohort_path, low_memory=False),
        )
    return validate_closed_offer_placement_regime(
        frame
    )


def write_closed_offer_placement_regime(
    frame: pd.DataFrame,
    output_dir: str | Path,
) -> Path:
    output = validate_closed_offer_placement_regime(frame)
    path = Path(output_dir) / OUTPUT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)
    return path


__all__ = [
    "COHORT_FILENAME",
    "ClosedOfferPlacementRegimeError",
    "OUTPUT_FILENAME",
    "PERIODS",
    "REGIME_ORDER",
    "SOURCE_ARCHIVE_SHA256",
    "SOURCE_AS_OF_DATE",
    "SOURCE_DATASET",
    "SOURCE_URL",
    "build_closed_offer_placement_regime",
    "load_materialized_closed_offer_placement_regime",
    "validate_closed_offer_placement_regime",
    "write_closed_offer_placement_regime",
]
