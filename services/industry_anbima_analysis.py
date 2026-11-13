"""Current ANBIMA/IBBA analysis with separate ranking and annex perimeters."""
from __future__ import annotations

import json
from pathlib import Path
import re

import pandas as pd

SCOPES = {
    "1": "Renda fixa", "1.3": "Securitização", "1.3.1": "FIDC",
    "2": "Híbridos", "3": "Empresas ligadas",
}
MEASURES = {"originacao_valor": "Originação", "distribuicao_valor": "Distribuição"}
WINDOWS = {"acumulado_ano": "Acumulado no ano", "ultimos_12_meses": "Últimos 12 meses"}
HYBRIDS_DEFINITION = (
    "Híbridos (Tipo 2, ANBIMA): títulos conversíveis ou permutáveis em ações, "
    "FII, CEPAC, FIP-IE e FIAGRO. FIDC, CRI, CRA e CR integram renda fixa "
    "(Tipo 1), dentro de securitização."
)
SYNTHESIS_PRODUCTS = (
    ("1", "Renda fixa consolidada"), ("1.3.1", "FIDC"),
    ("1.3.2", "CRI"), ("1.3.3", "CRA"), ("1.3.4", "CR"),
    ("2.2", "FII"), ("2.4", "FIP-IE"), ("2.5", "FIAGRO"),
)


