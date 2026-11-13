from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest


DATA = Path(__file__).resolve().parents[1] / "data/industry_study/generated_revision/artifact_payload.json"


def app(payload):
    from tabs.industry_anbima_view import render_anbima_analysis
    render_anbima_analysis(payload)


def test_anbima_ui_keeps_fidc_and_market_top15_and_exposes_twelve_month_window():
    payload = json.loads(DATA.read_text())
    ui = AppTest.from_function(app, args=(payload,)).run(timeout=60)
    assert not ui.exception
    assert [len(frame.value) for frame in ui.dataframe] == [10, 20, 15, 15]
    assert ui.dataframe[2].value["Registro CVM"].is_unique
    assert "56,42" in " ".join(caption.value for caption in ui.caption)
    ui.selectbox(key="industry-anbima-window").select("Últimos 12 meses").run(timeout=60)
    assert not ui.exception
    positions = ui.dataframe[0].value
    fidc = positions[positions["Recorte"].eq("FIDC")].set_index("Papel")
    assert fidc.loc["Originação", "Participação"] == "41,5%"
    assert fidc.loc["Distribuição", "Participação"] == "27,8%"
    assert "2025-10-01 a 2026-09-30" in " ".join(caption.value for caption in ui.caption)


def test_missing_related_company_distribution_is_explicit():
    ui = AppTest.from_function(app, args=(json.loads(DATA.read_text()),)).run(timeout=60)
    ui.selectbox(key="industry-anbima-ranking-scope").select("Empresas ligadas").run(timeout=60)
    assert not ui.exception
    assert any("Distribuição: ranking não publicado" in info.value for info in ui.info)
