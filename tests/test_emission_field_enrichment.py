from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.emission_field_enrichment import (
    TOP15_BLOCK,
    build_emission_field_coverage,
    build_profile_curation_evidence,
    build_taxonomy_party_evidence,
    classify_party_value,
    enrich_emission_field_audit,
    load_curated_remuneration_evidence,
    validate_emission_field_coverage,
)


def _audit_row(cnpj: str, *, table: str = "Financeiro · 2026-06", **overrides: str) -> dict[str, str]:
    row = {
        "bloco": TOP15_BLOCK,
        "tabela": table,
        "cnpj": cnpj,
        "emissao_id": "N/D",
        "fundo": f"FIDC {cnpj}",
        "originador": "N/D",
        "subordinacao_minima": "N/D",
        "preco_por_tipo_cota": "N/D",
        "remuneracao_por_tipo_cota": "N/D",
        "cedente": "N/D",
        "sacado": "N/D",
        "fonte_originador_cedente": "N/D",
        "fonte_subordinacao": "N/D",
        "fonte_preco": "N/D",
        "fonte_remuneracao": "N/D",
        "fonte_sacado": "N/D",
        "status": "N/D",
    }
    row.update(overrides)
    return row


def _evidence(
    cnpj: str,
    field: str,
    value: str,
    *,
    source_kind: str = "regulamento",
    source_id: str = "1001",
    date: str = "2026-06-30",
    page: str = "10",
    nature: str = "",
    confidence: float = 1.0,
    status: str = "encontrado_explicito",
) -> dict[str, object]:
    return {
        "cnpj": cnpj,
        "field": field,
        "value": value,
        "status": status,
        "source_kind": source_kind,
        "source_id": source_id,
        "document_class": source_kind,
        "document_date": date,
        "page": page,
        "nature": nature,
        "confidence": confidence,
    }


def _enrich(
    audit: pd.DataFrame,
    *,
    cedents: pd.DataFrame | None = None,
    evidence: pd.DataFrame | None = None,
) -> pd.DataFrame:
    return enrich_emission_field_audit(
        audit,
        cedent_triage=cedents if cedents is not None else pd.DataFrame(),
        documentary_evidence=[evidence if evidence is not None else pd.DataFrame()],
    )


def test_curated_remuneration_uses_exact_ranking_cutoff(tmp_path: Path) -> None:
    path = tmp_path / "accepted.csv"
    path.write_text(
        "cutoff,ranking_table,cnpj,fundo,classe_serie,value,source_kind,"
        "source_id,document_date,event_date,page,decision,reason\n"
        "2025-12-31,Financeiro · 2025-12,12345678000190,FIDC TESTE,Sênior,"
        '"CDI + 1,00% a.a.",regulamento,1001,2025-11-30,,10,ACEITA,alvo vigente\n'
        "2026-06-30,Financeiro · 2026-06,12345678000190,FIDC TESTE,Sênior,"
        '"CDI + 0,80% a.a.",assembleia,2002,2026-04-30,,2,ACEITA,alvo revisto\n',
        encoding="utf-8",
    )
    evidence = load_curated_remuneration_evidence(path)
    audit = pd.DataFrame(
        [
            _audit_row("12345678000190", table="Financeiro · 2025-12"),
            _audit_row("12345678000190", table="Financeiro · 2026-06"),
        ]
    )

    result = _enrich(audit, evidence=evidence)

    assert result["remuneracao_por_tipo_cota"].tolist() == [
        "Sênior: CDI + 1,00% a.a.",
        "Sênior: CDI + 0,80% a.a.",
    ]
    assert "1001" in result.iloc[0]["fonte_remuneracao"]
    assert "2002" in result.iloc[1]["fonte_remuneracao"]


def test_exact_cnpj14_join_keeps_legal_cedent_separate_from_originator() -> None:
    target = "12345678000190"
    sibling = "12345678000270"
    audit = pd.DataFrame([_audit_row(target)])
    cedents = pd.DataFrame(
        [
            {
                "cnpj_fundo": target,
                "cedente_declarado_flag": True,
                "cedente_razao_social_consolidada": "CEDENTE LEGAL CORRETO S.A.",
            },
            {
                "cnpj_fundo": sibling,
                "cedente_declarado_flag": True,
                "cedente_razao_social_consolidada": "CEDENTE DO FUNDO IRMÃO S.A.",
            },
        ]
    )
    evidence = pd.DataFrame(
        [
            _evidence(target, "originador", "ORIGINADOR ECONÔMICO CORRETO LTDA."),
            _evidence(sibling, "originador", "ORIGINADOR DO FUNDO IRMÃO LTDA."),
        ]
    )

    result = _enrich(audit, cedents=cedents, evidence=evidence).iloc[0]

    assert result["cnpj"] == target
    assert result["originador"] == "ORIGINADOR ECONÔMICO CORRETO LTDA."
    assert result["cedente"] == "CEDENTE LEGAL CORRETO S.A."
    assert result["originador"] != result["cedente"]
    assert "FUNDO IRMÃO" not in result["originador"]
    assert "FUNDO IRMÃO" not in result["cedente"]
    assert "regulamento" in result["fonte_originador"]
    assert "Tabela I" in result["fonte_cedente"]


