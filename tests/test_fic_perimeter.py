from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from services.fic_perimeter import (
    OVERRIDE_COLUMNS,
    apply_fic_perimeter_overrides,
    assert_fic_overrides_have_no_direct_receivables,
    load_fic_perimeter_overrides,
    validate_fic_quantitative_overrides,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "industry_study"


def _overrides(*cnpjs: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cnpj_fundo": cnpj,
                "denominacao": f"fundo {cnpj}",
                "is_fic_fidc": True,
                "evidencia": "cotas de FIDC acima de 50% das aplicações",
                "fonte": "Informe Mensal Estruturado CVM",
                "revisado_em_utc": "2026-07-30T00:00:00+00:00",
            }
            for cnpj in cnpjs
        ],
        columns=list(OVERRIDE_COLUMNS),
    )


def _vehicle() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "competencia": ["2026-06", "2026-06", "2025-12"],
            "cnpj": ["11111111000191", "22222222000172", "11111111000191"],
            "is_fic_fidc": [False, True, False],
            "pl": [1_000_000_000.0, 500_000_000.0, 800_000_000.0],
        }
    )


def test_no_overrides_leaves_the_frame_untouched() -> None:
    frame = _vehicle()

    corrected, correction = apply_fic_perimeter_overrides(frame, _overrides())

    assert correction.cnpj_count == 0
    pd.testing.assert_frame_equal(corrected, frame)


def test_quantitative_override_is_refused_when_a_later_month_reports_receivables() -> None:
    frame = _vehicle()
    frame["carteira_dc"] = [12_900_000.0, 0.0, 0.0]
    frame.loc[0, "competencia"] = "2026-07"
    original = frame.copy()
    with pytest.raises(ValueError, match="11111111000191 · 2026-07"):
        apply_fic_perimeter_overrides(frame, _overrides("11111111000191"))
    pd.testing.assert_frame_equal(frame, original)


def test_quantitative_preflight_does_not_replace_missing_receivables_with_zero() -> None:
    frame = _vehicle()
    frame["carteira_dc"] = [None, 0.0, 0.0]
    original = frame.copy()
    assert_fic_overrides_have_no_direct_receivables(frame, _overrides("11111111000191"))
    pd.testing.assert_frame_equal(frame, original)
    with pytest.raises(ValueError, match="carteira_dc"):
        assert_fic_overrides_have_no_direct_receivables(frame.drop(columns="carteira_dc"), _overrides("11111111000191"))


def test_preflight_reads_raw_monthly_before_any_generated_bundle(tmp_path: Path) -> None:
    _overrides("11111111000191").to_csv(tmp_path / "fic_perimeter_overrides.csv", index=False)
    frame = _vehicle()
    frame["carteira_dc"] = [1.0, 0.0, 0.0]
    frame.to_csv(tmp_path / "vehicle_monthly.csv.gz", index=False, compression="gzip")
    with pytest.raises(ValueError, match="11111111000191 · 2026-06"):
        validate_fic_quantitative_overrides(tmp_path)
    frame.loc[0, "carteira_dc"] = 0.0
    frame.to_csv(tmp_path / "vehicle_monthly.csv.gz", index=False, compression="gzip")
    validate_fic_quantitative_overrides(tmp_path)


def test_the_flag_is_turned_on_for_every_competence_of_the_cnpj() -> None:
    corrected, correction = apply_fic_perimeter_overrides(
        _vehicle(), _overrides("11111111000191")
    )

    assert correction.cnpj_count == 1
    assert correction.rows_changed == 2
    assert correction.pl_moved_brl == 1_800_000_000.0
    assert correction.competences == ("2025-12", "2026-06")
    # O saldo que sai dos tipos ANBIMA é o da competência mais recente, não a
    # soma do fluxo mensal.
    assert correction.last_competence == "2026-06"
    assert correction.pl_moved_last_competence_brl == 1_000_000_000.0
    assert bool(corrected.loc[corrected["cnpj"].eq("11111111000191"), "is_fic_fidc"].all())


