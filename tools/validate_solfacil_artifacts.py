#!/usr/bin/env python3
"""Validate the auditable Solfacil CSV, XLSX, and PPTX artifact contract.

The validator is deliberately read-only and uses only Python's standard
library.  By default it locates the dated artifacts under ``outputs/solfacil``.
If the matching PPTX has not been built yet, PPTX checks are reported as
skipped; pass ``--require-pptx`` to make its absence an error.
"""

from __future__ import annotations

import argparse
import colorsys
import csv
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


EXPECTED_CSVS = (
    "00_painel.csv",
    "01_veiculos.csv",
    "02_series.csv",
    "03_elegibilidade.csv",
    "04_concentracao.csv",
    "05_prazos_wam.csv",
    "06_waterfall.csv",
    "06b_waterfall_visual.csv",
    "07_subordinada.csv",
    "08_pdd.csv",
    "09_eventos.csv",
    "10_subscritores.csv",
    "11_matriz_fidc_cri.csv",
    "11b_cessoes.csv",
    "12_custo_captacao.csv",
    "13_cronograma_pagamentos.csv",
    "14_antes_depois.csv",
    "15_fidc_vs_cri.csv",
    "16_conflitos.csv",
    "17_fontes.csv",
    "18_metodologia.csv",
    "19_glossario.csv",
)

EXPECTED_SHEETS = (
    "00_Painel",
    "01_Veiculos",
    "02_Series",
    "03_Elegibilidade",
    "04_Concentracao",
    "05_Prazos_WAM",
    "06_Waterfall",
    "06b_Waterfall_Visual",
    "07_Subordinada",
    "08_PDD",
    "09_Eventos",
    "10_Subscritores",
    "11_Matriz_FIDC_CRI",
    "11b_Cessoes",
    "12_Custo_Captacao",
    "13_Cronograma_Pagamentos",
    "14_Antes_Depois",
    "15_FIDC_vs_CRI",
    "16_Conflitos",
    "17_Fontes",
    "18_Metodologia",
    "19_Glossario",
)

EXPECTED_TABLES = tuple(f"tbl_{sheet}" for sheet in EXPECTED_SHEETS)

XML_SLIDE_RE = re.compile(r"^ppt/slides/slide\d+\.xml$")
XML_WORKSHEET_RE = re.compile(r"^xl/worksheets/sheet\d+\.xml$")
XML_XLSX_TABLE_RE = re.compile(r"^xl/tables/table\d+\.xml$")
XML_XLSX_CHART_RE = re.compile(r"^xl/(?:charts|drawings/charts)/chart\d+\.xml$")
XML_PPTX_CHART_RE = re.compile(r"^ppt/(?:charts|slides/charts)/chart\d+\.xml$")
XML_NOTES_RE = re.compile(r"^ppt/notesSlides/notesSlide\d+\.xml$")

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"

COLOR_SCAN_PREFIXES = (
    "ppt/slides/",
    "ppt/slideMasters/",
    "ppt/slideLayouts/",
    "ppt/charts/",
    "ppt/diagrams/",
)

SCHEME_ALIASES = {
    "tx1": "dk1",
    "bg1": "lt1",
    "tx2": "dk2",
    "bg2": "lt2",
}

FORBIDDEN_PRESET_TERMS = (
    "red",
    "crimson",
    "maroon",
    "tomato",
    "firebrick",
    "green",
    "lime",
    "olive",
    "blue",
    "navy",
    "cyan",
    "aqua",
    "teal",
)


