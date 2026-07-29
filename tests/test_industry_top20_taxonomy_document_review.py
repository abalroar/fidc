from __future__ import annotations

import pandas as pd

from scripts.build_fidc_top20_taxonomy_document_review import (
    build_top20_universe,
    classify_regulation_pages,
)


def _base() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    periods = ("2023-12", "2024-12", "2025-12", "2026-06")
    categories = (
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    )
    for period_index, period in enumerate(periods):
        for category_index, category in enumerate(categories):
            for rank in range(1, 23):
                rows.append(
                    {
                        "competencia": period,
                        "cnpj_fundo": str(
                            period_index * 10_000
                            + category_index * 100
                            + rank
                        ),
                        "denominacao": f"FIDC {period} {category} {rank}",
                        "pl": float(1_000_000 - rank),
                        "is_fic_fidc": False,
                        "anbima_tipo": category,
                    }
                )
    return pd.DataFrame(rows)


def test_build_top20_universe_returns_20_per_category_and_period() -> None:
    periods = ("2023-12", "2024-12", "2025-12", "2026-06")

    result = build_top20_universe(_base(), periods)

    assert len(result) == 320
    assert set(result.groupby(["competencia", "tipo_exibicao"]).size()) == {20}
    assert result["rank_tipo"].max() == 20


def test_specific_acquiring_evidence_dominates_generic_commercial_language() -> None:
    pages = [
        "A Classe adquire direitos creditórios decorrentes de transações de pagamento "
        "operacionalizadas por credenciadora. Os estabelecimentos realizam prestação "
        "de serviços e os direitos creditórios são cedidos ao Fundo."
    ]

    result = classify_regulation_pages(pages)

    assert result["status"] == "potencial_reclassificacao"
    assert result["n2"] == "Arranjos de pagamento/adquirência"
    assert result["tipo"] == "Agro, Indústria e Comércio"


def test_multiple_distinct_receivable_families_remain_ambiguous() -> None:
    pages = [
        "A política admite cédulas de crédito bancário, créditos inadimplidos e "
        "precatórios originários de ações judiciais."
    ]

    result = classify_regulation_pages(pages)

    assert result["status"] == "ambigua"
    assert result["tipo"] == ""
    assert "mais de uma família" in result["reason"]
