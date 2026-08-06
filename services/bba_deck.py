"""Shared 16:9 PowerPoint scaffolding for the BBA decks.

Palette and typography match ``services/industry_ppt_export.py`` so decks built
here sit alongside the existing ones without a visual break: white surface,
orange accent, Arial, 13.333 × 7.5 inches, kicker + title + rule, footer with
source and page number.

Everything rendered is native and editable — no rasterized images.
"""

from __future__ import annotations

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


BLACK = "151515"
ORANGE = "E36C0A"
ORANGE_LIGHT = "F8E9DE"
GRAY_900 = "30353A"
GRAY_700 = "5D6369"
GRAY_500 = "8D9399"
GRAY_300 = "D7DADD"
GRAY_200 = "E7E9EB"
GRAY_100 = "F5F6F7"
WHITE = "FFFFFF"

#: Chart emphasis pair.  ``HOUSE_BLUE`` marks the house; ``NEUTRAL`` is the
#: recessive backdrop for every competitor.  Validated for CVD separation
#: (ΔE 33.9 protan) and ≥3:1 contrast against the white chart surface.
HOUSE_BLUE = "14315C"
NEUTRAL = "8D9399"

FONT = "Arial"

SLIDE_WIDTH_IN = 13.333
SLIDE_HEIGHT_IN = 7.5
MARGIN_IN = 0.62
CONTENT_WIDTH_IN = 12.05


def fmt_mm(value: float, decimals: int = 1) -> str:
    """Brazilian thousand/decimal separators for a R$ million figure."""

    if pd.isna(value):
        return "—"
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "@").replace(".", ",").replace("@", ".")


def fmt_pct(value: float, decimals: int = 1) -> str:
    if pd.isna(value):
        return "—"
    return f"{value * 100:,.{decimals}f}%".replace(".", ",")


def fmt_pp(value: float, decimals: int = 1) -> str:
    if pd.isna(value):
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.{decimals}f}".replace(".", ",")


def fmt_rank(value: object) -> str:
    return "—" if value is None or pd.isna(value) else f"{int(value)}º"


