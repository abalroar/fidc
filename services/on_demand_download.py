"""Prepare a download once for the current analytical context, on request."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import hashlib
from io import BytesIO
import logging
import pickle
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Callable, MutableMapping

import streamlit as st


logger = logging.getLogger(__name__)

# One preparation at a time per process. Streamlit Cloud gives all sessions one
# shared memory limit, so two clicks (or two sessions) building a deck at once
# add their peaks and can kill the app. Reentrant in case a producer nests.
_PREPARATION_LOCK = RLock()


@dataclass(frozen=True)
class PreparedDownload:
    data: bytes
    warnings: tuple[str, ...] = ()


class _DownloadContextPickler(pickle.Pickler):
    """Describe dataclass values without depending on a live class identity.

    Streamlit can keep cached instances after reloading their defining module.
    Ordinary pickle rejects those instances because the module now exposes a
    different class object. This representation is only hashed, never loaded.
    The builtin tuple reducer also visits nested dataclasses in tables/metadata.
    """

    def reducer_override(self, value: Any) -> Any:
        if isinstance(value, type) or not is_dataclass(value):
            return NotImplemented
        cls = type(value)
        field_values = tuple((field.name, getattr(value, field.name)) for field in fields(value))
        field_names = {name for name, _ in field_values}
        extra_values = {
            name: item for name, item in getattr(value, "__dict__", {}).items()
            if name not in field_names
        }
        return tuple, (("dataclass", cls.__module__, cls.__qualname__, field_values, extra_values),)


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
    payload = BytesIO()
    _DownloadContextPickler(payload, protocol=5).dump((values, source_versions))
    return hashlib.sha256(payload.getvalue()).hexdigest()


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


def discard_other_download_stores(
    state: MutableMapping[str, Any], *, family: str, namespace: str,
) -> None:
    """Drop files prepared for other contexts of the same family.

    Prepared decks are megabytes each; switching portfolios would otherwise
    keep every portfolio's files in the session until it ends. ``namespace``
    and its sub-namespaces (``namespace::…``) are kept.
    """
    family_prefix = f"prepared_downloads::{family}"
    current = f"prepared_downloads::{namespace}"
    stale = [
        key for key in list(state.keys())
        if isinstance(key, str) and key.startswith(family_prefix)
        and key != current and not key.startswith(f"{current}::")
    ]
    for key in stale:
        del state[key]


def prepare_download(
    store: dict[str, PreparedDownload], *, artifact: str,
    producer: Callable[[], bytes | PreparedDownload],
) -> PreparedDownload:
    """Run only the requested producer and keep a successful result.

    A failed refresh removes the previous artifact, leaving the next request
    free to retry. It never presents a previous file as the successful refresh.
    """
    store.pop(artifact, None)
    with _PREPARATION_LOCK:
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
        except Exception as exc:  # noqa: BLE001 — recover without losing the analysis.
            logger.exception("Failed to prepare download %s/%s", namespace, artifact)
            prepared = None
            st.error("Não foi possível preparar este arquivo. Tente novamente.")
            from services.dashboard_ui import diagnostics_enabled

            if diagnostics_enabled():
                st.caption(f"Diagnóstico: {type(exc).__name__}: {exc}")
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
                with _PREPARATION_LOCK:
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
