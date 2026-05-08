from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable

import pandas as pd

from services.variaveis_fnet import VARIAVEIS_FNET, competencia_columns, resolve_tag_path, variaveis_fnet_df


DEFAULT_OVERRIDES_DIR = Path("manual_overrides")
MONEY_SCALE = 1_000_000.0


@dataclass(frozen=True)
class MonitoringTables:
    raw_variables_df: pd.DataFrame
    indicators_df: pd.DataFrame
    aging_df: pd.DataFrame
    audit_df: pd.DataFrame


def read_wide_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    return normalize_wide_frame(frame)


def normalize_wide_frame(wide_df: pd.DataFrame) -> pd.DataFrame:
    frame = wide_df.copy()
    if "tag_path" not in frame.columns:
        frame = frame.reset_index()
        if "tag_path" not in frame.columns:
            first_col = frame.columns[0]
            frame = frame.rename(columns={first_col: "tag_path"})
    frame["tag_path"] = frame["tag_path"].astype(str)
    return frame.set_index("tag_path", drop=False)


def load_manual_overrides(cnpj: str, *, overrides_dir: Path | None = None) -> dict[str, Any]:
    path = _override_path(cnpj, overrides_dir=overrides_dir)
    if not path.exists():
        return {"cnpj": _normalize_cnpj(cnpj), "competencias": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"cnpj": _normalize_cnpj(cnpj), "competencias": {}}
    competencias = payload.get("competencias") if isinstance(payload, dict) else {}
    return {
        "cnpj": _normalize_cnpj(str(payload.get("cnpj") if isinstance(payload, dict) else cnpj) or cnpj),
        "competencias": competencias if isinstance(competencias, dict) else {},
    }


