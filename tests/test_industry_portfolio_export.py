from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from services.industry_portfolio_export import (
    build_industry_portfolio_export,
    build_industry_portfolio_export_from_payload,
)


def _cnpj(index: int) -> str:
    return f"{index:014d}"


def _portfolio_detail(rows: list[dict[str, object]]) -> pd.DataFrame:
    defaults: dict[str, object] = {
        "ordem": 1,
        "cnpj_fundo": _cnpj(1),
        "denominacao": "FUNDO TESTE",
        "nome_foto": "Fundo teste",
        "status_identidade": "localizado",
        "pl_atual_brl": 100.0,
        "pl_classes_reportadas_brl": 100.0,
        "pl_subordinado_atual_brl": 20.0,
        "subordinacao_atual_pct": 0.20,
        "subordinacao_atual_status": "calculado",
        "subordinacao_minima_junior_pct": np.nan,
        "suporte_estrutural_minimo_pct": np.nan,
        "subordinacao_minima_natureza": "sem_indice",
        "subordinacao_minima_junior_display": "N/D",
        "suporte_estrutural_minimo_display": "N/D",
        "subordinacao_minima_formula": "N/D",
        "comparabilidade_tranche_flag": "false",
        "comparabilidade_tranche_motivo": "N/D",
        "tipo_exibicao": "Financeiro",
        "foco_exibicao": "Crédito Pessoal",
        "documento_id_regulamento": "DOC-1",
        "documento_data_regulamento": "2026-01-01",
        "pagina_clausula": "10",
        "status_curadoria_documental": "revisto",
        "subordinacao_minima_fonte": "regulamento",
        "subordinacao_minima_texto": "texto",
    }
    return pd.DataFrame([{**defaults, **row} for row in rows])


def _structural(rows: list[dict[str, object]]) -> pd.DataFrame:
    defaults: dict[str, object] = {
        "cnpj": _cnpj(1),
        "sub_jr_min_regulamento": np.nan,
        "minimo_estrutural_display": "N/D",
        "minimo_estrutural_natureza": "sem_indice",
        "minimo_estrutural_formula": "N/D",
        "comparacao_estrutural_completa_flag": False,
        "comparacao_estrutural_motivo": "incomparável",
        "excecao_asterisco_flag": False,
        "folga_pp": np.nan,
        "perda_ate_gatilho": np.nan,
        "situacao_regulatoria": "não medido",
        "mvp_slide_categoria": "N/D",
        "mvp_faixa_sub_atual": "N/D",
        "mvp_elegivel_flag": False,
        "mvp_situacao_piso": "N/D",
        "categoria": "Financeiro",
        "data_ref": "2026-06",
    }
    return pd.DataFrame([{**defaults, **row} for row in rows])


def _flagships(rows: list[dict[str, object]]) -> pd.DataFrame:
    defaults: dict[str, object] = {
        "ordem_familia": 1,
        "cnpj_fundo": _cnpj(101),
        "denominacao": "FLAGSHIP TESTE",
        "familia_flagship": "Flagship teste",
        "categoria": "Financeiro",
        "pl_atual_brl": 100.0,
        "pl_classes_reportadas_brl": 100.0,
        "pl_subordinado_atual_brl": 20.0,
        "subordinacao_atual_pct": 0.20,
        "subordinacao_atual_status": "calculado",
        "subordinacao_minima_junior_pct": np.nan,
        "subordinacao_minima_junior_display": "N/D",
        "subordinacao_minima_texto": "N/D",
        "cota_mezanino": "N/D",
        "documento_id_regulamento": "DOC-F",
        "documento_data_regulamento": "2026-01-01",
        "pagina_clausula": "12",
        "status_curadoria_documental": "revisto",
        "subordinacao_minima_fonte": "regulamento",
    }
    return pd.DataFrame([{**defaults, **row} for row in rows])


