from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.apply_consolidated_taxonomy_decisions import (
    load_manual_override_actions,
)
from services.industry_taxonomy_review import (
    apply_taxonomy_review_overlay,
    load_taxonomy_review_actions,
    validate_taxonomy_review_action,
)


ROOT = Path(__file__).resolve().parents[1]
OVERRIDES = (
    ROOT / "data" / "industry_study" / "taxonomy_user_comment_overrides.csv"
)
RISK_OVERRIDES = (
    ROOT
    / "data"
    / "industry_study"
    / "taxonomy_user_risk_overrides_2026_07_31.csv"
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


def test_vehicle_decisions_follow_the_documented_debtor_and_preserve_pan_gap() -> None:
    actions = load_manual_override_actions(
        RISK_OVERRIDES, saved_at_utc="2026-07-31T19:30:00+00:00"
    )
    by_cnpj = {action["cnpj_fundo"]: action for action in actions}

    assert len(actions) == 12
    assert len(by_cnpj) == 12
    for action in actions:
        validate_taxonomy_review_action(action)
        assert action["status"] == "aprovado"
        assert action["competencia_inicio"] == ""
        assert action["responsavel"] == "usuario_curadoria_manual"

    concessionary_risk = {
        "28279473000199": "659783",
        "52651831000127": "690896",
        "11230727000181": "700587",
    }
    for cnpj, document_id in concessionary_risk.items():
        action = by_cnpj[cnpj]
        assert action["tipo_analitico"] == "Agro, Indústria e Comércio"
        assert action["foco_analitico"] == "Crédito Corporativo"
        assert "concession" in action["evidencia"].lower()
        assert action["documento_id"] == document_id

    consumer_vehicle = by_cnpj["35868110000154"]
    assert consumer_vehicle["tipo_analitico"] == "Financeiro"
    assert consumer_vehicle["foco_analitico"] == "Financiamento de Veículos"
    assert consumer_vehicle["taxonomia_funcional_n2"] == (
        "Auto/Veículos"
    )
    assert "pessoas físicas" in consumer_vehicle["evidencia"].lower()
    assert consumer_vehicle["documento_id"] == "174945"

    # PAN Auto permanece fora do arquivo aprovado: os documentos disponíveis
    # não identificam se o sacado é concessionária ou tomador de CDC.
    assert "65473848000183" not in by_cnpj


def test_additional_user_decisions_use_existing_taxonomy_labels() -> None:
    actions = load_manual_override_actions(
        RISK_OVERRIDES, saved_at_utc="2026-07-31T19:30:00+00:00"
    )
    by_cnpj = {action["cnpj_fundo"]: action for action in actions}

    assert (
        by_cnpj["42154687000160"]["tipo_analitico"],
        by_cnpj["42154687000160"]["foco_analitico"],
    ) == ("Financeiro", "Multicarteira Financeiro")
    assert (
        by_cnpj["62838025000116"]["tipo_analitico"],
        by_cnpj["62838025000116"]["foco_analitico"],
    ) == ("Financeiro", "Adquirência")
    assert (
        by_cnpj["26722650000134"]["tipo_analitico"],
        by_cnpj["26722650000134"]["foco_analitico"],
    ) == ("Financeiro", "Cartão de crédito")
    assert (
        by_cnpj["32526025000110"]["tipo_analitico"],
        by_cnpj["32526025000110"]["foco_analitico"],
    ) == ("Financeiro", "Cartão de crédito")
    for cnpj in ("53286499000101", "49826785000145", "48349509000170"):
        assert (
            by_cnpj[cnpj]["tipo_analitico"],
            by_cnpj[cnpj]["foco_analitico"],
        ) == ("Outros", "Multicarteira Outros")


def test_published_vehicle_overlay_propagates_by_cnpj_and_preserves_official_fields() -> None:
    data = ROOT / "data" / "industry_study"
    actions = load_taxonomy_review_actions(data / "taxonomy_review_actions.csv")
    funds = pd.read_csv(
        data / "generated_revision" / "base_fundo_cnpj.csv.gz",
        dtype={"cnpj_fundo": str},
        low_memory=False,
    )
    target_cnpjs = {
        "28279473000199",
        "52651831000127",
        "11230727000181",
        "35868110000154",
        "65473848000183",
    }
    funds["cnpj_fundo"] = (
        funds["cnpj_fundo"].str.replace(r"\D", "", regex=True).str.zfill(14)
    )
    scoped = funds[funds["cnpj_fundo"].isin(target_cnpjs)].copy()
    overlaid = apply_taxonomy_review_overlay(scoped, actions)

    concessionary_risk = overlaid[
        overlaid["cnpj_fundo"].isin(
            {"28279473000199", "52651831000127", "11230727000181"}
        )
    ]
    assert concessionary_risk["taxonomy_review_applied"].all()
    assert concessionary_risk["anbima_tipo_curado"].eq(
        "Agro, Indústria e Comércio"
    ).all()
    assert concessionary_risk["anbima_foco_curado"].eq(
        "Crédito Corporativo"
    ).all()
    assert concessionary_risk["anbima_foco"].eq("Crédito Corporativo").all()
    assert concessionary_risk["anbima_foco_oficial"].eq(
        "Recebíveis Comerciais"
    ).all()

    consumer_vehicle = overlaid[
        overlaid["cnpj_fundo"].eq("35868110000154")
    ]
    assert consumer_vehicle["taxonomy_review_applied"].all()
    assert consumer_vehicle["anbima_tipo_curado"].eq("Financeiro").all()
    assert consumer_vehicle["anbima_foco_curado"].eq(
        "Financiamento de Veículos"
    ).all()
    assert consumer_vehicle["anbima_foco_oficial"].eq("N/D").all()

    pan = overlaid[overlaid["cnpj_fundo"].eq("65473848000183")]
    assert pan["taxonomy_review_applied"].all()
    assert pan["anbima_tipo_curado"].eq("Outros").all()
    assert pan["anbima_foco_curado"].eq("Multicedente/Multissacado").all()
    assert pan["anbima_tipo_oficial"].eq(
        "Agro, Indústria e Comércio"
    ).all()
    assert pan["anbima_foco_oficial"].eq("Recebíveis Comerciais").all()
