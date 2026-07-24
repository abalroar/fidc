from __future__ import annotations

from pathlib import Path

import pandas as pd

from services.industry_closed_offer_rankings import build_closed_offer_top15


def _write_fixture(data_dir: Path) -> None:
    cohort_rows = []
    offer_rows = []
    offer_id = 1
    for order, label, start, end in (
        (2, "2025 FY", "2025-01-01", "2025-12-31"),
        (3, "2026 jan-jun", "2026-01-01", "2026-06-30"),
    ):
        for rank in range(1, 17):
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


def test_top15_uses_closed_cohort_and_enriches_offer_metadata(
    tmp_path: Path,
) -> None:
    _write_fixture(tmp_path)

    outputs = build_closed_offer_top15(tmp_path)

    assert len(outputs.rankings) == 30
    assert outputs.rankings.groupby("period_label")["rank"].apply(list).to_dict() == {
        "2025 FY": list(range(1, 16)),
        "2026 jan-jun": list(range(1, 16)),
    }
    first = outputs.rankings.iloc[0]
    assert first["originator_group"] == "Não identificado"
    assert first["ibba_coord_lead_label"] == "Sim"
    assert first["firm_commitment_label"] == "Sim"
    assert first["publico"] == "Geral"
    assert outputs.summary["metadata_matched_top15"].eq(15).all()
    assert outputs.summary["ibba_lead_offers_top15"].eq(2).all()
    assert outputs.summary["ibba_firm_commitment_offers_top15"].eq(1).all()