def test_portfolio_keeps_minimum_natures_separate_and_uses_existing_metrics() -> None:
    detail = _portfolio_detail(
        [
            {
                "ordem": 1,
                "cnpj_fundo": _cnpj(1),
                "subordinacao_minima_natureza": "junior_pl",
                "subordinacao_minima_junior_pct": 5.0,
                "suporte_estrutural_minimo_pct": 7.0,
            },
            {
                "ordem": 2,
                "cnpj_fundo": _cnpj(2),
                "subordinacao_minima_natureza": "junior_pl_calculado",
                "subordinacao_minima_junior_pct": 4.0,
                "suporte_estrutural_minimo_pct": 4.0,
            },
            {
                "ordem": 3,
                "cnpj_fundo": _cnpj(3),
                "subordinacao_minima_natureza": "junior_pl_ajustado",
                "subordinacao_minima_junior_pct": 3.0,
            },
            {
                "ordem": 4,
                "cnpj_fundo": _cnpj(4),
                "subordinacao_minima_natureza": "suporte_combinado_pl",
                "suporte_estrutural_minimo_pct": 9.2,
            },
            {
                "ordem": 5,
                "cnpj_fundo": _cnpj(5),
                "subordinacao_minima_natureza": "suporte_total_pl",
                "suporte_estrutural_minimo_pct": 10.0,
            },
            {
                "ordem": 6,
                "cnpj_fundo": _cnpj(6),
                "status_identidade": "fora_base_fidc",
                "denominacao": "NOME DA FOTO USADO COMO FALLBACK",
                "subordinacao_minima_natureza": "fora_perimetro",
            },
        ]
    )
    structural = _structural(
        [
            {
                "cnpj": _cnpj(1),
                "sub_jr_min_regulamento": 0.07,
                "comparacao_estrutural_completa_flag": True,
                "folga_pp": 0.13,
                "perda_ate_gatilho": 0.139784946,
            },
            {
                "cnpj": _cnpj(2),
                "sub_jr_min_regulamento": 0.04,
                "comparacao_estrutural_completa_flag": True,
                "folga_pp": 0.16,
                "perda_ate_gatilho": 0.166666667,
            },
            {
                "cnpj": _cnpj(3),
                "sub_jr_min_regulamento": 0.03,
                "comparacao_estrutural_completa_flag": False,
                "folga_pp": 999.0,
                "perda_ate_gatilho": 999.0,
                "mvp_slide_categoria": "Financeiro",
                "mvp_faixa_sub_atual": "20%–35%",
                "mvp_elegivel_flag": True,
                "mvp_situacao_piso": "acima do piso",
            },
            {
                "cnpj": _cnpj(4),
                "sub_jr_min_regulamento": 0.092,
                "comparacao_estrutural_completa_flag": True,
                "folga_pp": 0.108,
                "perda_ate_gatilho": 0.118942731,
            },
            {
                "cnpj": _cnpj(5),
                "sub_jr_min_regulamento": 0.10,
                "comparacao_estrutural_completa_flag": True,
                "folga_pp": 0.10,
                "perda_ate_gatilho": 0.111111111,
            },
            {"cnpj": _cnpj(6)},
        ]
    )

    result = build_industry_portfolio_export(
        carteira_detail=detail,
        carteira_structural=structural,
        flagship_detail=_flagships([]),
        data_ref="2026-06",
    )
    rows = result.carteira.set_index("cnpj")

    assert rows.loc[_cnpj(1), "minimo_junior_literal"] == 0.05
    assert rows.loc[_cnpj(1), "suporte_total"] == 0.07
    assert rows.loc[_cnpj(2), "minimo_junior_calculado"] == 0.04
    assert rows.loc[_cnpj(3), "minimo_junior_ajustado"] == 0.03
    assert rows.loc[_cnpj(4), "suporte_combinado_junior_mezanino"] == 0.092
    assert rows.loc[_cnpj(5), "suporte_total"] == 0.10
    assert math.isnan(rows.loc[_cnpj(3), "folga_pp"])
    assert math.isnan(rows.loc[_cnpj(3), "capacidade_ate_gatilho"])
    assert rows.loc[_cnpj(3), "mvp_elegivel_flag"]
    assert rows.loc[_cnpj(3), "mvp_situacao_piso"] == "acima do piso"
    assert rows.loc[_cnpj(1), "folga_pp"] == 0.13
    assert rows.loc[_cnpj(1), "cnpj_numerico"] == 1
    assert rows.loc[_cnpj(1), "cnpj_formatado"] == "00.000.000/0000-01"
    assert rows.loc[_cnpj(6), "nome_oficial_cvm"] == "N/D"
    assert rows.loc[_cnpj(6), "status_preenchimento"] == "fora_perimetro"


