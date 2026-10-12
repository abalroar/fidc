from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from services.portfolio_presentation_context import build_portfolio_presentation_context


def test_reference_dates_keep_common_historical_and_document_generation_distinct():
    metadata = {"display_period_label": "ago-25 → ago-26"}
    analysis = SimpleNamespace(
        outputs=SimpleNamespace(metadata=metadata),
        aggregate_bundle=SimpleNamespace(
            dashboard=SimpleNamespace(latest_competencia="02/2026"),
            competence_coverage_df=pd.DataFrame({"competencia": ["02/2026", "08/2026"]}),
        ),
    )
    context = build_portfolio_presentation_context(
        analysis=analysis, portfolio=SimpleNamespace(name="Nome 1T26", funds=(1, 2)),
        period=SimpleNamespace(label="10/2025 a 09/2026"),
        generated_at=datetime(2026, 10, 12, 15, 30),
    )
    assert context.name == "Nome 1T26"
    assert context.common_position == "02/2026"
    assert context.latest_observed == "08/2026"
    assert context.historical_window == "ago-25 → ago-26"
    assert context.requested_window == "10/2025 a 09/2026"
    assert context.consulted_at == "12/10/2026 15:30 BRT"
    assert metadata == {"display_period_label": "ago-25 → ago-26"}


def test_absent_reference_is_not_an_invented_month():
    context = build_portfolio_presentation_context(
        analysis=SimpleNamespace(outputs=SimpleNamespace(metadata={}), aggregate_bundle=None),
        portfolio=SimpleNamespace(name="Carteira março 2026", funds=(1,)),
        period=SimpleNamespace(label="Janela solicitada"),
    )
    assert context.common_position == context.latest_observed == "N/D"
