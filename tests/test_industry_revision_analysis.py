from __future__ import annotations

import math

import pandas as pd
import pytest

from scripts.build_fidc_industry_study import field_reported
from scripts.build_fidc_revision_artifact_payload import (
    _atlantico_payload,
    _holder_distribution,
    _holder_distribution_history,
    _provider_leadership_payload,
    _provider_concentration_history,
    _read_optional,
    _receivables_history,
    _type_mix_history,
)
from services.industry_anbima import ANBIMA_FOCUS_BY_TYPE
from services.industry_revision_analysis import (
    BTG_CONTROLLED_FIDCS,
    MARKET_SHARE_EXCLUDED_FUNDS,
    TABLE_II_RECEIVABLE_COLUMNS,
    build_base_by_vehicle,
    build_btg_controlled_reconciliation,
    build_break_bridge,
    build_classification_coverage,
    build_delinquency_qa,
    build_frozen_single_receivable_history,
    build_market_share_by_subtype,
    build_market_share_scope_summary,
    build_provider_historical_ranking,
    build_provider_leadership_attribution,
    build_provider_transition_flows,
    build_reag_admin_cohort,
    build_reconciliation,
    build_top20_and_monostructure,
)


def _vehicle_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "competencia": "2026-05",
                "cnpj": "1",
                "cnpj_fundo": "10",
                "denominacao": "A",
                "pl": 100.0,
                "carteira_dc": 50.0,
                "dc_inadimplentes": 80.0,
                "reports_tab_i": True,
                "reports_carteira_dc": True,
                "reports_dc_inadimplentes": True,
                "is_np": False,
            },
            {
                "competencia": "2026-05",
                "cnpj": "2",
                "cnpj_fundo": "10",
                "denominacao": "A - CLASSE 2",
                "pl": 20.0,
                "carteira_dc": 10.0,
                "dc_inadimplentes": 0.0,
                "reports_tab_i": True,
                "reports_carteira_dc": True,
                "reports_dc_inadimplentes": True,
                "is_np": False,
            },
            {
                "competencia": "2026-05",
                "cnpj": "3",
                "cnpj_fundo": "30",
                "denominacao": "B",
                "pl": 80.0,
                "carteira_dc": 40.0,
                "dc_inadimplentes": 0.0,
                "reports_tab_i": True,
                "reports_carteira_dc": True,
                "reports_dc_inadimplentes": False,
                "is_np": False,
            },
        ]
    )


def test_source_presence_distinguishes_reported_zero_from_empty_cell() -> None:
    raw = pd.DataFrame({"field": ["0", "", "  ", "12.5"]})

    assert field_reported(raw, ("field",)).tolist() == [True, False, False, True]


def test_holder_distribution_percentages_close_at_one_for_funds_and_pl() -> None:
    vehicles = pd.DataFrame(
        [
            {"competencia": "2026-05", "cnpj": "1", "cnpj_fundo": "1", "pl": 250_000_000, "cotistas": 0, "is_fic_fidc": False},
            {"competencia": "2026-05", "cnpj": "2", "cnpj_fundo": "2", "pl": 300_000_000, "cotistas": 1, "is_fic_fidc": False},
            {"competencia": "2026-05", "cnpj": "3", "cnpj_fundo": "3", "pl": 400_000_000, "cotistas": 2, "is_fic_fidc": False},
            {"competencia": "2026-05", "cnpj": "4", "cnpj_fundo": "4", "pl": 500_000_000, "cotistas": 8, "is_fic_fidc": False},
            {"competencia": "2026-05", "cnpj": "5", "cnpj_fundo": "5", "pl": 600_000_000, "cotistas": 25, "is_fic_fidc": False},
            {"competencia": "2026-05", "cnpj": "6", "cnpj_fundo": "6", "pl": 700_000_000, "cotistas": 100, "is_fic_fidc": False},
            {"competencia": "2026-05", "cnpj": "7", "cnpj_fundo": "7", "pl": 199_999_999, "cotistas": 1, "is_fic_fidc": False},
            {"competencia": "2026-05", "cnpj": "8", "cnpj_fundo": "8", "pl": 900_000_000, "cotistas": 1, "is_fic_fidc": True},
            {"competencia": "2026-05", "cnpj": "9", "cnpj_fundo": "9", "pl": 350_000_000, "cotistas": None, "is_fic_fidc": False},
        ]
    )

    result = _holder_distribution(vehicles, "2026-05")

    assert result["bucket"].astype(str).tolist() == ["0", "1", "2–3", "4–10", "11–50", "51+"]
    assert result["fundos"].sum() == 6
    assert math.isclose(result["pl"].sum(), 2_750_000_000.0)
    assert math.isclose(result["share_fundos"].sum(), 1.0, abs_tol=1e-12)
    assert math.isclose(result["share_pl"].sum(), 1.0, abs_tol=1e-12)
    assert result["universo_fundos"].eq(6).all()
    assert result["universo_pl"].eq(2_750_000_000.0).all()


