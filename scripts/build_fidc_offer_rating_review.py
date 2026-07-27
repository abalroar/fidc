#!/usr/bin/env python3
"""Build the offer-level rating review used by the annual Top 15 tables."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from services.industry_closed_offer_rankings import build_closed_offer_top15


PERIOD_ORDER = {
    "2026 jan-jun": 0,
    "2025 FY": 1,
    "2024 FY": 2,
    "2023 FY": 3,
    "2022 FY parcial": 4,
}


def _clean(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text and text.casefold() != "nan" else default


def _cnpj(value: object) -> str:
    digits = "".join(char for char in str(value or "") if char.isdigit())
    return digits.zfill(14) if digits else ""


def build(data_dir: Path) -> pd.DataFrame:
    top15 = build_closed_offer_top15(data_dir, include_ratings=False).rankings.copy()
    top15["rank"] = pd.to_numeric(top15["rank"], errors="raise").astype(int)
    top15["offer_id"] = top15["offer_id"].astype(str).str.strip()
    top15["cnpj"] = top15["cnpj_emissor"].map(_cnpj)
    top15["issuer_name"] = top15["nome_emissor"].map(_clean)
    inherited_rating_columns = [
        column
        for column in top15.columns
        if column.startswith("rating_")
        or column in {"latest_document_id", "latest_document_date"}
    ]
    top15 = top15.drop(columns=inherited_rating_columns)

    fund_review = pd.read_csv(
        data_dir / "industry_offer_rating_review.csv",
        dtype=str,
        keep_default_na=False,
    )
    fund_review["cnpj"] = fund_review["cnpj"].map(_cnpj)
    fund_review = fund_review.rename(
        columns={
            "latest_document_id": "fund_latest_document_id",
            "latest_document_date": "fund_latest_document_date",
            "rating_availability_status": "fund_rating_status",
            "rating_limitation": "fund_rating_limitation",
            "rating_agency": "fund_rating_agency",
            "rating_assigned": "fund_rating_assigned",
            "rating_scope": "fund_rating_scope",
        }
    )
    fund_columns = [
        "cnpj",
        "rating_document_count",
        "fund_latest_document_id",
        "fund_latest_document_date",
        "fund_rating_status",
        "fund_rating_limitation",
    ]
    top15 = top15.merge(
        fund_review[fund_columns].drop_duplicates("cnpj"),
        on="cnpj",
        how="left",
        validate="many_to_one",
    )

    curation = pd.read_csv(
        data_dir / "industry_offer_rating_curation.csv",
        dtype=str,
        keep_default_na=False,
    )
    curation["offer_id"] = curation["offer_id"].astype(str).str.strip()
    if curation["offer_id"].duplicated().any():
        duplicates = sorted(curation.loc[curation["offer_id"].duplicated(), "offer_id"])
        raise ValueError(f"Curadoria contém offer_id duplicado: {duplicates}")
    unknown = sorted(set(curation["offer_id"]) - set(top15["offer_id"]))
    if unknown:
        raise ValueError(f"Curadoria contém ofertas fora do Top 15: {unknown}")
    top15 = top15.merge(curation, on="offer_id", how="left", validate="one_to_one")

    curated = top15["rating_match_status"].fillna("").str.strip().ne("")
    has_fund_document = top15["fund_latest_document_id"].fillna("").str.strip().ne("")
    top15["rating_document_count"] = top15["rating_document_count"].map(
        lambda value: _clean(value, "0")
    )
    for column in ("rating_agency", "rating_assigned", "rating_scope"):
        top15[column] = top15[column].map(lambda value: _clean(value, "N/D"))
    top15["latest_document_id"] = top15["latest_document_id"].map(_clean)
    top15["latest_document_date"] = top15["latest_document_date"].map(_clean)
    top15["rating_source_type"] = top15["rating_source_type"].map(_clean)
    top15["rating_source_url"] = top15["rating_source_url"].map(_clean)
    top15["rating_match_status"] = top15["rating_match_status"].map(_clean)
    top15["rating_evidence"] = top15["rating_evidence"].map(_clean)
    top15["rating_limitation"] = top15["rating_limitation"].map(_clean)

    fund_only = ~curated & has_fund_document
    top15.loc[fund_only, "latest_document_id"] = top15.loc[
        fund_only, "fund_latest_document_id"
    ]
    top15.loc[fund_only, "latest_document_date"] = top15.loc[
        fund_only, "fund_latest_document_date"
    ]
    top15.loc[fund_only, "rating_source_type"] = "FundosNet"
    top15.loc[fund_only, "rating_source_url"] = top15.loc[
        fund_only, "fund_latest_document_id"
    ].map(
        lambda document_id: (
            "https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento"
            f"?id={document_id}&cvm=true"
        )
    )
    top15.loc[fund_only, "rating_match_status"] = (
        "documento do fundo sem vínculo comprovado à emissão"
    )
    top15.loc[fund_only, "rating_evidence"] = (
        "Relatório público localizado para o fundo; emissão, série ou subclasse "
        "do Top 15 não conciliada com segurança."
    )
    top15.loc[fund_only, "rating_limitation"] = (
        "Agência e rating mantidos como N/D porque o documento não comprova "
        "aplicação à mesma emissão, série ou subclasse."
    )

    no_document = ~curated & ~has_fund_document
    top15.loc[no_document, "rating_match_status"] = (
        "sem documento público verificável"
    )
    top15.loc[no_document, "rating_evidence"] = (
        "Nenhum relatório de rating conciliável com a emissão foi localizado."
    )
    top15.loc[no_document, "rating_limitation"] = (
        "Agência e rating mantidos como N/D por ausência de documento público "
        "verificável para a emissão."
    )
    top15["rating_availability_status"] = curated.map(
        {True: "rating da emissão verificado", False: "N/D para a emissão"}
    )

    columns = [
        "offer_id",
        "period_label",
        "rank",
        "cnpj",
        "issuer_name",
        "rating_document_count",
        "latest_document_id",
        "latest_document_date",
        "rating_agency",
        "rating_assigned",
        "rating_scope",
        "rating_source_type",
        "rating_source_url",
        "rating_match_status",
        "rating_evidence",
        "rating_availability_status",
        "rating_limitation",
    ]
    top15["_period_order"] = top15["period_label"].map(PERIOD_ORDER)
    result = top15.sort_values(["_period_order", "rank"])[columns].reset_index(drop=True)
    if len(result) != 67 or result["offer_id"].nunique() != 67:
        raise ValueError(
            "Revisão de ratings deveria conter 67 ofertas únicas "
            f"e contém {len(result)} linhas/{result['offer_id'].nunique()} ofertas."
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/industry_study"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/industry_study/industry_offer_rating_by_offer.csv"),
    )
    args = parser.parse_args()
    result = build(args.data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    verified = int(result["rating_agency"].ne("N/D").sum())
    print(f"{args.output}: {len(result)} ofertas; {verified} ratings verificados")


if __name__ == "__main__":
    main()
