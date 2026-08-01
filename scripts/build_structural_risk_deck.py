#!/usr/bin/env python3
"""Build the structural-risk figures and insights from a portfolio CSV.

Reads a book with the minimum contract described in ``services.structural_risk``
and writes one self-contained HTML per figure plus the derived tables.  Runs
with ``--demo`` on synthetic data so the pack can be inspected before the real
book exists.

    python3 scripts/build_structural_risk_deck.py --demo --output-dir /tmp/risco
    python3 scripts/build_structural_risk_deck.py --input carteira.csv --output-dir out/
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.structural_risk import (  # noqa: E402
    automatic_insights,
    coverage_report,
    enrich_assets,
    portfolio_metrics,
    summarize_by_category,
)
from services.structural_risk_charts import (  # noqa: E402
    chart_coverage,
    chart_dumbbell_categories,
    chart_floor_diagonal,
    chart_loss_absorption,
    chart_size_versus_headroom,
)


#: Categorias com o eixo de risco que importa: quem é o devedor final e como o
#: caixa chega.  Consignado INSS e CLT não são o mesmo crédito, e adquirência
#: com risco de banco emissor não é a mesma contraparte de risco adquirente.
DEMO_CATEGORIES = {
    "Consignado INSS": (0.12, 0.08),
    "Consignado CLT": (0.20, 0.15),
    "Consignado FGTS": (0.18, 0.13),
    "Adquirência — banco emissor": (0.10, 0.07),
    "Adquirência — risco adquirente": (0.22, 0.16),
    "Automotivo": (0.16, 0.12),
    "Factoring multicedente": (0.35, 0.28),
    "Crédito PJ": (0.25, 0.18),
    "Cartão consignado": (0.19, 0.14),
    "Judicial/Precatórios": (0.45, 0.35),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def build_demo(seed: int, n: int = 101) -> pd.DataFrame:
    """Synthetic book that reproduces the failure modes worth designing for.

    Deliberately includes: a breach, thin cushions on large positions, a
    category with too few peers to benchmark, and assets with no floor located
    at all — because a pack that only handles clean data is untested.
    """

    rng = np.random.default_rng(seed)
    names = list(DEMO_CATEGORIES)
    rows: list[dict[str, object]] = []
    for index in range(n):
        categoria = names[index % len(names)]
        centre, floor = DEMO_CATEGORIES[categoria]
        # O piso inferior fica acima do mínimo: os rompimentos do demo são os
        # injetados adiante, não ruído do gerador, senão o pacote pareceria
        # encontrar um problema que só existe na amostra sintética.
        sub = float(np.clip(rng.normal(centre, centre * 0.22), floor * 1.02, 0.75))
        pl = float(np.exp(rng.normal(19.0, 1.35)))
        peers = 2 if categoria == "Judicial/Precatórios" else int(rng.integers(6, 40))
        sem_minimo = index % 17 == 0
        rows.append(
            {
                "ativo": f"{categoria.split(' —')[0][:14]} {index + 1:03d}",
                "cnpj": f"{rng.integers(10**13, 10**14 - 1)}",
                "categoria": categoria,
                "sub_pl_atual": sub,
                "sub_jr_min_regulamento": np.nan if sem_minimo else floor,
                "pl_atual": pl,
                "data_ref": "2026-06-30",
                "carteira_flag": "nossa",
                "mercado_categoria_mediana_sub": centre,
                "mercado_categoria_media_ponderada_pl_sub": centre * 0.96,
                "mercado_categoria_q25_sub": centre * 0.85,
                "mercado_categoria_q75_sub": centre * 1.18,
                "n_comparaveis_categoria": peers,
                "comparacao_estrutural_completa_flag": not sem_minimo,
            }
        )
    frame = pd.DataFrame(rows)
    # Um rompimento e duas posições grandes com colchão fino, para provar que o
    # pacote enxerga o que existe para ser enxergado.
    frame.loc[3, "sub_pl_atual"] = frame.loc[3, "sub_jr_min_regulamento"] - 0.015
    big = frame.nlargest(2, "pl_atual").index
    frame.loc[big, "sub_pl_atual"] = frame.loc[big, "sub_jr_min_regulamento"] + 0.008
    return frame


def main() -> None:
    args = parse_args()
    if args.demo:
        book = build_demo(args.seed)
    elif args.input:
        book = pd.read_csv(args.input)
    else:
        raise SystemExit("informe --input ou --demo")

    assets = enrich_assets(book)
    by_category = summarize_by_category(assets)
    coverage = coverage_report(assets)
    metrics = portfolio_metrics(assets)
    insights = automatic_insights(assets, by_category)

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    assets.to_csv(output / "ativos_enriquecidos.csv", index=False)
    by_category.to_csv(output / "resumo_por_categoria.csv", index=False)
    coverage.to_csv(output / "cobertura.csv", index=False)
    (output / "insights.md").write_text(
        "\n".join(f"- {line}" for line in insights), encoding="utf-8"
    )

    figures = {
        "01_piso_diagonal": chart_floor_diagonal(assets),
        "02_dumbbell_categorias": chart_dumbbell_categories(by_category),
        "03_absorcao_perda": chart_loss_absorption(assets),
        "04_porte_x_folga": chart_size_versus_headroom(assets),
        "05_cobertura": chart_coverage(coverage),
    }
    for name, figure in figures.items():
        figure.write_html(
            output / f"{name}.html", include_plotlyjs="cdn", full_html=True
        )

    print(f"[ok] {len(figures)} figuras e 3 tabelas em {output}")
    print(
        f"carteira: R$ {metrics['pl_total'] / 1e9:.2f} bi em {int(metrics['n_ativos'])} ativos"
    )
    print(f"subordinação ponderada: {metrics['sub_ponderada'] * 100:.1f}%")
    print(
        f"absorção de perda ponderada: {metrics['perda_ate_gatilho_ponderada'] * 100:.1f}%"
    )
    print(f"PL em watchlist: R$ {metrics['pl_em_watchlist'] / 1e9:.2f} bi")
    print(f"PL sem mínimo localizado: R$ {metrics['pl_sem_minimo'] / 1e9:.2f} bi")
    print("\nbandas:")
    print(assets["banda"].value_counts().to_string())
    print("\ninsights:")
    for line in insights:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
