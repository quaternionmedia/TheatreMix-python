"""TheatreMix plugin for ShowRunner — DCA cue generation and mixer database management."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

import showrunner

router = APIRouter(prefix='/theatremix', tags=['TheatreMix'])

_db = None  # TheatreMixDB instance, set during startup
_config: dict = {}


@router.get('/')
async def index():
    return {'plugin': 'TheatreMix', 'status': 'ok'}


@router.get('/cues')
async def list_cues():
    if _db is None:
        raise HTTPException(status_code=503, detail='TheatreMix database not loaded')
    cues = _db.get_all_cues()
    return [cue.model_dump() for cue in cues]


@router.get('/profiles')
async def list_profiles():
    if _db is None:
        raise HTTPException(status_code=503, detail='TheatreMix database not loaded')
    profiles = _db.get_profiles()
    return [p.model_dump() for p in profiles]


@router.get('/characters')
async def list_characters():
    from .script import get_characters, open_script

    script_path = _config.get('script')
    if not script_path:
        raise HTTPException(status_code=400, detail='No script path configured')
    path = Path(script_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f'Script not found: {script_path}')
    script = open_script(str(path))
    return get_characters(script)


@router.post('/generate')
async def generate_cues():
    """Generate DCA cues from the configured Fountain script and write to the database."""
    from .dca import generate_dca_cues
    from .script import open_script

    script_path = _config.get('script')
    if not script_path:
        raise HTTPException(status_code=400, detail='No script path configured')
    if _db is None:
        raise HTTPException(status_code=503, detail='TheatreMix database not loaded')

    path = Path(script_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f'Script not found: {script_path}')

    script = open_script(str(path))
    lookahead = int(_config.get('lookahead', 7))
    cues = generate_dca_cues(script, str(_db.db_path), max_dialogues_ahead=lookahead)
    return {'cues_generated': len(cues)}


def _open_database(db_path: str):
    """Open a TheatreMix database, importing TheatreMixDB lazily."""
    from .db import TheatreMixDB

    return TheatreMixDB(db_path, create_schema=False, init_config=False)


class TheatreMixPlugin:
    """DCA cue generation and mixer database management for theatrical productions.

    Parses Fountain scripts to generate automatic DCA muting cues and manages
    character-to-channel mappings via TheatreMix (.tmix) databases.

    Configure in show.toml:
        [plugins.theatremix]
        database = "mix/show.tmix"
        script = "scripts/show.fountain"
        lookahead = 7
    """

    @showrunner.hookimpl
    def showrunner_register(self):
        return {
            'name': 'TheatreMix',
            'description': 'DCA cue generation and mixer database management',
            'version': '0.1.0',
        }

    @showrunner.hookimpl
    def showrunner_startup(self, app):
        global _db, _config
        config = getattr(app, 'config', None)
        if config is not None:
            _config = config.plugins.settings.get('theatremix', {})

        db_path = _config.get('database')
        if db_path:
            path = Path(db_path)
            if path.is_file():
                _db = _open_database(str(path))

    @showrunner.hookimpl
    def showrunner_shutdown(self, app):
        global _db
        if _db is not None:
            _db.close()
            _db = None

    @showrunner.hookimpl
    def showrunner_get_routes(self):
        return router

    @showrunner.hookimpl
    def showrunner_get_commands(self):
        return [
            {
                'name': 'theatremix:generate',
                'description': 'Generate DCA cues from Fountain script',
            },
            {
                'name': 'theatremix:characters',
                'description': 'List characters found in Fountain script',
            },
        ]

    @showrunner.hookimpl
    def showrunner_command(self, command_name: str, **kwargs):
        if command_name == 'theatremix:generate':
            return self._cmd_generate()
        if command_name == 'theatremix:characters':
            return self._cmd_characters()
        return None

    @showrunner.hookimpl
    def showrunner_config_changed(self, config, previous_config):
        global _db, _config
        new_settings = config.plugins.settings.get('theatremix', {})
        old_db = _config.get('database')
        new_db = new_settings.get('database')

        _config = new_settings

        if new_db != old_db:
            if _db is not None:
                _db.close()
                _db = None
            if new_db:
                path = Path(new_db)
                if path.is_file():
                    _db = _open_database(str(path))

    @showrunner.hookimpl
    def showrunner_get_nav(self):
        return {
            'label': 'TheatreMix',
            'path': '/theatremix',
            'icon': 'mic',
            'order': 50,
        }

    @showrunner.hookimpl
    def showrunner_get_status(self):
        connected = _db is not None
        return {
            'icon': 'mic' if connected else 'mic_off',
            'tooltip': (
                'TheatreMix: connected' if connected else 'TheatreMix: no database'
            ),
            'color': 'green' if connected else 'grey',
        }

    def _cmd_generate(self):
        from .dca import generate_dca_cues
        from .script import open_script

        script_path = _config.get('script')
        if not script_path:
            return {'error': 'No script path configured in [plugins.theatremix]'}
        if _db is None:
            return {'error': 'TheatreMix database not loaded'}

        path = Path(script_path)
        if not path.is_file():
            return {'error': f'Script not found: {script_path}'}

        script = open_script(str(path))
        lookahead = int(_config.get('lookahead', 7))
        cues = generate_dca_cues(
            script, str(_db.db_path), max_dialogues_ahead=lookahead
        )
        return {'cues_generated': len(cues)}

    def _cmd_characters(self):
        from .script import get_characters, open_script

        script_path = _config.get('script')
        if not script_path:
            return {'error': 'No script path configured in [plugins.theatremix]'}

        path = Path(script_path)
        if not path.is_file():
            return {'error': f'Script not found: {script_path}'}

        script = open_script(str(path))
        return {'characters': get_characters(script)}


plugin = TheatreMixPlugin()
