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
