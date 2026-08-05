from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pandas.testing as pdt

from services.industry_cedente_top500 import (
    _read_csv_bytes,
    _registry_frame,
    build_cedente_top500,
    build_multi_competence_top500,
    classify_natureza,
    classify_segmento,
    load_cvm_table,
    normalize_document,
    normalize_tab_iv,
    rank_top500,
    select_dominant_cedents,
)


def test_registry_preserves_leading_zero_in_numeric_cnae() -> None:
    registry = _registry_frame(
        pd.DataFrame(
            [
                {
                    "CNPJ/CPF": "01.645.009/0003-84",
                    "Razão social": "EXTRATIVA EXEMPLO",
                    "CNAE (cód.)": 600001.0,
                }
            ]
        )
    )

    assert registry.iloc[0]["cnae_codigo"] == "0600001"


def test_cvm_reader_repairs_only_structurally_valid_orphan_quotes() -> None:
    payload = (
        "TP;CNPJ;NOME;DT;PL;PL_MEDIO\n"
        'Classe;41.609.394/0001-67;"VERSATILE FIDC;2024-12-31;190807222.61;191046212.50\n'
        'Classe;46.073.195/0001-09;CITI-SYNGENTA FIDC",;2024-12-31;368903488.79;276981191.73\n'
    ).encode("latin-1")

    frame = _read_csv_bytes(payload, source_name="tab_IV_202412.csv")

    assert len(frame) == 2
    assert frame["NOME"].tolist() == ["VERSATILE FIDC", "CITI-SYNGENTA FIDC"]
    assert frame["PL"].tolist() == ["190807222.61", "368903488.79"]
    repairs = frame.attrs["source_repairs"]
    assert [item["linha_fisica"] for item in repairs] == [2, 3]
    assert repairs[1]["acao"] == "remove_unpaired_quote_and_adjacent_comma"


def test_cvm_reader_rejects_unbalanced_quotes_outside_structural_gate() -> None:
    payload = (
        "TP;CNPJ;NOME;DT;PL;PL_MEDIO\n"
        'Classe;41.609.394/0001-67;"VERSATILE FIDC;2024-12-31;190807222.61\n'
    ).encode("latin-1")

    try:
        _read_csv_bytes(payload, source_name="broken.csv")
    except ValueError as exc:
        assert "fora do reparo estrutural permitido" in str(exc)
    else:  # pragma: no cover - documents the fail-closed contract
        raise AssertionError("CSV malformado deveria ser rejeitado")


def _tab_iv(competencia: str = "202606") -> pd.DataFrame:
    date = f"{competencia[:4]}-{competencia[4:6]}-30"
    return pd.DataFrame(
        [
            {
                "DT_COMPTC": date,
                "CNPJ_FUNDO_CLASSE": "01.000.000/0001-01",
                "TP_FUNDO_CLASSE": "Classe",
                "DENOM_SOCIAL": "FIDC A CLASSE",
                "TAB_IV_A_VL_PL": "999",
            },
            {
                "DT_COMPTC": date,
                "CNPJ_FUNDO_CLASSE": "01.000.000/0001-01",
                "TP_FUNDO_CLASSE": "Fundo",
                "DENOM_SOCIAL": "FIDC A",
                "TAB_IV_A_VL_PL": "100",
            },
            {
                "DT_COMPTC": date,
                "CNPJ_FUNDO_CLASSE": "02.000.000/0001-02",
                "TP_FUNDO_CLASSE": "Classe",
                "DENOM_SOCIAL": "FIDC B",
                "TAB_IV_A_VL_PL": "80",
            },
            {
                "DT_COMPTC": date,
                "CNPJ_FUNDO_CLASSE": "03.000.000/0001-03",
                "TP_FUNDO_CLASSE": "Fundo",
                "DENOM_SOCIAL": "FIDC C",
                "TAB_IV_A_VL_PL": "60",
            },
            {
                "DT_COMPTC": date,
                "CNPJ_FUNDO_CLASSE": "04.000.000/0001-04",
                "TP_FUNDO_CLASSE": "Fundo",
                "DENOM_SOCIAL": "FIDC D",
                "TAB_IV_A_VL_PL": "40",
            },
            {
                "DT_COMPTC": date,
                "CNPJ_FUNDO_CLASSE": "05.000.000/0001-05",
                "TP_FUNDO_CLASSE": "Fundo",
                "DENOM_SOCIAL": "FIDC E",
                "TAB_IV_A_VL_PL": "20",
            },
        ]
    )


