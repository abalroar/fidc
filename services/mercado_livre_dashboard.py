from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill, Side, Border
from openpyxl.utils import get_column_letter


PT_MONTH_ABBR = {
    1: "jan",
    2: "fev",
    3: "mar",
    4: "abr",
    5: "mai",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "set",
    10: "out",
    11: "nov",
    12: "dez",
}

MONEY_COLUMNS = [
    "pl_total",
    "pl_senior",
    "pl_subordinada_strict",
    "pl_mezzanino",
    "pl_subordinada_mezz",
    "carteira_bruta",
    "pdd_total",
    "carteira_liquida",
    "carteira_em_dia",
    "atraso_ate30",
    "atraso_31_60",
    "atraso_61_90",
    "atraso_91_180",
    "atraso_181_360",
    "vencidos_360",
    "npl_over1",
    "npl_over30",
    "npl_over60",
    "npl_over90",
    "npl_over180",
    "npl_over360",
    "carteira_ex360",
    "pdd_ex360",
    "carteira_liquida_ex360",
    "npl_over1_ex360",
    "npl_over30_ex360",
    "npl_over60_ex360",
    "npl_over90_ex360",
    "npl_over180_ex360",
    "carteira_em_dia_mais_ate30",
]

PRIMITIVE_SUM_COLUMNS = [
    "pl_total",
    "pl_senior",
    "pl_subordinada_strict",
    "pl_mezzanino",
    "carteira_bruta",
    "pdd_total",
    "atraso_ate30",
    "atraso_31_60",
    "atraso_61_90",
    "atraso_91_120",
    "atraso_121_150",
    "atraso_151_180",
    "atraso_181_360",
    "atraso_361_720",
    "atraso_721_1080",
    "atraso_1080",
]

WIDE_TABLE_COLUMNS = ["Bloco", "Métrica", "Memória / fórmula"]


@dataclass(frozen=True)
class MercadoLivreOutputs:
    fund_monthly: dict[str, pd.DataFrame]
    fund_wide: dict[str, pd.DataFrame]
    consolidated_monthly: pd.DataFrame
    consolidated_wide: pd.DataFrame
    warnings_df: pd.DataFrame
    metadata: dict[str, Any]


def build_mercado_livre_outputs(
    *,
    portfolio_id: str,
    portfolio_name: str,
    dashboards_by_cnpj: dict[str, tuple[str, Any]],
    period_label: str,
) -> MercadoLivreOutputs:
    fund_monthly: dict[str, pd.DataFrame] = {}
    fund_wide: dict[str, pd.DataFrame] = {}
    warnings: list[dict[str, object]] = []
    for cnpj, (fund_name, dashboard) in dashboards_by_cnpj.items():
        monthly = build_fund_monthly_base(cnpj=cnpj, fund_name=fund_name, dashboard=dashboard)
        fund_monthly[cnpj] = monthly
        fund_wide[cnpj] = build_wide_table(monthly, scope_name=fund_name)
        warnings.extend(_warning_rows(monthly, scope_name=fund_name, cnpj=cnpj))

    consolidated = build_consolidated_monthly_base(
        portfolio_name=portfolio_name,
        fund_monthly_frames=fund_monthly,
    )
    consolidated_wide = build_wide_table(consolidated, scope_name=portfolio_name)
    warnings.extend(_warning_rows(consolidated, scope_name=portfolio_name, cnpj="CONSOLIDADO"))
    metadata = {
        "schema_version": 1,
        "generated_at": _utc_now_iso(),
        "portfolio_id": portfolio_id,
        "portfolio_name": portfolio_name,
        "period_label": period_label,
        "funds": [
            {
                "cnpj": cnpj,
                "name": fund_name,
                "competencias": _competencia_list(frame),
            }
            for cnpj, (fund_name, _dashboard) in dashboards_by_cnpj.items()
            for frame in [fund_monthly.get(cnpj, pd.DataFrame())]
        ],
        "formulas": _formula_catalog(),
        "known_limitations": [
            "O XML padrao analisado possui buckets de atraso acima de 360 dias, mas nao possui PDD segmentado por faixa de atraso.",
            "A visao Ex Over 360 usa PDD total contra NPL ex-360 quando solicitado; PDD Ex Over 360 fica nao calculavel sem alocacao aprovada.",
            "PL FIDC total usa a soma das classes de cotas calculadas por quantidade de cotas vezes valor da cota, preservando a logica atual do dashboard.",
            "Carteira Bruta usa a base canonica de direitos crediticios do dashboard, nao o campo amplo APLIC_ATIVO/VL_CARTEIRA.",
        ],
    }
    return MercadoLivreOutputs(
        fund_monthly=fund_monthly,
        fund_wide=fund_wide,
        consolidated_monthly=consolidated,
        consolidated_wide=consolidated_wide,
        warnings_df=pd.DataFrame(warnings),
        metadata=metadata,
    )


