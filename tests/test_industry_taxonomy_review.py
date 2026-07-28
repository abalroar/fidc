from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import warnings

import pandas as pd
import pytest

import services.industry_taxonomy_review as taxonomy_review_module
from services.industry_taxonomy_review import (
    TAXONOMY_REVIEW_COLUMNS,
    apply_taxonomy_review_overlay,
    assert_taxonomy_review_ledger_matches_audit,
    build_curated_type_mix,
    build_taxonomy_review_queue,
    build_top20_by_anbima_type,
    commit_taxonomy_review_action,
    load_taxonomy_review_audit,
    load_taxonomy_review_actions,
    save_taxonomy_review_actions,
    taxonomy_review_summary,
    taxonomy_review_audit_has_pending,
    upsert_taxonomy_review_action,
)


def _action(**updates: object) -> pd.DataFrame:
    row = {column: "" for column in TAXONOMY_REVIEW_COLUMNS}
    row.update(
        {
            "cnpj_fundo": "1",
            "denominacao_referencia": "FIDC OUTROS 1",
            "status": "aprovado",
            "tipo_analitico": "Agro, Indústria e Comércio",
            "foco_analitico": "Recebíveis Comerciais",
            "tabela_ii_analitica": "Adquirência",
            "taxonomia_funcional_n1": "Meios de Pagamento e Cartões",
            "taxonomia_funcional_n2": "Arranjos de pagamento/adquirência",
            "confianca": "alta",
            "documento_id": "123",
            "fonte_documental": "regulamento.pdf",
            "documento_data": "2026-06-15",
            "pagina_clausula": "p. 12, cláusula 4.1",
            "evidencia": "recebíveis de transações em arranjo de pagamento",
            "cedente_originador_expresso": "Instituição de Pagamento S.A.",
            "responsavel": "Analista",
            "competencia_inicio": "2026-06",
            "updated_at_utc": "2026-07-28T12:00:00+00:00",
        }
    )
    row.update(updates)
    return pd.DataFrame([row], columns=list(TAXONOMY_REVIEW_COLUMNS))


def _funds() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    categories = (
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    )
    for category_index, category in enumerate(categories):
        focus = {
            "Fomento Mercantil": "Fomento Mercantil",
            "Agro, Indústria e Comércio": "Recebíveis Comerciais",
            "Financeiro": "Crédito Pessoal",
            "Outros": "Multicarteira Outros",
        }[category]
        for rank in range(1, 106):
            cnpj = category_index * 1000 + rank
            rows.append(
                {
                    "competencia": "2026-06",
                    "cnpj_fundo": str(cnpj),
                    "cnpj_fundo_formatado": str(cnpj),
                    "denominacao": f"FIDC {category} {rank}",
                    "pl": float(1_000_000_000 - rank),
                    "is_fic_fidc": False,
                    "anbima_tipo": category,
                    "anbima_foco": focus,
                    "classification_tier": "oficial_anbima",
                    "classification_status": "oficial",
                    "classification_source": "ANBIMA Data",
                    "classification_warning": "",
                    "cnpj_classe_count": 1,
                    "admin_nome": "Administrador",
                    "admin_cnpj": "10",
                    "gestor_nome": "Gestor",
                    "gestor_cnpj": "20",
                    "custodiante_nome": "Custodiante",
                    "custodiante_cnpj": "30",
                }
            )
    rows.append(
        {
            **rows[-1],
            "cnpj_fundo": "999999",
            "denominacao": "FIDC N/D GRANDE",
            "pl": 2_000_000_000.0,
            "anbima_tipo": "N/D",
            "anbima_foco": "N/D",
            "classification_tier": "nao_disponivel",
        }
    )
    current = pd.DataFrame(rows)
    previous = current.copy()
    previous["competencia"] = "2026-05"
    return pd.concat([previous, current], ignore_index=True)


def test_top20_by_type_has_four_groups_and_uses_slide_bucket() -> None:
    top20, coverage = build_top20_by_anbima_type(_funds(), latest="2026-06")

    assert len(top20) == 80
    assert top20["cnpj_fundo"].nunique() == 80
    assert set(top20.groupby("tipo_exibicao").size()) == {20}
    assert set(top20.groupby("tipo_exibicao")["rank_tipo"].max()) == {20}
    assert "FIDC N/D GRANDE" in set(top20.loc[top20["tipo_exibicao"].eq("Outros"), "denominacao"])
    assert coverage.loc[coverage["tipo_exibicao"].eq("Total"), "fundos"].item() == 80


