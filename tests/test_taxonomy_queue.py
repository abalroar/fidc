from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.industry_taxonomy_review import (
    CVM_TABLE_II_CATEGORIES,
    FUNCTIONAL_TAXONOMY,
    validate_taxonomy_review_action,
)
from services.taxonomy_queue import (
    ANONYMOUS_REVIEWER,
    DECISION_STATUSES,
    MAX_SIGNATURE_LENGTH,
    REVIEWER_PREFIX,
    OPEN_STATUSES,
    QUEUE_COLUMNS,
    build_decision,
    build_queue,
    filter_queue,
    focus_options,
    functional_level2_options,
    queue_summary,
    reviewer_responsible,
    taxonomy_vocabularies,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "industry_study"


@pytest.fixture(scope="module")
def queue() -> pd.DataFrame:
    return build_queue(DATA_DIR)


def test_every_vocabulary_offered_by_the_form_is_the_ledger_vocabulary() -> None:
    vocab = taxonomy_vocabularies()

    assert set(vocab["tabela_ii"]) == set(CVM_TABLE_II_CATEGORIES)
    assert set(vocab["n1"]) == set(FUNCTIONAL_TAXONOMY)
    assert set(vocab["status"]) == set(DECISION_STATUSES)
    for level1 in vocab["n1"]:
        assert functional_level2_options(level1) == FUNCTIONAL_TAXONOMY[level1]
    for anbima_type in vocab["tipo"]:
        assert focus_options(anbima_type)


def test_an_unknown_type_offers_no_focus_instead_of_raising() -> None:
    assert focus_options("Inexistente") == ()


def test_queue_has_one_row_per_cnpj_with_the_expected_columns(queue) -> None:
    assert not queue.empty
    assert list(queue.columns) == list(QUEUE_COLUMNS)
    assert not queue["cnpj_fundo"].duplicated().any()
    assert queue["cnpj_fundo"].str.fullmatch(r"\d{14}").all()
    assert queue["pl_max"].is_monotonic_decreasing


def test_queue_status_comes_from_the_ledger(queue) -> None:
    assert queue["status_atual"].isin(DECISION_STATUSES).all()
    summary = queue_summary(queue)
    assert summary["total"] == len(queue)
    assert summary["abertos"] == int(queue["status_atual"].isin(OPEN_STATUSES).sum())


def test_default_filter_shows_only_what_still_needs_a_decision(queue) -> None:
    open_only = filter_queue(queue)

    assert set(open_only["status_atual"]).issubset(set(OPEN_STATUSES))
    assert len(open_only) == int(queue["status_atual"].isin(OPEN_STATUSES).sum())


def test_search_matches_name_and_cnpj(queue) -> None:
    sample = queue.iloc[0]
    everything = DECISION_STATUSES

    by_name = filter_queue(queue, statuses=everything, search=sample["nome_fidc"][:18])
    by_cnpj = filter_queue(queue, statuses=everything, search=sample["cnpj_fundo"][:8])

    assert sample["cnpj_fundo"] in set(by_name["cnpj_fundo"])
    assert sample["cnpj_fundo"] in set(by_cnpj["cnpj_fundo"])


def test_search_accepts_a_formatted_cnpj(queue) -> None:
    sample = queue.iloc[0]
    digits = sample["cnpj_fundo"]
    masked = f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"

    found = filter_queue(queue, statuses=DECISION_STATUSES, search=masked)

    assert sample["cnpj_fundo"] in set(found["cnpj_fundo"])


def test_every_prefilled_row_produces_a_valid_ledger_action(queue) -> None:
    """The form must never offer a combination the ledger would refuse."""

    for record in queue.to_dict(orient="records"):
        row = pd.Series(record)
        tipo = row["tipo_sugerido"] or "Outros"
        focus_choices = focus_options(tipo)
        foco = row["foco_sugerido"] if row["foco_sugerido"] in focus_choices else focus_choices[0]
        n1 = row["n1_sugerida"] or "Multissetorial / Outros"
        level2_choices = functional_level2_options(n1)
        n2 = row["n2_sugerida"] if row["n2_sugerida"] in level2_choices else level2_choices[0]
        action = build_decision(
            row,
            status="aprovado",
            tipo=tipo,
            foco=foco,
            tabela_ii=row["tabela_ii_sugerida"] or "N/D",
            n1=n1,
            n2=n2,
            confianca=row["confianca"] or "media",
            justificativa=row["justificativa"],
            responsavel="curadoria_manual_streamlit",
            saved_at_utc="2026-07-30T00:00:00+00:00",
        )
        validate_taxonomy_review_action(action)


def test_a_rejected_decision_may_leave_every_taxonomy_empty(queue) -> None:
    action = build_decision(
        queue.iloc[0],
        status="rejeitado",
        tipo="",
        foco="",
        tabela_ii="",
        n1="",
        n2="",
        confianca="media",
        justificativa="Fora do perímetro FIDC.",
        responsavel="curadoria_manual_streamlit",
        saved_at_utc="2026-07-30T00:00:00+00:00",
    )

    validate_taxonomy_review_action(action)
    assert action["status"] == "rejeitado"


def test_the_decision_carries_the_evidence_into_the_ledger(queue) -> None:
    documented = queue[queue["evidencia"].str.len().gt(0)].iloc[0]

    action = build_decision(
        documented,
        status="aprovado",
        tipo=documented["tipo_sugerido"] or "Outros",
        foco=documented["foco_sugerido"] or "Multicarteira Outros",
        tabela_ii=documented["tabela_ii_sugerida"] or "N/D",
        n1=documented["n1_sugerida"] or "Multissetorial / Outros",
        n2=documented["n2_sugerida"] or "Multicarteira outros",
        confianca="alta",
        justificativa="Validado manualmente.",
        responsavel="curadoria_manual_streamlit",
        saved_at_utc="2026-07-30T00:00:00+00:00",
    )

    assert action["evidencia"]
    assert "Validado manualmente." in str(action["notas"])
    assert action["responsavel"] == "curadoria_manual_streamlit"


def test_the_panel_module_exposes_its_entrypoint() -> None:
    from tabs.tab_taxonomy_queue import render_tab_taxonomy_queue

    assert callable(render_tab_taxonomy_queue)


def test_the_app_registers_the_section() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert '("taxonomia", "Fila de Taxonomia")' in source
    assert "render_tab_taxonomy_queue()" in source


def test_a_signature_becomes_an_attributable_responsible() -> None:
    assert reviewer_responsible("Matheus Prates") == (
        "curadoria_manual_streamlit:matheus-prates"
    )
    assert reviewer_responsible("  ANA/Ré  Silva ") == (
        "curadoria_manual_streamlit:ana-ré-silva"
    )


def test_an_unsigned_review_is_recorded_as_anonymous_not_as_someone_else() -> None:
    """A blank field must never borrow the previous reviewer's name."""

    assert reviewer_responsible("") == ANONYMOUS_REVIEWER
    assert reviewer_responsible("   ") == ANONYMOUS_REVIEWER
    assert reviewer_responsible("///") == ANONYMOUS_REVIEWER


def test_a_signature_cannot_break_the_ledger_row() -> None:
    responsible = reviewer_responsible("a" * 200 + ' ";\n\tdrop')

    assert "\n" not in responsible and '"' not in responsible
    assert len(responsible) <= len(REVIEWER_PREFIX) + 1 + MAX_SIGNATURE_LENGTH


def test_an_override_reason_leads_the_notes(queue: pd.DataFrame) -> None:
    documented = queue[queue["evidencia"].str.len().gt(0)].iloc[0]

    action = build_decision(
        documented,
        status="aprovado",
        tipo=documented["tipo_sugerido"] or "Outros",
        foco=documented["foco_sugerido"] or "Multicarteira Outros",
        tabela_ii=documented["tabela_ii_sugerida"] or "N/D",
        n1=documented["n1_sugerida"] or "Multissetorial / Outros",
        n2=documented["n2_sugerida"] or "Multicarteira outros",
        confianca="alta",
        justificativa="Validado manualmente.",
        responsavel=reviewer_responsible("ana"),
        saved_at_utc="2026-07-30T00:00:00+00:00",
        motivo_override="o regulamento novo declara outro foco",
    )

    assert str(action["notas"]).startswith(
        "Sobrescreve aprovação anterior: o regulamento novo declara outro foco"
    )
    assert action["responsavel"] == "curadoria_manual_streamlit:ana"
    validate_taxonomy_review_action(action)


def test_the_panel_refuses_to_overwrite_an_approval_without_a_reason() -> None:
    """The guardrail lives in the panel; assert it is wired, not decorative."""

    source = (ROOT / "tabs" / "tab_taxonomy_queue.py").read_text(encoding="utf-8")

    assert 'overriding = str(row["status_atual"]) == "aprovado"' in source
    assert "if overriding and not motivo_override.strip():" in source
    assert "motivo_override=motivo_override" in source
