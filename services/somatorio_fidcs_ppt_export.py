"""Soma de FIDCs — deck v3 para comitê de crédito.

Estrutura: 7 + 4 slides por FIDC da seleção + tabelas de rentabilidade
  1  Capa
  2  Divisor 01 — Visão consolidada
  3  Consolidado: PL por classe + subordinação + NPL + cobertura
  4  Consolidado: Carteira + crescimento YoY + NPL por severidade + roll rates
  5  Consolidado: Duration por FIDC + cohorts recentes
  6  Consolidado: Roll rates por mês do ano (placeholder se sem dados)
  7+ Blocos individuais por FIDC carregado
  N  Síntese — Pontos de atenção e destaques
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from services.export_chart_labels import choose_export_label_policy, format_export_label
from services.fund_return_disclosures import CVM_RETURN_REINVESTMENT_NOTE
from services.fund_return_matrix import (
    RETURN_ISSUANCE_SPREAD_COLUMN,
    RETURN_SERIES_COLUMN,
    RETURN_TRAILING_12M_CDI_COLUMN,
    RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN,
    RETURN_TRAILING_12M_COLUMN,
    RETURN_TRAILING_12M_SPREAD_GAP_COLUMN,
    RETURN_YTD_CDI_COLUMN,
    RETURN_YTD_IMPLIED_SPREAD_COLUMN,
    RETURN_YTD_COLUMN,
    RETURN_YTD_SPREAD_GAP_COLUMN,
    build_fund_return_matrix,
    format_fund_return_matrix,
)
from services.fund_name_display import short_fund_name

# ---------------------------------------------------------------------------
# Paleta de cores
# ---------------------------------------------------------------------------
_BLACK = "1F1F1F"
_ORANGE = "EC7000"
_GRAY = "6B6B6B"
_GRAY_LIGHT = "E5E5E5"
_GRAY_MID = "9C9C9C"
_GRAY_PALE = "BDBDBD"
_CARD_BG = "F5F5F5"
_WHITE = "FFFFFF"
_DARK_BG = "1F1F1F"   # capa e divisores
_SUBTITLE_FG = "CCCCCC"

# ---------------------------------------------------------------------------
# Abreviações de mês
# ---------------------------------------------------------------------------
_PT_MONTH = {
    1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
    7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez",
}

# ---------------------------------------------------------------------------
# Mapeamento de nomes longos → (header curto, subtítulo)
# ---------------------------------------------------------------------------
_FUND_NAMES: dict[str, tuple[str, str]] = {
    # chaves normalizadas (upper + strip)
    "MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA": (
        "Mercado Crédito FIDC",
        "Mercado Crédito Fundo de Investimento em Direitos Creditórios Resp. Ltda.",
    ),
    "MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA": (
        "Mercado Crédito I Brasil FIDC",
        "Mercado Crédito I Brasil FIDC Segmento Financeiro Resp. Ltda.",
    ),
    "MERCADO CRÉDITO II BRASIL FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS DE RESPONSABILIDADE LIMITADA": (
        "Mercado Crédito II Brasil FIDC",
        "Mercado Crédito II Brasil Fundo de Investimento em Direitos Creditórios Resp. Ltda.",
    ),
}

# Fallback: prefixo parcial
_FUND_PREFIXES = [
    ("MERCADO CRÉDITO II BRASIL", "Mercado Crédito II Brasil FIDC",
     "Mercado Crédito II Brasil Fundo de Investimento em Direitos Creditórios Resp. Ltda."),
    ("MERCADO CRÉDITO I BRASIL", "Mercado Crédito I Brasil FIDC",
     "Mercado Crédito I Brasil FIDC Segmento Financeiro Resp. Ltda."),
    ("MERCADO CRÉDITO", "Mercado Crédito FIDC",
     "Mercado Crédito Fundo de Investimento em Direitos Creditórios Resp. Ltda."),
]

# ---------------------------------------------------------------------------
# Geometria do slide
# ---------------------------------------------------------------------------
_SW = 13.333   # largura
_SH = 7.5      # altura
_HDR_H = 0.50  # banda header
_KPI_TOP = 0.55
_KPI_H = 0.70
_CTX_TOP = _KPI_TOP + _KPI_H + 0.08   # ~ 1.33"
_FTR_TOP = 7.20
_MX = 0.50     # margem horizontal
_CTX_H = _FTR_TOP - _CTX_TOP          # ~ 5.87"
_GAP_X = 0.15
_GAP_Y = 0.20

_RETURN_ROWS_PER_SLIDE = 22

_RETURN_COMPARISON_COLUMNS = (
    RETURN_SERIES_COLUMN,
    RETURN_TRAILING_12M_COLUMN,
    RETURN_TRAILING_12M_CDI_COLUMN,
    RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN,
    RETURN_YTD_COLUMN,
    RETURN_YTD_CDI_COLUMN,
    RETURN_YTD_IMPLIED_SPREAD_COLUMN,
    RETURN_ISSUANCE_SPREAD_COLUMN,
    RETURN_TRAILING_12M_SPREAD_GAP_COLUMN,
    RETURN_YTD_SPREAD_GAP_COLUMN,
)
_RETURN_SUMMARY_COLUMNS = frozenset(_RETURN_COMPARISON_COLUMNS)
_RETURN_COMPARISON_DETAIL_COLUMNS = frozenset(
    column
    for column in _RETURN_COMPARISON_COLUMNS
    if column not in {RETURN_SERIES_COLUMN, RETURN_TRAILING_12M_COLUMN, RETURN_YTD_COLUMN}
)

# ===========================================================================
# ENTRY POINT
# ===========================================================================

def build_somatorio_fidcs_pptx_bytes(
    *,
    outputs: Any,
    monitor_outputs: Any,
    research_outputs: Any | None = None,
    monthly_cdi_rates_by_fund: Mapping[str, Iterable[Any]] | None = None,
    benchmark_spreads_by_fund: Mapping[str, Mapping[str, float]] | None = None,
    portfolio_mode: bool = False,
    portfolio_name: str | None = None,
    generated_at: datetime | None = None,
    compact: bool = False,
) -> bytes:
    """Gera o deck v3 completo em formato PPTX."""
    try:
        from pptx import Presentation
        from pptx.chart.data import CategoryChartData
        from pptx.dml.color import RGBColor
        from pptx.enum.chart import (
            XL_CHART_TYPE, XL_DATA_LABEL_POSITION, XL_LABEL_POSITION,
            XL_LEGEND_POSITION, XL_MARKER_STYLE,
        )
        from pptx.util import Inches, Pt
    except ImportError as exc:
        raise RuntimeError("Dependência python-pptx não instalada.") from exc

    prs = Presentation()
    prs.slide_width = Inches(_SW)
    prs.slide_height = Inches(_SH)
    layout = prs.slide_layouts[6]

    deps = dict(
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_DATA_LABEL_POSITION=XL_DATA_LABEL_POSITION,
        XL_LABEL_POSITION=XL_LABEL_POSITION,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
        portfolio_mode=portfolio_mode,
        compact=bool(portfolio_mode and compact),
        portfolio_name=portfolio_name or str((getattr(outputs, "metadata", {}) or {}).get("portfolio_name") or "Carteira"),
    )

    # Data-base: último mês do consolidado
    con_monthly = _last_12m(getattr(outputs, "consolidated_monthly", pd.DataFrame()))
    data_base = _detect_data_base(con_monthly)

    # Mapa fund_cnpj → DataFrames
    fund_monthly_map = {
        cnpj: _last_12m(frame)
        for cnpj, frame in getattr(outputs, "fund_monthly", {}).items()
    }
    fund_monitor_map = {
        cnpj: _chart_monthly(frame)
        for cnpj, frame in getattr(monitor_outputs, "fund_monitor", {}).items()
    }
    fund_cohort_map = getattr(monitor_outputs, "fund_cohorts", {})
    con_monitor = _chart_monthly(getattr(monitor_outputs, "consolidated_monitor", pd.DataFrame()))
    con_cohorts = getattr(monitor_outputs, "consolidated_cohorts", pd.DataFrame())
    roll_df = getattr(research_outputs, "roll_seasonality", pd.DataFrame()) if research_outputs else pd.DataFrame()
    fund_sections = _build_fund_sections(outputs, fund_monthly_map)
    if portfolio_mode:
        fund_sections = [
            (number, cnpj, short_fund_name(raw_name), "Estrutura, crédito e rentabilidade", raw_name)
            for number, cnpj, _header, _subtitle, raw_name in fund_sections
        ]
    fund_return_pages = _build_fund_return_pages(
        outputs,
        fund_sections,
        monthly_cdi_rates_by_fund=monthly_cdi_rates_by_fund,
        benchmark_spreads_by_fund=benchmark_spreads_by_fund,
    )
    total_slides = (
        7
        + 4 * len(fund_sections)
        + sum(len(pages) for pages in fund_return_pages.values())
    )

    page = [0]  # mutable counter

    def next_page() -> int:
        page[0] += 1
        return page[0]

    # ---- Slide 1: Capa ----
    _add_cover(prs, layout, data_base, **deps)
    next_page()

    # ---- Slide 2: Divisor 01 ----
    if not deps["compact"]:
        _add_divider(prs, layout, "01", "Visão consolidada",
                     "PL, carteira, risco e duration agregados", **deps)
        next_page()

    # ---- Slides 3–6: Consolidado ----
    consolidated_title = "Carteira — Consolidado" if portfolio_mode else "Soma de FIDCs — Consolidado"
    _add_base_slide(prs, layout, con_monthly, con_monitor, consolidated_title,
                    next_page(), total_slides, data_base, is_subordination_fund=False, **deps)
    _add_credit_slide(prs, layout, con_monitor, consolidated_title,
                      next_page(), total_slides, data_base, **deps)
    _add_detail_slide(prs, layout, con_monitor, fund_monitor_map, con_cohorts,
                      consolidated_title,
                      next_page(), total_slides, data_base, **deps)
    _add_roll_slide(prs, layout, con_monitor, roll_df, consolidated_title,
                    next_page(), total_slides, data_base, **deps)

    # ---- Per-fund blocks ----
    for sec_num, cnpj, hdr, sub, raw_name in fund_sections:
        fund_slide_start = len(prs.slides)
        if not deps["compact"]:
            _add_divider(prs, layout, sec_num, hdr, sub, **deps)
            next_page()

        fm = fund_monthly_map.get(cnpj, pd.DataFrame()) if cnpj else pd.DataFrame()
        mon = fund_monitor_map.get(cnpj, pd.DataFrame()) if cnpj else pd.DataFrame()
        coh = fund_cohort_map.get(cnpj, pd.DataFrame()) if cnpj else pd.DataFrame()
        is_mc_fidc = _is_mercado_credito_zero(raw_name)
        fund_data_base = _portfolio_data_base(fm) if portfolio_mode else data_base
        empty_monthly = deps["compact"] and fm.empty and mon.empty and coh.empty

        return_pages = fund_return_pages.get(cnpj, [])
        return_groups = _portfolio_return_groups(return_pages) if deps["compact"] else [(frame,) for frame in return_pages]
        for page_index, return_group in enumerate(return_groups, start=1):
            _add_fund_return_slide(
                prs,
                layout,
                return_group[0],
                hdr,
                next_page(),
                total_slides,
                fund_data_base,
                page_index=page_index,
                page_count=len(return_groups),
                **deps,
            )
            if len(return_group) == 2:
                _append_paired_return_table(prs, layout, return_group[1], hdr, fund_data_base, **deps)

        empty_inline = empty_monthly and bool(return_groups) and _append_empty_monthly_record(prs.slides[-1], **deps)
        if not empty_inline:
            _add_base_slide(prs, layout, fm, mon, hdr,
                            next_page(), total_slides, fund_data_base,
                            is_subordination_fund=is_mc_fidc, empty_monthly=empty_monthly, **deps)
        if not empty_monthly:
            _add_credit_slide(prs, layout, mon, hdr,
                              next_page(), total_slides, fund_data_base, **deps)
            _add_detail_slide(prs, layout, mon, {}, coh, hdr,
                              next_page(), total_slides, fund_data_base, **deps)
        else:
            _append_portfolio_notes(
                prs.slides[-1],
                "Compactação: crédito e duration sem observação mensal na janela foram reunidos neste quadro. "
                "Retornos disponíveis continuam em suas tabelas próprias; ausência de informe não foi tratada como zero.",
            )
        if portfolio_mode:
            for fund_slide in list(prs.slides)[fund_slide_start:]:
                _append_portfolio_notes(
                    fund_slide,
                    f"Fundo: {raw_name}\nCNPJ: {cnpj}\nÚltima competência deste fundo na janela: {fund_data_base}.",
                )

    # ---- Slide 19: Síntese ----
    _add_synthesis(
        prs,
        layout,
        next_page(),
        total_slides,
        data_base,
        consolidated_monitor=con_monitor,
        consolidated_monthly=con_monthly,
        fund_monitor_map=fund_monitor_map,
        fund_monthly_map=fund_monthly_map,
        **deps,
    )

    if portfolio_mode:
        generated = generated_at or datetime.now(timezone.utc)
        _append_portfolio_notes(
            prs.slides[0],
            "Carteira: " + deps["portfolio_name"] + "\n"
            + "Gerado em: " + generated.isoformat() + "\n"
            + "Fonte: Informe Mensal CVM. Unidade e perímetro seguem os indicadores originais.\n"
            + "Nomes e CNPJs da cesta:\n"
            + "\n".join(f"{raw_name} — {cnpj}" for _, cnpj, _, _, raw_name in fund_sections),
        )
        _refine_portfolio_native_presentation(prs, compact=deps["compact"])
        if deps["compact"]:
            first_content = prs.slides[1]
            _append_portfolio_notes(first_content, "Compactação: divisores separados foram integrados aos títulos dos fundos; nenhuma identidade da cesta foi retirada.")
            for index, slide in enumerate(prs.slides, start=1):
                for shape in slide.shapes:
                    if shape.has_text_frame and shape.text.startswith("Página "):
                        shape.text_frame.paragraphs[0].runs[0].text = f"Página {index} de {len(prs.slides)}"

    buf = BytesIO()
    prs.save(buf)
    return _normalize_pptx_native_number_formats(buf.getvalue())


# ===========================================================================
# STRUCTURAL SLIDES
# ===========================================================================

def _add_cover(prs, layout, data_base: str, *, Inches, Pt, RGBColor, **_kw) -> None:
    slide = prs.slides.add_slide(layout)
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = _rgb(_DARK_BG, RGBColor)

    # Linha laranja vertical (4pt × 1.5")
    line = slide.shapes.add_shape(1, Inches(0.60), Inches(2.80), Inches(4 / 72), Inches(1.5))
    line.fill.solid()
    line.fill.fore_color.rgb = _rgb(_ORANGE, RGBColor)
    line.line.fill.background()

    # Título principal
    portfolio_mode = bool(_kw.get("portfolio_mode"))
    cover_title = str(_kw.get("portfolio_name") or "Carteira") if portfolio_mode else "Mercado de FIDCs"
    _textbox(slide, cover_title,
             left=1.0, top=2.50, width=10.0, height=1.30 if portfolio_mode else 0.80,
             size=32 if portfolio_mode else 44, bold=True, color=_WHITE,
             word_wrap=portfolio_mode, Inches=Inches, Pt=Pt, RGBColor=RGBColor)

    # Subtítulo
    subtitle = f"Visão consolidada e por fundo — Data-base {data_base}"
    _textbox(slide, subtitle,
             left=1.0, top=4.00 if portfolio_mode else 3.50, width=10.5, height=0.45,
             size=18, bold=False, color=_SUBTITLE_FG, Inches=Inches, Pt=Pt, RGBColor=RGBColor)

    # Rodapé canto inferior direito
    _textbox(slide, "Toma Conta" if portfolio_mode else "Análise Setorial de Crédito",
             left=_SW - 5.5, top=_SH - 0.50, width=5.0, height=0.35,
             size=10, bold=False, color=_SUBTITLE_FG,
             align_right=True, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    if _kw.get("compact"):
        _textbox(slide, "Divisores integrados aos títulos. Retornos complementares reunidos quando cabem.\nSéries compactadas ficam identificadas nos quadros e nas notas.",
                 left=1.0, top=5.50, width=10.5, height=0.60, size=12, bold=False, color=_SUBTITLE_FG,
                 word_wrap=True, Inches=Inches, Pt=Pt, RGBColor=RGBColor)


def _add_divider(
    prs, layout, number: str, title: str, subtitle: str,
    *, Inches, Pt, RGBColor, **_kw
) -> None:
    slide = prs.slides.add_slide(layout)
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = _rgb(_DARK_BG, RGBColor)

    # Numeração laranja
    _textbox(slide, f"{number} —",
             left=1.0, top=2.60, width=3.0, height=0.45,
             size=24, bold=True, color=_ORANGE, Inches=Inches, Pt=Pt, RGBColor=RGBColor)

    # Título branco
    _textbox(slide, title,
             left=1.0, top=3.10, width=11.0, height=0.60,
             size=32, bold=True, color=_WHITE, Inches=Inches, Pt=Pt, RGBColor=RGBColor)

    # Subtítulo cinza claro
    _textbox(slide, subtitle,
             left=1.0, top=3.80, width=11.0, height=0.40,
             size=14, bold=False, color=_SUBTITLE_FG, Inches=Inches, Pt=Pt, RGBColor=RGBColor)


def _add_synthesis(
    prs, layout, page_num: int, total: int, data_base: str,
    *,
    consolidated_monitor: pd.DataFrame,
    consolidated_monthly: pd.DataFrame,
    fund_monitor_map: dict[str, pd.DataFrame],
    fund_monthly_map: dict[str, pd.DataFrame],
    Inches, Pt, RGBColor, **_kw
) -> None:
    slide = prs.slides.add_slide(layout)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(_WHITE, RGBColor)

    _slide_header(slide, "Síntese — Pontos de atenção e destaques", data_base,
                  Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    _slide_footer(slide, page_num, total, Inches=Inches, Pt=Pt, RGBColor=RGBColor)

    col_top = _HDR_H + 0.15
    col_w = 5.50
    col_gap = 0.50
    col_left_1 = _MX
    col_left_2 = _MX + col_w + col_gap

    sections = _build_synthesis_sections(
        consolidated_monitor=consolidated_monitor,
        consolidated_monthly=consolidated_monthly,
        fund_monitor_map=fund_monitor_map,
        fund_monthly_map=fund_monthly_map,
    )
    if _kw.get("compact"):
        sections = _compact_synthesis_sections(
            slide, sections, consolidated_monitor, fund_monthly_map, fund_monitor_map,
        )

    for col_left, hdr_color, hdr_text, bullets in [
        (col_left_1, _ORANGE, "Pontos de atenção", sections["attention"]),
        (col_left_2, _BLACK, "Destaques positivos", sections["highlights"]),
    ]:
        if _kw.get("portfolio_mode"):
            hdr_color = _BLACK
        if _kw.get("compact"):
            hdr_text = "Crédito e cobertura" if col_left == col_left_1 else "Carteira e estrutura"
        _textbox(slide, hdr_text,
                 left=col_left, top=col_top, width=col_w, height=0.35,
                 size=16, bold=True, color=hdr_color,
                 Inches=Inches, Pt=Pt, RGBColor=RGBColor)
        bullet_top = col_top + 0.45
        for bullet in bullets:
            _textbox(slide, f"• {bullet}",
                     left=col_left, top=bullet_top, width=col_w, height=0.58,
                     size=12.5, bold=False, color=_BLACK,
                     word_wrap=True,
                     Inches=Inches, Pt=Pt, RGBColor=RGBColor)
            bullet_top += 0.70


# ===========================================================================
# CONTENT SLIDES
# ===========================================================================

def _add_base_slide(
    prs, layout,
    monthly_df: pd.DataFrame,
    monitor_df: pd.DataFrame,
    title: str,
    page_num: int, total: int, data_base: str,
    *,
    is_subordination_fund: bool = False,
    Inches, Pt, RGBColor,
    CategoryChartData, XL_CHART_TYPE, XL_DATA_LABEL_POSITION,
    XL_LEGEND_POSITION, **_kw,
) -> None:
    if _kw.get("compact"):
        return _add_compact_base_slide(prs, layout, monthly_df, monitor_df, title, page_num, total, data_base,
                                      is_subordination_fund=is_subordination_fund,
                                      Inches=Inches, Pt=Pt, RGBColor=RGBColor,
                                      CategoryChartData=CategoryChartData, XL_CHART_TYPE=XL_CHART_TYPE,
                                      XL_DATA_LABEL_POSITION=XL_DATA_LABEL_POSITION, XL_LEGEND_POSITION=XL_LEGEND_POSITION, **_kw)
    slide = prs.slides.add_slide(layout)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(_WHITE, RGBColor)

    _slide_header(slide, title, data_base, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    _slide_footer(slide, page_num, total, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    _kpi_strip(slide, monitor_df, monthly_df, portfolio_mode=bool(_kw.get("portfolio_mode")), Inches=Inches, Pt=Pt, RGBColor=RGBColor)

    df = monthly_df
    cats = _category_labels(df)
    slots = _grid_2x2(portfolio_mode=bool(_kw.get("portfolio_mode")))

    _chart_pl_stacked(slide, slots[0], df, cats,
                      CategoryChartData=CategoryChartData, RGBColor=RGBColor,
                      XL_CHART_TYPE=XL_CHART_TYPE, XL_LEGEND_POSITION=XL_LEGEND_POSITION,
                      XL_DATA_LABEL_POSITION=XL_DATA_LABEL_POSITION,
                      Inches=Inches, Pt=Pt)
    _chart_percent_line(slide, slots[1],
                        title="% Subordinação Total ex-360",
                        column="subordinacao_total_ex360_pct",
                        df=df, cats=cats, color=_GRAY,
                        portfolio_mode=bool(_kw.get("portfolio_mode")),
                        clip_outlier=is_subordination_fund,
                        CategoryChartData=CategoryChartData, RGBColor=RGBColor,
                        XL_CHART_TYPE=XL_CHART_TYPE, Inches=Inches, Pt=Pt)
    _chart_percent_line(slide, slots[2],
                        title="NPL Over 90d ex-360 / Carteira",
                        column="npl_over90_ex360_pct",
                        df=df, cats=cats, color=_BLACK, metric_kind="npl_pct",
                        portfolio_mode=bool(_kw.get("portfolio_mode")),
                        CategoryChartData=CategoryChartData, RGBColor=RGBColor,
                        XL_CHART_TYPE=XL_CHART_TYPE, Inches=Inches, Pt=Pt)
    _chart_percent_line(slide, slots[3],
                        title="Cobertura PDD / NPL Over 90d ex-360",
                        column="pdd_npl_over90_ex360_pct",
                        df=df, cats=cats, color=_ORANGE, metric_kind="coverage_pct",
                        portfolio_mode=bool(_kw.get("portfolio_mode")),
                        CategoryChartData=CategoryChartData, RGBColor=RGBColor,
                        XL_CHART_TYPE=XL_CHART_TYPE, Inches=Inches, Pt=Pt)


def _add_credit_slide(
    prs, layout,
    monitor_df: pd.DataFrame,
    title: str,
    page_num: int, total: int, data_base: str,
    *, Inches, Pt, RGBColor,
    CategoryChartData, XL_CHART_TYPE, XL_LABEL_POSITION,
    XL_LEGEND_POSITION, XL_MARKER_STYLE, **_kw,
) -> None:
    if _kw.get("compact"):
        return _add_compact_credit_slide(prs, layout, monitor_df, title, page_num, total, data_base,
                                        Inches=Inches, Pt=Pt, RGBColor=RGBColor,
                                        CategoryChartData=CategoryChartData, XL_CHART_TYPE=XL_CHART_TYPE,
                                        XL_LABEL_POSITION=XL_LABEL_POSITION, XL_LEGEND_POSITION=XL_LEGEND_POSITION,
                                        XL_MARKER_STYLE=XL_MARKER_STYLE, **_kw)
    slide = prs.slides.add_slide(layout)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(_WHITE, RGBColor)

    _slide_header(slide, title, data_base, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    _slide_footer(slide, page_num, total, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    _kpi_strip(slide, monitor_df, pd.DataFrame(), portfolio_mode=bool(_kw.get("portfolio_mode")), Inches=Inches, Pt=Pt, RGBColor=RGBColor)

    df = monitor_df
    cats = _category_labels(df)
    slots = _grid_2x2(portfolio_mode=bool(_kw.get("portfolio_mode")))

    _chart_bar_money(slide, slots[0], title="Carteira Bruta ex-360",
                     column="carteira_ex360", series_name="Carteira Bruta ex-360",
                     df=df, cats=cats,
                     CategoryChartData=CategoryChartData, RGBColor=RGBColor,
                     XL_CHART_TYPE=XL_CHART_TYPE,
                     XL_LABEL_POSITION=XL_LABEL_POSITION,
                     Inches=Inches, Pt=Pt)
    _chart_multi_line(slide, slots[1], title="Crescimento YoY carteira bruta ex-360",
                      df=df, cats=cats,
                      series_specs=[("Crescimento YoY", "carteira_ex360_yoy_pct", _ORANGE)],
                      y_title="%", value_is_percent=True,
                      CategoryChartData=CategoryChartData, RGBColor=RGBColor,
                      XL_CHART_TYPE=XL_CHART_TYPE, XL_LABEL_POSITION=XL_LABEL_POSITION,
                      XL_LEGEND_POSITION=XL_LEGEND_POSITION, XL_MARKER_STYLE=XL_MARKER_STYLE,
                      Inches=Inches, Pt=Pt)
    _chart_stacked_npl(slide, slots[2], df=df, cats=cats,
                       CategoryChartData=CategoryChartData, RGBColor=RGBColor,
                       XL_CHART_TYPE=XL_CHART_TYPE,
                       XL_LABEL_POSITION=XL_LABEL_POSITION,
                       XL_LEGEND_POSITION=XL_LEGEND_POSITION,
                       Inches=Inches, Pt=Pt)
    _chart_multi_line(slide, slots[3], title="Roll rates",
                      df=df, cats=cats,
                      series_specs=[
                          ("Roll 61-90 M-3", "roll_61_90_m3_pct", _BLACK),
                          ("Roll 91-120 M-4", "roll_91_120_m4_pct", _GRAY),
                          ("Roll 121-150 M-5", "roll_121_150_m5_pct", _GRAY_MID),
                          ("Roll 151-180 M-6", "roll_151_180_m6_pct", _ORANGE),
                      ],
                      y_title="%", value_is_percent=True, metric_kind="roll_pct",
                      CategoryChartData=CategoryChartData, RGBColor=RGBColor,
                      XL_CHART_TYPE=XL_CHART_TYPE, XL_LABEL_POSITION=XL_LABEL_POSITION,
                      XL_LEGEND_POSITION=XL_LEGEND_POSITION, XL_MARKER_STYLE=XL_MARKER_STYLE,
                      Inches=Inches, Pt=Pt)


def _add_detail_slide(
    prs, layout,
    monitor_df: pd.DataFrame,
    fund_monitor_map: dict[str, pd.DataFrame],
    cohort_df: pd.DataFrame,
    title: str,
    page_num: int, total: int, data_base: str,
    *, Inches, Pt, RGBColor,
    CategoryChartData, XL_CHART_TYPE, XL_LABEL_POSITION,
    XL_LEGEND_POSITION, XL_MARKER_STYLE, **_kw,
) -> None:
    if _kw.get("compact"):
        return _add_compact_detail_slide(prs, layout, monitor_df, fund_monitor_map, cohort_df, title, page_num, total, data_base,
                                        Inches=Inches, Pt=Pt, RGBColor=RGBColor,
                                        CategoryChartData=CategoryChartData, XL_CHART_TYPE=XL_CHART_TYPE,
                                        XL_LABEL_POSITION=XL_LABEL_POSITION, XL_LEGEND_POSITION=XL_LEGEND_POSITION,
                                        XL_MARKER_STYLE=XL_MARKER_STYLE, **_kw)
    slide = prs.slides.add_slide(layout)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(_WHITE, RGBColor)

    _slide_header(slide, title, data_base, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    _slide_footer(slide, page_num, total, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    _kpi_strip(slide, monitor_df, pd.DataFrame(), portfolio_mode=bool(_kw.get("portfolio_mode")), Inches=Inches, Pt=Pt, RGBColor=RGBColor)

    slots = _grid_1x2(portfolio_mode=bool(_kw.get("portfolio_mode")))

    # Duration chart — legenda ABAIXO do eixo X para evitar colisão
    dur_df = _build_duration_frame(monitor_df, fund_monitor_map)
    dur_series = [c for c in dur_df.columns if c not in {"competencia_dt", "competencia"}]
    dur_specs = [(s, _short_name(s), color)
                 for s, color in zip(dur_series, [_BLACK, _ORANGE, _GRAY, _GRAY_MID])]
    if _kw.get("portfolio_mode"):
        colors = [_BLACK, _ORANGE, _GRAY, _GRAY_MID, _GRAY_PALE, "383838", "585858"]
        dur_specs = [(short_fund_name(series), series, colors[index % len(colors)])
                     for index, series in enumerate(dur_series)]
        if fund_monitor_map:
            missing_duration = [
                cnpj for cnpj, frame in fund_monitor_map.items()
                if frame.empty or "duration_months" not in frame.columns
                or pd.to_numeric(frame["duration_months"], errors="coerce").notna().sum() == 0
            ]
            if missing_duration:
                slots = [(left, top, width, height - 0.35) for left, top, width, height in slots]
                _textbox(
                    slide,
                    f"Duration: {len(fund_monitor_map) - len(missing_duration)}/{len(fund_monitor_map)} fundos com série. Ausentes nas notas.",
                    left=_MX, top=6.90, width=_SW - 2 * _MX, height=0.25,
                    size=11, bold=False, color=_GRAY, Inches=Inches, Pt=Pt, RGBColor=RGBColor,
                )
                _append_portfolio_notes(slide, "Duration sem série informada na janela: " + ", ".join(missing_duration))
    _chart_multi_line(slide, slots[0],
                      title="Duration por FIDC",
                      df=dur_df, cats=_category_labels(dur_df),
                      series_specs=dur_specs,
                      y_title="meses", value_is_percent=False, metric_kind="duration",
                      legend_below=True,
                      CategoryChartData=CategoryChartData, RGBColor=RGBColor,
                      XL_CHART_TYPE=XL_CHART_TYPE, XL_LABEL_POSITION=XL_LABEL_POSITION,
                      XL_LEGEND_POSITION=XL_LEGEND_POSITION, XL_MARKER_STYLE=XL_MARKER_STYLE,
                      Inches=Inches, Pt=Pt)
    _chart_cohorts(slide, slots[1], cohort_df=cohort_df,
                   CategoryChartData=CategoryChartData, RGBColor=RGBColor,
                   XL_CHART_TYPE=XL_CHART_TYPE, XL_LABEL_POSITION=XL_LABEL_POSITION,
                   XL_LEGEND_POSITION=XL_LEGEND_POSITION, XL_MARKER_STYLE=XL_MARKER_STYLE,
                   Inches=Inches, Pt=Pt)


def _add_fund_return_slide(
    prs,
    layout,
    return_frame: pd.DataFrame,
    title: str,
    page_num: int,
    total: int,
    data_base: str,
    *,
    page_index: int,
    page_count: int,
    Inches,
    Pt,
    RGBColor,
    **_kw,
) -> None:
    """Adiciona uma tabela PowerPoint nativa de rentabilidade por série."""
    from pptx.enum.text import MSO_VERTICAL_ANCHOR, PP_ALIGN

    slide = prs.slides.add_slide(layout)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(_WHITE, RGBColor)

    _slide_header(
        slide,
        f"{title} — Rentabilidade por série",
        data_base,
        Inches=Inches,
        Pt=Pt,
        RGBColor=RGBColor,
    )
    _slide_footer(slide, page_num, total, Inches=Inches, Pt=Pt, RGBColor=RGBColor)

    columns = return_frame.columns.tolist()
    is_comparison = any(column in columns for column in _RETURN_COMPARISON_DETAIL_COLUMNS)
    continuation = f" · Página {page_index} de {page_count}" if page_count > 1 else ""
    section_description = (
        "CDI realizado, spread implícito, CDI+ de emissão e gaps"
        if is_comparison
        else "Retornos mensais e acumulados (%) · Últimos 12 meses"
    )
    _textbox(
        slide,
        f"{section_description}{continuation}",
        left=_MX,
        top=0.55,
        width=_SW - 2 * _MX,
        height=0.22,
        size=9,
        bold=False,
        color=_GRAY,
        Inches=Inches,
        Pt=Pt,
        RGBColor=RGBColor,
    )

    table_top = 0.82
    header_height = 0.68 if is_comparison else 0.48
    row_height = 0.24
    table_height = header_height + row_height * len(return_frame)
    shape = slide.shapes.add_table(
        len(return_frame) + 1,
        len(columns),
        Inches(_MX),
        Inches(table_top),
        Inches(_SW - 2 * _MX),
        Inches(table_height),
    )
    table = shape.table
    table.first_row = True

    available_width = _SW - 2 * _MX
    if is_comparison:
        comparison_weights = {
            RETURN_SERIES_COLUMN: 2.0,
            RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN: 1.45,
            RETURN_YTD_IMPLIED_SPREAD_COLUMN: 1.45,
            RETURN_TRAILING_12M_SPREAD_GAP_COLUMN: 1.10,
            RETURN_YTD_SPREAD_GAP_COLUMN: 1.10,
        }
        weights = [comparison_weights.get(column, 1.18) for column in columns]
        total_weight = sum(weights) or 1.0
        for column_index, weight in enumerate(weights):
            table.columns[column_index].width = Inches(available_width * weight / total_weight)
    else:
        series_width = 1.85 if _kw.get("portfolio_mode") else 2.10
        trailing_width = 1.00 if _kw.get("portfolio_mode") else 1.50
        ytd_width = 1.00 if _kw.get("portfolio_mode") else 1.55
        month_columns = [column for column in columns if column not in _RETURN_SUMMARY_COLUMNS]
        month_width = (
            (available_width - series_width - trailing_width - ytd_width) / len(month_columns)
            if month_columns
            else 0.0
        )
        for column_index, column in enumerate(columns):
            if column == RETURN_SERIES_COLUMN:
                width = series_width
            elif column == RETURN_TRAILING_12M_COLUMN:
                width = trailing_width
            elif column == RETURN_YTD_COLUMN:
                width = ytd_width
            else:
                width = month_width
            table.columns[column_index].width = Inches(width)

    table.rows[0].height = Inches(header_height)
    for row_index in range(1, len(table.rows)):
        table.rows[row_index].height = Inches(row_height)

    for column_index, column in enumerate(columns):
        cell = table.cell(0, column_index)
        _style_return_table_cell(
            cell,
            _portfolio_return_header(str(column)) if _kw.get("portfolio_mode") else str(column),
            fill_color=_CARD_BG if _kw.get("portfolio_mode") else _ORANGE,
            text_color=_BLACK if _kw.get("portfolio_mode") else _WHITE,
            font_size=11 if _kw.get("portfolio_mode") else 6.0 if is_comparison else 6.5,
            bold=True,
            alignment=PP_ALIGN.LEFT if column == RETURN_SERIES_COLUMN else PP_ALIGN.CENTER,
            vertical_anchor=MSO_VERTICAL_ANCHOR.MIDDLE,
            word_wrap=True,
            Inches=Inches,
            Pt=Pt,
            RGBColor=RGBColor,
        )

    for row_index, (_, row) in enumerate(return_frame.iterrows(), start=1):
        fill_color = _WHITE if row_index % 2 else _CARD_BG
        for column_index, column in enumerate(columns):
            value = row.get(column)
            text = "N/D" if pd.isna(value) or str(value).strip() == "" else str(value)
            _style_return_table_cell(
                table.cell(row_index, column_index),
                text,
                fill_color=fill_color,
                text_color=_BLACK if text != "N/D" else _GRAY,
                font_size=11 if _kw.get("portfolio_mode") else 7.5,
                bold=column == RETURN_SERIES_COLUMN,
                alignment=PP_ALIGN.LEFT if column == RETURN_SERIES_COLUMN else PP_ALIGN.RIGHT,
                vertical_anchor=MSO_VERTICAL_ANCHOR.MIDDLE,
                word_wrap=False,
                Inches=Inches,
                Pt=Pt,
                RGBColor=RGBColor,
            )

    if _kw.get("portfolio_mode"):
        _append_portfolio_notes(
            slide,
            "Cabeçalhos completos de rentabilidade:\n"
            + "\n".join(f"{_portfolio_return_header(str(column))}: {column}" for column in columns),
        )

    _textbox(
        slide,
        f"* {CVM_RETURN_REINVESTMENT_NOTE}",
        left=_MX,
        top=6.82,
        width=_SW - 2 * _MX,
        height=0.38,
        size=7,
        bold=False,
        color=_GRAY,
        word_wrap=True,
        margin_vertical=0.01,
        Inches=Inches,
        Pt=Pt,
        RGBColor=RGBColor,
    )


def _style_return_table_cell(
    cell,
    text: str,
    *,
    fill_color: str,
    text_color: str,
    font_size: float,
    bold: bool,
    alignment,
    vertical_anchor,
    word_wrap: bool,
    Inches,
    Pt,
    RGBColor,
) -> None:
    cell.fill.solid()
    cell.fill.fore_color.rgb = _rgb(fill_color, RGBColor)
    text_frame = cell.text_frame
    text_frame.clear()
    text_frame.word_wrap = word_wrap
    text_frame.margin_left = Inches(0.035)
    text_frame.margin_right = Inches(0.035)
    text_frame.margin_top = Inches(0.01)
    text_frame.margin_bottom = Inches(0.01)
    text_frame.vertical_anchor = vertical_anchor
    paragraph = text_frame.paragraphs[0]
    paragraph.alignment = alignment
    run = paragraph.add_run()
    run.text = text
    run.font.name = "Calibri"
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.color.rgb = _rgb(text_color, RGBColor)


def _add_roll_slide(
    prs, layout,
    monitor_df: pd.DataFrame,
    roll_df: pd.DataFrame,
    title: str,
    page_num: int, total: int, data_base: str,
    *, Inches, Pt, RGBColor,
    CategoryChartData, XL_CHART_TYPE, XL_LABEL_POSITION,
    XL_LEGEND_POSITION, XL_MARKER_STYLE, **_kw,
) -> None:
    if _kw.get("compact"):
        return _add_compact_roll_slide(prs, layout, roll_df, title, page_num, total, data_base,
                                      Inches=Inches, Pt=Pt, RGBColor=RGBColor,
                                      CategoryChartData=CategoryChartData, XL_CHART_TYPE=XL_CHART_TYPE,
                                      XL_LABEL_POSITION=XL_LABEL_POSITION, XL_LEGEND_POSITION=XL_LEGEND_POSITION,
                                      XL_MARKER_STYLE=XL_MARKER_STYLE, **_kw)
    slide = prs.slides.add_slide(layout)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(_WHITE, RGBColor)

    _slide_header(slide, title, data_base, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    _slide_footer(slide, page_num, total, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    _kpi_strip(slide, monitor_df, pd.DataFrame(), portfolio_mode=bool(_kw.get("portfolio_mode")), Inches=Inches, Pt=Pt, RGBColor=RGBColor)

    if roll_df is None or not isinstance(roll_df, pd.DataFrame) or roll_df.empty:
        _empty_placeholder(slide, _grid_2x2(portfolio_mode=bool(_kw.get("portfolio_mode")))[0],
                           "Roll rates por mês do ano",
                           "Dados de sazonalidade não disponíveis.",
                           Inches=Inches, Pt=Pt, RGBColor=RGBColor)
        return

    slots = _grid_2x2(portfolio_mode=bool(_kw.get("portfolio_mode")))
    roll_metrics = [
        ("Roll 61-90 por mês do ano", "roll_61_90_m3"),
        ("Roll 91-120 por mês do ano", "roll_91_120_m4"),
        ("Roll 121-150 por mês do ano", "roll_121_150_m5"),
        ("Roll 151-180 por mês do ano", "roll_151_180_m6"),
    ]
    colors = [_BLACK, _GRAY, _GRAY_MID, _GRAY_PALE]
    for slot, (r_title, metric_id) in zip(slots, roll_metrics):
        chart_df = _research_roll_wide(roll_df, metric_id=metric_id)
        series = [c for c in chart_df.columns if c not in {"competencia_dt", "competencia", "month", "ordem"}]
        _chart_multi_line(slide, slot, title=r_title,
                          df=chart_df,
                          cats=chart_df.get("competencia", pd.Series(dtype="str")).astype(str).tolist(),
                          series_specs=[(s, s, colors[i % len(colors)]) for i, s in enumerate(series)],
                          y_title="%", value_is_percent=True, metric_kind="roll_pct",
                          CategoryChartData=CategoryChartData, RGBColor=RGBColor,
                          XL_CHART_TYPE=XL_CHART_TYPE, XL_LABEL_POSITION=XL_LABEL_POSITION,
                          XL_LEGEND_POSITION=XL_LEGEND_POSITION, XL_MARKER_STYLE=XL_MARKER_STYLE,
                          Inches=Inches, Pt=Pt)


# ===========================================================================
# CHROME: HEADER / FOOTER / KPI STRIP
# ===========================================================================

def _slide_header(slide, title: str, data_base: str, *, Inches, Pt, RGBColor) -> None:
    """Faixa superior: título (esq) + chip data-base (dir)."""
    # Título
    _textbox(slide, title,
             left=_MX, top=0.10, width=10.0, height=0.36,
             size=22, bold=True, color=_BLACK,
             Inches=Inches, Pt=Pt, RGBColor=RGBColor)

    # Chip "Data-base: mar/26" — retângulo arredondado #F5F5F5
    chip_w = 2.20
    chip_h = 0.32
    chip_left = _SW - _MX - chip_w
    chip_top = 0.09
    chip = slide.shapes.add_shape(5, Inches(chip_left), Inches(chip_top),
                                   Inches(chip_w), Inches(chip_h))
    chip.fill.solid()
    chip.fill.fore_color.rgb = _rgb(_CARD_BG, RGBColor)
    chip.line.fill.background()
    _shape_text(chip, f"Data-base: {data_base}", size=9, bold=False,
                color=_GRAY, Pt=Pt, RGBColor=RGBColor, align_center=True)


def _slide_footer(slide, page_num: int, total: int, *, Inches, Pt, RGBColor) -> None:
    """Faixa inferior: fonte (esq) + paginação (dir)."""
    y = _FTR_TOP + 0.04
    h = 0.22

    _textbox(slide, "Fonte: CVM Fundos.NET | Elaboração: Toma Conta",
             left=_MX, top=y, width=8.0, height=h,
             size=8, bold=False, color=_GRAY,
             Inches=Inches, Pt=Pt, RGBColor=RGBColor)

    _textbox(slide, f"Página {page_num} de {total}",
             left=_SW - _MX - 2.5, top=y, width=2.5, height=h,
             size=8, bold=False, color=_GRAY,
             align_right=True, Inches=Inches, Pt=Pt, RGBColor=RGBColor)


def _kpi_strip(
    slide, monitor_df: pd.DataFrame, monthly_df: pd.DataFrame,
    *, Inches, Pt, RGBColor, portfolio_mode: bool = False,
) -> None:
    """KPI cards v3: fundo #F5F5F5, cantos arredondados, sem borda."""
    cards = _build_kpi_cards(monitor_df, monthly_df)
    if not cards:
        return
    remaining = []
    if portfolio_mode:
        remaining = [(label.replace("NPL Over ", "NPL > ").replace(" ex-360", ""), value)
                     for label, value in cards[1:4]]
        cards = [("Carteira ex-360", cards[0][1]), ("NPL > 90d ex-360", cards[4][1]), cards[5]]

    total_w = _SW - _MX * 2
    gap = 0.15
    n = len(cards)
    card_w = (total_w - gap * (n - 1)) / n
    card_h = _KPI_H

    for i, (label, value) in enumerate(cards):
        left = _MX + i * (card_w + gap)
        top = _KPI_TOP

        card = slide.shapes.add_shape(
            5, Inches(left), Inches(top), Inches(card_w), Inches(card_h))
        card.fill.solid()
        card.fill.fore_color.rgb = _rgb(_CARD_BG, RGBColor)
        card.line.fill.background()

        tf = card.text_frame
        tf.word_wrap = not portfolio_mode
        tf.margin_left = Inches(0.06)
        tf.margin_right = Inches(0.06)
        tf.margin_top = Inches(0.06)
        tf.margin_bottom = Inches(0.02)

        # Label (uppercase, 9pt, cinza)
        p1 = tf.paragraphs[0]
        r1 = p1.add_run()
        r1.text = label.upper()
        r1.font.name = "Calibri"
        r1.font.size = Pt(11 if portfolio_mode else 9)
        r1.font.bold = False
        r1.font.color.rgb = _rgb(_GRAY, RGBColor)

        # Valor (18pt, bold, preto)
        p2 = tf.add_paragraph()
        r2 = p2.add_run()
        r2.text = value
        r2.font.name = "Calibri"
        r2.font.size = Pt(18)
        r2.font.bold = True
        r2.font.color.rgb = _rgb(_BLACK, RGBColor)

    if remaining:
        from pptx.enum.text import PP_ALIGN

        native = slide.shapes.add_table(1, len(remaining), Inches(_MX), Inches(1.30), Inches(total_w), Inches(0.30)).table
        for index, (label, value) in enumerate(remaining):
            cell = native.cell(0, index)
            cell.text = f"{label}: {value}"
            cell.fill.solid()
            cell.fill.fore_color.rgb = _rgb(_WHITE, RGBColor)
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            cell.margin_left = cell.margin_right = Inches(0.06)
            for paragraph in cell.text_frame.paragraphs:
                paragraph.alignment = PP_ALIGN.LEFT
                for run in paragraph.runs:
                    run.font.name = "Calibri"
                    run.font.size = Pt(11)
                    run.font.color.rgb = _rgb(_GRAY, RGBColor)


