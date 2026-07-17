from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.fund_return_benchmark import (
    parse_simple_cdi_plus_spread,
    resolve_fund_return_benchmarks,
)
from services.regulatory_profiles import CuratedRegulatoryProfile


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Taxa DI + 1,35% a.a.", 0.0135),
        ("CDI + 3.50% a.a.", 0.035),
        ("DI + 1,60% a.a. (252 d.u.)", 0.016),
    ],
)
def test_parse_simple_cdi_plus_spread_accepts_only_fixed_standalone_terms(
    text: str,
    expected: float,
) -> None:
    assert parse_simple_cdi_plus_spread(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text",
    [
        "CDI + até 3,50% a.a.",
        "CDI + 3,50% a.a.; cap CDI + 4,50% a.a.",
        "CDI + 3,50% a.a. + remuneração adicional",
        "CDI + 3,50% a.a. + 15% do excesso de spread",
        "CDI + 3,50% a.a. em evento de aceleração",
        "CDI + 3,50% a.a. com step-up",
        "CDI + 3,50% a.a. definido em bookbuilding",
        "130% do CDI",
        "IPCA + 5,25% a.a.",
        "CDI + 3,50% a.a. ou IPCA + 5,25% a.a.",
        "Conforme suplemento: CDI + 3,50% a.a.",
    ],
)
def test_parse_simple_cdi_plus_spread_rejects_ambiguous_or_non_fixed_terms(text: str) -> None:
    assert parse_simple_cdi_plus_spread(text) is None


def test_resolver_matches_cnpj_macro_and_explicit_series_and_exposes_diagnostics() -> None:
    requested: list[str] = []
    profile = _profile(
        profile_type="curado",
        emissions=[
            {
                "Cota/Classe": "2ª série sênior",
                "Tipo": "Sênior",
                "Remuneração": "CDI + 3,50% a.a.",
                "Fonte": "ata-2a-serie.pdf · p.5",
                "Status curadoria": "curado documental",
            }
        ],
    )

    def loader(cnpj: str) -> CuratedRegulatoryProfile:
        requested.append(cnpj)
        return profile

    result = resolve_fund_return_benchmarks(
        "33.254.370/0001-04",
        _series_frame("senior|_|série 2|_", "Sênior · Série 2", "senior"),
        profile_loader=loader,
    )

    assert requested == ["33254370000104"]
    assert result.spreads_by_class_key == {"senior|_|série 2|_": pytest.approx(0.035)}
    diagnostic = result.diagnostics_df.iloc[0]
    assert diagnostic["status"] == "resolved"
    assert diagnostic["source"] == "ata-2a-serie.pdf · p.5"
    assert diagnostic["curation_status"] == "curado documental"
    assert diagnostic["remuneration"] == "CDI + 3,50% a.a."
    assert diagnostic["matched_class"] == "2ª série sênior"
    assert diagnostic["spread_aa"] == pytest.approx(0.035)


@pytest.mark.parametrize("profile_type", ["triagem estruturada", "heurístico"])
def test_resolver_rejects_profiles_that_are_not_manually_curated(profile_type: str) -> None:
    profile = _profile(
        profile_type=profile_type,
        emissions=[
            {
                "Cota/Classe": "1ª série sênior",
                "Tipo": "Sênior",
                "Remuneração": "DI + 1,00% a.a.",
            }
        ],
    )

    result = resolve_fund_return_benchmarks(
        profile.cnpj,
        _series_frame("senior|_|série 1|_", "Sênior · Série 1", "senior"),
        profile_loader=lambda _cnpj: profile,
    )

    assert result.spreads_by_class_key == {}
    assert result.diagnostics_df.iloc[0]["status"] == "profile_not_manually_curated"


def test_resolver_requires_explicit_series_number_on_both_sides() -> None:
    profile = _profile(
        emissions=[
            {
                "Cota/Classe": "Cotas Seniores",
                "Tipo": "Sênior",
                "Remuneração": "CDI + 1,00% a.a.",
            }
        ]
    )

    missing_ime_series = resolve_fund_return_benchmarks(
        profile.cnpj,
        _series_frame("senior|_|_|_", "Sênior", "senior"),
        profile_loader=lambda _cnpj: profile,
    )
    missing_document_series = resolve_fund_return_benchmarks(
        profile.cnpj,
        _series_frame("senior|_|série 1|_", "Sênior · Série 1", "senior"),
        profile_loader=lambda _cnpj: profile,
    )

    assert missing_ime_series.diagnostics_df.iloc[0]["status"] == "missing_explicit_series_number"
    assert missing_document_series.diagnostics_df.iloc[0]["status"] == "no_matching_emission"


