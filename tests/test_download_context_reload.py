from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

import pandas as pd

from services.fidc_model.b3_cdi import B3CdiMonthlyRate
from services.on_demand_download import download_context_signature


class DownloadContextReloadTests(unittest.TestCase):
    def test_cached_portfolio_and_nested_cdi_survive_real_module_reload(self):
        # Isolate reloads so other tests retain their imported class identities.
        script = textwrap.dedent("""
            import importlib
            import pickle
            from datetime import date
            import pandas as pd
            from services import portfolio_store
            from services.fidc_model import b3_cdi
            from services.on_demand_download import download_context_signature

            def inputs():
                portfolio = portfolio_store.PortfolioRecord(
                    id="robbin", name="Robbin", created_at="2026-10-13", updated_at="2026-10-13",
                    funds=(portfolio_store.PortfolioFund("63615161000100", "Robbin"),),
                )
                rate = b3_cdi.B3CdiMonthlyRate(
                    mes="2026-08", cdi_mensal=0.01123456789, dias_uteis=21,
                    data_inicio=date(2026, 8, 1), data_fim=date(2026, 8, 31), source="B3",
                )
                frame = pd.DataFrame({"PL": [0.0, float("nan"), 1234567.8912345]})
                frame.attrs["source"] = rate
                return portfolio, {"history": frame, "return_inputs": (rate,)}

            cached = inputs()
            baseline = download_context_signature(*cached)
            importlib.reload(portfolio_store)
            importlib.reload(b3_cdi)
            try:
                pickle.dumps(cached, protocol=5)
            except pickle.PicklingError:
                pass
            else:
                raise AssertionError("The production error was not reproduced")
            assert download_context_signature(*cached) == baseline
            assert download_context_signature(*inputs()) == baseline
        """)
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_all_table_values_and_nested_source_metadata_affect_signature(self):
        rate = B3CdiMonthlyRate(
            mes="2026-08", cdi_mensal=0.01123456789, dias_uteis=21,
            data_inicio=date(2026, 8, 1), data_fim=date(2026, 8, 31), source="B3",
        )
        frame = pd.DataFrame({"PL": [Decimal("0"), None, Decimal("1234567.8912345")]})
        frame.attrs["source"] = rate
        original = frame.copy(deep=True)
        baseline = download_context_signature({"history": frame})
        for row, value in ((0, None), (1, Decimal("0")), (2, Decimal("1234567.8912346"))):
            revised = frame.copy(deep=True)
            revised.iloc[row, 0] = value
            self.assertNotEqual(baseline, download_context_signature({"history": revised}))
        revised = frame.copy(deep=True)
        revised.attrs["source"] = replace(rate, cdi_mensal=0.01123456790)
        self.assertNotEqual(baseline, download_context_signature({"history": revised}))
        revised = frame.copy(deep=True)
        revised.index = ["a", "b", "c"]
        self.assertNotEqual(baseline, download_context_signature({"history": revised}))
        pd.testing.assert_frame_equal(original, frame)
        self.assertEqual(original.attrs, frame.attrs)

    def test_slotted_fields_and_additional_instance_state_are_preserved(self):
        @dataclass(slots=True)
        class SlottedSource:
            value: float | None

        @dataclass
        class Source:
            value: float | None

        slotted = SlottedSource(None)
        self.assertNotEqual(download_context_signature(slotted), download_context_signature(SlottedSource(0)))
        source = Source(0)
        source.coverage = "partial"
        baseline = download_context_signature(source)
        source.coverage = "complete"
        self.assertNotEqual(baseline, download_context_signature(source))


if __name__ == "__main__":
    unittest.main()
