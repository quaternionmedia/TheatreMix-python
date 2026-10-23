"""Colours and cell-state rules for the /theatremix DCA grid.

Colour values are Quasar palette names (e.g. 'green-4', 'white'). The UI
applies them as text-<name> / bg-<name> classes. Edit this file, or override
per show in show.toml under [plugins.theatremix.colors] (see docs/theme.md).
"""

from __future__ import annotations

# Background colour of a DCA cell, by what the DCA does in the NEXT cue.
COLORS: dict[str, str] = {
    'stays_on': 'green-8',  # same channels assigned in the next cue
    'muted_next': 'grey-7',  # on in this cue, muted (no channels) in the next cue
    'changed': 'orange-8',  # channels on now and different in the next cue
}

# Cue.colour is an index into this list (0 = no tint). The TheatreMix app's own
# palette is not documented, so these are only a starting point.
ROW_COLOURS: list[str] = [
    '',
    'red-10',
    'orange-10',
    'yellow-10',
    'green-10',
    'cyan-10',
    'blue-10',
    'purple-10',
    'pink-10',
    'grey-8',
]


def override(values: dict | None) -> None:
    """Apply [plugins.theatremix.colors] from show.toml. Unknown keys are ignored."""
    for state, colour in (values or {}).items():
        if state in COLORS and isinstance(colour, str):
            COLORS[state] = colour


def dca_cell(cue, dca: int) -> tuple[str, str]:
    """(label, channels) of one DCA on a cue; None becomes ''."""
    label = getattr(cue, f'dca{dca:02d}Label', None) or ''
    channels = getattr(cue, f'dca{dca:02d}Channels', None) or ''
    return label, channels


def cell_state(cur: tuple, nxt: tuple | None) -> str:
    """Grid state of a DCA cell, from (label, channels) of this cue and the next cue.

    Returns a key of COLORS, or '' for no tint. A cell counts as on when it has channels.
    nxt is None on the last cue, which has no next cue to compare with.
    """
    if nxt is None:
        return ''
    channels = cur[1] or ''
    next_channels = nxt[1] or ''
    if not channels:
        return ''
    if channels == next_channels:
        return 'stays_on'
    if not next_channels:
        return 'muted_next'
    return 'changed'


def row_colour(index: int | None) -> str:
    """Quasar colour for Cue.colour, or '' when there is none or the index is unknown."""
    if index and 0 < index < len(ROW_COLOURS):
        return ROW_COLOURS[index]
    return ''
