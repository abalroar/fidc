from __future__ import annotations

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from tabs import tab_industry_study


def _conclusions_app(payload: dict[str, object]) -> None:
    from tabs.tab_industry_study import _render_revision_conclusions

    _render_revision_conclusions(payload)


def test_five_editorial_conclusions_render_compactly_and_keep_notes_accessible() -> None:
    payload = {
        "latest_complete": "2026-08",
        "closed_offers_jan_june": [{"year": 2026, "period_end": "2026-06-30"}],
        "executive_conclusions": [
            {"order": index, "title": f"Tema {index} <CVM>", "bullets": [f"Cerca de {index}%.", "Detalhe secundário."]}
            for index in range(5, 0, -1)
        ],
        "executive_conclusion_notes": ["Contas não equivalem a investidores únicos."],
    }
    app = AppTest.from_function(_conclusions_app, args=(payload,)).run()

    assert not app.exception
    cards = app.markdown[1].value
    assert cards.count('<article class="industry-conclusion">') == 5
    assert cards.count("<p>") == 5
    assert cards.index("Tema 1") < cards.index("Tema 5")
    assert "&lt;CVM&gt;" in cards
    assert "Detalhe secundário" not in cards
    assert all("Grandes números" not in element.value for element in app.markdown)
    assert "estoque em ago/26" in app.caption[0].value
    assert "30/06/2026" in app.caption[0].value
    assert app.expander[0].label == "Fontes e limites das conclusões"
    assert not app.expander[0].proto.expanded
    assert "investidores únicos" in app.expander[0].markdown[0].value


def test_conclusion_fallback_uses_current_stock_and_preserves_zero_and_missing() -> None:
    payload = {
        "latest_complete": "2026-08",
        "pl_history": [
            {"competencia": "2026-08", "pl_ex_fic": 846_300_000_000},
            {"competencia": "2026-06", "pl_ex_fic": 999_000_000_000},
        ],
        "receivables_history": [
            {"competencia": "2026-08", "segmento": "Financeiro", "share_reported": 0.648},
            {"competencia": "2026-06", "segmento": "Financeiro", "share_reported": 0.9},
        ],
        "conclusion_metrics": {
            "competencia": "2026-08",
            "holder_ge_200m_share_fundos_ate_10_contas": 0,
        },
    }
    conclusions = tab_industry_study._revision_conclusion_items(payload)

    assert len(conclusions) == 5
    assert "R$ 850 bi" in conclusions[0][1]
    assert "65%" in conclusions[1][1]
    assert "0%" in conclusions[2][1]
    assert "N/D" in conclusions[3][1]
    assert "N/D" in conclusions[4][1]


def test_conclusion_fallback_does_not_use_metrics_from_an_older_month() -> None:
    conclusions = tab_industry_study._revision_conclusion_items({
        "latest_complete": "2026-08",
        "conclusion_metrics": {
            "competencia": "2026-06",
            "holder_ge_200m_share_fundos_ate_10_contas": 0.6,
            "admin_custodia_juntas_share_pl": 0.9,
        },
        "service_model": [{"competencia": "2026-06", "modelo_prestacao": "Monoestrutura", "share_pl": 0.9}],
    })

    assert "N/D" in conclusions[2][1]
    assert "N/D" in conclusions[3][1]


@pytest.mark.parametrize(("share", "expected"), [
    (None, "N/D"),
    (0, "0%"),
    (0.5, "50%"),
    (0.574728, "Mais da metade dos fundos de maior porte reporta até dez contas."),
    (0.6, "60%"),
])
def test_holder_conclusion_fallback_respects_the_majority_boundary(
    share: float | None, expected: str,
) -> None:
    conclusions = tab_industry_study._revision_conclusion_items({
        "latest_complete": "2026-08",
        "conclusion_metrics": {
            "competencia": "2026-08",
            "holder_ge_200m_share_fundos_ate_10_contas": share,
        },
    })
    text = conclusions[2][1]

    assert expected in text
    assert "R$ 200" not in text
    if share == 0.574728:
        assert "60%" not in text
    else:
        assert "Mais da metade" not in text