def test_a_fund_already_reported_as_fic_is_not_counted_twice() -> None:
    """The correction only turns the flag on; it never re-moves what is moved."""

    corrected, correction = apply_fic_perimeter_overrides(
        _vehicle(), _overrides("22222222000172")
    )

    assert correction.cnpj_count == 0
    assert correction.pl_moved_brl == 0.0
    assert bool(corrected.loc[corrected["cnpj"].eq("22222222000172"), "is_fic_fidc"].all())


def test_the_correction_never_turns_a_flag_off() -> None:
    frame = _vehicle()
    frame.loc[frame["cnpj"].eq("22222222000172"), "is_fic_fidc"] = True

    corrected, _correction = apply_fic_perimeter_overrides(
        frame, _overrides("11111111000191")
    )

    assert bool(corrected.loc[corrected["cnpj"].eq("22222222000172"), "is_fic_fidc"].all())


def test_a_masked_cnpj_in_the_curation_still_matches() -> None:
    corrected, correction = apply_fic_perimeter_overrides(
        _vehicle(), _overrides("11.111.111/0001-91")
    )

    assert correction.cnpj_count == 1
    assert bool(corrected.loc[corrected["cnpj"].eq("11111111000191"), "is_fic_fidc"].all())


def test_a_missing_curation_file_is_not_an_error(tmp_path: Path) -> None:
    overrides = load_fic_perimeter_overrides(tmp_path)

    assert overrides.empty
    assert list(overrides.columns) == list(OVERRIDE_COLUMNS)


def test_the_published_curation_is_well_formed() -> None:
    overrides = load_fic_perimeter_overrides(DATA_DIR)
    if overrides.empty:
        return
    assert overrides["cnpj_fundo"].str.fullmatch(r"\d{14}").all()
    assert not overrides["cnpj_fundo"].duplicated().any()
    assert overrides["evidencia"].str.len().gt(0).all()
    assert overrides["fonte"].str.len().gt(0).all()


def test_the_published_curation_only_covers_funds_without_receivables() -> None:
    """The active decisions are checked against source observations."""

    overrides = load_fic_perimeter_overrides(DATA_DIR)
    if overrides.empty:
        return
    base = pd.read_csv(
        DATA_DIR / "vehicle_monthly.csv.gz",
        dtype=str,
        keep_default_na=False,
        usecols=["competencia", "cnpj", "carteira_dc"],
    )
    scoped = base[base["cnpj"].isin(set(overrides["cnpj_fundo"]))]
    assert not scoped.empty
    observed = pd.to_numeric(scoped["carteira_dc"], errors="coerce").dropna()
    assert not observed.empty
    assert observed.eq(0.0).all()
    validate_fic_quantitative_overrides(DATA_DIR)


def test_revoked_decisions_preserve_old_evidence_and_current_source_observations() -> None:
    history = pd.read_csv(
        DATA_DIR / "fic_perimeter_overrides_history.csv",
        dtype=str,
        keep_default_na=False,
    )
    revoked_ids = {"54519672000137", "43140980000130", "64780387000129"}
    assert set(history["cnpj_fundo"]) == revoked_ids
    assert set(load_fic_perimeter_overrides(DATA_DIR)["cnpj_fundo"]).isdisjoint(revoked_ids)
    source = pd.read_csv(
        DATA_DIR / "vehicle_monthly.csv.gz",
        dtype={"cnpj": str, "competencia": str},
        usecols=["cnpj", "competencia", "carteira_dc", "pl"],
    ).set_index(["cnpj", "competencia"])
    for row in history.to_dict("records"):
        assert row["decisao_atual"] == "revogado_por_carteira_dc_positiva"
        original = json.loads(row["registro_revisao_original"])
        assert original[0]["cnpj_fundo"] == row["cnpj_fundo"]
        assert original[0]["veredito"] == "fic_confirmado"
        assert original[0]["evidencia"] == row["evidencia"]
        observations = json.loads(row["observacoes_dc_positiva"])
        official_sources = json.loads(row["fontes_brutas"])
        assert observations
        for observation in observations:
            month = observation["competencia"]
            raw = source.loc[(row["cnpj_fundo"], month)]
            assert float(observation["carteira_dc"]) == raw["carteira_dc"] > 0
            assert float(observation["pl"]) == raw["pl"]
            assert official_sources[month]["url"].startswith("https://dados.cvm.gov.br/")
            assert len(official_sources[month]["sha256"]) == 64
