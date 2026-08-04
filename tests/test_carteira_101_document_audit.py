from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from services.carteira_101_document_audit import (
    SCHEMA_VERSION,
    DocumentSource,
    Evidence,
    PriceEvidence,
    build_audit_table,
    choose_field,
    coverage_table,
    evidence_from_checkpoint,
    extract_document_evidence,
    is_missing,
    load_document_audit_materialization,
    normalize_cnpj,
    price_rows_from_sqlite,
    deduplicate_prices,
    read_checkpoint,
    write_checkpoint,
)


def _evidence(
    *,
    field: str,
    value: str,
    source_kind: str,
    status: str = "encontrado_explicito",
) -> Evidence:
    return Evidence(
        cnpj="01234567000189",
        field=field,
        value=value,
        source_kind=source_kind,
        source_id="12345",
        document_class=source_kind,
        document_date="2026-06-30",
        source_path="doc.pdf",
        source_url="https://example.test/doc.pdf",
        page="12",
        status=status,
        confidence=0.95,
        excerpt="cláusula",
    )


def test_normalize_cnpj_preserves_leading_zero_and_scientific_notation() -> None:
    assert normalize_cnpj("01.234.567/0001-89") == "01234567000189"
    assert normalize_cnpj("1.234567000189E+12") == "01234567000189"
    assert is_missing("N/D")


def test_document_extraction_requires_explicit_definitions_and_keeps_prices_long() -> None:
    text = """
    “Originador” significa SOLAR CRÉDITO S.A., inscrita no CNPJ 01.111.111/0001-11.
    “Cedente” significa SOLAR SECURITIZADORA LTDA., inscrita no CNPJ 02.222.222/0001-22.
    “Devedores” significam as pessoas físicas titulares dos contratos de crédito consignado.
    “Direitos Creditórios” correspondem a contratos de crédito consignado INSS cedidos à Classe.
    O Índice de Subordinação Júnior deverá ser mantido em, no mínimo, 12,5% do PL.
    As Cotas Seniores da 3ª Série terão Valor Nominal Unitário de R$ 1.000,00.
    """
    source = DocumentSource(
        cnpj="01234567000189",
        source_kind="rating_report",
        source_id="9001",
        document_class="Relatório de Agência de Rating",
        document_date="2026-06-30",
        source_path="rating.pdf",
        source_url="https://example.test/9001",
        text=text,
        pages=((1, text),),
    )
    evidence, prices = extract_document_evidence(source)
    by_field = {row.field: row for row in evidence}
    assert "SOLAR CRÉDITO" in by_field["originador"].value
    assert "SOLAR SECURITIZADORA" in by_field["cedente"].value
    assert "pessoas físicas" in by_field["sacado_devedor"].value
    assert "consignado INSS" in by_field["tipo_recebivel"].value
    assert by_field["minimo_junior"].value == "12.5%"
    assert prices[0].price_display == "R$ 1.000,00"
    assert "Cotas Seniores" in prices[0].class_series
    assert prices[0].price_nature == "Valor nominal unitário (VNU)"
    assert prices[0].exception_flag == ""


def test_document_extraction_keeps_target_remuneration_separate_from_vnu() -> None:
    text = """
    As Cotas Seniores da 3ª Série terão Valor Nominal Unitário de R$ 1.000,00.
    Para as Cotas Seniores da 3ª Série, a Meta de Remuneração corresponde à
    variação do CDI acrescida de um spread de 1,50% a.a.
    As Cotas Subordinadas Mezanino terão como Retorno Alvo 120% do CDI.
    """
    source = DocumentSource(
        cnpj="01234567000189",
        source_kind="emissao",
        source_id="9003",
        document_class="Instrumento de emissão",
        document_date="2026-06-30",
        source_path="emissao.pdf",
        source_url="https://example.test/9003",
        text=text,
        pages=((1, text),),
    )

    evidence, prices = extract_document_evidence(source)
    remuneration = [row for row in evidence if row.field == "remuneracao_alvo"]

    assert {row.value for row in remuneration} == {
        "Sênior · 3ª Série: CDI + 1,50% a.a.",
        "Mezanino: 120% do CDI",
    }
    assert {row.price_display for row in prices} == {"R$ 1.000,00"}