# ===========================================================================
# CHART BUILDERS
# ===========================================================================

def _chart_pl_stacked(
    slide, slot, df: pd.DataFrame, cats: list[str],
    *, CategoryChartData, RGBColor, XL_CHART_TYPE,
    XL_LEGEND_POSITION, XL_DATA_LABEL_POSITION, Inches, Pt,
) -> None:
    if df.empty or not cats:
        _empty_placeholder(slide, slot, "PL por classe", "Sem dados.", Inches=Inches, Pt=Pt, RGBColor=RGBColor)
        return

    scale_div, scale_lbl = _money_scale(
        pd.concat([
            pd.to_numeric(df.get("pl_senior"), errors="coerce"),
            pd.to_numeric(df.get("pl_subordinada_mezz_ex360"), errors="coerce"),
        ], ignore_index=True)
    )
    senior_vals = [_scaled(v, scale_div) for v in df.get("pl_senior", pd.Series(dtype="float"))]
    subord_vals = [_scaled(v, scale_div) for v in df.get("pl_subordinada_mezz_ex360", pd.Series(dtype="float"))]

    cdata = CategoryChartData()
    cdata.categories = cats
    cdata.add_series("Sênior", senior_vals)
    cdata.add_series("Subordinada + Mezanino ex-360", subord_vals)

    chart = _place_chart(slide, slot, XL_CHART_TYPE.COLUMN_STACKED, cdata, Inches)
    _style_chart(chart, "PL por classe", "Competência", scale_lbl, "#,##0.0", RGBColor, Pt)
    observed = [value for values in (senior_vals, subord_vals) for value in values if value is not None]
    if observed and min(observed) >= 0:
        chart.value_axis.minimum_scale = 0
    chart.has_legend = True
    _style_legend(chart, XL_LEGEND_POSITION.BOTTOM, RGBColor, Pt)
    if chart.series:
        _series_fill(chart.series[0], _rgb(_BLACK, RGBColor))
    if len(chart.series) > 1:
        _series_fill(chart.series[1], _rgb(_ORANGE, RGBColor))
    _apply_export_labels(
        chart,
        [senior_vals, subord_vals],
        [_WHITE, _BLACK],
        chart_kind="stacked_bar",
        metric_kind="money",
        percent=False,
        decimals=0,
        RGBColor=RGBColor,
        Pt=Pt,
        positions=[
            XL_DATA_LABEL_POSITION.INSIDE_END,
            XL_DATA_LABEL_POSITION.INSIDE_END,
        ],
    )

    # Badge "PL total: R$ x mm"
    if not df.empty:
        latest = df.iloc[-1]
        total = (_num(latest.get("pl_senior")) or 0) + (_num(latest.get("pl_subordinada_mezz_ex360")) or 0)
        if total > 0:
            lft, top, wid, _ = slot
            badge = f"PL total: {_fmt_money_scaled(total, scale_div, scale_lbl)}"
            _textbox(slide, badge,
                     left=lft + wid - 2.40, top=top + 0.28, width=2.30, height=0.22,
                     size=10, bold=True, color=_BLACK,
                     Inches=Inches, Pt=Pt, RGBColor=RGBColor)