def test_documentary_priority_prefers_regulation_over_later_sources() -> None:
    cnpj = "11111111000191"
    audit = pd.DataFrame([_audit_row(cnpj)])
    evidence = pd.DataFrame(
        [
            _evidence(
                cnpj,
                "originador",
                "ORIGINADOR DO REGULAMENTO",
                source_kind="regulamento",
                source_id="REG-1",
                date="2025-01-01",
                confidence=0.1,
            ),
            _evidence(
                cnpj,
                "originador",
                "ORIGINADOR DA EMISSÃO",
                source_kind="emissao",
                source_id="EMI-2",
                date="2026-06-30",
                confidence=1.0,
            ),
            _evidence(
                cnpj,
                "originador",
                "ORIGINADOR DA ASSEMBLEIA",
                source_kind="assembleia",
                source_id="AGE-3",
                date="2026-07-01",
                confidence=1.0,
            ),
            _evidence(
                cnpj,
                "originador",
                "ORIGINADOR DO INFORME",
                source_kind="informe_mensal",
                source_id="CVM-4",
                date="2026-07-31",
                confidence=1.0,
            ),
            _evidence(
                cnpj,
                "originador",
                "EXTRAÇÃO AINDA NÃO APROVADA",
                source_kind="candidate_extraction",
                source_id="CAND-5",
                date="2026-08-01",
                confidence=1.0,
            ),
        ]
    )

    result = _enrich(audit, evidence=evidence).iloc[0]

    assert result["originador"] == "ORIGINADOR DO REGULAMENTO"
    assert "REG-1" in result["fonte_originador"]
    assert "EMI-2" not in result["fonte_originador"]


def test_evidence_after_june_cutoff_does_not_fill_the_deck() -> None:
    cnpj = "11111111000191"
    audit = pd.DataFrame([_audit_row(cnpj)])
    evidence = pd.DataFrame(
        [
            _evidence(
                cnpj,
                "originador",
                "ORIGINADOR POSTERIOR AO CORTE",
                source_id="JUL-1",
                date="2026-07-01",
            )
        ]
    )

    result = _enrich(audit, evidence=evidence).iloc[0]

    assert result["originador"] == "N/D"


