from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CURATION = ROOT / "data" / "industry_study" / "industry_carteira_1_document_curation.csv"


def test_documentary_coverage_and_exceptions_reconcile() -> None:
    detail = pd.read_csv(CURATION, dtype=str, keep_default_na=False)
    junior = pd.to_numeric(detail["subordinacao_minima_junior_pct"], errors="coerce")
    support = pd.to_numeric(detail["suporte_estrutural_minimo_pct"], errors="coerce")

    assert len(detail) == 101
    assert detail["cnpj_fundo"].nunique() == 101
    assert junior.notna().sum() == 83
    assert (junior.notna() | support.notna()).sum() == 99
    assert detail["subordinacao_minima_natureza"].eq("sem_indice").sum() == 1
    assert detail["subordinacao_minima_natureza"].eq("fora_perimetro").sum() == 1


def test_non_junior_or_adjusted_metrics_carry_an_asterisk() -> None:
    detail = pd.read_csv(CURATION, dtype=str, keep_default_na=False)
    exception = ~detail["subordinacao_minima_natureza"].isin(
        ["junior_pl", "sem_indice", "fora_perimetro"]
    )
    displays = detail.loc[exception, "suporte_estrutural_minimo_display"].where(
        detail.loc[exception, "suporte_estrutural_minimo_display"].ne(""),
        detail.loc[exception, "subordinacao_minima_junior_display"],
    )

    assert displays.ne("").all()
    assert displays.str.contains(r"\*", regex=True).all()


def test_every_numeric_metric_has_document_page_and_nature() -> None:
    detail = pd.read_csv(CURATION, dtype=str, keep_default_na=False)
    junior = pd.to_numeric(detail["subordinacao_minima_junior_pct"], errors="coerce")
    support = pd.to_numeric(detail["suporte_estrutural_minimo_pct"], errors="coerce")
    measured = junior.notna() | support.notna()

    assert detail.loc[measured, "documento_id_regulamento"].ne("").all()
    assert detail.loc[measured, "documento_id_regulamento"].ne("N/D").all()
    assert detail.loc[measured, "pagina_clausula"].ne("").all()
    assert detail.loc[measured, "subordinacao_minima_natureza"].ne("").all()
