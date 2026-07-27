"""Documentary review of the current Top 20 funds classified as Outros."""

from __future__ import annotations

from pathlib import Path
import re

import pandas as pd


OUTPUT_FILENAME = "industry_top20_outros_regulation_review.csv"
CURATION_FILENAME = "top20_outros_regulation_curation.csv"
FUNDOSNET_URL = (
    "https://fnet.bmfbovespa.com.br/fnet/publico/"
    "abrirGerenciadorDocumentosCVM?cnpjFundo={cnpj}"
)
OUTPUT_COLUMNS = (
    "rank_outros",
    "cnpj_fundo",
    "nome_fidc",
    "pl_atual_brl",
    "competencia_pl",
    "existente_ativo",
    "document_id",
    "document_reference_date",
    "document_url",
    "cedent_originator_explicit",
    "evidence_summary",
    "proposed_category",
    "reclassification_status",
    "manual_validation_reason",
    "reading_method",
    "source_limitations",
)


class Top20OutrosRegulationError(ValueError):
    """Raised when the regulation-review contract cannot be reconciled."""


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or "")).zfill(14)


def build_top20_outros_regulation_review(
    top20_outros: pd.DataFrame,
    curation: pd.DataFrame,
) -> pd.DataFrame:
    required_top = {
        "rank_outros",
        "cnpj_fundo",
        "denominacao",
        "pl",
        "competencia",
    }
    required_curation = {
        "cnpj_fundo",
        "expected_document_id",
        "document_reference_date",
        "cedent_originator_explicit",
        "evidence_summary",
        "proposed_category",
        "reclassification_status",
        "manual_validation_reason",
    }
    missing_top = sorted(required_top.difference(top20_outros.columns))
    missing_curation = sorted(required_curation.difference(curation.columns))
    if missing_top or missing_curation:
        raise Top20OutrosRegulationError(
            "Colunas ausentes: " + ", ".join(missing_top + missing_curation)
        )
    top = top20_outros.sort_values("rank_outros").head(20).copy()
    if len(top) != 20:
        raise Top20OutrosRegulationError("O ranking deve conter 20 fundos.")
    top["cnpj_key"] = top["cnpj_fundo"].map(_digits)
    cur = curation.copy()
    cur["cnpj_key"] = cur["cnpj_fundo"].map(_digits)
    if cur["cnpj_key"].duplicated().any():
        raise Top20OutrosRegulationError("Curadoria contém CNPJ duplicado.")
    joined = top.merge(
        cur.drop(columns="cnpj_fundo"),
        on="cnpj_key",
        how="left",
        validate="one_to_one",
    )
    if joined["cedent_originator_explicit"].isna().any():
        raise Top20OutrosRegulationError(
            "Há fundo do Top 20 sem curadoria documental."
        )
    joined["expected_document_id"] = joined[
        "expected_document_id"
    ].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    joined["document_url"] = joined["cnpj_key"].map(
        lambda cnpj: FUNDOSNET_URL.format(cnpj=cnpj)
    )
    joined["source_limitations"] = joined.apply(
        lambda row: (
            "Regulamento não localizado no FundosNet; ausência documentada."
            if not row["expected_document_id"]
            else "Extração automatizada do regulamento mais recente; a decisão taxonômica permanece sujeita a validação manual quando indicada."
        ),
        axis=1,
    )
    output = pd.DataFrame(
        {
            "rank_outros": joined["rank_outros"],
            "cnpj_fundo": joined["cnpj_key"],
            "nome_fidc": joined["denominacao"],
            "pl_atual_brl": pd.to_numeric(joined["pl"], errors="coerce"),
            "competencia_pl": joined["competencia"],
            "existente_ativo": True,
            "document_id": joined["expected_document_id"],
            "document_reference_date": joined["document_reference_date"].fillna("N/D"),
            "document_url": joined["document_url"],
            "cedent_originator_explicit": joined["cedent_originator_explicit"],
            "evidence_summary": joined["evidence_summary"],
            "proposed_category": joined["proposed_category"],
            "reclassification_status": joined["reclassification_status"],
            "manual_validation_reason": joined["manual_validation_reason"],
            "reading_method": "FundosNet; seleção do regulamento público vigente mais recente e extração de texto PDF por pypdf",
            "source_limitations": joined["source_limitations"],
        }
    )
    return validate_top20_outros_regulation_review(output)


def validate_top20_outros_regulation_review(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(OUTPUT_COLUMNS).difference(frame.columns))
    if missing:
        raise Top20OutrosRegulationError(
            "Saída sem colunas: " + ", ".join(missing)
        )
    result = frame.loc[:, OUTPUT_COLUMNS].copy()
    if len(result) != 20 or result["cnpj_fundo"].duplicated().any():
        raise Top20OutrosRegulationError(
            "A saída deve conter 20 CNPJs únicos."
        )
    result["rank_outros"] = pd.to_numeric(
        result["rank_outros"], errors="coerce"
    )
    result["pl_atual_brl"] = pd.to_numeric(
        result["pl_atual_brl"], errors="coerce"
    )
    if result[["rank_outros", "pl_atual_brl"]].isna().any().any():
        raise Top20OutrosRegulationError("Ranking contém número ausente.")
    if result["rank_outros"].tolist() != list(range(1, 21)):
        raise Top20OutrosRegulationError("Ranks devem ser sequenciais de 1 a 20.")
    if not result["pl_atual_brl"].is_monotonic_decreasing:
        raise Top20OutrosRegulationError("PL deve estar em ordem decrescente.")
    return result.reset_index(drop=True)


def load_top20_outros_regulation_review(data_dir: str | Path) -> pd.DataFrame:
    path = Path(data_dir) / OUTPUT_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Revisão de Outros ausente: {path}")
    return validate_top20_outros_regulation_review(pd.read_csv(path))


def write_top20_outros_regulation_review(
    frame: pd.DataFrame, data_dir: str | Path
) -> Path:
    output = validate_top20_outros_regulation_review(frame)
    path = Path(data_dir) / OUTPUT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)
    return path


__all__ = [
    "CURATION_FILENAME",
    "OUTPUT_FILENAME",
    "Top20OutrosRegulationError",
    "build_top20_outros_regulation_review",
    "load_top20_outros_regulation_review",
    "validate_top20_outros_regulation_review",
    "write_top20_outros_regulation_review",
]
