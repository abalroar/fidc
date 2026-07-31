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

    assert len(actions) == 43
    assert len({action["cnpj_fundo"] for action in actions}) == 43
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

    assert sum(action["tipo_analitico"] != "Outros" for action in actions) == 39
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


def test_acquiring_user_decisions_cover_every_named_fidc_and_risk_split() -> None:
    actions = load_manual_override_actions(
        OVERRIDES, saved_at_utc="2026-07-31T12:00:00+00:00"
    )
    by_cnpj = {action["cnpj_fundo"]: action for action in actions}
    bank_issuer = {
        "57609282000146",
        "42085830000109",
        "44124617000194",
        "62393679000183",
        "54218673000141",
        "54218941000125",
        "54219179000100",
        "54248022000102",
        "42085816000105",
        "42102603000144",
        "60356171000180",
        "26286939000158",
        "21824924000182",
        "40906116000109",
        "39862949000136",
        "40906126000144",
        "54979779000168",
        "50971775000182",
        "43911620000195",
        "52240598000190",
        "51983832000106",
        "52247063000140",
        "52272573000178",
        "52256912000122",
    }
    corporate_acquirer = {
        "28169275000172",
        "26287464000114",
        "37262902000106",
        "50473039000102",
        "55471753000177",
        "63572282000111",
    }

    assert bank_issuer | corporate_acquirer <= set(by_cnpj)
    for cnpj in bank_issuer | corporate_acquirer:
        assert by_cnpj[cnpj]["tipo_analitico"] == "Financeiro"
        assert by_cnpj[cnpj]["foco_analitico"] == "Adquirência"
        assert by_cnpj[cnpj]["tabela_ii_analitica"] == "Adquirência"
        assert by_cnpj[cnpj]["taxonomia_funcional_n1"] == (
            "Meios de Pagamento e Cartões"
        )
    assert {
        by_cnpj[cnpj]["taxonomia_funcional_n2"] for cnpj in bank_issuer
    } == {"Banco emissor/cartão de crédito"}
    assert {
        by_cnpj[cnpj]["taxonomia_funcional_n2"] for cnpj in corporate_acquirer
    } == {"Arranjos de pagamento/adquirência"}
    assert {
        by_cnpj[cnpj]["documento_id"]
        for cnpj in bank_issuer | corporate_acquirer
    } == {"chat_task_acquiring_2026_07_31"}
