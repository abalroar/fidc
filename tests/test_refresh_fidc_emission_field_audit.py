from __future__ import annotations

import pandas as pd
import pytest

from scripts.build_fidc_revision_artifact_payload import EMISSION_FIELD_AUDIT_COLUMNS, _load_emission_field_audit
from scripts.refresh_fidc_emission_field_audit import FUND_BLOCK, OFFER_BLOCK, reconcile_emission_field_audit


def _fixtures() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    types = ("Fomento Mercantil", "Financeiro", "Agro, Indústria e Comércio", "Outros")
    funds, offers, ledger = [], [], []

    def audit_row(block, table, cnpj, emission, name, price):
        row = dict.fromkeys(EMISSION_FIELD_AUDIT_COLUMNS, "N/D")
        row.update(bloco=block, tabela=table, cnpj=cnpj, emissao_id=emission, fundo=name,
                   preco_por_tipo_cota=price, fonte_preco="https://example.test/documento/" + cnpj,
                   status="Valor documental preservado")
        return row

    for period in ("2025-12", "2026-08"):
        for type_index, category in enumerate(types):
            for rank in range(1, 16):
                cnpj = f"{type_index * 15 + rank:014d}"
                funds.append(dict(competencia=period, tipo_exibicao=category, rank_tipo=rank,
                                  cnpj_fundo=cnpj, denominacao=f"Fundo {cnpj}"))
                old_period = "2026-06" if period == "2026-08" else period
                ledger.append(audit_row(FUND_BLOCK, f"{category} · {old_period}", cnpj,
                                        "N/D — tabela no nível do fundo", f"Fundo {cnpj}",
                                        "R$ 200" if period == "2026-08" else "R$ 100"))
    for period_index, period in enumerate(("2023 FY", "2024 FY", "2025 FY", "2026 jan-ago")):
        for rank in range(1, 16):
            emission = str(period_index * 15 + rank)
            cnpj = f"{1000 + period_index * 15 + rank:014d}"
            offers.append(dict(period_label=period, rank=rank, offer_id=emission,
                               cnpj_emissor=cnpj, issuer_name=f"Emissor {cnpj}"))
            ledger.append(audit_row(OFFER_BLOCK, period, cnpj, emission, f"Emissor {cnpj}", "R$ 300"))
    return pd.DataFrame(ledger), pd.DataFrame(funds), pd.DataFrame(offers)


def _refresh(audit, funds, offers, **kwargs):
    return reconcile_emission_field_audit(audit, latest="2026-08", top20_taxonomy_review=funds,
                                        closed_offer_top15=offers, **kwargs)


def test_refresh_keeps_fund_evidence_and_offer_terms_and_still_passes_production_guard(tmp_path):
    audit, funds, offers = _fixtures()
    funds.loc[funds["competencia"].eq("2026-08"), "denominacao"] += " vigente"
    result, report = _refresh(audit, funds, offers)

    assert report["fundos_preservados_chave_exata"] == 60
    assert report["fundos_evidencia_cnpj_anterior"] == 60
    assert report["ofertas_preservadas_id_cnpj"] == 60
    assert result.loc[result["tabela"].str.endswith("2026-08"), "preco_por_tipo_cota"].eq("R$ 200").all()
    assert result.loc[result["tabela"].str.endswith("2025-12"), "preco_por_tipo_cota"].eq("R$ 100").all()
    assert result.loc[result["tabela"].str.endswith("2026-08"), "fundo"].str.endswith("vigente").all()
    path = tmp_path / "ledger.csv"
    result.to_csv(path, index=False)
    loaded = _load_emission_field_audit(path, latest="2026-08", top20_taxonomy_review=funds,
                                      closed_offer_top15=offers)
    assert len(loaded) == 180


