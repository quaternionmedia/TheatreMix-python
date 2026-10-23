"""Tests for TheatreMix ShowRunner plugin."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from showrunner.models import (
    Cue as SRCue,
    CueList as SRCueList,
    Script as SRScript,
    Show,
)

from theatremix.showrunner import (
    GenerateDCARequest,
    TheatreMixPlugin,
    _format_dca_notes,
    _get_current_show_id,
    _get_showrunner_db,
    _load_showrunner_script,
    plugin,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FOUNTAIN_TEXT = '''\
Title: Test Show

# ACT I
[[Page 1]]

INT. ROOM - DAY

ALICE
Hello there!

BOB
Hi Alice!

ALICE
How are you?

BOB
Fine, thanks!

CHARLIE
Hey everyone!
'''


@pytest.fixture
def sr_db(tmp_path):
    """Create a temporary ShowRunner database with a show and fountain script."""
    db_path = tmp_path / 'show.db'
    engine = create_engine(f'sqlite:///{db_path}')
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        show = Show(name='Test Show')
        s.add(show)
        s.commit()
        s.refresh(show)

        script = SRScript(
            show_id=show.id,
            title='Test Script',
            format='fountain',
            content=FOUNTAIN_TEXT,
        )
        s.add(script)

        non_fountain = SRScript(
            show_id=show.id,
            title='PDF Script',
            format='pdf',
            content='binary data',
        )
        s.add(non_fountain)
        s.commit()

    # Return a mock that behaves like ShowDatabase
    mock_db = MagicMock()
    mock_db.session.return_value = Session(engine)
    # Make session() usable as context manager
    mock_db.session = lambda: Session(engine)
    mock_db.db_path = db_path
    mock_db.engine = engine
    return mock_db


@pytest.fixture
def tmix_db(tmp_path):
    """Create a TheatreMix database with character profiles."""
    from theatremix.db import TheatreMixDB

    db_path = tmp_path / 'test.tmix'
    db = TheatreMixDB(str(db_path), create_schema=True, init_config=True)

    from sqlalchemy.orm import Session as SASession

    from theatremix.models import Profile

    with SASession(db.engine) as s:
        for i, name in enumerate(['Alice', 'Bob', 'Charlie'], start=1):
            p = Profile(name=name, channel=str(i))
            s.add(p)
        s.commit()

    return db


@pytest.fixture
def mock_app(sr_db):
    """Mock ShowRunner app with db and config."""
    app = MagicMock()
    app.db = sr_db
    app.config.current_show = 1
    app.config.plugins.settings = {'theatremix': {}}
    return app


@pytest.fixture
def layer_pm(mock_app):
    """A real plugin manager with TheatreMix registered, so its layer type is known to ShowRunner."""
    import pluggy
    from showrunner.hookspecs import ShowRunnerSpec
    import theatremix.showrunner as sr_mod
    pm = pluggy.PluginManager('showrunner')
    pm.add_hookspecs(ShowRunnerSpec)
    pm.register(sr_mod.plugin)
    mock_app.pm = pm
    return pm


@pytest.fixture
def setup_plugin(mock_app, tmix_db, layer_pm):
    """Configure the plugin module globals for testing."""
    import theatremix.showrunner as sr_mod

    old_db = sr_mod._db
    old_app = sr_mod._app
    old_config = sr_mod._config

    sr_mod._app = mock_app
    sr_mod._db = tmix_db
    sr_mod._config = {}

    yield

    sr_mod._db = old_db
    sr_mod._app = old_app
    sr_mod._config = old_config


# ---------------------------------------------------------------------------
# Tests: _format_dca_notes
# ---------------------------------------------------------------------------


class TestFormatDcaNotes:
    def test_empty_cue(self):
        from theatremix.models import Cue

        cue = Cue(number=1, name='test')
        assert _format_dca_notes(cue) == ''

    def test_label_only(self):
        from theatremix.models import Cue

        cue = Cue(number=1, name='test', dca01Label='Alice')
        assert _format_dca_notes(cue) == 'DCA1: Alice'

    def test_label_and_channels(self):
        from theatremix.models import Cue

        cue = Cue(number=1, name='test', dca01Label='Alice', dca01Channels='1')
        assert _format_dca_notes(cue) == 'DCA1: Alice (ch 1)'

    def test_multiple_dcas(self):
        from theatremix.models import Cue

        cue = Cue(number=1, name='test', dca01Label='Alice', dca02Label='Bob')
        result = _format_dca_notes(cue)
        assert 'DCA1: Alice' in result
        assert 'DCA2: Bob' in result
        assert '; ' in result


# ---------------------------------------------------------------------------
# Tests: _load_showrunner_script
# ---------------------------------------------------------------------------


class TestLoadShowrunnerScript:
    def test_loads_valid_script(self, setup_plugin):
        script = _load_showrunner_script(1)
        assert script is not None
        assert len(script.elements) > 0

    def test_not_found_raises_404(self, setup_plugin):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _load_showrunner_script(999)
        assert exc_info.value.status_code == 404

    def test_non_fountain_raises_400(self, setup_plugin):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _load_showrunner_script(2)  # PDF script
        assert exc_info.value.status_code == 400
        assert 'not fountain' in exc_info.value.detail


# ---------------------------------------------------------------------------
# Tests: _get_showrunner_db / _get_current_show_id
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_get_db_no_app_raises_503(self):
        import theatremix.showrunner as sr_mod

        old = sr_mod._app
        sr_mod._app = None
        try:
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                _get_showrunner_db()
            assert exc_info.value.status_code == 503
        finally:
            sr_mod._app = old

    def test_get_show_id_no_config_raises_400(self):
        import theatremix.showrunner as sr_mod

        old = sr_mod._app
        sr_mod._app = MagicMock()
        sr_mod._app.config = None
        try:
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                _get_current_show_id()
            assert exc_info.value.status_code == 400
        finally:
            sr_mod._app = old

    def test_get_show_id_returns_id(self, setup_plugin):
        assert _get_current_show_id() == 1


# ---------------------------------------------------------------------------
# Tests: Plugin class registration
# ---------------------------------------------------------------------------


class TestPluginRegistration:
    def test_register_returns_metadata(self):
        info = plugin.showrunner_register()
        assert info['name'] == 'TheatreMix'
        assert 'version' in info

    def test_get_routes_returns_router(self):
        routes = plugin.showrunner_get_routes()
        assert routes is not None

    def test_get_commands_returns_list(self):
        cmds = plugin.showrunner_get_commands()
        names = [c['name'] for c in cmds]
        assert 'theatremix:generate-dca' in names
        assert 'theatremix:scripts' in names
        assert 'theatremix:characters' in names
        assert 'theatremix:cuelists' in names


# ---------------------------------------------------------------------------
# Tests: Command — generate-dca
# ---------------------------------------------------------------------------


class TestCmdGenerateDca:
    def test_writes_tmix_and_links_cues(self, setup_plugin, sr_db, tmix_db):
        result = plugin.showrunner_command(
            command_name='theatremix:generate-dca', script_id=1, lookahead=7
        )
        assert result['cues_created'] > 0
        assert result['script_title'] == 'Test Script'

        # .tmix is the source of truth and is backed up first
        assert len(tmix_db.get_all_cues()) == result['cues_created']
        assert tmix_db.db_path.with_name('test.tmix.bak').exists()

        # ShowRunner gets one linked 'Mix' cue per .tmix cue
        with sr_db.session() as s:
            links = s.exec(
                select(SRCue).where(SRCue.cue_list_id == result['cue_list_id'])
            ).all()
        assert len(links) == result['cues_created']
        assert all(c.layer == 'Mix' and c.cue_type == 'TheatreMix' for c in links)
        assert all(c.script_line is not None for c in links)

    def test_regenerate_replaces_not_appends(self, setup_plugin, sr_db, tmix_db):
        r1 = plugin.showrunner_command(command_name='theatremix:generate-dca', script_id=1)
        r2 = plugin.showrunner_command(command_name='theatremix:generate-dca', script_id=1)
        assert r2['cue_list_id'] == r1['cue_list_id']
        assert len(tmix_db.get_all_cues()) == r2['cues_created']
        with sr_db.session() as s:
            links = s.exec(
                select(SRCue).where(SRCue.cue_list_id == r1['cue_list_id'])
            ).all()
        assert len(links) == r2['cues_created']

    def test_generate_into_existing_cuelist(self, setup_plugin, sr_db):
        with sr_db.session() as s:
            cl = SRCueList(show_id=1, name='Main')
            s.add(cl)
            s.commit()
            s.refresh(cl)
            cl_id = cl.id
        result = plugin.showrunner_command(
            command_name='theatremix:generate-dca', script_id=1, cue_list_id=cl_id
        )
        assert result['cue_list_id'] == cl_id
        with sr_db.session() as s:
            links = s.exec(select(SRCue).where(SRCue.cue_list_id == cl_id)).all()
        assert len(links) == result['cues_created']

    def test_nonexistent_cuelist_leaves_tmix_untouched(self, setup_plugin, tmix_db):
        tmix_db.add_cue('Keep')
        result = plugin.showrunner_command(
            command_name='theatremix:generate-dca', script_id=1, cue_list_id=999
        )
        assert result == {'error': 'Cue list 999 not found'}
        assert [c.name for c in tmix_db.get_all_cues()] == ['Keep']

    def test_missing_script_id_returns_error(self, setup_plugin):
        result = plugin.showrunner_command(command_name='theatremix:generate-dca')
        assert result == {'error': 'script_id is required'}

    def test_nonexistent_script_returns_error(self, setup_plugin):
        result = plugin.showrunner_command(
            command_name='theatremix:generate-dca', script_id=999
        )
        assert result == {'error': 'Script 999 not found'}

    def test_no_tmix_database_returns_error(self, setup_plugin):
        import theatremix.showrunner as sr_mod

        sr_mod._db = None
        result = plugin.showrunner_command(command_name='theatremix:generate-dca', script_id=1)
        assert result == {'error': 'TheatreMix database not loaded'}


# ---------------------------------------------------------------------------
class TestCmdScripts:
    def test_lists_only_fountain_scripts(self, setup_plugin):
        result = plugin.showrunner_command(command_name='theatremix:scripts')
        scripts = result['scripts']
        assert len(scripts) == 1
        assert scripts[0]['title'] == 'Test Script'

    def test_no_app_returns_error(self):
        import theatremix.showrunner as sr_mod

        old = sr_mod._app
        sr_mod._app = None
        try:
            result = plugin.showrunner_command(command_name='theatremix:scripts')
            assert 'error' in result
        finally:
            sr_mod._app = old


# ---------------------------------------------------------------------------
# Tests: Command — characters
# ---------------------------------------------------------------------------


class TestCmdCharacters:
    def test_extracts_characters_from_script(self, setup_plugin):
        result = plugin.showrunner_command(
            command_name='theatremix:characters', script_id=1
        )
        chars = result['characters']
        assert 'Alice' in chars
        assert 'Bob' in chars
        assert 'Charlie' in chars

    def test_no_script_or_path_returns_error(self, setup_plugin):
        result = plugin.showrunner_command(command_name='theatremix:characters')
        assert 'error' in result


# ---------------------------------------------------------------------------
# Tests: Command — cuelists
# ---------------------------------------------------------------------------


class TestCmdCuelists:
    def test_lists_cuelists_for_show(self, setup_plugin, sr_db):
        # Create a couple of cue lists
        with sr_db.session() as s:
            s.add(SRCueList(show_id=1, name='Main'))
            s.add(SRCueList(show_id=1, name='DCA'))
            s.commit()

        result = plugin.showrunner_command(command_name='theatremix:cuelists')
        names = [cl['name'] for cl in result['cue_lists']]
        assert 'Main' in names
        assert 'DCA' in names

    def test_empty_when_no_cuelists(self, setup_plugin):
        result = plugin.showrunner_command(command_name='theatremix:cuelists')
        assert result['cue_lists'] == []

    def test_no_app_returns_error(self):
        import theatremix.showrunner as sr_mod

        old = sr_mod._app
        sr_mod._app = None
        try:
            result = plugin.showrunner_command(command_name='theatremix:cuelists')
            assert 'error' in result
        finally:
            sr_mod._app = old


class TestGenerateDestination:
    """Generate writes to the chosen cue list and layer, remembers it, and moves old links."""

    def _new_list(self, sr_db, name):
        with sr_db.session() as s:
            cl = SRCueList(show_id=1, name=name)
            s.add(cl)
            s.commit()
            s.refresh(cl)
            return cl.id

    def _links(self, sr_db, list_id, layer):
        with sr_db.session() as s:
            return s.exec(select(SRCue).where(SRCue.cue_list_id == list_id, SRCue.layer == layer)).all()

    def test_choice_is_used_remembered_and_old_links_removed(self, setup_plugin, sr_db, tmix_db):
        first = plugin.showrunner_command(command_name='theatremix:generate-dca', script_id=1)
        lights = self._new_list(sr_db, 'Lights')
        r = plugin.showrunner_command(
            command_name='theatremix:generate-dca', script_id=1, cue_list_id=lights, layer='Lights')
        assert (r['cue_list_id'], r['layer']) == (lights, 'Lights')
        assert len(self._links(sr_db, lights, 'Lights')) == r['cues_created']
        assert self._links(sr_db, first['cue_list_id'], 'Mix') == []  # old destination cleaned up

        again = plugin.showrunner_command(command_name='theatremix:generate-dca', script_id=1)
        assert (again['cue_list_id'], again['layer']) == (lights, 'Lights')

    def test_destination_options_lists_show_cue_lists_and_layers(self, setup_plugin, sr_db):
        self._new_list(sr_db, 'Lights')
        import theatremix.showrunner as sr_mod
        opts = sr_mod.destination_options()
        assert 'Lights' in opts['cue_lists'].values()
        assert opts['layer'] == 'Mix' and 'Mix' in opts['layers']


class TestLayerRow:
    """Generating onto a layer adds that layer to ShowRunner's layers table."""

    pytestmark = pytest.mark.skipif(
        not hasattr(__import__('showrunner.models', fromlist=['x']), 'Layer'),
        reason='needs a ShowRunner with a layers table',
    )

    def test_generate_adds_missing_layer_row(self, setup_plugin, sr_db):
        from showrunner.models import Layer as SRLayer
        r = plugin.showrunner_command(command_name='theatremix:generate-dca', script_id=1, layer='Mix')
        with sr_db.session() as s:
            rows = s.exec(select(SRLayer).where(SRLayer.show_id == 1, SRLayer.name == 'Mix')).all()
        assert len(rows) == 1 and rows[0].color == 'pink' and rows[0].type == 'TheatreMix'
        assert r['layer'] == 'Mix'

    def test_existing_mix_layer_switches_to_mix_type(self, setup_plugin, sr_db):
        from showrunner.models import Layer as SRLayer
        from showrunner.layers import add_layer
        with sr_db.session() as s:
            add_layer(s, 1, 'Mix', 'generic', 'pink')
        plugin.showrunner_command(command_name='theatremix:generate-dca', script_id=1, layer='Mix')
        with sr_db.session() as s:
            assert s.exec(select(SRLayer).where(SRLayer.name == 'Mix')).one().type == 'TheatreMix'

    def test_existing_layer_row_not_duplicated(self, setup_plugin, sr_db):
        from showrunner.models import Layer as SRLayer
        from showrunner.layers import add_layer
        with sr_db.session() as s:
            add_layer(s, 1, 'Lights', 'lights', 'orange')
        plugin.showrunner_command(command_name='theatremix:generate-dca', script_id=1, layer='Lights')
        plugin.showrunner_command(command_name='theatremix:generate-dca', script_id=1, layer='Lights')
        with sr_db.session() as s:
            rows = s.exec(select(SRLayer).where(SRLayer.show_id == 1, SRLayer.name == 'Lights')).all()
        assert len(rows) == 1 and rows[0].color == 'orange'
