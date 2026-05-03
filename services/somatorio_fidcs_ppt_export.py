from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd


def build_somatorio_fidcs_pptx_bytes(
    *,
    outputs: Any,
    monitor_outputs: Any,
    research_outputs: Any | None = None,
) -> bytes:
    """Gera um único PPTX com a visão base do Somatório e a análise de crédito."""
    try:
        from pptx import Presentation
        from pptx.chart.data import CategoryChartData
        from pptx.dml.color import RGBColor
        from pptx.enum.chart import XL_CHART_TYPE, XL_DATA_LABEL_POSITION, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE
        from pptx.util import Inches, Pt
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("Dependência python-pptx não instalada.") from exc

    from services import mercado_livre_ppt_export as base_ppt
    from services import meli_credit_monitor_ppt_export as credit_ppt

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    layout = prs.slide_layouts[6]

    _add_base_slides(
        prs=prs,
        layout=layout,
        outputs=outputs,
        base_ppt=base_ppt,
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_DATA_LABEL_POSITION=XL_DATA_LABEL_POSITION,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
    )
    _add_credit_slides(
        prs=prs,
        layout=layout,
        monitor_outputs=monitor_outputs,
        research_outputs=research_outputs,
        credit_ppt=credit_ppt,
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_LABEL_POSITION=XL_LABEL_POSITION,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
    )

    buffer = BytesIO()
    prs.save(buffer)
    return buffer.getvalue()


def _add_base_slides(
    *,
    prs,
    layout,
    outputs: Any,
    base_ppt,
    CategoryChartData,
    RGBColor,
    XL_CHART_TYPE,
    XL_DATA_LABEL_POSITION,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
    Inches,
    Pt,
) -> None:
    scopes: list[tuple[str, pd.DataFrame]] = [("Somatório FIDCs - Base consolidada", outputs.consolidated_monthly)]
    for cnpj, frame in getattr(outputs, "fund_monthly", {}).items():
        fund_name = (
            str(frame["fund_name"].iloc[0])
            if isinstance(frame, pd.DataFrame) and not frame.empty and "fund_name" in frame.columns
            else str(cnpj)
        )
        scopes.append((fund_name, frame))

    for scope_name, monthly_df in scopes:
        base_ppt._add_scope_grid_slide(  # noqa: SLF001 - reuso deliberado do layout existente.
            prs=prs,
            layout=layout,
            scope_name=scope_name,
            monthly_df=monthly_df,
            CategoryChartData=CategoryChartData,
            RGBColor=RGBColor,
            XL_CHART_TYPE=XL_CHART_TYPE,
            XL_DATA_LABEL_POSITION=XL_DATA_LABEL_POSITION,
            XL_LEGEND_POSITION=XL_LEGEND_POSITION,
            XL_MARKER_STYLE=XL_MARKER_STYLE,
            Inches=Inches,
            Pt=Pt,
        )


def _add_credit_slides(
    *,
    prs,
    layout,
    monitor_outputs: Any,
    research_outputs: Any | None,
    credit_ppt,
    CategoryChartData,
    RGBColor,
    XL_CHART_TYPE,
    XL_LABEL_POSITION,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
    Inches,
    Pt,
) -> None:
    credit_ppt._add_consolidated_slide(  # noqa: SLF001 - reuso deliberado do layout existente.
        prs=prs,
        layout=layout,
        monitor_outputs=monitor_outputs,
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_LABEL_POSITION=XL_LABEL_POSITION,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
    )
    credit_ppt._add_consolidated_detail_slide(  # noqa: SLF001 - reuso deliberado do layout existente.
        prs=prs,
        layout=layout,
        monitor_outputs=monitor_outputs,
        research_outputs=research_outputs,
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_LABEL_POSITION=XL_LABEL_POSITION,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
    )
    if research_outputs is not None and not getattr(research_outputs, "roll_seasonality", pd.DataFrame()).empty:
        credit_ppt._add_consolidated_roll_seasonality_slide(  # noqa: SLF001 - reuso deliberado do layout existente.
            prs=prs,
            layout=layout,
            research_outputs=research_outputs,
            CategoryChartData=CategoryChartData,
            RGBColor=RGBColor,
            XL_CHART_TYPE=XL_CHART_TYPE,
            XL_LABEL_POSITION=XL_LABEL_POSITION,
            XL_LEGEND_POSITION=XL_LEGEND_POSITION,
            XL_MARKER_STYLE=XL_MARKER_STYLE,
            Inches=Inches,
            Pt=Pt,
        )
    for cnpj, monitor in getattr(monitor_outputs, "fund_monitor", {}).items():
        credit_ppt._add_fund_slide(  # noqa: SLF001 - reuso deliberado do layout existente.
            prs=prs,
            layout=layout,
            title=credit_ppt._fund_name(monitor, fallback=str(cnpj)),  # noqa: SLF001
            monitor_df=monitor,
            cohort_df=getattr(monitor_outputs, "fund_cohorts", {}).get(cnpj, pd.DataFrame()),
            CategoryChartData=CategoryChartData,
            RGBColor=RGBColor,
            XL_CHART_TYPE=XL_CHART_TYPE,
            XL_LABEL_POSITION=XL_LABEL_POSITION,
            XL_LEGEND_POSITION=XL_LEGEND_POSITION,
            XL_MARKER_STYLE=XL_MARKER_STYLE,
            Inches=Inches,
            Pt=Pt,
        )
