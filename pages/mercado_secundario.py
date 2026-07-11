"""Página Streamlit: mercado secundário de cotas de FIDC (ANBIMA Feed).

Lê os parquet curados gerados por secondary.backfill + secondary.aggregate:
    data/curated/mensal_fidc.parquet       (agregado mensal)
    data/curated/negociacoes_fidc.parquet  (nível negociação, p/ boxplot)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_BASE_DIR = Path(__file__).resolve().parent.parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

from secondary import CURATED_MENSAL, CURATED_NEGOCIACOES  # noqa: E402

st.set_page_config(page_title="Mercado Secundário FIDC", page_icon="📊", layout="wide")

# Paleta validada (dataviz): série azul, tinta e grades neutras, superfície branca.
_SERIE = "#2a78d6"
_INK = "#2f3a48"
_MUTED = "#898781"
_GRID = "#e1e0d9"
_FONT = "IBM Plex Sans, sans-serif"

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');
    html, body, .stApp, div, p, label, h1, h2, h3, h4 { font-family: 'IBM Plex Sans', sans-serif !important; }
    .stApp { background: #ffffff; color: #2f3a48; }
    .sec-kicker { color: #ff5a00; font-size: 0.76rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
    .sec-title { color: #12171d; font-size: 2.2rem; font-weight: 300; letter-spacing: -0.03em; margin: 0; }
    .sec-sub { color: #6f7a87; font-size: 0.95rem; margin-top: 0.35rem; }
    </style>
    <div class="sec-kicker">tomaconta FIDCs</div>
    <h1 class="sec-title">Mercado secundário de cotas de FIDC</h1>
    <div class="sec-sub">Volume operado, preço e taxa (REUNE/ANBIMA), com ágio/deságio
    implícito frente ao PU indicativo — agregação mensal, 2023–2026.</div>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="Carregando parquet curado...")
def _carregar() -> tuple[pd.DataFrame, pd.DataFrame]:
    mensal = pd.read_parquet(CURATED_MENSAL)
    try:
        trades = pd.read_parquet(CURATED_NEGOCIACOES)
    except (FileNotFoundError, OSError):
        trades = pd.DataFrame()
    return mensal, trades


def _fmt_brl_compacto(valor: float) -> str:
    if pd.isna(valor):
        return "—"
    for corte, sufixo in ((1e9, "bi"), (1e6, "mi"), (1e3, "mil")):
        if abs(valor) >= corte:
            return f"R$ {valor / corte:,.1f} {sufixo}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {valor:,.0f}".replace(",", ".")


def _layout_base(fig: go.Figure, altura: int = 380) -> go.Figure:
    fig.update_layout(
        height=altura,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(family=_FONT, color=_INK, size=13),
        showlegend=False,
        hoverlabel=dict(bgcolor="#ffffff", font=dict(family=_FONT, color=_INK)),
    )
    fig.update_xaxes(showgrid=False, linecolor=_GRID, tickfont=dict(color=_MUTED))
    fig.update_yaxes(gridcolor=_GRID, zerolinecolor=_GRID, linecolor=_GRID,
                     tickfont=dict(color=_MUTED))
    return fig


_CONFIG = {"displayModeBar": False}

if not CURATED_MENSAL.exists():
    st.info(
        "Ainda não há dado curado. Gere os parquet primeiro:\n\n"
        "```\n"
        "python -m secondary.backfill --mes 2026-06   # teste com um mês\n"
        "python -m secondary.aggregate\n"
        "```\n"
        "Depois recarregue esta página. Detalhes (credenciais ANBIMA, backfill "
        "completo 2023–2026) no README, seção 'Mercado Secundário'."
    )
    st.stop()

mensal, trades = _carregar()
if mensal.empty:
    st.warning(
        "O parquet curado existe, mas está vazio — nenhuma negociação de FIDC "
        "foi capturada no período baixado. Liquidez baixa é normal; amplie a "
        "janela do backfill e rode `python -m secondary.aggregate` de novo."
    )
    st.stop()

mensal["ano"] = mensal["mes"].str.slice(0, 4)
anos = sorted(mensal["ano"].unique())
sel_anos = st.multiselect("Anos", options=anos, default=anos)
if sel_anos:
    mensal = mensal[mensal["ano"].isin(sel_anos)]
    if not trades.empty:
        trades = trades[trades["mes"].str.slice(0, 4).isin(sel_anos)]

# ---------------------------------------------------------------- KPIs
volume_total = float(mensal["volume"].sum())
n_operacoes = int(mensal["n_operacoes"].sum())
n_fidcs = int(mensal["cnpj"].fillna(mensal["emissor"]).nunique())
k1, k2, k3 = st.columns(3)
k1.metric("Volume operado", _fmt_brl_compacto(volume_total))
k2.metric("Nº de operações", f"{n_operacoes:,}".replace(",", "."))
k3.metric("FIDCs operados", f"{n_fidcs}")

st.divider()

por_mes = (
    mensal.groupby("mes", as_index=True)
    .agg(volume=("volume", "sum"), n_operacoes=("n_operacoes", "sum"))
    .sort_index()
)
# Taxa média mensal ponderada pelo volume (só grupos com taxa disponível).
com_taxa = mensal[mensal["taxa_media"].notna() & (mensal["volume"] > 0)].copy()
com_taxa["_vt"] = com_taxa["taxa_media"] * com_taxa["volume"]
taxa_mes = (
    com_taxa.groupby("mes").agg(vt=("_vt", "sum"), v=("volume", "sum")).sort_index()
)
taxa_mes["taxa"] = taxa_mes["vt"] / taxa_mes["v"]

c1, c2 = st.columns(2)
with c1:
    st.subheader("Volume operado por mês")
    fig = go.Figure(
        go.Bar(
            x=por_mes.index,
            y=por_mes["volume"],
            marker=dict(color=_SERIE, cornerradius=4),
            customdata=[_fmt_brl_compacto(v) for v in por_mes["volume"]],
            hovertemplate="<b>%{x}</b><br>Volume: %{customdata}<extra></extra>",
        )
    )
    fig.update_yaxes(title_text="Volume (R$)")
    st.plotly_chart(_layout_base(fig), config=_CONFIG, use_container_width=True)

with c2:
    st.subheader("Taxa média negociada por mês")
    fig = go.Figure(
        go.Scatter(
            x=taxa_mes.index,
            y=taxa_mes["taxa"],
            mode="lines+markers",
            line=dict(color=_SERIE, width=2),
            marker=dict(size=8, color=_SERIE),
            hovertemplate="<b>%{x}</b><br>Taxa média: %{y:.2f}%<extra></extra>",
        )
    )
    fig.update_yaxes(title_text="Taxa (% a.a., ponderada por volume)")
    st.plotly_chart(_layout_base(fig), config=_CONFIG, use_container_width=True)

c3, c4 = st.columns(2)
with c3:
    st.subheader("Top 15 FIDCs por volume")
    top = (
        mensal.groupby("emissor", dropna=False)["volume"].sum()
        .sort_values(ascending=False)
        .head(15)
        .iloc[::-1]
    )
    fig = go.Figure(
        go.Bar(
            x=top.values,
            y=[str(nome)[:48] for nome in top.index],
            orientation="h",
            marker=dict(color=_SERIE, cornerradius=4),
            customdata=[_fmt_brl_compacto(v) for v in top.values],
            hovertemplate="<b>%{y}</b><br>Volume: %{customdata}<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Volume (R$)")
    st.plotly_chart(_layout_base(fig, altura=460), config=_CONFIG, use_container_width=True)

with c4:
    st.subheader("Ágio (+) / deságio (–) implícito por mês")
    st.caption("PU negociado (REUNE) vs. PU indicativo ANBIMA do mesmo ISIN e dia.")
    box = trades.dropna(subset=["agio_desagio_impl_pct"]) if not trades.empty else trades
    if box is None or box.empty:
        st.info(
            "Sem negociações casadas com PU indicativo no período — o boxplot "
            "exige o parquet de nível negociação (secondary.aggregate)."
        )
    else:
        fig = go.Figure(
            go.Box(
                x=box["mes"],
                y=box["agio_desagio_impl_pct"],
                marker=dict(color=_SERIE, size=4),
                line=dict(color=_SERIE, width=2),
                fillcolor="rgba(42, 120, 214, 0.25)",
                boxpoints="outliers",
                hovertemplate="<b>%{x}</b><br>Ágio/deságio: %{y:.2f}%<extra></extra>",
            )
        )
        fig.add_hline(y=0, line_color=_MUTED, line_dash="dot", line_width=1)
        fig.update_yaxes(title_text="Ágio/deságio implícito (%)")
        fig.update_xaxes(categoryorder="category ascending")
        st.plotly_chart(_layout_base(fig, altura=460), config=_CONFIG, use_container_width=True)

st.divider()
st.subheader("Detalhe mensal por FIDC")
detalhe = mensal.loc[
    :, ["mes", "emissor", "cnpj", "volume", "n_operacoes", "taxa_media", "agio_desagio_medio"]
].sort_values(["mes", "volume"], ascending=[False, False])
st.dataframe(
    detalhe,
    use_container_width=True,
    hide_index=True,
    column_config={
        "mes": st.column_config.TextColumn("Mês"),
        "emissor": st.column_config.TextColumn("Emissor"),
        "cnpj": st.column_config.TextColumn("CNPJ"),
        "volume": st.column_config.NumberColumn("Volume (R$)", format="localized"),
        "n_operacoes": st.column_config.NumberColumn("Operações"),
        "taxa_media": st.column_config.NumberColumn("Taxa média (%)", format="%.2f"),
        "agio_desagio_medio": st.column_config.NumberColumn("Ágio/deságio médio (%)", format="%.2f"),
    },
)
st.caption(
    "Fonte: ANBIMA Feed — Preços & Índices (REUNE + preços indicativos de FIDC). "
    "Dados anonimizados: não há comprador/vendedor, apenas o emissor da cota."
)
