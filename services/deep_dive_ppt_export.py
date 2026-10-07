from __future__ import annotations

from datetime import datetime
from dataclasses import replace
from io import BytesIO
import re
import textwrap
from typing import TYPE_CHECKING, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from services.deep_dive_models import DeepDiveManifest, DeepDiveTableSpec
from services.presentation_text import document_comparison_value, public_document_text, public_pptx_bytes

if TYPE_CHECKING:
    from services.document_curation_comparison import DocumentComparisonPage


SLIDE_W = 13.333
SLIDE_H = 7.5
LEFT = 0.34
RIGHT = 0.28
TOP = 0.26
FOOTER_TOP = 7.08
CONTENT_W = SLIDE_W - LEFT - RIGHT
TABLE_TOP = 0.96
TABLE_BOTTOM = 6.88
TABLE_H = TABLE_BOTTOM - TABLE_TOP

BLACK = "1F1F1F"
HEADER = "111827"
ORANGE = "EC7000"
HEADER_ORANGE = "FF6200"
WHITE = "FFFFFF"
SOFT = "F7F7F7"
GRID = "D9DEE5"
MID = "6B7280"
HIGHLIGHT = "FFF2E8"
RED_TEXT = "C8102E"
FONT = "Calibri"

DOCUMENT_LEFT = 0.48
DOCUMENT_WIDTH = SLIDE_W - DOCUMENT_LEFT * 2
DOCUMENT_TABLE_TOP = 1.02
DOCUMENT_TABLE_BOTTOM = 6.83
DOCUMENT_FONT_SIZE = 13.0
DOCUMENT_LINE_HEIGHT = 0.205
DOCUMENT_CELL_PADDING = 0.10
DOCUMENT_MAX_FUNDS = 4