def test_resolver_rejects_multiple_distinct_spreads_for_the_same_series() -> None:
    profile = _profile(
        profile_type="curado parcial",
        emissions=[
            {
                "Cota/Classe": "1ª série sênior - alteração",
                "Tipo": "Sênior",
                "Remuneração": "Taxa DI + 1,34% a.a.",
                "Fonte": "alteracao.pdf",
            },
            {
                "Cota/Classe": "1ª série sênior - rerratificação",
                "Tipo": "Sênior",
                "Remuneração": "Taxa DI + 1,37% a.a.",
                "Fonte": "rerratificacao.pdf",
            },
        ],
    )

    result = resolve_fund_return_benchmarks(
        profile.cnpj,
        _series_frame("senior|_|série 1|_", "Sênior · Série 1", "senior"),
        profile_loader=lambda _cnpj: profile,
    )

    assert result.spreads_by_class_key == {}
    diagnostic = result.diagnostics_df.iloc[0]
    assert diagnostic["status"] == "ambiguous_spread"
    assert diagnostic["candidate_count"] == 2
    assert "1,34%" in diagnostic["remuneration"]
    assert "1,37%" in diagnostic["remuneration"]


def test_resolver_rejects_a_complex_term_even_when_the_first_rate_looks_parseable() -> None:
    profile = _profile(
        emissions=[
            {
                "Cota/Classe": "1ª Série Senior",
                "Tipo": "Cotas Seniores",
                "Remuneração": "CDI + 4,80% a.a. + 15% do excesso de spread, com cap de CDI + 6,00% a.a.",
                "Fonte": "ata.pdf",
            }
        ]
    )

    result = resolve_fund_return_benchmarks(
        profile.cnpj,
        _series_frame("senior|_|série 1|_", "Sênior · Série 1", "senior"),
        profile_loader=lambda _cnpj: profile,
    )

    assert result.spreads_by_class_key == {}
    assert result.diagnostics_df.iloc[0]["status"] == "unsupported_remuneration"


def test_resolver_accepts_duplicate_document_rows_only_when_the_fixed_spread_agrees() -> None:
    profile = _profile(
        emissions=[
            {
                "Cota/Classe": "3ª série sênior",
                "Tipo": "Sênior",
                "Remuneração": "DI + 1,50% a.a.",
                "Fonte": "ata.pdf",
            },
            {
                "Cota/Classe": "Sênior 3ª série",
                "Tipo": "Cotas Seniores",
                "Remuneração": "Taxa DI + 1,50% a.a.",
                "Fonte": "suplemento.pdf",
            },
        ]
    )

    result = resolve_fund_return_benchmarks(
        profile.cnpj,
        _series_frame("senior|_|série 3|_", "Sênior · Série 3", "senior"),
        profile_loader=lambda _cnpj: profile,
    )

    assert result.spreads_by_class_key == {"senior|_|série 3|_": pytest.approx(0.015)}
    assert result.diagnostics_df.iloc[0]["status"] == "resolved"
    assert result.diagnostics_df.iloc[0]["candidate_count"] == 2


def test_resolver_uses_juros_field_when_primary_remuneration_is_missing() -> None:
    profile = _profile(
        emissions=[
            {
                "Cota/Classe": "2ª série sênior",
                "Tipo": "Sênior",
                "Remuneração": pd.NA,
                "Juros/remuneração": "DI + 2,50% a.a.",
            }
        ]
    )

    result = resolve_fund_return_benchmarks(
        profile.cnpj,
        _series_frame("senior|_|série 2|_", "Sênior · Série 2", "senior"),
        profile_loader=lambda _cnpj: profile,
    )

    assert result.spreads_by_class_key == {"senior|_|série 2|_": pytest.approx(0.025)}


def test_resolver_fails_closed_when_class_key_collides_across_reported_series() -> None:
    profile = _profile(
        emissions=[
            {
                "Cota/Classe": "1ª série subordinada",
                "Tipo": "Subordinada",
                "Remuneração": "DI + 1,00% a.a.",
            }
        ]
    )
    series = pd.DataFrame(
        [
            {
                "class_key": "subordinada|subordinada 1|série 1|_",
                "class_label": "Subordinada 1 · Série 1 · item 1",
                "class_kind": "subordinada",
            },
            {
                "class_key": "subordinada|subordinada 1|série 1|_",
                "class_label": "Subordinada 1 · Série 1 · item 2",
                "class_kind": "subordinada",
            },
        ]
    )

    result = resolve_fund_return_benchmarks(
        profile.cnpj,
        series,
        profile_loader=lambda _cnpj: profile,
    )

    assert result.spreads_by_class_key == {}
    assert set(result.diagnostics_df["status"]) == {"ambiguous_series_identity"}


def _series_frame(class_key: str, class_label: str, class_kind: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "class_key": class_key,
                "class_label": class_label,
                "class_kind": class_kind,
            }
        ]
    )


def _profile(
    *,
    profile_type: str = "curado",
    emissions: list[dict[str, str]],
) -> CuratedRegulatoryProfile:
    return CuratedRegulatoryProfile(
        cnpj="33254370000104",
        emissions_df=pd.DataFrame(emissions),
        criteria_df=pd.DataFrame(),
        source_files=(Path("perfil.csv"),),
        profile_type=profile_type,
    )
