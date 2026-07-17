from __future__ import annotations

import math

import pandas as pd
import pytest

from scripts.build_fidc_industry_study import field_reported
from scripts.build_fidc_revision_artifact_payload import (
    _atlantico_payload,
    _holder_distribution,
    _holder_distribution_history,
    _provider_concentration_history,
    _receivables_history,
    _type_mix_history,
)
from services.industry_anbima import ANBIMA_FOCUS_BY_TYPE
from services.industry_revision_analysis import (
    MARKET_SHARE_EXCLUDED_FUNDS,
    build_base_by_vehicle,
    build_break_bridge,
    build_classification_coverage,
    build_delinquency_qa,
    build_market_share_by_subtype,
    build_market_share_scope_summary,
    build_provider_historical_ranking,
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
