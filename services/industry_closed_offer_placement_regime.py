"""Materialize placement-regime views for closed primary FIDC offerings.

The offer-level cohort defines the audited universe and periods.  The official
``Regime_distribuicao`` field is joined from the same CVM public-offering
snapshot by ``Numero_Requerimento``.  No missing regime is imputed.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import unicodedata
from zipfile import ZipFile

import numpy as np
import pandas as pd


SOURCE_DATASET = "oferta_resolucao_160.csv"
SOURCE_URL = (
    "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/"
    "oferta_distribuicao.zip"
)
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


def _archive_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    path = Path(archive_path)
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo CVM de ofertas ausente: {path}")
    digest = _archive_sha256(path)
    if expected_archive_sha256 and digest != expected_archive_sha256:
        raise ClosedOfferPlacementRegimeError(
            "SHA-256 do arquivo CVM diverge do snapshot esperado: " + digest
        )
    with ZipFile(path) as archive:
        if SOURCE_DATASET not in archive.namelist():
            raise ClosedOfferPlacementRegimeError(
                f"Tabela {SOURCE_DATASET} ausente no arquivo CVM."
            )
        source = pd.read_csv(
            archive.open(SOURCE_DATASET),
            sep=";",
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
            low_memory=False,
        )
    required = {
        "Numero_Requerimento",
        "Status_Requerimento",
        "Valor_Mobiliario",
        "Tipo_Oferta",
        "Regime_distribuicao",
    }
    missing = sorted(required.difference(source.columns))
    if missing:
        raise ClosedOfferPlacementRegimeError(
            "Colunas CVM obrigatórias ausentes: " + ", ".join(missing)
        )
    source = source.rename(
        columns={"Numero_Requerimento": "offer_id"}
    ).copy()
    source["offer_id"] = source["offer_id"].str.strip()
    source = source[source["Valor_Mobiliario"].str.contains(
        "FIDC", case=False, na=False
    )].copy()
    if source["offer_id"].eq("").any():
        raise ClosedOfferPlacementRegimeError(
            "Numero_Requerimento vazio na fonte CVM."
        )
    if source["offer_id"].duplicated().any():
        raise ClosedOfferPlacementRegimeError(
            "Numero_Requerimento duplicado na fonte CVM."
        )
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
    joined = cohort.merge(
        source[
            [
                "offer_id",
                "Status_Requerimento",
                "Valor_Mobiliario",
                "Tipo_Oferta",
                "Regime_distribuicao",
            ]
        ],
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
    if not joined["Status_Requerimento"].map(_normalize_text).eq(
        "OFERTA ENCERRADA"
    ).all():
        raise ClosedOfferPlacementRegimeError(
            "Coorte contém status diferente de Oferta Encerrada na fonte."
        )
    if not joined["Tipo_Oferta"].map(_normalize_text).eq("PRIMARIA").all():
        raise ClosedOfferPlacementRegimeError(
            "Coorte contém oferta diferente de primária na fonte."
        )
    joined["placement_regime"] = joined["Regime_distribuicao"].map(
        _regime_bucket
    )

    scope = (
        "Cotas de FIDC | oferta primária | status oficial Oferta Encerrada | "
        "Data_Encerramento no período | Valor_Total_Registrado positivo"
    )
    methodology = (
        "Uma oferta = Numero_Requerimento. Regime usa o campo oficial "
        "Regime_distribuicao; Garantia Firme de Colocação e de Liquidação "
        "são consolidadas em Garantia firme. 2024/2025 são anos completos; "
        "2026 cobre janeiro a junho."
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


def load_materialized_closed_offer_placement_regime(
    data_dir: str | Path,
) -> pd.DataFrame:
    path = Path(data_dir) / OUTPUT_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Tabela de regime ausente: {path}")
    return validate_closed_offer_placement_regime(
        pd.read_csv(path, low_memory=False)
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
