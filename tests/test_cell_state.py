"""Pure grid helpers in theatremix.theme."""

import pytest

from theatremix import theme
from theatremix.models import Cue


@pytest.mark.parametrize(
    'prev, cur, expected',
    [
        (('', ''), ('Judge', '3'), 'new'),  # first assignment
        (('Judge', '3'), ('Judge', '3'), 'same'),
        (('Judge', '3'), ('Judge', '4'), 'new'),  # channel changed
        (('Judge', '3'), ('', ''), 'cleared'),  # muted this cue
        (('', ''), ('', ''), 'empty'),
        ((None, None), ('Judge', None), 'new'),  # None == ''
        (('Judge', None), ('Judge', ''), 'same'),
    ],
)
def test_cell_state(prev, cur, expected):
    assert theme.cell_state(prev, cur) == expected


def test_every_state_has_a_colour():
    assert set(theme.COLORS) == {'new', 'same', 'cleared', 'empty'}


def test_dca_cell_reads_label_and_channels():
    cue = Cue(number=1, point=0, dca03Label='Guard', dca03Channels='13')
    assert theme.dca_cell(cue, 3) == ('Guard', '13')
    assert theme.dca_cell(cue, 4) == ('', '')


def test_row_colour_index():
    assert theme.row_colour(0) == ''
    assert theme.row_colour(None) == ''
    assert theme.row_colour(99) == ''
    assert theme.row_colour(1) == theme.ROW_COLOURS[1]


def test_override_changes_only_known_states(monkeypatch):
    monkeypatch.setattr(theme, 'COLORS', dict(theme.COLORS))
    theme.override({'new': 'cyan-4', 'bogus': 'pink', 'same': 3})
    assert theme.COLORS['new'] == 'cyan-4'
    assert theme.COLORS['same'] == 'white'
    assert 'bogus' not in theme.COLORS


def test_override_applies_known_keys_only():
    from theatremix import theme

    saved = dict(theme.COLORS)
    try:
        theme.override({'new': 'cyan-4', 'bogus': 'red-4', 'same': 42})
        assert theme.COLORS['new'] == 'cyan-4'
        assert theme.COLORS['same'] == 'white'  # non-string ignored
        assert 'bogus' not in theme.COLORS
    finally:
        theme.COLORS.clear()
        theme.COLORS.update(saved)
