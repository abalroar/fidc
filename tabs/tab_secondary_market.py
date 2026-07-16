from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

try:
    import plotly.graph_objects as go
except ModuleNotFoundError:  # pragma: no cover - defensive deploy fallback
    go = None

from secondary import CURATED_MENSAL, CURATED_NEGOCIACOES
from services.dashboard_ui import (
    PLOTLY_CHART_CONFIG,
    diagnostics_enabled,
    render_context_strip,
    render_page_header,
    style_plotly_figure,
)


_SERIES = "#2a78d6"
_MUTED = "#7a838d"
SECONDARY_CHART_KEYS = (
    "secondary_market_volume_monthly",
    "secondary_market_rate_monthly",
    "secondary_market_top_funds",
    "secondary_market_premium_discount",
)
_MONTHLY_REQUIRED = {
    "mes",
    "emissor",
    "cnpj",
    "volume",
    "n_operacoes",
    "taxa_media",
    "agio_desagio_medio",
}


@st.cache_data(show_spinner=False)
def _load_secondary_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    monthly = pd.read_parquet(CURATED_MENSAL)
    try:
        trades = pd.read_parquet(CURATED_NEGOCIACOES)
    except (FileNotFoundError, OSError):
        trades = pd.DataFrame()
    return monthly, trades


def _format_brl_compact(value: float) -> str:
    if pd.isna(value):
        return "-"
    for threshold, suffix in ((1e9, "bi"), (1e6, "mi"), (1e3, "mil")):
        if abs(value) >= threshold:
            return f"R$ {value / threshold:,.1f} {suffix}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {value:,.0f}".replace(",", ".")


def _layout_base(figure: object, *, height: int = 380) -> object:
    styled = style_plotly_figure(figure, height=height, showlegend=False)
    styled.update_xaxes(nticks=8)
    return styled


def _render_empty_state(message: str) -> None:
    st.info(message)


