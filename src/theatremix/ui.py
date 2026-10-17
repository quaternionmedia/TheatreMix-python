"""NiceGUI pages for the TheatreMix plugin.

/theatremix is the DCA grid: one row per .tmix cue, one column per DCA.
Editing is behind a lock switch; every change re-syncs the linked ShowRunner cues.
Sub pages for profiles, ensembles and actors go under /theatremix/edit/.
"""

from __future__ import annotations

import re
from collections import deque

from fastapi import HTTPException

from . import showrunner as tm
from . import theme
from .models import Actor, Ensemble, Profile

UNDO_LEVELS = 50
# Shared by every client: the .tmix file is shared, so undo is too.
_undo_stack: deque[dict] = deque(maxlen=UNDO_LEVELS)

# Vue template for every body cell. Click emits the cell; right-click emits the cue (for colour).
CELL_TEMPLATE = """
<q-td :props="props" :class="props.col.name.startsWith('dca') ? props.value.cls : props.row.row_cls"
  @click="$parent.$emit('cell-click', {id: props.row.id, col: props.col.name})"
  @contextmenu.prevent="$parent.$emit('cell-click', {id: props.row.id, col: 'cue'})">
  <span v-if="props.col.name.startsWith('dca')">
    <q-tooltip v-if="props.value.channels">ch {{ props.value.channels }}</q-tooltip>
    {{ props.value.label }}
  </span>
  <span v-else>{{ props.value }}</span>
</q-td>
"""


def _cue_label(cue) -> str:
    """Cue number with point, e.g. '5' or '5.10'."""
    return f'{cue.number}.{cue.point}' if cue.point else f'{cue.number}'


def grid_rows(cues, dcas: list[int]) -> list[dict]:
    """Table rows for the DCA grid. Each DCA cell is compared with the same DCA on the previous cue."""
    rows = []
    cues = list(cues)
    for i, cue in enumerate(cues):
        nxt = cues[i + 1] if i + 1 < len(cues) else None
        colour = theme.row_colour(cue.colour)
        row = {
            'id': f'{cue.number}.{cue.point}',
            'cue': _cue_label(cue),
            'name': cue.name or '',
            'row_cls': f'bg-{colour}' if colour else '',
        }
        for d in dcas:
            cur = theme.dca_cell(cue, d)
            state = theme.cell_state(cur, theme.dca_cell(nxt, d) if nxt else None)
            row[f'dca{d}'] = {
                'label': cur[0],
                'channels': cur[1],
                'cls': f'bg-{theme.COLORS[state]}' if state else row['row_cls'],
            }
        rows.append(row)
    return rows


def script_previews(tm_cues, dcas: list[int], sr_cues: list[dict]) -> dict[int, list[dict]]:
    """Preview chips for linked 'Mix' cues in the ShowRunner script viewer: {sr cue id: chips}.

    Chips use the grid's background colours (state vs the next .tmix cue). Empty DCAs are left out.
    """
    by_key: dict[tuple[int, int], list[dict]] = {}
    cues = list(tm_cues)
    for i, cue in enumerate(cues):
        nxt = cues[i + 1] if i + 1 < len(cues) else None
        chips = []
        for d in dcas:
            cur = theme.dca_cell(cue, d)
            if not any(cur):
                continue
            state = theme.cell_state(cur, theme.dca_cell(nxt, d) if nxt else None)
            label, channels = cur
            # no state: same as the grid, the row tint or no tint (ShowRunner would otherwise fall back to grey-9)
            colour = theme.COLORS[state] if state else (theme.row_colour(cue.colour) or 'transparent')
            chip = {'text': f'{d} {label or channels}', 'color': colour}
            if channels:
                chip['tooltip'] = f'DCA {d}: ch {channels}'
            chips.append(chip)
        by_key[(cue.number, cue.point)] = chips

    out = {}
    for c in sr_cues:
        if c.get('layer') != 'Mix':
            continue
        try:
            key = (int(c['number']), c['point'])
        except (TypeError, ValueError):
            continue
        if key in by_key:
            out[c['id']] = by_key[key]
    return out


