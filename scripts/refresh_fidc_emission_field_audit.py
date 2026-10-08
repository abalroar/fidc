"""Reconcile the emission-field ledger with current fund and offer rankings.

Existing fund evidence follows the exact legal CNPJ into a later competence.
Offer terms follow the exact CNPJ/offer ID pair. New members retain N/D until
the normal documentary enrichment pipeline identifies a supporting source.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_fidc_revision_artifact_payload import (  # noqa: E402
    EMISSION_FIELD_AUDIT_COLUMNS,
    _load_emission_field_audit,
)
from services.industry_closed_offer_rankings import build_closed_offer_top15  # noqa: E402
from services.industry_comparative_period import ComparisonCut  # noqa: E402
from services.industry_offer_periods import offer_periods as comparative_offer_periods  # noqa: E402
from services.industry_taxonomy_review import (  # noqa: E402
    build_historical_top20_taxonomy_review,
    load_taxonomy_review_actions,
)

FUND_BLOCK = "slides 10–17"
OFFER_BLOCK = "slides 21–22"
FUND_EMISSION_ID = "N/D — tabela no nível do fundo"

OFFER_PERIODS = ("2023 FY", "2024 FY", "2025 FY", "2026 jan-jun")  # Legacy import compatibility.
IDENTITY_COLUMNS = {"bloco", "tabela", "cnpj", "emissao_id", "fundo"}
EVIDENCE_COLUMNS = tuple(
    column for column in EMISSION_FIELD_AUDIT_COLUMNS if column not in IDENTITY_COLUMNS
)


def _text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _cnpj(value: object) -> str:
    digits = re.sub(r"\D", "", _text(value))
    if not digits or len(digits) > 14:
        raise ValueError(f"CNPJ inválido no ledger/ranking: {value!r}")
    return digits.zfill(14)


def _offer_id(value: object) -> str:
    return re.sub(r"\.0+$", "", _text(value))


def _normalise_ledger(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for optional in ("remuneracao_por_tipo_cota", "fonte_remuneracao"):
        if optional not in output:
            output[optional] = "N/D"
    missing = set(EMISSION_FIELD_AUDIT_COLUMNS).difference(output.columns)
    if missing:
        raise ValueError(f"ledger sem colunas obrigatórias: {sorted(missing)}")
    output = output.loc[:, EMISSION_FIELD_AUDIT_COLUMNS].map(_text)
    output["cnpj"] = output["cnpj"].map(_cnpj)
    output["emissao_id"] = output["emissao_id"].map(_offer_id)
    output = output.replace("", "N/D")
    return output


def _require_unique(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    if frame.duplicated(columns).any():
        raise ValueError(f"{label} contém chave duplicada: {'/'.join(columns)}")


def reconcile_emission_field_audit(
    audit: pd.DataFrame,
    *,
    latest: str,
    top20_taxonomy_review: pd.DataFrame,
    closed_offer_top15: pd.DataFrame,
    history: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Build the 120+60 ledger without transferring terms across emissions."""
    if not re.fullmatch(r"\d{4}-\d{2}", latest):
        raise ValueError("competência deve seguir AAAA-MM")
    cut = ComparisonCut.from_competence(latest)
    offer_period_labels = tuple(period["period_label"] for period in comparative_offer_periods(cut))
    current = _normalise_ledger(audit)
    _require_unique(current[current["bloco"].eq(FUND_BLOCK)], ["tabela", "cnpj"], "ledger de fundos")
    _require_unique(current[current["bloco"].eq(OFFER_BLOCK)], ["tabela", "cnpj", "emissao_id"], "ledger de emissões")
    if history is not None and not history.empty:
        archive = _normalise_ledger(history)
        # The current ledger is authoritative for the same logical observation.
        source = pd.concat([archive, current], ignore_index=True).drop_duplicates(
            ["bloco", "tabela", "cnpj", "emissao_id"], keep="last"
        )
    else:
        source = current

    funds = top20_taxonomy_review[
        top20_taxonomy_review["competencia"].astype(str).isin((latest, f"{cut.year-1}-12"))
        & pd.to_numeric(top20_taxonomy_review["rank_tipo"], errors="coerce").le(15)
    ].copy()
    funds["cnpj_fundo"] = funds["cnpj_fundo"].map(_cnpj)
    funds["tabela"] = funds["tipo_exibicao"].map(_text) + " · " + funds["competencia"].map(_text)
    _require_unique(funds, ["tabela", "cnpj_fundo"], "ranking de fundos")
    counts = funds.groupby("tabela").size()
    if len(funds) != 120 or len(counts) != 8 or not counts.eq(15).all():
        raise ValueError("ranking de fundos deve fechar oito tabelas de 15 fundos")
    offers = closed_offer_top15[
        closed_offer_top15["period_label"].astype(str).isin(offer_period_labels)
        & pd.to_numeric(closed_offer_top15["rank"], errors="coerce").le(15)
    ].copy()
    offers["cnpj_emissor"] = offers["cnpj_emissor"].map(_cnpj)
    offers["offer_id"] = offers["offer_id"].map(_offer_id)
    _require_unique(offers, ["period_label", "offer_id", "cnpj_emissor"], "ranking de ofertas")
    if len(offers) != 60 or not offers.groupby("period_label").size().reindex(offer_period_labels, fill_value=0).eq(15).all():
        raise ValueError("ranking de ofertas deve fechar quatro tabelas de 15 emissões")

    fund_source = source[source["bloco"].eq(FUND_BLOCK)].copy()
    fund_source["competencia"] = fund_source["tabela"].str.extract(r"(\d{4}-\d{2})$")[0]
    if fund_source["competencia"].isna().any():
        raise ValueError("ledger de fundos contém tabela sem competência identificada")
    offer_source = source[source["bloco"].eq(OFFER_BLOCK)]
    rows: list[dict[str, str]] = []
    stats = {"fundos_preservados_chave_exata": 0, "fundos_evidencia_cnpj_anterior": 0,
             "fundos_novos_nd": 0, "ofertas_preservadas_id_cnpj": 0, "ofertas_novas_nd": 0}

    def new_row(block: str, table: str, cnpj: str, emission: str, name: str) -> dict[str, str]:
        row = dict.fromkeys(EMISSION_FIELD_AUDIT_COLUMNS, "N/D")
        row.update(bloco=block, tabela=table, cnpj=cnpj, emissao_id=emission, fundo=name or "N/D")
        row["status"] = "N/D preservado — entrada no ranking sem evidência documental no ledger"
        return row

    for rank in funds.sort_values(["competencia", "tipo_exibicao", "rank_tipo"]).to_dict(orient="records"):
        cnpj, table, competence = rank["cnpj_fundo"], rank["tabela"], str(rank["competencia"])
        row = new_row(FUND_BLOCK, table, cnpj, FUND_EMISSION_ID, _text(rank["denominacao"]))
        candidates = fund_source[fund_source["cnpj"].eq(cnpj) & fund_source["competencia"].le(competence)]
        exact = candidates[candidates["tabela"].eq(table)]
        if not exact.empty:
            selected = exact
            stat = "fundos_preservados_chave_exata"
        elif not candidates.empty:
            selected = candidates[candidates["competencia"].eq(candidates["competencia"].max())]
            stat = "fundos_evidencia_cnpj_anterior"
        else:
            selected = pd.DataFrame()
            stat = "fundos_novos_nd"
        if not selected.empty:
            evidence = selected.loc[:, EVIDENCE_COLUMNS].drop_duplicates()
            if len(evidence) != 1:
                raise ValueError(f"evidência ambígua para CNPJ {cnpj} em {competence}")
            row.update(evidence.iloc[0].to_dict())
        stats[stat] += 1
        rows.append(row)

    for rank in offers.sort_values(["period_label", "rank"]).to_dict(orient="records"):
        cnpj, emission = rank["cnpj_emissor"], rank["offer_id"]
        row = new_row(OFFER_BLOCK, str(rank["period_label"]), cnpj, emission, _text(rank.get("issuer_name")))
        candidates = offer_source[offer_source["cnpj"].eq(cnpj) & offer_source["emissao_id"].eq(emission)]
        exact = candidates[candidates["tabela"].eq(str(rank["period_label"]))]
        selected = exact if not exact.empty else candidates
        if not selected.empty:
            evidence = selected.loc[:, EVIDENCE_COLUMNS].drop_duplicates()
            if len(evidence) != 1:
                raise ValueError(f"evidência ambígua para emissão {emission}, CNPJ {cnpj}")
            row.update(evidence.iloc[0].to_dict())
            stats["ofertas_preservadas_id_cnpj"] += 1
        else:
            stats["ofertas_novas_nd"] += 1
        rows.append(row)
    output = pd.DataFrame(rows, columns=EMISSION_FIELD_AUDIT_COLUMNS)
    report: dict[str, object] = {"latest": latest, "rows": len(output), "blocks": output.groupby("bloco").size().to_dict(), **stats}
    return output, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/industry_study")
    parser.add_argument("--latest", required=True)
    ranks = parser.add_mutually_exclusive_group(required=True)
    ranks.add_argument("--funds", type=Path, help="base_fundo_cnpj.csv.gz para reconstruir as mesmas chaves do produtor")
    ranks.add_argument("--top20-taxonomy-review", type=Path)
    parser.add_argument("--closed-offer-top15", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    audit_path = args.audit or args.data_dir / "emission_field_audit.csv"
    output_path = args.output or audit_path
    history_path = args.history or audit_path.with_name("emission_field_audit_history.csv")
    report_path = args.report or output_path.with_name("emission_field_audit_refresh_manifest.json")
    audit = pd.read_csv(audit_path, dtype=str, keep_default_na=False)
    history = pd.read_csv(history_path, dtype=str, keep_default_na=False) if history_path.exists() else None
    if args.top20_taxonomy_review:
        top = pd.read_csv(args.top20_taxonomy_review, dtype=str, keep_default_na=False)
    else:
        funds = pd.read_csv(args.funds, dtype={"cnpj_fundo": str}, low_memory=False)
        vehicle = pd.read_csv(args.data_dir / "vehicle_monthly.csv.gz", low_memory=False)
        top = build_historical_top20_taxonomy_review(
            funds, load_taxonomy_review_actions(args.data_dir / "taxonomy_review_actions.csv"),
            periods=(f"{ComparisonCut.from_competence(args.latest).year-1}-12", args.latest), table_ii=vehicle,
        )
    offers = (
        pd.read_csv(args.closed_offer_top15, dtype=str, keep_default_na=False)
        if args.closed_offer_top15 else build_closed_offer_top15(args.data_dir).rankings
    )
    reconciled, report = reconcile_emission_field_audit(
        audit, latest=args.latest, top20_taxonomy_review=top, closed_offer_top15=offers, history=history,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="emission-ledger-") as directory:
        candidate = Path(directory) / "emission_field_audit.csv"
        reconciled.to_csv(candidate, index=False)
        selected_periods = {period["period_label"] for period in comparative_offer_periods(ComparisonCut.from_competence(args.latest))}
        current_offers = offers[offers["period_label"].isin(selected_periods)]
        _load_emission_field_audit(candidate, latest=args.latest, top20_taxonomy_review=top, closed_offer_top15=current_offers)
        report["sha256_before"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
        report["sha256_after"] = hashlib.sha256(candidate.read_bytes()).hexdigest()
        report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        archived = pd.concat(
            [frame for frame in (history, audit, reconciled) if frame is not None], ignore_index=True,
        )
        archived = _normalise_ledger(archived).drop_duplicates().reset_index(drop=True)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        archived.to_csv(history_path, index=False)
        report["history_rows"] = len(archived)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output_path.write_bytes(candidate.read_bytes())
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
