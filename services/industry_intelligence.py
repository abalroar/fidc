from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timezone
import io
import re
import unicodedata
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


COMPLETE_VEHICLE_RATIO = 0.85
COMPLETE_PL_RATIO = 0.85
RELEVANT_TICKET_BRL = 300_000_000.0

EXCLUDED_OFFER_STATUSES = {
    "OFERTA REVOGADA",
    "OFERTA SUSPENSA",
    "REGISTRO CADUCADO",
}

PROVIDER_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Itaú", (r"\bITAU\b", r"\bINTRAG\b")),
    ("BTG Pactual", (r"\bBTG\b",)),
    ("QI Tech", (r"\bQI\s+(?:CORRETORA|DISTRIBUIDORA|GESTAO|CTVM)", r"\bQI\s+TECH\b")),
    ("Oliveira Trust", (r"\bOLIVEIRA\s+TRUST\b",)),
    ("Banco do Brasil", (r"\bBANCO\s+DO\s+BRASIL\b", r"\bBB\s+GESTAO\b")),
    ("Bradesco", (r"\bBRADESCO\b", r"\bBEM\s+DISTRIBUIDORA\b", r"\bBRAM\b")),
    ("Daycoval", (r"\bDAYCOVAL\b",)),
    ("Genial", (r"\bGENIAL\b",)),
    ("Vórtx", (r"\bVORTX\b",)),
    ("Singulare", (r"\bSINGULARE\b",)),
    ("REAG", (r"\bREAG\b",)),
    ("CBSF", (r"\bCBSF\b",)),
    ("BRL Trust", (r"\bBRL\s+TRUST\b",)),
    ("Banco BV", (r"\bBANCO\s+VOTORANTIM\b", r"\bBANCO\s+BV\b")),
    ("XP", (r"\bXP\s+INVEST", r"\bXP\s+VISTA\b")),
    ("Santander", (r"\bSANTANDER\b",)),
    ("Banco ABC", (r"\bABC\s+BRASIL\b",)),
    ("BNY Mellon", (r"\bBNY\s+MELLON\b",)),
    ("Finaxis", (r"\bFINAXIS\b",)),
    ("Limine Trust", (r"\bLIMINE\s+TRUST\b",)),
    ("Vert", (r"\bVERT\b",)),
    ("Hemera", (r"\bHEMERA\b",)),
    ("Banco Master", (r"\bMASTER\b",)),
    ("Banco Pine", (r"\bBANCO\s+PINE\b",)),
)

ORIGINATOR_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("CloudWalk", (r"\bCLOUDWALK\b",)),
    ("Stone", (r"\bSISTEMA\s+STONE\b", r"\bSTONE\b")),
    ("Banco BV", (r"\bFIDC\s+BV\s+AUTO\b", r"\bBV\s+AUTO\b", r"\bBANCO\s+(?:BV|VOTORANTIM)\b")),
    ("PagSeguro", (r"\bPAGSEGURO\b",)),
    ("Mercado Pago / Mercado Crédito", (r"\bMERCADO\s+(?:PAGO|CREDITO)\b",)),
    ("Banco Volkswagen", (r"\bBANCO\s+VOLKSWAGEN\b", r"\bDRIVER(?:\s+MASTER)?\s+BRASIL\b")),
    ("Banco Santander", (r"\bSANTANDER\s+AUTO\b",)),
    ("Agibank", (r"\bAGIBANK\b",)),
    ("Creditas", (r"\bCREDITAS\b",)),
    ("Cielo", (r"\bCIELO\b",)),
    ("Verdecard", (r"\bVERDECARD\b",)),
    ("MRV", (r"\bMRV\b",)),
    ("Bayer", (r"\bCITI[ -]?BAYER\b", r"\bBAYER\b")),
    ("BRB", (r"\bBRB\b", r"\bBANCO\s+DE\s+BRASILIA\b")),
    ("Sabemi", (r"\bSABEMI\b",)),
    ("XP Comercializadora de Energia", (r"\bAETOS\s+ENERGIA\b", r"\bXP\s+COMERCIALIZADORA\s+DE\s+ENERGIA\b")),
    ("D365", (r"\bD365\b",)),
    ("Sistema Petrobras", (r"\bSISTEMA\s+PETROBRAS\b",)),
    ("PicPay", (r"\bPICPAY\b",)),
    ("Banco Pine", (r"\bPINE\s+INSS\b", r"\bBANCO\s+PINE\b")),
    ("Solfácil", (r"\bSOLFACIL\b", r"\bSOL\s+AGORA\b")),
    ("Pravaler", (r"\bPRAVALER\b", r"\bCREDITO\s+UNIVERSITARIO\b")),
    ("iFood", (r"\bIFOOD\b",)),
    ("Asaas", (r"\bASAAS\b",)),
    ("ICred", (r"\bICRED\b",)),
    ("AgroGalaxy", (r"\bAGROGALAXY\b",)),
    ("Lavoro", (r"\bLAVORO\b",)),
    ("Minerva", (r"\bMINERVA\b",)),
    ("Stellantis", (r"\bSTELLANTIS\b",)),
    ("SumUp", (r"\bSUMUP\b",)),
    ("Banco PAN", (r"\bPAN\s+AUTO\b", r"\bBANCO\s+PAN\b")),
    ("Paraná Banco", (r"\bPARANA\s+BANCO\b",)),
    ("Banco BMG", (r"\bBANCO\s+BMG\b",)),
)

SEGMENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Meios de pagamento", (r"PAGAMENTO", r"CARTAO", r"ADQUIRENCIA", r"CREDENCIAD")),
    ("Consignado", (r"CONSIGNAD", r"INSS", r"FGTS", r"CREDITO\s+DO\s+TRABALHADOR")),
    ("Veículos", (r"VEICUL", r"AUTO\s+LOAN")),
    ("Crédito PF", (r"CREDITO\s+PESSOAL", r"EMPRESTIMO\s+PESSOAL", r"CCB")),
    ("Crédito PJ", (r"MIDDLE\s+MARKET", r"CORPORATIV", r"FORNECEDOR", r"DUPLICAT")),
    ("Agro", (r"AGRONEG", r"FIAGRO", r"CPR", r"CDCA")),
    ("Imobiliário", (r"IMOBILI", r"HIPOTEC")),
    ("Judicial / NPL", (r"PRECATOR", r"JUDICIAL", r"NAO\s*PADRONIZ", r"\bNPL\b")),
    ("Infra / energia", (r"ENERG", r"INFRA", r"SANEAMENTO")),
    ("FIC / alocador", (r"FUNDO\s+DE\s+INVESTIMENTO\s+EM\s+COTAS", r"\bFIC\b")),
)


def only_digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Z0-9]+", " ", text.upper())
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return "" if text.lower() in {"nan", "none", "nat", "n.a", "n.a>"} else text


def canonical_provider(value: object) -> str:
    original = clean_text(value)
    if not original:
        return "Não informado"
    normalized = normalize_text(original)
    for label, patterns in PROVIDER_RULES:
        if any(re.search(pattern, normalized) for pattern in patterns):
            return label
    short = re.sub(
        r"\b(S A|SA|LTDA|DTVM|CTVM|CCTVM|DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS|CORRETORA DE VALORES MOBILIARIOS)\b.*$",
        "",
        normalized,
    ).strip()
    return short.title() if short else original


def classify_segment(*values: object) -> str:
    text = normalize_text(" ".join(clean_text(value) for value in values))
    for label, patterns in SEGMENT_RULES:
        if any(re.search(pattern, text) for pattern in patterns):
            return label
    return "Multissetorial / não identificado"


def identify_originator(*values: object) -> tuple[str, str, str]:
    sources = [(f"campo_{index + 1}", clean_text(value)) for index, value in enumerate(values)]
    for source, original in sources:
        normalized = normalize_text(original)
        for label, patterns in ORIGINATOR_RULES:
            match = next((pattern for pattern in patterns if re.search(pattern, normalized)), None)
            if match:
                return label, source, f"{source}: {match}"
    return "Não identificado", "", ""


