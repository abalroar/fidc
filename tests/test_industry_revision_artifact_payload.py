from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.build_fidc_revision_artifact_payload import (
    _apply_manual_enrichment_to_rankings,
    _apply_detected_fic_history,
    _load_manual_cnpj_enrichment,
    _portfolio_type_mix_history,
    _type_mix_history,
)


ROOT = Path(__file__).resolve().parents[1]


def test_emission_field_audit_uses_current_slide_range_and_document_sources() -> None:
    audit = pd.read_csv(
        ROOT / "data/industry_study/emission_field_audit.csv",
        dtype=str,
        keep_default_na=False,
    )

    assert audit["bloco"].value_counts().to_dict() == {
        "slides 10–17": 120,
        "slides 21–22": 60,
    }
    source_columns = [
        "fonte_originador_cedente",
        "fonte_subordinacao",
        "fonte_preco",
        "fonte_sacado",
    ]
    assert not audit[source_columns].apply(
        lambda column: column.str.contains("abrirGerenciador", regex=False)
    ).any(axis=None)


def test_exact_cnpj_manual_join_loses_no_legacy_correspondence() -> None:
    audit = pd.read_csv(
        ROOT / "data/industry_study/emission_field_audit.csv",
        dtype=str,
        keep_default_na=False,
    )
    manual = _load_manual_cnpj_enrichment(
        ROOT / "data/industry_study/industry_cnpj_manual_enrichment.csv"
    )
    confirmed = manual[manual["status_confirmado"]]
    legacy_match = audit["cnpj"].str[:8].isin(confirmed["raiz_cnpj_foto"])
    exact_match = audit["cnpj"].isin(confirmed["cnpj"])
    lost = audit.loc[legacy_match & ~exact_match, ["cnpj", "fundo"]]

    assert lost.empty, lost.to_dict(orient="records")


def test_manual_photo_loader_accepts_confirmed_status_with_underscore(tmp_path) -> None:
    path = tmp_path / "manual.csv"
    pd.DataFrame(
        [
            {
                "raiz_cnpj_foto": "12345678",
                "cnpj": "12.345.678/0001-90",
                "cedente_originador_literal": "Grupo",
                "papel_literal": "cedente",
                "originador": "",
                "cedente": "Grupo",
                "sacado_devedor": "",
                "tipo_recebivel_literal": "Recebível",
                "fonte_imagem": "IMG.JPG",
                "localizacao_imagem": "linha 1",
                "status_transcricao": "confirmado_legivel",
            },
            {
                "raiz_cnpj_foto": "87654321",
                "cnpj": "87.654.321/0001-09",
                "cedente_originador_literal": "Revisar",
                "papel_literal": "N/D",
                "originador": "",
                "cedente": "",
                "sacado_devedor": "",
                "tipo_recebivel_literal": "",
                "fonte_imagem": "IMG2.JPG",
                "localizacao_imagem": "linha 2",
                "status_transcricao": "revisao",
            },
        ]
    ).to_csv(path, index=False)

    loaded = _load_manual_cnpj_enrichment(path)

    assert loaded["status_confirmado"].tolist() == [True, False]