def test_holder_distribution_rejects_negative_accounts_instead_of_bucket_zero() -> None:
    vehicles = pd.DataFrame(
        [
            {
                "competencia": "2026-05",
                "cnpj": "1",
                "cnpj_fundo": "1",
                "pl": 250_000_000,
                "cotistas": -1,
                "is_fic_fidc": False,
            }
        ]
    )

    with pytest.raises(ValueError, match="quantidade negativa"):
        _holder_distribution(vehicles, "2026-05")


def test_slides_5_to_7_histories_use_both_snapshots_and_close_at_one() -> None:
    vehicle_rows: list[dict[str, object]] = []
    buckets = [0, 1, 2, 8, 25, 100]
    for period, multiplier in (("2023-12", 1.0), ("2026-05", 2.0)):
        for index, accounts in enumerate(buckets, start=1):
            vehicle_rows.append(
                {
                    "competencia": period,
                    "cnpj": f"{period}-{index}",
                    "cnpj_fundo": f"{period}-{index}",
                    "pl": (200_000_000 + index * 10_000_000) * multiplier,
                    "cotistas": accounts,
                    "is_fic_fidc": False,
                }
            )
    holder, holder_meta = _holder_distribution_history(
        pd.DataFrame(vehicle_rows), ["2023-12", "2026-05"]
    )

    assert set(holder["competencia"]) == {"2023-12", "2026-05"}
    assert set(holder_meta["competencia"]) == {"2023-12", "2026-05"}
    assert holder.groupby("competencia")["share_fundos"].sum().eq(1.0).all()
    assert holder.groupby("competencia")["share_pl"].sum().map(
        lambda value: math.isclose(value, 1.0, abs_tol=1e-12)
    ).all()

    funds = pd.DataFrame(
        [
            {
                "competencia": period,
                "cnpj_fundo": f"{period}-{index}",
                "pl": pl,
                "is_fic_fidc": False,
                "anbima_tipo": anbima_type,
                "classification_tier": tier,
            }
            for period in ("2023-12", "2026-05")
            for index, (anbima_type, pl, tier) in enumerate(
                [
                    ("Financeiro", 60.0, "oficial_anbima"),
                    ("Outros", 30.0, "evidencia_publicada"),
                    # Um rótulo cadastral atual de FIC não pode retirar do
                    # denominador um veículo que era ex-FIC na competência.
                    ("FIC-FIDC", 10.0, "nao_disponivel"),
                ],
                start=1,
            )
        ]
    )
    type_mix, coverage = _type_mix_history(funds, ["2023-12", "2026-05"])

    assert set(type_mix["competencia"]) == {"2023-12", "2026-05"}
    assert type_mix.groupby("competencia")["share"].sum().map(
        lambda value: math.isclose(value, 1.0, abs_tol=1e-12)
    ).all()
    assert coverage.groupby("competencia")["share"].sum().map(
        lambda value: math.isclose(value, 1.0, abs_tol=1e-12)
    ).all()
    assert set(type_mix.loc[type_mix["anbima_tipo"].eq("N/D"), "competencia"]) == {
        "2023-12",
        "2026-05",
    }

    segments = pd.DataFrame(
        [
            {
                "competencia": period,
                "nivel": "top",
                "segmento": segment,
                "valor": value,
            }
            for period in ("2023-12", "2026-05")
            for segment, value in (("Financeiro", 70.0), ("Comercial", 30.0))
        ]
    )
    monthly = pd.DataFrame(
        [
            {"competencia": "2023-12", "carteira_dc": 90.0},
            {"competencia": "2026-05", "carteira_dc": 95.0},
        ]
    )
    receivables, receivables_meta = _receivables_history(
        segments, monthly, ["2023-12", "2026-05"]
    )

    assert set(receivables["competencia"]) == {"2023-12", "2026-05"}
    assert set(receivables_meta["competencia"]) == {"2023-12", "2026-05"}
    assert receivables.groupby("competencia")["share_reported"].sum().map(
        lambda value: math.isclose(value, 1.0, abs_tol=1e-12)
    ).all()


def test_provider_top5_and_top10_keep_missing_provider_in_denominator() -> None:
    rows: list[dict[str, object]] = []
    for period in ("2025-12", "2026-05"):
        for index in range(12):
            missing = index == 11
            rows.append(
                {
                    "competencia": period,
                    "cnpj_fundo": f"{period}-{index}",
                    "pl": 10.0,
                    "admin_nome": "" if missing else f"ADMIN {index}",
                    "admin_cnpj": "" if missing else f"1{index:03d}",
                    "gestor_nome": "" if missing else f"GESTOR {index}",
                    "gestor_cnpj": "" if missing else f"2{index:03d}",
                    "custodiante_nome": "" if missing else f"CUST {index}",
                    "custodiante_cnpj": "" if missing else f"3{index:03d}",
                }
            )

    result = _provider_concentration_history(
        pd.DataFrame(rows), ["2025-12", "2026-05"]
    )

    assert {(row["competencia"], row["papel"]) for row in result} == {
        (period, role)
        for period in ("2025-12", "2026-05")
        for role in ("administrador", "gestor", "custodiante")
    }
    for row in result:
        assert row["total_pl"] == 120.0
        assert row["missing_pl"] == 10.0
        assert row["missing_share"] == pytest.approx(10.0 / 120.0)
        assert row["coverage_pl"] == pytest.approx(110.0 / 120.0)
        assert row["top5_share"] == pytest.approx(50.0 / 120.0)
        assert row["top10_share"] == pytest.approx(100.0 / 120.0)
        assert row["top10_share"] < 100.0 / 110.0


