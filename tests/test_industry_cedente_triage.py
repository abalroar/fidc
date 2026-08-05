from __future__ import annotations

import gzip
import json
from pathlib import Path

import pandas as pd

from services.industry_cedente_triage import (
    CONSOLIDATED_HEADERS,
    FUND_CEDENT_HEADERS,
    PRIORITY_HEADERS,
    build_coverage_curve,
    consolidate_fund_cedents,
    join_fund_cedents,
    materialize_cedente_triage,
    normalize_cedente_document,
    normalize_consolidated,
    normalize_fund_cedents,
    normalize_priority,
)


def _readme_rows() -> list[list[object]]:
    return [
        ["Mapa de cedentes dos FIDCs · competência jun/26", None],
        [None, None],
        [
            "O que a CVM entrega",
            "A Tabela I identifica cedente por CPF ou CNPJ.",
        ],
        [
            "O que a CVM NÃO entrega",
            "Não existe campo de sacado; a identificação exige leitura documental.",
        ],
        ["Por que isso serve ao seu objetivo", "O cedente é a unidade de triagem."],
        [
            "Cobertura",
            "Dos 4.311 fundos, 1.908 declaram cedente, correspondendo a 38,7% do PL.",
        ],
        ["Como usar a aba Priorização", "Ordenar do maior para o menor PL."],
        ["Fonte do cadastro", "Dados Abertos do CNPJ da Receita Federal."],
        [
            "Sobre o campo Porte da Receita",
            "Demais não isola a faixa de R$ 30 a 500 mi.",
        ],
        ["Como usar Simples e MEI para excluir", "Sim exclui a faixa."],
        ["Sobre capital social", "Capital social não é faturamento."],
        [
            "Regra de preenchimento",
            "Célula vazia significa ausência na fonte.",
        ],
    ]


def _priority_rows() -> list[list[object]]:
    return [
        [1, "01.000.000/0001-01", "FIDC A", 100.0, 0.5, 0.5, 2, "ADM A"],
        [2, "02.000.000/0001-02", "FIDC B", 60.0, 0.3, 0.8, 0, "ADM B"],
        [3, "03.000.000/0001-03", "FIDC C", 40.0, 0.2, 1.0, 1, "ADM C"],
    ]


def _fund_cedent_rows() -> list[list[object]]:
    empty_tail = [None] * 10
    return [
        [
            1,
            "01.000.000/0001-01",
            "FIDC A",
            100.0,
            0.5,
            "com retenção de risco",
            1,
            "33.000.167/0001-01",
            "CNPJ",
            0.6,
            "CEDENTE A S.A.",
            *empty_tail,
        ],
        [
            1,
            "01.000.000/0001-01",
            "FIDC A",
            100.0,
            0.5,
            "sem retenção de risco",
            1,
            "33.000.167/0001-01",
            "CNPJ",
            1.2,
            "CEDENTE A S.A.",
            *empty_tail,
        ],
        [
            3,
            "03.000.000/0001-03",
            "FIDC C",
            40.0,
            1.0,
            "com retenção de risco",
            1,
            "529.982.247-25",
            "CPF",
            0.0,
            None,
            *empty_tail,
        ],
    ]


def _consolidated_rows() -> list[list[object]]:
    return [
        [
            "33.000.167/0001-01",
            "CNPJ",
            "CEDENTE A S.A.",
            "1234-5/00",
            "Demais",
            25_000_000.0,
            "Não",
            "Não",
            "SP",
            1,
            100.0,
            1.2,
            "FIDC A",
        ],
        [
            "529.982.247-25",
            "CPF",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            1,
            40.0,
            0.0,
            "FIDC C",
        ],
    ]


def _write_source_workbook(path: Path) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(_readme_rows()).to_excel(
            writer, sheet_name="Leia-me", header=False, index=False
        )
        pd.DataFrame(_priority_rows(), columns=PRIORITY_HEADERS).to_excel(
            writer, sheet_name="Priorização por PL", startrow=3, index=False
        )
        pd.DataFrame(_fund_cedent_rows(), columns=FUND_CEDENT_HEADERS).to_excel(
            writer, sheet_name="Fundo x Cedente", startrow=3, index=False
        )
        pd.DataFrame(_consolidated_rows(), columns=CONSOLIDATED_HEADERS).to_excel(
            writer, sheet_name="Cedentes consolidados", startrow=3, index=False
        )


def _normalized_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    priority = normalize_priority(pd.DataFrame(_priority_rows(), columns=PRIORITY_HEADERS))
    fund_cedent = normalize_fund_cedents(
        pd.DataFrame(_fund_cedent_rows(), columns=FUND_CEDENT_HEADERS)
    )
    consolidated = normalize_consolidated(
        pd.DataFrame(_consolidated_rows(), columns=CONSOLIDATED_HEADERS)
    )
    return priority, fund_cedent, consolidated


