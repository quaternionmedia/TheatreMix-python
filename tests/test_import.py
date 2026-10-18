"""Character and actor imports: script -> profiles, CSV -> actors."""

import pytest

from theatremix.db import TheatreMixDB
from theatremix.models import Actor, Profile
from theatremix.script import get_characters, parse_script
from theatremix.ui import parse_actor_csv

FOUNTAIN = '''Title: Test

INT. ROOM - DAY

ALICE
Hello there!

BOB (V.O.)
Hi Alice!

ALICE
How are you?

CHARLIE & ALICE
Hey everyone!
'''


@pytest.fixture
def db(tmp_path):
    d = TheatreMixDB(str(tmp_path / 'test.tmix'), create_schema=True, init_config=True)
    yield d
    d.close()


def test_script_characters_become_profiles(db):
    names = get_characters(parse_script(FOUNTAIN))
    assert names == ['Alice', 'Bob', 'Charlie']
    assert db.add_named_rows(Profile, [{'name': n} for n in names]) == (3, 0, 0)
    assert [p.name for p in db.get_profiles()] == ['Alice', 'Bob', 'Charlie']


def test_existing_profiles_are_kept_and_not_duplicated(db):
    db.add_row(Profile, name='Alice', channel=5)
    assert db.add_named_rows(Profile, [{'name': 'Alice'}, {'name': 'Bob'}, {'name': 'Bob'}]) == (1, 0, 2)
    alice = db.get_profile_by_name('Alice')
    assert alice.channel == 5  # the existing row is untouched
    assert sorted(p.name for p in db.get_profiles()) == ['Alice', 'Bob']


def test_csv_rows_become_actors(db):
    rows = parse_actor_csv('Name,Channel,Order,Active\nAnn Lee,3,2,yes\nBo Park,,,\n')
    assert db.add_named_rows(Actor, rows) == (2, 0, 0)
    ann = next(a for a in db.list_rows(Actor) if a.name == 'Ann Lee')
    assert (ann.channel, ann.order, ann.active) == (3, 2, 1)
    bo = next(a for a in db.list_rows(Actor) if a.name == 'Bo Park')
    assert (bo.channel, bo.order, bo.active) == (None, 0, 0)
    assert db.add_named_rows(Actor, rows) == (0, 0, 2)  # re-import adds nothing


def test_csv_headers_and_blank_rows():
    rows = parse_actor_csv(' name , Channel \n Ann ,4\n,\n\n')
    assert rows == [{'name': 'Ann', 'channel': 4, 'order': 0, 'active': 0}]


def test_csv_needs_name_column():
    with pytest.raises(ValueError, match="needs a 'name' column"):
        parse_actor_csv('channel,order\n1,2\n')


def test_csv_rejects_non_numeric_channel():
    with pytest.raises(ValueError, match="'channel' must be a whole number: 'x'"):
        parse_actor_csv('name,channel\nAnn,x\n')


def test_overwrite_replaces_listed_fields_only(db):
    db.add_row(Profile, name='Alice', channel=5, label='Old')
    assert db.add_named_rows(Profile, [{'name': 'Alice', 'channel': 9}], overwrite=True) == (0, 1, 0)
    alice = db.get_profile_by_name('Alice')
    assert (alice.channel, alice.label) == (9, 'Old')  # fields not in the row are kept


def test_overwrite_csv_blank_clears_and_repeated_name_applies_in_order(db):
    db.add_row(Actor, name='Ann', channel=3, order=1, active=1)
    rows = parse_actor_csv('name,channel\nAnn,\nAnn,7\nNew,2\n')
    assert db.add_named_rows(Actor, rows, overwrite=True) == (1, 2, 0)
    ann = next(a for a in db.list_rows(Actor) if a.name == 'Ann')
    assert ann.channel == 7
    assert ann.order == 0 and ann.active == 0  # CSV defaults overwrite the stored values


def test_script_overwrite_clears_profile_channel(db):
    db.add_row(Profile, name='Alice', channel=5, label='Lead')
    rows = [{'name': 'Alice', 'channel': None, 'label': None, 'default': 1}]
    assert db.add_named_rows(Profile, rows, overwrite=True) == (0, 1, 0)
    alice = db.get_profile_by_name('Alice')
    assert (alice.channel, alice.label, alice.default) == (None, None, 1)


def test_long_names_are_stored_truncated(db):
    from theatremix.script import tm_name
    assert db.add_named_rows(Profile, [{'name': tm_name('Mrs Bennet Senior'), 'channel': None}]) == (1, 0, 0)
    assert [p.name for p in db.get_profiles()] == ['Mrs Bennet S']


PATCH = '''Channel,Actor,Character,Order,Active
1,Ann Lee,Alice,2,yes
2,Bo Park,Bob (V.O.),,
3,Ann Lee,Cassandra Bellweather,3,
,Cy Dane,,1,y
'''


def test_patch_list_populates_actors_profiles_and_links(db):
    from theatremix.models import ActorProfile
    from theatremix.ui import parse_patch_csv

    rows = parse_patch_csv(PATCH)
    assert rows[1]['profile'] == 'Bob (V.O.)'[:12] and rows[2]['profile'] == 'Cassandra Be'
    result = db.import_patch(rows)
    assert result == {'actors': (3, 0, 1), 'profiles': (3, 0, 0), 'links': (3, 0)}

    ann = next(a for a in db.list_rows(Actor) if a.name == 'Ann Lee')
    assert (ann.channel, ann.order, ann.active) == (1, 2, 1)  # first row defines the actor
    alice = db.get_profile_by_name('Alice')
    assert alice.channel == 1
    with db.engine.connect() as conn:
        links = conn.exec_driver_sql('select actor, profile from actorProfiles').all()
    assert len(links) == 3


def test_patch_list_reimport_adds_nothing_and_overwrite_updates(db):
    from theatremix.ui import parse_patch_csv

    db.import_patch(parse_patch_csv(PATCH))
    again = db.import_patch(parse_patch_csv(PATCH))
    assert again['links'] == (0, 3) and again['profiles'] == (0, 0, 3)
    changed = parse_patch_csv('Channel,Actor,Character\n9,Ann Lee,Alice\n')
    db.import_patch(changed, overwrite=True)
    assert db.get_profile_by_name('Alice').channel == 9


def test_patch_list_needs_actor_and_character_columns():
    from theatremix.ui import parse_patch_csv

    with pytest.raises(ValueError, match="needs a 'character' column"):
        parse_patch_csv('Channel,Actor\n1,Ann\n')


def test_patch_channel_written_to_existing_rows(db):
    from theatremix.ui import parse_patch_csv

    db.add_row(Actor, name='Ann Lee')
    db.add_row(Profile, name='Alice')
    db.add_row(Profile, name='Bob', channel=7)
    db.import_patch(parse_patch_csv('Channel,Actor,Character\n1,Ann Lee,Alice\n2,Ann Lee,Bob\n'))
    assert next(a for a in db.list_rows(Actor) if a.name == 'Ann Lee').channel == 1
    assert db.get_profile_by_name('Alice').channel == 1
    assert db.get_profile_by_name('Bob').channel == 2  # patch channel written even without overwrite


def test_csv_with_byte_order_mark_still_reads_channel():
    from theatremix.ui import parse_actor_csv, parse_patch_csv

    assert parse_patch_csv('\ufeff' + PATCH)[0]['channel'] == 1
    assert parse_actor_csv('\ufeffName,Channel\nAnn,4\n') == [
        {'name': 'Ann', 'channel': 4, 'order': 0, 'active': 0}]