def test_atlantico_payload_keeps_five_checkpoints_and_june_july_bridge(
    tmp_path,
) -> None:
    (tmp_path / "atlantico_curadoria.json").write_text(
        '{"cnpj":"09.194.841/0001-51","estrategia":"Aquisição de NPLs"}',
        encoding="utf-8",
    )
    periods = ["2023-12", "2024-06", "2024-07", "2025-12", "2026-05"]
    rows = []
    for index, period in enumerate(periods):
        raw = 16_000.0 if period == "2024-06" else 100.0 + index
        portfolio = 40.0 if period == "2024-06" else 120.0
        rows.append(
            {
                "competencia": period,
                "cnpj_fundo": "09194841000151",
                "denominacao": "ATLÂNTICO FIDC",
                "pl": 140.0,
                "carteira_dc": portfolio,
                "dc_inadimplentes": raw,
                "dc_inadimplentes_ajustado_recalculado": min(raw, portfolio),
                "reports_inad_acima_360d": True,
                "inad_acima_360d": min(raw, portfolio),
                "inad_maior_1080d": min(raw, portfolio) * 0.9,
                "admin_nome": "ID CORRETORA",
                "gestor_nome": "HYPERION",
                "custodiante_nome": "ID CORRETORA",
                "is_np": False,
            }
        )

    profile, history = _atlantico_payload(
        pd.DataFrame(rows), tmp_path, "2026-05"
    )

    assert [row["competencia"] for row in history] == periods
    assert profile["snapshot"]["competencia"] == "2026-05"
    assert profile["snapshot"]["inadimplencia_share_carteira"] == pytest.approx(
        104.0 / 120.0
    )
    assert profile["bridge_2024_06_07"]["delta_inadimplencia_bruta"] == pytest.approx(
        102.0 - 16_000.0
    )


def test_delinquency_qa_uses_report_flags_and_reconciles_vehicle_to_fund() -> None:
    base = build_base_by_vehicle(_vehicle_rows())
    qa = build_delinquency_qa(base).iloc[0]
    reconciliation = build_reconciliation(base)

    assert qa["veiculos_total"] == 3
    assert qa["fundos_total"] == 2
    assert qa["veiculos_com_campos_reportados"] == 2
    assert qa["casos_inad_supera_carteira"] == 1
    assert qa["inadimplencia_bruta_brl"] == 80.0
    assert qa["inadimplencia_ajustada_brl"] == 50.0
    assert qa["excesso_removido_brl"] == 30.0
    assert qa["excesso_top1_share"] == 1.0
    assert reconciliation["universo_veiculos"].iloc[0] == 3
    assert reconciliation["universo_fundos"].iloc[0] == 2
    assert reconciliation["diferenca_veiculos_menos_fundo"].sum() == 1


def test_delinquency_qa_reconciles_aging_and_builds_ex360_sensitivity() -> None:
    row = _vehicle_rows().head(1).copy()
    row["carteira_dc"] = 100.0
    row["dc_inadimplentes"] = 80.0
    row["reports_aging"] = True
    row["reports_inad_acima_360d"] = True
    row["inad_ate_30d"] = 50.0
    row["inad_361_720d"] = 30.0
    row["inad_acima_360d"] = 30.0
    base = build_base_by_vehicle(row)
    qa = build_delinquency_qa(base).iloc[0]

    assert qa["aging_reconciliacao_ratio"] == 1.0
    assert qa["aging_publication_status"] == "publicável"
    assert qa["inadimplencia_ex_360d_pct_sobre_cobertura"] == 0.5
    assert qa["inadimplencia_ex_360d_ajustada_pct_sobre_cobertura"] == 0.5


