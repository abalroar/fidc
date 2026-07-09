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

REVIEW_AUDIT_COLUMNS = [
    "event_id",
    "saved_at_utc",
    "review_domain",
    "record_id",
    "field",
    "old_value",
    "new_value",
    "status_after",
    "source",
]

MONTHLY_DELTA_ACTION_COLUMNS = [
    "delta_id",
    "status_acao",
    "acao_revisada",
    "responsavel",
    "prazo",
    "notas",
    "updated_at_utc",
]

DOCUMENT_CHUNK_ACTION_COLUMNS = [
    "chunk_id",
    "status_lote",
    "acao_revisada",
    "responsavel",
    "prazo",
    "notas",
    "updated_at_utc",
]

PUBLICATION_GATE_COLUMNS = [
    "gate_id",
    "ordem",
    "tipo_sinal",
    "frente",
    "status_gate",
    "decisao_publicacao",
    "bloqueia_publicacao",
    "exige_nota_publica",
    "pendencias",
    "evidencia",
    "acao_sugerida",
    "fonte",
    "comando",
    "competencia_referencia",
]

SNAPSHOT_GAP_ACTION_COLUMNS = [
    "gap_id",
    "status_lacuna",
    "acao_revisada",
    "responsavel",
    "prazo",
    "notas",
    "updated_at_utc",
]

CATALOG_GAP_ACTION_COLUMNS = [
    "traceability_gap_id",
    "status_lacuna",
    "acao_revisada",
    "responsavel",
    "prazo",
    "notas",
    "updated_at_utc",
]

MANUAL_REVIEW_LEDGER_SPECS = [
    {
        "domain_id": "cedente_review",
        "label": "Cedentes/sacados",
        "module_id": "cedentes",
        "action_file": "cedente_reviews.csv",
        "audit_file": "cedente_review_audit.csv",
        "key_column": "review_id",
        "status_column": "status",
        "ui_surface": "Cedentes",
        "comparison": "participante extraído × nome/CNPJ/setor revisado",
        "rerun_command": "python scripts/build_fidc_industry_cedentes.py",
        "action_columns": CEDENTE_REVIEW_COLUMNS,
    },
    {
        "domain_id": "criteria_review",
        "label": "Critérios e subordinação",
        "module_id": "criteria",
        "action_file": "criteria_reviews.csv",
        "audit_file": "criteria_review_audit.csv",
        "key_column": "rule_id",
        "status_column": "status",
        "ui_surface": "Critérios",
        "comparison": "critério/regra automática × regra revisada",
        "rerun_command": "python scripts/build_fidc_industry_criteria.py",
        "action_columns": CRITERIA_REVIEW_COLUMNS,
    },
    {
        "domain_id": "monthly_delta_action",
        "label": "Delta mensal",
        "module_id": "monthly_delta",
        "action_file": "monthly_delta_actions.csv",
        "audit_file": "monthly_delta_action_audit.csv",
        "key_column": "delta_id",
        "status_column": "status_acao",
        "ui_surface": "Pipeline > Delta mensal",
        "comparison": "delta automático × ação revisada",
        "rerun_command": "python scripts/build_fidc_industry_monthly_delta.py",
        "action_columns": MONTHLY_DELTA_ACTION_COLUMNS,
    },
    {
        "domain_id": "document_chunk_action",
        "label": "Chunks documentais",
        "module_id": "documents",
        "action_file": "document_chunk_actions.csv",
        "audit_file": "document_chunk_action_audit.csv",
        "key_column": "chunk_id",
        "status_column": "status_lote",
        "ui_surface": "Documentos",
        "comparison": "chunk planejado × acompanhamento revisado",
        "rerun_command": "python scripts/build_fidc_industry_document_chunk_plan.py",
        "action_columns": DOCUMENT_CHUNK_ACTION_COLUMNS,
    },
    {
        "domain_id": "snapshot_gap",
        "label": "Lacunas do snapshot",
        "module_id": "fund_snapshot",
        "action_file": "snapshot_gap_actions.csv",
        "audit_file": "snapshot_gap_action_audit.csv",
        "key_column": "gap_id",
        "status_column": "status_lacuna",
        "ui_surface": "Base granular",
        "comparison": "lacuna automática × decisão manual",
        "rerun_command": "python scripts/build_fidc_industry_fund_snapshot.py",
        "action_columns": SNAPSHOT_GAP_ACTION_COLUMNS,
    },
    {
        "domain_id": "dimension_catalog_gap",
        "label": "Rastreabilidade do catálogo",
        "module_id": "dimension_catalog",
        "action_file": "dimension_catalog_gap_actions.csv",
        "audit_file": "dimension_catalog_gap_action_audit.csv",
        "key_column": "traceability_gap_id",
        "status_column": "status_lacuna",
        "ui_surface": "Pipeline > Qualidade catálogo",
        "comparison": "campo faltante × decisão manual",
        "rerun_command": "python scripts/build_fidc_industry_dimensions.py",
        "action_columns": CATALOG_GAP_ACTION_COLUMNS,
    },
]

PUBLIC_CLAIM_SPECS = [
    {
        "claim_id": "anbima_fidc_net_flow_2025_jan_sep",
        "source_name": "ANBIMA",
        "source_title": "Indústria de fundos registra captação líquida de R$ 110,9 bilhões no ano até setembro",
        "source_url": "https://www.anbima.com.br/pt_br/noticias/industria-de-fundos-registra-captacao-liquida-de-r-110-9-bilhoes-no-ano-ate-setembro.htm",
        "published_at": "2025-10-07",
        "metric_group": "captação líquida",
        "claim_text": "FIDCs captaram R$ 63,0 bi entre janeiro e setembro de 2025.",
        "period_start": "2025-01",
        "period_end": "2025-09",
        "public_value": 63_000_000_000.0,
        "unit": "BRL",
        "local_metric": "monthly_net_flow_sum",
        "local_source_artifact": "industry_monthly.csv",
        "comparability": "metodologia_diferente",
        "method_note": "ANBIMA usa universo próprio da indústria de fundos; a aba usa Informe Mensal CVM com veículos/classes, exclusivos, NP e FIC-FIDC.",
    },
    {
        "claim_id": "anbima_fidc_accounts_aug_2025",
        "source_name": "ANBIMA",
        "source_title": "Indústria de fundos registra captação líquida de R$ 110,9 bilhões no ano até setembro",
        "source_url": "https://www.anbima.com.br/pt_br/noticias/industria-de-fundos-registra-captacao-liquida-de-r-110-9-bilhoes-no-ano-ate-setembro.htm",
        "published_at": "2025-10-07",
        "metric_group": "contas",
        "claim_text": "Contas de investidores em FIDCs chegaram a 318,8 mil em agosto de 2025.",
        "period_start": "2025-08",
        "period_end": "2025-08",
        "public_value": 318_800.0,
        "unit": "contas",
        "local_metric": "cotistas_total_snapshot",
        "local_source_artifact": "industry_monthly.csv",
        "comparability": "metodologia_diferente",
        "method_note": "CVM reporta cotistas/contas por veículo; ANBIMA pode consolidar contas por categoria e distribuidor.",
    },
    {
        "claim_id": "anbima_fidc_net_flow_2025_full",
        "source_name": "ANBIMA",
        "source_title": "Renda fixa, FIPs e FIDCs puxam a captação e indústria de fundos encerra 2025 no azul",
        "source_url": "https://www.anbima.com.br/pt_br/noticias/renda-fixa-fips-e-fidcs-puxam-a-captacao-e-industria-de-fundos-encerra-2025-no-azul.htm",
        "published_at": "2026-01-08",
        "metric_group": "captação líquida",
        "claim_text": "FIDCs captaram R$ 57,6 bi em 2025.",
        "period_start": "2025-01",
        "period_end": "2025-12",
        "public_value": 57_600_000_000.0,
        "unit": "BRL",
        "local_metric": "monthly_net_flow_sum",
        "local_source_artifact": "industry_monthly.csv",
        "comparability": "metodologia_diferente",
        "method_note": "Conceito público da ANBIMA não é idêntico ao fluxo reconstruído do Informe Mensal CVM.",
    },
    {
        "claim_id": "anbima_fidc_accounts_dec_2025",
        "source_name": "ANBIMA",
        "source_title": "Renda fixa, FIPs e FIDCs puxam a captação e indústria de fundos encerra 2025 no azul",
        "source_url": "https://www.anbima.com.br/pt_br/noticias/renda-fixa-fips-e-fidcs-puxam-a-captacao-e-industria-de-fundos-encerra-2025-no-azul.htm",
        "published_at": "2026-01-08",
        "metric_group": "contas",
        "claim_text": "Contas de investidores em FIDCs chegaram a 331,4 mil em dezembro de 2025.",
        "period_start": "2025-12",
        "period_end": "2025-12",
        "public_value": 331_400.0,
        "unit": "contas",
        "local_metric": "cotistas_total_snapshot",
        "local_source_artifact": "industry_monthly.csv",
        "comparability": "metodologia_diferente",
        "method_note": "CVM reporta cotistas/contas por veículo; pode haver dupla contagem entre fundos/classes.",
    },
    {
        "claim_id": "anbima_fidc_offers_2026_jan_may",
        "source_name": "ANBIMA",
        "source_title": "Mercado de capitais movimenta R$ 283 bilhões em ofertas puxado por FIDCs, híbridos e ações",
        "source_url": "https://www.anbima.com.br/pt_br/noticias/mercado-de-capitais-movimenta-r-283-bilhoes-em-ofertas-puxado-por-fidcs-hibridos-e-acoes.htm",
        "published_at": "2026-06-16",
        "metric_group": "ofertas",
        "claim_text": "FIDCs somaram R$ 41,7 bi em ofertas nos cinco primeiros meses de 2026.",
        "period_start": "2026-01",
        "period_end": "2026-05",
        "public_value": 41_700_000_000.0,
        "unit": "BRL",
        "local_metric": "issuance_tranche_volume_sum",
        "local_source_artifact": "issuance_tranches.csv.gz",
        "comparability": "subcobertura_documental",
        "method_note": "A base local de tranches documentais é curada/offline e não deve ser lida como boletim ANBIMA de ofertas encerradas.",
    },
    {
        "claim_id": "seu_dinheiro_fidc_pl_may_2026",
        "source_name": "Seu Dinheiro",
        "source_title": "Resgates de fundos multimercados disparam e FIDCs entram na mira do investidor",
        "source_url": "https://www.seudinheiro.com/2026/economia/resgates-de-fundos-multimercados-dispara-e-fidcs-entram-na-mira-do-investidor-segundo-anbima-entenda-lbrdcp162/",
        "published_at": "2026-06-17",
        "metric_group": "patrimônio líquido",
        "claim_text": "Indústria de FIDCs chegou a R$ 754 bi em maio de 2026.",
        "period_start": "2026-05",
        "period_end": "2026-05",
        "public_value": 754_000_000_000.0,
        "unit": "BRL",
        "local_metric": "pl_total_snapshot",
        "local_source_artifact": "industry_monthly.csv",
        "comparability": "metodologia_diferente",
        "method_note": "A aba exibe FIDCs + FIC-FIDCs e série ex-FIC; veículos CVM não são o mesmo universo consolidado da notícia.",
    },
    {
        "claim_id": "seu_dinheiro_fidc_net_flow_apr_2026",
        "source_name": "Seu Dinheiro",
        "source_title": "Resgates de fundos multimercados disparam e FIDCs entram na mira do investidor",
        "source_url": "https://www.seudinheiro.com/2026/economia/resgates-de-fundos-multimercados-dispara-e-fidcs-entram-na-mira-do-investidor-segundo-anbima-entenda-lbrdcp162/",
        "published_at": "2026-06-17",
        "metric_group": "captação líquida",
        "claim_text": "FIDCs tiveram captação mensal de R$ 4,5 bi em abril de 2026.",
        "period_start": "2026-04",
        "period_end": "2026-04",
        "public_value": 4_500_000_000.0,
        "unit": "BRL",
        "local_metric": "monthly_net_flow_sum",
        "local_source_artifact": "industry_monthly.csv",
        "comparability": "metodologia_diferente",
        "method_note": "A notícia usa ANBIMA; a aba soma aplicações, resgates e amortizações do Informe Mensal CVM.",
    },
    {
        "claim_id": "seu_dinheiro_fidc_net_flow_may_2026",
        "source_name": "Seu Dinheiro",
        "source_title": "Resgates de fundos multimercados disparam e FIDCs entram na mira do investidor",
        "source_url": "https://www.seudinheiro.com/2026/economia/resgates-de-fundos-multimercados-dispara-e-fidcs-entram-na-mira-do-investidor-segundo-anbima-entenda-lbrdcp162/",
        "published_at": "2026-06-17",
        "metric_group": "captação líquida",
        "claim_text": "FIDCs captaram R$ 2,5 bi em maio de 2026.",
        "period_start": "2026-05",
        "period_end": "2026-05",
        "public_value": 2_500_000_000.0,
        "unit": "BRL",
        "local_metric": "monthly_net_flow_sum",
        "local_source_artifact": "industry_monthly.csv",
        "comparability": "metodologia_diferente",
        "method_note": "A notícia usa ANBIMA; a aba soma aplicações, resgates e amortizações do Informe Mensal CVM.",
    },
]

CURATION_QUEUE_SUMMARY_COLUMNS = [
    "summary_id",
    "summary_type",
    "rank",
    "scope_label",
    "queue_domain",
    "status_curadoria",
    "priority_band",
    "cnpj_fundo",
    "nome_exibicao",
    "admin_nome",
    "gestor_nome",
    "segmento_principal",
    "rows",
    "open_rows",
    "closed_rows",
    "high_priority_rows",
    "priority_2025_2026_rows",
    "funds",
    "max_priority_score",
    "pl_reference_brl",
    "latest_competencia",
    "domains",
    "status_mix",
    "priority_mix",
    "action_types",
    "next_actions_sample",
    "gap_sample",
    "source_documents_sample",
    "rerun_commands_sample",
]

HEATMAP_PRESET_SPECS = [
    {
        "preset_id": "admin_segmento",
        "label": "Administrador × Segmento",
        "row_label": "Administrador",
        "row_dimension_id": "admin",
        "col_label": "Segmento",
        "col_dimension_id": "segmento",
    },
    {
        "preset_id": "gestor_segmento",
        "label": "Gestor × Segmento",
        "row_label": "Gestor",
        "row_dimension_id": "gestor",
        "col_label": "Segmento",
        "col_dimension_id": "segmento",
    },
    {
        "preset_id": "cedente_segmento",
        "label": "Cedente/sacado × Segmento",
        "row_label": "Cedente/sacado",
        "row_dimension_id": "cedente_sacado",
        "col_label": "Segmento",
        "col_dimension_id": "segmento",
    },
    {
        "preset_id": "cedente_admin",
        "label": "Cedente/sacado × Administrador",
        "row_label": "Cedente/sacado",
        "row_dimension_id": "cedente_sacado",
        "col_label": "Administrador",
        "col_dimension_id": "admin",
    },
    {
        "preset_id": "setor_ano_primeira_oferta",
        "label": "Setor cedente × Ano 1ª oferta",
        "row_label": "Setor cedente",
        "row_dimension_id": "setor_cedente",
        "col_label": "Ano 1ª oferta",
        "col_dimension_id": "ano_primeira_oferta",
    },
    {
        "preset_id": "segmento_safra_emissao",
        "label": "Segmento × Safra emissão",
        "row_label": "Segmento",
        "row_dimension_id": "segmento",
        "col_label": "Safra emissão",
        "col_dimension_id": "safra_emissao",
    },
    {
        "preset_id": "setor_indexador",
        "label": "Setor cedente × Indexador",
        "row_label": "Setor cedente",
        "row_dimension_id": "setor_cedente",
        "col_label": "Indexador",
        "col_dimension_id": "indexador",
    },
    {
        "preset_id": "segmento_indexador",
        "label": "Segmento × Indexador",
        "row_label": "Segmento",
        "row_dimension_id": "segmento",
        "col_label": "Indexador",
        "col_dimension_id": "indexador",
    },
    {
        "preset_id": "admin_tipo_cota",
        "label": "Administrador × Tipo de cota",
        "row_label": "Administrador",
        "row_dimension_id": "admin",
        "col_label": "Tipo de cota",
        "col_dimension_id": "tipo_cota",
    },
    {
        "preset_id": "criterio_segmento",
        "label": "Critério × Segmento",
        "row_label": "Critério",
        "row_dimension_id": "criterio",
        "col_label": "Segmento",
        "col_dimension_id": "segmento",
    },
    {
        "preset_id": "status_curadoria_segmento",
        "label": "Status curadoria × Segmento",
        "row_label": "Status curadoria",
        "row_dimension_id": "status_curadoria",
        "col_label": "Segmento",
        "col_dimension_id": "segmento",
    },
]

HEATMAP_REGISTRY_COLUMNS = [
    "preset_id",
    "preset_label",
    "order",
    "row_dimension_id",
    "row_dimension_label",
    "col_dimension_id",
    "col_dimension_label",
    "status",
    "available",
    "profile_available",
    "missing_dimensions",
    "profile_rows",
    "profile_links",
    "source_document_links",
    "curated_links",
    "weighted_links",
    "avg_confidence_score",
    "metrics_supported",
    "source_mode",
    "rerun_command",
]

DIMENSION_VALUE_ATLAS_COLUMNS = [
    "dimension_id",
    "dimension_label",
    "dimension_value",
    "rank_in_dimension",
    "rank_global",
    "competencia_atual",
    "competencia_12m_antes",
    "months_available",
    "first_competencia",
    "pl_atual_brl",
    "captacao_12m_brl",
    "pl_12m_antes_brl",
    "pl_delta_12m_brl",
    "pl_growth_12m_pct",
    "carteira_atual_brl",
    "inad_atual_brl",
    "inad_pct_atual",
    "fundos_atuais",
    "veiculos_atuais",
    "funds_equiv_atual",
    "cotistas_equiv_atual",
    "links_catalogo",
    "links_com_fonte",
    "links_com_metodo",
    "links_com_camada",
    "links_com_pagina",
    "links_com_data",
    "links_com_score",
    "links_curados",
    "links_ponderados",
    "traceability_coverage",
    "evidence_coverage",
    "curated_coverage",
    "weighted_coverage",
    "evidence_funds",
    "source_layers",
    "source_documents_sample",
    "source_pages_sample",
    "source_methods_sample",
    "review_status_mix",
    "priority_2025_2026_links",
    "avg_confidence_score",
    "last_source_date",
    "rank_score",
    "source_artifact",
    "source_method",
    "rerun_command",
]

DIMENSION_DOSSIER_COLUMNS = [
    "dimension_id",
    "dimension_label",
    "status_dossie",
    "status_reasons",
    "latest_competencia",
    "atlas_values",
    "atlas_values_with_pl",
    "top_values_sample",
    "pl_total_atual_brl",
    "pl_top_20_brl",
    "captacao_12m_top_20_brl",
    "fundos_atuais_total",
    "veiculos_atuais_total",
    "links_catalogo",
    "links_com_fonte",
    "source_document_coverage",
    "links_com_metodo",
    "links_com_camada",
    "traceability_links",
    "traceability_coverage",
    "links_curados",
    "curated_coverage",
    "links_ponderados",
    "weighted_coverage",
    "avg_confidence_score",
    "source_documents_sample",
    "source_pages_sample",
    "source_methods_sample",
    "review_status_mix",
    "priority_2025_2026_links",
    "profile_rows",
    "profile_target_dimensions",
    "profile_target_values",
    "profile_links",
    "profile_source_document_links",
    "profile_curated_links",
    "profile_weighted_links",
    "profile_avg_confidence_score",
    "heatmap_presets",
    "heatmap_presets_ok",
    "heatmap_preset_labels_sample",
    "source_artifacts",
    "source_method",
    "rerun_command",
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


def load_review_audit(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=REVIEW_AUDIT_COLUMNS)
    audit = pd.read_csv(path, dtype=str, keep_default_na=False)
    for col in REVIEW_AUDIT_COLUMNS:
        if col not in audit.columns:
            audit[col] = ""
    return audit[REVIEW_AUDIT_COLUMNS]


def _audit_value(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _material_review_mask(frame: pd.DataFrame, key_column: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool)
    out = pd.Series(False, index=frame.index)
    if "status" in frame.columns:
        out = out | ~frame["status"].map(_audit_value).str.lower().isin({"", "pendente"})
    for col in frame.columns:
        if col in {key_column, "status"}:
            continue
        out = out | frame[col].map(_audit_value).ne("")
    return out


def build_review_audit_events(
    *,
    previous: pd.DataFrame,
    updated: pd.DataFrame,
    key_column: str,
    review_domain: str,
    saved_at_utc: str | None = None,
    source: str = "app",
) -> pd.DataFrame:
    """Return append-only field-level audit events for changed review rows."""

    if updated is None or updated.empty or key_column not in updated.columns:
        return pd.DataFrame(columns=REVIEW_AUDIT_COLUMNS)
    saved_at = saved_at_utc or datetime.now(timezone.utc).isoformat(timespec="seconds")
    prev = previous.copy() if previous is not None and not previous.empty else pd.DataFrame()
    curr = updated.copy()
    columns = [col for col in curr.columns if col != key_column]
    if key_column not in prev.columns:
        prev = pd.DataFrame(columns=[key_column, *columns])
    for col in columns:
        if col not in prev.columns:
            prev[col] = ""
    prev = prev[[key_column, *columns]].drop_duplicates(key_column, keep="last")
    curr = curr[[key_column, *columns]].drop_duplicates(key_column, keep="last")
    prev = prev.set_index(key_column, drop=False)
    curr = curr.set_index(key_column, drop=False)
    material_curr = _material_review_mask(curr.reset_index(drop=True), key_column)
    material_by_id = pd.Series(material_curr.to_numpy(), index=curr.index)

    events: list[dict[str, str]] = []
    for record_id, row in curr.iterrows():
        record_key = _audit_value(record_id)
        if not record_key:
            continue
        old_row = prev.loc[record_id] if record_id in prev.index else pd.Series(dtype=object)
        existed_before = record_id in prev.index
        if not existed_before and not bool(material_by_id.get(record_id, False)):
            continue
        status_after = _audit_value(row.get("status"))
        for field in columns:
            old_value = _audit_value(old_row.get(field, ""))
            new_value = _audit_value(row.get(field, ""))
            if old_value == new_value:
                continue
            event_key = "|".join(
                [review_domain, record_key, field, saved_at, old_value, new_value, source]
            )
            events.append(
                {
                    "event_id": hashlib.sha1(event_key.encode("utf-8", errors="ignore")).hexdigest()[:20],
                    "saved_at_utc": saved_at,
                    "review_domain": review_domain,
                    "record_id": record_key,
                    "field": field,
                    "old_value": old_value,
                    "new_value": new_value,
                    "status_after": status_after,
                    "source": source,
                }
            )
    if not events:
        return pd.DataFrame(columns=REVIEW_AUDIT_COLUMNS)
    return pd.DataFrame(events, columns=REVIEW_AUDIT_COLUMNS)


def append_review_audit_events(events: pd.DataFrame, path: Path) -> pd.DataFrame:
    path.parent.mkdir(parents=True, exist_ok=True)
    if events is None or events.empty:
        audit = load_review_audit(path)
        if not path.exists():
            audit.to_csv(path, index=False)
        return audit
    audit = load_review_audit(path)
    combined = pd.concat([audit, events[REVIEW_AUDIT_COLUMNS]], ignore_index=True)
    combined = combined.drop_duplicates("event_id", keep="last")
    combined.to_csv(path, index=False)
    return combined


def load_monthly_delta_actions(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=MONTHLY_DELTA_ACTION_COLUMNS)
    actions = pd.read_csv(path, dtype=str, keep_default_na=False)
    for col in MONTHLY_DELTA_ACTION_COLUMNS:
        if col not in actions.columns:
            actions[col] = ""
    return actions[MONTHLY_DELTA_ACTION_COLUMNS]


def save_monthly_delta_actions(actions: pd.DataFrame, path: Path) -> pd.DataFrame:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = actions.copy() if actions is not None else pd.DataFrame(columns=MONTHLY_DELTA_ACTION_COLUMNS)
    for col in MONTHLY_DELTA_ACTION_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[MONTHLY_DELTA_ACTION_COLUMNS]
    out = out[out["delta_id"].map(_audit_value).ne("")].drop_duplicates("delta_id", keep="last")
    out.to_csv(path, index=False)
    return out


def initialize_monthly_delta_actions(
    delta: pd.DataFrame,
    actions: pd.DataFrame | None = None,
    *,
    priority_bands: tuple[str, ...] = ("alta",),
) -> pd.DataFrame:
    """Create pending action rows for priority deltas without creating decisions."""

    existing = pd.DataFrame() if actions is None else actions.copy()
    for col in MONTHLY_DELTA_ACTION_COLUMNS:
        if col not in existing.columns:
            existing[col] = ""
    existing = existing[MONTHLY_DELTA_ACTION_COLUMNS].copy()
    existing["delta_id"] = existing["delta_id"].map(_audit_value)
    existing = existing[existing["delta_id"].ne("")].drop_duplicates("delta_id", keep="last")
    if delta is None or delta.empty or "delta_id" not in delta.columns:
        return existing.reset_index(drop=True)

    candidates = delta.copy()
    candidates["delta_id"] = candidates["delta_id"].map(_audit_value)
    candidates = candidates[candidates["delta_id"].ne("")].drop_duplicates("delta_id", keep="first")
    if priority_bands and "priority_band" in candidates.columns:
        bands = {str(value).strip().lower() for value in priority_bands if str(value).strip()}
        priority = candidates["priority_band"].fillna("").astype(str).str.strip().str.lower()
        candidates = candidates[priority.isin(bands)].copy()
    candidates = candidates[~candidates["delta_id"].isin(set(existing["delta_id"]))].copy()
    if candidates.empty:
        return existing.reset_index(drop=True)

    seeded = pd.DataFrame({"delta_id": candidates["delta_id"].tolist()})
    seeded["status_acao"] = "pendente"
    for col in ["acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        seeded[col] = ""
    seeded = seeded[MONTHLY_DELTA_ACTION_COLUMNS]
    return pd.concat([existing, seeded], ignore_index=True)[MONTHLY_DELTA_ACTION_COLUMNS].reset_index(drop=True)


def apply_monthly_delta_actions(delta: pd.DataFrame, actions: pd.DataFrame | None) -> pd.DataFrame:
    if delta is None or delta.empty:
        return pd.DataFrame() if delta is None else delta.copy()
    out = delta.copy()
    for col in ["status_acao", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        if col not in out.columns:
            out[col] = ""
    if actions is None or actions.empty or "delta_id" not in actions.columns or "delta_id" not in out.columns:
        out["status_acao"] = out["status_acao"].replace("", "pendente")
        return out
    overlay = actions.copy()
    for col in MONTHLY_DELTA_ACTION_COLUMNS:
        if col not in overlay.columns:
            overlay[col] = ""
    overlay = overlay[MONTHLY_DELTA_ACTION_COLUMNS].drop_duplicates("delta_id", keep="last")
    out = out.merge(overlay, on="delta_id", how="left", suffixes=("", "_review"))
    for col in ["status_acao", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        review_col = f"{col}_review"
        if review_col in out.columns:
            out[col] = out[review_col].where(out[review_col].map(_audit_value).ne(""), out[col])
    out = out.drop(columns=[f"{col}_review" for col in ["status_acao", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]], errors="ignore")
    out["status_acao"] = out["status_acao"].replace("", "pendente")
    return out


def review_audit_summary(audit: pd.DataFrame, key_column: str) -> pd.DataFrame:
    columns = [
        key_column,
        "review_event_count",
        "last_review_at_utc",
        "last_review_field",
        "last_review_source",
    ]
    if audit is None or audit.empty or "record_id" not in audit.columns:
        return pd.DataFrame(columns=columns)
    frame = audit.copy()
    frame[key_column] = frame["record_id"].map(_audit_value)
    frame = frame[frame[key_column].ne("")].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["saved_at_sort"] = pd.to_datetime(frame.get("saved_at_utc"), errors="coerce", utc=True)
    frame = frame.sort_values(["saved_at_sort", "saved_at_utc"], ascending=[True, True])
    grouped = frame.groupby(key_column, dropna=False)
    latest = grouped.tail(1).set_index(key_column)
    summary = grouped.size().rename("review_event_count").reset_index()
    summary["last_review_at_utc"] = summary[key_column].map(latest["saved_at_utc"].to_dict()).fillna("")
    summary["last_review_field"] = summary[key_column].map(latest["field"].to_dict()).fillna("")
    summary["last_review_source"] = summary[key_column].map(latest["source"].to_dict()).fillna("")
    return summary[columns]


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


def _participant_types_from_signal_keys(value: object) -> list[str]:
    keys = re.split(r"\s*\|\s*|,", str(value or ""))
    types: list[str] = []
    for key in keys:
        lower = key.strip().lower()
        if not lower:
            continue
        if ("debtor" in lower or "sacado" in lower) and "sacado_devedor" not in types:
            types.append("sacado_devedor")
        if ("originator" in lower or "cedente" in lower) and "cedente_originador" not in types:
            types.append("cedente_originador")
    return types or ["cedente_originador"]


def augment_cedente_candidates_with_signal_focus(
    candidates: pd.DataFrame,
    signal_focus: pd.DataFrame,
) -> pd.DataFrame:
    """Add reviewable placeholders for funds with participant signal but no candidate row.

    Placeholders intentionally keep participant name/CNPJ blank, so they become
    editable review rows without inflating identified cedente/sacado coverage.
    """

    base = candidates.copy() if candidates is not None else pd.DataFrame()
    candidate_columns = [
        "cnpj_fundo",
        "fund_name",
        "setor_n1",
        "setor_n2",
        "participant_type",
        "participant_cnpj_candidate",
        "participant_name_candidate",
        "evidence_context",
        "source_cache",
        "review_id",
        "participante_extraido",
        "documento_origem",
        "pagina",
        "metodo_extracao",
        "score_confianca",
        "evidencias_agrupadas",
        "signal_placeholder",
    ]
    for col in candidate_columns:
        if col not in base.columns:
            base[col] = False if col == "signal_placeholder" else ""
    if not base.empty:
        base["cnpj_fundo"] = base["cnpj_fundo"].map(normalize_cnpj)
        existing_funds = set(base["cnpj_fundo"].dropna().astype(str))
    else:
        existing_funds = set()

    if signal_focus is None or signal_focus.empty or "cnpj_fundo" not in signal_focus.columns:
        return base.reset_index(drop=True)

    focus = signal_focus.copy()
    focus["cnpj_fundo"] = focus["cnpj_fundo"].map(normalize_cnpj)
    focus = focus[focus["cnpj_fundo"].astype(str).str.len().eq(14)].copy()
    if "participant_signal_rows" in focus.columns:
        focus = focus[pd.to_numeric(focus["participant_signal_rows"], errors="coerce").fillna(0).gt(0)].copy()
    if "cedente_rows" in focus.columns:
        focus = focus[pd.to_numeric(focus["cedente_rows"], errors="coerce").fillna(0).le(0)].copy()
    if existing_funds:
        focus = focus[~focus["cnpj_fundo"].isin(existing_funds)].copy()
    if focus.empty:
        return base.reset_index(drop=True)

    rows: list[dict[str, object]] = []
    for _, row in focus.iterrows():
        evidence = str(row.get("participant_signal_evidence", "") or "").strip()
        source_cache = str(row.get("criteria_documentos", "") or row.get("source_document", "") or "").strip()
        signal_rows = pd.to_numeric(pd.Series([row.get("participant_signal_rows", 1)]), errors="coerce").fillna(1).iloc[0]
        for participant_type in _participant_types_from_signal_keys(row.get("participant_signal_keys", "")):
            record = {
                "cnpj_fundo": row.get("cnpj_fundo", ""),
                "fund_name": row.get("nome_exibicao", row.get("fund_name", row.get("denominacao", ""))),
                "setor_n1": row.get("signal_segmento_principal", row.get("segmento_principal", "")),
                "setor_n2": row.get("segmento_financeiro_principal", row.get("segmento_principal", "")),
                "participant_type": participant_type,
                "participant_cnpj_candidate": "",
                "participant_name_candidate": "",
                "participante_extraido": "",
                "evidence_context": evidence,
                "source_cache": source_cache,
                "documento_origem": source_cache.split(" | ")[0][:160],
                "pagina": "",
                "metodo_extracao": "strategy_regulatory_feature_signal",
                "score_confianca": 0.4,
                "evidencias_agrupadas": int(max(float(signal_rows), 1.0)),
                "signal_placeholder": True,
            }
            record["review_id"] = review_id(pd.Series(record))
            rows.append(record)

    if not rows:
        return base.reset_index(drop=True)
    placeholders = pd.DataFrame(rows)
    out = pd.concat([base, placeholders], ignore_index=True, sort=False)
    return out.drop_duplicates("review_id", keep="first").reset_index(drop=True)


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
    review_audit: pd.DataFrame | None = None,
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

    if review_audit is not None and not review_audit.empty:
        audit_summary = review_audit_summary(review_audit, "review_id")
        if not audit_summary.empty:
            out = out.merge(audit_summary, on="review_id", how="left")
    for col in ["review_event_count", "last_review_at_utc", "last_review_field", "last_review_source"]:
        if col not in out.columns:
            out[col] = 0 if col == "review_event_count" else ""
    out["review_event_count"] = pd.to_numeric(out["review_event_count"], errors="coerce").fillna(0).astype(int)

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
        "review_event_count",
        "last_review_at_utc",
        "last_review_field",
        "last_review_source",
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


def manual_review_file_specs() -> list[dict[str, object]]:
    """Return the authoritative in-app manual review file inventory."""

    specs: list[dict[str, object]] = []
    for spec in MANUAL_REVIEW_LEDGER_SPECS:
        action = dict(spec)
        action["file_role"] = "actions"
        action["file_name"] = spec["action_file"]
        action["columns"] = list(spec["action_columns"])
        specs.append(action)
        audit = dict(spec)
        audit["file_role"] = "audit"
        audit["file_name"] = spec["audit_file"]
        audit["columns"] = list(REVIEW_AUDIT_COLUMNS)
        specs.append(audit)
    return specs


def initialize_manual_review_ledgers(*, industry_dir: Path) -> pd.DataFrame:
    """Create missing in-app review CSVs with headers, without adding decisions."""

    rows: list[dict[str, object]] = []
    for spec in manual_review_file_specs():
        file_name = str(spec["file_name"])
        path = industry_dir / file_name
        columns = [str(col) for col in spec.get("columns", [])]
        existed_before = path.exists()
        if not existed_before:
            path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(columns=columns).to_csv(path, index=False)
        frame = load_dataframe(path)
        rows.append(
            {
                "domain_id": spec.get("domain_id", ""),
                "label": spec.get("label", ""),
                "module_id": spec.get("module_id", ""),
                "file_role": spec.get("file_role", ""),
                "file_name": file_name,
                "path": str(path),
                "exists": path.exists(),
                "created": not existed_before,
                "rows": int(len(frame)),
                "columns_expected": len(columns),
                "columns_present": int(sum(1 for col in columns if col in frame.columns)),
                "schema_ok": all(col in frame.columns for col in columns),
            }
        )
    return pd.DataFrame(rows)


def manual_review_ledgers_quality_summary(ledger_files: pd.DataFrame) -> dict[str, object]:
    if ledger_files is None or ledger_files.empty:
        return {
            "files": 0,
            "files_present": 0,
            "files_created": 0,
            "schema_ok_files": 0,
            "domains": 0,
        }
    frame = ledger_files.copy()
    return {
        "files": int(len(frame)),
        "files_present": int(frame.get("exists", pd.Series(False, index=frame.index)).astype(bool).sum()),
        "files_created": int(frame.get("created", pd.Series(False, index=frame.index)).astype(bool).sum()),
        "schema_ok_files": int(frame.get("schema_ok", pd.Series(False, index=frame.index)).astype(bool).sum()),
        "domains": int(frame.get("domain_id", pd.Series("", index=frame.index)).fillna("").astype(str).nunique()),
        "action_files": int(frame.get("file_role", pd.Series("", index=frame.index)).fillna("").astype(str).eq("actions").sum()),
        "audit_files": int(frame.get("file_role", pd.Series("", index=frame.index)).fillna("").astype(str).eq("audit").sum()),
        "rows": int(pd.to_numeric(frame.get("rows"), errors="coerce").fillna(0).sum()),
    }


def _competencia_key(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[:6] if len(digits) >= 6 else ""


def _competencia_label(value: object) -> str:
    key = _competencia_key(value)
    return f"{key[:4]}-{key[4:6]}" if len(key) == 6 else str(value or "")


def _period_month_mask(frame: pd.DataFrame, start: str, end: str) -> pd.Series:
    if frame.empty or "competencia" not in frame.columns:
        return pd.Series(False, index=frame.index)
    comp = frame["competencia"].fillna("").astype(str)
    return comp.ge(str(start)) & comp.le(str(end))


def _public_claim_local_value(
    *,
    spec: dict[str, object],
    industry_monthly: pd.DataFrame,
    issuance_tranches: pd.DataFrame,
) -> tuple[float | None, str, str]:
    metric = str(spec.get("local_metric") or "")
    start = str(spec.get("period_start") or "")
    end = str(spec.get("period_end") or start)
    if metric in {"monthly_net_flow_sum", "cotistas_total_snapshot", "pl_total_snapshot"}:
        frame = industry_monthly.copy()
        if frame.empty or "competencia" not in frame.columns:
            return None, "", "industry_monthly vazio ou sem competência"
        rows = frame[_period_month_mask(frame, start, end)].copy()
        if rows.empty:
            return None, "", f"sem linhas CVM entre {start} e {end}"
        if metric == "monthly_net_flow_sum":
            value = pd.to_numeric(rows.get("captacao_liquida"), errors="coerce").fillna(0.0).sum()
            evidence = f"{len(rows)} competência(s) em industry_monthly.csv"
            return float(value), evidence, ""
        snapshot = rows.sort_values("competencia").tail(1).iloc[0]
        if metric == "cotistas_total_snapshot":
            value = pd.to_numeric(pd.Series([snapshot.get("cotistas_total")]), errors="coerce").iloc[0]
            return (None if pd.isna(value) else float(value)), f"competência {snapshot.get('competencia')}", ""
        if metric == "pl_total_snapshot":
            value = pd.to_numeric(pd.Series([snapshot.get("pl_total")]), errors="coerce").iloc[0]
            return (None if pd.isna(value) else float(value)), f"competência {snapshot.get('competencia')}", ""
    if metric == "issuance_tranche_volume_sum":
        frame = issuance_tranches.copy()
        if frame.empty or "data_deliberacao" not in frame.columns:
            return None, "", "issuance_tranches vazio ou sem data"
        dates = pd.to_datetime(frame["data_deliberacao"], errors="coerce")
        start_date = pd.to_datetime(f"{start}-01", errors="coerce")
        end_date = pd.to_datetime(f"{end}-01", errors="coerce") + pd.offsets.MonthEnd(0)
        rows = frame[dates.ge(start_date) & dates.le(end_date)].copy()
        if rows.empty:
            return 0.0, f"0 tranche entre {start} e {end}", ""
        value = pd.to_numeric(rows.get("volume_brl"), errors="coerce").fillna(0.0).sum()
        evidence = f"{len(rows)} tranche(s); {rows.get('cnpj_fundo', pd.Series(dtype=str)).nunique()} FIDC(s)"
        return float(value), evidence, ""
    return None, "", f"métrica local não implementada: {metric}"


def build_public_claim_audit(
    *,
    industry_monthly: pd.DataFrame,
    issuance_tranches: pd.DataFrame,
    claim_specs: list[dict[str, object]] | None = None,
    tolerance_pct: float = 0.10,
) -> pd.DataFrame:
    """Compare public market claims with the Industry tab's auditable local metrics."""

    specs = claim_specs or PUBLIC_CLAIM_SPECS
    rows: list[dict[str, object]] = []
    for spec in specs:
        public_value = pd.to_numeric(pd.Series([spec.get("public_value")]), errors="coerce").iloc[0]
        local_value, evidence, local_note = _public_claim_local_value(
            spec=spec,
            industry_monthly=industry_monthly,
            issuance_tranches=issuance_tranches,
        )
        if pd.isna(public_value):
            public_value = None
        delta_value = None
        delta_pct = None
        if public_value not in (None, 0) and local_value is not None:
            delta_value = float(local_value) - float(public_value)
            delta_pct = delta_value / float(public_value)
        comparability = str(spec.get("comparability") or "comparável")
        if local_value is None:
            status = "sem_base_local"
        elif comparability != "comparável":
            status = "diferença_metodológica"
        elif delta_pct is not None and abs(float(delta_pct)) <= tolerance_pct:
            status = "aderente"
        else:
            status = "divergente"
        rows.append(
            {
                "claim_id": spec.get("claim_id", ""),
                "source_name": spec.get("source_name", ""),
                "source_title": spec.get("source_title", ""),
                "source_url": spec.get("source_url", ""),
                "published_at": spec.get("published_at", ""),
                "metric_group": spec.get("metric_group", ""),
                "claim_text": spec.get("claim_text", ""),
                "period_start": spec.get("period_start", ""),
                "period_end": spec.get("period_end", ""),
                "unit": spec.get("unit", ""),
                "public_value": public_value,
                "local_value": local_value,
                "delta_value": delta_value,
                "delta_pct": delta_pct,
                "status_auditoria": status,
                "comparability": comparability,
                "tolerance_pct": tolerance_pct,
                "local_metric": spec.get("local_metric", ""),
                "local_source_artifact": spec.get("local_source_artifact", ""),
                "local_evidence": evidence,
                "method_note": spec.get("method_note", ""),
                "local_note": local_note,
                "rerun_command": "python scripts/build_fidc_industry_public_claim_audit.py",
            }
        )
    return pd.DataFrame(rows)


def public_claim_audit_quality_summary(audit: pd.DataFrame) -> dict[str, object]:
    if audit is None or audit.empty:
        return {
            "rows": 0,
            "claims_with_local_metric": 0,
            "public_sources": 0,
            "methodology_gap_claims": 0,
            "adherent_claims": 0,
            "divergent_claims": 0,
            "max_abs_delta_pct": None,
        }
    status = audit.get("status_auditoria", pd.Series("", index=audit.index)).fillna("").astype(str)
    delta_abs = pd.to_numeric(audit.get("delta_pct"), errors="coerce").abs()
    return {
        "rows": int(len(audit)),
        "claims_with_local_metric": int(audit.get("local_value", pd.Series(dtype=float)).notna().sum()),
        "public_sources": int(audit.get("source_name", pd.Series(dtype=str)).nunique()),
        "methodology_gap_claims": int(status.eq("diferença_metodológica").sum()),
        "adherent_claims": int(status.eq("aderente").sum()),
        "divergent_claims": int(status.eq("divergente").sum()),
        "missing_local_claims": int(status.eq("sem_base_local").sum()),
        "max_abs_delta_pct": None if delta_abs.dropna().empty else float(delta_abs.max()),
        "metric_group_counts": {
            str(key): int(value)
            for key, value in audit.get("metric_group", pd.Series(dtype=str)).fillna("n/d").astype(str).value_counts().to_dict().items()
        },
        "status_counts": {str(key): int(value) for key, value in status.value_counts().to_dict().items()},
    }


def _public_claim_bridge_profile(row: pd.Series) -> dict[str, str]:
    source = str(row.get("source_name") or "").strip()
    metric = str(row.get("metric_group") or "").strip().lower()
    local_metric = str(row.get("local_metric") or "").strip()
    comparability = str(row.get("comparability") or "").strip()
    public_universe = "Fonte pública declarada"
    if source == "ANBIMA":
        public_universe = "ANBIMA; categoria pública de FIDCs na indústria de fundos"
    elif source == "Seu Dinheiro":
        public_universe = "Notícia pública baseada em dados ANBIMA"

    local_universe = "Base local da aba Indústria"
    local_concept = "Métrica local materializada"
    primary_gap = "Conceito público e métrica local não são perfeitamente equivalentes"
    reconciliation_basis = "Comparar como ponte metodológica, não como erro automático"
    if local_metric == "monthly_net_flow_sum":
        local_universe = "Informe Mensal CVM; veículos/classes reportantes em industry_monthly.csv"
        local_concept = "Soma de captação líquida reconstruída como aplicações menos resgates e amortizações"
        primary_gap = "ANBIMA usa sua base de indústria; CVM soma veículos reportantes e pode carregar diferenças de universo, classes, exclusivos, NP e FIC-FIDC"
        reconciliation_basis = "Usar para explicar direção e ordem de grandeza; valor absoluto exige nota de universo"
    elif local_metric == "cotistas_total_snapshot":
        local_universe = "Informe Mensal CVM; contas/cotistas reportadas por veículo"
        local_concept = "Contas de cotistas do snapshot mensal; não representa CPF/CNPJ único consolidado"
        primary_gap = "Contas podem ser duplicadas entre veículos/classes e divergir de consolidação pública por distribuidor/categoria"
        reconciliation_basis = "Apresentar como contas reportadas CVM, não como investidores únicos"
    elif local_metric == "pl_total_snapshot":
        local_universe = "Informe Mensal CVM; FIDCs + FIC-FIDCs no snapshot mensal"
        local_concept = "Patrimônio líquido total reportado; a aba também mantém série ex-FIC para reduzir dupla contagem"
        primary_gap = "Universo CVM e universo consolidado ANBIMA/notícia diferem; FIC-FIDC pode induzir dupla contagem"
        reconciliation_basis = "Mostrar sempre as duas séries de PL e explicitar possível dupla contagem"
    elif local_metric == "issuance_tranche_volume_sum":
        local_universe = "Base local de tranches/ofertas extraída da aba Estratégia e documentação disponível"
        local_concept = "Volume de tranches documentais com data de deliberação no período"
        primary_gap = "Base local de ofertas é curada/offline e pode subcobrir boletins ANBIMA de mercado de capitais"
        reconciliation_basis = "Usar como evidência documental local; não como substituto do boletim ANBIMA"

    if comparability == "subcobertura_documental":
        primary_gap = "Subcobertura documental local frente ao boletim público de ofertas"
    if metric and "oferta" in metric:
        reconciliation_basis = "Tratar diferença como cobertura documental até completar a base de ofertas"

    return {
        "public_universe": public_universe,
        "local_universe": local_universe,
        "local_concept": local_concept,
        "primary_gap": primary_gap,
        "reconciliation_basis": reconciliation_basis,
    }


def build_public_claim_methodology_bridge(audit: pd.DataFrame) -> pd.DataFrame:
    """Create an explicit per-claim bridge between public figures and local CVM metrics."""

    columns = [
        "claim_id",
        "source_name",
        "metric_group",
        "period_start",
        "period_end",
        "status_auditoria",
        "comparability",
        "public_universe",
        "local_universe",
        "local_concept",
        "primary_gap",
        "reconciliation_basis",
        "delta_pct",
        "gap_severity",
        "needs_methodology_disclosure",
        "external_use_status",
        "action_before_external_use",
        "local_source_artifact",
        "source_url",
    ]
    if audit is None or audit.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    for _, row in audit.iterrows():
        profile = _public_claim_bridge_profile(row)
        status = str(row.get("status_auditoria") or "").strip()
        comparability = str(row.get("comparability") or "").strip()
        delta_pct = pd.to_numeric(pd.Series([row.get("delta_pct")]), errors="coerce").iloc[0]
        abs_delta = None if pd.isna(delta_pct) else abs(float(delta_pct))
        needs_disclosure = status in {"diferença_metodológica", "divergente", "sem_base_local"} or comparability != "comparável"
        if status == "sem_base_local":
            severity = "bloqueante"
            external_status = "não usar externamente sem base local"
            action = "Materializar a métrica local antes de comparar com a notícia."
        elif comparability == "subcobertura_documental":
            severity = "alta"
            external_status = "usar apenas como evidência de subcobertura"
            action = "Completar cobertura documental de ofertas ou citar explicitamente a subcobertura local."
        elif needs_disclosure and abs_delta is not None and abs_delta >= 0.50:
            severity = "alta"
            external_status = "usar com nota metodológica explícita"
            action = "Explicar universo público versus CVM antes de apresentação externa."
        elif needs_disclosure:
            severity = "média"
            external_status = "usar com nota metodológica"
            action = "Manter a diferença metodológica no rodapé ou na fala executiva."
        else:
            severity = "baixa"
            external_status = "comparável dentro da tolerância"
            action = "Pode ser usado como reconciliação direta, mantendo fonte e período."
        rows.append(
            {
                "claim_id": row.get("claim_id", ""),
                "source_name": row.get("source_name", ""),
                "metric_group": row.get("metric_group", ""),
                "period_start": row.get("period_start", ""),
                "period_end": row.get("period_end", ""),
                "status_auditoria": status,
                "comparability": comparability,
                **profile,
                "delta_pct": None if pd.isna(delta_pct) else float(delta_pct),
                "gap_severity": severity,
                "needs_methodology_disclosure": bool(needs_disclosure),
                "external_use_status": external_status,
                "action_before_external_use": action,
                "local_source_artifact": row.get("local_source_artifact", ""),
                "source_url": row.get("source_url", ""),
            }
        )
    out = pd.DataFrame(rows, columns=columns)
    status_order = {"bloqueante": 0, "alta": 1, "média": 2, "baixa": 3}
    out["_severity_order"] = out["gap_severity"].map(status_order).fillna(9)
    return out.sort_values(["_severity_order", "source_name", "metric_group", "period_start"]).drop(columns=["_severity_order"]).reset_index(drop=True)


def public_claim_methodology_bridge_quality_summary(bridge: pd.DataFrame) -> dict[str, object]:
    if bridge is None or bridge.empty:
        return {
            "rows": 0,
            "needs_disclosure_rows": 0,
            "high_or_blocking_rows": 0,
        }
    severity = bridge.get("gap_severity", pd.Series("", index=bridge.index)).fillna("").astype(str)
    needs = _boolish_series(bridge.get("needs_methodology_disclosure", pd.Series(False, index=bridge.index)))
    return {
        "rows": int(len(bridge)),
        "needs_disclosure_rows": int(needs.sum()),
        "high_or_blocking_rows": int(severity.isin({"bloqueante", "alta"}).sum()),
        "severity_counts": {str(key): int(value) for key, value in severity.value_counts().to_dict().items()},
    }


def _first_non_empty(series: pd.Series) -> str:
    for value in series:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _vehicle_monthly_by_fund(frame: pd.DataFrame, competencia_key: str) -> pd.DataFrame:
    if frame.empty or "competencia" not in frame.columns:
        return pd.DataFrame()
    base = frame.copy()
    base["competencia_key"] = base["competencia"].map(_competencia_key)
    base = base[base["competencia_key"].eq(competencia_key)].copy()
    if base.empty:
        return base
    if "cnpj_fundo" in base.columns:
        base["cnpj_fundo"] = base["cnpj_fundo"].map(normalize_cnpj)
    elif "cnpj" in base.columns:
        base["cnpj_fundo"] = base["cnpj"].map(normalize_cnpj)
    else:
        return pd.DataFrame()
    base = base[base["cnpj_fundo"].astype(str).str.len().eq(14)].copy()
    if base.empty:
        return base
    text_aggs = {
        col: (col, _first_non_empty)
        for col in [
            "denominacao",
            "admin_nome",
            "gestor_nome",
            "custodiante_nome",
            "segmento_principal",
            "segmento_financeiro_principal",
        ]
        if col in base.columns
    }
    num_aggs = {
        "pl_atual": ("pl", "sum"),
        "captacao_liquida_mes": ("captacao_liquida", "sum"),
        "carteira_dc": ("carteira_dc", "sum"),
        "cotistas": ("cotistas", "sum"),
        "subordinacao_pct": ("subordinacao_pct", "median"),
        "inad_pct_ajustada": ("inad_pct_ajustada", "median"),
    }
    for source_col, _agg in list(num_aggs.values()):
        if source_col not in base.columns:
            base[source_col] = 0.0
        base[source_col] = pd.to_numeric(base[source_col], errors="coerce").fillna(0.0)
    grouped = (
        base.groupby("cnpj_fundo", dropna=False)
        .agg(
            vehicle_rows=("cnpj_fundo", "size"),
            **text_aggs,
            **num_aggs,
        )
        .reset_index()
    )
    grouped["competencia"] = _competencia_label(competencia_key)
    return grouped


def _snapshot_delta_overlay(snapshot: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "cnpj_fundo",
        "nome_exibicao",
        "document_rows",
        "cedente_rows",
        "criteria_rows",
        "tem_sub_minima",
        "camadas_com_evidencia",
        "snapshot_status",
        "document_chunk_ids",
        "cedentes_top",
    ]
    if snapshot.empty or "cnpj_fundo" not in snapshot.columns:
        return pd.DataFrame(columns=columns)
    out = snapshot.copy()
    out["cnpj_fundo"] = out["cnpj_fundo"].map(normalize_cnpj)
    keep = [col for col in columns if col in out.columns]
    out = out[keep].drop_duplicates("cnpj_fundo", keep="first")
    for col in columns:
        if col not in out.columns:
            out[col] = ""
    return out[columns]


def build_industry_monthly_delta(
    *,
    vehicle_monthly: pd.DataFrame,
    snapshot: pd.DataFrame | None = None,
    metadata: dict[str, object] | None = None,
    action_reviews: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if vehicle_monthly is None or vehicle_monthly.empty or "competencia" not in vehicle_monthly.columns:
        return pd.DataFrame()
    frame = vehicle_monthly.copy()
    frame["competencia_key"] = frame["competencia"].map(_competencia_key)
    frame = frame[frame["competencia_key"].str.len().eq(6)].copy()
    if frame.empty:
        return pd.DataFrame()
    metadata = metadata or {}
    current_key = _competencia_key(metadata.get("competencia_snapshot")) or frame["competencia_key"].max()
    available = sorted(frame["competencia_key"].dropna().unique().tolist())
    previous_candidates = [key for key in available if key < current_key]
    previous_key = previous_candidates[-1] if previous_candidates else ""
    current = _vehicle_monthly_by_fund(frame, current_key)
    previous = _vehicle_monthly_by_fund(frame, previous_key) if previous_key else pd.DataFrame()

    current_ids = set(current["cnpj_fundo"]) if "cnpj_fundo" in current.columns else set()
    previous_ids = set(previous["cnpj_fundo"]) if "cnpj_fundo" in previous.columns else set()
    historical = frame[frame["competencia_key"].lt(current_key)].copy()
    if "cnpj_fundo" in historical.columns:
        historical["cnpj_fundo"] = historical["cnpj_fundo"].map(normalize_cnpj)
    elif "cnpj" in historical.columns:
        historical["cnpj_fundo"] = historical["cnpj"].map(normalize_cnpj)
    historical_ids = set(historical["cnpj_fundo"]) if "cnpj_fundo" in historical.columns else set()
    all_ids = sorted(current_ids | previous_ids)
    if not all_ids:
        return pd.DataFrame()

    current_prefixed = current.add_prefix("current_") if not current.empty else pd.DataFrame()
    previous_prefixed = previous.add_prefix("previous_") if not previous.empty else pd.DataFrame()
    base = pd.DataFrame({"cnpj_fundo": all_ids})
    if not current_prefixed.empty:
        base = base.merge(current_prefixed, left_on="cnpj_fundo", right_on="current_cnpj_fundo", how="left")
    if not previous_prefixed.empty:
        base = base.merge(previous_prefixed, left_on="cnpj_fundo", right_on="previous_cnpj_fundo", how="left")
    base["in_current"] = base["cnpj_fundo"].isin(current_ids)
    base["in_previous"] = base["cnpj_fundo"].isin(previous_ids)
    base["status_delta"] = "recorrente"
    base.loc[base["in_current"] & ~base["in_previous"] & ~base["cnpj_fundo"].isin(historical_ids), "status_delta"] = "novo_no_ime"
    base.loc[base["in_current"] & ~base["in_previous"] & base["cnpj_fundo"].isin(historical_ids), "status_delta"] = "reativado"
    base.loc[~base["in_current"] & base["in_previous"], "status_delta"] = "saiu_do_ime"

    for col in ["pl_atual", "captacao_liquida_mes", "carteira_dc", "cotistas"]:
        current_col = f"current_{col}"
        previous_col = f"previous_{col}"
        if current_col not in base.columns:
            base[current_col] = 0.0
        if previous_col not in base.columns:
            base[previous_col] = 0.0
        base[current_col] = pd.to_numeric(base[current_col], errors="coerce").fillna(0.0)
        base[previous_col] = pd.to_numeric(base[previous_col], errors="coerce").fillna(0.0)
    base["pl_delta"] = base["current_pl_atual"] - base["previous_pl_atual"]
    base["pl_delta_pct"] = base["pl_delta"] / base["previous_pl_atual"].replace(0, pd.NA)

    overlay = _snapshot_delta_overlay(snapshot if snapshot is not None else pd.DataFrame())
    if not overlay.empty:
        base = base.merge(overlay, on="cnpj_fundo", how="left")
    for col in ["document_rows", "cedente_rows", "criteria_rows", "camadas_com_evidencia"]:
        if col not in base.columns:
            base[col] = 0
        base[col] = pd.to_numeric(base[col], errors="coerce").fillna(0).astype(int)
    if "tem_sub_minima" not in base.columns:
        base["tem_sub_minima"] = False
    has_sub = base["tem_sub_minima"].astype(str).str.lower().isin({"true", "1", "sim"})
    base["needs_document_discovery"] = base["in_current"] & (
        base["document_rows"].eq(0) | base["status_delta"].isin(["novo_no_ime", "reativado"])
    )
    base["needs_cedente_review"] = base["in_current"] & base["cedente_rows"].eq(0)
    base["needs_criteria_review"] = base["in_current"] & base["criteria_rows"].eq(0)
    base["needs_subordination_review"] = base["in_current"] & ~has_sub

    pl_rank = pd.qcut(base["current_pl_atual"].rank(method="first"), q=min(5, len(base)), labels=False, duplicates="drop") if len(base) > 1 else pd.Series([0], index=base.index)
    pl_rank = pd.to_numeric(pl_rank, errors="coerce").fillna(0)
    priority = pd.Series(0.0, index=base.index)
    priority += base["status_delta"].map({"novo_no_ime": 45, "reativado": 35, "saiu_do_ime": 15, "recorrente": 5}).fillna(0)
    priority += base["needs_document_discovery"].astype(int) * 20
    priority += base["needs_cedente_review"].astype(int) * 12
    priority += base["needs_criteria_review"].astype(int) * 12
    priority += base["needs_subordination_review"].astype(int) * 6
    priority += pl_rank.astype(float) * 3
    priority += pd.to_numeric(base["current_captacao_liquida_mes"], errors="coerce").fillna(0).gt(100_000_000).astype(int) * 8
    base["priority_score"] = priority.round(1)
    base["priority_band"] = pd.cut(
        base["priority_score"],
        bins=[-1, 39, 79, float("inf")],
        labels=["baixa", "média", "alta"],
    ).astype(str)

    def actions(row: pd.Series) -> str:
        items: list[str] = []
        if row["status_delta"] in {"novo_no_ime", "reativado"}:
            items.append("descobrir documentos")
        if bool(row["needs_document_discovery"]):
            items.append("inventariar documentos")
        if bool(row["needs_cedente_review"]):
            items.append("curar cedentes/sacados")
        if bool(row["needs_criteria_review"]):
            items.append("curar critérios")
        if bool(row["needs_subordination_review"]):
            items.append("validar sub mínima")
        if row["status_delta"] == "saiu_do_ime":
            items.append("validar ausência no próximo IME")
        return " | ".join(dict.fromkeys(items)) or "monitorar"

    base["next_actions"] = base.apply(actions, axis=1)
    base["rerun_command"] = "python scripts/build_fidc_industry_documents.py && python scripts/build_fidc_industry_cedentes.py && python scripts/build_fidc_industry_criteria.py"
    base["source_artifacts"] = "vehicle_monthly.csv.gz | industry_fund_snapshot.csv.gz"

    out = pd.DataFrame(
        {
            "delta_id": [_competencia_key(current_key) + "_" + cnpj for cnpj in base["cnpj_fundo"]],
            "competencia_atual": _competencia_label(current_key),
            "competencia_anterior": _competencia_label(previous_key),
            "cnpj_fundo": base["cnpj_fundo"],
            "fundo": base.get("nome_exibicao", pd.Series("", index=base.index)).fillna("").astype(str).where(
                base.get("nome_exibicao", pd.Series("", index=base.index)).fillna("").astype(str).str.strip().ne(""),
                base.get("current_denominacao", pd.Series("", index=base.index)).fillna("").astype(str),
            ),
            "status_delta": base["status_delta"],
            "priority_band": base["priority_band"],
            "priority_score": base["priority_score"],
            "next_actions": base["next_actions"],
            "pl_atual": base["current_pl_atual"],
            "pl_anterior": base["previous_pl_atual"],
            "pl_delta": base["pl_delta"],
            "pl_delta_pct": base["pl_delta_pct"],
            "captacao_liquida_mes": base["current_captacao_liquida_mes"],
            "carteira_dc": base["current_carteira_dc"],
            "cotistas": base["current_cotistas"],
            "admin_nome": base.get("current_admin_nome", pd.Series("", index=base.index)).fillna("").astype(str),
            "gestor_nome": base.get("current_gestor_nome", pd.Series("", index=base.index)).fillna("").astype(str),
            "custodiante_nome": base.get("current_custodiante_nome", pd.Series("", index=base.index)).fillna("").astype(str),
            "segmento_principal": base.get("current_segmento_principal", pd.Series("", index=base.index)).fillna("").astype(str),
            "document_rows": base["document_rows"],
            "cedente_rows": base["cedente_rows"],
            "criteria_rows": base["criteria_rows"],
            "tem_sub_minima": has_sub,
            "camadas_com_evidencia": base["camadas_com_evidencia"],
            "snapshot_status": base.get("snapshot_status", pd.Series("", index=base.index)).fillna("").astype(str),
            "document_chunk_ids": base.get("document_chunk_ids", pd.Series("", index=base.index)).fillna("").astype(str),
            "cedentes_top": base.get("cedentes_top", pd.Series("", index=base.index)).fillna("").astype(str),
            "needs_document_discovery": base["needs_document_discovery"],
            "needs_cedente_review": base["needs_cedente_review"],
            "needs_criteria_review": base["needs_criteria_review"],
            "needs_subordination_review": base["needs_subordination_review"],
            "rerun_command": base["rerun_command"],
            "source_artifacts": base["source_artifacts"],
        }
    )
    out = apply_monthly_delta_actions(out, action_reviews)
    return out.sort_values(["priority_score", "pl_atual"], ascending=[False, False]).reset_index(drop=True)


def industry_monthly_delta_quality_summary(delta: pd.DataFrame) -> dict[str, object]:
    if delta is None or delta.empty:
        return {
            "rows": 0,
            "current_funds": 0,
            "new_funds": 0,
            "reactivated_funds": 0,
            "exited_funds": 0,
            "high_priority_rows": 0,
        }
    status = delta.get("status_delta", pd.Series(dtype=str)).astype(str)
    action_status = delta.get("status_acao", pd.Series(dtype=str)).fillna("").astype(str).replace("", "pendente")
    action_counts = action_status.value_counts().to_dict()
    high_priority_mask = delta.get("priority_band", pd.Series(dtype=str)).astype(str).eq("alta")
    normalized_action = action_status.str.strip().str.lower()
    closed_action = normalized_action.isin({"concluído", "concluido", "ignorado", "resolvido", "aprovado"})
    high_priority_open = high_priority_mask & ~closed_action
    return {
        "rows": int(len(delta)),
        "competencia_atual": _first_non_empty(delta.get("competencia_atual", pd.Series(dtype=str))),
        "competencia_anterior": _first_non_empty(delta.get("competencia_anterior", pd.Series(dtype=str))),
        "current_funds": int(status.ne("saiu_do_ime").sum()),
        "new_funds": int(status.eq("novo_no_ime").sum()),
        "reactivated_funds": int(status.eq("reativado").sum()),
        "exited_funds": int(status.eq("saiu_do_ime").sum()),
        "high_priority_rows": int(high_priority_mask.sum()),
        "high_priority_open_rows": int(high_priority_open.sum()),
        "high_priority_pending_rows": int((high_priority_mask & normalized_action.eq("pendente")).sum()),
        "high_priority_in_progress_rows": int((high_priority_mask & normalized_action.eq("em andamento")).sum()),
        "high_priority_closed_rows": int((high_priority_mask & closed_action).sum()),
        "action_status_counts": {str(key): int(value) for key, value in action_counts.items()},
        "completed_actions": int(action_status.isin(["concluído", "concluido"]).sum()),
        "ignored_actions": int(action_status.eq("ignorado").sum()),
        "needs_document_discovery": int(delta.get("needs_document_discovery", pd.Series(dtype=bool)).astype(str).str.lower().isin({"true", "1", "sim"}).sum()),
        "needs_cedente_review": int(delta.get("needs_cedente_review", pd.Series(dtype=bool)).astype(str).str.lower().isin({"true", "1", "sim"}).sum()),
        "needs_criteria_review": int(delta.get("needs_criteria_review", pd.Series(dtype=bool)).astype(str).str.lower().isin({"true", "1", "sim"}).sum()),
        "needs_subordination_review": int(delta.get("needs_subordination_review", pd.Series(dtype=bool)).astype(str).str.lower().isin({"true", "1", "sim"}).sum()),
    }


def build_monthly_delta_pipeline_manifest(
    *,
    industry_dir: Path,
    output_path: Path,
    manifest_path: Path,
    vehicle_monthly: pd.DataFrame,
    snapshot: pd.DataFrame,
    delta: pd.DataFrame,
) -> dict[str, object]:
    quality = industry_monthly_delta_quality_summary(delta)
    return {
        "schema_version": "industry-monthly-delta-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_monthly_delta",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "manual_review_in_app": True,
            "macbook_air_m4_friendly": True,
            "notes": [
                "Compara apenas a competência snapshot com a anterior para criar fila operacional mensal.",
                "Não reprocessa documentos; aponta quais CNPJs precisam de descoberta, curadoria ou validação.",
            ],
        },
        "inputs": {
            "vehicle_monthly": file_fingerprint(industry_dir / "vehicle_monthly.csv.gz"),
            "fund_snapshot": file_fingerprint(industry_dir / "industry_fund_snapshot.csv.gz"),
            "metadata": file_fingerprint(industry_dir / "metadata.json"),
            "monthly_delta_actions": file_fingerprint(industry_dir / "monthly_delta_actions.csv"),
        },
        "outputs": {
            "monthly_delta": file_fingerprint(output_path),
            "manifest": {"path": str(manifest_path)},
        },
        "stages": [
            {
                "id": "load_monthly_fund_panels",
                "label": "Carregar competências atual e anterior",
                "status": "ok" if not vehicle_monthly.empty else "empty",
                "input": str(industry_dir / "vehicle_monthly.csv.gz"),
                "output": "memoria:current_previous_funds",
                "rows": int(len(vehicle_monthly)),
                "rerun": "python scripts/build_fidc_industry_monthly_delta.py",
            },
            {
                "id": "join_structured_snapshot",
                "label": "Cruzar camadas estruturadas",
                "status": "ok" if not snapshot.empty else "empty",
                "input": str(industry_dir / "industry_fund_snapshot.csv.gz"),
                "output": "memoria:fund_delta_with_layers",
                "rows": int(len(snapshot)),
                "rerun": "python scripts/build_fidc_industry_fund_snapshot.py",
            },
            {
                "id": "prioritize_update_queue",
                "label": "Priorizar fila mensal",
                "status": "ok" if not delta.empty else "empty",
                "input": "memoria:current_previous_funds+snapshot",
                "output": str(output_path),
                "rows": int(len(delta)),
                "rerun": "python scripts/build_fidc_industry_monthly_delta.py",
            },
        ],
        "quality": quality,
    }


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


def _boolish_series(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(str).str.strip().str.lower().isin({"true", "1", "sim", "yes", "y"})


def _mode_text(values: pd.Series) -> str:
    cleaned = values.fillna("").astype(str).str.strip()
    cleaned = cleaned[cleaned.ne("")]
    if cleaned.empty:
        return ""
    return str(cleaned.value_counts().index[0])


def apply_document_chunk_actions(plan: pd.DataFrame, actions: pd.DataFrame | None) -> pd.DataFrame:
    """Apply manual chunk tracking actions onto a generated processing plan."""

    if plan is None or plan.empty:
        return pd.DataFrame() if plan is None else plan.copy()
    out = plan.copy()
    for col in ["status_lote", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        if col not in out.columns:
            out[col] = ""
    if actions is None or actions.empty or "chunk_id" not in actions.columns or "chunk_id" not in out.columns:
        out["status_lote"] = out["status_lote"].fillna("").astype(str).replace("", "pendente")
        return out

    overlay = actions.copy()
    for col in DOCUMENT_CHUNK_ACTION_COLUMNS:
        if col not in overlay.columns:
            overlay[col] = ""
    overlay = overlay[DOCUMENT_CHUNK_ACTION_COLUMNS].drop_duplicates("chunk_id", keep="last")
    out = out.merge(overlay, on="chunk_id", how="left", suffixes=("", "_review"))
    for col in ["status_lote", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        review_col = f"{col}_review"
        if review_col in out.columns:
            review_values = out[review_col].fillna("").astype(str)
            out[col] = review_values.where(review_values.str.strip().ne(""), out[col].fillna("").astype(str))
            out = out.drop(columns=[review_col])
    out["status_lote"] = out["status_lote"].fillna("").astype(str).replace("", "pendente")
    return out


def initialize_document_chunk_actions(plan: pd.DataFrame, actions: pd.DataFrame | None = None) -> pd.DataFrame:
    """Persist pending tracking rows for chunks that do not yet have an action row."""

    existing = pd.DataFrame() if actions is None else actions.copy()
    for col in DOCUMENT_CHUNK_ACTION_COLUMNS:
        if col not in existing.columns:
            existing[col] = ""
    existing = existing[DOCUMENT_CHUNK_ACTION_COLUMNS].copy()
    existing["chunk_id"] = existing["chunk_id"].fillna("").astype(str).str.strip()
    existing = existing[existing["chunk_id"].ne("")].drop_duplicates("chunk_id", keep="last")
    if plan is None or plan.empty or "chunk_id" not in plan.columns:
        return existing.reset_index(drop=True)

    plan_rows = plan.copy()
    plan_rows["chunk_id"] = plan_rows["chunk_id"].fillna("").astype(str).str.strip()
    plan_rows = plan_rows[plan_rows["chunk_id"].ne("")].drop_duplicates("chunk_id", keep="first")
    missing = plan_rows[~plan_rows["chunk_id"].isin(set(existing["chunk_id"]))].copy()
    if missing.empty:
        return existing.reset_index(drop=True)
    seeded = pd.DataFrame({"chunk_id": missing["chunk_id"].tolist()})
    seeded["status_lote"] = "pendente"
    for col in ["acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        seeded[col] = ""
    seeded = seeded[DOCUMENT_CHUNK_ACTION_COLUMNS]
    return pd.concat([existing, seeded], ignore_index=True)[DOCUMENT_CHUNK_ACTION_COLUMNS].reset_index(drop=True)


def build_document_chunk_plan(
    chunks: pd.DataFrame,
    inventory: pd.DataFrame,
    actions: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the operational plan for document chunks using persisted inventory detail."""

    if chunks is None or chunks.empty or "chunk_id" not in chunks.columns:
        return pd.DataFrame()
    plan = chunks.copy()
    plan["chunk_id"] = plan["chunk_id"].fillna("").astype(str)
    plan = plan[plan["chunk_id"].str.strip().ne("")].copy()
    if plan.empty:
        return plan

    inv = pd.DataFrame() if inventory is None else inventory.copy()
    if not inv.empty and "chunk_id" in inv.columns:
        inv["chunk_id"] = inv["chunk_id"].fillna("").astype(str)
        inv = inv[inv["chunk_id"].str.strip().ne("")].copy()
    else:
        inv = pd.DataFrame()

    if inv.empty:
        for col in [
            "inventory_docs",
            "missing_local_docs",
            "hash_pending_docs",
            "dominant_stage",
            "dominant_processing_status",
            "priority_score",
        ]:
            plan[col] = 0 if col.endswith("_docs") or col == "priority_score" else ""
    else:
        for col in ["fundo", "suggested_stage", "processing_status"]:
            if col not in inv.columns:
                inv[col] = ""
        local_ready = _boolish_series(inv.get("local_exists", pd.Series(False, index=inv.index)))
        priority = _boolish_series(inv.get("priority_2025_2026", pd.Series(False, index=inv.index)))
        hashed = inv.get("sha256", pd.Series("", index=inv.index)).fillna("").astype(str).str.strip().ne("")
        inv = inv.assign(
            _local_ready=local_ready,
            _priority=priority,
            _hashed=hashed,
            _bytes=pd.to_numeric(inv.get("bytes", pd.Series(0, index=inv.index)), errors="coerce").fillna(0),
        )
        grouped = inv.groupby("chunk_id", dropna=False)
        summary = grouped.agg(
            inventory_docs=("chunk_id", "size"),
            missing_local_docs=("_local_ready", lambda values: int((~values.astype(bool)).sum())),
            hash_pending_docs=("_hashed", lambda values: int((~values.astype(bool)).sum())),
            priority_docs_inventory=("_priority", "sum"),
            bytes_inventory=("_bytes", "sum"),
            sample_funds=("fundo", lambda values: _join_unique(values, sep=", ", limit=4)),
        ).reset_index()
        stage = grouped["suggested_stage"].apply(_mode_text).rename("dominant_stage").reset_index()
        processing = grouped["processing_status"].apply(_mode_text).rename("dominant_processing_status").reset_index()
        summary = summary.merge(stage, on="chunk_id", how="left").merge(processing, on="chunk_id", how="left")
        plan = plan.merge(summary, on="chunk_id", how="left")

    numeric_cols = [
        "document_count",
        "cnpj_count",
        "priority_2025_2026_docs",
        "local_ready_docs",
        "hashed_docs",
        "total_bytes",
        "inventory_docs",
        "missing_local_docs",
        "hash_pending_docs",
        "priority_docs_inventory",
        "bytes_inventory",
    ]
    for col in numeric_cols:
        if col not in plan.columns:
            plan[col] = 0
        plan[col] = pd.to_numeric(plan[col], errors="coerce").fillna(0)
    for col in ["dominant_stage", "dominant_processing_status", "sample_funds", "rerun_command"]:
        if col not in plan.columns:
            plan[col] = ""
        plan[col] = plan[col].fillna("").astype(str)

    plan["missing_local_docs"] = plan["missing_local_docs"].astype(int)
    plan["hash_pending_docs"] = plan["hash_pending_docs"].astype(int)
    plan["priority_docs_effective"] = plan["priority_docs_inventory"].where(
        plan["priority_docs_inventory"].gt(0),
        plan["priority_2025_2026_docs"],
    )
    plan["local_ready_ratio"] = plan["local_ready_docs"] / plan["document_count"].where(plan["document_count"].ne(0), pd.NA)
    plan["hash_ratio"] = plan["hashed_docs"] / plan["document_count"].where(plan["document_count"].ne(0), pd.NA)

    def status(row: pd.Series) -> str:
        if int(row.get("missing_local_docs", 0)) > 0:
            return "baixar"
        if int(row.get("hash_pending_docs", 0)) > 0:
            return "fingerprint"
        if str(row.get("dominant_stage", "")).strip():
            return "processar"
        return "pronto"

    def action(row: pd.Series) -> str:
        if row["chunk_status"] == "baixar":
            return "baixar documentos faltantes"
        if row["chunk_status"] == "fingerprint":
            return "atualizar fingerprint"
        if row["chunk_status"] == "processar":
            stage = str(row.get("dominant_stage", "")).replace("_", " ").strip()
            return stage or "processar lote"
        return "sem ação"

    plan["chunk_status"] = plan.apply(status, axis=1)
    plan["next_action"] = plan.apply(action, axis=1)
    plan["priority_score"] = (
        plan["priority_docs_effective"].fillna(0) * 3
        + plan["missing_local_docs"].fillna(0) * 2
        + plan["document_count"].fillna(0) * 0.01
    )
    status_order = {"baixar": 0, "fingerprint": 1, "processar": 2, "pronto": 3}
    plan["_status_order"] = plan["chunk_status"].map(status_order).fillna(9)
    plan = plan.sort_values(["_status_order", "priority_score", "chunk_id"], ascending=[True, False, True]).drop(
        columns=["_status_order"]
    ).reset_index(drop=True)
    return apply_document_chunk_actions(plan, actions)


def document_quality_summary(
    inventory: pd.DataFrame,
    chunks: pd.DataFrame,
    chunk_plan: pd.DataFrame | None = None,
) -> dict[str, object]:
    if inventory is None:
        inventory = pd.DataFrame()
    if chunks is None:
        chunks = pd.DataFrame()
    if chunk_plan is None:
        chunk_plan = pd.DataFrame()
    plan_status_counts = (
        {
            str(k): int(v)
            for k, v in chunk_plan.get("chunk_status", pd.Series(dtype=str)).fillna("").astype(str).value_counts().to_dict().items()
        }
        if not chunk_plan.empty
        else {}
    )
    if inventory.empty:
        return {
            "document_rows": 0,
            "funds": 0,
            "chunks": 0,
            "chunk_plan_rows": int(len(chunk_plan)),
            "chunk_plan_status_counts": plan_status_counts,
            "chunk_plan_open_rows": int(
                chunk_plan.get("chunk_status", pd.Series(dtype=str)).fillna("").astype(str).ne("pronto").sum()
            )
            if not chunk_plan.empty
            else 0,
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
        "chunk_plan_rows": int(len(chunk_plan)),
        "chunk_plan_status_counts": plan_status_counts,
        "chunk_plan_open_rows": int(
            chunk_plan.get("chunk_status", pd.Series(dtype=str)).fillna("").astype(str).ne("pronto").sum()
        )
        if not chunk_plan.empty
        else 0,
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


def _nonempty_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().ne("")


def _normalized_status(series: pd.Series, default: str = "pendente") -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.lower().replace("", default)


def apply_snapshot_gap_actions(gaps: pd.DataFrame, actions: pd.DataFrame | None) -> pd.DataFrame:
    if gaps is None or gaps.empty:
        return pd.DataFrame() if gaps is None else gaps.copy()
    out = gaps.copy()
    for col in ["status_lacuna", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        if col not in out.columns:
            out[col] = ""
    if actions is None or actions.empty or "gap_id" not in actions.columns or "gap_id" not in out.columns:
        out["status_lacuna"] = out["status_lacuna"].fillna("").astype(str).replace("", "pendente")
        return out
    overlay = actions.copy()
    for col in SNAPSHOT_GAP_ACTION_COLUMNS:
        if col not in overlay.columns:
            overlay[col] = ""
    overlay = overlay[SNAPSHOT_GAP_ACTION_COLUMNS].drop_duplicates("gap_id", keep="last")
    out = out.merge(overlay, on="gap_id", how="left", suffixes=("", "_review"))
    for col in ["status_lacuna", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        review_col = f"{col}_review"
        if review_col in out.columns:
            review_values = out[review_col].fillna("").astype(str)
            out[col] = review_values.where(review_values.str.strip().ne(""), out[col].fillna("").astype(str))
            out = out.drop(columns=[review_col])
    out["status_lacuna"] = out["status_lacuna"].fillna("").astype(str).replace("", "pendente")
    return out


def apply_dimension_catalog_gap_actions(gaps: pd.DataFrame, actions: pd.DataFrame | None) -> pd.DataFrame:
    if gaps is None or gaps.empty:
        return pd.DataFrame() if gaps is None else gaps.copy()
    out = gaps.copy()
    for col in ["status_lacuna", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        if col not in out.columns:
            out[col] = ""
    if (
        actions is None
        or actions.empty
        or "traceability_gap_id" not in actions.columns
        or "traceability_gap_id" not in out.columns
    ):
        out["status_lacuna"] = out["status_lacuna"].fillna("").astype(str).replace("", "pendente")
        return out
    overlay = actions.copy()
    for col in CATALOG_GAP_ACTION_COLUMNS:
        if col not in overlay.columns:
            overlay[col] = ""
    overlay = overlay[CATALOG_GAP_ACTION_COLUMNS].drop_duplicates("traceability_gap_id", keep="last")
    out = out.merge(overlay, on="traceability_gap_id", how="left", suffixes=("", "_review"))
    for col in ["status_lacuna", "acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
        review_col = f"{col}_review"
        if review_col in out.columns:
            review_values = out[review_col].fillna("").astype(str)
            out[col] = review_values.where(review_values.str.strip().ne(""), out[col].fillna("").astype(str))
            out = out.drop(columns=[review_col])
    out["status_lacuna"] = out["status_lacuna"].fillna("").astype(str).replace("", "pendente")
    return out


def build_snapshot_gap_queue(snapshot: pd.DataFrame, actions: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build the all-FIDC structural gap queue from the current fund snapshot."""

    if snapshot is None or snapshot.empty:
        return pd.DataFrame()
    frame = snapshot.copy()
    for col in [
        "pl",
        "valid_volume_2024_2026_brl",
        "valid_volume_2025_brl",
        "valid_volume_2026_brl",
        "document_rows",
        "document_local_ready",
        "cedente_rows",
        "participant_signal_rows",
        "criteria_rows",
        "criteria_subordination_rows",
    ]:
        frame[col] = pd.to_numeric(frame.get(col, pd.Series(0, index=frame.index)), errors="coerce").fillna(0.0)
    for col in ["cnpj_fundo", "nome_exibicao", "competencia", "admin_nome", "gestor_nome", "segmento_principal", "document_chunk_ids"]:
        if col not in frame.columns:
            frame[col] = ""
        frame[col] = frame[col].fillna("").astype(str)

    cnpj_norm = frame["cnpj_fundo"].map(normalize_cnpj)
    competencia = frame["competencia"].replace("", "snapshot")
    frame["gap_id"] = "snapshot_" + competencia + "_" + cnpj_norm
    priority_source = _boolish_series(frame.get("tem_emissao_2025_2026", pd.Series(False, index=frame.index)))
    priority_source = priority_source | frame["valid_volume_2025_brl"].gt(0) | frame["valid_volume_2026_brl"].gt(0)
    frame["priority_2025_2026"] = priority_source

    missing_cedente = frame["cedente_rows"].le(0)
    has_participant_signal = frame["participant_signal_rows"].gt(0)
    gap_specs = [
        ("sem documento", frame["document_rows"].le(0)),
        ("sem documento local", frame["document_local_ready"].le(0)),
        ("cedente/sacado sinalizado sem participante", missing_cedente & has_participant_signal),
        ("sem cedente/sacado", missing_cedente & ~has_participant_signal),
        ("sem critérios", frame["criteria_rows"].le(0)),
        ("sem sub mínima", frame["criteria_subordination_rows"].le(0)),
    ]
    missing_layers: list[str] = []
    gap_counts: list[int] = []
    for idx in frame.index:
        gaps = [label for label, mask in gap_specs if bool(mask.loc[idx])]
        missing_layers.append(" | ".join(gaps))
        gap_counts.append(len(gaps))
    frame["missing_layers"] = missing_layers
    frame["gap_count"] = gap_counts
    frame["gap_priority_score"] = (
        frame["gap_count"] * 10
        + frame["priority_2025_2026"].astype(int) * 20
        + frame["pl"].rank(pct=True).fillna(0.0) * 5
    ).round(1)
    frame = frame[frame["gap_count"].gt(0)].copy()
    if frame.empty:
        return frame
    frame = apply_snapshot_gap_actions(frame, actions)
    return frame.sort_values(["priority_2025_2026", "gap_priority_score", "pl"], ascending=[False, False, False]).reset_index(drop=True)


def build_dimension_catalog_gap_queue(catalog: pd.DataFrame, actions: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build traceability gaps for structured dimensions used by heatmaps and deep dives."""

    if catalog is None or catalog.empty or "dimension_id" not in catalog.columns:
        return pd.DataFrame()
    frame = catalog.copy()
    for col in [
        "cnpj_fundo",
        "nome_exibicao",
        "dimension_id",
        "dimension_label",
        "dimension_value",
        "source_layer",
        "source_document",
        "source_page",
        "source_date",
        "source_method",
        "confidence_score",
        "review_status",
        "participant_type",
        "participant_cnpj",
        "is_curated",
        "priority_2025_2026",
    ]:
        if col not in frame.columns:
            frame[col] = ""
    source_layer = frame["source_layer"].fillna("").astype(str)
    is_curated = _boolish_series(frame["is_curated"])
    doc_expected = is_curated | source_layer.isin({"cedente", "criteria"}) | _nonempty_series(frame["source_document"])
    review_expected = is_curated | source_layer.isin({"cedente", "criteria"})
    has_source_layer = _nonempty_series(frame["source_layer"])
    has_source_document = _nonempty_series(frame["source_document"])
    has_source_page = _nonempty_series(frame["source_page"])
    has_source_method = _nonempty_series(frame["source_method"])
    has_confidence = pd.to_numeric(frame["confidence_score"], errors="coerce").notna()
    has_review_status = _nonempty_series(frame["review_status"])
    missing: list[str] = []
    scores: list[int] = []
    for idx in frame.index:
        fields: list[str] = []
        if not bool(has_source_layer.loc[idx]):
            fields.append("fonte")
        if not bool(has_source_method.loc[idx]):
            fields.append("método")
        if not bool(has_confidence.loc[idx]):
            fields.append("score")
        if bool(doc_expected.loc[idx]) and not bool(has_source_document.loc[idx]):
            fields.append("documento")
        if bool(doc_expected.loc[idx]) and not bool(has_source_page.loc[idx]):
            fields.append("página")
        if bool(review_expected.loc[idx]) and not bool(has_review_status.loc[idx]):
            fields.append("status revisão")
        missing.append(" | ".join(fields))
        scores.append(len(fields) + int(bool(is_curated.loc[idx])) + int(bool(doc_expected.loc[idx])))
    frame["missing_traceability_fields"] = missing
    frame["traceability_gap_score"] = scores
    out = frame[frame["missing_traceability_fields"].astype(str).str.strip().ne("")].copy()
    if out.empty:
        return out
    out["cnpj_fundo_norm"] = out["cnpj_fundo"].map(normalize_cnpj)
    value_hash = out["dimension_value"].fillna("").astype(str).map(
        lambda value: hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    )
    out["traceability_gap_id"] = (
        "catalog_"
        + out["dimension_id"].fillna("").astype(str).str.replace(r"[^A-Za-z0-9_]+", "_", regex=True)
        + "_"
        + out["cnpj_fundo_norm"].fillna("").astype(str)
        + "_"
        + value_hash
    )
    out["priority_2025_2026"] = _boolish_series(out["priority_2025_2026"])
    out["confidence_score"] = pd.to_numeric(out["confidence_score"], errors="coerce")
    out = apply_dimension_catalog_gap_actions(out, actions)
    return out.sort_values(
        ["priority_2025_2026", "traceability_gap_score", "dimension_label", "dimension_value"],
        ascending=[False, False, True, True],
    ).reset_index(drop=True)


def _queue_status_from(row: pd.Series, *columns: str) -> str:
    for col in columns:
        text = str(row.get(col, "") or "").strip()
        if text:
            return text
    return "pendente"


def _queue_review_fields(row: pd.Series) -> dict[str, object]:
    return {
        "status_curadoria": _queue_status_from(row, "status_lacuna", "status_acao", "status_lote"),
        "acao_revisada": row.get("acao_revisada", ""),
        "responsavel": row.get("responsavel", ""),
        "prazo": row.get("prazo", ""),
        "notas": row.get("notas", ""),
        "updated_at_utc": row.get("updated_at_utc", ""),
    }


def build_industry_curation_queue(
    *,
    snapshot: pd.DataFrame | None = None,
    monthly_delta: pd.DataFrame | None = None,
    document_chunk_plan: pd.DataFrame | None = None,
    dimension_catalog: pd.DataFrame | None = None,
    snapshot_gap_actions: pd.DataFrame | None = None,
    catalog_gap_actions: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build a single all-FIDC operational curation queue for the Industry tab."""

    rows: list[dict[str, object]] = []

    snapshot_gaps = build_snapshot_gap_queue(snapshot if snapshot is not None else pd.DataFrame(), snapshot_gap_actions)
    for _, row in snapshot_gaps.iterrows():
        review = _queue_review_fields(row)
        rows.append(
            {
                "queue_id": f"snapshot_gap:{row.get('gap_id', '')}",
                "queue_domain": "snapshot_gap",
                "record_id": row.get("gap_id", ""),
                "competencia": row.get("competencia", ""),
                "cnpj_fundo": normalize_cnpj(row.get("cnpj_fundo", "")),
                "nome_exibicao": row.get("nome_exibicao", ""),
                "admin_nome": row.get("admin_nome", ""),
                "gestor_nome": row.get("gestor_nome", ""),
                "segmento_principal": row.get("segmento_principal", ""),
                "pl": row.get("pl", 0),
                "priority_2025_2026": bool(row.get("priority_2025_2026", False)),
                "priority_score": row.get("gap_priority_score", 0),
                "priority_band": "alta" if bool(row.get("priority_2025_2026", False)) else "média",
                "action_type": "completar camadas estruturadas",
                "next_action": row.get("missing_layers", ""),
                "gap_summary": row.get("missing_layers", ""),
                "source_artifacts": "industry_fund_snapshot.csv.gz | snapshot_gap_actions.csv",
                "source_document": row.get("document_chunk_ids", ""),
                "source_page": "",
                "source_method": "snapshot_gap_queue",
                "confidence_score": "",
                "rerun_command": "python scripts/build_fidc_industry_fund_snapshot.py",
                **review,
            }
        )

    delta = pd.DataFrame() if monthly_delta is None else monthly_delta.copy()
    if not delta.empty and "delta_id" in delta.columns:
        status = _normalized_status(delta.get("status_acao", pd.Series("", index=delta.index)))
        open_delta = delta[~status.isin({"concluído", "concluido", "ignorado"})].copy()
        for _, row in open_delta.iterrows():
            review = _queue_review_fields(row)
            rows.append(
                {
                    "queue_id": f"monthly_delta:{row.get('delta_id', '')}",
                    "queue_domain": "monthly_delta",
                    "record_id": row.get("delta_id", ""),
                    "competencia": row.get("competencia_atual", ""),
                    "cnpj_fundo": normalize_cnpj(row.get("cnpj_fundo", "")),
                    "nome_exibicao": row.get("fundo", ""),
                    "admin_nome": row.get("admin_nome", ""),
                    "gestor_nome": row.get("gestor_nome", ""),
                    "segmento_principal": row.get("segmento_principal", ""),
                    "pl": row.get("pl_atual", 0),
                    "priority_2025_2026": True,
                    "priority_score": row.get("priority_score", 0),
                    "priority_band": row.get("priority_band", ""),
                    "action_type": row.get("status_delta", ""),
                    "next_action": row.get("next_actions", ""),
                    "gap_summary": row.get("next_actions", ""),
                    "source_artifacts": row.get("source_artifacts", "industry_monthly_delta.csv.gz"),
                    "source_document": row.get("document_chunk_ids", ""),
                    "source_page": "",
                    "source_method": "monthly_delta",
                    "confidence_score": "",
                    "rerun_command": row.get("rerun_command", "python scripts/build_fidc_industry_monthly_delta.py"),
                    **review,
                }
            )

    chunk_plan = pd.DataFrame() if document_chunk_plan is None else document_chunk_plan.copy()
    if not chunk_plan.empty and "chunk_id" in chunk_plan.columns:
        status = _normalized_status(chunk_plan.get("status_lote", pd.Series("", index=chunk_plan.index)))
        open_chunks = chunk_plan[~status.isin({"processado", "ignorado", "concluído", "concluido"})].copy()
        for _, row in open_chunks.iterrows():
            review = _queue_review_fields(row)
            rows.append(
                {
                    "queue_id": f"document_chunk:{row.get('chunk_id', '')}",
                    "queue_domain": "document_chunk",
                    "record_id": row.get("chunk_id", ""),
                    "competencia": row.get("document_date_max", ""),
                    "cnpj_fundo": row.get("sample_cnpjs", ""),
                    "nome_exibicao": row.get("sample_funds", ""),
                    "admin_nome": "",
                    "gestor_nome": "",
                    "segmento_principal": row.get("document_classes", ""),
                    "pl": 0,
                    "priority_2025_2026": pd.to_numeric(pd.Series([row.get("priority_docs_effective", 0)]), errors="coerce").fillna(0).iloc[0] > 0,
                    "priority_score": row.get("priority_score", 0),
                    "priority_band": "alta" if str(row.get("chunk_status", "")) in {"baixar", "fingerprint"} else "média",
                    "action_type": row.get("chunk_status", ""),
                    "next_action": row.get("next_action", ""),
                    "gap_summary": (
                        f"{row.get('document_count', 0)} docs; "
                        f"{row.get('missing_local_docs', 0)} sem local; {row.get('hash_pending_docs', 0)} sem hash"
                    ),
                    "source_artifacts": "document_chunk_plan.csv | document_processing_chunks.csv",
                    "source_document": row.get("document_classes", ""),
                    "source_page": "",
                    "source_method": "document_chunk_plan",
                    "confidence_score": "",
                    "rerun_command": row.get("rerun_command", "python scripts/build_fidc_industry_document_chunk_plan.py"),
                    **review,
                }
            )

    catalog_gaps = build_dimension_catalog_gap_queue(
        dimension_catalog if dimension_catalog is not None else pd.DataFrame(),
        catalog_gap_actions,
    )
    for _, row in catalog_gaps.iterrows():
        review = _queue_review_fields(row)
        rows.append(
            {
                "queue_id": f"catalog_gap:{row.get('traceability_gap_id', '')}",
                "queue_domain": "catalog_gap",
                "record_id": row.get("traceability_gap_id", ""),
                "competencia": row.get("source_date", ""),
                "cnpj_fundo": normalize_cnpj(row.get("cnpj_fundo", "")),
                "nome_exibicao": row.get("nome_exibicao", ""),
                "admin_nome": "",
                "gestor_nome": "",
                "segmento_principal": row.get("dimension_label", ""),
                "pl": 0,
                "priority_2025_2026": bool(row.get("priority_2025_2026", False)),
                "priority_score": row.get("traceability_gap_score", 0),
                "priority_band": "alta" if bool(row.get("priority_2025_2026", False)) else "média",
                "action_type": "completar rastreabilidade",
                "next_action": row.get("missing_traceability_fields", ""),
                "gap_summary": f"{row.get('dimension_label', '')}: {row.get('dimension_value', '')}",
                "source_artifacts": "industry_dimension_catalog.csv.gz | dimension_catalog_gap_actions.csv",
                "source_document": row.get("source_document", ""),
                "source_page": row.get("source_page", ""),
                "source_method": row.get("source_method", ""),
                "confidence_score": row.get("confidence_score", ""),
                "rerun_command": "python scripts/build_fidc_industry_dimensions.py",
                **review,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "queue_id",
                "queue_domain",
                "record_id",
                "competencia",
                "cnpj_fundo",
                "nome_exibicao",
                "priority_score",
                "priority_band",
                "status_curadoria",
                "action_type",
                "next_action",
            ]
        )
    out = pd.DataFrame(rows)
    out["priority_score"] = pd.to_numeric(out.get("priority_score"), errors="coerce").fillna(0.0)
    out["pl"] = pd.to_numeric(out.get("pl"), errors="coerce").fillna(0.0)
    out["status_curadoria"] = _normalized_status(out.get("status_curadoria", pd.Series("", index=out.index)))
    domain_order = {"monthly_delta": 0, "snapshot_gap": 1, "document_chunk": 2, "catalog_gap": 3}
    status_order = {"bloqueado": 0, "pendente": 1, "em andamento": 2, "corrigido": 5, "aceito": 5, "ignorado": 6, "processado": 6}
    priority_order = {"alta": 0, "média": 1, "media": 1, "baixa": 2}
    out["_domain_order"] = out["queue_domain"].map(domain_order).fillna(9)
    out["_status_order"] = out["status_curadoria"].map(status_order).fillna(3)
    out["_priority_order"] = out["priority_band"].fillna("").astype(str).str.lower().map(priority_order).fillna(4)
    return out.sort_values(
        ["_status_order", "_priority_order", "priority_score", "pl", "_domain_order", "queue_id"],
        ascending=[True, True, False, False, True, True],
    ).drop(columns=["_domain_order", "_status_order", "_priority_order"]).reset_index(drop=True)


def industry_curation_queue_quality_summary(queue: pd.DataFrame) -> dict[str, object]:
    if queue is None or queue.empty:
        return {
            "rows": 0,
            "funds": 0,
            "open_rows": 0,
            "high_priority_rows": 0,
            "high_priority_open_rows": 0,
            "domain_counts": {},
            "status_counts": {},
        }
    status = _normalized_status(queue.get("status_curadoria", pd.Series("", index=queue.index)))
    open_status = ~status.isin({"corrigido", "aceito", "ignorado", "processado", "concluído", "concluido"})
    domain = queue.get("queue_domain", pd.Series("", index=queue.index)).fillna("").astype(str)
    priority = queue.get("priority_band", pd.Series("", index=queue.index)).fillna("").astype(str).str.lower()
    high_priority = priority.eq("alta")
    cnpj = queue.get("cnpj_fundo", pd.Series("", index=queue.index)).fillna("").astype(str)
    return {
        "rows": int(len(queue)),
        "funds": int(cnpj.map(normalize_cnpj).replace("", pd.NA).dropna().nunique()),
        "open_rows": int(open_status.sum()),
        "high_priority_rows": int(high_priority.sum()),
        "high_priority_open_rows": int((high_priority & open_status).sum()),
        "high_priority_pending_rows": int((high_priority & status.eq("pendente")).sum()),
        "high_priority_in_progress_rows": int((high_priority & status.eq("em andamento")).sum()),
        "high_priority_closed_rows": int((high_priority & ~open_status).sum()),
        "priority_2025_2026_rows": int(_boolish_series(queue.get("priority_2025_2026", pd.Series(False, index=queue.index))).sum()),
        "domain_counts": {str(k): int(v) for k, v in domain.value_counts().to_dict().items()},
        "status_counts": {str(k): int(v) for k, v in status.value_counts().to_dict().items()},
    }


def initialize_curation_queue_actions(
    queue: pd.DataFrame,
    *,
    monthly_delta_actions: pd.DataFrame | None = None,
    snapshot_gap_actions: pd.DataFrame | None = None,
    catalog_gap_actions: pd.DataFrame | None = None,
    document_chunk_actions: pd.DataFrame | None = None,
    priority_bands: tuple[str, ...] = ("alta",),
) -> dict[str, pd.DataFrame]:
    """Create pending domain action rows for curation queue items without decisions."""

    specs = {
        "monthly_delta": ("record_id", "delta_id", "status_acao", MONTHLY_DELTA_ACTION_COLUMNS, monthly_delta_actions),
        "snapshot_gap": ("record_id", "gap_id", "status_lacuna", SNAPSHOT_GAP_ACTION_COLUMNS, snapshot_gap_actions),
        "catalog_gap": ("record_id", "traceability_gap_id", "status_lacuna", CATALOG_GAP_ACTION_COLUMNS, catalog_gap_actions),
        "document_chunk": ("record_id", "chunk_id", "status_lote", DOCUMENT_CHUNK_ACTION_COLUMNS, document_chunk_actions),
    }
    outputs: dict[str, pd.DataFrame] = {}
    queue_frame = pd.DataFrame() if queue is None else queue.copy()
    for domain, (queue_id_col, action_id_col, status_col, columns, existing_actions) in specs.items():
        existing = pd.DataFrame() if existing_actions is None else existing_actions.copy()
        for col in columns:
            if col not in existing.columns:
                existing[col] = ""
        existing = existing[columns].copy()
        existing[action_id_col] = existing[action_id_col].map(_audit_value)
        existing = existing[existing[action_id_col].ne("")].drop_duplicates(action_id_col, keep="last")
        if queue_frame.empty or "queue_domain" not in queue_frame.columns or queue_id_col not in queue_frame.columns:
            outputs[domain] = existing.reset_index(drop=True)
            continue

        subset = queue_frame[queue_frame["queue_domain"].fillna("").astype(str).eq(domain)].copy()
        if priority_bands and "priority_band" in subset.columns:
            bands = {str(value).strip().lower() for value in priority_bands if str(value).strip()}
            priority = subset["priority_band"].fillna("").astype(str).str.strip().str.lower()
            subset = subset[priority.isin(bands)].copy()
        if subset.empty:
            outputs[domain] = existing.reset_index(drop=True)
            continue
        subset[action_id_col] = subset[queue_id_col].map(_audit_value)
        subset = subset[subset[action_id_col].ne("")].drop_duplicates(action_id_col, keep="first")
        missing = subset[~subset[action_id_col].isin(set(existing[action_id_col]))].copy()
        if missing.empty:
            outputs[domain] = existing.reset_index(drop=True)
            continue
        seeded = pd.DataFrame({action_id_col: missing[action_id_col].tolist()})
        seeded[status_col] = "pendente"
        for col in ["acao_revisada", "responsavel", "prazo", "notas", "updated_at_utc"]:
            seeded[col] = ""
        seeded = seeded[columns]
        outputs[domain] = pd.concat([existing, seeded], ignore_index=True)[columns].reset_index(drop=True)
    return outputs


def _single_cnpj_or_empty(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 14:
        return ""
    return digits


def build_industry_curation_queue_summary(queue: pd.DataFrame) -> pd.DataFrame:
    """Build compact operational rollups from the granular all-FIDC queue."""

    if queue is None or queue.empty:
        return pd.DataFrame(columns=CURATION_QUEUE_SUMMARY_COLUMNS)

    frame = queue.copy()
    for col in [
        "queue_domain",
        "status_curadoria",
        "priority_band",
        "cnpj_fundo",
        "nome_exibicao",
        "admin_nome",
        "gestor_nome",
        "segmento_principal",
        "action_type",
        "next_action",
        "gap_summary",
        "source_document",
        "rerun_command",
        "competencia",
    ]:
        if col not in frame.columns:
            frame[col] = ""
        frame[col] = frame[col].fillna("").astype(str)
    frame["status_curadoria"] = _normalized_status(frame["status_curadoria"])
    frame["priority_band"] = frame["priority_band"].replace("", "n/d")
    frame["cnpj_fundo_norm"] = frame["cnpj_fundo"].map(_single_cnpj_or_empty)
    frame["priority_2025_2026_bool"] = _boolish_series(
        frame.get("priority_2025_2026", pd.Series(False, index=frame.index))
    )
    frame["priority_score_num"] = pd.to_numeric(frame.get("priority_score", pd.Series(0, index=frame.index)), errors="coerce").fillna(0.0)
    frame["pl_num"] = pd.to_numeric(frame.get("pl", pd.Series(0, index=frame.index)), errors="coerce").fillna(0.0)
    closed = {"corrigido", "aceito", "ignorado", "processado", "concluído", "concluido"}
    frame["is_open"] = ~frame["status_curadoria"].isin(closed)
    frame["is_high_priority"] = frame["priority_band"].str.lower().eq("alta")
    frame["competencia_key"] = frame["competencia"].map(_competencia_key)

    def scope_label(group: pd.DataFrame, summary_type: str) -> str:
        if summary_type == "frente_status":
            parts = [
                _first_nonempty(group["queue_domain"]),
                _first_nonempty(group["status_curadoria"]),
                _first_nonempty(group["priority_band"]),
            ]
            return " · ".join(part for part in parts if part)
        if summary_type == "fidc_backlog":
            return _first_nonempty(group["nome_exibicao"]) or _first_nonempty(group["cnpj_fundo_norm"])
        if summary_type == "admin_backlog":
            return _first_nonempty(group["admin_nome"])
        if summary_type == "segment_backlog":
            return _first_nonempty(group["segmento_principal"])
        return summary_type

    def summarize_group(group: pd.DataFrame, summary_type: str, summary_id: str) -> dict[str, object]:
        known_funds = group[group["cnpj_fundo_norm"].str.strip().ne("")]
        if known_funds.empty:
            pl_reference = float(group["pl_num"].max()) if not group.empty else 0.0
            fund_count = 0
        else:
            pl_reference = float(known_funds.groupby("cnpj_fundo_norm")["pl_num"].max().sum())
            fund_count = int(known_funds["cnpj_fundo_norm"].nunique())
        latest_key = _first_nonempty(pd.Series([max(group["competencia_key"]) if group["competencia_key"].ne("").any() else ""]))
        return {
            "summary_id": summary_id,
            "summary_type": summary_type,
            "rank": 0,
            "scope_label": scope_label(group, summary_type),
            "queue_domain": _first_nonempty(group["queue_domain"]) if summary_type == "frente_status" else "",
            "status_curadoria": _first_nonempty(group["status_curadoria"]) if summary_type == "frente_status" else "",
            "priority_band": _first_nonempty(group["priority_band"]) if summary_type == "frente_status" else "",
            "cnpj_fundo": _first_nonempty(group["cnpj_fundo_norm"]) if summary_type == "fidc_backlog" else "",
            "nome_exibicao": _first_nonempty(group["nome_exibicao"]) if summary_type == "fidc_backlog" else "",
            "admin_nome": _first_nonempty(group["admin_nome"]),
            "gestor_nome": _first_nonempty(group["gestor_nome"]) if summary_type == "fidc_backlog" else "",
            "segmento_principal": _first_nonempty(group["segmento_principal"]) if summary_type in {"fidc_backlog", "segment_backlog"} else "",
            "rows": int(len(group)),
            "open_rows": int(group["is_open"].sum()),
            "closed_rows": int((~group["is_open"]).sum()),
            "high_priority_rows": int(group["is_high_priority"].sum()),
            "priority_2025_2026_rows": int(group["priority_2025_2026_bool"].sum()),
            "funds": fund_count,
            "max_priority_score": float(group["priority_score_num"].max()) if not group.empty else 0.0,
            "pl_reference_brl": pl_reference,
            "latest_competencia": _competencia_label(latest_key) if latest_key else "",
            "domains": _join_unique(group["queue_domain"], limit=5),
            "status_mix": _join_unique(group["status_curadoria"], limit=5),
            "priority_mix": _join_unique(group["priority_band"], limit=5),
            "action_types": _join_unique(group["action_type"], limit=5),
            "next_actions_sample": _join_unique(group["next_action"], limit=4),
            "gap_sample": _join_unique(group["gap_summary"], limit=4),
            "source_documents_sample": _join_unique(group["source_document"], limit=4),
            "rerun_commands_sample": _join_unique(group["rerun_command"], limit=3),
        }

    def grouped_records(summary_type: str, group_cols: list[str], subset: pd.DataFrame) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        if subset.empty:
            return records
        for keys, group in subset.groupby(group_cols, dropna=False, sort=False):
            key_tuple = keys if isinstance(keys, tuple) else (keys,)
            key_text = "|".join(str(value or "") for value in key_tuple)
            records.append(summarize_group(group, summary_type, f"{summary_type}:{key_text}"))
        return records

    records: list[dict[str, object]] = []
    records.extend(grouped_records("frente_status", ["queue_domain", "status_curadoria", "priority_band"], frame))
    records.extend(grouped_records("fidc_backlog", ["cnpj_fundo_norm"], frame[frame["cnpj_fundo_norm"].str.strip().ne("")]))
    records.extend(grouped_records("admin_backlog", ["admin_nome"], frame[frame["admin_nome"].str.strip().ne("")]))
    records.extend(grouped_records("segment_backlog", ["segmento_principal"], frame[frame["segmento_principal"].str.strip().ne("")]))
    if not records:
        return pd.DataFrame(columns=CURATION_QUEUE_SUMMARY_COLUMNS)

    out = pd.DataFrame(records)
    type_order = {"frente_status": 0, "fidc_backlog": 1, "admin_backlog": 2, "segment_backlog": 3}
    out["type_order"] = out["summary_type"].map(type_order).fillna(9)
    out = out.sort_values(
        ["type_order", "high_priority_rows", "open_rows", "max_priority_score", "pl_reference_brl", "scope_label"],
        ascending=[True, False, False, False, False, True],
    ).reset_index(drop=True)
    out["rank"] = out.groupby("summary_type").cumcount() + 1
    out = out.drop(columns=["type_order"])
    for col in CURATION_QUEUE_SUMMARY_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    return out[CURATION_QUEUE_SUMMARY_COLUMNS]


def build_curation_queue_pipeline_manifest(
    *,
    industry_dir: Path,
    output_path: Path,
    manifest_path: Path,
    summary_path: Path | None = None,
    snapshot: pd.DataFrame,
    monthly_delta: pd.DataFrame,
    document_chunk_plan: pd.DataFrame,
    dimension_catalog: pd.DataFrame,
    queue: pd.DataFrame,
    summary: pd.DataFrame | None = None,
) -> dict[str, object]:
    quality = industry_curation_queue_quality_summary(queue)
    if summary is not None and not summary.empty:
        summary_type = summary.get("summary_type", pd.Series("", index=summary.index)).fillna("").astype(str)
        quality.update(
            {
                "summary_rows": int(len(summary)),
                "summary_type_counts": {str(k): int(v) for k, v in summary_type.value_counts().to_dict().items()},
                "fund_backlog_rows": int(summary_type.eq("fidc_backlog").sum()),
                "admin_backlog_rows": int(summary_type.eq("admin_backlog").sum()),
                "segment_backlog_rows": int(summary_type.eq("segment_backlog").sum()),
            }
        )
    else:
        quality.update(
            {
                "summary_rows": 0,
                "summary_type_counts": {},
                "fund_backlog_rows": 0,
                "admin_backlog_rows": 0,
                "segment_backlog_rows": 0,
            }
        )
    outputs = {
        "curation_queue": file_fingerprint(output_path),
        "manifest": {"path": str(manifest_path)},
    }
    if summary_path is not None:
        outputs["curation_queue_summary"] = file_fingerprint(summary_path)
    return {
        "schema_version": "industry-curation-queue-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_curation_queue",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "manual_review_in_app": True,
            "notes": [
                "A fila unifica delta mensal, lacunas all-FIDCs do snapshot, chunks documentais e rastreabilidade do catálogo.",
                "As ações continuam sendo editadas nas telas específicas; este artefato consolida prioridades para o fechamento mensal.",
            ],
        },
        "inputs": {
            "fund_snapshot": file_fingerprint(industry_dir / "industry_fund_snapshot.csv.gz"),
            "monthly_delta": file_fingerprint(industry_dir / "industry_monthly_delta.csv.gz"),
            "document_chunk_plan": file_fingerprint(industry_dir / "document_chunk_plan.csv"),
            "dimension_catalog": file_fingerprint(industry_dir / "industry_dimension_catalog.csv.gz"),
            "snapshot_gap_actions": file_fingerprint(industry_dir / "snapshot_gap_actions.csv"),
            "catalog_gap_actions": file_fingerprint(industry_dir / "dimension_catalog_gap_actions.csv"),
            "monthly_delta_actions": file_fingerprint(industry_dir / "monthly_delta_actions.csv"),
            "document_chunk_actions": file_fingerprint(industry_dir / "document_chunk_actions.csv"),
        },
        "outputs": outputs,
        "stages": [
            {
                "id": "snapshot_all_fidcs_gaps",
                "label": "Lacunas estruturais all FIDCs",
                "status": "ok" if snapshot is not None and not snapshot.empty else "empty",
                "rows": int(len(snapshot)) if snapshot is not None else 0,
                "rerun": "python scripts/build_fidc_industry_fund_snapshot.py",
            },
            {
                "id": "monthly_delta_queue",
                "label": "Delta mensal",
                "status": "ok" if monthly_delta is not None and not monthly_delta.empty else "empty",
                "rows": int(len(monthly_delta)) if monthly_delta is not None else 0,
                "rerun": "python scripts/build_fidc_industry_monthly_delta.py",
            },
            {
                "id": "document_chunk_queue",
                "label": "Chunks documentais",
                "status": "ok" if document_chunk_plan is not None and not document_chunk_plan.empty else "empty",
                "rows": int(len(document_chunk_plan)) if document_chunk_plan is not None else 0,
                "rerun": "python scripts/build_fidc_industry_document_chunk_plan.py",
            },
            {
                "id": "catalog_traceability_queue",
                "label": "Rastreabilidade do catálogo",
                "status": "ok" if dimension_catalog is not None and not dimension_catalog.empty else "empty",
                "rows": int(len(dimension_catalog)) if dimension_catalog is not None else 0,
                "rerun": "python scripts/build_fidc_industry_dimensions.py",
            },
            {
                "id": "persist_unified_queue",
                "label": "Fila única de curadoria",
                "status": "ok" if output_path.exists() else "empty",
                "rows": int(len(queue)),
                "rerun": "python scripts/build_fidc_industry_curation_queue.py",
            },
            {
                "id": "persist_operational_summary",
                "label": "Resumo operacional da fila",
                "status": "ok" if summary_path is not None and summary_path.exists() else "empty",
                "rows": int(len(summary)) if summary is not None else 0,
                "rerun": "python scripts/build_fidc_industry_curation_queue.py",
            },
        ],
        "quality": quality,
    }


def _open_queue_mask(frame: pd.DataFrame, status_column: str = "status_curadoria") -> pd.Series:
    status = _normalized_status(frame.get(status_column, pd.Series("", index=frame.index)))
    return ~status.isin({"corrigido", "aceito", "ignorado", "processado", "concluído", "concluido", "resolvido", "aprovado"})


def _chunk_id_parts(value: object) -> list[str]:
    parts = re.split(r"\s*\|\s*|,\s*|;\s*", str(value or ""))
    return [part.strip() for part in parts if part.strip()]


def build_incremental_onboarding_plan(
    *,
    monthly_delta: pd.DataFrame,
    curation_queue: pd.DataFrame | None = None,
    document_chunk_plan: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the per-FIDC onboarding checklist for new/reactivated monthly entrants."""

    if monthly_delta is None or monthly_delta.empty:
        return pd.DataFrame()
    delta = monthly_delta.copy()
    for col in ["status_delta", "cnpj_fundo", "delta_id"]:
        if col not in delta.columns:
            delta[col] = ""
    delta["cnpj_fundo"] = delta["cnpj_fundo"].map(normalize_cnpj)
    status_delta = delta["status_delta"].fillna("").astype(str).str.lower()
    delta = delta[status_delta.isin({"novo_no_ime", "reativado"}) & delta["cnpj_fundo"].astype(str).str.len().eq(14)].copy()
    if delta.empty:
        return pd.DataFrame()

    queue_summary = pd.DataFrame()
    queue = pd.DataFrame() if curation_queue is None else curation_queue.copy()
    if not queue.empty and "cnpj_fundo" in queue.columns:
        queue["cnpj_fundo"] = queue["cnpj_fundo"].map(normalize_cnpj)
        queue = queue[queue["cnpj_fundo"].astype(str).str.len().eq(14)].copy()
        if not queue.empty:
            queue["status_curadoria"] = _normalized_status(queue.get("status_curadoria", pd.Series("", index=queue.index)))
            queue["is_open"] = _open_queue_mask(queue)
            queue["is_high_priority_open"] = queue["is_open"] & queue.get("priority_band", pd.Series("", index=queue.index)).fillna("").astype(str).str.lower().eq("alta")
            queue_summary = (
                queue.groupby("cnpj_fundo", dropna=False)
                .agg(
                    open_queue_rows=("is_open", "sum"),
                    open_high_priority_rows=("is_high_priority_open", "sum"),
                    queue_domains=("queue_domain", lambda values: _join_unique(values, limit=8)),
                    queue_action_types=("action_type", lambda values: _join_unique(values, limit=8)),
                    queue_next_actions=("next_action", lambda values: _join_unique(values, limit=8)),
                    queue_rerun_commands=("rerun_command", lambda values: _join_unique(values, limit=5)),
                    queue_status_mix=("status_curadoria", lambda values: _join_unique(values, limit=8)),
                )
                .reset_index()
            )

    chunk_status_by_id: dict[str, str] = {}
    chunk_action_by_id: dict[str, str] = {}
    chunks = pd.DataFrame() if document_chunk_plan is None else document_chunk_plan.copy()
    if not chunks.empty and "chunk_id" in chunks.columns:
        chunks["chunk_id"] = chunks["chunk_id"].fillna("").astype(str)
        status_col = "status_lote" if "status_lote" in chunks.columns else "chunk_status"
        chunks[status_col] = _normalized_status(chunks.get(status_col, pd.Series("", index=chunks.index)))
        chunk_status_by_id = chunks.set_index("chunk_id")[status_col].to_dict()
        if "next_action" in chunks.columns:
            chunk_action_by_id = chunks.set_index("chunk_id")["next_action"].fillna("").astype(str).to_dict()

    if not queue_summary.empty:
        delta = delta.merge(queue_summary, on="cnpj_fundo", how="left")
    for col in [
        "open_queue_rows",
        "open_high_priority_rows",
        "queue_domains",
        "queue_action_types",
        "queue_next_actions",
        "queue_rerun_commands",
        "queue_status_mix",
    ]:
        if col not in delta.columns:
            delta[col] = 0 if col.endswith("_rows") else ""
    delta["open_queue_rows"] = pd.to_numeric(delta["open_queue_rows"], errors="coerce").fillna(0).astype(int)
    delta["open_high_priority_rows"] = pd.to_numeric(delta["open_high_priority_rows"], errors="coerce").fillna(0).astype(int)

    for col in ["document_rows", "cedente_rows", "criteria_rows", "camadas_com_evidencia", "priority_score", "pl_atual"]:
        if col not in delta.columns:
            delta[col] = 0
        delta[col] = pd.to_numeric(delta[col], errors="coerce").fillna(0)
    for col in [
        "needs_document_discovery",
        "needs_cedente_review",
        "needs_criteria_review",
        "needs_subordination_review",
        "tem_sub_minima",
    ]:
        if col not in delta.columns:
            delta[col] = False
        delta[col] = _boolish_series(delta[col])

    def chunk_statuses(value: object) -> tuple[str, str]:
        chunk_ids = _chunk_id_parts(value)
        statuses = [chunk_status_by_id.get(chunk_id, "") for chunk_id in chunk_ids]
        actions = [chunk_action_by_id.get(chunk_id, "") for chunk_id in chunk_ids]
        return _join_unique(pd.Series(statuses), limit=6), _join_unique(pd.Series(actions), limit=6)

    chunk_pairs = delta.get("document_chunk_ids", pd.Series("", index=delta.index)).map(chunk_statuses)
    delta["document_chunk_statuses"] = [pair[0] for pair in chunk_pairs]
    delta["document_chunk_actions"] = [pair[1] for pair in chunk_pairs]

    discovery_ok = delta["document_rows"].gt(0)
    delta["discovery_status"] = "ok"
    delta.loc[~discovery_ok, "discovery_status"] = "bloqueado"
    delta["discovery_evidence"] = (
        delta["document_rows"].astype(int).astype(str)
        + " docs; chunks "
        + delta.get("document_chunk_ids", pd.Series("", index=delta.index)).fillna("").astype(str).replace("", "n/d")
    )

    chunk_status = delta["document_chunk_statuses"].fillna("").astype(str).str.lower()
    no_chunks = delta.get("document_chunk_ids", pd.Series("", index=delta.index)).fillna("").astype(str).str.strip().eq("")
    delta["processing_status"] = "ok"
    delta.loc[delta["document_rows"].le(0) & no_chunks, "processing_status"] = "bloqueado"
    delta.loc[chunk_status.str.contains("bloqueado", na=False), "processing_status"] = "bloqueado"
    delta.loc[
        delta["processing_status"].eq("ok")
        & (
            chunk_status.str.contains("pendente|em andamento|processar|baixar|fingerprint", na=False)
            | (delta["document_rows"].gt(0) & no_chunks)
        ),
        "processing_status",
    ] = "atenção"
    delta["processing_evidence"] = (
        "status chunks "
        + delta["document_chunk_statuses"].replace("", "n/d")
        + "; ações "
        + delta["document_chunk_actions"].replace("", "n/d")
    )

    has_cedente = delta["cedente_rows"].gt(0)
    has_criteria = delta["criteria_rows"].gt(0)
    has_sub = delta["tem_sub_minima"]
    delta["incorporation_status"] = "ok"
    delta.loc[~(has_cedente & has_criteria & has_sub), "incorporation_status"] = "atenção"
    delta.loc[~has_cedente & ~has_criteria, "incorporation_status"] = "bloqueado"
    delta["incorporation_evidence"] = (
        "cedentes "
        + delta["cedente_rows"].astype(int).astype(str)
        + "; critérios "
        + delta["criteria_rows"].astype(int).astype(str)
        + "; sub mínima "
        + delta["tem_sub_minima"].map({True: "sim", False: "não"})
    )

    order = {"bloqueado": 0, "atenção": 1, "ok": 2}

    def worst_status(row: pd.Series) -> str:
        statuses = [row["discovery_status"], row["processing_status"], row["incorporation_status"]]
        if int(row.get("open_high_priority_rows", 0) or 0) > 0:
            statuses.append("bloqueado")
        return sorted(statuses, key=lambda value: order.get(str(value), 9))[0]

    delta["overall_status"] = delta.apply(worst_status, axis=1)

    def missing_steps(row: pd.Series) -> str:
        items: list[str] = []
        if row["discovery_status"] != "ok":
            items.append("descoberta documental")
        if row["processing_status"] != "ok":
            items.append("processamento documental")
        if row["incorporation_status"] != "ok":
            items.append("incorporação estruturada")
        if int(row.get("open_queue_rows", 0) or 0) > 0:
            items.append("fechar fila única")
        return " | ".join(dict.fromkeys(items)) or "pronto"

    delta["missing_steps"] = delta.apply(missing_steps, axis=1)
    delta["onboarding_id"] = delta.get("delta_id", pd.Series("", index=delta.index)).fillna("").astype(str).where(
        delta.get("delta_id", pd.Series("", index=delta.index)).fillna("").astype(str).str.strip().ne(""),
        delta.get("competencia_atual", pd.Series("", index=delta.index)).map(_competencia_key) + "_" + delta["cnpj_fundo"],
    )
    delta["source_artifacts"] = (
        delta.get("source_artifacts", pd.Series("", index=delta.index)).fillna("").astype(str)
        + " | industry_curation_queue.csv.gz | document_chunk_plan.csv"
    ).str.strip(" |")
    delta["rerun_command"] = delta.get("queue_rerun_commands", pd.Series("", index=delta.index)).fillna("").astype(str).where(
        delta.get("queue_rerun_commands", pd.Series("", index=delta.index)).fillna("").astype(str).str.strip().ne(""),
        delta.get("rerun_command", pd.Series("", index=delta.index)).fillna("").astype(str),
    )

    columns = [
        "onboarding_id",
        "competencia_atual",
        "cnpj_fundo",
        "fundo",
        "status_delta",
        "priority_band",
        "priority_score",
        "pl_atual",
        "admin_nome",
        "gestor_nome",
        "segmento_principal",
        "overall_status",
        "discovery_status",
        "processing_status",
        "incorporation_status",
        "missing_steps",
        "discovery_evidence",
        "processing_evidence",
        "incorporation_evidence",
        "document_rows",
        "document_chunk_ids",
        "document_chunk_statuses",
        "cedente_rows",
        "criteria_rows",
        "tem_sub_minima",
        "camadas_com_evidencia",
        "open_queue_rows",
        "open_high_priority_rows",
        "queue_domains",
        "queue_action_types",
        "queue_next_actions",
        "queue_status_mix",
        "next_actions",
        "rerun_command",
        "source_artifacts",
    ]
    for col in columns:
        if col not in delta.columns:
            delta[col] = ""
    delta["_overall_order"] = delta["overall_status"].map(order).fillna(9)
    return delta.sort_values(
        ["_overall_order", "priority_score", "pl_atual", "cnpj_fundo"],
        ascending=[True, False, False, True],
    )[columns].reset_index(drop=True)


def incremental_onboarding_quality_summary(plan: pd.DataFrame) -> dict[str, object]:
    if plan is None or plan.empty:
        return {
            "rows": 0,
            "funds": 0,
            "new_funds": 0,
            "reactivated_funds": 0,
            "blocked_rows": 0,
            "attention_rows": 0,
            "ok_rows": 0,
        }
    status = plan.get("overall_status", pd.Series("", index=plan.index)).fillna("").astype(str)
    delta_status = plan.get("status_delta", pd.Series("", index=plan.index)).fillna("").astype(str)
    return {
        "rows": int(len(plan)),
        "funds": int(plan.get("cnpj_fundo", pd.Series(dtype=str)).map(normalize_cnpj).replace("", pd.NA).dropna().nunique()),
        "new_funds": int(delta_status.eq("novo_no_ime").sum()),
        "reactivated_funds": int(delta_status.eq("reativado").sum()),
        "blocked_rows": int(status.eq("bloqueado").sum()),
        "attention_rows": int(status.eq("atenção").sum()),
        "ok_rows": int(status.eq("ok").sum()),
        "discovery_blocked": int(plan.get("discovery_status", pd.Series("", index=plan.index)).fillna("").astype(str).eq("bloqueado").sum()),
        "processing_attention": int(plan.get("processing_status", pd.Series("", index=plan.index)).fillna("").astype(str).eq("atenção").sum()),
        "incorporation_blocked": int(plan.get("incorporation_status", pd.Series("", index=plan.index)).fillna("").astype(str).eq("bloqueado").sum()),
        "open_queue_rows": int(pd.to_numeric(plan.get("open_queue_rows", pd.Series(0, index=plan.index)), errors="coerce").fillna(0).sum()),
        "open_high_priority_rows": int(pd.to_numeric(plan.get("open_high_priority_rows", pd.Series(0, index=plan.index)), errors="coerce").fillna(0).sum()),
        "status_counts": {str(k): int(v) for k, v in status.value_counts().to_dict().items()},
    }


def build_incremental_onboarding_pipeline_manifest(
    *,
    industry_dir: Path,
    output_path: Path,
    manifest_path: Path,
    monthly_delta: pd.DataFrame,
    curation_queue: pd.DataFrame,
    document_chunk_plan: pd.DataFrame,
    plan: pd.DataFrame,
) -> dict[str, object]:
    quality = incremental_onboarding_quality_summary(plan)
    return {
        "schema_version": "industry-incremental-onboarding-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_incremental_onboarding",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "manual_review_in_app": True,
            "notes": [
                "Materializa apenas FIDCs novos ou reativados da competência corrente.",
                "O checklist consolida descoberta documental, processamento por chunks e incorporação às bases estruturadas.",
                "Não cria decisões de curadoria; usa a fila única e os ledgers existentes como fonte de status.",
            ],
        },
        "inputs": {
            "monthly_delta": file_fingerprint(industry_dir / "industry_monthly_delta.csv.gz"),
            "curation_queue": file_fingerprint(industry_dir / "industry_curation_queue.csv.gz"),
            "document_chunk_plan": file_fingerprint(industry_dir / "document_chunk_plan.csv"),
        },
        "outputs": {
            "incremental_onboarding": file_fingerprint(output_path),
            "manifest": {"path": str(manifest_path)},
        },
        "stages": [
            {
                "id": "filter_new_reactivated",
                "label": "Filtrar novos e reativados",
                "status": "ok" if monthly_delta is not None and not monthly_delta.empty else "empty",
                "rows": int(len(monthly_delta)) if monthly_delta is not None else 0,
                "rerun": "python scripts/build_fidc_industry_monthly_delta.py",
            },
            {
                "id": "join_queue_and_chunks",
                "label": "Cruzar fila única e chunks documentais",
                "status": "ok" if curation_queue is not None and not curation_queue.empty else "empty",
                "rows": int(len(curation_queue)) if curation_queue is not None else 0,
                "rerun": "python scripts/build_fidc_industry_curation_queue.py",
            },
            {
                "id": "persist_onboarding_plan",
                "label": "Persistir onboarding incremental",
                "status": "ok" if output_path.exists() else "empty",
                "rows": int(len(plan)),
                "rerun": "python scripts/build_fidc_industry_incremental_onboarding.py",
            },
        ],
        "quality": quality,
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
    if "Fonte camada" not in frame.columns:
        frame["Fonte camada"] = "criteria_monitoraveis_ime"
    if "Método extração" not in frame.columns:
        frame["Método extração"] = "triagem_documental_offline"
    frame["rule_id"] = frame.apply(criteria_rule_id, axis=1)
    return frame


def _feature_criteria_key(value: object) -> str:
    key = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return f"feature_{key}" if key else "feature_regulatoria"


def load_regulatory_feature_criteria(db_path: Path) -> pd.DataFrame:
    """Load positive Strategy regulatory matrix features as Industry criteria signals."""

    if not db_path.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute("select name from sqlite_master where type='table'").fetchall()
            }
            if "regulatory_feature_long" not in tables:
                return pd.DataFrame()
            frame = pd.read_sql_query(
                """
                select cnpj, fund_name, setor_n1, setor_n2, emission_cohort,
                       emitted_2024, emitted_2025, has_regulatory_matrix,
                       feature_key, feature_label, has_feature, evidence,
                       pl_atual_brl, volume_2024_brl, volume_2025_brl
                from regulatory_feature_long
                where cast(coalesce(has_feature, 0) as integer) = 1
                """,
                conn,
            )
    except sqlite3.Error:
        return pd.DataFrame()
    if frame.empty:
        return pd.DataFrame()

    out = pd.DataFrame(index=frame.index)
    out["Fundo"] = _text(frame.get("fund_name"), frame.index)
    out["CNPJ"] = _text(frame.get("cnpj"), frame.index).map(normalize_cnpj)
    out["Critério"] = _text(frame.get("feature_label"), frame.index).where(
        _text(frame.get("feature_label"), frame.index).str.strip().ne(""),
        _text(frame.get("feature_key"), frame.index),
    )
    out["Chave"] = _text(frame.get("feature_key"), frame.index).map(_feature_criteria_key)
    evidence = _text(frame.get("evidence"), frame.index).str.replace(r"\s+", " ", regex=True).str.strip()
    out["Limite/regra"] = evidence.where(
        evidence.ne(""),
        "Presença detectada na matriz regulatória da aba Estratégia.",
    ).str.slice(0, 900)
    out["Monitorabilidade IME"] = "feature_documental"
    out["Métrica IME / proxy"] = ""
    out["Condição de alerta sugerida"] = "Revisar regra operacional e parametrizar limite quando houver métrica mensal aplicável."
    out["Observação técnica"] = (
        "Sinal de presença da matriz regulatória da aba Estratégia; não substitui "
        "extração percentual curada para subordinação mínima."
    )
    out["Fonte"] = (
        "strategy_regulatory_feature_long"
        + " · feature_key="
        + _text(frame.get("feature_key"), frame.index)
        + " · cohort="
        + _text(frame.get("emission_cohort"), frame.index)
    )
    out["Status curadoria"] = "triagem estruturada por evidência documental da matriz Estratégia"
    out["Fonte camada"] = "strategy_regulatory_feature_long"
    out["Método extração"] = "strategy_regulatory_feature_matrix"
    out["setor_n1"] = _text(frame.get("setor_n1"), frame.index)
    out["setor_n2"] = _text(frame.get("setor_n2"), frame.index)
    out["emission_cohort"] = _text(frame.get("emission_cohort"), frame.index)
    out["pl_atual_brl"] = _num(frame.get("pl_atual_brl"), frame.index)
    out["volume_2024_brl"] = _num(frame.get("volume_2024_brl"), frame.index)
    out["volume_2025_brl"] = _num(frame.get("volume_2025_brl"), frame.index)
    out = out[out["CNPJ"].astype(str).str.len().eq(14)].copy()
    if out.empty:
        return out
    out["rule_id"] = out.apply(criteria_rule_id, axis=1)
    return out.drop_duplicates("rule_id", keep="first").reset_index(drop=True)


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
    review_audit: pd.DataFrame | None = None,
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
    fonte_camada = _text(merged.get("Fonte camada"), idx).replace("", "criteria_monitoraveis_ime")
    metodo_auto = _text(merged.get("Método extração"), idx).replace("", "triagem_documental_offline")
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
            "fonte_camada": fonte_camada,
            "documento_origem": documento,
            "documento_id": fonte.map(_document_id),
            "document_date": doc_date,
            "pagina": fonte.map(extract_page),
            "status_curadoria": status_curadoria,
            "status_revisao": status_review,
            "ativo_curadoria": ~status_review.str.lower().eq("rejeitado"),
            "metodo_extracao": metodo_auto,
            "score_confianca_final": score_final,
            "periodo_prioritario": priority.map({True: "2025-2026 YTD", False: "histórico"}),
            "notas_revisao": _text(merged.get("notas"), idx),
            "first_offer_year": first_offer_year,
            "emission_cohort": _text(merged.get("emission_cohort"), idx),
            "pl_atual_brl": _num(merged.get("pl_atual_brl"), idx),
        }
    )
    if review_audit is not None and not review_audit.empty:
        audit_summary = review_audit_summary(review_audit, "rule_id")
        if not audit_summary.empty:
            out = out.merge(audit_summary, on="rule_id", how="left")
    for col in ["review_event_count", "last_review_at_utc", "last_review_field", "last_review_source"]:
        if col not in out.columns:
            out[col] = 0 if col == "review_event_count" else ""
    out["review_event_count"] = pd.to_numeric(out["review_event_count"], errors="coerce").fillna(0).astype(int)
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
    source_layer = structured.get("fonte_camada", pd.Series("", index=structured.index)).fillna("").astype(str)
    active_source_layer = active.get("fonte_camada", pd.Series("", index=active.index)).fillna("").astype(str)
    feature_active = active_source_layer.eq("strategy_regulatory_feature_long")
    return {
        "source_rows": int(len(criteria)),
        "source_funds": int(criteria["CNPJ"].nunique()) if "CNPJ" in criteria else 0,
        "structured_rows": int(len(structured)),
        "structured_funds": int(structured["cnpj_fundo"].nunique()) if "cnpj_fundo" in structured else 0,
        "active_rows": int(len(active)),
        "active_funds": int(active["cnpj_fundo"].nunique()) if "cnpj_fundo" in active else 0,
        "source_layer_counts": {str(k): int(v) for k, v in source_layer.value_counts().to_dict().items()},
        "feature_rows": int(feature_active.sum()),
        "feature_funds": int(active.loc[feature_active, "cnpj_fundo"].nunique()) if "cnpj_fundo" in active else 0,
        "documentary_rows": int((~feature_active).sum()),
        "documentary_funds": int(active.loc[~feature_active, "cnpj_fundo"].nunique()) if "cnpj_fundo" in active else 0,
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


def _optional_artifact_row(module_id: str, artifact: str, path: Path, *, group: str = "manual_review") -> dict[str, object]:
    return {
        "module_id": module_id,
        "group": group,
        "artifact": artifact,
        "required": False,
        **file_fingerprint(path),
    }


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


def _competencia_key(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) >= 6:
        return digits[:6]
    return digits


def _readiness_sample(frame: pd.DataFrame, cols: list[str], limit: int = 4) -> str:
    if frame.empty:
        return ""
    samples: list[str] = []
    for _, row in frame.head(limit).iterrows():
        values = [str(row.get(col, "") or "").strip() for col in cols]
        values = [value for value in values if value]
        if values:
            samples.append(" · ".join(values))
    return " | ".join(samples)


def build_pipeline_readiness_checks(
    *,
    modules: list[dict[str, object]],
    artifact_rows: list[dict[str, object]],
    quality_rollup: dict[str, object],
) -> list[dict[str, object]]:
    """Build persisted, lightweight readiness checks for the monthly Industry refresh."""

    rows: list[dict[str, object]] = []

    def add(
        check_id: str,
        ordem: int,
        frente: str,
        escopo: str,
        status: str,
        pendencias: int,
        amostra: str,
        acao: str,
        fonte: str,
        comando: str = "",
    ) -> None:
        rows.append(
            {
                "check_id": check_id,
                "ordem": ordem,
                "frente": frente,
                "escopo": escopo,
                "status_prontidao": status,
                "pendencias": int(pendencias),
                "amostra": amostra,
                "acao_sugerida": acao,
                "fonte": fonte,
                "comando": comando,
            }
        )

    snapshot_comp = str(quality_rollup.get("competencia_snapshot", "") or "")
    dimension_monthly_comp = str(quality_rollup.get("dimension_monthly_latest_competencia", "") or "")
    delta_comp = str(quality_rollup.get("monthly_delta_competencia_atual", "") or "")
    stale = []
    snapshot_key = _competencia_key(snapshot_comp)
    dimension_key = _competencia_key(dimension_monthly_comp)
    delta_key = _competencia_key(delta_comp)
    if snapshot_key and dimension_key and snapshot_key != dimension_key:
        stale.append("séries por dimensão")
    if snapshot_key and delta_key and snapshot_key != delta_key:
        stale.append("delta mensal")
    add(
        "competencia_alignment",
        1,
        "Competência",
        "Sincronia dos artefatos mensais",
        "bloqueado" if stale else "ok",
        len(stale),
        f"snapshot {snapshot_comp or 'n/d'}; dimensão {dimension_monthly_comp or 'n/d'}; delta {delta_comp or 'n/d'}",
        "Reexecutar os módulos derivados depois de atualizar a base granular.",
        "quality_rollup",
        "python scripts/build_fidc_industry_dimension_monthly.py && python scripts/build_fidc_industry_monthly_delta.py",
    )

    module_frame = pd.DataFrame(modules)
    bad_modules = module_frame.iloc[0:0].copy() if module_frame.empty else module_frame[
        ~module_frame.get("status", pd.Series("", index=module_frame.index)).fillna("").astype(str).str.lower().eq("ok")
    ].copy()
    add(
        "module_status",
        2,
        "Pipeline",
        "Módulos com manifesto válido",
        "bloqueado" if not bad_modules.empty else "ok",
        len(bad_modules),
        _readiness_sample(bad_modules.rename(columns={"label": "module_label"}), ["module_label", "status"]),
        "Rodar os comandos dos módulos pendentes antes de fechar a competência.",
        "modules",
        " && ".join([str(value) for value in bad_modules.get("command", pd.Series(dtype=str)).head(3) if str(value).strip()]),
    )

    artifact_frame = pd.DataFrame(artifact_rows)
    if artifact_frame.empty:
        missing_required = artifact_frame
        missing_optional = artifact_frame
    else:
        exists = artifact_frame.get("exists", pd.Series(False, index=artifact_frame.index)).eq(True)
        required = artifact_frame.get("required", pd.Series(False, index=artifact_frame.index)).eq(True)
        missing_required = artifact_frame[required & ~exists].copy()
        missing_optional = artifact_frame[~required & ~exists].copy()
    add(
        "artifact_presence",
        3,
        "Artefatos",
        "Arquivos obrigatórios e opcionais",
        "bloqueado" if not missing_required.empty else ("atenção" if not missing_optional.empty else "ok"),
        len(missing_required) if not missing_required.empty else len(missing_optional),
        _readiness_sample(pd.concat([missing_required, missing_optional], ignore_index=True), ["module_id", "artifact"]),
        "Gerar arquivos ausentes; opcionais indicam histórico de revisão ainda não iniciado.",
        "artifact_index",
        "",
    )

    high_priority = int(quality_rollup.get("monthly_delta_high_priority_open", 0) or 0)
    high_priority_total = int(quality_rollup.get("monthly_delta_high_priority", 0) or 0)
    high_priority_pending = int(quality_rollup.get("monthly_delta_high_priority_pending", 0) or 0)
    high_priority_in_progress = int(quality_rollup.get("monthly_delta_high_priority_in_progress", 0) or 0)
    high_priority_closed = int(quality_rollup.get("monthly_delta_high_priority_closed", 0) or 0)
    new_funds = int(quality_rollup.get("monthly_delta_new_funds", 0) or 0)
    reactivated = int(quality_rollup.get("monthly_delta_reactivated_funds", 0) or 0)
    add(
        "monthly_delta_queue",
        4,
        "Delta mensal",
        "Novos, reativados, saídas e grandes variações",
        "bloqueado" if high_priority else ("atenção" if new_funds or reactivated else "ok"),
        high_priority if high_priority else new_funds + reactivated,
        (
            f"{new_funds} novos; {reactivated} reativados; "
            f"alta prioridade {high_priority}/{high_priority_total} abertos "
            f"({high_priority_pending} pendentes; {high_priority_in_progress} em andamento; {high_priority_closed} fechados)"
        ),
        "Fechar ou justificar as ações do delta mensal de maior prioridade.",
        "industry_monthly_delta_manifest.json",
        "python scripts/build_fidc_industry_monthly_delta.py",
    )

    curation_open = int(quality_rollup.get("curation_queue_open_rows", 0) or 0)
    curation_high = int(quality_rollup.get("curation_queue_high_priority_open_rows", 0) or 0)
    curation_high_total = int(quality_rollup.get("curation_queue_high_priority_rows", 0) or 0)
    curation_high_pending = int(quality_rollup.get("curation_queue_high_priority_pending_rows", 0) or 0)
    curation_high_in_progress = int(quality_rollup.get("curation_queue_high_priority_in_progress_rows", 0) or 0)
    curation_high_closed = int(quality_rollup.get("curation_queue_high_priority_closed_rows", 0) or 0)
    add(
        "curation_queue",
        5,
        "Curadoria",
        "Fila única all-FIDCs",
        "bloqueado" if curation_high else ("atenção" if curation_open else "ok"),
        curation_high if curation_high else curation_open,
        (
            f"{curation_open} abertas; alta prioridade {curation_high}/{curation_high_total} abertas "
            f"({curation_high_pending} pendentes; {curation_high_in_progress} em andamento; {curation_high_closed} fechadas)"
        ),
        "Usar a fila única para fechar delta, lacunas estruturais, chunks e rastreabilidade da competência.",
        "industry_curation_queue.csv.gz",
        "python scripts/build_fidc_industry_curation_queue.py",
    )

    document_chunks = int(quality_rollup.get("document_chunks", 0) or 0)
    chunk_untracked = int(quality_rollup.get("document_chunks_without_action", 0) or 0)
    chunk_pending = int(quality_rollup.get("document_chunks_pending_action", 0) or 0)
    chunk_blocked = int(quality_rollup.get("document_chunks_blocked", 0) or 0)
    chunk_in_progress = int(quality_rollup.get("document_chunks_in_progress", 0) or 0)
    chunk_processed = int(quality_rollup.get("document_chunks_processed", 0) or 0)
    chunk_open = chunk_untracked + chunk_pending + chunk_in_progress + chunk_blocked
    add(
        "document_chunk_processing",
        6,
        "Documentos",
        "Execução incremental de OCR, parsing e extração por chunk",
        "bloqueado" if chunk_blocked else ("atenção" if chunk_open else "ok"),
        chunk_open,
        (
            f"{chunk_processed}/{document_chunks} processados; "
            f"{chunk_untracked} sem acompanhamento; {chunk_pending} pendentes; "
            f"{chunk_in_progress} em andamento; {chunk_blocked} bloqueados"
        ),
        "Acompanhar e fechar chunks no editor Documentos > Chunks antes de depender das extrações documentais.",
        "document_chunk_actions.csv",
        "python scripts/build_fidc_industry_document_chunk_plan.py && python scripts/build_fidc_industry_documents.py --chunk-id doc-0001",
    )

    snapshot_rows = int(quality_rollup.get("fund_snapshot_rows", 0) or 0)
    with_cedentes = int(quality_rollup.get("fund_snapshot_with_cedentes", 0) or 0)
    with_participant_signal = int(quality_rollup.get("fund_snapshot_with_participant_signal", 0) or 0)
    signal_without_cedente = int(quality_rollup.get("fund_snapshot_with_participant_signal_without_cedente", 0) or 0)
    with_criteria = int(quality_rollup.get("fund_snapshot_with_criteria", 0) or 0)
    missing_structured = max(snapshot_rows - min(with_cedentes, with_criteria), 0)
    add(
        "structured_coverage",
        7,
        "Snapshot",
        "Cobertura de cedentes e critérios estruturados",
        "atenção" if missing_structured else "ok",
        missing_structured,
        (
            f"cedentes identificados {with_cedentes}/{snapshot_rows}; "
            f"sinal cedente/sacado {with_participant_signal}/{snapshot_rows} "
            f"({signal_without_cedente} sem participante); critérios {with_criteria}/{snapshot_rows}"
        ),
        "Priorizar lacunas estruturais em FIDCs materiais antes de publicar cortes por participante.",
        "industry_fund_snapshot_manifest.json",
        "python scripts/build_fidc_industry_fund_snapshot.py",
    )

    checks = pd.DataFrame(rows)
    if checks.empty:
        return []
    status_order = {"bloqueado": 0, "atenção": 1, "ok": 2}
    checks["_status_order"] = checks["status_prontidao"].map(status_order).fillna(9)
    checks = checks.sort_values(["_status_order", "ordem"]).drop(columns=["_status_order"]).reset_index(drop=True)
    return checks.to_dict("records")


def build_monthly_update_plan(
    *,
    modules: list[dict[str, object]],
    artifact_rows: list[dict[str, object]],
    refresh_plan: list[dict[str, object]],
    readiness_checks: list[dict[str, object]],
    quality_rollup: dict[str, object],
) -> list[dict[str, object]]:
    """Join refresh commands, module evidence and readiness blockers into an operational monthly plan."""

    module_by_id = {str(module.get("id") or ""): module for module in modules if isinstance(module, dict)}
    artifact_frame = pd.DataFrame(artifact_rows)
    readiness_by_id = {
        str(row.get("check_id") or ""): row
        for row in readiness_checks
        if isinstance(row, dict)
    }
    stage_checks = {
        "base_monthly": ["competencia_alignment"],
        "manual_review_ledgers": ["artifact_presence"],
        "monthly_delta": ["competencia_alignment", "monthly_delta_queue"],
        "incremental_onboarding": ["monthly_delta_queue", "curation_queue", "document_chunk_processing", "structured_coverage"],
        "issuance": [],
        "public_claims": ["competencia_alignment"],
        "documents": ["document_chunk_processing"],
        "document_chunk_plan": ["document_chunk_processing"],
        "cedentes": ["structured_coverage", "curation_queue"],
        "criteria": ["structured_coverage", "curation_queue"],
        "fund_snapshot": ["structured_coverage", "competencia_alignment"],
        "dimension_catalog": ["structured_coverage", "curation_queue"],
        "curation_queue": ["curation_queue"],
        "dimension_profiles": ["structured_coverage"],
        "dimension_monthly": ["competencia_alignment", "structured_coverage"],
        "dimension_dossiers": ["competencia_alignment", "structured_coverage"],
        "market_share": ["structured_coverage"],
        "pipeline_index": ["module_status", "artifact_presence"],
    }
    status_order = {"bloqueado": 0, "atenção": 1, "ok": 2, "n/d": 3}

    def phase(order: int) -> str:
        if order <= 3:
            return "Informe mensal e delta"
        if order <= 8:
            return "Documentos e ofertas"
        if order <= 14:
            return "Estruturação"
        if order <= 18:
            return "Agregações reutilizáveis"
        return "Controle"

    def module_for_stage(module_id: str) -> dict[str, object]:
        if module_id == "document_chunk_plan":
            return module_by_id.get("documents", {})
        if module_id == "pipeline_index":
            return {
                "id": "pipeline_index",
                "label": "Cockpit do pipeline",
                "status": "ok",
                "generated_at_utc": quality_rollup.get("latest_module_generated_at_utc", ""),
                "artifact_count": quality_rollup.get("artifacts_total", 0),
                "artifacts_present": quality_rollup.get("artifacts_present", 0),
                "quality_highlights": {
                    "prd_requirements_total": quality_rollup.get("prd_requirements_total", 0),
                    "artifacts_present": quality_rollup.get("artifacts_present", 0),
                    "artifacts_total": quality_rollup.get("artifacts_total", 0),
                },
            }
        return module_by_id.get(module_id, {})

    def artifact_names(module_id: str, group: str | None = None, limit: int = 6) -> str:
        if artifact_frame.empty:
            return ""
        ids = [module_id]
        if module_id == "document_chunk_plan":
            ids = ["documents"]
        subset = artifact_frame[artifact_frame.get("module_id", pd.Series("", index=artifact_frame.index)).astype(str).isin(ids)].copy()
        if group is not None and "group" in subset.columns:
            subset = subset[subset["group"].astype(str).eq(group)].copy()
        if subset.empty or "artifact" not in subset.columns:
            return ""
        names = subset["artifact"].fillna("").astype(str)
        names = [name for name in names if name]
        return " | ".join(dict.fromkeys(names[:limit]))

    def quality_text(module: dict[str, object]) -> str:
        quality = module.get("quality_highlights", {}) if isinstance(module.get("quality_highlights"), dict) else {}
        parts: list[str] = []
        for key, value in quality.items():
            if value in ("", None, {}, []):
                continue
            parts.append(f"{key}={value}")
            if len(parts) >= 6:
                break
        return " · ".join(parts)

    rows: list[dict[str, object]] = []
    competencia = str(quality_rollup.get("competencia_snapshot") or quality_rollup.get("competencia_final") or "")
    for stage in refresh_plan:
        if not isinstance(stage, dict):
            continue
        order = int(pd.to_numeric(pd.Series([stage.get("order", 0)]), errors="coerce").fillna(0).iloc[0])
        module_id = str(stage.get("module_id") or "")
        module = module_for_stage(module_id)
        linked_checks = [
            readiness_by_id[check_id]
            for check_id in stage_checks.get(module_id, [])
            if check_id in readiness_by_id
        ]
        if linked_checks:
            worst = sorted(
                [str(check.get("status_prontidao") or "n/d") for check in linked_checks],
                key=lambda value: status_order.get(value, 9),
            )[0]
            open_checks = [
                check
                for check in linked_checks
                if str(check.get("status_prontidao") or "") != "ok"
            ]
        else:
            worst = "ok"
            open_checks = []
        blocker_text = " | ".join(
            f"{check.get('frente')}: {check.get('pendencias', 0)} ({check.get('acao_sugerida')})"
            for check in open_checks
        )
        next_action = (
            "Fechar bloqueios/atenções vinculados antes de depender desta etapa."
            if open_checks
            else "Rodar ou validar a etapa e seguir para a próxima ordem."
        )
        rows.append(
            {
                "plan_id": f"{order:02d}_{module_id}",
                "order": order,
                "fase": phase(order),
                "module_id": module_id,
                "etapa": stage.get("label", module.get("label", module_id)),
                "competencia_referencia": competencia,
                "status_modulo": module.get("status", "n/d"),
                "status_prontidao": worst,
                "bloqueios_ou_atencoes": blocker_text,
                "acao_antes_de_rodar": next_action,
                "comando": stage.get("command", ""),
                "validacao": "python scripts/build_fidc_industry_pipeline_index.py",
                "entradas": " | ".join(str(value) for value in module.get("depends_on", []) if value)
                or artifact_names(module_id, group="inputs"),
                "saidas": artifact_names(module_id, group="outputs"),
                "evidencia_atual": quality_text(module),
                "artefatos": f"{module.get('artifacts_present', 0)}/{module.get('artifact_count', 0)}",
                "gerado_em_utc": module.get("generated_at_utc", ""),
                "motivo": stage.get("reason", ""),
                "incrementalidade": stage.get("incremental_note", ""),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return []
    frame["_status_order"] = frame["status_prontidao"].map(status_order).fillna(9)
    frame = frame.sort_values(["order", "_status_order"]).drop(columns=["_status_order"]).reset_index(drop=True)
    return frame.to_dict("records")


def build_monthly_publication_gate(
    *,
    readiness_checks: list[dict[str, object]],
    prd_coverage: list[dict[str, object]],
    monthly_update_plan: list[dict[str, object]],
    quality_rollup: dict[str, object],
) -> list[dict[str, object]]:
    """Build a director-facing monthly publish gate from existing cockpit signals."""

    status_order = {"bloqueado": 0, "atenção": 1, "ok": 2, "n/d": 3}
    competencia = str(
        quality_rollup.get("competencia_snapshot")
        or quality_rollup.get("competencia_final")
        or quality_rollup.get("monthly_delta_competencia_atual")
        or ""
    )

    def number(key: str) -> float:
        return float(pd.to_numeric(pd.Series([quality_rollup.get(key, 0)]), errors="coerce").fillna(0).iloc[0])

    def norm_status(value: object) -> str:
        text = str(value or "n/d").strip().lower()
        return text if text else "n/d"

    def decision(status: str, note: bool = False) -> str:
        if status == "bloqueado":
            return "não publicar antes de fechar"
        if status == "atenção" or note:
            return "publicar apenas com ressalva explícita"
        if status == "ok":
            return "liberado"
        return "validar antes de publicar"

    def row(
        *,
        gate_id: str,
        ordem: int,
        tipo_sinal: str,
        frente: str,
        status_gate: str,
        pendencias: object,
        evidencia: str,
        acao_sugerida: str,
        fonte: str,
        comando: str,
        exige_nota_publica: bool = False,
    ) -> dict[str, object]:
        status = norm_status(status_gate)
        return {
            "gate_id": gate_id,
            "ordem": ordem,
            "tipo_sinal": tipo_sinal,
            "frente": frente,
            "status_gate": status,
            "decisao_publicacao": decision(status, exige_nota_publica),
            "bloqueia_publicacao": status == "bloqueado",
            "exige_nota_publica": bool(exige_nota_publica),
            "pendencias": pendencias,
            "evidencia": evidencia,
            "acao_sugerida": acao_sugerida,
            "fonte": fonte,
            "comando": comando,
            "competencia_referencia": competencia,
        }

    readiness = pd.DataFrame(readiness_checks)
    prd = pd.DataFrame(prd_coverage)
    plan = pd.DataFrame(monthly_update_plan)
    rows: list[dict[str, object]] = []

    readiness_status = (
        readiness.get("status_prontidao", pd.Series(dtype=str)).fillna("").astype(str)
        if not readiness.empty
        else pd.Series(dtype=str)
    )
    prd_status = (
        prd.get("status_prd", pd.Series(dtype=str)).fillna("").astype(str)
        if not prd.empty
        else pd.Series(dtype=str)
    )
    plan_status = (
        plan.get("status_prontidao", pd.Series(dtype=str)).fillna("").astype(str)
        if not plan.empty
        else pd.Series(dtype=str)
    )

    readiness_blocked = int(readiness_status.eq("bloqueado").sum())
    readiness_attention = int(readiness_status.eq("atenção").sum())
    prd_blocked = int(prd_status.eq("bloqueado").sum())
    prd_attention = int(prd_status.eq("atenção").sum())
    plan_blocked = int(plan_status.eq("bloqueado").sum())
    plan_attention = int(plan_status.eq("atenção").sum())
    disclosure_rows = int(
        number("public_claim_methodology_bridge_needs_disclosure_rows")
        + number("public_claim_audit_methodology_gap_claims")
    )
    blocking_signals = readiness_blocked + prd_blocked + plan_blocked
    attention_signals = readiness_attention + prd_attention + plan_attention + (1 if disclosure_rows else 0)
    summary_status = "bloqueado" if blocking_signals else ("atenção" if attention_signals else "ok")
    readiness_open_pending = 0
    if not readiness.empty and "pendencias" in readiness.columns:
        open_readiness = readiness[~readiness_status.eq("ok")]
        readiness_open_pending = int(pd.to_numeric(open_readiness["pendencias"], errors="coerce").fillna(0).sum())
    rows.append(
        row(
            gate_id="publication_gate_summary",
            ordem=0,
            tipo_sinal="síntese",
            frente="Portão mensal",
            status_gate=summary_status,
            pendencias=readiness_open_pending + prd_blocked + prd_attention + plan_blocked + plan_attention,
            evidencia=(
                f"readiness {readiness_blocked} bloqueado/{readiness_attention} atenção; "
                f"PRD {prd_blocked} bloqueado/{prd_attention} atenção; "
                f"plano {plan_blocked} bloqueado/{plan_attention} atenção; "
                f"notas públicas {disclosure_rows}"
            ),
            acao_sugerida=(
                "Fechar todos os sinais bloqueados e registrar ressalvas metodológicas antes de apresentação externa."
                if summary_status == "bloqueado"
                else "Registrar ressalvas metodológicas no material antes de publicar."
                if summary_status == "atenção"
                else "Atualizar evidências e publicar a competência."
            ),
            fonte="industry_pipeline_index.json",
            comando="python scripts/build_fidc_industry_pipeline_index.py",
            exige_nota_publica=disclosure_rows > 0,
        )
    )

    if not readiness.empty:
        open_readiness = readiness[~readiness_status.eq("ok")].copy()
        for pos, item in enumerate(open_readiness.to_dict("records"), start=10):
            rows.append(
                row(
                    gate_id=f"readiness_{item.get('check_id', pos)}",
                    ordem=pos,
                    tipo_sinal="prontidão",
                    frente=str(item.get("frente") or item.get("check_id") or ""),
                    status_gate=str(item.get("status_prontidao") or "n/d"),
                    pendencias=item.get("pendencias", 0),
                    evidencia=str(item.get("amostra") or ""),
                    acao_sugerida=str(item.get("acao_sugerida") or ""),
                    fonte=str(item.get("fonte") or "industry_monthly_readiness.csv"),
                    comando=str(item.get("comando") or ""),
                )
            )

    if not prd.empty:
        open_prd = prd[~prd_status.eq("ok")].copy()
        for pos, item in enumerate(open_prd.to_dict("records"), start=100):
            req_id = str(item.get("requirement_id") or pos)
            rows.append(
                row(
                    gate_id=f"prd_{req_id}",
                    ordem=pos,
                    tipo_sinal="PRD",
                    frente=str(item.get("tema") or req_id),
                    status_gate=str(item.get("status_prd") or "n/d"),
                    pendencias=1,
                    evidencia=str(item.get("evidencia") or item.get("metrica") or ""),
                    acao_sugerida=str(item.get("proximo_passo") or ""),
                    fonte=str(item.get("artefato") or "industry_pipeline_index.json"),
                    comando=str(item.get("comando") or ""),
                    exige_nota_publica=req_id == "public_audit_readiness",
                )
            )

    if disclosure_rows:
        rows.append(
            row(
                gate_id="public_methodology_disclosure",
                ordem=180,
                tipo_sinal="divulgação pública",
                frente="Claims públicos",
                status_gate="atenção",
                pendencias=disclosure_rows,
                evidencia=(
                    f"{int(number('public_claim_methodology_bridge_rows'))} pontes; "
                    f"{int(number('public_claim_methodology_bridge_high_or_blocking_rows'))} severidade alta/bloqueante"
                ),
                acao_sugerida="Manter nota ANBIMA/CVM e diferenças de universo/conceito junto dos números públicos.",
                fonte="industry_public_claim_methodology_bridge.csv",
                comando="python scripts/build_fidc_industry_public_claim_audit.py",
                exige_nota_publica=True,
            )
        )

    if not plan.empty:
        open_plan = plan[~plan_status.eq("ok")].copy()
        if "order" in open_plan.columns:
            open_plan = open_plan.sort_values("order")
        for pos, item in enumerate(open_plan.to_dict("records"), start=200):
            module_id = str(item.get("module_id") or item.get("plan_id") or pos)
            rows.append(
                row(
                    gate_id=f"plan_{module_id}_{pos}",
                    ordem=pos,
                    tipo_sinal="plano mensal",
                    frente=str(item.get("etapa") or module_id),
                    status_gate=str(item.get("status_prontidao") or "n/d"),
                    pendencias=1,
                    evidencia=str(item.get("bloqueios_ou_atencoes") or item.get("evidencia_atual") or ""),
                    acao_sugerida=str(item.get("acao_antes_de_rodar") or ""),
                    fonte=str(item.get("saidas") or "industry_monthly_update_plan.csv"),
                    comando=str(item.get("comando") or ""),
                )
            )

    frame = pd.DataFrame(rows)
    for col in PUBLICATION_GATE_COLUMNS:
        if col not in frame.columns:
            frame[col] = ""
    frame["_status_order"] = frame["status_gate"].map(status_order).fillna(9)
    frame = frame.sort_values(["ordem", "_status_order"]).drop(columns=["_status_order"]).reset_index(drop=True)
    return frame[PUBLICATION_GATE_COLUMNS].to_dict("records")


def build_manual_review_ledger(*, industry_dir: Path) -> list[dict[str, object]]:
    """Summarize all in-app review domains, their persisted actions and append-only audit logs."""

    closed_statuses = {
        "aprovado",
        "corrigido",
        "rejeitado",
        "aceito",
        "ignorado",
        "processado",
        "concluído",
        "concluido",
    }
    specs = MANUAL_REVIEW_LEDGER_SPECS

    rows: list[dict[str, object]] = []
    for spec in specs:
        action_path = industry_dir / str(spec["action_file"])
        audit_path = industry_dir / str(spec["audit_file"])
        actions = load_dataframe(action_path)
        audit = load_review_audit(audit_path)
        key_column = str(spec["key_column"])
        status_column = str(spec["status_column"])

        action_rows = int(len(actions))
        action_records = 0
        open_rows = 0
        closed_rows = 0
        status_mix = ""
        latest_action_utc = ""
        if not actions.empty:
            if key_column in actions.columns:
                action_keys = actions[key_column].fillna("").astype(str).str.strip()
                action_records = int(action_keys[action_keys.ne("")].nunique())
            if status_column in actions.columns:
                status = (
                    actions[status_column]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.lower()
                    .replace("", "pendente")
                )
                counts = status.value_counts().to_dict()
                status_mix = " | ".join(f"{key}:{int(value)}" for key, value in counts.items())
                closed_mask = status.isin(closed_statuses)
                closed_rows = int(closed_mask.sum())
                open_rows = int((~closed_mask).sum())
            else:
                open_rows = action_rows
            if "updated_at_utc" in actions.columns:
                latest_action_utc = _latest_iso(actions["updated_at_utc"].tolist())

        audit_events = int(len(audit))
        audited_records = 0
        latest_audit_utc = ""
        audit_domains = ""
        if not audit.empty:
            audited_keys = audit.get("record_id", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
            audited_records = int(audited_keys[audited_keys.ne("")].nunique())
            latest_audit_utc = _latest_iso(audit.get("saved_at_utc", pd.Series(dtype=str)).tolist())
            if "review_domain" in audit.columns:
                counts = audit["review_domain"].fillna("").astype(str).replace("", "n/d").value_counts().to_dict()
                audit_domains = " | ".join(f"{key}:{int(value)}" for key, value in counts.items())

        if action_rows and audit_events:
            status_ledger = "ok"
        elif action_rows and not audit_events:
            status_ledger = "atenção"
        elif not action_rows and audit_events:
            status_ledger = "atenção"
        else:
            status_ledger = "sem_uso"

        rows.append(
            {
                "domain_id": spec["domain_id"],
                "label": spec["label"],
                "status_ledger": status_ledger,
                "ui_surface": spec["ui_surface"],
                "comparison": spec["comparison"],
                "action_file": spec["action_file"],
                "audit_file": spec["audit_file"],
                "action_exists": action_path.exists(),
                "audit_exists": audit_path.exists(),
                "action_rows": action_rows,
                "action_records": action_records,
                "open_rows": open_rows,
                "closed_rows": closed_rows,
                "status_mix": status_mix,
                "audit_events": audit_events,
                "audited_records": audited_records,
                "audit_domains": audit_domains,
                "latest_action_utc": latest_action_utc,
                "latest_audit_utc": latest_audit_utc,
                "source_artifacts": f"{spec['action_file']} | {spec['audit_file']}",
                "rerun_command": spec["rerun_command"],
            }
        )

    status_order = {"atenção": 0, "sem_uso": 1, "ok": 2}
    frame = pd.DataFrame(rows)
    if frame.empty:
        return []
    frame["_status_order"] = frame["status_ledger"].map(status_order).fillna(9)
    frame = frame.sort_values(["_status_order", "domain_id"]).drop(columns=["_status_order"]).reset_index(drop=True)
    return frame.to_dict("records")


def build_manual_review_pipeline_manifest(
    *,
    industry_dir: Path,
    manifest_path: Path,
    ledger_files: pd.DataFrame,
) -> dict[str, object]:
    quality = manual_review_ledgers_quality_summary(ledger_files)
    outputs = {
        "manifest": {"path": str(manifest_path)},
    }
    for spec in manual_review_file_specs():
        role = str(spec.get("file_role") or "")
        domain = str(spec.get("domain_id") or "")
        file_name = str(spec.get("file_name") or "")
        artifact_id = f"{domain}_{role}"
        outputs[artifact_id] = file_fingerprint(industry_dir / file_name)
    return {
        "schema_version": "industry-manual-review-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_manual_review_ledgers",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "manual_review_in_app": True,
            "notes": [
                "Inicializa arquivos CSV vazios com cabeçalhos oficiais para que a UI persista revisões sem edição manual.",
                "Não cria decisões, aprovações ou eventos artificiais; auditoria continua append-only quando o usuário salva alterações.",
                "Cada domínio preserva schema próprio de ações e compartilha o schema único de eventos de auditoria.",
            ],
        },
        "inputs": {},
        "review_specs": {
            "domains": len(MANUAL_REVIEW_LEDGER_SPECS),
            "files_expected": len(manual_review_file_specs()),
        },
        "outputs": outputs,
        "stages": [
            {
                "id": "initialize_missing_ledgers",
                "label": "Inicializar ledgers ausentes",
                "status": "ok" if quality.get("files_present") == quality.get("files") else "missing",
                "rows": int(len(ledger_files)) if ledger_files is not None else 0,
                "files_created": quality.get("files_created", 0),
                "rerun": "python scripts/build_fidc_industry_manual_review_ledgers.py",
            },
            {
                "id": "validate_review_schemas",
                "label": "Validar schemas de revisão",
                "status": "ok" if quality.get("schema_ok_files") == quality.get("files") else "atenção",
                "schema_ok_files": quality.get("schema_ok_files", 0),
                "files": quality.get("files", 0),
                "rerun": "python scripts/build_fidc_industry_manual_review_ledgers.py",
            },
        ],
        "quality": quality,
    }


def build_prd_coverage_matrix(
    *,
    quality_rollup: dict[str, object],
    artifact_rows: list[dict[str, object]],
    refresh_plan: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Map the Industry PRD requirements to current materialized evidence."""

    artifact_frame = pd.DataFrame(artifact_rows)
    artifact_names = set()
    if not artifact_frame.empty and "artifact" in artifact_frame.columns:
        artifact_names = set(artifact_frame["artifact"].fillna("").astype(str))

    def number(key: str) -> float:
        return float(pd.to_numeric(pd.Series([quality_rollup.get(key, 0)]), errors="coerce").fillna(0).iloc[0])

    def has_artifact(name: str) -> bool:
        return name in artifact_names

    rows: list[dict[str, object]] = []

    def add(
        requirement_id: str,
        ordem: int,
        tema: str,
        requisito: str,
        status: str,
        evidencia: str,
        metrica: str,
        artefato: str,
        proximo_passo: str,
        comando: str,
    ) -> None:
        rows.append(
            {
                "requirement_id": requirement_id,
                "ordem": ordem,
                "tema": tema,
                "requisito": requisito,
                "status_prd": status,
                "evidencia": evidencia,
                "metrica": metrica,
                "artefato": artefato,
                "proximo_passo": proximo_passo,
                "comando": comando,
            }
        )

    modules_ok = int(quality_rollup.get("module_status_counts", {}).get("ok", 0)) if isinstance(quality_rollup.get("module_status_counts"), dict) else 0
    modules_total = int(number("modules_total"))
    artifacts_present = int(number("artifacts_present"))
    artifacts_total = int(number("artifacts_total"))
    add(
        "pipeline_modular",
        1,
        "Arquitetura",
        "Pipeline modular com etapas reexecutáveis e artefatos persistidos",
        "ok" if modules_total and modules_ok == modules_total and artifacts_present == artifacts_total else "atenção",
        f"{modules_ok}/{modules_total} módulos ok; {artifacts_present}/{artifacts_total} artefatos obrigatórios presentes",
        f"refresh_plan={len(refresh_plan)}",
        "industry_pipeline_index.json",
        "Rodar módulos não-ok ou gerar artefatos obrigatórios ausentes.",
        "python scripts/build_fidc_industry_pipeline_index.py",
    )
    chunk_open = int(number("document_chunk_plan_open_rows"))
    add(
        "document_processing_chunks",
        2,
        "Documentos",
        "Descoberta/documentos em chunks pequenos para processamento incremental",
        "atenção" if chunk_open else ("ok" if number("document_chunks") else "bloqueado"),
        f"{int(number('document_chunks'))} chunks; {chunk_open} abertos; {int(number('max_documents_per_chunk'))} docs/chunk máx.",
        f"document_chunks={int(number('document_chunks'))}",
        "document_chunk_plan.csv",
        "Fechar ou justificar chunks abertos antes de depender da extração documental.",
        "python scripts/build_fidc_industry_documents.py && python scripts/build_fidc_industry_document_chunk_plan.py",
    )
    manual_present = int(number("manual_review_artifacts_present"))
    manual_total = int(number("manual_review_artifacts_total"))
    add(
        "manual_review_in_app",
        3,
        "Revisão manual",
        "Curadoria pela interface com persistência e histórico",
        "ok" if manual_total and manual_present == manual_total else "atenção",
        f"{manual_present}/{manual_total} artefatos de revisão/histórico presentes; fila única {int(number('curation_queue_rows'))} linhas",
        f"manual_artifacts={manual_present}/{manual_total}",
        "cedente_reviews.csv | criteria_reviews.csv | monthly_delta_actions.csv | document_chunk_actions.csv | snapshot_gap_actions.csv | dimension_catalog_gap_actions.csv",
        "Inicializar ledgers ausentes e usar a fila única e as mesas específicas para registrar decisões e auditoria.",
        "python scripts/build_fidc_industry_manual_review_ledgers.py && python scripts/build_fidc_industry_curation_queue.py",
    )
    add(
        "fic_fidc_pl_overlay",
        4,
        "Patrimônio Líquido",
        "Séries FIDCs + FIC-FIDCs e somente FIDCs com metodologia de dupla contagem",
        "ok" if has_artifact("industry_monthly") and has_artifact("vehicle_monthly") else "atenção",
        f"competência {quality_rollup.get('competencia_snapshot') or quality_rollup.get('competencia_final') or 'n/d'}; base granular e série mensal presentes",
        f"base_monthly={int(number('fund_snapshot_rows'))} FIDCs no snapshot",
        "industry_monthly.csv | vehicle_monthly.csv.gz",
        "Manter o texto metodológico e reexecutar a base mensal quando nova competência chegar.",
        "python scripts/build_fidc_industry_study.py --report",
    )
    add(
        "cedentes_structured",
        5,
        "Cedentes",
        "Base estruturada de cedentes/sacados com prioridade 2025-2026 e evidência",
        "ok" if number("cedentes_structured_rows") and number("fund_snapshot_with_cedentes") else "atenção",
        (
            f"{int(number('cedentes_structured_rows'))} linhas estruturadas; "
            f"{int(number('fund_snapshot_with_cedentes'))} FIDCs com participante identificado; "
            f"{int(number('fund_snapshot_with_participant_signal'))} com sinal regulatório; "
            f"{int(number('fund_snapshot_with_participant_signal_without_cedente'))} sinalizados sem participante"
        ),
        (
            f"cedentes={int(number('cedentes_structured_rows'))}; "
            f"sinais={int(number('fund_snapshot_with_participant_signal'))}"
        ),
        "cedentes_structured.csv.gz",
        "Priorizar FIDCs sinalizados sem participante para extrair razão social/CNPJ e fechar lacunas de fonte/página/score.",
        "python scripts/build_fidc_industry_cedentes.py",
    )
    add(
        "criteria_subordination",
        6,
        "Critérios",
        "Subordinação mínima, critérios monitoráveis e score de extração",
        "ok" if number("subordination_funds") else "atenção",
        f"{int(number('criteria_structured_rows'))} critérios; {int(number('subordination_funds'))} FIDCs com sub mínima; mediana {quality_rollup.get('subordination_median_pct')}",
        f"subordination_funds={int(number('subordination_funds'))}",
        "criteria_structured.csv.gz",
        "Completar revisão documental de regras monitoráveis e subordinação.",
        "python scripts/build_fidc_industry_criteria.py",
    )
    add(
        "dimension_catalog_traceability",
        7,
        "Base estruturada",
        "Catálogo CNPJ × dimensão × valor com fonte, documento, método e score",
        "ok" if number("dimension_catalog_rows") and number("dimension_catalog_dimensions") else "bloqueado",
        f"{int(number('dimension_catalog_rows'))} linhas; {int(number('dimension_catalog_dimensions'))} dimensões",
        f"atlas_docs={int(number('dimension_value_atlas_values_with_source_document_sample'))}; atlas_pages={int(number('dimension_value_atlas_values_with_source_page_sample'))}",
        "industry_dimension_catalog.csv.gz | industry_dimension_value_atlas.csv.gz",
        "Fechar lacunas de rastreabilidade no catálogo e rematerializar atlas/perfis.",
        "python scripts/build_fidc_industry_dimensions.py && python scripts/build_fidc_industry_dimension_monthly.py",
    )
    add(
        "heatmaps_generic",
        8,
        "Heatmaps",
        "Combinações livres e presets sem regra específica por painel",
        "ok" if number("heatmap_preset_profile_available") and number("heatmap_preset_profile_available") == number("heatmap_preset_rows") else "atenção",
        f"{int(number('heatmap_preset_profile_available'))}/{int(number('heatmap_preset_rows'))} presets com perfil materializado",
        f"market_share_dimensions={int(number('market_share_dimensions'))}",
        "industry_heatmap_registry.csv | industry_dimension_profiles.csv.gz",
        "Adicionar novas combinações pela lista declarativa de presets/dimensões.",
        "python scripts/build_fidc_industry_dimension_profiles.py",
    )
    add(
        "deep_dive_reusable",
        9,
        "Deep Dive",
        "Análises por qualquer dimensão reutilizando catálogo, atlas, perfis e dossiês",
        "ok" if number("dimension_dossier_rows") and number("dimension_dossier_blocked_rows") == 0 else "atenção",
        f"{int(number('dimension_dossier_rows'))} dossiês; {int(number('dimension_value_atlas_rows'))} valores no atlas; {int(number('dimension_profile_rows'))} células de perfil",
        f"ok={int(number('dimension_dossier_ok_rows'))}; atenção={int(number('dimension_dossier_attention_rows'))}; bloqueado={int(number('dimension_dossier_blocked_rows'))}",
        "industry_dimension_dossiers.csv | industry_dimension_value_atlas.csv.gz | industry_dimension_profiles.csv.gz",
        "Usar dossiês como camada primária do Deep Dive e completar fonte/página onde faltar.",
        "python scripts/build_fidc_industry_dimension_dossiers.py",
    )
    add(
        "market_share_concentration",
        10,
        "Market share",
        "Market share, concentração e rankings por participante/dimensão",
        "ok" if number("market_share_rows") and number("market_share_dimensions") else "atenção",
        f"{int(number('market_share_rows'))} linhas; {int(number('market_share_dimensions'))} dimensões; {int(number('market_share_metrics'))} métricas",
        f"market_share_rows={int(number('market_share_rows'))}",
        "industry_market_share.csv.gz",
        "Reexecutar após mudanças no snapshot unificado por FIDC.",
        "python scripts/build_fidc_industry_market_share.py",
    )
    add(
        "incremental_monthly_update",
        11,
        "Evolução contínua",
        "Atualização mensal incremental para novos FIDCs sem reprocessar tudo",
        "atenção" if number("curation_queue_high_priority_open_rows") else "ok",
        (
            f"{int(number('monthly_delta_rows'))} linhas de delta; "
            f"{int(number('incremental_onboarding_rows'))} FIDCs em onboarding; "
            f"{int(number('curation_queue_high_priority_open_rows'))}/{int(number('curation_queue_high_priority_rows'))} "
            "alta prioridade abertas na fila única"
        ),
        (
            f"delta_high_open={int(number('monthly_delta_high_priority_open'))}; "
            f"delta_high_total={int(number('monthly_delta_high_priority'))}; "
            f"onboarding_blocked={int(number('incremental_onboarding_blocked_rows'))}; "
            f"curation_open={int(number('curation_queue_open_rows'))}"
        ),
        "industry_monthly_delta.csv.gz | industry_incremental_onboarding.csv | industry_curation_queue.csv.gz",
        "Fechar alta prioridade da fila única antes de publicar a competência.",
        "python scripts/build_fidc_industry_monthly_delta.py && python scripts/build_fidc_industry_incremental_onboarding.py && python scripts/build_fidc_industry_curation_queue.py",
    )
    add(
        "public_audit_readiness",
        12,
        "Qualidade",
        "Camada auditável para escrutínio público com fonte, documento, página, método e score",
        "atenção"
        if (
            number("dimension_value_atlas_values_with_source_page_sample")
            < number("dimension_value_atlas_values_with_source_document_sample")
            or number("public_claim_audit_methodology_gap_claims")
        )
        else "ok",
        (
            f"{int(number('dimension_value_atlas_values_with_source_document_sample'))} valores com documento; "
            f"{int(number('dimension_value_atlas_values_with_source_page_sample'))} com página; "
            f"{int(number('dimension_value_atlas_values_with_confidence'))} com score; "
            f"{int(number('dimension_traceability_low_quality_rows'))} grupos dimensão/fonte baixa qualidade; "
            f"{int(number('public_claim_audit_rows'))} claims públicos reconciliados; "
            f"{int(number('public_claim_methodology_bridge_rows'))} pontes metodológicas"
        ),
        (
            f"readiness_checks={len(rows)}; "
            f"traceability_matrix={int(number('dimension_traceability_rows'))}; "
            f"methodology_gaps={int(number('public_claim_audit_methodology_gap_claims'))}; "
            f"bridge_high={int(number('public_claim_methodology_bridge_high_or_blocking_rows'))}"
        ),
        "industry_pipeline_index.json | industry_dimension_traceability_matrix.csv | industry_dimension_value_atlas.csv.gz | industry_public_claim_audit.csv | industry_public_claim_methodology_bridge.csv",
        "Aumentar cobertura de página/score e manter diferenças ANBIMA/CVM explícitas antes de apresentações externas.",
        "python scripts/build_fidc_industry_traceability.py && python scripts/build_fidc_industry_public_claim_audit.py && python scripts/build_fidc_industry_pipeline_index.py",
    )

    status_order = {"bloqueado": 0, "atenção": 1, "ok": 2}
    frame = pd.DataFrame(rows)
    frame["_status_order"] = frame["status_prd"].map(status_order).fillna(9)
    frame = frame.sort_values(["_status_order", "ordem"]).drop(columns=["_status_order"]).reset_index(drop=True)
    return frame.to_dict("records")


def build_industry_pipeline_index(
    *,
    industry_dir: Path,
    output_path: Path | None = None,
) -> dict[str, object]:
    """Build the monthly refresh cockpit for all Industry tab modules."""

    module_specs = [
        {
            "module_id": "manual_review_ledgers",
            "label": "Ledgers de revisão manual",
            "manifest_name": "industry_manual_review_manifest.json",
            "command": "python scripts/build_fidc_industry_manual_review_ledgers.py",
            "cadence": "antes da curadoria mensal",
            "depends_on": ["schemas de revisão manual", "UI de curadoria"],
            "quality_keys": [
                "files",
                "files_present",
                "files_created",
                "schema_ok_files",
                "domains",
                "action_files",
                "audit_files",
                "rows",
            ],
        },
        {
            "module_id": "monthly_delta",
            "label": "Delta mensal e fila de curadoria",
            "manifest_name": "industry_monthly_delta_manifest.json",
            "command": "python scripts/build_fidc_industry_monthly_delta.py",
            "cadence": "após base granular mensal",
            "depends_on": ["base granular mensal", "snapshot unificado por FIDC"],
            "quality_keys": [
                "rows",
                "competencia_atual",
                "competencia_anterior",
                "new_funds",
                "reactivated_funds",
                "exited_funds",
                "high_priority_rows",
                "high_priority_open_rows",
                "high_priority_pending_rows",
                "high_priority_in_progress_rows",
                "high_priority_closed_rows",
                "needs_document_discovery",
                "needs_cedente_review",
                "needs_criteria_review",
            ],
        },
        {
            "module_id": "incremental_onboarding",
            "label": "Onboarding incremental",
            "manifest_name": "industry_incremental_onboarding_manifest.json",
            "command": "python scripts/build_fidc_industry_incremental_onboarding.py",
            "cadence": "após delta mensal e fila única",
            "depends_on": ["delta mensal", "fila única de curadoria", "plano de chunks documentais"],
            "quality_keys": [
                "rows",
                "funds",
                "new_funds",
                "reactivated_funds",
                "blocked_rows",
                "attention_rows",
                "ok_rows",
                "discovery_blocked",
                "processing_attention",
                "incorporation_blocked",
                "open_queue_rows",
                "open_high_priority_rows",
            ],
        },
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
            "module_id": "public_claims",
            "label": "Auditoria de claims públicos",
            "manifest_name": "industry_public_claim_audit_manifest.json",
            "command": "python scripts/build_fidc_industry_public_claim_audit.py",
            "cadence": "quando fontes públicas ou números-base mudarem",
            "depends_on": ["base granular mensal", "emissões/ofertas", "claims públicos declarados"],
            "quality_keys": [
                "rows",
                "claims_with_local_metric",
                "public_sources",
                "methodology_gap_claims",
                "adherent_claims",
                "divergent_claims",
                "missing_local_claims",
                "max_abs_delta_pct",
                "methodology_bridge_rows",
                "methodology_bridge_needs_disclosure_rows",
                "methodology_bridge_high_or_blocking_rows",
                "methodology_bridge_severity_counts",
                "status_counts",
            ],
        },
        {
            "module_id": "curation_queue",
            "label": "Fila única de curadoria",
            "manifest_name": "industry_curation_queue_manifest.json",
            "command": "python scripts/build_fidc_industry_curation_queue.py",
            "cadence": "mensal/após filas operacionais",
            "depends_on": ["delta mensal", "snapshot unificado por FIDC", "documentos", "catálogo de dimensões"],
            "quality_keys": [
                "rows",
                "funds",
                "open_rows",
                "high_priority_rows",
                "high_priority_open_rows",
                "high_priority_pending_rows",
                "high_priority_in_progress_rows",
                "high_priority_closed_rows",
                "priority_2025_2026_rows",
                "summary_rows",
                "summary_type_counts",
                "fund_backlog_rows",
                "admin_backlog_rows",
                "segment_backlog_rows",
                "domain_counts",
                "status_counts",
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
                "chunk_plan_rows",
                "chunk_plan_open_rows",
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
                "feature_rows",
                "feature_funds",
                "documentary_rows",
                "documentary_funds",
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
                "with_participant_signal",
                "with_participant_signal_without_cedente",
                "with_cedente_signal",
                "with_sacado_signal",
                "with_criteria",
                "with_subordination_min",
            ],
        },
        {
            "module_id": "dimension_catalog",
            "label": "Catálogo de dimensões",
            "manifest_name": "industry_dimension_catalog_manifest.json",
            "command": "python scripts/build_fidc_industry_dimensions.py",
            "cadence": "após snapshot/cedentes",
            "depends_on": ["snapshot unificado por FIDC", "cedentes estruturados"],
            "quality_keys": [
                "rows",
                "funds",
                "dimensions",
                "curated_rows",
                "weighted_dimensions",
                "with_source_document",
                "with_confidence",
            ],
        },
        {
            "module_id": "dimension_traceability",
            "label": "Matriz de rastreabilidade",
            "manifest_name": "industry_dimension_traceability_manifest.json",
            "command": "python scripts/build_fidc_industry_traceability.py",
            "cadence": "após catálogo de dimensões",
            "depends_on": ["catálogo de dimensões"],
            "quality_keys": [
                "rows",
                "dimensions",
                "source_layers",
                "low_quality_rows",
                "missing_page_rows",
                "missing_document_rows",
                "missing_method_rows",
                "missing_score_rows",
                "median_quality_score",
                "worst_quality_score",
            ],
        },
        {
            "module_id": "dimension_monthly",
            "label": "Séries mensais por dimensão",
            "manifest_name": "industry_dimension_monthly_manifest.json",
            "command": "python scripts/build_fidc_industry_dimension_monthly.py",
            "cadence": "após catálogo de dimensões",
            "depends_on": ["base granular mensal", "catálogo de dimensões"],
            "quality_keys": [
                "rows",
                "months",
                "dimensions",
                "dimension_values",
                "latest_competencia",
                "latest_rows",
                "with_source_document_links",
                "curated_rows",
                "atlas_rows",
                "atlas_dimensions",
                "atlas_latest_competencia",
                "atlas_values_with_pl",
                "atlas_values_with_source_document_links",
                "atlas_values_with_traceability_links",
                "atlas_values_with_source_document_sample",
                "atlas_values_with_source_page_sample",
                "atlas_values_with_confidence",
                "atlas_traceability_coverage",
            ],
        },
        {
            "module_id": "dimension_profiles",
            "label": "Perfis cruzados por dimensão",
            "manifest_name": "industry_dimension_profile_manifest.json",
            "command": "python scripts/build_fidc_industry_dimension_profiles.py",
            "cadence": "após catálogo de dimensões",
            "depends_on": ["snapshot unificado por FIDC", "catálogo de dimensões"],
            "quality_keys": [
                "rows",
                "competencia",
                "source_dimensions",
                "target_dimensions",
                "source_values",
                "target_values",
                "with_source_document_links",
                "curated_links",
                "heatmap_preset_rows",
                "heatmap_preset_available",
                "heatmap_preset_profile_available",
                "heatmap_preset_status_counts",
            ],
        },
        {
            "module_id": "dimension_dossiers",
            "label": "Dossiês dimensionais",
            "manifest_name": "industry_dimension_dossier_manifest.json",
            "command": "python scripts/build_fidc_industry_dimension_dossiers.py",
            "cadence": "após atlas e perfis cruzados",
            "depends_on": ["séries mensais por dimensão", "perfis cruzados", "registry de heatmaps"],
            "quality_keys": [
                "rows",
                "dimensions",
                "ok_rows",
                "attention_rows",
                "blocked_rows",
                "atlas_values",
                "atlas_values_with_pl",
                "with_profiles",
                "profile_rows",
                "heatmap_presets",
                "heatmap_presets_ok",
                "traceability_coverage",
                "source_document_coverage",
            ],
        },
        {
            "module_id": "market_share",
            "label": "Market share e concentração",
            "manifest_name": "industry_market_share_manifest.json",
            "command": "python scripts/build_fidc_industry_market_share.py",
            "cadence": "após snapshot unificado",
            "depends_on": ["snapshot unificado por FIDC"],
            "quality_keys": [
                "rows",
                "dimensions",
                "metrics",
                "weighted_dimensions",
                "top5_pl_share_admin",
                "hhi_pl_admin",
                "source_snapshot_rows",
            ],
        },
    ]

    base_module, base_artifacts = _build_base_monthly_module(industry_dir)
    modules = [base_module]
    artifact_rows = base_artifacts
    for spec in module_specs:
        module, artifacts = _build_manifest_module(industry_dir=industry_dir, **spec)
        if spec["module_id"] == "cedentes":
            manual_artifacts = [
                _optional_artifact_row("cedentes", "cedente_reviews", industry_dir / "cedente_reviews.csv"),
                _optional_artifact_row("cedentes", "cedente_review_audit", industry_dir / "cedente_review_audit.csv"),
            ]
            artifacts.extend(manual_artifacts)
            module["artifact_count"] = len(artifacts)
            module["artifacts_present"] = sum(1 for item in artifacts if item.get("exists") is True)
        if spec["module_id"] == "criteria":
            manual_artifacts = [
                _optional_artifact_row("criteria", "criteria_reviews", industry_dir / "criteria_reviews.csv"),
                _optional_artifact_row("criteria", "criteria_review_audit", industry_dir / "criteria_review_audit.csv"),
            ]
            artifacts.extend(manual_artifacts)
            module["artifact_count"] = len(artifacts)
            module["artifacts_present"] = sum(1 for item in artifacts if item.get("exists") is True)
        if spec["module_id"] == "monthly_delta":
            manual_artifacts = [
                _optional_artifact_row("monthly_delta", "monthly_delta_actions", industry_dir / "monthly_delta_actions.csv"),
                _optional_artifact_row("monthly_delta", "monthly_delta_action_audit", industry_dir / "monthly_delta_action_audit.csv"),
            ]
            artifacts.extend(manual_artifacts)
            module["artifact_count"] = len(artifacts)
            module["artifacts_present"] = sum(1 for item in artifacts if item.get("exists") is True)
        if spec["module_id"] == "documents":
            derived_artifacts = [
                _optional_artifact_row("documents", "document_chunk_plan", industry_dir / "document_chunk_plan.csv", group="derived"),
            ]
            artifacts.extend(derived_artifacts)
            manual_artifacts = [
                _optional_artifact_row("documents", "document_chunk_actions", industry_dir / "document_chunk_actions.csv"),
                _optional_artifact_row("documents", "document_chunk_action_audit", industry_dir / "document_chunk_action_audit.csv"),
            ]
            artifacts.extend(manual_artifacts)
            module["artifact_count"] = len(artifacts)
            module["artifacts_present"] = sum(1 for item in artifacts if item.get("exists") is True)
        if spec["module_id"] == "fund_snapshot":
            manual_artifacts = [
                _optional_artifact_row("fund_snapshot", "snapshot_gap_actions", industry_dir / "snapshot_gap_actions.csv"),
                _optional_artifact_row("fund_snapshot", "snapshot_gap_action_audit", industry_dir / "snapshot_gap_action_audit.csv"),
            ]
            artifacts.extend(manual_artifacts)
            module["artifact_count"] = len(artifacts)
            module["artifacts_present"] = sum(1 for item in artifacts if item.get("exists") is True)
        if spec["module_id"] == "dimension_catalog":
            manual_artifacts = [
                _optional_artifact_row("dimension_catalog", "dimension_catalog_gap_actions", industry_dir / "dimension_catalog_gap_actions.csv"),
                _optional_artifact_row("dimension_catalog", "dimension_catalog_gap_action_audit", industry_dir / "dimension_catalog_gap_action_audit.csv"),
            ]
            artifacts.extend(manual_artifacts)
            module["artifact_count"] = len(artifacts)
            module["artifacts_present"] = sum(1 for item in artifacts if item.get("exists") is True)
        modules.append(module)
        artifact_rows.extend(artifacts)

    control_output_path = output_path if output_path is not None else industry_dir / "industry_pipeline_index.json"
    artifact_rows.extend(
        [
            {
                "module_id": "pipeline_index",
                "group": "outputs",
                "artifact": "industry_pipeline_index",
                "required": False,
                **file_fingerprint(control_output_path),
            },
            {
                "module_id": "pipeline_index",
                "group": "outputs",
                "artifact": "industry_monthly_update_plan",
                "required": False,
                **file_fingerprint(industry_dir / "industry_monthly_update_plan.csv"),
            },
            {
                "module_id": "pipeline_index",
                "group": "outputs",
                "artifact": "industry_monthly_readiness",
                "required": False,
                **file_fingerprint(industry_dir / "industry_monthly_readiness.csv"),
            },
            {
                "module_id": "pipeline_index",
                "group": "outputs",
                "artifact": "industry_publication_gate",
                "required": False,
                **file_fingerprint(industry_dir / "industry_publication_gate.csv"),
            },
        ]
    )

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
            "module_id": "manual_review_ledgers",
            "label": "Inicializar ledgers de revisão manual",
            "command": "python scripts/build_fidc_industry_manual_review_ledgers.py",
            "reason": "Garante arquivos de ações e auditoria com schema oficial antes de qualquer edição na UI.",
            "incremental_note": "Cria apenas arquivos ausentes; não cria decisões, aprovações ou eventos artificiais.",
        },
        {
            "order": 3,
            "module_id": "monthly_delta",
            "label": "Gerar delta mensal e fila de curadoria",
            "command": "python scripts/build_fidc_industry_monthly_delta.py",
            "reason": "Identifica FIDCs novos, reativados ou ausentes e aponta lacunas de documentos, cedentes, critérios e subordinação.",
            "incremental_note": "Compara apenas competência snapshot contra a anterior e cruza camadas já materializadas.",
        },
        {
            "order": 4,
            "module_id": "incremental_onboarding",
            "label": "Materializar onboarding dos FIDCs novos/reativados",
            "command": "python scripts/build_fidc_industry_incremental_onboarding.py",
            "reason": "Consolida descoberta, processamento documental e incorporação estruturada em uma linha por FIDC novo ou reativado.",
            "incremental_note": "Lê apenas delta mensal, fila única e plano de chunks; não reprocessa informes nem documentos.",
        },
        {
            "order": 5,
            "module_id": "issuance",
            "label": "Reconciliar emissões/ofertas",
            "command": "python scripts/build_fidc_industry_issuance.py",
            "reason": "Refaz séries de volume anual, emissores, setor x ano e tranches documentais.",
            "incremental_note": "Lê o SQLite da Estratégia já estruturado; não depende de Informe Mensal.",
        },
        {
            "order": 6,
            "module_id": "public_claims",
            "label": "Auditar claims públicos",
            "command": "python scripts/build_fidc_industry_public_claim_audit.py",
            "reason": "Compara números citados por ANBIMA/Seu Dinheiro contra métricas locais e explicita divergências de universo/conceito.",
            "incremental_note": "Rerun leve quando uma nova notícia for adicionada aos specs ou quando base mensal/emissões forem atualizadas.",
        },
        {
            "order": 7,
            "module_id": "documents",
            "label": "Inventariar documentação pública",
            "command": "python scripts/build_fidc_industry_documents.py",
            "reason": "Atualiza fingerprints, classes documentais e chunks pequenos para processamento posterior.",
            "incremental_note": "Use --chunk-id doc-0001 para rodar ou depurar lotes sem reprocessar a indústria toda.",
        },
        {
            "order": 8,
            "module_id": "document_chunk_plan",
            "label": "Atualizar plano operacional de chunks",
            "command": "python scripts/build_fidc_industry_document_chunk_plan.py",
            "reason": "Aplica o acompanhamento salvo na UI sobre inventário e chunks para priorizar download, fingerprint, OCR, parsing e extração.",
            "incremental_note": "Rerun leve quando o usuário muda status/responsável/prazo na aba Documentos > Chunks.",
        },
        {
            "order": 9,
            "module_id": "cedentes",
            "label": "Regerar base de cedentes/sacados",
            "command": "python scripts/build_fidc_industry_cedentes.py",
            "reason": "Aplica revisões manuais e expõe participantes para heatmaps e deep dives.",
            "incremental_note": "A curadoria continua sendo feita pela UI e reaplicada pelo overlay persistido.",
        },
        {
            "order": 10,
            "module_id": "criteria",
            "label": "Regerar critérios e subordinação mínima",
            "command": "python scripts/build_fidc_industry_criteria.py",
            "reason": "Atualiza regras monitoráveis, sub mínima e status de revisão por fundo.",
            "incremental_note": "Revisões feitas pela UI são reaplicadas antes da consolidação.",
        },
        {
            "order": 11,
            "module_id": "fund_snapshot",
            "label": "Regerar snapshot unificado por FIDC",
            "command": "python scripts/build_fidc_industry_fund_snapshot.py",
            "reason": "Consolida uma linha por CNPJ com IME, emissões, documentos, cedentes e critérios.",
            "incremental_note": "Não apaga granularidade; apenas resume camadas já materializadas e preserva caminhos de origem.",
        },
        {
            "order": 12,
            "module_id": "dimension_catalog",
            "label": "Regerar catálogo de dimensões",
            "command": "python scripts/build_fidc_industry_dimensions.py",
            "reason": "Explode CNPJ x dimensão x valor com pesos, fonte e metadados de curadoria.",
            "incremental_note": "Lê snapshot e cedentes estruturados; não reprocessa informe mensal nem documentos.",
        },
        {
            "order": 13,
            "module_id": "dimension_traceability",
            "label": "Regerar matriz de rastreabilidade",
            "command": "python scripts/build_fidc_industry_traceability.py",
            "reason": "Resume cobertura de documento, página, data, método, score e revisão por dimensão e camada de fonte.",
            "incremental_note": "Lê apenas o catálogo de dimensões; ajuda a priorizar lacunas antes de uso público.",
        },
        {
            "order": 14,
            "module_id": "curation_queue",
            "label": "Consolidar fila única de curadoria",
            "command": "python scripts/build_fidc_industry_curation_queue.py",
            "reason": "Une delta mensal, lacunas all-FIDCs, chunks documentais e rastreabilidade do catálogo em uma fila operacional.",
            "incremental_note": "Rerun leve depois de salvar ações manuais na UI ou de regenerar qualquer fila detalhe.",
        },
        {
            "order": 15,
            "module_id": "dimension_profiles",
            "label": "Regerar perfis cruzados por dimensão",
            "command": "python scripts/build_fidc_industry_dimension_profiles.py",
            "reason": "Materializa composição de cada dimensão por outras dimensões para Deep Dive e heatmaps sem cálculo ad hoc.",
            "incremental_note": "Lê apenas snapshot e catálogo; pesos de dimensões multivalor são aplicados no agregado.",
        },
        {
            "order": 16,
            "module_id": "dimension_monthly",
            "label": "Regerar séries mensais por dimensão",
            "command": "python scripts/build_fidc_industry_dimension_monthly.py",
            "reason": "Agrega PL, fluxos, carteira, inadimplência, fundos e veículos por competência × dimensão × valor.",
            "incremental_note": "Lê o catálogo e a base granular mensal; evita recomputar séries no momento da interação.",
        },
        {
            "order": 17,
            "module_id": "dimension_dossiers",
            "label": "Regerar dossiês dimensionais",
            "command": "python scripts/build_fidc_industry_dimension_dossiers.py",
            "reason": "Resume cobertura, evidência, perfis e presets de cada dimensão para Deep Dive e auditoria mês a mês.",
            "incremental_note": "Lê apenas atlas, perfis e registry já materializados; não reprocessa documentos ou informe mensal.",
        },
        {
            "order": 18,
            "module_id": "market_share",
            "label": "Regerar market share e concentração",
            "command": "python scripts/build_fidc_industry_market_share.py",
            "reason": "Materializa rankings por administrador, segmento, documentos, critérios e dimensões multivalor.",
            "incremental_note": "Lê apenas o snapshot unificado; dimensões multivalor são ponderadas sem reprocessar bases detalhe.",
        },
        {
            "order": 19,
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
    required_artifacts = [item for item in artifact_rows if item.get("required") is True]
    optional_artifacts = [item for item in artifact_rows if item.get("required") is not True]
    manual_review_artifacts = [item for item in artifact_rows if item.get("group") == "manual_review"]
    artifact_total = len(required_artifacts)
    artifact_present = sum(1 for item in required_artifacts if item.get("exists") is True)
    optional_artifact_total = len(optional_artifacts)
    optional_artifact_present = sum(1 for item in optional_artifacts if item.get("exists") is True)
    manual_review_artifact_total = len(manual_review_artifacts)
    manual_review_artifact_present = sum(1 for item in manual_review_artifacts if item.get("exists") is True)
    base_meta = base_module.get("quality_highlights", {})
    monthly_delta_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "monthly_delta"), {})
    onboarding_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "incremental_onboarding"), {})
    curation_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "curation_queue"), {})
    criteria_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "criteria"), {})
    document_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "documents"), {})
    cedente_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "cedentes"), {})
    issuance_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "issuance"), {})
    public_claim_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "public_claims"), {})
    snapshot_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "fund_snapshot"), {})
    dimension_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "dimension_catalog"), {})
    traceability_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "dimension_traceability"), {})
    dimension_monthly_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "dimension_monthly"), {})
    dimension_profile_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "dimension_profiles"), {})
    dimension_dossier_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "dimension_dossiers"), {})
    market_quality = next((m.get("quality_highlights", {}) for m in modules if m.get("id") == "market_share"), {})
    criteria_manifest = _safe_read_json(industry_dir / "industry_criteria_manifest.json")
    subordination = criteria_manifest.get("quality", {}).get("subordination", {}) if isinstance(criteria_manifest.get("quality"), dict) else {}
    document_chunks_total = int(document_quality.get("chunks", 0) or 0)
    document_chunk_plan_rows = int(document_quality.get("chunk_plan_rows", 0) or 0)
    document_chunk_plan_open_rows = int(document_quality.get("chunk_plan_open_rows", 0) or 0)
    document_chunk_actions = load_dataframe(industry_dir / "document_chunk_actions.csv")
    if document_chunk_actions.empty or "chunk_id" not in document_chunk_actions.columns:
        document_chunk_action_rows = 0
        document_chunk_status_counts: dict[str, int] = {}
    else:
        document_chunk_actions = document_chunk_actions.copy()
        document_chunk_actions["chunk_id"] = document_chunk_actions["chunk_id"].fillna("").astype(str)
        document_chunk_actions = document_chunk_actions[document_chunk_actions["chunk_id"].str.strip().ne("")]
        document_chunk_actions = document_chunk_actions.drop_duplicates("chunk_id", keep="last")
        status_series = (
            document_chunk_actions.get("status_lote", pd.Series("", index=document_chunk_actions.index))
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
            .replace("", "pendente")
        )
        document_chunk_status_counts = {str(k): int(v) for k, v in status_series.value_counts().to_dict().items()}
        document_chunk_action_rows = int(len(document_chunk_actions))
    document_chunks_without_action = max(document_chunks_total - document_chunk_action_rows, 0)
    document_chunks_pending_action = document_chunk_status_counts.get("pendente", 0)
    document_chunks_in_progress = document_chunk_status_counts.get("em andamento", 0)
    document_chunks_blocked = document_chunk_status_counts.get("bloqueado", 0)
    document_chunks_processed = (
        document_chunk_status_counts.get("processado", 0)
        + document_chunk_status_counts.get("ignorado", 0)
    )
    quality_rollup = {
        "modules_total": len(modules),
        "module_status_counts": status_counts,
        "artifacts_total": artifact_total,
        "artifacts_present": artifact_present,
        "artifacts_missing": artifact_total - artifact_present,
        "optional_artifacts_total": optional_artifact_total,
        "optional_artifacts_present": optional_artifact_present,
        "optional_artifacts_missing": optional_artifact_total - optional_artifact_present,
        "manual_review_artifacts_total": manual_review_artifact_total,
        "manual_review_artifacts_present": manual_review_artifact_present,
        "manual_review_artifacts_missing": manual_review_artifact_total - manual_review_artifact_present,
        "latest_module_generated_at_utc": _latest_iso(generated_values),
        "competencia_final": base_meta.get("competencia_final", ""),
        "competencia_snapshot": base_meta.get("competencia_snapshot", ""),
        "monthly_delta_rows": monthly_delta_quality.get("rows", 0),
        "monthly_delta_competencia_atual": monthly_delta_quality.get("competencia_atual", ""),
        "monthly_delta_competencia_anterior": monthly_delta_quality.get("competencia_anterior", ""),
        "monthly_delta_new_funds": monthly_delta_quality.get("new_funds", 0),
        "monthly_delta_reactivated_funds": monthly_delta_quality.get("reactivated_funds", 0),
        "monthly_delta_high_priority": monthly_delta_quality.get("high_priority_rows", 0),
        "monthly_delta_high_priority_open": monthly_delta_quality.get("high_priority_open_rows", 0),
        "monthly_delta_high_priority_pending": monthly_delta_quality.get("high_priority_pending_rows", 0),
        "monthly_delta_high_priority_in_progress": monthly_delta_quality.get("high_priority_in_progress_rows", 0),
        "monthly_delta_high_priority_closed": monthly_delta_quality.get("high_priority_closed_rows", 0),
        "incremental_onboarding_rows": onboarding_quality.get("rows", 0),
        "incremental_onboarding_funds": onboarding_quality.get("funds", 0),
        "incremental_onboarding_new_funds": onboarding_quality.get("new_funds", 0),
        "incremental_onboarding_reactivated_funds": onboarding_quality.get("reactivated_funds", 0),
        "incremental_onboarding_blocked_rows": onboarding_quality.get("blocked_rows", 0),
        "incremental_onboarding_attention_rows": onboarding_quality.get("attention_rows", 0),
        "incremental_onboarding_ok_rows": onboarding_quality.get("ok_rows", 0),
        "incremental_onboarding_open_queue_rows": onboarding_quality.get("open_queue_rows", 0),
        "incremental_onboarding_open_high_priority_rows": onboarding_quality.get("open_high_priority_rows", 0),
        "curation_queue_rows": curation_quality.get("rows", 0),
        "curation_queue_funds": curation_quality.get("funds", 0),
        "curation_queue_open_rows": curation_quality.get("open_rows", 0),
        "curation_queue_high_priority_rows": curation_quality.get("high_priority_rows", 0),
        "curation_queue_high_priority_open_rows": curation_quality.get("high_priority_open_rows", 0),
        "curation_queue_high_priority_pending_rows": curation_quality.get("high_priority_pending_rows", 0),
        "curation_queue_high_priority_in_progress_rows": curation_quality.get("high_priority_in_progress_rows", 0),
        "curation_queue_high_priority_closed_rows": curation_quality.get("high_priority_closed_rows", 0),
        "curation_queue_priority_2025_2026_rows": curation_quality.get("priority_2025_2026_rows", 0),
        "curation_queue_summary_rows": curation_quality.get("summary_rows", 0),
        "curation_queue_fund_backlog_rows": curation_quality.get("fund_backlog_rows", 0),
        "curation_queue_admin_backlog_rows": curation_quality.get("admin_backlog_rows", 0),
        "curation_queue_segment_backlog_rows": curation_quality.get("segment_backlog_rows", 0),
        "document_chunks": document_chunks_total,
        "document_chunk_plan_rows": document_chunk_plan_rows,
        "document_chunk_plan_open_rows": document_chunk_plan_open_rows,
        "max_documents_per_chunk": document_quality.get("max_documents_per_chunk", 0),
        "document_chunk_actions_rows": document_chunk_action_rows,
        "document_chunk_action_status_counts": document_chunk_status_counts,
        "document_chunks_without_action": document_chunks_without_action,
        "document_chunks_pending_action": document_chunks_pending_action,
        "document_chunks_in_progress": document_chunks_in_progress,
        "document_chunks_blocked": document_chunks_blocked,
        "document_chunks_processed": document_chunks_processed,
        "cedentes_structured_rows": cedente_quality.get("structured_rows", 0),
        "criteria_structured_rows": criteria_quality.get("structured_rows", 0),
        "subordination_funds": criteria_quality.get("subordination_funds", 0),
        "subordination_median_pct": subordination.get("median") if isinstance(subordination, dict) else None,
        "issuance_volume_conservador_brl": issuance_quality.get("annual_volume_conservador_brl", 0),
        "public_claim_audit_rows": public_claim_quality.get("rows", 0),
        "public_claim_audit_claims_with_local_metric": public_claim_quality.get("claims_with_local_metric", 0),
        "public_claim_audit_sources": public_claim_quality.get("public_sources", 0),
        "public_claim_audit_methodology_gap_claims": public_claim_quality.get("methodology_gap_claims", 0),
        "public_claim_audit_adherent_claims": public_claim_quality.get("adherent_claims", 0),
        "public_claim_audit_divergent_claims": public_claim_quality.get("divergent_claims", 0),
        "public_claim_audit_missing_local_claims": public_claim_quality.get("missing_local_claims", 0),
        "public_claim_audit_max_abs_delta_pct": public_claim_quality.get("max_abs_delta_pct"),
        "public_claim_methodology_bridge_rows": public_claim_quality.get("methodology_bridge_rows", 0),
        "public_claim_methodology_bridge_needs_disclosure_rows": public_claim_quality.get(
            "methodology_bridge_needs_disclosure_rows", 0
        ),
        "public_claim_methodology_bridge_high_or_blocking_rows": public_claim_quality.get(
            "methodology_bridge_high_or_blocking_rows", 0
        ),
        "fund_snapshot_rows": snapshot_quality.get("fund_rows", 0),
        "fund_snapshot_with_cedentes": snapshot_quality.get("with_cedentes", 0),
        "fund_snapshot_with_participant_signal": snapshot_quality.get("with_participant_signal", 0),
        "fund_snapshot_with_participant_signal_without_cedente": snapshot_quality.get(
            "with_participant_signal_without_cedente", 0
        ),
        "fund_snapshot_with_cedente_signal": snapshot_quality.get("with_cedente_signal", 0),
        "fund_snapshot_with_sacado_signal": snapshot_quality.get("with_sacado_signal", 0),
        "fund_snapshot_with_criteria": snapshot_quality.get("with_criteria", 0),
        "dimension_catalog_rows": dimension_quality.get("rows", 0),
        "dimension_catalog_dimensions": dimension_quality.get("dimensions", 0),
        "dimension_traceability_rows": traceability_quality.get("rows", 0),
        "dimension_traceability_low_quality_rows": traceability_quality.get("low_quality_rows", 0),
        "dimension_traceability_missing_page_rows": traceability_quality.get("missing_page_rows", 0),
        "dimension_traceability_missing_document_rows": traceability_quality.get("missing_document_rows", 0),
        "dimension_traceability_missing_method_rows": traceability_quality.get("missing_method_rows", 0),
        "dimension_traceability_missing_score_rows": traceability_quality.get("missing_score_rows", 0),
        "dimension_traceability_median_quality_score": traceability_quality.get("median_quality_score"),
        "dimension_monthly_rows": dimension_monthly_quality.get("rows", 0),
        "dimension_monthly_latest_competencia": dimension_monthly_quality.get("latest_competencia", ""),
        "dimension_value_atlas_rows": dimension_monthly_quality.get("atlas_rows", 0),
        "dimension_value_atlas_dimensions": dimension_monthly_quality.get("atlas_dimensions", 0),
        "dimension_value_atlas_latest_competencia": dimension_monthly_quality.get("atlas_latest_competencia", ""),
        "dimension_value_atlas_values_with_pl": dimension_monthly_quality.get("atlas_values_with_pl", 0),
        "dimension_value_atlas_values_with_source_document_links": dimension_monthly_quality.get(
            "atlas_values_with_source_document_links", 0
        ),
        "dimension_value_atlas_values_with_traceability_links": dimension_monthly_quality.get(
            "atlas_values_with_traceability_links", 0
        ),
        "dimension_value_atlas_values_with_source_document_sample": dimension_monthly_quality.get(
            "atlas_values_with_source_document_sample", 0
        ),
        "dimension_value_atlas_values_with_source_page_sample": dimension_monthly_quality.get(
            "atlas_values_with_source_page_sample", 0
        ),
        "dimension_value_atlas_values_with_confidence": dimension_monthly_quality.get("atlas_values_with_confidence", 0),
        "dimension_value_atlas_traceability_coverage": dimension_monthly_quality.get("atlas_traceability_coverage"),
        "dimension_profile_rows": dimension_profile_quality.get("rows", 0),
        "dimension_profile_source_dimensions": dimension_profile_quality.get("source_dimensions", 0),
        "heatmap_preset_rows": dimension_profile_quality.get("heatmap_preset_rows", 0),
        "heatmap_preset_available": dimension_profile_quality.get("heatmap_preset_available", 0),
        "heatmap_preset_profile_available": dimension_profile_quality.get("heatmap_preset_profile_available", 0),
        "dimension_dossier_rows": dimension_dossier_quality.get("rows", 0),
        "dimension_dossier_ok_rows": dimension_dossier_quality.get("ok_rows", 0),
        "dimension_dossier_attention_rows": dimension_dossier_quality.get("attention_rows", 0),
        "dimension_dossier_blocked_rows": dimension_dossier_quality.get("blocked_rows", 0),
        "dimension_dossier_atlas_values": dimension_dossier_quality.get("atlas_values", 0),
        "dimension_dossier_with_profiles": dimension_dossier_quality.get("with_profiles", 0),
        "dimension_dossier_profile_rows": dimension_dossier_quality.get("profile_rows", 0),
        "dimension_dossier_heatmap_presets": dimension_dossier_quality.get("heatmap_presets", 0),
        "dimension_dossier_traceability_coverage": dimension_dossier_quality.get("traceability_coverage"),
        "dimension_dossier_source_document_coverage": dimension_dossier_quality.get("source_document_coverage"),
        "market_share_rows": market_quality.get("rows", 0),
        "market_share_dimensions": market_quality.get("dimensions", 0),
        "market_share_metrics": market_quality.get("metrics", 0),
    }
    readiness_checks = build_pipeline_readiness_checks(
        modules=modules,
        artifact_rows=artifact_rows,
        quality_rollup=quality_rollup,
    )
    readiness_status_counts: dict[str, int] = {}
    for row in readiness_checks:
        status = str(row.get("status_prontidao") or "n/d")
        readiness_status_counts[status] = readiness_status_counts.get(status, 0) + 1
    quality_rollup["readiness_checks_rows"] = len(readiness_checks)
    quality_rollup["readiness_status_counts"] = readiness_status_counts
    prd_coverage = build_prd_coverage_matrix(
        quality_rollup=quality_rollup,
        artifact_rows=artifact_rows,
        refresh_plan=refresh_plan,
    )
    prd_status_counts: dict[str, int] = {}
    for row in prd_coverage:
        status = str(row.get("status_prd") or "n/d")
        prd_status_counts[status] = prd_status_counts.get(status, 0) + 1
    quality_rollup["prd_requirements_total"] = len(prd_coverage)
    quality_rollup["prd_status_counts"] = prd_status_counts
    monthly_update_plan = build_monthly_update_plan(
        modules=modules,
        artifact_rows=artifact_rows,
        refresh_plan=refresh_plan,
        readiness_checks=readiness_checks,
        quality_rollup=quality_rollup,
    )
    update_plan_status_counts: dict[str, int] = {}
    for row in monthly_update_plan:
        status = str(row.get("status_prontidao") or "n/d")
        update_plan_status_counts[status] = update_plan_status_counts.get(status, 0) + 1
    quality_rollup["monthly_update_plan_rows"] = len(monthly_update_plan)
    quality_rollup["monthly_update_plan_status_counts"] = update_plan_status_counts
    publication_gate = build_monthly_publication_gate(
        readiness_checks=readiness_checks,
        prd_coverage=prd_coverage,
        monthly_update_plan=monthly_update_plan,
        quality_rollup=quality_rollup,
    )
    gate_status_counts: dict[str, int] = {}
    gate_blocking_rows = 0
    gate_disclosure_rows = 0
    for row in publication_gate:
        status = str(row.get("status_gate") or "n/d")
        gate_status_counts[status] = gate_status_counts.get(status, 0) + 1
        if row.get("bloqueia_publicacao") is True:
            gate_blocking_rows += 1
        if row.get("exige_nota_publica") is True:
            gate_disclosure_rows += 1
    quality_rollup["publication_gate_rows"] = len(publication_gate)
    quality_rollup["publication_gate_status"] = (
        str(publication_gate[0].get("status_gate") or "n/d") if publication_gate else "n/d"
    )
    quality_rollup["publication_gate_status_counts"] = gate_status_counts
    quality_rollup["publication_gate_blocking_rows"] = gate_blocking_rows
    quality_rollup["publication_gate_disclosure_rows"] = gate_disclosure_rows
    manual_review_ledger = build_manual_review_ledger(industry_dir=industry_dir)
    manual_review_status_counts: dict[str, int] = {}
    for row in manual_review_ledger:
        status = str(row.get("status_ledger") or "n/d")
        manual_review_status_counts[status] = manual_review_status_counts.get(status, 0) + 1
    quality_rollup["manual_review_domains_total"] = len(manual_review_ledger)
    quality_rollup["manual_review_domains_with_actions"] = sum(
        1 for row in manual_review_ledger if int(row.get("action_rows", 0) or 0) > 0
    )
    quality_rollup["manual_review_domains_with_audit"] = sum(
        1 for row in manual_review_ledger if int(row.get("audit_events", 0) or 0) > 0
    )
    quality_rollup["manual_review_action_rows"] = sum(int(row.get("action_rows", 0) or 0) for row in manual_review_ledger)
    quality_rollup["manual_review_audit_events"] = sum(int(row.get("audit_events", 0) or 0) for row in manual_review_ledger)
    quality_rollup["manual_review_status_counts"] = manual_review_status_counts
    quality_rollup["manual_review_latest_audit_utc"] = _latest_iso(
        [row.get("latest_audit_utc", "") for row in manual_review_ledger]
    )

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
        "quality_rollup": quality_rollup,
        "readiness_checks": readiness_checks,
        "prd_coverage": prd_coverage,
        "monthly_update_plan": monthly_update_plan,
        "publication_gate": publication_gate,
        "manual_review_ledger": manual_review_ledger,
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
    if active.empty:
        identified = active
        signal_placeholders = active
    else:
        has_name = _nonempty_series(active.get("razao_social", pd.Series("", index=active.index)))
        has_cnpj = _nonempty_series(active.get("cnpj_participante", pd.Series("", index=active.index)))
        identified = active[has_name | has_cnpj].copy()
        if "signal_placeholder" in active.columns:
            placeholder_mask = active["signal_placeholder"].astype(str).str.lower().isin({"true", "1", "sim"})
        else:
            placeholder_mask = active.get("metodo_extracao", pd.Series("", index=active.index)).astype(str).eq("strategy_regulatory_feature_signal")
        signal_placeholders = active[placeholder_mask].copy()
    return {
        "candidate_rows": int(len(candidates)),
        "candidate_funds": int(candidates["cnpj_fundo"].nunique()) if "cnpj_fundo" in candidates else 0,
        "structured_rows": int(len(structured)),
        "active_rows": int(len(active)),
        "structured_funds": int(structured["cnpj_fundo"].nunique()) if "cnpj_fundo" in structured else 0,
        "identified_rows": int(len(identified)),
        "identified_funds": int(identified["cnpj_fundo"].nunique()) if "cnpj_fundo" in identified else 0,
        "signal_placeholder_rows": int(len(signal_placeholders)),
        "signal_placeholder_funds": int(signal_placeholders["cnpj_fundo"].nunique()) if "cnpj_fundo" in signal_placeholders else 0,
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
    outputs = {
        "cedentes_structured": file_fingerprint(output_path),
        "manifest": {"path": str(industry_dir / "industry_pipeline_manifest.json")},
    }
    review_audit_path = industry_dir / "cedente_review_audit.csv"
    if review_audit_path.exists():
        outputs["review_audit"] = file_fingerprint(review_audit_path)
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
        "outputs": outputs,
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
                "funds": int(quality.get("structured_funds", 0) or 0),
                "identified_funds": int(quality.get("identified_funds", 0) or 0),
                "signal_placeholder_funds": int(quality.get("signal_placeholder_funds", 0) or 0),
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


def build_public_claim_audit_pipeline_manifest(
    *,
    industry_dir: Path,
    output_path: Path,
    bridge_path: Path,
    manifest_path: Path,
    industry_monthly_path: Path,
    issuance_tranches_path: Path,
    industry_monthly: pd.DataFrame,
    issuance_tranches: pd.DataFrame,
    audit: pd.DataFrame,
    bridge: pd.DataFrame,
) -> dict[str, object]:
    quality = public_claim_audit_quality_summary(audit)
    bridge_quality = public_claim_methodology_bridge_quality_summary(bridge)
    quality = {
        **quality,
        "methodology_bridge_rows": bridge_quality.get("rows", 0),
        "methodology_bridge_needs_disclosure_rows": bridge_quality.get("needs_disclosure_rows", 0),
        "methodology_bridge_high_or_blocking_rows": bridge_quality.get("high_or_blocking_rows", 0),
        "methodology_bridge_severity_counts": bridge_quality.get("severity_counts", {}),
    }
    return {
        "schema_version": "industry-public-claim-audit-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_public_claim_audit",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "macbook_air_m4_friendly": True,
            "notes": [
                "Este modulo compara claims publicos contra metricas locais ja materializadas.",
                "Divergencias metodologicas sao preservadas como evidência, não corrigidas por ajuste ad hoc.",
                "O objetivo é preparar a aba para escrutinio publico antes de apresentacoes executivas.",
            ],
        },
        "inputs": {
            "industry_monthly": file_fingerprint(industry_monthly_path),
            "issuance_tranches": file_fingerprint(issuance_tranches_path),
            "public_claim_specs": {
                "exists": True,
                "rows": len(PUBLIC_CLAIM_SPECS),
                "source": "services.industry_study.PUBLIC_CLAIM_SPECS",
            },
        },
        "outputs": {
            "public_claim_audit": file_fingerprint(output_path),
            "methodology_bridge": file_fingerprint(bridge_path),
            "manifest": {"path": str(manifest_path)},
        },
        "stages": [
            {
                "id": "load_local_metrics",
                "label": "Carregar métricas locais",
                "status": "ok" if not industry_monthly.empty else "empty",
                "input": f"{industry_monthly_path} | {issuance_tranches_path}",
                "output": "memoria:industry_monthly+issuance_tranches",
                "rows": int(len(industry_monthly)),
                "rerun": "python scripts/build_fidc_industry_study.py --report && python scripts/build_fidc_industry_issuance.py",
            },
            {
                "id": "compare_public_claims",
                "label": "Comparar claims públicos",
                "status": "ok" if not audit.empty else "empty",
                "input": "PUBLIC_CLAIM_SPECS",
                "output": str(output_path),
                "rows": int(len(audit)),
                "claims_with_local_metric": int(quality.get("claims_with_local_metric", 0) or 0),
                "rerun": "python scripts/build_fidc_industry_public_claim_audit.py",
            },
            {
                "id": "classify_methodology_gaps",
                "label": "Classificar aderência/metodologia",
                "status": "ok" if int(quality.get("claims_with_local_metric", 0) or 0) else "empty",
                "input": str(output_path),
                "output": str(bridge_path),
                "methodology_gap_claims": int(quality.get("methodology_gap_claims", 0) or 0),
                "adherent_claims": int(quality.get("adherent_claims", 0) or 0),
                "methodology_bridge_rows": int(bridge_quality.get("rows", 0) or 0),
                "high_or_blocking_rows": int(bridge_quality.get("high_or_blocking_rows", 0) or 0),
                "rerun": "python scripts/build_fidc_industry_public_claim_audit.py",
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
    outputs = {
        "criteria_structured": file_fingerprint(output_path),
        "manifest": {"path": str(manifest_path)},
    }
    review_audit_path = industry_dir / "criteria_review_audit.csv"
    if review_audit_path.exists():
        outputs["review_audit"] = file_fingerprint(review_audit_path)
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
        "outputs": outputs,
        "stages": [
            {
                "id": "load_documentary_criteria",
                "label": "Critérios documentais",
                "status": "ok" if not criteria.empty else "empty",
                "input": str(criteria_source_path),
                "output": "memoria:all_fidcs_criteria_monitoraveis_ime",
                "rows": int(quality.get("documentary_rows", 0) or 0),
                "funds": int(quality.get("documentary_funds", 0) or 0),
                "rerun": "python scripts/classify_fidc_sectors_and_practices.py",
            },
            {
                "id": "load_strategy_regulatory_features",
                "label": "Features regulatórias da Estratégia",
                "status": "ok" if int(quality.get("feature_rows", 0) or 0) else "empty",
                "input": str(strategy_db),
                "output": "memoria:regulatory_feature_long",
                "rows": int(quality.get("feature_rows", 0) or 0),
                "funds": int(quality.get("feature_funds", 0) or 0),
                "rerun": "python scripts/execute_fidc_director_diagnostic.py --download-limit 0",
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
        keys = group.get("chave", pd.Series("", index=group.index)).fillna("").astype(str)
        sub = group[keys.eq("subordination_ratio_min")]
        cedente_signal = group[keys.eq("feature_named_originator_or_cedente")]
        sacado_signal = group[keys.eq("feature_named_debtor_or_sacado")]
        participant_signal = group[keys.isin({"feature_named_originator_or_cedente", "feature_named_debtor_or_sacado"})]
        row = {
            "cnpj_fundo": cnpj,
            "criteria_rows": int(len(group)),
            "criteria_monitorable_rows": int(monitor.eq("monitoravel").sum()),
            "criteria_partial_rows": int(monitor.eq("parcial").sum()),
            "criteria_not_monitorable_rows": int(monitor.eq("nao_monitoravel").sum()),
            "criteria_subordination_rows": int(len(sub)),
            "cedente_signal_rows": int(len(cedente_signal)),
            "sacado_signal_rows": int(len(sacado_signal)),
            "participant_signal_rows": int(len(participant_signal)),
            "sub_min_pct_median": _median_numeric(sub.get("pct_min", pd.Series(dtype=float))),
            "sub_min_pct_min": _json_float(pd.to_numeric(sub.get("pct_min", pd.Series(dtype=float)), errors="coerce").min()) if not sub.empty else None,
            "sub_min_pct_max": _json_float(pd.to_numeric(sub.get("pct_min", pd.Series(dtype=float)), errors="coerce").max()) if not sub.empty else None,
            "criteria_keys": _join_unique(group.get("chave", pd.Series(dtype=str)), limit=8),
            "participant_signal_keys": _join_unique(participant_signal.get("chave", pd.Series(dtype=str)), limit=4),
            "participant_signal_evidence": _join_unique(participant_signal.get("limite_regra", pd.Series(dtype=str)), limit=3),
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
        "cedente_signal_rows",
        "sacado_signal_rows",
        "participant_signal_rows",
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
        "participant_signal_keys",
        "participant_signal_evidence",
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
    snapshot["tem_sinal_cedente_sacado"] = snapshot["participant_signal_rows"].gt(0)
    snapshot["tem_sinal_sem_participante"] = snapshot["tem_sinal_cedente_sacado"] & ~snapshot["tem_cedente"]
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
        "participant_signal_rows",
        "participantes_count",
        "cedentes_top",
        "participant_signal_keys",
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
        "with_participant_signal": int(_num(frame.get("participant_signal_rows"), frame.index).gt(0).sum()),
        "with_participant_signal_without_cedente": int(
            (
                _num(frame.get("participant_signal_rows"), frame.index).gt(0)
                & _num(frame.get("cedente_rows"), frame.index).le(0)
            ).sum()
        ),
        "with_cedente_signal": int(_num(frame.get("cedente_signal_rows"), frame.index).gt(0).sum()),
        "with_sacado_signal": int(_num(frame.get("sacado_signal_rows"), frame.index).gt(0).sum()),
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
            "participant_signal_rows": float(_num(frame.get("participant_signal_rows"), frame.index).gt(0).mean()),
            "criteria_rows": float(_num(frame.get("criteria_rows"), frame.index).gt(0).mean()),
            "sub_min_pct_median": float(pd.to_numeric(frame.get("sub_min_pct_median"), errors="coerce").notna().mean())
            if "sub_min_pct_median" in frame
            else 0.0,
        },
    }


MARKET_SHARE_DIMENSIONS = [
    {"dimension_id": "admin", "label": "Administrador", "column": "admin_nome", "multi_value": False},
    {"dimension_id": "gestor", "label": "Gestor", "column": "gestor_nome", "multi_value": False},
    {"dimension_id": "custodiante", "label": "Custodiante", "column": "custodiante_nome", "multi_value": False},
    {"dimension_id": "segmento_ime", "label": "Segmento IME", "column": "segmento_principal", "multi_value": False},
    {"dimension_id": "segmento_estrategia", "label": "Segmento Estratégia", "column": "segmento_estrategia", "multi_value": False},
    {"dimension_id": "subsegmento_estrategia", "label": "Subsegmento Estratégia", "column": "subsegmento_estrategia", "multi_value": False},
    {"dimension_id": "snapshot_status", "label": "Status snapshot", "column": "snapshot_status", "multi_value": False},
    {"dimension_id": "fic_fidc", "label": "FIC-FIDC", "column": "is_fic_fidc", "multi_value": False},
    {"dimension_id": "emissao_2025_2026", "label": "Emissão 25-26", "column": "tem_emissao_2025_2026", "multi_value": False},
    {"dimension_id": "subordinacao_minima", "label": "Tem sub mín.", "column": "tem_sub_minima", "multi_value": False},
    {"dimension_id": "sinal_cedente_sacado", "label": "Sinal ced/sacado", "column": "tem_sinal_cedente_sacado", "multi_value": False},
    {"dimension_id": "documento_local", "label": "Documento local", "column": "tem_documento_local", "multi_value": False},
    {"dimension_id": "indexador", "label": "Indexador", "column": "indexadores", "multi_value": True},
    {"dimension_id": "tipo_cota", "label": "Tipo de cota", "column": "tipo_cotas", "multi_value": True},
    {"dimension_id": "classe_documento", "label": "Classe documento", "column": "document_classes", "multi_value": True},
    {"dimension_id": "criterio", "label": "Critério", "column": "criteria_keys", "multi_value": True},
]

MARKET_SHARE_METRICS = [
    {"metric_id": "pl", "label": "PL", "source": "pl_brl"},
    {"metric_id": "issuance", "label": "Emissões 24-26", "source": "issuance_2024_2026_brl"},
    {"metric_id": "funds", "label": "Fundos eq.", "source": "funds_equivalent"},
    {"metric_id": "documents", "label": "Documentos", "source": "document_rows"},
    {"metric_id": "cedentes", "label": "Cedentes", "source": "cedente_rows"},
    {"metric_id": "criteria", "label": "Critérios", "source": "criteria_rows"},
]

DIMENSION_CATALOG_SPECS = [
    {"dimension_id": "admin", "label": "Administrador", "column": "admin_nome", "source_layer": "snapshot", "multi_value": False},
    {"dimension_id": "gestor", "label": "Gestor", "column": "gestor_nome", "source_layer": "snapshot", "multi_value": False},
    {"dimension_id": "custodiante", "label": "Custodiante", "column": "custodiante_nome", "source_layer": "snapshot", "multi_value": False},
    {"dimension_id": "cedente_sacado", "label": "Cedente/sacado", "column": "razao_social", "source_layer": "cedente", "multi_value": False},
    {"dimension_id": "grupo_economico", "label": "Grupo econômico", "column": "grupo_economico", "source_layer": "cedente", "multi_value": False},
    {"dimension_id": "tipo_participante", "label": "Tipo participante", "column": "tipo_participante", "source_layer": "cedente", "multi_value": False},
    {"dimension_id": "setor_cedente", "label": "Setor cedente", "column": "setor", "source_layer": "cedente", "multi_value": False},
    {"dimension_id": "segmento_cedente", "label": "Segmento cedente", "column": "segmento", "source_layer": "cedente", "multi_value": False},
    {"dimension_id": "segmento", "label": "Segmento", "column": "segmento_principal", "source_layer": "snapshot", "multi_value": False},
    {
        "dimension_id": "segmento_estrategia",
        "label": "Segmento Estratégia",
        "column": "segmento_estrategia",
        "source_layer": "snapshot",
        "multi_value": False,
    },
    {
        "dimension_id": "subsegmento_estrategia",
        "label": "Subsegmento Estratégia",
        "column": "subsegmento_estrategia",
        "source_layer": "snapshot",
        "multi_value": False,
    },
    {"dimension_id": "condominio", "label": "Condomínio", "column": "condominio", "source_layer": "snapshot", "multi_value": False},
    {"dimension_id": "publico_alvo", "label": "Público-alvo", "column": "publico_alvo", "source_layer": "snapshot", "multi_value": False},
    {"dimension_id": "fic_fidc", "label": "FIC-FIDC", "column": "is_fic_fidc", "source_layer": "snapshot", "multi_value": False},
    {"dimension_id": "status_curadoria", "label": "Status curadoria", "column": "status_revisao", "source_layer": "cedente", "multi_value": False},
    {"dimension_id": "periodo_prioritario", "label": "Período prioritário", "column": "periodo_prioritario", "source_layer": "cedente", "multi_value": False},
    {"dimension_id": "snapshot_status", "label": "Status snapshot", "column": "snapshot_status", "source_layer": "snapshot", "multi_value": False},
    {
        "dimension_id": "camadas_evidencia",
        "label": "Camadas evidência",
        "column": "camadas_com_evidencia",
        "source_layer": "snapshot",
        "multi_value": False,
    },
    {
        "dimension_id": "emissao_2025_2026",
        "label": "Emissão 25-26",
        "column": "tem_emissao_2025_2026",
        "source_layer": "snapshot",
        "multi_value": False,
    },
    {
        "dimension_id": "ano_primeira_oferta",
        "label": "Ano 1ª oferta",
        "column": "first_offer_year",
        "source_layer": "snapshot",
        "multi_value": False,
    },
    {
        "dimension_id": "safra_emissao",
        "label": "Safra emissão",
        "column": "emission_cohort",
        "source_layer": "snapshot",
        "multi_value": False,
    },
    {
        "dimension_id": "faixa_sub_minima",
        "label": "Faixa sub mín.",
        "column": "sub_min_pct_median",
        "source_layer": "snapshot",
        "multi_value": False,
        "derived": "sub_min_bucket",
    },
    {"dimension_id": "tem_sub_minima", "label": "Tem sub mín.", "column": "tem_sub_minima", "source_layer": "snapshot", "multi_value": False},
    {
        "dimension_id": "sinal_cedente_sacado",
        "label": "Sinal ced/sacado",
        "column": "tem_sinal_cedente_sacado",
        "source_layer": "snapshot",
        "multi_value": False,
    },
    {"dimension_id": "documento_local", "label": "Documento local", "column": "tem_documento_local", "source_layer": "snapshot", "multi_value": False},
    {"dimension_id": "indexador", "label": "Indexador", "column": "indexadores", "source_layer": "snapshot", "multi_value": True},
    {"dimension_id": "tipo_cota", "label": "Tipo de cota", "column": "tipo_cotas", "source_layer": "snapshot", "multi_value": True},
    {"dimension_id": "classe_documento", "label": "Classe documento", "column": "document_classes", "source_layer": "snapshot", "multi_value": True},
    {"dimension_id": "criterio", "label": "Critério", "column": "criteria_keys", "source_layer": "snapshot", "multi_value": True},
    {"dimension_id": "chunk_docs", "label": "Chunk docs", "column": "document_chunk_ids", "source_layer": "snapshot", "multi_value": True},
]

_MARKET_SHARE_COLUMNS = [
    "dimension_id",
    "dimension_label",
    "dimension_column",
    "dimension_value",
    "metric_id",
    "metric_label",
    "metric_value",
    "share",
    "rank",
    "groups",
    "top5_share",
    "top10_share",
    "hhi",
    "pl_brl",
    "issuance_2024_2026_brl",
    "funds_equivalent",
    "funds_unique",
    "document_rows",
    "cedente_rows",
    "criteria_rows",
    "with_subordination_min_equiv",
    "with_issuance_2025_2026_equiv",
    "average_evidence_layers",
    "weighted_multivalue",
    "source_snapshot_rows",
    "prepared_snapshot_rows",
]


def _split_market_values(value: object) -> list[str]:
    values: list[str] = []
    for part in str(value or "").split("|"):
        text = part.strip()
        if text and text.lower() not in {"nan", "none", "n/d"}:
            values.append(text[:70])
    return values


def _market_dimension_values(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series("n/d", index=frame.index)
    if column == "is_fic_fidc":
        return _bool_series(frame[column], frame.index).map({True: "FIC-FIDC", False: "FIDC direto"})
    boolean_labels = {
        "tem_emissao_2025_2026": ("com emissão 2025-2026", "sem emissão 2025-2026"),
        "tem_sub_minima": ("com sub mínima", "sem sub mínima"),
        "tem_cedente": ("com cedente/sacado", "sem cedente/sacado"),
        "tem_sinal_cedente_sacado": ("com sinal cedente/sacado", "sem sinal cedente/sacado"),
        "tem_documento_local": ("com documento local", "sem documento local"),
    }
    if column in boolean_labels:
        values = _bool_series(frame[column], frame.index)
        yes, no = boolean_labels[column]
        return values.map({True: yes, False: no})
    if column == "camadas_com_evidencia":
        numbers = _num(frame[column], frame.index).round().astype(int)
        return numbers.map(lambda value: f"{value} camada" if value == 1 else f"{value} camadas")
    if column == "first_offer_year":
        years = _num(frame[column], frame.index).round().astype(int)
        return years.map(lambda value: "" if value <= 0 else str(value))
    values = _text(frame[column], frame.index).str.strip()
    values = values.where(values.ne(""), "n/d")
    return values.str.slice(0, 70)


def _prepare_market_share_frame(snapshot: pd.DataFrame, dimension_spec: dict[str, object]) -> pd.DataFrame:
    if snapshot is None or snapshot.empty:
        return pd.DataFrame()
    column = str(dimension_spec["column"])
    frame = snapshot.copy()
    frame["_metric_weight"] = 1.0
    if bool(dimension_spec.get("multi_value")):
        if column not in frame.columns:
            return frame.iloc[0:0].copy()
        values = frame[column].map(_split_market_values)
        counts = values.map(len)
        frame = frame[counts.gt(0)].copy()
        if frame.empty:
            return frame
        values = values.loc[frame.index]
        counts = counts.loc[frame.index]
        frame[column] = values
        frame["_metric_weight"] = 1.0 / counts
        frame = frame.explode(column).reset_index(drop=True)
    frame["_dimension_value"] = _market_dimension_values(frame, column)
    frame = frame[frame["_dimension_value"].ne("n/d")].copy()
    return frame


def _market_grouped_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    fund_id = "cnpj_fundo" if "cnpj_fundo" in frame.columns else "cnpj"
    if fund_id not in frame.columns:
        frame = frame.copy()
        fund_id = "_row_fund_id"
        frame[fund_id] = frame.index.astype(str)
    weighted = frame.copy()
    weighted["_pl_metric"] = _num(weighted.get("pl"), weighted.index) * weighted["_metric_weight"]
    weighted["_issuance_metric"] = _num(weighted.get("valid_volume_2024_2026_brl"), weighted.index) * weighted["_metric_weight"]
    weighted["_fund_metric"] = weighted["_metric_weight"]
    weighted["_document_metric"] = _num(weighted.get("document_rows"), weighted.index) * weighted["_metric_weight"]
    weighted["_cedente_metric"] = _num(weighted.get("cedente_rows"), weighted.index) * weighted["_metric_weight"]
    weighted["_criteria_metric"] = _num(weighted.get("criteria_rows"), weighted.index) * weighted["_metric_weight"]
    weighted["_sub_min_metric"] = _bool_series(weighted.get("tem_sub_minima"), weighted.index).astype(float) * weighted["_metric_weight"]
    weighted["_emission_2526_metric"] = (
        _bool_series(weighted.get("tem_emissao_2025_2026"), weighted.index).astype(float) * weighted["_metric_weight"]
    )
    weighted["_layers_metric"] = _num(weighted.get("camadas_com_evidencia"), weighted.index) * weighted["_metric_weight"]
    grouped = (
        weighted.groupby("_dimension_value", dropna=False)
        .agg(
            pl_brl=("_pl_metric", "sum"),
            issuance_2024_2026_brl=("_issuance_metric", "sum"),
            funds_equivalent=("_fund_metric", "sum"),
            funds_unique=(fund_id, "nunique"),
            document_rows=("_document_metric", "sum"),
            cedente_rows=("_cedente_metric", "sum"),
            criteria_rows=("_criteria_metric", "sum"),
            with_subordination_min_equiv=("_sub_min_metric", "sum"),
            with_issuance_2025_2026_equiv=("_emission_2526_metric", "sum"),
            evidence_layers_total=("_layers_metric", "sum"),
        )
        .reset_index()
        .rename(columns={"_dimension_value": "dimension_value"})
    )
    grouped["average_evidence_layers"] = grouped["evidence_layers_total"] / grouped["funds_equivalent"].replace(0, pd.NA)
    return grouped.drop(columns=["evidence_layers_total"], errors="ignore")


def build_industry_market_share(
    snapshot: pd.DataFrame,
    *,
    dimensions: list[dict[str, object]] | None = None,
    metrics: list[dict[str, object]] | None = None,
) -> pd.DataFrame:
    """Materialize concentration and market-share views from the unified FIDC snapshot."""

    dimension_specs = dimensions or MARKET_SHARE_DIMENSIONS
    metric_specs = metrics or MARKET_SHARE_METRICS
    if snapshot is None or snapshot.empty:
        return pd.DataFrame(columns=_MARKET_SHARE_COLUMNS)

    rows: list[dict[str, object]] = []
    source_snapshot_rows = int(len(snapshot))
    for dimension in dimension_specs:
        prepared = _prepare_market_share_frame(snapshot, dimension)
        grouped = _market_grouped_frame(prepared)
        if grouped.empty:
            continue
        groups = int(len(grouped))
        for metric in metric_specs:
            source = str(metric["source"])
            metric_values = pd.to_numeric(grouped.get(source), errors="coerce").fillna(0.0)
            total_metric = float(metric_values.sum())
            shares = metric_values / total_metric if total_metric else pd.Series(0.0, index=grouped.index)
            ranked = grouped.copy()
            ranked["metric_value"] = metric_values
            ranked["share"] = shares
            ranked = ranked.sort_values(["metric_value", "dimension_value"], ascending=[False, True]).reset_index(drop=True)
            ranked["rank"] = range(1, len(ranked) + 1)
            ranked_shares = ranked["share"].fillna(0.0)
            top5_share = float(ranked_shares.head(5).sum())
            top10_share = float(ranked_shares.head(10).sum())
            hhi = float(ranked_shares.pow(2).sum() * 10000)
            for record in ranked.to_dict("records"):
                rows.append(
                    {
                        "dimension_id": dimension["dimension_id"],
                        "dimension_label": dimension["label"],
                        "dimension_column": dimension["column"],
                        "dimension_value": record["dimension_value"],
                        "metric_id": metric["metric_id"],
                        "metric_label": metric["label"],
                        "metric_value": _json_float(record["metric_value"]) or 0.0,
                        "share": _json_float(record["share"]) or 0.0,
                        "rank": int(record["rank"]),
                        "groups": groups,
                        "top5_share": top5_share,
                        "top10_share": top10_share,
                        "hhi": hhi,
                        "pl_brl": _json_float(record.get("pl_brl")) or 0.0,
                        "issuance_2024_2026_brl": _json_float(record.get("issuance_2024_2026_brl")) or 0.0,
                        "funds_equivalent": _json_float(record.get("funds_equivalent")) or 0.0,
                        "funds_unique": int(pd.to_numeric(pd.Series([record.get("funds_unique")]), errors="coerce").fillna(0).iloc[0]),
                        "document_rows": _json_float(record.get("document_rows")) or 0.0,
                        "cedente_rows": _json_float(record.get("cedente_rows")) or 0.0,
                        "criteria_rows": _json_float(record.get("criteria_rows")) or 0.0,
                        "with_subordination_min_equiv": _json_float(record.get("with_subordination_min_equiv")) or 0.0,
                        "with_issuance_2025_2026_equiv": _json_float(record.get("with_issuance_2025_2026_equiv")) or 0.0,
                        "average_evidence_layers": _json_float(record.get("average_evidence_layers")),
                        "weighted_multivalue": bool(dimension.get("multi_value")),
                        "source_snapshot_rows": source_snapshot_rows,
                        "prepared_snapshot_rows": int(len(prepared)),
                    }
                )
    if not rows:
        return pd.DataFrame(columns=_MARKET_SHARE_COLUMNS)
    return pd.DataFrame(rows, columns=_MARKET_SHARE_COLUMNS)


def industry_market_share_quality_summary(market_share: pd.DataFrame) -> dict[str, object]:
    if market_share is None or market_share.empty:
        return {
            "rows": 0,
            "dimensions": 0,
            "metrics": 0,
            "weighted_dimensions": 0,
        }
    frame = market_share.copy()
    pl_admin = frame[(frame["dimension_id"] == "admin") & (frame["metric_id"] == "pl")]
    issuance_segment = frame[(frame["dimension_id"] == "segmento_estrategia") & (frame["metric_id"] == "issuance")]
    return {
        "rows": int(len(frame)),
        "dimensions": int(frame["dimension_id"].nunique()) if "dimension_id" in frame else 0,
        "metrics": int(frame["metric_id"].nunique()) if "metric_id" in frame else 0,
        "weighted_dimensions": int(
            frame.loc[frame.get("weighted_multivalue", pd.Series(False, index=frame.index)).astype(str).str.lower().isin({"true", "1"}), "dimension_id"].nunique()
        )
        if "dimension_id" in frame
        else 0,
        "top5_pl_share_admin": _json_float(pl_admin["top5_share"].iloc[0]) if not pl_admin.empty else None,
        "hhi_pl_admin": _json_float(pl_admin["hhi"].iloc[0]) if not pl_admin.empty else None,
        "top5_issuance_share_segmento_estrategia": _json_float(issuance_segment["top5_share"].iloc[0])
        if not issuance_segment.empty
        else None,
        "max_groups": int(pd.to_numeric(frame.get("groups"), errors="coerce").fillna(0).max()) if "groups" in frame else 0,
        "source_snapshot_rows": int(pd.to_numeric(frame.get("source_snapshot_rows"), errors="coerce").fillna(0).max())
        if "source_snapshot_rows" in frame
        else 0,
    }


def build_market_share_pipeline_manifest(
    *,
    industry_dir: Path,
    snapshot_path: Path,
    output_path: Path,
    manifest_path: Path,
    snapshot: pd.DataFrame,
    market_share: pd.DataFrame,
) -> dict[str, object]:
    quality = industry_market_share_quality_summary(market_share)
    return {
        "schema_version": "industry-market-share-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_market_share",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "macbook_air_m4_friendly": True,
            "notes": [
                "Este modulo transforma o snapshot unificado em rankings reutilizaveis de market share e concentracao.",
                "Dimensoes multivalor sao ponderadas por item para preservar o PL/volume total do snapshot filtrado.",
                "Novas combinacoes devem ser adicionadas pela lista declarativa de dimensoes e metricas, sem regra especifica de painel.",
            ],
        },
        "inputs": {
            "fund_snapshot": file_fingerprint(snapshot_path),
        },
        "outputs": {
            "market_share": file_fingerprint(output_path),
            "manifest": {"path": str(manifest_path)},
        },
        "stages": [
            {
                "id": "load_fund_snapshot",
                "label": "Carregar snapshot por FIDC",
                "status": "ok" if not snapshot.empty else "empty",
                "input": str(snapshot_path),
                "output": "memoria:industry_fund_snapshot",
                "rows": int(len(snapshot)),
                "rerun": "python scripts/build_fidc_industry_fund_snapshot.py",
            },
            {
                "id": "aggregate_market_share",
                "label": "Agregacoes de market share",
                "status": "ok" if not market_share.empty else "empty",
                "input": "memoria:industry_fund_snapshot",
                "output": str(output_path),
                "rows": int(len(market_share)),
                "dimensions": quality.get("dimensions", 0),
                "metrics": quality.get("metrics", 0),
                "rerun": "python scripts/build_fidc_industry_market_share.py",
            },
        ],
        "quality": quality,
    }


_DIMENSION_CATALOG_COLUMNS = [
    "cnpj_fundo",
    "nome_exibicao",
    "dimension_id",
    "dimension_label",
    "dimension_column",
    "dimension_value",
    "source_layer",
    "source_field",
    "source_value",
    "value_weight",
    "is_multivalue",
    "is_curated",
    "participant_type",
    "participant_cnpj",
    "source_document",
    "source_page",
    "source_date",
    "source_method",
    "confidence_score",
    "review_status",
    "priority_2025_2026",
]

_DIMENSION_MONTHLY_COLUMNS = [
    "competencia",
    "dimension_id",
    "dimension_label",
    "dimension_value",
    "pl_brl",
    "captacao_liquida_brl",
    "carteira_dc_brl",
    "dc_inadimplentes_ajustado_brl",
    "inad_pct_ajustada",
    "cotistas_equiv",
    "funds_equiv",
    "funds_unique",
    "vehicles_unique",
    "catalog_links",
    "source_document_links",
    "curated_links",
    "weighted_links",
]

_DIMENSION_PROFILE_COLUMNS = [
    "competencia",
    "source_dimension_id",
    "source_dimension_label",
    "source_dimension_value",
    "target_dimension_id",
    "target_dimension_label",
    "target_dimension_value",
    "pl_brl",
    "issuance_2024_2026_brl",
    "funds_equiv",
    "funds_unique",
    "vehicles_unique",
    "document_rows_equiv",
    "cedente_rows_equiv",
    "criteria_rows_equiv",
    "evidence_layers_equiv",
    "with_subordination_min_equiv",
    "catalog_links",
    "source_document_links",
    "curated_links",
    "weighted_links",
    "avg_confidence_score",
]


def _catalog_clean_value(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if text.lower() in {"", "nan", "none", "n/d"}:
        return ""
    return text[:120]


def _catalog_sub_min_bucket(value: object) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return "sem sub mínima"
    if number < 10:
        return "<10%"
    if number < 15:
        return "10%-15%"
    if number < 25:
        return "15%-25%"
    return ">=25%"


def _catalog_document_column(dimension_id: str) -> str:
    if dimension_id in {"indexador", "tipo_cota"}:
        return "pricing_documentos"
    if dimension_id in {"criterio", "tem_sub_minima", "faixa_sub_minima", "sinal_cedente_sacado"}:
        return "criteria_documentos"
    if dimension_id in {"classe_documento", "chunk_docs", "documento_local"}:
        return "document_classes"
    return ""


def _catalog_confidence_column(dimension_id: str) -> str:
    if dimension_id in {"indexador", "tipo_cota"}:
        return "pricing_score_mediana"
    if dimension_id in {"criterio", "tem_sub_minima", "faixa_sub_minima", "sinal_cedente_sacado"}:
        return "criteria_score_mediana"
    if dimension_id in {"cedente_sacado", "grupo_economico", "tipo_participante", "setor_cedente", "segmento_cedente"}:
        return "cedente_score_mediana"
    return ""


def _catalog_snapshot_values(row: pd.Series, spec: dict[str, object]) -> list[tuple[str, object]]:
    column = str(spec["column"])
    if spec.get("derived") == "sub_min_bucket":
        value = _catalog_sub_min_bucket(row.get(column))
        return [(value, row.get(column, ""))]
    if column not in row.index:
        return []
    if bool(spec.get("multi_value")):
        parts = _split_market_values(row.get(column))
        return [(part, row.get(column, "")) for part in parts]
    frame = pd.DataFrame([row])
    label = _market_dimension_values(frame, column).iloc[0]
    value = _catalog_clean_value(label)
    if not value:
        return []
    return [(value, row.get(column, ""))]


def _catalog_row_base(row: pd.Series, spec: dict[str, object]) -> dict[str, object]:
    dimension_id = str(spec["dimension_id"])
    document_col = _catalog_document_column(dimension_id)
    confidence_col = _catalog_confidence_column(dimension_id)
    return {
        "cnpj_fundo": normalize_cnpj(row.get("cnpj_fundo")),
        "nome_exibicao": row.get("nome_exibicao") or row.get("fundo") or row.get("denominacao") or "",
        "dimension_id": dimension_id,
        "dimension_label": spec["label"],
        "dimension_column": spec["column"],
        "source_layer": spec["source_layer"],
        "source_field": spec["column"],
        "is_multivalue": bool(spec.get("multi_value")),
        "is_curated": spec.get("source_layer") in {"cedente", "criteria"},
        "participant_type": row.get("participant_type", ""),
        "participant_cnpj": normalize_cnpj(row.get("cnpj_participante")) if row.get("cnpj_participante", "") else "",
        "source_document": row.get(document_col, "") if document_col else row.get("documento_origem", ""),
        "source_page": row.get("pagina", ""),
        "source_date": row.get("document_date", "") or row.get("document_latest_date", "") or row.get("latest_regulamento_date", ""),
        "source_method": row.get("metodo_extracao", "") or "snapshot_consolidado",
        "confidence_score": _json_float(row.get(confidence_col, row.get("score_confianca_final", row.get("score_confianca", "")))),
        "review_status": row.get("status_revisao", ""),
        "priority_2025_2026": row.get("periodo_prioritario", "") == "2025-2026 YTD"
        or str(row.get("priority_2025_2026", "")).lower() in {"true", "1", "sim"},
    }


def _build_snapshot_dimension_rows(snapshot: pd.DataFrame, specs: list[dict[str, object]]) -> list[dict[str, object]]:
    if snapshot is None or snapshot.empty:
        return []
    frame = snapshot.copy()
    if "cnpj_fundo" not in frame.columns and "cnpj" in frame.columns:
        frame["cnpj_fundo"] = frame["cnpj"]
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    rows: list[dict[str, object]] = []
    snapshot_specs = [spec for spec in specs if spec.get("source_layer") == "snapshot"]
    for _, row in frame.iterrows():
        cnpj = normalize_cnpj(row.get("cnpj_fundo"))
        if not cnpj:
            continue
        for spec in snapshot_specs:
            values = _catalog_snapshot_values(row, spec)
            if not values:
                continue
            weight = 1.0 / len(values)
            base = _catalog_row_base(row, spec)
            for value, source_value in values:
                clean = _catalog_clean_value(value)
                if not clean:
                    continue
                item = {
                    **base,
                    "dimension_value": clean,
                    "source_value": _catalog_clean_value(source_value) or clean,
                    "value_weight": weight,
                }
                rows.append(item)
    return rows


def _build_cedente_dimension_rows(cedentes: pd.DataFrame, specs: list[dict[str, object]]) -> list[dict[str, object]]:
    if cedentes is None or cedentes.empty:
        return []
    frame = cedentes.copy()
    if "cnpj_fundo" not in frame.columns:
        return []
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    if "ativo_curadoria" in frame.columns:
        frame = frame[frame["ativo_curadoria"].astype(str).str.lower().isin({"true", "1", "sim", "s", "yes"})].copy()
    cedente_specs = [spec for spec in specs if spec.get("source_layer") == "cedente"]
    rows: list[dict[str, object]] = []
    for spec in cedente_specs:
        column = str(spec["column"])
        if column not in frame.columns:
            continue
        part = frame.copy()
        part["dimension_value"] = part[column].map(_catalog_clean_value)
        part = part[part["dimension_value"].ne("")].copy()
        if part.empty:
            continue
        part["_confidence_sort"] = _num(part.get("score_confianca_final"), part.index)
        part = part.sort_values("_confidence_sort", ascending=False)
        part = part.drop_duplicates(["cnpj_fundo", "dimension_value"], keep="first")
        counts = part.groupby("cnpj_fundo")["dimension_value"].transform("nunique").clip(lower=1)
        part["_catalog_weight"] = 1.0 / counts
        for _, row in part.iterrows():
            base = _catalog_row_base(row, spec)
            rows.append(
                {
                    **base,
                    "dimension_value": row["dimension_value"],
                    "source_value": row["dimension_value"],
                    "value_weight": _json_float(row["_catalog_weight"]) or 0.0,
                }
            )
    return rows


def build_industry_dimension_catalog(
    *,
    snapshot: pd.DataFrame,
    cedentes: pd.DataFrame | None = None,
    specs: list[dict[str, object]] | None = None,
) -> pd.DataFrame:
    """Build a reusable long catalog of FIDC dimensions with source metadata."""

    catalog_specs = specs or DIMENSION_CATALOG_SPECS
    rows = _build_snapshot_dimension_rows(snapshot, catalog_specs)
    rows.extend(_build_cedente_dimension_rows(cedentes if cedentes is not None else pd.DataFrame(), catalog_specs))
    if not rows:
        return pd.DataFrame(columns=_DIMENSION_CATALOG_COLUMNS)
    frame = pd.DataFrame(rows)
    for col in _DIMENSION_CATALOG_COLUMNS:
        if col not in frame.columns:
            frame[col] = ""
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame["value_weight"] = pd.to_numeric(frame["value_weight"], errors="coerce").fillna(0.0)
    frame["confidence_score"] = pd.to_numeric(frame["confidence_score"], errors="coerce")
    frame = frame[frame["cnpj_fundo"].astype(str).str.len().eq(14) & frame["dimension_value"].astype(str).str.strip().ne("")]
    frame = frame.drop_duplicates(["cnpj_fundo", "dimension_id", "dimension_value", "source_layer"], keep="first")
    return frame[_DIMENSION_CATALOG_COLUMNS].sort_values(["dimension_id", "dimension_value", "cnpj_fundo"])


def industry_dimension_catalog_quality_summary(catalog: pd.DataFrame) -> dict[str, object]:
    if catalog is None or catalog.empty:
        return {
            "rows": 0,
            "funds": 0,
            "dimensions": 0,
            "source_layer_counts": {},
        }
    frame = catalog.copy()
    return {
        "rows": int(len(frame)),
        "funds": int(frame["cnpj_fundo"].nunique()) if "cnpj_fundo" in frame else 0,
        "dimensions": int(frame["dimension_id"].nunique()) if "dimension_id" in frame else 0,
        "source_layer_counts": {
            str(k): int(v)
            for k, v in frame.get("source_layer", pd.Series("", index=frame.index)).fillna("").astype(str).value_counts().to_dict().items()
        },
        "curated_rows": int(frame.get("is_curated", pd.Series(False, index=frame.index)).astype(str).str.lower().isin({"true", "1"}).sum()),
        "weighted_dimensions": int(
            frame.loc[pd.to_numeric(frame.get("value_weight"), errors="coerce").fillna(1.0).lt(1.0), "dimension_id"].nunique()
        )
        if "dimension_id" in frame
        else 0,
        "with_source_document": int(frame.get("source_document", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip().ne("").sum()),
        "with_confidence": int(pd.to_numeric(frame.get("confidence_score"), errors="coerce").notna().sum())
        if "confidence_score" in frame
        else 0,
    }


def build_dimension_traceability_matrix(catalog: pd.DataFrame) -> pd.DataFrame:
    """Summarize traceability quality by dimension and source layer."""

    required = {"dimension_id", "dimension_label", "dimension_value", "cnpj_fundo"}
    if catalog is None or catalog.empty or not required.issubset(catalog.columns):
        return pd.DataFrame()
    frame = catalog.copy()
    for col in [
        "source_layer",
        "source_document",
        "source_page",
        "source_date",
        "source_method",
        "confidence_score",
        "review_status",
        "is_curated",
        "is_multivalue",
        "priority_2025_2026",
    ]:
        if col not in frame.columns:
            frame[col] = ""
    frame["_cnpj_norm"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame["_source_layer"] = frame["source_layer"].fillna("").astype(str).replace("", "sem fonte")
    frame["_has_source_document"] = _nonempty_series(frame["source_document"])
    frame["_has_source_page"] = _nonempty_series(frame["source_page"])
    frame["_has_source_date"] = _nonempty_series(frame["source_date"])
    frame["_has_source_method"] = _nonempty_series(frame["source_method"])
    frame["_has_confidence"] = pd.to_numeric(frame["confidence_score"], errors="coerce").notna()
    frame["_has_review_status"] = _nonempty_series(frame["review_status"])
    frame["_is_curated"] = _boolish_series(frame["is_curated"])
    frame["_is_multivalue"] = _boolish_series(frame["is_multivalue"])
    frame["_priority_2025_2026"] = _boolish_series(frame["priority_2025_2026"])
    source_layer = frame["source_layer"].fillna("").astype(str)
    frame["_doc_expected"] = frame["_is_curated"] | source_layer.isin({"cedente", "criteria"}) | frame["_has_source_document"]
    frame["_review_expected"] = frame["_is_curated"] | source_layer.isin({"cedente", "criteria"})
    confidence = pd.to_numeric(frame["confidence_score"], errors="coerce")
    frame["_confidence_score_num"] = confidence

    grouped = (
        frame.groupby(["dimension_id", "dimension_label", "_source_layer"], dropna=False)
        .agg(
            rows=("dimension_value", "size"),
            funds=("_cnpj_norm", "nunique"),
            values=("dimension_value", "nunique"),
            curated_rows=("_is_curated", "sum"),
            multivalue_rows=("_is_multivalue", "sum"),
            priority_2025_2026_rows=("_priority_2025_2026", "sum"),
            document_expected_rows=("_doc_expected", "sum"),
            review_expected_rows=("_review_expected", "sum"),
            with_source_document=("_has_source_document", "sum"),
            with_source_page=("_has_source_page", "sum"),
            with_source_date=("_has_source_date", "sum"),
            with_source_method=("_has_source_method", "sum"),
            with_confidence=("_has_confidence", "sum"),
            with_review_status=("_has_review_status", "sum"),
            confidence_median=("_confidence_score_num", _median_numeric),
        )
        .reset_index()
        .rename(columns={"_source_layer": "source_layer"})
    )
    rows = pd.to_numeric(grouped["rows"], errors="coerce").astype(float).where(lambda values: values.ne(0))
    doc_expected = pd.to_numeric(grouped["document_expected_rows"], errors="coerce").astype(float).where(lambda values: values.ne(0))
    review_expected = pd.to_numeric(grouped["review_expected_rows"], errors="coerce").astype(float).where(lambda values: values.ne(0))
    grouped["source_document_ratio"] = grouped["with_source_document"] / doc_expected
    grouped["source_page_ratio"] = grouped["with_source_page"] / doc_expected
    grouped["source_date_ratio"] = grouped["with_source_date"] / rows
    grouped["source_method_ratio"] = grouped["with_source_method"] / rows
    grouped["confidence_ratio"] = grouped["with_confidence"] / rows
    grouped["review_status_ratio"] = grouped["with_review_status"] / review_expected
    grouped["quality_score"] = (
        grouped["source_method_ratio"].fillna(0.0) * 0.20
        + grouped["confidence_ratio"].fillna(0.0) * 0.20
        + grouped["source_document_ratio"].fillna(1.0) * 0.22
        + grouped["source_page_ratio"].fillna(1.0) * 0.18
        + grouped["source_date_ratio"].fillna(0.0) * 0.10
        + grouped["review_status_ratio"].fillna(1.0) * 0.10
    )
    grouped["missing_document_rows"] = (grouped["document_expected_rows"] - grouped["with_source_document"]).clip(lower=0)
    grouped["missing_page_rows"] = (grouped["document_expected_rows"] - grouped["with_source_page"]).clip(lower=0)
    grouped["missing_method_rows"] = (grouped["rows"] - grouped["with_source_method"]).clip(lower=0)
    grouped["missing_score_rows"] = (grouped["rows"] - grouped["with_confidence"]).clip(lower=0)
    grouped["missing_review_rows"] = (grouped["review_expected_rows"] - grouped["with_review_status"]).clip(lower=0)
    grouped["traceability_gap_rows"] = grouped[
        [
            "missing_document_rows",
            "missing_page_rows",
            "missing_method_rows",
            "missing_score_rows",
            "missing_review_rows",
        ]
    ].sum(axis=1)
    grouped["traceability_priority_score"] = (
        grouped["traceability_gap_rows"]
        + grouped["priority_2025_2026_rows"] * 0.5
        + grouped["curated_rows"] * 0.25
        + grouped["funds"] * 0.05
    )
    ordered = [
        "dimension_id",
        "dimension_label",
        "source_layer",
        "rows",
        "funds",
        "values",
        "curated_rows",
        "multivalue_rows",
        "priority_2025_2026_rows",
        "document_expected_rows",
        "review_expected_rows",
        "with_source_document",
        "with_source_page",
        "with_source_date",
        "with_source_method",
        "with_confidence",
        "with_review_status",
        "source_document_ratio",
        "source_page_ratio",
        "source_date_ratio",
        "source_method_ratio",
        "confidence_ratio",
        "review_status_ratio",
        "quality_score",
        "confidence_median",
        "missing_document_rows",
        "missing_page_rows",
        "missing_method_rows",
        "missing_score_rows",
        "missing_review_rows",
        "traceability_gap_rows",
        "traceability_priority_score",
    ]
    return grouped[ordered].sort_values(
        ["quality_score", "traceability_priority_score", "rows"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def dimension_traceability_quality_summary(matrix: pd.DataFrame) -> dict[str, object]:
    if matrix is None or matrix.empty:
        return {
            "rows": 0,
            "dimensions": 0,
            "source_layers": 0,
            "low_quality_rows": 0,
            "missing_page_rows": 0,
            "missing_document_rows": 0,
            "missing_method_rows": 0,
            "missing_score_rows": 0,
            "median_quality_score": None,
            "worst_quality_score": None,
        }
    quality = pd.to_numeric(matrix.get("quality_score"), errors="coerce")
    return {
        "rows": int(len(matrix)),
        "dimensions": int(matrix["dimension_id"].nunique()) if "dimension_id" in matrix else 0,
        "source_layers": int(matrix["source_layer"].nunique()) if "source_layer" in matrix else 0,
        "low_quality_rows": int(quality.lt(0.7).sum()) if len(quality) else 0,
        "missing_page_rows": int(pd.to_numeric(matrix.get("missing_page_rows"), errors="coerce").fillna(0).sum()),
        "missing_document_rows": int(pd.to_numeric(matrix.get("missing_document_rows"), errors="coerce").fillna(0).sum()),
        "missing_method_rows": int(pd.to_numeric(matrix.get("missing_method_rows"), errors="coerce").fillna(0).sum()),
        "missing_score_rows": int(pd.to_numeric(matrix.get("missing_score_rows"), errors="coerce").fillna(0).sum()),
        "median_quality_score": _json_float(quality.median()) if quality.notna().any() else None,
        "worst_quality_score": _json_float(quality.min()) if quality.notna().any() else None,
    }


def build_dimension_traceability_pipeline_manifest(
    *,
    industry_dir: Path,
    catalog_path: Path,
    output_path: Path,
    manifest_path: Path,
    catalog: pd.DataFrame,
    matrix: pd.DataFrame,
) -> dict[str, object]:
    quality = dimension_traceability_quality_summary(matrix)
    return {
        "schema_version": "industry-dimension-traceability-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_dimension_traceability",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "manual_review_in_app": True,
            "notes": [
                "Resume a cobertura de fonte, documento, pagina, metodo, score e status de revisao por dimensao e camada.",
                "Serve para priorizar lacunas de rastreabilidade antes de usar valores em escrutinio publico.",
            ],
        },
        "inputs": {
            "dimension_catalog": file_fingerprint(catalog_path),
        },
        "outputs": {
            "traceability_matrix": file_fingerprint(output_path),
            "manifest": {"path": str(manifest_path)},
        },
        "stages": [
            {
                "id": "load_dimension_catalog",
                "label": "Carregar catálogo de dimensões",
                "status": "ok" if catalog is not None and not catalog.empty else "empty",
                "rows": int(len(catalog)) if catalog is not None else 0,
                "rerun": "python scripts/build_fidc_industry_dimensions.py",
            },
            {
                "id": "aggregate_traceability_matrix",
                "label": "Agregar qualidade por dimensão e camada",
                "status": "ok" if matrix is not None and not matrix.empty else "empty",
                "rows": int(len(matrix)) if matrix is not None else 0,
                "rerun": "python scripts/build_fidc_industry_traceability.py",
            },
        ],
        "quality": quality,
    }


def build_dimension_catalog_pipeline_manifest(
    *,
    industry_dir: Path,
    snapshot_path: Path,
    cedentes_path: Path,
    output_path: Path,
    manifest_path: Path,
    snapshot: pd.DataFrame,
    cedentes: pd.DataFrame,
    catalog: pd.DataFrame,
) -> dict[str, object]:
    quality = industry_dimension_catalog_quality_summary(catalog)
    return {
        "schema_version": "industry-dimension-catalog-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_dimension_catalog",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "macbook_air_m4_friendly": True,
            "notes": [
                "Este modulo materializa CNPJ x dimensao x valor, com pesos e metadados de fonte.",
                "Heatmaps e Deep Dives podem cruzar qualquer dimensao sem regras especificas por painel.",
                "Dimensoes de cedentes preservam documento, pagina, score e status de revisao quando disponiveis.",
            ],
        },
        "inputs": {
            "fund_snapshot": file_fingerprint(snapshot_path),
            "cedentes_structured": file_fingerprint(cedentes_path),
        },
        "outputs": {
            "dimension_catalog": file_fingerprint(output_path),
            "manifest": {"path": str(manifest_path)},
        },
        "stages": [
            {
                "id": "load_snapshot_and_cedentes",
                "label": "Carregar camadas estruturadas",
                "status": "ok" if not snapshot.empty else "empty",
                "input": f"{snapshot_path}+{cedentes_path}",
                "output": "memoria:snapshot+cedentes",
                "rows": int(len(snapshot) + len(cedentes)),
                "rerun": "python scripts/build_fidc_industry_fund_snapshot.py && python scripts/build_fidc_industry_cedentes.py",
            },
            {
                "id": "explode_dimension_catalog",
                "label": "Explodir dimensoes reutilizaveis",
                "status": "ok" if not catalog.empty else "empty",
                "input": "memoria:snapshot+cedentes",
                "output": str(output_path),
                "rows": int(len(catalog)),
                "dimensions": quality.get("dimensions", 0),
                "rerun": "python scripts/build_fidc_industry_dimensions.py",
            },
        ],
        "quality": quality,
    }


def build_industry_dimension_monthly(
    *,
    vehicle_monthly: pd.DataFrame,
    dimension_catalog: pd.DataFrame,
    max_competencia: str | None = None,
) -> pd.DataFrame:
    """Aggregate monthly metrics by reusable Industry dimension/value."""

    if vehicle_monthly is None or vehicle_monthly.empty or dimension_catalog is None or dimension_catalog.empty:
        return pd.DataFrame(columns=_DIMENSION_MONTHLY_COLUMNS)
    vehicle = vehicle_monthly.copy()
    id_col = "cnpj_fundo" if "cnpj_fundo" in vehicle.columns else "cnpj"
    if id_col not in vehicle.columns or "competencia" not in vehicle.columns:
        return pd.DataFrame(columns=_DIMENSION_MONTHLY_COLUMNS)
    vehicle["cnpj_fundo_norm"] = vehicle[id_col].map(normalize_cnpj)
    vehicle = vehicle[vehicle["cnpj_fundo_norm"].astype(str).str.len().eq(14)].copy()
    if vehicle.empty:
        return pd.DataFrame(columns=_DIMENSION_MONTHLY_COLUMNS)
    if "cnpj" not in vehicle.columns:
        vehicle["cnpj"] = vehicle["cnpj_fundo_norm"]
    max_key = _competencia_key(max_competencia) if max_competencia else ""
    if max_key:
        vehicle["_competencia_key"] = vehicle["competencia"].map(_competencia_key)
        vehicle = vehicle[vehicle["_competencia_key"].le(max_key)].copy()
        vehicle = vehicle.drop(columns=["_competencia_key"])
        if vehicle.empty:
            return pd.DataFrame(columns=_DIMENSION_MONTHLY_COLUMNS)
    metric_cols = [
        "competencia",
        "cnpj",
        "cnpj_fundo_norm",
        "pl",
        "captacao_liquida",
        "carteira_dc",
        "dc_inadimplentes_ajustado",
        "cotistas",
    ]
    for col in metric_cols:
        if col not in vehicle.columns:
            vehicle[col] = 0.0 if col not in {"competencia", "cnpj", "cnpj_fundo_norm"} else ""
    vehicle = vehicle[metric_cols].copy()
    for col in ["pl", "captacao_liquida", "carteira_dc", "dc_inadimplentes_ajustado", "cotistas"]:
        vehicle[col] = _num(vehicle[col], vehicle.index)

    catalog = dimension_catalog.copy()
    if "cnpj_fundo" not in catalog.columns:
        return pd.DataFrame(columns=_DIMENSION_MONTHLY_COLUMNS)
    catalog["cnpj_fundo_norm"] = catalog["cnpj_fundo"].map(normalize_cnpj)
    catalog = catalog[catalog["cnpj_fundo_norm"].astype(str).str.len().eq(14)].copy()
    keep = [
        "cnpj_fundo_norm",
        "dimension_id",
        "dimension_label",
        "dimension_value",
        "value_weight",
        "source_document",
        "is_curated",
        "is_multivalue",
    ]
    for col in keep:
        if col not in catalog.columns:
            catalog[col] = ""
    catalog = catalog[keep].copy()
    catalog["dimension_value"] = catalog["dimension_value"].fillna("").astype(str).str.strip()
    catalog = catalog[catalog["dimension_value"].ne("")].copy()
    catalog["value_weight"] = pd.to_numeric(catalog["value_weight"], errors="coerce").fillna(1.0)
    catalog["source_document_filled"] = catalog["source_document"].fillna("").astype(str).str.strip().ne("")
    catalog["is_curated_bool"] = catalog["is_curated"].astype(str).str.lower().isin({"true", "1", "sim", "s", "yes"})
    catalog["is_multivalue_bool"] = catalog["is_multivalue"].astype(str).str.lower().isin({"true", "1", "sim", "s", "yes"})
    catalog = catalog.drop_duplicates(["cnpj_fundo_norm", "dimension_id", "dimension_value"], keep="first")
    if catalog.empty:
        return pd.DataFrame(columns=_DIMENSION_MONTHLY_COLUMNS)

    joined = vehicle.merge(catalog, on="cnpj_fundo_norm", how="inner")
    if joined.empty:
        return pd.DataFrame(columns=_DIMENSION_MONTHLY_COLUMNS)
    weight = pd.to_numeric(joined["value_weight"], errors="coerce").fillna(1.0)
    joined["_pl_brl"] = joined["pl"] * weight
    joined["_captacao_liquida_brl"] = joined["captacao_liquida"] * weight
    joined["_carteira_dc_brl"] = joined["carteira_dc"] * weight
    joined["_dc_inadimplentes_ajustado_brl"] = joined["dc_inadimplentes_ajustado"] * weight
    joined["_cotistas_equiv"] = joined["cotistas"] * weight
    joined["_funds_equiv"] = weight
    joined["_source_document_link"] = joined["source_document_filled"].astype(int)
    joined["_curated_link"] = joined["is_curated_bool"].astype(int)
    joined["_weighted_link"] = weight.lt(1.0).astype(int)
    keys = ["competencia", "dimension_id", "dimension_label", "dimension_value"]
    grouped = (
        joined.groupby(keys, dropna=False)
        .agg(
            pl_brl=("_pl_brl", "sum"),
            captacao_liquida_brl=("_captacao_liquida_brl", "sum"),
            carteira_dc_brl=("_carteira_dc_brl", "sum"),
            dc_inadimplentes_ajustado_brl=("_dc_inadimplentes_ajustado_brl", "sum"),
            cotistas_equiv=("_cotistas_equiv", "sum"),
            funds_equiv=("_funds_equiv", "sum"),
            funds_unique=("cnpj_fundo_norm", "nunique"),
            vehicles_unique=("cnpj", "nunique"),
            catalog_links=("cnpj_fundo_norm", "size"),
            source_document_links=("_source_document_link", "sum"),
            curated_links=("_curated_link", "sum"),
            weighted_links=("_weighted_link", "sum"),
        )
        .reset_index()
    )
    grouped["inad_pct_ajustada"] = grouped["dc_inadimplentes_ajustado_brl"] / grouped["carteira_dc_brl"].replace(0, pd.NA)
    grouped["inad_pct_ajustada"] = pd.to_numeric(grouped["inad_pct_ajustada"], errors="coerce").fillna(0.0)
    for col in _DIMENSION_MONTHLY_COLUMNS:
        if col not in grouped.columns:
            grouped[col] = 0 if col not in {"competencia", "dimension_id", "dimension_label", "dimension_value"} else ""
    return grouped[_DIMENSION_MONTHLY_COLUMNS].sort_values(["competencia", "dimension_id", "pl_brl"], ascending=[True, True, False])


def industry_dimension_monthly_quality_summary(monthly: pd.DataFrame) -> dict[str, object]:
    if monthly is None or monthly.empty:
        return {
            "rows": 0,
            "months": 0,
            "dimensions": 0,
            "latest_competencia": "",
            "latest_rows": 0,
        }
    frame = monthly.copy()
    latest = str(frame["competencia"].dropna().astype(str).max()) if "competencia" in frame else ""
    latest_frame = frame[frame["competencia"].astype(str).eq(latest)].copy() if latest else pd.DataFrame()
    return {
        "rows": int(len(frame)),
        "months": int(frame["competencia"].nunique()) if "competencia" in frame else 0,
        "dimensions": int(frame["dimension_id"].nunique()) if "dimension_id" in frame else 0,
        "dimension_values": int(frame[["dimension_id", "dimension_value"]].drop_duplicates().shape[0])
        if {"dimension_id", "dimension_value"}.issubset(frame.columns)
        else 0,
        "latest_competencia": latest,
        "latest_rows": int(len(latest_frame)),
        "latest_pl_brl": float(pd.to_numeric(latest_frame.get("pl_brl"), errors="coerce").fillna(0.0).sum())
        if not latest_frame.empty
        else 0.0,
        "with_source_document_links": int(pd.to_numeric(frame.get("source_document_links"), errors="coerce").fillna(0).gt(0).sum())
        if "source_document_links" in frame
        else 0,
        "curated_rows": int(pd.to_numeric(frame.get("curated_links"), errors="coerce").fillna(0).gt(0).sum())
        if "curated_links" in frame
        else 0,
    }


def build_industry_dimension_value_atlas(
    monthly: pd.DataFrame,
    *,
    dimension_catalog: pd.DataFrame | None = None,
    latest_competencia: str | None = None,
    trailing_months: int = 12,
) -> pd.DataFrame:
    """Build a reusable latest-value atlas for Deep Dives from monthly dimension series."""

    required = {"competencia", "dimension_id", "dimension_label", "dimension_value"}
    if monthly is None or monthly.empty or not required.issubset(monthly.columns):
        return pd.DataFrame(columns=DIMENSION_VALUE_ATLAS_COLUMNS)
    frame = monthly.copy()
    frame["competencia"] = frame["competencia"].fillna("").astype(str)
    frame = frame[frame["competencia"].str.strip().ne("")].copy()
    if frame.empty:
        return pd.DataFrame(columns=DIMENSION_VALUE_ATLAS_COLUMNS)
    for col in [
        "pl_brl",
        "captacao_liquida_brl",
        "carteira_dc_brl",
        "dc_inadimplentes_ajustado_brl",
        "funds_unique",
        "vehicles_unique",
        "funds_equiv",
        "cotistas_equiv",
        "catalog_links",
        "source_document_links",
        "curated_links",
        "weighted_links",
    ]:
        if col not in frame.columns:
            frame[col] = 0.0
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)

    frame["_competencia_key"] = frame["competencia"].map(_competencia_key)
    valid_keys = sorted(value for value in frame["_competencia_key"].dropna().astype(str).unique() if value)
    if not valid_keys:
        return pd.DataFrame(columns=DIMENSION_VALUE_ATLAS_COLUMNS)
    latest_key = _competencia_key(latest_competencia) if latest_competencia else ""
    if not latest_key or latest_key not in valid_keys:
        latest_key = valid_keys[-1]
    latest_pos = valid_keys.index(latest_key)
    window_keys = valid_keys[max(0, latest_pos - trailing_months + 1) : latest_pos + 1]
    previous_key = valid_keys[latest_pos - 12] if latest_pos >= 12 else ""

    latest_frame = frame[frame["_competencia_key"].eq(latest_key)].copy()
    window_frame = frame[frame["_competencia_key"].isin(window_keys)].copy()
    if latest_frame.empty or window_frame.empty:
        return pd.DataFrame(columns=DIMENSION_VALUE_ATLAS_COLUMNS)

    keys = ["dimension_id", "dimension_label", "dimension_value"]
    current = (
        latest_frame.groupby(keys, dropna=False)
        .agg(
            pl_atual_brl=("pl_brl", "sum"),
            carteira_atual_brl=("carteira_dc_brl", "sum"),
            inad_atual_brl=("dc_inadimplentes_ajustado_brl", "sum"),
            fundos_atuais=("funds_unique", "max"),
            veiculos_atuais=("vehicles_unique", "max"),
            funds_equiv_atual=("funds_equiv", "sum"),
            cotistas_equiv_atual=("cotistas_equiv", "sum"),
            links_catalogo=("catalog_links", "sum"),
            links_com_fonte=("source_document_links", "sum"),
            links_curados=("curated_links", "sum"),
            links_ponderados=("weighted_links", "sum"),
        )
        .reset_index()
    )
    flow = (
        window_frame.groupby(keys, dropna=False)
        .agg(
            captacao_12m_brl=("captacao_liquida_brl", "sum"),
            months_available=("_competencia_key", "nunique"),
            first_competencia=("_competencia_key", "min"),
        )
        .reset_index()
    )
    out = current.merge(flow, on=keys, how="left")
    evidence = _dimension_value_atlas_evidence_summary(dimension_catalog)
    if not evidence.empty:
        out = out.merge(evidence, on=keys, how="left")
    if previous_key:
        previous = (
            frame[frame["_competencia_key"].eq(previous_key)]
            .groupby(keys, dropna=False)["pl_brl"]
            .sum()
            .reset_index(name="pl_12m_antes_brl")
        )
        out = out.merge(previous, on=keys, how="left")
    else:
        out["pl_12m_antes_brl"] = pd.NA
    for col in [
        "pl_atual_brl",
        "captacao_12m_brl",
        "pl_12m_antes_brl",
        "carteira_atual_brl",
        "inad_atual_brl",
        "fundos_atuais",
        "veiculos_atuais",
        "funds_equiv_atual",
        "cotistas_equiv_atual",
        "links_catalogo",
        "links_com_fonte",
        "links_com_metodo",
        "links_com_camada",
        "links_com_pagina",
        "links_com_data",
        "links_com_score",
        "links_curados",
        "links_ponderados",
    ]:
        out[col] = pd.to_numeric(out.get(col), errors="coerce").fillna(0.0)
    out["competencia_atual"] = _competencia_label(latest_key)
    out["competencia_12m_antes"] = _competencia_label(previous_key) if previous_key else ""
    out["first_competencia"] = out["first_competencia"].map(_competencia_label)
    out["pl_delta_12m_brl"] = out["pl_atual_brl"] - out["pl_12m_antes_brl"]
    out["pl_growth_12m_pct"] = out["pl_delta_12m_brl"] / out["pl_12m_antes_brl"].where(out["pl_12m_antes_brl"].ne(0))
    out["inad_pct_atual"] = out["inad_atual_brl"] / out["carteira_atual_brl"].where(out["carteira_atual_brl"].ne(0))
    out["traceability_links"] = out[
        ["links_com_fonte", "links_com_metodo", "links_com_camada", "links_com_pagina", "links_com_data", "links_com_score"]
    ].max(axis=1)
    out["traceability_links_capped"] = out[["traceability_links", "links_catalogo"]].min(axis=1)
    out["traceability_coverage"] = out["traceability_links_capped"] / out["links_catalogo"].where(out["links_catalogo"].ne(0))
    out["evidence_coverage"] = out["links_com_fonte"] / out["links_catalogo"].where(out["links_catalogo"].ne(0))
    out["curated_coverage"] = out["links_curados"] / out["links_catalogo"].where(out["links_catalogo"].ne(0))
    out["weighted_coverage"] = out["links_ponderados"] / out["links_catalogo"].where(out["links_catalogo"].ne(0))
    out["rank_score"] = out["pl_atual_brl"].abs() + out["captacao_12m_brl"].abs()
    out = out.sort_values(["dimension_id", "rank_score", "links_com_fonte", "dimension_value"], ascending=[True, False, False, True])
    out["rank_in_dimension"] = out.groupby("dimension_id").cumcount() + 1
    out = out.sort_values(["rank_score", "links_com_fonte", "dimension_id", "dimension_value"], ascending=[False, False, True, True])
    out["rank_global"] = range(1, len(out) + 1)
    out["source_artifact"] = "industry_dimension_monthly.csv.gz"
    out["source_method"] = "dimension_value_atlas"
    out["rerun_command"] = "python scripts/build_fidc_industry_dimension_monthly.py"
    for col in DIMENSION_VALUE_ATLAS_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    return out[DIMENSION_VALUE_ATLAS_COLUMNS].reset_index(drop=True)


def _dimension_value_atlas_evidence_summary(catalog: pd.DataFrame | None) -> pd.DataFrame:
    keys = ["dimension_id", "dimension_label", "dimension_value"]
    if catalog is None or catalog.empty or not set(keys).issubset(catalog.columns):
        return pd.DataFrame(columns=keys)
    frame = catalog.copy()
    for col in [
        "cnpj_fundo",
        "source_layer",
        "source_document",
        "source_page",
        "source_method",
        "source_date",
        "confidence_score",
        "review_status",
        "priority_2025_2026",
    ]:
        if col not in frame.columns:
            frame[col] = ""
    for col in keys + ["source_layer", "source_document", "source_page", "source_method", "source_date", "review_status"]:
        frame[col] = frame[col].fillna("").astype(str).str.strip()
    frame = frame[frame["dimension_id"].ne("") & frame["dimension_value"].ne("")].copy()
    if frame.empty:
        return pd.DataFrame(columns=keys)
    frame["cnpj_fundo_norm"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame["confidence_score_num"] = pd.to_numeric(frame["confidence_score"], errors="coerce")
    frame["priority_2025_2026_bool"] = _boolish_series(frame["priority_2025_2026"])
    frame["_source_layer_link"] = frame["source_layer"].ne("").astype(int)
    frame["_source_document_link"] = frame["source_document"].ne("").astype(int)
    frame["_source_page_link"] = frame["source_page"].ne("").astype(int)
    frame["_source_method_link"] = frame["source_method"].ne("").astype(int)
    frame["_source_date_link"] = frame["source_date"].ne("").astype(int)
    frame["_confidence_score_link"] = frame["confidence_score_num"].notna().astype(int)
    grouped = (
        frame.groupby(keys, dropna=False)
        .agg(
            evidence_funds=("cnpj_fundo_norm", lambda values: int(pd.Series(values).replace("", pd.NA).dropna().nunique())),
            links_com_camada=("_source_layer_link", "sum"),
            links_com_pagina=("_source_page_link", "sum"),
            links_com_metodo=("_source_method_link", "sum"),
            links_com_data=("_source_date_link", "sum"),
            links_com_score=("_confidence_score_link", "sum"),
            source_layers=("source_layer", lambda values: _join_unique(values, limit=5)),
            source_documents_sample=("source_document", lambda values: _join_unique(values, limit=5)),
            source_pages_sample=("source_page", lambda values: _join_unique(values, limit=5)),
            source_methods_sample=("source_method", lambda values: _join_unique(values, limit=5)),
            review_status_mix=("review_status", lambda values: _join_unique(values, limit=5)),
            priority_2025_2026_links=("priority_2025_2026_bool", "sum"),
            avg_confidence_score=("confidence_score_num", "mean"),
            last_source_date=("source_date", lambda values: max([str(value) for value in values if str(value).strip()] or [""])),
        )
        .reset_index()
    )
    grouped["avg_confidence_score"] = pd.to_numeric(grouped["avg_confidence_score"], errors="coerce")
    grouped["priority_2025_2026_links"] = pd.to_numeric(grouped["priority_2025_2026_links"], errors="coerce").fillna(0).astype(int)
    return grouped


def industry_dimension_value_atlas_quality_summary(atlas: pd.DataFrame) -> dict[str, object]:
    if atlas is None or atlas.empty:
        return {
            "rows": 0,
            "dimensions": 0,
            "latest_competencia": "",
            "with_source_document_links": 0,
        }
    frame = atlas.copy()
    return {
        "rows": int(len(frame)),
        "dimensions": int(frame["dimension_id"].nunique()) if "dimension_id" in frame else 0,
        "latest_competencia": _first_non_empty(frame.get("competencia_atual", pd.Series(dtype=str))),
        "values_with_pl": int(pd.to_numeric(frame.get("pl_atual_brl"), errors="coerce").fillna(0).gt(0).sum())
        if "pl_atual_brl" in frame
        else 0,
        "values_with_source_document_links": int(
            pd.to_numeric(frame.get("links_com_fonte"), errors="coerce").fillna(0).gt(0).sum()
        )
        if "links_com_fonte" in frame
        else 0,
        "values_with_traceability_links": int(
            pd.to_numeric(frame.get("traceability_coverage"), errors="coerce").fillna(0).gt(0).sum()
        )
        if "traceability_coverage" in frame
        else 0,
        "values_with_source_document_sample": int(
            frame.get("source_documents_sample", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip().ne("").sum()
        )
        if "source_documents_sample" in frame
        else 0,
        "values_with_source_page_sample": int(
            frame.get("source_pages_sample", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip().ne("").sum()
        )
        if "source_pages_sample" in frame
        else 0,
        "values_with_confidence": int(pd.to_numeric(frame.get("avg_confidence_score"), errors="coerce").notna().sum())
        if "avg_confidence_score" in frame
        else 0,
        "with_source_document_links": int(pd.to_numeric(frame.get("links_com_fonte"), errors="coerce").fillna(0).sum())
        if "links_com_fonte" in frame
        else 0,
        "traceability_coverage": _json_float(pd.to_numeric(frame.get("traceability_coverage"), errors="coerce").mean())
        if "traceability_coverage" in frame
        else None,
        "top_rank_score": _json_float(pd.to_numeric(frame.get("rank_score"), errors="coerce").fillna(0).max())
        if "rank_score" in frame
        else None,
    }


def _dimension_profile_snapshot(snapshot: pd.DataFrame) -> pd.DataFrame:
    if snapshot is None or snapshot.empty:
        return pd.DataFrame()
    frame = snapshot.copy()
    if "cnpj_fundo" not in frame.columns and "cnpj" in frame.columns:
        frame["cnpj_fundo"] = frame["cnpj"]
    if "cnpj_fundo" not in frame.columns:
        return pd.DataFrame()
    frame["cnpj_fundo_norm"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame = frame[frame["cnpj_fundo_norm"].astype(str).str.len().eq(14)].copy()
    if frame.empty:
        return frame
    if "cnpj" not in frame.columns:
        frame["cnpj"] = frame["cnpj_fundo_norm"]
    defaults = {
        "competencia": "",
        "pl": 0.0,
        "valid_volume_2024_2026_brl": 0.0,
        "document_rows": 0.0,
        "cedente_rows": 0.0,
        "criteria_rows": 0.0,
        "camadas_com_evidencia": 0.0,
        "tem_sub_minima": False,
    }
    for col, default in defaults.items():
        if col not in frame.columns:
            frame[col] = default
    for col in ["pl", "valid_volume_2024_2026_brl", "document_rows", "cedente_rows", "criteria_rows", "camadas_com_evidencia"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
    frame["tem_sub_minima_bool"] = frame["tem_sub_minima"].astype(str).str.lower().isin({"true", "1", "sim", "s", "yes"})
    return frame[
        [
            "cnpj_fundo_norm",
            "cnpj",
            "competencia",
            "pl",
            "valid_volume_2024_2026_brl",
            "document_rows",
            "cedente_rows",
            "criteria_rows",
            "camadas_com_evidencia",
            "tem_sub_minima_bool",
        ]
    ].copy()


def _dimension_profile_catalog(catalog: pd.DataFrame) -> pd.DataFrame:
    if catalog is None or catalog.empty or "cnpj_fundo" not in catalog.columns:
        return pd.DataFrame()
    frame = catalog.copy()
    frame["cnpj_fundo_norm"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame = frame[frame["cnpj_fundo_norm"].astype(str).str.len().eq(14)].copy()
    required = [
        "dimension_id",
        "dimension_label",
        "dimension_value",
        "value_weight",
        "source_document",
        "is_curated",
        "is_multivalue",
        "confidence_score",
    ]
    for col in required:
        if col not in frame.columns:
            frame[col] = ""
    frame["dimension_value"] = frame["dimension_value"].map(_catalog_clean_value)
    frame = frame[frame["dimension_value"].ne("")].copy()
    frame["value_weight"] = pd.to_numeric(frame["value_weight"], errors="coerce").fillna(1.0)
    frame["source_document_filled"] = frame["source_document"].fillna("").astype(str).str.strip().ne("")
    frame["is_curated_bool"] = frame["is_curated"].astype(str).str.lower().isin({"true", "1", "sim", "s", "yes"})
    frame["is_multivalue_bool"] = frame["is_multivalue"].astype(str).str.lower().isin({"true", "1", "sim", "s", "yes"})
    frame["confidence_score_num"] = pd.to_numeric(frame["confidence_score"], errors="coerce")
    frame = frame.drop_duplicates(["cnpj_fundo_norm", "dimension_id", "dimension_value"], keep="first")
    return frame[
        [
            "cnpj_fundo_norm",
            "dimension_id",
            "dimension_label",
            "dimension_value",
            "value_weight",
            "source_document_filled",
            "is_curated_bool",
            "is_multivalue_bool",
            "confidence_score_num",
        ]
    ].copy()


def build_industry_dimension_profiles(
    *,
    snapshot: pd.DataFrame,
    dimension_catalog: pd.DataFrame,
    target_dimensions: list[str] | None = None,
) -> pd.DataFrame:
    """Aggregate latest source-dimension x target-dimension profiles."""

    funds = _dimension_profile_snapshot(snapshot)
    catalog = _dimension_profile_catalog(dimension_catalog)
    if funds.empty or catalog.empty:
        return pd.DataFrame(columns=_DIMENSION_PROFILE_COLUMNS)
    source = catalog.add_prefix("source_").rename(columns={"source_cnpj_fundo_norm": "cnpj_fundo_norm"})
    target = catalog
    if target_dimensions:
        targets = {str(item) for item in target_dimensions}
        target = target[target["dimension_id"].astype(str).isin(targets)].copy()
    target = target.add_prefix("target_").rename(columns={"target_cnpj_fundo_norm": "cnpj_fundo_norm"})
    pairs = source.merge(target, on="cnpj_fundo_norm", how="inner")
    if pairs.empty:
        return pd.DataFrame(columns=_DIMENSION_PROFILE_COLUMNS)
    pairs = pairs.merge(funds, on="cnpj_fundo_norm", how="inner")
    if pairs.empty:
        return pd.DataFrame(columns=_DIMENSION_PROFILE_COLUMNS)

    weight = (
        pd.to_numeric(pairs["source_value_weight"], errors="coerce").fillna(1.0)
        * pd.to_numeric(pairs["target_value_weight"], errors="coerce").fillna(1.0)
    )
    pairs["_pair_weight"] = weight
    pairs["_pl_brl"] = pairs["pl"] * weight
    pairs["_issuance_2024_2026_brl"] = pairs["valid_volume_2024_2026_brl"] * weight
    pairs["_document_rows_equiv"] = pairs["document_rows"] * weight
    pairs["_cedente_rows_equiv"] = pairs["cedente_rows"] * weight
    pairs["_criteria_rows_equiv"] = pairs["criteria_rows"] * weight
    pairs["_evidence_layers_equiv"] = pairs["camadas_com_evidencia"] * weight
    pairs["_with_subordination_min_equiv"] = pairs["tem_sub_minima_bool"].astype(int) * weight
    pairs["_source_document_pair"] = (
        pairs["source_source_document_filled"].astype(bool) | pairs["target_source_document_filled"].astype(bool)
    ).astype(int)
    pairs["_curated_pair"] = (pairs["source_is_curated_bool"].astype(bool) | pairs["target_is_curated_bool"].astype(bool)).astype(int)
    pairs["_weighted_pair"] = weight.lt(1.0).astype(int)
    pairs["_pair_confidence"] = pairs[["source_confidence_score_num", "target_confidence_score_num"]].mean(axis=1, skipna=True)

    keys = [
        "competencia",
        "source_dimension_id",
        "source_dimension_label",
        "source_dimension_value",
        "target_dimension_id",
        "target_dimension_label",
        "target_dimension_value",
    ]
    grouped = (
        pairs.groupby(keys, dropna=False)
        .agg(
            pl_brl=("_pl_brl", "sum"),
            issuance_2024_2026_brl=("_issuance_2024_2026_brl", "sum"),
            funds_equiv=("_pair_weight", "sum"),
            funds_unique=("cnpj_fundo_norm", "nunique"),
            vehicles_unique=("cnpj", "nunique"),
            document_rows_equiv=("_document_rows_equiv", "sum"),
            cedente_rows_equiv=("_cedente_rows_equiv", "sum"),
            criteria_rows_equiv=("_criteria_rows_equiv", "sum"),
            evidence_layers_equiv=("_evidence_layers_equiv", "sum"),
            with_subordination_min_equiv=("_with_subordination_min_equiv", "sum"),
            catalog_links=("cnpj_fundo_norm", "size"),
            source_document_links=("_source_document_pair", "sum"),
            curated_links=("_curated_pair", "sum"),
            weighted_links=("_weighted_pair", "sum"),
            avg_confidence_score=("_pair_confidence", "mean"),
        )
        .reset_index()
    )
    for col in _DIMENSION_PROFILE_COLUMNS:
        if col not in grouped.columns:
            grouped[col] = 0 if col not in keys else ""
    return grouped[_DIMENSION_PROFILE_COLUMNS].sort_values(
        ["source_dimension_id", "source_dimension_value", "target_dimension_id", "pl_brl"],
        ascending=[True, True, True, False],
    )


def build_industry_heatmap_registry(
    *,
    dimension_catalog: pd.DataFrame,
    profiles: pd.DataFrame | None = None,
    presets: list[dict[str, object]] | None = None,
) -> pd.DataFrame:
    """Build an auditable registry of declarative heatmap presets."""

    preset_specs = presets or HEATMAP_PRESET_SPECS
    catalog = pd.DataFrame() if dimension_catalog is None else dimension_catalog.copy()
    profile_frame = pd.DataFrame() if profiles is None else profiles.copy()
    available_dimensions: set[str] = set()
    catalog_labels: dict[str, str] = {}
    if not catalog.empty and {"dimension_id", "dimension_label"}.issubset(catalog.columns):
        catalog["dimension_id"] = catalog["dimension_id"].fillna("").astype(str)
        catalog["dimension_label"] = catalog["dimension_label"].fillna("").astype(str)
        available_dimensions = set(catalog.loc[catalog["dimension_id"].str.strip().ne(""), "dimension_id"])
        catalog_labels = (
            catalog[catalog["dimension_id"].str.strip().ne("")]
            .drop_duplicates("dimension_id")
            .set_index("dimension_id")["dimension_label"]
            .to_dict()
        )

    profile_lookup: dict[tuple[str, str], dict[str, object]] = {}
    required_profile_cols = {"source_dimension_id", "target_dimension_id"}
    if not profile_frame.empty and required_profile_cols.issubset(profile_frame.columns):
        profile_frame["source_dimension_id"] = profile_frame["source_dimension_id"].fillna("").astype(str)
        profile_frame["target_dimension_id"] = profile_frame["target_dimension_id"].fillna("").astype(str)
        for (source_id, target_id), group in profile_frame.groupby(["source_dimension_id", "target_dimension_id"], dropna=False):
            profile_lookup[(str(source_id), str(target_id))] = {
                "profile_rows": int(len(group)),
                "profile_links": int(pd.to_numeric(group.get("catalog_links"), errors="coerce").fillna(0).sum()),
                "source_document_links": int(pd.to_numeric(group.get("source_document_links"), errors="coerce").fillna(0).sum()),
                "curated_links": int(pd.to_numeric(group.get("curated_links"), errors="coerce").fillna(0).sum()),
                "weighted_links": int(pd.to_numeric(group.get("weighted_links"), errors="coerce").fillna(0).sum()),
                "avg_confidence_score": _json_float(pd.to_numeric(group.get("avg_confidence_score"), errors="coerce").mean()),
            }

    rows: list[dict[str, object]] = []
    for order, spec in enumerate(preset_specs, start=1):
        row_id = str(spec.get("row_dimension_id", ""))
        col_id = str(spec.get("col_dimension_id", ""))
        row_label = catalog_labels.get(row_id) or str(spec.get("row_label", row_id))
        col_label = catalog_labels.get(col_id) or str(spec.get("col_label", col_id))
        missing = []
        if row_id not in available_dimensions:
            missing.append(row_label)
        if col_id not in available_dimensions:
            missing.append(col_label)
        available = not missing
        profile_stats = profile_lookup.get((row_id, col_id), {})
        profile_available = bool(available and int(profile_stats.get("profile_rows", 0) or 0) > 0)
        status = "ok" if profile_available else ("sem_perfil" if available else "sem_dimensao")
        rows.append(
            {
                "preset_id": spec.get("preset_id", f"{row_id}_{col_id}"),
                "preset_label": spec.get("label", f"{row_label} × {col_label}"),
                "order": order,
                "row_dimension_id": row_id,
                "row_dimension_label": row_label,
                "col_dimension_id": col_id,
                "col_dimension_label": col_label,
                "status": status,
                "available": available,
                "profile_available": profile_available,
                "missing_dimensions": " | ".join(missing),
                "profile_rows": int(profile_stats.get("profile_rows", 0) or 0),
                "profile_links": int(profile_stats.get("profile_links", 0) or 0),
                "source_document_links": int(profile_stats.get("source_document_links", 0) or 0),
                "curated_links": int(profile_stats.get("curated_links", 0) or 0),
                "weighted_links": int(profile_stats.get("weighted_links", 0) or 0),
                "avg_confidence_score": profile_stats.get("avg_confidence_score"),
                "metrics_supported": "PL médio | Fundos | Veículos" if profile_available else "",
                "source_mode": "dimension_profiles" if profile_available else ("catalog_runtime" if available else "missing_dimension"),
                "rerun_command": "python scripts/build_fidc_industry_dimension_profiles.py",
            }
        )
    if not rows:
        return pd.DataFrame(columns=HEATMAP_REGISTRY_COLUMNS)
    frame = pd.DataFrame(rows)
    for col in HEATMAP_REGISTRY_COLUMNS:
        if col not in frame.columns:
            frame[col] = ""
    return frame[HEATMAP_REGISTRY_COLUMNS].sort_values("order").reset_index(drop=True)


def industry_dimension_profile_quality_summary(profiles: pd.DataFrame) -> dict[str, object]:
    if profiles is None or profiles.empty:
        return {
            "rows": 0,
            "source_dimensions": 0,
            "target_dimensions": 0,
            "source_values": 0,
            "target_values": 0,
        }
    frame = profiles.copy()
    return {
        "rows": int(len(frame)),
        "competencia": _first_non_empty(frame.get("competencia", pd.Series(dtype=str))),
        "source_dimensions": int(frame["source_dimension_id"].nunique()) if "source_dimension_id" in frame else 0,
        "target_dimensions": int(frame["target_dimension_id"].nunique()) if "target_dimension_id" in frame else 0,
        "source_values": int(frame[["source_dimension_id", "source_dimension_value"]].drop_duplicates().shape[0])
        if {"source_dimension_id", "source_dimension_value"}.issubset(frame.columns)
        else 0,
        "target_values": int(frame[["target_dimension_id", "target_dimension_value"]].drop_duplicates().shape[0])
        if {"target_dimension_id", "target_dimension_value"}.issubset(frame.columns)
        else 0,
        "profile_links": int(pd.to_numeric(frame.get("catalog_links"), errors="coerce").fillna(0).sum()),
        "with_source_document_links": int(pd.to_numeric(frame.get("source_document_links"), errors="coerce").fillna(0).sum()),
        "curated_links": int(pd.to_numeric(frame.get("curated_links"), errors="coerce").fillna(0).sum()),
        "weighted_links": int(pd.to_numeric(frame.get("weighted_links"), errors="coerce").fillna(0).sum()),
    }


def _dimension_label_lookup(
    atlas: pd.DataFrame | None,
    profiles: pd.DataFrame | None,
    heatmap_registry: pd.DataFrame | None,
) -> dict[str, str]:
    labels: dict[str, str] = {}
    if atlas is not None and not atlas.empty and {"dimension_id", "dimension_label"}.issubset(atlas.columns):
        for _, row in atlas[["dimension_id", "dimension_label"]].drop_duplicates().iterrows():
            dim_id = str(row.get("dimension_id", "") or "").strip()
            label = str(row.get("dimension_label", "") or "").strip()
            if dim_id and label and dim_id not in labels:
                labels[dim_id] = label
    if profiles is not None and not profiles.empty:
        for id_col, label_col in [
            ("source_dimension_id", "source_dimension_label"),
            ("target_dimension_id", "target_dimension_label"),
        ]:
            if {id_col, label_col}.issubset(profiles.columns):
                for _, row in profiles[[id_col, label_col]].drop_duplicates().iterrows():
                    dim_id = str(row.get(id_col, "") or "").strip()
                    label = str(row.get(label_col, "") or "").strip()
                    if dim_id and label and dim_id not in labels:
                        labels[dim_id] = label
    if heatmap_registry is not None and not heatmap_registry.empty:
        for id_col, label_col in [
            ("row_dimension_id", "row_dimension_label"),
            ("col_dimension_id", "col_dimension_label"),
        ]:
            if {id_col, label_col}.issubset(heatmap_registry.columns):
                for _, row in heatmap_registry[[id_col, label_col]].drop_duplicates().iterrows():
                    dim_id = str(row.get(id_col, "") or "").strip()
                    label = str(row.get(label_col, "") or "").strip()
                    if dim_id and label and dim_id not in labels:
                        labels[dim_id] = label
    return labels


def build_industry_dimension_dossiers(
    *,
    atlas: pd.DataFrame,
    profiles: pd.DataFrame | None = None,
    heatmap_registry: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Summarize Deep Dive readiness by reusable structured dimension."""

    atlas_frame = pd.DataFrame() if atlas is None else atlas.copy()
    profile_frame = pd.DataFrame() if profiles is None else profiles.copy()
    registry_frame = pd.DataFrame() if heatmap_registry is None else heatmap_registry.copy()
    labels = _dimension_label_lookup(atlas_frame, profile_frame, registry_frame)
    dimension_ids: set[str] = set(labels)
    if not atlas_frame.empty and "dimension_id" in atlas_frame.columns:
        dimension_ids.update(value for value in atlas_frame["dimension_id"].fillna("").astype(str).str.strip() if value)
    if not profile_frame.empty and "source_dimension_id" in profile_frame.columns:
        dimension_ids.update(value for value in profile_frame["source_dimension_id"].fillna("").astype(str).str.strip() if value)
    if not registry_frame.empty:
        for col in ["row_dimension_id", "col_dimension_id"]:
            if col in registry_frame.columns:
                dimension_ids.update(value for value in registry_frame[col].fillna("").astype(str).str.strip() if value)
    if not dimension_ids:
        return pd.DataFrame(columns=DIMENSION_DOSSIER_COLUMNS)

    atlas_required = {"dimension_id", "dimension_value"}
    if not atlas_frame.empty and atlas_required.issubset(atlas_frame.columns):
        for col in [
            "pl_atual_brl",
            "captacao_12m_brl",
            "fundos_atuais",
            "veiculos_atuais",
            "links_catalogo",
            "links_com_fonte",
            "links_com_metodo",
            "links_com_camada",
            "links_com_pagina",
            "links_com_data",
            "links_com_score",
            "links_curados",
            "links_ponderados",
            "avg_confidence_score",
            "priority_2025_2026_links",
            "rank_score",
        ]:
            if col not in atlas_frame.columns:
                atlas_frame[col] = 0.0
            atlas_frame[col] = pd.to_numeric(atlas_frame[col], errors="coerce").fillna(0.0)
        for col in [
            "dimension_label",
            "competencia_atual",
            "source_documents_sample",
            "source_pages_sample",
            "source_methods_sample",
            "review_status_mix",
        ]:
            if col not in atlas_frame.columns:
                atlas_frame[col] = ""
            atlas_frame[col] = atlas_frame[col].fillna("").astype(str)
        atlas_frame["dimension_id"] = atlas_frame["dimension_id"].fillna("").astype(str).str.strip()
        atlas_frame["dimension_value"] = atlas_frame["dimension_value"].fillna("").astype(str).str.strip()
    else:
        atlas_frame = pd.DataFrame()

    if not profile_frame.empty and "source_dimension_id" in profile_frame.columns:
        for col in [
            "catalog_links",
            "source_document_links",
            "curated_links",
            "weighted_links",
            "avg_confidence_score",
        ]:
            if col not in profile_frame.columns:
                profile_frame[col] = 0.0
            profile_frame[col] = pd.to_numeric(profile_frame[col], errors="coerce").fillna(0.0)
        for col in ["source_dimension_id", "target_dimension_id", "target_dimension_value"]:
            if col not in profile_frame.columns:
                profile_frame[col] = ""
            profile_frame[col] = profile_frame[col].fillna("").astype(str).str.strip()
    else:
        profile_frame = pd.DataFrame()

    if not registry_frame.empty:
        for col in ["row_dimension_id", "col_dimension_id", "preset_label"]:
            if col not in registry_frame.columns:
                registry_frame[col] = ""
            registry_frame[col] = registry_frame[col].fillna("").astype(str).str.strip()
        if "profile_available" not in registry_frame.columns:
            registry_frame["profile_available"] = False
        registry_frame["_profile_available_bool"] = _boolish_series(registry_frame["profile_available"])

    rows: list[dict[str, object]] = []
    for dim_id in sorted(dimension_ids):
        dim_atlas = (
            atlas_frame[atlas_frame["dimension_id"].astype(str).eq(dim_id)].copy()
            if not atlas_frame.empty
            else pd.DataFrame()
        )
        label = labels.get(dim_id, dim_id)
        if not dim_atlas.empty:
            label = _first_non_empty(dim_atlas.get("dimension_label", pd.Series(dtype=str))) or label
            sort_cols = [col for col in ["rank_score", "pl_atual_brl", "dimension_value"] if col in dim_atlas.columns]
            if sort_cols:
                dim_atlas = dim_atlas.sort_values(
                    sort_cols,
                    ascending=[False if col != "dimension_value" else True for col in sort_cols],
                )
            top_20 = dim_atlas.head(20)
            links_catalogo = float(pd.to_numeric(dim_atlas.get("links_catalogo"), errors="coerce").fillna(0.0).sum())
            links_com_fonte = float(pd.to_numeric(dim_atlas.get("links_com_fonte"), errors="coerce").fillna(0.0).sum())
            links_com_metodo = float(pd.to_numeric(dim_atlas.get("links_com_metodo"), errors="coerce").fillna(0.0).sum())
            links_com_camada = float(pd.to_numeric(dim_atlas.get("links_com_camada"), errors="coerce").fillna(0.0).sum())
            links_com_pagina = float(pd.to_numeric(dim_atlas.get("links_com_pagina"), errors="coerce").fillna(0.0).sum())
            links_com_data = float(pd.to_numeric(dim_atlas.get("links_com_data"), errors="coerce").fillna(0.0).sum())
            links_com_score = float(pd.to_numeric(dim_atlas.get("links_com_score"), errors="coerce").fillna(0.0).sum())
            links_curados = float(pd.to_numeric(dim_atlas.get("links_curados"), errors="coerce").fillna(0.0).sum())
            links_ponderados = float(pd.to_numeric(dim_atlas.get("links_ponderados"), errors="coerce").fillna(0.0).sum())
            traceability_parts = dim_atlas[
                [
                    "links_com_fonte",
                    "links_com_metodo",
                    "links_com_camada",
                    "links_com_pagina",
                    "links_com_data",
                    "links_com_score",
                ]
            ].copy()
            traceability_by_value = traceability_parts.max(axis=1)
            catalog_by_value = pd.to_numeric(dim_atlas.get("links_catalogo"), errors="coerce").fillna(0.0)
            traceability_links = float(pd.concat([traceability_by_value, catalog_by_value], axis=1).min(axis=1).sum())
            atlas_values = int(dim_atlas["dimension_value"].nunique())
            atlas_values_with_pl = int(pd.to_numeric(dim_atlas.get("pl_atual_brl"), errors="coerce").fillna(0).gt(0).sum())
            source_document_coverage = links_com_fonte / links_catalogo if links_catalogo else None
            traceability_coverage = traceability_links / links_catalogo if links_catalogo else None
            curated_coverage = links_curados / links_catalogo if links_catalogo else None
            weighted_coverage = links_ponderados / links_catalogo if links_catalogo else None
            avg_confidence = _json_float(pd.to_numeric(dim_atlas.get("avg_confidence_score"), errors="coerce").mean())
        else:
            top_20 = pd.DataFrame()
            links_catalogo = links_com_fonte = links_com_metodo = links_com_camada = 0.0
            links_com_pagina = links_com_data = links_com_score = 0.0
            traceability_links = links_curados = links_ponderados = 0.0
            atlas_values = atlas_values_with_pl = 0
            source_document_coverage = traceability_coverage = curated_coverage = weighted_coverage = None
            avg_confidence = None

        dim_profiles = (
            profile_frame[profile_frame["source_dimension_id"].astype(str).eq(dim_id)].copy()
            if not profile_frame.empty
            else pd.DataFrame()
        )
        profile_links = float(pd.to_numeric(dim_profiles.get("catalog_links"), errors="coerce").fillna(0.0).sum()) if not dim_profiles.empty else 0.0
        profile_source_document_links = (
            float(pd.to_numeric(dim_profiles.get("source_document_links"), errors="coerce").fillna(0.0).sum())
            if not dim_profiles.empty
            else 0.0
        )
        profile_curated_links = (
            float(pd.to_numeric(dim_profiles.get("curated_links"), errors="coerce").fillna(0.0).sum())
            if not dim_profiles.empty
            else 0.0
        )
        profile_weighted_links = (
            float(pd.to_numeric(dim_profiles.get("weighted_links"), errors="coerce").fillna(0.0).sum())
            if not dim_profiles.empty
            else 0.0
        )

        if not registry_frame.empty:
            dim_registry = registry_frame[
                registry_frame["row_dimension_id"].astype(str).eq(dim_id)
                | registry_frame["col_dimension_id"].astype(str).eq(dim_id)
            ].copy()
        else:
            dim_registry = pd.DataFrame()
        heatmap_presets = int(len(dim_registry))
        heatmap_presets_ok = (
            int(dim_registry.get("_profile_available_bool", pd.Series(False, index=dim_registry.index)).sum())
            if not dim_registry.empty
            else 0
        )

        reasons = []
        if atlas_values == 0:
            reasons.append("sem atlas mensal")
        if atlas_values_with_pl == 0:
            reasons.append("sem PL atual")
        if profile_links == 0:
            reasons.append("sem perfil cruzado")
        if links_catalogo and (traceability_coverage or 0.0) < 0.5:
            reasons.append("baixa rastreabilidade")
        if heatmap_presets and heatmap_presets_ok == 0:
            reasons.append("presets sem perfil")
        status = "bloqueado" if atlas_values == 0 else ("atenção" if reasons else "ok")

        rows.append(
            {
                "dimension_id": dim_id,
                "dimension_label": label,
                "status_dossie": status,
                "status_reasons": " | ".join(reasons),
                "latest_competencia": _first_non_empty(dim_atlas.get("competencia_atual", pd.Series(dtype=str))) if not dim_atlas.empty else "",
                "atlas_values": atlas_values,
                "atlas_values_with_pl": atlas_values_with_pl,
                "top_values_sample": _join_unique(top_20.get("dimension_value", pd.Series(dtype=str)), limit=10) if not top_20.empty else "",
                "pl_total_atual_brl": float(pd.to_numeric(dim_atlas.get("pl_atual_brl"), errors="coerce").fillna(0.0).sum()) if not dim_atlas.empty else 0.0,
                "pl_top_20_brl": float(pd.to_numeric(top_20.get("pl_atual_brl"), errors="coerce").fillna(0.0).sum()) if not top_20.empty else 0.0,
                "captacao_12m_top_20_brl": float(pd.to_numeric(top_20.get("captacao_12m_brl"), errors="coerce").fillna(0.0).sum()) if not top_20.empty else 0.0,
                "fundos_atuais_total": float(pd.to_numeric(dim_atlas.get("fundos_atuais"), errors="coerce").fillna(0.0).sum()) if not dim_atlas.empty else 0.0,
                "veiculos_atuais_total": float(pd.to_numeric(dim_atlas.get("veiculos_atuais"), errors="coerce").fillna(0.0).sum()) if not dim_atlas.empty else 0.0,
                "links_catalogo": links_catalogo,
                "links_com_fonte": links_com_fonte,
                "source_document_coverage": source_document_coverage,
                "links_com_metodo": links_com_metodo,
                "links_com_camada": links_com_camada,
                "traceability_links": traceability_links,
                "traceability_coverage": traceability_coverage,
                "links_curados": links_curados,
                "curated_coverage": curated_coverage,
                "links_ponderados": links_ponderados,
                "weighted_coverage": weighted_coverage,
                "avg_confidence_score": avg_confidence,
                "source_documents_sample": _join_unique(dim_atlas.get("source_documents_sample", pd.Series(dtype=str)), limit=8) if not dim_atlas.empty else "",
                "source_pages_sample": _join_unique(dim_atlas.get("source_pages_sample", pd.Series(dtype=str)), limit=8) if not dim_atlas.empty else "",
                "source_methods_sample": _join_unique(dim_atlas.get("source_methods_sample", pd.Series(dtype=str)), limit=8) if not dim_atlas.empty else "",
                "review_status_mix": _join_unique(dim_atlas.get("review_status_mix", pd.Series(dtype=str)), limit=8) if not dim_atlas.empty else "",
                "priority_2025_2026_links": float(pd.to_numeric(dim_atlas.get("priority_2025_2026_links"), errors="coerce").fillna(0.0).sum()) if not dim_atlas.empty else 0.0,
                "profile_rows": int(len(dim_profiles)),
                "profile_target_dimensions": int(dim_profiles["target_dimension_id"].nunique()) if not dim_profiles.empty else 0,
                "profile_target_values": int(dim_profiles["target_dimension_value"].nunique()) if not dim_profiles.empty else 0,
                "profile_links": profile_links,
                "profile_source_document_links": profile_source_document_links,
                "profile_curated_links": profile_curated_links,
                "profile_weighted_links": profile_weighted_links,
                "profile_avg_confidence_score": _json_float(pd.to_numeric(dim_profiles.get("avg_confidence_score"), errors="coerce").mean()) if not dim_profiles.empty else None,
                "heatmap_presets": heatmap_presets,
                "heatmap_presets_ok": heatmap_presets_ok,
                "heatmap_preset_labels_sample": _join_unique(dim_registry.get("preset_label", pd.Series(dtype=str)), limit=8) if not dim_registry.empty else "",
                "source_artifacts": "industry_dimension_value_atlas.csv.gz | industry_dimension_profiles.csv.gz | industry_heatmap_registry.csv",
                "source_method": "dimension_dossier",
                "rerun_command": "python scripts/build_fidc_industry_dimension_dossiers.py",
            }
        )

    frame = pd.DataFrame(rows)
    for col in DIMENSION_DOSSIER_COLUMNS:
        if col not in frame.columns:
            frame[col] = ""
    status_order = {"bloqueado": 0, "atenção": 1, "ok": 2}
    frame["_status_order"] = frame["status_dossie"].map(status_order).fillna(9)
    frame["pl_total_atual_brl"] = pd.to_numeric(frame["pl_total_atual_brl"], errors="coerce").fillna(0.0)
    frame = frame.sort_values(["_status_order", "pl_total_atual_brl", "dimension_label"], ascending=[True, False, True])
    return frame.drop(columns=["_status_order"])[DIMENSION_DOSSIER_COLUMNS].reset_index(drop=True)


def industry_dimension_dossier_quality_summary(dossiers: pd.DataFrame) -> dict[str, object]:
    if dossiers is None or dossiers.empty:
        return {
            "rows": 0,
            "ok_rows": 0,
            "attention_rows": 0,
            "blocked_rows": 0,
            "dimensions": 0,
        }
    frame = dossiers.copy()
    status = frame.get("status_dossie", pd.Series("", index=frame.index)).fillna("").astype(str)
    links = pd.to_numeric(frame.get("links_catalogo"), errors="coerce").fillna(0.0)
    source_links = pd.to_numeric(frame.get("links_com_fonte"), errors="coerce").fillna(0.0)
    traceability_links = pd.to_numeric(frame.get("traceability_links"), errors="coerce").fillna(0.0)
    return {
        "rows": int(len(frame)),
        "dimensions": int(frame["dimension_id"].nunique()) if "dimension_id" in frame else int(len(frame)),
        "ok_rows": int(status.eq("ok").sum()),
        "attention_rows": int(status.eq("atenção").sum()),
        "blocked_rows": int(status.eq("bloqueado").sum()),
        "atlas_values": int(pd.to_numeric(frame.get("atlas_values"), errors="coerce").fillna(0).sum()),
        "atlas_values_with_pl": int(pd.to_numeric(frame.get("atlas_values_with_pl"), errors="coerce").fillna(0).sum()),
        "profile_rows": int(pd.to_numeric(frame.get("profile_rows"), errors="coerce").fillna(0).sum()),
        "profile_links": int(pd.to_numeric(frame.get("profile_links"), errors="coerce").fillna(0).sum()),
        "with_profiles": int(pd.to_numeric(frame.get("profile_rows"), errors="coerce").fillna(0).gt(0).sum()),
        "heatmap_presets": int(pd.to_numeric(frame.get("heatmap_presets"), errors="coerce").fillna(0).sum()),
        "heatmap_presets_ok": int(pd.to_numeric(frame.get("heatmap_presets_ok"), errors="coerce").fillna(0).sum()),
        "source_document_coverage": _json_float(source_links.sum() / links.sum()) if links.sum() else None,
        "traceability_coverage": _json_float(traceability_links.sum() / links.sum()) if links.sum() else None,
    }


def build_dimension_dossier_pipeline_manifest(
    *,
    industry_dir: Path,
    atlas_path: Path,
    profiles_path: Path,
    heatmap_registry_path: Path,
    output_path: Path,
    manifest_path: Path,
    atlas: pd.DataFrame,
    profiles: pd.DataFrame,
    heatmap_registry: pd.DataFrame,
    dossiers: pd.DataFrame,
) -> dict[str, object]:
    quality = industry_dimension_dossier_quality_summary(dossiers)
    return {
        "schema_version": "industry-dimension-dossier-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_dimension_dossiers",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "macbook_air_m4_friendly": True,
            "notes": [
                "Resume cada dimensao estruturada em um dossie reutilizavel para Deep Dive e auditoria publica.",
                "Nao le documentos brutos; consome apenas atlas, perfis e registry de heatmaps ja materializados.",
                "A UI pode atualizar mensalmente lendo este CSV sem joins pesados no momento da interacao.",
            ],
        },
        "inputs": {
            "dimension_value_atlas": file_fingerprint(atlas_path),
            "dimension_profiles": file_fingerprint(profiles_path),
            "heatmap_registry": file_fingerprint(heatmap_registry_path),
        },
        "outputs": {
            "dimension_dossiers": file_fingerprint(output_path),
            "manifest": {"path": str(manifest_path)},
        },
        "stages": [
            {
                "id": "load_dimension_layers",
                "label": "Carregar camadas dimensionais",
                "status": "ok" if not atlas.empty and not profiles.empty else "empty",
                "input": f"{atlas_path}+{profiles_path}+{heatmap_registry_path}",
                "output": "memoria:atlas+profiles+heatmap_registry",
                "rows": int(len(atlas) + len(profiles) + len(heatmap_registry)),
                "rerun": "python scripts/build_fidc_industry_dimension_monthly.py && python scripts/build_fidc_industry_dimension_profiles.py",
            },
            {
                "id": "summarize_dimension_dossiers",
                "label": "Materializar dossiês por dimensão",
                "status": "ok" if not dossiers.empty else "empty",
                "input": "memoria:atlas+profiles+heatmap_registry",
                "output": str(output_path),
                "rows": int(len(dossiers)),
                "ok_rows": quality.get("ok_rows", 0),
                "rerun": "python scripts/build_fidc_industry_dimension_dossiers.py",
            },
        ],
        "quality": quality,
    }


def build_dimension_profile_pipeline_manifest(
    *,
    industry_dir: Path,
    snapshot_path: Path,
    dimension_catalog_path: Path,
    output_path: Path,
    manifest_path: Path,
    heatmap_registry_path: Path | None = None,
    snapshot: pd.DataFrame,
    dimension_catalog: pd.DataFrame,
    profiles: pd.DataFrame,
    heatmap_registry: pd.DataFrame | None = None,
) -> dict[str, object]:
    quality = industry_dimension_profile_quality_summary(profiles)
    if heatmap_registry is not None and not heatmap_registry.empty:
        status_counts = (
            heatmap_registry.get("status", pd.Series("", index=heatmap_registry.index))
            .fillna("")
            .astype(str)
            .value_counts()
            .to_dict()
        )
        quality.update(
            {
                "heatmap_preset_rows": int(len(heatmap_registry)),
                "heatmap_preset_available": int(
                    heatmap_registry.get("available", pd.Series(False, index=heatmap_registry.index))
                    .astype(str)
                    .str.lower()
                    .isin({"true", "1"})
                    .sum()
                ),
                "heatmap_preset_profile_available": int(
                    heatmap_registry.get("profile_available", pd.Series(False, index=heatmap_registry.index))
                    .astype(str)
                    .str.lower()
                    .isin({"true", "1"})
                    .sum()
                ),
                "heatmap_preset_status_counts": {str(k): int(v) for k, v in status_counts.items()},
            }
        )
    else:
        quality.update(
            {
                "heatmap_preset_rows": 0,
                "heatmap_preset_available": 0,
                "heatmap_preset_profile_available": 0,
                "heatmap_preset_status_counts": {},
            }
        )
    outputs = {
        "dimension_profiles": file_fingerprint(output_path),
        "manifest": {"path": str(manifest_path)},
    }
    if heatmap_registry_path is not None:
        outputs["heatmap_registry"] = file_fingerprint(heatmap_registry_path)
    return {
        "schema_version": "industry-dimension-profile-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_dimension_profiles",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "macbook_air_m4_friendly": True,
            "notes": [
                "Materializa cruzamentos dimensão-origem x dimensão-alvo para Deep Dives e heatmaps.",
                "Usa apenas snapshot e catálogo já estruturados; não reprocessa informes ou documentos.",
                "Dimensões multivalor são ponderadas pelo produto dos pesos de origem e alvo.",
            ],
        },
        "inputs": {
            "fund_snapshot": file_fingerprint(snapshot_path),
            "dimension_catalog": file_fingerprint(dimension_catalog_path),
        },
        "outputs": outputs,
        "stages": [
            {
                "id": "load_snapshot_and_catalog",
                "label": "Carregar snapshot e catálogo",
                "status": "ok" if not snapshot.empty and not dimension_catalog.empty else "empty",
                "input": f"{snapshot_path}+{dimension_catalog_path}",
                "output": "memoria:snapshot+dimension_catalog",
                "rows": int(len(snapshot) + len(dimension_catalog)),
                "rerun": "python scripts/build_fidc_industry_fund_snapshot.py && python scripts/build_fidc_industry_dimensions.py",
            },
            {
                "id": "aggregate_cross_dimension_profiles",
                "label": "Agregar perfis cruzados",
                "status": "ok" if not profiles.empty else "empty",
                "input": "memoria:snapshot+dimension_catalog",
                "output": str(output_path),
                "rows": int(len(profiles)),
                "profile_links": quality.get("profile_links", 0),
                "rerun": "python scripts/build_fidc_industry_dimension_profiles.py",
            },
            {
                "id": "register_heatmap_presets",
                "label": "Registrar presets de heatmap",
                "status": "ok" if heatmap_registry_path is not None and heatmap_registry_path.exists() else "empty",
                "input": "memoria:dimension_profiles+dimension_catalog",
                "output": str(heatmap_registry_path) if heatmap_registry_path is not None else "",
                "rows": int(len(heatmap_registry)) if heatmap_registry is not None else 0,
                "available_presets": quality.get("heatmap_preset_available", 0),
                "rerun": "python scripts/build_fidc_industry_dimension_profiles.py",
            },
        ],
        "quality": quality,
    }


def build_dimension_monthly_pipeline_manifest(
    *,
    industry_dir: Path,
    vehicle_monthly_path: Path,
    dimension_catalog_path: Path,
    output_path: Path,
    manifest_path: Path,
    atlas_path: Path | None = None,
    vehicle_monthly: pd.DataFrame,
    dimension_catalog: pd.DataFrame,
    monthly: pd.DataFrame,
    atlas: pd.DataFrame | None = None,
    max_competencia: str | None = None,
) -> dict[str, object]:
    quality = industry_dimension_monthly_quality_summary(monthly)
    atlas_quality = industry_dimension_value_atlas_quality_summary(atlas if atlas is not None else pd.DataFrame())
    quality.update(
        {
            "max_competencia_requested": _competencia_label(max_competencia) if max_competencia else "",
            "atlas_rows": atlas_quality.get("rows", 0),
            "atlas_dimensions": atlas_quality.get("dimensions", 0),
            "atlas_latest_competencia": atlas_quality.get("latest_competencia", ""),
            "atlas_values_with_pl": atlas_quality.get("values_with_pl", 0),
            "atlas_values_with_source_document_links": atlas_quality.get("values_with_source_document_links", 0),
            "atlas_values_with_traceability_links": atlas_quality.get("values_with_traceability_links", 0),
            "atlas_values_with_source_document_sample": atlas_quality.get("values_with_source_document_sample", 0),
            "atlas_values_with_source_page_sample": atlas_quality.get("values_with_source_page_sample", 0),
            "atlas_values_with_confidence": atlas_quality.get("values_with_confidence", 0),
            "atlas_source_document_links": atlas_quality.get("with_source_document_links", 0),
            "atlas_traceability_coverage": atlas_quality.get("traceability_coverage"),
        }
    )
    outputs = {
        "dimension_monthly": file_fingerprint(output_path),
        "manifest": {"path": str(manifest_path)},
    }
    if atlas_path is not None:
        outputs["dimension_value_atlas"] = file_fingerprint(atlas_path)
    return {
        "schema_version": "industry-dimension-monthly-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "industry_dimension_monthly",
        "design_constraints": {
            "modular": True,
            "incremental": True,
            "macbook_air_m4_friendly": True,
            "notes": [
                "Este modulo agrega metricas mensais por dimensao reutilizavel sem expandir o arquivo de UI.",
                "O catalogo de dimensoes fornece pesos e relacoes; a base granular mensal fornece as metricas.",
                "Por padrao, a serie e o atlas param na competencia_snapshot para nao misturar dimensoes curadas de uma foto antiga com um mes agregado mais recente.",
                "Deep Dives podem usar esta serie diretamente, preservando fallback para detalhe por veiculo.",
            ],
        },
        "inputs": {
            "vehicle_monthly": file_fingerprint(vehicle_monthly_path),
            "dimension_catalog": file_fingerprint(dimension_catalog_path),
        },
        "parameters": {
            "max_competencia": _competencia_label(max_competencia) if max_competencia else "",
        },
        "outputs": outputs,
        "stages": [
            {
                "id": "load_vehicle_monthly_and_catalog",
                "label": "Carregar base mensal e catalogo",
                "status": "ok" if not vehicle_monthly.empty and not dimension_catalog.empty else "empty",
                "input": f"{vehicle_monthly_path}+{dimension_catalog_path}",
                "output": "memoria:vehicle_monthly+dimension_catalog",
                "rows": int(len(vehicle_monthly) + len(dimension_catalog)),
                "rerun": "python scripts/build_fidc_industry_study.py --report && python scripts/build_fidc_industry_dimensions.py",
            },
            {
                "id": "aggregate_monthly_by_dimension",
                "label": "Agregar series por dimensao",
                "status": "ok" if not monthly.empty else "empty",
                "input": "memoria:vehicle_monthly+dimension_catalog",
                "output": str(output_path),
                "rows": int(len(monthly)),
                "months": quality.get("months", 0),
                "dimensions": quality.get("dimensions", 0),
                "rerun": "python scripts/build_fidc_industry_dimension_monthly.py",
            },
            {
                "id": "build_dimension_value_atlas",
                "label": "Materializar atlas de valores",
                "status": "ok" if atlas_path is not None and atlas_path.exists() else "empty",
                "input": str(output_path),
                "output": str(atlas_path) if atlas_path is not None else "",
                "rows": int(len(atlas)) if atlas is not None else 0,
                "dimensions": atlas_quality.get("dimensions", 0),
                "rerun": "python scripts/build_fidc_industry_dimension_monthly.py",
            },
        ],
        "quality": quality,
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
    plan_path: Path | None = None,
    chunk_plan: pd.DataFrame | None = None,
) -> dict[str, object]:
    if chunk_plan is None:
        chunk_plan = pd.DataFrame()
    quality = document_quality_summary(inventory, chunks, chunk_plan)
    outputs = {
        "document_inventory": file_fingerprint(inventory_path),
        "document_processing_chunks": file_fingerprint(chunks_path),
        "manifest": {"path": str(manifest_path)},
    }
    if plan_path is not None:
        outputs["document_chunk_plan"] = file_fingerprint(plan_path)
    stages = [
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
    ]
    if plan_path is not None:
        stages.append(
            {
                "id": "build_chunk_execution_plan",
                "label": "Plano operacional dos chunks",
                "status": "ok" if not chunk_plan.empty else "empty",
                "input": "document_processing_chunks+document_inventory+document_chunk_actions",
                "output": str(plan_path),
                "rows": int(len(chunk_plan)),
                "rerun": "python scripts/build_fidc_industry_document_chunk_plan.py",
            }
        )
    stages.append(
        {
            "id": "persist_document_inventory",
            "label": "Inventário versionável",
            "status": "ok" if inventory_path.exists() else "empty",
            "input": "memoria:document_inventory",
            "output": str(inventory_path),
            "rows": int(len(inventory)),
            "rerun": "python scripts/build_fidc_industry_documents.py",
        }
    )
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
        "outputs": outputs,
        "stages": stages,
        "quality": quality,
    }


def save_pipeline_manifest(manifest: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def load_pipeline_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
