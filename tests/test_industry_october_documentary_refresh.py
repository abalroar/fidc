"""Competence-aware documentary selection and the exact October additions."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from services.emission_field_enrichment import (
    DOCUMENT_CUTOFF, _select_document_fields, enrich_emission_field_audit, is_missing,
)

SANTANDER = "67148005000137"
ATLANTIS = "63977188000142"
DATA_DIR = Path(os.environ.get("FIDC_OCTOBER_TEST_DATA_DIR", Path(__file__).resolve().parents[1] / "data" / "industry_study"))


def _audit(cnpj=SANTANDER, period="2026-10", **values):
    row = dict(bloco="slides 10–17", tabela=f"Outros · {period}", cnpj=cnpj,
               emissao_id="N/D", fundo="FIDC", status="N/D")
    row.update({key: "N/D" for key in ("originador", "cedente", "subordinacao_minima",
        "preco_por_tipo_cota", "remuneracao_por_tipo_cota", "sacado",
        "fonte_originador_cedente", "fonte_subordinacao", "fonte_preco", "fonte_remuneracao", "fonte_sacado")})
    row.update(values)
    return row


def _evidence(date="2026-10-13", **values):
    row = dict(cnpj=SANTANDER, field="originador", value="SANTANDER SOCIEDADE DE CRÉDITO, FINANCIAMENTO E INVESTIMENTO S.A. (07.707.650/0001-10)",
        source_kind="regulamento", source_id="1359650", document_class="regulamento",
        document_date=date, source_path="", source_url="https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id=1359650&cvm=true",
        page="19–20; 83–84", status="encontrado_explicito", confidence=1.0,
        excerpt="Emitente concede, analisa e desembolsa os créditos.", nature="originação funcional; rótulo literal Emitente")
    row.update(values)
    return row


def _enrich(rows, evidence, triage=None):
    return enrich_emission_field_audit(pd.DataFrame(rows), cedent_triage=pd.DataFrame() if triage is None else triage,
                                     documentary_evidence=(pd.DataFrame(evidence),))


def test_october_source_is_accepted_only_in_its_own_month_and_later():
    rows = [_audit(period=p) for p in ("2025-12", "2026-06", "2026-09", "2026-10")]
    result = _enrich(rows, [_evidence()])
    assert result.originador.iloc[:3].map(is_missing).all()
    assert "07.707.650/0001-10" in result.originador.iloc[3]
    assert result.cedente.map(is_missing).all()
    assert _select_document_fields(pd.DataFrame([_evidence()])) == {}
    assert (SANTANDER, "originador") in _select_document_fields(pd.DataFrame([_evidence()]), cutoff=pd.Timestamp("2026-10-31"))


def test_november_document_cannot_enter_october_even_with_priority_and_confidence():
    row = _evidence(date="2026-11-01", source_kind="curadoria_humana_documental", source_id="future")
    assert is_missing(_enrich([_audit()], [row]).iloc[0].originador)
    accepted = _enrich([_audit(period="2026-11")], [row])
    assert not is_missing(accepted.iloc[0].originador)


def test_approved_june_window_is_preserved_for_legacy_tables():
    rows = [_audit(period=p) for p in ("2023-12", "2025-12", "2026-06")]
    result = _enrich(rows, [_evidence(date="2026-06-22")])
    assert result.originador.str.contains("07.707.650/0001-10", regex=False).all()
    assert DOCUMENT_CUTOFF == pd.Timestamp("2026-06-30")


def test_existing_supported_originator_and_minimum_are_not_overwritten():
    row = _audit(originador="EMPRESA ORIGINAL S.A.", subordinacao_minima="Jr. 30%", fonte_originador_cedente="regulamento · documento old · 2026-06-01")
    result = _enrich([row], [_evidence(), _evidence(field="minimo_junior", value="50%")]).iloc[0]
    assert result.originador == "EMPRESA ORIGINAL S.A."
    assert result.subordinacao_minima == "Jr. 30%"
    assert "old" in result.fonte_originador


def test_legal_cedent_source_uses_actual_adapter_competence_and_preserves_legacy_default():
    triage = pd.DataFrame([dict(cnpj_fundo=SANTANDER, cedente_declarado_flag="Sim", cedente_razao_social_consolidada="CEDENTE DECLARADO S.A.", competencia_cedente="2026-10")])
    result = _enrich([_audit()], [], triage).iloc[0]
    assert "2026-10" in result.fonte_cedente and "jun/26" not in result.fonte_cedente
    assert "cedente legal declarado" in result.fonte_cedente
    legacy = _enrich([_audit()], [], triage.drop(columns="competencia_cedente")).iloc[0]
    assert "jun/26" in legacy.fonte_cedente
    invalid = pd.concat([triage, triage.assign(competencia_cedente="2026-09")])
    with pytest.raises(ValueError, match="competência válida"):
        _enrich([_audit()], [], invalid)


def _accepted_additions():
    path = DATA_DIR / "emission_field_document_audit" / "emission_field_document_evidence.csv.gz"
    frame = pd.read_csv(path, dtype={"cnpj": str}, keep_default_na=False)
    return frame[frame.cnpj.isin([SANTANDER, ATLANTIS]) & frame.source_id.astype(str).isin(["1359650", "1226689"])]


def test_exact_primary_additions_reach_real_october_selector_with_other_roles_missing():
    evidence = _accepted_additions()
    assert len(evidence) == 2
    santander = evidence[evidence.cnpj.eq(SANTANDER)].iloc[0]
    assert santander.field == "originador" and santander.document_date == "2026-10-13"
    assert "07.707.650/0001-10" in santander.value
    assert "Emitente" in santander.nature
    atlantis = evidence[evidence.cnpj.eq(ATLANTIS)].iloc[0]
    assert atlantis.field == "minimo_junior" and atlantis.document_date == "2026-06-22"
    assert atlantis.value == "50%"
    result = _enrich([_audit(), _audit(cnpj=ATLANTIS)], evidence.to_dict("records"))
    assert "07.707.650/0001-10" in result.iloc[0].originador
    assert is_missing(result.iloc[0].cedente)
    assert result.iloc[1].subordinacao_minima == "Jr. 50%"
    for field in ("originador", "cedente", "sacado", "remuneracao_por_tipo_cota"):
        assert is_missing(result.iloc[1][field])
    assert "1226689" in result.iloc[1].fonte_subordinacao
    assert "2026-06-22" in result.iloc[1].fonte_subordinacao
    historical = _enrich([_audit(period="2026-09")], evidence.to_dict("records")).iloc[0]
    assert is_missing(historical.originador)


def test_october_review_records_reported_and_contractual_types_without_a_waiver():
    review = json.loads((DATA_DIR / "industry_top15_originator_cohort_review_202610.json").read_text())
    assert review["specific_waiver"] is None
    assert review["competencia"] == "2026-10"
    contradiction = review["classification_contradiction"]
    assert contradiction["cnpj"] == SANTANDER
    assert contradiction["cvm_reported_segment"] == "Setor publico"
    assert contradiction["preserved_display_type"] == "Outros"
    assert contradiction["contractual_type"] == "Financeiro"
    assert contradiction["contractual_focus"] == "Financiamento de Veículos"
    assert contradiction["classification_changed"] is False
