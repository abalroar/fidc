from __future__ import annotations

import gzip
import hashlib

import pandas as pd

from scripts.build_fidc_revision_artifact_payload import (
    _merge_documentary_review_layers,
)
from scripts.build_fidc_top20_taxonomy_document_review import (
    OUTPUT_COLUMNS,
    build_top20_universe,
    classify_regulation_pages,
)
from scripts.build_fidc_top20_taxonomy_document_conclusions import (
    BANK_ISSUER_CNPJS,
    CURATED_CLASSIFICATION_OVERRIDES,
    DOCUMENTARY_OVERRIDES,
    _apply_documentary_overrides,
    _digest,
    _family_evidence,
    _select_family,
)


def _base() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    periods = ("2023-12", "2024-12", "2025-12", "2026-06")
    categories = (
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    )
    for period_index, period in enumerate(periods):
        for category_index, category in enumerate(categories):
            for rank in range(1, 23):
                rows.append(
                    {
                        "competencia": period,
                        "cnpj_fundo": str(
                            period_index * 10_000
                            + category_index * 100
                            + rank
                        ),
                        "denominacao": f"FIDC {period} {category} {rank}",
                        "pl": float(1_000_000 - rank),
                        "is_fic_fidc": False,
                        "anbima_tipo": category,
                    }
                )
    return pd.DataFrame(rows)


def test_build_top20_universe_returns_20_per_category_and_period() -> None:
    periods = ("2023-12", "2024-12", "2025-12", "2026-06")

    result = build_top20_universe(_base(), periods)

    assert len(result) == 320
    assert set(result.groupby(["competencia", "tipo_exibicao"]).size()) == {20}
    assert result["rank_tipo"].max() == 20


def test_specific_acquiring_evidence_dominates_generic_commercial_language() -> None:
    pages = [
        "A Classe adquire direitos creditórios decorrentes de transações de pagamento "
        "operacionalizadas por credenciadora. Os estabelecimentos realizam prestação "
        "de serviços e os direitos creditórios são cedidos ao Fundo."
    ]

    result = classify_regulation_pages(pages)

    assert result["status"] == "potencial_reclassificacao"
    assert result["n2"] == "Arranjos de pagamento/adquirência"
    assert result["tipo"] == "Agro, Indústria e Comércio"


def test_multiple_distinct_receivable_families_remain_ambiguous() -> None:
    pages = [
        "A política admite cédulas de crédito bancário, créditos inadimplidos e "
        "precatórios originários de ações judiciais."
    ]

    result = classify_regulation_pages(pages)

    assert result["status"] == "ambigua"
    assert result["tipo"] == ""
    assert "mais de uma família" in result["reason"]


def test_conclusion_uses_specific_policy_clause_and_marks_acquiring() -> None:
    pages = [
        "POLÍTICA DE INVESTIMENTO. Os direitos creditórios decorrem de transações "
        "de pagamento realizadas em arranjo de pagamento e liquidadas por "
        "credenciadora aos estabelecimentos comerciais."
    ]
    row = pd.Series(
        {
            "anbima_tipo_oficial": "Outros",
            "anbima_foco_oficial": "Multicarteira Outros",
        }
    )

    candidates = _family_evidence(pages)
    selected, mixed = _select_family(candidates, row)

    assert selected is not None
    assert selected["family"].key == "adquirencia"
    assert selected["family"].tabela_ii == "Adquirência"
    assert mixed is False


def test_conclusion_resolves_generic_commercial_language_to_fomento_official() -> None:
    pages = [
        "POLÍTICA DE INVESTIMENTO. Os direitos creditórios são representados por "
        "duplicatas decorrentes de vendas mercantis e prestação de serviços."
    ]
    row = pd.Series(
        {
            "anbima_tipo_oficial": "Fomento Mercantil",
            "anbima_foco_oficial": "Fomento Mercantil",
        }
    )

    candidates = _family_evidence(pages)
    selected, _ = _select_family(candidates, row)

    assert selected is not None
    assert selected["family"].key == "recebiveis_comerciais"


