"""Consolida os dados reproduzíveis consumidos pelo PPTX/XLSX revisados.

O módulo analítico (`build_fidc_revision_analysis.py`) permanece responsável
pelos denominadores, rankings, cobertura e reconciliações. Este script apenas
organiza essas saídas e as bases já versionadas em um payload editorial único;
nenhum percentual do deck é recalculado na camada de PowerPoint.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sys
from typing import Any
import unicodedata

import numpy as np
import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fund_name_display import short_fund_name
from services.industry_intelligence import canonical_provider
from services.industry_closed_offers import build_closed_offers_payload
from services.industry_closed_offer_placement_regime import (
    load_materialized_closed_offer_placement_regime,
)
from services.industry_closed_offer_rankings import build_closed_offer_top15
from services.industry_offer_ticket_distribution import (
    load_materialized_offer_ticket_outputs,
)
from services.industry_fixed_income_offer_comparison import (
    load_materialized_fixed_income_offer_comparison,
)
from services.industry_market_offer_reconciliation import (
    load_materialized_market_offer_reconciliation,
)
from services.industry_issuance_taxonomy import (
    build_issuance_taxonomy,
    build_wide_table,
    write_issuance_taxonomy,
)
from services.industry_bcb_expanded_credit import (
    load_materialized_expanded_credit_history,
)
from services.industry_flagship_curation import (
    build_flagship_curation,
    build_portfolio_curation,
    build_portfolio_flagship_comparison,
)
from services.industry_structural_risk import build_portfolio_structural_risk
from services.industry_portfolio_export import build_industry_portfolio_export
from services.carteira_101_document_audit import (
    load_document_audit_materialization,
)
from services.industry_revision_analysis import (
    BTG_CONTROLLED_FIDCS,
    MARKET_SHARE_EXCLUDED_FUNDS,
)
from services.industry_taxonomy_review import (
    apply_taxonomy_review_overlay,
    assert_taxonomy_review_ledger_matches_audit,
    build_curated_taxonomy_level_history,
    build_curated_type_mix,
    build_historical_top20_taxonomy_review,
    build_taxonomy_review_queue,
    build_top20_by_anbima_type,
    load_taxonomy_review_actions,
    taxonomy_review_audit_digest,
    taxonomy_review_ledger_digest,
    taxonomy_review_summary,
)


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_REFERENCE = "2023-12"
PROVIDER_REFERENCE = "2025-12"
ATLANTICO_CNPJ = "09194841000151"
ANNUAL_GROWTH_PERIODS = (
    (2015, 2018, "CAGR 2015–18", "cagr"),
    (2019, 2020, "2020/19", "yoy"),
    (2021, 2022, "2022/21", "yoy"),
    (2022, 2023, "2023/22", "yoy"),
    (2023, 2024, "2024/23", "yoy"),
    (2024, 2025, "2025/24", "yoy"),
    (2025, 2026, "2026 YTD", "ytd"),
)
EXECUTIVE_OFFER_CONCENTRATION_THRESHOLD_BRL = 500_000_000.0
TOP100_PLUS2_ADDITIONAL_CNPJS = (
    "44302112000172",  # Citi-Bayer Farmtech
    "61669748000176",  # Lavoro Farmtech
)

def _digits(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    raw = str(value).strip()
    numeric_raw = raw.replace(",", ".") if "e" in raw.casefold() else raw
    if re.fullmatch(
        r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",
        numeric_raw,
    ):
        try:
            parsed = Decimal(numeric_raw)
        except InvalidOperation:
            parsed = None
        if (
            parsed is not None
            and parsed.is_finite()
            and parsed == parsed.to_integral_value()
        ):
            raw = str(int(parsed))
    digits = re.sub(r"\D", "", raw)
    return digits.zfill(14) if digits else ""


def _text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _display_fund_name(value: object) -> str:
    text = _text(value)
    upper = text.upper()
    rules = (
        ("SISTEMA PETROBRAS", "FIDC Sistema Petrobras"),
        ("TAPSO", "TAPSO"),
        ("CLOUDWALK BELA", "CloudWalk Bela"),
        ("ITAÚ CRÉDITO PRIVADO", "Itaú Crédito Privado"),
        ("ESPERANZA", "Esperanza"),
        ("BTG PACTUAL CONSIGNADOS II", "BTG Consignados II"),
        ("CLASSE CONSIGNADO PRIVADO DO MT GLOBAL", "MT Global · Consignado Privado"),
        ("PAN AUTO", "PAN Auto"),
        ("AETOS ENERGIA", "Aetos Energia"),
        ("PAGSEGURO I", "PagSeguro I"),
        ("CIELO", "Cielo"),
        ("RIO VERMELHO", "Rio Vermelho NP"),
        ("BTG PACTUAL CONSIGNADOS", "BTG Consignados"),
        ("ALTERNATIVE ASSETS III", "Alternative Assets III"),
        ("NC 2025 I", "NC 2025 I"),
        ("MONEE I", "Monee I"),
        ("PICPAY I", "PicPay I"),
        ("ARTESANAL MASTER", "Artesanal Master"),
        ("MAROBÁ", "Marobá"),
        ("VENDA DE VEÍCULOS", "Venda de Veículos"),
        ("ACR BEM", "ACR BEM"),
        ("HIGH TOWER", "High Tower NP"),
        ("DAY MAXX 2", "Day Maxx 2"),
    )
    for needle, label in rules:
        if needle in upper:
            return label
    return short_fund_name(text, max_length=62).replace("...", "").strip()


def _format_cnpj(value: object) -> str:
    digits = _digits(value)
    if len(digits) != 14:
        return digits
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _fold_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", _text(value))
    return re.sub(r"\s+", " ", "".join(char for char in text if not unicodedata.combining(char))).upper()


def _offer_target_public_shares(offer_cohort: pd.DataFrame) -> pd.DataFrame:
    periods = ["2023 FY", "2024 FY", "2025 FY", "2026 jan-jun"]
    categories = ["Profissional", "Qualificado", "Público Geral", "N/D"]
    source_url = "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/oferta_distribuicao.zip"
    rows: list[dict[str, Any]] = []
    for period in periods:
        frame = offer_cohort[offer_cohort["period_label"].eq(period)].copy()
        total = float(frame["registered_volume_brl"].sum())
        for category in categories:
            mask = (
                frame["target_public"].fillna("N/D").eq(category)
                if category != "N/D"
                else frame["target_public"].fillna("N/D").eq("N/D")
            )
            volume = float(frame.loc[mask, "registered_volume_brl"].sum())
            rows.append(
                {
                    "period_label": period,
                    "target_public": category,
                    "offers": int(mask.sum()),
                    "registered_volume_brl": volume,
                    "share_registered_volume": volume / total if total else float("nan"),
                    "period_registered_volume_brl": total,
                    "source": "CVM, Ofertas Públicas de Distribuição, campo Público_alvo",
                    "source_url": source_url,
                    "source_as_of_date": "2026-07-24",
                    "limitation": (
                        "Público-alvo é elegibilidade regulatória da oferta e não mede a alocação efetiva por pessoa física, "
                        "instituição ou gestora. Profissional e Qualificado incluem pessoas naturais e jurídicas previstas "
                        "na Resolução CVM 30; Público Geral permite varejo, mas não identifica o investidor final."
                    ),
                }
            )
    return pd.DataFrame(rows)


def _reclassification_exports(
    funds: pd.DataFrame,
    *,
    latest: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    current = funds[funds["competencia"].astype(str).eq(latest)].copy()
    current["pl"] = pd.to_numeric(current["pl"], errors="coerce")
    current["is_fic_fidc"] = (
        current["is_fic_fidc"]
        .fillna(False)
        .map(lambda value: str(value).strip().lower() in {"true", "1", "sim"})
    )
    current = current[current["pl"].gt(0) & ~current["is_fic_fidc"]].copy()
    current["cnpj_fundo_formatado"] = current["cnpj_fundo"].map(_format_cnpj)
    base_columns = ["cnpj_fundo_formatado", "denominacao", "pl"]

    anbima = current[current["anbima_tipo"].eq("Outros")].copy()
    anbima["taxonomia_atual"] = (
        anbima["anbima_tipo"].fillna("N/D")
        + " · "
        + anbima["anbima_foco"].fillna("N/D")
    )
    anbima["nova_classificacao_proposta"] = ""
    anbima["fonte"] = anbima["classification_source"].fillna(
        "ANBIMA Data — Fundos 175"
    )
    anbima["data_referencia"] = "ANBIMA dez/25 aplicada à fotografia CVM jun/26"
    anbima["limitacao"] = anbima["classification_warning"].fillna(
        "Classificação cadastral ANBIMA de dez/25; validar fundos novos e alterações posteriores."
    )
    anbima = anbima[
        base_columns
        + [
            "taxonomia_atual",
            "nova_classificacao_proposta",
            "fonte",
            "data_referencia",
            "limitacao",
        ]
    ].sort_values("pl", ascending=False)

    cvm = current[
        current["segmento_principal"].eq("Financeiro")
        &
        current["segmento_financeiro_principal"].eq("Financeiro: outros")
    ].copy()
    cvm["taxonomia_atual"] = "Financeiro · Outros"
    cvm["nova_classificacao_proposta"] = ""
    cvm["fonte"] = "CVM, Informe Mensal FIDC, Tabela II, campo Financeiro: Outros"
    cvm["data_referencia"] = latest
    cvm["limitacao"] = (
        "O rótulo corresponde ao maior subtipo financeiro reportado na Tabela II; fundos com múltiplos tipos "
        "podem exigir leitura da composição completa antes de reclassificação."
    )
    cvm = cvm[
        base_columns
        + [
            "taxonomia_atual",
            "nova_classificacao_proposta",
            "fonte",
            "data_referencia",
            "limitacao",
        ]
    ].sort_values("pl", ascending=False)
    return anbima.reset_index(drop=True), cvm.reset_index(drop=True)


def _card_taxonomy_audit(
    vehicle: pd.DataFrame,
    funds: pd.DataFrame,
    acquiring_curation: pd.DataFrame,
    *,
    latest: str,
    pl_reference: str = "2025-06",
    card_curation: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """List and reconcile every current fund with a Table-II card exposure."""

    current_vehicle = vehicle[vehicle["competencia"].astype(str).eq(latest)].copy()
    current_vehicle["cnpj_fundo"] = current_vehicle.get(
        "cnpj_fundo", current_vehicle.get("cnpj")
    ).map(_digits)
    current_vehicle["cnpj_fundo"] = current_vehicle["cnpj_fundo"].where(
        current_vehicle["cnpj_fundo"].ne(""), current_vehicle["cnpj"].map(_digits)
    )
    current_vehicle["valor_cartao_tabela_ii_brl"] = pd.to_numeric(
        current_vehicle.get("table_ii_cartao_credito_brl"), errors="coerce"
    ).fillna(0.0)
    card_by_fund = current_vehicle.groupby("cnpj_fundo", as_index=False).agg(
        valor_cartao_tabela_ii_brl=("valor_cartao_tabela_ii_brl", "sum"),
        veiculos_classes=("cnpj", "nunique"),
    )

    current = funds[funds["competencia"].astype(str).eq(latest)].copy()
    current["cnpj_fundo"] = current["cnpj_fundo"].map(_digits)
    current = current.drop_duplicates("cnpj_fundo").merge(
        card_by_fund, on="cnpj_fundo", how="left", validate="one_to_one"
    )
    current["valor_cartao_tabela_ii_brl"] = current[
        "valor_cartao_tabela_ii_brl"
    ].fillna(0.0)
    current["segmento_principal"] = current["segmento_principal"].fillna("").astype(str)
    strict = current["segmento_principal"].map(_fold_text).eq("CARTAO DE CREDITO")
    anbima_card = (
        current.get("anbima_tipo", pd.Series("", index=current.index))
        .map(_fold_text)
        .str.contains(r"\bCARTAO(?: DE CREDITO)?\b", regex=True, na=False)
        | current.get("anbima_foco", pd.Series("", index=current.index))
        .map(_fold_text)
        .str.contains(r"\bCARTAO(?: DE CREDITO)?\b", regex=True, na=False)
    )
    secondary = current["valor_cartao_tabela_ii_brl"].gt(0.005)
    selected = current[
        strict | secondary | anbima_card
    ].copy()
    selected["cartao_segmento_principal"] = strict.reindex(selected.index).fillna(False)
    selected["cartao_exposicao_positiva"] = secondary.reindex(selected.index).fillna(False)
    selected["anbima_cartao_explicito"] = anbima_card.reindex(selected.index).fillna(False)

    prior = funds[funds["competencia"].astype(str).eq(pl_reference)].copy()
    prior["cnpj_fundo"] = prior["cnpj_fundo"].map(_digits)
    prior["pl_jun25_brl"] = pd.to_numeric(prior["pl"], errors="coerce")
    prior = prior.groupby("cnpj_fundo", as_index=False)["pl_jun25_brl"].sum(
        min_count=1
    )
    selected = selected.merge(prior, on="cnpj_fundo", how="left", validate="one_to_one")

    latest_period = pd.Period(latest, freq="M")
    fallback_period = str(latest_period - 1)
    selected["pl_competencia_atual_brl"] = pd.to_numeric(
        selected.get("pl"), errors="coerce"
    )
    fallback = funds[funds["competencia"].astype(str).eq(fallback_period)].copy()
    fallback["cnpj_fundo"] = fallback["cnpj_fundo"].map(_digits)
    fallback["pl_competencia_anterior_brl"] = pd.to_numeric(
        fallback["pl"], errors="coerce"
    )
    fallback = fallback.groupby("cnpj_fundo", as_index=False)[
        "pl_competencia_anterior_brl"
    ].sum(min_count=1)
    selected = selected.merge(
        fallback, on="cnpj_fundo", how="left", validate="one_to_one"
    )
    selected["pl_referencia_brl"] = selected["pl_competencia_atual_brl"].where(
        selected["pl_competencia_atual_brl"].notna(),
        selected["pl_competencia_anterior_brl"],
    )
    selected["pl_referencia_competencia"] = np.where(
        selected["pl_competencia_atual_brl"].notna(), latest, fallback_period
    )
    selected["pl_fallback_usado"] = selected["pl_competencia_atual_brl"].isna() & selected[
        "pl_competencia_anterior_brl"
    ].notna()

    curated = set()
    if not acquiring_curation.empty:
        cnpj_column = next(
            (
                column
                for column in ("cnpj14_digits", "cnpj_fundo", "cnpj")
                if column in acquiring_curation
            ),
            "",
        )
        if cnpj_column:
            curated = {_digits(value) for value in acquiring_curation[cnpj_column]}

    strong_rules = (
        ("SEGMENTO MEIOS DE PAGAMENTO", "expressão segmento meios de pagamento"),
        ("UNIDADE DE RECEBIVEIS", "expressão unidade de recebíveis"),
        ("PAGSEGURO", "marca PagSeguro"),
        ("CIELO", "marca Cielo"),
        ("FISERV", "marca Fiserv"),
    )
    indicative_rules = (
        ("PICPAY", "marca PicPay"),
        ("CEA PAY", "marca C&A Pay"),
        ("PAYJOY", "marca PayJoy"),
        ("NATURA PAY", "expressão Natura Pay"),
    )

    def nominal_flag(name: object) -> tuple[str, str]:
        folded = _fold_text(name)
        for needle, reason in strong_rules:
            if needle in folded:
                return "Forte — revisar adquirência", reason
        for needle, reason in indicative_rules:
            if needle in folded:
                return "Indicativo — revisar natureza econômica", reason
        return "Sem indicação nominal específica", ""

    flags = selected["denominacao"].map(nominal_flag)
    selected["flag_nome_adquirencia"] = flags.map(lambda item: item[0])
    selected["motivo_flag_nome"] = flags.map(lambda item: item[1])
    selected["cnpj_fundo_formatado"] = selected["cnpj_fundo"].map(_format_cnpj)
    selected["cnpj_fundo_identificado"] = selected["cnpj_fundo"].str.len().eq(14)
    selected["criterio_inclusao"] = np.select(
        [
            selected["cartao_segmento_principal"],
            selected["cartao_exposicao_positiva"],
            selected["anbima_cartao_explicito"],
        ],
        [
            "Cartão de crédito é o segmento principal da Tabela II",
            "Exposição positiva em Cartão; segmento principal diferente",
            "Cartão aparece explicitamente no Tipo ou Foco ANBIMA",
        ],
        default="Revisão manual",
    )
    selected["categoria_tabela_ii"] = selected["segmento_principal"].replace(
        {"Cartao de credito": "Cartão de crédito", "Servicos": "Serviços"}
    )
    selected["pl_jun25_observavel"] = selected["pl_jun25_brl"].notna()
    selected["ja_curado_como_adquirencia"] = selected["cnpj_fundo"].isin(curated)

    detailed = card_curation.copy() if card_curation is not None else pd.DataFrame()
    if not detailed.empty:
        cnpj_column = next(
            (
                column
                for column in ("cnpj14_digits", "cnpj_fundo", "cnpj")
                if column in detailed
            ),
            "",
        )
        if cnpj_column:
            detailed["cnpj_fundo"] = detailed[cnpj_column].map(_digits)
            detailed = detailed.drop_duplicates("cnpj_fundo", keep="last")
            selected = selected.merge(
                detailed.drop(columns=[cnpj_column], errors="ignore"),
                on="cnpj_fundo",
                how="left",
                validate="one_to_one",
            )

    prior_curation = selected["ja_curado_como_adquirencia"]
    curated_defaults: dict[str, object] = {
        "status_curadoria": np.where(
            prior_curation, "Incluído em Adquirência", "Pendente"
        ),
        "decisao_curadoria": np.where(
            prior_curation,
            "Manter na abertura de Adquirência",
            "Revisão documental pendente",
        ),
        "cedente_originador": "N/D",
        "devedor_sacado": "N/D",
        "instrumento": "N/D",
        "natureza_economica": "N/D",
        "criterio_decisao": np.where(
            prior_curation,
            "Curadoria de adquirência já vigente",
            "Documento primário ainda não concluído",
        ),
        "evidencia_curta": np.where(
            prior_curation,
            "CNPJ já integra a curadoria vigente de Adquirência.",
            "N/D",
        ),
        "fonte_documento": np.where(
            prior_curation, "Curadoria anterior", "N/D"
        ),
        "fonte_data": "N/D",
        "fonte_url": np.where(
            prior_curation,
            "https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM?cnpjFundo="
            + selected["cnpj_fundo"].astype(str),
            "N/D",
        ),
        "confianca": np.where(prior_curation, "Alta", "Pendente"),
        "origem_decisao": np.where(
            prior_curation, "Curadoria anterior", "Curadoria documental"
        ),
        "flag_pf_pj_ccb": "N/D",
    }
    for column, default in curated_defaults.items():
        if column not in selected:
            selected[column] = default
        else:
            missing = selected[column].isna() | selected[column].astype(str).eq("")
            selected.loc[missing, column] = (
                pd.Series(default, index=selected.index).loc[missing]
                if isinstance(default, np.ndarray)
                else default
            )

    selected["consistencia_decisao_reclassificacao"] = np.where(
        selected["ja_curado_como_adquirencia"].eq(
            selected["status_curadoria"].eq("Incluído em Adquirência")
        ),
        "OK",
        "Revisar divergência",
    )
    selected["nota_anbima"] = np.where(
        selected["anbima_cartao_explicito"],
        "Cartão aparece explicitamente no Tipo ou Foco ANBIMA deste registro.",
        "A taxonomia ANBIMA associada ao registro não usa Cartão de crédito como rótulo.",
    )
    output_columns = [
        "cnpj_fundo_formatado",
        "cnpj_fundo_identificado",
        "denominacao",
        "criterio_inclusao",
        "categoria_tabela_ii",
        "valor_cartao_tabela_ii_brl",
        "pl_jun25_brl",
        "pl_jun25_observavel",
        "pl_competencia_atual_brl",
        "pl_competencia_anterior_brl",
        "pl_referencia_brl",
        "pl_referencia_competencia",
        "pl_fallback_usado",
        "anbima_tipo",
        "anbima_foco",
        "classification_tier",
        "classification_status",
        "classification_source",
        "anbima_cartao_explicito",
        "nota_anbima",
        "veiculos_classes",
        "ja_curado_como_adquirencia",
        "flag_nome_adquirencia",
        "motivo_flag_nome",
        "status_curadoria",
        "decisao_curadoria",
        "cedente_originador",
        "devedor_sacado",
        "instrumento",
        "natureza_economica",
        "criterio_decisao",
        "evidencia_curta",
        "fonte_documento",
        "fonte_data",
        "fonte_url",
        "confianca",
        "origem_decisao",
        "flag_pf_pj_ccb",
        "consistencia_decisao_reclassificacao",
    ]
    output = selected[output_columns].sort_values(
        ["pl_referencia_brl", "valor_cartao_tabela_ii_brl", "denominacao"],
        ascending=[False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    output.insert(0, "ordem_materialidade", np.arange(1, len(output) + 1))
    included = output["status_curadoria"].eq("Incluído em Adquirência")
    excluded = output["status_curadoria"].eq("Fora de Adquirência")
    pending = ~(included | excluded)

    def observed_sum(mask: pd.Series, column: str) -> float:
        value = output.loc[mask, column].sum(min_count=1)
        return 0.0 if pd.isna(value) else float(value)

    summary = {
        "competencia_tabela_ii": latest,
        "competencia_pl": pl_reference,
        "fundos_cartao_segmento_principal": int(
            output["criterio_inclusao"].eq(
                "Cartão de crédito é o segmento principal da Tabela II"
            ).sum()
        ),
        "fundos_exposicao_secundaria": int(
            output["criterio_inclusao"].str.startswith("Exposição").sum()
        ),
        "fundos_total": int(len(output)),
        "fundos_pl_observavel": int(output["pl_jun25_observavel"].sum()),
        "pl_jun25_observado_brl": float(output["pl_jun25_brl"].sum(min_count=1)),
        "valor_cartao_tabela_ii_jun26_brl": float(
            output["valor_cartao_tabela_ii_brl"].sum()
        ),
        "fundos_anbima_cartao_explicito": int(
            output["anbima_cartao_explicito"].sum()
        ),
        "fundos_curados_adquirencia": int(output["ja_curado_como_adquirencia"].sum()),
        "competencia_pl_atual": latest,
        "competencia_pl_fallback": fallback_period,
        "fundos_pl_atual_observavel": int(output["pl_competencia_atual_brl"].notna().sum()),
        "fundos_pl_fallback_usado": int(output["pl_fallback_usado"].sum()),
        "pl_referencia_observado_brl": float(output["pl_referencia_brl"].sum(min_count=1)),
        "fundos_incluidos_adquirencia": int(included.sum()),
        "pl_incluido_adquirencia_brl": observed_sum(included, "pl_referencia_brl"),
        "fundos_fora_adquirencia": int(excluded.sum()),
        "pl_fora_adquirencia_brl": observed_sum(excluded, "pl_referencia_brl"),
        "fundos_pendentes_curadoria": int(pending.sum()),
        "pl_pendente_curadoria_brl": observed_sum(pending, "pl_referencia_brl"),
        "divergencias_decisao_reclassificacao": int(
            output["consistencia_decisao_reclassificacao"].ne("OK").sum()
        ),
        "metodologia": (
            "uma linha por CNPJ; fundos com direitos originados no arranjo ou na cadeia "
            "de pagamentos entram em Adquirência; crédito a PF/PJ ou representado por "
            "CCB permanece fora. PL usa a competência atual e recorre ao mês anterior "
            "somente quando o valor atual está ausente"
        ),
    }
    return output, summary


def _acquiring_curation_detail(
    acquiring_curation: pd.DataFrame,
    card_audit: pd.DataFrame,
    funds: pd.DataFrame,
    acquiring_taxonomy: dict[str, Any],
    *,
    latest: str,
) -> pd.DataFrame:
    """Materialize the full acquiring curation, including non-card reporters."""

    columns = [
        "ordem_materialidade",
        "cnpj_fundo_formatado",
        "denominacao",
        "pl_referencia_brl",
        "pl_referencia_competencia",
        "cedente_originador",
        "devedor_sacado",
        "instrumento",
        "natureza_economica",
        "categoria_tabela_ii",
        "valor_cartao_tabela_ii_brl",
        "anbima_tipo",
        "anbima_foco",
        "fonte_url",
        "origem_curadoria",
    ]
    if acquiring_curation.empty:
        return pd.DataFrame(columns=columns)

    latest_period = pd.Period(latest, freq="M")
    fallback_period = str(latest_period - 1)

    current = funds[funds["competencia"].astype(str).eq(latest)].copy()
    current["cnpj_fundo"] = current["cnpj_fundo"].map(_digits)
    current = current.drop_duplicates("cnpj_fundo").set_index("cnpj_fundo")
    fallback = funds[funds["competencia"].astype(str).eq(fallback_period)].copy()
    fallback["cnpj_fundo"] = fallback["cnpj_fundo"].map(_digits)
    fallback = fallback.drop_duplicates("cnpj_fundo").set_index("cnpj_fundo")

    audit = card_audit.copy()
    audit["cnpj_fundo"] = audit["cnpj_fundo_formatado"].map(_digits)
    audit = audit.drop_duplicates("cnpj_fundo").set_index("cnpj_fundo")

    static_rows = pd.DataFrame(acquiring_taxonomy.get("funds") or [])
    if not static_rows.empty:
        static_rows["cnpj_fundo"] = static_rows["cnpj"].map(_digits)
        static_rows = static_rows.drop_duplicates("cnpj_fundo").set_index("cnpj_fundo")

    rows: list[dict[str, Any]] = []
    for curation in acquiring_curation.to_dict("records"):
        cnpj = _digits(curation.get("cnpj14_digits") or curation.get("cnpj14_formatted"))
        live = current.loc[cnpj] if cnpj in current.index else pd.Series(dtype=object)
        prior = fallback.loc[cnpj] if cnpj in fallback.index else pd.Series(dtype=object)
        reviewed = audit.loc[cnpj] if cnpj in audit.index else pd.Series(dtype=object)
        static = (
            static_rows.loc[cnpj]
            if not static_rows.empty and cnpj in static_rows.index
            else pd.Series(dtype=object)
        )

        live_pl = pd.to_numeric(live.get("pl"), errors="coerce")
        prior_pl = pd.to_numeric(prior.get("pl"), errors="coerce")
        if pd.notna(live_pl):
            pl_reference = float(live_pl)
            pl_competence = latest
        elif pd.notna(prior_pl):
            pl_reference = float(prior_pl)
            pl_competence = fallback_period
        else:
            pl_reference = np.nan
            pl_competence = "N/D"

        reviewed_source = _text(reviewed.get("fonte_url"))
        static_source = _text(static.get("primary_document"))
        curation_source = _text(curation.get("source_reference"))
        source_url = next(
            (
                value
                for value in (reviewed_source, static_source, curation_source)
                if value.startswith("http")
            ),
            curation_source or "N/D",
        )
        economic_nature = (
            _text(reviewed.get("natureza_economica"))
            or _text(static.get("economic_nature"))
            or "Direitos ligados a transações de pagamento"
        )
        category = (
            _text(reviewed.get("categoria_tabela_ii"))
            or _text(live.get("segmento_principal"))
            or _text(static.get("table_ii_category"))
            or "N/D"
        )
        rows.append(
            {
                "cnpj_fundo_formatado": _format_cnpj(cnpj),
                "denominacao": (
                    _text(live.get("denominacao"))
                    or _text(curation.get("label"))
                    or _text(static.get("fund"))
                ),
                "pl_referencia_brl": pl_reference,
                "pl_referencia_competencia": pl_competence,
                "cedente_originador": (
                    _text(reviewed.get("cedente_originador"))
                    or _text(static.get("group"))
                    or "N/D"
                ),
                "devedor_sacado": (
                    _text(reviewed.get("devedor_sacado"))
                    or (
                        "Emissores e instituições de pagamento"
                        if not static.empty
                        else "N/D"
                    )
                ),
                "instrumento": (
                    _text(reviewed.get("instrumento"))
                    or "Direitos de transações de pagamento"
                ),
                "natureza_economica": economic_nature,
                "categoria_tabela_ii": category,
                "valor_cartao_tabela_ii_brl": pd.to_numeric(
                    reviewed.get("valor_cartao_tabela_ii_brl"), errors="coerce"
                ),
                "anbima_tipo": (
                    _text(live.get("anbima_tipo"))
                    or _text(reviewed.get("anbima_tipo"))
                    or _text(static.get("anbima_type"))
                    or "N/D"
                ),
                "anbima_foco": (
                    _text(live.get("anbima_foco"))
                    or _text(reviewed.get("anbima_foco"))
                    or _text(static.get("anbima_focus"))
                    or "N/D"
                ),
                "fonte_url": source_url,
                "origem_curadoria": curation_source or "Curadoria documental",
            }
        )

    output = pd.DataFrame(rows).sort_values(
        ["pl_referencia_brl", "denominacao"],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)
    output.insert(0, "ordem_materialidade", np.arange(1, len(output) + 1))
    return output[columns]


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, np.bool_):
        return bool(value)
    if value is pd.NA or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        if "√" in value or re.search(r"(?:Ã|Â)[\u0080-\u00bf]", value):
            raise ValueError(f"texto publicado contém mojibake: {value[:120]}")
        if "\ufffd" in value:
            value = re.sub(
                r"\ufffd+",
                " [trecho ilegível na extração] ",
                value,
            )
            value = re.sub(r"\s+", " ", value).strip()
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.astype(object).where(pd.notna(frame), None)
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in clean.to_dict(orient="records")
    ]


EMISSION_FIELD_AUDIT_COLUMNS = (
    "bloco",
    "tabela",
    "cnpj",
    "emissao_id",
    "fundo",
    "originador",
    "subordinacao_minima",
    "preco_por_tipo_cota",
    "cedente",
    "sacado",
    "fonte_originador_cedente",
    "fonte_subordinacao",
    "fonte_preco",
    "fonte_sacado",
    "status",
)


def _identifier_text(value: object) -> str:
    text = _text(value)
    return re.sub(r"\.0+$", "", text) if re.fullmatch(r"\d+\.0+", text) else text


def _load_emission_field_audit(
    path: Path,
    *,
    latest: str,
    top20_taxonomy_review: pd.DataFrame,
    closed_offer_top15: pd.DataFrame,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"auditoria de campos das emissões ausente: {path}")
    audit = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = set(EMISSION_FIELD_AUDIT_COLUMNS).difference(audit.columns)
    if missing:
        raise ValueError(f"auditoria de emissões sem colunas obrigatórias: {sorted(missing)}")
    audit = audit.loc[:, EMISSION_FIELD_AUDIT_COLUMNS].copy()
    for column in EMISSION_FIELD_AUDIT_COLUMNS:
        audit[column] = audit[column].map(_text)
    audit["cnpj"] = audit["cnpj"].map(_digits).str.zfill(14)
    audit["emissao_id"] = audit["emissao_id"].map(_identifier_text)
    if len(audit) != 180:
        raise ValueError(f"auditoria de emissões deveria conter 180 linhas; contém {len(audit)}")
    expected_block_counts = {"slides 10–13": 120, "slides 21–22": 60}
    if audit.groupby("bloco").size().to_dict() != expected_block_counts:
        raise ValueError("auditoria de emissões não fecha os blocos 120 + 60")
    if not audit["cnpj"].str.fullmatch(r"\d{14}").all():
        raise ValueError("auditoria de emissões contém CNPJ inválido")
    if audit.loc[:, EMISSION_FIELD_AUDIT_COLUMNS].eq("").any().any():
        raise ValueError("auditoria de emissões contém campo vazio; use N/D para lacunas")

    top_audit = audit[audit["bloco"].eq("slides 10–13")]
    if top_audit.duplicated(["tabela", "cnpj"]).any():
        raise ValueError("auditoria dos slides 10–13 contém chave tabela/CNPJ duplicada")
    ranked = top20_taxonomy_review[
        top20_taxonomy_review["competencia"].astype(str).isin((latest, "2025-12"))
        & pd.to_numeric(top20_taxonomy_review["rank_tipo"], errors="coerce").le(15)
    ].copy()
    expected_top_keys = {
        (f"{_text(row.tipo_exibicao)} · {_text(row.competencia)}", _digits(row.cnpj_fundo).zfill(14))
        for row in ranked.itertuples(index=False)
    }
    observed_top_keys = set(zip(top_audit["tabela"], top_audit["cnpj"], strict=True))
    if observed_top_keys != expected_top_keys:
        raise ValueError("auditoria dos slides 10–13 diverge dos rankings materializados")

    offer_audit = audit[audit["bloco"].eq("slides 21–22")]
    if offer_audit.duplicated(["tabela", "emissao_id"]).any():
        raise ValueError("auditoria dos slides 21–22 contém emissão duplicada")
    period_labels = {"2023 FY", "2024 FY", "2025 FY", "2026 jan-jun"}
    offers = closed_offer_top15[
        closed_offer_top15["period_label"].astype(str).isin(period_labels)
        & pd.to_numeric(closed_offer_top15["rank"], errors="coerce").le(15)
    ]
    expected_offer_keys = {
        (
            _text(row.period_label),
            _identifier_text(row.offer_id),
            _digits(row.cnpj_emissor).zfill(14),
        )
        for row in offers.itertuples(index=False)
    }
    observed_offer_keys = set(
        zip(offer_audit["tabela"], offer_audit["emissao_id"], offer_audit["cnpj"], strict=True)
    )
    if observed_offer_keys != expected_offer_keys:
        raise ValueError("auditoria dos slides 21–22 diverge das emissões materializadas")
    return audit


def _load_manual_cnpj_enrichment(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    manual = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {
        "raiz_cnpj_foto",
        "cedente_originador_literal",
        "papel_literal",
        "originador",
        "cedente",
        "sacado_devedor",
        "tipo_recebivel_literal",
        "fonte_imagem",
        "localizacao_imagem",
        "status_transcricao",
    }
    missing = required.difference(manual.columns)
    if missing:
        raise ValueError(
            f"enriquecimento manual por foto sem colunas: {sorted(missing)}"
        )
    manual["raiz_cnpj_foto"] = manual["raiz_cnpj_foto"].map(
        lambda value: re.sub(r"\D", "", str(value)).zfill(8)
    )
    if manual["raiz_cnpj_foto"].duplicated().any():
        raise ValueError("enriquecimento manual contém raiz de CNPJ duplicada")
    manual["status_confirmado"] = manual["status_transcricao"].map(
        lambda value: _fold_text(value).replace("_", " ") == "CONFIRMADO LEGIVEL"
    )
    return manual


def _manual_source_label(row: pd.Series) -> str:
    image = _text(row.get("fonte_imagem")) or "imagem fornecida pelo usuário"
    location = _text(row.get("localizacao_imagem"))
    return f"Comentário manual do usuário — {image}" + (
        f"; {location}" if location else ""
    )


def _apply_manual_enrichment_to_rankings(
    top20_taxonomy_review: pd.DataFrame,
    emission_field_audit: pd.DataFrame,
    manual: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if manual.empty:
        return top20_taxonomy_review, emission_field_audit
    confirmed = manual[manual["status_confirmado"]].copy()
    by_root = {
        row.raiz_cnpj_foto: row
        for row in confirmed.itertuples(index=False)
    }

    ranking = top20_taxonomy_review.copy()
    ranking["manual_enrichment_applied"] = False
    for index, current in ranking.iterrows():
        root = _digits(current.get("cnpj_fundo"))[:8]
        if root not in by_root:
            continue
        row = pd.Series(by_root[root]._asdict())
        literal = _text(row.get("cedente_originador_literal"))
        existing = _text(current.get("cedente_originador"))
        if not literal or (existing and not existing.upper().startswith("N/D")):
            continue
        ranking.at[index, "cedente_originador"] = f"{literal}*"
        ranking.at[index, "cedente_status"] = "comentario_manual_usuario"
        ranking.at[index, "evidencia_cedente"] = _manual_source_label(row)
        ranking.at[index, "limitacao_cedente"] = (
            "* Informação manual transcrita da planilha fotografada; não substitui evidência documental."
        )
        ranking.at[index, "manual_enrichment_applied"] = True

    audit = emission_field_audit.copy()
    audit["cedente_originador_literal"] = "N/D"
    audit["tipo_recebivel_literal"] = "N/D"
    audit["fonte_enriquecimento_manual"] = "N/D"
    for index, current in audit.iterrows():
        root = _digits(current.get("cnpj"))[:8]
        if root not in by_root:
            continue
        row = pd.Series(by_root[root]._asdict())
        source = _manual_source_label(row)
        literal = _text(row.get("cedente_originador_literal"))
        audit.at[index, "cedente_originador_literal"] = (
            f"{literal}*" if literal else "N/D"
        )
        audit.at[index, "tipo_recebivel_literal"] = (
            _text(row.get("tipo_recebivel_literal")) or "N/D"
        )
        audit.at[index, "fonte_enriquecimento_manual"] = source
        applied: list[str] = []
        for source_field, target_field in (
            ("originador", "originador"),
            ("cedente", "cedente"),
            ("sacado_devedor", "sacado"),
        ):
            value = _text(row.get(source_field))
            existing = _text(current.get(target_field))
            if value and (not existing or existing.upper().startswith("N/D")):
                audit.at[index, target_field] = f"{value}*"
                applied.append(target_field)
        if applied:
            audit.at[index, "fonte_originador_cedente"] = source
            if "sacado" in applied:
                audit.at[index, "fonte_sacado"] = source
            audit.at[index, "status"] = (
                "Complemento manual marcado com *; lacunas documentais restantes preservadas como N/D"
            )
    return ranking, audit


def _first_documented(*values: object) -> str:
    for value in values:
        text = _text(value)
        if text and not text.upper().startswith("N/D"):
            return text
    return "N/D"


def _clean_top100_field(value: object) -> str:
    """Return a publishable entity/lastro value, excluding raw regex excerpts."""

    text = _text(value)
    if not text or text.upper().startswith("N/D"):
        return "N/D"
    folded = _fold_text(text)
    gap_tokens = (
        "NAO LOCALIZADO",
        "NAO LOCALIZADA",
        "AUSENCIA DE",
        "SEM TRECHO CITAVEL",
        "NENHUM DOCUMENTO PRIMARIO",
    )
    if any(token in folded for token in gap_tokens):
        return "N/D"
    # Historical regex-context rows can begin with a page marker and contain a
    # document fragment rather than a resolved entity. They remain available in
    # the evidence/source columns, but never become a party or lastro field.
    if re.match(r"^p\.\s*\d+\s*:", text, flags=re.IGNORECASE):
        return "N/D"
    return text


def _first_clean_top100_field(*values: object) -> str:
    for value in values:
        cleaned = _clean_top100_field(value)
        if cleaned != "N/D":
            return cleaned
    return "N/D"


def _load_top100_plus2_curation(path: Path) -> pd.DataFrame:
    """Load the two documentary 2026 additions to the global Top 100 export."""

    if not path.exists():
        raise ValueError(f"curadoria Top 100 + 2 ausente: {path}")
    frame = pd.read_csv(
        path,
        dtype={
            "cnpj": "string",
            "oferta_id": "string",
            "processo_cvm": "string",
            "documento_regulamento_id": "string",
            "documento_emissao_id": "string",
        },
        low_memory=False,
    )
    frame["cnpj"] = frame.get("cnpj", pd.Series(dtype="object")).map(_digits)
    expected = set(TOP100_PLUS2_ADDITIONAL_CNPJS)
    actual = set(frame["cnpj"].dropna().astype(str))
    if len(frame) != 2 or actual != expected or frame["cnpj"].nunique() != 2:
        raise ValueError(
            "curadoria Top 100 + 2 deve conter somente Citi-Bayer e Lavoro, "
            f"um registro por CNPJ; encontrados {sorted(actual)}"
        )
    required = {
        "inclusao_criterio",
        "oferta_id",
        "processo_cvm",
        "data_encerramento",
        "preco_cota_emissao_brl",
        "cedente_originador",
        "sacado_devedor",
        "tipo_recebivel",
        "taxonomia_funcional_n1",
        "taxonomia_funcional_n2",
        "minimo_subordinacao_estrutural",
        "natureza_minimo",
        "documento_regulamento_id",
        "documento_emissao_id",
        "pagina_clausula",
        "evidencia",
        "fonte_regulamento",
        "fonte_emissao",
        "status_cobertura",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            "curadoria Top 100 + 2 sem colunas obrigatórias: "
            + ", ".join(sorted(missing))
        )
    for column in required.difference({"minimo_subordinacao_estrutural"}):
        gaps = frame[column].fillna("").astype(str).str.strip().eq("")
        if gaps.any():
            cnpjs = ", ".join(frame.loc[gaps, "cnpj"].astype(str))
            raise ValueError(
                f"curadoria Top 100 + 2 contém lacuna indevida em {column}: {cnpjs}"
            )
    frame["minimo_subordinacao_estrutural"] = pd.to_numeric(
        frame["minimo_subordinacao_estrutural"], errors="coerce"
    )
    if frame["minimo_subordinacao_estrutural"].isna().any():
        raise ValueError("curadoria Top 100 + 2 sem mínimo estrutural documental")
    return frame


def _build_top100_fidcs_middle_market(
    *,
    funds: pd.DataFrame,
    latest: str,
    actions: pd.DataFrame,
    top20_taxonomy_review: pd.DataFrame,
    profiles: pd.DataFrame,
    manual_enrichment: pd.DataFrame,
    additional_2026: pd.DataFrame,
    vehicle: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Rank the global Top 100 and append two documented 2026 issuances."""

    current = funds[funds["competencia"].astype(str).eq(latest)].copy()
    current["cnpj_fundo"] = current["cnpj_fundo"].map(_digits)
    fic_column = "is_fic" if "is_fic" in current.columns else "is_fic_fidc"
    fic = current.get(fic_column, pd.Series(False, index=current.index))
    fic = fic.map(
        lambda value: value
        if isinstance(value, (bool, np.bool_))
        else str(value).strip().lower() in {"1", "true", "sim", "yes"}
    )
    current = current[~fic.fillna(False)].copy()
    current["pl"] = pd.to_numeric(current.get("pl"), errors="coerce")
    current = apply_taxonomy_review_overlay(current, actions)
    denominator = current["pl"].sum(min_count=1)
    ranked = current.sort_values(
        ["pl", "cnpj_fundo"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    ranked["rank_geral"] = range(1, len(ranked) + 1)
    ranked["share_pl_ex_fic"] = ranked["pl"].div(denominator)
    top100 = ranked.head(100).copy()
    if len(top100) != 100 or top100["cnpj_fundo"].nunique() != 100:
        raise ValueError("Top 100 geral deve conter 100 CNPJs únicos")
    additions = ranked[
        ranked["cnpj_fundo"].isin(TOP100_PLUS2_ADDITIONAL_CNPJS)
    ].copy()
    if len(additions) != 2 or additions["cnpj_fundo"].nunique() != 2:
        raise ValueError("Citi-Bayer e Lavoro devem existir na competência publicada")
    overlap = set(top100["cnpj_fundo"]).intersection(additions["cnpj_fundo"])
    if overlap:
        raise ValueError(
            "inclusões adicionais já pertencem ao Top 100 e duplicariam o export: "
            + ", ".join(sorted(overlap))
        )
    top100["inclusao_criterio"] = "Top 100 por PL ex-FIC"
    additional_curated = additional_2026.rename(
        columns={
            column: f"{column}_curadoria"
            for column in additional_2026.columns
            if column not in {"cnpj", "inclusao_criterio"}
        }
    )
    additions = additions.merge(
        additional_curated,
        left_on="cnpj_fundo",
        right_on="cnpj",
        how="left",
        validate="one_to_one",
        suffixes=("", "_curadoria"),
    ).drop(columns=["cnpj"], errors="ignore")
    top = pd.concat([top100, additions], ignore_index=True, sort=False)
    top["ordem_exportacao"] = range(1, 103)

    current_vehicle = vehicle[
        vehicle["competencia"].astype(str).eq(latest)
    ].copy()
    current_vehicle["cnpj_fundo"] = current_vehicle.get(
        "cnpj_fundo", current_vehicle.get("cnpj", pd.Series(dtype="object"))
    ).map(_digits)
    current_vehicle["subordinacao_atual_pl"] = pd.to_numeric(
        current_vehicle.get("subordinacao_pct"), errors="coerce"
    )
    current_vehicle = current_vehicle.drop_duplicates("cnpj_fundo", keep="last")
    top = top.merge(
        current_vehicle[["cnpj_fundo", "subordinacao_atual_pl"]],
        on="cnpj_fundo",
        how="left",
        validate="one_to_one",
    )

    latest_review = top20_taxonomy_review[
        top20_taxonomy_review.get(
            "competencia", pd.Series("", index=top20_taxonomy_review.index)
        ).astype(str).eq(latest)
    ].copy()
    latest_review["cnpj_fundo"] = latest_review.get(
        "cnpj_fundo", pd.Series(dtype="object")
    ).map(_digits)
    latest_review = latest_review.drop_duplicates("cnpj_fundo", keep="last")
    review_fields = [
        "cnpj_fundo",
        "cedente_originador",
        "cedente_status",
        "evidencia_cedente",
        "limitacao_cedente",
        "regulamento_id",
        "regulamento_url",
        "pagina_clausula",
        "taxonomia_funcional_n1_curada",
        "taxonomia_funcional_n2_curada",
    ]
    top = top.merge(
        latest_review[
            [column for column in review_fields if column in latest_review.columns]
        ],
        on="cnpj_fundo",
        how="left",
        validate="one_to_one",
        suffixes=("", "_review"),
    )

    profile = profiles.copy()
    if not profile.empty:
        profile["cnpj_fundo"] = profile["cnpj_fundo"].map(_digits)
        profile = profile.drop_duplicates("cnpj_fundo", keep="last")
        top = top.merge(
            profile[
                [
                    column
                    for column in (
                        "cnpj_fundo",
                        "cedente_originador",
                        "sacado_devedor",
                        "natureza_recebiveis",
                        "fonte",
                        "evidencia",
                        "documentos_primarios_ids",
                        "status_curadoria",
                    )
                    if column in profile.columns
                ]
            ].rename(
                columns={
                    "cedente_originador": "cedente_originador_profile",
                    "fonte": "fonte_profile",
                    "evidencia": "evidencia_profile",
                }
            ),
            on="cnpj_fundo",
            how="left",
            validate="one_to_one",
        )

    confirmed_manual = manual_enrichment[
        manual_enrichment.get(
            "status_confirmado", pd.Series(False, index=manual_enrichment.index)
        ).fillna(False).astype(bool)
    ].copy()
    manual_by_root = {
        str(row.raiz_cnpj_foto): row
        for row in confirmed_manual.itertuples(index=False)
    }

    effective_actions = actions[
        actions.get("status", pd.Series("", index=actions.index))
        .astype(str)
        .str.strip()
        .eq("aprovado")
    ].copy()
    effective_actions["cnpj_fundo"] = effective_actions.get(
        "cnpj_fundo", pd.Series(dtype="object")
    ).map(_digits)
    effective_actions["_updated"] = pd.to_datetime(
        effective_actions.get("updated_at_utc"), errors="coerce", utc=True
    )
    effective_actions = (
        effective_actions.sort_values(["_updated", "competencia_referencia"])
        .drop_duplicates("cnpj_fundo", keep="last")
        .set_index("cnpj_fundo")
    )

    output_rows: list[dict[str, object]] = []
    for row in top.to_dict(orient="records"):
        cnpj = _digits(row.get("cnpj_fundo"))
        action = (
            effective_actions.loc[cnpj].to_dict()
            if cnpj in effective_actions.index
            else {}
        )
        manual = manual_by_root.get(cnpj[:8])
        manual_values = manual._asdict() if manual is not None else {}
        action_source = _text(action.get("fonte_documental"))
        action_is_manual = "COMENTARIO" in _fold_text(action_source)
        action_cedente = (
            action.get("cedente_originador_expresso") if action_is_manual else None
        )
        curated_addition = cnpj in TOP100_PLUS2_ADDITIONAL_CNPJS
        cedente = _first_clean_top100_field(
            row.get("cedente_originador_curadoria")
            if curated_addition
            else None,
            row.get("cedente_originador_profile"),
            manual_values.get("cedente_originador_literal"),
            action_cedente,
        )
        sacado = _first_clean_top100_field(
            row.get("sacado_devedor_curadoria") if curated_addition else None,
            row.get("sacado_devedor"),
            manual_values.get("sacado_devedor"),
        )
        documentary_receivable = _first_clean_top100_field(
            row.get("tipo_recebivel_curadoria") if curated_addition else None,
            row.get("natureza_recebiveis"),
            manual_values.get("tipo_recebivel_literal"),
        )
        receivable = _first_clean_top100_field(
            documentary_receivable,
            row.get("taxonomia_funcional_n2_curada"),
            action.get("taxonomia_funcional_n2"),
        )
        functional_n1 = _first_documented(
            row.get("taxonomia_funcional_n1_curadoria")
            if curated_addition
            else None,
            row.get("taxonomia_funcional_n1_curada"),
            action.get("taxonomia_funcional_n1"),
        )
        functional_n2 = _first_documented(
            row.get("taxonomia_funcional_n2_curadoria")
            if curated_addition
            else None,
            row.get("taxonomia_funcional_n2_curada"),
            action.get("taxonomia_funcional_n2"),
        )
        evidence = _first_documented(
            row.get("evidencia_curadoria") if curated_addition else None,
            row.get("evidencia_profile"),
            row.get("evidencia_cedente"),
            action.get("evidencia"),
            manual_values.get("observacao"),
        )
        source = _first_documented(
            row.get("fonte_regulamento_curadoria") if curated_addition else None,
            row.get("fonte_emissao_curadoria") if curated_addition else None,
            row.get("fonte_profile"),
            action.get("fonte_documental"),
            row.get("regulamento_url"),
            manual_values.get("fonte_imagem"),
            row.get("classification_source"),
        )
        combined = _fold_text(
            " | ".join(
                value
                for value in (
                    cedente,
                    sacado,
                    receivable,
                    functional_n1,
                    functional_n2,
                    evidence,
                )
                if value != "N/D"
            )
        )
        direct = any(
            token in combined for token in ("MIDDLE MARKET", "CREDITO PME", " PME")
        )
        corporate = functional_n1 == "Crédito PJ" or any(
            token in combined
            for token in (
                "CREDITO PJ",
                "CAPITAL DE GIRO",
                "CCB",
                "NOTA COMERCIAL",
                "DEBENTURE",
                "RECEBIVEIS COMERCIAIS",
                "RISCO SACADO",
                "FORNECEDOR",
            )
        )
        if direct:
            mm_status = "Rótulo documental PME / Middle Market; porte N/D"
            mm_flag: object = None
            mm_reason = (
                "A fonte usa PME ou Middle Market, mas a base não documenta receita, ativo ou outro critério de porte do tomador."
            )
        elif corporate:
            mm_status = "Indício de crédito corporativo; porte N/D"
            mm_flag = None
            mm_reason = (
                "O lastro é compatível com crédito corporativo tradicional, mas a base não documenta o porte do tomador."
            )
        elif all(value == "N/D" for value in (cedente, sacado, receivable, functional_n1, functional_n2)):
            mm_status = "N/D — dados insuficientes"
            mm_flag = None
            mm_reason = "Cedente, sacado e tipo de recebível não foram localizados."
        else:
            mm_status = "Sem indício documental de Middle Market"
            mm_flag = False
            mm_reason = "A evidência disponível aponta outro tipo de risco ou não traz crédito corporativo."
        output_rows.append(
            {
                "ordem_exportacao": int(row["ordem_exportacao"]),
                "rank_geral": int(row["rank_geral"]),
                "inclusao_criterio": _first_documented(
                    row.get("inclusao_criterio")
                ),
                "cnpj": cnpj,
                "cnpj_formatado": _format_cnpj(cnpj),
                "nome_fundo": _text(row.get("denominacao")) or "N/D",
                "pl_brl": row.get("pl"),
                "share_pl_ex_fic": row.get("share_pl_ex_fic"),
                "subordinacao_atual_pl": row.get("subordinacao_atual_pl"),
                "minimo_subordinacao_junior": row.get(
                    "minimo_subordinacao_junior_curadoria"
                ),
                "minimo_subordinacao_estrutural": row.get(
                    "minimo_subordinacao_estrutural_curadoria"
                ),
                "natureza_minimo": _first_documented(
                    row.get("natureza_minimo_curadoria")
                ),
                "preco_cota_emissao_brl": row.get(
                    "preco_cota_emissao_brl_curadoria"
                ),
                "oferta_id": _first_documented(row.get("oferta_id_curadoria")),
                "processo_cvm": _first_documented(
                    row.get("processo_cvm_curadoria")
                ),
                "data_registro": _first_documented(
                    row.get("data_registro_curadoria")
                ),
                "data_encerramento": _first_documented(
                    row.get("data_encerramento_curadoria")
                ),
                "volume_registrado_brl": row.get(
                    "volume_registrado_brl_curadoria"
                ),
                "quantidade_registrada": row.get(
                    "quantidade_registrada_curadoria"
                ),
                "quantidade_colocada": row.get(
                    "quantidade_colocada_curadoria"
                ),
                "montante_encerrado_brl": row.get(
                    "montante_encerrado_brl_curadoria"
                ),
                "cedente_originador": cedente,
                "sacado_devedor": sacado,
                "tipo_recebivel": receivable,
                "tipo_anbima_oficial": _first_documented(row.get("anbima_tipo_oficial"), row.get("anbima_tipo")),
                "foco_anbima_oficial": _first_documented(row.get("anbima_foco_oficial"), row.get("anbima_foco")),
                "tipo_analitico": _first_documented(row.get("anbima_tipo_curado")),
                "foco_analitico": _first_documented(row.get("anbima_foco_curado")),
                "taxonomia_funcional_n1": functional_n1,
                "taxonomia_funcional_n2": functional_n2,
                "middle_market_flag": mm_flag,
                "middle_market_status": mm_status,
                "middle_market_justificativa": mm_reason,
                "evidencia": evidence,
                "fonte": source,
                "documento_id": _first_documented(
                    row.get("documento_regulamento_id_curadoria")
                    if curated_addition
                    else None,
                    row.get("documentos_primarios_ids"),
                    action.get("documento_id"),
                    row.get("regulamento_id"),
                ),
                "documento_emissao_id": _first_documented(
                    row.get("documento_emissao_id_curadoria")
                ),
                "pagina_clausula": _first_documented(
                    row.get("pagina_clausula_curadoria")
                    if curated_addition
                    else None,
                    action.get("pagina_clausula"), row.get("pagina_clausula")
                ),
                "fonte_regulamento": _first_documented(
                    row.get("fonte_regulamento_curadoria")
                ),
                "fonte_emissao": _first_documented(
                    row.get("fonte_emissao_curadoria")
                ),
                "status_cobertura": _first_documented(
                    row.get("status_cobertura_curadoria")
                    if curated_addition
                    else None,
                    "documentado — parte ou lastro identificado"
                    if source != "N/D"
                    and any(
                        value != "N/D"
                        for value in (cedente, sacado, documentary_receivable)
                    )
                    else (
                        "taxonomia disponível — partes e lastro documental N/D"
                        if any(value != "N/D" for value in (functional_n1, functional_n2))
                        else "N/D — partes, lastro e taxonomia não localizados"
                    )
                ),
            }
        )
    output = pd.DataFrame(output_rows).sort_values("ordem_exportacao").reset_index(drop=True)
    direct_mask = output["middle_market_status"].str.startswith(
        "Rótulo documental", na=False
    )
    corporate_mask = output["middle_market_status"].eq(
        "Indício de crédito corporativo; porte N/D"
    )
    summary = {
        "fundos": 102,
        "top100_fundos": 100,
        "adicionais_2026_fundos": 2,
        "competencia": latest,
        "top100_pl_brl": float(
            pd.to_numeric(
                output.loc[output["ordem_exportacao"].le(100), "pl_brl"],
                errors="coerce",
            ).sum()
        ),
        "top100_share_pl_ex_fic": float(
            pd.to_numeric(
                output.loc[
                    output["ordem_exportacao"].le(100), "share_pl_ex_fic"
                ],
                errors="coerce",
            ).sum()
        ),
        "top100_plus2_pl_brl": float(
            pd.to_numeric(output["pl_brl"], errors="coerce").sum()
        ),
        "top100_plus2_share_pl_ex_fic": float(
            pd.to_numeric(output["share_pl_ex_fic"], errors="coerce").sum()
        ),
        "middle_market_rotulo_documental_fundos": int(direct_mask.sum()),
        "middle_market_rotulo_documental_pl_brl": float(
            pd.to_numeric(output.loc[direct_mask, "pl_brl"], errors="coerce").sum()
        ),
        "credito_corporativo_indicio_fundos": int(corporate_mask.sum()),
        "credito_corporativo_indicio_pl_brl": float(
            pd.to_numeric(output.loc[corporate_mask, "pl_brl"], errors="coerce").sum()
        ),
        "metodologia": (
            "A menção PME ou Middle Market é publicada como rótulo documental com porte N/D. "
            "CCB, nota comercial, recebíveis comerciais, risco sacado e fornecedores geram apenas indício de crédito corporativo; porte permanece N/D."
        ),
    }
    return output, summary


def _pt_number(value: object, decimals: int = 1) -> str:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return "N/D"
    rendered = f"{float(parsed):,.{decimals}f}"
    return rendered.replace(",", "#").replace(".", ",").replace("#", ".")


def _pt_integer(value: object) -> str:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return "N/D"
    return f"{int(parsed):,}".replace(",", ".")


def _pt_pct(value: object, decimals: int = 1) -> str:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return "N/D"
    return f"{_pt_number(float(parsed) * 100, decimals)}%"


def _pt_brl_mi(value: object, decimals: int = 1) -> str:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return "R$ N/D"
    return f"R$ {_pt_number(float(parsed) / 1e6, decimals)} mi"


def _pt_brl_bi(value: object, decimals: int = 1) -> str:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return "R$ N/D"
    return f"R$ {_pt_number(float(parsed) / 1e9, decimals)} bi"


def _offer_ticket_concentration_2026(
    cohort: pd.DataFrame,
    *,
    threshold_brl: float = EXECUTIVE_OFFER_CONCENTRATION_THRESHOLD_BRL,
) -> dict[str, Any]:
    """Measure the explicit R$500m+ tail in the Jan-Jun 2026 offer cohort."""

    required = {
        "period_label",
        "period_start",
        "period_end",
        "numero_requerimento",
        "registered_volume_brl",
    }
    missing = sorted(required.difference(cohort.columns))
    if missing:
        raise ValueError(
            "coorte de tickets sem campos obrigatórios: " + ", ".join(missing)
        )
    if threshold_brl <= 0:
        raise ValueError("limiar de concentração de ofertas deve ser positivo")

    scoped = cohort[cohort["period_end"].astype(str).eq("2026-06-30")].copy()
    if scoped.empty:
        raise ValueError("coorte de ofertas jan-jun/26 ausente")
    scoped["registered_volume_brl"] = pd.to_numeric(
        scoped["registered_volume_brl"], errors="coerce"
    )
    if scoped["registered_volume_brl"].isna().any() or scoped[
        "registered_volume_brl"
    ].le(0).any():
        raise ValueError("coorte jan-jun/26 contém ticket ausente ou não positivo")
    if scoped["numero_requerimento"].astype(str).duplicated().any():
        raise ValueError("coorte jan-jun/26 contém Numero_Requerimento duplicado")

    large = scoped[scoped["registered_volume_brl"].ge(threshold_brl)].copy()
    universe_offers = int(scoped["numero_requerimento"].nunique())
    universe_volume = float(scoped["registered_volume_brl"].sum())
    large_offers = int(large["numero_requerimento"].nunique())
    large_volume = float(large["registered_volume_brl"].sum())
    largest = scoped.sort_values(
        ["registered_volume_brl", "numero_requerimento"],
        ascending=[False, True],
        kind="stable",
    ).iloc[0]

    def singleton(column: str) -> Any:
        if column not in scoped:
            return None
        values = scoped[column].dropna().unique().tolist()
        if len(values) > 1:
            raise ValueError(
                f"metadado {column} divergente na coorte de ofertas jan-jun/26"
            )
        return _json_value(values[0]) if values else None

    return {
        "period_label": singleton("period_label"),
        "period_start": singleton("period_start"),
        "period_end": singleton("period_end"),
        "threshold_operator": ">=",
        "threshold_registered_volume_brl": float(threshold_brl),
        "ticket_bucket": "≥ R$ 500 mi",
        "rule": "Valor_Total_Registrado >= R$ 500 milhões",
        "methodology": (
            "coorte fixa por Data_Encerramento; aplicação de limiar absoluto, "
            "sem seleção top-N"
        ),
        "universe_closed_offers": universe_offers,
        "universe_registered_volume_brl": universe_volume,
        "large_offer_closed_offers": large_offers,
        "large_offer_share": large_offers / universe_offers,
        "large_offer_registered_volume_brl": large_volume,
        "large_offer_registered_volume_share": large_volume / universe_volume,
        "large_offer_requirement_numbers": large.sort_values(
            ["registered_volume_brl", "numero_requerimento"],
            ascending=[False, True],
            kind="stable",
        )["numero_requerimento"].astype(str).tolist(),
        "largest_offer_requirement_number": str(largest["numero_requerimento"]),
        "largest_offer_issuer_cnpj": _digits(largest.get("cnpj_emissor")),
        "largest_offer_issuer_name": _text(largest.get("nome_emissor")),
        "largest_offer_registered_volume_brl": float(
            largest["registered_volume_brl"]
        ),
        "largest_offer_registered_volume_share": float(
            largest["registered_volume_brl"] / universe_volume
        ),
        "source_dataset": singleton("source_dataset"),
        "source_url": singleton("source_url"),
        "source_as_of_date": singleton("source_as_of_date"),
        "source_archive_sha256": singleton("source_archive_sha256"),
        "scope": singleton("scope"),
        "deduplication": singleton("deduplication"),
    }


def _executive_conclusions(
    *,
    latest: str,
    conclusion_metrics: dict[str, Any],
    offer_concentration: dict[str, Any],
    closed_annual: list[dict[str, Any]],
    closed_jan_june: list[dict[str, Any]],
    provider_concentration_history: list[dict[str, Any]],
    provider_historical_ranking: pd.DataFrame,
    qi_legacy_attribution: pd.DataFrame,
    reag_admin_summary: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build concise audience-facing conclusions from published raw metrics."""

    latest_period = pd.Period(latest, freq="M")
    month_labels = (
        "jan",
        "fev",
        "mar",
        "abr",
        "mai",
        "jun",
        "jul",
        "ago",
        "set",
        "out",
        "nov",
        "dez",
    )
    latest_label = (
        f"{month_labels[latest_period.month - 1]}/{str(latest_period.year)[-2:]}"
    )
    current_offer = next(
        (row for row in closed_annual if int(row.get("year", 0)) == 2026), {}
    )
    comparable = {
        int(row.get("year", 0)): row
        for row in closed_jan_june
        if row.get("year") is not None
    }
    offer_2024 = comparable.get(2024, {})
    offer_2025 = comparable.get(2025, {})
    offer_2026 = comparable.get(2026, current_offer)

    def ratio(numerator: object, denominator: object) -> float | None:
        top = pd.to_numeric(numerator, errors="coerce")
        bottom = pd.to_numeric(denominator, errors="coerce")
        if pd.isna(top) or pd.isna(bottom) or float(bottom) == 0:
            return None
        return float(top) / float(bottom)

    def provider_row(role: str, participant: str) -> dict[str, Any]:
        if provider_historical_ranking.empty:
            return {}
        scoped = provider_historical_ranking[
            provider_historical_ranking["competencia"].astype(str).eq(latest)
            & provider_historical_ranking["papel"].astype(str).eq(role)
            & provider_historical_ranking["participante"].map(_fold_text).eq(
                _fold_text(participant)
            )
        ]
        return (
            {str(key): _json_value(value) for key, value in scoped.iloc[0].items()}
            if not scoped.empty
            else {}
        )

    concentration = {
        str(row.get("papel")): row
        for row in provider_concentration_history
        if str(row.get("competencia")) == latest
    }
    btg_manager = provider_row("gestor", "BTG Pactual")
    ot_manager = provider_row("gestor", "Oliveira Trust")

    qi_legacy = {}
    if not qi_legacy_attribution.empty and "attribution" in qi_legacy_attribution:
        scoped = qi_legacy_attribution[
            qi_legacy_attribution["attribution"].astype(str).eq("legacy_singulare")
        ]
        qi_legacy = _single_record(scoped)
    reag = _single_record(reag_admin_summary)
    mean_ticket = current_offer.get("mean_registered_ticket_brl")
    median_ticket = current_offer.get("median_registered_ticket_brl")
    median_to_mean = ratio(median_ticket, mean_ticket)
    pf_share = current_offer.get("natural_person_placed_volume_share")
    current_volume = offer_2026.get("registered_volume_brl")
    prior_volume = offer_2025.get("registered_volume_brl")
    volume_2024 = offer_2024.get("registered_volume_brl")
    growth_2025 = (
        ratio(current_volume, prior_volume) - 1
        if ratio(current_volume, prior_volume) is not None
        else None
    )
    growth_2024 = (
        ratio(current_volume, volume_2024) - 1
        if ratio(current_volume, volume_2024) is not None
        else None
    )
    largest_offer_name = _display_fund_name(
        offer_concentration.get("largest_offer_issuer_name")
    )
    largest_offer_volume = offer_concentration.get(
        "largest_offer_registered_volume_brl"
    )
    largest_offer_share = offer_concentration.get(
        "largest_offer_registered_volume_share"
    )
    incremental_volume = (
        float(current_volume) - float(prior_volume)
        if pd.notna(pd.to_numeric(current_volume, errors="coerce"))
        and pd.notna(pd.to_numeric(prior_volume, errors="coerce"))
        else None
    )
    largest_offer_share_increment = ratio(largest_offer_volume, incremental_volume)
    growth_ex_largest_offer = (
        ratio(float(current_volume) - float(largest_offer_volume), prior_volume) - 1
        if pd.notna(pd.to_numeric(current_volume, errors="coerce"))
        and pd.notna(pd.to_numeric(largest_offer_volume, errors="coerce"))
        and ratio(float(current_volume) - float(largest_offer_volume), prior_volume)
        is not None
        else None
    )

    cielo_share_migrated = ratio(
        conclusion_metrics.get("admin_transition_2024_2025_cielo_pl_brl"),
        conclusion_metrics.get("admin_transition_2024_2025_changed_pl_brl"),
    )
    admin_top10 = concentration.get("administrador", {}).get("top10_share")
    manager_top10 = concentration.get("gestor", {}).get("top10_share")
    custody_top10 = concentration.get("custodiante", {}).get("top10_share")
    btg_cohort_combo_share_total = ratio(
        conclusion_metrics.get("btg_bank_cohort_combo_pl_brl"),
        conclusion_metrics.get("btg_combo_tres_funcoes_pl_brl"),
    )

    conclusions = [
        {
            "order": 1,
            "title": "Distribuição após a RCVM 175 segue institucional e concentrada",
            "bullets": [
                (
                    f"A mediana foi de {_pt_brl_mi(median_ticket)}, apenas "
                    f"{_pt_pct(median_to_mean, 0)} do ticket médio de "
                    f"{_pt_brl_mi(mean_ticket)}; "
                    f"{_pt_integer(offer_concentration.get('large_offer_closed_offers'))} "
                    "ofertas de R$ 500 mi ou mais — "
                    f"{_pt_pct(offer_concentration.get('large_offer_share'))} do total — "
                    f"concentraram {_pt_pct(offer_concentration.get('large_offer_registered_volume_share'))} do volume."
                ),
                (
                    f"Pessoas físicas responderam por apenas {_pt_pct(pf_share)} do volume "
                    "colocado estimado; entre os fundos com PL ≥ R$ 200 mi, "
                    f"{_pt_pct(conclusion_metrics.get('holder_ge_200m_share_fundos_ate_10_contas'))} "
                    "têm até dez contas."
                ),
            ],
        },
        {
            "order": 2,
            "title": "Verticalização define o modelo operacional da indústria",
            "bullets": [
                (
                    "Administração e custódia estão no mesmo conglomerado em "
                    f"{_pt_pct(conclusion_metrics.get('admin_custodia_juntas_share_pl'))} do PL: "
                    "nove em cada dez reais da indústria."
                ),
                (
                    "Monoestruturas, com as três funções no mesmo grupo, já concentram "
                    f"{_pt_pct(conclusion_metrics.get('monoestrutura_share_pl'))} do PL."
                ),
            ],
        },
        {
            "order": 3,
            "title": "Escala independente está concentrada em poucas plataformas",
            "bullets": [
                (
                    "QI Tech lidera administração e está em empate técnico com o BTG em "
                    "custódia; "
                    f"{_pt_pct(qi_legacy.get('share_admin_group'), 0)} de sua base administrativa "
                    "em dez/24 veio do legado Singulare."
                ),
                (
                    "Oliveira Trust é a terceira maior gestora, com "
                    f"{_pt_brl_bi(ot_manager.get('pl_brl'))}; na coorte CBSF/Reag, "
                    f"{_pt_pct(reag.get('migrated_share_current'))} do PL continuante já havia "
                    f"migrado de administrador até {latest_label}."
                ),
            ],
        },
        {
            "order": 4,
            "title": "Movimentação de administradores foi baixa e concentrada",
            "bullets": [
                (
                    f"Apenas {_pt_pct(conclusion_metrics.get('admin_transition_2024_2025_changed_share_pl'))} "
                    "do PL comparável trocou de administrador entre dez/24 e dez/25: "
                    f"{_pt_brl_bi(conclusion_metrics.get('admin_transition_2024_2025_changed_pl_brl'))} "
                    f"em {_pt_integer(conclusion_metrics.get('admin_transition_2024_2025_changed_funds'))} fundos."
                ),
                (
                    "Os dois FIDCs Cielo responderam sozinhos por "
                    f"{_pt_pct(cielo_share_migrated, 0)} do volume migrado, com "
                    f"{_pt_brl_bi(conclusion_metrics.get('admin_transition_2024_2025_cielo_pl_brl'))} "
                    "transferidos de Oliveira Trust para Bradesco."
                ),
            ],
        },
        {
            "order": 5,
            "title": "Gestão é a função mais pulverizada",
            "bullets": [
                (
                    "As dez maiores gestoras reúnem apenas "
                    f"{_pt_pct(manager_top10)} do PL ex-FIC; a líder, BTG, tem "
                    f"{_pt_pct(btg_manager.get('share_pl'))}."
                ),
                (
                    "Administração e custódia têm, respectivamente, "
                    f"{_pt_pct(admin_top10)} e {_pt_pct(custody_top10)} do PL nos dez "
                    "maiores grupos, praticamente o dobro da concentração em gestão."
                ),
            ],
        },
        {
            "order": 6,
            "title": "Coorte bancária explica dois terços do combo completo do BTG",
            "bullets": [
                (
                    f"Dos {_pt_integer(conclusion_metrics.get('btg_bank_cohort_observed_funds'))} "
                    "FIDCs observados na coorte BTG, "
                    f"{_pt_integer(conclusion_metrics.get('btg_bank_cohort_combo_funds'))} "
                    "concentram as três funções no grupo e representam "
                    f"{_pt_pct(conclusion_metrics.get('btg_bank_cohort_combo_share_pl'), 0)} "
                    f"do PL da coorte — {_pt_brl_bi(conclusion_metrics.get('btg_bank_cohort_combo_pl_brl'))}."
                ),
                (
                    f"Os {_pt_brl_bi(conclusion_metrics.get('btg_bank_cohort_combo_pl_brl'))} "
                    "da coorte equivalem a "
                    f"{_pt_pct(btg_cohort_combo_share_total, 1)} dos "
                    f"{_pt_brl_bi(conclusion_metrics.get('btg_combo_tres_funcoes_pl_brl'))} "
                    "de PL ex-FIC atendidos pelo BTG nas três funções."
                ),
            ],
        },
        {
            "order": 7,
            "title": "Emissões aceleraram; a maior oferta explica dois terços do avanço",
            "bullets": [
                (
                    f"As {_pt_integer(offer_2026.get('closed_offers'))} ofertas encerradas "
                    f"em jan–jun/26 somaram {_pt_brl_bi(current_volume)}, avanço de "
                    f"{_pt_pct(growth_2025, 0)} sobre jan–jun/25 e "
                    f"{_pt_pct(growth_2024, 0)} sobre jan–jun/24."
                ),
                (
                    f"A oferta {largest_offer_name}, de {_pt_brl_bi(largest_offer_volume)}, "
                    f"representou {_pt_pct(largest_offer_share)} do volume e "
                    f"{_pt_pct(largest_offer_share_increment)} do crescimento sobre jan–jun/25; "
                    "na sensibilidade sem essa oferta, o mercado teria avançado "
                    f"{_pt_pct(growth_ex_largest_offer)}."
                ),
            ],
        },
    ]

    notes = [
        (
            "PF: proxy de volume colocado com "
            f"{_pt_pct(current_offer.get('placed_quantity_registered_volume_coverage'))} "
            "de cobertura do valor registrado."
        ),
        (
            "Contas: quantidade reportada por fundo/classe e agregada ao CNPJ legal; "
            "não equivale a investidores únicos."
        ),
        (
            "Verticalização: universo bruto de CNPJs legais em "
            f"{latest_label}, incluindo FIC-FIDC; grupos econômicos normalizados."
        ),
        (
            "Concentração por função: PL ex-FIC; FIDC Sistema Petrobras e TAPSO "
            "excluídos dos três denominadores."
        ),
        (
            "QI Tech: posição corrente consolidada por grupo; legado Singulare medido "
            "pelos CNPJs legais na fotografia de dez/24."
        ),
        (
            f"BTG: {_pt_integer(conclusion_metrics.get('btg_bank_cohort_listed_roots'))} "
            "raízes listadas em FIDCs.xlsx e "
            f"{_pt_integer(conclusion_metrics.get('btg_bank_cohort_observed_funds'))} "
            f"observadas em {latest_label}; ausência não equivale a PL zero."
        ),
        (
            "Ofertas: cotas primárias de FIDC com status CVM 'Oferta Encerrada', "
            "Data_Encerramento até 30/06/2026 e Valor_Total_Registrado positivo; "
            "uma oferta por Numero_Requerimento."
        ),
    ]
    return conclusions, notes


def _read_optional(
    path: Path,
    *,
    cnpj_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(
            path,
            low_memory=False,
            dtype={column: str for column in cnpj_columns},
        )
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    for column in cnpj_columns:
        if column in frame:
            frame[column] = frame[column].map(_digits)
    return frame


def _read_required_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"arquivo normalizado obrigatório ausente: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"manifesto normalizado deve ser objeto JSON: {path}")
    return payload


def _load_bundle_audit_supplements(data_dir: Path) -> dict[str, Any]:
    """Load normalized cedent/taxonomy audit outputs without reinterpreting them.

    These blocks are materialized upstream from the two source-of-truth
    workbooks.  The payload layer validates cardinalities and carries the
    source/limitations forward; it does not repair declared percentages,
    infer debtors, or infer revenue from cadastral attributes.
    """

    cedente_dir = data_dir / "cedente_triage" / "202606"
    cedente_manifest_path = (
        cedente_dir / "fidc_cedentes_triagem_manifest_202606.json"
    )
    cedente_manifest = _read_required_json(cedente_manifest_path)
    cedente_top = _read_optional(
        cedente_dir / "fidc_cedentes_top437_202606.csv.gz",
        cnpj_columns=("cnpj_fundo",),
    )
    cedente_curve = _read_optional(
        cedente_dir / "fidc_cedentes_curva_cobertura_202606.csv",
        cnpj_columns=("cnpj_fundo",),
    )
    if cedente_top.empty or cedente_curve.empty:
        raise ValueError("triagem de cedentes normalizada está vazia")

    top_queue = cedente_manifest.get("cutoff", {}).get("top_queue", {})
    expected_top_rows = int(top_queue.get("linhas") or 0)
    expected_curve_rows = int(
        cedente_manifest.get("coverage", {}).get("fundos_total") or 0
    )
    if expected_top_rows <= 0 or len(cedente_top) != expected_top_rows:
        raise ValueError(
            "triagem Top N diverge do manifesto: "
            f"{len(cedente_top)} linhas vs. {expected_top_rows}"
        )
    if expected_curve_rows <= 0 or len(cedente_curve) != expected_curve_rows:
        raise ValueError(
            "curva de cobertura diverge do manifesto: "
            f"{len(cedente_curve)} fundos vs. {expected_curve_rows}"
        )
    if cedente_top["cnpj_fundo"].eq("").any() or cedente_curve[
        "cnpj_fundo"
    ].eq("").any():
        raise ValueError("triagem de cedentes contém CNPJ de fundo vazio")

    taxonomy_manifest_path = (
        data_dir / "industry_taxonomy_audit_manifest_202606.json"
    )
    taxonomy_manifest = _read_required_json(taxonomy_manifest_path)
    taxonomy_decisions = _read_optional(
        data_dir / "industry_taxonomy_audited_decisions_202606.csv",
        cnpj_columns=("cnpj_fundo",),
    )
    taxonomy_outros = _read_optional(
        data_dir / "industry_taxonomy_outros_three_buckets_202606.csv",
        cnpj_columns=("cnpj_fundo",),
    )
    taxonomy_impact = _read_optional(
        data_dir / "industry_taxonomy_impact_summary_202606.csv"
    )
    taxonomy_issuance_impact = _read_optional(
        data_dir / "industry_taxonomy_issuance_impact_202606.csv"
    )
    taxonomy_market_share_impact = _read_optional(
        data_dir
        / "industry_taxonomy_market_share_denominator_impact_202606.csv"
    )
    expected_decisions = int(
        taxonomy_manifest.get("sheets", {}).get(
            "De-para reclassificação", 0
        )
    )
    expected_outros = int(
        taxonomy_manifest.get("sheets", {}).get("Outros · 3 baldes", 0)
    )
    if len(taxonomy_decisions) != expected_decisions:
        raise ValueError(
            "de-para de taxonomia diverge do manifesto: "
            f"{len(taxonomy_decisions)} decisões vs. {expected_decisions}"
        )
    if len(taxonomy_outros) != expected_outros:
        raise ValueError(
            "abertura de Outros diverge do manifesto: "
            f"{len(taxonomy_outros)} linhas vs. {expected_outros}"
        )
    for label, frame in (
        ("de-para", taxonomy_decisions),
        ("Outros · 3 baldes", taxonomy_outros),
    ):
        if frame["cnpj_fundo"].eq("").any():
            raise ValueError(f"{label} contém CNPJ vazio")
        if frame["cnpj_fundo"].duplicated().any():
            raise ValueError(f"{label} contém CNPJ duplicado")

    impact_requirements = (
        (
            "impacto consolidado da taxonomia",
            taxonomy_impact,
            {
                "view",
                "competence",
                "universe",
                "dimension",
                "category",
                "delta_brl",
                "denominator_brl",
                "delta_pp",
                "source",
                "note",
            },
        ),
        (
            "impacto da taxonomia nas emissões",
            taxonomy_issuance_impact,
            {
                "period_key",
                "period_label",
                "categoria",
                "before_volume_brl",
                "after_volume_brl",
                "delta_brl",
                "delta_pp",
                "source_before",
                "source_after",
                "note",
            },
        ),
        (
            "impacto da taxonomia nos denominadores de market share",
            taxonomy_market_share_impact,
            {
                "competence",
                "tipo_anbima",
                "foco_anbima",
                "before_denominator_brl",
                "after_denominator_brl",
                "delta_denominator_brl",
                "delta_pp",
                "source",
                "note",
            },
        ),
    )
    for label, frame, required_columns in impact_requirements:
        if frame.empty:
            raise ValueError(f"{label} está vazio")
        missing_columns = sorted(required_columns.difference(frame.columns))
        if missing_columns:
            raise ValueError(
                f"{label} sem colunas obrigatórias: {missing_columns}"
            )

    issues_by_cnpj = {
        _digits(issue.get("cnpj_fundo")): issue
        for issue in taxonomy_manifest.get("issues", [])
        if isinstance(issue, dict) and _digits(issue.get("cnpj_fundo"))
    }
    source = taxonomy_manifest.get("source", {})
    source_file = str(source.get("filename") or "N/D")
    source_sha256 = str(source.get("sha256") or "N/D")
    reference_competence = "2026-06"

    def add_taxonomy_trace(frame: pd.DataFrame) -> pd.DataFrame:
        traced = frame.copy()
        traced["fonte_arquivo"] = source_file
        traced["fonte_sha256"] = source_sha256
        traced["competencia_referencia"] = reference_competence
        traced["status_nota_manifest"] = traced["cnpj_fundo"].map(
            lambda cnpj: str(issues_by_cnpj.get(cnpj, {}).get("status") or "")
        )
        traced["nota_manifest"] = traced["cnpj_fundo"].map(
            lambda cnpj: str(issues_by_cnpj.get(cnpj, {}).get("detail") or "")
        )
        return traced

    return {
        "cedente_middle_market_top437": _records(cedente_top),
        "cedente_middle_market_coverage_curve": _records(cedente_curve),
        "cedente_middle_market_manifest": _json_value(cedente_manifest),
        "taxonomy_audit_decisions": _records(
            add_taxonomy_trace(taxonomy_decisions)
        ),
        "taxonomy_audit_outros_three_buckets": _records(
            add_taxonomy_trace(taxonomy_outros)
        ),
        "taxonomy_audit_impact_summary": _records(taxonomy_impact),
        "taxonomy_audit_issuance_impact": _records(
            taxonomy_issuance_impact
        ),
        "taxonomy_audit_market_share_impact": _records(
            taxonomy_market_share_impact
        ),
        "taxonomy_audit_manifest": _json_value(taxonomy_manifest),
    }


def _merge_documentary_review_layers(
    *layers: pd.DataFrame,
) -> pd.DataFrame:
    """Overlay documentary layers by CNPJ, preserving only explicit values.

    Layers are ordered from lowest to highest precedence. A later row replaces
    a field only when that field is populated, so a focused human review can
    override its conclusions without erasing complementary classification
    fields produced by the complete Top 20 review.
    """
    result = pd.DataFrame()
    for layer in layers:
        if layer is None or layer.empty:
            continue
        current = layer.copy()
        current["cnpj_fundo"] = current["cnpj_fundo"].map(_digits)
        current = current[current["cnpj_fundo"].ne("")].drop_duplicates(
            "cnpj_fundo", keep="last"
        )
        if result.empty:
            result = current.reset_index(drop=True)
            continue

        result = result.set_index("cnpj_fundo")
        current = current.set_index("cnpj_fundo")
        all_index = result.index.union(current.index)
        all_columns = result.columns.union(current.columns, sort=False)
        result = result.reindex(index=all_index, columns=all_columns).astype(object)
        current = current.reindex(index=all_index, columns=all_columns).astype(object)
        for column in all_columns:
            values = current[column]
            populated = values.notna() & values.map(
                lambda value: not isinstance(value, str) or bool(value.strip())
            )
            result.loc[populated, column] = values.loc[populated]
        result = result.reset_index()
    return result


def _single_record(frame: pd.DataFrame) -> dict[str, Any]:
    records = _records(frame)
    return records[0] if records else {}


def _provider_leadership_payload(
    summary: pd.DataFrame,
    btg_detail: pd.DataFrame,
    qi_detail: pd.DataFrame,
) -> dict[str, Any]:
    """Convert the sparse two-row analytical table into renderer dictionaries."""

    output: dict[str, Any] = {}
    for record in _records(summary):
        provider = str(record.pop("provider", "")).strip().lower()
        if not provider:
            continue
        clean = {key: value for key, value in record.items() if value is not None}
        for key in (
            "rank_without_confirmed",
            "controlled_fidcs_expected",
            "controlled_fidcs_reconciled",
        ):
            if key in clean:
                clean[key] = int(clean[key])
        output[provider] = clean
    if "btg" in output and not btg_detail.empty:
        output["btg"]["reconciliation"] = _records(btg_detail)
    if "qi" in output and not qi_detail.empty:
        output["qi"]["legacy_entities"] = _records(qi_detail)
    return _json_value(output)


def _last_observation_by_year(monthly: pd.DataFrame, latest: str) -> pd.DataFrame:
    scoped = monthly[monthly["competencia"].astype(str).le(latest)].copy()
    scoped["year"] = scoped["competencia"].astype(str).str[:4].astype(int)
    scoped = scoped[scoped["year"].ge(2015)]
    return (
        scoped.sort_values("competencia")
        .groupby("year", as_index=False)
        .tail(1)
        .sort_values("year")
    )


def _apply_detected_fic_history(
    annual_pl: pd.DataFrame,
    fic_detection_audit: pd.DataFrame,
) -> pd.DataFrame:
    """Replace the legacy nominal signal with the audited FIC perimeter."""

    output = annual_pl.copy()
    if fic_detection_audit.empty:
        output["pl_ex_fic"] = output["pl_total"] - output["pl_fic_fidc"]
        output["pl_fic_componente"] = output["pl_fic_fidc"]
        return output

    required = {"competencia", "cnpj_fundo", "is_fic", "pl"}
    missing = sorted(required.difference(fic_detection_audit.columns))
    if missing:
        raise ValueError(
            "auditoria FIC sem colunas obrigatórias: " + ", ".join(missing)
        )
    audit = fic_detection_audit.copy()
    audit = audit[
        audit["is_fic"]
        .astype(str)
        .str.strip()
        .str.casefold()
        .isin({"true", "1", "sim", "yes"})
    ].copy()
    audit["pl"] = pd.to_numeric(audit["pl"], errors="coerce").fillna(0.0)
    by_period = (
        audit.groupby("competencia", as_index=False)
        .agg(
            pl_fic_detectado=("pl", "sum"),
            fundos_fic_detectados=("cnpj_fundo", "nunique"),
        )
        .set_index("competencia")
    )
    output["pl_fic_fidc"] = (
        output["competencia"].astype(str).map(by_period["pl_fic_detectado"]).fillna(0.0)
    )
    output["fundos_fic_detectados"] = (
        output["competencia"]
        .astype(str)
        .map(by_period["fundos_fic_detectados"])
        .fillna(0)
        .astype(int)
    )
    output["pl_ex_fic"] = output["pl_total"] - output["pl_fic_fidc"]
    output["pl_fic_componente"] = output["pl_fic_fidc"]
    output["fic_detection_source"] = "industry_fic_detection_audit.csv"
    output["fic_detection_rule"] = (
        "sinal nominal legado derivado da denominação social ou VL_DICRED zerado "
        "em toda a série com cotas de FIDC representando pelo menos 50% das "
        "aplicações"
    )
    return output


def _pl_total_cagr_periods(annual_pl: pd.DataFrame) -> pd.DataFrame:
    """Materialize annual growth from the ex-FIC series shown in the chart."""

    required = {"year", "competencia", "pl_ex_fic"}
    missing = sorted(required.difference(annual_pl.columns))
    if missing:
        raise ValueError("série anual de PL sem colunas: " + ", ".join(missing))
    by_year = annual_pl.set_index("year", drop=False)
    rows: list[dict[str, Any]] = []
    for start_year, end_year, period_label, growth_kind in ANNUAL_GROWTH_PERIODS:
        if start_year not in by_year.index or end_year not in by_year.index:
            raise ValueError(
                f"série anual de PL não cobre CAGR {start_year}-{end_year}"
            )
        start = by_year.loc[start_year]
        end = by_year.loc[end_year]
        start_pl = float(start["pl_ex_fic"])
        end_pl = float(end["pl_ex_fic"])
        annual_intervals = int(end_year - start_year)
        if start_pl <= 0 or end_pl <= 0 or annual_intervals <= 0:
            raise ValueError(f"base inválida para CAGR {start_year}-{end_year}")
        growth = (
            (end_pl / start_pl) ** (1 / annual_intervals) - 1
            if growth_kind == "cagr"
            else end_pl / start_pl - 1
        )
        rows.append(
            {
                "metric": "PL ex-FIC",
                "period_label": period_label,
                "growth_kind": growth_kind,
                "start_year": int(start_year),
                "end_year": int(end_year),
                "start_competencia": str(start["competencia"]),
                "end_competencia": str(end["competencia"]),
                "start_pl_total_brl": start_pl,
                "end_pl_total_brl": end_pl,
                "annual_intervals": annual_intervals,
                "cagr": growth,
            }
        )
    return pd.DataFrame(rows)


def _bcb_total_growth_periods(expanded_credit: pd.DataFrame) -> pd.DataFrame:
    """Materialize growth windows for private expanded credit in slide 3."""

    required = {"competencia", "private_expanded_credit_total_brl"}
    missing = sorted(required.difference(expanded_credit.columns))
    if missing:
        raise ValueError("série BCB sem colunas: " + ", ".join(missing))
    scoped = expanded_credit.copy()
    scoped["year"] = scoped["competencia"].astype(str).str[:4].astype(int)
    by_year = scoped.set_index("year", drop=False)
    rows: list[dict[str, Any]] = []
    for start_year, end_year, period_label, growth_kind in ANNUAL_GROWTH_PERIODS:
        if start_year not in by_year.index or end_year not in by_year.index:
            raise ValueError(
                f"série BCB não cobre crescimento {start_year}-{end_year}"
            )
        start = by_year.loc[start_year]
        end = by_year.loc[end_year]
        start_value = float(start["private_expanded_credit_total_brl"])
        end_value = float(end["private_expanded_credit_total_brl"])
        annual_intervals = int(end_year - start_year)
        if start_value <= 0 or end_value <= 0 or annual_intervals <= 0:
            raise ValueError(
                f"base BCB inválida para crescimento {start_year}-{end_year}"
            )
        growth = (
            (end_value / start_value) ** (1 / annual_intervals) - 1
            if growth_kind == "cagr"
            else end_value / start_value - 1
        )
        rows.append(
            {
                "metric": "Carteira de Crédito Privada Ampliada",
                "period_label": period_label,
                "growth_kind": growth_kind,
                "start_year": int(start_year),
                "end_year": int(end_year),
                "start_competencia": str(start["competencia"]),
                "end_competencia": str(end["competencia"]),
                "start_total_brl": start_value,
                "end_total_brl": end_value,
                "annual_intervals": annual_intervals,
                "cagr": growth,
            }
        )
    return pd.DataFrame(rows)


def _investor_composition(
    cotistas: pd.DataFrame,
    latest: str,
    *,
    expected_total: float | None = None,
) -> pd.DataFrame:
    scoped = cotistas[cotistas["competencia"].astype(str).eq(latest)].copy()
    values = scoped.set_index("tipo_cotista")["n_cotistas"].to_dict()

    def total(*labels: str) -> float:
        return float(sum(float(values.get(label, 0) or 0) for label in labels))

    rows = [
        ("Fundos", total("Outros fundos", "Cotas de FIDC (outros FIDC/FIC-FIDC)", "FII")),
        ("Empresas e outros", total("Outros", "PJ nao financeira", "Investidor nao residente", "Clube de investimento")),
        ("Pessoa física", total("Pessoa fisica")),
        ("Instituições financeiras", total("Corretora/distribuidora", "Banco comercial", "Outra PJ financeira")),
        ("Previdência e seguros", total("Previdencia fechada (EFPC)", "Regime proprio (RPPS)", "Previdencia aberta (EAPC)", "Seguradora", "Capitalizacao")),
    ]
    result = pd.DataFrame(rows, columns=["categoria", "contas"])
    identified = float(result["contas"].sum())
    residual = max(0.0, float(expected_total or 0.0) - identified)
    if residual:
        result = pd.concat(
            [
                result,
                pd.DataFrame([{"categoria": "Não classificado", "contas": residual}]),
            ],
            ignore_index=True,
        )
    result["share"] = result["contas"] / result["contas"].sum()
    return result


def _holder_distribution(vehicle: pd.DataFrame, latest: str) -> pd.DataFrame:
    scoped = vehicle[
        vehicle["competencia"].astype(str).eq(latest)
        & ~vehicle["is_fic_fidc"].fillna(False).astype(bool)
    ].copy()
    scoped["cnpj_fundo"] = scoped["cnpj_fundo"].map(_digits)
    scoped["cnpj_fundo"] = scoped["cnpj_fundo"].where(
        scoped["cnpj_fundo"].ne(""), scoped["cnpj"].map(_digits)
    )
    scoped["cotistas"] = pd.to_numeric(scoped["cotistas"], errors="coerce")
    funds = scoped.groupby("cnpj_fundo", as_index=False).agg(
        pl=("pl", "sum"), contas=("cotistas", lambda values: values.sum(min_count=1))
    )
    funds = funds[funds["pl"].ge(200_000_000)].copy()
    funds = funds[funds["contas"].notna()].copy()
    if funds["contas"].lt(0).any():
        raise ValueError("distribuição por cotistas contém quantidade negativa")
    if not np.allclose(funds["contas"], funds["contas"].round(), atol=1e-9):
        raise ValueError("distribuição por cotistas contém quantidade fracionária")
    funds["bucket"] = pd.cut(
        funds["contas"],
        bins=[-np.inf, 0, 1, 3, 10, 50, np.inf],
        labels=["0", "1", "2–3", "4–10", "11–50", "51+"],
        right=True,
    )
    order = ["0", "1", "2–3", "4–10", "11–50", "51+"]
    grouped = (
        funds.groupby("bucket", observed=False)
        .agg(fundos=("cnpj_fundo", "nunique"), pl=("pl", "sum"))
        .reindex(order, fill_value=0)
        .reset_index()
    )
    total_funds = int(grouped["fundos"].sum())
    total_pl = float(grouped["pl"].sum())
    grouped["share_fundos"] = grouped["fundos"] / total_funds if total_funds else 0.0
    grouped["share_pl"] = grouped["pl"] / total_pl if total_pl else 0.0
    grouped["universo_fundos"] = total_funds
    grouped["universo_pl"] = total_pl

    if total_funds and not np.isclose(grouped["share_fundos"].sum(), 1.0, atol=1e-12):
        raise ValueError("distribuição por cotistas não fecha 100% em quantidade de fundos")
    if total_pl and not np.isclose(grouped["share_pl"].sum(), 1.0, atol=1e-12):
        raise ValueError("distribuição por cotistas não fecha 100% em PL")
    return grouped


def _holder_distribution_history(
    vehicle: pd.DataFrame,
    periods: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    distributions: list[pd.DataFrame] = []
    metadata: list[dict[str, Any]] = []
    for period in periods:
        grouped = _holder_distribution(vehicle, period)
        grouped.insert(0, "competencia", period)
        distributions.append(grouped)

        scoped = vehicle[
            vehicle["competencia"].astype(str).eq(period)
            & ~vehicle["is_fic_fidc"].fillna(False).astype(bool)
        ].copy()
        scoped["cnpj_fundo"] = scoped["cnpj_fundo"].map(_digits)
        scoped["cnpj_fundo"] = scoped["cnpj_fundo"].where(
            scoped["cnpj_fundo"].ne(""), scoped["cnpj"].map(_digits)
        )
        ex_fic_funds = int(scoped["cnpj_fundo"].nunique())
        ex_fic_pl = float(pd.to_numeric(scoped["pl"], errors="coerce").fillna(0).sum())
        eligible_funds = int(grouped["fundos"].sum())
        eligible_pl = float(grouped["pl"].sum())
        metadata.append(
            {
                "competencia": period,
                "minimum_pl_brl": 200_000_000,
                "eligible_funds": eligible_funds,
                "eligible_pl_brl": eligible_pl,
                "ex_fic_funds": ex_fic_funds,
                "ex_fic_pl_brl": ex_fic_pl,
                "fund_coverage": eligible_funds / ex_fic_funds if ex_fic_funds else None,
                "pl_coverage": eligible_pl / ex_fic_pl if ex_fic_pl else None,
            }
        )
    return pd.concat(distributions, ignore_index=True), pd.DataFrame(metadata)


def _type_mix(funds: pd.DataFrame, latest: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    scoped = funds[
        funds["competencia"].astype(str).eq(latest)
        & ~funds["is_fic_fidc"].fillna(False).astype(bool)
    ].copy()
    total_pl = float(scoped["pl"].sum())
    # A taxonomia ANBIMA é uma fotografia cadastral vigente aplicada ao histórico.
    # Se o veículo era ex-FIC na competência, mas hoje está rotulado como FIC-FIDC,
    # não o eliminamos retrospectivamente do denominador: preservamos o PL em N/D.
    scoped["anbima_tipo_period_aware"] = scoped["anbima_tipo"]
    fic_label_on_ex_fic = scoped["anbima_tipo"].map(_text).eq("FIC-FIDC")
    scoped.loc[fic_label_on_ex_fic, "anbima_tipo_period_aware"] = "N/D"
    mix = scoped.groupby("anbima_tipo_period_aware", dropna=False, as_index=False)["pl"].sum()
    mix = mix.rename(columns={"anbima_tipo_period_aware": "anbima_tipo"})
    mix["anbima_tipo"] = mix["anbima_tipo"].map(_text).replace("", "N/D")
    mix["share"] = mix["pl"] / total_pl
    order = ["Fomento Mercantil", "Agro, Indústria e Comércio", "Financeiro", "Outros", "N/D"]
    mix["order"] = mix["anbima_tipo"].map({name: index for index, name in enumerate(order)})
    mix = mix.sort_values(["order", "pl"], na_position="last").drop(columns="order")

    coverage = scoped.groupby("classification_tier", dropna=False, as_index=False)["pl"].sum()
    label_map = {
        "oficial_anbima": "Oficial ANBIMA",
        "evidencia_publicada": "Evidência documental",
        "proxy_cvm": "Proxy CVM",
        "nao_disponivel": "N/D",
    }
    coverage["categoria"] = coverage["classification_tier"].map(label_map).fillna(
        coverage["classification_tier"].map(_text)
    )
    coverage["share"] = coverage["pl"] / total_pl
    coverage = coverage[["categoria", "pl", "share"]]
    return mix, coverage


def _type_mix_history(
    funds: pd.DataFrame,
    periods: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    categories = [
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    ]
    mixes: list[pd.DataFrame] = []
    coverages: list[pd.DataFrame] = []
    metadata: list[dict[str, Any]] = []
    unique_periods = list(dict.fromkeys(periods))
    month_labels = (
        "jan",
        "fev",
        "mar",
        "abr",
        "mai",
        "jun",
        "jul",
        "ago",
        "set",
        "out",
        "nov",
        "dez",
    )
    for period_order, period in enumerate(unique_periods):
        raw_mix, coverage = _type_mix(funds, period)
        raw_mix["anbima_tipo_original"] = raw_mix["anbima_tipo"].map(_text)
        raw_mix["anbima_tipo"] = raw_mix["anbima_tipo_original"].where(
            raw_mix["anbima_tipo_original"].isin(categories[:-1]),
            "Outros",
        )
        nd_incorporated_pl = float(
            raw_mix.loc[
                raw_mix["anbima_tipo_original"].eq("N/D"),
                "pl",
            ].sum()
        )
        mix = (
            raw_mix.groupby("anbima_tipo", as_index=False)["pl"]
            .sum()
            .set_index("anbima_tipo")
            .reindex(categories, fill_value=0.0)
            .rename_axis("anbima_tipo")
            .reset_index()
        )
        total_pl = float(mix["pl"].sum())
        mix["share"] = mix["pl"] / total_pl if total_pl else 0.0
        parsed = pd.Period(period, freq="M")
        period_label = f"{month_labels[parsed.month - 1]}/{str(parsed.year)[-2:]}"
        mix.insert(0, "competencia", period)
        mix["period_label"] = period_label
        mix["period_order"] = period_order
        mix["category_order"] = mix["anbima_tipo"].map(
            {category: index for index, category in enumerate(categories)}
        )
        coverage.insert(0, "competencia", period)
        mixes.append(mix)
        coverages.append(coverage)
        metadata.append(
            {
                "competencia": period,
                "label": period_label,
                "total_pl_ex_fic": total_pl,
                "nd_incorporated_pl": nd_incorporated_pl,
                "nd_incorporated_share": (
                    nd_incorporated_pl / total_pl if total_pl else 0.0
                ),
            }
        )
    meta = {
        "periods": metadata,
        "categories": categories,
        "nd_incorporated_into": "Outros",
        "classification_method": (
            "Fotografia cadastral ANBIMA de dez/25 aplicada ao PL ex-FIC de cada "
            "competência; evidência documental e proxy CVM nos fundos sem "
            "correspondência oficial."
        ),
    }
    return (
        pd.concat(mixes, ignore_index=True),
        pd.concat(coverages, ignore_index=True),
        meta,
    )


def _portfolio_type_mix_history(
    funds: pd.DataFrame,
    actions: pd.DataFrame | None,
    *,
    scope: pd.DataFrame,
    periods: list[str],
    market_history: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build the saved-portfolio history on the same analytical Type contract as the market."""

    categories = [
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    ]
    unique_periods = list(dict.fromkeys(periods))
    if not unique_periods:
        raise ValueError("Carteira 1 requer ao menos uma competência")
    scope_frame = scope.copy()
    if "cnpj_fundo" not in scope_frame:
        raise ValueError("Escopo da Carteira 1 sem cnpj_fundo")
    scope_frame["cnpj_fundo"] = scope_frame["cnpj_fundo"].map(_digits)
    if scope_frame["cnpj_fundo"].eq("").any():
        raise ValueError("Escopo da Carteira 1 contém CNPJ vazio")
    if scope_frame["cnpj_fundo"].duplicated().any():
        raise ValueError("Escopo da Carteira 1 contém CNPJ duplicado")
    scope_cnpjs = set(scope_frame["cnpj_fundo"])

    frame = funds[funds["competencia"].astype(str).isin(unique_periods)].copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(_digits)
    frame = frame[frame["cnpj_fundo"].isin(scope_cnpjs)].copy()
    fic_mask = frame.get("is_fic_fidc", pd.Series(False, index=frame.index)).map(
        lambda value: str(value).strip().casefold() in {"1", "true", "sim", "yes"}
    )
    frame = frame[~fic_mask].copy()
    frame["pl"] = pd.to_numeric(frame["pl"], errors="coerce")
    if frame["pl"].lt(0).any():
        raise ValueError("Carteira 1 contém PL negativo no histórico selecionado")
    frame = frame[frame["pl"].notna()].copy()
    frame = apply_taxonomy_review_overlay(frame, actions)
    frame["anbima_tipo"] = frame["anbima_tipo_curado"].where(
        frame["anbima_tipo_curado"].isin(categories[:-1]),
        "Outros",
    )

    market = market_history.copy()
    market["competencia"] = market["competencia"].astype(str)
    rows: list[dict[str, Any]] = []
    month_labels = (
        "jan", "fev", "mar", "abr", "mai", "jun",
        "jul", "ago", "set", "out", "nov", "dez",
    )
    for period_order, period in enumerate(unique_periods):
        period_frame = frame[frame["competencia"].astype(str).eq(period)]
        grouped = period_frame.groupby("anbima_tipo", as_index=True).agg(
            portfolio_pl_brl=("pl", "sum"),
            portfolio_funds=("cnpj_fundo", "nunique"),
        )
        portfolio_total = float(grouped["portfolio_pl_brl"].sum()) if not grouped.empty else 0.0
        observed_cnpjs = int(period_frame["cnpj_fundo"].nunique())
        market_period = market[market["competencia"].eq(period)].set_index("anbima_tipo")
        market_total = float(pd.to_numeric(market_period.get("pl"), errors="coerce").sum())
        parsed = pd.Period(period, freq="M")
        label = f"{month_labels[parsed.month - 1]}/{str(parsed.year)[-2:]}"
        for category_order, category in enumerate(categories):
            portfolio_pl = (
                float(grouped.at[category, "portfolio_pl_brl"])
                if category in grouped.index else 0.0
            )
            market_pl = (
                float(market_period.at[category, "pl"])
                if category in market_period.index else 0.0
            )
            rows.append(
                {
                    "competencia": period,
                    "period_label": label,
                    "period_order": period_order,
                    "category_order": category_order,
                    "anbima_tipo": category,
                    "portfolio_pl_brl": portfolio_pl,
                    "portfolio_share": portfolio_pl / portfolio_total if portfolio_total else 0.0,
                    "portfolio_funds": (
                        int(grouped.at[category, "portfolio_funds"])
                        if category in grouped.index else 0
                    ),
                    "portfolio_total_brl": portfolio_total,
                    "scope_cnpjs": len(scope_cnpjs),
                    "observed_cnpjs": observed_cnpjs,
                    "coverage_scope_share": observed_cnpjs / len(scope_cnpjs),
                    "market_pl_brl": market_pl,
                    "market_share": market_pl / market_total if market_total else 0.0,
                    "market_total_brl": market_total,
                }
            )
    history = pd.DataFrame(rows)
    start = history[history["competencia"].eq(unique_periods[0])].set_index("anbima_tipo")
    for index, row in history.iterrows():
        category = str(row["anbima_tipo"])
        portfolio_start = float(start.at[category, "portfolio_pl_brl"])
        market_start = float(start.at[category, "market_pl_brl"])
        history.at[index, "portfolio_growth_since_start"] = (
            float(row["portfolio_pl_brl"]) / portfolio_start - 1
            if portfolio_start else None
        )
        history.at[index, "market_growth_since_start"] = (
            float(row["market_pl_brl"]) / market_start - 1
            if market_start else None
        )
        history.at[index, "portfolio_share_delta_pp"] = (
            float(row["portfolio_share"]) - float(start.at[category, "portfolio_share"])
        )
        history.at[index, "market_share_delta_pp"] = (
            float(row["market_share"]) - float(start.at[category, "market_share"])
        )
    latest_rows = history[history["competencia"].eq(unique_periods[-1])]
    summary = {
        "portfolio": "Carteira 1",
        "periods": unique_periods,
        "scope_cnpjs": len(scope_cnpjs),
        "latest_observed_cnpjs": int(latest_rows["observed_cnpjs"].max()),
        "latest_total_brl": float(latest_rows["portfolio_total_brl"].max()),
        "source": "CVM, Informe Mensal FIDC; ledger de taxonomia analítica aprovado",
        "methodology": (
            "CNPJs salvos da Carteira 1, ex-FIC, com classificação analítica aprovada "
            "retroaplicada às competências observadas. CNPJ ausente em uma competência "
            "permanece ausente e não recebe PL imputado. O mercado usa o mesmo Tipo "
            "ANBIMA reclassificado e o denominador ex-FIC."
        ),
    }
    return history, summary


def _receivables(segments: pd.DataFrame, latest: str, portfolio_total: float) -> dict[str, Any]:
    scoped = segments[
        segments["competencia"].astype(str).eq(latest)
        & segments["nivel"].astype(str).eq("top")
    ].copy()
    scoped = scoped.groupby("segmento", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
    reported_total = float(scoped["valor"].sum())
    scoped["share_reported"] = scoped["valor"] / reported_total if reported_total else 0.0
    if reported_total and not np.isclose(scoped["share_reported"].sum(), 1.0, atol=1e-12):
        raise ValueError("tipos de recebível não fecham 100% sobre a Tabela II")
    return {
        "rows": _records(scoped),
        "reported_total": reported_total,
        "portfolio_total": portfolio_total,
        "gap": reported_total - portfolio_total,
        "gap_pct": (reported_total / portfolio_total - 1) if portfolio_total else None,
    }


def _receivables_history(
    segments: pd.DataFrame,
    monthly: pd.DataFrame,
    periods: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[pd.DataFrame] = []
    metadata: list[dict[str, Any]] = []
    for period in periods:
        month = monthly[monthly["competencia"].astype(str).eq(period)]
        if month.empty:
            raise ValueError(f"competência ausente em industry_monthly.csv: {period}")
        portfolio_total = float(month.iloc[0]["carteira_dc"])
        result = _receivables(segments, period, portfolio_total)
        frame = pd.DataFrame(result["rows"])
        frame.insert(0, "competencia", period)
        rows.append(frame)
        metadata.append(
            {
                "competencia": period,
                "reported_total": result["reported_total"],
                "portfolio_total": result["portfolio_total"],
                "gap": result["gap"],
                "gap_pct": result["gap_pct"],
            }
        )
    return pd.concat(rows, ignore_index=True), pd.DataFrame(metadata)


def _provider_concentration(providers: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for role, group in providers.groupby("papel"):
        sorted_group = group.sort_values("pl", ascending=False).copy()
        shares = pd.to_numeric(sorted_group["share_pl"], errors="coerce").fillna(0)
        top = sorted_group.head(3)
        rows.append(
            {
                "papel": role,
                "top5_share": float(shares.head(5).sum()),
                "top10_share": float(shares.head(10).sum()),
                "hhi": float(((shares * 100) ** 2).sum()),
                "top3": _records(top[["nome", "pl", "share_pl", "n_fundos"]]),
            }
        )
    return rows


def _provider_concentration_history(
    funds: pd.DataFrame,
    periods: list[str],
) -> list[dict[str, Any]]:
    role_columns = {
        "administrador": ("admin_nome", "admin_cnpj", "informe mensal da competência"),
        "gestor": ("gestor_nome", "gestor_cnpj", "cadastro CVM vigente aplicado à competência"),
        "custodiante": (
            "custodiante_nome",
            "custodiante_cnpj",
            "cadastro CVM vigente aplicado à competência",
        ),
    }
    rows: list[dict[str, Any]] = []
    excluded = set(MARKET_SHARE_EXCLUDED_FUNDS)
    for period in periods:
        scoped = funds[funds["competencia"].astype(str).eq(period)].copy()
        if "is_fic_fidc" in scoped.columns:
            scoped = scoped[~scoped["is_fic_fidc"].fillna(False)]
        scoped = scoped[~scoped["cnpj_fundo"].map(_digits).isin(excluded)]
        scoped["pl"] = pd.to_numeric(scoped["pl"], errors="coerce").fillna(0.0)
        total_pl = float(scoped["pl"].sum())
        total_funds = int(scoped["cnpj_fundo"].map(_digits).nunique())
        for role, (name_col, cnpj_col, source_note) in role_columns.items():
            scoped_role = scoped[["cnpj_fundo", "pl", name_col, cnpj_col]].copy()
            scoped_role["nome"] = scoped_role[name_col].map(canonical_provider)
            scoped_role["cnpj_prestador"] = scoped_role[cnpj_col].map(_digits)
            missing = scoped_role["nome"].eq("Não informado")
            missing_pl = float(scoped_role.loc[missing, "pl"].sum())
            known = scoped_role.loc[~missing].copy()
            grouped = (
                known.groupby("nome", as_index=False)
                .agg(
                    cnpj_prestador=("cnpj_prestador", "first"),
                    pl=("pl", "sum"),
                    n_fundos=("cnpj_fundo", lambda values: values.map(_digits).nunique()),
                )
                .sort_values("pl", ascending=False)
            )
            grouped["share_pl"] = grouped["pl"] / total_pl if total_pl else 0.0
            shares = grouped["share_pl"]
            rows.append(
                {
                    "competencia": period,
                    "papel": role,
                    "total_pl": total_pl,
                    "n_fundos": total_funds,
                    "identified_pl": total_pl - missing_pl,
                    "coverage_pl": (total_pl - missing_pl) / total_pl if total_pl else None,
                    "missing_pl": missing_pl,
                    "missing_share": missing_pl / total_pl if total_pl else None,
                    "top3_share": float(shares.head(3).sum()),
                    "top5_share": float(shares.head(5).sum()),
                    "top10_share": float(shares.head(10).sum()),
                    "hhi": float(((shares * 100) ** 2).sum()),
                    "top3": _records(grouped.head(3)[["nome", "cnpj_prestador", "pl", "share_pl", "n_fundos"]]),
                    "source_note": source_note,
                }
            )
    return rows


def _atlantico_payload(
    funds: pd.DataFrame,
    data_dir: Path,
    latest: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    curation_path = data_dir / "atlantico_curadoria.json"
    if not curation_path.exists():
        raise FileNotFoundError(f"curadoria do Atlântico não encontrada: {curation_path}")
    curated = json.loads(curation_path.read_text(encoding="utf-8"))

    scoped = funds[funds["cnpj_fundo"].map(_digits).eq(ATLANTICO_CNPJ)].copy()
    if scoped.empty:
        raise ValueError("FIDC Atlântico não encontrado na base por fundo/CNPJ")
    scoped = scoped.sort_values("competencia")

    def numeric(value: object) -> float:
        parsed = pd.to_numeric(value, errors="coerce")
        return 0.0 if pd.isna(parsed) else float(parsed)

    selected_periods = [HISTORICAL_REFERENCE, "2024-06", "2024-07", PROVIDER_REFERENCE, latest]
    history_rows: list[dict[str, Any]] = []
    for period in selected_periods:
        period_rows = scoped[scoped["competencia"].astype(str).eq(period)]
        if period_rows.empty:
            continue
        row = period_rows.iloc[0]
        portfolio = numeric(row.get("carteira_dc"))
        raw = numeric(row.get("dc_inadimplentes"))
        adjusted = numeric(row.get("dc_inadimplentes_ajustado_recalculado"))
        report_above_360 = str(row.get("reports_inad_acima_360d")).strip().lower() == "true"
        above_360 = (
            numeric(row.get("inad_acima_360d"))
            if report_above_360
            else None
        )
        above_1080 = (
            numeric(row.get("inad_maior_1080d"))
            if report_above_360
            else None
        )
        history_rows.append(
            {
                "competencia": period,
                "pl": numeric(row.get("pl")),
                "carteira": portfolio,
                "inadimplencia_bruta": raw,
                "inadimplencia_ajustada": adjusted,
                "vencidos_mais_360d": above_360,
                "vencidos_mais_1080d": above_1080,
                "excesso": max(raw - adjusted, 0.0),
                "inadimplencia_share_carteira": raw / portfolio if portfolio else None,
                "ajustada_share_carteira": adjusted / portfolio if portfolio else None,
                "mais_360_share_carteira": above_360 / portfolio if portfolio and above_360 is not None else None,
                "aging_reportado": report_above_360,
                "administrador": _text(row.get("admin_nome")) or "não identificado",
            }
        )

    history = pd.DataFrame(history_rows)
    current_rows = scoped[scoped["competencia"].astype(str).eq(latest)]
    if current_rows.empty:
        raise ValueError(f"FIDC Atlântico ausente na competência {latest}")
    current = current_rows.iloc[0]
    current_history = history[history["competencia"].eq(latest)].iloc[0]
    june = history[history["competencia"].eq("2024-06")].iloc[0]
    july = history[history["competencia"].eq("2024-07")].iloc[0]
    current_raw = float(current_history["inadimplencia_bruta"])
    current_portfolio = float(current_history["carteira"])
    current_above_360 = current_history["vencidos_mais_360d"]
    current_above_1080 = current_history["vencidos_mais_1080d"]

    profile: dict[str, Any] = {
        **curated,
        "denominacao": _text(current.get("denominacao")),
        "administrador": _text(current.get("admin_nome")) or "não identificado",
        "gestor": _text(current.get("gestor_nome")) or "não identificado",
        "custodiante": _text(current.get("custodiante_nome")) or "não identificado",
        "prestadores": (
            f"Administrador e custodiante: {_text(current.get('admin_nome')) or 'não identificado'}. "
            f"Gestor: {_text(current.get('gestor_nome')) or 'não identificado'}. "
            "Consultoria especializada: MGC Capital; agente de cobrança: Crediativos; auditor: BDO."
        ),
        "snapshot": {
            "competencia": latest,
            "pl": float(current_history["pl"]),
            "carteira": current_portfolio,
            "inadimplencia_bruta": current_raw,
            "inadimplencia_ajustada": float(current_history["inadimplencia_ajustada"]),
            "inadimplencia_share_carteira": current_raw / current_portfolio if current_portfolio else None,
            "vencidos_mais_360d": float(current_above_360) if pd.notna(current_above_360) else None,
            "mais_360_share_carteira": float(current_above_360) / current_portfolio
            if current_portfolio and pd.notna(current_above_360)
            else None,
            "vencidos_mais_1080d": float(current_above_1080) if pd.notna(current_above_1080) else None,
            "mais_1080_share_inadimplencia": float(current_above_1080) / current_raw
            if current_raw and pd.notna(current_above_1080)
            else None,
        },
        "bridge_2024_06_07": {
            "inadimplencia_bruta_jun": float(june["inadimplencia_bruta"]),
            "inadimplencia_bruta_jul": float(july["inadimplencia_bruta"]),
            "delta_inadimplencia_bruta": float(july["inadimplencia_bruta"] - june["inadimplencia_bruta"]),
            "carteira_jun": float(june["carteira"]),
            "carteira_jul": float(july["carteira"]),
            "delta_carteira": float(july["carteira"] - june["carteira"]),
            "pl_jun": float(june["pl"]),
            "pl_jul": float(july["pl"]),
            "delta_pl": float(july["pl"] - june["pl"]),
            "excesso_jun": float(june["excesso"]),
            "excesso_jul": float(july["excesso"]),
        },
        "is_np_pipeline": bool(current.get("is_np")) if pd.notna(current.get("is_np")) else None,
        "data_referencia": latest,
    }
    return profile, _records(history)


def _service_model(mono: pd.DataFrame, latest: str) -> pd.DataFrame:
    scoped = mono[mono["competencia"].astype(str).eq(latest)].copy()
    grouped = scoped.groupby("modelo_prestacao", dropna=False).agg(
        fundos=("cnpj_fundo", "nunique"), pl=("pl", "sum")
    ).reset_index()
    grouped["share_fundos"] = grouped["fundos"] / grouped["fundos"].sum()
    grouped["share_pl"] = grouped["pl"] / grouped["pl"].sum()
    order = [
        "Monoestrutura",
        "Administração + Gestão",
        "Administração + Custódia",
        "Gestão + Custódia",
        "Três prestadores distintos",
        "Dados incompletos",
    ]
    grouped["order"] = grouped["modelo_prestacao"].map({name: i for i, name in enumerate(order)})
    return grouped.sort_values("order").drop(columns="order")


def _provider_transition_conclusion_metrics(
    funds: pd.DataFrame,
    *,
    from_competence: str = "2024-12",
    to_competence: str = "2025-12",
) -> dict[str, Any]:
    """Summarize administrator changes on a like-for-like legal-fund cohort.

    The bridge deliberately weights every continuing fund by the lower PL of
    the two observations.  This keeps growth or shrinkage inside an unchanged
    fund from being mistaken for provider migration.
    """

    excluded = {_digits(value) for value in MARKET_SHARE_EXCLUDED_FUNDS}

    def _scope(competence: str) -> pd.DataFrame:
        scoped = funds[
            funds["competencia"].astype(str).str[:7].eq(str(competence)[:7])
        ].copy()
        scoped["cnpj_fundo"] = scoped["cnpj_fundo"].map(_digits)
        scoped["pl"] = pd.to_numeric(scoped["pl"], errors="coerce")
        scoped = scoped[
            scoped["cnpj_fundo"].ne("")
            & ~scoped["is_fic_fidc"].fillna(False).astype(bool)
            & scoped["pl"].gt(0)
            & ~scoped["cnpj_fundo"].isin(excluded)
        ].copy()
        return (
            scoped.sort_values(["pl", "cnpj_fundo"], ascending=[False, True])
            .drop_duplicates("cnpj_fundo", keep="first")
            .reset_index(drop=True)
        )

    old = _scope(from_competence)[
        ["cnpj_fundo", "denominacao", "pl", "admin_nome"]
    ].rename(
        columns={
            "denominacao": "denominacao_origem",
            "pl": "pl_origem_brl",
            "admin_nome": "admin_origem_nome",
        }
    )
    new = _scope(to_competence)[
        ["cnpj_fundo", "denominacao", "pl", "admin_nome"]
    ].rename(
        columns={
            "denominacao": "denominacao_destino",
            "pl": "pl_destino_brl",
            "admin_nome": "admin_destino_nome",
        }
    )
    detail = old.merge(new, on="cnpj_fundo", how="inner", validate="one_to_one")
    detail["grupo_origem"] = detail["admin_origem_nome"].map(canonical_provider)
    detail["grupo_destino"] = detail["admin_destino_nome"].map(canonical_provider)
    detail["pl_comparavel_brl"] = detail[
        ["pl_origem_brl", "pl_destino_brl"]
    ].min(axis=1)
    detail["mudou_grupo"] = detail["grupo_origem"].ne(detail["grupo_destino"])

    comparable_pl = float(detail["pl_comparavel_brl"].sum())
    changed = detail[detail["mudou_grupo"]].copy()
    changed_pl = float(changed["pl_comparavel_brl"].sum())
    cielo = changed[
        changed["grupo_origem"].eq("Oliveira Trust")
        & changed["grupo_destino"].eq("Bradesco")
        & changed["denominacao_destino"].fillna("").str.contains(
            "CIELO", case=False, regex=False
        )
    ].copy()

    return {
        "admin_transition_2024_2025_from": str(from_competence)[:7],
        "admin_transition_2024_2025_to": str(to_competence)[:7],
        "admin_transition_2024_2025_continuing_funds": int(len(detail)),
        "admin_transition_2024_2025_comparable_pl_brl": comparable_pl,
        "admin_transition_2024_2025_changed_funds": int(len(changed)),
        "admin_transition_2024_2025_changed_pl_brl": changed_pl,
        "admin_transition_2024_2025_changed_share_pl": (
            changed_pl / comparable_pl if comparable_pl else None
        ),
        "admin_transition_2024_2025_cielo_funds": int(len(cielo)),
        "admin_transition_2024_2025_cielo_pl_brl": float(
            cielo["pl_comparavel_brl"].sum()
        ),
        "admin_transition_2024_2025_cielo_names": sorted(
            cielo["denominacao_destino"].dropna().astype(str).unique().tolist()
        ),
        "admin_transition_2024_2025_methodology": (
            "CNPJs legais com PL positivo em dez/24 e dez/25; ex-FIC-FIDC e sem "
            "FIDC Sistema Petrobras/TAPSO; administrador informado em cada "
            "competência; PL comparável = menor PL entre as duas datas"
        ),
    }


def _conclusion_metrics(
    vehicle: pd.DataFrame,
    funds: pd.DataFrame,
    latest: str,
    *,
    mono: pd.DataFrame | None = None,
    bank_fidc_detail: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Materialize the small set of cross-slide metrics used in conclusions."""

    current = funds[
        funds["competencia"].astype(str).eq(latest)
        & ~funds["is_fic_fidc"].fillna(False).astype(bool)
        & pd.to_numeric(funds["pl"], errors="coerce").gt(0)
    ].copy()
    current["cnpj_fundo"] = current["cnpj_fundo"].map(_digits)
    current["pl"] = pd.to_numeric(current["pl"], errors="coerce")
    for source, target in (
        ("admin_nome", "administrador_grupo"),
        ("gestor_nome", "gestor_grupo"),
        ("custodiante_nome", "custodiante_grupo"),
    ):
        current[target] = current[source].map(canonical_provider)
    total_pl = float(current["pl"].sum())
    identified_admin_custody = (
        ~current["administrador_grupo"].isin(["", "Não informado"])
        & ~current["custodiante_grupo"].isin(["", "Não informado"])
    )
    same_admin_custody = identified_admin_custody & current[
        "administrador_grupo"
    ].eq(current["custodiante_grupo"])
    provider_current = current[
        ~current["cnpj_fundo"].isin({_digits(value) for value in MARKET_SHARE_EXCLUDED_FUNDS})
    ].copy()
    provider_total_pl = float(provider_current["pl"].sum())
    provider_identified_admin_custody = (
        ~provider_current["administrador_grupo"].isin(["", "Não informado"])
        & ~provider_current["custodiante_grupo"].isin(["", "Não informado"])
    )
    provider_same_admin_custody = provider_identified_admin_custody & provider_current[
        "administrador_grupo"
    ].eq(provider_current["custodiante_grupo"])
    triple_btg = (
        current["administrador_grupo"].eq("BTG Pactual")
        & current["gestor_grupo"].eq("BTG Pactual")
        & current["custodiante_grupo"].eq("BTG Pactual")
    )
    controlled = {_digits(value) for value in BTG_CONTROLLED_FIDCS}
    triple_btg_ex_controlled = triple_btg & ~current["cnpj_fundo"].isin(controlled)

    holder = vehicle[
        vehicle["competencia"].astype(str).eq(latest)
        & ~vehicle["is_fic_fidc"].fillna(False).astype(bool)
    ].copy()
    holder["cnpj_fundo"] = holder["cnpj_fundo"].map(_digits)
    holder["cnpj_fundo"] = holder["cnpj_fundo"].where(
        holder["cnpj_fundo"].ne(""), holder["cnpj"].map(_digits)
    )
    holder["pl"] = pd.to_numeric(holder["pl"], errors="coerce")
    holder["cotistas"] = pd.to_numeric(holder["cotistas"], errors="coerce")
    holder = holder.groupby("cnpj_fundo", as_index=False).agg(
        pl=("pl", "sum"),
        contas=("cotistas", lambda values: values.sum(min_count=1)),
    )
    holder = holder[holder["pl"].gt(0) & holder["contas"].notna()].copy()
    up_to_5 = holder["contas"].le(5)
    up_to_10 = holder["contas"].le(10)
    holder_pl = float(holder["pl"].sum())

    holder_ge_200m = holder[holder["pl"].ge(200_000_000)].copy()
    holder_ge_200m_up_to_10 = holder_ge_200m["contas"].le(10)
    holder_ge_200m_pl = float(holder_ge_200m["pl"].sum())

    service_metrics: dict[str, Any] = {}
    btg_bank_metrics: dict[str, Any] = {}
    if mono is not None and not mono.empty:
        service = _service_model(mono, latest).set_index("modelo_prestacao")
        service_total_funds = int(service["fundos"].sum())
        service_total_pl = float(service["pl"].sum())
        monostructure = service.loc["Monoestrutura"]
        admin_custody = service.loc["Administração + Custódia"]
        admin_custody_together_funds = int(
            monostructure["fundos"] + admin_custody["fundos"]
        )
        admin_custody_together_pl = float(
            monostructure["pl"] + admin_custody["pl"]
        )
        service_metrics = {
            "service_model_universe_funds": service_total_funds,
            "service_model_universe_pl_brl": service_total_pl,
            "admin_custodia_juntas_fundos": admin_custody_together_funds,
            "admin_custodia_juntas_pl_brl": admin_custody_together_pl,
            "admin_custodia_juntas_share_pl": (
                admin_custody_together_pl / service_total_pl
                if service_total_pl
                else None
            ),
            "monoestrutura_fundos": int(monostructure["fundos"]),
            "monoestrutura_pl_brl": float(monostructure["pl"]),
            "monoestrutura_share_pl": (
                float(monostructure["pl"]) / service_total_pl
                if service_total_pl
                else None
            ),
            "service_model_definition": (
                f"universo elegível de CNPJs legais em {latest}; mesmo conglomerado "
                "econômico normalizado; FICs excluídos pelo portão único"
            ),
        }
        if bank_fidc_detail is not None and not bank_fidc_detail.empty:
            bank_current = bank_fidc_detail[
                bank_fidc_detail["competencia"].astype(str).eq(latest)
                & bank_fidc_detail["bank_group"].astype(str).eq("BTG")
            ].copy()
            bank_current["cnpj_fundo"] = bank_current["cnpj_fundo"].map(_digits)
            observed = bank_current[
                bank_current["observado"].fillna(False).astype(bool)
                & pd.to_numeric(bank_current["pl_brl"], errors="coerce").gt(0)
            ].copy()
            observed_cnpjs = set(observed["cnpj_fundo"])
            mono_current = mono[mono["competencia"].astype(str).eq(latest)].copy()
            mono_current["cnpj_fundo"] = mono_current["cnpj_fundo"].map(_digits)
            mono_current = mono_current[mono_current["cnpj_fundo"].isin(observed_cnpjs)]
            combo = (
                mono_current["administrador_grupo"].eq("BTG Pactual")
                & mono_current["gestor_grupo"].eq("BTG Pactual")
                & mono_current["custodiante_grupo"].eq("BTG Pactual")
            )
            cohort_pl = float(pd.to_numeric(observed["pl_brl"], errors="coerce").sum())
            combo_pl = float(pd.to_numeric(mono_current.loc[combo, "pl"], errors="coerce").sum())
            btg_bank_metrics = {
                "btg_bank_cohort_listed_roots": int(len(bank_current)),
                "btg_bank_cohort_observed_funds": int(observed["cnpj_fundo"].nunique()),
                "btg_bank_cohort_pl_brl": cohort_pl,
                "btg_bank_cohort_combo_funds": int(
                    mono_current.loc[combo, "cnpj_fundo"].nunique()
                ),
                "btg_bank_cohort_combo_pl_brl": combo_pl,
                "btg_bank_cohort_combo_share_pl": (
                    combo_pl / cohort_pl if cohort_pl else None
                ),
                "btg_bank_cohort_definition": (
                    "raízes listadas na aba BTG de FIDCs.xlsx; PL bruto observado "
                    f"no Informe Mensal em {latest}; ausências permanecem explícitas"
                ),
            }

    transition_metrics = _provider_transition_conclusion_metrics(funds)

    return {
        "competencia": latest,
        "universo_fundos_ex_fic_pl_positivo": int(current["cnpj_fundo"].nunique()),
        "universo_pl_ex_fic_brl": total_pl,
        "admin_custodia_mesmo_grupo_fundos": int(current.loc[same_admin_custody, "cnpj_fundo"].nunique()),
        "admin_custodia_mesmo_grupo_pl_brl": float(current.loc[same_admin_custody, "pl"].sum()),
        "admin_custodia_mesmo_grupo_share_pl": float(current.loc[same_admin_custody, "pl"].sum()) / total_pl,
        "admin_custodia_cobertura_share_pl": float(current.loc[identified_admin_custody, "pl"].sum()) / total_pl,
        "universo_prestadores_fundos": int(provider_current["cnpj_fundo"].nunique()),
        "universo_prestadores_pl_brl": provider_total_pl,
        "admin_custodia_mesmo_grupo_prestadores_fundos": int(
            provider_current.loc[provider_same_admin_custody, "cnpj_fundo"].nunique()
        ),
        "admin_custodia_mesmo_grupo_prestadores_pl_brl": float(
            provider_current.loc[provider_same_admin_custody, "pl"].sum()
        ),
        "admin_custodia_mesmo_grupo_prestadores_share_pl": float(
            provider_current.loc[provider_same_admin_custody, "pl"].sum()
        ) / provider_total_pl,
        "admin_custodia_prestadores_cobertura_share_pl": float(
            provider_current.loc[provider_identified_admin_custody, "pl"].sum()
        ) / provider_total_pl,
        "btg_combo_tres_funcoes_fundos": int(current.loc[triple_btg, "cnpj_fundo"].nunique()),
        "btg_combo_tres_funcoes_pl_brl": float(current.loc[triple_btg, "pl"].sum()),
        "btg_controlados_df_excluidos_fundos": int(current.loc[triple_btg & current["cnpj_fundo"].isin(controlled), "cnpj_fundo"].nunique()),
        "btg_controlados_df_excluidos_pl_brl": float(current.loc[triple_btg & current["cnpj_fundo"].isin(controlled), "pl"].sum()),
        "btg_combo_ex_controlados_fundos": int(current.loc[triple_btg_ex_controlled, "cnpj_fundo"].nunique()),
        "btg_combo_ex_controlados_pl_brl": float(current.loc[triple_btg_ex_controlled, "pl"].sum()),
        "fundos_contas_observadas": int(holder["cnpj_fundo"].nunique()),
        "pl_contas_observadas_brl": holder_pl,
        "fundos_ate_5_contas": int(holder.loc[up_to_5, "cnpj_fundo"].nunique()),
        "share_fundos_ate_5_contas": float(up_to_5.mean()),
        "share_pl_ate_5_contas": float(holder.loc[up_to_5, "pl"].sum()) / holder_pl,
        "share_fundos_ate_10_contas": float(up_to_10.mean()),
        "share_pl_ate_10_contas": float(holder.loc[up_to_10, "pl"].sum()) / holder_pl,
        "holder_ge_200m_fundos": int(holder_ge_200m["cnpj_fundo"].nunique()),
        "holder_ge_200m_pl_brl": holder_ge_200m_pl,
        "holder_ge_200m_fundos_ate_10_contas": int(
            holder_ge_200m_up_to_10.sum()
        ),
        "holder_ge_200m_share_fundos_ate_10_contas": float(
            holder_ge_200m_up_to_10.mean()
        ),
        "holder_ge_200m_share_pl_ate_10_contas": (
            float(holder_ge_200m.loc[holder_ge_200m_up_to_10, "pl"].sum())
            / holder_ge_200m_pl
            if holder_ge_200m_pl
            else None
        ),
        "holder_definition": "contas reportadas por fundo/classe, agregadas ao CNPJ legal; não equivalem a investidores únicos",
        "btg_combo_definition": (
            "PL ex-FIC-FIDC com administração, gestão e custódia no grupo BTG; "
            "a exclusão cobre seis CNPJs com controle confirmado na DF BTG 1T26"
        ),
        **service_metrics,
        **btg_bank_metrics,
        **transition_metrics,
    }


def _offers_ytd(offers: pd.DataFrame, *, as_of_date: str) -> pd.DataFrame:
    frame = offers.copy()
    frame["registration_date"] = pd.to_datetime(frame["registration_date"], errors="coerce")
    frame["year"] = frame["registration_date"].dt.year
    cutoff = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(cutoff):
        cutoff = pd.Timestamp(year=2026, month=7, day=15)
    cutoff_month_day = (int(cutoff.month), int(cutoff.day))
    comparison_years = list(range(int(cutoff.year) - 2, int(cutoff.year) + 1))
    frame = frame[
        frame["year"].isin(comparison_years)
        & frame["valid_offer"].fillna(False).astype(bool)
        & frame["registration_date"].notna()
    ].copy()
    frame = frame[
        (frame["registration_date"].dt.month < cutoff_month_day[0])
        | (
            frame["registration_date"].dt.month.eq(cutoff_month_day[0])
            & frame["registration_date"].dt.day.le(cutoff_month_day[1])
        )
    ]
    return frame.groupby("year", as_index=False).agg(
        ofertas=("offer_id", "nunique"), volume=("registered_volume_brl", "sum")
    )


def _originators(originators: pd.DataFrame, year: int) -> dict[str, Any]:
    scoped = originators[originators["year"].eq(year)].copy()
    scoped = scoped[~scoped["originator_group"].astype(str).eq("Não identificado")]
    scoped = scoped.sort_values(["rank", "volume_brl"], ascending=[True, False]).head(5)
    coverage = float(scoped["identified_volume_coverage"].dropna().iloc[0]) if not scoped.empty else None
    return {"coverage": coverage, "rows": _records(scoped[["originator_group", "volume_brl", "share_of_total", "confidence"]])}


def _load_curation(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            for key in ("rows", "top20", "curadoria", "funds"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        return pd.DataFrame(payload if isinstance(payload, list) else [])
    return pd.read_csv(path, low_memory=False)


def _pick(row: pd.Series, *names: str) -> str:
    for name in names:
        if name in row.index:
            value = _text(row.get(name))
            if value:
                return value
    return ""


def _usable_profile_text(value: object) -> str:
    text = _text(value)
    normalized = text.casefold()
    if (
        not text
        or normalized == "não identificado"
        or normalized.startswith("não identificado no")
        or normalized.startswith("campo não identificado")
    ):
        return ""
    if normalized.startswith("não identificado como entidade única;"):
        return (
            "Os documentos não apontam uma entidade cedente única;"
            + text.split(";", 1)[1]
        )
    return text


def _build_profiles(
    top20: pd.DataFrame,
    curation: pd.DataFrame,
    documentary: pd.DataFrame,
    *,
    latest: str,
) -> pd.DataFrame:
    cur = curation.copy()
    if not cur.empty:
        cnpj_col = next((c for c in ("cnpj", "cnpj_fundo", "cnpj_14") if c in cur.columns), None)
        cur["cnpj_key"] = cur[cnpj_col].map(_digits) if cnpj_col else ""
        cur = cur.drop_duplicates("cnpj_key", keep="last").set_index("cnpj_key")
    doc = documentary.copy()
    if not doc.empty:
        doc["cnpj_key"] = doc["cnpj"].map(_digits)
        doc = doc.drop_duplicates("cnpj_key", keep="last").set_index("cnpj_key")
    profiles: list[dict[str, Any]] = []
    origin_labels = {
        "oficial_anbima_snapshot": "Classificação oficial ANBIMA por CNPJ da classe",
        "nao_identificado": "Sem classificação ANBIMA no snapshot consultado",
        "evidencia_documental": "Evidência documental primária",
        "evidencia_publicada": "Evidência documental primária",
        "proxy_cvm": "Proxy determinístico a partir do Informe Mensal CVM",
    }
    for _, fund in top20.sort_values("rank").iterrows():
        key = _digits(fund.get("cnpj_fundo"))
        curated = cur.loc[key] if not cur.empty and key in cur.index else pd.Series(dtype=object)
        documented = doc.loc[key] if not doc.empty and key in doc.index else pd.Series(dtype=object)
        nature = _usable_profile_text(
            _pick(
                curated,
                "natureza_recebiveis",
                "natureza_dos_recebiveis",
                "recebiveis",
            )
        )
        if not nature:
            d1 = _pick(documented, "document_segment_n1")
            d2 = _pick(documented, "document_segment_n2")
            nature = " — ".join(item for item in (d1, d2) if item)
        evidence = _usable_profile_text(
            _pick(
                curated,
                "evidencia",
                "evidencia_resumo",
                "trecho_evidencia",
            )
        )
        evidence = evidence or _pick(
            curated,
            "nota_classificacao",
            "segmento_economico_documental",
        )
        if not evidence:
            evidence = _usable_profile_text(
                _pick(documented, "classification_evidence")[:280]
            )
        source = _usable_profile_text(
            _pick(curated, "fonte", "fontes", "source", "url", "links")
        )
        source = source or _pick(curated, "fundosnet_gerenciador")
        if not source:
            source = _pick(documented, "source")
        classes = _usable_profile_text(
            _pick(
                curated,
                "classes_subordinacao_garantias",
                "classes_subordinacao",
                "classes",
                "subordinacao_garantias",
            )
        )
        guarantees = _pick(curated, "garantias")
        if guarantees and guarantees not in classes:
            classes = f"{classes} Garantias: {guarantees}".strip()
        consultation_date = _pick(curated, "data_consulta", "consulted_at") or "2026-07-24"
        missing_by_field = {
            "cedente_originador": "Cedente/originador não localizado nas fontes consultadas.",
            "sacado_devedor": "Sacado ou perfil de devedores não localizado nas fontes consultadas.",
            "natureza_recebiveis": "Natureza dos recebíveis não localizada nas fontes consultadas.",
            "funcionamento_economico": "Mecânica econômica não localizada nas fontes consultadas.",
            "emissoes": "Emissões relevantes não localizadas nas fontes consultadas.",
            "classes_subordinacao_garantias": (
                "Classes, subordinação e garantias não localizadas nas fontes consultadas."
            ),
        }
        profile_values = {
            "cedente_originador": _usable_profile_text(
                _pick(curated, "cedente_originador", "cedente", "originador")
            ),
            "sacado_devedor": _usable_profile_text(
                _pick(
                    curated,
                    "sacado_devedor",
                    "sacado",
                    "devedor",
                    "perfil_sacados",
                )
            ),
            "natureza_recebiveis": nature,
            "funcionamento_economico": _usable_profile_text(
                _pick(
                    curated,
                    "funcionamento_economico",
                    "funcionamento",
                    "mecanica",
                )
            ),
            "emissoes": _usable_profile_text(
                _pick(curated, "emissoes", "emissoes_relevantes", "ofertas")
            ),
            "classes_subordinacao_garantias": classes,
        }
        identified_fields = sum(bool(value) for value in profile_values.values())
        coverage_label = _pick(
            curated, "cobertura_documental", "document_coverage"
        ) or f"{identified_fields}/6 campos documentais preenchidos"
        curated_type = _usable_profile_text(_pick(curated, "tipo_anbima"))
        curated_focus = _usable_profile_text(_pick(curated, "foco_anbima"))
        raw_origin = (
            _pick(curated, "origem_tipo_foco")
            if curated_type or curated_focus
            else ""
        ) or _text(fund.get("classification_status")) or "N/D"
        readable_origin = origin_labels.get(raw_origin, raw_origin.replace("_", " ").strip())
        fields = {
            "rank": int(fund["rank"]),
            "cnpj_fundo": key,
            "cnpj_fundo_formatado": _text(fund.get("cnpj_fundo_formatado")),
            "denominacao": _text(fund.get("denominacao")),
            "nome_curto": _display_fund_name(fund.get("denominacao")),
            "pl": float(fund["pl"]),
            "market_share_ex_fic": float(fund["market_share_ex_fic"]),
            **{
                name: value or missing_by_field[name]
                for name, value in profile_values.items()
            },
            "administrador": _pick(curated, "administrador") or _text(fund.get("admin_nome")) or "não informado",
            "gestor": _pick(curated, "gestor") or _text(fund.get("gestor_nome")) or "não informado",
            "custodiante": _pick(curated, "custodiante") or _text(fund.get("custodiante_nome")) or "não informado",
            "anbima_tipo": curated_type
            or _text(fund.get("anbima_tipo"))
            or "N/D",
            "anbima_foco": curated_focus
            or _text(fund.get("anbima_foco"))
            or "N/D",
            "origem_classificacao": readable_origin,
            "fonte": source
            or (
                "FundosNet e CVM SRE consultados em "
                f"{consultation_date}; documento primário não localizado"
            ),
            "data_consulta": consultation_date,
            "evidencia": evidence
            or _pick(curated, "nota_classificacao", "segmento_economico_documental")
            or "Sem trecho citável no corpus consultado.",
            "status_curadoria": _pick(curated, "status_curadoria") or "pendente",
            "campos_nao_identificados": _pick(curated, "campos_nao_identificados")
            or "Ver campos documentais sem preenchimento.",
            "documentos_primarios_ids": _pick(curated, "documentos_primarios_ids")
            or "Nenhum documento primário localizado.",
            "cobertura_documental": coverage_label,
            "data_referencia_tipo_foco": (
                _pick(curated, "data_referencia_tipo_foco") or latest
            ),
        }
        profiles.append(fields)
    return pd.DataFrame(profiles)


def _build_top20_outros_review(
    top20_outros: pd.DataFrame,
    documentary: pd.DataFrame,
    regulation_review: pd.DataFrame,
) -> pd.DataFrame:
    doc = documentary.copy()
    if not doc.empty:
        doc["cnpj_key"] = doc["cnpj"].map(_digits)
        doc = doc.drop_duplicates("cnpj_key", keep="last").set_index("cnpj_key")
    regulations = regulation_review.copy()
    if not regulations.empty:
        regulations["cnpj_key"] = regulations["cnpj_fundo"].map(_digits)
        regulations = regulations.drop_duplicates(
            "cnpj_key", keep="last"
        ).set_index("cnpj_key")
    rows: list[dict[str, Any]] = []
    for _, fund in top20_outros.sort_values("rank_outros").iterrows():
        key = _digits(fund.get("cnpj_fundo"))
        evidence = doc.loc[key] if not doc.empty and key in doc.index else pd.Series(dtype=object)
        regulation = (
            regulations.loc[key]
            if not regulations.empty and key in regulations.index
            else pd.Series(dtype=object)
        )
        d1 = _pick(evidence, "document_segment_n1")
        d2 = _pick(evidence, "document_segment_n2")
        hypothesis = " — ".join(item for item in (d1, d2) if item)
        if d1 and d2:
            authored_evidence = (
                f"O regulamento enquadra a carteira em {d2}, dentro de {d1}."
            )
        elif d1:
            authored_evidence = (
                f"O documento primário sustenta o enquadramento em {d1}."
            )
        else:
            authored_evidence = "Sem trecho citável no corpus consultado."
        rows.append(
            {
                **{key_: _json_value(value) for key_, value in fund.items()},
                "nome_curto": _display_fund_name(fund.get("denominacao")),
                "classificacao_oficial": " | ".join(
                    item for item in (_text(fund.get("anbima_tipo")), _text(fund.get("anbima_foco"))) if item
                ) or "N/D",
                "hipotese_revisao": hypothesis or "Sem hipótese documental.",
                "evidencia_revisao": authored_evidence,
                "fonte_revisao": _pick(evidence, "source")
                or "Fonte primária não localizada no corpus consultado.",
                "status_revisao": (
                    _pick(regulation, "reclassification_status")
                    or (
                        f"evidência documental — {_pick(evidence, 'classification_confidence')}"
                        if hypothesis
                        else "pendente"
                    )
                ),
                "cedente_originador_regulamento": _pick(
                    regulation, "cedent_originator_explicit"
                ) or "N/D",
                "regulamento_id": _pick(regulation, "document_id") or "N/D",
                "regulamento_data": _pick(
                    regulation, "document_reference_date"
                ) or "N/D",
                "regulamento_url": _pick(regulation, "document_url"),
                "categoria_proposta_regulamento": _pick(
                    regulation, "proposed_category"
                ) or "N/D",
                "motivo_validacao_manual": _pick(
                    regulation, "manual_validation_reason"
                ) or "N/D",
            }
        )
    return pd.DataFrame(rows)


def build_payload(
    data_dir: Path,
    revision_dir: Path,
    curation_path: Path,
    latest: str,
) -> dict[str, Any]:
    monthly = pd.read_csv(data_dir / "industry_monthly.csv", low_memory=False)
    fic_detection_audit = _read_optional(
        data_dir / "industry_fic_detection_audit.csv",
        cnpj_columns=("cnpj_fundo",),
    )
    competence_status = _read_optional(data_dir / "industry_competence_status.csv")
    vehicle = pd.read_csv(data_dir / "vehicle_monthly.csv.gz", low_memory=False)
    cotistas = pd.read_csv(data_dir / "cotistas_tipo_monthly.csv", low_memory=False)
    segments = pd.read_csv(data_dir / "segments_monthly.csv", low_memory=False)
    providers = pd.read_csv(data_dir / "prestadores_latest.csv", low_memory=False)
    documentary = _read_optional(data_dir / "industry_large_fund_classification.csv")
    top20_outros_regulations = _read_optional(
        data_dir / "industry_top20_outros_regulation_review.csv"
    )
    acquiring_curation = _read_optional(
        data_dir / "acquiring_reclassification_curation.csv",
        cnpj_columns=("cnpj14_digits",),
    )
    card_receivables_curation = _read_optional(
        data_dir / "card_receivables_curation.csv",
        cnpj_columns=("cnpj14_digits",),
    )
    document_inventory = _read_optional(
        data_dir / "document_inventory.csv.gz",
        cnpj_columns=("cnpj_fundo",),
    )
    taxonomy_document_review = _read_optional(
        data_dir / "industry_taxonomy_document_review.csv",
        cnpj_columns=("cnpj_fundo",),
    )
    manual_cnpj_enrichment = _load_manual_cnpj_enrichment(
        data_dir / "industry_cnpj_manual_enrichment.csv"
    )
    top100_plus2_2026_curation = _load_top100_plus2_curation(
        data_dir / "top100_plus2_2026_curation.csv"
    )
    carteira_101_document_audit = load_document_audit_materialization(
        data_dir / "carteira_101_document_audit"
    )
    historical_top20_document_review = _read_optional(
        data_dir / "industry_top20_taxonomy_document_review.csv",
        cnpj_columns=("cnpj_fundo",),
    )
    historical_top20_document_conclusions = _read_optional(
        data_dir / "industry_top20_taxonomy_document_conclusions.csv",
        cnpj_columns=("cnpj_fundo",),
    )
    if (
        not historical_top20_document_review.empty
        or not historical_top20_document_conclusions.empty
    ):
        taxonomy_document_review = _merge_documentary_review_layers(
            historical_top20_document_review,
            historical_top20_document_conclusions,
            taxonomy_document_review,
        )
    taxonomy_review_path = data_dir / "taxonomy_review_actions.csv"
    taxonomy_review_audit_path = data_dir / "taxonomy_review_audit.csv"
    assert_taxonomy_review_ledger_matches_audit(
        taxonomy_review_path,
        taxonomy_review_audit_path,
    )
    taxonomy_review_actions = load_taxonomy_review_actions(taxonomy_review_path)

    funds = pd.read_csv(revision_dir / "base_fundo_cnpj.csv.gz", low_memory=False)
    qa = pd.read_csv(revision_dir / "qa_inadimplencia_competencia.csv", low_memory=False)
    receivables_reconciliation_summary = _read_optional(
        revision_dir / "reconciliacao_tabelas_i_ii_resumo.csv"
    )
    receivables_reconciliation_detail = _read_optional(
        revision_dir / "reconciliacao_tabelas_i_ii_detalhe.csv",
        cnpj_columns=("cnpj_fundo",),
    )
    bridge_summary = pd.read_csv(
        revision_dir / "bridge_inadimplencia_2024-06_2024-07_resumo.csv", low_memory=False
    )
    bridge_detail = pd.read_csv(
        revision_dir / "bridge_inadimplencia_2024-06_2024-07_detalhe.csv", low_memory=False
    )
    top20 = pd.read_csv(revision_dir / "top20_fidcs.csv", dtype={"cnpj_fundo": str})
    top20 = apply_taxonomy_review_overlay(top20, taxonomy_review_actions)
    top20_outros = pd.read_csv(revision_dir / "top20_outros.csv", dtype={"cnpj_fundo": str})
    mono = pd.read_csv(revision_dir / "monoestrutura_por_fundo.csv", low_memory=False)
    mono_concentration = pd.read_csv(revision_dir / "monoestrutura_concentracao.csv", low_memory=False)
    if not mono_concentration.empty:
        mono_concentration["maior_fundo_nome_curto"] = mono_concentration[
            "maior_fundo"
        ].map(_display_fund_name)
    market = pd.read_csv(revision_dir / "market_share_por_subtipo.csv", low_memory=False)
    fixed_top10 = pd.read_csv(revision_dir / "market_share_top10_fixo.csv", low_memory=False)
    market_scope = pd.read_csv(
        revision_dir / "market_share_escopo_resumo.csv", low_memory=False
    )
    provider_historical_ranking = pd.read_csv(
        revision_dir / "prestadores_ranking_historico.csv", low_memory=False
    )
    provider_independent_ranking = _read_optional(
        revision_dir / "prestadores_independentes_ranking.csv"
    )
    bank_fidc_evolution = _read_optional(
        revision_dir / "bancos_fidcs_evolucao.csv"
    )
    bank_fidc_detail = _read_optional(
        revision_dir / "bancos_fidcs_detalhe.csv",
        cnpj_columns=("cnpj_fundo",),
    )
    acquiring_reclassified_mix = _read_optional(
        revision_dir / "adquirencia_mix_reclassificado.csv"
    )
    delinquency_single_receivable = _read_optional(
        revision_dir / "inadimplencia_tipo_recebivel_unico.csv"
    )
    delinquency_single_receivable_summary = _read_optional(
        revision_dir / "inadimplencia_tipo_recebivel_unico_resumo.csv"
    )
    delinquency_frozen_cohort_history = _read_optional(
        revision_dir / "inadimplencia_coorte_atual_historico.csv"
    )
    delinquency_frozen_cohort_summary = _read_optional(
        revision_dir / "inadimplencia_coorte_atual_resumo.csv"
    )
    delinquency_cohort_revision_summary = _read_optional(
        revision_dir / "inadimplencia_coorte_revisao_resumo.csv"
    )
    delinquency_cohort_revision_transitions = _read_optional(
        revision_dir / "inadimplencia_coorte_revisao_transicoes.csv"
    )
    delinquency_cohort_revision_sensitivity = _read_optional(
        revision_dir / "inadimplencia_coorte_revisao_sensibilidade.csv"
    )
    delinquency_dispersion = _read_optional(
        revision_dir / "inadimplencia_dispersao_subcategoria.csv"
    )
    delinquency_dispersion_summary = _read_optional(
        revision_dir / "inadimplencia_dispersao_resumo.csv"
    )
    provider_transition_summary = _read_optional(
        revision_dir / "prestadores_transicoes_resumo.csv"
    )
    provider_transition_links = _read_optional(
        revision_dir / "prestadores_transicoes_links.csv"
    )
    provider_transition_detail = _read_optional(
        revision_dir / "prestadores_transicoes_detalhe.csv",
        cnpj_columns=(
            "cnpj_fundo",
            "admin_origem_cnpj",
            "admin_destino_cnpj",
        ),
    )
    provider_transition_role_availability = _read_optional(
        revision_dir / "prestadores_transicoes_disponibilidade.csv"
    )
    provider_history_cvm_coverage = _read_optional(
        revision_dir / "prestadores_historico_cvm_cobertura.csv"
    )
    provider_history_cvm_links = _read_optional(
        revision_dir / "prestadores_historico_cvm_transicoes_links.csv"
    )
    provider_history_cvm_detail = _read_optional(
        revision_dir / "prestadores_historico_cvm_transicoes_detalhe.csv.gz",
        cnpj_columns=("cnpj_fundo",),
    )
    if not provider_history_cvm_detail.empty and "comparavel" in provider_history_cvm_detail:
        comparable = provider_history_cvm_detail["comparavel"].astype(str).str.lower().isin(
            {"true", "1", "sim"}
        )
        provider_history_cvm_detail = provider_history_cvm_detail.loc[comparable].copy()
    reag_admin_summary = _read_optional(
        revision_dir / "reag_cbsf_coorte_resumo.csv",
        cnpj_columns=("origin_admin_cnpj",),
    )
    reag_admin_links = _read_optional(
        revision_dir / "reag_cbsf_coorte_links.csv",
        cnpj_columns=("admin_destino_cnpj",),
    )
    reag_admin_detail = _read_optional(
        revision_dir / "reag_cbsf_coorte_detalhe.csv",
        cnpj_columns=(
            "cnpj_fundo",
            "admin_origem_cnpj",
            "admin_destino_cnpj_observado",
            "gestor_destino_cnpj_observado",
            "custodiante_destino_cnpj_observado",
            "admin_destino_cnpj",
        ),
    )
    provider_leadership_attribution = _read_optional(
        revision_dir / "prestadores_lideranca_atribuicao.csv"
    )
    btg_controlled_reconciliation = _read_optional(
        revision_dir / "btg_fidcs_controlados_reconciliacao.csv",
        cnpj_columns=(
            "cnpj_veiculo",
            "cnpj_fundo",
            "admin_cnpj",
            "gestor_cnpj",
            "custodiante_cnpj",
        ),
    )
    btg_provider_ex_controlled_scenario = _read_optional(
        revision_dir / "btg_prestadores_ex_controlados.csv"
    )
    qi_legacy_attribution = _read_optional(
        revision_dir / "qi_atribuicao_cnpjs_legados.csv",
        cnpj_columns=("provider_cnpj",),
    )
    acquiring_path = data_dir / "acquiring_taxonomy_curation.json"
    acquiring_taxonomy = (
        json.loads(acquiring_path.read_text(encoding="utf-8"))
        if acquiring_path.exists()
        else {"summary": {}, "funds": [], "sources": []}
    )

    closed_offers = build_closed_offers_payload(data_dir)
    closed_offer_placement_regime = (
        load_materialized_closed_offer_placement_regime(data_dir)
    )
    offer_ticket_outputs = load_materialized_offer_ticket_outputs(data_dir)
    fixed_income_offer_comparison = (
        load_materialized_fixed_income_offer_comparison(data_dir)
    )
    market_offer_reconciliation = (
        load_materialized_market_offer_reconciliation(data_dir)
    )
    issuance_taxonomy, issuance_taxonomy_coverage = build_issuance_taxonomy(data_dir)
    # Standalone payload builds must not consume a stale pre-ledger CSV.
    write_issuance_taxonomy(issuance_taxonomy, data_dir)
    issuance_taxonomy_table = build_wide_table(issuance_taxonomy)
    offer_cohort = pd.read_csv(
        data_dir / "industry_closed_offer_ticket_cohort.csv.gz",
        compression="gzip",
        low_memory=False,
    )
    offer_target_public_shares = _offer_target_public_shares(offer_cohort)
    anbima_outros_reclassification, cvm_outros_reclassification = (
        _reclassification_exports(funds, latest=latest)
    )
    bcb_expanded_credit = load_materialized_expanded_credit_history(data_dir)
    closed_offer_ticket_distribution = offer_ticket_outputs.distribution.copy()
    offer_rankings = build_closed_offer_top15(data_dir)
    closed_offer_top15 = offer_rankings.rankings.copy()
    closed_offer_top15["fund_name_short"] = closed_offer_top15[
        "nome_emissor"
    ].map(_display_fund_name)
    closed_offer_top15_summary = offer_rankings.summary.copy()
    closed_annual = closed_offers["annual"]["rows"]
    closed_monthly = closed_offers["monthly"]["rows"]
    closed_jan_june = closed_offers["jan_june_2024_2026"]["rows"]
    closed_originators = closed_offers["originators_2026_ytd"]["rows"]
    closed_source = closed_offers["annual"]["source"]
    card_taxonomy_audit, card_taxonomy_summary = _card_taxonomy_audit(
        vehicle,
        funds,
        acquiring_curation,
        latest=latest,
        card_curation=card_receivables_curation,
    )
    included_card = card_taxonomy_audit[
        card_taxonomy_audit["status_curadoria"].eq("Incluído em Adquirência")
    ].copy()
    requested_type_labels = {
        "OUTROS": "Outros",
        "FOMENTO MERCANTIL": "Fomento Mercantil",
        "AGRO, INDUSTRIA E COMERCIO": "Agro Indústria e Comércio",
        "AGRO INDUSTRIA E COMERCIO": "Agro Indústria e Comércio",
        "FINANCEIRO": "Financeiro",
    }

    def suggested_reference_category(value: object) -> str:
        raw = "" if value is None or pd.isna(value) else str(value).strip()
        if not raw:
            return "N/D — Tipo ANBIMA ausente"
        return requested_type_labels.get(
            _fold_text(raw),
            "N/D — Tipo ANBIMA fora das quatro categorias de referência",
        )

    acquiring_anbima_review = included_card[
        [
            "cnpj_fundo_formatado",
            "denominacao",
            "pl_referencia_brl",
            "pl_referencia_competencia",
            "anbima_tipo",
            "anbima_foco",
            "classification_source",
            "classification_status",
        ]
    ].copy()
    acquiring_anbima_review["tipo_anbima_atual"] = acquiring_anbima_review[
        "anbima_tipo"
    ].where(acquiring_anbima_review["anbima_tipo"].fillna("").astype(str).str.strip().ne(""), "N/D")
    acquiring_anbima_review["foco_anbima_atual"] = acquiring_anbima_review[
        "anbima_foco"
    ].where(acquiring_anbima_review["anbima_foco"].fillna("").astype(str).str.strip().ne(""), "N/D")
    acquiring_anbima_review["categoria_referencia_sugerida"] = acquiring_anbima_review[
        "anbima_tipo"
    ].map(suggested_reference_category)
    acquiring_anbima_review["base_alterada"] = "Não"
    acquiring_anbima_review["criterio_sugestao"] = (
        "correspondência literal do Tipo ANBIMA atual com uma das quatro categorias de referência; sem uso do nome do fundo ou de fonte indireta"
    )
    acquiring_anbima_review = acquiring_anbima_review.sort_values(
        ["denominacao", "cnpj_fundo_formatado"]
    ).reset_index(drop=True)

    taxonomy_top15_rows: list[dict[str, object]] = []
    for _, row in top20.head(15).sort_values("rank").iterrows():
        cnpj = _digits(row.get("cnpj_fundo"))
        reported_table_ii = _text(row.get("segmento_principal")) or "N/D"
        curated_table_ii = _text(row.get("tabela_ii_curada"))
        if not curated_table_ii or curated_table_ii == "N/D":
            curated_table_ii = reported_table_ii
        views = (
            (
                "Tipo ANBIMA reclassificado",
                _text(row.get("anbima_tipo_curado")) or "N/D",
            ),
            (
                "Foco ANBIMA reclassificado",
                _text(row.get("anbima_foco_curado")) or "N/D",
            ),
            ("Tabela II reportada", reported_table_ii),
            (
                "Tabela II reclassificada",
                curated_table_ii,
            ),
        )
        for view, taxonomy in views:
            taxonomy_top15_rows.append(
                {
                    "visao": view,
                    "rank": int(row.get("rank") or 0),
                    "cnpj_fundo": cnpj,
                    "cnpj_fundo_formatado": str(row.get("cnpj_fundo_formatado") or ""),
                    "denominacao": str(row.get("denominacao") or "N/D"),
                    "taxonomia_atual": taxonomy,
                    "pl_brl": float(row.get("pl") or 0.0),
                    "competencia": latest,
                    "fonte": (
                        "ANBIMA Data, fotografia cadastral de dez/25"
                        if "ANBIMA" in view
                        else f"CVM, Informe Mensal FIDC, Tabela II, {latest}"
                    ),
                    "metodologia": (
                        "overlay analítico aprovado por CNPJ; campos oficiais preservados no payload"
                        if "reclassificado" in view.lower()
                        else "Tabela II original preservada na visão reportada"
                    ),
                }
            )
    taxonomy_top15 = pd.DataFrame(taxonomy_top15_rows)
    acquiring_curation_detail = _acquiring_curation_detail(
        acquiring_curation,
        card_taxonomy_audit,
        funds,
        acquiring_taxonomy,
        latest=latest,
    )

    stock_preliminary_status: dict[str, Any] = {}
    if not competence_status.empty:
        candidates = competence_status[
            competence_status["competencia"].astype(str).gt(latest)
            & ~competence_status["publication_status"].astype(str).eq("completa")
        ].sort_values("competencia")
        if not candidates.empty:
            row = candidates.iloc[-1]
            stock_preliminary_status = {
                "competencia": str(row.get("competencia") or ""),
                "publication_status": str(row.get("publication_status") or ""),
                "status_reason": str(row.get("status_reason") or ""),
                "n_veiculos": _json_value(row.get("n_veiculos")),
                "pl_total_brl": _json_value(row.get("pl_total")),
                "previous_vehicles": _json_value(row.get("previous_vehicles")),
                "previous_pl_brl": _json_value(row.get("previous_pl_brl")),
                "vehicle_ratio_vs_previous": _json_value(
                    row.get("vehicle_ratio_vs_previous")
                ),
                "pl_ratio_vs_previous": _json_value(row.get("pl_ratio_vs_previous")),
                "generated_at_utc": str(row.get("generated_at_utc") or ""),
            }

    annual = _last_observation_by_year(monthly, latest)
    annual_pl = annual[["year", "competencia", "pl_total", "pl_fic_fidc"]].copy()
    annual_pl = _apply_detected_fic_history(annual_pl, fic_detection_audit)
    pl_total_cagr_periods = _pl_total_cagr_periods(annual_pl)
    bcb_total_growth_periods = _bcb_total_growth_periods(bcb_expanded_credit)
    annual_base = annual[["year", "competencia", "cotistas_total", "n_veiculos"]].copy()

    reconciliation_audit_slice = receivables_reconciliation_detail[
        pd.to_numeric(
            receivables_reconciliation_detail.get(
                "rank_gap_positivo",
                pd.Series(dtype=float),
            ),
            errors="coerce",
        ).le(100)
        | ~receivables_reconciliation_detail.get(
            "tabela_ii_reportada",
            pd.Series(False, index=receivables_reconciliation_detail.index),
        ).fillna(False).astype(bool)
    ].copy()

    latest_month = monthly[monthly["competencia"].astype(str).eq(latest)].iloc[0]
    offers_as_of = str(closed_source.get("latest_source_closing_date") or "2026-06-30")
    offers_source_as_of = str(closed_source.get("as_of_date") or "2026-07-21")
    latest_period = pd.Period(latest, freq="M")
    latest_months = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
    latest_label = f"{latest_months[latest_period.month - 1]}/{str(latest_period.year)[-2:]}"
    comparison_periods = [HISTORICAL_REFERENCE, latest]
    type_mix_periods = ["2023-12", "2024-12", "2025-12", latest]
    holder_distribution_history, holder_distribution_meta_history = _holder_distribution_history(
        vehicle, comparison_periods
    )
    (
        type_mix_history,
        classification_coverage_history,
        type_mix_meta,
    ) = _type_mix_history(
        funds, type_mix_periods
    )
    type_mix_history_official = type_mix_history.copy()
    for mix_period in type_mix_periods:
        curated_period_mix = build_curated_type_mix(
            funds,
            taxonomy_review_actions,
            latest=mix_period,
        )
        curated_lookup = curated_period_mix.set_index("anbima_tipo")
        period_mask = type_mix_history["competencia"].eq(mix_period)
        for index in type_mix_history[period_mask].index:
            category = str(type_mix_history.at[index, "anbima_tipo"])
            if category in curated_lookup.index:
                type_mix_history.at[index, "pl"] = float(
                    curated_lookup.at[category, "pl"]
                )
                type_mix_history.at[index, "share"] = float(
                    curated_lookup.at[category, "share"]
                )
    type_mix_meta["taxonomy_review_overlay"] = {
        "ledger_sha256": taxonomy_review_ledger_digest(taxonomy_review_path),
        "decisions_effective": int(
            taxonomy_review_actions.get(
                "status", pd.Series(dtype="object")
            ).eq("aprovado").sum()
        ),
        "official_history_preserved_in": "type_mix_history_official",
    }
    taxonomy_level_history = build_curated_taxonomy_level_history(
        funds,
        taxonomy_review_actions,
        periods=tuple(type_mix_periods),
        table_ii=vehicle,
    )
    carteira_1_taxonomy_history, carteira_1_taxonomy_summary = (
        _portfolio_type_mix_history(
            funds,
            taxonomy_review_actions,
            scope=pd.read_csv(
                data_dir / "industry_carteira_1_scope.csv",
                dtype={"cnpj_fundo": str},
                keep_default_na=False,
            ),
            periods=type_mix_periods,
            market_history=type_mix_history,
        )
    )
    receivables_history, receivables_meta_history = _receivables_history(
        segments, monthly, comparison_periods
    )
    provider_concentration_history = _provider_concentration_history(
        funds, [PROVIDER_REFERENCE, latest]
    )
    type_mix = type_mix_history[type_mix_history["competencia"].eq(latest)].drop(
        columns="competencia"
    )
    classification_coverage = classification_coverage_history[
        classification_coverage_history["competencia"].eq(latest)
    ].drop(columns="competencia")
    receivables = _receivables(segments, latest, float(latest_month["carteira_dc"]))
    qa_latest = qa[qa["competencia"].astype(str).eq(latest)].iloc[0].to_dict()
    qa_series = qa[qa["competencia"].astype(str).between("2023-01", latest)].copy()
    qa_series = qa_series[
        [
            "competencia",
            "inadimplencia_bruta_pct",
            "inadimplencia_ajustada_pct",
            "inadimplencia_ajustada_ex_np_pct",
            "cobertura_carteira",
        ]
    ]
    atlantic = bridge_detail[
        bridge_detail["cnpj"].map(_digits).eq("09194841000151")
        | bridge_detail["cnpj_fundo"].map(_digits).eq("09194841000151")
    ].copy()
    atlantico_profile, atlantico_history = _atlantico_payload(funds, data_dir, latest)

    curation = _load_curation(curation_path)
    profile_overrides = _read_optional(
        data_dir / "top20_profile_curation_overrides.csv",
        cnpj_columns=("cnpj_fundo",),
    )
    if not profile_overrides.empty:
        curation = pd.concat(
            [curation, profile_overrides],
            ignore_index=True,
            sort=False,
        )
    profiles = _build_profiles(
        top20,
        curation,
        documentary,
        latest=latest,
    )
    flagship_curation = build_flagship_curation(
        scope_path=data_dir / "industry_flagship_scope.csv",
        documentary_path=(
            data_dir / "industry_flagship_document_curation.csv"
        ),
        funds=funds,
        vehicle=vehicle,
        latest=latest,
        deep_dives_dir=ROOT / "data" / "deep_dives",
    )
    carteira_1_curation = build_portfolio_curation(
        scope_path=data_dir / "industry_carteira_1_scope.csv",
        documentary_path=data_dir / "industry_carteira_1_document_curation.csv",
        funds=funds,
        vehicle=vehicle,
        taxonomy_actions=taxonomy_review_actions,
        latest=latest,
    )
    carteira_1_flagship_comparison = build_portfolio_flagship_comparison(
        portfolio_detail=carteira_1_curation.detail,
        flagship_detail=flagship_curation.detail,
        latest=latest,
    )
    carteira_1_structural_risk = build_portfolio_structural_risk(
        portfolio=carteira_1_curation,
        comparison=carteira_1_flagship_comparison,
    )
    portfolio_export = build_industry_portfolio_export(
        carteira_detail=carteira_1_curation.detail,
        carteira_structural=carteira_1_structural_risk.assets,
        flagship_detail=flagship_curation.detail,
        manual_enrichment=manual_cnpj_enrichment,
        carteira_document_audit=carteira_101_document_audit.audit,
        carteira_price_evidence=carteira_101_document_audit.prices,
        data_ref=latest,
    )
    top20_outros_review = _build_top20_outros_review(
        top20_outros, documentary, top20_outros_regulations
    )
    reclassification_candidates = top20_outros_review[
        top20_outros_review["status_revisao"].eq(
            "potencial_reclassificação"
        )
    ]
    top20_outros_reclassification_summary = {
        "candidate_funds": int(len(reclassification_candidates)),
        "candidate_pl_brl": float(
            reclassification_candidates["pl"].sum()
        ),
        "candidate_share_of_outros": float(
            reclassification_candidates["market_share_outros"].sum()
        ),
        "candidate_share_of_ex_fic": float(
            reclassification_candidates["market_share_ex_fic"].sum()
        ),
        "manual_validation_funds": int(
            top20_outros_review["status_revisao"].eq(
                "validação_manual"
            ).sum()
        ),
        "methodology": (
            "Potencial considera somente regulamentos com evidência expressa "
            "compatível com categoria já existente fora de Outros; nenhuma "
            "mudança taxonômica é aplicada automaticamente."
        ),
    }
    top20_by_anbima_type, top20_by_anbima_type_coverage = (
        build_top20_by_anbima_type(
            funds,
            latest=latest,
            actions=taxonomy_review_actions,
            curated_top20=curation,
            regulation_review=top20_outros_regulations,
            document_inventory=document_inventory,
            card_curation=card_receivables_curation,
            document_review=taxonomy_document_review,
        )
    )
    top20_taxonomy_review = build_historical_top20_taxonomy_review(
        funds,
        taxonomy_review_actions,
        periods=tuple(type_mix_periods),
        table_ii=vehicle,
        curated_top20=curation,
        regulation_review=top20_outros_regulations,
        document_inventory=document_inventory,
        card_curation=card_receivables_curation,
        document_review=taxonomy_document_review,
    )
    emission_field_audit = _load_emission_field_audit(
        data_dir / "emission_field_audit.csv",
        latest=latest,
        top20_taxonomy_review=top20_taxonomy_review,
        closed_offer_top15=closed_offer_top15,
    )
    top20_taxonomy_review, emission_field_audit = (
        _apply_manual_enrichment_to_rankings(
            top20_taxonomy_review,
            emission_field_audit,
            manual_cnpj_enrichment,
        )
    )
    top100_fidcs_middle_market, top100_fidcs_middle_market_summary = (
        _build_top100_fidcs_middle_market(
            funds=funds,
            latest=latest,
            actions=taxonomy_review_actions,
            top20_taxonomy_review=top20_taxonomy_review,
            profiles=profiles,
            manual_enrichment=manual_cnpj_enrichment,
            additional_2026=top100_plus2_2026_curation,
            vehicle=vehicle,
        )
    )
    top100_outros_review = build_taxonomy_review_queue(
        funds,
        taxonomy_review_actions,
        latest=latest,
        table_ii=vehicle,
        regulation_review=top20_outros_regulations,
        document_inventory=document_inventory,
        card_curation=card_receivables_curation,
        document_review=taxonomy_document_review,
    )
    top100_outros_summary = taxonomy_review_summary(
        funds,
        taxonomy_review_actions,
        latest=latest,
        queue=top100_outros_review,
    )

    material_focus = (
        market[["tipo_anbima", "foco_anbima", "denominador_pl_subtipo_brl"]]
        .drop_duplicates()
        .sort_values("denominador_pl_subtipo_brl", ascending=False)
    )
    material_top6 = material_focus.head(6).copy()
    material_omitted = material_focus.iloc[6:].copy()
    holder_distribution = holder_distribution_history[
        holder_distribution_history["competencia"].eq(latest)
    ].drop(columns="competencia")
    holder_meta_latest = holder_distribution_meta_history[
        holder_distribution_meta_history["competencia"].eq(latest)
    ].iloc[0].drop(labels="competencia").to_dict()
    provider_concentration = [
        row for row in provider_concentration_history if row["competencia"] == latest
    ]
    conclusion_metrics = _conclusion_metrics(
        vehicle,
        funds,
        latest,
        mono=mono,
        bank_fidc_detail=bank_fidc_detail,
    )
    offer_ticket_concentration_2026 = _offer_ticket_concentration_2026(
        offer_ticket_outputs.cohort
    )
    executive_conclusions, executive_conclusion_notes = _executive_conclusions(
        latest=latest,
        conclusion_metrics=conclusion_metrics,
        offer_concentration=offer_ticket_concentration_2026,
        closed_annual=closed_annual,
        closed_jan_june=closed_jan_june,
        provider_concentration_history=provider_concentration_history,
        provider_historical_ranking=provider_historical_ranking,
        qi_legacy_attribution=qi_legacy_attribution,
        reag_admin_summary=reag_admin_summary,
    )

    output = {
        "schema_version": "fidc_revision_artifact_payload_v10",
        "latest_complete": latest,
        "stock_preliminary_status": stock_preliminary_status,
        "offers_as_of": offers_as_of,
        "offers_source_as_of": offers_source_as_of,
        "generated_at": pd.Timestamp.now(tz="America/Sao_Paulo").isoformat(),
        "pl_history": _records(annual_pl),
        "pl_total_cagr_periods": _records(pl_total_cagr_periods),
        "bcb_expanded_credit": _records(bcb_expanded_credit),
        "bcb_total_growth_periods": _records(bcb_total_growth_periods),
        "investor_base_history": _records(annual_base),
        "investor_composition": _records(
            _investor_composition(
                cotistas,
                latest,
                expected_total=float(latest_month["cotistas_total"]),
            )
        ),
        "holder_distribution": _records(holder_distribution),
        "holder_distribution_meta": {
            str(key): _json_value(value) for key, value in holder_meta_latest.items()
        },
        "holder_distribution_history": _records(holder_distribution_history),
        "holder_distribution_meta_history": _records(holder_distribution_meta_history),
        "type_mix": _records(type_mix),
        "type_mix_meta": type_mix_meta,
        "classification_coverage": _records(classification_coverage),
        "type_mix_history": _records(type_mix_history),
        "type_mix_history_official": _records(type_mix_history_official),
        "taxonomy_level_history": _records(taxonomy_level_history),
        "carteira_1_taxonomy_history": _records(carteira_1_taxonomy_history),
        "carteira_1_taxonomy_summary": {
            str(key): _json_value(value)
            for key, value in carteira_1_taxonomy_summary.items()
        },
        "classification_coverage_history": _records(classification_coverage_history),
        "receivables": receivables,
        "receivables_history": _records(receivables_history),
        "receivables_meta_history": _records(receivables_meta_history),
        "qa_latest": {str(key): _json_value(value) for key, value in qa_latest.items()},
        "qa_series": _records(qa_series),
        "receivables_reconciliation_summary": _records(
            receivables_reconciliation_summary
        ),
        "receivables_reconciliation_detail": _records(
            reconciliation_audit_slice
        ),
        "delinquency_single_receivable": _records(
            delinquency_single_receivable
        ),
        "delinquency_single_receivable_summary": _single_record(
            delinquency_single_receivable_summary
        ),
        "delinquency_frozen_cohort_history": _records(
            delinquency_frozen_cohort_history
        ),
        "delinquency_frozen_cohort_summary": _records(
            delinquency_frozen_cohort_summary
        ),
        "delinquency_cohort_revision_summary": _single_record(
            delinquency_cohort_revision_summary
        ),
        "delinquency_cohort_revision_transitions": _records(
            delinquency_cohort_revision_transitions
        ),
        "delinquency_cohort_revision_sensitivity": _records(
            delinquency_cohort_revision_sensitivity
        ),
        "delinquency_dispersion": _records(delinquency_dispersion),
        "delinquency_dispersion_summary": _single_record(
            delinquency_dispersion_summary
        ),
        "bridge_summary": _records(bridge_summary),
        "bridge_top_contributors": _records(bridge_detail.head(30)),
        "bridge_atlantico": _records(atlantic),
        "atlantico_profile": atlantico_profile,
        "atlantico_history": atlantico_history,
        "provider_concentration": provider_concentration,
        "provider_concentration_history": provider_concentration_history,
        "provider_historical_ranking": _records(provider_historical_ranking),
        "provider_independent_ranking": _records(provider_independent_ranking),
        "provider_independent_scope": {
            "groups": int(provider_independent_ranking["participante"].nunique())
            if not provider_independent_ranking.empty
            else 0,
            "roles": int(provider_independent_ranking["papel"].nunique())
            if not provider_independent_ranking.empty
            else 0,
            "methodology": (
                "grupos com independência revisada; aliases consolidados antes do "
                "ranking; posição independente e posição geral permanecem separadas"
            ),
        },
        "bank_fidc_evolution": _records(
            bank_fidc_evolution.assign(
                grupo_bancario=bank_fidc_evolution.get("bank_group", pd.Series(dtype="object")).map(
                    {
                        "BB": "Banco do Brasil",
                        "BTG": "BTG Pactual",
                        "Bradesco": "Bradesco",
                        "Itau": "Itaú",
                        "Santander": "Santander",
                        "Total 5 bancos": "Total 5 bancos",
                    }
                ),
                pl_bruto_brl=bank_fidc_evolution.get("pl_brl"),
                observado=bank_fidc_evolution.get("fundos_observados", pd.Series(dtype="float64")).fillna(0).gt(0),
                metodologia=(
                    "coorte fixa das raízes de CNPJ listadas em FIDCs.xlsx; PL histórico do conjunto atual"
                ),
            )
        ) if not bank_fidc_evolution.empty else [],
        "bank_fidc_detail": _records(
            bank_fidc_detail.assign(
                grupo_bancario=bank_fidc_detail.get("bank_group", pd.Series(dtype="object")).map(
                    {
                        "BB": "Banco do Brasil",
                        "BTG": "BTG Pactual",
                        "Bradesco": "Bradesco",
                        "Itau": "Itaú",
                        "Santander": "Santander",
                    }
                ),
                nome_curto=bank_fidc_detail.get("denominacao", pd.Series(dtype="object")).map(
                    _display_fund_name
                ),
            )
        ) if not bank_fidc_detail.empty else [],
        "acquiring_reclassified_mix": _records(
            acquiring_reclassified_mix.assign(
                categoria_analitica=acquiring_reclassified_mix.get("categoria_cvm").replace(
                    {
                        "Cartao de credito": "Cartão",
                        "Acoes judiciais": "Ações judiciais",
                        "Servicos": "Serviços",
                        "Agronegocio": "Agronegócio",
                        "Imobiliario": "Imobiliário",
                        "Setor publico": "Setor público",
                        "Nao informado": "N/D",
                    }
                ),
                pl_brl=acquiring_reclassified_mix.get("pl_reclassificado_brl"),
                share_pl=acquiring_reclassified_mix.get("share_reclassificado"),
                fundos=acquiring_reclassified_mix.get("fundos_reclassificados"),
                metodologia=(
                    "reclassificação analítica restrita aos "
                    f"{int(acquiring_reclassified_mix['fundos_adquirencia_curados'].max())} "
                    "CNPJs curados; classificação CVM original preservada"
                ),
            )
        ) if not acquiring_reclassified_mix.empty else [],
        "market_share": _records(market),
        "market_share_top10_fixed": _records(fixed_top10),
        "market_share_scope_summary": _records(market_scope),
        "market_share_exclusions": [
            {"cnpj": cnpj, "fund": name}
            for cnpj, name in MARKET_SHARE_EXCLUDED_FUNDS.items()
        ],
        "acquiring_taxonomy": acquiring_taxonomy,
        "acquiring_curation_detail": _records(acquiring_curation_detail),
        "card_taxonomy_audit": _records(card_taxonomy_audit),
        "card_taxonomy_summary": {
            str(key): _json_value(value)
            for key, value in card_taxonomy_summary.items()
        },
        "acquiring_anbima_review": _records(acquiring_anbima_review),
        "acquiring_anbima_review_summary": {
            "fundos_filtrados": int(len(acquiring_anbima_review)),
            "fundos_total_breakdown_cartao": int(card_taxonomy_summary.get("fundos_total") or 0),
            "filtro_aplicado": 'Decisão = "Incluído em Adquirência"',
            "limitacao_contagem": (
                f"a base vigente contém {int(card_taxonomy_summary.get('fundos_total') or 0)} "
                "fundos revisados em Cartão; "
                f"{int(card_taxonomy_summary.get('fundos_incluidos_adquirencia') or 0)} "
                "atendem ao filtro literal solicitado"
            ),
            "base_alterada": False,
        },
        "taxonomy_top15": _records(taxonomy_top15),
        "top20_by_anbima_type": _records(top20_by_anbima_type),
        "top20_by_anbima_type_coverage": _records(
            top20_by_anbima_type_coverage
        ),
        "top20_taxonomy_review": _records(top20_taxonomy_review),
        "emission_field_audit": _records(emission_field_audit),
        "manual_cnpj_enrichment": _records(manual_cnpj_enrichment),
        "top100_outros_review": _records(top100_outros_review),
        "top100_fidcs_middle_market": _records(top100_fidcs_middle_market),
        "top100_fidcs_middle_market_summary": {
            str(key): _json_value(value)
            for key, value in top100_fidcs_middle_market_summary.items()
        },
        "top100_outros_summary": {
            str(key): _json_value(value)
            for key, value in top100_outros_summary.items()
            if key != "destinos"
        },
        "top100_outros_destinations": _records(
            top100_outros_summary.get("destinos", pd.DataFrame())
        ),
        "taxonomy_review_meta": {
            "ledger_sha256": taxonomy_review_ledger_digest(taxonomy_review_path),
            "ledger_path": "data/industry_study/taxonomy_review_actions.csv",
            "audit_sha256": taxonomy_review_audit_digest(
                taxonomy_review_audit_path
            ),
            "audit_path": "data/industry_study/taxonomy_review_audit.csv",
            "official_fields_mutated": False,
            "review_key": "cnpj_fundo",
            "historical_periods": list(type_mix_periods),
            "historical_positions": int(len(top20_taxonomy_review)),
            "historical_unique_funds": int(
                top20_taxonomy_review["cnpj_fundo"].nunique()
            ),
            "application_rule": (
                "decisão aprovada por CNPJ é aplicada a todas as competências passadas e futuras "
                "em que o mesmo fundo apareça"
            ),
        },
        "numeric_locale_audit": [
            {"artefato": "PPTX", "ponto": "KPIs, títulos, notas e rodapés", "padrao": "vírgula decimal e ponto de milhar"},
            {"artefato": "PPTX", "ponto": "eixos X e Y nativos dos gráficos", "padrao": "chartSpace em pt-BR, formato numérico vinculado ao dado e unidades explícitas no título do eixo ou do painel"},
            {"artefato": "PPTX", "ponto": "data labels nativos", "padrao": "percentual, R$ bi, R$ mi ou valor absoluto conforme a escala do gráfico"},
            {"artefato": "PPTX", "ponto": "limitação de compatibilidade regional", "padrao": "PowerPoint usa o idioma pt-BR gravado no gráfico; renderizadores que ignoram chartSpace.lang podem exibir o separador da máquina"},
            {"artefato": "PPTX", "ponto": "tabelas nativas dos rankings e Top 15", "padrao": "texto pt-BR; colunas monetárias identificadas em R$ bi"},
            {"artefato": "XLSX", "ponto": "células monetárias", "padrao": "valor numérico editável com formato R$ e unidade bi/mi quando indicada"},
            {"artefato": "XLSX", "ponto": "percentuais e índices", "padrao": "célula numérica editável; vírgula decimal na localidade pt-BR"},
            {"artefato": "XLSX", "ponto": "inteiros, contagens e rankings", "padrao": "ponto de milhar na localidade pt-BR"},
            {"artefato": "Streamlit", "ponto": "KPIs, captions e campos editoriais", "padrao": "funções de formatação pt-BR"},
            {"artefato": "Streamlit", "ponto": "tabelas pandas", "padrao": "formatadores pt-BR para números, percentuais e variações"},
            {"artefato": "Streamlit", "ponto": "gráficos Altair/Vega", "padrao": "locale numérico global pt-BR para eixos, labels e tooltips"},
            {"artefato": "CSV exportado no Streamlit", "ponto": "arquivos numéricos revisados", "padrao": "separador ponto e vírgula e vírgula decimal"},
            {"artefato": "Novos exports", "ponto": "reclassificação de adquirência, Top 15 por taxonomia e dispersão", "padrao": "mesma convenção pt-BR do workbook e do Streamlit"},
        ],
        "material_focus_top6": _records(material_top6),
        "material_focus_omitted": {
            "focuses": int(len(material_omitted)),
            "pl": float(material_omitted["denominador_pl_subtipo_brl"].sum()),
            "share": float(
                material_omitted["denominador_pl_subtipo_brl"].sum()
                / material_focus["denominador_pl_subtipo_brl"].sum()
            ),
        },
        "top20_fidcs": _records(top20.assign(nome_curto=top20["denominacao"].map(_display_fund_name))),
        "top20_outros": _records(top20_outros_review),
        "top20_outros_regulation_review": _records(
            top20_outros_regulations
        ),
        "top20_outros_reclassification_summary": (
            top20_outros_reclassification_summary
        ),
        "profiles": _records(profiles),
        "flagship_curation": _records(flagship_curation.detail),
        "flagship_families": _records(flagship_curation.families),
        "flagship_curation_summary": {
            str(key): _json_value(value)
            for key, value in flagship_curation.summary.items()
        },
        "carteira_1_curation": _records(carteira_1_curation.detail),
        "carteira_1_curation_ranges": _records(carteira_1_curation.ranges),
        "carteira_1_curation_summary": {
            str(key): _json_value(value)
            for key, value in carteira_1_curation.summary.items()
        },
        "carteira_1_flagship_comparison": _records(
            carteira_1_flagship_comparison.detail
        ),
        "carteira_1_flagship_comparison_summary": {
            str(key): _json_value(value)
            for key, value in carteira_1_flagship_comparison.summary.items()
        },
        "carteira_1_structural_assets": _records(
            carteira_1_structural_risk.assets
        ),
        "carteira_1_structural_taxonomy": _records(
            carteira_1_structural_risk.taxonomy
        ),
        "carteira_1_structural_watchlist": _records(
            carteira_1_structural_risk.watchlist
        ),
        "carteira_1_structural_summary": {
            str(key): _json_value(value)
            for key, value in carteira_1_structural_risk.summary.items()
        },
        "portfolio_export_carteira_101": _records(portfolio_export.carteira),
        "portfolio_export_cases_99": _records(
            portfolio_export.carteira[
                portfolio_export.carteira["categoria_risco_proposta"].isin(
                    {
                        "Financeiro",
                        "Adquirência",
                        "Agro / Revenda",
                        "Risco Corporativo",
                        "Consignado INSS e FGTS",
                        "Factoring",
                    }
                )
            ]
        ),
        "portfolio_export_flagships": _records(portfolio_export.flagships),
        "portfolio_export_coverage": _records(portfolio_export.coverage),
        "portfolio_export_gaps": _records(portfolio_export.gaps),
        "portfolio_export_manual_audit": _records(portfolio_export.manual),
        "portfolio_export_dictionary": _records(portfolio_export.dictionary),
        "portfolio_export_price_evidence": _records(portfolio_export.prices),
        "carteira_101_document_audit": _records(
            carteira_101_document_audit.audit
        ),
        "carteira_101_document_coverage": _records(
            carteira_101_document_audit.coverage
        ),
        "carteira_101_document_evidence": _records(
            carteira_101_document_audit.evidence
        ),
        "carteira_101_document_prices": _records(
            carteira_101_document_audit.prices
        ),
        "carteira_101_document_checkpoint": _records(
            carteira_101_document_audit.checkpoint
        ),
        "carteira_101_document_manifest": carteira_101_document_audit.manifest,
        "service_model": _records(_service_model(mono, latest)),
        "conclusion_metrics": conclusion_metrics,
        "executive_conclusions": executive_conclusions,
        "executive_conclusion_notes": executive_conclusion_notes,
        "monostructure_concentration": _records(mono_concentration),
        "closed_offers": closed_offers,
        "closed_offers_annual": closed_annual,
        "closed_offers_monthly": closed_monthly,
        "closed_offers_jan_june": closed_jan_june,
        # Compatibility alias for readers from the prior release.  Row labels
        # and period_end remain authoritative and identify jan–jun.
        "closed_offers_jan_may": closed_jan_june,
        "closed_offer_originators_2026": closed_originators,
        "closed_offer_ticket_distribution": _records(
            closed_offer_ticket_distribution
        ),
        "closed_offer_placement_regime": _records(
            closed_offer_placement_regime
        ),
        "fixed_income_offer_comparison": _records(
            fixed_income_offer_comparison
        ),
        "market_offer_reconciliation": _records(
            market_offer_reconciliation
        ),
        "issuance_taxonomy": _records(issuance_taxonomy),
        "issuance_taxonomy_table": _records(issuance_taxonomy_table),
        "issuance_taxonomy_reconciliation": _records(
            issuance_taxonomy_coverage.frame().assign(
                emitted_volume_brl=lambda frame: (
                    frame["total_brl"] + frame["fic_excluded_brl"]
                )
            )
        ),
        # Compatibility alias for exports/readers from the prior release.
        "offer_public_validation": _records(
            market_offer_reconciliation
        ),
        "offer_target_public_shares": _records(offer_target_public_shares),
        "anbima_outros_reclassification": _records(
            anbima_outros_reclassification
        ),
        "cvm_outros_reclassification": _records(cvm_outros_reclassification),
        "closed_offer_top15": _records(closed_offer_top15),
        "closed_offer_top15_summary": _records(
            closed_offer_top15_summary
        ),
        "offer_ticket_concentration_2026": offer_ticket_concentration_2026,
        # Aliases mantidos apenas para leitores v2/v3; o renderer v4 usa os blocos acima.
        "offers_ytd": [
            {
                "year": row["year"],
                "ofertas": row["closed_offers"],
                "volume": row["registered_volume_brl"],
            }
            for row in closed_jan_june
        ],
        "originators_current": {
            "coverage": closed_originators[0]["identified_registered_volume_coverage"]
            if closed_originators
            else 0,
            "rows": closed_originators,
        },
        "originators_2026": {
            "coverage": closed_originators[0]["identified_registered_volume_coverage"]
            if closed_originators
            else 0,
            "rows": closed_originators,
        },
        "sources": {
            "pl_cotistas_recebiveis": f"CVM, Informe Mensal de FIDC, competência {latest_label}",
            "anbima": f"ANBIMA Data, fotografia cadastral de dez/25 aplicada a {latest_label}; evidência documental; proxy CVM; N/D",
            "offers": (
                f"CVM, Ofertas Públicas de Distribuição, snapshot {offers_source_as_of}; "
                f"encerramentos até {offers_as_of}"
            ),
            "cvm_489": "https://conteudo.cvm.gov.br/export/sites/cvm/legislacao/instrucoes/anexos/400/inst489.pdf",
            "cvm_writeoff": "https://conteudo.cvm.gov.br/export/sites/cvm/legislacao/oficios-circulares/sin-snc/anexos/oc-sin-snc-0113.pdf",
        },
    }
    output.update(_load_bundle_audit_supplements(data_dir))
    # Optional v3 blocks: older published revision directories do not contain
    # these CSVs, so their absence must not invalidate a compatible payload.
    if not provider_transition_summary.empty:
        transition = _single_record(provider_transition_summary)
        if not provider_transition_role_availability.empty:
            transition["role_availability"] = _records(
                provider_transition_role_availability
            )
        output["provider_transition_summary"] = transition
    if not provider_transition_links.empty:
        output["provider_transition_links"] = _records(provider_transition_links)
    if not provider_transition_detail.empty:
        output["provider_transition_detail"] = _records(provider_transition_detail)
    if not provider_transition_role_availability.empty:
        output["provider_transition_role_availability"] = _records(
            provider_transition_role_availability
        )
    if not provider_history_cvm_coverage.empty:
        output["provider_history_cvm_coverage"] = _records(
            provider_history_cvm_coverage
        )
    if not provider_history_cvm_links.empty:
        output["provider_history_cvm_links"] = _records(
            provider_history_cvm_links
        )
    if not provider_history_cvm_detail.empty:
        output["provider_history_cvm_detail"] = _records(
            provider_history_cvm_detail
        )
    if not reag_admin_summary.empty:
        output["reag_admin_summary"] = _single_record(reag_admin_summary)
    if not reag_admin_links.empty:
        output["reag_admin_links"] = _records(reag_admin_links)
    if not reag_admin_detail.empty:
        output["reag_admin_detail"] = _records(reag_admin_detail)
    leadership = _provider_leadership_payload(
        provider_leadership_attribution,
        btg_controlled_reconciliation,
        qi_legacy_attribution,
    )
    if leadership:
        output["provider_leadership_attribution"] = leadership
    if not btg_controlled_reconciliation.empty:
        output["btg_controlled_reconciliation"] = _records(
            btg_controlled_reconciliation
        )
    if not btg_provider_ex_controlled_scenario.empty:
        output["btg_provider_ex_controlled_scenario"] = _records(
            btg_provider_ex_controlled_scenario
        )
    if not qi_legacy_attribution.empty:
        output["qi_legacy_attribution"] = _records(qi_legacy_attribution)
    return _json_value(output)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/industry_study")
    parser.add_argument(
        "--revision-dir",
        type=Path,
        default=ROOT / "data/industry_study/generated_revision",
    )
    parser.add_argument(
        "--curation",
        type=Path,
        default=ROOT / "outputs/analysis/top20_fidcs_curadoria.csv",
    )
    parser.add_argument(
        "--latest-complete",
        default="",
        help="competência AAAA-MM; vazio usa a última marcada como completa",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/industry_study/generated_revision/artifact_payload.json",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    latest_complete = str(args.latest_complete or "").strip()
    if not latest_complete:
        status_path = args.data_dir / "industry_competence_status.csv"
        status = pd.read_csv(status_path, low_memory=False) if status_path.exists() else pd.DataFrame()
        complete = (
            status[status["publication_status"].astype(str).eq("completa")]
            if not status.empty and "publication_status" in status
            else pd.DataFrame()
        )
        if not complete.empty:
            latest_complete = str(complete["competencia"].astype(str).max())
        else:
            monthly = pd.read_csv(args.data_dir / "industry_monthly.csv", low_memory=False)
            latest_complete = str(monthly["competencia"].astype(str).max())
    payload = build_payload(
        data_dir=args.data_dir,
        revision_dir=args.revision_dir,
        curation_path=args.curation,
        latest=latest_complete,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=_json_value,
        ),
        encoding="utf-8",
    )
    print(f"[ok] payload editorial: {args.output}")


if __name__ == "__main__":
    main()
