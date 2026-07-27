from __future__ import annotations

from pathlib import Path

import pandas as pd

from services.industry_closed_offer_rankings import build_closed_offer_top15


def _write_fixture(data_dir: Path) -> None:
    cohort_rows = []
    offer_rows = []
    offer_id = 1
    for order, label, start, end, row_count in (
        (1, "2022 FY parcial", "2022-01-01", "2022-12-31", 7),
        (2, "2023 FY", "2023-01-01", "2023-12-31", 16),
        (3, "2024 FY", "2024-01-01", "2024-12-31", 16),
        (4, "2025 FY", "2025-01-01", "2025-12-31", 16),
        (5, "2026 jan-jun", "2026-01-01", "2026-06-30", 16),
    ):
        for rank in range(1, row_count + 1):
            volume = float((20 - rank) * 100_000_000)
            cohort_rows.append(
                {
                    "period_order": order,
                    "period_label": label,
                    "period_start": start,
                    "period_end": end,
                    "numero_requerimento": str(offer_id),
                    "data_encerramento": end,
                    "cnpj_emissor": str(offer_id).zfill(14),
                    "nome_emissor": f"FIDC {label} {rank}",
                    "registered_volume_brl": volume,
                    "rite": "Automático RCVM 160",
                    "leader_name": "",
                    "distribution_regime": "",
                    "target_public": "",
                    "investor_count": "",
                    "investor_person_natural": 0,
                    "investor_funds": 0,
                    "investor_financial_institutions": 0,
                    "investor_other_legal_entities": 0,
                    "investor_pension": 0,
                    "investor_insurers": 0,
                    "investor_foreign": 0,
                    "investor_clubs": 0,
                    "source_dataset": "oferta_resolucao_160.csv",
                    "source_url": "https://dados.cvm.gov.br/",
                    "source_as_of_date": "2026-07-21",
                    "scope": "Cotas de FIDC | oferta primária | Oferta Encerrada",
                }
            )
            offer_rows.append(
                {
                    "offer_id": str(offer_id),
                    "issuer_name": f"FIDC {label} {rank}",
                    "leader_name": (
                        "ITAU BBA ASSESSORIA FINANCEIRA S.A."
                        if rank in {1, 2}
                        else "OUTRO COORDENADOR"
                    ),
                    "distribution_regime": (
                        "Garantia Firme de Colocação"
                        if rank in {1, 3}
                        else "Melhores Esforços"
                    ),
                    "target_public": "Público Geral" if rank == 1 else "Profissional",
                    "investor_count": rank,
                    "originator_group": (
                        "" if rank == 1 else f"Originador {rank}"
                    ),
                    "originator_source": "issuer_name",
                    "originator_evidence": "evidência",
                    "status": "Oferta Encerrada",
                    "offer_type": "PRIMARIA",
                    "security": "Cotas de FIDC",
                }
            )
            offer_id += 1
    pd.DataFrame(cohort_rows).to_csv(
        data_dir / "industry_closed_offer_ticket_cohort.csv.gz",
        index=False,
        compression="gzip",
    )
    pd.DataFrame(offer_rows).to_csv(
        data_dir / "industry_offers.csv.gz",
        index=False,
        compression="gzip",
    )
    pd.DataFrame(
        [
            {
                "offer_id": "1",
                "rating_document_count": "2",
                "latest_document_id": "doc-1",
                "latest_document_date": "01/07/2026",
                "rating_agency": "Agência Teste",
                "rating_assigned": "AAA(sf)",
                "rating_scope": "Série sênior",
                "rating_source_type": "FundosNet",
                "rating_source_url": "https://example.test/doc-1",
                "rating_match_status": "vínculo por oferta e série",
                "rating_evidence": "Documento identifica a oferta e a série.",
                "rating_availability_status": "rating da emissão verificado",
                "rating_limitation": "Aplicável somente à série indicada.",
            }
        ]
    ).to_csv(data_dir / "industry_offer_rating_by_offer.csv", index=False)


def test_top15_uses_closed_cohort_and_enriches_offer_metadata(
    tmp_path: Path,
) -> None:
    _write_fixture(tmp_path)

    outputs = build_closed_offer_top15(tmp_path)

    assert len(outputs.rankings) == 67
    assert outputs.rankings.groupby("period_label")["rank"].apply(list).to_dict() == {
        "2022 FY parcial": list(range(1, 8)),
        "2023 FY": list(range(1, 16)),
        "2024 FY": list(range(1, 16)),
        "2025 FY": list(range(1, 16)),
        "2026 jan-jun": list(range(1, 16)),
    }
    first = outputs.rankings.iloc[0]
    assert first["originator_group"] == "Não identificado"
    assert first["ibba_coord_lead_label"] == "Sim"
    assert first["firm_commitment_label"] == "Sim"
    assert first["publico"] == "Geral"
    assert first["rating_agency"] == "Agência Teste"
    assert first["rating_assigned"] == "AAA(sf)"
    assert first["rating_match_status"] == "vínculo por oferta e série"
    assert outputs.rankings.iloc[1]["rating_agency"] == "N/D"
    assert outputs.summary.set_index("period_label")[
        "metadata_matched_top15"
    ].to_dict() == {
        "2022 FY parcial": 7,
        "2023 FY": 15,
        "2024 FY": 15,
        "2025 FY": 15,
        "2026 jan-jun": 15,
    }
    assert outputs.summary["ibba_lead_offers_top15"].eq(2).all()
    assert outputs.summary["ibba_firm_commitment_offers_top15"].eq(1).all()
