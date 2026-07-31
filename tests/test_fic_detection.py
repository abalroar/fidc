from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from scripts.build_fidc_industry_study import FIC_FIDC_PATTERN
from scripts.build_fic_detection_audit import build_fic_detection_audit_frame
from services.fic_detection import (
    METHOD_INFORME,
    METHOD_LEGACY_NOMINAL,
    METHOD_NAME,
    annotate_fic_detection,
    build_fic_audit,
    exclude_fics_from_fidc_universe,
    name_says_fic,
)
from services.fic_perimeter import (
    apply_fic_perimeter_overrides,
    load_fic_perimeter_overrides,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "industry_study"


@pytest.mark.parametrize(
    "name",
    [
        "XP FIC FIDC",
        "ABC-FIC-DL",
        "FIC MULTISETORIAL",
        "FUNDO ALFA (FIC) II",
        "FUNDO BETA/FIC",
        "ESTRUTURA FIC.",
        "fic minusculo",
    ],
)
def test_fic_is_detected_as_an_isolated_token(name: str) -> None:
    assert name_says_fic(name)


@pytest.mark.parametrize(
    "name",
    [
        "FICÇÃO CAPITAL",
        "SIFIC FUNDO DE INVESTIMENTO",
        "FIC123 CAPITAL",
        "PACIFICO FIDC",
        "FUNDO MAGNIFICO",
        "ARTIFICE CREDITO",
        "",
        "   ",
    ],
)
def test_fic_welded_into_another_sequence_is_not_detected(name: str) -> None:
    """The substring rule is exactly the false positive this audit prevents."""

    assert name_says_fic(name) == ""


@pytest.mark.parametrize(
    "name",
    [
        "FUNDO DE INVESTIMENTO EM COTAS DE FIDC",
        "FI EM COTAS DE FUNDOS DE INVESTIMENTO EM DIREITOS CREDITÓRIOS",
    ],
)
def test_the_spelled_out_legal_form_is_detected(name: str) -> None:
    assert "forma legal" in name_says_fic(name)


def _base() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "competencia": ["2026-06"] * 5 + ["2025-12"],
            "cnpj_fundo": [
                "11111111000191",
                "22222222000172",
                "33333333000153",
                "44444444000134",
                "55555555000115",
                "11111111000191",
            ],
            "denominacao": [
                "ALFA FIDC",
                "BETA FIC FIDC",
                "GAMA FIDC",
                "DELTA FIC FIDC",
                "PACIFICO FIDC",
                "ALFA FIDC",
            ],
            "is_fic_fidc": [False, True, False, False, False, False],
            "pl": [1e9, 2e9, 3e9, 4e9, 5e9, 8e8],
        }
    )


def test_the_legacy_nominal_signal_alone_excludes() -> None:
    annotated = annotate_fic_detection(_base(), curated_cnpjs=())

    beta = annotated[annotated["cnpj_fundo"].eq("22222222000172")].iloc[0]
    assert bool(beta["is_fic"])
    assert beta["fic_detection_method"] == METHOD_LEGACY_NOMINAL
    assert "Sinal nominal legado" in beta["fic_detection_evidence"]
    assert "CVM" not in beta["fic_detection_evidence"]
    assert "cadastral" not in beta["fic_detection_evidence"]
    assert "sinal nominal legado" in beta["fic_exclusion_reason"]


def test_the_informe_rule_excludes_a_fund_the_legacy_signal_missed() -> None:
    annotated = annotate_fic_detection(
        _base(), curated_cnpjs=["33333333000153"], curated_evidence={
            "33333333000153": "cotas de FIDC em 96% das aplicações"
        }
    )

    gama = annotated[annotated["cnpj_fundo"].eq("33333333000153")].iloc[0]
    assert bool(gama["is_fic"])
    assert gama["fic_detection_method"] == METHOD_INFORME
    assert "96%" in gama["fic_detection_evidence"]


def test_the_quantitative_review_takes_provenance_precedence() -> None:
    annotated = annotate_fic_detection(
        _base(),
        curated_cnpjs=["22222222000172"],
        curated_evidence={"22222222000172": "confirmação quantitativa curada"},
    )

    beta = annotated[annotated["cnpj_fundo"].eq("22222222000172")].iloc[0]
    assert beta["fic_detection_method"] == METHOD_INFORME
    assert "confirmação quantitativa curada" in beta["fic_detection_evidence"]


def test_the_secondary_nominal_crosscheck_alone_opens_review() -> None:
    """DELTA is named FIC yet buys receivables; excluding it would be the bug."""

    annotated = annotate_fic_detection(_base(), curated_cnpjs=())

    delta = annotated[annotated["cnpj_fundo"].eq("44444444000134")].iloc[0]
    assert not bool(delta["is_fic"])
    assert delta["fic_detection_method"] == METHOD_NAME
    assert bool(delta["revisao_manual_sugerida"])
    assert "sem confirmação quantitativa registrada" in delta["motivo_revisao"]


