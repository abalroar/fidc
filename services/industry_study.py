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

CRITERIA_REVIEW_COLUMNS = [
    "rule_id",
    "status",
    "criterio_revisado",
    "chave_revisada",
    "limite_revisado",
    "pct_min_revisado",
    "monitorabilidade_revisada",
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


_DOCUMENT_SOURCE_COLUMNS = [
    "cnpj_fundo",
    "fundo",
    "setor_n1",
    "setor_n2",
    "source_table",
    "source_field",
    "source_value",
    "document_date_hint",
    "priority_hint",
]


def _empty_document_sources() -> pd.DataFrame:
    return pd.DataFrame(columns=_DOCUMENT_SOURCE_COLUMNS)


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute("select name from sqlite_master where type='table'").fetchall()
    }


def load_document_source_rows(strategy_db: Path) -> pd.DataFrame:
    """Load document references already discovered by the strategy pipeline."""
    if not strategy_db.exists():
        return _empty_document_sources()
    frames: list[pd.DataFrame] = []
    try:
        with sqlite3.connect(strategy_db) as conn:
            tables = _table_names(conn)
            if "manual_review_queue" in tables:
                frames.append(
                    pd.read_sql_query(
                        """
                        select coalesce(cnpj, cnpj_emissor, '') as cnpj_fundo,
                               coalesce(nome_emissor, '') as fundo,
                               coalesce(setor_n1_final, setor_n1, '') as setor_n1,
                               coalesce(setor_n2_final, setor_n2, '') as setor_n2,
                               'manual_review_queue' as source_table,
                               'latest_regulamento_file' as source_field,
                               coalesce(latest_regulamento_file, '') as source_value,
                               coalesce(latest_regulamento_date, '') as document_date_hint,
                               coalesce(review_wave, '') || ' ' || coalesce(review_reason, '') as priority_hint
                        from manual_review_queue
                        where trim(coalesce(latest_regulamento_file, '')) <> ''
                        """,
                        conn,
                    )
                )
            if "cedentes_sacados_candidates" in tables:
                frames.append(
                    pd.read_sql_query(
                        """
                        select coalesce(cnpj_fundo, '') as cnpj_fundo,
                               coalesce(fund_name, '') as fundo,
                               coalesce(setor_n1, '') as setor_n1,
                               coalesce(setor_n2, '') as setor_n2,
                               'cedentes_sacados_candidates' as source_table,
                               'source_cache' as source_field,
                               coalesce(source_cache, '') as source_value,
                               '' as document_date_hint,
                               coalesce(participant_type, '') as priority_hint
                        from cedentes_sacados_candidates
                        where trim(coalesce(source_cache, '')) <> ''
                        """,
                        conn,
                    )
                )
            if "pricing_tranche_enriched" in tables:
                frames.append(
                    pd.read_sql_query(
                        """
                        select coalesce(
                                   nullif(nullif(cnpj_emissor, 'nan'), ''),
                                   nullif(nullif(cnpj_2, 'nan'), ''),
                                   nullif(nullif(cnpj, 'nan'), ''),
                                   ''
                               ) as cnpj_fundo,
                               coalesce(fund_name_final, nome_emissor, fundo, '') as fundo,
                               coalesce(setor_n1, setor_n1_y, setor_n1_x, '') as setor_n1,
                               coalesce(setor_n2, setor_n2_y, setor_n2_x, '') as setor_n2,
                               'pricing_tranche_enriched' as source_table,
                               'fonte' as source_field,
                               coalesce(fonte, '') as source_value,
                               coalesce(data_deliberacao_dt, data_deliberacao, '') as document_date_hint,
                               coalesce(pricing_period, emission_cohort, '') as priority_hint
                        from pricing_tranche_enriched
                        where trim(coalesce(fonte, '')) <> ''
                        """,
                        conn,
                    )
                )
    except sqlite3.Error:
        return _empty_document_sources()
    if not frames:
        return _empty_document_sources()
    out = pd.concat(frames, ignore_index=True, sort=False)
    for col in _DOCUMENT_SOURCE_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[_DOCUMENT_SOURCE_COLUMNS].fillna("").astype(str)
    out["cnpj_fundo"] = out["cnpj_fundo"].map(normalize_cnpj)
    out = out[out["source_value"].str.strip() != ""].copy()
    return out.reset_index(drop=True)


def scan_regulatory_extraction_files(extractions_dir: Path) -> pd.DataFrame:
    """Expose local JSON extraction artifacts as document inventory inputs."""
    if not extractions_dir.exists():
        return _empty_document_sources()
    rows = []
    for path in sorted(extractions_dir.glob("*/*.local.json")):
        cnpj = normalize_cnpj(path.parent.name)
        if not cnpj:
            continue
        rows.append(
            {
                "cnpj_fundo": cnpj,
                "fundo": "",
                "setor_n1": "",
                "setor_n2": "",
                "source_table": "regulatory_extractions",
                "source_field": "local_json",
                "source_value": str(path),
                "document_date_hint": "",
                "priority_hint": "",
            }
        )
    if not rows:
        return _empty_document_sources()
    return pd.DataFrame(rows, columns=_DOCUMENT_SOURCE_COLUMNS)


