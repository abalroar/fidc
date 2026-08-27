"""Scoped director revision; preserve published taxonomies and source snapshots.

The PF/PJ view is a screening population, not a certified pulverized portfolio.
It must never overwrite the approved classification ledger.
"""
from __future__ import annotations

import pandas as pd

from services.industry_taxonomy_review import apply_taxonomy_review_overlay

EXCLUDED_CNPJS = ("09195235000150", "26287464000114")
STOCK_CATEGORIES = (
    "Fomento Mercantil", "Agro, Indústria e Comércio", "Financeiro",
    "Precatórios / ações", "Multicedente / multisacado", "Recuperação / NP", "N/D",
)


def _boolean(values: pd.Series) -> pd.Series:
    return values.fillna(False).astype(str).str.lower().isin({"true", "1", "sim"})


def stock_category(row: pd.Series) -> str:
    kind, focus = row["anbima_tipo_curado"], row["anbima_foco_curado"]
    if kind in STOCK_CATEGORIES[:3]:
        return kind
    if kind == "Outros":
        return {
            "Poder Público": "Precatórios / ações",
            "Multicarteira Outros": "Multicedente / multisacado",
            "Multicedente/Multissacado": "Multicedente / multisacado",
            "Recuperação": "Recuperação / NP",
        }.get(focus, "N/D")
    return "N/D"


def prepare_funds(funds: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    frame = funds.loc[~_boolean(funds["is_fic_fidc"])].copy()
    if frame.duplicated(["competencia", "cnpj_fundo"]).any():
        raise ValueError("Mais de uma linha por competência/CNPJ")
    frame["pl"] = pd.to_numeric(frame["pl"], errors="raise")
    if frame["pl"].isna().any():
        raise ValueError("PL ausente: não imputar zero")
    frame = apply_taxonomy_review_overlay(frame, actions)
    frame["categoria_slide"] = frame.apply(stock_category, axis=1)
    frame["excluido_cenario"] = frame["cnpj_fundo"].isin(EXCLUDED_CNPJS)
    return frame


def build_stock_scenarios(frame: pd.DataFrame, periods: list[str]) -> pd.DataFrame:
    rows = []
    for period in periods:
        original = frame.loc[frame["competencia"].eq(period)]
        if original.empty:
            raise ValueError(f"Competência ausente: {period}")
        for scenario in ("original", "sem_tapso_petrobras"):
            scoped = original if scenario == "original" else original.loc[~original["excluido_cenario"]]
            denominator = float(scoped["pl"].sum())
            if denominator <= 0:
                raise ValueError("Denominador de PL não positivo")
            for order, category in enumerate(STOCK_CATEGORIES):
                subset = scoped.loc[scoped["categoria_slide"].eq(category)]
                value = float(subset["pl"].sum())
                rows.append(dict(competencia=period, cenario=scenario, categoria=category,
                                 ordem=order, fundos=len(subset), pl_brl=value,
                                 denominador_pl_brl=denominator, share=value / denominator))
    return pd.DataFrame(rows)


def build_credit_screen(frame: pd.DataFrame, latest: str) -> pd.DataFrame:
    """Identify candidates by existing fields, never by the fund's name.

    Consignado, vehicles, real estate and payment arrangements remain separate.
    The functional PJ label is not proof of PJ-only borrowers or diversification.
    """
    out = frame.loc[frame["competencia"].eq(latest)].copy()
    focus = out["anbima_foco_curado"].fillna("")
    n1 = out["taxonomia_funcional_n1_curada"].fillna("")
    n2 = out["taxonomia_funcional_n2_curada"].fillna("")
    financial = out["anbima_tipo_curado"].eq("Financeiro")
    payment = financial & (focus.isin(["Adquirência", "Cartão de crédito"]) | n1.eq("Meios de Pagamento e Cartões"))
    consignado = financial & ~payment & (focus.eq("Crédito Consignado") | n2.isin(["Consignado/INSS", "FGTS"]) | out["segmento_financeiro_principal"].eq("Financeiro: consignado"))
    vehicles = financial & ~payment & ~consignado & (focus.eq("Financiamento de Veículos") | n2.eq("Auto/Veículos"))
    real_estate = financial & ~payment & ~consignado & ~vehicles & (focus.eq("Crédito Imobiliário") | n1.eq("Imobiliário"))
    eligible = financial & ~payment & ~consignado & ~vehicles & ~real_estate
    pf = eligible & (focus.eq("Crédito Pessoal") | n1.eq("Crédito PF"))
    pj = eligible & ~pf & n1.eq("Crédito PJ")
    out["recorte_credito"] = "Demais fundos"
    for mask, label in (
        (financial, "Financeiro sem segregação"),
        (payment, "Meios de pagamento / cartão"),
        (consignado, "Consignado / FGTS"),
        (vehicles, "Veículos"),
        (real_estate, "Imobiliário PF/PJ"),
        (pf, "PF pessoal / estudantil / BNPL (triagem)"),
        (pj, "PJ / PF-PJ (triagem)"),
        (out["categoria_slide"].eq("Fomento Mercantil"), "Fomento Mercantil"),
        (out["categoria_slide"].eq("Multicedente / multisacado"), "Multicedente / multisacado"),
    ):
        out.loc[mask, "recorte_credito"] = label
    out["pulverizacao_validada"] = "N/D — requer concentração por devedor e composição PF/PJ"
    out["denominador_pl_brl"] = float(out["pl"].sum())
    out["share_total"] = out["pl"] / out["denominador_pl_brl"]
    return out


def provider_comparison_group(name: str) -> str:
    """Display grouping from the documented Itaú and Kanastra relationships."""
    text = str(name).casefold()
    if "kanastra" in text or "limine trust" in text:
        return "Kanastra (incl. Limine)"
    if "kinea" in text or "intrag" in text or text in {"itaú", "itau"}:
        return "Itaú"
    return name


def build_provider_comparison(history: pd.DataFrame, latest: str, top_n: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    if top_n < 1:
        raise ValueError("top_n deve ser positivo")
    out = history.copy()
    out["participante_original"] = out["participante"]
    out["participante"] = out["participante"].map(provider_comparison_group)
    keys = ["competencia", "papel"]
    if out.groupby(keys)["denominador_pl_brl"].nunique().gt(1).any():
        raise ValueError("Denominadores de prestadores conflitantes")
    ranking = out.groupby(keys + ["participante"], as_index=False).agg(
        pl_brl=("pl_brl", "sum"), fundos=("fundos", "sum"),
        denominador_pl_brl=("denominador_pl_brl", "first"),
        participantes_origem=("participante_original", lambda x: " | ".join(sorted(set(x)))),
    ).sort_values(keys + ["pl_brl", "participante"], ascending=[True, True, False, True])
    ranking["rank_periodo"] = ranking.groupby(keys).cumcount() + 1
    ranking["share_pl"] = ranking["pl_brl"] / ranking["denominador_pl_brl"]
    ranking["ordem_slide"] = pd.NA
    latest_rows = ranking.loc[ranking["competencia"].eq(latest)]
    for role, scoped in latest_rows.groupby("papel"):
        top = scoped.loc[scoped["participante"].ne("Não informado")].head(top_n)
        # True Top N is preserved. Comparators never replace the Nth provider.
        names = top["participante"].tolist()
        names += [name for name in ("Itaú", "Kanastra (incl. Limine)") if name not in names and name in set(scoped["participante"])]
        for order, name in enumerate(names, 1):
            ranking.loc[ranking["papel"].eq(role) & ranking["participante"].eq(name), "ordem_slide"] = order
    return ranking, out
