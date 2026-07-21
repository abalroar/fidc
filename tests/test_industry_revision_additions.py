from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.industry_revision_additions import (
    ACQUIRING_RECLASSIFIED_MIX_COLUMNS,
    BANK_COHORT_HISTORY_COLUMNS,
    INDEPENDENT_PROVIDER_HISTORY_COLUMNS,
    build_acquiring_reclassified_cvm_mix,
    build_fixed_bank_fidc_cohort_detail,
    build_fixed_bank_fidc_cohort_history,
    build_independent_provider_historical_ranking,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "industry_study"


def _ownership_curation() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "participant_pattern": r"(?i)\b(?:QI TECH|SINGULARE)\b",
                "normalized_group": "QI Tech",
                "bank_affiliated": False,
                "independent_reviewed": True,
                "ownership_status": "independent",
                "source_url": "https://example.com/qi",
                "as_of_date": "2026-07-20",
                "notes": "QI e Singulare consolidados",
            },
            {
                "participant_pattern": r"(?i)\bOLIVEIRA TRUST\b",
                "normalized_group": "Oliveira Trust",
                "bank_affiliated": False,
                "independent_reviewed": True,
                "ownership_status": "independent",
                "source_url": "https://example.com/oliveira",
                "as_of_date": "2026-07-20",
                "notes": "independente revisado",
            },
            {
                "participant_pattern": r"(?i)\b(?:ITAU|BANCO ALFA)\b",
                "normalized_group": "Itaú",
                "bank_affiliated": True,
                "independent_reviewed": False,
                "ownership_status": "bank_group",
                "source_url": "https://example.com/itau",
                "as_of_date": "2026-07-20",
                "notes": "grupo bancário",
            },
            {
                "participant_pattern": r"(?i)\bKANASTRA\b",
                "normalized_group": "Itaú",
                "bank_affiliated": True,
                "independent_reviewed": False,
                "ownership_status": "minority_affiliate_user_rule",
                "source_url": "https://example.com/kanastra",
                "as_of_date": "2026-07-20",
                "notes": "afiliação minoritária solicitada",
            },
        ]
    )


def _provider_history() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    values = {
        "2024-12": {
            "QI TECH": 100.0,
            "SINGULARE": 50.0,
            "OLIVEIRA TRUST": 120.0,
            "BANCO ALFA": 300.0,
            "KANASTRA": 60.0,
            "SEM CURADORIA": 80.0,
        },
        "2026-05": {
            "QI TECH": 200.0,
            "OLIVEIRA TRUST": 250.0,
            "BANCO ALFA": 300.0,
            "KANASTRA": 100.0,
            "SEM CURADORIA": 50.0,
        },
    }
    for period, participants in values.items():
        denominator = sum(participants.values())
        for participant, pl_brl in participants.items():
            rows.append(
                {
                    "competencia": period,
                    "papel": "administrador",
                    "participante": participant,
                    "rank_periodo": 0,
                    "pl_brl": pl_brl,
                    "share_pl": pl_brl / denominator,
                    "fundos": 1,
                    "denominador_pl_brl": denominator,
                    "fundos_universo": len(participants),
                    "fonte_prestador": "Informe Mensal",
                }
            )
    return pd.DataFrame(rows)


def test_independent_provider_ranking_consolidates_and_filters_before_reranking() -> None:
    result = build_independent_provider_historical_ranking(
        _provider_history(),
        _ownership_curation(),
        latest_period="2026-05",
        top_n=1,
    )

    assert tuple(result.columns) == INDEPENDENT_PROVIDER_HISTORY_COLUMNS
    assert set(result["participante"]) == {"QI Tech", "Oliveira Trust"}
    qi_2024 = result[
        result["participante"].eq("QI Tech")
        & result["competencia"].eq("2024-12")
    ].iloc[0]
    assert qi_2024["pl_brl"] == 150.0
    assert qi_2024["fundos"] == 2
    assert qi_2024["rank_independente"] == 1
    assert qi_2024["rank_geral"] == 2

    oliveira_2026 = result[
        result["participante"].eq("Oliveira Trust")
        & result["competencia"].eq("2026-05")
    ].iloc[0]
    assert oliveira_2026["rank_independente"] == 1
    assert oliveira_2026["rank_geral"] == 2
    assert oliveira_2026["selected_latest_top_n"]
    assert oliveira_2026["ordem_slide"] == 1
    assert not result.loc[result["participante"].eq("QI Tech"), "selected_latest_top_n"].any()
    assert "Itaú" not in set(result["participante"])
    assert "SEM CURADORIA" not in set(result["participante"])


