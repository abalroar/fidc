from __future__ import annotations

import pandas as pd


ROLL_SEASONALITY_CHARTS: tuple[dict[str, str], ...] = (
    {
        "metric_id": "roll_61_90_m3",
        "title": "Roll 61-90 por mês do ano",
        "note": "Fórmula: atraso 61-90 no mês t ÷ carteira a vencer três meses antes. O gráfico mostra sazonalidade e compara anos na mesma janela mensal.",
    },
    {
        "metric_id": "roll_91_120_m4",
        "title": "Roll 91-120 por mês do ano",
        "note": "Fórmula: atraso 91-120 no mês t ÷ carteira a vencer quatro meses antes. A defasagem acompanha a maturação para atraso acima de 90 dias.",
    },
    {
        "metric_id": "roll_121_150_m5",
        "title": "Roll 121-150 por mês do ano",
        "note": "Fórmula: atraso 121-150 no mês t ÷ carteira a vencer cinco meses antes. A série mostra a migração intermediária antes do bucket 151-180.",
    },
    {
        "metric_id": "roll_151_180_m6",
        "title": "Roll 151-180 por mês do ano",
        "note": "Fórmula: atraso 151-180 no mês t ÷ carteira a vencer seis meses antes. A defasagem acompanha a maturação até atraso severo.",
    },
)

ROLL_RATES_NOTES: tuple[str, ...] = (
    "Cada linha mede o atraso observado no mês t dividido pela carteira a vencer de uma competência anterior.",
    "A defasagem acompanha o bucket: 61-90 usa M-3, 91-120 usa M-4, 121-150 usa M-5 e 151-180 usa M-6.",
    "Exemplo: Roll 91-120 em abr/26 = atraso 91-120 de abr/26 dividido pela carteira a vencer em dez/25.",
)


def available_roll_seasonality_specs(roll_df: pd.DataFrame) -> tuple[dict[str, str], ...]:
    if roll_df is None or roll_df.empty or "metric_id" not in roll_df.columns:
        return tuple()
    return tuple(spec for spec in ROLL_SEASONALITY_CHARTS if not roll_df[roll_df["metric_id"].eq(spec["metric_id"])].empty)


def default_roll_seasonality_metric_ids(specs: tuple[dict[str, str], ...]) -> list[str]:
    return [specs[0]["metric_id"]] if specs else []
