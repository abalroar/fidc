from __future__ import annotations

import argparse
import html
import json
import math
import re
import sqlite3
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

import pandas as pd


DEFAULT_DB = Path("data/fidc_credit_strategy/fidc_credit_strategy.sqlite")
DEFAULT_OUTPUT = Path("reports/fidc_strategy_static_20260609.html")
DEFAULT_NAMED_PARTIES = Path("reports/fidc_clean_named_parties_20260609.csv")
DEFAULT_MANUAL_REVIEW = Path("reports/fidc_manual_reclassification_review_20260609.csv")
OFFERS_PATH = Path("outputs/fidc_credit_strategy_study_20260609/issuance/fidc_public_offers_2024_2026ytd.csv")
STRATEGY_DIR = Path("outputs/fidc_credit_strategy_study_20260609/strategy")
DIAGNOSTIC_DIR = Path("outputs/fidc_director_deep_diagnostic_20260609")
TEXT_CACHE_DIR = DIAGNOSTIC_DIR / "pdf_text_cache"

PALETTE = {
    "ink": "#17212b",
    "muted": "#657184",
    "line": "#dce5ea",
    "paper": "#fbfcfd",
    "blue": "#285f8f",
    "teal": "#287a74",
    "green": "#4f8161",
    "orange": "#c66a32",
    "red": "#a94d59",
    "gold": "#a97d31",
}

FEATURES_FOR_BOARD = [
    "asset_class_confirmed",
    "named_originator_or_cedente",
    "named_debtor_or_sacado",
    "subordination_minimum",
    "mezzanine_layer",
    "cash_or_liquidity_reserve",
    "eligibility_criteria",
    "concentration_limits",
    "default_or_performance_triggers",
    "repurchase_or_indemnity",
    "rating_required",
    "amortization_profile_defined",
]

CLASS_RULES: list[tuple[str, str, list[str]]] = [
    (
        "Meios de Pagamento e Cartões",
        "Bancos Emissores",
        [
            r"\bbanco emissor\b",
            r"\bemissor(?:es)? de cart",
            r"\bissuer\b",
            r"fatura(?:s)? de cart",
            r"cart[aã]o de cr[eé]dito consignado",
            r"cart[aã]o benef[ií]cio consignado",
        ],
    ),
    (
        "Meios de Pagamento e Cartões",
        "Arranjos de pagamento/adquirência",
        [
            r"arranjo(?:s)? de pagamento",
            r"adquir[eê]ncia|adquirente|subadquirente|subcredenciador",
            r"estabelecimentos? credenciad",
            r"transa[cç][oõ]es? de pagamento",
            r"sistema cloudwalk|sistema sumup|maquinin",
            r"instrumentos? de pagamento",
        ],
    ),
    (
        "Crédito PF",
        "FGTS",
        [r"saque[- ]anivers[aá]rio", r"\bfgts\b", r"cess[aã]o fiduci[aá]ria.*fgts"],
    ),
    (
        "Crédito PF",
        "Consignado/INSS",
        [r"\binss\b", r"consigna[cç][aã]o", r"empr[eé]stimos? consignad", r"benef[ií]cio previdenci[aá]rio"],
    ),
    (
        "Crédito PF",
        "Auto/Veículos",
        [r"ve[ií]cul", r"autom[oó]v", r"financiamento de ve", r"garantia.*ve[ií]cul"],
    ),
    (
        "Crédito PF",
        "Crédito estudantil",
        [r"cr[eé]dito estudantil", r"servi[cç]os educacionais", r"institui[cç][oõ]es de ensino", r"pravaler|educbank"],
    ),
    (
        "Agro",
        "Agro",
        [r"agroneg[oó]cio", r"produtor(?:es)? rural", r"c[eé]dula de produto rural|\bcpr\b", r"insumos agr[ií]colas"],
    ),
    (
        "Crédito PJ",
        "Risco sacado/fornecedores",
        [r"risco sacado", r"fornecedor(?:es)?", r"confirming", r"antecip[aã].*fornecedor", r"sacado(?:s)?.*fornecedor"],
    ),
    (
        "Crédito PJ",
        "CCB/Notas comerciais/Capital de giro",
        [r"c[eé]dulas? de cr[eé]dito banc[aá]rio|\bccb\b", r"capital de giro", r"notas? comerciais?"],
    ),
    (
        "Crédito PJ",
        "Recebíveis comerciais/multissetorial",
        [r"duplicata", r"receb[ií]veis comerciais", r"presta[cç][aã]o de servi[cç]os", r"industrial, comercial"],
    ),
    (
        "Imobiliário",
        "Imobiliário",
        [r"imobili[aá]ri", r"alug[uú]eis?", r"loteamento", r"contratos? de compra e venda de im[oó]veis"],
    ),
    (
        "Judicial/Precatórios/NPL",
        "Precatórios/direitos judiciais",
        [r"precat[oó]ri", r"direitos? credit[oó]rios judiciais", r"senten[cç]a judicial"],
    ),
    (
        "Judicial/Precatórios/NPL",
        "Não padronizado/NPL",
        [r"n[aã]o padronizad", r"\bnpl\b", r"cr[eé]ditos? inadimplid", r"carteira vencida"],
    ),
    (
        "FIC/Alocador",
        "FIC de FIDC",
        [r"cotas? de emiss[aã]o de fidc", r"fic fidc", r"fundo de investimento em cotas"],
    ),
]

SUBTYPE_NOTES = {
    ("Meios de Pagamento e Cartões", "Arranjos de pagamento/adquirência"): (
        "Recebíveis de liquidação de transações em arranjos de pagamento. O risco principal tende a estar no fluxo de liquidação por adquirente/subadquirente, estabelecimento credenciado, bandeira e regras do arranjo."
    ),
    ("Meios de Pagamento e Cartões", "Bancos Emissores"): (
        "Recebíveis ligados a emissores de cartão ou faturas. Deve ficar separado da adquirência: aqui a discussão é risco do emissor/portador/fatura, não apenas risco de liquidação do adquirente."
    ),
    ("Crédito PF", "FGTS"): (
        "CCBs ou direitos vinculados ao saque-aniversário do FGTS, com forte dependência de regras operacionais de cessão fiduciária, esteira digital e repasse do fluxo."
    ),
    ("Crédito PF", "Consignado/INSS"): (
        "Recebíveis de empréstimos consignados, frequentemente representados por CCBs, com risco de margem, convênio, averbação e fluxo de benefício/folha."
    ),
    ("Crédito PF", "Auto/Veículos"): (
        "Crédito ao consumidor ou financiamento garantido por veículos. A qualidade da garantia, formalização, cobrança e elegibilidade da carteira costuma ser tão importante quanto a subordinação."
    ),
    ("Crédito PJ", "Risco sacado/fornecedores"): (
        "Estruturas de supplier finance: cedente/originador vende recebíveis, mas o risco de crédito econômico concentra-se no sacado/devedor corporativo."
    ),
    ("Crédito PJ", "Recebíveis comerciais/multissetorial"): (
        "Carteiras de duplicatas, prestação de serviços, recebíveis comerciais e multicedentes. A leitura-chave é concentração, recompra, verificação de lastro e elegibilidade."
    ),
    ("Crédito PJ", "CCB/Notas comerciais/Capital de giro"): (
        "Crédito corporativo documentado por CCB, nota comercial ou instrumentos similares. O risco migra para underwriting, covenants, garantias e capacidade de cobrança."
    ),
    ("Agro", "Agro"): (
        "Direitos ligados ao agronegócio: CPR, insumos, produtores, tradings ou cadeias rurais. A safra, concentração por produtor/grupo e garantias reais/cessões pesam muito."
    ),
    ("Imobiliário", "Imobiliário"): (
        "Recebíveis imobiliários, aluguel, loteamentos ou contratos de compra e venda. O conforto vem de garantias, fluxo do empreendimento e governança sobre repasses."
    ),
    ("Judicial/Precatórios/NPL", "Precatórios/direitos judiciais"): (
        "Ativos judiciais ou precatórios. O foco não é só inadimplência: é prazo, liquidez, elegibilidade jurídica, cessão e validação documental."
    ),
    ("FIC/Alocador", "FIC de FIDC"): (
        "Fundo alocador em cotas de outros FIDCs. Deve ser lido como veículo de exposição, não como originação direta de recebíveis."
    ),
}


