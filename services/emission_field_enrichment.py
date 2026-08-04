"""Documentary enrichment for the Top 15 by ANBIMA type audit table.

The module joins sources by the full 14-digit CNPJ.  It keeps the legal cedent
reported in CVM Table I separate from the economic originator and only accepts
originator, debtor, structural minimum and target-remuneration values supported
by an identified document.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import unicodedata
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


TOP15_BLOCK = "slides 10–17"
TEXT_ND = "N/D"
FIELDS = (
    "originador",
    "cedente",
    "subordinacao_minima",
    "remuneracao_por_tipo_cota",
    "sacado",
)

# The publication guard uses per-page floors.  These values are intentionally
# conservative because the public CVM table does not identify originator or
# debtor and the documentary fields have heterogeneous disclosure.
DEFAULT_COVERAGE_FLOORS: Mapping[str, float] = {
    "originador": 0.01,
    "cedente": 0.15,
    "subordinacao_minima": 0.01,
    # A remuneração-alvo depende de uma emissão/série numericamente divulgada.
    # Algumas páginas podem legitimamente ficar sem observação; o publicador
    # aplica um guard global para impedir que a coluna inteira volte a N/D.
    "remuneracao_por_tipo_cota": 0.0,
    "sacado": 0.01,
}

# The two ``Outros`` pages contain broad multi-asset/NPL mandates.  The
# available identified documents describe cedents and obligor classes but do
# not name an economic originator for any line.  Keeping a named, auditable
# waiver avoids converting a source gap into a party name merely to satisfy a
# mechanical floor.  Every other page/field remains fail-closed.
PAGE_COVERAGE_WAIVERS: Mapping[tuple[str, str], str] = {
    (
        "Outros",
        "originador",
    ): (
        "documentos identificados não individualizam originador econômico; "
        "cedentes legais permanecem em coluna separada"
    ),
}

DOCUMENT_CUTOFF = pd.Timestamp("2026-06-30")

_DOCUMENT_PRIORITY: Mapping[str, int] = {
    "curadoria_humana_documental": 0,
    "regulamento": 10,
    "emissao": 20,
    "assembleia": 30,
    "rating_report": 40,
    "informe_mensal": 50,
    "payload_documental": 60,
    "planilha_manual": 70,
    "candidate_extraction": 99,
}

_REMUNERATION_PRIORITY: Mapping[str, int] = {
    "curadoria_humana_documental": 0,
    "emissao": 10,
    "assembleia": 15,
    "regulamento": 20,
    "rating_report": 40,
    "payload_documental": 50,
    "informe_mensal": 60,
    "planilha_manual": 70,
    "candidate_extraction": 99,
}

_APPROVED_EVIDENCE = {"aceito_payload", "encontrado_explicito"}

# These profiles only describe the broad obligor universe of a discretionary
# credit portfolio.  They do not identify a usable debtor class for the table.
PROFILE_UNUSABLE_DEBTOR_CNPJS = {
    "53286499000101",  # Itaú Crédito Privado
    "63700113000110",  # NC 2025 I
    "30576260000170",  # Artesanal Master
}

PROFILE_PARTY_DISPLAY: Mapping[str, str] = {
    "09195235000150": "Empresas Petrobras",
    "26287464000114": "Stone/Pagar.me",
    "62393679000183": "CloudWalk IP",
    "52610624000124": "XP Comercializadora",
    "28169275000172": "PagSeguro",
    "63953619000130": "Parati Crédito",
    "26286939000158": "Cielo",
    "42922136000107": "SHPP Brasil",
    "32527650000186": "Usuários PicPay",
}


def _digits(value: object) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    if not digits or len(digits) > 14:
        return ""
    return digits.zfill(14)


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def is_missing(value: object) -> bool:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return True
    text = str(value).strip()
    return not text or text.upper().startswith("N/D") or text.lower() == "nan"


def classify_party_value(value: object) -> str:
    """Classify party prose by what the phrase identifies.

    A value counts as Cedente/Originador only when it names an entity or a
    recognizable ecosystem.  Generic legal definitions remain useful as
    receivable context, while explicit non-findings remain N/D.
    """

    if is_missing(value):
        return "nao_localizado"
    folded = _fold(value)
    if folded.startswith(
        (
            "ausencia de cedente",
            "ausencia de entidade",
            "ausencia de originador",
            "nao identificado",
            "nao ha cedente",
            "nao localizado",
        )
    ):
        return "nao_localizado"
    generic_markers = (
        "candidato textual para validacao",
        "nomes nao identificados",
        "nomes individuais nao identificados",
        "nenhuma entidade unica foi identificada",
        "multicedente",
        "multiplos originadores",
        "todas as pessoas fisicas ou juridicas que cedem",
        "pessoas fisicas ou juridicas titulares",
        "pessoas fisicas juridicas ou fundos que",
        "pessoas juridicas ou fundos que",
        "instituicoes financeiras que concedam",
        "empresas de diferentes setores",
        "um titular de direitos creditorios",
        "os titulares dos direitos creditorios",
        "os cedentes e ou endossantes",
        "os fornecedores que cedem",
        "os produtores que",
        "a subcredenciadora",
        "baixa por deposito",
    )
    if any(marker in folded for marker in generic_markers):
        return "categoria_sem_entidade_nomeada"
    tokens = folded.split()
    numeric_tokens = sum(bool(re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?", token)) for token in tokens)
    if tokens and numeric_tokens / len(tokens) >= 0.60:
        return "categoria_sem_entidade_nomeada"
    return "entidade_ou_ecossistema_nomeado"


def _profile_value_names_originator(value: object) -> bool:
    """Return whether the profile sentence explicitly assigns originator role."""

    folded = _fold(value)
    return any(
        marker in folded
        for marker in (
            "atua como originador",
            "atua como originadora",
            "originador economico",
            "originadora economica",
        )
    )


def build_taxonomy_party_evidence(review: pd.DataFrame) -> pd.DataFrame:
    """Convert the curated taxonomy review into explicit party evidence.

    The adapter accepts only named values whose evidence assigns a documentary
    role such as cedent, endorser or original creditor.  Extracted fragments,
    generic legal definitions and non-findings remain outside the party table.
    """

    if review.empty:
        return pd.DataFrame()
    required = {
        "cnpj_fundo",
        "document_id",
        "document_reference_date",
        "pagina_clausula",
        "cedent_originator_explicit",
        "evidence_summary",
        "confianca_documental",
    }
    missing = required.difference(review.columns)
    if missing:
        raise ValueError(
            f"curadoria taxonômica sem colunas obrigatórias: {sorted(missing)}"
        )

    rows: list[dict[str, object]] = []
    for item in review.to_dict(orient="records"):
        cnpj = _digits(item.get("cnpj_fundo"))
        value = str(item.get("cedent_originator_explicit") or "").strip()
        evidence = str(item.get("evidence_summary") or "").strip()
        value_folded = _fold(value)
        evidence_folded = _fold(evidence)
        if (
            not re.fullmatch(r"\d{14}", cnpj)
            or classify_party_value(value) != "entidade_ou_ecossistema_nomeado"
            or value_folded.startswith("candidato textual para validacao")
        ):
            continue

        cedent_role = any(
            marker in evidence_folded
            for marker in (
                "cedente",
                "endossa",
                "endossante",
                "credora original",
            )
        )
        originator_role = any(
            marker in evidence_folded
            for marker in (
                "concede os emprestimos",
                "credora original",
                "originador",
                "originadora",
            )
        )
        if not cedent_role and not originator_role:
            continue

        confidence = {
            "alta": 1.0,
            "media": 0.7,
            "baixa": 0.3,
        }.get(_fold(item.get("confianca_documental")), 0.0)
        common = {
            "cnpj": cnpj,
            "value": value,
            "status": "encontrado_explicito",
            "source_kind": "curadoria_humana_documental",
            "source_id": str(item.get("document_id") or "").strip(),
            "document_class": "industry_taxonomy_document_review.csv",
            "document_date": str(
                item.get("document_reference_date") or ""
            ).strip(),
            "page": str(item.get("pagina_clausula") or "").strip(),
            "source_path": (
                "data/industry_study/industry_taxonomy_document_review.csv"
            ),
            "source_url": str(item.get("document_url") or "").strip(),
            "confidence": confidence,
            "excerpt": evidence,
        }
        if cedent_role:
            rows.append(
                {
                    **common,
                    "field": "cedente",
                    "nature": "curadoria taxonômica · cedente/endossante explícito",
                }
            )
        if originator_role:
            rows.append(
                {
                    **common,
                    "field": "originador",
                    "nature": "curadoria taxonômica · originação explícita",
                }
            )
    return pd.DataFrame(rows)


def _truthy(value: object) -> bool:
    return _fold(value) in {"1", "true", "sim", "yes"}


def _parse_date(value: object) -> pd.Timestamp:
    text = str(value or "").strip()
    if not text:
        return pd.NaT
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return pd.Timestamp(datetime.strptime(text[:10], fmt))
        except ValueError:
            continue
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if isinstance(parsed, pd.Timestamp) and parsed.tzinfo is not None:
        return parsed.tz_convert(None)
    return parsed


def _series(frame: pd.DataFrame, column: str, default: object = "") -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series(default, index=frame.index, dtype=object)


def _document_label(row: Mapping[str, object]) -> str:
    kind = str(row.get("source_kind") or row.get("camada") or "documento")
    source_id = str(row.get("source_id") or row.get("fonte") or "").strip()
    document_class = str(row.get("document_class") or "").strip()
    date = str(row.get("document_date") or row.get("data") or "").strip()
    page = str(row.get("page") or row.get("pagina") or "").strip()
    parts = [kind]
    if document_class and document_class != kind:
        parts.append(document_class)
    if source_id and not is_missing(source_id):
        parts.append(f"documento {source_id}")
    if date and not is_missing(date):
        parts.append(date)
    if page and not is_missing(page):
        parts.append(f"p. {page}")
    return " · ".join(parts)


@dataclass(frozen=True)
class SelectedValue:
    value: str
    source: str
    nature: str = ""
    exception: bool = False


def build_profile_curation_evidence(
    profiles: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Classify Top-20 profile prose by function and emit accepted evidence.

    Table I remains the first source for the legal cedent.  Named profile text
    is a documented fallback when Table I is blank.  Generic prose remains in
    the classification ledger and never inflates party coverage.
    """

    required = {
        "cnpj_fundo",
        "denominacao",
        "cedente_originador",
        "sacado_devedor",
        "natureza_recebiveis",
        "documentos_primarios_ids",
        "data_consulta",
    }
    missing = required.difference(profiles.columns)
    if missing:
        raise ValueError(
            f"curadoria Top 20 sem colunas obrigatórias: {sorted(missing)}"
        )

    evidence_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    for row in profiles.to_dict(orient="records"):
        cnpj = _digits(row.get("cnpj_fundo"))
        if not re.fullmatch(r"\d{14}", cnpj):
            raise ValueError("curadoria Top 20 contém CNPJ inválido")
        documents = str(row.get("documentos_primarios_ids") or "").strip()
        source_id = (
            f"IDs {documents} · consulta {row.get('data_consulta')}"
            if documents
            else f"consulta {row.get('data_consulta')}"
        )
        common = {
            "cnpj": cnpj,
            "source_kind": "curadoria_humana_documental",
            "source_id": source_id,
            "document_class": "top20_fidcs_curadoria.csv",
            # The consultation date is after the reference month, while the
            # cited primary documents support the content.  Keep the document
            # date blank so the June cutoff does not misrepresent it.
            "document_date": "",
            "source_path": "outputs/analysis/top20_fidcs_curadoria.csv",
            "source_url": "",
            "page": "",
            "status": "encontrado_explicito",
            "confidence": 1.0,
            "excerpt": str(row.get("natureza_recebiveis") or "").strip(),
        }
        party_text = str(row.get("cedente_originador") or "").strip()
        party_class = classify_party_value(party_text)
        party_display = PROFILE_PARTY_DISPLAY.get(cnpj, party_text)
        names_originator = _profile_value_names_originator(party_text)
        if party_class == "entidade_ou_ecossistema_nomeado" and not is_missing(party_text):
            evidence_rows.append(
                {
                    **common,
                    "field": "cedente",
                    "value": party_display,
                    "nature": "perfil curado · entidade/ecossistema nomeado",
                }
            )
            if names_originator:
                evidence_rows.append(
                    {
                        **common,
                        "field": "originador",
                        "value": party_display,
                        "nature": "perfil curado · papel de originador explícito",
                    }
                )

        debtor_text = str(row.get("sacado_devedor") or "").strip()
        debtor_class = (
            "nao_utilizavel"
            if cnpj in PROFILE_UNUSABLE_DEBTOR_CNPJS
            else "classe_de_sacado_documentada"
        )
        if debtor_class == "classe_de_sacado_documentada" and not is_missing(debtor_text):
            evidence_rows.append(
                {
                    **common,
                    "field": "sacado_devedor",
                    "value": debtor_text,
                    "nature": "perfil curado · classe de sacado/devedor",
                }
            )

        audit_rows.append(
            {
                "cnpj": cnpj,
                "fundo": str(row.get("denominacao") or "").strip(),
                "cedente_originador_texto": party_text,
                "classificacao_cedente_originador": party_class,
                "aplicacao_como_cedente": (
                    "aceito_como_fallback_documental"
                    if party_class == "entidade_ou_ecossistema_nomeado"
                    else "nao_aplicado"
                ),
                "valor_aplicado_como_cedente": (
                    party_display
                    if party_class == "entidade_ou_ecossistema_nomeado"
                    else TEXT_ND
                ),
                "aplicacao_como_originador": (
                    "aceito_papel_explicito"
                    if names_originator
                    else "nao_aplicado"
                ),
                "valor_aplicado_como_originador": (
                    party_display if names_originator else TEXT_ND
                ),
                "sacado_devedor_texto": debtor_text,
                "classificacao_sacado_devedor": debtor_class,
                "natureza_recebiveis": str(row.get("natureza_recebiveis") or "").strip(),
                "documentos_primarios_ids": documents or TEXT_ND,
                "data_consulta": str(row.get("data_consulta") or "").strip(),
            }
        )
    return pd.DataFrame(evidence_rows), pd.DataFrame(audit_rows)


