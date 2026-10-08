import pandas as pd
import pytest

from scripts.build_fidc_revision_analysis import select_source_presence_months
from services.industry_intelligence import latest_complete_competence


def test_all_source_months_include_later_preliminary_without_promoting_it() -> None:
    panel = pd.DataFrame({"competencia": ["2026-07", "2026-08", "2026-09"]})
    status = panel.assign(publication_status=["completa", "completa", "preliminar"])
    original = status.copy(deep=True)

    assert latest_complete_competence(status) == "2026-08"
    assert select_source_presence_months(panel, "all") == [
        "2026-07", "2026-08", "2026-09"
    ]
    assert latest_complete_competence(status) == "2026-08"
    pd.testing.assert_frame_equal(status, original)


def test_explicit_source_months_preserve_requested_range() -> None:
    panel = pd.DataFrame({"competencia": ["2026-07", "2026-08", "2026-09"]})
    assert select_source_presence_months(panel, " 2026-07, 2026-08 ") == [
        "2026-07", "2026-08"
    ]


def test_all_source_months_reject_empty_panel() -> None:
    with pytest.raises(ValueError, match="sem competências"):
        select_source_presence_months(pd.DataFrame(), "all")
