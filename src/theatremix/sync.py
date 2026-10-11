"""Mirror a .tmix cue list into linked ShowRunner cues (layer 'Mix').

The .tmix file holds the DCA data. ShowRunner only gets one thin cue per
.tmix cue, matched by (number, point), so it shows up in ShowRunner's cue
views. Links are never created or edited from the ShowRunner side.
"""

from __future__ import annotations

from sqlmodel import Session, select

from showrunner.models import Cue as SRCue, CueList as SRCueList

from .models import Cue as TMCue

LAYER = 'Mix'
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
) -> None:
    """Make the linked 'Mix' cues in cue_list_id match tm_cues exactly.

    renames maps old (number, point) to new, so a renumbered cue keeps its
    ShowRunner row (and script_line). Cues in the list that are not
    'Mix'/'TheatreMix' are left alone.
    """
    existing = {
        _key(c.number, c.point): c
        for c in s.exec(
            select(SRCue).where(
                SRCue.cue_list_id == cue_list_id,
                SRCue.layer == LAYER,
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
            cue_list_id=cue_list_id, layer=LAYER, cue_type=CUE_TYPE
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
