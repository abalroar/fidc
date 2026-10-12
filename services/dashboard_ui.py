from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from contextlib import contextmanager
from html import escape
import re
from typing import Any, Iterator

import altair as alt
import streamlit as st


FONT_FAMILY = "IBM Plex Sans"
ACCENT = "#ff5a00"
INK = "#202832"
MUTED = "#66717d"
GRID = "#e5e8ec"

PLOTLY_CHART_CONFIG: dict[str, Any] = {
    "displayModeBar": "hover",
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": False,
}


@alt.theme.register("fidc_finance", enable=False)
def _fidc_finance_theme() -> alt.theme.ThemeConfig:
    return alt.theme.ThemeConfig(
        {
            "config": {
                "background": "transparent",
                "font": FONT_FAMILY,
                "view": {"stroke": None},
                "axis": {
                    "domainColor": "#cfd4da",
                    "grid": False,
                    "labelColor": MUTED,
                    "labelFont": FONT_FAMILY,
                    "labelFontSize": 11,
                    "labelOverlap": "greedy",
                    "tickColor": "#cfd4da",
                    "titleColor": MUTED,
                    "titleFont": FONT_FAMILY,
                    "titleFontSize": 11,
                    "titleFontWeight": 500,
                },
                "axisX": {"grid": False, "labelFlush": True},
                "axisY": {"grid": True, "gridColor": GRID, "gridOpacity": 0.8},
                "legend": {
                    "columns": 3,
                    "direction": "horizontal",
                    "labelColor": MUTED,
                    "labelFont": FONT_FAMILY,
                    "labelFontSize": 11,
                    "labelLimit": 220,
                    "orient": "bottom",
                    "symbolSize": 70,
                    "title": None,
                },
                "line": {"strokeWidth": 2},
                "point": {"size": 30},
                "title": {
                    "anchor": "start",
                    "color": INK,
                    "font": FONT_FAMILY,
                    "fontSize": 13,
                    "fontWeight": 600,
                    "offset": 10,
                },
            }
        }
    )


def enable_chart_theme() -> None:
    alt.theme.enable("fidc_finance")


def style_plotly_figure(figure: Any, *, height: int | None = None, showlegend: bool | None = None) -> Any:
    layout: dict[str, Any] = {
        "autosize": True,
        "font": {"family": f"{FONT_FAMILY}, sans-serif", "color": INK, "size": 12},
        "hoverlabel": {"bgcolor": "#ffffff", "font": {"family": f"{FONT_FAMILY}, sans-serif", "color": INK}},
        "legend": {
            "orientation": "h",
            "x": 0,
            "xanchor": "left",
            "y": -0.18,
            "yanchor": "top",
        },
        "margin": {"l": 12, "r": 12, "t": 12, "b": 52},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "uirevision": None,
    }
    if height is not None:
        layout["height"] = height
    if showlegend is not None:
        layout["showlegend"] = showlegend
    figure.update_layout(**layout)
    figure.update_xaxes(
        automargin=True,
        gridcolor=GRID,
        showgrid=False,
        tickfont={"color": MUTED, "size": 11},
        title_font={"color": MUTED, "size": 11},
    )
    figure.update_yaxes(
        automargin=True,
        gridcolor=GRID,
        showgrid=True,
        tickfont={"color": MUTED, "size": 11},
        title_font={"color": MUTED, "size": 11},
        zeroline=False,
    )
    return figure


def diagnostic_mode_from_params(params: Mapping[str, object]) -> bool:
    raw = params.get("diagnostic", "")
    if isinstance(raw, Sequence) and not isinstance(raw, str):
        raw = raw[-1] if raw else ""
    return str(raw).strip().lower() in {"1", "true", "sim", "on", "yes"}


def diagnostics_enabled() -> bool:
    return diagnostic_mode_from_params(st.query_params)


def normalize_single_selection(value: object, options: Sequence[str], *, default: str) -> str:
    if default not in options:
        raise ValueError("default must be present in options")
    return str(value) if value in options else default


