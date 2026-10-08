from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.industry_issuance_taxonomy import (
    DELTAS,
    issuance_deltas,
    periods_from_issuance_frame,
    DISPLAY_CATEGORIES,
    PERIODS,
    IssuanceTaxonomyError,
    build_issuance_taxonomy,
    build_wide_table,
    load_issuance_taxonomy,
    validate_issuance_taxonomy,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "industry_study"

#: Volumes de referência: valor encerrado ANBIMA em 2023 e volume registrado
#: CVM nos demais, os mesmos que o gráfico de emissões exibe.
EMITTED_BY_PERIOD = {
    "2023": 43_746_140_196.22,
    "2024": 95_416_726_133.75,
    "2025": 116_941_319_054.77,
    "ago25": 70_546_652_757.16,
    "ago26": 91_917_778_632.26,
}


def test_materialized_decomposition_is_complete_and_normalized() -> None:
    frame = load_issuance_taxonomy(DATA_DIR)
    assert set(frame["period_key"]) == {period["key"] for period in periods_from_issuance_frame(frame)}
    assert set(frame["categoria"]) == set(DISPLAY_CATEGORIES)
    for _, group in frame.groupby("period_key"):
        assert group["share"].sum() == pytest.approx(1.0)


def test_four_types_plus_fic_reproduce_the_issuance_chart() -> None:
    """The table must bridge back to the volume the offers chart shows.

    FIC-FIDCs leave the four types because they are quota funds, so the sum of
    the categories is deliberately below the issued volume.  What cannot happen
    is the difference being anything other than the excluded feeders.
    """

    frame, coverage = build_issuance_taxonomy(DATA_DIR)
    audit = coverage.frame().set_index("period_key")
    for key, emitted in EMITTED_BY_PERIOD.items():
        categories = float(frame.loc[frame["period_key"].eq(key), "volume_brl"].sum())
        fic = float(audit.at[key, "fic_excluded_brl"])
        assert categories + fic == pytest.approx(emitted, rel=1e-6)


def test_2023_is_scaled_to_the_anbima_level_and_others_are_not() -> None:
    _, coverage = build_issuance_taxonomy(DATA_DIR)
    audit = coverage.frame().set_index("period_key")
    assert audit.at["2023", "scale_factor"] > 1.5
    assert audit.at["2023", "observed_brl"] == pytest.approx(26_476_286_193.56)
    for key in ("2024", "2025", "ago25", "ago26"):
        assert audit.at[key, "scale_factor"] == pytest.approx(1.0)


def test_every_period_rests_mostly_on_a_positive_classification() -> None:
    """Funds the curation could not name fold into Outros — bounded, and measured.

    The rule mirrors the Escala e taxonomia tab, which sends N/D to Outros.  If
    that fallback ever carried a material share, Outros would stop meaning the
    ANBIMA category and start meaning "unknown", so the share is asserted.
    """

    _, coverage = build_issuance_taxonomy(DATA_DIR)
    for row in coverage.frame().itertuples(index=False):
        assert row.classified_share + row.outros_from_fallback_share == pytest.approx(1.0)
        if row.period_key != "ago26":
            assert row.classified_share > 0.95, row.period_label
        else:
            # New August cohort includes 20 issuers absent from monthly taxonomy.
            # Its observed 5.01% fallback is disclosed, with no classification imputed.
            assert row.classified_share == pytest.approx(0.9499113358581662)
            assert row.unresolved_issuers == 20


def test_wide_table_places_each_delta_after_the_period_it_closes() -> None:
    frame = load_issuance_taxonomy(DATA_DIR)
    table = build_wide_table(frame)
    periods = periods_from_issuance_frame(frame)
    labels = {period["key"]: period["label"] for period in periods}
    columns = list(table.columns)
    assert columns[0] == "Categoria"
    for start, end in issuance_deltas(periods):
        delta_column = f"Delta {labels[start]}→{labels[end]} (R$ bi)"
        assert delta_column in columns
        assert columns.index(delta_column) > columns.index(f"{labels[end]} (R$ bi)")
        expected = (
            frame[frame["period_key"].eq(end)].set_index("categoria")["volume_brl"]
            - frame[frame["period_key"].eq(start)].set_index("categoria")["volume_brl"]
        ).reindex(DISPLAY_CATEGORIES) / 1e9
        assert table[delta_column].tolist() == pytest.approx(expected.tolist())


def test_share_column_follows_its_own_value_column() -> None:
    """The workbook divides each share by the column to its left; hold that."""

    table = build_wide_table(load_issuance_taxonomy(DATA_DIR))
    columns = list(table.columns)
    for index, name in enumerate(columns):
        if not name.endswith("(%)"):
            continue
        left = columns[index - 1]
        assert left.endswith("(R$ bi)")
        assert left.rsplit(" (", 1)[0] == name.rsplit(" (", 1)[0]


def test_validation_rejects_shares_that_do_not_close() -> None:
    frame = load_issuance_taxonomy(DATA_DIR)
    broken = frame.copy()
    broken.loc[broken.index[0], "share"] += 0.2
    with pytest.raises(IssuanceTaxonomyError, match="participações"):
        validate_issuance_taxonomy(broken)


def test_validation_rejects_a_missing_period() -> None:
    frame = load_issuance_taxonomy(DATA_DIR)
    with pytest.raises(IssuanceTaxonomyError):
        validate_issuance_taxonomy(frame[frame["period_key"].ne("2025")])
