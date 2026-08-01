"""Plotly figures for the structural-risk deck.

Design rules, in the order they win:

1. **The floor is a line, not a color.**  Anything that answers "how far from
   breaching" draws the threshold explicitly, so the reader measures distance
   instead of trusting a legend.
2. **Size is net assets, always.**  A committee reads risk in money; an
   unweighted dot makes a R$ 5 mi position look like a R$ 5 bi one.
3. **Saturated color only in the tails.**  "In line with the market" is the
   common case and is drawn grey, so the eye lands on the exceptions.
4. **A gap is drawn as a gap.**  Missing data gets a hollow marker and stays on
   the chart; dropping it would shrink the denominator silently.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from services.structural_risk import (
    BAND_ABOVE_MARKET,
    BAND_BELOW_MARKET,
    BAND_BREACH,
    BAND_HIGH_CUSHION,
    BAND_IN_LINE,
    BAND_NO_BENCHMARK,
    BAND_THIN,
    BAND_UNMEASURED,
)


#: Vermelho e laranja só para o que exige ação; cinza para o caso comum.
BAND_COLORS: dict[str, str] = {
    BAND_BREACH: "#c0392b",
    BAND_THIN: "#e67e22",
    BAND_BELOW_MARKET: "#d4a03c",
    BAND_IN_LINE: "#8c9196",
    BAND_ABOVE_MARKET: "#2f6fa8",
    BAND_HIGH_CUSHION: "#5b4b8a",
    BAND_NO_BENCHMARK: "#b9bcc0",
    BAND_UNMEASURED: "#d8dade",
}

_GRID = "#e6e8ea"
_AXIS = "#2f3a48"


def _layout(fig: go.Figure, title: str, subtitle: str = "") -> go.Figure:
    fig.update_layout(
        title={
            "text": f"<b>{title}</b>" + (f"<br><span style='font-size:12px;color:#5a6472'>{subtitle}</span>" if subtitle else ""),
            "x": 0,
            "xanchor": "left",
        },
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"family": "Inter, Helvetica, Arial, sans-serif", "color": _AXIS, "size": 12},
        margin={"l": 70, "r": 30, "t": 90, "b": 60},
        hovermode="closest",
    )
    fig.update_xaxes(gridcolor=_GRID, zeroline=False)
    fig.update_yaxes(gridcolor=_GRID, zeroline=False)
    return fig


def _marker_sizes(pl: pd.Series, maximum: float = 46.0, minimum: float = 7.0) -> pd.Series:
    """Area proportional to net assets, so a dot twice as wide is four times the money."""

    values = pd.to_numeric(pl, errors="coerce").fillna(0.0).clip(lower=0)
    top = float(values.max())
    if top <= 0:
        return pd.Series(minimum, index=values.index)
    return minimum + (maximum - minimum) * np.sqrt(values / top)


def chart_floor_diagonal(assets: pd.DataFrame) -> go.Figure:
    """Current subordination against the contractual floor, with the y=x line.

    The single most useful chart in the pack.  Everything on the diagonal is at
    its trigger; everything below it is in breach.  Vertical distance from the
    line is the headroom, and dot area is the money exposed to it.
    """

    frame = assets.dropna(subset=["sub_jr_min_regulamento", "sub_pl_atual"]).copy()
    fig = go.Figure()
    if frame.empty:
        return _layout(fig, "Subordinação atual × mínimo regulamentar", "sem dados de mínimo")

    limit = float(
        max(
            pd.to_numeric(frame["sub_pl_atual"], errors="coerce").max(),
            pd.to_numeric(frame["sub_jr_min_regulamento"], errors="coerce").max(),
        )
    ) * 1.12
    fig.add_trace(
        go.Scatter(
            x=[0, limit],
            y=[0, limit],
            mode="lines",
            line={"color": "#c0392b", "width": 1.5, "dash": "dash"},
            name="gatilho (y = x)",
            hoverinfo="skip",
        )
    )

    sizes = _marker_sizes(frame["pl_atual"])
    for band, group in frame.groupby("banda"):
        fig.add_trace(
            go.Scatter(
                x=group["sub_jr_min_regulamento"],
                y=group["sub_pl_atual"],
                mode="markers",
                name=str(band),
                marker={
                    "size": sizes.loc[group.index],
                    "color": BAND_COLORS.get(str(band), "#8c9196"),
                    "line": {"width": 1, "color": "white"},
                    "opacity": 0.85,
                },
                customdata=np.stack(
                    [
                        group["ativo"].astype(str),
                        group["categoria"].astype(str),
                        pd.to_numeric(group["pl_atual"], errors="coerce") / 1e6,
                        group["folga_pp"] * 100,
                        group["perda_ate_gatilho"] * 100,
                    ],
                    axis=-1,
                ),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
                    "PL R$ %{customdata[2]:.0f} mi<br>"
                    "mínimo %{x:.1%} · atual %{y:.1%}<br>"
                    "folga %{customdata[3]:.1f} pp<br>"
                    "absorve %{customdata[4]:.1f}% de perda<extra></extra>"
                ),
            )
        )
    fig.update_xaxes(title="Mínimo regulamentar de subordinação", tickformat=".0%", range=[0, limit])
    fig.update_yaxes(title="Subordinação atual (Sub/PL)", tickformat=".0%", range=[0, limit])
    return _layout(
        fig,
        "Distância do piso, ativo a ativo",
        "Área do ponto = patrimônio. Abaixo da diagonal = gatilho rompido.",
    )


def chart_dumbbell_categories(by_category: pd.DataFrame) -> go.Figure:
    """Our weighted subordination against the market median, category by category.

    The interquartile range of the peers is drawn as the grey bar behind the
    pair, so "above the median" is read together with how wide the peer
    dispersion is — a 2pp edge over a tight distribution means something a 2pp
    edge over a scattered one does not.
    """

    frame = by_category.dropna(subset=["sub_ponderada_carteira"]).copy()
    frame = frame.sort_values("sub_ponderada_carteira")
    fig = go.Figure()
    if frame.empty:
        return _layout(fig, "Carteira × mercado por categoria", "sem dados")

    for _, row in frame.iterrows():
        market = row.get("mercado_mediana")
        if pd.notna(market):
            fig.add_trace(
                go.Scatter(
                    x=[market, row["sub_ponderada_carteira"]],
                    y=[row["categoria"], row["categoria"]],
                    mode="lines",
                    line={"color": "#c9ced4", "width": 3},
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

    fig.add_trace(
        go.Scatter(
            x=frame["mercado_mediana"],
            y=frame["categoria"],
            mode="markers",
            name="mediana do mercado",
            marker={"size": 13, "color": "#8c9196", "symbol": "circle"},
            hovertemplate="mercado %{x:.1%}<extra></extra>",
        )
    )
    colors = [
        BAND_COLORS[BAND_NO_BENCHMARK] if not bool(ok) else "#ff5a00"
        for ok in frame["benchmark_confiavel"]
    ]
    fig.add_trace(
        go.Scatter(
            x=frame["sub_ponderada_carteira"],
            y=frame["categoria"],
            mode="markers",
            name="nossa carteira (ponderada por PL)",
            marker={"size": 15, "color": colors, "symbol": "diamond"},
            customdata=np.stack(
                [frame["pl_total"] / 1e6, frame["n_ativos"], frame["n_comparaveis"]],
                axis=-1,
            ),
            hovertemplate=(
                "carteira %{x:.1%}<br>PL R$ %{customdata[0]:.0f} mi<br>"
                "%{customdata[1]:.0f} ativos · %{customdata[2]:.0f} pares<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(title="Subordinação (Sub/PL)", tickformat=".0%")
    return _layout(
        fig,
        "Carteira × mercado, por categoria",
        "Losango cinza = categoria sem pares suficientes para benchmark.",
    )


def chart_loss_absorption(assets: pd.DataFrame, top: int = 25) -> go.Figure:
    """How much each asset can lose before its trigger, ordered, largest first by PL."""

    frame = assets.dropna(subset=["perda_ate_gatilho"]).copy()
    frame = frame.nlargest(min(top, len(frame)), "pl_atual").sort_values(
        "perda_ate_gatilho"
    )
    fig = go.Figure()
    if frame.empty:
        return _layout(fig, "Capacidade de absorção de perda", "sem dados de mínimo")

    fig.add_trace(
        go.Bar(
            x=frame["perda_ate_gatilho"],
            y=frame["ativo"],
            orientation="h",
            marker={"color": [BAND_COLORS.get(str(b), "#8c9196") for b in frame["banda"]]},
            customdata=np.stack(
                [
                    pd.to_numeric(frame["pl_atual"], errors="coerce") / 1e6,
                    frame["categoria"].astype(str),
                ],
                axis=-1,
            ),
            hovertemplate=(
                "<b>%{y}</b><br>%{customdata[1]}<br>PL R$ %{customdata[0]:.0f} mi<br>"
                "absorve %{x:.1%} de perda<extra></extra>"
            ),
        )
    )
    fig.add_vline(
        x=0.03, line={"color": "#e67e22", "width": 1.5, "dash": "dot"},
        annotation_text="3% — zona de atenção", annotation_position="top",
    )
    fig.update_xaxes(title="Perda absorvível antes do gatilho (% do PL)", tickformat=".0%")
    return _layout(
        fig,
        f"Capacidade de absorção de perda — {len(frame)} maiores por patrimônio",
        "(Sub/PL − mínimo) ÷ (1 − mínimo). Não é a diferença aritmética.",
    )


def chart_size_versus_headroom(assets: pd.DataFrame) -> go.Figure:
    """Net assets against headroom — the quadrant where large and thin meet.

    Answers "where does the risk actually live" in one look: the bottom-right
    corner is big money on a thin cushion, and nothing else on the page shows it.
    """

    frame = assets.dropna(subset=["perda_ate_gatilho"]).copy()
    fig = go.Figure()
    if frame.empty:
        return _layout(fig, "Porte × folga", "sem dados de mínimo")

    pl = pd.to_numeric(frame["pl_atual"], errors="coerce")
    for band, group in frame.groupby("banda"):
        fig.add_trace(
            go.Scatter(
                x=pd.to_numeric(group["pl_atual"], errors="coerce") / 1e6,
                y=group["perda_ate_gatilho"],
                mode="markers",
                name=str(band),
                marker={
                    "size": 12,
                    "color": BAND_COLORS.get(str(band), "#8c9196"),
                    "line": {"width": 1, "color": "white"},
                },
                text=group["ativo"].astype(str),
                hovertemplate="<b>%{text}</b><br>PL R$ %{x:.0f} mi<br>absorve %{y:.1%}<extra></extra>",
            )
        )
    fig.add_hline(y=0.03, line={"color": "#e67e22", "width": 1.5, "dash": "dot"})
    median_pl = float(pl.median() / 1e6) if pl.notna().any() else 0.0
    fig.add_vline(x=median_pl, line={"color": _GRID, "width": 1.5})
    fig.update_xaxes(title="Patrimônio (R$ mi)", type="log")
    fig.update_yaxes(title="Perda absorvível antes do gatilho", tickformat=".0%")
    return _layout(
        fig,
        "Onde o risco mora: porte × folga",
        "Quadrante inferior direito = posição grande com colchão fino.",
    )


def chart_coverage(coverage: pd.DataFrame) -> go.Figure:
    """Share of the book covered by each field — the denominator of everything else."""

    frame = coverage.sort_values("cobertura_pl")
    fig = go.Figure(
        go.Bar(
            x=frame["cobertura_pl"],
            y=frame["campo"],
            orientation="h",
            marker={
                "color": [
                    "#c0392b" if value < 0.5 else "#e67e22" if value < 0.8 else "#8c9196"
                    for value in frame["cobertura_pl"]
                ]
            },
            customdata=np.stack(
                [frame["ativos_com_dado"], frame["ativos_total"]], axis=-1
            ),
            hovertemplate=(
                "%{y}<br>%{x:.0%} do patrimônio<br>"
                "%{customdata[0]:.0f} de %{customdata[1]:.0f} ativos<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(title="Cobertura, medida em patrimônio", tickformat=".0%", range=[0, 1])
    return _layout(
        fig,
        "Cobertura do dado",
        "Medida em patrimônio, não em contagem: faltar no maior ativo não é o mesmo que faltar no menor.",
    )


def chart_direction(history: pd.DataFrame) -> go.Figure:
    """Level plus direction: where each category sits and which way it moved.

    Two dates only, on purpose.  A committee needs "onde está e para onde foi",
    and a full time series buries that in ink.
    """

    frame = history.dropna(subset=["sub_inicio", "sub_fim"]).copy()
    fig = go.Figure()
    if frame.empty:
        return _layout(fig, "Direção da proteção", "sem série temporal")

    frame = frame.sort_values("sub_fim")
    for _, row in frame.iterrows():
        rising = row["sub_fim"] >= row["sub_inicio"]
        fig.add_trace(
            go.Scatter(
                x=[row["sub_inicio"], row["sub_fim"]],
                y=[row["categoria"], row["categoria"]],
                mode="lines+markers",
                line={"color": "#2f6fa8" if rising else "#c0392b", "width": 3},
                marker={"size": [8, 15], "symbol": ["circle", "arrow-right"]},
                showlegend=False,
                hovertemplate="%{x:.1%}<extra></extra>",
            )
        )
    fig.update_xaxes(title="Subordinação ponderada (Sub/PL)", tickformat=".0%")
    return _layout(
        fig,
        "Direção da proteção por categoria",
        "Azul = colchão engrossando; vermelho = afinando.",
    )
