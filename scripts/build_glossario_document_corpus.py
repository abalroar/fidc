"""Inventaria e le documentos oficiais do corpus de 100 FIDCs.

Os PDFs ficam em ``data/raw/`` (ignorado pelo Git). O ledger versionavel e
gravado no diretorio do relatorio. A selecao de documentos e deliberadamente
conservadora: regulamento vigente, versao material anterior e um documento
mais recente de cada familia prioritaria, quando disponivel no Fundos.NET.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
from io import BytesIO
from pathlib import Path
import re
import sys
from typing import Any

import pandas as pd
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.fundonet_client import FundosNetClient  # noqa: E402
from services.fundonet_models import DocumentoFundo  # noqa: E402


DEFAULT_REPORT_DIR = ROOT / "reports" / "glossario_100_fidcs_20260716"
DEFAULT_RAW_DIR = ROOT / "data" / "raw" / "glossario_100_fidcs_20260716"
EXISTING_RAW_DIR = ROOT / "data" / "raw" / "industry_large_funds"
FUNDOSNET_DOCUMENT_URL = "https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id={document_id}&cvm=true"

PRIORITIES = (
    "regulamento vigente",
    "parte geral e anexo da classe",
    "versão anterior material",
    "instrumento de emissão",
    "prospecto ou lâmina",
    "relatório mensal ou trimestral",
    "relatório de rating",
    "fato relevante ou assembleia",
    "demonstrações financeiras",
)


def _cnpj(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(14)[-14:] if digits else ""


def _safe_name(value: object) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._")
    return text[:100] or "documento"


def _date(value: object) -> pd.Timestamp | pd.NaT:
    text = str(value or "").strip()
    if not text:
        return pd.NaT
    return pd.to_datetime(text, dayfirst=True, errors="coerce")


def _document_text(document: DocumentoFundo) -> str:
    return " ".join(
        str(value or "")
        for value in (
            document.categoria,
            document.tipo,
            document.especie,
            document.nome_arquivo,
        )
    ).casefold()


def _family(document: DocumentoFundo) -> str:
    text = _document_text(document)
    if "rating" in text or "classifica" in text and "risco" in text:
        return "relatório de rating"
    if "demonstra" in text and ("financeir" in text or "contáb" in text or "contab" in text):
        return "demonstrações financeiras"
    if "prospecto" in text or "lâmina" in text or "lamina" in text:
        return "prospecto ou lâmina"
    if "regulamento" in text or "aditamento" in text or "alteração de regulamento" in text:
        return "regulamento"
    if any(token in text for token in ("instrumento de emissão", "instrumento de emissao", "emissão de cotas", "emissao de cotas", "suplemento", "oferta")):
        return "instrumento de emissão"
    if any(token in text for token in ("relatório mensal", "relatorio mensal", "relatório trimestral", "relatorio trimestral", "informe trimestral")):
        return "relatório mensal ou trimestral"
    if any(token in text for token in ("assembleia", "assembléia", "ata", "fato relevante", "comunicado", "deliberação", "deliberacao")):
        return "fato relevante ou assembleia"
    return "outro"


def _sort_key(document: DocumentoFundo) -> tuple[int, datetime, datetime, int, int]:
    reference = _date(document.data_referencia)
    delivery = _date(document.data_entrega)
    return (
        1 if str(document.status).upper() == "AC" else 0,
        reference.to_pydatetime() if not pd.isna(reference) else datetime.min,
        delivery.to_pydatetime() if not pd.isna(delivery) else datetime.min,
        int(document.versao or 0),
        int(document.id),
    )


def _select_documents(documents: list[DocumentoFundo]) -> dict[str, DocumentoFundo | None]:
    grouped: dict[str, list[DocumentoFundo]] = defaultdict(list)
    for document in documents:
        grouped[_family(document)].append(document)
    for values in grouped.values():
        values.sort(key=_sort_key, reverse=True)

    regulations = grouped.get("regulamento", [])
    selected: dict[str, DocumentoFundo | None] = {
        "regulamento vigente": regulations[0] if regulations else None,
        "parte geral e anexo da classe": regulations[0] if regulations else None,
        "versão anterior material": regulations[1] if len(regulations) > 1 else None,
    }
    for priority in PRIORITIES[3:]:
        selected[priority] = grouped.get(priority, [None])[0]
    return selected


def _existing_document(document_id: int, cnpjs: set[str]) -> Path | None:
    candidates: list[Path] = []
    for cnpj in sorted(cnpjs):
        directory = EXISTING_RAW_DIR / cnpj
        if not directory.is_dir():
            continue
        candidates.extend(path for path in directory.glob(f"{document_id}_*") if path.is_file())
    suffix_priority = {".pdf": 0, ".docx": 1, ".doc": 2, ".txt": 3}
    supported = [path for path in candidates if path.suffix.lower() in suffix_priority]
    return min(
        supported,
        key=lambda path: (suffix_priority[path.suffix.lower()], str(path)),
        default=None,
    )


def _download(
    *,
    client: FundosNetClient,
    document: DocumentoFundo,
    fund_dir: Path,
    component_cnpjs: set[str],
) -> tuple[Path | None, bytes, str]:
    existing = _existing_document(document.id, component_cnpjs)
    if existing is not None:
        return existing, existing.read_bytes(), ""
    candidates = sorted(fund_dir.glob(f"{document.id}_*")) if fund_dir.is_dir() else []
    if candidates:
        return candidates[0], candidates[0].read_bytes(), ""
    try:
        content = client.download_documento(document.id)
    except Exception as exc:  # noqa: BLE001
        return None, b"", f"{type(exc).__name__}: {exc}"
    suffix = ".pdf" if content.startswith(b"%PDF") else ".bin"
    fund_dir.mkdir(parents=True, exist_ok=True)
    path = fund_dir / f"{document.id}_{_safe_name(_family(document))}{suffix}"
    path.write_bytes(content)
    return path, content, ""


def _extract(content: bytes, path: Path | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "sha256": hashlib.sha256(content).hexdigest() if content else "",
        "bytes": len(content),
        "pages": 0,
        "pages_without_text": 0,
        "text_chars": 0,
        "extraction_method": "",
        "extraction_error": "",
        "read_status": "inacessível" if not content else "OCR necessário",
    }
    if not content:
        return result
    if content.startswith(b"%PDF"):
        try:
            reader = PdfReader(BytesIO(content))
            page_texts: list[str] = []
            for page in reader.pages:
                try:
                    page_texts.append(page.extract_text() or "")
                except Exception:  # noqa: BLE001
                    page_texts.append("")
            result["pages"] = len(page_texts)
            result["pages_without_text"] = sum(not text.strip() for text in page_texts)
            result["text_chars"] = sum(len(text) for text in page_texts)
            result["extraction_method"] = "pypdf_page_by_page"
            result["read_status"] = "lido" if result["text_chars"] else "OCR necessário"
        except Exception as exc:  # noqa: BLE001
            result["extraction_error"] = f"{type(exc).__name__}: {exc}"
            result["read_status"] = "OCR necessário"
    elif path and path.suffix.lower() == ".txt":
        result["text_chars"] = len(content.decode("utf-8", errors="replace"))
        result["extraction_method"] = "texto_local_derivado"
        result["read_status"] = "cache-only"
    else:
        result["extraction_method"] = "formato_não_suportado"
        result["read_status"] = "OCR necessário"
    return result


def _base_row(
    *,
    selection_row: Any,
    priority: str,
    document: DocumentoFundo | None,
    historical_names: str,
) -> dict[str, Any]:
    original_date = document.data_referencia if document else ""
    normalized_date = _date(original_date)
    return {
        "competencia": selection_row.competencia,
        "cnpj_fundo": selection_row.cnpj_fundo,
        "fundo": selection_row.nome,
        "nomes_historicos": historical_names,
        "segmento_oficial": selection_row.segmento_oficial_tabela_ii,
        "abertura_financeira": selection_row.abertura_financeira_tabela_ii,
        "subtipo_cvm_ime": selection_row.subtipo_cvm_ime,
        "pl": float(selection_row.pl_agregado),
        "prioridade_documental": priority,
        "documento_id": document.id if document else "",
        "categoria": document.categoria if document else "",
        "tipo": document.tipo if document else "",
        "especie": document.especie if document else "",
        "data_original": original_date or "",
        "data_normalizada": normalized_date.date().isoformat() if not pd.isna(normalized_date) else "",
        "data_entrega_original": document.data_entrega if document else "",
        "versao": document.versao if document else "",
        "status_fundosnet": document.status if document else "",
        "url_oficial": FUNDOSNET_DOCUMENT_URL.format(document_id=document.id) if document else "",
    }


def _relative(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _append_existing_additional(
    rows: list[dict[str, Any]],
    selection: pd.DataFrame,
    seen_document_ids: set[tuple[str, int]],
) -> None:
    ledger_path = ROOT / "data" / "industry_study" / "industry_large_fund_documents.csv.gz"
    if not ledger_path.is_file():
        return
    ledger = pd.read_csv(ledger_path, low_memory=False, dtype={"cnpj": str, "document_id": str})
    ledger["cnpj"] = ledger["cnpj"].map(_cnpj)
    selected_lookup = selection.set_index("cnpj_fundo")
    for item in ledger.itertuples(index=False):
        cnpj = item.cnpj
        if cnpj not in selected_lookup.index:
            continue
        try:
            document_id = int(str(item.document_id))
        except ValueError:
            continue
        if (cnpj, document_id) in seen_document_ids:
            continue
        paths = sorted((EXISTING_RAW_DIR / cnpj).glob(f"{document_id}_*"))
        path = next((candidate for candidate in paths if candidate.suffix.lower() == ".pdf"), None)
        if path is None:
            continue
        selected = selected_lookup.loc[cnpj]
        content = path.read_bytes()
        extracted = _extract(content, path)
        date_value = str(getattr(item, "data_referencia", "") or "")
        normalized_date = _date(date_value)
        rows.append(
            {
                "competencia": selected["competencia"],
                "cnpj_fundo": cnpj,
                "fundo": selected["nome"],
                "nomes_historicos": "",
                "segmento_oficial": selected["segmento_oficial_tabela_ii"],
                "abertura_financeira": selected["abertura_financeira_tabela_ii"],
                "subtipo_cvm_ime": selected["subtipo_cvm_ime"],
                "pl": float(selected["pl_agregado"]),
                "prioridade_documental": "corpus primário adicional",
                "documento_id": document_id,
                "categoria": getattr(item, "categoria", ""),
                "tipo": getattr(item, "tipo", ""),
                "especie": getattr(item, "especie", ""),
                "data_original": date_value,
                "data_normalizada": normalized_date.date().isoformat() if not pd.isna(normalized_date) else "",
                "data_entrega_original": str(getattr(item, "data_entrega", "") or ""),
                "versao": getattr(item, "versao", ""),
                "status_fundosnet": getattr(item, "status", ""),
                "url_oficial": FUNDOSNET_DOCUMENT_URL.format(document_id=document_id),
                "caminho_local": _relative(path),
                **extracted,
                "download_error": "",
                "listing_error": "",
            }
        )
        seen_document_ids.add((cnpj, document_id))


def _canonicalize_document_rows(output: pd.DataFrame) -> pd.DataFrame:
    """Mantém uma linha por documento primário e uma por lacuna solicitada.

    O mesmo regulamento pode atender simultaneamente às prioridades "vigente"
    e "parte geral/anexo". Isso não o transforma em duas evidências. Linhas sem
    documento permanecem separadas para que a cobertura negativa de cada tipo
    solicitado continue auditável.
    """

    priority_order = {name: position for position, name in enumerate(PRIORITIES)}
    priority_order["corpus primário adicional"] = len(priority_order)
    with_document = output[output["documento_id"].notna() & (output["documento_id"].astype(str) != "")].copy()
    without_document = output[~output.index.isin(with_document.index)].copy()
    canonical_rows: list[pd.Series] = []
    for _, group in with_document.groupby(["cnpj_fundo", "documento_id"], sort=False, dropna=False):
        group = group.copy()
        group["_priority_order"] = group["prioridade_documental"].map(priority_order).fillna(999)
        group = group.sort_values(["_priority_order", "data_normalizada"], na_position="last")
        row = group.iloc[0].drop(labels=["_priority_order"])
        priorities = sorted(
            set(group["prioridade_documental"].dropna().astype(str)),
            key=lambda value: (priority_order.get(value, 999), value),
        )
        row["prioridades_documentais"] = ";".join(priorities)
        canonical_rows.append(row)
    documents = pd.DataFrame(canonical_rows)
    if not documents.empty:
        sha_counts = documents.loc[documents["sha256"].fillna("") != "", "sha256"].value_counts()
        documents["duplicatas_sha_no_corpus"] = documents["sha256"].map(sha_counts).fillna(0).astype(int)
    without_document["prioridades_documentais"] = without_document["prioridade_documental"]
    without_document["duplicatas_sha_no_corpus"] = 0
    return pd.concat([documents, without_document], ignore_index=True, sort=False)


def build(selection_path: Path, output_path: Path, raw_dir: Path, timeout: int) -> pd.DataFrame:
    selection = pd.read_csv(selection_path, dtype={"cnpj_fundo": str}, low_memory=False)
    selection["cnpj_fundo"] = selection["cnpj_fundo"].map(_cnpj)
    client = FundosNetClient(timeout_seconds=timeout, max_retries=2)
    rows: list[dict[str, Any]] = []
    seen_document_ids: set[tuple[str, int]] = set()

    for position, selected in enumerate(selection.itertuples(index=False), start=1):
        print(f"[{position:03d}/100] {selected.cnpj_fundo} {selected.nome[:62]}", flush=True)
        component_cnpjs = {
            _cnpj(value)
            for value in str(selected.cnpjs_classes_componentes).split(";")
            if _cnpj(value)
        }
        component_cnpjs.add(selected.cnpj_fundo)
        try:
            documents = client.listar_documentos(
                selected.cnpj_fundo,
                error_stage="listar_documentos_glossario_100",
            )
            listing_error = ""
        except Exception as exc:  # noqa: BLE001
            documents = []
            listing_error = f"{type(exc).__name__}: {exc}"
        historical_names = ";".join(
            sorted({str(document.nome_fundo).strip() for document in documents if document.nome_fundo})
        )
        selected_documents = _select_documents(documents)
        extracted_by_id: dict[int, tuple[Path | None, dict[str, Any], str]] = {}

        for priority in PRIORITIES:
            document = selected_documents.get(priority)
            row = _base_row(
                selection_row=selected,
                priority=priority,
                document=document,
                historical_names=historical_names,
            )
            if document is None:
                row.update(
                    {
                        "caminho_local": "",
                        "sha256": "",
                        "bytes": 0,
                        "pages": 0,
                        "pages_without_text": 0,
                        "text_chars": 0,
                        "extraction_method": "",
                        "extraction_error": "",
                        "read_status": "inacessível" if listing_error else "ausente",
                        "download_error": "",
                        "listing_error": listing_error,
                    }
                )
                rows.append(row)
                continue
            if document.id not in extracted_by_id:
                local_path, content, download_error = _download(
                    client=client,
                    document=document,
                    fund_dir=raw_dir / selected.cnpj_fundo,
                    component_cnpjs=component_cnpjs,
                )
                extracted_by_id[document.id] = (
                    local_path,
                    _extract(content, local_path),
                    download_error,
                )
            local_path, extracted, download_error = extracted_by_id[document.id]
            row.update(
                {
                    "caminho_local": _relative(local_path),
                    **extracted,
                    "download_error": download_error,
                    "listing_error": listing_error,
                }
            )
            rows.append(row)
            seen_document_ids.add((selected.cnpj_fundo, int(document.id)))

    _append_existing_additional(rows, selection, seen_document_ids)
    output = _canonicalize_document_rows(pd.DataFrame(rows))
    output = output.sort_values(
        ["cnpj_fundo", "prioridade_documental", "data_normalizada", "documento_id"],
        na_position="last",
    ).reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_REPORT_DIR / "selection_100.csv")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT_DIR / "document_coverage.csv")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()
    output = build(args.selection.resolve(), args.output.resolve(), args.raw_dir.resolve(), args.timeout)
    print(output["read_status"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
