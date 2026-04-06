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
def setup_plugin(mock_app, tmix_db):
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


# ---------------------------------------------------------------------------
# Tests: Command — generate-dca
# ---------------------------------------------------------------------------


class TestCmdGenerateDca:
    def test_generates_cues_and_writes_to_cuelist(self, setup_plugin, sr_db):
        result = plugin.showrunner_command(
            command_name='theatremix:generate-dca',
            script_id=1,
            lookahead=7,
            layer='Sound',
        )
        assert result is not None
        assert result['cues_created'] > 0
        assert result['layer'] == 'Sound'
        assert result['script_title'] == 'Test Script'
        assert 'cue_list_id' in result

        # Verify cues were written to ShowRunner DB
        with sr_db.session() as s:
            cues = s.exec(
                select(SRCue).where(SRCue.cue_list_id == result['cue_list_id'])
            ).all()
            assert len(cues) == result['cues_created']
            assert all(c.layer == 'Sound' for c in cues)
            assert all(c.cue_type == 'DCA' for c in cues)

    def test_invalid_layer_returns_error(self, setup_plugin):
        result = plugin.showrunner_command(
            command_name='theatremix:generate-dca',
            script_id=1,
            layer='Invalid',
        )
        assert 'error' in result

    def test_missing_script_id_returns_error(self, setup_plugin):
        result = plugin.showrunner_command(
            command_name='theatremix:generate-dca',
            layer='Sound',
        )
        assert 'error' in result

    def test_nonexistent_script_returns_error(self, setup_plugin):
        result = plugin.showrunner_command(
            command_name='theatremix:generate-dca',
            script_id=999,
            layer='Sound',
        )
        assert 'error' in result

    def test_regenerate_clears_old_cues(self, setup_plugin, sr_db):
        # Generate once
        r1 = plugin.showrunner_command(
            command_name='theatremix:generate-dca',
            script_id=1,
            lookahead=7,
            layer='Sound',
        )
        cue_list_id = r1['cue_list_id']
        count1 = r1['cues_created']

        # Generate again — should reuse same cue list, clear old cues
        r2 = plugin.showrunner_command(
            command_name='theatremix:generate-dca',
            script_id=1,
            lookahead=7,
            layer='Sound',
        )
        assert r2['cue_list_id'] == cue_list_id

        # Total cues should equal second run only, not accumulated
        with sr_db.session() as s:
            cues = s.exec(select(SRCue).where(SRCue.cue_list_id == cue_list_id)).all()
            assert len(cues) == r2['cues_created']

    def test_different_layers_get_separate_cuelists(self, setup_plugin, sr_db):
        r_sound = plugin.showrunner_command(
            command_name='theatremix:generate-dca',
            script_id=1,
            layer='Sound',
        )
        r_lights = plugin.showrunner_command(
            command_name='theatremix:generate-dca',
            script_id=1,
            layer='Lights',
        )
        assert r_sound['cue_list_id'] != r_lights['cue_list_id']


# ---------------------------------------------------------------------------
# Tests: Command — scripts
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