@dataclass
class Reporter:
    passes: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    skips: list[str] = field(default_factory=list)

    def check(self, condition: bool, label: str, detail: str = "") -> bool:
        message = label if not detail else f"{label}: {detail}"
        if condition:
            self.passes.append(message)
        else:
            self.failures.append(message)
        return condition

    def fail(self, label: str, detail: str = "") -> None:
        self.check(False, label, detail)

    def skip(self, label: str, detail: str = "") -> None:
        self.skips.append(label if not detail else f"{label}: {detail}")

    def emit(self) -> None:
        for message in self.passes:
            print(f"[PASS] {message}")
        for message in self.skips:
            print(f"[SKIP] {message}")
        for message in self.failures:
            print(f"[FAIL] {message}")
        print(
            "\nResumo: "
            f"{len(self.passes)} passou/passaram, "
            f"{len(self.skips)} ignorado(s), "
            f"{len(self.failures)} falhou/falharam."
        )


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read_csv_rows(path: Path, reporter: Reporter) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = list(reader.fieldnames or [])
            rows: list[dict[str, str]] = []
            malformed: list[int] = []
            for line_number, row in enumerate(reader, start=2):
                if None in row:
                    malformed.append(line_number)
                rows.append({str(key): value or "" for key, value in row.items() if key is not None})
    except (OSError, UnicodeError, csv.Error) as exc:
        reporter.fail(f"CSV legível — {path.name}", str(exc))
        return [], []

    reporter.check(bool(headers), f"Cabeçalho presente — {path.name}")
    reporter.check(bool(rows), f"Linhas de dados presentes — {path.name}", f"{len(rows)} linha(s)")
    reporter.check(
        not malformed,
        f"Estrutura CSV íntegra — {path.name}",
        "linhas com colunas excedentes: " + ", ".join(map(str, malformed[:10])) if malformed else "ok",
    )
    return headers, rows


def split_source_ids(value: str) -> list[str]:
    return [part.strip() for part in value.split("|") if part.strip()]


