import pandas as pd

from services.industry_package_documents import (
    PACKAGE_DOCUMENT_DISCOVERY_STATUS_COLUMNS,
    merge_package_document_discovery,
    package_document_discovery_quality_summary,
    select_package_document_targets,
)


def test_package_document_targets_dedupe_funds_and_skip_completed_scope():
    evidence = pd.DataFrame(
        [
            {
                "package_id": "pkg-a-delta",
                "cnpj_fundo": "11.111.111/0001-11",
                "work_tier": "P0 competência",
                "batch_id": "P0-001",
                "nome_exibicao": "FIDC A",
                "technical_stage": "descoberta",
                "scope_status": "aderente",
            },
            {
                "package_id": "pkg-a-gap",
                "cnpj_fundo": "11.111.111/0001-11",
                "work_tier": "P1 material 25-26",
                "batch_id": "P1-001",
                "nome_exibicao": "FIDC A",
                "technical_stage": "download",
                "scope_status": "aderente",
            },
            {
                "package_id": "pkg-b",
                "cnpj_fundo": "22.222.222/0001-22",
                "work_tier": "P0 competência",
                "batch_id": "P0-001",
                "nome_exibicao": "FIDC B",
                "technical_stage": "descoberta",
                "scope_status": "aderente",
            },
            {
                "package_id": "pkg-c",
                "cnpj_fundo": "33.333.333/0001-33",
                "work_tier": "P0 competência",
                "batch_id": "P0-001",
                "nome_exibicao": "FUNDO C",
                "technical_stage": "descoberta",
                "scope_status": "revisar universo",
            },
        ]
    )
    completed = pd.DataFrame([{"cnpj_fundo": "22222222000122", "listing_status": "sem_documento_relevante"}])

    targets = select_package_document_targets(
        evidence,
        existing_status=completed,
        work_tiers=("P0 competência", "P1 material 25-26"),
        max_funds=25,
    )

    assert len(targets) == 1
    assert targets.iloc[0]["cnpj_fundo"] == "11111111000111"
    assert targets.iloc[0]["work_tier"] == "P0 competência"
    assert set(targets.iloc[0]["package_ids"].split(" | ")) == {"pkg-a-delta", "pkg-a-gap"}


def test_package_document_discovery_merge_and_quality_are_incremental():
    existing = pd.DataFrame(
        [
            {
                "cnpj_fundo": "11111111000111",
                "listing_status": "erro_listagem",
                "documents_relevant": 0,
            }
        ]
    )
    updates = pd.DataFrame(
        [
            {
                "cnpj_fundo": "11111111000111",
                "listing_status": "ok",
                "documents_relevant": 2,
                "documents_downloaded": 1,
                "documents_reused": 1,
            }
        ]
    )
    status = merge_package_document_discovery(
        existing,
        updates,
        key_column="cnpj_fundo",
        columns=PACKAGE_DOCUMENT_DISCOVERY_STATUS_COLUMNS,
    )
    documents = pd.DataFrame(
        [
            {"download_status": "baixado"},
            {"download_status": "reutilizado"},
        ]
    )
    quality = package_document_discovery_quality_summary(documents, status, target_funds=1)

    assert len(status) == 1
    assert status.iloc[0]["listing_status"] == "ok"
    assert quality["successful_funds"] == 1
    assert quality["relevant_documents"] == 2
    assert quality["downloaded_documents"] == 1
    assert quality["reused_documents"] == 1
