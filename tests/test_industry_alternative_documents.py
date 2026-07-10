from __future__ import annotations

import pandas as pd

from services.industry_alternative_documents import (
    alternative_documents_to_inventory_sources,
    alternative_document_quality_summary,
    build_alternative_document_status,
    build_cvm_eventual_candidates,
    classify_cvm_eventual_document,
    select_alternative_document_targets,
)


def test_select_alternative_targets_keeps_only_adherent_no_fnet_packages():
    evidence = pd.DataFrame(
        [
            {
                "package_id": "pkg-a",
                "cnpj_fundo": "11.111.111/0001-11",
                "work_tier": "P0 competência",
                "batch_id": "P0-001",
                "nome_exibicao": "FIDC A",
                "competencia": "2026-05",
                "technical_stage": "fontes alternativas",
                "scope_status": "aderente",
            },
            {
                "package_id": "pkg-b",
                "cnpj_fundo": "22.222.222/0001-22",
                "work_tier": "P0 competência",
                "batch_id": "P0-001",
                "nome_exibicao": "FUNDO B",
                "competencia": "2026-05",
                "technical_stage": "fontes alternativas",
                "scope_status": "revisar universo",
            },
            {
                "package_id": "pkg-c",
                "cnpj_fundo": "33.333.333/0001-33",
                "work_tier": "P0 competência",
                "batch_id": "P0-001",
                "nome_exibicao": "FIDC C",
                "competencia": "2026-05",
                "technical_stage": "revisão",
                "scope_status": "aderente",
            },
        ]
    )

    targets = select_alternative_document_targets(evidence)

    assert targets.to_dict("records") == [
        {
            "cnpj_fundo": "11111111000111",
            "package_ids": "pkg-a",
            "work_tier": "P0 competência",
            "batch_id": "P0-001",
            "nome_exibicao": "FIDC A",
            "source_years": "2026",
        }
    ]


def test_cvm_eventual_candidates_preserve_official_provenance_and_constitutive_types():
    targets = pd.DataFrame(
        [
            {
                "cnpj_fundo": "11111111000111",
                "package_ids": "pkg-a",
                "work_tier": "P0 competência",
                "batch_id": "P0-001",
                "nome_exibicao": "FIDC A",
                "source_years": "2026",
            }
        ]
    )
    eventual = pd.DataFrame(
        [
            {
                "CNPJ_FUNDO_CLASSE": "11.111.111/0001-11",
                "DENOM_SOCIAL": "FIDC A",
                "DT_COMPTC": "2026-05-10",
                "DT_RECEB": "2026-05-11",
                "ID_DOC": "",
                "TP_DOC": "REGUL FDO",
                "TP_FUNDO_CLASSE": "FIDC",
                "NM_ARQ": "DOC_REGUL_A.pdf",
                "LINK_ARQ": "https://web.cvm.gov.br/DOC_REGUL_A.pdf",
            },
            {
                "CNPJ_FUNDO_CLASSE": "11.111.111/0001-11",
                "DENOM_SOCIAL": "FIDC A",
                "DT_COMPTC": "2026-05-12",
                "DT_RECEB": "2026-05-12",
                "ID_DOC": "123",
                "TP_DOC": "SGF APENDICE",
                "TP_FUNDO_CLASSE": "CLASSES - FIDC",
                "NM_ARQ": "DOC_APENDICE_A.pdf",
                "LINK_ARQ": "https://web.cvm.gov.br/DOC_APENDICE_A.pdf",
            },
            {
                "CNPJ_FUNDO_CLASSE": "11.111.111/0001-11",
                "DENOM_SOCIAL": "FIDC A",
                "DT_COMPTC": "2026-05-13",
                "DT_RECEB": "2026-05-13",
                "ID_DOC": "124",
                "TP_DOC": "OUTROS",
                "TP_FUNDO_CLASSE": "FIDC",
                "NM_ARQ": "ARQUIVO_A.pdf",
                "LINK_ARQ": "https://web.cvm.gov.br/ARQUIVO_A.pdf",
            },
        ]
    )

    candidates = build_cvm_eventual_candidates(
        eventual,
        targets,
        source_year=2026,
        dataset_url="https://dados.cvm.gov.br/eventual_fi_2026.csv",
        discovered_at_utc="2026-07-10T12:00:00+00:00",
    )

    assert len(candidates) == 2
    assert set(candidates["document_class"]) == {"regulamento"}
    assert set(candidates["document_type"]) == {"REGUL FDO", "SGF APENDICE"}
    assert candidates["source_dataset"].eq("CVM FI Documentos Eventuais").all()
    assert candidates["source_dataset_url"].str.contains("dados.cvm.gov.br").all()
    assert candidates["source_url"].str.contains("web.cvm.gov.br").all()
    assert candidates["document_id"].str.len().gt(0).all()
    assert classify_cvm_eventual_document("SGF ANEXO") == "regulamento"