def validate_csv_layer(data_dir: Path, reporter: Reporter) -> None:
    expected = set(EXPECTED_CSVS)
    observed = {
        path.name
        for path in data_dir.glob("*.csv")
        if not path.name.startswith("raw_")
    }
    reporter.check(data_dir.is_dir(), "Diretório CSV existe", str(data_dir))
    reporter.check(
        observed == expected,
        "Camada canônica contém exatamente 22 CSVs",
        (
            f"encontrados={len(observed)}, ausentes={sorted(expected - observed)}, "
            f"extras={sorted(observed - expected)}"
        ),
    )
    if not data_dir.is_dir() or not expected.issubset(observed):
        return

    parsed: dict[str, list[dict[str, str]]] = {}
    headers_by_file: dict[str, list[str]] = {}
    blank_sources: list[str] = []

    for name in EXPECTED_CSVS:
        headers, rows = read_csv_rows(data_dir / name, reporter)
        headers_by_file[name] = headers
        parsed[name] = rows
        if "fonte_id" not in headers:
            reporter.fail(f"Coluna fonte_id presente — {name}")
            continue
        for index, row in enumerate(rows, start=2):
            if not row.get("fonte_id", "").strip():
                blank_sources.append(f"{name}:{index}")

    reporter.check(
        not blank_sources,
        "Nenhuma fonte_id vazia nos 22 CSVs",
        "ok" if not blank_sources else ", ".join(blank_sources[:20]),
    )

    source_rows = parsed["17_fontes.csv"]
    mapped_source_ids = [row.get("fonte_id", "").strip() for row in source_rows]
    duplicate_source_ids = sorted(
        source_id for source_id, count in Counter(mapped_source_ids).items() if source_id and count > 1
    )
    atomic_mapping_ids = [source_id for source_id in mapped_source_ids if "|" not in source_id]
    reporter.check(
        len(atomic_mapping_ids) == len(mapped_source_ids),
        "17_fontes usa uma fonte_id atômica por linha",
    )
    reporter.check(
        not duplicate_source_ids,
        "17_fontes não contém fonte_id duplicada",
        "ok" if not duplicate_source_ids else ", ".join(duplicate_source_ids),
    )
    mapping = set(mapped_source_ids)
    unmapped: dict[str, list[str]] = {}
    for name, rows in parsed.items():
        if "fonte_id" not in headers_by_file[name]:
            continue
        for line_number, row in enumerate(rows, start=2):
            for source_id in split_source_ids(row.get("fonte_id", "")):
                if source_id not in mapping:
                    unmapped.setdefault(source_id, []).append(f"{name}:{line_number}")
    if unmapped:
        detail = "; ".join(
            f"{source_id} ({', '.join(locations[:5])})"
            for source_id, locations in sorted(unmapped.items())
        )
    else:
        detail = f"{len(mapping)} fonte(s) mapeada(s)"
    reporter.check(not unmapped, "Toda fonte_id está mapeada em 17_fontes", detail)

    vehicle_rows = parsed["01_veiculos.csv"]
    vehicle_ids = [row.get("veiculo_id", "").strip() for row in vehicle_rows]
    unique_vehicle_ids = set(vehicle_ids)
    reporter.check(len(vehicle_rows) == 13, "01_veiculos contém 13 linhas", str(len(vehicle_rows)))
    reporter.check(
        len(unique_vehicle_ids) == 13 and "" not in unique_vehicle_ids,
        "01_veiculos contém 13 veiculo_id únicos e preenchidos",
        str(len(unique_vehicle_ids - {""})),
    )
    vehicle_types = {
        row.get("veiculo_id", "").strip(): row.get("tipo", "").strip().upper()
        for row in vehicle_rows
        if row.get("veiculo_id", "").strip()
    }
    type_counts = Counter(vehicle_types.values())
    reporter.check(
        type_counts == Counter({"FIDC": 7, "CRI": 6}),
        "Universo possui 7 FIDCs e 6 CRIs",
        str(dict(type_counts)),
    )

    series_rows = parsed["02_series.csv"]
    reporter.check(len(series_rows) == 59, "02_series contém 59 linhas", str(len(series_rows)))
    series_type_counts: Counter[str] = Counter()
    unknown_series_vehicles: list[str] = []
    series_keys: list[tuple[str, str]] = []
    for row in series_rows:
        vehicle_id = row.get("veiculo_id", "").strip()
        series = row.get("serie", "").strip()
        series_keys.append((vehicle_id, series))
        vehicle_type = vehicle_types.get(vehicle_id)
        if vehicle_type:
            series_type_counts[vehicle_type] += 1
        else:
            unknown_series_vehicles.append(vehicle_id or "<vazio>")
    reporter.check(
        not unknown_series_vehicles,
        "Todas as linhas de 02_series apontam para 01_veiculos",
        "ok" if not unknown_series_vehicles else ", ".join(sorted(set(unknown_series_vehicles))),
    )
    reporter.check(
        series_type_counts == Counter({"CRI": 34, "FIDC": 25}),
        "02_series contém 34 séries CRI e 25 classes FIDC",
        str(dict(series_type_counts)),
    )
    duplicate_series_keys = sorted(
        key for key, count in Counter(series_keys).items() if count > 1
    )
    reporter.check(
        not duplicate_series_keys,
        "Chave veiculo_id + serie é única em 02_series",
        "ok" if not duplicate_series_keys else str(duplicate_series_keys[:10]),
    )
    cri_placements = Counter(
        row.get("colocacao", "").strip()
        for row in series_rows
        if row.get("veiculo_id", "").startswith("CRI_")
    )
    reporter.check(
        cri_placements == Counter({"pública": 28, "privada": 6}),
        "34 séries CRI separam 28 públicas e 6 privadas",
        str(dict(cri_placements)),
    )

    panel_questions = [row for row in parsed["00_painel.csv"] if row.get("tipo") == "pergunta"]
    reporter.check(
        len(panel_questions) == 8,
        "00_painel endereça as oito perguntas obrigatórias",
        str(len(panel_questions)),
    )

    conflicts = parsed["16_conflitos.csv"]
    iso_date_or_range = re.compile(
        r"^\d{4}-\d{2}-\d{2}(?: (?:a|\|) \d{4}-\d{2}-\d{2})*$"
    )
    conflict_dates_complete = all(
        iso_date_or_range.fullmatch(row.get("data_base_A", "").strip())
        and iso_date_or_range.fullmatch(row.get("data_base_B", "").strip())
        for row in conflicts
    )
    reporter.check(
        len(conflicts) == 20 and conflict_dates_complete,
        "Conflitos registram valor, fonte, data-base e decisão",
        f"linhas={len(conflicts)}, datas completas={conflict_dates_complete}",
    )

    source_dates_valid = all(
        iso_date_or_range.fullmatch(row.get("data_acesso", "").strip())
        and (
            row.get("data_base", "").strip() == "n/d"
            or iso_date_or_range.fullmatch(row.get("data_base", "").strip())
        )
        for row in parsed["17_fontes.csv"]
    )
    reporter.check(
        source_dates_valid,
        "17_fontes usa datas ISO ou intervalos de datas ISO",
    )

    schedule = parsed["13_cronograma_pagamentos.csv"]
    schedule_keys = [
        (
            row.get("veiculo_id", ""),
            row.get("serie", ""),
            row.get("competencia", ""),
            row.get("status", ""),
        )
        for row in schedule
    ]
    duplicate_schedule_keys = [
        key for key, count in Counter(schedule_keys).items() if count > 1
    ]
    schedule_statuses = {row.get("status", "") for row in schedule}
    first_openings: dict[tuple[str, str], tuple[str, str]] = {}
    for row in schedule:
        if row.get("status") != "Realizado":
            continue
        key = (row.get("veiculo_id", ""), row.get("serie", ""))
        candidate = (row.get("competencia", ""), row.get("saldo_inicial", ""))
        if key not in first_openings or candidate[0] < first_openings[key][0]:
            first_openings[key] = candidate
    first_openings_are_missing = all(value == "n/d" for _date, value in first_openings.values())
    reporter.check(
        not duplicate_schedule_keys and schedule_statuses == {"Realizado", "Projetado"},
        "Cronograma tem uma linha por série, mês e status",
        f"duplicadas={len(duplicate_schedule_keys)}, status={sorted(schedule_statuses)}",
    )
    reporter.check(
        first_openings_are_missing,
        "Saldo inicial da primeira competência permanece n/d",
        f"séries realizadas={len(first_openings)}",
    )


