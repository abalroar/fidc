from __future__ import annotations

import math

import pandas as pd

from scripts.build_fidc_industry_study import field_reported
from services.industry_anbima import ANBIMA_FOCUS_BY_TYPE
from services.industry_revision_analysis import (
    build_base_by_vehicle,
    build_break_bridge,
    build_classification_coverage,
    build_delinquency_qa,
    build_market_share_by_subtype,
    build_market_share_scope_summary,
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
    admin = market[market["papel"].eq("administrador")]
    assert "Outros identificados" in set(admin["participante_bucket"])
    assert "Prestador não informado" in set(admin["participante_bucket"])
    valid = market[market["publication_status"].eq("publicável")]
    closing = valid.groupby(["papel", "tipo_anbima", "foco_anbima"])["share_subtipo"].sum()
    assert closing.map(lambda value: math.isclose(value, 1.0, abs_tol=1e-9)).all()
    assert scope["focos_taxonomia"].eq(14).all()
    assert scope["pl_fora_14_focos_nd_brl"].eq(0).all()
    assert math.isclose(coverage["cobertura_pl_ex_fic"].sum(), 1.0, abs_tol=1e-9)


def test_market_share_blocks_negative_category() -> None:
    funds = _fund_base_for_rankings()
    target = funds.index[0]
    funds.loc[target, "pl"] = -1.0
    market, _ = build_market_share_by_subtype(funds)
    row = funds.loc[target]
    scoped = market[
        market["tipo_anbima"].eq(row["anbima_tipo"])
        & market["foco_anbima"].eq(row["anbima_foco"])
    ]

    assert "bloqueado_pl_negativo" in set(scoped["publication_status"])
    assert scoped["quality_note"].str.contains("não publicar").all()