def build_document_comparison_pptx_bytes(
    manifest: DeepDiveManifest,
    pages: Sequence[DocumentComparisonPage],
) -> bytes:
    """Render documentary comparisons as editable, source-cited slide tables.

    Every fund stays in the export. Column groups repeat the criterion column,
    and long content continues on subsequent slides without ellipses.
    """
    try:
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.enum.text import MSO_AUTO_SIZE, MSO_ANCHOR, PP_ALIGN
        from pptx.util import Inches, Pt
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Dependência python-pptx não instalada.") from exc

    from services.document_curation_comparison import comparison_column_chunks

    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)
    jobs = []
    for page in pages:
        page = replace(page,
            notes=tuple(clean for note in page.notes if (clean := public_document_text(note))),
            sources=tuple(clean for source in page.sources if (clean := public_document_text(source))),
        )
        frame = page.frame.copy()
        if frame.empty or not len(frame.columns):
            continue
        for column in frame.columns[1:]:
            frame[column] = frame[column].map(_document_cell_text)
        note_lines = [line for note in page.notes if (clean := public_document_text(note)) for line in textwrap.wrap(clean, width=165)]
        note_groups = [note_lines[start : start + 8] for start in range(0, len(note_lines), 8)] or [[]]
        for selected in comparison_column_chunks(frame, max_funds=DOCUMENT_MAX_FUNDS):
            widths = _document_column_widths(len(selected.columns))
            header_height = max(0.43, _document_row_height(pd.Series(selected.columns), widths))
            for visible_notes in note_groups:
                notes_height = len(visible_notes) * 0.155 + 0.15 if visible_notes else 0
                for segment, heights in _document_row_pages(selected, widths, header_height, notes_height=notes_height):
                    jobs.append((page, segment, widths, header_height, heights, visible_notes, notes_height))

    if not jobs:
        raise ValueError("Não há tabelas documentais disponíveis para exportação.")

    def rgb(value: str):  # noqa: ANN202
        return RGBColor.from_string(value)

    def text_box(slide, text: str, left: float, top: float, width: float, height: float, size: float, *, bold: bool = False, color: str = BLACK, align=PP_ALIGN.LEFT):  # noqa: ANN001, ANN202, PLR0913
        shape = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        frame = shape.text_frame
        frame.word_wrap = True
        frame.auto_size = MSO_AUTO_SIZE.NONE
        frame.margin_left = frame.margin_right = 0
        frame.margin_top = frame.margin_bottom = 0
        paragraph = frame.paragraphs[0]
        paragraph.alignment = align
        run = paragraph.add_run()
        run.text = text
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = rgb(color)
        return shape

    for index, (page, frame, widths, header_height, row_heights, visible_notes, notes_height) in enumerate(jobs, start=1):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = rgb(WHITE)
        title = f"{manifest.title} – {page.title}"
        title_size = 23 if len(title) <= 95 else 20
        text_box(slide, title, DOCUMENT_LEFT, 0.32, DOCUMENT_WIDTH, 0.61, title_size, bold=True, color=ORANGE)
        height = header_height + sum(row_heights)
        table = slide.shapes.add_table(
            len(frame) + 1, len(frame.columns),
            Inches(DOCUMENT_LEFT), Inches(DOCUMENT_TABLE_TOP),
            Inches(DOCUMENT_WIDTH), Inches(height),
        ).table
        table.first_row = False
        table.horz_banding = False
        table.vert_banding = False
        for col_index, width in enumerate(widths):
            table.columns[col_index].width = Inches(width)
        table.rows[0].height = Inches(header_height)
        for row_index, row_height in enumerate(row_heights, start=1):
            table.rows[row_index].height = Inches(row_height)
        values = [list(frame.columns), *frame.values.tolist()]
        for row_index, row in enumerate(values):
            for col_index, value in enumerate(row):
                cell = table.cell(row_index, col_index)
                cell.text = "\n".join(_document_wrapped_lines(value, widths[col_index]))
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(HEADER_ORANGE if row_index == 0 else WHITE)
                cell.margin_left = cell.margin_right = Inches(DOCUMENT_CELL_PADDING)
                cell.margin_top = cell.margin_bottom = Inches(0.045)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell.text_frame.word_wrap = True
                cell.text_frame.auto_size = MSO_AUTO_SIZE.NONE
                for paragraph in cell.text_frame.paragraphs:
                    paragraph.alignment = PP_ALIGN.LEFT if col_index == 0 else PP_ALIGN.CENTER
                    paragraph.space_before = paragraph.space_after = Pt(0)
                    paragraph.line_spacing = 1.0
                    for run in paragraph.runs:
                        run.font.name = FONT
                        run.font.size = Pt(DOCUMENT_FONT_SIZE)
                        run.font.bold = row_index == 0 or col_index == 0
                        run.font.color.rgb = rgb(WHITE if row_index == 0 else BLACK)
                _document_cell_borders(cell, header=row_index == 0, last=row_index == len(frame))

        if visible_notes:
            text_box(slide, "\n".join(visible_notes), DOCUMENT_LEFT, DOCUMENT_TABLE_BOTTOM - notes_height + 0.1, DOCUMENT_WIDTH, notes_height, 10, color=MID)

        reading_date = _document_reading_date(manifest.generated_at)
        text_box(slide, f"Leitura documental: {reading_date}. Fontes e referências nas notas do slide.", DOCUMENT_LEFT, 7.03, DOCUMENT_WIDTH - 1, 0.18, 8.5, color=MID)
        text_box(slide, f"{index}/{len(jobs)}", SLIDE_W - DOCUMENT_LEFT - 0.7, 7.03, 0.7, 0.18, 8.5, color=MID, align=PP_ALIGN.RIGHT)
        notes = [page.title, f"Leitura documental: {manifest.generated_at or 'data não informada'}"]
        notes.extend(f"{fund.get('short_name') or fund.get('name')}: CNPJ {fund.get('cnpj') or 'não localizado'}" for fund in manifest.funds)
        if page.notes:
            notes.extend(["Observações:", *page.notes])
        notes.extend(["Fontes:", *(page.sources or (manifest.source or "Fonte documental não localizada",))])
        slide.notes_slide.notes_text_frame.text = "\n".join(notes)

    output = BytesIO()
    prs.save(output)
    return public_pptx_bytes(output.getvalue())


def _document_cell_text(value: object) -> str:
    return document_comparison_value(value)


def _document_reading_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except (ValueError, AttributeError):
        return "data não informada"


def _document_column_widths(count: int) -> list[float]:
    if count <= 1:
        return [DOCUMENT_WIDTH]
    criterion = 2.55
    return [criterion, *[(DOCUMENT_WIDTH - criterion) / (count - 1)] * (count - 1)]


def _document_wrapped_lines(value: object, width: float) -> list[str]:
    # Conservative width at 13 pt: table columns retain readable typography.
    capacity = max(12, int((width - DOCUMENT_CELL_PADDING * 2) * 72 / (DOCUMENT_FONT_SIZE * 0.53)))
    output = []
    for paragraph in str(value).split("\n"):
        output.extend(textwrap.wrap(paragraph, width=capacity, break_long_words=True, break_on_hyphens=False) or [""])
    return output


