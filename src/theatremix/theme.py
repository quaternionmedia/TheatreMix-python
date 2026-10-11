"""Colours and cell-state rules for the /theatremix DCA grid.

Colour values are Quasar palette names (e.g. 'green-4', 'white'). The UI
applies them as text-<name> / bg-<name> classes. Edit this file, or override
per show in show.toml under [plugins.theatremix.colors] (see docs/theme.md).
"""

from __future__ import annotations

# Text colour of a DCA cell, by its state compared with the previous cue.
COLORS: dict[str, str] = {
    'new': 'green-4',  # label set or changed since the previous cue
    'same': 'white',  # label unchanged from the previous cue
    'cleared': 'red-4',  # DCA cleared (muted) in this cue
    'empty': 'grey-7',  # no label
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


def cell_state(prev: tuple, cur: tuple) -> str:
    """Grid state of a DCA cell: compares (label, channels) with the previous cue's cell.

    Returns one of the keys of COLORS: 'cleared', 'empty', 'new' or 'same'.
    """
    prev = tuple(x or '' for x in prev)
    cur = tuple(x or '' for x in cur)
    if not any(cur):
        return 'cleared' if any(prev) else 'empty'
    return 'same' if cur == prev else 'new'


def row_colour(index: int | None) -> str:
    """Quasar colour for Cue.colour, or '' when there is none or the index is unknown."""
    if index and 0 < index < len(ROW_COLOURS):
        return ROW_COLOURS[index]
    return ''
