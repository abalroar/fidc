from __future__ import annotations

import math

import pandas as pd
import pytest

from services.industry_executive_pack import (
    ANBIMA_CLASSIFICATION_VALUES,
    ANBIMA_FIC,
    ANBIMA_ND,
    ANBIMA_TYPES,
    HOLDER_BUCKETS,
    IndustryExecutivePack,
    aggregate_vehicle_monthly_by_fund,
    apply_anbima_classification,
    build_holder_histograms,
    build_industry_executive_pack,
    build_market_share,
    build_monostructure_history,
    build_provider_rankings,
    select_executive_competences,
)


def _status(*, june_status: str = "preliminar") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "competencia": ["2024-12", "2025-12", "2026-05", "2026-06"],
            "publication_status": ["completa", "completa", "completa", june_status],
            "pl_total": [450.0, 540.0, 660.0, 200.0],
        }
    )


def _vehicle_rows() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    values_by_period = {
        "2024-12": [70.0, 50.0, 40.0, 30.0, 20.0, 10.0],
        "2025-12": [85.0, 60.0, 50.0, 35.0, 25.0, 15.0],
        "2026-05": [100.0, 80.0, 60.0, 40.0, 30.0, 20.0],
    }
    specifications = [
        # fund, class, name, segment, financial segment, cotistas, providers, FIC
        (
            "11111111000111",
            "91111111000111",
            "Fundo Financeiro",
            "Comercial",
            "",
            3.0,
            "INTRAG DTVM LTDA.",
            "ITAU UNIBANCO ASSET MANAGEMENT LTDA.",
            "ITAU UNIBANCO S.A.",
            False,
        ),
        (
            "22222222000122",
            "92222222000122",
            "Fundo Fomento",
            "Factoring",
            "",
            1.0,
            "QI CORRETORA DE TITULOS E VALORES MOBILIARIOS S.A.",
            "QI GESTAO DE RECURSOS LTDA.",
            "BANCO BRADESCO S.A.",
            False,
        ),
        (
            "33333333000133",
            "93333333000133",
            "Fundo Sem Classificação",
            "Marcas e patentes",
            "",
            math.nan,
            "OLIVEIRA TRUST DTVM S.A.",
            "",
            "OLIVEIRA TRUST DTVM S.A.",
            False,
        ),
        (
            "44444444000144",
            "94444444000144",
            "Fundo Outros",
            "Ações judiciais",
            "",
            11.0,
            "BANCO BRADESCO S.A.",
            "BANCO BRADESCO S.A.",
            "BANCO BRADESCO S.A.",
            False,
        ),
        (
            "55555555000155",
            "95555555000155",
            "FIC de FIDC",
            "Financeiro",
            "Financeiro: outros",
            5.0,
            "OLIVEIRA TRUST DTVM S.A.",
            "OLIVEIRA TRUST DTVM S.A.",
            "OLIVEIRA TRUST DTVM S.A.",
            True,
        ),
        (
            "66666666000166",
            "96666666000166",
            "Fundo Agro",
            "Agronegócio",
            "",
            51.0,
            "BANCO DO BRASIL S.A.",
            "BB GESTAO DE RECURSOS DTVM S.A.",
            "BANCO DO BRASIL S.A.",
            False,
        ),
    ]
    for competence, values in values_by_period.items():
        for spec, value in zip(specifications, values):
            (
                fund_cnpj,
                class_cnpj,
                name,
                segment,
                financial_segment,
                cotistas,
                admin,
                manager,
                custodian,
                is_fic,
            ) = spec
            rows.append(
                {
                    "competencia": competence,
                    "cnpj_fundo": fund_cnpj,
                    "cnpj": class_cnpj,
                    "denominacao": name,
                    "pl": value,
                    "cotistas": cotistas,
                    "is_fic_fidc": is_fic,
                    "segmento_principal": segment,
                    "segmento_financeiro_principal": financial_segment,
                    "admin_nome": admin,
                    "gestor_nome": manager,
                    "custodiante_nome": custodian,
                    "classificacao_anbima": "",
                }
            )

    # The latest total for fund 1 is 100 (60 + 40), never the first class only.
    latest_fund_1 = next(
        row
        for row in rows
        if row["competencia"] == "2026-05" and row["cnpj_fundo"] == "11111111000111"
    )
    latest_fund_1["pl"] = 60.0
    latest_fund_1["cotistas"] = 1.0
    rows.append(
        {
            **latest_fund_1,
            "cnpj": "91111111000112",
            "pl": 40.0,
            "cotistas": 2.0,
        }
    )
    return pd.DataFrame(rows)


