#!/usr/bin/env python3
"""Build the publication-grade dataset used by the FIDC president deck.

The script deliberately keeps census-like CVM evidence separate from targeted
document curation.  It is designed to be rerun after the monthly Industry
pipeline refreshes ``industry_fund_snapshot.csv.gz``.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import re
import unicodedata
from urllib.request import urlopen
import zipfile

import pandas as pd


ANBIMA_MACRO_MAP = {
    "Financeiro": "Financeiro",
    "Imobiliario": "Financeiro",
    "Factoring": "Fomento Mercantil",
    "Comercial": "Agro, Indústria e Comércio",
    "Industrial": "Agro, Indústria e Comércio",
    "Servicos": "Agro, Indústria e Comércio",
    "Agronegocio": "Agro, Indústria e Comércio",
    "Setor publico": "Outros",
    "Acoes judiciais": "Outros",
}

ANBIMA_CLASS_ORDER = [
    "Financeiro",
    "Agro, Indústria e Comércio",
    "Outros",
    "Fomento Mercantil",
    "Meios de pagamento | classe não determinada",
    "Sem evidência suficiente",
]

CVM_OFFERS_URL = (
    "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/"
    "oferta_distribuicao.zip"
)

CARD_CLASS_OVERRIDES = {
    "62393679000183": "Agro, Indústria e Comércio",  # CloudWalk Bela
    "60356171000180": "Agro, Indústria e Comércio",  # CloudWalk PI
    "44124617000194": "Agro, Indústria e Comércio",  # CloudWalk Akira II
    "28169275000172": "Outros",  # PagSeguro I
}

CARD_SAMPLE_AUDIT = [
    {
        "fundo": "CloudWalk Bela FIDC",
        "cnpj": "62.393.679/0001-83",
        "classe_declarada": "Agro, Indústria e Comércio - Recebíveis Comerciais",
        "status": "EXPLÍCITA",
        "documento": "Regulamento de 19/02/2026, item 1.7",
        "url": "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=1117954",
    },
    {
        "fundo": "CloudWalk PI FIDC",
        "cnpj": "60.356.171/0001-80",
        "classe_declarada": "Agro, Indústria e Comércio - Recebíveis Comerciais",
        "status": "EXPLÍCITA",
        "documento": "Regulamento de 04/09/2025, item 1.7",
        "url": "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=993687",
    },
    {
        "fundo": "CloudWalk Akira II FIDC",
        "cnpj": "44.124.617/0001-94",
        "classe_declarada": "Agro, Indústria e Comércio - Recebíveis Comerciais",
        "status": "EXPLÍCITA",
        "documento": "Regulamento de 28/02/2025, item 1.10",
        "url": "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=851798",
    },
    {
        "fundo": "Tapso FIDC",
        "cnpj": "26.287.464/0001-14",
        "classe_declarada": "Não localizada no regulamento público consultado",
        "status": "INDETERMINADA",
        "documento": "Regulamento público: lastro em recebíveis Stone/Pagar.me",
        "url": "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=726965",
    },
    {
        "fundo": "PagSeguro I FIDC",
        "cnpj": "28.169.275/0001-72",
        "classe_declarada": "Outros - Multicarteira Outros",
        "status": "EXPLÍCITA",
        "documento": "Regulamento de 25/03/2026, item 3.4",
        "url": "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=1149521",
    },
]

ANBIMA_PUBLIC_ISSUANCE = [
    {
        "ano": 2023,
        "volume_publicado_brl": 38.7e9,
        "publicado_em": "2024-01-18",
        "fonte": "ANBIMA - fechamento de 2023",
        "operacoes_publicadas": pd.NA,
        "url": "https://www.anbima.com.br/pt_br/noticias/ofertas-no-mercado-de-capitais-chegam-a-r-463-7-bilhoes-em-2023.htm",
        "nota_vintage": "A apresentação de fechamento de 2024 revisou 2023 para R$ 43,7 bi.",
    },
    {
        "ano": 2024,
        "volume_publicado_brl": 81.41e9,
        "publicado_em": "2025-01",
        "fonte": "ANBIMA - coletiva de mercado de capitais 2024",
        "operacoes_publicadas": 918,
        "url": "https://www.anbima.com.br/data/files/56/66/80/A5/DAE849109036A849B82BA2A8/Coletiva_MercadodeCapitais_2024_apresentacao.pdf",
        "nota_vintage": "A publicação de 2025 implica base comparável de cerca de R$ 82,9 bi.",
    },
    {
        "ano": 2025,
        "volume_publicado_brl": 90.8e9,
        "publicado_em": "2026-01-22",
        "fonte": "ANBIMA - fechamento de 2025",
        "operacoes_publicadas": "> 1.000",
        "url": "https://www.anbima.com.br/pt_br/imprensa/ofertas-no-mercado-de-capitais-atingem-r-838-8-bilhoes-e-batem-recorde-em-2025.htm",
        "nota_vintage": "ANBIMA informa crescimento de 9,5% sobre sua base comparável de 2024.",
    },
]

ANBIMA_CLASS_DEFINITIONS = [
    {
        "classe": "Fomento Mercantil",
        "explicacao": (
            "Carteira pulverizada de recebíveis cedidos por diversos originadores "
            "para antecipação de recursos, incluindo duplicatas, notas, cheques e factoring."
        ),
        "focos": "Fomento mercantil / factoring",
    },
    {
        "classe": "Financeiro",
        "explicacao": (
            "Recebíveis originados em crédito imobiliário, consignado, pessoal, "
            "financiamento de veículos ou combinação dessas carteiras."
        ),
        "focos": "Imobiliário | consignado | pessoal | veículos | multicarteira",
    },
    {
        "classe": "Agro, Indústria e Comércio",
        "explicacao": (
            "Crédito do setor real: infraestrutura, recebíveis comerciais, crédito "
            "corporativo, agronegócio ou combinação desses focos."
        ),
        "focos": "Infra | comerciais | corporativo | agro | multicarteira",
    },
    {
        "classe": "Outros",
        "explicacao": (
            "Recuperação de créditos vencidos, poder público e carteiras com dois "
            "ou mais tipos que não se concentram nas classes anteriores."
        ),
        "focos": "NPL/recuperação | poder público | multicarteira outros",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/industry_study"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/fidc_presidente_bba_20260711_v2"),
    )
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument(
        "--cvm-offers-zip",
        type=Path,
        default=Path(".cache/cvm-offers/oferta_distribuicao.zip"),
    )
    parser.add_argument(
        "--cadastro-history-zip",
        type=Path,
        default=Path(".cache/cvm-cadastro/cad_fi_hist.zip"),
    )
    parser.add_argument("--refresh-cvm-offers", action="store_true")
    return parser.parse_args()


def read_csv(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, **kwargs)


def as_records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def role_current_rows(role_delta: pd.DataFrame, role: str) -> pd.DataFrame:
    rows = role_delta.loc[role_delta["role"].eq(role)].copy()
    return rows.sort_values(["share_current", "pl_brl_current"], ascending=False)


def digits(value: object) -> str:
    return re.sub(r"\D", "", "" if pd.isna(value) else str(value))


def ascii_upper(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper()


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
    return re.sub(r"\s+", " ", text).strip(" .,") or "NÃO INFORMADO"


def classify_anbima_macro(rows: pd.DataFrame) -> pd.Series:
    classification = rows["segmento_principal"].map(ANBIMA_MACRO_MAP)
    card = rows["segmento_principal"].eq("Cartao de credito")
    classification = classification.where(
        ~card, "Meios de pagamento | classe não determinada"
    )
    fund_cnpj = rows["cnpj_fundo"].map(digits)
    for cnpj, category in CARD_CLASS_OVERRIDES.items():
        classification = classification.where(~fund_cnpj.eq(cnpj), category)
    return classification.fillna("Sem evidência suficiente")


def ensure_cvm_offers_zip(path: Path, *, refresh: bool) -> Path:
    if path.exists() and not refresh:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(CVM_OFFERS_URL, timeout=120) as response:  # noqa: S310 - fixed CVM URL
        payload = response.read()
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        if "oferta_resolucao_160.csv" not in archive.namelist():
            raise ValueError("CVM offers ZIP is missing oferta_resolucao_160.csv")
    path.write_bytes(payload)
    return path


def read_cvm_r160(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        return pd.read_csv(
            archive.open("oferta_resolucao_160.csv"),
            sep=";",
            encoding="latin-1",
            low_memory=False,
        )


def build_offer_evidence(
    r160: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    offers = r160.loc[
        r160["Valor_Mobiliario"].eq("Cotas de FIDC")
        & r160["Tipo_Oferta"].eq("PRIMARIA")
        & r160["Status_Requerimento"].eq("Oferta Encerrada")
    ].copy()
    offers["data_registro"] = pd.to_datetime(offers["Data_Registro"], errors="coerce")
    offers["data_encerramento"] = pd.to_datetime(
        offers["Data_Encerramento"], errors="coerce"
    )
    offers["ano"] = offers["data_encerramento"].dt.year.astype("Int64")
    offers["volume_registrado_brl"] = pd.to_numeric(
        offers["Valor_Total_Registrado"], errors="coerce"
    ).fillna(0.0)
    offers["cnpj_emissor"] = offers["CNPJ_Emissor"].map(digits)
    role_columns = {
        "administrador": "Administrador",
        "gestor": "Gestor",
        "custodiante": "Custodiante",
    }
    for role, source in role_columns.items():
        offers[role] = offers[source].map(participant_group)

    annual_rows = []
    role_rows = []
    structure_rows = []
    for year in (2023, 2024, 2025):
        year_rows = offers.loc[offers["ano"].eq(year)].copy()
        total_volume = float(year_rows["volume_registrado_brl"].sum())
        annual_row = {
            "ano": year,
            "requerimentos_encerrados": int(year_rows["Numero_Requerimento"].nunique()),
            "volume_registrado_brl": total_volume,
            "volume_registrado_bi": total_volume / 1e9,
            "metodologia": (
                "RCVM 160 rito automático; ofertas primárias encerradas; "
                "montante máximo registrado, não valor efetivamente colocado"
            ),
        }
        for role, source in role_columns.items():
            known = year_rows[source].fillna("").astype(str).str.strip().ne("")
            annual_row[f"{role}_cobertura_linhas"] = float(known.mean()) if len(year_rows) else 0.0
            annual_row[f"{role}_cobertura_volume"] = (
                float(year_rows.loc[known, "volume_registrado_brl"].sum() / total_volume)
                if total_volume
                else 0.0
            )
            grouped = year_rows.groupby(role, dropna=False).agg(
                volume_registrado_brl=("volume_registrado_brl", "sum"),
                ofertas=("Numero_Requerimento", "nunique"),
                emissores=("cnpj_emissor", "nunique"),
            )
            grouped["share"] = grouped["volume_registrado_brl"] / total_volume
            grouped["rank"] = grouped["volume_registrado_brl"].rank(
                method="min", ascending=False
            )
            grouped = grouped.reset_index()
            grouped.insert(0, "ano", year)
            grouped.insert(0, "role", role)
            role_rows.extend(grouped.to_dict("records"))
        annual_rows.append(annual_row)

        all_same = (
            year_rows["administrador"].eq(year_rows["gestor"])
            & year_rows["gestor"].eq(year_rows["custodiante"])
        )
        flags = {
            "todos_iguais": all_same,
            "administrador_igual_custodiante": year_rows["administrador"].eq(
                year_rows["custodiante"]
            ),
            "administrador_igual_gestor": year_rows["administrador"].eq(
                year_rows["gestor"]
            ),
            "gestor_igual_custodiante": year_rows["gestor"].eq(
                year_rows["custodiante"]
            ),
        }
        for pattern, flag in flags.items():
            structure_rows.append(
                {
                    "ano": year,
                    "padrao": pattern,
                    "share_ofertas": float(flag.mean()) if len(year_rows) else 0.0,
                    "share_volume_registrado": (
                        float(year_rows.loc[flag, "volume_registrado_brl"].sum() / total_volume)
                        if total_volume
                        else 0.0
                    ),
                }
            )

    combinations = (
        offers.loc[offers["ano"].eq(2025)]
        .groupby(["administrador", "gestor", "custodiante"], dropna=False)
        .agg(
            ofertas=("Numero_Requerimento", "nunique"),
            volume_registrado_brl=("volume_registrado_brl", "sum"),
        )
        .reset_index()
        .sort_values("volume_registrado_brl", ascending=False)
    )
    return (
        pd.DataFrame(annual_rows),
        pd.DataFrame(role_rows),
        pd.DataFrame(structure_rows),
        combinations,
    )


def load_cadastro_history(path: Path, role: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(
            columns=["cnpj_fundo", "role_name", "evidence_start", "evidence_end"]
        )
    source = f"cad_fi_hist_{role}.csv"
    with zipfile.ZipFile(path) as archive:
        frame = pd.read_csv(
            archive.open(source),
            sep=";",
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
        )
    role_upper = role.upper()
    frame["cnpj_fundo"] = frame["CNPJ_FUNDO"].map(digits)
    frame["role_name"] = frame[role_upper].astype(str).str.strip()
    frame["evidence_start"] = pd.to_datetime(
        frame[f"DT_INI_{role_upper}"], errors="coerce"
    )
    frame["evidence_end"] = pd.to_datetime(
        frame[f"DT_FIM_{role_upper}"].replace("", pd.NA), errors="coerce"
    )
    return frame[["cnpj_fundo", "role_name", "evidence_start", "evidence_end"]]


def build_role_historical_coverage(
    vehicle: pd.DataFrame,
    r160: pd.DataFrame,
    history_zip: Path,
    current_month: str,
) -> pd.DataFrame:
    entity_map = vehicle[["cnpj", "cnpj_fundo"]].copy()
    entity_map["cnpj"] = entity_map["cnpj"].map(digits)
    entity_map["cnpj_fundo"] = entity_map["cnpj_fundo"].map(digits)
    entity_map = entity_map.drop_duplicates("cnpj").set_index("cnpj")["cnpj_fundo"]

    offer_roles = r160.copy()
    offer_roles["data_registro"] = pd.to_datetime(
        offer_roles["Data_Registro"], errors="coerce"
    )
    offer_roles["cnpj_fundo"] = offer_roles["CNPJ_Emissor"].map(digits).map(entity_map)
    offer_roles["cnpj_fundo"] = offer_roles["cnpj_fundo"].fillna(
        offer_roles["CNPJ_Emissor"].map(digits)
    )

    rows = []
    periods = ["2023-12", "2024-12", "2025-12", current_month]
    role_columns = {
        "administrador": ("admin_nome", "Administrador"),
        "gestor": ("gestor_nome", "Gestor"),
        "custodiante": ("custodiante_nome", "Custodiante"),
    }
    for competence in periods:
        month = vehicle.loc[vehicle["competencia"].eq(competence)].copy()
        if month.empty:
            continue
        month["cnpj_fundo"] = month["cnpj_fundo"].map(digits)
        as_of = pd.Period(competence, freq="M").end_time.normalize()
        total_pl = float(month["pl"].sum())
        total_funds = int(month["cnpj_fundo"].nunique())
        for role, (current_column, offer_column) in role_columns.items():
            if role == "administrador" or competence == current_month:
                known = month[current_column].fillna("").astype(str).str.strip().ne("")
                confidence = pd.Series("baixa", index=month.index)
                confidence.loc[known] = "alta"
                source = (
                    "informe_mensal_cvm"
                    if role == "administrador"
                    else "cadastro_atual"
                )
            else:
                confidence = pd.Series("baixa", index=month.index)
                source = pd.Series("cadastro_atual_retroagido", index=month.index)

                dated_offers = offer_roles.loc[
                    offer_roles["data_registro"].le(as_of)
                    & offer_roles[offer_column].fillna("").astype(str).str.strip().ne("")
                ].copy()
                if not dated_offers.empty:
                    dated_offers = dated_offers.sort_values("data_registro").drop_duplicates(
                        "cnpj_fundo", keep="last"
                    )
                    matched = month["cnpj_fundo"].isin(dated_offers["cnpj_fundo"])
                    confidence.loc[matched] = "media-alta"
                    source.loc[matched] = "oferta_publica_cvm_dated"

                history = load_cadastro_history(history_zip, role)
                active = history.loc[
                    history["evidence_start"].le(as_of)
                    & (history["evidence_end"].isna() | history["evidence_end"].ge(as_of))
                    & history["role_name"].ne("")
                ].copy()
                if not active.empty:
                    matched = month["cnpj_fundo"].isin(active["cnpj_fundo"])
                    confidence.loc[matched] = "alta"
                    source.loc[matched] = "cad_fi_hist_active"

            high = confidence.eq("alta")
            dated = confidence.isin(["alta", "media-alta"])
            rows.append(
                {
                    "competencia": competence,
                    "role": role,
                    "pl_total_brl": total_pl,
                    "fundos_total": total_funds,
                    "pl_cobertura_alta": float(month.loc[high, "pl"].sum() / total_pl),
                    "pl_cobertura_datada": float(month.loc[dated, "pl"].sum() / total_pl),
                    "fundos_cobertura_datada": float(
                        month.loc[dated, "cnpj_fundo"].nunique() / total_funds
                    ),
                    "fonte_principal": (
                        source if isinstance(source, str) else "cadastro histórico + ofertas datadas"
                    ),
                    "regra_publicacao": (
                        "PUBLICÁVEL"
                        if role == "administrador" or competence == current_month
                        else "NÃO PUBLICAR DELTA" if float(month.loc[dated, "pl"].sum() / total_pl) < 0.8 else "PUBLICÁVEL"
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_current_role_rankings(role_delta: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for role in ("administrador", "gestor", "custodiante"):
        frame = role_current_rows(role_delta, role).copy()
        frame["rank_pl"] = frame["pl_brl_current"].rank(
            method="min", ascending=False
        ).astype(int)
        frame["rank_fundos"] = frame["funds_current"].rank(
            method="min", ascending=False
        ).astype(int)
        frame["pl_bi"] = frame["pl_brl_current"] / 1e9
        frame["share_pct"] = 100 * frame["share_current"]
        rows.append(
            frame[
                [
                    "role",
                    "participant",
                    "pl_brl_current",
                    "pl_bi",
                    "share_current",
                    "share_pct",
                    "funds_current",
                    "rank_pl",
                    "rank_fundos",
                    "competencia_current",
                ]
            ]
        )
    return pd.concat(rows, ignore_index=True)


def build_administrator_type_rankings(vehicle: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for competence in ("2023-12", "2024-12", "2025-12"):
        frame = vehicle.loc[
            vehicle["competencia"].eq(competence)
            & ~vehicle["is_fic_fidc"].fillna(False)
            & vehicle["pl"].gt(0)
        ].copy()
        frame["classe_analitica"] = classify_anbima_macro(frame)
        frame["participant"] = frame["admin_nome"].map(participant_group)
        grouped = frame.groupby(["classe_analitica", "participant"], dropna=False).agg(
            pl_brl=("pl", "sum"),
            fundos=("cnpj_fundo", "nunique"),
        )
        type_totals = frame.groupby("classe_analitica")["pl"].sum()
        grouped["share_tipo"] = grouped.index.get_level_values(0).map(type_totals)
        grouped["share_tipo"] = grouped["pl_brl"] / grouped["share_tipo"]
        grouped["rank_tipo"] = grouped.groupby(level=0)["pl_brl"].rank(
            method="min", ascending=False
        ).astype(int)
        grouped = grouped.reset_index()
        grouped.insert(0, "competencia", competence)
        rows.append(grouped)
    return pd.concat(rows, ignore_index=True)


def build_administrator_type_rank_delta(rankings: pd.DataFrame) -> pd.DataFrame:
    official = rankings.loc[
        rankings["classe_analitica"].isin(
            [
                "Agro, Indústria e Comércio",
                "Financeiro",
                "Fomento Mercantil",
                "Outros",
            ]
        )
    ].copy()
    rows = []
    for (category, participant), group in official.groupby(
        ["classe_analitica", "participant"], dropna=False
    ):
        by_period = group.set_index("competencia")
        row = {
            "classe_analitica": category,
            "participant": participant,
        }
        for competence in ("2023-12", "2024-12", "2025-12"):
            suffix = competence[:4]
            if competence in by_period.index:
                current = by_period.loc[competence]
                row[f"rank_{suffix}"] = int(current["rank_tipo"])
                row[f"share_{suffix}"] = float(current["share_tipo"])
                row[f"pl_brl_{suffix}"] = float(current["pl_brl"])
                row[f"fundos_{suffix}"] = int(current["fundos"])
            else:
                row[f"rank_{suffix}"] = pd.NA
                row[f"share_{suffix}"] = 0.0
                row[f"pl_brl_{suffix}"] = 0.0
                row[f"fundos_{suffix}"] = 0
        rank_2023 = row["rank_2023"]
        rank_2025 = row["rank_2025"]
        row["delta_posicoes_2023_2025"] = (
            int(rank_2023) - int(rank_2025)
            if not pd.isna(rank_2023) and not pd.isna(rank_2025)
            else pd.NA
        )
        rows.append(row)
    result = pd.DataFrame(rows)
    return result.sort_values(
        ["classe_analitica", "rank_2025", "pl_brl_2025"],
        ascending=[True, True, False],
        na_position="last",
    )


def build() -> None:
    args = parse_args()
    data_dir = args.data_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    vehicle = read_csv(data_dir / "vehicle_monthly.csv.gz", low_memory=False)
    snapshot = read_csv(data_dir / "industry_fund_snapshot.csv.gz", low_memory=False)
    industry_monthly = read_csv(data_dir / "industry_monthly.csv")
    role_delta = read_csv(data_dir / "role_market_share_delta.csv")
    offer_delta = read_csv(data_dir / "offer_role_share_delta.csv")
    funnel = read_csv(data_dir / "document_universe_funnel.csv")
    cotista_types = read_csv(data_dir / "cotistas_tipo_monthly.csv")
    offers_zip = ensure_cvm_offers_zip(
        args.cvm_offers_zip, refresh=args.refresh_cvm_offers
    )
    r160 = read_cvm_r160(offers_zip)

    snapshot_months = sorted(snapshot["competencia"].dropna().astype(str).unique())
    if not snapshot_months:
        raise ValueError("industry_fund_snapshot has no competence")
    current_month = snapshot_months[-1]
    current_year = int(current_month[:4])
    previous_month = f"{current_year - 1}-{current_month[5:7]}"

    monthly_index = industry_monthly.set_index("competencia")
    for required_month in (current_month, previous_month):
        if required_month not in monthly_index.index:
            raise ValueError(f"missing complete monthly aggregate: {required_month}")

    annual_months = [
        f"{year}-12" for year in range(args.start_year, current_year) if f"{year}-12" in set(vehicle["competencia"])
    ]
    annual_months.append(current_month)

    annual_rows: list[dict] = []
    mix_rows: list[dict] = []
    for competence in annual_months:
        rows = vehicle.loc[
            vehicle["competencia"].eq(competence)
            & ~vehicle["is_fic_fidc"].fillna(False)
            & vehicle["pl"].gt(0)
        ].copy()
        if rows.empty:
            continue
        rows["anbima_macro"] = classify_anbima_macro(rows)
        total_pl = float(rows["pl"].sum())
        grouped = rows.groupby("anbima_macro", dropna=False)["pl"].sum()
        unclassified_pl = float(grouped.get("Sem evidência suficiente", 0.0))
        payment_unknown_pl = float(
            grouped.get("Meios de pagamento | classe não determinada", 0.0)
        )
        annual_rows.append(
            {
                "competencia": competence,
                "rotulo": competence[:4] if competence.endswith("-12") else f"{competence[:4]} YTD",
                "pl_ex_fic_brl": total_pl,
                "pl_ex_fic_bi": total_pl / 1e9,
                "veiculos": int(len(rows)),
                "fundos": int(rows["cnpj_fundo"].nunique()),
                "pl_classificado_share": 1
                - (unclassified_pl + payment_unknown_pl) / total_pl,
                "pl_meios_pagamento_indeterminado_share": payment_unknown_pl
                / total_pl,
                "pl_sem_evidencia_share": unclassified_pl / total_pl,
            }
        )
        for category in ANBIMA_CLASS_ORDER:
            pl_brl = float(grouped.get(category, 0.0))
            mix_rows.append(
                {
                    "competencia": competence,
                    "rotulo": competence[:4] if competence.endswith("-12") else f"{competence[:4]} YTD",
                    "classe_anbima_macro": category,
                    "pl_brl": pl_brl,
                    "share": pl_brl / total_pl,
                    "share_pct": 100 * pl_brl / total_pl,
                    "metodologia": (
                        "macroclasse ANBIMA inferida do segmento dominante de direitos "
                        "creditórios no informe mensal CVM; FIC-FIDC e PL<=0 excluídos"
                    ),
                }
            )

    annual = pd.DataFrame(annual_rows)
    anbima_mix = pd.DataFrame(mix_rows)
    anbima_mix["rank_pl"] = anbima_mix.groupby("competencia")["pl_brl"].rank(
        method="min", ascending=False
    ).astype(int)
    rank_2023 = anbima_mix.loc[
        anbima_mix["competencia"].eq("2023-12"),
        ["classe_anbima_macro", "rank_pl"],
    ].set_index("classe_anbima_macro")["rank_pl"]
    rank_2025 = anbima_mix.loc[
        anbima_mix["competencia"].eq("2025-12"),
        ["classe_anbima_macro", "rank_pl"],
    ].set_index("classe_anbima_macro")["rank_pl"]
    anbima_mix["rank_delta_2023_2025"] = anbima_mix["classe_anbima_macro"].map(
        rank_2023 - rank_2025
    )
    annual.to_csv(output_dir / "pl_ex_fic_yearly.csv", index=False)
    anbima_mix.to_csv(output_dir / "anbima_macro_mix_yearly.csv", index=False)
    pd.DataFrame(ANBIMA_CLASS_DEFINITIONS).to_csv(
        output_dir / "anbima_class_definitions.csv", index=False
    )
    pd.DataFrame(ANBIMA_PUBLIC_ISSUANCE).to_csv(
        output_dir / "anbima_public_issuance_yearly.csv", index=False
    )

    current_snapshot = snapshot.loc[
        snapshot["competencia"].astype(str).eq(current_month)
        & ~snapshot["is_fic_fidc"].fillna(False)
        & snapshot["pl"].gt(0)
    ].copy()
    current_snapshot["cotistas"] = pd.to_numeric(current_snapshot["cotistas"], errors="coerce").fillna(0)
    bucket_specs = [
        ("1", current_snapshot["cotistas"].eq(1)),
        ("2", current_snapshot["cotistas"].eq(2)),
        ("3 a 5", current_snapshot["cotistas"].between(3, 5)),
        ("6 a 10", current_snapshot["cotistas"].between(6, 10)),
        ("11 a 50", current_snapshot["cotistas"].between(11, 50)),
        ("> 50", current_snapshot["cotistas"].gt(50)),
        ("Sem cotista positivo", current_snapshot["cotistas"].le(0)),
    ]
    histogram_rows = []
    for label, mask in bucket_specs:
        histogram_rows.append(
            {
                "bucket": label,
                "fundos": int(mask.sum()),
                "fund_share": float(mask.mean()),
                "pl_brl": float(current_snapshot.loc[mask, "pl"].sum()),
                "pl_share": float(current_snapshot.loc[mask, "pl"].sum() / current_snapshot["pl"].sum()),
            }
        )
    cotista_histogram = pd.DataFrame(histogram_rows)
    cotista_histogram.to_csv(output_dir / "cotista_histogram_full_universe.csv", index=False)

    current_accounts = cotista_types.loc[cotista_types["competencia"].eq(current_month)].copy()
    current_accounts["share_accounts"] = current_accounts["n_cotistas"] / current_accounts["n_cotistas"].sum()
    current_accounts["publication_status"] = "supporting_only_not_unique_investors_no_value_split"
    current_accounts.to_csv(output_dir / "cotista_account_types_supporting_only.csv", index=False)

    for role in ("administrador", "gestor", "custodiante"):
        role_current_rows(role_delta, role).to_csv(
            output_dir / f"{role}_current_share.csv", index=False
        )

    current_role_rankings = build_current_role_rankings(role_delta)
    current_role_rankings.to_csv(
        output_dir / "role_current_rankings_pl_and_funds.csv", index=False
    )
    administrator_type_rankings = build_administrator_type_rankings(vehicle)
    administrator_type_rankings.to_csv(
        output_dir / "administrator_type_rankings_2023_2025.csv", index=False
    )
    administrator_type_rank_delta = build_administrator_type_rank_delta(
        administrator_type_rankings
    )
    administrator_type_rank_delta.to_csv(
        output_dir / "administrator_type_rank_delta_2023_2025.csv", index=False
    )

    (
        offer_annual,
        offer_role_annual,
        offer_structure,
        offer_combinations,
    ) = build_offer_evidence(r160)
    offer_annual.to_csv(
        output_dir / "cvm_r160_closed_registered_annual.csv", index=False
    )
    offer_role_annual.to_csv(
        output_dir / "cvm_r160_offer_role_share_annual.csv", index=False
    )
    offer_structure.to_csv(
        output_dir / "cvm_r160_offer_structure_patterns.csv", index=False
    )
    offer_combinations.to_csv(
        output_dir / "cvm_r160_offer_top_combinations_2025.csv", index=False
    )
    role_historical_coverage = build_role_historical_coverage(
        vehicle,
        r160,
        args.cadastro_history_zip,
        current_month,
    )
    role_historical_coverage.to_csv(
        output_dir / "role_historical_coverage_2023_2026.csv", index=False
    )

    admin_delta = role_current_rows(role_delta, "administrador")
    admin_delta.to_csv(output_dir / "administrador_share_delta.csv", index=False)
    offer_admin = offer_delta.loc[offer_delta["role"].eq("administrador")].copy()
    offer_admin = offer_admin.sort_values("volume_share_current", ascending=False)
    offer_admin.to_csv(output_dir / "administrador_primary_offer_share.csv", index=False)
    funnel.to_csv(output_dir / "document_evidence_funnel.csv", index=False)

    def participant_row(frame: pd.DataFrame, name: str) -> pd.Series:
        match = frame.loc[frame["participant"].eq(name)]
        if match.empty:
            raise ValueError(f"participant not found: {name}")
        return match.iloc[0]

    admin_itau = participant_row(admin_delta, "ITAU/INTRAG")
    offer_itau = participant_row(offer_admin, "ITAU/INTRAG")
    offer_qi = participant_row(offer_admin, "QI TECH + SINGULARE")
    offer_btg = participant_row(offer_admin, "BTG PACTUAL")
    offer_oliveira = participant_row(offer_admin, "OLIVEIRA TRUST")

    gross_pl = float(monthly_index.loc[current_month, "pl_total"])
    ex_fic_reported_net_pl = float(
        monthly_index.loc[current_month, "pl_total"]
        - monthly_index.loc[current_month, "pl_fic_fidc"]
    )
    cotistas_positive = current_snapshot["cotistas"].gt(0)
    up_to_five = current_snapshot["cotistas"].between(1, 5)
    current_mix = anbima_mix.loc[anbima_mix["competencia"].eq(current_month)]
    unclassified_share = float(
        current_mix.loc[
            current_mix["classe_anbima_macro"].eq("Sem evidência suficiente"), "share"
        ].iloc[0]
    )
    payment_unknown_share = float(
        current_mix.loc[
            current_mix["classe_anbima_macro"].eq(
                "Meios de pagamento | classe não determinada"
            ),
            "share",
        ].iloc[0]
    )
    annual_index = annual.set_index("competencia")
    ex_fic_pl = float(annual_index.loc[current_month, "pl_ex_fic_brl"])
    pl_2018 = float(annual_index.loc["2018-12", "pl_ex_fic_brl"])
    pl_2023 = float(annual_index.loc["2023-12", "pl_ex_fic_brl"])
    pl_2024 = float(annual_index.loc["2024-12", "pl_ex_fic_brl"])
    pl_2025 = float(annual_index.loc["2025-12", "pl_ex_fic_brl"])
    current_card = current_snapshot.loc[
        current_snapshot["segmento_principal"].eq("Cartao de credito")
    ].copy()
    card_sample_cnpjs = {digits(row["cnpj"]) for row in CARD_SAMPLE_AUDIT}
    current_card["cnpj_fundo_normalizado"] = current_card["cnpj_fundo"].map(digits)
    card_total_pl = float(current_card["pl"].sum())
    card_sample_pl = float(
        current_card.loc[
            current_card["cnpj_fundo_normalizado"].isin(card_sample_cnpjs), "pl"
        ].sum()
    )
    card_pl_by_cnpj = current_card.groupby("cnpj_fundo_normalizado")["pl"].sum()
    card_audit = pd.DataFrame(CARD_SAMPLE_AUDIT)
    card_audit["cnpj_normalizado"] = card_audit["cnpj"].map(digits)
    card_audit["pl_atual_brl"] = card_audit["cnpj_normalizado"].map(
        card_pl_by_cnpj
    ).fillna(0.0)
    card_audit["share_pl_segmento_cartao"] = (
        card_audit["pl_atual_brl"] / card_total_pl if card_total_pl else 0.0
    )
    card_audit.to_csv(
        output_dir / "card_receivables_classification_audit.csv", index=False
    )
    explicit_card = card_audit["status"].eq("EXPLÍCITA")
    aic_card = card_audit["classe_declarada"].str.startswith(
        "Agro, Indústria e Comércio"
    )
    other_card = card_audit["classe_declarada"].str.startswith("Outros")
    structure_2025 = offer_structure.loc[offer_structure["ano"].eq(2025)].set_index(
        "padrao"
    )
    cvm_offer_2025 = offer_annual.loc[offer_annual["ano"].eq(2025)].iloc[0]
    role_coverage_index = role_historical_coverage.set_index(["role", "competencia"])
    manager_current_coverage = role_coverage_index.loc[("gestor", current_month)]
    custodian_current_coverage = role_coverage_index.loc[("custodiante", current_month)]
    manager_2025_coverage = role_coverage_index.loc[("gestor", "2025-12")]
    custodian_2025_coverage = role_coverage_index.loc[("custodiante", "2025-12")]

    metrics = {
        "current_month": current_month,
        "previous_month": previous_month,
        "gross_pl_brl": gross_pl,
        "gross_pl_bi": gross_pl / 1e9,
        "ex_fic_pl_brl": ex_fic_pl,
        "ex_fic_pl_bi": ex_fic_pl / 1e9,
        "ex_fic_reported_net_pl_brl": ex_fic_reported_net_pl,
        "current_universe_funds": int(
            funnel.loc[funnel["stage"].eq("current_cvm_universe"), "current_funds_matched"].iloc[0]
        ),
        "classification_share": 1 - unclassified_share - payment_unknown_share,
        "unclassified_share": unclassified_share,
        "payment_unknown_share": payment_unknown_share,
        "pl_cagr_2018_2023": (pl_2023 / pl_2018) ** (1 / 5) - 1,
        "pl_growth_2024": pl_2024 / pl_2023 - 1,
        "pl_growth_2025": pl_2025 / pl_2024 - 1,
        "card_sample_pl_share": card_sample_pl / card_total_pl if card_total_pl else 0.0,
        "card_total_pl_brl": card_total_pl,
        "card_sample_pl_brl": card_sample_pl,
        "card_explicit_sample_pl_share": float(
            card_audit.loc[explicit_card, "pl_atual_brl"].sum() / card_total_pl
        ),
        "card_unresolved_sample_pl_share": float(
            card_audit.loc[~explicit_card, "pl_atual_brl"].sum() / card_total_pl
        ),
        "card_aic_explicit_pl_share": float(
            card_audit.loc[explicit_card & aic_card, "pl_atual_brl"].sum()
            / card_total_pl
        ),
        "card_other_explicit_pl_share": float(
            card_audit.loc[explicit_card & other_card, "pl_atual_brl"].sum()
            / card_total_pl
        ),
        "cvm_closed_registered_2025_brl": float(cvm_offer_2025["volume_registrado_brl"]),
        "cvm_closed_registered_2025_offers": int(
            cvm_offer_2025["requerimentos_encerrados"]
        ),
        "cvm_offer_2025_admin_volume_coverage": float(
            cvm_offer_2025["administrador_cobertura_volume"]
        ),
        "cvm_offer_2025_manager_volume_coverage": float(
            cvm_offer_2025["gestor_cobertura_volume"]
        ),
        "cvm_offer_2025_custodian_volume_coverage": float(
            cvm_offer_2025["custodiante_cobertura_volume"]
        ),
        "manager_current_pl_coverage": float(
            manager_current_coverage["pl_cobertura_datada"]
        ),
        "custodian_current_pl_coverage": float(
            custodian_current_coverage["pl_cobertura_datada"]
        ),
        "manager_2025_pl_coverage": float(
            manager_2025_coverage["pl_cobertura_datada"]
        ),
        "custodian_2025_pl_coverage": float(
            custodian_2025_coverage["pl_cobertura_datada"]
        ),
        "manager_2025_high_pl_coverage": float(
            manager_2025_coverage["pl_cobertura_alta"]
        ),
        "custodian_2025_high_pl_coverage": float(
            custodian_2025_coverage["pl_cobertura_alta"]
        ),
        "offer_2025_admin_custodian_same_volume_share": float(
            structure_2025.loc[
                "administrador_igual_custodiante", "share_volume_registrado"
            ]
        ),
        "offer_2025_all_same_volume_share": float(
            structure_2025.loc["todos_iguais", "share_volume_registrado"]
        ),
        "offer_2025_all_same_offer_share": float(
            structure_2025.loc["todos_iguais", "share_ofertas"]
        ),
        "itau_admin_share": float(admin_itau["share_current"]),
        "itau_admin_delta_pp": float(admin_itau["delta_share_pp"]),
        "itau_admin_rank": int(admin_itau["rank_current"]),
        "itau_admin_previous_rank": int(admin_itau["rank_previous"]),
        "itau_admin_pl_brl": float(admin_itau["pl_brl_current"]),
        "itau_admin_pl_gap_to_5pct_brl": 0.05 * gross_pl - float(admin_itau["pl_brl_current"]),
        "itau_offer_share": float(offer_itau["volume_share_current"]),
        "itau_offer_delta_pp": float(offer_itau["delta_volume_share_pp"]),
        "qi_offer_share": float(offer_qi["volume_share_current"]),
        "qi_offer_count": int(offer_qi["offers_current"]),
        "btg_offer_share": float(offer_btg["volume_share_current"]),
        "btg_offer_delta_pp": float(offer_btg["delta_volume_share_pp"]),
        "oliveira_offer_share": float(offer_oliveira["volume_share_current"]),
        "cotista_funds": int(len(current_snapshot)),
        "cotista_positive_funds": int(cotistas_positive.sum()),
        "cotista_positive_pl_share": float(
            current_snapshot.loc[cotistas_positive, "pl"].sum() / current_snapshot["pl"].sum()
        ),
        "cotistas_median": float(current_snapshot.loc[cotistas_positive, "cotistas"].median()),
        "funds_up_to_five_share": float(up_to_five.mean()),
        "pl_up_to_five_share": float(
            current_snapshot.loc[up_to_five, "pl"].sum() / current_snapshot["pl"].sum()
        ),
    }

    publication_gate = pd.DataFrame(
        [
            {
                "tema": "PL e composição por macroclasse ANBIMA",
                "cobertura": (
                    f"100% do PL ex-FIC; {metrics['classification_share']:.1%} em classe "
                    f"oficial, {metrics['payment_unknown_share']:.1%} em meios de pagamento "
                    f"indeterminado e {metrics['unclassified_share']:.1%} sem evidência"
                ),
                "decisao": "PUBLICAR",
                "regra": "as duas faixas não classificadas permanecem explícitas",
            },
            {
                "tema": "Cartão de lojista",
                "cobertura": (
                    f"5 fundos, {metrics['card_sample_pl_share']:.1%} do PL do segmento; "
                    f"só {metrics['card_explicit_sample_pl_share']:.1%} do PL do segmento tem "
                    f"classe explícita e {metrics['card_unresolved_sample_pl_share']:.1%} "
                    "está no TAPSO indeterminado"
                ),
                "decisao": "PUBLICAR REGRA",
                "regra": "usar classe declarada no regulamento; não classificar cartão por inferência",
            },
            {
                "tema": "Administração: share e delta",
                "cobertura": "100% do PL; papel observado no informe mensal",
                "decisao": "PUBLICAR",
                "regra": "janela comparável de 12 meses",
            },
            {
                "tema": "Gestão e custódia",
                "cobertura": (
                    f"foto atual: gestor {metrics['manager_current_pl_coverage']:.1%} e custodiante "
                    f"{metrics['custodian_current_pl_coverage']:.1%} do PL; dez/25 com cadastro "
                    f"histórico ativo: {metrics['manager_2025_high_pl_coverage']:.1%} e "
                    f"{metrics['custodian_2025_high_pl_coverage']:.1%}; teto com ofertas datadas: "
                    f"{metrics['manager_2025_pl_coverage']:.1%} e "
                    f"{metrics['custodian_2025_pl_coverage']:.1%}"
                ),
                "decisao": "PUBLICAR FOTO",
                "regra": "deltas históricos excluídos abaixo do corte mínimo de 80% do PL",
            },
            {
                "tema": "Ofertas: volume anual",
                "cobertura": "ANBIMA: captação anual publicada para 2023, 2024 e 2025",
                "decisao": "PUBLICAR COM VINTAGE",
                "regra": "não combinar revisões posteriores sem identificar a data da publicação",
            },
            {
                "tema": "Ofertas: share por prestador",
                "cobertura": (
                    f"CVM RCVM 160, 2025: {metrics['cvm_closed_registered_2025_offers']:,} "
                    f"requerimentos encerrados e R$ {metrics['cvm_closed_registered_2025_brl']/1e9:.1f} bi "
                    "de teto registrado"
                ),
                "decisao": "PUBLICAR COMO PROXY",
                "regra": "share do montante máximo registrado; não equivale à colocação efetiva",
            },
            {
                "tema": "Quantidade de cotistas",
                "cobertura": "100% dos fundos ex-FIC; 99,9% do PL com valor positivo",
                "decisao": "PUBLICAR HISTOGRAMA",
                "regra": "contas por classe/série, não CPF/CNPJ único",
            },
            {
                "tema": "Investidores nominais, cedentes, sacados e secundário",
                "cobertura": "sem censo documental, beneficiário final ou negócio a negócio",
                "decisao": "EXCLUIR",
                "regra": "nenhum ranking ou turnover no material executivo",
            },
        ]
    )
    publication_gate.to_csv(output_dir / "publication_gate.csv", index=False)

    source_rows = [
        {
            "tema": "PL, segmentos, administradores e cotistas",
            "fonte": "CVM - Informe Mensal de FIDC",
            "url": "https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal",
            "arquivo_local": "vehicle_monthly.csv.gz | industry_monthly.csv | industry_fund_snapshot.csv.gz",
            "uso": "universo mensal, PL, recebível dominante, administração e número de cotistas",
        },
        {
            "tema": "Gestão e custódia atuais",
            "fonte": "CVM - Cadastro de Fundos",
            "url": "https://dados.cvm.gov.br/dataset/fi-cad",
            "arquivo_local": "role_market_share_delta.csv",
            "uso": "foto cadastral atual por gestor e custodiante",
        },
        {
            "tema": "Histórico datado de gestão e custódia",
            "fonte": "CVM - Cadastro histórico de Fundos",
            "url": "https://dados.cvm.gov.br/dataset/fi-cad",
            "arquivo_local": "cad_fi_hist.zip | role_historical_coverage_2023_2026.csv",
            "uso": "medir cobertura histórica e bloquear deltas abaixo de 80% do PL",
        },
        {
            "tema": "Ofertas e prestadores",
            "fonte": "CVM - Ofertas Públicas de Distribuição",
            "url": "https://dados.cvm.gov.br/dataset/oferta-distrib",
            "arquivo_local": "oferta_resolucao_160.csv | cvm_r160_offer_role_share_annual.csv",
            "uso": "ofertas primárias encerradas, teto registrado e papéis declarados; atualização diária",
        },
        {
            "tema": "Classes de FIDC",
            "fonte": "ANBIMA - Diretriz de Classificação do FIDC nº 09",
            "url": "https://www.anbima.com.br/data/files/85/40/8F/2D/79E386106416A38678A80AC2/Diretrizes_e_deliberacoes_do_Codigo_de_Administracao_de_Recursos_de_terceiros.pdf",
            "arquivo_local": "anbima_class_definitions.csv",
            "uso": "denominações e focos oficiais; macro-mapeamento analítico dos informes CVM",
        },
        {
            "tema": "Cobertura documental",
            "fonte": "Documentos públicos CVM/Fundos.NET curados localmente",
            "url": "https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM",
            "arquivo_local": "document_universe_funnel.csv",
            "uso": "medir cobertura e impedir publicação de rankings não censitários",
        },
        {
            "tema": "Referência de conteúdo",
            "fonte": "Industria_FIDC_2026053.pptx - Clodo Couto",
            "url": "local",
            "arquivo_local": "/Users/matheusjprates/Downloads/Industria_FIDC_2026053.pptx",
            "uso": "taxonomia, gráfico 100% empilhado e encadeamento; números reprocessados",
        },
    ]
    source_rows.extend(
        {
            "tema": f"Captação pública de FIDC {row['ano']}",
            "fonte": row["fonte"],
            "url": row["url"],
            "arquivo_local": "anbima_public_issuance_yearly.csv",
            "uso": f"volume anual publicado em {row['publicado_em']}; vintage preservado",
        }
        for row in ANBIMA_PUBLIC_ISSUANCE
    )
    source_rows.extend(
        {
            "tema": f"Classificação de cartão - {row['fundo']}",
            "fonte": f"Fundos.NET - {row['documento']}",
            "url": row["url"],
            "arquivo_local": "card_receivables_classification_audit.csv",
            "uso": f"classe {row['status'].lower()}: {row['classe_declarada']}",
        }
        for row in CARD_SAMPLE_AUDIT
    )
    source_ledger = pd.DataFrame(source_rows)
    source_ledger.to_csv(output_dir / "source_ledger.csv", index=False)

    clodo_log = pd.DataFrame(
        [
            {
                "item": "Quatro denominações ANBIMA",
                "slide_clodo": 5,
                "tratamento": "ADOTADO E VERIFICADO",
                "motivo": "terminologia confirmada na Diretriz ANBIMA nº 09",
            },
            {
                "item": "Gráfico 100% empilhado por ano",
                "slide_clodo": 4,
                "tratamento": "ADOTADO COM REPROCESSAMENTO",
                "motivo": (
                    "universo CVM ex-FIC integral; quatro classes oficiais, meios de pagamento "
                    "indeterminado e faixa sem evidência"
                ),
            },
            {
                "item": "Cartão de lojista dentro de AIC",
                "slide_clodo": 5,
                "tratamento": "CORRIGIDO",
                "motivo": (
                    "BELA, CloudWalk PI e Akira II declaram AIC; PagSeguro declara Outros; "
                    "TAPSO não tem classe inequívoca no documento consultado"
                ),
            },
            {
                "item": "Série histórica de PL",
                "slide_clodo": 3,
                "tratamento": "RECALCULADO",
                "motivo": "o valor de 2023 do deck de referência não reproduz o universo CVM ex-FIC atual",
            },
            {
                "item": "Histograma de fundos acima de R$ 200 milhões",
                "slide_clodo": 15,
                "tratamento": "SUBSTITUÍDO",
                "motivo": "histograma agora cobre todo o universo ex-FIC, sem corte por PL",
            },
            {
                "item": "Mix de investidores de junho de 2026",
                "slide_clodo": 16,
                "tratamento": "EXCLUÍDO",
                "motivo": "competência parcial e contas não equivalem a investidores únicos ou valor investido",
            },
            {
                "item": "Deltas históricos de gestores e custodiantes",
                "slide_clodo": "7 e 9",
                "tratamento": "EXCLUÍDO",
                "motivo": (
                    f"em dez/25, cadastro histórico ativo cobre só "
                    f"{metrics['manager_2025_high_pl_coverage']:.1%} do PL em gestão e "
                    f"{metrics['custodian_2025_high_pl_coverage']:.1%} em custódia"
                ),
            },
            {
                "item": "Cedentes e sacados nominais",
                "slide_clodo": 14,
                "tratamento": "EXCLUÍDO",
                "motivo": "curadoria direcionada não permite ranking representativo da indústria",
            },
        ]
    )
    clodo_log.to_csv(output_dir / "clodo_content_adoption_log.csv", index=False)

    content = {
        "metrics": metrics,
        "annual_pl": as_records(annual),
        "anbima_mix": as_records(anbima_mix),
        "anbima_definitions": ANBIMA_CLASS_DEFINITIONS,
        "card_sample_audit": as_records(card_audit),
        "public_issuance": as_records(pd.DataFrame(ANBIMA_PUBLIC_ISSUANCE)),
        "cotista_histogram": as_records(cotista_histogram),
        "administrator_current": as_records(admin_delta.head(12)),
        "manager_current": as_records(role_current_rows(role_delta, "gestor").head(12)),
        "custodian_current": as_records(role_current_rows(role_delta, "custodiante").head(12)),
        "current_role_rankings": as_records(current_role_rankings),
        "administrator_type_rankings": as_records(administrator_type_rankings),
        "administrator_type_rank_delta": as_records(administrator_type_rank_delta),
        "administrator_offers": as_records(offer_admin.head(15)),
        "offer_annual": as_records(offer_annual),
        "offer_role_annual": as_records(offer_role_annual),
        "offer_structure": as_records(offer_structure),
        "offer_combinations": as_records(offer_combinations.head(30)),
        "role_historical_coverage": as_records(role_historical_coverage),
        "document_funnel": as_records(funnel),
        "publication_gate": as_records(publication_gate),
        "sources": as_records(source_ledger),
    }
    (output_dir / "deck_content.json").write_text(
        json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "current_month": current_month,
                "gross_pl_bi": round(metrics["gross_pl_bi"], 1),
                "ex_fic_pl_bi": round(metrics["ex_fic_pl_bi"], 1),
                "classification_share": round(metrics["classification_share"], 4),
                "payment_unknown_share": round(metrics["payment_unknown_share"], 4),
                "pl_cagr_2018_2023": round(metrics["pl_cagr_2018_2023"], 4),
                "pl_growth_2024": round(metrics["pl_growth_2024"], 4),
                "pl_growth_2025": round(metrics["pl_growth_2025"], 4),
                "card_sample_pl_share": round(metrics["card_sample_pl_share"], 4),
                "cvm_closed_registered_2025_bi": round(
                    metrics["cvm_closed_registered_2025_brl"] / 1e9, 1
                ),
                "cotista_funds": metrics["cotista_funds"],
                "funds_up_to_five_share": round(metrics["funds_up_to_five_share"], 4),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    build()
