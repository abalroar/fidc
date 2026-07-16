from __future__ import annotations

import argparse
import csv
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


START_DATE = pd.Timestamp("2024-01-01")
DEFAULT_AS_OF = pd.Timestamp("2026-06-09")
COUNTED_CLOSED_STATUSES = {"OFERTA ENCERRADA"}
EXCLUDED_STATUSES = {"REGISTRO CADUCADO", "OFERTA REVOGADA", "OFERTA SUSPENSA"}


@dataclass(frozen=True)
class StudyInputs:
    cad_fi_csv: Path
    registro_fundo_classe_zip: Path
    oferta_distribuicao_zip: Path
    output_dir: Path
    as_of_date: pd.Timestamp


def only_digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def clean_text(value: object) -> str:
    text = str(value or "").strip()
    if text.lower() in {"nan", "none", "nat"}:
        return ""
    return re.sub(r"\s+", " ", text)


def parse_date_series(series: pd.Series, *, dayfirst: bool = False) -> pd.Series:
    return pd.to_datetime(series.replace("", pd.NA), errors="coerce", dayfirst=dayfirst)


def parse_number_series(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    text = text.str.replace("\u00a0", "", regex=False)
    has_br_decimal = text.str.contains(r",\d{1,6}$", regex=True)
    text = text.where(~has_br_decimal, text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(text.replace({"": pd.NA, "nan": pd.NA}), errors="coerce")


def min_date_across(frame: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    parsed = []
    for column in columns:
        if column in frame.columns:
            parsed.append(pd.to_datetime(frame[column], errors="coerce"))
    if not parsed:
        return pd.Series(pd.NaT, index=frame.index)
    return pd.concat(parsed, axis=1).min(axis=1)


def yyyymmdd(value: object) -> str:
    if pd.isna(value):
        return ""
    ts = pd.Timestamp(value)
    return ts.strftime("%Y-%m-%d")


def date_label(value: object) -> str:
    if pd.isna(value):
        return ""
    return pd.Timestamp(value).date().isoformat()


def value_to_brl_text(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"R$ {float(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def load_cvm_entities(inputs: StudyInputs) -> pd.DataFrame:
    legacy = pd.read_csv(
        inputs.cad_fi_csv,
        sep=";",
        encoding="latin-1",
        dtype=str,
        keep_default_na=False,
    )
    legacy = legacy[legacy["TP_FUNDO"].str.contains("FIDC", case=False, na=False)].copy()
    legacy_out = pd.DataFrame(
        {
            "entity_kind": "fundo_legado_cad_fi",
            "cnpj_entity": legacy["CNPJ_FUNDO"].map(only_digits),
            "cnpj_fundo": legacy["CNPJ_FUNDO"].map(only_digits),
            "cnpj_classe": "",
            "nome_entity": legacy["DENOM_SOCIAL"].map(clean_text),
            "nome_fundo": legacy["DENOM_SOCIAL"].map(clean_text),
            "nome_classe": "",
            "tipo_fidc_cvm": legacy["CLASSE"].map(clean_text),
            "data_registro": parse_date_series(legacy["DT_REG"]),
            "data_constituicao": parse_date_series(legacy["DT_CONST"]),
            "data_inicio": parse_date_series(legacy["DT_INI_ATIV"]),
            "data_cancelamento": parse_date_series(legacy["DT_CANCEL"]),
            "situacao": legacy["SIT"].map(clean_text),
            "administrador": legacy["ADMIN"].map(clean_text),
            "gestor": legacy["GESTOR"].map(clean_text),
            "custodiante": legacy["CUSTODIANTE"].map(clean_text),
            "patrimonio_liquido": parse_number_series(legacy["VL_PATRIM_LIQ"]),
            "data_patrimonio_liquido": parse_date_series(legacy["DT_PATRIM_LIQ"]),
            "source_dataset": "cad_fi.csv",
        }
    )

    with zipfile.ZipFile(inputs.registro_fundo_classe_zip) as archive:
        fundo = pd.read_csv(
            archive.open("registro_fundo.csv"),
            sep=";",
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
        )
        classe = pd.read_csv(
            archive.open("registro_classe.csv"),
            sep=";",
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
        )

    fundo_fidc = fundo[fundo["Tipo_Fundo"].str.contains("FIDC", case=False, na=False)].copy()
    fundo_out = pd.DataFrame(
        {
            "entity_kind": "fundo_rcvm175",
            "cnpj_entity": fundo_fidc["CNPJ_Fundo"].map(only_digits),
            "cnpj_fundo": fundo_fidc["CNPJ_Fundo"].map(only_digits),
            "cnpj_classe": "",
            "nome_entity": fundo_fidc["Denominacao_Social"].map(clean_text),
            "nome_fundo": fundo_fidc["Denominacao_Social"].map(clean_text),
            "nome_classe": "",
            "tipo_fidc_cvm": fundo_fidc["Tipo_Fundo"].map(clean_text),
            "data_registro": parse_date_series(fundo_fidc["Data_Registro"]),
            "data_constituicao": parse_date_series(fundo_fidc["Data_Constituicao"]),
            "data_inicio": pd.NaT,
            "data_cancelamento": parse_date_series(fundo_fidc["Data_Cancelamento"]),
            "situacao": fundo_fidc["Situacao"].map(clean_text),
            "administrador": fundo_fidc["Administrador"].map(clean_text),
            "gestor": fundo_fidc["Gestor"].map(clean_text),
            "custodiante": "",
            "patrimonio_liquido": parse_number_series(fundo_fidc["Patrimonio_Liquido"]),
            "data_patrimonio_liquido": parse_date_series(fundo_fidc["Data_Patrimonio_Liquido"]),
            "source_dataset": "registro_fundo.csv",
        }
    )

    fund_lookup = fundo[
        [
            "ID_Registro_Fundo",
            "CNPJ_Fundo",
            "Denominacao_Social",
            "Administrador",
            "Gestor",
        ]
    ].copy()
    fund_lookup.columns = [
        "ID_Registro_Fundo",
        "CNPJ_Fundo_lookup",
        "Denominacao_Social_fundo_lookup",
        "Administrador_lookup",
        "Gestor_lookup",
    ]
    classe_fidc = classe[classe["Tipo_Classe"].str.contains("FIDC", case=False, na=False)].copy()
    classe_fidc = classe_fidc.merge(fund_lookup, on="ID_Registro_Fundo", how="left")
    classe_out = pd.DataFrame(
        {
            "entity_kind": "classe_rcvm175",
            "cnpj_entity": classe_fidc["CNPJ_Classe"].map(only_digits),
            "cnpj_fundo": classe_fidc["CNPJ_Fundo_lookup"].map(only_digits),
            "cnpj_classe": classe_fidc["CNPJ_Classe"].map(only_digits),
            "nome_entity": classe_fidc["Denominacao_Social"].map(clean_text),
            "nome_fundo": classe_fidc["Denominacao_Social_fundo_lookup"].map(clean_text),
            "nome_classe": classe_fidc["Denominacao_Social"].map(clean_text),
            "tipo_fidc_cvm": classe_fidc["Tipo_Classe"].map(clean_text),
            "data_registro": parse_date_series(classe_fidc["Data_Registro"]),
            "data_constituicao": parse_date_series(classe_fidc["Data_Constituicao"]),
            "data_inicio": parse_date_series(classe_fidc["Data_Inicio"]),
            "data_cancelamento": pd.NaT,
            "situacao": classe_fidc["Situacao"].map(clean_text),
            "administrador": classe_fidc["Administrador_lookup"].map(clean_text),
            "gestor": classe_fidc["Gestor_lookup"].map(clean_text),
            "custodiante": classe_fidc["Custodiante"].map(clean_text),
            "patrimonio_liquido": parse_number_series(classe_fidc["Patrimonio_Liquido"]),
            "data_patrimonio_liquido": parse_date_series(classe_fidc["Data_Patrimonio_Liquido"]),
            "source_dataset": "registro_classe.csv",
        }
    )

    entities = pd.concat([legacy_out, fundo_out, classe_out], ignore_index=True)
    entities = entities[entities["cnpj_entity"].str.len() == 14].copy()
    entities["first_known_date"] = min_date_across(
        entities,
        ["data_constituicao", "data_inicio", "data_registro"],
    )
    entities["registered_since_2024"] = entities["data_registro"] >= START_DATE
    entities["constituted_since_2024"] = entities["data_constituicao"] >= START_DATE
    entities["born_since_2024_strict"] = entities["first_known_date"] >= START_DATE
    entities["registration_is_probable_recadastro"] = (
        entities["registered_since_2024"] & ~entities["born_since_2024_strict"]
    )
    return entities


def aggregate_entities(entities: pd.DataFrame) -> pd.DataFrame:
    sort_cols = ["cnpj_entity", "entity_kind", "first_known_date", "data_registro"]
    frame = entities.sort_values(sort_cols, na_position="last").copy()

    rows: list[dict[str, object]] = []
    for (entity_kind, cnpj), group in frame.groupby(["entity_kind", "cnpj_entity"], sort=False):
        latest_idx = group["data_registro"].fillna(pd.Timestamp.min).idxmax()
        latest = group.loc[latest_idx]
        earliest = group.iloc[0]
        rows.append(
            {
                "entity_kind": entity_kind,
                "cnpj_entity": cnpj,
                "cnpj_fundo": latest["cnpj_fundo"],
                "cnpj_classe": latest["cnpj_classe"],
                "nome_entity": latest["nome_entity"] or earliest["nome_entity"],
                "nome_fundo": latest["nome_fundo"] or earliest["nome_fundo"],
                "nome_classe": latest["nome_classe"] or earliest["nome_classe"],
                "tipo_fidc_cvm": latest["tipo_fidc_cvm"] or earliest["tipo_fidc_cvm"],
                "first_known_date": group["first_known_date"].min(),
                "first_data_constituicao": group["data_constituicao"].min(),
                "first_data_inicio": group["data_inicio"].min(),
                "first_data_registro": group["data_registro"].min(),
                "latest_data_registro": group["data_registro"].max(),
                "situacao_latest": latest["situacao"],
                "administrador": latest["administrador"],
                "gestor": latest["gestor"],
                "custodiante": latest["custodiante"],
                "patrimonio_liquido_latest": latest["patrimonio_liquido"],
                "data_patrimonio_liquido_latest": latest["data_patrimonio_liquido"],
                "source_datasets": "; ".join(sorted(set(group["source_dataset"].dropna().astype(str)))),
                "raw_record_count": len(group),
            }
        )
    output = pd.DataFrame(rows)
    output["registered_since_2024"] = output["latest_data_registro"] >= START_DATE
    output["born_since_2024_strict"] = output["first_known_date"] >= START_DATE
    output["registration_is_probable_recadastro"] = (
        output["registered_since_2024"] & ~output["born_since_2024_strict"]
    )
    return output.sort_values(["first_known_date", "entity_kind", "nome_entity"], na_position="last")


def standardize_offers(inputs: StudyInputs) -> pd.DataFrame:
    with zipfile.ZipFile(inputs.oferta_distribuicao_zip) as archive:
        legacy = pd.read_csv(
            archive.open("oferta_distribuicao.csv"),
            sep=";",
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
        )
        r160 = pd.read_csv(
            archive.open("oferta_resolucao_160.csv"),
            sep=";",
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
        )

    legacy_mask = legacy["Tipo_Ativo"].str.contains("FIDC", case=False, na=False)
    legacy = legacy[legacy_mask].copy()
    legacy_out = pd.DataFrame(
        {
            "source_dataset": "oferta_distribuicao.csv",
            "offer_id": legacy["Numero_Processo"].map(clean_text)
            + " | "
            + legacy["Numero_Registro_Oferta"].map(clean_text),
            "numero_processo": legacy["Numero_Processo"].map(clean_text),
            "numero_requerimento": "",
            "data_registro": parse_date_series(legacy["Data_Registro_Oferta"]),
            "data_requerimento": parse_date_series(legacy["Data_Protocolo"]),
            "data_inicio": parse_date_series(legacy["Data_Inicio_Oferta"]),
            "data_encerramento": parse_date_series(legacy["Data_Encerramento_Oferta"]),
            "status": legacy["Modalidade_Registro"].map(clean_text),
            "status_raw": legacy["Modalidade_Oferta"].map(clean_text)
            + " / "
            + legacy["Modalidade_Registro"].map(clean_text),
            "valor_mobiliario": legacy["Tipo_Ativo"].map(clean_text),
            "fidc_subtipo": legacy["Tipo_Ativo"].map(
                lambda x: "FIAGRO-FIDC" if "FIAGRO" in str(x).upper() else "FIDC"
            ),
            "tipo_oferta": legacy["Tipo_Oferta"].map(clean_text),
            "cnpj_emissor": legacy["CNPJ_Emissor"].map(only_digits),
            "nome_emissor": legacy["Nome_Emissor"].map(clean_text),
            "cnpj_lider": legacy["CNPJ_Lider"].map(only_digits),
            "nome_lider": legacy["Nome_Lider"].map(clean_text),
            "emissao": legacy["Emissao"].map(clean_text),
            "classe_ativo": legacy["Classe_Ativo"].map(clean_text),
            "serie": legacy["Serie"].map(clean_text),
            "quantidade_total": parse_number_series(legacy["Quantidade_Total"]),
            "preco_unitario": parse_number_series(legacy["Preco_Unitario"]),
            "valor_total_registrado": parse_number_series(legacy["Valor_Total"]),
            "publico_alvo": "",
            "tipo_lastro": "",
            "descricao_lastro": "",
            "ativos_alvo": "",
            "fidc_nao_padronizado": "",
            "regime_distribuicao": "",
            "administrador": "",
            "gestor": "",
            "custodiante": "",
        }
    )

    r160_mask = r160["Valor_Mobiliario"].str.contains("FIDC", case=False, na=False)
    r160 = r160[r160_mask].copy()
    r160_out = pd.DataFrame(
        {
            "source_dataset": "oferta_resolucao_160.csv",
            "offer_id": r160["Numero_Requerimento"].map(clean_text),
            "numero_processo": r160["Numero_Processo"].map(clean_text),
            "numero_requerimento": r160["Numero_Requerimento"].map(clean_text),
            "data_registro": parse_date_series(r160["Data_Registro"]),
            "data_requerimento": parse_date_series(r160["Data_requerimento"]),
            "data_inicio": pd.NaT,
            "data_encerramento": parse_date_series(r160["Data_Encerramento"]),
            "status": r160["Status_Requerimento"].map(clean_text),
            "status_raw": r160["Status_Requerimento"].map(clean_text),
            "valor_mobiliario": r160["Valor_Mobiliario"].map(clean_text),
            "fidc_subtipo": r160["Valor_Mobiliario"].map(
                lambda x: "FIAGRO-FIDC" if "FIAGRO" in str(x).upper() else "FIDC"
            ),
            "tipo_oferta": r160["Tipo_Oferta"].map(clean_text),
            "cnpj_emissor": r160["CNPJ_Emissor"].map(only_digits),
            "nome_emissor": r160["Nome_Emissor"].map(clean_text),
            "cnpj_lider": r160["CNPJ_Lider"].map(only_digits),
            "nome_lider": r160["Nome_Lider"].map(clean_text),
            "emissao": r160["Emissao"].map(clean_text),
            "classe_ativo": r160["Valor_Mobiliario"].map(clean_text),
            "serie": "",
            "quantidade_total": parse_number_series(r160["Qtde_Total_Registrada"]),
            "preco_unitario": pd.NA,
            "valor_total_registrado": parse_number_series(r160["Valor_Total_Registrado"]),
            "publico_alvo": r160["Publico_alvo"].map(clean_text),
            "tipo_lastro": r160["Tipo_lastro"].map(clean_text),
            "descricao_lastro": r160["Descricao_lastro"].map(clean_text),
            "ativos_alvo": r160["Ativos_alvo"].map(clean_text),
            "fidc_nao_padronizado": r160["FIDC_nao_padronizado"].map(clean_text),
            "regime_distribuicao": r160["Regime_distribuicao"].map(clean_text),
            "administrador": r160["Administrador"].map(clean_text),
            "gestor": r160["Gestor"].map(clean_text),
            "custodiante": r160["Custodiante"].map(clean_text),
        }
    )

    offers = pd.concat([legacy_out, r160_out], ignore_index=True)
    offers = offers[offers["data_registro"].notna()].copy()
    offers = offers[(offers["data_registro"] >= START_DATE) & (offers["data_registro"] <= inputs.as_of_date)].copy()
    offers["year"] = offers["data_registro"].dt.year.astype(int)
    offers["periodo_estudo"] = offers["year"].map({2024: "2024FY", 2025: "2025FY", 2026: "2026YTD"})
    offers["status_upper"] = offers["status"].str.upper()
    offers["status_bucket"] = "outros"
    offers.loc[offers["status_upper"].isin(COUNTED_CLOSED_STATUSES), "status_bucket"] = "oferta_encerrada"
    offers.loc[offers["status_upper"].isin(EXCLUDED_STATUSES), "status_bucket"] = "nao_emitida_suspensa_caducada"
    offers.loc[
        (offers["source_dataset"] == "oferta_distribuicao.csv")
        & (offers["data_encerramento"].notna()),
        "status_bucket",
    ] = "oferta_encerrada_rito_ordinario"
    offers.loc[
        (offers["status_bucket"] == "outros")
        & offers["status_upper"].str.contains("CONCEDIDO", na=False),
        "status_bucket",
    ] = "registro_concedido_em_aberto"
    offers["volume_registrado_valido_flag"] = ~offers["status_upper"].isin(EXCLUDED_STATUSES)
    offers["volume_encerrado_conservador_flag"] = offers["status_bucket"].isin(
        {"oferta_encerrada", "oferta_encerrada_rito_ordinario"}
    )
    return offers.drop(columns=["status_upper"])


def add_platform_coverage(offers: pd.DataFrame, entities: pd.DataFrame, repo_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    knowledge_cnpjs = {path.stem for path in (repo_root / "data/regulatory_knowledge").glob("*.json")}
    raw_cnpjs = {path.name for path in (repo_root / "data/raw").glob("*") if path.is_dir()}
    curated_emissions_path = repo_root / "data/regulatory_profiles/all_fidcs_cotas_emissoes_pagamentos.csv"
    curated_cnpjs: set[str] = set()
    if curated_emissions_path.exists():
        curated = pd.read_csv(curated_emissions_path, dtype=str, keep_default_na=False)
        if "CNPJ" in curated.columns:
            curated_cnpjs = set(curated["CNPJ"].map(only_digits))

    for frame, cnpj_col in [(offers, "cnpj_emissor"), (entities, "cnpj_entity")]:
        frame["platform_has_regulatory_knowledge"] = frame[cnpj_col].isin(knowledge_cnpjs)
        frame["platform_has_raw_documents"] = frame[cnpj_col].isin(raw_cnpjs)
        frame["platform_has_curated_emission_rows"] = frame[cnpj_col].isin(curated_cnpjs)
        frame["platform_coverage_level"] = "sem_curadoria_local"
        frame.loc[frame["platform_has_raw_documents"], "platform_coverage_level"] = "documentos_baixados"
        frame.loc[frame["platform_has_regulatory_knowledge"], "platform_coverage_level"] = "knowledge_json"
        frame.loc[frame["platform_has_curated_emission_rows"], "platform_coverage_level"] = "emissoes_curadas"
    return offers, entities


def join_offers_to_entities(offers: pd.DataFrame, entities: pd.DataFrame) -> pd.DataFrame:
    entity_keys = entities[
        [
            "entity_kind",
            "cnpj_entity",
            "cnpj_fundo",
            "cnpj_classe",
            "nome_entity",
            "first_known_date",
            "first_data_constituicao",
            "latest_data_registro",
            "born_since_2024_strict",
            "registration_is_probable_recadastro",
        ]
    ].copy()
    entity_keys = entity_keys.sort_values(
        ["cnpj_entity", "born_since_2024_strict", "first_known_date"],
        ascending=[True, False, True],
        na_position="last",
    ).drop_duplicates("cnpj_entity", keep="first")
    joined = offers.merge(
        entity_keys.add_prefix("cvm_match_"),
        left_on="cnpj_emissor",
        right_on="cvm_match_cnpj_entity",
        how="left",
    )
    joined["issuer_found_in_cvm_fidc_entities"] = joined["cvm_match_cnpj_entity"].notna()
    joined["issuer_born_since_2024_strict"] = joined["cvm_match_born_since_2024_strict"].fillna(False)
    return joined


def build_summary(entities: pd.DataFrame, offers: pd.DataFrame, inputs: StudyInputs) -> dict[str, object]:
    period_summary = []
    for period, group in offers.groupby("periodo_estudo", sort=True):
        if not period:
            continue
        valid = group[group["volume_registrado_valido_flag"]]
        closed = group[group["volume_encerrado_conservador_flag"]]
        period_summary.append(
            {
                "periodo": period,
                "ofertas_total_linhas": int(len(group)),
                "ofertas_validas_ou_abertas_linhas": int(len(valid)),
                "ofertas_encerradas_linhas": int(len(closed)),
                "volume_registrado_bruto": float(group["valor_total_registrado"].sum(skipna=True)),
                "volume_registrado_valido_ou_aberto": float(valid["valor_total_registrado"].sum(skipna=True)),
                "volume_encerrado_conservador": float(closed["valor_total_registrado"].sum(skipna=True)),
                "emissores_unicos": int(group["cnpj_emissor"].nunique()),
                "emissores_unicos_encerradas": int(closed["cnpj_emissor"].nunique()),
            }
        )

    entity_summary = []
    for kind, group in entities.groupby("entity_kind"):
        entity_summary.append(
            {
                "entity_kind": kind,
                "total_entities": int(len(group)),
                "born_since_2024_strict": int(group["born_since_2024_strict"].sum()),
                "registered_since_2024": int(group["registered_since_2024"].sum()),
                "probable_recadastro_since_2024": int(group["registration_is_probable_recadastro"].sum()),
            }
        )

    status_summary = (
        offers.groupby(["periodo_estudo", "status_bucket"], dropna=False)["valor_total_registrado"]
        .agg(["count", "sum"])
        .reset_index()
        .rename(columns={"count": "linhas", "sum": "valor_total_registrado"})
        .to_dict(orient="records")
    )
    lastro_summary = (
        offers[offers["tipo_lastro"].astype(str).str.strip() != ""]
        .groupby(["periodo_estudo", "tipo_lastro"], dropna=False)["valor_total_registrado"]
        .agg(["count", "sum"])
        .reset_index()
        .rename(columns={"count": "linhas", "sum": "valor_total_registrado"})
        .sort_values(["periodo_estudo", "valor_total_registrado"], ascending=[True, False])
        .head(100)
        .to_dict(orient="records")
    )
    born_offer_summary: list[dict[str, object]] = []
    if "issuer_born_since_2024_strict" in offers.columns:
        for (period, born_flag), group in offers.groupby(["periodo_estudo", "issuer_born_since_2024_strict"]):
            valid = group[group["volume_registrado_valido_flag"]]
            closed = group[group["volume_encerrado_conservador_flag"]]
            born_offer_summary.append(
                {
                    "periodo": period,
                    "issuer_born_since_2024_strict": bool(born_flag),
                    "ofertas_total_linhas": int(len(group)),
                    "volume_registrado_bruto": float(group["valor_total_registrado"].sum(skipna=True)),
                    "volume_registrado_valido_ou_aberto": float(valid["valor_total_registrado"].sum(skipna=True)),
                    "volume_encerrado_conservador": float(closed["valor_total_registrado"].sum(skipna=True)),
                    "emissores_unicos": int(group["cnpj_emissor"].nunique()),
                }
            )
    platform_coverage_summary: list[dict[str, object]] = []
    if "platform_coverage_level" in offers.columns:
        platform_coverage_summary = (
            offers.groupby("platform_coverage_level", dropna=False)["valor_total_registrado"]
            .agg(["count", "sum"])
            .reset_index()
            .rename(columns={"count": "linhas", "sum": "valor_total_registrado"})
            .sort_values("valor_total_registrado", ascending=False)
            .to_dict(orient="records")
        )
    return {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": inputs.as_of_date.date().isoformat(),
        "start_date": START_DATE.date().isoformat(),
        "source_files": {
            "cad_fi_csv": str(inputs.cad_fi_csv),
            "registro_fundo_classe_zip": str(inputs.registro_fundo_classe_zip),
            "oferta_distribuicao_zip": str(inputs.oferta_distribuicao_zip),
        },
        "period_summary": period_summary,
        "entity_summary": entity_summary,
        "status_summary": status_summary,
        "lastro_summary_top100": lastro_summary,
        "born_offer_summary": born_offer_summary,
        "platform_coverage_summary": platform_coverage_summary,
    }


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def write_markdown(summary: dict[str, object], output_dir: Path) -> None:
    lines = [
        "# Estudo FIDC - nascimentos CVM e ofertas 2024FY-2026YTD",
        "",
        f"Data de corte: {summary['as_of_date']}.",
        "",
        "## Metodo",
        "",
        "- Nascimento CVM estrito: menor data conhecida entre constituicao, inicio e registro >= 2024-01-01.",
        "- Registro desde 2024: data de registro CVM >= 2024-01-01; pode incluir recadastro/adaptacao de veiculo antigo.",
        "- Volume de ofertas: conjunto CVM Ofertas Publicas de Distribuicao, tabelas `oferta_resolucao_160.csv` e `oferta_distribuicao.csv`.",
        "- Volume encerrado conservador: apenas `Oferta Encerrada` na RCVM 160 e linhas do rito ordinario com data de encerramento.",
        "- Volume registrado valido/ou aberto: exclui `Registro Caducado`, `Oferta Revogada` e `Oferta Suspensa`, mas inclui registros concedidos ainda nao encerrados.",
        "- Setor nao foi inferido por nome. A fila de classificacao preserva campos CVM de lastro/ativos para leitura posterior de regulamentos e documentos da oferta.",
        "",
        "## Totais de ofertas",
        "",
        "| Periodo | Linhas | Linhas validas/abertas | Linhas encerradas | Volume registrado valido/aberto | Volume encerrado conservador | Emissores unicos |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["period_summary"]:
        lines.append(
            "| {periodo} | {ofertas_total_linhas:,} | {ofertas_validas_ou_abertas_linhas:,} | {ofertas_encerradas_linhas:,} | {valid} | {closed} | {emissores_unicos:,} |".format(
                periodo=row["periodo"],
                ofertas_total_linhas=row["ofertas_total_linhas"],
                ofertas_validas_ou_abertas_linhas=row["ofertas_validas_ou_abertas_linhas"],
                ofertas_encerradas_linhas=row["ofertas_encerradas_linhas"],
                valid=value_to_brl_text(row["volume_registrado_valido_ou_aberto"]),
                closed=value_to_brl_text(row["volume_encerrado_conservador"]),
                emissores_unicos=row["emissores_unicos"],
            )
        )

    lines.extend(
        [
            "",
            "## Ofertas por nascimento CVM do emissor",
            "",
            "| Periodo | Emissor nasceu desde 2024 | Linhas | Volume registrado valido/aberto | Volume encerrado conservador | Emissores unicos |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in summary.get("born_offer_summary", []):
        lines.append(
            "| {periodo} | {born} | {linhas:,} | {valid} | {closed} | {emissores_unicos:,} |".format(
                periodo=row["periodo"],
                born="sim" if row["issuer_born_since_2024_strict"] else "nao",
                linhas=row["ofertas_total_linhas"],
                valid=value_to_brl_text(row["volume_registrado_valido_ou_aberto"]),
                closed=value_to_brl_text(row["volume_encerrado_conservador"]),
                emissores_unicos=row["emissores_unicos"],
            )
        )

    lines.extend(
        [
            "",
            "## Entidades CVM",
            "",
            "| Tipo | Total | Nascidas desde 2024 | Registradas desde 2024 | Provavel recadastro/adaptacao |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in summary["entity_summary"]:
        lines.append(
            f"| {row['entity_kind']} | {row['total_entities']:,} | {row['born_since_2024_strict']:,} | {row['registered_since_2024']:,} | {row['probable_recadastro_since_2024']:,} |"
        )

    lines.extend(
        [
            "",
            "## Arquivos gerados",
            "",
            "- `fidc_cvm_entities_all.csv`: universo CVM FIDC de fundos/classes.",
            "- `fidc_cvm_born_since_2024.csv`: entidades com nascimento estrito desde 2024.",
            "- `fidc_cvm_registrations_since_2024.csv`: entidades registradas desde 2024, incluindo possiveis recadastros/adaptacoes.",
            "- `fidc_public_offers_2024_2026ytd.csv`: ofertas publicas de cotas de FIDC/FIAGRO-FIDC no periodo.",
            "- `fidc_offer_classification_queue.csv`: fila para classificacao setorial por leitura documental.",
            "- `summary.json`: metricas agregadas e auditoria de fontes.",
        ]
    )
    (output_dir / "methodology_and_summary.md").write_text("\n".join(lines), encoding="utf-8")


def build_classification_queue(offers: pd.DataFrame) -> pd.DataFrame:
    queue_cols = [
        "periodo_estudo",
        "data_registro",
        "cnpj_emissor",
        "nome_emissor",
        "valor_mobiliario",
        "fidc_subtipo",
        "valor_total_registrado",
        "status",
        "status_bucket",
        "publico_alvo",
        "tipo_lastro",
        "descricao_lastro",
        "ativos_alvo",
        "fidc_nao_padronizado",
        "administrador",
        "gestor",
        "custodiante",
        "nome_lider",
        "platform_coverage_level",
    ]
    queue = offers[queue_cols].copy()
    queue["setor_proposto"] = ""
    queue["familia_credito_proposta"] = ""
    queue["classificacao_status"] = "pendente_leitura_regulamento_ou_documento_oferta"
    queue["evidencia_classificacao"] = ""
    queue["observacoes_analista"] = ""
    return queue.sort_values(["periodo_estudo", "valor_total_registrado"], ascending=[True, False])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build FIDC CVM birth and public-offer study.")
    parser.add_argument("--cad-fi-csv", default="outputs/fidc_issuance_study_20260609/cad_fi.csv")
    parser.add_argument("--registro-fundo-classe-zip", default="outputs/fidc_issuance_study_20260609/registro_fundo_classe.zip")
    parser.add_argument("--oferta-distribuicao-zip", default="outputs/fidc_issuance_study_20260609/oferta_distribuicao.zip")
    parser.add_argument("--output-dir", default="outputs/fidc_issuance_study_20260609")
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF.date().isoformat())
    args = parser.parse_args()

    inputs = StudyInputs(
        cad_fi_csv=Path(args.cad_fi_csv),
        registro_fundo_classe_zip=Path(args.registro_fundo_classe_zip),
        oferta_distribuicao_zip=Path(args.oferta_distribuicao_zip),
        output_dir=Path(args.output_dir),
        as_of_date=pd.Timestamp(date.fromisoformat(args.as_of_date)),
    )
    inputs.output_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path.cwd()

    entities_raw = load_cvm_entities(inputs)
    entities = aggregate_entities(entities_raw)
    offers = standardize_offers(inputs)
    offers, entities = add_platform_coverage(offers, entities, repo_root)
    offers = join_offers_to_entities(offers, entities)
    classification_queue = build_classification_queue(offers)
    born_since_2024 = entities[entities["born_since_2024_strict"]].copy()
    registrations_since_2024 = entities[entities["registered_since_2024"]].copy()
    summary_entities = entities.copy()
    summary_offers = offers.copy()

    for frame in [entities, born_since_2024, registrations_since_2024, offers, classification_queue]:
        for column in frame.columns:
            if pd.api.types.is_datetime64_any_dtype(frame[column]):
                frame[column] = frame[column].map(date_label)

    write_csv(entities, inputs.output_dir / "fidc_cvm_entities_all.csv")
    write_csv(born_since_2024, inputs.output_dir / "fidc_cvm_born_since_2024.csv")
    write_csv(registrations_since_2024, inputs.output_dir / "fidc_cvm_registrations_since_2024.csv")
    write_csv(offers, inputs.output_dir / "fidc_public_offers_2024_2026ytd.csv")
    write_csv(classification_queue, inputs.output_dir / "fidc_offer_classification_queue.csv")

    summary = build_summary(entities=summary_entities, offers=summary_offers, inputs=inputs)
    (inputs.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    write_markdown(summary, inputs.output_dir)
    print(json.dumps(summary["period_summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
