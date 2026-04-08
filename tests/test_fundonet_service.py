from __future__ import annotations

import unittest

import pandas as pd

from services.fundonet_service import InformeMensalService


class BuildTidyContractTests(unittest.TestCase):
    def test_keep_required_columns_and_preserve_extra_columns(self) -> None:
        contas_df = pd.DataFrame(
            [
                {
                    "documento_id": 10,
                    "data_referencia": "2026-01-31",
                    "conta_codigo": "1.01",
                    "conta_descricao": "Disponibilidades",
                    "conta_caminho": "1 - Ativo > 1.01 - Disponibilidades",
                    "valor": 123.45,
                    "coluna_informe": "2026-01",
                }
            ]
        )

        tidy_df = InformeMensalService._build_tidy_contract(contas_df=contas_df, cnpj_fundo="33254370000104")

        expected_prefix = [
            "cnpj_fundo",
            "documento_id",
            "data_referencia",
            "conta_codigo",
            "conta_descricao",
            "conta_caminho",
            "valor",
            "fonte",
        ]
        self.assertEqual(expected_prefix, tidy_df.columns.tolist()[: len(expected_prefix)])
        self.assertIn("coluna_informe", tidy_df.columns.tolist())
        self.assertEqual("33254370000104", tidy_df.iloc[0]["cnpj_fundo"])
        self.assertEqual("fundonet", tidy_df.iloc[0]["fonte"])

    def test_raise_explicit_error_when_parser_contract_is_invalid(self) -> None:
        contas_df = pd.DataFrame(
            [
                {
                    "documento_id": 10,
                    "conta_codigo": "1.01",
                    "conta_descricao": "Disponibilidades",
                    "conta_caminho": "1 - Ativo > 1.01 - Disponibilidades",
                    "valor": 123.45,
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "colunas ausentes em contas_df: data_referencia"):
            InformeMensalService._build_tidy_contract(contas_df=contas_df, cnpj_fundo="33254370000104")


if __name__ == "__main__":
    unittest.main()
