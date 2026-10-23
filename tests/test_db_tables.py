"""Generic row CRUD used by the profile/ensemble/actor sub pages."""

import pytest

from theatremix.db import TheatreMixDB
from theatremix.models import Actor, Ensemble, Profile


@pytest.fixture
def db(tmp_path):
    return TheatreMixDB(str(tmp_path / 'test.tmix'))


def test_add_update_delete_actor(db):
    actor_id = db.add_row(Actor, name='Ann', channel=3, order=1, active=0)
    db.update_row(Actor, actor_id, active=1, channel=4)
    row = next(r for r in db.list_rows(Actor) if r.id == actor_id)
    assert (row.name, row.channel, row.active) == ('Ann', 4, 1)
    db.delete_row(Actor, actor_id)
    assert db.list_rows(Actor) == []


def test_profiles_and_ensembles_are_separate(db):
    db.add_row(Profile, channel=1, name='Judge', label='Judge', default=1)
    db.add_row(Ensemble, name='Chorus', channels='5,6,7')
    assert [p.name for p in db.list_rows(Profile)] == ['Judge']
    assert [e.channels for e in db.list_rows(Ensemble)] == ['5,6,7']