def parse_number(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    text = series.fillna("").astype(str).str.strip()
    comma_decimal = text.str.contains(",", regex=False)
    text.loc[comma_decimal] = text.loc[comma_decimal].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(text, errors="coerce")


def parse_date(series: pd.Series) -> pd.Series:
    iso = pd.to_datetime(series, errors="coerce", format="%Y-%m-%d")
    missing = iso.isna()
    if missing.any():
        iso.loc[missing] = pd.to_datetime(series.loc[missing], errors="coerce", dayfirst=True)
    return iso


def build_competence_status(
    industry: pd.DataFrame,
    audit: pd.DataFrame | None = None,
    *,
    generated_at_utc: str | None = None,
) -> pd.DataFrame:
    if industry is None or industry.empty:
        return pd.DataFrame()
    frame = industry.copy().sort_values("competencia").reset_index(drop=True)
    frame["n_veiculos"] = pd.to_numeric(frame["n_veiculos"], errors="coerce").fillna(0)
    frame["pl_total"] = pd.to_numeric(frame["pl_total"], errors="coerce").fillna(0)
    frame["previous_vehicles"] = frame["n_veiculos"].shift(1)
    frame["previous_pl_brl"] = frame["pl_total"].shift(1)
    frame["vehicle_ratio_vs_previous"] = frame["n_veiculos"].div(frame["previous_vehicles"].where(frame["previous_vehicles"] > 0))
    frame["pl_ratio_vs_previous"] = frame["pl_total"].div(frame["previous_pl_brl"].where(frame["previous_pl_brl"] > 0))
    frame["publication_status"] = "completa"
    frame["status_reason"] = "competência histórica consolidada"
    is_partial = (
        frame["vehicle_ratio_vs_previous"].lt(COMPLETE_VEHICLE_RATIO)
        | frame["pl_ratio_vs_previous"].lt(COMPLETE_PL_RATIO)
    )
    # Large historical jumps are possible; only the open tail can be provisional.
    if len(frame):
        tail_idx = frame.index[-1]
        if bool(is_partial.loc[tail_idx]):
            frame.loc[tail_idx, "publication_status"] = "preliminar"
            frame.loc[tail_idx, "status_reason"] = "carga parcial da CVM; não usar como fotografia consolidada"
    if audit is not None and not audit.empty:
        audit_cols = [
            column
            for column in ["competencia", "tab1_coverage", "tab2_coverage", "x1_coverage", "x2_coverage", "x4_coverage", "tab7_coverage"]
            if column in audit.columns
        ]
        frame = frame.merge(audit[audit_cols].drop_duplicates("competencia"), on="competencia", how="left")
    frame["generated_at_utc"] = generated_at_utc or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return frame[
        [
            "competencia",
            "publication_status",
            "status_reason",
            "n_veiculos",
            "pl_total",
            "previous_vehicles",
            "previous_pl_brl",
            "vehicle_ratio_vs_previous",
            "pl_ratio_vs_previous",
            *[column for column in frame.columns if column.endswith("_coverage")],
            "generated_at_utc",
        ]
    ]


def latest_complete_competence(status: pd.DataFrame, fallback: str = "") -> str:
    if status is None or status.empty or "publication_status" not in status:
        return fallback
    complete = status[status["publication_status"].eq("completa")]
    if complete.empty:
        return fallback
    return str(complete.sort_values("competencia").iloc[-1]["competencia"])


def merge_competence_rows(existing: pd.DataFrame, replacement: pd.DataFrame) -> pd.DataFrame:
    if existing is None or existing.empty:
        return replacement.copy()
    if replacement is None or replacement.empty:
        return existing.copy()
    keys = [column for column in ["competencia", "cnpj", "segmento", "nivel", "tipo_cotista", "admin_cnpj"] if column in existing.columns and column in replacement.columns]
    if not keys:
        raise ValueError("Não foi possível identificar a chave de atualização mensal.")
    replacement_keys = replacement[keys].astype(str).agg("|".join, axis=1)
    existing_keys = existing[keys].astype(str).agg("|".join, axis=1)
    output = pd.concat([existing.loc[~existing_keys.isin(set(replacement_keys))], replacement], ignore_index=True)
    return output.sort_values(keys).reset_index(drop=True)


def load_cvm_offers_zip(
    path: str | Path,
    *,
    start: str = "2024-01-01",
    as_of: date | pd.Timestamp | None = None,
) -> pd.DataFrame:
    path = Path(path)
    with ZipFile(path) as archive:
        r160 = pd.read_csv(
            archive.open("oferta_resolucao_160.csv"),
            sep=";",
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
            low_memory=False,
        )
        legacy = pd.read_csv(
            archive.open("oferta_distribuicao.csv"),
            sep=";",
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
            low_memory=False,
        )

    r160 = r160[r160["Valor_Mobiliario"].str.contains("FIDC", case=False, na=False)].copy()
    standardized = pd.DataFrame(
        {
            "source_dataset": "oferta_resolucao_160.csv",
            "offer_id": r160["Numero_Requerimento"].map(clean_text),
            "process_id": r160["Numero_Processo"].map(clean_text),
            "registration_date": parse_date(r160["Data_Registro"]),
            "closing_date": parse_date(r160["Data_Encerramento"]),
            "status": r160["Status_Requerimento"].map(clean_text),
            "security": r160["Valor_Mobiliario"].map(clean_text),
            "offer_type": r160["Tipo_Oferta"].map(clean_text),
            "initial_offer": r160["Oferta_inicial"].map(normalize_text).eq("S"),
            "issuer_cnpj": r160["CNPJ_Emissor"].map(only_digits),
            "issuer_name": r160["Nome_Emissor"].map(clean_text),
            "leader_cnpj": r160["CNPJ_Lider"].map(only_digits),
            "leader_name": r160["Nome_Lider"].map(clean_text),
            "registered_quantity": parse_number(r160["Qtde_Total_Registrada"]),
            "registered_volume_brl": parse_number(r160["Valor_Total_Registrado"]),
            "target_public": r160["Publico_alvo"].map(clean_text),
            "collateral_type": r160["Tipo_lastro"].map(clean_text),
            "target_assets": r160["Ativos_alvo"].map(clean_text),
            "collateral_description": r160["Descricao_lastro"].map(clean_text),
            "identified_debtors": r160["Identificacao_devedores_coobrigados"].map(clean_text),
            "distribution_regime": r160["Regime_distribuicao"].map(clean_text),
            "trading_market": r160["Mercado_negociacao"].map(clean_text),
            "administrator_name": r160["Administrador"].map(clean_text),
            "manager_name": r160["Gestor"].map(clean_text),
            "custodian_name": r160["Custodiante"].map(clean_text),
        }
    )
    for column in _investor_source_columns():
        standardized[column] = parse_number(r160[column]) if column in r160 else 0.0

    legacy = legacy[legacy["Tipo_Ativo"].str.contains("FIDC", case=False, na=False)].copy()
    if not legacy.empty:
        legacy_rows = pd.DataFrame(
            {
                "source_dataset": "oferta_distribuicao.csv",
                "offer_id": legacy["Numero_Processo"].map(clean_text) + " | " + legacy["Numero_Registro_Oferta"].map(clean_text),
                "process_id": legacy["Numero_Processo"].map(clean_text),
                "registration_date": parse_date(legacy["Data_Registro_Oferta"]),
                "closing_date": parse_date(legacy["Data_Encerramento_Oferta"]),
                "status": legacy["Modalidade_Registro"].map(clean_text),
                "security": legacy["Tipo_Ativo"].map(clean_text),
                "offer_type": legacy["Tipo_Oferta"].map(clean_text),
                "initial_offer": False,
                "issuer_cnpj": legacy["CNPJ_Emissor"].map(only_digits),
                "issuer_name": legacy["Nome_Emissor"].map(clean_text),
                "leader_cnpj": legacy["CNPJ_Lider"].map(only_digits),
                "leader_name": legacy["Nome_Lider"].map(clean_text),
                "registered_quantity": parse_number(legacy["Quantidade_Total"]),
                "registered_volume_brl": parse_number(legacy["Valor_Total"]),
                "target_public": "",
                "collateral_type": "",
                "target_assets": "",
                "collateral_description": "",
                "identified_debtors": "",
                "distribution_regime": "",
                "trading_market": "",
                "administrator_name": "",
                "manager_name": "",
                "custodian_name": "",
            }
        )
        for column in _investor_source_columns():
            legacy_column = _legacy_investor_column(column)
            legacy_rows[column] = parse_number(legacy[legacy_column]) if legacy_column in legacy else 0.0
        standardized = pd.concat([standardized, legacy_rows], ignore_index=True)

    cutoff = pd.Timestamp(as_of or date.today())
    standardized = standardized[
        standardized["registration_date"].between(pd.Timestamp(start), cutoff, inclusive="both")
    ].copy()
    standardized["year"] = standardized["registration_date"].dt.year.astype(int)
    standardized["period"] = standardized["year"].astype(str).replace({str(cutoff.year): f"{cutoff.year}YTD"})
    status_upper = standardized["status"].map(normalize_text)
    standardized["valid_offer"] = ~status_upper.isin(EXCLUDED_OFFER_STATUSES)
    standardized["closed_offer"] = status_upper.eq("OFERTA ENCERRADA") | (
        standardized["source_dataset"].eq("oferta_distribuicao.csv") & standardized["closing_date"].notna()
    )
    standardized["ticket_relevant"] = standardized["registered_volume_brl"].ge(RELEVANT_TICKET_BRL)
    standardized["leader_group"] = standardized["leader_name"].map(canonical_provider)
    standardized["administrator_group"] = standardized["administrator_name"].map(canonical_provider)
    standardized["manager_group"] = standardized["manager_name"].map(canonical_provider)
    standardized["custodian_group"] = standardized["custodian_name"].map(canonical_provider)
    standardized["segment"] = standardized.apply(
        lambda row: classify_segment(
            row["issuer_name"],
            row["target_assets"],
            row["collateral_description"],
            row["security"],
        ),
        axis=1,
    )
    originators = standardized.apply(
        lambda row: identify_originator(
            row["issuer_name"],
            row["target_assets"],
            row["collateral_description"],
            row["identified_debtors"],
        ),
        axis=1,
        result_type="expand",
    )
    originators.columns = ["originator_group", "originator_source", "originator_evidence"]
    standardized = pd.concat([standardized, originators], axis=1)
    return _add_investor_metrics(standardized).sort_values(
        ["registration_date", "registered_volume_brl"], ascending=[False, False]
    ).reset_index(drop=True)


def _investor_source_columns() -> list[str]:
    return [
        "Num_Invest_Pessoa_Natural",
        "Qtde_VM_Pessoa_Natural",
        "Num_Invest_Clube_Investimento",
        "Qtde_VM_Clube_Investimento",
        "Num_Invest_Fundos_Investimento",
        "Qtde_VM_Fundos_Investimento",
        "Num_Invest_Entidade_Previdencia_Privada",
        "Qtde_VM_Entidade_Previdencia_Privada",
        "Num_Invest_Companhia_Seguradora",
        "Qtde_VM_Companhia_Seguradora",
        "Num_Invest_Investidor_Estrangeiro",
        "Qtde_VM_Investidor_Estrangeiro",
        "Num_Invest_Instit_Intermed_Partic_Consorcio_Distrib",
        "Qtde_VM_Instit_Intermed_Partic_Consorcio_Distrib",
        "Num_Invest_Instit_Financ_Emissora_Partic_Consorcio",
        "Qtde_VM_Instit_Financ_Emissora_Partic_Consorcio",
        "Num_Invest_Demais_Instit_Financ",
        "Qtde_VM_Demais_Instit_Financ",
        "Num_Invest_Demais_Pessoa_Juridica_Emissora_Partic_Consorcio",
        "Qtde_VM_Demais_Pessoa_Juridica_Emissora_Partic_Consorcio",
        "Num_Invest_Demais_Pessoa_Juridica",
        "Qtde_VM_Demais_Pessoa_Juridica",
        "Num_Invest_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio",
        "Qdte_VM_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio",
    ]


def _legacy_investor_column(column: str) -> str:
    replacements = {
        "Num_Invest_": "Nr_",
        "Qtde_VM_": "Qtd_",
        "Qdte_VM_": "Qdt_",
    }
    output = column
    for source, target in replacements.items():
        if output.startswith(source):
            output = target + output[len(source) :]
            break
    return output


def _add_investor_metrics(offers: pd.DataFrame) -> pd.DataFrame:
    frame = offers.copy()
    count_columns = [column for column in frame if column.startswith("Num_Invest_")]
    quantity_columns = [column for column in frame if column.startswith(("Qtde_VM_", "Qdte_VM_"))]
    frame["investor_count"] = frame[count_columns].fillna(0).sum(axis=1)
    frame["placed_quantity"] = frame[quantity_columns].fillna(0).sum(axis=1)
    frame["investor_data_available"] = frame["investor_count"].gt(0)
    implied_price = frame["registered_volume_brl"].div(frame["registered_quantity"].where(frame["registered_quantity"] > 0))
    frame["placed_volume_proxy_brl"] = (frame["placed_quantity"] * implied_price).clip(upper=frame["registered_volume_brl"])
    frame["single_investor"] = frame["investor_count"].eq(1)
    frame["investor_bucket"] = pd.cut(
        frame["investor_count"],
        bins=[-0.1, 0, 1, 2, 5, 20, float("inf")],
        labels=["Sem dado", "1 investidor", "2 investidores", "3-5 investidores", "6-20 investidores", "21+ investidores"],
    ).astype(str)
    market = frame["trading_market"].map(normalize_text)
    secondary_pattern = r"SECUND|FUNDOS21|CETIP|BALCAO\s+ORGANIZ|\bB3\b"
    frame["secondary_market_infrastructure"] = market.str.contains(secondary_pattern, regex=True, na=False) & ~market.str.fullmatch(r"PRIMARI[OA]", na=False)
    frame["fund_investor_present"] = pd.to_numeric(frame.get("Num_Invest_Fundos_Investimento"), errors="coerce").fillna(0).gt(0)
    bank_columns = [
        column
        for column in (
            "Num_Invest_Instit_Intermed_Partic_Consorcio_Distrib",
            "Num_Invest_Instit_Financ_Emissora_Partic_Consorcio",
            "Num_Invest_Demais_Instit_Financ",
        )
        if column in frame
    ]
    frame["bank_investor_present"] = frame[bank_columns].fillna(0).sum(axis=1).gt(0)
    informed_roles = frame[["administrator_group", "manager_group", "custodian_group"]].ne("Não informado").all(axis=1)
    frame["same_platform_admin_manager_custodian"] = informed_roles & (
        frame["administrator_group"].eq(frame["manager_group"])
        & frame["administrator_group"].eq(frame["custodian_group"])
    )
    return frame


def build_offer_annual(offers: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for year, group in offers.groupby("year", sort=True):
        valid = group[group["valid_offer"]]
        closed = group[group["closed_offer"]]
        relevant = valid[valid["ticket_relevant"]]
        initial = valid[valid["initial_offer"]]
        initial_relevant = initial[initial["ticket_relevant"]]
        investor = closed[closed["investor_data_available"]]
        rows.append(
            {
                "year": int(year),
                "period": str(valid["period"].iloc[0]) if not valid.empty else str(year),
                "valid_offers": int(valid["offer_id"].nunique()),
                "valid_registered_volume_brl": float(valid["registered_volume_brl"].sum()),
                "valid_issuers": int(valid["issuer_cnpj"].nunique()),
                "closed_offers": int(closed["offer_id"].nunique()),
                "closed_registered_volume_brl": float(closed["registered_volume_brl"].sum()),
                "initial_offers": int(initial["offer_id"].nunique()),
                "initial_registered_volume_brl": float(initial["registered_volume_brl"].sum()),
                "initial_issuers": int(initial["issuer_cnpj"].nunique()),
                "relevant_ticket_offers": int(relevant["offer_id"].nunique()),
                "relevant_ticket_volume_brl": float(relevant["registered_volume_brl"].sum()),
                "relevant_ticket_volume_share": float(relevant["registered_volume_brl"].sum() / valid["registered_volume_brl"].sum()) if valid["registered_volume_brl"].sum() else 0.0,
                "initial_relevant_ticket_offers": int(initial_relevant["offer_id"].nunique()),
                "initial_relevant_ticket_volume_brl": float(initial_relevant["registered_volume_brl"].sum()),
                "offers_with_investor_data": int(len(investor)),
                "investor_data_coverage": float(len(investor) / len(closed)) if len(closed) else 0.0,
                "single_investor_offers": int(investor["single_investor"].sum()),
                "single_investor_share": float(investor["single_investor"].mean()) if len(investor) else 0.0,
                "median_investors": float(investor["investor_count"].median()) if len(investor) else 0.0,
                "placed_volume_proxy_brl": float(investor["placed_volume_proxy_brl"].sum()),
            }
        )
    return pd.DataFrame(rows)


def build_offer_rankings(offers: pd.DataFrame) -> pd.DataFrame:
    role_specs = {
        "coordenador": "leader_group",
        "administrador": "administrator_group",
        "gestor": "manager_group",
        "custodiante": "custodian_group",
    }
    rows: list[dict[str, object]] = []
    valid = offers[offers["valid_offer"]].copy()
    for ticket_scope, scoped in {
        "todas": valid,
        ">= R$ 300 mi": valid[valid["ticket_relevant"]],
    }.items():
        for (year, segment), period_group in scoped.groupby(["year", "segment"], dropna=False):
            for role, column in role_specs.items():
                grouped = (
                    period_group[period_group[column].ne("Não informado")]
                    .groupby(column, as_index=False)
                    .agg(offers=("offer_id", "nunique"), volume_brl=("registered_volume_brl", "sum"))
                    .rename(columns={column: "participant"})
                )
                total = float(grouped["volume_brl"].sum())
                grouped = grouped.sort_values(["volume_brl", "offers"], ascending=[False, False]).reset_index(drop=True)
                grouped["rank"] = grouped.index + 1
                for item in grouped.itertuples(index=False):
                    rows.append(
                        {
                            "year": int(year),
                            "period": str(period_group["period"].iloc[0]),
                            "segment": clean_text(segment) or "Não identificado",
                            "ticket_scope": ticket_scope,
                            "role": role,
                            "participant": item.participant,
                            "offers": int(item.offers),
                            "volume_brl": float(item.volume_brl),
                            "share": float(item.volume_brl / total) if total else 0.0,
                            "rank": int(item.rank),
                            "source": "CVM Ofertas Públicas de Distribuição",
                        }
                    )
        # Overall view is generated separately to avoid mixing segment totals.
        for year, period_group in scoped.groupby("year"):
            for role, column in role_specs.items():
                grouped = (
                    period_group[period_group[column].ne("Não informado")]
                    .groupby(column, as_index=False)
                    .agg(offers=("offer_id", "nunique"), volume_brl=("registered_volume_brl", "sum"))
                    .rename(columns={column: "participant"})
                    .sort_values(["volume_brl", "offers"], ascending=[False, False])
                    .reset_index(drop=True)
                )
                total = float(grouped["volume_brl"].sum())
                for rank, item in enumerate(grouped.itertuples(index=False), start=1):
                    rows.append(
                        {
                            "year": int(year),
                            "period": str(period_group["period"].iloc[0]),
                            "segment": "Todos",
                            "ticket_scope": ticket_scope,
                            "role": role,
                            "participant": item.participant,
                            "offers": int(item.offers),
                            "volume_brl": float(item.volume_brl),
                            "share": float(item.volume_brl / total) if total else 0.0,
                            "rank": rank,
                            "source": "CVM Ofertas Públicas de Distribuição",
                        }
                    )
    return pd.DataFrame(rows)


def build_originator_annual(offers: pd.DataFrame) -> pd.DataFrame:
    valid = offers[offers["valid_offer"]].copy()
    identified = valid[valid["originator_group"].ne("Não identificado")].copy()
    total_by_year = valid.groupby("year")["registered_volume_brl"].sum().to_dict()
    identified_by_year = identified.groupby("year")["registered_volume_brl"].sum().to_dict()
    grouped = (
        identified.groupby(["year", "period", "originator_group"], as_index=False)
        .agg(
            offers=("offer_id", "nunique"),
            funds=("issuer_cnpj", "nunique"),
            volume_brl=("registered_volume_brl", "sum"),
            evidence_sample=("originator_evidence", lambda values: " | ".join(dict.fromkeys(filter(None, values)))[:500]),
        )
    )
    grouped["share_of_identified"] = grouped.apply(
        lambda row: row["volume_brl"] / identified_by_year.get(row["year"], 1.0), axis=1
    )
    grouped["share_of_total"] = grouped.apply(
        lambda row: row["volume_brl"] / total_by_year.get(row["year"], 1.0), axis=1
    )
    grouped["identified_volume_coverage"] = grouped["year"].map(
        lambda year: identified_by_year.get(year, 0.0) / total_by_year.get(year, 1.0)
    )
    grouped["rank"] = grouped.groupby("year")["volume_brl"].rank(method="first", ascending=False).astype(int)
    grouped["confidence"] = "alta - regra nominal auditável"
    return grouped.sort_values(["year", "rank"])


def build_competitive_position(offers: pd.DataFrame) -> pd.DataFrame:
    """Executive view of relevant-ticket structuring, recurring roles and placement."""
    rows: list[dict[str, object]] = []
    relevant = offers[offers["valid_offer"] & offers["ticket_relevant"]].copy()
    for year, group in relevant.groupby("year", sort=True):
        total_volume = float(group["registered_volume_brl"].sum())
        coordinator = (
            group.groupby("leader_group", as_index=False)["registered_volume_brl"]
            .sum()
            .sort_values("registered_volume_brl", ascending=False)
            .reset_index(drop=True)
        )
        coordinator["rank"] = coordinator.index + 1
        itau = group[group["leader_group"].eq("Itaú")]
        itau_closed = itau[itau["closed_offer"] & itau["investor_data_available"]]
        all_closed = group[group["closed_offer"] & group["investor_data_available"]]

        role_values: dict[str, float] = {}
        role_ranks: dict[str, int] = {}
        for role, column in {
            "administrator": "administrator_group",
            "manager": "manager_group",
            "custodian": "custodian_group",
        }.items():
            by_role = (
                group[group[column].ne("Não informado")]
                .groupby(column)["registered_volume_brl"]
                .sum()
                .sort_values(ascending=False)
            )
            role_values[role] = float(by_role.get("Itaú", 0.0))
            role_ranks[role] = int(list(by_role.index).index("Itaú") + 1) if "Itaú" in by_role.index else 0

        itau_coordinator_row = coordinator[coordinator["leader_group"].eq("Itaú")]
        itau_coordinator_rank = int(itau_coordinator_row.iloc[0]["rank"]) if not itau_coordinator_row.empty else 0
        monostructure_volume = float(
            group.loc[group["same_platform_admin_manager_custodian"], "registered_volume_brl"].sum()
        )
        rows.append(
            {
                "year": int(year),
                "period": str(group["period"].iloc[0]),
                "market_relevant_offers": int(group["offer_id"].nunique()),
                "market_relevant_volume_brl": total_volume,
                "itau_coordinator_offers": int(itau["offer_id"].nunique()),
                "itau_coordinator_volume_brl": float(itau["registered_volume_brl"].sum()),
                "itau_coordinator_share": float(itau["registered_volume_brl"].sum() / total_volume) if total_volume else 0.0,
                "itau_coordinator_rank": itau_coordinator_rank,
                "itau_administrator_volume_brl": role_values["administrator"],
                "itau_administrator_share": role_values["administrator"] / total_volume if total_volume else 0.0,
                "itau_administrator_rank": role_ranks["administrator"],
                "itau_manager_volume_brl": role_values["manager"],
                "itau_manager_share": role_values["manager"] / total_volume if total_volume else 0.0,
                "itau_manager_rank": role_ranks["manager"],
                "itau_custodian_volume_brl": role_values["custodian"],
                "itau_custodian_share": role_values["custodian"] / total_volume if total_volume else 0.0,
                "itau_custodian_rank": role_ranks["custodian"],
                "itau_coordinator_with_itau_admin_volume_brl": float(itau.loc[itau["administrator_group"].eq("Itaú"), "registered_volume_brl"].sum()),
                "itau_coordinator_with_itau_custody_volume_brl": float(itau.loc[itau["custodian_group"].eq("Itaú"), "registered_volume_brl"].sum()),
                "itau_coordinator_with_itau_management_volume_brl": float(itau.loc[itau["manager_group"].eq("Itaú"), "registered_volume_brl"].sum()),
                "market_monostructure_volume_share": monostructure_volume / total_volume if total_volume else 0.0,
                "market_closed_investor_data_offers": int(len(all_closed)),
                "market_single_investor_share": float(all_closed["single_investor"].mean()) if len(all_closed) else 0.0,
                "itau_closed_investor_data_offers": int(len(itau_closed)),
                "itau_single_investor_share": float(itau_closed["single_investor"].mean()) if len(itau_closed) else 0.0,
                "itau_median_investors": float(itau_closed["investor_count"].median()) if len(itau_closed) else 0.0,
                "itau_fund_investor_presence_share": float(itau_closed["fund_investor_present"].mean()) if len(itau_closed) else 0.0,
                "itau_bank_investor_presence_share": float(itau_closed["bank_investor_present"].mean()) if len(itau_closed) else 0.0,
                "source": "CVM Ofertas Públicas de Distribuição; volume registrado, não garantia de liquidação",
            }
        )
    return pd.DataFrame(rows)


INVESTOR_CATEGORIES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("Pessoa natural", ("Num_Invest_Pessoa_Natural",), ("Qtde_VM_Pessoa_Natural",)),
    ("Fundos de investimento", ("Num_Invest_Fundos_Investimento",), ("Qtde_VM_Fundos_Investimento",)),
    (
        "Instituições financeiras",
        (
            "Num_Invest_Instit_Intermed_Partic_Consorcio_Distrib",
            "Num_Invest_Instit_Financ_Emissora_Partic_Consorcio",
            "Num_Invest_Demais_Instit_Financ",
        ),
        (
            "Qtde_VM_Instit_Intermed_Partic_Consorcio_Distrib",
            "Qtde_VM_Instit_Financ_Emissora_Partic_Consorcio",
            "Qtde_VM_Demais_Instit_Financ",
        ),
    ),
    (
        "Demais pessoas jurídicas",
        (
            "Num_Invest_Demais_Pessoa_Juridica_Emissora_Partic_Consorcio",
            "Num_Invest_Demais_Pessoa_Juridica",
            "Num_Invest_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio",
        ),
        (
            "Qtde_VM_Demais_Pessoa_Juridica_Emissora_Partic_Consorcio",
            "Qtde_VM_Demais_Pessoa_Juridica",
            "Qdte_VM_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio",
        ),
    ),
    ("Previdência", ("Num_Invest_Entidade_Previdencia_Privada",), ("Qtde_VM_Entidade_Previdencia_Privada",)),
    ("Seguradoras", ("Num_Invest_Companhia_Seguradora",), ("Qtde_VM_Companhia_Seguradora",)),
    ("Investidor estrangeiro", ("Num_Invest_Investidor_Estrangeiro",), ("Qtde_VM_Investidor_Estrangeiro",)),
    ("Clubes de investimento", ("Num_Invest_Clube_Investimento",), ("Qtde_VM_Clube_Investimento",)),
)


def build_investor_distribution(offers: pd.DataFrame) -> pd.DataFrame:
    frame = offers[offers["closed_offer"] & offers["investor_data_available"]].copy()
    grouped = (
        frame.groupby(["year", "period", "investor_bucket"], as_index=False)
        .agg(
            offers=("offer_id", "nunique"),
            registered_volume_brl=("registered_volume_brl", "sum"),
            placed_volume_proxy_brl=("placed_volume_proxy_brl", "sum"),
        )
    )
    totals = grouped.groupby("year").agg(total_offers=("offers", "sum"), total_volume=("registered_volume_brl", "sum"))
    grouped = grouped.merge(totals, on="year", how="left")
    grouped["offer_share"] = grouped["offers"] / grouped["total_offers"]
    grouped["volume_share"] = grouped["registered_volume_brl"] / grouped["total_volume"]
    return grouped


def build_investor_types(offers: pd.DataFrame) -> pd.DataFrame:
    frame = offers[offers["closed_offer"] & offers["investor_data_available"]].copy()
    rows: list[dict[str, object]] = []
    implied_price = frame["registered_volume_brl"].div(frame["registered_quantity"].where(frame["registered_quantity"] > 0))
    for label, count_columns, quantity_columns in INVESTOR_CATEGORIES:
        count = frame[list(count_columns)].fillna(0).sum(axis=1)
        quantity = frame[list(quantity_columns)].fillna(0).sum(axis=1)
        value = (quantity * implied_price).clip(upper=frame["registered_volume_brl"])
        for year in sorted(frame["year"].unique()):
            mask = frame["year"].eq(year)
            rows.append(
                {
                    "year": int(year),
                    "period": str(frame.loc[mask, "period"].iloc[0]),
                    "investor_type": label,
                    "investor_accounts": float(count.loc[mask].sum()),
                    "offers_present": int(count.loc[mask].gt(0).sum()),
                    "placed_volume_proxy_brl": float(value.loc[mask].sum()),
                    "offers_total": int(mask.sum()),
                }
            )
    output = pd.DataFrame(rows)
    output["offer_presence_share"] = output["offers_present"] / output["offers_total"]
    output["value_share"] = output["placed_volume_proxy_brl"] / output.groupby("year")["placed_volume_proxy_brl"].transform("sum")
    return output


def build_stock_ranking_deltas(
    vehicle_monthly: pd.DataFrame,
    *,
    latest_competence: str,
    target_competences: dict[str, str] | None = None,
) -> pd.DataFrame:
    if vehicle_monthly is None or vehicle_monthly.empty:
        return pd.DataFrame()
    targets = target_competences or {
        "2024": "2024-12",
        "2025": "2025-12",
        "2026YTD": latest_competence,
    }
    frame = vehicle_monthly[vehicle_monthly["competencia"].isin(set(targets.values()))].copy()
    frame["period"] = frame["competencia"].map({value: key for key, value in targets.items()})
    frame["pl"] = pd.to_numeric(frame["pl"], errors="coerce").fillna(0)
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(only_digits)
    frame["segment"] = frame.get("segmento_principal", pd.Series(index=frame.index, dtype=str)).fillna("Não classificado")
    role_specs = {
        "administrador": ("admin_nome", "histórico mensal do Informe Mensal CVM"),
        "gestor": ("gestor_nome", "reconstrução com prestador do cadastro vigente"),
        "custodiante": ("custodiante_nome", "reconstrução com prestador do cadastro vigente"),
    }
    rows: list[dict[str, object]] = []
    for role, (column, nature) in role_specs.items():
        role_frame = frame.copy()
        role_frame["participant"] = role_frame[column].map(canonical_provider)
        role_frame = role_frame[role_frame["participant"].ne("Não informado")]
        for segment, segment_frame in [("Todos", role_frame), *list(role_frame.groupby("segment"))]:
            for period, period_frame in segment_frame.groupby("period"):
                grouped = (
                    period_frame.groupby("participant", as_index=False)
                    .agg(pl_brl=("pl", "sum"), funds=("cnpj_fundo", "nunique"))
                )
                total_pl = float(grouped["pl_brl"].sum())
                total_funds = float(grouped["funds"].sum())
                source_total_pl = float(segment_frame[segment_frame["period"].eq(period)]["pl"].sum())
                for metric, value_column, denominator in [
                    ("PL", "pl_brl", total_pl),
                    ("Fundos", "funds", total_funds),
                ]:
                    ranked = grouped.sort_values([value_column, "participant"], ascending=[False, True]).reset_index(drop=True)
                    for rank, item in enumerate(ranked.itertuples(index=False), start=1):
                        value = float(getattr(item, value_column))
                        rows.append(
                            {
                                "period": period,
                                "competencia": targets[period],
                                "role": role,
                                "segment": clean_text(segment) or "Não classificado",
                                "metric": metric,
                                "participant": item.participant,
                                "value": value,
                                "share": value / denominator if denominator else 0.0,
                                "rank": rank,
                                "pl_coverage": total_pl / source_total_pl if source_total_pl else 0.0,
                                "data_nature": nature,
                            }
                        )
    output = pd.DataFrame(rows)
    if output.empty:
        return output
    period_order = {period: index for index, period in enumerate(targets)}
    output["period_order"] = output["period"].map(period_order)
    output = output.sort_values(["role", "segment", "metric", "participant", "period_order"])
    grouped = output.groupby(["role", "segment", "metric", "participant"], dropna=False)
    output["rank_change_vs_prior"] = grouped["rank"].shift(1) - output["rank"]
    output["share_change_pp_vs_prior"] = (output["share"] - grouped["share"].shift(1)) * 100.0
    output["value_change_vs_prior"] = output["value"] - grouped["value"].shift(1)
    return output.drop(columns="period_order").reset_index(drop=True)


def intelligence_manifest(
    *,
    offers: pd.DataFrame,
    annual: pd.DataFrame,
    rankings: pd.DataFrame,
    originators: pd.DataFrame,
    investor_distribution: pd.DataFrame,
    investor_types: pd.DataFrame,
    stock_rankings: pd.DataFrame,
    source_path: Path,
    as_of: date,
) -> dict[str, object]:
    valid = offers[offers["valid_offer"]]
    closed = offers[offers["closed_offer"]]
    return {
        "schema_version": "industry-intelligence/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of_date": as_of.isoformat(),
        "sources": {
            "offers": "CVM Ofertas Públicas de Distribuição - atualização diária",
            "offers_url": "https://dados.cvm.gov.br/dataset/oferta-distrib",
            "offers_source_file": source_path.name,
            "stock": "CVM FIDC - Informe Mensal",
        },
        "quality": {
            "offer_rows": int(len(offers)),
            "valid_offer_rows": int(len(valid)),
            "closed_offer_rows": int(len(closed)),
            "valid_registered_volume_brl": float(valid["registered_volume_brl"].sum()),
            "closed_investor_data_coverage": float(closed["investor_data_available"].mean()) if len(closed) else 0.0,
            "originator_identified_volume_coverage": {
                str(int(year)): float(group["registered_volume_brl"].sum() / valid.loc[valid["year"].eq(year), "registered_volume_brl"].sum())
                for year, group in valid[valid["originator_group"].ne("Não identificado")].groupby("year")
                if valid.loc[valid["year"].eq(year), "registered_volume_brl"].sum()
            },
            "stock_manager_custodian_nature": "reconstrução com cadastro vigente; não prova troca histórica de mandato",
        },
        "outputs": {
            "annual_rows": int(len(annual)),
            "offer_ranking_rows": int(len(rankings)),
            "originator_rows": int(len(originators)),
            "investor_distribution_rows": int(len(investor_distribution)),
            "investor_type_rows": int(len(investor_types)),
            "stock_ranking_rows": int(len(stock_rankings)),
        },
    }