def test_independent_provider_ranking_rejects_conflicting_group_flags() -> None:
    curation = _ownership_curation()
    conflict = curation.iloc[[0]].copy()
    conflict["bank_affiliated"] = True
    curation = pd.concat([curation, conflict], ignore_index=True)

    with pytest.raises(ValueError, match="não pode ser bancário"):
        build_independent_provider_historical_ranking(
            _provider_history(), curation
        )


def _bank_curation() -> pd.DataFrame:
    groups = ["BB", "BTG", "Bradesco", "Itau", "Santander"]
    return pd.DataFrame(
        [
            {
                "bank_group": group,
                "cnpj_root8": f"{index}" * 8,
                "source_reference": f"FIDCs.xlsx#{group}",
            }
            for index, group in enumerate(groups, start=1)
        ]
    )


def _cohort_fund_base() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for period in ("2024-12", "2025-12"):
        for index in range(1, 6):
            if period == "2025-12" and index == 1:
                continue
            rows.append(
                {
                    "competencia": period,
                    "cnpj_fundo": f"{index}" * 8 + "000001",
                    "pl": index * (10.0 if period == "2024-12" else 20.0),
                }
            )
    return pd.DataFrame(rows)


def test_fixed_bank_cohort_emits_each_bank_and_reconciled_total() -> None:
    result = build_fixed_bank_fidc_cohort_history(
        _cohort_fund_base(), _bank_curation()
    )

    assert tuple(result.columns) == BANK_COHORT_HISTORY_COLUMNS
    assert len(result) == 12
    total_2024 = result[
        result["competencia"].eq("2024-12") & result["is_total_5_banks"]
    ].iloc[0]
    assert total_2024["pl_brl"] == 150.0
    assert total_2024["fundos_observados"] == 5
    assert total_2024["cobertura_fundos"] == 1.0
    assert total_2024["raizes_cnpj_listadas"] == (
        "11111111;22222222;33333333;44444444;55555555"
    )
    assert total_2024["raizes_cnpj_observadas"] == (
        "11111111;22222222;33333333;44444444;55555555"
    )
    assert total_2024["publication_status"] == "complete_fixed_cohort"

    total_2025 = result[
        result["competencia"].eq("2025-12") & result["is_total_5_banks"]
    ].iloc[0]
    assert total_2025["pl_brl"] == 280.0
    assert total_2025["fundos_observados"] == 4
    assert total_2025["fundos_curados"] == 5
    assert total_2025["cobertura_fundos"] == 0.8
    assert total_2025["raizes_cnpj_nao_observadas"] == "11111111"
    assert total_2025["cnpjs_nao_observados"] == "11111111"
    assert total_2025["publication_status"] == "partial_fixed_cohort"


