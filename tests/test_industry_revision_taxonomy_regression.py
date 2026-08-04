from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import scripts.publish_fidc_revision_bundle as revision_publisher
import services.industry_revision_analysis as revision_analysis
from services.industry_taxonomy_review import TAXONOMY_REVIEW_COLUMNS


PAN_AUTO_CNPJ = "65473848000183"
FOCUS_MOVE_CNPJ = "22222222000182"


def _approved_action(
    *,
    cnpj_fundo: str,
    denominacao: str,
    tipo: str,
    foco: str,
) -> pd.DataFrame:
    row = {column: "" for column in TAXONOMY_REVIEW_COLUMNS}
    row.update(
        {
            "cnpj_fundo": cnpj_fundo,
            "denominacao_referencia": denominacao,
            "status": "aprovado",
            "tipo_analitico": tipo,
            "foco_analitico": foco,
            "tabela_ii_analitica": "N/D",
            "taxonomia_funcional_n1": "Crédito PJ",
            "taxonomia_funcional_n2": "Recebíveis comerciais/multissetorial",
            "confianca": "alta",
            "documento_id": f"doc-{cnpj_fundo}",
            "fonte_documental": "auditoria de classificação jun/26",
            "documento_data": "2026-06-30",
            "pagina_clausula": "de-para auditado",
            "evidencia": "decisão auditada por CNPJ",
            "responsavel": "auditoria",
            "competencia_inicio": "2026-06",
            "updated_at_utc": "2026-08-04T12:00:00+00:00",
        }
    )
    return pd.DataFrame([row], columns=list(TAXONOMY_REVIEW_COLUMNS))


def _fund_base() -> pd.DataFrame:
    def row(
        cnpj_fundo: str,
        denominacao: str,
        pl: float,
        tipo: str,
        foco: str,
    ) -> dict[str, object]:
        return {
            "competencia": "2026-06",
            "cnpj_fundo": cnpj_fundo,
            "denominacao": denominacao,
            "pl": pl,
            "is_fic_fidc": False,
            "anbima_tipo": tipo,
            "anbima_foco": foco,
            "admin_nome": "Administrador Teste",
            "admin_cnpj": "12345678000190",
            "gestor_nome": "Gestor Teste",
            "gestor_cnpj": "22345678000190",
            "custodiante_nome": "Custodiante Teste",
            "custodiante_cnpj": "32345678000190",
        }

    return pd.DataFrame(
        [
            row(
                PAN_AUTO_CNPJ,
                "PAN AUTO FIDC",
                100.0,
                "Agro, Indústria e Comércio",
                "Recebíveis Comerciais",
            ),
            row(
                "11111111000191",
                "FIDC AGRO PAR",
                40.0,
                "Agro, Indústria e Comércio",
                "Recebíveis Comerciais",
            ),
            row(
                FOCUS_MOVE_CNPJ,
                "FIDC OUTROS RECLASSIFICADO",
                30.0,
                "Outros",
                "Poder Público",
            ),
            row(
                "33333333000173",
                "FIDC PODER PÚBLICO PAR",
                20.0,
                "Outros",
                "Poder Público",
            ),
        ]
    )


def _patch_non_taxonomy_branches(
    monkeypatch: pytest.MonkeyPatch,
    fund_base: pd.DataFrame,
) -> None:
    empty = lambda *args, **kwargs: pd.DataFrame()  # noqa: E731
    pair = lambda *args, **kwargs: (pd.DataFrame(), pd.DataFrame())  # noqa: E731
    triple = lambda *args, **kwargs: (  # noqa: E731
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
    )
    quadruple = lambda *args, **kwargs: (  # noqa: E731
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
    )

    monkeypatch.setattr(
        revision_analysis,
        "build_base_by_vehicle",
        lambda _vehicle_monthly: pd.DataFrame({"sentinela": [1]}),
    )
    monkeypatch.setattr(
        revision_analysis,
        "overlay_raw_source_presence",
        lambda base, _raw: base,
    )
    monkeypatch.setattr(revision_analysis, "build_delinquency_qa", empty)
    monkeypatch.setattr(revision_analysis, "build_delinquency_cases", empty)
    monkeypatch.setattr(
        revision_analysis,
        "build_receivables_reconciliation",
        pair,
    )
    monkeypatch.setattr(revision_analysis, "build_break_bridge", pair)
    monkeypatch.setattr(revision_analysis, "build_reconciliation", empty)
    monkeypatch.setattr(
        revision_analysis,
        "build_fund_base",
        lambda *args, **kwargs: fund_base.copy(),
    )
    monkeypatch.setattr(
        revision_analysis,
        "build_single_receivable_delinquency",
        pair,
    )
    monkeypatch.setattr(
        revision_analysis,
        "build_frozen_single_receivable_history",
        triple,
    )
    monkeypatch.setattr(
        revision_analysis,
        "build_frozen_cohort_revision_audit",
        triple,
    )
    monkeypatch.setattr(revision_analysis, "build_delinquency_dispersion", pair)
    monkeypatch.setattr(
        revision_analysis,
        "build_market_share_scope_summary",
        empty,
    )
    monkeypatch.setattr(
        revision_analysis,
        "build_provider_historical_ranking",
        empty,
    )
    monkeypatch.setattr(
        revision_analysis,
        "build_classification_coverage",
        empty,
    )
    monkeypatch.setattr(
        revision_analysis,
        "build_provider_transition_flows",
        quadruple,
    )
    monkeypatch.setattr(revision_analysis, "build_reag_admin_cohort", triple)
    monkeypatch.setattr(
        revision_analysis,
        "build_provider_leadership_attribution",
        triple,
    )
    monkeypatch.setattr(
        revision_analysis,
        "build_btg_provider_ex_controlled_scenario",
        empty,
    )