def test_profile_prose_only_fills_named_cedent_and_usable_debtor() -> None:
    profiles = pd.DataFrame(
        [
            {
                "cnpj_fundo": "26287464000114",
                "denominacao": "TAPSO",
                "cedente_originador": "Estabelecimentos Stone/Pagar.me",
                "sacado_devedor": "Stone e Pagar.me",
                "natureza_recebiveis": "Recebíveis de pagamento",
                "documentos_primarios_ids": "1066031",
                "data_consulta": "2026-07-16",
            },
            {
                "cnpj_fundo": "53263761000100",
                "denominacao": "ESPERANZA",
                "cedente_originador": "Pessoas que transfiram direitos; nomes não identificados",
                "sacado_devedor": "Entes públicos e demais devedores",
                "natureza_recebiveis": "Precatórios e NPL",
                "documentos_primarios_ids": "830304",
                "data_consulta": "2026-07-16",
            },
            {
                "cnpj_fundo": "53286499000101",
                "denominacao": "ITAÚ CRÉDITO PRIVADO",
                "cedente_originador": "Não identificado como entidade única",
                "sacado_devedor": "Emissores ou devedores dos instrumentos",
                "natureza_recebiveis": "Crédito privado multicarteira",
                "documentos_primarios_ids": "579249;579248",
                "data_consulta": "2026-07-16",
            },
        ]
    )

    evidence, mapping = build_profile_curation_evidence(profiles)

    tapso = evidence[evidence["cnpj"].eq("26287464000114")]
    esperanza = evidence[evidence["cnpj"].eq("53263761000100")]
    itau = evidence[evidence["cnpj"].eq("53286499000101")]
    assert set(tapso["field"]) == {"cedente", "sacado_devedor"}
    assert tapso.loc[tapso["field"].eq("cedente"), "value"].item() == (
        "Stone/Pagar.me"
    )
    assert set(esperanza["field"]) == {"sacado_devedor"}
    assert itau.empty
    mapped = mapping.set_index("cnpj")
    assert mapped.loc["26287464000114", "classificacao_cedente_originador"] == (
        "entidade_ou_ecossistema_nomeado"
    )
    assert mapped.loc["53263761000100", "classificacao_cedente_originador"] == (
        "categoria_sem_entidade_nomeada"
    )
    assert mapped.loc["53286499000101", "classificacao_sacado_devedor"] == (
        "nao_utilizavel"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "Estabelecimentos credenciados, representados por Stone/Pagar.me",
            "entidade_ou_ecossistema_nomeado",
        ),
        (
            "Parati Crédito, Financiamento e Investimento S.A.",
            "entidade_ou_ecossistema_nomeado",
        ),
        (
            "Instituições financeiras que concedam as CCBs; nomes individuais não identificados",
            "categoria_sem_entidade_nomeada",
        ),
        (
            "Múltiplos Originadores de Diversos Setores",
            "categoria_sem_entidade_nomeada",
        ),
        (
            "Ausência de cedente ou originador nominal; definição genérica",
            "nao_localizado",
        ),
        (
            "Candidato textual para validação (p. 36): CEDENTES",
            "categoria_sem_entidade_nomeada",
        ),
        ("Não localizado nas fontes consultadas", "nao_localizado"),
    ],
)
def test_party_classifier_uses_the_function_of_the_phrase(
    value: str,
    expected: str,
) -> None:
    assert classify_party_value(value) == expected


def test_generic_party_prose_does_not_inflate_documentary_coverage() -> None:
    cnpj = "11111111000191"
    audit = pd.DataFrame([_audit_row(cnpj)])
    evidence = pd.DataFrame(
        [
            _evidence(
                cnpj,
                "cedente",
                "todas as pessoas físicas ou jurídicas que cedem os Direitos Creditórios",
            ),
            _evidence(
                cnpj,
                "originador",
                "Múltiplos Originadores de Diversos Setores",
                source_kind="rating_report",
            ),
        ]
    )

    result = _enrich(audit, evidence=evidence).iloc[0]

    assert result["cedente"] == "N/D"
    assert result["originador"] == "N/D"


def test_profile_only_fills_originator_when_role_is_explicit() -> None:
    profiles = pd.DataFrame(
        [
            {
                "cnpj_fundo": "42922136000107",
                "denominacao": "MONEE I",
                "cedente_originador": (
                    "SHPP Brasil Instituição de Pagamento Ltda. atua como "
                    "originadora/correspondente"
                ),
                "sacado_devedor": "Tomadores dos empréstimos",
                "natureza_recebiveis": "CCB e recebíveis de pagamento",
                "documentos_primarios_ids": "1001",
                "data_consulta": "2026-07-16",
            }
        ]
    )

    evidence, mapping = build_profile_curation_evidence(profiles)

    assert set(evidence["field"]) == {
        "originador",
        "cedente",
        "sacado_devedor",
    }
    assert mapping.iloc[0]["aplicacao_como_originador"] == (
        "aceito_papel_explicito"
    )
    assert mapping.iloc[0]["valor_aplicado_como_originador"] == "SHPP Brasil"


def test_taxonomy_review_only_emits_named_explicit_party_roles() -> None:
    review = pd.DataFrame(
        [
            {
                "cnpj_fundo": "59356753000187",
                "document_id": "1001065",
                "document_reference_date": "2025-11-07",
                "document_url": "https://example.test/1001065",
                "pagina_clausula": "p. 75",
                "cedent_originator_explicit": "ÂMBAR ENERGIA S.A.",
                "evidence_summary": (
                    "A Âmbar é credora original e cedente dos recebíveis."
                ),
                "confianca_documental": "alta",
            },
            {
                "cnpj_fundo": "11468186000124",
                "document_id": "1130307",
                "document_reference_date": "2026-02-01",
                "document_url": "https://example.test/1130307",
                "pagina_clausula": "p. 4",
                "cedent_originator_explicit": (
                    "Ausência de entidade nominal; múltiplos cedentes"
                ),
                "evidence_summary": "Cedentes definidos genericamente.",
                "confianca_documental": "media",
            },
            {
                "cnpj_fundo": "50906397000153",
                "document_id": "771809",
                "document_reference_date": "2026-01-01",
                "document_url": "https://example.test/771809",
                "pagina_clausula": "p. 36",
                "cedent_originator_explicit": (
                    "Candidato textual para validação (p. 36): CEDENTE"
                ),
                "evidence_summary": "Fragmento automático truncado.",
                "confianca_documental": "baixa",
            },
        ]
    )

    evidence = build_taxonomy_party_evidence(review)

    assert set(evidence["cnpj"]) == {"59356753000187"}
    assert set(evidence["field"]) == {"originador", "cedente"}
    assert set(evidence["source_id"]) == {"1001065"}


