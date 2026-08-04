"""Resumable documentary audit helpers for the 101-CNPJ portfolio.

The module deliberately separates three layers:

* values already accepted by the revision payload;
* explicit clauses located in primary documents;
* automatic candidates that still need human review.

Only the first two layers may improve the reported ``after`` coverage.  A
candidate extracted from a fund name, a loose keyword or an unbound CNPJ stays
in the evidence log and never becomes a portfolio fact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import re
import unicodedata
from typing import Iterable, Mapping, Sequence

import pandas as pd


SCHEMA_VERSION = "carteira-101-document-audit/v2"
TEXT_ND = "N/D"

AUDITED_FIELDS: tuple[str, ...] = (
    "originador",
    "cedente",
    "sacado_devedor",
    "tipo_recebivel",
    "minimo_junior",
    "minimo_estrutural_total",
    "natureza_indice",
)

SOURCE_PRIORITY: Mapping[str, int] = {
    "rating_report": 10,
    "regulamento": 20,
    "emissao": 25,
    "assembleia": 30,
    "informe_mensal": 40,
    "payload_documental": 50,
    "planilha_manual": 60,
    "candidate_extraction": 90,
}

_MISSING_MARKERS = {"", "n/d", "n d", "nd", "nan", "none", "null", "na"}
_EXPLICIT_STATUS = {"aceito_payload", "encontrado_explicito"}
_CURATED_STRUCTURAL_FIELDS = {
    "minimo_junior",
    "minimo_estrutural_total",
    "natureza_indice",
}


@dataclass(frozen=True)
class DocumentSource:
    cnpj: str
    source_kind: str
    source_id: str
    document_class: str
    document_date: str
    source_path: str
    source_url: str
    text: str
    pages: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class Evidence:
    cnpj: str
    field: str
    value: str
    source_kind: str
    source_id: str
    document_class: str
    document_date: str
    source_path: str
    source_url: str
    page: str
    status: str
    confidence: float
    excerpt: str
    nature: str = ""


@dataclass(frozen=True)
class PriceEvidence:
    cnpj: str
    class_series: str
    price_display: str
    source_kind: str
    source_id: str
    document_class: str
    document_date: str
    source_path: str
    source_url: str
    page: str
    status: str
    excerpt: str
    price_nature: str = "N/D"
    exception_flag: str = ""
    exception_reason: str = ""


@dataclass(frozen=True)
class Carteira101DocumentAuditMaterialization:
    """Versioned, publication-ready tables; loading never starts a scan."""

    audit: pd.DataFrame
    coverage: pd.DataFrame
    evidence: pd.DataFrame
    prices: pd.DataFrame
    checkpoint: pd.DataFrame
    manifest: dict[str, object]


def load_document_audit_materialization(
    base_dir: Path,
    *,
    prefix: str = "carteira_101_document",
) -> Carteira101DocumentAuditMaterialization:
    """Load accepted scan outputs without consulting documents or the network."""

    paths = {
        "audit": base_dir / f"{prefix}_audit.csv",
        "coverage": base_dir / f"{prefix}_coverage.csv",
        "evidence": base_dir / f"{prefix}_evidence.csv.gz",
        "prices": base_dir / f"{prefix}_prices.csv.gz",
        "checkpoint": base_dir / f"{prefix}_checkpoint.jsonl",
        "manifest": base_dir / f"{prefix}_manifest.json",
    }
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"materialização documental incompleta: {missing}")
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            "schema documental incompatível: "
            f"{manifest.get('schema_version')!r} != {SCHEMA_VERSION!r}"
        )
    checkpoint_rows = list(read_checkpoint(paths["checkpoint"]).values())
    return Carteira101DocumentAuditMaterialization(
        audit=pd.read_csv(paths["audit"], dtype={"cnpj": str}),
        coverage=pd.read_csv(paths["coverage"]),
        evidence=pd.read_csv(paths["evidence"], dtype={"cnpj": str}),
        prices=pd.read_csv(paths["prices"], dtype={"cnpj": str}),
        checkpoint=pd.DataFrame(checkpoint_rows),
        manifest=manifest,
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def normalize_cnpj(value: object) -> str:
    """Return a 14-digit CNPJ without losing leading zeroes."""

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, int):
        digits = str(value)
    elif isinstance(value, float) and value.is_integer():
        digits = str(int(value))
    else:
        raw = str(value).strip()
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?[eE][+-]?[0-9]+", raw):
            try:
                number = Decimal(raw)
            except InvalidOperation:
                return ""
            if number != number.to_integral_value():
                return ""
            digits = str(int(number))
        else:
            digits = re.sub(r"\D", "", raw)
    if not digits or len(digits) > 14:
        return ""
    return digits.zfill(14)


def is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    folded = fold_text(value)
    return folded in _MISSING_MARKERS or folded.startswith("n d ")


def fold_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-zA-Z0-9]+", " ", text).lower().split())


def compact_text(value: object, *, limit: int = 1200) -> str:
    text = " ".join(str(value or "").replace("\u00a0", " ").split())
    return text[:limit].strip()


def source_priority(source_kind: str) -> int:
    return SOURCE_PRIORITY.get(source_kind, 80)


def fundonet_download_url(document_id: object) -> str:
    digits = re.sub(r"\D", "", str(document_id or ""))
    if not digits:
        return ""
    return (
        "https://fnet.bmfbovespa.com.br/fnet/publico/"
        f"downloadDocumento?id={digits}"
    )


def classify_source_kind(
    *, document_class: object = "", description: object = ""
) -> str:
    folded = fold_text(f"{document_class} {description}")
    if any(
        token in folded
        for token in (
            "relatorio de agencia de rating",
            "relatorio de rating",
            "classificacao de risco",
            "standard poor",
            "moodys",
            "fitch",
            "austin rating",
            "liberum ratings",
        )
    ):
        return "rating_report"
    if "regulamento" in folded or "aditamento" in folded:
        return "regulamento"
    if any(token in folded for token in ("emissao", "suplemento", "oferta")):
        return "emissao"
    if any(token in folded for token in ("assembleia", "ata", "deliberacao")):
        return "assembleia"
    if "informe mensal" in folded:
        return "informe_mensal"
    return "outro"


def _page_for_offset(source: DocumentSource, offset: int) -> str:
    if not source.pages:
        return ""
    cumulative = 0
    for page_number, page_text in source.pages:
        cumulative += len(page_text) + 1
        if offset <= cumulative:
            return str(page_number)
    return str(source.pages[-1][0])


def _explicit_definition_matches(
    source: DocumentSource,
    *,
    field: str,
    terms: Sequence[str],
    nature: str = "",
) -> list[Evidence]:
    """Extract quoted or capitalized contractual definitions conservatively."""

    text = source.text
    term_pattern = "|".join(re.escape(term) for term in terms)
    patterns = (
        # Contractual glossaries consistently quote the defined term. Requiring
        # the quotes avoids treating an incidental use of "cedente" or
        # "devedor" elsewhere in a long paragraph as a definition.
        re.compile(
            rf"[\"“](?:{term_pattern})(?:\s+[^\"”\n]{{1,60}})?[\"”]"
            rf"\s+(?:significa|significam)\s+(?P<value>.{{8,700}}?)"
            rf"(?=(?:[.;]\s+[\"“A-ZÁÀÂÃÉÊÍÓÔÕÚÇ])|\n\s*\n)",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            rf"(?P<value>[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-ZÁÀÂÃÉÊÍÓÔÕÚÇa-záàâãéêíóôõúç0-9 .,&'/-]{{5,180}}?)"
            rf",?\s+(?:doravante\s+)?(?:denominad[ao]|designad[ao])\s+[\"“”]?(?:{term_pattern})[\"“”]?",
            re.IGNORECASE | re.DOTALL,
        ),
    )
    results: list[Evidence] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = compact_text(match.group("value"), limit=500)
            folded = fold_text(value)
            if len(value) < 8 or folded in seen:
                continue
            if any(
                marker in folded
                for marker in (
                    "este regulamento",
                    "a regulamentacao aplicavel",
                    "conforme definido",
                    "qualquer pessoa",
                )
            ) and not re.search(r"\b(?:S\.?A\.?|LTDA|CNPJ)\b", value, re.I):
                continue
            seen.add(folded)
            excerpt_start = max(0, match.start() - 120)
            excerpt_end = min(len(text), match.end() + 120)
            results.append(
                Evidence(
                    cnpj=source.cnpj,
                    field=field,
                    value=value,
                    source_kind=source.source_kind,
                    source_id=source.source_id,
                    document_class=source.document_class,
                    document_date=source.document_date,
                    source_path=source.source_path,
                    source_url=source.source_url,
                    page=_page_for_offset(source, match.start()),
                    status="encontrado_explicito",
                    confidence=0.95,
                    excerpt=compact_text(text[excerpt_start:excerpt_end]),
                    nature=nature,
                )
            )
    return results


_PARTY_TABLE_LABELS = (
    "Administrador|Administradora|Gestor|Gestora|Custodiante|Cedente|Cedentes|"
    "Originador|Originadora|Originadores|Originadoras|Sacado|Sacados|Devedor|"
    "Devedores|Provedor|Agente|Proteção|Rating|Emissor|Endossante|Prazo|Conta|"
    "Estruturador|Coordenador|Servicer|Consultor|Consultora"
)


def _explicit_party_label_matches(
    source: DocumentSource,
    *,
    field: str,
    terms: Sequence[str],
) -> list[Evidence]:
    """Extract explicit participant-table labels and direct role annotations.

    Rating reports frequently identify transaction parties in a two-column table
    whose PDF text is emitted as ``Originador EMPRESA``.  The label and the
    following value are documentary evidence even when the document does not use
    a contractual ``significa`` definition.
    """

    if source.source_kind != "rating_report":
        return []

    text = source.text
    term_pattern = "|".join(re.escape(term) for term in terms)
    line_pattern = re.compile(
        rf"^\s*(?:{term_pattern})(?:\s*/\s*Servicer)?\s*(?::|[-–—])?\s+"
        rf"(?P<value>[^\n]+(?:\n(?!\s*(?:{_PARTY_TABLE_LABELS})\b)[^\n]+){{0,5}})",
        re.IGNORECASE | re.MULTILINE,
    )
    annotation_patterns = (
        # Entity/alias appears inside the parenthesis before the role:
        # ``(ACQIO / Cedente / Originadora)``.
        re.compile(
            rf"\(\s*(?P<value>[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-ZÁÀÂÃÉÊÍÓÔÕÚÇa-záàâãéêíóôõúç0-9 .&'-]{{1,80}}"
            rf"(?:/[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-ZÁÀÂÃÉÊÍÓÔÕÚÇa-záàâãéêíóôõúç0-9 .&'-]{{1,60}})*)"
            rf"\s*(?:/|,)\s*[^()\n]{{0,80}}(?i:(?:{term_pattern}))\b[^()\n]{{0,80}}\)",
        ),
        # Full entity immediately precedes a role-only parenthesis:
        # ``Solfácil Energia (Originadora)``.
        re.compile(
            rf"(?P<value>[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-ZÁÀÂÃÉÊÍÓÔÕÚÇa-záàâãéêíóôõúç0-9 .,&'/-]{{2,100}}?)"
            rf"\s*\(\s*(?i:(?:{term_pattern}))\s*\)",
        ),
    )
    results: list[Evidence] = []
    seen: set[str] = set()
    for pattern in (line_pattern, *annotation_patterns):
        for match in pattern.finditer(text):
            value = compact_text(match.group("value"), limit=500).strip(" ,-–—/:;")
            value = re.sub(r"^(?:e|pela|pelo)\s+", "", value, flags=re.IGNORECASE)
            folded = fold_text(value)
            tokens = set(folded.split())
            if (
                len(value) < 3
                or folded in seen
                or tokens <= {"na", "n/a", "servicer", "nd", "n/d"}
                or folded in {"na na", "n/a", "na", "nd", "n/d"}
                or folded.startswith(("na na ", "n/a n/a "))
            ):
                continue
            bad_markers = (
                "%",
                " max ",
                "enq ",
                " in ",
                "rating",
                "patrimonio liquido",
                "direitos creditorios",
                "clausula",
                "risco de ",
                "montante inicial",
                "data de inicio",
                "nao podera",
                "devera atender",
                "o fundo",
                "do fundo",
            )
            padded = f" {folded} "
            if any(marker in padded for marker in bad_markers):
                continue
            if field in {"originador", "cedente"}:
                if len(value) > 360 or len(value.split()) > 45:
                    continue
                if fold_text(value).strip(" .") in {
                    "ltda",
                    "s a",
                    "sa",
                    "instituicao",
                    "originador",
                    "cedente",
                }:
                    continue
            elif len(value) > 220 or len(value.split()) > 32:
                continue
            # Avoid swallowing a narrative paragraph after a bare role label.
            # Participant names/populations are short and do not end in a full
            # sentence with multiple verbs.
            if len(value) > 420 or value.count(".") > 12:
                continue
            seen.add(folded)
            results.append(
                Evidence(
                    cnpj=source.cnpj,
                    field=field,
                    value=value,
                    source_kind=source.source_kind,
                    source_id=source.source_id,
                    document_class=source.document_class,
                    document_date=source.document_date,
                    source_path=source.source_path,
                    source_url=source.source_url,
                    page=_page_for_offset(source, match.start()),
                    status="encontrado_explicito",
                    confidence=0.93,
                    excerpt=compact_text(
                        text[max(0, match.start() - 80) : min(len(text), match.end() + 80)]
                    ),
                    nature="rótulo explícito de participante v2",
                )
            )
    return results


def _receivable_matches(source: DocumentSource) -> list[Evidence]:
    text = source.text
    patterns = (
        re.compile(
            r"[\"“]Direitos Credit[oó]rios(?:\s+Eleg[ií]veis)?[\"”]\s+"
            r"(?:significa|significam|correspondem a|s[aã]o)\s+(?P<value>.{12,900}?)"
            r"(?=(?:[.;]\s+[\"“”A-ZÁÀÂÃÉÊÍÓÔÕÚÇ])|\n\s*\n)",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"(?:lastro|natureza dos direitos credit[oó]rios)\s*[:\-]\s*(?P<value>.{12,650}?)"
            r"(?=(?:[.;]\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ])|\n\s*\n)",
            re.IGNORECASE | re.DOTALL,
        ),
    )
    asset_tokens = re.compile(
        r"\b(?:duplicat|ccb|c[eé]dula|cpr|fgts|consignad|cart[aã]o|receb[ií]ve|"
        r"cr[eé]dito|contrato|nota fiscal|devedor|sacado|financiamento|empr[eé]stimo)\w*\b",
        re.IGNORECASE,
    )
    results: list[Evidence] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = compact_text(match.group("value"), limit=700)
            folded = fold_text(value)
            if not asset_tokens.search(value) or folded in seen:
                continue
            seen.add(folded)
            results.append(
                Evidence(
                    cnpj=source.cnpj,
                    field="tipo_recebivel",
                    value=value,
                    source_kind=source.source_kind,
                    source_id=source.source_id,
                    document_class=source.document_class,
                    document_date=source.document_date,
                    source_path=source.source_path,
                    source_url=source.source_url,
                    page=_page_for_offset(source, match.start()),
                    status="encontrado_explicito",
                    confidence=0.92,
                    excerpt=compact_text(
                        text[max(0, match.start() - 100) : min(len(text), match.end() + 100)]
                    ),
                )
            )
    return results


_PERCENT = r"(?P<pct>\d{1,3}(?:[.,]\d{1,4})?)\s*%"


def _minimum_matches(source: DocumentSource) -> list[Evidence]:
    text = source.text
    definitions: tuple[tuple[str, str, str], ...] = (
        (
            "minimo_junior",
            "junior_pl",
            rf"(?:[ií]ndice|percentual|rela[cç][aã]o)\s+(?:de\s+)?subordina[cç][aã]o\s+j[uú]nior"
            rf"[^.;\n]{{0,180}}?(?:m[ií]nim[oa]|n[aã]o\s+inferior|igual\s+ou\s+superior|mantid[oa])"
            rf"[^.;\n]{{0,80}}?{_PERCENT}",
        ),
        (
            "minimo_junior",
            "junior_pl",
            rf"{_PERCENT}[^.;\n]{{0,80}}?(?:m[ií]nim[oa]|n[aã]o\s+inferior|igual\s+ou\s+superior)"
            rf"[^.;\n]{{0,180}}?(?:[ií]ndice|percentual|rela[cç][aã]o)\s+(?:de\s+)?subordina[cç][aã]o\s+j[uú]nior",
        ),
        (
            "minimo_estrutural_total",
            "suporte_total_pl",
            rf"(?:[ií]ndice|percentual|rela[cç][aã]o)\s+(?:de\s+)?subordina[cç][aã]o\s+(?:s[eê]nior|total)"
            rf"[^.;\n]{{0,180}}?(?:m[ií]nim[oa]|n[aã]o\s+inferior|igual\s+ou\s+superior|mantid[oa])"
            rf"[^.;\n]{{0,80}}?{_PERCENT}",
        ),
        (
            "minimo_estrutural_total",
            "suporte_combinado_pl",
            rf"(?:cotas?\s+subordinadas?\s+j[uú]nior\s*(?:e|\+)\s*(?:cotas?\s+)?(?:subordinadas?\s+)?mezanino)"
            rf"[^.;\n]{{0,180}}?(?:m[ií]nim[oa]|n[aã]o\s+inferior|igual\s+ou\s+superior|mantid[oa])"
            rf"[^.;\n]{{0,80}}?{_PERCENT}",
        ),
    )
    results: list[Evidence] = []
    seen: set[tuple[str, str, str]] = set()
    for field, nature, raw_pattern in definitions:
        pattern = re.compile(raw_pattern, re.IGNORECASE | re.DOTALL)
        for match in pattern.finditer(text):
            pct = match.group("pct").replace(",", ".")
            try:
                number = float(pct)
            except ValueError:
                continue
            if not 0 < number <= 100:
                continue
            key = (field, nature, f"{number:.6f}")
            if key in seen:
                continue
            seen.add(key)
            value = f"{number:g}%"
            results.append(
                Evidence(
                    cnpj=source.cnpj,
                    field=field,
                    value=value,
                    source_kind=source.source_kind,
                    source_id=source.source_id,
                    document_class=source.document_class,
                    document_date=source.document_date,
                    source_path=source.source_path,
                    source_url=source.source_url,
                    page=_page_for_offset(source, match.start()),
                    status="encontrado_explicito",
                    confidence=0.95,
                    excerpt=compact_text(
                        text[max(0, match.start() - 180) : min(len(text), match.end() + 220)]
                    ),
                    nature=nature,
                )
            )
    return results


def _price_matches(source: DocumentSource) -> list[PriceEvidence]:
    text = source.text
    pattern = re.compile(
        r"(?P<nature>valor\s+nominal\s+unit[aá]rio|pre[cç]o\s+(?:de\s+)?(?:emiss[aã]o|"
        r"subscri[cç][aã]o|integraliza[cç][aã]o)|valor\s+unit[aá]rio\s+de\s+emiss[aã]o)"
        r"(?P<bridge>.{0,100}?)(?P<price>R\$\s*\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,6})?|"
        r"R\$\s*\d+(?:,\d{1,6})?)",
        re.IGNORECASE | re.DOTALL,
    )
    class_pattern = re.compile(
        r"(?:(?:\d+[ªa]\s*)?s[eé]rie\s+(?:de\s+)?)?cotas?\s+"
        r"(?:seniores?|subordinadas?(?:\s+(?:j[uú]nior|mezanino))?)",
        re.IGNORECASE,
    )
    results: list[PriceEvidence] = []
    seen: set[tuple[str, str]] = set()
    for match in pattern.finditer(text):
        price = compact_text(match.group("price"), limit=80)
        nature_literal = compact_text(match.group("nature"), limit=120)
        nature_folded = fold_text(nature_literal)
        bridge_literal = match.group("bridge")
        bridge_folded = fold_text(bridge_literal)
        if bridge_literal.count("\n") > 4:
            continue
        if any(
            marker in bridge_folded
            for marker in (
                "montante",
                "quantidade",
                "volume",
                "valor total",
                "montante total",
                "respectivamente",
                "limite de",
                "perfazendo",
                "totalizando",
                "correspondendo",
            )
        ):
            continue
        preceding_label = fold_text(text[max(0, match.start() - 120) : match.start()])
        if any(
            marker in preceding_label
            for marker in (
                "valor total da oferta",
                "montante total da oferta",
                "valor global da oferta",
            )
        ):
            continue
        unit_label = (
            "unitario" in nature_folded
            or bool(
                re.search(
                    r"\b(?:por|cada)\s+cotas?\b|\bunit[aá]ri[oa]\b",
                    bridge_literal,
                    re.IGNORECASE,
                )
            )
        )
        # A bare "preço de emissão" can denote the aggregate offer amount.
        # It is accepted only when the same clause explicitly says that the
        # amount is per cota/unitary.
        if not unit_label:
            continue
        if "valor nominal unitario" in nature_folded:
            price_nature = "Valor nominal unitário (VNU)"
        elif "valor unitario de emissao" in nature_folded:
            price_nature = "Valor unitário de emissão"
        elif "subscricao" in nature_folded:
            price_nature = "Preço de subscrição"
        elif "integralizacao" in nature_folded:
            price_nature = "Preço de integralização"
        else:
            price_nature = "Preço de emissão"
        preceding = text[max(0, match.start() - 700) : match.start()]
        class_matches = list(class_pattern.finditer(preceding))
        class_series = (
            compact_text(class_matches[-1].group(0), limit=140)
            if class_matches
            else TEXT_ND
        )
        exception_reasons: list[str] = []
        if class_series == TEXT_ND:
            exception_reasons.append("classe/série não identificada no trecho")
        if price_nature not in {
            "Valor nominal unitário (VNU)",
            "Valor unitário de emissão",
        }:
            exception_reasons.append(
                "natureza distinta de VNU; comparar conforme o documento"
            )
        key = (fold_text(class_series), fold_text(price))
        if key in seen:
            continue
        seen.add(key)
        results.append(
            PriceEvidence(
                cnpj=source.cnpj,
                class_series=class_series,
                price_display=price,
                source_kind=source.source_kind,
                source_id=source.source_id,
                document_class=source.document_class,
                document_date=source.document_date,
                source_path=source.source_path,
                source_url=source.source_url,
                page=_page_for_offset(source, match.start()),
                status="encontrado_explicito",
                excerpt=compact_text(
                    text[max(0, match.start() - 220) : min(len(text), match.end() + 220)]
                ),
                price_nature=price_nature,
                exception_flag="*" if exception_reasons else "",
                exception_reason="; ".join(exception_reasons),
            )
        )
    return results


_REMUNERATION_ANCHOR = re.compile(
    r"(?:meta\s+de\s+remunera[cç][aã]o|remunera[cç][aã]o\s+alvo|"
    r"remunera[cç][aã]o\s*\(\s*taxa\s*\)|"
    r"rentabilidade[-\s]+alvo|retorno\s+alvo|benchmark\s+alvo|"
    r"meta\s+de\s+rentabilidade(?:\s+priorit[aá]ria)?|"
    r"taxas?\s+de\s+remunera[cç][aã]o|benchmark\s+(?:das?\s+)?(?:cotas?|quotas?))",
    re.IGNORECASE,
)

_REMUNERATION_PLUS = re.compile(
    r"(?:(?:varia[cç][aã]o\s+da\s+)?taxa\s+)?"
    r"(?P<index>CDI|DI|IPCA|SELIC|IGP[-\s]?M)"
    r"\s*(?:,\s*)?(?:\+|acrescid[ao]\s+de(?:\s+um\s+spread\s+de)?)\s*"
    r"(?P<rate>\d{1,3}(?:[.,]\d{1,4})?)\s*(?P<pct>%?)",
    re.IGNORECASE,
)

_REMUNERATION_PERCENT_INDEX = re.compile(
    r"(?P<rate>\d{1,3}(?:[.,]\d{1,4})?)\s*%\s*(?:do|da)?\s*"
    r"(?P<index>CDI|DI|IPCA|SELIC|IGP[-\s]?M)",
    re.IGNORECASE,
)

_REMUNERATION_CLASS_PATTERNS = (
    re.compile(
        r"(?:(?P<series>\d{1,2}[ªa]\s+s[eé]rie)\s+(?:de\s+)?)?"
        r"(?:cotas?|quotas?)\s+"
        r"(?P<class>(?:subordinadas?\s+)?(?:seniores?|mezanino(?:\s+(?:\d{1,2}M|[A-Z]\b))?|j[uú]nior(?:es)?))"
        r"(?:\s+da\s+(?P<series_after>\d{1,2}[ªa]\s+s[eé]rie))?",
        re.IGNORECASE,
    ),
    re.compile(
        r"FIDC\s*[-–—]\s*(?P<class>senior|s[eê]nior|mezanino|j[uú]nior)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:nome\s+da\s+cota\s+)?(?P<class>mezanino\s+\d{1,2}M)"
        r"(?:\s+\d{1,2}\s+mes(?:es)?)?\s+(?:(?:taxa\s+)?(?:CDI|DI)|remunera[cç][aã]o)",
        re.IGNORECASE,
    ),
)


def _canonical_rate_index(value: str) -> str:
    folded = fold_text(value).replace(" ", "")
    if folded in {"di", "cdi"}:
        return "CDI"
    if folded == "igpm":
        return "IGP-M"
    return str(value or "").upper().replace(" ", "")


def _canonical_rate_number(value: str) -> str:
    raw = str(value or "").strip().replace(".", ",")
    return raw


def _remuneration_class_series(text: str, rate_start: int, rate_end: int) -> str:
    start = max(0, rate_start - 700)
    end = min(len(text), rate_end + 180)
    window = text[start:end]
    relative_rate_start = rate_start - start
    candidates: list[tuple[int, re.Match[str]]] = []
    for pattern in _REMUNERATION_CLASS_PATTERNS:
        for match in pattern.finditer(window):
            # Prefer the closest class label before the benchmark.  A label just
            # after the benchmark is accepted for compact rating-report tables.
            if match.end() <= relative_rate_start:
                distance = relative_rate_start - match.end()
            else:
                distance = 1000 + match.start() - relative_rate_start
            candidates.append((distance, match))
    if not candidates:
        return TEXT_ND
    _, match = min(candidates, key=lambda item: item[0])
    literal = compact_text(match.group("class"), limit=80)
    folded = fold_text(literal)
    if "mezanino" in folded:
        suffix_match = re.search(
            r"\bmezanino\s+(\d{1,2}M|[A-Z])\b",
            literal,
            re.I,
        )
        class_label = f"Mezanino {suffix_match.group(1)}" if suffix_match else "Mezanino"
    elif "junior" in folded:
        class_label = "Júnior"
    else:
        class_label = "Sênior"
    series = ""
    if "series" in match.re.groupindex:
        series = compact_text(match.groupdict().get("series") or "", limit=40)
    if "series_after" in match.re.groupindex and not series:
        series = compact_text(match.groupdict().get("series_after") or "", limit=40)
    return f"{class_label} · {series}" if series else class_label


def _remuneration_matches(source: DocumentSource) -> list[Evidence]:
    """Locate explicit target remuneration for a quota class or series.

    A benchmark expression is accepted only when a nearby clause identifies it
    as the quota's target remuneration/return.  This deliberately excludes
    excess spread of the receivables, assignment rates and service-provider
    remuneration even when those passages also contain CDI/IPCA references.
    """

    text = source.text
    results: list[Evidence] = []
    seen: set[tuple[str, str, str, str]] = set()
    for pattern, percent_of_index in (
        (_REMUNERATION_PLUS, False),
        (_REMUNERATION_PERCENT_INDEX, True),
    ):
        for match in pattern.finditer(text):
            context_start = max(0, match.start() - 520)
            context_end = min(len(text), match.end() + 180)
            context = text[context_start:context_end]
            anchors = list(_REMUNERATION_ANCHOR.finditer(context))
            class_series = _remuneration_class_series(
                text, match.start(), match.end()
            )
            if anchors:
                nearest_anchor = min(
                    anchors,
                    key=lambda item: abs(
                        (context_start + item.start()) - match.start()
                    ),
                )
                anchor_distance = abs(
                    (context_start + nearest_anchor.start()) - match.start()
                )
            elif re.search(r"\bbenchmark\b", context, re.IGNORECASE) and class_series != TEXT_ND:
                anchor_distance = 100
            else:
                continue
            # Missing percent signs occur in rating-report tables (for example
            # ``CDI + 3,10 a.a.``).  They are accepted only when the target label
            # is in the same compact row.
            if (
                not percent_of_index
                and not match.groupdict().get("pct")
                and anchor_distance > 140
            ):
                continue
            folded_context = fold_text(context)
            if any(
                marker in folded_context
                for marker in (
                    "no maximo",
                    "taxa maxima de remuneracao",
                    "a ser definido em procedimento de bookbuilding",
                    "a ser definida em procedimento de bookbuilding",
                )
            ):
                continue
            if (
                "remuneracao da administradora" in folded_context
                or "taxa de administracao" in folded_context
            ) and class_series == TEXT_ND:
                continue
            index = _canonical_rate_index(match.group("index"))
            rate = _canonical_rate_number(match.group("rate"))
            try:
                number = float(rate.replace(",", "."))
            except ValueError:
                continue
            if number <= 0 or number > (300 if percent_of_index else 100):
                continue
            benchmark = (
                f"{rate}% do {index}"
                if percent_of_index
                else f"{index} + {rate}% a.a."
            )
            value = (
                f"{class_series}: {benchmark}"
                if class_series != TEXT_ND
                else benchmark
            )
            key = (
                fold_text(class_series),
                fold_text(benchmark),
                source.source_id,
                _page_for_offset(source, match.start()),
            )
            if key in seen:
                continue
            seen.add(key)
            results.append(
                Evidence(
                    cnpj=source.cnpj,
                    field="remuneracao_alvo",
                    value=value,
                    source_kind=source.source_kind,
                    source_id=source.source_id,
                    document_class=source.document_class,
                    document_date=source.document_date,
                    source_path=source.source_path,
                    source_url=source.source_url,
                    page=_page_for_offset(source, match.start()),
                    status="encontrado_explicito",
                    confidence=0.97 if class_series != TEXT_ND else 0.90,
                    excerpt=compact_text(
                        text[
                            max(0, match.start() - 260) : min(
                                len(text), match.end() + 260
                            )
                        ]
                    ),
                    nature=(
                        f"rentabilidade-alvo documentada · {class_series}"
                        if class_series != TEXT_ND
                        else "rentabilidade-alvo documentada · classe/série N/D*"
                    ),
                )
            )
    return results


def extract_document_evidence(
    source: DocumentSource,
) -> tuple[list[Evidence], list[PriceEvidence]]:
    evidence: list[Evidence] = []
    evidence.extend(
        _explicit_definition_matches(
            source, field="originador", terms=("Originador", "Originadores")
        )
    )
    evidence.extend(
        _explicit_party_label_matches(
            source,
            field="originador",
            terms=("Originador", "Originadora", "Originadores", "Originadoras"),
        )
    )
    evidence.extend(
        _explicit_definition_matches(
            source, field="cedente", terms=("Cedente", "Cedentes")
        )
    )
    evidence.extend(
        _explicit_party_label_matches(
            source, field="cedente", terms=("Cedente", "Cedentes")
        )
    )
    evidence.extend(
        _explicit_definition_matches(
            source,
            field="sacado_devedor",
            terms=("Sacado", "Sacados", "Devedor", "Devedores"),
        )
    )
    evidence.extend(
        _explicit_party_label_matches(
            source,
            field="sacado_devedor",
            terms=("Sacado", "Sacados", "Devedor", "Devedores"),
        )
    )
    evidence.extend(_receivable_matches(source))
    evidence.extend(_minimum_matches(source))
    evidence.extend(_remuneration_matches(source))
    return deduplicate_evidence(evidence), _price_matches(source)


def payload_evidence(rows: pd.DataFrame) -> list[Evidence]:
    """Convert accepted revision fields to evidence without changing them."""

    evidence: list[Evidence] = []
    field_mapping = {
        "originador": "originador",
        "cedente": "cedente",
        "sacado_devedor": "sacado_devedor",
        "tipo_recebivel_literal": "tipo_recebivel",
    }
    for _, row in rows.iterrows():
        cnpj = normalize_cnpj(row.get("cnpj"))
        manual = fold_text(row.get("status_complemento_manual")) not in {
            "",
            "sem overlay",
            "sem_overlay",
            "n d",
        }
        source_kind = "planilha_manual" if manual else "payload_documental"
        source = (
            row.get("fonte_partes_recebivel")
            or row.get("fonte_documental")
            or source_kind
        )
        for source_column, field in field_mapping.items():
            value = row.get(source_column)
            if is_missing(value):
                continue
            evidence.append(
                Evidence(
                    cnpj=cnpj,
                    field=field,
                    value=compact_text(value, limit=1000),
                    source_kind=source_kind,
                    source_id=compact_text(source, limit=500),
                    document_class="payload",
                    document_date=compact_text(row.get("documento_data"), limit=50),
                    source_path="data/industry_study/generated_revision/artifact_payload.json",
                    source_url="",
                    page=compact_text(row.get("pagina_clausula"), limit=80),
                    status="aceito_payload",
                    confidence=1.0,
                    excerpt=compact_text(
                        row.get("observacao_complemento_manual")
                        or row.get("texto_minimo"),
                        limit=1000,
                    ),
                )
            )

        junior_values = (
            ("minimo_junior_literal", "junior_pl"),
            ("minimo_junior_calculado", "junior_pl_calculado"),
            ("minimo_junior_ajustado", "junior_pl_ajustado"),
        )
        for column, nature in junior_values:
            value = row.get(column)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            evidence.append(
                Evidence(
                    cnpj=cnpj,
                    field="minimo_junior",
                    value=_fraction_display(value),
                    source_kind="payload_documental",
                    source_id=compact_text(row.get("documento_id"), limit=100),
                    document_class="documento_curado",
                    document_date=compact_text(row.get("documento_data"), limit=50),
                    source_path="data/industry_study/generated_revision/artifact_payload.json",
                    source_url=fundonet_download_url(row.get("documento_id")),
                    page=compact_text(row.get("pagina_clausula"), limit=80),
                    status="aceito_payload",
                    confidence=1.0,
                    excerpt=compact_text(row.get("texto_minimo"), limit=1000),
                    nature=nature,
                )
            )
        for column, nature in (
            ("suporte_total", "suporte_total_pl"),
            ("suporte_combinado_junior_mezanino", "suporte_combinado_pl"),
        ):
            value = row.get(column)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            evidence.append(
                Evidence(
                    cnpj=cnpj,
                    field="minimo_estrutural_total",
                    value=_fraction_display(value),
                    source_kind="payload_documental",
                    source_id=compact_text(row.get("documento_id"), limit=100),
                    document_class="documento_curado",
                    document_date=compact_text(row.get("documento_data"), limit=50),
                    source_path="data/industry_study/generated_revision/artifact_payload.json",
                    source_url=fundonet_download_url(row.get("documento_id")),
                    page=compact_text(row.get("pagina_clausula"), limit=80),
                    status="aceito_payload",
                    confidence=1.0,
                    excerpt=compact_text(row.get("texto_minimo"), limit=1000),
                    nature=nature,
                )
            )
        nature = row.get("minimo_estrutural_natureza")
        if not is_missing(nature):
            evidence.append(
                Evidence(
                    cnpj=cnpj,
                    field="natureza_indice",
                    value=compact_text(nature, limit=120),
                    source_kind="payload_documental",
                    source_id=compact_text(row.get("documento_id"), limit=100),
                    document_class="documento_curado",
                    document_date=compact_text(row.get("documento_data"), limit=50),
                    source_path="data/industry_study/generated_revision/artifact_payload.json",
                    source_url=fundonet_download_url(row.get("documento_id")),
                    page=compact_text(row.get("pagina_clausula"), limit=80),
                    status="aceito_payload",
                    confidence=1.0,
                    excerpt=compact_text(row.get("texto_minimo"), limit=1000),
                    nature=compact_text(nature, limit=120),
                )
            )
    return deduplicate_evidence(evidence)


def _fraction_display(value: object) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return TEXT_ND
    return f"{float(number) * 100:g}%"


def deduplicate_evidence(evidence: Iterable[Evidence]) -> list[Evidence]:
    rows: dict[tuple[str, ...], Evidence] = {}
    for item in evidence:
        key = (
            item.cnpj,
            item.field,
            fold_text(item.value),
            item.source_kind,
            item.source_id,
            item.page,
        )
        previous = rows.get(key)
        if previous is None or item.confidence > previous.confidence:
            rows[key] = item
    return sorted(
        rows.values(),
        key=lambda item: (
            item.cnpj,
            item.field,
            source_priority(item.source_kind),
            -item.confidence,
            item.document_date,
            item.source_id,
        ),
    )


def choose_field(evidence: Iterable[Evidence], field: str) -> Evidence | None:
    eligible = [
        item
        for item in evidence
        if item.field == field and item.status in _EXPLICIT_STATUS and not is_missing(item.value)
    ]
    if not eligible:
        return None
    # The payload structural fields have already passed the flagship documentary
    # curation.  A fresh automatic extraction may fill a gap, but it must not
    # replace an accepted minimum with a differently scoped percentage from the
    # same document (for example, a concentration limit or a mezzanine trigger).
    if field in _CURATED_STRUCTURAL_FIELDS:
        accepted = [item for item in eligible if item.status == "aceito_payload"]
        if accepted:
            eligible = accepted
    return min(
        eligible,
        key=lambda item: (
            source_priority(item.source_kind),
            -item.confidence,
            _reverse_date_key(item.document_date),
            item.source_id,
        ),
    )


def _reverse_date_key(value: str) -> int:
    digits = re.sub(r"\D", "", str(value or ""))[:8]
    try:
        return -int(digits or 0)
    except ValueError:
        return 0


def build_audit_table(
    portfolio_rows: pd.DataFrame,
    evidence: Iterable[Evidence],
    *,
    scan_status: Mapping[str, Mapping[str, object]] | None = None,
) -> pd.DataFrame:
    all_evidence = deduplicate_evidence(evidence)
    by_cnpj: dict[str, list[Evidence]] = {}
    for item in all_evidence:
        by_cnpj.setdefault(item.cnpj, []).append(item)

    output: list[dict[str, object]] = []
    for _, source in portfolio_rows.sort_values("ordem", kind="stable").iterrows():
        cnpj = normalize_cnpj(source.get("cnpj"))
        items = by_cnpj.get(cnpj, [])
        row: dict[str, object] = {
            "ordem": source.get("ordem"),
            "cnpj": cnpj,
            "nome_fundo": source.get("nome_oficial_cvm") or source.get("nome_referencia"),
            "status_scan": (scan_status or {}).get(cnpj, {}).get("status", "não executado"),
            "fontes_consultadas": int(
                (scan_status or {}).get(cnpj, {}).get("sources_consulted", 0) or 0
            ),
            "status_online": (scan_status or {}).get(cnpj, {}).get("online_status", "não consultado"),
            "erros_scan": "; ".join(
                str(value)
                for value in ((scan_status or {}).get(cnpj, {}).get("errors") or [])
            ),
        }
        for field in AUDITED_FIELDS:
            selected = choose_field(items, field)
            row[field] = selected.value if selected else TEXT_ND
            row[f"{field}_status"] = selected.status if selected else "não encontrado"
            row[f"{field}_natureza"] = selected.nature if selected else ""
            row[f"{field}_fonte"] = selected.source_id if selected else TEXT_ND
            row[f"{field}_data"] = selected.document_date if selected else TEXT_ND
            row[f"{field}_pagina"] = selected.page if selected else TEXT_ND
            row[f"{field}_link"] = selected.source_url if selected else TEXT_ND
            row[f"{field}_camada"] = selected.source_kind if selected else TEXT_ND
        output.append(row)
    return pd.DataFrame(output)


def coverage_table(
    before_evidence: Iterable[Evidence],
    after_evidence: Iterable[Evidence],
    cnpjs: Sequence[str],
) -> pd.DataFrame:
    before = deduplicate_evidence(before_evidence)
    after = deduplicate_evidence(after_evidence)
    rows: list[dict[str, object]] = []
    denominator = len(cnpjs)
    for field in AUDITED_FIELDS:
        before_count = sum(
            choose_field([item for item in before if item.cnpj == cnpj], field)
            is not None
            for cnpj in cnpjs
        )
        after_count = sum(
            choose_field([item for item in after if item.cnpj == cnpj], field)
            is not None
            for cnpj in cnpjs
        )
        rows.append(
            {
                "campo": field,
                "linhas_total": denominator,
                "antes_com_dado": before_count,
                "antes_cobertura_pct": before_count / denominator if denominator else 0.0,
                "depois_com_dado": after_count,
                "depois_cobertura_pct": after_count / denominator if denominator else 0.0,
                "ganho_linhas": after_count - before_count,
            }
        )
    return pd.DataFrame(rows)


def price_rows_from_sqlite(frame: pd.DataFrame, cnpjs: set[str]) -> list[PriceEvidence]:
    """Read VNU/price only; remuneration and quantity are intentionally ignored."""

    if frame.empty:
        return []
    rows: list[PriceEvidence] = []
    for _, row in frame.iterrows():
        cnpj = normalize_cnpj(row.get("cnpj") or row.get("cnpj_2"))
        if cnpj not in cnpjs:
            continue
        price = compact_text(row.get("vnu"), limit=120)
        if is_missing(price) or not re.search(r"\d", price):
            continue
        source_id = compact_text(row.get("fonte"), limit=500)
        document_id_match = re.search(r"\bID\s+(\d+)", source_id, re.I)
        document_id = document_id_match.group(1) if document_id_match else source_id
        date = compact_text(
            row.get("data_deliberacao") or row.get("data_delibera_o"), limit=50
        )
        rows.append(
            PriceEvidence(
                cnpj=cnpj,
                class_series=compact_text(
                    row.get("cota_classe") or row.get("tipo_cota_normalizado"), limit=180
                )
                or TEXT_ND,
                price_display=price,
                source_kind="payload_documental",
                source_id=document_id,
                document_class="emissao",
                document_date=date,
                source_path=(
                    "data/fidc_credit_strategy/fidc_credit_strategy.sqlite"
                    "::pricing_tranche_enriched"
                ),
                source_url=fundonet_download_url(document_id),
                page="",
                status="aceito_payload",
                excerpt=source_id,
                price_nature="Valor nominal unitário (VNU)",
                exception_flag=(
                    "*"
                    if is_missing(row.get("cota_classe") or row.get("tipo_cota_normalizado"))
                    else ""
                ),
                exception_reason=(
                    "classe/série não identificada no registro"
                    if is_missing(row.get("cota_classe") or row.get("tipo_cota_normalizado"))
                    else ""
                ),
            )
        )
    return deduplicate_prices(rows)


def deduplicate_prices(prices: Iterable[PriceEvidence]) -> list[PriceEvidence]:
    output: dict[tuple[str, ...], PriceEvidence] = {}
    for item in prices:
        key = (
            item.cnpj,
            fold_text(item.class_series),
            _brl_amount_key(item.price_display),
            fold_text(item.price_nature),
        )
        previous = output.get(key)
        if previous is None or (
            source_priority(item.source_kind),
            _reverse_date_key(item.document_date),
            item.source_id,
        ) < (
            source_priority(previous.source_kind),
            _reverse_date_key(previous.document_date),
            previous.source_id,
        ):
            output[key] = item
    return sorted(
        output.values(),
        key=lambda item: (
            item.cnpj,
            source_priority(item.source_kind),
            item.document_date,
            item.class_series,
            item.price_display,
        ),
    )


def _brl_amount_key(value: str) -> str:
    text = re.sub(r"[^0-9,.-]", "", str(value or ""))
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return format(Decimal(text), "f")
    except InvalidOperation:
        return fold_text(value)


def evidence_frame(evidence: Iterable[Evidence]) -> pd.DataFrame:
    return pd.DataFrame([asdict(item) for item in deduplicate_evidence(evidence)])


def price_frame(prices: Iterable[PriceEvidence]) -> pd.DataFrame:
    return pd.DataFrame([asdict(item) for item in deduplicate_prices(prices)])


def read_checkpoint(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, object]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        cnpj = normalize_cnpj(row.get("cnpj"))
        if cnpj:
            rows[cnpj] = row
    return rows


def write_checkpoint(path: Path, rows: Mapping[str, Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    payload = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True)
        for _, row in sorted(rows.items())
    )
    temp.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
    temp.replace(path)


def evidence_from_checkpoint(
    rows: Mapping[str, Mapping[str, object]],
) -> tuple[list[Evidence], list[PriceEvidence]]:
    evidence: list[Evidence] = []
    prices: list[PriceEvidence] = []
    for row in rows.values():
        for item in row.get("evidence") or []:
            try:
                evidence.append(Evidence(**item))
            except TypeError:
                continue
        for item in row.get("prices") or []:
            try:
                prices.append(PriceEvidence(**item))
            except TypeError:
                continue
    return deduplicate_evidence(evidence), deduplicate_prices(prices)


def serialize_evidence(items: Iterable[Evidence]) -> list[dict[str, object]]:
    return [asdict(item) for item in deduplicate_evidence(items)]


def serialize_prices(items: Iterable[PriceEvidence]) -> list[dict[str, object]]:
    return [asdict(item) for item in deduplicate_prices(items)]