def latest_artifact(output_dir: Path, suffix: str) -> Path | None:
    candidates = sorted(output_dir.glob(f"Solfacil_CRI_FIDC_*{suffix}"))
    canonical = [
        path
        for path in candidates
        if re.fullmatch(rf"Solfacil_CRI_FIDC_\d{{8}}{re.escape(suffix)}", path.name)
    ]
    return canonical[-1] if canonical else (candidates[-1] if candidates else None)


def validate_zip(path: Path, reporter: Reporter, label: str) -> zipfile.ZipFile | None:
    if not path.is_file():
        reporter.fail(f"{label} existe", str(path))
        return None
    try:
        archive = zipfile.ZipFile(path)
        bad_member = archive.testzip()
    except (OSError, zipfile.BadZipFile) as exc:
        reporter.fail(f"{label} é um pacote OOXML válido", str(exc))
        return None
    if bad_member:
        reporter.fail(f"{label} é um pacote OOXML válido", f"membro corrompido: {bad_member}")
        archive.close()
        return None
    reporter.check(True, f"{label} é um pacote OOXML válido", path.name)
    return archive


def validate_xlsx(path: Path, reporter: Reporter) -> None:
    archive = validate_zip(path, reporter, "XLSX")
    if archive is None:
        return
    try:
        names = archive.namelist()
        worksheet_parts = sorted(name for name in names if XML_WORKSHEET_RE.match(name))
        table_parts = sorted(name for name in names if XML_XLSX_TABLE_RE.match(name))
        chart_parts = sorted(name for name in names if XML_XLSX_CHART_RE.match(name))
        drawing_parts = sorted(
            name for name in names if re.match(r"^xl/drawings/drawing\d+\.xml$", name)
        )

        reporter.check(
            len(worksheet_parts) == 22,
            "XLSX contém 22 worksheets",
            str(len(worksheet_parts)),
        )
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet_names = [
            element.attrib.get("name", "")
            for element in workbook_root.iter()
            if local_name(element.tag) == "sheet"
        ]
        reporter.check(
            tuple(sheet_names) == EXPECTED_SHEETS,
            "XLSX contém as 22 abas esperadas na ordem esperada",
            ", ".join(sheet_names),
        )

        table_names: list[str] = []
        malformed_tables: list[str] = []
        for part in table_parts:
            try:
                table_root = ET.fromstring(archive.read(part))
            except ET.ParseError:
                malformed_tables.append(part)
                continue
            table_name = table_root.attrib.get("name") or table_root.attrib.get("displayName") or ""
            table_names.append(table_name)
        reporter.check(
            len(table_parts) == 22 and not malformed_tables,
            "XLSX contém 22 tabelas nativas legíveis",
            f"tabelas={len(table_parts)}, inválidas={malformed_tables}",
        )
        reporter.check(
            len(set(table_names)) == len(table_names) and all(name.startswith("tbl_") for name in table_names),
            "Tabelas XLSX têm nomes tbl_* únicos",
            ", ".join(table_names),
        )
        reporter.check(
            set(table_names) == set(EXPECTED_TABLES),
            "Nomes das tabelas XLSX correspondem às 22 abas",
            (
                f"ausentes={sorted(set(EXPECTED_TABLES) - set(table_names))}, "
                f"extras={sorted(set(table_names) - set(EXPECTED_TABLES))}"
            ),
        )
        chart_reference_count = 0
        for part in drawing_parts:
            try:
                drawing_root = ET.fromstring(archive.read(part))
            except ET.ParseError:
                continue
            chart_reference_count += sum(
                1 for element in drawing_root.iter() if element.tag == f"{{{C_NS}}}chart"
            )
        reporter.check(
            bool(chart_parts) and chart_reference_count > 0,
            "XLSX contém gráficos nativos",
            f"partes={len(chart_parts)}, referências={chart_reference_count}",
        )
    except (KeyError, ET.ParseError) as exc:
        reporter.fail("Estrutura interna do XLSX é legível", str(exc))
    finally:
        archive.close()