def test_conclusion_fallback_preserves_missing_for_invalid_denominators() -> None:
    conclusions = tab_industry_study._revision_conclusion_items({
        "latest_complete": "2026-08",
        "pl_history": [{"competencia": "2026-08", "pl_ex_fic": -1}],
        "receivables_history": [{"competencia": "2026-08", "segmento": "Financeiro", "share_reported": 1.2}],
        "conclusion_metrics": {
            "holder_ge_200m_share_fundos_ate_10_contas": float("inf"),
            "admin_custodia_juntas_share_pl": -0.2,
        },
    })

    assert all("N/D" in text for _, text in conclusions)


def _industry_header_app() -> None:
    from tabs.tab_industry_study import render_tab_industry_study

    render_tab_industry_study()


def test_industry_header_distinguishes_complete_stock_partial_month_and_offers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = pd.DataFrame([
        {"competencia": "2026-08", "publication_status": "completa"},
        {"competencia": "2026-09", "publication_status": "preliminar"},
    ])
    payload = {
        "latest_complete": "2026-08",
        "offers_as_of": "2026-06-30",
        "closed_offers_jan_june": [{"year": 2026, "period_end": "2026-06-30"}],
        "executive_conclusions": [
            {"order": index, "title": f"Tema {index}", "bullets": ["Conclusão curta."]}
            for index in range(1, 6)
        ],
    }
    monkeypatch.setattr(
        tab_industry_study, "_intelligence_frame",
        lambda name: status if name == "industry_competence_status.csv"
        else pd.DataFrame([{"competencia": "2026-09"}]),
    )
    monkeypatch.setattr(tab_industry_study, "_industry_revision_signature", lambda: "header-test")
    monkeypatch.setattr(tab_industry_study, "_load_industry_revision_payload", lambda *_: payload)
    for renderer in (
        "_render_revision_overview", "_render_revision_investors", "_render_revision_credit",
        "_render_revision_providers", "_render_revision_offers", "_render_carteira",
        "_render_revision_data_exports",
    ):
        monkeypatch.setattr(tab_industry_study, renderer, lambda *_: None)

    app = AppTest.from_function(_industry_header_app).run()

    assert not app.exception
    assert len(app.tabs) == 8
    assert any("Estoque: ago/26" in element.value and "ofertas: 30/06/2026" in element.value for element in app.markdown)
    assert any("set/26 é preliminar" in element.value and "usa ago/26" in element.value for element in app.caption)
    assert not app.warning


def _industry_exports_app(payload: dict[str, object]) -> None:
    import pandas as pd
    from tabs.tab_industry_study import _render_revision_data_exports

    _render_revision_data_exports(payload, pd.DataFrame(), pd.DataFrame())


