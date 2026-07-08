from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


CEDENTE_REVIEW_COLUMNS = [
    "review_id",
    "status",
    "nome_revisado",
    "nome_fantasia_revisado",
    "cnpj_revisado",
    "grupo_economico",
    "setor_revisado",
    "segmento_revisado",
    "confianca_manual",
    "notas",
]

APPROVED_REVIEW_STATUSES = {"aprovado", "corrigido"}
ISSUANCE_YEARS = [2024, 2025, 2026]


def normalize_cnpj(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    return digits.zfill(14)[-14:]


def clean_candidate_name(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip(" ;,."))
    if len(text) < 8:
        return ""
    upper = text.upper()
    noisy_tokens = (
        "CEP",
        "ANDAR",
        "CONJUNTO",
        "SALA",
        "BAIRRO",
        "MUNICÍPIO",
        "MUNICIPIO",
        "RUA ",
        "AVENIDA",
        "DO DE INVESTIMENTO",
    )
    if any(token in upper for token in noisy_tokens):
        return ""
    if sum(char.isdigit() for char in text) > 4:
        return ""
    if not re.search(
        r"\b(S\.A\.?|LTDA|BANCO|INSTITUI|FUNDO|COMPANHIA|SOCIEDADE|SERVIÇOS|SERVICOS|TECH|TRANSPORTES)\b",
        upper,
    ):
        return ""
    return text[:120]


def review_id(row: pd.Series) -> str:
    key = "|".join(
        str(row.get(col, ""))
        for col in ["cnpj_fundo", "participant_type", "participant_name_candidate", "participant_cnpj_candidate", "source_cache"]
    )
    return hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:16]


def extract_page(value: object) -> str:
    match = re.search(r"p[aá]gina\s+(\d+)|pagina\s+(\d+)|page\s+(\d+)", str(value or ""), flags=re.IGNORECASE)
    if not match:
        return ""
    return next(group for group in match.groups() if group)


def load_cedente_reviews(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=CEDENTE_REVIEW_COLUMNS)
    reviews = pd.read_csv(path, dtype=str, keep_default_na=False)
    for col in CEDENTE_REVIEW_COLUMNS:
        if col not in reviews.columns:
            reviews[col] = ""
    return reviews[CEDENTE_REVIEW_COLUMNS]


def save_cedente_reviews(reviews: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = reviews.copy()
    for col in CEDENTE_REVIEW_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[CEDENTE_REVIEW_COLUMNS].drop_duplicates("review_id", keep="last")
    out.to_csv(path, index=False)


def load_cedente_candidates(db_path: Path) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            candidates = pd.read_sql_query(
                """
                select cnpj_fundo, fund_name, setor_n1, setor_n2, participant_type,
                       participant_cnpj_candidate, participant_name_candidate,
                       evidence_context, source_cache
                from cedentes_sacados_candidates
                """,
                conn,
            )
    except sqlite3.Error:
        return pd.DataFrame()
    if candidates.empty:
        return candidates
    candidates["cnpj_fundo"] = candidates["cnpj_fundo"].map(normalize_cnpj)
    candidates["review_id"] = candidates.apply(review_id, axis=1)
    candidates["participante_extraido"] = candidates["participant_name_candidate"].map(clean_candidate_name)
    candidates["participante_extraido"] = candidates["participante_extraido"].where(
        candidates["participante_extraido"].astype(str).str.len() > 0,
        candidates["participant_cnpj_candidate"].fillna("").astype(str),
    )
    candidates["documento_origem"] = candidates["source_cache"].map(lambda value: Path(str(value)).name if str(value) else "")
    candidates["pagina"] = candidates["evidence_context"].map(extract_page)
    candidates["metodo_extracao"] = "regex_contexto_documental"
    has_name = candidates["participante_extraido"].astype(str).str.len() > 0
    has_cnpj = candidates["participant_cnpj_candidate"].map(normalize_cnpj).astype(str).str.len().eq(14)
    has_doc = candidates["source_cache"].astype(str).str.len() > 0
    candidates["score_confianca"] = (0.35 + 0.25 * has_name + 0.25 * has_cnpj + 0.15 * has_doc).clip(upper=0.95)
    candidates["evidencias_agrupadas"] = candidates.groupby("review_id")["review_id"].transform("size")
    candidates = candidates.sort_values(["score_confianca", "cnpj_fundo"], ascending=[False, True])
    return candidates.drop_duplicates("review_id", keep="first").reset_index(drop=True)


def load_fund_universe(db_path: Path) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            frame = pd.read_sql_query(
                """
                select cnpj, fund_name_final, administrador, gestor, custodiante,
                       setor_n1, setor_n2, first_offer_year, emission_cohort,
                       emitted_2024, emitted_2025, volume_2024_brl, volume_2025_brl,
                       volume_2026_brl, valid_volume_2024_brl, valid_volume_2025_brl,
                       valid_volume_2026_brl, pl_atual_brl, has_regulatory_matrix,
                       latest_regulamento_date
                from fund_universe
                """,
                conn,
            )
    except sqlite3.Error:
        return pd.DataFrame()
    if frame.empty:
        return frame
    frame["cnpj"] = frame["cnpj"].map(normalize_cnpj)
    return frame.drop_duplicates("cnpj", keep="first")


def load_pricing_tranches(db_path: Path) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute("select name from sqlite_master where type='table'").fetchall()
            }
            if "pricing_tranche_enriched" not in tables:
                return pd.DataFrame()
            frame = pd.read_sql_query("select * from pricing_tranche_enriched", conn)
    except sqlite3.Error:
        return pd.DataFrame()
    if frame.empty:
        return frame
    id_col = "cnpj_emissor" if "cnpj_emissor" in frame.columns else "cnpj"
    frame["cnpj_fundo"] = frame[id_col].map(normalize_cnpj)
    return frame