def parse_theme_colors(archive: zipfile.ZipFile) -> dict[str, str]:
    theme_parts = sorted(
        name
        for name in archive.namelist()
        if re.match(r"^ppt/theme/theme\d+\.xml$", name)
    )
    if not theme_parts:
        return {}
    try:
        root = ET.fromstring(archive.read(theme_parts[0]))
    except (KeyError, ET.ParseError):
        return {}

    colors: dict[str, str] = {}
    for scheme in root.iter():
        if local_name(scheme.tag) != "clrScheme":
            continue
        for slot in list(scheme):
            slot_name = local_name(slot.tag)
            for value in list(slot):
                value_name = local_name(value.tag)
                if value_name == "srgbClr" and value.attrib.get("val"):
                    colors[slot_name] = value.attrib["val"].upper()
                    break
                if value_name == "sysClr" and value.attrib.get("lastClr"):
                    colors[slot_name] = value.attrib["lastClr"].upper()
                    break
        break
    return colors


def forbidden_rgb_category(value: str) -> str | None:
    value = value.strip().lstrip("#").upper()
    if not re.fullmatch(r"[0-9A-F]{6}", value):
        return None
    red, green, blue = (int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))
    hue, saturation, brightness = colorsys.rgb_to_hsv(red, green, blue)
    hue_degrees = hue * 360
    # Low-saturation tints still read as colored fills on a white credit deck.
    # A small floor filters only true neutral grays and near-black artifacts.
    if saturation < 0.08 or brightness < 0.15:
        return None
    if hue_degrees <= 15 or hue_degrees >= 345:
        return "vermelho"
    if 75 <= hue_degrees <= 165:
        return "verde"
    if 170 <= hue_degrees <= 265:
        return "azul"
    return None


def scan_forbidden_pptx_colors(archive: zipfile.ZipFile) -> list[str]:
    theme_colors = parse_theme_colors(archive)
    findings: Counter[tuple[str, str, str]] = Counter()
    sample_parts: dict[tuple[str, str, str], str] = {}
    relevant_parts = sorted(
        name
        for name in archive.namelist()
        if name.endswith(".xml")
        and not name.endswith(".rels")
        and "/theme/" not in name
        and name.startswith(COLOR_SCAN_PREFIXES)
    )

    for part in relevant_parts:
        try:
            root = ET.fromstring(archive.read(part))
        except ET.ParseError:
            continue
        for element in root.iter():
            element_name = local_name(element.tag)
            source = ""
            rgb_value = ""
            if element_name == "srgbClr":
                rgb_value = element.attrib.get("val", "")
                source = "srgbClr"
            elif element_name == "sysClr":
                rgb_value = element.attrib.get("lastClr", "")
                source = "sysClr"
            elif element_name == "schemeClr":
                scheme_name = element.attrib.get("val", "")
                resolved_name = SCHEME_ALIASES.get(scheme_name, scheme_name)
                rgb_value = theme_colors.get(resolved_name, "")
                source = f"schemeClr:{scheme_name}"
            elif element_name == "prstClr":
                preset_name = element.attrib.get("val", "").lower()
                if any(term in preset_name for term in FORBIDDEN_PRESET_TERMS):
                    key = ("preset", preset_name, "prstClr")
                    findings[key] += 1
                    sample_parts.setdefault(key, part)
                continue

            category = forbidden_rgb_category(rgb_value)
            if category:
                normalized = rgb_value.strip().lstrip("#").upper()
                key = (category, normalized, source)
                findings[key] += 1
                sample_parts.setdefault(key, part)

    return [
        f"{category} #{value} via {source}, {count} ocorrência(s), ex. {sample_parts[key]}"
        for key, count in sorted(findings.items())
        for category, value, source in [key]
    ]


