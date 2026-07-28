from __future__ import annotations

import pandas as pd
import pytest

from scripts.build_fidc_revision_artifact_payload import _type_mix
from services.industry_taxonomy_review import TAXONOMY_REVIEW_COLUMNS


def test_type_mix_builds_four_periods_and_incorporates_nd_into_outros() -> None:
    rows: list[dict[str, object]] = []
    periods = ("2023-12", "2024-12", "2025-12", "2026-06")
    for index, competencia in enumerate(periods, start=1):
        for category, pl in (
            ("Fomento Mercantil", 10.0 * index),
            ("Agro, Indústria e Comércio", 20.0 * index),
            ("Financeiro", 30.0 * index),
            ("Outros", 35.0 * index),
            ("N/D", 5.0 * index),
        ):
            rows.append(
                {
                    "competencia": competencia,
                    "is_fic_fidc": False,
                    "anbima_tipo": category,
                    "classification_tier": (
                        "nao_disponivel" if category == "N/D" else "oficial_anbima"
                    ),
                    "pl": pl,
                }
            )
        rows.append(
            {
                "competencia": competencia,
                "is_fic_fidc": True,
                "anbima_tipo": "Outros",
                "classification_tier": "oficial_anbima",
                "pl": 1_000.0,
            }
        )

    mix, coverage, meta = _type_mix(pd.DataFrame(rows), "2026-06")

    assert len(mix) == 16
    assert mix["competencia"].drop_duplicates().tolist() == list(periods)
    assert set(mix["anbima_tipo"]) == {
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    }
    assert "N/D" not in set(mix["anbima_tipo"])
    assert (
        mix.groupby("competencia")["share"].sum().tolist()
        == pytest.approx([1.0, 1.0, 1.0, 1.0])
    )
    latest_outros = mix[
        mix["competencia"].eq("2026-06") & mix["anbima_tipo"].eq("Outros")
    ].iloc[0]
    assert latest_outros["pl"] == pytest.approx((35.0 + 5.0) * 4)
    assert meta["nd_incorporated_into"] == "Outros"
    assert [row["label"] for row in meta["periods"]] == [
        "dez/23",
        "dez/24",
        "dez/25",
        "jun/26",
    ]
    assert set(coverage["categoria"]) == {"Oficial ANBIMA", "N/D"}


def test_type_mix_applies_only_approved_analytical_decisions_from_effective_month() -> None:
    rows = []
    for competencia in ("2023-12", "2024-12", "2025-12", "2026-06"):
        rows.extend(
            [
                {
                    "competencia": competencia,
                    "cnpj_fundo": "1",
                    "is_fic_fidc": False,
                    "anbima_tipo": "Outros",
                    "anbima_foco": "Multicarteira Outros",
                    "classification_tier": "oficial_anbima",
                    "pl": 100.0,
                },
                {
                    "competencia": competencia,
                    "cnpj_fundo": "2",
                    "is_fic_fidc": False,
                    "anbima_tipo": "Financeiro",
                    "anbima_foco": "Crédito Pessoal",
                    "classification_tier": "oficial_anbima",
                    "pl": 100.0,
                },
            ]
        )
    action = {column: "" for column in TAXONOMY_REVIEW_COLUMNS}
    action.update(
        {
            "cnpj_fundo": "1",
            "status": "aprovado",
            "tipo_analitico": "Agro, Indústria e Comércio",
            "foco_analitico": "Recebíveis Comerciais",
            "competencia_inicio": "2026-06",
        }
    )

    mix, _, _ = _type_mix(pd.DataFrame(rows), "2026-06", pd.DataFrame([action]))

    historical_outros = mix[
        mix["competencia"].eq("2025-12") & mix["anbima_tipo"].eq("Outros")
    ].iloc[0]
    latest_outros = mix[
        mix["competencia"].eq("2026-06") & mix["anbima_tipo"].eq("Outros")
    ].iloc[0]
    latest_aic = mix[
        mix["competencia"].eq("2026-06")
        & mix["anbima_tipo"].eq("Agro, Indústria e Comércio")
    ].iloc[0]
    assert historical_outros["pl"] == pytest.approx(100.0)
    assert latest_outros["pl"] == pytest.approx(0.0)
    assert latest_aic["pl"] == pytest.approx(100.0)
