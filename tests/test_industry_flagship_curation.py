from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.industry_flagship_curation import _document_fields, build_flagship_curation


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "industry_study"
REVISION = DATA / "generated_revision"
DEEP_DIVES = ROOT / "data" / "deep_dives"
LATEST = "2026-06"


@pytest.fixture(scope="module")
def flagship():
    return build_flagship_curation(
        scope_path=DATA / "industry_flagship_scope.csv",
        funds=pd.read_csv(
            REVISION / "base_fundo_cnpj.csv.gz",
            low_memory=False,
        ),
        vehicle=pd.read_csv(
            REVISION / "base_competencia_cnpj.csv.gz",
            low_memory=False,
        ),
        latest=LATEST,
        deep_dives_dir=DEEP_DIVES,
        documentary_path=DATA / "industry_flagship_document_curation.csv",
    )


def test_flagship_scope_is_complete_unique_and_current(flagship) -> None:
    detail = flagship.detail
    families = flagship.families
    assert len(detail) == 47
    assert detail["cnpj_fundo"].nunique() == 47
    assert len(families) == 26
    assert families["ordem_familia"].tolist() == list(range(1, 27))
    assert detail["pl_atual_brl"].notna().all()
    assert detail["subordinacao_atual_pct"].notna().all()
    assert detail["subordinacao_atual_pct"].between(0, 1).all()
    assert detail["subordinacao_atual_status"].eq(
        "Calculado com classes reportadas e PL oficial reconciliado"
    ).all()


def test_flagship_documentary_coverage_preserves_gaps(flagship) -> None:
    detail = flagship.detail.set_index("cnpj_fundo")
    assert flagship.summary["cnpjs_com_pacote_documental"] == 15
    assert flagship.summary["cnpjs_com_minimo_junior"] == 12
    assert flagship.summary["cnpjs_com_regulamento_lido"] == 24
    # October documentary exports preserve unavailable VNU fields as N/D.
    assert flagship.summary["cnpjs_com_preco_vnu"] == 12
    assert flagship.summary["cnpjs_com_mezanino_comprovado"] == 12

    paketa = detail.loc["53841740000117"]
    assert pd.isna(paketa["subordinacao_minima_junior_pct"])
    assert paketa["subordinacao_minima_junior_display"] == "N/D"
    assert pd.isna(paketa["preco_emissao_brl"])
    assert paketa["preco_emissao_display"] == "N/D"
    assert paketa["cota_mezanino"] == "N/D"
    assert paketa["vencimento_antecipado"].startswith("N/D")


def test_flagship_known_documentary_fields_are_source_faithful(flagship) -> None:
    detail = flagship.detail.set_index("cnpj_fundo")

    bela = detail.loc["62393679000183"]
    assert pd.isna(bela["subordinacao_minima_junior_pct"])
    assert bela["subordinacao_minima_junior_display"] == "1,0% até D+180; 2,5% após D+180"
    assert pd.isna(bela["preco_emissao_brl"])
    assert bela["preco_emissao_display"] == "N/D"
    assert bela["cota_mezanino"] == "Sim"
    assert "1117954" in bela["subordinacao_minima_fonte"]
    assert bela["status_curadoria_documental"] == "revisto — mínimo júnior localizado"

    seller_iii = detail.loc["63572282000111"]
    assert seller_iii["subordinacao_minima_junior_pct"] == pytest.approx(10.0)
    assert pd.isna(seller_iii["preco_emissao_brl"])
    assert seller_iii["preco_emissao_display"] == "N/D"
    assert seller_iii["cota_mezanino"] == "Sim"

    mercado_ii = detail.loc["41970012000126"]
    assert mercado_ii["subordinacao_minima_junior_pct"] == pytest.approx(10.0)
    assert pd.isna(mercado_ii["preco_emissao_brl"])
    assert mercado_ii["preco_emissao_display"] == (
        "R$ 1.000,00 da data base do apêndice / "
        "R$ 561,60 da data base do apêndice / "
        "R$ 492,09 da data base do apêndice"
    )
    assert mercado_ii["preco_emissao_data"] == "N/D"
    assert "1302706" in mercado_ii["preco_emissao_fonte"]
    assert "1077334" in mercado_ii["subordinacao_minima_fonte"]

    big_picture_iii = detail.loc["54219179000100"]
    assert pd.isna(big_picture_iii["subordinacao_minima_junior_pct"])
    assert big_picture_iii["subordinacao_minima_junior_display"] == "N/D"
    assert "5% (três por cento)" in big_picture_iii["subordinacao_minima_texto"]
    assert big_picture_iii["status_curadoria_documental"] == "revisto — conflito interno do documento"