def scan_non_palette_pptx_colors(archive: zipfile.ZipFile) -> list[str]:
    """Return saturated colors that are not the approved Solfácil orange."""
    theme_colors = parse_theme_colors(archive)
    findings: Counter[tuple[str, str]] = Counter()
    for part in sorted(
        name
        for name in archive.namelist()
        if name.endswith(".xml")
        and not name.endswith(".rels")
        and "/theme/" not in name
        and name.startswith(COLOR_SCAN_PREFIXES)
    ):
        try:
            root = ET.fromstring(archive.read(part))
        except ET.ParseError:
            continue
        for element in root.iter():
            name = local_name(element.tag)
            value = ""
            if name == "srgbClr":
                value = element.attrib.get("val", "")
            elif name == "sysClr":
                value = element.attrib.get("lastClr", "")
            elif name == "schemeClr":
                scheme_name = element.attrib.get("val", "")
                value = theme_colors.get(SCHEME_ALIASES.get(scheme_name, scheme_name), "")
            value = value.strip().lstrip("#").upper()
            if not re.fullmatch(r"[0-9A-F]{6}", value):
                continue
            red, green, blue = (int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))
            _hue, saturation, brightness = colorsys.rgb_to_hsv(red, green, blue)
            if saturation >= 0.08 and brightness >= 0.15 and value != "E46C0A":
                findings[(value, part)] += 1
    return [f"#{value}, {count} ocorrência(s), ex. {part}" for (value, part), count in sorted(findings.items())]


