"""Executive analytics over the ANBIMA fixed-income/hybrid ranking.

Everything here is derived from the two official workbooks parsed by
``services.anbima_fixed_income_ranking``:

* the published ranking — league tables per type, measure and window; and
* the closing annex — one row per (operation, participant) with the share
  credited to each participant.

The module produces the tables an executive pack needs: league tables with
gaps to the leader and to the house, a per-product position map, the
operation participation matrix, and the largest operations of the period.
"""

from __future__ import annotations

import pandas as pd

from services.anbima_fixed_income_ranking import CLASS_LABELS


HOUSE = "ITAU BBA"

#: The peer set the committee compares against, in the order it is presented.
PEERS: tuple[str, ...] = (
    "BRADESCO BBI",
    "ITAU BBA",
    "BTG PACTUAL",
    "SANTANDER",
    "XP INVESTIMENTOS",
    "UBS BB",
)

DISPLAY_NAMES: dict[str, str] = {
    "BRADESCO BBI": "Bradesco BBI",
    "ITAU BBA": "Itaú BBA",
    "BTG PACTUAL": "BTG Pactual",
    "SANTANDER": "Santander",
    "XP INVESTIMENTOS": "XP Investimentos",
    "UBS BB": "UBS BB",
    "CEF": "Caixa Econômica Federal",
    "SAFRA": "Safra",
    "ABC BRASIL": "ABC Brasil",
    "VOTORANTIM": "Votorantim",
    "CITIGROUP": "Citigroup",
    "BNDES": "BNDES",
    "BR PARTNERS": "BR Partners",
    "BB-BI": "BB-BI",
    "DAYCOVAL": "Daycoval",
    "BNP PARIBAS": "BNP Paribas",
    "BOCOM BBM": "Bocom BBM",
    "INTER": "Inter",
    "M7 IB": "M7 IB",
    "JP MORGAN": "J.P. Morgan",
    "RABOBANK": "Rabobank",
    "ONE CORPORATE": "One Corporate",
}

WINDOWS: dict[str, str] = {
    "acumulado_ano": "Acumulado 2026 (jan–jun)",
    "ultimos_12_meses": "Últimos 12 meses (jul/25–jun/26)",
}

MEASURES: dict[str, str] = {
    "originacao_valor": "Originação",
    "distribuicao_valor": "Distribuição",
}

#: Segments reported in the per-product view, in committee order.
SEGMENTS: tuple[tuple[str, str], ...] = (
    ("1", "Renda fixa consolidada"),
    ("1.2", "Renda fixa — longo prazo"),
    ("1.1", "Renda fixa — curto prazo"),
    ("1.3", "Securitização"),
    ("1.3.1", "FIDC"),
    ("1.3.2", "CRI"),
    ("1.3.3", "CRA"),
    ("1.3.4", "CR"),
    ("2", "Operações híbridas"),
    ("2.2", "FII"),
    ("2.4", "FI-Infra (FIP-IE)"),
    ("2.5", "FIAGRO"),
)

#: Instrument label derived from the ANBIMA asset class of the operation.
INSTRUMENTS: dict[str, str] = {
    "1.1.A": "Debênture",
    "1.1.B": "Nota promissória",
    "1.1.C": "VM agência multilateral",
    "1.1.D": "Nota comercial",
    "1.1.E": "CPR-F",
    "1.2.A": "Debênture",
    "1.2.B": "Nota promissória",
    "1.2.C": "VM agência multilateral",
    "1.2.D": "Nota comercial",
    "1.2.E": "CPR-F",
    "1.3.1": "FIDC",
    "1.3.2": "CRI",
    "1.3.3": "CRA",
    "1.3.4": "CR",
    "2.1.A": "Debênture conversível",
    "2.1.B": "Debênture permutável",
    "2.2": "FII",
    "2.3": "CEPAC",
    "2.4": "FI-Infra (FIP-IE)",
    "2.5": "FIAGRO",
}