def test_conclusion_ignores_incidental_delinquency_monitoring() -> None:
    pages = [
        "A gestora deve monitorar a adimplência da carteira e diligenciar a cobrança "
        "dos direitos creditórios vencidos e não pagos."
    ]
    row = pd.Series(
        {
            "nome_fidc": "FIDC AGRO EXEMPLO",
            "anbima_tipo_oficial": "Agro, Indústria e Comércio",
            "anbima_foco_oficial": "Agronegócio",
        }
    )

    candidates = _family_evidence(pages)
    selected, _ = _select_family(candidates, row)

    assert selected is None


def test_conclusion_keeps_npl_when_fund_mandate_is_explicit() -> None:
    pages = [
        "O objetivo é adquirir carteiras de créditos inadimplidos e vencidos na data "
        "da cessão."
    ]
    row = pd.Series(
        {
            "nome_fidc": "FIDC MULTISEGMENTOS NPL EXEMPLO",
            "anbima_tipo_oficial": "Outros",
            "anbima_foco_oficial": "Multicarteira Outros",
        }
    )

    candidates = _family_evidence(pages)
    selected, _ = _select_family(candidates, row)

    assert selected is not None
    assert selected["family"].key == "npl"


def test_documentary_overrides_preserve_mixed_mandates_and_bank_issuers() -> None:
    cnpjs = sorted(
        set(DOCUMENTARY_OVERRIDES)
        | set(CURATED_CLASSIFICATION_OVERRIDES)
        | set(BANK_ISSUER_CNPJS)
    )
    rows = [
        {**{column: "" for column in OUTPUT_COLUMNS}, "cnpj_fundo": cnpj}
        for cnpj in cnpjs
    ]

    result = _apply_documentary_overrides(pd.DataFrame(rows))
    indexed = result.set_index("cnpj_fundo")

    assert indexed.loc["49826785000145", "reclassification_status"] == (
        "manter_classificacao_oficial"
    )
    assert indexed.loc["49826785000145", "foco_anbima_sugerido"] == (
        "Multicarteira Outros"
    )
    assert indexed.loc["43911620000195", "tipo_anbima_sugerido"] == "Financeiro"
    assert indexed.loc["43911620000195", "taxonomia_funcional_n2_sugerida"] == (
        "Bancos Emissores"
    )
    assert indexed.loc["52256912000122", "reclassification_status"] == (
        "manter_classificacao_oficial"
    )
    assert indexed.loc["24761946000139", "foco_anbima_sugerido"] == "Crédito Pessoal"
    assert indexed.loc["32527650000186", "tabela_ii_sugerida_documental"] == "N/D"


def test_documentary_layer_precedence_is_field_by_field() -> None:
    automated = pd.DataFrame(
        [
            {
                "cnpj_fundo": "12.345.678/0001-90",
                "tipo_anbima_sugerido": "Outros",
                "evidence_summary": "extração automática",
            }
        ]
    )
    concluded = pd.DataFrame(
        [
            {
                "cnpj_fundo": "12345678000190",
                "tipo_anbima_sugerido": "Financeiro",
                "foco_anbima_sugerido": "Crédito Consignado",
                "evidence_summary": "conclusão integral",
            }
        ]
    )
    human = pd.DataFrame(
        [
            {
                "cnpj_fundo": "12345678000190",
                "tipo_anbima_sugerido": "",
                "evidence_summary": "trecho validado por pessoa",
            }
        ]
    )

    result = _merge_documentary_review_layers(automated, concluded, human)

    assert len(result) == 1
    assert result.loc[0, "tipo_anbima_sugerido"] == "Financeiro"
    assert result.loc[0, "foco_anbima_sugerido"] == "Crédito Consignado"
    assert result.loc[0, "evidence_summary"] == "trecho validado por pessoa"


def test_conclusion_digest_uses_uncompressed_gzip_content(tmp_path) -> None:
    content = b"cnpj_fundo,competencia\n12345678000190,2026-06\n"
    source = tmp_path / "base.csv.gz"
    with gzip.open(source, "wb") as handle:
        handle.write(content)

    assert _digest(source) == hashlib.sha256(content).hexdigest()
