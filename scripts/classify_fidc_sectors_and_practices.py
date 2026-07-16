from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


DEFAULT_INPUT_DIR = Path("outputs/fidc_issuance_study_20260609")
DEFAULT_OUTPUT_DIR = Path("outputs/fidc_classification_practices_20260609")
CRITERIA_PATH = Path("data/regulatory_profiles/all_fidcs_criteria_monitoraveis_ime.csv")
OFFER_ID_COLUMNS = ["source_dataset", "offer_id", "numero_processo", "numero_requerimento"]


@dataclass(frozen=True)
class Classification:
    setor_n1: str
    setor_n2: str
    confidence: str
    evidence: str
    rule_id: str


@dataclass(frozen=True)
class ClassificationRule:
    rule_id: str
    setor_n1: str
    setor_n2: str
    patterns: tuple[str, ...]
    priority: int


RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(
        "fiagro_or_agro",
        "Agro",
        "Agro",
        (
            r"\bFIAGRO\b",
            r"AGRONEGOCIO",
            r"AGRONEGOCIO",
            r"CADEIAS PRODUTIVAS DO AGRONEGOCIO",
            r"\bAGRO\b",
            r"PRODUTOR(?:ES)? RURAL",
            r"CEDULA DE PRODUTO RURAL",
            r"\bCPR\b",
            r"INSUMOS AGRICOLAS",
            r"SAFRA",
        ),
        100,
    ),
    ClassificationRule(
        "card_issuer_banks",
        "Meios de Pagamento e Cartões",
        "Bancos Emissores",
        (
            r"BANCOS EMISSORES",
            r"EMISSORES DE CARTAO",
            r"BANCO EMISSOR",
            r"RECEBIVEIS DE CARTAO",
            r"CARTAO DE CREDITO",
            r"CARTAO DE COMPRA",
            r"\bIBCB\b",
        ),
        95,
    ),
    ClassificationRule(
        "payment_arrangements",
        "Meios de Pagamento e Cartões",
        "Arranjos de pagamento/adquirência",
        (
            r"MEIOS DE PAGAMENTO",
            r"ARRANJOS DE PAGAMENTO",
            r"TRANSACOES DE PAGAMENTO",
            r"INSTRUMENTOS DE PAGAMENTO",
            r"ESTABELECIMENTOS CREDENCIADOS",
            r"\bADQUIRENCIA\b",
            r"\bCLOUDWALK\b",
            r"\bPAGSEGURO\b",
            r"\bSUMUP\b",
            r"\bSELLER\b",
        ),
        92,
    ),
    ClassificationRule(
        "fgts",
        "Crédito PF",
        "FGTS",
        (
            r"\bFGTS\b",
            r"ANTECIPACAO DE FGTS",
            r"SAQUE ANIVERSARIO",
        ),
        90,
    ),
    ClassificationRule(
        "payroll_inss_public_private",
        "Crédito PF",
        "Consignado/INSS",
        (
            r"\bINSS\b",
            r"CONSIGNADO",
            r"CONSIGNADOS",
            r"CARTAO INSS",
            r"CONSIGNADO PRIVADO",
            r"CONSIGNADOS ESTADUAIS",
        ),
        88,
    ),
    ClassificationRule(
        "auto_loans",
        "Crédito PF",
        "Auto/Veículos",
        (
            r"\bAUTO\b",
            r"VEICULO",
            r"VEICULOS",
            r"ALIENACAO FIDUCIARIA DE VEICULO",
            r"FINANCIAMENTO DE VEICULOS",
            r"\bCREDITAS AUTO\b",
            r"BANCO VOLKSWAGEN",
            r"\bSTELLANTIS\b",
        ),
        86,
    ),
    ClassificationRule(
        "student_credit",
        "Crédito PF",
        "Crédito estudantil",
        (
            r"CREDITO UNIVERSITARIO",
            r"SERVICOS EDUCACIONAIS",
            r"FINANCIAMENTO DE SERVICOS EDUCACIONAIS",
            r"INSTITUICOES DE ENSINO",
            r"\bALUNOS\b",
        ),
        84,
    ),
    ClassificationRule(
        "consumer_credit",
        "Crédito PF",
        "Crédito pessoal/consumo",
        (
            r"EMPRESTIMOS PESSOAIS",
            r"CREDITO PESSOAL",
            r"PESSOA NATURAL",
            r"PESSOAS NATURAIS",
            r"CONSUMIDOR",
        ),
        80,
    ),
    ClassificationRule(
        "sacado_fornecedores",
        "Crédito PJ",
        "Risco sacado/fornecedores",
        (
            r"RISCO SACADO",
            r"FORNECEDORES",
            r"FORNECEDOR",
            r"SUPPLY",
            r"SUPPLIER",
            r"VENDA DE PRODUTOS OU NA PRESTACAO DE SERVICOS",
            r"DUPLICATAS",
            r"CHEQUES",
            r"MULTI CEDENTES COM MULTI SACADOS",
            r"MULTI SACADOS",
            r"SACADOS",
        ),
        78,
    ),
    ClassificationRule(
        "pj_ccb_notas_comerciais",
        "Crédito PJ",
        "CCB/Notas comerciais/Capital de giro",
        (
            r"NOTAS COMERCIAIS",
            r"\bCCB\b",
            r"CEDULAS DE CREDITO BANCARIO",
            r"CAPITAL DE GIRO",
            r"CLIENTES PESSOA JURIDICA",
            r"PESSOAS JURIDICAS",
        ),
        75,
    ),
    ClassificationRule(
        "receivables_commercial_multisector",
        "Crédito PJ",
        "Recebíveis comerciais/multissetorial",
        (
            r"MULTISSETORIAL",
            r"MULTISETORIAL",
            r"MULTICARTEIRA",
            r"RECEBIVEIS COMERCIAIS",
            r"SEGMENTOS FINANCEIRO, COMERCIAL, INDUSTRIAL",
            r"COMERCIAL, INDUSTRIAL",
            r"PRESTACAO DE SERVICOS",
            r"CREDITO MERCANTIL",
            r"INDUSTRIA PETROQUIMICA",
            r"CREDITO CORPORATIVO",
        ),
        70,
    ),
    ClassificationRule(
        "real_estate",
        "Imobiliário",
        "Imobiliário",
        (
            r"IMOBILIARIO",
            r"HIPOTEC",
            r"INCORPORACAO",
            r"LOTEAMENTO",
            r"CONTRATOS DE COMPRA E VENDA DE IMOVEIS",
        ),
        68,
    ),
    ClassificationRule(
        "judicial_precatorios",
        "Judicial/Precatórios/NPL",
        "Precatórios/direitos judiciais",
        (
            r"PRECATORIO",
            r"PRECATORIOS",
            r"PRE-PRECATORIO",
            r"\bRPV\b",
            r"LEGAL CLAIMS",
            r"DIREITOS CREDITORIOS JUDICIAIS",
            r"PROCESSOS AINDA EM TRAMITE",
            r"ACOES JUDICIAIS",
            r"\bPJUS\b",
        ),
        66,
    ),
    ClassificationRule(
        "npl_np",
        "Judicial/Precatórios/NPL",
        "Não padronizado/NPL",
        (
            r"NAO PADRONIZADO",
            r"NAO-PADRONIZADO",
            r"\bFIDC NP\b",
            r"NPL",
            r"NON PERFORMING",
            r"INADIMPLIDOS",
        ),
        55,
    ),
    ClassificationRule(
        "energy_infra",
        "Infra/Energia",
        "Energia/infra",
        (
            r"ENERGIA",
            r"ENERGY",
            r"INFRA",
            r"SANEAMENTO",
            r"ILUMINACAO PUBLICA",
        ),
        50,
    ),
    ClassificationRule(
        "fic_fidc",
        "FIC/Alocador",
        "FIC de FIDC",
        (
            r"FIC FIDC",
            r"FUNDO DE INVESTIMENTO EM COTAS",
            r"FIC DE FIDC",
            r"FIC DE FUNDOS DE INVESTIMENTO EM DIREITOS CREDITORIOS",
        ),
        20,
    ),
)