def test_june_july_bridge_is_additive_and_separates_entries_exits_and_report_changes() -> None:
    rows = pd.DataFrame(
        [
            {
                "competencia": "2024-06",
                "cnpj": "1",
                "cnpj_fundo": "1",
                "denominacao": "CONTINUANTE",
                "pl": 100,
                "carteira_dc": 50,
                "dc_inadimplentes": 80,
                "reports_carteira_dc": True,
                "reports_dc_inadimplentes": True,
            },
            {
                "competencia": "2024-07",
                "cnpj": "1",
                "cnpj_fundo": "1",
                "denominacao": "CONTINUANTE",
                "pl": 100,
                "carteira_dc": 50,
                "dc_inadimplentes": 0,
                "reports_carteira_dc": True,
                "reports_dc_inadimplentes": False,
            },
            {
                "competencia": "2024-06",
                "cnpj": "2",
                "cnpj_fundo": "2",
                "denominacao": "SAIDA",
                "pl": 20,
                "carteira_dc": 10,
                "dc_inadimplentes": 2,
                "reports_carteira_dc": True,
                "reports_dc_inadimplentes": True,
            },
            {
                "competencia": "2024-07",
                "cnpj": "3",
                "cnpj_fundo": "3",
                "denominacao": "ENTRADA",
                "pl": 30,
                "carteira_dc": 15,
                "dc_inadimplentes": 3,
                "reports_carteira_dc": True,
                "reports_dc_inadimplentes": True,
            },
        ]
    )
    base = build_base_by_vehicle(rows)
    detail, summary = build_break_bridge(base)

    assert set(summary["bridge_group"]) == {"entradas", "mudança de reporte", "saídas"}
    assert math.isclose(detail["delta_pl_brl"].sum(), 10.0)
    assert math.isclose(detail["delta_inad_bruta_brl"].sum(), -79.0)
    assert math.isclose(
        summary["delta_excesso_brl"].sum(), detail["delta_excesso_brl"].sum()
    )


def _fund_base_for_rankings() -> pd.DataFrame:
    focus_pairs = [
        (anbima_type, focus)
        for anbima_type, focuses in ANBIMA_FOCUS_BY_TYPE.items()
        for focus in focuses
    ]
    rows = []
    for index in range(30):
        anbima_type, focus = focus_pairs[index % len(focus_pairs)]
        rows.append(
            {
                "competencia": "2026-05",
                "cnpj_fundo": str(index + 1).zfill(14),
                "denominacao": f"FIDC {index + 1:02d}",
                "pl": float((100 - index) * 1_000_000),
                "is_fic_fidc": False,
                "anbima_tipo": anbima_type,
                "anbima_foco": focus,
                "classification_tier": "oficial_anbima",
                "admin_nome": f"ADMIN {index % 12}",
                "admin_cnpj": str(1000 + index % 12),
                "gestor_nome": f"GESTOR {index % 12}",
                "gestor_cnpj": str(2000 + index % 12),
                "custodiante_nome": f"CUSTODIANTE {index % 12}",
                "custodiante_cnpj": str(3000 + index % 12),
            }
        )
    rows[0].update(
        {
            "cnpj_fundo": "09195235000150",
            "denominacao": "FIDC DO SISTEMA PETROBRAS",
            "admin_nome": "BB GESTAO DE RECURSOS DTVM S.A",
            "admin_cnpj": "30822936000169",
            "gestor_nome": "BB GESTAO DE RECURSOS DTVM S.A",
            "gestor_cnpj": "30822936000169",
            "custodiante_nome": "BANCO DO BRASIL S.A.",
            "custodiante_cnpj": "00000000000191",
        }
    )
    rows[1].update(
        {
            "cnpj_fundo": "26287464000114",
            "denominacao": "TAPSO FIDC",
            "admin_nome": "OLIVEIRA TRUST DTVM S.A.",
            "admin_cnpj": "36113876000191",
            "gestor_nome": "OLIVEIRA TRUST SERVICER S/A",
            "gestor_cnpj": "02150453000120",
            "custodiante_nome": "OLIVEIRA TRUST DTVM S.A.",
            "custodiante_cnpj": "36113876000191",
        }
    )
    return pd.DataFrame(rows)


def test_top20_uses_full_universe_and_mono_uses_one_group_definition() -> None:
    funds = _fund_base_for_rankings()
    top20, _, structured, concentration = build_top20_and_monostructure(funds)

    assert len(top20) == 20
    assert top20["rank"].tolist() == list(range(1, 21))
    assert top20["market_share_ex_fic"].is_monotonic_decreasing
    selected = structured[structured["denominacao"].isin({"FIDC DO SISTEMA PETROBRAS", "TAPSO FIDC"})]
    assert selected["monoestrutura_conglomerado"].all()
    assert not selected["monoestrutura_entidade_legal"].all()
    assert set(selected["definicao_mono_adotada"]) == {
        "mesmo conglomerado econômico normalizado"
    }
    assert {"Banco do Brasil", "Oliveira Trust"}.issubset(set(concentration["grupo_economico"]))