def test_manual_overlay_fills_only_gaps_and_never_splits_combined_role() -> None:
    detail = _portfolio_detail(
        [
            {
                "ordem": 1,
                "cnpj_fundo": _cnpj(1),
                "originador": "Originador documental",
                "cedente": "N/D",
            },
            {"ordem": 2, "cnpj_fundo": _cnpj(2)},
        ]
    )
    structural = _structural(
        [{"cnpj": _cnpj(1)}, {"cnpj": _cnpj(2)}]
    )
    manual = pd.DataFrame(
        [
            {
                "cnpj_fundo": _cnpj(1),
                "cedente_originador_literal": "Cedente / Originador da foto",
                "originador": "Originador da foto",
                "cedente": "Cedente da foto",
                "sacado": "Sacado da foto",
                "tipo_recebivel": "Duplicatas",
                "fonte_imagem": "IMG_8704.JPG",
                "status_transcricao": "confirmado_legivel",
            },
            {
                "cnpj_fundo": _cnpj(2),
                "cedente_originador_literal": "Papel ambíguo",
                "fonte_imagem": "IMG_8705.JPG",
                "status_transcricao": "confirmado",
            },
        ]
    )

    result = build_industry_portfolio_export(
        carteira_detail=detail,
        carteira_structural=structural,
        flagship_detail=_flagships([]),
        manual_enrichment=manual,
    )
    rows = result.carteira.set_index("cnpj")

    assert rows.loc[_cnpj(1), "originador"] == "Originador documental"
    assert rows.loc[_cnpj(1), "cedente"] == "Cedente da foto"
    assert rows.loc[_cnpj(1), "sacado_devedor"] == "Sacado da foto"
    assert rows.loc[_cnpj(1), "tipo_recebivel_literal"] == "Duplicatas"
    assert rows.loc[_cnpj(1), "fonte_partes_recebivel"] == "IMG_8704.JPG"
    assert rows.loc[_cnpj(2), "cedente_originador_literal"] == "Papel ambíguo"
    assert rows.loc[_cnpj(2), "originador"] == "N/D"
    assert rows.loc[_cnpj(2), "cedente"] == "N/D"
    assert result.manual["aplicado_flag"].tolist() == [True, True]

    with pytest.raises(ValueError, match="CNPJ duplicado"):
        build_industry_portfolio_export(
            carteira_detail=detail,
            carteira_structural=structural,
            flagship_detail=_flagships([]),
            manual_enrichment=pd.concat([manual.iloc[[0]], manual.iloc[[0]]]),
        )


def test_unapproved_manual_transcription_is_audited_but_not_applied() -> None:
    detail = _portfolio_detail([{"cnpj_fundo": _cnpj(1)}])
    manual = pd.DataFrame(
        [
            {
                "cnpj": _cnpj(1),
                "originador": "Texto a revisar",
                "status_transcricao": "pendente",
            }
        ]
    )
    result = build_industry_portfolio_export(
        carteira_detail=detail,
        carteira_structural=_structural([{"cnpj": _cnpj(1)}]),
        flagship_detail=_flagships([]),
        manual_enrichment=manual,
    )

    assert result.carteira.loc[0, "originador"] == "N/D"
    assert not bool(result.manual.loc[0, "aplicado_flag"])
    assert result.manual.loc[0, "motivo_aplicacao"] == (
        "status de transcrição não aprovado"
    )


