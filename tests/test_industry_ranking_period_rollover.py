import pandas as pd

from services.industry_intelligence import build_stock_ranking_deltas
from services.industry_revision_analysis import annual_comparison_competences


def test_provider_history_rolls_prior_december_dates() -> None:
    assert annual_comparison_competences("2026-08", previous_years=2) == (
        "2024-12", "2025-12", "2026-08"
    )
    assert annual_comparison_competences("2027-03", previous_years=2) == (
        "2025-12", "2026-12", "2027-03"
    )


def test_stock_ranking_deltas_roll_labels_and_values_with_source_dates() -> None:
    panel = pd.DataFrame({
        "competencia": ["2024-12", "2025-12", "2026-12", "2027-03"],
        "cnpj_fundo": ["12345678000190"] * 4,
        "pl": [10.0, 20.0, 30.0, 40.0],
        "segmento_principal": ["Financeiro"] * 4,
        "admin_nome": ["Itaú"] * 4,
        "gestor_nome": ["Itaú"] * 4,
        "custodiante_nome": ["Itaú"] * 4,
    })
    output = build_stock_ranking_deltas(panel, latest_competence="2027-03")
    assert set(output["period"]) == {"2025", "2026", "2027YTD"}
    assert set(output["competencia"]) == {"2025-12", "2026-12", "2027-03"}
    observed = output[output.role.eq("administrador") & output.segment.eq("Todos") & output.metric.eq("PL")]
    assert observed.value.tolist() == [20.0, 30.0, 40.0]
    assert observed.value_change_vs_prior.iloc[1:].tolist() == [10.0, 10.0]