def _select_document_fields(evidence: pd.DataFrame) -> dict[tuple[str, str], SelectedValue]:
    if evidence.empty:
        return {}
    frame = evidence.copy()
    frame["cnpj"] = frame["cnpj"].map(_digits)
    frame["_date"] = _series(frame, "document_date").map(_parse_date)
    frame = frame[
        _series(frame, "status").astype(str).isin(_APPROVED_EVIDENCE)
        & ~_series(frame, "value").map(is_missing)
        & ~_series(frame, "source_kind").astype(str).eq("candidate_extraction")
        & (frame["_date"].isna() | frame["_date"].le(DOCUMENT_CUTOFF))
        & frame["cnpj"].str.fullmatch(r"\d{14}")
    ].copy()
    party_mask = frame["field"].astype(str).isin(("originador", "cedente"))
    frame = frame[
        ~party_mask
        | frame["value"].map(classify_party_value).eq(
            "entidade_ou_ecossistema_nomeado"
        )
    ].copy()
    if frame.empty:
        return {}
    frame["_priority"] = frame["source_kind"].map(
        lambda value: _DOCUMENT_PRIORITY.get(str(value), 80)
    )
    frame["_confidence"] = pd.to_numeric(
        _series(frame, "confidence"), errors="coerce"
    ).fillna(0)
    frame = frame.sort_values(
        ["cnpj", "field", "_priority", "_confidence", "_date", "source_id"],
        ascending=[True, True, True, False, False, False],
        kind="stable",
    )
    selected: dict[tuple[str, str], SelectedValue] = {}
    for (cnpj, field), group in frame.groupby(["cnpj", "field"], sort=False):
        row = group.iloc[0].to_dict()
        selected[(cnpj, str(field))] = SelectedValue(
            value=str(row.get("value") or "").strip(),
            source=_document_label(row),
            nature=str(row.get("nature") or "").strip(),
        )
    return selected