def _document_row_height(row: pd.Series, widths: list[float]) -> float:
    lines = max(len(_document_wrapped_lines(value, width)) for value, width in zip(row, widths, strict=True))
    return max(0.265, lines * DOCUMENT_LINE_HEIGHT + 0.105)


def _document_row_pages(frame: pd.DataFrame, widths: list[float], header_height: float, *, notes_height: float = 0) -> list[tuple[pd.DataFrame, list[float]]]:
    available = DOCUMENT_TABLE_BOTTOM - DOCUMENT_TABLE_TOP - header_height - notes_height
    max_lines = max(1, int((available - 0.105) / DOCUMENT_LINE_HEIGHT))
    expanded = []
    for _, row in frame.iterrows():
        wrapped = [_document_wrapped_lines(value, width) for value, width in zip(row, widths, strict=True)]
        if max(map(len, wrapped)) <= max_lines:
            expanded.append(row.tolist())
            continue
        for offset in range(0, max(map(len, wrapped)), max_lines):
            values = ["\n".join(lines[offset : offset + max_lines]) for lines in wrapped]
            values[0] = str(row.iloc[0]) if offset == 0 else f"{row.iloc[0]} (continuação)"
            expanded.append(values)
    jobs = []
    rows, heights = [], []
    for values in expanded:
        height = _document_row_height(pd.Series(values), widths)
        if rows and sum(heights) + height > available:
            jobs.append((pd.DataFrame(rows, columns=frame.columns), heights))
            rows, heights = [], []
        rows.append(values)
        heights.append(min(height, available))
    if rows:
        jobs.append((pd.DataFrame(rows, columns=frame.columns), heights))
    if len(jobs) > 1:
        # Balance continuations so a full first slide does not leave two rows
        # stranded on the next slide. The maximum readable height still wins.
        row_heights = [_document_row_height(pd.Series(values), widths) for values in expanded]
        remaining_height = sum(row_heights)
        pages_left = len(jobs)
        jobs, rows, heights = [], [], []
        target = remaining_height / pages_left
        for index, (values, height) in enumerate(zip(expanded, row_heights, strict=True)):
            used = sum(heights)
            balanced_break = pages_left > 1 and len(expanded) - index >= pages_left - 1 and abs(used - target) <= abs(used + height - target)
            if rows and (used + height > available or balanced_break):
                jobs.append((pd.DataFrame(rows, columns=frame.columns), heights))
                remaining_height -= used
                pages_left = max(1, pages_left - 1)
                target = remaining_height / pages_left
                rows, heights = [], []
            rows.append(values)
            heights.append(min(height, available))
        if rows:
            jobs.append((pd.DataFrame(rows, columns=frame.columns), heights))
    return jobs


def _document_cell_borders(cell, *, header: bool, last: bool) -> None:  # noqa: ANN001
    from pptx.oxml.xmlchemy import OxmlElement

    properties = cell._tc.get_or_add_tcPr()
    for edge in ("L", "R", "T", "B"):
        tag = f"a:ln{edge}"
        for existing in list(properties.findall(f"{{http://schemas.openxmlformats.org/drawingml/2006/main}}ln{edge}")):
            properties.remove(existing)
        line = OxmlElement(tag)
        if edge == "B" and (header or last):
            line.set("w", "6350")
            fill = OxmlElement("a:solidFill")
            color = OxmlElement("a:srgbClr")
            color.set("val", GRID)
            fill.append(color)
            line.append(fill)
        else:
            line.append(OxmlElement("a:noFill"))
        properties.append(line)