def test_document_key_recovers_unambiguous_missing_leading_zero() -> None:
    assert normalize_cedente_document("33.000.167/0001-01", "CNPJ") == (
        "33.000.167/0001-01",
        "CNPJ|33000167000101",
        "cnpj_valido",
    )
    assert normalize_cedente_document("18.189.547/0001-40", "CNPJ") == (
        "18.189.547/0001-40",
        "CNPJ|18189547000140",
        "cnpj_dv_invalido",
    )
    raw, key, status = normalize_cedente_document(1027058000191, "irregular")
    assert raw == "1027058000191"
    assert key == "CNPJ|01027058000191"
    assert status == "cnpj_zero_esquerda_recuperado"


def test_consolidation_keeps_both_blocks_and_flags_bad_percentages() -> None:
    _, fund_cedent, consolidated = _normalized_frames()
    joined = join_fund_cedents(fund_cedent, consolidated)
    pairs = consolidate_fund_cedents(joined)
    company = pairs.loc[pairs["cedente_doc_key"].eq("CNPJ|33000167000101")].iloc[0]

    assert company["cedente_razao_social_coluna_k"] == "CEDENTE A S.A."
    assert company["cedente_porte_receita"] == "Demais"
    assert company["cedente_capital_social_reais"] == 25_000_000.0
    assert company["linhas_declaracao_origem"] == 2
    assert company["duplicidade_fundo_cedente_flag"]
    assert company["duplicidade_cruza_blocos_flag"]
    assert not company["duplicidade_mesmo_bloco_flag"]
    assert company["percentual_acima_100_flag"]
    assert company["percentual_invalido_flag"]
    declarations = json.loads(company["declaracoes_json"])
    assert [item["bloco"] for item in declarations] == [
        "com retenção de risco",
        "sem retenção de risco",
    ]
    assert [item["percentual"] for item in declarations] == [0.6, 1.2]


def test_join_does_not_mark_missing_company_names_as_reconciled() -> None:
    _, fund_cedent, consolidated = _normalized_frames()
    fund_cedent.loc[0, "cedente_razao_social_coluna_k"] = ""
    consolidated.loc[0, "cedente_razao_social_consolidada"] = ""

    joined = join_fund_cedents(fund_cedent, consolidated)

    assert not bool(joined.iloc[0]["razao_social_match_flag"])


def test_coverage_curve_keeps_zero_cedent_funds_in_the_denominator() -> None:
    priority, _, _ = _normalized_frames()
    curve = build_coverage_curve(priority, cutoff_rank=2)
    cutoff = curve.iloc[1]

    assert cutoff["pl_total_acumulado_pct"] == 0.8
    assert cutoff["fundos_com_cedente_acumulado"] == 1
    assert cutoff["fundos_sem_cedente_acumulado"] == 1
    assert cutoff["pl_com_cedente_acumulado_reais"] == 100.0
    assert cutoff["pl_sem_cedente_acumulado_reais"] == 60.0
    assert cutoff["corte_recomendado_flag"]


def test_materialization_is_deterministic_and_adds_gap_rows(tmp_path: Path) -> None:
    source = tmp_path / "FIDC_Cedentes_202606.xlsx"
    _write_source_workbook(source)
    first = materialize_cedente_triage(source, tmp_path / "first", cutoff_rank=2)
    second = materialize_cedente_triage(source, tmp_path / "second", cutoff_rank=2)

    queue_name = "fidc_cedentes_top2_202606.csv.gz"
    curve_name = "fidc_cedentes_curva_cobertura_202606.csv"
    assert first["outputs"][queue_name]["sha256"] == second["outputs"][queue_name]["sha256"]
    assert first["outputs"][curve_name]["sha256"] == second["outputs"][curve_name]["sha256"]
    assert first["cutoff"]["top_queue"] == {
        "fundos": 2,
        "linhas": 2,
        "fundos_com_cedente": 1,
        "fundos_sem_cedente": 1,
        "pares_fundo_cedente": 1,
    }

    with gzip.open(first["queue_path"], "rt", encoding="utf-8") as handle:
        queue = pd.read_csv(handle, keep_default_na=False)
    gap = queue.loc[queue["cnpj_fundo"].astype(str).str.zfill(14).eq("02000000000102")].iloc[0]
    assert not gap["cedente_declarado_flag"]
    assert gap["middle_market_triage_status"] == "sem_cedente_tabela_i"