def _select_prices(prices: pd.DataFrame) -> dict[str, SelectedValue]:
    if prices.empty:
        return {}
    frame = prices.copy()
    frame["cnpj"] = frame["cnpj"].map(_digits)
    frame["_date"] = _series(frame, "document_date").map(_parse_date)
    frame = frame[
        _series(frame, "status").astype(str).isin(_APPROVED_EVIDENCE)
        & ~_series(frame, "price_display").map(is_missing)
        & ~_series(frame, "source_kind").astype(str).eq("candidate_extraction")
        & (frame["_date"].isna() | frame["_date"].le(DOCUMENT_CUTOFF))
        & frame["cnpj"].str.fullmatch(r"\d{14}")
    ].copy()
    if frame.empty:
        return {}
    frame["_priority"] = frame["source_kind"].map(
        lambda value: _PRICE_PRIORITY.get(str(value), 80)
    )
    output: dict[str, SelectedValue] = {}
    for cnpj, group in frame.groupby("cnpj", sort=False):
        group = group[group["_priority"].eq(group["_priority"].min())].copy()
        if group["_date"].notna().any():
            group = group[group["_date"].eq(group["_date"].max())].copy()
        pairs: list[str] = []
        seen: set[tuple[str, str]] = set()
        for row in group.to_dict(orient="records"):
            class_series = str(row.get("class_series") or "").strip()
            price = str(row.get("price_display") or "").strip()
            key = (_fold(class_series), _fold(price))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(
                f"{class_series}: {price}"
                if class_series and not is_missing(class_series)
                else price
            )
        representative = group.iloc[0].to_dict()
        exception = len(pairs) > 1 or any(
            str(value or "").strip() not in {"", "0", "False", "false"}
            for value in group.get("exception_flag", pd.Series(index=group.index, dtype=object))
        )
        output[cnpj] = SelectedValue(
            value=" | ".join(pairs),
            source=_document_label(representative),
            nature=str(representative.get("price_nature") or "").strip(),
            exception=exception,
        )
    return output


def _remuneration_has_rate(value: object) -> bool:
    text = str(value or "").strip()
    if is_missing(text):
        return False
    folded = _fold(text)
    if any(
        marker in folded
        for marker in (
            "residual sem parametro",
            "sem parametro definido",
            "sem spread",
            "a definir em bookbuilding",
            "ate ",
        )
    ):
        return False
    return bool(
        re.search(
            r"(?:CDI|DI|IPCA|SELIC|IGP[-\s]?M)\s*(?:\+|acrescid[ao])\s*\d|"
            r"\d+(?:[.,]\d+)?\s*%\s*(?:do|da)?\s*(?:CDI|DI|IPCA|SELIC|IGP[-\s]?M)|"
            r"(?:benchmark|prefixad[ao])\s*\d+(?:[.,]\d+)?\s*%\s*a\.a\.",
            text,
            re.IGNORECASE,
        )
    )