def build_deep_dive_pptx_bytes(
    manifest: DeepDiveManifest,
    tables: list[tuple[DeepDiveTableSpec, pd.DataFrame]],
    *,
    highlighted_column: str | None = None,
    generated_at: datetime | None = None,
) -> bytes:
    try:
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
        from pptx.enum.text import MSO_AUTO_SIZE, MSO_ANCHOR, PP_ALIGN
        from pptx.util import Inches, Pt
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Dependência python-pptx não instalada.") from exc

    tz = ZoneInfo("America/Sao_Paulo")
    if generated_at is None:
        generated_at = datetime.now(tz)
    elif generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=tz)
    else:
        generated_at = generated_at.astimezone(tz)

    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)
    blank = prs.slide_layouts[6]

    def rgb(hex_color: str):  # noqa: ANN202
        value = str(hex_color).strip().lstrip("#")
        return RGBColor(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))

    def add_text(slide, left, top, width, height, text, *, size, bold=False, color=BLACK, align=PP_ALIGN.LEFT):  # noqa: ANN001, ANN202
        box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        tf = box.text_frame
        tf.clear()
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.NONE
        tf.margin_left = Inches(0.01)
        tf.margin_right = Inches(0.01)
        tf.margin_top = Inches(0.00)
        tf.margin_bottom = Inches(0.00)
        p = tf.paragraphs[0]
        p.alignment = align
        run = p.add_run()
        run.text = public_document_text(text)
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = rgb(color)
        return box

    def add_header(slide, title: str, subtitle: str) -> None:  # noqa: ANN001
        add_text(slide, LEFT, TOP, 8.5, 0.26, manifest.title, size=17, bold=True, color=BLACK)
        line2 = subtitle or manifest.subtitle
        if line2:
            add_text(slide, LEFT, TOP + 0.30, 9.5, 0.18, line2, size=8.2, color=MID)
        source = manifest.source or "Deep Dive offline"
        add_text(slide, 9.25, TOP, 3.55, 0.18, source, size=7.5, color=MID, align=PP_ALIGN.RIGHT)

    def add_footer(slide, page: int, total: int) -> None:  # noqa: ANN001
        sep = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, Inches(LEFT), Inches(6.98), Inches(CONTENT_W), Inches(0.005))
        sep.fill.solid()
        sep.fill.fore_color.rgb = rgb(GRID)
        sep.line.fill.background()
        stamp = generated_at.strftime("%d/%m/%Y %H:%M")
        add_text(slide, LEFT, FOOTER_TOP, 8.8, 0.16, f"Fonte: {manifest.source or 'pacote offline'} | Gerado em: {stamp} | {manifest.confidentiality}", size=7, color=MID)
        add_text(slide, 11.20, FOOTER_TOP, 1.55, 0.16, f"Página {page} de {total}", size=7, color=MID, align=PP_ALIGN.RIGHT)

    slide_jobs: list[tuple[DeepDiveTableSpec, pd.DataFrame, int, int]] = []
    for spec, frame in tables:
        normalized = _normalize_table(frame, first_column=spec.first_column)
        col_chunks = _column_chunks(normalized)
        for col_start, col_end in col_chunks:
            chunk_cols = [spec.first_column, *normalized.columns[col_start:col_end].tolist()]
            col_frame = normalized[chunk_cols].copy()
            for row_start, row_end in _row_chunks(col_frame):
                slide_jobs.append((spec, col_frame.iloc[row_start:row_end].copy(), row_start, len(col_frame)))
    if not slide_jobs:
        slide_jobs.append((DeepDiveTableSpec(id="empty", title="Deep Dive", source_file=""), pd.DataFrame({"Nome": ["Sem dados"]}), 0, 1))

    total_pages = len(slide_jobs)
    for page, (spec, frame, row_start, row_total) in enumerate(slide_jobs, start=1):
        slide = prs.slides.add_slide(blank)
        suffix = f"{spec.title}"
        if row_total > len(frame):
            suffix = f"{suffix} · linhas {row_start + 1}-{row_start + len(frame)} de {row_total}"
        add_header(slide, manifest.title, suffix)
        add_footer(slide, page, total_pages)
        _add_table(
            slide,
            frame,
            highlighted_column=highlighted_column,
            rgb=rgb,
            Inches=Inches,
            Pt=Pt,
            MSO_ANCHOR=MSO_ANCHOR,
            PP_ALIGN=PP_ALIGN,
            MSO_AUTO_SIZE=MSO_AUTO_SIZE,
        )

    output = BytesIO()
    prs.save(output)
    return public_pptx_bytes(output.getvalue())