def test_party_without_identified_source_is_not_counted_as_audited() -> None:
    cnpj = "55555555000195"
    audit = pd.DataFrame(
        [
            _audit_row(
                cnpj,
                originador="NOME SEM DOCUMENTO",
                cedente="NOME SEM DOCUMENTO",
                fonte_originador_cedente="N/D — sem documento identificado",
            )
        ]
    )

    result = _enrich(audit).iloc[0]

    assert result["originador"] == "N/D"
    assert result["cedente"] == "N/D"
    assert "origem" not in result["fonte_originador"].lower()


def test_minimum_junior_and_structural_are_labeled_separately() -> None:
    junior_cnpj = "22222222000192"
    structural_cnpj = "33333333000193"
    audit = pd.DataFrame(
        [
            _audit_row(junior_cnpj),
            _audit_row(structural_cnpj),
        ]
    )
    evidence = pd.DataFrame(
        [
            _evidence(
                junior_cnpj,
                "minimo_junior",
                "10,0%",
                source_id="JR-10",
                nature="junior_pl",
            ),
            _evidence(
                structural_cnpj,
                "minimo_estrutural_total",
                "25,0%",
                source_id="EST-25",
                nature="suporte_total_pl",
            ),
        ]
    )

    result = _enrich(audit, evidence=evidence).set_index("cnpj")

    assert result.loc[junior_cnpj, "subordinacao_minima"] == "Jr. 10,0%"
    assert not result.loc[junior_cnpj, "subordinacao_minima"].endswith("*")
    assert result.loc[junior_cnpj, "tipo_subordinacao_minima"] == "júnior"
    assert result.loc[structural_cnpj, "subordinacao_minima"] == "Estrut. 25,0%*"
    assert result.loc[structural_cnpj, "tipo_subordinacao_minima"] == "suporte_total_pl"
    assert "EST-25" in result.loc[structural_cnpj, "fonte_subordinacao"]


def test_remuneration_keeps_each_class_from_latest_document_event() -> None:
    cnpj = "44444444000194"
    audit = pd.DataFrame([_audit_row(cnpj)])
    evidence = pd.DataFrame(
        [
            _evidence(
                cnpj,
                "remuneracao_alvo",
                "Sênior A: CDI + 1,00% a.a.",
                source_kind="emissao",
                source_id="EMI-100",
                date="2026-06-10",
                page="2",
                nature="rentabilidade-alvo documentada · Sênior A",
            ),
            _evidence(
                cnpj,
                "remuneracao_alvo",
                "Sênior B: CDI + 1,15% a.a.",
                source_kind="emissao",
                source_id="EMI-100",
                date="2026-06-10",
                page="3",
                nature="rentabilidade-alvo documentada · Sênior B",
            ),
            _evidence(
                cnpj,
                "remuneracao_alvo",
                "Sênior C: CDI + 0,80% a.a.",
                source_kind="regulamento",
                source_id="REG-200",
                date="2026-06-30",
                page="50",
                nature="rentabilidade-alvo documentada · Sênior C",
            ),
        ]
    )

    result = _enrich(audit, evidence=evidence).iloc[0]

    assert result["remuneracao_por_tipo_cota"] == "Sênior C: CDI + 0,80% a.a."
    assert "EMI-100" not in result["fonte_remuneracao"]
    assert "REG-200" in result["fonte_remuneracao"]


