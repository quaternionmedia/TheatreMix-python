"""Pure grid helpers in theatremix.theme."""

import pytest

from theatremix import theme
from theatremix.models import Cue


@pytest.mark.parametrize(
    'cur, nxt, expected',
    [
        (('Judge', '3'), ('Judge', '3'), 'stays_on'),  # same channels in the next cue
        (('Judge', '3'), ('Guard', '3'), 'stays_on'),  # channels unchanged, label changed
        (('Judge', '3'), ('', ''), 'muted_next'),  # muted in the next cue
        (('Judge', '3'), ('Judge', None), 'muted_next'),
        (('Judge', '3'), ('Judge', '4'), 'changed'),  # channels change
        (('Judge', '3'), None, ''),  # last cue: no next cue
        (('', ''), ('Judge', '3'), 'changed'),  # assigned in the next cue from empty
        (('', ''), ('', ''), ''),
        (('Judge', ''), ('Judge', ''), ''),  # label only, no channels
        ((None, None), (None, None), ''),
    ],
)
def test_cell_state(cur, nxt, expected):
    assert theme.cell_state(cur, nxt) == expected


def test_every_state_has_a_colour():
    assert set(theme.COLORS) == {'stays_on', 'muted_next', 'changed'}


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
    theme.override({'stays_on': 'cyan-4', 'bogus': 'pink', 'muted_next': 3})
    assert theme.COLORS['stays_on'] == 'cyan-4'
    assert theme.COLORS['muted_next'] == 'grey-7'
    assert 'bogus' not in theme.COLORS


def test_override_applies_known_keys_only():
    from theatremix import theme

    saved = dict(theme.COLORS)
    try:
        theme.override({'stays_on': 'cyan-4', 'bogus': 'red-4', 'muted_next': 42})
        assert theme.COLORS['stays_on'] == 'cyan-4'
        assert theme.COLORS['muted_next'] == 'grey-7'  # non-string ignored
        assert 'bogus' not in theme.COLORS
    finally:
        theme.COLORS.clear()
        theme.COLORS.update(saved)