def _official_anbima() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "CNPJ Fundo": [
                "11111111000111",
                "11111111000111",
                "44444444000144",
                "66666666000166",
            ],
            "CNPJ Classe": [
                "91111111000111",
                "",
                "94444444000144",
                "",
            ],
            "Tipo ANBIMA": [
                "Financeiro",
                "Agro, Indústria e Comércio",
                "Outros",
                "Agro, Indústria e Comércio",
            ],
            "foco_atuacao": [
                "Crédito Pessoal",
                "Recebíveis Comerciais",
                "Multicarteira Outros",
                "Agronegócio",
            ],
            "fonte": ["ANBIMA público"] * 4,
            "source_snapshot_date": ["2025-12-29"] * 4,
        }
    )


def test_select_competences_excludes_preliminary_tail() -> None:
    result = select_executive_competences(_status())

    assert result.ordered == ("2024-12", "2025-12", "2026-05")
    assert result.latest_complete == "2026-05"
    assert result.latest_available == "2026-06"
    assert result.excluded_tail == ("2026-06",)


def test_select_competences_refuses_to_infer_missing_december() -> None:
    status = _status().query("competencia != '2024-12'")

    with pytest.raises(ValueError, match="2024-12"):
        select_executive_competences(status)


def test_fund_aggregation_sums_classes_and_preserves_class_identifiers() -> None:
    latest = _vehicle_rows().query("competencia == '2026-05'")

    aggregated = aggregate_vehicle_monthly_by_fund(latest)
    fund = aggregated.loc[aggregated["cnpj_fundo"].eq("11111111000111")].iloc[0]

    assert fund["pl"] == 100.0
    assert fund["cotistas"] == 3.0
    assert fund["source_rows"] == 2
    assert fund["cnpj_classe_count"] == 2
    assert set(fund["cnpj_classes"].split(" | ")) == {
        "91111111000111",
        "91111111000112",
    }


def test_anbima_precedence_is_class_then_fund_then_published_then_proxy_then_nd() -> None:
    aggregated = aggregate_vehicle_monthly_by_fund(
        _vehicle_rows().query("competencia == '2026-05'")
    )
    evidence = pd.DataFrame(
        {
            "cnpj": ["22222222000122"],
            "anbima_type_document": ["Outros"],
            "anbima_focus_document": ["Poder Público"],
            "anbima_evidence": ["regulamento público"],
        }
    )

    classified = apply_anbima_classification(
        aggregated,
        anbima_classification=_official_anbima(),
        published_classifications=evidence,
    ).set_index("cnpj_fundo")

    # The class row overrides the contradictory fund row.
    assert classified.loc["11111111000111", "anbima_tipo"] == "Financeiro"
    assert classified.loc["11111111000111", "anbima_foco"] == "Crédito Pessoal"
    assert classified.loc["11111111000111", "classification_tier"] == "oficial_anbima"
    assert "ponte" not in classified.loc["11111111000111", "classification_warning"]
    assert "após a fotografia" in classified.loc["11111111000111", "classification_warning"]
    # Published documentary evidence overrides the Factoring proxy.
    assert classified.loc["22222222000122", "anbima_tipo"] == "Outros"
    assert classified.loc["22222222000122", "classification_tier"] == "evidencia_publicada"
    # Unknown CVM segments remain N/D, never Outros.
    assert classified.loc["33333333000133", "anbima_tipo"] == ANBIMA_ND
    assert classified.loc["33333333000133", "classification_tier"] == "nao_disponivel"
    # FIC is kept outside the four-type taxonomy even if the CVM segment is Financeiro.
    assert classified.loc["55555555000155", "anbima_tipo"] == ANBIMA_FIC
    assert set(classified["anbima_tipo"]).issubset(ANBIMA_CLASSIFICATION_VALUES)


def test_invalid_official_label_falls_back_without_becoming_outros() -> None:
    aggregated = aggregate_vehicle_monthly_by_fund(
        _vehicle_rows().query("competencia == '2026-05' and cnpj_fundo == '33333333000133'")
    )
    official = pd.DataFrame(
        {
            "CNPJ Fundo": ["33333333000133"],
            "Tipo ANBIMA": ["Renda Fixa"],
            "foco_atuacao": ["Duração Livre"],
        }
    )

    row = apply_anbima_classification(aggregated, official).iloc[0]

    assert row["anbima_tipo"] == ANBIMA_ND
    assert "fora da whitelist" in row["classification_warning"]


def test_official_mapping_wins_but_flags_documentary_disagreement() -> None:
    aggregated = aggregate_vehicle_monthly_by_fund(
        _vehicle_rows().query("competencia == '2026-05' and cnpj_fundo == '44444444000144'")
    )
    published = pd.DataFrame(
        {
            "cnpj": ["44444444000144"],
            "anbima_type_document": ["Financeiro"],
            "anbima_focus_document": ["Crédito Pessoal"],
            "anbima_evidence": ["regulamento público"],
        }
    )

    row = apply_anbima_classification(
        aggregated,
        anbima_classification=_official_anbima(),
        published_classifications=published,
    ).iloc[0]

    assert row["anbima_tipo"] == "Outros"
    assert row["classification_tier"] == "oficial_anbima"
    assert row["classification_requires_warning"]
    assert "diverge da evidência documental" in row["classification_warning"]