def test_flagship_family_ranges_cover_every_family(flagship) -> None:
    observed = flagship.families["faixa_subordinacao_atual"].value_counts().to_dict()
    assert observed == {
        "< 10%": 5,
        "10%–15%": 4,
        "15%–20%": 6,
        "20%–35%": 3,
        "35%–60%": 4,
        "≥ 60%": 4,
    }
    assert flagship.families["subordinacao_atual_pct"].notna().all()


def test_flagship_divergent_quota_pl_is_not_materialized_as_zero(tmp_path: Path) -> None:
    scope = pd.DataFrame(
        [
            {
                "ordem_categoria": 1,
                "categoria": "Teste",
                "ordem_familia": 1,
                "familia_flagship": "Fundo teste",
                "cnpj_fundo": "00.000.000/0001-91",
                "representante_familia": 1,
                "pacote_documental": "",
            }
        ]
    )
    scope_path = tmp_path / "scope.csv"
    scope.to_csv(scope_path, index=False)
    funds = pd.DataFrame(
        [
            {
                "competencia": LATEST,
                "cnpj_fundo": "00000000000191",
                "denominacao": "Fundo teste",
                "pl": 100.0,
            }
        ]
    )
    vehicle = pd.DataFrame(
        [
            {
                "competencia": LATEST,
                "cnpj_fundo": "00000000000191",
                "cnpj": "00000000000191",
                "vl_cotas_total": 50.0,
                "vl_cotas_subordinadas": 10.0,
            }
        ]
    )
    result = build_flagship_curation(
        scope_path=scope_path,
        funds=funds,
        vehicle=vehicle,
        latest=LATEST,
        deep_dives_dir=tmp_path,
    )
    row = result.detail.iloc[0]
    assert pd.isna(row["subordinacao_atual_pct"])
    assert "diverge" in row["subordinacao_atual_status"]
    assert result.families.iloc[0]["faixa_subordinacao_atual"] == "N/D"


@pytest.mark.parametrize(
    ("has_date_column", "date_value"),
    [(False, None), (True, None), (True, pd.NaT), (True, "NaT"), (True, "data indisponível")],
)
def test_document_package_with_missing_emission_date_preserves_gaps(
    tmp_path: Path, date_value: object, has_date_column: bool
) -> None:
    tables = tmp_path / "tables"
    tables.mkdir()
    row = {
        "CNPJ": "00000000000191",
        "Preço/VNU": "R$ 1.000,00",
        "Classe/Série": "Sênior",
        "Tipo": "Sênior",
        "Fonte": "Documento primário, página 2",
    }
    if has_date_column:
        row["Data"] = date_value
    pd.DataFrame([row]).to_csv(tables / "emissions.csv", index=False)

    result = _document_fields(package_dir=tmp_path, cnpj="00000000000191")

    assert result["preco_emissao_brl"] == pytest.approx(1_000.0)
    assert result["preco_emissao_data"] == "N/D"
    assert result["emissao_data"] == "N/D"
    assert result["emissao_data_display"] == "N/D"
    assert result["preco_emissao_fonte"] == "Documento primário, página 2"
    assert result["emissao_fonte"] == "Documento primário, página 2"


def test_documentary_vnu_schema_preserves_multiple_values_and_undated_emissions(tmp_path: Path) -> None:
    tables = tmp_path / "tables"
    tables.mkdir()
    pd.DataFrame([
        {"CNPJ": "00000000000191", "VNU": "R$ 1.000,00", "Cota/Classe": "Sênior 1ª",
         "Tipo": "Sênior", "Data deliberação": "01/08/2026",
         "Data emissão / 1ª integralização": "Não informado nas fontes consultadas",
         "Fonte": "Documento 123, página 1"},
        {"CNPJ": "00000000000191", "VNU": "R$ 561,60", "Cota/Classe": "Sênior 2ª",
         "Tipo": "Sênior", "Data deliberação": "01/08/2026",
         "Data emissão / 1ª integralização": "Não informado nas fontes consultadas",
         "Fonte": "Documento 123, página 2"},
    ]).to_csv(tables / "emissions.csv", index=False)
    result = _document_fields(package_dir=tmp_path, cnpj="00000000000191")
    assert result["preco_emissao_brl"] is None
    assert result["preco_emissao_display"] == "R$ 1.000,00 / R$ 561,60"
    assert result["preco_emissao_classe"] == "Sênior 1ª / Sênior 2ª"
    assert result["preco_emissao_fonte"] == "Documento 123, página 1 | Documento 123, página 2"
    assert result["emissao_data"] == "N/D"
    assert result["preco_emissao_data"] == "N/D"


