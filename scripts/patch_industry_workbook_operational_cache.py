"""Repair only the operational formula caches and monetary column widths.

ArtifactTool can cache an Excel comparison with an empty string as empty when
the input is numeric zero.  G/H remain the reported source values.  AC/AD keep
their original formulas; this module writes their mathematical cached results.
All unrelated ZIP parts and worksheet cells are preserved.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import posixpath
import re
from xml.etree import ElementTree as ET
from xml.sax.saxutils import quoteattr
from zipfile import ZipFile


SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SHEET_NAME = "Base competência-CNPJ"
MIN_MONETARY_WIDTH = Decimal(26)
MIN_PORTFOLIO_WIDTH = Decimal(32)
HEADERS = {
    "G4": "Carteira DC",
    "H4": "Inadimplência reportada",
    "AC4": "Ajustado (fórmula)",
    "AD4": "Excesso (fórmula)",
}
CELL_RE = re.compile(
    rb'<(?P<tag>(?:[\w.-]+:)?c)\b(?P<attrs>[^>]*\br="(?P<address>(?:AC|AD)\d+)"[^>]*)>(?P<body>.*?)</(?P=tag)>',
    re.DOTALL,
)
COL_RE = re.compile(rb"<(?:[\w.-]+:)?col\b[^>]*(?:/>|>\s*</(?:[\w.-]+:)?col>)")
ZERO = Decimal(0)


def _tag(name: str) -> str:
    return f"{{{SHEET_NS}}}{name}"


def _strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.itertext()) for node in root.findall(_tag("si"))]


def _text(cell: ET.Element | None, strings: list[str]) -> str:
    if cell is None:
        return ""
    if cell.attrib.get("t") == "s":
        return strings[int(cell.findtext(_tag("v")) or "-1")]
    if cell.attrib.get("t") == "inlineStr":
        node = cell.find(_tag("is"))
        return "" if node is None else "".join(node.itertext())
    return cell.findtext(_tag("v")) or ""


def _number(cell: ET.Element | None, address: str) -> Decimal | None:
    if cell is None:
        return None
    if cell.find(_tag("f")) is not None:
        raise ValueError(f"Reported source {address} must not contain a formula")
    value = cell.findtext(_tag("v"))
    if value in {None, ""} and cell.attrib.get("t") in {None, "n", "str"}:
        return None
    if cell.attrib.get("t") not in {None, "n"}:
        raise ValueError(f"Reported source {address} is not numeric")
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError) as error:
        raise ValueError(f"Invalid numeric source {address}") from error
    if not number.is_finite():
        raise ValueError(f"Nonfinite numeric source {address}")
    return number


def _model(archive: ZipFile) -> tuple[str, bytes, ET.Element, dict[str, tuple[ET.Element, Decimal | None]]]:
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError("Duplicate workbook ZIP parts")
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    matches = [item for item in workbook.findall(f"{_tag('sheets')}/{_tag('sheet')}") if item.attrib.get("name") == SHEET_NAME]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {SHEET_NAME} sheet")
    relationship_id = matches[0].attrib[f"{{{REL_NS}}}id"]
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = [item for item in relationships if item.attrib.get("Id") == relationship_id]
    if len(targets) != 1 or targets[0].attrib.get("TargetMode") == "External":
        raise ValueError("Invalid operational worksheet relationship")
    target = targets[0].attrib["Target"]
    part = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
    raw = archive.read(part)
    worksheet = ET.fromstring(raw)
    strings = _strings(archive)
    expected: dict[str, tuple[ET.Element, Decimal | None]] = {}
    cells: dict[str, ET.Element] = {}
    for row in worksheet.findall(f"{_tag('sheetData')}/{_tag('row')}"):
        for cell in row.findall(_tag("c")):
            address = cell.attrib["r"]
            if address in cells:
                raise ValueError(f"Duplicate worksheet cell {address}")
            cells[address] = cell
    for address, label in HEADERS.items():
        if _text(cells.get(address), strings) != label:
            raise ValueError(f"Unexpected operational header {address}")
    for row in worksheet.findall(f"{_tag('sheetData')}/{_tag('row')}"):
        number = int(row.attrib["r"])
        if number < 5 or not (_text(cells.get(f"A{number}"), strings) or _text(cells.get(f"B{number}"), strings)):
            continue
        portfolio = _number(cells.get(f"G{number}"), f"G{number}")
        delinquency = _number(cells.get(f"H{number}"), f"H{number}")
        adjusted = None if portfolio is None or delinquency is None else min(max(delinquency, ZERO), max(portfolio, ZERO))
        excess = None if portfolio is None or delinquency is None else max(delinquency - max(portfolio, ZERO), ZERO)
        formulas = {
            f"AC{number}": f'IF(AND(G{number}<>"",H{number}<>""),MIN(MAX(H{number},0),MAX(G{number},0)),"")',
            f"AD{number}": f'IF(AC{number}="","",MAX(H{number}-AC{number},0))',
        }
        for address, value in [(f"AC{number}", adjusted), (f"AD{number}", excess)]:
            cell = cells.get(address)
            if cell is None or cell.findtext(_tag("f")) != formulas[address]:
                raise ValueError(f"Unexpected operational formula {address}")
            if len(cell.findall(_tag("v"))) > 1:
                raise ValueError(f"Duplicate formula cache {address}")
            expected[address] = (cell, value)
    if not expected:
        raise ValueError("Operational worksheet has no formula rows")
    formula_addresses = {address for address, cell in cells.items() if re.fullmatch(r"(?:AC|AD)\d+", address) and cell.find(_tag("f")) is not None}
    if formula_addresses != set(expected):
        raise ValueError("Operational formulas outside the documented rows")
    return part, raw, worksheet, expected


def _cache_matches(cell: ET.Element, expected: Decimal | None) -> bool:
    value = cell.findtext(_tag("v"))
    if expected is None:
        return value in {None, ""}
    if cell.attrib.get("t") not in {None, "n"} or value in {None, ""}:
        return False
    try:
        actual = Decimal(value)
    except InvalidOperation:
        return False
    if expected == ZERO:
        return actual.is_finite() and actual == ZERO
    tolerance = max(Decimal("0.000001"), abs(expected) * Decimal("0.000000000001"))
    return actual.is_finite() and abs(actual - expected) <= tolerance


def _required_widths(expected: dict[str, tuple[ET.Element, Decimal | None]]) -> dict[int, Decimal]:
    result = {6: MIN_PORTFOLIO_WIDTH, 7: MIN_PORTFOLIO_WIDTH, 8: MIN_PORTFOLIO_WIDTH, 29: MIN_MONETARY_WIDTH, 30: MIN_MONETARY_WIDTH}
    for address, (_, value) in expected.items():
        if value is not None:
            column = 29 if address.startswith("AC") else 30
            result[column] = max(result[column], Decimal(len(f"R$ {value:,.2f}") + 2))
    return result


def _column_width(worksheet: ET.Element, column: int) -> Decimal:
    matches = [node for node in worksheet.findall(f"{_tag('cols')}/{_tag('col')}") if int(node.attrib["min"]) <= column <= int(node.attrib["max"])]
    if len(matches) > 1:
        raise ValueError(f"Overlapping column definitions at {column}")
    if matches:
        return Decimal(matches[0].attrib.get("width", "8.43"))
    default = worksheet.find(_tag("sheetFormatPr"))
    return Decimal(default.attrib.get("defaultColWidth", "8.43") if default is not None else "8.43")


def _serialized_empty(tag: bytes, attrs: dict[str, str]) -> bytes:
    return b"<" + tag + b" " + " ".join(f"{key}={quoteattr(value)}" for key, value in attrs.items()).encode() + b" />"


def _patch_widths(raw: bytes, worksheet: ET.Element, required: dict[int, Decimal]) -> bytes:
    missing = {column for column, width in required.items() if _column_width(worksheet, column) < width}
    if not missing:
        return raw
    region = re.search(rb"<(?P<tag>(?:[\w.-]+:)?cols)\b[^>]*>(?P<body>.*?)</(?P=tag)>", raw, re.DOTALL)
    if region is None:
        raise ValueError("Operational monetary columns require an explicit cols block")
    prefix = region.group("tag")[:-4]
    pieces: list[tuple[int, bytes]] = []
    found: set[int] = set()
    nodes = worksheet.findall(f"{_tag('cols')}/{_tag('col')}")
    matches = list(COL_RE.finditer(region.group("body")))
    if len(nodes) != len(matches):
        raise ValueError("Unsupported operational column XML")
    for node, match in zip(nodes, matches):
        lower, upper = int(node.attrib["min"]), int(node.attrib["max"])
        affected = sorted(column for column in missing if lower <= column <= upper)
        if not affected:
            pieces.append((lower, match.group()))
            continue
        start = lower
        for column in affected:
            if start < column:
                attrs = {**node.attrib, "min": str(start), "max": str(column - 1)}
                pieces.append((start, _serialized_empty(prefix + b"col", attrs)))
            attrs = {**node.attrib, "min": str(column), "max": str(column), "width": str(required[column]), "customWidth": "1"}
            pieces.append((column, _serialized_empty(prefix + b"col", attrs)))
            found.add(column)
            start = column + 1
        if start <= upper:
            attrs = {**node.attrib, "min": str(start), "max": str(upper)}
            pieces.append((start, _serialized_empty(prefix + b"col", attrs)))
    for column in missing - found:
        attrs = {"min": str(column), "max": str(column), "width": str(required[column]), "customWidth": "1"}
        pieces.append((column, _serialized_empty(prefix + b"col", attrs)))
    body = b"".join(value for _, value in sorted(pieces, key=lambda item: item[0]))
    return raw[:region.start("body")] + body + raw[region.end("body"):]


def _patch_sheet(raw: bytes, worksheet: ET.Element, expected: dict[str, tuple[ET.Element, Decimal | None]]) -> bytes:
    visited: set[str] = set()

    def replace(match: re.Match[bytes]) -> bytes:
        address = match.group("address").decode()
        if address not in expected:
            return match.group()
        if address in visited:
            raise ValueError(f"Duplicate operational cache XML {address}")
        visited.add(address)
        cell, value = expected[address]
        if _cache_matches(cell, value):
            return match.group()
        tag, attrs, body = match.group("tag", "attrs", "body")
        kind = b"str" if value is None else b"n"
        if re.search(rb'\bt="[^"]*"', attrs):
            attrs = re.sub(rb'\bt="[^"]*"', b't="' + kind + b'"', attrs, count=1)
        else:
            attrs += b' t="' + kind + b'"'
        prefix = tag[:-1]
        cached = b"<" + prefix + b"v/>" if value is None else b"<" + prefix + b"v>" + format(value, "f").encode() + b"</" + prefix + b"v>"
        value_re = re.compile(rb"<(?:[\w.-]+:)?v\b[^>]*(?:/>|>.*?</(?:[\w.-]+:)?v>)", re.DOTALL)
        if value_re.search(body):
            body = value_re.sub(lambda _: cached, body, count=1)
        else:
            formula_re = re.compile(rb"<(?:[\w.-]+:)?f\b[^>]*>.*?</(?:[\w.-]+:)?f>", re.DOTALL)
            formula = formula_re.search(body)
            if formula is None:
                raise ValueError(f"Unsupported formula XML {address}")
            body = body[:formula.end()] + cached + body[formula.end():]
        return b"<" + tag + attrs + b">" + body + b"</" + tag + b">"

    changed = CELL_RE.sub(replace, raw)
    if visited != set(expected):
        raise ValueError("Operational cache XML does not cover every formula")
    return _patch_widths(changed, worksheet, _required_widths(expected))


def _patch_calc(raw: bytes) -> bytes:
    root = ET.fromstring(raw)
    current = root.find(_tag("calcPr"))
    settings = {"calcMode": "auto", "fullCalcOnLoad": "1", "forceFullCalc": "1"}
    if current is not None and all(current.attrib.get(key) == value for key, value in settings.items()):
        return raw
    if current is not None:
        pattern = re.compile(rb"<(?P<tag>(?:[\w.-]+:)?calcPr)\b[^>]*(?:/>|>\s*</(?P=tag)>)")
        match = pattern.search(raw)
        if match is None:
            raise ValueError("Unsupported calcPr XML")
        return raw[:match.start()] + _serialized_empty(match.group("tag"), {**current.attrib, **settings}) + raw[match.end():]
    closing = re.search(rb"</(?P<tag>(?:[\w.-]+:)?workbook)>\s*$", raw)
    if closing is None:
        raise ValueError("Unsupported workbook XML")
    prefix = closing.group("tag")[:-8]
    later = re.search(rb"<(?:[\w.-]+:)?(?:oleSize|customWorkbookViews|pivotCaches|smartTagPr|smartTagTypes|webPublishing|fileRecoveryPr|webPublishObjects|extLst)\b", raw)
    position = later.start() if later else closing.start()
    return raw[:position] + _serialized_empty(prefix + b"calcPr", settings) + raw[position:]


def validate_workbook_caches(payload: bytes) -> None:
    """Fail closed on a stale cache, altered formula or unusable monetary width."""
    with ZipFile(BytesIO(payload)) as archive:
        _, _, worksheet, expected = _model(archive)
        for address, (cell, value) in expected.items():
            if not _cache_matches(cell, value):
                raise ValueError(f"Operational formula cache disagrees with G/H at {address}")
        for column, width in _required_widths(expected).items():
            if _column_width(worksheet, column) < width:
                raise ValueError(f"Operational monetary column {column} is too narrow")
        calc = ET.fromstring(archive.read("xl/workbook.xml")).find(_tag("calcPr"))
        if calc is None or any(calc.attrib.get(key) != value for key, value in {"calcMode": "auto", "fullCalcOnLoad": "1", "forceFullCalc": "1"}.items()):
            raise ValueError("Operational workbook must recalculate automatically")


def patch_workbook_bytes(payload: bytes) -> bytes:
    """Return a repaired copy; no file is modified by this API."""
    with ZipFile(BytesIO(payload)) as source:
        part, raw, worksheet, expected = _model(source)
        changed = {part: _patch_sheet(raw, worksheet, expected), "xl/workbook.xml": _patch_calc(source.read("xl/workbook.xml"))}
        if all(source.read(name) == value for name, value in changed.items()):
            validate_workbook_caches(payload)
            return payload
        output = BytesIO()
        with ZipFile(output, "w") as destination:
            destination.comment = source.comment
            for info in source.infolist():
                destination.writestr(info, changed.get(info.filename, source.read(info.filename)))
    result = output.getvalue()
    validate_workbook_caches(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, help="Write a corrected copy at this explicit path")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    payload = args.input.read_bytes()
    if args.validate_only:
        validate_workbook_caches(payload)
    else:
        if args.output is None or args.output.resolve() == args.input.resolve():
            parser.error("--output must identify a separate file")
        args.output.write_bytes(patch_workbook_bytes(payload))


if __name__ == "__main__":
    main()
