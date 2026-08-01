"""Structural risk of a securitization book, measured against its market.

Two questions drive everything here:

1. How protected is each asset, and how does that compare to its peers?
2. What logic built this book — by category, by size, by cushion?

The central quantity is subordination: the junior tranche as a share of net
assets.  It is the first loss the senior holder does not take.  Every fund also
carries a contractual floor; breaching it is an evaluation event that forces
amortization or early wind-down.

**The raw cushion is not comparable across categories.**  Two percentage points
of headroom over a 10% floor and two over a 40% floor are different animals.
So this module reports the cushion three ways:

- ``folga_pp``      — the arithmetic distance to the floor, in points;
- ``folga_relativa``— that distance as a fraction of the floor;
- ``perda_ate_gatilho`` — how much of the portfolio can be written off before
  the floor is breached, which is what a credit committee actually needs.

The third one deserves the algebra.  With subordination ``s`` and floor ``m``,
a loss ``L`` (as a share of current net assets) hits the junior first, so net
assets become ``1 - L`` and subordination becomes ``s - L``.  The breach happens
when ``(s - L) / (1 - L) < m``, which solves to::

    L* = (s - m) / (1 - m)

A fund at 25% subordination with a 20% floor absorbs 6.25% of its book — not
the 5 points the arithmetic difference suggests.  The gap between the two grows
with the floor, which is exactly where the naive reading misleads.

Nothing here imputes.  A missing floor produces a missing cushion, never a
zero, because a zero would read as "no protection" when the truth is "not
measured" — and those two lead to opposite decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


#: Columns the caller must provide.  Everything else is derived or optional.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "ativo",
    "categoria",
    "sub_pl_atual",
    "pl_atual",
)

OPTIONAL_COLUMNS: tuple[str, ...] = (
    "cnpj",
    "sub_jr_min_regulamento",
    "data_ref",
    "carteira_flag",
    "mercado_categoria_mediana_sub",
    "mercado_categoria_media_ponderada_pl_sub",
    "mercado_categoria_q25_sub",
    "mercado_categoria_q75_sub",
    "n_comparaveis_categoria",
    "comparacao_estrutural_completa_flag",
)

#: Below this many peers a category median is an anecdote, not a benchmark.
MIN_COMPARABLES = 5

#: Loss-absorption below this is a watchlist item regardless of category.
THIN_LOSS_ABSORPTION = 0.03

#: Arithmetic headroom below this is a watchlist item regardless of category.
THIN_HEADROOM_PP = 0.02

#: Market comparison is deliberately encoded separately from regulatory status.
MARKET_IN_LINE_PP = 0.02


@dataclass(frozen=True)
class StructuralRiskConfig:
    """Configurable thresholds used by the structural-risk chapter."""

    min_comparables: int = MIN_COMPARABLES
    thin_loss_absorption: float = THIN_LOSS_ABSORPTION
    thin_headroom_pp: float = THIN_HEADROOM_PP
    market_in_line_pp: float = MARKET_IN_LINE_PP

#: Positions relative to the floor and to the peer distribution.
BAND_BREACH = "abaixo do mínimo"
BAND_THIN = "folga estreita"
BAND_BELOW_MARKET = "abaixo do mercado"
BAND_IN_LINE = "em linha com o mercado"
BAND_ABOVE_MARKET = "acima do mercado"
BAND_HIGH_CUSHION = "colchão alto"
BAND_ABOVE_FLOOR = "acima do mínimo"
BAND_NO_BENCHMARK = "sem benchmark confiável"
BAND_UNMEASURED = "não medido"

#: Order matters: the first matching rule wins, and breach outranks everything.
BAND_ORDER: tuple[str, ...] = (
    BAND_BREACH,
    BAND_THIN,
    BAND_BELOW_MARKET,
    BAND_IN_LINE,
    BAND_ABOVE_MARKET,
    BAND_HIGH_CUSHION,
    BAND_NO_BENCHMARK,
    BAND_UNMEASURED,
)


@dataclass(frozen=True)
class Coverage:
    """How much of the book each metric actually covers.

    Reported in net assets, not in count: a metric missing on three small funds
    and a metric missing on the largest position are not the same blind spot,
    and counting assets hides the difference.
    """

    campo: str
    ativos_com_dado: int
    ativos_total: int
    pl_com_dado: float
    pl_total: float

    @property
    def cobertura_pl(self) -> float:
        return self.pl_com_dado / self.pl_total if self.pl_total else 0.0


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def loss_until_trigger(subordination: pd.Series, floor: pd.Series) -> pd.Series:
    """Share of the portfolio absorbable before the floor is breached.

    ``(s - m) / (1 - m)``.  Negative when already in breach — kept negative on
    purpose, because clipping it to zero would erase the severity of a breach.
    """

    denominator = 1.0 - floor
    result = (subordination - floor) / denominator
    return result.where(denominator.abs() > 1e-9)


def percentile_from_quartiles(
    value: pd.Series,
    q25: pd.Series,
    median: pd.Series,
    q75: pd.Series,
) -> pd.Series:
    """Position inside the peer distribution, interpolated from three points.

    A true percentile needs the full distribution; three quantiles give a
    piecewise-linear approximation and nothing better.  Outside the quartiles
    the function saturates rather than extrapolating, because the tail shape is
    unknown and inventing it would manufacture precision.

    A z-score would be worse here: it assumes a symmetric distribution that
    subordination levels do not have, being bounded below by the floor.
    """

    value = pd.to_numeric(value, errors="coerce")
    q25, median, q75 = (pd.to_numeric(s, errors="coerce") for s in (q25, median, q75))
    result = pd.Series(np.nan, index=value.index, dtype="float64")

    lower = value <= q25
    result[lower] = 0.25 * (value[lower] - q25[lower]).clip(upper=0).mul(0)  # satura
    result[lower] = 0.25

    middle_low = (value > q25) & (value <= median)
    span = (median - q25).replace(0, np.nan)
    result[middle_low] = 0.25 + 0.25 * (value - q25)[middle_low] / span[middle_low]

    middle_high = (value > median) & (value < q75)
    span = (q75 - median).replace(0, np.nan)
    result[middle_high] = 0.50 + 0.25 * (value - median)[middle_high] / span[middle_high]

    upper = value >= q75
    result[upper] = 0.75
    return result.clip(0.0, 1.0)


def enrich_assets(
    frame: pd.DataFrame,
    config: StructuralRiskConfig | None = None,
) -> pd.DataFrame:
    """Add every derived metric, leaving gaps as gaps."""

    config = config or StructuralRiskConfig()

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise KeyError(f"colunas obrigatórias ausentes: {missing}")

    out = frame.copy()
    sub = _numeric(out, "sub_pl_atual")
    floor = _numeric(out, "sub_jr_min_regulamento")
    pl = _numeric(out, "pl_atual")
    median = _numeric(out, "mercado_categoria_mediana_sub")
    weighted = _numeric(out, "mercado_categoria_media_ponderada_pl_sub")
    q25 = _numeric(out, "mercado_categoria_q25_sub")
    q75 = _numeric(out, "mercado_categoria_q75_sub")
    peers = _numeric(out, "n_comparaveis_categoria")

    comparable = out.get(
        "comparacao_estrutural_completa_flag",
        pd.Series(True, index=out.index),
    )
    comparable = comparable.map(
        lambda value: value
        if isinstance(value, (bool, np.bool_))
        else str(value).strip().lower() in {"1", "true", "sim", "yes"}
    ).fillna(False)
    out["comparacao_estrutural_completa_flag"] = comparable
    market_comparable = out.get(
        "comparacao_mercado_flag",
        pd.Series(True, index=out.index),
    )
    market_comparable = market_comparable.map(
        lambda value: value
        if isinstance(value, (bool, np.bool_))
        else str(value).strip().lower() in {"1", "true", "sim", "yes"}
    ).fillna(False)
    out["comparacao_mercado_flag"] = market_comparable
    out["folga_pp"] = (sub - floor).where(comparable)
    out["folga_relativa"] = ((sub - floor) / floor.replace(0, np.nan)).where(
        comparable
    )
    out["perda_ate_gatilho"] = loss_until_trigger(sub, floor).where(comparable)

    # O benchmark só vale quando há pares suficientes. Sem isso a mediana é
    # anedota, e publicá-la como referência é o erro que esta coluna evita.
    benchmark_ok = peers.ge(config.min_comparables).fillna(False) & market_comparable
    out["benchmark_confiavel"] = benchmark_ok
    out["excesso_vs_mercado"] = (sub - median).where(benchmark_ok)
    out["excesso_vs_mercado_ponderado"] = (sub - weighted).where(benchmark_ok)
    out["percentil_na_categoria"] = percentile_from_quartiles(
        sub, q25, median, q75
    ).where(benchmark_ok)

    total_pl = float(pl.sum())
    out["peso_pl"] = pl / total_pl if total_pl else np.nan
    out["peso_pl_categoria"] = pl / pl.groupby(out["categoria"]).transform("sum")

    out["situacao_regulatoria"] = _regulatory_status(out, sub, floor, comparable, config)
    out["posicao_mercado"] = _market_position(out, benchmark_ok, config)
    # Backwards-compatible column used by existing charts/tests. It now carries
    # only the regulatory situation; market position has its own channel.
    out["banda"] = out["situacao_regulatoria"]
    out["watchlist"] = _watchlist(out, config)
    return out


def _regulatory_status(
    frame: pd.DataFrame,
    sub: pd.Series,
    floor: pd.Series,
    comparable: pd.Series,
    config: StructuralRiskConfig,
) -> pd.Series:
    """Regulatory status, which is the only metric encoded by color."""

    status = pd.Series(BAND_UNMEASURED, index=frame.index, dtype="object")
    measured = sub.notna() & floor.notna() & comparable
    status[measured] = BAND_ABOVE_FLOOR
    thin = measured & (
        frame["perda_ate_gatilho"].lt(config.thin_loss_absorption)
        | frame["folga_pp"].lt(config.thin_headroom_pp)
    )
    status[thin] = BAND_THIN
    status[measured & frame["folga_pp"].lt(0)] = BAND_BREACH
    return status


def _market_position(
    frame: pd.DataFrame,
    benchmark_ok: pd.Series,
    config: StructuralRiskConfig,
) -> pd.Series:
    """Relative position as text/arrows, never as the regulatory color."""

    delta = frame["excesso_vs_mercado"]
    result = pd.Series(BAND_NO_BENCHMARK, index=frame.index, dtype="object")
    result[benchmark_ok & delta.lt(-config.market_in_line_pp)] = BAND_BELOW_MARKET
    result[benchmark_ok & delta.between(-config.market_in_line_pp, config.market_in_line_pp)] = BAND_IN_LINE
    result[benchmark_ok & delta.gt(config.market_in_line_pp)] = BAND_ABOVE_MARKET
    return result


def _classify(
    frame: pd.DataFrame,
    sub: pd.Series,
    floor: pd.Series,
    q25: pd.Series,
    q75: pd.Series,
    benchmark_ok: pd.Series,
) -> pd.Series:
    """Assign one band per asset, breach first, unmeasured last."""

    band = pd.Series(BAND_UNMEASURED, index=frame.index, dtype="object")
    absorption = frame["perda_ate_gatilho"]
    headroom = frame["folga_pp"]

    measured = sub.notna()
    has_floor = measured & floor.notna()

    # Sem piso não dá para falar de folga, mas ainda dá para comparar ao mercado.
    only_market = measured & ~floor.notna() & benchmark_ok
    band[only_market] = BAND_IN_LINE
    band[only_market & sub.gt(q75)] = BAND_ABOVE_MARKET
    band[only_market & sub.lt(q25)] = BAND_BELOW_MARKET

    with_bench = has_floor & benchmark_ok
    band[with_bench] = BAND_IN_LINE
    band[with_bench & sub.gt(q75)] = BAND_ABOVE_MARKET
    band[with_bench & sub.lt(q25)] = BAND_BELOW_MARKET

    band[has_floor & ~benchmark_ok] = BAND_NO_BENCHMARK

    # Um colchão muito acima do q75 é proteção, mas também é capital caro:
    # a banda é separada para que o comitê veja a ineficiência, não só o conforto.
    band[has_floor & benchmark_ok & sub.gt(q75 * 1.5)] = BAND_HIGH_CUSHION

    thin = has_floor & (
        absorption.lt(THIN_LOSS_ABSORPTION) | headroom.lt(THIN_HEADROOM_PP)
    )
    band[thin] = BAND_THIN
    band[has_floor & headroom.lt(0)] = BAND_BREACH
    return band


def _watchlist(frame: pd.DataFrame, config: StructuralRiskConfig) -> pd.Series:
    """Flag the assets a committee has to look at, with the reason attached."""

    reasons: list[str] = []
    peso_mediano = frame["peso_pl"].median()
    for _, row in frame.iterrows():
        why: list[str] = []
        if row["banda"] == BAND_BREACH:
            why.append("abaixo do mínimo regulamentar")
        elif row["banda"] == BAND_THIN:
            why.append("folga estreita")
        grande = pd.notna(row["peso_pl"]) and row["peso_pl"] > max(peso_mediano, 0) * 2
        if grande and pd.notna(row["perda_ate_gatilho"]):
            if row["perda_ate_gatilho"] < config.thin_loss_absorption * 2:
                why.append("posição grande com baixa capacidade de absorção")
        if pd.isna(row.get("sub_jr_min_regulamento")):
            why.append("mínimo regulamentar não localizado")
        if not bool(row.get("benchmark_confiavel", False)):
            why.append("sem benchmark de categoria")
        reasons.append("; ".join(why))
    return pd.Series(reasons, index=frame.index, dtype="object")


def summarize_by_category(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per category, with the simple and the weighted reading side by side.

    Both are needed and they answer different questions.  The median describes
    the typical asset; the PL-weighted average describes where the money
    actually sits.  When they diverge, the book is carrying its protection in
    the small positions — which is the finding, not a rounding artifact.
    """

    if frame.empty:
        return pd.DataFrame()

    def _weighted(values: pd.Series, weights: pd.Series) -> float:
        mask = values.notna() & weights.notna() & weights.gt(0)
        if not mask.any():
            return float("nan")
        return float(np.average(values[mask], weights=weights[mask]))

    rows: list[dict[str, object]] = []
    for categoria, group in frame.groupby("categoria", dropna=False):
        pl = pd.to_numeric(group["pl_atual"], errors="coerce")
        sub = pd.to_numeric(group["sub_pl_atual"], errors="coerce")
        rows.append(
            {
                "categoria": categoria,
                "n_ativos": int(len(group)),
                "pl_total": float(pl.sum()),
                "peso_pl": float(pl.sum()),
                "sub_mediana_carteira": float(sub.median()),
                "sub_ponderada_carteira": _weighted(sub, pl),
                "folga_mediana_pp": float(group["folga_pp"].median()),
                "folga_ponderada_pp": _weighted(group["folga_pp"], pl),
                "perda_ate_gatilho_mediana": float(group["perda_ate_gatilho"].median()),
                "perda_ate_gatilho_ponderada": _weighted(
                    group["perda_ate_gatilho"], pl
                ),
                "mercado_mediana": float(
                    pd.to_numeric(
                        group.get("mercado_categoria_mediana_sub"), errors="coerce"
                    ).median()
                )
                if "mercado_categoria_mediana_sub" in group
                else float("nan"),
                "mercado_ponderada": float(
                    pd.to_numeric(
                        group.get("mercado_categoria_media_ponderada_pl_sub"),
                        errors="coerce",
                    ).median()
                )
                if "mercado_categoria_media_ponderada_pl_sub" in group
                else float("nan"),
                "n_comparaveis": float(
                    pd.to_numeric(
                        group.get("n_comparaveis_categoria"), errors="coerce"
                    ).median()
                )
                if "n_comparaveis_categoria" in group
                else float("nan"),
                "benchmark_confiavel": bool(
                    group.get("benchmark_confiavel", pd.Series(False)).any()
                ),
                "ativos_sem_minimo": int(
                    pd.to_numeric(
                        group.get("sub_jr_min_regulamento"), errors="coerce"
                    ).isna().sum()
                )
                if "sub_jr_min_regulamento" in group
                else int(len(group)),
            }
        )
    result = pd.DataFrame(rows)
    total = result["pl_total"].sum()
    result["peso_pl"] = result["pl_total"] / total if total else np.nan
    result["excesso_vs_mercado"] = (
        result["sub_ponderada_carteira"] - result["mercado_mediana"]
    ).where(result["benchmark_confiavel"])
    return result.sort_values("pl_total", ascending=False).reset_index(drop=True)