def test_top20_type_denominator_keeps_negative_pl_from_slide_universe() -> None:
    funds = _funds()
    baseline, _ = build_top20_by_anbima_type(funds, latest="2026-06")
    negative = funds[
        funds["competencia"].eq("2026-06")
        & funds["anbima_tipo"].eq("Fomento Mercantil")
    ].iloc[0].copy()
    negative["cnpj_fundo"] = "88888888888888"
    negative["denominacao"] = "AJUSTE NEGATIVO FORA DO RANKING"
    negative["pl"] = -123_456.0

    reconciled, _ = build_top20_by_anbima_type(
        pd.concat([funds, pd.DataFrame([negative])], ignore_index=True),
        latest="2026-06",
    )

    baseline_total = baseline.loc[
        baseline["tipo_exibicao"].eq("Fomento Mercantil"), "pl_tipo_brl"
    ].iloc[0]
    reconciled_total = reconciled.loc[
        reconciled["tipo_exibicao"].eq("Fomento Mercantil"), "pl_tipo_brl"
    ].iloc[0]
    assert reconciled_total == pytest.approx(baseline_total - 123_456.0)
    assert "AJUSTE NEGATIVO FORA DO RANKING" not in set(reconciled["denominacao"])


def test_supplemental_document_review_completes_top20_originator_evidence() -> None:
    funds = _funds()
    cnpj = funds.loc[
        funds["competencia"].eq("2026-06")
        & funds["anbima_tipo"].eq("Fomento Mercantil"),
        "cnpj_fundo",
    ].iloc[0]
    review = pd.DataFrame(
        [
            {
                "cnpj_fundo": cnpj,
                "document_id": "doc-1",
                "document_reference_date": "2026-05-10",
                "document_url": "https://exemplo.invalid/doc-1",
                "pagina_clausula": "p. 12, cláusula 4.1",
                "cedent_originator_explicit": "Cedente A S.A.",
                "evidence_summary": "O regulamento nomeia Cedente A S.A. como cedente.",
                "confianca_documental": "alta",
                "manual_validation_reason": "",
            }
        ]
    )

    top20, coverage = build_top20_by_anbima_type(
        funds,
        latest="2026-06",
        document_review=review,
    )

    row = top20[top20["cnpj_fundo"].eq(str(cnpj).zfill(14))].iloc[0]
    assert row["cedente_originador"] == "Cedente A S.A."
    assert row["pagina_clausula"] == "p. 12, cláusula 4.1"
    assert row["cedente_status"] == "curadoria_documental_concluida"
    assert coverage.loc[
        coverage["tipo_exibicao"].eq("Fomento Mercantil"),
        "cedente_curadoria_concluida",
    ].item() == 1


def test_queue_filters_bucket_before_ranking_top100() -> None:
    queue = build_taxonomy_review_queue(
        _funds(),
        pd.DataFrame(columns=list(TAXONOMY_REVIEW_COLUMNS)),
        latest="2026-06",
    )

    assert len(queue) == 100
    assert queue["rank_outros_slide"].tolist() == list(range(1, 101))
    assert set(queue["anbima_tipo_oficial"]) == {"Outros", "N/D"}
    assert queue.iloc[0]["denominacao"] == "FIDC N/D GRANDE"