def _chart_percent_line(
    slide, slot, title: str, column: str,
    df: pd.DataFrame, cats: list[str], color: str,
    *, CategoryChartData, RGBColor, XL_CHART_TYPE, Inches, Pt,
    clip_outlier: bool = False, metric_kind: str = "general_pct", portfolio_mode: bool = False,
) -> None:
    if df.empty or not cats or column not in df.columns:
        _empty_placeholder(slide, slot, title, "Sem dados.", Inches=Inches, Pt=Pt, RGBColor=RGBColor)
        return

    raw = pd.to_numeric(df[column], errors="coerce")
    if portfolio_mode and raw.notna().sum() == 0:
        denominator = pd.to_numeric(df.get("npl_over90_ex360", pd.Series(dtype=float)), errors="coerce")
        reason = (
            "Não aplicável: NPL > 90d ex-360 é zero na janela."
            if metric_kind == "coverage_pct" and not denominator.empty and denominator.notna().all() and denominator.eq(0).all()
            else "N/D: série sem valor informado na janela."
        )
        _empty_placeholder(slide, slot, title, reason, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
        _append_portfolio_notes(slide, f"{title}: {reason}")
        return
    values = [_pct_val(v) for v in raw]

    cdata = CategoryChartData()
    cdata.categories = cats
    cdata.add_series(title, values)

    chart = _place_chart(slide, slot, XL_CHART_TYPE.LINE_MARKERS, cdata, Inches)
    _style_chart(chart, title, "Competência", "%", "0.0%", RGBColor, Pt)
    chart.has_legend = False

    if chart.series:
        _series_line(chart.series[0], _rgb(color, RGBColor))

    # Outlier fix: corta eixo Y em 70% e adiciona anotação
    if clip_outlier and values:
        non_null = [v for v in values if v is not None]
        if non_null and min(non_null) < 0.10:  # outlier detectado
            try:
                chart.value_axis.minimum_scale = 0.70
            except Exception:
                pass
            lft, top, wid, hgt = slot
            _textbox(slide,
                     "Outlier: dado mai/25 inconsistente na CVM",
                     left=lft + wid * 0.55,
                     top=top + hgt * 0.70,
                     width=wid * 0.42, height=0.30,
                     size=9, bold=False, color=_GRAY, italic=True,
                     Inches=Inches, Pt=Pt, RGBColor=RGBColor)

    _apply_export_labels(
        chart,
        [values],
        [color],
        chart_kind="line",
        metric_kind=metric_kind,
        percent=True,
        RGBColor=RGBColor,
        Pt=Pt,
    )


def _chart_bar_money(
    slide, slot, title: str, column: str, series_name: str,
    df: pd.DataFrame, cats: list[str],
    *, CategoryChartData, RGBColor, XL_CHART_TYPE,
    XL_LABEL_POSITION, Inches, Pt,
) -> None:
    if df.empty or not cats or column not in df.columns:
        _empty_placeholder(slide, slot, title, "Sem dados.", Inches=Inches, Pt=Pt, RGBColor=RGBColor)
        return

    scale_div, scale_lbl = _money_scale(pd.to_numeric(df[column], errors="coerce"))
    values = [_scaled(v, scale_div) for v in df[column]]

    cdata = CategoryChartData()
    cdata.categories = cats
    cdata.add_series(series_name, values)

    chart = _place_chart(slide, slot, XL_CHART_TYPE.COLUMN_CLUSTERED, cdata, Inches)
    _style_chart(chart, title, "Competência", scale_lbl, "#,##0.0", RGBColor, Pt)
    chart.has_legend = False
    if chart.series:
        _series_fill(chart.series[0], _rgb(_BLACK, RGBColor))
    _apply_export_labels(
        chart,
        [values],
        [_BLACK],
        chart_kind="bar",
        metric_kind="money",
        percent=False,
        decimals=0,
        RGBColor=RGBColor,
        Pt=Pt,
        positions=[XL_LABEL_POSITION.OUTSIDE_END],
    )


def _chart_multi_line(
    slide, slot, title: str,
    df: pd.DataFrame, cats: list[str],
    series_specs: list[tuple[str, str, str]],
    y_title: str,
    *,
    CategoryChartData, RGBColor, XL_CHART_TYPE,
    XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE, Inches, Pt,
    value_is_percent: bool = True,
    metric_kind: str = "general_pct",
    legend_below: bool = False,
) -> None:
    valid = [(nm, col, clr) for nm, col, clr in series_specs
             if col in df.columns or not df.empty]
    if df.empty or not cats or not valid:
        _empty_placeholder(slide, slot, title, "Sem dados.", Inches=Inches, Pt=Pt, RGBColor=RGBColor)
        return

    cdata = CategoryChartData()
    cdata.categories = cats
    all_vals: list[list] = []
    for name, col, _ in valid:
        if col in df.columns:
            vals = [_pct_val(v) if value_is_percent else _num(v) for v in df[col]]
        else:
            vals = [None] * len(cats)
        cdata.add_series(name, vals)
        all_vals.append(vals)

    chart = _place_chart(slide, slot, XL_CHART_TYPE.LINE_MARKERS, cdata, Inches)
    fmt = "0.0%" if value_is_percent else "#,##0.0"
    _style_chart(chart, title, "Competência", y_title, fmt, RGBColor, Pt)
    chart.has_legend = len(valid) > 1
    if chart.has_legend:
        pos = XL_LEGEND_POSITION.BOTTOM
        _style_legend(chart, pos, RGBColor, Pt)

    for series, (_, _, clr) in zip(chart.series, valid):
        _series_line(series, _rgb(clr, RGBColor))

    _apply_export_labels(
        chart,
        all_vals,
        [clr for _, _, clr in valid],
        chart_kind="multi_line" if len(valid) > 1 else "line",
        metric_kind=metric_kind,
        percent=value_is_percent,
        RGBColor=RGBColor,
        Pt=Pt,
        positions=_ranked_line_label_positions(all_vals, XL_LABEL_POSITION),
    )


def _chart_stacked_npl(
    slide, slot, df: pd.DataFrame, cats: list[str],
    *, CategoryChartData, RGBColor, XL_CHART_TYPE,
    XL_LABEL_POSITION, XL_LEGEND_POSITION, Inches, Pt,
) -> None:
    if df.empty or not cats:
        _empty_placeholder(slide, slot, "NPL ex-360 por severidade", "Sem dados.", Inches=Inches, Pt=Pt, RGBColor=RGBColor)
        return

    v1 = [_pct_val(v) for v in df.get("npl_1_90_pct", pd.Series(dtype="float"))]
    v2 = [_pct_val(v) for v in df.get("npl_91_360_pct", pd.Series(dtype="float"))]

    cdata = CategoryChartData()
    cdata.categories = cats
    cdata.add_series("NPL 1-90d", v1)
    cdata.add_series("NPL 91-360d", v2)

    chart = _place_chart(slide, slot, XL_CHART_TYPE.COLUMN_STACKED, cdata, Inches)
    _style_chart(chart, "NPL ex-360 por severidade", "Competência",
                 "% carteira bruta ex-360", "0.0%", RGBColor, Pt)
    chart.has_legend = True
    _style_legend(chart, XL_LEGEND_POSITION.BOTTOM, RGBColor, Pt)
    if chart.series:
        _series_fill(chart.series[0], _rgb(_BLACK, RGBColor))
    if len(chart.series) > 1:
        _series_fill(chart.series[1], _rgb(_ORANGE, RGBColor))
    _apply_export_labels(
        chart,
        [v1, v2],
        [_WHITE, _BLACK],
        chart_kind="stacked_bar",
        metric_kind="npl_pct",
        percent=True,
        RGBColor=RGBColor,
        Pt=Pt,
        positions=[XL_LABEL_POSITION.CENTER, XL_LABEL_POSITION.CENTER],
    )


def _chart_cohorts(
    slide, slot, cohort_df: pd.DataFrame,
    *, CategoryChartData, RGBColor, XL_CHART_TYPE,
    XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE, Inches, Pt,
) -> None:
    if cohort_df is None or cohort_df.empty:
        _empty_placeholder(slide, slot, "Cohorts recentes", "Sem dados.", Inches=Inches, Pt=Pt, RGBColor=RGBColor)
        return

    df = cohort_df.copy()
    recent = (df[["cohort", "cohort_dt"]].drop_duplicates()
              .sort_values("cohort_dt").tail(6)["cohort"].tolist())
    df = df[df["cohort"].isin(recent)]
    months = ["M1", "M2", "M3", "M4", "M5", "M6"]
    gray_series = [_BLACK, _GRAY, _GRAY_MID, _GRAY_PALE, "383838", "585858"]

    cdata = CategoryChartData()
    cdata.categories = months
    all_vals: list[list] = []
    for coh in recent:
        g = df[df["cohort"].eq(coh)].set_index("mes_ciclo")
        vals = [_pct_val(g.loc[m, "valor_pct"]) if m in g.index else None for m in months]
        cdata.add_series(coh, vals)
        all_vals.append(vals)

    chart = _place_chart(slide, slot, XL_CHART_TYPE.LINE_MARKERS, cdata, Inches)
    _style_chart(chart, "Cohorts recentes", "Mês de maturação",
                 "% saldo a vencer 30d", "0.0%", RGBColor, Pt)
    chart.has_legend = True
    _style_legend(chart, XL_LEGEND_POSITION.BOTTOM, RGBColor, Pt)
    for series, clr in zip(chart.series, gray_series):
        _series_line(series, _rgb(clr, RGBColor))
    _apply_export_labels(
        chart,
        all_vals,
        gray_series,
        chart_kind="cohort",
        metric_kind="cohort_pct",
        percent=True,
        RGBColor=RGBColor,
        Pt=Pt,
        positions=_ranked_line_label_positions(all_vals, XL_LABEL_POSITION),
    )


# ===========================================================================
# GRID LAYOUTS
# ===========================================================================

def _grid_2x2(*, portfolio_mode: bool = False) -> list[tuple[float, float, float, float]]:
    w = (_SW - _MX * 2 - _GAP_X) / 2
    top = 1.70 if portfolio_mode else _CTX_TOP
    h = (_FTR_TOP - top - _GAP_Y) / 2
    return [
        (_MX, top, w, h),
        (_MX + w + _GAP_X, top, w, h),
        (_MX, top + h + _GAP_Y, w, h),
        (_MX + w + _GAP_X, top + h + _GAP_Y, w, h),
    ]


def _grid_1x2(*, portfolio_mode: bool = False) -> list[tuple[float, float, float, float]]:
    w = (_SW - _MX * 2 - _GAP_X) / 2
    top = 1.70 if portfolio_mode else _CTX_TOP
    return [
        (_MX, top, w, _FTR_TOP - top),
        (_MX + w + _GAP_X, top, w, _FTR_TOP - top),
    ]


# ===========================================================================
# CHART STYLING HELPERS
# ===========================================================================

def _place_chart(slide, slot, chart_type, chart_data, Inches):
    l, t, w, h = slot
    return slide.shapes.add_chart(
        chart_type, Inches(l), Inches(t), Inches(w), Inches(h), chart_data
    ).chart


def _style_chart(chart, title, x_title, y_title, num_fmt, RGBColor, Pt) -> None:
    chart.has_title = True
    _set_text(chart.chart_title.text_frame, title, Pt(11), True, _BLACK, RGBColor)

    chart.category_axis.has_title = True
    _set_text(chart.category_axis.axis_title.text_frame, x_title, Pt(9), False, _GRAY, RGBColor)
    chart.value_axis.has_title = True
    _set_text(chart.value_axis.axis_title.text_frame, y_title, Pt(9), False, _GRAY, RGBColor)

    for axis in (chart.category_axis, chart.value_axis):
        axis.tick_labels.font.name = "Calibri"
        axis.tick_labels.font.size = Pt(9.5)
        axis.tick_labels.font.color.rgb = _rgb(_GRAY, RGBColor)

    chart.value_axis.tick_labels.number_format = num_fmt
    try:
        chart.value_axis.tick_labels.number_format_is_linked = False
    except Exception:
        pass
    chart.value_axis.has_major_gridlines = True
    try:
        chart.value_axis.major_gridlines.format.line.color.rgb = _rgb(_GRAY_LIGHT, RGBColor)
        chart.value_axis.major_gridlines.format.line.width = 6350  # 0.5pt
    except Exception:
        pass

    # Remove plot area border
    try:
        chart.plot_area.format.line.fill.background()
    except Exception:
        pass

    # Remove vertical gridlines
    try:
        chart.category_axis.has_major_gridlines = False
    except Exception:
        pass


def _style_legend(chart, position, RGBColor, Pt) -> None:
    if chart.legend is None:
        return
    chart.legend.position = position
    chart.legend.include_in_layout = True
    chart.legend.font.name = "Calibri"
    chart.legend.font.size = Pt(9)
    chart.legend.font.color.rgb = _rgb(_GRAY, RGBColor)


def _series_fill(series, color) -> None:
    series.format.fill.solid()
    series.format.fill.fore_color.rgb = color
    series.format.line.color.rgb = color


def _series_line(series, color) -> None:
    series.format.line.color.rgb = color
    series.format.line.width = 15875  # ~1.25pt
    try:
        from pptx.enum.chart import XL_MARKER_STYLE
        series.marker.style = XL_MARKER_STYLE.CIRCLE
        series.marker.size = 4
        series.marker.format.fill.solid()
        series.marker.format.fill.fore_color.rgb = color
        series.marker.format.line.color.rgb = color
    except Exception:
        pass


def _ranked_line_label_positions(series_values: list[list], XL_LABEL_POSITION) -> list:
    """Spread final-point labels using the latest y-value ranking."""
    positions = [XL_LABEL_POSITION.RIGHT for _ in series_values]
    latest: list[tuple[int, float]] = []
    for idx, values in enumerate(series_values):
        last_idx = _last_non_null(values)
        if last_idx is None:
            continue
        value = _num(values[last_idx])
        if value is not None:
            latest.append((idx, value))
    if len(latest) <= 1:
        return positions

    ranked = sorted(latest, key=lambda item: item[1])
    positions[ranked[0][0]] = XL_LABEL_POSITION.BELOW
    positions[ranked[-1][0]] = XL_LABEL_POSITION.ABOVE
    middle_positions = [XL_LABEL_POSITION.RIGHT, XL_LABEL_POSITION.LEFT]
    for offset, (idx, _value) in enumerate(ranked[1:-1]):
        positions[idx] = middle_positions[offset % len(middle_positions)]
    return positions


def _apply_export_labels(
    chart,
    series_values: list[list],
    colors: list[str],
    *,
    chart_kind: str,
    metric_kind: str,
    percent: bool,
    RGBColor,
    Pt,
    decimals: int | None = None,
    positions: list | None = None,
) -> None:
    """Apply shared label policy to a python-pptx chart."""

    policy = choose_export_label_policy(
        series_values,
        chart_kind=chart_kind,
        metric_kind=metric_kind,
    )
    if policy.mode == "none":
        return
    native_num_fmt = _native_label_number_format(
        metric_kind=metric_kind,
        percent=percent,
        decimals=decimals,
    )

    for series_idx, point_indices in enumerate(policy.indices_by_series):
        if series_idx >= len(chart.series):
            continue
        series = chart.series[series_idx]
        try:
            series.data_labels.number_format = native_num_fmt
            series.data_labels.number_format_is_linked = False
        except Exception:
            pass
        values = series_values[series_idx]
        for point_idx in point_indices:
            if point_idx >= len(values):
                continue
            try:
                point = series.points[point_idx]
                label = point.data_label
                if positions:
                    label.position = positions[series_idx % len(positions)]
                label.has_text_frame = True
                text_frame = label.text_frame
                text_frame.clear()
                run = text_frame.paragraphs[0].add_run()
                run.text = format_export_label(
                    values[point_idx],
                    metric_kind=metric_kind,
                    percent_value=percent,
                    decimals=decimals,
                )
                run.font.name = "Calibri"
                run.font.size = Pt(policy.font_size_pt)
                run.font.bold = True
                run.font.color.rgb = _rgb(colors[series_idx % len(colors)], RGBColor)
            except Exception:
                continue


def _empty_placeholder(slide, slot, title, msg, *, Inches, Pt, RGBColor) -> None:
    l, t, w, h = slot
    _textbox(slide, title, left=l, top=t + 0.04, width=w, height=0.24,
             size=11, bold=True, color=_BLACK, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    _textbox(slide, msg, left=l, top=t + h / 2 - 0.1, width=w, height=0.28,
             size=10, bold=False, color=_GRAY, Inches=Inches, Pt=Pt, RGBColor=RGBColor)


# ===========================================================================
# TEXT HELPERS
# ===========================================================================

def _textbox(
    slide, text: str, *, left, top, width, height, size, bold, color,
    italic: bool = False, align_right: bool = False, word_wrap: bool = False,
    margin_vertical: float | None = None,
    Inches, Pt, RGBColor,
) -> None:
    from pptx.enum.text import PP_ALIGN
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = word_wrap
    tf.clear()
    if margin_vertical is not None:
        tf.margin_top = Inches(margin_vertical)
        tf.margin_bottom = Inches(margin_vertical)
    p = tf.paragraphs[0]
    if align_right:
        p.alignment = PP_ALIGN.RIGHT
    run = p.add_run()
    run.text = text
    run.font.name = "Calibri"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = _rgb(color, RGBColor)


def _shape_text(shape, text: str, *, size, bold, color, Pt, RGBColor,
                align_center: bool = False) -> None:
    from pptx.enum.text import PP_ALIGN
    tf = shape.text_frame
    tf.word_wrap = False
    tf.clear()
    p = tf.paragraphs[0]
    if align_center:
        p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = text
    run.font.name = "Calibri"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = _rgb(color, RGBColor)


def _set_text(text_frame, text, size, bold, color, RGBColor) -> None:
    text_frame.clear()
    p = text_frame.paragraphs[0]
    run = p.add_run()
    run.text = text
    run.font.name = "Calibri"
    run.font.size = size
    run.font.bold = bold
    run.font.color.rgb = _rgb(color, RGBColor)


# ===========================================================================
# DATA HELPERS
# ===========================================================================

def _chart_dependencies(deps, *names):
    return {name: deps[name] for name in ("Inches", "Pt", "RGBColor", "CategoryChartData", "XL_CHART_TYPE", *names) if name in deps}


def _component(name, frame, columns, render, *, reason=None):
    from services.portfolio_presentation_state import classify_component

    frame = frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    return dict(name=name, frame=frame, columns=tuple(columns), render=render,
                state=classify_component(frame, columns), reason=reason)


def _component_labels(frame):
    if "competencia_dt" in frame:
        return _category_labels(frame)
    if "competencia" in frame:
        return frame["competencia"].astype(str).tolist()
    if "cohort" in frame and "mes_ciclo" in frame:
        return (frame["cohort"].astype(str) + " · " + frame["mes_ciclo"].astype(str)).tolist()
    return [str(index + 1) for index in range(len(frame))]


def _component_note(component):
    import json
    import math

    frame = component["frame"]
    state = component["state"]
    identities = [column for column in ("competencia", "competencia_dt", "cohort", "cohort_dt", "mes_ciclo") if column in frame]
    columns = list(dict.fromkeys([*identities, *component["columns"]]))
    records = []
    for _, row in frame.iterrows():
        record = {}
        for column in columns:
            value = row.get(column)
            value = None if pd.isna(value) else value.item() if hasattr(value, "item") else value
            record[column] = str(value) + " (não finito)" if isinstance(value, float) and not math.isfinite(value) else value
        records.append(record)
    reason = component.get("reason") or ("nenhum valor finito informado" if state.status == "absent" else "todos os valores finitos são exatamente zero")
    return (f"Compactação: {component['name']} | {state.status} | {reason}. "
            f"{state.finite_count} valores finitos; {state.missing_count} lacunas. "
            "Gráfico substituído por registro explícito; dados originais completos:\n"
            + json.dumps(records, ensure_ascii=False, default=str, allow_nan=False))


def _component_grid(count, *, top, bottom):
    width = _SW - 2 * _MX
    height = bottom - top
    if count <= 1:
        return [(_MX, top, width, height)]
    half_width = (width - _GAP_X) / 2
    if count == 2:
        return [(_MX, top, half_width, height), (_MX + half_width + _GAP_X, top, half_width, height)]
    half_height = (height - _GAP_Y) / 2
    slots = [(_MX, top, half_width, half_height), (_MX + half_width + _GAP_X, top, half_width, half_height)]
    if count == 3:
        return [*slots, (_MX, top + half_height + _GAP_Y, width, half_height)]
    return [*slots, (_MX, top + half_height + _GAP_Y, half_width, half_height),
            (_MX + half_width + _GAP_X, top + half_height + _GAP_Y, half_width, half_height)]


def _zero_gap_rows(components):
    labels = []
    rows = []
    for component in components:
        state = component["state"]
        if state.status != "zero" or not state.has_gaps:
            continue
        frame = component["frame"]
        own_labels = _component_labels(frame)
        for label in own_labels:
            if label not in labels:
                labels.append(label)
        for column in component["columns"]:
            values = frame[column].tolist() if column in frame else [None] * len(frame)
            mapped = dict(zip(own_labels, values))
            rows.append((f"{component['name']} · {column}", mapped))
    return labels, rows


def _add_zero_gap_table(slide, labels, rows, *, top, Inches, Pt, RGBColor):
    from pptx.enum.text import MSO_VERTICAL_ANCHOR, PP_ALIGN

    shape = slide.shapes.add_table(len(rows) + 1, len(labels) + 1,
                                  Inches(_MX), Inches(top), Inches(_SW - 2 * _MX), Inches(0.38 + len(rows) * 0.30))
    table = shape.table
    table.columns[0].width = Inches(3.3)
    for column in list(table.columns)[1:]:
        column.width = Inches((_SW - 2 * _MX - 3.3) / len(labels))
    table.rows[0].height = Inches(0.38)
    for row in list(table.rows)[1:]:
        row.height = Inches(0.30)
    aliases = {"roll_61_90_m3_pct": "61–90d", "roll_91_120_m4_pct": "91–120d",
               "roll_121_150_m5_pct": "121–150d", "roll_151_180_m6_pct": "151–180d",
               "npl_1_90_pct": "1–90d", "npl_91_360_pct": "91–360d",
               "pl_subordinada_mezz_ex360": "Sub. + mezanino", "pl_senior": "Sênior",
               "subordinacao_total_ex360_pct": "Subordinação (%)",
               "pdd_npl_over90_ex360_pct": "Cobertura (%)", "npl_over90_ex360_pct": "90d (%)",
               "duration_months": "Meses", "valor_pct": "Valor (%)"}
    contents = [["0 / N/D na base", *labels]]
    for name, values in rows:
        for raw, label in aliases.items():
            name = name.replace(raw, label)
        contents.append([name, *["0" if _num(values.get(label)) == 0 else "N/D" for label in labels]])
    for row_index, row in enumerate(contents):
        for column_index, text in enumerate(row):
            _style_return_table_cell(table.cell(row_index, column_index), text,
                                     fill_color=_CARD_BG if row_index == 0 else _WHITE,
                                     text_color=_BLACK, font_size=11, bold=row_index == 0,
                                     alignment=PP_ALIGN.LEFT if column_index == 0 else PP_ALIGN.RIGHT,
                                     vertical_anchor=MSO_VERTICAL_ANCHOR.MIDDLE, word_wrap=column_index == 0,
                                     Inches=Inches, Pt=Pt, RGBColor=RGBColor)


def _add_component_slide(prs, layout, title, page_num, total, data_base, components, *, monitor=None, monthly=None, **deps):
    active = [component for component in components if component["state"].status == "observed"]
    if len(active) > 4:
        raise ValueError("Mais de quatro componentes observados exigem paginação explícita; nenhum gráfico pode ser descartado.")
    Inches, Pt, RGBColor = (deps[key] for key in ("Inches", "Pt", "RGBColor"))
    slide = prs.slides.add_slide(layout)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(_WHITE, RGBColor)
    _slide_header(slide, title, data_base, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    _slide_footer(slide, page_num, total, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    show_kpis = monthly is not None
    if show_kpis:
        _kpi_strip(slide, monitor, monthly, portfolio_mode=True, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    else:
        _textbox(slide, "KPIs da mesma posição no quadro de estrutura.", left=_MX, top=0.58,
                 width=_SW - 2 * _MX, height=0.24, size=11, bold=False, color=_GRAY,
                 Inches=Inches, Pt=Pt, RGBColor=RGBColor)
        _append_portfolio_notes(slide, "Compactação: KPIs repetidos permanecem no quadro de estrutura da mesma posição.")
    inactive = [component for component in components if component["state"].status != "observed"]
    gap_labels, gap_rows = _zero_gap_rows(inactive)
    inline_gap = bool(gap_rows) and len(gap_labels) <= 13 and len(gap_rows) <= 7
    caption_height = 0.58 if inactive else 0
    gap_height = 0.38 + len(gap_rows) * 0.30 if inline_gap else 0
    bottom = _FTR_TOP - 0.08 - caption_height - gap_height
    top = 1.70 if show_kpis else 0.95
    for component, slot in zip(active, _component_grid(len(active), top=top, bottom=bottom)):
        component["render"](slide, slot)
    if inactive:
        parts = []
        for component in inactive:
            state = component["state"]
            status = component.get("reason") or ("N/D" if state.status == "absent" else f"0 em {state.row_count} observações" if not state.has_gaps else f"0 e N/D em {state.row_count} observações")
            parts.append(f"{component['name']}: {status}")
            _append_portfolio_notes(slide, _component_note(component))
        caption = "Compactação: " + "; ".join(parts) + ". Dados completos nas notas."
        if deps.get("empty_monthly"):
            caption += " Crédito e duration sem informe mensal foram reunidos aqui; as tabelas de retorno permanecem próprias."
        _textbox(slide, caption, left=_MX, top=_FTR_TOP - caption_height - 0.03,
                 width=_SW - 2 * _MX, height=caption_height, size=11, bold=False, color=_GRAY,
                 word_wrap=True, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    if inline_gap:
        _add_zero_gap_table(slide, gap_labels, gap_rows, top=bottom + 0.04, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    elif gap_rows:
        for start in range(0, len(gap_labels), 13):
            for row_start in range(0, len(gap_rows), 18):
                extra = prs.slides.add_slide(layout)
                _slide_header(extra, title + " — Zeros e lacunas", data_base, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
                _slide_footer(extra, page_num, total, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
                _add_zero_gap_table(extra, gap_labels[start:start + 13], gap_rows[row_start:row_start + 18], top=0.80, Inches=Inches, Pt=Pt, RGBColor=RGBColor)
                _append_portfolio_notes(extra, "Compactação: registro nativo completo de zeros e lacunas; 0 e N/D permanecem distintos.")
    if not active:
        _textbox(slide, "Sem componente gráfico com valor não zero nesta janela.", left=_MX, top=top + 0.15,
                 width=_SW - 2 * _MX, height=0.35, size=14, bold=True, color=_BLACK,
                 Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    return slide


def _add_compact_base_slide(prs, layout, monthly, monitor, title, page_num, total, data_base, *, is_subordination_fund=False, **deps):
    cats = _category_labels(monthly)
    common = _chart_dependencies(deps)
    stacked = _chart_dependencies(deps, "XL_LEGEND_POSITION", "XL_DATA_LABEL_POSITION")
    components = [
        _component("PL por classe", monthly, ("pl_senior", "pl_subordinada_mezz_ex360"),
                   lambda slide, slot: _chart_pl_stacked(slide, slot, monthly, cats, **stacked)),
        _component("Subordinação ex-360", monthly, ("subordinacao_total_ex360_pct",),
                   lambda slide, slot: _chart_percent_line(slide, slot, "% Subordinação Total ex-360", "subordinacao_total_ex360_pct", monthly, cats, _GRAY,
                                                         clip_outlier=is_subordination_fund, portfolio_mode=True, **common)),
        _component("NPL > 90d ex-360", monthly, ("npl_over90_ex360_pct",),
                   lambda slide, slot: _chart_percent_line(slide, slot, "NPL Over 90d ex-360 / Carteira", "npl_over90_ex360_pct", monthly, cats, _BLACK,
                                                         metric_kind="npl_pct", portfolio_mode=True, **common)),
        _component("Cobertura PDD / NPL", monthly, ("pdd_npl_over90_ex360_pct",),
                   lambda slide, slot: _chart_percent_line(slide, slot, "Cobertura PDD / NPL Over 90d ex-360", "pdd_npl_over90_ex360_pct", monthly, cats, _ORANGE,
                                                         metric_kind="coverage_pct", portfolio_mode=True, **common)),
    ]
    denominator = pd.to_numeric(monthly.get("npl_over90_ex360", pd.Series(dtype=float)), errors="coerce")
    if components[-1]["state"].status == "absent" and not denominator.empty and denominator.notna().all() and denominator.eq(0).all():
        components[-1]["reason"] = "não aplicável (NPL zero)"
    # A positive or negative PDD stays visible even when coverage has a zero denominator.
    pdd = _component("PDD total (R$)", monthly, ("pdd_total",),
                     lambda slide, slot: _chart_bar_money(slide, slot, "PDD total", "pdd_total", "PDD total", monthly, cats,
                                                         **_chart_dependencies(deps, "XL_LABEL_POSITION")))
    if components[-1]["state"].status != "observed" and pdd["state"].status == "observed":
        components.append(pdd)
    return _add_component_slide(prs, layout, title + " — Estrutura", page_num, total, data_base, components, monitor=monitor, monthly=monthly, **deps)


def _add_compact_credit_slide(prs, layout, frame, title, page_num, total, data_base, **deps):
    cats = _category_labels(frame)
    line = _chart_dependencies(deps, "XL_LABEL_POSITION", "XL_LEGEND_POSITION", "XL_MARKER_STYLE")
    components = [
        _component("Carteira ex-360", frame, ("carteira_ex360",),
                   lambda slide, slot: _chart_bar_money(slide, slot, "Carteira Bruta ex-360", "carteira_ex360", "Carteira Bruta ex-360", frame, cats,
                                                       **_chart_dependencies(deps, "XL_LABEL_POSITION"))),
        _component("YoY da carteira", frame, ("carteira_ex360_yoy_pct",),
                   lambda slide, slot: _chart_multi_line(slide, slot, "Crescimento YoY carteira bruta ex-360", frame, cats,
                                                        [("Crescimento YoY", "carteira_ex360_yoy_pct", _ORANGE)], "%", **line)),
        _component("NPL por severidade", frame, ("npl_1_90_pct", "npl_91_360_pct"),
                   lambda slide, slot: _chart_stacked_npl(slide, slot, frame, cats,
                                                         **_chart_dependencies(deps, "XL_LABEL_POSITION", "XL_LEGEND_POSITION"))),
        _component("Roll rates", frame, ("roll_61_90_m3_pct", "roll_91_120_m4_pct", "roll_121_150_m5_pct", "roll_151_180_m6_pct"),
                   lambda slide, slot: _chart_multi_line(slide, slot, "Roll rates", frame, cats,
                                                        [("Roll 61–90 M-3", "roll_61_90_m3_pct", _BLACK), ("Roll 91–120 M-4", "roll_91_120_m4_pct", _GRAY),
                                                         ("Roll 121–150 M-5", "roll_121_150_m5_pct", _GRAY_MID), ("Roll 151–180 M-6", "roll_151_180_m6_pct", _ORANGE)],
                                                        "%", metric_kind="roll_pct", **line)),
    ]
    return _add_component_slide(prs, layout, title + " — Crédito", page_num, total, data_base, components, **deps)


def _add_compact_detail_slide(prs, layout, monitor, fund_map, cohorts, title, page_num, total, data_base, **deps):
    duration = _build_duration_frame(monitor, fund_map)
    columns = [column for column in duration if column not in ("competencia", "competencia_dt")]
    colors = [_BLACK, _ORANGE, _GRAY, _GRAY_MID, _GRAY_PALE, "383838", "585858"]
    line = _chart_dependencies(deps, "XL_LABEL_POSITION", "XL_LEGEND_POSITION", "XL_MARKER_STYLE")
    components = [
        _component("Duration", duration, columns,
                   lambda slide, slot: _chart_multi_line(slide, slot, "Duration por FIDC", duration, _category_labels(duration),
                                                        [(short_fund_name(column), column, colors[index % len(colors)]) for index, column in enumerate(columns)],
                                                        "meses", value_is_percent=False, metric_kind="duration", **line)),
        _component("Cohorts recentes", cohorts, ("valor_pct",),
                   lambda slide, slot: _chart_cohorts(slide, slot, cohorts, **line)),
    ]
    slide = _add_component_slide(prs, layout, title + " — Duration e cohorts", page_num, total, data_base, components, **deps)
    missing = [short_fund_name(_raw_fund_name(frame, fallback=cnpj))
               for cnpj, frame in fund_map.items()
               if frame.empty or "duration_months" not in frame
               or pd.to_numeric(frame["duration_months"], errors="coerce").notna().sum() == 0]
    if missing:
        caption = next(shape for shape in slide.shapes if shape.has_text_frame and shape.text.startswith("KPIs da mesma posição"))
        caption.text_frame.paragraphs[0].runs[0].text = f"Duration: {len(fund_map) - len(missing)}/{len(fund_map)} fundos com série; ausências nas notas."
        _append_portfolio_notes(slide, "Duration sem série informada na janela: " + ", ".join(missing))
    return slide


def _add_compact_roll_slide(prs, layout, frame, title, page_num, total, data_base, **deps):
    line = _chart_dependencies(deps, "XL_LABEL_POSITION", "XL_LEGEND_POSITION", "XL_MARKER_STYLE")
    components = []
    for label, metric in (("Roll 61–90", "roll_61_90_m3"), ("Roll 91–120", "roll_91_120_m4"),
                          ("Roll 121–150", "roll_121_150_m5"), ("Roll 151–180", "roll_151_180_m6")):
        wide = _research_roll_wide(frame, metric_id=metric)
        columns = [column for column in wide if column not in ("competencia", "competencia_dt", "month", "ordem")]
        colors = [_BLACK, _GRAY, _GRAY_MID, _GRAY_PALE]
        render = lambda slide, slot, wide=wide, columns=columns, label=label: _chart_multi_line(
            slide, slot, label.replace("–", "-") + " por mês do ano", wide, wide.get("competencia", pd.Series(dtype=str)).astype(str).tolist(),
            [(column, column, colors[index % len(colors)]) for index, column in enumerate(columns)], "%", metric_kind="roll_pct", **line)
        components.append(_component(label, wide, columns, render))
    if all(component["state"].status == "absent" for component in components) and len(prs.slides):
        previous = prs.slides[-1]
        for component in components:
            _append_portfolio_notes(previous, _component_note(component))
        visible = next((shape for shape in previous.shapes if shape.has_text_frame and shape.text.startswith("Compactação:")), None)
        if visible is not None:
            visible.text_frame.text += " Sazonalidade: N/D (sem série finita)."
        else:
            _textbox(previous, "Compactação: sazonalidade N/D, sem série finita. Detalhes nas notas.",
                     left=_MX, top=6.86, width=_SW - 2 * _MX, height=0.28, size=11, bold=False, color=_GRAY,
                     **{key: deps[key] for key in ("Inches", "Pt", "RGBColor")})
        return
    return _add_component_slide(prs, layout, title + " — Sazonalidade", page_num, total, data_base, components, **deps)


def _portfolio_return_groups(pages: list[pd.DataFrame]) -> list[tuple[pd.DataFrame, ...]]:
    """Pair complementary views only when every series and readable row fits."""
    monthly = [frame for frame in pages if not any(column in frame for column in _RETURN_COMPARISON_DETAIL_COLUMNS)]
    comparisons = [frame for frame in pages if any(column in frame for column in _RETURN_COMPARISON_DETAIL_COLUMNS)]
    groups = []
    used = set()
    for frame in monthly:
        match = next((index for index, other in enumerate(comparisons)
                      if index not in used and frame[RETURN_SERIES_COLUMN].tolist() == other[RETURN_SERIES_COLUMN].tolist()), None)
        other = comparisons[match] if match is not None else None
        # Existing row heights at 11 pt; two captions and native table headers.
        fits = other is not None and 0.48 + 0.68 + 0.24 * (len(frame) + len(other)) + 0.42 <= 5.96
        if fits:
            groups.append((frame, other))
            used.add(match)
        else:
            groups.append((frame,))
    groups.extend((frame,) for index, frame in enumerate(comparisons) if index not in used)
    return groups


def _append_paired_return_table(prs, layout, frame, title, data_base, *, Inches, Pt, RGBColor, **kwargs) -> None:
    """Copy a second native table into the readable space of the first slide."""
    from copy import deepcopy
    from pptx import Presentation

    target = prs.slides[-1]
    first = next(shape for shape in target.shapes if shape.has_table)
    second_top = first.top / 914400 + first.height / 914400 + 0.42
    temporary = Presentation()
    temporary.slide_width = prs.slide_width
    temporary.slide_height = prs.slide_height
    _add_fund_return_slide(temporary, temporary.slide_layouts[6], frame, title, 1, 1, data_base,
                          page_index=1, page_count=1, Inches=Inches, Pt=Pt, RGBColor=RGBColor, **kwargs)
    original = next(shape for shape in temporary.slides[0].shapes if shape.has_table)
    element = deepcopy(original._element)
    identity = element.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr")
    identity.set("id", str(max(shape.shape_id for shape in target.shapes) + 1))
    identity.set("name", "Comparação de rentabilidade")
    element.xfrm.off.y = Inches(second_top)
    target.shapes._spTree.insert_element_before(element, "p:extLst")
    _textbox(target, "Comparativo reunido neste slide — CDI, spread e referência de emissão", left=_MX, top=second_top - 0.29,
             width=_SW - 2 * _MX, height=0.22, size=11, bold=True, color=_BLACK,
             Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    _append_portfolio_notes(target, temporary.slides[0].notes_slide.notes_text_frame.text)
    _append_portfolio_notes(target, "Compactação: tabelas mensais e comparativas reunidas no mesmo slide; todas as séries e células originais foram preservadas.")


def _append_empty_monthly_record(slide, *, Inches, Pt, RGBColor, **_kwargs):
    """Keep an identified no-monthly-data fund next to its retained return tables."""
    from pptx.enum.text import MSO_VERTICAL_ANCHOR, PP_ALIGN

    tables = [shape for shape in slide.shapes if shape.has_table]
    if not tables:
        return False
    top = max((shape.top + shape.height) / 914400 for shape in tables) + 0.28
    if top + 1.0 > 6.72:
        return False
    _textbox(slide, "Indicadores mensais: N/D, sem informe utilizável na janela selecionada.",
             left=_MX, top=top, width=_SW - 2 * _MX, height=0.22, size=11, bold=False, color=_GRAY,
             Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    table = slide.shapes.add_table(2, 6, Inches(_MX), Inches(top + 0.27),
                                   Inches(_SW - 2 * _MX), Inches(0.58)).table
    for row_index, values in enumerate((("PL", "Carteira", "NPL", "PDD", "Cobertura", "Duration"), ("N/D",) * 6)):
        for column_index, text in enumerate(values):
            _style_return_table_cell(table.cell(row_index, column_index), text,
                                     fill_color=_CARD_BG if row_index == 0 else _WHITE, text_color=_BLACK,
                                     font_size=11, bold=row_index == 0, alignment=PP_ALIGN.LEFT,
                                     vertical_anchor=MSO_VERTICAL_ANCHOR.MIDDLE, word_wrap=False,
                                     Inches=Inches, Pt=Pt, RGBColor=RGBColor)
    _append_portfolio_notes(slide, "Compactação: estrutura, crédito e duration sem observação mensal foram reunidos nesta tabela nativa de N/D. "
                            "O fundo continua identificado; retornos disponíveis foram mantidos integralmente. Ausência não foi tratada como zero.")
    return True


def _portfolio_data_base(frame: pd.DataFrame) -> str:
    """Label a fund with its own observed date; never use the portfolio date."""
    row = _latest_row(frame)
    if row is None:
        return "N/D"
    observed = pd.to_datetime(row.get("competencia_dt"), errors="coerce")
    return _fmt_month(observed) if pd.notna(observed) else "N/D"


def _portfolio_return_header(column: str) -> str:
    return {
        RETURN_TRAILING_12M_COLUMN: "12M (%)",
        RETURN_TRAILING_12M_CDI_COLUMN: "CDI 12M (%)",
        RETURN_TRAILING_12M_IMPLIED_SPREAD_COLUMN: "Spread 12M (% a.a.)",
        RETURN_YTD_COLUMN: "YTD (%)",
        RETURN_YTD_CDI_COLUMN: "CDI YTD (%)",
        RETURN_YTD_IMPLIED_SPREAD_COLUMN: "Spread YTD (% a.a.)",
        RETURN_ISSUANCE_SPREAD_COLUMN: "CDI+ emissão (% a.a.)",
        RETURN_TRAILING_12M_SPREAD_GAP_COLUMN: "Gap 12M (bps)",
        RETURN_YTD_SPREAD_GAP_COLUMN: "Gap YTD (bps)",
    }.get(column, column)


def _append_portfolio_notes(slide, text: str) -> None:
    notes = slide.notes_slide.notes_text_frame
    notes.text = "\n".join(part for part in (notes.text.strip(), text.strip()) if part)


def _refine_portfolio_native_presentation(prs, *, compact=False) -> None:
    """Apply portfolio-only typography and final labels without changing caches."""
    from pptx.oxml.xmlchemy import OxmlElement
    from pptx.util import Inches, Pt

    scale = (11, 12, 14, 16, 20, 24, 32)

    def size(value: float) -> int:
        return next((candidate for candidate in scale if candidate >= value), scale[-1])

    def manual_layout(element, *, x, y, width, height, plot=False):
        layout = element.find("{http://schemas.openxmlformats.org/drawingml/2006/chart}layout")
        if layout is None:
            layout = OxmlElement("c:layout")
            if element.tag.endswith("}legend"):
                element.insert_element_before(layout, "c:overlay", "c:spPr", "c:txPr", "c:extLst")
            else:
                element.insert(0, layout)
        for child in list(layout):
            layout.remove(child)
        manual = OxmlElement("c:manualLayout")
        layout.append(manual)
        if plot:
            target = OxmlElement("c:layoutTarget")
            target.set("val", "inner")
            manual.append(target)
        for tag in ("xMode", "yMode", "wMode", "hMode"):
            mode = OxmlElement("c:" + tag)
            mode.set("val", "factor")
            manual.append(mode)
        for tag, value in (("x", x), ("y", y), ("w", width), ("h", height)):
            coordinate = OxmlElement("c:" + tag)
            coordinate.set("val", str(value))
            manual.append(coordinate)

    for slide in prs.slides:
        for shape in slide.shapes:
            text_frames = []
            if shape.has_text_frame:
                if shape.text.startswith(f"* {CVM_RETURN_REINVESTMENT_NOTE}"):
                    _append_portfolio_notes(slide, CVM_RETURN_REINVESTMENT_NOTE)
                    shape.text_frame.text = "Retornos CVM. Reinvestimentos e lacunas: consulte as notas."
                text_frames.append(shape.text_frame)
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        text_frames.append(cell.text_frame)
            for text_frame in text_frames:
                text_frame.margin_top = text_frame.margin_bottom = Inches(0.01)
                for paragraph in text_frame.paragraphs:
                    for run in paragraph.runs:
                        run.font.name = "Calibri"
                        run.font.size = Pt(size(run.font.size.pt if run.font.size else 11))
            if not shape.has_chart:
                continue
            chart = shape.chart
            chart.category_axis.has_title = False
            for axis in (chart.category_axis, chart.value_axis):
                axis.tick_labels.font.size = Pt(11)
                axis.tick_labels.font.name = "Calibri"
            if chart.has_legend:
                chart.legend.font.size = Pt(11)
                chart.legend.include_in_layout = False
                legend = chart._chartSpace.find(".//{http://schemas.openxmlformats.org/drawingml/2006/chart}legend")
                plot_area = chart._chartSpace.find(".//{http://schemas.openxmlformats.org/drawingml/2006/chart}plotArea")
                manual_layout(plot_area, x=0.15, y=0.16, width=0.82, height=0.55, plot=True)
                manual_layout(legend, x=0.02, y=0.87, width=0.96, height=0.11)
            for props in chart._chartSpace.iter():
                if props.tag.endswith("}rPr") or props.tag.endswith("}defRPr"):
                    previous = float(props.get("sz", "1100")) / 100
                    props.set("sz", str(size(previous) * 100))
            is_line = "LINE" in str(chart.chart_type)
            observed = [float(value) for series in chart.series for value in series.values if value is not None]
            if observed and min(observed) >= 0 and chart.value_axis.minimum_scale is None:
                chart.value_axis.minimum_scale = 0
            if observed and max(observed) > 0 and chart.value_axis.maximum_scale is None:
                if "STACKED" in str(chart.chart_type):
                    totals = [sum(max(0, float(value)) for value in values if value is not None)
                              for values in zip(*(series.values for series in chart.series))]
                    upper = max(totals, default=max(observed))
                else:
                    upper = max(observed)
                if upper > 0 and upper * 1.15 > (chart.value_axis.minimum_scale or 0):
                    chart.value_axis.maximum_scale = upper * 1.15
            labeled_points = set()
            dense_labels = None
            if compact and is_line and len(chart.series) > 6:
                # Keep every series; select legible annotations, with the consolidated first.
                dense_labels = set()
                endpoints = []
                value_range = (chart.value_axis.maximum_scale or max(observed, default=1)) - (chart.value_axis.minimum_scale or min(observed, default=0))
                separation = abs(value_range) * 0.30 / max(shape.height / 914400 * 0.55, 0.5)
                order = sorted(range(len(chart.series)), key=lambda index: chart.series[index].name != "Consolidado")
                for index in order:
                    points = [(position, value) for position, value in enumerate(chart.series[index].values) if value is not None]
                    if not points:
                        continue
                    point = points[-1]
                    if any(point[0] == earlier[0] and abs(point[1] - earlier[1]) < separation for earlier in endpoints):
                        continue
                    dense_labels.add(index)
                    endpoints.append(point)
                _append_portfolio_notes(slide, "Rótulos finais próximos: o consolidado tem prioridade. As demais anotações são espaçadas; todas as séries e valores continuam no gráfico e na planilha nativa.")
            for series_index, series in enumerate(chart.series):
                valid = [(index, value) for index, value in enumerate(series.values) if value is not None]
                last = valid[-1][0] if valid else None
                labels = series._element.find("{http://schemas.openxmlformats.org/drawingml/2006/chart}dLbls")
                if labels is None:
                    continue
                repeated = is_line and last is not None and (last, series.values[last]) in labeled_points
                for label in list(labels):
                    if not label.tag.endswith("}dLbl"):
                        continue
                    index = label.find("{http://schemas.openxmlformats.org/drawingml/2006/chart}idx")
                    dense_stack = "STACKED" in str(chart.chart_type) and len(series.values) > 8
                    if dense_stack or repeated or dense_labels is not None and series_index not in dense_labels or index is None or int(index.get("val")) != last:
                        labels.remove(label)
                if last is not None and is_line and not repeated and (dense_labels is None or series_index in dense_labels):
                    labeled_points.add((last, series.values[last]))
                    position = series.points[last].data_label
                    from pptx.enum.chart import XL_DATA_LABEL_POSITION
                    position.position = XL_DATA_LABEL_POSITION.ABOVE if dense_labels is not None else (
                        XL_DATA_LABEL_POSITION.ABOVE if series_index % 2 == 0
                        else XL_DATA_LABEL_POSITION.BELOW
                    )
            category_axis = chart._chartSpace.find(".//{http://schemas.openxmlformats.org/drawingml/2006/chart}catAx")
            if category_axis is not None:
                skip = category_axis.find("{http://schemas.openxmlformats.org/drawingml/2006/chart}tickLblSkip")
                if skip is None:
                    skip = OxmlElement("c:tickLblSkip")
                    category_axis.insert_element_before(skip, "c:tickMarkSkip", "c:noMultiLvlLbl", "c:extLst")
                category_count = max((len(series.values) for series in chart.series), default=0)
                skip.set("val", "2" if category_count > 9 else "1")
        _append_portfolio_notes(
            slide,
            "Rótulos numéricos priorizam o último ponto válido; todos os pontos e séries continuam nos gráficos nativos editáveis. "
            "Pontos finais idênticos compartilham um rótulo. Barras empilhadas densas priorizam o total destacado; valores dos segmentos permanecem nos dados editáveis. "
            "Competências extensas podem ter rótulos alternados para preservar a leitura.",
        )


def _build_fund_return_pages(
    outputs: Any,
    fund_sections: list[tuple[str, str, str, str, str]],
    *,
    monthly_cdi_rates_by_fund: Mapping[str, Iterable[Any]] | None = None,
    benchmark_spreads_by_fund: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, list[pd.DataFrame]]:
    """Prepara páginas mensais e comparativas das tabelas de rentabilidade."""
    histories = getattr(outputs, "fund_return_history", {})
    summaries = getattr(outputs, "fund_return_summary", {})
    if not isinstance(histories, dict):
        histories = {}
    if not isinstance(summaries, dict):
        summaries = {}
    if not histories and not summaries:
        return {}

    pages_by_fund: dict[str, list[pd.DataFrame]] = {}
    for _, cnpj, _, _, _ in fund_sections:
        monthly_cdi_rates = (
            None
            if monthly_cdi_rates_by_fund is None
            else monthly_cdi_rates_by_fund.get(cnpj, ())
        )
        benchmark_spreads = (
            None
            if benchmark_spreads_by_fund is None
            else benchmark_spreads_by_fund.get(cnpj, {})
        )
        matrix = build_fund_return_matrix(
            outputs,
            cnpj,
            months=12,
            monthly_cdi_rates=monthly_cdi_rates,
            benchmark_spreads=benchmark_spreads,
        )
        if not isinstance(matrix, pd.DataFrame) or matrix.empty:
            continue
        formatted = format_fund_return_matrix(matrix)
        if not isinstance(formatted, pd.DataFrame) or formatted.empty:
            continue

        month_columns = [
            column
            for column in formatted.columns
            if column not in _RETURN_SUMMARY_COLUMNS
        ]
        monthly_columns = [
            RETURN_SERIES_COLUMN,
            *month_columns,
            RETURN_TRAILING_12M_COLUMN,
            RETURN_YTD_COLUMN,
        ]
        if any(column not in formatted.columns for column in monthly_columns):
            continue
        table_views = [formatted.loc[:, monthly_columns].reset_index(drop=True)]
        comparison_columns = [
            column
            for column in _RETURN_COMPARISON_COLUMNS
            if column in formatted.columns
        ]
        if (
            any(column in formatted.columns for column in _RETURN_COMPARISON_DETAIL_COLUMNS)
            and len(comparison_columns) > 1
        ):
            table_views.append(formatted.loc[:, comparison_columns].reset_index(drop=True))

        pages_by_fund[cnpj] = [
            view.iloc[start : start + _RETURN_ROWS_PER_SLIDE].reset_index(drop=True)
            for view in table_views
            for start in range(0, len(view), _RETURN_ROWS_PER_SLIDE)
        ]
    return pages_by_fund


def _build_fund_sections(
    outputs: Any,
    fund_monthly_map: dict[str, pd.DataFrame],
) -> list[tuple[str, str, str, str, str]]:
    metadata_names = _fund_names_from_metadata(getattr(outputs, "metadata", {}) or {})
    sections: list[tuple[str, str, str, str, str]] = []
    for idx, (cnpj, frame) in enumerate(fund_monthly_map.items(), start=2):
        raw_name = _raw_fund_name(
            frame,
            fallback=metadata_names.get(_digits(cnpj)) or str(cnpj),
        )
        header, subtitle = _fund_title_meta(raw_name)
        sections.append((f"{idx:02d}", cnpj, header, subtitle, raw_name))
    return sections


def _fund_names_from_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    for item in metadata.get("funds") or []:
        if not isinstance(item, dict):
            continue
        cnpj = _digits(item.get("cnpj"))
        name = str(item.get("name") or "").strip()
        if cnpj and name:
            names[cnpj] = name
    return names


def _raw_fund_name(frame: pd.DataFrame, *, fallback: str) -> str:
    if frame is not None and not frame.empty and "fund_name" in frame.columns and frame["fund_name"].notna().any():
        raw = str(frame["fund_name"].dropna().iloc[0]).strip()
        if raw:
            return raw
    return str(fallback or "").strip()


def _fund_title_meta(raw_name: str) -> tuple[str, str]:
    key = str(raw_name or "").strip().upper()
    if key in _FUND_NAMES:
        return _FUND_NAMES[key]
    for prefix, short, subtitle in _FUND_PREFIXES:
        if key.startswith(prefix):
            return short, subtitle
    header = short_fund_name(raw_name)
    subtitle = str(raw_name or header).strip()
    return header or subtitle or "FIDC", subtitle or header or "FIDC"


def _is_mercado_credito_zero(raw_name: str) -> bool:
    key = str(raw_name or "").strip().upper()
    return key == "MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA"


def _digits(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _last_12m(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra para os últimos 12 meses da série."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    out = df.copy()
    out["_dt"] = pd.to_datetime(out.get("competencia_dt", out.get("competencia")), errors="coerce")
    out = out.sort_values("_dt").dropna(subset=["_dt"])
    if len(out) > 12:
        out = out.tail(12)
    return out.drop(columns=["_dt"], errors="ignore").reset_index(drop=True)


def _chart_monthly(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out["competencia_dt"] = pd.to_datetime(
        out.get("competencia_dt", out.get("competencia")), errors="coerce"
    )
    return out.sort_values("competencia_dt").reset_index(drop=True)


def _category_labels(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []
    labels = []
    for _, row in df.iterrows():
        ts = pd.to_datetime(row.get("competencia_dt"), errors="coerce")
        if pd.notna(ts):
            labels.append(f"{_PT_MONTH[int(ts.month)]}/{str(int(ts.year))[-2:]}")
        else:
            labels.append(str(row.get("competencia") or ""))
    return labels


def _detect_data_base(df: pd.DataFrame) -> str:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return "mar/26"
    out = _chart_monthly(df)
    if out.empty:
        return "mar/26"
    ts = pd.to_datetime(out.iloc[-1].get("competencia_dt"), errors="coerce")
    if pd.notna(ts):
        return f"{_PT_MONTH[int(ts.month)]}/{str(ts.year)[-2:]}"
    return "mar/26"


def _build_kpi_cards(
    monitor_df: pd.DataFrame, monthly_df: pd.DataFrame
) -> list[tuple[str, str]]:
    """Retorna lista (label, value) para o KPI strip."""
    row = None
    if isinstance(monitor_df, pd.DataFrame) and not monitor_df.empty:
        df = _chart_monthly(monitor_df)
        if not df.empty:
            row = df.iloc[-1]

    if row is None and isinstance(monthly_df, pd.DataFrame) and not monthly_df.empty:
        df = _chart_monthly(monthly_df)
        if not df.empty:
            row = df.iloc[-1]

    if row is None:
        return []

    comp = _fmt_month(row.get("competencia_dt") or row.get("competencia"))
    cart_label = f"Carteira Bruta ex-360 · {comp}" if comp else "Carteira Bruta ex-360"
    return [
        (cart_label, _fmt_money(_num(row.get("carteira_ex360")))),
        ("NPL Over 1d ex-360", _fmt_pct(_num(row.get("npl_over1_ex360_pct")))),
        ("NPL Over 30d ex-360", _fmt_pct(_num(row.get("npl_over30_ex360_pct")))),
        ("NPL Over 60d ex-360", _fmt_pct(_num(row.get("npl_over60_ex360_pct")))),
        ("NPL Over 90d ex-360", _fmt_pct(_num(row.get("npl_over90_ex360_pct")))),
        ("Duration", _fmt_duration(_num(row.get("duration_months")))),
    ]


def _build_synthesis_sections(
    *,
    consolidated_monitor: pd.DataFrame,
    consolidated_monthly: pd.DataFrame,
    fund_monitor_map: dict[str, pd.DataFrame],
    fund_monthly_map: dict[str, pd.DataFrame],
) -> dict[str, list[str]]:
    con_row = _latest_row(consolidated_monitor)
    con_monthly_row = _latest_row(consolidated_monthly)
    attention: list[str] = []
    highlights: list[str] = []

    fund_npl = _latest_fund_metric(fund_monitor_map, "npl_over90_ex360_pct")
    if fund_npl is not None:
        name, value = fund_npl
        con_npl = _num(con_row.get("npl_over90_ex360_pct")) if con_row is not None else None
        suffix = f"; consolidado em {_fmt_pct(con_npl)}" if con_npl is not None else ""
        attention.append(f"Maior Over 90 ex-360: {name} em {_fmt_pct(value)}{suffix}.")

    fund_coverage = _latest_fund_metric(
        fund_monthly_map,
        "pdd_npl_over90_ex360_pct",
        choose="min",
    )
    if fund_coverage is not None:
        name, value = fund_coverage
        attention.append(f"Menor cobertura PDD/Over 90 ex-360: {name} em {_fmt_pct(value)}.")

    duration = _num(con_row.get("duration_months")) if con_row is not None else None
    if duration is not None:
        attention.append(f"Duration consolidada em {_fmt_duration(duration)}; acompanhar dispersão entre fundos.")

    carteira = _num(con_row.get("carteira_ex360")) if con_row is not None else None
    yoy = _num(con_row.get("carteira_ex360_yoy_pct")) if con_row is not None else None
    if carteira is not None:
        yoy_text = f", com variação YoY de {_fmt_pct(yoy)}" if yoy is not None else ""
        highlights.append(f"Carteira Bruta ex-360 consolidada em {_fmt_money(carteira)}{yoy_text}.")

    subordination = _num(con_monthly_row.get("subordinacao_total_ex360_pct")) if con_monthly_row is not None else None
    if subordination is not None:
        highlights.append(f"Subordinação total ex-360 em {_fmt_pct(subordination)} na data-base.")

    coverage = _num(con_monthly_row.get("pdd_npl_over90_ex360_pct")) if con_monthly_row is not None else None
    if coverage is not None:
        highlights.append(f"Cobertura consolidada PDD/Over 90 ex-360 em {_fmt_pct(coverage)}.")

    npl_delta = _latest_delta(consolidated_monitor, "npl_over90_ex360_pct")
    if npl_delta is not None and len(highlights) < 3:
        direction = "recuou" if npl_delta < 0 else "avançou"
        highlights.append(f"Over 90 ex-360 {direction} {_fmt_pp(abs(npl_delta))} versus mês anterior.")

    return {
        "attention": _ensure_three_bullets(
            attention,
            [
                "Sem alerta automático adicional com a base disponível.",
                "Verificar manualmente eventos regulatórios relevantes antes de uso externo.",
                "Manter leitura por fundo para identificar concentração de risco.",
            ],
        ),
        "highlights": _ensure_three_bullets(
            highlights,
            [
                "Deck gerado com gráficos nativos e editáveis no PowerPoint.",
                "Data-base, fonte e paginação preservadas automaticamente.",
                "Indicadores percentuais recalculados a partir das bases consolidadas.",
            ],
        ),
    }


def _latest_row(frame: pd.DataFrame | None) -> pd.Series | None:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    df = _chart_monthly(frame)
    if df.empty:
        return None
    return df.iloc[-1]


def _compact_synthesis_sections(slide, sections, consolidated_monitor, fund_monthly_map, fund_monitor_map):
    """Refine the existing conclusions; keep the original wording in notes."""
    generic = {
        "Sem alerta automático adicional com a base disponível.",
        "Verificar manualmente eventos regulatórios relevantes antes de uso externo.",
        "Manter leitura por fundo para identificar concentração de risco.",
        "Deck gerado com gráficos nativos e editáveis no PowerPoint.",
        "Data-base, fonte e paginação preservadas automaticamente.",
        "Indicadores percentuais recalculados a partir das bases consolidadas.",
    }
    names = {
        _raw_fund_name(frame, fallback=cnpj): short_fund_name(_raw_fund_name(frame, fallback=cnpj))
        for mapping in (fund_monthly_map, fund_monitor_map) for cnpj, frame in mapping.items()
    }
    result = {}
    removed = []
    delta = _latest_delta(consolidated_monitor, "npl_over90_ex360_pct")
    for section, bullets in sections.items():
        visible = []
        for bullet in bullets:
            if bullet in generic:
                removed.append(bullet)
                continue
            if delta == 0 and bullet.startswith("Over 90 ex-360 avançou "):
                bullet = "Over 90 ex-360 estável versus mês anterior (variação zero)."
            for full_name, short_name in sorted(names.items(), key=lambda item: len(item[0]), reverse=True):
                if full_name:
                    bullet = bullet.replace(full_name, short_name)
            visible.append(bullet)
        result[section] = visible
    if removed:
        _append_portfolio_notes(slide, "Compactação: textos automáticos sem conclusão financeira foram retirados da síntese: " + " | ".join(removed))
    _append_portfolio_notes(slide, "Síntese original, antes da apresentação compacta:\n" + "\n".join(bullet for bullets in sections.values() for bullet in bullets))
    return result


def _latest_fund_metric(
    fund_map: dict[str, pd.DataFrame],
    column: str,
    *,
    choose: str = "max",
) -> tuple[str, float] | None:
    rows: list[tuple[str, float]] = []
    for cnpj, frame in fund_map.items():
        row = _latest_row(frame)
        if row is None:
            continue
        value = _num(row.get(column))
        if value is None:
            continue
        rows.append((_fund_display_name(frame, fallback=str(cnpj)), value))
    if not rows:
        return None
    key = lambda item: item[1]
    return min(rows, key=key) if choose == "min" else max(rows, key=key)


def _latest_delta(frame: pd.DataFrame | None, column: str) -> float | None:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty or column not in frame.columns:
        return None
    df = _chart_monthly(frame)
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    if len(values) < 2:
        return None
    return float(values.iloc[-1] - values.iloc[-2])


def _ensure_three_bullets(items: list[str], fallbacks: list[str]) -> list[str]:
    clean = [item for item in items if item]
    for fallback in fallbacks:
        if len(clean) >= 3:
            break
        clean.append(fallback)
    return clean[:3]


def _build_duration_frame(
    consolidated: pd.DataFrame, fund_map: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    rows = []
    if consolidated is not None and not consolidated.empty:
        rows.extend(_duration_rows(consolidated, "Consolidado"))
    for cnpj, frame in fund_map.items():
        name = _fund_display_name(frame, fallback=str(cnpj))
        rows.extend(_duration_rows(frame, name))
    if not rows:
        return pd.DataFrame()
    long = pd.DataFrame(rows)
    wide = (long.pivot_table(index=["competencia_dt", "competencia"],
                             columns="serie", values="duration_months",
                             aggfunc="last")
            .reset_index())
    wide.columns.name = None
    # Rename series cols to short names
    renames = {c: _short_name(c) for c in wide.columns
               if c not in {"competencia_dt", "competencia"}}
    wide = wide.rename(columns=renames)
    return wide.sort_values("competencia_dt").reset_index(drop=True)


def _duration_rows(frame: pd.DataFrame, label: str) -> list[dict]:
    if frame is None or frame.empty:
        return []
    df = _chart_monthly(frame)
    vals = pd.to_numeric(df.get("duration_months"), errors="coerce")
    return [
        {
            "competencia_dt": row.get("competencia_dt"),
            "competencia": row.get("competencia"),
            "serie": label,
            "duration_months": vals.iloc[i],
        }
        for i, (_, row) in enumerate(df.iterrows())
    ]


def _research_roll_wide(roll_df: pd.DataFrame, *, metric_id: str) -> pd.DataFrame:
    if roll_df is None or roll_df.empty:
        return pd.DataFrame()
    mask = (
        roll_df.get("scope", pd.Series(dtype="object")).astype(str).eq("consolidado")
        & roll_df["metric_id"].eq(metric_id)
    )
    df = roll_df[mask].copy()
    if df.empty:
        return pd.DataFrame()
    df["month"] = pd.to_numeric(df.get("month"), errors="coerce")
    df = df.sort_values("month")
    wide = (df.pivot_table(index=["month", "month_label"],
                           columns="series_name", values="value_pct",
                           aggfunc="last")
            .reset_index())
    wide.columns.name = None
    return wide.rename(columns={"month_label": "competencia"}).reset_index(drop=True)


# ===========================================================================
# FORMATTING HELPERS
# ===========================================================================

def _fund_display_name(frame: pd.DataFrame, *, fallback: str) -> str:
    if frame is not None and not frame.empty and "fund_name" in frame.columns:
        raw = str(frame["fund_name"].dropna().iloc[0]) if frame["fund_name"].notna().any() else fallback
    else:
        raw = fallback
    return _short_name(raw)


def _short_name(raw: str) -> str:
    """Converte nome longo para header curto."""
    key = raw.strip().upper()
    if key in _FUND_NAMES:
        return _FUND_NAMES[key][0]
    for prefix, short, _ in _FUND_PREFIXES:
        if key.startswith(prefix):
            return short
    return short_fund_name(raw) or raw


def _fmt_month(value) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    return f"{_PT_MONTH[int(ts.month)]}/{str(int(ts.year))[-2:]}" if pd.notna(ts) else ""


def _fmt_money(v) -> str:
    if v is None:
        return "N/D"
    scale_div, scale_lbl = _money_scale(pd.Series([v]))
    scaled = v / scale_div
    dec = 0 if abs(scaled) >= 10 else 1
    unit = scale_lbl.removeprefix("R$").strip()
    return f"R$ {_br(scaled, dec)} {unit}".strip()


def _fmt_pct(v) -> str:
    if v is None:
        return "N/D"
    return f"{_br(v, 1)}%"


def _fmt_duration(v) -> str:
    if v is None:
        return "N/D"
    return f"{_br(v, 1)} meses"


def _fmt_pp(v) -> str:
    if v is None:
        return "N/D"
    return f"{_br(v, 1)} p.p."


def _fmt_money_scaled(total: float, div: float, lbl: str) -> str:
    scaled = total / div if div else total
    dec = 0 if abs(scaled) >= 10 else 1
    n = _br(scaled, dec)
    if lbl == "R$":
        return f"R$ {n}"
    return f"R$ {n} {lbl.replace('R$ ', '')}"


def _fmt_val(v, *, percent: bool, decimals: int) -> str:
    if v is None:
        return "N/D"
    if percent:
        return f"{_br(v * 100.0, decimals)}%"
    return _br(v, decimals)


def _native_label_number_format(*, metric_kind: str, percent: bool, decimals: int | None = None) -> str:
    if percent or metric_kind in {"npl_pct", "general_pct", "coverage_pct", "roll_pct", "cohort_pct"}:
        places = 1 if decimals is None else max(0, int(decimals))
        return "0%" if places == 0 else "0." + ("0" * places) + "%"
    if metric_kind == "money":
        return "#,##0" if decimals == 0 else "#,##0.0"
    if metric_kind == "duration":
        return "#,##0.0"
    return "#,##0.0"


def _br(v: float, decimals: int) -> str:
    return f"{v:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _pct_val(v) -> float | None:
    n = _num(v)
    return None if n is None else n / 100.0


def _scaled(v, div) -> float | None:
    n = _num(v)
    return None if n is None else n / div


def _num(v) -> float | None:
    parsed = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def _last_non_null(values: list) -> int | None:
    for i in range(len(values) - 1, -1, -1):
        if values[i] is not None and not (isinstance(values[i], float) and pd.isna(values[i])):
            return i
    return None


def _money_scale(values: pd.Series) -> tuple[float, str]:
    mx = pd.to_numeric(values, errors="coerce").abs().max()
    if pd.isna(mx):
        mx = 0.0
    if mx >= 1_000_000_000_000:
        return 1_000_000_000.0, "R$ bi"
    if mx >= 1_000_000:
        return 1_000_000.0, "R$ mm"
    if mx >= 1_000:
        return 1_000.0, "R$ mil"
    return 1.0, "R$"


def _rgb(hex_color: str, RGBColor):
    c = str(hex_color).strip().lstrip("#")
    return RGBColor(int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


# ===========================================================================
# PPTX PACKAGE POST-PROCESSING
# ===========================================================================

def _normalize_pptx_native_number_formats(pptx_bytes: bytes) -> bytes:
    """Persist axis number formats into chart caches and embedded workbooks.

    PowerPoint can display chart axes correctly while keeping the embedded
    workbook cells and chart value caches as ``General``. That is fragile for
    analyst handoff: editing the chart may expose raw values such as ``1-4``
    instead of ``100%-400%``. This pass keeps the deck fully native/editable and
    makes the underlying Office objects carry the same unit contract as the
    rendered axis.
    """
    try:
        from lxml import etree
        from openpyxl import load_workbook
    except Exception:
        return pptx_bytes

    embedded_formats: dict[str, str] = {}
    updated_payloads: dict[str, bytes] = {}
    chart_ns = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart"}
    rel_ns = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}

    with ZipFile(BytesIO(pptx_bytes), "r") as zin:
        names = set(zin.namelist())
        for name in sorted(n for n in names if n.startswith("ppt/charts/chart") and n.endswith(".xml")):
            xml = zin.read(name)
            try:
                root = etree.fromstring(xml)
            except Exception:
                continue
            fmt = _chart_value_axis_format(root, chart_ns)
            if not fmt:
                continue
            changed = _set_chart_value_cache_format(root, fmt, chart_ns)
            if changed:
                updated_payloads[name] = etree.tostring(
                    root,
                    xml_declaration=True,
                    encoding="UTF-8",
                    standalone=True,
                )

            rels_name = _chart_rels_path(name)
            if rels_name in names:
                try:
                    rel_root = etree.fromstring(zin.read(rels_name))
                except Exception:
                    continue
                for rel in rel_root.xpath(".//rel:Relationship", namespaces=rel_ns):
                    target = str(rel.get("Target") or "")
                    if "embeddings/" not in target or not target.endswith(".xlsx"):
                        continue
                    embedded_name = _resolve_package_target(name, target)
                    embedded_formats[embedded_name] = fmt

        for embedded_name, fmt in embedded_formats.items():
            if embedded_name not in names:
                continue
            try:
                wb = load_workbook(BytesIO(zin.read(embedded_name)))
                for ws in wb.worksheets:
                    for row in ws.iter_rows(min_row=2, min_col=2):
                        for cell in row:
                            if isinstance(cell.value, (int, float)):
                                cell.number_format = fmt
                out = BytesIO()
                wb.save(out)
                updated_payloads[embedded_name] = out.getvalue()
            except Exception:
                continue

        if not updated_payloads:
            return pptx_bytes

        out_zip = BytesIO()
        with ZipFile(out_zip, "w", compression=ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                payload = updated_payloads.get(info.filename, zin.read(info.filename))
                zout.writestr(info.filename, payload)
        return out_zip.getvalue()


def _chart_value_axis_format(root, chart_ns: dict[str, str]) -> str | None:  # noqa: ANN001
    num_fmt = root.find(".//c:valAx/c:numFmt", namespaces=chart_ns)
    if num_fmt is not None and num_fmt.get("formatCode"):
        return str(num_fmt.get("formatCode"))
    axis_title = "".join(root.xpath(".//c:valAx/c:title//text()", namespaces=chart_ns))
    if "%" in axis_title:
        return "0.0%"
    if "R$" in axis_title:
        return "#,##0.0"
    if "mes" in axis_title.lower():
        return "#,##0.0"
    return None


def _set_chart_value_cache_format(root, fmt: str, chart_ns: dict[str, str]) -> bool:  # noqa: ANN001
    from lxml import etree
    from pptx.oxml.ns import qn

    changed = False
    for num_cache in root.xpath(".//c:ser/c:val//c:numCache", namespaces=chart_ns):
        format_code = num_cache.find(qn("c:formatCode"))
        if format_code is None:
            format_code = etree.Element(qn("c:formatCode"))
            num_cache.insert(0, format_code)
            changed = True
        if format_code.text != fmt:
            format_code.text = fmt
            changed = True
    return changed


def _chart_rels_path(chart_path: str) -> str:
    path = PurePosixPath(chart_path)
    return str(path.parent / "_rels" / f"{path.name}.rels")


def _resolve_package_target(base_path: str, target: str) -> str:
    parts: list[str] = []
    for part in (PurePosixPath(base_path).parent / target).parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part not in {"", "."}:
            parts.append(part)
    return "/".join(parts)
