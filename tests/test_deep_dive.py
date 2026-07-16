from __future__ import annotations

from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

import pandas as pd

from services.deep_dive_ppt_export import build_deep_dive_pptx_bytes
from services.deep_dive_store import deep_dive_matches_portfolio, list_deep_dives, load_deep_dive_table
from tabs import tab_deep_dive


def _write_package(root: Path) -> Path:
    package = root / "sample"
    (package / "tables").mkdir(parents=True)
    (package / "tables" / "comparison.csv").write_text(
        'Nome,FIDC A,FIDC B\nPL,R$ 100 mm,R$ 200 mm\nNPL Over 90,"1,0%","2,0%"\n',
        encoding="utf-8",
    )
    (package / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "deep_dive_id": "sample",
                "title": "Deep Dive Teste",
                "subtitle": "Comparativo",
                "generated_at": "2026-05-13T10:00:00-03:00",
                "source": "teste",
                "funds": [{"cnpj": "00.000.000/0001-00", "name": "FIDC A", "short_name": "FIDC A"}],
                "tables": [
                    {
                        "id": "comparison",
                        "title": "Comparativo",
                        "source_file": "tables/comparison.csv",
                        "first_column": "Nome",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return package


def test_deep_dive_store_loads_manifest_and_table(tmp_path: Path) -> None:
    _write_package(tmp_path)
    manifests = list_deep_dives(tmp_path)
    assert len(manifests) == 1
    assert manifests[0].title == "Deep Dive Teste"

    frame = load_deep_dive_table(manifests[0], manifests[0].tables[0])
    assert list(frame.columns) == ["Nome", "FIDC A", "FIDC B"]
    assert frame.iloc[0]["FIDC A"] == "R$ 100 mm"


def test_deep_dive_pptx_is_editable_office_package(tmp_path: Path) -> None:
    _write_package(tmp_path)
    manifest = list_deep_dives(tmp_path)[0]
    frame = pd.DataFrame({"Nome": ["PL", "NPL"], "FIDC A": ["R$ 100 mm", "1,0%"], "FIDC B": ["R$ 200 mm", "2,0%"]})
    pptx = build_deep_dive_pptx_bytes(manifest, [(manifest.tables[0], frame)], highlighted_column="FIDC B")

    assert pptx.startswith(b"PK")
    path = tmp_path / "out.pptx"
    path.write_bytes(pptx)
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        assert "ppt/presentation.xml" in names
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        assert "Deep Dive Teste" in slide_xml
        assert "R$ 100 mm" in slide_xml


def test_deep_dive_pptx_preserves_long_schedule_text(tmp_path: Path) -> None:
    _write_package(tmp_path)
    manifest = list_deep_dives(tmp_path)[0]
    schedule = (
        "15/12/2027: 16,67%; 15/01/2028: 20,00%; 15/02/2028: 25,00%; "
        "15/03/2028: 33,33%; 15/04/2028: 50,00%; 15/05/2028: 100,00%"
    )
    frame = pd.DataFrame(
        {
            "Nome": ["Cronograma de amortização mais recente"],
            "FIDC A": [schedule],
            "FIDC B": ["—"],
        }
    )

    pptx = build_deep_dive_pptx_bytes(manifest, [(manifest.tables[0], frame)])

    path = tmp_path / "long_schedule.pptx"
    path.write_bytes(pptx)
    with ZipFile(path) as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        assert "15/05/2028: 100,00%" in slide_xml
        assert "15/05/2..." not in slide_xml


def test_curadoria_emissions_summary_aggregates_only_identified_values() -> None:
    frame = pd.DataFrame(
        {
            "Tipo": ["Sênior", "Sênior", "Mezanino"],
            "Qtd cotas": ["80.000", "não informada", "100.000"],
            "Volume identificado (R$ mm)": ["80,0", "1.300,0", "—"],
            "Remuneração-alvo": ["DI + 3,50% a.a.", "DI + 2,50% a.a.", "DI + 5,25% a.a."],
            "Amortização/vencimento": ["jan/27", "out/31", "jun/29"],
        }
    )

    summary = tab_deep_dive._build_emissions_type_summary(frame)

    senior = summary.loc[summary["Tipo de cota"] == "Sênior"].iloc[0]
    mezz = summary.loc[summary["Tipo de cota"] == "Mezanino"].iloc[0]
    assert senior["Emissões"] == 2
    assert senior["Volume identificado"] == "R$ 1.380,0 mm"
    assert senior["Qtd cotas identificada"] == "80.000"
    assert "DI + 3,50% a.a." in senior["Custo / remuneração"]
    assert mezz["Volume identificado"] == "N/D"
    assert mezz["Qtd cotas identificada"] == "100.000"


def test_curadoria_formats_repository_reading_date() -> None:
    assert tab_deep_dive._format_reading_date("2026-05-14T11:46:27-03:00") == "14/05/2026"
    assert tab_deep_dive._format_reading_date("") == "data não informada"


def test_curadoria_discards_technical_placeholders_and_duplicate_limits() -> None:
    assert tab_deep_dive._clean_document_fact("texto; >=; Regra textual: verificar observação") == ""
    assert tab_deep_dive._clean_document_fact("texto 20%") == ""
    assert tab_deep_dive._clean_document_fact(">= 67%; 67%") == ">= 67%"
    assert tab_deep_dive._clean_document_fact("0%; 0") == ""


def test_curadoria_filters_cross_theme_clauses_and_contradictory_minimums() -> None:
    seller_value = (
        "Direitos Creditórios Elegíveis / PL >= 67%; "
        "Direitos Creditórios Elegíveis / PL >= 50% após 180 dias; "
        "Default de qualquer Direito Creditório por >5 dias pode ser evento de liquidação"
    )

    allocation = tab_deep_dive._clean_comparison_fact(seller_value, theme="Alocação mínima")

    assert "Direitos Creditórios Elegíveis / PL >= 67%" in allocation
    assert "Direitos Creditórios Elegíveis / PL >= 50% após 180 dias" in allocation
    assert "Default" not in allocation
    assert tab_deep_dive._clean_comparison_fact("<= 50%", theme="Alocação mínima") == ""


def test_curadoria_preserves_threshold_operator_and_rejects_implausible_concentration() -> None:
    concentration = pd.DataFrame(
        [
            {
                "Critério": "Limite de concentração",
                "Comparação": "<=",
                "Limite": "20%",
            }
        ]
    )
    implausible = pd.DataFrame(
        [
            {
                "Critério": "Limite de concentração",
                "Comparação": ">=",
                "Limite": "240%",
            }
        ]
    )
    no_effective_limit = pd.DataFrame(
        [
            {
                "Critério": "Limite de concentração",
                "Comparação": "<=",
                "Limite": "100%",
            }
        ]
    )

    assert tab_deep_dive._best_threshold_fact(
        concentration,
        ("limite de concentracao",),
        theme="Concentração",
    ) == "<= 20%"
    assert tab_deep_dive._best_threshold_fact(
        implausible,
        ("limite de concentracao",),
        theme="Concentração",
    ) == ""
    assert tab_deep_dive._best_threshold_fact(
        no_effective_limit,
        ("limite de concentracao",),
        theme="Concentração",
    ) == ""


def test_curadoria_threshold_trigger_keeps_its_context() -> None:
    frame = pd.DataFrame(
        [
            {
                "Critério": "Índice de atraso Over 30 - evento de avaliação",
                "Evento": "avaliação",
                "Comparação": ">=",
                "Limite": "25%",
            }
        ]
    )

    fact = tab_deep_dive._best_threshold_fact(frame, ("atraso",), theme="Gatilhos")

    assert fact == "Índice de atraso Over 30 - evento de avaliação: >= 25%"


def test_curadoria_keeps_only_material_manifest_warnings() -> None:
    manifest = SimpleNamespace(
        warnings=(
            "Tabela principal com 38 linhas.",
            "Custos estruturais incluídos.",
            "O regulamento consolidado não estava acessível na data da leitura.",
        )
    )

    assert tab_deep_dive._useful_manifest_warnings(manifest) == (
        "O regulamento consolidado não estava acessível na data da leitura.",
    )


def test_curadoria_always_exposes_the_refresh_prompt() -> None:
    with (
        patch("tabs.tab_deep_dive.st.expander", return_value=nullcontext()) as expander,
        patch("tabs.tab_deep_dive.st.code") as code,
        patch("tabs.tab_deep_dive._load_reverse_engineering_prompt", return_value="PROMPT ATUAL"),
    ):
        tab_deep_dive._render_update_prompt()

    expander.assert_called_once_with("Prompt usado para atualizar este artefato", expanded=False)
    code.assert_called_once_with("PROMPT ATUAL", language="markdown")


def test_curadoria_source_has_no_legacy_waterfall_or_black_table() -> None:
    source = (Path(__file__).parents[1] / "tabs" / "tab_deep_dive.py").read_text(encoding="utf-8")

    assert "Waterfall Cloudwalk" not in source
    assert "deepdive-table" not in source
    assert "st.dataframe" not in source


def test_curadoria_uses_human_source_copy_and_repository_prompt_path() -> None:
    bullets = tab_deep_dive._curation_base_bullets(SimpleNamespace(source="IME cache"))

    assert bullets[0] == "**Fonte:** documentos públicos disponibilizados pela CVM e pelo Fundos.NET."
    assert all("IME cache" not in bullet for bullet in bullets)
    assert tab_deep_dive._REVERSE_ENGINEERING_PROMPT_PATH.is_file()


def test_deep_dive_portfolio_matching_prefers_current_basket_signature() -> None:
    current = SimpleNamespace(portfolio_id="carteira-1", portfolio_signature="assinatura-antiga")
    legacy = SimpleNamespace(portfolio_id="carteira-1", portfolio_signature="")

    assert not deep_dive_matches_portfolio(current, "carteira-1", "assinatura-nova")
    assert deep_dive_matches_portfolio(current, "outra-carteira", "assinatura-antiga")
    assert deep_dive_matches_portfolio(legacy, "carteira-1", "assinatura-nova")