BLOCK_LABELS: dict[str, str] = {
    "1": "Tipo 1 — Renda fixa",
    "2": "Tipo 2 — Híbridas",
    "3": "Tipo 3 — Empresas ligadas",
}

PARTICIPATED = "X"
LEADER = "Líder"
ABSENT = "–"


def display_name(value: object) -> str:
    label = str(value).strip()
    return DISPLAY_NAMES.get(label.upper(), label.title() if label.isupper() else label)


def league_table(
    official: pd.DataFrame,
    *,
    measure: str,
    window: str,
    ranking_code: str = "1",
    limit: int | None = None,
) -> pd.DataFrame:
    """League table with volume, share and gaps to the leader and the house."""

    block = official[
        official["measure"].eq(measure)
        & official["window"].eq(window)
        & official["ranking_code"].eq(ranking_code)
    ]
    block = block[block["value_brl_or_count"] > 0].sort_values("rank")
    if block.empty:
        return pd.DataFrame()

    leader_share = float(block["share"].iloc[0])
    house = block[block["participant"].eq(HOUSE)]
    house_share = float(house["share"].iloc[0]) if not house.empty else float("nan")

    table = pd.DataFrame(
        {
            "posicao": block["rank"].astype(int),
            "instituicao": block["participant"].map(display_name),
            "participante": block["participant"],
            "volume_brl_mm": block["value_brl_or_count"] / 1e6,
            "market_share": block["share"],
            "gap_lider_pp": (block["share"] - leader_share) * 100,
            "gap_itau_pp": (block["share"] - house_share) * 100,
        }
    ).reset_index(drop=True)
    if limit is not None:
        keep = table.index < limit
        keep |= table["participante"].isin(PEERS)
        table = table[keep]
    return table.reset_index(drop=True)


def _position(official: pd.DataFrame, measure: str, window: str, code: str) -> tuple:
    block = official[
        official["measure"].eq(measure)
        & official["window"].eq(window)
        & official["ranking_code"].eq(code)
    ]
    block = block[block["value_brl_or_count"] > 0]
    if block.empty:
        return (None, None, None)
    house = block[block["participant"].eq(HOUSE)]
    if house.empty:
        return (None, None, int(len(block)))
    return (
        int(house["rank"].iloc[0]),
        float(house["share"].iloc[0]),
        int(len(block)),
    )


def product_view(official: pd.DataFrame) -> pd.DataFrame:
    """Per-segment position of the house across measures and windows."""

    rows: list[dict[str, object]] = []
    for code, label in SEGMENTS:
        for measure, measure_label in MEASURES.items():
            rank_ytd, share_ytd, peers_ytd = _position(
                official, measure, "acumulado_ano", code
            )
            rank_12m, share_12m, _ = _position(
                official, measure, "ultimos_12_meses", code
            )
            if rank_ytd is None and rank_12m is None and peers_ytd is None:
                continue
            rows.append(
                {
                    "segmento": label,
                    "codigo_anbima": code,
                    "visao": measure_label,
                    "ranking_1s26": rank_ytd,
                    "share_1s26": share_ytd,
                    "ranking_12m": rank_12m,
                    "share_12m": share_12m,
                    "variacao_posicao": (
                        rank_12m - rank_ytd
                        if rank_ytd is not None and rank_12m is not None
                        else None
                    ),
                    "concorrentes_1s26": peers_ytd,
                }
            )
    return pd.DataFrame(rows)