def test_official_class_conflict_uses_dominant_class_and_stays_flagged() -> None:
    aggregated = aggregate_vehicle_monthly_by_fund(
        _vehicle_rows().query("competencia == '2026-05' and cnpj_fundo == '11111111000111'")
    )
    official = pd.DataFrame(
        {
            "cnpj_classe": ["91111111000111", "91111111000112"],
            "cnpj_fundo": ["11111111000111", "11111111000111"],
            "tipo_anbima": ["Financeiro", "Outros"],
            "foco_anbima": ["Financiamento de Veículos", "Recuperação"],
        }
    )

    row = apply_anbima_classification(aggregated, official).iloc[0]

    assert row["anbima_tipo"] == "Financeiro"
    assert row["anbima_foco"] == "Financiamento de Veículos"
    assert row["classification_requires_warning"]
    assert "conflitantes" in row["classification_warning"]


def test_market_share_has_four_types_plus_nd_and_excludes_fic() -> None:
    competences = select_executive_competences(_status())
    aggregated = aggregate_vehicle_monthly_by_fund(_vehicle_rows())
    classified = apply_anbima_classification(aggregated, _official_anbima())

    market_share = build_market_share(classified, competences)
    latest = market_share.query("competencia == '2026-05'")

    assert tuple(latest.sort_values("category_order")["anbima_tipo"]) == (*ANBIMA_TYPES, ANBIMA_ND)
    assert latest["share_ex_fic"].sum() == pytest.approx(1.0)
    assert ANBIMA_FIC not in set(market_share["anbima_tipo"])
    nd = latest.loc[latest["anbima_tipo"].eq(ANBIMA_ND)].iloc[0]
    assert nd["pl_brl"] == 60.0
    assert "N/D não foi convertido em Outros" in nd["warning"]


def test_holder_histograms_keep_zero_distinct_and_report_missing_coverage() -> None:
    cotistas = [0.0, 1.0, 2.0, 4.0, 11.0, 51.0, math.nan]
    rows = []
    for index, holders in enumerate(cotistas):
        rows.append(
            {
                "competencia": "2026-05",
                "fund_key": f"f{index}",
                "cnpj_fundo": str(index).zfill(14),
                "pl": 250.0,
                "cotistas": holders,
                "anbima_tipo": ANBIMA_TYPES[index % len(ANBIMA_TYPES)],
            }
        )
    rows.append(
        {
            "competencia": "2026-05",
            "fund_key": "fic",
            "cnpj_fundo": "99999999999999",
            "pl": 999.0,
            "cotistas": 1.0,
            "anbima_tipo": ANBIMA_FIC,
        }
    )

    histogram, coverage = build_holder_histograms(
        pd.DataFrame(rows), "2026-05", min_pl_brl=200.0
    )

    assert tuple(histogram["cotistas_bucket"].drop_duplicates()) == HOLDER_BUCKETS
    assert histogram["fund_count"].sum() == 6
    assert histogram.loc[histogram["cotistas_bucket"].eq("0"), "fund_count"].sum() == 1
    assert coverage.iloc[0]["eligible_funds"] == 7
    assert coverage.iloc[0]["funds_excluded_missing_cotistas"] == 1
    assert coverage.iloc[0]["fund_coverage"] == pytest.approx(6 / 7)


def test_monostructure_uses_canonical_provider_and_never_equates_missing_values() -> None:
    competences = select_executive_competences(_status())
    aggregated = aggregate_vehicle_monthly_by_fund(_vehicle_rows())
    classified = apply_anbima_classification(aggregated, _official_anbima())

    history = build_monostructure_history(classified, competences)
    latest = history.query("competencia == '2026-05'").set_index("structure_model")

    assert latest.loc["Monoestrutura", "funds"] >= 2
    assert latest.loc["Dados incompletos", "funds"] == 1
    assert "não inferir integração" in latest.loc["Dados incompletos", "warning"]
    assert latest["fund_share_total"].sum() == pytest.approx(1.0)
    historical = history.query("competencia == '2024-12'")
    assert historical["historical_registry_proxy"].all()
    assert historical["requires_warning"].all()
    assert historical["warning"].str.contains("cadastro CVM vigente").all()
    assert not latest["historical_registry_proxy"].any()


