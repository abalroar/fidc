from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.industry_outros_reclassification import (
    FAMILY_BY_ID,
    MULTICARTEIRA_BY_TYPE,
    RECEIVABLE_FAMILIES,
    decide,
    detect_fic_fidc,
    extract_anbima_declaration,
    resolve_with_declared_segment,
    detect_perimeter,
    fold_text,
    score_families,
)
from services.industry_taxonomy_review import (
    FUNCTIONAL_TAXONOMY,
    CVM_TABLE_II_CATEGORIES,
    valid_analytical_type_focus_pair,
)


ROOT = Path(__file__).resolve().parents[1]
CONCLUSIONS = (
    ROOT / "data" / "industry_study" / "industry_outros_reclassification_conclusions.csv"
)
PENDING_CURATION = (
    ROOT / "data" / "industry_study" / "industry_top20_pending_curation.csv"
)


def _document(*pages: str) -> list[tuple[str, list[str]]]:
    return [("regulamento 1", list(pages))]


def test_every_family_targets_the_existing_project_taxonomies() -> None:
    for family in RECEIVABLE_FAMILIES:
        assert valid_analytical_type_focus_pair(family.tipo, family.foco)
        assert family.tabela_ii in CVM_TABLE_II_CATEGORIES
        assert family.n1 in FUNCTIONAL_TAXONOMY
        assert family.n2 in FUNCTIONAL_TAXONOMY[family.n1]


def test_multicarteira_targets_are_valid_for_every_anbima_type() -> None:
    for anbima_type, (foco, table_ii, n1, n2) in MULTICARTEIRA_BY_TYPE.items():
        assert valid_analytical_type_focus_pair(anbima_type, foco)
        assert table_ii in CVM_TABLE_II_CATEGORIES
        assert n2 in FUNCTIONAL_TAXONOMY[n1]


def test_policy_section_outweighs_a_risk_section_mention() -> None:
    policy = "CRITERIOS DE ELEGIBILIDADE: DIREITOS CREDITORIOS ORIUNDOS DE PRECATORIOS"
    risk = (
        "FATORES DE RISCO: A COBRANCA PODERA ENVOLVER DUPLICATAS, DUPLICATAS "
        "E DUPLICATAS DE TERCEIROS"
    )
    scores = score_families(_document(policy, risk))

    assert scores["precatorios"].score > scores["recebiveis_comerciais"].score


def test_vehicle_purpose_absorbs_the_bank_note_instrument() -> None:
    page = (
        "POLITICA DE INVESTIMENTO: A CLASSE ADQUIRE CEDULAS DE CREDITO BANCARIO "
        "CEDULAS DE CREDITO BANCARIO CEDULAS DE CREDITO BANCARIO DECORRENTES DE "
        "FINANCIAMENTO DE VEICULOS COM ALIENACAO FIDUCIARIA DE VEICULOS"
    )
    decision = decide(_document(page), official_type="Outros")

    assert decision.decision_status == "aprovado"
    assert decision.n2 == "Auto/Veículos"


def test_payroll_loan_absorbs_the_public_entity_vocabulary() -> None:
    page = (
        "CRITERIOS DE ELEGIBILIDADE: EMPRESTIMOS CONSIGNADOS COM AVERBACAO EM "
        "FOLHA, INCLUSIVE INSS, COM RECEITAS PUBLICAS COMO ORIGEM DA MARGEM "
        "CONSIGNAVEL E MARGEM CONSIGNAVEL VERIFICADA"
    )
    decision = decide(_document(page), official_type="Outros")

    assert decision.decision_status == "aprovado"
    assert decision.tipo == "Financeiro"
    assert decision.foco == "Crédito Consignado"


def test_public_requisition_and_private_judicial_credits_are_separate_families() -> None:
    assert FAMILY_BY_ID["precatorios"].foco == "Poder Público"
    assert FAMILY_BY_ID["direitos_judiciais"].foco == "Recuperação"
    assert FAMILY_BY_ID["direitos_judiciais"].n1 == "Judicial/Precatórios/NPL"


def test_a_multimarket_fif_regulation_is_rejected_for_the_fidc_perimeter() -> None:
    pages = (
        "REGULAMENTO DO FUNDO DE INVESTIMENTO FINANCEIRO ALFA MULTIMERCADO",
        "POLITICA DE INVESTIMENTOS: INVESTIR EM ATIVOS FINANCEIROS, COTAS DE "
        "FUNDOS DE INVESTIMENTO EM DIREITOS CREDITORIOS ATE 40% E DEBENTURES",
    )
    assert detect_perimeter(_document(*pages))
    decision = decide(_document(*pages), official_type="Outros")
    assert decision.decision_status == "rejeitado"


