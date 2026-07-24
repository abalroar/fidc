"""Consolida os dados reproduzíveis consumidos pelo PPTX/XLSX revisados.

O módulo analítico (`build_fidc_revision_analysis.py`) permanece responsável
pelos denominadores, rankings, cobertura e reconciliações. Este script apenas
organiza essas saídas e as bases já versionadas em um payload editorial único;
nenhum percentual do deck é recalculado na camada de PowerPoint.
"""

from __future__ import annotations

import argparse
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
from services.industry_revision_analysis import (
    BTG_CONTROLLED_FIDCS,
    MARKET_SHARE_EXCLUDED_FUNDS,
)


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_REFERENCE = "2023-12"
PROVIDER_REFERENCE = "2025-12"
ATLANTICO_CNPJ = "09194841000151"
PL_TOTAL_CAGR_PERIODS = ((2022, 2023), (2023, 2024), (2024, 2025))
EXECUTIVE_OFFER_CONCENTRATION_THRESHOLD_BRL = 500_000_000.0


def _digits(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    raw = str(value).strip()
    if re.fullmatch(r"\d{1,14}(?:\.0+)?", raw):
        raw = raw.split(".", 1)[0]
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
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.astype(object).where(pd.notna(frame), None)
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in clean.to_dict(orient="records")
    ]


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
                    "Essa carteira responde por "
                    f"{_pt_pct(btg_cohort_combo_share_total, 0)} de todo o PL atendido pelo "
                    "BTG no combo completo, indicando forte ancoragem nos veículos da coorte bancária."
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
                    f"{_pt_pct(growth_2025, 0)} sobre 2025 e {_pt_pct(growth_2024, 0)} sobre 2024."
                ),
                (
                    f"A oferta {largest_offer_name}, de {_pt_brl_bi(largest_offer_volume)}, "
                    f"representou {_pt_pct(largest_offer_share)} do volume e "
                    f"{_pt_pct(largest_offer_share_increment)} do crescimento sobre 2025; "
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
    frame = pd.read_csv(
        path,
        low_memory=False,
        dtype={column: str for column in cnpj_columns},
    )
    for column in cnpj_columns:
        if column in frame:
            frame[column] = frame[column].map(_digits)
    return frame


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
    return output


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


def _pl_total_cagr_periods(annual_pl: pd.DataFrame) -> pd.DataFrame:
    """Materialize CAGRs from the same gross-PL series shown above the bars."""

    required = {"year", "competencia", "pl_total"}
    missing = sorted(required.difference(annual_pl.columns))
    if missing:
        raise ValueError("série anual de PL sem colunas: " + ", ".join(missing))
    by_year = annual_pl.set_index("year", drop=False)
    rows: list[dict[str, Any]] = []
    for start_year, end_year in PL_TOTAL_CAGR_PERIODS:
        if start_year not in by_year.index or end_year not in by_year.index:
            raise ValueError(
                f"série anual de PL não cobre CAGR {start_year}-{end_year}"
            )
        start = by_year.loc[start_year]
        end = by_year.loc[end_year]
        start_pl = float(start["pl_total"])
        end_pl = float(end["pl_total"])
        annual_intervals = int(end_year - start_year)
        if start_pl <= 0 or end_pl <= 0 or annual_intervals <= 0:
            raise ValueError(f"base inválida para CAGR {start_year}-{end_year}")
        rows.append(
            {
                "metric": "PL bruto",
                "start_year": int(start_year),
                "end_year": int(end_year),
                "start_competencia": str(start["competencia"]),
                "end_competencia": str(end["competencia"]),
                "start_pl_total_brl": start_pl,
                "end_pl_total_brl": end_pl,
                "annual_intervals": annual_intervals,
                "cagr": (end_pl / start_pl) ** (1 / annual_intervals) - 1,
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
                f"universo bruto de CNPJs legais em {latest}; mesmo conglomerado "
                "econômico normalizado; inclui FIC-FIDC"
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
    for _, fund in top20.sort_values("rank").iterrows():
        key = _digits(fund.get("cnpj_fundo"))
        curated = cur.loc[key] if not cur.empty and key in cur.index else pd.Series(dtype=object)
        documented = doc.loc[key] if not doc.empty and key in doc.index else pd.Series(dtype=object)
        nature = _pick(curated, "natureza_recebiveis", "natureza_dos_recebiveis", "recebiveis")
        if not nature:
            d1 = _pick(documented, "document_segment_n1")
            d2 = _pick(documented, "document_segment_n2")
            nature = " — ".join(item for item in (d1, d2) if item)
        evidence = _pick(curated, "evidencia", "evidencia_resumo", "trecho_evidencia")
        evidence = evidence or _pick(
            curated,
            "nota_classificacao",
            "segmento_economico_documental",
        )
        if not evidence:
            evidence = _pick(documented, "classification_evidence")[:280]
        source = _pick(curated, "fonte", "fontes", "source", "url", "links")
        source = source or _pick(curated, "fundosnet_gerenciador")
        if not source:
            source = _pick(documented, "source")
        classes = _pick(
            curated,
            "classes_subordinacao_garantias",
            "classes_subordinacao",
            "classes",
            "subordinacao_garantias",
        )
        guarantees = _pick(curated, "garantias")
        if guarantees and guarantees not in classes:
            classes = f"{classes} Garantias: {guarantees}".strip()
        fields = {
            "rank": int(fund["rank"]),
            "cnpj_fundo": key,
            "cnpj_fundo_formatado": _text(fund.get("cnpj_fundo_formatado")),
            "denominacao": _text(fund.get("denominacao")),
            "nome_curto": _display_fund_name(fund.get("denominacao")),
            "pl": float(fund["pl"]),
            "market_share_ex_fic": float(fund["market_share_ex_fic"]),
            "cedente_originador": _pick(curated, "cedente_originador", "cedente", "originador") or "não identificado",
            "sacado_devedor": _pick(curated, "sacado_devedor", "sacado", "devedor", "perfil_sacados") or "não identificado",
            "natureza_recebiveis": nature or "não identificado",
            "funcionamento_economico": _pick(curated, "funcionamento_economico", "funcionamento", "mecanica") or "não identificado",
            "emissoes": _pick(curated, "emissoes", "emissoes_relevantes", "ofertas") or "não identificado",
            "classes_subordinacao_garantias": classes or "não identificado",
            "administrador": _pick(curated, "administrador") or _text(fund.get("admin_nome")) or "não informado",
            "gestor": _pick(curated, "gestor") or _text(fund.get("gestor_nome")) or "não informado",
            "custodiante": _pick(curated, "custodiante") or _text(fund.get("custodiante_nome")) or "não informado",
            "anbima_tipo": _pick(curated, "tipo_anbima") or _text(fund.get("anbima_tipo")) or "N/D",
            "anbima_foco": _pick(curated, "foco_anbima") or _text(fund.get("anbima_foco")) or "N/D",
            "origem_classificacao": _pick(curated, "origem_tipo_foco") or _text(fund.get("classification_status")) or "N/D",
            "fonte": source or "CVM/FundosNet consultado; campo não identificado",
            "data_consulta": _pick(curated, "data_consulta", "consulted_at") or "2026-07-16",
            "evidencia": evidence
            or _pick(curated, "nota_classificacao", "segmento_economico_documental")
            or "campo não identificado nos documentos consultados",
            "status_curadoria": _pick(curated, "status_curadoria") or "pendente",
            "campos_nao_identificados": _pick(curated, "campos_nao_identificados") or "não identificado",
            "documentos_primarios_ids": _pick(curated, "documentos_primarios_ids") or "não identificado",
            "data_referencia_tipo_foco": (
                _pick(curated, "data_referencia_tipo_foco") or latest
            ),
        }
        profiles.append(fields)
    return pd.DataFrame(profiles)


def _build_top20_outros_review(
    top20_outros: pd.DataFrame,
    documentary: pd.DataFrame,
) -> pd.DataFrame:
    doc = documentary.copy()
    if not doc.empty:
        doc["cnpj_key"] = doc["cnpj"].map(_digits)
        doc = doc.drop_duplicates("cnpj_key", keep="last").set_index("cnpj_key")
    rows: list[dict[str, Any]] = []
    for _, fund in top20_outros.sort_values("rank_outros").iterrows():
        key = _digits(fund.get("cnpj_fundo"))
        evidence = doc.loc[key] if not doc.empty and key in doc.index else pd.Series(dtype=object)
        d1 = _pick(evidence, "document_segment_n1")
        d2 = _pick(evidence, "document_segment_n2")
        hypothesis = " — ".join(item for item in (d1, d2) if item)
        rows.append(
            {
                **{key_: _json_value(value) for key_, value in fund.items()},
                "nome_curto": _display_fund_name(fund.get("denominacao")),
                "classificacao_oficial": " | ".join(
                    item for item in (_text(fund.get("anbima_tipo")), _text(fund.get("anbima_foco"))) if item
                ) or "N/D",
                "hipotese_revisao": hypothesis or "não identificada",
                "evidencia_revisao": _pick(evidence, "classification_evidence")[:220]
                or "não identificada nos documentos locais",
                "fonte_revisao": _pick(evidence, "source") or "fonte primária pendente",
                "status_revisao": (
                    f"evidência documental — {_pick(evidence, 'classification_confidence')}"
                    if hypothesis
                    else "pendente"
                ),
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
    competence_status = _read_optional(data_dir / "industry_competence_status.csv")
    vehicle = pd.read_csv(data_dir / "vehicle_monthly.csv.gz", low_memory=False)
    cotistas = pd.read_csv(data_dir / "cotistas_tipo_monthly.csv", low_memory=False)
    segments = pd.read_csv(data_dir / "segments_monthly.csv", low_memory=False)
    providers = pd.read_csv(data_dir / "prestadores_latest.csv", low_memory=False)
    documentary = _read_optional(data_dir / "industry_large_fund_classification.csv")
    acquiring_curation = _read_optional(
        data_dir / "acquiring_reclassification_curation.csv",
        cnpj_columns=("cnpj14_digits",),
    )
    card_receivables_curation = _read_optional(
        data_dir / "card_receivables_curation.csv",
        cnpj_columns=("cnpj14_digits",),
    )

    funds = pd.read_csv(revision_dir / "base_fundo_cnpj.csv.gz", low_memory=False)
    qa = pd.read_csv(revision_dir / "qa_inadimplencia_competencia.csv", low_memory=False)
    bridge_summary = pd.read_csv(
        revision_dir / "bridge_inadimplencia_2024-06_2024-07_resumo.csv", low_memory=False
    )
    bridge_detail = pd.read_csv(
        revision_dir / "bridge_inadimplencia_2024-06_2024-07_detalhe.csv", low_memory=False
    )
    top20 = pd.read_csv(revision_dir / "top20_fidcs.csv", dtype={"cnpj_fundo": str})
    top20_outros = pd.read_csv(revision_dir / "top20_outros.csv", dtype={"cnpj_fundo": str})
    mono = pd.read_csv(revision_dir / "monoestrutura_por_fundo.csv", low_memory=False)
    mono_concentration = pd.read_csv(revision_dir / "monoestrutura_concentracao.csv", low_memory=False)
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
    annual_pl["pl_ex_fic"] = annual_pl["pl_total"] - annual_pl["pl_fic_fidc"]
    annual_pl["pl_fic_componente"] = annual_pl["pl_fic_fidc"]
    pl_total_cagr_periods = _pl_total_cagr_periods(annual_pl)
    annual_base = annual[["year", "competencia", "cotistas_total", "n_veiculos"]].copy()

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
    profiles = _build_profiles(
        top20,
        curation,
        documentary,
        latest=latest,
    )
    top20_outros_review = _build_top20_outros_review(top20_outros, documentary)

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
        "schema_version": "fidc_revision_artifact_payload_v6",
        "latest_complete": latest,
        "stock_preliminary_status": stock_preliminary_status,
        "offers_as_of": offers_as_of,
        "offers_source_as_of": offers_source_as_of,
        "generated_at": pd.Timestamp.now(tz="America/Sao_Paulo").isoformat(),
        "pl_history": _records(annual_pl),
        "pl_total_cagr_periods": _records(pl_total_cagr_periods),
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
        "classification_coverage_history": _records(classification_coverage_history),
        "receivables": receivables,
        "receivables_history": _records(receivables_history),
        "receivables_meta_history": _records(receivables_meta_history),
        "qa_latest": {str(key): _json_value(value) for key, value in qa_latest.items()},
        "qa_series": _records(qa_series),
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
        "profiles": _records(profiles),
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
    return output


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