def coverage_report(frame: pd.DataFrame, campos: Iterable[str] | None = None) -> pd.DataFrame:
    """Share of the book covered by each field, measured in net assets.

    This table belongs in the deck, not in an appendix.  A committee reading a
    median built on 40% of the portfolio should know it is reading 40%.
    """

    campos = tuple(
        campos
        or (
            "sub_pl_atual",
            "sub_jr_min_regulamento",
            "mercado_categoria_mediana_sub",
            "mercado_categoria_q25_sub",
            "n_comparaveis_categoria",
        )
    )
    pl = pd.to_numeric(frame.get("pl_atual"), errors="coerce").fillna(0.0)
    total_pl = float(pl.sum())
    rows: list[dict[str, object]] = []
    for campo in campos:
        present = (
            pd.to_numeric(frame[campo], errors="coerce").notna()
            if campo in frame.columns
            else pd.Series(False, index=frame.index)
        )
        rows.append(
            {
                "campo": campo,
                "ativos_com_dado": int(present.sum()),
                "ativos_total": int(len(frame)),
                "pl_com_dado": float(pl[present].sum()),
                "pl_total": total_pl,
                "cobertura_pl": float(pl[present].sum() / total_pl) if total_pl else 0.0,
            }
        )
    return pd.DataFrame(rows)