def test_rankings_expose_type_focus_role_share_and_rank_movement() -> None:
    competences = select_executive_competences(_status())
    aggregated = aggregate_vehicle_monthly_by_fund(_vehicle_rows())
    classified = apply_anbima_classification(aggregated, _official_anbima())

    rankings = build_provider_rankings(classified, competences)

    assert {"tipo", "foco"}.issubset(set(rankings["scope"]))
    assert {"administrador", "gestor", "custodiante"} == set(rankings["role"])
    assert set(rankings["period"]) == {"2024", "2025", "2026"}
    finance = rankings.query(
        "role == 'administrador' and scope == 'tipo' and anbima_tipo == 'Financeiro'"
    )
    assert finance["rank"].eq(1).all()
    assert finance["share_pl"].eq(1.0).all()
    assert finance["role_pl_coverage"].eq(1.0).all()
    historical_manager = rankings.query(
        "role == 'gestor' and competencia == '2024-12'"
    )
    assert historical_manager["historical_registry_proxy"].all()
    assert historical_manager["warning"].str.contains("reconstrução indicativa").all()
    historical_admin = rankings.query(
        "role == 'administrador' and competencia == '2024-12'"
    )
    assert not historical_admin["historical_registry_proxy"].any()


def test_builder_returns_complete_no_io_pack_with_coverage_and_warnings() -> None:
    vehicle = _vehicle_rows()
    industry = pd.DataFrame(
        {
            "competencia": ["2024-12", "2025-12", "2026-05"],
            # Match the six synthetic funds, including FIC.
            "pl_total": [220.0, 270.0, 330.0],
        }
    )
    status = _status()
    status.loc[status["competencia"].eq("2024-12"), "pl_total"] = 220.0
    status.loc[status["competencia"].eq("2025-12"), "pl_total"] = 270.0
    status.loc[status["competencia"].eq("2026-05"), "pl_total"] = 330.0

    pack = build_industry_executive_pack(
        vehicle_monthly=vehicle,
        competence_status=status,
        industry_monthly=industry,
        anbima_classification=_official_anbima(),
        holder_min_pl_brl=0.0,
    )

    assert isinstance(pack, IndustryExecutivePack)
    assert pack.competences.latest_complete == "2026-05"
    assert set(pack.fund_monthly["competencia"]) == {"2024-12", "2025-12", "2026-05"}
    assert pack.annual_pl["coverage_status"].eq("ok").all()
    assert pack.annual_pl.iloc[-1]["pl_total_brl"] == 330.0
    assert pack.annual_pl.iloc[-1]["pl_ex_fic_brl"] == 300.0
    assert not pack.top_20_outros.empty
    assert {"pl_share_ex_fic", "classification_requires_warning"}.issubset(pack.top_20_outros.columns)
    assert set(pack.curation_queue["anbima_tipo"]).issubset({"Outros", ANBIMA_ND})
    assert pack.coverage.iloc[-1]["official_anbima_classification_pl_share"] > 0
    assert any("2026-06" in warning for warning in pack.warnings)
    assert any("reconstrução indicativa" in warning for warning in pack.warnings)


def test_builder_preserves_tab4_source_conflicts_and_marks_annual_output() -> None:
    vehicle = _vehicle_rows()
    conflict = (
        vehicle["competencia"].eq("2025-12")
        & vehicle["cnpj_fundo"].eq("44444444000144")
    )
    vehicle.loc[conflict, "tab4_duplicate_detected"] = True
    vehicle.loc[conflict, "tab4_type_conflict"] = True
    vehicle.loc[conflict, "tab4_pl_conflict"] = True
    vehicle.loc[conflict, "tab4_duplicate_rows_dropped"] = 1
    vehicle.loc[conflict, "tab4_warning"] = (
        "2 registros Tab IV para o mesmo CNPJ; selecionado Classe sem somar duplicidades | "
        "conflito de tipo (Classe | Fundo) | conflito de PL (35 | 999)"
    )
    industry = pd.DataFrame(
        {
            "competencia": ["2024-12", "2025-12", "2026-05"],
            "pl_total": [220.0, 270.0, 330.0],
        }
    )
    status = _status()
    status.loc[status["competencia"].eq("2024-12"), "pl_total"] = 220.0
    status.loc[status["competencia"].eq("2025-12"), "pl_total"] = 270.0
    status.loc[status["competencia"].eq("2026-05"), "pl_total"] = 330.0

    pack = build_industry_executive_pack(
        vehicle_monthly=vehicle,
        competence_status=status,
        industry_monthly=industry,
        anbima_classification=_official_anbima(),
        holder_min_pl_brl=0.0,
    )

    assert len(pack.source_conflicts) == 1
    annual_2025 = pack.annual_pl.loc[pack.annual_pl["competencia"].eq("2025-12")].iloc[0]
    assert annual_2025["tab4_pl_conflict_funds"] == 1
    assert annual_2025["requires_warning"]
    assert "Classe priorizada sobre Fundo" in annual_2025["warning"]
    assert any("Classe priorizada sobre Fundo" in warning for warning in pack.warnings)
