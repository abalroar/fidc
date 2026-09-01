"""Scoped director revision for the June 2026 FIDC industry snapshot.

The analytical ledger remains CNPJ-addressable and is kept separate from the
canonical industry taxonomy.  The requested PF/PJ opening is a presentation
classification: the reported amount is the full PL of selected funds, while the
PF/PJ exposure inside those funds and the total number of debtors remain N/D.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from services.industry_taxonomy_review import apply_taxonomy_review_overlay, normalize_cnpj

EXCLUDED_CNPJS = ("09195235000150", "26287464000114")
PF_PJ_CATEGORY = "Multicarteira Pulverizado PF/PJ"
PF_PJ_LEDGER_FILENAME = "director_pfpj_ledger_20260901.csv"
STOCK_CATEGORIES = (
    "Fomento Mercantil",
    "Agro, Indústria e Comércio",
    "Financeiro",
    PF_PJ_CATEGORY,
    "Precatórios / ações",
    "Multicedente / multisacado",
    "Recuperação / NP",
    "N/D",
)
ISSUANCE_PERIODS = (
    {"key": "2023", "label": "2023", "year": 2023, "months": 12, "anbima_scaled": True},
    {"key": "2024", "label": "2024", "year": 2024, "months": 12, "anbima_scaled": False},
    {"key": "2025", "label": "2025", "year": 2025, "months": 12, "anbima_scaled": False},
    {"key": "jun25", "label": "jan–jun/25", "year": 2025, "months": 6, "anbima_scaled": False},
    {"key": "jun26", "label": "jan–jun/26", "year": 2026, "months": 6, "anbima_scaled": False},
)


def _boolean(values: pd.Series) -> pd.Series:
    return values.fillna(False).astype(str).str.lower().isin({"true", "1", "sim"})


def stock_category(row: pd.Series) -> str:
    """Resolve the display category after the approved Type/Focus overlay."""
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


def load_pfpj_ledger(path: str | Path) -> pd.DataFrame:
    ledger = pd.read_csv(path, dtype={"cnpj_fundo": str}, keep_default_na=False)
    required = {
        "ordem", "cnpj_fundo", "nome_exibicao", "pl_brl", "cobertura_mensal",
        "top1_pct_dc_bruto", "produto_documental", "fonte_regulamento",
        "incluir_pfpj", "decisao",
    }
    missing = required - set(ledger.columns)
    if missing:
        raise ValueError(f"Ledger PF/PJ incompleto: {sorted(missing)}")
    ledger["cnpj_fundo"] = ledger["cnpj_fundo"].map(normalize_cnpj)
    if ledger["cnpj_fundo"].duplicated().any():
        raise ValueError("Ledger PF/PJ duplicado por CNPJ")
    ledger["incluir_pfpj"] = _boolean(ledger["incluir_pfpj"])
    ledger["pl_brl"] = pd.to_numeric(ledger["pl_brl"], errors="raise")
    included = ledger.loc[ledger["incluir_pfpj"]]
    if len(ledger) != 26 or len(included) != 24:
        raise ValueError("Ledger PF/PJ deve preservar 26 decisões e 24 inclusões")
    excluded_orders = set(pd.to_numeric(ledger.loc[~ledger["incluir_pfpj"], "ordem"]))
    if excluded_orders != {11, 26}:
        raise ValueError("Exclusões PF/PJ esperadas: fundos 11 e 26")
    return ledger


def prepare_funds(
    funds: pd.DataFrame,
    actions: pd.DataFrame,
    pfpj_ledger: pd.DataFrame | None = None,
) -> pd.DataFrame:
    frame = funds.loc[~_boolean(funds["is_fic_fidc"])].copy()
    if frame.duplicated(["competencia", "cnpj_fundo"]).any():
        raise ValueError("Mais de uma linha por competência/CNPJ")
    frame["cnpj_fundo"] = frame["cnpj_fundo"].astype(str).map(normalize_cnpj)
    frame["pl"] = pd.to_numeric(frame["pl"], errors="raise")
    if frame["pl"].isna().any():
        raise ValueError("PL ausente: não imputar zero")
    frame = apply_taxonomy_review_overlay(frame, actions)
    frame["categoria_slide_origem"] = frame.apply(stock_category, axis=1)
    frame["categoria_slide"] = frame["categoria_slide_origem"]
    frame["pfpj_overlay"] = False
    if pfpj_ledger is not None:
        selected = set(
            pfpj_ledger.loc[pfpj_ledger["incluir_pfpj"], "cnpj_fundo"].astype(str)
        )
        mask = frame["cnpj_fundo"].isin(selected)
        conflicts = frame.loc[mask & frame["categoria_slide_origem"].ne("Financeiro")]
        if len(conflicts):
            sample = conflicts[["competencia", "cnpj_fundo", "categoria_slide_origem"]].head()
            raise ValueError(
                "CNPJ PF/PJ saiu de Financeiro; requer decisão explícita antes do backcast: "
                + sample.to_dict("records").__repr__()
            )
        frame.loc[mask, "categoria_slide"] = PF_PJ_CATEGORY
        frame.loc[mask, "pfpj_overlay"] = True
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
                rows.append(dict(
                    competencia=period,
                    cenario=scenario,
                    categoria=category,
                    ordem=order,
                    fundos=len(subset),
                    pl_brl=value,
                    denominador_pl_brl=denominator,
                    share=value / denominator,
                ))
    return pd.DataFrame(rows)


def build_category_cnpj_ledger(frame: pd.DataFrame, latest: str) -> pd.DataFrame:
    """Freeze the latest CNPJ-to-display-category map used for stock and offers."""
    columns = [
        "cnpj_fundo", "cnpj_classe", "denominacao", "pl", "categoria_slide",
        "categoria_slide_origem", "anbima_tipo_curado", "anbima_foco_curado",
        "taxonomy_review_applied", "pfpj_overlay",
    ]
    out = frame.loc[frame["competencia"].eq(latest), columns].copy()
    if out["cnpj_fundo"].duplicated().any():
        raise ValueError("Mapa de categorias duplicado por CNPJ")
    return out.rename(columns={"pl": "pl_brl"}).sort_values(
        ["categoria_slide", "pl_brl", "cnpj_fundo"], ascending=[True, False, True]
    )


def _classification_lookups(category_ledger: pd.DataFrame) -> tuple[dict[str, str], dict[str, str]]:
    by_fund = category_ledger.set_index("cnpj_fundo")["categoria_slide"].to_dict()
    classes = category_ledger.loc[
        category_ledger["cnpj_classe"].fillna("").astype(str).str.len().eq(14),
        ["cnpj_classe", "categoria_slide"],
    ].copy()
    duplicated = classes.groupby("cnpj_classe")["categoria_slide"].nunique()
    if duplicated.gt(1).any():
        raise ValueError("CNPJ de classe associado a categorias conflitantes")
    by_class = classes.drop_duplicates("cnpj_classe").set_index("cnpj_classe")["categoria_slide"].to_dict()
    return by_fund, by_class


def build_issuance_by_display_category(
    offers: pd.DataFrame,
    category_ledger: pd.DataFrame,
    *,
    anbima_2023_brl: float,
    fic_cnpjs: Iterable[str] = (),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Classify each closed offer by the frozen June-2026 CNPJ ledger.

    A fund-CNPJ match wins, then a class-CNPJ match. Issuers outside the ledger
    are N/D. FICs remain outside the eight displayed sectors. The 2023 observed
    cohort is scaled to the official ANBIMA closed total, preserving its observed
    category mix.
    """
    frame = offers.copy()
    frame["cnpj_n"] = frame["cnpj_emissor"].astype(str).map(normalize_cnpj)
    frame["registered_volume_brl"] = pd.to_numeric(
        frame["registered_volume_brl"], errors="raise"
    )
    closing = pd.to_datetime(frame["data_encerramento"], errors="raise")
    frame["ano"] = closing.dt.year
    frame["mes"] = closing.dt.month
    by_fund, by_class = _classification_lookups(category_ledger)
    frame["categoria"] = frame["cnpj_n"].map(by_fund)
    frame["match_categoria"] = frame["categoria"].notna().map(
        {True: "cnpj_fundo", False: ""}
    )
    missing = frame["categoria"].isna()
    frame.loc[missing, "categoria"] = frame.loc[missing, "cnpj_n"].map(by_class)
    frame.loc[missing & frame["categoria"].notna(), "match_categoria"] = "cnpj_classe"
    frame["categoria"] = frame["categoria"].fillna("N/D")
    frame.loc[frame["match_categoria"].eq(""), "match_categoria"] = "não localizado no ledger jun/26"
    fic_set = {normalize_cnpj(value) for value in fic_cnpjs}
    frame["is_fic"] = frame["cnpj_n"].isin(fic_set)

    rows: list[dict] = []
    lineage: list[pd.DataFrame] = []
    audits: list[dict] = []
    for period in ISSUANCE_PERIODS:
        scoped = frame.loc[
            frame["ano"].eq(period["year"])
            & (frame["mes"].le(period["months"]))
        ].copy()
        observed = float(scoped["registered_volume_brl"].sum())
        if observed <= 0:
            raise ValueError(f"Sem emissões no período {period['label']}")
        scale = anbima_2023_brl / observed if period["anbima_scaled"] else 1.0
        scoped["period_key"] = period["key"]
        scoped["period_label"] = period["label"]
        scoped["scale_factor"] = scale
        scoped["volume_apurado_brl"] = scoped["registered_volume_brl"] * scale
        lineage.append(scoped)
        eligible = scoped.loc[~scoped["is_fic"]]
        grouped = (
            eligible.groupby("categoria")["volume_apurado_brl"]
            .sum()
            .reindex(STOCK_CATEGORIES, fill_value=0.0)
        )
        total = float(grouped.sum())
        for order, (category, volume) in enumerate(grouped.items()):
            rows.append({
                "period_key": period["key"],
                "period_label": period["label"],
                "categoria": category,
                "ordem": order,
                "volume_brl": float(volume),
                "share": float(volume) / total if total else 0.0,
                "denominador_emissoes_brl": total,
            })
        unresolved = eligible["match_categoria"].eq("não localizado no ledger jun/26")
        audits.append({
            "period_key": period["key"],
            "period_label": period["label"],
            "ofertas": len(scoped),
            "emissores": scoped["cnpj_n"].nunique(),
            "observado_brl": observed,
            "scale_factor": scale,
            "fic_excluido_brl": float(scoped.loc[scoped["is_fic"], "volume_apurado_brl"].sum()),
            "denominador_emissoes_brl": total,
            "nao_localizado_brl": float(eligible.loc[unresolved, "volume_apurado_brl"].sum()),
            "nao_localizado_emissores": int(eligible.loc[unresolved, "cnpj_n"].nunique()),
        })
    detail = pd.concat(lineage, ignore_index=True)
    return pd.DataFrame(rows), detail, pd.DataFrame(audits)


def build_credit_screen(frame: pd.DataFrame, latest: str) -> pd.DataFrame:
    """Legacy screen retained for compatibility; it never proves pulverization."""
    out = frame.loc[frame["competencia"].eq(latest)].copy()
    focus = out["anbima_foco_curado"].fillna("")
    n1 = out["taxonomia_funcional_n1_curada"].fillna("")
    n2 = out["taxonomia_funcional_n2_curada"].fillna("")
    origin = out["categoria_slide_origem"] if "categoria_slide_origem" in out else out["categoria_slide"]
    financial = origin.eq("Financeiro")
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
        names = top["participante"].tolist()
        names += [name for name in ("Itaú", "Kanastra (incl. Limine)") if name not in names and name in set(scoped["participante"])]
        for order, name in enumerate(names, 1):
            ranking.loc[ranking["papel"].eq(role) & ranking["participante"].eq(name), "ordem_slide"] = order
    return ranking, out