def render_tab_secondary_market() -> None:
    render_page_header(
        "Mercado secundário",
        "Volume, preço e taxa das cotas de FIDC negociadas no REUNE/ANBIMA.",
    )
    if go is None:
        st.error("Os gráficos do mercado secundário estão indisponíveis neste ambiente.")
        return
    if not CURATED_MENSAL.exists():
        _render_empty_state("A base curada do mercado secundário ainda não está disponível.")
        return

    try:
        monthly, trades = _load_secondary_data()
    except Exception as exc:  # noqa: BLE001
        st.error("Não foi possível carregar a base do mercado secundário.")
        if diagnostics_enabled():
            st.exception(exc)
        return

    missing_columns = sorted(_MONTHLY_REQUIRED.difference(monthly.columns))
    if missing_columns:
        st.error("A base do mercado secundário está incompleta para esta visualização.")
        if diagnostics_enabled():
            st.caption("Colunas ausentes: " + ", ".join(missing_columns))
        return
    if monthly.empty:
        _render_empty_state("Nenhuma negociação de FIDC foi encontrada na janela disponível.")
        return

    monthly = monthly.copy()
    monthly["ano"] = monthly["mes"].astype(str).str.slice(0, 4)
    years = sorted(value for value in monthly["ano"].dropna().unique() if value)
    selected_years = st.multiselect(
        "Anos",
        options=years,
        default=years,
        key="secondary_market_years",
    )
    if not selected_years:
        _render_empty_state("Selecione ao menos um ano para exibir o mercado secundário.")
        return

    monthly = monthly[monthly["ano"].isin(selected_years)].copy()
    if not trades.empty and "mes" in trades.columns:
        trades = trades[trades["mes"].astype(str).str.slice(0, 4).isin(selected_years)].copy()
    if monthly.empty:
        _render_empty_state("Não há negociações para os anos selecionados.")
        return

    volume_total = float(pd.to_numeric(monthly["volume"], errors="coerce").fillna(0).sum())
    operations = int(pd.to_numeric(monthly["n_operacoes"], errors="coerce").fillna(0).sum())
    funds = int(monthly["cnpj"].fillna(monthly["emissor"]).nunique())
    base_until = str(monthly["mes"].max())
    render_context_strip(
        source="ANBIMA Feed (REUNE e preços indicativos)",
        base_until=base_until,
        coverage=f"{funds} FIDCs | {operations:,} negócios".replace(",", "."),
    )

    metric_columns = st.columns(3)
    metric_columns[0].metric("Volume negociado", _format_brl_compact(volume_total))
    metric_columns[1].metric("Negócios", f"{operations:,}".replace(",", "."))
    metric_columns[2].metric("FIDCs negociados", str(funds))

    by_month = (
        monthly.groupby("mes", as_index=True)
        .agg(volume=("volume", "sum"), n_operacoes=("n_operacoes", "sum"))
        .sort_index()
    )
    with_rate = monthly[monthly["taxa_media"].notna() & (monthly["volume"] > 0)].copy()
    with_rate["_volume_rate"] = with_rate["taxa_media"] * with_rate["volume"]
    rate_by_month = with_rate.groupby("mes").agg(vt=("_volume_rate", "sum"), volume=("volume", "sum")).sort_index()
    rate_by_month["taxa"] = rate_by_month["vt"] / rate_by_month["volume"]

    left, right = st.columns(2)
    with left:
        st.markdown("<h2>Volume mensal</h2>", unsafe_allow_html=True)
        figure = go.Figure(
            go.Bar(
                x=by_month.index,
                y=by_month["volume"],
                marker={"color": _SERIES, "cornerradius": 3},
                customdata=[_format_brl_compact(value) for value in by_month["volume"]],
                hovertemplate="<b>%{x}</b><br>Volume: %{customdata}<extra></extra>",
            )
        )
        figure.update_yaxes(title_text="Volume (R$)")
        st.plotly_chart(
            _layout_base(figure),
            config=PLOTLY_CHART_CONFIG,
            width="stretch",
            key=SECONDARY_CHART_KEYS[0],
        )

    with right:
        st.markdown("<h2>Taxa média mensal</h2>", unsafe_allow_html=True)
        figure = go.Figure(
            go.Scatter(
                x=rate_by_month.index,
                y=rate_by_month["taxa"],
                mode="lines+markers",
                line={"color": _SERIES, "width": 2},
                marker={"size": 6, "color": _SERIES},
                hovertemplate="<b>%{x}</b><br>Taxa média: %{y:.2f}%<extra></extra>",
            )
        )
        figure.update_yaxes(title_text="Taxa (% a.a., ponderada por volume)")
        st.plotly_chart(
            _layout_base(figure),
            config=PLOTLY_CHART_CONFIG,
            width="stretch",
            key=SECONDARY_CHART_KEYS[1],
        )

    left, right = st.columns(2)
    with left:
        st.markdown("<h2>Maiores volumes</h2>", unsafe_allow_html=True)
        top = monthly.groupby("emissor", dropna=False)["volume"].sum().sort_values(ascending=False).head(15).iloc[::-1]
        figure = go.Figure(
            go.Bar(
                x=top.values,
                y=[str(name)[:48] for name in top.index],
                orientation="h",
                marker={"color": _SERIES, "cornerradius": 3},
                customdata=[_format_brl_compact(value) for value in top.values],
                hovertemplate="<b>%{y}</b><br>Volume: %{customdata}<extra></extra>",
            )
        )
        figure.update_xaxes(title_text="Volume (R$)")
        st.plotly_chart(
            _layout_base(figure, height=460),
            config=PLOTLY_CHART_CONFIG,
            width="stretch",
            key=SECONDARY_CHART_KEYS[2],
        )

    with right:
        st.markdown("<h2>Ágio e deságio implícitos</h2>", unsafe_allow_html=True)
        box = (
            trades.dropna(subset=["agio_desagio_impl_pct"])
            if not trades.empty and "agio_desagio_impl_pct" in trades.columns
            else pd.DataFrame()
        )
        if box.empty:
            _render_empty_state("Sem negócios conciliados com PU indicativo para o período.")
        else:
            figure = go.Figure(
                go.Box(
                    x=box["mes"],
                    y=box["agio_desagio_impl_pct"],
                    marker={"color": _SERIES, "size": 4},
                    line={"color": _SERIES, "width": 2},
                    fillcolor="rgba(42, 120, 214, 0.18)",
                    boxpoints="outliers",
                    hovertemplate="<b>%{x}</b><br>Ágio/deságio: %{y:.2f}%<extra></extra>",
                )
            )
            figure.add_hline(y=0, line_color=_MUTED, line_dash="dot", line_width=1)
            figure.update_yaxes(title_text="Ágio/deságio implícito (%)")
            figure.update_xaxes(categoryorder="category ascending")
            st.plotly_chart(
                _layout_base(figure, height=460),
                config=PLOTLY_CHART_CONFIG,
                width="stretch",
                key=SECONDARY_CHART_KEYS[3],
            )

    with st.expander("Dados e exportações", expanded=False):
        detail = monthly.loc[
            :, ["mes", "emissor", "cnpj", "volume", "n_operacoes", "taxa_media", "agio_desagio_medio"]
        ].sort_values(["mes", "volume"], ascending=[False, False])
        st.dataframe(
            detail,
            width="stretch",
            hide_index=True,
            column_config={
                "mes": st.column_config.TextColumn("Mês"),
                "emissor": st.column_config.TextColumn("Emissor"),
                "cnpj": st.column_config.TextColumn("CNPJ"),
                "volume": st.column_config.NumberColumn("Volume (R$)", format="localized"),
                "n_operacoes": st.column_config.NumberColumn("Negócios"),
                "taxa_media": st.column_config.NumberColumn("Taxa média (%)", format="%.2f"),
                "agio_desagio_medio": st.column_config.NumberColumn("Ágio/deságio médio (%)", format="%.2f"),
            },
        )

    with st.expander("Sobre a base", expanded=False):
        st.markdown(
            "Fonte: **ANBIMA Feed - Preços & Índices** (REUNE e preços indicativos de FIDC). "
            "O ágio/deságio compara o PU negociado ao PU indicativo do mesmo ISIN e dia. "
            "A base é anonimizada e não identifica comprador ou vendedor."
        )
        if diagnostics_enabled():
            st.caption(f"Mensal: {Path(CURATED_MENSAL)} | Negócios: {Path(CURATED_NEGOCIACOES)}")
            st.caption(f"Linhas mensais: {len(monthly):,} | Linhas negócio a negócio: {len(trades):,}")