def only_digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def normalize_text(value: object) -> str:
    text = str(value or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    text = re.sub(r"[^A-Z0-9%$+.,/\- ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def format_brl(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"R$ {float(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def parse_percent(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    if not match:
        return None
    return float(match.group(1).replace(".", "").replace(",", "."))


def extract_percentages(value: object) -> list[float]:
    text = str(value or "")
    percentages = []
    for match in re.finditer(r"(\d{1,3}(?:[.,]\d+)?)\s*%", text):
        try:
            percentages.append(float(match.group(1).replace(".", "").replace(",", ".")))
        except ValueError:
            continue
    return percentages


def classify_texts(source_texts: dict[str, object]) -> Classification:
    normalized_sources = {key: normalize_text(value) for key, value in source_texts.items()}
    best: tuple[int, ClassificationRule, str, str] | None = None
    for rule in RULES:
        for source, text in normalized_sources.items():
            if not text:
                continue
            for pattern in rule.patterns:
                if re.search(pattern, text):
                    source_score = {
                        "valor_mobiliario": 40,
                        "ativos_alvo": 35,
                        "descricao_lastro": 35,
                        "tipo_lastro": 15,
                        "fundo": 22,
                        "nome_emissor": 20,
                        "nome_fundo": 20,
                        "observacao_tecnica": 10,
                    }.get(source, 10)
                    score = rule.priority + source_score
                    if best is None or score > best[0]:
                        best = (score, rule, source, pattern)
    if best is None:
        return Classification(
            setor_n1="Não classificado",
            setor_n2="Revisar manualmente",
            confidence="baixa",
            evidence="Sem regra setorial acionada por metadados disponíveis.",
            rule_id="unclassified",
        )
    score, rule, source, pattern = best
    confidence = "alta" if source in {"valor_mobiliario", "ativos_alvo", "descricao_lastro"} else "media"
    if source == "observacao_tecnica":
        confidence = "media"
    return Classification(
        setor_n1=rule.setor_n1,
        setor_n2=rule.setor_n2,
        confidence=confidence,
        evidence=f"{source}: regex `{pattern}`",
        rule_id=rule.rule_id,
    )


def classify_offers(offers: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in offers.iterrows():
        classification = classify_texts(
            {
                "valor_mobiliario": row.get("valor_mobiliario", ""),
                "ativos_alvo": row.get("ativos_alvo", ""),
                "descricao_lastro": row.get("descricao_lastro", ""),
                "tipo_lastro": row.get("tipo_lastro", ""),
                "nome_emissor": row.get("nome_emissor", ""),
            }
        )
        rows.append(classification.__dict__)
    output = offers.copy()
    class_df = pd.DataFrame(rows)
    for column in class_df.columns:
        output[column] = class_df[column].values
    return output


def issuer_classification(classified_offers: pd.DataFrame) -> pd.DataFrame:
    rows = []
    confidence_rank = {"alta": 3, "media": 2, "baixa": 1}
    for cnpj, group in classified_offers.groupby("cnpj_emissor", dropna=False):
        group = group.copy()
        group["valor_total_registrado"] = pd.to_numeric(group["valor_total_registrado"], errors="coerce").fillna(0)
        grouped = (
            group.groupby(["setor_n1", "setor_n2", "rule_id"], dropna=False)
            .agg(
                linhas_oferta=("offer_id", "count"),
                volume_total=("valor_total_registrado", "sum"),
                max_confidence=("confidence", lambda x: max(x, key=lambda y: confidence_rank.get(y, 0))),
                evidence=("evidence", lambda x: " | ".join(sorted(set(map(str, x)))[:3])),
            )
            .reset_index()
        )
        grouped["confidence_score"] = grouped["max_confidence"].map(confidence_rank).fillna(0)
        grouped = grouped.sort_values(
            ["confidence_score", "linhas_oferta", "volume_total"],
            ascending=[False, False, False],
        )
        winner = grouped.iloc[0]
        first = group.iloc[0]
        rows.append(
            {
                "cnpj_emissor": cnpj,
                "nome_emissor": first.get("nome_emissor", ""),
                "setor_n1": winner["setor_n1"],
                "setor_n2": winner["setor_n2"],
                "confidence": winner["max_confidence"],
                "classification_evidence": winner["evidence"],
                "rule_id": winner["rule_id"],
                "linhas_oferta": int(len(group)),
                "volume_total_registrado": float(group["valor_total_registrado"].sum()),
                "volume_encerrado_conservador": float(
                    group.loc[group["volume_encerrado_conservador_flag"].astype(str).eq("True"), "valor_total_registrado"].sum()
                ),
                "platform_coverage_level": first.get("platform_coverage_level", ""),
            }
        )
    return pd.DataFrame(rows).sort_values(["setor_n1", "setor_n2", "volume_total_registrado"], ascending=[True, True, False])


def sector_summaries(classified_offers: pd.DataFrame, issuers: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    offers = classified_offers.copy()
    offers["valor_total_registrado"] = pd.to_numeric(offers["valor_total_registrado"], errors="coerce").fillna(0)
    closed = offers["volume_encerrado_conservador_flag"].astype(str).eq("True")
    valid = offers["volume_registrado_valido_flag"].astype(str).eq("True")
    rows = []
    for keys, group in offers.groupby(["setor_n1", "setor_n2"], dropna=False):
        mask = group.index
        group_closed = group.loc[closed.loc[mask]]
        group_valid = group.loc[valid.loc[mask]]
        rows.append(
            {
                "setor_n1": keys[0],
                "setor_n2": keys[1],
                "linhas_oferta": int(len(group)),
                "emissores_unicos": int(group["cnpj_emissor"].nunique()),
                "ofertas_encerradas_linhas": int(len(group_closed)),
                "volume_registrado_valido_ou_aberto": float(group_valid["valor_total_registrado"].sum()),
                "volume_encerrado_conservador": float(group_closed["valor_total_registrado"].sum()),
                "ticket_mediano_oferta": float(group["valor_total_registrado"].median()) if len(group) else None,
                "share_conf_alta": float((group["confidence"] == "alta").mean()) if len(group) else None,
            }
        )
    sector_summary = pd.DataFrame(rows).sort_values("volume_registrado_valido_ou_aberto", ascending=False)

    issuer_rows = []
    for keys, group in issuers.groupby(["setor_n1", "setor_n2"], dropna=False):
        issuer_rows.append(
            {
                "setor_n1": keys[0],
                "setor_n2": keys[1],
                "emissores_unicos_equal_weight": int(len(group)),
                "volume_total_registrado": float(group["volume_total_registrado"].sum()),
                "volume_encerrado_conservador": float(group["volume_encerrado_conservador"].sum()),
                "ticket_mediano_por_emissor": float(group["volume_total_registrado"].median()) if len(group) else None,
                "share_conf_alta": float((group["confidence"] == "alta").mean()) if len(group) else None,
            }
        )
    issuer_summary = pd.DataFrame(issuer_rows).sort_values("emissores_unicos_equal_weight", ascending=False)
    return sector_summary, issuer_summary


def load_criteria(criteria_path: Path) -> pd.DataFrame:
    criteria = pd.read_csv(criteria_path, dtype=str, keep_default_na=False)
    criteria["cnpj_digits"] = criteria["CNPJ"].map(only_digits)
    criteria["percent_value"] = criteria["Limite/regra"].map(parse_percent)
    criteria["all_percent_values_from_observation"] = criteria["Observação técnica"].map(
        lambda value: ";".join(f"{pct:g}" for pct in extract_percentages(value))
    )
    criteria["rule_text"] = criteria["Limite/regra"].map(clean_text)
    return criteria


def normalize_subordination_row(row: pd.Series) -> tuple[float | None, str]:
    pct = row.get("percent_value")
    if pct is None or pd.isna(pct):
        return None, "sem_percentual_parseavel"
    pct_float = float(pct)
    if pct_float <= 100:
        return pct_float, "percentual_direto"
    observation_pcts = extract_percentages(row.get("Observação técnica", ""))
    plausible = [value for value in observation_pcts if 0 < value <= 100 and abs(value - pct_float) > 0.01]
    if plausible:
        return plausible[0], f"normalizado_de_razao_maior_que_100_para_{plausible[0]:g}%_por_observacao"
    return pct_float, "razao_maior_que_100_sem_normalizacao"


def is_subordination_common_level_valid(row: pd.Series) -> bool:
    if row.get("Chave") != "subordination_ratio_min":
        return False
    pct = row.get("subordination_pct_normalized")
    if pct is None or pd.isna(pct):
        return False
    observation = normalize_text(row.get("Observação técnica", ""))
    if "CURSOS DE MEDICINA" in observation and "DIREITOS CREDITORIOS" in observation:
        return False
    if "INDICE DE COBERTURA SENIOR" in observation:
        return False
    if float(pct) > 60 and not ("PATRIMONIO LIQUIDO" in observation and "COTAS SUBORDINADAS" in observation):
        return False
    return True


def classify_practice_funds(criteria: pd.DataFrame, issuer_map: pd.DataFrame) -> pd.DataFrame:
    issuer_lookup = issuer_map.set_index("cnpj_emissor").to_dict(orient="index")
    rows = []
    for _, row in criteria.iterrows():
        cnpj = row["cnpj_digits"]
        if cnpj in issuer_lookup:
            base = issuer_lookup[cnpj]
            classification = Classification(
                setor_n1=base["setor_n1"],
                setor_n2=base["setor_n2"],
                confidence=base["confidence"],
                evidence=base["classification_evidence"],
                rule_id=base["rule_id"],
            )
        else:
            classification = classify_texts(
                {
                    "fundo": row.get("Fundo", ""),
                    "observacao_tecnica": row.get("Observação técnica", ""),
                }
            )
        rows.append(classification.__dict__)
    out = criteria.copy()
    class_df = pd.DataFrame(rows)
    for column in class_df.columns:
        out[column] = class_df[column].values
    normalized = out.apply(normalize_subordination_row, axis=1)
    out["subordination_pct_normalized"] = [value for value, _ in normalized]
    out["subordination_normalization_note"] = [note for _, note in normalized]
    out["subordination_valid_for_common_level"] = out.apply(is_subordination_common_level_valid, axis=1)
    return out


def practice_prevalence(practices: pd.DataFrame) -> pd.DataFrame:
    fund_sector = practices[["cnpj_digits", "Fundo", "setor_n1", "setor_n2"]].drop_duplicates()
    denom = (
        fund_sector.groupby(["setor_n1", "setor_n2"], dropna=False)["cnpj_digits"]
        .nunique()
        .rename("fundos_curados_no_setor")
        .reset_index()
    )
    with_key = practices[practices["Chave"].astype(str).str.strip() != ""].copy()
    counts = (
        with_key.drop_duplicates(["cnpj_digits", "setor_n1", "setor_n2", "Chave"])
        .groupby(["setor_n1", "setor_n2", "Chave"], dropna=False)["cnpj_digits"]
        .nunique()
        .rename("fundos_com_pratica_extraida")
        .reset_index()
    )
    out = counts.merge(denom, on=["setor_n1", "setor_n2"], how="left")
    out["share_fundos_curados"] = out["fundos_com_pratica_extraida"] / out["fundos_curados_no_setor"].replace(0, pd.NA)
    return out.sort_values(["setor_n1", "setor_n2", "fundos_com_pratica_extraida"], ascending=[True, True, False])


def subordination_by_fund(practices: pd.DataFrame) -> pd.DataFrame:
    sub = practices[
        (practices["Chave"] == "subordination_ratio_min")
        & practices["subordination_pct_normalized"].notna()
        & practices["subordination_valid_for_common_level"].astype(bool)
    ].copy()
    if sub.empty:
        return pd.DataFrame()
    rows = []
    for (cnpj, setor_n1, setor_n2), group in sub.groupby(["cnpj_digits", "setor_n1", "setor_n2"], dropna=False):
        values = sorted(float(value) for value in group["subordination_pct_normalized"].dropna())
        rows.append(
            {
                "cnpj": cnpj,
                "fundo": group.iloc[0]["Fundo"],
                "setor_n1": setor_n1,
                "setor_n2": setor_n2,
                "subordination_main_pct_max": max(values),
                "subordination_min_pct": min(values),
                "subordination_threshold_count": len(values),
                "subordination_all_thresholds_pct": ";".join(f"{value:g}" for value in values),
                "sources": " | ".join(sorted(set(group["Fonte"].astype(str)))[:5]),
                "normalization_notes": " | ".join(sorted(set(group["subordination_normalization_note"].astype(str)))),
            }
        )
    return pd.DataFrame(rows).sort_values(["setor_n1", "setor_n2", "subordination_main_pct_max"])


def common_value_bins(values: Iterable[float]) -> str:
    bins: dict[str, int] = {}
    for value in values:
        rounded = round(float(value) * 2) / 2
        label = f"{rounded:g}%"
        bins[label] = bins.get(label, 0) + 1
    return "; ".join(f"{label} ({count})" for label, count in sorted(bins.items(), key=lambda item: (-item[1], item[0]))[:8])


def subordination_summary(sub_by_fund: pd.DataFrame) -> pd.DataFrame:
    if sub_by_fund.empty:
        return pd.DataFrame()
    rows = []
    for keys, group in sub_by_fund.groupby(["setor_n1", "setor_n2"], dropna=False):
        values = group["subordination_main_pct_max"].astype(float)
        rows.append(
            {
                "setor_n1": keys[0],
                "setor_n2": keys[1],
                "fundos_com_subordinacao": int(len(group)),
                "subordinacao_mediana_pct_equal_weight": float(values.median()),
                "subordinacao_p25_pct": float(values.quantile(0.25)),
                "subordinacao_p75_pct": float(values.quantile(0.75)),
                "subordinacao_min_pct": float(values.min()),
                "subordinacao_max_pct": float(values.max()),
                "valores_mais_comuns_arred_0_5pp": common_value_bins(values),
            }
        )
    return pd.DataFrame(rows).sort_values("fundos_com_subordinacao", ascending=False)


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def write_summary_md(
    output_dir: Path,
    offer_sector_summary: pd.DataFrame,
    issuer_sector_summary: pd.DataFrame,
    sub_summary: pd.DataFrame,
    prevalence: pd.DataFrame,
    classified_offers: pd.DataFrame,
    practices: pd.DataFrame,
) -> None:
    lines = [
        "# Classificação setorial e práticas de regulamento de FIDCs",
        "",
        f"Gerado em UTC: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Escopo",
        "",
        f"- Ofertas classificadas: {len(classified_offers):,}.",
        f"- Emissores únicos classificados: {classified_offers['cnpj_emissor'].nunique():,}.",
        f"- Fundos com critérios regulatórios locais: {practices['cnpj_digits'].nunique():,}.",
        "",
        "## Método",
        "",
        "- Classificação setorial: regras auditáveis sobre `valor_mobiliario`, `ativos_alvo`, `descricao_lastro` e `nome_emissor`.",
        "- Confiança alta: regra acionada por campo CVM de ativo/lastro. Confiança média: regra acionada por nome ou texto regulatório local. Confiança baixa: sem regra.",
        "- Práticas regulatórias: amostra documental local em `data/regulatory_profiles/all_fidcs_criteria_monitoraveis_ime.csv`; resultados são equal-weight por fundo.",
        "- Subordinação: quando o extrator capturou uma razão maior que 100% mas a observação trazia o percentual de PL subordinado, o script normalizou para o percentual de PL.",
        "",
        "## Setores por emissores",
        "",
        "| Setor | Subsetor | Emissores | Volume registrado | Volume encerrado | Conf. alta |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for _, row in issuer_sector_summary.head(18).iterrows():
        lines.append(
            "| {setor_n1} | {setor_n2} | {emissores:,} | {volume} | {closed} | {conf:.0%} |".format(
                setor_n1=row["setor_n1"],
                setor_n2=row["setor_n2"],
                emissores=int(row["emissores_unicos_equal_weight"]),
                volume=format_brl(row["volume_total_registrado"]),
                closed=format_brl(row["volume_encerrado_conservador"]),
                conf=float(row["share_conf_alta"] or 0),
            )
        )
    lines.extend(
        [
            "",
            "## Subordinação por setor",
            "",
            "| Setor | Subsetor | Fundos | Mediana | P25 | P75 | Valores comuns |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for _, row in sub_summary.head(18).iterrows():
        lines.append(
            "| {setor_n1} | {setor_n2} | {fundos:,} | {median:g}% | {p25:g}% | {p75:g}% | {common} |".format(
                setor_n1=row["setor_n1"],
                setor_n2=row["setor_n2"],
                fundos=int(row["fundos_com_subordinacao"]),
                median=float(row["subordinacao_mediana_pct_equal_weight"]),
                p25=float(row["subordinacao_p25_pct"]),
                p75=float(row["subordinacao_p75_pct"]),
                common=row["valores_mais_comuns_arred_0_5pp"],
            )
        )
    lines.extend(
        [
            "",
            "## Arquivos",
            "",
            "- `fidc_offer_sector_classification.csv`: classificação linha a linha das ofertas.",
            "- `fidc_issuer_sector_classification.csv`: classificação consolidada por emissor.",
            "- `fidc_manual_review_queue_unclassified_issuers.csv`: emissores ainda sem classificação, ordenados por volume.",
            "- `fidc_sector_summary_equal_weight.csv`: resumo por setor via contagem de emissores.",
            "- `fidc_regulatory_practices_long.csv`: critérios regulatórios extraídos, com setor.",
            "- `fidc_subordination_by_fund.csv`: subordinação principal por fundo curado.",
            "- `fidc_subordination_summary_by_sector.csv`: distribuição equal-weight de subordinação por setor.",
            "- `fidc_practice_prevalence_by_sector.csv`: prevalência de práticas extraídas por setor.",
        ]
    )
    (output_dir / "classification_practices_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify FIDC sectors and summarize local regulatory practices.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--criteria-csv", default=str(CRITERIA_PATH))
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    offers = pd.read_csv(input_dir / "fidc_public_offers_2024_2026ytd.csv", dtype=str, keep_default_na=False)
    offers["valor_total_registrado"] = pd.to_numeric(offers["valor_total_registrado"], errors="coerce")

    classified_offers = classify_offers(offers)
    issuers = issuer_classification(classified_offers)
    offer_sector_summary, issuer_sector_summary = sector_summaries(classified_offers, issuers)

    criteria = load_criteria(Path(args.criteria_csv))
    practices = classify_practice_funds(criteria, issuers)
    prevalence = practice_prevalence(practices)
    sub_fund = subordination_by_fund(practices)
    sub_summary = subordination_summary(sub_fund)

    write_csv(classified_offers, output_dir / "fidc_offer_sector_classification.csv")
    write_csv(issuers, output_dir / "fidc_issuer_sector_classification.csv")
    write_csv(
        issuers[issuers["setor_n1"].eq("Não classificado")].sort_values("volume_total_registrado", ascending=False),
        output_dir / "fidc_manual_review_queue_unclassified_issuers.csv",
    )
    write_csv(offer_sector_summary, output_dir / "fidc_sector_summary_by_offer.csv")
    write_csv(issuer_sector_summary, output_dir / "fidc_sector_summary_equal_weight.csv")
    write_csv(practices, output_dir / "fidc_regulatory_practices_long.csv")
    write_csv(prevalence, output_dir / "fidc_practice_prevalence_by_sector.csv")
    write_csv(sub_fund, output_dir / "fidc_subordination_by_fund.csv")
    write_csv(sub_summary, output_dir / "fidc_subordination_summary_by_sector.csv")

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "offers_classified": int(len(classified_offers)),
        "issuers_classified": int(issuers["cnpj_emissor"].nunique()),
        "curated_practice_funds": int(practices["cnpj_digits"].nunique()),
        "curated_subordination_funds": int(sub_fund["cnpj"].nunique()) if not sub_fund.empty else 0,
        "top_equal_weight_sectors": issuer_sector_summary.head(20).to_dict(orient="records"),
        "subordination_summary": sub_summary.to_dict(orient="records") if not sub_summary.empty else [],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_summary_md(output_dir, offer_sector_summary, issuer_sector_summary, sub_summary, prevalence, classified_offers, practices)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