def test_a_name_that_merely_contains_fic_raises_nothing() -> None:
    annotated = annotate_fic_detection(_base(), curated_cnpjs=())

    pacifico = annotated[annotated["cnpj_fundo"].eq("55555555000115")].iloc[0]
    assert not bool(pacifico["is_fic"])
    assert not bool(pacifico["revisao_manual_sugerida"])


def test_the_secondary_nominal_detail_is_recorded_with_quantitative_evidence() -> None:
    annotated = annotate_fic_detection(
        _base(),
        curated_cnpjs=["22222222000172"],
    )

    beta = annotated[annotated["cnpj_fundo"].eq("22222222000172")].iloc[0]
    assert "Detalhe nominal" in beta["fic_detection_evidence"]


def test_the_gate_removes_every_competence_of_an_excluded_cnpj() -> None:
    annotated = annotate_fic_detection(_base(), curated_cnpjs=["11111111000191"])

    kept, report = exclude_fics_from_fidc_universe(annotated)

    assert "11111111000191" not in set(kept["cnpj_fundo"])
    assert report.cnpj_excluded == 2
    assert report.rows_excluded == 3
    assert report.last_competence == "2026-06"


def test_the_gate_reports_the_balance_not_the_flow() -> None:
    annotated = annotate_fic_detection(_base(), curated_cnpjs=["11111111000191"])

    _kept, report = exclude_fics_from_fidc_universe(annotated)

    # ALFA 1,0 bi + BETA 2,0 bi em 2026-06; os 0,8 bi de 2025-12 não entram.
    assert report.pl_excluded_last_competence_brl == 3e9


def test_an_unannotated_frame_is_refused_rather_than_passed_through() -> None:
    """Silently skipping the filter is how the same money gets counted twice."""

    naked = pd.DataFrame({"cnpj_fundo": ["11111111000191"], "pl": [1.0]})

    with pytest.raises(KeyError, match="annotate_fic_detection"):
        exclude_fics_from_fidc_universe(naked)


def test_the_legacy_signal_is_accepted_so_nothing_slips_through_unfiltered() -> None:
    legacy = _base()

    kept, report = exclude_fics_from_fidc_universe(legacy)

    assert report.cnpj_excluded == 1
    assert "22222222000172" not in set(kept["cnpj_fundo"])


def test_the_audit_carries_excluded_and_ambiguous_funds() -> None:
    annotated = annotate_fic_detection(_base(), curated_cnpjs=["33333333000153"])

    audit = build_fic_audit(annotated)

    excluded = audit[audit["is_fic"]]
    ambiguous = audit[audit["revisao_manual_sugerida"]]
    assert set(excluded["cnpj_fundo"]) == {"22222222000172", "33333333000153"}
    assert set(ambiguous["cnpj_fundo"]) == {"44444444000134"}
    assert excluded["fic_exclusion_reason"].str.len().gt(0).all()


def test_the_published_audit_is_well_formed() -> None:
    path = DATA_DIR / "industry_fic_detection_audit.csv"
    if not path.exists():
        pytest.skip("auditoria ainda não materializada")
    audit = pd.read_csv(path, dtype=str, keep_default_na=False)

    assert audit["cnpj_fundo"].str.fullmatch(r"\d{14}").all()
    excluded = audit[audit["is_fic"].str.casefold().eq("true")]
    assert excluded["fic_detection_method"].str.len().gt(0).all()
    assert excluded["fic_detection_evidence"].str.len().gt(0).all()
    assert excluded["fic_exclusion_reason"].str.len().gt(0).all()
    assert set(audit["fic_detection_method"]) == {
        METHOD_LEGACY_NOMINAL,
        METHOD_INFORME,
        METHOD_NAME,
    }
    nominal = audit[
        audit["fic_detection_method"].eq(METHOD_LEGACY_NOMINAL)
    ]
    assert nominal["fic_detection_evidence"].str.startswith(
        "Sinal nominal legado:"
    ).all()
    assert not audit["fic_detection_evidence"].str.contains(
        "flag cadastral",
        case=False,
        regex=False,
    ).any()


def test_the_versioned_audit_matches_the_current_provenance_rules() -> None:
    path = DATA_DIR / "industry_fic_detection_audit.csv"
    expected = build_fic_detection_audit_frame(DATA_DIR)

    assert path.read_bytes() == expected.to_csv(index=False).encode("utf-8")


