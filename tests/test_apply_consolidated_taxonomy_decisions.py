from __future__ import annotations

from pathlib import Path

from scripts.apply_consolidated_taxonomy_decisions import (
    load_manual_override_actions,
)
from services.industry_taxonomy_review import validate_taxonomy_review_action


ROOT = Path(__file__).resolve().parents[1]
OVERRIDES = (
    ROOT / "data" / "industry_study" / "taxonomy_user_comment_overrides.csv"
)


def test_user_comment_overrides_are_unique_valid_cnpj_decisions() -> None:
    actions = load_manual_override_actions(
        OVERRIDES, saved_at_utc="2026-07-29T20:21:37+00:00"
    )

    assert len(actions) == 15
    assert len({action["cnpj_fundo"] for action in actions}) == 15
    for action in actions:
        validate_taxonomy_review_action(action)
        assert action["status"] == "aprovado"
        assert action["competencia_inicio"] == ""
        assert action["responsavel"] == "usuario_curadoria_manual"


def test_user_comment_overrides_maximize_non_outros_with_explicit_exceptions() -> None:
    actions = load_manual_override_actions(
        OVERRIDES, saved_at_utc="2026-07-29T20:21:37+00:00"
    )
    by_cnpj = {action["cnpj_fundo"]: action for action in actions}

    assert sum(action["tipo_analitico"] != "Outros" for action in actions) == 11
    assert {
        cnpj
        for cnpj, action in by_cnpj.items()
        if action["tipo_analitico"] == "Outros"
    } == {
        "07727002000126",
        "29225241000110",
        "29301202000155",
        "53216449000158",
    }
    assert by_cnpj["17250006000110"]["tipo_analitico"] == "Fomento Mercantil"
    assert by_cnpj["48349509000170"]["foco_analitico"] == "Crédito Corporativo"
    assert by_cnpj["53073485000100"]["tipo_analitico"] == "Financeiro"