def reconcile_context_selection(
    state: MutableMapping[str, Any],
    *,
    signature_key: str,
    value_key: str,
    signature: str,
    options: Sequence[str],
    default: Sequence[str] = (),
) -> tuple[str, ...]:
    valid_options = tuple(dict.fromkeys(str(option) for option in options))
    valid_lookup = set(valid_options)
    context_changed = state.get(signature_key) != signature
    if context_changed:
        selected = tuple(value for value in default if value in valid_lookup)
        state[signature_key] = signature
        state[value_key] = list(selected)
        return selected

    raw_selection = state.get(value_key) or []
    if isinstance(raw_selection, str):
        raw_selection = [raw_selection]
    selected = tuple(str(value) for value in raw_selection if str(value) in valid_lookup)
    if list(selected) != list(raw_selection):
        state[value_key] = list(selected)
    return selected


def render_page_header(title: str, subtitle: str | None = None) -> None:
    subtitle_html = f'<p class="dashboard-page-subtitle">{escape(subtitle)}</p>' if subtitle else ""
    heading_id = f"dashboard-{_safe_scope(title)}"
    st.html(
        f'<header class="dashboard-page-header"><h1 id="{heading_id}">{escape(title)}</h1>{subtitle_html}</header>'
    )


def render_context_strip(*, source: str, base_until: str, coverage: str) -> None:
    items = (
        ("Fonte", source),
        ("Base até", base_until),
        ("Cobertura", coverage),
    )
    html = '<div class="dashboard-context-strip">' + "".join(
        f'<span><b>{escape(label)}:</b> {escape(str(value))}</span>' for label, value in items if str(value).strip()
    ) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


def analysis_context_html(items: Sequence[tuple[str, object]]) -> str:
    """A compact, reusable context; callers supply the financial interpretation."""
    content = "".join(
        f'<div><dt>{escape(label)}</dt><dd>{escape(str(value))}</dd></div>'
        for label, value in items
        if value is not None and str(value).strip()
    )
    return f'<dl class="dashboard-analysis-context" aria-label="Contexto da análise">{content}</dl>'


def indicator_help_html(label: str, items: Sequence[tuple[str, object]], *, glossary_page: str = "") -> str:
    """Native disclosure supports click, touch and Enter/Space without a rerun."""
    content = "".join(
        f'<p><b>{escape(title)}:</b> {escape(str(value))}</p>'
        for title, value in items
        if value is not None and str(value).strip()
    )
    if glossary_page:
        from urllib.parse import quote

        content += (
            '<a target="_blank" rel="noopener" href="?section=glossario&amp;book_page='
            f'{quote(glossary_page, safe="")}">Abrir no glossário</a>'
        )
    return (
        '<details class="dashboard-indicator-help">'
        f'<summary aria-label="Sobre {escape(label, quote=True)}"><span aria-hidden="true">i</span></summary>'
        f'<div class="dashboard-indicator-help-body">{content}</div></details>'
    )