def _first_nonempty(values: pd.Series) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _join_unique(values: pd.Series, sep: str = " | ", limit: int = 8) -> str:
    seen: list[str] = []
    for value in values:
        for part in str(value or "").split("|"):
            text = part.strip()
            if text and text not in seen:
                seen.append(text)
            if len(seen) >= limit:
                return sep.join(seen)
    return sep.join(seen)


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _document_name(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    first = re.split(r"\s+·\s+", text, maxsplit=1)[0].strip()
    return Path(first).name or first


def _document_id(value: object) -> str:
    text = str(value or "")
    patterns = [
        r"\bID\s*(\d{4,})\b",
        r"(?:^|/)(\d{4,})_",
        r"(?:^|/)(\d{4,})\.local\.json$",
        r"\b(\d{5,})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _parse_document_date(*values: object) -> str:
    for value in values:
        text = str(value or "")
        if not text.strip():
            continue
        match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
        if match:
            return match.group(1)
        match = re.search(r"\b(\d{1,2}/\d{1,2}/20\d{2})\b", text)
        candidate = match.group(1) if match else text
        parsed = pd.to_datetime(pd.Series([candidate]), errors="coerce", dayfirst=True).iloc[0]
        if pd.notna(parsed):
            return parsed.date().isoformat()
    return ""


def classify_document(value: object) -> str:
    text = str(value or "").lower()
    replacements = {
        "ç": "c",
        "ã": "a",
        "á": "a",
        "à": "a",
        "â": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    if "regulamento" in text:
        return "regulamento"
    if any(token in text for token in ["assembleia", "ata_", "ata-", "ata "]):
        return "assembleia"
    if any(token in text for token in ["suplemento", "emissao", "encerramento", "aviso", "anuncio", "oferta"]):
        return "emissao"
    if "rating" in text:
        return "rating"
    if "informe" in text:
        return "informe"
    if "demonstr" in text or "dfp" in text:
        return "demonstracao_financeira"
    if text.endswith(".local.json"):
        return "extracao_json"
    if text.endswith(".txt"):
        return "cache_texto"
    return "outro"


def _resolve_document_path(source_value: object, cnpj: object, root: Path) -> Path | None:
    text = str(source_value or "").strip()
    if not text:
        return None
    first = re.split(r"\s+·\s+", text, maxsplit=1)[0].strip()
    if not first:
        return None
    cnpj_digits = normalize_cnpj(cnpj)
    raw_path = Path(first)
    candidates: list[Path] = [raw_path if raw_path.is_absolute() else root / raw_path]
    doc_name = Path(first).name
    if cnpj_digits and doc_name:
        candidates.append(root / "data" / "raw" / cnpj_digits / doc_name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    if "/" in first or "\\" in first:
        return candidates[0]
    return None


def _content_kind(path: Path | None, document_name: str) -> str:
    suffix = (path.suffix if path is not None else Path(document_name).suffix).lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".txt":
        return "text_cache"
    if suffix == ".json":
        return "extraction_json"
    return "reference"


def _suggested_stage(content_kind: str, local_exists: bool) -> str:
    if not local_exists:
        return "discover_download"
    if content_kind == "pdf":
        return "ocr_parse_extract"
    if content_kind == "text_cache":
        return "parse_extract"
    if content_kind == "extraction_json":
        return "consolidate_extraction"
    return "classify_enrich"


def _document_file_info(path: Path | None, root: Path, max_hash_bytes: int) -> dict[str, object]:
    if path is None:
        return {"local_path": "", "local_exists": False, "bytes": 0, "sha256": "", "hash_status": "missing_path"}
    display = _display_path(path, root)
    if not path.exists():
        return {"local_path": display, "local_exists": False, "bytes": 0, "sha256": "", "hash_status": "missing_file"}
    size = path.stat().st_size
    if size > max_hash_bytes:
        return {
            "local_path": display,
            "local_exists": True,
            "bytes": int(size),
            "sha256": "",
            "hash_status": "skipped_large_file",
        }
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "local_path": display,
        "local_exists": True,
        "bytes": int(size),
        "sha256": digest.hexdigest(),
        "hash_status": "hashed",
    }


def build_document_inventory(
    source_rows: pd.DataFrame,
    *,
    fund_universe: pd.DataFrame | None = None,
    extraction_rows: pd.DataFrame | None = None,
    root: Path | None = None,
    max_hash_bytes: int = 25 * 1024 * 1024,
) -> pd.DataFrame:
    root = Path(".") if root is None else root
    frames = []
    if source_rows is not None and not source_rows.empty:
        frames.append(source_rows.copy())
    if extraction_rows is not None and not extraction_rows.empty:
        frames.append(extraction_rows.copy())
    if not frames:
        return pd.DataFrame()
    sources = pd.concat(frames, ignore_index=True, sort=False)
    for col in _DOCUMENT_SOURCE_COLUMNS:
        if col not in sources.columns:
            sources[col] = ""
    sources = sources[_DOCUMENT_SOURCE_COLUMNS].fillna("").astype(str)
    sources["cnpj_fundo"] = sources["cnpj_fundo"].map(normalize_cnpj)
    sources = sources[sources["source_value"].str.strip() != ""].copy()
    if sources.empty:
        return pd.DataFrame()

    if fund_universe is not None and not fund_universe.empty:
        funds = fund_universe.copy()
        id_col = "cnpj" if "cnpj" in funds.columns else "cnpj_fundo"
        funds["cnpj_lookup"] = funds[id_col].map(normalize_cnpj)
        enrich_cols = [
            col
            for col in [
                "cnpj_lookup",
                "fund_name_final",
                "setor_n1",
                "setor_n2",
                "first_offer_year",
                "emission_cohort",
                "valid_volume_2025_brl",
                "valid_volume_2026_brl",
                "has_regulatory_matrix",
            ]
            if col in funds.columns
        ]
        sources = sources.merge(
            funds[enrich_cols].drop_duplicates("cnpj_lookup"),
            left_on="cnpj_fundo",
            right_on="cnpj_lookup",
            how="left",
        )
        for col in ["fundo", "setor_n1", "setor_n2"]:
            fund_col = "fund_name_final" if col == "fundo" else f"{col}_y"
            source_col = col if col in sources.columns else f"{col}_x"
            if fund_col in sources.columns and source_col in sources.columns:
                sources[source_col] = sources[source_col].where(
                    sources[source_col].astype(str).str.strip() != "",
                    sources[fund_col].fillna("").astype(str),
                )
        for col in ["setor_n1", "setor_n2"]:
            alt = f"{col}_x"
            if alt in sources.columns and col not in sources.columns:
                sources[col] = sources[alt]

    rows = []
    for _, row in sources.iterrows():
        source_value = row.get("source_value", "")
        doc_name = _document_name(source_value)
        local_path = _resolve_document_path(source_value, row.get("cnpj_fundo", ""), root)
        info = _document_file_info(local_path, root, max_hash_bytes=max_hash_bytes)
        content_kind = _content_kind(local_path, doc_name)
        document_class = classify_document(f"{doc_name} {source_value}")
        document_date = _parse_document_date(source_value, row.get("document_date_hint", ""))
        key_seed = info["local_path"] or "|".join(
            [
                str(row.get("cnpj_fundo", "")),
                doc_name,
                _document_id(source_value),
                str(row.get("source_table", "")),
            ]
        )
        first_offer_year = pd.to_numeric(pd.Series([row.get("first_offer_year", "")]), errors="coerce").iloc[0]
        year_from_doc = pd.to_numeric(pd.Series([document_date[:4] if document_date else ""]), errors="coerce").iloc[0]
        priority_hint = str(row.get("priority_hint", "")) + " " + str(row.get("emission_cohort", ""))
        priority = (
            (pd.notna(year_from_doc) and int(year_from_doc) in {2025, 2026})
            or (pd.notna(first_offer_year) and int(first_offer_year) in {2025, 2026})
            or bool(re.search(r"\b202[56]\b|2025|2026", priority_hint))
        )
        rows.append(
            {
                "document_key": hashlib.sha1(str(key_seed).encode("utf-8", errors="ignore")).hexdigest()[:16],
                "cnpj_fundo": row.get("cnpj_fundo", ""),
                "fundo": row.get("fundo", ""),
                "setor_n1": row.get("setor_n1", ""),
                "setor_n2": row.get("setor_n2", ""),
                "documento_origem": doc_name,
                "documento_id": _document_id(source_value),
                "document_class": document_class,
                "content_kind": content_kind,
                "document_date": document_date,
                "source_table": row.get("source_table", ""),
                "source_field": row.get("source_field", ""),
                "source_value": source_value,
                "source_rows": 1,
                "priority_2025_2026": bool(priority),
                "first_offer_year": "" if pd.isna(first_offer_year) else int(first_offer_year),
                "emission_cohort": row.get("emission_cohort", ""),
                "suggested_stage": _suggested_stage(content_kind, bool(info["local_exists"])),
                "processing_status": "local_ready" if info["local_exists"] else "missing_local_file",
                **info,
            }
        )
    detailed = pd.DataFrame(rows)
    if detailed.empty:
        return detailed
    grouped = (
        detailed.groupby("document_key", dropna=False)
        .agg(
            cnpj_fundo=("cnpj_fundo", _first_nonempty),
            fundo=("fundo", _first_nonempty),
            setor_n1=("setor_n1", _first_nonempty),
            setor_n2=("setor_n2", _first_nonempty),
            documento_origem=("documento_origem", _first_nonempty),
            documento_id=("documento_id", _first_nonempty),
            document_class=("document_class", _first_nonempty),
            content_kind=("content_kind", _first_nonempty),
            document_date=("document_date", _first_nonempty),
            local_path=("local_path", _first_nonempty),
            local_exists=("local_exists", "max"),
            bytes=("bytes", "max"),
            sha256=("sha256", _first_nonempty),
            hash_status=("hash_status", _first_nonempty),
            source_table=("source_table", _join_unique),
            source_field=("source_field", _join_unique),
            source_value=("source_value", _first_nonempty),
            source_rows=("source_rows", "sum"),
            priority_2025_2026=("priority_2025_2026", "max"),
            first_offer_year=("first_offer_year", _first_nonempty),
            emission_cohort=("emission_cohort", _first_nonempty),
            suggested_stage=("suggested_stage", _first_nonempty),
            processing_status=("processing_status", _first_nonempty),
        )
        .reset_index()
    )
    grouped["local_exists"] = grouped["local_exists"].astype(bool)
    grouped["priority_2025_2026"] = grouped["priority_2025_2026"].astype(bool)
    grouped["bytes"] = pd.to_numeric(grouped["bytes"], errors="coerce").fillna(0).astype("int64")
    return grouped.sort_values(
        ["priority_2025_2026", "cnpj_fundo", "document_class", "document_date", "documento_origem"],
        ascending=[False, True, True, False, True],
    ).reset_index(drop=True)


def assign_document_chunks(
    inventory: pd.DataFrame,
    *,
    max_cnpjs: int = 40,
    max_documents: int = 250,
    max_bytes: int = 256 * 1024 * 1024,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if inventory is None or inventory.empty:
        return pd.DataFrame(), pd.DataFrame()
    frame = inventory.copy().reset_index(drop=True)
    frame["bytes"] = pd.to_numeric(frame.get("bytes"), errors="coerce").fillna(0).astype("int64")
    frame["priority_2025_2026"] = frame.get("priority_2025_2026", False).astype(bool)
    frame = frame.sort_values(
        ["priority_2025_2026", "cnpj_fundo", "document_class", "document_date", "documento_origem"],
        ascending=[False, True, True, False, True],
    ).reset_index(drop=True)

    assignments: dict[int, str] = {}
    chunk_rows: list[pd.DataFrame] = []
    current: list[int] = []
    current_cnpjs: set[str] = set()
    current_bytes = 0

    def flush() -> None:
        nonlocal current, current_cnpjs, current_bytes
        if not current:
            return
        chunk_id = f"doc-{len(chunk_rows) + 1:04d}"
        for idx in current:
            assignments[idx] = chunk_id
        subset = frame.loc[current].copy()
        chunk_rows.append(_document_chunk_summary(chunk_id, subset))
        current = []
        current_cnpjs = set()
        current_bytes = 0

    for idx, row in frame.iterrows():
        cnpj = str(row.get("cnpj_fundo", ""))
        row_bytes = int(row.get("bytes", 0) or 0)
        next_cnpjs = current_cnpjs | ({cnpj} if cnpj else set())
        should_flush = bool(
            current
            and (
                len(current) + 1 > max_documents
                or len(next_cnpjs) > max_cnpjs
                or (current_bytes + row_bytes > max_bytes and current_bytes > 0)
            )
        )
        if should_flush:
            flush()
        current.append(idx)
        if cnpj:
            current_cnpjs.add(cnpj)
        current_bytes += row_bytes
    flush()

    frame["chunk_id"] = frame.index.map(assignments)
    chunks = pd.concat(chunk_rows, ignore_index=True) if chunk_rows else pd.DataFrame()
    return frame, chunks


def _document_chunk_summary(chunk_id: str, subset: pd.DataFrame) -> pd.DataFrame:
    cnpjs = [value for value in subset["cnpj_fundo"].astype(str).dropna().unique().tolist() if value]
    classes = sorted(set(subset["document_class"].fillna("").astype(str)))
    source_tables = sorted(
        {
            part.strip()
            for value in subset["source_table"].fillna("").astype(str)
            for part in value.split("|")
            if part.strip()
        }
    )
    dates = subset["document_date"].fillna("").astype(str)
    dates = dates[dates != ""]
    row = {
        "chunk_id": chunk_id,
        "document_count": int(len(subset)),
        "cnpj_count": int(len(cnpjs)),
        "priority_2025_2026_docs": int(subset["priority_2025_2026"].astype(bool).sum()),
        "local_ready_docs": int(subset["local_exists"].astype(bool).sum()) if "local_exists" in subset else 0,
        "hashed_docs": int(subset["sha256"].fillna("").astype(str).str.len().gt(0).sum()) if "sha256" in subset else 0,
        "total_bytes": int(pd.to_numeric(subset["bytes"], errors="coerce").fillna(0).sum()),
        "document_date_min": dates.min() if not dates.empty else "",
        "document_date_max": dates.max() if not dates.empty else "",
        "document_classes": ", ".join(classes[:8]),
        "source_tables": ", ".join(source_tables[:8]),
        "sample_cnpjs": ", ".join(cnpjs[:8]),
        "rerun_command": f"python scripts/build_fidc_industry_documents.py --chunk-id {chunk_id}",
    }
    return pd.DataFrame([row])


def document_quality_summary(inventory: pd.DataFrame, chunks: pd.DataFrame) -> dict[str, object]:
    if inventory is None:
        inventory = pd.DataFrame()
    if chunks is None:
        chunks = pd.DataFrame()
    if inventory.empty:
        return {
            "document_rows": 0,
            "funds": 0,
            "chunks": 0,
            "coverage": {},
            "document_class_counts": {},
            "content_kind_counts": {},
        }
    local_exists = inventory["local_exists"].astype(bool) if "local_exists" in inventory else pd.Series(False, index=inventory.index)
    hashed = inventory["sha256"].fillna("").astype(str).str.len().gt(0) if "sha256" in inventory else pd.Series(False, index=inventory.index)
    priority = inventory["priority_2025_2026"].astype(bool) if "priority_2025_2026" in inventory else pd.Series(False, index=inventory.index)
    return {
        "document_rows": int(len(inventory)),
        "funds": int(inventory["cnpj_fundo"].nunique()) if "cnpj_fundo" in inventory else 0,
        "priority_2025_2026_docs": int(priority.sum()),
        "local_ready_docs": int(local_exists.sum()),
        "missing_local_docs": int((~local_exists).sum()),
        "hashed_docs": int(hashed.sum()),
        "chunks": int(len(chunks)),
        "max_documents_per_chunk": int(pd.to_numeric(chunks.get("document_count"), errors="coerce").max()) if not chunks.empty and "document_count" in chunks else 0,
        "max_cnpjs_per_chunk": int(pd.to_numeric(chunks.get("cnpj_count"), errors="coerce").max()) if not chunks.empty and "cnpj_count" in chunks else 0,
        "coverage": {
            "cnpj_fundo": _coverage(inventory, "cnpj_fundo"),
            "documento_origem": _coverage(inventory, "documento_origem"),
            "documento_id": _coverage(inventory, "documento_id"),
            "document_date": _coverage(inventory, "document_date"),
            "local_path": _coverage(inventory, "local_path"),
            "sha256": _coverage(inventory, "sha256"),
            "setor_n1": _coverage(inventory, "setor_n1"),
        },
        "document_class_counts": {
            str(k): int(v)
            for k, v in inventory["document_class"].fillna("outro").astype(str).value_counts().to_dict().items()
        }
        if "document_class" in inventory
        else {},
        "content_kind_counts": {
            str(k): int(v)
            for k, v in inventory["content_kind"].fillna("reference").astype(str).value_counts().to_dict().items()
        }
        if "content_kind" in inventory
        else {},
    }


def criteria_rule_id(row: pd.Series) -> str:
    key = "|".join(
        str(row.get(col, ""))
        for col in ["CNPJ", "Critério", "Chave", "Limite/regra", "Fonte"]
    )
    return hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:16]


def load_criteria_reviews(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=CRITERIA_REVIEW_COLUMNS)
    reviews = pd.read_csv(path, dtype=str, keep_default_na=False)
    for col in CRITERIA_REVIEW_COLUMNS:
        if col not in reviews.columns:
            reviews[col] = ""
    return reviews[CRITERIA_REVIEW_COLUMNS]


def save_criteria_reviews(reviews: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = reviews.copy()
    for col in CRITERIA_REVIEW_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[CRITERIA_REVIEW_COLUMNS].drop_duplicates("rule_id", keep="last")
    out.to_csv(path, index=False)


def load_criteria_source(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    if frame.empty:
        return frame
    if "CNPJ" in frame.columns:
        frame["CNPJ"] = frame["CNPJ"].map(normalize_cnpj)
    frame["rule_id"] = frame.apply(criteria_rule_id, axis=1)
    return frame


def _pct_values(text: object) -> list[float]:
    values: list[float] = []
    for match in re.finditer(r"(\d+(?:[\.,]\d+)?)\s*%", str(text or "")):
        try:
            values.append(float(match.group(1).replace(",", ".")))
        except ValueError:
            continue
    return values


def _review_text(reviews: pd.DataFrame, column: str, index: pd.Index) -> pd.Series:
    if column not in reviews.columns:
        return pd.Series("", index=index)
    return reviews[column].fillna("").astype(str).reindex(index).fillna("")


def build_criteria_structured(
    criteria: pd.DataFrame,
    reviews: pd.DataFrame | None = None,
    *,
    fund_universe: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if criteria is None or criteria.empty:
        return pd.DataFrame()
    reviews = pd.DataFrame(columns=CRITERIA_REVIEW_COLUMNS) if reviews is None else reviews.copy()
    source = criteria.copy()
    if "rule_id" not in source.columns:
        source["rule_id"] = source.apply(criteria_rule_id, axis=1)
    source["cnpj_fundo"] = source.get("CNPJ", pd.Series("", index=source.index)).map(normalize_cnpj)

    enrich = pd.DataFrame()
    if fund_universe is not None and not fund_universe.empty:
        funds = fund_universe.copy()
        id_col = "cnpj" if "cnpj" in funds.columns else "cnpj_fundo"
        funds["cnpj_fundo"] = funds[id_col].map(normalize_cnpj)
        enrich_cols = [
            col
            for col in [
                "cnpj_fundo",
                "fund_name_final",
                "setor_n1",
                "setor_n2",
                "first_offer_year",
                "emission_cohort",
                "pl_atual_brl",
                "has_regulatory_matrix",
            ]
            if col in funds.columns
        ]
        enrich = funds[enrich_cols].drop_duplicates("cnpj_fundo")

    if not enrich.empty:
        source = source.merge(enrich, on="cnpj_fundo", how="left", suffixes=("", "_fund"))

    for col in CRITERIA_REVIEW_COLUMNS:
        if col not in reviews.columns:
            reviews[col] = ""
    reviews = reviews[CRITERIA_REVIEW_COLUMNS].drop_duplicates("rule_id", keep="last")
    merged = source.merge(reviews, on="rule_id", how="left", suffixes=("", "_review"))
    idx = merged.index

    criterio_auto = _text(merged.get("Critério"), idx)
    chave_auto = _text(merged.get("Chave"), idx)
    limite_auto = _text(merged.get("Limite/regra"), idx)
    monitor_auto = _text(merged.get("Monitorabilidade IME"), idx)
    status_review = _text(merged.get("status"), idx).replace("", "pendente")

    criterio_final = criterio_auto.where(_review_text(merged, "criterio_revisado", idx).str.strip().eq(""), _review_text(merged, "criterio_revisado", idx))
    chave_final = chave_auto.where(_review_text(merged, "chave_revisada", idx).str.strip().eq(""), _review_text(merged, "chave_revisada", idx))
    limite_final = limite_auto.where(_review_text(merged, "limite_revisado", idx).str.strip().eq(""), _review_text(merged, "limite_revisado", idx))
    monitor_final = monitor_auto.where(
        _review_text(merged, "monitorabilidade_revisada", idx).str.strip().eq(""),
        _review_text(merged, "monitorabilidade_revisada", idx),
    )

    pct_auto = limite_auto.map(_pct_values)
    pct_min_auto = pct_auto.map(lambda values: min(values) if values else None)
    pct_max_auto = pct_auto.map(lambda values: max(values) if values else None)
    pct_manual = pd.to_numeric(_review_text(merged, "pct_min_revisado", idx).str.replace(",", ".", regex=False), errors="coerce")
    pct_min_final = pd.to_numeric(pct_min_auto, errors="coerce")
    pct_min_final = pct_min_final.where(pct_manual.isna(), pct_manual)
    confidence_manual = pd.to_numeric(_review_text(merged, "confianca_manual", idx).str.replace(",", ".", regex=False), errors="coerce")

    fonte = _text(merged.get("Fonte"), idx)
    documento = fonte.map(source_document)
    doc_date = fonte.map(_parse_document_date)
    first_offer_year = pd.to_numeric(merged.get("first_offer_year"), errors="coerce") if "first_offer_year" in merged else pd.Series(index=idx, dtype=float)
    year_from_doc = pd.to_numeric(doc_date.str.slice(0, 4), errors="coerce")
    priority = first_offer_year.isin([2025, 2026]) | year_from_doc.isin([2025, 2026]) | _text(merged.get("emission_cohort"), idx).str.contains("2025|2026", regex=True)

    status_curadoria = _text(merged.get("Status curadoria"), idx)
    base_score = pd.Series(0.45, index=idx)
    base_score += 0.15 * documento.ne("")
    base_score += 0.15 * pct_min_final.notna()
    base_score += 0.15 * status_curadoria.str.contains("estruturada|evidência|evidencia", case=False, na=False)
    base_score += 0.10 * monitor_final.str.contains("monitoravel|monitorável", case=False, na=False)
    score_final = base_score.clip(upper=0.9).where(confidence_manual.isna(), confidence_manual.clip(lower=0, upper=1))

    fundo_auto = _text(merged.get("Fundo"), idx)
    fundo_fund = _text(merged.get("fund_name_final"), idx)
    setor_csv = _text(merged.get("setor_n1"), idx)
    setor_fund = _text(merged.get("setor_n1_fund"), idx) if "setor_n1_fund" in merged else pd.Series("", index=idx)
    segmento_csv = _text(merged.get("setor_n2"), idx)
    segmento_fund = _text(merged.get("setor_n2_fund"), idx) if "setor_n2_fund" in merged else pd.Series("", index=idx)

    out = pd.DataFrame(
        {
            "rule_id": merged["rule_id"].astype(str),
            "cnpj_fundo": merged["cnpj_fundo"].astype(str),
            "fundo": fundo_auto.where(fundo_auto.str.strip() != "", fundo_fund),
            "setor": setor_csv.where(setor_csv.str.strip() != "", setor_fund),
            "segmento": segmento_csv.where(segmento_csv.str.strip() != "", segmento_fund),
            "criterio": criterio_final,
            "chave": chave_final,
            "limite_regra": limite_final,
            "pct_min": pct_min_final,
            "pct_max": pd.to_numeric(pct_max_auto, errors="coerce"),
            "monitorabilidade_ime": monitor_final,
            "metrica_ime_proxy": _text(merged.get("Métrica IME / proxy"), idx),
            "condicao_alerta_sugerida": _text(merged.get("Condição de alerta sugerida"), idx),
            "observacao_tecnica": _text(merged.get("Observação técnica"), idx),
            "fonte": fonte,
            "documento_origem": documento,
            "documento_id": fonte.map(_document_id),
            "document_date": doc_date,
            "pagina": fonte.map(extract_page),
            "status_curadoria": status_curadoria,
            "status_revisao": status_review,
            "ativo_curadoria": ~status_review.str.lower().eq("rejeitado"),
            "metodo_extracao": "triagem_documental_offline",
            "score_confianca_final": score_final,
            "periodo_prioritario": priority.map({True: "2025-2026 YTD", False: "histórico"}),
            "notas_revisao": _text(merged.get("notas"), idx),
            "first_offer_year": first_offer_year,
            "emission_cohort": _text(merged.get("emission_cohort"), idx),
            "pl_atual_brl": _num(merged.get("pl_atual_brl"), idx),
        }
    )
    return out.sort_values(
        ["periodo_prioritario", "chave", "score_confianca_final", "cnpj_fundo"],
        ascending=[True, True, False, True],
    ).reset_index(drop=True)


def criteria_quality_summary(
    criteria: pd.DataFrame,
    reviews: pd.DataFrame,
    structured: pd.DataFrame,
) -> dict[str, object]:
    if criteria is None:
        criteria = pd.DataFrame()
    if reviews is None:
        reviews = pd.DataFrame(columns=CRITERIA_REVIEW_COLUMNS)
    if structured is None:
        structured = pd.DataFrame()
    active = structured
    if "ativo_curadoria" in structured.columns:
        active = structured[structured["ativo_curadoria"].astype(str).str.lower().isin({"true", "1", "sim"})]
    sub = active[active["chave"].astype(str).eq("subordination_ratio_min")] if "chave" in active else pd.DataFrame()
    sub_values = pd.to_numeric(sub.get("pct_min"), errors="coerce").dropna() if not sub.empty else pd.Series(dtype=float)
    monitorable = active["monitorabilidade_ime"].astype(str).str.contains("monitoravel|monitorável", case=False, na=False) if "monitorabilidade_ime" in active else pd.Series(False, index=active.index)
    partial = active["monitorabilidade_ime"].astype(str).str.contains("parcial", case=False, na=False) if "monitorabilidade_ime" in active else pd.Series(False, index=active.index)
    score = pd.to_numeric(structured.get("score_confianca_final"), errors="coerce") if "score_confianca_final" in structured else pd.Series(dtype=float)
    status_counts = reviews["status"].replace("", "pendente").value_counts().to_dict() if "status" in reviews else {}
    return {
        "source_rows": int(len(criteria)),
        "source_funds": int(criteria["CNPJ"].nunique()) if "CNPJ" in criteria else 0,
        "structured_rows": int(len(structured)),
        "structured_funds": int(structured["cnpj_fundo"].nunique()) if "cnpj_fundo" in structured else 0,
        "active_rows": int(len(active)),
        "active_funds": int(active["cnpj_fundo"].nunique()) if "cnpj_fundo" in active else 0,
        "subordination_rows": int(len(sub)),
        "subordination_funds": int(sub["cnpj_fundo"].nunique()) if "cnpj_fundo" in sub else 0,
        "monitorable_rows": int(monitorable.sum()),
        "partial_rows": int(partial.sum()),
        "review_rows": int(len(reviews)),
        "review_status_counts": {str(k): int(v) for k, v in status_counts.items()},
        "coverage": {
            "cnpj_fundo": _coverage(structured, "cnpj_fundo"),
            "criterio": _coverage(structured, "criterio"),
            "chave": _coverage(structured, "chave"),
            "limite_regra": _coverage(structured, "limite_regra"),
            "pct_min": float(pd.to_numeric(structured.get("pct_min"), errors="coerce").notna().mean()) if "pct_min" in structured and len(structured) else 0.0,
            "monitorabilidade_ime": _coverage(structured, "monitorabilidade_ime"),
            "documento_origem": _coverage(structured, "documento_origem"),
            "document_date": _coverage(structured, "document_date"),
            "score_confianca_final": float(score.notna().mean()) if len(score) else 0.0,
        },
        "subordination": {
            "median": _json_float(sub_values.median()) if sub_values.notna().any() else None,
            "p25": _json_float(sub_values.quantile(0.25)) if sub_values.notna().any() else None,
            "p75": _json_float(sub_values.quantile(0.75)) if sub_values.notna().any() else None,
        },
        "score": {
            "median": _json_float(score.median()) if score.notna().any() else None,
            "p25": _json_float(score.quantile(0.25)) if score.notna().any() else None,
            "p75": _json_float(score.quantile(0.75)) if score.notna().any() else None,
        },
        "criteria_key_counts": {
            str(k): int(v)
            for k, v in structured["chave"].fillna("").astype(str).value_counts().to_dict().items()
        }
        if "chave" in structured
        else {},
    }


def file_fingerprint(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"path": str(path), "exists": False, "bytes": 0, "sha256": ""}
    if path.is_dir():
        return {
            "path": str(path),
            "exists": True,
            "bytes": 0,
            "sha256": "",
            "kind": "directory",
        }
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


def _safe_read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _artifact_info(info: object, *, fallback_path: Path | None = None) -> dict[str, object]:
    if isinstance(info, dict):
        path_value = info.get("path") or (str(fallback_path) if fallback_path is not None else "")
        if path_value:
            fingerprint = file_fingerprint(Path(str(path_value)))
            out = {**fingerprint, **info}
            out["exists"] = bool(fingerprint.get("exists"))
            out["bytes"] = fingerprint.get("bytes", info.get("bytes", 0))
            out["sha256"] = fingerprint.get("sha256", info.get("sha256", ""))
            out["path"] = str(path_value)
            return out
        return {**info, "path": ""}
    if fallback_path is None:
        return {"path": "", "exists": False, "bytes": 0, "sha256": ""}
    return file_fingerprint(fallback_path)


def _stage_status_counts(manifest: dict[str, object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for stage in manifest.get("stages", []):
        if not isinstance(stage, dict):
            continue
        status = str(stage.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _module_status(manifest: dict[str, object], artifacts: list[dict[str, object]]) -> str:
    if not manifest:
        return "missing"
    if any(item.get("required") is True and item.get("exists") is False for item in artifacts):
        return "missing_artifact"
    counts = _stage_status_counts(manifest)
    if any(status not in {"ok"} for status in counts):
        return "warning"
    return "ok"


def _manifest_artifacts(
    manifest: dict[str, object],
    *,
    module_id: str,
    manifest_path: Path,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group_name in ["inputs", "outputs"]:
        files = manifest.get(group_name, {})
        if not isinstance(files, dict):
            continue
        for artifact, info in files.items():
            fallback = manifest_path if artifact == "manifest" else None
            artifact_info = _artifact_info(info, fallback_path=fallback)
            rows.append(
                {
                    "module_id": module_id,
                    "group": group_name,
                    "artifact": str(artifact),
                    "required": group_name == "outputs",
                    **artifact_info,
                }
            )
    if not any(row["artifact"] == "manifest" and row["group"] == "outputs" for row in rows):
        rows.append(
            {
                "module_id": module_id,
                "group": "outputs",
                "artifact": "manifest",
                "required": True,
                **file_fingerprint(manifest_path),
            }
        )
    return rows


def _quality_pick(quality: dict[str, object], keys: list[str]) -> dict[str, object]:
    return {key: quality.get(key) for key in keys if key in quality}


def _build_base_monthly_module(industry_dir: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    metadata_path = industry_dir / "metadata.json"
    metadata = _safe_read_json(metadata_path)
    output_names = [
        "industry_monthly.csv",
        "vehicle_monthly.csv.gz",
        "update_audit_monthly.csv",
        "admin_monthly.csv",
        "flows_monthly.csv",
        "segments_monthly.csv",
        "prestadores_latest.csv",
        "universe_latest.csv",
    ]
    artifacts = [
        {
            "module_id": "base_monthly",
            "group": "outputs",
            "artifact": name,
            "required": True,
            **file_fingerprint(industry_dir / name),
        }
        for name in output_names
    ]
    artifacts.append(
        {
            "module_id": "base_monthly",
            "group": "outputs",
            "artifact": "metadata",
            "required": True,
            **file_fingerprint(metadata_path),
        }
    )
    missing_required = any(row.get("exists") is False for row in artifacts)
    module = {
        "id": "base_monthly",
        "label": "Base granular mensal",
        "status": "missing_artifact" if missing_required else "ok",
        "schema_version": "industry-monthly-base/v1",
        "pipeline": "industry_granular_ime",
        "generated_at_utc": metadata.get("gerado_em_utc", ""),
        "manifest_path": str(metadata_path),
        "command": "python scripts/build_fidc_industry_study.py --report",
        "cadence": "mensal",
        "depends_on": ["CVM informes mensais", "Cadastro CVM"],
        "stage_status_counts": {"ok": 1} if not missing_required else {"missing_artifact": 1},
        "artifact_count": len(artifacts),
        "artifacts_present": sum(1 for item in artifacts if item.get("exists") is True),
        "quality_highlights": {
            "competencia_inicial": metadata.get("competencia_inicial", ""),
            "competencia_final": metadata.get("competencia_final", ""),
            "competencia_snapshot": metadata.get("competencia_snapshot", ""),
            "n_competencias": metadata.get("n_competencias", 0),
        },
    }
    return module, artifacts


def _build_manifest_module(
    *,
    industry_dir: Path,
    module_id: str,
    label: str,
    manifest_name: str,
    command: str,
    cadence: str,
    depends_on: list[str],
    quality_keys: list[str],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    manifest_path = industry_dir / manifest_name
    manifest = _safe_read_json(manifest_path)
    artifacts = _manifest_artifacts(manifest, module_id=module_id, manifest_path=manifest_path) if manifest else [
        {
            "module_id": module_id,
            "group": "outputs",
            "artifact": "manifest",
            "required": True,
            **file_fingerprint(manifest_path),
        }
    ]
    quality = manifest.get("quality", {}) if isinstance(manifest.get("quality"), dict) else {}
    module = {
        "id": module_id,
        "label": label,
        "status": _module_status(manifest, artifacts),
        "schema_version": manifest.get("schema_version", ""),
        "pipeline": manifest.get("pipeline", ""),
        "generated_at_utc": manifest.get("generated_at_utc", ""),
        "manifest_path": str(manifest_path),
        "command": command,
        "cadence": cadence,
        "depends_on": depends_on,
        "stage_status_counts": _stage_status_counts(manifest),
        "stage_count": len(manifest.get("stages", [])) if isinstance(manifest.get("stages"), list) else 0,
        "artifact_count": len(artifacts),
        "artifacts_present": sum(1 for item in artifacts if item.get("exists") is True),
        "quality_highlights": _quality_pick(quality, quality_keys),
    }
    return module, artifacts


def _latest_iso(values: list[object]) -> str:
    parsed: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text:
            parsed.append(text)
    return max(parsed) if parsed else ""


def build_industry_pipeline_index(
    *,
    industry_dir: Path,
    output_path: Path | None = None,
) -> dict[str, object]:
    """Build the monthly refresh cockpit for all Industry tab modules."""

    module_specs = [
        {
            "module_id": "issuance",
            "label": "Emissões e ofertas",
            "manifest_name": "industry_issuance_manifest.json",
            "command": "python scripts/build_fidc_industry_issuance.py",
            "cadence": "quando Estratégia/ofertas mudar",
            "depends_on": ["SQLite da aba Estratégia"],
            "quality_keys": [
                "annual_years",
                "annual_volume_conservador_brl",
                "annual_emissores_cnpj",
                "sector_year_rows",
                "tranche_rows",
                "tranche_funds",
            ],
        },
        {
            "module_id": "documents",
            "label": "Inventário documental",
            "manifest_name": "industry_document_manifest.json",
            "command": "python scripts/build_fidc_industry_documents.py",
            "cadence": "incremental/chunks",
            "depends_on": ["SQLite da aba Estratégia", "data/regulatory_extractions"],
            "quality_keys": [
                "document_rows",
                "funds",
                "priority_2025_2026_docs",
                "local_ready_docs",
                "missing_local_docs",
                "chunks",
                "max_documents_per_chunk",
                "max_cnpjs_per_chunk",
            ],
        },
        {
            "module_id": "cedentes",
            "label": "Cedentes e sacados",
            "manifest_name": "industry_pipeline_manifest.json",
            "command": "python scripts/build_fidc_industry_cedentes.py",
            "cadence": "após extração/curadoria",
            "depends_on": ["SQLite da aba Estratégia", "revisões manuais da UI", "base granular mensal"],
            "quality_keys": [
                "candidate_rows",
                "candidate_funds",
                "structured_rows",
                "structured_funds",
                "priority_2025_2026_rows",
                "priority_2025_2026_funds",
                "review_rows",
            ],
        },
        {
            "module_id": "criteria",
            "label": "Critérios e subordinação",
            "manifest_name": "industry_criteria_manifest.json",
            "command": "python scripts/build_fidc_industry_criteria.py",
            "cadence": "após curadoria regulatória",
            "depends_on": ["data/regulatory_profiles/all_fidcs_criteria_monitoraveis_ime.csv", "revisões manuais da UI"],
            "quality_keys": [
                "source_rows",
                "source_funds",
                "structured_rows",
                "structured_funds",
                "subordination_rows",
                "subordination_funds",
                "monitorable_rows",
                "partial_rows",
                "review_rows",
            ],
        },
        {
            "module_id": "fund_snapshot",
            "label": "Snapshot unificado por FIDC",
            "manifest_name": "industry_fund_snapshot_manifest.json",
            "command": "python scripts/build_fidc_industry_fund_snapshot.py",
            "cadence": "após módulos estruturados",
            "depends_on": ["base granular mensal", "emissões", "documentos", "cedentes", "critérios"],
            "quality_keys": [
                "fund_rows",
                "pl_total_brl",
                "with_issuance_2025_2026",
                "with_documents",
                "with_cedentes",
                "with_criteria",
                "with_subordination_min",
            ],
        },
    ]

    base_module, base_artifacts = _build_base_monthly_module(industry_dir)
    modules = [base_module]
    artifact_rows = base_artifacts
    for spec in module_specs:
        module, artifacts = _build_manifest_module(industry_dir=industry_dir, **spec)
        modules.append(module)
        artifact_rows.extend(artifacts)

    refresh_plan = [
        {
            "order": 1,
            "module_id": "base_monthly",
            "label": "Atualizar informes mensais e foto granular",
            "command": "python scripts/build_fidc_industry_study.py --report",
            "reason": "Atualiza PL, fluxos, inadimplência, FIC-FIDC overlay, prestadores e auditoria de cobertura.",
            "incremental_note": "Baixa/usa apenas competências necessárias e materializa CSVs por veículo x competência.",
        },
        {
            "order": 2,
            "module_id": "issuance",
            "label": "Reconciliar emissões/ofertas",
            "command": "python scripts/build_fidc_industry_issuance.py",
            "reason": "Refaz séries de volume anual, emissores, setor x ano e tranches documentais.",
            "incremental_note": "Lê o SQLite da Estratégia já estruturado; não depende de Informe Mensal.",
        },
        {
            "order": 3,
            "module_id": "documents",
            "label": "Inventariar documentação pública",
            "command": "python scripts/build_fidc_industry_documents.py",
            "reason": "Atualiza fingerprints, classes documentais e chunks pequenos para processamento posterior.",
            "incremental_note": "Use --chunk-id doc-0001 para rodar ou depurar lotes sem reprocessar a indústria toda.",
        },
        {
            "order": 4,
            "module_id": "cedentes",
            "label": "Regerar base de cedentes/sacados",
            "command": "python scripts/build_fidc_industry_cedentes.py",
            "reason": "Aplica revisões manuais e expõe participantes para heatmaps e deep dives.",
            "incremental_note": "A curadoria continua sendo feita pela UI e reaplicada pelo overlay persistido.",
        },
        {
            "order": 5,
            "module_id": "criteria",
            "label": "Regerar critérios e subordinação mínima",
            "command": "python scripts/build_fidc_industry_criteria.py",
            "reason": "Atualiza regras monitoráveis, sub mínima e status de revisão por fundo.",
            "incremental_note": "Revisões feitas pela UI são reaplicadas antes da consolidação.",
        },
        {
            "order": 6,
            "module_id": "fund_snapshot",
            "label": "Regerar snapshot unificado por FIDC",
            "command": "python scripts/build_fidc_industry_fund_snapshot.py",
            "reason": "Consolida uma linha por CNPJ com IME, emissões, documentos, cedentes e critérios.",
            "incremental_note": "Não apaga granularidade; apenas resume camadas já materializadas e preserva caminhos de origem.",
        },
        {
            "order": 7,
            "module_id": "pipeline_index",
            "label": "Atualizar cockpit do pipeline",
            "command": "python scripts/build_fidc_industry_pipeline_index.py",
            "reason": "Recalcula hashes, freshness, status dos módulos e checklist mensal visível na aba Pipeline.",
            "incremental_note": "Não reprocessa dados; apenas lê manifests e arquivos já materializados.",
        },
    ]

    status_counts: dict[str, int] = {}
    for module in modules:
        status = str(module.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    generated_values = [module.get("generated_at_utc") for module in modules if module.get("generated_at_utc")]
    artifact_total = len(artifact_rows)
    artifact_present = sum(1 for item in artifact_rows if item.get("exists") is True)
    base_meta = base_module.get("quality_highlights", {})
    criteria_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "criteria"), {})
    document_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "documents"), {})
    cedente_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "cedentes"), {})
    issuance_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "issuance"), {})
    snapshot_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "fund_snapshot"), {})
    criteria_manifest = _safe_read_json(industry_dir / "industry_criteria_manifest.json")
    subordination = criteria_manifest.get("quality", {}).get("subordination", {}) if isinstance(criteria_manifest.get("quality"), dict) else {}

    return {
        "schema_version": "industry-pipeline-index/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_monthly_refresh",
        "industry_dir": str(industry_dir),
        "output_path": str(output_path) if output_path is not None else str(industry_dir / "industry_pipeline_index.json"),
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "manual_review_in_app": True,
            "macbook_air_m4_friendly": True,
            "notes": [
                "Este índice não reprocessa dados; ele agrega manifests e fingerprints para orientar a atualização mensal.",
                "Cada módulo pode ser reexecutado de forma independente e possui artefatos persistidos.",
                "Documentos são divididos em chunks para processamento incremental confortável em notebook.",
            ],
        },
        "quality_rollup": {
            "modules_total": len(modules),
            "module_status_counts": status_counts,
            "artifacts_total": artifact_total,
            "artifacts_present": artifact_present,
            "artifacts_missing": artifact_total - artifact_present,
            "latest_module_generated_at_utc": _latest_iso(generated_values),
            "competencia_final": base_meta.get("competencia_final", ""),
            "competencia_snapshot": base_meta.get("competencia_snapshot", ""),
            "document_chunks": document_quality.get("chunks", 0),
            "max_documents_per_chunk": document_quality.get("max_documents_per_chunk", 0),
            "cedentes_structured_rows": cedente_quality.get("structured_rows", 0),
            "criteria_structured_rows": criteria_quality.get("structured_rows", 0),
            "subordination_funds": criteria_quality.get("subordination_funds", 0),
            "subordination_median_pct": subordination.get("median") if isinstance(subordination, dict) else None,
            "issuance_volume_conservador_brl": issuance_quality.get("annual_volume_conservador_brl", 0),
            "fund_snapshot_rows": snapshot_quality.get("fund_rows", 0),
            "fund_snapshot_with_cedentes": snapshot_quality.get("with_cedentes", 0),
            "fund_snapshot_with_criteria": snapshot_quality.get("with_criteria", 0),
        },
        "modules": modules,
        "refresh_plan": refresh_plan,
        "artifact_index": artifact_rows,
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


def build_criteria_pipeline_manifest(
    *,
    industry_dir: Path,
    strategy_db: Path,
    criteria_source_path: Path,
    reviews_path: Path,
    output_path: Path,
    manifest_path: Path,
    criteria: pd.DataFrame,
    reviews: pd.DataFrame,
    fund_universe: pd.DataFrame,
    structured: pd.DataFrame,
) -> dict[str, object]:
    quality = criteria_quality_summary(criteria, reviews, structured)
    return {
        "schema_version": "industry-criteria-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_criteria_structured",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "macbook_air_m4_friendly": True,
            "notes": [
                "Este modulo consolida criterios monitoraveis e subordinação minima ja extraidos documentalmente.",
                "Revisoes manuais sao aplicadas como overlay persistido pela UI; nao editar CSV interno manualmente.",
                "Percentuais em uma mesma regra usam o menor valor explicito como minimo conservador.",
            ],
        },
        "inputs": {
            "strategy_db": file_fingerprint(strategy_db),
            "criteria_source": file_fingerprint(criteria_source_path),
            "manual_reviews": file_fingerprint(reviews_path),
        },
        "outputs": {
            "criteria_structured": file_fingerprint(output_path),
            "manifest": {"path": str(manifest_path)},
        },
        "stages": [
            {
                "id": "load_documentary_criteria",
                "label": "Critérios documentais",
                "status": "ok" if not criteria.empty else "empty",
                "input": str(criteria_source_path),
                "output": "memoria:all_fidcs_criteria_monitoraveis_ime",
                "rows": int(len(criteria)),
                "funds": int(criteria["CNPJ"].nunique()) if "CNPJ" in criteria else 0,
                "rerun": "python scripts/classify_fidc_sectors_and_practices.py",
            },
            {
                "id": "apply_manual_review",
                "label": "Revisao manual persistida",
                "status": "ok",
                "input": str(reviews_path),
                "output": "memoria:criteria_review_overlay",
                "rows": int(len(reviews)),
                "rerun": "Editar pela aba Indústria > Critérios; nao editar CSV manualmente.",
            },
            {
                "id": "enrich_fund_universe",
                "label": "Enriquecimento por universo/ofertas",
                "status": "ok" if not fund_universe.empty else "empty",
                "input": str(strategy_db),
                "output": "memoria:fund_universe",
                "rows": int(len(fund_universe)),
                "funds": int(fund_universe["cnpj"].nunique()) if "cnpj" in fund_universe else 0,
                "rerun": "python scripts/export_fidc_strategy_audit_report.py",
            },
            {
                "id": "normalize_structured_criteria",
                "label": "Base estruturada de critérios",
                "status": "ok" if not structured.empty else "empty",
                "input": "memoria:criteria+review_overlay+fund_universe",
                "output": str(output_path),
                "rows": int(len(structured)),
                "funds": int(structured["cnpj_fundo"].nunique()) if "cnpj_fundo" in structured else 0,
                "rerun": "python scripts/build_fidc_industry_criteria.py",
            },
        ],
        "quality": quality,
    }


def _normalize_snapshot_id(frame: pd.DataFrame, preferred: str = "cnpj_fundo") -> pd.DataFrame:
    out = frame.copy()
    if preferred not in out.columns:
        fallback = "cnpj" if "cnpj" in out.columns else ""
        out[preferred] = out[fallback] if fallback else ""
    out[preferred] = out[preferred].map(normalize_cnpj)
    return out[out[preferred].astype(str).str.len().eq(14)].copy()


def _bool_series(series: pd.Series | None, index: pd.Index | None = None) -> pd.Series:
    values = _text(series, index=index).str.lower().str.strip()
    return values.isin({"true", "1", "sim", "s", "yes"})


def _median_numeric(values: pd.Series) -> float | None:
    number = pd.to_numeric(values, errors="coerce")
    if not number.notna().any():
        return None
    return _json_float(number.median())


def _latest_text(values: pd.Series) -> str:
    clean = values.fillna("").astype(str).str.strip()
    clean = clean[clean.ne("")]
    if clean.empty:
        return ""
    return str(clean.max())


def _aggregate_strategy_universe(fund_universe: pd.DataFrame) -> pd.DataFrame:
    if fund_universe is None or fund_universe.empty:
        return pd.DataFrame()
    frame = fund_universe.copy()
    frame["cnpj_fundo"] = _text(frame.get("cnpj"), frame.index).map(normalize_cnpj)
    frame = frame[frame["cnpj_fundo"].str.len().eq(14)].copy()
    if frame.empty:
        return frame
    rows = []
    for cnpj, group in frame.groupby("cnpj_fundo", dropna=False):
        row: dict[str, object] = {
            "cnpj_fundo": cnpj,
            "fundo_estrategia": _first_nonempty(group.get("fund_name_final", pd.Series(dtype=str))),
            "segmento_estrategia": _first_nonempty(group.get("setor_n1", pd.Series(dtype=str))),
            "subsegmento_estrategia": _first_nonempty(group.get("setor_n2", pd.Series(dtype=str))),
            "emission_cohort": _first_nonempty(group.get("emission_cohort", pd.Series(dtype=str))),
            "first_offer_year": _json_float(_num(group.get("first_offer_year"), group.index).replace(0, pd.NA).min()),
            "has_regulatory_matrix": int(_num(group.get("has_regulatory_matrix"), group.index).gt(0).any()),
            "latest_regulamento_date": _latest_text(group.get("latest_regulamento_date", pd.Series(dtype=str))),
        }
        for year in ISSUANCE_YEARS:
            row[f"volume_{year}_brl"] = float(_num(group.get(f"volume_{year}_brl"), group.index).sum())
            row[f"valid_volume_{year}_brl"] = float(_num(group.get(f"valid_volume_{year}_brl"), group.index).sum())
            row[f"offers_{year}"] = int(_num(group.get(f"offers_{year}"), group.index).sum())
            row[f"emitted_{year}"] = bool(
                row[f"volume_{year}_brl"] > 0 or row[f"valid_volume_{year}_brl"] > 0 or row[f"offers_{year}"] > 0
            )
        row["valid_volume_2024_2026_brl"] = float(sum(float(row.get(f"valid_volume_{year}_brl", 0)) for year in ISSUANCE_YEARS))
        rows.append(row)
    return pd.DataFrame(rows)


def _aggregate_tranches(tranches: pd.DataFrame) -> pd.DataFrame:
    if tranches is None or tranches.empty:
        return pd.DataFrame()
    frame = _normalize_snapshot_id(tranches)
    if frame.empty:
        return frame
    frame["volume_brl"] = _num(frame.get("volume_brl"), frame.index)
    frame["ano"] = _num(frame.get("ano"), frame.index).round().astype("Int64")
    rows = []
    for cnpj, group in frame.groupby("cnpj_fundo", dropna=False):
        row: dict[str, object] = {
            "cnpj_fundo": cnpj,
            "tranche_rows": int(len(group)),
            "tranche_volume_brl": float(group["volume_brl"].sum()),
            "indexadores": _join_unique(group.get("indexador", pd.Series(dtype=str)), limit=6),
            "tipo_cotas": _join_unique(group.get("tipo_cota", pd.Series(dtype=str)), limit=6),
            "pricing_documentos": _join_unique(group.get("documento_origem", pd.Series(dtype=str)), limit=5),
            "pricing_score_mediana": _median_numeric(group.get("score_confianca", pd.Series(dtype=float))),
        }
        for year in ISSUANCE_YEARS:
            row[f"tranche_volume_{year}_brl"] = float(group.loc[group["ano"].eq(year), "volume_brl"].sum())
            row[f"tranche_rows_{year}"] = int(group["ano"].eq(year).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def _aggregate_cedentes_snapshot(cedentes: pd.DataFrame) -> pd.DataFrame:
    if cedentes is None or cedentes.empty:
        return pd.DataFrame()
    frame = _normalize_snapshot_id(cedentes)
    if frame.empty:
        return frame
    if "ativo_curadoria" in frame.columns:
        frame = frame[_bool_series(frame["ativo_curadoria"], frame.index)].copy()
    frame = frame[frame.get("razao_social", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip().ne("")]
    if frame.empty:
        return frame
    rows = []
    for cnpj, group in frame.groupby("cnpj_fundo", dropna=False):
        participant = group.get("participant_type", pd.Series("", index=group.index)).fillna("").astype(str)
        row = {
            "cnpj_fundo": cnpj,
            "cedente_rows": int(len(group)),
            "cedente_originador_count": int(participant.eq("cedente_originador").sum()),
            "sacado_devedor_count": int(participant.eq("sacado_devedor").sum()),
            "participantes_count": int(group.get("razao_social", pd.Series(dtype=str)).nunique()),
            "cedentes_top": _join_unique(group.get("razao_social", pd.Series(dtype=str)), limit=6),
            "grupos_economicos": _join_unique(group.get("grupo_economico", pd.Series(dtype=str)), limit=6),
            "tipos_participante": _join_unique(group.get("tipo_participante", pd.Series(dtype=str)), limit=5),
            "cedente_statuses": _join_unique(group.get("status_revisao", pd.Series(dtype=str)), limit=5),
            "cedente_documentos": _join_unique(group.get("documento_origem", pd.Series(dtype=str)), limit=5),
            "cedente_score_mediana": _median_numeric(group.get("score_confianca_final", pd.Series(dtype=float))),
            "cedentes_prioridade_2025_2026": int(
                group.get("periodo_prioritario", pd.Series("", index=group.index)).astype(str).eq("2025-2026 YTD").sum()
            ),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _aggregate_criteria_snapshot(criteria: pd.DataFrame) -> pd.DataFrame:
    if criteria is None or criteria.empty:
        return pd.DataFrame()
    frame = _normalize_snapshot_id(criteria)
    if frame.empty:
        return frame
    if "ativo_curadoria" in frame.columns:
        frame = frame[_bool_series(frame["ativo_curadoria"], frame.index)].copy()
    if frame.empty:
        return frame
    frame["pct_min"] = pd.to_numeric(frame.get("pct_min"), errors="coerce")
    rows = []
    for cnpj, group in frame.groupby("cnpj_fundo", dropna=False):
        monitor = group.get("monitorabilidade_ime", pd.Series("", index=group.index)).fillna("").astype(str)
        sub = group[group.get("chave", pd.Series("", index=group.index)).astype(str).eq("subordination_ratio_min")]
        row = {
            "cnpj_fundo": cnpj,
            "criteria_rows": int(len(group)),
            "criteria_monitorable_rows": int(monitor.eq("monitoravel").sum()),
            "criteria_partial_rows": int(monitor.eq("parcial").sum()),
            "criteria_not_monitorable_rows": int(monitor.eq("nao_monitoravel").sum()),
            "criteria_subordination_rows": int(len(sub)),
            "sub_min_pct_median": _median_numeric(sub.get("pct_min", pd.Series(dtype=float))),
            "sub_min_pct_min": _json_float(pd.to_numeric(sub.get("pct_min", pd.Series(dtype=float)), errors="coerce").min()) if not sub.empty else None,
            "sub_min_pct_max": _json_float(pd.to_numeric(sub.get("pct_min", pd.Series(dtype=float)), errors="coerce").max()) if not sub.empty else None,
            "criteria_keys": _join_unique(group.get("chave", pd.Series(dtype=str)), limit=8),
            "criteria_documentos": _join_unique(group.get("documento_origem", pd.Series(dtype=str)), limit=5),
            "criteria_score_mediana": _median_numeric(group.get("score_confianca_final", pd.Series(dtype=float))),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _aggregate_document_snapshot(documents: pd.DataFrame) -> pd.DataFrame:
    if documents is None or documents.empty:
        return pd.DataFrame()
    frame = _normalize_snapshot_id(documents)
    if frame.empty:
        return frame
    local = _bool_series(frame.get("local_exists"), frame.index)
    priority = _bool_series(frame.get("priority_2025_2026"), frame.index)
    frame = frame.assign(_local_exists=local, _priority=priority)
    rows = []
    for cnpj, group in frame.groupby("cnpj_fundo", dropna=False):
        row = {
            "cnpj_fundo": cnpj,
            "document_rows": int(len(group)),
            "document_local_ready": int(group["_local_exists"].sum()),
            "document_missing_local": int((~group["_local_exists"]).sum()),
            "document_priority_2025_2026": int(group["_priority"].sum()),
            "document_classes": _join_unique(group.get("document_class", pd.Series(dtype=str)), limit=8),
            "document_content_kinds": _join_unique(group.get("content_kind", pd.Series(dtype=str)), limit=5),
            "document_chunk_ids": _join_unique(group.get("chunk_id", pd.Series(dtype=str)), limit=6),
            "document_latest_date": _latest_text(group.get("document_date", pd.Series(dtype=str))),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def build_industry_fund_snapshot(
    *,
    vehicle_latest: pd.DataFrame,
    fund_universe: pd.DataFrame | None = None,
    issuance_tranches: pd.DataFrame | None = None,
    cedentes: pd.DataFrame | None = None,
    criteria: pd.DataFrame | None = None,
    documents: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build one auditable row per FIDC with all Industry intelligence layers."""

    base = vehicle_latest.copy() if vehicle_latest is not None else pd.DataFrame()
    if base.empty:
        frames = [fund_universe, issuance_tranches, cedentes, criteria, documents]
        ids = []
        for frame in frames:
            if frame is None or frame.empty:
                continue
            id_col = "cnpj_fundo" if "cnpj_fundo" in frame.columns else "cnpj"
            if id_col in frame.columns:
                ids.extend(frame[id_col].map(normalize_cnpj).tolist())
        base = pd.DataFrame({"cnpj_fundo": sorted(set(cnpj for cnpj in ids if len(cnpj) == 14))})
    base = _normalize_snapshot_id(base)
    if base.empty:
        return pd.DataFrame()
    if "cnpj" not in base.columns:
        base["cnpj"] = base["cnpj_fundo"]
    base = base.drop_duplicates("cnpj_fundo", keep="first").copy()

    keep_cols = [
        "cnpj_fundo",
        "cnpj",
        "competencia",
        "tp_registro",
        "denominacao",
        "pl",
        "is_fic_fidc",
        "admin_nome",
        "admin_cnpj",
        "gestor_nome",
        "gestor_cnpj",
        "custodiante_nome",
        "custodiante_cnpj",
        "condominio",
        "exclusivo",
        "publico_alvo",
        "classificacao_anbima",
        "segmento_principal",
        "carteira_dc",
        "dc_inadimplentes",
        "inad_pct",
        "cotistas",
    ]
    snapshot = base[[col for col in keep_cols if col in base.columns]].copy()
    snapshot["cnpj_fundo"] = snapshot["cnpj_fundo"].map(normalize_cnpj)
    numeric_cols = ["pl", "carteira_dc", "dc_inadimplentes", "inad_pct", "cotistas"]
    for col in numeric_cols:
        if col in snapshot.columns:
            snapshot[col] = _num(snapshot[col], snapshot.index)
    snapshot["is_fic_fidc"] = _bool_series(snapshot.get("is_fic_fidc"), snapshot.index)

    aggregates = [
        _aggregate_strategy_universe(fund_universe if fund_universe is not None else pd.DataFrame()),
        _aggregate_tranches(issuance_tranches if issuance_tranches is not None else pd.DataFrame()),
        _aggregate_cedentes_snapshot(cedentes if cedentes is not None else pd.DataFrame()),
        _aggregate_criteria_snapshot(criteria if criteria is not None else pd.DataFrame()),
        _aggregate_document_snapshot(documents if documents is not None else pd.DataFrame()),
    ]
    for agg in aggregates:
        if agg is not None and not agg.empty:
            snapshot = snapshot.merge(agg, on="cnpj_fundo", how="left")

    count_defaults = [
        "tranche_rows",
        "cedente_rows",
        "cedente_originador_count",
        "sacado_devedor_count",
        "participantes_count",
        "criteria_rows",
        "criteria_monitorable_rows",
        "criteria_partial_rows",
        "criteria_not_monitorable_rows",
        "criteria_subordination_rows",
        "document_rows",
        "document_local_ready",
        "document_missing_local",
        "document_priority_2025_2026",
        "has_regulatory_matrix",
    ]
    for col in count_defaults:
        if col not in snapshot.columns:
            snapshot[col] = 0
        snapshot[col] = _num(snapshot[col], snapshot.index).round().astype(int)
    money_defaults = [
        "valid_volume_2024_2026_brl",
        "tranche_volume_brl",
        "volume_2024_brl",
        "volume_2025_brl",
        "volume_2026_brl",
        "valid_volume_2024_brl",
        "valid_volume_2025_brl",
        "valid_volume_2026_brl",
        "tranche_volume_2024_brl",
        "tranche_volume_2025_brl",
        "tranche_volume_2026_brl",
    ]
    for col in money_defaults:
        if col not in snapshot.columns:
            snapshot[col] = 0.0
        snapshot[col] = _num(snapshot[col], snapshot.index)
    text_defaults = [
        "fundo_estrategia",
        "segmento_estrategia",
        "subsegmento_estrategia",
        "emission_cohort",
        "latest_regulamento_date",
        "indexadores",
        "tipo_cotas",
        "pricing_documentos",
        "cedentes_top",
        "grupos_economicos",
        "tipos_participante",
        "cedente_statuses",
        "cedente_documentos",
        "criteria_keys",
        "criteria_documentos",
        "document_classes",
        "document_content_kinds",
        "document_chunk_ids",
        "document_latest_date",
    ]
    for col in text_defaults:
        if col not in snapshot.columns:
            snapshot[col] = ""
        snapshot[col] = _text(snapshot[col], snapshot.index)

    evidence_flags = pd.DataFrame(
        {
            "ime": snapshot.get("pl", pd.Series(0, index=snapshot.index)).fillna(0).gt(0),
            "emissoes": snapshot["valid_volume_2024_2026_brl"].gt(0) | snapshot["tranche_rows"].gt(0),
            "documentos": snapshot["document_rows"].gt(0),
            "cedentes": snapshot["cedente_rows"].gt(0),
            "criterios": snapshot["criteria_rows"].gt(0),
        }
    )
    snapshot["camadas_com_evidencia"] = evidence_flags.sum(axis=1).astype(int)
    snapshot["tem_emissao_2025_2026"] = snapshot["valid_volume_2025_brl"].gt(0) | snapshot["valid_volume_2026_brl"].gt(0)
    snapshot["tem_sub_minima"] = snapshot["criteria_subordination_rows"].gt(0)
    snapshot["tem_cedente"] = snapshot["cedente_rows"].gt(0)
    snapshot["tem_documento_local"] = snapshot["document_local_ready"].gt(0)
    snapshot["snapshot_status"] = snapshot["camadas_com_evidencia"].map(
        lambda value: "completo" if value >= 4 else "parcial" if value >= 2 else "basico"
    )
    if "denominacao" in snapshot.columns:
        snapshot["nome_exibicao"] = snapshot["denominacao"].where(
            snapshot["denominacao"].astype(str).str.strip().ne(""),
            snapshot["fundo_estrategia"],
        )
    else:
        snapshot["nome_exibicao"] = snapshot["fundo_estrategia"]

    ordered = [
        "cnpj_fundo",
        "nome_exibicao",
        "competencia",
        "pl",
        "is_fic_fidc",
        "segmento_principal",
        "segmento_estrategia",
        "subsegmento_estrategia",
        "admin_nome",
        "gestor_nome",
        "custodiante_nome",
        "condominio",
        "publico_alvo",
        "valid_volume_2024_2026_brl",
        "valid_volume_2025_brl",
        "valid_volume_2026_brl",
        "tranche_rows",
        "indexadores",
        "document_rows",
        "document_local_ready",
        "document_chunk_ids",
        "cedente_rows",
        "participantes_count",
        "cedentes_top",
        "criteria_rows",
        "criteria_subordination_rows",
        "sub_min_pct_median",
        "criteria_keys",
        "camadas_com_evidencia",
        "snapshot_status",
    ]
    ordered_present = [col for col in ordered if col in snapshot.columns]
    rest = [col for col in snapshot.columns if col not in ordered_present]
    return snapshot[ordered_present + rest].sort_values(["pl", "camadas_com_evidencia"], ascending=[False, False])


def fund_snapshot_quality_summary(snapshot: pd.DataFrame) -> dict[str, object]:
    if snapshot is None or snapshot.empty:
        return {
            "fund_rows": 0,
            "pl_total_brl": 0.0,
            "evidence_layer_counts": {},
            "coverage": {},
        }
    frame = snapshot.copy()
    score = _num(frame.get("camadas_com_evidencia"), frame.index)
    return {
        "fund_rows": int(len(frame)),
        "pl_total_brl": float(_num(frame.get("pl"), frame.index).sum()),
        "fic_fidc_rows": int(_bool_series(frame.get("is_fic_fidc"), frame.index).sum()),
        "with_issuance_2025_2026": int(_bool_series(frame.get("tem_emissao_2025_2026"), frame.index).sum()),
        "with_documents": int(_num(frame.get("document_rows"), frame.index).gt(0).sum()),
        "with_local_documents": int(_num(frame.get("document_local_ready"), frame.index).gt(0).sum()),
        "with_cedentes": int(_num(frame.get("cedente_rows"), frame.index).gt(0).sum()),
        "with_criteria": int(_num(frame.get("criteria_rows"), frame.index).gt(0).sum()),
        "with_subordination_min": int(_num(frame.get("criteria_subordination_rows"), frame.index).gt(0).sum()),
        "evidence_layers": {
            "median": _json_float(score.median()),
            "p25": _json_float(score.quantile(0.25)),
            "p75": _json_float(score.quantile(0.75)),
        },
        "status_counts": {
            str(k): int(v)
            for k, v in frame.get("snapshot_status", pd.Series("", index=frame.index)).fillna("").astype(str).value_counts().to_dict().items()
        },
        "coverage": {
            "segmento_principal": _coverage(frame, "segmento_principal"),
            "segmento_estrategia": _coverage(frame, "segmento_estrategia"),
            "admin_nome": _coverage(frame, "admin_nome"),
            "gestor_nome": _coverage(frame, "gestor_nome"),
            "document_rows": float(_num(frame.get("document_rows"), frame.index).gt(0).mean()),
            "cedente_rows": float(_num(frame.get("cedente_rows"), frame.index).gt(0).mean()),
            "criteria_rows": float(_num(frame.get("criteria_rows"), frame.index).gt(0).mean()),
            "sub_min_pct_median": float(pd.to_numeric(frame.get("sub_min_pct_median"), errors="coerce").notna().mean())
            if "sub_min_pct_median" in frame
            else 0.0,
        },
    }


def build_fund_snapshot_pipeline_manifest(
    *,
    industry_dir: Path,
    strategy_db: Path,
    output_path: Path,
    manifest_path: Path,
    vehicle_latest: pd.DataFrame,
    fund_universe: pd.DataFrame,
    issuance_tranches: pd.DataFrame,
    cedentes: pd.DataFrame,
    criteria: pd.DataFrame,
    documents: pd.DataFrame,
    snapshot: pd.DataFrame,
) -> dict[str, object]:
    quality = fund_snapshot_quality_summary(snapshot)
    return {
        "schema_version": "industry-fund-snapshot-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_fund_snapshot",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "macbook_air_m4_friendly": True,
            "notes": [
                "Este modulo consolida uma linha por FIDC, sem apagar as bases detalhe.",
                "O snapshot e uma camada de leitura e navegacao; auditoria fina permanece nos artefatos de origem.",
                "Novas dimensoes devem ser adicionadas a partir das bases estruturadas, nao por regra especifica de painel.",
            ],
        },
        "inputs": {
            "strategy_db": file_fingerprint(strategy_db),
            "vehicle_latest": file_fingerprint(industry_dir / "universe_latest.csv"),
            "issuance_tranches": file_fingerprint(industry_dir / "issuance_tranches.csv.gz"),
            "cedentes_structured": file_fingerprint(industry_dir / "cedentes_structured.csv.gz"),
            "criteria_structured": file_fingerprint(industry_dir / "criteria_structured.csv.gz"),
            "document_inventory": file_fingerprint(industry_dir / "document_inventory.csv.gz"),
        },
        "outputs": {
            "fund_snapshot": file_fingerprint(output_path),
            "manifest": {"path": str(manifest_path)},
        },
        "stages": [
            {
                "id": "load_latest_ime_universe",
                "label": "Foto IME por FIDC",
                "status": "ok" if not vehicle_latest.empty else "empty",
                "input": str(industry_dir / "universe_latest.csv"),
                "output": "memoria:vehicle_latest",
                "rows": int(len(vehicle_latest)),
                "funds": int(vehicle_latest["cnpj_fundo"].nunique()) if "cnpj_fundo" in vehicle_latest else 0,
                "rerun": "python scripts/build_fidc_industry_study.py --report",
            },
            {
                "id": "join_issuance_documents_criteria_cedentes",
                "label": "Join das camadas estruturadas",
                "status": "ok" if not snapshot.empty else "empty",
                "input": "memoria:vehicle_latest+fund_universe+tranches+cedentes+criteria+documents",
                "output": str(output_path),
                "rows": int(len(snapshot)),
                "funds": int(snapshot["cnpj_fundo"].nunique()) if "cnpj_fundo" in snapshot else 0,
                "rerun": "python scripts/build_fidc_industry_fund_snapshot.py",
            },
            {
                "id": "preserve_source_granularity",
                "label": "Rastreabilidade das bases detalhe",
                "status": "ok",
                "input": "artefatos estruturados versionados",
                "output": "metadados de contagem/camadas por CNPJ",
                "rows": int(
                    len(fund_universe)
                    + len(issuance_tranches)
                    + len(cedentes)
                    + len(criteria)
                    + len(documents)
                ),
                "rerun": "Reexecute apenas o modulo de origem alterado e depois este snapshot.",
            },
        ],
        "quality": quality,
    }


def build_document_pipeline_manifest(
    *,
    industry_dir: Path,
    strategy_db: Path,
    extractions_dir: Path,
    inventory_path: Path,
    chunks_path: Path,
    manifest_path: Path,
    source_rows: pd.DataFrame,
    extraction_rows: pd.DataFrame,
    inventory: pd.DataFrame,
    chunks: pd.DataFrame,
    max_hash_bytes: int,
) -> dict[str, object]:
    quality = document_quality_summary(inventory, chunks)
    return {
        "schema_version": "industry-document-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_document_inventory",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "macbook_air_m4_friendly": True,
            "notes": [
                "Este modulo inventaria documentos e caches locais; nao faz download, OCR ou interpretacao juridica.",
                "Chunks pequenos permitem executar parsing/extracao por lote, sem reprocessar toda a industria.",
                f"Arquivos acima de {max_hash_bytes:,} bytes recebem stat de tamanho, mas o hash e pulado para preservar tempo de execucao.",
            ],
        },
        "inputs": {
            "strategy_db": file_fingerprint(strategy_db),
            "regulatory_extractions_dir": {
                "path": str(extractions_dir),
                "exists": extractions_dir.exists(),
            },
        },
        "outputs": {
            "document_inventory": file_fingerprint(inventory_path),
            "document_processing_chunks": file_fingerprint(chunks_path),
            "manifest": {"path": str(manifest_path)},
        },
        "stages": [
            {
                "id": "discover_sqlite_document_sources",
                "label": "Descoberta em SQLite",
                "status": "ok" if not source_rows.empty else "empty",
                "input": str(strategy_db),
                "output": "memoria:document_source_rows",
                "rows": int(len(source_rows)),
                "funds": int(source_rows["cnpj_fundo"].nunique()) if "cnpj_fundo" in source_rows else 0,
                "rerun": "python scripts/build_fidc_industry_documents.py",
            },
            {
                "id": "scan_local_extraction_artifacts",
                "label": "Artefatos de extração locais",
                "status": "ok" if not extraction_rows.empty else "empty",
                "input": str(extractions_dir),
                "output": "memoria:regulatory_extractions",
                "rows": int(len(extraction_rows)),
                "funds": int(extraction_rows["cnpj_fundo"].nunique()) if "cnpj_fundo" in extraction_rows else 0,
                "rerun": "python scripts/build_fidc_industry_documents.py",
            },
            {
                "id": "fingerprint_local_files",
                "label": "Fingerprint e status local",
                "status": "ok" if not inventory.empty else "empty",
                "input": "memoria:document_source_rows+regulatory_extractions",
                "output": "memoria:document_inventory",
                "rows": int(len(inventory)),
                "funds": int(inventory["cnpj_fundo"].nunique()) if "cnpj_fundo" in inventory else 0,
                "rerun": "python scripts/build_fidc_industry_documents.py",
            },
            {
                "id": "assign_processing_chunks",
                "label": "Chunking incremental",
                "status": "ok" if not chunks.empty else "empty",
                "input": "memoria:document_inventory",
                "output": str(chunks_path),
                "rows": int(len(chunks)),
                "rerun": "python scripts/build_fidc_industry_documents.py",
            },
            {
                "id": "persist_document_inventory",
                "label": "Inventário versionável",
                "status": "ok" if inventory_path.exists() else "empty",
                "input": "memoria:document_inventory",
                "output": str(inventory_path),
                "rows": int(len(inventory)),
                "rerun": "python scripts/build_fidc_industry_documents.py",
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
