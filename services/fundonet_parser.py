from __future__ import annotations

from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

import pandas as pd

from services.fundonet_errors import DocumentParseError


def flatten_xml_contas(xml_content: bytes, doc_id: int) -> pd.DataFrame:
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise DocumentParseError(f"XML inválido para documento {doc_id}: {exc}") from exc

    rows: List[Dict[str, Any]] = []

    def walk(node: ET.Element, trail: List[str], attrs: Dict[str, str]) -> None:
        tag = _strip_ns(node.tag)
        current_attrs = dict(attrs)
        for k, v in node.attrib.items():
            current_attrs[_strip_ns(k)] = v

        ident = (
            current_attrs.get("codigoConta")
            or current_attrs.get("codigo")
            or current_attrs.get("codConta")
            or ""
        )
        label = (
            current_attrs.get("descricaoConta")
            or current_attrs.get("descricao")
            or current_attrs.get("nomeConta")
            or current_attrs.get("nome")
            or tag
        )

        path_chunk = f"{ident} - {label}".strip(" -")
        next_trail = trail + [path_chunk]

        text = (node.text or "").strip()
        numeric = _parse_br_number(text)
        if numeric is not None:
            rows.append(
                {
                    "documento_id": doc_id,
                    "conta_codigo": ident or None,
                    "conta_descricao": label,
                    "conta_caminho": " > ".join(next_trail),
                    "valor": numeric,
                }
            )

        for child in list(node):
            walk(child, next_trail, current_attrs)

    walk(root, [], {})
    return pd.DataFrame(rows)


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_br_number(value: str) -> Optional[float]:
    if not value:
        return None
    normalized = value.replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None
