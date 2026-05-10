from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

import pandas as pd

from services.regulatory_profiles import load_curated_regulatory_profile, payment_calendar_rows


class RegulatoryProfilesTests(unittest.TestCase):
    def test_load_curated_profile_filters_by_cnpj(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            pd.DataFrame(
                [
                    {
                        "Fundo": "A",
                        "CNPJ": "50.473.039/0001-02",
                        "Cota/Classe": "Sênior 1",
                        "Amortização principal": "15/12/2025: 25,00%",
                    },
                    {
                        "Fundo": "B",
                        "CNPJ": "00.000.000/0001-00",
                        "Cota/Classe": "Sênior X",
                        "Amortização principal": "",
                    },
                ]
            ).to_csv(base / "seller_cotas_emissoes_pagamentos.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "Fundo": "A",
                        "CNPJ": "50.473.039/0001-02",
                        "Critério": "Índice de Subordinação",
                        "Monitorabilidade IME": "direto com validação",
                    }
                ]
            ).to_csv(base / "seller_criteria_monitoraveis_ime.csv", index=False)

            profile = load_curated_regulatory_profile("50473039000102", base_dir=base)

        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual(1, len(profile.emissions_df))
        self.assertEqual(1, len(profile.criteria_df))
        self.assertEqual("Sênior 1", profile.emissions_df.iloc[0]["Cota/Classe"])

    def test_payment_calendar_rows_extracts_dated_amortizations_and_recurring_interest(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "Cota/Classe": "Sênior 1",
                    "Tipo": "Sênior",
                    "Juros/remuneração": "Semestral, a cada 6 meses",
                    "Amortização principal": "15/12/2025: 25,00%; 15/01/2026: 33,33%",
                    "Fonte": "doc p.1",
                }
            ]
        )

        rows = payment_calendar_rows(frame)

        self.assertEqual(3, len(rows))
        self.assertEqual("Juros/remuneração", rows[0]["Evento"])
        self.assertEqual("15/12/2025", rows[1]["Data/janela"])
        self.assertEqual("25,00%", rows[1]["Detalhe"])
        self.assertEqual("15/01/2026", rows[2]["Data/janela"])


if __name__ == "__main__":
    unittest.main()