def test_unmatched_manual_root_is_explicit_and_does_not_block_export() -> None:
    canonical_cnpj = "43616659000180"
    detail = _portfolio_detail(
        [{"cnpj_fundo": canonical_cnpj, "denominacao": "TALO 1 FIDC"}]
    )
    manual = pd.DataFrame(
        [
            {
                "raiz_cnpj_foto": "43616658",
                "cedente": "Yara",
                "status_transcricao": "confirmado_legivel",
            }
        ]
    )

    result = build_industry_portfolio_export(
        carteira_detail=detail,
        carteira_structural=_structural([{"cnpj": canonical_cnpj}]),
        flagship_detail=_flagships([]),
        manual_enrichment=manual,
    )

    assert result.carteira.loc[0, "cedente"] == "N/D"
    assert result.manual.loc[0, "cnpj"] == ""
    assert result.manual.loc[0, "raiz_cnpj_foto"] == "43616658"
    assert result.manual.loc[0, "status_resolucao_cnpj"] == "sem_correspondencia"
    assert result.manual.loc[0, "quantidade_candidatos_cnpj"] == 0
    assert result.manual.loc[0, "candidatos_cnpj"] == ""
    assert not bool(result.manual.loc[0, "aplicado_flag"])
    assert result.manual.loc[0, "motivo_aplicacao"] == (
        "raiz de CNPJ não resolvida nas duas coortes"
    )


def test_unique_manual_root_resolves_and_revision_status_never_applies() -> None:
    confirmed_cnpj = "43616659000180"
    revision_cnpj = "52343195000104"
    detail = _portfolio_detail(
        [
            {"ordem": 1, "cnpj_fundo": confirmed_cnpj},
            {"ordem": 2, "cnpj_fundo": revision_cnpj},
        ]
    )
    manual = pd.DataFrame(
        [
            {
                "raiz_cnpj_foto": "43616659",
                "cedente": "Yara",
                "status_transcricao": "confirmado_legivel",
            },
            {
                "raiz_cnpj_foto": "52343195",
                "cedente": "FARM",
                "status_transcricao": "revisao",
            },
        ]
    )

    result = build_industry_portfolio_export(
        carteira_detail=detail,
        carteira_structural=_structural(
            [{"cnpj": confirmed_cnpj}, {"cnpj": revision_cnpj}]
        ),
        flagship_detail=_flagships([]),
        manual_enrichment=manual,
    )
    rows = result.carteira.set_index("cnpj")
    audit = result.manual.set_index("raiz_cnpj_foto")

    assert rows.loc[confirmed_cnpj, "cedente"] == "Yara"
    assert rows.loc[revision_cnpj, "cedente"] == "N/D"
    assert audit.loc["43616659", "cnpj"] == confirmed_cnpj
    assert audit.loc["43616659", "status_resolucao_cnpj"] == (
        "correspondencia_unica"
    )
    assert audit.loc["43616659", "quantidade_candidatos_cnpj"] == 1
    assert bool(audit.loc["43616659", "aplicado_flag"])
    assert audit.loc["52343195", "motivo_aplicacao"] == (
        "status de transcrição não aprovado"
    )