def test_queue_surfaces_documented_fic_perimeter_correction() -> None:
    funds = _funds()
    baseline = build_taxonomy_review_queue(
        funds,
        pd.DataFrame(columns=list(TAXONOMY_REVIEW_COLUMNS)),
        latest="2026-06",
    )
    first = baseline.iloc[0]
    review = pd.DataFrame(
        [
            {
                "cnpj_fundo": first["cnpj_fundo"],
                "document_id": "fic-doc",
                "document_reference_date": "2026-05-04",
                "document_url": "https://exemplo.invalid/fic-doc",
                "pagina_clausula": "pp. 14 e 34",
                "cedent_originator_explicit": "Ausência de cedente nominal.",
                "evidence_summary": "O regulamento classifica o veículo como FICFIDC.",
                "tipo_anbima_sugerido": "Outros",
                "foco_anbima_sugerido": "Multicarteira Outros",
                "tabela_ii_sugerida_documental": "N/D",
                "taxonomia_funcional_n1_sugerida": "",
                "taxonomia_funcional_n2_sugerida": "",
                "reclassification_status": "potencial_reclassificacao",
                "confianca_documental": "alta",
                "perimeter_proposal": "Excluir do perímetro ex-FIC",
                "is_fic_fidc_suggested": "True",
            }
        ]
    )

    queue = build_taxonomy_review_queue(
        funds,
        pd.DataFrame(columns=list(TAXONOMY_REVIEW_COLUMNS)),
        latest="2026-06",
        document_review=review,
    )
    summary = taxonomy_review_summary(
        funds,
        pd.DataFrame(columns=list(TAXONOMY_REVIEW_COLUMNS)),
        latest="2026-06",
        queue=queue,
    )

    row = queue.iloc[0]
    assert bool(row["is_fic_fidc_sugerido"])
    assert row["pl_correcao_perimetro_candidata_brl"] == pytest.approx(row["pl"])
    assert summary["candidatos_correcao_perimetro_brl"] == pytest.approx(row["pl"])


def test_approved_overlay_preserves_official_fields_and_changes_analytical_mix() -> None:
    funds = pd.DataFrame(
        [
            {
                "competencia": "2026-06",
                "cnpj_fundo": "1",
                "denominacao": "FIDC OUTROS 1",
                "pl": 100.0,
                "is_fic_fidc": False,
                "anbima_tipo": "Outros",
                "anbima_foco": "Multicarteira Outros",
                "tabela_ii_dominante": "Cartão de crédito",
            },
            {
                "competencia": "2026-06",
                "cnpj_fundo": "2",
                "denominacao": "FIDC N/D",
                "pl": 50.0,
                "is_fic_fidc": False,
                "anbima_tipo": "N/D",
                "anbima_foco": "N/D",
                "tabela_ii_dominante": "N/D",
            },
        ]
    )

    overlaid = apply_taxonomy_review_overlay(funds, _action())
    first = overlaid.loc[overlaid["cnpj_fundo"].eq("00000000000001")].iloc[0]
    summary = taxonomy_review_summary(funds, _action(), latest="2026-06")

    assert first["anbima_tipo_oficial"] == "Outros"
    assert first["anbima_tipo_curado"] == "Agro, Indústria e Comércio"
    assert first["tabela_ii_curada"] == "Adquirência"
    assert bool(first["taxonomy_review_applied"])
    assert summary["outros_oficial_brl"] == pytest.approx(150.0)
    assert summary["outros_curado_brl"] == pytest.approx(50.0)


def test_approved_overlay_respects_the_starting_competence() -> None:
    funds = pd.DataFrame(
        [
            {
                "competencia": competence,
                "cnpj_fundo": "1",
                "denominacao": "FIDC OUTROS 1",
                "pl": 100.0,
                "is_fic_fidc": False,
                "anbima_tipo": "Outros",
                "anbima_foco": "Multicarteira Outros",
            }
            for competence in ("2025-12", "2026-06")
        ]
    )
    actions = _action(competencia_inicio="2026-06")

    historical = build_curated_type_mix(funds, actions, latest="2025-12").set_index(
        "anbima_tipo"
    )
    current = build_curated_type_mix(funds, actions, latest="2026-06").set_index(
        "anbima_tipo"
    )

    assert historical.loc["Outros", "pl"] == pytest.approx(100.0)
    assert historical.loc["Agro, Indústria e Comércio", "pl"] == pytest.approx(0.0)
    assert current.loc["Outros", "pl"] == pytest.approx(0.0)
    assert current.loc["Agro, Indústria e Comércio", "pl"] == pytest.approx(100.0)


def test_draft_is_saved_but_does_not_apply(tmp_path: Path) -> None:
    actions = _action(status="em_revisao", evidencia="", responsavel="")
    path = tmp_path / "taxonomy_review_actions.csv"

    save_taxonomy_review_actions(actions, path)
    loaded = load_taxonomy_review_actions(path)
    overlaid = apply_taxonomy_review_overlay(
        pd.DataFrame(
            [
                {
                    "competencia": "2026-06",
                    "cnpj_fundo": "1",
                    "anbima_tipo": "Outros",
                    "anbima_foco": "Multicarteira Outros",
                }
            ]
        ),
        loaded,
    )

    assert loaded.iloc[0]["status"] == "em_revisao"
    assert not overlaid["taxonomy_review_applied"].any()


