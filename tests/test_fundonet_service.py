from __future__ import annotations

from datetime import datetime
import unittest

import pandas as pd

from services.fundonet_models import DocumentoFundo
from services.fundonet_service import InformeMensalService, select_latest_documents


class BuildTidyContractTests(unittest.TestCase):
    def test_keep_required_columns_and_preserve_extra_columns(self) -> None:
        contas_base_df = pd.DataFrame(
            [
                {
                    "documento_id": 10,
                    "competencia": "01/2026",
                    "bloco": "APLIC_ATIVO",
                    "sub_bloco": "CRED_EXISTE",
                    "tag": "VL_DISPONIB",
                    "tag_path": "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_DISPONIB",
                    "descricao": "VALOR DAS DISPONIBILIDADES",
                    "valor_raw": "123,45",
                    "valor_num": 123.45,
                    "valor_excel": 123.45,
                    "ordem_xml": 12,
                    "schema_match_strategy": "exact",
                }
            ]
        )

        tidy_df = InformeMensalService._build_tidy_contract(contas_base_df=contas_base_df, cnpj_fundo="33254370000104")

        expected_prefix = [
            "cnpj_fundo",
            "documento_id",
            "competencia",
            "bloco",
            "sub_bloco",
            "tag",
            "tag_path",
            "descricao",
            "valor_raw",
            "valor_num",
            "fonte",
        ]
        self.assertEqual(expected_prefix, tidy_df.columns.tolist()[: len(expected_prefix)])
        self.assertIn("schema_match_strategy", tidy_df.columns.tolist())
        self.assertEqual("33254370000104", tidy_df.iloc[0]["cnpj_fundo"])
        self.assertEqual("fundonet", tidy_df.iloc[0]["fonte"])

    def test_raise_explicit_error_when_parser_contract_is_invalid(self) -> None:
        contas_base_df = pd.DataFrame(
            [
                {
                    "documento_id": 10,
                    "competencia": "01/2026",
                    "bloco": "APLIC_ATIVO",
                    "sub_bloco": "",
                    "tag": "VL_DISPONIB",
                    "tag_path": "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_DISPONIB",
                    "descricao": "VALOR DAS DISPONIBILIDADES",
                    "valor_raw": "123,45",
                    "valor_num": 123.45,
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "colunas ausentes em contas_base_df: ordem_xml, valor_excel"):
            InformeMensalService._build_tidy_contract(contas_base_df=contas_base_df, cnpj_fundo="33254370000104")


class SelectLatestDocumentsTests(unittest.TestCase):
    def test_prefer_active_highest_version_latest_delivery(self) -> None:
        base = {
            "categoria": "Informes Periódicos",
            "tipo": "Informe Mensal Estruturado ",
            "especie": "",
            "nome_fundo": "Teste",
            "nome_arquivo": None,
            "fundo_ou_classe": "Fundo",
            "raw": {},
        }
        docs = [
            DocumentoFundo(
                id=973064,
                data_referencia="07/2025",
                data_entrega="15/08/2025 17:48",
                versao=1,
                status="IC",
                **base,
            ),
            DocumentoFundo(
                id=975452,
                data_referencia="07/2025",
                data_entrega="21/08/2025 09:25",
                versao=2,
                status="IC",
                **base,
            ),
            DocumentoFundo(
                id=984542,
                data_referencia="07/2025",
                data_entrega="05/09/2025 10:40",
                versao=3,
                status="AC",
                **base,
            ),
        ]

        selected = select_latest_documents(docs)

        self.assertEqual(1, len(selected))
        self.assertEqual(984542, selected[0].id)
        self.assertEqual(datetime(2025, 9, 5, 10, 40), selected[0].data_entrega_dt)


if __name__ == "__main__":
    unittest.main()
