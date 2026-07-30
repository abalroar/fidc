from __future__ import annotations

from pathlib import Path

import pandas as pd

from services.fic_perimeter import (
    OVERRIDE_COLUMNS,
    apply_fic_perimeter_overrides,
    load_fic_perimeter_overrides,
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
    """Every corrected CNPJ must report a zero receivables portfolio."""

    overrides = load_fic_perimeter_overrides(DATA_DIR)
    if overrides.empty:
        return
    base = pd.read_csv(
        DATA_DIR / "generated_revision" / "base_fundo_cnpj.csv.gz",
        dtype=str,
        keep_default_na=False,
        usecols=["competencia", "cnpj_fundo", "carteira_dc"],
    )
    base["carteira_dc"] = pd.to_numeric(base["carteira_dc"], errors="coerce").fillna(0.0)
    scoped = base[base["cnpj_fundo"].isin(set(overrides["cnpj_fundo"]))]
    assert not scoped.empty
    assert scoped["carteira_dc"].eq(0.0).all()
