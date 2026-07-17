"""Consolida os dados reproduzíveis consumidos pelo PPTX/XLSX revisados.

O módulo analítico (`build_fidc_revision_analysis.py`) permanece responsável
pelos denominadores, rankings, cobertura e reconciliações. Este script apenas
organiza essas saídas e as bases já versionadas em um payload editorial único;
nenhum percentual do deck é recalculado na camada de PowerPoint.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

import numpy as np
import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fund_name_display import short_fund_name


ROOT = Path(__file__).resolve().parents[1]
LATEST_COMPLETE = "2026-05"


def _digits(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    raw = str(value).strip()
    if re.fullmatch(r"\d{1,14}(?:\.0+)?", raw):
        raw = raw.split(".", 1)[0]
    digits = re.sub(r"\D", "", raw)
    return digits.zfill(14) if digits else ""


def _text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _display_fund_name(value: object) -> str:
    text = _text(value)
    upper = text.upper()
    rules = (
        ("SISTEMA PETROBRAS", "FIDC Sistema Petrobras"),
        ("TAPSO", "TAPSO"),
        ("CLOUDWALK BELA", "CloudWalk Bela"),
        ("ITAÚ CRÉDITO PRIVADO", "Itaú Crédito Privado"),
        ("ESPERANZA", "Esperanza"),
        ("BTG PACTUAL CONSIGNADOS II", "BTG Consignados II"),
        ("CLASSE CONSIGNADO PRIVADO DO MT GLOBAL", "MT Global · Consignado Privado"),
        ("PAN AUTO", "PAN Auto"),
        ("AETOS ENERGIA", "Aetos Energia"),
        ("PAGSEGURO I", "PagSeguro I"),
        ("CIELO", "Cielo"),
        ("RIO VERMELHO", "Rio Vermelho NP"),
        ("BTG PACTUAL CONSIGNADOS", "BTG Consignados"),
        ("ALTERNATIVE ASSETS III", "Alternative Assets III"),
        ("NC 2025 I", "NC 2025 I"),
        ("MONEE I", "Monee I"),
        ("PICPAY I", "PicPay I"),
        ("ARTESANAL MASTER", "Artesanal Master"),
        ("HIGH TOWER", "High Tower NP"),
        ("DAY MAXX 2", "Day Maxx 2"),
    )
    for needle, label in rules:
        if needle in upper:
            return label
    return short_fund_name(text, max_length=62).replace("...", "").strip()


def _json_value(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, np.bool_):
        return bool(value)
    if value is pd.NA or (isinstance(value, float) and pd.isna(value)):
        return None
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.astype(object).where(pd.notna(frame), None)
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in clean.to_dict(orient="records")
    ]


def _read_optional(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def _last_observation_by_year(monthly: pd.DataFrame, latest: str) -> pd.DataFrame:
    scoped = monthly[monthly["competencia"].astype(str).le(latest)].copy()
    scoped["year"] = scoped["competencia"].astype(str).str[:4].astype(int)
    scoped = scoped[scoped["year"].ge(2015)]
    return (
        scoped.sort_values("competencia")
        .groupby("year", as_index=False)
        .tail(1)
        .sort_values("year")
    )


def _investor_composition(
    cotistas: pd.DataFrame,
    latest: str,
    *,
    expected_total: float | None = None,
) -> pd.DataFrame:
    scoped = cotistas[cotistas["competencia"].astype(str).eq(latest)].copy()
    values = scoped.set_index("tipo_cotista")["n_cotistas"].to_dict()

    def total(*labels: str) -> float:
        return float(sum(float(values.get(label, 0) or 0) for label in labels))

    rows = [
        ("Fundos", total("Outros fundos", "Cotas de FIDC (outros FIDC/FIC-FIDC)", "FII")),
        ("Empresas e outros", total("Outros", "PJ nao financeira", "Investidor nao residente", "Clube de investimento")),
        ("Pessoa física", total("Pessoa fisica")),
        ("Instituições financeiras", total("Corretora/distribuidora", "Banco comercial", "Outra PJ financeira")),
        ("Previdência e seguros", total("Previdencia fechada (EFPC)", "Regime proprio (RPPS)", "Previdencia aberta (EAPC)", "Seguradora", "Capitalizacao")),
    ]
    result = pd.DataFrame(rows, columns=["categoria", "contas"])
    identified = float(result["contas"].sum())
    residual = max(0.0, float(expected_total or 0.0) - identified)
    if residual:
        result = pd.concat(
            [
                result,
                pd.DataFrame([{"categoria": "Não classificado", "contas": residual}]),
            ],
            ignore_index=True,
        )
    result["share"] = result["contas"] / result["contas"].sum()
    return result


def _holder_distribution(vehicle: pd.DataFrame, latest: str) -> pd.DataFrame:
    scoped = vehicle[
        vehicle["competencia"].astype(str).eq(latest)
        & ~vehicle["is_fic_fidc"].fillna(False).astype(bool)
    ].copy()
    scoped["cnpj_fundo"] = scoped["cnpj_fundo"].map(_digits)
    scoped["cnpj_fundo"] = scoped["cnpj_fundo"].where(
        scoped["cnpj_fundo"].ne(""), scoped["cnpj"].map(_digits)
    )
    scoped["cotistas"] = pd.to_numeric(scoped["cotistas"], errors="coerce")
    funds = scoped.groupby("cnpj_fundo", as_index=False).agg(
        pl=("pl", "sum"), contas=("cotistas", lambda values: values.sum(min_count=1))
    )
    funds = funds[funds["pl"].ge(200_000_000)].copy()
    funds = funds[funds["contas"].notna()].copy()
    if funds["contas"].lt(0).any():
        raise ValueError("distribuição por cotistas contém quantidade negativa")
    if not np.allclose(funds["contas"], funds["contas"].round(), atol=1e-9):
        raise ValueError("distribuição por cotistas contém quantidade fracionária")
    funds["bucket"] = pd.cut(
        funds["contas"],
        bins=[-np.inf, 0, 1, 3, 10, 50, np.inf],
        labels=["0", "1", "2–3", "4–10", "11–50", "51+"],
        right=True,
    )
    order = ["0", "1", "2–3", "4–10", "11–50", "51+"]
    grouped = (
        funds.groupby("bucket", observed=False)
        .agg(fundos=("cnpj_fundo", "nunique"), pl=("pl", "sum"))
        .reindex(order, fill_value=0)
        .reset_index()
    )
    total_funds = int(grouped["fundos"].sum())
    total_pl = float(grouped["pl"].sum())
    grouped["share_fundos"] = grouped["fundos"] / total_funds if total_funds else 0.0
    grouped["share_pl"] = grouped["pl"] / total_pl if total_pl else 0.0
    grouped["universo_fundos"] = total_funds
    grouped["universo_pl"] = total_pl

    if total_funds and not np.isclose(grouped["share_fundos"].sum(), 1.0, atol=1e-12):
        raise ValueError("distribuição por cotistas não fecha 100% em quantidade de fundos")
    if total_pl and not np.isclose(grouped["share_pl"].sum(), 1.0, atol=1e-12):
        raise ValueError("distribuição por cotistas não fecha 100% em PL")
    return grouped


def _type_mix(funds: pd.DataFrame, latest: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    scoped = funds[
        funds["competencia"].astype(str).eq(latest)
        & ~funds["is_fic_fidc"].fillna(False).astype(bool)
    ].copy()
    total_pl = float(scoped["pl"].sum())
    mix = scoped.groupby("anbima_tipo", dropna=False, as_index=False)["pl"].sum()
    mix["anbima_tipo"] = mix["anbima_tipo"].map(_text).replace("", "N/D")
    mix["share"] = mix["pl"] / total_pl
    order = ["Fomento Mercantil", "Agro, Indústria e Comércio", "Financeiro", "Outros", "N/D"]
    mix["order"] = mix["anbima_tipo"].map({name: index for index, name in enumerate(order)})
    mix = mix.sort_values(["order", "pl"], na_position="last").drop(columns="order")

    coverage = scoped.groupby("classification_tier", dropna=False, as_index=False)["pl"].sum()
    label_map = {
        "oficial_anbima": "Oficial ANBIMA",
        "evidencia_publicada": "Evidência documental",
        "proxy_cvm": "Proxy CVM",
        "nao_disponivel": "N/D",
    }
    coverage["categoria"] = coverage["classification_tier"].map(label_map).fillna(
        coverage["classification_tier"].map(_text)
    )
    coverage["share"] = coverage["pl"] / total_pl
    coverage = coverage[["categoria", "pl", "share"]]
    return mix, coverage


def _receivables(segments: pd.DataFrame, latest: str, portfolio_total: float) -> dict[str, Any]:
    scoped = segments[
        segments["competencia"].astype(str).eq(latest)
        & segments["nivel"].astype(str).eq("top")
    ].copy()
    scoped = scoped.groupby("segmento", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
    reported_total = float(scoped["valor"].sum())
    return {
        "rows": _records(scoped),
        "reported_total": reported_total,
        "portfolio_total": portfolio_total,
        "gap": reported_total - portfolio_total,
        "gap_pct": (reported_total / portfolio_total - 1) if portfolio_total else None,
    }


def _provider_concentration(providers: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for role, group in providers.groupby("papel"):
        sorted_group = group.sort_values("pl", ascending=False).copy()
        shares = pd.to_numeric(sorted_group["share_pl"], errors="coerce").fillna(0)
        top = sorted_group.head(3)
        rows.append(
            {
                "papel": role,
                "top5_share": float(shares.head(5).sum()),
                "top10_share": float(shares.head(10).sum()),
                "hhi": float(((shares * 100) ** 2).sum()),
                "top3": _records(top[["nome", "pl", "share_pl", "n_fundos"]]),
            }
        )
    return rows


def _service_model(mono: pd.DataFrame, latest: str) -> pd.DataFrame:
    scoped = mono[mono["competencia"].astype(str).eq(latest)].copy()
    grouped = scoped.groupby("modelo_prestacao", dropna=False).agg(
        fundos=("cnpj_fundo", "nunique"), pl=("pl", "sum")
    ).reset_index()
    grouped["share_fundos"] = grouped["fundos"] / grouped["fundos"].sum()
    grouped["share_pl"] = grouped["pl"] / grouped["pl"].sum()
    order = [
        "Monoestrutura",
        "Administração + Gestão",
        "Administração + Custódia",
        "Gestão + Custódia",
        "Três prestadores distintos",
        "Dados incompletos",
    ]
    grouped["order"] = grouped["modelo_prestacao"].map({name: i for i, name in enumerate(order)})
    return grouped.sort_values("order").drop(columns="order")


def _offers_ytd(offers: pd.DataFrame, *, as_of_date: str) -> pd.DataFrame:
    frame = offers.copy()
    frame["registration_date"] = pd.to_datetime(frame["registration_date"], errors="coerce")
    frame["year"] = frame["registration_date"].dt.year
    cutoff = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(cutoff):
        cutoff = pd.Timestamp(year=2026, month=7, day=15)
    cutoff_month_day = (int(cutoff.month), int(cutoff.day))
    comparison_years = list(range(int(cutoff.year) - 2, int(cutoff.year) + 1))
    frame = frame[
        frame["year"].isin(comparison_years)
        & frame["valid_offer"].fillna(False).astype(bool)
        & frame["registration_date"].notna()
    ].copy()
    frame = frame[
        (frame["registration_date"].dt.month < cutoff_month_day[0])
        | (
            frame["registration_date"].dt.month.eq(cutoff_month_day[0])
            & frame["registration_date"].dt.day.le(cutoff_month_day[1])
        )
    ]
    return frame.groupby("year", as_index=False).agg(
        ofertas=("offer_id", "nunique"), volume=("registered_volume_brl", "sum")
    )


def _originators(originators: pd.DataFrame, year: int) -> dict[str, Any]:
    scoped = originators[originators["year"].eq(year)].copy()
    scoped = scoped[~scoped["originator_group"].astype(str).eq("Não identificado")]
    scoped = scoped.sort_values(["rank", "volume_brl"], ascending=[True, False]).head(5)
    coverage = float(scoped["identified_volume_coverage"].dropna().iloc[0]) if not scoped.empty else None
    return {"coverage": coverage, "rows": _records(scoped[["originator_group", "volume_brl", "share_of_total", "confidence"]])}


def _load_curation(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            for key in ("rows", "top20", "curadoria", "funds"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        return pd.DataFrame(payload if isinstance(payload, list) else [])
    return pd.read_csv(path, low_memory=False)


def _pick(row: pd.Series, *names: str) -> str:
    for name in names:
        if name in row.index:
            value = _text(row.get(name))
            if value:
                return value
    return ""


def _build_profiles(
    top20: pd.DataFrame,
    curation: pd.DataFrame,
    documentary: pd.DataFrame,
) -> pd.DataFrame:
    cur = curation.copy()
    if not cur.empty:
        cnpj_col = next((c for c in ("cnpj", "cnpj_fundo", "cnpj_14") if c in cur.columns), None)
        cur["cnpj_key"] = cur[cnpj_col].map(_digits) if cnpj_col else ""
        cur = cur.drop_duplicates("cnpj_key", keep="last").set_index("cnpj_key")
    doc = documentary.copy()
    if not doc.empty:
        doc["cnpj_key"] = doc["cnpj"].map(_digits)
        doc = doc.drop_duplicates("cnpj_key", keep="last").set_index("cnpj_key")
    profiles: list[dict[str, Any]] = []
    for _, fund in top20.sort_values("rank").iterrows():
        key = _digits(fund.get("cnpj_fundo"))
        curated = cur.loc[key] if not cur.empty and key in cur.index else pd.Series(dtype=object)
        documented = doc.loc[key] if not doc.empty and key in doc.index else pd.Series(dtype=object)
        nature = _pick(curated, "natureza_recebiveis", "natureza_dos_recebiveis", "recebiveis")
        if not nature:
            d1 = _pick(documented, "document_segment_n1")
            d2 = _pick(documented, "document_segment_n2")
            nature = " — ".join(item for item in (d1, d2) if item)
        evidence = _pick(curated, "evidencia", "evidencia_resumo", "trecho_evidencia")
        evidence = evidence or _pick(
            curated,
            "nota_classificacao",
            "segmento_economico_documental",
        )
        if not evidence:
            evidence = _pick(documented, "classification_evidence")[:280]
        source = _pick(curated, "fonte", "fontes", "source", "url", "links")
        source = source or _pick(curated, "fundosnet_gerenciador")
        if not source:
            source = _pick(documented, "source")
        classes = _pick(
            curated,
            "classes_subordinacao_garantias",
            "classes_subordinacao",
            "classes",
            "subordinacao_garantias",
        )
        guarantees = _pick(curated, "garantias")
        if guarantees and guarantees not in classes:
            classes = f"{classes} Garantias: {guarantees}".strip()
        fields = {
            "rank": int(fund["rank"]),
            "cnpj_fundo": key,
            "cnpj_fundo_formatado": _text(fund.get("cnpj_fundo_formatado")),
            "denominacao": _text(fund.get("denominacao")),
            "nome_curto": _display_fund_name(fund.get("denominacao")),
            "pl": float(fund["pl"]),
            "market_share_ex_fic": float(fund["market_share_ex_fic"]),
            "cedente_originador": _pick(curated, "cedente_originador", "cedente", "originador") or "não identificado",
            "sacado_devedor": _pick(curated, "sacado_devedor", "sacado", "devedor", "perfil_sacados") or "não identificado",
            "natureza_recebiveis": nature or "não identificado",
            "funcionamento_economico": _pick(curated, "funcionamento_economico", "funcionamento", "mecanica") or "não identificado",
            "emissoes": _pick(curated, "emissoes", "emissoes_relevantes", "ofertas") or "não identificado",
            "classes_subordinacao_garantias": classes or "não identificado",
            "administrador": _pick(curated, "administrador") or _text(fund.get("admin_nome")) or "não informado",
            "gestor": _pick(curated, "gestor") or _text(fund.get("gestor_nome")) or "não informado",
            "custodiante": _pick(curated, "custodiante") or _text(fund.get("custodiante_nome")) or "não informado",
            "anbima_tipo": _pick(curated, "tipo_anbima") or _text(fund.get("anbima_tipo")) or "N/D",
            "anbima_foco": _pick(curated, "foco_anbima") or _text(fund.get("anbima_foco")) or "N/D",
            "origem_classificacao": _pick(curated, "origem_tipo_foco") or _text(fund.get("classification_status")) or "N/D",
            "fonte": source or "CVM/FundosNet consultado; campo não identificado",
            "data_consulta": _pick(curated, "data_consulta", "consulted_at") or "2026-07-16",
            "evidencia": evidence
            or _pick(curated, "nota_classificacao", "segmento_economico_documental")
            or "campo não identificado nos documentos consultados",
            "status_curadoria": _pick(curated, "status_curadoria") or "pendente",
            "campos_nao_identificados": _pick(curated, "campos_nao_identificados") or "não identificado",
            "documentos_primarios_ids": _pick(curated, "documentos_primarios_ids") or "não identificado",
            "data_referencia_tipo_foco": _pick(curated, "data_referencia_tipo_foco") or "2026-05",
        }
        profiles.append(fields)
    return pd.DataFrame(profiles)


def _build_top20_outros_review(
    top20_outros: pd.DataFrame,
    documentary: pd.DataFrame,
) -> pd.DataFrame:
    doc = documentary.copy()
    if not doc.empty:
        doc["cnpj_key"] = doc["cnpj"].map(_digits)
        doc = doc.drop_duplicates("cnpj_key", keep="last").set_index("cnpj_key")
    rows: list[dict[str, Any]] = []
    for _, fund in top20_outros.sort_values("rank_outros").iterrows():
        key = _digits(fund.get("cnpj_fundo"))
        evidence = doc.loc[key] if not doc.empty and key in doc.index else pd.Series(dtype=object)
        d1 = _pick(evidence, "document_segment_n1")
        d2 = _pick(evidence, "document_segment_n2")
        hypothesis = " — ".join(item for item in (d1, d2) if item)
        rows.append(
            {
                **{key_: _json_value(value) for key_, value in fund.items()},
                "nome_curto": _display_fund_name(fund.get("denominacao")),
                "classificacao_oficial": " | ".join(
                    item for item in (_text(fund.get("anbima_tipo")), _text(fund.get("anbima_foco"))) if item
                ) or "N/D",
                "hipotese_revisao": hypothesis or "não identificada",
                "evidencia_revisao": _pick(evidence, "classification_evidence")[:220]
                or "não identificada nos documentos locais",
                "fonte_revisao": _pick(evidence, "source") or "fonte primária pendente",
                "status_revisao": (
                    f"evidência documental — {_pick(evidence, 'classification_confidence')}"
                    if hypothesis
                    else "pendente"
                ),
            }
        )
    return pd.DataFrame(rows)


def build_payload(
    data_dir: Path,
    revision_dir: Path,
    curation_path: Path,
    latest: str,
) -> dict[str, Any]:
    monthly = pd.read_csv(data_dir / "industry_monthly.csv", low_memory=False)
    vehicle = pd.read_csv(data_dir / "vehicle_monthly.csv.gz", low_memory=False)
    cotistas = pd.read_csv(data_dir / "cotistas_tipo_monthly.csv", low_memory=False)
    segments = pd.read_csv(data_dir / "segments_monthly.csv", low_memory=False)
    providers = pd.read_csv(data_dir / "prestadores_latest.csv", low_memory=False)
    offers = pd.read_csv(data_dir / "industry_offers.csv.gz", low_memory=False)
    originators = pd.read_csv(data_dir / "industry_originators_annual.csv", low_memory=False)
    documentary = _read_optional(data_dir / "industry_large_fund_classification.csv")
    intelligence_manifest_path = data_dir / "industry_intelligence_manifest.json"
    intelligence_manifest = (
        json.loads(intelligence_manifest_path.read_text(encoding="utf-8"))
        if intelligence_manifest_path.exists()
        else {}
    )

    funds = pd.read_csv(revision_dir / "base_fundo_cnpj.csv.gz", low_memory=False)
    qa = pd.read_csv(revision_dir / "qa_inadimplencia_competencia.csv", low_memory=False)
    bridge_summary = pd.read_csv(
        revision_dir / "bridge_inadimplencia_2024-06_2024-07_resumo.csv", low_memory=False
    )
    bridge_detail = pd.read_csv(
        revision_dir / "bridge_inadimplencia_2024-06_2024-07_detalhe.csv", low_memory=False
    )
    top20 = pd.read_csv(revision_dir / "top20_fidcs.csv", dtype={"cnpj_fundo": str})
    top20_outros = pd.read_csv(revision_dir / "top20_outros.csv", dtype={"cnpj_fundo": str})
    mono = pd.read_csv(revision_dir / "monoestrutura_por_fundo.csv", low_memory=False)
    mono_concentration = pd.read_csv(revision_dir / "monoestrutura_concentracao.csv", low_memory=False)
    market = pd.read_csv(revision_dir / "market_share_por_subtipo.csv", low_memory=False)
    fixed_top10 = pd.read_csv(revision_dir / "market_share_top10_fixo.csv", low_memory=False)

    annual = _last_observation_by_year(monthly, latest)
    annual_pl = annual[["year", "competencia", "pl_total", "pl_fic_fidc"]].copy()
    annual_pl["pl_ex_fic"] = annual_pl["pl_total"] - annual_pl["pl_fic_fidc"]
    annual_pl["pl_fic_componente"] = annual_pl["pl_fic_fidc"]
    annual_base = annual[["year", "competencia", "cotistas_total", "n_veiculos"]].copy()

    latest_month = monthly[monthly["competencia"].astype(str).eq(latest)].iloc[0]
    offers_as_of = str(intelligence_manifest.get("as_of_date") or "")
    if not offers_as_of:
        offer_dates = pd.to_datetime(
            offers["registration_date"]
            if "registration_date" in offers
            else pd.Series(dtype="object"),
            errors="coerce",
        )
        latest_offer_date = offer_dates.max()
        offers_as_of = (
            latest_offer_date.strftime("%Y-%m-%d")
            if pd.notna(latest_offer_date)
            else "2026-07-15"
        )
    offers_year = int(pd.to_datetime(offers_as_of, errors="coerce").year)
    latest_period = pd.Period(latest, freq="M")
    latest_months = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
    latest_label = f"{latest_months[latest_period.month - 1]}/{str(latest_period.year)[-2:]}"
    type_mix, classification_coverage = _type_mix(funds, latest)
    receivables = _receivables(segments, latest, float(latest_month["carteira_dc"]))
    qa_latest = qa[qa["competencia"].astype(str).eq(latest)].iloc[0].to_dict()
    qa_series = qa[qa["competencia"].astype(str).between("2023-01", latest)].copy()
    qa_series = qa_series[
        [
            "competencia",
            "inadimplencia_bruta_pct",
            "inadimplencia_ajustada_pct",
            "inadimplencia_ajustada_ex_np_pct",
            "cobertura_carteira",
        ]
    ]
    atlantic = bridge_detail[
        bridge_detail["cnpj"].map(_digits).eq("09194841000151")
        | bridge_detail["cnpj_fundo"].map(_digits).eq("09194841000151")
    ].copy()

    curation = _load_curation(curation_path)
    profiles = _build_profiles(top20, curation, documentary)
    top20_outros_review = _build_top20_outros_review(top20_outros, documentary)

    material_focus = (
        market[["tipo_anbima", "foco_anbima", "denominador_pl_subtipo_brl"]]
        .drop_duplicates()
        .sort_values("denominador_pl_subtipo_brl", ascending=False)
    )
    material_top6 = material_focus.head(6).copy()
    material_omitted = material_focus.iloc[6:].copy()
    holder_distribution = _holder_distribution(vehicle, latest)
    latest_ex_fic = funds[
        funds["competencia"].astype(str).eq(latest)
        & ~funds["is_fic_fidc"].fillna(False).astype(bool)
    ].copy()
    holder_funds = int(holder_distribution["fundos"].sum())
    holder_pl = float(holder_distribution["pl"].sum())
    ex_fic_funds = int(latest_ex_fic["cnpj_fundo"].nunique())
    ex_fic_pl = float(latest_ex_fic["pl"].sum())

    output = {
        "schema_version": "fidc_revision_artifact_payload_v1",
        "latest_complete": latest,
        "offers_as_of": offers_as_of,
        "generated_at": pd.Timestamp.now(tz="America/Sao_Paulo").isoformat(),
        "pl_history": _records(annual_pl),
        "investor_base_history": _records(annual_base),
        "investor_composition": _records(
            _investor_composition(
                cotistas,
                latest,
                expected_total=float(latest_month["cotistas_total"]),
            )
        ),
        "holder_distribution": _records(holder_distribution),
        "holder_distribution_meta": {
            "minimum_pl_brl": 200_000_000,
            "eligible_funds": holder_funds,
            "eligible_pl_brl": holder_pl,
            "ex_fic_funds": ex_fic_funds,
            "ex_fic_pl_brl": ex_fic_pl,
            "fund_coverage": holder_funds / ex_fic_funds if ex_fic_funds else None,
            "pl_coverage": holder_pl / ex_fic_pl if ex_fic_pl else None,
        },
        "type_mix": _records(type_mix),
        "classification_coverage": _records(classification_coverage),
        "receivables": receivables,
        "qa_latest": {str(key): _json_value(value) for key, value in qa_latest.items()},
        "qa_series": _records(qa_series),
        "bridge_summary": _records(bridge_summary),
        "bridge_top_contributors": _records(bridge_detail.head(30)),
        "bridge_atlantico": _records(atlantic),
        "provider_concentration": _provider_concentration(providers),
        "market_share": _records(market),
        "market_share_top10_fixed": _records(fixed_top10),
        "material_focus_top6": _records(material_top6),
        "material_focus_omitted": {
            "focuses": int(len(material_omitted)),
            "pl": float(material_omitted["denominador_pl_subtipo_brl"].sum()),
            "share": float(
                material_omitted["denominador_pl_subtipo_brl"].sum()
                / material_focus["denominador_pl_subtipo_brl"].sum()
            ),
        },
        "top20_fidcs": _records(top20.assign(nome_curto=top20["denominacao"].map(_display_fund_name))),
        "top20_outros": _records(top20_outros_review),
        "profiles": _records(profiles),
        "service_model": _records(_service_model(mono, latest)),
        "monostructure_concentration": _records(mono_concentration),
        "offers_ytd": _records(_offers_ytd(offers, as_of_date=offers_as_of)),
        "originators_current": _originators(originators, offers_year),
        # Backward-compatible alias for the July/2026 renderer snapshot.
        "originators_2026": _originators(originators, offers_year),
        "sources": {
            "pl_cotistas_recebiveis": f"CVM, Informe Mensal de FIDC, competência {latest_label}",
            "anbima": f"ANBIMA Data, fotografia cadastral de dez/25 aplicada a {latest_label}; evidência documental; proxy CVM; N/D",
            "offers": f"CVM, Ofertas Públicas de Distribuição, registros até {offers_as_of}",
            "cvm_489": "https://conteudo.cvm.gov.br/export/sites/cvm/legislacao/instrucoes/anexos/400/inst489.pdf",
            "cvm_writeoff": "https://conteudo.cvm.gov.br/export/sites/cvm/legislacao/oficios-circulares/sin-snc/anexos/oc-sin-snc-0113.pdf",
        },
    }
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/industry_study")
    parser.add_argument(
        "--revision-dir",
        type=Path,
        default=ROOT / "data/industry_study/generated_revision",
    )
    parser.add_argument(
        "--curation",
        type=Path,
        default=ROOT / "outputs/analysis/top20_fidcs_curadoria.csv",
    )
    parser.add_argument(
        "--latest-complete",
        default="",
        help="competência AAAA-MM; vazio usa a última marcada como completa",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/industry_study/generated_revision/artifact_payload.json",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    latest_complete = str(args.latest_complete or "").strip()
    if not latest_complete:
        status_path = args.data_dir / "industry_competence_status.csv"
        status = pd.read_csv(status_path, low_memory=False) if status_path.exists() else pd.DataFrame()
        complete = (
            status[status["publication_status"].astype(str).eq("completa")]
            if not status.empty and "publication_status" in status
            else pd.DataFrame()
        )
        if not complete.empty:
            latest_complete = str(complete["competencia"].astype(str).max())
        else:
            monthly = pd.read_csv(args.data_dir / "industry_monthly.csv", low_memory=False)
            latest_complete = str(monthly["competencia"].astype(str).max())
    payload = build_payload(
        data_dir=args.data_dir,
        revision_dir=args.revision_dir,
        curation_path=args.curation,
        latest=latest_complete,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_value),
        encoding="utf-8",
    )
    print(f"[ok] payload editorial: {args.output}")


if __name__ == "__main__":
    main()
