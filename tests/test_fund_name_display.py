import unittest

from services.fund_name_display import short_fund_name


class FundNameDisplayTests(unittest.TestCase):
    def test_short_fund_name_uses_known_portfolio_aliases(self) -> None:
        self.assertEqual(
            "Delta Consig.",
            short_fund_name("CONSIGNADO DELTA RECEIVABLES I FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS"),
        )
        self.assertEqual(
            "MT Consig. I",
            short_fund_name("MT CONSIGNADO PRIVADO I FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS"),
        )
        self.assertEqual(
            "MC II",
            short_fund_name(
                "MERCADO CRÉDITO II BRASIL FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS DE RESPONSABILIDADE LIMITADA"
            ),
        )

    def test_short_fund_name_falls_back_to_clean_truncated_label(self) -> None:
        self.assertEqual(
            "EXEMPLO LONGO",
            short_fund_name("FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS EXEMPLO LONGO RESPONSABILIDADE LIMITADA"),
        )
