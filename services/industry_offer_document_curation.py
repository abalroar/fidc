"""Document and participant curation for the largest closed FIDC offerings."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import unicodedata

import pandas as pd
import pdfplumber
import requests


OUTPUT_FILENAME = "industry_offer_document_curation.csv"
SRE_BASE = "https://web.cvm.gov.br/sre-publico-cvm"
PARTICIPANTS_URL = (
    SRE_BASE + "/rest/sitePublico/pesquisar/participantes/{offer_id}"
)
DOCUMENTS_URL = (
    SRE_BASE + "/rest/sitePublico/pesquisar/documentosPublicados/{offer_id}"
)
DOWNLOAD_URL = SRE_BASE + "/rest/download/{document_uuid}"
TOP_PERIODS = ("2025 FY", "2026 jan-jun")
ITAU_CNPJS = {
    "04845753000159",  # Itaú BBA Assessoria Financeira
    "60701190000104",  # Itaú Unibanco
}
ITAU_PATTERN = re.compile(
    r"\b(?:ITAU\s*BBA|ITAU\s+UNIBANCO|ITAUBBA)\b",
    flags=re.IGNORECASE,
)
PARTICIPANT_ROLES = {"COORDENADOR", "REQUERENTE"}
OUTPUT_COLUMNS = (
    "offer_id",
    "period_label",
    "rank",
    "issuer_name",
    "originator_group_curated",
    "originator_confidence",
    "originator_evidence",
    "ibba_participant",
    "ibba_participant_label",
    "ibba_participant_entities",
    "ibba_participant_roles",
    "ibba_participation_source",
    "participants_source_url",
    "closing_document_name",
    "closing_document_date",
    "closing_document_url",
    "closing_document_uuid",
    "document_text_method",
    "document_text_characters",
    "document_itau_mention",
    "review_status",
)


class OfferDocumentCurationError(ValueError):
    """Raised when official offer-document evidence cannot be reconciled."""


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    return " ".join(text.upper().split())


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _is_itau_participant(row: dict[str, object]) -> bool:
    cnpj = _digits(row.get("cnpjInstituicao"))
    name = _normalize(row.get("razaoSocial"))
    role = _normalize(row.get("tipo"))
    return (
        role in PARTICIPANT_ROLES
        and (cnpj in ITAU_CNPJS or bool(ITAU_PATTERN.search(name)))
    )


def _select_closing_document(
    documents: list[dict[str, object]],
) -> dict[str, object] | None:
    candidates = [
        row
        for row in documents
        if "ENCERRAMENTO" in _normalize(row.get("nome"))
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda row: (
            pd.to_datetime(row.get("data"), dayfirst=True, errors="coerce"),
            str(row.get("hora") or ""),
        ),
    )[-1]


def _extract_pdf_text(content: bytes) -> tuple[str, str]:
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            ).strip()
    except Exception:
        return "", "falha de leitura"
    return text, "texto PDF" if text else "imagem sem OCR disponível"


def _originator_curation(
    offer_id: str,
    issuer_name: str,
    existing_originator: str,
) -> tuple[str, str, str]:
    """Return document-safe labels; uncertain originators remain explicit."""

    curated: dict[str, tuple[str, str, str]] = {
        "24212": (
            "Não identificado · carteira multicedente",
            "baixa",
            "JiveMauá Bossa Nova II: documentos consultados descrevem carteira "
            "discricionária/diversificada sem um cedente único nominável.",
        ),
        "24371": (
            "Fornecedores de BRF e Marfrig",
            "alta",
            "Comerciais Medici I: direitos creditórios comerciais cedidos por "
            "fornecedores; BRF e Marfrig são devedores/âncoras, não originadores.",
        ),
        "26532": (
            "Não identificado · Cartão Benefício e Cartão BMG",
            "média",
            "Daycoval D413: a base oficial descreve o lastro, mas o anúncio de "
            "encerramento não individualiza o cedente/originador.",
        ),
        "19640": (
            "Não identificado · recebíveis de energia",
            "baixa",
            "ER - Energia: documentos consultados não nomeiam um único cedente "
            "ou originador; a carteira está ligada a recebíveis de energia/CCEE.",
        ),
        "21258": (
            "Não aplicável · FIC-FIDC alocador",
            "alta",
            "ASA LP II: a oferta é de veículo alocador em cotas de FIDC; não há "
            "um originador único dos recebíveis subjacentes.",
        ),
        "17862": (
            "Carteira agro multicedente",
            "média",
            "Agro Flex: carteira de instrumentos de crédito do agronegócio; "
            "documentos da oferta não individualizam um originador único.",
        ),
        "18230": (
            "Carteira agro multicedente",
            "média",
            "Agro Flex: carteira de instrumentos de crédito do agronegócio; "
            "documentos da oferta não individualizam um originador único.",
        ),
        "20365": (
            "Carteira agro multicedente",
            "média",
            "Agro Flex: carteira de instrumentos de crédito do agronegócio; "
            "documentos da oferta não individualizam um originador único.",
        ),
        "19298": (
            "Banco Volkswagen / Volkswagen Financial Services",
            "média",
            "Volkswagen Tera: recebíveis de financiamento e cadeia de veículos "
            "do grupo Volkswagen; vínculo nominal requer leitura conjunta da oferta.",
        ),
        "21006": (
            "Não identificado · crédito consignado",
            "baixa",
            "Byx Mozart Consignado: documentos consultados descrevem o lastro, "
            "mas não identificam um cedente/originador único.",
        ),
    }
    if offer_id in curated:
        return curated[offer_id]
    current = str(existing_originator or "").strip()
    if current and current not in {"N/D", "Não identificado"}:
        return (
            current,
            "média",
            "Classificação nominal preexistente; não revisada nesta rodada documental.",
        )
    return (
        "Não identificado",
        "baixa",
        f"{issuer_name}: originador não identificado na evidência consultada.",
    )


def build_offer_document_curation(
    cohort: pd.DataFrame,
    offers: pd.DataFrame,
    *,
    top_n: int = 15,
    session: requests.Session | None = None,
    timeout: int = 60,
) -> pd.DataFrame:
    """Query the official SRE endpoints for the current Top 15 in each period."""

    required_cohort = {
        "numero_requerimento",
        "period_label",
        "nome_emissor",
        "registered_volume_brl",
    }
    missing = sorted(required_cohort.difference(cohort.columns))
    if missing:
        raise OfferDocumentCurationError(
            "Coorte sem colunas: " + ", ".join(missing)
        )
    offers = offers.copy()
    if "offer_id" not in offers:
        raise OfferDocumentCurationError("Metadados sem offer_id.")
    offers["offer_id"] = offers["offer_id"].astype(str).str.strip()
    originators = (
        offers.set_index("offer_id")["originator_group"].to_dict()
        if "originator_group" in offers
        else {}
    )
    selected_parts: list[pd.DataFrame] = []
    for period_label in TOP_PERIODS:
        period = cohort[cohort["period_label"].eq(period_label)].copy()
        period["registered_volume_brl"] = pd.to_numeric(
            period["registered_volume_brl"], errors="coerce"
        )
        period = period.sort_values(
            ["registered_volume_brl", "numero_requerimento"],
            ascending=[False, True],
        ).head(top_n)
        if len(period) != top_n:
            raise OfferDocumentCurationError(
                f"{period_label} possui apenas {len(period)} ofertas."
            )
        period["rank"] = range(1, top_n + 1)
        selected_parts.append(period)
    selected = pd.concat(selected_parts, ignore_index=True)

    client = session or requests.Session()
    rows: list[dict[str, object]] = []
    for item in selected.itertuples(index=False):
        offer_id = str(item.numero_requerimento).strip()
        if not offer_id.isdigit():
            raise OfferDocumentCurationError(
                f"Top 15 contém oferta legada sem endpoint SRE: {offer_id}"
            )
        participants_url = PARTICIPANTS_URL.format(offer_id=offer_id)
        participant_response = client.get(participants_url, timeout=timeout)
        participant_response.raise_for_status()
        participants = participant_response.json()
        if not isinstance(participants, list):
            raise OfferDocumentCurationError(
                f"{offer_id}: participantes inválidos."
            )
        itau_rows = [row for row in participants if _is_itau_participant(row)]

        documents_url = DOCUMENTS_URL.format(offer_id=offer_id)
        documents_response = client.get(documents_url, timeout=timeout)
        documents_response.raise_for_status()
        documents = documents_response.json()
        if not isinstance(documents, list):
            raise OfferDocumentCurationError(
                f"{offer_id}: documentos inválidos."
            )
        closing = _select_closing_document(documents)
        document_text = ""
        document_method = "anúncio de encerramento ausente"
        document_url = ""
        document_uuid = ""
        if closing:
            document_uuid = (
                str(closing.get("valor") or "").split(",", 1)[0].strip()
            )
            document_url = DOWNLOAD_URL.format(document_uuid=document_uuid)
            content_response = client.get(document_url, timeout=timeout)
            content_response.raise_for_status()
            document_text, document_method = _extract_pdf_text(
                content_response.content
            )
        document_itau = bool(ITAU_PATTERN.search(_normalize(document_text)))
        ibba_participant = bool(itau_rows)
        source = (
            "participantes oficiais SRE"
            if ibba_participant
            else "participantes oficiais SRE; anúncio conferido"
        )
        originator, confidence, evidence = _originator_curation(
            offer_id,
            str(item.nome_emissor),
            str(originators.get(offer_id) or ""),
        )
        rows.append(
            {
                "offer_id": offer_id,
                "period_label": str(item.period_label),
                "rank": int(item.rank),
                "issuer_name": str(item.nome_emissor),
                "originator_group_curated": originator,
                "originator_confidence": confidence,
                "originator_evidence": evidence,
                "ibba_participant": ibba_participant,
                "ibba_participant_label": "Sim" if ibba_participant else "Não",
                "ibba_participant_entities": " | ".join(
                    dict.fromkeys(
                        str(row.get("razaoSocial") or "").strip()
                        for row in itau_rows
                    )
                ),
                "ibba_participant_roles": " | ".join(
                    dict.fromkeys(
                        str(row.get("tipo") or "").strip() for row in itau_rows
                    )
                ),
                "ibba_participation_source": source,
                "participants_source_url": participants_url,
                "closing_document_name": (
                    str(closing.get("nome") or "") if closing else ""
                ),
                "closing_document_date": (
                    str(closing.get("data") or "") if closing else ""
                ),
                "closing_document_url": document_url,
                "closing_document_uuid": document_uuid,
                "document_text_method": document_method,
                "document_text_characters": len(document_text),
                "document_itau_mention": document_itau,
                "review_status": (
                    "revisado"
                    if document_text or not closing
                    else "requer OCR manual"
                ),
            }
        )
    return validate_offer_document_curation(pd.DataFrame(rows))


def validate_offer_document_curation(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(OUTPUT_COLUMNS).difference(frame.columns))
    if missing:
        raise OfferDocumentCurationError(
            "Curadoria sem colunas: " + ", ".join(missing)
        )
    result = frame.loc[:, OUTPUT_COLUMNS].copy()
    if len(result) != 30:
        raise OfferDocumentCurationError(
            f"Curadoria deveria conter 30 ofertas; contém {len(result)}."
        )
    if result["offer_id"].duplicated().any():
        raise OfferDocumentCurationError("Oferta duplicada na curadoria.")
    for period in TOP_PERIODS:
        ranks = result.loc[result["period_label"].eq(period), "rank"].tolist()
        if ranks != list(range(1, 16)):
            raise OfferDocumentCurationError(
                f"Ranking incompleto em {period}."
            )
    return result.sort_values(["period_label", "rank"]).reset_index(drop=True)


def write_offer_document_curation(
    frame: pd.DataFrame,
    data_dir: str | Path,
) -> Path:
    output = validate_offer_document_curation(frame)
    path = Path(data_dir) / OUTPUT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)
    return path


def load_offer_document_curation(data_dir: str | Path) -> pd.DataFrame:
    path = Path(data_dir) / OUTPUT_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Curadoria documental ausente: {path}")
    return validate_offer_document_curation(pd.read_csv(path))


__all__ = [
    "OUTPUT_FILENAME",
    "OfferDocumentCurationError",
    "build_offer_document_curation",
    "load_offer_document_curation",
    "validate_offer_document_curation",
    "write_offer_document_curation",
]
