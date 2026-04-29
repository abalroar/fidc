from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path

from data_loader import load_model_inputs
from services.fidc_model import (
    AMORTIZATION_MODE_BULLET,
    AMORTIZATION_MODE_LINEAR,
    AMORTIZATION_MODE_WORKBOOK,
    INTEREST_PAYMENT_MODE_AFTER_GRACE,
    INTEREST_PAYMENT_MODE_PERIODIC,
    RATE_MODE_PRE,
    Premissas,
    annual_252_to_monthly_rate,
    build_flow,
    build_kpis,
    cession_discount_to_monthly_rate,
    monthly_to_annual_252_rate,
    monthly_rate_to_cession_discount,
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
        carteira_revolvente=False,
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

    def test_cession_discount_converts_to_monthly_rate(self):
        discount_rate = 0.05
        monthly_rate = cession_discount_to_monthly_rate(discount_rate)

        self.assertAlmostEqual((100.0 / 95.0) - 1.0, monthly_rate, delta=1e-12)
        self.assertAlmostEqual(discount_rate, monthly_rate_to_cession_discount(monthly_rate), delta=1e-12)

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

    def test_expected_and_unexpected_losses_drive_portfolio_loss(self):
        monthly_dates = [datetime(2025, 1, 1), datetime(2025, 1, 31)]
        premissas = Premissas(
            volume=1_000_000.0,
            tx_cessao_am=0.0,
            tx_cessao_cdi_aa=None,
            custo_adm_aa=0.0,
            custo_min=0.0,
            inadimplencia=0.0,
            proporcao_senior=0.0,
            taxa_senior=0.0,
            proporcao_mezz=0.0,
            taxa_mezz=0.0,
            proporcao_subordinada=1.0,
            tipo_taxa_senior=RATE_MODE_PRE,
            tipo_taxa_mezz=RATE_MODE_PRE,
            perda_esperada_am=0.01,
            perda_inesperada_am=0.02,
        )

        periods = build_flow(monthly_dates, [], [1.0, 2000.0], [0.0, 0.0], premissas)

        self.assertAlmostEqual(10_000.0, periods[1].perda_esperada_despesa)
        self.assertAlmostEqual(20_000.0, periods[1].perda_inesperada_despesa)
        self.assertAlmostEqual(30_000.0, periods[1].perda_carteira_despesa)
        self.assertAlmostEqual(periods[1].perda_carteira_despesa, periods[1].inadimplencia_despesa)
        self.assertAlmostEqual(periods[1].fluxo_carteira - 30_000.0, periods[1].resultado_carteira_liquido)

    def test_revolving_portfolio_keeps_open_receivables_base_at_initial_volume(self):
        monthly_dates = [datetime(2025, 1, 1), datetime(2025, 2, 1), datetime(2025, 3, 1)]
        premissas = Premissas(
            volume=1_000_000.0,
            tx_cessao_am=0.10,
            tx_cessao_cdi_aa=None,
            custo_adm_aa=0.0,
            custo_min=0.0,
            inadimplencia=0.0,
            proporcao_senior=0.0,
            taxa_senior=0.0,
            proporcao_mezz=0.0,
            taxa_mezz=0.0,
            proporcao_subordinada=1.0,
            tipo_taxa_senior=RATE_MODE_PRE,
            tipo_taxa_mezz=RATE_MODE_PRE,
            carteira_revolvente=True,
        )

        periods = build_flow(monthly_dates, [], [1.0, 2000.0], [0.0, 0.0], premissas)

        self.assertAlmostEqual(1_000_000.0, periods[1].carteira)
        self.assertAlmostEqual(1_000_000.0, periods[2].carteira)
        self.assertGreater(periods[2].pl_fidc, periods[1].pl_fidc)

    def test_acquisition_premium_reduces_initial_subordination(self):
        premissas = Premissas(
            volume=1_000_000.0,
            tx_cessao_am=0.0,
            tx_cessao_cdi_aa=None,
            custo_adm_aa=0.0,
            custo_min=0.0,
            inadimplencia=0.0,
            proporcao_senior=0.75,
            taxa_senior=0.0,
            proporcao_mezz=0.15,
            taxa_mezz=0.0,
            proporcao_subordinada=0.10,
            tipo_taxa_senior=RATE_MODE_PRE,
            tipo_taxa_mezz=RATE_MODE_PRE,
            agio_aquisicao=0.02,
        )

        periods = build_flow([datetime(2025, 1, 1), datetime(2025, 2, 1)], [], [1.0, 2000.0], [0.0, 0.0], premissas)

        self.assertAlmostEqual(20_000.0, periods[0].agio_aquisicao_despesa)
        self.assertAlmostEqual(980_000.0, periods[0].pl_fidc)
        self.assertAlmostEqual(80_000.0, periods[0].pl_sub_jr)

    def test_cession_rate_floor_uses_senior_remuneration_plus_excess_spread(self):
        premissas = Premissas(
            volume=1_000_000.0,
            tx_cessao_am=0.0,
            tx_cessao_cdi_aa=None,
            custo_adm_aa=0.0,
            custo_min=0.0,
            inadimplencia=0.0,
            proporcao_senior=1.0,
            taxa_senior=0.12,
            proporcao_mezz=0.0,
            taxa_mezz=0.0,
            proporcao_subordinada=0.0,
            tipo_taxa_senior=RATE_MODE_PRE,
            tipo_taxa_mezz=RATE_MODE_PRE,
            excesso_spread_senior_am=0.01,
        )
        expected_floor = annual_252_to_monthly_rate(
            (1.0 + 0.12) * (1.0 + monthly_to_annual_252_rate(0.01)) - 1.0
        )

        periods = build_flow([datetime(2025, 1, 1), datetime(2025, 2, 1)], [], [1.0, 2000.0], [0.0, 0.0], premissas)

        self.assertAlmostEqual(expected_floor, periods[1].tx_cessao_am_piso)
        self.assertAlmostEqual(expected_floor, periods[1].tx_cessao_am_aplicada)

    def test_workbook_principal_schedule_is_capped_for_longer_terms(self):
        monthly_dates = [datetime(2025 + (month // 12), (month % 12) + 1, 1) for month in range(61)]
        premissas = Premissas(
            volume=1_000_000.0,
            tx_cessao_am=0.0,
            tx_cessao_cdi_aa=None,
            custo_adm_aa=0.0,
            custo_min=0.0,
            inadimplencia=0.0,
            proporcao_senior=0.75,
            taxa_senior=0.0,
            proporcao_mezz=0.15,
            taxa_mezz=0.0,
            proporcao_subordinada=0.10,
            tipo_taxa_senior=RATE_MODE_PRE,
            tipo_taxa_mezz=RATE_MODE_PRE,
            amortizacao_senior=AMORTIZATION_MODE_WORKBOOK,
            amortizacao_mezz=AMORTIZATION_MODE_WORKBOOK,
        )

        periods = build_flow(monthly_dates, [], [1.0, 2000.0], [0.0, 0.0], premissas)

        self.assertAlmostEqual(0.0, periods[-1].pl_senior)
        self.assertAlmostEqual(0.0, periods[-1].pl_mezz)
        self.assertGreaterEqual(min(period.pl_senior for period in periods), 0.0)
        self.assertGreaterEqual(min(period.pl_mezz for period in periods), 0.0)

    def test_custom_linear_and_bullet_amortization_modes_change_principal_schedule(self):
        monthly_dates = [datetime(2025 + (month // 12), (month % 12) + 1, 1) for month in range(13)]
        premissas = Premissas(
            volume=1_000_000.0,
            tx_cessao_am=0.0,
            tx_cessao_cdi_aa=None,
            custo_adm_aa=0.0,
            custo_min=0.0,
            inadimplencia=0.0,
            proporcao_senior=0.60,
            taxa_senior=0.0,
            proporcao_mezz=0.20,
            taxa_mezz=0.0,
            proporcao_subordinada=0.20,
            tipo_taxa_senior=RATE_MODE_PRE,
            tipo_taxa_mezz=RATE_MODE_PRE,
            prazo_senior_anos=1.0,
            prazo_mezz_anos=1.0,
            amortizacao_senior=AMORTIZATION_MODE_LINEAR,
            amortizacao_mezz=AMORTIZATION_MODE_BULLET,
            inicio_amortizacao_senior_meses=6,
        )

        periods = build_flow(monthly_dates, [], [1.0, 2000.0], [0.0, 0.0], premissas)

        self.assertEqual(0.0, periods[6].principal_senior)
        self.assertAlmostEqual(600_000.0 / 6.0, periods[7].principal_senior)
        self.assertAlmostEqual(200_000.0, periods[12].principal_mezz)
        self.assertAlmostEqual(0.0, periods[-1].pl_senior)
        self.assertAlmostEqual(0.0, periods[-1].pl_mezz)

    def test_interest_after_grace_defers_payment_until_amortization_start(self):
        monthly_dates = [datetime(2025 + (month // 12), (month % 12) + 1, 1) for month in range(8)]
        base_kwargs = dict(
            volume=1_000_000.0,
            tx_cessao_am=0.0,
            tx_cessao_cdi_aa=None,
            custo_adm_aa=0.0,
            custo_min=0.0,
            inadimplencia=0.0,
            proporcao_senior=1.0,
            taxa_senior=0.12,
            proporcao_mezz=0.0,
            taxa_mezz=0.0,
            proporcao_subordinada=0.0,
            tipo_taxa_senior=RATE_MODE_PRE,
            tipo_taxa_mezz=RATE_MODE_PRE,
            amortizacao_senior=AMORTIZATION_MODE_LINEAR,
            amortizacao_mezz=AMORTIZATION_MODE_LINEAR,
            inicio_amortizacao_senior_meses=7,
        )
        periodic = build_flow(
            monthly_dates,
            [],
            [1.0, 2000.0],
            [0.0, 0.0],
            Premissas(**base_kwargs, juros_senior=INTEREST_PAYMENT_MODE_PERIODIC),
        )
        deferred = build_flow(
            monthly_dates,
            [],
            [1.0, 2000.0],
            [0.0, 0.0],
            Premissas(**base_kwargs, juros_senior=INTEREST_PAYMENT_MODE_AFTER_GRACE),
        )

        self.assertGreater(periodic[1].juros_senior, 0.0)
        self.assertEqual(0.0, deferred[1].juros_senior)
        self.assertGreater(deferred[7].juros_senior, periodic[7].juros_senior)


if __name__ == "__main__":
    unittest.main()