def save_manual_overrides(
    cnpj: str,
    payload: dict[str, Any],
    *,
    overrides_dir: Path | None = None,
) -> Path:
    path = _override_path(cnpj, overrides_dir=overrides_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = {"cnpj": _normalize_cnpj(cnpj), "competencias": {}}
    for competencia, values in (payload.get("competencias") or {}).items():
        if not isinstance(values, dict):
            continue
        row = {}
        for key in ("vl_total_mz", "rent_mz"):
            parsed = _to_float(values.get(key))
            if parsed is not None:
                row[key] = parsed
        if row:
            normalized["competencias"][str(competencia)] = row
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_monitoring_tables(
    wide_df: pd.DataFrame,
    competencias: list[str] | None = None,
    *,
    cnpj: str = "",
    overrides: dict[str, Any] | None = None,
) -> MonitoringTables:
    wide_lookup = normalize_wide_frame(wide_df)
    resolved_competencias = competencias or competencia_columns(wide_lookup)
    raw_variables_df = build_raw_variables_df(wide_lookup, resolved_competencias)
    indicators_df, audit_df = build_indicators_df(
        wide_lookup,
        resolved_competencias,
        cnpj=cnpj,
        overrides=overrides,
    )
    aging_df = build_aging_df(wide_lookup, resolved_competencias)
    return MonitoringTables(
        raw_variables_df=raw_variables_df,
        indicators_df=indicators_df,
        aging_df=aging_df,
        audit_df=audit_df,
    )


def build_raw_variables_df(wide_df: pd.DataFrame, competencias: list[str]) -> pd.DataFrame:
    wide_lookup = normalize_wide_frame(wide_df)
    catalog = variaveis_fnet_df(wide_lookup)
    rows: list[dict[str, object]] = []
    for item in catalog.itertuples(index=False):
        tag_path = getattr(item, "tag_path")
        values = _series_for_path(wide_lookup, competencias, tag_path)
        row = {
            "id_cvm": item.id_cvm,
            "label": item.label,
            "secao": item.secao,
            "tag_path": tag_path or "",
            "status": "OK" if tag_path else "AUSENTE",
        }
        row.update({competencia: values.loc[competencia] for competencia in competencias})
        rows.append(row)
    return pd.DataFrame(rows)


def build_indicators_df(
    wide_df: pd.DataFrame,
    competencias: list[str],
    *,
    cnpj: str = "",
    overrides: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    wide_lookup = normalize_wide_frame(wide_df)
    overrides = overrides or load_manual_overrides(cnpj)

    pl_raw = _series(wide_lookup, competencias, "PATRLIQ/VL_SOM_PATRLIQ")
    dircred_raw = _sum_series(
        wide_lookup,
        competencias,
        ["CRED_EXISTE/VL_SOM_DICRED_AQUIS", "DICRED/VL_DICRED"],
    )
    venc_ate_90_raw = _sum_series(wide_lookup, competencias, _aging_ids(["VL_INAD_VENC_30", "VL_INAD_VENC_31_60", "VL_INAD_VENC_61_90"]))
    venc_acima_90_raw = _sum_series(
        wide_lookup,
        competencias,
        _aging_ids(
            [
                "VL_INAD_VENC_91_120",
                "VL_INAD_VENC_121_150",
                "VL_INAD_VENC_151_180",
                "VL_INAD_VENC_181_360",
                "VL_INAD_VENC_361_720",
                "VL_INAD_VENC_721_1080",
                "VL_INAD_VENC_1080",
            ]
        ),
    )
    venc_total_raw = _sum_existing_series([venc_ate_90_raw, venc_acima_90_raw])
    pdd_raw = _sum_series(
        wide_lookup,
        competencias,
        ["CRED_EXISTE/VL_PROVIS_REDUC_RECUP", "DICRED/VL_DICRED_PROVIS_REDUC_RECUP"],
    )
    recomp_raw = _series(wide_lookup, competencias, "DICRED_MES_ALIEN_RECOMP/VL_DICRED_ALIEN")
    sr_raw = _series(wide_lookup, competencias, "CLASSE_SENIOR/VL_TOTAL")
    sub_raw = _series(wide_lookup, competencias, "CLASSE_SUBORD/VL_TOTAL")
    rent_sr = _series(wide_lookup, competencias, "RENT_CLASSE_SENIOR/PR_APURADA")
    rent_sub = _series(wide_lookup, competencias, "RENT_CLASSE_SUBORD/PR_APURADA")
    mz_raw = _override_series(overrides, competencias, "vl_total_mz")
    rent_mz = _override_series(overrides, competencias, "rent_mz")

    specs: list[tuple[str, str, pd.Series, str, str]] = [
        ("PL (R$)", "R$ bruto", pl_raw, "PATRLIQ/VL_SOM_PATRLIQ", "PATRLIQ/VL_SOM_PATRLIQ"),
        ("PL (R$ MM)", "R$ MM", pl_raw / MONEY_SCALE, "PATRLIQ/VL_SOM_PATRLIQ ÷ 1e6", "PATRLIQ/VL_SOM_PATRLIQ"),
        ("Dir Cred (R$ MM)", "R$ MM", dircred_raw / MONEY_SCALE, "(CRED_EXISTE/VL_SOM_DICRED_AQUIS + DICRED/VL_DICRED) ÷ 1e6", "CRED_EXISTE/VL_SOM_DICRED_AQUIS; DICRED/VL_DICRED"),
        ("Dir Cred / PL", "ratio", _safe_divide(dircred_raw, pl_raw), "Dir Cred ÷ PL", "derivado"),
        ("Vencidos <= 90 d (R$ MM)", "R$ MM", venc_ate_90_raw / MONEY_SCALE, "Soma buckets 1-90d ÷ 1e6", "COMPMT_DICRED_*"),
        ("Vencidos > 90 d (R$ MM)", "R$ MM", venc_acima_90_raw / MONEY_SCALE, "Soma buckets 91d+ ÷ 1e6", "COMPMT_DICRED_*"),
        ("Vencidos Total (R$ MM)", "R$ MM", venc_total_raw / MONEY_SCALE, "Vencidos <=90d + Vencidos >90d", "derivado"),
        ("Vencidos <= 90 d / Crédito", "ratio", _safe_divide(venc_ate_90_raw, dircred_raw), "Vencidos <=90d ÷ Dir Cred", "derivado"),
        ("Vencidos > 90 d / Crédito", "ratio", _safe_divide(venc_acima_90_raw, dircred_raw), "Vencidos >90d ÷ Dir Cred", "derivado"),
        ("Vencidos Total / Crédito", "ratio", _safe_divide(venc_total_raw, dircred_raw), "Vencidos Total ÷ Dir Cred", "derivado"),
        ("PDD (R$ MM)", "R$ MM", pdd_raw / MONEY_SCALE, "(PDD com aquisição + PDD sem aquisição) ÷ 1e6", "CRED_EXISTE/VL_PROVIS_REDUC_RECUP; DICRED/VL_DICRED_PROVIS_REDUC_RECUP"),
        ("PDD / Crédito", "ratio", _safe_divide(pdd_raw, dircred_raw), "PDD ÷ Dir Cred", "derivado"),
        ("PDD / Venc > 90 d", "ratio", _safe_divide(pdd_raw, venc_acima_90_raw), "PDD ÷ Vencidos >90d", "derivado"),
        ("PDD / Venc Total", "ratio", _safe_divide(pdd_raw, venc_total_raw), "PDD ÷ Vencidos Total", "derivado"),
        ("Recompras (R$ MM)", "R$ MM", recomp_raw / MONEY_SCALE, "DICRED_MES_ALIEN_RECOMP/VL_DICRED_ALIEN ÷ 1e6", "DICRED_MES_ALIEN_RECOMP/VL_DICRED_ALIEN"),
        ("Recompras / Crédito", "ratio", _safe_divide(recomp_raw, dircred_raw), "Recompras ÷ Dir Cred", "derivado"),
        ("Recompras / PL", "ratio", _safe_divide(recomp_raw, pl_raw), "Recompras ÷ PL", "derivado"),
        ("Cotas SR / PL %", "%", _safe_divide(sr_raw, pl_raw) * 100.0, "CLASSE_SENIOR/VL_TOTAL ÷ PL", "CLASSE_SENIOR/VL_TOTAL"),
        ("Cotas Sub / PL %", "%", _safe_divide(sub_raw, pl_raw) * 100.0, "CLASSE_SUBORD/VL_TOTAL ÷ PL", "CLASSE_SUBORD/VL_TOTAL"),
        ("Rentabilidade SR % a.m.", "%", rent_sr, "RENT_CLASSE_SENIOR/PR_APURADA", "RENT_CLASSE_SENIOR/PR_APURADA"),
        ("Rentabilidade Sub % a.m.", "%", rent_sub, "RENT_CLASSE_SUBORD/PR_APURADA", "RENT_CLASSE_SUBORD/PR_APURADA"),
    ]
    if not mz_raw.isna().all():
        specs.append(("Cotas MZ / PL %", "%", _safe_divide(mz_raw, pl_raw) * 100.0, "override vl_total_mz ÷ PL", "manual_overrides"))
    if not rent_mz.isna().all():
        specs.append(("Rentabilidade MZ % a.m.", "%", rent_mz, "override rent_mz", "manual_overrides"))

    rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    for ordem, (indicador, unidade, values, formula, fonte) in enumerate(specs, start=1):
        row: dict[str, object] = {"ordem": ordem, "indicador": indicador, "unidade": unidade}
        row.update({competencia: _to_nullable(values.loc[competencia]) for competencia in competencias})
        rows.append(row)
        audit_rows.append(
            {
                "indicador": indicador,
                "formula": formula,
                "fonte": fonte,
                "status": "OK" if not values.isna().all() else "AUSENTE",
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(audit_rows)


def build_aging_df(wide_df: pd.DataFrame, competencias: list[str]) -> pd.DataFrame:
    wide_lookup = normalize_wide_frame(wide_df)
    dircred_raw = _sum_series(wide_lookup, competencias, ["CRED_EXISTE/VL_SOM_DICRED_AQUIS", "DICRED/VL_DICRED"])
    buckets = [
        ("1-30d", ["VL_INAD_VENC_30"]),
        ("31-60d", ["VL_INAD_VENC_31_60"]),
        ("61-90d", ["VL_INAD_VENC_61_90"]),
        ("91-120d", ["VL_INAD_VENC_91_120"]),
        ("121-150d", ["VL_INAD_VENC_121_150"]),
        ("151-180d", ["VL_INAD_VENC_151_180"]),
        ("181-360d", ["VL_INAD_VENC_181_360"]),
        ("361d+", ["VL_INAD_VENC_361_720", "VL_INAD_VENC_721_1080", "VL_INAD_VENC_1080"]),
    ]
    rows = []
    cumulative = pd.Series([0.0] * len(competencias), index=competencias, dtype="Float64")
    for ordem, (bucket, suffixes) in enumerate(buckets, start=1):
        raw = _sum_series(wide_lookup, competencias, _aging_ids(suffixes))
        cumulative = _sum_existing_series([cumulative, raw])
        row = {"ordem": ordem, "bucket": bucket, "unidade": "R$ MM"}
        row.update({competencia: _to_nullable((raw / MONEY_SCALE).loc[competencia]) for competencia in competencias})
        rows.append(row)
        ratio_row = {"ordem": ordem + 100, "bucket": f"{bucket} acumulado / Crédito", "unidade": "ratio"}
        cumulative_ratio = _safe_divide(cumulative, dircred_raw)
        ratio_row.update({competencia: _to_nullable(cumulative_ratio.loc[competencia]) for competencia in competencias})
        rows.append(ratio_row)
    return pd.DataFrame(rows)


def _series(wide_lookup: pd.DataFrame, competencias: list[str], short_id: str) -> pd.Series:
    tag_path = resolve_tag_path(short_id, wide_lookup)
    return _series_for_path(wide_lookup, competencias, tag_path)


def _series_for_path(wide_lookup: pd.DataFrame, competencias: list[str], tag_path: str | None) -> pd.Series:
    if not tag_path or tag_path not in wide_lookup.index:
        return pd.Series([pd.NA] * len(competencias), index=competencias, dtype="Float64")
    row = wide_lookup.loc[tag_path]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    values = pd.to_numeric(pd.Series([row.get(competencia, pd.NA) for competencia in competencias], index=competencias), errors="coerce")
    return values.astype("Float64")


def _sum_series(wide_lookup: pd.DataFrame, competencias: list[str], short_ids: Iterable[str]) -> pd.Series:
    return _sum_existing_series([_series(wide_lookup, competencias, short_id) for short_id in short_ids])


def _sum_existing_series(series_list: list[pd.Series]) -> pd.Series:
    if not series_list:
        return pd.Series(dtype="Float64")
    frame = pd.concat(series_list, axis=1)
    return frame.sum(axis=1, min_count=1).astype("Float64")


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce").astype("Float64")
    den = pd.to_numeric(denominator, errors="coerce").astype("Float64")
    result = num / den.where(den > 0)
    return result.astype("Float64")


def _aging_ids(suffixes: list[str]) -> list[str]:
    bases = ["COMPMT_DICRED_AQUIS", "COMPMT_DICRED_SEM_AQUIS"]
    return [f"{base}/{suffix}" for base in bases for suffix in suffixes]


def _override_series(overrides: dict[str, Any], competencias: list[str], field: str) -> pd.Series:
    values = []
    payload = overrides.get("competencias") or {}
    for competencia in competencias:
        values.append(_to_float((payload.get(competencia) or {}).get(field)))
    return pd.Series(values, index=competencias, dtype="Float64")


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if value is pd.NA:
        return None
    text = str(value).strip()
    if text in {"", "nan", "None", "<NA>"}:
        return None
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return None
    return float(parsed)


def _to_nullable(value: object) -> object:
    numeric = _to_float(value)
    return pd.NA if numeric is None else numeric


def _override_path(cnpj: str, *, overrides_dir: Path | None = None) -> Path:
    return (overrides_dir or DEFAULT_OVERRIDES_DIR) / f"{_normalize_cnpj(cnpj)}.json"


def _normalize_cnpj(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))
