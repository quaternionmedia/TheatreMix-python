# Plan: TheatreMix cue & DCA patching pages for the ShowRunner plugin

## Context
`theatremix.showrunner` has REST routes only (`/theatremix/cues`, `/profiles`, `/generate-dca`, …) and no UI.
We add NiceGUI pages in the style of TheatreMix's main screen: a cue list with one column per DCA, editable inline.

Decisions (from user):
1. **Source of truth = the external `.tmix` DB** (option A). DCA channels/labels are read and written there.
2. **ShowRunner side** = thin linked cues: `layer='Mix'`, `cue_type='TheatreMix'`, one per `.tmix` cue, so they show up in the
   ShowRunner script/cue views. They hold no DCA data.
3. **Main page = DCA grid.** Sub pages for the other things (profiles, ensembles, actors; see below).
4. **No console features** (active-cue highlight, level monitoring, backup-mic status): leave out, noted in "Later".
5. **v1 scope:** grid, lock/unlock inline edit, row colours, undo, channel tray, generate from script. **No Position/FX columns.**
6. **Look:** simple dark theme, basic colours, all in one editable colour table, documented.

## TheatreMix main screen (from theatremix.com/features)
- One row per cue (number, name), one column per DCA 1–12; cell = DCA label, colour coded by change vs previous cue.
- Edit lock; unlocked: change DCA assignments, renumber, `>` prefix to indent a name.
- Right-click cue number → row colour (`Cue.colour`). Channel tray below the list (profile channels, name as label).

## Existing code we reuse
- Page pattern: `~/ShowRunner/src/showrunner/plugins/midi.py:_build_page` and `scripter.py:_build_page`
  (`@ui.page`, `ui.dark_mode(True)`, `showrunner.ui.header()`, `_current_show_id()`, `ui.refreshable`,
  undo deque of snapshot/reverse fns `_push_undo/_perform_undo`). `showrunner_startup` calls `_build_page()`.
- `src/theatremix/db.py` `TheatreMixDB`: `get_all_cues/add_cue/update_cue/delete_cue/get_profiles/get_config`.
- `src/theatremix/models.py` `Cue` (`dcaNNChannels`, `dcaNNLabel` ×12, `colour`, `name`, `number`, `point`),
  `Profile`, `Ensemble`, `Actor`, `ActorProfile`.
- `src/theatremix/dca.py:generate_dca_cues` (already yields full DCA state per cue, plus `_script_line`).
- `src/theatremix/showrunner.py`: `_get_showrunner_db`, `_get_current_show_id`, `_load_showrunner_script`, `VALID_LAYERS`,
  the SR `Cue`/`CueList` writing code inside `generate_dca` (duplicated in `_cmd_generate_dca` — will be merged into one helper).
- Real test data: `~/LittleWomen/mix/LittleWomen.tmix` (use a copy).

## Findings that change the code
- `TheatreMixDB.update_cue/delete_cue/get_cue` look up by `point` only. Generated cues all have `point=0`, so these hit the
  wrong row. → key by `(number, point)`.
- `.tmix` `cues` table has no primary key; `Cue` model fakes one on `(number, point)`. Renumbering = update of a PK column →
  do it as delete+insert in one transaction.
- `generate_dca` currently writes only to ShowRunner (`cue_type='DCA'`, DCA state flattened into `notes`) and never to the `.tmix`.
  New behaviour: write to `.tmix` (source of truth), then upsert linked SR cues.
- `'Mix'` is not in ShowRunner's `LAYERS` (`scripter.py:20`), so the script page's layer toolbar won't offer it, and its chips fall
  back to grey. `Cue.layer` is a free string, so nothing breaks. Small follow-up PR in ShowRunner (add `'Mix'` + colour) — not
  needed for this work.

## Design

### Data link
- Linked SR cue: `number=str(tm.number)`, `point=tm.point`, `name=tm.name`, `layer='Mix'`, `cue_type='TheatreMix'`,
  `script_line` kept from generation. Key = `(cue_list_id, number, point)`.
- One SR `CueList` per show named `TheatreMix` (find or create — replaces the per-layer `TheatreMix DCA (…)` convention).
- `sync_links(tm_db, sr_session, cue_list_id)`: upsert/delete SR cues so they mirror the `.tmix` cue list. Called after every
  grid edit that changes number/point/name or adds/deletes a cue. DCA-only edits touch the `.tmix` only.
- Orphans: SR `Mix` cues whose `.tmix` cue is gone are deleted by sync. `.tmix` cues are never created from SR edits in v1.
- `showrunner_config_changed` already reopens the DB when the path changes; pages must read `_db` at request time.

### Pages (`src/theatremix/ui.py`, one `register_pages()` called from `showrunner_startup`)
| Route | Content |
|---|---|
| `/mix` | **DCA grid** (main) |
| `/mix/profiles` | `profiles` table: channel ↔ name/label, default flag; add/edit/delete |
| `/mix/ensembles` | `ensembles`: name + channel list |
| `/mix/actors` | `actors` + `actorProfiles`: actor ↔ channel/profile, active toggle |