def test_approval_requires_document_page_and_evidence(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="aprovação requer página ou cláusula"):
        save_taxonomy_review_actions(
            _action(pagina_clausula=""),
            tmp_path / "taxonomy_review_actions.csv",
        )


def test_approval_rejects_documentary_placeholders(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="aprovação requer"):
        save_taxonomy_review_actions(
            _action(
                documento_id="N/D",
                fonte_documental="não localizado",
                documento_data="N/D",
                pagina_clausula="N/D",
                evidencia="sem evidência",
            ),
            tmp_path / "taxonomy_review_actions.csv",
        )


@pytest.mark.parametrize(
    "placeholder",
    ["pendente", "a definir", "não disponível", "aguardando documento"],
)
def test_approval_rejects_additional_documentary_placeholders(
    tmp_path: Path,
    placeholder: str,
) -> None:
    with pytest.raises(ValueError, match="aprovação requer ID do documento"):
        save_taxonomy_review_actions(
            _action(documento_id=placeholder),
            tmp_path / "taxonomy_review_actions.csv",
        )


def test_approval_rejects_invalid_document_date(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="data do documento inválida"):
        save_taxonomy_review_actions(
            _action(documento_data="2026-02-30"),
            tmp_path / "taxonomy_review_actions.csv",
        )


@pytest.mark.parametrize("competence", ["2026-00", "2026-13"])
def test_approval_rejects_invalid_calendar_competence(
    tmp_path: Path,
    competence: str,
) -> None:
    with pytest.raises(ValueError, match="competência inicial deve seguir AAAA-MM"):
        save_taxonomy_review_actions(
            _action(competencia_inicio=competence),
            tmp_path / "taxonomy_review_actions.csv",
        )


def test_approval_requires_explicit_table_ii_taxonomy(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match="aprovação requer categoria analítica da Tabela II",
    ):
        save_taxonomy_review_actions(
            _action(tabela_ii_analitica=""),
            tmp_path / "taxonomy_review_actions.csv",
        )

    saved = save_taxonomy_review_actions(
        _action(tabela_ii_analitica="N/D"),
        tmp_path / "taxonomy_review_actions.csv",
    )
    assert saved.iloc[0]["tabela_ii_analitica"] == "N/D"


@pytest.mark.parametrize(
    "updates",
    [
        {"taxonomia_funcional_n1": "", "taxonomia_funcional_n2": ""},
        {
            "taxonomia_funcional_n1": "Meios de Pagamento e Cartões",
            "taxonomia_funcional_n2": "",
        },
    ],
)
def test_approval_requires_complete_functional_taxonomy(
    tmp_path: Path,
    updates: dict[str, str],
) -> None:
    with pytest.raises(ValueError, match="aprovação requer taxonomia funcional N1 e N2"):
        save_taxonomy_review_actions(
            _action(**updates),
            tmp_path / "taxonomy_review_actions.csv",
        )


def test_approval_rejects_uncontrolled_functional_nd(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="taxonomia funcional N1 inválida: N/D"):
        save_taxonomy_review_actions(
            _action(
                taxonomia_funcional_n1="N/D",
                taxonomia_funcional_n2="N/D",
            ),
            tmp_path / "taxonomy_review_actions.csv",
        )


@pytest.mark.parametrize(
    "cnpj",
    [
        "912345678901234",
        "12.345.678/9012-34 extra",
        "abc1",
        "12-345",
    ],
)
def test_review_action_rejects_malformed_raw_cnpj(
    tmp_path: Path,
    cnpj: str,
) -> None:
    with pytest.raises(ValueError, match="CNPJ do fundo"):
        save_taxonomy_review_actions(
            _action(cnpj_fundo=cnpj),
            tmp_path / "taxonomy_review_actions.csv",
        )


def test_review_action_accepts_common_cnpj_mask(tmp_path: Path) -> None:
    saved = save_taxonomy_review_actions(
        _action(cnpj_fundo="12.345.678/9012-34"),
        tmp_path / "taxonomy_review_actions.csv",
    )
    assert saved.iloc[0]["cnpj_fundo"] == "12345678901234"


