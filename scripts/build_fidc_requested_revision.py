"""Build auditable CSVs for the 2026-09-01 director revision, offline."""
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
    EXCLUDED_CNPJS,
    PF_PJ_CATEGORY,
    PF_PJ_LEDGER_FILENAME,
    build_category_cnpj_ledger,
    build_issuance_by_display_category,
    build_provider_comparison,
    build_stock_scenarios,
    load_pfpj_ledger,
    prepare_funds,
)
from services.industry_taxonomy_review import normalize_cnpj


def truthy(values: pd.Series) -> pd.Series:
    return values.fillna(False).astype(str).str.lower().isin({"true", "1", "sim"})


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/industry_study")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.data_dir / "generated_revision"
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)

    payload_path = source / "artifact_payload.json"
    payload = json.loads(payload_path.read_text())
    latest = payload["latest_complete"]
    periods = list(dict.fromkeys(row["competencia"] for row in payload["type_mix_history"]))
    fund_path = source / "base_fundo_cnpj.csv.gz"
    action_path = args.data_dir / "taxonomy_review_actions.csv"
    pfpj_path = args.data_dir / PF_PJ_LEDGER_FILENAME
    offer_path = args.data_dir / "industry_closed_offer_ticket_cohort.csv.gz"
    anbima_offer_path = args.data_dir / "industry_anbima_market_offers.csv"
    vehicle_path = args.data_dir / "vehicle_monthly.csv.gz"

    funds = pd.read_csv(fund_path, dtype={"cnpj_fundo": str, "cnpj_classe": str}, low_memory=False)
    actions = pd.read_csv(action_path, dtype=str, keep_default_na=False)
    pfpj = load_pfpj_ledger(pfpj_path)
    frame = prepare_funds(
        funds.loc[funds["competencia"].isin(periods)],
        actions,
        pfpj,
    )
    stock = build_stock_scenarios(frame, periods)
    original = stock.loc[stock["cenario"].eq("original")]
    published = pd.DataFrame(payload["type_mix_history"])
    for period in periods:
        actual = original.loc[original["competencia"].eq(period), "pl_brl"].sum()
        expected = published.loc[published["competencia"].eq(period), "pl"].sum()
        if abs(actual - expected) > 0.01:
            raise ValueError(f"PL original não reconcilia com o deck: {period}")

    category_ledger = build_category_cnpj_ledger(frame, latest)
    selected = pfpj.loc[pfpj["incluir_pfpj"]].copy()
    latest_selected = category_ledger.loc[
        category_ledger["categoria_slide"].eq(PF_PJ_CATEGORY),
        ["cnpj_fundo", "denominacao", "pl_brl"],
    ]
    selected = selected.merge(
        latest_selected,
        on="cnpj_fundo",
        how="left",
        validate="one_to_one",
        suffixes=("_auditoria", "_base"),
    )
    if selected["pl_brl_base"].isna().any():
        raise ValueError("CNPJ PF/PJ incluído não localizado no saldo de jun/26")
    if (selected["pl_brl_auditoria"] - selected["pl_brl_base"]).abs().gt(0.01).any():
        raise ValueError("PL PF/PJ divergente entre auditoria e base do deck")

    offers = pd.read_csv(offer_path, dtype={"cnpj_emissor": str}, low_memory=False)
    anbima = pd.read_csv(anbima_offer_path)
    anbima_2023 = anbima.loc[
        anbima["instrument_label"].eq("FIDCs")
        & anbima["period_label"].eq("2023 FY"),
        "closed_volume_brl",
    ]
    if len(anbima_2023) != 1:
        raise ValueError("Total ANBIMA 2023 ausente ou duplicado")

    all_funds = pd.read_csv(
        fund_path,
        usecols=["cnpj_fundo", "cnpj_classe", "is_fic_fidc"],
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    fic_rows = all_funds.loc[truthy(all_funds["is_fic_fidc"])]
    fic_cnpjs = set(fic_rows["cnpj_fundo"].map(normalize_cnpj))
    fic_cnpjs.update(
        fic_rows.loc[fic_rows["cnpj_classe"].str.len().eq(14), "cnpj_classe"].map(normalize_cnpj)
    )
    vehicle = pd.read_csv(vehicle_path, usecols=["cnpj", "is_fic_fidc"], dtype=str, keep_default_na=False)
    fic_cnpjs.update(vehicle.loc[truthy(vehicle["is_fic_fidc"]), "cnpj"].map(normalize_cnpj))

    issuance, issuance_detail, issuance_audit = build_issuance_by_display_category(
        offers,
        category_ledger,
        anbima_2023_brl=float(anbima_2023.iloc[0]),
        fic_cnpjs=fic_cnpjs,
    )
    excluded_offer_mask = issuance_detail["cnpj_n"].isin(EXCLUDED_CNPJS)
    if excluded_offer_mask.any():
        raise ValueError("TAPSO/Petrobras têm emissões: o cenário precisa excluí-las do fluxo")

    providers, provider_lineage = build_provider_comparison(
        pd.DataFrame(payload["provider_historical_ranking"]), latest
    )
    exclusion = frame.loc[
        frame["excluido_cenario"],
        ["competencia", "cnpj_fundo", "denominacao", "categoria_slide", "pl"],
    ]
    latest_stock = stock.loc[stock["competencia"].eq(latest)]
    pfpj_value = float(
        latest_stock.loc[
            latest_stock["cenario"].eq("sem_tapso_petrobras")
            & latest_stock["categoria"].eq(PF_PJ_CATEGORY),
            "pl_brl",
        ].iloc[0]
    )
    finance_value = float(
        latest_stock.loc[
            latest_stock["cenario"].eq("sem_tapso_petrobras")
            & latest_stock["categoria"].eq("Financeiro"),
            "pl_brl",
        ].iloc[0]
    )
    metrics = {
        "pl_original_brl": float(latest_stock.loc[latest_stock["cenario"].eq("original"), "pl_brl"].sum()),
        "pl_sem_tapso_petrobras_brl": float(latest_stock.loc[latest_stock["cenario"].eq("sem_tapso_petrobras"), "pl_brl"].sum()),
        "pl_excluido_tapso_petrobras_brl": float(exclusion.loc[exclusion["competencia"].eq(latest), "pl"].sum()),
        "pfpj_fundos_incluidos": len(selected),
        "pfpj_pl_brl": pfpj_value,
        "financeiro_apos_pfpj_sem_tapso_petrobras_brl": finance_value,
        "pfpj_share_sem_tapso_petrobras": pfpj_value / float(latest_stock.loc[latest_stock["cenario"].eq("sem_tapso_petrobras"), "pl_brl"].sum()),
        "pfpj_posicoes_reportadas": int(
            selected["cobertura_mensal"].str.extract(r"^(\d+)")[0].astype(int).sum()
        ),
        "pfpj_total_devedores": "N/D",
        "pfpj_exposicao_efetiva": "N/D",
    }
    category_method = pd.DataFrame([
        {
            "categoria": PF_PJ_CATEGORY,
            "criterio": "24 CNPJs aprovados no ledger; regulamento integral confirma crédito direto PF/PJ elegível e Top1 mensal <=1% dos DC brutos; Sólido e BizCapital excluídos por decisão do usuário.",
            "fonte_operacional": PF_PJ_LEDGER_FILENAME,
            "regra_temporal": "Lista congelada em jun/26 e retroaplicada às séries e ofertas; conflito futuro exige nova decisão.",
        },
        {
            "categoria": "Recuperação / NP",
            "criterio": "Após overlay documental aprovado: Tipo ANBIMA Outros + Foco Recuperação.",
            "fonte_operacional": "taxonomy_review_actions.csv + base_fundo_cnpj.csv.gz",
            "regra_temporal": "Decisão única por CNPJ do ledger, aplicada ao histórico publicado.",
        },
        {
            "categoria": "Precatórios / ações",
            "criterio": "Após overlay documental aprovado: Tipo ANBIMA Outros + Foco Poder Público.",
            "fonte_operacional": "taxonomy_review_actions.csv + base_fundo_cnpj.csv.gz",
            "regra_temporal": "Decisão única por CNPJ do ledger, aplicada ao histórico publicado.",
        },
        {
            "categoria": "Multicedente / multisacado",
            "criterio": "Após overlay documental aprovado: Tipo ANBIMA Outros + Foco Multicarteira Outros ou Multicedente/Multissacado.",
            "fonte_operacional": "taxonomy_review_actions.csv + base_fundo_cnpj.csv.gz",
            "regra_temporal": "Decisão única por CNPJ do ledger, aplicada ao histórico publicado.",
        },
    ])

    issuance_public_columns = [
        "period_key", "period_label", "data_encerramento", "cnpj_n", "nome_emissor",
        "numero_requerimento", "registered_volume_brl", "scale_factor",
        "volume_apurado_brl", "categoria", "match_categoria", "is_fic",
        "source_dataset", "source_url",
    ]
    outputs = {
        "saldo_cenarios.csv": stock,
        "exclusoes_por_cnpj.csv": exclusion,
        "pfpj_26_decisoes.csv": pfpj,
        "pfpj_24_incluidos.csv": selected,
        "categorias_cnpj_jun26.csv": category_ledger,
        "criterios_categorias.csv": category_method,
        "emissoes_por_categoria.csv": issuance,
        "emissoes_por_cnpj.csv": issuance_detail[issuance_public_columns],
        "emissoes_auditoria.csv": issuance_audit,
        "prestadores_separados.csv": providers,
        "prestadores_linhagem.csv": provider_lineage,
        "metricas_reconciliacao.csv": pd.DataFrame(metrics.items(), columns=["metrica", "valor"]),
        "evidencias_taxonomia.csv": actions.loc[actions["cnpj_fundo"].isin(category_ledger["cnpj_fundo"])],
    }
    for name, data in outputs.items():
        data.to_csv(output / name, index=False)

    deck_data = {
        "manifest": {
            "latest_complete": latest,
            "periods": periods,
            "stock_scenario": "sem_tapso_petrobras",
            "pfpj_category": PF_PJ_CATEGORY,
        }
    }
    for name in ("saldo_cenarios", "emissoes_por_categoria", "prestadores_separados", "metricas_reconciliacao"):
        deck_data[name] = pd.read_csv(output / f"{name}.csv").fillna("").to_dict("records")
    (output / "revision_payload.json").write_text(
        json.dumps(deck_data, ensure_ascii=False, allow_nan=False)
    )

    files = [
        fund_path, payload_path, action_path, pfpj_path, offer_path,
        anbima_offer_path, vehicle_path,
    ]
    manifest = {
        "schema": "industry_requested_revision.v2",
        "latest_complete": latest,
        "excluded_cnpjs": EXCLUDED_CNPJS,
        "pfpj_excluded_orders": [11, 26],
        "periods": periods,
        "stock_scenario": "sem_tapso_petrobras",
        "issuance_rule": "Taxonomia CNPJ congelada em jun/26; match por fundo e depois classe; não localizado=N/D; FIC fora; 2023 escalado ao total ANBIMA.",
        "source_slide_mapping": {
            "saldo_tipos_emissoes": 4,
            "emissoes_detalhe": 5,
            "metodologia_taxonomia": 6,
            "prestadores": 34,
        },
        "input_root": "data/industry_study",
        "inputs": [
            {"path": str(path.resolve().relative_to(args.data_dir.resolve())), "sha256": digest(path)}
            for path in files
        ],
        "outputs": {
            name: {"rows": len(data), "sha256": digest(output / name)}
            for name, data in outputs.items()
        },
    }
    manifest["outputs"]["revision_payload.json"] = {
        "sha256": digest(output / "revision_payload.json")
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
    )
    print(pd.DataFrame(metrics.items(), columns=["metrica", "valor"]).to_string(index=False))
    print(issuance.loc[issuance["period_key"].eq("jun26")].to_string(index=False))


if __name__ == "__main__":
    main()