def build_deep_dive_remuneration_evidence(paths: Iterable[Path]) -> pd.DataFrame:
    """Normalize the human-curated deep-dive issuance tables as evidence.

    The tables already bind CNPJ, quota/series, target remuneration and primary
    document IDs.  Residual returns, bookbuilding caps and rows without a numeric
    target stay outside the reported coverage.
    """

    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for path in paths:
        if not path.exists():
            continue
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        required = {"CNPJ", "Classe/Série", "Remuneração-alvo", "Fonte"}
        if not required.issubset(frame.columns):
            continue
        for row in frame.to_dict(orient="records"):
            cnpj = _digits(row.get("CNPJ"))
            target = str(row.get("Remuneração-alvo") or "").strip()
            if not cnpj or not _remuneration_has_rate(target):
                continue
            class_series = str(row.get("Classe/Série") or "").strip()
            if is_missing(class_series) or class_series == "—":
                continue
            source = str(row.get("Fonte") or "").strip()
            ids = re.findall(r"\b\d{5,}\b", source)
            source_id = " | ".join(dict.fromkeys(ids)) or source
            source_dates = re.findall(r"20\d{2}-\d{2}-\d{2}", source)
            if source_dates:
                document_date = min(source_dates)
            else:
                parsed = _parse_date(row.get("Data"))
                document_date = (
                    parsed.strftime("%Y-%m-%d") if not pd.isna(parsed) else ""
                )
            value = f"{class_series}: {target}"
            key = (cnpj, _fold(value), source_id, document_date)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "cnpj": cnpj,
                    "field": "remuneracao_alvo",
                    "value": value,
                    "source_kind": "curadoria_humana_documental",
                    "source_id": source_id,
                    "document_class": "deep dive · emissões",
                    "document_date": document_date,
                    "source_path": str(path),
                    "source_url": "",
                    "page": "",
                    "status": "encontrado_explicito",
                    "confidence": 1.0,
                    "excerpt": target,
                    "nature": f"rentabilidade-alvo documentada · {class_series}",
                }
            )
    return pd.DataFrame(rows)


def load_curated_remuneration_evidence(path: Path) -> pd.DataFrame:
    """Load the cutoff-specific human review of target remuneration.

    The automatic scanner is deliberately broader than the publication
    contract: it can surface table fragments, bookbuilding caps and historical
    series that still need reconciliation.  This materialization contains only
    class/series values reviewed against an identified document and an explicit
    ranking cutoff.  The raw scanner output remains available in the audit
    package and never fills the slide directly.
    """

    required = {
        "cutoff",
        "ranking_table",
        "cnpj",
        "fundo",
        "classe_serie",
        "value",
        "source_kind",
        "source_id",
        "document_date",
        "event_date",
        "page",
        "decision",
        "reason",
    }
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            "curadoria de remuneração-alvo sem colunas: "
            + ", ".join(sorted(missing))
        )
    if not frame["decision"].eq("ACEITA").all():
        raise ValueError(
            "materialização aceita contém decisão diferente de ACEITA"
        )
    frame["cnpj"] = frame["cnpj"].map(_digits)
    if not frame["cnpj"].str.fullmatch(r"\d{14}").all():
        raise ValueError("curadoria de remuneração-alvo contém CNPJ inválido")
    frame["_cutoff"] = frame["cutoff"].map(_parse_date)
    if frame["_cutoff"].isna().any():
        raise ValueError("curadoria de remuneração-alvo contém cutoff inválido")
    if not frame["value"].map(_remuneration_has_rate).all():
        raise ValueError(
            "curadoria de remuneração-alvo contém valor sem benchmark e taxa"
        )

    output = pd.DataFrame(
        {
            "cnpj": frame["cnpj"],
            "fundo": frame["fundo"].str.strip(),
            "classe_serie": frame["classe_serie"].str.strip(),
            "field": "remuneracao_alvo",
            "value": frame["classe_serie"].str.strip()
            + ": "
            + frame["value"].str.strip(),
            "source_kind": "curadoria_humana_documental",
            "source_id": frame["source_id"].str.strip(),
            "document_class": (
                "curadoria remuneração-alvo · "
                + frame["source_kind"].str.strip()
            ),
            "document_date": frame["document_date"].str.strip(),
            "event_date": frame["event_date"].str.strip(),
            "selection_cutoff": frame["cutoff"].str.strip(),
            "ranking_table": frame["ranking_table"].str.strip(),
            "source_path": str(path),
            "source_url": frame["source_id"].map(
                lambda value: (
                    "https://fnet.bmfbovespa.com.br/fnet/publico/"
                    f"downloadDocumento?id={value}"
                    if str(value).isdigit()
                    else ""
                )
            ),
            "page": frame["page"].str.strip(),
            "status": "encontrado_explicito",
            "confidence": 1.0,
            "excerpt": frame["reason"].str.strip(),
            "nature": (
                "rentabilidade-alvo documentada · "
                + frame["classe_serie"].str.strip()
            ),
            "decision": frame["decision"].str.strip(),
            "reason": frame["reason"].str.strip(),
        }
    )
    if output.duplicated(
        ["selection_cutoff", "ranking_table", "cnpj", "value", "source_id"]
    ).any():
        raise ValueError("curadoria de remuneração-alvo contém linha duplicada")
    return output