def grid_columns(dcas: list[int]) -> list[dict]:
    """Column definitions: cue number, name, then one column per DCA."""
    cols = [
        {'name': 'cue', 'label': '#', 'field': 'cue', 'align': 'left'},
        {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left'},
    ]
    cols += [{'name': f'dca{d}', 'label': f'DCA {d}', 'field': f'dca{d}', 'align': 'left'} for d in dcas]
    return cols


def parse_channels(text: str) -> str | None:
    """'1, 2,3' -> '1,2,3'; blank -> None. Only digits and commas are allowed."""
    text = ''.join(text.split())
    if not text:
        return None
    if not re.fullmatch(r'\d+(,\d+)*', text):
        raise ValueError('Channels must be digits separated by commas, e.g. 1,2,3')
    return text


# Sub pages under /theatremix/edit/: (title, model, [(attribute, label, kind)]); kind is int, str or bool.
SUB_PAGES = {
    'profiles': ('Profiles', Profile, [('channel', 'Channel', 'int'), ('name', 'Name', 'str'),
                                       ('label', 'Label', 'str'), ('default', 'Default', 'bool')]),
    'ensembles': ('Ensembles', Ensemble, [('name', 'Name', 'str'), ('channels', 'Channels', 'str')]),
    'actors': ('Actors', Actor, [('channel', 'Channel', 'int'), ('name', 'Name', 'str'),
                                 ('order', 'Order', 'int'), ('active', 'Active', 'bool')]),
}

CRUD_CELL_TEMPLATE = """
<q-td :props="props" @click="$parent.$emit('cell-click', {id: props.row.id})">{{ props.value }}</q-td>
"""


def _cell_text(kind: str, value) -> str:
    if kind == 'bool':
        return '✓' if value else ''
    return '' if value is None else str(value)


def _parse(kind: str, widget):
    """Widget value -> column value. Raises ValueError for a bad int."""
    if kind == 'bool':
        return int(bool(widget.value))
    text = str(widget.value).strip()
    if kind == 'int':
        return int(text) if text else None
    return text or None


def merge_channels(current: str, added: str) -> str:
    """Append channels from a tray chip to the current value, skipping duplicates. '1,3' + '3,4' -> '1,3,4'."""
    have = [x for x in current.replace(' ', '').split(',') if x]
    new = [x for x in added.replace(' ', '').split(',') if x and x not in have]
    return ','.join(have + new)


def register_pages() -> None:
    """Register the NiceGUI pages. Called from the plugin's startup hook."""
    from nicegui import ui

    from showrunner.ui import header

    @ui.page('/theatremix')
    def theatremix_page():
        ui.dark_mode(True)
        header()

        db = tm._db
        with ui.column().classes('w-full max-w-full p-4 gap-4'):
            if db is None:
                ui.label(
                    'No TheatreMix database loaded. Set [plugins.theatremix] database in show.toml.'
                ).classes('text-amber text-lg')
                return

            dcas = db.get_dca_numbers()
            active = {'v': None}  # channel input of the open DCA dialog, filled by tray chips
            with ui.row().classes('w-full items-center gap-4'):
                ui.label('TheatreMix').classes('text-h5')
                lock = ui.switch('Unlock editing', value=False)
                add_btn = ui.button('Add cue', icon='add')
                add_btn.bind_visibility_from(lock, 'value')
                undo_btn = ui.button('Undo', icon='undo', color='grey-8')
                undo_btn.bind_visibility_from(lock, 'value')
                gen_btn = ui.button('Generate…', icon='movie', color='grey-8')
                gen_btn.bind_visibility_from(lock, 'value')
                count = ui.label().classes('text-grey')
                for key, (title, _, _) in SUB_PAGES.items():
                    ui.link(title, f'/theatremix/edit/{key}')

            table = ui.table(
                columns=grid_columns(dcas),
                rows=[],
                row_key='id',
                pagination={'rowsPerPage': 0},  # 0 = all rows on one page
            ).classes('w-full')
            table.add_slot('body-cell', CELL_TEMPLATE)

            def checkpoint(description: str, back: dict | None = None) -> None:
                """Snapshot the cue list before a change. back maps new (number, point) to old, for sync."""
                _undo_stack.append({'description': description, 'snapshot': db.snapshot_cues(), 'renames': back})

            def undo_last() -> None:
                if not _undo_stack:
                    ui.notify('Nothing to undo', type='warning')
                    return
                entry = _undo_stack.pop()
                db.restore_cues(entry['snapshot'])
                ui.notify(f"Undone: {entry['description']}")
                refresh(entry['renames'])

            def reload():
                cues = db.get_all_cues()
                table.rows[:] = grid_rows(cues, dcas)
                table.update()
                count.set_text(f'{db.db_path.name} · {len(cues)} cues')

            def refresh(renames=None):
                """After a change: re-sync the linked ShowRunner cues, then reload the grid."""
                tm._sync_links(renames)
                reload()

            def edit_dca(cue, d):
                def save():
                    try:
                        channels = parse_channels(chan_in.value)
                    except ValueError as e:
                        ui.notify(str(e), type='negative')
                        return
                    checkpoint(f'DCA {d} on cue {cue.number}.{cue.point}')
                    db.update_cue(
                        cue.number, cue.point,
                        **{f'dca{d:02d}Label': label_in.value or None, f'dca{d:02d}Channels': channels},
                    )
                    dlg.close()
                    refresh()

                def clear():
                    checkpoint(f'Clear DCA {d} on cue {cue.number}.{cue.point}')
                    db.update_cue(cue.number, cue.point, **{f'dca{d:02d}Label': None, f'dca{d:02d}Channels': None})
                    dlg.close()
                    refresh()

                with ui.dialog().props('seamless') as dlg, ui.card():
                    ui.label(f'Cue {cue.number}.{cue.point} · DCA {d}').classes('text-h6')
                    label_in = ui.input('Label', value=getattr(cue, f'dca{d:02d}Label') or '')
                    chan_in = ui.input('Channels', value=getattr(cue, f'dca{d:02d}Channels') or '')
                    with ui.row():
                        ui.button('Clear', on_click=clear, color='red-4')
                        ui.button('Cancel', on_click=dlg.close)
                        ui.button('Save', on_click=save)
                dlg.on('hide', lambda: active.update(v=None))
                active['v'] = chan_in
                dlg.open()

            def edit_cue(cue=None):
                """Cue dialog. cue=None adds a new cue."""
                is_new = cue is None

                def save():
                    number, point = int(num_in.value), int(pt_in.value)
                    try:
                        if is_new:
                            if db.get_cue(number, point):
                                raise ValueError(f'Cue {number}.{point} already exists')
                            checkpoint(f'Add cue {number}.{point}')
                            db.add_cue(name=name_in.value, number=number, point=point, colour=colour_in.value)
                        else:
                            checkpoint(
                                f'Edit cue {cue.number}.{cue.point}',
                                {(number, point): (cue.number, cue.point)} if (number, point) != (cue.number, cue.point) else None,
                            )
                            if (number, point) != (cue.number, cue.point):
                                db.renumber_cue(cue.number, cue.point, number, point)
                            db.update_cue(number, point, name=name_in.value, colour=colour_in.value)
                    except ValueError as e:
                        ui.notify(str(e), type='negative')
                        return
                    dlg.close()
                    renames = None
                    if not is_new and (number, point) != (cue.number, cue.point):
                        renames = {(cue.number, cue.point): (number, point)}
                    refresh(renames)

                def delete():
                    checkpoint(f'Delete cue {cue.number}.{cue.point}')
                    db.delete_cue(cue.number, cue.point)
                    dlg.close()
                    refresh()

                def duplicate():
                    checkpoint(f'Duplicate cue {cue.number}.{cue.point}')
                    new_point = db.copy_cue(cue.number, cue.point)
                    ui.notify(f'Copied to {cue.number}.{new_point}')
                    dlg.close()
                    refresh()

                with ui.dialog() as dlg, ui.card():
                    ui.label('Add cue' if is_new else f'Cue {cue.number}.{cue.point}').classes('text-h6')
                    num_in = ui.number('Number', value=cue.number if cue else db.get_next_cue_number()[0], precision=0)
                    pt_in = ui.number('Point', value=cue.point if cue else 0, precision=0)
                    name_in = ui.input('Name', value=(cue.name or '') if cue else '')
                    colour_in = ui.select(
                        {i: (n or 'none') for i, n in enumerate(theme.ROW_COLOURS)}, label='Row colour',
                        value=(cue.colour or 0) if cue else 0,
                    )
                    with ui.row():
                        if not is_new:
                            ui.button('Delete', on_click=delete, color='red-4')
                            ui.button('Duplicate', on_click=duplicate)
                        ui.button('Cancel', on_click=dlg.close)
                        ui.button('Save', on_click=save)
                dlg.open()

            def fill_channels(value) -> None:
                """Tray chip: add channels to the open DCA dialog's channel input."""
                if active['v'] is None:
                    ui.notify('Open a DCA cell first', type='warning')
                    return
                active['v'].value = merge_channels(active['v'].value, str(value))

            with ui.row().classes('w-full gap-2 flex-wrap'):
                for p in db.get_profiles():
                    if p.channel:
                        ui.chip(f'{p.channel} {p.name or ""}'.strip(), on_click=lambda _, c=p.channel: fill_channels(c))
                for e in db.get_ensembles():
                    ui.chip(f'{e.name}: {e.channels}', on_click=lambda _, c=e.channels: fill_channels(c))

            async def open_generate() -> None:
                scripts = await tm.list_scripts()
                if not scripts:
                    ui.notify('No Fountain scripts in ShowRunner for this show', type='warning')
                    return
                with ui.dialog() as gdlg, ui.card():
                    ui.label('Generate DCA cues from script').classes('text-h6')
                    script_sel = ui.select({sc['id']: sc['title'] for sc in scripts}, label='Script',
                                           value=scripts[0]['id'])
                    look = ui.number('Lookahead (dialogues)', value=7, precision=0, min=1)

                    def confirm():
                        with ui.dialog() as cdlg, ui.card():
                            ui.label(f'Replace all {len(db.get_all_cues())} cues in {db.db_path.name} '
                                     'with generated DCA cues?')
                            ui.label(f'A backup is written to {db.db_path.name}.bak first.').classes('text-grey')
                            with ui.row():
                                ui.button('Cancel', on_click=cdlg.close)
                                ui.button('Replace', color='red-4', on_click=lambda: run(cdlg))
                        cdlg.open()

                    def run(cdlg):
                        cdlg.close()
                        gdlg.close()
                        snap = db.snapshot_cues()
                        try:
                            report = tm._generate_dca(script_sel.value, int(look.value))
                        except HTTPException as e:
                            ui.notify(str(e.detail), type='negative')
                            return
                        if report['errors']:
                            ui.notify('; '.join(report['errors']), type='warning')
                        if report['cues_created']:
                            _undo_stack.append({'description': f'Generate from script {script_sel.value}',
                                                'snapshot': snap, 'renames': None})
                            ui.notify(f"Generated {report['cues_created']} cues")
                        reload()

                    with ui.row():
                        ui.button('Cancel', on_click=gdlg.close)
                        ui.button('Generate…', on_click=confirm)
                gdlg.open()

            def on_cell(args):
                if not lock.value:
                    ui.notify('Unlock editing first', type='warning')
                    return
                cue_id, col = args['id'], args['col']
                number, point = (int(x) for x in cue_id.split('.'))
                cue = db.get_cue(number, point)
                if cue is None:
                    return
                if col.startswith('dca'):
                    edit_dca(cue, int(col[3:]))
                else:
                    edit_cue(cue)

            table.on('cell-click', lambda e: on_cell(e.args))
            add_btn.on_click(lambda: edit_cue(None))
            undo_btn.on_click(undo_last)
            gen_btn.on_click(open_generate)
            reload()

        def crud_page(path: str, title: str, model, fields: list) -> None:
            @ui.page(path)
            def page():
                ui.dark_mode(True)
                header()
                db = tm._db
                with ui.column().classes('w-full max-w-full p-4 gap-4'):
                    if db is None:
                        ui.label('No TheatreMix database loaded.').classes('text-amber text-lg')
                        return
                    with ui.row().classes('w-full items-center gap-4'):
                        ui.link('← DCA grid', '/theatremix')
                        ui.label(title).classes('text-h5')
                        lock = ui.switch('Unlock editing', value=False)
                        add_btn = ui.button('Add', icon='add')
                        add_btn.bind_visibility_from(lock, 'value')
                    table = ui.table(
                        columns=[{'name': a, 'label': lbl, 'field': a, 'align': 'left'} for a, lbl, _ in fields],
                        rows=[], row_key='id',
                        pagination={'rowsPerPage': 0},
                    ).classes('w-full')
                    table.add_slot('body-cell', CRUD_CELL_TEMPLATE)

                    def reload():
                        table.rows[:] = [
                            {'id': r.id, **{a: _cell_text(k, getattr(r, a)) for a, _, k in fields}}
                            for r in db.list_rows(model)
                        ]
                        table.update()

                    def edit(row_id=None):
                        if not lock.value:
                            ui.notify('Unlock editing first', type='warning')
                            return
                        row = next((r for r in db.list_rows(model) if r.id == row_id), None) if row_id else None

                        def save():
                            try:
                                data = {a: _parse(k, inputs[a]) for a, _, k in fields}
                            except ValueError:
                                ui.notify('Channel and order must be whole numbers', type='negative')
                                return
                            if row:
                                db.update_row(model, row.id, **data)
                            else:
                                db.add_row(model, **data)
                            dlg.close()
                            reload()

                        def delete():
                            db.delete_row(model, row.id)
                            dlg.close()
                            reload()

                        with ui.dialog() as dlg, ui.card():
                            ui.label(title if row is None else f'{title} #{row.id}').classes('text-h6')
                            inputs = {}
                            for a, lbl, k in fields:
                                val = getattr(row, a) if row else None
                                if k == 'bool':
                                    inputs[a] = ui.switch(lbl, value=bool(val))
                                else:
                                    inputs[a] = ui.input(lbl, value=_cell_text(k, val))
                            with ui.row():
                                if row:
                                    ui.button('Delete', on_click=delete, color='red-4')
                                ui.button('Cancel', on_click=dlg.close)
                                ui.button('Save', on_click=save)
                        dlg.open()

                    table.on('cell-click', lambda e: edit(e.args['id']))
                    add_btn.on_click(lambda: edit(None))
                    reload()

        for key, (title, model, fields) in SUB_PAGES.items():
            crud_page(f'/theatremix/edit/{key}', title, model, fields)
