"""sync_links: linked ShowRunner 'Mix' cues mirror a .tmix cue list."""

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from showrunner.models import Cue as SRCue, CueList as SRCueList, Show

from theatremix.models import Cue as TMCue
from theatremix.sync import get_or_create_cue_list, sync_links


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


def _tm(number, point, name):
    return TMCue(number=number, point=point, name=name)


def _links(s, list_id):
    return s.exec(
        select(SRCue)
        .where(SRCue.cue_list_id == list_id)
        .order_by(SRCue.sequence)
    ).all()


def test_list_is_created_once(s):
    show_id = s.info['show_id']
    first = get_or_create_cue_list(s, show_id)
    assert get_or_create_cue_list(s, show_id).id == first.id
    assert s.exec(select(SRCueList)).all() == [first]


def test_creates_linked_mix_cues(s):
    lst = get_or_create_cue_list(s, s.info['show_id'])
    sync_links(s, lst.id, [_tm(1, 0, 'Foreman'), _tm(2, 0, 'Two')])
    links = _links(s, lst.id)
    assert [(c.number, c.point, c.name, c.layer, c.cue_type) for c in links] == [
        ('1', 0, 'Foreman', 'Mix', 'TheatreMix'),
        ('2', 0, 'Two', 'Mix', 'TheatreMix'),
    ]


def test_name_change_updates_in_place_and_keeps_script_line(s):
    lst = get_or_create_cue_list(s, s.info['show_id'])
    tm = _tm(1, 0, 'Old')
    tm._script_line = 42
    sync_links(s, lst.id, [tm])
    row_id = _links(s, lst.id)[0].id

    sync_links(s, lst.id, [_tm(1, 0, 'New')])  # grid edit: no _script_line
    (row,) = _links(s, lst.id)
    assert (row.id, row.name, row.script_line) == (row_id, 'New', 42)


def test_rename_keeps_row_and_script_line(s):
    lst = get_or_create_cue_list(s, s.info['show_id'])
    tm = _tm(2, 10, 'Gamma')
    tm._script_line = 7
    sync_links(s, lst.id, [tm])
    row_id = _links(s, lst.id)[0].id

    sync_links(s, lst.id, [_tm(5, 0, 'Gamma')], renames={(2, 10): (5, 0)})
    (row,) = _links(s, lst.id)
    assert (row.id, row.number, row.point, row.script_line) == (row_id, '5', 0, 7)


def test_orphans_are_deleted_and_other_cues_untouched(s):
    lst = get_or_create_cue_list(s, s.info['show_id'])
    s.add(SRCue(cue_list_id=lst.id, number='9', layer='Sound', name='Playback'))
    sync_links(s, lst.id, [_tm(1, 0, 'A'), _tm(2, 0, 'B')])

    sync_links(s, lst.id, [_tm(2, 0, 'B')])
    names = sorted(c.name for c in _links(s, lst.id))
    assert names == ['B', 'Playback']


def test_generated_script_line_is_set(s):
    lst = get_or_create_cue_list(s, s.info['show_id'])
    tm = _tm(3, 0, 'C')
    tm._script_line = 99
    sync_links(s, lst.id, [tm])
    assert _links(s, lst.id)[0].script_line == 99