def test_overlay_fails_closed_for_approved_action_without_documentary_guardrails() -> None:
    action = _action(
        confianca="",
        documento_id="",
        fonte_documental="",
        documento_data="",
        pagina_clausula="",
        evidencia="",
        responsavel="",
    )
    funds = pd.DataFrame(
        [
            {
                "competencia": "2026-06",
                "cnpj_fundo": "1",
                "anbima_tipo": "Outros",
                "anbima_foco": "Multicarteira Outros",
            }
        ]
    )

    overlaid = apply_taxonomy_review_overlay(funds, action)

    assert overlaid.iloc[0]["anbima_tipo_curado"] == "Outros"
    assert overlaid.iloc[0]["anbima_foco_curado"] == "Multicarteira Outros"
    assert not bool(overlaid.iloc[0]["taxonomy_review_applied"])


@pytest.mark.parametrize(
    "competence",
    ["", "invalida", "2026/06", "2026-00", "2026-13"],
)
def test_overlay_fails_closed_for_invalid_fund_competence(competence: str) -> None:
    funds = pd.DataFrame(
        [
            {
                "competencia": competence,
                "cnpj_fundo": "1",
                "anbima_tipo": "Outros",
                "anbima_foco": "Multicarteira Outros",
            }
        ]
    )

    overlaid = apply_taxonomy_review_overlay(funds, _action())

    assert not bool(overlaid.iloc[0]["taxonomy_review_applied"])