def test_target_remuneration_rejects_portfolio_yield_and_provider_fee() -> None:
    text = """
    A carteira possui taxa média ponderada CDI + 7,00% a.a.
    A remuneração da Administradora será CDI + 2,00% a.a.
    """
    source = DocumentSource(
        cnpj="01234567000189",
        source_kind="regulamento",
        source_id="9004",
        document_class="Regulamento",
        document_date="2026-06-30",
        source_path="regulamento.pdf",
        source_url="https://example.test/9004",
        text=text,
        pages=((1, text),),
    )

    evidence, _ = extract_document_evidence(source)

    assert not [row for row in evidence if row.field == "remuneracao_alvo"]


def test_target_remuneration_rejects_bookbuilding_cap() -> None:
    text = """
    Para as Cotas Seniores, o Benchmark corresponde à Taxa DI acrescida de,
    no máximo, 0,85% a.a., a ser definido em procedimento de bookbuilding.
    """
    source = DocumentSource(
        cnpj="01234567000189",
        source_kind="regulamento",
        source_id="9005",
        document_class="Regulamento",
        document_date="2026-06-30",
        source_path="regulamento.pdf",
        source_url="https://example.test/9005",
        text=text,
        pages=((1, text),),
    )

    evidence, _ = extract_document_evidence(source)

    assert not [row for row in evidence if row.field == "remuneracao_alvo"]


def test_rating_participant_table_is_explicit_party_evidence() -> None:
    text = """
    Participantes da Operação
    Originador BRASKEM S.A.
    Gestor BANCO EXEMPLO S.A.
    Cedente LAVORO AGROCOMERCIAL S.A., AGROCONTATO COMÉRCIO S.A.
    Provedor de conta bancária BANCO EXEMPLO S.A.
    """
    source = DocumentSource(
        cnpj="01234567000189",
        source_kind="rating_report",
        source_id="9002",
        document_class="Relatório de rating",
        document_date="2026-06-30",
        source_path="rating.pdf",
        source_url="https://example.test/9002",
        text=text,
        pages=((1, text),),
    )
    evidence, _ = extract_document_evidence(source)
    selected = {(row.field, row.value) for row in evidence}
    assert ("originador", "BRASKEM S.A.") in selected
    assert any(field == "cedente" and "LAVORO" in value for field, value in selected)


def test_source_precedence_and_candidates_do_not_promote() -> None:
    manual = _evidence(field="cedente", value="Manual", source_kind="planilha_manual")
    regulation = _evidence(field="cedente", value="Regulamento", source_kind="regulamento")
    rating = _evidence(field="cedente", value="Rating", source_kind="rating_report")
    candidate = _evidence(
        field="originador",
        value="Candidato",
        source_kind="candidate_extraction",
        status="candidato_revisao",
    )
    assert choose_field([manual, regulation, rating], "cedente") == rating
    assert choose_field([candidate], "originador") is None


def test_accepted_structural_minimum_is_not_overwritten_by_fresh_extraction() -> None:
    accepted = _evidence(
        field="minimo_junior",
        value="12.5%",
        source_kind="payload_documental",
        status="aceito_payload",
    )
    fresh = _evidence(
        field="minimo_junior",
        value="20%",
        source_kind="rating_report",
    )
    assert choose_field([fresh, accepted], "minimo_junior") == accepted