def operation_matrix(
    annex: pd.DataFrame,
    *,
    role: str = "originacao",
    peers: tuple[str, ...] = PEERS,
) -> pd.DataFrame:
    """One row per operation, one column per peer, ``Líder``/``X``/``–``.

    The operation is keyed on the CVM registration, as required: two series of
    the same issuance under different registrations stay on separate rows, and
    the same registration consolidates its participants onto one row.
    """

    source = annex[annex["role"].eq(role)].copy()
    if source.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for registro, group in source.groupby("registro_cvm", sort=False):
        total = float(group["valor_brl"].sum())
        percentages = group.groupby("participante")["percentual_participacao"].sum()
        values = group.groupby("participante")["valor_brl"].sum()
        best = float(percentages.max()) if len(percentages) else 0.0
        # A leader is only meaningful when some share was actually credited;
        # an all-zero registration has formal participants and no economics.
        leaders = (
            sorted(percentages[percentages.eq(best)].index) if best > 0 else []
        )
        first = group.sort_values("data_encerramento").iloc[0]

        record: dict[str, object] = {
            "operacao": str(first["emissor"]).replace("\n", " ").strip(),
            "registro_cvm": registro,
            "instrumento": INSTRUMENTS.get(str(first["classe"]), ""),
            "classe_anbima": str(first["classe"]),
            "classe_descricao": CLASS_LABELS.get(str(first["classe"]), ""),
            "bloco_anbima": BLOCK_LABELS.get(str(first["block_code"]), ""),
            "originador_risco": str(first["risco_securitizacao"]).replace("\n", " ").strip(),
            "regime_colocacao": str(first["regime_colocacao"]),
            "data_encerramento": first["data_encerramento"],
            "valor_total_brl_mil": total / 1e3,
            "valor_total_brl_mm": total / 1e6,
        }
        for peer in peers:
            if peer not in percentages.index:
                record[peer] = ABSENT
            elif peer in leaders:
                record[peer] = LEADER
            else:
                record[peer] = PARTICIPATED

        house_pct = float(percentages.get(HOUSE, float("nan")))
        record["participacao_itau_pct"] = (
            house_pct if HOUSE in percentages.index else float("nan")
        )
        record["valor_itau_brl_mm"] = (
            float(values.get(HOUSE, 0.0)) / 1e6 if HOUSE in values.index else float("nan")
        )
        record["itau_participa"] = "Sim" if HOUSE in percentages.index else "Não"
        record["lideres"] = " | ".join(display_name(name) for name in leaders) or "—"
        others = [
            name for name in sorted(percentages.index) if name not in peers
        ]
        record["demais_participantes"] = (
            " | ".join(display_name(name) for name in others) or "—"
        )
        record["participantes_completos"] = " | ".join(
            f"{display_name(name)} ({percentages[name]:.1%})"
            for name in percentages.sort_values(ascending=False).index
        )
        record["n_participantes"] = int(len(percentages))
        record["sem_valor_economico"] = "Sim" if total == 0 else "Não"
        rows.append(record)

    matrix = pd.DataFrame(rows)
    return matrix.sort_values(
        ["data_encerramento", "valor_total_brl_mm"], ascending=[False, False]
    ).reset_index(drop=True)


def largest_operations(matrix: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """The largest operations of the period, by total operation value."""

    if matrix.empty:
        return matrix
    top = matrix.nlargest(limit, "valor_total_brl_mm").copy()
    top["participacao_itau"] = top.apply(
        lambda row: (
            "—"
            if row["itau_participa"] == "Não"
            else f"{row['participacao_itau_pct'] * 100:.1f}%".replace(".", ",")
        ),
        axis=1,
    )
    return top.reset_index(drop=True)


def peer_chart_frame(
    official: pd.DataFrame, *, measure: str, window: str, ranking_code: str = "1"
) -> pd.DataFrame:
    """The six peers, ranked, ready for a horizontal bar chart."""

    table = league_table(
        official, measure=measure, window=window, ranking_code=ranking_code
    )
    if table.empty:
        return table
    peers = table[table["participante"].isin(PEERS)].copy()
    return peers.sort_values("market_share", ascending=False).reset_index(drop=True)


__all__ = [
    "ABSENT",
    "BLOCK_LABELS",
    "DISPLAY_NAMES",
    "HOUSE",
    "INSTRUMENTS",
    "LEADER",
    "MEASURES",
    "PARTICIPATED",
    "PEERS",
    "SEGMENTS",
    "WINDOWS",
    "display_name",
    "largest_operations",
    "league_table",
    "operation_matrix",
    "peer_chart_frame",
    "product_view",
]