def _eight_page_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    before_rows: list[dict[str, str]] = []
    ranking_rows: list[dict[str, object]] = []
    serial = 1
    for type_name in (
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    ):
        for period in ("2025-12", "2026-06"):
            table = f"{type_name} · {period}"
            for rank in range(1, 16):
                cnpj = f"{serial:014d}"
                serial += 1
                before_rows.append(_audit_row(cnpj, table=table))
                ranking_rows.append(
                    {
                        "cnpj_fundo": cnpj,
                        "tipo_exibicao": type_name,
                        "competencia": period,
                        "rank_tipo": rank,
                        "pl": 9.0 if rank == 1 else 1.0,
                    }
                )
    before = pd.DataFrame(before_rows)
    after = before.copy()
    rank_in_page = after.groupby("tabela", sort=False).cumcount() + 1
    after.loc[rank_in_page.eq(1), "originador"] = "Originador documentado"
    after.loc[rank_in_page.le(3), "cedente"] = "Cedente legal declarado"
    after.loc[rank_in_page.eq(1), "subordinacao_minima"] = "Jr. 10,0%"
    after.loc[rank_in_page.eq(1), "remuneracao_por_tipo_cota"] = "Sênior: CDI + 1,00% a.a."
    after.loc[rank_in_page.eq(1), "sacado"] = "Sacado documentado"
    return before, after, pd.DataFrame(ranking_rows)


def test_coverage_contract_measures_all_eight_pages_in_rows_and_pl() -> None:
    before, after, ranking = _eight_page_frames()

    coverage = build_emission_field_coverage(before, after, ranking)

    assert len(coverage) == 8 * 5
    assert coverage["tabela"].nunique() == 8
    assert coverage["linhas_total"].eq(15).all()
    assert coverage["antes_com_dado"].eq(0).all()
    assert coverage.loc[coverage["campo"].eq("originador"), "depois_com_dado"].eq(1).all()
    assert coverage.loc[coverage["campo"].eq("cedente"), "depois_com_dado"].eq(3).all()
    assert coverage.loc[
        coverage["campo"].isin(("subordinacao_minima", "remuneracao_por_tipo_cota", "sacado")),
        "depois_com_dado",
    ].eq(1).all()
    assert coverage.loc[
        coverage["campo"].eq("originador"), "depois_cobertura_pl_pct"
    ].tolist() == pytest.approx([9 / 23] * 8)
    assert coverage.loc[
        coverage["campo"].eq("cedente"), "depois_cobertura_pl_pct"
    ].tolist() == pytest.approx([11 / 23] * 8)
    assert validate_emission_field_coverage(coverage.to_dict(orient="records")) == []


def test_publication_guard_rejects_an_entire_nd_column_on_one_page() -> None:
    before, after, ranking = _eight_page_frames()
    failed_table = "Outros · 2026-06"
    after.loc[after["tabela"].eq(failed_table), "sacado"] = "N/D"
    coverage = build_emission_field_coverage(before, after, ranking)

    violations = validate_emission_field_coverage(coverage.to_dict(orient="records"))

    assert len(violations) == 1
    assert failed_table in violations[0]
    assert "sacado: 0/15" in violations[0]
    assert "abaixo do piso" in violations[0]


def test_remuneration_allows_a_documentary_gap_on_one_page_but_not_globally() -> None:
    before, after, ranking = _eight_page_frames()
    gap_table = "Outros · 2026-06"
    after.loc[
        after["tabela"].eq(gap_table),
        "remuneracao_por_tipo_cota",
    ] = "N/D"
    partial = build_emission_field_coverage(before, after, ranking)

    assert validate_emission_field_coverage(partial.to_dict(orient="records")) == []

    after["remuneracao_por_tipo_cota"] = "N/D"
    empty = build_emission_field_coverage(before, after, ranking)
    violations = validate_emission_field_coverage(empty.to_dict(orient="records"))

    assert violations == [
        "slides 10–17 · remuneração-alvo: coluna inteira sem evidência documental"
    ]


def test_originator_waiver_is_limited_to_outros_and_keeps_a_reason() -> None:
    before, after, ranking = _eight_page_frames()
    after.loc[after["tabela"].str.startswith("Outros ·"), "originador"] = "N/D"
    coverage = build_emission_field_coverage(before, after, ranking)

    outros_originator = coverage[
        coverage["tabela"].str.startswith("Outros ·")
        & coverage["campo"].eq("originador")
    ]
    assert outros_originator["depois_com_dado"].eq(0).all()
    assert outros_originator["excecao_publicacao"].str.startswith(
        "documentos identificados"
    ).all()
    assert validate_emission_field_coverage(coverage.to_dict(orient="records")) == []

    failed_table = "Fomento Mercantil · 2026-06"
    after.loc[after["tabela"].eq(failed_table), "originador"] = "N/D"
    failed = build_emission_field_coverage(before, after, ranking)
    violations = validate_emission_field_coverage(failed.to_dict(orient="records"))
    assert any(failed_table in item and "originador: 0/15" in item for item in violations)