def test_ambiguous_manual_root_fails_closed() -> None:
    root = "12345678"
    first_cnpj = f"{root}000101"
    second_cnpj = f"{root}000292"
    detail = _portfolio_detail(
        [
            {"ordem": 1, "cnpj_fundo": first_cnpj},
            {"ordem": 2, "cnpj_fundo": second_cnpj},
        ]
    )

    with pytest.raises(ValueError, match="raiz manual ambígua"):
        build_industry_portfolio_export(
            carteira_detail=detail,
            carteira_structural=_structural(
                [{"cnpj": first_cnpj}, {"cnpj": second_cnpj}]
            ),
            flagship_detail=_flagships([]),
            manual_enrichment=pd.DataFrame(
                [
                    {
                        "raiz_cnpj_foto": root,
                        "cedente": "Texto manual",
                        "status_transcricao": "confirmado_legivel",
                    }
                ]
            ),
        )


def test_flagship_headroom_requires_documented_tranche_comparability() -> None:
    detail = _flagships(
        [
            {
                "ordem_familia": 1,
                "cnpj_fundo": _cnpj(101),
                "subordinacao_atual_pct": 0.12,
                "subordinacao_minima_junior_pct": 5.0,
                "subordinacao_minima_junior_display": "5,0%",
                "subordinacao_minima_texto": (
                    "Cotas subordinadas / PL, mínimo de 5,0%; a estrutura não "
                    "tem mezanino no regulamento lido."
                ),
            },
            {
                "ordem_familia": 2,
                "cnpj_fundo": _cnpj(102),
                "subordinacao_atual_pct": 0.20,
                "subordinacao_minima_junior_pct": 10.0,
                "subordinacao_minima_junior_display": "10,0%",
                "subordinacao_minima_texto": "Cota júnior / PL, mínimo de 10%.",
                "cota_mezanino": "Sim",
            },
            {
                "ordem_familia": 3,
                "cnpj_fundo": _cnpj(103),
                "subordinacao_atual_pct": 0.30,
                "subordinacao_minima_junior_pct": 15.0,
                "subordinacao_minima_junior_display": "15,0%",
                "subordinacao_minima_texto": "Cota júnior / PL, mínimo de 15%.",
                "cota_mezanino": "N/D",
            },
        ]
    )

    result = build_industry_portfolio_export(
        carteira_detail=_portfolio_detail([]),
        carteira_structural=_structural([]),
        flagship_detail=detail,
        data_ref="2026-06",
    )
    rows = result.flagships.set_index("cnpj")

    assert bool(rows.loc[_cnpj(101), "comparavel_flag"])
    assert rows.loc[_cnpj(101), "folga_pp"] == pytest.approx(0.07)
    assert rows.loc[_cnpj(101), "capacidade_ate_gatilho"] == pytest.approx(
        (0.12 - 0.05) / (1.0 - 0.05)
    )
    for cnpj in (_cnpj(102), _cnpj(103)):
        assert not bool(rows.loc[cnpj, "comparavel_flag"])
        assert math.isnan(rows.loc[cnpj, "folga_pp"])
        assert math.isnan(rows.loc[cnpj, "capacidade_ate_gatilho"])
        assert bool(rows.loc[cnpj, "excecao_asterisco_flag"])


def test_payload_wrapper_builds_count_and_pl_coverage_without_zero_imputation() -> None:
    detail = _portfolio_detail(
        [
            {
                "ordem": 1,
                "cnpj_fundo": _cnpj(1),
                "pl_atual_brl": 100.0,
            },
            {
                "ordem": 2,
                "cnpj_fundo": _cnpj(2),
                "pl_atual_brl": np.nan,
                "subordinacao_atual_pct": np.nan,
            },
        ]
    )
    payload = {
        "latest_complete": "2026-06",
        "carteira_1_curation": detail.to_dict("records"),
        "carteira_1_structural_assets": _structural(
            [{"cnpj": _cnpj(1)}, {"cnpj": _cnpj(2)}]
        ).to_dict("records"),
        "flagship_curation": [],
    }

    result = build_industry_portfolio_export_from_payload(payload)
    coverage = result.coverage.set_index(["coorte", "campo"])
    pl_coverage = coverage.loc[("Carteira 101", "pl_atual_brl")]
    originator_coverage = coverage.loc[("Carteira 101", "originador")]

    assert pl_coverage["linhas_com_dado"] == 1
    assert pl_coverage["linhas_total"] == 2
    assert pl_coverage["cobertura_contagem_pct"] == 0.5
    assert pl_coverage["cobertura_pl_pct"] == 1.0
    assert originator_coverage["linhas_com_dado"] == 0
    assert originator_coverage["pl_com_dado_brl"] == 0.0
    assert originator_coverage["cobertura_pl_pct"] == 0.0
    assert result.carteira.loc[1, "pl_atual_brl"] is np.nan or pd.isna(
        result.carteira.loc[1, "pl_atual_brl"]
    )


