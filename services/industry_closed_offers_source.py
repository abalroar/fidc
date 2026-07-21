"""Materialize the closed-offer tables from the official CVM archive.

The published offer universe is deliberately frozen at 30 June 2026.  The
archive can contain later closings; those rows remain outside this release so
the three-year comparison uses six complete months in every year.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import unicodedata
from typing import Any
from zipfile import ZipFile

import pandas as pd

from services.industry_closed_offers import (
    ANNUAL_COLUMNS,
    ANNUAL_FILENAME,
    MONTHLY_COLUMNS,
    MONTHLY_FILENAME,
    ORIGINATOR_COLUMNS,
    ORIGINATORS_FILENAME,
    ClosedOffersTables,
    validate_closed_offer_originators,
    validate_closed_offers_annual,
    validate_closed_offers_monthly,
)


SOURCE_DATASET = "oferta_resolucao_160.csv"
SOURCE_URL = (
    "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/"
    "oferta_distribuicao.zip"
)
SOURCE_AS_OF_DATE = "2026-07-21"
SOURCE_ARCHIVE_SHA256 = (
    "ff53d4406953411a3153a2701669c6d06ebad56f5d849c7e0190406ac7bfa0f3"
)
RELEASE_CUTOFF = "2026-06-30"

SCOPE = (
    "Cotas de FIDC | oferta primária | Oferta Encerrada | "
    "Data_Encerramento até 30/06/2026 | Valor_Total_Registrado positivo"
)
METHODOLOGY = (
    "Uma oferta = Numero_Requerimento; coorte por Data_Encerramento; "
    "registered_volume_brl = Valor_Total_Registrado; "
    "placed_volume_proxy_brl = min(sum(Qtde_VM_*) * "
    "Valor_Total_Registrado / Qtde_Total_Registrada, Valor_Total_Registrado)."
)
ORIGINATOR_METHODOLOGY = (
    METHODOLOGY
    + " Origem = primeiro match nominal auditável, pela prioridade da regra, "
    "em Nome_Emissor ou Ativos_alvo; o residual permanece não identificado."
)

REQUIRED_COLUMNS = (
    "Numero_Requerimento",
    "Data_Encerramento",
    "Status_Requerimento",
    "Valor_Mobiliario",
    "Tipo_Oferta",
    "CNPJ_Emissor",
    "Nome_Emissor",
    "Qtde_Total_Registrada",
    "Valor_Total_Registrado",
    "Publico_alvo",
    "Ativos_alvo",
    "Descricao_lastro",
    "Identificacao_devedores_coobrigados",
    "Num_Invest_Pessoa_Natural",
    "Qtde_VM_Pessoa_Natural",
)

# Priority is meaningful: an offer is assigned to the first rule that matches.
ORIGINATOR_RULES: tuple[dict[str, Any], ...] = (
    {"group": "CloudWalk", "fields": ("Nome_Emissor",), "patterns": (r"\bCLOUDWALK\b",)},
    {"group": "Agibank", "fields": ("Nome_Emissor",), "patterns": (r"\bAGIBANK\b",)},
    {"group": "Banco Volkswagen", "fields": ("Nome_Emissor",), "patterns": (r"\bBANCO\s+VOLKSWAGEN\b",)},
    {"group": "Solfácil", "fields": ("Nome_Emissor",), "patterns": (r"\bSOL\s+AGORA\b", r"\bSOLFACIL\b")},
    {"group": "Mercado Pago / Mercado Crédito", "fields": ("Ativos_alvo",), "patterns": (r"\bMERCADO\s+(?:PAGO|CREDITO)\b",)},
    {"group": "Banco Pine", "fields": ("Nome_Emissor",), "patterns": (r"\bPINE\s+INSS\b",)},
    {"group": "PicPay", "fields": ("Nome_Emissor",), "patterns": (r"\bPICPAY\b",)},
    {"group": "ICred", "fields": ("Nome_Emissor",), "patterns": (r"\bICRED\b",)},
    {"group": "PagSeguro", "fields": ("Nome_Emissor",), "patterns": (r"\bPAGSEGURO\b",)},
    {"group": "Lavoro", "fields": ("Nome_Emissor",), "patterns": (r"\bLAVORO\b",)},
    {"group": "Bayer", "fields": ("Nome_Emissor",), "patterns": (r"\bCITI[ -]?BAYER\b",)},
    {"group": "iFood", "fields": ("Nome_Emissor",), "patterns": (r"\bIFOOD\b",)},
    {"group": "MRV", "fields": ("Nome_Emissor",), "patterns": (r"\bMRV\b",)},
    {"group": "Creditas", "fields": ("Nome_Emissor",), "patterns": (r"\bCREDITAS\b",)},
    {"group": "Verdecard", "fields": ("Nome_Emissor",), "patterns": (r"\bVERDECARD\b",)},
    {"group": "Paraná Banco", "fields": ("Nome_Emissor",), "patterns": (r"\bPARANA\s+BANCO\b",)},
    {"group": "Minerva", "fields": ("Nome_Emissor",), "patterns": (r"\bMINERVA\b",)},
    {"group": "D365", "fields": ("Nome_Emissor",), "patterns": (r"\bD365\b",)},
    {"group": "Pravaler", "fields": ("Nome_Emissor",), "patterns": (r"\bPRAVALER\b",)},
)


class ClosedOffersSourceError(ValueError):
    """Raised when the official source cannot satisfy the release contract."""


def _archive_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(text.upper().split())


def _normalize_cnpj(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.replace(r"\D", "", regex=True)


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _source_metadata(*, source_as_of_date: str, archive_digest: str) -> dict[str, str]:
    return {
        "source_dataset": SOURCE_DATASET,
        "source_url": SOURCE_URL,
        "source_as_of_date": source_as_of_date,
        "source_archive_sha256": archive_digest,
        "latest_source_closing_date": RELEASE_CUTOFF,
        "scope": SCOPE,
        "methodology": METHODOLOGY,
    }


def load_closed_offer_source(
    archive_path: str | Path,
    *,
    source_as_of_date: str = SOURCE_AS_OF_DATE,
    expected_archive_sha256: str | None = SOURCE_ARCHIVE_SHA256,
) -> tuple[pd.DataFrame, str]:
    """Read, scope, deduplicate and enrich the official offer records."""

    path = Path(archive_path)
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo CVM de ofertas ausente: {path}")
    digest = _archive_sha256(path)
    if expected_archive_sha256 and digest != expected_archive_sha256:
        raise ClosedOffersSourceError(
            "SHA-256 do arquivo CVM diverge do snapshot esperado: " + digest
        )

    with ZipFile(path) as archive:
        if SOURCE_DATASET not in archive.namelist():
            raise ClosedOffersSourceError(f"Tabela {SOURCE_DATASET} ausente no arquivo CVM.")
        source = pd.read_csv(
            archive.open(SOURCE_DATASET),
            sep=";",
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
            low_memory=False,
        )
    missing = [column for column in REQUIRED_COLUMNS if column not in source]
    if missing:
        raise ClosedOffersSourceError("Colunas CVM obrigatórias ausentes: " + ", ".join(missing))

    normalized_value_type = source["Valor_Mobiliario"].map(_normalize_text)
    normalized_offer_type = source["Tipo_Oferta"].map(_normalize_text)
    normalized_status = source["Status_Requerimento"].map(_normalize_text)
    selected = source.loc[
        normalized_value_type.eq("COTAS DE FIDC")
        & normalized_offer_type.eq("PRIMARIA")
        & normalized_status.eq("OFERTA ENCERRADA")
    ].copy()
    selected["data_encerramento"] = pd.to_datetime(
        selected["Data_Encerramento"], errors="coerce"
    )
    selected["registered_volume_brl"] = pd.to_numeric(
        selected["Valor_Total_Registrado"], errors="coerce"
    )
    selected = selected.loc[
        selected["data_encerramento"].notna()
        & selected["data_encerramento"].le(RELEASE_CUTOFF)
        & selected["registered_volume_brl"].gt(0)
    ].copy()

    selected["Numero_Requerimento"] = selected["Numero_Requerimento"].str.strip()
    if selected["Numero_Requerimento"].eq("").any():
        raise ClosedOffersSourceError("Numero_Requerimento vazio no universo selecionado.")
    duplicates = selected.duplicated("Numero_Requerimento", keep=False)
    if duplicates.any():
        comparison = [
            "Data_Encerramento",
            "CNPJ_Emissor",
            "Nome_Emissor",
            "Valor_Total_Registrado",
        ]
        conflicting = [
            str(requirement)
            for requirement, group in selected.loc[duplicates].groupby("Numero_Requerimento")
            if len(group[comparison].drop_duplicates()) != 1
        ]
        if conflicting:
            raise ClosedOffersSourceError(
                "Numero_Requerimento com linhas conflitantes: " + ", ".join(conflicting[:5])
            )
        selected = selected.drop_duplicates("Numero_Requerimento", keep="first")

    selected["cnpj_emissor"] = _normalize_cnpj(selected["CNPJ_Emissor"])
    selected["registered_quantity"] = pd.to_numeric(
        selected["Qtde_Total_Registrada"], errors="coerce"
    )
    quantity_columns = [
        column
        for column in selected.columns
        if column.startswith("Qtde_VM_") or column.startswith("Qdte_VM_")
    ]
    investor_columns = [
        column for column in selected.columns if column.startswith("Num_Invest_")
    ]
    selected["placed_quantity"] = selected[quantity_columns].apply(
        pd.to_numeric, errors="coerce"
    ).sum(axis=1, min_count=1)
    selected["investor_accounts"] = selected[investor_columns].apply(
        pd.to_numeric, errors="coerce"
    ).sum(axis=1, min_count=1)
    selected["natural_person_accounts"] = pd.to_numeric(
        selected["Num_Invest_Pessoa_Natural"], errors="coerce"
    ).fillna(0)
    selected["natural_person_quantity"] = pd.to_numeric(
        selected["Qtde_VM_Pessoa_Natural"], errors="coerce"
    ).fillna(0)
    unit_price = selected["registered_volume_brl"].div(
        selected["registered_quantity"].where(selected["registered_quantity"].gt(0))
    )
    selected["placed_volume_proxy_brl"] = (
        selected["placed_quantity"] * unit_price
    ).clip(upper=selected["registered_volume_brl"])
    selected["natural_person_placed_volume_proxy_brl"] = (
        selected["natural_person_quantity"] * unit_price
    ).clip(upper=selected["registered_volume_brl"]).fillna(0)
    selected["publico_alvo_norm"] = selected["Publico_alvo"].map(_normalize_text)
    unexpected_targets = set(selected["publico_alvo_norm"]) - {
        "PROFISSIONAL",
        "QUALIFICADO",
        "PUBLICO GERAL",
    }
    if unexpected_targets:
        raise ClosedOffersSourceError(
            "Público-alvo fora do contrato: " + ", ".join(sorted(unexpected_targets))
        )
    for field in ("Nome_Emissor", "Ativos_alvo"):
        selected[f"{field}_norm"] = selected[field].map(_normalize_text)
    selected.attrs["source_as_of_date"] = source_as_of_date
    return selected.sort_values(["data_encerramento", "Numero_Requerimento"]), digest


def _offer_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        raise ClosedOffersSourceError("O período agregado não contém ofertas.")
    offers = int(len(frame))
    registered_volume = float(frame["registered_volume_brl"].sum())
    registered_covered = frame["registered_quantity"].gt(0)
    placed_covered = frame["placed_volume_proxy_brl"].gt(0)
    investor_covered = frame["investor_accounts"].gt(0)
    up_to_five = investor_covered & frame["investor_accounts"].le(5)
    natural_person = investor_covered & frame["natural_person_accounts"].gt(0)

    placed = frame.loc[placed_covered, "placed_volume_proxy_brl"]
    placed_volume = float(placed.sum())
    placed_registered_volume = float(frame.loc[placed_covered, "registered_volume_brl"].sum())
    investor_registered_volume = float(frame.loc[investor_covered, "registered_volume_brl"].sum())
    target_volume = {
        target: float(frame.loc[frame["publico_alvo_norm"].eq(target), "registered_volume_brl"].sum())
        for target in ("PROFISSIONAL", "QUALIFICADO", "PUBLICO GERAL")
    }
    natural_person_volume = float(
        frame.loc[placed_covered, "natural_person_placed_volume_proxy_brl"].sum()
    )
    return {
        "closed_offers": offers,
        "issuer_cnpjs": int(frame.loc[frame["cnpj_emissor"].ne(""), "cnpj_emissor"].nunique()),
        "registered_volume_brl": registered_volume,
        "mean_registered_ticket_brl": _safe_ratio(registered_volume, offers),
        "median_registered_ticket_brl": float(frame["registered_volume_brl"].median()),
        "offers_with_registered_quantity": int(registered_covered.sum()),
        "registered_quantity_offer_coverage": _safe_ratio(int(registered_covered.sum()), offers),
        "registered_quantity_volume_coverage": _safe_ratio(
            float(frame.loc[registered_covered, "registered_volume_brl"].sum()), registered_volume
        ),
        "offers_with_placed_quantity": int(placed_covered.sum()),
        "placed_quantity_offer_coverage": _safe_ratio(int(placed_covered.sum()), offers),
        "placed_quantity_registered_volume_coverage": _safe_ratio(
            placed_registered_volume, registered_volume
        ),
        "placed_volume_proxy_brl": placed_volume,
        "mean_placed_ticket_brl": _safe_ratio(placed_volume, int(placed_covered.sum())),
        "median_placed_ticket_brl": float(placed.median()),
        "placed_proxy_share_of_registered_covered": _safe_ratio(
            placed_volume, placed_registered_volume
        ),
        "offers_with_investor_count_data": int(investor_covered.sum()),
        "investor_count_offer_coverage": _safe_ratio(int(investor_covered.sum()), offers),
        "investor_count_registered_volume_coverage": _safe_ratio(
            investor_registered_volume, registered_volume
        ),
        "median_investor_accounts": float(frame.loc[investor_covered, "investor_accounts"].median()),
        "offers_with_up_to_5_investors": int(up_to_five.sum()),
        "up_to_5_investors_offer_share_covered": _safe_ratio(
            int(up_to_five.sum()), int(investor_covered.sum())
        ),
        "up_to_5_investors_registered_volume_share_covered": _safe_ratio(
            float(frame.loc[up_to_five, "registered_volume_brl"].sum()), investor_registered_volume
        ),
        "professional_target_registered_volume_brl": target_volume["PROFISSIONAL"],
        "professional_target_registered_volume_share": _safe_ratio(
            target_volume["PROFISSIONAL"], registered_volume
        ),
        "qualified_target_registered_volume_brl": target_volume["QUALIFICADO"],
        "qualified_target_registered_volume_share": _safe_ratio(
            target_volume["QUALIFICADO"], registered_volume
        ),
        "general_target_registered_volume_brl": target_volume["PUBLICO GERAL"],
        "general_target_registered_volume_share": _safe_ratio(
            target_volume["PUBLICO GERAL"], registered_volume
        ),
        "natural_person_accounts": int(frame.loc[investor_covered, "natural_person_accounts"].sum()),
        "offers_with_natural_person": int(natural_person.sum()),
        "natural_person_offer_presence_share_covered": _safe_ratio(
            int(natural_person.sum()), int(investor_covered.sum())
        ),
        "natural_person_placed_volume_proxy_brl": natural_person_volume,
        "natural_person_placed_volume_share": _safe_ratio(natural_person_volume, placed_volume),
    }


def build_closed_offer_annual(
    source: pd.DataFrame, *, source_as_of_date: str, archive_digest: str
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    metadata = _source_metadata(
        source_as_of_date=source_as_of_date, archive_digest=archive_digest
    )
    for year in (2023, 2024, 2025, 2026):
        end = f"{year}-12-31" if year < 2026 else RELEASE_CUTOFF
        period = source.loc[source["data_encerramento"].between(f"{year}-01-01", end)]
        rows.append(
            {
                "year": year,
                "period_label": f"{year} FY" if year < 2026 else "2026 YTD",
                "period_start": f"{year}-01-01",
                "period_end": end,
                "is_full_year": year < 2026,
                **_offer_metrics(period),
                **metadata,
            }
        )
    return validate_closed_offers_annual(pd.DataFrame(rows, columns=ANNUAL_COLUMNS))


def build_closed_offer_monthly(
    source: pd.DataFrame, *, source_as_of_date: str, archive_digest: str
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    metadata = _source_metadata(
        source_as_of_date=source_as_of_date, archive_digest=archive_digest
    )
    source_month = pd.Period(source_as_of_date, freq="M")
    for competence, period in source.groupby(source["data_encerramento"].dt.to_period("M")):
        start = competence.start_time.date().isoformat()
        end = min(competence.end_time.date(), pd.Timestamp(RELEASE_CUTOFF).date()).isoformat()
        rows.append(
            {
                "year": competence.year,
                "month": competence.month,
                "competence": str(competence),
                "period_start": start,
                "period_end": end,
                "is_complete_month": competence < source_month,
                **_offer_metrics(period),
                **metadata,
            }
        )
    return validate_closed_offers_monthly(pd.DataFrame(rows, columns=MONTHLY_COLUMNS))


def build_closed_offer_originators(
    source: pd.DataFrame, *, source_as_of_date: str, archive_digest: str
) -> pd.DataFrame:
    period = source.loc[source["data_encerramento"].between("2026-01-01", RELEASE_CUTOFF)].copy()
    period["originator_group"] = ""
    period["originator_source_fields"] = ""
    period["originator_evidence_sample"] = ""
    period["confidence"] = ""
    for rule in ORIGINATOR_RULES:
        unmatched = period["originator_group"].eq("")
        mask = pd.Series(False, index=period.index)
        evidence_parts: list[str] = []
        for field in rule["fields"]:
            normalized = period[f"{field}_norm"]
            for pattern in rule["patterns"]:
                mask |= normalized.str.contains(pattern, regex=True, na=False)
                evidence_parts.append(f"{field}: {pattern}")
        mask &= unmatched
        period.loc[mask, "originator_group"] = rule["group"]
        period.loc[mask, "originator_source_fields"] = ", ".join(rule["fields"])
        period.loc[mask, "originator_evidence_sample"] = " | ".join(evidence_parts)
        period.loc[mask, "confidence"] = "alta - regra nominal auditável"

    identified = period.loc[period["originator_group"].ne("")].copy()
    universe_volume = float(period["registered_volume_brl"].sum())
    identified_volume = float(identified["registered_volume_brl"].sum())
    metadata = _source_metadata(
        source_as_of_date=source_as_of_date, archive_digest=archive_digest
    )
    rows: list[dict[str, Any]] = []
    for group, group_frame in identified.groupby("originator_group", sort=False):
        placed_covered = group_frame["placed_volume_proxy_brl"].gt(0)
        placed = group_frame.loc[placed_covered, "placed_volume_proxy_brl"]
        registered_volume = float(group_frame["registered_volume_brl"].sum())
        placed_volume = float(placed.sum())
        rows.append(
            {
                "period_label": "2026 jan–jun",
                "period_start": "2026-01-01",
                "period_end": RELEASE_CUTOFF,
                "originator_group": group,
                "closed_offers": int(len(group_frame)),
                "issuer_cnpjs": int(group_frame.loc[group_frame["cnpj_emissor"].ne(""), "cnpj_emissor"].nunique()),
                "registered_volume_brl": registered_volume,
                "mean_registered_ticket_brl": _safe_ratio(registered_volume, len(group_frame)),
                "median_registered_ticket_brl": float(group_frame["registered_volume_brl"].median()),
                "placed_volume_proxy_brl": placed_volume,
                "offers_with_placed_quantity": int(placed_covered.sum()),
                "placed_quantity_offer_coverage": _safe_ratio(int(placed_covered.sum()), len(group_frame)),
                "placed_quantity_registered_volume_coverage": _safe_ratio(
                    float(group_frame.loc[placed_covered, "registered_volume_brl"].sum()),
                    registered_volume,
                ),
                "mean_placed_ticket_brl": _safe_ratio(placed_volume, int(placed_covered.sum())),
                "median_placed_ticket_brl": float(placed.median()),
                "share_of_total_registered_volume": _safe_ratio(registered_volume, universe_volume),
                "share_of_identified_registered_volume": _safe_ratio(registered_volume, identified_volume),
                "originator_source_fields": str(group_frame["originator_source_fields"].iloc[0]),
                "originator_evidence_sample": str(group_frame["originator_evidence_sample"].iloc[0]),
                "confidence": str(group_frame["confidence"].iloc[0]),
                "universe_closed_offers": int(len(period)),
                "universe_registered_volume_brl": universe_volume,
                "identified_registered_volume_brl": identified_volume,
                "unidentified_registered_volume_brl": universe_volume - identified_volume,
                "identified_registered_volume_coverage": _safe_ratio(identified_volume, universe_volume),
                **metadata,
                "originator_methodology": ORIGINATOR_METHODOLOGY,
            }
        )
    result = pd.DataFrame(rows)
    result = result.sort_values(
        ["registered_volume_brl", "originator_group"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    result.insert(0, "rank", range(1, len(result) + 1))
    return validate_closed_offer_originators(result.loc[:, ORIGINATOR_COLUMNS])


def build_closed_offer_tables_from_archive(
    archive_path: str | Path,
    *,
    source_as_of_date: str = SOURCE_AS_OF_DATE,
    expected_archive_sha256: str | None = SOURCE_ARCHIVE_SHA256,
) -> ClosedOffersTables:
    source, digest = load_closed_offer_source(
        archive_path,
        source_as_of_date=source_as_of_date,
        expected_archive_sha256=expected_archive_sha256,
    )
    return ClosedOffersTables(
        annual=build_closed_offer_annual(
            source, source_as_of_date=source_as_of_date, archive_digest=digest
        ),
        monthly=build_closed_offer_monthly(
            source, source_as_of_date=source_as_of_date, archive_digest=digest
        ),
        originators=build_closed_offer_originators(
            source, source_as_of_date=source_as_of_date, archive_digest=digest
        ),
    )


def write_closed_offer_tables(
    tables: ClosedOffersTables, data_dir: str | Path
) -> dict[str, Any]:
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    annual = validate_closed_offers_annual(tables.annual)
    monthly = validate_closed_offers_monthly(tables.monthly)
    originators = validate_closed_offer_originators(tables.originators)
    annual.to_csv(root / ANNUAL_FILENAME, index=False)
    monthly.to_csv(root / MONTHLY_FILENAME, index=False)
    originators.to_csv(root / ORIGINATORS_FILENAME, index=False)
    return {
        "annual_path": str(root / ANNUAL_FILENAME),
        "monthly_path": str(root / MONTHLY_FILENAME),
        "originators_path": str(root / ORIGINATORS_FILENAME),
        "annual_rows": int(len(annual)),
        "monthly_rows": int(len(monthly)),
        "originator_rows": int(len(originators)),
        "source_archive_sha256": str(annual["source_archive_sha256"].iloc[0]),
    }


__all__ = [
    "ClosedOffersSourceError",
    "ORIGINATOR_RULES",
    "RELEASE_CUTOFF",
    "SOURCE_ARCHIVE_SHA256",
    "SOURCE_AS_OF_DATE",
    "build_closed_offer_tables_from_archive",
    "load_closed_offer_source",
    "write_closed_offer_tables",
]