def _tab_i(competencia: str = "202606") -> pd.DataFrame:
    date = f"{competencia[:4]}-{competencia[4:6]}-30"
    return pd.DataFrame(
        [
            {
                "DT_COMPTC": date,
                "CNPJ_FUNDO_CLASSE": "01.000.000/0001-01",
                "TP_FUNDO_CLASSE": "Fundo",
                "DENOM_SOCIAL": "FIDC A",
                "TAB_I2A12_CPF_CNPJ_CEDENTE_1": "1027058000191",
                "TAB_I2A12_PR_CEDENTE_1": "10",
                "TAB_I2B12_CPF_CNPJ_CEDENTE_1": "00.000.000/0000-00",
                "TAB_I2B12_PR_CEDENTE_1": "99",
                "TAB_I2B12_CPF_CNPJ_CEDENTE_2": "77.000.000/0001-77",
                "TAB_I2B12_PR_CEDENTE_2": "5",
            },
            {
                "DT_COMPTC": date,
                "CNPJ_FUNDO_CLASSE": "01.000.000/0001-01",
                "TP_FUNDO_CLASSE": "Classe",
                "DENOM_SOCIAL": "FIDC A CLASSE",
                "TAB_I2A12_CPF_CNPJ_CEDENTE_1": "1027058000191",
                "TAB_I2A12_PR_CEDENTE_1": "11",
            },
            {
                "DT_COMPTC": date,
                "CNPJ_FUNDO_CLASSE": "02.000.000/0001-02",
                "TP_FUNDO_CLASSE": "Classe",
                "DENOM_SOCIAL": "FIDC B",
                "TAB_I2A12_CPF_CNPJ_CEDENTE_1": "22.000.000/0001-22",
                "TAB_I2A12_PR_CEDENTE_1": "",
                "TAB_I2A12_CPF_CNPJ_CEDENTE_2": "23.000.000/0001-23",
                "TAB_I2A12_PR_CEDENTE_2": "",
            },
            {
                "DT_COMPTC": date,
                "CNPJ_FUNDO_CLASSE": "03.000.000/0001-03",
                "TP_FUNDO_CLASSE": "Fundo",
                "DENOM_SOCIAL": "FIDC C",
                "TAB_I2A12_CPF_CNPJ_CEDENTE_1": "33.000.000/0001-33",
                "TAB_I2A12_PR_CEDENTE_1": "20",
                "TAB_I2A12_CPF_CNPJ_CEDENTE_2": "34.000.000/0001-34",
                "TAB_I2A12_PR_CEDENTE_2": "20",
                "TAB_I2B12_CPF_CNPJ_CEDENTE_1": "35.000.000/0001-35",
                "TAB_I2B12_PR_CEDENTE_1": "20",
            },
            {
                "DT_COMPTC": date,
                "CNPJ_FUNDO_CLASSE": "04.000.000/0001-04",
                "TP_FUNDO_CLASSE": "Fundo",
                "DENOM_SOCIAL": "FIDC D",
                "TAB_I2A12_CPF_CNPJ_CEDENTE_1": "99.999.999/9999-99",
                "TAB_I2A12_PR_CEDENTE_1": "100",
            },
            {
                "DT_COMPTC": date,
                "CNPJ_FUNDO_CLASSE": "05.000.000/0001-05",
                "TP_FUNDO_CLASSE": "Fundo",
                "DENOM_SOCIAL": "FIDC E",
            },
        ]
    ).fillna("")


