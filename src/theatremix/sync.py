"""Mirror a .tmix cue list into linked ShowRunner cues (layer 'Mix').

The .tmix file holds the DCA data. ShowRunner only gets one thin cue per
.tmix cue, matched by (number, point), so it shows up in ShowRunner's cue
views. Cue create, edit and delete in the ShowRunner script viewer are carried back into
the .tmix file (mirror_cue).
"""

from __future__ import annotations

from loguru import logger
from sqlmodel import Session, select

from showrunner.models import Cue as SRCue, CueList as SRCueList

from .models import Cue as TMCue

LAYER = 'Mix'
LAYER_TYPE = 'TheatreMix'  # ShowRunner layer type registered by this plugin
CUE_TYPE = 'TheatreMix'
LIST_NAME = 'TheatreMix'


def get_or_create_cue_list(s: Session, show_id: int) -> SRCueList:
    """The show's 'TheatreMix' cue list, created on first use."""
    cue_list = s.exec(
        select(SRCueList).where(
            SRCueList.show_id == show_id, SRCueList.name == LIST_NAME
        )
    ).first()
    if cue_list is None:
        cue_list = SRCueList(
            show_id=show_id,
            name=LIST_NAME,
            description='Linked TheatreMix cues; DCA data lives in the .tmix file',
        )
        s.add(cue_list)
        s.commit()
        s.refresh(cue_list)
    return cue_list


def _key(number, point) -> tuple[str, int]:
    """ShowRunner stores the cue number as text."""
    return (str(number), point)


def sync_links(
    s: Session,
    cue_list_id: int,
    tm_cues: list[TMCue],
    renames: dict[tuple[int, int], tuple[int, int]] | None = None,
    layer: str = LAYER,
) -> None:
    """Make the linked cues on `layer` in cue_list_id match tm_cues exactly.

    renames maps old (number, point) to new, so a renumbered cue keeps its
    ShowRunner row (and script_line). Cues in the list that are not
    TheatreMix links on `layer` are left alone.
    """
    existing = {
        _key(c.number, c.point): c
        for c in s.exec(
            select(SRCue).where(
                SRCue.cue_list_id == cue_list_id,
                SRCue.layer == layer,
                SRCue.cue_type == CUE_TYPE,
            )
        ).all()
    }

    for old, new in (renames or {}).items():
        sr = existing.pop(_key(*old), None)
        if sr is not None:
            stale = existing.pop(_key(*new), None)
            if stale is not None:
                s.delete(stale)
            sr.number, sr.point = str(new[0]), new[1]
            existing[_key(*new)] = sr

    for seq, tm in enumerate(tm_cues):
        sr = existing.pop(_key(tm.number, tm.point), None) or SRCue(
            cue_list_id=cue_list_id, layer=layer, cue_type=CUE_TYPE
        )
        sr.number, sr.point = str(tm.number), tm.point
        sr.name = tm.name
        sr.sequence = seq
        # Only generation knows the script line; grid edits leave it alone.
        if hasattr(tm, '_script_line'):
            sr.script_line = tm._script_line
        s.add(sr)

    for orphan in existing.values():
        s.delete(orphan)
    s.commit()


def _int_key(number, point) -> tuple[int, int] | None:
    """The .tmix key of a ShowRunner cue, or None when its number is not a whole number."""
    try:
        return int(number), int(point or 0)
    except (TypeError, ValueError):
        return None


def _is_link(c: dict | None, layer: str) -> bool:
    return c is not None and c['layer'] == layer and c['cue_type'] == CUE_TYPE


