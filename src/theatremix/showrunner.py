"""TheatreMix plugin for ShowRunner — DCA cue generation and mixer database management."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select as sr_select

import showrunner

from .db import TheatreMixDB
from .dca import generate_dca_cues
from .script import get_characters, open_script, parse_script

router = APIRouter(prefix='/theatremix', tags=['TheatreMix'])

_db: TheatreMixDB | None = None  # TheatreMix .tmix database
_app: Any = None  # ShowRunner app instance (provides app.db, app.config)
_config: dict = {}

VALID_LAYERS = ('Lights', 'Sound', 'Video', 'Audio', 'Stage')


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class GenerateDCARequest(BaseModel):
    script_id: int
    lookahead: int = 7
    layer: str = 'Sound'
    cue_list_id: int | None = None


class GenerateDCAReport(BaseModel):
    script_title: str
    layer: str
    lookahead: int
    cue_list_id: int
    cues_created: int
    cues: list[dict]
    errors: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_showrunner_db():
    """Return the ShowRunner database, or raise 503."""
    if _app is None:
        raise HTTPException(status_code=503, detail='ShowRunner app not available')
    sr_db = getattr(_app, 'db', None)
    if sr_db is None:
        raise HTTPException(status_code=503, detail='ShowRunner database not loaded')
    return sr_db


def _get_current_show_id() -> int:
    """Return the current show ID from ShowRunner config."""
    config = getattr(_app, 'config', None)
    show_id = getattr(config, 'current_show', None) if config else None
    if show_id is None:
        raise HTTPException(status_code=400, detail='No current show configured')
    return show_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


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


@router.get('/cuelists')
async def list_cuelists():
    """List available cue lists from the ShowRunner database."""
    from showrunner.models import CueList as SRCueList

    sr_db = _get_showrunner_db()
    show_id = _get_current_show_id()

    with sr_db.session() as s:
        cue_lists = s.exec(
            sr_select(SRCueList).where(SRCueList.show_id == show_id)
        ).all()

    return [
        {
            'id': cl.id,
            'name': cl.name,
            'description': cl.description,
        }
        for cl in cue_lists
    ]


@router.get('/scripts')
async def list_scripts():
    """List available Fountain scripts from the ShowRunner database."""
    from showrunner.models import Script as SRScript

    sr_db = _get_showrunner_db()
    show_id = _get_current_show_id()

    with sr_db.session() as s:
        scripts = s.exec(
            sr_select(SRScript).where(
                SRScript.show_id == show_id,
                SRScript.format == 'fountain',
            )
        ).all()

    return [
        {
            'id': sc.id,
            'title': sc.title,
            'format': sc.format,
            'has_content': sc.content is not None and len(sc.content) > 0,
        }
        for sc in scripts
    ]


@router.get('/characters')
async def list_characters(
    script_id: int | None = Query(default=None, description='ShowRunner script ID'),
):
    """List characters from a Fountain script.

    If script_id is provided, reads from ShowRunner database.
    Otherwise falls back to the configured file path.
    """
    if script_id is not None:
        script = _load_showrunner_script(script_id)
    else:
        script_path = _config.get('script')
        if not script_path:
            raise HTTPException(
                status_code=400, detail='No script path or script_id provided'
            )
        path = Path(script_path)
        if not path.is_file():
            raise HTTPException(
                status_code=404, detail=f'Script not found: {script_path}'
            )
        script = open_script(str(path))

    return get_characters(script)


@router.post('/generate-dca', response_model=GenerateDCAReport)
async def generate_dca(body: GenerateDCARequest):
    """Generate DCA muting cues from a ShowRunner script and write to a cue list."""
    errors: list[str] = []

    # Validate layer
    if body.layer not in VALID_LAYERS:
        raise HTTPException(
            status_code=400,
            detail=f'Invalid layer {body.layer!r}. Must be one of: {", ".join(VALID_LAYERS)}',
        )

    if _db is None:
        raise HTTPException(status_code=503, detail='TheatreMix database not loaded')

    # Load and parse the Fountain script from ShowRunner DB
    script = _load_showrunner_script(body.script_id)
    script_title = _get_showrunner_script_title(body.script_id)

    # Generate DCA cues using TheatreMix logic
    dca_cues = generate_dca_cues(
        script, str(_db.db_path), max_dialogues_ahead=body.lookahead
    )

    if not dca_cues:
        return GenerateDCAReport(
            script_title=script_title,
            layer=body.layer,
            lookahead=body.lookahead,
            cue_list_id=0,
            cues_created=0,
            cues=[],
            errors=[
                'No DCA cues generated — check that the script has character dialogue'
            ],
        )

    # Write cues to ShowRunner's cue list
    from showrunner.models import Cue as SRCue, CueList as SRCueList

    sr_db = _get_showrunner_db()
    show_id = _get_current_show_id()

    with sr_db.session() as s:
        # Use specified cue list or find/create one by convention
        if body.cue_list_id is not None:
            cue_list = s.get(SRCueList, body.cue_list_id)
            if cue_list is None:
                raise HTTPException(
                    status_code=404,
                    detail=f'Cue list {body.cue_list_id} not found',
                )
        else:
            cue_list = s.exec(
                sr_select(SRCueList).where(
                    SRCueList.show_id == show_id,
                    SRCueList.name == f'TheatreMix DCA ({body.layer})',
                )
            ).first()

            if cue_list is None:
                cue_list = SRCueList(
                    show_id=show_id,
                    name=f'TheatreMix DCA ({body.layer})',
                    description=f'Auto-generated DCA muting cues for {body.layer} layer',
                )
                s.add(cue_list)
                s.commit()
                s.refresh(cue_list)

        # Determine sequence offset so new cues append after existing ones
        max_seq = s.exec(
            sr_select(SRCue.sequence)
            .where(SRCue.cue_list_id == cue_list.id)
            .order_by(SRCue.sequence.desc())
        ).first()
        seq_offset = (max_seq + 1) if max_seq is not None else 0

        # Convert TheatreMix Cues to ShowRunner Cues
        created = []
        for seq, tm_cue in enumerate(dca_cues, start=seq_offset):
            sr_cue = SRCue(
                cue_list_id=cue_list.id,
                number=tm_cue.number,
                point=tm_cue.point,
                name=tm_cue.name,
                layer=body.layer,
                cue_type='DCA',
                notes=_format_dca_notes(tm_cue),
                sequence=seq,
            )
            s.add(sr_cue)
            created.append(sr_cue)

        s.commit()

        # Build report after commit so IDs are populated
        for c in created:
            s.refresh(c)

        cue_dicts = [
            {
                # 'id': c.id,
                'number': c.number,
                'point': c.point,
                'name': c.name,
                'layer': c.layer,
                'notes': c.notes,
            }
            for c in created
        ]

        cue_list_id = cue_list.id

    return GenerateDCAReport(
        script_title=script_title,
        layer=body.layer,
        lookahead=body.lookahead,
        cue_list_id=cue_list_id,
        cues_created=len(created),
        cues=cue_dicts,
        errors=errors,
    )


def _load_showrunner_script(script_id: int):
    """Load a Fountain script from ShowRunner DB and parse it."""
    from showrunner.models import Script as SRScript

    sr_db = _get_showrunner_db()

    with sr_db.session() as s:
        sr_script = s.get(SRScript, script_id)

    if sr_script is None:
        raise HTTPException(status_code=404, detail=f'Script {script_id} not found')
    if sr_script.format != 'fountain':
        raise HTTPException(
            status_code=400,
            detail=f'Script {script_id} is {sr_script.format!r}, not fountain',
        )
    if not sr_script.content:
        raise HTTPException(
            status_code=400,
            detail=f'Script {script_id} has no content',
        )

    return parse_script(sr_script.content)


def _get_showrunner_script_title(script_id: int) -> str:
    """Get the title of a ShowRunner script."""
    from showrunner.models import Script as SRScript

    sr_db = _get_showrunner_db()
    with sr_db.session() as s:
        sr_script = s.get(SRScript, script_id)
    return sr_script.title if sr_script else f'Script {script_id}'


def _format_dca_notes(tm_cue) -> str:
    """Format TheatreMix DCA assignments as a readable notes string."""
    parts = []
    for i in range(1, 13):
        label = getattr(tm_cue, f'dca{i:02d}Label', None)
        channels = getattr(tm_cue, f'dca{i:02d}Channels', None)
        if label or channels:
            entry = f'DCA{i}: {label or "?"}'
            if channels:
                entry += f' (ch {channels})'
            parts.append(entry)
    return '; '.join(parts) if parts else ''


# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------


def _open_database(db_path: str):
    """Open a TheatreMix database."""
    return TheatreMixDB(db_path, create_schema=False, init_config=False)


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


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
        global _db, _app, _config
        _app = app
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
        global _db, _app
        if _db is not None:
            _db.close()
            _db = None
        _app = None

    @showrunner.hookimpl
    def showrunner_get_routes(self):
        return router

    @showrunner.hookimpl
    def showrunner_get_commands(self):
        return [
            {
                'name': 'theatremix:generate-dca',
                'description': 'Generate DCA cues from a ShowRunner Fountain script',
            },
            {
                'name': 'theatremix:scripts',
                'description': 'List available Fountain scripts',
            },
            {
                'name': 'theatremix:characters',
                'description': 'List characters found in a Fountain script',
            },
            {
                'name': 'theatremix:cuelists',
                'description': 'List available cue lists for the current show',
            },
        ]

    @showrunner.hookimpl
    def showrunner_command(self, command_name: str, **kwargs):
        if command_name == 'theatremix:generate-dca':
            return self._cmd_generate_dca(**kwargs)
        if command_name == 'theatremix:scripts':
            return self._cmd_scripts()
        if command_name == 'theatremix:characters':
            return self._cmd_characters(**kwargs)
        if command_name == 'theatremix:cuelists':
            return self._cmd_cuelists()
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

    # -- Command implementations ----------------------------------------------

    def _cmd_scripts(self):
        from showrunner.models import Script as SRScript

        sr_db = getattr(_app, 'db', None)
        if sr_db is None:
            return {'error': 'ShowRunner database not loaded'}

        config = getattr(_app, 'config', None)
        show_id = getattr(config, 'current_show', None) if config else None
        if show_id is None:
            return {'error': 'No current show configured'}

        with sr_db.session() as s:
            scripts = s.exec(
                sr_select(SRScript).where(
                    SRScript.show_id == show_id,
                    SRScript.format == 'fountain',
                )
            ).all()

        return {'scripts': [{'id': sc.id, 'title': sc.title} for sc in scripts]}

    def _cmd_characters(self, script_id: int | None = None, **_kwargs):
        if script_id is not None:
            script = _load_showrunner_script(script_id)
        else:
            script_path = _config.get('script')
            if not script_path:
                return {'error': 'No script_id or script path configured'}
            path = Path(script_path)
            if not path.is_file():
                return {'error': f'Script not found: {script_path}'}
            script = open_script(str(path))

        return {'characters': get_characters(script)}

    def _cmd_cuelists(self):
        from showrunner.models import CueList as SRCueList

        sr_db = getattr(_app, 'db', None)
        if sr_db is None:
            return {'error': 'ShowRunner database not loaded'}

        config = getattr(_app, 'config', None)
        show_id = getattr(config, 'current_show', None) if config else None
        if show_id is None:
            return {'error': 'No current show configured'}

        with sr_db.session() as s:
            cue_lists = s.exec(
                sr_select(SRCueList).where(SRCueList.show_id == show_id)
            ).all()

        return {
            'cue_lists': [
                {'id': cl.id, 'name': cl.name, 'description': cl.description}
                for cl in cue_lists
            ]
        }

    def _cmd_generate_dca(
        self,
        script_id: int | None = None,
        lookahead: int = 7,
        layer: str = 'Sound',
        cue_list_id: int | None = None,
        **_kwargs,
    ):
        if layer not in VALID_LAYERS:
            return {
                'error': f'Invalid layer {layer!r}. Must be one of: {", ".join(VALID_LAYERS)}'
            }

        if _db is None:
            return {'error': 'TheatreMix database not loaded'}

        if script_id is None:
            return {'error': 'script_id is required'}

        try:
            script = _load_showrunner_script(script_id)
        except HTTPException as e:
            return {'error': e.detail}

        script_title = _get_showrunner_script_title(script_id)

        dca_cues = generate_dca_cues(
            script, str(_db.db_path), max_dialogues_ahead=lookahead
        )

        if not dca_cues:
            return {
                'script_title': script_title,
                'cues_created': 0,
                'errors': [
                    'No DCA cues generated — check that the script has character dialogue'
                ],
            }

        # Write to ShowRunner cue list
        from showrunner.models import Cue as SRCue, CueList as SRCueList

        sr_db = getattr(_app, 'db', None)
        if sr_db is None:
            return {'error': 'ShowRunner database not loaded'}

        config = getattr(_app, 'config', None)
        show_id = getattr(config, 'current_show', None) if config else None
        if show_id is None:
            return {'error': 'No current show configured'}

        errors: list[str] = []

        with sr_db.session() as s:
            # Use specified cue list or find/create one by convention
            if cue_list_id is not None:
                cue_list = s.get(SRCueList, cue_list_id)
                if cue_list is None:
                    return {'error': f'Cue list {cue_list_id} not found'}
            else:
                cue_list = s.exec(
                    sr_select(SRCueList).where(
                        SRCueList.show_id == show_id,
                        SRCueList.name == f'TheatreMix DCA ({layer})',
                    )
                ).first()

                if cue_list is None:
                    cue_list = SRCueList(
                        show_id=show_id,
                        name=f'TheatreMix DCA ({layer})',
                        description=f'Auto-generated DCA muting cues for {layer} layer',
                    )
                    s.add(cue_list)
                    s.commit()
                    s.refresh(cue_list)

            # Determine sequence offset so new cues append after existing ones
            max_seq = s.exec(
                sr_select(SRCue.sequence)
                .where(SRCue.cue_list_id == cue_list.id)
                .order_by(SRCue.sequence.desc())
            ).first()
            seq_offset = (max_seq + 1) if max_seq is not None else 0

            for seq, tm_cue in enumerate(dca_cues, start=seq_offset):
                sr_cue = SRCue(
                    cue_list_id=cue_list.id,
                    number=tm_cue.number,
                    point=tm_cue.point,
                    name=tm_cue.name,
                    layer=layer,
                    cue_type='DCA',
                    notes=_format_dca_notes(tm_cue),
                    sequence=seq,
                )
                s.add(sr_cue)
            s.commit()

            cue_list_id = cue_list.id

        return {
            'script_title': script_title,
            'layer': layer,
            'lookahead': lookahead,
            'cue_list_id': cue_list_id,
            'cues_created': len(dca_cues),
            'errors': errors,
        }


plugin = TheatreMixPlugin()