def number_or_nan(value: object) -> float:
    try:
        if value is None:
            return math.nan
        number = float(value)
        return number if math.isfinite(number) else math.nan
    except (TypeError, ValueError):
        return math.nan


def brl(value: object) -> str:
    number = number_or_nan(value)
    if math.isnan(number):
        return "-"
    if abs(number) >= 1e9:
        return f"R$ {number / 1e9:,.1f} bi".replace(",", "_").replace(".", ",").replace("_", ".")
    if abs(number) >= 1e6:
        return f"R$ {number / 1e6:,.0f} mi".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {number:,.0f}".replace(",", "_").replace(".", ",").replace("_", ".")


def pct(value: object, digits: int = 1) -> str:
    number = number_or_nan(value)
    if math.isnan(number):
        return "-"
    return f"{number:.{digits}f}%".replace(".", ",")


def num(value: object, digits: int = 0) -> str:
    number = number_or_nan(value)
    if math.isnan(number):
        return "-"
    return f"{number:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def norm_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def clean_ws(value: object) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "sim", "yes", "y"})


def read_sql(db: Path, table: str) -> pd.DataFrame:
    with sqlite3.connect(db) as conn:
        return pd.read_sql_query(f"select * from {table}", conn)


def read_metadata(db: Path) -> dict[str, str]:
    if not db.exists():
        return {}
    frame = read_sql(db, "study_metadata")
    if {"key", "value"}.issubset(frame.columns):
        return dict(zip(frame["key"], frame["value"]))
    if frame.shape[1] >= 2:
        return dict(zip(frame.iloc[:, 0], frame.iloc[:, 1]))
    return {}


def classify_text(text: str) -> tuple[str, str, str, int]:
    normalized = norm_text(text)
    best: tuple[str, str, str, int] = ("Não classificado", "Sem classificação", "", 0)
    for setor, subtipo, patterns in CLASS_RULES:
        hits = []
        for pattern in patterns:
            found = re.search(pattern, normalized, flags=re.I)
            if found:
                hits.append(pattern)
        if len(hits) > best[3]:
            best = (setor, subtipo, hits[0], len(hits))
    return best