def _subtype_denominator(
    market: pd.DataFrame,
    *,
    tipo: str,
    foco: str,
) -> float:
    values = market.loc[
        market["papel"].eq("administrador")
        & market["tipo_anbima"].eq(tipo)
        & market["foco_anbima"].eq(foco),
        "denominador_publicacao_pl_positivo_brl",
    ].dropna()
    assert not values.empty
    assert values.nunique() == 1
    return float(values.iloc[0])


def test_revision_outputs_apply_audited_taxonomy_before_rankings_and_market_share(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fund_base = _fund_base()
    _patch_non_taxonomy_branches(monkeypatch, fund_base)
    actions = pd.concat(
        [
            _approved_action(
                cnpj_fundo=PAN_AUTO_CNPJ,
                denominacao="PAN AUTO FIDC",
                tipo="Outros",
                foco="Multicedente/Multissacado",
            ),
            _approved_action(
                cnpj_fundo=FOCUS_MOVE_CNPJ,
                denominacao="FIDC OUTROS RECLASSIFICADO",
                tipo="Outros",
                foco="Multicarteira Outros",
            ),
        ],
        ignore_index=True,
    )

    baseline = revision_analysis.build_revision_outputs(
        vehicle_monthly=pd.DataFrame(),
        latest_complete="2026-06",
    )
    audited = revision_analysis.build_revision_outputs(
        vehicle_monthly=pd.DataFrame(),
        taxonomy_review_actions=actions,
        latest_complete="2026-06",
    )

    baseline_pan = baseline.top20_fidcs.loc[
        baseline.top20_fidcs["cnpj_fundo"].eq(PAN_AUTO_CNPJ)
    ].iloc[0]
    audited_pan = audited.top20_fidcs.loc[
        audited.top20_fidcs["cnpj_fundo"].eq(PAN_AUTO_CNPJ)
    ].iloc[0]
    audited_pan_base = audited.fund_base.loc[
        audited.fund_base["cnpj_fundo"].eq(PAN_AUTO_CNPJ)
    ].iloc[0]

    assert baseline_pan["anbima_tipo"] == "Agro, Indústria e Comércio"
    assert audited_pan["anbima_tipo"] == "Outros"
    assert audited_pan["anbima_tipo_oficial"] == "Agro, Indústria e Comércio"
    assert audited_pan["anbima_foco_oficial"] == "Recebíveis Comerciais"
    assert audited_pan_base["anbima_tipo_curado"] == "Outros"
    assert audited_pan_base["anbima_foco_curado"] == "Multicedente/Multissacado"
    assert bool(audited_pan_base["taxonomy_review_applied"])
    assert PAN_AUTO_CNPJ not in set(baseline.top20_outros["cnpj_fundo"])
    assert PAN_AUTO_CNPJ in set(audited.top20_outros["cnpj_fundo"])

    assert _subtype_denominator(
        baseline.market_share_subtype,
        tipo="Agro, Indústria e Comércio",
        foco="Recebíveis Comerciais",
    ) == pytest.approx(140.0)
    assert _subtype_denominator(
        audited.market_share_subtype,
        tipo="Agro, Indústria e Comércio",
        foco="Recebíveis Comerciais",
    ) == pytest.approx(40.0)
    assert _subtype_denominator(
        baseline.market_share_subtype,
        tipo="Outros",
        foco="Poder Público",
    ) == pytest.approx(50.0)
    assert _subtype_denominator(
        audited.market_share_subtype,
        tipo="Outros",
        foco="Poder Público",
    ) == pytest.approx(20.0)
    assert _subtype_denominator(
        audited.market_share_subtype,
        tipo="Outros",
        foco="Multicarteira Outros",
    ) == pytest.approx(30.0)


def test_publisher_rebuilds_issuance_taxonomy_before_input_hash_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class HashCaptureReached(RuntimeError):
        pass

    monkeypatch.setattr(
        revision_publisher,
        "_validate_input_workbook",
        lambda _path: None,
    )
    monkeypatch.setattr(
        revision_publisher,
        "validate_fic_detection_audit_provenance",
        lambda _path: None,
    )

    def build_taxonomy(_data_dir: Path):
        calls.append("build_issuance_taxonomy")
        return pd.DataFrame(), {}

    def write_taxonomy(_frame: pd.DataFrame, _data_dir: Path) -> None:
        calls.append("write_issuance_taxonomy")

    def capture_hashes(**_kwargs: object) -> dict[str, str]:
        calls.append("collect_input_hashes")
        raise HashCaptureReached

    monkeypatch.setattr(
        revision_publisher,
        "build_issuance_taxonomy",
        build_taxonomy,
    )
    monkeypatch.setattr(
        revision_publisher,
        "write_issuance_taxonomy",
        write_taxonomy,
    )
    monkeypatch.setattr(
        revision_publisher,
        "collect_input_hashes",
        capture_hashes,
    )

    with pytest.raises(HashCaptureReached):
        revision_publisher.publish_revision_bundle(
            data_dir=tmp_path / "data",
            publish_dir=tmp_path / "published",
            curation_path=tmp_path / "curation.csv",
            input_workbook=tmp_path / "input.xlsx",
            latest_complete="2026-06",
        )

    assert calls == [
        "build_issuance_taxonomy",
        "write_issuance_taxonomy",
        "collect_input_hashes",
    ]