def test_price_evidence_keeps_classes_and_uses_latest_best_source() -> None:
    cnpj = _cnpj(1)
    prices = pd.DataFrame(
        [
            {
                "cnpj": cnpj,
                "class_series": "Cota sênior",
                "price_display": "R$ 90.000,00",
                "source_kind": "regulamento",
                "source_id": "DOC-OLD",
                "document_class": "regulamento",
                "document_date": "2025-06-01",
                "source_url": "https://example.test/old",
                "status": "encontrado_explicito",
            },
            {
                "cnpj": cnpj,
                "class_series": "Cota sênior",
                "price_display": "R$ 100.000,00",
                "source_kind": "regulamento",
                "source_id": "DOC-NEW",
                "document_class": "regulamento",
                "document_date": "2026-04-09",
                "source_url": "https://example.test/new",
                "status": "encontrado_explicito",
                "excerpt": "O valor unitário de emissão será R$ 100.000,00.",
            },
            {
                "cnpj": cnpj,
                "class_series": "Cota subordinada júnior",
                "price_display": "R$ 5.000,00",
                "source_kind": "regulamento",
                "source_id": "DOC-NEW",
                "document_class": "regulamento",
                "document_date": "2026-04-09",
                "source_url": "https://example.test/new",
                "status": "encontrado_explicito",
                "excerpt": "O valor unitário de emissão será R$ 5.000,00.",
            },
            {
                "cnpj": cnpj,
                "class_series": "Cota sênior",
                "price_display": "R$ 1.000,00",
                "source_kind": "payload_documental",
                "source_id": "LOWER-PRIORITY",
                "document_class": "emissao",
                "document_date": "2026-05-01",
                "source_url": "https://example.test/lower-priority",
                "status": "aceito_payload",
            },
        ]
    )

    result = build_industry_portfolio_export(
        carteira_detail=_portfolio_detail([{"cnpj_fundo": cnpj}]),
        carteira_structural=_structural([{"cnpj": cnpj}]),
        flagship_detail=_flagships([]),
        carteira_price_evidence=prices,
    )
    row = result.carteira.iloc[0]

    assert pd.isna(row["preco_cota_brl"])
    assert row["preco_cota_display"] == (
        "Cota sênior: R$ 100.000,00 | "
        "Cota subordinada júnior: R$ 5.000,00"
    )
    assert row["preco_cota_classe_serie"] == (
        "Cota sênior | Cota subordinada júnior"
    )
    assert row["preco_cota_natureza"] == "preço/valor unitário de emissão"
    assert bool(row["preco_cota_excecao_asterisco_flag"])
    assert row["preco_cota_documento_data"] == "2026-04-09"
    assert row["preco_cota_documento_id"] == "DOC-NEW"
    assert row["preco_cota_fonte"] == "https://example.test/new"
    assert row["preco_cota_status"].endswith("múltiplos valores/classes")
    assert len(result.prices) == 4
    assert result.prices["price_brl"].map(
        lambda value: isinstance(value, (float, np.floating))
    ).all()
    assert result.prices["aprovado_para_export_flag"].all()
    latest = result.prices[result.prices["source_id"].eq("DOC-NEW")]
    assert latest["price_nature"].eq(
        "preço/valor unitário de emissão"
    ).all()