def _normalize_table(frame: pd.DataFrame, *, first_column: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame({first_column: ["Sem dados"]})
    output = frame.copy().fillna("—").replace("", "—")
    if first_column not in output.columns:
        output = output.rename(columns={output.columns[0]: first_column})
    return output


def _column_chunks(frame: pd.DataFrame) -> list[tuple[int, int]]:
    other_cols = list(range(1, len(frame.columns)))
    if len(other_cols) <= 5:
        return [(1, len(frame.columns))]
    chunks = []
    for start in range(1, len(frame.columns), 5):
        chunks.append((start, min(start + 5, len(frame.columns))))
    return chunks


def _rows_per_slide(frame: pd.DataFrame) -> int:
    cols = len(frame.columns)
    if cols <= 4:
        return 25
    if cols <= 6:
        return 22
    return 19


def _row_chunks(frame: pd.DataFrame) -> list[tuple[int, int]]:
    if frame.empty:
        return [(0, 0)]

    capacity = float(_rows_per_slide(frame))
    chunks: list[tuple[int, int]] = []
    start = 0
    used = 0.0
    for idx, (_, row) in enumerate(frame.iterrows()):
        weight = _row_weight(row, list(frame.columns))
        if idx > start and used + weight > capacity:
            chunks.append((start, idx))
            start = idx
            used = 0.0
        used += weight
    chunks.append((start, len(frame)))
    return chunks


def _row_weight(row: pd.Series, columns: list[str]) -> float:
    if not columns:
        return 1.0
    max_score = 0.0
    for col_idx, column in enumerate(columns):
        text = _cell_text(row.get(column, "—"))
        line_count = max(text.count("\n") + 1, 1)
        divisor = 34 if col_idx == 0 else 48
        max_score = max(max_score, len(text) / divisor, line_count * 0.75)
    if max_score <= 1.35:
        return 1.0
    return min(4.0, 1.0 + (max_score - 1.0) * 0.72)


def _column_widths(columns: list[str]) -> list[float]:
    total = CONTENT_W
    if len(columns) == 1:
        return [total]
    first = 2.25 if len(columns) <= 5 else 2.05
    other = (total - first) / (len(columns) - 1)
    return [first, *([other] * (len(columns) - 1))]


def _add_table(slide, frame: pd.DataFrame, *, highlighted_column: str | None, rgb, Inches, Pt, MSO_ANCHOR, PP_ALIGN, MSO_AUTO_SIZE) -> None:  # noqa: ANN001, PLR0913
    rows = len(frame) + 1
    cols = len(frame.columns)
    table = slide.shapes.add_table(rows, cols, Inches(LEFT), Inches(TABLE_TOP), Inches(CONTENT_W), Inches(TABLE_H)).table
    widths = _column_widths(list(frame.columns))
    for idx, width in enumerate(widths):
        table.columns[idx].width = Inches(width)
    row_weights = [1.0, *[_row_weight(row, list(frame.columns)) for _, row in frame.iterrows()]]
    weight_total = max(sum(row_weights), 1.0)
    for row, weight in zip(table.rows, row_weights, strict=False):
        row.height = Inches(TABLE_H * (weight / weight_total))

    for col_idx, column in enumerate(frame.columns):
        table.cell(0, col_idx).text = str(column)
    for row_idx, (_, row) in enumerate(frame.iterrows(), start=1):
        for col_idx, column in enumerate(frame.columns):
            table.cell(row_idx, col_idx).text = _cell_text(row.get(column, "—"))

    for row_idx in range(rows):
        for col_idx in range(cols):
            column = frame.columns[col_idx]
            cell = table.cell(row_idx, col_idx)
            is_header = row_idx == 0
            is_first = col_idx == 0
            is_highlight = bool(highlighted_column) and column == highlighted_column
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = Inches(0.045)
            cell.margin_right = Inches(0.045)
            cell.margin_top = Inches(0.012)
            cell.margin_bottom = Inches(0.012)
            cell.fill.solid()
            if is_header:
                cell.fill.fore_color.rgb = rgb(HEADER_ORANGE)
            elif is_highlight:
                cell.fill.fore_color.rgb = rgb(HIGHLIGHT)
            elif is_first:
                cell.fill.fore_color.rgb = rgb(SOFT)
            else:
                cell.fill.fore_color.rgb = rgb(WHITE if row_idx % 2 else "FBFBFB")
            for paragraph in cell.text_frame.paragraphs:
                paragraph.alignment = PP_ALIGN.LEFT if is_first else PP_ALIGN.CENTER
                for run in paragraph.runs:
                    text = str(run.text or "")
                    run.font.name = FONT
                    run.font.size = Pt(_font_size(row_count=rows - 1, col_count=cols, is_header=is_header))
                    run.font.bold = is_header or is_first
                    run.font.color.rgb = rgb(WHITE if is_header else RED_TEXT if _looks_relevant(text) else BLACK)
            cell.text_frame.word_wrap = True
            cell.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE


def _font_size(*, row_count: int, col_count: int, is_header: bool) -> float:
    if is_header:
        return 8.0 if col_count <= 5 else 7.4
    if row_count >= 23 or col_count >= 6:
        return 7.2
    if row_count >= 19:
        return 7.7
    return 8.2


def _cell_text(value: object) -> str:
    text = document_comparison_value(value)
    if len(text) > 80 and " | " in text:
        text = re.sub(r"\s+\|\s+", "\n", text)
    return text


def _looks_relevant(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(token in lowered for token in ("diverg", "alerta", "lacuna", "não identific", "ausente", "waiver"))
