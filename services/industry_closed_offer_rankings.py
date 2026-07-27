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
DOCUMENT_CURATION_FILENAME = "industry_offer_document_curation.csv"
RATING_REVIEW_FILENAME = "industry_offer_rating_review.csv"
TOP_PERIODS = (
    "2022 FY parcial",
    "2023 FY",
    "2024 FY",
    "2025 FY",
    "2026 jan-jun",
)
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
        "rite",
        "leader_name",
        "distribution_regime",
        "target_public",
        "investor_count",
        "investor_person_natural",
        "investor_funds",
        "investor_financial_institutions",
        "investor_other_legal_entities",
        "investor_pension",
        "investor_insurers",
        "investor_foreign",
        "investor_clubs",
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
    offer_metadata = offers[metadata_columns].rename(
        columns={
            column: f"offer_{column}"
            for column in metadata_columns
            if column != "offer_id"
        }
    )
    joined = cohort.merge(
        offer_metadata,
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
    for column in (
        "leader_name",
        "distribution_regime",
        "target_public",
        "investor_count",
    ):
        offer_column = f"offer_{column}"
        if offer_column not in joined:
            continue
        current = joined[column].map(_clean_text)
        supplement = joined[offer_column].map(_clean_text)
        joined[column] = current.where(current.ne(""), supplement)
    joined["originator_group"] = joined["offer_originator_group"]
    joined["originator_source"] = joined["offer_originator_source"]
    joined["originator_evidence"] = joined["offer_originator_evidence"]
    joined["status"] = joined["offer_status"].map(
        lambda value: _clean_text(value, "Oferta encerrada")
    )
    joined["offer_type"] = joined["offer_offer_type"].map(
        lambda value: _clean_text(value, "PRIMARIA")
    )
    joined["security"] = joined["offer_security"].map(
        lambda value: _clean_text(value, "Cotas de FIDC")
    )
    curation_path = data_dir / DOCUMENT_CURATION_FILENAME
    if curation_path.is_file():
        curation = pd.read_csv(
            curation_path, dtype=str, keep_default_na=False
        )
        required_curation = {
            "offer_id",
            "originator_group_curated",
            "originator_confidence",
            "originator_evidence",
            "ibba_participant",
            "ibba_participant_label",
            "ibba_participant_entities",
            "ibba_participant_roles",
            "ibba_participation_source",
            "participants_source_url",
            "coordinator_entities",
            "firm_commitment_coordinators",
            "firm_commitment_amount_by_coordinator",
            "firm_commitment_source_limitation",
            "closing_document_url",
            "document_text_method",
            "review_status",
        }
        missing_curation = sorted(
            required_curation.difference(curation.columns)
        )
        if missing_curation:
            raise ClosedOfferRankingError(
                "curadoria documental sem colunas: "
                + ", ".join(missing_curation)
            )
        if curation["offer_id"].duplicated().any():
            raise ClosedOfferRankingError(
                "curadoria documental contém offer_id duplicado"
            )
        joined = joined.merge(
            curation[list(required_curation)],
            on="offer_id",
            how="left",
            validate="one_to_one",
        )
    else:
        joined["originator_group_curated"] = ""
        joined["originator_confidence"] = ""
        joined["originator_evidence_y"] = ""
        joined["ibba_participant"] = ""
        joined["ibba_participant_label"] = ""
        joined["ibba_participant_entities"] = ""
        joined["ibba_participant_roles"] = ""
        joined["ibba_participation_source"] = ""
        joined["participants_source_url"] = ""
        joined["coordinator_entities"] = ""
        joined["firm_commitment_coordinators"] = ""
        joined["firm_commitment_amount_by_coordinator"] = ""
        joined["firm_commitment_source_limitation"] = ""
        joined["closing_document_url"] = ""
        joined["document_text_method"] = ""
        joined["review_status"] = ""
    if "originator_evidence_y" in joined:
        joined["originator_evidence_document"] = joined[
            "originator_evidence_y"
        ]
    else:
        joined["originator_evidence_document"] = ""
    if "originator_evidence_x" in joined:
        joined["originator_evidence"] = joined["originator_evidence_x"]
    joined["originator_group"] = joined["originator_group"].map(
        lambda value: _clean_text(value, "Não identificado")
    )
    curated_originator = joined["originator_group_curated"].map(_clean_text)
    joined.loc[curated_originator.ne(""), "originator_group"] = (
        curated_originator[curated_originator.ne("")]
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
    investor_columns = {
        "Pessoa física": "investor_person_natural",
        "Fundos": "investor_funds",
        "Instituições financeiras": "investor_financial_institutions",
        "Demais pessoas jurídicas": "investor_other_legal_entities",
        "Previdência": "investor_pension",
        "Seguradoras": "investor_insurers",
        "Investidor estrangeiro": "investor_foreign",
        "Clubes": "investor_clubs",
    }
    for column in investor_columns.values():
        joined[column] = pd.to_numeric(joined[column], errors="coerce")

    def investor_categories(row: pd.Series) -> str:
        available = [
            f"{label}: {int(row[column])}"
            for label, column in investor_columns.items()
            if pd.notna(row[column]) and float(row[column]) > 0
        ]
        return " | ".join(available) if available else "N/D"

    joined["investor_categories"] = joined.apply(
        investor_categories, axis=1
    )
    joined["investor_categories_source"] = joined["source_dataset"].map(
        lambda value: (
            "CVM, oferta_resolucao_160.csv, categorias Num_Invest_*"
            if "resolucao_160" in str(value)
            else "CVM, oferta_distribuicao.csv; categorias não disponíveis para esta linha"
        )
    )
    joined["ibba_coord_lead"] = joined["leader_name"].map(
        lambda value: _normalized_text(value) == IBBA_LEADER
    )
    curated_participant = (
        joined["ibba_participant"].astype(str).str.strip().str.casefold()
    )
    joined["ibba_participant"] = curated_participant.isin(
        {"true", "1", "sim", "yes"}
    ) | joined["ibba_coord_lead"]
    joined["ibba_participant_label"] = joined["ibba_participant"].map(
        {True: "Sim", False: "Não"}
    )
    joined["firm_commitment"] = joined["distribution_regime"].map(
        lambda value: "GARANTIA FIRME" in _normalized_text(value)
    )
    joined.loc[
        ~joined["firm_commitment"], "firm_commitment_coordinators"
    ] = "Não aplicável"
    joined.loc[
        ~joined["firm_commitment"], "firm_commitment_amount_by_coordinator"
    ] = "Não aplicável"

    rating_path = data_dir / RATING_REVIEW_FILENAME
    if rating_path.is_file():
        rating = pd.read_csv(rating_path, dtype=str, keep_default_na=False)
        required_rating = {
            "cnpj",
            "rating_document_count",
            "latest_document_id",
            "latest_document_date",
            "rating_agency",
            "rating_assigned",
            "rating_scope",
            "rating_availability_status",
            "rating_limitation",
        }
        missing_rating = sorted(required_rating.difference(rating.columns))
        if missing_rating:
            raise ClosedOfferRankingError(
                "curadoria de rating sem colunas: "
                + ", ".join(missing_rating)
            )
        rating["cnpj"] = rating["cnpj"].astype(str).str.replace(
            r"\D", "", regex=True
        ).str.zfill(14)
        rating = rating.sort_values(
            ["cnpj", "latest_document_date"], ascending=[True, False]
        ).drop_duplicates("cnpj")
        joined["cnpj_key"] = joined["cnpj_emissor"].astype(str).str.replace(
            r"\D", "", regex=True
        ).str.zfill(14)
        joined = joined.merge(
            rating[list(required_rating)],
            left_on="cnpj_key",
            right_on="cnpj",
            how="left",
            validate="many_to_one",
        )
        joined["rating_document_count"] = joined[
            "rating_document_count"
        ].map(lambda value: _clean_text(value, "0"))
        for column in (
            "latest_document_id",
            "latest_document_date",
            "rating_agency",
            "rating_assigned",
            "rating_scope",
        ):
            joined[column] = joined[column].map(
                lambda value: _clean_text(value, "N/D")
            )
        joined["rating_availability_status"] = joined[
            "rating_availability_status"
        ].map(
            lambda value: _clean_text(
                value, "sem documento público localizado"
            )
        )
        joined["rating_limitation"] = joined["rating_limitation"].map(
            lambda value: _clean_text(
                value,
                "Nenhum Relatório de Agência de Rating localizado no "
                "FundosNet em 27/07/2026.",
            )
        )
    else:
        for column in (
            "rating_document_count",
            "latest_document_id",
            "latest_document_date",
            "rating_agency",
            "rating_assigned",
            "rating_scope",
            "rating_availability_status",
            "rating_limitation",
        ):
            joined[column] = "N/D"

    ranking_parts: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    for period_label in TOP_PERIODS:
        period = joined[joined["period_label"].eq(period_label)].copy()
        period = period.sort_values(
            ["registered_volume_brl", "offer_id"],
            ascending=[False, True],
        ).reset_index(drop=True)
        top = period.head(top_n).copy()
        if len(top) < top_n and period_label != "2022 FY parcial":
            raise ClosedOfferRankingError(
                f"{period_label} possui apenas {len(top)} ofertas"
            )
        top["rank"] = range(1, len(top) + 1)
        top["ibba_coord_lead_label"] = top["ibba_coord_lead"].map(
            {True: "Sim", False: "Não"}
        )
        top["firm_commitment_label"] = top["firm_commitment"].map(
            {True: "Sim", False: "Não"}
        )
        ranking_parts.append(top)

        period_volume = float(period["registered_volume_brl"].sum())
        top_volume = float(top["registered_volume_brl"].sum())
        automatic = period["source_dataset"].eq(
            "oferta_resolucao_160.csv"
        )
        automatic_volume = float(
            period.loc[automatic, "registered_volume_brl"].sum()
        )
        ibba = top["ibba_coord_lead"]
        ibba_participation = top["ibba_participant"]
        firm = top["firm_commitment"]
        summary_rows.append(
            {
                "period_order": int(top["period_order"].iloc[0]),
                "period_label": period_label,
                "period_start": top["period_start"].iloc[0],
                "period_end": top["period_end"].iloc[0],
                "period_closed_offers": int(len(period)),
                "period_registered_volume_brl": period_volume,
                "automatic_rite_offers": int(automatic.sum()),
                "automatic_rite_offer_share": float(automatic.mean()),
                "automatic_rite_registered_volume_brl": automatic_volume,
                "automatic_rite_registered_volume_share": (
                    automatic_volume / period_volume if period_volume else 0.0
                ),
                "legacy_rite_offers": int((~automatic).sum()),
                "legacy_rite_registered_volume_brl": float(
                    period.loc[~automatic, "registered_volume_brl"].sum()
                ),
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
                "ibba_participation_offers_top15": int(
                    ibba_participation.sum()
                ),
                "ibba_participation_volume_top15_brl": float(
                    top.loc[
                        ibba_participation, "registered_volume_brl"
                    ].sum()
                ),
                "ibba_participation_share_top15_volume": float(
                    top.loc[
                        ibba_participation, "registered_volume_brl"
                    ].sum()
                    / top_volume
                ) if top_volume else 0.0,
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
                "comparability_status": (
                    "parcial_não_comparável"
                    if period_label == "2022 FY parcial"
                    else "comparável_todos_os_ritos"
                ),
                "coverage_note": (
                    "A tabela legada CVM contém somente sete ofertas de cotas de FIDC encerradas em 2022; o período é contextual e não sustenta comparação de crescimento."
                    if period_label == "2022 FY parcial"
                    else "Coorte de ofertas encerradas reconciliada entre rito automático e ritos ordinários/legados."
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
            "rite",
            "leader_name",
            "ibba_coord_lead",
            "ibba_coord_lead_label",
            "ibba_participant",
            "ibba_participant_label",
            "ibba_participant_entities",
            "ibba_participant_roles",
            "ibba_participation_source",
            "participants_source_url",
            "coordinator_entities",
            "firm_commitment_coordinators",
            "firm_commitment_amount_by_coordinator",
            "firm_commitment_source_limitation",
            "closing_document_url",
            "distribution_regime",
            "firm_commitment",
            "firm_commitment_label",
            "rating_document_count",
            "latest_document_id",
            "latest_document_date",
            "rating_agency",
            "rating_assigned",
            "rating_scope",
            "rating_availability_status",
            "rating_limitation",
            "publico",
            "investor_count",
            "investor_categories",
            "investor_categories_source",
            "investor_person_natural",
            "investor_funds",
            "investor_financial_institutions",
            "investor_other_legal_entities",
            "investor_pension",
            "investor_insurers",
            "investor_foreign",
            "investor_clubs",
            "originator_source",
            "originator_evidence",
            "originator_evidence_document",
            "originator_confidence",
            "document_text_method",
            "review_status",
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