def extract_evidence(text: str, pattern: str, width: int = 180) -> str:
    if not text or not pattern:
        return ""
    normalized = norm_text(text)
    match = re.search(pattern, normalized, flags=re.I)
    if not match:
        return ""
    start = max(0, match.start() - width // 2)
    end = min(len(normalized), match.end() + width // 2)
    return clean_ws(normalized[start:end])


def load_cached_text(cnpj: str) -> str:
    digits = re.sub(r"\D", "", str(cnpj))
    if not digits or not TEXT_CACHE_DIR.exists():
        return ""
    chunks = []
    for path in sorted(TEXT_CACHE_DIR.glob(f"{digits}_*.txt")):
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(chunks)


def enrich_offers_with_audit_classification(offers: pd.DataFrame, funds: pd.DataFrame) -> pd.DataFrame:
    class_cols = ["cnpj", "setor_n1", "setor_n2", "fund_name_final", "pl_atual_brl"]
    enriched = offers.merge(funds[class_cols], left_on="cnpj_emissor", right_on="cnpj", how="left")
    enriched["valor_brl"] = pd.to_numeric(enriched["valor_total_registrado"], errors="coerce").fillna(0.0)
    enriched["valid_registered"] = bool_series(enriched["volume_registrado_valido_flag"])
    enriched["closed_conservative"] = bool_series(enriched["volume_encerrado_conservador_flag"])
    audit_rows = []
    for row in enriched.itertuples(index=False):
        original_setor = clean_ws(getattr(row, "setor_n1", "")) or "Não classificado"
        original_subtipo = clean_ws(getattr(row, "setor_n2", "")) or "Sem classificação"
        text = " ".join(
            clean_ws(getattr(row, attr, ""))
            for attr in ["nome_emissor", "fidc_subtipo", "tipo_lastro", "ativos_alvo", "administrador", "gestor", "custodiante"]
        )
        rule_setor, rule_subtipo, rule_pattern, score = classify_text(text)
        needs_rule = original_setor in {"", "Não classificado", "Sem oferta CVM mapeada"} or original_subtipo in {
            "",
            "Sem classificação",
            "Revisar manualmente",
        }
        audit_setor = original_setor
        audit_subtipo = original_subtipo
        source = "Classificação de fundo/regulamento já existente"
        evidence = ""
        if needs_rule and score >= 1 and rule_setor != "Não classificado":
            audit_setor, audit_subtipo = rule_setor, rule_subtipo
            source = "Texto oficial da oferta CVM (ativos/lastro)"
            evidence = extract_evidence(text, rule_pattern)
        elif original_setor == "Meios de Pagamento e Cartões":
            payment_setor, payment_subtipo, payment_pattern, payment_score = classify_text(text)
            if payment_setor == "Meios de Pagamento e Cartões" and payment_score >= 1:
                audit_setor, audit_subtipo = payment_setor, payment_subtipo
                source = "Refino adquirência vs banco emissor por texto CVM"
                evidence = extract_evidence(text, payment_pattern)
        audit_rows.append((audit_setor, audit_subtipo, source, evidence))
    enriched[["audit_setor", "audit_subtipo", "audit_classification_source", "audit_evidence"]] = pd.DataFrame(
        audit_rows, index=enriched.index
    )
    enriched["audit_setor"] = enriched["audit_setor"].replace("", "Não classificado").fillna("Não classificado")
    enriched["audit_subtipo"] = enriched["audit_subtipo"].replace("", "Sem classificação").fillna("Sem classificação")
    return enriched


def build_segment_table(offers: pd.DataFrame, funds: pd.DataFrame) -> pd.DataFrame:
    valid = offers[offers["valid_registered"]].copy()
    grouped = (
        valid.pivot_table(
            index=["audit_setor", "audit_subtipo"],
            columns="year",
            values="valor_brl",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for year in [2024, 2025, 2026]:
        if year not in grouped.columns:
            grouped[year] = 0.0
    emitted_funds = funds[
        (pd.to_numeric(funds.get("offers_2024", 0), errors="coerce").fillna(0) > 0)
        | (pd.to_numeric(funds.get("offers_2025", 0), errors="coerce").fillna(0) > 0)
        | (pd.to_numeric(funds.get("offers_2026", 0), errors="coerce").fillna(0) > 0)
    ].copy()
    pl = (
        emitted_funds.groupby(["setor_n1", "setor_n2"], dropna=False)
        .agg(current_pl_brl=("pl_atual_brl", "sum"), funds=("cnpj", "nunique"))
        .reset_index()
        .rename(columns={"setor_n1": "audit_setor", "setor_n2": "audit_subtipo"})
    )
    out = grouped.merge(pl, on=["audit_setor", "audit_subtipo"], how="left")
    out["current_pl_brl"] = pd.to_numeric(out["current_pl_brl"], errors="coerce").fillna(0.0)
    out["funds"] = pd.to_numeric(out["funds"], errors="coerce").fillna(0).astype(int)
    out = out.rename(
        columns={
            "audit_setor": "Segmento",
            "audit_subtipo": "Subtipo",
            2024: "2024 Issuance",
            2025: "2025 Issuance",
            2026: "2026 YTD",
            "current_pl_brl": "Current PL",
            "funds": "Funds",
        }
    )
    out = out.sort_values("2025 Issuance", ascending=False)
    total = {
        "Segmento": "Total",
        "Subtipo": "Total",
        "2024 Issuance": out["2024 Issuance"].sum(),
        "2025 Issuance": out["2025 Issuance"].sum(),
        "2026 YTD": out["2026 YTD"].sum(),
        "Current PL": emitted_funds["pl_atual_brl"].sum(),
        "Funds": emitted_funds["cnpj"].nunique(),
    }
    return pd.concat([pd.DataFrame([total]), out], ignore_index=True)


def build_reconciliation(offers: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year in [2024, 2025, 2026]:
        year_rows = offers[offers["year"].astype(str) == str(year)]
        valid = year_rows[year_rows["valid_registered"]]
        closed = year_rows[year_rows["closed_conservative"]]
        classified = valid[valid["audit_setor"] != "Não classificado"]
        rows.append(
            {
                "Ano": "2026 YTD" if year == 2026 else f"{year}FY",
                "Ofertas CVM válidas": len(valid),
                "Volume CVM válido": valid["valor_brl"].sum(),
                "Volume encerrado conservador": closed["valor_brl"].sum(),
                "Volume classificado": classified["valor_brl"].sum(),
                "% classificado": classified["valor_brl"].sum() / valid["valor_brl"].sum() * 100 if valid["valor_brl"].sum() else math.nan,
                "Fundos/CNPJs": valid["cnpj_emissor"].nunique(),
            }
        )
    return pd.DataFrame(rows)


def build_manual_reclassification(funds: pd.DataFrame, max_rows: int = 40) -> pd.DataFrame:
    data = funds.copy()
    data["materialidade_brl"] = pd.concat(
        [
            pd.to_numeric(data.get("valid_volume_2024_brl", 0), errors="coerce").fillna(0),
            pd.to_numeric(data.get("valid_volume_2025_brl", 0), errors="coerce").fillna(0),
            pd.to_numeric(data.get("valid_volume_2026_brl", 0), errors="coerce").fillna(0),
            pd.to_numeric(data.get("pl_atual_brl", 0), errors="coerce").fillna(0),
        ],
        axis=1,
    ).max(axis=1)
    mask = (data["setor_n1"].fillna("").eq("Não classificado")) | (
        data["setor_n2"].fillna("").isin(["Revisar manualmente", "Sem classificação", ""])
    )
    if TEXT_CACHE_DIR.exists():
        data["docs_lidos"] = data["cnpj"].astype(str).str.replace(r"\D", "", regex=True).map(
            lambda cnpj: len(list(TEXT_CACHE_DIR.glob(f"{cnpj}_*.txt")))
        )
    else:
        data["docs_lidos"] = 0
    with_docs = data[mask & data["docs_lidos"].gt(0)].sort_values("materialidade_brl", ascending=False).head(max_rows // 2)
    no_docs = data[mask & data["docs_lidos"].eq(0)].sort_values("materialidade_brl", ascending=False).head(max_rows - len(with_docs))
    selection = pd.concat([with_docs, no_docs], ignore_index=True)
    rows = []
    for row in selection.itertuples(index=False):
        cnpj = getattr(row, "cnpj")
        cnpj_digits = re.sub(r"\D", "", str(cnpj))
        full_text = load_cached_text(cnpj)
        setor, subtipo, pattern, score = classify_text(full_text)
        rows.append(
            {
                "CNPJ": cnpj,
                "Fundo": getattr(row, "fund_name_final", "") or getattr(row, "fund_name", ""),
                "Classificação anterior": f"{getattr(row, 'setor_n1', '')} | {getattr(row, 'setor_n2', '')}",
                "Sugestão após leitura integral": f"{setor} | {subtipo}" if score else "Sem evidência forte",
                "Score textual": score,
                "Materialidade": getattr(row, "materialidade_brl"),
                "Docs lidos": getattr(row, "docs_lidos", 0),
                "Evidência": extract_evidence(full_text, pattern, width=260),
            }
        )
    return pd.DataFrame(rows)


LEGAL_SUFFIX = (
    r"(?:(?<![A-Za-zÀ-ÿ])S\.\s*A\.?(?![A-Za-zÀ-ÿ])|"
    r"(?<![A-Za-zÀ-ÿ])S/A(?![A-Za-zÀ-ÿ])|"
    r"(?<![A-Za-zÀ-ÿ])LTDA\.?(?![A-Za-zÀ-ÿ])|"
    r"(?<![A-Za-zÀ-ÿ])EIRELI(?![A-Za-zÀ-ÿ])|"
    r"(?<![A-Za-zÀ-ÿ])S\.\s*S\.?(?![A-Za-zÀ-ÿ])|"
    r"SOCIEDADE AN[OÔ]NIMA)"
)
ADDRESS_RE = re.compile(
    r"\b(rua|avenida|av\.?|alameda|pra[cç]a|rodovia|estrada|andar|sala|conjunto|conj\.?|bloco|cep|bairro|pinheiros|"
    r"cerqueira|jardim|centro|edif[ií]cio|condom[ií]nio|cidade|estado)\b",
    re.I,
)


def clean_party_name(name: object) -> str:
    text = clean_ws(name)
    text = re.sub(r"^[\"'“”\s]*(significa|e|é|a|o|as|os|empresa de consultoria especializada ou consultora especializada)\s+", "", text, flags=re.I)
    text = re.sub(r"\s*(,?\s*com sede\b|,?\s*pessoa jur[ií]dica\b|,?\s*inscrit[ao]\b).*$", "", text, flags=re.I)
    text = re.sub(r"^[\"'“”\s]+|[\"'“”\s;,.]+$", "", text)
    text = re.sub(r"^.*\b(?:empresa|significa|consultora especializada|consultoria especializada|cedente|originador|originadora)\s+", "", text, flags=re.I)
    text = re.sub(r"^.*\b(?:endossante|sacado|devedor)\s+", "", text, flags=re.I)
    text = re.sub(r"^\d+(?:\.\d+)*\s+", "", text)
    text = re.sub(r"^.*\b(?:a|o)\s+(?=[A-ZÁ-Ú0-9][A-Za-zÀ-ÿ0-9&.,'’ \-]{2,120}" + LEGAL_SUFFIX + r")", "", text, flags=re.I)
    text = re.sub(r"^(do|da|de|dos|das)\s+", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def valid_party_name(name: str) -> bool:
    if not name or len(name) < 6:
        return False
    if re.fullmatch(r"[\d\s,./-]+", name):
        return False
    has_legal_suffix = bool(re.search(LEGAL_SUFFIX, name, flags=re.I))
    if not has_legal_suffix:
        return False
    if re.match(r"^(para|contrata[cç][aã]o|nstitui[cç][aã]o|de boletos|u\s+)", name, flags=re.I):
        return False
    if re.search(r"\b(Fitch Ratings|Moody|S&P|ag[eê]ncia de classifica[cç][aã]o|P[aá]gina|Regulamento|Direitos Credit[oó]rios|Anexo)\b", name, flags=re.I):
        return False
    if ADDRESS_RE.search(name) and not has_legal_suffix:
        return False
    if re.search(r"\b(ANDAR|SALA|CONJUNTO|BLOCO|CEP)\b", name, flags=re.I) and not has_legal_suffix:
        return False
    if len(name.split()) <= 2 and ADDRESS_RE.search(name):
        return False
    return True


def extract_party_from_context(context: object) -> str:
    text = clean_ws(context)
    patterns = [
        rf"([A-ZÁ-Ú0-9][A-Za-zÀ-ÿ0-9&.,'’ \-]{{4,150}}?{LEGAL_SUFFIX})\s*,?\s*(?:pessoa jur[ií]dica,?\s*)?(?:devidamente\s*)?inscrit[ao]",
        rf"(?:Cedente|Cedentes|Originador|Originadora|Consultora Especializada|Consultoria Especializada|Devedor|Devedores|Banco Emissor)[\"'“”:\s]*(?:é|são|significa|a|o)?\s*([A-ZÁ-Ú0-9][A-Za-zÀ-ÿ0-9&.,'’ \-]{{4,150}}?{LEGAL_SUFFIX})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            name = clean_party_name(match.group(1))
            if valid_party_name(name):
                return name
    return ""


def build_clean_named_parties(candidates: pd.DataFrame, funds: pd.DataFrame) -> pd.DataFrame:
    c = candidates.copy()
    c["candidate_clean"] = c["participant_name_candidate"].map(clean_party_name)
    c["context_name"] = c["evidence_context"].map(extract_party_from_context)
    c["party_name"] = c["context_name"]
    fallback = c["candidate_clean"].map(valid_party_name) & c["party_name"].eq("")
    c.loc[fallback, "party_name"] = c.loc[fallback, "candidate_clean"]
    c["party_name"] = c["party_name"].map(clean_party_name)
    c["participant_cnpj_candidate"] = c["participant_cnpj_candidate"].fillna("")
    c = c[c["party_name"].map(valid_party_name)].copy()
    c["cnpj_fundo"] = c["cnpj_fundo"].astype(str).str.replace(r"\D", "", regex=True)
    c["participant_cnpj_candidate"] = c["participant_cnpj_candidate"].astype(str).str.extract(r"(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})")[0].fillna("")
    fcols = ["cnpj", "valid_volume_2024_brl", "valid_volume_2025_brl", "valid_volume_2026_brl", "pl_atual_brl"]
    joined = c.merge(funds[fcols], left_on="cnpj_fundo", right_on="cnpj", how="left")
    for col in fcols[1:]:
        joined[col] = pd.to_numeric(joined[col], errors="coerce").fillna(0)
    joined["materiality_brl"] = joined[["valid_volume_2024_brl", "valid_volume_2025_brl", "valid_volume_2026_brl", "pl_atual_brl"]].max(axis=1)
    grouped = (
        joined.groupby(["setor_n1", "setor_n2", "participant_type", "party_name", "participant_cnpj_candidate"], dropna=False)
        .agg(
            funds=("cnpj_fundo", "nunique"),
            evidence_rows=("source_cache", "count"),
            materiality_brl=("materiality_brl", "sum"),
        )
        .reset_index()
        .sort_values(["materiality_brl", "funds", "evidence_rows"], ascending=False)
    )
    return grouped


def build_pricing_coverage(pricing: pd.DataFrame, offers: pd.DataFrame) -> pd.DataFrame:
    p = pricing.copy()
    p["volume_brl_num"] = pd.to_numeric(p.get("volume_brl_num"), errors="coerce").fillna(0)
    p["spread_cdi_aa_num"] = pd.to_numeric(p.get("spread_cdi_aa_num"), errors="coerce")
    p["pl_atual_brl"] = pd.to_numeric(p.get("pl_atual_brl"), errors="coerce").fillna(0)
    p = p[p["tipo_cota_normalizado"].astype(str).str.contains("Sênior", case=False, na=False)].copy()
    p = p[p["pricing_period"].isin(["2024FY", "2025FY", "2026YTD"])].copy()
    p = p[p["setor_n1"].ne("Sem oferta CVM mapeada")].copy()
    official = offers[offers["valid_registered"]].copy()
    official["pricing_period"] = official["year"].map(lambda x: "2026YTD" if str(x) == "2026" else f"{int(float(x))}FY")
    official_counts = (
        official.groupby(["pricing_period", "audit_setor", "audit_subtipo"], dropna=False)
        .agg(official_funds=("cnpj_emissor", "nunique"), official_volume_brl=("valor_brl", "sum"))
        .reset_index()
        .rename(columns={"audit_setor": "setor_n1", "audit_subtipo": "setor_n2"})
    )
    rows = []
    for keys, group in p.groupby(["pricing_period", "setor_n1", "setor_n2"], dropna=False):
        period, setor, subtipo = keys
        with_spread = group[group["spread_cdi_aa_num"].notna()]
        volume_with_spread = with_spread["volume_brl_num"].sum()
        weighted_issue = (
            (with_spread["spread_cdi_aa_num"] * with_spread["volume_brl_num"]).sum() / volume_with_spread
            if volume_with_spread > 0
            else math.nan
        )
        pl_weight = with_spread["pl_atual_brl"].sum()
        weighted_pl = (
            (with_spread["spread_cdi_aa_num"] * with_spread["pl_atual_brl"]).sum() / pl_weight if pl_weight > 0 else math.nan
        )
        rows.append(
            {
                "Período": period,
                "Setor": setor,
                "Subtipo": subtipo,
                "Tranches sênior lidas": len(group),
                "Fundos com tranche sênior": group["cnpj"].nunique(),
                "Fundos com CDI+": with_spread["cnpj"].nunique(),
                "Cobertura CDI+ por fundo": with_spread["cnpj"].nunique() / group["cnpj"].nunique() * 100 if group["cnpj"].nunique() else math.nan,
                "Cobertura CDI+ por linha": len(with_spread) / len(group) * 100 if len(group) else math.nan,
                "Volume sênior lido": group["volume_brl_num"].sum(),
                "Volume com CDI+": volume_with_spread,
                "CDI+ mediano EW": with_spread["spread_cdi_aa_num"].median(),
                "CDI+ ponderado volume": weighted_issue,
                "CDI+ ponderado PL atual": weighted_pl,
            }
        )
    out = pd.DataFrame(rows).merge(
        official_counts,
        left_on=["Período", "Setor", "Subtipo"],
        right_on=["pricing_period", "setor_n1", "setor_n2"],
        how="left",
    )
    out["Cobertura vs fundos oficiais"] = out["Fundos com tranche sênior"] / out["official_funds"] * 100
    return out.sort_values(["Período", "Volume sênior lido"], ascending=[True, False])


def build_pricing_anomalies(pricing: pd.DataFrame, offers: pd.DataFrame) -> pd.DataFrame:
    p = pricing.copy()
    p["volume_brl_num"] = pd.to_numeric(p.get("volume_brl_num"), errors="coerce").fillna(0)
    p["spread_cdi_aa_num"] = pd.to_numeric(p.get("spread_cdi_aa_num"), errors="coerce")
    rows = []
    sem = p[p["setor_n1"].eq("Sem oferta CVM mapeada")]
    rows.append(
        {
            "Ponto": "Sem oferta CVM mapeada",
            "Diagnóstico": f"{len(sem)} linhas de pricing/documento, {sem['cnpj'].nunique()} CNPJs e {brl(sem['volume_brl_num'].sum())} de volume extraído ficam fora do gráfico oficial porque não reconciliam com uma linha de oferta CVM 2024-2026.",
        }
    )
    pj = p[
        p["pricing_period"].eq("2024FY")
        & p["setor_n1"].eq("Crédito PJ")
        & p["setor_n2"].eq("Risco sacado/fornecedores")
        & p["tipo_cota_normalizado"].astype(str).str.contains("Sênior", na=False)
    ]
    if not pj.empty:
        sample = pj.sort_values("volume_brl_num", ascending=False).iloc[0]
        rows.append(
            {
                "Ponto": "R$ 1 mm em Crédito PJ",
                "Diagnóstico": f"Não é issuance do subtipo. É apenas a linha sênior com CDI+ extraída para {sample.get('fund_name_final') or sample.get('fundo')} ({brl(sample['volume_brl_num'])}, CDI+ {pct(sample['spread_cdi_aa_num'], 2)}).",
            }
        )
    bank = p[
        p["setor_n1"].eq("Meios de Pagamento e Cartões")
        & p["setor_n2"].eq("Bancos Emissores")
        & p["pricing_period"].isin(["2024FY", "2025FY"])
    ]
    official_bank = offers[
        offers["valid_registered"]
        & offers["audit_setor"].eq("Meios de Pagamento e Cartões")
        & offers["audit_subtipo"].eq("Bancos Emissores")
    ]
    rows.append(
        {
            "Ponto": "R$ 60 mm / Bancos Emissores",
            "Diagnóstico": f"O número pequeno vinha de filtro de tranches sênior com tipo identificado. O universo oficial CVM 2024-2026 soma {brl(official_bank['valor_brl'].sum())}; as linhas de pricing de bancos emissores somam {brl(bank['volume_brl_num'].sum())}, mas parte relevante está como tipo de cota não identificado ou sem CDI+.",
        }
    )
    pay = p[p["setor_n1"].eq("Meios de Pagamento e Cartões") & p["setor_n2"].eq("Arranjos de pagamento/adquirência")]
    rows.append(
        {
            "Ponto": "Meios de pagamento sem mediana CDI+",
            "Diagnóstico": f"Foram lidas {len(pay)} linhas e {pay['cnpj'].nunique()} CNPJs; {pay['spread_cdi_aa_num'].notna().sum()} linhas tinham CDI+ parseável. Onde a cobertura é 0%, a mediana deve ficar vazia, não virar conclusão econômica.",
        }
    )
    return pd.DataFrame(rows)


def build_participant_coverage(offers: pd.DataFrame, funds: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    valid = offers[offers["valid_registered"]].copy()
    role_cols = {
        "Coordenador líder": "nome_lider",
        "Administrador na oferta": "administrador",
        "Gestor na oferta": "gestor",
        "Custodiante na oferta": "custodiante",
    }
    coverage_rows = []
    top_rows = []
    for year, ydf in valid.groupby("year"):
        total_volume = ydf["valor_brl"].sum()
        total_funds = ydf["cnpj_emissor"].nunique()
        for role, col in role_cols.items():
            named = ydf[ydf[col].fillna("").astype(str).str.strip().ne("")]
            coverage_rows.append(
                {
                    "Ano": "2026 YTD" if int(year) == 2026 else f"{int(year)}FY",
                    "Campo": role,
                    "Fundos cobertos": named["cnpj_emissor"].nunique(),
                    "Fundos totais": total_funds,
                    "Cobertura fundos": named["cnpj_emissor"].nunique() / total_funds * 100 if total_funds else math.nan,
                    "Volume coberto": named["valor_brl"].sum(),
                    "Volume total": total_volume,
                    "Cobertura volume": named["valor_brl"].sum() / total_volume * 100 if total_volume else math.nan,
                }
            )
            top = (
                named.groupby(col, dropna=False)
                .agg(Volume=("valor_brl", "sum"), Fundos=("cnpj_emissor", "nunique"))
                .reset_index()
                .rename(columns={col: "Participante"})
                .sort_values("Volume", ascending=False)
                .head(6)
            )
            top["Ano"] = "2026 YTD" if int(year) == 2026 else f"{int(year)}FY"
            top["Papel"] = role
            top_rows.append(top)
    current_rows = []
    for role, col in {"Administrador CVM atual": "administrador", "Gestor CVM atual": "gestor", "Custodiante CVM atual": "custodiante"}.items():
        named = funds[funds[col].fillna("").astype(str).str.strip().ne("")]
        top = (
            named.groupby(col)
            .agg(Current_PL=("pl_atual_brl", "sum"), Fundos=("cnpj", "nunique"))
            .reset_index()
            .rename(columns={col: "Participante"})
            .sort_values("Current_PL", ascending=False)
            .head(8)
        )
        top["Papel"] = role
        current_rows.append(top)
    return pd.DataFrame(coverage_rows), pd.concat(top_rows, ignore_index=True), pd.concat(current_rows, ignore_index=True)


def fetch_finsiders_spotchecks(offers: pd.DataFrame) -> pd.DataFrame:
    checks = [
        ("CloudWalk", "https://finsidersbrasil.com.br/wp-json/wp/v2/search?search=CloudWalk%20FIDC&per_page=3"),
        ("Agibank", "https://finsidersbrasil.com.br/wp-json/wp/v2/search?search=Agibank%20FIDC&per_page=3"),
        ("SumUp", "https://finsidersbrasil.com.br/wp-json/wp/v2/search?search=SumUp%20FIDC&per_page=3"),
        ("iCred", "https://finsidersbrasil.com.br/wp-json/wp/v2/search?search=iCred%20FIDC&per_page=3"),
        ("Altis", "https://finsidersbrasil.com.br/wp-json/wp/v2/search?search=Altis%20FIDC&per_page=3"),
    ]
    rows = []
    haystack = (
        offers["nome_emissor"].fillna("")
        + " "
        + offers["ativos_alvo"].fillna("")
        + " "
        + offers["gestor"].fillna("")
        + " "
        + offers["administrador"].fillna("")
    ).str.upper()
    for key, url in checks:
        title = ""
        link = ""
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 FIDC strategy audit"})
            with urllib.request.urlopen(request, timeout=8) as response:
                items = json.loads(response.read().decode("utf-8"))
            if items:
                title = html.unescape(items[0].get("title", ""))
                link = items[0].get("url", "")
        except Exception:
            title = "Consulta Finsiders indisponível no momento da geração"
            link = url
        mask = haystack.str.contains(re.escape(key.upper()), na=False)
        matched = offers[mask & offers["valid_registered"]]
        rows.append(
            {
                "Caso externo": key,
                "Finsiders": title,
                "Link": link,
                "Linhas CVM encontradas": len(matched),
                "Volume CVM 2024-2026": matched["valor_brl"].sum(),
                "Status": "Reconciliado direcionalmente" if len(matched) else "Não encontrado pelo nome simples",
            }
        )
    return pd.DataFrame(rows)


def table_html(frame: pd.DataFrame, formatters: dict[str, Callable[[object], str]] | None = None, max_rows: int = 20) -> str:
    formatters = formatters or {}
    if frame.empty:
        return "<p class='empty'>Sem dados suficientes para este corte.</p>"
    data = frame.head(max_rows).copy()
    head = "".join(f"<th>{esc(col)}</th>" for col in data.columns)
    rows = []
    for _, row in data.iterrows():
        cells = []
        for col, value in row.items():
            text = formatters[col](value) if col in formatters else value
            cells.append(f"<td>{esc(text)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def card_grid(cards: list[tuple[str, str, str]]) -> str:
    items = []
    for label, value, note in cards:
        items.append(
            "<div class='kpi'>"
            f"<div class='kpi-label'>{esc(label)}</div>"
            f"<div class='kpi-value'>{esc(value)}</div>"
            f"<div class='kpi-note'>{esc(note)}</div>"
            "</div>"
        )
    return "<div class='kpi-grid'>" + "".join(items) + "</div>"


def short_label(label: object, max_len: int = 44) -> str:
    text = str(label)
    return text if len(text) <= max_len else text[: max_len - 1] + "..."


def bar_chart(frame: pd.DataFrame, label_col: str, value_col: str, title: str, color: str, max_rows: int = 14) -> str:
    data = frame[[label_col, value_col]].copy()
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data[data[value_col].notna() & (data[value_col] > 0)].head(max_rows)
    if data.empty:
        return "<p class='empty'>Sem dados para gráfico.</p>"
    width, row_h, left, right, top = 980, 30, 280, 135, 42
    plot_w = width - left - right
    height = top + row_h * len(data) + 24
    max_value = float(data[value_col].max()) or 1
    svg = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{esc(title)}'>",
        f"<text class='chart-title' x='0' y='22'>{esc(title)}</text>",
    ]
    for i, (_, row) in enumerate(data.iterrows()):
        label = row[label_col]
        value = float(row[value_col])
        y = top + i * row_h
        bar_w = max(2, plot_w * value / max_value)
        svg.extend(
            [
                f"<text class='axis-label' x='{left - 10}' y='{y + 18}' text-anchor='end'>{esc(short_label(label))}</text>",
                f"<rect x='{left}' y='{y + 5}' width='{plot_w}' height='16' rx='2' fill='#eef3f6'/>",
                f"<rect x='{left}' y='{y + 5}' width='{bar_w:.1f}' height='16' rx='2' fill='{color}'/>",
                f"<text class='value-label' x='{left + bar_w + 8:.1f}' y='{y + 18}'>{esc(brl(value))}</text>",
            ]
        )
    svg.append("</svg>")
    return "\n".join(svg)


def bar_dot_chart(frame: pd.DataFrame, label_col: str, bar_col: str, dot_col: str, title: str, dot_label: str) -> str:
    data = frame[[label_col, bar_col, dot_col]].copy()
    data[bar_col] = pd.to_numeric(data[bar_col], errors="coerce")
    data[dot_col] = pd.to_numeric(data[dot_col], errors="coerce")
    data = data[data[bar_col].notna() & (data[bar_col] > 0)].head(14)
    if data.empty:
        return "<p class='empty'>Sem dados para gráfico.</p>"
    width, row_h, left, right, top = 1010, 34, 300, 190, 54
    plot_w = width - left - right
    height = top + row_h * len(data) + 26
    max_bar = float(data[bar_col].max()) or 1
    max_dot = max(float(data[dot_col].dropna().max()) if data[dot_col].notna().any() else 1, 1)
    svg = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{esc(title)}'>",
        f"<text class='chart-title' x='0' y='22'>{esc(title)}</text>",
        f"<text class='legend' x='{left}' y='42'>Barra = volume lido | ponto = {esc(dot_label)}</text>",
    ]
    for i, (_, row) in enumerate(data.iterrows()):
        label = row[label_col]
        bar_value = float(row[bar_col])
        dot_value = row[dot_col]
        y = top + i * row_h
        bar_w = max(2, plot_w * bar_value / max_bar)
        svg.extend(
            [
                f"<text class='axis-label' x='{left - 10}' y='{y + 20}' text-anchor='end'>{esc(short_label(label))}</text>",
                f"<rect x='{left}' y='{y + 6}' width='{plot_w}' height='18' rx='2' fill='#eef3f6'/>",
                f"<rect x='{left}' y='{y + 6}' width='{bar_w:.1f}' height='18' rx='2' fill='{PALETTE['blue']}'/>",
                f"<text class='value-label' x='{left + bar_w + 8:.1f}' y='{y + 20}'>{esc(brl(bar_value))}</text>",
            ]
        )
        if not pd.isna(dot_value):
            dot_x = left + plot_w * float(dot_value) / max_dot
            svg.extend(
                [
                    f"<circle cx='{dot_x:.1f}' cy='{y + 15}' r='6' fill='{PALETTE['orange']}' stroke='white' stroke-width='2'/>",
                    f"<text class='dot-label' x='{dot_x + 9:.1f}' y='{y + 19}'>{esc(pct(dot_value, 2))}</text>",
                ]
            )
    svg.append("</svg>")
    return "\n".join(svg)


def heatmap_svg(frame: pd.DataFrame, title: str, max_rows: int = 12) -> str:
    if frame.empty:
        return "<p class='empty'>Sem dados para heatmap.</p>"
    data = frame[frame["feature_key"].isin(FEATURES_FOR_BOARD)].copy()
    data["subtipo"] = data["setor_n1"].astype(str) + " | " + data["setor_n2"].astype(str)
    top = (
        data[["subtipo", "funds"]]
        .drop_duplicates()
        .sort_values("funds", ascending=False)
        .head(max_rows)["subtipo"]
        .tolist()
    )
    data = data[data["subtipo"].isin(top)]
    features = [f for f in FEATURES_FOR_BOARD if f in data["feature_key"].unique()]
    labels = (
        data[["feature_key", "feature_label"]]
        .drop_duplicates()
        .set_index("feature_key")["feature_label"]
        .to_dict()
    )
    width = 1180
    cell_w, cell_h, left, top_px = 54, 28, 250, 74
    height = top_px + cell_h * len(top) + 210
    values = {(r["subtipo"], r["feature_key"]): r for _, r in data.iterrows()}
    svg = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{esc(title)}'>",
        f"<text class='chart-title' x='0' y='22'>{esc(title)}</text>",
        "<text class='legend' x='0' y='44'>Cor = feature_count / funds. Texto = numerador/denominador.</text>",
    ]
    for j, feature in enumerate(features):
        x = left + j * cell_w + cell_w / 2
        svg.append(
            f"<text class='heat-label' transform='translate({x:.1f},66) rotate(-55)' text-anchor='start'>{esc(short_label(labels.get(feature, feature), 18))}</text>"
        )
    for i, subtype in enumerate(top):
        y = top_px + i * cell_h
        svg.append(f"<text class='axis-label' x='{left - 10}' y='{y + 19}' text-anchor='end'>{esc(short_label(subtype, 36))}</text>")
        for j, feature in enumerate(features):
            rec = values.get((subtype, feature))
            share = float(rec["feature_share"]) * 100 if rec is not None else 0
            count = int(rec["feature_count"]) if rec is not None else 0
            funds = int(rec["funds"]) if rec is not None else 0
            alpha = 0.10 + 0.90 * min(max(share, 0), 100) / 100
            fill = f"rgba(40, 122, 116, {alpha:.2f})"
            x = left + j * cell_w
            text_color = "#ffffff" if share >= 55 else "#20303b"
            svg.extend(
                [
                    f"<rect x='{x}' y='{y}' width='{cell_w - 2}' height='{cell_h - 2}' fill='{fill}'/>",
                    f"<text class='heat-cell' x='{x + (cell_w - 2) / 2:.1f}' y='{y + 18}' text-anchor='middle' fill='{text_color}'>{count}/{funds}</text>",
                ]
            )
    svg.append("</svg>")
    return "\n".join(svg)


def subtype_deep_dive_html(heatmap: pd.DataFrame, segment_table: pd.DataFrame) -> str:
    volume_cols = ["2024 Issuance", "2025 Issuance", "2026 YTD"]
    seg = segment_table[segment_table["Segmento"].ne("Total")].copy()
    seg["volume_total"] = seg[volume_cols].sum(axis=1)
    seg = seg.sort_values("volume_total", ascending=False).head(10)
    parts = ["<div class='subtype-grid'>"]
    for _, row in seg.iterrows():
        setor = row["Segmento"]
        subtipo = row["Subtipo"]
        h = heatmap[(heatmap["setor_n1"].eq(setor)) & (heatmap["setor_n2"].eq(subtipo)) & (heatmap["emission_cohort"].eq("2025FY"))].copy()
        h = h[h["feature_key"].isin(FEATURES_FOR_BOARD)]
        common = h.sort_values("feature_share", ascending=False).head(4)
        weak = h.sort_values("feature_share", ascending=True).head(3)
        common_txt = ", ".join(f"{r.feature_label} ({pct(float(r.feature_share)*100, 0)})" for r in common.itertuples())
        weak_txt = ", ".join(f"{r.feature_label} ({pct(float(r.feature_share)*100, 0)})" for r in weak.itertuples())
        note = SUBTYPE_NOTES.get((setor, subtipo), "Subtipo ainda depende de revisão manual/documental para virar tese comercial robusta.")
        parts.append(
            "<div class='subtype-card'>"
            f"<h3>{esc(setor)} | {esc(subtipo)}</h3>"
            f"<p><strong>Como o crédito é encarteirado:</strong> {esc(note)}</p>"
            f"<p><strong>Práticas mais comuns em 2025:</strong> {esc(common_txt or '-')}</p>"
            f"<p><strong>Pontos para diligência:</strong> {esc(weak_txt or '-')}</p>"
            f"<p class='small'>Volume 2025: {esc(brl(row['2025 Issuance']))} | PL atual: {esc(brl(row['Current PL']))} | fundos: {esc(num(row['Funds']))}</p>"
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def css() -> str:
    return f"""
    <style>
    :root {{
      --ink: {PALETTE['ink']};
      --muted: {PALETTE['muted']};
      --line: {PALETTE['line']};
      --paper: {PALETTE['paper']};
      --blue: {PALETTE['blue']};
      --teal: {PALETTE['teal']};
      --orange: {PALETTE['orange']};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #f3f6f8;
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      line-height: 1.45;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 30px 26px 54px; }}
    .hero {{
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 28px 30px;
      margin-bottom: 18px;
    }}
    .kicker {{ color: var(--orange); font-size: 12px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }}
    h1 {{ margin: 8px 0 8px; font-size: 34px; line-height: 1.08; letter-spacing: 0; }}
    h2 {{ margin: 0 0 10px; font-size: 22px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 16px; }}
    p {{ margin: 0 0 10px; }}
    .subtitle {{ color: var(--muted); max-width: 900px; font-size: 15px; }}
    .stamp {{ color: var(--muted); font-size: 12px; margin-top: 14px; }}
    section {{
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px 24px;
      margin: 14px 0;
    }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 16px; }}
    .kpi {{ background: var(--paper); border: 1px solid #e6edf2; border-radius: 6px; padding: 12px; min-height: 96px; }}
    .kpi-label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; font-weight: 800; letter-spacing: .06em; }}
    .kpi-value {{ font-size: 23px; font-weight: 780; margin-top: 6px; }}
    .kpi-note {{ color: var(--muted); font-size: 12px; margin-top: 4px; }}
    .note, .small {{ color: var(--muted); font-size: 12px; }}
    .callout {{ border-left: 4px solid var(--orange); background: #fff8f3; padding: 12px 14px; margin: 10px 0; }}
    .grid-2 {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; }}
    .subtype-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .subtype-card {{ border: 1px solid #e5edf2; border-radius: 6px; padding: 13px; background: #fbfcfd; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; }}
    th {{ background: #eef3f6; color: #293744; text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }}
    th, td {{ padding: 8px 9px; border-bottom: 1px solid #e5edf2; vertical-align: top; }}
    tr:first-child td {{ font-weight: 780; background: #fbfcfd; }}
    svg {{ width: 100%; height: auto; margin: 8px 0; }}
    .chart-title {{ fill: var(--ink); font-size: 17px; font-weight: 760; }}
    .axis-label, .value-label, .dot-label, .legend, .heat-label, .heat-cell {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; }}
    .axis-label {{ fill: #334351; font-size: 11px; }}
    .value-label, .dot-label {{ fill: #334351; font-size: 11px; font-weight: 650; }}
    .legend {{ fill: var(--muted); font-size: 12px; }}
    .heat-label {{ fill: #334351; font-size: 10px; }}
    .heat-cell {{ font-size: 9px; font-weight: 750; }}
    .empty {{ color: var(--muted); font-size: 13px; }}
    ul {{ margin-top: 6px; }}
    li {{ margin-bottom: 5px; }}
    a {{ color: var(--blue); }}
    @media (max-width: 900px) {{
      main {{ padding: 18px 12px 36px; }}
      .kpi-grid, .grid-2, .subtype-grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 28px; }}
    }}
    </style>
    """


def render_report(
    metadata: dict[str, str],
    offers: pd.DataFrame,
    funds: pd.DataFrame,
    segment: pd.DataFrame,
    reconciliation: pd.DataFrame,
    heatmap: pd.DataFrame,
    pricing_coverage: pd.DataFrame,
    pricing_anomalies: pd.DataFrame,
    participant_coverage: pd.DataFrame,
    top_participants: pd.DataFrame,
    current_participants: pd.DataFrame,
    parties: pd.DataFrame,
    manual_review: pd.DataFrame,
    finsiders: pd.DataFrame,
) -> str:
    total_2025 = reconciliation.loc[reconciliation["Ano"].eq("2025FY"), "Volume CVM válido"].iloc[0]
    closed_2025 = reconciliation.loc[reconciliation["Ano"].eq("2025FY"), "Volume encerrado conservador"].iloc[0]
    classified_2025 = reconciliation.loc[reconciliation["Ano"].eq("2025FY"), "% classificado"].iloc[0]
    funds_2025 = reconciliation.loc[reconciliation["Ano"].eq("2025FY"), "Fundos/CNPJs"].iloc[0]
    pricing_2025 = pricing_coverage[pricing_coverage["Período"].eq("2025FY")]
    cards = [
        ("Emissões 2025 CVM", brl(total_2025), "Volume registrado válido; reconcilia com ~R$130 bi."),
        ("Encerrado 2025", brl(closed_2025), "Corte conservador só com ofertas encerradas."),
        ("Classificado 2025", pct(classified_2025), "Após overlay textual de oferta CVM e leitura documental."),
        ("CNPJs 2025", num(funds_2025), "Fundos/emissores únicos em ofertas válidas."),
    ]
    top_2025 = segment[segment["Segmento"].ne("Total")].copy()
    top_2025["Label"] = top_2025["Segmento"] + " | " + top_2025["Subtipo"]
    top_2025 = top_2025.sort_values("2025 Issuance", ascending=False)
    price_chart = pricing_2025.copy()
    price_chart["Label"] = price_chart["Setor"] + " | " + price_chart["Subtipo"]
    price_chart = price_chart.sort_values("Volume sênior lido", ascending=False)
    html_parts = [
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>FIDC Strategy Audit Snapshot</title>",
        css(),
        "</head><body><main>",
        "<div class='hero'>",
        "<div class='kicker'>FIDC Strategy Audit · Diretor-ready</div>",
        "<h1>Emissões, estruturas e práticas regulatórias de FIDCs desde Jan-2024</h1>",
        "<p class='subtitle'>Refazimento do snapshot com reconciliação linha a linha contra ofertas públicas CVM, leitura integral dos regulamentos cacheados para os casos materiais não classificados, cobertura explícita de pricing e limpeza dos candidatos a cedente/sacado.</p>",
        f"<div class='stamp'>Data-base do estudo: {esc(metadata.get('as_of_date', '2026-06-09'))} · Fonte primária: CVM Dados Abertos · Snapshot leve para Streamlit Cloud</div>",
        card_grid(cards),
        "</div>",
        "<section><h2>Leitura executiva</h2>",
        "<div class='callout'><strong>O número de 2025 reconciliou.</strong> A soma correta por subtipo precisa incluir a linha de Total e os casos ainda não classificados. Pelo critério CVM de volume registrado válido, 2025 soma "
        + esc(brl(total_2025))
        + ". Pelo critério mais conservador de ofertas encerradas, soma "
        + esc(brl(closed_2025))
        + ".</div>",
        "<ul>",
        "<li><strong>Issuance</strong> agora vem da tabela de ofertas CVM por ano de registro da oferta, não da coorte de nascimento do fundo. Isso corrige o descasamento que você percebeu.</li>",
        "<li><strong>PL atual</strong> é estoque atual do fundo/classe, não fluxo emitido. Ele naturalmente não bate com issuance acumulado porque há amortização, resgate, novas séries e reciclagem de carteira.</li>",
        "<li><strong>Pricing</strong> mostra apenas tranches sênior com informação extraída de documentos. Quando a cobertura CDI+ é baixa ou zero, a mediana fica vazia e não vira tese econômica.</li>",
        "<li><strong>Meios de pagamento</strong> foi separado entre risco de adquirência/arranjos e bancos emissores sempre que o texto CVM/regulamento permitiu.</li>",
        "</ul></section>",
        "<section><h2>Metodologia para diretoria</h2>",
        "<ol>",
        "<li>Baixei as ofertas públicas da CVM e usei cada linha de oferta como fonte primária de volume emitido. O critério principal é <em>volume registrado válido</em>; o critério conservador alternativo é <em>oferta encerrada</em>.</li>",
        "<li>Juntei cada CNPJ emissor ao cadastro/base de fundos da plataforma para trazer classificação, PL atual, prestadores CVM e matriz de cláusulas regulatórias.</li>",
        "<li>Quando a classificação estava ausente ou genérica, rodei uma classificação textual auditável sobre campos oficiais da oferta (<em>ativos alvo</em>, tipo de lastro, nome do emissor) e, para os maiores casos, reli integralmente os textos de regulamento cacheados.</li>",
        "<li>Para heatmaps, cada célula é <strong>feature_count / funds</strong>. Exemplo: 8/10 em subordinação significa 8 regulamentos com cláusula entre 10 regulamentos lidos naquele subtipo. As visões ponderadas por PL/volume são complementares, mas a matriz principal privilegia prática comum equal-weight.</li>",
        "<li>Para participantes, separei dois universos: prestadores/coordenadores de <strong>ofertas por ano de emissão</strong> e prestadores <strong>atuais por PL</strong>. Misturar os dois distorce a leitura comercial.</li>",
        "</ol>",
        "<p class='note'>Links-fonte usados como referência: <a href='https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/'>CVM Ofertas Públicas</a>, <a href='https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/'>CVM Informes Mensais FIDC</a>, <a href='https://www.anbima.com.br/pt_br/informar/estatisticas/mercado-de-capitais/mercado-de-capitais.htm'>ANBIMA Mercado de Capitais</a>, <a href='https://data.anbima.com.br/'>ANBIMA Data</a> e checagens jornalísticas via Finsiders.</p>",
        "</section>",
        "<section><h2>Reconciliação CVM</h2>",
        table_html(
            reconciliation,
            {
                "Volume CVM válido": brl,
                "Volume encerrado conservador": brl,
                "Volume classificado": brl,
                "% classificado": pct,
                "Ofertas CVM válidas": num,
                "Fundos/CNPJs": num,
            },
            max_rows=10,
        ),
        "<p class='note'>A diferença entre volume CVM válido e encerrado conservador explica por que fontes de mercado podem citar números próximos, mas não idênticos. O ~R$130 bi de 2025 corresponde ao registrado válido.</p>",
        "</section>",
        "<section><h2>Tabela com Total por segmento</h2>",
        bar_chart(top_2025, "Label", "2025 Issuance", "2025FY issuance por subtipo, incluindo não classificados", PALETTE["blue"], max_rows=14),
        table_html(
            segment,
            {
                "2024 Issuance": brl,
                "2025 Issuance": brl,
                "2026 YTD": brl,
                "Current PL": brl,
                "Funds": num,
            },
            max_rows=24,
        ),
        "</section>",
        "<section><h2>Heatmaps: número puro e cálculo</h2>",
        "<p>Fórmula da matriz: <strong>frequência equal-weight = feature_count / funds</strong>. A cor é esse percentual. O texto dentro da célula mostra numerador/denominador.</p>",
        heatmap_svg(heatmap[heatmap["emission_cohort"].eq("2025FY")], "2025FY · cláusulas por subtipo"),
        "<p class='note'>Exemplo de leitura: se a célula mostra 12/15 em “Elegibilidade”, 80% dos regulamentos lidos daquele subtipo possuem critério de elegibilidade identificado por texto.</p>",
        "</section>",
        "<section><h2>Deep dive por subtipo</h2>",
        subtype_deep_dive_html(heatmap, segment),
        "</section>",
        "<section><h2>Pricing: barras x CDI+ com cobertura</h2>",
        "<p>Este gráfico não é issuance total. Ele é o universo de tranches sênior com documentos de pricing extraídos. A tabela mostra cobertura contra fundos oficiais e cobertura CDI+.</p>",
        bar_dot_chart(price_chart, "Label", "Volume sênior lido", "CDI+ mediano EW", "2025FY · volume sênior lido e CDI+ mediano", "CDI+ mediano a.a."),
        table_html(
            pricing_2025.sort_values("Volume sênior lido", ascending=False),
            {
                "Tranches sênior lidas": num,
                "Fundos com tranche sênior": num,
                "Fundos com CDI+": num,
                "Cobertura CDI+ por fundo": pct,
                "Cobertura CDI+ por linha": pct,
                "Volume sênior lido": brl,
                "Volume com CDI+": brl,
                "CDI+ mediano EW": lambda x: pct(x, 2),
                "CDI+ ponderado volume": lambda x: pct(x, 2),
                "CDI+ ponderado PL atual": lambda x: pct(x, 2),
                "official_funds": num,
                "official_volume_brl": brl,
                "Cobertura vs fundos oficiais": pct,
            },
            max_rows=18,
        ),
        table_html(pricing_anomalies, max_rows=10),
        "</section>",
        "<section><h2>Participantes: cobertura e ranking</h2>",
        "<p>A decisão de apresentação é: coordenadores/administradores/gestores/custodiantes por <strong>volume de oferta no ano</strong>; prestadores atuais por <strong>PL atual</strong>. Assim a leitura comercial não mistura fluxo e estoque.</p>",
        table_html(
            participant_coverage,
            {
                "Fundos cobertos": num,
                "Fundos totais": num,
                "Cobertura fundos": pct,
                "Volume coberto": brl,
                "Volume total": brl,
                "Cobertura volume": pct,
            },
            max_rows=18,
        ),
        "<div class='grid-2'><div><h3>Top participantes por oferta</h3>"
        + table_html(
            top_participants[top_participants["Ano"].eq("2025FY")],
            {"Volume": brl, "Fundos": num},
            max_rows=18,
        )
        + "</div><div><h3>Top prestadores atuais por PL</h3>"
        + table_html(current_participants, {"Current_PL": brl, "Fundos": num}, max_rows=18)
        + "</div></div></section>",
        "<section><h2>Cedentes e sacados: extração limpa</h2>",
        "<p>Refiz a extração com filtros para endereços e captura por padrões de pessoa jurídica antes do CNPJ. Linhas como “ANDAR, CONJUNTO 202, SALA 02 PINHEIROS” e “1206, SALA 709” passam a ser rejeitadas se não houver nome empresarial válido.</p>",
        table_html(
            parties.head(30),
            {"funds": num, "evidence_rows": num, "materiality_brl": brl},
            max_rows=20,
        ),
        "</section>",
        "<section><h2>Releitura integral dos casos materiais</h2>",
        "<p>Fila priorizada por maior valor entre emissão 2024/2025/2026 e PL atual. A coluna de evidência vem do texto integral dos regulamentos cacheados, não só de metadados.</p>",
        table_html(manual_review, {"Materialidade": brl, "Docs lidos": num, "Score textual": num}, max_rows=20),
        "</section>",
        "<section><h2>Checagem externa ANBIMA/Finsiders</h2>",
        "<p>A ANBIMA publica a área de estatísticas e o ANBIMA Data, mas a base pública granular de cada oferta não ficou exposta na página estática consultada; por isso o número contábil do estudo fica ancorado na CVM. Finsiders foi usado como spot-check jornalístico de operações relevantes, não como fonte de total de mercado.</p>",
        table_html(finsiders, {"Volume CVM 2024-2026": brl, "Linhas CVM encontradas": num}, max_rows=10),
        "</section>",
        "<section><h2>What to do next executado</h2>",
        "<ul>",
        "<li><strong>1. Revisão dos maiores outliers:</strong> gerada fila de releitura integral com sugestão textual e evidência por regulamento.</li>",
        "<li><strong>2. Validação de pricing:</strong> removi a leitura inútil de preço de subscrição IME e explicitei cobertura CDI+ por linha, fundo e subtipo.</li>",
        "<li><strong>3. Cedentes/sacados:</strong> criada base limpa de partes nomeadas, rejeitando endereços e fragmentos sem nome empresarial.</li>",
        "<li><strong>4. Teses comerciais:</strong> o deep dive por subtipo traduz cláusulas comuns em ângulos de estruturação, diligência e oportunidade.</li>",
        "<li><strong>5. Visão para estrangeiro:</strong> o relatório separa fluxo/estoque, risco sacado/adquirência/banco emissor e explica por que securitização no Brasil é uma infraestrutura de funding com lastro e governança regulatória.</li>",
        "</ul>",
        "</section>",
        "</main></body></html>",
    ]
    return "\n".join(html_parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--named-parties-output", type=Path, default=DEFAULT_NAMED_PARTIES)
    parser.add_argument("--manual-review-output", type=Path, default=DEFAULT_MANUAL_REVIEW)
    args = parser.parse_args()

    if not args.db.exists():
        raise FileNotFoundError(args.db)
    offers = pd.read_csv(OFFERS_PATH, dtype={"cnpj_emissor": str})
    funds = read_sql(args.db, "fund_universe")
    heatmap = read_sql(args.db, "regulatory_feature_heatmap_year")
    pricing = read_sql(args.db, "pricing_tranche_enriched")
    candidates = read_sql(args.db, "cedentes_sacados_candidates")
    metadata = read_metadata(args.db)

    for col in [
        "valid_volume_2024_brl",
        "valid_volume_2025_brl",
        "valid_volume_2026_brl",
        "pl_atual_brl",
        "offers_2024",
        "offers_2025",
        "offers_2026",
    ]:
        funds[col] = pd.to_numeric(funds.get(col), errors="coerce").fillna(0)

    offers = enrich_offers_with_audit_classification(offers, funds)
    segment = build_segment_table(offers, funds)
    reconciliation = build_reconciliation(offers)
    manual_review = build_manual_reclassification(funds)
    parties = build_clean_named_parties(candidates, funds)
    pricing_coverage = build_pricing_coverage(pricing, offers)
    pricing_anomalies = build_pricing_anomalies(pricing, offers)
    participant_coverage, top_participants, current_participants = build_participant_coverage(offers, funds)
    finsiders = fetch_finsiders_spotchecks(offers)

    args.named_parties_output.parent.mkdir(parents=True, exist_ok=True)
    parties.to_csv(args.named_parties_output, index=False)
    manual_review.to_csv(args.manual_review_output, index=False)

    html_report = render_report(
        metadata=metadata,
        offers=offers,
        funds=funds,
        segment=segment,
        reconciliation=reconciliation,
        heatmap=heatmap,
        pricing_coverage=pricing_coverage,
        pricing_anomalies=pricing_anomalies,
        participant_coverage=participant_coverage,
        top_participants=top_participants,
        current_participants=current_participants,
        parties=parties,
        manual_review=manual_review,
        finsiders=finsiders,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_report, encoding="utf-8")
    print(f"Wrote {args.output} ({args.output.stat().st_size:,} bytes)")
    print(f"Wrote {args.named_parties_output} ({len(parties):,} rows)")
    print(f"Wrote {args.manual_review_output} ({len(manual_review):,} rows)")


if __name__ == "__main__":
    main()