def load_sacado_display_curation(path: Path) -> pd.DataFrame:
    """Load the editorial debtor summaries used only by slides 10–17.

    The full documentary wording remains in ``sacado``.  This small curation
    prevents a native Office table from publishing arbitrary character cuts as
    if they were complete descriptions.  A row may deliberately resolve to
    ``N/D`` when the underlying extraction is not a debtor observation.
    """

    required = {"cnpj", "sacado_exibicao", "decisao", "racional"}
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            "curadoria de exibição de sacado sem colunas: "
            + ", ".join(sorted(missing))
        )
    frame = frame[list(required)].copy()
    frame["cnpj"] = frame["cnpj"].map(_digits)
    if not frame["cnpj"].str.fullmatch(r"\d{14}").all():
        raise ValueError("curadoria de exibição de sacado contém CNPJ inválido")
    if frame["cnpj"].duplicated().any():
        raise ValueError("curadoria de exibição de sacado contém CNPJ duplicado")
    if frame["sacado_exibicao"].map(lambda value: not str(value).strip()).any():
        raise ValueError("curadoria de exibição de sacado contém resumo vazio")
    allowed = {"RESUMO_SEMANTICO", "MANTER_LITERAL", "REJEITAR_ARTEFATO"}
    invalid_decisions = sorted(set(frame["decisao"]) - allowed)
    if invalid_decisions:
        raise ValueError(
            "curadoria de exibição de sacado contém decisão inválida: "
            + ", ".join(invalid_decisions)
        )
    return frame.sort_values("cnpj", kind="stable").reset_index(drop=True)


def apply_sacado_display_curation(
    audit: pd.DataFrame,
    curation: pd.DataFrame,
) -> pd.DataFrame:
    """Attach display-only debtor summaries without changing raw audit values."""

    output = audit.copy()
    output["sacado_exibicao"] = TEXT_ND
    output["regra_exibicao_sacado"] = TEXT_ND
    curated = {
        row["cnpj"]: row
        for row in curation.to_dict(orient="records")
    }
    top_mask = output["bloco"].eq(TOP15_BLOCK)
    raw_cnpjs = {
        _digits(row.get("cnpj"))
        for row in output[top_mask].to_dict(orient="records")
        if not is_missing(row.get("sacado"))
    }
    missing_curation = sorted(raw_cnpjs.difference(curated))
    if missing_curation:
        raise ValueError(
            "sacados preenchidos sem resumo editorial por CNPJ: "
            + ", ".join(missing_curation)
        )
    unused_curation = sorted(set(curated).difference(raw_cnpjs))
    if unused_curation:
        raise ValueError(
            "curadoria de sacado sem texto integral no payload: "
            + ", ".join(unused_curation)
        )

    for index, row in output[top_mask].iterrows():
        cnpj = _digits(row.get("cnpj"))
        if is_missing(row.get("sacado")):
            output.at[index, "regra_exibicao_sacado"] = (
                "N/D — campo documental ausente"
            )
            continue
        decision = curated[cnpj]
        output.at[index, "sacado_exibicao"] = (
            str(decision["sacado_exibicao"]).strip() or TEXT_ND
        )
        output.at[index, "regra_exibicao_sacado"] = (
            f"{decision['decisao']} — {decision['racional']}"
        )
    return output


def _remuneration_tranche_family(value: object) -> str:
    folded = _fold(value)
    if "senior" in folded:
        return "Sênior"
    if "mezanino" in folded:
        return "Mezanino"
    return ""


def _remuneration_signature(value: object) -> tuple[str, float] | None:
    text = str(value or "")
    spread = re.search(
        r"\b(?:CDI|DI)\s*\+\s*(\d{1,3}(?:[.,]\d+)?)\s*%",
        text,
        flags=re.IGNORECASE,
    )
    if spread:
        return "interbank_spread", float(spread.group(1).replace(",", "."))
    percent = re.search(
        r"\b(\d{1,3}(?:[.,]\d+)?)\s*%\s*(?:do|da)\s*(?:CDI|DI)\b",
        text,
        flags=re.IGNORECASE,
    )
    if percent:
        return "percent_interbank", float(percent.group(1).replace(",", "."))
    return None


def build_remuneration_comparison_analysis(
    evidence: pd.DataFrame,
) -> dict[str, object]:
    """Build the two matched-sample readings used below slides 10–17.

    ``tier_pairs`` compares, within the same fund and cutoff, the lowest
    documented interbank spread in the Sênior level with the lowest documented
    spread in the Mezanino level.  ``matched_pairs`` compares the set of target
    rates for the same CNPJ and broad tranche family in both ranking cutoffs.
    DI and CDI keep their literal wording in the evidence table; for the
    semester movement they share the interbank-spread signature, so a change in
    benchmark spelling without a change in numerical spread is not counted as
    a rate movement.
    """

    required = {
        "cnpj",
        "fundo",
        "classe_serie",
        "value",
        "selection_cutoff",
        "ranking_table",
    }
    missing = required.difference(evidence.columns)
    if missing:
        raise ValueError(
            "evidência de remuneração sem colunas para comparação: "
            + ", ".join(sorted(missing))
        )
    frame = evidence.copy()
    frame["tranche_family"] = frame["classe_serie"].map(
        _remuneration_tranche_family
    )
    frame["signature"] = frame["value"].map(_remuneration_signature)
    frame = frame[
        frame["tranche_family"].ne("") & frame["signature"].notna()
    ].copy()
    frame["rate_kind"] = frame["signature"].map(lambda item: item[0])
    frame["rate_value"] = frame["signature"].map(lambda item: item[1])

    tier_pairs: list[dict[str, object]] = []
    interbank = frame[frame["rate_kind"].eq("interbank_spread")]
    for (cutoff, cnpj), group in interbank.groupby(
        ["selection_cutoff", "cnpj"], sort=True
    ):
        senior = group[group["tranche_family"].eq("Sênior")]["rate_value"]
        mezzanine = group[group["tranche_family"].eq("Mezanino")]["rate_value"]
        if senior.empty or mezzanine.empty:
            continue
        senior_min = float(senior.min())
        mezzanine_min = float(mezzanine.min())
        tier_pairs.append(
            {
                "cutoff": str(cutoff),
                "ranking_table": next(
                    (
                        str(value)
                        for value in group["ranking_table"]
                        if str(value).strip()
                    ),
                    "",
                ),
                "cnpj": str(cnpj),
                "fundo": str(group.iloc[0]["fundo"]),
                "senior_min_spread_pct": senior_min,
                "mezzanine_min_spread_pct": mezzanine_min,
                "premium_bps": int(round((mezzanine_min - senior_min) * 100)),
                "metodo": "menor spread CDI/DI+ documentado por nível",
            }
        )
    premiums = [int(row["premium_bps"]) for row in tier_pairs]
    tier_summary = {
        "pairs": len(tier_pairs),
        "median_bps": int(round(float(np.median(premiums)))) if premiums else 0,
        "min_bps": min(premiums) if premiums else 0,
        "max_bps": max(premiums) if premiums else 0,
        "unit": "fundo-corte",
        "method": "menor spread CDI/DI+ documentado em Sênior e Mezanino no mesmo fundo e corte",
    }

    ranked = frame[frame["ranking_table"].astype(str).str.strip().ne("")]
    signatures: dict[tuple[str, str, str], tuple[tuple[str, float], ...]] = {}
    names: dict[str, str] = {}
    for (cutoff, cnpj, family), group in ranked.groupby(
        ["selection_cutoff", "cnpj", "tranche_family"], sort=True
    ):
        signatures[(str(cutoff), str(cnpj), str(family))] = tuple(
            sorted(set(group["signature"]))
        )
        names[str(cnpj)] = str(group.iloc[0]["fundo"])
    prior_cutoff = "2025-12-31"
    current_cutoff = "2026-06-30"
    prior_keys = {
        (cnpj, family)
        for cutoff, cnpj, family in signatures
        if cutoff == prior_cutoff
    }
    current_keys = {
        (cnpj, family)
        for cutoff, cnpj, family in signatures
        if cutoff == current_cutoff
    }
    matched_pairs: list[dict[str, object]] = []
    for cnpj, family in sorted(prior_keys.intersection(current_keys)):
        prior = signatures[(prior_cutoff, cnpj, family)]
        current = signatures[(current_cutoff, cnpj, family)]
        changed = prior != current
        delta_bps: int | None = None
        if (
            len(prior) == 1
            and len(current) == 1
            and prior[0][0] == current[0][0] == "interbank_spread"
        ):
            delta_bps = int(round((current[0][1] - prior[0][1]) * 100))
        matched_pairs.append(
            {
                "cnpj": cnpj,
                "fundo": names.get(cnpj, ""),
                "tranche_family": family,
                "prior_signatures": list(prior),
                "current_signatures": list(current),
                "changed": changed,
                "delta_bps": delta_bps,
            }
        )
    changed_pairs = [row for row in matched_pairs if row["changed"]]
    matched_summary = {
        "pairs": len(matched_pairs),
        "changed_pairs": len(changed_pairs),
        "unchanged_pairs": len(matched_pairs) - len(changed_pairs),
        "unit": "fundo-classe",
        "method": "mesmo CNPJ e família de tranche nos rankings de dez/25 e jun/26",
    }
    return {
        "tier_pairs": tier_pairs,
        "tier_summary": tier_summary,
        "matched_pairs": matched_pairs,
        "matched_summary": matched_summary,
    }