def load_vehicle_latest(industry_dir: Path) -> pd.DataFrame:
    path = industry_dir / "universe_latest.csv"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, low_memory=False)
    for col in ["cnpj", "cnpj_fundo"]:
        if col in frame.columns:
            frame[col] = frame[col].map(normalize_cnpj)
    if "cnpj_fundo" not in frame.columns and "cnpj" in frame.columns:
        frame["cnpj_fundo"] = frame["cnpj"]
    return frame


def _num(series: pd.Series | None, index: pd.Index | None = None) -> pd.Series:
    if series is None:
        return pd.Series(0.0, index=index)
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def _text(series: pd.Series | None, index: pd.Index | None = None) -> pd.Series:
    if series is None:
        return pd.Series("", index=index)
    return series.fillna("").astype(str)


def _confidence_score(series: pd.Series | None, index: pd.Index | None = None) -> pd.Series:
    values = _text(series, index=index).str.lower()
    return values.map({"alta": 0.9, "media": 0.7, "média": 0.7, "baixa": 0.5}).fillna(0.5)


def normalize_indexer(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "n/d"
    if "ipca" in text:
        return "IPCA+"
    if "%cdi" in text or "% cdi" in text or "pct_cdi" in text:
        return "% CDI"
    if "cdi" in text or "di" == text:
        return "CDI+"
    if "pré" in text or "pre" in text:
        return "Pré"
    if "selic" in text:
        return "Selic"
    return text.upper()[:40]


def source_document(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.split(" · ")[0].strip()


def build_issuance_annual(fund_universe: pd.DataFrame) -> pd.DataFrame:
    if fund_universe.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for year in ISSUANCE_YEARS:
        volume = _num(fund_universe.get(f"volume_{year}_brl"), fund_universe.index)
        valid_volume = _num(fund_universe.get(f"valid_volume_{year}_brl"), fund_universe.index)
        offers = _num(fund_universe.get(f"offers_{year}"), fund_universe.index)
        active = volume.gt(0) | valid_volume.gt(0) | offers.gt(0)
        frame = fund_universe[active].copy()
        rows.append(
            {
                "ano": year,
                "periodo": f"{year} YTD" if year == max(ISSUANCE_YEARS) else str(year),
                "emissores_cnpj": int(frame["cnpj"].nunique()) if "cnpj" in frame else 0,
                "ofertas_linhas": int(offers[active].sum()),
                "volume_registrado_brl": float(volume[active].sum()),
                "volume_conservador_brl": float(valid_volume[active].sum()),
                "pl_atual_brl": float(_num(frame.get("pl_atual_brl"), frame.index).sum()) if not frame.empty else 0.0,
                "com_matriz_regulatoria": int(_num(frame.get("has_regulatory_matrix"), frame.index).gt(0).sum()) if not frame.empty else 0,
            }
        )
    return pd.DataFrame(rows)


def build_issuance_sector_year(fund_universe: pd.DataFrame) -> pd.DataFrame:
    if fund_universe.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    base = fund_universe.copy()
    base["setor_n1"] = _text(base.get("setor_n1"), base.index).replace("", "Não classificado")
    base["setor_n2"] = _text(base.get("setor_n2"), base.index).replace("", "Sem classificação")
    for year in ISSUANCE_YEARS:
        frame = base.copy()
        frame["volume_registrado_brl"] = _num(frame.get(f"volume_{year}_brl"), frame.index)
        frame["volume_conservador_brl"] = _num(frame.get(f"valid_volume_{year}_brl"), frame.index)
        frame["ofertas_linhas"] = _num(frame.get(f"offers_{year}"), frame.index)
        frame = frame[
            frame["volume_registrado_brl"].gt(0)
            | frame["volume_conservador_brl"].gt(0)
            | frame["ofertas_linhas"].gt(0)
        ].copy()
        if frame.empty:
            continue
        grouped = (
            frame.groupby(["setor_n1", "setor_n2"], dropna=False)
            .agg(
                emissores_cnpj=("cnpj", "nunique"),
                ofertas_linhas=("ofertas_linhas", "sum"),
                volume_registrado_brl=("volume_registrado_brl", "sum"),
                volume_conservador_brl=("volume_conservador_brl", "sum"),
                pl_atual_brl=("pl_atual_brl", "sum"),
            )
            .reset_index()
        )
        grouped["ano"] = year
        rows.extend(grouped.to_dict("records"))
    return pd.DataFrame(rows).sort_values(["ano", "volume_conservador_brl"], ascending=[True, False])


def build_issuance_tranches(pricing: pd.DataFrame) -> pd.DataFrame:
    if pricing.empty:
        return pd.DataFrame()
    frame = pricing.copy()
    idx = frame.index
    if "cnpj_fundo" not in frame.columns:
        id_col = "cnpj_emissor" if "cnpj_emissor" in frame.columns else "cnpj"
        frame["cnpj_fundo"] = _text(frame.get(id_col), idx).map(normalize_cnpj)
    frame["ano"] = _num(frame.get("pricing_year"), idx).where(_num(frame.get("pricing_year"), idx).gt(0), _num(frame.get("year_num"), idx))
    frame["ano"] = frame["ano"].round().astype("Int64")
    frame["volume_brl"] = _num(frame.get("volume_brl_num"), idx)
    if "volume_brl_num" not in frame.columns:
        frame["volume_brl"] = _num(frame.get("volume_brl"), idx)
    frame["indexador"] = _text(frame.get("pricing_basis"), idx).map(normalize_indexer)
    frame["tipo_cota"] = _text(frame.get("tipo_cota_normalizado"), idx)
    frame["tipo_cota"] = frame["tipo_cota"].where(frame["tipo_cota"].str.strip() != "", _text(frame.get("tipo"), idx))
    frame["documento_origem"] = _text(frame.get("fonte"), idx).map(source_document)
    out = pd.DataFrame(
        {
            "cnpj_fundo": frame["cnpj_fundo"].map(normalize_cnpj),
            "fundo": _text(frame.get("fund_name_final"), idx).where(
                _text(frame.get("fund_name_final"), idx).str.strip() != "",
                _text(frame.get("nome_emissor"), idx).where(_text(frame.get("nome_emissor"), idx).str.strip() != "", _text(frame.get("fundo"), idx)),
            ),
            "ano": frame["ano"],
            "periodo": _text(frame.get("pricing_period"), idx).where(_text(frame.get("pricing_period"), idx).str.strip() != "", frame["ano"].astype(str)),
            "data_deliberacao": _text(frame.get("data_deliberacao_dt"), idx).where(
                _text(frame.get("data_deliberacao_dt"), idx).str.strip() != "",
                _text(frame.get("data_deliberacao"), idx),
            ),
            "cota_classe": _text(frame.get("cota_classe"), idx),
            "tipo_cota": frame["tipo_cota"],
            "indexador": frame["indexador"],
            "spread_cdi_aa": _num(frame.get("spread_cdi_aa_num"), idx),
            "pct_cdi": _num(frame.get("pct_cdi_num"), idx),
            "spread_ipca_aa": _num(frame.get("spread_ipca_aa_num"), idx),
            "volume_brl": frame["volume_brl"],
            "setor_n1": _text(frame.get("setor_n1"), idx).replace("", "Não classificado"),
            "setor_n2": _text(frame.get("setor_n2"), idx).replace("", "Sem classificação"),
            "emission_cohort": _text(frame.get("emission_cohort"), idx),
            "status_curadoria": _text(frame.get("status_curadoria"), idx),
            "fonte": _text(frame.get("fonte"), idx),
            "documento_origem": frame["documento_origem"],
            "metodo_extracao": "pricing_tranche_enriched_sqlite",
            "score_confianca": _confidence_score(frame.get("confidence"), idx),
            "pricing_evidence": _text(frame.get("pricing_evidence"), idx),
            "remuneracao_texto": _text(frame.get("remunera_o"), idx),
            "amortizacao_texto": _text(frame.get("amortiza_o_principal"), idx),
        }
    )
    out = out[out["cnpj_fundo"].astype(str).str.len().eq(14)].copy()
    return out.sort_values(["ano", "volume_brl"], ascending=[False, False], na_position="last")


def issuance_quality_summary(
    annual: pd.DataFrame,
    sector_year: pd.DataFrame,
    tranches: pd.DataFrame,
) -> dict[str, object]:
    tranche_score = pd.to_numeric(tranches.get("score_confianca"), errors="coerce") if not tranches.empty and "score_confianca" in tranches else pd.Series(dtype=float)
    return {
        "annual_years": int(annual["ano"].nunique()) if "ano" in annual else 0,
        "annual_volume_conservador_brl": float(_num(annual.get("volume_conservador_brl"), annual.index).sum()) if not annual.empty else 0.0,
        "annual_emissores_cnpj": int(annual["emissores_cnpj"].max()) if "emissores_cnpj" in annual and not annual.empty else 0,
        "sector_year_rows": int(len(sector_year)),
        "tranche_rows": int(len(tranches)),
        "tranche_funds": int(tranches["cnpj_fundo"].nunique()) if "cnpj_fundo" in tranches else 0,
        "coverage": {
            "tranche_volume": _coverage(tranches, "volume_brl"),
            "tranche_indexador": _coverage(tranches, "indexador"),
            "tranche_documento": _coverage(tranches, "documento_origem"),
            "tranche_data": _coverage(tranches, "data_deliberacao"),
            "tranche_setor": _coverage(tranches, "setor_n1"),
            "tranche_score": float(tranche_score.notna().mean()) if len(tranche_score) else 0.0,
        },
        "score": {
            "median": _json_float(tranche_score.median()) if tranche_score.notna().any() else None,
            "p25": _json_float(tranche_score.quantile(0.25)) if tranche_score.notna().any() else None,
            "p75": _json_float(tranche_score.quantile(0.75)) if tranche_score.notna().any() else None,
        },
    }


def _clean_review_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def build_cedente_structured(
    candidates: pd.DataFrame,
    reviews: pd.DataFrame,
    *,
    fund_universe: pd.DataFrame | None = None,
    vehicle_latest: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()

    base = candidates.copy()
    if reviews is None or reviews.empty:
        reviews = pd.DataFrame(columns=CEDENTE_REVIEW_COLUMNS)
    for col in CEDENTE_REVIEW_COLUMNS:
        if col not in reviews.columns:
            reviews[col] = ""
    base = base.merge(reviews[CEDENTE_REVIEW_COLUMNS], on="review_id", how="left")
    for col in CEDENTE_REVIEW_COLUMNS:
        if col not in base.columns:
            base[col] = ""
        base[col] = _clean_review_text(base[col])
    base["status"] = base["status"].replace("", "pendente")
    approved = base["status"].str.lower().isin(APPROVED_REVIEW_STATUSES)

    auto_name = base["participante_extraido"].fillna("").astype(str).str.strip()
    reviewed_name = base["nome_revisado"].where(approved, "").fillna("").astype(str).str.strip()
    base["razao_social"] = reviewed_name.where(reviewed_name != "", auto_name)

    auto_cnpj = base["participant_cnpj_candidate"].map(normalize_cnpj)
    reviewed_cnpj = base["cnpj_revisado"].where(approved, "").map(normalize_cnpj)
    base["cnpj_participante"] = reviewed_cnpj.where(reviewed_cnpj != "", auto_cnpj)

    manual_score = pd.to_numeric(base["confianca_manual"], errors="coerce")
    auto_score = pd.to_numeric(base["score_confianca"], errors="coerce").fillna(0)
    base["score_confianca_final"] = manual_score.where(manual_score.notna(), auto_score)
    base["fonte_nome"] = approved.map({True: "revisao_manual", False: "extracao_automatica"})
    base["fonte_cnpj"] = (approved & (reviewed_cnpj != "")).map({True: "revisao_manual", False: "extracao_automatica"})
    base["ativo_curadoria"] = ~base["status"].str.lower().eq("rejeitado")

    type_labels = {
        "cedente_originador": "cedente/originador",
        "sacado_devedor": "sacado/devedor",
        "consultora": "consultora",
    }
    base["tipo_participante"] = base["participant_type"].replace(type_labels)
    base["setor"] = base["setor_revisado"].where(base["setor_revisado"] != "", base["setor_n1"].fillna(""))
    base["segmento"] = base["segmento_revisado"].where(base["segmento_revisado"] != "", base["setor_n2"].fillna(""))

    out = pd.DataFrame(
        {
            "review_id": base["review_id"],
            "cnpj_fundo": base["cnpj_fundo"].map(normalize_cnpj),
            "fundo": base["fund_name"].fillna("").astype(str),
            "participant_type": base["participant_type"].fillna("").astype(str),
            "tipo_participante": base["tipo_participante"].fillna("").astype(str),
            "razao_social": base["razao_social"],
            "nome_fantasia": base["nome_fantasia_revisado"].fillna("").astype(str),
            "cnpj_participante": base["cnpj_participante"],
            "grupo_economico": base["grupo_economico"].fillna("").astype(str),
            "setor": base["setor"],
            "segmento": base["segmento"],
            "setor_auto": base["setor_n1"].fillna("").astype(str),
            "segmento_auto": base["setor_n2"].fillna("").astype(str),
            "status_revisao": base["status"],
            "ativo_curadoria": base["ativo_curadoria"],
            "metodo_extracao": base["metodo_extracao"],
            "score_confianca": auto_score,
            "score_confianca_final": base["score_confianca_final"],
            "n_evidencias": pd.to_numeric(base["evidencias_agrupadas"], errors="coerce").fillna(1).astype(int),
            "documento_origem": base["documento_origem"].fillna("").astype(str),
            "pagina": base["pagina"].fillna("").astype(str),
            "source_cache": base["source_cache"].fillna("").astype(str),
            "evidencia": base["evidence_context"].fillna("").astype(str),
            "fonte_nome": base["fonte_nome"],
            "fonte_cnpj": base["fonte_cnpj"],
            "notas": base["notas"].fillna("").astype(str),
        }
    )

    if fund_universe is not None and not fund_universe.empty:
        fund = fund_universe.copy()
        fund["cnpj"] = fund["cnpj"].map(normalize_cnpj)
        fund_cols = [
            "cnpj",
            "fund_name_final",
            "administrador",
            "gestor",
            "custodiante",
            "first_offer_year",
            "emission_cohort",
            "emitted_2024",
            "emitted_2025",
            "volume_2024_brl",
            "volume_2025_brl",
            "volume_2026_brl",
            "valid_volume_2024_brl",
            "valid_volume_2025_brl",
            "valid_volume_2026_brl",
            "pl_atual_brl",
            "has_regulatory_matrix",
            "latest_regulamento_date",
        ]
        out = out.merge(fund[[col for col in fund_cols if col in fund.columns]], left_on="cnpj_fundo", right_on="cnpj", how="left")
        out = out.drop(columns=["cnpj"], errors="ignore")

    if vehicle_latest is not None and not vehicle_latest.empty:
        vehicle = vehicle_latest.copy()
        if "cnpj_fundo" in vehicle.columns:
            vehicle["cnpj_fundo"] = vehicle["cnpj_fundo"].map(normalize_cnpj)
        keep = [
            "cnpj_fundo",
            "competencia",
            "admin_nome",
            "gestor_nome",
            "custodiante_nome",
            "segmento_principal",
            "segmento_financeiro_principal",
            "pl",
            "carteira_dc",
            "cotistas",
            "subordinacao_pct",
            "inad_pct_ajustada",
        ]
        vehicle = vehicle[[col for col in keep if col in vehicle.columns]].drop_duplicates("cnpj_fundo")
        out = out.merge(vehicle, on="cnpj_fundo", how="left", suffixes=("", "_ime"))

    for col in ["volume_2025_brl", "volume_2026_brl", "valid_volume_2025_brl", "valid_volume_2026_brl", "first_offer_year"]:
        if col not in out.columns:
            out[col] = 0
    volume_priority = (
        pd.to_numeric(out["volume_2025_brl"], errors="coerce").fillna(0)
        + pd.to_numeric(out["volume_2026_brl"], errors="coerce").fillna(0)
        + pd.to_numeric(out["valid_volume_2025_brl"], errors="coerce").fillna(0)
        + pd.to_numeric(out["valid_volume_2026_brl"], errors="coerce").fillna(0)
    )
    first_year = pd.to_numeric(out["first_offer_year"], errors="coerce")
    out["periodo_prioritario"] = ((volume_priority > 0) | first_year.isin([2025, 2026])).map(
        {True: "2025-2026 YTD", False: "histórico"}
    )

    ordered = [
        "review_id",
        "cnpj_fundo",
        "fundo",
        "participant_type",
        "tipo_participante",
        "razao_social",
        "nome_fantasia",
        "cnpj_participante",
        "grupo_economico",
        "setor",
        "segmento",
        "status_revisao",
        "ativo_curadoria",
        "periodo_prioritario",
        "score_confianca_final",
        "score_confianca",
        "n_evidencias",
        "metodo_extracao",
        "documento_origem",
        "pagina",
        "source_cache",
        "evidencia",
        "fonte_nome",
        "fonte_cnpj",
        "notas",
    ]
    rest = [col for col in out.columns if col not in ordered]
    return out[ordered + rest].sort_values(
        ["periodo_prioritario", "score_confianca_final", "cnpj_fundo"],
        ascending=[True, False, True],
    )


def save_cedente_structured(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression="gzip" if path.suffix == ".gz" else None)


def load_cedente_structured(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


def save_dataframe(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression="gzip" if path.suffix == ".gz" else None)


def load_dataframe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


def file_fingerprint(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"path": str(path), "exists": False, "bytes": 0, "sha256": ""}
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "exists": True,
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def _coverage(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    values = frame[column].fillna("").astype(str).str.strip()
    return float(values.ne("").mean())


def _json_float(value: object) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return None
    return float(number)


def cedente_quality_summary(
    candidates: pd.DataFrame,
    reviews: pd.DataFrame,
    structured: pd.DataFrame,
) -> dict[str, object]:
    if reviews is None:
        reviews = pd.DataFrame(columns=CEDENTE_REVIEW_COLUMNS)
    if structured is None:
        structured = pd.DataFrame()
    active = structured
    if "ativo_curadoria" in structured.columns:
        active = structured[structured["ativo_curadoria"].astype(str).str.lower().isin({"true", "1", "sim"})]
    priority = structured
    if "periodo_prioritario" in structured.columns:
        priority = structured[structured["periodo_prioritario"].eq("2025-2026 YTD")]
    status_counts = reviews["status"].replace("", "pendente").value_counts().to_dict() if "status" in reviews else {}
    participant_counts = structured["participant_type"].value_counts().to_dict() if "participant_type" in structured else {}
    if not structured.empty and "score_confianca_final" in structured.columns:
        score = pd.to_numeric(structured["score_confianca_final"], errors="coerce")
    else:
        score = pd.Series(dtype=float)
    return {
        "candidate_rows": int(len(candidates)),
        "candidate_funds": int(candidates["cnpj_fundo"].nunique()) if "cnpj_fundo" in candidates else 0,
        "structured_rows": int(len(structured)),
        "active_rows": int(len(active)),
        "structured_funds": int(structured["cnpj_fundo"].nunique()) if "cnpj_fundo" in structured else 0,
        "priority_2025_2026_rows": int(len(priority)),
        "priority_2025_2026_funds": int(priority["cnpj_fundo"].nunique()) if "cnpj_fundo" in priority else 0,
        "review_rows": int(len(reviews)),
        "review_status_counts": {str(k): int(v) for k, v in status_counts.items()},
        "participant_type_counts": {str(k): int(v) for k, v in participant_counts.items()},
        "coverage": {
            "razao_social": _coverage(structured, "razao_social"),
            "nome_fantasia": _coverage(structured, "nome_fantasia"),
            "cnpj_participante": _coverage(structured, "cnpj_participante"),
            "grupo_economico": _coverage(structured, "grupo_economico"),
            "setor": _coverage(structured, "setor"),
            "segmento": _coverage(structured, "segmento"),
            "documento_origem": _coverage(structured, "documento_origem"),
            "pagina": _coverage(structured, "pagina"),
            "metodo_extracao": _coverage(structured, "metodo_extracao"),
            "score_confianca_final": float(score.notna().mean()) if len(score) else 0.0,
        },
        "score": {
            "median": _json_float(score.median()) if score.notna().any() else None,
            "p25": _json_float(score.quantile(0.25)) if score.notna().any() else None,
            "p75": _json_float(score.quantile(0.75)) if score.notna().any() else None,
        },
    }


def build_cedente_pipeline_manifest(
    *,
    industry_dir: Path,
    strategy_db: Path,
    reviews_path: Path,
    output_path: Path,
    candidates: pd.DataFrame,
    reviews: pd.DataFrame,
    fund_universe: pd.DataFrame,
    vehicle_latest: pd.DataFrame,
    structured: pd.DataFrame,
) -> dict[str, object]:
    quality = cedente_quality_summary(candidates, reviews, structured)
    return {
        "schema_version": "industry-pipeline-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_cedentes_structured",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "macbook_air_m4_friendly": True,
            "notes": [
                "Este modulo consolida candidatos ja extraidos; nao baixa nem reprocessa documentos.",
                "Cada entrada/saida fica persistida para permitir reexecucao parcial e auditoria mensal.",
            ],
        },
        "inputs": {
            "strategy_db": file_fingerprint(strategy_db),
            "manual_reviews": file_fingerprint(reviews_path),
            "vehicle_snapshot": file_fingerprint(industry_dir / "universe_latest.csv"),
        },
        "outputs": {
            "cedentes_structured": file_fingerprint(output_path),
            "manifest": {"path": str(industry_dir / "industry_pipeline_manifest.json")},
        },
        "stages": [
            {
                "id": "extract_candidates",
                "label": "Candidatos cedente/sacado",
                "status": "ok" if not candidates.empty else "empty",
                "input": str(strategy_db),
                "output": "memoria:cedentes_sacados_candidates",
                "rows": int(len(candidates)),
                "funds": int(candidates["cnpj_fundo"].nunique()) if "cnpj_fundo" in candidates else 0,
                "rerun": "python scripts/execute_fidc_director_diagnostic.py --download-limit 0",
            },
            {
                "id": "apply_manual_review",
                "label": "Revisao manual persistida",
                "status": "ok",
                "input": str(reviews_path),
                "output": "memoria:review_overlay",
                "rows": int(len(reviews)),
                "rerun": "Editar pela aba Indústria > Cedentes; nao editar CSV manualmente.",
            },
            {
                "id": "enrich_funds",
                "label": "Enriquecimento por fundos/ofertas",
                "status": "ok" if not fund_universe.empty else "empty",
                "input": str(strategy_db),
                "output": "memoria:fund_universe",
                "rows": int(len(fund_universe)),
                "rerun": "python scripts/export_fidc_strategy_audit_report.py",
            },
            {
                "id": "enrich_ime_snapshot",
                "label": "Enriquecimento IME atual",
                "status": "ok" if not vehicle_latest.empty else "empty",
                "input": str(industry_dir / "universe_latest.csv"),
                "output": "memoria:universe_latest",
                "rows": int(len(vehicle_latest)),
                "rerun": "python scripts/build_fidc_industry_study.py --report",
            },
            {
                "id": "consolidate_structured_base",
                "label": "Base estruturada de cedentes",
                "status": "ok" if not structured.empty else "empty",
                "input": "memoria:candidates+review_overlay+fund_universe+universe_latest",
                "output": str(output_path),
                "rows": int(len(structured)),
                "funds": int(structured["cnpj_fundo"].nunique()) if "cnpj_fundo" in structured else 0,
                "rerun": "python scripts/build_fidc_industry_cedentes.py",
            },
        ],
        "quality": quality,
    }


def build_issuance_pipeline_manifest(
    *,
    industry_dir: Path,
    strategy_db: Path,
    annual_path: Path,
    sector_year_path: Path,
    tranches_path: Path,
    fund_universe: pd.DataFrame,
    pricing: pd.DataFrame,
    annual: pd.DataFrame,
    sector_year: pd.DataFrame,
    tranches: pd.DataFrame,
) -> dict[str, object]:
    quality = issuance_quality_summary(annual, sector_year, tranches)
    return {
        "schema_version": "industry-issuance-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_issuance_structured",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "macbook_air_m4_friendly": True,
            "notes": [
                "Este modulo consolida ofertas/emissoes ja estruturadas no SQLite de Estratégia.",
                "A serie de emissões é conceito de mercado primário/oferta; não substitui captação líquida do IME.",
            ],
        },
        "inputs": {
            "strategy_db": file_fingerprint(strategy_db),
        },
        "outputs": {
            "issuance_annual": file_fingerprint(annual_path),
            "issuance_sector_year": file_fingerprint(sector_year_path),
            "issuance_tranches": file_fingerprint(tranches_path),
            "manifest": {"path": str(industry_dir / "industry_issuance_manifest.json")},
        },
        "stages": [
            {
                "id": "load_fund_universe",
                "label": "Universo de fundos/ofertas",
                "status": "ok" if not fund_universe.empty else "empty",
                "input": str(strategy_db),
                "output": "memoria:fund_universe",
                "rows": int(len(fund_universe)),
                "funds": int(fund_universe["cnpj"].nunique()) if "cnpj" in fund_universe else 0,
                "rerun": "python scripts/export_fidc_strategy_audit_report.py",
            },
            {
                "id": "load_pricing_tranches",
                "label": "Tranches e pricing documental",
                "status": "ok" if not pricing.empty else "empty",
                "input": str(strategy_db),
                "output": "memoria:pricing_tranche_enriched",
                "rows": int(len(pricing)),
                "funds": int(pricing["cnpj_fundo"].nunique()) if "cnpj_fundo" in pricing else 0,
                "rerun": "python scripts/execute_fidc_director_diagnostic.py --download-limit 0",
            },
            {
                "id": "aggregate_annual_issuance",
                "label": "Volume anual e emissores",
                "status": "ok" if not annual.empty else "empty",
                "input": "memoria:fund_universe",
                "output": str(annual_path),
                "rows": int(len(annual)),
                "rerun": "python scripts/build_fidc_industry_issuance.py",
            },
            {
                "id": "aggregate_sector_year",
                "label": "Setor por ano",
                "status": "ok" if not sector_year.empty else "empty",
                "input": "memoria:fund_universe",
                "output": str(sector_year_path),
                "rows": int(len(sector_year)),
                "rerun": "python scripts/build_fidc_industry_issuance.py",
            },
            {
                "id": "normalize_tranches",
                "label": "Base de tranches normalizada",
                "status": "ok" if not tranches.empty else "empty",
                "input": "memoria:pricing_tranche_enriched",
                "output": str(tranches_path),
                "rows": int(len(tranches)),
                "funds": int(tranches["cnpj_fundo"].nunique()) if "cnpj_fundo" in tranches else 0,
                "rerun": "python scripts/build_fidc_industry_issuance.py",
            },
        ],
        "quality": quality,
    }


def save_pipeline_manifest(manifest: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def load_pipeline_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