def _previous_key(s: Session, list_id: int, layer: str, cue: dict) -> tuple[int, int] | None:
    """Key of the linked cue just before `cue` in the script, or the last linked cue if it has no line."""
    rows = [r for r in s.exec(select(SRCue).where(
        SRCue.cue_list_id == list_id, SRCue.layer == layer,
        SRCue.cue_type == CUE_TYPE, SRCue.id != cue['id'])).all()]
    if cue['script_line'] is None:
        cands = [r for r in rows if _int_key(r.number, r.point) is not None]
        best = max(cands, key=lambda r: _int_key(r.number, r.point), default=None)
    else:
        here = (cue['script_line'], cue['script_char'] or 0)
        cands = [r for r in rows if r.script_line is not None
                 and (r.script_line, r.script_char or 0) <= here]
        best = max(cands, key=lambda r: (r.script_line, r.script_char or 0), default=None)
    return _int_key(best.number, best.point) if best is not None else None


def _refuse(s: Session, cue: dict, msg: str) -> str:
    """Unlink a ShowRunner cue whose .tmix cue could not be made.

    Left linked, the next sync would find no .tmix cue for it and delete it as an orphan.
    """
    row = s.get(SRCue, cue['id'])
    row.cue_type = None
    s.add(row)
    s.commit()
    return msg


def _adopt(s: Session, tm_db, show_id: int, list_id: int | None, layer: str, cue: dict) -> str | None:
    """Give a ShowRunner cue its own .tmix cue: a copy of the previous linked cue, placed after it.

    Returns a message for the user, and makes no .tmix change, when there is no earlier linked
    cue to copy from.
    """
    list_id = list_id or get_or_create_cue_list(s, show_id).id
    prev = _previous_key(s, list_id, layer, cue)
    if prev is None or tm_db.get_cue(*prev) is None:
        return _refuse(s, cue, f'no earlier {layer} cue to copy DCA state from; add a TheatreMix cue above it in the grid first')
    try:
        key = tm_db.copy_cue(*prev, to=tm_db.place_after(*prev))
    except ValueError as exc:
        return _refuse(s, cue, str(exc))
    tm_db.update_cue(*key, name=cue['name'] or '')
    row = s.get(SRCue, cue['id'])
    row.number, row.point = str(key[0]), key[1]
    row.cue_type, row.cue_list_id = CUE_TYPE, list_id
    s.add(row)
    s.commit()
    return None


def mirror_cue(
    s: Session,
    tm_db,
    show_id: int,
    list_id: int | None,
    layer: str,
    action: str,
    cue: dict,
    before: dict | None = None,
) -> str | None:
    """Carry one ShowRunner cue change into the .tmix file (see showrunner_cue_changed).

    A cue created on `layer`, or moved onto it, gets a copy of the previous linked cue's DCA
    state. Edits rename or renumber its .tmix cue; a renumber that clashes is reverted in
    ShowRunner. Deleting it, or moving it off `layer`, removes its .tmix cue. Returns a message
    when the .tmix file was not changed as asked, else None.
    """
    if action == 'delete' or cue['layer'] != layer:
        gone = before if action != 'delete' else cue
        key = _int_key(gone['number'], gone['point']) if _is_link(gone, layer) else None
        if key is not None:
            tm_db.delete_cue(*key)
        return None
    if _is_link(cue, layer):
        new_key = _int_key(cue['number'], cue['point'])
        if new_key is None:
            return _refuse(s, cue, f'number {cue["number"]!r} is not a whole number')
        old_key = _int_key(before['number'], before['point']) if _is_link(before, layer) else None
        if old_key == new_key and before['name'] == cue['name']:
            return None
        if old_key is not None and old_key != new_key:
            try:
                tm_db.renumber_cue(*old_key, *new_key)
            except ValueError as exc:
                row = s.get(SRCue, cue['id'])
                row.number, row.point = str(old_key[0]), old_key[1]
                s.add(row)
                s.commit()
                return f'{exc}; the cue keeps {old_key[0]}.{old_key[1]}'
        if tm_db.get_cue(*new_key) is not None:
            tm_db.update_cue(*new_key, name=cue['name'] or '')
            return None
        # else: undo of a delete, the .tmix cue is gone, so it is re-created
    return _adopt(s, tm_db, show_id, list_id, layer, cue)
