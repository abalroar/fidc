"""Offer-level Top 15 rankings for closed primary FIDC offerings.

The closed-offer cohort is authoritative for scope and period.  Offer metadata
is joined by ``Numero_Requerimento`` only to enrich the selected rows with
originator, lead coordinator, distribution regime, target public and investor
counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unicodedata

import pandas as pd


COHORT_FILENAME = "industry_closed_offer_ticket_cohort.csv.gz"
OFFERS_FILENAME = "industry_offers.csv.gz"
TOP_PERIODS = ("2025 FY", "2026 jan-jun")
IBBA_LEADER = "ITAU BBA ASSESSORIA FINANCEIRA S.A"


class ClosedOfferRankingError(ValueError):
    """Raised when the closed-offer ranking cannot be reconciled."""


@dataclass(frozen=True)
class ClosedOfferRankingOutputs:
    rankings: pd.DataFrame
    summary: pd.DataFrame


def _normalized_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(
        character for character in text
        if not unicodedata.combining(character)
    )
    return " ".join(text.upper().split()).strip(" .")


def _clean_text(value: object, fallback: str = "") -> str:
    if value is None or pd.isna(value):
        return fallback
    text = " ".join(str(value).split())
    return text if text else fallback


def _public_label(value: object) -> str:
    normalized = _normalized_text(value)
    if "PROFISSIONAL" in normalized:
        return "Profissional"
    if "QUALIFICADO" in normalized:
        return "Qualificado"
    if "GERAL" in normalized:
        return "Geral"
    return "N/D"


def _read_inputs(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    cohort_path = data_dir / COHORT_FILENAME
    offers_path = data_dir / OFFERS_FILENAME
    if not cohort_path.exists():
        raise ClosedOfferRankingError(f"coorte de ofertas ausente: {cohort_path}")
    if not offers_path.exists():
        raise ClosedOfferRankingError(
            f"metadados de ofertas ausentes: {offers_path}"
        )

    cohort = pd.read_csv(cohort_path, dtype=str, low_memory=False).rename(
        columns={"numero_requerimento": "offer_id"}
    )
    offers = pd.read_csv(offers_path, dtype=str, low_memory=False)
    required_cohort = {
        "offer_id",
        "period_order",
        "period_label",
        "period_start",
        "period_end",
        "data_encerramento",
        "cnpj_emissor",
        "nome_emissor",
        "registered_volume_brl",
        "source_dataset",
        "source_url",
        "source_as_of_date",
        "scope",
    }
    required_offers = {
        "offer_id",
        "issuer_name",
        "leader_name",
        "distribution_regime",
        "target_public",
        "investor_count",
        "originator_group",
        "originator_source",
        "originator_evidence",
        "status",
        "offer_type",
        "security",
    }
    missing_cohort = sorted(required_cohort.difference(cohort.columns))
    missing_offers = sorted(required_offers.difference(offers.columns))
    if missing_cohort:
        raise ClosedOfferRankingError(
            "coorte sem colunas obrigatórias: " + ", ".join(missing_cohort)
        )
    if missing_offers:
        raise ClosedOfferRankingError(
            "metadados sem colunas obrigatórias: " + ", ".join(missing_offers)
        )

    cohort["offer_id"] = cohort["offer_id"].map(_clean_text)
    offers["offer_id"] = offers["offer_id"].map(_clean_text)
    if cohort["offer_id"].eq("").any():
        raise ClosedOfferRankingError("coorte contém Numero_Requerimento vazio")
    if cohort["offer_id"].duplicated().any():
        raise ClosedOfferRankingError(
            "coorte contém Numero_Requerimento duplicado"
        )
    if offers["offer_id"].duplicated().any():
        raise ClosedOfferRankingError(
            "metadados contêm Numero_Requerimento duplicado"
        )
    return cohort, offers


def build_closed_offer_top15(
    data_dir: Path,
    *,
    top_n: int = 15,
) -> ClosedOfferRankingOutputs:
    """Build offer-level rankings from the materialized closed-offer cohort."""

    if top_n <= 0:
        raise ClosedOfferRankingError("top_n deve ser positivo")
    cohort, offers = _read_inputs(data_dir)
    cohort = cohort[cohort["period_label"].isin(TOP_PERIODS)].copy()
    period_labels = tuple(
        cohort.sort_values("period_order")["period_label"].drop_duplicates()
    )
    if period_labels != TOP_PERIODS:
        raise ClosedOfferRankingError(
            f"períodos esperados {TOP_PERIODS}; observados {period_labels}"
        )

    metadata_columns = [
        "offer_id",
        "issuer_name",
        "leader_name",
        "distribution_regime",
        "target_public",
        "investor_count",
        "originator_group",
        "originator_source",
        "originator_evidence",
        "status",
        "offer_type",
        "security",
    ]
    joined = cohort.merge(
        offers[metadata_columns],
        on="offer_id",
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    joined["registered_volume_brl"] = pd.to_numeric(
        joined["registered_volume_brl"], errors="coerce"
    )
    if (
        joined["registered_volume_brl"].isna().any()
        or joined["registered_volume_brl"].le(0).any()
    ):
        raise ClosedOfferRankingError(
            "coorte contém Valor_Total_Registrado inválido"
        )

    joined["metadata_matched"] = joined["_merge"].eq("both")
    joined["originator_group"] = joined["originator_group"].map(
        lambda value: _clean_text(value, "Não identificado")
    )
    joined["originator_group"] = joined["originator_group"].replace(
        {"N/D": "Não identificado", "Não Identificado": "Não identificado"}
    )
    joined["leader_name"] = joined["leader_name"].map(
        lambda value: _clean_text(value, "N/D")
    )
    joined["distribution_regime"] = joined["distribution_regime"].map(
        lambda value: _clean_text(value, "N/D")
    )
    joined["publico"] = joined["target_public"].map(_public_label)
    joined["investor_count"] = pd.to_numeric(
        joined["investor_count"], errors="coerce"
    ).round()
    joined["ibba_coord_lead"] = joined["leader_name"].map(
        lambda value: _normalized_text(value) == IBBA_LEADER
    )
    joined["firm_commitment"] = joined["distribution_regime"].map(
        lambda value: "GARANTIA FIRME" in _normalized_text(value)
    )

    ranking_parts: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    for period_label in TOP_PERIODS:
        period = joined[joined["period_label"].eq(period_label)].copy()
        period = period.sort_values(
            ["registered_volume_brl", "offer_id"],
            ascending=[False, True],
        ).reset_index(drop=True)
        top = period.head(top_n).copy()
        if len(top) != top_n:
            raise ClosedOfferRankingError(
                f"{period_label} possui apenas {len(top)} ofertas"
            )
        top["rank"] = range(1, top_n + 1)
        top["ibba_coord_lead_label"] = top["ibba_coord_lead"].map(
            {True: "Sim", False: "Não"}
        )
        top["firm_commitment_label"] = top["firm_commitment"].map(
            {True: "Sim", False: "Não"}
        )
        ranking_parts.append(top)

        period_volume = float(period["registered_volume_brl"].sum())
        top_volume = float(top["registered_volume_brl"].sum())
        ibba = top["ibba_coord_lead"]
        firm = top["firm_commitment"]
        summary_rows.append(
            {
                "period_order": int(top["period_order"].iloc[0]),
                "period_label": period_label,
                "period_start": top["period_start"].iloc[0],
                "period_end": top["period_end"].iloc[0],
                "period_closed_offers": int(len(period)),
                "period_registered_volume_brl": period_volume,
                "top15_offers": int(len(top)),
                "top15_registered_volume_brl": top_volume,
                "top15_share_of_period_volume": (
                    top_volume / period_volume if period_volume else 0.0
                ),
                "ibba_lead_offers_top15": int(ibba.sum()),
                "ibba_lead_volume_top15_brl": float(
                    top.loc[ibba, "registered_volume_brl"].sum()
                ),
                "ibba_lead_share_top15_volume": float(
                    top.loc[ibba, "registered_volume_brl"].sum() / top_volume
                ) if top_volume else 0.0,
                "ibba_lead_share_period_volume": float(
                    top.loc[ibba, "registered_volume_brl"].sum() / period_volume
                ) if period_volume else 0.0,
                "firm_commitment_offers_top15": int(firm.sum()),
                "firm_commitment_volume_top15_brl": float(
                    top.loc[firm, "registered_volume_brl"].sum()
                ),
                "ibba_firm_commitment_offers_top15": int((ibba & firm).sum()),
                "ibba_firm_commitment_volume_top15_brl": float(
                    top.loc[ibba & firm, "registered_volume_brl"].sum()
                ),
                "metadata_matched_top15": int(top["metadata_matched"].sum()),
                "originators_identified_top15": int(
                    top["originator_group"].ne("Não identificado").sum()
                ),
                "scope": top["scope"].iloc[0],
                "source_dataset": top["source_dataset"].iloc[0],
                "source_url": top["source_url"].iloc[0],
                "source_as_of_date": top["source_as_of_date"].iloc[0],
                "investor_count_methodology": (
                    "soma de todas as colunas Num_Invest_* da base CVM; "
                    "Num_Invest_Pessoa_Natural isoladamente não representa o total"
                ),
                "ranking_methodology": (
                    "Valor Total Registrado decrescente; empates por "
                    "Numero_Requerimento crescente"
                ),
            }
        )

    rankings = pd.concat(ranking_parts, ignore_index=True)
    rankings = rankings[
        [
            "period_order",
            "period_label",
            "period_start",
            "period_end",
            "rank",
            "offer_id",
            "data_encerramento",
            "cnpj_emissor",
            "nome_emissor",
            "originator_group",
            "registered_volume_brl",
            "leader_name",
            "ibba_coord_lead",
            "ibba_coord_lead_label",
            "distribution_regime",
            "firm_commitment",
            "firm_commitment_label",
            "publico",
            "investor_count",
            "originator_source",
            "originator_evidence",
            "metadata_matched",
            "status",
            "offer_type",
            "security",
            "source_dataset",
            "source_url",
            "source_as_of_date",
            "scope",
        ]
    ].copy()
    summary = pd.DataFrame(summary_rows)
    return ClosedOfferRankingOutputs(rankings=rankings, summary=summary)
