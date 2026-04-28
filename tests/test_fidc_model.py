from __future__ import annotations

import json
import unittest
from pathlib import Path

from data_loader import load_model_inputs
from services.fidc_model import (
    RATE_MODE_PRE,
    Premissas,
    annual_252_to_monthly_rate,
    build_flow,
    build_kpis,
    monthly_to_annual_252_rate,
)


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "modelo_publico_fixture.json"


def _build_default_premissas() -> Premissas:
    inputs = load_model_inputs("model_data.json")
    return Premissas(
        volume=inputs.premissas["Volume"],
        tx_cessao_am=inputs.premissas["Tx Cessão (%am)"],
        tx_cessao_cdi_aa=inputs.premissas["Tx Cessão (CDI+ %aa)"],
        custo_adm_aa=inputs.premissas["Custo Adm/Gestão (a.a.)"],
        custo_min=inputs.premissas["Custo Adm/Gestão (mín)"],
        inadimplencia=inputs.premissas["Inadimplência"],
        proporcao_senior=inputs.premissas["Proporção PL Sr."],
        taxa_senior=inputs.premissas["Taxa Sênior"],
        proporcao_mezz=inputs.premissas["Proporção PL Mezz"],
        taxa_mezz=inputs.premissas["Taxa Mezz"],
    )


class FidcModelParityTest(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.inputs = load_model_inputs("model_data.json")
        cls.periods = build_flow(
            cls.inputs.datas,
            cls.inputs.feriados,
            cls.inputs.curva_du,
            cls.inputs.curva_cdi,
            _build_default_premissas(),
        )
        cls.kpis = build_kpis(cls.periods)

    def assertAlmostOptional(self, actual, expected, delta=1e-7):
        if expected is None:
            self.assertIsNone(actual)
            return
        self.assertIsNotNone(actual)
        self.assertAlmostEqual(actual, expected, delta=delta)

    def test_first_period_contract(self):
        first = self.periods[0]
        self.assertEqual(first.indice, 0)
        self.assertEqual(first.dc, 0)
        self.assertEqual(first.du, 0)
        self.assertIsNone(first.pre_di)
        self.assertEqual(first.pmt_senior, -900000.0)
        self.assertEqual(first.pmt_mezz, -50000.0)
        self.assertEqual(first.pl_sub_jr, 50000.0)
        self.assertIsNone(first.pl_sub_jr_modelo)

    def test_periods_match_fluxo_base_fixture(self):
        comparable_fields = [
            "indice",
            "dc",
            "du",
            "pre_di",
            "taxa_senior",
            "fra_senior",
            "taxa_mezz",
            "fra_mezz",
            "carteira",
            "fluxo_carteira",
            "pl_fidc",
            "custos_adm",
            "inadimplencia_despesa",
            "pmt_senior",
            "vp_pmt_senior",
            "pl_senior",
            "pmt_mezz",
            "pl_mezz",
        ]
        for actual, expected in zip(self.periods[1:], self.fixture["timeline"][1:]):
            self.assertEqual(actual.data.date().isoformat(), expected["data"])
            for field in comparable_fields:
                self.assertAlmostOptional(getattr(actual, field), expected[field])
            self.assertAlmostOptional(actual.pl_sub_jr_modelo, expected["pl_sub_jr"])
            self.assertAlmostOptional(actual.subordinacao_pct_modelo, expected["subordinacao_pct"])

    def test_kpis_match_fixture_and_junior_is_not_fabricated(self):
        self.assertAlmostOptional(self.kpis.xirr_senior, self.fixture["kpis"]["xirr_senior"])
        self.assertAlmostOptional(self.kpis.xirr_mezz, self.fixture["kpis"]["xirr_mezz"])
        self.assertIsNone(self.kpis.xirr_sub_jr)
        self.assertIsNone(self.kpis.taxa_retorno_sub_jr_cdi)
        self.assertAlmostOptional(self.kpis.duration_senior_anos, self.fixture["kpis"]["duration_senior_anos"])
        self.assertAlmostOptional(self.kpis.pre_di_duration, self.fixture["kpis"]["pre_di_duration"])

    def test_annual_252_monthly_conversion_roundtrip(self):
        monthly_rate = 0.02
        annual_rate = monthly_to_annual_252_rate(monthly_rate)

        self.assertAlmostEqual(monthly_rate, annual_252_to_monthly_rate(annual_rate), delta=1e-12)

    def test_prefixed_quota_rate_uses_informed_annual_rate(self):
        premissas = _build_default_premissas()
        premissas = Premissas(
            **{
                **premissas.__dict__,
                "tipo_taxa_senior": RATE_MODE_PRE,
                "taxa_senior": 0.12,
                "tipo_taxa_mezz": RATE_MODE_PRE,
                "taxa_mezz": 0.15,
            }
        )

        periods = build_flow(
            self.inputs.datas,
            self.inputs.feriados,
            self.inputs.curva_du,
            self.inputs.curva_cdi,
            premissas,
        )

        self.assertAlmostEqual(0.12, periods[1].taxa_senior)
        self.assertAlmostEqual(0.15, periods[1].taxa_mezz)

    def test_explicit_subordinated_pl_proportion_is_used(self):
        premissas = _build_default_premissas()
        premissas = Premissas(
            **{
                **premissas.__dict__,
                "proporcao_senior": 0.7,
                "proporcao_mezz": 0.2,
                "proporcao_subordinada": 0.1,
            }
        )

        periods = build_flow(
            self.inputs.datas,
            self.inputs.feriados,
            self.inputs.curva_du,
            self.inputs.curva_cdi,
            premissas,
        )

        self.assertAlmostEqual(100000.0, periods[0].pl_sub_jr)


if __name__ == "__main__":
    unittest.main()
