from __future__ import annotations

import pandas as pd
import altair as alt

from services.mercado_livre_dashboard import PT_MONTH_ABBR


SENIOR_COLOR = "#1f77b4"
SUB_MEZZ_COLOR = "#8ecae6"
NPL_COLOR = "#d1495b"
COVERAGE_COLOR = "#1b998b"


def pl_subordination_chart(monthly_df: pd.DataFrame, *, title: str = "Evolução de PL e Subordinação") -> alt.Chart:
    if monthly_df.empty:
        return _empty_chart(title=title)
    df = monthly_df.sort_values("competencia_dt").copy()
    scale_divisor, scale_label = _money_scale(
        pd.concat(
            [
                pd.to_numeric(df.get("pl_senior"), errors="coerce"),
                pd.to_numeric(df.get("pl_subordinada_mezz_ex360"), errors="coerce"),
            ],
            ignore_index=True,
        )
    )
    bar_rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        bar_rows.append(
            {
                "competencia": _format_competencia(row.get("competencia_dt"), row.get("competencia")),
                "ordem": 1,
                "serie": "Sênior",
                "valor": _num(row.get("pl_senior")),
                "valor_scaled": _divide(row.get("pl_senior"), scale_divisor),
                "valor_fmt": _format_money(row.get("pl_senior"), scale_divisor=scale_divisor, scale_label=scale_label),
            }
        )
        bar_rows.append(
            {
                "competencia": _format_competencia(row.get("competencia_dt"), row.get("competencia")),
                "ordem": 2,
                "serie": "Subordinada + Mez ex-360",
                "valor": _num(row.get("pl_subordinada_mezz_ex360")),
                "valor_scaled": _divide(row.get("pl_subordinada_mezz_ex360"), scale_divisor),
                "valor_fmt": _format_money(row.get("pl_subordinada_mezz_ex360"), scale_divisor=scale_divisor, scale_label=scale_label),
            }
        )
    bar_df = pd.DataFrame(bar_rows)
    line_df = pd.DataFrame(
        {
            "competencia": [_format_competencia(row.get("competencia_dt"), row.get("competencia")) for _, row in df.iterrows()],
            "serie": "% Subordinação Total ex-360",
            "valor": pd.to_numeric(df.get("subordinacao_total_ex360_pct"), errors="coerce"),
        }
    )
    line_df["valor_fmt"] = line_df["valor"].map(_format_percent)
    x_sort = bar_df["competencia"].drop_duplicates().tolist()
    x = alt.X("competencia:N", title="Competência", sort=x_sort)
    bars = (
        alt.Chart(bar_df)
        .mark_bar()
        .encode(
            x=x,
            y=alt.Y(
                "valor_scaled:Q",
                title=scale_label,
                stack="zero",
                axis=alt.Axis(labelPadding=8, titlePadding=12),
            ),
            color=alt.Color(
                "serie:N",
                title="PL",
                scale=alt.Scale(domain=["Sênior", "Subordinada + Mez ex-360"], range=[SENIOR_COLOR, SUB_MEZZ_COLOR]),
            ),
            order=alt.Order("ordem:Q"),
            tooltip=[
                alt.Tooltip("competencia:N", title="Competência"),
                alt.Tooltip("serie:N", title="Série"),
                alt.Tooltip("valor_fmt:N", title="Valor"),
            ],
        )
    )
    line = (
        alt.Chart(line_df)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=52), strokeWidth=2.8, color=COVERAGE_COLOR)
        .encode(
            x=x,
            y=alt.Y(
                "valor:Q",
                title="% Subordinação Total ex-360",
                axis=alt.Axis(orient="right", grid=False, labelColor=COVERAGE_COLOR, titleColor=COVERAGE_COLOR),
            ),
            tooltip=[
                alt.Tooltip("competencia:N", title="Competência"),
                alt.Tooltip("valor_fmt:N", title="% Subordinação Total ex-360"),
            ],
        )
    )
    return _style_chart(alt.layer(bars, line).resolve_scale(y="independent").properties(title=title, height=360))