def test_manual_photo_enrichment_only_fills_gaps_and_marks_asterisk() -> None:
    ranking = pd.DataFrame(
        [
            {
                "cnpj_fundo": "12345678000190",
                "cedente_originador": "N/D",
                "cedente_status": "N/D",
                "evidencia_cedente": "N/D",
                "limitacao_cedente": "N/D",
            },
            {
                "cnpj_fundo": "87654321000109",
                "cedente_originador": "Documental",
                "cedente_status": "documental",
                "evidencia_cedente": "regulamento",
                "limitacao_cedente": "N/D",
            },
        ]
    )
    audit = pd.DataFrame(
        [
            {
                "cnpj": "12345678000190",
                "originador": "N/D",
                "cedente": "N/D",
                "sacado": "N/D",
                "fonte_originador_cedente": "N/D",
                "fonte_sacado": "N/D",
                "status": "N/D",
            },
            {
                "cnpj": "87654321000109",
                "originador": "Originador documental",
                "cedente": "Cedente documental",
                "sacado": "Sacado documental",
                "fonte_originador_cedente": "regulamento",
                "fonte_sacado": "regulamento",
                "status": "documental",
            },
        ]
    )
    manual = pd.DataFrame(
        [
            {
                "raiz_cnpj_foto": "12345678",
                "cnpj": "12345678000190",
                "cedente_originador_literal": "Grupo manual",
                "originador": "Originador manual",
                "cedente": "Cedente manual",
                "sacado_devedor": "Sacado manual",
                "tipo_recebivel_literal": "Recebível manual",
                "fonte_imagem": "IMG_0001.JPG",
                "localizacao_imagem": "linha 1",
                "status_confirmado": True,
            },
            {
                "raiz_cnpj_foto": "87654321",
                "cnpj": "87654321000109",
                "cedente_originador_literal": "Não deve substituir",
                "originador": "Não deve substituir",
                "cedente": "Não deve substituir",
                "sacado_devedor": "Não deve substituir",
                "tipo_recebivel_literal": "Recebível manual",
                "fonte_imagem": "IMG_0002.JPG",
                "localizacao_imagem": "linha 2",
                "status_confirmado": True,
            },
        ]
    )

    enriched_ranking, enriched_audit = _apply_manual_enrichment_to_rankings(
        ranking, audit, manual
    )

    assert enriched_ranking.loc[0, "cedente_originador"] == "Grupo manual*"
    assert enriched_ranking.loc[1, "cedente_originador"] == "Documental"
    assert enriched_audit.loc[0, "originador"] == "Originador manual*"
    assert enriched_audit.loc[0, "cedente"] == "Cedente manual*"
    assert enriched_audit.loc[0, "sacado"] == "Sacado manual*"
    assert enriched_audit.loc[1, "originador"] == "Originador documental"
    assert enriched_audit.loc[1, "cedente"] == "Cedente documental"
    assert enriched_audit.loc[1, "sacado"] == "Sacado documental"
    assert "IMG_0001.JPG" in enriched_audit.loc[0, "fonte_enriquecimento_manual"]


def test_manual_photo_enrichment_does_not_cross_exact_cnpj_siblings() -> None:
    ranking = pd.DataFrame(
        [
            {
                "cnpj_fundo": "12345678000190",
                "cedente_originador": "N/D",
                "cedente_status": "N/D",
                "evidencia_cedente": "N/D",
                "limitacao_cedente": "N/D",
            },
            {
                "cnpj_fundo": "12345678000270",
                "cedente_originador": "N/D",
                "cedente_status": "N/D",
                "evidencia_cedente": "N/D",
                "limitacao_cedente": "N/D",
            },
        ]
    )
    audit = pd.DataFrame(
        [
            {
                "cnpj": "12345678000190",
                "originador": "N/D",
                "cedente": "N/D",
                "sacado": "N/D",
                "fonte_originador_cedente": "N/D",
                "fonte_sacado": "N/D",
                "status": "N/D",
            },
            {
                "cnpj": "12345678000270",
                "originador": "N/D",
                "cedente": "N/D",
                "sacado": "N/D",
                "fonte_originador_cedente": "N/D",
                "fonte_sacado": "N/D",
                "status": "N/D",
            },
        ]
    )
    manual = pd.DataFrame(
        [
            {
                "raiz_cnpj_foto": "12345678",
                "cnpj": "12345678000190",
                "cedente_originador_literal": "Grupo manual",
                "originador": "Originador manual",
                "cedente": "Cedente manual",
                "sacado_devedor": "Sacado manual",
                "tipo_recebivel_literal": "Recebível manual",
                "fonte_imagem": "IMG_0001.JPG",
                "localizacao_imagem": "linha 1",
                "status_confirmado": True,
            }
        ]
    )

    enriched_ranking, enriched_audit = _apply_manual_enrichment_to_rankings(
        ranking, audit, manual
    )

    assert enriched_ranking["cedente_originador"].tolist() == [
        "Grupo manual*",
        "N/D",
    ]
    assert enriched_audit["originador"].tolist() == [
        "Originador manual*",
        "N/D",
    ]


