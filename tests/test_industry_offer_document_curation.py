from __future__ import annotations

import pandas as pd

from services.industry_offer_document_curation import (
    build_offer_document_curation,
)


class _Response:
    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.content = b""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class _Session:
    def get(self, url: str, timeout: int) -> _Response:
        if "/participantes/" in url:
            offer_id = url.rsplit("/", 1)[-1]
            if offer_id == "1":
                return _Response(
                    [
                        {
                            "cnpjInstituicao": "04.845.753/0001-59",
                            "razaoSocial": "ITAÚ BBA ASSESSORIA FINANCEIRA S.A.",
                            "tipo": "Coordenador",
                        }
                    ]
                )
            return _Response([])
        if "/documentosPublicados/" in url:
            return _Response([])
        raise AssertionError(f"URL não esperada: {url}")


def test_document_curation_uses_official_participants_for_ibba_flag() -> None:
    cohort_rows = []
    offer_rows = []
    offer_id = 1
    for period in ("2025 FY", "2026 jan-jun"):
        for rank in range(1, 16):
            cohort_rows.append(
                {
                    "numero_requerimento": str(offer_id),
                    "period_label": period,
                    "nome_emissor": f"FIDC {offer_id}",
                    "registered_volume_brl": 1_000_000_000 - rank,
                }
            )
            offer_rows.append(
                {
                    "offer_id": str(offer_id),
                    "originator_group": "",
                }
            )
            offer_id += 1

    result = build_offer_document_curation(
        pd.DataFrame(cohort_rows),
        pd.DataFrame(offer_rows),
        session=_Session(),
    )

    first = result[result["offer_id"].eq("1")].iloc[0]
    second = result[result["offer_id"].eq("2")].iloc[0]
    assert first["ibba_participant_label"] == "Sim"
    assert first["ibba_participant_roles"] == "Coordenador"
    assert second["ibba_participant_label"] == "Não"
    assert result["participants_source_url"].str.contains(
        "web.cvm.gov.br/sre-publico-cvm"
    ).all()
