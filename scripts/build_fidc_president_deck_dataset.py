#!/usr/bin/env python3
"""Build the publication-grade dataset used by the FIDC president deck.

The script deliberately keeps census-like CVM evidence separate from targeted
document curation.  It is designed to be rerun after the monthly Industry
pipeline refreshes ``industry_fund_snapshot.csv.gz``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


ANBIMA_MACRO_MAP = {
    "Financeiro": "Financeiro",
    "Imobiliario": "Financeiro",
    "Factoring": "Fomento Mercantil",
    "Comercial": "Agro, Indústria e Comércio",
    "Industrial": "Agro, Indústria e Comércio",
    "Cartao de credito": "Agro, Indústria e Comércio",
    "Servicos": "Agro, Indústria e Comércio",
    "Agronegocio": "Agro, Indústria e Comércio",
    "Setor publico": "Outros",
    "Acoes judiciais": "Outros",
}

ANBIMA_CLASS_ORDER = [
    "Financeiro",
    "Agro, Indústria e Comércio",
    "Outros",
    "Fomento Mercantil",
    "Sem evidência suficiente",
]

ANBIMA_CLASS_DEFINITIONS = [
    {
        "classe": "Fomento Mercantil",
        "explicacao": (
            "Carteira pulverizada de recebíveis cedidos por diversos originadores "
            "para antecipação de recursos, incluindo duplicatas, notas, cheques e factoring."
        ),
        "focos": "Fomento mercantil / factoring",
    },
    {
        "classe": "Financeiro",
        "explicacao": (
            "Recebíveis originados em crédito imobiliário, consignado, pessoal, "
            "financiamento de veículos ou combinação dessas carteiras."
        ),
        "focos": "Imobiliário | consignado | pessoal | veículos | multicarteira",
    },
    {
        "classe": "Agro, Indústria e Comércio",
        "explicacao": (
            "Crédito do setor real: infraestrutura, recebíveis comerciais, crédito "
            "corporativo, agronegócio ou combinação desses focos."
        ),
        "focos": "Infra | comerciais | corporativo | agro | multicarteira",
    },
    {
        "classe": "Outros",
        "explicacao": (
            "Recuperação de créditos vencidos, poder público e carteiras com dois "
            "ou mais tipos que não se concentram nas classes anteriores."
        ),
        "focos": "NPL/recuperação | poder público | multicarteira outros",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/industry_study"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/fidc_presidente_bba_20260711"),
    )
    parser.add_argument("--start-year", type=int, default=2020)
    return parser.parse_args()


def read_csv(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, **kwargs)


def as_records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def role_current_rows(role_delta: pd.DataFrame, role: str) -> pd.DataFrame:
    rows = role_delta.loc[role_delta["role"].eq(role)].copy()
    return rows.sort_values(["share_current", "pl_brl_current"], ascending=False)


def build() -> None:
    args = parse_args()
    data_dir = args.data_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    vehicle = read_csv(data_dir / "vehicle_monthly.csv.gz", low_memory=False)
    snapshot = read_csv(data_dir / "industry_fund_snapshot.csv.gz", low_memory=False)
    industry_monthly = read_csv(data_dir / "industry_monthly.csv")
    role_delta = read_csv(data_dir / "role_market_share_delta.csv")
    offer_delta = read_csv(data_dir / "offer_role_share_delta.csv")
    funnel = read_csv(data_dir / "document_universe_funnel.csv")
    cotista_types = read_csv(data_dir / "cotistas_tipo_monthly.csv")

    snapshot_months = sorted(snapshot["competencia"].dropna().astype(str).unique())
    if not snapshot_months:
        raise ValueError("industry_fund_snapshot has no competence")
    current_month = snapshot_months[-1]
    current_year = int(current_month[:4])
    previous_month = f"{current_year - 1}-{current_month[5:7]}"

    monthly_index = industry_monthly.set_index("competencia")
    for required_month in (current_month, previous_month):
        if required_month not in monthly_index.index:
            raise ValueError(f"missing complete monthly aggregate: {required_month}")

    annual_months = [
        f"{year}-12" for year in range(args.start_year, current_year) if f"{year}-12" in set(vehicle["competencia"])
    ]
    annual_months.append(current_month)

    annual_rows: list[dict] = []
    mix_rows: list[dict] = []
    for competence in annual_months:
        rows = vehicle.loc[
            vehicle["competencia"].eq(competence)
            & ~vehicle["is_fic_fidc"].fillna(False)
            & vehicle["pl"].gt(0)
        ].copy()
        if rows.empty:
            continue
        rows["anbima_macro"] = rows["segmento_principal"].map(ANBIMA_MACRO_MAP)
        rows["anbima_macro"] = rows["anbima_macro"].fillna("Sem evidência suficiente")
        total_pl = float(rows["pl"].sum())
        grouped = rows.groupby("anbima_macro", dropna=False)["pl"].sum()
        unclassified_pl = float(grouped.get("Sem evidência suficiente", 0.0))
        annual_rows.append(
            {
                "competencia": competence,
                "rotulo": competence[:4] if competence.endswith("-12") else f"{competence[:4]} YTD",
                "pl_ex_fic_brl": total_pl,
                "pl_ex_fic_bi": total_pl / 1e9,
                "veiculos": int(len(rows)),
                "pl_classificado_share": 1 - unclassified_pl / total_pl,
            }
        )
        for category in ANBIMA_CLASS_ORDER:
            pl_brl = float(grouped.get(category, 0.0))
            mix_rows.append(
                {
                    "competencia": competence,
                    "rotulo": competence[:4] if competence.endswith("-12") else f"{competence[:4]} YTD",
                    "classe_anbima_macro": category,
                    "pl_brl": pl_brl,
                    "share": pl_brl / total_pl,
                    "share_pct": 100 * pl_brl / total_pl,
                    "metodologia": (
                        "macroclasse ANBIMA inferida do segmento dominante de direitos "
                        "creditórios no informe mensal CVM; FIC-FIDC e PL<=0 excluídos"
                    ),
                }
            )

    annual = pd.DataFrame(annual_rows)
    anbima_mix = pd.DataFrame(mix_rows)
    annual.to_csv(output_dir / "pl_ex_fic_yearly.csv", index=False)
    anbima_mix.to_csv(output_dir / "anbima_macro_mix_yearly.csv", index=False)
    pd.DataFrame(ANBIMA_CLASS_DEFINITIONS).to_csv(
        output_dir / "anbima_class_definitions.csv", index=False
    )

    current_snapshot = snapshot.loc[
        snapshot["competencia"].astype(str).eq(current_month)
        & ~snapshot["is_fic_fidc"].fillna(False)
        & snapshot["pl"].gt(0)
    ].copy()
    current_snapshot["cotistas"] = pd.to_numeric(current_snapshot["cotistas"], errors="coerce").fillna(0)
    bucket_specs = [
        ("1", current_snapshot["cotistas"].eq(1)),
        ("2", current_snapshot["cotistas"].eq(2)),
        ("3 a 5", current_snapshot["cotistas"].between(3, 5)),
        ("6 a 10", current_snapshot["cotistas"].between(6, 10)),
        ("11 a 50", current_snapshot["cotistas"].between(11, 50)),
        ("> 50", current_snapshot["cotistas"].gt(50)),
        ("Sem cotista positivo", current_snapshot["cotistas"].le(0)),
    ]
    histogram_rows = []
    for label, mask in bucket_specs:
        histogram_rows.append(
            {
                "bucket": label,
                "fundos": int(mask.sum()),
                "fund_share": float(mask.mean()),
                "pl_brl": float(current_snapshot.loc[mask, "pl"].sum()),
                "pl_share": float(current_snapshot.loc[mask, "pl"].sum() / current_snapshot["pl"].sum()),
            }
        )
    cotista_histogram = pd.DataFrame(histogram_rows)
    cotista_histogram.to_csv(output_dir / "cotista_histogram_full_universe.csv", index=False)

    current_accounts = cotista_types.loc[cotista_types["competencia"].eq(current_month)].copy()
    current_accounts["share_accounts"] = current_accounts["n_cotistas"] / current_accounts["n_cotistas"].sum()
    current_accounts["publication_status"] = "supporting_only_not_unique_investors_no_value_split"
    current_accounts.to_csv(output_dir / "cotista_account_types_supporting_only.csv", index=False)

    for role in ("administrador", "gestor", "custodiante"):
        role_current_rows(role_delta, role).to_csv(
            output_dir / f"{role}_current_share.csv", index=False
        )

    admin_delta = role_current_rows(role_delta, "administrador")
    admin_delta.to_csv(output_dir / "administrador_share_delta.csv", index=False)
    offer_admin = offer_delta.loc[offer_delta["role"].eq("administrador")].copy()
    offer_admin = offer_admin.sort_values("volume_share_current", ascending=False)
    offer_admin.to_csv(output_dir / "administrador_primary_offer_share.csv", index=False)
    funnel.to_csv(output_dir / "document_evidence_funnel.csv", index=False)

    def participant_row(frame: pd.DataFrame, name: str) -> pd.Series:
        match = frame.loc[frame["participant"].eq(name)]
        if match.empty:
            raise ValueError(f"participant not found: {name}")
        return match.iloc[0]

    admin_itau = participant_row(admin_delta, "ITAU/INTRAG")
    offer_itau = participant_row(offer_admin, "ITAU/INTRAG")
    offer_qi = participant_row(offer_admin, "QI TECH + SINGULARE")
    offer_btg = participant_row(offer_admin, "BTG PACTUAL")
    offer_oliveira = participant_row(offer_admin, "OLIVEIRA TRUST")

    gross_pl = float(monthly_index.loc[current_month, "pl_total"])
    ex_fic_pl = float(
        monthly_index.loc[current_month, "pl_total"]
        - monthly_index.loc[current_month, "pl_fic_fidc"]
    )
    cotistas_positive = current_snapshot["cotistas"].gt(0)
    up_to_five = current_snapshot["cotistas"].between(1, 5)
    current_mix = anbima_mix.loc[anbima_mix["competencia"].eq(current_month)]
    unclassified_share = float(
        current_mix.loc[
            current_mix["classe_anbima_macro"].eq("Sem evidência suficiente"), "share"
        ].iloc[0]
    )

    metrics = {
        "current_month": current_month,
        "previous_month": previous_month,
        "gross_pl_brl": gross_pl,
        "gross_pl_bi": gross_pl / 1e9,
        "ex_fic_pl_brl": ex_fic_pl,
        "ex_fic_pl_bi": ex_fic_pl / 1e9,
        "current_universe_funds": int(
            funnel.loc[funnel["stage"].eq("current_cvm_universe"), "current_funds_matched"].iloc[0]
        ),
        "classification_share": 1 - unclassified_share,
        "itau_admin_share": float(admin_itau["share_current"]),
        "itau_admin_delta_pp": float(admin_itau["delta_share_pp"]),
        "itau_admin_rank": int(admin_itau["rank_current"]),
        "itau_admin_previous_rank": int(admin_itau["rank_previous"]),
        "itau_admin_pl_brl": float(admin_itau["pl_brl_current"]),
        "itau_admin_pl_gap_to_5pct_brl": 0.05 * gross_pl - float(admin_itau["pl_brl_current"]),
        "itau_offer_share": float(offer_itau["volume_share_current"]),
        "itau_offer_delta_pp": float(offer_itau["delta_volume_share_pp"]),
        "qi_offer_share": float(offer_qi["volume_share_current"]),
        "qi_offer_count": int(offer_qi["offers_current"]),
        "btg_offer_share": float(offer_btg["volume_share_current"]),
        "btg_offer_delta_pp": float(offer_btg["delta_volume_share_pp"]),
        "oliveira_offer_share": float(offer_oliveira["volume_share_current"]),
        "cotista_funds": int(len(current_snapshot)),
        "cotista_positive_funds": int(cotistas_positive.sum()),
        "cotista_positive_pl_share": float(
            current_snapshot.loc[cotistas_positive, "pl"].sum() / current_snapshot["pl"].sum()
        ),
        "cotistas_median": float(current_snapshot.loc[cotistas_positive, "cotistas"].median()),
        "funds_up_to_five_share": float(up_to_five.mean()),
        "pl_up_to_five_share": float(
            current_snapshot.loc[up_to_five, "pl"].sum() / current_snapshot["pl"].sum()
        ),
    }

    publication_gate = pd.DataFrame(
        [
            {
                "tema": "PL e composição por macroclasse ANBIMA",
                "cobertura": f"100% do PL ex-FIC; {metrics['classification_share']:.1%} classificável",
                "decisao": "PUBLICAR",
                "regra": "faixa sem evidência permanece explícita",
            },
            {
                "tema": "Administração: share e delta",
                "cobertura": "100% do PL; papel observado no informe mensal",
                "decisao": "PUBLICAR",
                "regra": "janela comparável de 12 meses",
            },
            {
                "tema": "Gestão e custódia",
                "cobertura": "foto atual integral; histórico datado insuficiente",
                "decisao": "PUBLICAR FOTO",
                "regra": "deltas históricos excluídos",
            },
            {
                "tema": "Ofertas primárias",
                "cobertura": "distribuições CVM registradas; janela e estágio explícitos",
                "decisao": "PUBLICAR",
                "regra": "secundárias excluídas",
            },
            {
                "tema": "Quantidade de cotistas",
                "cobertura": "100% dos fundos ex-FIC; 99,9% do PL com valor positivo",
                "decisao": "PUBLICAR HISTOGRAMA",
                "regra": "contas por classe/série, não CPF/CNPJ único",
            },
            {
                "tema": "Investidores nominais, cedentes, sacados e secundário",
                "cobertura": "sem censo documental, beneficiário final ou negócio a negócio",
                "decisao": "EXCLUIR",
                "regra": "nenhum ranking ou turnover no material executivo",
            },
        ]
    )
    publication_gate.to_csv(output_dir / "publication_gate.csv", index=False)

    source_ledger = pd.DataFrame(
        [
            {
                "tema": "PL, segmentos, administradores e cotistas",
                "fonte": "CVM - Informe Mensal de FIDC",
                "url": "https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal",
                "arquivo_local": "vehicle_monthly.csv.gz | industry_monthly.csv | industry_fund_snapshot.csv.gz",
                "uso": "universo mensal, PL, recebível dominante, administração e número de cotistas",
            },
            {
                "tema": "Ofertas primárias",
                "fonte": "CVM - Ofertas Públicas de Distribuição",
                "url": "https://dados.cvm.gov.br/dataset/oferta-distrib",
                "arquivo_local": "offer_role_share_delta.csv",
                "uso": "volume, quantidade e participação por prestador em janelas comparáveis",
            },
            {
                "tema": "Classes de FIDC",
                "fonte": "ANBIMA - Diretriz de Classificação do FIDC nº 09",
                "url": "https://www.anbima.com.br/data/files/85/40/8F/2D/79E386106416A38678A80AC2/Diretrizes_e_deliberacoes_do_Codigo_de_Administracao_de_Recursos_de_terceiros.pdf",
                "arquivo_local": "anbima_class_definitions.csv",
                "uso": "denominações e focos oficiais; macro-mapeamento analítico dos informes CVM",
            },
            {
                "tema": "Cobertura documental",
                "fonte": "Documentos públicos CVM/Fundos.NET curados localmente",
                "url": "https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM",
                "arquivo_local": "document_universe_funnel.csv",
                "uso": "medir cobertura e impedir publicação de rankings não censitários",
            },
            {
                "tema": "Referência de conteúdo",
                "fonte": "Industria_FIDC_2026053.pptx - Clodo Couto",
                "url": "local",
                "arquivo_local": "/Users/matheusjprates/Downloads/Industria_FIDC_2026053.pptx",
                "uso": "taxonomia, ideia do gráfico 100% empilhado e encadeamento; números reprocessados",
            },
        ]
    )
    source_ledger.to_csv(output_dir / "source_ledger.csv", index=False)

    clodo_log = pd.DataFrame(
        [
            {
                "item": "Quatro denominações ANBIMA",
                "slide_clodo": 5,
                "tratamento": "ADOTADO E VERIFICADO",
                "motivo": "terminologia confirmada na Diretriz ANBIMA nº 09",
            },
            {
                "item": "Gráfico 100% empilhado por ano",
                "slide_clodo": 4,
                "tratamento": "ADOTADO COM REPROCESSAMENTO",
                "motivo": "universo CVM ex-FIC integral; quatro macroclasses e faixa sem evidência",
            },
            {
                "item": "Série histórica de PL",
                "slide_clodo": 3,
                "tratamento": "RECALCULADO",
                "motivo": "o valor de 2023 do deck de referência não reproduz o universo CVM ex-FIC atual",
            },
            {
                "item": "Histograma de fundos acima de R$ 200 milhões",
                "slide_clodo": 15,
                "tratamento": "SUBSTITUÍDO",
                "motivo": "histograma agora cobre todo o universo ex-FIC, sem corte por PL",
            },
            {
                "item": "Mix de investidores de junho de 2026",
                "slide_clodo": 16,
                "tratamento": "EXCLUÍDO",
                "motivo": "competência parcial e contas não equivalem a investidores únicos ou valor investido",
            },
            {
                "item": "Deltas históricos de gestores e custodiantes",
                "slide_clodo": "7 e 9",
                "tratamento": "EXCLUÍDO",
                "motivo": "histórico datado cobre cerca de 31% do PL; somente a foto atual é publicada",
            },
            {
                "item": "Cedentes e sacados nominais",
                "slide_clodo": 14,
                "tratamento": "EXCLUÍDO",
                "motivo": "curadoria direcionada não permite ranking representativo da indústria",
            },
        ]
    )
    clodo_log.to_csv(output_dir / "clodo_content_adoption_log.csv", index=False)

    content = {
        "metrics": metrics,
        "annual_pl": as_records(annual),
        "anbima_mix": as_records(anbima_mix),
        "anbima_definitions": ANBIMA_CLASS_DEFINITIONS,
        "cotista_histogram": as_records(cotista_histogram),
        "administrator_current": as_records(admin_delta.head(12)),
        "manager_current": as_records(role_current_rows(role_delta, "gestor").head(12)),
        "custodian_current": as_records(role_current_rows(role_delta, "custodiante").head(12)),
        "administrator_offers": as_records(offer_admin.head(15)),
        "document_funnel": as_records(funnel),
        "publication_gate": as_records(publication_gate),
        "sources": as_records(source_ledger),
    }
    (output_dir / "deck_content.json").write_text(
        json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "current_month": current_month,
                "gross_pl_bi": round(metrics["gross_pl_bi"], 1),
                "ex_fic_pl_bi": round(metrics["ex_fic_pl_bi"], 1),
                "classification_share": round(metrics["classification_share"], 4),
                "cotista_funds": metrics["cotista_funds"],
                "funds_up_to_five_share": round(metrics["funds_up_to_five_share"], 4),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    build()
