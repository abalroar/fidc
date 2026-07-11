"""Build a repeatable executive FIDC industry brief from materialized CVM data."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd


PLAYER_GROUPS = (
    "BTG PACTUAL",
    "QI TECH + SINGULARE",
    "OLIVEIRA TRUST",
    "ITAU/INTRAG",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--industry-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/fidc_presidente_bba_latest"),
    )
    return parser.parse_args()


def ascii_upper(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", text.upper())
        if not unicodedata.combining(character)
    )


def participant_group(value: object) -> str:
    text = ascii_upper(value)
    if "SINGULARE" in text or (
        ("QI " in text or "QITECH" in text)
        and any(token in text for token in ("CORRET", "DISTRIB", "CTVM", "GESTAO"))
    ):
        return "QI TECH + SINGULARE"
    if "INTRAG" in text or re.search(r"\bITAU\b", text):
        return "ITAU/INTRAG"
    if "BTG" in text and "PACTUAL" in text:
        return "BTG PACTUAL"
    if "OLIVEIRA TRUST" in text:
        return "OLIVEIRA TRUST"
    if "GENIAL" in text:
        return "GRUPO GENIAL"
    if "BEM - " in text or "BRADESCO" in text:
        return "GRUPO BRADESCO/BEM"
    if "BB GESTAO" in text or "BANCO DO BRASIL" in text:
        return "GRUPO BB"
    if "REAG" in text or "CBSF" in text:
        return "REAG/CBSF"
    return re.sub(r"\s+", " ", text).strip(" .,") or "NAO INFORMADO"


def bool_series(frame: pd.DataFrame, column: str) -> pd.Series:
    values = frame[column]
    if values.dtype == bool:
        return values.fillna(False)
    return values.astype("string").fillna("").str.upper().isin({"TRUE", "1", "S", "SIM"})


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return float(numerator / denominator) if denominator else None


def record(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return frame.iloc[0].to_dict()


def sanitize(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if pd.isna(value) or np.isinf(value) else float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value) if not isinstance(value, str) else False:
        return None
    return value


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    industry_dir = args.industry_dir

    metadata = json.loads((industry_dir / "metadata.json").read_text())
    current_month = str(metadata["competencia_snapshot"])
    current_month = f"{current_month[:4]}-{current_month[4:]}"
    previous_year_month = f"{int(current_month[:4]) - 1}-{current_month[5:]}"
    prior_year_end = f"{int(current_month[:4]) - 1}-12"
    ytd_start = f"{current_month[:4]}-01"

    industry = pd.read_csv(industry_dir / "industry_monthly.csv")
    vehicle = pd.read_csv(industry_dir / "vehicle_monthly.csv.gz", low_memory=False)
    snapshot = pd.read_csv(industry_dir / "industry_fund_snapshot.csv.gz", low_memory=False)
    offers = pd.read_csv(industry_dir / "issuance_offers.csv.gz", low_memory=False)
    cedentes = pd.read_csv(industry_dir / "cedentes_structured.csv.gz", low_memory=False)
    claim_audit = pd.read_csv(industry_dir / "industry_public_claim_audit.csv")

    for role in ("admin_nome", "gestor_nome", "custodiante_nome"):
        vehicle[f"{role}_group"] = vehicle[role].map(participant_group)
        snapshot[f"{role}_group"] = snapshot[role].map(participant_group)
    for role in ("administrador", "gestor", "custodiante"):
        offers[f"{role}_group"] = offers[role].map(participant_group)

    current_vehicle = vehicle.loc[vehicle["competencia"].eq(current_month)].copy()
    previous_vehicle = vehicle.loc[vehicle["competencia"].eq(previous_year_month)].copy()
    year_end_vehicle = vehicle.loc[vehicle["competencia"].eq(prior_year_end)].copy()
    ytd_vehicle = vehicle.loc[vehicle["competencia"].between(ytd_start, current_month)].copy()

    current_industry = record(industry.loc[industry["competencia"].eq(current_month)])
    previous_industry = record(industry.loc[industry["competencia"].eq(previous_year_month)])
    ytd_industry = industry.loc[industry["competencia"].between(ytd_start, current_month)]

    current_fic = bool_series(current_vehicle, "is_fic_fidc")
    current_np = bool_series(current_vehicle, "is_np")
    ytd_fic = bool_series(ytd_vehicle, "is_fic_fidc")
    ytd_np = bool_series(ytd_vehicle, "is_np")

    market_views = {
        "pl_cvm_gross_brl": float(current_vehicle["pl"].sum()),
        "pl_ex_fic_brl": float(current_vehicle.loc[~current_fic, "pl"].sum()),
        "pl_ex_fic_np_brl": float(current_vehicle.loc[~current_fic & ~current_np, "pl"].sum()),
        "flow_ytd_cvm_gross_brl": float(ytd_vehicle["captacao_liquida"].sum()),
        "flow_ytd_ex_fic_np_brl": float(
            ytd_vehicle.loc[~ytd_fic & ~ytd_np, "captacao_liquida"].sum()
        ),
        "pl_yoy_growth": safe_ratio(
            float(current_industry["pl_total"]), float(previous_industry["pl_total"])
        ),
        "pl_yoy_delta_brl": float(current_industry["pl_total"] - previous_industry["pl_total"]),
        "vehicles_current": int(current_industry["n_veiculos"]),
        "vehicles_yoy_delta": int(current_industry["n_veiculos"] - previous_industry["n_veiculos"]),
        "applications_ytd_brl": float(ytd_industry["captacoes"].sum()),
        "redemptions_ytd_brl": float(ytd_industry["resgates"].sum()),
        "amortizations_ytd_brl": float(ytd_industry["amortizacoes"].sum()),
    }
    if market_views["pl_yoy_growth"] is not None:
        market_views["pl_yoy_growth"] -= 1

    public_claims = {}
    for claim_id in (
        "seu_dinheiro_fidc_pl_may_2026",
        "seu_dinheiro_fidc_net_flow_2026_ytd_may",
        "anbima_fidc_offers_2026_jan_may",
    ):
        row = claim_audit.loc[claim_audit["claim_id"].eq(claim_id)]
        if not row.empty:
            public_claims[claim_id] = row.iloc[0].to_dict()
    pl_public = float(public_claims["seu_dinheiro_fidc_pl_may_2026"]["public_value"])
    flow_public = float(public_claims["seu_dinheiro_fidc_net_flow_2026_ytd_may"]["public_value"])

    current_by_group = current_vehicle.groupby("admin_nome_group", dropna=False).agg(
        pl=("pl", "sum"), vehicles=("cnpj", "nunique"), funds=("cnpj_fundo", "nunique")
    )
    previous_by_group = previous_vehicle.groupby("admin_nome_group", dropna=False).agg(
        pl=("pl", "sum"), vehicles=("cnpj", "nunique"), funds=("cnpj_fundo", "nunique")
    )
    year_end_by_group = year_end_vehicle.groupby("admin_nome_group", dropna=False).agg(
        pl=("pl", "sum")
    )
    ytd_flow_by_group = ytd_vehicle.groupby("admin_nome_group", dropna=False).agg(
        applications=("captacoes", "sum"),
        redemptions=("resgates", "sum"),
        amortizations=("amortizacoes", "sum"),
        net_flow=("captacao_liquida", "sum"),
    )

    valid_offers = offers.loc[
        offers["volume_registrado_valido"].astype(bool)
        & offers["competencia"].between(ytd_start, current_month)
    ]
    offer_by_group = valid_offers.groupby("administrador_group", dropna=False).agg(
        offer_volume=("valor_total_registrado_brl", "sum"),
        offers=("offer_id", "nunique"),
        issuers=("cnpj_emissor", "nunique"),
    )
    closed_offers = offers.loc[
        offers["volume_encerrado_conservador"].astype(bool)
        & offers["competencia"].between(ytd_start, current_month)
    ]

    current_fund = current_vehicle.groupby(["cnpj_fundo", "admin_nome_group"], dropna=False).agg(
        name=("denominacao", "first"), pl=("pl", "sum")
    ).reset_index()
    previous_fund = previous_vehicle.groupby("cnpj_fundo", dropna=False).agg(
        pl_previous=("pl", "sum")
    ).reset_index()
    current_fund = current_fund.merge(previous_fund, on="cnpj_fundo", how="left")
    current_fund["pl_previous"] = current_fund["pl_previous"].fillna(0.0)
    current_fund["pl_delta_yoy"] = current_fund["pl"] - current_fund["pl_previous"]
    ytd_fund_flow = ytd_vehicle.groupby(["cnpj_fundo", "admin_nome_group"], dropna=False).agg(
        net_flow=("captacao_liquida", "sum")
    ).reset_index()

    scorecard_rows: list[dict[str, object]] = []
    top_fund_rows: list[dict[str, object]] = []
    for group in PLAYER_GROUPS:
        current = current_by_group.loc[group] if group in current_by_group.index else pd.Series(dtype=float)
        previous = previous_by_group.loc[group] if group in previous_by_group.index else pd.Series(dtype=float)
        year_end = year_end_by_group.loc[group] if group in year_end_by_group.index else pd.Series(dtype=float)
        flow = ytd_flow_by_group.loc[group] if group in ytd_flow_by_group.index else pd.Series(dtype=float)
        offer = offer_by_group.loc[group] if group in offer_by_group.index else pd.Series(dtype=float)
        funds = current_fund.loc[current_fund["admin_nome_group"].eq(group)].sort_values(
            "pl", ascending=False
        )
        flows = ytd_fund_flow.loc[ytd_fund_flow["admin_nome_group"].eq(group)].sort_values(
            "net_flow", ascending=False
        )
        positive_flows = flows.loc[flows["net_flow"].gt(0)]
        positive_flow_total = float(positive_flows["net_flow"].sum())
        snapshot_admin = snapshot.loc[snapshot["admin_nome_group"].eq(group)]
        snapshot_custody = snapshot.loc[snapshot["custodiante_nome_group"].eq(group)]
        snapshot_manager = snapshot.loc[snapshot["gestor_nome_group"].eq(group)]
        subordination = snapshot_admin.loc[
            bool_series(snapshot_admin, "tem_sub_minima")
            & snapshot_admin["sub_min_pct_median"].notna()
        ]

        current_pl = float(current.get("pl", 0.0))
        previous_pl = float(previous.get("pl", 0.0))
        year_end_pl = float(year_end.get("pl", 0.0))
        net_flow = float(flow.get("net_flow", 0.0))
        scorecard_rows.append(
            {
                "group": group,
                "pl_current_brl": current_pl,
                "share_current": safe_ratio(current_pl, float(current_vehicle["pl"].sum())),
                "vehicles_current": int(current.get("vehicles", 0)),
                "funds_current": int(current.get("funds", 0)),
                "median_fund_brl": float(funds["pl"].median()) if not funds.empty else 0.0,
                "pl_yoy_delta_brl": current_pl - previous_pl,
                "pl_yoy_growth": safe_ratio(current_pl, previous_pl),
                "share_yoy_change_pp": (
                    safe_ratio(current_pl, float(current_vehicle["pl"].sum()))
                    - safe_ratio(previous_pl, float(previous_vehicle["pl"].sum()))
                )
                * 100,
                "vehicles_yoy_delta": int(current.get("vehicles", 0) - previous.get("vehicles", 0)),
                "pl_ytd_delta_brl": current_pl - year_end_pl,
                "net_flow_ytd_brl": net_flow,
                "pl_flow_residual_ytd_brl": current_pl - year_end_pl - net_flow,
                "positive_fund_flow_ytd_brl": positive_flow_total,
                "positive_flow_top1_share": safe_ratio(
                    float(positive_flows.head(1)["net_flow"].sum()), positive_flow_total
                ),
                "positive_flow_top5_share": safe_ratio(
                    float(positive_flows.head(5)["net_flow"].sum()), positive_flow_total
                ),
                "positive_flow_concentration_note": (
                    "share of gross positive fund-level net flows; denominator is not aggregate net flow"
                ),
                "offer_volume_ytd_brl": float(offer.get("offer_volume", 0.0)),
                "offers_ytd": int(offer.get("offers", 0)),
                "offer_issuers_ytd": int(offer.get("issuers", 0)),
                "average_offer_ticket_brl": safe_ratio(
                    float(offer.get("offer_volume", 0.0)), int(offer.get("offers", 0))
                ),
                "admin_pl_snapshot_brl": float(snapshot_admin["pl"].sum()),
                "custody_pl_snapshot_brl": float(snapshot_custody["pl"].sum()),
                "manager_pl_snapshot_brl": float(snapshot_manager["pl"].sum()),
                "admin_funds_snapshot": int(snapshot_admin["cnpj_fundo"].nunique()),
                "custody_funds_snapshot": int(snapshot_custody["cnpj_fundo"].nunique()),
                "manager_funds_snapshot": int(snapshot_manager["cnpj_fundo"].nunique()),
                "admin_same_custody_share": safe_ratio(
                    float(snapshot_admin.loc[snapshot_admin["custodiante_nome_group"].eq(group), "pl"].sum()),
                    float(snapshot_admin["pl"].sum()),
                ),
                "admin_same_manager_share": safe_ratio(
                    float(snapshot_admin.loc[snapshot_admin["gestor_nome_group"].eq(group), "pl"].sum()),
                    float(snapshot_admin["pl"].sum()),
                ),
                "top1_pl_share": safe_ratio(float(funds.head(1)["pl"].sum()), current_pl),
                "top5_pl_share": safe_ratio(float(funds.head(5)["pl"].sum()), current_pl),
                "subordination_sample_funds": int(subordination["cnpj_fundo"].nunique()),
                "subordination_median_pct": (
                    float(subordination["sub_min_pct_median"].median())
                    if not subordination.empty
                    else None
                ),
                "criteria_sample_funds": int(
                    snapshot_admin.loc[snapshot_admin["criteria_rows"].fillna(0).gt(0), "cnpj_fundo"].nunique()
                ),
            }
        )
        top = funds.head(10).copy()
        top.insert(0, "group", group)
        top_fund_rows.extend(top.to_dict("records"))

    scorecard = pd.DataFrame(scorecard_rows)
    scorecard["pl_yoy_growth"] = scorecard["pl_yoy_growth"] - 1
    top_funds = pd.DataFrame(top_fund_rows)

    admin_group_monthly = vehicle.groupby(["competencia", "admin_nome_group"], dropna=False).agg(
        pl=("pl", "sum"), vehicles=("cnpj", "nunique")
    ).reset_index()
    current_admin = admin_group_monthly.loc[admin_group_monthly["competencia"].eq(current_month)]
    previous_admin = admin_group_monthly.loc[
        admin_group_monthly["competencia"].eq(previous_year_month),
        ["admin_nome_group", "pl"],
    ].rename(columns={"pl": "pl_previous"})
    movers = current_admin.merge(previous_admin, on="admin_nome_group", how="left")
    movers["pl_previous"] = movers["pl_previous"].fillna(0.0)
    movers["pl_delta_yoy"] = movers["pl"] - movers["pl_previous"]
    movers["pl_yoy_growth"] = np.where(
        movers["pl_previous"].gt(0), movers["pl"] / movers["pl_previous"] - 1, np.nan
    )
    movers = movers.sort_values("pl_delta_yoy", ascending=False)

    accepted = cedentes.loc[
        bool_series(cedentes, "ativo_curadoria") & cedentes["candidate_status"].eq("accepted")
    ].copy()
    accepted["participant"] = accepted["nome_fantasia"].fillna("").astype(str).str.strip()
    empty_name = accepted["participant"].eq("")
    accepted.loc[empty_name, "participant"] = accepted.loc[empty_name, "razao_social"].fillna("")
    accepted["participant_normalized"] = accepted["participant"].map(ascii_upper)
    accepted["linked_pl_brl"] = pd.to_numeric(accepted["pl"], errors="coerce").fillna(
        pd.to_numeric(accepted["pl_atual_brl"], errors="coerce")
    ).fillna(0.0)
    participant_pairs = accepted.sort_values("score_confianca_final", ascending=False).drop_duplicates(
        ["cnpj_fundo", "participant_type", "cnpj_participante", "participant_normalized"]
    )
    participant_summary = participant_pairs.groupby(
        ["participant_type", "participant_normalized", "cnpj_participante"], dropna=False
    ).agg(
        funds=("cnpj_fundo", "nunique"),
        linked_pl_brl=("linked_pl_brl", "sum"),
        confidence_median=("score_confianca_final", "median"),
        sector=("setor", lambda values: " | ".join(sorted(set(values.dropna().astype(str)))[:2])),
    ).reset_index()
    participant_summary = participant_summary.sort_values(
        ["participant_type", "funds", "linked_pl_brl"], ascending=[True, False, False]
    )

    claim_range = {
        "anbima_pl_brl": pl_public,
        "cvm_pl_gross_brl": market_views["pl_cvm_gross_brl"],
        "cvm_pl_ex_fic_np_brl": market_views["pl_ex_fic_np_brl"],
        "cvm_pl_ex_fic_np_gap_pct": market_views["pl_ex_fic_np_brl"] / pl_public - 1,
        "anbima_flow_ytd_brl": flow_public,
        "cvm_flow_ytd_gross_brl": market_views["flow_ytd_cvm_gross_brl"],
        "cvm_flow_ytd_ex_fic_np_brl": market_views["flow_ytd_ex_fic_np_brl"],
        "cvm_flow_ytd_ex_fic_np_gap_pct": market_views["flow_ytd_ex_fic_np_brl"] / flow_public - 1,
        "anbima_offers_ytd_brl": float(
            public_claims["anbima_fidc_offers_2026_jan_may"]["public_value"]
        ),
        "cvm_offers_registered_valid_brl": float(valid_offers["valor_total_registrado_brl"].sum()),
        "cvm_offers_closed_conservative_brl": float(
            closed_offers["valor_total_registrado_brl"].sum()
        ),
    }

    scorecard.to_csv(args.output_dir / "player_scorecard.csv", index=False)
    top_funds.to_csv(args.output_dir / "top_funds.csv", index=False)
    movers.to_csv(args.output_dir / "admin_movers.csv", index=False)
    participant_summary.to_csv(args.output_dir / "participant_signals.csv", index=False)

    payload = sanitize(
        {
            "schema_version": "fidc-executive-brief/v2",
            "as_of": current_month,
            "previous_year_month": previous_year_month,
            "market": market_views,
            "claim_reconciliation": claim_range,
            "players": scorecard.to_dict("records"),
            "top_funds": top_funds.to_dict("records"),
            "participant_coverage": {
                "accepted_rows": len(accepted),
                "accepted_funds": int(accepted["cnpj_fundo"].nunique()),
                "linked_pl_brl": float(accepted.drop_duplicates("cnpj_fundo")["linked_pl_brl"].sum()),
                "linked_pl_share": safe_ratio(
                    float(accepted.drop_duplicates("cnpj_fundo")["linked_pl_brl"].sum()),
                    float(current_vehicle["pl"].sum()),
                ),
            },
            "sources": {
                "industry_monthly": str(industry_dir / "industry_monthly.csv"),
                "vehicle_monthly": str(industry_dir / "vehicle_monthly.csv.gz"),
                "fund_snapshot": str(industry_dir / "industry_fund_snapshot.csv.gz"),
                "offers": str(industry_dir / "issuance_offers.csv.gz"),
                "cedentes": str(industry_dir / "cedentes_structured.csv.gz"),
                "public_claim_audit": str(industry_dir / "industry_public_claim_audit.csv"),
            },
        }
    )
    (args.output_dir / "executive_brief.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps({"output_dir": str(args.output_dir), "as_of": current_month}, ensure_ascii=False))


if __name__ == "__main__":
    main()
