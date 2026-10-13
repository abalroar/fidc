from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pandas as pd

from services.document_curation_comparison import DocumentComparisonPage
from tabs import tab_deep_dive


def test_portfolio_documentary_export_is_deferred_and_matches_compact_page_content():
    frame = pd.DataFrame({"Critério": ["Limite"], "Fundo A": ["≤ 80%"], "Fundo B": ["≤ 80%"]})
    page = DocumentComparisonPage("Elegibilidade", frame, notes=("Leitura parcial preservada.",), sources=("CVM ID 101, p. 3",))
    manifest = SimpleNamespace(deep_dive_id="p", funds=[
        {"name": "Razão social A", "short_name": "Fundo A", "cnpj": "33254370000104"},
        {"name": "Razão social B", "short_name": "Fundo B", "cnpj": "37511828000114"},
    ])
    with (
        patch.object(tab_deep_dive, "build_document_comparison_pages", return_value=[page]),
        patch("services.deep_dive_ppt_export.build_document_comparison_pptx_bytes", return_value=b"native-pptx") as build,
        patch.object(tab_deep_dive.st, "session_state", {}),
        patch.object(tab_deep_dive.st, "expander", return_value=nullcontext()),
        patch.object(tab_deep_dive.st, "markdown") as markup,
        patch.object(tab_deep_dive.st, "caption") as captions,
        patch("services.on_demand_download.st.download_button") as download,
    ):
        tab_deep_dive._render_fund_reading(manifest, portfolio_mode=True)
        build.assert_not_called()
        rendered = "\n".join(call.args[0] for call in markup.call_args_list)
        assert "Todos os fundos" in rendered and "≤ 80%" in rendered
        assert "document-comparison--portfolio" in rendered
        assert any(call.args[0] == "Leitura parcial preservada." for call in captions.call_args_list)
        assert download.call_args.kwargs["data"]() == b"native-pptx"
    build.assert_called_once_with(manifest, [page], portfolio_mode=True, compact=True)
    assert list(frame.columns) == ["Critério", "Fundo A", "Fundo B"]


def test_standalone_documentary_table_keeps_its_original_presentation():
    frame = pd.DataFrame({"Critério": ["Taxa"], "Fundo": ["0%"]})
    original = tab_deep_dive._comparison_table_html("Título", frame, 1)
    assert "document-comparison--portfolio" not in original
    assert "background:#ff6200" in original


def test_portfolio_curation_keeps_all_fifteen_reading_caveats_in_one_audit():
    warnings = tuple(f"Lacuna RESSALVA_{index:02}: condição documental {index}." for index in range(14)) + (
        "Pacote gerado exclusivamente da cesta. Referência /Users/analista/Documentos/consulta.pdf. "
        + "Texto integral preservado. " * 40 + "FINAL_DA_RESSALVA.",
    )
    manifest = SimpleNamespace(generated_at="2026-10-07T11:08:04-03:00", warnings=warnings)
    with (
        patch.object(tab_deep_dive, "_render_fund_reading"),
        patch.object(tab_deep_dive, "build_document_comparison_pages", return_value=[]),
        patch.object(tab_deep_dive, "_render_update_prompt"),
        patch.object(tab_deep_dive.st, "expander", return_value=nullcontext()) as expander,
        patch.object(tab_deep_dive.st, "markdown") as markup,
        patch.object(tab_deep_dive.st, "caption"),
    ):
        tab_deep_dive._render_document_curation(manifest, portfolio_mode=True)
    expander.assert_has_calls([
        call("Auditoria documental", expanded=False),
        call("Ferramentas documentais", expanded=False),
    ])
    assert expander.call_count == 2
    all_caveats = markup.call_args_list[-1].args[0]
    assert all(f"RESSALVA_{index:02}" in all_caveats for index in range(14))
    assert "Pacote gerado exclusivamente da cesta." in all_caveats
    assert "FINAL_DA_RESSALVA." in all_caveats
    assert "consulta.pdf" in all_caveats
    assert "/Users/analista" not in all_caveats
    assert len([line for line in all_caveats.splitlines() if line.startswith("- ")]) == 15
    assert manifest.warnings == warnings


def test_standalone_curation_keeps_original_two_point_limit_without_new_expander():
    warnings = tuple(f"Lacuna RESSALVA_{index:02}: condição documental." for index in range(5))
    manifest = SimpleNamespace(generated_at="2026-10-07T11:08:04-03:00", warnings=warnings)
    with (
        patch.object(tab_deep_dive, "_render_fund_reading"),
        patch.object(tab_deep_dive.st, "expander") as expander,
        patch.object(tab_deep_dive.st, "markdown") as markup,
        patch.object(tab_deep_dive.st, "caption"),
    ):
        tab_deep_dive._render_document_curation(manifest)
    expander.assert_not_called()
    highlights = markup.call_args_list[-1].args[0]
    assert "RESSALVA_00" in highlights and "RESSALVA_01" in highlights
    assert "RESSALVA_02" not in highlights