def _build_synthesis(official: pd.DataFrame, totals: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Published origination counts and volumes, with no annex-grain proxy."""
    keys = ["measure", "window", "ranking_code"]
    if totals.duplicated(keys).any():
        raise ValueError("Totais ANBIMA duplicados no mesmo recorte")
    totals_by_key = totals.set_index(keys)["total"]
    names = official.participant.str.replace(r"\*+$", "", regex=True).str.strip()
    rows = []
    for code, label in SYNTHESIS_PRODUCTS:
        row = {"ranking_code": code, "product": label,
               "family": "Renda fixa" if code.startswith("1") else "Híbridos"}
        for window, suffix in [("acumulado_ano", "ytd"), ("ultimos_12_meses", "ltm")]:
            for measure, field in [("originacao_numero_operacoes", "operations"), ("originacao_valor", "market_volume_brl")]:
                key = (measure, window, code)
                if key not in totals_by_key or pd.isna(totals_by_key[key]):
                    raise ValueError(f"Total publicado ANBIMA ausente: {key}")
                row[f"{field}_{suffix}"] = float(totals_by_key[key])
            ibba = official[official.measure.eq("originacao_valor") & official.window.eq(window)
                            & official.ranking_code.eq(code) & names.eq("ITAU BBA") & official["rank"].notna()]
            for source, field in [("rank", "rank"), ("share", "share"), ("value_brl_or_count", "volume_brl")]:
                row[f"ibba_{field}_{suffix}"] = None if ibba.empty else float(ibba.iloc[0][source])
        rows.append(row)
    counts = official[official.measure.eq("originacao_numero_operacoes")
                      & official.window.eq("acumulado_ano") & official.ranking_code.eq("1.3.1")].copy()
    values = official[official.measure.eq("originacao_valor") & official.window.eq("acumulado_ano")
                      & official.ranking_code.eq("1.3.1") & official["rank"].notna()].copy()
    for frame in [counts, values]:
        frame["participant_source"] = frame.participant
        frame["participant"] = frame.participant.str.replace(r"\*+$", "", regex=True).str.strip()
    competitors = values[["rank", "participant", "participant_source", "value_brl_or_count", "share"]].rename(columns={"value_brl_or_count": "volume_brl"}).merge(
        counts[["participant", "value_brl_or_count"]].rename(columns={"value_brl_or_count": "operations"}),
        on="participant", how="left", validate="one_to_one")
    # Preserve ANBIMA's published rank even when a rectification leaves a
    # neighboring volume out of order; do not invent a replacement ranking.
    competitors = competitors.sort_values(["rank", "participant"], kind="stable")
    competitors["market_operations"] = float(totals_by_key[("originacao_numero_operacoes", "acumulado_ano", "1.3.1")])
    competitors["market_volume_brl"] = float(totals_by_key[("originacao_valor", "acumulado_ano", "1.3.1")])
    return pd.DataFrame(rows), competitors


def build_anbima_analysis(data_dir: Path) -> dict[str, object]:
    from services.industry_issuance_taxonomy import _load_taxonomy_photo, _resolve_issuers, _truthy

    data_dir = Path(data_dir)
    manifest = json.loads((data_dir / "anbima_rf_ranking_manifest.json").read_text())
    official = pd.read_csv(data_dir / "anbima_rf_ranking_official.csv", dtype={"ranking_code": str})
    totals = pd.read_csv(data_dir / "anbima_rf_ranking_totals.csv", dtype={"ranking_code": str})
    synthesis_products, synthesis_competitors = _build_synthesis(official, totals)
    all_ranking = official[
        official["window"].isin(WINDOWS) & official["measure"].isin(MEASURES)
        & official["rank"].notna()
    ].copy()
    all_ranking["participant_source"] = all_ranking["participant"]
    all_ranking["participant"] = all_ranking["participant"].str.replace(r"\*+$", "", regex=True).str.strip()
    all_ranking["scope"] = all_ranking["ranking_code"].map(SCOPES).fillna(all_ranking["ranking_label"])
    all_ranking["role"] = all_ranking["measure"].map(MEASURES)
    all_ranking["window_label"] = all_ranking["window"].map(WINDOWS)
    all_ranking = all_ranking.rename(columns={"value_brl_or_count": "volume_brl"})
    if all_ranking.duplicated(["ranking_code", "measure", "window", "participant"]).any():
        raise ValueError("Ranking ANBIMA tem participantes duplicados no mesmo recorte")
    ranking = all_ranking[all_ranking.window.eq("acumulado_ano") & all_ranking.ranking_code.isin(SCOPES)].copy()
    positions = []
    scope_labels = dict(official[["ranking_code", "ranking_label"]].drop_duplicates().itertuples(index=False, name=None))
    scope_labels.update(SCOPES)
    for window, window_label in WINDOWS.items():
        for code, scope in scope_labels.items():
            for measure, role in MEASURES.items():
                subset = all_ranking[all_ranking.window.eq(window) & all_ranking.ranking_code.eq(code) & all_ranking.measure.eq(measure)]
                ibba = subset[subset.participant.eq("ITAU BBA")]
                positions.append({
                    "scope": scope, "ranking_code": code, "role": role,
                    "window": window, "window_label": window_label,
                    "rank": None if ibba.empty else int(ibba.iloc[0]["rank"]),
                    "volume_brl": None if ibba.empty else float(ibba.iloc[0]["volume_brl"]),
                    "share": None if ibba.empty else float(ibba.iloc[0]["share"]),
                    "universe_volume_brl": None if subset.empty else float(subset.volume_brl.sum()),
                    "status": "sem ranking publicado" if subset.empty else "IBBA não listado" if ibba.empty else "publicado",
                })

    annex = pd.read_csv(data_dir / "anbima_rf_ranking_annex.csv.gz", dtype={"cnpj_emissor": str, "block_code": str}, keep_default_na=False)
    # Origination and distribution credit are different measures. Type 3 is
    # kept separate from Types 1/2. Never add coordinator rows twice by role.
    origin = annex[annex.role.eq("originacao") & annex.block_code.isin(["1", "2"])].copy()
    products = origin.groupby(["block_name", "classe", "classe_label"], as_index=False).agg(
        volume_brl=("valor_brl", "sum"), registrations=("registro_cvm", "nunique"),
    )
    products["share"] = products.volume_brl / products.volume_brl.sum()
    fidc = origin[origin.classe.eq("1.3.1") & origin.block_code.eq("1")].copy()
    if fidc.empty or fidc.valor_brl.sum() <= 0:
        raise ValueError("Anexo ANBIMA sem originação de FIDC")
    fidc["deal_key"] = fidc.registro_cvm.where(fidc.registro_cvm.ne(""), "sem-registro:" + fidc.operation_key)
    def unique_cnpj(values):
        found = {str(value) for value in values if re.fullmatch(r"\d{14}", str(value))}
        return next(iter(found)) if len(found) == 1 else ""

    # The market-wide table follows ANBIMA's issuer/closing-date operation
    # grain, retaining every registration. Missing CNPJ uses issuer name so
    # unrelated foreign issuers closed on the same day do not collapse.
    origin["operation_id"] = origin.operation_key.where(
        origin.cnpj_emissor.str.fullmatch(r"\d{14}"),
        "emissor:" + origin.emissor.str.strip() + ":" + origin.data_encerramento,
    )
    operations = origin.groupby("operation_id", as_index=False).agg(
        cnpj_emissor=("cnpj_emissor", unique_cnpj),
        emissor=("emissor", lambda values: max(values, key=len)),
        data_encerramento=("data_encerramento", "max"),
        registros_cvm=("registro_cvm", lambda values: "; ".join(sorted(set(values)))),
        products=("classe_label", lambda values: "; ".join(sorted(set(values)))),
        volume_brl=("valor_brl", "sum"),
        participants=("participante", lambda values: "; ".join(sorted(set(values)))),
    )
    market_ibba = origin[origin.participante.eq("ITAU BBA")].groupby("operation_id").valor_brl.sum()
    operations["ibba_volume_brl"] = operations.operation_id.map(market_ibba).fillna(0)
    operations["ibba_participant"] = operations.operation_id.isin(market_ibba.index)
    market_top15 = operations.sort_values(["volume_brl", "operation_id"], ascending=[False, True]).head(15).copy()
    market_top15.insert(0, "rank", range(1, len(market_top15) + 1))

    deals = fidc.groupby("deal_key", as_index=False, dropna=False).agg(
        registro_cvm=("registro_cvm", "first"), cnpj_emissor=("cnpj_emissor", unique_cnpj),
        emissor=("emissor", lambda values: max(values, key=len)),
        data_encerramento=("data_encerramento", "max"),
        closing_dates=("data_encerramento", lambda values: "; ".join(sorted(set(values)))),
        volume_brl=("valor_brl", "sum"),
        participants=("participante", lambda values: "; ".join(sorted(set(values)))),
        regimes=("regime_colocacao", lambda values: "; ".join(sorted(set(values)))),
    )
    ibba_volume = fidc[fidc.participante.eq("ITAU BBA")].groupby("deal_key").valor_brl.sum()
    deals["ibba_volume_brl"] = deals.deal_key.map(ibba_volume).fillna(0)
    deals["ibba_participant"] = deals.deal_key.isin(ibba_volume.index)
    deals["cnpj_n"] = deals.cnpj_emissor.fillna("")
    photo = _load_taxonomy_photo(data_dir)
    deals = _resolve_issuers(deals, photo, data_dir)
    known = deals["anbima_tipo_curado"].fillna("").astype(str)
    deals["category"] = known.where(known.isin(["Financeiro", "Agro, Indústria e Comércio", "Fomento Mercantil", "Outros"]), "N/D")
    deals.loc[_truthy(deals.is_fic_fidc), "category"] = "FIC-FIDC"
    sectors = deals.groupby("category", as_index=False).agg(volume_brl=("volume_brl", "sum"), registrations=("deal_key", "nunique"))
    total = float(deals.volume_brl.sum())
    sectors["share"] = sectors.volume_brl / total
    if abs(float(sectors.volume_brl.sum()) - float(fidc.valor_brl.sum())) > 0.02:
        raise ValueError("Setores ANBIMA não reconciliam com o anexo")
    top15 = deals.sort_values(["volume_brl", "deal_key"], ascending=[False, True]).head(15).copy()
    top15.insert(0, "rank", range(1, len(top15) + 1))
    matched = deals[deals["match"].ne("")]
    meta = manifest["comparison_meta"]
    ltm_start = (pd.Timestamp(meta["current_period_end"]).replace(day=1) - pd.DateOffset(months=11)).date().isoformat()
    month_labels = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
    def short_date(value):
        return f"{month_labels[int(value[5:7])-1]}/{value[2:4]}"
    notes = [
        HYBRIDS_DEFINITION,
        "Síntese de originação: operações e mercado vêm da linha Total do ranking publicado. Contagens por coordenador não são aditivas; cada casa recebe uma unidade por operação em que tenha crédito. O anexo possui registros CVM e contagem reconstruída por emissor/data, unidades distintas do total oficial de operações.",
        "As posições dos competidores são preservadas como publicadas pela ANBIMA, inclusive quando os volumes retificados de duas casas vizinhas aparecem fora da ordem numérica.",
        "Ranking oficial: crédito por participante e papel; valores em R$ convertidos de R$ mil.",
        "Originação e distribuição têm perímetros distintos. Tipos 1 e 2 excluem empresas ligadas; Tipo 3 é apresentado separadamente.",
        "Top 15 ANBIMA: registros CVM distintos no anexo de originação de FIDC, Tipo 1; soma dos créditos por participante em cada registro. Não é o universo de ofertas CVM/SRE.",
        "Top 15 renda fixa e híbridos: operações por emissor e data de encerramento, Tipos 1 e 2 do anexo de originação; todos os registros vinculados são preservados. Empresas ligadas ficam no Tipo 3, fora deste total.",
        "Últimos 12 meses: valores do ranking oficial, com janela própria. O anexo corrente contém somente o acumulado do ano e não reconstrói a janela de 12 meses.",
        "Setores: volume do anexo ANBIMA associado por CNPJ à taxonomia oficial/analítica usada no estudo; FIC-FIDC e N/D permanecem explícitos no denominador.",
        "Asteriscos da planilha oficial são notas da publicação; o nome original é preservado em participant_source.",
    ]
    def records(frame):
        # JSON round-trip gives native scalar types and null for missing data.
        return json.loads(frame.to_json(orient="records", force_ascii=False, date_format="iso", double_precision=15))
    return {
        "schema_version": "industry_anbima_analysis_v1", "comparison_meta": meta,
        "source_reference_competence": manifest["source_reference_competence"],
        "source_as_of_date": manifest["source_as_of_date"],
        "windows": {"acumulado_ano": {"label":meta["period_label"], "start":meta["current_period_start"], "end":meta["current_period_end"]},
                    "ultimos_12_meses": {"label":f"{short_date(ltm_start)}–{short_date(meta['current_period_end'])}", "start":ltm_start,"end":meta["current_period_end"]}},
        "sources": manifest.get("sources", {}),
        "reconciliation_quality": manifest["reconciliation_quality"], "notes": notes,
        "ranking": records(ranking), "ranking_all": records(all_ranking),
        "ibba_positions": [row for row in positions if row["window"] == "acumulado_ano" and row["ranking_code"] in SCOPES],
        "ibba_positions_all": positions,
        "hybrids_definition": HYBRIDS_DEFINITION,
        "synthesis_products": records(synthesis_products),
        "synthesis_competitors": records(synthesis_competitors),
        "market_operations": records(operations), "market_top15": records(market_top15),
        "market_summary": {"volume_brl": float(operations.volume_brl.sum()), "operations": len(operations),
            "top15_volume_brl": float(market_top15.volume_brl.sum()),
            "top15_share": float(market_top15.volume_brl.sum()/operations.volume_brl.sum()),
            "top15_ibba_operations": int(market_top15.ibba_participant.sum())},
        "products": records(products.sort_values("volume_brl", ascending=False)),
        "fidc_sectors": records(sectors.sort_values("volume_brl", ascending=False)),
        "fidc_deals": records(deals), "fidc_top15": records(top15),
        "fidc_summary": {"volume_brl": total, "registrations": len(deals),
            "top15_volume_brl": float(top15.volume_brl.sum()), "top15_share": float(top15.volume_brl.sum()) / total,
            "top15_ibba_registrations": int(top15.ibba_participant.sum()),
            "matched_registrations": len(matched), "matched_volume_brl": float(matched.volume_brl.sum()),
            "cnpj_volume_coverage": float(matched.volume_brl.sum()) / total,
            "classification_volume_coverage": float(deals.loc[deals.category.ne("N/D"), "volume_brl"].sum()) / total},
    }
