"""Lossless grouping of documentary columns for the portfolio presentation."""
from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd

from services.fund_name_display import short_fund_name
from services.presentation_text import document_comparison_value


DOCUMENT_GROUPING_CAPTION = "Colunas idênticas agrupadas; composição de cada grupo nas notas."


def _short_label(value: object) -> str:
    text = str(value)
    # Canonical aliases are shared with the page. Unknown names stay whole.
    return short_fund_name(text, max_length=max(28, len(text))) or text


def _fund_identity(column: object, funds: tuple[Mapping[str, str], ...]) -> str:
    label = str(column)
    matches = []
    for fund in funds:
        aliases = {str(fund.get(key) or "") for key in ("name", "short_name", "cnpj")}
        aliases.add(f"{fund.get('short_name') or fund.get('name')} ({fund.get('cnpj')})")
        if label in aliases:
            matches.append(fund)
    if len(matches) != 1:
        # Ambiguous aliases are kept verbatim; identity is never guessed.
        return label
    fund = matches[0]
    legal_name = str(fund.get("name") or label)
    cnpj = str(fund.get("cnpj") or "não informado")
    return f"{label} — {legal_name} · CNPJ {cnpj}"


def compact_document_frame(
    frame: pd.DataFrame, *, funds: Iterable[Mapping[str, str]] = (),
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Group only complete columns equal in the existing public representation.

    The criterion, row order and every distinct value vector are retained.
    Zero remains ``0`` and missing answers retain the existing ``-`` display.
    The second result maps each visible group to all original fund columns.
    """
    output = frame.copy(deep=True)
    if frame.empty or len(frame.columns) <= 1:
        return output, ()
    for index in range(1, len(output.columns)):
        output.isetitem(index, output.iloc[:, index].map(document_comparison_value))
    if len(output.columns) == 2:
        return output, ()

    fund_records = tuple(funds)
    groups: dict[tuple[str, ...], list[int]] = {}
    for index in range(1, len(output.columns)):
        key = tuple(output.iloc[:, index].tolist())
        groups.setdefault(key, []).append(index)

    columns = [output.iloc[:, 0].copy()]
    labels = [output.columns[0]]
    mappings = []
    used_labels = set()
    for indices in groups.values():
        original = [output.columns[index] for index in indices]
        if len(indices) == len(output.columns) - 1:
            base_label = "Todos os fundos"
        elif len(indices) <= 2:
            base_label = " / ".join(_short_label(column) for column in original)
        else:
            base_label = f"{len(indices)} fundos"
        label = base_label
        suffix = 2
        while label in used_labels:
            label = f"{base_label} ({suffix})"
            suffix += 1
        used_labels.add(label)
        labels.append(label)
        columns.append(output.iloc[:, indices[0]].copy())
        identities = [_fund_identity(column, fund_records) for column in original]
        mappings.append(f"{label} → " + "; ".join(identities))

    compact = pd.concat(columns, axis=1)
    compact.columns = labels
    return compact, tuple(mappings)


__all__ = ["DOCUMENT_GROUPING_CAPTION", "compact_document_frame"]
