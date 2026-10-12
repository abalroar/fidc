from unittest.mock import Mock, patch

import pytest

from services.on_demand_download import (
    current_download_store, render_native_deferred_download,
)


def _register(store, producer):
    with patch("services.on_demand_download.st.download_button") as download:
        render_native_deferred_download(
            store=store, namespace="carteira", artifact="xlsx", label="Resumo (Excel)",
            file_name="resumo.xlsx", mime="application/xlsx", producer=producer,
        )
    assert download.call_args.kwargs["on_click"] == "ignore"
    return download.call_args.kwargs["data"]


def test_native_download_is_deferred_and_invalidates_with_the_selected_context():
    state = {}
    producer = Mock(return_value=b"selected-data")
    data = _register(current_download_store(state, namespace="carteira", signature="A"), producer)
    producer.assert_not_called()
    assert data() == data() == b"selected-data"
    producer.assert_called_once()
    revised = Mock(return_value=b"revised-data")
    data = _register(current_download_store(state, namespace="carteira", signature="B"), revised)
    revised.assert_not_called()
    assert data() == b"revised-data"


def test_native_download_failure_can_retry_without_serving_previous_context():
    store = {}
    producer = Mock(side_effect=[RuntimeError("failed"), b"recovered"])
    data = _register(store, producer)
    with pytest.raises(RuntimeError):
        data()
    assert not store
    assert data() == b"recovered"