def validate_pptx(path: Path, reporter: Reporter) -> None:
    archive = validate_zip(path, reporter, "PPTX")
    if archive is None:
        return
    try:
        names = archive.namelist()
        slide_parts = sorted(name for name in names if XML_SLIDE_RE.match(name))
        notes_parts = sorted(name for name in names if XML_NOTES_RE.match(name))
        chart_parts = sorted(name for name in names if XML_PPTX_CHART_RE.match(name))
        media_parts = sorted(
            name for name in names if name.startswith("ppt/media/") and not name.endswith("/")
        )
        reporter.check(len(slide_parts) == 16, "PPTX contém 16 slides", str(len(slide_parts)))

        presentation_root = ET.fromstring(archive.read("ppt/presentation.xml"))
        presentation_slide_ids = [
            element for element in presentation_root.iter() if local_name(element.tag) == "sldId"
        ]
        reporter.check(
            len(presentation_slide_ids) == 16,
            "presentation.xml referencia 16 slides",
            str(len(presentation_slide_ids)),
        )
        reporter.check(
            not media_parts,
            "PPTX não contém ppt/media",
            "ok" if not media_parts else ", ".join(media_parts),
        )

        shape_count = 0
        table_count = 0
        chart_reference_count = 0
        malformed_slides: list[str] = []
        connector_glyphs: list[str] = []
        for part in slide_parts:
            try:
                root = ET.fromstring(archive.read(part))
            except ET.ParseError:
                malformed_slides.append(part)
                continue
            shape_count += sum(
                1
                for element in root.iter()
                if element.tag
                in {
                    f"{{{P_NS}}}sp",
                    f"{{{P_NS}}}cxnSp",
                    f"{{{P_NS}}}grpSp",
                }
            )
            table_count += sum(1 for element in root.iter() if element.tag == f"{{{A_NS}}}tbl")
            chart_reference_count += sum(
                1 for element in root.iter() if element.tag == f"{{{C_NS}}}chart"
            )
            slide_text = " ".join(
                element.text or "" for element in root.iter() if element.tag == f"{{{A_NS}}}t"
            )
            if any(glyph in slide_text for glyph in ("›", "→", "←", "↔")):
                connector_glyphs.append(part)

        reporter.check(
            not malformed_slides,
            "XML dos slides é legível",
            "ok" if not malformed_slides else ", ".join(malformed_slides),
        )
        reporter.check(
            not connector_glyphs,
            "PPTX não usa glifos como conectores visuais",
            "ok" if not connector_glyphs else ", ".join(connector_glyphs),
        )

        notes_with_sources = 0
        for part in notes_parts:
            try:
                root = ET.fromstring(archive.read(part))
            except ET.ParseError:
                continue
            note_text = " ".join(
                element.text or "" for element in root.iter() if element.tag == f"{{{A_NS}}}t"
            )
            if "[Sources]" in note_text:
                notes_with_sources += 1
        reporter.check(
            len(notes_parts) == 16 and notes_with_sources == 16,
            "PPTX contém 16 notas com bloco [Sources]",
            f"notas={len(notes_parts)}, com fontes={notes_with_sources}",
        )
        reporter.check(shape_count > 0, "PPTX contém shapes nativos", str(shape_count))
        reporter.check(table_count > 0, "PPTX contém tabelas nativas", str(table_count))
        reporter.check(
            bool(chart_parts) and chart_reference_count > 0,
            "PPTX contém charts nativos",
            f"partes={len(chart_parts)}, referências={chart_reference_count}",
        )

        forbidden_colors = scan_forbidden_pptx_colors(archive)
        reporter.check(
            not forbidden_colors,
            "PPTX não usa cores saturadas proibidas (verde/vermelho/azul)",
            "ok" if not forbidden_colors else "; ".join(forbidden_colors[:20]),
        )
        non_palette_colors = scan_non_palette_pptx_colors(archive)
        reporter.check(
            not non_palette_colors,
            "PPTX restringe cores cromáticas ao laranja aprovado",
            "ok" if not non_palette_colors else "; ".join(non_palette_colors[:20]),
        )
    except (KeyError, ET.ParseError) as exc:
        reporter.fail("Estrutura interna do PPTX é legível", str(exc))
    finally:
        archive.close()


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    script_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=script_root,
        help="Raiz do worktree (padrão: diretório pai de tools/).",
    )
    parser.add_argument("--data-dir", type=Path, help="Sobrescreve data/solfacil.")
    parser.add_argument("--xlsx", type=Path, help="XLSX específico a validar.")
    parser.add_argument("--pptx", type=Path, help="PPTX específico a validar.")
    parser.add_argument(
        "--require-pptx",
        action="store_true",
        help="Falha se o PPTX ainda não existir.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    data_dir = (args.data_dir or root / "data" / "solfacil").resolve()
    output_dir = root / "outputs" / "solfacil"
    reporter = Reporter()

    validate_csv_layer(data_dir, reporter)

    xlsx_path = args.xlsx.resolve() if args.xlsx else latest_artifact(output_dir, ".xlsx")
    if xlsx_path is None:
        reporter.fail("XLSX localizado", display_path(output_dir, root))
    else:
        validate_xlsx(xlsx_path, reporter)

    if args.pptx:
        pptx_path = args.pptx.resolve()
    elif xlsx_path is not None:
        matching_pptx = xlsx_path.with_suffix(".pptx")
        pptx_path = matching_pptx if matching_pptx.is_file() else latest_artifact(output_dir, ".pptx")
    else:
        pptx_path = latest_artifact(output_dir, ".pptx")

    if pptx_path is None:
        detail = display_path(output_dir, root)
        if args.require_pptx:
            reporter.fail("PPTX localizado", detail)
        else:
            reporter.skip("Validações do PPTX", f"arquivo ainda não existe em {detail}")
    else:
        validate_pptx(pptx_path, reporter)

    reporter.emit()
    return 1 if reporter.failures else 0


if __name__ == "__main__":
    sys.exit(main())