def _select_remunerations(
    evidence: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
) -> dict[str, SelectedValue]:
    if evidence.empty:
        return {}
    frame = evidence.copy()
    frame["cnpj"] = frame["cnpj"].map(_digits)
    frame["_date"] = _series(frame, "document_date").map(_parse_date)
    frame["_selection_cutoff"] = _series(frame, "selection_cutoff").map(
        _parse_date
    )
    frame = frame[
        _series(frame, "field").astype(str).eq("remuneracao_alvo")
        & _series(frame, "status").astype(str).isin(_APPROVED_EVIDENCE)
        & ~_series(frame, "value").map(is_missing)
        & ~_series(frame, "source_kind").astype(str).eq("candidate_extraction")
        & (frame["_date"].isna() | frame["_date"].le(cutoff))
        & frame["cnpj"].str.fullmatch(r"\d{14}")
    ].copy()
    if frame["_selection_cutoff"].notna().any():
        frame = frame[frame["_selection_cutoff"].eq(cutoff)].copy()
        output: dict[str, SelectedValue] = {}
        for cnpj, group in frame.groupby("cnpj", sort=False):
            group = group.sort_values(
                ["value", "source_id"], kind="stable"
            )
            pairs = list(
                dict.fromkeys(str(value).strip() for value in group["value"])
            )
            sources = list(
                dict.fromkeys(
                    _document_label(row)
                    for row in group.to_dict(orient="records")
                )
            )
            natures = list(
                dict.fromkeys(
                    str(value).strip()
                    for value in group["nature"]
                    if str(value).strip()
                )
            )
            output[cnpj] = SelectedValue(
                value=" | ".join(pairs),
                source=" | ".join(sources),
                nature=" | ".join(natures),
                exception=len(pairs) > 1,
            )
        return output
    if frame.empty:
        return {}
    frame["_priority"] = frame["source_kind"].map(
        lambda value: _REMUNERATION_PRIORITY.get(str(value), 80)
    )
    frame["_confidence"] = pd.to_numeric(
        _series(frame, "confidence"), errors="coerce"
    ).fillna(0)
    output: dict[str, SelectedValue] = {}
    for cnpj, group in frame.groupby("cnpj", sort=False):
        if group["_date"].notna().any():
            group = group[group["_date"].eq(group["_date"].max())]
        group = group[group["_priority"].eq(group["_priority"].min())]
        group = group.sort_values(
            ["_confidence", "source_id", "value"],
            ascending=[False, False, True],
            kind="stable",
        )
        # Keep a single documentary event.  A source may define more than one
        # class/series; those rates remain together and visibly starred.
        selected_source = str(group.iloc[0].get("source_id") or "")
        same_source = group[group["source_id"].astype(str).eq(selected_source)]
        pairs = list(dict.fromkeys(str(value).strip() for value in same_source["value"]))
        representative = same_source.iloc[0].to_dict()
        exception = len(pairs) > 1 or any(
            "classe/série n/d" in _fold(value) for value in same_source["nature"]
        )
        output[cnpj] = SelectedValue(
            value=" | ".join(pairs),
            source=_document_label(representative),
            nature=str(representative.get("nature") or "").strip(),
            exception=exception,
        )
    return output


def _table_cutoff(value: object) -> pd.Timestamp:
    match = re.search(r"(20\d{2})-(\d{2})", str(value or ""))
    if not match:
        return DOCUMENT_CUTOFF
    period = pd.Period(f"{match.group(1)}-{match.group(2)}", freq="M")
    return period.end_time.normalize()