def test_price_evidence_marks_missing_class_as_asterisk_exception() -> None:
    cnpj = _cnpj(1)
    prices = pd.DataFrame(
        [
            {
                "cnpj": cnpj,
                "class_series": "N/D",
                "price_display": "R$ 1.000,00",
                "source_kind": "emissao",
                "source_id": "DOC-MISSING-CLASS",
                "document_date": "2026-06-30",
                "status": "encontrado_explicito",
                "exception_flag": "*",
                "excerpt": "Valor unitário de emissão: R$ 1.000,00.",
            }
        ]
    )

    result = build_industry_portfolio_export(
        carteira_detail=_portfolio_detail([{"cnpj_fundo": cnpj}]),
        carteira_structural=_structural([{"cnpj": cnpj}]),
        flagship_detail=_flagships([]),
        carteira_price_evidence=prices,
    )

    assert bool(result.prices.iloc[0]["excecao_asterisco_flag"])
    assert bool(result.carteira.iloc[0]["preco_cota_excecao_asterisco_flag"])


def test_price_evidence_parses_brazilian_dates_before_selecting_latest() -> None:
    cnpj = _cnpj(1)
    prices = pd.DataFrame(
        [
            {
                "cnpj": cnpj,
                "class_series": "Cota sênior",
                "price_display": "R$ 90.000,00",
                "source_kind": "regulamento",
                "source_id": "DOC-ISO",
                "document_date": "2025-03-31",
                "source_url": "https://example.test/iso",
                "status": "encontrado_explicito",
                "excerpt": "Valor unitário de emissão de R$ 90.000,00.",
            },
            {
                "cnpj": cnpj,
                "class_series": "Cota sênior",
                "price_display": "R$ 100.000,00",
                "source_kind": "regulamento",
                "source_id": "DOC-BR",
                "document_date": "03/04/2025",
                "source_url": "https://example.test/br",
                "status": "encontrado_explicito",
                "excerpt": "Valor unitário de emissão de R$ 100.000,00.",
            },
        ]
    )

    result = build_industry_portfolio_export(
        carteira_detail=_portfolio_detail([{"cnpj_fundo": cnpj}]),
        carteira_structural=_structural([{"cnpj": cnpj}]),
        flagship_detail=_flagships([]),
        carteira_price_evidence=prices,
    )

    row = result.carteira.iloc[0]
    assert row["preco_cota_documento_id"] == "DOC-BR"
    assert row["preco_cota_documento_data"] == "03/04/2025"
    assert row["preco_cota_display"] == "Cota sênior: R$ 100.000,00"