def test_documentary_vnu_schema_reads_exact_emission_date(tmp_path: Path) -> None:
    tables = tmp_path / "tables"
    tables.mkdir()
    pd.DataFrame([
        {"CNPJ": "00000000000191", "VNU": "R$ 1.000,00", "Cota/Classe": "Sênior",
         "Tipo": "Sênior", "Data emissão / 1ª integralização": "11/08/2026",
         "Fonte": "Documento primário, página 4"},
    ]).to_csv(tables / "emissions.csv", index=False)
    result = _document_fields(package_dir=tmp_path, cnpj="00000000000191")
    assert result["preco_emissao_brl"] == pytest.approx(1000.0)
    assert result["emissao_data"] == "11/08/2026"
    assert result["preco_emissao_data"] == "11/08/2026"


def test_reported_zero_and_negative_pl_remain_distinct_from_missing_current_observation(tmp_path: Path) -> None:
    from services.industry_portfolio_export import build_industry_portfolio_export_from_payload

    cnpjs = ["00000000000191", "00000000000272", "00000000000353"]
    scope = pd.DataFrame([
        {"ordem_categoria": 1, "categoria": "Teste", "ordem_familia": index,
         "familia_flagship": f"Família {index}", "cnpj_fundo": cnpj,
         "representante_familia": 1, "pacote_documental": ""}
        for index, cnpj in enumerate(cnpjs, 1)
    ])
    scope_path = tmp_path / "scope.csv"
    scope.to_csv(scope_path, index=False)
    funds = pd.DataFrame([
        {"competencia": "2026-08", "cnpj_fundo": cnpjs[0], "denominacao": "Zero reportado", "pl": 0.0},
        {"competencia": "2026-07", "cnpj_fundo": cnpjs[1], "denominacao": "Ausente em agosto", "pl": 100.0},
        {"competencia": "2026-08", "cnpj_fundo": cnpjs[2], "denominacao": "Negativo reportado", "pl": -10.0},
    ])
    vehicle = pd.DataFrame([
        {"competencia": "2026-08", "cnpj_fundo": cnpjs[0], "vl_cotas_total": 0.0, "vl_cotas_subordinadas": 0.0},
        {"competencia": "2026-08", "cnpj_fundo": cnpjs[2], "vl_cotas_total": -10.0, "vl_cotas_subordinadas": 0.0},
    ])
    result = build_flagship_curation(scope_path=scope_path, funds=funds, vehicle=vehicle,
                                     latest="2026-08", deep_dives_dir=tmp_path)
    detail = result.detail.set_index("cnpj_fundo")
    assert detail.loc[cnpjs[0], "pl_atual_brl"] == 0.0
    assert "reportado zero" in detail.loc[cnpjs[0], "subordinacao_atual_status"]
    assert pd.isna(detail.loc[cnpjs[1], "pl_atual_brl"])
    assert detail.loc[cnpjs[1], "subordinacao_atual_status"] == "PL oficial ausente em 2026-08"
    assert detail.loc[cnpjs[2], "pl_atual_brl"] == -10.0
    assert "reportado negativo" in detail.loc[cnpjs[2], "subordinacao_atual_status"]
    assert detail["subordinacao_atual_pct"].isna().all()

    exported = build_industry_portfolio_export_from_payload({
        "latest_complete": "2026-08", "carteira_1_curation": [],
        "carteira_1_structural_assets": [], "flagship_curation": result.detail.to_dict("records"),
    }).flagships.set_index("cnpj")
    assert exported.loc[cnpjs[0], "pl_atual_brl"] == 0.0
    assert "reportado zero" in exported.loc[cnpjs[0], "status_sub_pl_atual"]
    assert pd.isna(exported.loc[cnpjs[1], "pl_atual_brl"])
    assert exported.loc[cnpjs[2], "pl_atual_brl"] == -10.0