def test_provenance_relabel_preserves_the_full_fic_mask_and_pl() -> None:
    vehicle = pd.read_csv(
        DATA_DIR / "vehicle_monthly.csv.gz",
        usecols=[
            "competencia",
            "cnpj",
            "denominacao",
            "is_fic_fidc",
            "pl",
        ],
        dtype={
            "competencia": str,
            "cnpj": str,
            "denominacao": str,
        },
        low_memory=False,
    )
    reported_signal = (
        vehicle["is_fic_fidc"]
        .astype(str)
        .str.strip()
        .str.casefold()
        .isin({"true", "1", "sim", "t", "yes"})
    )
    derived_signal = vehicle["denominacao"].fillna("").str.contains(
        FIC_FIDC_PATTERN,
        na=False,
    )
    assert len(vehicle) == 229_451
    assert reported_signal.equals(derived_signal)

    overrides = load_fic_perimeter_overrides(DATA_DIR)
    corrected, _ = apply_fic_perimeter_overrides(vehicle, overrides)
    annotated = annotate_fic_detection(
        corrected,
        curated_cnpjs=overrides["cnpj_fundo"],
        curated_evidence=dict(
            zip(overrides["cnpj_fundo"], overrides["evidencia"])
        ),
        cnpj_column="cnpj",
    )

    mask = annotated[["competencia", "cnpj", "is_fic"]].copy()
    mask["is_fic"] = mask["is_fic"].astype(bool).astype(int)
    mask = mask.sort_values(["competencia", "cnpj"], kind="mergesort")
    mask_blob = "".join(
        f"{row.competencia}|{row.cnpj}|{row.is_fic}\n"
        for row in mask.itertuples(index=False)
    ).encode()
    assert hashlib.sha256(mask_blob).hexdigest() == (
        "7c8a531b0b2d2daad47a36e8f55087dd3c7b55c9e46e4c5f7102d59ee40b65b5"
    )

    annotated["pl_cents"] = (
        pd.to_numeric(annotated["pl"], errors="raise")
        .mul(100)
        .round()
        .astype("int64")
    )
    lines = [
        "competencia,rows,fic_rows,pl_gross_cents,pl_fic_cents,pl_ex_cents"
    ]
    for competence, group in annotated.groupby("competencia", sort=True):
        is_fic = group["is_fic"].astype(bool)
        gross = int(group["pl_cents"].sum())
        fic = int(group.loc[is_fic, "pl_cents"].sum())
        direct = int(group.loc[~is_fic, "pl_cents"].sum())
        lines.append(
            f"{competence},{len(group)},{int(is_fic.sum())},"
            f"{gross},{fic},{direct}"
        )
    aggregate_blob = ("\n".join(lines) + "\n").encode()
    assert hashlib.sha256(aggregate_blob).hexdigest() == (
        "7276fa1d0be2fe4ba8202a577842f912e97afe3f42da7077b70ac95081096648"
    )

    current = annotated[annotated["competencia"].eq("2026-06")].copy()
    current_fics = current[current["is_fic"].astype(bool)]
    assert len(current) == 4_252
    assert len(current_fics) == 773
    assert int(current["pl_cents"].sum()) == 96_148_603_788_865
    assert int(current_fics["pl_cents"].sum()) == 14_012_447_860_420
    assert int(
        current.loc[~current["is_fic"].astype(bool), "pl_cents"].sum()
    ) == 82_136_155_928_445
    assert current_fics["fic_detection_method"].value_counts().to_dict() == {
        METHOD_LEGACY_NOMINAL: 451,
        METHOD_INFORME: 322,
    }
    by_method = current_fics.groupby("fic_detection_method")["pl_cents"].sum()
    assert int(by_method[METHOD_LEGACY_NOMINAL]) == 8_071_759_150_214
    assert int(by_method[METHOD_INFORME]) == 5_940_688_710_206


def test_a_decision_reaches_every_competence_of_the_cnpj() -> None:
    """One decision per CNPJ, applied to the whole history — never per month."""

    from services.industry_taxonomy_review import (
        TAXONOMY_REVIEW_COLUMNS,
        apply_taxonomy_review_overlay,
        taxonomy_review_id,
    )

    funds = pd.DataFrame(
        {
            "competencia": ["2023-12", "2024-12", "2025-12", "2026-06"],
            "cnpj_fundo": ["11111111000191"] * 4,
            "anbima_tipo": ["Outros"] * 4,
            "anbima_foco": ["Multicarteira Outros"] * 4,
            "tabela_ii_dominante": ["N/D"] * 4,
        }
    )
    action = {column: "" for column in TAXONOMY_REVIEW_COLUMNS}
    action.update(
        {
            "review_id": taxonomy_review_id("11111111000191"),
            "cnpj_fundo": "11111111000191",
            "status": "aprovado",
            "tipo_analitico": "Financeiro",
            "foco_analitico": "Crédito Consignado",
            "tabela_ii_analitica": "Financeiro",
            "taxonomia_funcional_n1": "Crédito PF",
            "taxonomia_funcional_n2": "Consignado/INSS",
            "confianca": "alta",
            "competencia_referencia": "2026-06",
            "denominacao_referencia": "FUNDO TESTE",
            "fonte_documental": "regulamento",
            "pagina_clausula": "p. 5",
            "responsavel": "teste",
            "evidencia": "regulamento p. 5: cessão de contratos de consignado.",
            "updated_at_utc": "2026-07-30T00:00:00+00:00",
        }
    )

    overlaid = apply_taxonomy_review_overlay(
        funds, pd.DataFrame([action], columns=list(TAXONOMY_REVIEW_COLUMNS))
    )

    assert overlaid["anbima_tipo_curado"].eq("Financeiro").all()
    assert overlaid["anbima_foco_curado"].eq("Crédito Consignado").all()
    assert overlaid["taxonomy_review_applied"].all()
    assert len(overlaid["competencia"].unique()) == 4