def test_market_share_subtype_uses_fixed_top10_and_separates_missing_provider() -> None:
    funds = _fund_base_for_rankings()
    # Ensure each of the 14 focuses has one explicitly missing administrator.
    extra = []
    for index, (anbima_type, focuses) in enumerate(ANBIMA_FOCUS_BY_TYPE.items()):
        for focus in focuses:
            extra.append(
                {
                    "competencia": "2026-05",
                    "cnpj_fundo": f"9{len(extra):013d}",
                    "denominacao": f"SEM ADMIN {focus}",
                    "pl": 1_000_000.0,
                    "is_fic_fidc": False,
                    "anbima_tipo": index,
                    "anbima_foco": focus,
                    "classification_tier": "oficial_anbima",
                    "admin_nome": "",
                    "admin_cnpj": "",
                    "gestor_nome": "GESTOR 1",
                    "gestor_cnpj": "2001",
                    "custodiante_nome": "CUSTODIANTE 1",
                    "custodiante_cnpj": "3001",
                }
            )
            extra[-1]["anbima_tipo"] = anbima_type
    funds = pd.concat([funds, pd.DataFrame(extra)], ignore_index=True)
    market, fixed = build_market_share_by_subtype(funds)
    scope = build_market_share_scope_summary(funds, market)
    coverage = build_classification_coverage(funds)

    assert market["foco_anbima"].nunique() == 14
    assert fixed.groupby("papel").size().eq(10).all()
    excluded_pl = funds.loc[
        funds["cnpj_fundo"].isin(MARKET_SHARE_EXCLUDED_FUNDS), "pl"
    ].sum()
    expected_denominator = funds["pl"].sum() - excluded_pl
    assert scope["pl_total_ex_fic_brl"].eq(expected_denominator).all()
    assert scope["fundos_total_ex_fic"].eq(funds["cnpj_fundo"].nunique() - 2).all()
    assert not fixed["participante"].isin(
        {"Banco do Brasil", "Oliveira Trust Servicer"}
    ).any()
    admin = market[market["papel"].eq("administrador")]
    assert "Outros identificados" in set(admin["participante_bucket"])
    assert "Prestador não informado" in set(admin["participante_bucket"])
    valid = market[market["publication_status"].eq("publicável")]
    closing = valid.groupby(["papel", "tipo_anbima", "foco_anbima"])["share_subtipo"].sum()
    assert closing.map(lambda value: math.isclose(value, 1.0, abs_tol=1e-9)).all()
    assert scope["focos_taxonomia"].eq(14).all()
    assert scope["pl_fora_14_focos_nd_brl"].eq(0).all()
    assert math.isclose(coverage["cobertura_pl_ex_fic"].sum(), 1.0, abs_tol=1e-9)


def test_market_share_normalizes_on_positive_pl_and_flags_negative_category() -> None:
    funds = _fund_base_for_rankings()
    target = funds.index[2]
    funds.loc[target, "pl"] = -1.0
    market, _ = build_market_share_by_subtype(funds)
    row = funds.loc[target]
    scoped = market[
        market["tipo_anbima"].eq(row["anbima_tipo"])
        & market["foco_anbima"].eq(row["anbima_foco"])
    ]

    expected_positive_denominator = funds.loc[
        funds["anbima_tipo"].eq(row["anbima_tipo"])
        & funds["anbima_foco"].eq(row["anbima_foco"])
        & funds["pl"].ge(0),
        "pl",
    ].sum()
    assert set(scoped["publication_status"]) == {"publicável_com_nota_pl_negativo"}
    assert scoped["denominador_publicacao_pl_positivo_brl"].eq(
        expected_positive_denominator
    ).all()
    closing = scoped.groupby("papel")["share_subtipo"].sum()
    assert closing.map(lambda value: math.isclose(value, 1.0, abs_tol=1e-9)).all()
    assert scoped["fundos_pl_negativo"].eq(1).all()
    assert scoped["quality_note"].str.contains(
        r"excluído\(s\) da normalização percentual sobre PL positivo",
        regex=True,
    ).all()


def test_provider_historical_ranking_excludes_named_funds_in_all_periods() -> None:
    rows: list[dict[str, object]] = []
    for period in ("2024-12", "2025-12", "2026-05"):
        rows.extend(
            [
                {
                    "competencia": period,
                    "cnpj_fundo": "09195235000150",
                    "pl": 1_000.0,
                    "is_fic_fidc": False,
                    "admin_nome": "BANCO DO BRASIL",
                    "gestor_nome": "BANCO DO BRASIL",
                    "custodiante_nome": "BANCO DO BRASIL",
                },
                {
                    "competencia": period,
                    "cnpj_fundo": "26287464000114",
                    "pl": 800.0,
                    "is_fic_fidc": False,
                    "admin_nome": "OLIVEIRA TRUST",
                    "gestor_nome": "OLIVEIRA TRUST",
                    "custodiante_nome": "OLIVEIRA TRUST",
                },
                {
                    "competencia": period,
                    "cnpj_fundo": f"{period}-A",
                    "pl": 300.0,
                    "is_fic_fidc": False,
                    "admin_nome": "QI TECH",
                    "gestor_nome": "QI TECH",
                    "custodiante_nome": "QI TECH",
                },
                {
                    "competencia": period,
                    "cnpj_fundo": f"{period}-B",
                    "pl": 200.0,
                    "is_fic_fidc": False,
                    "admin_nome": "BTG PACTUAL",
                    "gestor_nome": "BTG PACTUAL",
                    "custodiante_nome": "BTG PACTUAL",
                },
                {
                    "competencia": period,
                    "cnpj_fundo": f"{period}-FIC",
                    "pl": 500.0,
                    "is_fic_fidc": True,
                    "admin_nome": "FIC PROVIDER",
                    "gestor_nome": "FIC PROVIDER",
                    "custodiante_nome": "FIC PROVIDER",
                },
            ]
        )

    ranking = build_provider_historical_ranking(pd.DataFrame(rows))

    assert set(ranking["competencia"]) == {"2024-12", "2025-12", "2026-05"}
    assert set(ranking["papel"]) == {"administrador", "gestor", "custodiante"}
    assert ranking["denominador_pl_brl"].eq(500.0).all()
    assert ranking["fundos_universo"].eq(2).all()
    assert not ranking["participante"].isin(
        {"Banco do Brasil", "Oliveira Trust", "FIC PROVIDER"}
    ).any()
    assert ranking.groupby(["competencia", "papel"])["rank_periodo"].apply(
        list
    ).map(lambda ranks: ranks == [1, 2]).all()


