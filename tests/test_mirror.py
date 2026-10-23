"""mirror_cue: ShowRunner create, edit and delete on the TheatreMix layer reach the .tmix file."""

import pytest
from sqlmodel import Session, SQLModel, create_engine

from showrunner.models import Cue as SRCue, Show

from theatremix.db import TheatreMixDB
from theatremix.sync import get_or_create_cue_list, mirror_cue


@pytest.fixture
def s():
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        show = Show(name='Show')
        session.add(show)
        session.commit()
        session.refresh(show)
        session.info['show_id'] = show.id
        yield session


@pytest.fixture
def tm(tmp_path):
    return TheatreMixDB(str(tmp_path / 'test.tmix'), create_schema=True, init_config=True)


def _state(row: SRCue) -> dict:
    return {'id': row.id, 'number': row.number, 'point': row.point, 'name': row.name,
            'layer': row.layer, 'cue_type': row.cue_type, 'cue_list_id': row.cue_list_id,
            'script_line': row.script_line, 'script_char': row.script_char}


def _add(s, **fields) -> SRCue:
    row = SRCue(**fields)
    s.add(row)
    s.commit()
    s.refresh(row)
    return row


def test_new_cue_copies_previous_state_halfway_after_it(s, tm):
    tm.add_cue(name='Judge', dca_channels={1: '1,2'}, dca_labels={1: 'Judge'}, number=1, point=0)
    tm.add_cue(name='Next', number=2, point=0)
    lst = get_or_create_cue_list(s, s.info['show_id'])
    _add(s, cue_list_id=lst.id, layer='Mix', cue_type='TheatreMix', number='1', point=0,
         name='Judge', script_line=10, script_char=0)
    new = _add(s, cue_list_id=lst.id, layer='Mix', name='Dup', script_line=20, script_char=0)

    mirror_cue(s, tm, s.info['show_id'], lst.id, 'Mix', 'create', _state(new))

    row = s.get(SRCue, new.id)
    assert (row.number, row.point, row.cue_type) == ('1', 50, 'TheatreMix')
    copy = tm.get_cue(1, 50)
    assert (copy.name, copy.dca01Channels, copy.dca01Label) == ('Dup', '1,2', 'Judge')


def test_rename_and_renumber_update_the_tmix_cue(s, tm):
    tm.add_cue(name='Old', number=1, point=0)
    lst = get_or_create_cue_list(s, s.info['show_id'])
    row = _add(s, cue_list_id=lst.id, layer='Mix', cue_type='TheatreMix', number='1', point=0,
               name='Old', script_line=10, script_char=0)
    before = _state(row)
    row.number, row.name = '5', 'New'
    s.add(row)
    s.commit()

    mirror_cue(s, tm, s.info['show_id'], lst.id, 'Mix', 'update', _state(row), before)

    assert tm.get_cue(1, 0) is None
    assert (tm.get_cue(5, 0).name, s.get(SRCue, row.id).number) == ('New', '5')


def test_clashing_renumber_is_reverted_in_shownrunner(s, tm):
    tm.add_cue(name='One', number=1, point=0)
    tm.add_cue(name='Two', number=2, point=0)
    lst = get_or_create_cue_list(s, s.info['show_id'])
    row = _add(s, cue_list_id=lst.id, layer='Mix', cue_type='TheatreMix', number='1', point=0,
               name='One', script_line=10, script_char=0)
    before = _state(row)
    row.number = '2'
    s.add(row)
    s.commit()

    mirror_cue(s, tm, s.info['show_id'], lst.id, 'Mix', 'update', _state(row), before)

    assert s.get(SRCue, row.id).number == '1'
    assert tm.get_cue(1, 0).name == 'One' and tm.get_cue(2, 0).name == 'Two'


def test_delete_removes_the_tmix_cue_and_undo_restores_it(s, tm):
    tm.add_cue(name='Gone', number=1, point=0)
    lst = get_or_create_cue_list(s, s.info['show_id'])
    row = _add(s, cue_list_id=lst.id, layer='Mix', cue_type='TheatreMix', number='1', point=0,
               name='Gone', script_line=10, script_char=0)
    state = _state(row)

    mirror_cue(s, tm, s.info['show_id'], lst.id, 'Mix', 'delete', state)
    assert tm.get_cue(1, 0) is None

    # Undo of the delete: no earlier linked cue, so it is refused and left unlinked.
    undo = _add(s, cue_list_id=lst.id, layer='Mix', cue_type='TheatreMix', number='1', point=0,
                name='Gone', script_line=10, script_char=0)
    assert mirror_cue(s, tm, s.info['show_id'], lst.id, 'Mix', 'create', _state(undo))
    assert tm.get_all_cues() == []
    assert s.get(SRCue, undo.id).cue_type is None


def test_no_earlier_linked_cue_is_refused_and_nothing_is_written(s, tm):
    lst = get_or_create_cue_list(s, s.info['show_id'])
    tm.add_cue(name='Only', number=1, point=0)
    new = _add(s, cue_list_id=lst.id, layer='Mix', name='First', script_line=5, script_char=0)

    msg = mirror_cue(s, tm, s.info['show_id'], lst.id, 'Mix', 'create', _state(new))

    assert msg and 'no earlier' in msg
    assert [c.name for c in tm.get_all_cues()] == ['Only']
    assert s.get(SRCue, new.id).cue_type is None
