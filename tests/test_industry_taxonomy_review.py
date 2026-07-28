from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.industry_taxonomy_review import (
    TAXONOMY_REVIEW_COLUMNS,
    apply_taxonomy_review_overlay,
    build_taxonomy_review_queue,
    load_taxonomy_review_actions,
    save_taxonomy_review_actions,
    taxonomy_review_summary,
)


def _funds() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "competencia": "2026-06",
                "cnpj_fundo": "1",
                "denominacao": "FIDC ADQUIRENCIA",
                "pl": 100.0,
                "is_fic_fidc": False,
                "anbima_tipo": "Outros",
                "anbima_foco": "Multicarteira Outros",
                "classification_tier": "oficial_anbima",
                "classification_status": "oficial",
            },
            {
                "competencia": "2026-06",
                "cnpj_fundo": "2",
                "denominacao": "FIDC N/D",
                "pl": 50.0,
                "is_fic_fidc": False,
                "anbima_tipo": "N/D",
                "anbima_foco": "N/D",
                "classification_tier": "nao_disponivel",
                "classification_status": "N/D",
            },
            {
                "competencia": "2026-06",
                "cnpj_fundo": "3",
                "denominacao": "FIDC FINANCEIRO",
                "pl": 80.0,
                "is_fic_fidc": False,
                "anbima_tipo": "Financeiro",
                "anbima_foco": "Crédito Pessoal",
                "classification_tier": "oficial_anbima",
                "classification_status": "oficial",
            },
        ]
    )


def _approved_action() -> pd.DataFrame:
    row = {column: "" for column in TAXONOMY_REVIEW_COLUMNS}
    row.update(
        {
            "cnpj_fundo": "1",
            "denominacao_referencia": "FIDC ADQUIRENCIA",
            "status": "aprovado",
            "tipo_analitico": "Agro, Indústria e Comércio",
            "foco_analitico": "Recebíveis Comerciais",
            "taxonomia_funcional_n1": "Meios de Pagamento e Cartões",
            "taxonomia_funcional_n2": "Arranjos de pagamento/adquirência",
            "confianca": "alta",
            "fonte_documental": "regulamento.pdf",
            "evidencia": "liquidação de transações em arranjo de pagamento",
            "responsavel": "Analista",
            "competencia_inicio": "2026-06",
            "updated_at_utc": "2026-07-27T12:00:00+00:00",
        }
    )
    return pd.DataFrame([row], columns=list(TAXONOMY_REVIEW_COLUMNS))


def test_approved_overlay_preserves_official_fields_and_reduces_outros() -> None:
    funds = _funds()
    actions = _approved_action()

    overlaid = apply_taxonomy_review_overlay(funds, actions)
    first = overlaid[overlaid["cnpj_fundo"].eq("00000000000001")].iloc[0]
    summary = taxonomy_review_summary(funds, actions, latest="2026-06")

    assert first["anbima_tipo_oficial"] == "Outros"
    assert first["anbima_tipo_curado"] == "Agro, Indústria e Comércio"
    assert first["taxonomy_review_applied"]
    assert summary["outros_oficial_brl"] == pytest.approx(150.0)
    assert summary["outros_curado_brl"] == pytest.approx(50.0)
    assert summary["reducao_liquida_brl"] == pytest.approx(100.0)


def test_draft_is_persisted_but_does_not_change_the_analytical_mix(tmp_path: Path) -> None:
    actions = _approved_action()
    actions.loc[0, "status"] = "em_revisao"
    actions.loc[0, "fonte_documental"] = ""
    actions.loc[0, "evidencia"] = ""
    actions.loc[0, "responsavel"] = ""
    path = tmp_path / "taxonomy_review_actions.csv"

    saved = save_taxonomy_review_actions(actions, path)
    loaded = load_taxonomy_review_actions(path)
    overlaid = apply_taxonomy_review_overlay(_funds(), loaded)

    assert len(saved) == len(loaded) == 1
    assert loaded.iloc[0]["status"] == "em_revisao"
    assert not overlaid["taxonomy_review_applied"].any()


def test_approval_requires_traceability_fields(tmp_path: Path) -> None:
    actions = _approved_action()
    actions.loc[0, "evidencia"] = ""

    with pytest.raises(ValueError, match="aprovação requer evidência"):
        save_taxonomy_review_actions(actions, tmp_path / "actions.csv")


def test_queue_maps_documented_acquiring_to_existing_anbima_options() -> None:
    documentary = pd.DataFrame(
        [
            {
                "cnpj": "1",
                "pl_brl": 100.0,
                "document_segment_n1": "Meios de Pagamento e Cartões",
                "document_segment_n2": "Arranjos de pagamento/adquirência",
                "classification_confidence": "alta",
                "classification_evidence": "arranjo de pagamento",
                "source": "regulamento",
            }
        ]
    )

    queue = build_taxonomy_review_queue(
        _funds(),
        pd.DataFrame(columns=list(TAXONOMY_REVIEW_COLUMNS)),
        latest="2026-06",
        documentary=documentary,
    )

    acquiring = queue[queue["cnpj_fundo"].eq("00000000000001")].iloc[0]
    assert set(queue["cnpj_fundo"]) == {"00000000000001", "00000000000002"}
    assert acquiring["sugestao_tipo_analitico"] == "Agro, Indústria e Comércio"
    assert acquiring["sugestao_foco_analitico"] == "Recebíveis Comerciais"
    assert acquiring["document_source"] == "regulamento"
    assert acquiring["document_classification_evidence"] == "arranjo de pagamento"
    assert acquiring["acao_status"] == "pendente"