def test_manual_photo_loader_rejects_invalid_exact_cnpj(tmp_path) -> None:
    path = tmp_path / "manual.csv"
    pd.DataFrame(
        [
            {
                "raiz_cnpj_foto": "12345678",
                "cnpj": "12345678",
                "cedente_originador_literal": "Grupo",
                "papel_literal": "cedente",
                "originador": "",
                "cedente": "Grupo",
                "sacado_devedor": "",
                "tipo_recebivel_literal": "Recebível",
                "fonte_imagem": "IMG.JPG",
                "localizacao_imagem": "linha 1",
                "status_transcricao": "confirmado_legivel",
            }
        ]
    ).to_csv(path, index=False)

    with pytest.raises(ValueError, match="CNPJ inválido"):
        _load_manual_cnpj_enrichment(path)


def test_manual_photo_loader_rejects_exact_cnpj_from_another_root(tmp_path) -> None:
    path = tmp_path / "manual.csv"
    pd.DataFrame(
        [
            {
                "raiz_cnpj_foto": "12345678",
                "cnpj": "87654321000109",
                "cedente_originador_literal": "Grupo",
                "papel_literal": "cedente",
                "originador": "",
                "cedente": "Grupo",
                "sacado_devedor": "",
                "tipo_recebivel_literal": "Recebível",
                "fonte_imagem": "IMG.JPG",
                "localizacao_imagem": "linha 1",
                "status_transcricao": "confirmado_legivel",
            }
        ]
    ).to_csv(path, index=False)

    with pytest.raises(ValueError, match="divergente da raiz"):
        _load_manual_cnpj_enrichment(path)


def test_manual_photo_loader_accepts_siblings_from_the_same_root(tmp_path) -> None:
    path = tmp_path / "manual.csv"
    base = {
        "raiz_cnpj_foto": "12345678",
        "cedente_originador_literal": "Grupo",
        "papel_literal": "cedente",
        "originador": "",
        "cedente": "Grupo",
        "sacado_devedor": "",
        "tipo_recebivel_literal": "Recebível",
        "fonte_imagem": "IMG.JPG",
        "status_transcricao": "confirmado_legivel",
    }
    pd.DataFrame(
        [
            {**base, "cnpj": "12345678000190", "localizacao_imagem": "linha 1"},
            {**base, "cnpj": "12345678000270", "localizacao_imagem": "linha 2"},
        ]
    ).to_csv(path, index=False)

    loaded = _load_manual_cnpj_enrichment(path)

    assert loaded["cnpj"].tolist() == ["12345678000190", "12345678000270"]


def test_detected_fic_history_replaces_the_legacy_component() -> None:
    annual = pd.DataFrame(
        [
            {"year": 2025, "competencia": "2025-12", "pl_total": 200.0, "pl_fic_fidc": 10.0},
            {"year": 2026, "competencia": "2026-06", "pl_total": 300.0, "pl_fic_fidc": 20.0},
        ]
    )
    audit = pd.DataFrame(
        [
            {"competencia": "2025-12", "cnpj_fundo": "1", "is_fic": True, "pl": 30.0},
            {"competencia": "2026-06", "cnpj_fundo": "1", "is_fic": True, "pl": 40.0},
            {"competencia": "2026-06", "cnpj_fundo": "2", "is_fic": True, "pl": 10.0},
            {"competencia": "2026-06", "cnpj_fundo": "3", "is_fic": False, "pl": 99.0},
        ]
    )

    output = _apply_detected_fic_history(annual, audit)

    assert output["pl_fic_fidc"].tolist() == pytest.approx([30.0, 50.0])
    assert output["pl_ex_fic"].tolist() == pytest.approx([170.0, 250.0])
    assert output["fundos_fic_detectados"].tolist() == [1, 2]


