"""Canonical public-primary-offer universe across every CVM rite.

The official CVM archive exposes two tables with different schemas:

* ``oferta_resolucao_160.csv``: automatic RCVM 160 filings;
* ``oferta_distribuicao.csv``: ordinary RCVM 160/ICVM 400, ICVM 555 and
  closed ICVM 476 offerings.

This module normalizes both tables before any aggregation.  It preserves the
declared instrument and source row, while exposing one analytical instrument
taxonomy and one stable offer key.  Legacy rows are considered closed only
when ``Data_Encerramento_Oferta`` is present.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
import unicodedata
from zipfile import ZipFile

import pandas as pd


SOURCE_DATASETS = (
    "oferta_resolucao_160.csv",
    "oferta_distribuicao.csv",
)
SOURCE_DATASET_LABEL = "oferta_resolucao_160.csv + oferta_distribuicao.csv"
SOURCE_URL = (
    "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/"
    "oferta_distribuicao.zip"
)

FIDC_CANONICAL = "COTAS DE FIDC"
EXCLUDED_CANONICAL = "__EXCLUIDO__"


class PublicOffersError(ValueError):
    """Raised when the official archive cannot satisfy the source contract."""


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(
        character for character in text
        if not unicodedata.combining(character)
    )
    return " ".join(text.upper().split())


def only_digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def archive_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_instrument(value: object) -> str:
    """Map official labels across schemas without inferring an issuer sector."""

    label = normalize_text(value)
    if not label:
        return ""
    if "DEBENTUR" in label and "CONVERS" in label:
        return EXCLUDED_CANONICAL
    if (
        "FIAGRO" in label
        or "FIC-FIDC" in label
        or "FIC FIDC" in label
    ):
        return EXCLUDED_CANONICAL
    if "FIDC" in label or "FUNDO INVEST DIREITOS CREDITORIOS" in label:
        return FIDC_CANONICAL
    if "DEBENTUR" in label:
        return "DEBENTURES"
    if "RECEBIVEIS IMOBILIAR" in label:
        return "CERTIFICADOS DE RECEBIVEIS IMOBILIARIOS"
    if "RECEBIVEIS DO AGRONEGOCIO" in label:
        return "CERTIFICADOS DE RECEBIVEIS DO AGRONEGOCIO"
    if "NOTAS COMERCIAIS" in label or "NOTA COMERCIAL" in label:
        return "NOTAS COMERCIAIS"
    if "NOTAS PROMISSORIAS" in label or "NOTA PROMISSORIA" in label:
        return "NOTAS PROMISSORIAS"
    if "CEDULA DE PRODUTO RURAL" in label:
        return "CEDULA DE PRODUTO RURAL FINANCEIRA"
    if "DIREITOS CREDITORIOS DO AGRONEGOCIO" in label:
        return "CERTIFICADO DE DIREITOS CREDITORIOS DO AGRONEGOCIO"
    if "OUTROS TITULOS DE SECURITIZACAO" in label:
        return "OUTROS TITULOS DE SECURITIZACAO"
    if "CERTIFICADOS DE RECEBIVEIS" in label:
        return "CERTIFICADOS DE RECEBIVEIS"
    excluded_tokens = (
        "ACAO",
        "ACOES",
        "CERTIFICADO DE DEPOSITO DE ACOES",
        "FUNCINE",
        "FUNDO DE INVESTIMENTO",
        "FUNDO IMOBILIARIO",
        "FUNDOS DE INFRA",
        "QUOTAS DE FI",
        "COTAS DE FI",
        "QUOTAS DE FUNDO",
        "COTAS DE FUNDO",
        "QUOTAS DE OUTROS FUNDOS",
    )
    if any(token in label for token in excluded_tokens):
        return EXCLUDED_CANONICAL
    return label


def _read_csv(archive: ZipFile, name: str) -> pd.DataFrame:
    if name not in archive.namelist():
        raise PublicOffersError(f"Tabela {name} ausente no arquivo CVM.")
    return pd.read_csv(
        archive.open(name),
        sep=";",
        encoding="latin-1",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )


def _automatic_rows(source: pd.DataFrame) -> pd.DataFrame:
    required = {
        "Numero_Requerimento",
        "Data_Encerramento",
        "Status_Requerimento",
        "Valor_Mobiliario",
        "Tipo_Oferta",
        "Valor_Total_Registrado",
    }
    missing = sorted(required.difference(source.columns))
    if missing:
        raise PublicOffersError(
            "RCVM 160 automática sem colunas: " + ", ".join(missing)
        )
    blank = pd.Series("", index=source.index, dtype=object)
    result = pd.DataFrame(
        {
            "offer_id": source["Numero_Requerimento"].str.strip(),
            "source_dataset": "oferta_resolucao_160.csv",
            "source_offer_id": source["Numero_Requerimento"].str.strip(),
            "closing_date": pd.to_datetime(
                source["Data_Encerramento"], errors="coerce"
            ),
            "status_norm": source["Status_Requerimento"].map(normalize_text),
            "offer_type_norm": source["Tipo_Oferta"].map(normalize_text),
            "instrument_official": source["Valor_Mobiliario"].str.strip(),
            "issuer_cnpj": source.get("CNPJ_Emissor", blank).map(only_digits),
            "issuer_name": source.get("Nome_Emissor", blank).str.strip(),
            "registered_volume_brl": pd.to_numeric(
                source["Valor_Total_Registrado"], errors="coerce"
            ),
            "leader_name": source.get("Nome_Lider", blank).str.strip(),
            "target_public": source.get("Publico_alvo", blank).str.strip(),
            "distribution_regime": source.get(
                "Regime_distribuicao", blank
            ).str.strip(),
            "status_basis": "Status_Requerimento = Oferta Encerrada",
        }
    )
    investor_columns = [
        column for column in source.columns if column.startswith("Num_Invest_")
    ]
    result["investor_count"] = source[investor_columns].apply(
        pd.to_numeric, errors="coerce"
    ).sum(axis=1, min_count=1)
    quantity_columns = [
        column
        for column in source.columns
        if column.startswith("Qtde_VM_") or column.startswith("Qdte_VM_")
    ]
    result["registered_quantity"] = pd.to_numeric(
        source.get("Qtde_Total_Registrada", blank), errors="coerce"
    )
    result["placed_quantity"] = source[quantity_columns].apply(
        pd.to_numeric, errors="coerce"
    ).sum(axis=1, min_count=1)
    result["natural_person_accounts"] = pd.to_numeric(
        source.get("Num_Invest_Pessoa_Natural", blank), errors="coerce"
    )
    result["natural_person_quantity"] = pd.to_numeric(
        source.get("Qtde_VM_Pessoa_Natural", blank), errors="coerce"
    )
    result["assets_target"] = source.get("Ativos_alvo", blank).str.strip()
    result["receivables_description"] = source.get(
        "Descricao_lastro", blank
    ).str.strip()
    result["debtor_identification"] = source.get(
        "Identificacao_devedores_coobrigados", blank
    ).str.strip()
    return result


def _legacy_rows(source: pd.DataFrame) -> pd.DataFrame:
    required = {
        "Numero_Registro_Oferta",
        "Numero_Processo",
        "Data_Encerramento_Oferta",
        "Tipo_Ativo",
        "Tipo_Oferta",
        "CNPJ_Emissor",
        "Nome_Emissor",
        "Valor_Total",
        "Nome_Lider",
        "Rito_Oferta",
    }
    missing = sorted(required.difference(source.columns))
    if missing:
        raise PublicOffersError(
            "ritos ordinários/legados sem colunas: " + ", ".join(missing)
        )
    source = source.copy()
    source["canonical_instrument"] = source["Tipo_Ativo"].map(
        canonical_instrument
    )
    source["closing_date"] = pd.to_datetime(
        source["Data_Encerramento_Oferta"],
        errors="coerce",
        format="mixed",
        dayfirst=True,
    )
    source["registered_volume_brl"] = pd.to_numeric(
        source["Valor_Total"], errors="coerce"
    )
    source["offer_type_norm"] = source["Tipo_Oferta"].map(normalize_text)
    source["source_offer_id"] = (
        source["Numero_Registro_Oferta"].str.strip()
        .where(
            source["Numero_Registro_Oferta"].str.strip().ne(""),
            source["Numero_Processo"].str.strip(),
        )
    )
    source = source[
        source["source_offer_id"].ne("")
        & source["closing_date"].notna()
        & source["offer_type_norm"].eq("PRIMARIA")
        & source["registered_volume_brl"].gt(0)
    ].copy()
    source["issuer_cnpj"] = source["CNPJ_Emissor"].map(only_digits)
    source["offer_id"] = (
        "LEGACY:"
        + source["source_offer_id"]
        + ":"
        + source["issuer_cnpj"]
        + ":"
        + source["closing_date"].dt.strftime("%Y-%m-%d")
        + ":"
        + source["canonical_instrument"]
    )
    numeric_investor_columns = [
        column
        for column in source.columns
        if column.startswith("Nr_")
    ]
    source["investor_count"] = source[numeric_investor_columns].apply(
        pd.to_numeric, errors="coerce"
    ).sum(axis=1, min_count=1)
    source["registered_quantity"] = pd.to_numeric(
        source["Quantidade_Total"], errors="coerce"
    )
    legacy_quantity_columns = [
        column
        for column in source.columns
        if column.startswith("Qtd_") or column.startswith("Qdt_")
    ]
    source["placed_quantity"] = source[legacy_quantity_columns].apply(
        pd.to_numeric, errors="coerce"
    ).sum(axis=1, min_count=1)
    source["natural_person_accounts"] = pd.to_numeric(
        source["Nr_Pessoa_Fisica"], errors="coerce"
    )
    source["natural_person_quantity"] = pd.to_numeric(
        source["Qtd_Pessoa_Fisica"], errors="coerce"
    )

    # A legacy registration may list senior, mezzanine and subordinated FIDC
    # quotas on separate rows.  They form one offering for the analytical
    # instrument and their registered values are additive.
    grouped_rows: list[dict[str, object]] = []
    for (_, _, _, canonical), group in source.groupby(
        [
            "source_offer_id",
            "issuer_cnpj",
            "closing_date",
            "canonical_instrument",
        ],
        sort=False,
        dropna=False,
    ):
        first = group.iloc[0]
        stable = (
            "offer_type_norm",
            "issuer_cnpj",
        )
        values = {
            "offer_type_norm": group["offer_type_norm"],
            "issuer_cnpj": group["issuer_cnpj"],
        }
        conflicts = [
            column
            for column in stable
            if values[column].drop_duplicates().shape[0] > 1
        ]
        if conflicts:
            raise PublicOffersError(
                f"{first['source_offer_id']}: campos legados conflitantes: "
                + ", ".join(conflicts)
            )
        grouped_rows.append(
            {
                "offer_id": first["offer_id"],
                "source_dataset": "oferta_distribuicao.csv",
                "source_offer_id": first["source_offer_id"],
                "closing_date": first["closing_date"],
                "status_norm": "OFERTA ENCERRADA",
                "offer_type_norm": first["offer_type_norm"],
                "instrument_official": " | ".join(
                    dict.fromkeys(
                        value.strip()
                        for value in group["Tipo_Ativo"]
                        if value.strip()
                    )
                ),
                "canonical_instrument": canonical,
                "issuer_cnpj": only_digits(first["CNPJ_Emissor"]),
                "issuer_name": " | ".join(
                    dict.fromkeys(
                        value.strip()
                        for value in group["Nome_Emissor"]
                        if value.strip()
                    )
                ),
                "registered_volume_brl": float(
                    group["registered_volume_brl"].sum()
                ),
                "leader_name": " | ".join(
                    dict.fromkeys(
                        value.strip()
                        for value in group["Nome_Lider"]
                        if value.strip()
                    )
                ),
                "target_public": "",
                "distribution_regime": "",
                "investor_count": float(
                    group["investor_count"].sum(min_count=1)
                ),
                "registered_quantity": float(
                    group["registered_quantity"].sum(min_count=1)
                ),
                "placed_quantity": float(
                    group["placed_quantity"].sum(min_count=1)
                ),
                "natural_person_accounts": float(
                    group["natural_person_accounts"].sum(min_count=1)
                ),
                "natural_person_quantity": float(
                    group["natural_person_quantity"].sum(min_count=1)
                ),
                "assets_target": "",
                "receivables_description": "",
                "debtor_identification": "",
                "status_basis": (
                    "Data_Encerramento_Oferta preenchida; rito "
                    + str(first["Rito_Oferta"]).strip()
                ),
            }
        )
    return pd.DataFrame(grouped_rows)


def load_public_primary_closed_offers(
    archive_path: str | Path,
    *,
    cutoff: str,
    expected_archive_sha256: str | None = None,
) -> tuple[pd.DataFrame, str]:
    """Load and reconcile every public-primary rite in the CVM archive."""

    path = Path(archive_path)
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo CVM de ofertas ausente: {path}")
    digest = archive_sha256(path)
    if expected_archive_sha256 and digest != expected_archive_sha256:
        raise PublicOffersError(
            "SHA-256 do arquivo CVM diverge do snapshot esperado: " + digest
        )
    with ZipFile(path) as archive:
        automatic = _automatic_rows(
            _read_csv(archive, "oferta_resolucao_160.csv")
        )
        automatic["canonical_instrument"] = automatic[
            "instrument_official"
        ].map(canonical_instrument)
        legacy = _legacy_rows(_read_csv(archive, "oferta_distribuicao.csv"))
    duplicate = automatic.duplicated("offer_id", keep=False)
    if duplicate.any():
        comparison = [
            "closing_date",
            "canonical_instrument",
            "registered_volume_brl",
            "issuer_cnpj",
            "issuer_name",
        ]
        conflicts = [
            str(offer_id)
            for offer_id, group in automatic.loc[duplicate].groupby(
                "offer_id"
            )
            if len(group[comparison].drop_duplicates()) != 1
        ]
        if conflicts:
            raise PublicOffersError(
                "Numero_Requerimento com linhas conflitantes: "
                + ", ".join(conflicts[:5])
            )
        automatic = automatic.drop_duplicates("offer_id", keep="first")
    combined = pd.concat([automatic, legacy], ignore_index=True)
    selected = combined[
        combined["status_norm"].eq("OFERTA ENCERRADA")
        & combined["offer_type_norm"].eq("PRIMARIA")
        & combined["closing_date"].notna()
        & combined["closing_date"].le(pd.Timestamp(cutoff))
        & combined["registered_volume_brl"].gt(0)
    ].copy()
    if selected["offer_id"].eq("").any():
        raise PublicOffersError("Identificador de oferta vazio.")
    duplicate = selected.duplicated("offer_id", keep=False)
    if duplicate.any():
        sample = ", ".join(
            selected.loc[duplicate, "offer_id"].astype(str).head(5)
        )
        raise PublicOffersError(
            "Identificador de oferta duplicado após reconciliação: " + sample
        )
    selected["closing_date"] = pd.to_datetime(selected["closing_date"])
    return (
        selected.sort_values(["closing_date", "offer_id"]).reset_index(
            drop=True
        ),
        digest,
    )


__all__ = [
    "EXCLUDED_CANONICAL",
    "FIDC_CANONICAL",
    "PublicOffersError",
    "SOURCE_DATASET_LABEL",
    "SOURCE_DATASETS",
    "SOURCE_URL",
    "archive_sha256",
    "canonical_instrument",
    "load_public_primary_closed_offers",
    "normalize_text",
]