def analytical_components_css(scope: str) -> str:
    """Opt-in styles for context, native help and wide financial comparisons."""
    selector = f".st-key-{_safe_scope(scope)}"
    return f"""<style>
{selector} .dashboard-analysis-context {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: .55rem 1rem; padding: .7rem .8rem; margin: .3rem 0 .75rem;
    background: #f7f5f2; border: 1px solid {GRID}; border-radius: 4px;
}}
{selector} .dashboard-analysis-context div {{ min-width: 0; }}
{selector} .dashboard-analysis-context dt {{ color: {MUTED}; font-size: .73rem; line-height: 1.4; }}
{selector} .dashboard-analysis-context dd {{ margin: .1rem 0 0; color: {INK}; font-size: .85rem; line-height: 1.4; overflow-wrap: anywhere; }}
{selector} .fidc-snapshot-card {{ position: relative; background: #fff; border: 1px solid {GRID}; padding: .7rem; }}
{selector} .fidc-snapshot-card__label {{ padding-right: 34px; line-height: 1.35; }}
{selector} .fidc-snapshot-card__value {{ font-variant-numeric: tabular-nums; }}
{selector} .dashboard-indicator-help summary {{
    position: absolute; top: 0; right: 0; display: flex; align-items: center; justify-content: center;
    width: 44px; min-height: 44px; list-style: none; cursor: pointer; color: {MUTED};
}}
{selector} .dashboard-indicator-help summary::-webkit-details-marker {{ display: none; }}
{selector} .dashboard-indicator-help summary span {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 19px; height: 19px; border: 1px solid #cfd4da; border-radius: 50%; font-size: 12px;
}}
{selector} .dashboard-indicator-help summary:focus-visible,
{selector} .financial-table-region:focus-visible {{ outline: 2px solid {ACCENT}; outline-offset: -2px; }}
{selector} .dashboard-indicator-help[open] summary {{ color: {ACCENT}; }}
{selector} .dashboard-indicator-help-body {{
    position: absolute; top: calc(100% + 4px); right: 0; z-index: 10;
    width: min(340px, calc(100vw - 80px)); max-height: min(460px, 70vh); overflow: auto;
    background: #fff; border: 1px solid {GRID}; border-radius: 4px;
    padding: .75rem; box-shadow: 0 4px 16px rgba(32, 40, 50, .08);
}}
{selector} .fidc-snapshot-card:nth-child(-n+2) .dashboard-indicator-help-body {{ left: 0; right: auto; }}
{selector} .dashboard-indicator-help-body p {{ font-size: .78rem; line-height: 1.45; margin: 0 0 .4rem; }}
{selector} .dashboard-indicator-help-body a {{ color: #a94100; font-size: .78rem; }}
{selector} .monitor-wide-wrapper {{ max-width: 100%; max-height: 620px; overflow: auto; container-type: inline-size; border: 1px solid {GRID}; border-radius: 4px; }}
{selector} .monitor-wide-section {{ margin-bottom: 0; }}
{selector} .monitor-wide-section summary {{
    background: #f7f5f2; color: {INK}; font-weight: 500; min-height: 44px;
    border-bottom: 1px solid {GRID}; padding: .65rem .75rem;
}}
{selector} .monitor-wide-section > summary,
{selector} .wide-section > summary {{ position: sticky; left: 0; width: 100cqi; box-sizing: border-box; }}
{selector} .monitor-wide-table {{ font-size: 13px; font-variant-numeric: tabular-nums; }}
{selector} .monitor-wide-table th {{ border-bottom: 1px solid {GRID}; padding: .6rem .65rem; vertical-align: bottom; }}
{selector} .monitor-wide-table td {{ padding: .45rem .65rem; }}
{selector} .monitor-wide-table th.label-col,
{selector} .monitor-wide-table td.label {{ position: sticky; left: 0; background: #fff; z-index: 3; box-shadow: 1px 0 {GRID}; }}
{selector} .monitor-wide-table th.label-col {{ z-index: 4; }}
{selector} .monitor-wide-table tr.destaque td {{ font-weight: 600; }}
{selector} .monitor-wide-table small {{ color: {MUTED}; display: block; font-size: 10px; font-weight: 400; margin-top: .3rem; }}
{selector} .financial-fund-identity summary {{ background: #fff; border: 0; padding: .3rem 0; font-size: 13px; min-height: 44px; }}
{selector} .financial-fund-identity summary:focus-visible {{ outline: 2px solid {ACCENT}; }}
{selector} .financial-fund-identity span {{ font-size: 11px; font-weight: 400; line-height: 1.4; }}
{selector} .wide-table-wrapper {{ max-width: 100%; max-height: 620px; overflow: auto; container-type: inline-size; border: 1px solid {GRID}; border-radius: 4px; }}
{selector} .wide-section summary {{ background: #f7f5f2; color: {INK}; border-bottom: 1px solid {GRID}; font-weight: 500; min-height: 44px; padding: .65rem .75rem; }}
{selector} .wide-section summary::marker {{ color: {MUTED}; }}
{selector} .wide-table {{ font-size: 13px; font-variant-numeric: tabular-nums; }}
{selector} .wide-table th.label-col, {selector} .wide-table td.label {{ position: sticky; left: 0; background: #fff; z-index: 3; box-shadow: 1px 0 {GRID}; }}
{selector} .wide-table th.label-col {{ z-index: 4; }}
{selector} .wide-table td {{ padding: .45rem .65rem; }}
{selector} .fidc-snapshot-row {{ align-items: start; }}
@media (min-width: 641px) and (max-width: 960px) {{
    {selector} .dashboard-indicator-help-body {{ left: 0; right: auto; }}
    {selector} .fidc-snapshot-card:nth-child(4n) .dashboard-indicator-help-body,
    {selector} .fidc-snapshot-card:nth-child(6) .dashboard-indicator-help-body {{ left: auto; right: 0; }}
}}
@media (max-width: 640px) {{
    {selector} .dashboard-analysis-context {{ grid-template-columns: 1fr 1fr; gap: .55rem .75rem; padding: .65rem; }}
    {selector} .monitor-wide-table th.label-col, {selector} .monitor-wide-table td.label {{ max-width: 140px; }}
    {selector} .monitor-wide-table col:first-child, {selector} .wide-table col:first-child {{ width: 140px !important; }}
    {selector} .fidc-snapshot-row {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .65rem; }}
    {selector} .fidc-snapshot-card {{ min-width: 0; }}
    {selector} .fidc-snapshot-card:nth-child(odd) .dashboard-indicator-help-body {{ left: 0; right: auto; }}
    {selector} .fidc-snapshot-card:nth-child(even) .dashboard-indicator-help-body {{ left: auto; right: 0; }}
}}
@media (max-width: 360px) {{ {selector} .dashboard-analysis-context {{ grid-template-columns: 1fr; }} }}
</style>"""