def test_coverage_and_audit_preserve_not_found_as_nd() -> None:
    portfolio = pd.DataFrame(
        [
            {
                "ordem": 1,
                "cnpj": "01234567000189",
                "nome_oficial_cvm": "FIDC TESTE",
                "nome_referencia": "Teste",
            }
        ]
    )
    candidate = _evidence(
        field="originador",
        value="Candidato",
        source_kind="candidate_extraction",
        status="candidato_revisao",
    )
    explicit = _evidence(field="cedente", value="Cedente S.A.", source_kind="regulamento")
    coverage = coverage_table([], [candidate, explicit], ["01234567000189"])
    originator = coverage.loc[coverage["campo"].eq("originador")].iloc[0]
    cedente = coverage.loc[coverage["campo"].eq("cedente")].iloc[0]
    assert originator["depois_com_dado"] == 0
    assert cedente["depois_com_dado"] == 1

    audit = build_audit_table(portfolio, [candidate, explicit])
    assert audit.loc[0, "originador"] == "N/D"
    assert audit.loc[0, "originador_status"] == "não encontrado"
    assert audit.loc[0, "cedente"] == "Cedente S.A."


def test_checkpoint_roundtrip_preserves_evidence_and_price(tmp_path: Path) -> None:
    evidence = _evidence(field="cedente", value="Cedente S.A.", source_kind="regulamento")
    checkpoint = {
        "01234567000189": {
            "cnpj": "01234567000189",
            "status": "concluído",
            "evidence": [asdict(evidence)],
            "prices": [],
        }
    }
    path = tmp_path / "checkpoint.jsonl"
    write_checkpoint(path, checkpoint)
    loaded = read_checkpoint(path)
    loaded_evidence, prices = evidence_from_checkpoint(loaded)
    assert loaded_evidence == [evidence]
    assert prices == []


def test_sqlite_price_rows_preserve_multiple_classes_and_ignore_quantity() -> None:
    frame = pd.DataFrame(
        [
            {
                "cnpj": "01.234.567/0001-89",
                "cota_classe": "Cota Sênior 1ª Série",
                "vnu": "R$ 1.000,00",
                "quantidade": "5000",
                "remunera_o": "DI + 2%",
                "data_deliberacao": "2026-06-01",
                "fonte": "12345_emissao.pdf · ID 12345 · 01/06/2026",
            },
            {
                "cnpj": "01.234.567/0001-89",
                "cota_classe": "Cota Subordinada Júnior",
                "vnu": "R$ 10.000,00",
                "quantidade": "50",
                "remunera_o": "residual",
                "data_deliberacao": "2026-06-01",
                "fonte": "12345_emissao.pdf · ID 12345 · 01/06/2026",
            },
        ]
    )
    rows = price_rows_from_sqlite(frame, {"01234567000189"})
    assert len(rows) == 2
    assert {row.price_display for row in rows} == {"R$ 1.000,00", "R$ 10.000,00"}
    assert {row.price_nature for row in rows} == {"Valor nominal unitário (VNU)"}
    serialized = [asdict(row) for row in rows]
    assert all("quantidade" not in row and "remunera" not in row for row in serialized)


def test_price_extraction_rejects_aggregate_offer_amount_after_unit_value() -> None:
    text = """
    A oferta compreende 1.000.000 Cotas Seniores, com valor unitário de emissão
    equivalente a R$ 1.000,00 (mil reais) ("Valor Unitário de Emissão"),
    respectivamente, no montante total de R$ 1.000.000.000,00.
    O montante total terá preço de emissão de R$ 750.000.000,00.
    A Cota Subordinada terá preço de integralização por cota de R$ 10.000,00.
    """
    source = DocumentSource(
        cnpj="01234567000189",
        source_kind="emissao",
        source_id="771338",
        document_class="suplemento de emissão",
        document_date="2026-06-30",
        source_path="771338.pdf",
        source_url="https://example.test/771338",
        text=text,
        pages=((1, text),),
    )
    _, prices = extract_document_evidence(source)
    assert {row.price_display for row in prices} == {"R$ 1.000,00", "R$ 10.000,00"}
    assert all("1.000.000.000" not in row.price_display for row in prices)
    assert all("750.000.000" not in row.price_display for row in prices)