def build_fund_monthly_base(*, cnpj: str, fund_name: str, dashboard: Any) -> pd.DataFrame:
    competencias = list(getattr(dashboard, "competencias", []) or [])
    rows: list[dict[str, object]] = []
    info = getattr(dashboard, "fund_info", {}) or {}
    for competencia in competencias:
        row: dict[str, object] = {
            "scope": "individual",
            "fund_name": fund_name or info.get("nome_fundo") or cnpj,
            "cnpj": _digits(cnpj or info.get("cnpj_fundo")),
            "tipo_classe": _first_non_empty(info.get("nome_classe"), info.get("fundo_ou_classe")),
            "competencia": competencia,
            "competencia_dt": _competencia_to_timestamp(competencia),
        }
        row.update(_subordination_values(getattr(dashboard, "subordination_history_df", pd.DataFrame()), competencia))
        row.update(_credit_values(dashboard, competencia))
        row.update(_bucket_values(getattr(dashboard, "default_buckets_history_df", pd.DataFrame()), competencia))
        rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return _empty_monthly_frame()
    frame = frame.sort_values("competencia_dt").reset_index(drop=True)
    return _decorate_monthly_base(frame, expected_funds=1)


def build_consolidated_monthly_base(
    *,
    portfolio_name: str,
    fund_monthly_frames: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    valid_frames = [
        frame.copy()
        for frame in fund_monthly_frames.values()
        if isinstance(frame, pd.DataFrame) and not frame.empty
    ]
    if not valid_frames:
        return _empty_monthly_frame()
    combined = pd.concat(valid_frames, ignore_index=True, sort=False)
    rows: list[dict[str, object]] = []
    expected_funds = len(valid_frames)
    for competencia, group in combined.groupby("competencia", dropna=False):
        row: dict[str, object] = {
            "scope": "consolidado",
            "fund_name": portfolio_name,
            "cnpj": "CONSOLIDADO",
            "tipo_classe": "Carteira consolidada",
            "competencia": competencia,
            "competencia_dt": _competencia_to_timestamp(competencia),
            "funds_expected_count": expected_funds,
            "funds_present_count": int(group["cnpj"].nunique()) if "cnpj" in group.columns else len(group),
        }
        for column in PRIMITIVE_SUM_COLUMNS:
            row[column] = _sum_numeric(group.get(column))
        rows.append(row)
    frame = pd.DataFrame(rows).sort_values("competencia_dt").reset_index(drop=True)
    return _decorate_monthly_base(frame, expected_funds=expected_funds)


def build_wide_table(monthly_df: pd.DataFrame, *, scope_name: str) -> pd.DataFrame:
    if monthly_df.empty:
        return pd.DataFrame(columns=WIDE_TABLE_COLUMNS)
    sorted_df = monthly_df.sort_values("competencia_dt").reset_index(drop=True)
    competencias = sorted_df["competencia"].astype(str).tolist()
    display_competencias = [_format_competencia_short(value) for value in competencias]
    block_scales = _money_scales_by_block(sorted_df)
    metric_specs = _wide_metric_specs()
    rows: list[dict[str, object]] = []
    for spec in metric_specs:
        values = []
        for _, item in sorted_df.iterrows():
            values.append(_format_wide_value(item.get(spec["column"]), unit=str(spec["unit"]), scale=block_scales.get(str(spec["block"]))))
        rows.append(
            {
                "Bloco": spec["block"],
                "Métrica": spec["metric"],
                "Memória / fórmula": spec["formula"],
                **dict(zip(display_competencias, values, strict=False)),
            }
        )
    output = pd.DataFrame(rows)
    output.attrs["scope_name"] = scope_name
    output.attrs["competencias"] = competencias
    return output


def build_validation_table(outputs: MercadoLivreOutputs) -> pd.DataFrame:
    frames = list(outputs.fund_monthly.values())
    if not outputs.consolidated_monthly.empty:
        frames.append(outputs.consolidated_monthly)
    if not frames:
        return pd.DataFrame()
    columns = [
        "fund_name",
        "cnpj",
        "competencia",
        "pl_total",
        "pl_senior",
        "pl_subordinada_mezz",
        "subordinacao_total_pct",
        "carteira_bruta",
        "pdd_total",
        "npl_over90",
        "npl_over360",
        "npl_over90_ex360",
        "carteira_ex360",
        "pdd_npl_over90_pct",
        "pdd_npl_over90_ex360_pct",
        "warnings",
    ]
    combined = pd.concat(frames, ignore_index=True, sort=False)
    available = [column for column in columns if column in combined.columns]
    return combined[available].sort_values(["fund_name", "competencia"]).reset_index(drop=True)


def save_outputs_to_cache(
    outputs: MercadoLivreOutputs,
    *,
    portfolio_id: str,
    period_key: str,
    base_dir: Path | str = ".cache/mercado-livre",
) -> Path:
    root = Path(base_dir) / _safe_path_token(portfolio_id) / _safe_path_token(period_key)
    root.mkdir(parents=True, exist_ok=True)
    for cnpj, frame in outputs.fund_monthly.items():
        frame.to_csv(root / f"monthly_{_safe_path_token(cnpj)}.csv", index=False)
    for cnpj, frame in outputs.fund_wide.items():
        frame.to_csv(root / f"wide_{_safe_path_token(cnpj)}.csv", index=False)
    outputs.consolidated_monthly.to_csv(root / "monthly_consolidado.csv", index=False)
    outputs.consolidated_wide.to_csv(root / "wide_consolidado.csv", index=False)
    outputs.warnings_df.to_csv(root / "warnings.csv", index=False)
    (root / "metadata.json").write_text(json.dumps(outputs.metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def build_excel_export_bytes(outputs: MercadoLivreOutputs) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for cnpj, table in outputs.fund_wide.items():
            sheet_name = _excel_sheet_name(_sheet_name_from_table(table, fallback=cnpj))
            table.to_excel(writer, sheet_name=sheet_name, index=False)
            _style_wide_sheet(writer.book[sheet_name], table)
        outputs.consolidated_wide.to_excel(writer, sheet_name="Consolidado", index=False)
        _style_wide_sheet(writer.book["Consolidado"], outputs.consolidated_wide)
        validation = build_validation_table(outputs)
        validation.to_excel(writer, sheet_name="Auditoria", index=False)
        _style_plain_sheet(writer.book["Auditoria"])
        outputs.warnings_df.to_excel(writer, sheet_name="Warnings", index=False)
        _style_plain_sheet(writer.book["Warnings"])
        metadata_df = pd.DataFrame(
            [{"chave": key, "valor": json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value} for key, value in outputs.metadata.items()]
        )
        metadata_df.to_excel(writer, sheet_name="Metadados", index=False)
        _style_plain_sheet(writer.book["Metadados"])
    return buffer.getvalue()


def _subordination_values(frame: pd.DataFrame, competencia: str) -> dict[str, object]:
    row = _latest_match(frame, competencia)
    return {
        "pl_total": _num(row.get("pl_total")),
        "pl_senior": _num(row.get("pl_senior")),
        "pl_mezzanino": _num(row.get("pl_mezzanino")),
        "pl_subordinada_strict": _num(row.get("pl_subordinada_strict")),
        "pl_subordinada_mezz": _num(row.get("pl_subordinada")),
    }


def _credit_values(dashboard: Any, competencia: str) -> dict[str, object]:
    default_row = _latest_match(getattr(dashboard, "default_history_df", pd.DataFrame()), competencia)
    dc_row = _latest_match(getattr(dashboard, "dc_canonical_history_df", pd.DataFrame()), competencia)
    return {
        "carteira_bruta": _num(default_row.get("direitos_creditorios")) or _num(dc_row.get("dc_total_canonico")),
        "carteira_bruta_origem": _first_non_empty(default_row.get("direitos_creditorios_fonte"), dc_row.get("dc_total_fonte_efetiva")),
        "pdd_total": _num(default_row.get("provisao_total")),
    }


def _bucket_values(frame: pd.DataFrame, competencia: str) -> dict[str, object]:
    subset = frame[frame["competencia"].astype(str) == str(competencia)].copy() if isinstance(frame, pd.DataFrame) and not frame.empty and "competencia" in frame.columns else pd.DataFrame()
    values = {int(row.get("ordem")): _num(row.get("valor")) for _, row in subset.iterrows() if pd.notna(row.get("ordem"))}
    return {
        "atraso_ate30": values.get(1),
        "atraso_31_60": values.get(2),
        "atraso_61_90": values.get(3),
        "atraso_91_120": values.get(4),
        "atraso_121_150": values.get(5),
        "atraso_151_180": values.get(6),
        "atraso_181_360": values.get(7),
        "atraso_361_720": values.get(8),
        "atraso_721_1080": values.get(9),
        "atraso_1080": values.get(10),
    }


def _decorate_monthly_base(frame: pd.DataFrame, *, expected_funds: int) -> pd.DataFrame:
    df = frame.copy()
    for column in PRIMITIVE_SUM_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
        df[column] = pd.to_numeric(df[column], errors="coerce")
    if "funds_expected_count" not in df.columns:
        df["funds_expected_count"] = expected_funds
    if "funds_present_count" not in df.columns:
        df["funds_present_count"] = 1
    df["pl_subordinada_mezz"] = _coalesce_numeric(df["pl_subordinada_mezz"] if "pl_subordinada_mezz" in df.columns else pd.Series(pd.NA, index=df.index), df["pl_subordinada_strict"].fillna(0.0) + df["pl_mezzanino"].fillna(0.0))
    df["subordinacao_total_pct"] = _safe_div_pct(df["pl_subordinada_mezz"], df["pl_total"])
    df["pdd_carteira_bruta_pct"] = _safe_div_pct(df["pdd_total"], df["carteira_bruta"])
    df["carteira_liquida"] = df["carteira_bruta"] - df["pdd_total"]
    df["atraso_91_180"] = df[["atraso_91_120", "atraso_121_150", "atraso_151_180"]].sum(axis=1, min_count=1)
    df["vencidos_360"] = df[["atraso_361_720", "atraso_721_1080", "atraso_1080"]].sum(axis=1, min_count=1)
    df["npl_over1"] = df[["atraso_ate30", "atraso_31_60", "atraso_61_90", "atraso_91_120", "atraso_121_150", "atraso_151_180", "atraso_181_360", "atraso_361_720", "atraso_721_1080", "atraso_1080"]].sum(axis=1, min_count=1)
    df["npl_over30"] = df[["atraso_31_60", "atraso_61_90", "atraso_91_120", "atraso_121_150", "atraso_151_180", "atraso_181_360", "atraso_361_720", "atraso_721_1080", "atraso_1080"]].sum(axis=1, min_count=1)
    df["npl_over60"] = df[["atraso_61_90", "atraso_91_120", "atraso_121_150", "atraso_151_180", "atraso_181_360", "atraso_361_720", "atraso_721_1080", "atraso_1080"]].sum(axis=1, min_count=1)
    df["npl_over90"] = df[["atraso_91_120", "atraso_121_150", "atraso_151_180", "atraso_181_360", "atraso_361_720", "atraso_721_1080", "atraso_1080"]].sum(axis=1, min_count=1)
    df["npl_over180"] = df[["atraso_181_360", "atraso_361_720", "atraso_721_1080", "atraso_1080"]].sum(axis=1, min_count=1)
    df["npl_over360"] = df["vencidos_360"]
    df["carteira_em_dia"] = df["carteira_bruta"] - df["npl_over1"]
    df["carteira_ex360"] = df["carteira_bruta"] - df["npl_over360"]
    df["pdd_ex360"] = pd.NA
    df["pdd_ex360_calculavel"] = False
    df["pdd_ex360_carteira_ex360_pct"] = pd.NA
    df["carteira_liquida_ex360"] = pd.NA
    df["npl_over1_ex360"] = (df["npl_over1"] - df["npl_over360"]).clip(lower=0.0)
    df["npl_over30_ex360"] = (df["npl_over30"] - df["npl_over360"]).clip(lower=0.0)
    df["npl_over60_ex360"] = (df["npl_over60"] - df["npl_over360"]).clip(lower=0.0)
    df["npl_over90_ex360"] = (df["npl_over90"] - df["npl_over360"]).clip(lower=0.0)
    df["npl_over180_ex360"] = (df["npl_over180"] - df["npl_over360"]).clip(lower=0.0)
    df["npl_over1_pct"] = _safe_div_pct(df["npl_over1"], df["carteira_bruta"])
    df["npl_over30_pct"] = _safe_div_pct(df["npl_over30"], df["carteira_bruta"])
    df["npl_over60_pct"] = _safe_div_pct(df["npl_over60"], df["carteira_bruta"])
    df["npl_over90_pct"] = _safe_div_pct(df["npl_over90"], df["carteira_bruta"])
    df["npl_over180_pct"] = _safe_div_pct(df["npl_over180"], df["carteira_bruta"])
    df["npl_over360_pct"] = _safe_div_pct(df["npl_over360"], df["carteira_bruta"])
    df["npl_over1_ex360_pct"] = _safe_div_pct(df["npl_over1_ex360"], df["carteira_ex360"])
    df["npl_over30_ex360_pct"] = _safe_div_pct(df["npl_over30_ex360"], df["carteira_ex360"])
    df["npl_over60_ex360_pct"] = _safe_div_pct(df["npl_over60_ex360"], df["carteira_ex360"])
    df["npl_over90_ex360_pct"] = _safe_div_pct(df["npl_over90_ex360"], df["carteira_ex360"])
    df["npl_over180_ex360_pct"] = _safe_div_pct(df["npl_over180_ex360"], df["carteira_ex360"])
    df["pdd_npl_over1_pct"] = _safe_div_pct(df["pdd_total"], df["npl_over1"])
    df["pdd_npl_over30_pct"] = _safe_div_pct(df["pdd_total"], df["npl_over30"])
    df["pdd_npl_over60_pct"] = _safe_div_pct(df["pdd_total"], df["npl_over60"])
    df["pdd_npl_over90_pct"] = _safe_div_pct(df["pdd_total"], df["npl_over90"])
    df["pdd_npl_over180_pct"] = _safe_div_pct(df["pdd_total"], df["npl_over180"])
    df["pdd_npl_over360_pct"] = _safe_div_pct(df["pdd_total"], df["npl_over360"])
    df["pdd_npl_over90_ex360_pct"] = _safe_div_pct(df["pdd_total"], df["npl_over90_ex360"])
    df["carteira_em_dia_mais_ate30"] = df["carteira_em_dia"] + df["atraso_ate30"]
    df["roll_rate_31_60_pct"] = _safe_div_pct(df["atraso_31_60"], df["carteira_em_dia_mais_ate30"])
    df["missing_data_flag"] = df[["pl_total", "pl_senior", "pl_subordinada_mezz", "carteira_bruta", "pdd_total", "npl_over90"]].isna().any(axis=1)
    df["division_by_zero_flag"] = (
        (pd.to_numeric(df["pl_total"], errors="coerce").fillna(0) <= 0)
        | (pd.to_numeric(df["carteira_bruta"], errors="coerce").fillna(0) <= 0)
    )
    df["negative_value_flag"] = df[[column for column in MONEY_COLUMNS if column in df.columns]].lt(0).any(axis=1)
    df["not_calculable_flag"] = df["pdd_ex360_calculavel"].eq(False)
    df["warnings"] = df.apply(_row_warnings, axis=1)
    df["serie_inicio"] = _format_competencia_short(df["competencia"].iloc[0]) if not df.empty else ""
    df["periodo_inicial"] = _format_competencia_short(df["competencia"].iloc[0]) if not df.empty else ""
    df["periodo_final"] = _format_competencia_short(df["competencia"].iloc[-1]) if not df.empty else ""
    df["competencias_disponiveis"] = len(df)
    return df


def _wide_metric_specs() -> list[dict[str, str]]:
    return [
        {"block": "1. Identificação do FIDC", "metric": "Nome do fundo", "column": "fund_name", "unit": "text", "formula": "Nome resolvido do documento/carteira salva."},
        {"block": "1. Identificação do FIDC", "metric": "CNPJ", "column": "cnpj", "unit": "text", "formula": "CNPJ normalizado."},
        {"block": "1. Identificação do FIDC", "metric": "Início da série", "column": "serie_inicio", "unit": "text", "formula": "Primeira competência disponível."},
        {"block": "1. Identificação do FIDC", "metric": "Tipo/classe", "column": "tipo_classe", "unit": "text", "formula": "Classe reportada no cabeçalho, quando existir."},
        {"block": "1. Identificação do FIDC", "metric": "Período inicial", "column": "periodo_inicial", "unit": "text", "formula": "Primeira competência carregada."},
        {"block": "1. Identificação do FIDC", "metric": "Período final", "column": "periodo_final", "unit": "text", "formula": "Última competência carregada."},
        {"block": "1. Identificação do FIDC", "metric": "Quantidade de competências disponíveis", "column": "competencias_disponiveis", "unit": "count", "formula": "Contagem de competências na base mensal."},
        {"block": "1. Identificação do FIDC", "metric": "Warnings de dados faltantes", "column": "warnings", "unit": "text", "formula": "Alertas gerados pela base canônica."},
        {"block": "2. PL FIDC", "metric": "PL FIDC total", "column": "pl_total", "unit": "money", "formula": "Soma do PL das classes por quantidade de cotas × valor da cota."},
        {"block": "2. PL FIDC", "metric": "PL Sênior", "column": "pl_senior", "unit": "money", "formula": "PL da classe sênior."},
        {"block": "2. PL FIDC", "metric": "PL Subordinada", "column": "pl_subordinada_strict", "unit": "money", "formula": "PL subordinado estrito, sem mezanino."},
        {"block": "2. PL FIDC", "metric": "PL Mezanino", "column": "pl_mezzanino", "unit": "money", "formula": "PL classificado como mezanino quando aplicável."},
        {"block": "2. PL FIDC", "metric": "Subordinada + Mezanino", "column": "pl_subordinada_mezz", "unit": "money", "formula": "PL subordinada + PL mezanino."},
        {"block": "2. PL FIDC", "metric": "% Subordinação Total", "column": "subordinacao_total_pct", "unit": "percent", "formula": "(Subordinada + Mezanino) / PL FIDC total."},
        {"block": "3. Carteira Bruta", "metric": "Carteira Bruta total", "column": "carteira_bruta", "unit": "money", "formula": "Base canônica de direitos creditórios."},
        {"block": "3. Carteira Bruta", "metric": "PDD total", "column": "pdd_total", "unit": "money", "formula": "Provisão total reportada."},
        {"block": "3. Carteira Bruta", "metric": "PDD / Carteira Bruta", "column": "pdd_carteira_bruta_pct", "unit": "percent", "formula": "PDD total / Carteira Bruta total."},
        {"block": "3. Carteira Bruta", "metric": "Carteira Líquida", "column": "carteira_liquida", "unit": "money", "formula": "Carteira Bruta total - PDD total."},
        {"block": "4. Aging / faixas de atraso", "metric": "Carteira em dia", "column": "carteira_em_dia", "unit": "money", "formula": "Carteira Bruta - NPL Over 1d."},
        {"block": "4. Aging / faixas de atraso", "metric": "Atrasada até 30 dias", "column": "atraso_ate30", "unit": "money", "formula": "Bucket VL_INAD_VENC_30."},
        {"block": "4. Aging / faixas de atraso", "metric": "Atrasos 31-60 dias", "column": "atraso_31_60", "unit": "money", "formula": "Bucket VL_INAD_VENC_31_60."},
        {"block": "4. Aging / faixas de atraso", "metric": "Atrasos 61-90 dias", "column": "atraso_61_90", "unit": "money", "formula": "Bucket VL_INAD_VENC_61_90."},
        {"block": "4. Aging / faixas de atraso", "metric": "Atrasos 91-180 dias", "column": "atraso_91_180", "unit": "money", "formula": "Soma dos buckets 91-120, 121-150 e 151-180."},
        {"block": "4. Aging / faixas de atraso", "metric": "Atrasos 181-360 dias", "column": "atraso_181_360", "unit": "money", "formula": "Bucket VL_INAD_VENC_181_360."},
        {"block": "4. Aging / faixas de atraso", "metric": "Vencidos acima de 360 dias", "column": "vencidos_360", "unit": "money", "formula": "Soma dos buckets 361-720, 721-1080 e acima de 1080 dias."},
        {"block": "5. NPL Over acumulado", "metric": "NPL Over 1d", "column": "npl_over1", "unit": "money", "formula": "Soma dos buckets de atraso >= 1 dia."},
        {"block": "5. NPL Over acumulado", "metric": "NPL Over 1d / Carteira", "column": "npl_over1_pct", "unit": "percent", "formula": "NPL Over 1d / Carteira Bruta."},
        {"block": "5. NPL Over acumulado", "metric": "NPL Over 30d", "column": "npl_over30", "unit": "money", "formula": "Soma dos buckets >= 31 dias."},
        {"block": "5. NPL Over acumulado", "metric": "NPL Over 30d / Carteira", "column": "npl_over30_pct", "unit": "percent", "formula": "NPL Over 30d / Carteira Bruta."},
        {"block": "5. NPL Over acumulado", "metric": "NPL Over 60d", "column": "npl_over60", "unit": "money", "formula": "Soma dos buckets >= 61 dias."},
        {"block": "5. NPL Over acumulado", "metric": "NPL Over 60d / Carteira", "column": "npl_over60_pct", "unit": "percent", "formula": "NPL Over 60d / Carteira Bruta."},
        {"block": "5. NPL Over acumulado", "metric": "NPL Over 90d", "column": "npl_over90", "unit": "money", "formula": "Soma dos buckets >= 91 dias."},
        {"block": "5. NPL Over acumulado", "metric": "NPL Over 90d / Carteira", "column": "npl_over90_pct", "unit": "percent", "formula": "NPL Over 90d / Carteira Bruta."},
        {"block": "5. NPL Over acumulado", "metric": "NPL Over 180d", "column": "npl_over180", "unit": "money", "formula": "Soma dos buckets >= 181 dias."},
        {"block": "5. NPL Over acumulado", "metric": "NPL Over 180d / Carteira", "column": "npl_over180_pct", "unit": "percent", "formula": "NPL Over 180d / Carteira Bruta."},
        {"block": "5. NPL Over acumulado", "metric": "NPL Over 360d", "column": "npl_over360", "unit": "money", "formula": "Vencidos acima de 360 dias."},
        {"block": "5. NPL Over acumulado", "metric": "NPL Over 360d / Carteira", "column": "npl_over360_pct", "unit": "percent", "formula": "NPL Over 360d / Carteira Bruta."},
        {"block": "6. Cobertura", "metric": "PDD / NPL Over 1d", "column": "pdd_npl_over1_pct", "unit": "percent", "formula": "PDD total / NPL Over 1d."},
        {"block": "6. Cobertura", "metric": "PDD / NPL Over 30d", "column": "pdd_npl_over30_pct", "unit": "percent", "formula": "PDD total / NPL Over 30d."},
        {"block": "6. Cobertura", "metric": "PDD / NPL Over 60d", "column": "pdd_npl_over60_pct", "unit": "percent", "formula": "PDD total / NPL Over 60d."},
        {"block": "6. Cobertura", "metric": "PDD / NPL Over 90d", "column": "pdd_npl_over90_pct", "unit": "percent", "formula": "PDD total / NPL Over 90d."},
        {"block": "6. Cobertura", "metric": "PDD / NPL Over 180d", "column": "pdd_npl_over180_pct", "unit": "percent", "formula": "PDD total / NPL Over 180d."},
        {"block": "6. Cobertura", "metric": "PDD / NPL Over 360d", "column": "pdd_npl_over360_pct", "unit": "percent", "formula": "PDD total / NPL Over 360d, quando denominador > 0."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "Carteira Ex Over 360d", "column": "carteira_ex360", "unit": "money", "formula": "Carteira Bruta - NPL Over 360d."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "PDD Ex Over 360d", "column": "pdd_ex360", "unit": "money", "formula": "Não calculável sem PDD segmentado por faixa."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "PDD Ex Over 360d / Carteira Ex Over 360d", "column": "pdd_ex360_carteira_ex360_pct", "unit": "percent", "formula": "Não calculável sem PDD segmentado por faixa."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "Carteira Líquida Ex Over 360d", "column": "carteira_liquida_ex360", "unit": "money", "formula": "Não calculável sem PDD segmentado por faixa."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "NPL Over 1d Ex 360", "column": "npl_over1_ex360", "unit": "money", "formula": "NPL Over 1d - NPL Over 360d."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "NPL Over 1d Ex 360 / Carteira Ex 360", "column": "npl_over1_ex360_pct", "unit": "percent", "formula": "NPL Over 1d Ex 360 / Carteira Ex 360."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "NPL Over 30d Ex 360", "column": "npl_over30_ex360", "unit": "money", "formula": "NPL Over 30d - NPL Over 360d."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "NPL Over 30d Ex 360 / Carteira Ex 360", "column": "npl_over30_ex360_pct", "unit": "percent", "formula": "NPL Over 30d Ex 360 / Carteira Ex 360."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "NPL Over 60d Ex 360", "column": "npl_over60_ex360", "unit": "money", "formula": "NPL Over 60d - NPL Over 360d."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "NPL Over 60d Ex 360 / Carteira Ex 360", "column": "npl_over60_ex360_pct", "unit": "percent", "formula": "NPL Over 60d Ex 360 / Carteira Ex 360."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "NPL Over 90d Ex 360", "column": "npl_over90_ex360", "unit": "money", "formula": "NPL Over 90d - NPL Over 360d."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "NPL Over 90d Ex 360 / Carteira Ex 360", "column": "npl_over90_ex360_pct", "unit": "percent", "formula": "NPL Over 90d Ex 360 / Carteira Ex 360."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "NPL Over 180d Ex 360", "column": "npl_over180_ex360", "unit": "money", "formula": "NPL Over 180d - NPL Over 360d."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "NPL Over 180d Ex 360 / Carteira Ex 360", "column": "npl_over180_ex360_pct", "unit": "percent", "formula": "NPL Over 180d Ex 360 / Carteira Ex 360."},
        {"block": "7. Visão Ex-Vencidos > 360d", "metric": "PDD / NPL Over 90d Ex 360", "column": "pdd_npl_over90_ex360_pct", "unit": "percent", "formula": "PDD total / NPL Over 90d Ex 360; sem alocação de PDD por faixa."},
        {"block": "8. Roll Rate / fluxo de deterioração", "metric": "Carteira em dia + atrasada até 30d", "column": "carteira_em_dia_mais_ate30", "unit": "money", "formula": "Carteira em dia + atrasada até 30 dias."},
        {"block": "8. Roll Rate / fluxo de deterioração", "metric": "Atrasos 31-60d", "column": "atraso_31_60", "unit": "money", "formula": "Bucket 31-60 dias."},
        {"block": "8. Roll Rate / fluxo de deterioração", "metric": "Roll Rate", "column": "roll_rate_31_60_pct", "unit": "percent", "formula": "Atrasos 31-60d / (Carteira em dia + atrasada até 30d)."},
        {"block": "9. Campos auxiliares de auditoria", "metric": "Numerador % Subordinação Total", "column": "pl_subordinada_mezz", "unit": "money", "formula": "Subordinada + Mezanino."},
        {"block": "9. Campos auxiliares de auditoria", "metric": "Denominador % Subordinação Total", "column": "pl_total", "unit": "money", "formula": "PL FIDC total."},
        {"block": "9. Campos auxiliares de auditoria", "metric": "Numerador NPL Over 90d / Carteira", "column": "npl_over90", "unit": "money", "formula": "NPL Over 90d."},
        {"block": "9. Campos auxiliares de auditoria", "metric": "Denominador NPL Over 90d / Carteira", "column": "carteira_bruta", "unit": "money", "formula": "Carteira Bruta total."},
        {"block": "9. Campos auxiliares de auditoria", "metric": "Fórmula aplicada NPL Over 90d", "column": "formula_npl_over90", "unit": "text", "formula": "Texto fixo da fórmula aplicada."},
        {"block": "9. Campos auxiliares de auditoria", "metric": "Origem da coluna Carteira Bruta", "column": "carteira_bruta_origem", "unit": "text", "formula": "Fonte efetiva selecionada pela base canônica."},
        {"block": "9. Campos auxiliares de auditoria", "metric": "Flag de dado ausente", "column": "missing_data_flag", "unit": "bool", "formula": "Verdadeiro quando campo crítico está ausente."},
        {"block": "9. Campos auxiliares de auditoria", "metric": "Flag de divisão por zero", "column": "division_by_zero_flag", "unit": "bool", "formula": "Verdadeiro quando denominador crítico é zero/ausente."},
        {"block": "9. Campos auxiliares de auditoria", "metric": "Flag de valor negativo", "column": "negative_value_flag", "unit": "bool", "formula": "Verdadeiro quando valor monetário crítico é negativo."},
        {"block": "9. Campos auxiliares de auditoria", "metric": "Flag de métrica não calculável", "column": "not_calculable_flag", "unit": "bool", "formula": "Verdadeiro para métricas sem base tecnicamente calculável, como PDD ex-360."},
        {"block": "9. Campos auxiliares de auditoria", "metric": "Observação técnica", "column": "warnings", "unit": "text", "formula": "Resumo dos warnings da competência."},
    ]


def _money_scales_by_block(df: pd.DataFrame) -> dict[str, tuple[float, str]]:
    specs = _wide_metric_specs()
    result: dict[str, tuple[float, str]] = {}
    for block in sorted({spec["block"] for spec in specs}):
        cols = [spec["column"] for spec in specs if spec["block"] == block and spec["unit"] == "money"]
        values = []
        for col in cols:
            if col in df.columns:
                values.extend(pd.to_numeric(df[col], errors="coerce").dropna().abs().tolist())
        result[block] = _money_scale(values)
    return result


def _money_scale(values: list[float]) -> tuple[float, str]:
    max_value = max(values) if values else 0.0
    if max_value >= 1_000_000_000:
        return 1_000_000_000.0, "R$ bi"
    if max_value >= 1_000_000:
        return 1_000_000.0, "R$ mm"
    if max_value >= 1_000:
        return 1_000.0, "R$ mil"
    return 1.0, "R$"


def _format_wide_value(value: object, *, unit: str, scale: tuple[float, str] | None = None) -> str:
    if unit == "money":
        divisor, label = scale or (1.0, "R$")
        numeric = _num(value)
        if numeric is None:
            return "N/D"
        if label == "R$":
            return f"R$ {_format_decimal(numeric, 2)}"
        return f"{label} {_format_decimal(numeric / divisor, 2)}"
    if unit == "percent":
        numeric = _num(value)
        return "N/D" if numeric is None else f"{_format_decimal(numeric, 2)}%"
    if unit == "count":
        numeric = _num(value)
        return "N/D" if numeric is None else _format_decimal(numeric, 0)
    if unit == "bool":
        if pd.isna(value):
            return "N/D"
        return "Sim" if bool(value) else "Não"
    if pd.isna(value):
        return "N/D"
    return str(value)


def _format_decimal(value: object, decimals: int = 2) -> str:
    numeric = float(value)
    formatted = f"{numeric:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _safe_div_pct(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    return (num / den).where(den > 0).mul(100.0)


def _coalesce_numeric(primary: pd.Series, fallback: pd.Series) -> pd.Series:
    primary_num = pd.to_numeric(primary, errors="coerce")
    fallback_num = pd.to_numeric(fallback, errors="coerce")
    return primary_num.where(primary_num.notna(), fallback_num)


def _latest_match(frame: pd.DataFrame, competencia: str) -> pd.Series:
    if not isinstance(frame, pd.DataFrame) or frame.empty or "competencia" not in frame.columns:
        return pd.Series(dtype="object")
    match = frame[frame["competencia"].astype(str) == str(competencia)]
    if match.empty:
        return pd.Series(dtype="object")
    return match.iloc[-1]


def _num(value: object) -> float | None:
    try:
        parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    except Exception:  # noqa: BLE001
        return None
    if pd.isna(parsed):
        return None
    return float(parsed)


def _sum_numeric(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    values = pd.to_numeric(series, errors="coerce")
    if values.notna().sum() == 0:
        return None
    return float(values.sum(skipna=True))


def _digits(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _first_non_empty(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() not in {"nan", "none", "n/d", "<na>"}:
            return text
    return "N/D"


def _competencia_to_timestamp(value: object) -> pd.Timestamp:
    raw = str(value or "").strip()
    if re.fullmatch(r"\d{1,2}/\d{4}", raw):
        month, year = raw.split("/", 1)
        return pd.Timestamp(year=int(year), month=int(month), day=1)
    parsed = pd.to_datetime(raw, errors="coerce")
    return parsed if pd.notna(parsed) else pd.NaT


def _format_competencia_short(value: object) -> str:
    ts = _competencia_to_timestamp(value)
    if pd.isna(ts):
        return str(value or "N/D")
    return f"{PT_MONTH_ABBR[int(ts.month)]}/{str(int(ts.year))[-2:]}"


def _competencia_list(frame: pd.DataFrame) -> list[str]:
    if frame.empty or "competencia" not in frame.columns:
        return []
    return frame["competencia"].astype(str).tolist()


def _row_warnings(row: pd.Series) -> str:
    warnings: list[str] = []
    if bool(row.get("missing_data_flag")):
        warnings.append("dado crítico ausente")
    if bool(row.get("division_by_zero_flag")):
        warnings.append("denominador zero/ausente")
    if bool(row.get("negative_value_flag")):
        warnings.append("valor monetário negativo")
    if not bool(row.get("pdd_ex360_calculavel")):
        warnings.append("PDD ex-360 não calculável sem PDD por faixa")
    if int(row.get("funds_present_count") or 0) < int(row.get("funds_expected_count") or 0):
        warnings.append("consolidado parcial na competência")
    return "; ".join(warnings)


def _warning_rows(monthly_df: pd.DataFrame, *, scope_name: str, cnpj: str) -> list[dict[str, object]]:
    if monthly_df.empty:
        return [{"scope_name": scope_name, "cnpj": cnpj, "competencia": "", "warning": "base vazia"}]
    rows: list[dict[str, object]] = []
    for _, row in monthly_df.iterrows():
        warning = str(row.get("warnings") or "").strip()
        if warning:
            rows.append(
                {
                    "scope_name": scope_name,
                    "cnpj": cnpj,
                    "competencia": row.get("competencia"),
                    "warning": warning,
                }
            )
    return rows


def _formula_catalog() -> dict[str, str]:
    return {
        "subordinacao_total_pct": "(PL Subordinada + PL Mezanino) / PL FIDC total",
        "npl_over90_pct": "NPL Over 90d / Carteira Bruta",
        "pdd_npl_over90_pct": "PDD total / NPL Over 90d",
        "consolidado": "Somar valores absolutos por competência e recalcular percentuais a partir das somas.",
    }


def _empty_monthly_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["fund_name", "cnpj", "competencia", "competencia_dt"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_path_token(value: object) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return text.strip("._") or "sem_id"


def _sheet_name_from_table(table: pd.DataFrame, *, fallback: str) -> str:
    if hasattr(table, "attrs"):
        name = str(table.attrs.get("scope_name") or "").strip()
        if name:
            return name
    return fallback


def _excel_sheet_name(value: str) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]", " ", value).strip() or "Sheet"
    return cleaned[:31]


def _style_wide_sheet(worksheet, table: pd.DataFrame) -> None:  # noqa: ANN001
    header_fill = PatternFill("solid", fgColor="1F77B4")
    block_fill = PatternFill("solid", fgColor="EAF2FA")
    thin = Side(style="thin", color="D9E2EC")
    border = Border(bottom=thin)
    for cell in worksheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    block_col = 1
    previous_block = None
    for row_idx in range(2, worksheet.max_row + 1):
        block = worksheet.cell(row=row_idx, column=block_col).value
        if block != previous_block:
            for col_idx in range(1, worksheet.max_column + 1):
                cell = worksheet.cell(row=row_idx, column=col_idx)
                cell.font = Font(bold=True)
                cell.fill = block_fill
                cell.border = border
            previous_block = block
        worksheet.cell(row=row_idx, column=2).alignment = Alignment(indent=1)
    _auto_width(worksheet)
    worksheet.freeze_panes = "D2"
    worksheet.auto_filter.ref = worksheet.dimensions


def _style_plain_sheet(worksheet) -> None:  # noqa: ANN001
    header_fill = PatternFill("solid", fgColor="1F77B4")
    for cell in worksheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    _auto_width(worksheet)
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions


def _auto_width(worksheet) -> None:  # noqa: ANN001
    for col_idx, column_cells in enumerate(worksheet.columns, start=1):
        width = min(max(len(str(cell.value or "")) for cell in column_cells) + 2, 48)
        worksheet.column_dimensions[get_column_letter(col_idx)].width = width