def _safe_scope(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_") or "page"


def scoped_page_css(container_key: str) -> str:
    selector = f".st-key-{_safe_scope(container_key)}"
    return f"""
<style>
{selector} {{
    --dashboard-accent: {ACCENT};
    --dashboard-grid: {GRID};
    --dashboard-ink: {INK};
    --dashboard-muted: {MUTED};
    max-width: 100%;
    overflow-x: clip;
}}
{selector} .dashboard-page-header {{
    border-bottom: 1px solid #e3e6ea;
    margin: 0.2rem 0 0.75rem;
    padding: 0 0 0.7rem;
}}
{selector} .dashboard-page-header h1 {{
    color: var(--dashboard-ink);
    font-size: 1.7rem;
    font-weight: 650;
    letter-spacing: 0;
    line-height: 1.15;
    margin: 0;
}}
{selector} .dashboard-page-subtitle {{
    color: var(--dashboard-muted);
    font-size: 0.9rem;
    line-height: 1.45;
    margin: 0.28rem 0 0;
    max-width: 72rem;
}}
{selector} .dashboard-context-strip {{
    align-items: center;
    border-bottom: 1px solid #eceef1;
    color: var(--dashboard-muted);
    display: flex;
    flex-wrap: wrap;
    font-size: 0.76rem;
    gap: 0.25rem 0.8rem;
    line-height: 1.4;
    margin: -0.15rem 0 0.8rem;
    padding: 0 0 0.55rem;
}}
{selector} .dashboard-context-strip b {{
    color: #4d5864;
    font-weight: 600;
}}
{selector} h2 {{
    color: var(--dashboard-ink);
    font-size: 1.08rem !important;
    font-weight: 650 !important;
    letter-spacing: 0 !important;
    line-height: 1.3 !important;
    margin: 1.2rem 0 0.45rem !important;
}}
{selector} h3,
{selector} h4,
{selector} h5 {{
    color: var(--dashboard-ink);
    letter-spacing: 0 !important;
}}
{selector} [data-testid="stForm"] {{
    border: 0 !important;
    border-radius: 0 !important;
    padding: 0 !important;
}}
{selector} [data-testid="stMetric"] {{
    background: transparent !important;
    border: 0 !important;
    border-top: 2px solid var(--dashboard-accent) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    min-height: 5rem;
    padding: 0.58rem 0.1rem 0.35rem !important;
}}
{selector} [data-testid="stMetricLabel"] p {{
    color: var(--dashboard-muted) !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
}}
{selector} [data-testid="stMetricValue"] {{
    color: var(--dashboard-ink) !important;
    font-size: 1.35rem !important;
    font-weight: 650 !important;
}}
{selector} div[data-testid="stExpander"] details {{
    background: transparent !important;
    border: 0 !important;
    border-bottom: 1px solid #e2e5e9 !important;
    border-radius: 0 !important;
    box-shadow: none !important;
}}
{selector} div[data-testid="stExpander"] summary {{
    min-height: 2.35rem !important;
    padding: 0.42rem 0 !important;
}}
{selector} div[data-testid="stExpander"] summary p {{
    color: #394450 !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
}}
{selector} [data-testid="stAlert"] {{
    border-radius: 4px !important;
    box-shadow: none !important;
}}
{selector} [data-testid="stTabs"] [role="tablist"] {{
    gap: 1.2rem !important;
    margin-bottom: 0.35rem;
}}
{selector} [data-testid="stTabs"] [role="tab"] {{
    min-height: 2.3rem !important;
}}
{selector} [data-testid="stTabs"] [role="tab"] p {{
    font-size: 0.86rem !important;
}}
{selector} [data-testid="stVegaLiteChart"],
{selector} [data-testid="stPlotlyChart"] {{
    max-width: 100%;
    min-width: 0;
}}
{selector} [data-testid="stElementToolbar"] {{
    opacity: 0;
    transition: opacity 120ms ease;
}}
{selector} [data-testid="stVegaLiteChart"]:hover [data-testid="stElementToolbar"],
{selector} [data-testid="stPlotlyChart"]:hover [data-testid="stElementToolbar"] {{
    opacity: 1;
}}
{selector} .industry-kpi,
{selector} .fidc-model-kpi-card,
{selector} .about-card,
{selector} .dev-hours-card {{
    background: transparent !important;
    border: 0 !important;
    border-radius: 0 !important;
    box-shadow: none !important;
}}
{selector} .industry-kpi,
{selector} .fidc-model-kpi-card {{
    border-top: 2px solid var(--dashboard-accent) !important;
    padding: 0.65rem 0.15rem 0.35rem !important;
}}
{selector} [data-testid="stDataFrame"],
{selector} [data-testid="stDataEditor"] {{
    max-width: 100%;
    min-width: 0;
}}
@media (max-width: 520px) {{
    {selector} .dashboard-page-header h1 {{ font-size: 1.42rem; }}
    {selector} .dashboard-page-subtitle {{ font-size: 0.84rem; }}
    {selector} .dashboard-context-strip {{ align-items: flex-start; flex-direction: column; gap: 0.12rem; }}
    {selector} div[data-testid="stHorizontalBlock"] {{
        flex-direction: column !important;
        gap: 0.65rem !important;
    }}
    {selector} div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
        flex: 1 1 100% !important;
        min-width: 0 !important;
        width: 100% !important;
    }}
    {selector} .industry-kpi-grid,
    {selector} .fidc-model-kpi-grid,
    {selector} .about-grid,
    {selector} .dev-hours-grid {{
        grid-template-columns: minmax(0, 1fr) !important;
    }}
    {selector} [data-testid="stTabs"] [role="tablist"] {{ gap: 0.85rem !important; }}
    {selector} [data-testid="stTabs"] [role="tab"] p {{ font-size: 0.8rem !important; }}
}}
</style>
"""


@contextmanager
def dashboard_page(page_key: str) -> Iterator[None]:
    enable_chart_theme()
    container_key = f"fidc_page_{_safe_scope(page_key)}"
    with st.container(key=container_key):
        st.markdown(scoped_page_css(container_key), unsafe_allow_html=True)
        yield