def _cadastro() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "CNPJ/CPF": "01.027.058/0001-91",
                "Razão social": "CIELO S.A.",
                "CNAE (cód.)": "6619302",
                "Seção CNAE": "K",
                "Capital social (R$)": 100_000_000,
            },
            {
                "CNPJ/CPF": "77.000.000/0001-77",
                "Razão social": "EMPRESA SECUNDARIA",
                "CNAE (cód.)": "6201501",
                "Seção CNAE": "J",
                "Capital social (R$)": 10_000_000,
            },
            {
                "CNPJ/CPF": "22.000.000/0001-22",
                "Razão social": "J&F PARTICIPACOES",
                "CNAE (cód.)": "6462000",
                "Seção CNAE": "K",
                "Capital social (R$)": 10_000_000,
            },
            {
                "CNPJ/CPF": "23.000.000/0001-23",
                "Razão social": "EMPRESA DE SOFTWARE",
                "CNAE (cód.)": "6201501",
                "Seção CNAE": "J",
                "Capital social (R$)": 20_000_000,
            },
            {
                "CNPJ/CPF": "33.000.000/0001-33",
                "Razão social": "ENERGIA DO BRASIL",
                "CNAE (cód.)": "3514000",
                "Seção CNAE": "D",
                "Capital social (R$)": 500_000_000,
            },
            {
                "CNPJ/CPF": "34.000.000/0001-34",
                "Razão social": "AGRO SEMENTES",
                "CNAE (cód.)": "0111301",
                "Seção CNAE": "A",
                "Capital social (R$)": 20_000_000,
            },
            {
                "CNPJ/CPF": "35.000.000/0001-35",
                "Razão social": "EMPRESA CORPORATIVA",
                "CNAE (cód.)": "6201501",
                "Seção CNAE": "J",
                "Capital social (R$)": 350_000_000,
            },
        ]
    )


def test_document_normalization_repairs_leading_zero_and_flags_fake_ids() -> None:
    repaired = normalize_document(1027058000191, "CNPJ")
    assert repaired["documento_digitos_norm"] == "01027058000191"
    assert repaired["documento_status"] == "cnpj_zfill_13"
    assert repaired["cnpj_zfill_13_flag"]
    assert repaired["documento_real_flag"]

    repaired_two_zeros = normalize_document("416968000101", "CNPJ")
    assert repaired_two_zeros["documento_digitos_norm"] == "00416968000101"
    assert repaired_two_zeros["documento_status"] == "cnpj_zfill_12"
    assert repaired_two_zeros["cnpj_zfill_flag"]
    assert not repaired_two_zeros["cnpj_zfill_13_flag"]

    for raw in ("00.000.000/0000-00", "99.999.999/9999-99"):
        fake = normalize_document(raw, "CNPJ")
        assert fake["documento_ficticio_flag"]
        assert not fake["documento_real_flag"]
        assert fake["documento_status"] == "documento_ficticio"


def test_tab_iv_is_fund_first_then_class_and_never_sums_duplicates() -> None:
    normalized = normalize_tab_iv(_tab_iv(), competencia="202606")
    fund_a = normalized.loc[normalized["cnpj_fundo"].eq("01000000000101")].iloc[0]

    assert fund_a["tp_registro"] == "Fundo"
    assert fund_a["pl_fundo_reais"] == 100.0
    assert fund_a["tab_iv_source_rows"] == 2
    assert fund_a["tab_iv_selection_rule"] == "fundo_preferido_sobre_classe"
    assert normalized["pl_fundo_reais"].sum() == 300.0

    universe, top = rank_top500(_tab_iv(), competencia="202606", cutoff_rank=4)
    assert len(universe) == 5
    assert top["rank_pl"].tolist() == [1, 2, 3, 4]
    assert top["pl_fundo_reais"].tolist() == [100.0, 80.0, 60.0, 40.0]


