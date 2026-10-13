"""Explicit local OCR recovery for known unreadable PDFs; one page at a time."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from services.documentary_corpus import atomic_json, file_catalog_metadata, normalize_cnpj, sha256_file, text_stats, utc_now
from services.documentary_diligence import public_document_payload

OCR_METHODS = {"vision_ocr", "apple_vision_ocr"}


@dataclass
class OCRLimits:
    max_pages: int = 300
    dpi: int = 150
    page_timeout_seconds: int = 25
    disk_floor_bytes: int = 10 * 1024**3
    mean_confidence: float = .96
    minimum_confidence: float = .85
    max_image_side_pixels: int = 2200


class OCRResourceLimit(RuntimeError):
    pass


def select_documents(root: Path, *, all_unreadable=False, cnpjs=(), document_ids=()) -> list[tuple[Path, str]]:
    """Select explicit IDs or unreadable sources; names cannot authorize a match."""
    wanted = {normalize_cnpj(cnpj) for cnpj in cnpjs}
    ids = {str(value) for value in document_ids}
    selected = []
    for path in sorted((root / "data/documentary_diligence/corpus").glob("*.json")):
        corpus = json.loads(path.read_text(encoding="utf-8"))
        cnpj = normalize_cnpj(corpus.get("cnpj"))
        if cnpj != path.stem or (wanted and cnpj not in wanted):
            continue
        for document in corpus.get("documents", []):
            ident = str(document.get("id") or "")
            if not ident or not document.get("local_path") or (ids and ident not in ids):
                continue
            explicit_id = bool(ids and ident in ids)
            if all_unreadable and document.get("parse_status") != "unreadable_text":
                continue
            if not explicit_id and document.get("parse_status") != "unreadable_text":
                continue
            if not all_unreadable and not wanted:
                continue
            selected.append((path, ident))
    def priority(pair):
        corpus=json.loads(pair[0].read_text(encoding="utf-8"))
        document=next(d for d in corpus["documents"] if str(d.get("id"))==pair[1])
        return (document.get("classification") not in {"regulamento", "anexo"}, pair[0].stem, pair[1])
    return sorted(selected, key=priority)


def ocr_resume_valid(document: dict, pdf: Path) -> bool:
    if document.get("parse_method") not in OCR_METHODS or document.get("parse_status") not in {"complete", "partial"}:
        return False
    target = Path(document.get("text_path") or "")
    quality = document.get("ocr_quality") or {}
    if document.get("catalog_file_binding") == "conflict" or quality.get("source_sha256") not in (None, document.get("sha256")):
        return False
    if quality.get("source_catalog_metadata") and quality["source_catalog_metadata"] != (document.get("file_catalog_metadata") or file_catalog_metadata(document)):
        return False
    if not target.is_file() or not quality.get("text_sha256") or sha256_file(pdf) != document.get("sha256"):
        return False
    pages, visible = text_stats(target)
    return bool(visible and pages == document.get("pages_total") and len(quality.get("pages") or []) == pages
                and sha256_file(target) == quality["text_sha256"])


def page_output(rows: list[dict], limits: OCRLimits) -> tuple[str, dict]:
    rows = sorted(rows, key=lambda row: (-float(row["y"]), float(row["x"])))
    relevant = [row for row in rows if .04 < row["y"] < .96 and
                (len(row.get("text", "")) > 12 or re.search(r"\d.*(?:%|[,\.])", row.get("text", "")))]
    confidence = [float(row["confidence"]) for row in relevant]
    mean = statistics.mean(confidence) if confidence else 0
    minimum = min(confidence, default=0)
    excluded = not relevant or mean < limits.mean_confidence or minimum < limits.minimum_confidence
    lines, previous = [], None
    for row in rows:
        if previous and previous["y"] - (row["y"] + row["height"]) > max(row["height"], previous["height"]) * .65:
            lines.append("")
        lines.append(row.get("text", ""))
        previous = row
    return "\n".join(lines) + "\f", {"body_lines": len(relevant), "mean_confidence": round(mean, 4),
                                          "minimum_confidence": round(minimum, 4), "automatic_use_excluded": excluded}


class OCRRecovery:
    def __init__(self, root: Path, *, limits=None, runner=subprocess.run):
        self.root = root.resolve()
        self.base = self.root / "data/documentary_diligence"
        self.limits = limits or OCRLimits()
        self.runner = runner
        self.pages_used = 0
        self.binary = None

    def room(self):
        self.base.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.base).free < self.limits.disk_floor_bytes:
            raise OCRResourceLimit("disk_floor_reached")

    def engine(self) -> Path:
        if self.binary:
            return self.binary
        if sys.platform != "darwin" or not shutil.which("swiftc") or not shutil.which("pdftoppm") or not shutil.which("pdfinfo"):
            raise RuntimeError("local_apple_vision_unavailable; macOS, swiftc and Poppler required")
        self.room()
        source = Path(__file__).with_name("documentary_vision_ocr.swift")
        ident = sha256(source.read_bytes() + platform.machine().encode() + platform.mac_ver()[0].encode()).hexdigest()
        directory = self.root / ".cache/documentary-vision-ocr" / ident
        directory.mkdir(parents=True, exist_ok=True)
        binary = directory / "recognize"
        if not binary.exists():
            fd, temporary = tempfile.mkstemp(prefix="recognize.", dir=directory)
            os.close(fd)
            candidate = Path(temporary)
            try:
                self.runner([shutil.which("swiftc"), "-O", str(source), "-o", str(candidate)],
                            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
                os.replace(candidate, binary)
            finally:
                candidate.unlink(missing_ok=True)
        self.binary = binary
        return binary

    def recover(self, corpus_path: Path, ident: str, *, resume=True) -> dict:
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        document = next(d for d in corpus["documents"] if str(d.get("id")) == str(ident))
        if document.get("catalog_file_binding") == "conflict":
            raise ValueError("catalog_file_version_conflict_requires_document_acquisition")
        pdf = Path(document["local_path"])
        if not pdf.is_file() or sha256_file(pdf) != document.get("sha256"):
            raise ValueError("source_pdf_missing_or_sha256_mismatch")
        if resume and ocr_resume_valid(document, pdf):
            return {"cnpj": corpus["cnpj"], "document_id": ident, "status": "resumed_existing_ocr",
                    "source_sha256": document["sha256"], "parse_status": document["parse_status"], "pages_total": document["pages_total"]}
        self.room()
        info = self.runner(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True, timeout=self.limits.page_timeout_seconds)
        match = re.search(r"^Pages:\s*(\d+)\s*$", info.stdout, re.M)
        if not match:
            raise ValueError("physical_page_count_unavailable")
        total = int(match[1])
        source_catalog = document.get("file_catalog_metadata") or file_catalog_metadata(document)
        directory = self.base / "text/ocr"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (document["sha256"] + ".txt")
        partial = directory / (document["sha256"] + ".part.txt")
        checkpoint_path = directory / (document["sha256"] + ".checkpoint.json")
        recognition_config = {key: getattr(self.limits,key) for key in ("dpi", "mean_confidence", "minimum_confidence")}
        signature = sha256(json.dumps(recognition_config, sort_keys=True).encode()).hexdigest()
        checkpoint = json.loads(checkpoint_path.read_text()) if resume and checkpoint_path.exists() and partial.exists() else {}
        if checkpoint.get("source_sha256") != document["sha256"] or checkpoint.get("config_signature") != signature or checkpoint.get("pages_total") != total:
            checkpoint = {"source_sha256": document["sha256"], "config_signature": signature, "pages_total": total,
                          "completed_pages": 0, "text_bytes": 0, "pages": [], "excluded_pages": [], "started_at": utc_now()}
        completed = int(checkpoint["completed_pages"])
        if total - completed > self.limits.max_pages - self.pages_used:
            raise OCRResourceLimit("page_budget_reached; document not started or truncated")
        binary = self.engine()
        with partial.open("a+b") as stream, tempfile.TemporaryDirectory(prefix="documentary-ocr-page-") as temporary:
            stream.truncate(int(checkpoint["text_bytes"]))
            stream.seek(0, os.SEEK_END)
            temporary = Path(temporary)
            for page in range(completed + 1, total + 1):
                self.room()
                image, result = temporary / "page.png", temporary / "page.json"
                image.unlink(missing_ok=True); result.unlink(missing_ok=True)
                self.runner(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(self.limits.dpi),
                             "-gray", "-singlefile", "-png", str(pdf), str(temporary / "page")],
                            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=self.limits.page_timeout_seconds)
                with image.open("rb") as png:
                    header = png.read(24)
                if len(header) < 24 or not header.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("rendered_page_format_invalid")
                width, height = int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
                if max(width, height) > self.limits.max_image_side_pixels:
                    raise OCRResourceLimit("rendered_page_pixel_limit")
                self.runner([str(binary), str(image), str(result)], check=True, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, timeout=self.limits.page_timeout_seconds)
                if result.stat().st_size > 5 * 1024**2:
                    raise OCRResourceLimit("page_result_size_limit")
                content, metrics = page_output(json.loads(result.read_text())["lines"], self.limits)
                stream.write(content.encode("utf-8")); stream.flush()
                self.pages_used += 1
                metrics["page"] = page
                checkpoint["pages"].append(metrics)
                if metrics["automatic_use_excluded"]:
                    checkpoint["excluded_pages"].append(page)
                checkpoint.update(completed_pages=page, text_bytes=stream.tell(), updated_at=utc_now())
                atomic_json(checkpoint_path, checkpoint)
                if page % 10 == 0 or page == total:
                    print(f"{corpus['cnpj']}/{ident}: OCR {page}/{total}; excluded {len(checkpoint['excluded_pages'])}", flush=True)
        os.replace(partial, target)
        # Read the latest metadata before changing only this document's OCR fields.
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        document = next(d for d in corpus["documents"] if str(d.get("id")) == str(ident))
        if document.get("sha256") != checkpoint["source_sha256"] or document.get("catalog_file_binding") == "conflict" or (document.get("file_catalog_metadata") or file_catalog_metadata(document)) != source_catalog:
            raise ValueError("corpus_source_changed_during_ocr")
        excluded = checkpoint["excluded_pages"]
        original_quality = document.get("original_parse_quality") or document.get("parse_quality")
        if original_quality:
            document["original_parse_quality"] = original_quality
        document.update(original_text_map_status="unreadable_text", parse_method="apple_vision_ocr", text_path=str(target),
                        pages_total=total, pages_extracted=total, parse_status="partial" if excluded else "complete",
                        ocr_excluded_pages=excluded, error="ocr_low_confidence_pages:" + ",".join(map(str, excluded)) if excluded else "")
        document["parse_quality"] = {"status": "ocr_confidence_restricted" if excluded else "ocr_confidence_thresholds_met",
                                      "measurement": "local recognition model confidence; human review not certified"}
        document["ocr_quality"] = {"engine": "Apple Vision, local CPU", "recognition_languages": ["pt-BR", "en-US"],
                                   "dpi": self.limits.dpi, "maximum_image_side_pixels": self.limits.max_image_side_pixels, "color": "grayscale",
                                   "pages": checkpoint["pages"], "recognition_started_at": checkpoint["started_at"],
                                   "recognized_at": utc_now(), "confidence_threshold_mean": self.limits.mean_confidence,
                                   "confidence_threshold_minimum": self.limits.minimum_confidence,
                                   "human_review": "not_certified", "text_sha256": sha256_file(target)}
        document["ocr_quality"].update(source_sha256=document["sha256"], source_catalog_metadata=source_catalog)
        corpus["generated_at"] = utc_now()
        atomic_json(corpus_path, corpus)
        atomic_json(self.base / "audit_corpus" / corpus_path.name, public_document_payload(corpus))
        checkpoint.update(state="complete", completed_at=utc_now())
        atomic_json(checkpoint_path, checkpoint)
        return {"cnpj": corpus["cnpj"], "document_id": ident, "status": "recovered", "source_sha256": document["sha256"],
                "source_url": document.get("url"), "parse_status": document["parse_status"], "pages_total": total,
                "excluded_pages": excluded, "method": document["parse_method"], "quality": document["ocr_quality"]}


@contextmanager
def recovery_lock(base: Path):
    base.mkdir(parents=True, exist_ok=True)
    with (base / ".recovery.lock").open("a") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another_local_ocr_recovery_is_running") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all-unreadable", action="store_true")
    selection.add_argument("--only-cnpj", action="append", default=[])
    parser.add_argument("--document-id", "--only-id", action="append", default=[])
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-pages", type=int, default=300)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--page-timeout-seconds", type=int, default=25)
    parser.add_argument("--disk-floor-gb", type=float, default=10)
    args = parser.parse_args()
    if not 1 <= args.max_pages <= 300 or not 72 <= args.dpi <= 200 or not 1 <= args.page_timeout_seconds <= 60 or args.disk_floor_gb < 0:
        parser.error("Use max-pages1..300, dpi72..200, timeout1..60 and nonnegative disk floor")
    if any(len(normalize_cnpj(cnpj)) != 14 for cnpj in args.only_cnpj):
        parser.error("Selected CNPJs must have fourteen digits")
    root = args.root.resolve()
    selected = select_documents(root, all_unreadable=args.all_unreadable, cnpjs=args.only_cnpj, document_ids=args.document_id)
    recovery = OCRRecovery(root, limits=OCRLimits(max_pages=args.max_pages, dpi=args.dpi,
                           page_timeout_seconds=args.page_timeout_seconds, disk_floor_bytes=int(args.disk_floor_gb * 1024**3)))
    report = {"started_at": utc_now(), "scope": "Explicit local OCR of unreadable sources. Confidence is model output; no human or compliance certification.",
              "maximum_parallel_pages": 1, "limits": asdict(recovery.limits), "selected_documents": len(selected), "documents": [], "state": "running"}
    output = root / "data/documentary_diligence/qa/ocr_recovery.json"
    with recovery_lock(root / "data/documentary_diligence/text/ocr"):
        for path, ident in selected:
            try:
                row = recovery.recover(path, ident, resume=args.resume)
            except OCRResourceLimit as exc:
                row = {"cnpj": path.stem, "document_id": ident, "status": "resource_limit", "reason": str(exc)}
                report["state"] = "resource_limit"
                if not report.get("stopped_reason") or str(exc) == "disk_floor_reached":
                    report["stopped_reason"] = str(exc)
            except Exception as exc:
                row = {"cnpj": path.stem, "document_id": ident, "status": "ocr_failed", "reason": type(exc).__name__}
            report["documents"].append(row)
            report["pages_recognized_this_run"] = recovery.pages_used
            atomic_json(output, public_document_payload(report))
        if report["state"] != "resource_limit":
            report["state"] = "processed_with_failures" if any(row["status"] == "ocr_failed" for row in report["documents"]) else "complete"
        report["completed_at"] = utc_now()
        atomic_json(output, public_document_payload(report))
    print(f"OCR {report['state']}: {len(selected)} documents; {recovery.pages_used} pages", flush=True)
    if report["state"] == "resource_limit":
        parser.exit(2, "OCR resource limit; checkpoints and unreadable-source states retained\n")
    if report["state"] == "processed_with_failures":
        parser.exit(1, "Local OCR errors; inspect qa/ocr_recovery.json\n")


if __name__ == "__main__":
    main()