def test_fixed_bank_cohort_rejects_duplicate_monthly_fund() -> None:
    funds = _cohort_fund_base()
    funds = pd.concat([funds, funds.iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="duplicada por competência/CNPJ"):
        build_fixed_bank_fidc_cohort_history(funds, _bank_curation())


def test_fixed_bank_cohort_recovers_official_december_pl_once() -> None:
    curation = _bank_curation()
    target = curation["bank_group"].eq("BTG")
    curation.loc[target, "pl_override_competencia"] = "2025-12"
    curation.loc[target, "pl_override_brl"] = 7_918_754_073
    curation.loc[target, "pl_override_status"] = "official_recovered"
    curation.loc[target, "pl_override_display_suffix"] = "*"
    curation.loc[target, "pl_override_source_reference"] = (
        "Fundos.NET IME v2 id 1100733 | Fundos.NET DF id 1150673 p. 6"
    )
    funds = pd.DataFrame(
        [
            {
                "competencia": period,
                "cnpj_fundo": f"{index}" * 8 + "000001",
                "denominacao": f"FIDC {group}",
                "pl": (
                    0
                    if period == "2025-12" and group == "BTG"
                    else (8_269_231_438 if group == "BTG" else index * 100)
                ),
            }
            for period in ("2025-11", "2025-12")
            for index, group in enumerate(
                ["BB", "BTG", "Bradesco", "Itau", "Santander"], start=1
            )
        ]
    )

    history = build_fixed_bank_fidc_cohort_history(funds, curation)
    btg_december = history[
        history["competencia"].eq("2025-12")
        & history["bank_group"].eq("BTG")
    ].iloc[0]
    assert btg_december["pl_brl"] == 7_918_754_073
    assert btg_december["pl_brl_raw"] == 0
    assert bool(btg_december["pl_recovered_official"])
    assert btg_december["pl_display_suffix"] == "*"
    assert "1100733" in btg_december["pl_source_references"]
    assert "1150673" in btg_december["source_references"]

    total_december = history[
        history["competencia"].eq("2025-12")
        & history["is_total_5_banks"]
    ].iloc[0]
    assert total_december["pl_brl"] == 7_918_755_373
    assert total_december["pl_brl_raw"] == 1_300
    assert total_december["pl_display_suffix"] == "*"

    btg_november = history[
        history["competencia"].eq("2025-11")
        & history["bank_group"].eq("BTG")
    ].iloc[0]
    assert btg_november["pl_brl"] == 8_269_231_438
    assert not bool(btg_november["pl_recovered_official"])
    assert btg_november["pl_display_suffix"] == ""

    detail = build_fixed_bank_fidc_cohort_detail(
        funds, curation, periods=("2025-12",)
    )
    btg_detail = detail[detail["bank_group"].eq("BTG")].iloc[0]
    assert btg_detail["pl_brl"] == 7_918_754_073
    assert btg_detail["pl_brl_raw"] == 0
    assert bool(btg_detail["pl_reportado_zero"])
    assert bool(btg_detail["pl_recovered_official"])
    assert btg_detail["pl_display_suffix"] == "*"
    assert "1150673" in btg_detail["pl_source_reference"]


def test_fixed_bank_cohort_rejects_conflicting_positive_override() -> None:
    curation = _bank_curation()
    target = curation["bank_group"].eq("BTG")
    curation.loc[target, "pl_override_competencia"] = "2025-12"
    curation.loc[target, "pl_override_brl"] = 7_918_754_073
    curation.loc[target, "pl_override_status"] = "official_recovered"
    curation.loc[target, "pl_override_display_suffix"] = "*"
    curation.loc[target, "pl_override_source_reference"] = "Fundos.NET id 1150673"
    funds = _cohort_fund_base()

    with pytest.raises(ValueError, match="conflita com valor bruto positivo"):
        build_fixed_bank_fidc_cohort_history(funds, curation)


def _acquiring_curation() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cnpj14_digits": "11111111000001",
                "label": "Adquirente A",
                "source_reference": "FIDCs.xlsx#Adquirência!A1",
            },
            {
                "cnpj14_digits": "22222222000001",
                "label": "Adquirente B",
                "source_reference": "FIDCs.xlsx#Adquirência!A2",
            },
        ]
    )


def _acquiring_fund_base() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "competencia": "2025-12",
                "cnpj_fundo": "11111111000001",
                "pl": 100.0,
                "segmento_principal": "Financeiro",
                "is_fic_fidc": False,
            },
            {
                "competencia": "2025-12",
                "cnpj_fundo": "33333333000001",
                "pl": 200.0,
                "segmento_principal": "Financeiro",
                "is_fic_fidc": False,
            },
            {
                "competencia": "2026-05",
                "cnpj_fundo": "11111111000001",
                "pl": 100.0,
                "segmento_principal": "Financeiro",
                "is_fic_fidc": False,
            },
            {
                "competencia": "2026-05",
                "cnpj_fundo": "22222222000001",
                "pl": 50.0,
                "segmento_principal": "Cartão",
                "is_fic_fidc": False,
            },
            {
                "competencia": "2026-05",
                "cnpj_fundo": "33333333000001",
                "pl": 150.0,
                "segmento_principal": "Financeiro",
                "is_fic_fidc": False,
            },
            {
                "competencia": "2026-05",
                "cnpj_fundo": "44444444000001",
                "pl": 1_000.0,
                "segmento_principal": "Financeiro",
                "is_fic_fidc": True,
            },
        ]
    )