def test_a_receivables_regulation_is_never_treated_as_a_perimeter_error() -> None:
    pages = (
        "REGULAMENTO DO FUNDO DE INVESTIMENTO FINANCEIRO BETA MULTIMERCADO",
        "CRITERIOS DE ELEGIBILIDADE E CONDICOES DE CESSAO DEFINIDAS COM O CEDENTE",
    )
    assert detect_perimeter(_document(*pages)) == ""


def test_a_document_without_text_stays_pendente() -> None:
    decision = decide([], official_type="Outros", readable=False)

    assert decision.decision_status == "pendente"
    assert decision.limitation


def test_four_competing_families_produce_a_multicarteira_decision() -> None:
    page = (
        "POLITICA DE INVESTIMENTO: A CARTEIRA PODERA CONTER PRECATORIOS "
        "PRECATORIOS PRECATORIOS, EMPRESTIMOS CONSIGNADOS EMPRESTIMOS "
        "CONSIGNADOS EMPRESTIMOS CONSIGNADOS, CEDULAS DE PRODUTO RURAL "
        "CEDULAS DE PRODUTO RURAL CEDULAS DE PRODUTO RURAL E OPERACOES DE "
        "FOMENTO MERCANTIL FOMENTO MERCANTIL FOMENTO MERCANTIL"
    )
    decision = decide(_document(page), official_type="Outros")

    assert decision.decision_status == "aprovado"
    assert decision.tipo == "Outros"
    assert "Multicarteira" in decision.foco


def test_quota_feeder_is_flagged() -> None:
    page = (
        "O FUNDO DE INVESTIMENTO EM COTAS DE FUNDOS DE INVESTIMENTO EM DIREITOS "
        "CREDITORIOS APLICARA EM COTAS DE OUTROS FUNDOS"
    )
    assert detect_fic_fidc(_document(page))


def test_fold_text_removes_diacritics_and_collapses_whitespace() -> None:
    assert fold_text("  Direitos   Creditórios\n") == "DIREITOS CREDITORIOS"


@pytest.mark.skipif(not CONCLUSIONS.exists(), reason="conclusões ainda não geradas")
def test_published_conclusions_are_internally_consistent() -> None:
    frame = pd.read_csv(CONCLUSIONS, dtype=str, keep_default_na=False)

    assert not frame["cnpj_fundo"].duplicated().any()
    assert frame["decision_status"].isin(
        {"aprovado", "em_revisao", "pendente", "rejeitado"}
    ).all()
    #: Every CNPJ in the queue must carry a decision, and a pending one must
    #: always come with the documentary limitation that explains it.
    queue = pd.read_csv(
        CONCLUSIONS.parent / "industry_outros_reclassification_queue.csv",
        dtype=str,
        keep_default_na=False,
    )
    assert set(queue["cnpj_fundo"]) == set(frame["cnpj_fundo"])
    pending = frame[frame["decision_status"].eq("pendente")]
    assert pending.empty or pending["source_limitations"].str.len().gt(0).all()
    rejected = frame[frame["decision_status"].eq("rejeitado")]
    assert rejected.empty or rejected["perimeter_proposal"].str.len().gt(0).all()
    review = frame[frame["decision_status"].eq("em_revisao")]
    assert review.empty or review["manual_validation_reason"].str.len().gt(0).all()
    approved = frame[frame["decision_status"].eq("aprovado")]
    for row in approved.to_dict(orient="records"):
        assert valid_analytical_type_focus_pair(
            row["tipo_anbima_sugerido"], row["foco_anbima_sugerido"]
        ), row["cnpj_fundo"]
        assert row["tabela_ii_sugerida_documental"] in CVM_TABLE_II_CATEGORIES
        n1 = row["taxonomia_funcional_n1_sugerida"]
        assert row["taxonomia_funcional_n2_sugerida"] in FUNCTIONAL_TAXONOMY[n1]
        assert row["evidence_summary"], row["cnpj_fundo"]
        assert row["justificativa_curta"], row["cnpj_fundo"]
        assert row["confianca_documental"] in {"baixa", "media", "alta"}


