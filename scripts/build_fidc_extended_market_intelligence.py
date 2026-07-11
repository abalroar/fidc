"""Build auditable FIDC market-share, investor, cedent, and liquidity modules.

The script deliberately separates direct observations from reconstructions:

* administrator history comes from the monthly FIDC filing;
* manager and custodian history combines dated CVM cadastro history, dated
  public-offer records, and a clearly flagged current-cadastro fallback;
* investor profiles combine Table X.1.1 of the monthly filing with the direct
  subscriber table in closing announcements filed under CVM Resolution 160;
* secondary-market outputs distinguish registered secondary distributions
  from actual secondary trading, which is not published by CVM in trade-level
  form.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import re
import unicodedata
import zipfile
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np
import pandas as pd

from build_fidc_industry_study import (
    BASE_HIST_URL,
    BASE_MONTHLY_URL,
    COTISTA_TIPO_LABELS,
    RawStore,
    download,
    to_num,
)


INVESTOR_CATEGORY_PATTERNS = OrderedDict(
    [
        ("pessoas_naturais", r"PESSOAS (?:NATURAIS|FISICAS)"),
        ("clubes_investimento", r"CLUBES? DE INVESTIMENTO"),
        ("fundos_investimento", r"FUNDOS? DE INVESTIMENTO"),
        (
            "previdencia_privada",
            r"ENTIDADES? DE PREVIDENCIA (?:PRIVADA|COMPLEMENTAR)",
        ),
        ("seguradoras", r"COMPANHIAS? SEGURADORAS?"),
        ("investidores_estrangeiros", r"INVESTIDORES? ESTRANGEIROS?"),
        (
            "intermediarias_consorcio",
            r"INSTITUICOES? INTERMEDIARIAS? PARTICIPANTES? DO CONSORCIO DE DISTRIBUICAO",
        ),
        (
            "financeiras_ligadas",
            r"INSTITUICOES? FINANCEIRAS? LIGADAS? AO (?:EMISSOR|FUNDO)(?: E| E/OU)? (?:AOS? )?(?:PARTICIPANTES? DO CONSORCIO|COORDENADOR(?: LIDER)?|INSTITUICOES? PARTICIPANTES? DA OFERTA)",
        ),
        ("demais_financeiras", r"DEMAIS INSTITUICOES? FINANCEIRAS?"),
        (
            "pj_ligadas",
            r"DEMAIS PESSOAS? JURIDICAS? LIGADAS? AO (?:EMISSOR|FUNDO)(?: E| E/OU)? (?:AOS? |AS? )?(?:PARTICIPANTES? DO CONSORCIO|COORDENADOR(?: LIDER)?|INSTITUICOES? PARTICIPANTES? DA OFERTA)",
        ),
        ("demais_pj", r"DEMAIS PESSOAS? JURIDICAS?(?! LIGADAS)"),
        (
            "pessoas_ligadas",
            r"SOCIOS ADMINISTRADORES (?:EMPREGADOS|FUNCIONARIOS) PREPOSTOS E DEMAIS PESSOAS LIGADAS AO (?:EMISSOR|FUNDO)(?: E| E/OU)? (?:AOS? |AS? )?(?:PARTICIPANTES? DO CONSORCIO|COORDENADOR(?: LIDER)?|INSTITUICOES? PARTICIPANTES? DA OFERTA)",
        ),
    ]
)

INVESTOR_CATEGORY_LABELS = {
    "pessoas_naturais": "Pessoas naturais",
    "clubes_investimento": "Clubes de investimento",
    "fundos_investimento": "Fundos de investimento",
    "previdencia_privada": "Previdencia privada",
    "seguradoras": "Seguradoras",
    "investidores_estrangeiros": "Investidores estrangeiros",
    "intermediarias_consorcio": "Intermediarias do consorcio",
    "financeiras_ligadas": "Instituicoes financeiras ligadas",
    "demais_financeiras": "Demais instituicoes financeiras",
    "pj_ligadas": "Pessoas juridicas ligadas",
    "demais_pj": "Demais pessoas juridicas",
    "pessoas_ligadas": "Pessoas fisicas ligadas",
}

INVESTOR_FAMILIES = {
    "pessoas_naturais": "Pessoas naturais",
    "clubes_investimento": "Clubes de investimento",
    "fundos_investimento": "Fundos de investimento",
    "previdencia_privada": "Previdencia e seguradoras",
    "seguradoras": "Previdencia e seguradoras",
    "investidores_estrangeiros": "Investidores estrangeiros",
    "intermediarias_consorcio": "Instituicoes financeiras",
    "financeiras_ligadas": "Instituicoes financeiras",
    "demais_financeiras": "Instituicoes financeiras",
    "pj_ligadas": "Outras pessoas juridicas",
    "demais_pj": "Outras pessoas juridicas",
    "pessoas_ligadas": "Pessoas ligadas",
}

X11_FAMILY_KEYS = {
    "PF": "Pessoas naturais",
    "PJ_NAO_FINANC": "PJ nao financeira",
    "BANCO": "Instituicoes financeiras",
    "CORRETORA_DISTRIB": "Instituicoes financeiras",
    "PJ_FINANC": "Instituicoes financeiras",
    "INVNR": "Investidores estrangeiros",
    "EAPC": "Previdencia e seguradoras",
    "EFPC": "Previdencia e seguradoras",
    "RPPS": "Previdencia e seguradoras",
    "SEGUR": "Previdencia e seguradoras",
    "CAPITALIZ": "Instituicoes financeiras",
    "COTA_FIDC": "Fundos de investimento",
    "FII": "Fundos de investimento",
    "OUTRO_FI": "Fundos de investimento",
    "CLUBE": "Clubes de investimento",
    "OUTRO": "Outros",
}

SOURCE_URLS = {
    "cvm_monthly": "https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal",
    "cvm_cadastro": "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/",
    "cvm_offers": "https://dados.cvm.gov.br/dataset/oferta-distrib",
    "anbima_secondary": "https://developers.anbima.com.br/pt/documentacao/precos-indices/apis-de-precos/fidc/",
    "b3_datawise": "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/datawise-reports/",
    "anbima_2015_study": "https://www.anbima.com.br/data/files/89/A0/02/F5/EDB675106582A275862C16A8/FIDC_1_.pdf",
}
CAD_FI_HIST_URL = f"{SOURCE_URLS['cvm_cadastro']}cad_fi_hist.zip"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--industry-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/industry_study"),
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path(".cache/cvm-industry-investors"),
    )
    parser.add_argument(
        "--cad-hist-zip",
        type=Path,
        default=Path(".cache/cvm-cadastro/cad_fi_hist.zip"),
    )
    parser.add_argument("--lookback-months", type=int, default=24)
    parser.add_argument("--skip-download", action="store_true")
    return parser.parse_args()


def ascii_upper(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", text.upper())
        if not unicodedata.combining(character)
    )


def normalized_document_text(value: object) -> str:
    text = ascii_upper(value)
    text = text.replace("N.º", "N ").replace("Nº", "N ")
    return re.sub(r"[^A-Z0-9.,$/+-]+", " ", text).strip()


def digits(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.0f}"
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    elif re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)[Ee][+-]?\d+", text):
        try:
            text = format(Decimal(text), "f").split(".", 1)[0]
        except InvalidOperation:
            pass
    return re.sub(r"\D", "", text)


def bool_series(frame: pd.DataFrame, column: str) -> pd.Series:
    values = frame[column]
    if values.dtype == bool:
        return values.fillna(False)
    return values.astype("string").fillna("").str.upper().isin({"TRUE", "1", "S", "SIM"})


def participant_group(value: object) -> str:
    text = ascii_upper(value)
    if "SINGULARE" in text or (
        ("QI " in text or "QITECH" in text)
        and any(token in text for token in ("CORRET", "DISTRIB", "CTVM", "GESTAO"))
    ):
        return "QI TECH + SINGULARE"
    if "INTRAG" in text or re.search(r"\bITAU\b", text):
        return "ITAU/INTRAG"
    if "BTG" in text and "PACTUAL" in text:
        return "BTG PACTUAL"
    if "OLIVEIRA TRUST" in text:
        return "OLIVEIRA TRUST"
    if "GENIAL" in text:
        return "GRUPO GENIAL"
    if "BEM - " in text or "BRADESCO" in text:
        return "GRUPO BRADESCO/BEM"
    if "BB GESTAO" in text or "BANCO DO BRASIL" in text:
        return "GRUPO BB"
    if "REAG" in text or "CBSF" in text:
        return "REAG/CBSF"
    return re.sub(r"\s+", " ", text).strip(" .,") or "NAO INFORMADO"


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return float(numerator / denominator) if denominator else None


def period_label(period: pd.Period) -> str:
    return period.strftime("%Y-%m")


def parse_br_number(token: str) -> float:
    cleaned = token.strip().replace(" ", "")
    if cleaned == "" or set(cleaned) == {"-"}:
        return 0.0
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(".") >= 1:
        cleaned = cleaned.replace(".", "")
    return float(cleaned)


def subscriber_bucket(value: object) -> str:
    number = float(value or 0)
    if number <= 0:
        return "0"
    if number == 1:
        return "1"
    if number <= 5:
        return "2-5"
    if number <= 10:
        return "6-10"
    if number <= 50:
        return "11-50"
    if number <= 100:
        return "51-100"
    if number <= 500:
        return "101-500"
    return ">500"


def ensure_investor_raw_files(
    raw_dir: Path,
    periods: list[pd.Period],
    *,
    allow_download: bool,
) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for year in sorted({period.year for period in periods}):
        if year < max(period.year for period in periods):
            destination = raw_dir / f"inf_mensal_fidc_{year}.zip"
            if allow_download:
                download(f"{BASE_HIST_URL}/inf_mensal_fidc_{year}.zip", destination)
    latest_year = max(period.year for period in periods)
    for period in periods:
        if period.year != latest_year:
            continue
        yyyymm = period.strftime("%Y%m")
        destination = raw_dir / f"inf_mensal_fidc_{yyyymm}.zip"
        if allow_download:
            download(f"{BASE_MONTHLY_URL}/inf_mensal_fidc_{yyyymm}.zip", destination)


def extract_x11_snapshot(
    store: RawStore,
    vehicle: pd.DataFrame,
    period: pd.Period,
) -> pd.DataFrame:
    competencia = period_label(period)
    raw = store.read_table(period.strftime("%Y%m"), "tab_X_1_1")
    if raw is None or raw.empty:
        return pd.DataFrame()

    raw = raw.copy()
    output = pd.DataFrame({"cnpj": raw["cnpj"].map(digits)})
    numeric_columns: list[str] = []
    for key in COTISTA_TIPO_LABELS:
        for source_prefix, output_prefix in (("SENIOR", "senior"), ("SUBORD", "subordinado")):
            source = f"TAB_X_NR_COTST_{source_prefix}_{key}"
            target = f"{output_prefix}_{key.lower()}"
            output[target] = to_num(raw[source]) if source in raw.columns else 0.0
            numeric_columns.append(target)
        output[f"total_{key.lower()}"] = (
            output[f"senior_{key.lower()}"] + output[f"subordinado_{key.lower()}"]
        )
        numeric_columns.append(f"total_{key.lower()}")

    output = output.groupby("cnpj", as_index=False)[numeric_columns].sum()
    month_vehicle = vehicle.loc[vehicle["competencia"].eq(competencia)].copy()
    month_vehicle["cnpj"] = month_vehicle["cnpj"].map(digits)
    month_vehicle["cnpj_fundo"] = month_vehicle["cnpj_fundo"].map(digits)
    dimensions = month_vehicle[
        [
            "cnpj",
            "cnpj_fundo",
            "denominacao",
            "pl",
            "cotistas",
            "admin_nome",
            "gestor_nome",
            "custodiante_nome",
        ]
    ].drop_duplicates("cnpj")
    output = output.merge(dimensions, on="cnpj", how="inner")
    output.insert(0, "competencia", competencia)
    output["cotistas_x11"] = output[
        [column for column in output.columns if column.startswith("total_")]
    ].sum(axis=1)
    return output


def load_cadastro_history(path: Path, role: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    role_upper = role.upper()
    with zipfile.ZipFile(path) as archive:
        frame = pd.read_csv(
            archive.open(f"cad_fi_hist_{role}.csv"),
            sep=";",
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
        )
    frame["cnpj_fundo"] = frame["CNPJ_FUNDO"].map(digits)
    frame["role_name"] = frame[role_upper].astype(str).str.strip()
    frame["evidence_start"] = pd.to_datetime(
        frame[f"DT_INI_{role_upper}"], errors="coerce"
    )
    frame["evidence_end"] = pd.to_datetime(
        frame[f"DT_FIM_{role_upper}"].replace("", pd.NA), errors="coerce"
    )
    return frame[["cnpj_fundo", "role_name", "evidence_start", "evidence_end"]]


def map_offers_to_funds(offers: pd.DataFrame, vehicle: pd.DataFrame) -> pd.DataFrame:
    mapping = vehicle[["cnpj", "cnpj_fundo"]].copy()
    mapping["cnpj"] = mapping["cnpj"].map(digits)
    mapping["cnpj_fundo"] = mapping["cnpj_fundo"].map(digits)
    mapping = mapping.drop_duplicates("cnpj")
    entity_to_fund = mapping.set_index("cnpj")["cnpj_fundo"]

    output = offers.copy()
    output["cnpj_emissor"] = output["cnpj_emissor"].map(digits)
    output["cnpj_fundo"] = output["cnpj_emissor"].map(entity_to_fund)
    output["cnpj_fundo"] = output["cnpj_fundo"].fillna(output["cnpj_emissor"])
    output["data_registro"] = pd.to_datetime(output["data_registro"], errors="coerce")
    return output


def assign_role_as_of(
    frame: pd.DataFrame,
    role: str,
    as_of: pd.Timestamp,
    current_period: pd.Period,
    offers: pd.DataFrame,
    history: pd.DataFrame,
) -> pd.DataFrame:
    name_column = f"{role}_nome"
    output = frame.copy()
    output["cnpj_fundo"] = output["cnpj_fundo"].map(digits)
    output["role_name"] = output[name_column].fillna("")
    output["role_source"] = "cadastro_atual_fallback"
    output["role_source_confidence"] = "media-baixa"

    if pd.Period(as_of, freq="M") == current_period:
        output["role_source"] = "cadastro_atual"
        output["role_source_confidence"] = "alta"
        return output

    offer_role = role if role != "admin" else "administrador"
    dated_offers = offers.loc[
        offers["data_registro"].le(as_of)
        & offers[offer_role].fillna("").astype(str).str.strip().ne("")
    ].copy()
    if not dated_offers.empty:
        dated_offers = dated_offers.sort_values("data_registro").drop_duplicates(
            "cnpj_fundo", keep="last"
        )
        offer_map = dated_offers.set_index("cnpj_fundo")[offer_role]
        matched = output["cnpj_fundo"].isin(offer_map.index)
        output.loc[matched, "role_name"] = output.loc[matched, "cnpj_fundo"].map(offer_map)
        output.loc[matched, "role_source"] = "oferta_publica_cvm_dated"
        output.loc[matched, "role_source_confidence"] = "media-alta"

    if not history.empty:
        active = history.loc[
            history["evidence_start"].le(as_of)
            & (history["evidence_end"].isna() | history["evidence_end"].ge(as_of))
        ].copy()
        active = active.sort_values("evidence_start").drop_duplicates(
            "cnpj_fundo", keep="last"
        )
        history_map = active.set_index("cnpj_fundo")["role_name"]
        matched = output["cnpj_fundo"].isin(history_map.index)
        output.loc[matched, "role_name"] = output.loc[matched, "cnpj_fundo"].map(history_map)
        output.loc[matched, "role_source"] = "cad_fi_hist_active"
        output.loc[matched, "role_source_confidence"] = "alta"
    return output


def role_share_deltas(
    vehicle: pd.DataFrame,
    offers: pd.DataFrame,
    current_period: pd.Period,
    previous_period: pd.Period,
    cad_hist_zip: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[pd.DataFrame] = []
    coverage_rows: list[dict[str, object]] = []
    current_label = period_label(current_period)
    previous_label = period_label(previous_period)
    periods = {"current": current_period, "previous": previous_period}

    for role, column in (
        ("administrador", "admin_nome"),
        ("gestor", "gestor_nome"),
        ("custodiante", "custodiante_nome"),
    ):
        period_frames: dict[str, pd.DataFrame] = {}
        history = (
            pd.DataFrame()
            if role == "administrador"
            else load_cadastro_history(cad_hist_zip, role)
        )
        for period_key, period in periods.items():
            label = period_label(period)
            month = vehicle.loc[vehicle["competencia"].eq(label)].copy()
            if role == "administrador":
                month["role_name"] = month[column].fillna("")
                month["role_source"] = "informe_mensal_cvm"
                month["role_source_confidence"] = "alta"
            else:
                month = assign_role_as_of(
                    month,
                    role,
                    period.end_time.normalize(),
                    current_period,
                    offers,
                    history,
                )
            month["participant"] = month["role_name"].map(participant_group)
            period_frames[period_key] = month
            high = month["role_source_confidence"].eq("alta")
            medium_high = month["role_source_confidence"].eq("media-alta")
            total_pl = float(month["pl"].sum())
            coverage_rows.append(
                {
                    "role": role,
                    "competencia": label,
                    "pl_total_brl": total_pl,
                    "pl_high_confidence_brl": float(month.loc[high, "pl"].sum()),
                    "share_high_confidence": safe_ratio(
                        float(month.loc[high, "pl"].sum()), total_pl
                    ),
                    "share_high_or_medium_high": safe_ratio(
                        float(month.loc[high | medium_high, "pl"].sum()), total_pl
                    ),
                    "methodology": (
                        "direct monthly filing"
                        if role == "administrador"
                        else "dated cadastro history + dated CVM offers + current cadastro fallback"
                    ),
                }
            )

        aggregates: dict[str, pd.DataFrame] = {}
        for key, frame in period_frames.items():
            dated = frame["role_source_confidence"].isin({"alta", "media-alta"})
            frame = frame.assign(pl_dated=np.where(dated, frame["pl"], 0.0))
            aggregate = frame.groupby("participant", dropna=False).agg(
                pl_brl=("pl", "sum"),
                pl_dated_brl=("pl_dated", "sum"),
                vehicles=("cnpj", "nunique"),
                funds=("cnpj_fundo", "nunique"),
            )
            aggregate["share"] = aggregate["pl_brl"] / frame["pl"].sum()
            aggregate["dated_coverage"] = np.where(
                aggregate["pl_brl"].gt(0),
                aggregate["pl_dated_brl"] / aggregate["pl_brl"],
                0.0,
            )
            aggregate["rank"] = aggregate["pl_brl"].rank(
                method="min", ascending=False
            ).astype(int)
            aggregates[key] = aggregate

        combined = aggregates["current"].add_suffix("_current").join(
            aggregates["previous"].add_suffix("_previous"), how="outer"
        )
        combined = combined.fillna(0).reset_index()
        combined.insert(0, "role", role)
        combined["delta_pl_brl"] = combined["pl_brl_current"] - combined["pl_brl_previous"]
        combined["delta_share_pp"] = (
            combined["share_current"] - combined["share_previous"]
        ) * 100
        combined["delta_rank"] = combined["rank_previous"] - combined["rank_current"]
        combined["competencia_current"] = current_label
        combined["competencia_previous"] = previous_label
        combined["history_quality"] = (
            "alta"
            if role == "administrador"
            else "reconstruida; consultar role_share_coverage.csv"
        )
        rows.append(combined)

    result = pd.concat(rows, ignore_index=True)
    result = result.sort_values(["role", "pl_brl_current"], ascending=[True, False])
    return result, pd.DataFrame(coverage_rows)


def find_first(text: str, patterns: tuple[str, ...]) -> int:
    positions = [text.find(pattern) for pattern in patterns if text.find(pattern) >= 0]
    return min(positions) if positions else -1


def parse_closing_announcement(text: str) -> dict[str, object] | None:
    normalized = normalized_document_text(text)
    closing_position = normalized.find("ANUNCIO DE ENCERRAMENTO")
    opening_position = normalized.find("ANUNCIO DE INICIO")
    if closing_position < 0 or closing_position > 1200:
        return None
    if 0 <= opening_position < closing_position:
        return None

    section_patterns = (
        "DADOS FINAIS DA OFERTA",
        "DADOS FINAIS DA DISTRIBUICAO",
        "DADOS FINAIS",
        "DADOS DE COLOCACAO",
        "QUADRO DE ALOCACAO",
        "TIPO DE INVESTIDOR NUMERO DE INVESTIDORES",
        "TIPO DE SUBSCRITOR QUANTIDADE",
    )
    section_start = find_first(normalized, section_patterns)
    if section_start < 0:
        first_category = re.search(next(iter(INVESTOR_CATEGORY_PATTERNS.values())), normalized)
        section_start = max(0, (first_category.start() - 500) if first_category else -1)
    if section_start < 0:
        return {
            "parse_status": "closing_without_investor_table",
            "normalized_text": normalized,
        }

    section = normalized[section_start : section_start + 18000]
    category_matches: list[tuple[int, int, str]] = []
    for category, pattern in INVESTOR_CATEGORY_PATTERNS.items():
        match = re.search(pattern, section)
        if match:
            category_matches.append((match.start(), match.end(), category))
    category_matches.sort()
    if len(category_matches) < 6:
        return {
            "parse_status": f"investor_table_partial_{len(category_matches)}_labels",
            "normalized_text": normalized,
        }

    header = section[: category_matches[0][0]]
    numbered_rows = bool(re.search(r"\bN (?:TIPO DE )?(?:INVESTIDOR|SUBSCRITOR)", header))
    if numbered_rows:
        adjusted_matches: list[tuple[int, int, str]] = []
        for label_start, label_end, category in category_matches:
            prefix = section[max(0, label_start - 8) : label_start]
            row_number = re.search(r"(?:^|\s)\d{1,2}\s*$", prefix)
            adjusted_start = (
                label_start - (len(prefix) - row_number.start())
                if row_number
                else label_start
            )
            adjusted_matches.append((adjusted_start, label_end, category))
        category_matches = adjusted_matches

    field_patterns = OrderedDict(
        [
            (
                "subscribers",
                r"(?:NUMERO|N|QUANTIDADE) DE (?:INVESTIDORES|SUBSCRITORES)",
            ),
            (
                "quotas_subscribed",
                r"(?:QUANTIDADE|N) DE (?:NOVAS )?(?:COTAS|VALORES MOBILIARIOS)(?: OFERTADAS)? (?:SUBSCRITAS|ADQUIRIDAS)",
            ),
            (
                "quotas_integralized",
                r"(?:QUANTIDADE|N) DE (?:NOVAS )?COTAS(?: OFERTADAS)? INTEGRALIZADAS",
            ),
            (
                "securities",
                r"QUANTIDADE DE VALORES MOBILIARIOS(?! (?:SUBSCRITOS|ADQUIRIDOS))",
            ),
        ]
    )
    observed_fields: list[tuple[int, str]] = []
    for field, pattern in field_patterns.items():
        matches = list(re.finditer(pattern, header))
        if matches:
            observed_fields.append((matches[-1].start(), field))
    observed_fields.sort()
    ordered_fields = [field for _, field in observed_fields]
    if "subscribers" not in ordered_fields:
        ordered_fields.insert(0, "subscribers")
    if not any(field in ordered_fields for field in ("quotas_subscribed", "securities")):
        ordered_fields.append("quotas_subscribed")
    subscriber_index = ordered_fields.index("subscribers")
    quota_field = "quotas_subscribed" if "quotas_subscribed" in ordered_fields else "securities"
    quota_index = ordered_fields.index(quota_field)
    expected_columns = len(ordered_fields)
    order_known = len(observed_fields) >= 2

    raw_values: dict[str, list[float]] = {}
    incomplete_rows = 0
    number_pattern = re.compile(r"(?<![A-Z0-9])(?:-+|\d[\d.]*,\d+|\d[\d.]*)(?![A-Z])")
    for index, (_, label_end, category) in enumerate(category_matches):
        next_start = (
            category_matches[index + 1][0]
            if index + 1 < len(category_matches)
            else min(len(section), label_end + 500)
        )
        fragment = section[label_end:next_start]
        tokens = [match.group(0).strip() for match in number_pattern.finditer(fragment)]
        if tokens and len(tokens) < expected_columns:
            incomplete_rows += 1
        values = [parse_br_number(token) for token in tokens[:expected_columns]]
        values += [0.0] * (expected_columns - len(values))
        raw_values[category] = values

    category_values: dict[str, dict[str, float]] = {}
    for category, values in raw_values.items():
        category_values[category] = {
            "subscribers": values[subscriber_index],
            "quotas": values[quota_index],
        }

    total_subscribers = sum(item["subscribers"] for item in category_values.values())
    total_quotas = sum(item["quotas"] for item in category_values.values())
    tail = section[category_matches[-1][1] : category_matches[-1][1] + 1200]
    total_match = re.search(r"\bTOTAL\b", tail)
    reported_total_subscribers = None
    reported_total_quotas = None
    total_validated = False
    if total_match:
        total_fragment = tail[total_match.end() : total_match.end() + 300]
        total_tokens = [
            match.group(0).strip() for match in number_pattern.finditer(total_fragment)
        ]
        if len(total_tokens) >= expected_columns:
            total_values = [
                parse_br_number(token) for token in total_tokens[:expected_columns]
            ]
            reported_total_subscribers = total_values[subscriber_index]
            reported_total_quotas = total_values[quota_index]
            total_validated = math.isclose(
                total_subscribers,
                reported_total_subscribers,
                rel_tol=1e-7,
                abs_tol=1e-6,
            ) and math.isclose(
                total_quotas,
                reported_total_quotas,
                rel_tol=1e-7,
                abs_tol=1e-4,
            )
    plausible = (
        total_subscribers >= 0
        and total_quotas >= total_subscribers
        and abs(total_subscribers - round(total_subscribers)) < 1e-6
        and total_subscribers <= 5_000_000
    )
    high_confidence = (
        plausible
        and order_known
        and incomplete_rows == 0
        and (total_validated or total_match is None)
    )

    amount_brl = None
    amount_context = normalized[: min(len(normalized), 3500)]
    amount_match = re.search(
        r"(?:NO MONTANTE DE|MONTANTE TOTAL DE|PERFAZENDO O MONTANTE TOTAL DE)[^R$]{0,120}R\$\s*([0-9. ]+,\d{2})",
        amount_context,
    )
    if amount_match:
        amount_brl = parse_br_number(amount_match.group(1))

    return {
        "parse_status": "parsed_high" if high_confidence else "parsed_medium",
        "column_order": " | ".join(ordered_fields),
        "column_order_observed": order_known,
        "expected_numeric_columns": expected_columns,
        "incomplete_category_rows": incomplete_rows,
        "total_subscribers": total_subscribers,
        "total_quotas": total_quotas,
        "reported_total_subscribers": reported_total_subscribers,
        "reported_total_quotas": reported_total_quotas,
        "total_row_validated": total_validated,
        "closing_amount_brl": amount_brl,
        "categories": category_values,
        "private_only_language": bool(
            re.search(
                r"NAO HAVENDO NEGOCIACAO EM MERCADO ORGANIZADO|SOMENTE PODERAO SER NEGOCIADAS PRIVADAMENTE",
                normalized,
            )
        ),
        "b3_or_organized_market_language": bool(
            re.search(
                r"FUNDOS21|BALCAO B3|MERCADO DE BALCAO ORGANIZADO|DEPOSITADAS? (?:E|PARA) NEGOCIACAO.*B3|NEGOCIADAS? EM MERCADO ORGANIZADO",
                normalized,
            )
        ),
        "six_month_qualified_release": bool(
            re.search(r"QUALIFICADOS?.{0,180}6 SEIS MESES|6 SEIS MESES.{0,180}QUALIFICADOS?", normalized)
        ),
        "general_public_release": bool(
            re.search(r"PUBLICO INVESTIDOR EM GERAL", normalized)
        ),
        "normalized_text": normalized,
    }


def load_closing_announcements(
    industry_dir: Path,
    lookback_start: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    index = pd.read_csv(industry_dir / "document_text_index.csv.gz", low_memory=False)
    index["document_date"] = pd.to_datetime(index["document_date"], errors="coerce")
    candidates = index.loc[
        index["document_class"].eq("emissao")
        & index["parse_status"].eq("text_ready")
        & index["document_date"].ge(lookback_start)
    ].copy()
    candidates = candidates.drop_duplicates("document_key")

    offer_rows: list[dict[str, object]] = []
    category_rows: list[dict[str, object]] = []
    detected_closings = 0
    for row in candidates.itertuples(index=False):
        cache_path = Path(str(row.cache_path))
        if not cache_path.exists():
            continue
        try:
            with gzip.open(cache_path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        text = "\n".join(page.get("text", "") for page in payload.get("pages", []))
        parsed = parse_closing_announcement(text)
        if parsed is None:
            continue
        detected_closings += 1
        base = {
            "document_key": row.document_key,
            "cnpj_fundo": digits(row.cnpj_fundo),
            "fundo": row.fundo,
            "document_date": row.document_date.date().isoformat()
            if pd.notna(row.document_date)
            else "",
            "documento_origem": row.documento_origem,
            "source_path": row.source_path,
            "cache_path": str(cache_path),
            "parse_status": parsed["parse_status"],
            "total_subscribers": parsed.get("total_subscribers"),
            "total_quotas": parsed.get("total_quotas"),
            "closing_amount_brl": parsed.get("closing_amount_brl"),
            "column_order": parsed.get("column_order", ""),
            "column_order_observed": parsed.get("column_order_observed", False),
            "expected_numeric_columns": parsed.get("expected_numeric_columns"),
            "incomplete_category_rows": parsed.get("incomplete_category_rows"),
            "reported_total_subscribers": parsed.get("reported_total_subscribers"),
            "reported_total_quotas": parsed.get("reported_total_quotas"),
            "total_row_validated": parsed.get("total_row_validated", False),
            "private_only_language": parsed.get("private_only_language", False),
            "b3_or_organized_market_language": parsed.get(
                "b3_or_organized_market_language", False
            ),
            "six_month_qualified_release": parsed.get(
                "six_month_qualified_release", False
            ),
            "general_public_release": parsed.get("general_public_release", False),
        }
        offer_rows.append(base)
        categories = parsed.get("categories", {})
        for category, values in categories.items():
            category_rows.append(
                {
                    **base,
                    "investor_category": category,
                    "investor_category_label": INVESTOR_CATEGORY_LABELS[category],
                    "investor_family": INVESTOR_FAMILIES[category],
                    "subscribers": values["subscribers"],
                    "quotas": values["quotas"],
                    "allocated_amount_proxy_brl": (
                        base["closing_amount_brl"]
                        * values["quotas"]
                        / base["total_quotas"]
                        if base["closing_amount_brl"]
                        and base["total_quotas"]
                        and values["quotas"]
                        else 0.0
                    ),
                }
            )

    offers = pd.DataFrame(offer_rows)
    categories = pd.DataFrame(category_rows)
    if not offers.empty:
        offers = offers.sort_values(["document_date", "cnpj_fundo", "document_key"])
    if not categories.empty:
        categories = categories.sort_values(
            ["document_date", "cnpj_fundo", "investor_category"]
        )
    diagnostics = {
        "text_ready_emission_documents_in_window": int(len(candidates)),
        "closing_announcements_detected": int(detected_closings),
        "closing_announcements_with_parsed_table": int(
            offers["parse_status"].str.startswith("parsed").sum()
        )
        if not offers.empty
        else 0,
        "closing_announcements_high_confidence": int(
            offers["parse_status"].eq("parsed_high").sum()
        )
        if not offers.empty
        else 0,
    }
    return offers, categories, diagnostics


def infer_named_investor_family(name: str) -> str:
    normalized = ascii_upper(name)
    if any(token in normalized for token in ("FUNDO DE INVESTIMENTO", " FIDC", " FIC ")):
        return "Fundo de investimento"
    if any(token in normalized for token in ("BANCO ", "SOCIEDADE DE CREDITO", "DTVM", "CCTVM")):
        return "Instituicao financeira"
    if "PREVID" in normalized or "SEGUR" in normalized:
        return "Previdencia ou seguradora"
    if "GRUPO ECONOMICO" in normalized or normalized.startswith("GRUPO "):
        return "Grupo economico do originador"
    return "Pessoa juridica"


def clean_named_investor_candidate(prefix: str) -> str:
    candidate = re.sub(r"\s+", " ", prefix[-320:]).strip(" ,;:-")
    candidate = re.sub(
        r"^.*?(?:EXCLUSIVAMENTE POR|INTEGRALIZADAS POR|SUBSCRITAS POR|ADQUIRIDAS POR)\s+",
        "",
        candidate,
    )
    candidate = re.split(r"\([IVX]+\)|;", candidate)[-1]
    candidate = re.sub(r"^\s*(?:E|OU)\s+", "", candidate)
    candidate = re.sub(
        r"\s*,?\s*(?:SOCIEDADE|FUNDO)?\s*(?:DEVIDAMENTE )?INSCRIT[AO].*$",
        "",
        candidate,
    )
    candidate = re.sub(r"\s+(?:INSCRIT[AO]|COM SEDE|CNPJ).*$", "", candidate)
    candidate = candidate.strip(" ,;:-")
    if len(candidate) > 190:
        candidate = candidate[-190:].lstrip(" ,;:-")
    return candidate


def load_named_investor_signals(
    industry_dir: Path,
    lookback_start: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Extract exceptional public disclosures of named anchor/exclusive holders.

    This is intentionally high precision and is not a beneficial-owner registry.
    It captures contractual clauses in which a named entity or economic group is
    explicitly allowed or required to subscribe/integralize a quota class.
    """

    index = pd.read_csv(industry_dir / "document_text_index.csv.gz", low_memory=False)
    index["document_date"] = pd.to_datetime(index["document_date"], errors="coerce")
    candidates = index.loc[
        index["parse_status"].eq("text_ready")
        & index["document_date"].ge(lookback_start)
        & index["document_class"].isin({"regulamento", "assembleia", "emissao"})
    ].drop_duplicates("document_key")

    trigger_patterns = OrderedDict(
        [
            (
                "exclusive_subscription_or_holding",
                re.compile(
                    r"(?:SUBSCRITAS?|INTEGRALIZADAS?|ADQUIRIDAS?|DETIDAS?)"
                    r"(?: E (?:SUBSCRITAS?|INTEGRALIZADAS?|ADQUIRIDAS?|DETIDAS?))?"
                    r"(?: DE FORMA PRIVADA)? EXCLUSIVAMENTE POR"
                ),
            ),
            (
                "exclusive_eligibility",
                re.compile(
                    r"(?:PODERAO SER|SERAO) (?:SUBSCRITAS?|INTEGRALIZADAS?|ADQUIRIDAS?|DETIDAS?)"
                    r" EXCLUSIVAMENTE POR"
                ),
            ),
        ]
    )
    cnpj_pattern = re.compile(
        r"(?:INSCRIT[AO][^.;]{0,90}?)?(?:NO |SOB O )?CNPJ(?:/MF)?"
        r"(?: SOB O)?(?: N)?\s*([0-9][0-9./ -]{12,24})"
    )
    rows: list[dict[str, object]] = []
    scanned_documents = 0

    for row in candidates.itertuples(index=False):
        cache_path = Path(str(row.cache_path))
        if not cache_path.exists():
            continue
        try:
            with gzip.open(cache_path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        scanned_documents += 1
        text = "\n".join(page.get("text", "") for page in payload.get("pages", []))
        normalized = normalized_document_text(text)

        for signal_type, trigger_pattern in trigger_patterns.items():
            for trigger in trigger_pattern.finditer(normalized):
                context_start = max(0, trigger.start() - 260)
                context_end = min(len(normalized), trigger.end() + 1500)
                context = normalized[context_start:context_end]
                trigger_offset = trigger.end() - context_start
                after_trigger = context[trigger_offset:]
                clause = after_trigger
                for boundary_pattern in (
                    r"\bII FUNDOS DE INVESTIMENTO CUJAS ATIVIDADES DE GESTAO",
                    r"\bAPENSO [IVX0-9]",
                    r"\bANEXO [IVX0-9]",
                    r"\b[0-9]+\.[0-9]+\.[0-9]+\.",
                ):
                    boundary = re.search(boundary_pattern, clause)
                    if boundary:
                        clause = clause[: boundary.start()]
                clause = clause[:1000]
                if re.match(
                    r"\s*INVESTIDORES?\b.{0,80}\b(?:PROFISSIONAIS|QUALIFICADOS|AUTORIZADOS)\b",
                    clause,
                ):
                    continue
                cnpj_matches = list(cnpj_pattern.finditer(clause))
                accepted_cnpj_rows = 0
                previous_match_end = 0
                for cnpj_match in cnpj_matches[:4]:
                    investor_cnpj = digits(cnpj_match.group(1))[:14]
                    fund_cnpj = digits(row.cnpj_fundo)
                    local_prefix = clause[max(previous_match_end, cnpj_match.start() - 360) : cnpj_match.start()]
                    previous_match_end = cnpj_match.end()
                    if len(investor_cnpj) != 14 or investor_cnpj == fund_cnpj:
                        continue
                    if re.search(
                        r"(?:ADMINISTRAD[AO]|ADMINISTRADO POR|GERID[AO]|GESTORA|COORDENADOR)\b",
                        local_prefix,
                    ):
                        continue
                    investor_name = clean_named_investor_candidate(local_prefix)
                    if not investor_name or len(investor_name) < 3:
                        investor_name = f"CNPJ {investor_cnpj}"
                    investor_name = re.sub(r"^[IVX]+\s+", "", investor_name).strip()
                    quota_window = normalized[max(0, trigger.start() - 220) : trigger.end()]
                    quota_scope = (
                        "subordinada junior"
                        if re.search(r"SUBORDINADAS? JUNIOR", quota_window)
                        else "subordinada mezanino"
                        if re.search(r"SUBORDINADAS? MEZANINO", quota_window)
                        else "senior"
                        if re.search(r"COTAS? SENIOR", quota_window)
                        else "classe nao determinada"
                    )
                    rows.append(
                        {
                            "document_key": row.document_key,
                            "cnpj_fundo": digits(row.cnpj_fundo),
                            "fundo": row.fundo,
                            "document_date": row.document_date.date().isoformat(),
                            "document_class": row.document_class,
                            "signal_type": signal_type,
                            "quota_scope": quota_scope,
                            "investor_name_disclosed": investor_name,
                            "investor_cnpj_disclosed": investor_cnpj,
                            "investor_family_inferred": infer_named_investor_family(
                                investor_name
                            ),
                            "evidence_context": context[:1800],
                            "source_document": row.documento_origem,
                            "source_path": row.source_path,
                            "confidence": "high_cnpj_and_exclusive_clause",
                            "scope_note": "contractual anchor/eligibility disclosure; not a systematic beneficial-owner registry",
                        }
                    )
                    accepted_cnpj_rows += 1

                group_match = re.search(
                    r"ENTIDADES? DO GRUPO(?: ECONOMICO (?:DO |DA )?)?"
                    r"((?:GRUPO )?[A-Z0-9][A-Z0-9&.-]{1,45})"
                    r"(?=\s+(?:NAO|APOS|QUE|SERAO|DEVERAO))",
                    clause[:500],
                )
                if group_match and accepted_cnpj_rows == 0:
                    investor_name = group_match.group(1).strip(" ,;:-")
                    if not investor_name.startswith("GRUPO "):
                        investor_name = f"GRUPO {investor_name}"
                    rows.append(
                        {
                            "document_key": row.document_key,
                            "cnpj_fundo": digits(row.cnpj_fundo),
                            "fundo": row.fundo,
                            "document_date": row.document_date.date().isoformat(),
                            "document_class": row.document_class,
                            "signal_type": "exclusive_originator_group",
                            "quota_scope": "subordinada junior",
                            "investor_name_disclosed": investor_name,
                            "investor_cnpj_disclosed": "",
                            "investor_family_inferred": "Grupo economico do originador",
                            "evidence_context": context[:1800],
                            "source_document": row.documento_origem,
                            "source_path": row.source_path,
                            "confidence": "high_named_group_and_exclusive_clause",
                            "scope_note": "contractual anchor/eligibility disclosure; not a systematic beneficial-owner registry",
                        }
                    )

        for named_match in re.finditer(
            r"APENAS (?:A|O) ([A-Z0-9][A-Z0-9 .&/-]{1,70}?) OU[^.]{0,240}?"
            r"PODERAO ADQUIRIR COTAS SUBORDINADAS? JUNIOR",
            normalized,
        ):
            investor_name = named_match.group(1).strip(" ,;:-")
            if investor_name in {"INVESTIDOR", "INVESTIDORES AUTORIZADOS"}:
                continue
            rows.append(
                {
                    "document_key": row.document_key,
                    "cnpj_fundo": digits(row.cnpj_fundo),
                    "fundo": row.fundo,
                    "document_date": row.document_date.date().isoformat(),
                    "document_class": row.document_class,
                    "signal_type": "named_subordinated_eligibility",
                    "quota_scope": "subordinada junior",
                    "investor_name_disclosed": investor_name,
                    "investor_cnpj_disclosed": "",
                    "investor_family_inferred": infer_named_investor_family(investor_name),
                    "evidence_context": normalized[
                        max(0, named_match.start() - 220) : named_match.end() + 260
                    ],
                    "source_document": row.documento_origem,
                    "source_path": row.source_path,
                    "confidence": "medium_high_named_clause_without_cnpj",
                    "scope_note": "contractual anchor/eligibility disclosure; not a systematic beneficial-owner registry",
                }
            )

    output = pd.DataFrame(rows)
    if not output.empty:
        output = output.sort_values(
            ["document_date", "cnpj_fundo"], ascending=[False, True]
        )
        output["_identity_key"] = np.where(
            output["investor_cnpj_disclosed"].fillna("").ne(""),
            output["investor_cnpj_disclosed"].fillna(""),
            output["investor_name_disclosed"].map(ascii_upper),
        )
        output = output.drop_duplicates(["cnpj_fundo", "_identity_key"]).drop(
            columns="_identity_key"
        )
    diagnostics = {
        "documents_scanned": scanned_documents,
        "named_investor_signals": int(len(output)),
        "funds_with_named_investor_signal": int(output["cnpj_fundo"].nunique())
        if not output.empty
        else 0,
        "signals_with_cnpj": int(output["investor_cnpj_disclosed"].ne("").sum())
        if not output.empty
        else 0,
        "systematic_beneficial_owner_coverage": False,
    }
    return output, diagnostics


def investor_stock_family(category: str) -> str:
    normalized = ascii_upper(category)
    if normalized == "PESSOA FISICA":
        return "Pessoas naturais"
    if normalized == "PJ NAO FINANCEIRA":
        return "PJ nao financeira"
    if normalized in {
        "BANCO COMERCIAL",
        "CORRETORA/DISTRIBUIDORA",
        "OUTRA PJ FINANCEIRA",
        "CAPITALIZACAO",
    }:
        return "Instituicoes financeiras"
    if normalized == "INVESTIDOR NAO RESIDENTE":
        return "Investidores estrangeiros"
    if any(token in normalized for token in ("PREVIDENCIA", "RPPS", "SEGURADORA")):
        return "Previdencia e seguradoras"
    if normalized in {
        "COTAS DE FIDC (OUTROS FIDC/FIC-FIDC)",
        "FII",
        "OUTROS FUNDOS",
    }:
        return "Fundos de investimento"
    if normalized == "CLUBE DE INVESTIMENTO":
        return "Clubes de investimento"
    return "Outros"


def build_investor_stock_delta(
    industry_dir: Path,
    current_period: pd.Period,
    previous_period: pd.Period,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = pd.read_csv(industry_dir / "cotistas_tipo_monthly.csv")
    current_label = period_label(current_period)
    previous_label = period_label(previous_period)
    frame = frame.loc[frame["competencia"].isin({current_label, previous_label})].copy()
    pivot = frame.pivot_table(
        index="tipo_cotista",
        columns="competencia",
        values="n_cotistas",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    for label in (current_label, previous_label):
        if label not in pivot.columns:
            pivot[label] = 0
    pivot = pivot.rename(
        columns={current_label: "accounts_current", previous_label: "accounts_previous"}
    )
    current_total = float(pivot["accounts_current"].sum())
    previous_total = float(pivot["accounts_previous"].sum())
    pivot["share_current"] = pivot["accounts_current"] / current_total if current_total else 0.0
    pivot["share_previous"] = (
        pivot["accounts_previous"] / previous_total if previous_total else 0.0
    )
    pivot["delta_accounts"] = pivot["accounts_current"] - pivot["accounts_previous"]
    pivot["growth"] = np.where(
        pivot["accounts_previous"].gt(0),
        pivot["accounts_current"] / pivot["accounts_previous"] - 1,
        np.nan,
    )
    pivot["delta_share_pp"] = (pivot["share_current"] - pivot["share_previous"]) * 100
    pivot["investor_family"] = pivot["tipo_cotista"].map(investor_stock_family)
    pivot["competencia_current"] = current_label
    pivot["competencia_previous"] = previous_label
    pivot["unit_note"] = "accounts by quota class/series; not unique CPF/CNPJ"
    pivot = pivot.sort_values("accounts_current", ascending=False)

    family = pivot.groupby("investor_family", as_index=False).agg(
        accounts_current=("accounts_current", "sum"),
        accounts_previous=("accounts_previous", "sum"),
    )
    family["share_current"] = (
        family["accounts_current"] / current_total if current_total else 0.0
    )
    family["share_previous"] = (
        family["accounts_previous"] / previous_total if previous_total else 0.0
    )
    family["delta_accounts"] = family["accounts_current"] - family["accounts_previous"]
    family["growth"] = np.where(
        family["accounts_previous"].gt(0),
        family["accounts_current"] / family["accounts_previous"] - 1,
        np.nan,
    )
    family["delta_share_pp"] = (family["share_current"] - family["share_previous"]) * 100
    family["competencia_current"] = current_label
    family["competencia_previous"] = previous_label
    family["unit_note"] = "accounts by quota class/series; not unique CPF/CNPJ"
    family = family.sort_values("accounts_current", ascending=False)
    return pivot, family


def build_investor_fund_profiles(
    vehicle: pd.DataFrame,
    x11: pd.DataFrame,
    offers: pd.DataFrame,
    current_period: pd.Period,
    lookback_start: pd.Timestamp,
) -> pd.DataFrame:
    current_label = period_label(current_period)
    valid_offers = offers.loc[
        bool_series(offers, "volume_registrado_valido")
        & offers["data_registro"].ge(lookback_start)
        & offers["data_registro"].le(current_period.end_time)
    ].copy()
    issued = valid_offers.groupby("cnpj_fundo", as_index=False).agg(
        first_offer_date=("data_registro", "min"),
        latest_offer_date=("data_registro", "max"),
        offer_volume_24m_brl=("valor_total_registrado_brl", "sum"),
        offers_24m=("offer_id", "nunique"),
        public_target=("publico_alvo", lambda values: " | ".join(sorted(set(values.dropna().astype(str))))),
    )
    if issued.empty:
        return pd.DataFrame()

    current = vehicle.loc[vehicle["competencia"].eq(current_label)].copy()
    current["cnpj_fundo"] = current["cnpj_fundo"].map(digits)
    current_fund = current.groupby("cnpj_fundo", as_index=False).agg(
        fund_name=("denominacao", "first"),
        current_pl_brl=("pl", "sum"),
        cotistas_x1=("cotistas", "sum"),
        administrator=("admin_nome", "first"),
        manager=("gestor_nome", "first"),
        custodian=("custodiante_nome", "first"),
    )

    x11_current = x11.loc[x11["competencia"].eq(current_label)].copy()
    if not x11_current.empty:
        total_columns = [column for column in x11_current if column.startswith("total_")]
        x11_fund = x11_current.groupby("cnpj_fundo", as_index=False)[total_columns].sum()
        x11_fund["cotistas_x11"] = x11_fund[total_columns].sum(axis=1)
        family_columns: dict[str, list[str]] = {}
        for key, family in X11_FAMILY_KEYS.items():
            family_columns.setdefault(family, []).append(f"total_{key.lower()}")
        for family, columns in family_columns.items():
            x11_fund[f"family_{ascii_upper(family).lower().replace(' ', '_')}"] = x11_fund[
                [column for column in columns if column in x11_fund.columns]
            ].sum(axis=1)
        family_value_columns = [column for column in x11_fund if column.startswith("family_")]
        if family_value_columns:
            x11_fund["dominant_investor_family"] = (
                x11_fund[family_value_columns]
                .idxmax(axis=1)
                .str.removeprefix("family_")
                .str.replace("_", " ")
            )
    else:
        x11_fund = pd.DataFrame(columns=["cnpj_fundo", "cotistas_x11"])

    output = issued.merge(current_fund, on="cnpj_fundo", how="left")
    output = output.merge(x11_fund, on="cnpj_fundo", how="left")
    output["cotistas_histogram_value"] = output["cotistas_x1"].fillna(
        output.get("cotistas_x11")
    )
    output["cotistas_bucket"] = output["cotistas_histogram_value"].map(subscriber_bucket)
    return output.sort_values("offer_volume_24m_brl", ascending=False)


def build_investor_summaries(
    offer_profiles: pd.DataFrame,
    category_rows: pd.DataFrame,
    fund_profiles: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    parsed_offers = offer_profiles.loc[
        offer_profiles["parse_status"].eq("parsed_high")
    ].copy()
    parsed_categories = category_rows.loc[
        category_rows["parse_status"].eq("parsed_high")
    ].copy()

    if parsed_categories.empty:
        category_summary = pd.DataFrame()
        family_summary = pd.DataFrame()
    else:
        total_subscribers = float(parsed_categories["subscribers"].sum())
        total_proxy = float(parsed_categories["allocated_amount_proxy_brl"].sum())
        category_summary = parsed_categories.groupby(
            ["investor_category", "investor_category_label"], as_index=False
        ).agg(
            offers_with_category=("document_key", lambda values: values[parsed_categories.loc[values.index, "subscribers"].gt(0)].nunique()),
            subscribers=("subscribers", "sum"),
            allocated_amount_proxy_brl=("allocated_amount_proxy_brl", "sum"),
        )
        category_summary["share_subscriber_accounts"] = (
            category_summary["subscribers"] / total_subscribers if total_subscribers else 0.0
        )
        category_summary["share_amount_proxy"] = (
            category_summary["allocated_amount_proxy_brl"] / total_proxy if total_proxy else 0.0
        )
        category_summary = category_summary.sort_values("subscribers", ascending=False)

        family_summary = parsed_categories.groupby("investor_family", as_index=False).agg(
            offers_with_family=("document_key", lambda values: values[parsed_categories.loc[values.index, "subscribers"].gt(0)].nunique()),
            subscribers=("subscribers", "sum"),
            allocated_amount_proxy_brl=("allocated_amount_proxy_brl", "sum"),
        )
        family_summary["share_subscriber_accounts"] = (
            family_summary["subscribers"] / total_subscribers if total_subscribers else 0.0
        )
        family_summary["share_amount_proxy"] = (
            family_summary["allocated_amount_proxy_brl"] / total_proxy if total_proxy else 0.0
        )
        family_summary = family_summary.sort_values("subscribers", ascending=False)

    histogram_rows: list[dict[str, object]] = []
    bucket_order = ["0", "1", "2-5", "6-10", "11-50", "51-100", "101-500", ">500"]
    if not parsed_offers.empty:
        parsed_offers["bucket"] = parsed_offers["total_subscribers"].map(subscriber_bucket)
        counts = parsed_offers.groupby("bucket", observed=False).agg(
            observations=("document_key", "nunique"),
            associated_amount_brl=("closing_amount_brl", "sum"),
        )
        for bucket in bucket_order:
            row = counts.loc[bucket] if bucket in counts.index else pd.Series(dtype=float)
            histogram_rows.append(
                {
                    "basis": "closing_announcement_subscribers",
                    "bucket": bucket,
                    "observations": int(row.get("observations", 0)),
                    "share_observations": safe_ratio(
                        int(row.get("observations", 0)), parsed_offers["document_key"].nunique()
                    ),
                    "associated_amount_brl": float(row.get("associated_amount_brl", 0.0)),
                }
            )
    if not fund_profiles.empty:
        counts = fund_profiles.groupby("cotistas_bucket", observed=False).agg(
            observations=("cnpj_fundo", "nunique"),
            associated_amount_brl=("current_pl_brl", "sum"),
        )
        for bucket in bucket_order:
            row = counts.loc[bucket] if bucket in counts.index else pd.Series(dtype=float)
            histogram_rows.append(
                {
                    "basis": "latest_monthly_accounts_for_24m_issuers",
                    "bucket": bucket,
                    "observations": int(row.get("observations", 0)),
                    "share_observations": safe_ratio(
                        int(row.get("observations", 0)), fund_profiles["cnpj_fundo"].nunique()
                    ),
                    "associated_amount_brl": float(row.get("associated_amount_brl", 0.0)),
                }
            )
    return category_summary, family_summary, pd.DataFrame(histogram_rows)


def build_cedent_opportunity_map(
    industry_dir: Path,
    current_market_pl: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    cedentes = pd.read_csv(
        industry_dir / "cedentes_structured.csv.gz",
        low_memory=False,
        dtype={"cnpj_fundo": "string", "cnpj_participante": "string"},
    )
    accepted = cedentes.loc[
        bool_series(cedentes, "ativo_curadoria")
        & cedentes["candidate_status"].eq("accepted")
        & cedentes["participant_type"].eq("cedente_originador")
    ].copy()
    if accepted.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    accepted["cnpj_fundo"] = accepted["cnpj_fundo"].map(digits)
    accepted["cnpj_cedente"] = accepted["cnpj_participante"].map(digits)
    accepted["cedent_name_document"] = (
        accepted["nome_fantasia"].fillna("").astype(str).str.strip()
    )
    empty = accepted["cedent_name_document"].eq("")
    accepted.loc[empty, "cedent_name_document"] = accepted.loc[
        empty, "razao_social"
    ].fillna("")
    registry_path = industry_dir / "participant_registry.csv.gz"
    registry_name_map: dict[str, str] = {}
    if registry_path.exists():
        registry = pd.read_csv(registry_path, dtype=str, low_memory=False)
        registry["cnpj"] = registry["cnpj"].map(digits)
        registry["registry_name"] = registry["nome_fantasia"].fillna("").str.strip()
        missing_registry_name = registry["registry_name"].eq("")
        registry.loc[missing_registry_name, "registry_name"] = registry.loc[
            missing_registry_name, "razao_social"
        ].fillna("")
        registry_name_map = (
            registry.loc[registry["registry_name"].ne("")]
            .drop_duplicates("cnpj")
            .set_index("cnpj")["registry_name"]
            .to_dict()
        )
    accepted["cedent_name"] = accepted["cnpj_cedente"].map(registry_name_map)
    accepted["cedent_name"] = accepted["cedent_name"].fillna(
        accepted["cedent_name_document"]
    )
    serasa_named = accepted["cedent_name_document"].map(ascii_upper).str.contains(
        "SERASA S.A", na=False
    )
    accepted.loc[serasa_named, "cedent_name"] = "SERASA S.A."
    accepted["cedent_key"] = np.where(
        accepted["cnpj_cedente"].str.len().eq(14),
        accepted["cnpj_cedente"],
        accepted["cedent_name"].map(ascii_upper),
    )
    accepted["current_pl_brl"] = pd.to_numeric(accepted["pl"], errors="coerce").fillna(
        pd.to_numeric(accepted["pl_atual_brl"], errors="coerce")
    ).fillna(0.0)
    for column in ("valid_volume_2024_brl", "valid_volume_2025_brl", "valid_volume_2026_brl"):
        accepted[column] = pd.to_numeric(accepted[column], errors="coerce").fillna(0.0)
    accepted["issuance_2024_2026_brl"] = accepted[
        ["valid_volume_2024_brl", "valid_volume_2025_brl", "valid_volume_2026_brl"]
    ].sum(axis=1)
    accepted["confidence"] = pd.to_numeric(
        accepted["score_confianca_final"], errors="coerce"
    ).fillna(0.0)

    fund_counts = accepted.groupby("cnpj_fundo")["cedent_key"].transform("nunique").clip(lower=1)
    accepted["fractional_current_pl_brl"] = accepted["current_pl_brl"] / fund_counts
    accepted["fractional_issuance_brl"] = accepted["issuance_2024_2026_brl"] / fund_counts
    fund_map = accepted.sort_values("confidence", ascending=False).drop_duplicates(
        ["cnpj_fundo", "cedent_key"]
    )

    opportunity = fund_map.groupby(["cedent_key", "cnpj_cedente"], dropna=False).agg(
        cedent_name=("cedent_name", "first"),
        document_names=(
            "cedent_name_document",
            lambda values: " | ".join(sorted(set(values.dropna().astype(str)))[:3]),
        ),
        funds=("cnpj_fundo", "nunique"),
        linked_current_pl_gross_brl=("current_pl_brl", "sum"),
        linked_current_pl_fractional_brl=("fractional_current_pl_brl", "sum"),
        linked_issuance_gross_brl=("issuance_2024_2026_brl", "sum"),
        linked_issuance_fractional_brl=("fractional_issuance_brl", "sum"),
        confidence_median=("confidence", "median"),
        sector=("setor", lambda values: " | ".join(sorted(set(values.dropna().astype(str)))[:3])),
        administrators=("administrador", lambda values: " | ".join(sorted(set(values.dropna().astype(str)))[:4])),
        managers=("gestor", lambda values: " | ".join(sorted(set(values.dropna().astype(str)))[:4])),
        custodians=("custodiante", lambda values: " | ".join(sorted(set(values.dropna().astype(str)))[:4])),
        latest_document=("documento_origem", "last"),
    ).reset_index()
    opportunity["commercial_signal_brl"] = (
        opportunity["linked_current_pl_fractional_brl"]
        + opportunity["linked_issuance_fractional_brl"]
    )
    opportunity["priority_score"] = (
        np.log1p(opportunity["commercial_signal_brl"])
        * opportunity["confidence_median"].clip(lower=0.4)
        * (1 + np.log1p(opportunity["funds"]))
    )
    opportunity = opportunity.sort_values("priority_score", ascending=False)
    opportunity.insert(0, "commercial_rank", range(1, len(opportunity) + 1))

    unique_funds = fund_map.sort_values("confidence", ascending=False).drop_duplicates("cnpj_fundo")
    covered_pl = float(unique_funds["current_pl_brl"].sum())
    covered_issuance = float(unique_funds["issuance_2024_2026_brl"].sum())
    total_issuance = float(
        cedentes.sort_values("score_confianca_final", ascending=False)
        .drop_duplicates("cnpj_fundo")[[
            "valid_volume_2024_brl",
            "valid_volume_2025_brl",
            "valid_volume_2026_brl",
        ]]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        .sum(axis=1)
        .sum()
    )
    diagnostics = {
        "accepted_cedent_rows": int(len(accepted)),
        "funds_with_named_accepted_cedent": int(fund_map["cnpj_fundo"].nunique()),
        "linked_current_pl_brl": covered_pl,
        "linked_current_pl_share": safe_ratio(covered_pl, current_market_pl),
        "linked_issuance_2024_2026_brl": covered_issuance,
        "curated_universe_issuance_2024_2026_brl": total_issuance,
        "linked_issuance_share_within_curated_universe": safe_ratio(
            covered_issuance, total_issuance
        ),
        "gross_linked_values_are_not_additive": True,
    }
    return opportunity, fund_map, diagnostics


def build_secondary_market_proxies(
    offers: pd.DataFrame,
    closing_profiles: pd.DataFrame,
    lookback_start: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, object]]:
    valid = offers.loc[
        bool_series(offers, "volume_registrado_valido")
        & offers["data_registro"].ge(lookback_start)
    ].copy()
    valid["offer_type_normalized"] = valid["tipo_oferta"].map(ascii_upper)
    valid["year"] = valid["data_registro"].dt.year
    annual = valid.groupby(["year", "offer_type_normalized"], as_index=False).agg(
        registered_volume_brl=("valor_total_registrado_brl", "sum"),
        registered_offers=("offer_id", "nunique"),
        issuers=("cnpj_fundo", "nunique"),
    )
    annual["metric_scope"] = "registered_public_distribution_not_trading_turnover"

    parsed_closings = closing_profiles.loc[
        closing_profiles["parse_status"].eq("parsed_high")
    ].copy()
    diagnostics = {
        "registered_secondary_offer_volume_brl": float(
            valid.loc[valid["offer_type_normalized"].str.contains("SECUNDARIA"), "valor_total_registrado_brl"].sum()
        ),
        "registered_secondary_offers": int(
            valid.loc[valid["offer_type_normalized"].str.contains("SECUNDARIA"), "offer_id"].nunique()
        ),
        "closing_documents_with_private_only_language": int(
            parsed_closings["private_only_language"].sum()
        )
        if not parsed_closings.empty
        else 0,
        "closing_documents_with_b3_or_organized_market_language": int(
            parsed_closings["b3_or_organized_market_language"].sum()
        )
        if not parsed_closings.empty
        else 0,
        "closing_documents_with_six_month_qualified_release": int(
            parsed_closings["six_month_qualified_release"].sum()
        )
        if not parsed_closings.empty
        else 0,
        "cvm_trade_level_turnover_available": False,
        "anbima_fidc_pricing_api_has_volume_field": False,
        "anbima_fidc_pricing_api_fields": [
            "taxa_compra",
            "taxa_venda",
            "taxa_indicativa",
            "pu",
            "percent_pu_par",
            "duration",
        ],
        "actual_trade_volume_source": "B3 Fundos21 / OTC records; detailed history via B3 DataWise or participant access",
        "historical_public_benchmark": {
            "year": 2014,
            "volume_brl": 4_200_000_000.0,
            "operations": 4_300,
            "concentration_note": "one FIDC represented more than half of registered volume",
            "source": SOURCE_URLS["anbima_2015_study"],
        },
    }
    return annual, diagnostics


def source_ledger() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "module": "administrator_share_delta",
                "source": "CVM FIDC monthly filing, Tables I and IV",
                "url": SOURCE_URLS["cvm_monthly"],
                "observation_unit": "month x reporting vehicle",
                "status": "direct",
                "limitation": "provider migrations can create PL jumps without net fundraising",
            },
            {
                "module": "manager_custodian_share_delta",
                "source": "CVM cad_fi_hist + current registro_fundo_classe + dated public offers",
                "url": SOURCE_URLS["cvm_cadastro"],
                "observation_unit": "fund/class x role x validity interval",
                "status": "reconstructed",
                "limitation": "post-RCVM175 role-change history is not fully exposed in one public historical file; fallback coverage is reported",
            },
            {
                "module": "investor_stock_profile",
                "source": "CVM FIDC monthly filing, Tables X.1 and X.1.1",
                "url": SOURCE_URLS["cvm_monthly"],
                "observation_unit": "accounts by quota series and investor category",
                "status": "direct",
                "limitation": "accounts are not unique CPF/CNPJ and no invested value by investor category is published",
            },
            {
                "module": "primary_offer_investors",
                "source": "CVM/Fundos.NET closing announcements, Resolution 160 Annex N tables",
                "url": SOURCE_URLS["cvm_offers"],
                "observation_unit": "offer x investor category",
                "status": "direct_document_extraction",
                "limitation": "beneficial-owner names are generally confidential; amount allocation is a quota-count proxy when used",
            },
            {
                "module": "named_investor_signals",
                "source": "CVM/Fundos.NET regulations, assemblies and issuance documents",
                "url": SOURCE_URLS["cvm_offers"],
                "observation_unit": "fund x contractual named anchor or exclusive eligible holder",
                "status": "exceptional_direct_document_extraction",
                "limitation": "non-systematic disclosure; a named eligible or anchor entity is not proof of the full current beneficial-owner register",
            },
            {
                "module": "cedents",
                "source": "CVM/Fundos.NET regulations and issuance documents",
                "url": SOURCE_URLS["cvm_monthly"],
                "observation_unit": "fund x named participant x documentary evidence",
                "status": "curated_document_extraction",
                "limitation": "open-pool and generic multi-cedent structures may intentionally have no single named cedent",
            },
            {
                "module": "secondary_pricing",
                "source": "ANBIMA FIDC secondary-market pricing API",
                "url": SOURCE_URLS["anbima_secondary"],
                "observation_unit": "date x priced FIDC quota",
                "status": "available_with_authentication",
                "limitation": "publishes rates and PUs, not traded volume or trade count",
            },
            {
                "module": "secondary_turnover",
                "source": "B3 Fundos21 / OTC; B3 DataWise Reports",
                "url": SOURCE_URLS["b3_datawise"],
                "observation_unit": "registered trade",
                "status": "not_in_free_cvm_anbima_open_data",
                "limitation": "current volume and speed require B3/participant data; CVM secondary offers are not turnover",
            },
        ]
    )


def secondary_market_data_request() -> pd.DataFrame:
    fields = [
        ("trade_date", "Data do negocio", "median trade gap; monthly turnover"),
        ("fidc_identifier", "Codigo B3, ISIN and CNPJ/class/series", "join to CVM vehicle and quota series"),
        ("trade_identifier", "Unique trade/registration id", "deduplicate and count operations"),
        ("quantity", "Quantidade negociada", "turnover in quota units"),
        ("financial_volume_brl", "Volume financeiro", "ADTV and annual traded volume"),
        ("price_or_pu", "Preco/PU do negocio", "dispersion and execution quality"),
        ("rate_if_available", "Taxa do negocio", "spread evolution versus ANBIMA indicative rate"),
        ("buyer_participant", "Participante comprador, anonymized if required", "buyer concentration and repeat liquidity"),
        ("seller_participant", "Participante vendedor, anonymized if required", "seller concentration and repeat liquidity"),
        ("trade_status", "Registered/cancelled/corrected", "exclude reversals and corrections"),
        ("market_venue", "Fundos21/OTC/organized venue", "consistent market scope"),
        ("settlement_date", "Data de liquidacao", "time-to-settle; not time-to-sell"),
    ]
    return pd.DataFrame(
        [
            {
                "field": field,
                "description": description,
                "derived_use": use,
                "preferred_source": "B3 DataWise or participant Fundos21 extract",
                "minimum_history": "36 months",
            }
            for field, description, use in fields
        ]
    )


def json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if pd.isna(value) or math.isinf(float(value)) else float(value)
    if isinstance(value, (pd.Timestamp, pd.Period)):
        return str(value)
    if pd.isna(value) if not isinstance(value, str) else False:
        return None
    return value


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not args.cad_hist_zip.exists() and not args.skip_download:
        args.cad_hist_zip.parent.mkdir(parents=True, exist_ok=True)
        download(CAD_FI_HIST_URL, args.cad_hist_zip)
    metadata = json.loads((args.industry_dir / "metadata.json").read_text())
    current_period = pd.Period(str(metadata["competencia_snapshot"]), freq="M")
    previous_period = current_period - 12
    lookback_period = current_period - (args.lookback_months - 1)
    lookback_start = lookback_period.start_time

    vehicle = pd.read_csv(args.industry_dir / "vehicle_monthly.csv.gz", low_memory=False)
    offers = pd.read_csv(args.industry_dir / "issuance_offers.csv.gz", low_memory=False)
    offers = map_offers_to_funds(offers, vehicle)

    role_deltas, role_coverage = role_share_deltas(
        vehicle,
        offers,
        current_period,
        previous_period,
        args.cad_hist_zip,
    )
    role_deltas.to_csv(args.output_dir / "role_market_share_delta.csv", index=False)
    role_coverage.to_csv(args.output_dir / "role_share_coverage.csv", index=False)

    x11_periods = [previous_period, current_period]
    ensure_investor_raw_files(
        args.raw_dir,
        x11_periods,
        allow_download=not args.skip_download,
    )
    store = RawStore(args.raw_dir, allow_download=False)
    x11_frames = [extract_x11_snapshot(store, vehicle, period) for period in x11_periods]
    x11_frames = [frame for frame in x11_frames if not frame.empty]
    x11 = pd.concat(x11_frames, ignore_index=True) if x11_frames else pd.DataFrame()
    if not x11.empty:
        x11.to_csv(
            args.output_dir / "investor_type_vehicle_snapshots.csv.gz",
            index=False,
            compression="gzip",
        )

    investor_stock_delta, investor_stock_family_delta = build_investor_stock_delta(
        args.industry_dir,
        current_period,
        previous_period,
    )
    investor_stock_delta.to_csv(
        args.output_dir / "investor_stock_type_delta.csv", index=False
    )
    investor_stock_family_delta.to_csv(
        args.output_dir / "investor_stock_family_delta.csv", index=False
    )

    closing_profiles, closing_categories, closing_diagnostics = load_closing_announcements(
        args.industry_dir,
        lookback_start,
    )
    closing_profiles.to_csv(args.output_dir / "investor_offer_profiles.csv", index=False)
    closing_categories.to_csv(args.output_dir / "investor_offer_categories.csv", index=False)

    named_investor_signals, named_investor_diagnostics = load_named_investor_signals(
        args.industry_dir,
        lookback_start,
    )
    named_investor_signals.to_csv(
        args.output_dir / "named_investor_document_signals.csv", index=False
    )

    fund_profiles = build_investor_fund_profiles(
        vehicle,
        x11,
        offers,
        current_period,
        lookback_start,
    )
    fund_profiles.to_csv(args.output_dir / "investor_fund_profiles.csv", index=False)
    category_summary, family_summary, investor_histogram = build_investor_summaries(
        closing_profiles,
        closing_categories,
        fund_profiles,
    )
    category_summary.to_csv(args.output_dir / "investor_offer_type_summary.csv", index=False)
    family_summary.to_csv(args.output_dir / "investor_offer_family_summary.csv", index=False)
    investor_histogram.to_csv(args.output_dir / "investor_histogram.csv", index=False)

    current_market_pl = float(
        vehicle.loc[vehicle["competencia"].eq(period_label(current_period)), "pl"].sum()
    )
    cedent_opportunities, cedent_fund_map, cedent_diagnostics = build_cedent_opportunity_map(
        args.industry_dir,
        current_market_pl,
    )
    cedent_opportunities.to_csv(args.output_dir / "cedent_opportunity_map.csv", index=False)
    cedent_fund_map.to_csv(args.output_dir / "cedent_fund_map.csv", index=False)

    secondary_proxies, secondary_diagnostics = build_secondary_market_proxies(
        offers,
        closing_profiles,
        lookback_start,
    )
    secondary_proxies.to_csv(args.output_dir / "secondary_market_proxies.csv", index=False)
    source_ledger().to_csv(args.output_dir / "extended_source_ledger.csv", index=False)
    secondary_market_data_request().to_csv(
        args.output_dir / "secondary_market_b3_data_request.csv", index=False
    )

    role_top = (
        role_deltas.sort_values(["role", "share_current"], ascending=[True, False])
        .groupby("role", as_index=False, group_keys=False)
        .head(12)
    )
    cedent_top = cedent_opportunities.head(20)

    summary = json_safe(
        {
            "schema_version": "fidc-extended-market-intelligence/v1",
            "pl_snapshot": period_label(current_period),
            "previous_share_snapshot": period_label(previous_period),
            "investor_and_offer_window_start": lookback_start.date().isoformat(),
            "current_market_pl_brl": current_market_pl,
            "role_market_share_top": role_top.to_dict("records"),
            "role_share_coverage": role_coverage.to_dict("records"),
            "closing_announcement_diagnostics": closing_diagnostics,
            "named_investor_diagnostics": named_investor_diagnostics,
            "named_investor_examples": named_investor_signals.head(20).to_dict("records"),
            "investor_stock_family_delta": investor_stock_family_delta.to_dict("records"),
            "investor_offer_family_summary": family_summary.to_dict("records"),
            "investor_histogram": investor_histogram.to_dict("records"),
            "cedent_diagnostics": cedent_diagnostics,
            "cedent_opportunities_top": cedent_top.to_dict("records"),
            "secondary_market": secondary_diagnostics,
            "secondary_market_proxies": secondary_proxies.to_dict("records"),
            "methodological_conclusions": {
                "named_beneficial_owners_systematically_public": False,
                "investor_type_counts_public": True,
                "investor_type_invested_value_public": False,
                "current_secondary_trade_volume_in_cvm_open_data": False,
                "anbima_secondary_pricing_is_trade_volume": False,
            },
        }
    )
    (args.output_dir / "extended_market_intelligence.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "pl_snapshot": period_label(current_period),
                "role_rows": len(role_deltas),
                "closing_announcements": closing_diagnostics,
                "named_investors": named_investor_diagnostics,
                "investor_funds": len(fund_profiles),
                "cedents": len(cedent_opportunities),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
