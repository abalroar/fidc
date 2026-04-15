from __future__ import annotations

import unittest

from services.fundonet_client import FundosNetClient


class FundosNetClientTests(unittest.TestCase):
    def test_timeout_and_retry_are_relaxed_for_catalog_stages(self) -> None:
        client = FundosNetClient(timeout_seconds=30, max_retries=2)

        self.assertEqual(45, client._timeout_for_stage("abrir_gerenciador"))
        self.assertEqual(45, client._timeout_for_stage("listar_documentos"))
        self.assertEqual(3, client._retry_limit_for_stage("abrir_gerenciador"))
        self.assertEqual(3, client._retry_limit_for_stage("listar_documentos"))

    def test_timeout_defaults_remain_for_other_stages(self) -> None:
        client = FundosNetClient(timeout_seconds=30, max_retries=2)

        self.assertEqual(40, client._timeout_for_stage("download_documento"))
        self.assertEqual(30, client._timeout_for_stage("qualquer_outra_etapa"))
        self.assertEqual(2, client._retry_limit_for_stage("download_documento"))


if __name__ == "__main__":
    unittest.main()