def test_type_mix_builds_four_periods_and_incorporates_nd_into_outros() -> None:
    rows: list[dict[str, object]] = []
    periods = ("2023-12", "2024-12", "2025-12", "2026-06")
    for index, competencia in enumerate(periods, start=1):
        for category, pl in (
            ("Fomento Mercantil", 10.0 * index),
            ("Agro, Indústria e Comércio", 20.0 * index),
            ("Financeiro", 30.0 * index),
            ("Outros", 35.0 * index),
            ("N/D", 5.0 * index),
        ):
            rows.append(
                {
                    "competencia": competencia,
                    "is_fic_fidc": False,
                    "anbima_tipo": category,
                    "classification_tier": (
                        "nao_disponivel" if category == "N/D" else "oficial_anbima"
                    ),
                    "pl": pl,
                }
            )
        rows.append(
            {
                "competencia": competencia,
                "is_fic_fidc": True,
                "anbima_tipo": "Outros",
                "classification_tier": "oficial_anbima",
                "pl": 1_000.0,
            }
        )

    mix, coverage, meta = _type_mix_history(pd.DataFrame(rows), list(periods))

    assert len(mix) == 16
    assert mix["competencia"].drop_duplicates().tolist() == list(periods)
    assert set(mix["anbima_tipo"]) == {
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    }
    assert "N/D" not in set(mix["anbima_tipo"])
    assert (
        mix.groupby("competencia")["share"].sum().tolist()
        == pytest.approx([1.0, 1.0, 1.0, 1.0])
    )
    latest_outros = mix[
        mix["competencia"].eq("2026-06") & mix["anbima_tipo"].eq("Outros")
    ].iloc[0]
    assert latest_outros["pl"] == pytest.approx((35.0 + 5.0) * 4)
    assert meta["nd_incorporated_into"] == "Outros"
    assert [row["label"] for row in meta["periods"]] == [
        "dez/23",
        "dez/24",
        "dez/25",
        "jun/26",
    ]
    assert set(coverage["categoria"]) == {"Oficial ANBIMA", "N/D"}


def test_portfolio_type_mix_history_reconciles_scope_and_market() -> None:
    periods = ["2023-12", "2024-12", "2025-12", "2026-06"]
    funds = pd.DataFrame(
        [
            {
                "competencia": period,
                "cnpj_fundo": cnpj,
                "is_fic_fidc": False,
                "anbima_tipo": category,
                "anbima_foco": "N/D",
                "pl": pl * (period_index + 1),
            }
            for period_index, period in enumerate(periods)
            for cnpj, category, pl in (
                ("00000001000100", "Fomento Mercantil", 10.0),
                ("00000002000100", "Financeiro", 20.0),
                ("00000003000100", "N/D", 5.0),
            )
        ]
    )
    scope = pd.DataFrame(
        [
            {"cnpj_fundo": "00000001000100"},
            {"cnpj_fundo": "00000002000100"},
            {"cnpj_fundo": "00000003000100"},
            {"cnpj_fundo": "00000004000100"},
        ]
    )
    market = pd.DataFrame(
        [
            {
                "competencia": period,
                "anbima_tipo": category,
                "pl": 100.0 * (period_index + 1),
                "share": 0.25,
            }
            for period_index, period in enumerate(periods)
            for category in (
                "Fomento Mercantil",
                "Agro, Indústria e Comércio",
                "Financeiro",
                "Outros",
            )
        ]
    )

    history, summary = _portfolio_type_mix_history(
        funds,
        actions=pd.DataFrame(),
        scope=scope,
        periods=periods,
        market_history=market,
    )

    assert len(history) == 16
    assert history.groupby("competencia")["portfolio_share"].sum().tolist() == pytest.approx([1.0] * 4)
    assert history.groupby("competencia")["market_share"].sum().tolist() == pytest.approx([1.0] * 4)
    assert set(history["anbima_tipo"]) == {
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    }
    assert history.loc[history["anbima_tipo"].eq("Outros"), "portfolio_pl_brl"].tolist() == pytest.approx(
        [5.0, 10.0, 15.0, 20.0]
    )
    assert history.loc[history["anbima_tipo"].eq("Agro, Indústria e Comércio"), "portfolio_pl_brl"].eq(0).all()
    assert summary["scope_cnpjs"] == 4
    assert summary["latest_observed_cnpjs"] == 3
    assert summary["latest_total_brl"] == pytest.approx(140.0)
    assert "ausente" in summary["methodology"].casefold()
