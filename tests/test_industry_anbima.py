from __future__ import annotations

import pandas as pd
import pytest

from services.industry_anbima import (
    build_public_anbima_fidc_mapping,
    normalize_anbima_focus,
    normalize_anbima_type,
    valid_type_focus_pair,
)


def _row(**updates: object) -> dict[str, object]:
    base = {
        "Código ANBIMA": "C1",
        "Estrutura": "Classe",
        "Nome Comercial": "FIDC Teste",
        "CNPJ da Classe": "12.345.678/0001-90",
        "CNPJ do Fundo": "12.345.678/0001-90",
        "Status": "Ativo",
        "Data de Início de Atividade": "2025-01-01",
        "Quantidade de Subclasses": 0,
        "Categoria ANBIMA": "FIDC",
        "Tipo ANBIMA": "Outros",
        "Composição do Fundo": "CI",
        "Aberto Estatutariamente": "Fechado",
        "Fundo ESG": "Não",
        "Tributação Alvo": "Longo Prazo",
        "Administrador": "Administrador",
        "Gestor Principal": "Gestor",
        "Primeiro Aporte": "2025-01-01",
        "Tipo de Investidor": "Profissional",
        "Característica do Investidor": "Profissional",
        "Cota de Abertura": "Fechamento",
        "Aplicação Inicial Mínima": 0,
        "Prazo Pagamento Resgate em dias": None,
        "Adptado 175": "S",
        "Código CVM Subclasse": None,
        "foco_atuacao": "Multicarteira outros",
        "nivel_1_categoria": "FIDC",
        "nivel_2_categoria": "ND",
        "nivel_3_subcategoria": "ND",
    }
    return {**base, **updates}


def test_normalizers_keep_only_the_official_fidc_taxonomy() -> None:
    assert normalize_anbima_type("AGRO, INDUSTRIA E COMERCIO") == "Agro, Indústria e Comércio"
    assert normalize_anbima_focus("Multicarteiras outros") == "Multicarteira Outros"
    assert normalize_anbima_type("Multimercados Livre") == ""
    assert valid_type_focus_pair("Financeiro", "Crédito Consignado")
    assert not valid_type_focus_pair("Financeiro", "Poder Público")


def test_public_mapping_prefers_active_records_and_collapses_duplicates() -> None:
    workbook = pd.DataFrame(
        [
            _row(Status="Encerrado", **{"Código ANBIMA": "OLD", "Tipo ANBIMA": "Financeiro", "foco_atuacao": "Crédito Pessoal"}),
            _row(**{"Código ANBIMA": "ACTIVE-A"}),
            _row(**{"Código ANBIMA": "ACTIVE-B"}),
        ]
    )

    output = build_public_anbima_fidc_mapping(workbook)

    assert len(output) == 1
    assert output.iloc[0]["tipo_anbima"] == "Outros"
    assert output.iloc[0]["foco_anbima"] == "Multicarteira Outros"
    assert output.iloc[0]["mapping_status"] == "publicada"
    assert output.iloc[0]["active_record_count"] == 2
    assert output.iloc[0]["record_count"] == 3


def test_public_mapping_never_resolves_equal_priority_conflicts_silently() -> None:
    workbook = pd.DataFrame(
        [
            _row(**{"Código ANBIMA": "A", "Tipo ANBIMA": "Financeiro", "foco_atuacao": "Crédito Pessoal"}),
            _row(**{"Código ANBIMA": "B", "Tipo ANBIMA": "Outros", "foco_atuacao": "Poder Público"}),
        ]
    )

    output = build_public_anbima_fidc_mapping(workbook)

    assert output.iloc[0]["mapping_status"] == "conflito_tipo"
    assert output.iloc[0]["tipo_anbima"] == ""
    assert output.iloc[0]["foco_anbima"] == ""


def test_public_mapping_rejects_missing_source_columns() -> None:
    with pytest.raises(ValueError, match="colunas obrigatórias"):
        build_public_anbima_fidc_mapping(pd.DataFrame({"Categoria ANBIMA": ["FIDC"]}))
