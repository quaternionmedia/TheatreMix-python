"""Cue operations on a TheatreMix (.tmix) database keyed by (number, point)."""

import pytest

from theatremix.db import TheatreMixDB
from theatremix.models import Cue


@pytest.fixture
def db(tmp_path):
    d = TheatreMixDB(str(tmp_path / 'show.tmix'))
    d.add_cue('Alpha', number=1, point=0)
    d.add_cue('Beta', number=2, point=0)
    d.add_cue('Gamma', number=2, point=10)
    yield d
    d.close()


def test_get_cue_uses_number_and_point(db):
    assert db.get_cue(2, 0).name == 'Beta'
    assert db.get_cue(2, 10).name == 'Gamma'
    assert db.get_cue(3, 0) is None


def test_update_cue_targets_one_row(db):
    db.update_cue(2, 0, name='Beta2')
    assert db.get_cue(2, 0).name == 'Beta2'
    assert db.get_cue(2, 10).name == 'Gamma'


def test_renumber_moves_cue(db):
    db.renumber_cue(2, 10, 5, 0)
    assert db.get_cue(2, 10) is None
    assert db.get_cue(5, 0).name == 'Gamma'


def test_renumber_refuses_clash(db):
    with pytest.raises(ValueError):
        db.renumber_cue(2, 10, 1, 0)
    assert db.get_cue(2, 10).name == 'Gamma'


def test_delete_cue_by_key(db):
    db.delete_cue(2, 0)
    assert [c.name for c in db.get_all_cues()] == ['Alpha', 'Gamma']


def test_replace_cues_swaps_everything(db):
    db.replace_cues([Cue(number=9, point=0, name='New')])
    assert [(c.number, c.name) for c in db.get_all_cues()] == [(9, 'New')]


def test_get_dca_numbers_from_config(db):
    db.set_config('dcas', '1,2,3,4,5,6,7,8,9,10,11,12')
    assert db.get_dca_numbers() == list(range(1, 13))
    db.set_config('dcas', '1,2,3')
    assert db.get_dca_numbers() == [1, 2, 3]


def test_copy_cue_goes_halfway_to_next_cue(db):
    assert db.copy_cue(2, 0) == (2, 5)  # 2.00 and 2.10 -> 2.05
    assert db.get_cue(2, 5).name == 'Beta'
    assert db.get_cue(2, 0).name == 'Beta'


def test_copy_cue_between_whole_numbers_uses_point_fifty(db):
    assert db.copy_cue(1, 0) == (1, 50)  # 1.00 and 2.00 -> 1.50
    assert db.get_cue(1, 50).name == 'Alpha'


def test_copy_cue_refuses_last_cue_and_full_gaps(db):
    with pytest.raises(ValueError, match='no cue after'):
        db.copy_cue(2, 10)
    db.add_cue('Delta', number=3, point=0)
    db.add_cue('Epsilon', number=3, point=1)
    with pytest.raises(ValueError, match='No room between 3.0 and 3.1'):
        db.copy_cue(3, 0)
    assert db.get_cue(3, 0).name == 'Delta'
    assert len(db.get_all_cues()) == 5


def test_snapshot_restore_round_trip(db):
    before = db.snapshot_cues()
    db.update_cue(2, 0, name='Changed')
    db.delete_cue(2, 10)
    db.restore_cues(before)
    assert db.snapshot_cues() == before
