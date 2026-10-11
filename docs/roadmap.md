# TheatreMix roadmap

## Built in v1
- `/theatremix`: DCA grid (one row per cue, one column per DCA), colours by change.
- Edit lock; DCA cell dialog; cue name, number, point and row colour; add, delete, duplicate.
- Undo (full cue-list snapshot per change, last 50).
- Channel tray (profiles and ensembles) that fills the open DCA dialog.
- Generate DCA cues from a ShowRunner script (writes `<db>.bak` first, then replaces the `.tmix` cues).
- Sub pages under `/theatremix/edit/`: profiles, ensembles, actors.
- Linked ShowRunner cues (`layer='Mix'`, `cue_type='TheatreMix'`) in the `TheatreMix` cue list, synced after every change.

## Not built yet
- Live console connection: active-cue highlight, channel level monitor, backup-mic status.
- Position and FX columns.
- `>` prefix to indent a name (UI helper).
- Two-way sync: edits in ShowRunner's cues back to the `.tmix`.
- Undo history menu (v1 has a single Undo button).
- Row-size select in the grid.
- Editing actor↔profile links (`actorProfiles`); v1 edits actors only.
- Undo on the sub pages.

## Known limits
- Undo restores the whole cue list. Changes made in the TheatreMix app while ShowRunner is open are lost on undo.
- Undo of a delete recreates the linked ShowRunner cue; its `script_line` link is not restored.
- Generate with an explicit cue list still mirrors into the `TheatreMix` cue list.
- Editing the `.tmix` while the TheatreMix app has it open can collide.
- The grid dialogs were checked only by rendering the pages (HTTP 200), not in a browser.
