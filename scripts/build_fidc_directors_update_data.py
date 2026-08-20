"""Materializa os dados dos slides adicionais solicitados pela diretoria.

Saidas:
- carteira_101_cotistas_senior_202607.csv: uma linha por CNPJ da Carteira 101;
- financeiro_decomposition_202606.csv: abertura mutuamente exclusiva do PL
  ANBIMA Tipo Financeiro;
- fidc_directors_update_data.json: resumo e tabelas para o gerador do PPTX.

A contagem de cotistas seniores soma as contas reportadas por tipo de
investidor na Tabela X.1.1. Ela nao identifica o titular e nao deve ser
interpretada como contagem de pessoas unicas.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


SENIOR_PREFIX = "TAB_X_NR_COTST_SENIOR_"


def _digits(value: Any) -> str:
    text = re.sub(r"\D", "", str(value or ""))
    return text.zfill(14) if text else ""


def _read_cvm_table(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        sep=";",
        encoding="latin1",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )


def _load_month(month_dir: Path, competence: str) -> pd.DataFrame:
    tag = competence.replace("-", "")
    x11 = _read_cvm_table(month_dir / f"inf_mensal_fidc_tab_X_1_1_{tag}.csv")
    tab4 = _read_cvm_table(month_dir / f"inf_mensal_fidc_tab_IV_{tag}.csv")

    x11["cnpj"] = x11["CNPJ_FUNDO_CLASSE"].map(_digits)
    senior_columns = [column for column in x11 if column.startswith(SENIOR_PREFIX)]
    if not senior_columns:
        raise ValueError(f"Tabela X.1.1 sem colunas {SENIOR_PREFIX}*: {month_dir}")
    for column in senior_columns:
        x11[column] = pd.to_numeric(
            x11[column].str.replace(",", ".", regex=False), errors="coerce"
        )
    x11["contas_senior_reportadas"] = x11[senior_columns].sum(axis=1, min_count=1)
    senior = x11.groupby("cnpj", as_index=False).agg(
        contas_senior_reportadas=("contas_senior_reportadas", "sum"),
        linhas_tabela_x_1_1=("cnpj", "size"),
    )

    tab4["cnpj"] = tab4["CNPJ_FUNDO_CLASSE"].map(_digits)
    tab4["pl_publicado_brl"] = pd.to_numeric(
        tab4["TAB_IV_A_VL_PL"].str.replace(",", ".", regex=False), errors="coerce"
    )
    pl = tab4.groupby("cnpj", as_index=False).agg(
        nome_cvm=("DENOM_SOCIAL", "first"),
        pl_publicado_brl=("pl_publicado_brl", "sum"),
        linhas_tabela_iv=("cnpj", "size"),
    )
    merged = pl.merge(senior, on="cnpj", how="outer")
    merged["competencia_cvm"] = competence
    return merged


def build_carteira_101(
    payload_path: Path,
    july_dir: Path,
    june_dir: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    portfolio = pd.DataFrame(payload["portfolio_export_carteira_101"]).copy()
    portfolio["cnpj"] = portfolio["cnpj"].map(_digits)
    if len(portfolio) != 101 or portfolio["cnpj"].nunique() != 101:
        raise ValueError("O payload nao contem 101 CNPJs distintos na Carteira 101")

    july = _load_month(july_dir, "2026-07")
    june = _load_month(june_dir, "2026-06")
    latest = pd.concat(
        [july, june.loc[~june["cnpj"].isin(july["cnpj"])]],
        ignore_index=True,
    )
    out = portfolio.merge(latest, on="cnpj", how="left", validate="one_to_one")
    out["situacao_contas_senior"] = "N/D"
    out.loc[out["contas_senior_reportadas"].eq(0), "situacao_contas_senior"] = (
        "0 contas seniores reportadas"
    )
    out.loc[out["contas_senior_reportadas"].eq(1), "situacao_contas_senior"] = (
        "1 conta senior reportada"
    )
    out.loc[out["contas_senior_reportadas"].gt(1), "situacao_contas_senior"] = (
        "mais de 1 conta senior reportada"
    )
    out["indicio_posicao_exclusiva"] = out["contas_senior_reportadas"].eq(1)
    out["identidade_titular_cvm"] = "nao publicada"
    out["ordem_pl"] = out["pl_publicado_brl"].rank(
        method="first", ascending=False, na_option="bottom"
    )
    out = out.sort_values(
        ["indicio_posicao_exclusiva", "pl_publicado_brl", "nome_referencia"],
        ascending=[False, False, True],
        na_position="last",
    )

    covered = out["pl_publicado_brl"].notna()
    one = out["indicio_posicao_exclusiva"]
    known_portfolio_pl = pd.to_numeric(out["pl_atual_brl"], errors="coerce").sum()
    covered_pl = float(out.loc[covered, "pl_publicado_brl"].sum())
    one_pl = float(out.loc[one, "pl_publicado_brl"].sum())
    summary = {
        "portfolio_funds": int(len(out)),
        "funds_with_cvm_data": int(covered.sum()),
        "fund_coverage": float(covered.mean()),
        "known_portfolio_pl_brl": float(known_portfolio_pl),
        "covered_pl_brl": covered_pl,
        "pl_coverage": float(covered_pl / known_portfolio_pl) if known_portfolio_pl else None,
        "one_senior_account_funds": int(one.sum()),
        "one_senior_account_pl_brl": one_pl,
        "one_senior_account_share_covered_pl": float(one_pl / covered_pl) if covered_pl else None,
        "more_than_one_senior_account_funds": int(
            out["contas_senior_reportadas"].gt(1).sum()
        ),
        "zero_senior_account_funds": int(out["contas_senior_reportadas"].eq(0).sum()),
        "missing_funds": int(out["contas_senior_reportadas"].isna().sum()),
        "primary_competence": "2026-07",
        "fallback_competence": "2026-06",
        "method": (
            "Soma das contas seniores por tipo de investidor na Tabela X.1.1, "
            "por CNPJ de classe/fundo. A CVM nao publica a identidade do titular."
        ),
    }
    return out, summary


def build_financeiro_decomposition(
    fund_base_path: Path,
    acquiring_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    funds = pd.read_csv(
        fund_base_path,
        dtype={"cnpj_fundo": str},
        low_memory=False,
    )
    funds["cnpj_fundo"] = funds["cnpj_fundo"].map(_digits)
    funds = funds[
        funds["competencia"].astype(str).eq("2026-06")
        & ~funds["is_fic_fidc"].fillna(False).astype(bool)
    ].copy()
    funds["tipo_aplicado"] = funds["anbima_tipo_curado"].where(
        funds["anbima_tipo_curado"].fillna("").astype(str).str.strip().ne(""),
        funds["anbima_tipo"],
    )
    funds = funds[funds["tipo_aplicado"].eq("Financeiro")].copy()

    name = funds["denominacao"].fillna("").astype(str).str.upper()
    n1 = funds["taxonomia_funcional_n1_curada"].fillna("").astype(str)
    n2 = funds["taxonomia_funcional_n2_curada"].fillna("").astype(str)
    focus = funds["anbima_foco_curado"].where(
        funds["anbima_foco_curado"].fillna("").astype(str).str.strip().ne(""),
        funds["anbima_foco"],
    ).fillna("").astype(str)
    segment = funds["segmento_financeiro_principal"].fillna("").astype(str)

    payment = n1.eq("Meios de Pagamento e Cartoes") | n1.eq(
        "Meios de Pagamento e Cartões"
    ) | focus.isin(["Adquirência", "Cartão de crédito"])
    fgts = ~payment & (name.str.contains("FGTS", regex=False) | n2.eq("FGTS"))
    private = ~payment & ~fgts & name.str.contains(
        r"CONSIGNAD[^ ]* PRIV|CONSIGNADO PRIV|\bCLT\b|"
        r"CREDITO DO TRABALHADOR|CRÉDITO DO TRABALHADOR|FOLHA PRIVADA",
        regex=True,
    )
    inss = ~payment & ~fgts & ~private & (
        name.str.contains(r"\bINSS\b", regex=True) | n2.eq("Consignado/INSS")
    )
    consignado_nd = ~payment & ~fgts & ~private & ~inss & (
        focus.eq("Crédito Consignado")
        | segment.eq("Financeiro: consignado")
        | name.str.contains("CONSIGNAD", regex=False)
    )
    remainder = ~payment & ~fgts & ~private & ~inss & ~consignado_nd
    other_pf = remainder & (
        n1.eq("Crédito PF")
        | focus.isin(["Crédito Pessoal", "Financiamento de Veículos"])
    )
    corporate = remainder & ~other_pf & n1.eq("Crédito PJ")
    real_estate = remainder & ~other_pf & ~corporate & (
        n1.eq("Imobiliário") | focus.eq("Crédito Imobiliário")
    )

    funds["bucket_financeiro"] = "Outros / multicarteira sem segregacao PF-PJ"
    assignments = [
        (payment, "Meios de pagamento / cartoes"),
        (fgts, "Consignado FGTS"),
        (private, "Consignado privado / CLT"),
        (inss, "Consignado INSS / publico (proxy)"),
        (consignado_nd, "Consignado sem segregacao publica"),
        (other_pf, "Demais credito PF"),
        (corporate, "Credito PJ"),
        (real_estate, "Imobiliario PF/PJ"),
    ]
    for mask, label in assignments:
        funds.loc[mask, "bucket_financeiro"] = label

    order = {
        "Meios de pagamento / cartoes": 1,
        "Consignado INSS / publico (proxy)": 2,
        "Consignado FGTS": 3,
        "Consignado privado / CLT": 4,
        "Consignado sem segregacao publica": 5,
        "Demais credito PF": 6,
        "Credito PJ": 7,
        "Imobiliario PF/PJ": 8,
        "Outros / multicarteira sem segregacao PF-PJ": 9,
    }
    total = float(funds["pl"].sum())
    decomposition = (
        funds.groupby("bucket_financeiro", as_index=False)
        .agg(pl_brl=("pl", "sum"), fundos=("cnpj_fundo", "nunique"))
        .assign(
            share=lambda frame: frame["pl_brl"] / total,
            ordem=lambda frame: frame["bucket_financeiro"].map(order),
        )
        .sort_values("ordem")
    )

    acquiring = pd.read_csv(acquiring_path, dtype={"cnpj_fundo": str})
    acquiring["cnpj_fundo"] = acquiring["cnpj_fundo"].map(_digits)
    acquiring = acquiring[["cnpj_fundo", "Fundo", "Regulamento primário"]].drop_duplicates(
        "cnpj_fundo"
    )
    acquiring_ledger = acquiring.merge(
        funds[
            [
                "cnpj_fundo",
                "denominacao",
                "pl",
                "tipo_aplicado",
                "anbima_tipo_oficial",
                "anbima_foco_oficial",
                "anbima_tipo_curado",
                "anbima_foco_curado",
            ]
        ],
        on="cnpj_fundo",
        how="left",
    )
    acquiring_inside = float(acquiring_ledger["pl"].sum())
    tapso = funds.loc[funds["cnpj_fundo"].eq("26287464000114")]
    tapso_pl = float(tapso["pl"].sum())
    summary = {
        "competence": "2026-06",
        "financeiro_pl_brl": total,
        "financeiro_funds": int(funds["cnpj_fundo"].nunique()),
        "payment_chain_pl_brl": float(funds.loc[payment, "pl"].sum()),
        "consignado_total_pl_brl": float(
            funds.loc[fgts | private | inss | consignado_nd, "pl"].sum()
        ),
        "consignado_unsegmented_pl_brl": float(funds.loc[consignado_nd, "pl"].sum()),
        "document_curated_acquiring_inside_financeiro_pl_brl": acquiring_inside,
        "tapso_inside_financeiro": not tapso.empty,
        "tapso_pl_brl": tapso_pl,
        "tapso_type_applied": (
            str(tapso.iloc[0]["tipo_aplicado"]) if not tapso.empty else "N/D"
        ),
        "method": (
            "Prioridade mutuamente exclusiva: meios de pagamento; FGTS; privado/CLT; "
            "INSS/publico; consignado nao segregado; demais PF; PJ; imobiliario; "
            "multicarteira/N/D. Nome e taxonomia funcional sao proxies; o bucket "
            "nao segregado preserva lacunas em vez de forcar classificacao."
        ),
    }
    return funds, decomposition, acquiring_ledger, summary


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--july-dir", type=Path, required=True)
    parser.add_argument("--june-dir", type=Path, required=True)
    parser.add_argument("--fund-base", type=Path, required=True)
    parser.add_argument("--acquiring", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    carteira, carteira_summary = build_carteira_101(
        args.payload, args.july_dir, args.june_dir
    )
    finance_funds, decomposition, acquiring_ledger, finance_summary = (
        build_financeiro_decomposition(args.fund_base, args.acquiring)
    )

    carteira.to_csv(
        args.output_dir / "carteira_101_cotistas_senior_202607.csv", index=False
    )
    decomposition.to_csv(
        args.output_dir / "financeiro_decomposition_202606.csv", index=False
    )
    finance_funds.to_csv(
        args.output_dir / "financeiro_decomposition_fund_ledger_202606.csv", index=False
    )
    acquiring_ledger.to_csv(
        args.output_dir / "financeiro_acquiring_document_ledger_202606.csv", index=False
    )

    result = {
        "carteira_101": {
            "summary": carteira_summary,
            "one_senior_account_funds": _records(
                carteira.loc[carteira["indicio_posicao_exclusiva"]]
                .sort_values("pl_publicado_brl", ascending=False)
                [[
                    "cnpj",
                    "nome_referencia",
                    "nome_cvm",
                    "competencia_cvm",
                    "pl_publicado_brl",
                    "contas_senior_reportadas",
                ]]
            ),
        },
        "financeiro": {
            "summary": finance_summary,
            "decomposition": _records(decomposition),
        },
    }
    (args.output_dir / "fidc_directors_update_data.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