def _legal_cedents(cedent_triage: pd.DataFrame) -> tuple[dict[str, str], set[str]]:
    if cedent_triage.empty:
        return {}, set()
    frame = cedent_triage.copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(_digits)
    covered = set(frame["cnpj_fundo"])
    values: dict[str, str] = {}
    for cnpj, group in frame.groupby("cnpj_fundo", sort=False):
        names: list[str] = []
        for row in group.to_dict(orient="records"):
            if not _truthy(row.get("cedente_declarado_flag")):
                continue
            value = row.get("cedente_razao_social_consolidada")
            if is_missing(value):
                value = row.get("cedente_razao_social_coluna_k")
            text = str(value or "").strip()
            if text and not is_missing(text) and text not in names:
                names.append(text)
        if names:
            values[cnpj] = " | ".join(names)
    return values, covered


def _merge_source(originator_source: str, cedent_source: str, fallback: object) -> str:
    parts = []
    if originator_source and not is_missing(originator_source):
        parts.append(f"Originador: {originator_source}")
    if cedent_source and not is_missing(cedent_source):
        parts.append(f"Cedente: {cedent_source}")
    if parts:
        return " | ".join(parts)
    return str(fallback or TEXT_ND).strip() or TEXT_ND


def enrich_emission_field_audit(
    audit: pd.DataFrame,
    *,
    cedent_triage: pd.DataFrame,
    documentary_evidence: Iterable[pd.DataFrame],
    scan_checkpoint: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Fill Top 15 gaps without replacing supported values or inferring roles."""

    output = audit.copy()
    output["cnpj"] = output["cnpj"].map(_digits)
    if "remuneracao_por_tipo_cota" not in output.columns:
        output["remuneracao_por_tipo_cota"] = TEXT_ND
    if "fonte_remuneracao" not in output.columns:
        output["fonte_remuneracao"] = TEXT_ND
    evidence_frames = [frame for frame in documentary_evidence if frame is not None and not frame.empty]
    all_evidence = (
        pd.concat(evidence_frames, ignore_index=True, sort=False)
        if evidence_frames
        else pd.DataFrame()
    )
    selected = _select_document_fields(all_evidence)
    remuneration_by_cutoff: dict[pd.Timestamp, dict[str, SelectedValue]] = {}
    legal_cedents, triage_scope = _legal_cedents(cedent_triage)
    scan_status: dict[str, str] = {}
    if scan_checkpoint is not None and not scan_checkpoint.empty:
        scan = scan_checkpoint.copy()
        scan["cnpj"] = scan["cnpj"].map(_digits)
        scan_status = {
            row["cnpj"]: str(row.get("online_status") or row.get("status") or "")
            for row in scan.to_dict(orient="records")
        }

    for column in ("fonte_originador", "fonte_cedente", "tipo_subordinacao_minima", "motivo_nd"):
        output[column] = TEXT_ND

    top_mask = output["bloco"].eq(TOP15_BLOCK)
    for index, row in output[top_mask].iterrows():
        cnpj = row["cnpj"]
        originator_source = ""
        cedent_source = ""
        existing_party_source = str(row.get("fonte_originador_cedente") or "")
        party_source_is_audited = not is_missing(existing_party_source)
        originator_current = row.get("originador")
        cedent_current = row.get("cedente")
        if not is_missing(originator_current) and (
            not party_source_is_audited
            or classify_party_value(originator_current)
            != "entidade_ou_ecossistema_nomeado"
        ):
            output.at[index, "originador"] = TEXT_ND
            originator_current = TEXT_ND
        if not is_missing(cedent_current) and (
            not party_source_is_audited
            or classify_party_value(cedent_current)
            != "entidade_ou_ecossistema_nomeado"
        ):
            output.at[index, "cedente"] = TEXT_ND
            cedent_current = TEXT_ND

        originator = selected.get((cnpj, "originador"))
        if is_missing(originator_current) and originator:
            output.at[index, "originador"] = originator.value
            originator_source = originator.source
        elif not is_missing(originator_current):
            originator_source = existing_party_source

        legal_cedent = legal_cedents.get(cnpj)
        documented_cedent = selected.get((cnpj, "cedente"))
        if legal_cedent:
            output.at[index, "cedente"] = legal_cedent
            cedent_source = (
                "CVM · Informe Mensal FIDC · Tabela I · jun/26 · "
                "cedente legal declarado"
            )
        elif is_missing(cedent_current) and documented_cedent:
            output.at[index, "cedente"] = documented_cedent.value
            cedent_source = documented_cedent.source
        elif not is_missing(cedent_current):
            cedent_source = existing_party_source
        output.at[index, "fonte_originador"] = originator_source or TEXT_ND
        output.at[index, "fonte_cedente"] = cedent_source or TEXT_ND
        output.at[index, "fonte_originador_cedente"] = _merge_source(
            originator_source,
            cedent_source,
            row.get("fonte_originador_cedente"),
        )

        minimum = selected.get((cnpj, "minimo_junior"))
        minimum_type = "júnior"
        if minimum is None:
            minimum = selected.get((cnpj, "minimo_estrutural_total"))
            minimum_type = (
                (minimum.nature or "estrutural/total") if minimum else "N/D"
            )
        if is_missing(row.get("subordinacao_minima")) and minimum:
            suffix = "*" if minimum_type != "júnior" else ""
            label = "Jr." if minimum_type == "júnior" else "Estrut."
            output.at[index, "subordinacao_minima"] = f"{label} {minimum.value}{suffix}"
            output.at[index, "fonte_subordinacao"] = minimum.source
            output.at[index, "tipo_subordinacao_minima"] = minimum_type
        elif not is_missing(row.get("subordinacao_minima")):
            output.at[index, "tipo_subordinacao_minima"] = "conforme fonte existente"

        cutoff = _table_cutoff(row.get("tabela"))
        if cutoff not in remuneration_by_cutoff:
            remuneration_by_cutoff[cutoff] = _select_remunerations(
                all_evidence,
                cutoff=cutoff,
            )
        remunerations = remuneration_by_cutoff[cutoff]
        remuneration = remunerations.get(cnpj)
        if remuneration:
            output.at[index, "remuneracao_por_tipo_cota"] = (
                remuneration.value + ("*" if remuneration.exception else "")
            )
            output.at[index, "fonte_remuneracao"] = remuneration.source

        debtor = selected.get((cnpj, "sacado_devedor"))
        if is_missing(row.get("sacado")) and debtor:
            output.at[index, "sacado"] = debtor.value
            output.at[index, "fonte_sacado"] = debtor.source

        reasons: list[str] = []
        if is_missing(output.at[index, "originador"]):
            reasons.append("originador: papel explícito não localizado em documento")
        if is_missing(output.at[index, "cedente"]):
            reasons.append(
                "cedente: Tabela I sem declaração"
                if cnpj in triage_scope
                else "cedente: CNPJ fora do corte Top 437"
            )
        if is_missing(output.at[index, "subordinacao_minima"]):
            reasons.append("sub. mín.: cláusula explícita não localizada")
        if is_missing(output.at[index, "remuneracao_por_tipo_cota"]):
            reasons.append(
                "remuneração-alvo: benchmark numérico da cota/série não localizado"
            )
        if is_missing(output.at[index, "sacado"]):
            reasons.append("sacado: campo ausente na CVM e não localizado em documento")
        status = scan_status.get(cnpj, "")
        if status.startswith("erro"):
            reasons.append(f"scanner: {status}")
        output.at[index, "motivo_nd"] = "; ".join(reasons) or "campos cobertos"
        if reasons:
            output.at[index, "status"] = (
                "Fontes encadeadas por CNPJ; lacunas remanescentes: "
                + "; ".join(reasons)
            )
        else:
            output.at[index, "status"] = "Fontes encadeadas por CNPJ; cinco campos cobertos"
    return output


def build_emission_field_coverage(
    before: pd.DataFrame,
    after: pd.DataFrame,
    ranking: pd.DataFrame,
) -> pd.DataFrame:
    """Measure row and PL coverage for each type/period page."""

    ranked = ranking.copy()
    ranked["cnpj"] = ranked["cnpj_fundo"].map(_digits)
    ranked["tabela"] = (
        ranked["tipo_exibicao"].astype(str)
        + " · "
        + ranked["competencia"].astype(str)
    )
    ranked = ranked[pd.to_numeric(ranked["rank_tipo"], errors="coerce").le(15)]
    pl_by_key = {
        (row["tabela"], row["cnpj"]): float(row.get("pl") or 0.0)
        for row in ranked.to_dict(orient="records")
    }

    base = before[before["bloco"].eq(TOP15_BLOCK)].copy()
    final = after[after["bloco"].eq(TOP15_BLOCK)].copy()
    base["cnpj"] = base["cnpj"].map(_digits)
    final["cnpj"] = final["cnpj"].map(_digits)
    rows: list[dict[str, object]] = []
    for table, group_after in final.groupby("tabela", sort=True):
        group_before = base[base["tabela"].eq(table)].set_index("cnpj")
        group_after = group_after.set_index("cnpj")
        pl = pd.Series(
            {cnpj: pl_by_key.get((table, cnpj), 0.0) for cnpj in group_after.index},
            dtype=float,
        )
        total_pl = float(pl.sum())
        type_name, period = table.rsplit(" · ", 1)
        for field in FIELDS:
            before_mask = ~group_before.reindex(group_after.index)[field].map(is_missing)
            after_mask = ~group_after[field].map(is_missing)
            before_pl = float(pl[before_mask.fillna(False)].sum())
            after_pl = float(pl[after_mask].sum())
            waiver_reason = PAGE_COVERAGE_WAIVERS.get((type_name, field), "")
            publication_floor = (
                0.0 if waiver_reason else float(DEFAULT_COVERAGE_FLOORS[field])
            )
            rows.append(
                {
                    "tabela": table,
                    "tipo": type_name,
                    "competencia": period,
                    "campo": field,
                    "linhas_total": int(len(group_after)),
                    "antes_com_dado": int(before_mask.fillna(False).sum()),
                    "antes_cobertura_pct": float(before_mask.fillna(False).mean()),
                    "antes_pl_coberto_brl": before_pl,
                    "antes_cobertura_pl_pct": before_pl / total_pl if total_pl else 0.0,
                    "depois_com_dado": int(after_mask.sum()),
                    "depois_cobertura_pct": float(after_mask.mean()),
                    "depois_pl_coberto_brl": after_pl,
                    "depois_cobertura_pl_pct": after_pl / total_pl if total_pl else 0.0,
                    "nd_depois": int((~after_mask).sum()),
                    "piso_publicacao_pct": publication_floor,
                    "piso_atendido": bool(
                        waiver_reason
                        or after_mask.mean() >= publication_floor
                    ),
                    "excecao_publicacao": waiver_reason or TEXT_ND,
                }
            )
    return pd.DataFrame(rows)


def validate_emission_field_coverage(
    coverage: Iterable[Mapping[str, object]],
) -> list[str]:
    """Return contract violations; an empty list means the payload may publish."""

    rows = list(coverage)
    violations: list[str] = []
    expected = 8 * len(FIELDS)
    if len(rows) != expected:
        violations.append(f"cobertura esperava {expected} linhas; recebeu {len(rows)}")
        return violations
    for row in rows:
        field = str(row.get("campo") or "")
        table = str(row.get("tabela") or "")
        share = float(row.get("depois_cobertura_pct") or 0.0)
        raw_floor = row.get("piso_publicacao_pct")
        floor = float(
            DEFAULT_COVERAGE_FLOORS.get(field, 1.0)
            if raw_floor is None or str(raw_floor).strip() == ""
            else raw_floor
        )
        filled = int(row.get("depois_com_dado") or 0)
        waiver = str(row.get("excecao_publicacao") or "").strip()
        waived = field == "originador" and table.startswith("Outros ·") and not is_missing(waiver)
        if field not in FIELDS:
            violations.append(f"{table}: campo de cobertura desconhecido {field!r}")
        elif (share < floor or (floor > 0 and filled <= 0)) and not waived:
            violations.append(
                f"{table} · {field}: {filled}/15 ({share:.1%}) abaixo do piso {floor:.1%}"
            )
    remuneration_total = sum(
        int(row.get("depois_com_dado") or 0)
        for row in rows
        if str(row.get("campo") or "") == "remuneracao_por_tipo_cota"
    )
    if remuneration_total <= 0:
        violations.append(
            "slides 10–17 · remuneração-alvo: coluna inteira sem evidência documental"
        )
    return violations
