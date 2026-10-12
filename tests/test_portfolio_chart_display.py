from contextlib import nullcontext
from unittest.mock import Mock

import pandas as pd
import pytest

from services import portfolio_chart_display as display


@pytest.fixture
def ui(monkeypatch):
    calls = {name: Mock() for name in ('caption', 'altair_chart', 'dataframe')}
    for name, mock in calls.items():
        monkeypatch.setattr(display.st, name, mock)
    monkeypatch.setattr(display.st, 'expander', lambda *args, **kwargs: nullcontext())
    return calls


def test_zero_with_gaps_keeps_original_cells_and_zero_is_not_absence(ui):
    frame = pd.DataFrame({'competencia': ['jan/26', 'fev/26'], 'npl': [0., None]})
    original = frame.copy(deep=True)
    chart = Mock()
    assert display.render_portfolio_series(frame, columns=['npl'], title='NPL', chart_factory=chart) == 'zero'
    assert 'N/D' in ui['caption'].call_args.args[0]
    shown = ui['dataframe'].call_args.args[0]
    pd.testing.assert_frame_equal(frame, original)
    assert shown.loc[0, 'npl'] == 0 and pd.isna(shown.loc[1, 'npl'])
    chart.assert_not_called()


@pytest.mark.parametrize('value', [1e-200, -1e-200, 42.])
def test_any_nonzero_keeps_chart_and_original_input(ui, value):
    frame = pd.DataFrame({'npl': [value, None]})
    chart = Mock(return_value='native chart')
    assert display.render_portfolio_series(frame, columns=['npl'], title='NPL', chart_factory=chart) == 'observed'
    assert chart.call_args.args[0] is frame
    ui['altair_chart'].assert_called_once_with('native chart', use_container_width=True)
    ui['dataframe'].assert_not_called()


def test_existing_visual_ineligibility_is_explained_without_changing_original_frame(ui):
    frame = pd.DataFrame({'npl': [12.], 'universe_complete': [False]})
    original = frame.copy(deep=True)
    chart = Mock()
    status = display.render_portfolio_series(frame, columns=['npl'], title='NPL', chart_factory=chart,
        comparable_frame=frame[frame.universe_complete], absence_reason='Nenhuma competência com a base completa exigida.')
    assert status == 'absent'
    assert 'universo completo' in ui['caption'].call_args.args[0]
    assert ui['dataframe'].call_args.args[0].loc[0, 'npl'] == 12.
    chart.assert_not_called()
    pd.testing.assert_frame_equal(frame, original)
