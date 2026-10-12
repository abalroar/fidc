"""Prepare a download once for the current analytical context, on request."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
import pickle
from pathlib import Path
from threading import Lock
from typing import Any, Callable, MutableMapping

import streamlit as st


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedDownload:
    data: bytes
    warnings: tuple[str, ...] = ()


def download_context_signature(*values: Any, source_paths: tuple[Path, ...] = ()) -> str:
    """Hash full loaded values and the version of files used by the producers.

    No financial transformation or sampled DataFrame hash is used here. The
    input values remain untouched; the digest only controls session downloads.
    File versions include nanosecond timestamps, size and path. Missing sources
    are included so that a subsequently available source invalidates the file.
    """
    source_versions = []
    for path in sorted(source_paths):
        try:
            info = path.stat()
        except FileNotFoundError:
            version = None
        else:
            version = (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        source_versions.append((str(path), version))
    payload = pickle.dumps((values, source_versions), protocol=5)
    return hashlib.sha256(payload).hexdigest()


def current_download_store(
    state: MutableMapping[str, Any], *, namespace: str, signature: str,
) -> dict[str, PreparedDownload]:
    """Discard the previous analytical context before showing any file."""
    key = f"prepared_downloads::{namespace}"
    record = state.get(key)
    if not isinstance(record, dict) or record.get("signature") != signature:
        record = {"signature": signature, "files": {}}
        state[key] = record
    return record["files"]


def prepare_download(
    store: dict[str, PreparedDownload], *, artifact: str,
    producer: Callable[[], bytes | PreparedDownload],
) -> PreparedDownload:
    """Run only the requested producer and keep a successful result.

    A failed refresh removes the previous artifact, leaving the next request
    free to retry. It never presents a previous file as the successful refresh.
    """
    store.pop(artifact, None)
    result = producer()
    prepared = result if isinstance(result, PreparedDownload) else PreparedDownload(result)
    if not prepared.data:
        raise ValueError("O produtor retornou um arquivo vazio.")
    store[artifact] = prepared
    return prepared


def render_on_demand_download(
    *, store: dict[str, PreparedDownload], namespace: str, artifact: str,
    label: str, file_name: str, mime: str,
    producer: Callable[[], bytes | PreparedDownload],
    help_text: str | None = None, primary: bool = False,
) -> None:
    prepared = store.get(artifact)
    prepare_label = f"Preparar novamente: {label}" if prepared is not None else f"Preparar: {label}"
    if st.button(
        prepare_label,
        key=f"prepare_download::{namespace}::{artifact}",
        help=help_text,
        type="primary" if primary and prepared is None else "secondary",
        width="stretch",
    ):
        try:
            with st.spinner(f"Preparando {label}…"):
                prepared = prepare_download(store, artifact=artifact, producer=producer)
        except Exception:  # noqa: BLE001 — recover without losing the analysis.
            logger.exception("Failed to prepare download %s/%s", namespace, artifact)
            prepared = None
            st.error("Não foi possível preparar este arquivo. Tente novamente.")
    if prepared is None:
        return
    st.download_button(
        f"Baixar: {label}", data=prepared.data, file_name=file_name,
        mime=mime, key=f"download::{namespace}::{artifact}",
        help=help_text, type="primary" if primary else "secondary",
        width="stretch", on_click="ignore",
    )
    for warning in prepared.warnings:
        st.caption(f"Parte não incluída na apresentação: {warning}")


def render_native_deferred_download(
    *, store: dict[str, PreparedDownload], namespace: str, artifact: str,
    label: str, file_name: str, mime: str, producer: Callable[[], bytes],
    help_text: str | None = None,
) -> None:
    """One-click native download for byte-only producers with no export warnings.

    Streamlit 1.56 calls the producer in its download worker. The closure uses
    only ordinary Python state, so it issues no Streamlit command in that worker.
    Presentations with partial-export warnings keep the synchronous preparation
    flow, which shows those warnings before the analyst downloads the file.
    """
    lock = Lock()

    def data() -> bytes:
        with lock:
            prepared = store.get(artifact)
            if prepared is None:
                payload = producer()
                if not isinstance(payload, bytes) or not payload:
                    raise ValueError("O produtor deve retornar um arquivo válido em bytes.")
                prepared = PreparedDownload(payload)
                store[artifact] = prepared
            return prepared.data

    st.download_button(
        label, data=data, file_name=file_name, mime=mime,
        key=f"download::{namespace}::{artifact}",
        help=help_text, type="secondary", width="stretch", on_click="ignore",
    )