def test_executive_download_name_and_bytes_use_the_current_stock_month(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from types import SimpleNamespace
    import services.industry_case_studies_export as case_exports
    import services.industry_revision_export as revision_exports

    payloads = {spec["key"]: spec["key"].encode() for spec in tab_industry_study._INDUSTRY_EXPORT_BUTTONS}
    monkeypatch.setattr(tab_industry_study, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(tab_industry_study, "taxonomy_review_ledger_digest", lambda *_: "ledger")
    monkeypatch.setattr(tab_industry_study, "_bundle_predates_issuance_correction", lambda: False)
    monkeypatch.setattr(revision_exports, "get_revision_export_status", lambda *_: SimpleNamespace(bundle_valid=True, latest_complete="2026-08"))
    monkeypatch.setattr(tab_industry_study, "_industry_export_signature", lambda: "download-test")
    monkeypatch.setattr(tab_industry_study, "_industry_export_payloads", lambda *_: (payloads, {}))
    monkeypatch.setattr(tab_industry_study, "_render_requested_revision_exports", lambda **_: None)
    monkeypatch.setattr(case_exports, "load_case_studies_prompt", lambda *_: "Método disponível.")
    downloads: dict[str, dict[str, object]] = {}
    download_button = tab_industry_study.st.download_button

    def record_download(label: str, **kwargs: object) -> object:
        downloads[label] = kwargs
        return download_button(label, **kwargs)

    monkeypatch.setattr(tab_industry_study.st, "download_button", record_download)
    payload = {
        "latest_complete": "2026-08",
        "offers_as_of": "2026-06-30",
        "offers_source_as_of": "2026-07-24",
        "taxonomy_review_meta": {"ledger_sha256": "ledger"},
        "bcb_expanded_credit": [{"competencia": "2026-08"}],
    }
    app = AppTest.from_function(_industry_exports_app, args=(payload,)).run()

    assert not app.exception
    assert downloads["PPT executivo"]["file_name"] == "Industria_FIDC_Executivo_202608.pptx"
    assert downloads["PPT executivo"]["data"] is payloads["pptx"]
    assert downloads["XLSX"]["file_name"] == "Industria_FIDC_Dados_202608.xlsx"
    assert app.get("download_button")[0].proto.label == "PPT executivo"
    source_details = next(expander for expander in app.expander if expander.label == "Escopo, fontes e limitações")
    source_dates = source_details.dataframe[0].value.set_index("Dimensão")["Data-base"]
    assert source_dates["Tipo de recebível CVM"] == "2026-08"
    assert source_dates["Crédito Privado Ampliado"] == "ago/26"
    assert source_dates["Reclassificação ANBIMA"] == "dez/25 sobre PL ago/26"
    assert source_dates["Decisões de taxonomia"] == "jun/26"


def test_revised_downloads_expose_complete_offer_sources_with_their_extraction_date(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import gzip
    from io import BytesIO
    from types import SimpleNamespace
    import services.industry_revision_export as revision_exports

    complete = gzip.compress(b"offer_id,period\n1,2026YTD\n")
    ranking = gzip.compress(b"offer_id,rank\n1,1\n")
    (tmp_path / "industry_offers.csv.gz").write_bytes(complete)
    (tmp_path / "industry_offer_rankings.csv.gz").write_bytes(ranking)
    (tmp_path / "industry_offers_annual.csv").write_text(
        "year,period,valid_registered_volume_brl\n2026,2026YTD,1234.5\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tab_industry_study, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(tab_industry_study, "taxonomy_review_ledger_digest", lambda *_: "ledger")
    monkeypatch.setattr(tab_industry_study, "_bundle_predates_issuance_correction", lambda: False)
    monkeypatch.setattr(tab_industry_study, "_render_industry_exports", lambda **_: None)
    monkeypatch.setattr(revision_exports, "get_revision_export_status", lambda *_: SimpleNamespace(bundle_valid=True, latest_complete="2026-08"))
    downloads: dict[str, dict[str, object]] = {}
    actual_button = tab_industry_study.st.download_button

    def record_download(label: str, data=None, **kwargs: object) -> object:
        downloads[label] = {"data": data, **kwargs}
        return actual_button(label, data=data, **kwargs)

    monkeypatch.setattr(tab_industry_study.st, "download_button", record_download)
    payload = {
        "latest_complete": "2026-08", "offers_as_of": "2026-06-30",
        "offers_source_as_of": "2026-10-08",
        "taxonomy_review_meta": {"ledger_sha256": "ledger"},
    }
    app = AppTest.from_function(_industry_exports_app, args=(payload,)).run()

    assert not app.exception and not app.error
    bases = next(element for element in app.expander if element.label == "Bases revisadas para download")
    assert not bases.proto.expanded
    assert set(downloads) == {
        "Ofertas CVM: base atualizada · extração 08/10/2026",
        "Ofertas CVM · totais anuais · extração 08/10/2026",
        "Ofertas CVM · ranking · extração 08/10/2026",
    }
    all_offers = downloads["Ofertas CVM: base atualizada · extração 08/10/2026"]
    ranked = downloads["Ofertas CVM · ranking · extração 08/10/2026"]
    annual = downloads["Ofertas CVM · totais anuais · extração 08/10/2026"]
    assert all_offers["data"] == complete and all_offers["file_name"] == "industry_offers.csv.gz"
    assert ranked["data"] == ranking and ranked["file_name"] == "industry_offer_rankings.csv.gz"
    assert all_offers["mime"] == ranked["mime"] == "application/gzip"
    assert annual["file_name"] == "industry_offers_annual.csv" and annual["mime"] == "text/csv"
    assert annual["data"].startswith(b"\xef\xbb\xbf")
    frame = pd.read_csv(BytesIO(annual["data"]), sep=";", decimal=",")
    assert frame.loc[0, "period"] == "2026YTD"
    assert frame.loc[0, "valid_registered_volume_brl"] == 1234.5
    sources = next(element for element in app.expander if element.label == "Escopo, fontes e limitações").dataframe[0].value.set_index("Dimensão")
    assert sources.loc["Ofertas", "Data-base"] == "2026-06-30"


@pytest.mark.parametrize("competence,label", [("2026-08", "ago/26"), ("2027-03", "mar/27")])
def test_taxonomy_downloads_use_published_current_cut_and_keep_june_archive(
    monkeypatch: pytest.MonkeyPatch, tmp_path, competence: str, label: str,
) -> None:
    from io import BytesIO
    from types import SimpleNamespace
    import services.industry_revision_export as revision_exports

    suffix = competence.replace("-", "")
    stems = ("industry_taxonomy_impact_summary", "industry_taxonomy_impact_flows",
             "industry_taxonomy_issuance_impact", "industry_taxonomy_market_share_denominator_impact")
    for stem in stems:
        (tmp_path / f"{stem}_{suffix}.csv").write_text(f"competencia,valor\n{competence},0\n")
    (tmp_path / "industry_taxonomy_impact_summary_202606.csv").write_text("competencia,valor\n2026-06,1\n")
    monkeypatch.setattr(tab_industry_study, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(tab_industry_study, "taxonomy_review_ledger_digest", lambda *_: "ledger")
    monkeypatch.setattr(tab_industry_study, "_bundle_predates_issuance_correction", lambda: False)
    monkeypatch.setattr(tab_industry_study, "_render_industry_exports", lambda **_: None)
    monkeypatch.setattr(revision_exports, "get_revision_export_status", lambda *_: SimpleNamespace(
        bundle_valid=True, latest_complete=competence))
    downloads = {}
    actual_button = tab_industry_study.st.download_button
    def capture(label, data=None, **kwargs):
        downloads[label] = {"data": data, **kwargs}
        return actual_button(label, data=data, **kwargs)
    monkeypatch.setattr(tab_industry_study.st, "download_button", capture)
    payload = {"latest_complete": competence, "taxonomy_review_meta": {"ledger_sha256": "ledger"},
               "taxonomy_impact_meta": {"current_competence": competence, "documentary_reference": "2026-06"}}
    app = AppTest.from_function(_industry_exports_app, args=(payload,)).run()
    assert not app.exception and not app.error
    current = {key: value for key, value in downloads.items() if key.startswith("Impacto corrente")}
    assert len(current) == 4
    for name, download in current.items():
        assert label in name and download["file_name"].endswith(f"_{suffix}.csv")
        assert download["mime"] == "text/csv" and download["data"].startswith(b"\xef\xbb\xbf")
        frame = pd.read_csv(BytesIO(download["data"]), sep=";", decimal=",")
        assert frame.loc[0, "competencia"] == competence and frame.loc[0, "valor"] == 0
    archive = downloads["Impacto da taxonomia jun/26 · resumo por Tipo"]
    assert archive["file_name"] == "industry_taxonomy_impact_summary_202606.csv"
    instructions = " ".join(element.value for element in app.code)
    assert "update_fidc_industry.py --check-only" in instructions
    assert "update_fidc_industry.py --apply" in instructions


def _card_breakdown_app(payload: dict[str, object]) -> None:
    from tabs.tab_industry_study import _render_revision_card_breakdown

    _render_revision_card_breakdown(payload)


def test_card_breakdown_uses_the_curation_blocks_own_stock_and_fallback_dates() -> None:
    row = {
        "ordem_materialidade": 1, "cnpj_fundo_formatado": "12.345.678/0001-00",
        "denominacao": "FIDC de teste", "pl_referencia_brl": 1_000_000,
        "pl_referencia_competencia": "2026-08", "status_curadoria": "Pendente",
        "cedente_originador": "N/D", "devedor_sacado": "N/D", "instrumento": "N/D",
        "natureza_economica": "N/D", "evidencia_curta": "N/D", "fonte_url": "",
    }
    payload = {
        "latest_complete": "2026-09",
        "card_taxonomy_audit": [row],
        "card_taxonomy_summary": {
            "competencia_pl_atual": "2026-08", "competencia_pl_fallback": "2026-07",
            "fundos_total": 1, "fundos_pl_atual_observavel": 1, "fundos_pl_fallback_usado": 0,
        },
    }
    app = AppTest.from_function(_card_breakdown_app, args=(payload,)).run()

    assert not app.exception
    cards = app.markdown[1].value
    assert "PL em ago/26" in cards
    assert "fallback jul/26" in cards
    assert "fallback mai/26" not in cards
