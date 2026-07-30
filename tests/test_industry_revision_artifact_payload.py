from __future__ import annotations

import pandas as pd
import pytest

from scripts.build_fidc_revision_artifact_payload import (
    _apply_detected_fic_history,
    _type_mix_history,
)


def test_detected_fic_history_replaces_the_legacy_component() -> None:
    annual = pd.DataFrame(
        [
            {"year": 2025, "competencia": "2025-12", "pl_total": 200.0, "pl_fic_fidc": 10.0},
            {"year": 2026, "competencia": "2026-06", "pl_total": 300.0, "pl_fic_fidc": 20.0},
        ]
    )
    audit = pd.DataFrame(
        [
            {"competencia": "2025-12", "cnpj_fundo": "1", "is_fic": True, "pl": 30.0},
            {"competencia": "2026-06", "cnpj_fundo": "1", "is_fic": True, "pl": 40.0},
            {"competencia": "2026-06", "cnpj_fundo": "2", "is_fic": True, "pl": 10.0},
            {"competencia": "2026-06", "cnpj_fundo": "3", "is_fic": False, "pl": 99.0},
        ]
    )

    output = _apply_detected_fic_history(annual, audit)

    assert output["pl_fic_fidc"].tolist() == pytest.approx([30.0, 50.0])
    assert output["pl_ex_fic"].tolist() == pytest.approx([170.0, 250.0])
    assert output["fundos_fic_detectados"].tolist() == [1, 2]


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

    mix, coverage, meta = _type_mix_history(pd.DataFrame(rows), list(periods))

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