def test_approval_requires_nonempty_focus(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Tipo e Foco analíticos"):
        save_taxonomy_review_actions(
            _action(foco_analitico=""),
            tmp_path / "taxonomy_review_actions.csv",
        )


def test_concurrent_upserts_preserve_every_fund_decision(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy_review_actions.csv"

    def upsert(index: int) -> None:
        row = _action(
            cnpj_fundo=str(index),
            denominacao_referencia=f"FIDC {index}",
            status="em_revisao",
            evidencia="",
            responsavel="",
        ).iloc[0].to_dict()
        upsert_taxonomy_review_action(row, path)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(upsert, range(1, 33)))

    loaded = load_taxonomy_review_actions(path)
    assert len(loaded) == 32
    assert set(loaded["cnpj_fundo"]) == {
        str(index).zfill(14) for index in range(1, 33)
    }
    assert not list(tmp_path.glob(".taxonomy_review_actions.csv.tmp-*"))


def test_upsert_replaces_only_the_selected_fund(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy_review_actions.csv"
    first = _action(cnpj_fundo="1", status="em_revisao").iloc[0].to_dict()
    second = _action(cnpj_fundo="2", status="em_revisao").iloc[0].to_dict()
    replacement = _action(cnpj_fundo="1", status="rejeitado").iloc[0].to_dict()

    upsert_taxonomy_review_action(first, path)
    upsert_taxonomy_review_action(second, path)
    upsert_taxonomy_review_action(replacement, path)

    loaded = load_taxonomy_review_actions(path).set_index("cnpj_fundo")
    assert len(loaded) == 2
    assert loaded.loc["00000000000001", "status"] == "rejeitado"
    assert loaded.loc["00000000000002", "status"] == "em_revisao"


def test_commit_persists_decision_with_append_only_audit(tmp_path: Path) -> None:
    ledger_path = tmp_path / "taxonomy_review_actions.csv"
    audit_path = tmp_path / "taxonomy_review_audit.csv"
    action = _action(
        status="em_revisao",
        evidencia="",
        responsavel="",
    ).iloc[0].to_dict()

    updated, events = commit_taxonomy_review_action(
        action,
        ledger_path,
        audit_path,
        saved_at_utc="2026-07-28T12:00:00+00:00",
    )

    audit = pd.read_csv(audit_path, dtype=str, keep_default_na=False)
    assert len(updated) == 1
    assert not events.empty
    assert set(audit["review_domain"]) == {"taxonomy_review"}
    assert set(audit["record_id"]) == {"00000000000001"}
    assert not audit["source"].str.contains(":prepared:", regex=False).any()


def test_commit_preserves_repeated_transitions_within_the_same_second(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "taxonomy_review_actions.csv"
    audit_path = tmp_path / "taxonomy_review_audit.csv"
    saved_at = "2026-07-28T12:00:00+00:00"

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        for status in ("em_revisao", "rejeitado", "em_revisao", "rejeitado"):
            commit_taxonomy_review_action(
                _action(status=status).iloc[0].to_dict(),
                ledger_path,
                audit_path,
                saved_at_utc=saved_at,
            )

    audit = load_taxonomy_review_audit(audit_path)
    status_events = audit[audit["field"].eq("status")]
    assert len(status_events) == 4
    assert status_events["event_id"].is_unique
    assert status_events["event_id"].map(
        lambda value: bool(re.fullmatch(r"[0-9a-f]{32}:[0-9a-f]{20}", value))
    ).all()


def test_commit_recovers_an_interrupted_prepared_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger_path = tmp_path / "taxonomy_review_actions.csv"
    audit_path = tmp_path / "taxonomy_review_audit.csv"
    original_write = taxonomy_review_module._write_taxonomy_review_actions
    calls = 0

    def interrupt_final_audit(frame: pd.DataFrame, path: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("interrupção simulada")
        original_write(frame, path)

    monkeypatch.setattr(
        taxonomy_review_module,
        "_write_taxonomy_review_actions",
        interrupt_final_audit,
    )
    with pytest.raises(RuntimeError, match="interrupção simulada"):
        commit_taxonomy_review_action(
            _action(status="em_revisao").iloc[0].to_dict(),
            ledger_path,
            audit_path,
            saved_at_utc="2026-07-28T12:00:00+00:00",
        )
    assert taxonomy_review_audit_has_pending(audit_path)

    monkeypatch.setattr(
        taxonomy_review_module,
        "_write_taxonomy_review_actions",
        original_write,
    )
    commit_taxonomy_review_action(
        _action(cnpj_fundo="2", status="em_revisao").iloc[0].to_dict(),
        ledger_path,
        audit_path,
        saved_at_utc="2026-07-28T12:01:00+00:00",
    )

    audit = load_taxonomy_review_audit(audit_path)
    assert not taxonomy_review_audit_has_pending(audit_path)
    assert set(audit["record_id"]) == {"00000000000001", "00000000000002"}
    assert audit["event_id"].map(
        lambda value: bool(re.fullmatch(r"[0-9a-f]{32}:[0-9a-f]{20}", value))
    ).all()


def test_empty_ledger_is_reproducible_from_empty_audit(tmp_path: Path) -> None:
    assert_taxonomy_review_ledger_matches_audit(
        tmp_path / "taxonomy_review_actions.csv",
        tmp_path / "taxonomy_review_audit.csv",
    )


def test_committed_ledger_is_reproducible_from_audit(tmp_path: Path) -> None:
    ledger_path = tmp_path / "taxonomy_review_actions.csv"
    audit_path = tmp_path / "taxonomy_review_audit.csv"
    commit_taxonomy_review_action(
        _action().iloc[0].to_dict(),
        ledger_path,
        audit_path,
        saved_at_utc="2026-07-28T12:00:00+00:00",
    )

    assert_taxonomy_review_ledger_matches_audit(ledger_path, audit_path)


def test_replay_rejects_direct_ledger_mutation(tmp_path: Path) -> None:
    ledger_path = tmp_path / "taxonomy_review_actions.csv"
    audit_path = tmp_path / "taxonomy_review_audit.csv"
    commit_taxonomy_review_action(
        _action().iloc[0].to_dict(),
        ledger_path,
        audit_path,
        saved_at_utc="2026-07-28T12:00:00+00:00",
    )
    save_taxonomy_review_actions(_action(status="rejeitado"), ledger_path)

    with pytest.raises(ValueError, match="não é reproduzível"):
        assert_taxonomy_review_ledger_matches_audit(ledger_path, audit_path)


def test_replay_rejects_broken_old_value_chain(tmp_path: Path) -> None:
    ledger_path = tmp_path / "taxonomy_review_actions.csv"
    audit_path = tmp_path / "taxonomy_review_audit.csv"
    commit_taxonomy_review_action(
        _action().iloc[0].to_dict(),
        ledger_path,
        audit_path,
        saved_at_utc="2026-07-28T12:00:00+00:00",
    )
    audit = load_taxonomy_review_audit(audit_path)
    index = audit.index[audit["field"].eq("status")][0]
    transaction_id = str(audit.at[index, "event_id"]).split(":", 1)[0]
    audit.at[index, "old_value"] = "pendente"
    audit.at[index, "event_id"] = taxonomy_review_module._taxonomy_audit_event_id(
        audit.loc[index].to_dict(),
        transaction_id=transaction_id,
    )
    audit.to_csv(audit_path, index=False)

    with pytest.raises(ValueError, match="cadeia de old_value"):
        assert_taxonomy_review_ledger_matches_audit(ledger_path, audit_path)