def test_new_fund_and_new_emission_keep_nd_even_when_issuer_has_other_documented_emission():
    audit, funds, offers = _fixtures()
    current_fund = funds.index[funds["competencia"].eq("2026-08")][0]
    # This CNPJ has a documented offer but no fund-level documentary observation.
    new_cnpj = offers.iloc[0]["cnpj_emissor"]
    funds.loc[current_fund, "cnpj_fundo"] = new_cnpj
    offers.loc[0, "offer_id"] = "9999"
    result, report = _refresh(audit, funds, offers)

    new_fund = result[result["bloco"].eq(FUND_BLOCK) & result["cnpj"].eq(new_cnpj)].iloc[0]
    new_offer = result[result["emissao_id"].eq("9999")].iloc[0]
    for row in (new_fund, new_offer):
        assert row["preco_por_tipo_cota"] == "N/D"
        assert row["fonte_preco"] == "N/D"
        assert row["remuneracao_por_tipo_cota"] == "N/D"
    assert report["fundos_novos_nd"] == 1
    assert report["ofertas_novas_nd"] == 1


def test_fund_evidence_from_later_competence_does_not_backfill_historical_ranking():
    audit, funds, offers = _fixtures()
    future = audit["tabela"].str.endswith("2026-06")
    audit.loc[future, "tabela"] = audit.loc[future, "tabela"].str.replace("2026-06", "2026-09", regex=False)
    result, _ = _refresh(audit, funds, offers)
    assert result.loc[result["tabela"].str.endswith("2026-08"), "preco_por_tipo_cota"].eq("R$ 100").all()


def test_duplicate_existing_logical_observation_remains_error():
    audit, funds, offers = _fixtures()
    audit = pd.concat([audit, audit.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="chave duplicada"):
        _refresh(audit, funds, offers)


def test_ambiguous_fund_documentary_evidence_remains_error():
    audit, funds, offers = _fixtures()
    extra = audit[audit["tabela"].str.endswith("2026-06")].iloc[[0]].copy()
    extra["tabela"] = "Outro Tipo · 2026-06"
    extra["preco_por_tipo_cota"] = "R$ 777"
    audit = pd.concat([audit, extra], ignore_index=True)
    with pytest.raises(ValueError, match="evidência ambígua"):
        _refresh(audit, funds, offers)


def test_previous_history_restores_evidence_after_fund_reenters_ranking():
    audit, funds, offers = _fixtures()
    history = audit.copy()
    archived_cnpj = funds.iloc[0]["cnpj_fundo"]
    audit = audit[~(audit["bloco"].eq(FUND_BLOCK) & audit["cnpj"].eq(archived_cnpj))]
    result, _ = _refresh(audit, funds, offers, history=history)
    assert result.loc[result["bloco"].eq(FUND_BLOCK) & result["cnpj"].eq(archived_cnpj), "preco_por_tipo_cota"].tolist() == ["R$ 100", "R$ 200"]


def test_incomplete_current_ranking_is_rejected():
    audit, funds, offers = _fixtures()
    with pytest.raises(ValueError, match="oito tabelas"):
        _refresh(audit, funds.iloc[1:], offers)


def test_refresh_rolls_the_offer_and_fund_windows_without_copying_between_emissions():
    audit, funds, offers = _fixtures()
    replacements = {"2023 FY": "2024 FY", "2024 FY": "2025 FY", "2025 FY": "2026 FY", "2026 jan-ago": "2027 jan-mar"}
    offers["period_label"] = offers["period_label"].map(replacements)
    offer_rows = audit["bloco"].eq(OFFER_BLOCK)
    audit.loc[offer_rows, "tabela"] = audit.loc[offer_rows, "tabela"].map(replacements)
    funds["competencia"] = funds["competencia"].replace({"2025-12": "2026-12", "2026-08": "2027-03"})
    audit["tabela"] = audit["tabela"].str.replace("2025-12", "2026-12", regex=False)
    result, report = reconcile_emission_field_audit(
        audit, latest="2027-03", top20_taxonomy_review=funds, closed_offer_top15=offers,
    )
    assert len(result) == 180
    assert set(result.loc[result["bloco"].eq(OFFER_BLOCK), "tabela"]) == set(replacements.values())
    assert report["ofertas_preservadas_id_cnpj"] == 60
    assert result.loc[result["bloco"].eq(OFFER_BLOCK), "preco_por_tipo_cota"].eq("R$ 300").all()