def test_price_extraction_handles_table_layout_without_taking_offer_total() -> None:
    text = """
    Valor Total da Oferta, considerando o
    Valor Nominal Unitário na Data de
    Emissão
    R$30.000.000,00 (trinta milhões de reais)
    Valor Nominal Unitário na Data
    de Emissão

    R$1.000,00 (mil reais)
    Quantidade de Cotas Seniores 30.000 (trinta mil)
    """
    source = DocumentSource(
        cnpj="01234567000189",
        source_kind="emissao",
        source_id="938955",
        document_class="anúncio de encerramento",
        document_date="2025-07-02",
        source_path="938955.pdf",
        source_url="https://example.test/938955",
        text=text,
        pages=((1, text),),
    )
    _, prices = extract_document_evidence(source)
    assert {row.price_display for row in prices} == {"R$1.000,00"}


def test_price_extraction_rejects_total_after_defined_unit_term() -> None:
    text = """
    975.000 Cotas Seniores, com valor unitário de emissão equivalente a
    R$ 1.000,00 (mil reais), na data de emissão ("Valor Unitário de Emissão"),
    perfazendo o valor de R$ 975.000.000,00.
    """
    source = DocumentSource(
        cnpj="01234567000189",
        source_kind="emissao",
        source_id="1030080",
        document_class="suplemento",
        document_date="2025-11-06",
        source_path="1030080.pdf",
        source_url="https://example.test/1030080",
        text=text,
        pages=((1, text),),
    )
    _, prices = extract_document_evidence(source)
    assert {row.price_display for row in prices} == {"R$ 1.000,00"}


def test_price_deduplication_normalizes_spacing_and_keeps_one_source() -> None:
    base = {
        "cnpj": "01234567000189",
        "class_series": "Cota Sênior 1ª Série",
        "source_kind": "emissao",
        "document_class": "emissao",
        "document_date": "2026-06-30",
        "source_path": "doc.pdf",
        "source_url": "https://example.test/doc",
        "page": "1",
        "status": "encontrado_explicito",
        "excerpt": "valor unitário",
        "price_nature": "Valor nominal unitário (VNU)",
    }
    first = PriceEvidence(
        **base,
        price_display="R$1.000,00",
        source_id="100",
    )
    second = PriceEvidence(
        **base,
        price_display="R$ 1.000,00",
        source_id="101",
    )
    assert len(deduplicate_prices([first, second])) == 1


def test_materialized_loader_never_needs_source_documents(tmp_path: Path) -> None:
    pd.DataFrame([{"cnpj": "01234567000189"}]).to_csv(
        tmp_path / "carteira_101_document_audit.csv", index=False
    )
    pd.DataFrame([{"campo": "cedente", "depois_com_dado": 1}]).to_csv(
        tmp_path / "carteira_101_document_coverage.csv", index=False
    )
    pd.DataFrame([{"cnpj": "01234567000189", "field": "cedente"}]).to_csv(
        tmp_path / "carteira_101_document_evidence.csv.gz",
        index=False,
        compression="gzip",
    )
    pd.DataFrame(
        [
            {
                "cnpj": "01234567000189",
                "class_series": "Cota Sênior",
                "price_display": "R$ 1.000,00",
                "price_nature": "Valor nominal unitário (VNU)",
                "exception_flag": "",
                "exception_reason": "",
            }
        ]
    ).to_csv(
        tmp_path / "carteira_101_document_prices.csv.gz",
        index=False,
        compression="gzip",
    )
    (tmp_path / "carteira_101_document_checkpoint.jsonl").write_text(
        json.dumps({"cnpj": "01234567000189", "status": "concluído"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "carteira_101_document_manifest.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION}),
        encoding="utf-8",
    )

    materialized = load_document_audit_materialization(tmp_path)
    assert materialized.audit["cnpj"].tolist() == ["01234567000189"]
    assert materialized.prices.loc[0, "price_display"] == "R$ 1.000,00"
    assert materialized.checkpoint.loc[0, "status"] == "concluído"
