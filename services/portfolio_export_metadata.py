"""Append portfolio context without rewriting existing spreadsheet/CSV parts.

These wrappers are called only by the saved-portfolio flow. Shared producers
continue to return their original payloads for every other consumer.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from io import BytesIO
import json
import math
import re
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOCUMENT_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
_CONTEXT_SHEET = "Contexto da exportação"
_CONTEXT_JSON = "contexto_exportacao.json"


def _context_value(value: object) -> object:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _context_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_context_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "item"):
        return _context_value(value.item())
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _xml(payload: bytes):
    # Existing namespace declarations, including Office compatibility prefixes,
    # remain intact when package declarations are extended.
    return etree.fromstring(payload, etree.XMLParser(resolve_entities=False, no_network=True))


def _xml_bytes(element) -> bytes:
    return etree.tostring(element, encoding="UTF-8", xml_declaration=True)


def _context_styles(package: ZipFile) -> tuple[int, int]:
    """Reuse existing plain/wrapping/header styles; never edit styles.xml."""
    if "xl/styles.xml" not in package.namelist():
        return 0, 0
    styles = _xml(package.read("xl/styles.xml"))
    fonts = styles.find(f"{{{_MAIN}}}fonts")
    xfs = styles.find(f"{{{_MAIN}}}cellXfs")
    if fonts is None or xfs is None:
        return 0, 0
    body = header = 0
    for index, xf in enumerate(xfs):
        if xf.get("numFmtId", "0") != "0":
            continue
        font = fonts[int(xf.get("fontId", "0"))]
        bold = font.find(f"{{{_MAIN}}}b") is not None
        if bold and not header:
            header = index
        alignment = xf.find(f"{{{_MAIN}}}alignment")
        if not bold and not body and xf.get("fillId", "0") == "0" and alignment is not None and alignment.get("wrapText") in {"1", "true"}:
            body = index
    return body, header


def _context_worksheet(context: Mapping[str, object], styles: tuple[int, int]) -> bytes:
    body_style, header_style = styles
    sheet = etree.Element(f"{{{_MAIN}}}worksheet", nsmap={None: _MAIN})
    etree.SubElement(sheet, f"{{{_MAIN}}}dimension", ref=f"A1:B{len(context) + 1}")
    view = etree.SubElement(etree.SubElement(sheet, f"{{{_MAIN}}}sheetViews"), f"{{{_MAIN}}}sheetView", workbookViewId="0")
    etree.SubElement(view, f"{{{_MAIN}}}pane", ySplit="1", topLeftCell="A2", activePane="bottomLeft", state="frozen")
    etree.SubElement(view, f"{{{_MAIN}}}selection", pane="bottomLeft", activeCell="A2", sqref="A2")
    etree.SubElement(sheet, f"{{{_MAIN}}}sheetFormatPr", defaultRowHeight="15")
    columns = etree.SubElement(sheet, f"{{{_MAIN}}}cols")
    etree.SubElement(columns, f"{{{_MAIN}}}col", min="1", max="1", width="34", customWidth="1")
    etree.SubElement(columns, f"{{{_MAIN}}}col", min="2", max="2", width="112", customWidth="1")
    rows = etree.SubElement(sheet, f"{{{_MAIN}}}sheetData")
    values = [("Campo", "Valor"), *[(str(key), _context_value(value)) for key, value in context.items()]]
    for index, row_values in enumerate(values, 1):
        line_count = max(max(1, math.ceil(len(str(value or "")) / width)) for value, width in zip(row_values, (34, 112)))
        row = etree.SubElement(rows, f"{{{_MAIN}}}row", r=str(index), ht=str(min(409, max(20, line_count * 15))), customHeight="1")
        for column, value in zip(("A", "B"), row_values):
            cell = etree.SubElement(row, f"{{{_MAIN}}}c", r=f"{column}{index}", s=str(header_style if index == 1 else body_style))
            if value is None:
                continue
            if isinstance(value, bool):
                cell.set("t", "b")
                etree.SubElement(cell, f"{{{_MAIN}}}v").text = "1" if value else "0"
            elif isinstance(value, (int, float)):
                cell.set("t", "n")
                etree.SubElement(cell, f"{{{_MAIN}}}v").text = str(value)
            else:
                text = json.dumps(value, ensure_ascii=False, allow_nan=False) if isinstance(value, (dict, list)) else str(value)
                if len(text) > 32767:
                    raise ValueError("Um campo do contexto excede o limite de texto do Excel; nenhum conteúdo foi truncado.")
                cell.set("t", "inlineStr")
                run = etree.SubElement(etree.SubElement(cell, f"{{{_MAIN}}}is"), f"{{{_MAIN}}}t")
                run.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                run.text = text
    etree.SubElement(sheet, f"{{{_MAIN}}}autoFilter", ref=f"A1:B{len(values)}")
    return _xml_bytes(sheet)


def with_xlsx_export_context(payload: bytes, context: Mapping[str, object]) -> bytes:
    """Append one metadata sheet; original cells, charts and formats stay intact."""
    with ZipFile(BytesIO(payload)) as source:
        workbook = _xml(source.read("xl/workbook.xml"))
        sheets = workbook.find(f"{{{_MAIN}}}sheets")
        if sheets is None:
            raise ValueError("A pasta de trabalho não contém uma lista de abas válida.")
        if any(sheet.get("name") == _CONTEXT_SHEET for sheet in sheets):
            raise ValueError("A pasta de trabalho já contém Contexto da exportação; a aba existente não foi sobrescrita.")
        relations = _xml(source.read("xl/_rels/workbook.xml.rels"))
        content_types = _xml(source.read("[Content_Types].xml"))
        names = set(source.namelist())
        counters = [int(match.group(1)) for name in names if (match := re.fullmatch(r"xl/worksheets/sheet(\d+)\.xml", name))]
        number = max(counters, default=0) + 1
        part = f"xl/worksheets/sheet{number}.xml"
        relation_ids = {relation.get("Id") for relation in relations}
        relation_number = 1
        while f"rId{relation_number}" in relation_ids:
            relation_number += 1
        relationship = f"rId{relation_number}"
        etree.SubElement(relations, f"{{{_PACKAGE_REL}}}Relationship", Id=relationship, Type=f"{_DOCUMENT_REL}/worksheet", Target=f"worksheets/sheet{number}.xml")
        sheet_id = max((int(sheet.get("sheetId")) for sheet in sheets), default=0) + 1
        added = etree.SubElement(sheets, f"{{{_MAIN}}}sheet", nsmap={"r": _DOCUMENT_REL}, name=_CONTEXT_SHEET, sheetId=str(sheet_id))
        added.set(f"{{{_DOCUMENT_REL}}}id", relationship)
        etree.SubElement(content_types, f"{{{_CONTENT_TYPES}}}Override", PartName="/" + part, ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
        replacements = {
            "xl/workbook.xml": _xml_bytes(workbook),
            "xl/_rels/workbook.xml.rels": _xml_bytes(relations),
            "[Content_Types].xml": _xml_bytes(content_types),
        }
        worksheet = _context_worksheet(context, _context_styles(source))
        output = BytesIO()
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as target:
            for info in source.infolist():
                target.writestr(info, replacements.get(info.filename, source.read(info.filename)))
            target.writestr(part, worksheet)
        return output.getvalue()


def with_csv_export_context(payload: bytes, context: Mapping[str, object]) -> bytes:
    """Add context JSON; every original CSV member remains byte-for-byte equal."""
    metadata = json.dumps(_context_value(context), ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    with ZipFile(BytesIO(payload)) as source:
        if _CONTEXT_JSON in source.namelist():
            raise ValueError("O arquivo já contém contexto_exportacao.json; o conteúdo existente não foi sobrescrito.")
        output = BytesIO()
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as target:
            for info in source.infolist():
                target.writestr(info, source.read(info.filename))
            target.writestr(_CONTEXT_JSON, metadata)
        return output.getvalue()


__all__ = ["with_xlsx_export_context", "with_csv_export_context"]
