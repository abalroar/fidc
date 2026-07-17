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
from services.industry_intelligence import canonical_provider
from services.industry_revision_analysis import MARKET_SHARE_EXCLUDED_FUNDS


ROOT = Path(__file__).resolve().parents[1]
LATEST_COMPLETE = "2026-05"
HISTORICAL_REFERENCE = "2023-12"
PROVIDER_REFERENCE = "2025-12"
ATLANTICO_CNPJ = "09194841000151"


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


def _holder_distribution_history(
    vehicle: pd.DataFrame,
    periods: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    distributions: list[pd.DataFrame] = []
    metadata: list[dict[str, Any]] = []
    for period in periods:
        grouped = _holder_distribution(vehicle, period)
        grouped.insert(0, "competencia", period)
        distributions.append(grouped)

        scoped = vehicle[
            vehicle["competencia"].astype(str).eq(period)
            & ~vehicle["is_fic_fidc"].fillna(False).astype(bool)
        ].copy()
        scoped["cnpj_fundo"] = scoped["cnpj_fundo"].map(_digits)
        scoped["cnpj_fundo"] = scoped["cnpj_fundo"].where(
            scoped["cnpj_fundo"].ne(""), scoped["cnpj"].map(_digits)
        )
        ex_fic_funds = int(scoped["cnpj_fundo"].nunique())
        ex_fic_pl = float(pd.to_numeric(scoped["pl"], errors="coerce").fillna(0).sum())
        eligible_funds = int(grouped["fundos"].sum())
        eligible_pl = float(grouped["pl"].sum())
        metadata.append(
            {
                "competencia": period,
                "minimum_pl_brl": 200_000_000,
                "eligible_funds": eligible_funds,
                "eligible_pl_brl": eligible_pl,
                "ex_fic_funds": ex_fic_funds,
                "ex_fic_pl_brl": ex_fic_pl,
                "fund_coverage": eligible_funds / ex_fic_funds if ex_fic_funds else None,
                "pl_coverage": eligible_pl / ex_fic_pl if ex_fic_pl else None,
            }
        )
    return pd.concat(distributions, ignore_index=True), pd.DataFrame(metadata)


def _type_mix(funds: pd.DataFrame, latest: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    scoped = funds[
        funds["competencia"].astype(str).eq(latest)
        & ~funds["is_fic_fidc"].fillna(False).astype(bool)
    ].copy()
    total_pl = float(scoped["pl"].sum())
    # A taxonomia ANBIMA é uma fotografia cadastral vigente aplicada ao histórico.
    # Se o veículo era ex-FIC na competência, mas hoje está rotulado como FIC-FIDC,
    # não o eliminamos retrospectivamente do denominador: preservamos o PL em N/D.
    scoped["anbima_tipo_period_aware"] = scoped["anbima_tipo"]
    fic_label_on_ex_fic = scoped["anbima_tipo"].map(_text).eq("FIC-FIDC")
    scoped.loc[fic_label_on_ex_fic, "anbima_tipo_period_aware"] = "N/D"
    mix = scoped.groupby("anbima_tipo_period_aware", dropna=False, as_index=False)["pl"].sum()
    mix = mix.rename(columns={"anbima_tipo_period_aware": "anbima_tipo"})
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


def _type_mix_history(
    funds: pd.DataFrame,
    periods: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    mixes: list[pd.DataFrame] = []
    coverages: list[pd.DataFrame] = []
    for period in periods:
        mix, coverage = _type_mix(funds, period)
        mix.insert(0, "competencia", period)
        coverage.insert(0, "competencia", period)
        mixes.append(mix)
        coverages.append(coverage)
    return pd.concat(mixes, ignore_index=True), pd.concat(coverages, ignore_index=True)


def _receivables(segments: pd.DataFrame, latest: str, portfolio_total: float) -> dict[str, Any]:
    scoped = segments[
        segments["competencia"].astype(str).eq(latest)
        & segments["nivel"].astype(str).eq("top")
    ].copy()
    scoped = scoped.groupby("segmento", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
    reported_total = float(scoped["valor"].sum())
    scoped["share_reported"] = scoped["valor"] / reported_total if reported_total else 0.0
    if reported_total and not np.isclose(scoped["share_reported"].sum(), 1.0, atol=1e-12):
        raise ValueError("tipos de recebível não fecham 100% sobre a Tabela II")
    return {
        "rows": _records(scoped),
        "reported_total": reported_total,
        "portfolio_total": portfolio_total,
        "gap": reported_total - portfolio_total,
        "gap_pct": (reported_total / portfolio_total - 1) if portfolio_total else None,
    }


def _receivables_history(
    segments: pd.DataFrame,
    monthly: pd.DataFrame,
    periods: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[pd.DataFrame] = []
    metadata: list[dict[str, Any]] = []
    for period in periods:
        month = monthly[monthly["competencia"].astype(str).eq(period)]
        if month.empty:
            raise ValueError(f"competência ausente em industry_monthly.csv: {period}")
        portfolio_total = float(month.iloc[0]["carteira_dc"])
        result = _receivables(segments, period, portfolio_total)
        frame = pd.DataFrame(result["rows"])
        frame.insert(0, "competencia", period)
        rows.append(frame)
        metadata.append(
            {
                "competencia": period,
                "reported_total": result["reported_total"],
                "portfolio_total": result["portfolio_total"],
                "gap": result["gap"],
                "gap_pct": result["gap_pct"],
            }
        )
    return pd.concat(rows, ignore_index=True), pd.DataFrame(metadata)


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


def _provider_concentration_history(
    funds: pd.DataFrame,
    periods: list[str],
) -> list[dict[str, Any]]:
    role_columns = {
        "administrador": ("admin_nome", "admin_cnpj", "informe mensal da competência"),
        "gestor": ("gestor_nome", "gestor_cnpj", "cadastro CVM vigente aplicado à competência"),
        "custodiante": (
            "custodiante_nome",
            "custodiante_cnpj",
            "cadastro CVM vigente aplicado à competência",
        ),
    }
    rows: list[dict[str, Any]] = []
    excluded = set(MARKET_SHARE_EXCLUDED_FUNDS)
    for period in periods:
        scoped = funds[funds["competencia"].astype(str).eq(period)].copy()
        if "is_fic_fidc" in scoped.columns:
            scoped = scoped[~scoped["is_fic_fidc"].fillna(False)]
        scoped = scoped[~scoped["cnpj_fundo"].map(_digits).isin(excluded)]
        scoped["pl"] = pd.to_numeric(scoped["pl"], errors="coerce").fillna(0.0)
        total_pl = float(scoped["pl"].sum())
        total_funds = int(scoped["cnpj_fundo"].map(_digits).nunique())
        for role, (name_col, cnpj_col, source_note) in role_columns.items():
            scoped_role = scoped[["cnpj_fundo", "pl", name_col, cnpj_col]].copy()
            scoped_role["nome"] = scoped_role[name_col].map(canonical_provider)
            scoped_role["cnpj_prestador"] = scoped_role[cnpj_col].map(_digits)
            missing = scoped_role["nome"].eq("Não informado")
            missing_pl = float(scoped_role.loc[missing, "pl"].sum())
            known = scoped_role.loc[~missing].copy()
            grouped = (
                known.groupby("nome", as_index=False)
                .agg(
                    cnpj_prestador=("cnpj_prestador", "first"),
                    pl=("pl", "sum"),
                    n_fundos=("cnpj_fundo", lambda values: values.map(_digits).nunique()),
                )
                .sort_values("pl", ascending=False)
            )
            grouped["share_pl"] = grouped["pl"] / total_pl if total_pl else 0.0
            shares = grouped["share_pl"]
            rows.append(
                {
                    "competencia": period,
                    "papel": role,
                    "total_pl": total_pl,
                    "n_fundos": total_funds,
                    "identified_pl": total_pl - missing_pl,
                    "coverage_pl": (total_pl - missing_pl) / total_pl if total_pl else None,
                    "missing_pl": missing_pl,
                    "missing_share": missing_pl / total_pl if total_pl else None,
                    "top3_share": float(shares.head(3).sum()),
                    "top5_share": float(shares.head(5).sum()),
                    "top10_share": float(shares.head(10).sum()),
                    "hhi": float(((shares * 100) ** 2).sum()),
                    "top3": _records(grouped.head(3)[["nome", "cnpj_prestador", "pl", "share_pl", "n_fundos"]]),
                    "source_note": source_note,
                }
            )
    return rows


def _atlantico_payload(
    funds: pd.DataFrame,
    data_dir: Path,
    latest: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    curation_path = data_dir / "atlantico_curadoria.json"
    if not curation_path.exists():
        raise FileNotFoundError(f"curadoria do Atlântico não encontrada: {curation_path}")
    curated = json.loads(curation_path.read_text(encoding="utf-8"))

    scoped = funds[funds["cnpj_fundo"].map(_digits).eq(ATLANTICO_CNPJ)].copy()
    if scoped.empty:
        raise ValueError("FIDC Atlântico não encontrado na base por fundo/CNPJ")
    scoped = scoped.sort_values("competencia")

    def numeric(value: object) -> float:
        parsed = pd.to_numeric(value, errors="coerce")
        return 0.0 if pd.isna(parsed) else float(parsed)

    selected_periods = [HISTORICAL_REFERENCE, "2024-06", "2024-07", PROVIDER_REFERENCE, latest]
    history_rows: list[dict[str, Any]] = []
    for period in selected_periods:
        period_rows = scoped[scoped["competencia"].astype(str).eq(period)]
        if period_rows.empty:
            continue
        row = period_rows.iloc[0]
        portfolio = numeric(row.get("carteira_dc"))
        raw = numeric(row.get("dc_inadimplentes"))
        adjusted = numeric(row.get("dc_inadimplentes_ajustado_recalculado"))
        report_above_360 = str(row.get("reports_inad_acima_360d")).strip().lower() == "true"
        above_360 = (
            numeric(row.get("inad_acima_360d"))
            if report_above_360
            else None
        )
        above_1080 = (
            numeric(row.get("inad_maior_1080d"))
            if report_above_360
            else None
        )
        history_rows.append(
            {
                "competencia": period,
                "pl": numeric(row.get("pl")),
                "carteira": portfolio,
                "inadimplencia_bruta": raw,
                "inadimplencia_ajustada": adjusted,
                "vencidos_mais_360d": above_360,
                "vencidos_mais_1080d": above_1080,
                "excesso": max(raw - adjusted, 0.0),
                "inadimplencia_share_carteira": raw / portfolio if portfolio else None,
                "ajustada_share_carteira": adjusted / portfolio if portfolio else None,
                "mais_360_share_carteira": above_360 / portfolio if portfolio and above_360 is not None else None,
                "aging_reportado": report_above_360,
                "administrador": _text(row.get("admin_nome")) or "não identificado",
            }
        )

    history = pd.DataFrame(history_rows)
    current_rows = scoped[scoped["competencia"].astype(str).eq(latest)]
    if current_rows.empty:
        raise ValueError(f"FIDC Atlântico ausente na competência {latest}")
    current = current_rows.iloc[0]
    current_history = history[history["competencia"].eq(latest)].iloc[0]
    june = history[history["competencia"].eq("2024-06")].iloc[0]
    july = history[history["competencia"].eq("2024-07")].iloc[0]
    current_raw = float(current_history["inadimplencia_bruta"])
    current_portfolio = float(current_history["carteira"])
    current_above_360 = current_history["vencidos_mais_360d"]
    current_above_1080 = current_history["vencidos_mais_1080d"]

    profile: dict[str, Any] = {
        **curated,
        "denominacao": _text(current.get("denominacao")),
        "administrador": _text(current.get("admin_nome")) or "não identificado",
        "gestor": _text(current.get("gestor_nome")) or "não identificado",
        "custodiante": _text(current.get("custodiante_nome")) or "não identificado",
        "prestadores": (
            f"Administrador e custodiante: {_text(current.get('admin_nome')) or 'não identificado'}. "
            f"Gestor: {_text(current.get('gestor_nome')) or 'não identificado'}. "
            "Consultoria especializada: MGC Capital; agente de cobrança: Crediativos; auditor: BDO."
        ),
        "snapshot": {
            "competencia": latest,
            "pl": float(current_history["pl"]),
            "carteira": current_portfolio,
            "inadimplencia_bruta": current_raw,
            "inadimplencia_ajustada": float(current_history["inadimplencia_ajustada"]),
            "inadimplencia_share_carteira": current_raw / current_portfolio if current_portfolio else None,
            "vencidos_mais_360d": float(current_above_360) if pd.notna(current_above_360) else None,
            "mais_360_share_carteira": float(current_above_360) / current_portfolio
            if current_portfolio and pd.notna(current_above_360)
            else None,
            "vencidos_mais_1080d": float(current_above_1080) if pd.notna(current_above_1080) else None,
            "mais_1080_share_inadimplencia": float(current_above_1080) / current_raw
            if current_raw and pd.notna(current_above_1080)
            else None,
        },
        "bridge_2024_06_07": {
            "inadimplencia_bruta_jun": float(june["inadimplencia_bruta"]),
            "inadimplencia_bruta_jul": float(july["inadimplencia_bruta"]),
            "delta_inadimplencia_bruta": float(july["inadimplencia_bruta"] - june["inadimplencia_bruta"]),
            "carteira_jun": float(june["carteira"]),
            "carteira_jul": float(july["carteira"]),
            "delta_carteira": float(july["carteira"] - june["carteira"]),
            "pl_jun": float(june["pl"]),
            "pl_jul": float(july["pl"]),
            "delta_pl": float(july["pl"] - june["pl"]),
            "excesso_jun": float(june["excesso"]),
            "excesso_jul": float(july["excesso"]),
        },
        "is_np_pipeline": bool(current.get("is_np")) if pd.notna(current.get("is_np")) else None,
        "data_referencia": latest,
    }
    return profile, _records(history)


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
    market_scope = pd.read_csv(
        revision_dir / "market_share_escopo_resumo.csv", low_memory=False
    )
    provider_historical_ranking = pd.read_csv(
        revision_dir / "prestadores_ranking_historico.csv", low_memory=False
    )
    acquiring_path = data_dir / "acquiring_taxonomy_curation.json"
    acquiring_taxonomy = (
        json.loads(acquiring_path.read_text(encoding="utf-8"))
        if acquiring_path.exists()
        else {"summary": {}, "funds": [], "sources": []}
    )

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
    comparison_periods = [HISTORICAL_REFERENCE, latest]
    holder_distribution_history, holder_distribution_meta_history = _holder_distribution_history(
        vehicle, comparison_periods
    )
    type_mix_history, classification_coverage_history = _type_mix_history(
        funds, comparison_periods
    )
    receivables_history, receivables_meta_history = _receivables_history(
        segments, monthly, comparison_periods
    )
    provider_concentration_history = _provider_concentration_history(
        funds, [PROVIDER_REFERENCE, latest]
    )
    type_mix = type_mix_history[type_mix_history["competencia"].eq(latest)].drop(
        columns="competencia"
    )
    classification_coverage = classification_coverage_history[
        classification_coverage_history["competencia"].eq(latest)
    ].drop(columns="competencia")
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
    atlantico_profile, atlantico_history = _atlantico_payload(funds, data_dir, latest)

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
    holder_distribution = holder_distribution_history[
        holder_distribution_history["competencia"].eq(latest)
    ].drop(columns="competencia")
    holder_meta_latest = holder_distribution_meta_history[
        holder_distribution_meta_history["competencia"].eq(latest)
    ].iloc[0].drop(labels="competencia").to_dict()
    provider_concentration = [
        row for row in provider_concentration_history if row["competencia"] == latest
    ]

    output = {
        "schema_version": "fidc_revision_artifact_payload_v3",
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
            str(key): _json_value(value) for key, value in holder_meta_latest.items()
        },
        "holder_distribution_history": _records(holder_distribution_history),
        "holder_distribution_meta_history": _records(holder_distribution_meta_history),
        "type_mix": _records(type_mix),
        "classification_coverage": _records(classification_coverage),
        "type_mix_history": _records(type_mix_history),
        "classification_coverage_history": _records(classification_coverage_history),
        "receivables": receivables,
        "receivables_history": _records(receivables_history),
        "receivables_meta_history": _records(receivables_meta_history),
        "qa_latest": {str(key): _json_value(value) for key, value in qa_latest.items()},
        "qa_series": _records(qa_series),
        "bridge_summary": _records(bridge_summary),
        "bridge_top_contributors": _records(bridge_detail.head(30)),
        "bridge_atlantico": _records(atlantic),
        "atlantico_profile": atlantico_profile,
        "atlantico_history": atlantico_history,
        "provider_concentration": provider_concentration,
        "provider_concentration_history": provider_concentration_history,
        "provider_historical_ranking": _records(provider_historical_ranking),
        "market_share": _records(market),
        "market_share_top10_fixed": _records(fixed_top10),
        "market_share_scope_summary": _records(market_scope),
        "market_share_exclusions": [
            {"cnpj": cnpj, "fund": name}
            for cnpj, name in MARKET_SHARE_EXCLUDED_FUNDS.items()
        ],
        "acquiring_taxonomy": acquiring_taxonomy,
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