def test_frozen_receivable_cohort_keeps_latest_membership_and_subtype() -> None:
    fund_rows = []
    for competence, values in {
        "2025-12": [("10000000000001", 100.0, 80.0, 8.0), ("10000000000002", 50.0, 20.0, 25.0)],
        "2026-05": [("10000000000001", 120.0, 90.0, 9.0), ("10000000000002", 60.0, 30.0, 3.0)],
    }.items():
        for cnpj, pl, portfolio, delinquency in values:
            fund_rows.append(
                {
                    "competencia": competence,
                    "cnpj_fundo": cnpj,
                    "denominacao": f"FIDC {cnpj}",
                    "pl": pl,
                    "carteira_dc": portfolio,
                    "dc_inadimplentes": delinquency,
                    "dc_inadimplentes_ajustado_recalculado": min(portfolio, delinquency),
                    "is_fic_fidc": False,
                    "reports_carteira_dc": True,
                    "reports_dc_inadimplentes": True,
                }
            )
    vehicle = pd.DataFrame(
        [
            {"competencia": "2026-05", "cnpj_veiculo": "10000000000001", "cnpj_fundo": "10000000000001"},
            {"competencia": "2026-05", "cnpj_veiculo": "10000000000002", "cnpj_fundo": "10000000000002"},
        ]
    )
    raw_rows = []
    for cnpj, column in [
        ("10000000000001", "table_ii_financeiro_brl"),
        ("10000000000002", "table_ii_comercial_brl"),
    ]:
        row = {"competencia": "2026-05", "cnpj": cnpj}
        row.update({name: 0.0 for name in TABLE_II_RECEIVABLE_COLUMNS})
        row[column] = 100.0
        raw_rows.append(row)

    members, history, summary = build_frozen_single_receivable_history(
        vehicle,
        pd.DataFrame(fund_rows),
        pd.DataFrame(raw_rows),
    )

    assert len(members) == 2
    assert set(members["tipo_recebivel_tabela_ii"]) == {"Financeiro", "Comercial"}
    prior = history[history["competencia"].eq("2025-12")].set_index("tipo_recebivel_tabela_ii")
    assert prior.loc["Financeiro", "fundos_incluidos"] == 1
    assert prior.loc["Comercial", "fundos_incluidos"] == 0
    assert prior.loc["Comercial", "fundos_inad_supera_carteira_excluidos"] == 1
    latest = summary[summary["competencia"].eq("2026-05")].iloc[0]
    assert latest["fundos_coorte"] == 2
    assert latest["fundos_incluidos"] == 2
    assert "coorte e subtipo congelados" in latest["regra"]