def test_pipeline_unions_table_i_rows_deduplicates_exact_key_and_selects_dominant() -> None:
    overrides = {
        "33.000.000/0001-33": {
            "segmento": "Agro",
            "criterio_segmento": "override documental",
        }
    }
    result = build_cedente_top500(
        "202606",
        _tab_iv(),
        _tab_i(),
        cadastro=_cadastro(),
        registry_overrides=overrides,
        cutoff_rank=4,
    )
    links = result.vinculos

    repaired = links.loc[links["cedente_documento"].eq("01027058000191")]
    assert len(repaired) == 1
    assert repaired.iloc[0]["percentual_cedente_pontos"] == 11.0
    assert repaired.iloc[0]["percentual_cedente"] == 0.11
    assert repaired.iloc[0]["linhas_duplicadas_chave"] == 2
    assert repaired.iloc[0]["cedente_dominante_flag"]

    fund_b = links.loc[links["cnpj_fundo"].eq("02000000000102")]
    assert fund_b["dominante_todos_percentuais_ausentes_flag"].all()
    dominant_b = fund_b.loc[fund_b["cedente_dominante_flag"]].iloc[0]
    assert dominant_b["ordem"] == 1
    assert dominant_b["cedente_documento"] == "22000000000122"

    dominant_c = links.loc[
        links["cnpj_fundo"].eq("03000000000103") & links["cedente_dominante_flag"]
    ].iloc[0]
    assert dominant_c["cedente_documento"] == "33000000000133"
    assert dominant_c["bloco"] == "com_retencao"
    assert dominant_c["ordem"] == 1
    assert dominant_c["percentual_cedente"] == 0.20
    assert dominant_c["segmento"] == "Agro"
    assert dominant_c["criterio_segmento"] == "override documental"


def test_fake_cedents_are_excluded_from_coverage_and_full_pl_closes_by_segment() -> None:
    result = build_cedente_top500(
        "202606",
        _tab_iv(),
        _tab_i(),
        cadastro=_cadastro(),
        registry_overrides={
            "33.000.000/0001-33": {
                "segmento": "Agro",
                "criterio_segmento": "override documental",
            }
        },
        cutoff_rank=4,
    )
    coverage = result.cobertura.iloc[0]
    assert coverage["fundos_com_cedente_real"] == 3
    assert coverage["fundos_sem_cedente_real"] == 1
    assert coverage["vinculos_documento_ficticio"] == 2
    assert coverage["vinculos_cnpj_zfill"] == 1
    assert coverage["vinculos_cnpj_zfill_13"] == 1
    assert coverage["pl_top500_reais"] == 280.0
    assert coverage["pl_fundos_com_cedente_real_reais"] == 240.0

    assert len(result.fundos_sem_cedente) == 1
    gap = result.fundos_sem_cedente.iloc[0]
    assert gap["cnpj_fundo"] == "04000000000104"
    assert gap["motivo_sem_cedente"] == "somente_documento_ficticio"
    assert set(result.exclusoes["motivo_exclusao"]) == {"documento_ficticio_0_9"}

    segment = result.pl_por_segmento.set_index("segmento")
    assert segment["pl_dominante_reais"].sum() == 280.0
    assert segment.loc["IFs", "pl_dominante_reais"] == 100.0
    assert segment.loc["Large", "pl_dominante_reais"] == 80.0
    assert segment.loc["Agro", "pl_dominante_reais"] == 60.0
    assert segment.loc["Sem cedente", "pl_dominante_reais"] == 40.0
    assert abs(segment["pl_sobre_top500_pct"].sum() - 1.0) < 1e-12


def test_segment_classifier_order_exception_and_middle_limitation() -> None:
    assert classify_segmento(
        {"razao_social": "Banco Agro S.A.", "cnae_codigo": "0111301", "secao_cnae": "A"}
    )[0] == "IFs"
    assert classify_segmento(
        {
            "razao_social": "Energia Exemplo",
            "cnae_codigo": "3514000",
            "secao_cnae": "D",
            "capital_social_reais": 900_000_000,
        }
    )[0] == "Infra e Energia"
    assert classify_segmento(
        {"razao_social": "Extrativa Exemplo", "cnae_codigo": "0600001", "secao_cnae": "B"}
    )[0] == "Infra e Energia"

    holding = {
        "razao_social": "Empresa Participacoes",
        "cnae_codigo": "6462000",
        "secao_cnae": "K",
        "capital_social_reais": 10_000_000,
    }
    assert classify_segmento(holding)[0] == "Potencial Middle"
    assert classify_natureza(holding)[0] == "Holding/participação"

    assert classify_segmento(
        {"razao_social": "Escritorio Legal", "cnae_codigo": "6911701", "secao_cnae": "M"}
    )[0] == "Não classificado"
    segment, criterion = classify_segmento(
        {"razao_social": "Empresa de Software", "cnae_codigo": "6201501", "secao_cnae": "J"}
    )
    assert segment == "Potencial Middle"
    assert "faturamento não confirmado" in criterion