def test_alternative_document_status_and_quality_count_downloaded_coverage():
    targets = pd.DataFrame(
        [
            {
                "cnpj_fundo": "11111111000111",
                "package_ids": "pkg-a",
                "work_tier": "P0 competência",
                "batch_id": "P0-001",
                "nome_exibicao": "FIDC A",
                "source_years": "2026",
            },
            {
                "cnpj_fundo": "22222222000122",
                "package_ids": "pkg-b",
                "work_tier": "P0 competência",
                "batch_id": "P0-001",
                "nome_exibicao": "FIDC B",
                "source_years": "2026",
            },
        ]
    )
    documents = pd.DataFrame(
        [
            {
                "cnpj_fundo": "11111111000111",
                "download_status": "baixado",
                "document_type": "REGUL FDO",
                "document_class": "regulamento",
                "reference_date": "2026-05-10",
                "error_message": "",
            },
            {
                "cnpj_fundo": "11111111000111",
                "download_status": "reutilizado",
                "document_type": "SGF ANEXO",
                "document_class": "regulamento",
                "reference_date": "2026-05-12",
                "error_message": "",
            },
        ]
    )

    status = build_alternative_document_status(
        targets,
        documents,
        attempted_at_utc="2026-07-10T12:00:00+00:00",
    )
    quality = alternative_document_quality_summary(documents, status, target_funds=2)

    by_cnpj = status.set_index("cnpj_fundo")
    assert by_cnpj.loc["11111111000111", "listing_status"] == "ok"
    assert by_cnpj.loc["22222222000122", "listing_status"] == "sem_documento_alternativo"
    assert quality["covered_funds"] == 1
    assert quality["no_document_funds"] == 1
    assert quality["downloaded_documents"] == 1
    assert quality["reused_documents"] == 1
    assert quality["regulation_documents"] == 2


def test_alternative_documents_become_dated_inventory_sources_only_after_download():
    documents = pd.DataFrame(
        [
            {
                "cnpj_fundo": "11.111.111/0001-11",
                "nome_exibicao": "FIDC A",
                "local_path": "data/raw/11111111000111/regulamento.pdf",
                "reference_date": "2026-05-10",
                "document_class": "regulamento",
                "document_type": "REGUL FDO",
                "source_url": "https://web.cvm.gov.br/regulamento.pdf",
                "download_status": "baixado",
            },
            {
                "cnpj_fundo": "22.222.222/0001-22",
                "nome_exibicao": "FIDC B",
                "local_path": "",
                "reference_date": "2026-05-11",
                "document_class": "regulamento",
                "document_type": "REGUL FDO",
                "source_url": "https://web.cvm.gov.br/pendente.pdf",
                "download_status": "listado",
            },
        ]
    )

    sources = alternative_documents_to_inventory_sources(documents)

    assert len(sources) == 1
    assert sources.iloc[0]["cnpj_fundo"] == "11111111000111"
    assert sources.iloc[0]["document_date_hint"] == "2026-05-10"
    assert sources.iloc[0]["source_table"] == "cvm_eventual_documents"
    assert "web.cvm.gov.br" in sources.iloc[0]["priority_hint"]
