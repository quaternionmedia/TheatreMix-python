"""DCA grid rows and columns (pure functions behind the /theatremix page)."""

from theatremix.models import Cue
from theatremix.ui import grid_columns, grid_rows


def _cue(number, point=0, name=None, colour=None, **dcas):
    cue = Cue(number=number, point=point, name=name, colour=colour)
    for key, value in dcas.items():  # e.g. dca01Label='Judge', dca01Channels='3'
        setattr(cue, key, value)
    return cue


def test_columns_follow_dca_list():
    cols = grid_columns([1, 3])
    assert [c['name'] for c in cols] == ['cue', 'name', 'dca1', 'dca3']


def test_rows_compare_each_dca_with_previous_cue():
    cues = [
        _cue(1, name='Foreman', dca01Label='Foreman', dca01Channels='1'),
        _cue(2, name='Judge', dca01Label='Foreman', dca01Channels='1', dca02Label='Judge', dca02Channels='2'),
        _cue(3, name='Clear', dca02Label=None, dca02Channels=None),
    ]
    rows = grid_rows(cues, [1, 2])
    assert [r['id'] for r in rows] == ['1.0', '2.0', '3.0']
    assert rows[0]['dca1'] == {'label': 'Foreman', 'channels': '1', 'cls': 'text-green-4'}
    assert rows[0]['dca2']['cls'] == 'text-grey-7'  # empty
    assert rows[1]['dca1']['cls'] == 'text-white'  # unchanged
    assert rows[1]['dca2']['cls'] == 'text-green-4'  # new
    assert rows[2]['dca2']['cls'] == 'text-red-4'  # cleared


def test_cue_label_and_row_tint():
    rows = grid_rows([_cue(5, point=10, name='Gamma', colour=1)], [])
    assert rows[0]['cue'] == '5.10'
    assert rows[0]['row_cls'] == 'bg-red-10'
    assert grid_rows([_cue(5)], [])[0]['row_cls'] == ''


def test_parse_channels():
    from theatremix.ui import parse_channels

    assert parse_channels(' 1, 2,3 ') == '1,2,3'
    assert parse_channels('') is None
    assert parse_channels('   ') is None
    for bad in ('1-2', 'a', '1,,2', ',1'):
        try:
            parse_channels(bad)
        except ValueError:
            continue
        raise AssertionError(f'{bad!r} should be rejected')


def test_merge_channels():
    from theatremix.ui import merge_channels

    assert merge_channels('', '3,4') == '3,4'
    assert merge_channels('1, 3', '3,4') == '1,3,4'
    assert merge_channels('1', '') == '1'


def test_script_previews_follow_grid_state_and_skip_non_mix():
    from types import SimpleNamespace as NS

    from theatremix.ui import script_previews

    tm = [NS(number=1, point=0, dca01Label='Judge', dca01Channels='1', dca02Label=None, dca02Channels=None),
          NS(number=2, point=0, dca01Label=None, dca01Channels=None, dca02Label='Guard', dca02Channels='13')]
    sr = [{'id': 10, 'number': '1', 'point': 0, 'layer': 'Mix'},
          {'id': 11, 'number': '2', 'point': 0, 'layer': 'Mix'},
          {'id': 12, 'number': '2', 'point': 0, 'layer': 'Sound'},
          {'id': 13, 'number': 'x', 'point': 0, 'layer': 'Mix'},
          {'id': 14, 'number': '9', 'point': 0, 'layer': 'Mix'}]
    out = script_previews(tm, [1, 2], sr)
    assert set(out) == {10, 11}
    assert out[10] == [{'text': '1 Judge', 'color': 'green-4', 'tooltip': 'DCA 1: ch 1'}]
    assert [(c['text'], c['color']) for c in out[11]] == [('1 ✕', 'red-4'), ('2 Guard', 'green-4')]