def test_dominant_keeps_values_above_100_and_places_missing_percentages_last() -> None:
    links = pd.DataFrame(
        [
            {
                "competencia": "202606",
                "cnpj_fundo": "01000000000101",
                "cedente_real_flag": True,
                "percentual_cedente": 0.0,
                "bloco_ordem": 0,
                "ordem": 1,
                "tp_registro_tabela_i": "Fundo",
                "cedente_doc_key": "CNPJ|11000000000111",
            },
            {
                "competencia": "202606",
                "cnpj_fundo": "01000000000101",
                "cedente_real_flag": True,
                "percentual_cedente": float("nan"),
                "bloco_ordem": 0,
                "ordem": 2,
                "tp_registro_tabela_i": "Fundo",
                "cedente_doc_key": "CNPJ|12000000000112",
            },
            {
                "competencia": "202606",
                "cnpj_fundo": "02000000000102",
                "cedente_real_flag": True,
                "percentual_cedente": 1.5,
                "bloco_ordem": 1,
                "ordem": 1,
                "tp_registro_tabela_i": "Classe",
                "cedente_doc_key": "CNPJ|21000000000121",
            },
            {
                "competencia": "202606",
                "cnpj_fundo": "02000000000102",
                "cedente_real_flag": True,
                "percentual_cedente": 0.9,
                "bloco_ordem": 0,
                "ordem": 1,
                "tp_registro_tabela_i": "Fundo",
                "cedente_doc_key": "CNPJ|22000000000122",
            },
        ]
    )

    selected = select_dominant_cedents(links)
    dominant = selected.loc[selected["cedente_dominante_flag"]].set_index("cnpj_fundo")
    assert dominant.loc["01000000000101", "percentual_cedente"] == 0.0
    assert dominant.loc["02000000000102", "percentual_cedente"] == 1.5


def _write_annual_zip(path: Path) -> None:
    tab_iv = pd.concat(
        [
            _tab_iv("202312").head(1),
            _tab_iv("202312").head(1).assign(DT_COMPTC="2023-11-30", TAB_IV_A_VL_PL="9999"),
        ],
        ignore_index=True,
    )
    tab_i = pd.concat(
        [
            _tab_i("202312").head(1),
            _tab_i("202312").head(1).assign(DT_COMPTC="2023-11-30"),
        ],
        ignore_index=True,
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "inf_mensal_fidc_tab_IV_2023.csv",
            tab_iv.to_csv(index=False, sep=";").encode("latin-1"),
        )
        archive.writestr(
            "inf_mensal_fidc_tab_I_2023.csv",
            tab_i.to_csv(index=False, sep=";").encode("latin-1"),
        )


def test_zip_loader_filters_annual_file_and_pipeline_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "inf_mensal_fidc_2023.zip"
    _write_annual_zip(source)

    loaded = load_cvm_table(source, competencia="202312", table="tab_IV")
    assert len(loaded) == 1
    assert loaded.iloc[0]["DT_COMPTC"] == "2023-12-30"

    first = build_cedente_top500(
        "202312", source, source, cadastro=_cadastro(), cutoff_rank=1
    )
    second = build_cedente_top500(
        "202312", source, source, cadastro=_cadastro(), cutoff_rank=1
    )
    pdt.assert_frame_equal(first.top500, second.top500)
    pdt.assert_frame_equal(first.vinculos, second.vinculos)
    pdt.assert_frame_equal(first.cobertura, second.cobertura)


def test_multi_competence_api_sorts_and_concatenates_frames() -> None:
    sources = {
        "202606": {"tab_iv": _tab_iv("202606"), "tab_i": _tab_i("202606")},
        "202512": (_tab_iv("202512"), _tab_i("202512")),
    }
    frames = build_multi_competence_top500(
        sources,
        cadastro=_cadastro(),
        cutoff_rank=2,
    )

    assert frames["cobertura"]["competencia"].tolist() == ["202512", "202606"]
    assert frames["top500"].groupby("competencia").size().to_dict() == {
        "202512": 2,
        "202606": 2,
    }
    assert set(frames) == {
        "top500",
        "vinculos",
        "fundos_sem_cedente",
        "exclusoes",
            "cobertura",
            "pl_por_segmento",
            "reparos_fonte",
        }