@pytest.mark.skipif(not PENDING_CURATION.exists(), reason="curadoria não gerada")
def test_pending_top20_curation_closes_every_remaining_cnpj() -> None:
    frame = pd.read_csv(PENDING_CURATION, dtype=str, keep_default_na=False)

    assert len(frame) == 6
    assert not frame["cnpj_fundo"].duplicated().any()
    assert set(frame["decision_status"]) == {"aprovado", "em_revisao", "rejeitado"}
    for row in frame.to_dict(orient="records"):
        assert row["evidence_summary"]
        assert row["justificativa_curta"]
        assert row["documentos_lidos"]
        if row["decision_status"] in {"aprovado", "em_revisao"}:
            assert valid_analytical_type_focus_pair(
                row["tipo_anbima_sugerido"], row["foco_anbima_sugerido"]
            )
            n1 = row["taxonomia_funcional_n1_sugerida"]
            assert row["taxonomia_funcional_n2_sugerida"] in FUNCTIONAL_TAXONOMY[n1]
        else:
            assert row["perimeter_proposal"]
        if row["decision_status"] == "em_revisao":
            assert row["manual_validation_reason"]


def test_resolution_175_duty_boilerplate_does_not_create_a_precatorio_fund() -> None:
    page = (
        "OBRIGACOES DO ADMINISTRADOR: E) NO CASO DE CLASSE DESTINADA AO PUBLICO "
        "EM GERAL QUE ADQUIRA PRECATORIOS FEDERAIS: 1. SE O PRECATORIO PERMANECE "
        "NA ORDEM DE PAGAMENTO DA UNIAO, NOS TERMOS DO ARTIGO 27 DA RESOLUCAO "
        "CVM 175"
    )
    scores = score_families(_document(page))

    assert "precatorios" not in scores


def test_collection_contract_boilerplate_does_not_create_an_npl_fund() -> None:
    page = (
        "CONTRATO DE COBRANCA: O CONTRATO DE PRESTACAO DE SERVICOS DE COBRANCA "
        "DE DIREITOS DE CREDITO INADIMPLIDOS CELEBRADO ENTRE O FUNDO E O AGENTE "
        "DE COBRANCA"
    )
    scores = score_families(_document(page))

    assert "npl" not in scores


def test_the_eligibility_clause_still_creates_a_precatorio_fund() -> None:
    page = (
        "CRITERIOS DE ELEGIBILIDADE: A CLASSE PODERA ADQUIRIR DO CEDENTE "
        "DIREITOS CREDITORIOS ORIGINARIOS DE PRECATORIOS OU AINDA CREDITOS "
        "DECORRENTES DE RECEITAS OU DIVIDAS PUBLICAS DA UNIAO, ESTADOS, "
        "DISTRITO FEDERAL E MUNICIPIOS"
    )
    decision = decide(_document(page), official_type="Outros")

    assert decision.decision_status == "aprovado"
    assert decision.foco == "Poder Público"


def test_a_declared_anbima_classification_wins_over_the_vocabulary() -> None:
    page = (
        "PARA OS FINS DE CLASSIFICACAO ANBIMA, ESTA CLASSE E CLASSIFICADA COMO "
        "UM FUNDO DE INVESTIMENTO EM DIREITOS CREDITORIOS DO TIPO ANBIMA OUTROS "
        "- NON PERFORMING. A CARTEIRA PODE CONTER DUPLICATAS DUPLICATAS "
        "DUPLICATAS E VENDAS MERCANTIS VENDAS MERCANTIS VENDAS MERCANTIS."
    )
    decision = decide(_document(page), official_type="Agro, Indústria e Comércio")

    assert decision.decision_status == "aprovado"
    assert decision.confidence == "alta"
    assert (decision.tipo, decision.foco) == ("Outros", "Recuperação")


def test_a_declared_classification_is_ignored_when_type_and_focus_disagree() -> None:
    declaration = extract_anbima_declaration(
        _document("TIPO ANBIMA: FINANCEIRO - PODER PUBLICO")
    )

    assert declaration is None


def test_declared_segment_closes_a_fund_without_readable_documents() -> None:
    outcome = resolve_with_declared_segment(
        decision_status="pendente",
        family_scores="",
        declared_segment="Financeiro",
        declared_share=1.0,
        competence="2026-06",
    )

    assert outcome.resolved
    assert outcome.tipo == "Financeiro"
    assert outcome.tabela_ii == "Financeiro"


def test_declared_segment_breaks_a_tie_between_competing_families() -> None:
    outcome = resolve_with_declared_segment(
        decision_status="em_revisao",
        family_scores="agronegócio=20.0; crédito imobiliário=18.0",
        declared_segment="Agronegocio",
        declared_share=0.75,
        competence="2025-12",
    )

    assert outcome.resolved
    assert outcome.n2 == "Agro"


def test_declared_segment_never_touches_a_closed_decision() -> None:
    outcome = resolve_with_declared_segment(
        decision_status="aprovado",
        family_scores="agronegócio=20.0",
        declared_segment="Agronegocio",
        declared_share=1.0,
        competence="2025-12",
    )

    assert not outcome.resolved
