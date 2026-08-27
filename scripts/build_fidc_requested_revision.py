"""Build auditable CSVs for the 2026-08-27 director requests, offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd

from services.industry_requested_revision import (
    EXCLUDED_CNPJS, build_credit_screen, build_provider_comparison,
    build_stock_scenarios, prepare_funds,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/industry_study")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.data_dir / "generated_revision"
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    payload = json.loads((source / "artifact_payload.json").read_text())
    latest = payload["latest_complete"]
    periods = list(dict.fromkeys(row["competencia"] for row in payload["type_mix_history"]))
    funds = pd.read_csv(source / "base_fundo_cnpj.csv.gz", dtype={"cnpj_fundo": str}, low_memory=False)
    actions = pd.read_csv(args.data_dir / "taxonomy_review_actions.csv", dtype=str, keep_default_na=False)
    frame = prepare_funds(funds.loc[funds["competencia"].isin(periods)], actions)
    stock = build_stock_scenarios(frame, periods)
    original = stock.loc[stock["cenario"].eq("original")]
    published = pd.DataFrame(payload["type_mix_history"])
    for period in periods:
        actual = original.loc[original["competencia"].eq(period), "pl_brl"].sum()
        expected = published.loc[published["competencia"].eq(period), "pl"].sum()
        if abs(actual - expected) > 0.01:
            raise ValueError(f"PL original não reconcilia com o deck: {period}")
    screen = build_credit_screen(frame, latest)
    review_path = args.data_dir / "director_focal_document_review_20260827.csv"
    review = pd.read_csv(review_path, dtype=str, keep_default_na=False)
    if review["cnpj_fundo"].duplicated().any():
        raise ValueError("Revisão focal duplicada por CNPJ")
    review = review.merge(
        screen[["cnpj_fundo", "denominacao", "pl", "recorte_credito"]],
        on="cnpj_fundo", validate="one_to_one", how="left",
    ).rename(columns={"pl": "pl_brl", "recorte_credito": "recorte_triagem"})
    if review["pl_brl"].isna().any():
        raise ValueError("Documento focal sem fundo no perímetro atual")
    review_lookup = review.set_index("cnpj_fundo")
    screen["verificacao_focal_status"] = screen["cnpj_fundo"].map(review_lookup["status"]).fillna("Não revisto nesta rodada")
    screen["verificacao_focal_conclusao"] = screen["cnpj_fundo"].map(review_lookup["conclusao"]).fillna("")
    summary = screen.groupby("recorte_credito", as_index=False).agg(
        fundos=("cnpj_fundo", "nunique"), pl_brl=("pl", "sum"),
        denominador_pl_brl=("denominador_pl_brl", "first"), share_total=("share_total", "sum"),
    )
    coverage = screen.groupby(["classification_tier", "taxonomy_review_applied"], dropna=False, as_index=False).agg(
        fundos=("cnpj_fundo", "nunique"), pl_brl=("pl", "sum"), share_total=("share_total", "sum"),
    )
    providers, provider_lineage = build_provider_comparison(pd.DataFrame(payload["provider_historical_ranking"]), latest)
    exclusion = frame.loc[frame["excluido_cenario"], ["competencia", "cnpj_fundo", "denominacao", "categoria_slide", "pl"]]
    offers = pd.read_csv(args.data_dir / "industry_closed_offer_ticket_cohort.csv.gz", dtype={"cnpj_emissor": str})
    offer_id = offers["cnpj_emissor"].str.replace(r"\D", "", regex=True).str.zfill(14)
    excluded_offers = offers.loc[offer_id.isin(EXCLUDED_CNPJS)]
    if len(excluded_offers):
        raise ValueError("Fundos excluídos têm ofertas: recalcular emissões antes de exportar")
    latest_stock = stock.loc[stock["competencia"].eq(latest)]
    approved = screen["taxonomy_review_applied"].fillna(False).astype(str).str.lower().isin({"true", "1"})
    metrics = {
        "pl_original_brl": float(latest_stock.loc[latest_stock["cenario"].eq("original"), "pl_brl"].sum()),
        "pl_sem_dois_brl": float(latest_stock.loc[latest_stock["cenario"].eq("sem_tapso_petrobras"), "pl_brl"].sum()),
        "pl_excluido_brl": float(exclusion.loc[exclusion["competencia"].eq(latest), "pl"].sum()),
        "candidatos_pf_pj_brl": float(summary.loc[summary["recorte_credito"].isin(["PF pessoal / estudantil / BNPL (triagem)", "PJ / PF-PJ (triagem)"]), "pl_brl"].sum()),
        "fundos_exfic": len(screen),
        "fundos_com_override_aprovado": int(approved.sum()),
        "pl_override_aprovado_brl": float(screen.loc[approved, "pl"].sum()),
        "documentos_com_revisao_focal": len(review),
        "pl_documentos_com_revisao_focal_brl": float(review["pl_brl"].sum()),
        "total_paginas_documentos": int(pd.to_numeric(review["pages"]).sum()),
    }
    outputs = {
        "saldo_cenarios.csv": stock,
        "exclusoes_por_cnpj.csv": exclusion,
        "credito_triagem_resumo.csv": summary,
        "credito_triagem_cnpj.csv": screen,
        "cobertura_classificacao.csv": coverage,
        "prestadores_separados.csv": providers,
        "prestadores_linhagem.csv": provider_lineage,
        "emissoes_cenario.csv": pd.DataFrame(payload["issuance_taxonomy"]),
        "verificacao_documental_focal.csv": review,
        "metricas_reconciliacao.csv": pd.DataFrame(metrics.items(), columns=["metrica", "valor"]),
        "evidencias_taxonomia.csv": actions.loc[actions["cnpj_fundo"].isin(screen["cnpj_fundo"])],
    }
    for name, data in outputs.items():
        data.to_csv(output / name, index=False)
    # The presentation consumes CSV-round-tripped values, with no independent totals.
    deck_data = {"manifest": {"latest_complete": latest, "periods": periods}}
    for name in ("saldo_cenarios", "credito_triagem_resumo", "prestadores_separados"):
        deck_data[name] = pd.read_csv(output / f"{name}.csv").fillna("").to_dict("records")
    (output / "revision_payload.json").write_text(json.dumps(deck_data, ensure_ascii=False, allow_nan=False))
    files = [source / "base_fundo_cnpj.csv.gz", source / "artifact_payload.json", args.data_dir / "taxonomy_review_actions.csv", args.data_dir / "industry_closed_offer_ticket_cohort.csv.gz", review_path]
    manifest = {
        "schema": "industry_requested_revision.v1", "latest_complete": latest,
        "excluded_cnpjs": EXCLUDED_CNPJS, "periods": periods,
        "source_slide_mapping": {"saldo_tipos": 4, "taxonomia": 6, "prestadores": 34},
        "offers_tested_rows": len(offers), "excluded_offers_rows": len(excluded_offers),
        "offers_note": "Nenhuma oferta dos dois CNPJs na coorte usada pelos gráficos; emissões preservadas.",
        "credit_note": "PL integral dos fundos candidatos, sem estimar parcela da carteira. Pulverização e segregação PF/PJ não validadas; classificação cadastral, documental ou proxy preservada por linha.",
        "input_root": "data/industry_study",
        "inputs": [{"path": str(path.resolve().relative_to(args.data_dir.resolve())), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in files],
        "outputs": {name: {"rows": len(data), "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()} for name, data in outputs.items()},
    }
    manifest["outputs"]["revision_payload.json"] = {"sha256": hashlib.sha256((output / "revision_payload.json").read_bytes()).hexdigest()}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(summary.to_string(index=False))
    print(providers.loc[providers["competencia"].eq(latest) & providers["participante"].str.contains("Itaú|Kanastra"), ["papel", "participante", "pl_brl", "rank_periodo"]].to_string(index=False))


if __name__ == "__main__":
    main()
