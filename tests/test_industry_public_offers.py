from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from services.industry_public_offers import (
    FIDC_CANONICAL,
    load_public_primary_closed_offers,
)


def test_public_offer_universe_combines_automatic_and_legacy_rites(
    tmp_path: Path,
) -> None:
    automatic = pd.DataFrame(
        [
            {
                "Numero_Requerimento": "16001",
                "Data_Encerramento": "2025-06-10",
                "Status_Requerimento": "Oferta Encerrada",
                "Valor_Mobiliario": "Cotas de FIDC",
                "Tipo_Oferta": "Primária",
                "CNPJ_Emissor": "11.111.111/0001-11",
                "Nome_Emissor": "FIDC AUTOMÁTICO",
                "Valor_Total_Registrado": "100000000",
                "Nome_Lider": "LÍDER A",
            },
            {
                "Numero_Requerimento": "16002",
                "Data_Encerramento": "2025-06-10",
                "Status_Requerimento": "Oferta Encerrada",
                "Valor_Mobiliario": "Cotas de FIAGRO - FIDC",
                "Tipo_Oferta": "Primária",
                "CNPJ_Emissor": "22.222.222/0001-22",
                "Nome_Emissor": "FIAGRO EXCLUÍDO",
                "Valor_Total_Registrado": "50000000",
                "Nome_Lider": "LÍDER B",
            },
        ]
    )
    legacy_base = {
        "Numero_Registro_Oferta": "CVM/SRE/LEG/2025/001",
        "Numero_Processo": "19957.000001/2025-00",
        "Data_Encerramento_Oferta": "20/06/2025",
        "Tipo_Oferta": "Primária",
        "CNPJ_Emissor": "33.333.333/0001-33",
        "Nome_Emissor": "FIDC ORDINÁRIO",
        "Nome_Lider": "LÍDER C",
        "Rito_Oferta": "Registro ordinário RCVM 160",
        "Quantidade_Total": "1000",
        "Nr_Pessoa_Fisica": "2",
        "Qtd_Pessoa_Fisica": "100",
    }
    legacy = pd.DataFrame(
        [
            {
                **legacy_base,
                "Tipo_Ativo": "Cotas Seniores de FIDC",
                "Valor_Total": "200000000",
            },
            {
                **legacy_base,
                "Tipo_Ativo": "Cotas Subordinadas de FIDC",
                "Valor_Total": "50000000",
            },
            {
                **legacy_base,
                "Numero_Registro_Oferta": "ABERTA",
                "Data_Encerramento_Oferta": "",
                "Tipo_Ativo": "Cotas de FIDC",
                "Valor_Total": "900000000",
            },
        ]
    )
    archive_path = tmp_path / "ofertas.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "oferta_resolucao_160.csv",
            automatic.to_csv(index=False, sep=";").encode("latin-1"),
        )
        archive.writestr(
            "oferta_distribuicao.csv",
            legacy.to_csv(index=False, sep=";").encode("latin-1"),
        )

    offers, _ = load_public_primary_closed_offers(
        archive_path,
        cutoff="2025-12-31",
    )
    fidcs = offers[offers["canonical_instrument"].eq(FIDC_CANONICAL)]

    assert len(fidcs) == 2
    assert fidcs["registered_volume_brl"].sum() == 350_000_000
    ordinary = fidcs[fidcs["source_dataset"].eq("oferta_distribuicao.csv")]
    assert len(ordinary) == 1
    assert ordinary.iloc[0]["registered_volume_brl"] == 250_000_000
    assert "classes do mesmo FIDC" not in ordinary.iloc[0]["status_basis"]
