#!/usr/bin/env python3
"""Read the documents of the largest ``Outros`` FIDCs and propose decisions.

The script extends the historical Top 20 curation to the long tail of the
``Outros`` bucket.  It is resumable: documents are cached under ``data/raw`` and
the fetch/classify stages can run independently.

Stages
------
``fetch``          download the latest regulation of every queued CNPJ.
``fetch-extra``    download supplementary documents for the CNPJs whose
                   regulation alone did not close the decision.
``classify``       read every cached document page by page and write the
                   conclusions CSV plus its manifest.

Official ANBIMA and CVM fields are never written by this script.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import sys

import pandas as pd
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.fundonet_client import (  # noqa: E402
    FundosNetClient,
    REGULAMENTO_CATEGORIA_ID,
)
from services.fundonet_documents import select_latest_public_document  # noqa: E402
from services.industry_outros_reclassification import (  # noqa: E402
    NAMED_DISPLAY_TYPES,
    decide,
    detect_fic_fidc,
)
from services.industry_taxonomy_review import normalize_cnpj  # noqa: E402


LOGGER = logging.getLogger("outros_reclassification")

DEFAULT_PERIODS = ("2023-12", "2024-12", "2025-12", "2026-06")
DEFAULT_RAW_DIR = Path("data/raw/industry_outros_reclassification")
DEFAULT_DATA_DIR = Path("data/industry_study")
QUEUE_FILENAME = "industry_outros_reclassification_queue.csv"
CONCLUSIONS_FILENAME = "industry_outros_reclassification_conclusions.csv"
MANIFEST_FILENAME = "industry_outros_reclassification_manifest.json"

#: Supplementary categories consulted when the regulation is not decisive.
SUPPLEMENTARY_CATEGORY_PATTERN = re.compile(
    r"REGULAMENTO|PROSPECTO|SUPLEMENTO|ANEXO|FATO RELEVANTE|ASSEMBLEIA|ATA|"
    r"COMUNICADO|INFORME|DEMONSTRA",
    re.IGNORECASE,
)
MAX_SUPPLEMENTARY_DOCUMENTS = 6

OUTPUT_COLUMNS: tuple[str, ...] = (
    "review_scope",
    "rank_reference",
    "cnpj_fundo",
    "nome_fidc",
    "pl_max",
    "competencia_pl_max",
    "competencias_observadas",
    "tipo_anbima_oficial",
    "foco_anbima_oficial",
    "document_id",
    "document_reference_date",
    "document_url",
    "local_path",
    "documentos_lidos",
    "paginas_lidas",
    "pagina_clausula",
    "cedent_originator_explicit",
    "evidence_summary",
    "tipo_anbima_sugerido",
    "foco_anbima_sugerido",
    "tabela_ii_sugerida_documental",
    "taxonomia_funcional_n1_sugerida",
    "taxonomia_funcional_n2_sugerida",
    "decision_status",
    "confianca_documental",
    "justificativa_curta",
    "family_scores",
    "perimeter_proposal",
    "is_fic_fidc_suggested",
    "manual_validation_reason",
    "reading_method",
    "source_limitations",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=("queue", "fetch", "fetch-extra", "classify", "all"),
        default="all",
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--periods", default=",".join(DEFAULT_PERIODS))
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=60)
    return parser.parse_args()


def repo_relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve()))


def document_url(cnpj: str) -> str:
    return (
        "https://fnet.bmfbovespa.com.br/fnet/publico/"
        f"abrirGerenciadorDocumentosCVM?cnpjFundo={cnpj}"
    )


def build_queue(
    data_dir: Path,
    periods: tuple[str, ...],
) -> pd.DataFrame:
    """One row per non-curated CNPJ displayed as ``Outros``, ordered by PL."""

    base = pd.read_csv(
        data_dir / "generated_revision" / "base_fundo_cnpj.csv.gz",
        dtype=str,
        keep_default_na=False,
    )
    base["cnpj_fundo"] = base["cnpj_fundo"].map(normalize_cnpj)
    base["pl"] = pd.to_numeric(base["pl"], errors="coerce").fillna(0.0)
    base = base[base["competencia"].isin(periods)]
    base = base[~base["is_fic_fidc"].str.strip().str.casefold().isin({"true", "1"})]
    base["tipo_exibicao"] = base["anbima_tipo"].where(
        base["anbima_tipo"].isin(NAMED_DISPLAY_TYPES), "Outros"
    )
    outros = base[base["tipo_exibicao"].eq("Outros") & base["pl"].gt(0)].copy()

    ledger_path = data_dir / "taxonomy_review_actions.csv"
    curated: set[str] = set()
    if ledger_path.exists():
        ledger = pd.read_csv(ledger_path, dtype=str, keep_default_na=False)
        curated = set(ledger["cnpj_fundo"].map(normalize_cnpj))
    outros = outros[~outros["cnpj_fundo"].isin(curated)].copy()

    periods_seen = (
        outros.groupby("cnpj_fundo")["competencia"]
        .agg(lambda values: ", ".join(sorted(set(values), reverse=True)))
        .rename("competencias_observadas")
    )
    representatives = (
        outros.sort_values(
            ["pl", "competencia", "cnpj_fundo"], ascending=[False, False, True]
        )
        .drop_duplicates("cnpj_fundo", keep="first")
        .rename(columns={"pl": "pl_max", "competencia": "competencia_pl_max"})
        .merge(periods_seen, on="cnpj_fundo", how="left", validate="one_to_one")
    )
    representatives["is_np"] = representatives["is_np"].str.strip().str.casefold().isin(
        {"true", "1"}
    )
    queue = representatives[
        [
            "cnpj_fundo",
            "denominacao",
            "pl_max",
            "competencia_pl_max",
            "competencias_observadas",
            "anbima_tipo",
            "anbima_foco",
            "is_np",
        ]
    ].sort_values(["pl_max", "cnpj_fundo"], ascending=[False, True])
    return queue.reset_index(drop=True)


def _cached_documents(fund_dir: Path) -> list[Path]:
    if not fund_dir.is_dir():
        return []
    return sorted(
        path
        for path in fund_dir.glob("*.pdf")
        if path.stat().st_size and not path.name.endswith(".pages.json.gz")
    )


def fetch_regulation(
    cnpj: str,
    raw_dir: Path,
    timeout: int,
) -> dict[str, object]:
    fund_dir = raw_dir / cnpj
    cached = [path for path in _cached_documents(fund_dir) if "_regulamento" in path.name]
    if cached:
        latest_cached = cached[-1]
        return {
            "cnpj_fundo": cnpj,
            "document_id": latest_cached.name.split("_", 1)[0],
            "document_reference_date": "",
            "local_path": repo_relative(latest_cached),
            "reading_method": "cache_local_da_execucao",
            "status": "ok",
        }
    client = FundosNetClient(timeout_seconds=timeout, max_retries=2)
    try:
        documents = client.listar_documentos(
            cnpj, categoria_id=REGULAMENTO_CATEGORIA_ID
        )
    except Exception as error:  # noqa: BLE001
        return {
            "cnpj_fundo": cnpj,
            "document_id": "",
            "document_reference_date": "",
            "local_path": "",
            "reading_method": "falha_fundosnet",
            "status": f"erro: {type(error).__name__}",
        }
    latest = select_latest_public_document(documents)
    if latest is None:
        return {
            "cnpj_fundo": cnpj,
            "document_id": "",
            "document_reference_date": "",
            "local_path": "",
            "reading_method": "sem_regulamento_listado",
            "status": "sem_documento",
        }
    try:
        content = client.download_documento(latest.id)
    except Exception as error:  # noqa: BLE001
        return {
            "cnpj_fundo": cnpj,
            "document_id": str(latest.id),
            "document_reference_date": "",
            "local_path": "",
            "reading_method": "falha_download",
            "status": f"erro: {type(error).__name__}",
        }
    fund_dir.mkdir(parents=True, exist_ok=True)
    path = fund_dir / f"{latest.id}_regulamento.pdf"
    path.write_bytes(content)
    return {
        "cnpj_fundo": cnpj,
        "document_id": str(latest.id),
        "document_reference_date": (
            latest.data_referencia_dt.isoformat() if latest.data_referencia_dt else ""
        ),
        "local_path": repo_relative(path),
        "reading_method": "fundosnet_download",
        "status": "ok",
    }


def fetch_supplementary(
    cnpj: str,
    raw_dir: Path,
    timeout: int,
) -> dict[str, object]:
    fund_dir = raw_dir / cnpj
    existing = {path.name.split("_", 1)[0] for path in _cached_documents(fund_dir)}
    client = FundosNetClient(timeout_seconds=timeout, max_retries=2)
    try:
        documents = client.listar_documentos(cnpj)
    except Exception as error:  # noqa: BLE001
        return {"cnpj_fundo": cnpj, "downloaded": 0, "status": f"erro: {type(error).__name__}"}
    relevant = [
        document
        for document in documents
        if SUPPLEMENTARY_CATEGORY_PATTERN.search(
            f"{document.categoria} {document.tipo} {document.especie}"
        )
        and str(document.id) not in existing
    ]
    relevant.sort(
        key=lambda document: (
            document.data_referencia_dt or datetime.min.date(),
            document.id,
        ),
        reverse=True,
    )
    downloaded = 0
    fund_dir.mkdir(parents=True, exist_ok=True)
    for document in relevant[:MAX_SUPPLEMENTARY_DOCUMENTS]:
        try:
            content = client.download_documento(document.id)
        except Exception:  # noqa: BLE001
            continue
        if not content:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", str(document.categoria or "documento").lower())
        (fund_dir / f"{document.id}_{slug.strip('-') or 'documento'}.pdf").write_bytes(
            content
        )
        downloaded += 1
    return {"cnpj_fundo": cnpj, "downloaded": downloaded, "status": "ok"}


def extract_pages(path: Path) -> list[str]:
    """Extract the text of every page, caching it next to the PDF.

    Re-reading a corpus of two thousand regulations costs far more than the
    classification itself, and the calibration of the rules is iterative.  The
    cache is keyed by the size of the source file so a re-downloaded document
    invalidates it.
    """

    cache_path = path.with_suffix(".pages.json.gz")
    try:
        if cache_path.is_file():
            import gzip

            with gzip.open(cache_path, "rt", encoding="utf-8") as handle:
                cached = json.load(handle)
            if cached.get("bytes") == path.stat().st_size:
                return list(cached.get("pages", []))
    except Exception:  # noqa: BLE001
        pass
    pages = _extract_pages_uncached(path)
    try:
        import gzip

        with gzip.open(cache_path, "wt", encoding="utf-8") as handle:
            json.dump({"bytes": path.stat().st_size, "pages": pages}, handle)
    except Exception:  # noqa: BLE001
        pass
    return pages


def _extract_pages_uncached(path: Path) -> list[str]:
    try:
        reader = PdfReader(str(path))
    except Exception:  # noqa: BLE001
        return []
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(re.sub(r"\s+", " ", page.extract_text() or "").strip())
        except Exception:  # noqa: BLE001
            pages.append("")
    if sum(len(page) for page in pages) >= 400:
        return pages
    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as document:
            plumbed = [
                re.sub(r"\s+", " ", (page.extract_text() or "")).strip()
                for page in document.pages
            ]
    except Exception:  # noqa: BLE001
        return pages
    return plumbed if sum(len(page) for page in plumbed) > sum(
        len(page) for page in pages
    ) else pages


def _document_label(path: Path) -> str:
    parts = path.stem.split("_", 1)
    kind = parts[1] if len(parts) > 1 else "documento"
    return f"{kind} {parts[0]}"


def classify_fund(row: pd.Series, raw_dir: Path) -> dict[str, object]:
    cnpj = str(row["cnpj_fundo"])
    fund_dir = raw_dir / cnpj
    paths = _cached_documents(fund_dir)
    regulations = [path for path in paths if "regulamento" in path.name]
    ordered = regulations + [path for path in paths if path not in regulations]
    documents: list[tuple[str, list[str]]] = []
    pages_read = 0
    for path in ordered:
        pages = extract_pages(path)
        if not any(pages):
            continue
        documents.append((_document_label(path), pages))
        pages_read += len(pages)
    official_type = str(row.get("anbima_tipo") or "")
    if official_type not in NAMED_DISPLAY_TYPES:
        official_type = "Outros"
    decision = decide(
        documents,
        official_type=official_type,
        np_prior=bool(row.get("is_np")),
        readable=bool(documents),
    )
    primary = regulations[-1] if regulations else (ordered[0] if ordered else None)
    reading_method = (
        "leitura_pagina_a_pagina_regulamento"
        if regulations
        else ("leitura_pagina_a_pagina_documentos_complementares" if ordered else "sem_documento")
    )
    return {
        "review_scope": "outros_expansao_documental",
        "rank_reference": f"Outros — PL máximo em {row.get('competencia_pl_max')}",
        "cnpj_fundo": cnpj,
        "nome_fidc": str(row.get("denominacao") or ""),
        "pl_max": f"{float(row.get('pl_max') or 0.0):.2f}",
        "competencia_pl_max": str(row.get("competencia_pl_max") or ""),
        "competencias_observadas": str(row.get("competencias_observadas") or ""),
        "tipo_anbima_oficial": str(row.get("anbima_tipo") or ""),
        "foco_anbima_oficial": str(row.get("anbima_foco") or ""),
        "document_id": primary.stem.split("_", 1)[0] if primary else "",
        "document_reference_date": str(row.get("document_reference_date") or ""),
        "document_url": document_url(cnpj),
        "local_path": repo_relative(primary) if primary else "",
        "documentos_lidos": "; ".join(label for label, _pages in documents),
        "paginas_lidas": str(pages_read),
        "pagina_clausula": decision.pages,
        "cedent_originator_explicit": "",
        "evidence_summary": decision.evidence,
        "tipo_anbima_sugerido": decision.tipo,
        "foco_anbima_sugerido": decision.foco,
        "tabela_ii_sugerida_documental": decision.tabela_ii,
        "taxonomia_funcional_n1_sugerida": decision.n1,
        "taxonomia_funcional_n2_sugerida": decision.n2,
        "decision_status": decision.decision_status,
        "confianca_documental": decision.confidence,
        "justificativa_curta": decision.rationale,
        "family_scores": decision.family_scores,
        "perimeter_proposal": (
            decision.limitation if decision.decision_status == "rejeitado" else ""
        ),
        "is_fic_fidc_suggested": str(detect_fic_fidc(documents)) if documents else "False",
        "manual_validation_reason": decision.reason,
        "reading_method": reading_method,
        "source_limitations": decision.limitation,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = parse_args()
    periods = tuple(part.strip() for part in args.periods.split(",") if part.strip())
    data_dir = args.data_dir
    raw_dir = args.raw_dir
    queue_path = data_dir / QUEUE_FILENAME

    if args.stage in {"queue", "all"} or not queue_path.exists():
        queue = build_queue(data_dir, periods)
        queue.to_csv(queue_path, index=False)
        LOGGER.info("fila com %d CNPJs gravada em %s", len(queue), queue_path)
    queue = pd.read_csv(queue_path, dtype=str, keep_default_na=False)
    queue["pl_max"] = pd.to_numeric(queue["pl_max"], errors="coerce").fillna(0.0)
    queue["is_np"] = queue["is_np"].str.strip().str.casefold().isin({"true", "1"})
    batch = queue.iloc[args.offset : args.offset + args.limit].copy()
    LOGGER.info("lote de %d CNPJs (offset %d)", len(batch), args.offset)

    if args.stage in {"fetch", "all"}:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(fetch_regulation, cnpj, raw_dir, args.timeout): cnpj
                for cnpj in batch["cnpj_fundo"]
            }
            for index, future in enumerate(as_completed(futures), start=1):
                result = future.result()
                if index % 20 == 0:
                    LOGGER.info("regulamentos obtidos: %d/%d", index, len(futures))
                if result["status"] != "ok":
                    LOGGER.warning(
                        "%s: %s", result["cnpj_fundo"], result["status"]
                    )

    if args.stage in {"fetch-extra"}:
        conclusions_path = data_dir / CONCLUSIONS_FILENAME
        pending = batch["cnpj_fundo"].tolist()
        if conclusions_path.exists():
            previous = pd.read_csv(conclusions_path, dtype=str, keep_default_na=False)
            unresolved = previous[
                previous["decision_status"].isin({"pendente", "em_revisao"})
            ]["cnpj_fundo"]
            pending = [cnpj for cnpj in pending if cnpj in set(unresolved)]
        LOGGER.info("documentos complementares para %d CNPJs", len(pending))
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(fetch_supplementary, cnpj, raw_dir, args.timeout): cnpj
                for cnpj in pending
            }
            for index, future in enumerate(as_completed(futures), start=1):
                future.result()
                if index % 20 == 0:
                    LOGGER.info("complementares: %d/%d", index, len(futures))

    if args.stage in {"classify", "all", "fetch-extra"}:
        rows = [classify_fund(row, raw_dir) for _index, row in batch.iterrows()]
        conclusions = pd.DataFrame(rows, columns=list(OUTPUT_COLUMNS))
        conclusions_path = data_dir / CONCLUSIONS_FILENAME
        if conclusions_path.exists():
            previous = pd.read_csv(conclusions_path, dtype=str, keep_default_na=False)
            previous = previous[
                ~previous["cnpj_fundo"].isin(set(conclusions["cnpj_fundo"]))
            ]
            conclusions = pd.concat([previous, conclusions], ignore_index=True)
        conclusions = conclusions.sort_values(
            "pl_max", key=lambda values: pd.to_numeric(values, errors="coerce"),
            ascending=False,
        ).reset_index(drop=True)
        conclusions.to_csv(conclusions_path, index=False)
        base_path = data_dir / "generated_revision" / "base_fundo_cnpj.csv.gz"
        manifest = {
            "schema_version": "industry-outros-reclassification/v1",
            "generated_at_utc": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
            "periods": list(periods),
            "queue_size": int(len(queue)),
            "conclusions": int(len(conclusions)),
            "status_counts": conclusions["decision_status"]
            .value_counts()
            .to_dict(),
            "confidence_counts": conclusions["confianca_documental"]
            .value_counts()
            .to_dict(),
            "official_fields_mutated": False,
            "input_sha256": {str(base_path): _sha256(base_path)},
        }
        (data_dir / MANIFEST_FILENAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        LOGGER.info(
            "conclusões: %s", json.dumps(manifest["status_counts"], ensure_ascii=False)
        )


if __name__ == "__main__":
    main()