Pages live under `/mix` because the REST routes already own `/theatremix/cues`, `/theatremix/profiles` (JSON) — no route
changes, no collisions. `showrunner_get_nav` path changes `/theatremix` → `/mix`; add a `path` to the status icon so it links there.

### Grid layout (`/mix`)
- Toolbar: lock toggle (locked by default), undo (+ history menu like scripter), **Generate…** (script picker, lookahead;
  confirm dialog because it replaces all `.tmix` cues; writes `<db>.bak` first), add cue, row-size select, link-status chip
  (`.tmix` path or "no database").
- Table: `#` (number.point), Name, DCA 1…12. Cell shows the label; tooltip shows channels. Cell colour by comparing to the
  previous cue's cell:
  new/changed = green, unchanged = white, cleared this cue = red, (grey = empty).
  Row tint from `Cue.colour`. `>` prefix indents the name.
- Unlocked: click a cell → dialog (label, channels: pick from profiles/ensembles chips or type `3,4`), clear button;
  click name / number to edit; right-click number → colour menu; delete/duplicate row; each edit pushes an undo snapshot.
- Channel tray under the table: profile/ensemble chips (name + channel). Click a chip while a cell dialog is open to fill it.

### Colours / theme
- Single module `src/theatremix/theme.py`: `COLORS = {'new': 'green-4', 'same': 'white', 'cleared': 'red-4', 'empty': 'grey-8',
  'row_colours': {...}}` — values are Quasar colour names (or CSS hex).
- Docs: add `docs/theme.md` (+ README link) explaining the table, accepted values, how to change them (edit `theme.py`;
  optional override via `[plugins.theatremix.colors]` in `show.toml`, read in `showrunner_startup`). Dark mode is
  always on, as in other pages.

### Later (notes, not built)
Record in `docs/roadmap.md`: live console connection (active-cue highlight, channel level monitor, backup-mic status
tray), Position and FX columns, `>` indent UI helper, two-way sync from SR edits to `.tmix`.

## Files to add / modify
- add `src/theatremix/ui.py` — pages
- add `src/theatremix/theme.py` — colour table
- add `src/theatremix/sync.py` — `.tmix` ↔ SR link helpers (pure-ish, testable)
- edit `src/theatremix/db.py` — `(number, point)` keys; `replace_cues()`, `renumber_cue()`, profile/ensemble/actor CRUD
- edit `src/theatremix/showrunner.py` — register pages, `generate_dca` + `_cmd_generate_dca` call one shared writer
  (`.tmix` + sync), nav path `/mix`, `VALID_LAYERS` gets `'Mix'`, theme config load
- add `tests/test_db_cues.py`, `tests/test_sync.py`, `tests/test_cell_state.py`; update `tests/test_showrunner.py`
- add `docs/theme.md`, `docs/roadmap.md`; README links
- dependency: `nicegui` arrives via `showrunner` (verify in `uv.lock`; do not add)

## Steps
- [x] 1. DB: key cue ops by `(number, point)`; add `replace_cues`, `renumber_cue`; tests with a temp `.tmix`
- [x] 2. `sync.py`: upsert/delete linked SR cues (`layer='Mix'`, `cue_type='TheatreMix'`); tests with ShowRunner in-memory DB
- [x] 3. Make generate write `.tmix` (backup first) then sync; merge the duplicated REST/command code; update tests
- [x] 4. `theme.py` + pure helper `cell_state(prev, cur)`; unit tests
- [x] 5. Read-only `/mix` grid
- [x] 6. Lock toggle; DCA cell dialog; name/number/colour edit; add/delete/duplicate
- [x] 7. Undo (snapshot + reverse fn, copied from scripter pattern)
- [x] 8. Channel tray; Generate dialog
- [x] 9. Sub pages: profiles, ensembles, actors
- [x] 10. Docs (`theme.md`, `roadmap.md`), README

## Verification
- `uv run pytest` (new unit tests: DB keys, sync, cell state, generate end-to-end into a temp `.tmix` + SR DB).
- Manual: copy `~/LittleWomen/mix/LittleWomen.tmix`, start ShowRunner with
  `[plugins.theatremix] database=<copy>`, open `/mix`: generate from a script, check grid colours; unlock, edit a cell,
  rename, renumber, undo; reload, confirm persisted; open the TheatreMix app on the same file to confirm it still loads;
  check `/script` shows the linked `Mix` cues; edit sub pages.
- Edit colours in `theme.py`, reload, confirm they change.

## Risks
- Generate replaces `.tmix` cues (backed up, with confirm). Real show files: always test on a copy.
- Editing the `.tmix` while the TheatreMix app has it open may collide — note in the docs.
- `.tmix` has no real PK; renumber delete+insert must stay in one transaction.