class Deck:
    """A minimal, opinionated deck builder for the BBA house style."""

    def __init__(self, kicker: str) -> None:
        self.prs = Presentation()
        self.prs.slide_width = Inches(SLIDE_WIDTH_IN)
        self.prs.slide_height = Inches(SLIDE_HEIGHT_IN)
        self.kicker = kicker
        self.page = 0

    @staticmethod
    def rgb(value: str) -> RGBColor:
        return RGBColor.from_string(value)

    def text(
        self,
        slide,
        content: object,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        size: float = 12,
        color: str = GRAY_900,
        bold: bool = False,
        align=PP_ALIGN.LEFT,
        valign=MSO_ANCHOR.TOP,
    ):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        frame = box.text_frame
        frame.clear()
        frame.word_wrap = True
        frame.vertical_anchor = valign
        frame.margin_left = frame.margin_right = Inches(0)
        frame.margin_top = frame.margin_bottom = Inches(0)
        paragraph = frame.paragraphs[0]
        paragraph.text = str(content)
        paragraph.alignment = align
        paragraph.font.name = FONT
        paragraph.font.size = Pt(size)
        paragraph.font.bold = bold
        paragraph.font.color.rgb = self.rgb(color)
        return box

    def rule(
        self,
        slide,
        x: float,
        y: float,
        w: float,
        *,
        color: str = GRAY_300,
        height: float = 0.012,
    ):
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(height)
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = self.rgb(color)
        shape.line.fill.background()
        return shape

    def block(self, slide, x: float, y: float, w: float, h: float, color: str):
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = self.rgb(color)
        shape.line.fill.background()
        shape.shadow.inherit = False
        return shape

    def blank(self):
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = self.rgb(WHITE)
        return slide

    def slide(self, title: str, kicker: str | None = None):
        slide = self.blank()
        self.text(
            slide,
            kicker or self.kicker,
            MARGIN_IN,
            0.28,
            8.0,
            0.22,
            size=10,
            color=ORANGE,
            bold=True,
        )
        self.text(
            slide, title, MARGIN_IN, 0.57, 12.1, 0.48, size=22, color=BLACK, bold=True
        )
        self.rule(slide, MARGIN_IN, 1.15, CONTENT_WIDTH_IN, color=GRAY_300, height=0.018)
        return slide

    def footer(self, slide, source: str) -> None:
        self.page += 1
        self.rule(slide, MARGIN_IN, 6.95, CONTENT_WIDTH_IN, color=GRAY_200, height=0.01)
        self.text(slide, source, MARGIN_IN, 7.02, 11.45, 0.3, size=8, color=GRAY_500)
        self.text(
            slide,
            str(self.page),
            12.25,
            7.01,
            0.42,
            0.22,
            size=8,
            color=GRAY_500,
            align=PP_ALIGN.RIGHT,
        )

    def stat_cards(
        self, slide, cards: list[tuple[str, str, str]], y: float = 1.45
    ) -> float:
        """Render up to four headline figures across the content width."""

        for index, (label, value, note) in enumerate(cards):
            x = MARGIN_IN + index * 3.06
            self.block(slide, x, y, 2.86, 1.16, GRAY_100)
            self.text(slide, label.upper(), x + 0.2, y + 0.15, 2.5, 0.22, size=9, color=GRAY_500, bold=True)
            self.text(slide, value, x + 0.2, y + 0.41, 2.5, 0.42, size=20, color=BLACK, bold=True)
            self.text(slide, note, x + 0.2, y + 0.85, 2.5, 0.22, size=9, color=GRAY_500)
        return y + 1.16

    def table(
        self,
        slide,
        rows: list[list[str]],
        x: float,
        y: float,
        widths: list[float],
        *,
        highlight: int | None = None,
        row_height: float = 0.34,
        size: float = 11,
        align_right_from: int = 2,
        aligns: str | None = None,
    ) -> float:
        """Render a light, borderless table; returns the bottom y coordinate.

        ``aligns`` overrides ``align_right_from`` with one character per column:
        ``l`` for left, ``r`` for right.
        """

        header, *body = rows
        # A right-aligned column followed by a left-aligned one would touch at
        # the shared boundary, so every cell is inset by half a gutter.
        gutter = 0.07

        def alignment(index: int):
            if aligns is not None and index < len(aligns):
                return PP_ALIGN.RIGHT if aligns[index] == "r" else PP_ALIGN.LEFT
            return PP_ALIGN.RIGHT if index >= align_right_from else PP_ALIGN.LEFT

        def cell_box(index: int) -> tuple[float, float]:
            return (
                x + sum(widths[:index]) + gutter,
                max(widths[index] - 2 * gutter, 0.2),
            )

        cursor = y
        for index, label in enumerate(header):
            cell_x, cell_w = cell_box(index)
            self.text(
                slide,
                label,
                cell_x,
                cursor,
                cell_w,
                row_height,
                size=size - 1,
                color=GRAY_500,
                bold=True,
                align=alignment(index),
            )
        cursor += row_height * 0.85
        self.rule(slide, x, cursor, sum(widths), color=GRAY_300, height=0.012)
        cursor += 0.10

        for position, row in enumerate(body):
            is_house = highlight is not None and position == highlight
            if is_house:
                self.block(
                    slide,
                    x - 0.12,
                    cursor - 0.05,
                    sum(widths) + 0.24,
                    row_height,
                    ORANGE_LIGHT,
                )
            for index, value in enumerate(row):
                cell_x, cell_w = cell_box(index)
                self.text(
                    slide,
                    value,
                    cell_x,
                    cursor,
                    cell_w,
                    row_height,
                    size=size,
                    color=BLACK if is_house else GRAY_900,
                    bold=is_house,
                    align=alignment(index),
                )
            cursor += row_height
            if position < len(body) - 1:
                self.rule(
                    slide, x, cursor - 0.05, sum(widths), color=GRAY_200, height=0.008
                )
        return cursor

    def save(self, path) -> None:
        self.prs.save(path)


__all__ = [
    "BLACK",
    "CONTENT_WIDTH_IN",
    "Deck",
    "FONT",
    "GRAY_100",
    "GRAY_200",
    "GRAY_300",
    "GRAY_500",
    "GRAY_700",
    "GRAY_900",
    "HOUSE_BLUE",
    "MARGIN_IN",
    "NEUTRAL",
    "ORANGE",
    "ORANGE_LIGHT",
    "SLIDE_HEIGHT_IN",
    "SLIDE_WIDTH_IN",
    "WHITE",
    "fmt_mm",
    "fmt_pct",
    "fmt_pp",
    "fmt_rank",
]
