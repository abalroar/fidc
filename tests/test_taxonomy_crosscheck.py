from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.taxonomy_crosscheck import (
    ACTION_BACKEND,
    ACTION_REVIEW,
    FINDING_COLUMNS,
    crosscheck_taxonomy,
    summarize,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "industry_study"


def _decision(**overrides: object) -> dict[str, object]:
    base = {
        "cnpj_fundo": "11111111000191",
        "denominacao_referencia": "FUNDO TESTE",
        "status": "aprovado",
        "tipo_analitico": "Financeiro",
        "foco_analitico": "Crédito Consignado",
        "tabela_ii_analitica": "Financeiro",
        "taxonomia_funcional_n1": "Crédito PF",
        "taxonomia_funcional_n2": "Consignado",
        "evidencia": "regulamento 1 p. 5: " + "cessão de contratos de consignado " * 6,
        "notas": "",
        "pl_max": 1e9,
        "competencias_afetadas": "2026-06",
    }
    base.update(overrides)
    return base


def _ledger(*decisions: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(list(decisions))


def test_a_coherent_decision_produces_no_finding() -> None:
    findings = crosscheck_taxonomy(_ledger(_decision()))

    assert findings.empty
    assert list(findings.columns) == list(FINDING_COLUMNS)


def test_a_focus_outside_its_type_vocabulary_is_caught() -> None:
    findings = crosscheck_taxonomy(
        _ledger(_decision(tipo_analitico="Fomento Mercantil", foco_analitico="Agronegócio"))
    )

    assert findings["regra"].tolist() == ["tipo_incompativel_com_foco"]
    assert findings.iloc[0]["acao_sugerida"] == ACTION_BACKEND


def test_a_table_ii_at_odds_with_the_functional_level_is_caught() -> None:
    findings = crosscheck_taxonomy(
        _ledger(
            _decision(tabela_ii_analitica="Ações judiciais", taxonomia_funcional_n1="Agro")
        )
    )

    assert "tabela_ii_incompativel_com_funcional" in set(findings["regra"])
    assert findings.iloc[0]["acao_sugerida"] == ACTION_REVIEW


def test_the_real_vocabulary_pairs_are_accepted() -> None:
    """The published base pairs these constantly; flagging them would be noise."""

    findings = crosscheck_taxonomy(
        _ledger(
            _decision(
                tipo_analitico="Outros",
                foco_analitico="Poder Público",
                tabela_ii_analitica="Ações judiciais",
                taxonomia_funcional_n1="Judicial/Precatórios/NPL",
                taxonomia_funcional_n2="Precatórios/direitos judiciais",
            )
        )
    )

    assert "tabela_ii_incompativel_com_funcional" not in set(findings["regra"])


def test_acquiring_with_issuer_risk_evidence_is_caught() -> None:
    findings = crosscheck_taxonomy(
        _ledger(
            _decision(
                tabela_ii_analitica="Adquirência",
                taxonomia_funcional_n1="Meios de Pagamento e Cartões",
                evidencia="regulamento p. 3: o risco final é do banco emissor " * 4,
            )
        )
    )

    assert "adquirencia_com_evidencia_de_emissor" in set(findings["regra"])


def test_issuer_classification_with_acquirer_evidence_is_caught() -> None:
    findings = crosscheck_taxonomy(
        _ledger(
            _decision(
                tabela_ii_analitica="Cartão de crédito",
                foco_analitico="Cartão de Crédito",
                taxonomia_funcional_n1="Meios de Pagamento e Cartões",
                evidencia="regulamento p. 3: recebíveis cedidos pela credenciadora " * 4,
            )
        )
    )

    assert "emissor_com_evidencia_de_credenciadora" in set(findings["regra"])


def test_bnpl_classified_as_acquiring_is_caught() -> None:
    findings = crosscheck_taxonomy(
        _ledger(
            _decision(
                tabela_ii_analitica="Adquirência",
                taxonomia_funcional_n1="Meios de Pagamento e Cartões",
                evidencia="regulamento p. 3: operações de BNPL ao consumidor final " * 4,
            )
        )
    )

    assert "bnpl_classificado_como_adquirencia" in set(findings["regra"])


def test_an_approval_without_enough_evidence_is_caught() -> None:
    findings = crosscheck_taxonomy(_ledger(_decision(evidencia="ok")))

    assert "aprovado_sem_evidencia_suficiente" in set(findings["regra"])


def test_the_classifiers_own_output_is_not_read_as_evidence() -> None:
    """The family tag and the score line repeat the conclusion, not the proof."""

    findings = crosscheck_taxonomy(
        _ledger(
            _decision(
                tabela_ii_analitica="Comercial",
                taxonomia_funcional_n1="Crédito PJ",
                evidencia=(
                    "regulamento 1 p. 5 [recebíveis comerciais / multissetorial]: "
                    + "cessão de duplicatas mercantis " * 6
                ),
                notas="Escores documentais: recebíveis comerciais / multissetorial=7.0.",
            )
        )
    )

    assert "multicarteira_com_classificacao_especifica" not in set(findings["regra"])


def test_a_diversified_portfolio_with_a_specific_segment_is_caught() -> None:
    findings = crosscheck_taxonomy(
        _ledger(
            _decision(
                tabela_ii_analitica="Comercial",
                taxonomia_funcional_n1="Crédito PJ",
                evidencia=(
                    "regulamento p. 8: a carteira é diversificada, com natureza e "
                    "características distintas entre os direitos creditórios cedidos "
                    "ao fundo ao longo de sua existência."
                ),
            )
        )
    )

    assert "multicarteira_com_classificacao_especifica" in set(findings["regra"])


def test_one_cnpj_with_two_classifications_is_caught() -> None:
    findings = crosscheck_taxonomy(
        _ledger(
            _decision(),
            _decision(tipo_analitico="Fomento Mercantil", foco_analitico="Fomento Mercantil"),
        )
    )

    assert "cnpj_com_classificacoes_divergentes" in set(findings["regra"])


def test_a_divergence_against_the_published_classification_is_caught() -> None:
    published = pd.DataFrame(
        [
            {
                "cnpj_fundo": "11111111000191",
                "tipo_analitico": "Outros",
                "foco_analitico": "Multicarteira Outros",
            }
        ]
    )

    findings = crosscheck_taxonomy(_ledger(_decision()), published=published)

    assert "divergencia_aprovada_versus_publicada" in set(findings["regra"])


def test_nothing_is_rewritten_only_reported() -> None:
    ledger = _ledger(_decision(evidencia="curto"))
    before = ledger.copy()

    crosscheck_taxonomy(ledger)

    pd.testing.assert_frame_equal(ledger, before)


def test_the_summary_counts_each_cnpj_once_for_pl() -> None:
    findings = crosscheck_taxonomy(
        _ledger(
            _decision(
                evidencia="curto",
                tipo_analitico="Fomento Mercantil",
                foco_analitico="Agronegócio",
            )
        )
    )
    report = summarize(findings)

    assert report.findings >= 2
    assert report.pl_involved_brl == 1e9


def test_the_published_crosscheck_is_well_formed() -> None:
    path = DATA_DIR / "industry_taxonomy_crosscheck.csv"
    if not path.exists():
        pytest.skip("cross-check ainda não materializado")
    findings = pd.read_csv(path, dtype=str, keep_default_na=False)
    if findings.empty:
        return

    assert set(findings.columns) == set(FINDING_COLUMNS)
    assert findings["cnpj_fundo"].str.fullmatch(r"\d{14}").all()
    assert findings["motivo"].str.len().gt(0).all()
    assert findings["acao_sugerida"].str.len().gt(0).all()
