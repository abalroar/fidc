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

    _add_interleaved_slides(
        prs=prs,
        layout=layout,
        outputs=outputs,
        monitor_outputs=monitor_outputs,
        research_outputs=research_outputs,
        base_ppt=base_ppt,
        credit_ppt=credit_ppt,
        CategoryChartData=CategoryChartData,
        RGBColor=RGBColor,
        XL_CHART_TYPE=XL_CHART_TYPE,
        XL_DATA_LABEL_POSITION=XL_DATA_LABEL_POSITION,
        XL_LABEL_POSITION=XL_LABEL_POSITION,
        XL_LEGEND_POSITION=XL_LEGEND_POSITION,
        XL_MARKER_STYLE=XL_MARKER_STYLE,
        Inches=Inches,
        Pt=Pt,
    )

    buffer = BytesIO()
    prs.save(buffer)
    return buffer.getvalue()


def _add_interleaved_slides(
    *,
    prs,
    layout,
    outputs: Any,
    monitor_outputs: Any,
    research_outputs: Any | None,
    base_ppt,
    credit_ppt,
    CategoryChartData,
    RGBColor,
    XL_CHART_TYPE,
    XL_DATA_LABEL_POSITION,
    XL_LABEL_POSITION,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
    Inches,
    Pt,
) -> None:
    _add_base_scope_slide(
        prs=prs,
        layout=layout,
        scope_name="Somatório FIDCs - Base consolidada",
        monthly_df=outputs.consolidated_monthly,
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
    for cnpj, monthly_df in getattr(outputs, "fund_monthly", {}).items():
        fund_name = (
            str(monthly_df["fund_name"].iloc[0])
            if isinstance(monthly_df, pd.DataFrame) and not monthly_df.empty and "fund_name" in monthly_df.columns
            else str(cnpj)
        )
        _add_base_scope_slide(
            prs=prs,
            layout=layout,
            scope_name=fund_name,
            monthly_df=monthly_df,
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
        monitor = getattr(monitor_outputs, "fund_monitor", {}).get(cnpj, pd.DataFrame())
        title = credit_ppt._fund_name(monitor, fallback=fund_name)  # noqa: SLF001
        credit_ppt._add_fund_slide(  # noqa: SLF001 - reuso deliberado do layout existente.
            prs=prs,
            layout=layout,
            title=title,
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
        credit_ppt._add_fund_detail_slide(  # noqa: SLF001 - reuso deliberado do layout existente.
            prs=prs,
            layout=layout,
            title=title,
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


def _add_base_scope_slide(
    *,
    prs,
    layout,
    scope_name: str,
    monthly_df: pd.DataFrame,
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