def test_provider_transition_uses_current_pl_and_marks_overlay_roles_as_samples() -> None:
    def row(
        competence: str,
        cnpj: str,
        pl: float,
        administrator: str,
        admin_cnpj: str,
        *,
        is_fic: bool = False,
    ) -> dict[str, object]:
        return {
            "competencia": competence,
            "cnpj_fundo": cnpj,
            "denominacao": f"FIDC {cnpj}",
            "pl": pl,
            "is_fic_fidc": is_fic,
            "admin_nome": administrator,
            "admin_cnpj": admin_cnpj,
        }

    rows = [
        row("2024-12", "10000000000001", 100, "OLIVEIRA TRUST", "36113876000191"),
        row("2026-05", "10000000000001", 20, "BRADESCO", "60746948000112"),
        row("2024-12", "10000000000002", 20, "OLIVEIRA TRUST", "36113876000191"),
        row("2026-05", "10000000000002", 100, "BRADESCO", "60746948000112"),
        row("2024-12", "10000000000003", 40, "QI TECH", "62285390000140"),
        row("2026-05", "10000000000003", 60, "QI TECH", "62285390000140"),
        row("2024-12", "10000000000004", 50, "QI TECH", "62285390000140"),
        row("2026-05", "10000000000005", 50, "QI TECH", "62285390000140"),
        row("2024-12", "10000000000006", 10, "QI TECH", "62285390000140"),
        row("2026-05", "10000000000006", 0, "BRADESCO", "60746948000112"),
        row("2024-12", "10000000000007", 90, "QI TECH", "62285390000140", is_fic=True),
        row("2026-05", "10000000000007", 90, "BRADESCO", "60746948000112", is_fic=True),
        row("2024-12", "09195235000150", 1_000, "BANCO DO BRASIL", "00000000000191"),
        row("2026-05", "09195235000150", 1_000, "BRADESCO", "60746948000112"),
    ]

    summary, links, detail, availability = build_provider_transition_flows(
        pd.DataFrame(rows)
    )

    assert summary.iloc[0]["continuing_funds"] == 3
    assert summary.iloc[0]["comparable_pl_brl"] == 180
    assert summary.iloc[0]["changed_funds"] == 2
    assert summary.iloc[0]["changed_comparable_pl_brl"] == 120
    assert summary.iloc[0]["changed_share"] == pytest.approx(2 / 3)
    assert len(links) == 1
    assert links.iloc[0]["fundos"] == 2
    assert links.iloc[0]["pl_origem_brl"] == 120
    assert links.iloc[0]["pl_destino_brl"] == 120
    assert links.iloc[0]["pl_comparavel_brl"] == 120
    assert detail["fundosnet_url"].str.contains("cnpjFundo=").all()
    role_status = availability.set_index("papel")
    assert bool(role_status.loc["administrador", "serie_historica_observada"])
    assert not bool(role_status.loc["gestor", "serie_historica_observada"])
    assert not bool(role_status.loc["custodiante", "serie_historica_observada"])
    assert set(links["papel"]) == {"administrador"}


def test_reag_admin_cohort_reconciles_exits_and_collapses_small_destinations() -> None:
    origin_admin = "34829992000186"

    def row(
        competence: str,
        cnpj: str,
        pl: float,
        administrator: str,
        admin_cnpj: str,
        *,
        is_fic: bool = False,
    ) -> dict[str, object]:
        return {
            "competencia": competence,
            "cnpj_fundo": cnpj,
            "denominacao": f"FIDC {cnpj}",
            "pl": pl,
            "is_fic_fidc": is_fic,
            "admin_nome": administrator,
            "admin_cnpj": admin_cnpj,
        }

    rows = [
        row("2025-12", "20000000000001", 100, "CBSF DTVM", origin_admin),
        row("2026-05", "20000000000001", 110, "CBSF DTVM", origin_admin),
        row("2025-12", "20000000000002", 80, "CBSF DTVM", origin_admin),
        row("2026-05", "20000000000002", 90, "MASTER S/A CORRETORA", "33886862000112"),
        row("2025-12", "20000000000003", 60, "CBSF DTVM", origin_admin),
        row("2026-05", "20000000000003", 70, "PLANNER CORRETORA DE VALORES S.A.", "00806535000154"),
        row("2025-12", "20000000000004", 50, "CBSF DTVM", origin_admin),
        row("2026-05", "20000000000004", 40, "QI TECH", "62285390000140"),
        row("2025-12", "20000000000005", 40, "CBSF DTVM", origin_admin),
        row("2025-12", "20000000000006", 30, "CBSF DTVM", origin_admin),
        row("2026-05", "20000000000006", -5, "PLANNER CORRETORA DE VALORES S.A.", "00806535000154"),
        row("2025-12", "20000000000007", 20, "CBSF DTVM", origin_admin, is_fic=True),
        row("2025-12", "20000000000008", 0, "CBSF DTVM", origin_admin),
        row("2025-12", "09195235000150", 500, "CBSF DTVM", origin_admin),
    ]

    summary, links, detail = build_reag_admin_cohort(pd.DataFrame(rows))
    item = summary.iloc[0]

    assert item["funds_origin"] == 6
    assert item["pl_origin_brl"] == 360
    assert item["continuing_funds"] == 4
    assert item["continuing_pl_current_brl"] == 310
    assert item["migrated_funds"] == 3
    assert item["migrated_pl_current_brl"] == 200
    assert item["exited_funds"] == 2
    assert item["exited_pl_origin_brl"] == 70
    assert item["missing_destination_funds"] == 1
    assert item["nonpositive_destination_funds"] == 1
    assert not bool(item["manager_custodian_history_available"])
    assert set(links["destino_grupo"]) == {
        "CBSF",
        "Banco Master",
        "Planner Corretora De Valores",
        "Outros migrados",
        "Saída / sem reporte",
    }
    assert links["pl_flow_brl"].sum() == item["pl_origin_brl"]
    assert links["pl_current_brl"].sum() == item["continuing_pl_current_brl"]
    assert set(detail["status_destino"]) == {
        "continuante_ativo",
        "saida_sem_reporte",
        "saida_pl_nao_positivo",
    }