def portfolio_metrics(frame: pd.DataFrame) -> dict[str, float]:
    """Book-level numbers, always weighted, because the book is money not count."""

    pl = pd.to_numeric(frame["pl_atual"], errors="coerce").fillna(0.0)
    sub = pd.to_numeric(frame["sub_pl_atual"], errors="coerce")
    total = float(pl.sum())
    mask = sub.notna() & pl.gt(0)
    absorption = frame["perda_ate_gatilho"]
    amask = absorption.notna() & pl.gt(0)
    return {
        "pl_total": total,
        "n_ativos": float(len(frame)),
        "sub_ponderada": float(np.average(sub[mask], weights=pl[mask])) if mask.any() else float("nan"),
        "sub_mediana": float(sub.median()),
        "perda_ate_gatilho_ponderada": float(
            np.average(absorption[amask], weights=pl[amask])
        )
        if amask.any()
        else float("nan"),
        "pl_em_watchlist": float(pl[frame["watchlist"].str.len().gt(0)].sum()),
        "pl_sem_minimo": float(
            pl[pd.to_numeric(frame.get("sub_jr_min_regulamento"), errors="coerce").isna()].sum()
        )
        if "sub_jr_min_regulamento" in frame.columns
        else total,
    }


def automatic_insights(frame: pd.DataFrame, by_category: pd.DataFrame) -> list[str]:
    """Executive sentences a human can paste into a slide without editing.

    Each one states a number and what it implies.  None of them recommends;
    recommending is the committee's job, and a chart that argues its own
    conclusion is harder to challenge than one that states a fact.
    """

    lines: list[str] = []
    metrics = portfolio_metrics(frame)
    total = metrics["pl_total"]
    if not total:
        return ["Carteira sem patrimônio informado; nenhuma leitura possível."]

    lines.append(
        f"A carteira soma {_brl(total)} em {int(metrics['n_ativos'])} ativos, com "
        f"subordinação ponderada de {_pct(metrics['sub_ponderada'])} — contra "
        f"{_pct(metrics['sub_mediana'])} na mediana simples."
    )
    if (
        pd.notna(metrics["sub_ponderada"])
        and pd.notna(metrics["sub_mediana"])
        and metrics["sub_ponderada"] < metrics["sub_mediana"] - 0.01
    ):
        lines.append(
            "A ponderada abaixo da mediana indica que a proteção está nas posições "
            "menores: os ativos maiores carregam colchão mais fino que o ativo típico."
        )

    if pd.notna(metrics["perda_ate_gatilho_ponderada"]):
        lines.append(
            f"A carteira absorve {_pct(metrics['perda_ate_gatilho_ponderada'])} de perda "
            "antes de o primeiro gatilho de subordinação ser tocado, na média ponderada "
            "por patrimônio."
        )

    breach = frame[frame["banda"].eq(BAND_BREACH)]
    if not breach.empty:
        lines.append(
            f"{len(breach)} ativo(s) abaixo do mínimo regulamentar, somando "
            f"{_brl(float(pd.to_numeric(breach['pl_atual'], errors='coerce').sum()))}."
        )

    thin = frame[frame["banda"].eq(BAND_THIN)]
    if not thin.empty:
        thin_pl = float(pd.to_numeric(thin["pl_atual"], errors="coerce").sum())
        lines.append(
            f"{len(thin)} ativo(s) em folga estreita, {_brl(thin_pl)} "
            f"({_pct(thin_pl / total)} da carteira)."
        )

    if metrics["pl_sem_minimo"] > 0:
        lines.append(
            f"{_pct(metrics['pl_sem_minimo'] / total)} da carteira não tem mínimo "
            "regulamentar localizado; para essa fatia não há leitura de folga, apenas "
            "de nível."
        )

    ranked = by_category.dropna(subset=["excesso_vs_mercado"])
    if not ranked.empty:
        best = ranked.nlargest(1, "excesso_vs_mercado").iloc[0]
        worst = ranked.nsmallest(1, "excesso_vs_mercado").iloc[0]
        lines.append(
            f"Contra o mercado, a maior proteção relativa está em {best['categoria']} "
            f"({_pp(best['excesso_vs_mercado'])} acima da mediana da categoria) e a "
            f"menor em {worst['categoria']} ({_pp(worst['excesso_vs_mercado'])})."
        )

    sem_bench = by_category[~by_category["benchmark_confiavel"]]
    if not sem_bench.empty:
        pl_sem = float(sem_bench["pl_total"].sum())
        lines.append(
            f"{len(sem_bench)} categoria(s), {_pct(pl_sem / total)} da carteira, ficam "
            f"sem comparação de mercado por terem menos de {MIN_COMPARABLES} pares."
        )
    return lines


def _brl(value: float) -> str:
    if pd.isna(value):
        return "N/D"
    if abs(value) >= 1e9:
        return f"R$ {value / 1e9:,.2f} bi".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {value / 1e6:,.1f} mi".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(value: float) -> str:
    return "N/D" if pd.isna(value) else f"{value * 100:.1f}%".replace(".", ",")


def _pp(value: float) -> str:
    return "N/D" if pd.isna(value) else f"{value * 100:+.1f} pp".replace(".", ",")
