"""Reconcile the granular CVM offer universe with the ANBIMA market series."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services.industry_public_offers import (
    FIDC_CANONICAL,
    SOURCE_DATASET_LABEL,
    SOURCE_URL,
    load_public_primary_closed_offers,
)


ANBIMA_FILENAME = "industry_anbima_market_offers.csv"
OUTPUT_FILENAME = "industry_market_offer_reconciliation.csv"
ANBIMA_SOURCE_URL = (
    "https://data-strapi.prd.anbima.com.br/uploads/"
    "Boletim_MK_Anexo_8_33b8963678.xlsx"
)
ANBIMA_WORKBOOK_SHA256 = (
    "1236172468f5aa3ddde24382bfa9c5f6372f9b35cd03993ef2482d358845b524"
)
ANBIMA_JUNE_SOURCE_URL = (
    "https://www.anbima.com.br/data/files/8E/86/DB/07/"
    "325AF91098D078F9692BA2A8/"
    "Apresentacao%20_%20coletiva%20Mercado%20de%20Capitais%20_%201S26.pdf"
)
ANBIMA_JUNE_SOURCE_SHA256 = (
    "2d61cc13256c48e1427166c4b8a400d873c9be50a402ebba3c53b1616e9096a2"
)
CVM_SOURCE_AS_OF_DATE = "2026-07-24"
CVM_ARCHIVE_SHA256 = (
    "46a5a3c35e500dd4560a5a4b286a7a302311ea02b397c1a67821bc197514b4e5"
)

PERIODS: tuple[dict[str, Any], ...] = (
    {
        "period_order": 1,
        "period_label": "2023 FY",
        "period_start": "2023-01-01",
        "period_end": "2023-12-31",
        "is_full_year": True,
    },
    {
        "period_order": 2,
        "period_label": "2024 FY",
        "period_start": "2024-01-01",
        "period_end": "2024-12-31",
        "is_full_year": True,
    },
    {
        "period_order": 3,
        "period_label": "2025 FY",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "is_full_year": True,
    },
    {
        "period_order": 4,
        "period_label": "2026 jan-jun",
        "period_start": "2026-01-01",
        "period_end": "2026-06-30",
        "is_full_year": False,
    },
)

INSTRUMENTS: tuple[dict[str, Any], ...] = (
    {
        "instrument_order": 1,
        "instrument_label": "Debêntures",
        "cvm_instrument": "DEBENTURES",
        "cvm_harmonization_instrument": "OUTROS TITULOS DE SECURITIZACAO",
        "explanation": (
            "A ANBIMA inclui debêntures de securitização. A CVM passou a "
            "classificar parte desse volume como Outros títulos de securitização."
        ),
    },
    {
        "instrument_order": 2,
        "instrument_label": "FIDCs",
        "cvm_instrument": FIDC_CANONICAL,
        "cvm_harmonization_instrument": "",
        "explanation": (
            "A CVM mede volume registrado de ofertas primárias; a ANBIMA mede "
            "valor encerrado e o anexo não segrega sistematicamente ofertas "
            "primárias e secundárias."
        ),
    },
    {
        "instrument_order": 3,
        "instrument_label": "CRI",
        "cvm_instrument": "CERTIFICADOS DE RECEBIVEIS IMOBILIARIOS",
        "cvm_harmonization_instrument": "",
        "explanation": (
            "A diferença residual depende de valor registrado versus encerrado, "
            "fotografia da base e retificações; a causa individual exige "
            "reconciliação oferta a oferta."
        ),
    },
    {
        "instrument_order": 4,
        "instrument_label": "Notas comerciais",
        "cvm_instrument": "NOTAS COMERCIAIS",
        "cvm_harmonization_instrument": "",
        "explanation": (
            "A diferença residual depende de valor registrado versus encerrado, "
            "fotografia da base e retificações; a causa individual exige "
            "reconciliação oferta a oferta."
        ),
    },
    {
        "instrument_order": 5,
        "instrument_label": "CRA",
        "cvm_instrument": "CERTIFICADOS DE RECEBIVEIS DO AGRONEGOCIO",
        "cvm_harmonization_instrument": "",
        "explanation": (
            "A diferença residual depende de valor registrado versus encerrado, "
            "fotografia da base e retificações; a divergência de 2023 permanece "
            "sem causa atribuída."
        ),
    },
)

ANBIMA_COLUMNS = (
    "period_order",
    "period_label",
    "period_start",
    "period_end",
    "is_full_year",
    "instrument_order",
    "instrument_label",
    "anbima_instrument_label",
    "closed_volume_brl",
    "source_name",
    "source_snapshot",
    "source_sheet",
    "source_range",
    "source_url",
    "source_workbook_sha256",
    "metric",
    "scope",
    "limitation",
)

OUTPUT_COLUMNS = (
    "period_order",
    "period_label",
    "period_start",
    "period_end",
    "is_full_year",
    "instrument_order",
    "instrument_label",
    "cvm_instrument",
    "cvm_closed_offers",
    "cvm_registered_volume_brl",
    "cvm_harmonization_instrument",
    "cvm_harmonization_volume_brl",
    "cvm_harmonized_volume_brl",
    "anbima_instrument_label",
    "anbima_closed_volume_brl",
    "raw_gap_brl",
    "raw_gap_pct",
    "harmonized_gap_brl",
    "harmonized_gap_pct",
    "primary_explanation",
    "cvm_source_dataset",
    "cvm_source_url",
    "cvm_source_as_of_date",
    "cvm_source_archive_sha256",
    "cvm_metric",
    "cvm_scope",
    "anbima_source_name",
    "anbima_source_url",
    "anbima_source_snapshot",
    "anbima_source_sheet",
    "anbima_source_range",
    "anbima_source_workbook_sha256",
    "anbima_metric",
    "anbima_scope",
    "limitation",
)


class MarketOfferReconciliationError(ValueError):
    """Raised when the CVM/ANBIMA bridge violates its source contract."""


def _normalize_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    normalized = series.astype(str).str.strip().str.casefold()
    if not normalized.isin({"true", "false", "1", "0"}).all():
        raise MarketOfferReconciliationError("Booleano inválido em is_full_year.")
    return normalized.isin({"true", "1"})


def validate_anbima_market_offers(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in ANBIMA_COLUMNS if column not in frame]
    if missing:
        raise MarketOfferReconciliationError(
            "Snapshot ANBIMA sem colunas: " + ", ".join(missing)
        )
    result = frame.loc[:, ANBIMA_COLUMNS].copy()
    if len(result) != len(PERIODS) * len(INSTRUMENTS):
        raise MarketOfferReconciliationError(
            f"Snapshot ANBIMA deveria conter 20 linhas; contém {len(result)}."
        )
    result["period_order"] = pd.to_numeric(result["period_order"], errors="coerce")
    result["instrument_order"] = pd.to_numeric(
        result["instrument_order"], errors="coerce"
    )
    result["closed_volume_brl"] = pd.to_numeric(
        result["closed_volume_brl"], errors="coerce"
    )
    result["is_full_year"] = _normalize_bool(result["is_full_year"])
    numeric = result[["period_order", "instrument_order", "closed_volume_brl"]]
    if numeric.isna().any().any() or not np.isfinite(
        numeric.to_numpy(dtype=float)
    ).all():
        raise MarketOfferReconciliationError("Snapshot ANBIMA contém número inválido.")
    if (result["closed_volume_brl"] < 0).any():
        raise MarketOfferReconciliationError("Snapshot ANBIMA contém volume negativo.")
    key = ["period_label", "instrument_label"]
    if result.duplicated(key).any():
        raise MarketOfferReconciliationError("Snapshot ANBIMA contém chave duplicada.")
    expected = {
        (period["period_label"], instrument["instrument_label"])
        for period in PERIODS
        for instrument in INSTRUMENTS
    }
    if set(map(tuple, result[key].to_numpy())) != expected:
        raise MarketOfferReconciliationError(
            "Snapshot ANBIMA não cobre todos os períodos e instrumentos."
        )
    historical = result[~result["period_label"].eq("2026 jan-jun")]
    current = result[result["period_label"].eq("2026 jan-jun")]
    if set(historical["source_workbook_sha256"]) != {ANBIMA_WORKBOOK_SHA256}:
        raise MarketOfferReconciliationError(
            "SHA-256 do workbook histórico ANBIMA diverge."
        )
    if set(historical["source_url"]) != {ANBIMA_SOURCE_URL}:
        raise MarketOfferReconciliationError(
            "URL do workbook histórico ANBIMA diverge."
        )
    if set(current["source_workbook_sha256"]) != {ANBIMA_JUNE_SOURCE_SHA256}:
        raise MarketOfferReconciliationError(
            "SHA-256 da apresentação ANBIMA de jun/26 diverge."
        )
    if set(current["source_url"]) != {ANBIMA_JUNE_SOURCE_URL}:
        raise MarketOfferReconciliationError(
            "URL da apresentação ANBIMA de jun/26 diverge."
        )
    return result.sort_values(
        ["period_order", "instrument_order"], kind="stable"
    ).reset_index(drop=True)


def load_anbima_market_offers(data_dir: str | Path) -> pd.DataFrame:
    path = Path(data_dir) / ANBIMA_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Snapshot ANBIMA ausente: {path}")
    return validate_anbima_market_offers(pd.read_csv(path, low_memory=False))


def build_market_offer_reconciliation(
    archive_path: str | Path,
    anbima: pd.DataFrame,
    *,
    cvm_source_as_of_date: str = CVM_SOURCE_AS_OF_DATE,
    expected_cvm_archive_sha256: str | None = CVM_ARCHIVE_SHA256,
) -> pd.DataFrame:
    anbima = validate_anbima_market_offers(anbima)
    cvm, digest = load_public_primary_closed_offers(
        archive_path,
        cutoff="2026-06-30",
        expected_archive_sha256=expected_cvm_archive_sha256,
    )
    rows: list[dict[str, Any]] = []
    for period in PERIODS:
        period_cvm = cvm[cvm["closing_date"].between(
            period["period_start"], period["period_end"]
        )]
        for instrument in INSTRUMENTS:
            raw = period_cvm[
                period_cvm["canonical_instrument"].eq(instrument["cvm_instrument"])
            ]
            harmonization_name = instrument["cvm_harmonization_instrument"]
            harmonization = (
                period_cvm[period_cvm["canonical_instrument"].eq(harmonization_name)]
                if harmonization_name
                else period_cvm.iloc[0:0]
            )
            cvm_volume = float(raw["registered_volume_brl"].sum())
            harmonization_volume = float(
                harmonization["registered_volume_brl"].sum()
            )
            harmonized = cvm_volume + harmonization_volume
            official_row = anbima[
                anbima["period_label"].eq(period["period_label"])
                & anbima["instrument_label"].eq(instrument["instrument_label"])
            ].iloc[0]
            official = float(official_row["closed_volume_brl"])
            raw_gap = cvm_volume - official
            harmonized_gap = harmonized - official
            rows.append(
                {
                    **period,
                    "instrument_order": instrument["instrument_order"],
                    "instrument_label": instrument["instrument_label"],
                    "cvm_instrument": instrument["cvm_instrument"],
                    "cvm_closed_offers": int(len(raw)),
                    "cvm_registered_volume_brl": cvm_volume,
                    "cvm_harmonization_instrument": harmonization_name,
                    "cvm_harmonization_volume_brl": harmonization_volume,
                    "cvm_harmonized_volume_brl": harmonized,
                    "anbima_instrument_label": official_row[
                        "anbima_instrument_label"
                    ],
                    "anbima_closed_volume_brl": official,
                    "raw_gap_brl": raw_gap,
                    "raw_gap_pct": raw_gap / official if official else np.nan,
                    "harmonized_gap_brl": harmonized_gap,
                    "harmonized_gap_pct": (
                        harmonized_gap / official if official else np.nan
                    ),
                    "primary_explanation": instrument["explanation"],
                    "cvm_source_dataset": SOURCE_DATASET_LABEL,
                    "cvm_source_url": SOURCE_URL,
                    "cvm_source_as_of_date": cvm_source_as_of_date,
                    "cvm_source_archive_sha256": digest,
                    "cvm_metric": "Valor registrado",
                    "cvm_scope": (
                        "Ofertas públicas primárias encerradas; todos os ritos "
                        "disponíveis na CVM; data de encerramento no período; "
                        "volume registrado positivo."
                    ),
                    "anbima_source_name": official_row["source_name"],
                    "anbima_source_url": official_row["source_url"],
                    "anbima_source_snapshot": official_row["source_snapshot"],
                    "anbima_source_sheet": official_row["source_sheet"],
                    "anbima_source_range": official_row["source_range"],
                    "anbima_source_workbook_sha256": official_row[
                        "source_workbook_sha256"
                    ],
                    "anbima_metric": official_row["metric"],
                    "anbima_scope": official_row["scope"],
                    "limitation": official_row["limitation"],
                }
            )
    return validate_market_offer_reconciliation(pd.DataFrame(rows))


def validate_market_offer_reconciliation(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in OUTPUT_COLUMNS if column not in frame]
    if missing:
        raise MarketOfferReconciliationError(
            "Reconciliação sem colunas: " + ", ".join(missing)
        )
    result = frame.loc[:, OUTPUT_COLUMNS].copy()
    if len(result) != len(PERIODS) * len(INSTRUMENTS):
        raise MarketOfferReconciliationError(
            f"Reconciliação deveria conter 20 linhas; contém {len(result)}."
        )
    key = ["period_label", "instrument_label"]
    if result.duplicated(key).any():
        raise MarketOfferReconciliationError("Reconciliação contém chave duplicada.")
    numeric_columns = (
        "period_order",
        "instrument_order",
        "cvm_closed_offers",
        "cvm_registered_volume_brl",
        "cvm_harmonization_volume_brl",
        "cvm_harmonized_volume_brl",
        "anbima_closed_volume_brl",
        "raw_gap_brl",
        "raw_gap_pct",
        "harmonized_gap_brl",
        "harmonized_gap_pct",
    )
    for column in numeric_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
        if result[column].isna().any() or not np.isfinite(
            result[column].to_numpy(dtype=float)
        ).all():
            raise MarketOfferReconciliationError(
                f"Reconciliação contém valor inválido em {column}."
            )
    result["is_full_year"] = _normalize_bool(result["is_full_year"])
    if not np.isclose(
        result["cvm_harmonized_volume_brl"],
        result["cvm_registered_volume_brl"]
        + result["cvm_harmonization_volume_brl"],
        rtol=1e-12,
        atol=1e-4,
    ).all():
        raise MarketOfferReconciliationError("Harmonização CVM não reconcilia.")
    expected_raw_gap = (
        result["cvm_registered_volume_brl"]
        - result["anbima_closed_volume_brl"]
    )
    expected_harmonized_gap = (
        result["cvm_harmonized_volume_brl"]
        - result["anbima_closed_volume_brl"]
    )
    if not np.isclose(result["raw_gap_brl"], expected_raw_gap).all():
        raise MarketOfferReconciliationError("Diferença bruta não reconcilia.")
    if not np.isclose(
        result["harmonized_gap_brl"], expected_harmonized_gap
    ).all():
        raise MarketOfferReconciliationError(
            "Diferença harmonizada não reconcilia."
        )
    return result.sort_values(
        ["period_order", "instrument_order"], kind="stable"
    ).reset_index(drop=True)


def load_materialized_market_offer_reconciliation(
    data_dir: str | Path,
) -> pd.DataFrame:
    path = Path(data_dir) / OUTPUT_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Reconciliação CVM/ANBIMA ausente: {path}")
    return validate_market_offer_reconciliation(pd.read_csv(path, low_memory=False))


def write_market_offer_reconciliation(
    frame: pd.DataFrame, output_dir: str | Path
) -> Path:
    output = validate_market_offer_reconciliation(frame)
    path = Path(output_dir) / OUTPUT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)
    return path


__all__ = [
    "ANBIMA_FILENAME",
    "ANBIMA_JUNE_SOURCE_SHA256",
    "ANBIMA_JUNE_SOURCE_URL",
    "ANBIMA_SOURCE_URL",
    "ANBIMA_WORKBOOK_SHA256",
    "CVM_ARCHIVE_SHA256",
    "CVM_SOURCE_AS_OF_DATE",
    "MarketOfferReconciliationError",
    "OUTPUT_FILENAME",
    "build_market_offer_reconciliation",
    "load_anbima_market_offers",
    "load_materialized_market_offer_reconciliation",
    "validate_anbima_market_offers",
    "validate_market_offer_reconciliation",
    "write_market_offer_reconciliation",
]