def npl_coverage_chart(monthly_df: pd.DataFrame, *, title: str = "NPL e Cobertura Ex-Vencidos > 360d") -> alt.Chart:
    if monthly_df.empty:
        return _empty_chart(title=title)
    df = monthly_df.sort_values("competencia_dt").copy()
    x_values = [_format_competencia(row.get("competencia_dt"), row.get("competencia")) for _, row in df.iterrows()]
    chart_df = pd.DataFrame(
        {
            "competencia": x_values,
            "npl_pct": pd.to_numeric(df.get("npl_over90_ex360_pct"), errors="coerce"),
            "coverage_pct": pd.to_numeric(df.get("pdd_npl_over90_ex360_pct"), errors="coerce"),
        }
    )
    chart_df["npl_fmt"] = chart_df["npl_pct"].map(_format_percent)
    chart_df["coverage_fmt"] = chart_df["coverage_pct"].map(_format_percent)
    x_sort = chart_df["competencia"].drop_duplicates().tolist()
    x = alt.X("competencia:N", title="Competência", sort=x_sort)
    npl_line = (
        alt.Chart(chart_df)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=52), strokeWidth=2.8, color=NPL_COLOR)
        .encode(
            x=x,
            y=alt.Y(
                "npl_pct:Q",
                title="NPL Over 90d Ex 360 / Carteira Ex 360",
                axis=alt.Axis(labelColor=NPL_COLOR, titleColor=NPL_COLOR),
            ),
            tooltip=[alt.Tooltip("competencia:N", title="Competência"), alt.Tooltip("npl_fmt:N", title="NPL Over 90d Ex 360")],
        )
    )
    coverage_line = (
        alt.Chart(chart_df)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=52), strokeWidth=2.8, color=COVERAGE_COLOR)
        .encode(
            x=x,
            y=alt.Y(
                "coverage_pct:Q",
                title="PDD / NPL Over 90d Ex 360",
                axis=alt.Axis(orient="right", grid=False, labelColor=COVERAGE_COLOR, titleColor=COVERAGE_COLOR),
            ),
            tooltip=[alt.Tooltip("competencia:N", title="Competência"), alt.Tooltip("coverage_fmt:N", title="PDD / NPL Over 90d Ex 360")],
        )
    )
    return _style_chart(alt.layer(npl_line, coverage_line).resolve_scale(y="independent").properties(title=title, height=340))


def _empty_chart(*, title: str) -> alt.Chart:
    return _style_chart(
        alt.Chart(pd.DataFrame({"x": [0], "text": ["Sem dados"]}))
        .mark_text(color="#6f7a87", fontSize=13)
        .encode(text="text:N")
        .properties(title=title, height=260)
    )


def _style_chart(chart: alt.Chart) -> alt.Chart:
    return (
        chart.configure_axis(
            labelColor="#5f6b7a",
            titleColor="#5f6b7a",
            gridColor="#eef2f6",
            domainColor="#e9ecef",
        )
        .configure_title(
            color="#223247",
            font="IBM Plex Sans",
            fontSize=14,
            fontWeight=500,
            anchor="start",
        )
        .configure_view(stroke=None)
        .configure_legend(labelColor="#5f6b7a", titleColor="#5f6b7a", orient="bottom")
    )


def _money_scale(values: pd.Series) -> tuple[float, str]:
    max_value = pd.to_numeric(values, errors="coerce").abs().max()
    if pd.isna(max_value):
        max_value = 0.0
    if max_value >= 1_000_000_000:
        return 1_000_000_000.0, "R$ bi"
    if max_value >= 1_000_000:
        return 1_000_000.0, "R$ mm"
    if max_value >= 1_000:
        return 1_000.0, "R$ mil"
    return 1.0, "R$"


def _format_competencia(competencia_dt: object, fallback: object) -> str:
    ts = pd.to_datetime(competencia_dt, errors="coerce")
    if pd.notna(ts):
        return f"{PT_MONTH_ABBR[int(ts.month)]}/{str(int(ts.year))[-2:]}"
    return str(fallback or "")


def _num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return None
    return float(parsed)


def _divide(value: object, divisor: float) -> float | None:
    numeric = _num(value)
    if numeric is None:
        return None
    return numeric / divisor


def _format_decimal(value: object, decimals: int = 2) -> str:
    numeric = _num(value)
    if numeric is None:
        return "N/D"
    formatted = f"{numeric:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _format_percent(value: object) -> str:
    return f"{_format_decimal(value, 2)}%"


def _format_money(value: object, *, scale_divisor: float, scale_label: str) -> str:
    numeric = _num(value)
    if numeric is None:
        return "N/D"
    if scale_label == "R$":
        return f"R$ {_format_decimal(numeric, 2)}"
    return f"{scale_label} {_format_decimal(numeric / scale_divisor, 2)}"