def test_price_scalar_is_numeric_only_when_unique_and_missing_stays_missing() -> None:
    first_cnpj = _cnpj(1)
    second_cnpj = _cnpj(2)
    third_cnpj = _cnpj(3)
    detail = _portfolio_detail(
        [
            {
                "ordem": 1,
                "cnpj_fundo": first_cnpj,
                "preco_cota_brl": 1_000,
                "preco_cota_display": "R$ 1.000,00",
                "preco_cota_classe_serie": "Cota sênior",
                "preco_cota_documento_data": "2026-06-30",
                "preco_cota_documento_id": "DOC-WIDE",
                "preco_cota_fonte": "regulamento",
            },
            {"ordem": 2, "cnpj_fundo": second_cnpj},
            {"ordem": 3, "cnpj_fundo": third_cnpj},
        ]
    )
    prices = pd.DataFrame(
        [
            {
                "cnpj": first_cnpj,
                "class_series": "Cota sênior",
                "price_display": "R$ 999,00",
                "source_kind": "regulamento",
                "source_id": "SHOULD-NOT-REPLACE",
                "document_date": "2026-07-01",
                "status": "encontrado_explicito",
            },
            {
                "cnpj": second_cnpj,
                "class_series": "Cota sênior",
                "price_display": "R$ 1.000,00",
                "source_kind": "emissao",
                "source_id": "DOC-LONG",
                "document_date": "2026-06-30",
                "status": "aceito_payload",
            },
            {
                "cnpj": third_cnpj,
                "class_series": "Cota sênior",
                "price_display": "R$ 500,00",
                "source_kind": "candidate_extraction",
                "source_id": "PENDING",
                "document_date": "2026-06-30",
                "status": "candidato",
            },
        ]
    )
    result = build_industry_portfolio_export(
        carteira_detail=detail,
        carteira_structural=_structural(
            [
                {"cnpj": first_cnpj},
                {"cnpj": second_cnpj},
                {"cnpj": third_cnpj},
            ]
        ),
        flagship_detail=_flagships([]),
        carteira_price_evidence=prices,
    )
    rows = result.carteira.set_index("cnpj")

    assert isinstance(rows.loc[first_cnpj, "preco_cota_brl"], np.float64)
    assert rows.loc[first_cnpj, "preco_cota_brl"] == pytest.approx(1_000.0)
    assert rows.loc[first_cnpj, "preco_cota_documento_id"] == "DOC-WIDE"
    assert rows.loc[second_cnpj, "preco_cota_brl"] == pytest.approx(1_000.0)
    assert pd.isna(rows.loc[third_cnpj, "preco_cota_brl"])
    assert rows.loc[third_cnpj, "preco_cota_display"] == "N/D"
    assert rows.loc[third_cnpj, "preco_cota_status"] == (
        "pendente de revisão documental"
    )
    third_gap = result.gaps[result.gaps["cnpj"].eq(third_cnpj)].iloc[0]
    assert "preço unitário da cota" in third_gap["campos_nao_preenchidos"]
    dictionary = result.dictionary.set_index("campo")
    assert dictionary.loc["preco_cota_brl", "tipo_dado"] == "numérico"
    assert "quantidade" in dictionary.loc[
        "preco_cota_display", "origem_regra"
    ]


def test_group_market_fields_and_document_scan_are_propagated_without_recalc() -> None:
    cnpj = _cnpj(1)
    detail = _portfolio_detail(
        [
            {
                "cnpj_fundo": cnpj,
                "tipo_exibicao": "Agro, Indústria e Comércio",
                "originador": "Originador já curado",
            }
        ]
    )
    structural = _structural(
        [
            {
                "cnpj": cnpj,
                "posicao_mercado": "acima do mercado",
                "excesso_vs_mercado": 0.032,
                "benchmark_confiavel": False,
                "n_comparaveis_categoria": 4,
            }
        ]
    )
    audit = pd.DataFrame(
        [
            {
                "cnpj": cnpj,
                "originador": "Não deve substituir",
                "originador_status": "encontrado_explicito",
                "cedente": "Cedente do documento",
                "cedente_status": "encontrado_explicito",
                "cedente_link": "https://example.test/cedente",
                "sacado_devedor": "Candidato não aprovado",
                "sacado_devedor_status": "candidato",
            }
        ]
    )

    result = build_industry_portfolio_export(
        carteira_detail=detail,
        carteira_structural=structural,
        flagship_detail=_flagships([]),
        carteira_document_audit=audit,
    )
    row = result.carteira.iloc[0]

    assert row["grupo_comparacao"] == "Agro / Revenda"
    assert row["posicao_mercado"] == "acima do mercado"
    assert row["excesso_vs_mercado"] == pytest.approx(0.032)
    assert row["benchmark_confiavel"] is False or not bool(
        row["benchmark_confiavel"]
    )
    assert row["n_comparaveis_categoria"] == 4
    assert row["originador"] == "Originador já curado"
    assert row["cedente"] == "Cedente do documento"
    assert row["sacado_devedor"] == "N/D"
    assert row["fonte_partes_recebivel"] == (
        "cedente: https://example.test/cedente"
    )