def test_acquiring_mix_moves_only_curated_cnpjs_and_preserves_denominator() -> None:
    result = build_acquiring_reclassified_cvm_mix(
        _acquiring_fund_base(),
        _acquiring_curation(),
        expected_curated_funds=2,
    )

    assert tuple(result.columns) == ACQUIRING_RECLASSIFIED_MIX_COLUMNS
    current = result[result["competencia"].eq("2026-05")].set_index(
        "categoria_cvm"
    )
    assert current.at["Financeiro", "pl_original_brl"] == 250.0
    assert current.at["Financeiro", "pl_reclassificado_brl"] == 150.0
    assert current.at["Cartão", "pl_original_brl"] == 50.0
    assert current.at["Cartão", "pl_reclassificado_brl"] == 0.0
    assert current.at["Adquirência", "pl_reclassificado_brl"] == 150.0
    assert current.at["Adquirência", "fundos_movidos_para_adquirencia"] == 2
    assert current.at["Adquirência", "pl_movido_para_adquirencia_brl"] == 150.0
    assert current.at["Adquirência", "denominador_pl_brl"] == 300.0
    assert current["share_original"].sum() == pytest.approx(1.0)
    assert current["share_reclassificado"].sum() == pytest.approx(1.0)
    assert set(
        current.at["Adquirência", "cnpjs_movidos_para_adquirencia"].split(";")
    ) == {"11111111000001", "22222222000001"}

    prior = result[result["competencia"].eq("2025-12")]
    assert prior["fundos_adquirencia_observados"].eq(1).all()
    assert prior["cobertura_cnpjs_curados"].eq(0.5).all()
    assert prior["cnpjs_curados_nao_observados"].eq("22222222000001").all()


def test_acquiring_mix_enforces_curated_count() -> None:
    with pytest.raises(ValueError, match="quantidade de FIDCs"):
        build_acquiring_reclassified_cvm_mix(
            _acquiring_fund_base(),
            _acquiring_curation(),
            expected_curated_funds=16,
        )


def test_repository_curations_have_the_expected_audited_universes() -> None:
    ownership = pd.read_csv(DATA_DIR / "provider_ownership_curation.csv")
    bank = pd.read_csv(DATA_DIR / "bank_fidc_curation.csv", dtype=str)
    acquiring = pd.read_csv(
        DATA_DIR / "acquiring_reclassification_curation.csv", dtype=str
    )
    card = pd.read_csv(DATA_DIR / "card_receivables_curation.csv", dtype=str)

    independent_groups = set(
        ownership.loc[ownership["independent_reviewed"], "normalized_group"]
    )
    assert len(independent_groups) == 11
    assert set(bank["bank_group"]) == {"BB", "BTG", "Bradesco", "Itau", "Santander"}
    assert bank["cnpj_root8"].nunique() == len(bank)
    btg_consignados = bank[bank["cnpj_root8"].eq("50906397")].iloc[0]
    assert btg_consignados["pl_override_competencia"] == "2025-12"
    assert int(btg_consignados["pl_override_brl"]) == 7_918_754_073
    assert btg_consignados["pl_override_status"] == "official_recovered"
    assert btg_consignados["pl_override_display_suffix"] == "*"
    assert "1100733" in btg_consignados["pl_override_source_reference"]
    assert "1150673" in btg_consignados["pl_override_source_reference"]
    assert acquiring["cnpj14_digits"].nunique() == 33
    assert len(acquiring) == 33
    assert {
        "50473039000102",
        "55471753000177",
        "63572282000111",
    }.issubset(set(acquiring["cnpj14_digits"]))
    assert len(card) == card["cnpj14_digits"].nunique() == 44
    assert card["status_curadoria"].value_counts().to_dict() == {
        "Incluído em Adquirência": 26,
        "Fora de Adquirência": 17,
        "Pendente": 1,
    }
    assert card["fonte_url"].str.startswith("http").all()