def test_provider_leadership_reconciles_btg_six_and_qi_legal_cnpjs() -> None:
    btg_name = "BANCO BTG PACTUAL S/A"
    vehicle_rows = []
    for index, cnpj in enumerate(BTG_CONTROLLED_FIDCS, start=1):
        vehicle_rows.append(
            {
                "competencia": "2026-05",
                "cnpj_veiculo": cnpj,
                "cnpj_fundo": cnpj,
                "denominacao": BTG_CONTROLLED_FIDCS[cnpj],
                "pl": float(index * 10),
                "is_fic_fidc": False,
                "admin_nome": "BTG PACTUAL SERVIÇOS FINANCEIROS S/A DTVM",
                "admin_cnpj": "59281253000123",
                "gestor_nome": btg_name,
                "gestor_cnpj": "30306294000145",
                "custodiante_nome": btg_name,
                "custodiante_cnpj": "30306294000145",
            }
        )
    ranking = pd.DataFrame(
        [
            {"competencia": "2026-05", "papel": "administrador", "participante": "BTG Pactual", "pl_brl": 500},
            {"competencia": "2026-05", "papel": "gestor", "participante": "BTG Pactual", "pl_brl": 300},
            {"competencia": "2026-05", "papel": "gestor", "participante": "Bradesco", "pl_brl": 250},
            {"competencia": "2026-05", "papel": "gestor", "participante": "Genial", "pl_brl": 80},
            {"competencia": "2026-05", "papel": "custodiante", "participante": "BTG Pactual", "pl_brl": 400},
        ]
    )
    qi_funds = pd.DataFrame(
        [
            {
                "competencia": "2024-12",
                "cnpj_fundo": "30000000000001",
                "pl": 90.0,
                "is_fic_fidc": False,
                "admin_nome": "SINGULARE CTVM",
                "admin_cnpj": "62285390000140",
            },
            {
                "competencia": "2024-12",
                "cnpj_fundo": "30000000000002",
                "pl": 10.0,
                "is_fic_fidc": False,
                "admin_nome": "QI DISTRIBUIDORA DTVM",
                "admin_cnpj": "46955383000152",
            },
            {
                "competencia": "2024-12",
                "cnpj_fundo": "30000000000003",
                "pl": 50.0,
                "is_fic_fidc": False,
                "admin_nome": "QI TECH",
                "admin_cnpj": "99999999000199",
            },
        ]
    )

    summary, btg_detail, qi_detail = build_provider_leadership_attribution(
        pd.DataFrame(vehicle_rows), qi_funds, ranking
    )
    records = summary.set_index("provider")

    assert records.loc["btg", "confirmed_controlled_pl_brl"] == 210
    assert records.loc["btg", "residual_unproven_pl_brl"] == 90
    assert records.loc["btg", "confirmed_controlled_share"] == 0.7
    assert records.loc["btg", "rank_without_confirmed"] == 2
    assert len(btg_detail) == 6
    assert btg_detail["reconciliado_controlado_ativo"].all()
    assert records.loc["qi", "admin_group_pl_2024_brl"] == 100
    assert records.loc["qi", "legacy_singulare_pl_2024_brl"] == 90
    assert records.loc["qi", "original_qi_pl_2024_brl"] == 10
    assert records.loc["qi", "legacy_share_2024"] == 0.9
    assert set(qi_detail["provider_cnpj"]) == {
        "62285390000140",
        "46955383000152",
    }

    nested = _provider_leadership_payload(summary, btg_detail, qi_detail)
    assert nested["btg"]["rank_without_confirmed"] == 2
    assert len(nested["btg"]["reconciliation"]) == 6
    assert nested["qi"]["legacy_share_2024"] == 0.9
    assert len(nested["qi"]["legacy_entities"]) == 2


def test_btg_controlled_reconciliation_fails_if_one_disclosed_cnpj_is_missing() -> None:
    rows = [
        {
            "competencia": "2026-05",
            "cnpj_veiculo": cnpj,
            "cnpj_fundo": cnpj,
            "pl": 10.0,
            "is_fic_fidc": False,
            "admin_nome": "BTG PACTUAL",
            "gestor_nome": "BTG PACTUAL",
            "custodiante_nome": "BTG PACTUAL",
        }
        for cnpj in list(BTG_CONTROLLED_FIDCS)[:-1]
    ]
    ranking = pd.DataFrame(
        [
            {
                "competencia": "2026-05",
                "papel": "gestor",
                "participante": "BTG Pactual",
                "pl_brl": 100.0,
            }
        ]
    )

    with pytest.raises(AssertionError, match="seis FIDCs controlados"):
        build_btg_controlled_reconciliation(pd.DataFrame(rows), ranking)


def test_optional_payload_reader_preserves_leading_zero_cnpj(tmp_path) -> None:
    path = tmp_path / "reag_links.csv"
    path.write_text(
        "admin_destino_cnpj,pl_flow_brl\n00806535000154,10\n",
        encoding="utf-8",
    )

    records = _read_optional(path, cnpj_columns=("admin_destino_cnpj",))

    assert records.iloc[0]["admin_destino_cnpj"] == "00806535000154"
