from __future__ import annotations

import unittest
from unittest.mock import patch

from services.fundonet_client import FundosNetClient


class ResolveFundoTests(unittest.TestCase):
    def test_resolve_fundo_keeps_working_when_public_page_has_no_csrf(self) -> None:
        html = """
        <!doctype html>
        <html>
        <head><meta charset="utf-8"></head>
        <body>
          <input
            type="hidden"
            disabled="disabled"
            class="fundoItemInicial"
            data-id="18252"
            data-text="FUNDO TESTE"
          />
        </body>
        </html>
        """
        client = FundosNetClient()

        with patch.object(client, "_get_text", return_value=html):
            resolution = client.resolve_fundo("33.254.370/0001-04")

        self.assertEqual("33254370000104", resolution.cnpj)
        self.assertEqual("18252", resolution.id_fundo)
        self.assertEqual("FUNDO TESTE", resolution.nome_fundo)
        self.assertIsNone(client.csrf_token)
        self.assertEqual(
            "https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM?cnpjFundo=33254370000104",
            client.referer_url,
        )

    def test_resolve_fundo_accepts_alternative_html_attribute_order_and_csrf_syntax(self) -> None:
        html = """
        <html>
        <head>
          <script>window.csrf_token = 'abc-123';</script>
        </head>
        <body>
          <input data-text="FUNDO &amp; TESTE" class="foo fundoItemInicial bar" data-id="18252" />
        </body>
        </html>
        """
        client = FundosNetClient()

        with patch.object(client, "_get_text", return_value=html):
            resolution = client.resolve_fundo("33254370000104")

        self.assertEqual("18252", resolution.id_fundo)
        self.assertEqual("FUNDO & TESTE", resolution.nome_fundo)
        self.assertEqual("abc-123", client.csrf_token)


if __name__ == "__main__":
    unittest.main()
